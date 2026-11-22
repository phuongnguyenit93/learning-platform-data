# Chọn truy vấn trọng yếu từ độ trễ, tần suất và tài nguyên sử dụng trong Apache Cassandra

> **Chương:** Tối ưu truy vấn  
> **Phạm vi:** Chọn đúng truy vấn CQL cần ưu tiên tối ưu trên cluster Apache Cassandra bằng dữ liệu đo từ ứng dụng Java, Cassandra và hệ điều hành. Tập trung vào *latency*, *frequency* và *resource footprint* theo từng **query family**, kết hợp SLO nghiệp vụ, replication/consistency, partition key, tombstone, SSTable, tracing và runbook đo trước–sau. Ví dụ dùng Cassandra 4.1/5.0 và Java Driver 4.x; tham số/metric phải đối chiếu phiên bản đang chạy.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xây dựng **danh mục query family** theo thao tác nghiệp vụ, mẫu CQL, keyspace/table và consistency level, không gộp mọi `SELECT` vào một nhóm.
2. Phân biệt **độ trễ trung bình, p95/p99, tỷ lệ timeout, tần suất QPS, thời gian lưu trú của request và chi phí CPU/I/O/memory/network**.
3. Chọn truy vấn quan trọng bằng ma trận **SLO × tần suất × chi phí tài nguyên × độ ảnh hưởng nghiệp vụ**, kể cả truy vấn hiếm nhưng làm nghẽn cluster.
4. Dùng metrics từ **Java Driver 4.x**, Cassandra `ClientRequest`/`Table`, `nodetool`, tracing và sampling để tìm bằng chứng thay vì suy đoán từ một con số.
5. Nhận diện các kiểu truy vấn Cassandra dễ tốn chi phí: thiếu partition key, `ALLOW FILTERING`, partition rộng, tombstone nhiều, SSTable chồng lấn, page lớn, index fan-out, sai mô hình bảng.
6. Viết runbook chọn top truy vấn, đưa ra giả thuyết cải thiện, benchmark an toàn và xác minh không hồi quy về **tính đúng dữ liệu, consistency, latency và throughput**.
7. Thực hành CQL/Java để thu được bằng chứng định lượng với một workload mẫu có query family rõ ràng.

Điểm đặc thù của **wide-column Cassandra**: dữ liệu được thiết kế theo đường truy vấn, partition key điều khiển phân bố và truy cập replica, clustering columns điều khiển thứ tự trong partition. Một CQL statement nhìn đơn giản có thể đọc một partition nhỏ, quét nhiều SSTable/tombstone, hoặc fan-out ra nhiều node. Vì vậy **chọn đúng workload để tối ưu** quan trọng không kém việc chỉnh câu CQL.

## 2. Truy vấn “trọng yếu” nghĩa là gì?

Không phải cứ câu truy vấn có latency cao nhất là nên tối ưu đầu tiên. Một truy vấn trọng yếu là truy vấn mà **việc cải thiện có ý nghĩa lớn đối với người dùng, tài nguyên cluster hoặc rủi ro vận hành**.

So sánh bốn tình huống minh họa:

| Query family | Tần suất | Latency p95 | Mục tiêu p95 | Đặc điểm | Câu hỏi ưu tiên |
|---|---:|---:|---:|---|---|
| `order.getById` | 800 QPS | 12 ms | 40 ms | Đọc một partition/key nhỏ | Tần suất cao nhưng chưa vi phạm SLO; đang tốn bao nhiêu I/O? |
| `order.listRecent` | 90 QPS | 240 ms | 150 ms | Đọc nhiều trang/row | Vừa vi phạm SLO vừa có thể tốn nhiều tài nguyên |
| `order.searchStatus` | 4 QPS | 2.000 ms | 600 ms | Filtering/quét phạm vi lớn | QPS nhỏ nhưng mỗi request có thể gây tải lớn |
| `audit.exportNightly` | 0,05 QPS | 5.000 ms | 10.000 ms | Job nền có cửa sổ riêng | Chậm nhưng chưa vi phạm; liệu có đụng giờ cao điểm? |

Các con số này **giả định**, không phải benchmark Cassandra. Câu trả lời có thể là: `order.listRecent` cần ưu tiên vì ảnh hưởng trực tiếp trải nghiệm; `order.searchStatus` cần xem sớm vì chi phí mỗi lần quét lớn, dù QPS thấp; `order.getById` có thể tối ưu sau nếu cluster vẫn còn nhiều headroom; `audit.exportNightly` có thể được lên lịch/giới hạn thay vì tối ưu gấp.

### 2.1. Ba trục bắt buộc

~~~text
                   CHỌN QUERY FAMILY TRỌNG YẾU
                               |
           +-------------------+--------------------+
           |                   |                    |
        LATENCY             FREQUENCY           RESOURCE COST
      p50/p95/p99           QPS, burst          CPU / disk / memory
      timeout, SLO          peak window         rows/tombstones read
           |                   |                bytes / fan-out
           +-------------------+--------------------+
                               |
                  BUSINESS CRITICALITY / RISK
                  error budget, SLA, khách hàng
                               |
                       TOP CANDIDATES
                               |
                    TRACE + VERIFY + TUNE
~~~

**Không cộng ba trục theo một công thức mù quáng.** Một truy vấn phục vụ thanh toán có thể cần điều tra dù QPS rất thấp; ngược lại một tác vụ audit chậm nhưng được giới hạn và chạy ban đêm có thể không cần sửa ngay. Dùng thứ tự ưu tiên có thể giải thích và có nguồn số liệu.

### 2.2. Mục tiêu của bài là *selection*, không phải “chỉnh mọi thứ”

Sản phẩm đầu ra của một vòng chọn truy vấn nên là:

1. Danh mục những query family thực sự phát sinh lưu lượng.
2. Bảng xếp ưu tiên top 3–10 truy vấn với nguồn đo, khoảng thời gian, SLO và ước lượng impact.
3. Giả thuyết chi phí của từng truy vấn và **cách kiểm chứng**.
4. Kế hoạch thử tối ưu/rollback, owner và chỉ số thành công.
5. Các trường hợp **không chọn**, kèm lý do (đã đạt SLO, dữ liệu ít, tần suất rất thấp, rủi ro sửa quá cao).

Không cần có một “top slow queries” được Cassandra tự tạo sẵn cho mọi lệnh: Cassandra có metrics theo node/table/request type, còn thống kê **theo từng mẫu CQL** thường cần instrumentation ở ứng dụng, gateway hoặc cơ chế ghi log có giới hạn.

## 3. Query family: đơn vị đúng để so sánh

Một query family gom các lần thực thi **cùng mục đích và đường truy cập dữ liệu**, đồng thời giữ những khác biệt có ảnh hưởng tài nguyên.

Ví dụ hai câu thực thi:

~~~sql
SELECT status, total
FROM shop.orders_by_id
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

SELECT status, total
FROM shop.orders_by_id
WHERE tenant_id = 'tenant-b'
  AND order_id = 22222222-2222-2222-2222-222222222222;
~~~

Chúng có thể được gắn **một query family** `order.getById` vì cùng statement/template, partition key và shape. Nhưng nếu tenant-a có một hot partition rất lớn còn tenant-b không, phải có thêm chiều phân tích **kích thước partition, tenant tier hoặc token range** thay vì làm biến mất tail latency trong trung bình.

### 3.1. Cấu trúc nhãn nên dùng

| Trường metadata | Ví dụ | Lý do |
|---|---|---|
| `service` | `checkout-api` | Định vị owner và business criticality |
| `operation` / `query_family` | `order.listRecent` | Nhóm có số lượng hữu hạn |
| `cql_template_id` | `ord_recent_v2` | Nhận biết thay đổi shape sau deploy |
| `keyspace.table` | `shop.orders_by_tenant_day` | Liên kết metric table Cassandra |
| `access_pattern` | `single_partition_range` | Phân biệt point lookup, range, fan-out |
| `consistency_level` | `LOCAL_QUORUM` | Tác động số replica phản hồi và latency |
| `datacenter` | `dc1` | So sánh hiệu năng topology |
| `result_mode` | `first_page` / `all_pages` | Phân biệt đo trang đầu và đọc hết |
| `outcome` | `success` / `timeout` / `failure` | Tránh chỉ đo request thành công |

**Không dùng raw CQL chứa literal, tenant_id, order_id, email hoặc giá trị bind làm label Prometheus**: tạo cardinality bùng nổ, rủi ro lộ dữ liệu cá nhân và chi phí metric lớn. Với trace chi tiết, dữ liệu nhạy cảm phải được che hoặc lưu theo chính sách bảo mật.

### 3.2. Không gộp những workload khác nhau chỉ vì chung table

~~~text
Table: orders_by_tenant_day
   |
   +-- order.getByPrimaryKey  (đọc đúng một hàng)
   +-- order.listRecent       (slice 50 row trong một partition)
   +-- order.listAllDays      (nhiều partition, nhiều page)
   +-- order.deleteExpired    (nhiều tombstone)

Cùng table nhưng latency, QPS, rows scanned, fan-out và SLO khác nhau.
~~~

Một metric `Table.ReadLatency` cao chỉ nói **bảng đó có local reads chậm**, không chỉ ra query family nào chịu trách nhiệm. Muốn xếp ưu tiên đúng phải ghép **phía ứng dụng (theo query family)** với **phía server (theo node/table/replica)** và các trace chọn lọc.

## 4. Trục thứ nhất — Độ trễ và trải nghiệm người dùng

### 4.1. Đo p50, p95, p99 chứ không chỉ average

- **p50**: một nửa request hoàn tất không quá mức này, đại diện trải nghiệm điển hình.
- **p95/p99**: nhạy với phần đuôi, thường phù hợp các API cần latency SLO.
- **Mean/average**: hữu ích cho tính toán một số tải tổng hợp nhưng có thể che request chậm cực trị.
- **Timeout/Unavailables/Failures**: phải đo riêng; một truy vấn timeout không nên bị loại khỏi thống kê khi đánh giá trải nghiệm.
- **Time to first page** và **time to all pages**: là hai đại lượng khác nhau với Cassandra paging.

Ví dụ cùng p50=8 ms:

~~~text
Family A: p50=8ms, p95=18ms, p99=30ms
Family B: p50=8ms, p95=220ms, p99=900ms

=> Trung vị giống nhau nhưng Family B có tail latency rất xấu.
   Phải xem replica, partition-size outlier, paging, GC,
   compaction, tombstone và retry thay vì chỉ nhìn average.
~~~

### 4.2. Mỗi latency có một ranh giới đo

| Nguồn đo | Phạm vi | Bao gồm / không bao gồm |
|---|---|---|
| API/business operation | Từ khi ứng dụng nhận yêu cầu đến khi trả response | Có thể gồm auth, logic, nhiều truy vấn, cache, serialization |
| Query family trong Java service | Từ trước `session.execute` tới sau khi đạt điều kiện đo | Có driver, network, coordinator, retry; phụ thuộc đo first page hay all pages |
| Driver session `cql-requests` | Tổng thời gian CQL request ở cấp session | Bao gồm retry; mặc định gộp mọi query family của session |
| Driver node `cql-messages` | Message CQL gửi tới một node | Một request client có thể có nhiều message do retry/speculation |
| Cassandra `ClientRequest.Read.Latency` | Request latency ở coordinator theo request type | Gộp request cùng loại trên node; không phải từng CQL template |
| Cassandra `Table.ReadLatency` | Local read latency của table trên node | Không phải latency trọn vẹn của Java request |
| CQL tracing | Events của một request được chọn | Giúp nhận diện các bước tốn thời gian; sampling, overhead và coverage có hạn |

**Không ghép trực tiếp p99 ở phía API với p99 ở server rồi lấy hiệu để suy network latency**: percentiles của các tập phân phối khác nhau **không trừ được**, và request/replica sampled cũng có thể khác nhau. Đối chiếu cùng trace và mốc thời gian khi cần phân rã.

### 4.3. SLO và error budget quan trọng hơn “query chậm nhất”

Ví dụ:

~~~text
order.getById:       p95  12 ms / SLO  40 ms -> đạt
order.listRecent:    p95 240 ms / SLO 150 ms -> vi phạm
order.searchStatus:  p95 2.0 s  / SLO 0.6 s -> vi phạm
audit.exportNightly: p95 5.0 s  / SLO 10 s  -> đạt
~~~

Tỷ số `observed_latency / SLO` là một tín hiệu sàng lọc, **không thay tỷ lệ request vi phạm threshold**. Nếu SLO định nghĩa “99,9% request dưới 200 ms”, phải đo **tỷ lệ request dưới 200 ms**, không suy chỉ từ p95. Khi còn timeout, `p95 thành công` có thể trông đẹp trong khi user error budget đã cạn.

## 5. Trục thứ hai — Tần suất, burst và mức độ lan truyền

### 5.1. QPS trung bình không mô tả giờ cao điểm

Tối thiểu thu:

- `requests_per_second` theo query family trong cửa sổ 1–5 phút.
- `peak QPS` theo giờ cao điểm và đợt batch/cron.
- Số request theo tenant tier/region/DC nếu có cơ chế gắn nhãn **cardinality thấp**.
- Retry, speculative execution, fan-out tới nhiều node.
- Tần suất thay đổi theo deploy hoặc feature flag.

Ví dụ:

| Family | Trung bình QPS | Đỉnh QPS | Đặc điểm |
|---|---:|---:|---|
| `order.getById` | 800 | 2.000 | Đường đọc nóng toàn ngày |
| `order.listRecent` | 90 | 400 | Tăng khi trang lịch sử mở |
| `order.searchStatus` | 4 | 100 | Burst theo batch lọc/đối soát |
| `audit.exportNightly` | 0,05 | 20 | Tập trung trong cửa sổ job |

Nếu chỉ so theo QPS trung bình, `order.searchStatus` dễ bị bỏ qua dù có thể làm disk/CPU tăng mạnh trong burst.

### 5.2. Sự khác nhau giữa request logic và request vật lý

~~~text
                 1 API request
                      |
               1 query family
                      |
           Java Driver execute()
                      |
        1 coordinator attempt
         /                \
      Success        timeout / retry
                         |
                 coordinator attempt #2
                         |
                    replica reads
                      |
                  nhiều SSTable
~~~

**QPS logic** là số lần nghiệp vụ yêu cầu family; **các message/attempt tới node** có thể lớn hơn nếu có retry/speculation, paging hoặc một request gọi nhiều statement. Tăng driver retries để che latency có thể làm tải cluster tăng dù lượng người dùng không đổi.

Tính fan-out phải theo cơ chế từng loại query:

- Read `LOCAL_QUORUM` yêu cầu số phản hồi tương ứng RF/DC; một coordinator có thể liên hệ nhiều replica, gồm digest/data responses.
- Query dùng nhiều partition keys (`IN` theo partition key, nếu hợp lệ) có thể phải chạm nhiều token ranges.
- Pagination có thể phát sinh nhiều CQL fetch khi client đọc hết kết quả.
- Index/filtering query có thể quét nhiều dữ liệu hoặc phân tán tới nhiều node, phụ thuộc loại index và điều kiện.

**Không nhân cứng QPS với RF rồi gọi là số disk reads**. Replication, digest, speculative retry, cache và sự khác nhau giữa coordinator/replica khiến chi phí thực cần đo bằng tracing/metrics.

### 5.3. Một chỉ số bổ trợ: concurrency tương đương

Theo trực giác của Little's Law, trong **hệ thống ổn định**:

\[
L \approx \lambda W
\]

với `L` là số request **đang ở trong hệ thống**, `λ` là throughput request/giây và `W` là thời gian trung bình mỗi request (giây).

Ví dụ `order.listRecent` có 90 QPS, mean latency 100 ms thì `L ≈ 90 × 0,1 = 9` request đồng thời tương đương. Con số này hữu ích khi đánh giá **in-flight load/queue**, nhưng **không phải 9 giây CPU mỗi giây** và không tính trực tiếp lượng đĩa Cassandra đọc.

Tương tự, 800 QPS × mean 6 ms ≈ 4,8 request đồng thời. Một family có concurrency cao có thể tiêu hao connection/request slots, nhưng vẫn cần đo **chi phí thực** trước khi kết luận CPU/disk.

## 6. Trục thứ ba — Chi phí tài nguyên mỗi lần và tổng mức tiêu thụ

Latency nhanh không nhất thiết rẻ. Một truy vấn trả trong 10 ms nhờ cluster rất khỏe vẫn có thể tiêu hao nhiều I/O và trở thành vấn đề khi traffic tăng gấp 10. Ngược lại, request chờ network hoặc một downstream service có thể có latency lớn mà **không** chiếm nhiều CPU Cassandra.

### 6.1. Định nghĩa “chi phí mỗi query”

| Loại chi phí | Đơn vị nên dùng | Nguồn bằng chứng |
|---|---|---|
| Phân vùng bị truy cập | partitions/attempt | CQL shape, routing key, trace |
| Row/cell phải quét so với row trả về | scanned/returned ratio | Tracing và metrics table; ứng dụng đếm returned rows |
| Tombstone phải đọc | tombstones/read | `Table.TombstoneScannedHistogram`, warning logs, tracing |
| SSTable được chạm | SSTables/partition read | `Table.SSTablesPerReadHistogram` |
| Dữ liệu qua network | bytes/request, bytes/s | Driver, coordinator/network metrics, response size ước lượng |
| Disk reads / I/O | bytes/s, IOPS, disk await | OS/node disk, trace và thử tải |
| CPU/GC | CPU seconds hoặc % CPU/node, GC pause | OS/JVM metrics; cần workload cô lập để gán per-family |
| Memory/queue | in-flight, paging buffers, heap/off-heap, pending tasks | Driver/JVM, request pools, memtable/cache |
| Hàng mới/SSTable do ghi | bytes written, flush/compaction backlog | `Table.WriteLatency`, `BytesFlushed`, compaction metrics |
| LWT/counter | Paxos messages, contention, retries | `ClientRequest.CASRead/CASWrite`, tracing, app retries |

**Điểm cần nhớ:** Nhiều metric là **theo table/node**, không tự cung cấp “CPU mỗi template CQL”. Nếu trong cùng thời điểm nhiều query family dùng chung bảng và disk, **không thể gán toàn bộ disk bytes của bảng cho một family** mà không có thí nghiệm hoặc phân tích bổ sung.

### 6.2. Từ chi phí mỗi request tới tổng tải mỗi giây

Nếu có phép đo tương đối tin cậy về bytes trả về trung bình mỗi request:

\[
B_{\mathrm{response/sec}} \approx QPS \times \overline{B}_{\mathrm{response/request}}
\]

Ví dụ:

| Family | QPS | Bytes trả về trung bình | Tải response logic ước lượng |
|---|---:|---:|---:|
| `order.getById` | 800 | 2 KiB | 1.600 KiB/s |
| `order.listRecent` | 90 | 200 KiB | 18.000 KiB/s |
| `order.searchStatus` | 4 | 20 KiB | 80 KiB/s |
| `audit.exportNightly` | 0,05 | 2 MiB | 0,1 MiB/s theo trung bình |

`order.listRecent` tiêu thụ **response bandwidth** lớn hơn `getById` dù QPS thấp hơn. Nhưng `searchStatus` có thể chỉ trả 20 KiB trong khi phải quét **hàng trăm nghìn row**. **Response bytes không đại diện cho disk read bytes**.

Tương tự, nếu sampling cho thấy một query thường quét khoảng 100.000 row/lần ở 4 QPS, nó có thể gây tải đọc **400.000 row scanned/giây** trên phạm vi sampling. Đây chỉ là **proxy**; không tương đương CPU cycles hay tổng replica reads nếu không biết query plan và retry.

### 6.3. Phân biệt footprint tức thời và footprint theo thời gian

Đối với một báo cáo hiếm khi chạy:

- **Trung bình ngày** có thể thấp.
- **Tại thời điểm chạy** lại chạm nhiều token ranges, làm các node hoạt động hết công suất.
- **Trong thời gian chạy** tạo CPU/disk spike và chiếm request queues của truy vấn khác.

Vì vậy cần cả **peak-second/peak-minute impact**, đặc biệt với repair, bulk ingest, batch job, export và analytics đọc phân tán. Đối với một interactive query SLO nghiêm ngặt, kiểm **p99 và error budget**, không chỉ so bytes/sec.

### 6.4. Chi phí ghi cũng phải được xem xét

Bài tập query tuning không chỉ là SELECT. Một mutation đơn có thể được nhân tới nhiều replicas, ghi commit log/memtable và sinh compaction. Với bảng denormalized, một business operation có thể ghi nhiều tables.

Ví dụ:

~~~text
API placeOrder:
    INSERT orders_by_id
    INSERT orders_by_customer_day
    INSERT order_status_by_warehouse

Một sự kiện nghiệp vụ -> 3 query families/3 bảng
Mỗi bảng lại có RF và replica I/O riêng.
~~~

Không thể kết luận “INSERT chỉ 3 ms nên rất rẻ”: phải xem **write QPS, mutation size, RF, commit log, flush, pending compaction, SSTable count** và khả năng một retry tạo mutation bổ sung. Với LWT, đánh giá contention và số vòng Paxos chứ không chỉ một lần UPDATE thành công.

## 7. Thu thập số liệu đúng cấp: application, driver và Cassandra

### 7.1. Bảng nguồn dữ liệu

| Nguồn | Đo được gì? | Điểm mù |
|---|---|---|
| API gateway / service tracing | Business operation, error budget, request latency | Có thể có nhiều query CQL và cache; không chỉ ra từng truy vấn |
| App instrumentation **theo query family** | Count, latency, timeout, pages, returned rows, tags SLO | Không trực tiếp thấy SSTables/tombstone trên replica |
| Java Driver session metrics | `cql-requests`, `cql-client-timeouts`, connected-nodes | Mặc định gộp mọi query family của session |
| Java Driver node metrics | `cql-messages`, `pool.in-flight`, network/timeout theo node | Message không bằng một business request; retries làm số lượng tăng |
| Cassandra `ClientRequest` metrics | Coordinator Read/Write/CAS latency, failures, timeouts, unavailables | Phân theo request type/node, không theo query template |
| Cassandra `Table` metrics | Local read/scan latency, SSTables-per-read, tombstones, disk/compaction | Phân theo bảng/node, không tự biết owner business |
| CQL tracing / sampling | Những event của một truy vấn và replica tham gia | Overhead, sampling bias, không thống kê toàn bộ workload |
| Full Query Logging (FQL) được kiểm soát | Traffic query thực tế để phân loại hoặc replay | Dữ liệu nhạy cảm, dung lượng, cần quyền/phê duyệt và giới hạn |
| `nodetool` và OS/JVM | Node/table hotspots, compaction, disk/GC, thread queues | Không tách riêng CPU mỗi query family nếu chạy chung |

**Không dùng một nguồn thay cho toàn bộ bảng.** Nên lấy **định danh query family từ ứng dụng** rồi ghép theo cùng timestamp/DC/table với **phía server** để khoanh vùng.

### 7.2. Cassandra Table metrics đáng quan tâm

Các tên thông dụng trong tài liệu Apache:

~~~text
org.apache.cassandra.metrics:type=Table,keyspace=shop,scope=orders_by_tenant_day,name=ReadLatency
org.apache.cassandra.metrics:type=Table,keyspace=shop,scope=orders_by_tenant_day,name=CoordinatorReadLatency
org.apache.cassandra.metrics:type=Table,keyspace=shop,scope=orders_by_tenant_day,name=RangeLatency
org.apache.cassandra.metrics:type=Table,keyspace=shop,scope=orders_by_tenant_day,name=SSTablesPerReadHistogram
org.apache.cassandra.metrics:type=Table,keyspace=shop,scope=orders_by_tenant_day,name=TombstoneScannedHistogram
org.apache.cassandra.metrics:type=Table,keyspace=shop,scope=orders_by_tenant_day,name=LiveScannedHistogram
org.apache.cassandra.metrics:type=Table,keyspace=shop,scope=orders_by_tenant_day,name=EstimatedPartitionSizeHistogram
org.apache.cassandra.metrics:type=Table,keyspace=shop,scope=orders_by_tenant_day,name=ReadTotalLatency
~~~

Đọc kỹ:

- `ReadLatency` ở **replica/local table** khác `CoordinatorReadLatency`.
- `RangeLatency` áp dụng các range scans ở scope table, không đồng nghĩa mọi câu CQL có clustering range đều được tính như một cluster-wide scan.
- `SSTablesPerReadHistogram` đo số SSTable *thực sự phải truy cập* trên một partition read; đã loại một số SSTable được Bloom filter/min-max/index loại trước.
- `TombstoneScannedHistogram` và `LiveScannedHistogram` cho biết loại chi phí có thể không hiện trong response bytes.
- `EstimatedPartitionSizeHistogram` cho manh mối về **partition quá rộng**, không thay thống kê per-key.

Tên metric JMX/nhãn exporter có thể khác theo phiên bản, đặc biệt với histogram. Xác minh exporter để không lấy **cumulative histogram từ lúc server start** làm histogram chỉ riêng 5 phút nếu không có chuyển đổi delta/snapshot phù hợp.

### 7.3. ClientRequest và node-wide signals

~~~text
org.apache.cassandra.metrics:type=ClientRequest,scope=Read,name=Latency
org.apache.cassandra.metrics:type=ClientRequest,scope=Read,name=Timeouts
org.apache.cassandra.metrics:type=ClientRequest,scope=Read,name=Unavailables
org.apache.cassandra.metrics:type=ClientRequest,scope=Write,name=Latency
org.apache.cassandra.metrics:type=ClientRequest,scope=Write,name=Timeouts
org.apache.cassandra.metrics:type=ClientRequest,scope=CASWrite,name=Latency
~~~

Node-wide signals còn gồm `ThreadPools.ReadStage.PendingTasks`, `MutationStage`, native transport, compaction pending, commit log, GC và I/O. Khi cả nhiều query family tăng p99 đồng thời, có thể là **shared resource bottleneck** (disk, CPU, GC, network, node down) chứ không phải tất cả câu CQL đột nhiên có model sai.

### 7.4. Java Driver 4.x metrics: ý nghĩa và cấu hình

Theo tài liệu Java Driver 4.17, metrics **mặc định bị vô hiệu hóa**, bật có chọn lọc:

~~~hocon
datastax-java-driver {
  advanced.metrics {
    session.enabled = [
      connected-nodes,
      cql-requests,
      cql-client-timeouts
    ]
    node.enabled = [
      cql-messages,
      pool.open-connections,
      pool.in-flight
    ]
  }
}
~~~

Để xuất metrics, cần tích hợp reporter tương ứng (Dropwizard, Micrometer...) và chỉnh histogram/timer theo tài liệu driver/binary. `cql-requests` đo thời gian `session.execute()` ở cấp request **bao gồm retries**. `cql-messages` đo từng thông điệp gửi tới node và có thể lớn hơn số request logic nếu có retry/speculation.

**Lưu ý:** Bật metrics trong driver **không tự thêm nhãn query family**. Muốn chọn câu CQL trọng yếu, bổ sung timer/counter **ở tầng repository/service** theo các tên query family ổn định; không dùng raw SQL literal hoặc bind parameters làm labels.

### 7.5. Các lệnh thu thập an toàn

~~~bash
nodetool status
nodetool tablestats shop.orders_by_tenant_day
nodetool tpstats
nodetool compactionstats
nodetool netstats
nodetool gcstats
~~~

Không chạy tất cả lệnh như một script “kiểm 100% mọi query”. `nodetool tablestats` phản ánh aggregate của **table trên node**; `tpstats` cho biết queue nền; `netstats` cho thấy streaming; tất cả cần ghép với query family và mốc thời gian.

Nếu một node có `TombstoneScannedHistogram` cao nhưng ứng dụng có 20 family cùng đọc table, phải sampling/trace những family nghi ngờ, thay vì gán hết tombstone cho một câu query.

## 8. Phương pháp chọn ứng viên: từ longlist tới shortlist

Nên dùng **hai vòng**, thay vì ngay từ đầu đưa tất cả vào một điểm số:

### Vòng 1 — Phân luồng bắt buộc

| Luồng | Điều kiện | Quyết định |
|---|---|---|
| **Khẩn cấp (P0)** | Timeout/Unavailable vượt ngưỡng, ảnh hưởng thanh toán/đặt hàng, cluster gần mất khả dụng | Ưu tiên ngay, dù QPS thấp |
| **SLO breach (P1)** | p95/p99 hoặc tỷ lệ request dưới ngưỡng không đạt SLO trong nhiều cửa sổ | Điều tra sớm, ưu tiên theo user impact |
| **Capacity risk (P1)** | QPS × chi phí lớn, tombstone/SSTable/scan/CPU nóng, dự báo quá tải giờ cao điểm | Điều tra sớm dù latency hiện còn tốt |
| **Planned improvement (P2)** | Không vi phạm SLO, tài nguyên ổn; có tiềm năng tiết kiệm rõ | Xếp theo lợi ích và công sức |
| **Defer/monitor** | Workload hiếm, tác động thấp, có giới hạn an toàn, không có bằng chứng bottleneck | Giữ dashboard, chưa thay đổi |

**Không để score trung bình che P0.** Một query xóa sai dữ liệu hoặc khiến request thanh toán timeout cần hành động ngay, bất kể tổng điểm có thua truy vấn báo cáo.

### Vòng 2 — Xếp hạng trong cùng luồng

Chấm từng ứng viên theo thang 0–5 với rubric được định nghĩa **trước khi xem kết quả**, chẳng hạn:

- `S` — mức nghiêm trọng về SLO/error budget: 0 đạt rộng rãi; 5 vi phạm nghiêm trọng.
- `R` — tài nguyên mỗi request × peak traffic: 0 thấp; 5 áp lực CPU/disk/tombstone cao.
- `F` — tần suất/độ lan truyền: 0 rất thấp; 5 chiếm nhiều request hoặc burst trên nhiều node.
- `B` — mức ảnh hưởng nghiệp vụ: 0 batch không quan trọng; 5 request thiết yếu.

Một công thức nội bộ minh họa:

\[
Priority = 0.35S + 0.30R + 0.20F + 0.15B
\]

Đây là **cách hỗ trợ hội thoại**, không phải một thuật toán của Cassandra và không thể thay phán đoán. Trọng số tùy SLO, ngân sách và mục tiêu capacity. Với sự cố P0, ưu tiên đã được quyết định ở vòng 1; không dùng score để hạ cấp.

Ví dụ **số liệu giả định có owner và nguồn đo**:

| Query family | Luồng | S | R | F | B | Ưu tiên tương đối |
|---|---|---:|---:|---:|---:|---|
| `order.getById` | P2 | 0 | 2 | 5 | 5 | Cao về tần suất nhưng không khẩn cấp |
| `order.listRecent` | P1 SLO | 4 | 4 | 3 | 4 | Ưu tiên đầu trong nhóm SLO |
| `order.searchStatus` | P1 capacity | 5 | 5 | 1 | 3 | Ít QPS nhưng scan rất đắt |
| `audit.exportNightly` | Defer | 0 | 2 | 0 | 1 | Giới hạn lịch chạy, theo dõi |

Số điểm `R` **chỉ được cho sau khi có bằng chứng** từ traces, bytes/rows scanned hoặc tài nguyên; nếu chưa có, ghi “**unknown**” thay vì đặt 0 và để câu query nguy hiểm tụt hạng.

### 8.1. Lượng hóa cơ hội cải thiện

Với latency, ghi:

~~~text
Family: order.listRecent
Current: p95=240ms, error rate=0.7% trong peak 18:00–19:00
Target:  p95<=150ms, error rate<=0.1%
QPS peak: 400

Nếu thay mô hình bảng/limit/paging:
  Giả thuyết: giảm rows scanned và page fetch.
  Cần đo: p95/p99, total pages, tombstones/read,
          read bytes/requests, disk I/O, CPU và result correctness.
~~~

Không tuyên bố “tiết kiệm 90 ms × 400 QPS = 36 giây CPU/giây”. Độ trễ wall clock không phải CPU. Chỉ có thể dùng cải thiện mean latency × QPS như **giảm thời gian lưu trú tổng của request** dưới giả định hợp lệ; CPU/disk phải đo riêng.

### 8.2. Sàng lọc theo độ tin cậy và rủi ro thay đổi

Trong backlog, bổ sung:

| Thuộc tính | Tác dụng |
|---|---|
| Evidence confidence: cao/vừa/thấp | Tránh tối ưu khi nguyên nhân chưa xác định |
| Estimated effort | Thay LIMIT vài giờ khác tạo bảng mới, backfill và dual-write nhiều tuần |
| Blast radius | Bao nhiêu bảng, services, DC, dữ liệu lịch sử bị ảnh hưởng |
| Reversibility | Có feature flag/dual-read/rollback an toàn không |
| Data correctness risk | Có thay đổi semantics, CL, ordering, paging, TTL hoặc consistency không |
| Owner và deadline | Có người chịu trách nhiệm, thời điểm peak/load test |

Một câu SQL thay rất dễ nhưng làm sai phân trang/độ chính xác **không phải lựa chọn tốt** hơn việc đầu tư vào schema đúng. Tuy nhiên, chọn **quick win đã đo được** cũng có thể giảm áp lực sớm trước khi redesign.

## 9. Nhận diện truy vấn Cassandra nào có khả năng tốn tài nguyên

Sau khi có shortlist, đọc **shape của CQL** để hình thành giả thuyết. Cassandra tối ưu theo **query-driven data modeling**: truy vấn một partition có khóa phù hợp thường dễ kiểm soát hơn truy vấn buộc cluster lọc/quét nhiều dữ liệu.

### 9.1. Phân loại theo access pattern

| Query shape | Mẫu | Điểm mạnh/nguy cơ | Tín hiệu cần đo |
|---|---|---|---|
| **Point lookup** | Partition key + clustering key đầy đủ | Thường dự đoán được nếu partition nhỏ | p99, SSTables-per-read, node hotspots |
| **Slice trong partition** | Partition key + clustering range | Đọc theo thứ tự clustering; có thể rất rộng | Rows scanned, pages, response size, partition size |
| **Multi-partition** | Nhiều partition keys hoặc ứng dụng fan-out | Chạm nhiều token ranges/replicas | Fan-out, server traffic, retries, coordinator latency |
| **Index/SAI query** | Predicate được chỉ mục hỗ trợ | Có thể tốt nhưng selectivity và số node ảnh hưởng | Candidate rows, post-filtering, index SSTable pressure |
| **Filtering** | `ALLOW FILTERING` | Hiệu năng có thể không dự đoán được; kết quả ít vẫn quét nhiều | Scanned/returned ratio, CPU/disk, timeout |
| **Large partition lookup** | Đúng partition key nhưng hàng quá nhiều | Hotspot, nhiều tombstone, nhiều SSTable | Partition-size histogram, tombstones/read, p99 |
| **LWT/CAS** | `IF NOT EXISTS` hoặc `IF ...` | Nhiều vòng Paxos, contention | CASRead/CASWrite latency, contention, failures |
| **Unbounded scan/export** | `SELECT *` phạm vi lớn, nhiều pages | Chi phí theo dataset, ảnh hưởng cluster | Pages, bytes, range scan latency, off-peak footprint |
| **Write-heavy/update/delete** | Nhiều mutation/tombstone | LSM write amplification, flush/compaction | Mutation size, commit log, pending compaction, tombstones |

**Một query có partition key chưa chắc nhanh**: nếu một partition chứa hàng triệu clustering rows, chứa nhiều tombstone, hoặc truy vấn phải đọc hàng trăm trang thì p99 vẫn có thể lớn.

### 9.2. Ba mẫu CQL để so sánh

**Mẫu A — Đọc đúng một row:**

~~~sql
SELECT status, total
FROM shop.orders_by_id
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

Nếu `PRIMARY KEY ((tenant_id), order_id)`, một tenant lớn vẫn có thể là partition rộng, nhưng Cassandra có thể định vị row theo clustering key. Khi dữ liệu theo tenant tăng không giới hạn, thiết kế thêm bucket/partition phù hợp thay vì tự tin rằng point lookup luôn rẻ.

**Mẫu B — Đọc lịch sử theo bucket ngày:**

~~~sql
SELECT event_time, event_id, status
FROM shop.orders_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND order_day = '2026-11-21'
  AND event_time >= '2026-11-21T08:00:00Z'
  AND event_time <  '2026-11-21T09:00:00Z'
LIMIT 50;
~~~

Nếu partition key là `(tenant_id, order_day)` và clustering key bắt đầu bằng `event_time`, đây là single-partition range query. Thêm time bucket có thể giảm kích thước partition nhưng phải xét **người dùng cần nhiều ngày**, lúc đó ứng dụng phải đọc các buckets và phối hợp kết quả.

**Mẫu C — Lọc trạng thái không có khóa phù hợp:**

~~~sql
-- KHÔNG chạy trên bảng lớn/production để “test latency”.
SELECT tenant_id, event_time, event_id
FROM shop.orders_by_tenant_day
WHERE status = 'PAID'
ALLOW FILTERING;
~~~

Đây là ví dụ **anti-pattern nếu bảng không có index/access path phù hợp**. `ALLOW FILTERING` cho phép server làm phần việc lọc tốn kém, không biến query thành lookup hiệu quả. Một query trả 5 rows vẫn có thể duyệt nhiều dữ liệu. Một giải pháp có thể là **bảng theo truy vấn** (ví dụ `orders_by_status_day`), index phù hợp sau khi benchmark, hoặc chuyển phân tích sang hệ thống chuyên dụng; không mặc định “thêm SAI là chữa mọi search”.

### 9.3. `LIMIT` không phải bằng chứng đã tối ưu

`LIMIT 50` thường giới hạn **số rows trả về**, chứ không đảm bảo chỉ đọc đúng 50 cells hoặc 50 SSTables. Ví dụ:

- Một partition có nhiều tombstone phải vượt qua các giá trị đã xóa mới tìm đủ 50 rows sống.
- Filtering phải kiểm nhiều row mới lọc được 50 kết quả.
- Nhiều partition được truy cập và phải nhận kết quả theo điều kiện/ordering đã định.
- Một request có `LIMIT 50` vẫn có response rộng nếu mỗi row chứa collection/blob lớn.

Đo `rows_scanned / rows_returned`, tombstones/read và bytes response thay vì chỉ nhìn LIMIT.

### 9.4. Phân biệt giảm cột trả về với giảm số row được đọc

~~~sql
-- Version 1: nhiều cột, có thể tải payload lớn.
SELECT *
FROM shop.orders_by_id
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

-- Version 2: chỉ trả những cột API cần.
SELECT status, total
FROM shop.orders_by_id
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

Projection có thể giảm response bytes, serialization, network và client heap. Nhưng nó không đảm bảo giảm số SSTable được chạm một cách tương ứng. **Phải đo cả network và read path**, nhất là nếu wide rows/tombstones là vấn đề thực.

### 9.5. Hot partition và skew khiến aggregate sai lệch

~~~text
Average family latency: 20ms
  tenant-small: p95=12ms
  tenant-medium: p95=30ms
  tenant-large: p95=600ms

Table.ReadLatency trung bình vẫn có thể không quá cao
nhưng một nhóm tenant đang vi phạm SLO nghiêm trọng.
~~~

Để phát hiện, có thể gắn **bucket kích thước** hoặc **tenant tier** cardinality thấp. Không tạo label với từng tenant ID. Từ trace/metadata/`EstimatedPartitionSizeHistogram`, xem partition outliers, token-range distribution và node chịu hotspot. Với workload có nhiều data centers, đo riêng `LOCAL_QUORUM` và vị trí coordinator.

## 10. Đi sâu vào một ứng viên bằng tracing và bằng chứng server

Khi shortlist đã xác định, dùng **một truy vấn đại diện** (hoặc một số outlier) để tìm chi phí bất thường. Không bật full tracing cho toàn bộ traffic production.

### 10.1. Thực hành tracing từ cqlsh

~~~sql
CONSISTENCY LOCAL_QUORUM;
TRACING ON;

SELECT event_time, event_id, status
FROM shop.orders_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND order_day = '2026-11-21'
  AND event_time >= '2026-11-21T08:00:00Z'
  AND event_time <  '2026-11-21T09:00:00Z'
LIMIT 50;

TRACING OFF;
~~~

**Cách đọc trace:**

1. Query được coordinator nào nhận? Local DC/CL có đúng không?
2. Những replica nào phản hồi, có retry/speculative attempt không?
3. Thời gian phân rã giữa coordinator, đợi replica, SSTable read, merge/reconciliation và trả kết quả.
4. Có nhiều row/cell được đọc rồi bị loại, warning tombstone hoặc dấu hiệu index/filter không?
5. Truy vấn chậm chỉ ở một partition hay nhiều partition? Có liên quan token ranges/hot nodes?

Trace **không phải EXPLAIN plan kiểu RDBMS**. Cassandra không có một `EXPLAIN ANALYZE` SQL phổ quát cho mọi CQL. Trace mô tả những sự kiện thực thi được ghi nhận trong request đó; nó có overhead, mức chi tiết phụ thuộc phiên bản, và một trace nhanh không phủ định outliers ở giờ cao điểm.

### 10.2. Tracing chỉ một phần traffic và FQL

Apache Cassandra có `system_traces` và công cụ bật tracing xác suất (ví dụ `nodetool settraceprobability` trên phiên bản hỗ trợ). **Chỉ dùng theo phê duyệt** vì mỗi trace tự tạo ghi metadata và có thể làm tải tăng; xác suất nhỏ trên hệ thống QPS rất lớn vẫn có thể sinh nhiều trace.

Từ Cassandra 4.0, **Full Query Logging (FQL)** có thể ghi query traffic để phân tích/replay; lệnh `nodetool enablefullquerylog` hỗ trợ các giới hạn queue/disk. FQL khác **tracing**: FQL thu query, không tự nói từng request đã quét bao nhiêu tombstone. Bật FQL production cần kiểm:

- Dung lượng log, rotation, queue memory, tác động I/O và thời hạn lưu.
- Quyền đọc dữ liệu nhạy cảm trong câu lệnh/bound values, mã hóa và chính sách retention.
- Có thể ghi đúng những query forms cần thiết mà không phát tán PII không.
- Chỉ chạy trong **cửa sổ kiểm soát**, giới hạn node/phạm vi và có kế hoạch tắt.

**Ưu tiên ứng dụng gắn query family metrics** để luôn có tần suất và latency dài hạn; dùng FQL/tracing khi cần điều tra **shape thực tế** hoặc outlier mà metrics aggregate chưa giải thích.

### 10.3. Kết hợp tracing với stats của table

~~~bash
nodetool tablestats shop.orders_by_tenant_day
nodetool tpstats
nodetool compactionstats
~~~

| Kết quả | Cách diễn giải hợp lý |
|---|---|
| Tracing thấy nhiều replica/page reads | Có thể query fan-out hoặc cần nhiều trang |
| `TombstoneScannedHistogram` cao + warnings | Scan nhiều dữ liệu đã xóa; xét TTL, DELETE, compaction/repair |
| `SSTablesPerReadHistogram` cao | Read amplification; xem compaction backlog/strategy |
| `EstimatedPartitionSizeHistogram` lệch lớn | Một số partition quá rộng, dễ tạo tail latency |
| `Compaction.PendingTasks` tăng và disk await tăng | Bottleneck chia sẻ; đừng vội sửa CQL vì query xấu |
| `ClientRequest.Read.Timeouts` tăng nhưng app QPS ổn | Kiểm node availability, overload, GC, consistency và retry |
| `RangeLatency` tăng sau bulk load | Có thể scan/range queries đang chịu SSTable/compaction pressure |

**Một bảng có thể có nhiều query families**, nên dùng trace và/hoặc thí nghiệm có kiểm soát để quy trách nhiệm. Khi query đọc chậm do toàn node đang compaction bão hòa, chỉnh `WHERE` của query không giải quyết được nút thắt vật lý.

### 10.4. Tách nguyên nhân ứng dụng và server

| Symptom | Hướng xác minh |
|---|---|
| API p99 cao nhưng Java CQL p99 ổn | Cache, downstream, serialization, queue của web server |
| Java CQL p99 cao nhưng Cassandra coordinator p99 ổn | Network, client pool, throttling, retry, timeouts, pagination |
| Coordinator p99 cao, local table p99 thấp | Chờ replica/quorum/network/queue hoặc fan-out |
| Local table read p99 cao và SSTables-per-read cao | Storage read amplification, compaction, disk |
| Local table read p99 cao và tombstones/read cao | TTL/DELETE pattern, clustering range/partition design |
| Một vài node có p99 cao hơn còn lại | Hotspot, token skew, disk/GC, topology, repair |

Đừng suy từ một row trong bảng này như một kết luận chắc chắn. Cần **cùng cửa sổ thời gian, cùng DC, cùng CL, cùng query family** và lặp lại trên nhiều mẫu.

## 11. Những nhiễu thường làm sai thứ tự ưu tiên

### 11.1. Không cùng cửa sổ đo

Đem p99 của `getById` lúc 2 giờ sáng so với p99 `listRecent` lúc 19 giờ là so sánh không công bằng. Thu ít nhất:

- Cửa sổ business peak có tải tương đương.
- Cửa sổ steady-state sau khi cluster đã warm cache.
- Cửa sổ batch/maintenance nếu workload đụng tài nguyên chung.
- Trước/sau deploy, schema change, bootstrap hoặc repair.

### 11.2. Chỉ đếm success

Một family có 20% timeout thì p95 chỉ trên 80% request thành công có thể **giảm** vì request tệ nhất bị loại. Ưu tiên tính cả số failure, timeout và số request vượt deadline; khi duration bị cắt ở timeout, ghi rõ **censored data**.

### 11.3. Latency của một page vs toàn bộ truy vấn

Java Driver có paging: khi gọi `execute()`, driver có thể trả **trang đầu**; những lần lặp qua `ResultSet` hoặc fetch tiếp sẽ phát sinh truy vấn trang sau. Nếu API cần hiển thị 5.000 rows, đo chỉ `execute()` sẽ **bỏ sót phần chi phí đọc hết**.

Ngược lại, API chỉ cần 50 rows đầu thì không cần fetch hết để đo. Đặt tên family có hậu tố `firstPage`/`allPages` và ghi page size, rows consumed/returned; chú ý cơ chế prefetch của driver khi ghi số page thật.

### 11.4. Mô hình bảng thay đổi nhưng không đổi template/version

Sau một lần redesign, cùng tên method `getRecentOrders` có thể query bảng khác hoặc dùng thêm time bucket. Nếu dùng lại label `query_family` nhưng không ghi `cql_template_id`/release, dễ trộn trước/sau và kết luận sai.

### 11.5. Percentiles không có tính cộng gộp

- Không lấy trung bình đơn giản của p95 từ 10 pods để gọi là p95 toàn dịch vụ.
- Không cộng p99 của từng chặng để gọi là p99 end-to-end.
- Phải hợp nhất **histogram/distribution phù hợp** hoặc tổng hợp từ raw observations theo cách có trọng số đúng.
- Nếu một family hiếm chỉ có 10 requests trong cửa sổ thì p99 gần như chỉ là max; báo **sample count** và độ tin cậy.

### 11.6. Resource cost có thể đến từ request khác

Một query chạy đúng lúc compaction/repair nặng dễ có latency cao nhưng không phải query gốc gây I/O. Trong thí nghiệm, giữ nguyên workload tổng, không làm thay đổi đồng thời batch jobs, RF, compaction cap hoặc node topology nếu muốn quy kết nguyên nhân.

## 12. Runbook chọn top truy vấn theo một chu kỳ vận hành

Một quy trình lặp lại có thể áp dụng **hàng tuần**, sau deploy lớn hoặc khi cluster vượt capacity/SLO.

### 12.1. Bước 0 — Xác định mục tiêu và phạm vi

Ví dụ mục tiêu: “Giảm p99 của các API order dưới 250 ms và đưa peak CPU/disk vào vùng an toàn, **không giảm CL hoặc làm sai thứ tự kết quả**.”

Chốt:

- Cluster, datacenter, Cassandra version, RF, keyspaces/tables.
- Danh sách services Java, release/feature flags, time windows (peak/steady/batch).
- SLO của từng business operation và error budget.
- Mức headroom mong muốn trên CPU, disk, network, heap/GC.
- Mẫu dữ liệu/tenant tier cần đại diện, yêu cầu quyền riêng tư và audit.

Không đưa một query vào top chỉ vì team A nói nó “chậm” mà không có thời gian quan sát, sample count và điều kiện chạy.

### 12.2. Bước 1 — Lập longlist từ metric ứng dụng

Tạo một dòng cho **mỗi query family**:

~~~text
Query family          Request/s  p50  p95  p99  error rate  SLO   Owner
order.getById           800      5    12   27   0.01%     40ms  checkout
order.listRecent         90     45   240  570   0.70%    150ms  order-api
order.searchStatus        4    650  2000 4100   2.00%    600ms  ops-ui
audit.exportNightly    0.05   1500  5000 8400   0.00%  10000ms  audit
~~~

**Đây là dữ liệu giả định.** Nếu metrics đang thiếu family labels, triển khai instrumentation trước khi kết luận; có thể dùng mẫu traffic ngắn hạn có kiểm soát để dựng longlist bước đầu, nhưng ghi rõ sampling bias.

### 12.3. Bước 2 — Ghép table và resource hotspots

Với các table mà longlist truy cập:

~~~bash
nodetool tablestats shop.orders_by_tenant_day
nodetool tablestats shop.orders_by_id
nodetool tpstats
nodetool compactionstats
nodetool status
~~~

Thu `ReadLatency`/`CoordinatorReadLatency`, `SSTablesPerReadHistogram`, `TombstoneScannedHistogram`, partition size, disk I/O, GC và CPU **trên từng node**. Ghi lại giờ metric bắt đầu tăng và query family nào tăng cùng lúc.

**Phân biệt correlation với attribution**:

- “Family listRecent p99 tăng cùng SSTablesPerRead trên table” là một **giả thuyết**.
- “Đo trace của listRecent cho thấy đọc nhiều SSTable và tombstone, thử cải tiến làm giảm đúng chỉ số đó” là **bằng chứng mạnh hơn**.

### 12.4. Bước 3 — Gắn cờ bắt buộc và xếp hạng

1. Các family gây lỗi nghiêm trọng/vi phạm SLO được xếp vào P0/P1 trước.
2. Các family QPS cao hoặc burst nhưng footprint lớn vào P1 capacity.
3. Các family còn lại có thể dùng priority score và estimate effort.
4. Query thiếu số liệu có thể được đưa vào “**investigate**”, không mặc định low-priority.
5. Phân biệt “điều tra ngay” với “triển khai thay schema ngay”: một query P1 có thể cần đo sâu trước khi chọn giải pháp.

### 12.5. Bước 4 — Trace ít ứng viên trước, không bật mọi thứ

Chọn tối đa vài family đầu để giữ tính tập trung. Với mỗi family:

~~~text
Family: order.listRecent
Hypothesis:
  Query đọc quá nhiều rows để lấy 50 rows hiển thị.
Evidence:
  Peak p95=240ms >150ms; QPS=90; 4 pages/request;
  table tombstones/read p95 cao; traces ở tenant lớn.
Proposed action:
  Kiểm bucket/day, time range, page size và giới hạn rows.
Expected impact:
  Giảm rows scanned và pages, cải thiện p95/p99.
Non-negotiable:
  Không làm thiếu sự kiện thuộc khoảng thời gian và
  không thay nghĩa thứ tự phân trang.
~~~

Tránh “tuning by rumor” kiểu “cứ thêm index cho tất cả cột” hoặc “tăng thread pool” khi chưa biết bottleneck.

### 12.6. Bước 5 — Thử một thay đổi, có control

Thiết kế A/B hoặc load test có repeatability:

- Giữ tương đương request mix, peak QPS, data size, hot keys, CL, page size và cache warmup.
- Không gộp thay schema với thay RF, JVM memory, compaction strategy và deploy cùng một thời điểm khi cần xác định nguyên nhân.
- Đo **success + timeout**, latency histogram, CPU/disk, tombstones, SSTables-per-read và returned rows.
- Đảm bảo **dữ liệu đúng** theo nghiệp vụ, nhất là khi thêm bucket/denormalization hoặc thay ordering.
- Có rollback/feature flag hoặc dual-read/dual-write theo lộ trình đã đánh giá.

### 12.7. Bước 6 — Kiểm chứng trên production có giới hạn

Phát hành canary, so sánh cùng time window/tier với baseline, mở traffic từng bước. Nếu giảm p99 nhưng CPU/disk tăng và tác động family khác, phải xem **tổng thể cluster**, không chỉ một dashboard của service.

Một thay đổi không đạt nếu:

- Latency giảm nhờ **hạ CL** mà vi phạm yêu cầu nhất quán của ứng dụng.
- Số hàng trả về giảm vì **bỏ dữ liệu cần thiết**, sai ordering hoặc paging.
- Không còn timeout vì **không xử lý lỗi thật**, bỏ qua exception hoặc tăng timeout vô hạn.
- Một node nóng/đĩa bão hòa hơn dù mean latency toàn cluster đẹp hơn.

### 12.8. Bước 7 — Công bố kết quả và quay lại longlist

~~~text
QUERY TUNING REVIEW — kỳ 2026-W47, số liệu giả định
1. P1 listRecent:
   Owner: order-api
   Trước: p95=240ms, peak=400QPS, 4 pages/request
   Sau:   p95=120ms, peak=400QPS, 1 page/request
   Data correctness: PASS
   Resource effect: CPU/disk không tăng; tombstone scan giảm

2. P1 searchStatus:
   Owner: ops-ui
   Điều tra: ALLOW FILTERING, nhiều partitions
   Action: thiết kế bảng theo truy vấn, kiểm backfill/dual-write
   Status: EXPERIMENT; chưa triển khai production

3. P2 getById:
   800 QPS, p95=12ms dưới SLO=40ms
   Status: MONITOR; không ưu tiên sửa trước hai P1
~~~

Mỗi kỳ phải cập nhật cả **top queries** và **những việc đã trì hoãn có lý do**. Nếu data growth/feature mới làm một family từ 4 lên 100 QPS, cần xếp hạng lại.

## 13. Dashboard và truy vết: hiển thị sao cho không đánh lừa người vận hành

### 13.1. Các panel tối thiểu

| Panel | Labels | Dùng để |
|---|---|---|
| QPS theo query family | service/family/release/DC | Tìm family nóng và burst |
| p50/p95/p99 theo family | service/family/DC/CL | Xác định SLO breach, tail latency |
| Error/timeout rate | family/error class | Không chỉ đo những request thành công |
| In-flight request và driver pool | service/instance/DC/node | Xem queue client và tăng retries |
| Response bytes/rows/pages | family/result_mode | Phân biệt payload và paging |
| Cassandra ClientRequest | node/DC/Read/Write/CAS | Phân biệt coordinator-wide latency và lỗi |
| Table ReadLatency, SSTablesPerRead, tombstones | node/table | Xác định table hotspot và read amplification |
| Compaction/flush/commit log | node/table | Đánh giá bottleneck chia sẻ |
| Disk/CPU/GC/network | node/disk/DC | Phân biệt query inefficiency với vấn đề hạ tầng |
| Change markers | release/schema/RF/topology/repair | Liên kết hồi quy với thay đổi vận hành |

**Không gắn mỗi partition key/tenant/user/SQL text làm label**. Để điều tra outlier, có thể dùng **trace IDs** với dữ liệu được kiểm soát tại log/tracing backend, thay vì biến IDs thành time-series labels.

### 13.2. Ví dụ PromQL mang tính định hướng

Vì tên metrics sau exporter không cố định, đoạn dưới **không phải câu lệnh sẵn chạy**. Giả sử app sử dụng Micrometer, xuất histogram bucket `app_cql_family_duration_seconds_bucket` và counter `app_cql_family_requests_total`:

~~~promql
# p95 theo family trên cửa sổ 5 phút, chỉ khi histogram
# đã được exporter đưa ra dưới đúng tên bucket này.
histogram_quantile(
  0.95,
  sum by (le, service, query_family) (
    rate(app_cql_family_duration_seconds_bucket[5m])
  )
)
~~~

~~~promql
# Request QPS theo family, đổi tên metric theo hệ thống thực tế.
sum by (service, query_family) (
  rate(app_cql_family_requests_total[5m])
)
~~~

~~~promql
# Error rate logic; mẫu denominator phải đếm cả failure.
sum by (service, query_family) (
  rate(app_cql_family_requests_total{outcome!="success"}[5m])
)
/
clamp_min(
  sum by (service, query_family) (
    rate(app_cql_family_requests_total[5m])
  ),
  1e-9
)
~~~

**Hạn chế:** `histogram_quantile` cần histogram buckets có ý nghĩa và đủ sample; client metrics đôi khi dùng summary hoặc timer không cung cấp đúng bucket. Kiểm format exporter trước khi dán query. Đối với Prometheus classic histogram, có thể tính quantiles từ tổng bucket; không lấy trung bình p99 của từng JVM.

### 13.3. Khung số liệu theo ba cửa sổ

~~~text
Window A — 5 phút gần nhất:
  phát hiện sự cố và spikes

Window B — peak một giờ:
  kiểm nhu cầu capacity tại giờ cao điểm

Window C — 7 đến 14 ngày:
  đánh giá xu hướng tăng dữ liệu, seasonality
  và lựa chọn query cần tối ưu dài hạn
~~~

Nên ghi version/release markers và loại trừ các đợt maintenance bất thường khi mục tiêu là chọn **inefficient query shape**. Nhưng nếu maintenance luôn đụng traffic peak, nó vẫn là **rủi ro vận hành thật** cần ưu tiên phối hợp.

## 14. Quyết định “tối ưu query hay sửa tầng khác?”

Không phải mọi SLO breach cần viết lại CQL:

| Bằng chứng | Hướng hành động ưu tiên |
|---|---|
| Scan quá nhiều rows/tombstones so với kết quả | Đổi truy cập theo partition/clustering, TTL/delete strategy, bảng theo truy vấn |
| Nhiều pages và payload rộng | Giới hạn kết quả thực sự cần, projection, page size và UI contract |
| Query fan-out nhiều partitions do model sai | Thiết kế bảng/partition key theo access pattern |
| SAI/index query có selectivity thấp | Chọn lọc lại predicate, benchmark index vs denormalized table, tính fan-out |
| LWT contention tăng | Giảm tranh chấp một key, thiết kế workflow hoặc phân tách hot partitions |
| Tất cả family trên một node tăng p99 + disk await | Điều tra disk/compaction/repair/capacity, chưa quy riêng một CQL |
| Driver pool exhausted và retry tăng | Điều tra connection pool, concurrency, timeout, idempotency |
| Ứng dụng xử lý JSON/serialization rất chậm | Sửa tầng app, không tối ưu Cassandra vô ích |
| Nightly job đụng peak nhưng có thể dời giờ | Scheduling/rate limit thay vì redesign một query hiếm |
| Ứng dụng đọc lặp cùng key quá nhiều | Xem cache có TTL/invalidation phù hợp, không áp dụng mù quáng |

**Trọng tâm lựa chọn:** Mỗi ứng viên phải có giả thuyết **có thể bị bác bỏ**. Nếu giảm rows scanned mà p99 vẫn không cải thiện, kiểm network/pools/GC thay vì tuyên bố query tuning thành công bằng số liệu không liên quan.

## 15. Lab CQL: so sánh ba mẫu truy vấn trên cùng dữ liệu

**Mục tiêu lab:** Tạo một bảng nhỏ theo mô hình query-driven, chạy ba query families có shape khác nhau, bật tracing chọn lọc và lập bảng bằng chứng. Bài thực hành **không yêu cầu tạo tải nặng**; với vài row, latency và chi phí thường rất nhỏ, vì thế không được suy ra benchmark cho dataset production.

**Môi trường:** Apache Cassandra 4.1 hoặc 5.0 lab một node, `cqlsh`, quyền đọc `nodetool`. Ví dụ `SimpleStrategy` RF=1 chỉ để học trên một node; production nhiều DC cần `NetworkTopologyStrategy` và RF phù hợp.

### Bước 1 — Tạo keyspace và bảng có time bucket

~~~sql
CREATE KEYSPACE IF NOT EXISTS query_priority_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS query_priority_lab.events_by_tenant_day (
    tenant_id text,
    day date,
    event_time timestamp,
    event_id uuid,
    status text,
    payload text,
    PRIMARY KEY ((tenant_id, day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

Thiết kế:

- **Partition key**: `(tenant_id, day)` — một tenant trong một ngày.
- **Clustering key**: `(event_time, event_id)` — truy vấn theo khoảng thời gian, có thứ tự và tie-break duy nhất.
- `status` là **regular column**, không tự trở thành lookup key hiệu quả; lọc theo `status` trong partition có thể phải scan.
- Không có join, không có `ORDER BY` tùy ý trên các cột không phải clustering.

### Bước 2 — Nạp dữ liệu mẫu nhỏ

~~~sql
INSERT INTO query_priority_lab.events_by_tenant_day
  (tenant_id, day, event_time, event_id, status, payload)
VALUES ('tenant-a', '2026-11-21', '2026-11-21T08:00:00Z',
  11111111-1111-1111-1111-111111111111, 'NEW', 'created');

INSERT INTO query_priority_lab.events_by_tenant_day
  (tenant_id, day, event_time, event_id, status, payload)
VALUES ('tenant-a', '2026-11-21', '2026-11-21T08:05:00Z',
  22222222-2222-2222-2222-222222222222, 'PAID', 'payment accepted');

INSERT INTO query_priority_lab.events_by_tenant_day
  (tenant_id, day, event_time, event_id, status, payload)
VALUES ('tenant-a', '2026-11-21', '2026-11-21T08:10:00Z',
  33333333-3333-3333-3333-333333333333, 'PAID', 'confirmed');

INSERT INTO query_priority_lab.events_by_tenant_day
  (tenant_id, day, event_time, event_id, status, payload)
VALUES ('tenant-a', '2026-11-21', '2026-11-21T08:15:00Z',
  44444444-4444-4444-4444-444444444444, 'CANCELLED', 'cancelled');

INSERT INTO query_priority_lab.events_by_tenant_day
  (tenant_id, day, event_time, event_id, status, payload)
VALUES ('tenant-b', '2026-11-21', '2026-11-21T08:30:00Z',
  55555555-5555-5555-5555-555555555555, 'PAID', 'confirmed');

INSERT INTO query_priority_lab.events_by_tenant_day
  (tenant_id, day, event_time, event_id, status, payload)
VALUES ('tenant-a', '2026-11-20', '2026-11-20T18:00:00Z',
  66666666-6666-6666-6666-666666666666, 'PAID', 'previous day');
~~~

Lab nhỏ để nhìn shape; **không** tăng lên hàng triệu rows trong production chỉ để chứng minh `ALLOW FILTERING` có thể chậm. Nếu lab đã từng chạy, các INSERT lặp sẽ cập nhật cùng primary keys; khi đo latency phải phân biệt cold/warm cache và lần tạo bảng.

### Bước 3 — Family A: đọc một row bằng khóa đầy đủ

~~~sql
CONSISTENCY ONE;
TRACING ON;

SELECT status, payload
FROM query_priority_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND day = '2026-11-21'
  AND event_time = '2026-11-21T08:05:00Z'
  AND event_id = 22222222-2222-2222-2222-222222222222;

TRACING OFF;
~~~

Gắn nhãn `events.getExact`. Đây là điểm truy cập dự đoán được: partition key và clustering key đầy đủ. Quan sát trace được in ra: coordinator, replica, thời gian và thao tác thực hiện. Không lấy một lần chạy làm p99.

### Bước 4 — Family B: slice trong partition

~~~sql
TRACING ON;

SELECT event_time, event_id, status
FROM query_priority_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND day = '2026-11-21'
  AND event_time >= '2026-11-21T08:00:00Z'
  AND event_time <  '2026-11-21T09:00:00Z'
LIMIT 3;

TRACING OFF;
~~~

Gắn nhãn `events.listByHour`. Do clustering `event_time` được sắp DESC trong partition, Cassandra có thể tìm và trả range phù hợp. Thay đổi LIMIT hoặc khoảng thời gian có thể thay số rows được đọc/returned và số trang; trong dataset nhỏ việc khác biệt latency không đáng kể.

### Bước 5 — Family C: filtering trong partition (chỉ lab)

~~~sql
-- Chỉ dùng khi đã biết bảng rất nhỏ và được phép filtering.
TRACING ON;

SELECT event_time, event_id, status
FROM query_priority_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND day = '2026-11-21'
  AND status = 'PAID'
ALLOW FILTERING;

TRACING OFF;
~~~

Gắn nhãn `events.filterPaidWithinDay`. Nếu cluster bật guardrail chặn `ALLOW FILTERING`, câu lệnh có thể bị từ chối; đó **không phải lỗi lab**, hãy ghi nhận guardrail thay vì tắt bảo vệ trên production.

Truy vấn này **vẫn có partition key**, nên ví dụ so sánh **filtering trong một partition**, không phải quét vô điều kiện toàn cluster. Khi partition chứa nhiều ngày? Không: partition đã được bucket theo ngày. Khi một tenant/ngày có hàng triệu events, nó **vẫn** có thể quét rất nhiều rows để lấy vài rows PAID. Đây chính là lý do cần đo `scanned/returned ratio` khi traffic tăng.

### Bước 6 — Quan sát table, SSTable và tombstone

~~~bash
nodetool tablestats query_priority_lab.events_by_tenant_day
nodetool compactionstats
nodetool tpstats
~~~

Từ metrics/JMX, đọc `ReadLatency`, `SSTablesPerReadHistogram`, `TombstoneScannedHistogram` và `LiveScannedHistogram` nếu exporter sẵn có.

**Hạn chế của lab này:** Số rows quá ít để phân biệt áp lực I/O, disk/CPU hoặc p99 có ý nghĩa. Nếu muốn benchmark, phải chuyển sang **staging riêng**, nạp dữ liệu đại diện về kích thước partition, TTL/DELETE, traffic mix, key skew và RF. **Không** suy ra “Family C nhanh hơn A” chỉ vì một lần CQL shell chạy 2 ms và A chạy 3 ms.

### Bước 7 — Quan sát phân trang

~~~sql
PAGING 2;

SELECT event_time, event_id, status
FROM query_priority_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND day = '2026-11-21';

PAGING ON;
~~~

Câu lệnh `PAGING 2` đặt page size của **cqlsh** cho buổi thử, không tự sửa page size của ứng dụng Java. Khi API cần tất cả pages, phải đo số trang và thời gian hết kết quả; nếu API chỉ cần top 3 thì đừng fetch toàn bộ rồi bỏ phần dư.

### Bước 8 — Điền bảng xếp hạng từ số liệu của chính mình

| Thuộc tính | A — getExact | B — listByHour | C — filterPaidWithinDay |
|---|---|---|---|
| SLO được định nghĩa? | Tự điền | Tự điền | Tự điền |
| QPS thực tế trong ứng dụng? | Cần instrumentation | Cần instrumentation | Cần instrumentation |
| p95/p99 dưới tải đại diện? | Cần load test | Cần load test | Cần load test |
| Phạm vi partition | Một partition | Một partition | Một partition |
| Số rows dự kiến phải xét | Một khóa chính xác | Một range | Có thể nhiều rows để lọc |
| Page/response bytes | Đo | Đo | Đo |
| Tombstones/read, SSTables/read | Đo | Đo | Đo |
| Ưu tiên? | Dựa vào 3 trục | Dựa vào 3 trục | Dựa vào 3 trục |

**Kết luận đúng của lab:** Shape C có thể đắt khi partition lớn, **nhưng không thể xếp ưu tiên thực tế** nếu chưa đo QPS, latency và chi phí trong workload đại diện. Bài tập dạy cách **ra quyết định dựa trên bằng chứng**, không đưa sẵn thứ hạng bằng trực giác.

### Bước 9 — Phác thảo mô hình nếu family C thực sự là trọng yếu

Nếu nghiệp vụ thường yêu cầu “events PAID của một tenant trong một ngày”, có thể xem một bảng truy vấn riêng:

~~~sql
-- Ví dụ schema định hướng; cần thiết kế dual-write/backfill/TTL và
-- điều kiện đúng dữ liệu trước khi triển khai thực tế.
CREATE TABLE IF NOT EXISTS query_priority_lab.events_by_status_day (
    tenant_id text,
    day date,
    status text,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((tenant_id, day, status), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

SELECT event_time, event_id, payload
FROM query_priority_lab.events_by_status_day
WHERE tenant_id = 'tenant-a'
  AND day = '2026-11-21'
  AND status = 'PAID'
LIMIT 50;
~~~

Schema này chỉ chứng minh **access path**, chưa có dữ liệu vì không tự chuyển row từ bảng cũ. Để production dùng được, cần:

- Backfill dữ liệu lịch sử có kiểm soát.
- Dual-write/CDC/outbox hoặc pipeline đồng bộ đáng tin.
- Xử lý **status thay đổi**: xóa entry với status cũ, ghi entry status mới.
- Thiết kế TTL/DELETE, repair, retry và idempotency cho cả hai bảng.
- Đối soát theo nguồn sự thật để bảo đảm bảng derived không thiếu/thừa rows.

Chỉ nên chấp nhận chi phí write amplification/denormalization nếu **frequency × SLO × resource savings** của query C đủ lớn để biện minh.

## 16. Java Driver 4.x: đo đúng query family ngay tại ứng dụng

Driver 4.x có metrics chung ở cấp session/node, nhưng để **xếp hạng từng query family**, cách thực dụng là instrument tại repository/service với tên operation ổn định. Ví dụ dưới dùng **Java 17 + DataStax Java Driver 4.x + Micrometer Core**, trong đó `MeterRegistry` được ứng dụng DI cung cấp. Đây là code minh họa, không cần khởi tạo một Cassandra session hoặc MeterRegistry mới cho mỗi request.

### 16.1. Repository có hai query family khác nhau

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;

public final class EventRepository {
    public record EventSummary(
            Instant eventTime, UUID eventId, String status) {}

    private final CqlSession session;
    private final MeterRegistry metrics;
    private final PreparedStatement getExact;
    private final PreparedStatement listByHour;

    public EventRepository(CqlSession session, MeterRegistry metrics) {
        this.session = session;
        this.metrics = metrics;

        this.getExact = session.prepare(
            "SELECT event_time, event_id, status " +
            "FROM query_priority_lab.events_by_tenant_day " +
            "WHERE tenant_id = ? AND day = ? " +
            "AND event_time = ? AND event_id = ?");

        this.listByHour = session.prepare(
            "SELECT event_time, event_id, status " +
            "FROM query_priority_lab.events_by_tenant_day " +
            "WHERE tenant_id = ? AND day = ? " +
            "AND event_time >= ? AND event_time < ? LIMIT 50");
    }

    public EventSummary getExact(
            String tenantId, LocalDate day,
            Instant eventTime, UUID eventId) {
        return observe("events.getExact", () -> {
            BoundStatement query = getExact.bind(
                    tenantId, day, eventTime, eventId)
                .setConsistencyLevel(DefaultConsistencyLevel.ONE);

            Row row = session.execute(query).one();
            return row == null ? null : convert(row);
        });
    }

    public List<EventSummary> listByHour(
            String tenantId, LocalDate day,
            Instant startInclusive, Instant endExclusive) {
        return observe("events.listByHour", () -> {
            BoundStatement query = listByHour.bind(
                    tenantId, day, startInclusive, endExclusive)
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setPageSize(50);

            ResultSet result = session.execute(query);
            List<EventSummary> events = new ArrayList<>();
            for (Row row : result) {
                events.add(convert(row));
            }
            return events;
        });
    }

    private static EventSummary convert(Row row) {
        return new EventSummary(
            row.getInstant("event_time"),
            row.getUuid("event_id"),
            row.getString("status"));
    }

    private <T> T observe(String family, Supplier<T> operation) {
        // "family" chỉ nhận giá trị TĨNH từ code, không dùng tenantId.
        long started = System.nanoTime();
        boolean success = false;
        try {
            T answer = operation.get();
            success = true;
            return answer;
        } finally {
            String outcome = success ? "success" : "failure";
            long elapsed = System.nanoTime() - started;

            Timer.builder("app.cql.family.duration")
                .tag("service", "query-lab")
                .tag("query_family", family)
                .tag("outcome", outcome)
                .publishPercentileHistogram()
                .register(metrics)
                .record(elapsed, TimeUnit.NANOSECONDS);

            Counter.builder("app.cql.family.requests")
                .tag("service", "query-lab")
                .tag("query_family", family)
                .tag("outcome", outcome)
                .register(metrics)
                .increment();
        }
    }
}
~~~

Giải thích kỹ:

1. `PreparedStatement` được chuẩn bị **một lần** trong constructor, không prepare lại mỗi request.
2. Hai phương thức có **hai nhãn query family tĩnh**, không dùng UUID/tenant ID để tránh label cardinality.
3. `getExact` chỉ lấy một hàng; `listByHour` đọc hết tập kết quả nhưng đã có `LIMIT 50` trong CQL để ràng buộc phạm vi. Timer bao gồm cả quá trình lặp qua result, thay vì dừng ngay khi `execute()` trả trang đầu.
4. `Timer` ghi **wall-clock elapsed** theo `System.nanoTime()`. Nó không đo CPU/disk của Cassandra; phải ghép với metrics table/OS.
5. Nhãn `outcome` cho phép không loại các request lỗi khỏi phân phối. Trong thực tế, nên tách **timeout/unavailable/validation failure** thành số loại hữu hạn, thay vì chỉ success/failure.
6. `Timer.builder(...).register(metrics)` có thể dùng cho demo; production có thể **cache các Timer/Counter đã đăng ký** theo tập query families cố định để tránh overhead lookup/allocations mỗi request.

**Mục đích mã lab:** Dùng CL=`ONE` vì keyspace `query_priority_lab` có RF=1. Production cần chọn `LOCAL_QUORUM` hoặc mức thích hợp theo RF/DC và hợp đồng nhất quán; **không copy CL ONE cho nghiệp vụ nhạy cảm**.

### 16.2. Sử dụng trong chương trình

~~~java
// Đặt trong một phương thức đã có CqlSession và MeterRegistry.
EventRepository repo = new EventRepository(session, meterRegistry);

EventRepository.EventSummary exact = repo.getExact(
    "tenant-a",
    LocalDate.parse("2026-11-21"),
    Instant.parse("2026-11-21T08:05:00Z"),
    UUID.fromString("22222222-2222-2222-2222-222222222222"));

List<EventRepository.EventSummary> recent = repo.listByHour(
    "tenant-a",
    LocalDate.parse("2026-11-21"),
    Instant.parse("2026-11-21T08:00:00Z"),
    Instant.parse("2026-11-21T09:00:00Z"));
~~~

Kết quả có thể được xuất ra hệ thống monitoring qua `MeterRegistry` mà ứng dụng đã cấu hình. Với Prometheus exporter, kiểm histogram buckets thật có xuất hay không rồi mới dùng `histogram_quantile`.

### 16.3. Phân biệt đo một lần gọi với đo toàn bộ workflow

Nếu API gọi:

~~~text
GET /orders/{id}
    |
    +-- events.getExact  (CQL family A)
    +-- orderPayments.getById (CQL family B)
    +-- fraudService.verify (HTTP)
    +-- JSON serialization
~~~

Một timer bao quanh `events.getExact` chỉ đo **phần A**. API p99 có thể chậm do `fraudService.verify`. Nếu chỉ xem server `Table.ReadLatency` rồi sửa A, bạn có thể tối ưu sai chỗ.

Nên có:

- API span/timer **end-to-end**.
- Nested spans/timers cho từng **query family** và các downstream calls.
- Driver session/node metrics để xác minh thời gian network/retry.
- Server JMX metrics để biết pressure của replica/table.

Với asynchronous driver APIs, đo từ lúc submit tới khi future hoàn tất hoặc page tương ứng đã được consume; không dừng timer ngay sau `executeAsync()` vì lúc đó request thường chưa hoàn thành.

### 16.4. Khi cần đo rows/pages/response size

Trong method `listByHour`, có thể ghi thêm:

- `returned_rows = events.size()`.
- Số lần fetch trang bổ sung nếu thiết kế custom async paging; chú ý driver có thể prefetch.
- Kích thước response ước lượng nếu có một tầng serialization đo bytes.
- `page_size`/`LIMIT`/`CL` như metadata cố định hoặc một số giá trị phân nhóm có kiểm soát.

Không giả danh `events.size()` là “rows scanned” của server: Cassandra có thể phải quét nhiều rows/tombstones để trả về số nhỏ này. Ghép với trace và table metrics khi cần suy chi phí I/O.

## 17. Ba case study chọn đúng truy vấn

### 17.1. Ca A — Query có p99 xấu nhưng QPS thấp

~~~text
Family: customer.searchStatus
QPS bình thường = 3; peak=80; p99=4.2s; SLO=600ms
Rows returned ≈ 15; trace cho thấy quét rất nhiều rows
Một số lần chạy lúc 18:00 làm disk await tăng trên 3 nodes
~~~

**Quyết định:** Có thể xếp P1 capacity/SLO dù thường ít QPS. Kiểm filtering, index selectivity, partition access và timing của batch. Một bảng theo query hoặc chuyển workload search sang hệ thống chuyên dụng có thể hợp lý hơn tăng timeout.

**Bẫy:** Chỉ nhìn QPS trung bình và bỏ qua 80 QPS peak; từ đó tính capacity thấp hơn thực tế rất nhiều.

### 17.2. Ca B — Query rất nhiều QPS nhưng đang đạt SLO

~~~text
Family: order.getById
800 QPS trung bình, peak=2000; p95=12ms; SLO=40ms
Point lookup theo primary key, response≈2KiB
Disk/CPU và p99 node ổn định, còn headroom
~~~

**Quyết định:** Giữ trong dashboard và dự báo tăng trưởng; chưa cần ưu tiên hơn query P1. Nếu dự đoán QPS x3 với headroom thấp, có thể đưa vào capacity optimization dù latency hiện đẹp.

**Bẫy:** Xem 800 QPS là lý do bắt buộc sửa, làm dự án tốn công nhưng không cải thiện user/business hoặc capacity thực.

### 17.3. Ca C — Nhiều query cùng chậm vì node nền quá tải

~~~text
Trong peak:
  getById p99:       30 -> 300 ms
  listRecent p99:   200 -> 900 ms
  searchStatus p99:   2 ->   8 s

Cùng lúc:
  Disk await trên node N3 tăng cao.
  Compaction pending và repair streaming tăng.
  GC pause cũng tăng.
~~~

**Quyết định:** Mở incident về shared bottleneck trước. Có thể tạm dời repair/batch theo runbook và phân tích capacity. Chỉ sau khi cluster ổn định mới phân biệt query family nào **vốn đã** đắt.

**Bẫy:** Sửa ba câu CQL đồng thời và kết luận thành công khi repair tự kết thúc, dù thay CQL không phải nguyên nhân hồi phục.

### 17.4. Ca D — Tối ưu latency nhưng tệ hơn resource

Một ứng viên `listRecent` được đổi từ hai query nhỏ sang một query đọc rất rộng. Mean latency có thể giảm do bớt round trips, nhưng server phải scan nhiều rows hơn, tombstone và disk I/O tăng.

**Quyết định:** Chỉ chấp nhận nếu **SLO, throughput headroom, resource footprint và correctness** đều đạt. Trong Cassandra, giảm số request **không tự động** giảm tổng tài nguyên.

### 17.5. Ca E — Đọc ít nhưng sinh write amplification

Một query tìm đơn theo trạng thái được tối ưu bằng bảng `orders_by_status`. Read latency tốt hơn, nhưng mọi status change phải DELETE bản cũ + INSERT bản mới; TTL và repair của bảng phụ tạo thêm workload.

**Quyết định:** So lợi ích **query frequency × saved cost** với chi phí **write traffic × number of derived tables**, complexity và risk dữ liệu lệch. Chỉ triển khai khi có cơ chế đồng bộ đáng tin và kiểm thử dữ liệu.

## 18. Đánh giá kết quả tối ưu: không chỉ “query nhanh hơn”

### 18.1. Bốn cổng xác nhận

| Cổng | Câu hỏi | Điều kiện đạt |
|---|---|---|
| **A — Correctness** | Dữ liệu, ordering, paging, TTL, consistency có còn đúng không? | Kiểm bằng dữ liệu kỳ vọng và test nghiệp vụ |
| **B — Latency/SLO** | p95/p99 và failure rate có cải thiện trong peak không? | Đạt SLO theo cùng cửa sổ và sample đáng tin |
| **C — Resource** | CPU/disk/network/memory và scan/SSTable/tombstone có giảm hoặc còn headroom? | Không đẩy chi phí sang node/table khác quá mức |
| **D — Operability** | Có rollback, owner và monitoring sau deploy? | Có khả năng phát hiện hồi quy/backfill/dual-write lỗi |

### 18.2. Kết quả giả định của một thử nghiệm

| Chỉ số `order.listRecent` | Trước | Sau | Diễn giải |
|---|---:|---:|---|
| Peak QPS | 400 | 400 | Traffic tương đương |
| p95 | 240 ms | 120 ms | Đạt SLO 150 ms |
| p99 | 570 ms | 240 ms | Tail tốt hơn |
| Timeout rate | 0,7% | 0,1% | Đo đủ cả failure |
| Pages/request | 4 | 1 | Giảm fetch nếu semantics tương đương |
| Rows returned | 50 | 50 | Chưa bị cắt thiếu kết quả |
| Tombstones scanned p95 | 300 | 30 | Giả định có ít dữ liệu bị che phải đọc hơn |
| Disk read p99 trên node nóng | 35 ms | 18 ms | Tài nguyên cải thiện nhưng cần kiểm các node khác |

Đây là **bảng số minh họa**, không bảo đảm chỉ cần đổi `LIMIT` là đạt kết quả này. Trong thực tế, cần đo nhiều cửa sổ đủ mẫu, so sánh data skew và đảm bảo không có thay đổi cluster cùng lúc làm sai kết luận.

### 18.3. Nếu chỉ đạt hai trong bốn cổng?

- A fail: **không triển khai**, dù p99 tốt.
- B fail: xem lại giả thuyết, truy vết bottleneck tiếp.
- C fail: xem rủi ro capacity; có thể giảm latency bằng cách tiêu thêm quá nhiều tài nguyên.
- D fail: chưa đủ điều kiện rollout lớn, cần canary/rollback/monitor.

Với query family **trọng yếu**, tính đúng và an toàn rollback phải là điều kiện **không thỏa hiệp**.

## 19. Những ngộ nhận khiến chọn nhầm query

| Nhận định sai | Vì sao sai? | Cách tiếp cận đúng |
|---|---|---|
| “Truy vấn p99 cao nhất luôn đáng tối ưu trước.” | Có thể là job nền rất hiếm, đang nằm trong SLO | Xét SLO, tần suất, peak burst và business criticality |
| “QPS cao nhất phải sửa đầu tiên.” | Query point lookup có thể rẻ và đủ headroom | Đo chi phí mỗi request và tổng footprint |
| “Total wall-clock ms × QPS = CPU seconds.” | Latency gồm đợi network/I/O/quorum/queue | Tách concurrency proxy khỏi CPU/disk thật |
| “Table.ReadLatency cho biết câu CQL nào chậm.” | Metric theo bảng/node, gộp nhiều query families | Instrument family ở Java và trace ứng viên |
| “Java Driver `cql-requests` tự gắn nhãn theo CQL template.” | Metrics session gộp các request | Tạo timer ở repository/service theo family cố định |
| “Một lần cqlsh 2 ms nhanh hơn một lần 3 ms là bằng chứng.” | Caching, warmup, sampling và tải biến động | Benchmark nhiều mẫu với cùng workload và dữ liệu |
| “Request trả 10 row nên chỉ đọc 10 row.” | Filtering/tombstone có thể scan nhiều row | Đo scanned/returned, tombstone, SSTables-per-read |
| “`LIMIT 50` luôn giới hạn cost tới 50 rows.” | Có thể phải xét nhiều tombstone hoặc filters | Kiểm trace/metrics, không suy từ LIMIT |
| “`ALLOW FILTERING` là cách sửa truy vấn không có index.” | Có thể quét phạm vi lớn và latency khó dự đoán | Thiết kế bảng theo query hoặc index có benchmark |
| “Một partition key đúng thì query luôn nhanh.” | Hot partition/partition rộng/TTL có thể tốn | Kiểm kích thước partition, clustering range và skew |
| “Gộp p99 từ nhiều pod bằng cách lấy trung bình.” | Percentile không cộng tuyến tính | Gộp histogram/raw samples theo cách thống kê đúng |
| “Metrics chỉ cần gắn SQL text và tenant ID làm label.” | High-cardinality và rò rỉ thông tin | Label theo family/template/version và dimension hữu hạn |
| “Chỉ đo requests thành công là đủ.” | Timeout bỏ khỏi histogram làm tail latency có vẻ đẹp | Đếm failure/timeout, đo cả SLA violations |
| “Retry làm hết timeout nên query đã được tối ưu.” | Có thể tạo thêm attempts và che lỗi gốc | Đo retry cost, idempotency, in-flight và server pressure |
| “Tạo thêm bảng đọc mới chỉ có lợi.” | Write amplification, backfill, consistency của bảng phụ | Đo chi phí đọc/ghi toàn hệ thống và correctness |
| “Mọi query cùng chậm thì phải chỉnh từng WHERE.” | Có thể do disk, GC, compaction, node down | Điều tra bottleneck chung trước |
| “Tăng timeout nghĩa là đạt SLO.” | SLO thường về latency/error budget, không phải số timeout cấu hình | Dùng percentile, tỷ lệ dưới threshold và error budget |
| “Chọn top 3 xong là giữ thứ hạng mãi.” | Dataset, traffic, feature và topology thay đổi | Review định kỳ và sau thay đổi lớn |

## 20. Checklist nhanh để quyết định ứng viên nào vào backlog tối ưu

### 20.1. Trước khi đưa vào top candidates

- [ ] Mẫu CQL/operation có một **query family** ổn định và owner rõ.
- [ ] Biết keyspace/table, partition key, clustering key, CL và local DC.
- [ ] Có số request và QPS **trung bình lẫn giờ cao điểm** trong cùng kỳ.
- [ ] Có p50/p95/p99, tỷ lệ timeout/failure và SLO tương ứng.
- [ ] Đã phân biệt time-to-first-page với time-to-all-pages.
- [ ] Có ước lượng response bytes/rows và tài nguyên server đi kèm.
- [ ] Đã kiểm table/node hotspot, compaction, tombstones và disk/GC nếu nghi vấn.
- [ ] Số liệu đủ mẫu; không trung bình hóa p99 của các nhóm khác nhau.
- [ ] Không có raw values/bind data/tenant ID nhạy cảm trong metric labels.
- [ ] Đã tách P0/P1 (SLO/capacity) khỏi P2 (tối ưu kế hoạch).
- [ ] Có giả thuyết nguyên nhân **có thể kiểm chứng bằng trace/test**.
- [ ] Có cách đo hiệu quả và tác động lên query families khác.

### 20.2. Trước khi triển khai một cách tối ưu

- [ ] Đã so sánh workload đại diện về QPS, peak, partition size, tombstone, page size.
- [ ] Đã có test correctness và kiểm toán số/loại hàng trả về, ordering, TTL và paging.
- [ ] Đã đánh giá yêu cầu RF/CL; không tự hạ consistency để có latency đẹp.
- [ ] Có owner, canary, rollback và kế hoạch data migration nếu thêm bảng mới.
- [ ] Đã đánh giá write amplification/backfill/dual-write nếu thay schema.
- [ ] Đã đo cả latency, timeout, node/disk/CPU và resource footprint trước–sau.
- [ ] Không tạo sự cố bằng cách dùng `ALLOW FILTERING` trên dataset production rất lớn để “benchmark”.
- [ ] Không bật full tracing/FQL vô hạn hoặc ghi giá trị nhạy cảm vào log.
- [ ] Đã đặt mốc review lại khi QPS hoặc data size thay đổi.

## 21. Câu hỏi tự đánh giá

**Câu 1.** `A` có 2.000 QPS và p95 10 ms, SLO 50 ms. `B` có 50 QPS, p95 350 ms, SLO 150 ms. Truy vấn nào cần điều tra trước?  
**Định hướng:** B có SLO breach; A vẫn phải đánh giá capacity nếu QPS cao nhưng không mặc định ưu tiên hơn.

**Câu 2.** `getOrder` đọc 2 KiB/request với 1.000 QPS. `listOrders` đọc 200 KiB/request với 100 QPS. Query nào có response bytes/s lớn hơn?  
**Định hướng:** getOrder ≈ 2.000 KiB/s; listOrders ≈ 20.000 KiB/s. Response bytes chưa đại diện disk reads.

**Câu 3.** Một query 4 QPS, mỗi lần quét khoảng 100.000 rows và chỉ trả 10. Có thể bỏ qua vì ít QPS không?  
**Định hướng:** Không; peak và scanned/returned rất lớn, dễ là capacity risk.

**Câu 4.** Vì sao 800 QPS × mean latency 6 ms không thể gọi là 4,8 giây CPU/giây?  
**Định hướng:** Đây là concurrency tương đương theo thời gian lưu trú, gồm đợi network/replica/disk, không phải CPU time.

**Câu 5.** Cassandra `Table.ReadLatency` và Java Driver `cql-requests` đều tăng. Có thể biết query family cụ thể chưa?  
**Định hướng:** Chưa. Cần instrumentation theo template/family hoặc sampling/tracing.

**Câu 6.** Một client chỉ fetch trang đầu, service khác đọc hết 20 pages. Có nên gộp p99 của cả hai chỉ vì cùng câu CQL?  
**Định hướng:** Không. Phải phân biệt result mode, page size và tổng số trang thực sự consume.

**Câu 7.** Query trả 5 rows bằng `ALLOW FILTERING`. Có nghĩa chỉ 5 rows được đọc?  
**Định hướng:** Không; Cassandra có thể scan nhiều rows/partitions/tombstones để lọc.

**Câu 8.** Vì sao không đưa `tenant_id` vào nhãn Prometheus?  
**Định hướng:** Cardinality lớn, chi phí metrics, nguy cơ lộ dữ liệu; dùng query family và bucket có giới hạn.

**Câu 9.** Một số máy p99 cao, máy khác thấp. Có nên lấy trung bình p99 của máy để công bố p99 toàn cluster?  
**Định hướng:** Không; gộp raw histogram/distribution đúng cách, phân tích node hotspot.

**Câu 10.** Query p95 cao đồng thời toàn cluster đang repair và disk await tăng. Nên sửa schema ngay chưa?  
**Định hướng:** Chưa; kiểm shared bottleneck, đánh giá lại khi tải nền được kiểm soát.

**Câu 11.** Khi thiết kế bảng `events_by_status_day`, cần làm gì ngoài `CREATE TABLE` để query trả đủ dữ liệu?  
**Định hướng:** Backfill, dual-write/CDC, xóa entry status cũ khi đổi trạng thái, retry/idempotency, đối soát dữ liệu.

**Câu 12.** Khi thử một query mới, p95 giảm 40% nhưng số rows trả về giảm từ 50 còn 30 dù cùng bộ lọc. Có được công bố thành công?  
**Định hướng:** Không nếu semantics yêu cầu 50 rows; correctness gate fail.

**Câu 13.** Query A có 0,01 QPS và p99 10 s, nhưng SLO job nền 20 s và không ảnh hưởng peak. Có bắt buộc là P1?  
**Định hướng:** Không. Có thể defer, nhưng cần xem resource spike/operational risk.

**Câu 14.** Tại sao một `nodetool tablestats` sạch không đảm bảo mọi query family của bảng đạt SLO?  
**Định hướng:** Metric aggregate theo node/table có thể che outliers, page consumption, client retry và tenant skew.

**Câu 15.** Vì sao `cql-messages` của driver có thể vượt `cql-requests`?  
**Định hướng:** Retry, speculative execution và các attempts vật lý tới node, không phải một request ứng dụng = một message.

**Câu 16.** Query giảm p99 nhưng làm `PendingCompactions` và disk usage tăng ở toàn bộ replica. Đánh giá điều gì?  
**Định hướng:** Resource gate, write amplification, workload tổng và headroom; có thể cần rollback/điều chỉnh.

## 22. Tổng kết

~~~text
                API / JAVA SERVICE REQUESTS
                           |
                  Gắn QUERY FAMILY
                           |
             +-------------+-------------+
             |             |             |
          LATENCY       FREQUENCY      RESOURCE
          p95/p99       QPS / burst    rows/pages/tombstones
          SLO/failure   in-flight      CPU/disk/bytes/fan-out
             |             |             |
             +-------------+-------------+
                           |
                  BUSINESS CRITICALITY
                           |
                      Triage P0/P1/P2
                           |
                    Shortlist có owner
                           |
                Trace + server metrics
                           |
                   Giả thuyết kiểm chứng
                           |
              Thử 1 thay đổi + đo A/B
                           |
           +---------------+---------------+
           |               |               |
        CORRECTNESS      LATENCY         CAPACITY
           |               |               |
           +---------------+---------------+
                           |
                 Canary / rollback / review
~~~

**Nguyên lý quan trọng nhất:** Truy vấn trọng yếu không chỉ là truy vấn **chậm nhất**, cũng không chỉ là truy vấn **chạy nhiều nhất**. Trong Cassandra, phải kết hợp **latency/SLO, tần suất/peak và chi phí thực tế của replica/table/node**, rồi ưu tiên theo impact nghiệp vụ và độ an toàn của thay đổi. Một câu CQL có `LIMIT 50` vẫn có thể quét nhiều tombstone, còn một point lookup 800 QPS vẫn có thể là lựa chọn hiệu quả. **Đo đúng query family → chọn ứng viên có bằng chứng → kiểm chứng nguyên nhân → đánh giá cải thiện toàn hệ thống** là quy trình tối ưu bền vững.

## Tài liệu tham khảo

- [Apache Cassandra — Introduction to Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html) — mô hình dữ liệu theo truy vấn, partition key và việc hạn chế số partition cần đọc.
- [Apache Cassandra — CQL Data Manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html) — `SELECT`, `LIMIT`, `PER PARTITION LIMIT`, `ALLOW FILTERING`, clustering range và các hạn chế truy vấn.
- [Apache Cassandra — Monitoring metrics](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html) — `Table.ReadLatency`, `CoordinatorReadLatency`, `SSTablesPerReadHistogram`, tombstone metrics, `ClientRequest` metrics.
- [Apache Cassandra — cqlsh](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html) — `TRACING ON/OFF`, `PAGING` và các lệnh tương tác.
- [Apache Cassandra — Full Query Logging](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/fqllogging.html) — thu traffic CQL có giới hạn để phân tích và replay.
- [Apache Cassandra — nodetool tablestats](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/tablestats.html) — thống kê SSTable, read/write và tombstone theo bảng.
- [Apache Cassandra — Tombstones](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/tombstones.html) — tác động của DELETE/TTL tới read path và compaction.
- [DataStax Java Driver 4.17 — Metrics](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/metrics/) — metrics session/node, cách bật và scope.
- [DataStax Java Driver 4.17 — Configuration Reference](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/configuration/reference/) — `cql-requests`, `cql-messages`, timeouts, histograms và configuration.
- [DataStax Java Driver 4.17 — Prepared Statements](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/statements/prepared/) — bind metadata, routing key và tối ưu tương tác query-driven.
- [DataStax Java Driver 4.17 — Speculative Query Execution](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/speculative_execution/) — tail latency, rủi ro tạo thêm tải và quan hệ với retry.
