projectDir=$1
module=$2
polluterFormatTest=$3
victimFormatTest=$4
jdk=$5

mainDir=${projectDir}
curDir=$(pwd)

run_test(){
    echo mvn test -pl ${module} -Dsurefire.runOrder=testorder -Dtest=${polluterFormatTest},${victimFormatTest} -Drat.skip -Dcheckstyle.skip -Denforcer.skip=true -Dspotbugs.skip -Dmaven.test.failure.ignore=true -Djacoco.skip -Danimal.sniffer.skip -Dmaven.antrun.skip -Djacoco.skip -Dspotless.check.skip --log-file ${logDir}/"$1".log
    mvn test -pl ${module} -Dsurefire.runOrder=testorder -Dtest=${polluterFormatTest},${victimFormatTest} -Drat.skip -Dcheckstyle.skip -Denforcer.skip=true -Dspotbugs.skip -Dmaven.test.failure.ignore=true -Djacoco.skip -Danimal.sniffer.skip -Dmaven.antrun.skip -Djacoco.skip -Dspotless.check.skip --log-file ${logDir}/"$1".log
}

echo "* RUNNING Surefire on OD tests ${polluterFormatTest} ${victimFormatTest} STARTING at $(date)"
echo "* REPO VERSION $(git rev-parse HEAD)"

cd ${mainDir}
echo "* CURRENT DIR $(pwd)"
echo "* Expected Java version ${jdk}"

if  [[ ${jdk} == "8" ]]; then
    echo "Java version 8"
    export JAVA_HOME=/usr/lib/jvm/java-1.8.0-openjdk-amd64
    export PATH=$JAVA_HOME/bin:$PATH
fi

if  [[ ${jdk} == "11" ]]; then
    echo "Java version 11"
    export JAVA_HOME=/usr/lib/jvm/java-1.11.0-openjdk-amd64
    export PATH=$JAVA_HOME/bin:$PATH
fi

echo CURRENT DIR $(pwd)

run_test ${i} ${polluterFormatTest} ${victimFormatTest}

cd ${curDir}
echo "* RUNNING Surefire on OD tests ${polluterFormatTest} ${victimFormatTest} ENDING at $(date)"