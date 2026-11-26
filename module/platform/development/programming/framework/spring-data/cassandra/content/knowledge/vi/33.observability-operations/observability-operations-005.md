# Quan sát heap, GC, compaction và áp lực lưu trữ

Trong ứng dụng **Spring Data Cassandra**, một request chậm không nhất thiết bắt nguồn từ truy vấn CQL viết sai. Độ trễ có thể tăng vì **heap của ứng dụng Java bị áp lực**, **Garbage Collection (GC) dừng luồng quá lâu**, **node Cassandra đang compaction nhiều SSTable**, hoặc **ổ đĩa gần đầy** khiến các tác vụ nền cạnh tranh I/O với đọc/ghi. Các yếu tố này có quan hệ qua lại, nên quan sát hiệu năng phải kết nối **application → Java Driver → Cassandra coordinator/replica → disk**.

Bài học thuộc chương **Quan sát và vận hành** của **SPRING_DATA_CASSANDRA**. Mục tiêu là xác định đúng thành phần cần đo, đọc được các tín hiệu về heap/GC/compaction/storage, phân tích tình huống thực tế, và chọn cách xử lý an toàn với mô hình dữ liệu phân tán của Cassandra. Các tên metric và khả năng công cụ có thể khác theo phiên bản Cassandra, Java Driver, Spring Boot và hệ thống giám sát; hãy đối chiếu với phiên bản đang triển khai.

## 1. Bốn nhóm tín hiệu liên quan với nhau như thế nào?

Hình dung một service ghi sự kiện, tra cứu theo tenant và trả dữ liệu qua repository:

```text
HTTP request
    |
    v
Spring Service / CassandraRepository / CassandraTemplate
    |               JVM ỨNG DỤNG
    |               - heap / allocation / GC pause
    |               - pool / driver timeouts
    v
CqlSession / Cassandra Java Driver
    |
    v
Cassandra Coordinator
    |               JVM NODE CASSANDRA
    |               - heap / off-heap / GC
    |               - request queues / read latency
    v
Replica(s)
    |               LƯU TRỮ & TÁC VỤ NỀN
    |               - memtable, commit log
    |               - SSTables, compaction, tombstones
    |               - disk space / disk I/O
    v
Read / Write result
```

Một chuỗi vấn đề điển hình:

1. Ứng dụng liên tục xóa hoặc cập nhật nhiều dữ liệu, tạo thêm **tombstone** và SSTable mới.
2. Compaction cần đọc và ghi lại SSTable; khi phát sinh quá nhiều, compaction backlog tăng.
3. Ổ đĩa bận hoặc dung lượng khả dụng giảm, read/write latency tăng.
4. Driver phải chờ lâu hơn; request đang chờ tích tụ ở ứng dụng.
5. Ứng dụng giữ thêm object, response buffer hoặc context request; allocation và GC pressure có thể tăng.
6. p99 ở API tăng, dù logic của repository và CQL chưa thay đổi.

Chiều ngược lại cũng xảy ra: ứng dụng trả một tập kết quả quá lớn, mapping rất nhiều entity và gây **GC ở JVM ứng dụng**, trong khi Cassandra node vẫn khỏe. Vì vậy, khi thấy biểu đồ “heap cao”, câu hỏi đầu tiên là: **heap của tiến trình nào?**

| Nhóm | Nơi quan sát | Tín hiệu quan trọng | Câu hỏi chẩn đoán |
| --- | --- | --- | --- |
| JVM ứng dụng | Spring Boot / Micrometer / JFR | Heap used/committed/max, allocation, GC pause, thread count | API chậm do mapping, buffering hoặc GC của service? |
| JVM Cassandra | JMX / exporter / GC log | Heap, GC pause/frequency, CPU, off-heap/direct memory | Node bị dừng hoặc thiếu tài nguyên để phục vụ request? |
| Compaction | JMX / `nodetool compactionstats` | Pending tasks, running compactions, bytes processed, thời gian | SSTable mới có được hợp nhất kịp tốc độ ghi/TTL không? |
| Lưu trữ | Host/container metrics / `nodetool tablestats` | Disk used/free, IOPS, latency, SSTable size/count, snapshots | Còn chỗ cho ghi mới, compaction, streaming và phục hồi? |
| Đường truy vấn | Driver + server metrics | p95/p99, timeout, retries, tombstones read, partitions | Vấn đề gắn với query/partition nào? |

## 2. Phân biệt heap, off-heap, page cache và dung lượng đĩa

**Heap JVM** là vùng bộ nhớ được GC quản lý. Nhưng bộ nhớ của một tiến trình Cassandra không chỉ gồm heap:

- **Heap**: nhiều cấu trúc Java, đối tượng request và metadata; cách sử dụng tùy phiên bản và cấu hình.
- **Off-heap/direct/native memory**: một số bộ đệm, bộ nhớ native và thành phần Cassandra/driver; không phản ánh đầy đủ trong biểu đồ `jvm_memory_used_bytes{area="heap"}`.
- **OS page cache**: RAM do hệ điều hành dùng để cache dữ liệu SSTable trên đĩa; phần này có thể rất quan trọng với đọc Cassandra.
- **Disk**: commit log, SSTable, index, snapshot, dữ liệu đang streaming và các file tạm trong quá trình vận hành.

Đừng kết luận “node còn nhiều heap nên còn nhiều RAM”: hệ điều hành và native buffers vẫn có thể thiếu RAM. Cũng đừng kết luận “RAM used gần 100%” là xấu nếu phần lớn là page cache có thể thu hồi. Cần tách **process RSS, JVM heap, off-heap và OS memory available**.

Trong Spring Data Cassandra, application JVM cũng có các tầng bộ nhớ: entity được materialize bởi `CassandraTemplate`, collections trả về từ repository, object DTO và buffer của Java Driver. Một truy vấn đọc hàng trăm nghìn dòng rồi gọi `toList()` có thể tạo pressure ngay ở service, kể cả khi câu CQL trên server chạy hợp lệ.

### Bộ chỉ số tối thiểu về bộ nhớ

| Chỉ số | Ý nghĩa | Cách đọc thận trọng |
| --- | --- | --- |
| Heap used / max | Mức chiếm dụng heap tại thời điểm đo | “Used cao” sau warmup chưa đủ chứng minh rò rỉ; xem đồ thị sau GC và xu thế. |
| Old generation / live set sau GC | Khối lượng object tồn tại lâu | Tăng đều sau nhiều chu kỳ GC là tín hiệu cần điều tra. |
| Allocation rate | Số byte object mới/giây | Tăng đột ngột có thể đến từ query mapping, page size hoặc traffic. |
| GC pause p95/p99, tổng thời gian GC | Tần suất và thời gian luồng bị dừng | So mốc pause với spike latency/timeouts. |
| Direct / off-heap / RSS | Bộ nhớ ngoài heap hoặc tổng footprint | Phát hiện áp lực RAM không thể hiện trong heap. |
| OS available memory / page faults | Khả năng phục vụ workload và cache | Swapping hoặc major page faults tăng làm latency xấu đi. |

Không có một tỷ lệ heap dùng cố định nào là “an toàn” cho mọi collector. Cần nhìn **chu kỳ giải phóng heap, GC overhead, khoảng dự phòng và tải thực tế**.

## 3. Quan sát JVM của ứng dụng Spring Data Cassandra

Nếu ứng dụng dùng Spring Boot với Actuator và Micrometer, có thể xuất metric JVM qua endpoint cho Prometheus hoặc hệ giám sát tương đương.

Ví dụ cấu hình định hướng:

```yaml
# application.yml — ví dụ, cần có actuator + registry tương ứng
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  metrics:
    tags:
      application: order-service
```

Cấu hình endpoint `prometheus` phụ thuộc dependency registry và chính sách bảo mật. Trong production cần giới hạn truy cập, tránh công khai health details/metrics nhạy cảm ra Internet. Những meter có thể quan sát gồm bộ nhớ, GC, CPU và thread; tên cụ thể thay đổi theo registry/binder và phiên bản.

Các nhóm metric Micrometer/Prometheus thường gặp:

```promql
# Ví dụ tên metric phổ biến; kiểm tra tên thật sau khi scrape.
jvm_memory_used_bytes{area="heap"}
jvm_memory_max_bytes{area="heap"}
jvm_gc_pause_seconds_count
jvm_gc_pause_seconds_sum
process_resident_memory_bytes
process_cpu_usage
```

**Lưu ý về biểu đồ:** đếm `jvm_gc_pause_seconds_count` là số sự kiện GC, còn `jvm_gc_pause_seconds_sum` là tổng thời gian GC. `rate(...[5m])` cho biết tần suất hoặc thời gian GC trên mỗi giây quan sát; nó **không phải p99 GC pause**. Để đọc percentiles, cần histogram/phân phối phù hợp hoặc công cụ phân tích GC/JFR, thay vì chỉ lấy tổng chia số lần.

Một tỷ số tham khảo:

```promql
# Tỷ lệ heap used / max của một ứng dụng.
# Chỉ có ý nghĩa khi các series tương ứng cùng nhãn và max hữu hạn.
sum by (instance) (jvm_memory_used_bytes{area="heap"})
/
sum by (instance) (jvm_memory_max_bytes{area="heap"})
```

Không gộp mọi instance thành một giá trị trung bình nếu mục tiêu là tìm **một instance** bị GC hoặc memory pressure. Khi đặt dashboard, phân nhóm tối thiểu theo ứng dụng, instance/pod và môi trường triển khai.

### Đo từng thao tác truy cập Cassandra ở tầng ứng dụng

Spring Data repository có thể gọi nhiều query hoặc materialize nhiều object. Tạo meter ứng dụng với **tag cardinality thấp** để tìm thao tác gây áp lực:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

public final class EventQueryFacade {

    private final EventReader reader;
    private final MeterRegistry registry;

    public EventQueryFacade(EventReader reader, MeterRegistry registry) {
        this.reader = reader;
        this.registry = registry;
    }

    public List<EventView> recent(UUID tenantId, Instant from, int limit) {
        Timer.Sample sample = Timer.start(registry);
        boolean success = false;

        try {
            List<EventView> result = reader.recent(tenantId, from, limit);
            success = true;
            return result;
        } finally {
            sample.stop(Timer.builder("app.cassandra.read.duration")
                    .tag("operation", "events_recent")
                    .tag("outcome", success ? "success" : "error")
                    .register(registry));
        }
    }
}
```

Ở đây `EventReader`, `EventView` là những interface/DTO do ứng dụng tự định nghĩa. Đoạn code minh họa vị trí đặt timer; không thay thế việc đo cả đường HTTP. **Không đặt `tenantId`, primary key, câu CQL nguyên văn hoặc exception message làm metric label** vì cardinality rất cao và có thể làm lộ dữ liệu.

Kết hợp ba góc nhìn để định vị áp lực:

- HTTP p99 tăng, `app.cassandra.read.duration` vẫn thấp, app GC pause tăng → kiểm tra mapping ngoài đoạn timer, serialization, thread pool và request processing.
- `app.cassandra.read.duration` tăng, driver timeout tăng, app GC bình thường → điều tra Cassandra node, network, consistency và query.
- Cả app GC và Cassandra latency tăng → có thể có tương quan hai chiều; cần xem chuỗi thời gian và thay đổi workload trước khi kết luận nguyên nhân.

## 4. Quan sát heap và GC trên node Cassandra

Cassandra chạy trên JVM riêng với ứng dụng. Thu thập JVM metrics cho **từng node**, không chỉ coordinator hoặc một máy đại diện. Những nguồn chính:

1. **JMX** của Cassandra, qua exporter/agent được quản trị vận hành cấu hình.
2. **GC logs** của JVM đang chạy, thu thập và phân tích các pause dài, allocation và độ thường xuyên.
3. **JFR/JVM tooling** nếu phiên bản JVM và chính sách triển khai cho phép.
4. **OS metrics**: CPU, available memory, RSS, swap, disk I/O, file descriptor, network.

Ví dụ các MBean chuẩn của Java:

```text
java.lang:type=Memory
java.lang:type=MemoryPool,name=...
java.lang:type=GarbageCollector,name=...
java.nio:type=BufferPool,name=direct
```

Cassandra còn xuất metrics riêng qua JMX, chẳng hạn các nhóm **ClientRequest**, **Table/Keyspace**, **Compaction** và **ThreadPools**. **Tên MBean/counter chính xác cần kiểm tra ở phiên bản đang chạy**, đặc biệt khi dùng JMX exporter map chúng sang Prometheus.

### Đọc đúng biểu đồ GC

Một đồ thị heap dạng “răng cưa” — tăng khi allocation, giảm sau GC — thường là hành vi bình thường. Cần xem:

- **Tần suất GC**: cùng traffic nhưng GC xảy ra dày hơn hay không?
- **Pause duration**: p95/p99 và pause cực đại có trùng với timeout/app latency spike không?
- **Old generation/live set sau GC**: có dần tăng theo thời gian mặc dù tải đã giảm?
- **CPU spent on GC**: collector có tiêu thụ tỷ lệ CPU bất thường, cạnh tranh với request processing?
- **Bộ nhớ ngoài heap và RSS**: áp lực RAM có thể hiện ở server GC hay đến từ native/page cache?
- **Restart/OOM**: tăng heap đơn giản có thể che dấu chứ chưa giải quyết phân bố dữ liệu hoặc query gây allocation cao.

Không mặc định “cứ tăng `-Xmx` là sửa được GC”. Tăng heap có thể tăng headroom, nhưng cũng thu hẹp RAM dành cho page cache hoặc tác động đến hành vi GC, phụ thuộc collector/JVM. Cấu hình heap cần dựa trên kích thước dataset, tải, RAM vật lý, container limit và hướng dẫn phù hợp phiên bản Cassandra.

### Ví dụ thu thập GC logs

Với JVM hỗ trợ Unified Logging (chẳng hạn Java 11/17), cấu hình dạng sau minh họa việc xoay vòng log:

```text
-Xlog:gc*,safepoint:file=/var/log/cassandra/gc.log:time,uptime,level,tags:filecount=10,filesize=20M
```

Đây là **ví dụ JVM option**, không phải lệnh chạy trực tiếp trên node đang phục vụ traffic. Đường dẫn, quyền ghi file, tên service, Java version và cấu hình logging hiện tại cần được kiểm tra trước khi áp dụng; việc đổi JVM arguments thường đòi hỏi kế hoạch restart phù hợp.

Một dòng GC pause dài chỉ là **triệu chứng**. Phân tích cùng timestamp của request timeout, compaction activity, allocation, disk I/O và workload mới đưa tới nguyên nhân đáng tin.

## 5. Compaction là gì và tại sao ảnh hưởng hiệu năng?

Cassandra ghi dữ liệu qua cơ chế LSM-tree: cập nhật đi vào memtable/commit log rồi flush thành SSTable bất biến. Theo thời gian, một logical row có thể xuất hiện trong nhiều SSTable. **Compaction** đọc và ghi lại các SSTable theo chiến lược cấu hình để hợp nhất phiên bản dữ liệu, quản lý tombstone và cải thiện read path.

Những việc compaction có thể tiêu tốn:

- **Disk I/O**: đọc SSTable cũ, ghi SSTable mới.
- **CPU và memory**: xử lý key, metadata, nén/giải nén tùy cấu hình.
- **Disk headroom**: SSTable đầu ra cần được ghi trước khi file đầu vào đủ điều kiện xóa.
- **Băng thông lưu trữ** cạnh tranh với read/write/streaming.

Vì vậy, một node có **heap chưa đầy** vẫn có thể chậm do compaction làm nghẽn I/O. Một node có rất nhiều SSTable cũng có thể phải đọc nhiều cấu trúc dữ liệu hơn để trả lời một truy vấn.

### Các chiến lược compaction và cách đọc workload

| Chiến lược | Đặc điểm tổng quát | Khi quan sát cần chú ý |
| --- | --- | --- |
| STCS (SizeTieredCompactionStrategy) | Nhóm SSTable kích thước gần nhau, thường hợp lý với một số write-heavy workload | Số SSTable, read amplification, disk headroom khi compaction |
| LCS (LeveledCompactionStrategy) | Sắp xếp dữ liệu thành level để kiểm soát overlap | Write amplification, pending work, ổn định read latency |
| TWCS (TimeWindowCompactionStrategy) | Gom SSTable theo cửa sổ thời gian | Phù hợp với một số workload time-series/TTL nếu ghi và hết hạn theo thời gian đủ nhất quán; chú ý dữ liệu đến trễ/timestamp |

**Không chọn TWCS chỉ vì bảng có cột timestamp.** Việc có cập nhật cũ, xóa không đồng đều hoặc phân phối TTL phức tạp có thể làm hành vi compaction/tombstone khác dự kiến. Cần xem workload, phiên bản Cassandra và thực nghiệm trước khi đổi chiến lược.

### Xem công việc compaction bằng nodetool

```bash
# Chạy trên host/pod Cassandra với quyền phù hợp
nodetool compactionstats

# Thống kê lưu trữ/SSTable/tombstone theo bảng
nodetool tablestats perf.events_by_tenant_day

# Tình trạng thread pool / pending và dropped tasks
nodetool tpstats
```

Các lệnh trên chủ yếu phục vụ **quan sát**, không khởi động major compaction hoặc thay dữ liệu. Cách hiển thị, đơn vị và field cụ thể thay đổi theo phiên bản. Đặc biệt, **pending compaction tasks** là số công việc đang chờ tại một thời điểm, **không phải thời gian chờ còn lại**.

Tín hiệu compaction pressure mạnh hơn khi xuất hiện đồng thời:

1. Pending compaction tăng bền vững qua nhiều khoảng đo.
2. Khối lượng SSTable và số SSTable liên quan tiếp tục tăng.
3. Disk I/O utilization/latency tăng cao hoặc throughput I/O đã bão hòa.
4. Read/write p95/p99 và timeout tăng theo cùng cửa sổ thời gian.
5. Free disk giảm nhanh hơn dự kiến từ tốc độ ghi nghiệp vụ.

Một spike pending tasks ngắn sau flush nhiều memtable chưa chắc là vấn đề. Điều đáng lo hơn là **tốc độ phát sinh công việc > tốc độ xử lý ổn định trong thời gian dài**.

## 6. Quan sát áp lực lưu trữ chính xác

Một node Cassandra có nhiều loại dữ liệu trên disk: SSTable của bảng và index, commit log, snapshots, streaming data và các file liên quan tới hệ thống. Bốn con số không thể thay thế nhau:

- **Dung lượng logic**: dữ liệu nghiệp vụ theo ước lượng và schema.
- **Data load** mà Cassandra báo qua `nodetool status`: số liệu về lượng dữ liệu mà node quản lý, không phải tỷ lệ `df` của filesystem.
- **Disk used/free**: số liệu thực của từng volume/mount chứa Cassandra data.
- **Disk I/O latency/throughput**: hiệu năng thực của thiết bị hoặc hệ lưu trữ; có thể nghẽn trước khi đầy.

Lệnh quan sát cơ bản:

```bash
# Trạng thái cụm, ownership và thông tin load do Cassandra hiển thị
nodetool status

# Kích thước, SSTables và một số thống kê của từng bảng
nodetool tablestats perf.events_by_tenant_day

# Dung lượng trống và mức sử dụng mount thực tế
df -h

# Liệt kê snapshot được Cassandra quản lý
nodetool listsnapshots
```

`df -h` phải chạy trên **host/container gắn volume dữ liệu thực**. Nếu pod dùng PersistentVolume, cần hiểu mount và cách hệ thống lưu trữ báo quota; filesystem của container root có thể không phải nơi chứa SSTable. Bên cạnh Cassandra data directory còn phải xem commitlog/snapshot nếu đặt ở các volume khác.

### Vì sao không nên để disk sát 100%?

Trong compaction, Cassandra có thể cần duy trì **file đầu vào và file đầu ra cùng tồn tại tạm thời**. Ngoài ra, streaming, bootstrap, repair, snapshot và tăng trưởng dữ liệu thường ngày đều cần headroom. Khi disk gần đầy:

1. Compaction có thể không có đủ không gian để hoàn tất.
2. SSTable cũ tiếp tục tồn tại; read amplification hoặc dung lượng tiêu thụ không giảm như kỳ vọng.
3. Ghi mới, flush hoặc maintenance có thể thất bại, ảnh hưởng tính sẵn sàng.
4. Nếu các node cùng thiếu không gian, di chuyển tải hoặc streaming có thể không khả thi.

Không có một mốc “80% luôn nguy hiểm” hay “còn 20 GB luôn đủ” cho mọi cụm. Hãy dự báo **disk growth rate**, kích thước compaction cần chạy, giới hạn volume, độ lệch dữ liệu giữa node và khoảng dự phòng cho failure/rebuild. Với bảng lớn hoặc traffic ghi cao, lượng trống tuyệt đối quan trọng không kém tỷ lệ phần trăm.

### Ảnh hưởng của TTL, delete, tombstone và snapshot

Cassandra đánh dấu xóa bằng tombstone. Dữ liệu hết TTL không nhất thiết giải phóng disk ngay lập tức: SSTable bất biến và quy tắc tombstone/compaction quyết định khi nào byte có thể được thu hồi. Việc có bản sao chưa nhìn thấy tombstone ở replica khác cũng liên quan đến an toàn xóa và cơ chế sửa chữa/repair.

Snapshot thường sử dụng hard links hoặc cơ chế tương đương theo hệ thống tệp và phiên bản; số liệu “dung lượng snapshot” không nên cộng một cách máy móc với kích thước SSTable khi ước tính disk thực. Tuy nhiên, snapshot có thể giữ các SSTable cũ không được giải phóng sau compaction. Khi disk tăng bất thường, kiểm tra snapshot và retention policy; **không tự ý xóa trực tiếp file SSTable/snapshot trên filesystem**.

Các dấu hiệu tombstone pressure thường xuất hiện ở query đọc nhiều dữ liệu đã bị xóa hoặc hết hạn; hãy quan sát read latency, tombstone-related metrics/warnings và schema/time bucket. Không sử dụng `ALLOW FILTERING` hoặc chỉ giảm page size để che giấu truy vấn có read amplification lớn.

## 7. Ghép telemetry thành một dashboard phục vụ vận hành

Một dashboard hữu ích nên có cùng mốc thời gian và phân cấp theo **application → Cassandra cluster → node → keyspace/table**. Ví dụ bố cục:

| Panel | Series / chỉ số | Giá trị khi điều tra |
| --- | --- | --- |
| Trải nghiệm người dùng | API request rate, p95/p99, error/timeout | Xác định lúc nào tác động đến người dùng bắt đầu |
| Ứng dụng Spring | Heap, allocation, GC pause, thread/CPU, driver in-flight/errors | Phân biệt bottleneck client với server |
| Cassandra request | Read/write latency, timeouts, unavailable, failures theo node | Xác định vấn đề phát sinh ở DB |
| JVM Cassandra | Heap used/max, GC pause, CPU, RSS/off-heap | Phát hiện pressure tại node cụ thể |
| Compaction | Pending/running tasks, bytes processed, SSTable count | Có tồn đọng nền và read amplification hay không? |
| Disk | Used/free, IOPS, throughput, I/O latency, filesystem saturation | Có thiếu headroom hay nghẽn I/O? |
| Data model | Partition size, tombstones, row/cell reads, table stats | Truy vấn/bảng nào kích hoạt công việc lớn? |
| Hoạt động vận hành | Deploy, schema change, repair, bootstrap, compaction config change | Tìm thay đổi trùng thời điểm sự cố |

### Prometheus/JMX exporter: lưu ý tên metric

Prometheus không mặc định biết mọi metric Cassandra. Cần có **JMX exporter hoặc hệ thu thập tương ứng** với rule mapping, rồi xác nhận tên series thật qua endpoint. Các nhóm JMX như `org.apache.cassandra.metrics:type=Compaction,name=PendingTasks` hay metrics của bảng có thể được exporter đổi thành tên khác. Vì thế các truy vấn PromQL sau chỉ minh họa **cấu trúc phân tích**, không phải lời hứa rằng metric tồn tại trong mọi cluster:

```promql
# Application JVM: GC pause tổng (giây GC / giây thực).
sum by (instance) (
  rate(jvm_gc_pause_seconds_sum{application="order-service"}[5m])
)

# Application JVM: heap usage ratio theo instance.
sum by (instance) (
  jvm_memory_used_bytes{application="order-service",area="heap"}
)
/
sum by (instance) (
  jvm_memory_max_bytes{application="order-service",area="heap"}
)
```

Đối với Cassandra, tìm đúng các series exporter sinh cho **heap/GC, compaction pending, read latency và disk I/O** rồi viết dashboard tương tự; không bịa tên Prometheus cụ thể khi chưa biết exporter mapping. Bật scrape per-node và chọn label có cardinality kiểm soát được; tránh label theo `tenant_id`, partition key hay CQL chứa dữ liệu người dùng.

Dashboard phải thể hiện **mức tải đồng thời**. Khi RPS tăng gấp đôi, GC cycles và IOPS tăng chưa chắc là lỗi; tỷ lệ lỗi, p99 và tốc độ tăng backlog giúp phân biệt tăng tải bình thường với mất cân bằng tài nguyên.

## 8. Quy trình chẩn đoán sự cố: bắt đầu từ tác động, tìm bằng chứng

Dùng một luồng điều tra có thể lặp lại, hạn chế thao tác phá hủy trước khi biết nguyên nhân.

### Bước 1 — Xác nhận triệu chứng

Xác định khoảng thời gian, ứng dụng/endpoint bị ảnh hưởng, tỷ lệ request lỗi, p95/p99, consistency level, loại query và node nào xử lý request. So với cùng giờ/ngày trước đó và xem deploy hoặc thay đổi schema.

### Bước 2 — Tách ứng dụng và Cassandra

- Nếu **HTTP p99 tăng nhưng driver/server latency không đổi**, kiểm tra app heap/GC, thread starvation, serialization hoặc gọi dịch vụ khác.
- Nếu **driver latency, server latency và timeout cùng tăng**, chuyển trọng tâm sang Cassandra/network.
- Nếu chỉ một app instance chậm, kiểm tra instance đó trước khi kết luận cả cluster có vấn đề.
- Nếu chỉ một node Cassandra chậm, xem token ownership, hotspot partition, disk và GC ở node đó.

### Bước 3 — Ghép heap/GC với compaction và disk

```text
API p99 tăng / timeout tăng
             |
             v
  App GC pause tăng?
      /              \
    Có               Không
    |                  |
Kiểm tra entity,      Driver/DB latency tăng?
page size, allocation      /         \
& buffering              Không        Có
                          |            |
                      Network/pool    Cassandra node:
                      khác/scheduler  GC? compaction? disk?
                                         |
                                 +-------+-------+
                                 |               |
                           Compaction backlog   Disk gần đầy
                           + I/O bão hòa        hoặc I/O chậm
                                 |               |
                          Schema / write rate   Headroom / snapshot /
                          TTL / SSTables        capacity / streaming
```

Đây là cây hỏi đáp để **khoanh vùng**, không phải phép suy luận rằng mỗi triệu chứng chỉ có một nguyên nhân. Ví dụ, GC và compaction có thể cùng tăng bởi workload ghi lớn.

### Bước 4 — Kiểm tra bằng lệnh đọc trạng thái

```bash
nodetool status
nodetool compactionstats
nodetool tpstats
nodetool tablestats perf.events_by_tenant_day
df -h
```

Đọc kết quả theo thời gian: snapshot ngay lúc sự cố và 5–15 phút sau (hoặc khoảng phù hợp) để biết backlog đang giảm hay tăng. Không dựa chỉ vào một lần `nodetool status` rồi kết luận “disk còn đủ”. Ngoài lệnh đọc trạng thái, xem metrics host về I/O latency, CPU, RSS/GC logs và logs ứng dụng.

### Bước 5 — Kiểm tra query và data model

Nếu pressure tập trung vào một bảng/truy vấn:

- Xác minh CQL có đầy đủ partition key, clustering restriction hợp lệ, không ép `ALLOW FILTERING`.
- Xem partition size, hot keys (từ telemetry an toàn) và số hàng/tombstone mà read path phải xét.
- Xem ứng dụng đã giới hạn kết quả, dùng paging và có timeout phù hợp hay chưa.
- Kiểm tra thay đổi TTL, xóa dữ liệu, thời gian giữ dữ liệu và compaction strategy.
- Nếu một vài tenant/bucket quá lớn, cân nhắc bucket nhỏ hơn hoặc bảng đọc khác theo access pattern; mô hình này cần benchmark và migration plan riêng.

### Bước 6 — Chọn giải pháp tương ứng với nguyên nhân

Thay đổi read path, tối ưu dữ liệu, giảm tải có kiểm soát hoặc thêm capacity theo bằng chứng. Không ưu tiên tăng heap/restart node như phản xạ đầu tiên vì có thể che đi compaction debt hoặc disk pressure. Mọi thay đổi topology/compaction/repair cần tuân theo quy trình vận hành riêng và kiểm chứng khả năng phục hồi của cụm.

## 9. Ba tình huống vận hành minh họa

### Tình huống A — Ứng dụng hết headroom heap khi đọc trang lớn

**Bối cảnh:** một endpoint Spring Data Cassandra mới thay query có giới hạn thành `repository.findAll()` rồi chuyển toàn bộ entity sang DTO và trả JSON.

**Quan sát:**

- HTTP p99 tăng ở vài application pod.
- `jvm_memory_used_bytes` và allocation rate của app tăng mạnh; GC pause ở app trùng request chậm.
- Cassandra node heap/GC và server read latency không tăng tương ứng.
- Số object và kích thước response tăng.

**Giả thuyết mạnh:** ứng dụng materialize quá nhiều entity vào heap, tạo pressure cho garbage collector. Cần kiểm tra heap dump/JFR trong môi trường và cách thu thập phù hợp.

**Hướng xử lý:** giới hạn kết quả, thiết kế paging/cursor cho API, tránh giữ cả tập kết quả trong `List` nếu không cần; chỉ select cột cần thiết và đo lại allocation/p99. **Page size của driver không tự giới hạn tổng số hàng** nếu code vẫn duyệt hết kết quả.

### Tình huống B — Write burst tạo compaction backlog

**Bối cảnh:** lượng ghi tăng lớn trong một khoảng ngắn, nhiều flush/SSTable mới xuất hiện.

**Quan sát:**

- `nodetool compactionstats` cho thấy pending tasks tăng qua nhiều lần kiểm tra.
- Disk I/O latency và utilization tăng, read latency p99 tăng.
- SSTable count hoặc dung lượng bảng tăng.
- Node heap có thể bình thường; GC pause không nhất thiết là yếu tố chính.

**Giả thuyết mạnh:** tốc độ tạo SSTable lớn hơn khả năng compaction kịp thời hoặc lưu trữ đang bão hòa.

**Hướng xử lý:** kiểm tra write rate, compaction strategy, kích thước partition, khả năng I/O và dung lượng dự phòng. Có thể điều tiết ingestion nếu hợp đồng nghiệp vụ cho phép; lập kế hoạch thêm tài nguyên hoặc tối ưu schema/workload. Tránh tự chạy **major compaction** trên cụm đang thiếu I/O/disk: thao tác đó có thể tăng tải và cần nhiều không gian hơn.

### Tình huống C — Disk tăng dù số hàng đang sống giảm

**Bối cảnh:** bảng có TTL, hệ thống vừa tăng số lần xóa dữ liệu; người vận hành kỳ vọng disk giảm ngay.

**Quan sát:**

- Dung lượng filesystem tiếp tục tăng hoặc không giảm.
- SSTable/tombstone và compaction activity tăng.
- Có snapshot cũ chưa hết retention hoặc tồn tại compaction backlog.
- Query trên partition có nhiều dữ liệu hết hạn bắt đầu chậm.

**Giả thuyết cần kiểm chứng:** dung lượng chưa được thu hồi vì dữ liệu/tombstone còn trong SSTable, compaction chưa xử lý đủ, hoặc snapshot giữ file cũ. Không thể khẳng định chỉ từ thông tin “TTL đã hết”.

**Hướng xử lý:** xem `tablestats`, snapshot retention, gc grace/repair policy và compaction state. Xem lại mô hình time bucket/TTL và chiến lược compaction. Chỉ xóa snapshot/điều chỉnh retention qua quy trình đã được phê duyệt; **không xóa trực tiếp SSTable hay rút ngắn cơ chế an toàn tombstone tùy tiện**, vì có nguy cơ ảnh hưởng tính toàn vẹn dữ liệu.

## 10. Alerting dựa trên xu hướng và tác động

Cảnh báo tốt nên kết hợp **symptom hướng người dùng** với **tài nguyên và backlog**. Những ví dụ sau là định hướng, không phải threshold mặc định áp dụng cho mọi hệ thống.

| Tín hiệu cảnh báo | Điều kiện mang tính định hướng | Tránh báo động giả |
| --- | --- | --- |
| API read/write p99 tăng | Vượt SLO trong một cửa sổ đủ dài, kèm tăng error/timeout | So với RPS và thay đổi release |
| Cassandra request timeout | Tỷ lệ timeout/unavailable tăng liên tục | Tách lỗi mạng/driver khỏi server |
| GC pause cao | GC time/pause vượt baseline và trùng latency spike | Phân biệt spike ngắn lúc warmup với GC kéo dài |
| Heap live set tăng | Mức heap còn lại sau GC tăng dần nhiều chu kỳ | Xem traffic và allocation đồng thời |
| Compaction debt | Pending tasks tăng liên tục trong khi throughput không theo kịp | Kiểm tra có phải flush burst ngắn |
| Disk headroom thấp | Free disk dự báo không đủ cho compaction/streaming/growth | Xem dung lượng tuyệt đối và từng volume |
| Disk I/O saturation | Latency I/O tăng cùng read/write p99 | Tách throughput cao nhưng vẫn đáp ứng tốt |
| Hot partition / tombstones | Query chậm theo một bảng/partition, warnings/metrics tăng | Không kết luận từ một sample đơn lẻ |

Đối với disk pressure, nên ghi rõ **thời gian dự kiến đến ngưỡng nguy hiểm** từ tốc độ tăng trưởng, biến động theo thời gian và dự phòng maintenance. Với GC và compaction, threshold nên được xây dựng từ baseline của chính cluster ở tải bình thường. Tự đặt con số đẹp nhưng không gắn với SLO và dữ liệu sẽ tạo alert fatigue.

Khi alert kích hoạt, runbook nên nêu: panel/link truy cập, lệnh kiểm tra an toàn, cách xác định node/partition, ai chịu trách nhiệm, những thao tác cần phê duyệt, và dấu hiệu xác nhận sự cố đã giảm. Không cần đặt toàn bộ quyền thao tác vận hành vào ứng dụng Spring.

## 11. Những thao tác cần tránh khi chưa đủ bằng chứng

| Phản xạ dễ gây rủi ro | Vì sao có thể làm tình hình xấu hơn | Hành động trước tiên |
| --- | --- | --- |
| Tăng heap Cassandra ngay khi p99 tăng | Có thể làm giảm page cache, thay đổi GC mà không sửa disk I/O | Xem GC pause, RSS, page cache và disk metrics |
| Restart node vì pending compaction cao | Mất tiến độ/tăng xáo trộn, không xóa nguyên nhân backlog | Xem xu hướng pending, tốc độ ghi, I/O và khả năng phục hồi |
| Chạy major compaction khi disk sát đầy | Có thể cần thêm không gian và gây I/O lớn | Đo headroom, chiến lược compaction và lên kế hoạch bảo trì |
| Xóa file SSTable hoặc snapshot bằng tay | Có thể phá dữ liệu/metadata và vi phạm retention policy | Dùng cơ chế quản trị được hỗ trợ, có kiểm tra backup |
| Giảm GC grace không xét repair/replication | Có thể ảnh hưởng an toàn xóa/tombstone trong trường hợp replica chậm | Xem repair policy và mô hình replication |
| Bật CQL tracing mọi request | Tăng overhead, sinh dữ liệu chẩn đoán lớn | Trace có chọn lọc query đại diện |
| Đổ lỗi cho Cassandra khi app heap tăng | Có thể là entity mapping hoặc trả List quá lớn | So application GC, driver, server latency đồng thời |
| Kết luận từ `nodetool status` “Load” | Load không phải dung lượng free của filesystem | Xem disk used/free ở đúng mount |

Không mặc định rằng một câu lệnh `nodetool` an toàn chỉ vì tên quen thuộc. Những lệnh đọc trạng thái ở bài này chỉ phục vụ điều tra; lệnh thay đổi schema, compaction, cleanup, snapshot, repair hoặc topology có tác động vận hành riêng và cần quy trình phù hợp.

## 12. Kiểm thử cảnh báo và năng lực quan sát

Không nên chờ tới sự cố production đầu tiên mới phát hiện rằng dashboard thiếu dữ liệu. Có thể kiểm thử theo ba mức:

### Mức 1 — Telemetry contract

Xác minh mỗi application instance và Cassandra node đều có metric hiện diện:

- Ứng dụng: heap/GC, request latency, errors/timeouts, mức tải.
- Database: heap/GC, compaction metrics, table stats, read/write latency.
- Hạ tầng: available RAM, RSS, disk used/free, I/O latency.
- Nhãn: environment, cluster, node/instance, service; không tạo nhãn theo từng partition key.

Kiểm tra scrape gaps, label thay đổi theo phiên bản exporter và dashboard không vô tình gộp p99 của mọi node thành một đồ thị che mất node xấu.

### Mức 2 — Workload thử nghiệm

Với môi trường test đủ tài nguyên, thực hiện workload có kiểm soát:

1. **Read nhiều hàng** qua repository/Template, xem heap/allocation của app và tác động page size.
2. **Write burst** trên bảng thử, quan sát SSTable và compaction pending thay đổi theo thời gian.
3. **TTL/delete** trên bộ dữ liệu thử, xem dung lượng/tombstone/compaction; lưu ý một bài test ngắn không chứng minh toàn bộ vòng đời dữ liệu.
4. **Query partition lớn** so với partition nhỏ; xem read latency và tombstone warnings.
5. **Load tăng dần** với mức concurrency cố định từng pha, ghi p95/p99, error, node CPU/I/O và GC.

Không chạy phép thử đẩy disk tới mức nguy hiểm trên production. Mục tiêu là xác nhận dashboard và runbook phản ánh đúng thay đổi được tạo ra, không phải phá hủy môi trường.

### Mức 3 — Diễn tập chẩn đoán

Mô phỏng một cảnh báo bằng dữ liệu thử hoặc replay metrics, yêu cầu người trực vận hành:

- Chỉ rõ **ứng dụng nào, node nào, thời điểm nào** bị ảnh hưởng.
- Dựa trên chuỗi thời gian phân biệt app GC, Cassandra GC và compaction I/O.
- Cung cấp bằng chứng từ dashboard + lệnh đọc trạng thái.
- Đề xuất hành động có thể đảo ngược và tiêu chí kiểm tra hiệu quả.
- Ghi lại những chỉ số còn thiếu để cải thiện telemetry.

## 13. Bài tập thực hành

**Bài tập 1 — Hai JVM, một request chậm.** Tạo một API dùng `CassandraRepository` và đo p99 cùng heap/GC tại ứng dụng. So sánh khi API trả 20 entity và khi trả 20.000 entity trên môi trường test. Giải thích vì sao Cassandra server có thể bình thường dù app GC tăng.

**Bài tập 2 — Dashboard heap/GC.** Tạo panel hiển thị heap used/max, GC pause rate và p99 theo instance. Thiết kế logic để phân biệt heap used ổn định sau GC với live set tăng liên tục; viết cảnh báo có gắn với tác động latency, không đặt ngưỡng tuyệt đối tùy tiện.

**Bài tập 3 — Compaction backlog.** Trong cụm thử, nạp dữ liệu theo các đợt lớn vào bảng có compaction strategy được ghi rõ. Thu thập `nodetool compactionstats`, số SSTable, disk I/O và read p99 trước/sau đợt ghi. Mô tả lúc backlog trở về baseline và những yếu tố gây sai lệch.

**Bài tập 4 — TTL và disk.** Với dữ liệu thử và snapshot policy minh bạch, tạo các bản ghi có TTL, đo disk và số SSTable qua thời gian. Giải thích vì sao hết TTL không lập tức làm filesystem trống, và vì sao không nên xóa SSTable bằng tay.

**Bài tập 5 — Tìm root cause.** Một hệ thống có p99 tăng, pending compaction tăng, app heap ổn, nhưng disk free liên tục giảm. Lập giả thuyết, liệt kê ít nhất sáu metric/lệnh cần kiểm tra, và đề xuất cách thu thập bằng chứng trước khi thực hiện thay đổi vận hành.

## 14. Checklist vận hành

- [ ] Tách biệt được metric của **application JVM** và **Cassandra JVM**.
- [ ] Có heap used/max, GC pause/frequency, allocation hoặc live set, RSS/off-heap và OS memory.
- [ ] Có read/write latency, p95/p99, throughput, timeout và error rate ở cả client/server khi phù hợp.
- [ ] Theo dõi pending compaction, active compaction, SSTable count và disk I/O theo node/bảng.
- [ ] Đọc đúng disk free/used của volume chứa dữ liệu, commit log và snapshot khi cần.
- [ ] Hiểu partition key, clustering key, tombstone, TTL và paging của query đang điều tra.
- [ ] Có dashboard theo node, timestamp deploy/schema change và ngưỡng cảnh báo theo baseline/SLO.
- [ ] Biết khi nào `nodetool status`, `compactionstats` và `tablestats` cung cấp bằng chứng; không suy diễn quá khả năng của từng lệnh.
- [ ] Không thực hiện major compaction, xóa SSTable hoặc đổi cấu hình GC/repair chỉ từ một biểu đồ.
- [ ] Có thử nghiệm và runbook xác minh alert trước khi xử lý production.

**Ghi nhớ:** quan sát **heap, GC, compaction và áp lực lưu trữ** là một bài toán liên kết nhiều lớp. Spring Data Cassandra cho phép ứng dụng truy cập Cassandra bằng repository, entity mapping, `CassandraTemplate` và CQL, nhưng chất lượng vận hành còn phụ thuộc cách phân vùng dữ liệu, mức consistency, paging và khả năng xử lý của các node. Bằng cách kết hợp application metrics, JVM/GC trên Cassandra, compaction, SSTable/tombstone và dung lượng đĩa theo cùng trục thời gian, nhóm vận hành có thể phân biệt triệu chứng với nguyên nhân và chọn phương án khắc phục phù hợp với hệ phân tán.
