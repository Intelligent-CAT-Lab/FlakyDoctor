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

run_nondex_cmds = "src/cmds/run_nondex.sh"

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

def analyze_nondex_build_result(output):
    output_list = output.split("\n")
    result = "BUILD FAILURE"
    for line in output_list:
        if "BUILD FAILURE" in line:
            result = "BUILD FAILURE"
        elif "BUILD SUCCESS" in line:
            result = "BUILD SUCCESS"
    return result

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

def run_test_with_nondex(project_dir, module, test_fullname, jdk, nondex_times):
    test = utils.replace_last_symbol(test_fullname, ".", "#")
    result = subprocess.run(["bash", run_nondex_cmds,project_dir,module,test,jdk,nondex_times], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output = result.stdout.decode('utf-8')
    print(output)
    return output