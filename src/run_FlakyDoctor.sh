clone_dir=$1
api_key=$2
model=$3
output_dir=$4
flakies=$5
flakiness_type=$6
nondex_times=3

TimeStamp=$(echo -n $(date "+%Y-%m-%d %H:%M:%S") | shasum | cut -f 1 -d " ")

mkdir -p ${output_dir}
DIR=${output_dir}/ID_Results_${model}_${clone_dir}_${TimeStamp}
mkdir -p ${DIR}
echo "Running... Please refer to the results in ${DIR}"

exec 3>&1 4>&2
trap $(exec 2>&4 1>&3) 0 1 2 3
exec 1>${DIR}/${TimeStamp}.log 2>&1

echo "* "STARTING at $(date) 
echo "* "REPO VERSION $(git rev-parse HEAD)

for file in "${flakies[@]}"; do
    SubTimeStamp=$(echo -n $(date "+%Y-%m-%d %H:%M:%S") | shasum | cut -f 1 -d " ")
    result_csv=${DIR}/${model}_results_${SubTimeStamp}.csv
    result_json=${DIR}/${model}_results_${SubTimeStamp}.json
    save_dir=${DIR}
    details_json=${DIR}/${model}_test_details_${SubTimeStamp}.json
    python3 -u src/flakydoctor.py --input-tests-csv ${file} --projects ${clone_dir} --openai-key ${api_key} --model ${model} --nondex-times ${nondex_times} --output-dir ${save_dir} --output-result-csv ${result_csv} --output-result-json ${result_json} --output-details-json ${details_json} --flakiness-type ${flakiness_type}
done

echo "* "ENDING at $(date)