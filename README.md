# FlakyDoctor

This repo contains the source code and results of FlakyDoctor. FlakyDoctor is a neuro-symbolic approach to fix Implementation-Dependent (ID) and Order-Dependent (OD) tests.

## 🌟 File structures
File structures in this repository are as follows, please refer to `README.md` in each directory for more details: 
- [datasets](datasets/README.md): Datasets of flaky tests in the evaluation.
- [patches](patches/README.md): Successful patches generated.
- [results](results/README.md): Detailed results for successfully fixed flaky tests in the evaluation.
- `src`: Source code and scripts to run FlakyDoctor.

## 🌟 Get started to run the tool!
The options of `FlakyDoctor`:
```
usage: flakydoctor.py [-h] --input-tests-csv INPUT_TESTS_CSV --flakiness-type FLAKINESS_TYPE --projects PROJECTS --openai-key OPENAI_KEY --model MODEL [--nondex-times NONDEX_TIMES] --output-dir OUTPUT_DIR --output-result-csv OUTPUT_RESULT_CSV --output-result-json OUTPUT_RESULT_JSON --output-details-json OUTPUT_DETAILS_JSON

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

For example,

## 🌟 Reproduce the results
To reproduce the results from scratch, one should run the following commands:
1. Set up environment
```
git clone https://github.com/dserfe/FlakyDoctor
cd FlakyDoctor
bash -x src/setup.sh
```
create an `.env` with the following content:
```
MagiCoder_LOAD_PATH=/home/shared/huggingface/models--ise-uiuc--Magicoder-S-DS-6.7B/snapshots/cff055b1e110cbe75c0c3759bd436299c6d6bb66/

```

2. Clone and build all the projects
```
bash -x src/install.sh input_csv clone_dir output_dir save

bash -x src/install.sh datasets/demo.csv projects outputs 1.csv
```
Since one project may include multiple SHAs, 

## 🌟 Pull requests

