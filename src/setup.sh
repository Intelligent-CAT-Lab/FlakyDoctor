apt-get update
apt update
apt-get install -y openjdk-8-jdk
apt-get install -y maven gradle
apt-get install -y openjdk-11-jdk
apt-get install autoconf -y
apt-get install libtool -y
apt install protobuf-compiler -y

add-apt-repository ppa:deadsnakes/ppa -y
apt install git-all -y
pip3 install jsonlines
pip3 install GitPython
pip3 install beautifulsoup4==4.12.3
pip3 install javalang==0.13.0
pip3 install openai==0.28.0
pip3 install torch==2.1.0
pip3 install transformers==4.31.0
pip3 install git+https://github.com/jose/javalang.git@start_position_and_end_position
pip3 install accelerate==0.21.0

wget https://github.com/google/protobuf/releases/download/v2.5.0/protobuf-2.5.0.tar.gz
tar xvf protobuf-2.5.0.tar.gz
cd protobuf-2.5.0
./autogen.sh
./configure --prefix=/usr
make
make install
protoc --version