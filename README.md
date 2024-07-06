# FlakyDoctor

This repo contains the source code and results of FlakyDoctor. FlakyDoctor is a neuro-symbolic approach to fix Implementation-Dependent (ID) and Order-Dependent (OD) tests.

## 🌟 File structures
File structures in this repository are as follows, please refer to `README.md` in each directory for more details: 
- [datasets](datasets/README.md): Datasets of flaky tests in the evaluation.
- [patches](patches/README.md): Successful patches generated.
- [results](results/README.md): Detailed results for successfully fixed flaky tests in the evaluation.
- [src](src/README.md): Source code and scripts to run FlakyDoctor.

## 🌟 Reproduce the results

To reproduce the results from scratch, one should run the following commands:

0. Before starting:
FlakyDoctor works on `Linux` with the following requirements:
- Python 3.10.12
- Java 8 and Java 11
- Please also prepare an openai key and local checkpoints of [Magicoder](https://huggingface.co/ise-uiuc/Magicoder-S-DS-6.7B)

1. Set up requirements:
```
git clone https://github.com/dserfe/FlakyDoctor
cd FlakyDoctor
bash -x src/setup.sh
```
2. create an `.env` which includes your local path of model [Magicoder](https://huggingface.co/ise-uiuc/Magicoder-S-DS-6.7B):
```
echo "Magicoder_LOAD_PATH=[Your local path of Magicoder checkpoints]" > .env
```

3. Clone and build all Java projects:
To clone and build the projects, one should run the following commands:
```
bash -x src/install.sh [input_csv] [clone_dir] [output_dir] [save_csv]
```
- `input_csv`: Input of ID Java projects you need to set up, each line is in the format of `Project URL, SHA, Module`. More details in [datasets](datasets/README.md).
- `clone_dir`: A directory to clone all the java projects.
- `output_dir`: A directory for outputs and logs when building the projects.
- `save_csv`: A summary of the build results.

For example, one can run `bash -x src/install.sh datasets/ID_projects.csv projects outputs summary.csv` to build all Java projects for ID tests (~15 hours).

4. Run FlakyDoctor to fix flaky tests:
To fix flaky tests, one should run the following commands:
```
bash -x src/run_FlakyDoctor.sh [clone_dir] [openai_key] [model] [output_dir] [input_csv] [test_type]
```
- `clone_dir`: A directory where all the java projects are cloned.
- `openai_key`: Your openai authentication key.
- `output_dir`: A directory to save all the results.
- `input_csv`: A input `.csv` file including all the flaky tests. More details in [datasets](datasets/README.md).
- `test_type`: The type of flakiness to fix, `ID` or `OD`.

We procide a demo to reproduce the results quickly:

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
  --model MODEL         LLM model to run, currently we support [GPT-4, Magicoder].
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

## 🌟 Pull requests
19 Tests have been accepted (one PR may include fixes for multiple tests):

**Accepted PRs:**
- https://github.com/funkygao/cp-ddd-framework/pull/65
- https://github.com/apache/pinot/pull/11771
- https://github.com/dropwizard/dropwizard/pull/7629
- https://github.com/opengoofy/hippo4j/pull/1495
- https://github.com/moquette-io/moquette/pull/781
- https://github.com/jnr/jnr-posix/pull/185
- https://github.com/FasterXML/jackson-jakarta-rs-providers/pull/22
- https://github.com/yangfuhai/jboot/pull/117

**Opened PRs:**
- https://github.com/perwendel/spark/pull/1285
- https://github.com/dyc87112/SpringBoot-Learning/pull/98
- https://github.com/graphhopper/graphhopper/pull/2899
- https://github.com/BroadleafCommerce/BroadleafCommerce/pull/2901
- https://github.com/dianping/cat/pull/2320
- https://github.com/hellokaton/30-seconds-of-java8/pull/8
- https://github.com/AmadeusITGroup/workflow-cps-global-lib-http-plugin/pull/68
- https://github.com/wro4j/wro4j/pull/1167
- https://github.com/kevinsawicki/http-request/pull/177
- https://github.com/apache/flink/pull/23648


*We are waiting for developers to approve our requests to create an issue for the following PRs:*
- https://github.com/dserfe/flink/pull/2
- https://github.com/dserfe/nifi/pull/1
- https://github.com/dserfe/jenkins/pull/1

**Why other tests can not be opened PRs:**
```
Tests are deleted in the latest version of the project:
- org.apache.dubbo.registry.client.metadata.ServiceInstanceMetadataUtilsTest.testMetadataServiceURLParameters
- org.apache.cayenne.CayenneContextClientChannelEventsIT.testSyncToOneRelationship
- org.apache.shardingsphere.elasticjob.cloud.scheduler.env.BootstrapEnvironmentTest.assertWithoutEventTraceRdbConfiguration
- org.apache.shardingsphere.elasticjob.cloud.scheduler.mesos.AppConstraintEvaluatorTest.assertExistExecutorOnS0
- net.sf.marineapi.ais.event.AbstractAISMessageListenerTest.testParametrizedConstructor
- net.sf.marineapi.ais.event.AbstractAISMessageListenerTest.testSequenceListener
- com.willwinder.universalgcodesender.GrblControllerTest.testGetGrblVersion
- com.willwinder.universalgcodesender.GrblControllerTest.testIsReadyToStreamFile

Tests are fixed by developers in the latest version of the project:
- io.elasticjob.lite.lifecycle.internal.settings.JobSettingsAPIImplTest.assertUpdateJobSettings
- net.sf.marineapi.ais.event.AbstractAISMessageListenerTest.testBasicListenerWithUnexpectedMessage
- net.sf.marineapi.ais.event.AbstractAISMessageListenerTest.testConstructor
- net.sf.marineapi.ais.event.AbstractAISMessageListenerTest.testGenericsListener
- net.sf.marineapi.ais.event.AbstractAISMessageListenerTest.testOnMessageWithExpectedMessage
- com.willwinder.universalgcodesender.GrblControllerTest.rawResponseHandlerOnErrorWithNoSentCommandsShouldSendMessageToConsole
- com.willwinder.universalgcodesender.GrblControllerTest.rawResponseHandlerWithKnownErrorShouldWriteMessageToConsole
- com.willwinder.universalgcodesender.GrblControllerTest.rawResponseHandlerWithUnknownErrorShouldWriteGenericMessageToConsole
- com.graphhopper.isochrone.algorithm.IsochroneTest.testSearch

Tests are actually different types of flakiness after inspected:
- com.baidu.jprotobuf.pbrpc.EchoServiceTest.testDynamiceTalkTimeout

Repository is archived:
- io.searchbox.indices.RolloverTest.testBasicUriGeneration
- com.netflix.exhibitor.core.config.zookeeper.TestZookeeperConfigProvider.testConcurrentModification
- org.springframework.security.oauth2.provider.client.JdbcClientDetailsServiceTests.testUpdateClientRedirectURI
``` 

