import os
import sys
import linecache
import utils

# nondex_output from collect_flakies.output_nondex()
def get_line_location_msg(nondex_output,test_file_path,format_test):
    print("get_line_location_msg")
    output_seq = nondex_output.split("\n")
    test_class = test_file_path.split("/")[-1]
    test_full_name = format_test.replace("#", ".")
    test_class_name = format_test.split("#")[0]

    s_list = nondex_output.split("<<< FAILURE!")[1:]

    line_nums = []
    res_lines = []

    for seq in s_list:
        item = seq.replace("\x1b[1;31m","").replace("\x1b[m","").replace("\x1b[1m","").replace("\x1b[36m","").replace("\x1b[1;34m","")
        if "Results" in item and "Failures: 1" in item:
            add_info = item.split("Results")[0]
            if "\tat " in add_info:
                lines_info = (add_info.split("\tat", 1)[1]).split("\n")
                for line in lines_info:
                    if test_class in line and test_full_name in line \
                        and ":" in line and ")" in line:
                        num = (line.split(":")[1]).split(")")[0]
                        if num not in line_nums:
                            line_nums.append(num)
        if "Results" in item and "Errors: 1" in item:
            add_info = item.split("Results")[0]
            if "\tat " in add_info:
                lines_info = (add_info.split("\tat", 1)[1]).split("\n")
                for line in lines_info:
                    if test_class in line and test_full_name in line \
                        and ":" in line and ")" in line:
                        num = (line.split(":")[1]).split(")")[0]
                        if num not in line_nums:
                            line_nums.append(num)

    if len(line_nums) == 0:
        for seq in output_seq:
             if "\tat " in seq:
                lines_info = (seq.split("\tat", 1)[1]).split("\n")
                for line in lines_info:
                    if test_class in line and test_class_name in line \
                        and ":" in line and ")" in line:
                        num = (line.split(":")[1]).split(")")[0]
                        if num not in line_nums:
                            line_nums.append(num)

    for num in line_nums:
        f = open(test_file_path)
        lines = f.readlines()
        line = lines[int(num)-1]
        if line not in res_lines:
            res_lines.append(line)

    print(line_nums)
    print(res_lines)
    
    return res_lines,line_nums

def nod_get_line_location_msg(nondex_output,test_file_path,format_test):
    print("get_line_caused_errors")
    output_seq = nondex_output.split("\n")
    test_class = test_file_path.split("/")[-1]
    test_full_name = format_test.replace("#", ".")
    test_class_name = format_test.split("#")[0]

    s_list = nondex_output.split("<<< FAILURE!")[1:]

    line_nums = []
    res_lines = []
    method_names = []

    for seq in output_seq:
        if "\tat " in seq:
            lines_info = (seq.split("\tat", 1)[1]).split("\n")
            for line in lines_info:
                if test_class_name in line and ":" in line and ")" in line:
                    num = (line.split(":")[1]).split(")")[0]
                    if num not in line_nums:
                        line_nums.append(num)
                    if test_class_name+"." in line:
                        new_line = line.replace(" ","")
                        method_name = new_line.split("(")[0].replace(test_class_name+".","")
                        if method_name not in method_names:
                            method_names.append(method_name)
        elif test_class_name + ".java" in seq and ":" in seq and "[" in seq and "]" in seq and "," in seq:
                    num = (seq.split("[")[1]).split(",")[0]
                    if num not in line_nums:
                        line_nums.append(num)

    for num in line_nums:
        f = open(test_file_path)
        lines = f.readlines()
        line = lines[int(num)-1]
        if line not in res_lines:
            res_lines.append(line)

    print(line_nums)
    print(res_lines)
    
    return res_lines,line_nums,method_names

def extract_test_method(test_name, class_content):
    # res: [start,end,method_name,method_code,node.annotations]
    res = utils.get_test_method(test_name, class_content)
    if res == None:
        return None
    test_method = res[3]
    return test_method

def get_potential_API(test_content):
    potential_APIs = {
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
    # test_method = test_full_name.split(".")[-1]
    # file = open(test_file_path, 'r', errors='ignore')
    # test_class = file.read()
    # test_content = extract_test_method(test_method, test_class)
    if test_content != None:
        lines = test_content.split("\n")
        for api in potential_APIs:
            for line in lines:
                if api in line:
                    potential_APIs[api].append(line)
        # print(potential_APIs)
    return potential_APIs
    

def get_line(line_num,file_path):
    file = open(test_file_path, 'r', errors='ignore')
    test_class = file.read()
    line = linecache.getline(file_path, int(line_num))
    print(line)