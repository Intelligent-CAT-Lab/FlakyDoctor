input_csv=$1 # input csv of [project,sha,module]
clone_dir=$2 # directory to clone all projects
output_dir=$3 # output directory of project build logs
save=$4 # csv to save build results

TimeStamp=$(echo -n $(date "+%Y-%m-%d %H:%M:%S") | shasum | cut -f 1 -d " ")
pwd_dir=$(pwd)
main_dir=$(pwd)/${clone_dir}
log_dir=$(pwd)/${output_dir}/${TimeStamp}/install_logs
save_csv=$(pwd)/${save}

mkdir -p ${main_dir}
mkdir -p ${log_dir}

echo project,sha,module,build_result,java_version > ${save_csv}

exec 3>&1 4>&2
trap $(exec 2>&4 1>&3) 0 1 2 3
exec 1>${log_dir}/${TimeStamp}.log 2>&1

echo "* "STARTING at $(date) 
echo "* "REPO VERSION $(git rev-parse HEAD)

install(){
    echo "Java version 8"
    export JAVA_HOME=/usr/lib/jvm/java-1.8.0-openjdk-amd64
    export PATH=$JAVA_HOME/bin:$PATH

    t=$(echo -n $(date "+%Y-%m-%d %H:%M:%S") | shasum | cut -f 1 -d " ")
    install_log=${main_dir}/${sha}/${project}/install_${project}_${t}.log
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
    echo "${project},${sha},${module},${build_result},8" >> ${save_csv}
    
    if [[ ${build_result} == "BUILD FAILURE" ]]; then
        echo "Java version 11"
        export JAVA_HOME=/usr/lib/jvm/java-1.11.0-openjdk-amd64
        export PATH=$JAVA_HOME/bin:$PATH

        t=$(echo -n $(date "+%Y-%m-%d %H:%M:%S") | shasum | cut -f 1 -d " ")
        install_log=${main_dir}/${sha}/${project}/install_${project}_${module}_${t}.log
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
        echo "${project},${sha},${module},${build_result},11" >> ${save_csv}
    fi
}

for info in $(cat ${input_csv}); do
    URL=$(echo $info | cut -d, -f1)
    SHA=$(echo $info | cut -d, -f2)
    MODULE=$(echo $info | cut -d, -f3)

    url=${URL/$'\r'/}
    sha=${SHA/$'\r'/}
    module=${MODULE/$'\r'/}
    project=${url##*/}

    cd ${main_dir}

    if [[ ! -d ${sha} ]]; then
        echo Directory ${sha} does not exist in ${main_dir}
        mkdir -p ${sha}
    fi
    cd ${sha}

    if [[ ! -d ${project} ]]; then
        echo Directory ${project} does not exist in ${main_dir}/${sha}
        git clone ${url}
    fi
    cd ${project}

    git stash
    git checkout ${sha}
    
    install
    done

cd ${pwd_dir}
echo "* "ENDING at $(date)