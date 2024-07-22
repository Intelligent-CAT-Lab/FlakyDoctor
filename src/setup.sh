sudo apt update
sudo apt install protobuf-compiler -y
sudo apt install git-all -y

sudo apt-get update
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt-get install openjdk-8-jdk -y
sudo apt-get install openjdk-11-jdk -y
sudo apt-get install maven -y
sudo apt-get install autoconf -y
sudo apt-get install libtool -y
sudo apt-get install python3-pip -y

pip3 install jsonlines
pip3 install GitPython
pip3 install lxml
pip3 install beautifulsoup4==4.12.3
pip3 install numpy==1.21.0
pip3 install openai==0.28.0
pip3 install torch==2.1.0
pip3 install transformers==4.31.0
pip3 install accelerate==0.21.0
pip3 uninstall javalang -y
pip3 install git+https://github.com/jose/javalang.git@start_position_and_end_position

# protobuf is needed to set up for Java projects in the evaluation
sudo apt-get install build-essential -y
sudo apt install g++ -y
wget https://github.com/google/protobuf/releases/download/v2.5.0/protobuf-2.5.0.tar.gz
tar xvf protobuf-2.5.0.tar.gz
cd protobuf-2.5.0
./autogen.sh
./configure --prefix=/usr
sudo make
sudo make install
protoc --version
