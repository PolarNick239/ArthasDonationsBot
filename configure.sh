# IP=51.15.75.185
# scp -r ~/coding/experiments/twitchbot root@${IP}:/root/

# https://askubuntu.com/a/849087
# nano /etc/apt/apt.conf.d/20auto-upgrades
# from APT::Periodic::Unattended-Upgrade "1";
# to   APT::Periodic::Unattended-Upgrade "0";

python_version=3.5

apt update
apt install git cmake build-essential python3-pip python3-venv ffmpeg
apt install tree

cd /root/

git clone https://github.com/opencv/opencv
cd opencv
git checkout tags/3.3.1
mkdir build
cd build
python${python_version} -m pip install numpy
cmake -DWITH_CUDA=OFF -DBUILD_TESTS=OFF -DBUILD_PERF_TESTS=OFF -DPYTHON3_EXECUTABLE=/usr/bin/python${python_version} -DPYTHON_EXECUTABLE=/usr/bin/python${python_version} -DPYTHON_LIBRARY=/usr/lib/python${python_version}/config-${python_version}m-x86_64-linux-gnu/libpython${python_version}m.so -DPYTHON_INCLUDE_DIR=/usr/include/python${python_version}m/ ..
make -j5
cd ../..

python${python_version} -m venv venv
. venv/bin/activate
pip install -r twitchbot/requirements.txt
cp opencv/build/lib/python3/cv2.cpython-35m-x86_64-linux-gnu.so venv/lib/python3.5/site-packages/

mkdir running
chmod +x twitchbot/run.sh

cp twitchbot/twitchbot.service /etc/systemd/system/
