projectDir=$1 #abs path
file_path=$2

cd ${projectDir}
echo $(PWD)
echo "git checkout" ${file_path}
git checkout ${file_path}