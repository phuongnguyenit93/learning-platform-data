# Đo lường trước khi thay đổi kích thước nhóm luồng hoặc bộ thực thi

## 1. Vì sao không nên “tăng thread” khi ứng dụng chậm?

Trong một ứng dụng Spring Boot, thời gian phản hồi tăng có thể đến từ CPU, database, API bên ngoài, kết nối mạng, garbage collection, hàng đợi, hoặc từ chính cách tác vụ được phân phối đến luồng. Nếu chỉ nhìn thấy request chậm rồi tăng `server.tomcat.threads.max` hay `spring.task.execution.pool.max-size`, ta có thể làm hệ thống **chậm hơn** vì tăng cạnh tranh CPU, bộ nhớ, kết nối database hoặc khiến một dịch vụ phụ thuộc quá tải.

**Nguyên tắc của bài học:** đo **lưu lượng → thời gian chờ → thời gian chạy → mức bận của tài nguyên → hàng đợi/lỗi từ chối**, rồi mới đặt giả thuyết và thay đổi **một tham số** trong điều kiện tải có thể so sánh. Mục tiêu là đáp ứng SLO với tài nguyên và độ ổn định phù hợp, không phải tối đa số luồng.

Sau bài này, bạn có thể:
- Xác định đúng thread pool/executor đang xử lý yêu cầu hoặc tác vụ.
- Chọn các metric nền để biết hệ thống đang thiếu khả năng xử lý, đang bị nghẽn bên ngoài, hay đo sai đối tượng.
- Ghi baseline, đọc p95/p99, throughput, queue wait, saturation, rejection, CPU/GC.
- Ước lượng concurrency bằng Little's Law và hiểu giới hạn của các công thức sizing.
- Làm thí nghiệm trước/sau, đưa ra quyết định tăng, giảm hoặc giữ nguyên kích thước pool.
- Phân biệt pool Servlet/Tomcat, `@Async`/`ThreadPoolTaskExecutor`, `@Scheduled`, WebFlux và virtual threads.

> **Phạm vi:** kiến thức áp dụng cho Java 17+ và Spring Boot web-runtime. Ví dụ Java độc lập dùng Java 17. Cấu hình Actuator và pool minh họa Spring Boot 3.5/4.x với platform threads; trước khi áp dụng phải đối chiếu chính xác phiên bản và loại server của dự án.

## 2. Tìm đúng pool trước khi tối ưu

Trong cùng một Spring Boot service có thể tồn tại nhiều nhóm luồng và tài nguyên giới hạn độc lập. Chúng không có một “maxThreads” dùng chung.

| Thành phần | Nhiệm vụ chính | Cần đo | Nút chỉnh nếu thực sự là điểm nghẽn |
|---|---|---|---|
| **Tomcat/Jetty request workers** trong Spring MVC | Chạy request xử lý qua Servlet stack | Luồng bận/tối đa, request latency, mức chờ, HTTP error, CPU | Thuộc tính của embedded server, ví dụ `server.tomcat.threads.max` |
| **`ThreadPoolTaskExecutor` / `@Async`** | Chạy tác vụ được gửi vào executor (cũng có thể phục vụ cơ chế MVC async) | Active/pool size, queue depth, queue wait, thời gian chạy, số reject | `corePoolSize`, `maxPoolSize`, `queueCapacity`, policy |
| **`ThreadPoolTaskScheduler` / `@Scheduled`** | Kích hoạt công việc theo lịch | Lateness, số task chồng lấn, thời gian thực thi, task bỏ lỡ | Kích thước scheduler cùng cách lập lịch |
| **Reactor Netty event loops / WebFlux** | Xử lý I/O không chặn và callback trên event loop | Event-loop lag, latency, blocked tasks, CPU; các bounded queue liên quan | Gỡ blocking operation, chuyển việc blocking sang scheduler phù hợp; chỉ chỉnh event loop khi có bằng chứng |
| **Reactor `boundedElastic` / custom Scheduler** | Cách ly tác vụ blocking trong chương trình reactive | Số tác vụ chạy/chờ, queue, thời gian chờ, reject | Giới hạn scheduler/bounded concurrency và tốc độ nguồn |
| **HikariCP / JDBC connections** | Cấp kết nối database; **không phải** Java thread pool | Active, idle, pending, acquisition time, DB utilization | Tối ưu SQL/transaction, giới hạn concurrency, điều chỉnh pool DB khi có bằng chứng |
| **Worker của message consumer** | Xử lý message từ Kafka/RabbitMQ hoặc hệ thống hàng đợi | Consumer lag, time per message, retries, DLQ, partition/concurrency | Concurrency của consumer, backpressure, throughput dependency |

**Ví dụ sai đối tượng:** một request MVC nhận yêu cầu, gọi `@Async("reportExecutor")` rồi chờ `CompletableFuture.join()`. Nếu `reportExecutor` có hàng đợi dày, tăng Tomcat workers không làm executor hoàn thành nhanh hơn; request có thể còn giữ thêm Tomcat threads trong khi chờ. Hãy tìm điểm chờ **thực tế** trong trace/thread dump và metric của **reportExecutor**.

**Ví dụ khác:** một ứng dụng WebFlux dùng Reactor Netty nhưng code handler gọi JDBC đồng bộ ngay trên event loop. Vấn đề không được giải quyết bằng cấu hình `spring.task.execution.pool.max-size`, trừ khi đoạn code đó thực sự chạy trên Boot task executor. Việc đầu tiên là nhận diện blocking call trên event loop và thiết kế cách cách ly/giảm blocking phù hợp.

### Cách xác định pool thực sự được dùng

1. Đọc loại ứng dụng từ log và context: Spring MVC/Servlet hay WebFlux/Reactive; server thực tế là Tomcat, Jetty hay Netty.
2. Với `@Async`, xem annotation có tên executor hay không: `@Async("someExecutor")`, cấu hình `AsyncConfigurer`, bean executor, và auto-configuration.
3. Với `@Scheduled`, xem scheduler thực tế và cách lên lịch (`fixedDelay`, `fixedRate`, cron); không gán chậm trễ của scheduler cho web request pool.
4. Với custom `ExecutorService`, xem nơi tạo bean hoặc khởi tạo trong mã, và shutdown policy.
5. Đối chiếu **tên pool** trong metric với **tên thread** trong Java Flight Recorder (JFR)/thread dump. Đừng kết luận chỉ dựa trên tổng số JVM threads.

## 3. Bộ metric tối thiểu trước khi quyết định thay đổi

Hãy đo các giá trị trên cùng khoảng thời gian, cùng phiên bản ứng dụng, cùng số instance, cùng tải và cùng cấu hình phụ thuộc.

| Nhóm | Metric/cách hiểu | Câu hỏi cần trả lời |
|---|---|---|
| **Lưu lượng** | Requested/accepted/completed requests per second (RPS), tasks/s | Tải gửi đến và tải hoàn thành có lệch nhau không? |
| **Độ trễ** | p50, p95, p99; tách HTTP response time, queue wait, execution time, downstream wait | Người dùng chậm ở đoạn nào, tail latency có tăng không? |
| **Sức chứa pool** | `poolSize`, `corePoolSize`, `maxPoolSize`, `activeCount`, active/max theo thời gian | Pool có thật sự bão hòa, hay đang dư luồng? |
| **Hàng đợi** | Queue size/capacity, queue wait p95/p99, tốc độ tăng/giảm queue, oldest task age | Tác vụ đang được giữ lại bao lâu và queue có thể phục hồi không? |
| **Lỗi từ chối** | Rejected tasks/s, timeout, caller-runs, task drop, HTTP 429/503/5xx | Hệ thống đang quá giới hạn nào? Có mất việc hoặc lan truyền chậm không? |
| **CPU, memory, GC** | Container/host CPU %, quota/throttling, heap, live threads, GC pause, allocation | Tăng luồng có làm nghẽn CPU hoặc GC không? |
| **Downstream** | DB active/pending, connection acquisition time, SQL duration, external API p95, rate limit | Có đang chờ một tài nguyên khác thay vì chờ thread không? |
| **Độ ổn định** | Error rate, retry rate, saturation theo từng replica, cold/warm start | Cải thiện trung bình có khiến tail/error tệ hơn không? |

Phân biệt các số dễ gây nhầm:

- **Active threads** là số luồng đang thực hiện task tại thời điểm lấy mẫu; **pool size** là số luồng được tạo; **max pool size** là trần cấu hình. Một pool có 40 threads và 8 active không chứng minh có thể giảm ngay xuống 8, vì tải đỉnh có thể lớn.
- **Queue depth** là số task chờ tại một thời điểm; **queue wait time** là thời gian từ khi nộp đến lúc bắt đầu chạy. Queue size thấp không đủ bảo đảm p99 queue wait tốt, đặc biệt với đợt tăng tải ngắn.
- **Throughput hoàn thành** khác **tốc độ gửi vào**. Hệ thống có thể nhận 120 tác vụ/giây nhưng hoàn thành 90 tác vụ/giây, làm queue tăng khoảng 30 tác vụ/giây trong một đoạn ngắn. Nếu kéo dài, queue hoặc nguồn lực khác sẽ chạm giới hạn.
- **p95/p99** là phân vị, không phải trung bình. p99=800ms nghĩa là trong tập mẫu đang xét, khoảng 99% mẫu có độ trễ không vượt quá ngưỡng đó; việc so sánh cần đủ mẫu, cùng khoảng thời gian và cùng cách tính.
- **Saturation** không đơn thuần là số luồng cao: cần phối hợp active/max, độ chờ, reject và khả năng giữ ổn định khi tải tăng.
- **RejectedExecutionException** của `ThreadPoolExecutor` và `TaskRejectedException` trong đường Spring có thể xuất hiện ở những tầng khác nhau; các chính sách như `CallerRunsPolicy` còn có thể chuyển áp lực sang thread gọi mà không tăng counter lỗi rõ ràng.

**Metric nên có nhưng thường chưa có:** thời gian chờ **trong executor queue**. HTTP latency và tổng thời gian xử lý task có thể che mất khoảng chờ trước khi task bắt đầu. Với executor tự tạo, hãy ghi thời gian ngay trước `execute/submit`, đo tại đầu `Runnable` được thực thi và đếm reject/timeout. Gắn nhãn pool nhưng tránh label có cardinality cao như request ID hoặc user ID.

## 4. Thu thập số liệu trong Spring Boot bằng Actuator + Micrometer

Tùy phiên bản, Spring Boot Actuator tự động cung cấp metric JVM, hệ thống, HTTP, connection pool và các bean `ThreadPoolTaskExecutor`/`ThreadPoolTaskScheduler` phù hợp. **Hãy xem tên metric thực tế** qua endpoint `/actuator/metrics`; không suy luận tên metric từ tên bean hoặc format Prometheus.

### 4.1. Bật metric trong môi trường đo

Đoạn Gradle sau là **fragment** dành cho dự án Spring Boot đã được cấu hình plugin và repositories:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Ví dụ `application.yml` cho môi trường thử nghiệm có bảo vệ endpoint quản trị:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true

server:
  tomcat:
    mbeanregistry:
      enabled: true
~~~

Trong ví dụ này:
- `/actuator/metrics` hỗ trợ **chẩn đoán trực tiếp**, không thay cho hệ thống lưu time series production.
- `/actuator/prometheus` cung cấp dữ liệu cho Prometheus khi có registry tương ứng.
- Histogram của `http.server.requests` giúp tổng hợp latency quantile giữa nhiều instance. Cần cấu hình bucket và giới hạn cardinality hợp lý cho môi trường thực tế.
- `server.tomcat.mbeanregistry.enabled=true` chỉ có ý nghĩa khi ứng dụng dùng **Tomcat**; tài liệu Boot nêu Tomcat metrics cần bật MBean registry. Với Jetty/Netty, dùng metric của server thực tế.
- Giữ các endpoint quản trị trên mạng tin cậy hoặc áp dụng bảo mật phù hợp. Không tự mở các endpoint chẩn đoán ra Internet.

### 4.2. Khám phá meter hiện có

Sau khi chạy ứng dụng và đã có request/task thực thi:

~~~bash
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/metrics/http.server.requests
curl -s http://localhost:8080/actuator/metrics/jvm.threads.live
curl -s http://localhost:8080/actuator/prometheus
~~~

Đây là các lệnh **chỉ chạy được khi ứng dụng có các endpoint được bật tại port 8080**. Dữ liệu thực tế sẽ khác theo workload, container, phiên bản và tag; không có stdout cố định. Một meter không xuất hiện có thể do dependency, auto-configuration, endpoint chưa expose, chưa có traffic, hoặc loại executor/server không được instrument; **đừng coi giá trị “không có” là 0**.

Các nhóm cần chủ động tìm:
- `http.server.requests`: số lượng request, latency, tags phương thức/URI template/status khi có.
- `jvm.threads.*`, `jvm.gc.*`, `process.cpu.*` và `system.cpu.*`: sức khỏe JVM và hệ thống.
- `executor.*`: nhiều bean `ThreadPoolTaskExecutor` và `ThreadPoolTaskScheduler` sẽ có pool/queue/task metrics, được phân biệt bằng tag tên executor theo khả năng instrumentation.
- `tomcat.*` nếu có Tomcat và MBean registry; số lượng request worker bận và cấu hình tối đa là tín hiệu đáng theo dõi.
- `hikaricp.*` hoặc `jdbc.connections.*` nếu ứng dụng dùng datasource/HikariCP; phải đo cả tài nguyên này khi xử lý có truy cập DB.

Các tên có dấu chấm trên là tên **Micrometer/Actuator**, trong Prometheus có thể đổi sang dạng snake_case và hậu tố đơn vị. Không lấy tên Prometheus rồi thêm nguyên xi vào `/actuator/metrics/{name}`.

### 4.3. Dashboard thời gian và truy vấn tham khảo

Prometheus dùng time series; counter cần `rate(...)` hay `increase(...)`, histogram quantile cần bucket đã được phát hành. Ví dụ truy vấn cho HTTP timer mặc định (sửa selector/tag theo series thực tế):

~~~promql
sum(rate(http_server_requests_seconds_count[5m]))
~~~

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (rate(http_server_requests_seconds_bucket[5m]))
)
~~~

Hai truy vấn lần lượt ước lượng request/s và p95 từ histogram **trong khoảng 5 phút**. Nếu đo riêng endpoint hoặc từng ứng dụng, thêm selector đã xác thực. Với Prometheus, histogram có thể chưa tồn tại nếu chưa bật histogram hoặc không nhận được series tương ứng; đừng dùng truy vấn trả rỗng để kết luận p95=0.

**Dashboard tối thiểu** gồm 4 đồ thị cùng trục thời gian: RPS, p95/p99 + error rate, executor active/queue/reject, CPU + DB pending/GC. Đặt các mốc triển khai và thay cấu hình trên đồ thị. Nhìn từng biểu đồ riêng lẻ dễ bỏ qua sự lệch pha giữa đầu vào, queue và độ trễ.

## 5. Thực hành Java 17 — thấy rõ max threads không giải quyết queue vô hạn

`ThreadPoolExecutor` có thứ tự nhận task đặc thù:
1. Nếu đang có ít hơn `corePoolSize` workers, tạo thêm worker.
2. Khi đã đạt core size, ưu tiên đưa task vào queue nếu queue còn chỗ.
3. Chỉ khi queue đầy mới cố tạo worker mới tới `maximumPoolSize`.
4. Nếu không thể xếp queue hoặc tạo thêm worker, áp dụng `RejectedExecutionHandler`.

Vì vậy, **queue không giới hạn** khiến `maximumPoolSize` thông thường **không có cơ hội phát huy**. Đây là lý do nhiều người nâng `max-size` nhưng `active` vẫn không tăng và độ trễ vẫn dài.

Ví dụ độc lập dưới đây dùng **queue dung lượng 2** để ta có thể thấy hành vi. Lưu đúng tên tệp `SaturationDemo.java`:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class SaturationDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch release = new CountDownLatch(1);

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                2,                          // corePoolSize
                4,                          // maximumPoolSize
                30, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(2),
                new ThreadPoolExecutor.AbortPolicy()
        );

        Runnable blockedTask = () -> {
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        int accepted = 0;
        int rejected = 0;
        try {
            for (int i = 0; i < 8; i++) {
                try {
                    pool.execute(blockedTask);
                    accepted++;
                } catch (RejectedExecutionException e) {
                    rejected++;
                }
            }
            System.out.printf(
                    "accepted=%d rejected=%d%n", accepted, rejected);
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac SaturationDemo.java
java SaturationDemo
~~~

Stdout mong đợi:

~~~text
accepted=6 rejected=2
~~~

**Vì sao có kết quả này?** Trong thời gian submit, các task đang chạy phải chờ latch; pool không thể hoàn thành chúng trước khi mở latch. Hai task đầu dùng core workers, hai task tiếp nằm trong queue, hai task tiếp khiến pool tăng từ 2 lên 4 workers; hai task cuối bị reject do pool đã ở max và queue đầy. Sau khi in số, `finally` mở latch và shutdown sạch.

Đây là **thí nghiệm minh họa cơ chế**, không phải benchmark tính throughput hay bằng chứng chọn pool 4 cho ứng dụng thật. Đặc biệt, gọi `activeCount()` ở một thời điểm đơn lẻ có thể không ổn định do scheduling; muốn đánh giá thực tế phải lấy mẫu theo thời gian, có load test và thời gian xử lý giống workload nghiệp vụ.

### Tự đối chiếu với Spring

`ThreadPoolTaskExecutor` là wrapper quanh `ThreadPoolExecutor`. Trong ứng dụng Boot sử dụng **platform threads**, các thuộc tính `spring.task.execution.pool.core-size`, `max-size` và `queue-capacity` có thể được dùng để cấu hình auto-configured executor. Ví dụ **chỉ là ứng viên thử nghiệm sau khi đo**, không phải giá trị khuyến nghị chung:

~~~yaml
spring:
  task:
    execution:
      pool:
        core-size: 8
        max-size: 24
        queue-capacity: 100
        keep-alive: 30s
~~~

Một custom `ThreadPoolTaskExecutor` bean có thể có thiết lập riêng, và `@Async("namedExecutor")` có thể không dùng auto-configured executor. Phải xác định đúng bean trước khi tin rằng `spring.task.execution.*` đang điều khiển các task cần tối ưu.

## 6. Lập baseline có thể so sánh

Ghi baseline **trước khi sửa** bất kỳ giới hạn nào. Một lần đo tốt cần có thông tin này:

| Cần lưu | Vì sao |
|---|---|
| Version JDK, Spring Boot, image/build, commit và cấu hình pool hiện tại | Tránh so sánh hai phiên bản hoặc thay đổi thuật toán khác nhau |
| Số instance/pod, CPU quota, RAM limit, số vCPU khả dụng | Cùng pool size nhưng tài nguyên khác sẽ cho kết quả khác |
| Loại server và pool/executor, cơ chế rejected policy, queue capacity | Biết chính xác giới hạn cần đánh giá |
| Tập endpoint/message, tỷ lệ đọc/ghi, payload và tỷ lệ cache hit | Workload khác nhau đòi concurrency khác nhau |
| RPS đến và RPS hoàn thành, target p95/p99/error SLO | Xác định thành công theo tác động người dùng |
| Active/max, queue depth/age/wait, task run time, reject/timeout | Xem executor đang thiếu capacity hay không |
| CPU, GC, heap, DB pool, downstream latency, retry | Phát hiện bottleneck chuyển sang tài nguyên khác |
| Thời gian warm-up, thời điểm bắt đầu/kết thúc test, thời điểm deploy | Tránh so dữ liệu warm/cold hoặc lệch giờ |

Nếu service hoạt động theo chu kỳ, baseline phải bao gồm cả tải trung bình lẫn **giờ cao điểm**, burst và khoảng hồi phục. Một đợt đo 10 giây ở tải thấp không đủ để chỉnh capacity lâu dài.

**Thứ tự lấy mẫu khuyến nghị:** chạy warm-up để JIT, cache và connection pool ổn định; chạy đoạn steady-state đủ dài để quan sát queue/GC; tăng tải theo nấc; ghi recovery sau burst. Chọn thời lượng theo latency, chu kỳ GC và hệ thống phụ thuộc, không có số phút cố định đúng cho mọi dịch vụ.

Ví dụ lưu baseline ở dạng bảng:

| Test ID | Arrival RPS | Completed RPS | HTTP p95/p99 | Active/max | Queue p95 / wait p95 | Rejected/s | CPU | DB pending |
|---|---:|---:|---|---|---|---:|---:|---:|
| B0, tải ổn định | 80 | 80 | 240/390 ms | 18/24 | 3 tasks / 15 ms | 0 | 61% | 0 |
| B1, tải đỉnh | 130 | 112 | 970/1700 ms | 24/24 | 90 tasks / 650 ms | 5 | 65% | 0 |

*Số liệu giả lập để minh họa cách đọc bảng, không phải kết quả đo của một hệ thống cụ thể.*

Đọc B1: active chạm max, queue và queue wait tăng, rejection xuất hiện trong khi CPU chỉ 65% và DB pending=0. Điều đó tạo giả thuyết rằng **executor có thể là nút nghẽn**, nhất là nếu task thường xuyên chờ I/O. Nhưng chưa đủ để kết luận chỉ tăng max threads: cần xác định nguồn chờ, connection pool/downstream latency và quan hệ giữa tốc độ vào/ra.

## 7. Công thức hỗ trợ suy nghĩ — không thay thế số đo

### 7.1. Little's Law: concurrency trung bình

Trong điều kiện ổn định và xác định nhất quán đối tượng đo:

`L = λ × T`

Trong đó:
- `L`: số request/task đang tồn tại trung bình trong hệ thống đo (bao gồm chạy và chờ nếu `T` đo cả hai).
- `λ`: tốc độ hoàn thành trung bình (đơn vị request/giây hoặc task/giây).
- `T`: thời gian trung bình một request/task ở trong hệ thống (giây).

Ví dụ một endpoint xử lý ổn định **80 requests/s**, thời gian ở trong hệ thống trung bình **0,25 giây**:

`L = 80 × 0,25 = 20 requests đang tồn tại trung bình.`

**Không đồng nghĩa cần đúng 20 worker threads.** Async/reactive có thể có nhiều request đang tồn tại nhưng không giữ riêng một worker; một request blocking có thể chiếm worker phần lớn thời gian; request có thể gọi nhiều task hoặc fan-out. Little's Law hữu ích để kiểm tra tính nhất quán của throughput/latency/concurrency, sau đó phải đối chiếu với mô hình xử lý thật.

### 7.2. Ước lượng cho tác vụ blocking

Một heuristic thường được nhắc đến:

`N ≈ N_CPU × U_target × (1 + W_wait / C_cpu)`

Trong đó:
- `N_CPU`: số CPU thực sự được cấp (xem cả container quota).
- `U_target`: mức sử dụng CPU mong muốn trong khoảng 0..1.
- `W_wait`: thời gian trung bình task **không dùng CPU** do chờ I/O hoặc đồng bộ.
- `C_cpu`: thời gian CPU thực sự mà task tiêu thụ.

Giả sử 4 CPU, mục tiêu tải CPU 70%, task tốn trung bình 25ms CPU và 225ms chờ bên ngoài:

`N ≈ 4 × 0,7 × (1 + 225 / 25) = 28 threads.`

Con số **28 chỉ là điểm bắt đầu tạo giả thuyết**, không phải cấu hình áp dụng ngay. Công thức giả định phân chia CPU/wait có ý nghĩa, các task tương đối độc lập và không bị downstream giới hạn. Cần thử nhiều giá trị gần đó dưới tải thật; với nhiều pha, lock contention, context switching hoặc biến thiên lớn, heuristic có thể sai đáng kể.

**Kiểm tra chéo:** nếu input 80 request/s, request 250ms, số request đang tồn tại trung bình khoảng 20. Một pool cỡ 28 có thể cung cấp headroom nhưng không có nghĩa lúc nào cũng 28 active. Nếu database chỉ cho 10 connection và các task giữ connection lâu, 28 workers có thể chỉ tạo thêm hàng đợi chờ DB.

### 7.3. Tốc độ tăng queue

Tại một đoạn tải quá mức, có thể hình dung:

`ΔQ/Δt ≈ arrival_rate − completion_rate`

Nếu có 120 task/s đi vào nhưng chỉ 90 task/s hoàn thành và queue có thể nhận thêm, sau 10 giây queue có thể tăng khoảng **300 task** (trừ phần thay đổi số task đang chạy và các tác vụ bị từ chối). Công thức này là gần đúng theo luồng dữ liệu; áp dụng cứng nhắc có thể sai khi số worker đang tăng hoặc khi arrival, retry và completion không được đếm cùng hệ quy chiếu.

**Hàng đợi lớn không làm tăng năng lực phục vụ**; nó đổi lỗi từ chối sớm thành thời gian chờ dài hơn, tiêu thụ bộ nhớ và làm tail latency tệ hơn. Cần đo cả queue wait, không tối ưu chỉ để “hết reject”.

## 8. Phân biệt ba loại nghẽn bằng dấu hiệu

### Trường hợp A — CPU-bound

Dấu hiệu: CPU gần quota, throttling cao, GC/allocations đáng kể; tăng pool làm context switching và p99 tăng, dù queue không còn cao. Các task nhiều tính toán, ít chờ I/O.

Hướng thử: giảm việc dư thừa, cache/precompute hợp lý, tối ưu thuật toán, profiling CPU/JFR, scale CPU/instance; tránh tăng workers vô hạn. Với workload CPU-bound, kích thước gần số core thường là một điểm thử hợp lý hơn hàng trăm threads.

### Trường hợp B — I/O-bound hoặc đang giữ lock

Dấu hiệu: active threads cao, CPU còn dư, thread dump cho thấy nhiều task chờ network/database/lock, queue wait tăng, throughput không tương xứng với active. Một số tác vụ chờ API chậm 2 giây làm chiếm worker suốt thời gian đó.

Hướng thử: giảm timeout/retry không kiểm soát, dùng async/non-blocking khi hợp lý, tách executor theo loại task, hạn chế concurrency hướng đến downstream, giảm thời gian giữ lock/transaction. Chỉ sau đó thử tăng pool nếu phụ thuộc phía sau có đủ khả năng xử lý.

### Trường hợp C — Pool hoặc queue có giới hạn quá thấp

Dấu hiệu: queue thường đầy, reject liên tục ở tải đúng mục tiêu, CPU và downstream còn dư, task service time tương đối ổn định; tăng max/giảm queue wait trong một thử nghiệm có kiểm soát giúp tăng throughput, giảm p95/p99 mà không khiến resource khác bão hòa.

Hướng thử: đo theo nấc `core-size/max-size/queue-capacity`; đặt queue hữu hạn và policy từ chối phù hợp, tạo backpressure khi cần. Quan sát fail-fast, timeout và khả năng hồi phục khi burst kết thúc.

| Quan sát kết hợp | Giả thuyết chính | Điều cần xác thực |
|---|---|---|
| Active ≈ max; queue tăng; CPU thấp | Blocking/I/O wait hoặc pool quá nhỏ | Thread dump, DB/API wait, throughput sau tăng max |
| Active ≈ max; CPU 95–100%; queue tăng | Giới hạn CPU | CPU profiling, throttling, per-task CPU |
| Active thấp; queue nhiều; max lớn; queue vô hạn | Queue hấp thụ task trước khi pool mở rộng | `core`/`max`/`queueCapacity` thực tế |
| Queue ít; HTTP p99 cao; DB pending cao | Chờ database connection | Hikari acquisition time và SQL p99 |
| Không có reject nhưng p99 tăng liên tục | Hàng đợi hoặc caller-runs che dấu quá tải | Queue wait, caller request thread blocking |
| Reactor event loop lag cao, CPU không nhất thiết cao | Blocking trên event loop | JFR, BlockHound trong kiểm thử phù hợp, trace handler |

Đừng suy luận nhân quả từ **một metric đơn lẻ**. Cùng biểu hiện active cao có thể là CPU-bound, I/O-bound, deadlock hoặc workload bình thường đang bận.

## 9. Quy trình thử thay đổi theo từng nấc

Một lần thử nghiệm có giá trị gồm các bước sau.

**Bước 1 — Định nghĩa mục tiêu và ràng buộc.** Ví dụ: tại 80 RPS, p95 dưới 300ms, p99 dưới 500ms, error rate dưới 1%, không có reject mất việc, CPU trong ngưỡng an toàn, DB pending thấp, chi phí không tăng vô lý. Đây là ngưỡng **minh họa**, phải thay bằng SLO thực tế của dịch vụ.

**Bước 2 — Cố định điều kiện.** Dùng cùng image, payload, số replica, số vCPU, JDK, cấu hình GC, DB, cache và load generator; tránh so thử nghiệm có nhiều thay đổi cùng lúc.

**Bước 3 — Chụp baseline.** Đo warm-up, steady load, burst và recovery. Ghi đặc biệt active/max, queue depth/wait, rejection, CPU, downstream. Kiểm tra **load generator** không phải nút nghẽn: RPS phát được so với RPS mong muốn và số iteration bị bỏ không quá lớn.

**Bước 4 — Chọn một giả thuyết và một tham số.** Ví dụ chỉ thay `maxPoolSize=16 → 24` khi queue hữu hạn, giữ core/queue/policy. Nếu cần thử queue capacity, làm thí nghiệm riêng để không nhầm tác động.

**Bước 5 — Chạy lặp lại trong cùng điều kiện.** Thu metric đầy đủ theo từng candidate; so p50/p95/p99, throughput, reject, mức tiêu thụ tài nguyên, hành vi khi overload và thời gian queue trở về bình thường.

**Bước 6 — Quyết định theo SLO và điểm gãy.** Chọn cấu hình nhỏ nhất đạt mục tiêu có headroom phù hợp. Nếu thay đổi làm p95 giảm nhưng p99, lỗi, CPU hoặc database trở nên xấu hơn, chưa thể coi là cải thiện.

**Bước 7 — Triển khai có khả năng hồi phục.** Triển khai từng phần/canary nếu phù hợp, ghi mốc config change, theo dõi đủ chu kỳ tải và rollback nếu các chỉ số trọng yếu vượt ngưỡng đã định. Thay đổi pool cần được xem như thay đổi về khả năng tiếp nhận tải và thời gian chờ, không chỉ chỉnh một con số.

### Ví dụ đọc kết quả A/B

Giả định một service dùng platform-thread executor với `core=8`, queue hữu hạn 100, cùng tải mục tiêu 80 requests/s:

| max threads | Completed RPS | p95 / p99 | Queue wait p95 | CPU | Rejected/s |
|---:|---:|---|---:|---:|---:|
| 16 | 78 | 480 / 900 ms | 160 ms | 57% | 0,3 |
| 24 | 80 | 280 / 450 ms | 8 ms | 63% | 0 |
| 32 | 80 | 295 / 520 ms | 4 ms | 79% | 0 |

*Số liệu giả định để luyện cách ra quyết định, không phải benchmark thật.*

Nếu SLO là ví dụ ở bước 1, **24** là ứng viên tốt nhất trong tập thử: đáp ứng p95/p99, throughput đầy đủ, reject=0, CPU còn headroom. Pool 32 không tăng throughput, giảm queue wait rất ít nhưng CPU và tail latency xấu hơn. Vẫn cần xác nhận ổn định theo các chu kỳ tải và độ tin cậy của từng phép đo.

## 10. Cấu hình đúng đối tượng, sau khi đã có bằng chứng

### 10.1. Spring MVC với Tomcat

Ví dụ **một candidate** để thử cho Servlet/Tomcat:

~~~yaml
server:
  tomcat:
    threads:
      min-spare: 16
      max: 120
~~~

`server.tomcat.threads.max` điều chỉnh Tomcat request workers trên cấu hình phù hợp; **không chỉnh trực tiếp** số threads của `@Async` executor hoặc Hikari connection pool. Cấu hình `server.tomcat.accept-count` liên quan đến backlog kết nối khi server không tiếp nhận kịp, không phải một hàng đợi Java task tùy ý có thể tăng để giải quyết ứng dụng chậm. Các tham số của Jetty và Netty khác Tomcat.

Kiểm tra `server.tomcat.max-connections`, tình trạng accept/backlog, request latency, số worker bận cùng phụ thuộc trước khi kết luận thread pool là điểm nghẽn.

### 10.2. Spring `@Async` / `ThreadPoolTaskExecutor`

Ví dụ candidate đã nêu:

~~~yaml
spring:
  task:
    execution:
      pool:
        core-size: 8
        max-size: 24
        queue-capacity: 100
~~~

Trong `ThreadPoolExecutor`, việc tăng `max-size` **chỉ có thể có tác dụng khi queue bị đầy** (với cơ chế thông thường). Tăng `queue-capacity` có thể khiến pool ít tăng hơn và tăng tail latency. Một pool có queue rất lớn có thể giữ tác vụ rất lâu, gây hết thời hạn HTTP hoặc hết bộ nhớ trước khi sinh lỗi từ chối.

Với custom bean, có thể cấu hình trực tiếp:

~~~java
// Fragment đặt trong một lớp @Configuration của ứng dụng Spring.
// Không phải một chương trình Java độc lập.
@Bean
ThreadPoolTaskExecutor reportExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setThreadNamePrefix("report-");
    executor.setCorePoolSize(8);
    executor.setMaxPoolSize(24);
    executor.setQueueCapacity(100);
    return executor;
}
~~~

Import tương ứng:
- `org.springframework.context.annotation.Bean`
- `org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor`

Nếu bean được inject qua `@Async("reportExecutor")`, metric và test phải phản ánh chính bean đó. Boot có thể tự instrument các bean `ThreadPoolTaskExecutor` phù hợp, nhưng queue wait/rejection theo nghiệp vụ vẫn cần được kiểm tra rõ.

### 10.3. Spring WebFlux / Reactor Netty

Các event loop phục vụ I/O phải tránh tác vụ blocking dài. Nếu phát hiện handler blocking trên event loop, ưu tiên:
- Đổi sang client/driver không chặn khi có lựa chọn phù hợp.
- Cách ly việc blocking vào `Schedulers.boundedElastic()` hoặc executor phù hợp, với giới hạn concurrency minh bạch.
- Đo scheduler queue wait, bounded resources và downstream; kiểm tra sự tắc nghẽn do backpressure.

Không suy ra “WebFlux nhanh hơn thì cần thêm Netty event-loop threads”. Cấu hình `spring.task.execution.pool.*` cũng không phải công tắc chung điều khiển mọi Reactor scheduler. Muốn thay đổi một resource, phải xác nhận chính resource đó tiêu thụ công việc đang bị chậm.

### 10.4. Java 21+ virtual threads

Khi bật `spring.threads.virtual.enabled=true` trong những phiên bản Spring Boot hỗ trợ, auto-configured task executor có thể chuyển sang `SimpleAsyncTaskExecutor` dùng virtual threads thay vì `ThreadPoolTaskExecutor`. Các thuộc tính `spring.task.execution.pool.*` **không còn ý nghĩa điều chỉnh một platform-thread pool** trong chế độ đó; `server.tomcat.threads.max` cũng có thể không có hiệu lực khi server đang dùng virtual threads.

Không đánh giá virtual threads bằng đúng một dashboard active platform threads. Thay vào đó cần đo concurrency, CPU, heap, pinned/carrier behavior theo JDK, JFR, semaphore, DB/API connection limits và thời gian chờ. Virtual threads không tăng số core CPU hoặc năng lực database; cho phép tạo nhiều tác vụ đồng thời mà không có giới hạn upstream/downstream có thể làm hệ thống phụ thuộc quá tải.

### 10.5. Rejection policy và phản áp lực

- `AbortPolicy` từ chối task khi đầy; giúp bộc lộ overload sớm nhưng ứng dụng phải biến lỗi thành hành vi nghiệp vụ rõ ràng.
- `CallerRunsPolicy` cho thread submit thực thi task. Nó có thể tạo backpressure, đồng thời **tăng latency của caller**; đo ảnh hưởng đến Tomcat worker hoặc consumer đang submit.
- `DiscardPolicy`/`DiscardOldestPolicy` làm mất task trong một số trường hợp, rất nguy hiểm nếu task đại diện cho thanh toán, đơn hàng hoặc công việc cần được lưu bền.

Không tăng queue vô hạn để “hết lỗi”. Với workload cần bền vững, cân nhắc hàng đợi message có persistence, retry có giới hạn, idempotency và admission control phù hợp hơn một Java queue trong bộ nhớ.

## 11. Một ca điều tra từ request chậm đến quyết định không tăng pool

Giả sử Spring MVC trả lời `GET /reports/{id}`. Ở peak, p99 HTTP 2,5 giây, Tomcat active 40/200, `reportExecutor` active 8/8, queue 200, CPU 38%, Hikari pending 0. Tác vụ report gọi dịch vụ xuất báo cáo mất 2 giây và timeout thường xuyên.

**Dữ liệu ban đầu gợi ý:** Tomcat chưa bão hòa; executor report đang đầy; queue lớn nhưng nút nghẽn có thể là API xuất báo cáo. Nếu tăng executor lên 40 threads, sẽ có thêm 32 request đồng thời tới API chậm, dễ làm dịch vụ đó quá tải và nhiều timeout hơn.

Điều tra hợp lý:

1. Trace một request: thời gian xếp hàng trong reportExecutor, thời gian dùng CPU của việc tạo report, thời gian chờ API xuất báo cáo.
2. So sánh tail latency với biểu đồ downstream, tần suất retry và quota của API.
3. Giảm timeout/retry không kiểm soát, cache phần báo cáo lặp, giảm đồng thời đến API, hoặc đưa tác vụ dài sang luồng xử lý bất đồng bộ có trạng thái truy vấn kết quả nếu phù hợp nghiệp vụ.
4. Test lại cùng tải: nếu API giữ latency ổn định, executor queue mới giảm và HTTP p99 cải thiện, không cần tăng pool.
5. Chỉ thử tăng executor khi downstream có năng lực dự phòng và queue wait vẫn là bottleneck quan sát được.

Ví dụ này minh họa vì sao câu hỏi **“luồng đang làm gì?”** quan trọng hơn câu hỏi **“cần bao nhiêu luồng?”**.

## 12. Công cụ điều tra bổ sung khi metric không đủ

**JFR / Java Mission Control:** thu CPU sampling, allocation, thread states, monitor/lock contention, các sự kiện về virtual threads nếu JDK hỗ trợ. JFR giúp phân biệt thời gian chạy CPU với thời gian blocked/waiting mà gauge active đơn lẻ không thể hiện.

**Thread dump:** xem tên thread/pool, stack trace, trạng thái `RUNNABLE`, `WAITING`, `TIMED_WAITING`, `BLOCKED`. Không xem một snapshot duy nhất là “chân lý”: cần nhiều ảnh chụp theo thời gian và gắn với thời điểm queue tăng. Trạng thái `RUNNABLE` có thể bao gồm chờ I/O native, không nhất thiết luôn tiêu thụ CPU.

**Distributed tracing:** thể hiện quan hệ HTTP → executor → database → API. Thêm span cho khoảng chờ queue và thời gian chạy task giúp tách được “chờ để được chạy” khỏi “chạy mà đang chờ hệ thống khác”.

**Profiling CPU/heap:** dùng khi CPU/GC tăng sau khi mở rộng pool. Đừng tăng pool dựa trên một con số thread-count trong dashboard nếu hệ thống đang bão hòa CPU.

**Load generator:** ghi cả intended arrival rate, achieved throughput và dropped iterations. Nếu máy phát tải không đủ CPU/connections, thí nghiệm có thể kết luận sai rằng ứng dụng đã đạt throughput tối đa.

## 13. Những lỗi thường gặp khi tuning

1. **Tăng `maxPoolSize` nhưng queue vô hạn:** pool thường dừng tăng ở core size và backlog tiếp tục lớn. Cần hiểu thuật toán queue-first của `ThreadPoolExecutor`.
2. **Chỉnh nhầm pool:** sửa Tomcat khi `@Async` mới là nguồn chờ, hoặc sửa `spring.task.execution.*` khi đang dùng custom executor.
3. **Chỉ đo CPU trung bình:** một core có thể nóng, container bị throttling, hoặc bottleneck nằm ở connection pool/lock; CPU tổng thấp không đủ kết luận.
4. **Chỉ đo p50:** độ trễ p99 và thời gian chờ khi burst có thể tệ hơn nhiều dù trung bình không đổi.
5. **Chỉ đo completed RPS:** load đã gửi nhiều hơn nhưng bị reject/timeout/dropped iterations có thể không xuất hiện trong completed counter.
6. **Tăng queue để tránh reject:** queue lớn làm task quá hạn, tốn bộ nhớ và che overload; cần quan sát tuổi task chờ.
7. **Nhầm queue wait với task run time:** thời gian task chạy thấp vẫn có thể khiến người dùng chờ lâu do task nằm trong queue.
8. **Không đo dependency:** 100 task đồng thời cùng truy cập một DB pool 10 connections dễ gây thêm contention và timeout.
9. **Không có warm-up/cùng điều kiện:** đổi bản build, JDK, số replica hoặc cache giữa các lần đo rồi gán mọi khác biệt cho pool size.
10. **Đổi nhiều tham số cùng lúc:** không biết thay đổi nào làm p99 tốt hay xấu.
11. **Không có overload/recovery test:** ở steady-state mọi giá trị đều trông ổn nhưng khi burst, queue không thoát hoặc memory tăng.
12. **Dùng platform-thread metric để tối ưu virtual threads:** một số property pool bị bỏ qua; điều quan trọng là tài nguyên phía sau và cấu hình concurrency.
13. **Không giới hạn/cardinality metric:** gắn request ID vào label gây bùng nổ time series và làm hệ thống đo lường quá tải.
14. **Không kiểm tra rejection policy:** `CallerRunsPolicy` làm submitter bị chậm, còn discard policy có thể mất tác vụ mà không ném lỗi dễ thấy.

## 14. Checklist trước/sau thay đổi

Trước:
- [ ] Đã xác định đúng pool và đường xử lý request/task.
- [ ] Đã ghi phiên bản JDK/Boot, server, vCPU/quota, số replica và cấu hình core/max/queue/policy.
- [ ] Đã có baseline RPS, p95/p99, queue wait/size, active/max, reject, CPU, GC, DB/downstream.
- [ ] Đã xác định bottleneck có bằng chứng: CPU, I/O, dependency, queue, hay thiếu worker.
- [ ] Đã đặt SLO, ngưỡng error, latency, tài nguyên và kịch bản burst/recovery.
- [ ] Đã chọn một thay đổi có thể đo riêng và có đường rollback.

Sau:
- [ ] Cùng workload, cùng tài nguyên và cùng thời gian đo.
- [ ] Throughput, p95/p99, queue wait/reject và CPU/downstream đều được so sánh.
- [ ] Không có dấu hiệu chuyển bottleneck sang DB, API ngoài, GC, event-loop hoặc caller.
- [ ] Có quyết định chấp nhận/từ chối thay đổi dựa trên SLO và kết quả lặp lại.
- [ ] Có quan sát thực tế sau rollout đủ lâu để gặp tải cao điểm.

## 15. Câu hỏi ôn tập

**Câu 1.** Pool core=8, max=64, queue không giới hạn. Khi lượng task tăng, pool có nhất thiết tăng đến 64 không?

**Đáp án:** Không. Với quy tắc mặc định của `ThreadPoolExecutor`, queue không giới hạn tiếp nhận task sau khi đạt core size; `maxPoolSize` thường không được dùng để mở rộng.

**Câu 2.** CPU chỉ 30% và queue dài có đủ chứng minh nên tăng executor không?

**Đáp án:** Chưa. Có thể task đang chờ DB, API, lock hoặc executor thiếu threads. Phải đo queue wait, task service/wait, tài nguyên bên dưới và thử có kiểm soát.

**Câu 3.** Khi 100 req/s, thời gian trung bình trong hệ thống 200ms, Little's Law ước lượng bao nhiêu request đang tồn tại?

**Đáp án:** 100 × 0,2 = **20 request** trung bình trong hệ thống ở trạng thái ổn định. Đây không tự động là 20 Java threads.

**Câu 4.** Vì sao tăng `server.tomcat.threads.max` có thể không giảm thời gian chờ của một công việc chạy qua `@Async("billingExecutor")`?

**Đáp án:** Hai giới hạn độc lập. Phải đo `billingExecutor` và các downstream mà công việc đó sử dụng.

**Câu 5.** Nếu tăng max threads giúp p50 giảm nhưng p99 tăng và CPU tăng mạnh, có nên áp dụng ngay không?

**Đáp án:** Không. Cần so theo SLO và trade-off, kiểm tra saturation/GC/context switching/DB, chạy lại cùng điều kiện và có thể chọn cấu hình ít threads hơn.

**Câu 6.** Khi bật virtual threads, có nên chỉnh `spring.task.execution.pool.max-size` giống platform pool?

**Đáp án:** Không giả định có tác dụng. Phải kiểm tra executor thực tế; nhiều thuộc tính pool bị bỏ qua khi Boot dùng `SimpleAsyncTaskExecutor` với virtual threads.

## 16. Tài liệu tham khảo

- [Spring Boot — Metrics / Actuator / HTTP / Task Execution / Tomcat](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot — Task Execution and Scheduling, virtual threads và task executor properties](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html)
- [Spring Boot 4.0 — Common Application Properties](https://docs.spring.io/spring-boot/4.0/appendix/application-properties/index.html)
- [Spring Framework — Task Execution and Scheduling; ThreadPoolTaskExecutor, queue và rejection policy](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Java SE — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Spring Boot — Actuator metrics endpoint](https://docs.spring.io/spring-boot/api/rest/actuator/metrics.html)

**Ghi nhớ khi áp dụng:** đo cả thời gian của người dùng, thời gian trong queue và khả năng của tài nguyên phía sau. Thay đổi kích thước executor chỉ là một giả thuyết cần được kiểm chứng bằng dữ liệu.
