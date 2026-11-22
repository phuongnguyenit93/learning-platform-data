# Cài đặt bằng gói hệ điều hành, máy ảo hoặc container

## 1. Mục tiêu và lựa chọn cách cài

Apache Cassandra là hệ quản trị cơ sở dữ liệu **wide-column phân tán**. Một node có thể chạy trên máy Linux cài trực tiếp từ gói hệ điều hành, trong một máy ảo (VM), hoặc trong container. Các cách cài này cung cấp cùng giao diện **CQL native protocol**, nhưng khác nhau về vị trí cấu hình, dữ liệu, vòng đời tiến trình và mạng. Hiểu được các khác biệt đó giúp bạn chuẩn bị môi trường để thực hành partition key, thiết kế bảng theo truy vấn, replication, consistency level, compaction, repair, xử lý lỗi và ứng dụng Java.

Sau bài này, bạn sẽ:

1. Chọn một trong các cách triển khai **APT/DEB, DNF/RPM, máy ảo Linux, Docker** phù hợp với mục đích.
2. Cài một node Cassandra 5.0, xác nhận phiên bản, trạng thái `UN` và chạy truy vấn CQL kiểm tra.
3. Xác định chính xác nơi đặt `cassandra.yaml`, dữ liệu SSTable/commitlog, log, cổng CQL và cách quản lý tiến trình ở từng cách cài.
4. Phân biệt cô lập của **VM** và **container**, biết cách lưu dữ liệu khi tạo lại môi trường.
5. Nhận diện lỗi về JDK, repository, firewall/NAT, advertised address, quyền volume và thiếu tài nguyên.
6. Chuẩn bị địa chỉ kết nối để tiếp tục thực hành với Apache Cassandra Java Driver.

> **Nguyên tắc thực hành:** chọn **một cách cài** cho bài smoke test đầu tiên. Các nhánh dưới đây là những lựa chọn **thay thế nhau**. Nếu bật nhiều node Cassandra ở các cách cài khác nhau trên cùng máy, cần tách cổng, tên cluster và vùng lưu dữ liệu; đừng vô tình cho node mới tham gia cluster khác.

## 2. So sánh các phương án

| Phương án | Nơi Cassandra chạy | Ưu điểm | Chi phí/giới hạn | Phù hợp nhất |
|---|---|---|---|---|
| **DEB/APT** trên Debian, Ubuntu | Tiến trình và dịch vụ trong Linux host | Gói tích hợp với quản lý dịch vụ, log và thư mục hệ thống | Cần quyền quản trị; cài trực tiếp vào host | Linux VM hoặc máy Linux riêng để luyện vận hành |
| **RPM/DNF** trên RHEL/AlmaLinux và hệ tương thích | Tiến trình và dịch vụ trong Linux host | Gần cách quản trị dịch vụ trên hệ RPM | Hỗ trợ gói tùy bản phân phối; phải kiểm tra repository và JDK | Lab vận hành trên hệ RPM |
| **Máy ảo Linux** | Guest OS có kernel, systemd, filesystem và IP riêng | Snapshot, thử lỗi hệ điều hành, mạng và nhiều node | Tốn RAM/CPU/đĩa hơn container; phải cấu hình mạng guest | Học vận hành nhiều node, lỗi node/VM |
| **Docker container** | Process Cassandra trong Linux container/VM Docker Desktop | Dựng nhanh, ghi version trong image, dễ tạo lại | Phải quản lý volume, network, tài nguyên; có khác biệt khi chạy trên Desktop | Học CQL/Java, demo, CI và lab có thể tái lập |
| **Binary tarball** (bổ sung) | Tiến trình người dùng trong Linux | Không cần cài gói hệ thống; dễ kiểm thử phiên bản cụ thể | Tự quản lý process, log, cấu hình; không có dịch vụ OS mặc định | Máy Linux không có quyền cài package hoặc kiểm thử nhanh |

**VM không phải một phương pháp cài Cassandra độc lập.** Trước tiên tạo VM Linux, sau đó cài **DEB/RPM** hoặc **tarball** *bên trong guest*. Container dùng image đã đóng gói Cassandra và runtime; lệnh `docker run` khởi động process thay cho `systemctl`.

```text
Ứng dụng Java hoặc cqlsh
        │ TCP 9042: native transport/CQL
        ▼
┌─────────────────────────────────────────────────────┐
│ Cassandra server + CQL + nodetool                   │
├──────────────────┬──────────────────┬───────────────┤
│ Linux host       │ Linux guest VM   │ Container     │
│ apt/dnf +        │ apt/dnf +        │ image +       │
│ systemd          │ systemd          │ Docker Engine │
│ /var/lib/...     │ guest disk       │ named volume  │
└──────────────────┴──────────────────┴───────────────┘
        Dữ liệu phải bền vững qua lần khởi động lại
```

## 3. Chuẩn bị chung và cố định phiên bản

### 3.1. Bộ phiên bản tham chiếu

Tại thời điểm biên soạn **21/11/2026**, Apache công bố Cassandra **5.0.9** là bản GA mới nhất của nhánh 5.0. Bài sử dụng bản đó làm mốc thực hành. Trước khi cài, kiểm tra [trang tải Cassandra chính thức](https://cassandra.apache.org/_/download.html) để xác nhận phiên bản mình đang dùng.

| Thành phần | Chọn cho bài này | Lưu ý |
|---|---|---|
| Cassandra | **5.0.9**, nhánh `5.0` | Container/tarball có thể chọn bản vá cố định; repository `50x` có thể cung cấp bản vá mới hơn |
| JDK chạy Cassandra trên Linux/VM | **OpenJDK 17**, hoặc Java 11 theo tài liệu Cassandra 5.0 | Kiểm tra `java -version` trên **đúng host/guest** đang chạy Cassandra |
| Python cho `cqlsh` ngoài container | Python 3 tương thích với bản Cassandra đã cài | Theo tài liệu cài đặt Cassandra 5.0, Python 3.8–3.13 được hỗ trợ cho `cqlsh` |
| Docker | Docker Engine hoặc Docker Desktop dùng Linux containers; Compose v2 nếu dùng file Compose | Docker Desktop trên Windows/macOS chạy container trong Linux VM |
| Java client | JDK 17 và Apache Cassandra Java Driver 4.x | JDK ứng dụng có thể khác JVM đang chạy server; test driver riêng |

Với APT/DNF, nhánh repo `50x` **không có nghĩa là cố định 5.0.9**. Sau khi cài, ghi lại **phiên bản gói thực tế**. Nếu cần tái lập bit-for-bit, dùng image có digest đã ghi nhận, tarball đã kiểm tra hash/signature, hoặc gói được cố định phiên bản trong kho riêng. Không dùng `latest` làm baseline.

### 3.2. Tài nguyên, cổng và yêu cầu chung

- Lab một node nên bắt đầu với **host khoảng 8 GiB RAM trở lên**, có CPU và SSD đủ chỗ; VM/container cần phần bộ nhớ riêng cho OS, off-heap, page cache, log và compaction. Đây là gợi ý học tập, **không phải sizing production**.
- Kiểm tra đường mạng và firewall. **9042/TCP** phục vụ CQL/Java driver; **7000/TCP** thường phục vụ trao đổi giữa node, **7001/TCP** có thể dành cho internode TLS theo cấu hình, **7199/TCP** thường là JMX của `nodetool`. Không tùy tiện mở 7199 ra mạng ngoài.
- Đồng bộ thời gian cho máy chủ và VM bằng NTP/chrony hoặc dịch vụ tương ứng; mutation timestamp của Cassandra ảnh hưởng quy tắc **last-write-wins**.
- Server cần phiên bản Java được **nhánh Cassandra** hỗ trợ. `cqlsh` cần Python phù hợp, nhưng **CQL server không chạy bằng Python**.
- Mặc định nhiều môi trường lab dùng kết nối **không bật authentication/TLS**. Chỉ truy cập từ loopback hoặc mạng lab cô lập; trước khi dùng mạng chung hay production phải cấu hình authentication, mã hóa, firewall, backup, monitoring và topology.

Trên Linux/guest, kiểm tra sơ bộ:

```bash
uname -a
java -version
python3 --version
free -h
df -h .
date -u
```

Trên Windows/macOS chạy Docker Desktop, kiểm tra **RAM/disk cấp cho Linux VM** bên cạnh tài nguyên vật lý. Việc máy Windows cài JDK 17 **không cho biết** JVM bên trong image Cassandra đang dùng phiên bản nào.

## 4. Cách A: cài gói DEB/APT trên Debian hoặc Ubuntu

Thực hiện **trong shell Linux** của máy hoặc VM Debian/Ubuntu, với tài khoản có `sudo`. Phần này minh họa repository Apache dành cho Cassandra nhánh 5.0; nếu có repo Cassandra cũ, xem lại để tránh lẫn các nhánh.

### 4.1. Cài phụ thuộc và đăng ký repository Apache

```bash
sudo apt-get update
sudo apt-get install -y openjdk-17-jre-headless python3 curl ca-certificates

java -version
python3 --version

sudo install -d -m 0755 /etc/apt/keyrings
sudo curl -fsSL https://downloads.apache.org/cassandra/KEYS \
  -o /etc/apt/keyrings/apache-cassandra.asc

echo "deb [signed-by=/etc/apt/keyrings/apache-cassandra.asc] https://debian.cassandra.apache.org 50x main" \
  | sudo tee /etc/apt/sources.list.d/cassandra.sources.list

sudo apt-get update
apt-cache policy cassandra
```

Trong phần này:

- `50x` là **nhánh Cassandra 5.0**, không phải số bản vá.
- `/etc/apt/keyrings/apache-cassandra.asc` là tập khóa ký dùng để xác thực gói từ repository Apache; không tắt kiểm tra chữ ký để giải quyết lỗi key.
- `apt-cache policy cassandra` cho biết phiên bản **Candidate** mà APT định cài và nguồn của nó. Nếu yêu cầu cố định chính xác 5.0.9, kiểm tra các version hiện có rồi chọn đúng chuỗi version trong công cụ quản lý gói; không giả định chuỗi là đúng `5.0.9` khi chưa xem metadata.
- Repository chính thức hiện dùng miền `debian.cassandra.apache.org`, thay cho nhiều URL cũ trong bài viết trước đây.

### 4.2. Cài, khởi động và xác nhận

```bash
sudo apt-get install -y cassandra
dpkg-query -W cassandra

# Tùy bản phân phối, service có thể tự khởi động khi cài:
sudo systemctl status cassandra --no-pager
sudo systemctl start cassandra

nodetool status
nodetool version
cqlsh -e "SELECT release_version, cluster_name, data_center FROM system.local;"
```

Nếu `systemctl status` báo service chưa chạy, xem log trước khi thử khởi động lại. Cassandra mất thời gian tạo system keyspace và tham gia ring; `systemctl start` kết thúc thành công chưa đảm bảo CQL đã sẵn sàng. Khi khỏe, `nodetool status` hiển thị **`UN`** (*Up/Normal*) cho node.

Vị trí chính cần ghi nhớ với gói DEB:

| Thành phần | Đường dẫn thường dùng |
|---|---|
| Cấu hình | `/etc/cassandra/cassandra.yaml` |
| Dữ liệu/commitlog | Các thư mục bên dưới `/var/lib/cassandra` |
| Log | `/var/log/cassandra/system.log`, các log khác cùng thư mục |
| Tùy chọn lúc khởi động | `/etc/default/cassandra` và các file cấu hình đi kèm package |
| Dịch vụ | `systemctl start/stop/status cassandra` |

Nếu muốn đổi `cluster_name`, topology, địa chỉ listen hoặc đường dẫn dữ liệu, hãy dừng node và sửa cấu hình **trước khi có dữ liệu nghiệp vụ**. Đổi `cluster_name` trên node đang chứa dữ liệu cần kiểm soát metadata và quy trình thay đổi; trong lab mới, dễ nhất là cấu hình đúng trước lần chạy đầu.

### 4.3. Log và vòng đời gói

```bash
sudo journalctl -u cassandra -n 100 --no-pager
sudo tail -n 100 /var/log/cassandra/system.log
sudo systemctl stop cassandra
sudo systemctl start cassandra
```

**Không tự xóa** `/var/lib/cassandra` để “cài lại cho sạch” khi còn dữ liệu cần giữ. Việc gỡ package và việc xóa data directory là hai thao tác khác nhau. Nếu triển khai thật, dùng backup/snapshot và quy trình nâng cấp trước khi đổi package; không để auto-upgrade tự chuyển phiên bản giữa các đợt thực hành cần tái lập.

## 5. Cách B: cài gói RPM bằng DNF trên hệ Linux họ RHEL

Ví dụ áp dụng cho bản phân phối tương thích RPM có `dnf` và `systemd` (như RHEL/AlmaLinux). Phiên bản hệ điều hành phải phù hợp với repository và JDK; vì cách đóng gói RPM của Cassandra có thể khác giữa các bản phân phối, cần kiểm tra package metadata trước khi cài.

### 5.1. Khai báo repository

```bash
sudo dnf install -y java-17-openjdk-headless python3 curl ca-certificates
java -version

sudo tee /etc/yum.repos.d/cassandra.repo >/dev/null <<'EOF'
[cassandra]
name=Apache Cassandra
baseurl=https://redhat.cassandra.apache.org/50x/
enabled=1
gpgcheck=1
repo_gpgcheck=1
gpgkey=https://downloads.apache.org/cassandra/KEYS
EOF

sudo dnf makecache
dnf --showduplicates list cassandra
```

Nếu môi trường đang dùng `yum`, sử dụng lệnh tương đương phù hợp với hệ điều hành. URL `redhat.cassandra.apache.org/50x/` là repository cho nhánh 5.0. Trên một số hệ cũ có thể cần cấu hình repository khác; **không sao chép tùy chọn dành cho CentOS 7** sang hệ hiện đại nếu không có yêu cầu tương thích.

### 5.2. Cài gói, quản lý service

```bash
sudo dnf install -y cassandra
rpm -q cassandra

sudo systemctl daemon-reload
sudo systemctl enable --now cassandra
sudo systemctl status cassandra --no-pager

nodetool status
nodetool version
cqlsh -e "SELECT release_version, cluster_name, data_center FROM system.local;"
```

Trong môi trường RPM, cấu hình, log và data thường theo quy ước hệ thống tương tự gói DEB, nhưng phải kiểm tra **đường dẫn thật trong package** và `cassandra.yaml` thay vì giả định mọi bản RPM giống nhau:

```bash
rpm -ql cassandra
sudo journalctl -u cassandra -n 100 --no-pager
```

Trang download Apache lưu ý các bản RPM chưa được thử đầy đủ trên mọi platform. Khi gặp lỗi dịch vụ, thu `rpm -q cassandra`, `java -version`, repository đang dùng, log và thông tin hệ điều hành trước khi báo lỗi hoặc đổi cách cài.

## 6. Cách C: tạo máy ảo Linux rồi cài Cassandra trong guest

VM thích hợp khi cần mô phỏng thao tác của một máy chủ độc lập: cấu hình hệ điều hành, dịch vụ, firewall, hostname, network, snapshot và lỗi mất node. VM cũng giúp thực hành nhiều node trong một mạng ảo, nhưng **ba VM cùng một host vật lý không phải ba failure domain độc lập**.

### 6.1. Tạo một VM cho lab

Có thể dùng VirtualBox, VMware, Hyper-V, KVM hoặc trình quản lý VM sẵn có. Ví dụ thông số ban đầu:

| Tài nguyên VM | Giá trị lab tham khảo |
|---|---|
| Guest OS | Một bản Ubuntu Server/Debian hoặc AlmaLinux/RHEL được hỗ trợ |
| vCPU | 2 vCPU |
| RAM | Khoảng 4 GiB cấp cho guest, đồng thời host còn RAM |
| Đĩa | SSD-backed virtual disk từ 20 GiB cho dữ liệu nhỏ, tăng khi học compaction/repair |
| Network | NAT để truy cập internet, hoặc bridged/host-only phù hợp mục tiêu; đảm bảo SSH và DNS |
| Thời gian | Bật đồng bộ thời gian trong guest; kiểm tra UTC/NTP |

Đây là cấu hình **thực hành nhỏ**, không phải chỉ tiêu vận hành production.

Sau khi cài guest OS:

```bash
hostnamectl
ip addr
ip route
df -h
free -h
timedatectl status
```

Tiếp theo, chạy **Cách A** nếu guest là Debian/Ubuntu, hoặc **Cách B** nếu guest thuộc họ RPM. Lệnh `apt`/`dnf` phải chạy **trong terminal của guest**, không chạy trên Windows/macOS host.

### 6.2. Phân biệt các kiểu mạng VM

```text
Laptop/host                       Máy ảo Linux
┌─────────────────┐               ┌───────────────────┐
│ IDE + Java      │               │ Cassandra :9042   │
│ cqlsh           │── SSH/VM NIC ─│ SSH :22           │
└─────────────────┘               └───────────────────┘
         NAT: guest có thể ra internet, host cần forwarding/tunnel
         Bridged: guest có IP riêng trên LAN, firewall phải cho phép
         Host-only: host và guest trao đổi trên mạng ảo riêng
```

Khi Cassandra trên guest chỉ lắng nghe `127.0.0.1:9042`, lệnh `cqlsh` **bên trong guest** có thể hoạt động trong khi máy host không kết nối trực tiếp. Có thể giữ CQL nội bộ rồi mở **SSH tunnel** từ host cho thử nghiệm `cqlsh`:

```bash
# Chạy ở terminal host; thay VM_IP và user bằng thông tin SSH thực tế.
ssh -N -L 9242:127.0.0.1:9042 student@VM_IP
```

Lệnh SSH này yêu cầu host **thực sự truy cập được SSH của guest**; nếu hypervisor dùng NAT cô lập, cần cấu hình chuyển tiếp cổng SSH hoặc dùng một NIC host-only/bridged phù hợp trước. Trong một terminal host khác, khi đã cài `cqlsh` ở host:

```bash
cqlsh 127.0.0.1 9242
```

Tunnel trên chỉ giải thích kết nối TCP cho **một node**. Java Driver khám phá topology và sử dụng địa chỉ node **quảng bá** qua metadata; để chạy ứng dụng Java ngoài VM ổn định, các endpoint mà driver phát hiện phải được định tuyến từ máy ứng dụng. Khi lab nhiều node, cần mạng cho phép ứng dụng truy cập **mọi node cần dùng**, không chỉ forward một cổng ngẫu nhiên.

Nếu chủ động cấu hình cho remote CQL qua một mạng lab tin cậy, phân biệt:

- `listen_address`: địa chỉ node dùng cho **giao tiếp internode/gossip**, không được đặt `0.0.0.0`.
- `rpc_address`: địa chỉ bind cho **native CQL**, có thể là interface guest hoặc `0.0.0.0`.
- `broadcast_rpc_address`: địa chỉ Cassandra báo cho **driver**, phải truy cập được từ ứng dụng và không được là `0.0.0.0`.
- `native_transport_port`: mặc định `9042`, phải được firewall và chính sách truy cập cho phép.

Ví dụ, trong mạng riêng, `listen_address: 192.168.56.10`, `rpc_address: 0.0.0.0` và `broadcast_rpc_address: 192.168.56.10` chỉ hợp lệ nếu đó **thật sự là IP của guest**, host/app định tuyến tới được và firewall đã cấu hình. Không sao chép địa chỉ ví dụ này nguyên xi. Với môi trường có dữ liệu và nhiều node, thay đổi listen/broadcast cần theo quy trình topology, không chỉnh tùy tiện rồi restart toàn cluster.

### 6.3. Snapshot VM và giới hạn của snapshot

Snapshot VM rất tiện để quay lại tình trạng **hệ điều hành sạch** trước khi thực hành. Tuy vậy, snapshot VM khi Cassandra đang ghi dữ liệu có thể không bảo đảm consistency của database trong tình huống thực; snapshot storage/hypervisor không thay thế kế hoạch backup/restore hay `nodetool snapshot`. Với lab chưa có dữ liệu, tắt Cassandra/VM trước snapshot giúp đơn giản hóa việc phục hồi.

## 7. Cách D: cài bằng Docker container

Đây là lựa chọn nhanh nhất để học CQL và kết nối Java trên Windows/macOS/Linux. Docker Engine phải chạy được Linux containers; trên Windows/macOS, Docker Desktop sử dụng một Linux VM. Container **không** tự lưu dữ liệu bền vững nếu dữ liệu chỉ nằm trong lớp ghi có thể bị xóa khi container bị xóa.

### 7.1. Khởi động một node bằng Docker CLI

Chạy trên host có Docker CLI:

```bash
docker version
docker pull cassandra:5.0.9
docker volume create cassandra_install_data

docker run -d --name cassandra-install-lab \
  -p 127.0.0.1:9042:9042 \
  -e CASSANDRA_CLUSTER_NAME=install-lab \
  -e CASSANDRA_ENDPOINT_SNITCH=GossipingPropertyFileSnitch \
  -e CASSANDRA_DC=datacenter1 \
  -e CASSANDRA_RACK=rack1 \
  -v cassandra_install_data:/var/lib/cassandra \
  cassandra:5.0.9
```

**Chú ý shell:** ví dụ đa dòng sử dụng dấu `\` của **Bash/Linux/macOS**. Nếu chạy trong **Windows PowerShell**, hãy viết toàn bộ `docker run ...` trên một dòng hoặc thay cách xuống dòng theo cú pháp PowerShell; đừng dán nguyên dấu `\` rồi mong PowerShell xử lý như Bash.

| Thành phần | Ý nghĩa |
|---|---|
| `cassandra:5.0.9` | Cố định phiên bản image cho bài học |
| `127.0.0.1:9042:9042` | Cổng CQL host 9042 chuyển đến cổng CQL container 9042, chỉ mở trên localhost |
| `CASSANDRA_CLUSTER_NAME` | Tên cluster lab, không phải tên container |
| `CASSANDRA_ENDPOINT_SNITCH` + `CASSANDRA_DC/RACK` | Cấu hình topology cho môi trường một datacenter |
| `cassandra_install_data:/var/lib/cassandra` | Named volume lưu dữ liệu qua các lần xóa/tạo lại container |

Nếu host đã có service Cassandra dùng 9042, dừng service/container cũ hoặc chọn host port khác, ví dụ `-p 127.0.0.1:9242:9042`. Khi đổi host port, `cqlsh` chạy **trên host** sẽ truy cập `9242`; `cqlsh` chạy **trong container** vẫn dùng cổng `9042`. Với Java Driver, còn cần kiểm tra endpoint Cassandra quảng bá qua metadata khi truy cập qua NAT.

### 7.2. Xác minh trạng thái thực

```bash
docker ps --filter name=cassandra-install-lab
docker logs cassandra-install-lab
docker exec cassandra-install-lab nodetool status
docker exec cassandra-install-lab nodetool version
docker exec cassandra-install-lab java -version
docker exec cassandra-install-lab cqlsh -e "SELECT release_version, cluster_name, data_center FROM system.local;"
```

Đợi đến khi `nodetool status` hiển thị node `UN`. Container đang ở trạng thái `Up` **chưa đồng nghĩa** Cassandra đã nhận CQL. Nếu `cqlsh` báo kết nối bị từ chối trong lúc khởi động, xem `docker logs` và thử lại sau khi node sẵn sàng.

Trạng thái dung lượng và volume:

```bash
docker stats --no-stream cassandra-install-lab
docker exec cassandra-install-lab sh -c "df -h /var/lib/cassandra"
docker volume inspect cassandra_install_data
```

Trên Docker Desktop, volume có thể nằm trong Linux VM, không xuất hiện như thư mục thông thường trên host. Dùng volume giúp dữ liệu Cassandra bền vững; **không** phải bản backup độc lập.

### 7.3. Docker Compose để giữ cấu hình dưới dạng mã

Nếu lab cần tạo lại nhiều lần, ghi nội dung sau vào một tệp **`compose.yaml` trong thư mục thực hành riêng của bạn** (đoạn dưới chỉ là minh họa cho người học, không phải file được tạo kèm bài):

```yaml
services:
  cassandra:
    image: cassandra:5.0.9
    container_name: cassandra-compose-lab
    environment:
      CASSANDRA_CLUSTER_NAME: compose-lab
      CASSANDRA_ENDPOINT_SNITCH: GossipingPropertyFileSnitch
      CASSANDRA_DC: datacenter1
      CASSANDRA_RACK: rack1
    ports:
      - "127.0.0.1:9042:9042"
    volumes:
      - cassandra_compose_data:/var/lib/cassandra

volumes:
  cassandra_compose_data:
```

Trong thư mục có `compose.yaml`, dùng:

```bash
docker compose up -d
docker compose ps
docker compose logs cassandra
docker compose exec cassandra nodetool status
docker compose exec cassandra cqlsh -e "SELECT release_version FROM system.local;"
docker compose down
```

`docker compose down` xóa container/network do Compose tạo nhưng **giữ named volume** mặc định. `docker compose down -v` **xóa cả volume** và dữ liệu thực hành trong đó. Không dùng `-v` khi cần lưu dữ liệu cho buổi học tiếp theo.

Các lệnh Docker CLI của mục 7.1 và Compose ở mục 7.3 là **hai cách thay thế** để dựng lab. Dùng một cách mỗi lần, vì chúng cùng đề nghị cổng host 9042 và sẽ xung đột nếu cùng chạy. Khi chuyển cách, xác nhận đúng tên container và volume; Docker Compose tự thêm tiền tố project vào tên volume nếu không cấu hình tên cố định.

### 7.4. Docker network và kết nối từ ứng dụng Java

```text
Ứng dụng chạy trên host            Cassandra container
127.0.0.1:9042  ────────────────►  9042 (CQL)

Ứng dụng chạy trong Docker network  Cassandra container
DNS service/container :9042 ─────►  9042 (CQL)
```

- Ứng dụng Java chạy trên host dùng endpoint **được publish trên host** (ví dụ `127.0.0.1:9042`).
- Ứng dụng Java chạy trong container riêng, **cùng Docker network**, thường dùng tên dịch vụ `cassandra` và cổng `9042`. `127.0.0.1` bên trong container Java là **container Java**, không phải Cassandra.
- Driver 4.x có cơ chế phát hiện node qua metadata. Các địa chỉ Cassandra **quảng bá** phải nằm trong phạm vi mạng ứng dụng truy cập được, đặc biệt với multi-node, NAT hoặc nhiều host. Cổng được publish có thể giúp client chạm tới contact point ban đầu nhưng **chưa chứng minh** mọi kết nối điều hướng tới node đều thành công.
- Với production hoặc cluster nhiều node, thiết kế seed, listen/broadcast RPC, DNS, firewall, replication theo topology thật. Không dùng nguyên mẫu container một node để đánh giá khả năng chịu lỗi phân tán.

## 8. Cách E (bổ sung): tarball nhị phân không cần package manager

Tarball thuận tiện trên Linux/guest khi muốn chạy **một phiên bản Cassandra cụ thể** dưới quyền người dùng mà không đăng ký repository. Nó không tự tạo service hệ điều hành hoặc tự quản lý nâng cấp/backup.

Ví dụ dùng Linux Bash:

```bash
java -version
python3 --version

curl -fLO https://dlcdn.apache.org/cassandra/5.0.9/apache-cassandra-5.0.9-bin.tar.gz
curl -fLO https://dlcdn.apache.org/cassandra/5.0.9/apache-cassandra-5.0.9-bin.tar.gz.sha512
curl -fLO https://dlcdn.apache.org/cassandra/5.0.9/apache-cassandra-5.0.9-bin.tar.gz.asc
curl -fLO https://downloads.apache.org/cassandra/KEYS

# So sánh đầu ra với chuỗi trong file .sha512:
sha512sum apache-cassandra-5.0.9-bin.tar.gz
cat apache-cassandra-5.0.9-bin.tar.gz.sha512

# Kiểm tra chữ ký bằng các khóa công bố trên website Apache:
gpg --import KEYS
gpg --verify apache-cassandra-5.0.9-bin.tar.gz.asc apache-cassandra-5.0.9-bin.tar.gz

tar -xzf apache-cassandra-5.0.9-bin.tar.gz
cd apache-cassandra-5.0.9
bin/cassandra -f
```

Lệnh `-f` chạy Cassandra ở **foreground** để quan sát log ngay; dùng một terminal thứ hai, vẫn trong thư mục tarball:

```bash
bin/nodetool status
bin/nodetool version
bin/cqlsh -e "SELECT release_version, cluster_name, data_center FROM system.local;"
```

Nếu 5.0.9 không còn trên mirror hiện hành, lấy đúng phiên bản từ [Apache Archive](https://archive.apache.org/dist/cassandra/5.0.9/) và vẫn kiểm tra checksum/chữ ký. Không bỏ qua sai checksum. Với tarball:

- `conf/cassandra.yaml`: file cấu hình.
- `bin/cassandra`, `bin/nodetool`, `bin/cqlsh`: lệnh chạy và quản trị.
- `data/`, `logs/`: thư mục dữ liệu/log của bản cài theo bố cục tarball.
- Vì không có service manager sẵn, nếu cần tiến trình sống qua logout/reboot phải tự thiết kế dịch vụ theo hệ điều hành; không dùng `nohup` làm giải pháp production mặc định.

Không cài cả tarball và package rồi trỏ vào **cùng một data directory**. Chạy hai Cassandra process truy cập cùng SSTable/commitlog là tình huống có thể làm hỏng dữ liệu.

## 9. Smoke test chung sau khi cài

Điều kiện đầu vào là một node đã báo `UN` và `cqlsh` kết nối thành công, bất kể bạn chọn cách cài nào.

### 9.1. Xác nhận cluster và datacenter

Trong `cqlsh`, chạy:

```sql
SELECT release_version, cluster_name, data_center, host_id
FROM system.local;
```

Ghi lại `release_version` và `data_center` thực tế; không mặc định datacenter luôn mang tên `datacenter1`. Có thể đọc thêm `nodetool describecluster` để kiểm tra tên cluster, snitch và schema versions.

### 9.2. Tạo keyspace và bảng theo partition key

Ví dụ dưới đây giả sử `data_center` trả về **`datacenter1`**. Nếu kết quả khác, hãy thay đúng tên datacenter trong replication map:

```sql
CREATE KEYSPACE IF NOT EXISTS installation_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'datacenter1': 1
};

CREATE TABLE IF NOT EXISTS installation_lab.events_by_device (
  device_id text,
  event_id timeuuid,
  event_type text,
  PRIMARY KEY ((device_id), event_id)
) WITH CLUSTERING ORDER BY (event_id DESC);

INSERT INTO installation_lab.events_by_device
  (device_id, event_id, event_type)
VALUES ('device-001', now(), 'installed');

SELECT device_id, event_id, event_type
FROM installation_lab.events_by_device
WHERE device_id = 'device-001'
LIMIT 10;
```

Ở đây `device_id` là **partition key**, quyết định phân vùng chứa các sự kiện của thiết bị; `event_id` là **clustering key**, cho phép sắp xếp bản ghi trong cùng partition. Truy vấn lọc theo partition key phù hợp mô hình Cassandra.

Ví dụ `NetworkTopologyStrategy` với RF=1 chỉ phục vụ **lab một node**. Nó **không có dự phòng replica** và không chứng minh được read/write consistency khi một node bị lỗi. Muốn học `LOCAL_QUORUM`, failure handling và repair có ý nghĩa, cần cluster nhiều node với replication factor thích hợp.

### 9.3. Kiểm tra kết nối ứng dụng Java

Với Apache Cassandra Java Driver 4.x, cấu hình cơ bản có dạng:

```java
import java.net.InetSocketAddress;
import com.datastax.oss.driver.api.core.CqlSession;

try (CqlSession session = CqlSession.builder()
        .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
        .withLocalDatacenter("datacenter1")
        .build()) {
    System.out.println(
        session.execute("SELECT release_version FROM system.local")
               .one().getString("release_version"));
}
```

Đoạn này là **phần thân của phương thức Java**, không phải tệp `.java` hoàn chỉnh. Cần thêm dependency `org.apache.cassandra:java-driver-core` phù hợp với JDK 17 và khai báo class/method khi chạy. Đổi contact point, port và local datacenter theo nơi app chạy:

| Vị trí ứng dụng | Endpoint tham khảo | Điều kiện |
|---|---|---|
| Cùng Linux host với package/tarball | `127.0.0.1:9042` | Cassandra bind native transport ở loopback |
| Trong cùng VM với Cassandra | `127.0.0.1:9042` | CQL server trong guest hoạt động |
| Host kết nối Docker đã publish port 9042 | `127.0.0.1:9042` | Port mapping đúng, node quảng bá địa chỉ truy cập được |
| Ứng dụng cùng Docker Compose network | `cassandra:9042` | Tên dịch vụ DNS resolve được, metadata endpoint phù hợp |
| Host kết nối VM qua NAT hoặc bridged | IP/port thực tế hoặc SSH tunnel | Firewall, listener và địa chỉ broadcast phù hợp với driver |

**Kết nối TCP tới 9042 chưa đủ:** kết quả `nodetool status=UN`, `cqlsh` thành công, Java driver đọc được `system.local` và truy vấn keyspace thực tế là các mức kiểm tra khác nhau.

## 10. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| APT không tìm thấy package hoặc lỗi `NO_PUBKEY` | Repo `50x` sai URL, key chưa tải đúng, dùng hướng dẫn cũ | Kiểm tra `/etc/apt/sources.list.d/cassandra.sources.list`, `apt-cache policy`, KEYS chính thức; không vô hiệu GPG |
| DNF báo lỗi repository hoặc GPG | `baseurl` cũ/sai nhánh, bản distro không tương thích, mạng không truy cập repo | Xem `dnf repolist`, `dnf --showduplicates list cassandra`, file `cassandra.repo` và log |
| Cassandra không khởi động vì Java | JVM không phù hợp nhánh 5.0, biến `JAVA_HOME` sai | `java -version` trên **đúng môi trường**, kiểm tra service log và cấu hình Java |
| `cqlsh` lỗi Python module/version | Python của cqlsh thiếu hoặc không tương thích | Dùng Python phiên bản được bản Cassandra hỗ trợ; kiểm tra cách `cqlsh` được cài cùng gói |
| `systemctl status` báo running, nhưng `cqlsh` bị từ chối | Cassandra còn khởi tạo hoặc listener chưa mở | Đọc `system.log`, thử `nodetool status`, kiểm tra `ss -lntp` trên Linux |
| Docker container chạy rồi thoát | RAM không đủ, OOM, volume permission, lỗi JVM/config | `docker logs`, `docker inspect`, RAM của host/VM, quyền volume |
| `Bind for 0.0.0.0:9042 failed` | Port 9042 trên host đã có process/container sử dụng | `docker ps`, `ss -lntp` (Linux), đổi mapping host port hoặc dừng lab cũ |
| VM guest chạy CQL nhưng host không thấy cổng | VM dùng NAT, firewall chặn, Cassandra chỉ bind loopback | Kiểm tra mode mạng, guest IP, `rpc_address` và cổng; SSH tunnel hoặc cấu hình mạng phù hợp |
| Java driver `NoNodeAvailableException` sau khi bắt tay | Contact point chỉ tiếp cận được qua NAT nhưng node broadcast IP không route được | Kiểm tra `broadcast_rpc_address`, topology endpoints, DNS, firewall từ **máy ứng dụng** |
| Driver báo sai local datacenter | Tên truyền vào `withLocalDatacenter` không khớp `system.local.data_center` | Truy vấn DC thực, sửa đúng chữ hoa/thường; không đoán |
| CQL hoạt động nhưng dữ liệu biến mất sau khi xóa container | Không gắn volume hoặc đã dùng `docker compose down -v` | Dùng named volume và backup có kiểm chứng; không xem container layer là nơi lưu bền vững |
| Disk full, compaction/repair không chạy | Không đủ dung lượng khi tạo SSTable mới, commitlog hoặc snapshot | Kiểm tra `df -h` tại data directory/volume, tăng dung lượng; không xóa SSTable thủ công |
| Gắn data directory cũ vào phiên bản server khác rồi lỗi | Sai đường nâng/hạ phiên bản, dữ liệu/system tables không tương thích | Theo upgrade guide chính thức và bản backup; không downgrade dữ liệu tùy ý |

Các cách lấy bằng chứng khác nhau:

```text
APT/RPM    → systemctl status cassandra; journalctl -u cassandra;
             /var/log/cassandra/system.log; nodetool status
Tarball    → logs/system.log; bin/nodetool status; bin/cqlsh
VM         → log của guest + ip/route/firewall trên guest + mạng host/guest
Docker     → docker logs; docker stats; docker exec ... nodetool status
Compose    → docker compose logs cassandra; docker compose ps
```

Luôn thu **phiên bản Cassandra, Java, OS, trạng thái node, log và đường mạng ứng dụng→node** trước khi thay đổi cấu hình. Một lỗi port không liên quan đến partition key; ngược lại, một query thất bại vì thiếu partition key có thể xảy ra dù cài đặt hoàn toàn đúng.

## 11. Giữ dữ liệu, dọn môi trường và chuyển phương án cài

| Phương án | Dữ liệu thường ở đâu? | Thao tác dừng | Điều tránh làm |
|---|---|---|---|
| DEB/RPM | `/var/lib/cassandra` hoặc đường dẫn trong `cassandra.yaml` | `sudo systemctl stop cassandra` | Không xóa dữ liệu chỉ để khắc phục lỗi package |
| VM | Trong đĩa ảo của guest | Dừng Cassandra rồi shutdown guest | Không coi VM snapshot đang ghi là bản backup CQL đã được kiểm thử |
| Docker CLI | Named volume `cassandra_install_data` | `docker stop cassandra-install-lab` | Không `docker volume rm` khi cần dữ liệu |
| Docker Compose | Named volume của project Compose | `docker compose down` | Không `docker compose down -v` nếu muốn giữ dữ liệu |
| Tarball | Thư mục `data/` hoặc đường dẫn tùy chỉnh trong cấu hình | Dừng process qua cơ chế điều khiển tương ứng | Không chạy hai process dùng cùng data directory |

Với container CLI của mục 7.1, có thể dừng và tạo lại với cùng named volume:

```bash
docker stop cassandra-install-lab
docker rm cassandra-install-lab
docker volume ls --filter name=cassandra_install_data
```

Việc xóa **container** không đồng nghĩa xóa **volume**. Khi tạo lại, ghi đúng image version, cluster identity và cấu hình cần thiết. Nếu chuyển từ package/VM sang container, **không chép trực tiếp data directory** rồi mong một node mới với topology khác hoạt động. Chuyển dữ liệu phải đi qua kế hoạch hợp lệ như backup/restore đã kiểm chứng, `sstableloader` khi phù hợp, hoặc cơ chế streaming/migration phù hợp với phiên bản và schema.

## 12. Bài tập tự kiểm tra và tiêu chí đạt

1. Một bạn chạy `cqlsh` thành công trong Docker nhưng ứng dụng Java từ host thất bại. Hãy nêu thứ tự kiểm tra port mapping, listener, local datacenter và địa chỉ node được quảng bá.
2. Cùng yêu cầu giữ đúng Cassandra 5.0.9, vì sao `apt install cassandra` từ repo `50x` chưa đủ để bảo đảm version chính xác? Cách nào giúp cố định bản dùng cho lab?
3. Trên Windows, lệnh `java -version` là Java 17, nhưng Cassandra chạy trong container. Lệnh nào xác nhận JVM **thực sự bên trong Cassandra container**?
4. Bạn dùng Docker Compose rồi chạy `down -v`. Lần sau tạo lại container, dữ liệu trong keyspace lab còn không? Khác gì với `down`?
5. Trong VM NAT, `cqlsh` ở guest thành công nhưng host không kết nối tới `VM_IP:9042`. Hãy phân biệt NAT/SSH tunnel với việc cấu hình Cassandra bind/broadcast.
6. Tại sao phải kiểm tra `nodetool status` bên cạnh `systemctl status` hoặc `docker ps`? `UN` có tự chứng minh replication và repair đều khỏe không?
7. Một người có ba VM Cassandra trên cùng laptop rồi rút nguồn laptop. Mô hình đó đã kiểm chứng khả năng chịu lỗi ba máy vật lý độc lập chưa? Giải thích giới hạn thử nghiệm.
8. Một bảng sử dụng `PRIMARY KEY ((device_id), event_id)`. Lý do cần truy vấn theo `device_id` là gì, và nó liên quan thế nào đến phân phối dữ liệu giữa các node?

**Tiêu chí hoàn thành:** người học chọn được **một** phương án cài, ghi nhận đúng phiên bản gói/image/tarball, đọc được `system.local`, thấy trạng thái `UN`, chạy được các lệnh tạo bảng/ghi/đọc, xác định được nơi lưu dữ liệu và log, đồng thời mô tả chính xác endpoint cho `cqlsh` và ứng dụng Java. Đây là nền tảng để chuyển sang các lab nhiều node về replication, consistency level, compaction, repair và xử lý sự cố.

## 13. Nguồn tham khảo chính thức

- [Apache Cassandra — Download](https://cassandra.apache.org/_/download.html): bản phát hành, repository DEB/RPM `50x`, khóa ký và hướng dẫn cài package.
- [Apache Cassandra 5.0 — Installing Cassandra](https://cassandra.apache.org/doc/latest/cassandra/installing/installing.html): điều kiện Java/Python, Docker, tarball và package.
- [Apache Cassandra — Configuration reference](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html): `listen_address`, `rpc_address`, `broadcast_rpc_address`, `native_transport_port`.
- [Apache Cassandra — Quickstart](https://cassandra.apache.org/doc/stable/cassandra/getting-started/cassandra-quickstart.html): node, CQL và hướng dẫn khởi động nhanh.
- [Docker Hub — Official Cassandra image](https://hub.docker.com/_/cassandra): biến môi trường và cách chạy container.
- [Docker Docs — Compose file reference](https://docs.docker.com/reference/compose-file/): cú pháp `compose.yaml` và volume.
- [Docker Docs — Storage volumes](https://docs.docker.com/engine/storage/volumes/): vòng đời và khả năng lưu bền vững của named volume.
- [Apache Cassandra Java Driver](https://github.com/apache/cassandra-java-driver): cấu hình session và local datacenter cho client Java.
