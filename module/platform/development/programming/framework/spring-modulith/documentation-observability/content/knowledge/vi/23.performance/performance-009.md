# Đo overhead trước và sau khi bật Insight

> **Chương:** Hiệu năng  
> **Bối cảnh:** Spring Modulith Insight bổ sung khả năng công bố module architecture qua Actuator và quan sát tương tác giữa các module bằng metrics, traces. Những khả năng này giúp kiểm chứng kiến trúc khi ứng dụng chạy, nhưng cũng thêm công việc vào đường xử lý event, lời gọi qua module API và pipeline telemetry. Bài này hướng dẫn thiết kế phép đo trước/sau khi bật Insight, tách overhead trên request path khỏi chi phí scrape/export, và dùng kết quả để quyết định cấu hình production.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xác định những thành phần Insight bổ sung và vị trí chúng tạo overhead.
2. Thiết kế baseline và các biến thể thử nghiệm có thể so sánh công bằng.
3. Đo riêng chi phí event metrics, module spans, Actuator endpoint và exporter/scrape.
4. Thu thập throughput, latency, CPU, allocation, GC, startup time và telemetry volume.
5. Dùng workload thực tế để xác định overhead có ý nghĩa thống kê.
6. Phân biệt chi phí instrumentation với chi phí backend hoặc scrape.
7. Đặt tiêu chí chấp nhận và rollback trước khi triển khai Insight lên production.

## 1. Insight bổ sung những gì?

Spring Modulith Insight starter là cách thuận tiện để bật production-ready features của Spring Modulith. Starter tích hợp:

- Spring Boot Actuator và Application Module Actuator.
- Spring Modulith observability API và core.
- Hỗ trợ quan sát tương tác giữa application modules bằng Micrometer spans và event metrics.

Insight không tự kết nối ứng dụng tới mọi monitoring backend. Muốn export traces hoặc metrics tới hệ thống cụ thể, ứng dụng vẫn cần registry, tracing bridge/exporter và cấu hình tương ứng.

### 1.1. Những điểm có thể tạo overhead

| Thành phần | Hoạt động | Khi nào phát sinh chi phí |
| --- | --- | --- |
| Module entry spans | Intercept lời gọi tới Spring components thuộc module API và tạo Micrometer spans | Khi code đi qua module API được instrument |
| Event metrics | Cập nhật counter tổng và counter theo event type | Khi application event được publish |
| Application Module Actuator | Công bố module graph và dependency | Khi management endpoint được gọi |
| Metrics endpoint | Đọc/render meter đã đăng ký | Khi Actuator metrics endpoint được gọi |
| Prometheus scrape | Render và truyền toàn bộ sample được expose | Mỗi lần scraper poll endpoint |
| Trace exporter | Gom batch, serialize và gửi spans | Khi span được record và đến lịch export |
| Collector/backend | Nhận, xử lý, index và lưu telemetry | Theo lượng dữ liệu gửi đến |

Không phải mọi thành phần đều nằm trên business request path. Ví dụ /actuator/modulith chỉ được xử lý khi endpoint được gọi; chi phí render module graph không tự phát sinh trên mọi request nghiệp vụ. Ngược lại, module span và event counter có thể thêm công việc trực tiếp vào các lời gọi/event tương ứng.

### 1.2. Insight có thể tạo những tín hiệu nào?

Spring Modulith observability tạo module entry spans cho lời gọi tới Spring components nằm trong API của module. Các tag mô tả module và method gồm:

- module.identifier.
- module.invocation-type.
- module.method.
- module.name.

Spring Modulith cũng đăng ký hai event metrics:

- module.events.published: counter tổng hợp event publication.
- module.events.published.$moduleIdentifier.$simpleEventTypeName: counter riêng cho event type.

Các tín hiệu này có chi phí khác nhau. Span cần context, recording/sampling và export; counter cần meter lookup/update và tạo series; Actuator cần xử lý request quản trị.

## 2. Xác định câu hỏi cần trả lời trước khi benchmark

Không nên bắt đầu bằng câu hỏi chung "Insight chậm bao nhiêu phần trăm?". Hãy chuyển thành các giả thuyết có thể đo:

1. Bật module spans có làm tăng p95 latency của lời gọi xuyên module không?
2. Event metrics có ảnh hưởng đáng kể tới throughput khi publish event với tốc độ cao không?
3. Số meter/time series tăng bao nhiêu sau khi ứng dụng chạy đủ các event types?
4. Export traces tới Collector làm tăng CPU, allocation hoặc queue pressure bao nhiêu?
5. Prometheus scrape có làm tăng CPU và response time của management server không?
6. Thời gian startup và thời điểm readiness có thay đổi không?
7. Với cùng business throughput, tỷ lệ lỗi, heap và GC có thay đổi vượt ngân sách không?

Mỗi câu hỏi cần một workload và phép đo riêng. Nếu thay đồng thời sampling, scrape interval, custom tags và số replica, kết quả không cho biết yếu tố nào tạo ra khác biệt.

## 3. Thiết kế baseline và các biến thể

Một phép so sánh tốt cần giữ các yếu tố khác nhau ở mức tối thiểu. Dùng cùng source revision và tạo các build/profile thử nghiệm có dependency/configuration khác nhau.

### 3.1. Ma trận thử nghiệm đề xuất

| Biến thể | Cấu hình | Mục đích |
| --- | --- | --- |
| A — Baseline | Ứng dụng không có Spring Modulith Insight; giữ nguyên business logic và hạ tầng benchmark | Mốc hiệu năng ban đầu |
| B — Actuator control | Có Spring Boot Actuator và cùng metrics registry nhưng chưa bật Modulith observability | Đo chi phí nền của management/metrics infrastructure |
| C — Insight | Bật spring-modulith-starter-insight, tracing bridge và sampling policy được chọn | Đo tổng tác động của Insight trong cấu hình ứng dụng |
| D — Insight + scrape | Giống C, thêm Prometheus scrape theo interval dự kiến production | Đo tác động khi có scraper |
| E — Insight + export path | Giống C, gửi trace tới Collector test/staging với network và exporter gần production | Đo chi phí export và xử lý telemetry |

Không phải dự án nào cũng cần đủ năm biến thể. Nếu chỉ cần quyết định bật Insight hay không, A và C là phép so sánh chính; B, D và E giúp giải thích phần overhead đến từ đâu.

### 3.2. Giữ hạ tầng chung giữa baseline và Insight

Khi mục tiêu là đo riêng phần Modulith, giữ các yếu tố sau giống nhau:

- JDK distribution/version và JVM flags.
- Spring Boot version và các dependency chung.
- CPU/memory quota, container limits và node type.
- Heap size, garbage collector và container runtime.
- Database, broker và dataset.
- Số replica và concurrency.
- Business code, listener, transaction boundaries và request mix.
- HTTP client/server instrumentation chung nếu đang có.

Nếu baseline không có tracing infrastructure nhưng bản Insight có tracing bridge/exporter, phép so sánh A-C đo tổng chi phí của cả hai thay đổi. Hãy ghi rõ điều đó. Nếu muốn tách riêng Modulith instrumentation, giữ tracing bridge và exporter chung ở cả hai biến thể, rồi chỉ bật/tắt Modulith observability giữa chúng.

### 3.3. Tránh cấu hình giả tạo

Không tắt sampling, exporter hoặc instrumentation bằng một property tự suy đoán. Chỉ dùng cấu hình được tài liệu của đúng phiên bản Spring Boot/Spring Modulith hỗ trợ.

Nếu cần tách thành phần để đo, dùng các build variants hoặc profile rõ ràng:

- Actuator-only control.
- Modulith observability enabled.
- Modulith observability với exporter/scrape production-like.

Không dùng một profile benchmark khác xa production rồi lấy kết quả đó làm overhead production.

## 4. Xác định workload cho từng loại overhead

Insight tác động ở nhiều điểm. Nên tạo ít nhất ba workload riêng và một workload end-to-end.

### 4.1. Workload A — Event publication

Mục tiêu: đo tác động của event metrics khi application publish nhiều domain events.

Thiết kế:

1. Dùng cùng event type và cùng phân bố module.
2. Gọi ApplicationEventPublisher.publishEvent() qua đường xử lý thực tế.
3. Giữ listener và transaction logic giống nhau.
4. Không thêm custom tag trong lần đo đầu.
5. Đo event publications/second, publish path latency, CPU và allocation.

Với hai counters mặc định, có thể ước lượng ban đầu:

```text
counter updates / second
  ≈ event publications / second × 2
```

Đây là mô hình ước lượng theo hai metric được tài liệu công bố, không phải cam kết về số thao tác nội bộ của mọi phiên bản. Kiểm tra meter thực tế và đo trên workload đang chạy.

### 4.2. Workload B — Lời gọi xuyên module

Mục tiêu: đo chi phí module entry spans.

Thiết kế:

1. Gọi Spring bean thông qua module API.
2. Tạo chuỗi lời gọi qua hai hoặc nhiều module.
3. Giữ method body và số lần gọi giống nhau giữa các biến thể.
4. Đo latency của boundary method và request tổng.
5. Đếm số module invocations để tính overhead theo một request.

Đảm bảo benchmark thực sự đi qua Spring-managed components thuộc module API. Gọi trực tiếp một object được tạo bằng new hoặc gọi method nội bộ không đi qua boundary instrumented có thể không tạo cùng loại span.

### 4.3. Workload C — Management endpoint và scrape

Mục tiêu: đo chi phí chỉ phát sinh khi endpoint được gọi.

Đo riêng:

- /actuator/modulith.
- /actuator/metrics.
- /actuator/metrics/module.events.published.
- /actuator/prometheus.

Với mỗi endpoint, ghi response bytes, p50/p95 latency, request rate và CPU khi scrape. Không trộn traffic management vào latency của business endpoint nếu muốn đo request path riêng.

### 4.4. Workload D — End-to-end

Chạy một flow gần production, ví dụ:

```text
POST /orders
  -> orders.CheckoutService
  -> pricing.QuoteService
  -> payments.PaymentService
  -> publish OrderPlaced
  -> inventory.OrderPlacedListener
```

Đo throughput và latency tổng, đồng thời xác nhận module spans và event counters xuất hiện. Workload này cho biết tác động tổng hợp trong luồng thực tế; các workload A/B/C giúp giải thích nguyên nhân.

## 5. Chuẩn bị cấu hình Insight

Ví dụ Gradle dependency:

```groovy
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
}
```

Dependency version nên được quản lý bằng Spring Modulith BOM/dependency management tương thích với Spring Boot của dự án.

Nếu dùng Prometheus, bổ sung registry:

```groovy
dependencies {
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Nếu cần trace export, bổ sung tracing bridge và exporter theo stack được chọn. Insight starter không tự thêm mọi exporter hoặc tự quyết định backend.

### 5.1. Sampling phải giống nhau giữa các lần đo

Với Spring Boot, sampling probability thường được cấu hình qua:

```yaml
management:
  tracing:
    sampling:
      probability: 0.1
```

Spring Boot hiện hành mặc định sampling 10% request. Tuy nhiên, hãy đọc cấu hình effective của dự án và ghi rõ sampler thực tế. Nếu biến thể A không tạo module spans còn C có, phần chênh lệch bao gồm chi phí recording/export của số trace được sample.

Không so sánh baseline không có trace với Insight ở sampling 100% rồi kết luận tỷ lệ overhead đó sẽ xuất hiện khi production sampling 10%.

### 5.2. Giữ exporter và Collector ổn định

Nếu đo export overhead:

- Dùng cùng Collector version/config trong các lần chạy.
- Đặt Collector trên hạ tầng ổn định, tốt nhất tách khỏi process ứng dụng.
- Ghi endpoint, protocol, TLS, compression, batch và retry settings.
- Theo dõi exporter queue, send failures và Collector CPU/memory.
- Không thay backend hoặc network path giữa hai lần chạy.

Để đo phần chi phí do exporter, có thể so sánh cùng instrumentation/sampling với exporter path được cấu hình và không được cấu hình, nhưng cần ghi rõ đây là hai cấu hình telemetry khác nhau. Không diễn giải kết quả thành chi phí của module spans thuần túy.

## 6. Quy trình chạy benchmark có kiểm soát

### 6.1. Chuẩn hóa môi trường

Trước mỗi lần chạy, ghi lại:

| Thông tin | Giá trị cần ghi |
| --- | --- |
| Git revision | Commit SHA của source |
| Build variant | Baseline, Actuator-only, Insight, Insight + scrape/export |
| JDK/JVM | Vendor, version, flags |
| Spring Boot | Version |
| Spring Modulith | Version |
| Micrometer/tracing bridge | Version |
| CPU/memory | Container limit và host/node |
| Heap/GC | Heap min/max, collector |
| Dependencies | Database, broker, registry, exporter |
| Workload | Request/event mix, rate, concurrency, duration |
| Sampling | Sampler, probability và parent behavior |
| Scrape | Interval, target và số series |

Không dùng chung một Collector process đang bị workload khác làm nóng hoặc quá tải cho các lần benchmark.

### 6.2. Warm-up

JVM cần thời gian khởi động JIT, cache, connection pool và Micrometer registry. Mỗi lần chạy nên có:

1. Startup riêng.
2. Warm-up workload đủ để JIT và connection pool ổn định.
3. Giai đoạn đo chính.
4. Cool-down hoặc drain request đang chạy.

Không lấy số liệu startup/warm-up làm steady-state performance.

### 6.3. Dùng arrival rate ổn định

Với load test HTTP, ưu tiên mô hình arrival-rate/open workload nếu mục tiêu là giữ lượng request đến ổn định. Khi server chậm, closed-loop client có thể tự giảm tốc độ gửi request và che giấu việc throughput bị suy giảm.

Ghi rõ:

- Target requests/second.
- Số virtual users hoặc concurrency.
- Timeout.
- Ramp-up.
- Duration.
- Error threshold.

Nếu dùng k6, có thể bắt đầu với executor constant-arrival-rate; với Gatling, dùng injection profile phù hợp. Cấu hình cụ thể phải dựa trên capacity test của ứng dụng.

### 6.4. Lặp lại và đổi thứ tự

Chạy mỗi biến thể nhiều lần, ví dụ tối thiểu năm lượt sau warm-up. Xen kẽ hoặc ngẫu nhiên thứ tự chạy để giảm bias do nhiệt độ CPU, cache, noisy neighbor hoặc backend drift.

So sánh median và percentile giữa các lần chạy. Nếu chênh lệch nhỏ hơn dao động giữa các lượt, chưa đủ bằng chứng để quy kết cho Insight.

## 7. Chỉ số cần thu thập

### 7.1. Business performance

| Chỉ số | Ý nghĩa |
| --- | --- |
| Throughput | Số request/event xử lý mỗi giây |
| p50 latency | Độ trễ điển hình |
| p95 latency | Độ trễ của nhóm request chậm |
| p99 latency | Đuôi phân phối, nhạy với pause và contention |
| Error rate | Tỷ lệ request/event thất bại |
| Queue/consumer lag | Tác động lên async flow nếu có |

Không chỉ nhìn average latency. Insight có thể có tác động nhỏ lên trung bình nhưng rõ hơn ở p99 khi có allocation, contention hoặc export pressure.

### 7.2. JVM và process

Thu thập:

- Process CPU usage.
- Heap used/committed.
- Allocation rate.
- GC count và pause duration.
- Thread count và executor queue.
- Class loading và JIT compilation khi đo startup.
- Container CPU throttling và memory pressure.

Spring Boot Actuator/Micrometer cung cấp JVM, process, system và application metrics nếu các registry/instrumentation tương ứng được cấu hình. Dùng cùng nguồn đo ở tất cả biến thể.

### 7.3. Observability overhead

Ghi riêng:

- Số meter và active time series.
- Event counter rate.
- Số module spans được tạo/record/export.
- Trace sampling probability.
- Export queue size và dropped spans.
- Export duration/send failures.
- /actuator/prometheus response bytes và duration.
- /actuator/modulith response bytes và duration.
- Prometheus scrape duration và samples ingested.

Không dùng số trace tìm thấy trên backend làm số invocation chính xác nếu sampling đang bật.

## 8. Đo startup và readiness

Insight thêm dependency và auto-configuration nên startup/ready time cũng cần được kiểm tra.

Spring Boot công bố các application startup metrics:

- application.started.time: thời gian từ lúc bắt đầu startup đến khi application context đã khởi động.
- application.ready.time: thời gian đến khi ứng dụng sẵn sàng phục vụ request.

So sánh hai meter này giữa baseline và Insight trên cùng JVM/hạ tầng. Ngoài ra, ghi wall-clock từ lúc process start đến readiness probe success để bao gồm startup behavior thực tế của deployment.

Không chỉ nhìn application.started.time: instance có thể khởi động context xong nhưng còn startup tasks hoặc readiness chưa chuyển sang nhận traffic.

## 9. Tách riêng từng nguồn overhead

### 9.1. Module spans

Đo lời gọi qua module API với cùng số lần invocation. So sánh:

- Latency của boundary method.
- Request p95/p99.
- CPU và allocation.
- Số span được record/export.

Tác động có thể phụ thuộc số boundary calls trên mỗi request. Một request gọi qua 20 module API có thể tạo nhiều span hơn request chỉ gọi qua một boundary.

### 9.2. Event metrics

Đo workload publish event với cùng event type distribution. So sánh:

- Event publications/second.
- Publish path latency.
- CPU/allocation.
- Số meter/series sau khi các event types xuất hiện.

Hai counters mặc định có thể được cập nhật theo mỗi event publication. Tăng event rate làm số counter updates tăng, nhưng không nhất thiết làm cardinality tăng nếu tên meter và tag set giữ nguyên.

### 9.3. Actuator management endpoint

Gọi endpoint theo tần suất kiểm soát, tách khỏi business load:

| Endpoint | Đo gì |
| --- | --- |
| /actuator/modulith | Chi phí tạo/serialize response module graph |
| /actuator/metrics | Chi phí liệt kê meter |
| /actuator/metrics/module.events.published | Chi phí đọc một meter cụ thể |
| /actuator/prometheus | Chi phí render exposition format và payload |

Không gọi /actuator/modulith liên tục để mô phỏng traffic nghiệp vụ. Endpoint này thường được dùng để kiểm tra kiến trúc hoặc bởi công cụ quản trị, không phải API business hot path.

### 9.4. Exporter và Collector

So sánh khi có cùng số span được record:

- Exporter disabled/no external export path (nếu cấu hình stack cho phép).
- Exporter enabled tới Collector ổn định.
- Collector forwarding tới backend thực tế.

Đo CPU ứng dụng, allocation, queue, send failures, Collector CPU/memory và backend ingestion. Nếu chỉ đo response time của ứng dụng mà bỏ qua Collector, bạn có thể bỏ sót nơi chi phí chuyển sang.

## 10. Bảng kết quả benchmark

Dùng bảng sau để ghi số liệu thực tế; không điền giá trị ước đoán thay cho phép đo:

| Chỉ số | Baseline | Actuator-only | Insight | Insight + scrape/export |
| --- | ---: | ---: | ---: | ---: |
| Throughput (req/s) | — | — | — | — |
| p50 latency (ms) | — | — | — | — |
| p95 latency (ms) | — | — | — | — |
| p99 latency (ms) | — | — | — | — |
| Error rate (%) | — | — | — | — |
| CPU (%) | — | — | — | — |
| Heap used (MB) | — | — | — | — |
| Allocation (MB/s) | — | — | — | — |
| GC pause (ms/min) | — | — | — | — |
| Startup time (s) | — | — | — | — |
| Ready time (s) | — | — | — | — |
| Active time series | — | — | — | — |
| Prometheus payload (KB) | — | — | — | — |
| Export failures | — | — | — | — |

### 10.1. Tính overhead phần trăm

Với chỉ số mà giá trị tăng là xấu, như latency hoặc CPU:

```text
overhead (%) = (Insight - Baseline) / Baseline × 100
```

Với throughput, chiều tốt/xấu ngược lại:

```text
throughput change (%) = (Insight - Baseline) / Baseline × 100
```

Ví dụ nếu p95 baseline là 100 ms và Insight là 104 ms:

```text
(104 - 100) / 100 × 100 = 4% p95 latency increase
```

Đây là ví dụ tính toán, không phải kết quả benchmark của một ứng dụng cụ thể.

### 10.2. Đọc kết quả theo phân phối

Nếu p50 gần như không đổi nhưng p99 tăng:

- Kiểm tra allocation spikes và GC pauses.
- Kiểm tra export batch hoặc queue contention.
- Kiểm tra CPU throttling và thread pool saturation.
- Xem số module spans trên request chậm.

Nếu throughput giảm nhưng latency không đổi, có thể load generator, CPU quota hoặc concurrency đang giới hạn. Đừng quy kết cho Insight khi workload không giữ được target arrival rate.

## 11. Công cụ đo phù hợp

### 11.1. Load generator

- k6: phù hợp với HTTP arrival-rate profile và kịch bản API lặp lại.
- Gatling: phù hợp với workload nhiều bước, phân phối dữ liệu và concurrency.
- wrk/wrk2: phù hợp với benchmark HTTP đơn giản; cần chú ý open-loop/constant-rate behavior.
- Integration test: phù hợp đo event publication và module boundary bên trong ứng dụng.

Giữ nguyên script, dataset và target rate giữa các build.

### 11.2. JVM profiling

**Java Flight Recorder (JFR)** giúp xem:

- CPU samples và hot methods.
- Allocation by class/call path.
- Garbage collection và pause.
- Thread park/lock contention.
- Socket/file I/O và thread activity.

Chạy JFR với cấu hình tương đương cho baseline và Insight. Dùng profile duration đủ dài và so sánh cùng workload. JFR có overhead riêng, vì vậy bật ở cả hai biến thể hoặc thực hiện một vòng profiling riêng ngoài vòng latency chính.

### 11.3. Micrometer và Actuator

Dùng cùng meter registry ở mọi biến thể để lấy JVM/process metrics. Nếu expose endpoint, giới hạn danh sách endpoint cần thiết:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus,modulith
```

Endpoint metrics và prometheus cần registry/exposure phù hợp. Endpoint modulith cần Insight hoặc dependency Actuator của Spring Modulith.

### 11.4. JMH dùng đúng phạm vi

JMH phù hợp để đo một thao tác nhỏ, ví dụ so sánh counter update của registry trong điều kiện thread contention. Nó không thay thế benchmark toàn ứng dụng vì không đại diện đầy đủ event dispatch, transaction, module proxy, exporter và network.

Nếu dùng JMH, ghi fork count, warmup iterations, measurement iterations, thread count và registry implementation. Dùng kết quả như dữ liệu bổ sung để giải thích hot path, không làm tiêu chí duy nhất để quyết định bật Insight.

## 12. Tiêu chí chấp nhận trước khi bật production

Đặt ngưỡng dựa trên SLO và ngân sách của dịch vụ. Ví dụ cấu trúc tiêu chí:

| Hạng mục | Điều kiện chấp nhận |
| --- | --- |
| Business latency | p95/p99 vẫn trong SLO và mức tăng không vượt budget đã duyệt |
| Throughput | Đạt target arrival rate với error rate trong ngưỡng |
| CPU | Có headroom cho peak traffic và burst |
| Memory/GC | Heap, allocation và pause không gây pressure vượt ngưỡng |
| Startup/readiness | Ready time vẫn đáp ứng rollout/startup budget |
| Metrics cardinality | Active series và scrape payload trong budget |
| Trace export | Queue không tăng liên tục, dropped/send-failed spans trong ngưỡng |
| Actuator | Management endpoint trả lời trong timeout monitoring |
| Correctness | Event metrics, module spans và module graph phản ánh đúng |

Không đặt một ngưỡng overhead cố định cho mọi dịch vụ. Một API có SLO p99 chặt có thể cần budget khác với batch worker. Ghi ngưỡng trước benchmark để tránh điều chỉnh tiêu chí sau khi nhìn kết quả.

## 13. Tối ưu nếu overhead vượt budget

### 13.1. Kiểm tra số boundary calls

Nếu một request tạo quá nhiều module spans:

- Xem module API có bị gọi lặp trong vòng lặp không.
- Kiểm tra dependency graph và call pattern.
- Đo số span/request theo từng operation.
- Chỉ thay đổi instrumentation sau khi xác định boundary thực sự có giá trị quan sát.

Không bỏ module boundary chỉ để giảm span nếu boundary đó có ý nghĩa kiến trúc hoặc cần điều tra.

### 13.2. Kiểm soát event metric cardinality

- Giữ module/event tags hữu hạn.
- Không thêm order ID, customer ID, request ID hoặc email làm tag.
- Chỉ thêm enum/nhóm giá trị đã chuẩn hóa.
- Đo active series sau khi chạy đủ event types.

Counter increment rate cao không nhất thiết gây cardinality cao; tag set động mới là yếu tố làm số series phình ra.

### 13.3. Điều chỉnh sampling có căn cứ

Nếu trace recording/export tạo tải lớn:

- Xem sampling probability và parent-based sampler.
- Đánh giá tỷ lệ trace giữ lại so với nhu cầu điều tra.
- Giữ trace lỗi/chậm bằng tail sampling nếu kiến trúc Collector hỗ trợ và đủ capacity.
- Đo ingress load, queue và backend storage sau thay đổi.

Sampling ảnh hưởng traces, không làm giảm event metrics counters. Không hạ sampling để xử lý một vấn đề cardinality do metric tags động.

### 13.4. Tối ưu scrape và exporter

- Chọn scrape interval theo độ trễ phát hiện cần thiết.
- Giảm số series bằng cách sửa tag schema tại nguồn.
- Kiểm tra response size và scrape duration.
- Điều chỉnh batch/queue sau khi đo throughput và memory.
- Đặt Collector gần workload khi network latency là yếu tố lớn.

Không tăng queue vô hạn để che giấu backend không đủ throughput.

### 13.5. Chỉ expose endpoint cần thiết

Management endpoint chỉ nên được scrape/gọi theo mục đích. Tránh polling module graph hoặc metrics endpoint với tần suất cao không cần thiết. Dùng health probes riêng cho orchestrator và metrics scrape interval riêng cho monitoring.

## 14. Rollout theo từng bước

1. **Baseline:** chạy benchmark trước Insight và lưu kết quả.
2. **Canary:** bật Insight trên một phần instance hoặc staging có traffic tương đương.
3. **Compare:** so throughput, latency, CPU, memory, GC, series và export metrics.
4. **Inspect:** xác nhận module spans và event counters có ích, không có tag cardinality bất thường.
5. **Tune:** điều chỉnh sampling, exporter, scrape và instrumentation theo dữ liệu.
6. **Expand:** mở rộng rollout khi mọi tiêu chí chấp nhận đạt.
7. **Rollback:** khôi phục dependency/config version trước đó nếu SLO hoặc resource budget vượt ngưỡng.

Trong rolling deployment, so sánh canary và baseline ở cùng thời điểm nếu có thể. Traffic mix, campaign hoặc downstream degradation có thể làm kết quả trước/sau khác nhau dù Insight không đổi.

## 15. Bảng chẩn đoán kết quả

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| p95 tăng ở workload xuyên module | Module span creation, proxy/interceptor hoặc allocation | JFR hot methods, số span/request, boundary latency |
| Event publish throughput giảm | Counter update, meter lookup hoặc registry contention | Workload event-only, CPU profile, meter count |
| CPU tăng khi Prometheus scrape | Nhiều series hoặc render payload lớn | Response bytes, scrape rate, active series |
| Heap tăng sau khi bật Insight | Meter/tag set tăng, exporter queue hoặc trace buffers | Heap histogram, meter count, queue metrics |
| p99 tăng theo chu kỳ export | Batch export, network hoặc Collector backpressure | JFR I/O, exporter duration/queue, Collector logs |
| Startup/readiness chậm | Thêm auto-configuration/dependencies hoặc startup instrumentation | application.started.time, application.ready.time, startup logs |
| Metrics tăng nhưng trace count thấp | Sampling thấp hoặc exporter drop | Sampling config, sampled spans, send failures |
| Trace volume tăng nhưng event metrics không đổi | Sampling/export policy thay đổi; event volume giữ nguyên | Tách trace pipeline khỏi counter rate |
| /actuator/modulith chậm nhưng business latency ổn định | Management endpoint response/render cost | Đo endpoint riêng, không gộp với business request |
| Active series tăng nhanh | Custom tag có cardinality cao | Xem tag values và customizer |

## 16. Bài tập tự kiểm tra

**Câu 1.** Insight có thể thêm overhead vào những điểm nào của ứng dụng? Điểm nào không nằm trên mọi business request?

**Câu 2.** Vì sao baseline và Insight cần dùng cùng JDK, heap, CPU quota, database và workload?

**Câu 3.** Bạn cần đo event metrics. Vì sao nên tạo workload publish event riêng thay vì chỉ dùng HTTP endpoint tổng hợp?

**Câu 4.** Một request gọi qua 12 module API. Vì sao số module spans có thể ảnh hưởng latency khác với request chỉ đi qua một module boundary?

**Câu 5.** Prometheus scrape tăng từ 15 giây lên 5 giây. Điều này có làm tăng counter increments trong ứng dụng không? Những chi phí nào thay đổi?

**Câu 6.** JFR cho thấy allocation tăng nhưng p50 không đổi, p99 tăng. Cần kiểm tra những tín hiệu nào?

**Câu 7.** Sampling giảm từ 10% xuống 1%, event metric counter có giảm theo không?

**Câu 8.** Vì sao không thể dùng một benchmark JMH cho Counter.increment() để kết luận toàn bộ overhead của Insight?

### Gợi ý đáp án

1. Module spans phát sinh khi lời gọi đi qua module API instrumented; event counters phát sinh khi publish event; Actuator render khi management endpoint được gọi; scrape/export phát sinh theo pipeline. Module graph endpoint không chạy trên mọi business request.
2. Để giảm biến gây nhiễu và quy khác biệt cho đúng thành phần đang so sánh.
3. Vì HTTP flow có thể gồm database, transaction, listener và nhiều module calls; workload event-only giúp tách counter update khỏi các chi phí khác.
4. Nhiều boundary calls tạo nhiều span hơn, tăng context/span creation, recording và export; tổng chi phí phụ thuộc call count và sampling.
5. Không. Event counter vẫn tăng theo event publication. Scrape thường xuyên hơn làm tăng render, network, samples/second và backend ingestion.
6. Kiểm tra allocation hot spots, GC pause, exporter batch, queue, CPU throttling và số span/request.
7. Không. Trace sampling quyết định spans được ghi/export; event counters độc lập với sampling.
8. JMH không mô phỏng đầy đủ Spring proxy, event dispatch, transaction, context propagation, scrape, exporter và Collector.

## 17. Checklist benchmark và production rollout

- [ ] Đã ghi source revision, JDK, Spring Boot, Spring Modulith và Micrometer versions.
- [ ] Đã tạo baseline và Insight variant trên cùng business code.
- [ ] Đã giữ CPU/memory quota, heap, GC, database và dataset giống nhau.
- [ ] Đã tách event publication workload khỏi cross-module invocation workload.
- [ ] Đã đo Actuator endpoint và Prometheus scrape riêng.
- [ ] Đã đo exporter/Collector path với cấu hình có thể tái lập.
- [ ] Đã warm-up JVM và chạy nhiều lượt đo.
- [ ] Đã giữ target arrival rate và ghi error rate.
- [ ] Đã thu thập throughput, p50/p95/p99, CPU, allocation, GC và ready time.
- [ ] Đã ghi meter count, active series, scrape payload và export failures.
- [ ] Đã giữ sampling policy giống nhau hoặc ghi rõ khác biệt giữa biến thể.
- [ ] Đã kiểm tra event metrics không bị nhầm với trace sampling.
- [ ] Đã đặt acceptance criteria trước khi xem kết quả.
- [ ] Đã có canary, rollback và người chịu trách nhiệm.

## 18. Ghi nhớ

Đo overhead của Insight cần tách ba nhóm chi phí: **instrumentation trên business path, management/scrape và export/backend pipeline**. Module spans phát sinh khi lời gọi đi qua module API được instrument; event counters tăng khi event được publish; Actuator endpoint và Prometheus scrape chỉ tạo thêm tải khi được gọi.

Hãy so sánh baseline với Insight bằng cùng source, JVM, hạ tầng và workload. Đo riêng event publication, cross-module invocation, management endpoint và end-to-end flow; thu thập throughput, p95/p99, CPU, allocation, GC, startup/readiness, series và exporter queue. Giữ sampling/scrape policy ổn định, chạy nhiều lượt và đặt acceptance criteria trước rollout. Chỉ điều chỉnh instrumentation, tags, sampling hoặc scrape sau khi xác định đúng nguồn overhead bằng dữ liệu.

### Tài liệu tham khảo

- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): Insight starter, module entry spans, event metrics và customizer.
- [Spring Modulith — Appendix: Modules](https://docs.spring.io/spring-modulith/reference/appendix.html): thành phần được Insight starter kéo theo.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer registry, JVM/process metrics và metrics endpoint.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): Observation pipeline và cấu hình instrumentation.
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html): Observation tạo metrics và spans.
- [Micrometer — Concepts](https://docs.micrometer.io/micrometer/reference/concepts.html): meter types, registry và tag/cardinality concepts.
- [Java Flight Recorder](https://docs.oracle.com/en/java/javase/21/jfapi/): ghi nhận và phân tích hoạt động JVM.
- [k6 — Constant Arrival Rate](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/): tạo workload với arrival rate ổn định.
