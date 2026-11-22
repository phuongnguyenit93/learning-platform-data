# Metric theo node, keyspace, table và yêu cầu ứng dụng trong Apache Cassandra

## 1. Vì sao phải quan sát Cassandra ở nhiều cấp?

**Apache Cassandra** là cơ sở dữ liệu **wide-column phân tán**. Một yêu cầu CQL từ ứng dụng Java đi qua driver, coordinator, nhiều replica và lớp lưu trữ gồm memtable/SSTable. Vì vậy câu hỏi “Cassandra đang chậm ở đâu?” không thể được giải đáp bằng một con số CPU hoặc latency duy nhất.

Giả sử API `GET /devices/{id}/latest` tăng thời gian phản hồi từ 30 ms lên 700 ms. Các khả năng bao gồm:

- Một **node** hết dung lượng trống, đang garbage collection (GC) hoặc có nhiều pending tasks.
- Một **keyspace** có lượng ghi/đọc đột biến do nhiều bảng cùng phục vụ đợt traffic mới.
- Một **table** chứa partition lớn, nhiều tombstone hay nhiều SSTable cần đọc cho một truy vấn.
- Một **loại yêu cầu ứng dụng** bị chậm do retry, consistency level, timeout, pooling hoặc cách truy vấn không phù hợp.

Nếu chỉ nhìn metric tổng cluster, một node quá tải có thể bị trung bình của các node khỏe che khuất. Nếu chỉ nhìn metric ứng dụng, ta thấy ảnh hưởng tới khách hàng nhưng không biết nghẽn ở replica, disk hay chính tầng Java.

**Mục tiêu:** tổ chức metric thành bốn cấp **node → keyspace → table → yêu cầu ứng dụng**; biết đọc rate, latency, error, saturation; phân biệt coordinator với replica; chọn dashboard và alert phù hợp; thực hành đo đạc mà không nhầm các đơn vị hoặc nhân đôi lưu lượng do replication.

> Các tên metric cụ thể trong Cassandra/JMX, driver và exporter có thể khác giữa phiên bản, bản phân phối và bộ xuất metric. Ví dụ tên metric trong bài là **mẫu diễn giải**, không phải hợp đồng API áp dụng cho mọi cluster. Luôn đối chiếu danh sách metric thực xuất hiện trong deployment.

## 2. Hành trình của một request và vị trí đo

```text
 Java application / API
      |  API latency, error, retry, connection pool
      v
 Cassandra Java Driver 4.x
      |  driver request metrics / per-node metrics
      v
 Cassandra coordinator (Node A)
      |  client-request latency, timeout, pending, throughput
      +-------------+--------------+
      |             |              |
      v             v              v
  Replica A     Replica B      Replica C
  node metrics  node metrics   node metrics
  Table/Ks      Table/Ks       Table/Ks
      |             |              |
      +---- memtable, SSTable, cache, disk ----+
                   compaction, repair
```

Một coordinator có thể cũng là replica. Không phải mọi yêu cầu đều phải liên hệ tất cả replica: điều đó phụ thuộc **replication factor (RF)**, **consistency level (CL)**, topology, request và cơ chế Cassandra đang sử dụng.

Các metric đo những câu hỏi khác nhau:

| Cấp quan sát | Đơn vị nhóm | Câu hỏi chính | Ví dụ chỉ số |
|---|---|---|---|
| **Node** | Host/instance Cassandra | Node có khỏe, bị nghẽn tài nguyên không? | CPU, heap/GC, disk, network, pending tasks, dropped messages |
| **Keyspace** | Keyspace tại một node hoặc aggregate có định nghĩa | Nhóm dữ liệu nào tạo áp lực? | Read/write count, latency, pending flush, dữ liệu/traffic theo keyspace |
| **Table** | Keyspace + table + node | Bảng nào gây reads khó hoặc dữ liệu lớn? | SSTable, live/total disk, partition, tombstone, memtable, compaction |
| **Ứng dụng/yêu cầu** | Service + operation/query template | Người dùng chịu ảnh hưởng gì? | Request rate, success/error/timeout, p95/p99, retry, pool/acquisition latency |

**Phân biệt quan trọng:** Cassandra metrics xuất qua JMX thường là **metric của một node**, ngay cả khi tên có `Keyspace` hoặc `Table`. Tổng hợp toàn cluster là việc của collector/dashboard; không được gọi một giá trị lấy từ node A là “toàn keyspace của cluster”.

## 3. Phân loại metric: counter, gauge, timer, histogram

Trước khi vẽ biểu đồ, phải biết metric thuộc loại nào:

| Loại | Ý nghĩa | Cách dùng đúng | Sai lầm thường gặp |
|---|---|---|---|
| **Counter** | Tổng số sự kiện kể từ khi process/series bắt đầu | Tính `rate()`/`increase()` trên cửa sổ thời gian | Vẽ raw counter như “request/s” |
| **Gauge** | Trạng thái hiện tại, có thể tăng/giảm | Quan sát giá trị và xu hướng, mức bão hòa | Dùng `rate()` cho disk free hoặc pending queue |
| **Timer** | Lượng và phân phối thời gian thao tác | Latency theo unit, count, percentile/histogram tương ứng | Nhầm micro giây với milli giây/giây |
| **Histogram** | Phân phối số lần quan sát theo bucket hoặc snapshot | Xem bucket, quantile nếu cấu trúc hỗ trợ | Cộng trung bình của nhiều percentile |
| **Meter/rate** | Tần suất sự kiện đo bởi thư viện | Kiểm tra `mean`/`m1`/`m5`/`m15` và semantics | So sánh rate trong cửa sổ khác nhau mà không ghi chú |

Một số exporter JMX xuất percentile dưới dạng **gauge snapshot**; một số exporter khác tạo **Prometheus histogram buckets**. Hai kiểu này không tương đương: công thức `histogram_quantile()` chỉ phù hợp khi exporter thực sự có các chuỗi `*_bucket` hợp lệ. Từ `p99_node_A` và `p99_node_B` **không thể lấy trung bình** để suy ra p99 của cả cluster.

### Nhất quán đơn vị

- **Latency:** xác định micro giây, milli giây hay giây trước khi đặt ngưỡng.
- **Throughput:** request/giây, mutation/giây, bytes/giây là ba đại lượng khác nhau.
- **Storage:** bytes, MiB/GiB, phần trăm dùng đĩa; xem cả dung lượng theo mount.
- **GC:** thời lượng pause và tần suất GC; metric tổng thời gian GC và max pause không giống nhau.
- **Tombstone:** có thể là số cell quét, cảnh báo trên một query, hoặc tổng tombstone; đừng coi tất cả là cùng một metric.

## 4. Metric theo node: tài nguyên và sức khỏe tiến trình

Node là cấp đầu tiên khi nghi ngờ **một replica/coordinator bất thường**.

| Nhóm | Metric/quan sát đáng thu thập | Dấu hiệu cần chú ý |
|---|---|---|
| **Topology/availability** | Node up/down, trạng thái joining/leaving/moving, schema agreement | Node mất kết nối; nhiều request phải đổi replica |
| **CPU** | CPU process/host, load theo core | CPU kéo dài sát trần, latency đồng thời tăng |
| **Heap và GC** | Heap used/max, pause duration, GC rate | Pause dài trùng đỉnh latency/timeout |
| **Disk** | Free/used theo volume, throughput, latency, IOPS | Ghi/đọc bị giới hạn bởi disk hoặc gần đầy |
| **Network** | Bytes/s, errors, retransmits, connection saturation | Timeout khi data center/đường truyền nghẽn |
| **Memtable** | Memtable live data, pending flushes | Áp lực flush/ghi đĩa |
| **Compaction** | Pending tasks, completed, bytes compacted | Compaction tụt sau lượng ghi/TTL tombstones |
| **Thread pools/queues** | Active/pending tasks, blocked/dropped tasks nếu có | Queue tăng liên tục, coordinator/replica bão hòa |
| **Hints/repair/streaming** | Pending hints, repair/stream status | Replica mất cân bằng hoặc chưa hội tụ |

Không có **một ngưỡng CPU chung** khẳng định Cassandra hỏng: CPU cao dưới tải tốt với latency ổn định có thể là tận dụng tài nguyên hiệu quả. Quan sát **đồng thời** saturation, latency, errors và xu hướng.

### Lệnh kiểm tra nhanh bằng `nodetool`

Trên host được phép quản trị Cassandra:

```bash
nodetool status
nodetool info
nodetool tpstats
nodetool compactionstats
nodetool netstats
```

`status` xem topology và trạng thái node; `tpstats` giúp quan sát hàng đợi/thực thi và dropped-message counters; `compactionstats` quan sát công việc compaction; `netstats` hỗ trợ kiểm tra streaming và tình trạng mạng liên quan. Đây là **snapshot phục vụ chẩn đoán**, không thay thế hệ thống thu thập time series.

Tên lệnh/định dạng đầu ra có thể khác giữa các bản Cassandra. Không chạy các thao tác `nodetool` **thay đổi trạng thái** (như repair, flush, compact, cleanup) chỉ để “kiểm tra metric”; chúng có thể tạo I/O và ảnh hưởng cluster.

## 5. Metric của coordinator: request đến từ client

Một yêu cầu Java Driver thường chọn một **coordinator**. Ở cấp này, metric nhóm **ClientRequest** (tên JMX thường có ý nghĩa tương tự) giúp quan sát các đường `Read`, `Write` và một số nhóm truy vấn khác tùy phiên bản.

Nên xem:

1. **Throughput:** số client read/write request mỗi giây tại coordinator.
2. **Latency:** phân phối thời gian xử lý request, xem p50/p95/p99 thay vì chỉ trung bình.
3. **Timeout/unavailable/failure:** phân biệt lỗi quá thời gian, không đủ replica theo CL và các lỗi server khác.
4. **Pending hoặc overloaded:** scheduler, thread pool, dropped messages trong cùng khung giờ.
5. **Sự thay đổi khi tăng CL:** `ONE`, `LOCAL_QUORUM` hay `ALL` có yêu cầu xác nhận khác nhau và tác động latency/availability khác nhau.

Ví dụ câu chuyện sự cố:

```text
10:00  API p99 tăng
10:01  Coordinator A: read p99 tăng mạnh
10:02  Node A CPU bình thường; B có GC pause dài
10:03  Các read cần replica B thường timeout/retry
10:04  CL LOCAL_QUORUM khó đạt hơn do B không đáp ứng đúng hạn
```

Nếu chỉ nhìn CPU coordinator A sẽ bỏ lỡ vấn đề ở replica B. **Một coordinator chậm không chứng minh chính node coordinator là nguồn nghẽn duy nhất.**

### Không cộng nhầm throughput do replication

Một client write đến coordinator có thể tạo **nhiều thao tác replica** tùy RF và CL. Metric “coordinator client writes/s” **không bằng** tổng số disk/replica writes/s trong cluster. Nếu cộng table write count trên tất cả replica rồi tuyên bố đó là số request API, có thể **đếm nhiều lần** cùng một mutation.

Tương tự, retry và speculative execution của driver có thể tạo **nhiều attempts** cho một yêu cầu nghiệp vụ. Cần xác định đo **logical request**, **driver attempt**, **coordinator request** hay **replica operation** trước khi đối chiếu rate.

## 6. Metric theo keyspace: xác định nhóm dữ liệu gây tải

Một **keyspace** là phạm vi logic chứa bảng và cấu hình replication. Tập metric theo keyspace giúp khoanh vùng workload nào đang tăng tải trước khi đi xuống từng table.

Ví dụ một cluster có:

- `telemetry_ks`: ghi dày, TTL ngắn, bảng sự kiện theo ngày.
- `accounts_ks`: đọc theo khóa chính, dữ liệu bền hơn.
- `sessions_ks`: rất nhiều đọc/ghi ngắn hạn và tombstone.

Khi p99 của `sessions_ks` tăng nhưng `accounts_ks` vẫn bình thường, dấu hiệu gợi ý vấn đề tập trung ở **đường dữ liệu phiên**, không nhất thiết ở toàn cluster.

| Quan sát theo keyspace | Cách sử dụng |
|---|---|
| Read/write count hoặc rate | Xem nhóm workload nào tăng |
| Latency/read-write distribution nếu được exporter hỗ trợ | Đối chiếu chất lượng truy cập của keyspace |
| Pending flush/memtable và disk footprint liên quan | Phát hiện áp lực ghi/lưu trữ |
| Errors/timeout tổng hợp theo quy ước hệ thống | Khoanh vùng ảnh hưởng; xác nhận nguồn metric có phân tách được keyspace |
| Replication strategy/RF | Giải thích lưu lượng replica và yêu cầu CL |

**Giới hạn:** Cassandra không bảo đảm **mọi** metric coordinator-level đều có sẵn nhãn keyspace; một metric chỉ có `type=ClientRequest,scope=Read` không tự cho phép kết luận timeout thuộc `sessions_ks`. Khi cần phân tách đến query template/keyspace, bổ sung instrument ứng dụng và phân tích tracing/log có kiểm soát.

Khi tổng hợp nhiều node, quy ước nên chỉ rõ `sum by (keyspace)` đang là **tổng các series cục bộ trên node**, không tự động biến nó thành “unique logical requests của keyspace”.

## 7. Metric theo table: tìm hotspot, partition lớn và tombstone

Trong Cassandra, **thiết kế bảng theo truy vấn** ảnh hưởng trực tiếp các metric. Partition key phân bố dữ liệu đến token ranges, clustering key quyết định thứ tự trong partition. Một bảng có partition quá lớn hoặc truy vấn không bám partition key thường gây chi phí cao ngay cả khi tổng traffic chưa lớn.

Những nhóm metric đáng theo dõi ở cấp table:

| Nhóm | Ý nghĩa / dấu hiệu |
|---|---|
| **Read/write count, latency** | Bảng nào chịu tải hoặc có đọc/ghi chậm |
| **Live disk space, total disk space** | Dung lượng dữ liệu sống ước lượng và tổng lưu trữ cục bộ; kiểm tra semantics của exporter |
| **SSTable count / SSTables per read** | Mức phân mảnh SSTable; đọc phải chạm nhiều file |
| **Memtable live data / pending flush** | Áp lực write buffer và flush |
| **Partition size histogram/estimates** | Phát hiện partition lớn bất thường |
| **Tombstone/live cells scanned** | Truy vấn phải quét nhiều ô không còn sống |
| **Compaction bytes/tasks** | Áp lực dọn dữ liệu và SSTable của bảng |
| **Read repair / consistency-related counters** | Hỗ trợ chẩn đoán bất đồng replica, tùy phiên bản |

### Một ví dụ về “đọc 10 dòng nhưng quét nhiều tombstone”

Giả sử bảng `events_by_account_day` ghi 100.000 cell mỗi ngày với TTL 10 phút. Truy vấn lấy 10 event gần nhất trong một partition có thể phải đọc qua lượng tombstone đáng kể, đặc biệt nếu thiết kế clustering key hoặc mẫu truy vấn khiến nó chạm vùng dữ liệu đã hết hạn.

```text
Returned live rows:          10
Cells/tombstones scanned:  nhiều hơn nhiều
SSTables touched:            nhiều
API read p99:                tăng
```

Chỉ số “rows returned” ở ứng dụng không đủ giải thích chi phí thực thi. Hãy so table metrics, log truy vấn chậm và tracing được lấy mẫu với schema/partition size. **Không** lập tức tăng timeout để che vấn đề mô hình dữ liệu.

### Lệnh quan sát table

```bash
# Thay tên keyspace/table bằng giá trị thật.
nodetool tablestats demo_ks.events_by_account_day
nodetool tablehistograms demo_ks events_by_account_day
```

Các lệnh trên dùng để xem thông tin bảng/histogram khi được phiên bản hỗ trợ; cú pháp và trường đầu ra cần xác minh theo deployment. Chúng giúp tìm bằng chứng, không thay thế kiểm thử truy vấn.

## 8. Phân biệt keyspace/table metrics với phạm vi một replica

Vì một table được replicate trên nhiều node, mỗi node có thể ghi nhận metric table **khác nhau**:

```text
                         Keyspace telemetry_ks
                        Table readings_by_device_day

 Node A                       Node B                      Node C
 Table ReadCount=...          Table ReadCount=...          Table ReadCount=...
 DiskBytes=...                DiskBytes=...                DiskBytes=...
 Tombstones=...               Tombstones=...               Tombstones=...
       |                            |                          |
       +--------------- collector scrape ---------------------+
                                    |
                          Dashboard cluster-wide
```

Các cách gộp có ý nghĩa khác nhau:

- **`sum`:** phù hợp với một số tổng lượng công việc hoặc bytes cục bộ, nhưng nếu dữ liệu replicate, **tổng dung lượng không phải dung lượng logical unique**.
- **`max`:** tìm node nóng nhất, partition size lớn nhất trong dữ liệu đo, pending queue cao nhất.
- **`min`:** có thể hữu ích với disk free khi tìm node nguy cấp nhất.
- **`avg`:** xem xu hướng chung, nhưng có thể **che một node bất thường**.
- **Quantile:** không thể cộng/trung bình percentile gauge; cần dữ liệu phân phối/histogram hợp lệ hoặc quan sát per-node.

Với keyspace có **NetworkTopologyStrategy**, RF khác nhau theo datacenter, bảng điều khiển cần giữ nhãn `datacenter`/`rack` nếu hữu ích, tránh tổng hợp mất sự khác biệt giữa vùng. Không mặc định mọi node giữ toàn bộ partition.

## 9. Thu thập metric: JMX, exporter, Prometheus và dashboard

Cassandra có nhiều metric nội bộ được trình bày qua **JMX**; một hệ thống giám sát phổ biến có chuỗi:

```text
 Cassandra node
     |
     +-- org.apache.cassandra.metrics (JMX)
     |
     +-- JVM/OS metrics
     v
 JMX exporter / agent thu thập
     |
     v
 Prometheus / hệ time-series tương đương
     |
     +-- recording rules / alerts
     |
     v
 Grafana / bảng điều khiển
```

Các họ JMX thường được nhóm theo `type` và `scope` như **ClientRequest**, **Table**, **Keyspace**, **ThreadPools**, **Compaction**, **Cache**, **Storage**, **DroppedMessage**. Tên ObjectName, thuộc tính, unit và exporter mapping có thể thay đổi theo phiên bản Cassandra.

**Không mở JMX quản trị ra Internet.** Giới hạn network, xác thực và phân quyền theo hướng dẫn của deployment. Exporter chỉ nên công bố các metric cần thiết; không lộ cấu hình bí mật hoặc endpoint quản trị không được bảo vệ.

### Chọn khoảng scrape và retention metric

- Scrape quá thưa có thể bỏ lỡ spike GC/pending; quá dày tăng tải/chi phí lưu trữ.
- Cần phân biệt **retention của metric** trong Prometheus với **TTL của dữ liệu Cassandra**: hai hệ thống có chính sách riêng.
- Giữ labels và metric names ổn định khi nâng cấp exporter, hoặc có bảng ánh xạ để không làm dashboard “mất dữ liệu”.
- Theo dõi trạng thái `up`/scrape errors: một chart trống có thể là **mất collector**, không phải tải đã giảm về 0.

## 10. Ví dụ PromQL: cách hỏi đúng từ counter và histogram

Các tên như `cass_client_requests_total` dưới đây là **tên minh họa do exporter/recording rules đặt**, không phải tên chuẩn bắt buộc của Cassandra. Hãy ánh xạ sang metric thực tế trước khi sử dụng.

### 10.1. Tốc độ request theo operation

```promql
sum by (datacenter, operation) (
  rate(cass_client_requests_total{operation=~"read|write"}[5m])
)
```

Chỉ áp dụng nếu series `cass_client_requests_total` là **counter** theo từng coordinator và labels không làm đếm trùng cùng request. Dùng `rate()` thay vì raw counter để được đơn vị request/giây.

### 10.2. Tỷ lệ lỗi

```promql
sum by (service, operation) (
  rate(app_db_request_errors_total[5m])
)
/
clamp_min(
  sum by (service, operation) (
    rate(app_db_requests_total[5m])
  ),
  1
)
```

Ở ví dụ này cả tử số/mẫu số phải đếm **cùng loại logical request**. Nếu mẫu đếm application requests còn tử đếm driver retry attempts thì tỷ lệ có thể sai. Phép `clamp_min(..., 1)` trong ví dụ chỉ để tránh chia 0, nhưng với lưu lượng rất thấp có thể làm tỷ lệ bị đánh giá thấp; khi đặt alert nên sử dụng ngưỡng tối thiểu theo volume và quy tắc riêng.

### 10.3. P99 khi exporter có Prometheus histogram bucket

```promql
histogram_quantile(
  0.99,
  sum by (le, service, operation) (
    rate(app_db_request_duration_seconds_bucket[5m])
  )
)
```

Chỉ đúng nếu `*_bucket` là histogram hợp lệ và bucket boundaries giữa series nhất quán. Nếu exporter chỉ có gauge `p99_latency`/`Mean`, **không dùng công thức này** và không trung bình các gauge p99 để tạo p99 toàn cluster.

### 10.4. Node có pending compaction cao nhất

```promql
topk(5, cass_compaction_pending_tasks)
```

`cass_compaction_pending_tasks` là **gauge minh họa**, không phải counter. Kết quả cần giữ nhãn node để tìm chính xác host đang bị nghẽn.

### 10.5. Nguy cơ đĩa đầy

```promql
100 * (
  1 - node_filesystem_avail_bytes{mountpoint="/var/lib/cassandra"}
      / node_filesystem_size_bytes{mountpoint="/var/lib/cassandra"}
)
```

`node_filesystem_*` thường do **host exporter** cung cấp chứ không phải Cassandra JMX. Mountpoint của data, commitlog, cache hoặc backup có thể khác; không dùng tên mountpoint trên như cấu hình chung cho mọi hệ thống.

## 11. Metric ở ứng dụng Java: đo điều người dùng thực sự chịu

Node metrics không biết API của bạn đang chạy “đọc giỏ hàng”, “lấy danh sách cảm biến” hay “ghi token”. Do đó, ứng dụng Java cần tạo **metric theo query template/operation ổn định**, gắn với business SLO.

Một bộ metric tối thiểu:

| Metric ứng dụng | Label nên dùng | Mục đích |
|---|---|---|
| Request count | `service`, `operation`, `outcome` | Tổng logical requests; tỷ lệ lỗi |
| Request duration | `service`, `operation` | Latency p50/p95/p99 ở tầng service |
| Retry attempt count | `operation`, `cause` | Phát hiện timeout/retry storm |
| In-flight requests | `service`/`operation` | Load chưa hoàn thành |
| Driver pool/request metrics | `node` hoặc host-id ổn định | Phát hiện kết nối/coordinator chậm |
| Application timeout count | `operation`, `timeout_kind` | Phân biệt hết budget client với server timeout |

### Java Driver 4.x: ví dụ instrument một truy vấn

Ví dụ dùng một interface thu thập metric để không bắt buộc phải cài đặt thư viện telemetry cụ thể. Trong thực tế, `RequestMetricsSink` được triển khai bằng Micrometer, OpenTelemetry Metrics hoặc SDK giám sát đang dùng.

```java
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class DeviceEventReader {
    public interface RequestMetricsSink {
        void recordDuration(String operation, String outcome, long nanos);
        void countRequest(String operation, String outcome);
    }

    private final CqlSession session;
    private final PreparedStatement selectLatest;
    private final RequestMetricsSink metrics;

    public DeviceEventReader(CqlSession session, RequestMetricsSink metrics) {
        this.session = session;
        this.metrics = metrics;
        this.selectLatest = session.prepare(
            "SELECT event_time, temperature_c " +
            "FROM observability_readings_by_device_day " +
            "WHERE device_id = ? AND event_day = ? LIMIT 1"
        );
    }

    public Row getLatestInDay(String deviceId, LocalDate day) {
        final String operation = "device_readings_latest_by_day";
        long start = System.nanoTime();
        String outcome = "success";
        try {
            return session.execute(selectLatest.bind(deviceId, day)).one();
        } catch (RuntimeException error) {
            outcome = "error";
            throw error;
        } finally {
            long nanos = System.nanoTime() - start;
            metrics.recordDuration(operation, outcome, nanos);
            metrics.countRequest(operation, outcome);
        }
    }
}
```

**Giải thích cách đo:**

- `System.nanoTime()` đo **elapsed time** trong process; không dùng nó làm epoch timestamp của Cassandra.
- `operation` là tên **template hữu hạn**, không chứa `deviceId` hay từng khóa thực tế; tránh tạo hàng triệu time series.
- `outcome` chỉ có một số giá trị được chuẩn hóa như `success/error/timeout`, không chứa exception message tùy ý.
- Đoạn mã đo **lời gọi ứng dụng quanh session.execute(...)**: nó bao gồm thời gian client/driver/coordinator theo đường đồng bộ, không bằng timer nội bộ của một replica.
- Một request trả row `null` vẫn có thể là **thành công kỹ thuật**; nếu nghiệp vụ cần phân biệt “not found”, thêm outcome/metric được định nghĩa riêng.

Nếu driver đã bật metric sẵn, hãy tránh đếm trùng ở mức attempt và logical request; driver metrics dùng để phân tích sâu, app metrics để đo **SLO của người dùng**. Cấu hình metric trong Java Driver 4.x thay đổi theo driver/config và tích hợp metrics; chỉ sử dụng nhóm metric đã xác nhận được bật.

## 12. Tránh nổ cardinality và rò dữ liệu nhạy cảm qua labels

Một time series được phân biệt bởi **tên metric + tập labels**. Nếu gắn `device_id`, `user_id`, `session_id`, `partition_key`, raw CQL hoặc `exception_message` làm label, số series có thể tăng gần theo số request/dữ liệu.

```text
Các label hợp lý:
  service="device-api"
  operation="device_readings_latest_by_day"
  outcome="success"
  datacenter="dc1"

Các label nguy hiểm:
  device_id="mỗi thiết bị một chuỗi"
  cql="SELECT ... WHERE token=..."
  session_token="..."
  exception="full stack trace thay đổi theo request"
```

Ưu tiên:

1. `service`, `environment`, `datacenter`, `node`, `keyspace`, `table` nếu cardinality đã biết và thực sự cần.
2. `operation` là **tên query template**, không phải full CQL với tham số.
3. `outcome` hoặc `error_class` là tập phân loại hữu hạn.
4. ID/event cụ thể đưa vào **trace/log được kiểm soát và lấy mẫu**, không phải label metric.
5. Kiểm soát chi phí thu thập theo số node × số table × số loại metric × số labels ứng dụng.

Các query parameter có thể chứa dữ liệu cá nhân hoặc bí mật, vì vậy không bật tracing/log full CQL values đại trà trên production. Nếu cần correlation, dùng request ID/event ID đã chuẩn hóa và tuân chính sách bảo mật.

## 13. Chẩn đoán theo bốn tầng: từ SLO tới một table hoặc node

Giả sử API đọc lịch sử có **p99 900 ms**, tăng từ 100 ms. Một quy trình định hướng:

| Bước | Câu hỏi | Metric/bằng chứng |
|---|---|---|
| 1. Ứng dụng | API nào, vùng nào, lỗi nào? | App request rate, p95/p99, timeout, retries |
| 2. Driver/coordinator | Coordinator nào chậm, có connection acquisition/retry tăng không? | Driver per-node latency/errors/pool, client request metrics |
| 3. Node | Node có disk/GC/thread pool/compaction nghẽn không? | CPU, disk latency, GC pauses, pending tasks, dropped messages |
| 4. Keyspace | Workload nhóm nào tăng? | Keyspace read/write metrics, topology/RF |
| 5. Table | Bảng nào tạo nhiều SSTable/tombstone/partition lớn? | Table read latency, SSTables/read, tombstones scanned, partition histograms |
| 6. Query/schema | Truy vấn có đúng partition key và giới hạn range không? | CQL template, tracing mẫu, schema, query plan phù hợp |
| 7. Khắc phục | Có hiệu quả và không phát sinh tác dụng phụ không? | So before/after p99/errors và node/table metrics |

### Ví dụ 1 — Chỉ một node nóng

Ứng dụng báo retry tăng; bảng điều khiển node thấy **Node B** pending tasks và disk latency tăng, các node khác bình thường. Kiểm tra token/replica placement, query distribution và node B trước khi tăng quy mô toàn cluster.

### Ví dụ 2 — Một table có tombstone pressure

`sessions_ks.session_by_id` có live rows ít nhưng tombstone scanned per read tăng, read p99 tăng. Kiểm tra TTL, thao tác overwrite/delete, partition design và compaction; không giả định `gc_grace_seconds = 0` là giải pháp an toàn.

### Ví dụ 3 — Ứng dụng chậm nhưng Cassandra node bình thường

App p99 tăng, ClientRequest latency trên các coordinator vẫn ổn định, driver acquisition/retry hoặc thread pool ứng dụng tăng. Hướng điều tra chuyển sang **client connection pool, network, serialization, GC của Java service, upstream load** thay vì ép Cassandra compaction.

## 14. Bảng cảnh báo: ngưỡng phải xuất phát từ SLO và baseline

Không nên copy một tập ngưỡng tuyệt đối cho mọi cluster; workloads, phần cứng, CL và kích thước dữ liệu khác nhau. Thiết kế alert theo **tín hiệu có hành động cụ thể**:

| Alert gợi ý | Điều kiện khái niệm | Hành động đầu tiên |
|---|---|---|
| **API error budget burn** | Tỷ lệ lỗi vượt SLO liên tục trong cửa sổ có đủ traffic | Khoanh vùng service/operation và coordinator |
| **Read/write p99 degradation** | p99 > SLO và request rate đáng kể | Kiểm tra retry, node/table p99, disk/GC |
| **Cassandra node unavailable** | Node down thực sự, có ảnh hưởng RF/CL | Kiểm tra topology và kế hoạch khôi phục |
| **Disk headroom low** | Dung lượng trống giảm về ngưỡng vận hành | Phân tích tăng trưởng SSTable/snapshot/compaction |
| **Compaction backlog sustained** | Pending tasks tăng kéo dài cùng disk/latency pressure | Kiểm tra workload, disk bandwidth và strategy |
| **Read tombstone scan high** | Số tombstone quét trên query tăng cùng latency | Kiểm tra bảng và phạm vi truy vấn |
| **Dropped messages/timeout spike** | Tăng mạnh so baseline và có error ở client | Kiểm tra thread pools, network, GC, replica |
| **Metrics missing** | Scrape/exporter mất dữ liệu quá thời gian cho phép | Sửa hệ thống giám sát trước khi kết luận node khỏe |

**Kết hợp nhiều cửa sổ:** một spike 10 giây có thể cần dashboard, nhưng không nhất thiết pager. Với SLO quan trọng, dùng burn-rate nhanh và chậm; với disk/compaction nên dùng xu hướng và dự báo, không chỉ một sample.

**Alert nào cũng cần runbook**: cách xác nhận, dashboard liên quan, ngưỡng ảnh hưởng khách hàng và thao tác an toàn. Một cảnh báo chỉ nói “p99 cao” nhưng không nêu service/table/node khó giúp xử lý sự cố nhanh.

## 15. Thực hành CQL kiểm tra metric có căn cứ

Trong keyspace thử nghiệm đã chọn bằng `USE <keyspace>;`, tạo bảng được truy vấn bằng partition key và clustering key rõ ràng:

```sql
CREATE TABLE IF NOT EXISTS observability_readings_by_device_day (
    device_id text,
    event_day date,
    event_time timeuuid,
    temperature_c double,
    PRIMARY KEY ((device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);

INSERT INTO observability_readings_by_device_day (
    device_id, event_day, event_time, temperature_c
)
VALUES ('sensor-lab-01', '2026-11-21', now(), 29.8);

SELECT event_time, temperature_c
FROM observability_readings_by_device_day
WHERE device_id = 'sensor-lab-01'
  AND event_day = '2026-11-21'
LIMIT 10;
```

### Quy trình quan sát có kiểm soát

1. **Trước khi thử:** chụp baseline app latency, coordinator read/write request rate, node CPU/disk/GC và table metrics.
2. **Thực thi một lượng request nhỏ, giới hạn** theo khóa đã biết từ ứng dụng/driver, không chạy full scan.
3. **Sau khi thử:** xem app request count có tăng tương ứng hay không; coordinator request count có tương quan hay không; table reads/writes được ghi cục bộ ở node nào.
4. **Lý giải sai khác:** RF, CL, coordinator placement, retries, cache và exporter scrape interval có thể khiến count giữa các cấp không bằng nhau.
5. **Kiểm tra latency:** so app duration với coordinator latency và table metric nếu có, nhưng không trừ hai timer khác phạm vi để khẳng định “network bằng đúng phần chênh”.

Khi cần tạo tải nhiều hơn, dùng **môi trường test chuyên dụng và công cụ load test được cho phép**, giới hạn concurrency và giữ baseline. Không bắn hàng nghìn request vào một partition production chỉ để thử biểu đồ.

### Có cần `TRACING ON` không?

`TRACING ON` trong `cqlsh` có thể hữu ích khi điều tra một vài query cụ thể:

```sql
TRACING ON;
SELECT event_time, temperature_c
FROM observability_readings_by_device_day
WHERE device_id = 'sensor-lab-01'
  AND event_day = '2026-11-21'
LIMIT 10;
TRACING OFF;
```

Tracing mang overhead và có thể làm tăng dữ liệu ghi nội bộ. Dùng **lấy mẫu ngắn trong môi trường thích hợp**, không bật tracing tràn lan để thay thế metrics liên tục. Đối chiếu sự kiện trace với client timestamp, CL và node đang phục vụ.

## 16. Replication, consistency level, repair và compaction tác động metric ra sao?

Các tham số phân tán cần có mặt khi giải thích một dashboard:

- **RF (replication factor):** tăng số replica làm tăng bản sao lưu trữ và số thao tác giữa các node; không được suy số logical writes bằng tổng table writes trên tất cả replica.
- **CL (consistency level):** `ONE`, `LOCAL_QUORUM`, `QUORUM`, `ALL` có yêu cầu xác nhận khác nhau; so latency phải ghi rõ CL và topology.
- **Repair:** có thể tạo disk/network CPU và streaming/compaction load riêng với traffic ứng dụng. Spike khi chạy repair không nhất thiết là tăng request khách hàng.
- **Compaction:** chạy nền, cạnh tranh disk I/O với đọc/ghi; backlog kéo dài hoặc forced compaction có thể khiến latency xấu đi.
- **TTL/tombstones:** dữ liệu hết hạn logic vẫn có thể chiếm SSTable; tombstone scanned và compaction pressure có thể tăng trước khi dung lượng đĩa giảm.
- **Coordinator vs replica:** coordinator request latency và table metrics của node replica đo **khác phạm vi**, không cộng hoặc so 1:1 theo cách máy móc.

Trong thời gian repair hoặc rolling upgrade, nên **ghi chú sự kiện triển khai lên dashboard**. Khi p99 tăng, điểm thay đổi cấu hình/CL, topology hoặc compaction strategy là thông tin quan trọng để khoanh vùng nguyên nhân.

## 17. Checklist xây dashboard bốn cấp

Một dashboard hữu dụng không nhất thiết có hàng trăm biểu đồ. Nên sắp xếp theo trình tự ra quyết định:

1. **Tổng quan service/SLO:** logical request rate, p95/p99, success/error, timeout và retry.
2. **Cluster & topology:** node up/down, datacenter, schema/repair status; ánh xạ traffic tới coordinator và replica.
3. **Node health:** CPU, heap, GC, disk free/latency, network, thread pool pending, dropped messages.
4. **Coordinator requests:** read/write rates, latency distributions, timeout/unavailable/failure.
5. **Keyspace:** throughput/latency và footprint theo nhóm dữ liệu, giữ nhãn node/dc khi cần.
6. **Table:** read/write latency, SSTable, memtable, tombstone scan, partition size, disk và compaction.
7. **Dependencies/annotations:** app deployment, schema change, repair, compaction, topology changes.
8. **Data quality của metrics:** exporter health, missing series, unit conversion, counter reset, label cardinality.

Với mỗi biểu đồ phải ghi **đơn vị, phạm vi và phép tổng hợp**. Ví dụ: “Coordinator read requests/s — sum across nodes in dc1” khác với “Table local read count/s — max node per table”.

Một lối điều tra tốt là bắt đầu từ biểu đồ **ảnh hưởng người dùng**, sau đó drill-down theo `service → operation → coordinator/node → keyspace → table`. Không bắt đầu bằng cách chọn table ngẫu nhiên chỉ vì nó có dung lượng lớn.

## 18. Bài tập tự kiểm tra

**Câu 1.** Tại sao không thể lấy `p99` từ ba node Cassandra rồi tính trung bình làm p99 của cluster?

**Đáp án:** Percentile không tuyến tính. Cần histogram/distribution có thể tổng hợp, hoặc xem mỗi node riêng; trung bình các p99 gauge không tạo p99 toàn cluster.

**Câu 2.** Một API thực hiện 100 logical write requests, RF = 3. Có thể suy tổng table write count của cluster luôn bằng 100 không?

**Đáp án:** Không. Replica operations, coordinator, retries và cơ chế ghi có thể khiến số đo ở table/node khác số logical requests.

**Câu 3.** `ClientRequest.Read` latency tăng nhưng CPU coordinator thấp. Có thể loại trừ Cassandra không?

**Đáp án:** Không. Replica khác có thể nghẽn disk/GC hoặc mạng; coordinator vẫn phải chờ kết quả theo CL.

**Câu 4.** Một table có tombstone scanned tăng cùng p99 đọc tăng. Nên kiểm tra gì đầu tiên?

**Đáp án:** Schema/partition và query pattern, TTL/DELETE, SSTable/compaction; không tự hạ `gc_grace_seconds` để làm biến mất cảnh báo.

**Câu 5.** Vì sao metric `node_filesystem_avail_bytes` không phải là Cassandra JMX table metric?

**Đáp án:** Nó thường đến từ exporter hệ điều hành, phản ánh dung lượng filesystem của host. Cần phân biệt nguồn và mountpoint với metric lưu trữ nội bộ Cassandra.

**Câu 6.** Khi application timeouts tăng nhưng coordinator request latency vẫn bình thường, hướng kiểm tra tiếp là gì?

**Đáp án:** Driver pool/acquisition, network, retries, JVM service, concurrency và upstream API; so các metric có cùng phạm vi trước khi kết luận.

**Câu 7.** Có nên gắn từng `device_id` thành một Prometheus label cho latency của Cassandra?

**Đáp án:** Thông thường không. Nó tạo cardinality rất lớn; dùng operation/query template ổn định, còn ID cụ thể đưa vào log/trace đã kiểm soát.

**Câu 8.** `rate()` thích hợp với counter tổng số request hay gauge số pending tasks?

**Đáp án:** Với **counter tổng số request**. Pending tasks là gauge; đọc mức hiện tại và xu hướng thay vì áp dụng rate như counter.

**Câu 9.** `nodetool tablestats` cho biết chính xác timeout rate của một API Java cụ thể không?

**Đáp án:** Không. Nó là nguồn snapshot/thống kê theo table/node, không biết operation nghiệp vụ của API. Cần metric ứng dụng và driver/coordinator tương ứng.

**Câu 10.** Tại sao một dashboard có giá trị request rate bằng 0 chưa chắc là hệ thống khỏe?

**Đáp án:** Có thể collector/exporter đã mất kết nối hoặc metric bị đổi tên. Phải kiểm tra scrape health và khoảng dữ liệu bị thiếu trước khi kết luận.

---

**Ghi nhớ:** Quan sát Cassandra hiệu quả cần ghép **metric ứng dụng** (điều người dùng chịu), **coordinator request metrics**, **node health**, **keyspace** và **table metrics** theo đúng phạm vi của từng phép đo. Phân biệt **counter/gauge/histogram**, đơn vị đo, coordinator với replica và lưu lượng logical với replica-level. Dùng JMX/exporter và `nodetool` để có bằng chứng, giới hạn cardinality, đối chiếu RF/CL, tombstone, compaction/repair, và bắt đầu điều tra từ **SLO của yêu cầu ứng dụng** trước khi đi xuống node và bảng.
