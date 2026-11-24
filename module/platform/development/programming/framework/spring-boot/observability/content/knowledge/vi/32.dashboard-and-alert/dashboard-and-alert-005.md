# Dashboard JVM cho Spring Boot

JVM dashboard giúp đội vận hành nhìn thấy sức khỏe runtime của một ứng dụng Spring Boot qua heap/non-heap memory, garbage collection, threads, CPU, class loading và buffer pools. Các chỉ số này bổ sung cho HTTP metrics, logs và distributed traces: khi latency tăng, dashboard JVM giúp xác định liệu ứng dụng đang chịu áp lực bộ nhớ, GC pause, thread saturation hay CPU throttling. Một dashboard tốt phải trả lời được câu hỏi vận hành cụ thể, dùng đơn vị và labels nhất quán, đồng thời tránh biến mọi JVM metric thành biểu đồ không có ngữ cảnh.

Trong module **SPRING_BOOT_OBSERVABILITY**, dashboard JVM sử dụng dữ liệu Micrometer và Spring Boot Actuator để trình bày tình trạng runtime theo thời gian. Bài thuộc chương **Dashboard và alert**, tập trung vào thiết kế dashboard JVM: metric sources, memory pools, GC, threads, CPU, class loading, buffer pools, PromQL, labels/cardinality, panel layout, alert signals, validation và quy trình điều tra.

## Mục tiêu học tập

1. Xác định JVM metrics được Spring Boot/Micrometer expose.
2. Phân biệt heap, non-heap, memory pools và buffer pools.
3. Đọc GC count, pause duration và allocation pressure.
4. Theo dõi live/daemon/peak threads và thread states.
5. Kết hợp process/system CPU với container CPU limits.
6. Thiết kế panel cho class loading và direct buffers.
7. Viết PromQL có aggregation và labels phù hợp.
8. Tránh cardinality cao và dashboard gây hiểu nhầm.
9. Xây dựng cảnh báo dựa trên triệu chứng và điều tra theo tín hiệu liên quan.

## 1. Nguồn dữ liệu JVM metrics trong Spring Boot

Khi Actuator và Micrometer registry được cấu hình, Spring Boot có thể tự đăng ký JVM binders. Các meter thường gặp gồm:
- jvm.memory.used, jvm.memory.committed, jvm.memory.max;
- jvm.gc.pause;
- jvm.threads.live, jvm.threads.daemon, jvm.threads.peak, jvm.threads.states;
- jvm.classes.loaded, jvm.classes.unloaded;
- process.cpu.usage, system.cpu.usage;
- process.uptime, process.start.time;
- jvm.buffer.memory.used, jvm.buffer.count.

Tên meter và tag cụ thể phụ thuộc Micrometer, JVM và registry version. Hãy kiểm tra /actuator/metrics và /actuator/prometheus trong runtime thật trước khi viết dashboard. Một meter có thể được export thành nhiều Prometheus series với suffix _sum, _count, _max hoặc histogram buckets.

### 1.1. Bật Actuator và Prometheus registry

Ví dụ dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Ví dụ exposure:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  endpoint:
    prometheus:
      access: read-only
~~~

Cấu hình endpoint access thay đổi theo Spring Boot version. Chỉ expose Prometheus endpoint trên network được monitoring server truy cập và bảo vệ management endpoints theo policy của tổ chức.

### 1.2. Xác minh meter trước khi xây panel

Gọi:

~~~http
GET /actuator/metrics/jvm.memory.used
GET /actuator/metrics/jvm.gc.pause
GET /actuator/prometheus
~~~

Xác minh meter có dữ liệu, tag keys và units. Nếu metric không xuất hiện, kiểm tra registry dependency, binder configuration, endpoint exposure và runtime support trước khi sửa dashboard.

## 2. Thiết kế layout dashboard

Dashboard nên được sắp theo thứ tự từ tổng quan tới nguyên nhân:

~~~text
JVM overview
  ├─ Runtime identity: service, instance, version, uptime
  ├─ Memory: heap used/max, non-heap, pools, direct buffers
  ├─ GC: pause rate, pause duration, collection activity
  ├─ Threads: live/daemon/peak, state distribution
  ├─ CPU: process CPU, system CPU, container throttling
  └─ Class loading: loaded/unloaded classes

Related context
  ├─ HTTP request rate, errors, latency
  ├─ Executor queue and active threads
  ├─ Hikari connection pool
  └─ Logs and traces for the same time window
~~~

Một dashboard overview không cần hiển thị mọi meter. Chọn panels có thể phát hiện triệu chứng và dẫn tới dashboard chuyên sâu hoặc trace investigation.

### 2.1. Variables và dashboard filters

Các variable hữu ích:
- service: service name ổn định;
- environment: môi trường deployment;
- instance hoặc pod: instance cần drill down;
- namespace/cluster: phạm vi hạ tầng;
- version: phiên bản ứng dụng.

Dùng service/environment làm bộ lọc mặc định. Cho phép chọn instance để tìm pod lệch chuẩn. Không tạo variable từ user ID, request ID hoặc giá trị có cardinality lớn.

## 3. Heap memory

Heap là vùng memory JVM dùng để cấp phát object. Heap usage tăng có thể là workload bình thường, allocation burst, cache growth hoặc memory leak. Cần nhìn used, committed và max cùng nhau.

| Metric | Ý nghĩa |
| --- | --- |
| jvm.memory.used | Memory đang được sử dụng trong pool |
| jvm.memory.committed | Memory JVM đã commit |
| jvm.memory.max | Giới hạn pool nếu JVM cung cấp |
| jvm.memory.usage | Tỷ lệ usage nếu binder/registry expose |

Không cộng tất cả pool max một cách máy móc nếu có pool không có max hoặc memory pool lifecycle thay đổi. Phân biệt heap pools như Eden, Survivor và Old Gen theo collector/JVM.

### 3.1. Heap utilization

Một panel có thể biểu diễn tỷ lệ:

\[
\text{heap utilization} =
\frac{\sum \text{heap used}}{\sum \text{heap max}} \times 100
\]

Ví dụ PromQL nếu series có label area:

~~~promql
100 *
sum by (service, instance) (
  jvm_memory_used_bytes{area="heap"}
)
/
sum by (service, instance) (
  jvm_memory_max_bytes{area="heap", id=~".+"}
)
~~~

Đây là query minh họa. Tên label/series phụ thuộc Prometheus naming convention và Micrometer version. Một số pool có max không xác định; cần lọc/điều chỉnh để tránh tỷ lệ sai. Xác minh series thực tế trước khi dùng.

### 3.2. Used so với committed

Heap used cao nhưng committed còn thấp hơn max có thể khiến JVM mở rộng committed memory. Heap committed cao không đồng nghĩa toàn bộ memory đã được sử dụng. Khi điều tra, xem cả absolute bytes và tỷ lệ, cùng GC pause và allocation behavior.

### 3.3. Old generation và leak signals

Old Gen tăng dần qua nhiều chu kỳ GC và không giảm đáng kể có thể là dấu hiệu retained objects, cache không giới hạn hoặc leak. Một snapshot đơn lẻ không đủ kết luận. Quan sát xu hướng sau GC, load tương tự và qua nhiều giờ/ngày; heap dump chỉ thực hiện theo quy trình có kiểm soát vì có thể gây pause và chứa dữ liệu nhạy cảm.

## 4. Non-heap và metaspace

Non-heap bao gồm các vùng như Metaspace và Code Cache, tùy JVM. Metaspace chứa metadata class; tăng liên tục có thể liên quan classloader leak, dynamic proxy hoặc redeploy behavior. Code Cache lưu compiled code.

Panel nên hiển thị used/committed theo pool và cảnh báo dựa trên xu hướng/giới hạn runtime thực tế. jvm.memory.max có thể không xác định cho một số non-heap pools; không chia cho giá trị không hợp lệ.

## 5. Garbage collection

GC metrics giúp phân biệt allocation pressure và pause behavior. Micrometer thường cung cấp jvm.gc.pause với duration và tags mô tả action/cause tùy JVM.

### 5.1. GC pause rate

Với timer Prometheus export, có thể xem số lần pause:

~~~promql
sum by (service, instance) (
  rate(jvm_gc_pause_seconds_count[5m])
)
~~~

### 5.2. GC pause duration

P95 từ histogram buckets nếu histogram được bật:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, service, instance) (
    rate(jvm_gc_pause_seconds_bucket[5m])
  )
)
~~~

Nếu histogram buckets không được export, không dùng query này; kiểm tra _sum/_count và cấu hình histogram trước. Average pause có thể tính từ rate sum/rate count nhưng không thay thế p95/p99.

~~~promql
sum by (service, instance) (rate(jvm_gc_pause_seconds_sum[5m]))
/
sum by (service, instance) (rate(jvm_gc_pause_seconds_count[5m]))
~~~

### 5.3. Diễn giải GC đúng cách

GC count tăng không nhất thiết là vấn đề; cần xem pause duration, throughput, heap trend và latency của request. Một collector có nhiều short pauses có thể hoạt động bình thường. Alert chỉ dựa trên GC count thường gây noise.

## 6. Threads và thread states

Threads cho biết mức độ concurrency và khả năng pool bị kẹt. Các meter thường gặp:
- live threads;
- daemon threads;
- peak threads;
- thread states: NEW, RUNNABLE, BLOCKED, WAITING, TIMED_WAITING, TERMINATED tùy binder.

### 6.1. Live và peak threads

~~~promql
jvm_threads_live_threads
~~~

Panel hiển thị live threads theo instance và peak threads nếu series có mặt. Tăng liên tục có thể là thread leak, task tạo thread không giới hạn hoặc executor pool không được quản lý.

### 6.2. Thread state distribution

~~~promql
sum by (service, instance, state) (
  jvm_threads_states_threads
)
~~~

Tỷ lệ BLOCKED hoặc WAITING cao không tự động chứng minh deadlock. Cần so với baseline và xem thread dump khi có dấu hiệu request latency tăng, executor queue backlog hoặc lock contention.

### 6.3. Kết hợp executor metrics

JVM thread count nên được đọc cùng executor active threads, pool size, queue depth và rejected tasks. Thread count ổn định nhưng queue tăng có thể là worker bị block hoặc throughput thấp. Tránh chỉ tăng max pool mà chưa kiểm tra downstream capacity.

## 7. CPU và container limits

Process CPU và system CPU trả lời hai câu hỏi khác nhau:
- process CPU usage: tỷ lệ CPU được process sử dụng theo cách binder định nghĩa;
- system CPU usage: mức sử dụng CPU tổng thể của host/runtime environment.

~~~promql
process_cpu_usage
~~~

~~~promql
system_cpu_usage
~~~

Giá trị thường là tỷ lệ 0..1, nhưng xác minh unit và semantics của meter trong version/runtime. Với container, cần đối chiếu CPU usage với CPU limit, throttling và node pressure từ container/platform metrics. Các metrics này không nhất thiết đến từ Micrometer JVM binder.

### 7.1. CPU throttling

Kubernetes CPU limit có thể làm container bị throttled dù node còn CPU. JVM dashboard nên liên kết panel với container CPU usage/throttling metrics từ cAdvisor/kubelet hoặc platform exporter. Các metrics này không nhất thiết đến từ Micrometer.

### 7.2. CPU và latency

Nếu CPU tăng cùng request latency, xem thread states, GC pause và allocation. Nếu CPU thấp nhưng latency tăng, kiểm tra dependency spans, connection pool, locks hoặc thread pool.

## 8. Class loading và buffer pools

### 8.1. Class loading

jvm.classes.loaded theo dõi số class đang loaded; jvm.classes.unloaded là counter của class unload events tùy binder. Loaded classes tăng trong startup là bình thường. Tăng liên tục sau warm-up có thể gợi ý dynamic class generation hoặc classloader leak.

~~~promql
jvm_classes_loaded_classes
~~~

~~~promql
rate(jvm_classes_unloaded_classes_total[10m])
~~~

Tên Prometheus series có thể khác theo version; kiểm tra scrape output.

### 8.2. Direct và mapped buffers

NIO buffer pools có thể tiêu thụ native memory ngoài heap. Theo dõi jvm.buffer.memory.used và jvm.buffer.count theo pool. Heap ổn định nhưng direct buffer tăng có thể gây native memory pressure. Đọc cùng process RSS/container memory vì heap dashboard không bao quát toàn bộ memory của process.

## 9. Kết hợp JVM với application signals

JVM dashboard cần có liên kết tới các tín hiệu ứng dụng:
- HTTP request rate, error ratio và p95/p99 latency;
- executor active/queue/rejected;
- Hikari active/idle/pending/acquisition;
- messaging consumer lag;
- database/client span latency;
- deployment/version markers.

Ví dụ: HTTP latency tăng, CPU thấp, GC bình thường, Hikari pending tăng và JDBC spans dài thường gợi ý database/pool bottleneck hơn JVM CPU. Nếu heap/Old Gen tăng và GC pause tăng đồng thời, điều tra allocation/retention.

### 9.1. Correlation theo cùng labels

Dùng labels ổn định như service, environment, cluster, namespace, instance và version. Đảm bảo các dashboards dùng cùng naming conventions. Không join metrics theo request ID hoặc trace ID.

### 9.2. Deployment annotations

Đánh dấu deployment, config change, JVM restart và scaling events trên timeline. Điều này giúp liên hệ thay đổi runtime với heap, GC, thread và latency behavior.

## 10. Alerting từ JVM dashboard

Dashboard là nơi nhìn và điều tra; alert cần phát hiện triệu chứng có ý nghĩa và kích hoạt hành động cụ thể. Không alert trên mọi metric.

| Signal | Alert condition gợi ý | Điều cần xác minh |
| --- | --- | --- |
| Heap usage | Cao kéo dài sau GC | Leak/heap sizing/cache |
| GC pause | p95/p99 vượt latency budget | Collector/alloc pressure |
| Live threads | Tăng bất thường so baseline | Thread leak/pool growth |
| BLOCKED threads | Tăng cùng latency | Lock contention |
| Process CPU | Cao kéo dài | CPU saturation |
| Container throttling | Throttled time tăng | CPU limit/capacity |
| Direct buffers | Tăng liên tục hoặc gần limit | Native memory pressure |
| Class loaded | Tăng liên tục sau warm-up | Dynamic class generation |

### 10.1. Alert có cửa sổ và duration

Dùng for duration để tránh alert từ spike ngắn. Đặt threshold theo load test và baseline của service. Heap utilization 85% có thể bình thường với một workload và nguy hiểm với workload khác; không áp dụng ngưỡng chung mà không kiểm chứng.

### 10.2. Alert theo triệu chứng

Alert "JVM heap pressure sustained" tốt hơn "memory leak confirmed". Metrics chỉ gợi ý triệu chứng; leak cần heap analysis và xác minh object retention. Alert message nên nêu service/instance, metric, threshold, duration và link dashboard/runbook.

## 11. Ví dụ PromQL cho dashboard

Các query dưới đây là mẫu. Series names/labels phải được xác minh từ /actuator/prometheus.

**Heap used bytes:**

~~~promql
sum by (service, instance) (
  jvm_memory_used_bytes{area="heap"}
)
~~~

**Non-heap used bytes:**

~~~promql
sum by (service, instance) (
  jvm_memory_used_bytes{area="nonheap"}
)
~~~

**GC pause rate:**

~~~promql
sum by (service, instance) (
  rate(jvm_gc_pause_seconds_count[5m])
)
~~~

**GC average pause:**

~~~promql
sum by (service, instance) (rate(jvm_gc_pause_seconds_sum[5m]))
/
sum by (service, instance) (rate(jvm_gc_pause_seconds_count[5m]))
~~~

**Live threads:**

~~~promql
jvm_threads_live_threads
~~~

**Process CPU:**

~~~promql
process_cpu_usage
~~~

**Class loading:**

~~~promql
jvm_classes_loaded_classes
~~~

Nếu labels service hoặc instance không tồn tại, dùng labels thực tế của scrape/relabel configuration. Không copy query vào production dashboard trước khi kiểm tra output.

## 12. Cardinality và dashboard performance

Mỗi label dimension nhân số time series. Labels nên dùng giá trị có tập hữu hạn và ổn định: service, environment, region/cluster, namespace, instance/pod và version.

Tránh user ID, request ID/trace ID, URL path chứa IDs, exception message, thread name nếu mỗi task tạo tên động, JVM arguments hoặc path động.

Instance/pod là dimension hữu ích để phát hiện một replica lệch chuẩn nhưng có thể tạo churn khi autoscaling. Dùng dashboard variables và aggregation để kiểm soát panel; không loại bỏ instance nếu cần điều tra per-pod.

### 12.1. Giảm panel/query cost

- Giới hạn time range mặc định.
- Dùng recording rules cho query nặng lặp lại.
- Aggregate trước khi hiển thị khi panel không cần từng instance.
- Tránh regex label rộng và joins phức tạp.
- Dùng step/resolution phù hợp với thời gian hiển thị.
- Chỉ bật histogram buckets khi cần quantile và đã tính cardinality cost.

## 13. Kiểm thử dashboard và metric contracts

Dashboard cần kiểm thử ở hai lớp: metric production và query/panel behavior.

| Test | Mục tiêu |
| --- | --- |
| Actuator scrape test | JVM series được export |
| Meter contract test | Meter names/tags ổn định cần thiết |
| PromQL validation | Query parse và trả series |
| Dashboard JSON validation | Panels/variables/datasources hợp lệ |
| Load test | Panels vẫn phản hồi ở cardinality thực |
| Alert rule test | Threshold/for/labels/annotations đúng |
| Upgrade test | Micrometer/JDK/Boot upgrade không làm panel hỏng |

### 13.1. Kiểm tra metrics từ application

Gọi /actuator/prometheus trong integration test và xác minh các series cần thiết có mặt. Tránh assert toàn bộ scrape output vì JVM version, process và runtime metrics có thể thay đổi.

### 13.2. Kiểm tra query

Dùng Prometheus rule tests hoặc query validation trong CI nếu nền tảng hỗ trợ. Test cả trường hợp series absent, denominator zero và label không tồn tại. Heap utilization query phải xử lý pool max không xác định.

### 13.3. Kiểm tra dashboard sau upgrade

Khi nâng JDK, Spring Boot hoặc Micrometer, so sánh scrape output trước/sau. Một số meter/labels/units có thể thay đổi. Dashboard nên được version control cùng alert rules và review trong release.

## 14. Quy trình điều tra bằng JVM dashboard

Khi latency tăng hoặc pod restart:
1. Chọn service, environment và instance bị ảnh hưởng.
2. Xem request rate, error ratio và latency cùng thời điểm.
3. Kiểm tra heap used/max, Old Gen trend và non-heap.
4. Xem GC pause rate/duration và correlate với latency.
5. Kiểm tra live threads, state distribution và executor queue.
6. Xem process CPU cùng container throttling.
7. Kiểm tra direct buffers và process/container memory.
8. Đối chiếu Hikari pool, HTTP client spans và database metrics.
9. Mở logs/traces cùng time window để xác định operation cụ thể.
10. So sánh trước/sau deployment marker.

Không kết luận memory leak chỉ từ heap usage cao, deadlock chỉ từ WAITING threads hoặc CPU bottleneck chỉ từ system CPU. Dashboard giúp thu hẹp giả thuyết; heap dump, thread dump, profiler và traces cung cấp bằng chứng sâu hơn.

## 15. Troubleshooting dashboard JVM

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không có JVM metrics | Binder/registry thiếu hoặc endpoint chưa expose | Kiểm tra Actuator, registry và scrape |
| Heap utilization vượt 100% | Pool max không hợp lệ hoặc query sai | Lọc pool có max hợp lệ và xác minh labels |
| GC panel rỗng | Histogram/series name khác hoặc JVM binder không phát | Inspect scrape output |
| Thread count tăng liên tục | Thread leak hoặc executor growth | Thread dump và executor metrics |
| CPU panel bằng 0 | Unsupported OS bean hoặc unit/query sai | Kiểm tra runtime support và meter unit |
| Heap ổn định nhưng RSS tăng | Native/direct memory hoặc thread stacks | Buffer pools, NMT và container metrics |
| Class count tăng mãi | Dynamic class generation/classloader leak | Classloader analysis |
| Dashboard chậm | Query cardinality/time range lớn | Recording rules, aggregation, label review |
| Panel trống sau upgrade | Meter/label naming đổi | Contract tests và cập nhật query |
| Alert GC noise | Alert chỉ theo count | Dùng pause duration và latency correlation |
| Một pod lệch chuẩn | Instance-specific workload/config | Drill down instance và compare replicas |

### 15.1. Runbook ngắn

- Heap pressure: xem Old Gen sau GC, allocation, cache limits và heap dump theo quy trình.
- GC latency: xem pause quantiles, collector logs, CPU throttling và allocation rate.
- Thread saturation: xem thread states, executor queues, thread dump và downstream calls.
- CPU saturation: xem process CPU, container throttling, hot threads và request mix.
- Native memory: xem direct buffers, RSS, thread count và Native Memory Tracking.

## 16. Production checklist

| Tiêu chí | Bằng chứng |
| --- | --- |
| JVM meters được expose | Scrape test có các series cần thiết |
| Heap/non-heap phân biệt | Panels theo area/pool |
| Pool max xử lý đúng | Không chia cho -1/NaN |
| GC pause đo đúng | Count/sum/histogram semantics xác minh |
| Threads có context | Live/peak/states và executor metrics |
| CPU có container context | Process/system CPU cùng throttling |
| Native memory được xem xét | Direct buffers/RSS |
| Labels ổn định | Không dynamic identifiers |
| Dashboard có variables | Service/environment/instance |
| Alert có runbook | Threshold, duration, owner và action |
| Query performance phù hợp | Cardinality/time range/recording rules |
| Upgrade được kiểm tra | Metric contract và dashboard validation |
| Logs/traces liên kết | Drill-down cùng time window |

## 17. Bài thực hành: xây JVM dashboard cho order-service

**Bối cảnh:** order-service chạy nhiều replicas trên Kubernetes. Sau một bản phát hành, p99 HTTP latency tăng, một số pod restart vì memory pressure. Đội vận hành cần dashboard giúp phân biệt heap pressure, GC, CPU throttling và thread/executor saturation.

**Nhiệm vụ:**
1. Bật Actuator và Prometheus registry.
2. Thu scrape output, ghi nhận tên meters/labels thực tế.
3. Tạo variables service, environment, namespace và instance.
4. Tạo panels heap used/committed/max và non-heap theo pool.
5. Thêm GC pause rate, average và p95/p99 khi histogram có sẵn.
6. Thêm live/daemon/peak threads và state distribution.
7. Thêm process/system CPU cùng container CPU throttling.
8. Thêm direct buffer memory/count và class loading trend.
9. Liên kết HTTP latency/error, executor queue và Hikari pool panels.
10. Tạo alerts cho heap pressure kéo dài, GC pause cao, thread growth và CPU throttling.
11. Kiểm tra PromQL khi series absent, max không hợp lệ và labels thay đổi.
12. Viết runbook drill-down từ JVM symptom tới logs/traces và profiler.

**Kết quả mong đợi:** dashboard JVM có panels/variables, alert rules, query validation và runbook điều tra latency/memory incidents.

## 18. Ghi nhớ

JVM dashboard nên giúp phát hiện và phân loại runtime pressure. Heap/non-heap cho biết memory pools; GC pause cho biết chi phí collection; threads và executor metrics chỉ ra concurrency/saturation; process CPU cần được đọc cùng container throttling; direct buffers và RSS bổ sung góc nhìn native memory. Không một metric đơn lẻ đủ kết luận memory leak, deadlock hoặc CPU bottleneck.

Xác minh meter names, units và labels từ /actuator/prometheus trước khi viết PromQL. Dùng labels ổn định, variables để drill down và recording rules khi query tốn kém. Alerts cần duration, baseline, owner và runbook; tránh alert chỉ dựa vào GC count hoặc một ngưỡng heap chung. Kết hợp JVM dashboard với HTTP metrics, pool metrics, logs và traces để chuyển từ triệu chứng runtime sang nguyên nhân request cụ thể.

**Tài liệu tham khảo:**
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot — Prometheus Endpoint](https://docs.spring.io/spring-boot/reference/actuator/metrics.html#actuator.metrics.export.prometheus)
- [Micrometer JVM Metrics](https://docs.micrometer.io/micrometer/reference/reference/jvm.html)
- [Prometheus — Querying Basics](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Prometheus — Query Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/)
- [Grafana — Dashboards](https://grafana.com/docs/grafana/latest/dashboards/)
- [Java — Monitoring and Management](https://docs.oracle.com/en/java/javase/21/management/)

