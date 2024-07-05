import ast
import csv
import json
import os
import sys
import subprocess
import javalang
from typing import Set, Tuple
import sys
import re

checkout_project_cmds = "src/cmds/checkout_project.sh"
stash_project_cmds = "src/cmds/stash_project.sh"

def get_helper_methods(code):
    method_list = parse_java_func_intervals(code)
    start_lines = []
    res = {"before":{},"after":{},"earlist_line":{},"method_names":[]}
    for method_info in method_list:
        start, end, method_name, method_code, node = method_info[0:]
        start_lines.append(start.line)
        if node.annotations != None:
            for ele in node.annotations:
                if ele.name == "BeforeClass" or ele.name == "Before" or ele.name == "BeforeAll":
                    if method_name not in res["before"]:
                        method_code = get_string(code,start,end)
                        res["before"][method_name] = method_code
                        res["method_names"].append(method_name)
                elif ele.name == "AfterClass" or ele.name == "After" or ele.name == "AfterAll":
                    if method_name not in res["after"]:
                        method_code = get_string(code,start,end)
                        res["after"][method_name] = method_code
                        res["method_names"].append(method_name)
    res["earlist_line"] = min(start_lines)
    return res

def get_global_vars(code,start_line):
    fields = {}
    trees = javalang.parse.parse(code)
    for _, node in javalang.parse.parse(code):
        func_intervals = set()
        if isinstance(
            node,
            (javalang.tree.FieldDeclaration),
        ):
            stat = get_string(code,node.start_position,node.end_position),
            node_name = node.declarators[0].name,
            # func_intervals.add(
            #     (
            #         node.start_position,
            #         node.end_position,
            #         stat,
            #         node
            #     )
            # )
            if node.start_position.line >= start_line:
                continue
            if node_name not in fields:
                fields[node_name[0]] = stat[0]
    return fields

def git_checkout_file(projectDir,file_path):
    result = subprocess.run(["bash",checkout_project_cmds,projectDir,file_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output = result.stdout.decode('utf-8')
    print(output)

def git_stash(projectDir):
    result = subprocess.run(["bash",stash_project_cmds,projectDir], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output = result.stdout.decode('utf-8')
    print(output)

def get_package(code):
    try:
        trees = javalang.parse.parse(code)
        if trees.package:
            full_package = "package " + trees.package.name + ";"
            return full_package
    except:
        print("package not found")
        return None

def replace_last_symbol(source_string, replace_what, replace_with):
    head, _sep, tail = source_string.rpartition(replace_what)
    return head + replace_with + tail

def get_imports(code):
    original_code = code
    imp_list = []
    try:
        trees = javalang.parse.parse(code)
        if trees.imports:
            for import_node in trees.imports:
                import_stat = get_string(original_code,import_node.start_position,import_node.end_position)
                imp_list.append(import_stat)
    except:
        return imp_list
    return imp_list

def get_string(data, start, end):
    if start is None:
        return ""

    end_pos = None

    if end is not None:
        end_pos = end.line #- 1

    lines = data.splitlines(True)
    string = "".join(lines[start.line:end_pos])
    string = lines[start.line - 1] + string

    if end is None:
        left = string.count("{")
        right = string.count("}")
        if right - left == 1:
            p = string.rfind("}")
            string = string[:p]

    return string

def parse_java_func_intervals(content: str) -> Set[Tuple[int, int]]:
    func_intervals = set()
    try:
    # if True:
        # trees = javalang.parse.parse(content)
        # print(trees)
        for _, node in javalang.parse.parse(content):
            if isinstance(
                node,
                (javalang.tree.MethodDeclaration, javalang.tree.ConstructorDeclaration),
            ):
                func_intervals.add(
                    (
                        node.start_position,
                        node.end_position,
                        node.name,
                        get_string(content,node.start_position,node.end_position),
                        node
                    )
                )
        return func_intervals
    except Exception as e: # javalang.parser.JavaSyntaxError
        print("exp", e)
        return func_intervals

def extract_method(test_name,class_content):
    method_list = parse_java_func_intervals(class_content)
    res = None
    for method_info in method_list:
        start, end, method_name, method_code, node = method_info[0:]
        if test_name == method_name:
            # print(node.modifiers, node.name, node.parameters, node.return_type, node.throws)
            # if node.annotations != None:
            #     for ele in node.annotations:
            #         if ele.name != "Test":
            #             continue
            # res = [start,end,method_name,method_code,node.annotations]
            # print(node)
            res = [method_code,node, node.modifiers, node.name, node.parameters, node.return_type, node.throws]
    return res

def get_test_method(test_name,class_content):
    method_list = parse_java_func_intervals(class_content)
    res = None
    for method_info in method_list:
        start, end, method_name, method_code, node = method_info[0:]
        if test_name == method_name:
            # if node.annotations != None:
            #     for ele in node.annotations:
            #         if ele.name != "Test":
            #             continue
            # res = [start,end,method_name,method_code,node.annotations]
            res = method_code
    return res

def write_dict_csv(csv_path, fields, dict_data):
    with open(csv_path, 'a') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fields)
        writer.writerow(dict_data)

def write_header_csv(csv_path, fields):
    with open(csv_path, 'w') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fields)
        writer.writeheader()

def read_file(file_path):
    file = open(file_path, 'r')
    content = file.read()
    return content

def write_file(file_path,content):
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
    except:
        pass
    f = open(file_path, "w")
    f.write(content)
    f.close()

def write_json(file_path, dict):
    with open(file_path, 'w') as fp:
        json.dump(dict, fp)

def write_json_attach(file_path, dict):
    with open(file_path, 'a') as fp:
        json.dump(dict, fp)

def git_diff(file_path):
    diff_path = file_path.replace(".py","_diff.patch")
    diff_opts = ["git", "diff", file_path] #, "|& tee", diff_path
    print(" ".join(diff_opts), flush=True)
    diff = subprocess.run(diff_opts, stdout=subprocess.PIPE)
    diff_output = diff.stdout.decode('utf-8')
    write_file(diff_path, diff_output)
    # print(diff_output)
    return diff_path

def diff(source_file, target_file):
    diff_path = target_file.replace(".py","_diff.patch")
    diff_opts = ["diff", source_file, target_file]
    diff_output = run_cmds(diff_opts, None)
    write_file(diff_path, diff_output)
    # print(diff_output)
    return diff_output, diff_path

def run_cmds(cmd_list, timeoutVal):
    cmds = " ".join(cmd_list)
    # print(cmds, flush=True)
    if timeoutVal != None:
        run_cmds = subprocess.run(cmd_list, stdout=subprocess.PIPE, timeout=timeoutVal) #check=True, capture_output=True, shell=True
    else:
        run_cmds = subprocess.run(cmd_list, stdout=subprocess.PIPE)
    output = run_cmds.stdout.decode('utf-8')
    # print(output, flush=True)
    return output

def run_cmds_nopipe(cmd_list, timeoutVal):
    cmds = " ".join(cmd_list)
    print(cmds, flush=True)
    if timeoutVal != None:
        run_cmds = subprocess.run(cmds, check=True, capture_output=True, shell=True, timeout=timeoutVal) #check=True, capture_output=True, shell=True
    else:
        run_cmds = subprocess.run(cmds, check=True, capture_output=True, shell=True)
    output = run_cmds.stdout.decode('utf-8')
    # print(output, flush=True)
    return output

def git_checkout(file_path):
    git_checkout_opts = ["git", "checkout", file_path]
    print(" ".join(git_checkout_opts), flush=True)
    git_checkout = subprocess.run(git_checkout_opts, stdout=subprocess.PIPE)
    git_checkout_output = git_checkout.stdout.decode('utf-8')
    return git_checkout_output

def extract_java_code(text):
    lst = text.replace("```java","\n").replace("```","\n").replace("//<fix start>","\n").replace("//<fix end>","\n").split("\n")
    left = 0
    right = 0
    methods = {}
    idx = 0
    method = []
    inAmethod = False
    for line in lst:
        if "public class " in line:
            continue
        idx += 1
        l = line.count("{")
        left += l
        r = line.count("}")
        right += r
        if left == right and right > 0 and inAmethod == True:
            method.append(line)
            left = 0
            right = 0
            methods[str(idx)] = method
            method = []
            inAmethod = False
        elif left > right:
            inAmethod = True
            method.append(line)
        elif line.strip() in ["@Before","@After", "@BeforeEach","@AfterEach","@BeforeAll","@AfterAll","@BeforeClass","@AfterClass"]:
            inAmethod = True
            method.append(line)
    
    dummy_code = "public class Lambda {\n"
    for key in methods:
        method = "\n".join(methods[key]) + "\n"
        dummy_code += method
    dummy_code += "\n}\n"

    # print(dummy_code)

    method_list = parse_java_func_intervals(dummy_code)
    if method_list != None:
        return method_list,True
    else:
        return methods,False