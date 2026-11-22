# Mức hiệu năng cơ sở, SLI/SLO và ngưỡng cảnh báo cho cluster Apache Cassandra

## 1. Tại sao cần baseline trước khi đặt cảnh báo?

**Apache Cassandra** là cơ sở dữ liệu **wide-column phân tán**: dữ liệu trải trên nhiều node, request được coordinator xử lý rồi liên hệ các replica theo **replication factor (RF)** và **consistency level (CL)**. Độ trễ của một truy vấn có thể tăng do thiết kế partition không phù hợp, đọc nhiều tombstone, GC, compaction, mạng giữa replica, disk I/O hoặc tải ứng dụng thay đổi.

Một dashboard hiển thị “CPU 75%” hoặc “p99 150 ms” **chưa đủ kết luận hệ thống có vấn đề hay không**. Cần biết bình thường cluster chạy với tải nào, loại truy vấn nào, cam kết nào với người dùng và lúc nào phải gọi người trực vận hành.

Bài học phân biệt bốn khái niệm:

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| **Baseline** (mức hiệu năng cơ sở) | Hành vi bình thường của hệ thống ở tải, cấu hình và thời điểm xác định là gì? | p99 read 95–130 ms ở 2.000 req/s trong giờ cao điểm |
| **SLI** (*Service Level Indicator*) | Đo chất lượng thực tế theo định nghĩa và cửa sổ nào? | Tỷ lệ request đọc hợp lệ thành công; tỷ lệ đọc hoàn tất ≤ 250 ms |
| **SLO** (*Service Level Objective*) | Chất lượng tối thiểu mong muốn trong một khoảng thời gian? | 99,95% read thành công trong 30 ngày |
| **Alert threshold** (ngưỡng cảnh báo) | Khi nào có nguy cơ vi phạm mục tiêu hoặc cần con người can thiệp? | Error-budget burn cao ở cả cửa sổ 1 giờ và 5 phút |

**Baseline là quan sát thực nghiệm; SLO là mục tiêu dịch vụ.** Không nên lấy p99 đang rất tệ làm SLO chỉ vì đó là trạng thái “bình thường” của hệ thống chưa được tối ưu. Ngược lại, SLO rất tham vọng nhưng không có khả năng đo và không được thống nhất với người dùng cũng khó giúp vận hành.

Trong ví dụ xuyên suốt, giả định dịch vụ Java truy vấn Cassandra để lấy trạng thái thiết bị theo `device_id`, ghi sự kiện vào bảng time-series và yêu cầu availability/latency riêng cho hai lớp request này. Tất cả số liệu minh họa dưới đây **là giả định phục vụ học tập**, không phải khuyến nghị ngưỡng mặc định cho mọi cluster.

## 2. Đo ở đâu trong đường đi của request?

Một request từ ứng dụng Java không đồng nhất với một thao tác nội bộ của Cassandra:

```text
     Người dùng / API
             |
             v
     Dịch vụ Java
     [pool, queue, retry, timeout]
             |
             v
     Java Driver 4.x
       [load balancing]
             |
             v
      Coordinator node  ----> Replica A
             |          ----> Replica B
             |          ----> Replica C
             |
      [CL/RF, read repair,
       network, memtable/SSTable]
             |
             v
        Phản hồi về app
```

Phân biệt ba tầng quan sát:

1. **Người dùng/API:** latency end-to-end và outcome mà người dùng thực sự nhận. Đây thường là nơi thích hợp để đo SLI của sản phẩm.
2. **Ứng dụng/Java Driver:** latency thao tác Cassandra từ góc nhìn client, lỗi timeout/unavailable, retry, pool, số request chờ. Thích hợp cho SLI của **phụ thuộc Cassandra từ ứng dụng**.
3. **Cassandra node/cluster:** độ trễ client request ở server, request rate, queue, dropped messages, compaction, GC, disk, tombstone, repair. Đây là các **chỉ báo nguyên nhân** để chẩn đoán.

Một request thất bại ở API vì lỗi logic ứng dụng không nhất thiết là lỗi Cassandra. Ngược lại, một request ghi trả về thành công từ coordinator chưa chắc đáp ứng **toàn bộ kỳ vọng nghiệp vụ**, ví dụ một mutation timestamp cũ thua last-write-wins. Muốn SLI có ý nghĩa, phải định nghĩa chính xác **sự kiện thành công**, **ranh giới đo**, **những lớp request** và **cửa sổ thống kê**.

### Đừng trộn các loại consistency level

`ONE`, `LOCAL_QUORUM`, `QUORUM` và `ALL` có đường xử lý, mức chờ replica và đặc tính failure khác nhau. Cần gắn ít nhất `operation`/`query_class`/`consistency` khi phân tích, nhưng tránh gắn partition key hoặc UUID người dùng vào metric label vì sẽ gây **cardinality explosion**.

## 3. Thu baseline như thế nào cho đáng tin?

Một baseline có ích là **tập đường chuẩn theo bối cảnh**, không phải một con số “trung bình latency” được chụp một lần.

### Các chiều bối cảnh tối thiểu

- **Workload:** read theo partition key, range query trong partition, write, LWT, batch; tách request nhẹ và truy vấn quét nhiều row.
- **Lưu lượng:** request/giây, concurrency, payload size, row size, số partition truy cập và phân bố hot key.
- **Topology:** node count, data center, RF, CL, node đang down hay tất cả healthy.
- **Dữ liệu:** kích thước bảng, số SSTable, số tombstone, TTL, kích thước partition, hit/miss cache.
- **Thời gian:** giờ cao điểm/thấp điểm, ngày thường/cuối tuần, các đợt backfill và compaction/repair.
- **Phiên bản và thay đổi:** Cassandra, Java Driver, JVM, hệ điều hành, schema, compaction strategy và cấu hình timeout.

### Quy trình thiết lập

1. **Chọn cửa sổ khỏe mạnh** đủ dài để thấy chu kỳ tải, ví dụ 14–28 ngày nếu có dữ liệu và không bị sự cố bao phủ.
2. Xác định những **query class quan trọng** cho dịch vụ và các CL tương ứng.
3. Thu cùng lúc request rate, success/error, p50/p95/p99 client latency, server latency, saturation, compaction/GC và disk.
4. Ghi rõ **phiên bản cấu hình và điều kiện tải** của baseline, đánh dấu deploy, repair, node down và sự kiện bất thường.
5. Nếu hệ thống mới chưa có lịch sử, dùng **load test trên staging tương đồng**, sau đó hiệu chỉnh bằng số liệu production khi có.
6. Tách baseline **theo giờ/tải**; cập nhật định kỳ nhưng không để sự cố dài ngày tự trở thành “mức chuẩn” mới.

**Ví dụ baseline GIẢ ĐỊNH** của một dịch vụ đã chạy ổn định (không phải benchmark Cassandra):

| Query class | Tải quan sát | p50 từ app | p99 từ app | Tỷ lệ lỗi | Ghi chú |
|---|---:|---:|---:|---:|---|
| `read_device_by_id` | 1.500 req/s | 12 ms | 110 ms | 0,01% | `LOCAL_QUORUM`, hot keys được kiểm soát |
| `write_event` | 800 req/s | 9 ms | 75 ms | 0,02% | Append-only, TTL 7 ngày |
| `read_device_day` | 80 req/s | 38 ms | 310 ms | 0,03% | Nhiều row hơn, chỉ trong 1 partition |
| `lwt_update_state` | 25 req/s | 75 ms | 520 ms | 0,05% | CAS/Paxos, không gộp với ghi thường |

Các con số này chỉ so sánh được nếu **cùng định nghĩa cách đo**. Khi đọc p99, cần cả sample count và thời gian đo; một query class chỉ có vài request trong 5 phút thì p99 rất nhiễu.

## 4. Tứ trụ theo dõi: latency, traffic, errors và saturation

Mô hình **four golden signals** có thể áp dụng cho Cassandra, nhưng cần dịch ra các metric cụ thể.

| Tín hiệu | Tầng ứng dụng | Tầng Cassandra/node | Câu hỏi chẩn đoán |
|---|---|---|---|
| **Latency** | Duration của CQL request, p50/p95/p99, % dưới ngưỡng | ClientRequest read/write latency, server histogram, coordinator activity | Người dùng chậm hay server chậm? |
| **Traffic** | Request/s theo query class và CL, bytes | Read/write operations, network I/O, request rate | Tải tăng do khách hàng hay retry storm? |
| **Errors** | Timeout, unavailable, driver error, deadline exceeded | Failure/unavailable/timeout metrics nếu phiên bản cung cấp; dropped messages | Request nào thất bại, mức nào? |
| **Saturation** | In-flight/queued requests, driver pool pressure | CPU, GC pause, heap, disk I/O, disk free, compaction backlog, thread-pool pending tasks | Giới hạn tài nguyên nào đang tới? |

Đừng chỉ theo dõi một metric “CPU cao”. Một cluster có thể có CPU vừa phải nhưng **disk latency rất cao**, hoặc p99 tăng do **tombstone** của vài partition. Ngược lại CPU tăng vào đợt compaction nhưng latency vẫn đạt SLO có thể không cần cảnh báo gọi người ngay.

Một nguyên tắc hữu ích:

- **SLI/SLO** ưu tiên triệu chứng mà ứng dụng/người dùng cảm nhận.
- **Metric node** giúp tìm nguyên nhân và dự báo suy giảm.
- **Alert** kết hợp tác động thực tế với dấu hiệu sắp cạn năng lực hoặc mất an toàn dữ liệu.

## 5. Định nghĩa SLI có tử số, mẫu số và đơn vị rõ ràng

### 5.1. Availability SLI

Với nhóm request Cassandra đọc theo partition key:

```text
availability = số request hợp lệ có outcome "success"
               ---------------------------------------
                 tổng request hợp lệ được thực hiện
```

Cần quy định:

- **Mẫu số:** một logical operation của ứng dụng hay từng network attempt tới coordinator? Thường nên tính **logical operation**, tránh retry làm tăng mẫu số và bóp méo SLI.
- **Success:** truy vấn thực thi thành công, kể cả trả **không có row** nếu đó là kết quả nghiệp vụ hợp lệ.
- **Failure:** timeout khi deadline kết thúc, unavailable, lỗi server/driver không được phục hồi trong budget, hoặc kết quả không đáp ứng yêu cầu đã định.
- **Excluded:** có thể loại request kiểm thử hoặc lỗi do client gửi input sai, nhưng danh sách loại trừ phải được định nghĩa từ trước; không loại timeout chỉ vì “request vẫn có thể đã ghi ở replica”.

### 5.2. Latency SLI

Một định nghĩa ít gây hiểu lầm hơn “latency tốt”:

```text
fast_read_ratio =
  số logical read thành công hoàn tất trong <= 250 ms
  --------------------------------------------------
                số logical read thành công
```

Đây là **tỷ lệ request dưới ngưỡng**, không phải p99. Có thể dùng p99 như dấu hiệu phân tích, nhưng SLO nên có tử số/mẫu số rõ. Cần nói rõ latency được tính từ lúc **ứng dụng gọi driver** tới lúc nhận kết quả, có tính thời gian chờ pool/retry hay không. Nếu đo API end-to-end, ngưỡng 250 ms phải hiểu là toàn bộ API chứ không phải chỉ database.

### 5.3. Freshness và correctness nếu ứng dụng yêu cầu

Với dữ liệu cảm biến, có thể có SLI:

- **Freshness:** % thiết bị đang hoạt động có bản đo gần nhất không quá 2 phút theo nguồn thời gian tin cậy.
- **Completeness:** % event ID kỳ vọng được ingest đúng hạn, đo ở pipeline/broker thay vì chỉ dựa trên row Cassandra.
- **Correctness:** % chuyển trạng thái tuân business version hoặc không ghi trùng; cần instrumentation nghiệp vụ.

Không được lấy `CL = QUORUM` làm định nghĩa “100% dữ liệu mới nhất”: consistency level không bảo đảm thứ tự nghiệp vụ hay clock accuracy.

## 6. Thiết lập SLO theo lớp truy vấn và error budget

Một SLO cần có **đối tượng, metric, ngưỡng, cửa sổ, nguồn dữ liệu và owner**. Bảng sau là một đề xuất **GIẢ ĐỊNH** cho việc học:

| Dịch vụ / query class | SLI | SLO trong 30 ngày | Đơn vị |
|---|---|---:|---|
| `read_device_by_id` | Logical read thành công / tổng read hợp lệ | **99,95%** | Availability |
| `write_event` | Logical write được xác nhận theo CL / tổng write hợp lệ | **99,9%** | Availability của đường ghi |
| `read_device_by_id` | Read thành công ≤ 250 ms / tổng read thành công | **99%** | Latency |
| `read_device_day` | Read thành công ≤ 750 ms / tổng read thành công | **99%** | Latency theo query class riêng |

**Error budget** là lượng kết quả không đạt SLO còn chấp nhận được trong cửa sổ:

```text
allowed_bad_fraction = 1 - SLO
allowed_bad_requests ≈ eligible_requests × allowed_bad_fraction
```

Ví dụ 1.000.000 lần đọc hợp lệ trong 30 ngày:

- SLO availability **99,95%** cho phép khoảng **500** lần không thành công.
- SLO latency **99%** cho phép khoảng **10.000** lần đọc thành công vượt 250 ms nếu mẫu số latency đúng 1.000.000.
- Nếu chỉ có 900.000 read **thành công**, budget latency của 99% là **9.000 slow read**, không phải 10.000: **mẫu số đã khác**.

### Error-budget policy

SLO không nên chỉ nằm trên dashboard. Có thể quy định:

1. Khi burn rate tăng cao: ưu tiên giảm lỗi, rollback thay đổi nguy hiểm, tạm dừng load test/backfill không khẩn cấp.
2. Khi đã tiêu phần lớn budget tháng: rà soát rủi ro deploy và kế hoạch tăng dung lượng.
3. Sau sự cố: xác định loại request bị ảnh hưởng, lượng budget đã tiêu và quyết định cải tiến có owner.

Không cố “bảo vệ” SLO bằng cách xóa các request khó khỏi mẫu số sau khi xảy ra lỗi. Thay đổi định nghĩa SLI phải có version và được thống nhất.

## 7. Percentiles, histogram và cửa sổ đo: tránh đánh giá sai

**Average latency** thường che mất long tail. Với Cassandra, một vài partition nóng hoặc những request đọc nhiều tombstone có thể làm p99 cao dù p50 ổn.

| Thống kê | Ý nghĩa | Giới hạn |
|---|---|---|
| p50 | Trung vị: một nửa sample không vượt mốc này | Không phản ánh request chậm nhất |
| p95 | 95% sample không vượt mốc này | Có thể bỏ qua tail 5% quan trọng |
| p99 | 99% sample không vượt mốc này | Nhiễu ở mẫu ít và nhạy với burst |
| Mean | Trung bình | Bị che bởi phân bố lệch hoặc outlier |
| % ≤ ngưỡng | Tỷ lệ đạt deadline | Phù hợp một SLI latency được định nghĩa rõ |

Nếu một node có p99 50 ms và node khác có p99 500 ms, **không được lấy trung bình hai p99** để suy p99 của cluster. Muốn aggregate nên dùng **histogram buckets** phù hợp hoặc tính phân vị từ toàn bộ phân bố theo hệ thống metrics.

### Chọn cửa sổ đúng mục đích

- **5 phút:** phát hiện spike; nhiễu khi lưu lượng thấp.
- **1 giờ:** kiểm tra suy giảm kéo dài và burn nhanh.
- **6 giờ/24 giờ:** phát hiện suy giảm chậm, compaction backlog kéo dài.
- **7 hoặc 30 ngày:** đánh giá SLO dài hạn và xu hướng.

Mỗi biểu đồ nên ghi rõ **timezone, thời gian, aggregation, request volume, CL và query class**. Tăng số node hoặc thay retry policy giữa hai kỳ có thể khiến metric “total requests” đổi ý nghĩa nếu không ghi chú.

### Histogram cần bucket hợp với SLO

Nếu latency SLO là 250 ms, histogram ứng dụng cần một bucket ở **`0.25` giây** (hoặc cách tính tỷ lệ tương đương). Nếu bucket gần nhất là 0,1 và 0,5 giây, phép nội suy bằng `histogram_quantile` không thể khôi phục chính xác số request ≤ 250 ms.

## 8. Thu metric Cassandra: server, exporter và Java Driver

Cassandra thường cung cấp metrics qua **JMX**, được nhóm theo loại như **ClientRequest**, **Table**, **ThreadPools**, **Compaction**, **Storage**, **Cache** và các chỉ số JVM. Tên MBean, phạm vi `scope`, kiểu meter/timer và **đơn vị exporter đưa ra** có thể khác theo phiên bản Cassandra/bản phân phối và cấu hình JMX exporter.

Những nhóm quan sát quan trọng:

| Nhóm | Tín hiệu nên thu | Vấn đề gợi ý |
|---|---|---|
| **ClientRequest Read/Write** | Request latency, timeouts, failures, unavailable (nếu có) | User-facing failures, coordinator quá tải |
| **ThreadPools** | Active/pending/completed tasks, dropped tasks/messages | Queue kéo dài, request bị rơi |
| **Compaction** | Pending tasks, bytes compacted, workload compaction | Backlog, áp lực I/O/dung lượng |
| **Table** | Read/write latency, SSTable count, tombstone scanned, partition-size metrics nếu có | Schema/partition/tombstone gây tail latency |
| **Storage** | Load, streaming/hints, node state | Mất cân bằng node, bootstrap/repair |
| **Cache** | Hit/miss, eviction theo cache khả dụng | Cache churn và read amplification |
| **JVM** | Heap/non-heap, GC frequency/pause | GC stop-the-world, memory pressure |
| **OS/Disk/Network** | CPU, disk capacity, disk latency/queue, network retransmit | Saturation phần cứng và mạng |

**Không lấy tên Prometheus metric trong một bài viết làm cam kết rằng cluster đã có sẵn nó.** Cassandra đưa metrics qua JMX; Prometheus JMX exporter/Jolokia hoặc agent có thể đổi tên, đổi đơn vị và labels. Phải kiểm tra MBean thực tế và mapping của exporter trên **đúng phiên bản** trước khi viết alert.

### Vận hành dashboard theo từng lớp

Một dashboard tối thiểu có:

1. **Service overview:** availability, latency SLI, error-budget burn và request volume.
2. **Cassandra cluster:** status/up/down, RF/CL context, per-node read/write rate, latencies, failures.
3. **Bottlenecks:** thread pools pending, dropped messages, GC, disk, compaction, hints/repair.
4. **Hot tables/partitions:** read/write skew, tombstone, partition sizes và các query class gây tải.
5. **Change context:** deploy, schema alteration, topology change, compaction/repair và workload backfill.

Tránh gộp tất cả vào một biểu đồ tổng. **Một node duy nhất** bị disk latency nặng có thể bị che bởi trung bình của cluster dù CL QUORUM đã bắt đầu chạm timeout.

## 9. Instrument ứng dụng để có SLI chuẩn

Metrics **tự định nghĩa ở ứng dụng** giúp đo từng *logical operation*. Ví dụ cách đặt tên cho Prometheus/Micrometer (đây là **metric minh họa do ứng dụng phát**, không phải metric Cassandra mặc định):

- `app_cassandra_requests_total{operation, outcome, consistency}` — counter đếm logical operations.
- `app_cassandra_request_duration_seconds_bucket{operation, outcome, le}` — histogram bucket số logical operations đã hoàn tất theo latency.
- `app_cassandra_request_duration_seconds_count{operation, outcome}` — số sample của cùng histogram.
- `app_cassandra_inflight_requests{operation}` — gauge request đang chạy.

Chỉ dùng các nhãn **có tập giá trị hữu hạn**: `operation=read_by_id|write_event|read_day`, `outcome=success|failure`, `consistency=LOCAL_QUORUM|ONE`. **Không** dùng `device_id`, `order_id`, `query_text` hay `exception_message` làm label metric: cardinality có thể tăng vô hạn.

Quy ước quan trọng:

- Mỗi **logical operation** ghi đúng một outcome sau khi kết thúc chuỗi retry, nếu SLI tính theo logical operation.
- Phân loại exception: timeout, unavailable, server failure, validation lỗi client; chi tiết exception nên nằm ở trace/log, nhãn metric chỉ là nhóm thấp cardinality.
- Dùng `System.nanoTime()` để tính **elapsed duration**, không dùng `System.currentTimeMillis()` làm phép đo latency.
- Gắn trace ID vào log/trace, không đẩy mọi trace ID thành label Prometheus.
- Đo thời gian chờ driver pool/retry nếu ranh giới SLI đã chọn là thời gian thao tác Cassandra từ phía app.

## 10. PromQL mẫu để đọc SLI (chỉ dùng với metrics ứng dụng đã khai báo)

Các truy vấn dưới đây giả định ứng dụng **thực sự xuất** những metrics/labels ở mục 9 với đơn vị giây. Chúng **không tự chạy được trên một Cassandra cluster mới cài** nếu chưa có instrumentation.

### 10.1. Tỷ lệ logical read không thành công trong 5 phút

```promql
sum(rate(app_cassandra_requests_total{
  operation="read_by_id",outcome="failure"
}[5m]))
/
clamp_min(
  sum(rate(app_cassandra_requests_total{
    operation="read_by_id"
  }[5m])),
  1e-9
)
```

Giá trị `0.002` là **0,2% lỗi** trong cửa sổ tương ứng. SLI availability = `1 - error_ratio`, giả sử mỗi logical request được gắn đúng một outcome success/failure.

### 10.2. Tỷ lệ read thành công trong ≤ 250 ms

```promql
sum(rate(app_cassandra_request_duration_seconds_bucket{
  operation="read_by_id",outcome="success",le="0.25"
}[5m]))
/
clamp_min(
  sum(rate(app_cassandra_request_duration_seconds_count{
    operation="read_by_id",outcome="success"
  }[5m])),
  1e-9
)
```

Để đúng nghĩa, histogram phải khai báo **bucket `0.25`** và đếm **một lần cho mỗi logical read thành công**, kể cả khi driver đã retry nội bộ.

### 10.3. p99 cho điều tra hiệu năng, không phải tự động là SLO

```promql
histogram_quantile(
  0.99,
  sum by (le) (
    rate(app_cassandra_request_duration_seconds_bucket{
      operation="read_by_id",outcome="success"
    }[5m])
  )
)
```

Đây là ước lượng từ histogram bucket, không phải phép đo hoàn toàn chính xác ở mức từng request. Nếu dùng native histogram hoặc exporter format khác, cần điều chỉnh cú pháp. Trong cả ba truy vấn, cửa sổ quá ít traffic nên có **volume gate** hoặc đánh dấu insufficient data, tránh coi `0/0` được clamp thành số 0 là một hệ thống “khỏe”.

## 11. Ngưỡng cảnh báo: phân biệt page, ticket và dashboard

Cảnh báo chỉ hữu ích nếu người nhận **có hành động cụ thể**. Nên tách các mức:

| Mức | Loại tín hiệu | Ví dụ (minh họa, cần hiệu chỉnh) | Hành động |
|---|---|---|---|
| **Page / P1** | SLO burn nhanh, phần lớn request hỏng, sắp hết disk | Burn rate cao ở hai cửa sổ; node down làm mất khả năng đạt CL | Điều tra ngay theo runbook |
| **Page / P2** | SLO suy giảm kéo dài hoặc rủi ro rất gần | Burn cao ở 6 giờ và 30 phút; dung lượng dự báo cạn trong giờ tới | Người trực xử lý theo severity |
| **Ticket** | Tiến triển xấu, còn thời gian xử lý | Disk free dưới ngưỡng dự phòng, compaction pending tăng nhiều giờ | Lập kế hoạch capacity/tuning |
| **Dashboard/info** | Biến động không có tác động hiện tại | Spike GC ngắn không ảnh hưởng SLI | Theo dõi, không đánh thức on-call |

Một ngưỡng có thể dùng cho **capacity** nhưng không đủ làm page:

- Cảnh báo cảnh giác khi **disk free dưới 20%** và tốc độ tăng dung lượng khiến dự kiến cạn trong vài ngày.
- Cảnh báo khẩn khi **disk free dưới 10%** hoặc dự báo cạn rất sớm, nhất là node đang mất cân bằng/compaction cần thêm đĩa tạm.
- **Các ngưỡng 20%/10% chỉ minh họa**. Cassandra có compaction, streaming/repair và snapshot có thể cần headroom lớn; capacity phải dựa trên kích thước SSTable, độ lệch node, chiến lược compaction và tốc độ tăng dữ liệu.

**Không đặt page cho “CPU > 70% trong 1 phút” như điều kiện độc lập.** CPU cao nhưng latency/availability đạt SLO có thể là tải hợp lệ. Ngược lại, disk latency tăng gây timeout dù CPU thấp cũng cần hành động.

## 12. Error-budget burn rate và cảnh báo nhiều cửa sổ

Burn rate cho biết hệ thống tiêu budget nhanh hơn mức đều đặn bao nhiêu lần:

```text
budget_fraction = 1 - availability_slo
burn_rate = observed_error_fraction / budget_fraction
```

Với read availability SLO **99,95%**:

```text
budget_fraction = 1 - 0.9995 = 0.0005 = 0.05%
Nếu lỗi quan sát = 0.72%:
burn_rate = 0.0072 / 0.0005 = 14.4
```

Nếu duy trì burn **14,4** trong **1 giờ**, với cửa sổ SLO 30 ngày (720 giờ), hệ thống tiêu xấp xỉ **2% budget tháng chỉ trong 1 giờ**: `14.4 × 1 / 720 = 0.02`.

### Cảnh báo multi-window, multi-burn-rate (ví dụ cấu hình)

Một lựa chọn khởi đầu, **không phải ngưỡng áp dụng đại trà**:

- **Fast burn:** tỷ lệ lỗi lớn hơn `14.4 × budget_fraction` trong **cả 1 giờ và 5 phút**, kèm đủ request. Dùng để page sự cố nhanh.
- **Medium burn:** lớn hơn `6 × budget_fraction` trong **cả 6 giờ và 30 phút**. Dùng để phát hiện suy giảm kéo dài.
- **Slow burn:** lớn hơn `1 × budget_fraction` trong cửa sổ dài như 3 ngày và 6 giờ, có thể tạo ticket thay vì page.

Đặt alert theo **tỷ lệ lỗi** và **sản lượng request**. Nếu chỉ có 2 request/giờ, một lần timeout tạo 50% lỗi nhưng mức ý nghĩa đối với hệ thống có thể khác một sự cố ảnh hưởng 100.000 request/giờ. Ngược lại, các dịch vụ ít traffic nhưng quan trọng cần tín hiệu bổ sung như synthetic probes hoặc kiểm tra event freshness.

### Prometheus alert rule minh họa

Rule dưới đây giả định metric ứng dụng `app_cassandra_requests_total` theo chuẩn ở mục 9 và SLO read 99,95%; hãy thay `operation`/labels theo hệ thống thực:

```yaml
groups:
  - name: cassandra-dependent-service-slo
    rules:
      - alert: CassandraReadFastBurn
        expr: |
          (
            sum(rate(app_cassandra_requests_total{
              operation="read_by_id", outcome="failure"
            }[1h]))
            /
            clamp_min(sum(rate(app_cassandra_requests_total{
              operation="read_by_id"
            }[1h])), 1e-9)
          ) > (14.4 * 0.0005)
          and
          (
            sum(rate(app_cassandra_requests_total{
              operation="read_by_id", outcome="failure"
            }[5m]))
            /
            clamp_min(sum(rate(app_cassandra_requests_total{
              operation="read_by_id"
            }[5m])), 1e-9)
          ) > (14.4 * 0.0005)
          and
          sum(increase(app_cassandra_requests_total{
            operation="read_by_id"
          }[1h])) >= 1000
        for: 2m
        labels:
          severity: page
        annotations:
          summary: "Read error budget is burning rapidly"
          description: "Check logical read failures and Cassandra runbook"
```

Rule trên là **mẫu học tập**: chỉ đúng nếu counters có label như giả định, request được đếm chính xác một lần, Prometheus scrape đủ và metric không bị thay đổi tên. Trong production nên có recording rules để dễ đọc, phân vùng theo service/region/DC và kiểm tra missing telemetry (*no data*). Volume gate ở đây là 1.000 request/giờ, không phải con số mặc định cho mọi dịch vụ.

## 13. Ngưỡng cảnh báo nhân quả trên Cassandra node

Một số tình huống cần cảnh báo dù tỷ lệ lỗi chưa vượt SLO, vì chúng báo **sắp mất khả năng phục vụ hoặc an toàn dữ liệu**.

| Tín hiệu | Warn khi... | Page khi... | Điều cần đối chiếu |
|---|---|---|---|
| **Node unavailable** | Một node bị down nhưng RF/CL còn phục vụ | Mất đủ replica khiến CL không đáp ứng hoặc mất redundancy nghiêm trọng | `nodetool status`, DC, RF, CL, topology change |
| **Disk free / growth** | Cạn headroom, tốc độ tăng bất thường | Cạn dự báo rất sớm hoặc node không thể ghi/compact | SSTable/snapshot/compaction |
| **Dropped messages / request failure** | Tăng khác baseline, đi kèm latency | Tăng kéo dài và ảnh hưởng availability | Thread pools, saturation, network |
| **Compaction pending tasks** | Hàng đợi tăng liên tục nhiều cửa sổ | Backlog gây áp lực disk/latency nghiêm trọng | Disk IOPS, throughput, TWCS/STCS/LCS |
| **GC pause** | p95/p99 GC pause tăng liên quan tail latency | Pause kéo dài, lỗi request hoặc node unresponsive | Heap, allocation, GC logs |
| **Tombstone scanned** | Tail read tăng ở bảng cụ thể | Query failure/latency SLO do tombstone lớn | Schema, TTL, DELETE, read pattern |
| **Repair overdue** | Không đạt lịch repair đã quy định | Rủi ro tồn tại bản cũ vượt cửa sổ an toàn tombstone | RF, node offline, `gc_grace_seconds` |

**Ngưỡng tuyệt đối cần hiệu chỉnh theo baseline và cấu hình.** Ví dụ hàng đợi compaction có `PendingTasks > 0` trong một thời điểm không tự là sự cố; vấn đề là **tăng kéo dài, không thoát hàng đợi và tạo triệu chứng khác**. Tương tự một lần dropped message có thể không cần page, nhưng tăng theo tải cộng timeout là dấu hiệu quan trọng.

### Theo node và theo data center

Tối thiểu nên phân biệt `cluster`, `datacenter`, `node` và `role` (nếu có). Cảnh báo khi một node lệch nhiều lần so với median node khác trong cùng DC có thể phát hiện “straggler” trước khi trung bình cluster xấu. Tuy nhiên chênh lệch do hardware khác nhau hoặc node đang bootstrap/repair cần được gắn chú thích, không mặc định là lỗi.

## 14. Lệnh kiểm tra thực tế khi cảnh báo xảy ra

Các lệnh sau là **read-only theo mục đích**, thường dùng trong môi trường quản trị Cassandra. Cú pháp và trường output có thể khác theo phiên bản; chạy trên máy có `nodetool`/CQLSH và quyền phù hợp, ưu tiên tài khoản quan sát.

```bash
# Tổng quan trạng thái và phân bố node theo DC/rack.
nodetool status

# Queue/thread pools/dropped messages.
nodetool tpstats

# Các compaction đang chạy và pending.
nodetool compactionstats

# Thống kê bảng (thay tên keyspace/bảng thật).
nodetool tablestats telemetry_ks.readings_by_device_day

# Tình trạng streaming, bootstrap/rebuild nếu liên quan.
nodetool netstats

# Thông tin về trạng thái heap/GC tổng quát nếu phiên bản hỗ trợ.
nodetool gcstats
```

Đối với một query class chậm, kiểm tra schema/truy vấn:

```sql
-- Chỉ đọc theo partition key đã biết.
SELECT event_at, event_id, temperature_c
FROM telemetry_ks.readings_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
LIMIT 100;
```

Nếu dùng CQL tracing hoặc tracing ở driver, **chỉ bật có kiểm soát** cho yêu cầu mẫu vì tracing rộng có overhead. Không ghi toàn bộ partition key nhạy cảm, payload hoặc token vào log/metric.

Khi cluster bất ổn, tránh chạy `nodetool compact`, `flush` hàng loạt, `repair` toàn cluster hoặc quét bảng không giới hạn **chỉ để thu thập tín hiệu**. Những hành động đó có thể tạo thêm I/O và làm tình trạng xấu hơn.

## 15. Java Driver 4.x: đo latency và outcome của logical query

Ví dụ Java dưới đây dùng **Apache/DataStax Cassandra Java Driver 4.x**. Một recorder nhỏ được trừu tượng hóa để có thể tích hợp Micrometer/Prometheus/OpenTelemetry sau này mà không phụ thuộc một thư viện metrics cụ thể.

Trong keyspace thử nghiệm đã được chọn bằng `USE <keyspace>;`, tạo bảng scalar phục vụ truy vấn theo partition key (không chạy trên bảng production đã có dữ liệu):

```sql
CREATE TABLE IF NOT EXISTS device_state_by_id (
    device_id text PRIMARY KEY,
    state text
);
```

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class ObservedDeviceRepository {
    public interface RequestRecorder {
        // Cần xuất counter/histogram theo query class, không theo deviceId.
        void record(String operation, String outcome, double durationSeconds);
    }

    private final CqlSession session;
    private final PreparedStatement select;
    private final RequestRecorder recorder;

    public ObservedDeviceRepository(CqlSession session, RequestRecorder recorder) {
        this.session = session;
        this.recorder = recorder;
        this.select = session.prepare(
            "SELECT state FROM device_state_by_id WHERE device_id = ?"
        );
    }

    public String findState(String deviceId) {
        long started = System.nanoTime();
        String outcome = "failure";
        try {
            Row row = session.execute(select.bind(deviceId)).one();
            // Không có row vẫn là kết quả truy vấn thành công.
            outcome = "success";
            return row == null ? null : row.getString("state");
        } finally {
            double seconds = (System.nanoTime() - started) / 1_000_000_000.0;
            recorder.record("read_by_id", outcome, seconds);
        }
    }
}
```

**Giải thích:**

- `System.nanoTime()` phù hợp đo elapsed duration; không phải epoch timestamp cho Cassandra `USING TIMESTAMP`.
- `row == null` không nhất thiết là lỗi Cassandra; nó có thể là “khóa không có dữ liệu”, tùy hợp đồng nghiệp vụ.
- `finally` ghi metric cả khi `execute` ném exception; exception vẫn được truyền ra cho caller.
- Đoạn mã ghi **một sample mỗi lần gọi `findState`**. Nếu caller retry bằng cách gọi lại method, đó sẽ là nhiều samples; để đúng logical-operation SLI, cần đặt instrumentation **ngoài vòng retry ứng dụng** hoặc dùng một request context chia sẻ.
- Nếu `recorder.record(...)` có thể ném exception, nên thiết kế recorder không làm hỏng business request; trong production cần thử lỗi của pipeline telemetry.

Đây là ví dụ ngắn để hiểu instrumentation; không bao gồm thư viện export metrics, trace context, async execution, timeout và phân loại exception. Khi triển khai thật, cần quản lý các thành phần này để tránh **double-count** request.

## 16. Case study: p99 tăng nhưng availability chưa xấu

Giả sử baseline `read_by_id` là p99 110 ms ở 1.500 req/s, nhưng dashboard mới cho thấy p99 tăng lên 400 ms trong 20 phút. Availability vẫn 99,98%. Điều này **không tự chứng minh** cluster đang down, nhưng có thể đe dọa latency SLO.

Một chuỗi kiểm tra hợp lý:

1. **Xác định tác động:** latency SLI “% ≤ 250 ms” giảm còn bao nhiêu, số request bị chậm là bao nhiêu?
2. **Xác định phạm vi:** tất cả query class hay chỉ một bảng; một DC hay cả hai; một node hay toàn cluster?
3. **So sánh tải:** request/s, payload/row size, concurrency, deploy mới, đợt backfill hay retry storm.
4. **Phân tích Cassandra:** p99 server read, pending tasks, GC pause, disk read latency, tombstone scanned, SSTable count, compaction backlog.
5. **Kiểm tra query:** partition key có đủ không, có hotspot hoặc truy vấn rộng trong partition không, client có đổi CL không?
6. **Khoanh vùng nguyên nhân:** nếu app latency tăng nhưng server latency không tăng, xem driver pool, network, application queue/retry trước khi chỉnh compaction.

Ví dụ phân tích (số **giả định**):

| Tín hiệu | Trước | Trong sự cố | Giả thuyết |
|---|---:|---:|---|
| App p99 read | 110 ms | 400 ms | Tail latency tăng |
| Server read p99 | 85 ms | 350 ms | Thời gian ở server cũng tăng |
| Compaction pending | 2–5 | 900 và tăng | Backlog nghiêm trọng |
| Disk read p99 | 5 ms | 70 ms | Disk có thể bão hòa |
| Read failures | 0,02% | 0,02% | Availability chưa suy giảm |
| Latency SLI ≤ 250 ms | 99,6% | 96,5% | Vi phạm SLO 99% |

Kết luận **đúng mức chứng cứ** là “compaction/disk có tương quan với tail latency, cần điều tra nguyên nhân I/O”, **không** phải “chắc chắn compaction là thủ phạm” nếu chưa xem timeline và workload.

## 17. Case study: availability đột ngột giảm khi mất node

Giả sử cluster `RF = 3`, ứng dụng ghi/đọc ở `LOCAL_QUORUM` trong một DC. Khi mất một node, hệ thống có thể còn đáp ứng quorum cho nhiều partition nếu hai replica còn lại sẵn sàng, nhưng **khả năng chịu thêm lỗi giảm**. Nếu thêm replica không khả dụng hoặc mạng phân vùng, timeout/unavailable có thể tăng nhanh.

Checklist đầu tiên:

- Có bao nhiêu node down **trong DC nào**, và replication strategy/RF thực tế cho keyspace ra sao?
- Request lỗi là **read** hay **write**; CL là `ONE`, `LOCAL_QUORUM` hay `ALL`?
- Có hạ tầng mạng, disk hoặc GC khiến node “up” nhưng không trả lời kịp không?
- Client có retry quá nhiều, tạo tải dồn lên các replica còn lại không?
- Hints, pending repair và compaction backlog có tăng sau khi node quay lại không?

**Không vội giảm CL để “khôi phục SLO”** nếu điều đó phá yêu cầu consistency của nghiệp vụ. Quyết định failover/điều chỉnh CL phải dựa vào hợp đồng dữ liệu và runbook đã được phê duyệt. Tương tự, “node up” chưa đồng nghĩa “mọi replica đã hội tụ” sau một sự cố dài.

## 18. Thiết lập baseline và kiểm thử cảnh báo trên môi trường thử nghiệm

Không tạo sự cố bằng cách tắt node production hoặc ép compaction trên cluster đang phục vụ người dùng. Một quy trình lab:

### Bước A — Chuẩn bị môi trường

1. Dùng cluster staging có topology, RF, CL và bản Cassandra tương đồng hoặc ghi rõ khác biệt.
2. Tạo bảng theo truy vấn đơn giản; nạp dữ liệu đại diện kích thước row/partition thực tế.
3. Kết nối Java Driver và hệ thống metrics ở app, Cassandra JMX exporter, JVM/OS collector.
4. Bảo đảm label, đơn vị, histogram bucket và clock của hệ thống monitoring đúng.

### Bước B — Thu baseline có kiểm soát

Tạo các mức tải tăng dần (ví dụ 25%, 50%, 75%, 100% tải dự kiến). Mỗi mức đủ thời gian để thấy latency/queue ổn định; không dùng thời gian đo quá ngắn làm “baseline”.

Ghi lại theo từng mức:

| Tải mục tiêu | Throughput thực | Error rate | p95/p99 client | CPU/disk latency | Compaction pending |
|---|---|---|---|---|---|
| 25% | Đo, không giả định | Đo | Đo | Đo | Đo |
| 50% | Đo | Đo | Đo | Đo | Đo |
| 75% | Đo | Đo | Đo | Đo | Đo |
| 100% | Đo | Đo | Đo | Đo | Đo |

Chú ý **coordinated omission** trong load test: nếu tool ngừng phát request khi server chậm, latency đo có thể đẹp giả. Nên xác định load model và đo thời gian chờ/timeout cả ở client.

### Bước C — Thử cảnh báo

Trong staging, gây lỗi **có kiểm soát** như tăng latency của một dependency giả lập hoặc giảm traffic thành công trong bộ sinh metric để thử:

- Fast-burn alert kích hoạt khi error ratio vượt ngưỡng ở **cả cửa sổ dài và ngắn**.
- Cảnh báo không page khi traffic thấp hơn minimum-volume gate, nhưng vẫn có synthetic probe/tín hiệu riêng.
- Cảnh báo latency SLI kích hoạt khi tỷ lệ request ≤ ngưỡng giảm; không chỉ trông vào p99.
- Runbook, dashboard và người trực có thông tin đủ để xác định DC/query class/node bị ảnh hưởng.
- Sau khi phục hồi, alert tự đóng và không flapping liên tục.

**Test một cảnh báo không chỉ là test biểu thức PromQL.** Phải xác thực luồng notification, dedup/grouping, escalation, thời gian phát hiện và hướng xử lý.

## 19. Runbook ứng cứu: từ cảnh báo đến hành động an toàn

Một runbook ngắn nhưng có tác dụng nên giúp on-call trả lời:

1. **Tác động:** SLI nào đang vi phạm? Error budget burn bao nhiêu? Bao nhiêu request/minute và dịch vụ bị ảnh hưởng?
2. **Phạm vi:** Query class nào, data center nào, node nào, từ lúc nào? Có liên quan deploy hoặc schema change không?
3. **Hiện trạng cluster:** node up/down, CL/RF, pending tasks, timeouts, compaction, disk/GC, network.
4. **Hành động ít rủi ro trước:** dừng backfill/analytics không bắt buộc, kiểm soát retry storm, rollback deployment gây tăng tải, cô lập một query xấu theo quy trình.
5. **Không thao tác phá hoại:** không giảm `gc_grace_seconds`, không xóa SSTable thủ công, không ép compaction/repair toàn cluster khi chưa đánh giá tác động, không hạ CL tùy tiện.
6. **Xác nhận phục hồi:** availability và latency SLI trở lại bình thường theo nhiều cửa sổ, queue giảm, disk/GC ổn định, repair/topology đã có kế hoạch nếu cần.
7. **Hậu kiểm:** timeline, nguyên nhân, budget đã tiêu, thay đổi ngưỡng, action owner và cách ngăn tái diễn.

### Một mẫu alert có thể hành động

```text
Alert: CassandraReadFastBurn
Severity: page
Service: device-api
Query class: read_by_id
Consistency: LOCAL_QUORUM
SLO: 99.95% availability over 30d
Current: error ratio vượt fast-burn ở 1h và 5m
First checks: dashboard read errors, driver timeouts,
  nodetool status/tpstats, disk/GC, recent deploy
Runbook: internal link do đội vận hành quản lý
```

Đừng đưa **raw query parameters**, partition keys nhạy cảm, token hay thông tin xác thực vào alert. Các liên kết runbook và dashboard cần được triển khai thật trong hệ thống nội bộ; dòng trên là ví dụ định dạng.

## 20. Các sai lầm thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
|---|---|---|
| Chỉ nhìn **CPU** hoặc node status | Bỏ lỡ tail latency và lỗi driver | Dùng SLI end-to-end + server diagnostics |
| Lấy **average latency** làm toàn bộ SLO | Che long tail | Dùng % dưới deadline và percentiles phụ trợ |
| Lấy trung bình **p99 các node** | Số tổng hợp không đại diện phân bố thật | Aggregate histogram từ samples/buckets đúng |
| Gộp read point lookup với LWT/range scan | Baseline/SLO không công bằng | Tách query class và CL |
| Đếm **mỗi retry attempt** như một request độc lập | Error ratio/traffic bị phóng đại hoặc lệch | Tính SLI ở logical-operation boundary |
| Dùng partition key làm Prometheus label | Cardinality tăng mạnh, monitoring quá tải | Dùng labels hữu hạn và exemplar/trace ID riêng |
| Page cho mọi spike một phút | Alert fatigue | Multi-window burn, volume gate, `for` |
| Ngưỡng disk cứng không xét tốc độ tăng | Cảnh báo quá sớm hoặc quá muộn | Forecast + compaction/snapshot headroom |
| Chỉ nhìn trung bình cluster | Che node/DC bất thường | Per-node/zone dashboards và alert tương quan |
| Để baseline tự cập nhật giữa sự cố | Xem sự cố kéo dài như “bình thường” | Khóa baseline theo kỳ khỏe mạnh, review thay đổi |
| Thay CL khi timeout mà không xét semantics | Có thể vi phạm consistency | Quy trình dựa trên RF/CL và yêu cầu nghiệp vụ |
| SLO không có owner/runbook | Page không tạo hành động | Gắn SLO với nhóm phụ trách và quy trình ứng cứu |

## 21. Câu hỏi tự kiểm tra và đáp án

**Câu 1.** Baseline cho read p99 120 ms, nhưng SLO latency là 99% ≤ 250 ms trong 30 ngày. Nếu p99 của **5 phút gần nhất** lên 180 ms thì đã vi phạm SLO tháng chưa?

**Đáp án:** **Chưa thể kết luận về SLO 30 ngày chỉ từ p99 trong 5 phút.** Cần đo **tỷ lệ logical read thành công ≤ 250 ms** trên toàn cửa sổ SLO. Nếu p99 được tính chính xác trên cùng tập sample và cùng cửa sổ, p99 = 180 ms thấp hơn 250 ms thực sự cho thấy ít nhất khoảng 99% sample trong cửa sổ đó đạt ngưỡng; nhưng đó **không phải** kết luận cho cả tháng.

**Câu 2.** Một ứng dụng thực hiện 1.000.000 logical reads/tháng, SLO availability 99,95%. Khoảng bao nhiêu request lỗi là hết budget?

**Đáp án:** Khoảng **500 request**, nếu mẫu số đúng 1.000.000 và tất cả đều là eligible requests.

**Câu 3.** Với SLO availability 99,95%, error ratio 0,72% tương ứng burn rate bao nhiêu?

**Đáp án:** `0.0072 / 0.0005 = 14.4`.

**Câu 4.** Tại sao không lấy trung bình p99 của ba node để báo p99 cluster?

**Đáp án:** Percentiles là đặc tính của **phân bố**, không cộng/trung bình tuyến tính. Cần histogram/quan sát toàn bộ mẫu phù hợp.

**Câu 5.** Dịch vụ có read point lookup, range scan và LWT. Có nên dùng cùng một ngưỡng latency p99 cho cả ba?

**Đáp án:** **Không nên mặc định.** Chúng có chi phí/semantics khác nhau; định nghĩa SLI/SLO theo query class và nhu cầu người dùng.

**Câu 6.** Có nên page nếu một node CPU lên 80% trong 30 giây nhưng application SLI bình thường?

**Đáp án:** Thường **không chỉ từ CPU**. Cần xem tải bình thường, saturation khác, xu hướng và ảnh hưởng SLI; có thể chỉ cần dashboard hoặc ticket.

**Câu 7.** Một request timeout ở client nhưng một replica đã ghi thành công. Nó nên được tính là success availability SLI cho ứng dụng không?

**Đáp án:** Nếu **logical request không được xác nhận thành công trong deadline** theo hợp đồng ứng dụng, nó là **failure** ở SLI phía client, dù có replica đã nhận mutation. Cần reconcile trạng thái dữ liệu riêng.

**Câu 8.** Tại sao ngưỡng disk dưới 10% không thể áp dụng như chuẩn an toàn chung cho mọi cluster?

**Đáp án:** Cần tính **compaction temporary space, streaming/repair, snapshots, tốc độ tăng dữ liệu, cấu hình và topology**. 10% chỉ là số ví dụ, có thể đã quá muộn.

**Câu 9.** Alert ở server ClientRequest latency bình thường nhưng duration từ Java Driver tăng mạnh. Nên kiểm tra gì?

**Đáp án:** Driver pool/queue, retries, DNS/network, coordinator routing, application thread pool và sự khác nhau giữa phạm vi đo trước khi kết luận Cassandra node là nguyên nhân.

**Câu 10.** Vì sao `histogram_quantile` từ bucket 0,1 và 0,5 giây không cho tỷ lệ chính xác request ≤ 0,25 giây?

**Đáp án:** Không có bucket `le="0.25"`, nên không biết bao nhiêu mẫu nằm giữa 0,1 và 0,25. Muốn SLI dựa trên ngưỡng 250 ms, nên thiết kế bucket phù hợp từ đầu.

**Câu 11.** Khi `nodetool compactionstats` cho thấy pending tasks tăng liên tục, có nên chạy ép compact ngay không?

**Đáp án:** **Không.** Cần xem disk I/O, tác động SLI, nguyên nhân tải, compaction strategy và headroom trước khi có hành động. Ép compaction có thể làm quá tải thêm.

**Câu 12.** Vì sao một cluster RF 3/CL QUORUM không tự bảo đảm sự kiện đến muộn không làm lùi trạng thái?

**Đáp án:** CL ràng buộc số replica trả lời, còn Cassandra hòa giải phiên bản theo **mutation timestamp**. Thứ tự nghiệp vụ cần version/CAS hoặc cơ chế điều phối thích hợp.

---

**Ghi nhớ:** Với Cassandra, hãy đo **baseline theo workload, CL, topology và thời điểm**, định nghĩa **SLI có tử số/mẫu số**, chọn **SLO phản ánh nhu cầu người dùng**, rồi dùng **error-budget burn và tín hiệu saturation** để đặt cảnh báo **có thể hành động**. Quan sát đồng thời **Java Driver, Cassandra JMX, JVM/OS và replication/compaction/repair**; không đánh đồng các metric server với trải nghiệm người dùng. Một cảnh báo tốt luôn có ngữ cảnh, owner, runbook và cách xác nhận phục hồi.
