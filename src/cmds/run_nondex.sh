projectDir=$1
module=$2
test=$3
jdk=$4
times=$5

mainDir=${projectDir}
curDir=$(pwd)

run_test(){
    echo "* mvn edu.illinois:nondex-maven-plugin:2.1.7:nondex -pl ${module} -Dtest=${test} -Dbasepom.check.skip-prettier -Dgpg.skip -Dfindbugs.skip=true -Drat.skip -Dcheckstyle.skip -Denforcer.skip=true -Dspotbugs.skip -Dmaven.test.failure.ignore=true -Djacoco.skip -Danimal.sniffer.skip -Dmaven.antrun.skip -Dfmt.skip -Dskip.npm -Dlicense.skipCheckLicense -Dlicense.skipAddThirdParty=true -Dfindbugs.skip -Dlicense.skip -Dskip.npm -Dskip.yarn -Dskip.bower -Dskip.grunt -Dskip.gulp -Dskip.jspm -Dskip.karma -Dskip.webpack -DskipDockerBuild -DskipDockerTag -DskipDockerPush -DskipDocker -Denforcer.skip -DnondexRuns=${times} -Dstyle.color=never -Ddependency-check.skip -Dspotless.check.skip"
    mvn edu.illinois:nondex-maven-plugin:2.1.7:nondex -pl ${module} -Dtest=${test} -Dbasepom.check.skip-prettier -Dgpg.skip -Dfindbugs.skip=true -Drat.skip -Dcheckstyle.skip -Denforcer.skip=true -Dspotbugs.skip -Dmaven.test.failure.ignore=true -Djacoco.skip -Danimal.sniffer.skip -Dmaven.antrun.skip -Dfmt.skip -Dskip.npm -Dlicense.skipCheckLicense -Dlicense.skipAddThirdParty=true -Dfindbugs.skip -Dlicense.skip -Dskip.npm -Dskip.yarn -Dskip.bower -Dskip.grunt -Dskip.gulp -Dskip.jspm -Dskip.karma -Dskip.webpack -DskipDockerBuild -DskipDockerTag -DskipDockerPush -DskipDocker -Denforcer.skip -DnondexRuns=${times} -Dstyle.color=never -Ddependency-check.skip -Dspotless.check.skip
}

echo "* RUNNING NonDex on ID test ${test} STARTING at $(date)"
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

for i in {1..${times}}
do
    run_test ${i}
done

cd ${curDir}
echo "* RUNNING NonDex on ID test ${test} ENDING at $(date) "