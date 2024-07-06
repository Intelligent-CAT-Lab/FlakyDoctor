# FlakyDoctor

This repo contains the source code and results of FlakyDoctor.

## File structures
- `datasets`: Datasets for evaluation.
- `patches`: Successful patches generated in evaluation.
- `results`: Detailed results for successfully fixed flaky tests in the evaluation.
- `src`: Source code and scripts to run FlakyDoctor.

## Get started to run the tool!

## Reproduce the results
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

## Pull requests

