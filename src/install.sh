INPUT_CSV=$1 # input csv of [project,sha,module]
CLONE_DIR=$2 # directory to clone all projects
OUTPUT_DIR=$3 # output directory of project build logs
SAVE=$4 # csv to save build results

TimeStamp=$(echo -n $(date "+%Y-%m-%d %H:%M:%S") | shasum | cut -f 1 -d " ")
mkdir -p ./${OUTPUT_DIR}/${TimeStamp}/install_logs

PWD_DIR=$(pwd)
MAIN_DIR=$(pwd)/${CLONE_DIR}
LOG_DIR=$(pwd)/${OUTPUT_DIR}/${TimeStamp}/install_logs
SAVE_CSV=$(pwd)/${SAVE}
echo project,sha,module,build_result,java_version > ${SAVE_CSV}

exec 3>&1 4>&2
trap $(exec 2>&4 1>&3) 0 1 2 3
exec 1>${LOG_DIR}/${TimeStamp}.log 2>&1

echo "* "STARTING at $(date) 
echo "* "REPO VERSION $(git rev-parse HEAD)

install(){
    echo "Java version 8"
    export JAVA_HOME=/usr/lib/jvm/java-1.8.0-openjdk-amd64
    export PATH=$JAVA_HOME/bin:$PATH

    t=$(echo -n $(date "+%Y-%m-%d %H:%M:%S") | shasum | cut -f 1 -d " ")
    install_log=${MAIN_DIR}/${sha}/${project}/install_${project}_${t}.log
    mvn install -pl ${module} -am -DskipTests -Dfindbugs.skip=true -Dbasepom.check.skip-prettier -Dgpg.skip -Drat.skip -Dskip.npm -Dskip.yarn -Dskip.bower -Dskip.grunt -Dskip.gulp -Dskip.jspm -Dskip.karma -Dskip.webpack -Dcheckstyle.skip -Denforcer.skip=true -Dspotbugs.skip -Dmaven.test.failure.ignore=true -Djacoco.skip -Danimal.sniffer.skip -Dmaven.antrun.skip -Dfmt.skip -Dskip.npm -Dlicense.skipCheckLicense -Dlicense.skipAddThirdParty=true -Dfindbugs.skip -Dlicense.skip -DskipDockerBuild -DskipDockerTag -DskipDockerPush -DskipDocker -Denforcer.skip -Ddependency-check.skip > ${install_log}
    res="$(grep 'BUILD ' ${install_log})"

    build_result="NONE"
    if [[ ${res} == *"BUILD FAILURE"* ]]; then
        build_result="BUILD FAILURE"
    fi

    if [[ ${res} == *"BUILD SUCCESS"* ]]; then
        build_result="BUILD SUCCESS"
    fi

    echo "build-result:" ${project} ${sha} ${module} ${build_result}
    echo "${project},${sha},${module},${build_result},8" >> ${SAVE_CSV}
    
    if [[ ${build_result} == "BUILD FAILURE" ]]; then
        echo "Java version 11"
        export JAVA_HOME=/usr/lib/jvm/java-1.11.0-openjdk-amd64
        export PATH=$JAVA_HOME/bin:$PATH

        t=$(echo -n $(date "+%Y-%m-%d %H:%M:%S") | shasum | cut -f 1 -d " ")
        install_log=${MAIN_DIR}/${sha}/${project}/install_${project}_${module}_${t}.log
        mvn install -pl ${module} -am -DskipTests -Dfindbugs.skip=true -Dbasepom.check.skip-prettier -Dgpg.skip -Drat.skip -Dskip.npm -Dskip.yarn -Dskip.bower -Dskip.grunt -Dskip.gulp -Dskip.jspm -Dskip.karma -Dskip.webpack -Dcheckstyle.skip -Denforcer.skip=true -Dspotbugs.skip -Dmaven.test.failure.ignore=true -Djacoco.skip -Danimal.sniffer.skip -Dmaven.antrun.skip -Dfmt.skip -Dskip.npm -Dlicense.skipCheckLicense -Dlicense.skipAddThirdParty=true -Dfindbugs.skip -Dlicense.skip -DskipDockerBuild -DskipDockerTag -DskipDockerPush -DskipDocker -Denforcer.skip -Ddependency-check.skip > ${install_log}
        res="$(grep 'BUILD ' ${install_log})"

        build_result="NONE"
        if [[ ${res} == *"BUILD FAILURE"* ]]; then
            build_result="BUILD FAILURE"
        fi

        if [[ ${res} == *"BUILD SUCCESS"* ]]; then
            build_result="BUILD SUCCESS"
        fi
        echo "build-result:" ${project} ${sha} ${module} ${build_result}
        echo "${project},${sha},${module},${build_result},11" >> ${SAVE_CSV}
    fi
}

for info in $(cat ${INPUT_CSV}); do
    URL=$(echo $info | cut -d, -f1)
    SHA=$(echo $info | cut -d, -f2)
    MODULE=$(echo $info | cut -d, -f3)

    url=${URL/$'\r'/}
    sha=${SHA/$'\r'/}
    module=${MODULE/$'\r'/}
    project=${url##*/}

    cd ${MAIN_DIR}

    if [[ ! -d ${sha} ]]; then
        echo Directory ${sha} does not exist in ${MAIN_DIR}
        mkdir -p ${sha}
    fi
    cd ${sha}

    if [[ ! -d ${project} ]]; then
        echo Directory ${project} does not exist in ${MAIN_DIR}/${sha}
        git clone ${url}
    fi
    cd ${project}

    git stash
    git checkout ${sha}
    
    install
    done

cd ${PWD_DIR}
echo "* "ENDING at $(date)