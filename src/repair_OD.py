import csv
import sys
import os
import openai
import datetime
import utils
import subprocess
import re
import time
import update_pom
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
import torch
from bs4 import BeautifulSoup
from pathlib import Path
import json
import signal

os.environ["CUDA_VISIBLE_DEVICES"] = "0,1,2"
device = "cuda"

run_nondex_cmds = "src/cmds/run_nondex.sh"
run_surefire_cmds = "src/cmds/run_surefire.sh"

java_standard_libs = json.load(open("src/utils/java_standard_libs.json"))

def handler(signum, frame):
    raise ValueError("TimesUpError")

def main(pr_csv, clone_dir, test_file_info, model, nondex_times,result_csv,result_json,save_dir):
    model_load_path = {
            "MagicCoder": os.getenv("MagiCoder_LOAD_PATH"),
    }
    if model == "MagicCoder":
        print("Loading model...")
        loading_model = AutoModelForCausalLM.from_pretrained(load_path[model], device_map="auto", cache_dir='./huggingface')
        tokenizer = AutoTokenizer.from_pretrained(load_path[model], cache_dir='./huggingface')
    elif model == "CodeLlama":
        loading_model = AutoModelForCausalLM.from_pretrained(load_path[model], device_map="auto", cache_dir='./huggingface', offload_folder = './huggingface')
        tokenizer = AutoTokenizer.from_pretrained(load_path[model], cache_dir='./huggingface')
    elif model == "GPT-4":
        loading_model = "GPT-4"
        tokenizer = None


    test_info_csv = test_file_info.replace("json", "csv")
    
    test_file_info_heads = ["project", "project_name", "sha", "module", 
                            "test_type","victim", "victim_name", "polluter", "polluter_name",
                            "status", "PR_link", "notes", 
                            "victim_file_path", "polluter_file_path",
                            "patch_file", "test_results", "if_flaky", "Exceptions", "time"]
    utils.write_header_csv(test_info_csv,test_file_info_heads)

    result_csv_heads = ["project", "sha", "module", 
                        "test_type","victim", "victim_name","polluter", "polluter_name",
                        "status", "PR_link", "notes", 
                        "victim_file_path", "polluter_file_path",
                        "patch_file", "test_results", "jdk",
                        "build_results", "Exceptions", "all_round_logs", "time", "if_flaky"]
    utils.write_header_csv(result_csv,result_csv_heads)
    
    test_info = {}
    idx = 0
    with open(pr_csv, mode ='r')as file:
        csvFile = csv.reader(file)
        for line in csvFile:
            if "Project URL" in line or "project_url" in line or "project" in line:
                continue

            project = line[0]
            project_name = project.split("/")[-1]
            sha = line[1]
            module = line[2]
            victim = line[3]
            polluter = line[4]
            
            tag = project + "#" + sha + "#" + module + "#" + victim
            project_dir = os.path.join(clone_dir, sha, project_name)
            utils.git_stash(project_dir)
            victim_class_name = victim.split(".")[-2]
            victim_test_class = ".".join(victim.split(".")[:-1])
            polluter_class_name = polluter.split(".")[-2]
            polluter_test_class = ".".join(polluter.split(".")[:-1])
            test_type = "OD"

            victim_file_path_found = False
            polluter_file_path_found = False
            polluter_file_path, victim_file_path = None, None

            if tag not in test_info:
                info = { "project":project, "project_name":project_name, "sha":sha, "module":module, 
                            "test_type":test_type,"victim": victim, "victim_name": victim.split(".")[-1],
                            "polluter": polluter, "polluter_name": polluter.split(".")[-1],
                            "project_dir": project_dir,
                            "victim_test_class": victim_test_class, "polluter_test_class":polluter_test_class,
                            "victim_file_path":None, "polluter_file_path": None,
                            "relative_victim_file_path": None,"relative_polluter_file_path": None, 
                            "time": None,
                            "victim_class_content":{}, "polluter_class_content":{}, 
                            "victim_method_content": None, "polluter_method_content": None, 
                            "victim_class_imports": None, "polluter_class_imports": None,
                            "patch_file":None, "all_round_logs": None,
                            "jdk": None, "Exceptions": {}, "if_flaky": None,
                            "prompts": {}, "responses": {}, "pom": None,
                            "patches_before_stitching": {}, "patches_after_stitching": {},
                            "test_results":{}, "test_logs":{},
                            "polluter_err_msg":{}, "polluter_err_code":{}, 
                            "victim_err_msg":{}, "victim_err_code":{}, 
                            "build_results": {},
                            "status":None, "PR_link":None, "notes":None,
                        }
                test_done = False
                victim_test_path = "/".join(victim.split(".")[:-1])
                polluter_test_path = "/".join(polluter.split(".")[:-1])
                for root, dirs, files in os.walk(project_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        if victim_test_path in file_path and module in file_path \
                            and "/test-classes/" not in file_path and "/test/" in file_path \
                            and file.endswith(victim_class_name + ".java"):
                            victim_file_path_found = True
                            victim_file_path = file_path
                            relative_victim_file_path = file_path.split(project_dir + "/")[-1]
                            utils.git_checkout_file(project_dir,relative_victim_file_path)
                            victim_class_content = utils.read_file(victim_file_path)
                            info["relative_victim_file_path"] = relative_victim_file_path
                            info["victim_file_path"] = file_path
                            info["victim_class_content"][0] = victim_class_content
                            info["victim_class_imports"] = utils.get_imports(victim_class_content)
                            info["victim_method_content"] = utils.get_test_method(info["victim_name"],victim_class_content)
                            if "/src/" in file_path:
                                root_path = file_path.split("/src/")[0]
                                pom_path = os.path.join(root_path,"pom.xml")
                                if os.path.exists(pom_path):
                                    info["pom"] = pom_path

                        if polluter_test_path in file_path and module in file_path \
                            and "/test-classes/" not in file_path and "/test/" in file_path \
                            and file.endswith(polluter_class_name + ".java"):
                            polluter_file_path_found = True
                            polluter_file_path = file_path
                            relative_polluter_file_path = file_path.split(project_dir + "/")[-1]
                            utils.git_checkout_file(project_dir,relative_polluter_file_path)
                            polluter_class_content = utils.read_file(polluter_file_path)
                            info["relative_polluter_file_path"] = relative_polluter_file_path
                            info["polluter_file_path"] = file_path
                            info["polluter_class_content"][0] = polluter_class_content
                            info["polluter_class_imports"] = utils.get_imports(polluter_class_content)
                            info["polluter_method_content"] = utils.get_test_method(info["polluter_name"],polluter_class_content)

                if victim_file_path_found and polluter_file_path_found:
                    jdk = "8"
                    surefire_output = run_test_with_surefire(project_dir,module,victim, polluter,jdk)
                    build_result = analyze_surefire_build_result(surefire_output)
                    test_result = analyze_surefire_test_result(surefire_output)
                    print(build_result, test_result)
                    
                    if test_result == "test_failure":
                        idx += 1
                        info["jdk"] = jdk
                        info["test_logs"][0] = surefire_output
                        info["test_results"][0] = test_result
                        info["build_results"][0] = build_result
                        polluter_err_msg_list, victim_err_msg_list, \
                        polluter_err_code_list, victim_err_code_list = parse_err_msg(surefire_output, polluter, victim, \
                            polluter_test_class, victim_test_class, polluter_class_content, victim_class_content)
                        info["polluter_err_msg"][0] = polluter_err_msg_list
                        info["polluter_err_code"][0] = polluter_err_code_list
                        info["victim_err_msg"][0] = victim_err_msg_list
                        info["victim_err_code"][0] = victim_err_code_list
                        info["if_flaky"] = "True"
                        test_info[tag] = info
                        try:
                        # if True:
                            result_dict = repair_OD_tests(info, model,result_csv,result_json,save_dir, idx, loading_model, tokenizer)
                        except Exception as e:
                            info["Exceptions"] = str(e)
                        test_done = True
                        # exit(0)
                    elif test_result == "test_pass":
                        info["jdk"] = jdk
                        info["test_logs"][0] = surefire_output
                        info["test_results"][0] = test_result
                        info["build_results"][0] = build_result
                        info["if_flaky"] = "False"
                    elif test_result == "build_failure" or test_result == "compilation_error":
                        jdk = "11"
                        surefire_output = run_test_with_surefire(project_dir,module,victim, polluter,jdk)
                        build_result = analyze_surefire_build_result(surefire_output)
                        test_result = analyze_surefire_test_result(surefire_output)
                        print(build_result, test_result)
                        
                        if test_result == "test_failure":
                            idx += 1
                            info["jdk"] = jdk
                            info["test_logs"][0] = surefire_output
                            info["test_results"][0] = test_result
                            info["build_results"][0] = build_result
                            polluter_err_msg_list, victim_err_msg_list, \
                            polluter_err_code_list, victim_err_code_list = parse_err_msg(surefire_output, polluter, victim, \
                                polluter_test_class, victim_test_class, polluter_class_content, victim_class_content)
                            info["polluter_err_msg"][0] = polluter_err_msg_list
                            info["polluter_err_code"][0] = polluter_err_code_list
                            info["victim_err_msg"][0] = victim_err_msg_list
                            info["victim_err_code"][0] = victim_err_code_list
                            info["if_flaky"] = "True"
                            test_info[tag] = info
                            try:
                            # if True:
                                result_dict = repair_OD_tests(info, model,result_csv,result_json,save_dir, idx, loading_model, tokenizer)
                            except Exception as e:
                                info["Exceptions"] = str(e)
                            test_done = True
                            # exit(0)
                        elif test_result == "test_pass":
                            info["jdk"] = jdk
                            info["test_logs"][0] = surefire_output
                            info["test_results"][0] = test_result
                            info["build_results"][0] = build_result
                            info["if_flaky"] = "False"
                #     if test_done:
                #             break
                # if test_done:
                #     break

                if not victim_file_path_found or not polluter_file_path_found:  
                    info["Exceptions"][0] = "method_code_location_failure"
                
                res = {}
                for key in test_file_info_heads:
                    res[key] = info[key]
                utils.write_dict_csv(test_info_csv, test_file_info_heads, res)
                
                #TODO: handle cases that test method not found
                # if test_info["test_method_content"] == None:
                #     print(tag, "Not Found Test Code.", test_info["victim_file_path"])
                utils.write_json_attach(test_file_info,info)
    # print(len(test_info))
    return test_info

def run_test_with_surefire(project_dir, module, victim_fullname,polluter_fullname, jdk):
    polluter_test = utils.replace_last_symbol(polluter_fullname, ".", "#")
    victim_test = utils.replace_last_symbol(victim_fullname, ".", "#")
    result = subprocess.run(["bash",run_surefire_cmds,project_dir,module,polluter_test,victim_test,jdk], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output = result.stdout.decode('utf-8')
    print(output)
    return output

def analyze_surefire_build_result(output):
    output_list = output.split("\n")
    result = "BUILD FAILURE"
    for line in output_list:
        if "BUILD FAILURE" in line:
            result = "BUILD FAILURE"
        elif "BUILD SUCCESS" in line:
            result = "BUILD SUCCESS"
    
    return result

def analyze_surefire_test_result(output):
    all_test_results = []
    output_list = output.split("\n")
    for line in output_list:
        if "Tests run: 2, Failures: 0, Errors: 0, Skipped: 0" in line:
            all_test_results.append("test_pass")
        elif "Tests run: 2, Failures: 1, Errors: 0, Skipped: 0" in line:
            all_test_results.append("test_failure")
        elif "Tests run: 2, Failures: 0, Errors: 1, Skipped: 0" in line:
            all_test_results.append("test_failure")
        elif "Tests run: 2, Failures: 0, Errors: 2, Skipped: 0" in line\
            or "Tests run: 2, Failures: 2, Errors: 0, Skipped: 0" in line:
            all_test_results.append("test_failure")
    if len(all_test_results) == 0:
        if "COMPILATION ERROR" in output:
            return "compilation_error"
        elif "BUILD FAILURE" in output:
            return "build_failure"
        elif "processing the POMs" in output:
            return "pom_error"
        else:
            return "build_failure"
    if "test_pass" in all_test_results and "test_failure" not in all_test_results:
        return "test_pass"
    else:
        return "test_failure"

def parse_compilation_err(output, polluter_test_class,victim_test_class, polluter_class_content,victim_class_content):
    polluter_class_file = polluter_test_class.split(".")[-1] + ".java"
    victim_class_file = victim_test_class.split(".")[-1] + ".java"
    #polluter_err_msg_list, victim_err_msg_list, polluter_err_code_list, victim_err_code_list

    polluter_err_msg_list = []
    polluter_err_code_list = []
    polluter_lineno_list = []
    
    victim_err_msg_list = []
    victim_err_code_list = []
    victim_lineno_list = []

    for output_line in output.split("\n"):
        p_lineno = None
        v_lineno = None
        if polluter_class_file in output_line:
            p_lineno_str = str(output_line).split(polluter_class_file + ":")[-1].split(")")[0]
            try:
                p_lineno = int(p_lineno_str)
            except:
                pass
        if polluter_class_file in output_line and "[" in output_line and "]" in output_line:
            p_lineno_str = str(output_line).split(polluter_class_file + ":")[-1].split("[")[-1].split(",")[0].split("]")[0]
            try:
                p_lineno = int(p_lineno_str)
            except:
                pass
        if p_lineno != None and p_lineno not in polluter_lineno_list:
            polluter_lineno_list.append(p_lineno)

        if victim_class_file in output_line:
            v_lineno_str = str(output_line).split(victim_class_file + ":")[-1].split(")")[0]
            try:
                v_lineno = int(v_lineno_str)
            except:
                pass
        if victim_class_file in output_line and "[" in output_line and "]" in output_line:
            v_lineno_str = str(output_line).split(victim_class_file + ":")[-1].split("[")[-1].split(",")[0].split("]")[0]
            try:
                v_lineno = int(v_lineno_str)
            except:
                pass
        if v_lineno != None and v_lineno not in victim_lineno_list:
            victim_lineno_list.append(v_lineno)

    for number in polluter_lineno_list:
        err_code = polluter_class_content.split("\n")[int(number)-1]
        if err_code.strip() not in polluter_err_code_list:
            polluter_err_code_list.append(err_code.strip())
    
    for number in victim_lineno_list:
        err_code = victim_class_content.split("\n")[int(number)-1]
        if err_code.strip() not in victim_err_code_list:
            victim_err_code_list.append(err_code.strip())
        
    seq = output.split("[INFO] Finished at:")[-1].split("To see the full stack trace of the errors")[0].replace("-> [Help 1]", "")
    for line in seq.split("\n"):
        if "Failed to execute goal" in line:
            continue
        if not line.startswith("[ERROR]"):
            continue
        tmp_line = line.replace("[ERROR]","").strip()
        if polluter_class_file in tmp_line:
            msg = tmp_line.split("]")[-1]
            if msg not in polluter_err_code_list:
                polluter_err_msg_list.append(msg)
        if victim_class_file in tmp_line:
            msg = tmp_line.split("]")[-1]
            if msg not in victim_err_code_list:
                victim_err_msg_list.append(msg)
        if polluter_class_file not in tmp_line and victim_class_file not in tmp_line:
            polluter_err_msg_list.append(tmp_line)
            victim_err_msg_list.append(tmp_line)
    return polluter_err_msg_list, victim_err_msg_list, polluter_err_code_list, victim_err_code_list

def parse_err_msg(output,polluter,victim,polluter_test_class,victim_test_class, polluter_class_content,victim_class_content):
    polluter_test_method_name = polluter.split(".")[-1]
    victim_test_method_name = victim.split(".")[-1]

    polluter_err_msg_list = [] # error message from log
    polluter_err_code_list = [] # which test code causes the error
    polluter_lineno_list = []

    victim_err_msg_list = [] # error message from log
    victim_err_code_list = [] # which test code causes the error
    victim_lineno_list = []

    polluter_class_file = polluter_test_class.split(".")[-1] + ".java"
    victim_class_file = victim_test_class.split(".")[-1] + ".java"
    #TODO double check parsing for compilation errors
    if "COMPILATION ERROR" in output:
        polluter_err_msg_list, victim_err_msg_list, polluter_err_code_list, victim_err_code_list = parse_compilation_err(output, polluter_test_class,victim_test_class, polluter_class_content,victim_class_content)
        return polluter_err_msg_list, victim_err_msg_list, polluter_err_code_list, victim_err_code_list

    print(polluter_class_file, victim_class_file)

    for output_line in output.split("\n"):
        p_lineno = None
        v_lineno = None
        #polluter
        if polluter_class_file in output_line:
            p_lineno_str = str(output_line).split(polluter_class_file + ":")[-1].split(")")[0]
            try:
                p_lineno = int(p_lineno_str)
            except:
                pass
        if polluter_class_file in output_line and "[" in output_line and "]" in output_line:
            p_lineno_str = str(output_line).split(polluter_class_file + ":")[-1].split("[")[-1].split(",")[0].split("]")[0]
            try:
                p_lineno = int(p_lineno_str)
            except:
                pass
        if p_lineno != None and p_lineno not in polluter_lineno_list:
            polluter_lineno_list.append(p_lineno)
        #victim
        if victim_class_file in output_line:
            v_lineno_str = str(output_line).split(victim_class_file + ":")[-1].split(")")[0]
            try:
                v_lineno = int(v_lineno_str)
            except:
                pass
        if victim_class_file in output_line and "[" in output_line and "]" in output_line:
            v_lineno_str = str(output_line).split(victim_class_file + ":")[-1].split("[")[-1].split(",")[0].split("]")[0]
            try:
                v_lineno = int(v_lineno_str)
            except:
                pass
        if v_lineno != None and v_lineno not in victim_lineno_list:
            victim_lineno_list.append(v_lineno)

    for number in polluter_lineno_list:
        err_code = polluter_class_content.split("\n")[int(number)-1]
        if err_code.strip() not in polluter_err_code_list:
            polluter_err_code_list.append(err_code.strip())
    
    for number in victim_lineno_list:
        err_code = victim_class_content.split("\n")[int(number)-1]
        if err_code.strip() not in victim_err_code_list:
            victim_err_code_list.append(err_code.strip())

    for line in output.split("\n"):
        if "Please refer to" in line and "for the individual test results" in line:
            xml_dir = line.split("Please refer to")[-1].split("for")[0].strip()
            for root, dirs, files in os.walk(xml_dir):
                for file in files:
                    if file.endswith(".xml") and "TEST-" + polluter_test_class in file:
                        xml_path = os.path.join(root, file)
                        with open(xml_path, 'r') as f:
                            data = f.read()
                        bs_data = BeautifulSoup(data, 'xml')
                        for tag in bs_data.find_all('testcase', {'classname':polluter_test_class}, {'name':polluter_test_method_name}):
                            err_element = tag.find('error')
                            if err_element:
                                err_msg = err_element.get('message')
                                err_type = err_element.get('type')
                                if err_msg == None:
                                    err_msg = err_type
                                final_err_msg = ' '.join(err_msg.split())
                                if final_err_msg not in polluter_err_msg_list:
                                    polluter_err_msg_list.append(final_err_msg.strip())
                                
                            failure_element = tag.find('failure')
                            if failure_element:
                                failure_msg = failure_element.get('message')
                                failure_type = failure_element.get('type')
                                if failure_msg == None:
                                    failure_msg = failure_type
                                final_failure_msg = ' '.join(failure_msg.split())
                                if final_failure_msg not in polluter_err_msg_list:
                                    polluter_err_msg_list.append(final_failure_msg.strip())

                    if file.endswith(".xml") and "TEST-" + victim_test_class in file:
                        xml_path = os.path.join(root, file)
                        with open(xml_path, 'r') as f:
                            data = f.read()
                        bs_data = BeautifulSoup(data, 'xml')
                        for tag in bs_data.find_all('testcase', {'classname':victim_test_class}, {'name':victim_test_method_name}):
                            err_element = tag.find('error')
                            if err_element:
                                err_msg = err_element.get('message')
                                err_type = err_element.get('type')
                                if err_msg == None:
                                    err_msg = err_type
                                final_err_msg = ' '.join(err_msg.split())
                                if final_err_msg not in victim_err_msg_list:
                                    victim_err_msg_list.append(final_err_msg.strip())
                                
                            failure_element = tag.find('failure')
                            if failure_element:
                                failure_msg = failure_element.get('message')
                                failure_type = failure_element.get('type')
                                if failure_msg == None:
                                    failure_msg = failure_type
                                final_failure_msg = ' '.join(failure_msg.split())
                                if final_failure_msg not in victim_err_msg_list:
                                    victim_err_msg_list.append(final_failure_msg.strip())
    # print(polluter_err_msg_list, victim_err_msg_list, polluter_err_code_list, victim_err_code_list)
    # print(polluter_lineno_list, victim_lineno_list)
    # exit(0)                 
    return polluter_err_msg_list, victim_err_msg_list, polluter_err_code_list, victim_err_code_list

def get_potential_API(test_content):
    potential_apis = {
        "entrySet()":[], ".keySet()":[], ".values()":[],
        ".iterator()":[], ".toArray()":[], ".toString()":[], ".getGenericExceptionTypes()":[],
        ".getDeclaredAnnotations()":[], ".getParameterAnnotations()":[], ".getDeclaredMethods()":[], 
        ".getClasses()":[], ".getFields()":[],
        ".getMethods()":[], ".getConstructors()":[],
        ".getDeclaredClasses()":[], ".getDeclaredFields()":[],
        ".getDeclaredConstructors()":[],".getAnnotations()":[],
        ".getDeclaredAnnotations()":[],".getAnnotationsByType()":[],
        ".getDeclaredAnnotations()":[],".list()":[],
        ".listFiles()":[], ".listRoots()":[],
        ".getAvailableLocales()":[], ".getZoneStrings()":[],
        " HashMap":[], " HashSet":[], "Gson()":[]
    }
    if test_content != None:
        lines = test_content.split("\n")
        for api in potential_apis:
            for line in lines:
                if api in line:
                    potential_apis[api].append(line)
    return potential_apis

def generate_prompts(model, victim_name, polluter_name, test_type, \
        victim_method_content, polluter_method_content, victim_err_msg, polluter_err_msg,\
        victim_err_code,polluter_err_code, \
        victim_helper_methods, polluter_helper_methods, \
        victim_global_vars, polluter_global_vars,\
        round, loading_model, tokenizer):
    print("Generating prompt...")

    code_content = ""
    for method_name in victim_helper_methods["before"]:
        code_content += victim_helper_methods["before"][method_name]
    for method_name in victim_helper_methods["after"]:
        code_content += victim_helper_methods["after"][method_name]
    
    for method_name in polluter_helper_methods["before"]:
        code_content += polluter_helper_methods["before"][method_name]
    for method_name in polluter_helper_methods["after"]:
        code_content += polluter_helper_methods["after"][method_name]
    
    code_content += victim_method_content
    code_content += polluter_method_content

    global_vars = ""

    for key in victim_global_vars:
        global_vars += victim_global_vars[key] + "\n"
    for key in polluter_global_vars:
        global_vars += polluter_global_vars[key] + "\n"

    err_code = ""
    err_code += " ".join(polluter_err_code) + " " + " ".join(victim_err_code)

    err_msg = ""
    err_msg += " ".join(polluter_err_msg) + " " + " ".join(victim_err_msg)

    # print(code_content, global_vars, polluter_err_code,victim_err_code, err_msg)

    response = None

    OD_description = """
    Flaky tests non-deterministically pass or fail due to dependencies of test orders. 
    A polluter test pollutes the shared status with victim test, which makes the victim fail.
    When two tests are dependent on each other through a shared state, This shared state can be a variable used by two tests, a file that both tests write or read from, or any resource that is shared between two tests.
    Flakiness can be resolved by removing the dependency between tests.
    But if you didn't find above similar cases, you should fix by other ways, to make sure the test will always pass.
    """

    if model == "GPT-4":

        gpt_prompt ="""You are a software testing expert. 
            I want you to fix a flaky test. \n{}\n
            {} is the victim flaky test you need to fix, {} is the polluter, they are located in the following code of a java class:\n {}\n
            When the test fails, I get the following error:\n {}\n The error is caused by {}.
            Follow steps below, I want you to only reply with all code inside one unique code block, do not write anything else.
            do not write explanations. do not put original method in your answer.
            1) Fix the flakiness and print the fixed complete method code of this test between //<fix start> and //<fix end>.
                Your code should be compilable without any errors.
                Make sure all the arguments are correct.
                Use compatible types for all variables.
                Do not define or write helper methods out of the test, make sure all methods you want to call are inside the test method.
                Do not use try-catch to avoid assertion error.
            2) Update dependencies in pom.xml if needed,
                put the code between <!-- <pom.xml start> --> and <!-- <pom.xml end> -->.
                Provide a specific version for the dependency you add. Do not add existing dependencies. Do not add my artifact in dependencies, do not include my artifact in your pom.xml code.
            3) Update import list if needed,
                put the code between //<import start> and //<import end>.
                Assume required classes in the original code are setup correctly, do not include them in your code.
        """.format(OD_description, victim_name, polluter_name, code_content,err_msg, err_code)
        print(gpt_prompt)

        full_response = openai.ChatCompletion.create(
            model = "gpt-4", #"gpt-3.5-turbo",
            temperature = 0.2,
            messages = [
                {"role": "user", 
                "content":gpt_prompt}
            ]
        )
        response = full_response["choices"][0]["message"]["content"]

        return response,gpt_prompt

    elif model == "MagicCoder":
        magiccoder_prompt = """You are an exceptionally intelligent coding assistant that consistently delivers accurate and reliable responses to user instructions.
        @@ Instruction
        I want you to fix a flaky test. \n{}\n
        {} is the victim flaky test you need to fix, {} is the polluter, they are located in the following code of a java class:\n {}\n
        When the test fails, I get the following error:\n {}\n The error is caused by {}.
        Follow steps below, I want you to only reply with all code inside one unique code block, do not write anything else.
        do not write explanations. do not put original method in your answer.
        Fix the flakiness and print the fixed complete method code of this test between //<fix start> and //<fix end>.
        Do not define or write helper methods out of the test, make sure all methods you want to call are inside the test method.
        Do not use try-catch to avoid assertion error.
        Update dependencies in pom.xml if needed,
        put the code between <!-- <pom.xml start> --> and <!-- <pom.xml end> -->.
        Provide a specific version for the dependency you add. Do not add existing dependencies. Do not add my artifact in dependencies, do not include my artifact in your pom.xml code.
        Update import list if needed,
        put the code between //<import start> and //<import end>.
        Assume required classes in the original code are setup correctly, do not include them in your code.
        @@ Response
        """.format(OD_description,  victim_name, polluter_name, code_content,err_msg, err_code)
        print(magiccoder_prompt)
        # loading_model = AutoModelForCausalLM.from_pretrained(load_path[model], device_map="auto", cache_dir='./huggingface')
        # tokenizer = AutoTokenizer.from_pretrained(load_path[model], cache_dir='./huggingface', load_in_4bit = True)

        model_inputs = tokenizer([magiccoder_prompt], return_tensors="pt").to(device)
        generated_ids = loading_model.generate(**model_inputs, max_new_tokens=2048 , temperature=0.2, do_sample=True)
        generated_text = tokenizer.batch_decode(generated_ids)[0]
        print(generated_text)
        return generated_text, magiccoder_prompt
    
    elif model == "StarCoder":
        starcoder_prompt = """
        <Task>
        Fix flaky test {}, located in the following java code. {} 
        I got the following error when running NonDex on it: {}. 
        Lines {} cause the flakiness. Lines {} may cause potential flakiness.
        </Task>
        <Code>
        {}
        </Code>
        <Instructions>
        Follow steps below, I want you to only reply with all code inside one unique code block, do not write anything else.
        do not write explanations. do not put original method in your answer.
        Fix the flakiness and print the fixed complete method code of this test between //<fix start> and //<fix end>.
        Your code should be compilable without any errors. Make sure all the arguments are correct.
        Use compatible types for all variables. Do not define or write helper methods out of the test, make sure all methods you want to call are inside the test method.
        Do not use try-catch to avoid assertion error.
        Update dependencies in pom.xml if needed,
        put the code between <!-- <pom.xml start> --> and <!-- <pom.xml end> -->.
        Provide a specific version for the dependency you add. Do not add existing dependencies. Do not add my artifact in dependencies, do not include my artifact in your pom.xml code.
        Update import list if needed,
        put the code between //<import start> and //<import end>.
        Assume required classes in the original code are setup correctly, do not include them in your code.
        </Instructions>
        <Your Response>
        """.format(test_method_name, ID_description, err_msg, err_code, p_code, test_method_content)
        starcoder_model = AutoModelForCausalLM.from_pretrained(load_path[model], device_map="auto", cache_dir='./huggingface', offload_folder = './huggingface')
        tokenizer = AutoTokenizer.from_pretrained(load_path[model], cache_dir='./huggingface')

        model_inputs = tokenizer([starcoder_prompt], return_tensors="pt").to(device)
        generated_ids = starcoder_model.generate(**model_inputs, max_new_tokens=2048, temperature=0.2, do_sample=True)
        generated_text = tokenizer.batch_decode(generated_ids)[0]
        # print(starcoder_prompt)
        return generated_text, starcoder_prompt

    elif model == "CodeLlama":
        codellama_prompt = """You are a software testing expert. You will fix a flaky test.
        [INST]
        Fix a flaky test. \n{}\n
        {} is the victim flaky test you need to fix, {} is the polluter, they are located in the following code of a java class:
        <Code>
        {}
        </Code>
        When the test fails, I get the following error:\n {}\n The error is caused by {}.
        <Instructions>
        Follow steps below, print the fixed test in the following format:
        Fix the flakiness and print the fixed complete method code of this test between //<fix start> and //<fix end>.
        Update dependencies in pom.xml if needed,put the code between <!-- <pom.xml start> --> and <!-- <pom.xml end> -->.
        Provide a specific version for the dependency you add. Do not add existing dependencies. Do not add my artifact in dependencies, do not include my artifact in your pom.xml code.
        Update import list if needed, put the code between //<import start> and //<import end>.
        </Instructions>
        [/INST]
        <Your Response>
        """.format(OD_description,  victim_name, polluter_name, code_content,err_msg, err_code)
        print(codellama_prompt)
        if code_content != None:
            max_length = len(code_content.split(" ")) + 300
        else:
            max_length = 512
        print("Max Length: {}".format(max_length))

        # loading_model = AutoModelForCausalLM.from_pretrained(load_path[model], device_map="auto", cache_dir='./huggingface', offload_folder = './huggingface')
        # tokenizer = AutoTokenizer.from_pretrained(load_path[model], cache_dir='./huggingface')

        model_inputs = tokenizer([codellama_prompt], return_tensors="pt").to(device)
        generated_ids = loading_model.generate(**model_inputs, max_new_tokens=max_length, temperature=0.2, do_sample=True)
        generated_text = tokenizer.batch_decode(generated_ids)[0]
        print(generated_text)
        return generated_text, codellama_prompt

def huggingface_generator(model, prompt, max_new_tokens):
        device = "cuda:0"
        hf_model, hf_tokenizer = model, tokenizer
        model_inputs = hf_tokenizer([prompt], return_tensors="pt").to(device)
        generated_ids = hf_model.generate(**model_inputs, max_new_tokens=max_new_tokens)
        generated_text = hf_tokenizer.batch_decode(generated_ids)[0]
        return generated_text

def repair_OD_tests(test_info, model,result_csv,result_json,save_dir, idx, loading_model, tokenizer):
    """
    1. Run test before repairing to confirm flakiness; return result_0 + error trace/location to generate the prompt;
    2. Prompt the model, generate patch, apply patch, run test, get new result + error trace/location

    """
    result_csv_heads = ["project", "sha", "module", 
                        "test_type","victim", "polluter", "victim_name","polluter_name",
                        "status", "PR_link", "notes", 
                        "victim_file_path","polluter_file_path",
                        "patch_file", "test_results", "jdk",
                        "build_results", "Exceptions", "all_round_logs", "time", "if_flaky"]
    print("Index {} {} is working on victim {}".format(idx, model, test_info["victim"]))
    if test_info:

        project = test_info["project"]
        sha = test_info["sha"]
        project_dir = test_info["project_dir"]
        module = test_info["module"]
        test_type = test_info["test_type"]
        jdk = test_info["jdk"]

        victim = test_info["victim"]
        victim_test_method_name = test_info["victim_name"]
        victim_test_method_content = test_info["victim_method_content"]
        victim_imports = test_info["victim_class_imports"]
        victim_file_path = test_info["victim_file_path"]
        relative_victim_file_path = test_info["relative_victim_file_path"]
        victim_err_msg = test_info["victim_err_msg"][0]
        victim_err_code = test_info["victim_err_code"][0]
        victim_class_content = test_info["victim_class_content"][0]
        original_victim_class_content = victim_class_content
        victim_test_class = test_info["victim_test_class"]

        polluter = test_info["polluter"]
        polluter_test_method_name = test_info["polluter_name"]
        polluter_test_method_content = test_info["polluter_method_content"]
        polluter_imports = test_info["polluter_class_imports"]
        polluter_file_path = test_info["polluter_file_path"]
        relative_polluter_file_path = test_info["relative_polluter_file_path"]
        polluter_err_msg = test_info["polluter_err_msg"][0]
        polluter_err_code = test_info["polluter_err_code"][0]
        polluter_class_content = test_info["polluter_class_content"][0]
        original_polluter_class_content = polluter_class_content
        polluter_test_class = test_info["polluter_test_class"]

        result_dict = {}
        utils.git_stash(project_dir)
        if victim_test_method_content == None or polluter_test_method_content == None:
            test_info["Exceptions"][0] = "method_code_location_failure"
            test_info["if_flaky"] = "False"
            for key in result_csv_heads:
                result_dict[key] = test_info[key]
            utils.write_dict_csv(result_csv, result_csv_heads,result_dict)
            utils.write_json_attach(result_json, result_dict)
            utils.git_checkout_file(project_dir,relative_file_path)
            return result_dict
        
        print("polluter_err_msg {}; victim_err_msg {}".format(polluter_err_msg, victim_err_msg))
        print("polluter_err_code {}; victim_err_code {}".format(polluter_err_code, victim_err_code))
        fixed = False

        t0 = time.perf_counter()

        round = 1
        while round <= 5:
            print("Index {}: ROUND {} to Repair Test {}".format(idx, round, victim))
            now = datetime.datetime.now()
            print("Starting prompt", now)
            #TODO: parse helper method
            victim_helper_methods = utils.get_helper_methods(victim_class_content)
            polluter_helper_methods = utils.get_helper_methods(polluter_class_content)

            victim_global_vars = utils.get_global_vars(victim_class_content, victim_helper_methods["earlist_line"])
            polluter_global_vars = utils.get_global_vars(polluter_class_content, polluter_helper_methods["earlist_line"])

            print(victim_helper_methods, polluter_helper_methods,victim_global_vars, polluter_global_vars )
            # exit(0)
            if model == "GPT-4":
                try:
                    response, prompt = "", ""
                    response, prompt = generate_prompts(model, victim_test_method_name, polluter_test_method_name, test_type, \
                        victim_test_method_content, polluter_test_method_content, victim_err_msg, polluter_err_msg,\
                        victim_err_code,polluter_err_code, \
                        victim_helper_methods, polluter_helper_methods, \
                        victim_global_vars, polluter_global_vars,\
                        round, loading_model, tokenizer)
                    patch,ifstitched = parse_patch_gpt(response, victim_test_method_name, polluter_test_method_name, \
                        victim_class_content, polluter_class_content, victim_test_method_content, polluter_test_method_content)
                except Exception as e:
                    test_info["prompts"][round] = prompt
                    test_info["responses"][round] = response
                    test_info["Exceptions"][round] = str(e)
                    break
            
            if model == "MagicCoder":
                signal.signal(signal.SIGALRM, handler)
                signal.alarm(300)
                try:
                # if True:
                    response, prompt = "", ""
                    response, prompt = generate_prompts(model, victim_test_method_name, polluter_test_method_name, test_type, \
                        victim_test_method_content, polluter_test_method_content, victim_err_msg, polluter_err_msg,\
                        victim_err_code,polluter_err_code, \
                        victim_helper_methods, polluter_helper_methods, \
                        victim_global_vars, polluter_global_vars,\
                        round, loading_model, tokenizer)
                    patch,ifstitched = parse_patch_magiccoder(response, victim_test_method_name, polluter_test_method_name, \
                        victim_class_content, polluter_class_content, victim_test_method_content, polluter_test_method_content)
                    # print(response)
                    # print(patch)
                    # exit(0)
                except Exception as e:
                    test_info["prompts"][round] = prompt
                    test_info["responses"][round] = response
                    test_info["Exceptions"][round] = str(e)
                    signal.alarm(0)
                    break
                signal.alarm(0)
            if model == "StarCoder":
                signal.signal(signal.SIGALRM, handler)
                signal.alarm(300)
                try:
                    response, prompt = "", ""
                    response, prompt = generate_prompts(model, test_method_name, test_type, test_method_content, err_msg, err_code, potential_apis,round, loading_model, tokenizer)
                    patch,ifstitched = parse_patch_magiccoder(response, test_method_name, test_class_content)
                except Exception as e:
                    test_info["prompts"][round] = prompt
                    test_info["responses"][round] = response
                    test_info["Exceptions"][round] = str(e)
                    signal.alarm(0)
                    break
                signal.alarm(0)
            if model == "CodeLlama":
                signal.signal(signal.SIGALRM, handler)
                signal.alarm(300)
                try:
                    response, prompt = "", ""
                    response, prompt = generate_prompts(model, victim_test_method_name, polluter_test_method_name, test_type, \
                        victim_test_method_content, polluter_test_method_content, victim_err_msg, polluter_err_msg,\
                        victim_err_code,polluter_err_code, \
                        victim_helper_methods, polluter_helper_methods, \
                        victim_global_vars, polluter_global_vars,\
                        round, loading_model, tokenizer)
                    patch,ifstitched = parse_patch_codellama(response, victim_test_method_name, polluter_test_method_name, \
                        victim_class_content, polluter_class_content, victim_test_method_content, polluter_test_method_content)
                except Exception as e:
                    test_info["prompts"][round] = prompt
                    test_info["responses"][round] = response
                    test_info["Exceptions"][round] = str(e)
                    signal.alarm(0)
                    break
                signal.alarm(0)
                
            end = datetime.datetime.now()
            print("Ending prompt", end)
            
            test_info["prompts"][round] = prompt
            test_info["responses"][round] = response
            test_info["patches_before_stitching"][round] = patch

            
            print(prompt)
            print(response)
            print(patch)
            print(patch["victim_test_code"])
            print(patch["polluter_test_code"])
            
            final_victim_class, final_polluter_class = apply_patch(victim_file_path, polluter_file_path, victim_class_content, polluter_class_content, \
                victim_test_method_name, polluter_test_method_name, patch, project, sha, project_dir)
            test_info["victim_class_content"][round] = final_victim_class
            test_info["polluter_class_content"][round] = final_polluter_class
            
            surefire_output = run_test_with_surefire(project_dir,module,victim, polluter,jdk)
            build_result = analyze_surefire_build_result(surefire_output)
            test_result = analyze_surefire_test_result(surefire_output)
            polluter_err_msg_list, victim_err_msg_list, \
            polluter_err_code_list, victim_err_code_list = parse_err_msg(surefire_output, polluter, victim, \
                polluter_test_class, victim_test_class, final_polluter_class, final_victim_class)

            test_info["build_results"][round] = build_result
            test_info["test_results"][round] = test_result
            test_info["polluter_err_msg"][round] = polluter_err_msg_list
            test_info["victim_err_msg"][round] = victim_err_msg_list
            test_info["polluter_err_code"][round] = polluter_err_code_list
            test_info["victim_err_code"][round] = victim_err_code_list
            
            print(polluter_err_msg_list, victim_err_msg_list)
            print(polluter_err_code_list, victim_err_code_list)
            print(test_result)
            if test_result == "build_failure" or test_result == "pom_error":
                if test_info["pom"] != None:
                    project_name = project.split("/")[-1]
                    pom_path = test_info["pom"].split(project_name + "/")[-1]
                    print("/home/ubuntu/flaky/" + project_dir, pom_path)
                    utils.git_checkout_file( "/home/ubuntu/flaky/" + project_dir,pom_path)

            
            victim_test_method_content = patch["victim_test_code"]
            victim_err_msg = victim_err_msg_list
            victim_err_code = victim_err_code_list

            polluter_test_method_content = patch["polluter_test_code"]
            polluter_err_msg = polluter_err_msg_list
            polluter_err_code = polluter_err_code_list

            victim_class_content = final_victim_class
            polluter_class_content = final_polluter_class

            if test_result == "test_pass":
                fixed = True
                print(polluter, victim, "test_pass")
                file_path = victim_file_path + "\n" + polluter_file_path
                patch_file = write_patch(save_dir, project, sha, module, victim, polluter, patch, test_info["victim_method_content"],test_info["polluter_method_content"],file_path , round)
                test_info["patch_file"] = patch_file
                patch_log = dump_all_rounds_patch(test_info, victim, polluter, file_path, save_dir, project, sha, module, test_info["victim_method_content"],test_info["polluter_method_content"], round)
                test_info["all_round_logs"] = patch_log
                break
                    
            round += 1

        if fixed == False:
            file_path = victim_file_path + "\n" + polluter_file_path
            patch_log = dump_all_rounds_patch(test_info, victim, polluter, file_path, save_dir, project, sha, module, test_info["victim_method_content"],test_info["polluter_method_content"], round-1)
            test_info["all_round_logs"] = patch_log
        t1 = time.perf_counter()
        print("Total generation time:", t1 - t0)
        test_info["time"] = t1 - t0
        for key in result_csv_heads:
            result_dict[key] = test_info[key]
        utils.write_dict_csv(result_csv, result_csv_heads,result_dict)
        utils.write_json_attach(result_json, result_dict)
        utils.git_checkout_file(project_dir,relative_victim_file_path)
        utils.git_checkout_file(project_dir,relative_polluter_file_path)
    return result_dict

def dump_all_rounds_patch(info, victim, polluter, file_path, patch_dir,project_url, sha, module, original_victim_method,original_polluter_method, round):
    project = project_url.split("/")[-1]
    patch_dir = os.path.join(save_dir,"all_rounds", project,sha,module,victim)
    Path(patch_dir).mkdir(parents=True, exist_ok=True)
    patch_file = os.path.join(patch_dir,str(round) + ".patch")

    content = """Test File Path: {}\n
    Original Polluter Method:\n {} \n
    Original Victim Method:\n {} \n
    """.format(file_path, original_polluter_method, original_victim_method)

    file = open(patch_file, 'w')
    file.write(content)
    file.close()

    patch_content = ""

    for r in range(1, round+1):
        if r in info["patches_before_stitching"]:
            patch_content += """
            ROUND {}:\n
            Before stitching: \n
            test_code:\n
            {}\n
            {}\n
            import:\n
            {}\n
            pom:\n
            {}\n
            """.format(r, info["patches_before_stitching"][r]["victim_test_code"], info["patches_before_stitching"][r]["polluter_test_code"], \
            info["patches_before_stitching"][r]["import"], info["patches_before_stitching"][r]["pom"])
        if r in info["patches_after_stitching"]:
            patch_content += """\n
            After stitching: \n
            test_code:\n
            {}\n
            {}\n
            import:\n
            {}\n
            pom:\n
            {}\n
            """.format(info["patches_after_stitching"][r]["victim_test_code"], info["patches_before_stitching"][r]["polluter_test_code"] ,\
            info["patches_after_stitching"][r]["import"], info["patches_after_stitching"][r]["pom"])
    
    file = open(patch_file, 'a')
    file.write(patch_content)
    file.close()

    return patch_file

def write_patch_stitch(save_dir, project_url, sha, module, test, patch, patch_before_stitching, original_test_method, file_path, round):
    project = project_url.split("/")[-1]
    patch_dir = os.path.join(save_dir,project,sha,module,test)
    Path(patch_dir).mkdir(parents=True, exist_ok=True)
    patch_file = os.path.join(patch_dir,str(round) + ".patch")

    content = """Test File Path: {}\n
    Original Test Method:\n {}
    """.format(file_path, original_test_method)

    file = open(patch_file, 'w')
    file.write(content)
    file.close()

    file = open(patch_file, 'a')
    file.write("\nPatch after Stitching:\n")
    file.close()

    for key in patch:
        file = open(patch_file, 'a')
        file.write("\n" + str(key) + ":\n" + str(patch[key]))
        file.close()

    file = open(patch_file, 'a')
    file.write("\nPatch before Stitching:\n")
    file.close()

    for key in patch_before_stitching:
        file = open(patch_file, 'a')
        file.write("\n" + str(key) + ":\n" + str(patch_before_stitching[key]))
        file.close()
    return patch_file


def write_patch(save_dir, project, sha, module, victim, polluter, patch, original_victim_method,original_polluter_method, file_path, round):
    project = project.split("/")[-1]
    patch_dir = os.path.join(save_dir,project,sha,module,victim)
    Path(patch_dir).mkdir(parents=True, exist_ok=True)
    patch_file = os.path.join(patch_dir,str(round) + ".patch")

    file = open(patch_file, 'w')
    content = """Test File Path: {}\n
    Original Polluter Method:\n {} \n
    Original Victim Method:\n {} \n
    """.format(file_path, original_polluter_method,original_victim_method )

    file.write(content)
    file.close()

    for key in patch:
        file = open(patch_file, 'a')
        file.write("\n" + str(key) + ":\n" + str(patch[key]))
        file.close()
    return patch_file

def apply_patch_stitch(file_path, original_test_class_content, test_method_name, patch, before_patch, project, sha, project_dir):
    fixed_class = original_test_class_content
    old_test_method_code = ""
    old_test_method = utils.get_test_method(test_method_name, original_test_class_content) #res = [start,end,method_name,method_code,node.annotations]
    if old_test_method != None:
        old_test_method_code = old_test_method
    if patch["test_code"] != None:
        fixed_class = original_test_class_content.replace(old_test_method_code, "\n" + patch["test_code"] + "\n")
        print("Code Replaced.")
    
    tmp_class = fixed_class

    final_class = fixed_class
    
    f = open(file_path, "w", errors='ignore')
    f.write(final_class)
    f.close()

    return final_class

def apply_import(file_path, original_test_class_content, test_method_name, patch_import, project, sha, project_dir):
    fixed_class = original_test_class_content
    if patch_import != None:
        package = utils.get_package(fixed_class)
        if package != None:
            seq = fixed_class.split(package)
            final_class = seq[0] + "\n" + package + "\n" + str(patch_import) + "\n" + seq[1]
        else:
            seq = fixed_class.split("public class ")
            print(fixed_class)
            final_class = seq[0] + "\n" + str((patch_import)) + "\n" + "public class " + seq[1]
    
        f = open(file_path, "w", errors='ignore')
        f.write(final_class)
        f.close()

    return final_class

def apply_patch(victim_file_path, polluter_file_path, victim_class_content, polluter_class_content, \
        victim_method_name, polluter_method_name, patch, project, sha, project_dir):
    if victim_file_path == polluter_file_path:
        fixed_class = victim_class_content
        old_victim_method_code = ""
        old_victim_method = utils.get_test_method(victim_method_name, victim_class_content) #res = [start,end,method_name,method_code,node.annotations]
        old_polluter_method_code = ""
        old_polluter_method = utils.get_test_method(polluter_method_name, victim_class_content)
        if old_victim_method != None:
            old_victim_method_code = old_victim_method
        if old_polluter_method != None:
            old_polluter_method_code = old_polluter_method
        if patch["victim_test_code"] != None:
            fixed_class = victim_class_content.replace(old_victim_method_code, "\n" + patch["victim_test_code"] + "\n")
            print("Victim Code Replaced.")
        if patch["polluter_test_code"] != None:
            fixed_class = victim_class_content.replace(old_polluter_method_code, "\n" + patch["polluter_test_code"] + "\n")
            print("Polluter Code Replaced.")
       
        
        final_class = fixed_class

        if patch["import"] != []:
            package = utils.get_package(fixed_class)
            if package != None:
                seq = fixed_class.split(package)
                final_class = seq[0] + "\n" + package + "\n" + "\n".join(patch["import"]) + "\n" + seq[1]
            else:
                seq = fixed_class.split("public class ")
                print(fixed_class)
                final_class = seq[0] + "\n".join(patch["import"]) + "\n" + "public class " + seq[1]
    
        f = open(victim_file_path, "w", errors='ignore')
        f.write(final_class)
        f.close()
        final_victim_class = final_class
        final_polluter_class = final_class

    elif victim_file_path != polluter_file_path:
        victim_fixed_class = victim_class_content
        old_victim_method_code = ""
        old_victim_method = utils.get_test_method(victim_method_name, victim_class_content) #res = [start,end,method_name,method_code,node.annotations]

        if old_victim_method != None:
            old_victim_method_code = old_victim_method

        if patch["victim_test_code"] != None:
            victim_fixed_class = victim_class_content.replace(old_victim_method_code, "\n" + patch["victim_test_code"] + "\n")
            print("Victim Code Replaced.")
        
        final_victim_class = victim_fixed_class
        if patch["import"] != []:
            package = utils.get_package(victim_fixed_class)
            if package != None:
                seq = victim_fixed_class.split(package)
                final_victim_class = seq[0] + "\n" + package + "\n" + "\n".join(patch["import"]) + "\n" + seq[1]
            else:
                seq = victim_fixed_class.split("public class ")
                final_victim_class = seq[0] + "\n".join(patch["import"]) + "\n" + "public class " + seq[1]
    
        f = open(victim_file_path, "w", errors='ignore')
        f.write(final_victim_class)
        f.close()
        
        #polluter
        polluter_fixed_class = polluter_class_content
        
        old_polluter_method_code = ""
        old_polluter_method = utils.get_test_method(polluter_method_name, polluter_class_content)
        if old_polluter_method != None:
            old_polluter_method_code = old_polluter_method
        if patch["polluter_test_code"] != None:
            polluter_fixed_class = polluter_class_content.replace(old_polluter_method_code, "\n" + patch["polluter_test_code"] + "\n")
            print("Polluter Code Replaced.")
        
        final_polluter_class = polluter_fixed_class
        if patch["import"] != []:
            package = utils.get_package(polluter_fixed_class)
            if package != None:
                seq = polluter_fixed_class.split(package)
                final_polluter_class = seq[0] + "\n" + package + "\n" + "\n".join(patch["import"]) + "\n" + seq[1]
            else:
                seq = polluter_fixed_class.split("public class ")
                final_polluter_class = seq[0] + "\n".join(patch["import"]) + "\n" + "public class " + seq[1]
    
        f = open(polluter_file_path, "w", errors='ignore')
        f.write(final_polluter_class)
        f.close()

    if patch["pom"] != None:
        dep2add = patch["pom"]
        deps = dep2add
        if "<dependencies>" in patch["pom"]:
            dep2add  = patch["pom"].replace("<dependencies>","")
        if "</dependencies>" in dep2add:
            deps = dep2add.replace("</dependencies>","")
        if "/src/" in victim_file_path:
            root_path = victim_file_path.split("/src/")[0]
            pom_path = os.path.join(root_path,"pom.xml")
            if os.path.exists(pom_path):
                update_pom.add_dependency(pom_path,deps)
                print("POM Updated.", pom_path)

    return final_victim_class, final_polluter_class

def parse_patch_codellama(full_response, victim_test_method_name, polluter_test_method_name, \
        victim_class_content, polluter_class_content, victim_test_method_content, polluter_test_method_content):
    ifstitched = False
    response = full_response.split("[/INST]")[-1]
    patch = {
        "victim_test_code": victim_test_method_content,
        "polluter_test_code": polluter_test_method_content,
        "import": [],
        "pom": None
    }

    tmp_lines = response.split("\n")
    pom_start_idx = None
    pom_end_idx = None
    pom_list = []
    for line in tmp_lines:
        if "<pom.xml start>" in line:
            pom_start_idx = tmp_lines.index(line)
        if "<pom.xml end>" in line:
            pom_end_idx = tmp_lines.index(line)
    if pom_start_idx != None and pom_end_idx != None:
        pom_list = tmp_lines[pom_start_idx+1:pom_end_idx]
    
    if len(pom_list):
        patch["pom"] = "\n".join(pom_list).replace("<dependencies>","").replace("</dependencies>","").replace("```xml","").replace("```","")


    import_pattern = re.compile(r"import\s+(static\s+)?([\w\.]+(\.\*)?);", re.MULTILINE)

    victim_original_imp_matches = import_pattern.findall(victim_class_content)
    polluter_original_imp_matches = import_pattern.findall(polluter_class_content)

    original_imports = []

    for imp_match in victim_original_imp_matches:
        if imp_match[0].strip() == "static" and imp_match[1] != '':
            imp_stat = "import static " + imp_match[1] + ";"
            original_imports.append(imp_stat)
        elif imp_match[0].strip() == "" and imp_match[1] != '':
            imp_stat = "import " + imp_match[1] + ";"
            original_imports.append(imp_stat)

    for imp_match in polluter_original_imp_matches:
        if imp_match[0].strip() == "static" and imp_match[1] != '':
            imp_stat = "import static " + imp_match[1] + ";"
            original_imports.append(imp_stat)
        elif imp_match[0].strip() == "" and imp_match[1] != '':
            imp_stat = "import " + imp_match[1] + ";"
            original_imports.append(imp_stat)

    imp_matches = import_pattern.findall(response)
    for imp_match in imp_matches:
        if imp_match[0].strip() == "static" and imp_match[1] != '':
            imp_stat = "import static " + imp_match[1] + ";"
            short_name = "." + imp_stat.split(".")[-1]
            if imp_stat not in original_imports and short_name not in str(original_imports) \
            and imp_stat not in patch["import"]:
                print("Will add {}".format(imp_stat))
                patch["import"].append(imp_stat)
            else:
                print("Will not add {}".format(imp_stat))
                if short_name in str(original_imports) and imp_stat not in str(original_imports):
                    print("Conflict_Import {}".format(short_name))
                    ifstitched = True
        elif imp_match[0].strip() == "" and imp_match[1] != '':
            imp_stat = "import " + imp_match[1] + ";"
            short_name = "." + imp_stat.split(".")[-1]
            if imp_stat not in original_imports and short_name not in str(original_imports) \
            and imp_stat not in patch["import"]:
                print("Will add {}".format(imp_stat))
                patch["import"].append(imp_stat)
            else:
                print("Will not add {}".format(imp_stat))
                if short_name in str(original_imports) and imp_stat not in str(original_imports):
                    print("Conflict_Import {}".format(short_name))
                    ifstitched = True

    java_methods,if_parsed = utils.extract_java_code(response)
    victim_patch_method = {}
    polluter_patch_method = {}
    if if_parsed == True:
        if len(java_methods) == 1:
            for method in java_methods:
                start_position = method[0]
                method_name = method[2]
                method_code = method[3]
                if method_name == victim_test_method_name:
                    patch["victim_test_code"] = (method_code)
                if method_name == polluter_test_method_name:
                    patch["polluter_test_code"] = (method_code)
        elif len(java_methods) > 1:
            for method in java_methods:
                start_position = method[0]
                method_name = method[2]
                method_code = method[3]
                if method_name == victim_test_method_name:
                    if start_position not in victim_patch_method:
                        victim_patch_method[start_position] = (method_code)
                        print("matching:",start_position, method_code)
                if method_name == polluter_test_method_name:
                    if start_position not in polluter_patch_method:
                        polluter_patch_method[start_position] = (method_code)
                        print("matching:",start_position, method_code)
            if len(victim_patch_method):
                max_start = max(victim_patch_method.keys())
                patch["victim_test_code"] = victim_patch_method[max_start]
                print("victim_test_code:",max_start, patch["victim_test_code"])
            if len(polluter_patch_method):
                max_start = max(polluter_patch_method.keys())
                patch["polluter_test_code"] = polluter_patch_method[max_start]
                print("polluter_test_code:",max_start, patch["polluter_test_code"])

    return patch,ifstitched

def parse_patch_magiccoder(full_response, victim_test_method_name, polluter_test_method_name, \
        victim_class_content, polluter_class_content, victim_test_method_content, polluter_test_method_content):
    ifstitched = False
    response = full_response.split("@@ Response")[-1]
    patch = {
        "victim_test_code": victim_test_method_content,
        "polluter_test_code": polluter_test_method_content,
        "import": [],
        "pom": None
    }

    tmp_lines = response.split("\n")
    pom_start_idx = None
    pom_end_idx = None
    pom_list = []
    for line in tmp_lines:
        if "<pom.xml start>" in line:
            pom_start_idx = tmp_lines.index(line)
        if "<pom.xml end>" in line:
            pom_end_idx = tmp_lines.index(line)
    if pom_start_idx != None and pom_end_idx != None:
        pom_list = tmp_lines[pom_start_idx+1:pom_end_idx]
    
    if len(pom_list):
        patch["pom"] = "\n".join(pom_list).replace("<dependencies>","").replace("</dependencies>","").replace("```xml","").replace("```","")


    import_pattern = re.compile(r"import\s+(static\s+)?([\w\.]+(\.\*)?);", re.MULTILINE)

    victim_original_imp_matches = import_pattern.findall(victim_class_content)
    polluter_original_imp_matches = import_pattern.findall(polluter_class_content)

    original_imports = []

    for imp_match in victim_original_imp_matches:
        if imp_match[0].strip() == "static" and imp_match[1] != '':
            imp_stat = "import static " + imp_match[1] + ";"
            original_imports.append(imp_stat)
        elif imp_match[0].strip() == "" and imp_match[1] != '':
            imp_stat = "import " + imp_match[1] + ";"
            original_imports.append(imp_stat)

    for imp_match in polluter_original_imp_matches:
        if imp_match[0].strip() == "static" and imp_match[1] != '':
            imp_stat = "import static " + imp_match[1] + ";"
            original_imports.append(imp_stat)
        elif imp_match[0].strip() == "" and imp_match[1] != '':
            imp_stat = "import " + imp_match[1] + ";"
            original_imports.append(imp_stat)

    imp_matches = import_pattern.findall(response)
    for imp_match in imp_matches:
        if imp_match[0].strip() == "static" and imp_match[1] != '':
            imp_stat = "import static " + imp_match[1] + ";"
            short_name = "." + imp_stat.split(".")[-1]
            if imp_stat not in original_imports and short_name not in str(original_imports) \
            and imp_stat not in patch["import"]:
                print("Will add {}".format(imp_stat))
                patch["import"].append(imp_stat)
            else:
                print("Will not add {}".format(imp_stat))
                if short_name in str(original_imports) and imp_stat not in str(original_imports):
                    print("Conflict_Import {}".format(short_name))
                    ifstitched = True
        elif imp_match[0].strip() == "" and imp_match[1] != '':
            imp_stat = "import " + imp_match[1] + ";"
            short_name = "." + imp_stat.split(".")[-1]
            if imp_stat not in original_imports and short_name not in str(original_imports) \
            and imp_stat not in patch["import"]:
                print("Will add {}".format(imp_stat))
                patch["import"].append(imp_stat)
            else:
                print("Will not add {}".format(imp_stat))
                if short_name in str(original_imports) and imp_stat not in str(original_imports):
                    print("Conflict_Import {}".format(short_name))
                    ifstitched = True

    java_methods,if_parsed = utils.extract_java_code(response)
    victim_patch_method = {}
    polluter_patch_method = {}
    if if_parsed == True:
        if len(java_methods) == 1:
            for method in java_methods:
                start_position = method[0]
                method_name = method[2]
                method_code = method[3]
                if method_name == victim_test_method_name:
                    patch["victim_test_code"] = (method_code)
                if method_name == polluter_test_method_name:
                    patch["polluter_test_code"] = (method_code)
        elif len(java_methods) > 1:
            for method in java_methods:
                start_position = method[0]
                method_name = method[2]
                method_code = method[3]
                if method_name == victim_test_method_name:
                    if start_position not in victim_patch_method:
                        victim_patch_method[start_position] = (method_code)
                        print("matching:",start_position, method_code)
                if method_name == polluter_test_method_name:
                    if start_position not in polluter_patch_method:
                        polluter_patch_method[start_position] = (method_code)
                        print("matching:",start_position, method_code)
            if len(victim_patch_method):
                max_start = max(victim_patch_method.keys())
                patch["victim_test_code"] = victim_patch_method[max_start]
                print("victim_test_code:",max_start, patch["victim_test_code"])
            if len(polluter_patch_method):
                max_start = max(polluter_patch_method.keys())
                patch["polluter_test_code"] = polluter_patch_method[max_start]
                print("polluter_test_code:",max_start, patch["polluter_test_code"])

    return patch,ifstitched

def parse_patch_gpt(response, victim_test_method_name, polluter_test_method_name, \
        victim_class_content, polluter_class_content, victim_test_method_content, polluter_test_method_content):
    ifstitched = False
    patch = {
        "victim_test_code": victim_test_method_content,
        "polluter_test_code": polluter_test_method_content,
        "import": [],
        "pom": None
    }
    if "<!-- <pom.xml start> -->" in response and "<!-- <pom.xml end> -->" in response:
        pom_stat = (response.split("<!-- <pom.xml start> -->")[1]).split("<!-- <pom.xml end> -->")[0]
        patch["pom"] = pom_stat
    elif "<pom.xml start>" in response and "<!-- <pom.xml end>" in response:
        pom_stat = (response.split("<pom.xml start>")[1]).split("<!-- <pom.xml end>")[0]
        patch["pom"] = pom_stat

    import_pattern = re.compile(r"import\s+(static\s+)?([\w\.]+(\.\*)?);", re.MULTILINE)

    victim_original_imp_matches = import_pattern.findall(victim_class_content)
    polluter_original_imp_matches = import_pattern.findall(polluter_class_content)

    original_imports = []

    for imp_match in victim_original_imp_matches:
        if imp_match[0].strip() == "static" and imp_match[1] != '':
            imp_stat = "import static " + imp_match[1] + ";"
            original_imports.append(imp_stat)
        elif imp_match[0].strip() == "" and imp_match[1] != '':
            imp_stat = "import " + imp_match[1] + ";"
            original_imports.append(imp_stat)

    for imp_match in polluter_original_imp_matches:
        if imp_match[0].strip() == "static" and imp_match[1] != '':
            imp_stat = "import static " + imp_match[1] + ";"
            original_imports.append(imp_stat)
        elif imp_match[0].strip() == "" and imp_match[1] != '':
            imp_stat = "import " + imp_match[1] + ";"
            original_imports.append(imp_stat)

    imp_matches = import_pattern.findall(response)
    for imp_match in imp_matches:
        if imp_match[0].strip() == "static" and imp_match[1] != '':
            imp_stat = "import static " + imp_match[1] + ";"
            short_name = "." + imp_stat.split(".")[-1]
            if imp_stat not in original_imports and short_name not in str(original_imports) \
            and imp_stat not in patch["import"]:
                print("Will add {}".format(imp_stat))
                patch["import"].append(imp_stat)
            else:
                print("Will not add {}".format(imp_stat))
                if short_name in str(original_imports) and imp_stat not in str(original_imports):
                    print("Conflict_Import {}".format(short_name))
                    ifstitched = True
        elif imp_match[0].strip() == "" and imp_match[1] != '':
            imp_stat = "import " + imp_match[1] + ";"
            short_name = "." + imp_stat.split(".")[-1]
            if imp_stat not in original_imports and short_name not in str(original_imports) \
            and imp_stat not in patch["import"]:
                print("Will add {}".format(imp_stat))
                patch["import"].append(imp_stat)
            else:
                print("Will not add {}".format(imp_stat))
                if short_name in str(original_imports) and imp_stat not in str(original_imports):
                    print("Conflict_Import {}".format(short_name))
                    ifstitched = True

    java_methods,if_parsed = utils.extract_java_code(response)
    if if_parsed == True:
        for method in java_methods:
            method_name = method[2]
            method_code = method[3]
            if method_name == victim_test_method_name:
                patch["victim_test_code"] = (method_code)
            if method_name == polluter_test_method_name:
                patch["polluter_test_code"] = (method_code)
    return patch,ifstitched