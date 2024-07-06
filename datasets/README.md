# Dataset

File structures in the directory `datasets`:
- `ID_projects.csv`: Input of ID Java projects you need to set up, each line is in the format of `Project URL, SHA, Module`.
- `ID_inputs.csv`: Input of ID flaky tests in the format of `Project URL, SHA, Module, Test Full Name, Test Type, Status, PR, Notes` which is same as [IDoFT](https://github.com/TestingResearchIllinois/idoft).
- `OD_projects.csv`: Input of OD Java projects you need to set up, each line is in the format of `Project URL, SHA, Module`.
- `OD_inputs.csv`: Input of OD flaky tests in the format of `Project URL, SHA, Module, OD Victim Test, OD Polluter Test` which is same as [ODRepair](https://github.com/UT-SE-Research/ODRepair).
- `demo.csv`: A demo sample for reproduction.