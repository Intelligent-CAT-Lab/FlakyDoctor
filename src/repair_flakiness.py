import csv
import datetime
import json
import os
import openai
import signal
import subprocess
import sys
import re
import time
import torch
import update_pom
import utils
from bs4 import BeautifulSoup
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from pathlib import Path

os.environ["CUDA_VISIBLE_DEVICES"] = "0,1,2"
device = "cuda"
run_nondex_cmds = "src/cmds/run_nondex.sh"
java_standard_libs = json.load(open("src/utils/java_standard_libs.json"))
model_load_path = {
    "MagicCoder": os.getenv("MagiCoder_LOAD_PATH"),
}

test_file_info_heads = ["project", "project_name", "sha", "module", "test_type", 
    "test", "method_name", "status", "PR_link", "notes", 
    "file_path", "patch_file", "test_results", "if_flaky", "Exceptions", "time"]

result_csv_heads = ["project", "sha", "module", "test_type", "test", 
    "method_name", "status", "PR_link", "notes", "file_path", 
    "patch_file", "test_results", "jdk", "build_results", "Exceptions", 
    "all_round_logs", "time", "if_flaky"]

def handler(signum, frame):
    raise ValueError("TimesUpError")

def initialize_test_info(project, project_name, sha, module, test_type, test, status, pr, notes, project_dir, test_class):
    return  {"project":project, "project_name":project_name, "sha":sha, "module":module, 
            "test_type":test_type,"test": test, "method_name": test.split(".")[-1],
            "status": status, "PR_link":pr, "notes":notes, "project_dir": project_dir,
            "test_class": test_class, "relative_file_path": None, "time": None,
            "file_path":None, "test_class_content":{}, "patch_file":None, "all_round_logs": None,
            "test_method_content": None, "imports": None, "jdk": None, "Exceptions": {}, "if_flaky": None,
            "prompts": {}, "responses": {}, "pom": None,
            "patches_before_stitching": {}, "patches_after_stitching": {},
            "test_results":{}, "test_logs":{},
            "err_msg":{}, "err_code":{}, "build_results": {}
        }

def main(pr_csv, projects_dir, test_file_info, model, nondex_times,result_csv,result_json,save_dir):
    if model == "MagicCoder":
        print("Loading model...")
        loading_model = AutoModelForCausalLM.from_pretrained(model_load_path[model], device_map="auto", cache_dir='./huggingface')
        tokenizer = AutoTokenizer.from_pretrained(model_load_path[model], cache_dir='./huggingface')
    elif model == "GPT-4":
        loading_model = "GPT-4"
        tokenizer = None

    test_info_csv = test_file_info.replace("json", "csv")
    utils.write_header_csv(test_info_csv,test_file_info_heads)
    utils.write_header_csv(result_csv,result_csv_heads)
    
    test_info = {}
    idx = 0
    with open(pr_csv, mode ='r')as file:
        csvFile = csv.reader(file)
        for line in csvFile:
            if "Project URL" in line or "project_url" in line or "project" in line:
                continue
            project, sha, module, test, test_type, status, pr, notes = line[0], line[1], line[2], line[3], line[4], line[5], line[6], line[7]
            project_name = project.split("/")[-1]
            tag = "{}#{}#{}#{}".format(project, sha, module, test)
            test_class = ".".join(test.split(".")[:-1])
            test_class_short_name = test.split(".")[-2]
            
            project_dir = os.path.join(projects_dir, sha, project_name)
            utils.git_stash(project_dir)
            
            file_path_found = False

            if tag not in test_info:
                info = initialize_test_info(project, project_name, sha, module, test_type, test, status, pr, notes, project_dir, test_class)
                test_done = False
                for root, dirs, files in os.walk(project_dir):
                    for file in files:
                        if not file.endswith(test_class_short_name + ".java"):
                            continue
                        file_path = os.path.join(root, file)
                        test_path = "/".join(test.split(".")[:-1])
                        if test_path in file_path and module in file_path \
                            and "/test-classes/" not in file_path and "/test/" in file_path:
                            file_path_found = True
                            relative_file_path = file_path.split(project_dir + "/")[-1]
                            utils.git_checkout_file(project_dir,relative_file_path)
                            test_class_content = utils.read_file(file_path)
                            info["relative_file_path"] = relative_file_path
                            info["file_path"] = file_path
                            info["test_class_content"][0] = test_class_content
                            info["imports"] = utils.get_imports(test_class_content)
                            info["test_method_content"] = utils.get_test_method(info["method_name"],test_class_content)
                            if "/src/" in file_path:
                                root_path = file_path.split("/src/")[0]
                                pom_path = os.path.join(root_path,"pom.xml")
                                if os.path.exists(pom_path):
                                    info["pom"] = pom_path
                            jdk = "8"
                            nondex_output = run_test_with_nondex(project_dir,module, test, jdk, nondex_times)
                            build_result = analyze_nondex_build_result(nondex_output)
                            test_result = analyze_nondex_test_result(nondex_output)
                            if test_result == "test_failure":
                                idx += 1
                                info["jdk"] = jdk
                                info["test_logs"][0] = nondex_output
                                info["test_results"][0] = test_result
                                info["build_results"][0] = build_result
                                err_msg_list, err_code_list = parse_err_msg(nondex_output, test, test_class, test_class_content)
                                info["err_msg"][0] = err_msg_list
                                info["err_code"][0] = err_code_list
                                info["if_flaky"] = "True"
                                test_info[tag] = info
                                try:
                                    result_dict = repair_ID_tests(info, model, nondex_times,result_csv,result_json,save_dir, idx, loading_model, tokenizer)
                                except Exception as e:
                                    info["Exceptions"] = str(e)
                                test_done = True
                            elif test_result == "test_pass":
                                info["jdk"] = jdk
                                info["test_logs"][0] = nondex_output
                                info["test_results"][0] = test_result
                                info["build_results"][0] = build_result
                                info["if_flaky"] = "False"
                            elif test_result == "build_failure" or test_result == "compilation_error":
                                jdk = "11"
                                nondex_output = run_test_with_nondex(project_dir,module, test, jdk, "3")
                                build_result = analyze_nondex_build_result(nondex_output)
                                test_result = analyze_nondex_test_result(nondex_output)
                                if test_result == "test_failure":
                                    idx += 1
                                    test_result = analyze_nondex_test_result(nondex_output)
                                    info["jdk"] = jdk
                                    info["test_logs"][0] = nondex_output
                                    info["test_results"][0] = test_result
                                    info["build_results"][0] = build_result
                                    err_msg_list, err_code_list = parse_err_msg(nondex_output, test, test_class, test_class_content)
                                    info["err_msg"][0] = err_msg_list
                                    info["err_code"][0] = err_code_list
                                    info["if_flaky"] = "True"
                                    test_info[tag] = info
                                    try:
                                        result_dict = repair_ID_tests(info, model, nondex_times,result_csv,result_json,save_dir, idx, loading_model, tokenizer)
                                    except Exception as e:
                                        info["Exceptions"] = str(e)
                                    test_done = True
                                else:
                                    info["jdk"] = jdk
                                    info["test_logs"][0] = nondex_output
                                    info["test_results"][0] = test_result
                                    info["build_results"][0] = build_result
                                    info["if_flaky"] = "False"
                        if test_done:
                            break
                    if test_done:
                        break

                if not file_path_found:  
                    info["Exceptions"][0] = "method_code_location_failure"
                
                res = {}
                for key in test_file_info_heads:
                    res[key] = info[key]
                utils.write_dict_csv(test_info_csv, test_file_info_heads, res)
                utils.write_json_attach(test_file_info,info)
    return test_info

def run_test_with_nondex(project_dir, module, test_fullname, jdk, nondex_times):
    test = utils.replace_last_symbol(test_fullname, ".", "#")
    result = subprocess.run(["bash",run_nondex_cmds,project_dir,module,test,jdk,nondex_times], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output = result.stdout.decode('utf-8')
    print(output)
    return output

def analyze_nondex_build_result(output):
    output_list = output.split("\n")
    result = "BUILD FAILURE"
    for line in output_list:
        if "BUILD FAILURE" in line:
            result = "BUILD FAILURE"
        elif "BUILD SUCCESS" in line:
            result = "BUILD SUCCESS"
    
    return result

def analyze_nondex_test_result(output):
    all_test_results = []
    output_list = output.split("\n")
    for line in output_list:
        if "Tests run: 1, Failures: 0, Errors: 0, Skipped: 0" in line:
            all_test_results.append("test_pass")
        elif "Tests run: 1, Failures: 1, Errors: 0, Skipped: 0" in line:
            all_test_results.append("test_failure")
        elif "Tests run: 1, Failures: 0, Errors: 1, Skipped: 0" in line:
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

def parse_compilation_err(output, test_class, test_class_content):
    class_file = test_class.split(".")[-1] + ".java"
    err_msgs = []
    err_code_list = []
    lineno_list = []
    for output_line in output.split("\n"):
        lineno = None
        if class_file in output_line:
            lineno_str = str(output_line).split(class_file + ":")[-1].split(")")[0]
            try:
                lineno = int(lineno_str)
            except:
                pass
        if class_file in output_line and "[" in output_line and "]" in output_line:
            lineno_str = str(output_line).split(class_file + ":")[-1].split("[")[-1].split(",")[0].split("]")[0]
            try:
                lineno = int(lineno_str)
            except:
                pass
        if lineno != None and lineno not in lineno_list:
            lineno_list.append(lineno)
    for number in lineno_list:
        err_code = test_class_content.split("\n")[int(number)-1]
        if err_code.strip() not in err_code_list:
            err_code_list.append(err_code.strip())
        
    seq = output.split("[INFO] Finished at:")[-1].split("To see the full stack trace of the errors")[0].replace("-> [Help 1]", "")
    for line in seq.split("\n"):
        if "Failed to execute goal" in line:
            continue
        if not line.startswith("[ERROR]"):
            continue
        tmp_line = line.replace("[ERROR]","").strip()
        if class_file in tmp_line:
            msg = tmp_line.split("]")[-1]
            if msg not in err_msgs:
                err_msgs.append(msg)
        else:
            if tmp_line not in err_msgs:
                err_msgs.append(tmp_line)
    return err_msgs, err_code_list

def parse_err_msg(output, test, test_class, test_class_content):
    test_method_name = test.split(".")[-1]
    err_msg_list = [] # error message from log
    err_code_list = [] # which test code causes the error
    lineno_list = []
    class_file = test_class.split(".")[-1] + ".java"
    if "COMPILATION ERROR" in output:
        err_msg_list, err_code_list = parse_compilation_err(output, test_class, test_class_content)
        return err_msg_list, err_code_list

    for output_line in output.split("\n"):
        lineno = None
        if class_file in output_line:
            lineno_str = str(output_line).split(class_file + ":")[-1].split(")")[0]
            try:
                lineno = int(lineno_str)
            except:
                pass
        if class_file in output_line and "[" in output_line and "]" in output_line:
            lineno_str = str(output_line).split(class_file + ":")[-1].split("[")[-1].split(",")[0].split("]")[0]
            try:
                lineno = int(lineno_str)
            except:
                pass
        if lineno != None and lineno not in lineno_list:
            lineno_list.append(lineno)

    for number in lineno_list:
        err_code = test_class_content.split("\n")[int(number)-1]
        if err_code.strip() not in err_code_list:
            err_code_list.append(err_code.strip())

    for line in output.split("\n"):
        if "Please refer to" in line and "for the individual test results" in line:
            xml_dir = line.split("Please refer to")[-1].split("for")[0].strip()
            for root, dirs, files in os.walk(xml_dir):
                for file in files:
                    if file.endswith(".xml") and "TEST-" + test_class in file:
                        xml_path = os.path.join(root, file)
                        with open(xml_path, 'r') as f:
                            data = f.read()
                        bs_data = BeautifulSoup(data, 'xml')
                        for tag in bs_data.find_all('testcase', {'classname':test_class}, {'name':test_method_name}):
                            err_element = tag.find('error')
                            if err_element:
                                err_msg = err_element.get('message')
                                err_type = err_element.get('type')
                                if err_msg == None:
                                    err_msg = err_type
                                final_err_msg = ' '.join(err_msg.split())
                                if final_err_msg not in err_msg_list:
                                    err_msg_list.append(final_err_msg.strip())
                                
                            failure_element = tag.find('failure')
                            if failure_element:
                                failure_msg = failure_element.get('message')
                                failure_type = failure_element.get('type')
                                if failure_msg == None:
                                    failure_msg = failure_type
                                final_failure_msg = ' '.join(failure_msg.split())
                                if final_failure_msg not in err_msg_list:
                                    err_msg_list.append(final_failure_msg.strip())
                            
    return err_msg_list, err_code_list

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
        " HashMap":[], " HashSet":[], "Gson()":[],
        ".getKet()":[],
    }
    if test_content != None:
        lines = test_content.split("\n")
        for api in potential_apis:
            for line in lines:
                if api in line:
                    potential_apis[api].append(line)
    return potential_apis

def generate_prompts(model, test_method_name, test_type, test_method_content, err_msg_list, err_code_list,potential_apis, round, loading_model, tokenizer):
    print("Generating prompt...")

    potential_code = []
    for api in potential_apis:
        potential_code.extend(potential_apis[api])
    err_code = " ".join(err_code_list)
    p_code = " ".join(potential_code)
    response = None

    ID_description = """ID flaky tests are caused by using some APIs which assume the order of elements are guaranteed,
        such as HashSet, HashMap, toString, containsExactly, getDeclaredFields, getKey, etc. You should change such APIs which do not guarantee orders.
        A common fix is to use APIs which can make sure the elements are in deterministic order,such as LinkedHashSet, LinkedHashMap, JsonParser, containsOnly, containsExactlyInAnyOrder, assertThatJson, etc.;
        But if you didn't find above similar cases, you should fix by other ways, to make sure the test will always pass.
    """
    err_msg = " ".join(err_msg_list)
    if model == "GPT-4":
        if round == 1:
            prefix = """You are a software testing expert. 
            I want you to fix a flaky test. {} is a flaky test of type {}, located in the following java class {}.
            """.format(test_method_name, test_type, test_method_content)
        else:
            prefix = """You are a software testing expert. 
            To fix the original flaky test {}, the following code is from your previous answer {}.
            """.format(test_method_name, test_method_content)

        gpt_prompt = prefix + """I got the following error when running NonDex on it: {}. 
            Lines {} cause the flakiness. Lines {} may cause potential flakiness. {}.
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
        """.format(err_msg, err_code, p_code, ID_description)

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
        I want you to fix a flaky test. {} is a flaky test of type {}, located in the following java class {}. {} 
        I got the following error when running NonDex on it: {}. 
        Lines {} cause the flakiness. Lines {} may cause potential flakiness.
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
        """.format(test_method_name, test_type, test_method_content, ID_description, err_msg, err_code, p_code)
        print(magiccoder_prompt)

        model_inputs = tokenizer([magiccoder_prompt], return_tensors="pt").to(device)
        generated_ids = loading_model.generate(**model_inputs, max_new_tokens=2048 , temperature=0.2, do_sample=True)
        generated_text = tokenizer.batch_decode(generated_ids)[0]
        print(generated_text)
        return generated_text, magiccoder_prompt

def huggingface_generator(model, prompt, max_new_tokens):
        device = "cuda:0"
        hf_model, hf_tokenizer = model, tokenizer
        model_inputs = hf_tokenizer([prompt], return_tensors="pt").to(device)
        generated_ids = hf_model.generate(**model_inputs, max_new_tokens=max_new_tokens)
        generated_text = hf_tokenizer.batch_decode(generated_ids)[0]
        return generated_text

def repair_ID_tests(test_info, model, nondex_times,result_csv,result_json,save_dir, idx, loading_model, tokenizer):
    """
    1. Run test before repairing to confirm flakiness; return result_0 + error trace/location to generate the prompt;
    2. Prompt the model, generate patch, apply patch, run test, get new result + error trace/location

    """
    result_csv_heads = ["project", "sha", "module", 
                        "test_type","test", "method_name",
                        "status", "PR_link", "notes", 
                        "file_path", "patch_file", "test_results", "jdk",
                        "build_results", "Exceptions", "all_round_logs", "time", "if_flaky"]
    print("Index {} {} is working on {}".format(idx, model, test_info["test"]))
    if test_info:
        project = test_info["project"]
        sha = test_info["sha"]
        project_dir = test_info["project_dir"]
        module = test_info["module"]
        test = test_info["test"]
        test_type = test_info["test_type"]
        test_method_name = test_info["method_name"]
        test_method_content = test_info["test_method_content"]
        imports = test_info["imports"]
        jdk = test_info["jdk"]
        file_path = test_info["file_path"]
        relative_file_path = test_info["relative_file_path"]
        err_msg = test_info["err_msg"][0]
        err_code = test_info["err_code"][0]
        test_class_content = test_info["test_class_content"][0]
        original_test_class_content = test_class_content
        test_class = test_info["test_class"]
        result_dict = {}
        utils.git_stash(project_dir)
        if test_method_content == None:
            test_info["Exceptions"][0] = "method_code_location_failure"
            test_info["if_flaky"] = "False"
            for key in result_csv_heads:
                result_dict[key] = test_info[key]
            utils.write_dict_csv(result_csv, result_csv_heads,result_dict)
            utils.write_json_attach(result_json, result_dict)
            utils.git_checkout_file(project_dir,relative_file_path)
            return result_dict
        
        print(err_msg)
        print(err_code)
        fixed = False

        t0 = time.perf_counter()

        round = 1
        while round <= 5:
            potential_apis = get_potential_API(test_method_content)
            print("Index {}: ROUND {} to Repair Test {}".format(idx, round, test))
            now = datetime.datetime.now()
            print("Starting prompt", now)
            if model == "GPT-4":
                try:
                    response, prompt = "", ""
                    response, prompt = generate_prompts(model, test_method_name, test_type, test_method_content, err_msg, err_code, potential_apis,round, loading_model, tokenizer)
                    patch,ifstitched = parse_patch_gpt(response, test_method_name, test_class_content)
                except Exception as e:
                    test_info["prompts"][round] = prompt
                    test_info["responses"][round] = response
                    test_info["Exceptions"][round] = str(e)
                    break
            
            if model == "MagicCoder":
                signal.signal(signal.SIGALRM, handler)
                signal.alarm(300)
                try:
                    response, prompt = "", ""
                    response, prompt = generate_prompts(model, test_method_name, test_type, test_method_content, err_msg, err_code, potential_apis,round,loading_model, tokenizer)
                    patch,ifstitched = parse_patch_magiccoder(response, test_method_name, test_class_content)
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
            print(patch["test_code"])
            
            update_class_content = apply_patch(file_path, test_class_content, test_method_name, patch, project, sha, project_dir)
            test_info["test_class_content"][round] = update_class_content
            nondex_output = run_test_with_nondex(project_dir,module, test, jdk, nondex_times)
            build_result = analyze_nondex_build_result(nondex_output)
            test_result = analyze_nondex_test_result(nondex_output)
            err_msg_list, err_code_list = parse_err_msg(nondex_output, test, test_class, update_class_content)
            test_info["build_results"][round] = build_result
            if ifstitched:
                test_info["test_results"][round] = "Stitched:" + test_result
            else:
                test_info["test_results"][round] = test_result
            test_info["err_msg"][round] = err_msg_list
            test_info["err_code"][round] = err_code_list
            
            print(err_msg_list)
            print(err_code_list)
            print(test_result)
            if test_result == "build_failure" or test_result == "pom_error":
                if test_info["pom"] != None:
                    project_name = project.split("/")[-1]
                    pom_path = test_info["pom"].split(project_name + "/")[-1]
                    print("/home/flaky/" + project_dir, pom_path)
                    utils.git_checkout_file( "/home/flaky/" + project_dir,pom_path)

            
            test_method_content = patch["test_code"]
            err_msg = err_msg_list
            err_code = err_code_list
            test_class_content = update_class_content

            if test_result == "test_pass":
                fixed = True
                print(test, "test_pass")
                patch_file = write_patch(save_dir, project, sha, module, test, patch, test_info["test_method_content"], file_path, round)
                test_info["patch_file"] = patch_file
                patch_log = dump_all_rounds_patch(test_info, test, file_path, save_dir, project, sha, module, test_info["test_method_content"], round)
                test_info["all_round_logs"] = patch_log
                break

            if build_result == "BUILD FAILURE":
                after_patch, if_stitch = stitching_consistency(original_test_class_content, test_class_content, patch, err_code, err_msg, test, test_method_name)
                if if_stitch == True:
                    print("Index {}: ROUND {} to Repair Test {} STITCHING".format(idx, round, test))
                    test_info["patches_after_stitching"][round] = after_patch
                    update_class_content = apply_patch_stitch(file_path, test_class_content, test_method_name, after_patch, patch, project, sha, project_dir)
                    test_info["test_class_content"][round] = update_class_content

                    nondex_output = run_test_with_nondex(project_dir,module, test, jdk, nondex_times)
                    build_result = analyze_nondex_build_result(nondex_output)
                    test_result = analyze_nondex_test_result(nondex_output)
                    err_msg_list, err_code_list = parse_err_msg(nondex_output, test, test_class, update_class_content)
                    test_info["build_results"][round] += ";Stitched:" + build_result
                    test_info["test_results"][round] += ";Stitched:" + test_result
                    test_info["err_msg"][round] += ";Stitched:" + str(err_msg_list)
                    test_info["err_code"][round] += ";Stitched:" + str(err_code_list)

                    if test_result == "test_pass":
                        print(test, "test_pass")
                        fixed = True
                        patch_file = write_patch_stitch(save_dir, project, sha, module, test, after_patch, patch, test_info["test_method_content"], file_path, round)
                        test_info["patch_file"] = patch_file
                        patch_log = dump_all_rounds_patch(test_info, test, file_path, save_dir, project, sha, module, test_info["test_method_content"], round)
                        test_info["all_round_logs"] = patch_log
                        break
                if build_result == "BUILD FAILURE":
                    #patch, update_err_msg, final_class_content
                    last_patch = after_patch
                    after_patch, err_msg_list, update_class_content, if_import_stitched = stitching_symbols_imports(update_class_content, last_patch, err_code_list, \
                        err_msg_list, test, test_method_name, file_path,project,sha, module, project_dir, jdk, nondex_times, test_class)
                    if if_import_stitched:
                        test_info["patches_after_stitching"][round] = after_patch
                        test_info["test_class_content"][round] = update_class_content

                        nondex_output = run_test_with_nondex(project_dir,module, test, jdk, nondex_times)

                        build_result = analyze_nondex_build_result(nondex_output)
                        test_result = analyze_nondex_test_result(nondex_output)
                        err_msg_list, err_code_list = parse_err_msg(nondex_output, test, test_class, update_class_content)
                        test_info["build_results"][round] += ";Stitched:" + build_result
                        test_info["test_results"][round] += ";Stitched:" + test_result
                        test_info["err_msg"][round] += ";Stitched:" + str(err_msg_list)
                        test_info["err_code"][round] += ";Stitched:" + str(err_code_list)
                        if test_result == "test_pass":
                            print(test, "test_pass")
                            fixed = True
                            patch_file = write_patch_stitch(save_dir, project, sha, module, test, after_patch, patch, test_info["test_method_content"], file_path, round)
                            test_info["patch_file"] = patch_file
                            patch_log = dump_all_rounds_patch(test_info, test, file_path, save_dir, project, sha, module, test_info["test_method_content"], round)
                            test_info["all_round_logs"] = patch_log
                            break

                test_method_content = after_patch["test_code"]
                err_msg = err_msg_list
                err_code = err_code_list
                test_class_content = update_class_content
                
            round += 1

        if fixed == False:
            patch_log = dump_all_rounds_patch(test_info, test, file_path, save_dir, project, sha, module, test_info["test_method_content"], round-1)
            test_info["all_round_logs"] = patch_log
        t1 = time.perf_counter()
        print("Total generation time:", t1 - t0)
        test_info["time"] = t1 - t0
        for key in result_csv_heads:
            result_dict[key] = test_info[key]
        utils.write_dict_csv(result_csv, result_csv_heads,result_dict)
        utils.write_json_attach(result_json, result_dict)
        utils.git_checkout_file(project_dir,relative_file_path)
    return result_dict
        
        
def stitching_consistency(original_test_class_content,test_class_content_before_stitching, patch, err_code, err_msg, test, test_method_name):
    print("Stitching...")

    after_patch = {
        "test_code": patch["test_code"], "import": patch["import"], "pom": patch["pom"],
    }
    if_stitch = False

    original_method, original_node, original_modifiers, original_name, original_parameters, original_return_type, original_throws  \
        = utils.extract_method(test_method_name, original_test_class_content)

    test_code_before_stitching, before_node, before_modifiers, before_name, before_parameters, before_return_type, before_throws  \
        = utils.extract_method(test_method_name, test_class_content_before_stitching)
    
    test_code_after_stitching = None
    
    original_declaration = original_method.split("{")[0].strip()
    before_declaration = test_code_before_stitching.split("{")[0].strip()

    if [original_modifiers, original_name, original_parameters, original_return_type, original_throws] != \
        [before_modifiers, before_name, before_parameters, before_return_type, before_throws]:
        test_code_after_stitching = test_code_before_stitching.replace(before_declaration, original_declaration)

    if test_code_after_stitching != None:
        if_stitch = True
        print([original_modifiers, original_name, original_parameters, original_return_type, original_throws], \
        [before_modifiers, before_name, before_parameters, before_return_type, before_throws])
        after_patch["test_code"] = test_code_after_stitching

    return after_patch, if_stitch

def stitching_symbols_imports(test_class_content_before_stitching, patch, err_code, err_msg, test, test_method_name, file_path,project,sha, module, project_dir, jdk, nondex_times, test_class):
    # Try to add imports:
    print("Stitching missing symbols...")
    symbols = {}
    solved_err = []
    import_update = False
    final_class_content = test_class_content_before_stitching

    if "cannot find symbol" in str(err_msg):
        for msg in err_msg:
            if "symbol:   class" in msg:
                tofix_symbol = msg.split("class")[-1].replace(" ","").strip()
                if tofix_symbol not in symbols:
                    symbols[tofix_symbol] = []
                    if tofix_symbol not in java_standard_libs:
                        continue
                    print(java_standard_libs[tofix_symbol])
                    for potential_lib in java_standard_libs[tofix_symbol]:
                        update_class_content = apply_import(file_path, test_class_content_before_stitching, test_method_name, potential_lib, project, sha, project_dir)
                        nondex_output = run_test_with_nondex(project_dir,module, test, jdk, nondex_times)
                        build_result = analyze_nondex_build_result(nondex_output)
                        test_result = analyze_nondex_test_result(nondex_output)
                        err_msg_list, err_code_list = parse_err_msg(nondex_output, test, test_class, update_class_content)
                        if tofix_symbol not in str(err_msg_list):
                            import_update = True
                            symbols[tofix_symbol].append(potential_lib)
                            solved_err.append(msg)
                            test_class_content_before_stitching = update_class_content
                            final_class_content = update_class_content
                            break

    update_err_msg = [msg for msg in err_msg if msg not in solved_err]
    for symbol in symbols:
        if len(symbols[symbol]):
            patch["import"].extend(symbols[symbol])

    return patch, update_err_msg, final_class_content, import_update

def dump_all_rounds_patch(info, test, file_path, patch_dir,project_url, sha, module, original_test_method, round):
    project = project_url.split("/")[-1]
    patch_dir = os.path.join(save_dir,"all_rounds", project,sha,module,test)
    Path(patch_dir).mkdir(parents=True, exist_ok=True)
    patch_file = os.path.join(patch_dir,str(round) + ".patch")

    content = """Test File Path: {}\n
    Original Test Method:\n {}
    """.format(file_path, original_test_method)

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
            import:\n
            {}\n
            pom:\n
            {}\n
            """.format(r, info["patches_before_stitching"][r]["test_code"], \
            info["patches_before_stitching"][r]["import"], info["patches_before_stitching"][r]["pom"])
        if r in info["patches_after_stitching"]:
            patch_content += """\n
            After stitching: \n
            test_code:\n
            {}\n
            import:\n
            {}\n
            pom:\n
            {}\n
            """.format(info["patches_after_stitching"][r]["test_code"], \
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

def write_patch(save_dir, project_url, sha, module, test, patch, original_test_method, file_path, round):
    project = project_url.split("/")[-1]
    patch_dir = os.path.join(save_dir,project,sha,module,test)
    Path(patch_dir).mkdir(parents=True, exist_ok=True)
    patch_file = os.path.join(patch_dir,str(round) + ".patch")

    file = open(patch_file, 'w')
    content = """Test File Path: {}\n
    Original Test Method:\n {}
    """.format(file_path, original_test_method)

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

def apply_patch(file_path, original_test_class_content, test_method_name, patch, project, sha, project_dir):
    fixed_class = original_test_class_content
    old_test_method_code = ""
    old_test_method = utils.get_test_method(test_method_name, original_test_class_content) #res = [start,end,method_name,method_code,node.annotations]
    if old_test_method != None:
        old_test_method_code = old_test_method
    if patch["test_code"] != None:
        fixed_class = original_test_class_content.replace(old_test_method_code, "\n" + patch["test_code"] + "\n")
        print("Code Replaced.")
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
    
    f = open(file_path, "w", errors='ignore')
    f.write(final_class)
    f.close()

    if patch["pom"] != None:
        dep2add = patch["pom"]
        deps = dep2add
        if "<dependencies>" in patch["pom"]:
            dep2add  = patch["pom"].replace("<dependencies>","")
        if "</dependencies>" in dep2add:
            deps = dep2add.replace("</dependencies>","")
        if "/src/" in file_path:
            root_path = file_path.split("/src/")[0]
            pom_path = os.path.join(root_path,"pom.xml")
            if os.path.exists(pom_path):
                # utils.git_checkout_file(project_dir,pom_path)
                update_pom.add_dependency(pom_path,deps)
                print("POM Updated.")

    return final_class

def parse_patch_codellama(full_response, test_method_name, test_class_content):
    ifstitched = False
    response = full_response.split("[/INST]")[-1]
    patch = {
        "test_code": None,
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
    
    original_imp_matches = import_pattern.findall(test_class_content)
    original_imports = []
    for imp_match in original_imp_matches:
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
    patch_method = {}
    if if_parsed == True:
        if len(java_methods) == 1:
            for method in java_methods:
                start_position = method[0]
                method_name = method[2]
                method_code = method[3]
                if method_name == test_method_name:
                    patch["test_code"] = (method_code)
        elif len(java_methods) > 1:
            for method in java_methods:
                start_position = method[0]
                method_name = method[2]
                method_code = method[3]
                if method_name == test_method_name:
                    if start_position not in patch_method:
                        patch_method[start_position] = (method_code)
                        print("matching:",start_position, method_code)
            if len(patch_method):
                max_start = max(patch_method.keys())
                patch["test_code"] = patch_method[max_start]
                print("test_code:",max_start, patch["test_code"])
    if patch["test_code"] == None:
        if "//<fix end>" in response and "//<fix start>" in response:
            content = response.split("//<fix end>")[0].split("//<fix start>")[1]
            java_methods = utils.parse_java_func_intervals(content)
            for method in java_methods:
                start_position = method[0]
                method_name = method[2]
                method_code = method[3]
                if method_name == test_method_name:
                    patch["test_code"] = method_code
                    break
            if patch["test_code"] == None:
                patch["test_code"] = content  

    return patch,ifstitched

def parse_patch_deepseekcoder(full_response, test_method_name, test_class_content):
    ifstitched = False
    response = full_response.split("### Response:")[-1]
    patch = {
        "test_code": None,
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
    
    original_imp_matches = import_pattern.findall(test_class_content)
    original_imports = []
    for imp_match in original_imp_matches:
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
    patch_method = {}
    if if_parsed == True:
        if len(java_methods) == 1:
            for method in java_methods:
                start_position = method[0]
                method_name = method[2]
                method_code = method[3]
                if method_name == test_method_name:
                    patch["test_code"] = (method_code)
        elif len(java_methods) > 1:
            for method in java_methods:
                start_position = method[0]
                method_name = method[2]
                method_code = method[3]
                if method_name == test_method_name:
                    if start_position not in patch_method:
                        patch_method[start_position] = (method_code)
                        print("matching:",start_position, method_code)
            if len(patch_method):
                max_start = max(patch_method.keys())
                patch["test_code"] = patch_method[max_start]
                print("test_code:",max_start, patch["test_code"])
    return patch,ifstitched

def parse_patch_magiccoder(full_response, test_method_name, test_class_content):
    ifstitched = False
    response = full_response.split("@@ Response")[-1]
    patch = {
        "test_code": None,
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
    
    original_imp_matches = import_pattern.findall(test_class_content)
    original_imports = []
    for imp_match in original_imp_matches:
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
    patch_method = {}
    if if_parsed == True:
        if len(java_methods) == 1:
            for method in java_methods:
                start_position = method[0]
                method_name = method[2]
                method_code = method[3]
                if method_name == test_method_name:
                    patch["test_code"] = (method_code)
        elif len(java_methods) > 1:
            for method in java_methods:
                start_position = method[0]
                method_name = method[2]
                method_code = method[3]
                if method_name == test_method_name:
                    if start_position not in patch_method:
                        patch_method[start_position] = (method_code)
                        print("matching:",start_position, method_code)
            if len(patch_method):
                max_start = max(patch_method.keys())
                patch["test_code"] = patch_method[max_start]
                print("test_code:",max_start, patch["test_code"])
    return patch,ifstitched

def parse_patch_gpt(response, test_method_name, test_class_content):
    ifstitched = False
    patch = {
        "test_code": None,
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

    original_imp_matches = import_pattern.findall(test_class_content)
    original_imports = []
    for imp_match in original_imp_matches:
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
            if method_name == test_method_name:
                patch["test_code"] = (method_code)
    return patch,ifstitched