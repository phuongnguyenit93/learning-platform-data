# Theo dõi lỗi, độ trễ, bộ nhớ và hành vi GC sau phát hành

Nâng JDK, framework hoặc cơ chế đóng gói là một thay đổi có thể tác động đến ứng dụng **ngay cả khi toàn bộ code nghiệp vụ vẫn giống phiên bản trước**. Một bản phát hành Java 21 có thể khởi động và vượt unit tests nhưng xử lý request chậm hơn ở mức p99; một thay đổi dependency có thể làm số lỗi 5xx tăng; một JVM mới có thể cho thấy biểu đồ heap khác trước; hoặc một thay đổi GC configuration có thể giảm pause time nhưng làm tăng mức dùng CPU.

Do đó, **Java Advance Compatibility Migration không kết thúc khi build thành công**. Giai đoạn phát hành và vận hành cần một hệ thống đo lường giúp trả lời bốn câu hỏi:

1. **Lỗi:** Người dùng và các hệ thống tích hợp có gặp lỗi nhiều hơn không?
2. **Độ trễ:** Thời gian xử lý ở những phần quan trọng có xấu đi, nhất là tail latency không?
3. **Bộ nhớ:** Heap, non-heap, native memory và bộ nhớ container còn đủ headroom không?
4. **Garbage Collection (GC):** Tần suất, thời lượng và tác động của các chu kỳ thu gom có thay đổi bất lợi không?

Không thể kết luận chỉ từ một biểu đồ riêng lẻ. Chẳng hạn heap-used tăng không luôn là memory leak, GC count tăng không luôn là lỗi, còn p99 tăng không nhất thiết xuất phát từ GC. Cần nối **release metadata, workload, request traces, JVM metrics, GC events và tài nguyên hệ thống** để phân biệt thay đổi bình thường với regression.

Bài học này xây dựng một quy trình quan sát **trước – trong – sau phát hành**, gồm baseline, Service Level Indicators (SLI), canary, dashboard, ngưỡng cảnh báo, truy vết lỗi, phân tích p95/p99, heap/native memory, GC logs, Java Flight Recorder (JFR), xử lý sự cố và rollback. Những con số minh họa chỉ là dữ liệu giả định; ngưỡng vận hành thật phải được xác định từ SLO, tải và đặc tính của dịch vụ.

---

## 1. Vì sao sau migration phải đo cả ứng dụng và JVM?

### 1.1. Thay JDK có thể làm nhiều thứ thay đổi

Một lần chuyển từ JDK cũ sang JDK mới có thể đi kèm:

- Compiler và bytecode target mới.
- GC mặc định hoặc GC flags khác.
- Java platform APIs và JDK internals thay đổi.
- TLS, security provider, certificate, locale hoặc timezone data được cập nhật.
- Framework, driver, serializer và bytecode agent được nâng phiên bản.
- Container base image hoặc giới hạn cgroup khác.
- Threading, scheduling và executor behavior khác.
- JVM startup, JIT compilation, warm-up hoặc class loading thay đổi.
- Các library cũ chỉ lỗi trên một code path ít được sử dụng.

Nếu lỗi xuất hiện sau release, không nên tự động quy mọi thứ cho GC hoặc JDK. Phải có bằng chứng **đang chạy bản nào**, **thay đổi nào đã được triển khai** và **triệu chứng thuộc tầng nào**.

### 1.2. Quan sát theo ba tầng

```text
                 Trải nghiệm người dùng
           lỗi, thời gian đáp ứng, timeout
                           |
                           v
                    Ứng dụng / JVM
              request, trace, thread, heap
                 allocation, GC, safepoint
                           |
                           v
                    Hạ tầng / OS
             CPU, RAM, cgroup, I/O, network
                    pod restarts, OOMKill
```

Ba tầng phải được đọc cùng nhau. Ví dụ người dùng báo timeout có thể do backend GC pause, cũng có thể do database chậm, queue dài hoặc network packet loss. Heap ổn định không loại trừ native memory pressure dẫn đến container OOMKill.

### 1.3. Bốn nhóm tín hiệu tối thiểu

| Nhóm | Cần đo | Rủi ro bỏ sót |
|---|---|---|
| Lỗi | Error rate, exception type, startup failures, timeouts | Dịch vụ “running” nhưng nghiệp vụ lỗi |
| Độ trễ | p50/p95/p99, throughput, queue time | Trung bình tốt nhưng nhiều request chậm |
| Bộ nhớ | Heap, non-heap, RSS/container, allocation, OOM | Không phát hiện leak hoặc thiếu headroom |
| GC | Pause duration, frequency, GC time ratio, old-gen trend | Không giải thích được tail latency và áp lực CPU |

Ngoài ra nên có CPU, số threads, connection pools, database latency, deployment version và log/tracing. Không nên tạo một “JVM dashboard” đẹp nhưng không liên kết được tới tác động đối với người dùng.

## 2. Bước đầu tiên: xác định phạm vi và tiêu chí thành công

### 2.1. Mục tiêu migration phải đo được

Thay vì viết:

```text
Nâng Java 17 lên Java 21.
Yêu cầu: hệ thống chạy ổn định.
```

nên đặt tiêu chí có thể kiểm chứng:

```text
Ứng dụng      : order-service
Runtime cũ    : JDK 17, vendor/version đã ghi nhận
Runtime mới   : JDK 21, vendor/version đã ghi nhận
Framework     : phiên bản/bản vá đã kiểm chứng
Hạ tầng       : cùng giới hạn CPU/RAM, hoặc có ghi nhận khác biệt
SLO           : theo contract hiện hành
Phát hành     : canary -> tăng traffic -> toàn bộ
Tiêu chí      : không suy giảm error/latency/memory/GC ngoài ngưỡng
Rollback      : sẵn sàng nếu ngưỡng được xác nhận vượt quá
```

Những giá trị trên là mẫu cấu trúc. Khi triển khai thật, phải xác định exact image digest, source revision, dependency versions và runtime options.

### 2.2. Đừng đặt ngưỡng bằng cảm giác

Ví dụ một dịch vụ có SLO p99 dưới 300 ms. Sau migration, p99 tăng từ 180 ms lên 230 ms. Đây có thể là regression đáng kiểm tra dù vẫn chưa vi phạm SLO. Ngược lại, p99 tăng từ 10 ms lên 12 ms có thể không mang ý nghĩa vận hành nếu sản phẩm cho phép biên độ lớn.

Nên quản lý hai loại tiêu chí:

- **SLO/customer impact:** ngưỡng mà người dùng hoặc hợp đồng dịch vụ quan tâm.
- **Regression guardrail:** mức thay đổi so với baseline đủ lớn để dừng rollout hoặc điều tra.

Guardrail phải xét biến động tự nhiên, sample size và traffic mix. Không phải mọi sai khác một vài phần trăm đều đủ chứng minh một regression.

### 2.3. Phân loại ứng dụng

Các chỉ số nên được chọn theo workload:

| Loại ứng dụng | Tín hiệu trọng tâm |
|---|---|
| HTTP API | Error rate, p95/p99 theo route, request throughput, saturation |
| Batch job | Thành công/thất bại, job duration, records/sec, retries |
| Message consumer | Lag, processing latency, retry/dead-letter, rebalance |
| Desktop/CLI | Startup time, command duration, crash, memory footprint |
| Streaming service | End-to-end lag, backpressure, throughput, tail latency |
| JVM library | Test matrix trên JDK tiêu thụ, allocation, performance regressions |
| Background scheduler | Missed schedules, execution delay, overlapping jobs |

Không dùng HTTP request latency làm chỉ số duy nhất cho batch application hoặc messaging worker.

## 3. Thiết lập baseline trước khi phát hành

### 3.1. Baseline là gì?

**Baseline** là tập chỉ số và điều kiện vận hành được ghi nhận từ bản đang chạy ổn định, dùng để so sánh sau release.

Một baseline tối thiểu cần gồm:

- Application version và exact JDK vendor/full version.
- Runtime flags, GC collector và heap/container limits.
- CPU, memory, OS, architecture, container image.
- Workload: request rate, payload sizes, tenant/route mix.
- Error rate và error categories.
- p50/p95/p99 theo operation quan trọng.
- JVM heap/non-heap, process RSS và container memory.
- GC pause, tần suất và allocation rate nếu có.
- Threads, DB/HTTP connection pools, queue lengths.
- Thời điểm peak/off-peak và ngày/giờ có ý nghĩa nghiệp vụ.

### 3.2. So sánh cùng tải và cùng điều kiện

Ví dụ so sánh dễ gây nhầm:

```text
Trước release:
  100 request/s, chủ yếu GET nhẹ
  CPU 1 core, RAM 1 GiB

Sau release:
  300 request/s, nhiều request tạo báo cáo
  CPU 1 core, RAM 1 GiB

Kết luận "JDK mới gây p99 tăng" -> chưa có căn cứ.
```

Để so sánh có ý nghĩa, cần kiểm soát hoặc ghi nhận những biến như request rate, mix, payload, database load, CPU quota, autoscaling, cache warm-up, instance age và routing.

Một cách mạnh hơn là chạy **canary cũ và mới đồng thời** dưới phân phối traffic tương đương. Nếu không thể, dùng những khung thời gian đại diện và nêu rõ giới hạn của kết luận.

### 3.3. Tránh lấy baseline từ một khoảng thời gian quá ngắn

Vài phút trước release có thể không đại diện cho:

- Chu kỳ traffic theo giờ/ngày.
- Batch processing vào cuối ngày.
- Memory growth sau nhiều giờ.
- Cron jobs và scheduled cleanup.
- Chu kỳ GC dài hoặc rare full collections.
- TLS certificate refresh, connection pool reconfiguration.
- Các tính năng ít gọi nhưng rất quan trọng.

Chọn khoảng baseline dựa trên chu kỳ thực tế của workload, không tự áp một con số cố định cho mọi dịch vụ.

### 3.4. Lưu metadata để so sánh

Một bảng mẫu:

| Thuộc tính | Old release | Candidate release |
|---|---|---|
| App commit | Revision A | Revision B |
| Artifact SHA-256 | Checksum A | Checksum B |
| JDK vendor/build | JDK 17 update X | JDK 21 update Y |
| Collector | G1 theo cấu hình | G1 theo cấu hình |
| Heap limit | 768 MiB | 768 MiB |
| Container limit | 1.5 GiB | 1.5 GiB |
| CPU limit | 2 vCPU | 2 vCPU |
| Agent version | APM release A | APM release B |
| Traffic share | Stable | Canary |
| Framework | Framework release A | Framework release B |

Số và tên trong bảng chỉ mang tính minh họa. Một lần thay JDK mà đồng thời tăng memory limit và nâng framework có thể hợp lệ, nhưng cần ghi nhận để tránh kết luận sai về nguyên nhân.

## 4. Thiết kế dashboard vận hành sau phát hành

### 4.1. Dashboard phải trả lời câu hỏi, không chỉ trưng số liệu

Một bố cục hữu ích:

```text
+-------------------------------------------------------------+
| Release: old vs canary | JDK version | traffic split | time |
+-------------------------------------------------------------+
| Error rate | request rate | SLO burn rate | restart count  |
+-------------------------------------------------------------+
| p50 latency | p95 latency | p99 latency | queue wait       |
+-------------------------------------------------------------+
| CPU | heap used/committed/max | RSS | container memory     |
+-------------------------------------------------------------+
| GC pause p95/p99 | GC time rate | allocation | old-gen     |
+-------------------------------------------------------------+
| Threads | connection pools | retry/dead-letter | logs/traces |
+-------------------------------------------------------------+
```

Quan trọng nhất là có thể phân tách theo **service, environment, application version, JDK version và instance/pod** khi cần. Tránh tạo label/cardinality quá cao từ request ID, raw URL, email, user ID hoặc payload.

### 4.2. Chỉ số tổng hợp và phân đoạn phải đi cùng nhau

Một service có thể có error rate tổng thể ổn định nhưng một route trọng yếu lỗi 20%. Vì vậy:

- Dashboard tổng quan để phát hiện.
- Biểu đồ theo endpoint/operation để khoanh vùng.
- Breakdown theo status code, exception type, dependency.
- So sánh old/canary theo release version.
- Drill-down tới trace/log liên quan.

Không nhóm tất cả latency vào một biểu đồ nếu GET nhẹ và report generation có phân phối độ trễ hoàn toàn khác.

### 4.3. Gắn deployment events

Dashboard nên có marker thể hiện:

```text
10:00 Canary 5%
10:30 Canary 20%
11:15 Canary 50%
12:00 Full rollout
12:20 JDK option changed
```

Thời gian chỉ minh họa. Marker giúp xác định có phải tín hiệu bắt đầu thay đổi đúng lúc release, thay vì suy từ trí nhớ của người trực.

## 5. Theo dõi lỗi sau phát hành

### 5.1. Error rate và error budget

Đối với HTTP service, một SLI có thể là:

```text
Success ratio =
  số request hợp lệ hoàn tất thành công /
  tổng số request thuộc phạm vi SLI
```

Tùy sản phẩm, lỗi bao gồm 5xx, application-level failures, deadline exceeded, timeout hoặc trả response “200 OK” nhưng nghiệp vụ thực sự thất bại. Không mặc định mọi 4xx là service error; một số là input validation do client, nhưng 429 hoặc 408 có thể phản ánh overload tùy định nghĩa SLI.

### 5.2. Các lỗi đặc biệt liên quan Java migration

| Nhóm | Ví dụ | Ý nghĩa điều tra |
|---|---|---|
| Linkage | `NoSuchMethodError`, `NoSuchFieldError` | Dependency/ABI lệch |
| Bytecode | `UnsupportedClassVersionError` | Artifact class version quá mới |
| Classloading | `ClassNotFoundException`, `NoClassDefFoundError` | Thiếu JAR/module, init lỗi |
| JPMS/reflection | `InaccessibleObjectException`, `IllegalAccessError` | Access policy/module |
| Resources | `OutOfMemoryError`, native OOM | Heap, metaspace hoặc native/container |
| TLS | `SSLHandshakeException` | Certificate/protocol/provider |
| Native | `UnsatisfiedLinkError` | JNI/OS/architecture/ABI |
| Concurrency | Deadlock, timeouts, rejected tasks | Threading/executor behavior |
| Framework | Initialization/configuration error | Library/plugin migration |
| Data | Serialization/schema mismatch | Protocol và payload compatibility |

Không nên chỉ alert trên một exception tên cụ thể; production có nhiều lỗi ứng dụng không biểu hiện bằng Java exception hoặc được framework map thành response.

### 5.3. Đếm lỗi có ngữ cảnh

Ví dụ log có cấu trúc:

```json
{
  "timestamp": "2026-11-12T10:30:00Z",
  "level": "ERROR",
  "service": "order-service",
  "release": "2.4.0",
  "jdk": "21",
  "operation": "create-order",
  "error_type": "TimeoutException",
  "trace_id": "example-trace-id",
  "message": "downstream deadline exceeded"
}
```

Đây là log giả định. Không đưa raw customer ID, credentials hoặc request bodies nhạy cảm vào log. Một trace ID có thể giúp nối request lỗi với thời gian của GC pause, database latency và CPU spike.

### 5.4. Mẫu theo dõi mức tăng lỗi

| Tín hiệu | Mức quan sát | Phản ứng |
|---|---|---|
| Error rate tăng nhẹ nhưng trong dao động nền | Theo dõi | So traffic mix, sample |
| Error rate vượt guardrail trong nhiều cửa sổ | Cảnh báo rollout | Dừng tăng traffic, phân tích |
| SLO bị ảnh hưởng rõ hoặc lỗi chức năng trọng yếu | Sự cố | Cân nhắc rollback ngay theo runbook |
| Crash loop sau deploy | Sự cố nghiêm trọng | Kiểm tra startup/JDK/dependency, khôi phục |
| Một instance canary lỗi, instance khác ổn | Điều tra phân vùng | Kiểm tra config/image/node/arch |
| Error rate thấp do canary chưa có request | Không đủ dữ liệu | Chưa kết luận pass |

Ngưỡng cụ thể phải gắn với SLO, error budget, lưu lượng và mức độ quan trọng của chức năng.

## 6. Theo dõi độ trễ: không chỉ dùng average

### 6.1. p50, p95 và p99

Percentile latency biểu thị mốc mà một tỷ lệ request có thời gian xử lý **không vượt quá** giá trị đó:

- **p50:** median, cho biết request điển hình.
- **p95:** phần lớn request, nhạy hơn với đuôi phân phối.
- **p99:** 99% request ở dưới hoặc bằng mốc này; tập trung vào tail latency.
- **max:** request chậm nhất được thấy trong tập đo, dễ bị ảnh hưởng outliers.

Ví dụ giả định:

| Phiên bản | p50 | p95 | p99 | Request rate |
|---|---:|---:|---:|---:|
| Java 17 | 40 ms | 110 ms | 230 ms | 200/s |
| Java 21 | 42 ms | 118 ms | 490 ms | 200/s |

Chỉ nhìn average hoặc p50 sẽ bỏ qua việc p99 tăng mạnh. Nhưng trước khi kết luận regression, cần xác nhận sample size, loại request, thời gian warm-up, percentile computation và traffic mix.

### 6.2. Percentiles không thể cộng/trung bình tùy ý

Một lỗi phổ biến:

```text
p99(instance A) = 100 ms
p99(instance B) = 900 ms

Lấy trung bình (100 + 900) / 2 = 500 ms
-> không nhất thiết là p99 toàn service.
```

Nếu đo latency bằng histogram có cumulative buckets, có thể tính percentile từ **tổng bucket counts phù hợp**. Với client-side percentiles không thể aggregate đơn giản qua instances, cần cách thu thập/distribution phù hợp.

### 6.3. Tổng latency gồm những phần nào?

Một request có thể đi qua:

```text
Ingress / proxy
  -> network queue
  -> server accept
  -> application queue
  -> business processing
  -> DB/HTTP downstream
  -> response serialization
  -> response to client
```

Nếu JVM application metric chỉ đo từ handler vào đến handler ra, nó không bao gồm mọi thời gian người dùng quan sát, như ingress queue hoặc network RTT. Khi điều tra regression, tách:

- End-to-end client latency.
- Server-side handler latency.
- Queue wait.
- Dependency call latency.
- Serialization/deserialization.
- GC pauses và safepoints.
- Thread/executor scheduling.

### 6.4. Tail latency có thể tăng do GC nhưng không chỉ do GC

Một request lâu có thể trùng với stop-the-world pause, nhưng cũng có thể do:

- Connection pool hết kết nối.
- Database lock hoặc slow query.
- DNS/TLS handshake.
- Thread pool starvation.
- CPU throttling.
- Retry storm.
- Cache misses/warm-up.
- Synchronized contention.
- Virtual-thread pinning trong một số workload.
- Garbage collection hoặc safepoint.

Cần correlation giữa timestamps, traces và JVM diagnostics, không suy từ hai biểu đồ cùng tăng một cách cảm tính.

## 7. Histogram, throughput và saturation

### 7.1. Chọn histogram buckets có ý nghĩa

Ví dụ service SLO p99 ở mức 300 ms. Histogram latency nên có buckets đủ chi tiết quanh 100–300–500 ms để phát hiện vi phạm; nếu buckets quá thưa, p99 suy ra sẽ ít chính xác.

Một ví dụ phân bố giả định:

```text
<= 50 ms    : phần lớn
<= 100 ms   : nhiều
<= 200 ms   : gần SLO
<= 300 ms   : mục tiêu
<= 500 ms   : chậm
>  500 ms   : rất chậm
```

Đừng mặc định cùng histogram buckets cho một endpoint 5 ms và một batch job 30 phút. Buckets phải dựa trên SLO và workload.

### 7.2. Throughput là điều kiện giải thích latency

Một version xử lý p99 200 ms ở tải 20 req/s không thể được khẳng định nhanh hơn version p99 230 ms ở tải 500 req/s.

Theo dõi song song:

- Requests/messages/jobs mỗi giây.
- Number of concurrent in-flight operations.
- Queue length và queue wait.
- Errors/timeouts/retries.
- CPU usage và throttling.
- Connection pool utilization.
- Load shedding/rate limiting.

Trong thử tải, ghi rõ warm-up, ramp-up, steady-state, thời lượng và điều kiện dừng.

### 7.3. Đo theo route mà không tạo cardinality bùng nổ

Tránh label:

```text
path="/users/12345/orders/98432"
```

Nếu mỗi URL sinh time series mới, hệ metrics có thể quá tải. Nên dùng route template:

```text
route="/users/{userId}/orders/{orderId}"
```

Không đưa user ID, order ID, token hoặc raw query parameters vào labels.

## 8. Mẫu Prometheus/Micrometer để phân tích

Các ví dụ PromQL dưới đây **giả định** hệ instrumentation phát metrics tên `http_server_requests_seconds_*` theo kiểu histogram Prometheus và label `status` chứa HTTP status code. Tên metric, nhãn, classic/native histogram và semantic conventions khác nhau giữa Micrometer/OpenTelemetry/exporter versions; cần kiểm tra dữ liệu thật trước khi áp dụng.

### 8.1. Request throughput

```promql
sum(
  rate(http_server_requests_seconds_count{
    application="order-service"
  }[5m])
)
```

Đây là rate trung bình trong cửa sổ 5 phút, không phải tổng số request trong 5 phút.

### 8.2. Tỷ lệ HTTP 5xx

```promql
sum(
  rate(http_server_requests_seconds_count{
    application="order-service",
    status=~"5.."
  }[5m])
)
/
sum(
  rate(http_server_requests_seconds_count{
    application="order-service"
  }[5m])
)
```

Khi traffic quá thấp, mẫu số có thể bằng 0 hoặc ước lượng nhiễu. Cần kết hợp absolute error counts và điều kiện minimum traffic, đồng thời định nghĩa rõ những lỗi ứng dụng không được phản ánh bằng 5xx.

### 8.3. p99 từ classic histogram

```promql
histogram_quantile(
  0.99,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      application="order-service",
      uri="/orders/{id}"
    }[5m])
  )
)
```

Đây là một ví dụ filter route, trong đó label `uri` chỉ là giả định. Với nhiều service instances, cộng theo `le` để tính phân phối tổng thể; nếu cần breakdown theo version, giữ thêm label version trong `sum by (...)` và phân tách kết quả theo release.

### 8.4. Đặt ngưỡng không phụ thuộc duy nhất vào p99

p99 có thể dao động mạnh khi lượng request ít. Dashboard nên đi cùng:

- Total request count.
- Error count.
- p50/p95/p99.
- Histogram heatmap hoặc bucket distribution.
- SLO violation ratio.
- Number of affected instances.
- Cửa sổ đủ dài để thu sample đại diện.

Các query cần được xác minh trên hệ metrics thật; không triển khai alert production chỉ vì chúng chạy được trên dữ liệu mẫu.

## 9. Bộ nhớ JVM: phải hiểu từng vùng

### 9.1. Heap used, committed và max

Java heap có các khái niệm:

- **Used:** số byte JVM báo đang được sử dụng trong heap.
- **Committed:** số byte đã được JVM cam kết cho heap.
- **Max:** giới hạn tối đa heap theo cấu hình/capability của runtime.

Sơ đồ:

```text
Heap max (ví dụ 1024 MiB)
+-----------------------------------------+
| Committed (ví dụ 768 MiB)                |
| +-------------------------------------+ |
| | Used (ví dụ 420 MiB)                | |
| +-------------------------------------+ |
|                 free committed space    |
+-----------------------------------------+
                   uncommitted capacity
```

Used khác committed; committed khác RSS. Biểu đồ heap committed tăng không tự động đồng nghĩa live objects tăng hoặc memory leak.

### 9.2. Non-heap và native memory

Ứng dụng Java dùng nhiều vùng bộ nhớ ngoài object heap:

| Vùng | Ví dụ | Triệu chứng |
|---|---|---|
| Metaspace | Class metadata | Classloader leak, plugin redeploy |
| Code cache | JIT compiled code | Code cache pressure, compilation behavior |
| Direct buffers | NIO/Netty direct memory | RSS tăng dù heap ổn định |
| Thread stacks | Platform threads | Nhiều threads làm native memory tăng |
| JNI/native allocations | Native library, compression, crypto | Process RSS tăng không phản ánh hết qua heap |
| Memory mapped files | Mapped buffers/files | Page/cache/virtual memory behavior |
| GC internal structures | Collector metadata/buffers | Khác collector hoặc heap sizing |
| JIT/runtime internals | Compiler, symbols | Native memory footprint |

Không cộng một cách đơn giản tất cả metrics có tên “memory” mà không hiểu overlap. Một số container metrics bao gồm page cache, trong khi JVM heap metrics chỉ mô tả bộ nhớ do JVM quản lý.

### 9.3. Process RSS và container memory

**RSS (resident set size)** là một góc nhìn mức bộ nhớ vật lý đang hiện diện của process theo OS. **Container working set/usage** là cách nhìn ở cgroup/container, có thể gồm các thành phần và phương pháp tính khác RSS.

Ví dụ:

```text
JVM heap used       : 500 MiB
JVM heap committed  : 700 MiB
Process RSS         : 950 MiB
Container working set: 1100 MiB
Container limit     : 1200 MiB
```

Số liệu này giả định. Nếu chỉ quan sát heap used = 500 MiB, rất dễ bỏ qua việc container đang gần memory limit.

### 9.4. Headroom

Một cách tư duy:

```text
Container memory limit
  -
memory consumption ở steady state/peak
  =
headroom cho spike, startup, GC, native allocation
```

Không nên dùng toàn bộ container limit làm `-Xmx` mà quên non-heap/native/OS overhead. Nếu runtime dùng `-XX:MaxRAMPercentage`, cần hiểu nó tương tác với container memory detection và những flags khác như thế nào.

## 10. Phân biệt tăng heap bình thường và memory leak

### 10.1. Heap tăng dạng răng cưa

Trong JVM có GC, một đồ thị thường trông như:

```text
Heap used
  ^
  |        /\        /\       /\
  |       /  \      /  \     /  \
  |      /    \    /    \   /    \
  |_____/      \__/      \_/      \____
  +------------------------------------> time
             GC        GC       GC
```

Đây có thể là behavior bình thường: object được cấp phát rồi thu hồi khi GC.

### 10.2. Đường sau-GC tăng liên tục

Một dấu hiệu đáng chú ý hơn:

```text
After-GC live set
  ^
  |                              __
  |                        _____/
  |                   ____/
  |              ____/
  |         ____/
  |________/
  +------------------------------------> time
```

Nếu **live set sau những chu kỳ GC tương đương** tăng qua nhiều giờ/ngày dưới workload tương tự và không ổn định ở mức mới, có thể có retained objects quá nhiều, cache không giới hạn hoặc leak.

Tuy nhiên, cùng hình dạng có thể xuất hiện khi:

- Cache đang warm-up đến kích thước mục tiêu.
- Traffic/concurrency tăng.
- Batch giữ dữ liệu hợp lệ lâu hơn.
- Một feature mới giữ state có chủ đích.
- GC collector hoặc heap ergonomics thay đổi.

Không tuyên bố memory leak chỉ từ một đường “heap used đi lên” trong 10 phút.

### 10.3. Những thông tin cần thu thập

- Heap used/committed/max theo thời gian.
- Old-generation occupancy hoặc live set khi có metrics phù hợp collector.
- Allocation rate và object types.
- Số instances, traffic, concurrency.
- Cache size/eviction metrics.
- Thread count và classloader count.
- Full GC hoặc concurrent cycle behavior.
- Heap dump/JFR allocation/retention analysis nếu cần.

### 10.4. Heap dump chứa dữ liệu nhạy cảm

Heap dump có thể chứa passwords, tokens, request objects và dữ liệu khách hàng. Khi bật dump:

```text
-XX:+HeapDumpOnOutOfMemoryError
-XX:HeapDumpPath=/secure-diagnostics
```

cần bảo đảm đủ dung lượng, quyền truy cập chặt, retention policy, encryption và quy trình xóa. Không tự động tải dump lên hệ thống ticket công cộng.

## 11. Native memory và container OOMKill

### 11.1. Heap không đầy nhưng pod vẫn bị kill

Một trường hợp:

```text
Heap used                 400 MiB / max 768 MiB
Metaspace                  130 MiB
Direct buffers             250 MiB
Thread stacks/native       220 MiB
Other runtime/native       180 MiB
Container limit           1400 MiB
```

Các số minh họa không đại diện quy tắc cộng chính xác, vì metrics có thể overlap. Nhưng chúng cho thấy native/non-heap có thể làm tổng memory vượt container limit trước khi heap chạm `-Xmx`.

Container OOMKill thường không tạo Java `OutOfMemoryError` với heap dump. Process có thể biến mất và container orchestrator báo reason `OOMKilled` hoặc exit code tương ứng, tùy môi trường.

### 11.2. Khi nào dùng Native Memory Tracking?

HotSpot Native Memory Tracking (NMT) có thể giúp phân loại memory do JVM quản lý. Một cấu hình startup thường gặp:

```shell
java -XX:NativeMemoryTracking=summary -jar app.jar
```

Sau đó, ở runtime hỗ trợ `jcmd` và attach:

```shell
jcmd <pid> VM.native_memory summary
```

Có thể dùng baseline/diff nếu phiên bản HotSpot hỗ trợ:

```shell
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff
```

NMT có overhead và **không nhất thiết theo dõi mọi allocation của third-party native libraries**. Nó không phải công cụ đo tổng process RSS thay thế OS metrics. Bật theo quy trình chẩn đoán có kiểm soát; cần cấu hình tại startup để thu dữ liệu phù hợp.

### 11.3. Thread count và stack memory

Mỗi platform thread cần stack và các cấu trúc native. Nếu ứng dụng tạo quá nhiều platform threads, native memory có thể tăng dù heap còn dư.

Theo dõi:

- Live platform threads.
- Thread creation rate.
- Thread pool size và queue length.
- Số worker idle/busy.
- Deadlocks hoặc thread contention.
- JVM thread stack settings nếu được thay đổi có chủ đích.

Với virtual threads, mô hình memory và scheduling khác platform threads. Không suy từ tổng số virtual threads rằng native stack memory tăng theo một tỷ lệ giống platform threads.

## 12. Garbage Collection: các khái niệm cần đo

### 12.1. GC không chỉ là “dọn rác”

GC quản lý vòng đời object trên heap. Các collector có thể thực hiện công việc:

- Concurrent cùng application threads.
- Stop-the-world (STW) khi các application threads bị tạm dừng.
- Young-generation collections.
- Mixed/old-generation collections hoặc những pha tương ứng collector.
- Compaction, marking, relocation, remembered-set maintenance.

Tên pha và hành vi khác nhau theo G1, Parallel GC, ZGC, Shenandoah và các collector/version cụ thể. Không áp tên “young/full GC” của một collector vào collector khác mà không hiểu log.

### 12.2. Chỉ số GC quan trọng

| Chỉ số | Ý nghĩa | Điều cần tránh |
|---|---|---|
| GC pause duration | Thời gian một pause/event ảnh hưởng tiến trình | Chỉ nhìn trung bình, bỏ p99 |
| GC pause count/rate | Tần suất pauses | Coi count tăng tự động là lỗi |
| GC time ratio | Tỷ lệ thời gian JVM dành cho hoạt động GC theo định nghĩa metric | Nhầm với toàn bộ CPU dùng cho GC |
| Allocation rate | Byte object được cấp phát mỗi giây | Chỉ nhìn heap used |
| Reclaimed bytes | Dữ liệu được thu hồi theo event/collector | So tuyệt đối giữa tải khác |
| Old/live set trend | Dữ liệu tồn tại lâu, nguy cơ heap pressure | Kết luận leak chỉ từ một đoạn ngắn |
| Concurrent cycle duration | Pha chạy cùng application | Đánh đồng với STW pause |
| Full/degenerate collections | Tín hiệu áp lực hoặc path đặc biệt tùy collector | So sánh thô giữa collectors |
| Safepoint pause/time-to-safepoint | JVM synchronization outside/around GC | Quy mọi safepoint vào GC |

### 12.3. Tần suất GC tăng không luôn xấu

Ví dụ thay collector có thể tạo nhiều pause rất ngắn thay cho vài pause dài. Khi đó `GC count` tăng, nhưng tail latency tốt hơn.

Ngược lại, số GC events giảm nhưng mỗi pause dài hơn, làm p99 xấu. Cần xem **phân phối pause duration, total GC overhead và ảnh hưởng ứng dụng**, không đánh giá dựa vào một con số.

### 12.4. Một số thay đổi khi nâng JDK

- Phiên bản GC implementation và ergonomics có thể thay đổi.
- Heap sizing và cgroup detection có thể khác.
- Default flags hoặc option support thay đổi.
- Một số collectors có cách báo metrics/log events khác nhau.
- Virtual threads, allocation pattern hoặc framework object graph có thể đổi.
- Agent và profiler có thể làm thay đổi overhead.

Trước khi so GC, ghi exact collector và các startup flags. Nếu bạn đồng thời thay collector từ G1 sang một collector khác, đó là một **thử nghiệm hiệu năng riêng** cần được phân tích như một biến độc lập.

## 13. Đọc GC pause và liên hệ với request latency

### 13.1. Tư duy timestamp correlation

Giả sử:

```text
12:00:10.100 Request bắt đầu
12:00:10.220 GC pause bắt đầu
12:00:10.460 GC pause kết thúc
12:00:10.570 Request kết thúc
```

Request mất 470 ms và trùng một pause 240 ms. Điều này là bằng chứng để điều tra GC contribution, nhưng không chứng minh toàn bộ 470 ms do GC: request có thể chờ DB/network thêm thời gian.

### 13.2. Đồng bộ clock và đơn vị đo

GC log thường có timestamp, uptime hoặc cả hai tùy cấu hình. Trace/log ứng dụng có timestamps của hệ thống khác. Muốn correlate:

- Đồng bộ clock giữa instances và log collector.
- Ghi timezone thống nhất, ưu tiên UTC trong pipeline.
- Biết metrics là seconds, milliseconds hay nanoseconds.
- Phân biệt wall-clock duration với CPU time.
- Ghi deploy marker và pod restart để tránh nối nhầm khoảng uptime.

Đặc biệt khi container khởi động lại, JVM uptime reset; không so hai dòng uptime khác process như cùng một timeline.

### 13.3. GC không giải thích mọi STW pause

Một số safepoints khác có thể tạm dừng threads. Nếu ứng dụng có tail latency spike mà GC pause thấp, xem safepoint logs, thread contention, CPU throttling, lock wait và downstream traces.

Chỉ bật tracing/diagnostics đủ chi tiết theo nhu cầu; log mỗi class load hoặc mọi allocation trong production có thể tạo overhead lớn.

## 14. Bật GC logging trên JDK hiện đại

### 14.1. Unified logging từ JDK 9+

Trên HotSpot JDK 9+ có thể dùng:

```shell
java \
  -Xlog:gc*,safepoint:file=/var/log/app/gc.log:time,uptime,level,tags:filecount=5,filesize=20m \
  -jar application.jar
```

Ý tưởng của ví dụ:

- Ghi nhóm GC và safepoint events.
- Có timestamp và uptime.
- Ghi file theo đường dẫn được cấu hình.
- Rotation bằng số file và kích thước mỗi file.

Đường dẫn phải có quyền ghi, dung lượng và retention policy phù hợp; cú pháp/nhãn logging phụ thuộc JVM version và implementation. Với container, có thể chọn stdout hoặc file volume theo chính sách logging.

### 14.2. JDK 8 dùng cú pháp khác

Một ví dụ HotSpot JDK 8 truyền thống:

```shell
java \
  -XX:+PrintGCDetails \
  -XX:+PrintGCDateStamps \
  -Xloggc:gc.log \
  -jar application.jar
```

Không sao chép các flags JDK 8 này vào JDK 21 mà không kiểm tra: Java unified logging đã thay đổi cơ chế và một số flags cũ không còn phù hợp.

### 14.3. Chọn log level cân bằng

Log GC quá chi tiết có thể:

- Tăng I/O và dung lượng.
- Tạo áp lực log collector.
- Làm khó tìm sự kiện quan trọng.
- Thêm overhead trong những workload nhạy cảm.

Nên bắt đầu với mức đủ quan sát collection events, pause durations và heap transitions; chỉ bật trace/debug sâu khi có giả thuyết điều tra. Cần có rotation và giới hạn retention.

### 14.4. GC log parser phải hiểu collector và version

Không viết parser dựa vào một chuỗi tiếng Anh cố định từ JDK 8 rồi dùng cho mọi JDK mới. Định dạng unified logging và event names có thể khác.

Chọn parser hỗ trợ JDK/collector/version đang chạy hoặc sử dụng JMX/Micrometer/JFR events với semantic conventions đã được kiểm tra.

## 15. Các công cụ chẩn đoán JVM

### 15.1. jcmd

Nếu runtime có công cụ và cơ chế serviceability phù hợp:

```shell
jcmd <pid> VM.version
jcmd <pid> VM.flags
jcmd <pid> GC.heap_info
jcmd <pid> Thread.print
```

Thay `<pid>` bằng PID thực tế. Các lệnh được hỗ trợ có thể khác theo JDK/vendor hoặc tùy custom runtime image. `jcmd` thường cần quyền OS tương ứng và cơ chế attach.

Không coi việc một container thiếu `jcmd` là bằng chứng JVM không thể cung cấp diagnostics; có thể dùng JFR startup, agent hoặc công cụ vận hành phù hợp khác.

### 15.2. jstat

Trong JDK có `jstat`, một lệnh có thể là:

```shell
jstat -gcutil <pid> 1000 10
```

Mẫu này lấy nhiều snapshot GC utilization theo interval. Output và các cột phụ thuộc JDK/collector; không viết hệ thống alert production dựa vào một cột mà chưa xác minh semantics ở JDK mục tiêu.

### 15.3. Java Flight Recorder (JFR)

JFR giúp thu thập các JVM và application events liên quan:

- GC pauses và allocation.
- CPU/thread samples.
- File/socket I/O.
- Locks/monitor contention.
- Exceptions trong phạm vi được cấu hình.
- Class loading và runtime state.

Một cách bật recording lúc startup trên HotSpot JDK phù hợp:

```shell
java \
  -XX:StartFlightRecording=filename=/secure-diagnostics/service.jfr,settings=profile \
  -jar application.jar
```

Hoặc qua `jcmd` khi runtime cho phép:

```shell
jcmd <pid> JFR.start name=migration settings=profile duration=5m filename=/secure-diagnostics/migration.jfr
```

`settings=profile` thường thu chi tiết hơn `default` và có overhead; các tùy chọn phải được kiểm tra theo JDK cụ thể. File JFR có thể chứa thông tin nhạy cảm về threads, paths, network và stack traces; cần bảo vệ tương tự các diagnostic artifacts khác.

### 15.4. Java Mission Control (JMC) và các công cụ phân tích

JFR recordings có thể được mở bằng công cụ phân tích tương thích như Java Mission Control để xem hotspot, thread states, allocation và GC events.

Mục tiêu là dùng recording để **kiểm tra giả thuyết**. Ví dụ nếu p99 tăng, hãy xem có lock contention hoặc allocation spike trùng thời gian không, thay vì chỉ bật profiler rồi suy từ một biểu đồ tổng.

### 15.5. Heap dumps

Heap dump hữu ích khi nghi ngờ retained objects/leak, nhưng:

- Có thể rất lớn.
- Có thể tạm dừng ứng dụng hoặc tác động resource tùy phương pháp.
- Có thể chứa dữ liệu nhạy cảm.
- Cần quyền, nơi lưu và kế hoạch xóa.
- Có thể làm container hết disk space.

Chỉ thu theo quy trình được phê duyệt, phù hợp mức nghiêm trọng và privacy/security policy.

## 16. Metrics của Micrometer/OpenTelemetry/JMX

### 16.1. Phân biệt metric name và ý nghĩa

Các hệ thường cung cấp JVM metrics như:

```text
jvm_memory_used_bytes
jvm_memory_committed_bytes
jvm_memory_max_bytes
jvm_gc_pause_seconds_count
jvm_gc_pause_seconds_sum
jvm_threads_live_threads
process_cpu_usage
```

Các tên này là ví dụ thường gặp ở một số hệ instrumentation, **không phải schema bắt buộc cho mọi exporter**. Phải đọc labels và units thực tế trước khi tính toán.

### 16.2. Heap theo pool

Nếu metric `jvm_memory_used_bytes` có label `area` với giá trị `heap`:

```promql
sum by (instance) (
  jvm_memory_used_bytes{
    application="order-service",
    area="heap"
  }
)
```

Khi xem committed/max, phải hiểu một số memory pool có `max` không xác định hoặc metric khác nhau theo collector. Không tính “% heap” một cách máy móc nếu mẫu số không hợp lệ.

### 16.3. GC pause time rate

Nếu exporter có tổng pause time dưới dạng counter `jvm_gc_pause_seconds_sum`, một query minh họa:

```promql
sum by (instance) (
  rate(jvm_gc_pause_seconds_sum{
    application="order-service"
  }[5m])
)
```

Giá trị có đơn vị **giây pause / giây thời gian quan sát** theo cách exporter tính; nó không nhất thiết là chính xác “% CPU JVM dùng cho GC”. Với concurrent collectors, cần phân biệt STW pause events và concurrent CPU activity.

### 16.4. GC pause count rate

```promql
sum by (instance) (
  rate(jvm_gc_pause_seconds_count{
    application="order-service"
  }[5m])
)
```

Phải xem exporter đếm loại GC events nào và các labels như action/cause. Count tăng có thể hợp lý nếu pause ngắn hơn; cần xem cùng duration distribution và workload.

### 16.5. Container memory

Nếu hạ tầng công bố container memory metrics, có thể so memory usage/working set với limit và restarts/OOMKilled. Nhưng tên cAdvisor/Kubernetes metrics và định nghĩa working set khác nhau theo hệ thống.

Một dashboard đáng tin cậy cần ghi **nguồn của từng chỉ số**, đừng trộn process RSS, heap committed và cgroup memory thành ba cách viết của cùng một đại lượng.

## 17. Theo dõi GC sau khi đổi collector

### 17.1. Không có collector nào tốt nhất cho mọi workload

Các lựa chọn GC có các trade-offs khác nhau:

- Throughput.
- Tail latency.
- CPU overhead.
- Memory overhead.
- Heap size và allocation behavior.
- Pause predictability.
- Container constraints.
- Runtime/JDK vendor support.

Không nên mặc định đổi sang một collector “low latency” là luôn giảm tổng resource usage. Một collector có thể giảm STW pauses nhưng tăng concurrent CPU hoặc memory overhead.

### 17.2. Thử nghiệm tách biến

Nếu migration đổi cả JDK và GC collector, nên có ma trận khi khả thi:

```text
A: JDK cũ + collector cũ
B: JDK mới + collector cũ (nếu hỗ trợ)
C: JDK mới + collector mới
```

So B với A giúp nhìn thay đổi JVM/JDK; so C với B giúp nhìn tác động collector. Dù vậy, vẫn có các phiên bản GC implementation khác nhau giữa JDK releases, nên kết quả chỉ hỗ trợ suy luận trong điều kiện thử nghiệm đã kiểm soát.

### 17.3. Dữ liệu cần so

- p95/p99 GC pause theo workload.
- Request p95/p99 và timeout.
- CPU usage và throttling.
- Memory footprint.
- Allocation rate/live set.
- GC time ratio và throughput.
- Reclaim behavior.
- Startup/warm-up.
- Incidents full/degenerate/fallback collection nếu collector có khái niệm đó.

Đừng so riêng số lượng "Full GC" giữa collectors khác nhau và kết luận collector này tốt hơn collector kia.

### 17.4. Flags GC cần được ghi và kiểm chứng

Ví dụ HotSpot có flags lựa chọn collector theo release, nhưng hỗ trợ có thể thay đổi:

```text
-XX:+UseG1GC
-XX:+UseParallelGC
-XX:+UseZGC
```

Đây chỉ là ví dụ tên flags quen thuộc. Khi chọn collector, phải kiểm tra phiên bản/runtime cụ thể có hỗ trợ và cú pháp đúng; không copy một chuỗi flags cũ nguyên vẹn sang JDK 25 hoặc vendor khác.

## 18. GC, allocation rate và thiết kế ứng dụng

### 18.1. Allocation rate ảnh hưởng GC pressure

Một thay đổi serializer hoặc chuyển dữ liệu có thể tạo thêm nhiều object tạm:

```text
Request -> parse JSON -> DTOs -> transformations
                               -> temporary strings/lists
                               -> response serialization
```

Nếu allocation rate tăng mạnh, GC có thể phải làm nhiều công việc hơn dù live set không đổi. Ví dụ một API dùng object mapping mới có thể tốn thêm CPU/GC mà unit tests vẫn pass.

### 18.2. Không “tối ưu” bằng giữ object lâu hơn một cách mù quáng

Một cách giảm allocations là cache kết quả. Nhưng cache không giới hạn có thể tăng live set và gây memory pressure. Cần đo:

- Cache hit ratio.
- Cache size/weight.
- TTL/eviction policy.
- Allocation giảm được bao nhiêu.
- Heap occupancy sau-GC tăng bao nhiêu.
- Thay đổi p95/p99 và memory headroom.

### 18.3. Thread locals và classloader leaks

Một số leak xuất hiện khi:

- Thread-local values không được dọn đúng.
- Executor giữ reference tới object dài hạn.
- Plugin/redeploy tạo classloader mới nhưng classloader cũ vẫn bị giữ.
- Static caches giữ data theo từng deployment.

Metaspace hoặc old-gen tăng có thể là tín hiệu. Phải xem object retention/root paths qua heap analysis, không chỉ tăng `-Xmx` để trì hoãn triệu chứng.

### 18.4. Virtual threads và GC

Nếu migration dùng virtual threads, có thể tạo nhiều concurrent tasks hơn và thay đổi allocation profile. Cần kiểm tra:

- Số tác vụ đồng thời.
- Scheduling/backpressure.
- Stack/continuation-related memory theo JVM version.
- Thread-local usage.
- Network/database pool limits.
- Allocation và GC pause behavior.

Không suy “virtual threads nhẹ” đồng nghĩa bộ nhớ luôn giảm trong mọi ứng dụng. Số lượng tasks và payload mỗi task vẫn quan trọng.

## 19. Canary release và so sánh bản cũ – mới

### 19.1. Vì sao canary hữu ích?

Canary cho một phần traffic chạy phiên bản mới trong khi phần còn lại vẫn chạy bản trước:

```text
                 Production requests
                        |
               +--------+--------+
               |                 |
               v                 v
        Stable JDK 17       Canary JDK 21
         Release A           Release B
               |                 |
               +--------+--------+
                        |
                Compare metrics
                        |
             Promote / hold / rollback
```

Đối chiếu đồng thời giúp giảm ảnh hưởng của biến động theo thời điểm. Tuy nhiên, traffic routing có thể khiến canary nhận mix khác stable, nên cần kiểm tra cách phân chia requests.

### 19.2. Các giai đoạn tăng traffic

Một lộ trình minh họa:

```text
0% -> 5% -> 20% -> 50% -> 100%
```

Các tỷ lệ không phải tiêu chuẩn bắt buộc. Với dịch vụ ít traffic, 5% có thể không đủ samples để phát hiện lỗi hiếm. Với giao dịch cực kỳ quan trọng, nhóm có thể yêu cầu staging/load test và quan sát lâu hơn trước khi tăng phần trăm.

Mỗi gate phải dựa trên:

- SLO/error budget.
- Error count và sample size.
- p95/p99 theo route quan trọng.
- Heap/native/container headroom.
- GC pauses và allocation.
- Restart/OOMKilled/crash count.
- Downstream dependency behavior.
- Tính năng được canary thực sự sử dụng.

### 19.3. Đừng so canary mới 2 phút với stable 2 tuần

JVM có warm-up, JIT compilation, cache fill, connection pool establishment và traffic routing khác nhau. So sánh cần xét thời gian hoạt động và workload tương đương.

Có thể theo dõi cả:

- Cold-start behavior.
- Warmed steady-state behavior.
- Peak-load behavior.
- Long-running memory behavior.

Một bản tăng nhanh sau 2 phút chưa đủ kết luận không có leak sau 24 giờ. Một bản p99 xấu lúc cold start không nhất thiết tệ khi steady-state, nhưng nếu sản phẩm yêu cầu startup nhanh thì cold start vẫn là một SLI quan trọng.

### 19.4. Canary cần nhãn version đúng

Các series hoặc traces phải phân biệt:

```text
service.name
deployment.environment
service.version
jdk.version
container.image.digest
instance/pod identifier
```

Không dùng những label có cardinality không kiểm soát. Với tracing, release/JDK có thể đặt trong resource attributes thay vì lặp trong mọi log message theo cách tăng chi phí lớn.

## 20. Ngưỡng cảnh báo và điều kiện dừng rollout

### 20.1. Alert theo tác động, không theo từng dao động nhỏ

Một alert tốt cần trả lời:

- Người dùng có bị ảnh hưởng không?
- Ảnh hưởng nghiêm trọng đến mức nào?
- Tình trạng kéo dài hay chỉ một spike?
- Có đủ samples để kết luận không?
- Người trực có hành động rõ ràng nào không?

Những metrics như GC count hay heap used nên là diagnostic signals hoặc guardrails; không nhất thiết tạo pager alert chỉ vì chúng vượt một giá trị chưa xác minh.

### 20.2. Hai lớp cảnh báo

**Lớp 1 — User-facing SLI:** error rate, latency SLO violations, availability, job lag.

**Lớp 2 — JVM/resource early warning:** heap/container pressure, pause spikes, CPU throttling, abnormal restarts, threads/queue saturation.

Lớp 2 giúp giải thích và phòng ngừa, nhưng không tự thay thế lớp 1.

### 20.3. Ví dụ guardrails mang tính giả định

| Chỉ số | Ví dụ chính sách | Hành động |
|---|---|---|
| Error rate | Vượt baseline đủ lớn và kéo dài qua các cửa sổ | Hold/pause rollout |
| p99 route trọng yếu | Vượt SLO hoặc ngưỡng regression đã duyệt | Điều tra traces/GC/downstream |
| Container memory | Headroom thấp liên tục hoặc có OOMKilled | Dừng tăng traffic |
| GC pauses | Tăng tail pauses cùng với latency impact | Đối chiếu GC logs/JFR |
| Crash loops | Xuất hiện ở nhiều canary instances | Rollback theo runbook |
| Message lag | Không còn theo kịp producer | Giảm traffic hoặc rollback |
| Sample count | Quá thấp | Chưa promote do chưa đủ bằng chứng |

Không lấy các ví dụ này làm ngưỡng cụ thể. Có dịch vụ cần alert trong vài giây; dịch vụ batch có thể đánh giá theo giờ hoặc theo toàn bộ job.

### 20.4. Error-budget burn rate

Nếu có SLO, có thể theo dõi tốc độ tiêu thụ error budget qua những cửa sổ ngắn và dài. Fast burn cảnh báo sự cố nghiêm trọng; slow burn phát hiện regression nhỏ kéo dài.

Nhưng burn-rate alert chỉ đáng tin khi SLI/denominator được định nghĩa đúng. Nếu hệ thống có gần như không traffic, tỷ lệ phần trăm đơn lẻ có thể rất nhiễu.

## 21. Quyết định rollback: cần bằng chứng đủ nhưng không trì hoãn quá mức

### 21.1. Các nguyên nhân có thể yêu cầu rollback nhanh

- Crash loop do dependency/bytecode/classloading.
- Error rate tăng gây mất khả năng phục vụ.
- p99/timeout vi phạm SLO nghiêm trọng.
- OOMKilled lặp lại hoặc memory không có headroom.
- GC pauses dài tác động tới nghiệp vụ.
- Data corruption hoặc protocol incompatibility.
- Security regression quan trọng.
- Không còn khả năng quan sát/chẩn đoán production an toàn.

Các quyết định cần có owner và quyền điều phối rõ ràng. Khi tác động nghiêm trọng đã được xác nhận, không cần chờ tìm ra nguyên nhân GC hay library chính xác mới khôi phục bản ổn định, nếu rollback là phương án an toàn.

### 21.2. Rollback cả app và runtime/dependency

```text
Release A:
  application.jar A
  JDK 17 runtime
  dependency graph A
  agent version A

Release B:
  application.jar B
  JDK 21 runtime
  dependency graph B
  agent version B
```

Nếu chỉ rollback application JAR mà giữ runtime/dependency graph của B, có thể không khôi phục trạng thái đã kiểm thử. Với OCI image, dùng image digest của release đã biết tốt; với bundle, dùng artifact checksum và runtime kèm theo.

### 21.3. Data schema là điều kiện rollback độc lập

Rollback executable không đảo ngược database schema hoặc events đã được producer mới ghi. Cần kiểm tra backward compatibility của dữ liệu, expand/contract migrations và status của consumers trước khi rollback.

### 21.4. Không làm mất dữ liệu khi canary

Nếu canary ghi vào cùng database hoặc publish messages, rollback code phải xem:

- Idempotency/retry.
- Schema compatibility.
- Queue backlog.
- Dữ liệu chưa hoàn thành.
- Side effects của request.
- Job checkpoint/progress.

Một canary có thể nhỏ về traffic nhưng vẫn tạo side effects quan trọng.

## 22. Phân tích một ví dụ: p99 tăng sau nâng JDK

### 22.1. Tín hiệu ban đầu

Giả sử dashboard cho thấy:

```text
Old release:
  p99 = 250 ms
  error rate = 0.1%
  GC pause p99 = 35 ms

New canary:
  p99 = 570 ms
  error rate = 0.2%
  GC pause p99 = 40 ms
```

Dữ liệu giả định. Dù GC pause p99 tăng nhẹ, không có cơ sở cho rằng GC một mình giải thích chênh lệch request p99 320 ms.

### 22.2. Quy trình điều tra

1. Kiểm tra canary nhận request mix và tải tương đương stable không.
2. Phân loại route nào có p99 tăng.
3. Mở traces của các request chậm.
4. Xem thời gian DB, HTTP downstream, queue và lock contention.
5. Kiểm tra CPU throttling và thread pool saturation.
6. Correlate timestamps với GC/safepoint events.
7. Kiểm tra allocation rate nếu code/framework thay đổi.
8. Thử tái hiện trên staging/load test.
9. Tách tác động JDK khỏi thay đổi framework/agent nếu có thể.
10. Hold/rollback theo SLO và mức rủi ro.

### 22.3. Một số kết luận khả dĩ

- DB connection pool hết kết nối: không phải GC root cause.
- JIT warm-up chậm: cần đo cold vs steady-state.
- Serializer mới tạo nhiều object: allocation tăng, GC pressure là hệ quả.
- CPU limit bị giảm ở container mới: throttling làm p99 tăng.
- Agent mới instrument nhiều methods: tracing overhead tăng.
- GC collector mới có tail behavior khác: cần benchmark và GC diagnostics.

Đây là các **giả thuyết cần chứng minh**, không phải kết luận từ một bảng số liệu.

## 23. Phân tích ví dụ: heap ổn nhưng pod OOMKilled

### 23.1. Tình huống

```text
Heap used          350 MiB
Heap max           700 MiB
Process RSS       1200 MiB
Container limit   1280 MiB
Pod restart        OOMKilled
```

Khi nhìn heap used, tưởng JVM còn nhiều bộ nhớ. Nhưng RSS gần container limit.

### 23.2. Các bước

1. Xác minh exit reason và thời điểm OOMKill.
2. Kiểm tra heap used, committed/max và container working set.
3. Xem direct buffer metrics, thread counts, metaspace, classloaders.
4. Xem native/JNI allocations nếu có.
5. Kiểm tra JVM flags liên quan memory sizing.
6. Bật NMT ở một môi trường phù hợp nếu cần.
7. Xem có tăng traffic, threads hoặc buffers sau release không.
8. So lại container limits/base image.
9. Chọn sửa leak/giảm allocation/điều chỉnh memory limits theo bằng chứng.
10. Test peak load và giữ headroom.

Không đơn thuần tăng `-Xmx`: điều đó có thể làm container OOMKill **sớm hơn** nếu tổng memory bị giới hạn.

## 24. Phân tích ví dụ: GC count tăng nhưng latency tốt hơn

Giả sử:

| Chỉ số | Bản A | Bản B |
|---|---:|---:|
| GC pauses/minute | 4 | 20 |
| GC pause p99 | 180 ms | 16 ms |
| HTTP p99 | 400 ms | 260 ms |
| CPU | 60% | 68% |
| Container RSS | 800 MiB | 850 MiB |

Dữ liệu giả định. Số pause tăng **không tự động là regression** vì p99 GC pause và request latency giảm. Nhưng CPU/RSS tăng, cần đánh giá trade-off với resource budget và capacity.

Nếu bản B làm latency tốt nhưng chi phí compute tăng quá mức, quyết định phụ thuộc SLO và nhu cầu tài chính/vận hành. Không xếp hạng GC collectors chỉ bằng một metric.

## 25. Theo dõi startup, shutdown và restarts

### 25.1. Startup time

Sau nâng JDK/framework, đo:

- Thời gian từ process start đến readiness.
- Class loading và dependency initialization.
- JIT/warm-up cần cho các request đầu tiên.
- Database connection initialization.
- TLS/credential initialization.
- Thời gian build cache/restore state.

Startup lâu hơn có thể ảnh hưởng autoscaling và rolling deploy, dù steady-state p99 tốt.

### 25.2. Readiness khác liveness

Nếu readiness được đánh dấu quá sớm, load balancer có thể chuyển request tới JVM còn warm-up hoặc chưa kết nối backend. Điều này làm canary error/latency tăng không nhất thiết do GC.

Liveness probe nên xác định process bị kẹt/ngừng hoạt động, còn readiness phải phản ánh khả năng nhận traffic theo thiết kế. Đặt thresholds phù hợp và tránh restart loop do startup chậm.

### 25.3. Graceful shutdown

JDK/framework/executor changes có thể tác động tới:

- Thời gian hoàn tất in-flight requests.
- Message acknowledgement/rebalancing.
- Thread pool shutdown.
- JFR/telemetry flush.
- Connection teardown.
- Queue draining.

Một release có p99 đẹp nhưng làm mất message khi pod bị thay thế vẫn là không đạt.

### 25.4. Restart counter phải có nguyên nhân

Phân loại:

- Rolling deployment do release.
- Liveness probe kill.
- Process crash.
- Container OOMKilled.
- Node eviction.
- Manual restart.
- Native JVM crash.
- External kill signal.

Không coi tổng restart count tăng trong lúc rollout là sự cố nếu nó chỉ phản ánh replacement đúng kế hoạch. Cần tách các restarts bất thường.

## 26. Điều kiện dữ liệu để ra quyết định đáng tin

### 26.1. Sample size và statistical noise

Với canary 1% traffic, một route hiếm có thể chỉ có vài request. Percentile hoặc error ratio từ mẫu nhỏ dễ biến động.

Ví dụ:

```text
Canary có 5 request, 1 request lỗi -> 20% error rate
Canary có 100,000 request, 100 lỗi -> 0.1% error rate
```

Hai tỷ lệ không có cùng độ chắc chắn. Không được promote chỉ vì canary ít lỗi **khi nó gần như chưa được gọi**.

### 26.2. Traffic có thể không phân phối ngẫu nhiên

Một số gateway route theo user/session/region. Canary có thể nhận:

- Nhiều user ở một quốc gia.
- Payload lớn hơn.
- Tenant đặc thù.
- Cụm database khác.
- Traffic từ một mobile app version.
- Những request có cache hit ratio thấp.

Muốn so old/new, phải xét phân phối workload và có thể phân tầng kết quả theo route/region/tenant segment đã được ẩn danh phù hợp.

### 26.3. Seasonality và long-running issues

Một canary vượt 30 phút thử nghiệm không phát hiện mọi leak hoặc batch issue. Có thể cần soak test/staging chạy lâu hoặc canary dài hơn nếu rủi ro thuộc memory growth, timezone schedules hoặc periodic jobs.

### 26.4. Không gộp p99 từ nhiều windows bằng average

Một giá trị p99 được tính cho 5 phút không thể được bình quân với p99 của các khoảng khác và coi là p99 toàn ngày. Muốn aggregate đúng, dùng distribution/histogram dữ liệu phù hợp hoặc tính lại từ raw samples khi khả thi.

## 27. Cơ chế theo dõi sau phát hành theo giai đoạn

### Giai đoạn 1: Trước phát hành

- Xác định baseline và acceptance criteria.
- Kiểm tra instrumentation của ứng dụng/JVM.
- Chuẩn bị dashboard có nhãn release/JDK.
- Xác minh trace/log correlation.
- Lưu resolved dependencies và runtime flags.
- Kiểm tra GC logging/JFR/NMT policy nếu cần.
- Chuẩn bị rollback và owners.
- Kiểm tra staging load/soak tests.
- Xác định những nghiệp vụ phải được canary gọi tới.

### Giai đoạn 2: Canary nhỏ

- Xác nhận phiên bản và runtime thật.
- Kiểm tra không có startup/linkage errors.
- Xem error rate và response codes.
- So p95/p99 theo route.
- Xem heap, process RSS, container headroom.
- Xem GC pause/CPU/throttling.
- Kiểm tra trace/telemetry exporter.
- Hold nếu sample chưa đủ hoặc có blocker.

### Giai đoạn 3: Tăng traffic có kiểm soát

- So old/new ở tải tương đương.
- Kiểm tra downstream dependency saturation.
- Theo dõi allocation và long-lived memory.
- Quan sát retry storms và queue lag.
- Đánh giá SLO burn rate.
- Kiểm tra scaling/restarts.
- Ghi nhận từng quyết định promote hoặc hold.

### Giai đoạn 4: Full rollout

- Xác minh mọi instance chạy release mong muốn.
- Theo dõi các nhóm traffic không từng đi qua canary.
- Quan sát peak/off-peak và scheduled jobs.
- Không xóa baseline/old dashboard ngay.
- Giữ rollback artifacts.
- Cập nhật runbook và incident notes.

### Giai đoạn 5: Sau ổn định

- Đánh giá memory/GC trend theo chu kỳ dài.
- So chi phí CPU/RAM và hiệu năng.
- Xem incidents/alerts phát sinh.
- Chốt migration report và những vấn đề còn lại.
- Giảm diagnostic logging tạm thời nếu an toàn.
- Giữ monitoring thường trực theo SLO.

## 28. Runbook khi phát hiện lỗi hoặc regression

### 28.1. Triage đầu tiên

```text
Alert đến
    |
    v
Xác nhận customer impact / SLO
    |
    +-- Nghiêm trọng --> containment/rollback theo runbook
    |
    v
So stable và canary
    |
    v
Phân loại: error / latency / memory / GC / infra
    |
    v
Tìm release change + instance + trace
    |
    v
Thu thập bằng chứng có giới hạn
    |
    v
Sửa, thử lại, quyết định rollout
```

### 28.2. Khi error rate tăng

- Xem exception/status distribution.
- Kiểm tra lỗi chỉ xảy ra ở endpoint nào.
- Tìm `NoSuchMethodError`/`IllegalAccessError`/TLS/JDBC.
- So dependency graph, JDK version, app config.
- Kiểm tra rollout version và classloader/image digest.
- Tạm dừng rollout hoặc rollback khi người dùng bị ảnh hưởng rõ.

### 28.3. Khi latency tăng

- So percentile theo operation dưới tải tương đương.
- Phân tích traces.
- Kiểm tra dependency latency và queue.
- Xem CPU saturation/throttling.
- Correlate GC/safepoint events.
- Dùng JFR/thread dumps nếu vẫn chưa rõ.

### 28.4. Khi memory tăng

- Phân biệt heap used, live set, committed, native, RSS.
- Xem traffic/concurrency/cache/threads.
- Kiểm tra GC có reclaim bình thường không.
- Xem OOMKilled vs Java OOME.
- Thu heap dump/JFR/NMT có kiểm soát nếu cần.
- Điều chỉnh app/limits dựa trên root cause, không chỉ tăng heap.

### 28.5. Khi GC pause tăng

- Xác nhận collector/JDK flags và workload.
- Phân tích distribution pause, GC time rate.
- Xem allocation, old-gen occupancy.
- Kiểm tra CPU/container throttling.
- So với app latency impact.
- Phân biệt warm-up, heap sizing và collector behavior.
- Thử cấu hình trong staging trước khi thay flags production.

## 29. Quyền riêng tư và chi phí observability

### 29.1. Tracing/logging có thể tạo dữ liệu nhạy cảm

Traces, exception logs, heap dumps và JFR recordings có thể chứa:

- URL/path và query parameters.
- Request headers.
- Tokens/credentials.
- Stack traces kèm nội dung nghiệp vụ.
- File paths nội bộ.
- User/tenant information.
- Object contents trong heap.

Nên áp dụng redaction, sampling, access control, retention và encryption phù hợp. Không tạo high-cardinality metrics dựa trên các định danh cá nhân.

### 29.2. Overhead của diagnostic tools

Các công cụ có mức overhead khác nhau:

| Công cụ | Mục đích | Lưu ý |
|---|---|---|
| JVM metrics/JMX | Monitoring thường trực | Overhead thường thấp khi cấu hình hợp lý |
| GC logging cơ bản | GC event history | I/O và retention |
| Detailed GC/safepoint logging | Debug chi tiết | Khối lượng log lớn |
| JFR default/profile | JVM events và sampling | Overhead tùy settings/volume |
| Allocation profiling sâu | Phân tích object churn | Có thể đáng kể |
| Heap dump | Retained object analysis | Dung lượng và độ nhạy dữ liệu cao |
| NMT | Native JVM memory categories | Phải bật từ startup, có overhead |
| Full classloading logs | Tìm JAR/class origin | Rất nhiều log |

Không bật tất cả chế độ debug ở production vô thời hạn. Bắt đầu với monitoring thiết yếu, chỉ tăng độ chi tiết khi có câu hỏi cần trả lời.

### 29.3. Chi phí telemetry

Metrics có cardinality cao, traces sampling quá lớn hoặc GC logs vô hạn có thể làm tăng chi phí và tạo gánh nặng I/O. Trong một migration, nên kiểm soát:

- Retention theo loại dữ liệu.
- Sampling policy.
- Số metric labels và time series.
- Storage quota.
- Log rotation.
- Diagnostic artifact lifecycle.

Một hệ thống observability không nên tự trở thành nguồn gây regression.

## 30. Những sai lầm cần tránh

**Chỉ nhìn CPU và heap rồi kết luận ứng dụng khỏe.** Người dùng có thể đang gặp lỗi/timeout nghiêm trọng dù resource còn dư.

**Chỉ nhìn average latency.** Tail p99 có thể xấu hơn rất nhiều khi average gần như không đổi.

**Xem mọi GC count increase là lỗi.** Pause duration và impact mới là các yếu tố quan trọng.

**Xem heap used tăng là memory leak.** Cần xem after-GC live set, workload, cache, allocation và thời gian dài hơn.

**Đánh đồng process RSS với heap used.** Native memory, direct buffers, thread stacks và container page cache làm chúng khác nhau.

**Đặt `-Xmx` bằng toàn bộ container limit.** Có thể gây OOMKill do non-heap/native overhead.

**Thay JVM flags khi chưa biết nguyên nhân.** Một thay đổi GC không kiểm chứng có thể làm latency hoặc resource costs xấu hơn.

**So hai bản dưới traffic khác nhau.** Không có cơ sở quy sai khác cho JDK.

**Tính p99 toàn service bằng trung bình p99 mỗi pod.** Percentile aggregation như vậy không đúng.

**Dùng success HTTP 200 để che application-level errors.** SLI phải phản ánh hợp đồng nghiệp vụ.

**Promote canary khi traffic gần bằng 0.** Chưa có đủ bằng chứng, đặc biệt với routes hiếm.

**Không gắn nhãn release/JDK trên metrics.** Không thể so stable/canary một cách chắc chắn.

**Chỉ kiểm tra startup.** Lỗi runtime có thể lộ khi một feature được dùng lần đầu.

**Dùng GC log của JDK 8 như định dạng chuẩn cho JDK 21.** Cần công cụ và flags đúng release.

**Không bảo vệ JFR/heap dump.** Diagnostic artifacts có thể chứa dữ liệu nhạy cảm.

**Rollback mỗi application.jar nhưng giữ runtime/dependencies mới.** Có thể không khôi phục môi trường đã được kiểm thử.

**Không quản lý security updates của JVM.** Một bản phát hành ổn định về hiệu năng vẫn phải được cập nhật khi có bản vá JDK.

## 31. Bài tập thực hành

### Bài tập 1: Đọc kết quả canary

Cho bảng giả định:

| Metric | Stable | Canary |
|---|---:|---:|
| Request rate | 200/s | 10/s |
| Error rate | 0.1% | 0.0% |
| p99 latency | 220 ms | 120 ms |
| Heap used | 500 MiB | 300 MiB |
| Uptime | 20 ngày | 3 phút |

Hãy giải thích vì sao chưa thể kết luận canary tốt hơn: sample size, cache warm-up, uptime, workload mix và phân bổ request.

### Bài tập 2: GC count tăng

Bản A có 4 pauses/phút, p99 pause 180 ms; bản B 20 pauses/phút, p99 pause 15 ms. HTTP p99 ở B thấp hơn nhưng CPU tăng.

Hãy đề xuất đánh giá theo SLO, throughput, CPU cost, live set và pauses thay vì chỉ đếm collections.

### Bài tập 3: Heap không đầy nhưng bị OOMKilled

Một container giới hạn 1 GiB, heap max 600 MiB và heap used 350 MiB; process RSS cao gần 1 GiB.

Hãy lập kế hoạch thu thập direct buffers, metaspace, thread stacks, JNI/native, cgroup metrics, NMT và sự kiện OOMKilled. Giải thích vì sao tăng `-Xmx` có thể nguy hiểm.

### Bài tập 4: Correlate p99 và GC

Một request kéo dài 700 ms; GC log cho thấy pause 120 ms nằm trong khoảng đó. Hãy đề xuất sử dụng tracing để tách server processing, DB/HTTP, queue wait, lock contention và GC contribution. Có thể kết luận toàn bộ 700 ms do GC không?

### Bài tập 5: Viết guardrails

Một dịch vụ có SLO success ratio 99.9%, request latency p99 dưới ngưỡng nghiệp vụ, và cần không có OOMKill.

Hãy thiết kế alerts có short/long windows, minimum traffic condition, cùng cách gắn error budget và canary promotion gates.

### Bài tập 6: Thiết kế dashboard

Thiết kế các panels cho HTTP API có JVM, gồm release/JDK metadata, error rate, route p95/p99, throughput, heap/non-heap, RSS/container memory, GC pause, CPU/throttling, threads, connection pools và restarts.

Nêu metrics nào phải được phân tách theo release version và những labels nào không nên dùng vì chứa dữ liệu cá nhân hoặc cardinality quá cao.

### Bài tập 7: Runbook rollback

Một canary Java 21 bắt đầu phát sinh `NoSuchMethodError` ở endpoint trả tiền, trong khi stable Java 17 vẫn chạy bình thường.

Hãy xác định điều kiện dừng rollout, cách lấy class/JAR origin, khi nào cần rollback và những rủi ro rollback dữ liệu cần kiểm tra.

## 32. Checklist theo dõi sau phát hành

### Trước release

- [ ] Có exact JDK vendor/version và runtime flags trước/sau.
- [ ] Có artifact/image digest và dependency graph để truy vết.
- [ ] Baseline error, latency, throughput, heap, RSS và GC được lưu.
- [ ] SLO và regression guardrails được xác định trước.
- [ ] Monitoring/tracing/logging đã kiểm tra trên staging.
- [ ] Dashboard phân biệt stable/canary theo version.
- [ ] Có test peak/cold-start và các chức năng trọng yếu.
- [ ] Có owner, kênh incident và rollback runbook.

### Trong canary

- [ ] Sample count và traffic mix đủ đại diện.
- [ ] Error rate và application-level failures được đo.
- [ ] p50/p95/p99 theo route, không chỉ average.
- [ ] CPU, throttling, queues và downstream latency được xem.
- [ ] Heap, non-heap, process RSS và container headroom được xem.
- [ ] GC pause distribution và allocation/live set được theo dõi.
- [ ] Restart/crash/OOMKill được phân loại nguyên nhân.
- [ ] Canary thực sự đã gọi những code paths quan trọng.
- [ ] Từng bước promote/hold có quyết định và bằng chứng.

### Sau full rollout

- [ ] Đã xác nhận mọi instance chạy đúng phiên bản.
- [ ] Theo dõi peak/off-peak và các job định kỳ.
- [ ] Quan sát memory growth qua thời gian đủ dài.
- [ ] Không còn warnings/linkage errors bất thường.
- [ ] Agent/JFR/serviceability vẫn hoạt động theo runbook.
- [ ] Log/JFR/heap-dump policies đáp ứng yêu cầu bảo mật.
- [ ] Artifact cũ vẫn có thể rollback theo chính sách.
- [ ] Data/schema rollback compatibility đã được xét.
- [ ] Dashboard và alerts được cập nhật để vận hành dài hạn.
- [ ] Báo cáo migration ghi rõ kết quả và những rủi ro còn lại.

## Kết luận

**Theo dõi lỗi, độ trễ, bộ nhớ và hành vi GC sau phát hành** là cách kiểm chứng Java migration trong điều kiện người dùng và hệ thống thật, không chỉ qua việc build thành công. Một bản JDK mới được xem là ổn định khi giữ được SLO, không xuất hiện regression nghiệp vụ, sử dụng tài nguyên trong headroom cho phép và có behavior GC phù hợp với workload.

Hãy xây baseline trước release, gắn rõ thông tin application/JDK vào telemetry, dùng canary để so phiên bản dưới tải có thể so sánh, đo cả tail latency và các lớp memory ngoài heap, rồi correlate GC/JFR/traces thay vì đoán nguyên nhân từ một metric riêng. Khi rủi ro vượt ngưỡng, có rollback đã chuẩn bị; khi mọi tín hiệu đạt tiêu chí qua chu kỳ quan sát phù hợp, có thể tăng traffic và hoàn tất migration với bằng chứng cụ thể. Đây là kỷ luật vận hành giúp thay đổi JDK trở thành một quyết định có thể đo lường, giải thích và kiểm soát.

