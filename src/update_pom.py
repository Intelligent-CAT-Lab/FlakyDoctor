import os
import sys

def dependency_exists(pom_lines, artifactId):
    for line in pom_lines:
        if f'<artifactId>{artifactId}</artifactId>' in line:
            return True
    return False

def add_dependency(pom_path, dependency_lines):

    updated_pom_lines = []
    d_list = dependency_lines.split("</dependency>")
    for dep in d_list:
        if "<dependency>" in dep:
            d = "<dependency>\n" + dep.split("<dependency>")[1]
            if "<artifactId>" in d:
                with open(pom_path, 'r') as pom_file:
                    pom_lines = pom_file.readlines()
                artifactId = (d.split("<artifactId>")[1]).split("</artifactId>")[0]
                if "mycompany" in artifactId:
                    print("will not add", artifactId)
                if "artifact" in artifactId:
                    print("will not add", artifactId)
                if dependency_exists(pom_lines, artifactId):
                    print(artifactId, " already in pom.xml, no need to add")
                else:
                    print(artifactId, " will be added")
                    for line in pom_lines:
                        updated_pom_lines.append(line)
                        if '<dependencies>' in line:
                            updated_pom_lines.extend(d + "</dependency>\n")
                    with open(pom_path, 'w') as pom_file_new:
                        pom_file_new.writelines(updated_pom_lines)
