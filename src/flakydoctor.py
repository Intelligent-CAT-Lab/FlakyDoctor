import argparse
import os
import openai
import sys
import repair_ID
import repair_OD

def parse_args():
    parser = argparse.ArgumentParser(description="""
            FlakyDoctor: Neuro-symbolic repair of Implementation-Dependent (ID) and Order-Dependent (OD) flaky tests.
            """,)
    parser.add_argument("--input-tests-csv", dest = "input_tests_csv", required = True,
                        help = "A csv file include flaky tests with consistent format as in IDoFT `pr-data.csv`.")
    parser.add_argument("--flakiness-type", dest = "flakiness_type", required = True,
                        help = "Flakiness type to fix, select one from [ID, OD].")
    parser.add_argument("--projects", dest = "projects", required = True,
                        help = "A directory path where you save all the Java projects.")
    parser.add_argument("--openai-key", dest = "openai_key", required = True,
                        help = "Your openai key")
    parser.add_argument("--model", dest = "model", required = True,
                        help = "LLM model to run, currently we support [GPT-4, MagiCoder].")
    parser.add_argument("--nondex-times", dest = "nondex_times", required = False, default = 3,
                        help = "How many times you want to nondex to rerun.")
    parser.add_argument("--output-dir", dest = "output_dir", required = True,
                        help = "A directory to save all the outputs.")  
    parser.add_argument("--output-result-csv", dest = "output_result_csv", required = True,
                        help = "A csv to save summary of results.") 
    parser.add_argument("--output-result-json", dest = "output_result_json", required = True,
                        help = "A json to save summary of results.")  
    parser.add_argument("--output-details-json", dest = "output_details_json", required = True,
                        help = "A json to save details of results.")    
    args = parser.parse_args()
    return args

if __name__ == "__main__":
    args = parse_args()
    input_flakies_csv = args.input_tests_csv
    projects_dir = args.projects
    flakiness_type = args.flakiness_type
    api_key = args.openai_key
    model = args.model
    nondex_times = args.nondex_times
    output_dir = args.output_dir
    result_csv = args.output_result_csv
    result_json = args.output_result_json
    details_json = args.output_details_json

    openai.api_key = api_key
    openai.organization = os.getenv("OPENAI_ORGANIZATION")
    
    if flakiness_type == "ID":
        repair_ID.main(input_flakies_csv, projects_dir, details_json, model, nondex_times, result_csv, result_json, output_dir)
    elif flakiness_type == "OD":
        repair_OD.main(input_flakies_csv, projects_dir, details_json, model, nondex_times, result_csv, result_json, output_dir)


