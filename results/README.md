# Results

File structures in the directory `results`:
- `gpt_fixes_tests.csv` includes the detailed results of all 500 successfully fixed ID flaky tests from GPT-4. Each line includes `Project URL,SHA,Module,Type,Test,Results,Patch`.
- `magicoder_fixes_tests.csv` includes the detailed results of all 170 successfully fixed ID flaky tests from Magicoder. Each line includes `Project URL,SHA,Module,Type,Test,Results,Patch`.
- `vanilla_results` includes the results for only prompting models with vanilla prompt *"This is a flaky test. Can you fix it?"*

In the column of `Results`, `F` represents `Test Failure`, `P` represents `Test Pass`, and `CE` represents `Compilation Error`.