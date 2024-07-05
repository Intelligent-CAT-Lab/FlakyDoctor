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

java_standard_libs = json.load(open("src/utils/java_standard_libs.json"))
   
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
