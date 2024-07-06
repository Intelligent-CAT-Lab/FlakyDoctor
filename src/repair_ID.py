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
from pathlib import Path
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from operate_patch import dump_all_rounds_patch, apply_patch, apply_patch_stitch, write_patch, write_patch_stitch
from stitching import stitching_consistency, stitching_symbols_imports
from parse_nondex import * #parse_compilation_err, parse_err_msg, parse_patch_magiccoder, parse_patch_gpt, run_test_with_nondex, analyze_nondex_build_result, analyze_nondex_test_result

os.environ["CUDA_VISIBLE_DEVICES"] = "0,1,2"
device = "cuda"

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
    
def locate_test_file(project_dir, test_class_short_name, module, test_path):
    potential_file_paths = []
    for root, dirs, files in os.walk(project_dir):
        for file in files:
            if not file.endswith(test_class_short_name + ".java"):
                continue
            file_path = os.path.join(root, file)
            if test_path in file_path and module in file_path \
                and "/test-classes/" not in file_path and "/test/" in file_path:
                    potential_file_paths.append(file_path)
    return potential_file_paths

def main(pr_csv, projects_dir, details_csv, model, nondex_times, result_csv, result_json, save_dir):
    if model == "MagicCoder" or "Magiccoder":
        model = "MagicCoder"
        print("Loading model...")
        model_load_path = {
            "MagicCoder": os.getenv("MagiCoder_LOAD_PATH"),
        }
        loading_model = AutoModelForCausalLM.from_pretrained(model_load_path[model], device_map="auto", cache_dir='./huggingface')
        tokenizer = AutoTokenizer.from_pretrained(model_load_path[model], cache_dir='./huggingface')
    elif model == "GPT-4":
        loading_model = "GPT-4"
        tokenizer = None
        
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
            test_path = "/".join(test.split(".")[:-1]) # will use later
            
            project_dir = os.path.join(projects_dir, sha, project_name)
            utils.git_stash(project_dir)

            if tag not in test_info:
                info = initialize_test_info(project, project_name, sha, module, test_type, test, status, pr, notes, project_dir, test_class)
                test_done = False
                potential_file_paths = locate_test_file(project_dir, test_class_short_name, module, test_path)
                if len(potential_file_paths) == 0:
                    info["Exceptions"][0] = "method_code_location_failure"
                    test_done = True
                else:
                    for file_path in potential_file_paths:
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
                
                res = {}
                utils.write_json_attach(details_csv,info)
    return test_info

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
But if you didn't find above similar cases, you should fix by other ways, to make sure the test will always pass."""
    err_msg = " ".join(err_msg_list)
    if model == "GPT-4":
        if round == 1:
            prefix = """You are a software testing expert. I want you to fix a flaky test. {} is a flaky test of type {}, located in the following java class {}.""".\
                format(test_method_name, test_type, test_method_content)
        else:
            prefix = """You are a software testing expert. To fix the original flaky test {}, the following code is from your previous answer {}.""".\
                format(test_method_name, test_method_content)

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
Assume required classes in the original code are setup correctly, do not include them in your code.""".\
    format(err_msg, err_code, p_code, ID_description)

        print("GPT prompt:\n{}".format(gpt_prompt))
        full_response = openai.ChatCompletion.create(
            model = "gpt-4", #"gpt-3.5-turbo",
            temperature = 0.2,
            messages = [
                {"role": "user", 
                "content":gpt_prompt}
            ]
        )
        print("GPT response:\n{}".format(full_response))
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
        print("MagiCoder prompt:{}".format(magiccoder_prompt))

        model_inputs = tokenizer([magiccoder_prompt], return_tensors="pt").to(device)
        generated_ids = loading_model.generate(**model_inputs, max_new_tokens=2048 , temperature=0.2, do_sample=True)
        generated_text = tokenizer.batch_decode(generated_ids)[0]
        print("Magicoder response:{}".format(generated_text))
        return generated_text, magiccoder_prompt

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
        
        fixed = False
        t0 = time.perf_counter()

        round = 1
        while round <= 5:
            potential_apis = get_potential_API(test_method_content)
            print("Index {}: ROUND {} to Repair Test {}".format(idx, round, test))
            now = datetime.datetime.now()
            print("Starting prompting...", now)
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

            print("Patch:\n{}".format(patch))
            
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
