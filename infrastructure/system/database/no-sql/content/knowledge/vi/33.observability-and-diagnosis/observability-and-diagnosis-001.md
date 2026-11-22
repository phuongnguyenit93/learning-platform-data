# Thiết lập mức hiệu năng cơ sở và ngưỡng cảnh báo có ý nghĩa

Một hệ NoSQL có thể xử lý hàng nghìn truy vấn mỗi giây mà vẫn khỏe, nhưng cũng có thể bị timeout với tải thấp nếu một partition trở nên quá nóng, replica tụt xa, connection pool hết chỗ hoặc compaction không theo kịp. CPU ở mức 85% không tự chứng minh sự cố, và CPU 35% không tự chứng minh mọi thứ bình thường. Vì vậy, các quy tắc kiểu “CPU trên 80% thì báo động” hoặc “query chậm hơn 100 ms thì báo động” dễ tạo cảnh báo nhiễu và bỏ lỡ lỗi thật.

**Mức hiệu năng cơ sở (performance baseline)** mô tả phân bố số đo bình thường của một hệ ở **workload, thời điểm, dữ liệu và cấu hình cụ thể**. **Ngưỡng cảnh báo có ý nghĩa** chỉ ra khi nào một số đo cho thấy người dùng bị ảnh hưởng, dịch vụ có nguy cơ vi phạm SLO, hoặc tài nguyên sắp cạn đến mức cần một hành động rõ ràng.

Trong chương **Quan sát và chẩn đoán** của module **Database No SQL**, bài học này hướng dẫn thiết lập baseline cho throughput, p50/p95/p99, error rate, capacity, replication và CDC; thiết kế SLIs/SLOs, error budget burn-rate alerts, cảnh báo động và chống flapping; theo dõi tín hiệu riêng của MongoDB, Cassandra, DynamoDB, Redis, search engine; instrument ứng dụng Java bằng Micrometer; thiết kế dashboard, runbook và bài kiểm thử cảnh báo.

> **Nguyên tắc:** Baseline trả lời “hệ hoạt động như thế nào khi bình thường trong bối cảnh này?”, còn alert hữu ích phải trả lời thêm “điều gì đang bị đe dọa, nghiêm trọng đến đâu, và ai có thể làm gì ngay?”.

## 1. Vì sao một con số cố định dễ sai?

Giả sử một API đọc listing có kết quả:

| Giai đoạn | Requests/s | p95 | Error rate |
| --- | ---: | ---: | ---: |
| Ngày thường | 500 | 28 ms | 0,02% |
| Tối cuối tuần | 2.000 | 45 ms | 0,03% |
| Incident | 300 | 430 ms | 3,2% |

Một alert `p95 > 40ms` sẽ nổ vào tối cuối tuần dù có thể dịch vụ vẫn đáp ứng trải nghiệm mong đợi. Nếu chỉ theo throughput cao, incident ở dòng thứ ba lại không được phát hiện.

Phải phân biệt:

- **Anomaly:** số đo lệch baseline.
- **SLO violation:** người dùng không nhận chất lượng đã đặt mục tiêu.
- **Capacity risk:** tài nguyên gần giới hạn nên có thể sớm tạo SLO violation.

Một anomaly chưa chắc cần page, còn vi phạm SLO không thể bị bỏ qua chỉ vì vẫn giống baseline.

## 2. Baseline là phân bố có bối cảnh

Một baseline ví dụ:

~~~text
service: listing-api
operation: getListingById
region: A
traffic class: interactive reads
observation: weekday and weekend cycles

requests/s: median 500, peak 2,000
latency: p50 12ms, p95 35ms, p99 80ms
bad-request rate: 0.02%
driver pool wait p99: 6ms
cache hit rate: 91%
~~~

Mọi giá trị trong ví dụ này đều **giả định để học**, không phải ngưỡng sản xuất có thể sao chép.

Đi kèm phải có phiên bản DB/driver, số node, schema/index, kích thước dữ liệu, query mix, cache state, consistency level và thời điểm đo. Không so một benchmark với bộ dữ liệu nhỏ ở staging cùng p95 của production rồi mặc định chúng tương đương.

## 3. SLI, SLO, SLA và error budget

| Khái niệm | Ý nghĩa |
| --- | --- |
| Metric | Số đo vận hành theo thời gian |
| SLI | Chỉ số đo chất lượng dịch vụ |
| SLO | Mục tiêu cho SLI trong một cửa sổ |
| SLA | Cam kết dịch vụ có thể kèm điều khoản trách nhiệm |
| Baseline | Hành vi nền trong bối cảnh xác định |
| Error budget | Tỷ lệ sai hỏng được phép theo SLO |
| Burn rate | Tốc độ tiêu error budget |
| Alert | Điều kiện phát hiện và phân phối một vấn đề cần hành động |
| Runbook | Quy trình điều tra/giảm thiểu/khôi phục |

CPU là metric chẩn đoán hữu ích, nhưng không tự là SLI trải nghiệm người dùng. Một SLI nên đo kết quả người dùng quan tâm: request trả đúng, đủ nhanh, có độ mới dữ liệu phù hợp.

## 4. Phân tầng workload trước khi đo

Trong một cluster có thể tồn tại:

~~~text
getListingById            → point lookup
searchListings            → range/filter/full-text
reserveInventory          → conditional update
exportMonthlyTransactions → long scan
processChangeStream       → CDC consumer
~~~

Nếu gộp các operation vào một histogram, nhiều point lookups nhanh có thể che booking transaction chậm.

| Chiều phân tầng | Ví dụ |
| --- | --- |
| Operation | get, search, reserve, export |
| Read/write | Point read, write, bulk |
| Query shape | Indexed lookup, scan, aggregation |
| Traffic class | User interactive, batch job |
| Region | Local/cross-region |
| Data size | Small/large partition |
| Tenant class | Regular/heavy |
| Cache state | Hit, miss, warm-up |
| Consistency | Eventual/stronger mode |

Không dùng từng `userId`, `reservationId` hay raw query làm labels cho metrics vì cardinality có thể bùng nổ. Với entity cụ thể, dùng logs/traces có kiểm soát.

## 5. Đường đo từ người dùng tới storage engine

~~~text
Web/Mobile
     |
API Gateway
     |
Java Service -- queue/serialization/retries
     |
NoSQL Driver -- pool wait/network
     |
Coordinator/Router -- partition/replica routing
     |
Storage Engine -- index/disk/compaction
~~~

Một request mất 500 ms dù DB server execution chỉ 25 ms nếu pool wait, backoff và network chiếm phần lớn.

**End-to-end latency** là ứng viên tốt cho SLI. **Driver latency, server execution, queue và disk metrics** hỗ trợ xác định nguyên nhân. Không thay latency người dùng thấy bằng thời gian một query chạy bên trong DB.

## 6. RED và USE

**RED** cho request/service:

- **Rate:** lượng operation/giây.
- **Errors:** số/tỷ lệ thất bại.
- **Duration:** phân bố latency.

**USE** cho tài nguyên:

- **Utilization:** CPU, disk, RAM, network, connections.
- **Saturation:** queue, pool wait, throttling, rejected requests.
- **Errors:** lỗi ở tầng tài nguyên.

~~~text
Booking p99 ↑ và error rate ↑
          |
          +→ Driver pool wait ↑
          +→ Hot partition throttling ↑
          +→ Disk latency ↑
          +→ Compaction backlog ↑
~~~

RED cho biết **người dùng bị ảnh hưởng**; USE giúp giải thích **vì sao**.

## 7. Xây SLI availability đúng ngữ nghĩa

\[
SLI_{\text{availability}}=
\frac{\text{good eligible requests}}
{\text{all eligible requests}}
\]

Cần định nghĩa:

1. Request nào đủ điều kiện vào mẫu số?
2. HTTP 400 do client nhập sai có tính bad không?
3. Booking bị từ chối vì hết chỗ có thể là business outcome hợp lệ.
4. Timeout từ DB có tính bad không?
5. HTTP 200 nhưng dữ liệu sai có tính good không?
6. SDK retry nhiều lần có tính thành nhiều user requests không?

**Business invariant** như không double-booking cần kiểm và báo lỗi riêng. Một vi phạm correctness nghiêm trọng không thể được hợp thức hóa bằng availability error budget.

## 8. Xây SLI latency

Ví dụ một SLO:

> 99% lượt đọc listing hợp lệ trả kết quả đúng trong 250 ms, đo theo rolling 30 ngày.

\[
GoodLatencyFraction=
\frac{\text{eligible requests thành công trong 250ms}}
{\text{all eligible requests}}
\]

Giá trị 250 ms là **minh họa**. Product có yêu cầu khác có thể cần 100 ms hay 800 ms. Cần phân biệt tỷ lệ good requests của 30 ngày với một p99 đo trên 5 phút; chúng không mặc nhiên tương đương về cửa sổ và cách tổng hợp.

## 9. Error budget

SLO 99,9% good requests:

\[
AllowedBadFraction=1-0.999=0.001=0.1\%
\]

Nếu có 10 triệu requests đủ điều kiện:

\[
10{,}000{,}000\times0.001=10{,}000
\]

Khoảng 10.000 bad requests tương ứng toàn bộ budget của ví dụ.

Không chọn SLO chỉ vì hệ hiện tại dễ đạt. SLO phải phản ánh nhu cầu người dùng và độ tin cậy cần thiết, rồi mới đo khoảng cách giữa baseline và mục tiêu.

## 10. Error budget burn rate

Với allowed bad fraction 0,1%, nếu bad fraction hiện tại 1,44%:

\[
BurnRate=\frac{0.0144}{0.001}=14.4
\]

Trong 30 ngày có xấp xỉ 720 giờ. Nếu burn rate 14,4 duy trì một giờ với assumptions phù hợp:

\[
14.4\times\frac{1}{720}=2\%
\]

Tức khoảng 2% budget 30 ngày.

Một cấu hình **multi-window** tham khảo:

| Alert | Long window | Short window | Burn rate |
| --- | --- | --- | --- |
| Fast burn | 1 giờ | 5 phút | Cả hai >14,4 |
| Sustained burn | 6 giờ | 30 phút | Cả hai >6 |
| Slow burn | 24 giờ | 2 giờ | Chọn theo policy |

Short window phát hiện và reset nhanh; long window giảm noise. Các số này **không phải giá trị mặc định bắt buộc**, cần điều chỉnh theo SLO, traffic, mức khẩn cấp và cơ cấu on-call.

## 11. Percentile p50, p95, p99

| Metric | Công dụng |
| --- | --- |
| Mean | Trung bình; dễ che tail |
| p50 | Trải nghiệm trung vị |
| p95 | Nhóm requests chậm hơn thông thường |
| p99 | Tail latency |
| Maximum | Giá trị cực trị, dễ nhiễu |

Nếu một vài requests rất chậm nhưng đa số nhanh, mean có thể vẫn đẹp. Vì vậy dùng **phân bố**, không chỉ average.

### Những bẫy

- p99 của một tập 20 requests thiếu ổn định.
- Không lấy trung bình p99 của các nodes để tạo global p99.
- Histogram quantiles có sai số xấp xỉ theo bucket.
- Request timeout cần được tính trong SLI/errors và không âm thầm biến mất khỏi latency instrumentation.

## 12. Histogram và PromQL

Một classic histogram:

~~~text
nosql_operation_seconds_bucket{operation="getListing",le="0.05"}
nosql_operation_seconds_bucket{operation="getListing",le="0.10"}
nosql_operation_seconds_bucket{operation="getListing",le="0.25"}
nosql_operation_seconds_bucket{operation="getListing",le="+Inf"}
~~~

PromQL tính p99 theo operation:

~~~promql
histogram_quantile(
  0.99,
  sum by (le, operation) (
    rate(nosql_operation_seconds_bucket[5m])
  )
)
~~~

Đây là mẫu cho classic histogram; với native histograms hoặc metric names khác phải thay truy vấn phù hợp. Buckets nên bao phủ các latency/SLO boundaries quan trọng.

**Sai:** lấy trung bình p99 của server A và B khi traffic rất khác nhau. **Đúng hơn:** tổng hợp histogram observations rồi tính quantile toàn tập.

## 13. Đo cả thành công và thất bại

Nếu timer chỉ ghi sau khi query trả thành công:

~~~java
long start = System.nanoTime();
Result result = database.query();
timer.record(System.nanoTime() - start);
return result;
~~~

Thì lỗi/timeout làm method ném exception trước khi record. p99 có thể trông **nhanh hơn đúng lúc hệ bị lỗi nặng**.

Đo trong `finally` và tăng error counter phân loại. Phân biệt:

- **Logical request latency:** từ lúc user request tới lúc kết thúc.
- **Driver attempt latency:** một lần gọi DB, có thể retry.
- **Retry/backoff count/duration:** giải thích vì sao tổng request chậm.

Một request retry thành công không nên được coi là ba user requests nếu nó thực chất chỉ là một yêu cầu từ client.

## 14. Benchmark và coordinated omission

Một load generator chỉ gửi request tiếp theo **sau khi request trước hoàn thành** có thể làm số request đến giảm khi server chậm. Điều đó khiến tail latency dưới tải cố định được đánh giá quá lạc quan.

Khi muốn kiểm hiệu năng với arrival rate định trước, cần hiểu open-loop/closed-loop load generation và coordinated omission. Một vòng lặp tuần tự 1.000 requests không chứng minh hệ chịu được 1.000 concurrent requests.

## 15. Lập baseline đủ chu kỳ thời gian

Không lấy một ngày yên tĩnh để đại diện:

- Peak theo giờ và cuối tuần.
- Promotion/campaign.
- Import/backup/repair.
- Scheduled compaction.
- Cache cold starts.
- Autoscaling/failover.
- Dataset tăng trưởng.

Với hệ có chu kỳ tuần, thường cần đo nhiều chu kỳ tuần đại diện; nếu có chu kỳ tháng, cần thêm dữ liệu tương ứng. Không có số tuần cố định đúng cho mọi deployment.

### Metadata không được thiếu

~~~text
Period and sample interval
Workload/query shape
Traffic volume and concurrency
DB/schema/index version
Node class and cluster size
Region and consistency mode
Cache hit/miss state
Known incidents and maintenance windows
~~~

Không tự xóa mọi điểm xấu để baseline đẹp. Gắn nhãn incidents và phân biệt mức nền hiện tại với **mục tiêu phải cải thiện**.

## 16. Seasonality và baseline có điều kiện

~~~text
02:00–06:00: 100 requests/s
09:00–17:00: 700 requests/s
20:00–23:00: 2,500 requests/s
Sunday peak: 4,000 requests/s
~~~

Một threshold QPS tĩnh sẽ báo “tăng đột biến” nhiều lần vào peak hợp lệ.

\[
ExpectedMetric=f(hourOfWeek,trafficBucket,operation,region)
\]

Có thể so p95 của Thứ Bảy 20:00 với các Thứ Bảy 20:00 trước đó, hoặc trong cùng bucket 2.000–4.000 requests/s.

Không vội “học” một incident hoặc traffic spike chưa có tính lặp như một mùa vụ bình thường.

## 17. Skew, hot partitions và tenant

~~~text
Tenant A: 500 req/s across 100 partitions.
Tenant B: 200 req/s on one partition.
~~~

Tổng tải thấp hơn nhưng Tenant B có thể bị throttling nặng.

Đo per-partition/per-shard load nếu DB hỗ trợ, top-K hot keys, heavy tenants và query fan-out. Dùng sampling/traces khi không thể tạo hàng triệu metric series; **không đưa userId vào Prometheus label cho từng người dùng**.

## 18. Static, relative và dynamic thresholds

| Kiểu ngưỡng | Ví dụ | Khi phù hợp |
| --- | --- | --- |
| Hard/SLO | Good request ratio vi phạm SLO | User impact |
| Static capacity | Disk free gần vùng nguy hiểm | Ranh giới kỹ thuật |
| Relative | p95 gấp 2 baseline cùng cohort | Regression |
| Seasonal | QPS thấp hơn dự kiến theo giờ | Traffic có chu kỳ |
| Forecast | Disk sẽ đầy trong 3 ngày | Chủ động scale |
| Composite | Latency + throttling cùng tăng | Chẩn đoán và giảm nhiễu |

Ví dụ warning:

~~~text
p95 > max(2 × expected_p95, 120ms)
for 15 minutes
AND traffic > 50 requests/s
~~~

Toàn bộ ngưỡng trên **chỉ minh họa**. Nếu SLO yêu cầu 100 ms, không được dùng floor 120 ms để bỏ qua vi phạm. SLO burn alert vẫn phải độc lập.

## 19. Phương pháp robust median/MAD

Giả sử baseline p95 cùng workload ở bảy thời điểm:

~~~text
90, 94, 97, 100, 105, 108, 145 (ms)
~~~

Median = 100 ms. Các sai khác tuyệt đối:

~~~text
10, 6, 3, 0, 5, 8, 45
~~~

MAD = median của tập trên = 6 ms.

\[
z_{\text{robust}}\approx
\frac{|x-\operatorname{median}(x)|}
{1.4826\times MAD}
\]

Nếu MAD=0 hoặc sample quá ít, phải có fallback. Một giá trị anomalous chưa chắc user bị ảnh hưởng; cần xem SLO và hành động. Nếu baseline p95 vốn là 600ms khi SLO 250ms, **không được nâng ngưỡng lên 900ms chỉ vì hệ đã chậm lâu ngày**.

## 20. Duration và hysteresis

Khi latency dao động:

~~~text
100, 152, 99, 155, 101, 150 ms
threshold = 150ms
~~~

Alert ngay mỗi điểm vượt threshold sẽ flapping.

Cân nhắc:

- `for: 10m` hoặc cửa sổ phù hợp.
- Rolling metrics.
- Hysteresis: mở >150ms, đóng khi <120ms đủ lâu.
- Traffic/sample floor.
- Severity phân theo ảnh hưởng.

Không trì hoãn quá lâu những lỗi nghiêm trọng như data loss/double-booking chỉ để giảm nhiễu.

## 21. Phân cấp page, ticket và dashboard

~~~text
PAGE:
  User-facing SLO fast burn,
  critical correctness/durability failure,
  imminent resource exhaustion.

TICKET:
  Query regression, compaction backlog trend,
  mild replica lag, capacity planning.

DASHBOARD:
  Expected CPU peak, normal TTL expirations,
  planned background processing.
~~~

Một alert chỉ có “CPU 80%” nhưng không nêu hành động, scope hay impact thường không đủ lý do để page.

Ngược lại, resource alert có thể đáng page **trước khi user bị ảnh hưởng** nếu mất quorum/disk đầy sắp xảy ra và thời gian khắc phục ngắn.

## 22. NoData là trạng thái riêng

Exporter ngừng scrape có thể khiến error rate alert im lặng:

~~~text
No request series.
No error series.
~~~

Phải phân biệt **không có traffic thật**, **telemetry pipeline hỏng** và **service down**.

Dùng:

- Target `up`/heartbeat.
- Black-box synthetic probe.
- Expected scheduled job completion.
- NoData/missing series detection.
- Chính sách cho denominator bằng 0 hoặc NaN.

Một dashboard trống không chứng minh service đạt latency 0 ms.

## 23. Saturation và Little's law

Trong hệ tương đối ổn định:

\[
L=\lambda W
\]

Với `L` là số work trung bình trong hệ, `λ` là throughput và `W` là thời gian trong hệ. Ví dụ 1.000 requests/s × 0,1s ≈ 100 requests in-flight.

Khi bão hòa, queue depth, pool wait, timeouts, throttling và p99 thường tăng trong khi throughput không còn tăng theo arrival rate. Không chỉ xem CPU, vì một hot partition hoặc một storage node có thể là bottleneck.

## 24. Tìm điểm uốn của capacity

Một load test minh họa:

~~~text
100 req/s   → p95 20ms
400 req/s   → p95 25ms
800 req/s   → p95 40ms
1100 req/s  → p95 90ms
1200 req/s  → p95 220ms + throttling
~~~

Điểm uốn gần 1.100–1.200 req/s của **cấu hình và workload thử nghiệm** có thể dùng để cảnh báo forecast peak đang tiến vào vùng rủi ro.

Phải kiểm read/write mix, payload size, key skew, consistency mode, cache hit ratio và background compaction. Không biến một benchmark thành “hard capacity” cho mọi tình huống.

## 25. MongoDB: metrics nên đo

| Nhóm | Tín hiệu |
| --- | --- |
| API/driver | Operation p95/p99, timeout, pool wait |
| Query plan | Documents examined, keys examined, returned |
| Query efficiency | Examined/returned ratio |
| Storage | Disk latency, cache pressure |
| Replication | Secondary lag/failover health |
| Concurrency | Lock/queue contention |
| Sharding | Per-shard load/hot shard |
| Diagnostics | Slow query, explain, profiler samples |

Ví dụ:

~~~text
Normal:   p99=40ms, pool wait=5ms, examined/returned=1.2
Incident: p99=800ms, pool wait=300ms, examined/returned=1.2
~~~

Query plan không thay đổi nhiều nhưng pool wait tăng. Hãy xem connection pool saturation, concurrency và network trước khi thêm index.

Profiler/logging có thể tạo overhead; sampling và retention phải hợp lý.

## 26. Cassandra: compaction và partition quan trọng

| Tín hiệu | Mục đích |
| --- | --- |
| Coordinator read/write latency | Chất lượng request |
| Timeouts/unavailable | Client errors |
| Pending compactions | Backlog và read/write amplification |
| Tombstones scanned | Query tốn tài nguyên |
| SSTable count | Read amplification |
| Memtable flush tasks | Write path pressure |
| Dropped messages/queues | Saturation |
| Node GC/heap | Pauses |
| Disk latency/free space | Headroom |
| Repair/replica state | Durability/consistency maintenance |
| Hot partitions/nodes | Skew |

Ví dụ nodes có CPU 95%, 30%, 28%: average khoảng 51% che một node có thể đang timeout nghiêm trọng. Cần per-node/per-partition metrics, không chỉ cluster average.

Tăng timeout có thể che lỗi bề mặt nhưng làm in-flight work tăng; phải tìm bottleneck như tombstones, compaction hoặc disk.

## 27. DynamoDB: consumed capacity và throttling

Quan sát:

- Logical SDK request latency.
- Throttling reasons/events.
- Consumed RCU/WCU và capacity mode.
- Provisioned/autoscaling state nếu áp dụng.
- Hot partition/key skew.
- Query vs Scan workload.
- Evaluated/returned items và filter cost.
- Retry attempts/backoff.
- ConditionalCheckFailed theo business contract.
- DynamoDB Streams consumer lag.

Ví dụ:

~~~text
Table consumed WCU = 2,100/s (bình thường)
Một hot partition = 8% writes bị throttle
~~~

Alert “table WCU usage >80%” có thể không nhận ra vấn đề. Chế độ on-demand và provisioned có semantics capacity khác nhau.

`ConditionalCheckFailed` có thể là kết quả tranh chấp inventory hợp lệ, không mặc định phải tính là system error.

## 28. Redis: hit rate, eviction và freshness

| Signal | Ý nghĩa |
| --- | --- |
| Cache hit/miss ratio | Hiệu quả |
| Evictions vs expirations | Memory pressure khác TTL |
| Used memory/fragmentation | Headroom |
| Command latency/slow log | Performance |
| Blocked clients/connections | Contention |
| Hot keys | Skew |
| DB fallback QPS | Tác động cache miss tới nguồn |
| Replica lag/failover | Khả dụng |
| Stale version samples | Correctness/freshness |

Hit ratio giảm từ 95% xuống 80% có thể làm DB fallback tăng rất mạnh. Nhưng hit ratio cao vẫn có thể trả dữ liệu cũ. **Cache hiệu quả và cache đúng là hai tiêu chí riêng**.

TTL expiry bình thường không giống eviction do thiếu memory. Không nên page chỉ vì vài keys hết hạn.

## 29. Search engine: query nhanh vẫn có thể stale

Với OpenSearch/Elasticsearch:

- Search p95/p99.
- Query/indexing rejects.
- Thread pool queue.
- JVM heap/GC.
- Shard count/size/skew.
- Segment merge/indexing pressure.
- CDC ingestion backlog.
- Refresh/query-visible freshness lag.

~~~text
Search p95 = 25ms, normal.
Source latestVersion = 240.
Search latestVersion = 205.
Projection lag = 120s.
~~~

Search đang nhanh nhưng dữ liệu **không mới**. Tách query-latency SLI và freshness SLI.

## 30. Đo độ trễ CDC từ commit tới hiển thị

~~~text
t0 = DB commit
t1 = CDC capture
t2 = Broker publish
t3 = Consumer update
t4 = Search query sees new version
~~~

\[
CaptureLag=t_1-t_0
\]

\[
VisibleLag=t_4-t_0
\]

Nếu SLO là “99% thay đổi search visible trong 10 giây”, broker ACK hoặc consumer lag bằng 0 chưa chứng minh đáp ứng. Dùng version watermark hoặc synthetic probe tới khi query thấy bản mới.

Với các host clocks khác nhau phải chú ý clock skew và nguồn commit ordering.

## 31. Ngưỡng theo từng nghiệp vụ

| Hệ/đường đọc | Độ mới cần bảo vệ |
| --- | --- |
| Search listing | Thường có thể eventual |
| Analytics dashboard | Có thể trễ theo phút |
| Profile vừa chỉnh sửa | Có thể cần read-your-writes |
| CDC notifications | Có target delivery delay |
| Booking inventory decision | Phải revalidate tại authority |

Không dùng một ngưỡng “replica lag >10s” cho mọi dịch vụ. Độ mới dữ liệu của search khác quyết định commit booking.

## 32. Quy trình chọn alert threshold

1. Chọn user impact/capacity risk.
2. Đặt SLO/technical invariant.
3. Đo baseline đúng workload/region/time.
4. Xác định safe headroom.
5. Đặt warning có hành động.
6. Đặt page theo SLO burn/imminent failure.
7. Thêm minimum traffic/sample floor.
8. Chọn duration/hysteresis.
9. Route tới owner/runbook.
10. Backtest với normal periods và incidents.

### Bảng minh họa

| Tín hiệu | Baseline | Warning | Page |
| --- | --- | --- | --- |
| Listing p95 | 35ms | >90ms 15m, đủ traffic | SLO burn |
| Booking bad rate | 0,02% | >0,2% sustained | Multi-window burn |
| CDC visible lag p99 | 1,5s | >5s 10m | Freshness SLO violated |
| DB pool wait p99 | 4ms | >50ms 10m | SLO impact |
| Redis evictions | ~0 | Increased + cache misses | DB fallback SLO burn |
| Disk free | 45% | Forecast headroom short | Imminent exhaustion |

**Mọi ngưỡng trong bảng là ví dụ giả định**, không phải các giá trị sản phẩm mặc định.

## 33. Composite alerts và false negatives

~~~text
Alert if:
  p99 > 400ms for 10m
  AND traffic > 100 requests/min
  AND timeout rate elevated
~~~

Có thể giảm false positives. Nhưng nếu timeout metric biến mất, điều kiện AND có thể che sự cố. Phải có SLO detector độc lập và telemetry-loss alert. Không thêm nhiều điều kiện chỉ để giảm page mà bỏ sót user impact.

## 34. PromQL cho operations và timeout fraction

Giả định các metrics:

~~~text
nosql_operations_total{operation="reserve",status="success"}
nosql_operations_total{operation="reserve",status="timeout"}
nosql_operation_seconds_bucket{operation="reserve",le="0.25"}
~~~

Rate:

~~~promql
sum by (operation) (
  rate(nosql_operations_total[5m])
)
~~~

Timeout fraction:

~~~promql
sum by (operation) (
  rate(nosql_operations_total{status="timeout"}[5m])
)
/
clamp_min(
  sum by (operation) (
    rate(nosql_operations_total[5m])
  ),
  0.001
)
~~~

`clamp_min` chỉ tránh mẫu số quá nhỏ về số học; không tự giải quyết sample size hoặc missing series. Alert vẫn cần traffic floor và NoData policy.

## 35. Prometheus alert rule minh họa

~~~yaml
groups:
  - name: nosql-example
    rules:
      - alert: ListingLatencyRegression
        expr: |
          histogram_quantile(
            0.95,
            sum by (le) (
              rate(nosql_operation_seconds_bucket{
                operation="getListing"
              }[5m])
            )
          ) > 0.12
          and
          sum(
            rate(nosql_operations_total{
              operation="getListing"
            }[5m])
          ) > 50
        for: 15m
        labels:
          severity: warning
          team: listing
        annotations:
          summary: "Listing latency regression"
          description: "Check deploy, driver pool and query plan."
          runbook_url: "https://example.invalid/runbooks/listing"
~~~

Các giá trị 0,12s, 50 req/s, 15m là **giả định học tập**. Địa chỉ `example.invalid` là placeholder, không phải runbook thực. Cần chỉnh selector theo region/cohort, metric naming và NoData handling khi dùng thật.

## 36. Java Micrometer instrumentation

Một service Java có Micrometer:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.Callable;

public final class NoSqlTelemetry {
    private final MeterRegistry registry;

    public NoSqlTelemetry(MeterRegistry registry) {
        this.registry = registry;
    }

    public <T> T observe(
            String operation, Callable<T> action)
            throws Exception {

        Timer timer = Timer.builder("nosql.operation")
                .tag("operation", operation)
                .publishPercentileHistogram()
                .register(registry);

        Timer.Sample sample = Timer.start(registry);
        String status = "success";
        try {
            return action.call();
        } catch (Exception error) {
            status = "error";
            throw error;
        } finally {
            sample.stop(timer);
            Counter.builder("nosql.operations")
                    .tag("operation", operation)
                    .tag("status", status)
                    .register(registry)
                    .increment();
        }
    }
}
~~~

### Ghi chú triển khai

- Có dependency Micrometer và MeterRegistry phù hợp.
- `operation` phải là tập giá trị cố định; không dùng user ID/raw query làm tag.
- Production nên phân loại timeout, throttled, business conflict thay vì success/error đơn giản.
- Cấu hình histogram buckets/range theo SLO.
- `finally` giúp timer ghi cả failed operations.
- Nếu driver tự retry, xác định timer đang đo logical request hay một attempt.

## 37. Driver attempts và logical latency

~~~text
Logical request:
  DB attempt 1: 20ms → throttled
  Retry backoff: 50ms
  DB attempt 2: 25ms → success
  Total: about 95ms + overhead
~~~

Nếu chỉ đo successful DB attempt, dashboard báo 25ms, không đúng độ trễ người dùng. Cần hai nhóm metrics:

- Logical request duration/status.
- Attempt latency, retries, backoff, throttle reasons.

Không trộn attempt errors vào mẫu số SLO theo logical requests mà không định nghĩa rõ.

## 38. Tracing để tìm nguyên nhân

Một request cụ thể:

~~~text
API queue: 350ms
Driver pool wait: 200ms
DB execution/network: 100ms
Serialization: 50ms
Backoff: 100ms
Total: 800ms
~~~

Trace của **một request** có thể cho biết thời gian nằm ở đâu. Nhưng `p99(queue)+p99(DB)+p99(serialization)` từ các sets khác nhau không tự bằng `p99(total)`.

Metrics cho phân bố; traces cho causal path; logs cho query fingerprint/errors; DB profiler cho execution details.

## 39. Baseline sau deploy và cold start

Deploy mới có thể đổi query plan, index, partition key, cache TTL, driver pooling, instance size hoặc CDC batch size.

~~~text
Version A: p95=40ms at 800 req/s.
Version B: p95=55ms at 800 req/s.
~~~

So canary với cùng workload, dataset, cache state và traffic cohorts khi có thể. Nếu B chỉ nhận heavy tenants, so p95 thô có thể sai.

Sau restart, cache và JIT warm-up có thể làm latency khác steady state. Baseline nên phân biệt giai đoạn warm-up; nhưng requests người dùng thực nhận vẫn phải tính theo SLI contract, không mặc định miễn trừ.

## 40. Capacity forecast

Thay vì alert “disk >90%” quá muộn:

\[
TimeToFull\approx\frac{FreeCapacity}{NetGrowthRate}
\]

Còn 600 GiB, tăng ròng 100 GiB/ngày → khoảng **6 ngày** theo mô hình tuyến tính.

Thực tế compaction, repair, snapshots, sudden import và retention có thể làm nhu cầu tăng đột biến. Forecast cần uncertainty/headroom, không xem 6 ngày là deadline chính xác.

## 41. Chất lượng cảnh báo và alert fatigue

Theo dõi:

- Pages per on-call shift.
- Tỷ lệ pages có hành động thực tế.
- Time-to-detect/time-to-mitigate.
- Repeat/flapping alerts.
- Incidents không có cảnh báo (false negatives).
- Alerts cùng root cause bị gửi trùng.

Giảm nhiễu bằng grouping/inhibition, đúng severity/owner, duration và backtesting. **Không chỉ tắt alarms để đạt số pages thấp**; chất lượng là phát hiện đúng vấn đề đủ sớm.

## 42. Runbook p99 latency tăng

1. Kiểm user impact, bad-request rate, SLO burn.
2. Kiểm telemetry đủ sample, exporter khỏe.
3. So baseline cùng giờ/traffic cohort.
4. Kiểm deploy/schema/index/cluster changes.
5. Xem Java queue, thread pool, retries/backoff.
6. Xem driver connection pool wait, network.
7. Xem query plan, partitions, compaction, disk/GC.
8. Xem replica/CDC freshness nếu đọc projection.
9. Giảm tải batch, rollback deploy, rate limit hot traffic hoặc scale đúng bottleneck theo runbook.
10. Xác minh SLO phục hồi và không phá business invariant.

Không chỉ tăng timeout để che một hàng đợi đang phình.

## 43. Runbook cache miss spike

1. So hit/miss ratio với cùng workload baseline.
2. Kiểm cold start/TTL expiry/eviction.
3. Kiểm memory headroom và hot keys.
4. Kiểm recent invalidation/deploy.
5. Đo DB fallback QPS và p99.
6. Kiểm stampede/concurrent cache loads.
7. Dùng single-flight, backpressure/rate limit khi cần.
8. Không nâng TTL nếu làm sai freshness contract.

## 44. Runbook Cassandra compaction backlog

1. Kiểm read/write SLI và timeouts.
2. Xem pending compactions theo node/table.
3. Kiểm disk latency/free space, GC và flush backlog.
4. Kiểm tombstone scans/SSTable count/hot partitions.
5. Xác định batch import/repair/TTL cleanup gần đây.
6. Giảm tải hoặc điều chỉnh capacity/compaction theo runbook đã xác minh.
7. Xác nhận backlog drain và p99 trở lại baseline.

Metrics và knobs phụ thuộc phiên bản Cassandra/driver; không có một ngưỡng compaction queue toàn cục dùng cho mọi hệ.

## 45. Runbook DynamoDB throttling

1. Xác định operation/table/index/region.
2. Kiểm throttling reasons và user-visible errors.
3. So consumed capacity với capacity mode.
4. Kiểm key skew/hot partition.
5. Xem SDK retry/backoff/latency.
6. Xem autoscaling reaction nếu có.
7. Giảm batch concurrency hoặc tối ưu key/access pattern.
8. Đo SLO recovery và cost.

## 46. Fault injection và backtesting

| Test | Tạo tình huống | Kỳ vọng |
| --- | --- | --- |
| A | Artificial DB latency | Latency/SLO alert |
| B | Pool starvation | Saturation warning |
| C | Hot partition | Per-node/key throttling |
| D | CDC consumer paused | Freshness/backlog alert |
| E | Cache miss spike | DB fallback impact |
| F | Exporter stopped | NoData/TargetDown |
| G | Expected weekend peak | Không false page |
| H | Query plan regression | Diagnostics warning |
| I | Disk growth spike | Forecast warning |
| J | One tenant degraded | Scoped alert |

Backtest trên lịch sử có normal periods và incidents để đo false positives/false negatives. Fault injection nên thực hiện ở lab/staging hoặc môi trường có kiểm soát.

## 47. Mẫu baseline report

~~~yaml
service: "listing-api"
operation: "getListing"
database: "MongoDB"
scope:
  region: "example-region"
  trafficClass: "interactive"
observation:
  period: "representative weekly cycles"
  interval: "15s raw, 5m aggregate"
  incidents: "labeled separately"
  releaseVersion: "example-v1"
baseline:
  p50Ms: 12
  p95Ms: 35
  p99Ms: 80
  badRequestRatePct: 0.02
  poolWaitP99Ms: 6
  cacheHitRatePct: 91
slo:
  target: "99.9% good requests over 30 days"
  goodDefinition: "successful within 250ms"
alerts:
  page: "multi-window error budget burn"
  warning: "p95 regression with enough traffic"
  capacity: "forecast headroom and saturation"
owner: "listing-oncall"
runbook: "internal runbook link"
review: "after schema/index/traffic changes"
~~~

Các số là ví dụ; bản production phải lấy từ metrics thực và đường dẫn/runbook được đội vận hành xác nhận.

## 48. Bài tập thực hành

### Bài 1 — Baseline và traffic

API có p95=35ms ở 500 req/s, p95=75ms ở 2.000 req/s. Có đủ bằng chứng regression không? Thiếu những bối cảnh nào?

### Bài 2 — RED/USE

Lập bảng metric RED cho Booking API và USE cho database/driver. Phân loại impact vs diagnosis.

### Bài 3 — Denominator

Một API có 100 timeouts, 500 sold-out responses và 1.000 client validation errors. Chọn cách tính SLI theo contract.

### Bài 4 — Error budget

SLO 99,9%, 8 triệu eligible requests. Tính số bad requests được phép.

**Gợi ý:** 8.000.

### Bài 5 — Burn rate

Allowed bad rate=0,1%, observed=0,6%. Burn rate là bao nhiêu? Sáu giờ ở tốc độ ấy tiêu bao nhiêu % budget 30 ngày nếu assumptions ổn định?

**Gợi ý:** 6 và 5%.

### Bài 6 — p99

Node A có 100 requests, p99=500ms; B có 100.000 requests, p99=20ms. Tại sao trung bình p99 không phải global p99?

### Bài 7 — Missing timeout observations

Timer chỉ ghi khi thành công. Khi timeout tăng, dashboard p99 giảm. Giải thích và sửa.

### Bài 8 — Seasonality

Cuối tuần traffic gấp bốn. Thiết kế baseline theo giờ trong tuần và traffic buckets.

### Bài 9 — MAD

Tính median và MAD của [90,94,97,100,105,108,145]. Độ lệch thống kê cao có luôn đáng page?

**Gợi ý:** median=100, MAD=6.

### Bài 10 — Low traffic

Hai requests, một lỗi, error rate 50%. Tại sao cần sample floor/synthetic probes?

### Bài 11 — SLO vs baseline

Baseline p95=100ms, SLO 99% dưới 150ms. Vì sao warning chỉ khi p95>300ms có thể quá muộn?

### Bài 12 — NoData

Exporter chết, error counter biến mất. Thiết kế alert không coi đó là healthy.

### Bài 13 — Cassandra

Ba nodes CPU 95%, 30%, 28%; cluster average khoảng 51%. Chọn per-node saturation alerts.

### Bài 14 — Tombstones

Query p99 tăng cùng tombstone scanned/SSTable count. Thiết kế điều tra compaction, GC và disk.

### Bài 15 — DynamoDB

Table consumed WCU bình thường nhưng hot key throttle 8%. Cảnh báo nào cần thêm?

### Bài 16 — Conditional failure

`ConditionalCheckFailed` là system error hay business conflict? Nêu tiêu chí phân biệt.

### Bài 17 — Redis

Cache hit ratio giảm từ 95% xuống 80%, DB fallback tăng. Đặt warning/page dựa trên impact.

### Bài 18 — Search

Search p95=25ms nhưng CDC lag=120s. Tạo freshness SLI đo đến query-visible update.

### Bài 19 — Retry latency

Attempt 1=20ms lỗi, backoff=50ms, attempt 2=25ms thành công. Logical latency gần bao nhiêu?

### Bài 20 — Disk forecast

Còn 600 GiB, tăng 100 GiB/ngày. Tính time-to-full và giới hạn của mô hình.

### Bài 21 — Composite alerts

Rule có p99 cao AND CPU cao AND timeout cao. CPU exporter mất có thể gây false negative nào?

### Bài 22 — Metrics tags

Vì sao không dùng userId/raw query làm Micrometer labels? Đề xuất thay thế.

### Bài 23 — PromQL

Viết query p95 từ classic histogram và request rate; bổ sung NoData/traffic-floor policy.

### Bài 24 — Deploy comparison

Index mới làm p95 tăng 40→55ms. Thiết kế canary cohort comparison.

### Bài 25 — Alert fatigue

Nhóm nhận 200 pages/tuần, 90% không cần hành động. Làm gì để giảm noise mà không bỏ sót incidents?

### Bài 26 — Runbook

Soạn runbook p99 tăng 4×: user impact → telemetry → pool wait → query plan → saturation → mitigation.

### Bài 27 — Fault test

Thiết kế tests cho CDC lag, cache miss spike, hot partition và exporter loss. Đặt expected alert/detection time.

### Bài 28 — Tổng hợp

Thiết kế hệ giám sát cho MongoDB listing, Cassandra event history, DynamoDB conditional writes, Redis cache và search projection. Cần SLI/SLO, baseline theo workload, latency/error/saturation, CDC freshness, capacity alerts, owner/runbook, NoData và backtesting.

**Gợi ý:** bắt đầu từ user impact/SLO, sau đó truy ngược xuống từng storage engine.

## 49. Checklist áp dụng

1. Đã xác định business-critical operations chưa?
2. SLI có good/bad criteria và denominator rõ không?
3. Baseline phân tầng theo workload/region/traffic không?
4. Đã bao phủ peak/off-peak và background jobs chưa?
5. Có histogram đủ buckets thay vì average của p99 không?
6. Timeouts/failures có được đo không?
7. Retry attempts và logical requests có tách không?
8. Có traffic floor, duration, hysteresis và NoData không?
9. SLO burn alerts có độc lập với resource composite không?
10. Hot partitions/nodes có bị cluster average che không?
11. Mongo query plan, Cassandra tombstones/compaction, Dynamo throttling, Redis eviction có metrics riêng không?
12. CDC freshness có đo đến query-visible version không?
13. Cache correctness có được xem riêng hit rate không?
14. Có capacity forecast/headroom không?
15. Metric labels có low cardinality và không lộ PII không?
16. Alert có owner, severity, runbook và hành động rõ không?
17. Alert rules đã test với lịch sử và faults chưa?
18. Có review baseline sau deploy/schema/index changes không?
19. Có theo dõi alert fatigue và false negatives không?
20. Business invariants có detector riêng ngoài availability budget không?

**Một alert chỉ ghi “CPU >80%” mà không có impact, duration, scope và action thường chưa phải ngưỡng có ý nghĩa.**

## 50. Tổng kết

1. **Baseline** là phân bố số đo theo đúng tải, dữ liệu, thời gian và cấu hình, không chỉ một average của cluster.
2. **SLI/SLO** bảo vệ chất lượng người dùng; baseline giúp phát hiện regression và capacity risk.
3. **RED và USE** là hai lớp bổ trợ: một lớp đo ảnh hưởng, lớp kia chẩn đoán tài nguyên.
4. **p95/p99 cần được tính từ dữ liệu phân bố đúng**, có sample size và đo cả failed requests.
5. **Error budget burn rate** giúp định mức khẩn cấp theo thời gian, không bị dynamic baseline che vi phạm SLO.
6. **Threshold có ý nghĩa** cần duration, sample floor, hysteresis, no-data policy và action.
7. **NoSQL có tín hiệu riêng:** MongoDB pool/index, Cassandra partition/compaction/tombstones, DynamoDB throttle/hot keys, Redis cache/eviction, search/CDC freshness.
8. **Một query nhanh không chứng minh dữ liệu mới.** Freshness cần SLI riêng.
9. **Java metrics/PromQL và runbooks phải được kiểm thử**, gồm fault injection, backtesting và review sau deploy.
10. **Đích cuối cùng là phát hiện và khắc phục đúng sự cố nhanh hơn**, không phải có càng nhiều cảnh báo càng tốt.

**Nguyên tắc thực hành:** trước mỗi ngưỡng cảnh báo NoSQL, hãy trả lời bốn câu: **“đang bảo vệ SLO/rủi ro gì?”, “mức nền trong đúng workload là bao nhiêu?”, “vượt ngưỡng bao lâu mới cần hành động?”, “ai sẽ làm gì khi alert nổ?”**. Khi những câu trả lời có số liệu và có thể kiểm chứng, baseline và alerts mới hỗ trợ quan sát, chẩn đoán và vận hành hệ thống một cách đáng tin cậy.
