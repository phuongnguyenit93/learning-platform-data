# Tính tài nguyên cho Redis, trình điều khiển và ứng dụng trong Spring Data Redis

Khi triển khai một ứng dụng Spring Boot dùng Spring Data Redis, câu hỏi “Redis cần bao nhiêu RAM?” chỉ giải quyết **một phần** bài toán. Một hệ thống vận hành ổn định cần tính tài nguyên của **Redis Server**, **Redis client/driver**, **ứng dụng Java**, **mạng**, **storage**, các **replica**, cùng khả năng chịu tải khi cache mất tác dụng hoặc topology thay đổi.

Một Redis có dataset 6 GiB không đồng nghĩa chỉ cần container RAM 6 GiB. Ngoài dữ liệu logic còn có metadata, allocator fragmentation, connection buffers, replication buffers, bộ nhớ copy-on-write (COW) khi tạo RDB/AOF rewrite và bộ nhớ do hệ điều hành tính. Tương tự, một ứng dụng có 500 HTTP threads không nhất thiết cần 500 Redis connections: **Lettuce có thể multiplex nhiều lệnh qua native connection dùng chung**, còn Jedis và một số thao tác blocking/transaction cần chiến lược kết nối khác.

Mục tiêu bài học là xây dựng **capacity plan có thể kiểm chứng**: xác định workload, tính ngân sách theo thành phần, chọn cấu hình ban đầu, đo bằng benchmark và giám sát để điều chỉnh trước khi production quá tải. Các số dưới đây là **ví dụ minh họa**, không phải giá trị mặc định an toàn cho mọi ứng dụng.

## 1. Bản đồ tài nguyên của hệ thống

Một deployment thường có nhiều lớp:

```text
                      Internet / API Clients
                               |
                               v
                    Load Balancer / Ingress
                               |
                     +---------+---------+
                     |                   |
                     v                   v
               Spring Pod A         Spring Pod B ... N
                - JVM heap           - JVM heap
                - thread stacks      - thread stacks
                - Netty/direct RAM   - Netty/direct RAM
                - Lettuce/Jedis      - Lettuce/Jedis
                - connection pool    - connection pool
                     |                   |
                     +---------+---------+
                               |
                          Network / TLS
                               |
                      Redis data primary
                     +-------------------+
                     | in-memory dataset |
                     | expires/metadata  |
                     | client buffers    |
                     | replication buf.  |
                     | persistence child |
                     +-------------------+
                         /             \
                        v               v
                  Redis replica A   Redis replica B
                        |
                   Disk / AOF / RDB
```

Nếu dùng Redis Cluster, sơ đồ có nhiều primary, mỗi primary giữ một phần hash slots. Với Sentinel, còn có các Sentinel nodes giám sát và điều phối failover. Nếu dùng managed Redis, một số thành phần do nhà cung cấp quản lý nhưng chi phí và giới hạn thực tế vẫn tồn tại.

**Ngân sách phải lập cho cả hệ thống**, không chỉ cấu hình `maxmemory` của một Redis instance.

### 1.1. Các câu hỏi capacity planning cần trả lời

1. Redis giữ bao nhiêu key, value có kích thước và kiểu dữ liệu ra sao?
2. Key sống bao lâu? Dataset tăng nhanh nhất ở thời điểm nào?
3. Redis là cache có thể eviction hay đang chứa session/lock/queue/state không được phép loại bỏ?
4. Số lệnh GET/SET/HGET/ZADD/XADD/INCR mỗi giây là bao nhiêu?
5. P95/p99 payload, RTT và command latency là bao nhiêu?
6. Tỷ lệ đọc/ghi, cache hit/miss, timeout và retry thế nào?
7. Có bao nhiêu Spring Boot instances, workers, consumers, Redis factories?
8. Client là Lettuce hay Jedis; shared connection hoặc pooled connection?
9. Có RDB snapshot, AOF, replica, Sentinel, Cluster hay TLS không?
10. Khi một Redis node mất hoặc cache bị cold, hệ thống có bao nhiêu headroom?
11. SLO nghiệp vụ yêu cầu latency, availability và durability đến mức nào?
12. Bao nhiêu tài nguyên cần giữ dư cho deploy, failover, resharding và tăng trưởng?

Nếu chưa có số liệu, hãy đánh dấu **assumption** và thiết kế phép đo thay vì trình bày một ước lượng như sự thật.

## 2. Bắt đầu từ workload và các giới hạn nghiệp vụ

Trước khi chọn node size, lập workload inventory.

| Nhóm | Thông tin cần đo |
|---|---|
| Cache sản phẩm | Key count, key/value size, TTL, hit ratio, GET/SET rate |
| Session | Concurrent sessions, serializer size, TTL, read/write mỗi request |
| Rate limiter | Key cardinality, TTL, INCR/EXPIRE throughput |
| Lock/idempotency | Active locks, token size, lease, retry rate, business correctness |
| Hash/Set/ZSet | Số members/fields và phân phối kích thước |
| Redis Streams | Entries, payload size, retention, pending count, consumer groups |
| Pub/Sub | Publisher rate, số listeners, message bytes |
| Lua/scripts | P95/p99 duration, key count, max execution time |
| Batch/warm-up | Burst frequency, command count, pipeline size |
| Redis background jobs | Snapshot/rewrite windows, replication sync, resharding |

### 2.1. Average không đại diện cho peak

Giả sử lưu lượng:

```text
Bình thường:     2.000 Redis operations/giây
Đỉnh trong ngày: 8.000 operations/giây
Sau deploy:     25.000 operations/giây trong 30 giây do cache warm-up
```

Chọn cấu hình dựa trên 2.000 ops/s có thể không chịu được burst 25.000 ops/s. Phải thu:

- Throughput p50/p95 và **peak** theo cửa sổ đủ ngắn.
- Số command/HTTP request; một request có thể tạo nhiều command.
- Độ lớn payload trung bình và percentile, không chỉ số key.
- Dữ liệu đang tồn tại, dữ liệu tăng trong vài tháng tới.
- Các job theo lịch tạo burst.
- Tình trạng failover/reconnect làm command retry tăng.

Redis có thể chịu nhiều lệnh đơn giản nhưng bị nghẽn với vài Lua scripts nặng hoặc lệnh quét collection lớn. Không suy ra capacity chỉ từ `PING` benchmark.

### 2.2. Xác định nguồn dữ liệu và chính sách mất mát

Một instance Redis lưu cache có thể dùng `allkeys-lru` hoặc policy tương đương theo yêu cầu. Nhưng nếu Redis chứa session, lock, idempotency key hoặc stream nghiệp vụ, eviction có thể gây hành vi không an toàn.

Capacity planning phải đi kèm:

```text
Data criticality
    -> Có được eviction?
    -> Có thể dựng lại?
    -> RPO/RTO?
    -> Cần backup/persistence?
    -> Có được fail-open khi Redis lỗi?
```

**Tính tài nguyên không thể tách khỏi ý nghĩa nghiệp vụ của dữ liệu.**

## 3. Mô hình ước lượng RAM Redis

Một cách khởi đầu:

\[
M_{\text{logical}} \approx
\sum_{i=1}^{n}
N_i \times B_i
\]

Trong đó:

- \(N_i\): số key/entry của nhóm dữ liệu \(i\).
- \(B_i\): mức bộ nhớ Redis trung bình thực tế cho một entry thuộc nhóm \(i\), **bao gồm overhead phù hợp**.
- \(M_{\text{logical}}\): ngân sách bộ nhớ logic ước lượng theo dataset.

Không nên cho rằng:

\[
B_i = \text{UTF-8 key length} + \text{UTF-8 value length}
\]

vì Redis còn dùng object representation, dictionary entries, pointers, allocator rounding, expiration metadata và cấu trúc dữ liệu nội bộ.

### 3.1. Vì sao payload 1 KiB không tốn đúng 1 KiB RAM?

Một key kiểu String thường có thêm:

- Key object/representation.
- Entry trong Redis keyspace dictionary.
- Value object/representation.
- Allocation overhead và alignment.
- Expiration metadata nếu có TTL.
- Các thông tin nội bộ tùy phiên bản/encoding.

Một Hash, Sorted Set hoặc Stream có overhead theo field/member/entry và representation có thể thay đổi tùy kích thước/giới hạn encoding.

Số đo chỉ từ payload thường **đánh giá thiếu RAM**.

### 3.2. Dùng `MEMORY USAGE` để đo mẫu

Trên Redis thực:

```redis
MEMORY USAGE cache:product:42
MEMORY USAGE session:example
MEMORY USAGE stream:orders SAMPLES 0
```

`MEMORY USAGE` trả mức bytes theo cách Redis thống kê cho key. Với các kiểu dữ liệu lồng nhau, `SAMPLES` ảnh hưởng chi phí và độ chính xác của phép ước lượng; `SAMPLES 0` yêu cầu xem toàn bộ nested values theo semantics tương ứng, có thể tốn tài nguyên trên cấu trúc lớn.

Không chạy sampling sâu hàng loạt trên production peak chỉ để lập một báo cáo. Thực hiện ở staging hoặc lấy mẫu có giới hạn.

Tạo một tập key **đại diện cho dữ liệu thật**:

```text
1.000 product DTO nhỏ
1.000 product DTO lớn
1.000 user sessions
1.000 rate-limit counters
100 streams với số entry gần thực tế
...
```

Đo `MEMORY USAGE` của nhiều mẫu, tính trung bình/percentile cho từng nhóm; rồi nhân với cardinality dự kiến.

### 3.3. Đo bằng chênh lệch `used_memory`

Một phương pháp khác:

1. Redis test instance sạch và cấu hình giống production.
2. Đọc `INFO memory` để lấy baseline `used_memory`.
3. Nạp một số lượng key đủ lớn, ví dụ 100.000 key theo workload.
4. Đọc lại `used_memory`.
5. Lấy chênh lệch chia số key nạp.

\[
B_{\text{per-key, measured}}
\approx
\frac{M_{\text{after}}-M_{\text{before}}}{N_{\text{loaded}}}
\]

Phép đo bao gồm nhiều overhead hơn chỉ payload, nhưng không phải một hằng số tuyệt đối: Redis allocator, object encoding, dict resize, TTL, key distribution và phiên bản có thể làm kết quả thay đổi.

Nếu cần hiểu chi tiết encoding và độ phức tạp dữ liệu, kết hợp `OBJECT ENCODING`, `MEMORY STATS` và Redis server metrics trên bộ dữ liệu thử nghiệm phù hợp.

## 4. Các Redis data types có đặc điểm RAM khác nhau

| Kiểu Redis | Yếu tố quyết định RAM | Lưu ý tính toán |
|---|---|---|
| String | Kích thước key/value và object allocation | Nhiều key rất nhỏ có overhead tương đối cao |
| Hash | Số fields, kích thước field/value, encoding | Có thể tiết kiệm hơn nhiều String keys nhưng không luôn |
| List | Số elements, kích thước element, representation | Các list khổng lồ gây latency khi thao tác phạm vi lớn |
| Set | Số members và encoding | Mỗi member có overhead |
| Sorted Set | Số members, score, representation | Thường tốn hơn Set cho cùng payload |
| Stream | Entry payload, entry ID, retention, group/PEL | Pending/consumer state và trim policy có tác động |
| HyperLogLog | Representation và số lượng HLL keys | Ước lượng cardinality, không lưu đầy đủ member |
| Geo | Dữ liệu lưu trên Sorted Set | Cần tính key/member/score và truy vấn geo |
| Bitmap | Khoảng offset cao nhất | Dùng bit ở offset rất xa có thể làm value lớn |

Với Redis Hash, một user profile chứa 20 fields có thể có memory profile khác với 20 String keys riêng biệt. Nhưng đừng chuyển mọi record thành một Hash khổng lồ chỉ để giảm key overhead, vì có thể tạo hot key và làm tăng thời gian thao tác.

### 4.1. Đừng quên key cardinality

Một key `rate-limit:{userId}:{minute}` có thể tạo hàng triệu key mới mỗi giờ, dù mỗi value chỉ vài bytes. Nếu TTL bị quên hoặc đặt sai, memory tăng rất nhanh.

Ước lượng số key còn sống:

\[
N_{\text{live}} \approx
\text{new keys per second}
\times
\text{average lifetime in seconds}
\]

Ví dụ **mô hình lý tưởng**:

```text
100 unique new keys/s
TTL 600 giây
=> khoảng 60.000 live keys ở steady state
```

Con số thực tế phụ thuộc burst, key reuse, traffic distribution và expiration. Nếu Redis đang chịu áp lực CPU hoặc memory, key có thể chưa được giải phóng đúng vào mili giây hết TTL, nhưng Redis vẫn coi key expired là không còn hợp lệ theo semantics của lệnh đọc.

### 4.2. TTL và eviction không đồng nhất

- **TTL:** hết hạn theo thời gian được gán cho key.
- **Eviction:** Redis chủ động loại key vì chính sách `maxmemory`.
- **Deletion:** ứng dụng gọi `DEL`/`UNLINK`.
- **Persistence restore:** dataset có thể được khôi phục với TTL/expiration state tương ứng.

Đừng dựa vào eviction để sửa lỗi key không TTL trong một workload yêu cầu giữ dữ liệu đến một mốc chính xác. Với data quan trọng, chọn chính sách không bị eviction ngoài ý muốn.

## 5. Từ `used_memory` đến RAM thật của node

Các metric Redis thường gặp:

```redis
INFO memory
MEMORY STATS
INFO clients
```

Trong `INFO memory`, xem:

| Trường | Vai trò |
|---|---|
| `used_memory` | Memory Redis allocator đã cấp theo thống kê |
| `used_memory_dataset` | Bộ nhớ dataset theo Redis accounting |
| `used_memory_overhead` | Overhead theo thống kê Redis |
| `used_memory_rss` | RSS process do OS báo |
| `used_memory_peak` | Đỉnh cấp phát đã ghi nhận |
| `maxmemory` | Ngưỡng dùng cho eviction/ghi theo policy |
| `mem_fragmentation_ratio` | Dấu hiệu chênh lệch RSS/memory, cần đọc cùng các metric khác |
| `allocator_allocated` | Phần allocator đã cấp |
| `allocator_active` | Phần allocator đang active |
| `allocator_resident` | Phần memory allocator resident |
| `mem_not_counted_for_evict` | Một số buffer không tính vào memory dùng cho eviction |

Tên trường phụ thuộc phiên bản Redis và allocator, không mặc định mọi field luôn hiện diện.

### 5.1. `maxmemory` không phải cgroup limit

Redis có thể cấu hình:

```conf
maxmemory 8gb
maxmemory-policy noeviction
```

Nhưng nếu container memory limit cũng đúng 8 GiB, nó có thể bị OOM trước khi Redis chạm `maxmemory` do:

- Memory fragmentation.
- Client/replication/AOF buffers.
- Copy-on-write trong background save/rewrite.
- RDB/AOF child process.
- Page cache và memory accounting của container.
- Các process khác nếu dùng chung memory cgroup.

`maxmemory` phải được thiết lập có **headroom** so với RAM mà OS/container có thể cấp, dựa trên đo thực tế.

### 5.2. RSS, fragmentation và shared pages

Một Redis parent có RSS lớn hơn `used_memory` là chuyện có thể xảy ra. Khi `fork()` tạo child, nhiều physical pages ban đầu được chia sẻ giữa parent và child. Vì vậy:

- Không cộng RSS parent + RSS child một cách máy móc như thể tất cả page đều tách biệt.
- Không chỉ nhìn RSS parent rồi kết luận memory của cgroup còn dư.
- Đo **memory.current/working set, OOM events, swap**, cùng Redis INFO để hiểu đỉnh memory.
- Kiểm tra memory sau khi background job kết thúc, không chỉ steady state.

Đối với Kubernetes, `OOMKilled` có thể xảy ra dù Redis chưa báo `OOM command not allowed`: đó là hai giới hạn khác nhau.

## 6. Copy-on-write (COW): vùng RAM thường bị quên

RDB `BGSAVE` và AOF `BGREWRITEAOF` có thể sử dụng tiến trình con sau `fork()`. Ban đầu parent và child chia sẻ memory pages; khi parent sửa một page mà child còn cần đọc bản cũ, OS phải giữ hai bản vật lý.

```text
Ngay sau fork:
 parent ----+
            +---- memory page P
 child  ----+

Sau một write:
 parent -------- memory page P' (new)
 child  -------- memory page P  (old)
```

Chi phí phụ thuộc:

- Kích thước dataset.
- Số **memory pages bị thay đổi** khi child còn chạy.
- Thời gian background job kéo dài.
- Write rate và phân bố key được cập nhật.
- Redis allocator/OS behavior.
- Storage throughput và CPU của child.

**Không có công thức chắc chắn “COW luôn = 50% dataset” hay “BGSAVE luôn cần gấp đôi RAM”**. Cần đo ở tải gần production.

### 6.1. Vì sao disk chậm làm RAM peak tăng?

```text
Disk ghi snapshot chậm
      |
      v
RDB/AOF child tồn tại lâu
      |
      v
Parent tiếp tục thay đổi dữ liệu
      |
      v
Nhiều pages bị copy-on-write hơn
      |
      v
Memory pressure tăng
```

Vì vậy, storage capacity và memory capacity có liên hệ. Một ổ đĩa chậm không chỉ làm background job kéo dài mà còn có thể tăng cơ hội OOM khi write load cao.

### 6.2. Quan sát COW thực tế

```redis
INFO persistence
INFO stats
```

Tìm các field khi được Redis version hỗ trợ:

```text
rdb_last_cow_size
aof_last_cow_size
rdb_last_bgsave_time_sec
aof_last_rewrite_time_sec
latest_fork_usec
```

Các field thường ghi nhận lần job gần nhất; không được hiểu `rdb_last_cow_size` là toàn bộ cgroup memory đang dùng ở thời điểm đọc. Muốn chọn RAM limit, đo **đỉnh cgroup memory cùng thời điểm** với background job dưới đúng workload.

## 7. Lập ngân sách RAM cho Redis primary

Một công thức tư duy:

\[
M_{\text{required}} \gtrsim
M_{\text{steady resident}}
+
M_{\text{incremental COW peak}}
+
M_{\text{other non-overlapping pressure}}
+
M_{\text{safety margin}}
\]

Các thành phần này phải được đo tránh **double-count** phần đã nằm trong RSS/cgroup metrics.

Với ngân sách ban đầu, có thể chia:

```text
A. Dataset/projected Redis used_memory
B. Allocator fragmentation + resident overhead
C. Buffers: client, replication, AOF, command queues
D. Incremental COW peak khi persistence chạy
E. OS/page cache và background processes
F. Dự phòng tăng trưởng, burst, failover
```

Không nên áp một hệ số RAM chung cho mọi hệ thống. Cache read-mostly ít COW có profile khác với Stream/ZSet write-heavy và AOF rewrite thường xuyên.

### 7.1. Cần tính theo từng node

Với Redis Cluster:

```text
Primary A giữ 40% dữ liệu
Primary B giữ 30% dữ liệu
Primary C giữ 30% dữ liệu
```

Tổng RAM cluster 24 GiB không chứng minh mỗi primary 8 GiB là đủ; Primary A có thể cần nhiều hơn vì phân phối dữ liệu/hot slots không đều.

Đo:

- `used_memory` per primary.
- RAM peak per primary.
- Replication/reshard events trên mỗi node.
- Hot keys và giá trị lớn.
- Forecast của riêng shard.

**Capacity của Cluster được giới hạn bởi node nóng/yếu nhất**, không chỉ tổng RAM toàn cụm.

## 8. Replicas: chi phí không phải vài phần trăm

Một replica thường cần chứa bản sao dataset của primary tương ứng và quản lý connection/buffers/persistence theo cấu hình.

Ví dụ:

```text
1 primary + 2 replicas
```

không phải “một dataset và hai node nhẹ”. Nếu mỗi node thực sự chứa bản sao đầy đủ, tài nguyên memory/storage cần được cấp trên **cả ba data nodes**.

Một mô hình ngân sách:

\[
M_{\text{cluster data nodes}}
\approx
M_{\text{one role-equivalent node}}
\times
(1 + \text{replica count})
\]

Đây chỉ là quy mô thô khi các node có cấu hình tương tự. Replica có thể có write-apply, buffers, resync và persistence peak khác primary.

### 8.1. Full resynchronization có thể tạo peak

Khi replica mới tham gia hoặc mất liên kết quá lâu, nó có thể cần full resync. Tùy Redis version/config, quá trình này tiêu thụ:

- CPU/IO tạo hoặc truyền snapshot.
- Network bandwidth.
- Replication backlog/buffers.
- Memory pressure khi primary vẫn nhận write.
- Disk hoặc memory của replica khi load dataset.

Một hệ thống chỉ vừa đủ resource lúc steady state có thể không đủ tài nguyên **để tự phục hồi sau lỗi**.

### 8.2. Sentinel nodes cũng cần tài nguyên và độ độc lập

Sentinel thường nhẹ hơn data node về dataset nhưng vẫn cần:

- CPU/RAM cho process.
- Network tới data nodes và các Sentinel khác.
- File/config write permission.
- Monitoring/logging.
- Vị trí phân tán fault domains thích hợp.

Đặt ba Sentinel trên cùng một máy có thể đủ cho lab nhưng không mang lại khả năng chịu lỗi hạ tầng giống ba nodes độc lập.

## 9. Redis CPU: tính theo loại command, không chỉ ops/s

Redis có nhiều đường xử lý lệnh mà thời gian xử lý phụ thuộc dữ liệu và command mix.

Ví dụ:

```redis
GET small:key
SET small:key small-value
HGET user:42 name
ZRANGE leaderboard 0 100
SMEMBERS huge:set
EVAL long-script ...
```

Các lệnh này không có chi phí CPU giống nhau.

Những yếu tố chi phối CPU:

- Giá trị và response size.
- Độ phức tạp của command.
- Lua script loops.
- Compression/serialization của RDB.
- AOF rewrite.
- TLS encryption/decryption.
- Network packet processing.
- Key expiration và eviction.
- Replication/resharding.
- Các tác vụ background/threaded I/O tùy Redis version.

Không thể lấy “Redis xử lý 100.000 GET/s” làm bảo đảm rằng nó cũng xử lý 100.000 ZSet range queries/s với payload lớn.

### 9.1. Server command latency

Các lệnh quan sát hữu ích:

```redis
INFO cpu
INFO commandstats
SLOWLOG GET 20
LATENCY LATEST
```

Kết hợp:

- CPU usage per Redis instance/container.
- Commands/sec per type.
- Command execution latency.
- p95/p99 response latency tại application.
- Load của persistence/replication.
- Redis event loop/IO metrics phù hợp phiên bản.

`SLOWLOG` thường không bao gồm thời gian caller chờ network hoặc connection pool; vì vậy nếu Java p99 cao mà `SLOWLOG` rỗng, vẫn phải kiểm tra client queue, pool wait và network.

### 9.2. Cores và resource throttling

Redis thường có đường xử lý command chính chịu giới hạn xử lý tuần tự trên mỗi data node, dù một số hoạt động I/O có hỗ trợ threads. Cấp CPU rất nhiều cores cho một Redis process không bảo đảm command throughput tăng tuyến tính.

Trong Kubernetes, CPU quota thấp có thể gây throttling và tăng tail latency. Cần đo:

```text
container CPU usage
CPU throttling time/periods
Redis ops/s
Redis command latency
application p99
```

Cân nhắc tăng kích thước node, phân shard hoặc tối ưu workload nếu Redis đã saturation, thay vì chỉ tăng client connections.

## 10. Mạng: hai chiều command và response

Nhiều bài ước lượng mạng chỉ tính số lượng command:

```text
10.000 GET/s
```

nhưng không tính data transfer.

Một công thức sơ bộ:

\[
BW_{\text{app↔redis}} \approx
Q_{\text{ops/s}} \times
(B_{\text{request}} + B_{\text{response}})
\]

Ví dụ minh họa:

```text
10.000 operations/s
Request trung bình: 0,5 KiB
Response trung bình: 1,5 KiB

Tổng dữ liệu payload ≈ 20.000 KiB/s
                     ≈ 19,5 MiB/s
                     ≈ 164 Mbit/s
```

Con số chưa bao gồm TCP/TLS framing, retransmission, Redis protocol overhead, replication, metrics và overhead khác.

### 10.1. Read-heavy và write-heavy có network khác nhau

- GET trả value lớn: server → client bandwidth cao.
- SET value lớn: client → server bandwidth cao.
- Redis replica: primary → replica truyền replication stream.
- Redis Cluster: client kết nối đến nhiều node, resharding có chuyển key giữa nodes.
- Pub/Sub: một message có thể được fan-out tới nhiều subscribers.
- Stream consumers: batch/payload và ACK commands tạo traffic hai chiều.

Không dùng một đường mạng danh nghĩa 1 Gbit/s rồi giả định có toàn bộ 1 Gbit/s dành cho Redis nếu service mesh, TLS, overlay network và ứng dụng khác cùng sử dụng.

### 10.2. Latency theo khoảng cách mạng

Redis command nhỏ thường có server execution rất nhanh; **network RTT** có thể chi phối latency từ ứng dụng.

Ví dụ:

```text
App và Redis cùng zone: RTT thấp
App cross-zone: RTT tăng
App cross-region: RTT có thể cao hơn đáng kể
```

Các trị số phải đo theo vùng hạ tầng thực, không gán một con số RTT chung cho mọi cloud.

Nếu một HTTP request gọi Redis tuần tự 20 lần, dù mỗi GET chỉ tốn một RTT nhỏ, tổng latency có thể lớn. Batch/pipelining hoặc data model tốt có thể có lợi hơn tăng số Redis nodes.

## 11. Persistence: RAM và disk đi cùng nhau

Nếu Redis bật RDB và/hoặc AOF, storage không chỉ cần đủ chứa bộ file hiện tại.

### 11.1. RDB snapshot

`BGSAVE` có thể cần:

- Dung lượng cho file snapshot đang ghi.
- Dung lượng cho file snapshot cũ cho tới khi thay thế hoàn tất.
- CPU serialize/compression.
- Disk write throughput.
- Fork/COW memory headroom.

### 11.2. AOF và rewrite

Khi bật AOF:

```conf
appendonly yes
appendfsync everysec
```

Redis nối những thay đổi vào AOF theo policy. AOF rewrite sẽ tạo representation compact hơn, nhưng có thể cần:

- Active/base/incremental AOF components.
- File mới trong lúc rewrite.
- Disk bandwidth và fsync capacity.
- Fork/COW.
- Temporary space và metadata/manifest, đặc biệt với multi-part AOF trên Redis 7+.

**Không được lấy chỉ `aof_current_size` rồi đặt disk limit bằng chính số đó.** Trong rewrite hoặc backup, file cũ và file mới có thể cùng tồn tại, và page cache cũng tạo pressure.

### 11.3. Một cách tính disk budget

\[
D_{\text{needed}} \approx
D_{\text{active persistence}}
+
D_{\text{temporary rewrite/snapshot peak}}
+
D_{\text{local backups, if any}}
+
D_{\text{logs and growth}}
+
D_{\text{margin}}
\]

Trong đó dữ liệu phải đo theo Redis version, policy và cấu trúc dữ liệu. Không nên coi một hệ số “2× RDB” hay “3× AOF” là bảo đảm.

### 11.4. Disk throughput có tác động tới p99

Nếu rewrite kéo dài vì disk chậm, COW memory có thể tăng và Redis gặp pressure. Với AOF `appendfsync always` hoặc `everysec`, fsync delay cũng có thể ảnh hưởng write latency/durability window.

Thu:

```redis
INFO persistence
INFO stats
```

cùng OS metrics:

```text
disk used/free bytes
free inodes
read/write throughput
IOPS
I/O latency
filesystem errors
cgroup memory/page cache
```

Với managed Redis, các chỉ số tương tự có thể xuất hiện qua monitoring nhà cung cấp thay vì SSH vào host.

## 12. Spring Data Redis driver: phân biệt Lettuce và Jedis

Trong ứng dụng Java, driver cũng tiêu thụ:

- Memory cho connection và command buffers.
- Thread/event loop.
- Socket/file descriptor.
- Serialization/deserialization buffers.
- Connection pool objects.
- CPU TLS/network handling.
- Pending requests và retry queues.

### 12.1. Lettuce: shared native connection và multiplexing

Lettuce, dựa trên Netty, thường cho phép nhiều lệnh thông thường dùng **một native connection thread-safe**.

```text
HTTP thread A -- GET  -->+
HTTP thread B -- GET  -->+-- Lettuce shared connection -> Redis
HTTP thread C -- SET  -->+
```

Điều đó **không** có nghĩa `RedisConnection` wrapper của Spring luôn có thể chia sẻ tùy tiện giữa thread, hoặc các thao tác blocking/transaction/pubsub đều dùng cùng cơ chế.

Các thao tác như `BLPOP`, blocking Streams, subscription, transaction thường cần quản lý connection riêng theo cách client/factory hỗ trợ.

### 12.2. Jedis: pool thường giữ vai trò khác

Với Jedis, connection object không nên chia sẻ đồng thời tùy tiện giữa các threads. Pool giúp tái sử dụng sockets cho những tác vụ cần borrow/release.

Vì vậy một cấu hình:

```yaml
spring:
  data:
    redis:
      jedis:
        pool:
          max-active: 16
```

có thể ảnh hưởng trực tiếp đến borrowing ở đường synchronous Jedis, trong khi cấu hình Lettuce pool chưa chắc tác động tới phần lớn GET nếu factory đang dùng shared native connection.

**Không chọn kích thước pool theo số HTTP workers mà không hiểu connection semantics của driver.**

## 13. Tính ngân sách connection theo toàn deployment

Giả sử có:

```text
12 Spring Boot pods
Mỗi pod:
  1 Lettuce shared/native connection cho thao tác thường
  1 pool dedicated tối đa 20 connections
  2 long-lived Redis Streams subscriptions
```

Trần pooled dedicated connections:

\[
12 \times 20 = 240
\]

Còn phải tính thêm shared/long-lived, pool/factory khác, client/admin/monitoring, rolling deployments, Cluster node discovery và reconnect bursts.

Đây là **trần cấu hình giả định**, không phải số socket thực luôn mở.

### 13.1. Một biểu mẫu ngân sách connection

| Nguồn connection | Số instances | Connection tối đa/instance | Tổng ước lượng |
|---|---:|---:|---:|
| API instances | 12 | 20 pooled | 240 |
| Worker instances | 4 | 8 pooled | 32 |
| Shared native connections | Theo factory/node | Theo client | Đo thực |
| Streams/PubSub listeners | Theo consumers | Theo topology | Đo thực |
| Monitoring/exporter | Theo deployment | Theo tool | Dự phòng |
| Rollout surge | Old + new pods | Theo cấu hình | Dự phòng |
| Các ứng dụng khác | n | n | Phải kiểm kê |

Redis `CONFIG GET maxclients` và giới hạn file descriptors của OS là những ràng buộc cần đối chiếu. Một client connection có thể dùng memory buffers; tăng `maxclients` không tự tạo thêm CPU capacity.

### 13.2. `INFO clients` không phải số request concurrent

```redis
INFO clients
CLIENT LIST
INFO stats
```

Có thể nhìn thấy `connected_clients`, `blocked_clients`, `rejected_connections`. Tuy nhiên:

- Một shared Lettuce connection có thể có nhiều in-flight commands.
- Nhiều pooled idle connections vẫn làm `connected_clients` tăng.
- `blocked_clients` là trạng thái ở Redis server, **khác** với số Java callers đang chờ mượn pool.
- Trên Redis Cluster, cần xem **từng node**.

Do đó phải ghép server metrics với client/pool metrics.

## 14. Cấu hình Spring Boot cho Lettuce với pool giới hạn

Ví dụ cho Spring Boot 3.x:

```yaml
spring:
  data:
    redis:
      client-type: lettuce
      host: redis-primary.internal
      port: 6379
      connect-timeout: 2s
      timeout: 2s
      lettuce:
        pool:
          enabled: true
          max-active: 16
          max-idle: 8
          min-idle: 2
          max-wait: 300ms
```

Dependency khi sử dụng Commons Pool 2:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.apache.commons:commons-pool2'
}
```

Tên property và default phụ thuộc Spring Boot version. Nếu dùng factory tự viết, một số Boot properties có thể không được áp dụng; cần xác nhận bean `RedisConnectionFactory` thực tế.

### 14.1. Ý nghĩa cấu hình

| Property | Điều chỉnh |
|---|---|
| `connect-timeout` | Deadline tạo kết nối |
| `timeout` | Deadline command theo client/Boot |
| `pool.enabled` | Bật đường pooling được Boot/client hỗ trợ |
| `max-active` | Giới hạn connections active trong pool đó |
| `max-idle` | Số idle connections giữ lại |
| `min-idle` | Mức idle pool cố gắng duy trì |
| `max-wait` | Thời gian chờ borrow khi pool cạn |

`max-wait` **khác** command timeout. Borrow failure có thể xảy ra trước khi một Redis command được gửi tới server.

### 14.2. Pool không tự tăng throughput

Với Lettuce shared connection, tăng `max-active` có thể **không thay đổi** những GET/SET thông thường. Ngược lại, nếu phần lớn connections đang giữ `XREAD BLOCK`, pool có thể bị cạn nhanh.

Muốn tuning, đo:

```text
pool active / idle / waiters
borrow wait duration
Redis commands/s
Redis command p95/p99
application endpoint p95/p99
Redis CPU/network
```

Không chỉ nhìn `connected_clients`.

## 15. Netty event loops và native memory của Lettuce

Lettuce sử dụng Netty và các client resources để quản lý I/O. Trong một JVM, có thể có:

- I/O event-loop threads.
- NIO/direct buffers.
- Command queue/pending futures.
- DNS/TLS buffers.
- Connection state và topology refresh.
- Thread-local/cache/allocator overhead.
- Metrics/tracing metadata.

Một ứng dụng có `-Xmx2g` không chắc chỉ dùng 2 GiB RAM, vì **JVM process memory = heap + non-heap + native**.

Nếu tạo nhiều `RedisClient`/`LettuceConnectionFactory` và không chia sẻ hoặc đóng resources phù hợp, số threads, connections và buffers có thể tăng.

### 15.1. Không tạo Redis client trong từng request

Sai về kiến trúc:

```java
@GetMapping("/products/{id}")
public String get(@PathVariable String id) {
    // Tạo RedisConnectionFactory/RedisClient mới cho mỗi HTTP request?
    // -> thêm socket, thread/resource và kết nối không cần thiết.
}
```

Thường nên khai báo `RedisConnectionFactory` và `RedisTemplate` là Spring beans có vòng đời ứng dụng, rồi tái sử dụng hợp lý.

Nếu có nhu cầu nhiều factories cho cache, Streams và Pub/Sub, hãy tính tài nguyên tổng của chúng, không để mỗi factory tự dùng bộ event-loop threads quá lớn mà không có lý do.

### 15.2. Pending commands và memory pressure

Một lỗi nguy hiểm:

```text
Application tạo 100.000 Redis commands rất nhanh
Redis server chỉ xử lý được 10.000/s
      |
      v
Client pending queue tăng
      |
      v
Memory/futures/buffers tăng
      |
      v
Timeout + retry
      |
      v
Thêm pending commands
```

Tăng số connections không sửa căn nguyên khi arrival rate lớn hơn service capacity. Cần **backpressure hoặc concurrency limit** ở nguồn, retry có giới hạn và queue bound phù hợp.

## 16. Tính tài nguyên ứng dụng Spring Boot

Không chỉ Redis Server cần RAM/CPU. Một Spring Boot process dùng Redis còn cần:

\[
M_{\text{JVM process}} \approx
M_{\text{heap}}+
M_{\text{metaspace}}+
M_{\text{code cache}}+
M_{\text{thread stacks}}+
M_{\text{direct/native}}+
M_{\text{other}}
\]

Đây là mô hình kiểm kê, các thành phần thực tế phải đo bằng công cụ JVM/OS để tránh double-count.

### 16.1. Heap

Heap chứa:

- DTO/value khi deserialize Redis response.
- HTTP request/response objects.
- Cache nội bộ Java nếu có.
- Reactor publishers/futures.
- Queues và batch buffers.
- Data transformation objects.
- Connection/pool management objects.

Nếu Redis trả JSON 100 KiB, object graph Java sau deserialize có thể lớn hơn 100 KiB. Đừng tính memory app chỉ dựa trên network payload bytes.

### 16.2. Thread stacks

Spring MVC, background workers, Pub/Sub listener executors và scheduler threads đều có stack memory.

Một ví dụ **không phải hằng số cho mọi JVM**:

```text
400 threads × stack reservation ~1 MiB
=> khoảng 400 MiB virtual stack address space
```

Physical memory thực được commit có thể khác với reserved virtual stack, tùy JVM/OS và mức sử dụng. Không nhân `-Xss` với thread count rồi coi đó là RSS chính xác; hãy đo native memory/thread stacks thực.

### 16.3. Native/direct memory

Netty, TLS, NIO, compression, JNI và các thư viện native có thể tiêu thụ memory ngoài Java heap. Đặt `-Xmx` bằng đúng container memory limit tạo rủi ro OOM.

Ví dụ minh họa:

```text
Pod memory limit = 4 GiB
JVM -Xmx        = 3.0 GiB
```

Phần 1 GiB còn lại **có thể hoặc không đủ**, tùy số threads, direct buffers, metaspace, code cache, agents và workload. Không có tỷ lệ cố định an toàn cho mọi Spring Boot service.

Để sizing đúng, đo memory.current/cgroup, JVM heap/non-heap, GC, thread count và Netty/direct memory dưới tải peak.

### 16.4. CPU và GC

Nếu Redis trả nhiều object lớn hoặc code deserialize JSON liên tục, CPU/Garbage Collection phía Java có thể là bottleneck ngay cả khi Redis command latency thấp.

Quan sát:

```text
JVM process CPU
GC pause p95/p99
allocation rate
heap occupancy
thread utilization
event loop blocking
Redis command duration
end-to-end API duration
```

Không tăng Redis node size để sửa một vấn đề thực chất nằm ở Jackson serialization hay Java GC.

## 17. Spring MVC: HTTP threads không bằng Redis connections

Trong Spring MVC:

```text
Tomcat/Servlet worker
      |
      v
Service
      |
      v
StringRedisTemplate -> Redis
      |
      v
Thread chờ result
```

Nếu mỗi HTTP request gọi Redis nhiều lần, một request có thể tạo nhiều lệnh. Số HTTP worker threads có thể giới hạn request concurrency, nhưng **không bắt buộc mỗi thread phải giữ một TCP connection Redis** với Lettuce shared native connection.

### 17.1. Tính command demand từ HTTP traffic

Ví dụ:

```text
HTTP throughput:            1.000 requests/s
Redis commands per request: 4
=> Redis demand:            4.000 commands/s
```

Nếu 4 lệnh gọi tuần tự, request có thể chịu khoảng bốn lần network/command latency. Nếu code bắn chúng đồng thời, concurrency/in-flight commands tăng và memory buffers khác đi.

Cần đo command mix theo từng endpoint, không dùng một con số `Redis ops/s` bình quân cho tất cả.

### 17.2. Giới hạn thread cũng là một dạng backpressure

Tăng Tomcat worker threads từ 200 lên 1.000 có thể khiến nhiều request đồng thời đổ vào Redis, database và payment gateway. Nếu downstream không có capacity, p99 có thể xấu hơn.

Khi sizing Spring MVC, xem cùng lúc:

- HTTP concurrency/queue.
- Thread count.
- Redis connection semantics.
- DB pool size.
- Retry policy.
- Load balancer timeout.
- Request deadline.

## 18. WebFlux và ReactiveRedisTemplate: tính in-flight thay vì chỉ thread

Reactive Redis cho phép nhiều thao tác bất đồng bộ mà không giữ một blocking thread cho mỗi lệnh. Nhưng không có nghĩa tài nguyên vô hạn.

Ví dụ nguy cơ:

```java
return Flux.fromIterable(productIds)
        .flatMap(id ->
            reactiveRedis.opsForValue()
                .get("cache:product:" + id)
        );
```

Nếu danh sách rất lớn và nhiều HTTP requests cùng chạy, tổng in-flight commands có thể tăng nhanh.

### 18.1. Giới hạn concurrency tường minh

```java
public Flux<String> getProducts(List<String> ids) {
    int redisConcurrency = 16;

    return Flux.fromIterable(ids)
        .flatMap(
            id -> reactiveRedis.opsForValue()
                .get("cache:product:" + id),
            redisConcurrency
        );
}
```

Con số 16 chỉ là ví dụ. Cần tính:

```text
16 concurrent Redis operations / request
× 100 requests in-flight / pod
× 12 pods
= tối đa về mặt mô hình tới 19.200 operations in-flight
```

Phép nhân là một **upper-bound về fan-out ở một thời điểm** nếu tất cả request cùng đạt mức concurrency, không phải throughput hoặc số Redis connections. Reactor scheduling, shared client và tốc độ upstream có thể làm thực tế khác.

Không dùng một giới hạn `flatMap(concurrency=16)` rồi coi toàn deployment chỉ có 16 lệnh đồng thời. Nếu cần giới hạn cấp pod, dùng bulkhead/semaphore hoặc admission control ở phạm vi shared, với behavior khi quá tải được thiết kế rõ.

### 18.2. Backpressure và payload lớn

Reactive backpressure có thể giới hạn phát phần tử xuống subscriber, nhưng một lệnh như `SMEMBERS huge:set` vẫn có thể tạo response rất lớn trước khi phía Java xử lý từng item. Để giới hạn memory cần dùng command/data model phân trang, `SCAN`, range hoặc chunking phù hợp.

### 18.3. Không `.block()` trên event-loop

Nếu dùng WebFlux, gọi `.block()` trên thread event-loop có thể làm nghẽn xử lý I/O và tăng latency khi tải cao, khiến các phép đo Redis sai lệch.

Cần đo Redis RTT riêng và event-loop blocking/CPU riêng. Thêm Redis connections không cứu được một event-loop bị block.

## 19. Dùng Little's Law để kiểm tra concurrency

Trong hệ thống ổn định:

\[
L \approx \lambda \times W
\]

Với:

- \(L\): số operations trung bình cùng tồn tại trong hệ thống đo.
- \(\lambda\): số operations hoàn thành mỗi giây.
- \(W\): thời gian trung bình một operation ở hệ thống đó.

Ví dụ:

```text
3.000 Redis operations/s
Average application-observed Redis latency = 15 ms
```

Thì:

\[
L \approx 3000 \times 0.015 = 45
\]

Tức trung bình có khoảng 45 Redis operations in-flight hoặc đang chờ trên phạm vi đo, nếu điều kiện ổn định và cách đếm nhất quán.

**Không suy luận cần pool 45 connections**:

- Lettuce shared connection có thể multiplex.
- Jedis dedicated pool occupancy phụ thuộc borrow duration.
- Chỉ số trung bình không phản ánh burst hoặc p99.
- Lệnh có thể đợi pool, Netty queue, network hoặc Redis server.
- Khi đã saturation, tăng concurrency có thể làm \(W\) tăng mà \(\lambda\) không tăng.

Little's Law giúp kiểm tra tính hợp lý của số đo, không thay benchmark.

## 20. Pool sizing: tránh “max-active bằng số HTTP threads”

Một mô hình tốt hơn:

```text
Pool active demand
    = số thao tác đang giữ dedicated connections
```

Đo:

- Số blocking consumers (`BLPOP`, `XREAD BLOCK`).
- Số concurrent transactions/session callbacks.
- Số Jedis callers cần borrow.
- Số dedicated Lettuce operations theo configuration.
- Thời gian giữ connection.
- Pool borrow waiters.
- Peak và failure-mode occupancy.

### 20.1. Tại sao blocking commands đặc biệt?

```redis
BLPOP queue:jobs 0
```

có thể đợi rất lâu. Nếu 20 workers đều giữ dedicated connection, pool `max-active=10` có thể làm 10 workers bị block ở borrow, chưa hề gửi lệnh tới Redis.

Cần:

- Đếm blocking workers.
- Đặt `BLOCK` timeout phù hợp.
- Đồng bộ command timeout lớn hơn thời gian chờ hợp lệ khi cần.
- Tách pool/factory cho workload blocking nếu chúng cạnh tranh với request path.
- Theo dõi Redis `blocked_clients` và Java pool waiters riêng.

### 20.2. Pub/Sub cũng có long-lived connections

`RedisMessageListenerContainer` có subscription connection sống lâu và callback executor. Thêm listener threads không đồng nghĩa thêm một Redis connection cho mỗi thread. Handler chậm có thể gây backlog ở Java dù Redis subscription vẫn khỏe.

Phân biệt:

```text
Subscription socket
Listener dispatch executor
Business handler concurrency
Downstream DB/API capacity
```

Tối ưu đúng bottleneck thay vì tăng pool ngẫu nhiên.

## 21. Cache-miss fallback và nguy cơ khuếch đại tải

Một cache chỉ có ích khi nguồn dữ liệu gốc không bị quá tải lúc Redis mất hoặc cache cold.

Ví dụ:

```text
Bình thường:
  10.000 product reads/s
  cache hit ratio = 95%
  DB reads ≈ 500/s

Khi Redis mất:
  10.000 reads/s phải fallback
  DB reads có thể tăng lên tới 10.000/s
```

Đây là **mức tăng tới 20 lần** với các giả định trên, nếu mọi request đều fallback, không có coalescing/rate limiting và không có cache khác.

Nếu database chỉ chịu được 2.000 reads/s ở latency yêu cầu, hệ thống có thể ngừng phục vụ dù Redis là “cache không thiết yếu”.

### 21.1. Cần ngân sách dự phòng cho fallback

Thiết kế ít nhất:

- Đo cache hit ratio theo từng resource/endpoint.
- Đo DB capacity khi cache miss tăng.
- Giới hạn fallback concurrency.
- Dùng request coalescing/single-flight khi nhiều request cùng miss một key.
- TTL jitter hoặc background refresh tránh hết hạn đồng loạt.
- Circuit breaker/bulkhead khi Redis hoặc DB lỗi.
- Chọn failure policy rõ: trả dữ liệu stale, degrade, từ chối có kiểm soát hay truy vấn trực tiếp.

**Không tăng Redis client pool để giải quyết một database đã quá tải do fallback**.

### 21.2. Cache warm-up cũng cần ngân sách

Sau deploy/restore:

```text
Cache cold
    |
    v
Nhiều request miss
    |
    v
Database load tăng
    |
    v
Ứng dụng ghi lại cache
    |
    v
Redis write throughput tăng
```

Vừa DB read vừa Redis write đều có burst. Một capacity test chỉ chạy trên cache nóng sẽ đánh giá thiếu tài nguyên giai đoạn khởi động.

## 22. Redis Cluster: tài nguyên theo hash slot, hot shard và failover

Redis Cluster chia 16.384 hash slots lên nhiều primary. Tổng capacity còn phụ thuộc phân phối key và traffic.

```text
Primary A:  35% memory, 60% operations
Primary B:  33% memory, 25% operations
Primary C:  32% memory, 15% operations
```

Dù memory tương đối đều, Primary A vẫn là CPU/network hotspot.

### 22.1. Hash tags có thể tạo hot slot

Ví dụ:

```text
cart:{customer-42}:items
cart:{customer-42}:total
```

cùng slot là hữu ích nếu cần multi-key transaction.

Nhưng:

```text
cache:{ALL}:product:1
cache:{ALL}:product:2
...
```

dồn toàn bộ product keys vào một slot, khiến Cluster không phân phối tải như mong đợi.

Chọn hash tag theo đơn vị nguyên tử nghiệp vụ thật sự cần cùng slot, không dùng tag chung chỉ để dễ viết `MGET`.

### 22.2. Khi mất một primary

Trong Cluster có replica, failover có thể khiến replica thành primary mới. Ở giai đoạn đó:

- Client reconnect/reroute.
- Command retries có thể tăng.
- Replication may be lagging.
- CPU/network của các node còn lại có thể tăng.
- Warm-up/resharding có thể phát sinh traffic phụ.
- Một số write đã ACK có thể chưa được replica mới nhận.

Capacity test nên bao gồm **degraded-mode**, không chỉ steady state. Một cụm vừa đủ tải ở bình thường có thể không phục vụ ổn định trong failover.

### 22.3. Scale-out không giải quyết mọi lệnh

Thêm primary có thể giúp phân phối key và throughput, nhưng:

- Multi-key commands thường cần same-slot.
- Lua scripts chỉ chạy trong phạm vi node/slot phù hợp.
- Hot key không tự phân tán.
- Clients cần topology discovery/redirect.
- Rebalance/resharding có cost network và CPU.
- Dữ liệu và connection distribution không đảm bảo cân bằng ngay.

Đừng tính Cluster capacity = throughput của một primary × số primary mà không benchmark phân phối key thực tế.

## 23. Sentinel: tài nguyên cho failover và replica promotion

Trong Sentinel topology, khi primary ngừng hoạt động:

```text
Primary down
  -> Sentinel phát hiện/đồng thuận
  -> replica promote
  -> clients discover new primary
  -> application reconnect
```

Ngoài Redis data nodes, cần:

- Sentinel quorum khỏe.
- Network kết nối giữa Sentinel, data nodes và application.
- Driver configuration để hỏi primary mới.
- Connection/timeout/retry budgets.
- Đủ RAM/CPU/IO trên replica khi được thăng cấp.
- Kiểm thử khi primary cũ quay lại và đồng bộ lại.

**Đừng cấp replica máy yếu hơn primary chỉ vì nghĩ replica chỉ nhận dữ liệu.** Sau failover, replica có thể phải chịu toàn bộ write workload của primary.

## 24. RDB/AOF, durability và lựa chọn storage

Resource plan phải gắn với mục tiêu mất dữ liệu:

| Chế độ | Lợi ích | Chi phí/rủi ro |
|---|---|---|
| Không persistence | Giảm background disk work | Dữ liệu trên node không tự khôi phục sau restart |
| RDB | Snapshot compact | Fork/COW, disk, có thể mất write từ mốc snapshot |
| AOF `everysec` | Ghi thay đổi với fsync định kỳ | Disk/fsync, rewrite/COW, không cam kết RPO đúng 1 giây mọi sự cố |
| AOF `always` | Yêu cầu fsync thường xuyên hơn | Disk latency/throughput có thể bị ảnh hưởng |
| Replica | Data copy và failover | Tốn thêm node; replication thường bất đồng bộ |

`WAIT` hoặc cấu hình min-replicas có thể ảnh hưởng rủi ro mất ghi/availability nhưng **không biến Redis thành distributed durable transaction**.

Với dữ liệu thanh toán/đơn hàng cần invariant mạnh, Redis có thể là cache/idempotency supporting system nhưng nguồn sự thật cần lưu ở storage có bảo đảm transaction phù hợp.

## 25. Chọn CPU/RAM requests và limits trên Kubernetes

Kubernetes có hai lớp cấu hình phổ biến:

- **Requests:** giúp scheduler tính tài nguyên dành cho pod.
- **Limits:** giới hạn resource ở runtime theo cơ chế container/cgroup; memory vượt limit có thể dẫn tới OOM-kill, CPU quota có thể tạo throttling.

Ví dụ minh họa **cho Redis container**, không phải manifest production hoàn chỉnh:

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: redis-cache
spec:
  serviceName: redis-cache
  replicas: 1
  selector:
    matchLabels:
      app: redis-cache
  template:
    metadata:
      labels:
        app: redis-cache
    spec:
      containers:
        - name: redis
          image: redis:7.2.5-alpine
          ports:
            - containerPort: 6379
          command:
            - redis-server
            - --maxmemory
            - 5gb
            - --maxmemory-policy
            - allkeys-lru
          resources:
            requests:
              cpu: "500m"
              memory: "6Gi"
            limits:
              cpu: "2"
              memory: "10Gi"
```

Đây là **ví dụ giáo dục**, không có persistence volume, authentication, network policy, readiness/liveness, anti-affinity hoặc HA. Không triển khai nguyên xi lên production.

Các con số không tạo ra quy tắc chung: `maxmemory 5gb`, request 6Gi và limit 10Gi phải được thay bằng dữ liệu đo. Với write-heavy AOF/RDB, biên COW có thể khiến 10Gi không đủ.

### 25.1. Vì sao Redis thường cần StatefulSet/PVC hoặc managed Redis?

Nếu có persistence và yêu cầu khôi phục state trên disk, Kubernetes pod mất có thể kéo theo ephemeral filesystem. Cần:

- PersistentVolumeClaim và storage class phù hợp.
- Chiến lược backup ngoài node.
- Thử restore khi pod/node bị thay thế.
- Security/ACL/TLS.
- Pod placement/anti-affinity theo fault domains.
- Monitoring storage latency và free space.
- Quy trình nâng cấp/rolling failover.

Redis cache hoàn toàn tái tạo được có thể dùng phương án khác, nhưng **không được gọi Redis stateful durable nếu không có storage lifecycle rõ ràng**.

### 25.2. JVM app requests và limits

Ví dụ **application pod**:

```yaml
resources:
  requests:
    cpu: "500m"
    memory: "1Gi"
  limits:
    cpu: "2"
    memory: "3Gi"
```

Bên cạnh đó cần thiết lập JVM heap/direct memory/threading cho container, đo GC và native memory dưới traffic peak.

Không đặt `-Xmx3g` trong container limit 3Gi rồi giả định đủ RAM cho thread stacks, metaspace và Netty. Cần dự phòng non-heap/native dựa trên quan sát.

### 25.3. Rolling deployment có thể nhân tải tạm thời

Nếu 12 pods đang chạy mà rolling strategy cho phép thêm 3 pods trong lúc rollout:

```text
Pods cũ: 12
Pods mới đồng thời: 3
=> 15 pods kết nối Redis
```

Connection count, warm-up, authentication handshakes và cache traffic đều có thể tăng. Capacity plan phải tính **max surge**, không chỉ desired replicas.

## 26. Ví dụ tính ngân sách Redis RAM từng bước

Giả sử một hệ thống cache sản phẩm có các số **đã được giả định để minh họa**:

```text
Số key hiện tại:                     3.000.000
Bộ nhớ bình quân/key đo từ staging:   1,4 KiB
Hệ số tăng số lượng dữ liệu:          1,5 lần
Tỷ số RSS/used_memory quan sát:       1,20
COW peak trong thử nghiệm BGSAVE:     2 GiB
OS/page-cache pressure dự phòng:     1 GiB
Safety margin bổ sung:               20%
```

### Bước 1 — RAM logic cho dataset hiện tại

\[
M_{\text{current}}
= 3{,}000{,}000 \times 1.4\ \text{KiB}
= 4{,}200{,}000\ \text{KiB}
\approx 4.0\ \text{GiB}
\]

### Bước 2 — Tăng trưởng dự kiến

\[
M_{\text{future}}
\approx 4.0 \times 1.5
= 6.0\ \text{GiB}
\]

Con số này chỉ là **projection từ mẫu**, cần cộng/đo những memory overhead khác nếu chưa được phản ánh trong mẫu.

### Bước 3 — Ước lượng RSS steady-state

\[
M_{\text{RSS steady}}
\approx 6.0 \times 1.20
= 7.2\ \text{GiB}
\]

Tỷ số RSS/used_memory có thể thay đổi khi dataset, allocator và workload thay đổi. Đây là ước lượng, không phải hằng số.

### Bước 4 — Cộng pressure lớn đã được quan sát

```text
Steady-state RSS projection:   7,2 GiB
Incremental COW peak:          2,0 GiB
Other pressure allowance:      1,0 GiB
------------------------------
Subtotal:                     10,2 GiB
```

Một phần OS/page cache có thể đã được tính trong metrics cgroup đo được; trong mô hình minh họa này giả định đây là **phần tăng thêm không trùng**. Khi dùng số đo production phải tránh double-count.

### Bước 5 — Chừa biên dự phòng

\[
M_{\text{budget}}
\approx 10.2 \times 1.2
= 12.24\ \text{GiB}
\]

Có thể chọn một mức cấp phát như **14–16 GiB cho container/node** để có thêm headroom, nhưng **không xem đây là kết luận triển khai** khi chưa chạy benchmark và kiểm tra storage/replication.

### Bước 6 — Chọn `maxmemory` có chủ đích

Nếu projection `used_memory` của dataset là khoảng 6 GiB, đặt `maxmemory` ngay sát container limit sẽ không phù hợp. Một điểm bắt đầu có thể là `maxmemory` quanh 6,5–7 GiB, **nếu chính sách eviction cho phép và các overhead đã đo cho phép**, rồi xác nhận lại bằng test.

Cần trả lời:

- Nếu `maxmemory` đạt trước, cache eviction được chấp nhận không?
- Nếu policy `noeviction`, ứng dụng xử lý lỗi ghi ra sao?
- COW peak dưới write surge có vượt số đo 2 GiB không?
- Replica cũng có peak tương tự không?
- Disk chậm có khiến child sống lâu hơn không?
- Cgroup có bị OOM trong failover/full resync không?

Đây là quy trình **sizing theo giả định → đo → điều chỉnh**, không phải công thức xác định chính xác instance type chỉ từ số key.

## 27. Ví dụ tính CPU và network budget

Giả sử Redis primary nhận:

```text
GET:        8.000/s
SET:        1.500/s
HGET:         400/s
INCR:         100/s
-------------------
Tổng:      10.000 commands/s
```

Nếu response/payload bình quân theo command mix xấp xỉ 2 KiB hai chiều, network payload ~19,5 MiB/s như ví dụ trước.

Nhưng **không thể tự suy ra CPU cores** từ 10.000 commands/s. Cần benchmark latency/cpu trên chính loại command và dữ liệu.

Một phương pháp:

1. Chạy workload đại diện ở 2.500 ops/s.
2. Ghi CPU, memory, throughput, p95/p99.
3. Tăng lên 5.000, 10.000, 15.000 ops/s.
4. Xem ở đâu p99 hoặc error rate vượt SLO.
5. Lặp lại khi có BGSAVE/AOF rewrite.
6. Lặp lại với replica/full resync hoặc failover.
7. Đặt operating target **dưới điểm saturation** có headroom rõ ràng.

### 27.1. Không scale tuyến tính máy móc

Nếu 5.000 ops/s dùng 30% CPU, không chắc 20.000 ops/s dùng đúng 120% CPU vì:

- Payload và command mix có thể thay đổi.
- Cache hit/miss và TTL khác.
- Network/TLS overhead không tuyến tính.
- Disk persistence tạo burst.
- Queueing và scheduler effects tăng gần saturation.

Chỉ dùng phép nội suy CPU để định hướng, không dùng thay kết quả tải thực.

## 28. Đo tài nguyên ứng dụng từ phản hồi Redis

Một Redis response 2 KiB có thể biến thành object Java lớn hơn sau deserialize. Khi app xử lý nhiều lệnh đồng thời:

```text
Number of in-flight responses
× average decoded object footprint
≈ application live memory from Redis results
```

Đây là một thành phần trong tổng JVM heap, không phải mô hình heap đầy đủ.

Nếu một pipeline lấy 10.000 values, mỗi value 4 KiB wire size:

```text
Response bytes khoảng 40 MiB trước overhead
```

Java objects, `List<Object>`, deserializer buffers và application transforms có thể làm heap peak tăng đáng kể.

Một batch nhỏ hơn có thể tiết kiệm heap và giảm GC p99, dù tổng số command không đổi.

### 28.1. Giới hạn batch và concurrency trước khi tăng RAM

Các điều chỉnh:

- Pagination/range thay vì tải toàn bộ Set/List/Stream.
- Pipeline batch bounded.
- Limit Reactor flatMap concurrency.
- Bounded queues cho background tasks.
- Tránh giữ full response lists khi có thể xử lý từng phần.
- Theo dõi allocation rate và GC.
- Dùng key/value serialization phù hợp, tránh payload metadata không cần thiết.

Tăng JVM heap đôi khi cần thiết, nhưng giảm dữ liệu không cần thiết thường rẻ hơn và an toàn hơn.

## 29. Metrics tối thiểu cho capacity plan

### 29.1. Redis Server

```redis
INFO memory
INFO clients
INFO stats
INFO commandstats
INFO cpu
INFO persistence
INFO replication
```

Chỉ số:

| Nhóm | Metric |
|---|---|
| Memory | used_memory, RSS, peak, allocator, fragmentation |
| Client | connected_clients, blocked_clients, rejected_connections |
| Commands | ops/s, per-command stats, slowlog |
| Network | input/output bytes/sec hoặc tương đương |
| CPU | user/system CPU, throttling từ host/container |
| Persistence | BGSAVE/rewrite duration, fork latency, COW, delayed fsync |
| Replication | link status, offsets, full sync, replica count |
| Errors | OOM, READONLY, timeout, connection errors, rejected connections |
| Keyspace | key count/TTL/expirations/evictions |
| Disk | free bytes, inodes, IOPS, write latency |

### 29.2. Spring Data Redis client

- Redis command duration p50/p95/p99.
- Connect time/error.
- Reconnect attempts.
- Pool active/idle/waiters/borrow time nếu pooling được dùng.
- Pending commands/queue depth nếu client instrumentation có.
- Timeout/exception theo operation type.
- Retry count và jitter/backoff.
- Serialization/deserialization overhead.
- Thread/event-loop CPU và task queues.

Không giả định Spring Boot tự có sẵn một metric tên `redis.pool.active` trên mọi phiên bản; đo từ client/Micrometer/JMX phù hợp.

### 29.3. Business/Application

- HTTP p95/p99 và success rate.
- Cache hit/miss/error/fallback.
- DB connection pool usage và DB latency.
- Session failure.
- Stream processing delay/pending count.
- Lock/idempotency error.
- JVM heap/native memory/GC.
- Pod restarts/OOMKilled.
- Autoscaling events.

### 29.4. Theo dõi từng node/role

Với Redis Cluster hoặc primary+replica:

```text
redis_node
role: primary/replica
cluster/shard
environment
service owner
```

Không dùng user ID/key value làm Prometheus label. Giữ cardinality thấp và phân biệt resource từng node để tránh trung bình hóa che mất hot shard.

## 30. Capacity alerts: cảnh báo có hành động

Một số cảnh báo hữu ích:

| Tín hiệu | Rủi ro | Hành động |
|---|---|---|
| Cgroup memory gần limit + COW đang tăng | OOM kill | Điều tra write rate, persistence, headroom |
| Redis `used_memory` gần maxmemory | Eviction hoặc write rejection | Xem TTL, key count, policy |
| `evicted_keys` tăng bất thường | Cache miss/Session loss | Phân biệt dữ liệu được phép eviction |
| Pool waiters tăng + borrow timeout | App pool saturation | Tìm blocking consumers/leak |
| `rejected_connections` tăng | `maxclients`/FD hoặc connection storm | Xem pods/factories/rollouts |
| Command p99 tăng + Redis CPU cao | Server saturation | Xem command mix/hot key |
| Disk free thấp khi rewrite | Persistence failure | Dọn theo runbook an toàn/tăng volume |
| Replication lag lớn | RPO/failover risk | Kiểm tra network, replica health |
| Stream oldest pending age cao | SLA event bị đe dọa | Handler/reclaim/DB load |
| Cache fallback tăng + DB pool gần đầy | User impact sắp xảy ra | Rate limit/coalescing/cache recovery |

Không mặc định mọi tín hiệu là page. Mức severity nên gắn với **SLO, data criticality và hành động cụ thể**, không chỉ một ngưỡng CPU 80%.

## 31. Benchmark cho Redis và ứng dụng Spring Data Redis

Một phép thử capacity phải đi qua **ứng dụng thật** trong một phần workload, không chỉ bắn raw Redis commands.

### 31.1. Benchmark từng lớp

**Redis-only benchmark**

- Đo khả năng server với command mix đại diện.
- Tách network/Java overhead để hiểu bottleneck server.
- Không suy luận đây là throughput end-to-end app.

**Spring Data Redis benchmark**

- Dùng chính Lettuce/Jedis version, serializer, connection factory.
- Đo template/ReactiveRedisTemplate operations.
- Bao gồm cache hit/miss, payload sizes, blocking operations.
- Đo JVM heap/GC, driver queues/pool metrics.

**End-to-end benchmark**

- Chạy user journeys qua HTTP/worker.
- Có database, message handlers, authentication tương ứng.
- Đo p95/p99 business latency và lỗi.
- Đánh giá fallback khi Redis unavailable.

### 31.2. Kịch bản cần thử

| ID | Điều kiện | Mục tiêu |
|---|---|---|
| CAP-01 | Baseline read-heavy | Latency GET/SET |
| CAP-02 | Tải ghi cao | CPU, COW, AOF bandwidth |
| CAP-03 | Dataset lớn gần forecast | RSS, maxmemory, eviction |
| CAP-04 | Cache cold sau restart | DB fallback, warm-up burst |
| CAP-05 | BGSAVE đang chạy | Memory peak và fork latency |
| CAP-06 | BGREWRITEAOF | Disk pressure, fsync, COW |
| CAP-07 | Replica full resync | Network và memory headroom |
| CAP-08 | Primary failover | Client reconnect, RTO/RPO |
| CAP-09 | Rolling deployment nhiều pods | Connection storm, warm-up |
| CAP-10 | Redis chậm/timeout | Pending queue, retry amplification |
| CAP-11 | Cluster resharding | Hot shard, MOVED/ASK, routing |
| CAP-12 | Stream backlog | Blocking connections, handler capacity |
| CAP-13 | TLS enabled | CPU/network overhead |
| CAP-14 | Large response/pipeline | JVM heap/native memory peak |

Không nhất thiết mọi test chạy mỗi pull request; nhóm resilience/load có thể chạy định kỳ trên staging cô lập, nhưng cần có trước rollout có thay đổi lớn về dữ liệu hoặc topology.

### 31.3. Kết quả phải ghi rõ điều kiện

Một báo cáo nên có:

```text
Redis version/distribution:
Redis topology:
Spring Boot / Spring Data Redis / Lettuce/Jedis versions:
Redis data type mix:
Key count / value size distribution:
HTTP RPS and Redis ops/s:
Cache hit ratio:
Client concurrency / pool config:
Persistence / TLS / replica config:
Pod CPU and memory requests/limits:
Network topology:
Dataset warm/cold:

p50/p95/p99 latency:
Error/timeout rate:
Redis CPU/memory/RSS peak:
Cgroup memory peak / OOM events:
Disk IOPS/latency:
Network throughput:
Connections/pool waiters:
Replica lag:
Degraded-mode behavior:
```

Nếu không ghi điều kiện benchmark, một lần đo có throughput cao không đủ làm căn cứ sizing production.

## 32. Dùng `Testcontainers` để xác nhận cấu hình nhưng đừng thay capacity benchmark

Testcontainers với Redis thật rất hữu ích để kiểm thử:

- Redis version và command behavior.
- Serializer/TTL/CacheManager.
- Lua scripts.
- Memory policy ở data size vừa.
- Redis auth/ACL.
- Spring Data Redis reconnect ở mức integration.

Nhưng container test nhỏ trên laptop không chứng minh Redis sẽ hoạt động tốt với hàng triệu keys, hàng trăm connections và AOF rewrite nhiều GiB.

Phân tầng:

```text
Unit tests
   |
   v
Redis Testcontainers integration tests
   |
   v
Staging load/capacity tests
   |
   v
Failover/restore/chaos drills
```

Mỗi tầng trả lời câu hỏi khác nhau. Không gọi một lần `SET`/`GET` trên Redis container là đã hoàn thành capacity planning.

## 33. Autoscaling ứng dụng không làm Redis tự mở rộng

Trong Kubernetes, HPA có thể tăng Spring Boot pods từ 8 lên 20 khi CPU/traffic tăng. Nhưng Redis server vẫn là một dependency chung.

```text
HPA scale out
    |
    v
Nhiều Spring pods
    |
    +-- Nhiều Redis connections
    +-- Nhiều cache GET/SET
    +-- Nhiều retries nếu lỗi
    +-- Nhiều DB fallback requests
    |
    v
Redis/DB saturation
```

Autoscaling có thể vô tình làm sự cố lớn hơn nếu downstream không theo kịp.

### 33.1. Thêm giới hạn admission ở tầng ứng dụng

Các lựa chọn:

- Per-pod concurrency cap.
- Per-service global traffic limit khi có hệ thống điều phối phù hợp.
- Bounded executor queues.
- Retry budgets và exponential backoff.
- Circuit breaker/bulkhead.
- Work-queue backpressure.
- Scale-down/up policy tránh churn và reconnect storm.

Cần chú ý: một semaphore đặt riêng trên mỗi pod không tạo **global cap**. Tính tổng qua số pods tối đa và rollout surge.

### 33.2. Kubernetes requests không tự là SLO

Pod không OOM, CPU không throttling và Redis `PING` thành công không đủ kết luận user journey đạt SLO. Theo dõi business p95/p99, availability và correctness song song với resource metrics.

## 34. Tối ưu chi phí mà không giảm độ tin cậy

Để giảm cloud bill, có thể cân nhắc:

1. **Giảm dữ liệu thừa**: TTL hợp lý, tránh key không còn dùng, nén payload khi thực sự hiệu quả.
2. **Chọn data type phù hợp**: Hash thay nhiều Strings trong một aggregate nếu hợp lý.
3. **Giảm round trips**: pipeline/batch trong giới hạn driver, tránh GET lặp.
4. **Tối ưu key cardinality**: tránh namespace tạo vô hạn keys.
5. **Phân tầng cache**: cache tại app/CDN cho dữ liệu phù hợp để giảm Redis traffic.
6. **Chọn eviction policy theo dữ liệu**: cache có thể eviction, state quan trọng không.
7. **Tách workload**: tránh cache eviction ảnh hưởng session/lock.
8. **Tuning pool theo số đo**: giảm idle sockets không cần thiết.
9. **Scale theo bottleneck**: memory, CPU, network, storage hay hot shard.
10. **Chọn độ bền phù hợp**: không bật cơ chế đắt tiền trên dữ liệu hoàn toàn tái tạo nếu không cần; không tắt durability cho dữ liệu quan trọng.

### 34.1. Chi phí HA phải tính đầy đủ

Một primary 16 GiB với hai replicas không phải chi phí một node 16 GiB. Cần tính:

```text
Primary compute + memory
Replica compute + memory
Storage volume/snapshots
Network replication traffic
Sentinel/Cluster management
Monitoring/logging
Backup retention
Cross-zone/cross-region transfer (nếu có)
```

Nếu hạ tầng phân tán nhiều AZ, network charges và replication latency có thể đáng kể. Không chọn topology chỉ dựa trên giá RAM/GB.

## 35. Mẫu worksheet capacity planning

Một worksheet (có thể đưa vào spreadsheet vận hành) gồm các cột:

| Trường | Ví dụ nhập | Nguồn đo |
|---|---|---|
| Redis role | `product-cache` | Architecture inventory |
| Data criticality | Rebuildable cache | Product owner |
| Current keys | 3.000.000 | `INFO keyspace`/sampling |
| Future keys | 4.500.000 | Growth forecast |
| Measured RAM/key | 1,4 KiB | Staging Redis sample |
| Projected `used_memory` | ~6 GiB | Calculation |
| RSS multiplier | 1,20 | Benchmark/INFO |
| COW peak | 2 GiB | BGSAVE/rewrite load test |
| Container memory target | 14–16 GiB (illustrative) | Envelope + test |
| `maxmemory` | Theo policy/benchmark | Redis config |
| Ops/s peak | 10.000 | Production traces |
| GET/SET ratio | 80/20 | Commandstats/app |
| Average payload | 2 KiB two-way | Sample |
| Redis p99 target | Theo service SLO | SLO |
| Replica count | 2 | HA design |
| AOF/RDB policy | Measured deployment config | Redis config |
| Disk peak | Theo rewrite/backup test | Storage telemetry |
| App pods peak | 15 including rollout | HPA/rollout |
| Client type | Lettuce | Spring config |
| Pool and connection cap | Theo dedicated demand | Pool metrics |
| App heap/native RAM | Theo load test | JVM/cgroup |
| DB fallback budget | Theo cache outage drill | DB metrics |
| Failure headroom | Theo failover simulation | Staging drill |

Không để ô trống quan trọng được âm thầm hiểu là 0. Ghi rõ `UNKNOWN`, owner cần đo và thời điểm dự kiến cập nhật nếu chưa có dữ liệu.

## 36. Kịch bản triển khai từng bước

### Bước 1 — Chốt workload

Lấy production metrics hiện có; phân nhóm cache/session/lock/Streams. Định nghĩa forecast số key, payload và traffic cho 3–6–12 tháng phù hợp kế hoạch kinh doanh.

### Bước 2 — Kiểm tra data model

Tạo dataset thử nghiệm sát kiểu dữ liệu thật. Dùng `MEMORY USAGE`, `INFO memory`, key cardinality, TTL distribution để ước lượng dataset growth.

### Bước 3 — Chọn topology và failure model

Standalone, Sentinel hay Cluster? Có bao nhiêu replicas? Muốn chịu lỗi một node, một AZ hay hơn? RPO/RTO là gì? Resource plan phải cấp cho degraded-state, không chỉ bình thường.

### Bước 4 — Dự kiến CPU/RAM/network/disk

Tạo envelope cho mỗi Redis data node, client/app pods và đường network. Dự phòng COW, full sync, burst, rollout surge, disk rewrite.

### Bước 5 — Cấu hình driver

Chọn Lettuce/Jedis. Với Lettuce, xác định shared connection và dedicated workload; với Jedis, đo pool demand. Đặt connect/command/borrow timeouts và resource limits phù hợp.

### Bước 6 — Cấu hình ứng dụng

Giới hạn concurrency, Reactor fan-out, batch size, thread/executor count, retry budgets. Không tạo Redis client mỗi request và không giữ connection qua I/O ngoài Redis.

### Bước 7 — Load test trên staging

Chạy workload bình thường, peak, cache cold, persistence, failover và reconnect. Đo toàn bộ app/Redis/downstream p99 cùng cgroup memory.

### Bước 8 — Điều chỉnh bằng số đo

Nếu:

```text
Redis CPU thấp, pool wait cao -> xem pool/dedicated connection contention.
Redis CPU cao, pool wait thấp -> xem command mix/scale Redis.
RSS/cgroup sát limit khi BGSAVE -> tăng headroom hoặc tối ưu job/IO.
DB overload khi cache miss -> giảm fallback fan-out hoặc mở DB capacity.
```

Thay một biến mỗi lần để biết tác động của nó.

### Bước 9 — Đặt cảnh báo và runbook

Alert theo business SLO cùng các tín hiệu resource gần saturation. Có playbook cho OOM, disk full, connection storm, failover, hot shard và cache outage.

### Bước 10 — Kiểm tra lại sau thay đổi

Mỗi khi Redis version, Spring Boot/Lettuce/Jedis version, serializer, TTL policy, số pods, topology hoặc persistence policy thay đổi, năng lực tài nguyên có thể thay đổi. Capacity plan phải được cập nhật định kỳ, không phải tài liệu làm một lần.

## 37. Những hiểu lầm dễ gây sự cố

**“Redis dùng 5 GiB `used_memory` thì container RAM 5 GiB là đủ.”** Sai: RSS, COW, buffers, page cache và overhead khác có thể vượt limit.

**“`maxmemory` là tổng RAM process không thể vượt.”** Sai: Redis maxmemory không tương đương cgroup memory limit.

**“Snapshot chạy background nên không tốn resource.”** Sai: fork/COW, CPU và disk vẫn tạo pressure.

**“BGSAVE luôn cần gấp đôi RAM.”** Không đúng cho mọi workload; COW phụ thuộc pages bị sửa khi child còn chạy.

**“AOF `everysec` nghĩa là mọi write mất tối đa đúng một giây trong mọi crash.”** Không có cam kết tuyệt đối như vậy.

**“Replica chỉ cần ít RAM vì chủ yếu đọc.”** Sai: replica giữ bản sao dataset và có thể phải thành primary sau failover.

**“Cluster 3 primary nghĩa là capacity đúng gấp ba.”** Không chắc: hot key/slot, resharding và network có thể tạo giới hạn.

**“Số HTTP threads phải bằng số Redis connections.”** Không đúng với Lettuce shared/multiplexed operations.

**“Lettuce pool max-active=64 nghĩa là mọi GET dùng 64 socket.”** Không mặc định khi factory chia sẻ native connection cho regular commands.

**“Jedis và Lettuce dùng cùng pool config chắc cùng hiệu năng.”** Sai: connection semantics khác nhau.

**“Tăng pool size luôn làm Redis nhanh hơn.”** Có thể chỉ tăng queueing, resource consumption và server saturation.

**“Reactive Redis không dùng thread chờ nên concurrency vô hạn.”** Sai: vẫn có command queues, buffers, network và server capacity.

**“`flatMap(concurrency=16)` giới hạn toàn hệ thống ở 16 lệnh.”** Sai: giới hạn trên từng subscription/operator; nhiều requests và pods làm tổng concurrency tăng.

**“Redis command p99 tốt nghĩa là toàn HTTP p99 tốt.”** Không nếu app GC, serialization, DB fallback hoặc thread pool đang chậm.

**“Cache mất vẫn có DB nên không cần dự phòng.”** Sai: fallback có thể khuếch đại DB load rất mạnh.

**“Scale Spring Boot pods thì Redis cũng scale theo.”** Không: Redis là downstream dependency riêng.

**“Disk volume chỉ cần bằng kích thước RDB hiện tại.”** Sai: snapshot/rewrite, backup và growth có thể cần thêm không gian.

**“Một Redis Testcontainers test pass đủ cho capacity planning.”** Không: functional integration test không thay production-scale load/failure tests.

**“Redis `connected_clients` thấp là không có nhiều operations đang chờ.”** Không chắc: Lettuce có multiplexing.

**“Không có SLOWLOG nghĩa là Redis không gây latency.”** Không: pool wait, network, client queue và fork pause có thể chưa phản ánh ở SLOWLOG.

**“Mọi Redis key đều được eviction an toàn khi hết memory.”** Sai: session/lock/idempotency/state có thể không được phép mất.

**“Dùng số trung bình payload là đủ.”** Không: p99 value size, batch responses và Stream retention có thể tạo memory spikes.

## 38. Checklist trước khi triển khai

### 38.1. Redis data và memory

- [ ] Có inventory các kiểu key, TTL, số key hiện tại và forecast.
- [ ] Đã đo RAM/key với Redis version và serializer tương ứng.
- [ ] Đã đo `used_memory`, RSS và allocator behavior.
- [ ] Có số đo COW peak khi BGSAVE/AOF rewrite.
- [ ] `maxmemory` nhỏ hơn giới hạn RAM với headroom đã kiểm chứng.
- [ ] Eviction policy phù hợp tính chất dữ liệu.
- [ ] Không bỏ sót key không TTL hoặc Stream retention.

### 38.2. CPU, disk, network

- [ ] Có command mix và throughput peak.
- [ ] Có p95/p99 Redis latency và CPU peak.
- [ ] Đã tính request/response payload throughput hai chiều.
- [ ] Có network budget cho replication và failover.
- [ ] Có disk space peak cho RDB/AOF và rewrite.
- [ ] Đã kiểm tra fsync/disk throughput và thời gian restore.
- [ ] Có headroom cho full resync/resharding.

### 38.3. Redis driver

- [ ] Biết Spring Data Redis dùng Lettuce hay Jedis.
- [ ] Đã xác nhận shared native vs dedicated/pooled connection.
- [ ] Có ngân sách connection theo pods/factories/nodes.
- [ ] Đã tính các blocking consumers và Pub/Sub subscriptions.
- [ ] Có connect/command/borrow timeout phù hợp deadline.
- [ ] Có metrics pool waiters, rejected connections và reconnect.
- [ ] Không tạo driver/client mới trên mỗi request.

### 38.4. Spring Boot application

- [ ] JVM heap và native memory được đo dưới peak.
- [ ] Không đặt Xmx bằng toàn bộ memory limit nếu còn non-heap/native.
- [ ] Có concurrency/batch size limit cho reactive/batch workloads.
- [ ] HTTP/worker threads được chọn theo downstream capacity.
- [ ] Không retry mù những thao tác không idempotent.
- [ ] Có cache fallback/DB capacity plan.
- [ ] Có bảo vệ chống cache stampede/cold start.
- [ ] Autoscaling tính cả connection surge.

### 38.5. Vận hành

- [ ] Có load test production-like và degraded-mode.
- [ ] Có per-node metrics cho Cluster/replicas.
- [ ] Có SLO/error-budget alert và resource saturation alerts.
- [ ] Có runbook cho OOM, disk full, failover và high p99.
- [ ] Có kế hoạch rollback deployment khi latency/error rate xấu.
- [ ] Có lịch cập nhật capacity forecast theo growth.

## 39. Kết luận

**Tính tài nguyên cho Redis, trình điều khiển và ứng dụng** trong Spring Data Redis là bài toán nhiều tầng, cần bắt đầu từ **dữ liệu và hành vi nghiệp vụ** rồi mới chọn kích thước node hay cấu hình pool.

Những nguyên tắc quan trọng nhất:

1. **Đo RAM Redis bằng dữ liệu thật**, vì payload bytes không bao gồm toàn bộ object/allocator overhead.
2. **Tách `used_memory`, RSS, COW và cgroup memory**; `maxmemory` không phải RAM limit toàn tiến trình.
3. **Tính cả persistence, replication và failover**, vì background fork, AOF rewrite và full resync có thể tạo resource peak.
4. **Tính network từ payload và topology**, không chỉ số lệnh/giây.
5. **Đo CPU theo command mix**, nhất là Lua, collection commands, TLS và background jobs.
6. **Hiểu Lettuce/Jedis trước khi chỉnh pool**; shared/multiplexed connection, dedicated connections và blocking consumers có nhu cầu khác nhau.
7. **Tính connection budget theo toàn deployment**, kể cả app pods, factories, listeners, Cluster nodes và rolling surge.
8. **Tính JVM heap lẫn native memory**, giới hạn Reactor/worker concurrency và tránh unbounded command queues.
9. **Kiểm tra cache cold/fallback**, vì Redis outage có thể làm database chịu tải gấp nhiều lần.
10. **Benchmark ở peak và failure scenarios**, rồi chọn headroom theo SLO, không theo một hệ số mặc định.

Một capacity plan đúng không phải bảng số CPU/RAM được ước lượng một lần, mà là **một mô hình có giả định, số liệu đo, ngưỡng cảnh báo, phương án chịu lỗi và quy trình kiểm chứng lại** khi workload, phiên bản hoặc topology thay đổi.
