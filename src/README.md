# SRC

File structures in `src` are as follows:
```
src/
# commands to run some neccessary tools
├── cmds 
│   ├── checkout_project.sh
│   ├── run_nondex.sh
│   ├── run_surefire.sh
│   └── stash_project.sh
# main code of FlakyDoctor
├── flakydoctor.py 
├── install.sh
├── operate_patch.py
├── parse_nondex.py
├── process_line.py
├── repair_ID.py
├── repair_OD.py
├── run_FlakyDoctor.sh
├── setup.sh
├── stitching.py
├── update_pom.py
├── utils
│   ├── java_dependencies.json
│   └── java_standard_libs.json
└── utils.py
```

To run FlakyDoctor, you need to specify the following options:
```
usage: flakydoctor.py [-h] --input-tests-csv INPUT_TESTS_CSV --flakiness-type FLAKINESS_TYPE --projects PROJECTS
                      --openai-key OPENAI_KEY --model MODEL [--nondex-times NONDEX_TIMES] --output-dir OUTPUT_DIR
                      --output-result-csv OUTPUT_RESULT_CSV --output-result-json OUTPUT_RESULT_JSON
                      --output-details-json OUTPUT_DETAILS_JSON

options:
  -h, --help            show this help message and exit
  --input-tests-csv INPUT_TESTS_CSV
                        A csv file include flaky tests with consistent format as in IDoFT `pr-data.csv`.
  --flakiness-type FLAKINESS_TYPE
                        Flakiness type to fix, select one from [ID, OD].
  --projects PROJECTS   A directory path where you save all the Java projects.
  --openai-key OPENAI_KEY
                        Your openai key
  --model MODEL         LLM model to run, currently we support [GPT-4, MagiCoder].
  --nondex-times NONDEX_TIMES
                        How many times you want to nondex to rerun.
  --output-dir OUTPUT_DIR
                        A directory to save all the outputs.
  --output-result-csv OUTPUT_RESULT_CSV
                        A csv to save summary of results.
  --output-result-json OUTPUT_RESULT_JSON
                        A json to save summary of results.
  --output-details-json OUTPUT_DETAILS_JSON
                        A json to save details of results.
```