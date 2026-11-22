# Chuẩn bị CPU, RAM, đĩa, hệ điều hành và đồng bộ thời gian

## 1. Mục tiêu và ý nghĩa đối với Cassandra

Apache Cassandra là cơ sở dữ liệu **wide-column phân tán**. Mỗi node đồng thời xử lý truy vấn CQL, ghi commit log, giữ dữ liệu trong memtable, flush thành SSTable, compact SSTable và trao đổi dữ liệu với các replica. Vì vậy, chuẩn bị môi trường không chỉ là “cài được database”: CPU, RAM, dung lượng đĩa, hệ điều hành và đồng hồ hệ thống đều ảnh hưởng đến việc học **partition key, thiết kế bảng theo truy vấn, replication, consistency level, compaction, repair, xử lý lỗi và kết nối bằng Java**.

Kết thúc bài học, bạn có thể:

1. Chọn tài nguyên phù hợp cho lab một node và cho lab nhiều node; phân biệt chúng với yêu cầu production.
2. Giải thích CPU được dùng ở đâu, RAM được chia cho heap/off-heap/page cache ra sao và vì sao Cassandra cần đĩa trống khi compaction/repair.
3. Kiểm tra tài nguyên trên Linux, Windows/macOS dùng Docker và trong container.
4. Tạo một node Cassandra 5.0.9 với giới hạn tài nguyên, volume dữ liệu và thao tác xác minh.
5. Xác minh đồng bộ thời gian giữa host/VM/container, giải thích tác động của lệch giờ lên quy tắc **last-write-wins**.
6. Chẩn đoán lỗi thiếu CPU, OOM, đĩa đầy và thời gian hệ thống lệch.

> **Giới hạn lab:** hướng dẫn dưới đây sử dụng Docker và một node để kiểm chứng tài nguyên. Nó không thay thế việc đo hiệu năng, tính dung lượng, thiết kế failure domain và lựa chọn phần cứng cho cluster sản xuất.

## 2. Chọn cấu hình phần cứng theo mục đích

### 2.1. Mốc tham khảo

| Môi trường | CPU tham khảo | RAM tham khảo | Đĩa và mục tiêu |
|---|---|---|---|
| **Lab 1 node** | Host có ít nhất khoảng 2–4 luồng CPU có thể sử dụng; thử cấp tối đa 2 CPU cho container | Host từ **8 GiB**; container thử cấp **4 GiB**; máy 16 GiB thuận tiện nếu chạy IDE Java | SSD còn **20 GiB trở lên** để chứa image, volume, log và dữ liệu nhỏ |
| **Lab 3 node cùng máy** | Khoảng 6 luồng CPU trở lên để các node đỡ tranh tài nguyên; thực tế có thể chia sẻ CPU | Host **24 GiB trở lên** thuận tiện khi cấp 4 GiB mỗi node và dành RAM cho OS/Java/Docker | SSD còn **60 GiB trở lên** cho dữ liệu lab và thao tác streaming/compaction |
| **Production, mỗi node** | Tài liệu Apache đưa mốc tối thiểu **2 core**, các hệ thống thường sử dụng **8 core trở lên** | Mốc tối thiểu **8 GiB**, hệ thống điển hình thường **32 GiB trở lên** | Thiết kế theo kích thước dữ liệu, RF, tốc độ tăng trưởng, throughput, IOPS, compaction, repair và dự phòng |

Các con số **lab** là **mức gợi ý để bắt đầu**, không phải mức tối thiểu được Apache bảo đảm. Máy có ít RAM vẫn có thể khởi chạy Cassandra cho mục đích thử nghiệm nhưng dễ OOM hoặc phải chờ rất lâu. Ngược lại, lấy cấu hình của lab làm sizing production là không an toàn. Apache nêu các mốc **production** trong tài liệu [Hardware Choices](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/hardware.html); sizing thực tế phải dựa trên benchmark và tính chất truy vấn.

**Phân biệt ba lớp tài nguyên:**

```text
Máy vật lý / host OS: CPU, RAM, SSD, đồng hồ hệ thống
  └── Docker Engine hoặc máy ảo Docker Desktop (Windows/macOS)
        └── Cassandra container: quota CPU / limit bộ nhớ
              ├── JVM heap + off-heap + bộ nhớ tiến trình
              └── /var/lib/cassandra: commitlog, SSTable, caches, hints
```

Trên Linux, container chia sẻ kernel với host. Trên Windows/macOS, Docker Desktop thường chạy Linux container trong một máy ảo; **RAM và đĩa cấp cho VM** có thể nhỏ hơn tổng RAM/đĩa vật lý. `docker stats` chỉ cho biết tài nguyên container, không chứng minh host hoặc VM còn đủ dung lượng cho mọi thao tác.

Một **cluster 3 node cùng một laptop** giúp thực hành consistency level và replication logic, nhưng khi laptop tắt thì cả 3 node cùng tắt: đó không phải 3 failure domain độc lập.

### 2.2. Ghi kết quả trước khi cài Cassandra

Nếu dùng **Linux**, chạy trên host:

```bash
uname -srm
nproc
free -h
df -h .
date -u +"%Y-%m-%dT%H:%M:%SZ"
```

Nếu dùng **Windows PowerShell**:

```powershell
Get-CimInstance Win32_Processor | Select-Object NumberOfLogicalProcessors
Get-CimInstance Win32_ComputerSystem | Select-Object TotalPhysicalMemory
Get-PSDrive -PSProvider FileSystem
wsl --status
[DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
```

Nếu dùng **macOS**, các lệnh cơ bản là:

```bash
sw_vers
sysctl -n hw.logicalcpu
sysctl -n hw.memsize
df -h .
date -u +"%Y-%m-%dT%H:%M:%SZ"
```

`TotalPhysicalMemory` và `hw.memsize` trả **byte**; cần quy đổi về GiB khi lập bảng. `df -h .` cho biết filesystem chứa **thư mục hiện tại**, có thể khác nơi Docker thực sự lưu image/volume. Trên Docker Desktop, kiểm tra thêm dung lượng và cấu hình VM/đĩa trong Docker Desktop; nếu dùng WSL2, xác nhận máy ảo WSL2 hoạt động.

## 3. CPU: dành tài nguyên cho cả truy vấn lẫn công việc nền

Cassandra xử lý nhiều yêu cầu song song. Khi viết dữ liệu, node ghi commitlog và cập nhật memtable; khi đọc, nó truy cập memtable/SSTable và xử lý kết quả. Còn có các tác vụ nền tiêu thụ CPU đáng kể:

| Tác vụ | Vì sao cần CPU | Dấu hiệu khi bị thiếu CPU |
|---|---|---|
| Xử lý CQL và định tuyến theo partition key | Phân tích request, phối hợp với replica và xử lý kết quả | Latency p95/p99 tăng; request timeout |
| Flush và **compaction** | Ghi, nén/giải nén, merge SSTable | Pending compaction tăng, I/O cao |
| Repair và streaming | So sánh/trao đổi dữ liệu giữa node, xử lý checksum | Repair kéo dài, ảnh hưởng độ trễ truy vấn |
| JVM garbage collection | Thu hồi bộ nhớ Java | GC pause tăng khi CPU cạnh tranh |
| Driver/ứng dụng Java | Thread/event loop, serialization, xử lý response | Ứng dụng chậm dù Cassandra chưa quá tải |

Trong Docker, `--cpus=2` nghĩa là container chỉ được tiêu thụ tối đa khoảng **hai CPU tương đương thời gian xử lý** theo quota, **không có nghĩa** hai core riêng được cấp độc quyền. `--cpuset-cpus` mới là tùy chọn gắn process vào danh sách CPU cụ thể, thường không cần thiết cho bài lab.

Các bước quan sát hữu ích:

```bash
# Sau khi tạo container ở mục 6:
docker stats --no-stream cassandra-resources-lab
docker exec cassandra-resources-lab nodetool tpstats
docker exec cassandra-resources-lab nodetool compactionstats
```

`nodetool tpstats` giúp xem thread pool/queue; `compactionstats` giúp xem tác vụ compaction đang chạy hoặc chờ. Không vội kết luận “CQL chậm vì thiếu CPU” chỉ từ một mẫu `docker stats`: cần xem thêm I/O, bộ nhớ, truy vấn, mức cạnh tranh và GC.

## 4. RAM: JVM heap chỉ là một phần bộ nhớ Cassandra dùng

Sơ đồ đơn giản:

```text
RAM cấp cho node/container
├─ Java heap (Xmx): object, cấu trúc quản lý trong JVM
├─ Off-heap/native: bloom filter, metadata nén, direct buffer...
├─ Bộ nhớ cho thread, JVM và thư viện native
└─ Bộ nhớ hệ điều hành / page cache: tăng tốc đọc SSTable trên đĩa
```

**Không được cấp toàn bộ RAM làm heap.** Apache hướng dẫn heap production thường **ít nhất 2 GiB** và **không vượt 50% RAM của node**; phần còn lại phục vụ off-heap, page cache và OS. Giá trị phù hợp phụ thuộc phiên bản Cassandra, GC, kích thước dataset và cách chạy. Ví dụ giới hạn container **4 GiB** và heap **2 GiB** chỉ là cấu hình khởi đầu để học; không bảo đảm đủ cho workload lớn.

Những điểm cần nhớ:

- Java trên host để chạy **ứng dụng Java/driver** là một tiến trình riêng; JVM của Cassandra chạy bên trong container nếu dùng image Docker.
- `--memory=4g` là **giới hạn bộ nhớ container**, không chỉ giới hạn Java heap. Tổng heap, off-heap, native memory và các khoản phát sinh vẫn phải nằm trong giới hạn đó.
- `MAX_HEAP_SIZE=2G` là biến cấu hình heap được Cassandra trong image hỗ trợ. Khi sử dụng G1GC, không tùy tiện đặt `HEAP_NEWSIZE` vì tùy chọn đó gắn với cách cấu hình GC khác.
- `--memory-swap=4g` cùng `--memory=4g` làm container không có phần swap thêm theo cơ chế giới hạn Docker. Điều này tránh swap chậm trong lab nhưng khiến lỗi OOM xuất hiện nếu bộ nhớ cấp không đủ; cần theo dõi và cấp thêm RAM khi cần.
- Tăng heap quá lớn có thể giảm RAM cho page cache và làm GC nặng hơn. Đừng chữa mọi lỗi bộ nhớ bằng cách tăng `-Xmx`.

Khi node đang chạy:

```bash
docker stats --no-stream cassandra-resources-lab
docker exec cassandra-resources-lab nodetool info
docker inspect --format "{{.HostConfig.Memory}}" cassandra-resources-lab
docker inspect --format "{{.State.OOMKilled}}" cassandra-resources-lab
```

`HostConfig.Memory` hiển thị **byte**; `OOMKilled=true` cho thấy trạng thái container từng bị kernel kết thúc vì OOM ở lần chạy hiện tại. Nếu container còn chạy, hãy xem `docker logs` và `docker stats`; nếu container đã dừng, đọc `docker inspect` và log để xác minh, không đoán nguyên nhân chỉ từ việc process biến mất.

## 5. Đĩa: tính cả commitlog, SSTable, compaction và repair

### 5.1. Tại sao “đủ chỗ chứa dữ liệu” vẫn chưa đủ?

Trong quá trình ghi:

1. Cassandra append dữ liệu vào **commitlog** và cập nhật **memtable**.
2. Memtable được flush thành **SSTable bất biến** trên đĩa.
3. Các SSTable được **compaction**: ghi SSTable mới trước khi các SSTable cũ có thể được thu hồi.
4. Repair, bootstrap/streaming, snapshot và thay đổi compaction strategy có thể cần thêm I/O hoặc dung lượng tạm.

Vì SSTable bất biến, **UPDATE/DELETE không ghi đè ngay file cũ**; bản ghi cũ và tombstone có thể còn tồn tại cho đến khi điều kiện dọn dẹp và compaction thích hợp được đáp ứng. Lúc compaction, dữ liệu cũ và mới có thể cùng chiếm đĩa một thời gian. Node còn trống vài gigabyte nhưng có dữ liệu đang cần rewrite lớn vẫn có nguy cơ đầy đĩa.

| Vùng dữ liệu | Vai trò | Điều cần chú ý |
|---|---|---|
| `data_file_directories`, mặc định dưới `/var/lib/cassandra/data` trong image | SSTable, các thành phần lưu trữ dữ liệu | Dung lượng tăng theo số bản sao, nén, tombstone, compaction |
| `commitlog_directory`, mặc định `/var/lib/cassandra/commitlog` | Khôi phục các ghi chưa flush khi node khởi động lại | Ghi tuần tự, cần I/O ổn định |
| `saved_caches_directory`, mặc định dưới `/var/lib/cassandra/saved_caches` | Các cache được lưu ra đĩa | Không thay thế page cache của OS |
| Hints, log, snapshot | Hỗ trợ vận hành và phục hồi | Có thể phát sinh chi phí đĩa ngoài dung lượng SSTable đang phục vụ |

Tài liệu phần cứng Apache khuyến nghị thiết bị lưu trữ có hiệu năng tốt; tránh mặc định coi **NFS/SAN** là nơi lưu dữ liệu lý tưởng cho Cassandra. Trong hệ thống thực, SSD/NVMe, filesystem ổn định như XFS/ext4 trên Linux và giám sát **latency/IOPS** thường quan trọng hơn chỉ nhìn thông số GB. Nếu có nhiều HDD vật lý, cân nhắc tách commitlog và SSTable để tránh tranh cơ học, theo hướng dẫn phần cứng và mô hình triển khai cụ thể.

### 5.2. Ví dụ tính dung lượng sơ bộ

Giả sử hệ thống có **12 GiB dữ liệu vật lý sau nén cho một bản sao**, replication factor `RF=3` và **3 node cân bằng** trong một datacenter:

```text
Dung lượng bản sao toàn cluster ≈ 12 GiB × 3 = 36 GiB
Dung lượng dữ liệu nền mỗi node ≈ 36 GiB / 3 = 12 GiB
```

Nếu dự trù ví dụ thêm **12 GiB/node** cho tăng trưởng và các thao tác tạm, ta có mức **24 GiB/node** trước khi cộng phần commitlog/log/snapshot khác. Đây **không phải** công thức dự trù chính thức: độ lệch phân vùng, compression, index, TTL, tombstone, các strategy như LCS/TWCS/UCS, repair và backup có thể thay đổi đáng kể dung lượng thực tế. Production phải đo dữ liệu thực, mô hình tăng trưởng và các tình huống xấu nhất.

Khi vận hành, kiểm tra:

```bash
docker exec cassandra-resources-lab sh -c "df -h /var/lib/cassandra"
docker exec cassandra-resources-lab sh -c "du -sh /var/lib/cassandra/data /var/lib/cassandra/commitlog"
docker exec cassandra-resources-lab nodetool compactionstats
docker system df
```

`df -h` báo mức trống của filesystem chứa volume; `du -sh` báo kích thước thư mục hiện tại. `docker system df` phản ánh cả image/container/cache/volume Docker và **không tương đương** với mức trống của một filesystem gắn vào Cassandra. Đừng xóa SSTable hay commitlog bằng tay chỉ vì thấy đĩa gần đầy: có thể làm hỏng hoặc mất dữ liệu.

### 5.3. Chọn volume để không mất dữ liệu khi tạo lại container

Ví dụ lab sử dụng **Docker named volume**:

```bash
docker volume create cassandra_resources_data
```

Khi chạy Cassandra, gắn `-v cassandra_resources_data:/var/lib/cassandra`. Named volume giúp giữ dữ liệu sau khi dừng/xóa container **miễn là không xóa volume**. Nếu máy chủ Windows/macOS dùng Docker Desktop, ưu tiên volume Linux của Docker cho I/O của database; bind mount vào thư mục Windows/macOS có thể mang đặc tính filesystem và hiệu năng khác.

## 6. Chuẩn bị hệ điều hành và khởi động lab có giới hạn tài nguyên

### 6.1. Những điểm cần kiểm tra trước

- **Linux:** kernel và Docker Engine hoạt động, user được phép chạy Docker; kiểm tra `df`, RAM, cgroup và quyền trên nơi chứa dữ liệu. Với máy Linux thực chạy nhiều node, cần rà soát ulimit/file descriptor, swap, filesystem, network và các khuyến nghị production riêng.
- **Windows:** chạy **Linux containers** qua Docker Desktop (thường dùng WSL2). Kiểm tra đã bật virtualization, WSL2/VM có đủ RAM/đĩa và Docker Engine hoạt động; Windows container không phải môi trường cho image Linux này.
- **macOS:** dùng Docker Desktop với Linux VM, kiểm tra memory/disk resource của VM và kiến trúc image tương thích CPU.
- **Trong mọi môi trường:** cổng host `9142` còn trống; Docker có khả năng tải `cassandra:5.0.9`; không dùng máy đang phục vụ workload production để thử giới hạn gây OOM.

Lệnh kiểm tra Docker từ terminal host (PowerShell hoặc shell):

```bash
docker version
docker info
docker image inspect cassandra:5.0.9
```

Nếu image chưa có, lệnh `docker image inspect` sẽ báo chưa tìm thấy; tải trước:

```bash
docker pull cassandra:5.0.9
```

### 6.2. Chạy node riêng cho bài này

Để tránh xung đột cổng `9042` của lab khác, ví dụ này ánh xạ **9142 trên host → 9042 trong container**. Lệnh một dòng chạy được từ PowerShell, Bash hoặc terminal có Docker CLI:

```bash
docker run -d --name cassandra-resources-lab --cpus=2 --memory=4g --memory-swap=4g -e MAX_HEAP_SIZE=2G -e CASSANDRA_CLUSTER_NAME=resources-lab -e CASSANDRA_ENDPOINT_SNITCH=GossipingPropertyFileSnitch -e CASSANDRA_DC=datacenter1 -e CASSANDRA_RACK=rack1 -p 127.0.0.1:9142:9042 -v cassandra_resources_data:/var/lib/cassandra cassandra:5.0.9
```

Ý nghĩa:

| Tham số | Tác dụng |
|---|---|
| `--cpus=2` | Giới hạn tổng thời gian sử dụng CPU tương đương 2 CPU |
| `--memory=4g` | Giới hạn RAM container, bao gồm nhiều loại bộ nhớ ngoài heap |
| `--memory-swap=4g` | Không cấp thêm swap cho container ngoài RAM giới hạn |
| `MAX_HEAP_SIZE=2G` | Chọn JVM heap 2 GiB cho thí nghiệm, vẫn chừa không gian cho native/off-heap/page cache |
| `-p 127.0.0.1:9142:9042` | Ứng dụng trên host dùng `127.0.0.1:9142`, trong container vẫn dùng `9042` |
| `-v ...:/var/lib/cassandra` | Lưu dữ liệu vào named volume |
| `CASSANDRA_DC=datacenter1` và snitch | Định danh datacenter để thực hành topology/driver Java |

Lệnh giả định máy đã có **ít nhất 4 GiB RAM thực cấp cho Docker/container** và vẫn còn RAM cho host. Nếu không đủ, **cấp thêm bộ nhớ cho Docker VM/host** trước khi thử lại; không đặt heap quá lớn hoặc hạ giới hạn container đến mức node liên tục OOM.

### 6.3. Kiểm chứng node và tài nguyên

```bash
docker ps --filter name=cassandra-resources-lab
docker logs cassandra-resources-lab
docker stats --no-stream cassandra-resources-lab
docker exec cassandra-resources-lab nodetool status
docker exec cassandra-resources-lab nodetool info
docker exec cassandra-resources-lab cqlsh -e "SELECT release_version, data_center, cluster_name FROM system.local;"
```

Chờ tới khi `nodetool status` cho node ở trạng thái **`UN`** (*Up/Normal*). `docker run -d` thành công **chưa đồng nghĩa** Cassandra đã sẵn sàng cho CQL. `cqlsh` chạy **bên trong container** dùng cổng mặc định `9042`; chương trình Java chạy trên host sẽ dùng `127.0.0.1:9142` và local datacenter `datacenter1`.

Để xem dung lượng volume mà Cassandra nhìn thấy:

```bash
docker exec cassandra-resources-lab sh -c "df -h /var/lib/cassandra"
docker volume inspect cassandra_resources_data
```

`docker volume inspect` cho biết metadata/mountpoint theo Docker Engine; với Docker Desktop, mountpoint thuộc máy ảo Linux, không nhất thiết là đường dẫn Windows/macOS mà bạn truy cập trực tiếp được.

### 6.4. Kiểm tra ảnh hưởng của flush lên đĩa

Chạy một tập CQL nhỏ để có dữ liệu quan sát:

```bash
docker exec cassandra-resources-lab cqlsh -e "CREATE KEYSPACE IF NOT EXISTS resource_lab WITH replication = {'class':'SimpleStrategy', 'replication_factor':1};"
docker exec cassandra-resources-lab cqlsh -e "CREATE TABLE IF NOT EXISTS resource_lab.events_by_user (user_id text, event_id timeuuid, payload text, PRIMARY KEY ((user_id), event_id));"
docker exec cassandra-resources-lab cqlsh -e "INSERT INTO resource_lab.events_by_user (user_id, event_id, payload) VALUES ('u-1', now(), 'demo');"
docker exec cassandra-resources-lab cqlsh -e "SELECT * FROM resource_lab.events_by_user WHERE user_id='u-1';"
docker exec cassandra-resources-lab nodetool flush resource_lab events_by_user
docker exec cassandra-resources-lab nodetool tablestats resource_lab
docker exec cassandra-resources-lab sh -c "du -sh /var/lib/cassandra/data /var/lib/cassandra/commitlog"
```

`flush` chủ động chuyển memtable sang SSTable để minh họa cơ chế lưu trữ. Lượng dữ liệu mẫu rất nhỏ nên thay đổi dung lượng có thể bị làm tròn, không phù hợp để đo throughput hay dự đoán kích thước production. Keyspace `SimpleStrategy` với RF=1 được dùng **chỉ cho lab một node**; khi triển khai nhiều node và phân tán theo rack/datacenter, cần học và sử dụng `NetworkTopologyStrategy` phù hợp.

## 7. Đồng bộ thời gian: yêu cầu về tính đúng đắn dữ liệu

### 7.1. Tại sao Cassandra cần đồng hồ chính xác?

Cassandra gắn **mutation timestamp** cho các thay đổi và giải quyết xung đột bằng cơ chế **last-write-wins**: giữa các giá trị cạnh tranh của cùng một cell, timestamp lớn hơn thường được ưu tiên. Timestamp có thể do **client chỉ định**, hoặc được tạo ở **coordinator** khi client không đưa ra. Vì thế:

- Nếu đồng hồ node A chạy **nhanh**, một write từ A có thể có timestamp lớn hơn write mới hơn theo thời gian thực đến từ node B.
- Dữ liệu ghi sau ở B nhưng có timestamp nhỏ hơn có thể không thắng xung đột như người học mong đợi.
- Lệch giờ có thể làm các tình huống liên quan tới TTL, expiration, tombstone, log và chẩn đoán sự cố trở nên khó hiểu.
- **Replication factor** và **consistency level** không tự sửa được timestamp sai từ nguồn; đồng bộ giờ là phần thiết yếu của việc bảo đảm hành vi dự kiến.

Đây là lý do tài liệu kiến trúc [Dynamo của Cassandra](https://cassandra.apache.org/doc/latest/cassandra/architecture/dynamo.html) nhấn mạnh cần chạy cơ chế đồng bộ thời gian như **NTP**.

Ví dụ logic: write thứ nhất mang timestamp `2000` và giá trị `A`; write được gửi **sau** nhưng mang timestamp `1999` và giá trị `B`. Với cùng một cell, Cassandra giữ `A` vì timestamp lớn hơn; thứ tự ứng dụng gửi request **không thay thế** thứ tự timestamp. Đồng hồ lệch giữa client/coordinator hoặc `USING TIMESTAMP` sai có thể tạo ra tình huống tương tự.

### 7.2. Phân biệt múi giờ và đồng hồ

| Khái niệm | Ví dụ | Kết luận |
|---|---|---|
| Time zone hiển thị | Linux dùng UTC, máy cá nhân hiển thị UTC+7 | Cùng một thời điểm thực có thể có giờ hiển thị khác nhau; **không phải lỗi đồng bộ** |
| Clock synchronization | Đồng hồ của các node cùng theo nguồn NTP đáng tin cậy | Giúp timestamp phản ánh cùng trục thời gian |
| Clock skew | Một node nhanh 90 giây dù cùng hiển thị UTC | Có thể đảo thứ tự mutation timestamp, ảnh hưởng dữ liệu |
| Client-supplied timestamp | Java/driver hoặc CQL cung cấp timestamp tùy ý | Đồng bộ giờ server **không ngăn được** timestamp sai từ client |

Đối với Java, dùng các API thời gian rõ ràng như `Instant` khi cần UTC; tránh dùng đồng hồ máy chưa được đồng bộ để tự tạo mutation timestamp. Trong lab, luôn so sánh **UTC**, không lấy độ chênh của hai chuỗi giờ địa phương có múi giờ khác nhau làm bằng chứng đồng hồ lệch.

### 7.3. Kiểm tra NTP trên host và kiểm tra UTC trong container

Với **Linux host dùng systemd**:

```bash
timedatectl status
timedatectl show -p NTPSynchronized --value
date -u +"%Y-%m-%dT%H:%M:%SZ"
```

Nếu host sử dụng **chrony**, kiểm tra chất lượng đồng bộ:

```bash
chronyc tracking
chronyc sources -v
```

Không phải hệ thống nào cũng có `chronyc` hoặc `timedatectl` (ví dụ một container nhỏ, WSL không chạy dịch vụ tương ứng). Khi lệnh không tồn tại, kiểm tra dịch vụ đồng bộ giờ thực sự được cài trên **host hoặc VM**, không coi lỗi “command not found” là bằng chứng giờ lệch.

Với **Windows host** (PowerShell):

```powershell
[DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
w32tm /query /status
```

`w32tm` phản ánh trạng thái Windows Time nếu dịch vụ đang hoạt động; nếu không có nguồn/thông tin hợp lệ, kiểm tra cấu hình **Set time automatically** và đồng bộ giờ của Windows/VM. Với **macOS**, sử dụng `date -u` rồi kiểm tra thiết lập tự động ngày giờ trong System Settings.

Kiểm tra thời gian UTC trong container:

```bash
docker exec cassandra-resources-lab date -u +"%Y-%m-%dT%H:%M:%SZ"
```

Chạy lệnh host và container liên tiếp. Kết quả nên cùng mốc thời gian trong khoảng trễ hợp lý của việc gõ và thực thi lệnh. Nếu chênh lệch kéo dài bất thường, kiểm tra NTP và đồng hồ của **host/VM Docker**. Container thông thường chia sẻ đồng hồ kernel của host Linux/VM, nên việc thay đổi time zone hoặc cố chạy NTP riêng trong container **không giải quyết gốc rễ** của một VM bị lệch đồng hồ.

Trong cluster nhiều máy, đồng bộ **tất cả node**, và cả các máy **có thể phát sinh timestamp từ client**. Giám sát offset và trạng thái nguồn thời gian liên tục trong vận hành; không chỉ kiểm tra một lần lúc khởi tạo.

### 7.4. Thực hành chứng minh ý nghĩa timestamp (tùy chọn)

Ví dụ sau sử dụng **timestamp đặt thủ công** để minh họa last-write-wins, **không điều chỉnh đồng hồ hệ thống**:

```sql
CREATE KEYSPACE IF NOT EXISTS time_lab
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

CREATE TABLE IF NOT EXISTS time_lab.cell_demo (
    id text PRIMARY KEY,
    value text
);

INSERT INTO time_lab.cell_demo (id, value)
VALUES ('same-key', 'ghi-truoc')
USING TIMESTAMP 1780000000000000;

UPDATE time_lab.cell_demo
USING TIMESTAMP 1770000000000000
SET value = 'gui-sau-nhung-timestamp-nho'
WHERE id = 'same-key';

SELECT id, value, WRITETIME(value)
FROM time_lab.cell_demo WHERE id = 'same-key';
```

Chạy các câu trên trong `docker exec -it cassandra-resources-lab cqlsh`. Giá trị dự kiến vẫn là `ghi-truoc` vì `1780000000000000 > 1770000000000000` (đơn vị microsecond kể từ Unix epoch). Ví dụ này cố ý đặt timestamp và không đo mức skew thực tế. Khi kiểm tra xong, giữ kết quả làm minh chứng hoặc xóa keyspace **lab** có chủ đích; không áp dụng `USING TIMESTAMP` tùy tiện cho dữ liệu nghiệp vụ.

## 8. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Bằng chứng cần lấy và hướng khắc phục |
|---|---|---|
| Container chạy rồi thoát ngay | OOM, lỗi JVM, volume/permission, filesystem | `docker logs`, `docker inspect --format "{{.State.OOMKilled}}"`, `docker stats` và trạng thái đĩa; cấp tài nguyên phù hợp |
| `docker ps` có container nhưng CQL chưa kết nối | Cassandra còn khởi động, CPU/đĩa quá chậm | Chờ node `UN` trong `nodetool status`, đọc log và xem I/O; kiểm tra cổng ánh xạ |
| Java `OutOfMemoryError` | Heap thiếu hoặc workload vượt bộ nhớ, leak hoặc native memory/GC | Phân biệt lỗi JVM với kernel OOM, xem GC/heap, off-heap và limit container trước khi tăng heap |
| `OOMKilled=true` | Tổng bộ nhớ tiến trình vượt cgroup hoặc host cạn RAM | Xem limit, container metrics và OS log; tăng RAM/giảm tải, tránh chỉ tăng Xmx |
| Truy vấn chậm, CPU ~100% | Nhiều request, compaction/repair cạnh tranh CPU, GC | Đo latency, `tpstats`, `compactionstats`, GC và CPU quota; thay đổi một yếu tố rồi kiểm chứng |
| `No space left on device` | SSTable, commitlog, snapshot hoặc compaction cần thêm chỗ | `df -h /var/lib/cassandra`, `du -sh`, kiểm tra host/VM; bổ sung dung lượng theo quy trình an toàn |
| `df` trên host còn nhiều nhưng Cassandra báo đầy | Docker volume nằm trên filesystem/VM khác, hoặc VM có quota riêng | Chạy `df` **trong container tại volume**, kiểm tra Docker Desktop/WSL disk image |
| Read/write có kết quả lạ theo thứ tự thời gian | Clock skew, timestamp từ client, TTL/tombstone, khác partition | Kiểm tra `WRITETIME`, UTC/NTP của node và client; phân tích timestamp, consistency và key |
| Đồng hồ host/VM lệch sau sleep/resume | Time sync service/VM chưa cập nhật lại đồng hồ | Kiểm tra lại NTP trên host/VM và thời gian UTC từng node trước khi tiếp tục thí nghiệm phân tán |
| Có thể đọc CQL nhưng repair/compaction vẫn lỗi | Đĩa không đủ hoặc I/O/throttle lớn | Quan sát `compactionstats`, disk usage, log; không suy “node UN = hệ thống khỏe hoàn toàn” |

Thứ tự xử lý hợp lý là **ghi nhận triệu chứng → thu log/metrics → xác định nút nghẽn → thay đổi có kiểm soát → đo lại**. Với lab, có thể dựng lại container từ image đã ghim phiên bản; với dữ liệu cần giữ, phải bảo toàn volume và có quy trình phục hồi trước khi thay đổi cấu hình lưu trữ.

## 9. Checklist hoàn thành và bài tập tự kiểm tra

### 9.1. Biên bản chuẩn bị môi trường

Điền giá trị **thực tế**, không sao chép máy móc các giá trị trong ví dụ:

| Mục kiểm tra | Ghi nhận |
|---|---|
| Host OS và kiến trúc CPU | Phiên bản OS, `amd64/arm64`, CPU logic |
| RAM host và RAM cấp cho Docker/VM | Tổng, còn trống, giới hạn VM nếu có |
| Limit Cassandra container | `--cpus`, `--memory`, `--memory-swap`, `MAX_HEAP_SIZE` |
| Ổ đĩa/volume | Loại lưu trữ, filesystem, `df -h` tại `/var/lib/cassandra` |
| Cassandra image | `cassandra:5.0.9`, image digest nếu cần tái lập chính xác |
| Tình trạng node | `nodetool status` cho `UN` |
| CQL | `release_version` và `data_center` |
| Đồng bộ giờ | NTP status của host/VM; UTC host và container; offset nếu có công cụ đo |
| Quan sát workload | `docker stats`, `nodetool tpstats`, `nodetool compactionstats` |

### 9.2. Câu hỏi thực hành

1. Có máy 8 GiB RAM đang chạy IDE Java và Docker Desktop. Vì sao cấp `--memory=8g` cho Cassandra có thể khiến hệ thống thiếu RAM ngay cả khi JVM heap chỉ đặt 2 GiB?
2. Một node có 12 GiB SSTable đang hoạt động và chỉ 2 GiB đĩa trống. Vì sao một lượt compaction có thể lỗi dù không có INSERT mới?
3. `docker stats` hiển thị CPU gần quota 2 CPU trong khi `nodetool compactionstats` có tác vụ đang chạy. Những bước đo nào giúp phân biệt chậm do compaction với truy vấn sai partition key?
4. Laptop Windows còn 100 GiB ở ổ `D:` nhưng container Cassandra báo đầy đĩa. Cần kiểm tra dung lượng ở **lớp nào** trước khi kết luận Docker sai?
5. Node A và B hiển thị múi giờ địa phương khác nhau nhưng `date -u` giống nhau. Đó có phải clock skew không? Ngược lại, nếu một node nhanh 1 phút thì last-write-wins có thể chịu hậu quả gì?
6. Một phép ghi sau dùng `USING TIMESTAMP` nhỏ hơn timestamp của phép ghi trước. Thêm replica và chọn `QUORUM` có tự khiến giá trị mới thắng không?
7. Môi trường 3 node chạy trên cùng một máy đã đủ để thử lỗi mất cả datacenter hoặc mất nguồn điện độc lập chưa? Hãy phân biệt bài test logic với mô hình production.

**Tiêu chí đạt:** đã biết CPU/RAM/đĩa khả dụng của host và VM, chạy được node lab ở trạng thái `UN`, đọc CQL qua `cqlsh`, có named volume, kiểm tra được RAM/CPU/dung lượng bên trong container và xác định được nguồn đồng bộ thời gian trên host. Học viên giải thích được tại sao thiếu dung lượng ảnh hưởng compaction/repair, và tại sao timestamp lệch có thể làm kết quả Cassandra khác thứ tự ứng dụng gửi write.

### 9.3. Dừng lab nhưng giữ dữ liệu

```bash
docker stop cassandra-resources-lab
docker rm cassandra-resources-lab
docker volume ls --filter name=cassandra_resources_data
```

Các lệnh này dừng/xóa container **nhưng không xóa named volume**. Nếu tạo lại container bằng **cùng phiên bản Cassandra** và gắn lại volume, dữ liệu lab vẫn ở volume (với điều kiện volume chưa bị xóa). Khi đổi sang phiên bản Cassandra khác, phải tuân theo quy tắc nâng cấp; không gắn lại dữ liệu tùy tiện vào một phiên bản cũ hơn.

## 10. Tài liệu tham khảo

- [Apache Cassandra — Hardware Choices](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/hardware.html): mốc CPU/RAM production, cách Cassandra dùng heap/off-heap và lựa chọn đĩa.
- [Apache Cassandra — Compaction Overview](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/compaction/overview.html): SSTable bất biến, compaction và không gian lưu trữ.
- [Apache Cassandra — Dynamo architecture](https://cassandra.apache.org/doc/latest/cassandra/architecture/dynamo.html): mutation timestamp, last-write-wins và nhu cầu đồng bộ NTP.
- [Apache Cassandra — Production recommendations](https://cassandra.apache.org/doc/stable/cassandra/getting-started/production.html): replication strategy, cấu hình cluster production.
- [Docker Docs — Resource constraints](https://docs.docker.com/engine/containers/resource_constraints/): CPU quota, memory limit, memory-swap và OOM.
- [Docker Hub — Official Cassandra image](https://hub.docker.com/_/cassandra): tags, biến môi trường và ví dụ Docker.
- [Docker Docs — WSL2 backend](https://docs.docker.com/desktop/features/wsl/): cách Docker Desktop sử dụng WSL2 trên Windows.
