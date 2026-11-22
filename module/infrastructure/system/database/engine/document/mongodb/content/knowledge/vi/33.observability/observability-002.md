# CPU, RAM, ổ đĩa, WiredTiger cache và áp lực bộ nhớ trong MongoDB

## 1. Vì sao phải quan sát nhiều lớp cùng lúc?

Giả sử một ứng dụng có MongoDB replica set. Vào giờ cao điểm, thời gian phản hồi của API tăng từ khoảng 40 ms lên 800 ms. Dashboard hiển thị:

- CPU của máy primary khoảng 55%.
- RAM “used” của máy tới 93%.
- WiredTiger cache gần mức cấu hình tối đa.
- Ổ đĩa có nhiều thời điểm write latency tăng đột biến.
- Số request/giây chỉ tăng 20% so với bình thường.

Nếu chỉ nhìn RAM used 93%, một quyết định vội vàng là **tăng cache hoặc restart `mongod`**. Nhưng việc WiredTiger cache gần đầy có thể là trạng thái cache sử dụng tốt; nguyên nhân thực sự có thể là **I/O chậm, eviction không bắt kịp, một truy vấn thiếu index hoặc transaction dài giữ nhiều phiên bản dữ liệu**.

Một sự cố hiệu năng thường có nhiều mắt xích:

```text
            Application request
                    |
                    v
              MongoDB query
                    |
           +--------+--------+
           |                 |
           v                 v
     CPU execution       Memory access
   parse / plan /       WT internal cache
  filter / sort /         and OS cache
 compression                |
           |                 |
           +--------+--------+
                    |
                Cache miss
                    |
                    v
             Storage read I/O
                    |
               Write workload
                    |
           +--------+--------+
           |                 |
           v                 v
       Dirty pages        Journal
           |                 |
           +--------+--------+
                    |
              Storage write I/O
                    |
                  Disk
```

Mục tiêu bài học thuộc chương **Quan sát hệ thống** của module **Database Engine Document MongoDB** là đọc đúng tín hiệu từ **CPU, RAM, ổ đĩa và WiredTiger cache**, rồi tìm nguyên nhân gây **áp lực bộ nhớ** mà không làm gián đoạn hệ thống một cách thiếu căn cứ.

Sau bài, bạn có thể:

1. Phân biệt CPU bận vì xử lý query với CPU đang chờ I/O hoặc bị cgroup throttling.
2. Phân biệt RAM của máy, RSS/virtual memory của tiến trình, page cache của OS và WiredTiger internal cache.
3. Đọc các metric quan trọng trong `serverStatus()` và `hostInfo()`.
4. Hiểu cache occupancy, dirty bytes, eviction, cache misses và khi nào eviction là bình thường hay gây tắc nghẽn.
5. Đọc dung lượng ổ đĩa, IOPS, throughput, latency, queue depth và checkpoint/journal signals.
6. Giải thích sự khác nhau giữa `dataSize`, `storageSize`, `indexSize` và dung lượng filesystem thực.
7. Kết hợp tín hiệu MongoDB, hệ điều hành/container và độ trễ của ứng dụng để phân loại bottleneck.
8. Thiết kế dashboard, cảnh báo, capacity planning và runbook cho CPU/disk/RAM pressure.
9. Thực hành các lệnh **chỉ đọc** trên `mongosh` và hệ điều hành, cùng một lab nhỏ có cleanup an toàn.

## 2. Một mô hình quan sát theo bốn lớp

Không một metric đơn lẻ nào nói đủ về tình trạng MongoDB. Hãy chia thành:

| Lớp | Đối tượng | Câu hỏi chính |
| --- | --- | --- |
| Ứng dụng | API p50/p95/p99, QPS, lỗi, timeout, pool wait | Người dùng có bị ảnh hưởng không? |
| MongoDB | operations, active clients, WiredTiger, locks, transactions, replication | MongoDB đang phải xử lý/chờ điều gì? |
| Hệ điều hành / container | CPU, RSS, available memory, swap, iowait, page faults, cgroup memory/CPU limits | Process bị giới hạn tài nguyên gì? |
| Storage và hạ tầng | IOPS, throughput, read/write latency, queue, free disk, network, cloud volume limits | Thiết bị/băng thông có bắt kịp không? |

Một ví dụ phân tích:

```text
API p95 tăng
    |
    v
MongoDB read latency tăng?
    |
    +-- Có --> Cache misses tăng?
    |              |
    |              +-- Có --> Disk read latency tăng?
    |                              |
    |                              +-- Có --> I/O bottleneck
    |                              +-- Không --> Working set/cache pressure
    |
    +-- Không --> App connection pool / network / downstream
```

Đây là sơ đồ **định hướng triage**, không phải cây quyết định tuyệt đối. Các tín hiệu có thể tăng cùng nhau và cần đối chiếu theo timestamp.

### 2.1. Ưu tiên dữ liệu theo thời gian

CPU 95% tại một thời điểm không đồng nghĩa CPU bão hòa kéo dài. RAM used 90% có thể bình thường trên Linux do filesystem cache. `wiredTiger.cache["bytes currently in the cache"]` ở 90% mức tối đa không chứng minh ứng dụng đang thrash.

Nên đo:

- **Mức tuyệt đối:** hiện có bao nhiêu RAM/cache/disk.
- **Tốc độ thay đổi:** counters tăng bao nhiêu mỗi giây.
- **Tỷ lệ:** dirty bytes/cache max, disk free/capacity, error/requests.
- **Độ trễ:** p95/p99 API và disk.
- **Xu hướng:** chỉ số tăng dần suốt 15–60 phút hay chỉ spike ngắn.
- **Sự kiện cùng thời điểm:** deploy, index build, backup, bulk import, failover.

## 3. CPU: công suất tính toán và nút thắt truy vấn

### 3.1. CPU utilization phải đọc theo số lõi

Máy có 8 logical CPU cores. Một process chiếm 100% **một core** có thể chỉ hiện khoảng 12,5% CPU của toàn máy trong một dashboard chuẩn hóa theo tổng core.

Ví dụ:

```text
Host: 8 logical cores
One MongoDB thread: 100% of one core
Overall host CPU: ~12.5% (nếu các core khác idle)
```

Một số công cụ như `top` có thể hiển thị 100% cho một core, và **800% cho một process chạy hết 8 core** tùy chế độ. Trước khi so CPU từ các dashboard, phải thống nhất mẫu số và cách biểu diễn.

### 3.2. CPU time gồm nhiều loại

Trên Linux, người vận hành thường nhìn:

| Thành phần | Ý nghĩa gần đúng | Khi cao cần điều tra |
| --- | --- | --- |
| `user` | CPU chạy user-space code | Query execution, BSON parsing, compression, aggregation, TLS |
| `system` | CPU thực thi kernel | Syscalls, storage/network I/O, filesystem |
| `iowait` | CPU idle trong khi còn I/O cần chờ; định nghĩa OS cụ thể | Disk latency/queue; không coi là MongoDB CPU “đang tính” |
| `steal` | VM muốn chạy nhưng hypervisor phân CPU cho việc khác | Host overcommit/hạ tầng cloud |
| `idle` | CPU chưa sử dụng | Không loại trừ bottleneck ở một core hoặc I/O |
| `throttled` | Container vượt CPU quota nên bị giới hạn | Kubernetes/Docker cgroup CPU limit |

**CPU utilization cao chưa chắc do query**, và **CPU utilization thấp chưa chắc hệ thống không bị nghẽn**.

### 3.3. Nguyên nhân CPU cao thường gặp trong MongoDB

1. **COLLSCAN** vì thiếu index/điều kiện query không chọn lọc.
2. **SORT trong bộ nhớ** hoặc aggregation xử lý nhiều document.
3. **Regex phức tạp** hoặc nhiều biểu thức/transformations.
4. **Aggregation lớn** như `$group`, `$lookup`, `$unwind` trên tập dữ liệu lớn.
5. **Nén/giải nén** dữ liệu theo codec và workload.
6. **Index build** hoặc maintenance operation.
7. **Update liên tục** lên những document/index bị thay đổi nhiều.
8. **Nhiều kết nối đồng thời**, tạo quá nhiều việc cạnh tranh cùng CPU.
9. **Encryption/TLS** hoặc serialization ở phía client/server khi workload tăng.
10. **Search/Vector Search service** có thể có tiến trình/tài nguyên **riêng**, không phải mọi CPU search đều nằm trong `mongod`.

Nếu một query duy nhất bám một core do cách xử lý nội bộ, máy còn nhiều core rảnh cũng không nhất thiết giúp query đó nhanh hơn. Cần đánh giá **query plan và workload song song**, không chỉ tăng CPU.

### 3.4. Dấu hiệu bottleneck CPU

Có thể nghi CPU là giới hạn khi:

- CPU process cao kéo dài gần CPU quota/capacity;
- API latency tăng theo QPS;
- MongoDB operation execution time tăng;
- Disk latency và cache misses không có dấu hiệu tăng tương ứng;
- cgroup CPU throttling tăng hoặc run queue dài;
- giải thích query cho thấy examined documents/keys lớn so với returned;
- giảm một nhóm truy vấn nặng giúp CPU và p95 cải thiện.

Không nên tự khẳng định CPU là root cause từ một ảnh chụp `top` duy nhất.

### 3.5. Giải pháp theo nguyên nhân

| Quan sát | Hành động có cơ sở |
| --- | --- |
| `COLLSCAN` trên đường nóng | Xem query shape và index phù hợp |
| In-memory sort lớn | Xem compound index/filter/sort order; hạn chế dữ liệu |
| Pipeline nổ cardinality | Giảm `$unwind`/join/group, lọc sớm phù hợp |
| Thao tác bulk chiếm CPU | Throttle/batch, dời ngoài peak |
| Quota CPU thấp, throttling tăng | Điều chỉnh quota/requests/limits khi có capacity |
| Một core nóng, tổng CPU thấp | Xem operation đơn lẻ/lock, không vội scale cores |
| Index build chạy giờ peak | Lập kế hoạch DDL và giám sát build |
| Đã tối ưu query nhưng workload thực tăng | Cân nhắc vertical/horizontal scaling có benchmark |

Không kill operation hoặc restart primary chỉ vì CPU cao mà chưa xác định tác động, quyền và runbook.

## 4. RAM: phân biệt dữ liệu nào đang chiếm bộ nhớ

### 4.1. Bốn khái niệm rất dễ nhầm

```text
Physical RAM / Container memory limit
  |
  +-- mongod process memory
  |       |
  |       +-- WiredTiger internal cache
  |       +-- query execution/aggregation memory
  |       +-- connections, stacks, allocators
  |       +-- journals/metadata/other allocations
  |
  +-- OS filesystem/page cache
  |       +-- cached compressed database file blocks
  |
  +-- OS/kernel memory and other processes
  |
  +-- Free/available memory
```

- **Physical RAM:** tổng bộ nhớ máy có.
- **Process RSS/resident:** những trang bộ nhớ của `mongod` đang resident trong RAM (có thể chịu ảnh hưởng cơ chế đếm shared pages).
- **Virtual memory/VIRT:** không tương đương bộ nhớ thực đã sử dụng; bao gồm vùng địa chỉ được map/cấp phát.
- **WiredTiger internal cache:** bộ đệm nội bộ **có giới hạn riêng** để chứa pages/metadata của WiredTiger.
- **Filesystem/page cache:** RAM do OS quản lý để cache file blocks, gồm dữ liệu database trên ổ đĩa.
- **Memory available:** ước lượng OS có thể cấp cho ứng dụng mới mà không swap nặng; khác với “free” đơn thuần.

### 4.2. `mem.resident` khác `wiredTiger.cache`

MongoDB `serverStatus.mem.resident` được ghi bằng **MiB**, gần với RAM resident của tiến trình. WiredTiger cache metrics tính bằng **bytes**.

Ví dụ giả định:

```text
Host RAM                         16 GiB
WiredTiger cache maximum         7.5 GiB
WiredTiger bytes currently       7.1 GiB
mongod resident                  10.2 GiB
OS filesystem cache              3.2 GiB
```

Chúng **không thể cộng trừ tùy tiện** thành “tổng thực” vì các metric có ranh giới và cách tính khác nhau. Điểm quan trọng: **RSS lớn hơn WiredTiger cache là bình thường**, do `mongod` còn dùng bộ nhớ ngoài cache.

### 4.3. `mem.virtual` rất lớn có nhất thiết lỗi?

Không. Virtual address space của tiến trình có thể lớn vì memory mapping, reservations và allocator. Virtual size **không phải** lượng RAM vật lý đã tiêu thụ.

Dùng RSS, private/anonymous memory, OS MemAvailable, cgroup metrics và OOM/swap signals để đánh giá áp lực thực, thay vì cảnh báo chỉ dựa vào VIRT.

### 4.4. “RAM used 95%” có thể bình thường

Linux tận dụng RAM chưa dùng cho page cache. Khi một process cần RAM mới, phần page cache sạch có thể được thu hồi.

Ví dụ:

```text
Total RAM:      16 GiB
Used:           15 GiB
Free:          0.5 GiB
Available:      4 GiB
Swap in/out:  gần 0
```

Đây chưa phải bằng chứng thiếu RAM nghiêm trọng. Hãy xem **MemAvailable**, swap activity, memory pressure stall, major faults, OOM và latency.

Ngược lại, máy chỉ hiển thị “used 70%” nhưng có nhiều **container bị giới hạn cgroup 4 GiB** vẫn có thể OOM nếu một container chạm giới hạn riêng.

## 5. WiredTiger internal cache và filesystem cache

### 5.1. Tại sao có hai loại cache?

MongoDB với WiredTiger dùng **cả internal cache và filesystem cache của OS**:

```text
                mongod Query
                     |
                lookup B-tree
                     |
              WiredTiger cache
              (pages / metadata)
                     |
              cache miss / read
                     |
              OS filesystem cache
                     |
              cache miss / storage
                     |
                  Disk / SSD
```

- **WiredTiger internal cache** quản lý những pages mà storage engine cần để thực hiện reads/writes, giữ dirty/clean pages và eviction.
- **Filesystem cache** do OS quản lý, có thể lưu **compressed file blocks** của MongoDB, giảm I/O thực.
- Mỗi loại cache có cách đo và cơ chế thu hồi khác nhau.

Vì vậy **tăng WiredTiger cache không phải lúc nào cũng giảm disk read**. Bạn có thể lấy RAM của filesystem cache và làm I/O tệ hơn.

### 5.2. Default cache size

Theo tài liệu MongoDB hiện hành, kích thước mặc định của WiredTiger internal cache là **giá trị lớn hơn giữa**:

\[
0.5 \times (\text{RAM} - 1 \ \text{GB})
\]

và:

\[
0.256 \ \text{GB}
\]

Ví dụ một instance có 4 GB RAM:

\[
0.5 \times (4 - 1)=1.5 \ \text{GB}
\]

Với 16 GB RAM:

\[
0.5 \times (16 - 1)=7.5 \ \text{GB}
\]

Đây là **quy tắc mặc định**, không có nghĩa cache của process chỉ tiêu thụ đúng số byte đó ở mọi lúc hoặc host luôn còn nửa RAM “rảnh”. Ngoài cache còn có memory của query, connections, allocator và OS filesystem cache.

Khi sử dụng container, cần kiểm tra `hostInfo.system.memLimitMB` và giới hạn cgroup thực; trong một số cấu hình WiredTiger có thể không nhận diện hết memory limits. Không ước tính cache theo RAM host nếu `mongod` chỉ được cấp một phần RAM qua container.

### 5.3. Cấu hình có thể thay đổi cache

MongoDB có các cách cấu hình như:

```yaml
storage:
  wiredTiger:
    engineConfig:
      cacheSizeGB: 2
```

Hoặc tùy phiên bản:

```yaml
storage:
  wiredTiger:
    engineConfig:
      cacheSizePct: 50
```

Chỉ minh họa **hai phương án riêng**, không đặt đồng thời `cacheSizeGB` và `cacheSizePct`.

Tài liệu MongoDB khuyên **tránh tăng cache trên mức mặc định** nếu chưa có lý do thực nghiệm. Cấu hình phần trăm có giới hạn theo version và tổng RAM; việc tăng giá trị có thể chiếm mất memory cho filesystem cache, process ngoài cache và OS.

**Không đổi cấu hình cache trên production trực tiếp trong bài thực hành.** Việc thay đổi cấu hình có thể cần restart hoặc cơ chế vận hành tương ứng, ảnh hưởng khả năng phục vụ và failover; phải do người sở hữu hạ tầng kiểm soát.

### 5.4. Cache occupancy cao là tín hiệu gì?

Một cache được thiết kế để sử dụng bộ nhớ nhằm tăng hiệu năng. Vì vậy:

```text
max cache:         8.0 GiB
current cache:     7.6 GiB
occupancy:        95%
```

**Chưa đủ kết luận có vấn đề.** Nếu:

- eviction làm việc bình thường;
- page reads từ disk thấp/ổn định;
- dirty bytes không tăng bất thường;
- application threads ít phải tự eviction;
- p95 query latency ổn định;
- OS không swap hoặc OOM;

thì cache gần đầy có thể là bình thường.

Áp lực cache đáng chú ý hơn khi **occupancy cao kéo dài kèm eviction khó khăn, page-ins tăng, waiting tăng hoặc latency ứng dụng tăng**.

## 6. Dirty pages, checkpoint và eviction

### 6.1. Clean và dirty pages

Một page là:

- **Clean:** không có thay đổi chưa được đưa vào dạng bền vững cần thiết; thường có thể eviction dễ hơn.
- **Dirty:** chứa thay đổi chưa được ghi/đồng bộ tới cấu trúc file dữ liệu theo cơ chế WiredTiger.

```text
Update document
       |
       v
WiredTiger cache
  dirty page
       |
       +----> eviction/reconciliation/write path
       |
       +----> checkpoint hoạt động theo chu kỳ
       |
       v
Data files / storage
```

Không đồng nhất dirty page với dữ liệu “chưa được bảo vệ”. MongoDB còn có **journal** và write concern để đảm bảo tính bền vững theo chính sách. Việc flush data pages/checkpoint có thể diễn ra sau khi một write được xác nhận theo contract tương ứng.

### 6.2. Checkpoint và journal có mục tiêu khác nhau

- **Journal:** ghi các thông tin cần thiết để hỗ trợ phục hồi crash theo storage engine.
- **Checkpoint:** đưa một trạng thái nhất quán của dữ liệu xuống storage trong tiến trình quản lý WiredTiger.
- **Eviction:** giải phóng/chuẩn bị giải phóng pages khỏi internal cache để cache có chỗ cho công việc mới.

Ba cơ chế có liên quan nhưng không đồng nghĩa. **Journal đã flush không có nghĩa mọi dirty page trong internal cache đã bằng 0**.

### 6.3. Eviction là việc bình thường

Khi working set lớn hơn cache, WiredTiger phải chọn pages để loại khỏi cache, đọc lại sau khi cần. Có hai tình huống:

**Eviction khỏe:**

```text
Cache near target
     |
Eviction workers có tiến độ
     |
Cache có chỗ cho pages mới
     |
Latency tương đối ổn định
```

**Eviction pressure:**

```text
Cache near target
     |
Eviction không theo kịp / pages bị giữ
     |
Application threads phải tham gia eviction hoặc chờ
     |
Latency, write stalls, disk I/O tăng
```

Không có “số eviction cao = lỗi” trong mọi workload. Xem **tốc độ, loại eviction, application waits và latency**.

### 6.4. Page pinning và transaction dài

Một transaction dài hoặc snapshot reader giữ trạng thái cũ có thể khiến một số pages/versions không thể được reclaim dễ dàng. Hệ quả:

- Cache cần giữ nhiều history/update versions.
- Eviction bị cản trở.
- Dirty/cache pressure tăng.
- Operation khác chờ, timeout hoặc rollback theo điều kiện.
- Storage history/tracking có thể tăng.

Đừng chỉ tăng cache khi có một transaction mở hàng chục phút. Cần tìm transaction/cursor/snapshot giữ lâu và xem code ứng dụng.

### 6.5. Dirty cache percentage

Một chỉ số thường dùng để tham khảo:

\[
\text{Dirty cache fraction}
=
\frac{\text{tracked dirty bytes in cache}}
{\text{maximum bytes configured}}
\]

Nếu dirty bytes = 1 GiB và max cache = 8 GiB, dirty fraction khoảng 12,5%.

Không tự dùng một ngưỡng cố định như “trên 20% là hỏng”. Cần xét **điểm đặt eviction/checkpoint của phiên bản**, pattern ghi, disk latency, thời gian tăng và trạng thái ứng dụng. **Dirty fraction tăng liên tục kèm slow storage writes** đáng chú ý hơn một giá trị cao ngắn hạn.

## 7. Các metric WiredTiger cache quan trọng

Trong `mongosh`, trên `mongod` dùng WiredTiger:

```javascript
const status = db.serverStatus();
const cache = status.wiredTiger?.cache;

printjson({
  maxBytes: cache?.["maximum bytes configured"],
  currentBytes: cache?.["bytes currently in the cache"],
  dirtyBytes: cache?.["tracked dirty bytes in the cache"],
  pagesReadIntoCache: cache?.["pages read into cache"],
  pagesWrittenFromCache: cache?.["pages written from cache"],
  pagesEvictedByAppThreads:
    cache?.["pages evicted by application threads"],
  unmodifiedPagesEvicted:
    cache?.["unmodified pages evicted"],
  modifiedPagesEvicted:
    cache?.["modified pages evicted"]
});
```

Những field names có khoảng trắng là **tên statistics thực tế** trong tài liệu WiredTiger; vì vậy truy cập qua bracket notation. Một số metric có thể đổi tên/không được cung cấp giữa phiên bản. Dùng optional chaining và kiểm tra dữ liệu có tồn tại trước khi đưa vào monitoring.

### 7.1. `maximum bytes configured`

Mức giới hạn cấu hình internal cache, **không phải tổng giới hạn RSS của process**. Dùng làm mẫu số tham khảo cho occupancy và dirty fraction.

### 7.2. `bytes currently in the cache`

Số byte đang nằm trong WiredTiger cache. Nó có thể gần max trong hoạt động bình thường.

\[
\text{Cache occupancy} =
\frac{\text{Current bytes}}{\text{Max bytes}}
\times 100\%
\]

Đây là **occupancy**, không trực tiếp là hit ratio hoặc memory pressure.

### 7.3. `tracked dirty bytes in the cache`

Dung lượng dirty bytes được WiredTiger theo dõi trong cache. Dirty tăng nhanh có thể báo write workload hoặc flushing/eviction không theo kịp. Đọc cùng disk write latency, checkpoint time và page eviction/wait counters.

### 7.4. `pages read into cache`

Đây là **cumulative counter** về số pages được đọc vào cache. Để đánh giá cache miss/page-in activity, lấy **chênh lệch giữa hai mẫu trong cùng một `mongod` process**, chia cho thời gian.

```text
Sample at T1: 1,000,000 pages read
Sample at T2: 1,006,000 pages read
T2 - T1 = 60 seconds

Page read rate ≈ 6,000 / 60 = 100 pages/s
```

Một rate cao hơn baseline có thể cho thấy working set lớn, full collection/index scan, eviction churn hoặc cold cache sau restart. Nhưng một page được đọc qua filesystem cache **không nhất thiết gây physical disk I/O**; phải đối chiếu OS disk read metrics.

### 7.5. `pages written from cache` và eviction

Các chỉ số ghi/eviction là counters tích lũy. Chúng tăng khi engine làm việc; **tăng không tự là lỗi**.

Cần quan sát:

- `modified pages evicted` và `unmodified pages evicted`.
- `pages evicted by application threads`.
- `application threads page read from disk to cache time (usecs)`.
- `application threads page write from cache to disk time (usecs)`.
- `operations timed out waiting for space in cache` nếu được cung cấp.
- `eviction server unable to reach eviction goal` và các wait/eviction-blocked counters nếu phiên bản có.

Một số metric nội bộ thay tên theo release; chỉ dựng dashboard sau khi xác nhận với `serverStatus()` thực tế.

### 7.6. Vì sao phải lấy rate/delta?

`pages read into cache` có thể đang là 10 triệu sau 40 ngày uptime. So con số đó với node vừa restart 2 giờ là **không có ý nghĩa**.

Dùng:

\[
\text{Rate} =
\frac{\text{counter}_{T2}-\text{counter}_{T1}}
{T2-T1}
\]

Lưu ý:

- Counter có thể reset khi `mongod` restart.
- Một số giá trị là BSON `Long` lớn; chuyển JS Number có giới hạn chính xác.
- Không so số raw giữa hai primary khác nhau mà bỏ qua uptime.
- Đặt sample interval đủ ổn định và dùng clock đúng.
- Cần chú ý sampling load và cardinality của metrics.

## 8. Đọc `serverStatus()` về RAM và sức tải

### 8.1. Một snapshot nhỏ, chỉ đọc

```javascript
const s = db.serverStatus();

printjson({
  host: s.host,
  process: s.process,
  uptimeSeconds: s.uptime,
  mem: s.mem,
  connections: {
    current: s.connections?.current,
    available: s.connections?.available,
    active: s.connections?.active
  },
  activeClients: s.globalLock?.activeClients,
  opcounters: s.opcounters
});
```

Ý nghĩa:

| Metric | Diễn giải |
| --- | --- |
| `mem.resident` | RAM resident process theo MiB, có thể tăng khi cache ấm lên |
| `mem.virtual` | Virtual address space theo MiB, không phải RSS |
| `connections.current` | Số kết nối đang mở |
| `connections.active` | Số kết nối đang có operation, nếu có metric |
| `globalLock.activeClients.readers/writers` | Số active client reads/writes theo semantics của server |
| `opcounters` | Counters read/write operations; tính rate bằng delta |
| `uptime` | Để phân biệt counters reset sau restart |

Không in toàn bộ `serverStatus()` vào log liên tục: output lớn, một số fields nhạy cảm, và chỉ nên thu thập đúng những chỉ số cần.

### 8.2. Connections không đồng nghĩa CPU

10.000 connections **không có nghĩa** 10.000 operations đang chạy. Nhiều connections có thể idle do pool. Ngược lại 100 connections gửi nhiều operations song song cũng đủ bão hòa một node.

Nếu connections.current cao:
  
- Xem connection pool settings của driver.
- Kiểm tra `active`/activeClients/waiting clients.
- Xem bộ nhớ cho mỗi connection và file descriptor limit.
- Kiểm tra tình trạng pool leak, retry storm, connection churn.
- Không tăng `maxIncomingConnections` tùy tiện nếu RAM/CPU chưa đủ.

### 8.3. WiredTiger concurrent transactions/tickets

Tùy phiên bản, `serverStatus.wiredTiger.concurrentTransactions` có thể cung cấp số ticket của read/write:

```javascript
const wt = db.serverStatus().wiredTiger;

printjson(wt?.concurrentTransactions);
```

Khi tickets available thấp kéo dài, cần xem workload đang giữ tickets lâu, I/O waits, locks, cache pressure và quy tắc admission. Một số bản MongoDB có **dynamic ticket management** nên giá trị total/available có thể đổi, không coi số ticket một giá trị bất biến.

Không tự chỉnh concurrency ticket count để “thêm capacity” nếu chưa tìm nguyên nhân đang làm hoạt động giữ ticket lâu.

### 8.4. Locks, flow control và replication

Latency writes có thể tăng vì:

- Lock contention.
- Admission/ticket wait.
- Flow control để bảo vệ replica set khi secondaries tụt.
- Replication lag và write concern.
- Disk journaling/checkpoint.

Những tín hiệu này cần đọc cùng CPU/RAM/disk. Nếu storage vẫn khỏe nhưng write latency tăng cùng flow control, tăng WiredTiger cache không phải hành động đầu tiên.

## 9. Đo hai mẫu WiredTiger thay vì một snapshot

Ví dụ `mongosh` **chỉ đọc**, sử dụng hai lần `serverStatus` trong cùng phiên, cách nhau 5 giây:

```javascript
function captureCache() {
  const s = db.serverStatus();
  const c = s.wiredTiger?.cache || {};

  return {
    timeMs: Date.now(),
    uptime: s.uptime,
    max: c["maximum bytes configured"],
    used: c["bytes currently in the cache"],
    dirty: c["tracked dirty bytes in the cache"],
    pagesRead: c["pages read into cache"],
    pagesWritten: c["pages written from cache"],
    appEvictions: c["pages evicted by application threads"]
  };
}

const first = captureCache();
sleep(5000);
const second = captureCache();

function finiteNumber(value) {
  if (value == null) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function rate(a, b, seconds) {
  const x = finiteNumber(a);
  const y = finiteNumber(b);
  if (x == null || y == null || seconds <= 0 || y < x) {
    return null;
  }
  return (y - x) / seconds;
}

const durationSec =
  (second.timeMs - first.timeMs) / 1000;

const max = finiteNumber(second.max);
const used = finiteNumber(second.used);
const dirty = finiteNumber(second.dirty);

printjson({
  seconds: durationSec,
  sameProcessLikely: second.uptime > first.uptime,
  cacheUsedPct: max > 0 ? 100 * used / max : null,
  dirtyPctOfMax: max > 0 ? 100 * dirty / max : null,
  pageReadsPerSecond:
    rate(first.pagesRead, second.pagesRead, durationSec),
  pageWritesPerSecond:
    rate(first.pagesWritten, second.pagesWritten, durationSec),
  appEvictionsPerSecond:
    rate(first.appEvictions, second.appEvictions, durationSec)
});
```

Lưu ý:

1. `sleep(5000)` tạm chặn **shell đang quan sát**, không dừng MongoDB.
2. Đây là phép đo demo, không thay hệ thống metrics time-series.
3. Nếu `mongod` restart giữa hai mẫu, counters reset; phải bỏ mẫu.
4. `sameProcessLikely` chỉ là tín hiệu sơ bộ từ uptime, **không phải chứng minh** hai mẫu cùng process; production nên dùng process start time/instance identity.
5. Với counters lớn vượt JS safe integer, đừng tin phép chuyển `Number()` mà không kiểm tra precision; dùng thư viện telemetry/BigInt phù hợp.
6. Nếu gặp metric thiếu/đổi tên, báo `null` chứ không coi là 0.
7. Các số rate chỉ mô tả thời điểm đo, cần baseline giờ bình thường và giờ cao điểm.

## 10. Dung lượng ổ đĩa: logical size khác physical size

### 10.1. Ba lớp dung lượng

```text
MongoDB logical documents
          |
          | compression & storage layout
          v
WiredTiger allocated storage
          |
          | data files + indexes + journal + oplog
          v
Filesystem and disk volume
          |
          | snapshots / OS / other files
          v
Physical / provisioned capacity
```

Các metric không thay thế nhau.

### 10.2. `dbStats`

Đọc thống kê database test:

```javascript
const lab = db.getSiblingDB("mongo_observe_row352_lab");
const stats = lab.runCommand({ dbStats: 1 });

printjson({
  db: stats.db,
  objects: stats.objects,
  dataSize: stats.dataSize,
  storageSize: stats.storageSize,
  indexSize: stats.indexSize,
  totalSize: stats.totalSize,
  fsUsedSize: stats.fsUsedSize,
  fsTotalSize: stats.fsTotalSize
});
```

Đọc ý nghĩa:

| Field | Ý nghĩa |
| --- | --- |
| `dataSize` | Tổng kích thước logic dữ liệu **không nén** theo thống kê |
| `storageSize` | Storage allocated cho collections, **không bao gồm index** |
| `indexSize` | Storage allocated cho indexes |
| `totalSize` | `storageSize + indexSize` của database |
| `fsUsedSize` | Đã sử dụng trên filesystem theo command/version |
| `fsTotalSize` | Tổng dung lượng filesystem theo command/version |

`dataSize` có thể **lớn hơn storageSize** khi dữ liệu được nén tốt. `storageSize` thường không giảm ngay khi xóa document vì WiredTiger có thể **tái sử dụng không gian cấp phát**.

### 10.3. Dung lượng trống trong allocated storage

Một số phiên bản hỗ trợ:

```javascript
const st = lab.runCommand({
  dbStats: 1,
  freeStorage: 1
});

printjson({
  storageSize: st.storageSize,
  freeStorageSize: st.freeStorageSize,
  indexSize: st.indexSize,
  indexFreeStorageSize: st.indexFreeStorageSize
});
```

Tính `freeStorageSize` có thể tốn tài nguyên ở database có nhiều collections/indexes. **Không đưa `freeStorage:1` vào monitoring tần suất cao một cách vô điều kiện**.

### 10.4. Vì sao xóa 100 GiB chưa chắc filesystem giảm 100 GiB?

`deleteMany`, TTL hoặc cleanup có thể làm giảm số document và logical data, nhưng WiredTiger thường giữ phần storage đã cấp phát để tái sử dụng.

Do đó:

```text
Before delete:
  collection storageSize = 120 GiB

After deleting 80 GiB logical documents:
  dataSize decreases
  storageSize may remain near 120 GiB
  reusable free space increases
```

Không tự chạy `compact`/`repairDatabase` hoặc drop/recreate collection trong giờ production chỉ vì số byte trên disk chưa giảm. Những thao tác đó có điều kiện, chi phí I/O, ảnh hưởng replication/availability và cần quy trình DBA riêng.

### 10.5. Đừng quên oplog, journal, logs và backups

Một phép tính capacity phải kể:

- Collection data files.
- Index files.
- Journal và checkpoint activity.
- Replication oplog.
- Diagnostic logs và FTDC.
- Temporary files/aggregation spill/index build.
- Filesystem overhead.
- Backup local/snapshots nếu dùng cùng volume.
- Headroom cho restore, compaction/migration hoặc burst.

Không coi `db.stats().totalSize` là dung lượng duy nhất của ổ đĩa cần để MongoDB chạy khỏe.

## 11. Disk IOPS, throughput, latency và queue depth

### 11.1. Bốn chỉ số chính

| Metric | Đơn vị thường gặp | Câu hỏi |
| --- | --- | --- |
| IOPS | operations/s | Thiết bị xử lý bao nhiêu read/write operations? |
| Throughput | MiB/s | Đọc/ghi bao nhiêu dữ liệu mỗi giây? |
| Read/write latency | ms/op, p95/p99 khi có | Mỗi I/O phải chờ bao lâu? |
| Queue depth | số requests đang chờ/được phục vụ | Thiết bị có backlog không? |

Một workload toàn đọc 4 KiB có thể rất nhiều IOPS nhưng throughput thấp. Một backup tuần tự có thể throughput cao với IOPS vừa phải.

Ví dụ:

```text
Workload A:
  20,000 reads/s x 4 KiB ~= 78 MiB/s

Workload B:
  200 reads/s x 1 MiB = 200 MiB/s
```

Cả hai có thể chạm **loại giới hạn khác nhau** của storage.

### 11.2. Đọc `iostat` có ngữ cảnh

Trên Linux, khi `sysstat` được cài:

```bash
iostat -xz 1 5
```

Các cột thường hữu ích (phụ thuộc version):

- `r/s`, `w/s`: số operations/giây.
- `rkB/s`, `wkB/s`: throughput.
- `r_await`, `w_await`: latency trung bình của I/O (ms), có tính thời gian chờ.
- `aqu-sz` hoặc `avgqu-sz`: độ dài queue trung bình.
- `%util`: mức thời gian có I/O đang hoạt động theo semantics của tool/device.

**Không sử dụng `%util=100%` làm bằng chứng phổ quát NVMe/cloud volume đã đạt công suất tối đa**: thiết bị song song có thể phục vụ nhiều I/O cùng lúc; cần xem IOPS, throughput, latency, queue và giới hạn provisioned của cloud provider.

### 11.3. Dấu hiệu disk bottleneck

Có thể nghi disk khi:

- `read/write await` tăng rõ so với baseline;
- queue depth tăng kéo dài;
- IOPS/throughput tiến gần provisioned limits;
- MongoDB page-in/checkpoint/journal time tăng;
- API latency tăng tương ứng;
- CPU còn thấp hoặc iowait tăng;
- cloud volume có burst credits giảm hoặc throttling;
- replication lag tăng vì secondaries không apply kịp.

Không giải thích mọi disk wait là do thiếu WiredTiger cache; có thể do backup, snapshot, log rotation, index build, noisy neighbor hoặc storage service.

### 11.4. p95/p99 quan trọng hơn average

Một average disk write latency 3 ms có thể che khuất một số write 200 ms. Với API p99 nhạy cảm, spike ở journal/checkpoint/storage có thể gây tail latency.

Ưu tiên:

- latency histogram nếu storage/observability stack hỗ trợ;
- p95/p99 MongoDB read/write;
- số timeout;
- thời điểm checkpoint và journal pressure;
- correlation với cloud volume metrics.

Không đồng nhất p99 query latency với p99 disk latency; một query có thể có nhiều I/O hoặc không I/O.

## 12. Mối quan hệ giữa cache pressure và disk pressure

### 12.1. Working set lớn hơn cache

**Working set** là tập dữ liệu và indexes thường xuyên được truy cập trong một khoảng thời gian.

Nếu working set = 30 GiB mà WiredTiger cache 8 GiB, engine có thể liên tục thay các pages theo pattern truy vấn. Tuy nhiên OS filesystem cache vẫn có thể giữ phần compressed data trên RAM, nên tác động lên **physical disk** tùy workload.

```text
Working set > cache
         |
         v
More cache replacement
         |
         +-- OS page cache hit -> có thể không đọc disk vật lý
         |
         +-- OS cache miss -> physical disk read
         |
         v
Query latency changes
```

Không lấy tổng `dataSize + indexSize` làm working set chính xác. Một database 1 TiB có thể hoạt động rất tốt nếu chỉ truy cập nóng 10 GiB; một database 50 GiB có thể thrash nếu access ngẫu nhiên trải đều khắp dữ liệu và RAM hạn chế.

### 12.2. Khi eviction và disk cùng nghẽn

Kịch bản:

```text
Write burst
    |
    v
Dirty pages increase
    |
Disk write latency increases
    |
Eviction cannot keep up
    |
Application threads help eviction / wait
    |
Writes and reads slow down
```

Một hành động thiếu kiểm chứng là **tăng WiredTiger cache tối đa**. Điều này có thể làm buffer lớn hơn trong ngắn hạn nhưng:
  
- lấy mất RAM của filesystem cache;
- tăng RSS và nguy cơ OOM ở container;
- không tăng IOPS/storage bandwidth;
- không xử lý long transaction pinning.

Giải pháp có thể là **giảm write burst, tối ưu indexes/queries, cải thiện storage, tăng RAM đúng cách hoặc xử lý transaction dài**, tùy root cause.

### 12.3. Cache occupancy cao nhưng disk còn khỏe

```text
WiredTiger occupancy 94%
Dirty fraction ổn định
OS available RAM còn dư
Disk read/write latency thấp
Eviction tiến độ tốt
API p95 bình thường
```

Không cần tạo incident chỉ từ occupancy 94%. Dashboard nên cảnh báo bằng **tổ hợp chỉ số**, không một giá trị cố định.

## 13. Áp lực bộ nhớ từ hệ điều hành và container

### 13.1. Các tín hiệu OS quan trọng

Trên Linux:

```bash
free -h
vmstat 1 5
cat /proc/meminfo
```

Chú ý:

- `MemAvailable`.
- `SwapUsed`, swap-in/swap-out activity.
- Major page faults.
- Reclaim/page scanning pressure nếu exporter có.
- Memory PSI (`/proc/pressure/memory`) trên kernel hỗ trợ.
- OOM killer logs/restarts.

**Swap đã được cấp phát** chưa chắc đang xảy ra swap liên tục; hoạt động `si/so` (swap-in/out), memory stalls và latency tăng mới cho thấy áp lực đang ảnh hưởng. Hệ thống database nhạy cảm với swap thrashing.

### 13.2. Cgroup memory limit

Trong container/Kubernetes:

```text
Host physical RAM:       64 GiB
Container memory limit:   8 GiB
WiredTiger cache max:     7.0 GiB  (cấu hình bất hợp lý cho container này)
Other process memory:     2.0 GiB
Total:                    9.0 GiB  -> nguy cơ OOM
```

WiredTiger cache **không phải giới hạn tổng RAM của `mongod`**, và container memory còn bao gồm memory/caches khác theo cgroup semantics.

Các nguồn có thể kiểm tra theo cgroup version:

```bash
# cgroup v2 (nếu mount ở đường dẫn chuẩn):
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.events

# Tài nguyên CPU:
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpu.stat
```

Không áp đường dẫn trên cho mọi môi trường; cgroup v1/managed orchestration có cấu trúc khác. Trên Kubernetes, đối chiếu pod memory limit, working set, OOMKilled/restartCount và container memory metrics.

### 13.3. `hostInfo()` để xem giới hạn MongoDB thấy

```javascript
const info = db.adminCommand({ hostInfo: 1 });

printjson({
  physicalMemMB: info.system?.memSizeMB,
  memoryLimitMB: info.system?.memLimitMB,
  totalCores: info.system?.numCores,
  coresAvailableToProcess:
    info.system?.numCoresAvailableToProcess
});
```

Theo tài liệu MongoDB, `memLimitMB` biểu diễn mức memory limit mà MongoDB nhìn thấy, đặc biệt hữu ích trong container. Field có thể bị hạn chế bởi deployment, OS và quyền; một số Atlas tiers không hỗ trợ `hostInfo`.

**Không kết luận chỉ từ `memSizeMB` của host khi container có memory limit thấp hơn.**

### 13.4. OOM và restart không nên “chữa” bằng tăng cache

Nếu process bị OOMKilled:

1. Kiểm tra peak cgroup usage, `memory.events` và restart history.
2. Xem cấu hình WiredTiger cache so với limit.
3. Đếm connection và những process cùng pod.
4. Xem aggregation spill/in-memory operations/index build.
5. Tìm memory leak hoặc allocator growth ngoài WiredTiger.
6. Kiểm tra workload thay đổi trước incident.
7. Điều chỉnh giới hạn/cache/queries theo capacity plan.
8. Xem lại liveness/readiness probes và rollout.

Restart có thể làm RSS/cache giảm tạm thời nhưng **không chữa root cause**; còn làm cache lạnh, tăng disk reads, ảnh hưởng failover và latency.

## 14. Đo ở mức process và node

### 14.1. Các lệnh OS chỉ đọc

Linux:

```bash
# Tổng CPU/memory của node:
top

# Bộ nhớ ở node:
free -h

# Tổng quan CPU + paging:
vmstat 1 5

# Storage và queue:
iostat -xz 1 5

# Dung lượng filesystem:
df -h
df -i
```

Nếu có quyền và tooling:

```bash
# Quan sát memory/process bằng ps:
ps -eo pid,comm,%cpu,rss,vsz --sort=-rss

# Thống kê per-process (sysstat):
pidstat -rud 1 5
```

`pidstat` có thể tạo nhiều output; lọc đúng PID `mongod` trong môi trường thực. Không chạy các lệnh phá dữ liệu để đo “hiệu năng thật”, ví dụ tạo file hàng chục GiB, drop collection hoặc flush OS cache trên production.

### 14.2. Giới hạn của các số OS

- `RSS` có thể khác với metric cgroup working set.
- Page cache tính vào memory used, nhưng có thể được reclaim.
- `iowait` là metric scheduler của Linux, không phải số thời gian từng MongoDB operation chờ disk.
- `df -h` báo filesystem capacity; cloud block volume metrics có thể có burst/IOPS riêng.
- Hypervisor/container isolation làm các con số khó so trực tiếp.
- Trên Windows/macOS cần công cụ tương ứng, không copy lệnh Linux.

### 14.3. Atlas/managed service

Nếu dùng MongoDB Atlas, ưu tiên metrics/dashboard của dịch vụ được cấp quyền:

- CPU utilization / normalized CPU.
- Memory resident, system memory.
- WiredTiger cache, dirty/eviction indicators.
- Disk IOPS, throughput, utilization, read/write latency.
- Connection count, queued operations.
- Query execution metrics/slow query view.
- Replication lag và oplog window.
- Storage growth, index builds, maintenance events.

Tên metric và phạm vi tính toán thay đổi theo tier, deployment, MongoDB version. **Không giả định mọi field có sẵn trên free/shared tier hoặc trên mọi dịch vụ managed.**

### 14.4. FTDC và log

MongoDB hỗ trợ **Full-Time Diagnostic Data Capture (FTDC)**, thu thập các statistics như `serverStatus` định kỳ để phục vụ chẩn đoán. Trên self-managed deployments, FTDC thường được bật mặc định.

FTDC có thể chứa chi tiết về hệ thống/deployment, cần:

- hạn chế quyền đọc artifact;
- quản lý thời gian lưu/truyền;
- không chia sẻ lên kho công cộng;
- giữ timezone, thời điểm và context incident;
- không tắt tùy tiện vì có giá trị chẩn đoán.

Diagnostic logs/slow query logs cũng giúp đối chiếu latency, nhưng có thể chứa namespace/query shape. Áp dụng dữ liệu nhạy cảm và chính sách truy cập.

## 15. Kết nối metrics với query execution

### 15.1. Tại sao nhìn CPU/cache mà bỏ query là thiếu?

Một query không có index:

```javascript
db.orders.find({
  customerEmail: "person@example.test"
});
```

Nếu không có index `customerEmail` thích hợp, MongoDB có thể scan nhiều document, tiêu tốn CPU/cache và kích hoạt nhiều page reads.

Một index phù hợp:

```javascript
db.orders.createIndex({
  customerEmail: 1
});
```

có thể giảm số keys/docs examined, CPU và I/O **nếu query shape và cardinality phù hợp**. Tuy nhiên tạo index cũng làm tăng storage và write amplification, nên phải benchmark thay vì tạo bừa bãi.

### 15.2. `explain("executionStats")`

Trên collection test được quyền:

```javascript
db.orders.find({
  customerEmail: "person@example.test"
}).explain("executionStats");
```

Xem:

| Field / dấu hiệu | Ý nghĩa |
| --- | --- |
| `totalDocsExamined` | Số documents được xét |
| `totalKeysExamined` | Số index keys được xét |
| `nReturned` | Số document trả về |
| `COLLSCAN`/`IXSCAN` hoặc các stages tương ứng | Index có được dùng không |
| `executionTimeMillis` | Thời gian trong phép explain theo semantics của server |
| Blocking sort/spill indicators | Query có thêm memory/I/O pressure không |

Stage names/output khác theo MongoDB version và execution engine. Một lần explain không thay production observability; query plan/data/cache có thể khác workload thật.

### 15.3. Examined/returned ratio

Ví dụ:

```text
totalDocsExamined = 1,000,000
nReturned = 10
examined/returned = 100,000
```

Tỷ lệ cao gợi ý truy vấn phải duyệt rất nhiều để trả ít document. Nhưng với aggregation/group/count, `nReturned` là output của pipeline, nên ratio đơn lẻ không chứng minh index sai.

Cần hiểu **ngữ nghĩa query** và workload trước khi kết luận.

### 15.4. Aggregation spill

Một số aggregation stages như sort/group có thể cần memory. Khi vượt giới hạn có thể spill ra disk theo phiên bản và `allowDiskUse`/`allowDiskUseByDefault`.

Nếu thấy:

- temp disk writes tăng;
- query p95 tăng;
- CPU/memory tăng;
- profiler/diagnostics báo usedDisk/spill;

hãy xem pipeline, sort/filter/index và giới hạn dữ liệu. **Cho phép spill** giúp hoàn tất tác vụ nhưng có thể làm disk pressure tăng; **cấm spill** có thể khiến query thất bại. Không có lựa chọn “luôn tốt hơn” cho mọi trường hợp.

### 15.5. Profiler không miễn phí

MongoDB Database Profiler có thể ghi chi tiết operations vào `system.profile`, dùng CPU/disk và tăng tải. Tài liệu cảnh báo profiler level 2 (mọi operations) hoặc slow threshold quá thấp có overhead đáng kể.

Trong production:

- ưu tiên telemetry có sẵn, Atlas Query Profiler/Performance Advisor hoặc `$queryStats` nếu phù hợp;
- nếu cần database profiler, có kế hoạch giới hạn scope/time và rollback;
- không tự bật level 2 trên toàn cluster trong sự cố CPU/disk;
- chú ý quyền và khả năng chứa metadata nhạy cảm.

Bài lab này **không bật profiler**.

## 16. Tương quan CPU, cache, disk và workload

### 16.1. Kịch bản 1 — Cache misses và disk reads tăng

```text
p95 reads: 30 -> 250 ms
WiredTiger page reads/s: tăng 4 lần
Disk reads IOPS: tăng 3 lần
Disk read latency: tăng
CPU: 45%
```

Giả thuyết có cơ sở: working set/cache efficiency giảm, query scan lớn hoặc storage không theo kịp.

Kiểm tra:

1. Query/index change, collection growth, workload access pattern.
2. Repeated collection scans hoặc cache lạnh sau restart.
3. OS page cache và disk bandwidth.
4. Read preference/secondary đặc biệt nào đang nóng.
5. Có cần thêm RAM, cải tiến index hay giảm query fan-out?

Không tăng cache trước khi kiểm tra disk/working set và giới hạn RAM thực.

### 16.2. Kịch bản 2 — Dirty pages và write latency cùng tăng

```text
Write p95: 20 -> 400 ms
Dirty cache fraction: tăng liên tục
WT modified page evictions: tăng
Disk write await: tăng
Write throughput: tăng mạnh
```

Giả thuyết: storage writes/checkpoint/eviction đang không theo kịp thay đổi.

Hành động:

- Xem bulk import/index build/backup.
- Kiểm tra provisioned IOPS/throughput/burst credits.
- Throttle writes không khẩn cấp.
- Xem long transactions hoặc locks.
- Cân nhắc tăng storage performance hoặc capacity.

Đừng tắt journal hoặc giảm write concern chỉ để làm dashboard latency đẹp hơn; đó là thay đổi durability rất nghiêm trọng.

### 16.3. Kịch bản 3 — CPU cao, disk bình thường

```text
CPU: 95% sustained
Disk await: ổn định
WT page read rate: không thay đổi lớn
Query examined/returned ratio: tăng mạnh
```

Giả thuyết: workload tính toán/query-plan hiệu năng thấp.

Kiểm tra query shape, explain, regex, aggregation, index selection, connection concurrency và ứng dụng gửi lệnh trùng lặp.

### 16.4. Kịch bản 4 — RAM used cao nhưng không có áp lực

```text
Host RAM used: 94%
MemAvailable: còn đủ
Swap in/out: gần 0
OOM events: 0
WT cache: gần max, stable
API latency: stable
```

Chưa có bằng chứng cần can thiệp. Đây có thể là OS sử dụng RAM hữu ích cho cache.

### 16.5. Kịch bản 5 — Container OOM dù host còn RAM

```text
Host memory available: 60 GiB
Pod limit: 8 GiB
Container memory: đạt 8 GiB
Pod OOMKilled: tăng
WT configured max: 7 GiB
```

Vấn đề chính là **quota/cgroup memory so với tổng footprint**, không phải RAM host thiếu. Xem điều chỉnh cache size, resource limit, query memory và các tiến trình chia pod.

### 16.6. Kịch bản 6 — Secondary lag, write concern chậm

```text
Primary CPU: 40%
Primary disk: bình thường
Secondary disk: write latency cao
Replication lag: tăng
Majority write latency: tăng
```

Giả thuyết: secondary storage/apply không theo kịp hoặc flow control/replication đang ảnh hưởng writes. Tăng CPU/cache primary không giải quyết nếu bottleneck ở secondary.

## 17. Dashboard theo góc nhìn người vận hành

### 17.1. Dashboard tối thiểu

```text
+-----------------------------+------------------------------+
| API p95 / p99 + error rate  | MongoDB read/write latency   |
+-----------------------------+------------------------------+
| Host/process CPU            | Container CPU throttling     |
+-----------------------------+------------------------------+
| MemAvailable + RSS          | cgroup usage / OOM / swap    |
+-----------------------------+------------------------------+
| WT cache used/max           | WT dirty bytes / max         |
+-----------------------------+------------------------------+
| WT page-in & eviction rates | WT eviction/wait anomalies   |
+-----------------------------+------------------------------+
| Disk IOPS / throughput      | Read/write latency + queue   |
+-----------------------------+------------------------------+
| Disk free space / growth    | Replication lag + tickets    |
+-----------------------------+------------------------------+
| Slow query shapes           | Index build / deployment     |
+-----------------------------+------------------------------+
```

### 17.2. Tên metric có thể do ứng dụng tự định nghĩa

Ví dụ custom metrics:

```text
mongo_app_request_duration_seconds
mongo_wt_cache_occupancy_ratio
mongo_wt_dirty_fraction
mongo_wt_pages_read_per_second
mongo_wt_app_evictions_per_second
mongo_process_rss_bytes
mongo_container_memory_limit_bytes
mongo_disk_read_latency_seconds
mongo_disk_write_latency_seconds
mongo_disk_queue_depth
mongo_replication_lag_seconds
mongo_oom_events_total
```

Đây là **tên gợi ý**, không phải tên chuẩn bắt buộc MongoDB/Prometheus tự xuất. Nếu dùng exporter, xem tên/đơn vị metric thực tế và đảm bảo counters được chuyển sang rates đúng cách.

### 17.3. Cảnh báo dựa trên tác động và nhiều tín hiệu

Ví dụ **chỉ số minh họa**, không phải mặc định MongoDB:

| Alert | Điều kiện nên kết hợp | Mục tiêu |
| --- | --- | --- |
| CPU saturation | CPU/process hoặc throttling cao kéo dài **và** latency tăng | Phát hiện CPU ảnh hưởng người dùng |
| Memory pressure | MemAvailable thấp + swap/PSI/OOM hoặc cgroup gần limit | Ngăn OOM/thrashing |
| WT eviction pressure | Eviction waits tăng + cache/dirty pressure + p95 tăng | Phân biệt cache đầy khỏe với tắc |
| Storage bottleneck | Disk await/queue cao + throughput gần limit + DB latency tăng | Tìm I/O saturation |
| Disk capacity risk | Free space thấp + tốc độ tăng + headroom dự báo | Tránh full disk |
| Replication pressure | Lag tăng + write concern latency/flow control | Bảo vệ tính sẵn sàng và durability |
| Monitoring failure | Metrics stale/FTDC/collector lỗi | Tránh “dashboard xanh giả” |

Tránh alert chỉ vì WiredTiger cache used 95% hoặc RAM used 90%, bởi có thể tạo false positive liên tục.

### 17.4. Headroom phải có dự báo

Ví dụ:

```text
Disk volume:          1,000 GiB
Used:                   800 GiB
Recent growth:           10 GiB/day
Theoretical free:       200 GiB
Time to full:         ~20 days (nếu tốc độ ổn định)
```

Không đợi đến 99% đầy mới phản ứng: cần headroom cho oplog, journal, temporary files, index builds, bursts, restores và failure.

Phép chia trên chỉ để minh họa; tăng trưởng thực có thể không tuyến tính. Cần forecast từ nhiều khoảng thời gian và scenario như import/traffic campaign.

## 18. Lab an toàn: quan sát metrics mà không stress cluster

### 18.1. Điều kiện

- Dùng **MongoDB test deployment** đã được cấp quyền.
- Có quyền đọc `serverStatus`/`hostInfo` nếu muốn xem toàn hệ thống; một số managed tiers sẽ hạn chế.
- Không cố tình tạo disk pressure, memory leak hoặc CPU spike.
- Không chỉnh WiredTiger cache, profiler, journal, OS cache hoặc process resource limits trong bài học.
- Chỉ tạo vài trăm document nhỏ trong database lab riêng.
- Không chạy trên `admin`, `local`, `config` hoặc một namespace production.

### 18.2. Bước A — Đọc tổng quan chỉ bằng query

```javascript
const s = db.serverStatus();

printjson({
  uptimeSeconds: s.uptime,
  processMemoryMiB: {
    resident: s.mem?.resident,
    virtual: s.mem?.virtual
  },
  wtCache: {
    used: s.wiredTiger?.cache?.[
      "bytes currently in the cache"
    ],
    max: s.wiredTiger?.cache?.[
      "maximum bytes configured"
    ],
    dirty: s.wiredTiger?.cache?.[
      "tracked dirty bytes in the cache"
    ]
  },
  totalConnections: s.connections?.current
});
```

Nếu lệnh báo `Unauthorized`, đây là giới hạn RBAC của môi trường. Không xin quyền admin toàn hệ thống chỉ vì muốn chạy lab; dùng dashboard do DBA cung cấp hoặc account `clusterMonitor` được phê duyệt.

### 18.3. Bước B — Tạo dữ liệu demo theo runId

```javascript
const lab = db.getSiblingDB("mongo_observe_row352_lab");
const coll = lab.getCollection("sample_records");
const runId = "row352-" + new ObjectId().toHexString();

const docs = Array.from({ length: 200 }, (_, i) => ({
  _id: new ObjectId(),
  runId,
  seq: i,
  groupKey: "group-" + (i % 10),
  status: i % 2 ? "ACTIVE" : "INACTIVE",
  metric: i * 10,
  payload: "sample-" + i
}));

const inserted = coll.insertMany(docs);

printjson({
  runId,
  insertedCount: Object.keys(inserted.insertedIds).length,
  labCount: coll.countDocuments({ runId })
});
```

Đây chỉ là 200 document nhỏ, **không phải stress test**; số liệu CPU/cache/disk có thể hầu như không đổi.

### 18.4. Bước C — Tạo index chỉ cho collection lab

```javascript
coll.createIndex(
  { runId: 1, groupKey: 1, seq: 1 },
  { name: "row352_run_group_seq" }
);
```

Đây là một index phục vụ query cụ thể:

```javascript
printjson(
  coll.find({
    runId,
    groupKey: "group-3"
  }).sort({ seq: 1 }).limit(10).toArray()
);
```

Tạo index trên một collection được người khác chia sẻ có thể gây tải và thay đổi plan cho workloads khác. Trong lab, index được giới hạn theo collection test; nếu collection này có dữ liệu của lượt khác, cần quyền/chủ sở hữu rõ trước khi tạo.

### 18.5. Bước D — Xem explain

```javascript
const explanation = coll.find({
  runId,
  groupKey: "group-3"
}).sort({ seq: 1 }).limit(10)
  .explain("executionStats");

printjson({
  nReturned: explanation.executionStats?.nReturned,
  docsExamined:
    explanation.executionStats?.totalDocsExamined,
  keysExamined:
    explanation.executionStats?.totalKeysExamined,
  executionMs:
    explanation.executionStats?.executionTimeMillis
});
```

Lưu ý: output của explain phụ thuộc execution engine/version. Đo vài trăm document chỉ cho thấy cú pháp và cách đọc metric, không thể dùng để kết luận index sẽ cải thiện production bao nhiêu lần.

### 18.6. Bước E — Đo before/after rất nhỏ

Một đoạn đo:

```javascript
const before = db.serverStatus();

coll.updateMany(
  {
    runId,
    status: "ACTIVE"
  },
  {
    $inc: { metric: 1 }
  }
);

const after = db.serverStatus();

printjson({
  beforeUptime: before.uptime,
  afterUptime: after.uptime,
  beforeCacheBytes:
    before.wiredTiger?.cache?.[
      "bytes currently in the cache"
    ],
  afterCacheBytes:
    after.wiredTiger?.cache?.[
      "bytes currently in the cache"
    ]
});
```

Chỉ sửa các document có **runId của chính lượt test**. Dòng `updateMany` dùng để chứng minh cách thu thập trước/sau, **không dùng làm phép đo causal** trên hệ thống có workloads đồng thời; cache metrics toàn server có thể thay đổi do người khác.

### 18.7. Bước F — Dọn dữ liệu theo đúng quyền sở hữu

Trước khi xóa, hiển thị ID và số lượng:

```javascript
print("database=" + lab.getName());
print("collection=" + coll.getName());
print("runId=" + runId);

const ownedIds = coll.find(
  { runId },
  { _id: 1, runId: 1 }
).toArray();

printjson({
  count: ownedIds.length,
  ids: ownedIds.map((doc) => doc._id)
});
```

Chỉ khi xác nhận đúng 200 document thuộc chính lượt thử:

```javascript
for (const item of ownedIds) {
  coll.deleteOne({
    _id: item._id,
    runId
  });
}

print("remaining=" + coll.countDocuments({ runId }));
```

Không dùng `deleteMany({})` hoặc `dropDatabase()` trên database có thể được chia sẻ. Index lab có thể còn trên collection; chỉ thu hồi theo chính sách và quyền quản lý test environment.

## 19. Quy trình triage khi hiệu năng xuống cấp

### 19.1. Bước 1 — Xác nhận triệu chứng người dùng

Ghi lại:

- Thời điểm/khung giờ.
- p95/p99 và tỷ lệ lỗi.
- Loại request/query.
- Primary hay secondary bị ảnh hưởng.
- Có deploy, backup, batch import, index build, failover không.
- Độ trễ tăng ở tất cả endpoint hay chỉ một nhóm.

Không thay đổi cấu hình trước khi có baseline đủ để so.

### 19.2. Bước 2 — Kiểm tra tài nguyên bên ngoài MongoDB

- CPU process/host và cgroup throttling.
- MemAvailable, RSS, swap, OOM.
- Disk free, read/write await, queue và cloud IOPS/throughput.
- Network saturation/packet errors nếu có.
- Quyền và giới hạn container/VM.

Nếu `mongod` ở container, nhìn đúng container/pod và từng node, không chỉ host tổng.

### 19.3. Bước 3 — Kiểm tra serverStatus và WiredTiger

- Cache used/max và dirty bytes.
- Pages read into cache/s và app eviction rate.
- Eviction wait/timeout counters.
- Connections/active operations.
- Read/write ticket availability nếu version có.
- Checkpoint/journal timing.
- Replication lag/flow control.
- Uptime/restart.

### 19.4. Bước 4 — Xác định query/workload

- Slow query shapes từ logging/profiler được phép.
- `explain("executionStats")` cho query đại diện.
- `totalDocsExamined`/`totalKeysExamined`.
- Blocking sort, spills, large aggregations.
- Long-running transactions/cursors.
- Bulk writes/index maintenance.
- Connection pool saturation và retry storm.

### 19.5. Bước 5 — Sửa ở lớp gây vấn đề

```text
CPU/query bound
   -> index / query plan / aggregation / concurrency

Cache/workload bound
   -> working set / indexes / RAM / long transactions

Disk bound
   -> query I/O / storage provision / batch throttling

OS/container memory bound
   -> limits / cache config / outside-cache allocations

Replication bound
   -> secondary / oplog / flow control / network

App pool bound
   -> pool settings / leak / request queue / retry behavior
```

### 19.6. Bước 6 — Kiểm chứng tác động

Sau mỗi thay đổi được phê duyệt:

- Ghi rõ thời điểm thay đổi và version/config.
- So metrics trước/sau cùng traffic hoặc normalized workload.
- Xem p95/p99, error rate, throughput.
- Theo dõi vài chu kỳ cao điểm nếu cần.
- Có rollback nếu metrics xấu.
- Không tuyên bố “đã sửa” chỉ vì một snapshot giảm CPU.

## 20. Một số tình huống chẩn đoán nâng cao

### 20.1. Long-running transaction giữ cache

```text
Node CPU: 35%
Disk writes: tăng
WT dirty bytes: tăng
Eviction blocked: tăng
Oldest active transaction age: rất lớn
```

Đây có thể là vấn đề **version retention/pinning**, không phải chỉ RAM thấp. Cần tìm client mở transaction lâu, xử lý timeout/lifecycle và điều tra application code.

Không tùy tiện `killOp` hay hủy transaction của khách hàng thật mà không xác minh tác động; có thể rollback nghiệp vụ đang chạy.

### 20.2. Full scan do collection growth

```text
Dataset size: 20 -> 200 GiB
Traffic QPS: gần như không đổi
CPU/query latency: tăng
Docs examined per query: tăng
Disk reads/s: tăng
```

Nghi ngờ query có selectivity/index kém khi dataset lớn. Tối ưu query/index có thể hiệu quả hơn tăng cache lên gấp đôi.

### 20.3. “Cache lạnh” sau restart

`mongod` vừa restart, internal cache chưa được làm ấm; nhiều query phải load pages. Disk read IOPS tăng tạm thời, p95 cũng có thể tăng.

Không nhầm khoảng warm-up này với memory leak. Xem uptime, page read rate và xu hướng giảm khi cache ấm. Nếu cache mãi không bắt kịp, xem working set/disk.

### 20.4. Sau khi import, disk và replication lag tăng

Bulk import có thể vừa ghi data vừa cập nhật nhiều indexes, làm dirty pages tăng và gây pressure lên journal/checkpoint và secondaries.

Giảm batch size/throughput, cân nhắc thời gian triển khai, theo dõi replication lag và disk capacity. Không tăng `w`/giảm `w` hay tắt journaling một cách phản xạ; durability và availability phải được bảo đảm theo nghiệp vụ.

### 20.5. Disk free giảm nhanh do oplog hoặc logs

Nếu `dbStats.totalSize` tăng chậm nhưng filesystem full nhanh, phải kiểm tra **phần ngoài database logical collections**, gồm oplog/journal/logs/temp files/backup. Không chỉ xóa application collection khi nguyên nhân ở file khác.

Không tự xóa `local.oplog.rs`, journal files hay FTDC directory để lấy chỗ; thao tác sai có thể phá replication/khả năng khôi phục.

## 21. Capacity planning theo RAM, CPU và storage

### 21.1. Working set và RAM

Ví dụ:

```text
Hot index pages:            5 GiB
Hot document pages:         7 GiB
Estimated hot working set: 12 GiB
Available WT cache:         8 GiB
```

Đây là **ước lượng**. Nếu workload random access, cần RAM/index/query optimization; nếu OS cache giữ compressed blocks, hiệu năng có thể vẫn đủ. Không mặc định MongoDB cần chứa toàn bộ database trong WiredTiger cache.

Cách thực tế:

1. Xác định query access pattern.
2. Đo cache page-ins/s, eviction và disk reads.
3. Thử trên staging với workload tương đương.
4. So p95/p99 theo size/cache/traffic.
5. Tính headroom và failover scenario.

### 21.2. Capacity khi có failover

Replica set có thể cần primary mới phục vụ toàn bộ writes khi failover. Node secondary không nhất thiết có cache nóng giống primary, workload sau election có thể thay đổi.

Kế hoạch phải tính:

- Write throughput và replication apply.
- Disk/CPU headroom cho election và catch-up.
- Cache warm-up.
- Backup operations.
- Index builds/migrations.
- Traffic burst sau retries.

### 21.3. Disk forecast

```text
Current data+index allocated:    500 GiB
Oplog/journal/logs reserve:       80 GiB
Expected growth:                  15 GiB/day
Planned horizon:                  30 days
Growth estimate:                 450 GiB
Extra safety/maintenance reserve: 150 GiB
----------------------------------------
Projected requirement:         ~1180 GiB
```

Các số chỉ **minh họa**. Compression, TTL, index growth, backup location và compaction có thể làm thực tế khác. Dự báo theo storage metrics và kịch bản tăng trưởng thay vì chỉ nhìn một ngày.

### 21.4. Đừng quên storage giới hạn tách IOPS/throughput

Một volume lớn 2 TiB không đương nhiên cung cấp IOPS đủ cho 100.000 random reads/s; cloud storage có thể có provisioned IOPS, throughput và burst limits riêng.

Khi mở rộng, cần đánh giá cả:

- capacity;
- random IOPS;
- throughput;
- latency;
- sustained vs burst;
- replication/backup;
- cost.

## 22. Các hiểu lầm phổ biến

| Hiểu lầm | Cách hiểu đúng |
| --- | --- |
| “Cache dùng 95% là thiếu RAM” | Cache thường được thiết kế để đầy; xem eviction, I/O và latency |
| “MongoDB RSS = WiredTiger cache” | RSS gồm cả nhiều allocation ngoài cache |
| “VIRT 200 GiB = MongoDB dùng 200 GiB RAM” | Virtual address space khác resident memory |
| “Linux free thấp là OOM sắp xảy ra” | Xem MemAvailable, cgroup, swap/PSI/OOM |
| “Cache miss là physical disk read” | OS filesystem cache có thể đáp ứng read |
| “Đưa cacheSize lên tối đa RAM là nhanh nhất” | Có thể lấy memory của OS cache và gây OOM |
| “Giảm cache luôn tăng hiệu năng” | Có thể gây nhiều page-ins; cần đo |
| “CPU host thấp nghĩa query không CPU bound” | Có thể nghẽn một core hoặc bị cgroup throttling |
| “iowait cao là CPU đang tính toán quá tải” | Đây là thời gian idle đợi I/O theo OS |
| “Disk %util 100% trên NVMe chắc chắn đã chạm max IOPS” | Phải xem throughput, latency, queue, provisioned limits |
| “IOPS cao chắc chắn storage chậm” | IOPS có thể cao nhưng latency vẫn thấp |
| “dataSize là số byte chiếm trên disk” | dataSize không nén; storageSize là allocated storage |
| “Xóa document thì disk lập tức giảm” | WiredTiger có thể tái sử dụng allocated space |
| “Dirty pages nghĩa dữ liệu chắc chắn chưa bền” | Journal/write concern/checkpoint có semantics riêng |
| “Eviction counter tăng là lỗi” | Eviction hoạt động bình thường; quan sát waits/latency |
| “Page reads counter tăng tức disk bị đọc nhiều” | Counter tích lũy và có thể trúng OS cache |
| “Counter lớn hơn node khác là node xấu hơn” | Cần tính rate và xét uptime/restarts |
| “Cứ bật profiler level 2 để tìm root cause” | Có overhead và rủi ro nhạy cảm |
| “Tăng connection limit giảm latency” | Có thể tăng RAM/contension nếu pool không kiểm soát |
| “Tăng cache giải quyết replication lag” | Bottleneck có thể ở secondary/network/flow control |
| “Restart giúp giảm RAM nên đã sửa lỗi” | Có thể che lỗi tạm và làm cache lạnh |
| “Đổi write concern thấp để giảm disk pressure” | Có thể phá durability contract |
| “Tăng disk capacity là tăng IOPS” | Capacity và IOPS/throughput có thể là hai quota khác nhau |
| “Một snapshot đủ chứng minh root cause” | Cần xu hướng/correlation/baseline |
| “Container có thể dùng toàn bộ RAM host” | Cgroup memory limit có thể thấp hơn nhiều |
| “FTDC/profiler artifacts được chia sẻ công khai” | Có thông tin hệ thống/query; cần RBAC và retention |

## 23. Bài tập tự luyện

### Bài A — Phân biệt cache occupancy với memory pressure

Một node có:

```text
Host RAM used:           92%
MemAvailable:             6 GiB
WiredTiger cache used:   95% of max
Swap in/out:          gần 0
Disk read latency:    ổn định
API p95:              ổn định
```

1. Có đủ cơ sở kết luận thiếu RAM chưa?
2. Những metric nào bổ sung bằng chứng?
3. Vì sao tăng cache lên có thể phản tác dụng?

### Bài B — Tính cache occupancy

```text
Cache maximum: 8 GiB
Bytes in cache: 6.8 GiB
Tracked dirty: 0.9 GiB
```

1. Tính occupancy %.
2. Tính dirty fraction % của cache maximum.
3. Có thể kết luận eviction đang lỗi chỉ từ hai tỷ lệ không?
4. Cần xem metric nào cùng thời điểm?

### Bài C — Tính page-in rate

```text
T1: pages read into cache = 100,000,000
T2: pages read into cache = 100,012,000
Time elapsed: 60 sec
```

1. Tính page reads/s.
2. Điều gì xảy ra nếu MongoDB restart giữa T1/T2?
3. Tại sao page reads/s không nhất thiết bằng physical disk IOPS?

### Bài D — CPU process và CPU host

Một process MongoDB dùng 100% của một core trên máy 16 cores, trong khi tổng CPU khoảng 7%.

1. Có mâu thuẫn không?
2. Vì sao tăng core count không chắc cải thiện một query serial?
3. Đề xuất phép đo/query plan giúp tìm nguyên nhân.

### Bài E — Disk saturation

```text
Read IOPS:  gần volume limit
Read await: tăng 2ms -> 25ms
Queue:      tăng kéo dài
WT page-ins: tăng mạnh
API p99:    tăng mạnh
```

1. Root cause khả dĩ là gì?
2. Query/index change có thể gây ra không?
3. Vì sao chỉ tăng WiredTiger cache chưa đủ?
4. Cần kiểm tra cloud volume quota nào?

### Bài F — OOM trong container

```text
Host RAM:          64 GiB
Pod memory limit:   8 GiB
WT cache max:       7 GiB
mongod RSS:         8.5 GiB
Pod restarts:       OOMKilled
```

1. Tại sao host vẫn còn RAM mà pod bị kill?
2. Những allocation nào nằm ngoài WT cache?
3. Cấu hình/cache và metric nào cần xem?
4. Vì sao restart không phải giải pháp gốc?

### Bài G — `dbStats`

Một database có:

```text
dataSize:     200 GiB
storageSize:  120 GiB
indexSize:     40 GiB
```

1. Vì sao dataSize có thể lớn hơn storageSize?
2. totalSize khoảng bao nhiêu theo định nghĩa?
3. Sau khi xóa nhiều document, metric nào có thể giảm?
4. Những phần nào của disk chưa được phản ánh đầy đủ?

### Bài H — Dirty pages và transaction dài

```text
WT dirty bytes: tăng
Eviction waits: tăng
Disk latency: không tăng đáng kể
Oldest active transaction: 30 phút
```

1. Tại sao transaction dài có thể ảnh hưởng eviction?
2. Vì sao không nên chỉ tăng cache?
3. Nên điều tra application code nào?
4. Có nên kill transaction ngay không?

### Bài I — Chọn dashboard/alert

Thiết kế alert **Memory Pressure** mà không chỉ dựa vào RAM used%. Chọn ít nhất bốn metric và mô tả:

- điều kiện kéo dài bao lâu;
- cần kết hợp latency/availability không;
- cách tránh cảnh báo sai khi filesystem cache tăng;
- việc làm đầu tiên khi cảnh báo kích hoạt.

### Bài J — Capacity planning

Một cluster đang dùng 500 GiB cho dữ liệu/indexes, tăng 15 GiB/ngày. Cần dự báo 30 ngày, còn oplog/journal/logs và safety reserve.

1. Tính mức tăng cơ bản.
2. Vì sao không chỉ lấy `500 + 15*30` rồi chọn volume đúng bằng kết quả?
3. Disk capacity, IOPS và throughput phải được chọn ra sao?
4. Backup/index build ảnh hưởng headroom thế nào?

### Bài K — Phân biệt bottleneck đa node

Primary có CPU 40% và disk ổn; secondary có disk write latency cao, replication lag tăng và majority write p95 tăng.

1. Có nên tăng cache primary ngay không?
2. Metric nào ở secondary cần xem?
3. Có thể liên quan flow control/write concern không?
4. Sau can thiệp cần so những tín hiệu gì?

### Bài L — Phương án tối ưu query

Một query mỗi lần trả 10 document nhưng duyệt hàng triệu documents, CPU và page reads tăng.

1. Dùng `explain("executionStats")` đọc những field nào?
2. Tạo index như thế nào mà không tạo bừa?
3. Vì sao hiệu quả còn phụ thuộc selectivity và sort?
4. Khi nào cần thử staging/canary?

## 24. Tài liệu tham khảo chính thức

Khi triển khai, hãy đối chiếu đúng MongoDB server version, deployment topology, exporter và hệ điều hành:

- [WiredTiger Storage Engine](https://www.mongodb.com/docs/manual/core/wiredtiger/) — kiến trúc cache, filesystem cache, công thức default cache size và compression.
- [Production Notes for Self-Managed Deployments](https://www.mongodb.com/docs/manual/administration/production-notes/) — memory, cache và khuyến cáo tuning.
- [`serverStatus` Command](https://www.mongodb.com/docs/manual/reference/command/serverStatus/) — metrics `mem`, `wiredTiger.cache`, connections, opcounters và checkpoint.
- [`hostInfo` Command](https://www.mongodb.com/docs/manual/reference/command/hostInfo/) — RAM giới hạn, CPU cores và host/container information.
- [`dbStats` Command](https://www.mongodb.com/docs/manual/reference/command/dbStats/) — `dataSize`, `storageSize`, `indexSize`, filesystem metrics.
- [`db.stats()`](https://www.mongodb.com/docs/manual/reference/method/db.stats/) — helper, scale và freeStorage.
- [Explain Slow Queries](https://www.mongodb.com/docs/manual/tutorial/explain-slow-queries/) — dùng explain/profile để tìm query bottleneck.
- [Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/) — ngưỡng slow operations, overhead và giới hạn.
- [Full-Time Diagnostic Data Capture (FTDC)](https://www.mongodb.com/docs/manual/administration/full-time-diagnostic-data-capture/) — diagnostic metrics và cách bảo vệ artifacts.
- [`mongostat`](https://www.mongodb.com/docs/database-tools/mongostat/) — công cụ quan sát MongoDB throughput, cache và operations.
- [`mongotop`](https://www.mongodb.com/docs/database-tools/mongotop/) — thời gian đọc/ghi theo collection trong phạm vi hỗ trợ.
- [MongoDB Atlas Monitoring](https://www.mongodb.com/docs/atlas/monitor-cluster-metrics/) — metrics cluster trên dịch vụ managed.
- [WiredTiger Cache Configuration](https://www.mongodb.com/docs/manual/reference/configuration-options/#storage-wiredTiger.engineConfig.cacheSizeGB) — tùy chọn cache size và cảnh báo cấu hình.

**Ghi chú phiên bản:** tên thống kê WiredTiger, các chỉ số tickets, FTDC, profiler và quyền truy cập trên Atlas thay đổi giữa MongoDB releases và tiers. Các ngưỡng, tỷ lệ, ví dụ tải và SLO trong bài chỉ phục vụ minh họa, **không phải giới hạn/cam kết cố định do MongoDB bảo đảm**.

## 25. Kết luận

Quan sát MongoDB đúng cách đòi hỏi hiểu đồng thời **CPU, RAM, storage và WiredTiger cache**:

- **CPU cao** cần được phân tích theo process/core, query plan, throttling và I/O waits.
- **RAM used cao** không tự nghĩa thiếu RAM; phải xem RSS, MemAvailable, swap, OOM và container limits.
- **WiredTiger internal cache** là một bộ đệm có giới hạn riêng, hoạt động cùng **OS filesystem cache**. Cache gần đầy thường bình thường; chỉ đáng lo khi eviction/page-in/dirty/wait/latency cho thấy áp lực thực.
- **Ổ đĩa** phải được đánh giá theo IOPS, throughput, read/write latency, queue và dung lượng còn lại; logical data size không phải physical disk usage.
- **Counters tích lũy** phải đổi thành rates theo thời gian, xử lý restart và đối chiếu với baseline.
- **Giải pháp** phải nhắm đúng nguyên nhân: query/index, working set, long transaction, disk performance, container memory hay replication, thay vì tăng cache hoặc restart theo cảm tính.

**Thông điệp cốt lõi:** một node MongoDB khỏe không nhất thiết là node có CPU, RAM hay cache sử dụng thấp. Node khỏe là node **phục vụ workload trong giới hạn latency/availability/durability đã đặt ra**, có đủ headroom và có thể giải thích rõ các tín hiệu tài nguyên từ ứng dụng tới storage.
