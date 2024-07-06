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

def write_patch_stitch(save_dir, project_url, sha, module, test, patch, patch_before_stitching, original_test_method, file_path, round):
    project = project_url.split("/")[-1]
    patch_dir = os.path.join(save_dir, "GoodPatches", project,sha,module,test)
    Path(patch_dir).mkdir(parents=True, exist_ok=True)
    patch_file = os.path.join(patch_dir,str(round) + ".patch")

    content = """Test File Path: {}\nOriginal Test Method:\n {}""".\
        format(file_path, original_test_method)
        
    utils.write_file(patch_file, content)
    
    utils.add_file(patch_file, "\nPatch after Stitching:\n")
    for key in patch:
        utils.add_file(patch_file,"\n" + str(key) + ":\n" + str(patch[key]))

    utils.add_file(patch_file, "\nPatch before Stitching:\n")
    for key in patch_before_stitching:
        utils.add_file(patch_file, "\n" + str(key) + ":\n" + str(patch_before_stitching[key]))
    return patch_file

def write_patch(save_dir, project_url, sha, module, test, patch, original_test_method, file_path, round):
    project = project_url.split("/")[-1]
    patch_dir = os.path.join(save_dir, "GoodPatches", project,sha,module,test)
    Path(patch_dir).mkdir(parents=True, exist_ok=True)
    patch_file = os.path.join(patch_dir,str(round) + ".patch")

    content = """Test File Path: {}\nOriginal Test Method:\n {}Patch:\n""".\
        format(file_path, original_test_method)
    utils.write_file(patch_file, content)

    for key in patch:
        utils.add_file(patch_file, "\n" + str(key) + ":\n" + str(patch[key]))
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

def dump_all_rounds_patch(info, test, file_path, save_dir, project_url, sha, module, original_test_method, round):
    project = project_url.split("/")[-1]
    patch_dir = os.path.join(save_dir,"all_rounds", project,sha,module,test)
    Path(patch_dir).mkdir(parents=True, exist_ok=True)
    patch_file = os.path.join(patch_dir,str(round) + ".patch")

    content = """Test File Path: {}\nOriginal Test Method:\n {}""".\
        format(file_path, original_test_method)

    file = open(patch_file, 'w')
    file.write(content)
    file.close()

    patch_content = ""

    for r in range(1, round+1):
        if r in info["patches_before_stitching"]:
            patch_content += """ROUND {}:\n
Before stitching: \n
test_code:\n
{}\n
import:\n
{}\n
pom:\n
{}\n""".format(r, info["patches_before_stitching"][r]["test_code"], \
            info["patches_before_stitching"][r]["import"], info["patches_before_stitching"][r]["pom"])
        if r in info["patches_after_stitching"]:
            patch_content += """\n
After stitching: \n
test_code:\n
{}\n
import:\n
{}\n
pom:\n
{}\n""".format(info["patches_after_stitching"][r]["test_code"], \
            info["patches_after_stitching"][r]["import"], info["patches_after_stitching"][r]["pom"])
    
    file = open(patch_file, 'a')
    file.write(patch_content)
    file.close()

    return patch_file