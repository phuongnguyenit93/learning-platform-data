# Dashboard saturation

Một Spring Boot service có CPU trung bình 55% và request rate vẫn ổn định, nhưng p99 latency tăng nhanh. Nguyên nhân có thể là connection pool gần cạn, executor queue tích tụ hoặc thread phải chờ lock. Chỉ nhìn CPU không cho biết service còn bao nhiêu capacity để nhận thêm traffic. Saturation dashboard giúp quan sát mức sử dụng tài nguyên, lượng công việc đang chờ và lỗi phát sinh khi hệ thống tiến gần giới hạn.

Bài **Dashboard saturation** thuộc chương **Dashboard và alert** của module **SPRING_BOOT_OBSERVABILITY**. Module học cách thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; hiểu context propagation, tag/cardinality, exporter, sampling và liên kết các tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trong môi trường thực.

> **Nguyên tắc:** Một saturation dashboard phải trả lời ba câu hỏi: tài nguyên nào đang được sử dụng, công việc nào đang chờ, và hệ thống đã bắt đầu từ chối hoặc làm chậm request chưa. Dùng mô hình USE (Utilization, Saturation, Errors) cho từng resource; kết hợp latency/throughput ở tầng ứng dụng để thấy tác động tới người dùng. Không dùng một ngưỡng CPU duy nhất làm đại diện cho mọi dạng saturation.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:
1. Giải thích saturation và phân biệt nó với utilization.
2. Áp dụng phương pháp USE cho resource trong Spring Boot.
3. Chọn metrics cho CPU, memory, threads, executor, connection pools và queues.
4. Đọc backlog, pending tasks, pool wait và resource exhaustion.
5. Thiết kế dashboard kết hợp saturation với request rate, errors và latency.
6. Phân biệt capacity shortage với downstream dependency chậm.
7. Chọn aggregation, time window và thresholds phù hợp.
8. Tránh dashboard gây hiểu nhầm do average che khuất spikes hoặc do cardinality cao.
9. Thiết kế alerts theo symptom và saturation signals.
10. Xây dựng playbook điều tra và kiểm chứng dashboard bằng tải thử.

## 2. Saturation là gì?

Saturation mô tả mức độ một resource hoặc subsystem bị quá tải so với khả năng phục vụ công việc hiện tại. Utilization cho biết resource đang bận bao nhiêu; saturation cho biết có bao nhiêu công việc phải chờ hoặc bị từ chối vì resource không đáp ứng kịp.

Ví dụ:
- CPU utilization 95% cho thấy CPU gần như luôn bận; run queue cao cho thấy runnable threads còn phải chờ CPU.
- Connection pool active đạt max và pending tăng cho thấy request phải đợi connection.
- Executor queue tăng cho thấy task đến nhanh hơn tốc độ worker xử lý.
- Heap occupancy cao chưa chắc đã saturation; allocation pressure, GC pauses và memory limit gần chạm có thể gây latency hoặc OOM.

### 2.1 USE method

USE là cách rà soát từng resource:

| Thành phần | Câu hỏi | Ví dụ |
|---|---|---|
| Utilization | Resource bận bao nhiêu phần trăm/thời gian? | CPU usage, pool active/max |
| Saturation | Bao nhiêu công việc đang chờ hoặc bị xếp hàng? | CPU run queue, executor queue, pool pending |
| Errors | Có lỗi do resource không đáp ứng không? | Rejected tasks, acquisition timeout, OOM |

Không phải mọi resource đều có đủ ba metric. Nếu không có queue metric, tìm proxy phù hợp hoặc instrument thêm. Đừng suy ra saturation chỉ từ utilization.

~~~mermaid
flowchart TD
    A["Resource"] --> B["Utilization"]
    A --> C["Saturation"]
    A --> D["Errors"]
    B --> E["Resource đang bận?"]
    C --> F["Công việc có phải chờ?"]
    D --> G["Có bị reject/fail?"]
    E --> H["Liên hệ với latency và throughput"]
    F --> H
    G --> H
~~~

## 3. Saturation ở tầng ứng dụng

Dashboard nên bắt đầu bằng impact của service rồi mới đi sâu vào resource:
- Request rate: traffic đang tăng hay giảm?
- Error rate: request có bị lỗi hoặc timeout?
- Latency: p50/p95/p99 thay đổi ra sao?
- In-flight requests: có nhiều request đang xử lý đồng thời không?
- Queue wait: request/task phải chờ trước khi được xử lý bao lâu?
- Rejected requests/tasks: hệ thống đã chạm giới hạn chưa?

Một service có latency cao nhưng CPU thấp có thể đang chờ database, HTTP dependency, lock hoặc connection pool. Một service CPU cao nhưng latency thấp có thể vẫn còn đủ capacity ở mức tải hiện tại. Phải đọc các tín hiệu cùng nhau.

### 3.1 RED và USE bổ trợ nhau

RED (Rate, Errors, Duration) mô tả service behavior từ góc nhìn request. USE mô tả resource pressure.

| RED symptom | USE clue | Hướng điều tra |
|---|---|---|
| Request latency tăng | Executor queue tăng | Worker capacity hoặc blocking task |
| Error rate tăng | Pool pending và timeout tăng | Connection pool/DB dependency |
| Throughput giảm | CPU utilization cao, run queue cao | CPU saturation |
| Latency tăng, CPU thấp | Pool wait cao | DB/connection capacity |
| 5xx tăng | Memory pressure/GC pause | Heap, allocation và GC |

## 4. Dashboard overview: các panel nên có

Một dashboard saturation thực dụng có thể chia thành các hàng:

| Hàng | Panel | Mục đích |
|---|---|---|
| Service impact | Request rate, error ratio, p95/p99 latency | Xác định người dùng có bị ảnh hưởng |
| CPU | CPU usage, process CPU, run queue/load | Tìm CPU pressure |
| Memory/GC | Heap used/max, old-gen, GC pause/allocation | Tìm memory pressure |
| Threads | Live/peak threads, blocked threads, thread states | Tìm thread starvation/lock |
| Executors | Active/max workers, queue depth, rejected tasks | Tìm task backlog |
| Database pool | Active/idle/max/pending, acquire timeout/wait | Tìm connection starvation |
| Messaging | Queue depth, oldest age, consumer lag, in-flight | Tìm backlog bất đồng bộ |
| Dependency | HTTP client latency/errors, DB latency/errors | Phân biệt local và downstream pressure |

Không cần nhồi mọi metric vào một màn hình. Giữ overview gọn, sau đó tạo dashboard chi tiết theo resource hoặc dependency.

## 5. CPU saturation

Các metric thường hữu ích:
- Process CPU usage.
- System CPU usage.
- CPU cores/available processors.
- Load average hoặc runnable queue nếu host/platform expose.
- Request throughput và latency để xem impact.

Process CPU usage phản ánh phần CPU mà JVM process tiêu thụ; system CPU usage phản ánh host. Container CPU limit có thể thấp hơn số cores của host, vì vậy cần xem quota/throttling metrics từ container runtime hoặc platform.

### 5.1 CPU utilization không phải toàn bộ saturation

CPU usage cao trong thời gian dài có thể là dấu hiệu capacity pressure, nhưng run queue hoặc throttling mới cho biết công việc có bị trì hoãn vì CPU. Trong container, CPU throttling có thể xảy ra dù host còn CPU rảnh do quota của container.

Panel nên:
- So sánh process CPU với CPU limit/quota.
- Theo dõi throttled time/periods nếu platform cung cấp.
- So sánh p95/p99 latency và request rate.
- Hiển thị trend đủ dài để nhận biết sustained pressure.

Không alert chỉ vì một spike CPU ngắn. Dùng cửa sổ thời gian và symptom tương ứng.

## 6. Memory và garbage collection pressure

Memory panel nên tách:
- Heap used so với heap max.
- Old generation/tenured usage nếu JVM expose.
- Non-heap/metaspace.
- Allocation rate.
- GC count và pause duration.
- Container memory working set/limit.
- OOM/restart events từ platform.

Heap used cao không tự động có nghĩa sắp OOM; garbage collector có thể thu hồi memory. Quan sát xu hướng sau GC, allocation rate, pause time và khoảng cách tới container memory limit.

~~~mermaid
flowchart LR
    A["Allocation rate tăng"] --> B["GC frequency/pause tăng"]
    B --> C["CPU dành cho GC tăng"]
    C --> D["Request latency tăng"]
    A --> E["Heap/container memory pressure"]
    E --> F["OOM hoặc restart risk"]
~~~

Nếu container bị OOM kill, JVM có thể không có cơ hội ghi log OutOfMemoryError. Kết hợp process metrics với platform/container events.

## 7. Thread và executor saturation

Spring Boot service có nhiều loại threads: servlet request threads, async executors, scheduler threads, messaging consumers và framework worker pools.

Các metrics cần quan sát:
- Active threads và maximum/peak threads.
- Thread states: runnable, blocked, waiting.
- Executor active workers.
- Executor pool size/max size.
- Queue depth/remaining capacity.
- Rejected task count.
- Task queue wait và execution duration.

Nếu active workers đạt max, queue tăng liên tục và task wait p99 tăng, executor đang bị saturation. Nếu blocked threads tăng, có thể có lock contention hoặc thread đang chờ synchronized section.

Không chỉ tăng max pool size. Với blocking tasks, nhiều threads hơn có thể làm tăng memory, context switching và áp lực lên downstream dependencies.

## 8. Database connection pool saturation

Với HikariCP hoặc pool khác, dashboard nên có:
- Active connections.
- Idle connections.
- Maximum connections.
- Pending/waiting threads.
- Connection acquisition duration.
- Connection timeout count.
- Connection usage duration nếu có.

Tỷ lệ active/max cao trong một thời điểm chưa đủ kết luận saturation. Dấu hiệu mạnh hơn là active duy trì gần max, pending tăng, acquisition wait tăng và timeout xuất hiện.

Ví dụ PromQL conceptual:

~~~promql
max by (service) (hikaricp_connections_active)
/
clamp_min(max by (service) (hikaricp_connections_max), 1)
~~~

~~~promql
max by (service) (hikaricp_connections_pending)
~~~

Tên metric chính xác phụ thuộc Micrometer binder, registry naming convention và version. Kiểm tra /actuator/metrics hoặc scrape output trước khi dùng query.

Nếu active gần max nhưng query duration cũng tăng, DB hoặc transaction có thể giữ connection lâu. Nếu pending tăng mà DB query latency bình thường, xem pool sizing, connection leak và transaction boundaries.

## 9. Messaging và task queue saturation

Đối với Kafka, RabbitMQ hoặc task executor, queue depth đơn lẻ không đủ. Theo dõi:
- Queue depth/backlog.
- Oldest message age.
- Consumer lag (Kafka offset lag).
- Arrival rate và completion throughput.
- Consumer concurrency/active workers.
- In-flight/unacked messages.
- Retry/dead-letter rate.
- Queue wait time và processing duration.

Kafka offset lag là số records/offset distance, không trực tiếp là thời gian chờ. Kết hợp lag với throughput và record age. RabbitMQ ready/unacked counts phản ánh trạng thái queue khác nhau; hiểu broker semantics trước khi đặt threshold.

Một queue có depth lớn nhưng oldest age thấp và throughput drain nhanh có thể là burst bình thường. Queue depth và age cùng tăng liên tục là tín hiệu backlog đáng quan tâm.

## 10. Downstream saturation và dependency pressure

Service có thể trông như bị saturation vì dependency chậm:
- HTTP client connection pool cạn.
- Remote API latency tăng.
- Database lock/query chậm.
- DNS/TLS/connect timeout.
- Rate limit hoặc 429/503 từ dependency.

Panel dependency nên hiển thị client request rate, error rate, latency percentiles, timeout/retry count và pool wait. Trace giúp xác định request dành thời gian ở local queue, client pool hay downstream server.

Không quy mọi latency increase cho CPU hoặc thread pool. Một request thread đang chờ I/O có thể làm active thread count cao trong khi process CPU thấp.

## 11. Chọn aggregation và time windows

Dashboard saturation cần nhiều kiểu aggregation:

| Aggregation | Dùng khi nào | Lưu ý |
|---|---|---|
| Rate | Counter như errors/rejections | Dùng rate thay absolute count khi traffic thay đổi |
| Ratio | Active/max, errors/requests | Bảo đảm denominator không bằng 0 |
| Average | Trend tổng quát | Có thể che khuất outliers |
| p95/p99 | Latency và wait time | Cần histogram/buckets phù hợp |
| Max | Spike hoặc peak gauge | Có thể nhạy với một điểm đo |
| Sum | Tổng backlog/rejections trên fleet | Tránh cộng gauges không cùng semantics |
| Per-instance | Tìm pod/node lệch | Giữ dimension bounded |

Dùng cửa sổ ngắn để phát hiện spike và cửa sổ dài để xác nhận sustained saturation. Alert thường cần for duration để tránh flapping; dashboard có thể hiển thị raw series và smoothed trend.

Không lấy average của per-instance percentiles để suy ra fleet-wide percentile. Dùng histogram buckets có thể aggregate hoặc query backend hỗ trợ distribution aggregation.

## 12. Thresholds và alert design

Threshold phải dựa trên baseline, capacity và SLO. Ví dụ khởi điểm để thử nghiệm, không phải giá trị mặc định cho mọi hệ thống:

| Signal | Điều kiện cảnh báo tham khảo | Xác nhận bằng |
|---|---|---|
| CPU pressure | CPU gần quota trong vài phút | Throttling, run queue, latency |
| Heap/container memory | Memory tiến gần limit và tăng liên tục | GC pause, OOM/restart |
| Executor saturation | Queue tăng và active workers chạm max | Task wait, rejection |
| DB pool saturation | Active/max cao cùng pending/wait tăng | Acquire timeout, DB latency |
| Messaging backlog | Oldest age vượt processing SLO | Arrival/completion rate, consumer lag |
| Rejected work | Rejection rate tăng trên baseline | Thread/queue capacity và request errors |

Alert nên kết hợp resource signal với user impact:
- Warning khi resource pressure kéo dài.
- Critical khi pressure đi cùng latency/error SLO breach hoặc work bị reject.
- Có inhibition/deduplication để tránh nhiều alert cho cùng một nguyên nhân gốc.

Không alert critical chỉ vì utilization cao nếu service vẫn đáp ứng SLO và còn capacity headroom.

## 13. Cardinality và dashboard performance

Dashboard có thể chậm hoặc backend tốn kém nếu group theo dimensions không giới hạn:
- user/customer/order ID.
- raw URL hoặc query string.
- exception message.
- message ID hoặc trace ID.
- dynamic tenant identifiers.
- unbounded SQL statement.

Ưu tiên service, environment, region tổng quát, operation, route template, outcome và bounded error.type. Dùng dashboard drill-down sang traces/logs để điều tra một request; đừng tạo metric series riêng cho mỗi request.

Panel per-instance có thể hữu ích nhưng cần giới hạn số series và retention. Với fleet lớn, dùng top-k hoặc filter theo service/cluster rồi drill down.

## 14. Thiết kế dashboard dễ sử dụng

Một dashboard tốt nên:
1. Có service/environment selector với values bounded.
2. Đặt request rate, error ratio và p95/p99 ở hàng đầu.
3. Đặt resource utilization cạnh saturation/backlog tương ứng.
4. Hiển thị capacity limit cùng usage (active/max, used/limit).
5. Dùng cùng time range và timezone cho các panel liên quan.
6. Ghi rõ unit, aggregation và metric definition.
7. Có link tới traces/logs/runbook cho drill-down.
8. Dùng annotation cho deployment/config change.
9. Tránh quá nhiều panels và legends khó đọc.
10. Có panel cho missing/no data để phân biệt zero với telemetry absent.

Đặt tên panel theo câu hỏi vận hành, ví dụ “DB connections waiting” thay vì chỉ “Gauge 4”. Ghi rõ queue depth là instantaneous gauge, error rate là rate và latency là histogram quantile.

## 15. Kiểm chứng dashboard bằng tải thử

Dùng staging hoặc performance environment để tạo các tình huống có thể lặp lại:
- Tăng CPU-bound workload.
- Giảm executor worker count và tạo task backlog.
- Giới hạn connection pool hoặc giữ connection có kiểm soát.
- Làm database query chậm trong môi trường test.
- Tăng message arrival rate hơn consumer throughput.
- Tạo downstream HTTP latency/429/503.
- Tạo memory allocation pressure ở mức an toàn.

Với từng scenario, xác nhận:
1. Utilization panel phản ánh resource bận.
2. Saturation panel phản ánh queue/pending/wait.
3. Error panel phản ánh rejection/timeout.
4. RED panels phản ánh user impact.
5. Alert kích hoạt trong time window dự kiến.
6. Runbook chỉ đúng nhóm resource cần điều tra.

Không tạo overload không kiểm soát trên production. Dùng giới hạn tải, stop condition và rollback plan trong test environment.

## 16. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| CPU thấp nhưng latency cao | I/O wait, pool wait, lock hoặc downstream chậm | Xem queue/pool waits và distributed traces |
| CPU cao nhưng queue thấp | CPU-bound work vẫn trong capacity | Theo dõi latency/SLO và run queue |
| Active threads cao, CPU thấp | Threads blocked/waiting trên I/O/lock | Xem thread states và traces |
| Executor active=max, queue tăng | Worker capacity thiếu hoặc tasks chậm | Xem processing duration, blocking và downstream |
| DB active=max, pending tăng | Pool saturation hoặc connection giữ lâu | Xem acquisition wait, usage duration và DB spans |
| Heap cao nhưng GC hiệu quả | Heap occupancy sau allocation spike | Xem post-GC trend, allocation và pause |
| Container OOM dù JVM heap chưa max | Native memory/sidecar/direct buffers/container limit | So sánh process RSS, container working set và heap |
| Kafka lag tăng nhưng age thấp | Topic throughput cao | Xem records/sec và record timestamps |
| Queue depth cao nhưng không có impact | Burst được drain nhanh | Xem oldest age và completion throughput |
| Rejections tăng nhưng CPU thấp | Pool/queue limit hoặc bulkhead mở quá nhỏ | Xem resource-specific capacity và dependency |
| Fleet average bình thường nhưng một pod chậm | Một instance hot spot | Drill down per-instance và deployment placement |
| Dashboard không có dữ liệu | Meter/binder thiếu hoặc scrape/filter lỗi | Kiểm tra registry, endpoint và exporter pipeline |

## 17. Playbook: p99 tăng dù CPU chưa cao

**Tình huống:** Order Service p99 tăng gấp ba, CPU process vẫn dưới 60%.

1. Xác nhận request rate, error ratio và p95/p99 theo route.
2. Kiểm tra servlet/request threads và blocked/waiting states.
3. Xem executor active/max, queue depth, task queue wait và rejected count.
4. Kiểm tra HikariCP active/idle/max/pending và acquisition duration.
5. Xem HTTP client pool wait, downstream latency, timeout và retry.
6. Mở traces chậm để xác định thời gian nằm ở local queue, DB, remote HTTP hay lock.
7. Kiểm tra messaging backlog/oldest age nếu request chờ async result.
8. So sánh per-instance để tìm pod/node bất thường.
9. Thực hiện thay đổi có kiểm soát ở bottleneck đã xác định; không tăng mọi pool đồng thời.
10. Xác nhận p99, queue wait, pending và rejection trở về baseline sau thay đổi.

CPU thấp không loại trừ saturation. Threads và connections có thể bị giữ trong lúc chờ I/O, làm latency tăng mà CPU không bận.

## 18. Bài tập tự kiểm tra

**Bài 1 — USE.** Phân biệt utilization và saturation của connection pool. Metric nào cho biết connection đang bận và metric nào cho biết request đang chờ?

**Bài 2 — CPU.** CPU utilization 90% nhưng run queue thấp và latency ổn định. Có đủ bằng chứng để alert critical không? Vì sao?

**Bài 3 — Executor.** Active workers bằng max, queue tăng liên tục và rejected tasks xuất hiện. Bạn sẽ xem thêm metric nào để xác định nguyên nhân?

**Bài 4 — Database pool.** Active connections gần max nhưng pending bằng 0. Đây đã chắc chắn là saturation chưa? Cần thêm tín hiệu nào?

**Bài 5 — Messaging.** Vì sao Kafka lag 10.000 records không thể được hiểu trực tiếp là 10.000 giây queue wait?

**Bài 6 — Memory.** Heap used cao nhưng post-GC usage ổn định. Vì sao không nên chỉ dựa vào heap percentage để kết luận OOM risk?

**Bài 7 — Aggregation.** Vì sao không lấy average của p99 từng pod để tính p99 toàn fleet?

**Bài 8 — Diagnosis.** p99 tăng, CPU thấp, DB pool pending tăng và DB span duration cao. Hãy đề xuất thứ tự điều tra.

### Gợi ý trả lời

1. Utilization là active/max; saturation là pending/waiting work hoặc acquisition wait.
2. Chưa đủ. Xem CPU quota/throttling, run queue, latency và SLO trong một cửa sổ đủ dài.
3. Task queue wait, processing duration, task type bounded, blocked threads và downstream latency.
4. Chưa chắc; pool có thể gần đầy nhưng chưa có request phải chờ. Xem pending, acquisition latency và timeout.
5. Lag là offset distance; thời gian phụ thuộc arrival/consume throughput và record timestamps.
6. GC có thể thu hồi phần lớn allocation; xem post-GC trend, allocation rate, pause và container limit.
7. Percentile không có tính cộng tuyến tính; aggregate histogram buckets/raw observations ở backend.
8. Xem query/lock và DB capacity, connection usage duration, transaction boundaries, sau đó đối chiếu pool sizing và traffic concurrency.

## 19. Tài liệu tham khảo chính thức

- [USE Method](https://www.brendangregg.com/usemethod.html): utilization, saturation và errors cho từng resource.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer binders, JVM, datasource và application metrics.
- [Spring Boot — Actuator Metrics Endpoint](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.metrics): khám phá meter và measurements.
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): duration, histogram và percentiles.
- [Micrometer — Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html): gauge semantics và lifecycle.
- [HikariCP — Metrics](https://github.com/brettwooldridge/HikariCP): active/idle/pending connections và pool behavior.
- [Apache Kafka — Monitoring](https://kafka.apache.org/documentation/#monitoring): consumer lag và broker/consumer metrics.
- [RabbitMQ — Monitoring](https://www.rabbitmq.com/docs/monitoring): queue depth, ready/unacked và consumer metrics.
- [Prometheus — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/): histogram aggregation và quantile caveats.
- [Kubernetes — Resource Metrics](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): CPU/memory requests, limits và container resource behavior.

**Ghi nhớ:** Saturation là công việc phải chờ hoặc bị từ chối khi resource không theo kịp tải. Áp dụng USE cho CPU, memory, threads, executors, connection pools và queues; kết hợp RED để thấy impact tới request. Luôn xem usage cùng pending/backlog, errors và latency. Dùng thresholds theo baseline/SLO, drill down theo instance và dependency, rồi xác nhận bằng traces. Đừng tăng pool hoặc concurrency hàng loạt trước khi xác định resource đang nghẽn ở đâu.

