# Quan sát thread pool, connection pool và hàng chờ

Một REST API có thể vẫn trả `200 OK` cho đa số request nhưng độ trễ tăng dần, sau đó bất ngờ xuất hiện `503 Service Unavailable` và timeout. CPU chưa chắc cao, database chưa chắc ngừng hoạt động. Nguyên nhân có thể là **thread xử lý request bị chiếm hết**, **connection pool đang chờ mượn kết nối**, hoặc **hàng chờ công việc tăng nhanh hơn tốc độ xử lý**. Nếu chỉ quan sát mỗi lượng request và mã lỗi HTTP, rất khó biết hệ thống nghẽn ở đâu.

Trong mô-đun **INTEGRATION_API_REST**, các resource, URI, phương thức và mã trạng thái HTTP tạo thành hợp đồng của API. Chương **Quan sát hệ thống** mở rộng hợp đồng ấy sang hành vi khi chịu tải: muốn API có latency, phân trang, cache, idempotency, phân quyền và xử lý lỗi đáng tin cậy, người vận hành phải quan sát được **mức sử dụng tài nguyên, thời gian chờ, tình trạng bão hòa và cách hệ thống từ chối tải quá khả năng**. Bài này tập trung vào Java/Spring Boot, Micrometer, Actuator, Prometheus và các tác vụ REST có đồng bộ hoặc bất đồng bộ.

## 1. Mục tiêu và tình huống thực tế

Sau bài này, người học có thể:

1. Phân biệt **thread pool**, **connection pool**, **queue trong bộ nhớ** và **hàng chờ bền vững** như database/broker.
2. Đọc và diễn giải đúng các chỉ số *active*, *idle*, *pending*, *queue depth*, *oldest age*, *wait duration*, *rejection*, *throughput* và *latency*.
3. Cấu hình quan sát executor, HikariCP và HTTP server ở Spring Boot; viết các truy vấn PromQL cơ bản và liên kết metric với log/trace.
4. Nhận biết bão hòa, thread starvation, connection leak, head-of-line blocking và backlog tăng liên tục; tránh kết luận sai từ một gauge đơn lẻ.
5. Thiết kế bounded queue, timeout, backpressure, HTTP `429`/`503`/`202`, retry có giới hạn và cảnh báo gắn với SLO.
6. Kiểm thử bão hòa một cách có kiểm soát, xây runbook và bảo vệ dữ liệu trong hệ thống quan sát.

Giả sử `POST /api/v1/orders` cần kiểm tra tồn kho, ghi đơn hàng và gửi công việc thông báo. Kiến trúc điển hình:

~~~mermaid
flowchart LR
    C["Client / Gateway"] -->|"HTTP request"| T["Request thread pool"]
    T -->|"SQL"| P["HikariCP connection pool"]
    P --> D[("Database")]
    T -->|"Ghi job/outbox"| Q[("Hàng chờ bền vững")]
    Q --> W["Worker / Executor"]
    W --> S["Email / API đối tác"]
    M["Metrics + Logs + Traces"] -.-> T
    M -.-> P
    M -.-> Q
    M -.-> W
~~~

Khi API chậm, câu hỏi đầu tiên không phải “tăng `maxThreads` lên bao nhiêu?” mà là **request đang mất thời gian ở đoạn nào**. Tăng thread hoặc số connection sai chỗ có thể khiến database nghẽn nặng hơn.

## 2. Bốn loại tài nguyên và ý nghĩa của “đang chờ”

| Thành phần | Đơn vị tài nguyên | Điều gì được xếp hàng/chờ? | Số liệu quan trọng |
| --- | --- | --- | --- |
| HTTP server (Tomcat/Jetty/Undertow) | Worker thread và năng lực xử lý kết nối | Request/kết nối chờ được phục vụ tùy server/connector | Busy/current/max threads, active requests, request latency, 5xx, thời gian chờ nếu instrument được |
| Application executor (`ThreadPoolTaskExecutor`) | Thread chạy task và queue | Task đã nhận nhưng chưa bắt đầu chạy | Active, pool size, max size, queued, queue remaining, rejected, task wait/run time |
| Database pool (`HikariCP`) | Connection DB có giới hạn | Thread chờ mượn connection trước khi query | Active, idle, total/max, pending, acquire time, timeout count, connection usage |
| Hàng chờ bền vững (DB job, RabbitMQ, Kafka...) | Job/message/partition/consumer | Công việc chưa xử lý hoặc đang xử lý nhưng chưa ack | Ready/backlog, in-flight, oldest age, enqueue/dequeue rate, consumer lag, retry, DLQ |

**Không đồng nhất các queue:** hàng chờ của executor trong JVM có thể biến mất khi process bị kill; hàng chờ bền vững có thể tồn tại qua restart. Pending connection của Hikari là **người đang đợi mượn connection**, không phải số SQL query bị khóa trong database. Kafka consumer lag là chênh lệch offset theo nhóm consumer/partition, không phải lúc nào cũng tương đương số tác vụ nghiệp vụ đang chờ.

### 2.1. Thread pool của HTTP server

Với ứng dụng **Spring MVC** dùng servlet container, request thường chiếm một worker thread khi xử lý đồng bộ. Nếu service gọi một API bên ngoài và chờ phản hồi, thread có thể bị giữ dù CPU thấp. Khi số thread bận tiệm cận giới hạn, request mới có thể phải chờ tại connector/OS/proxy hoặc bị từ chối/timeout; chi tiết phụ thuộc container, connector và cấu hình hàng chờ.

Một ứng dụng **Spring WebFlux** dùng event loop có mô hình khác: chặn event loop bằng JDBC blocking, `Thread.sleep` hay gọi HTTP blocking có thể làm nghẽn rất nhiều request dù số thread ít. Với WebFlux, phải quan sát event-loop blocking, scheduler, pending tasks, HTTP client connection pool và độ trễ event loop; không bê nguyên công thức “tăng Tomcat worker threads” sang Netty.

### 2.2. Executor dành cho tác vụ nền

`ThreadPoolTaskExecutor` thường dùng cho `@Async`, công việc I/O độc lập hoặc xử lý bên ngoài luồng request. Các trạng thái cần phân biệt:

- **Active threads:** số thread đang thực thi task tại thời điểm đo, không phải tổng thread được tạo.
- **Pool size:** số worker thread hiện tồn tại; có thể nhỏ hơn max.
- **Queue size/depth:** số task đã được chấp nhận nhưng chưa bắt đầu; không bao gồm task đang chạy.
- **Remaining capacity:** số vị trí còn lại trong queue giới hạn; nếu queue không giới hạn, giá trị này ít hữu ích cho quyết định overload.
- **Rejected tasks:** task không được nhận khi executor đã đóng hoặc đã bão hòa; cần có chỉ số counter riêng và cơ chế xử lý thất bại.
- **Task wait time:** thời gian từ lúc enqueue tới khi bắt đầu; thường là triệu chứng backlog tốt hơn `queue size` đơn thuần.

Trong `ThreadPoolExecutor` truyền thống, khi core threads đã bận, queue thường được lấp trước khi pool tăng lên `maxPoolSize`. Vì vậy `active≈corePoolSize` và queue đang tăng **không tự động có nghĩa** cấu hình `maxPoolSize` đã được dùng hết. Nếu `queueCapacity` quá lớn, executor có thể hầu như không tăng thread vượt core mà đổi lại latency chờ lâu.

### 2.3. Connection pool không phải thread pool

HikariCP cho nhiều request mượn một tập connection JDBC. Một thread có thể đang bận chờ connection; việc tăng thread HTTP sẽ chỉ tạo thêm **người đợi**, không tạo thêm khả năng truy vấn database.

Ví dụ: pool tối đa 20 connection, cả 20 đang được mượn và 12 request khác đang chờ. `active=20`, `idle=0`, `pending=12` là dấu hiệu tranh chấp pool; nhưng nguyên nhân gốc có thể là SQL chậm, transaction giữ lock quá lâu, rò connection, query chạy quá lâu hoặc pool được đặt quá nhỏ so với throughput. Cần kết hợp với DB slow query, transaction duration và lock/wait metrics để phân biệt.

## 3. Từ số liệu đến câu hỏi vận hành

Nên phân tích pool/queue bằng ba nhóm tín hiệu:

| Nhóm | Ví dụ | Câu hỏi trả lời |
| --- | --- | --- |
| **Nhu cầu (demand)** | Request rate, enqueue rate, inflight request, task submitted | Bao nhiêu công việc đến? Có burst/tăng đột biến? |
| **Khả năng phục vụ (service)** | Completed tasks/s, dequeue/ack rate, query duration, worker throughput | Hệ thống giải quyết được bao nhiêu công việc? |
| **Tắc nghẽn (saturation)** | Active/max, pending acquires, queue size/age, rejected, timeout | Đang ở ngưỡng nào, người gọi phải chờ bao lâu, có ai bị từ chối? |

Khi request rate tăng, queue depth tăng chưa đủ để kết luận hệ thống quá tải bền vững: có thể đó chỉ là burst ngắn rồi được xử lý hết. Dấu hiệu đáng lo hơn là **tốc độ nhận liên tục lớn hơn tốc độ hoàn tất**, tuổi job già đi và latency của người dùng tăng.

### 3.1. Little's Law và các giới hạn

Với hệ thống ở trạng thái ổn định:

\[
L = \lambda W
\]

Trong đó `L` là số công việc trung bình đang ở trong hệ thống, `λ` là throughput trung bình (công việc/giây), `W` là thời gian trung bình của một công việc từ vào đến ra. Ví dụ nếu throughput là 100 request/giây và thời gian trung bình 0,2 giây, số request đồng thời trung bình xấp xỉ 20.

Đây **không phải công thức chọn số thread tối ưu**: nó giả định hệ ổn định trong khoảng quan sát và dùng trung bình, không mô tả trực tiếp p99 latency, burst, priority queue, blocking DB hoặc retry storm. Nếu throughput không theo kịp arrival rate, backlog tăng thì hệ không còn ổn định; suy luận bằng trung bình dài hạn có thể gây hiểu lầm.

### 3.2. Hàng chờ phải đo cả độ sâu và độ tuổi

Ví dụ một queue có 10.000 job: nếu consumer xử lý 100.000 job/giây thì queue có thể tiêu hết rất nhanh. Ngược lại, queue chỉ còn 5 job nhưng job cũ nhất chờ hàng giờ là dấu hiệu **kẹt phân vùng, lỗi retry lặp hoặc worker không xử lý đúng loại công việc**. Do đó nên ghi nhận:

- `queue_depth` hoặc lag tại thời điểm đo;
- `oldest_job_age_seconds`, `enqueue_to_start_seconds` và `end_to_end_processing_seconds`;
- tốc độ enqueue, start, complete, retry, fail, dead-letter;
- số consumer/worker đang hoạt động và các phân vùng không có tiến triển;
- kích thước và số lần retry phân theo **loại job hữu hạn**, không theo mỗi job ID.

Độ tuổi có thể tính bằng thời gian xử lý thực tế hoặc timestamp enqueue trong payload/database; cần đồng bộ clock, xác định timezone và cách xử lý job đang retry. Nếu `oldest_job_age` không có khi queue rỗng, hệ giám sát phải phân biệt **“không có sample”** với “giá trị 0” thay vì tự suy ra worker đã khỏe.

## 4. Instrumentation Spring Boot: điểm bắt đầu

Với Spring Boot 3, thường dùng **Spring Boot Actuator + Micrometer** và registry xuất Prometheus. Thêm dependency phù hợp phiên bản dự án:

~~~text
org.springframework.boot:spring-boot-starter-actuator
io.micrometer:micrometer-registry-prometheus
~~~

Ví dụ cấu hình:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
  metrics:
    tags:
      application: orders-api
    distribution:
      percentiles-histogram:
        http.server.requests: true

spring:
  datasource:
    hikari:
      maximum-pool-size: 20
      connection-timeout: 2000
~~~

Đây là **cấu hình minh họa**, không phải giá trị sizing cho mọi ứng dụng. `connection-timeout` của Hikari là thời gian đợi để **mượn connection**; nó không phải timeout thực thi SQL hay deadline tổng của request. Khi bật HTTP histogram, Prometheus có thể truy vấn phân bố latency; việc bật histogram có chi phí cardinality/storage nên chỉ bật cho những metric và nhãn có giá trị.

Endpoint `/actuator/prometheus` cần được **giới hạn bằng network policy, xác thực và quyền truy cập phù hợp**, không tùy tiện công khai trên Internet. Tương tự, chỉ expose management endpoint thực sự cần cho monitoring; `env`, `heapdump`, `configprops` và các endpoint có dữ liệu nhạy cảm phải được khóa chặt. Nếu triển khai management port riêng, cần bảo vệ port đó ở cả reverse proxy và mạng.

### 4.1. Xác minh meter thực tế thay vì dựa vào tên thuộc trí nhớ

Tên metric và tập metric được xuất có thể khác theo:

- phiên bản Spring Boot/Micrometer/container;
- servlet container là Tomcat/Jetty/Undertow hay WebFlux/Netty;
- có bật binders, HikariCP, registry và actuator hay không;
- meter được đăng ký sau khi bean tạo xong, và Prometheus chỉ hiện series khi đã có sample.

Khi vận hành, đối chiếu `/actuator/metrics` trong môi trường được bảo vệ với `/actuator/prometheus` hoặc registry đang dùng. Tên dấu chấm của Micrometer khi sang Prometheus thường được chuyển thành dấu gạch dưới; timer và counter có thêm hậu tố như `_seconds_count`, `_seconds_sum`, `_total` theo convention exporter.

Ví dụ một số nhóm thường gặp:

| Nguồn | Metric/Meter thường gặp | Ý nghĩa |
| --- | --- | --- |
| Spring MVC | `http.server.requests` | Số request, latency, status và URI template |
| JVM | `jvm.threads.live`, `jvm.threads.states`, `jvm.threads.peak` | Số lượng và trạng thái thread JVM, **không trực tiếp** là saturation một pool |
| HikariCP | `hikaricp.connections.active`, `idle`, `pending`, `max` | Trạng thái mượn/trả connection và người đợi |
| HikariCP | `hikaricp.connections.acquire`, `usage`, `timeout` | Thời gian mượn/giữ connection, lỗi hết thời gian đợi tùy phiên bản |
| Tomcat (khi binder/registry phù hợp) | `tomcat.threads.busy`, `tomcat.threads.current` | Thread servlet container đang bận và hiện có |
| Executor (khi được instrument) | `executor.active`, `executor.queued`, `executor.pool.size` | Các giá trị của pool/queue có tên và tag theo binder |
| HTTP client/broker | Metric theo thư viện client và binder | Connection leased/pending, latency, lag, retry, error |

**Đừng cố gắng tạo dashboard dựa trên metric không tồn tại.** Kiểm tra sự hiện diện của series, đơn vị đo (giây/millisecond), nhãn, giá trị và cách cập nhật trước khi viết rule cảnh báo.

## 5. Quan sát ThreadPoolTaskExecutor trong Spring

Giả sử tác vụ thông báo đơn hàng được xử lý bởi một pool riêng. Cấu hình giới hạn số thread và queue:

~~~java
@Configuration
@EnableAsync
public class OrderExecutorConfig {
    @Bean("orderIoExecutor")
    public ThreadPoolTaskExecutor orderIoExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(64);
        executor.setThreadNamePrefix("order-io-");
        executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        return executor;
    }
}
~~~

Các import chính thuộc `org.springframework.scheduling.*`, `org.springframework.context.annotation.*`, `java.util.concurrent.ThreadPoolExecutor`. Spring quản lý lifecycle của bean và khởi tạo executor; code không nên tự gọi `initialize()` lần nữa nếu framework đã thực hiện. Các con số chỉ dành cho ví dụ và phải được load test theo tài nguyên thực tế.

Khi `corePoolSize=8` và `queueCapacity=64`, đến khi các core thread bận, task mới thường vào queue trước. Executor có thể bắt đầu thêm thread vượt core khi queue đầy, tối đa 16; sau đó request submit có thể bị từ chối. `AbortPolicy` tạo tín hiệu rõ ràng thay vì âm thầm bỏ task. Nếu dùng `CallerRunsPolicy`, task có thể chạy trên thread gửi việc — với request HTTP, điều này làm kéo dài latency; với event-loop thread còn nguy hiểm hơn. Hãy đánh giá rõ chính sách overload trước khi chọn.

### 5.1. Gắn gauge cho pool cụ thể

Nếu Spring Boot/Micrometer đã tự bind executor này và cho đủ số liệu, ưu tiên dùng các meter có sẵn. Khi cần tên metric ổn định cho ứng dụng, có thể thêm `MeterBinder` quan sát trực tiếp `ThreadPoolExecutor`:

~~~java
@Configuration
class OrderExecutorMetrics {
    @Bean
    MeterBinder orderExecutorMeters(
            @Qualifier("orderIoExecutor") ThreadPoolTaskExecutor executor) {
        return registry -> {
            ThreadPoolExecutor pool = executor.getThreadPoolExecutor();
            Tags tags = Tags.of("pool", "order-io");

            Gauge.builder("app.executor.active", pool,
                    ThreadPoolExecutor::getActiveCount)
                .tags(tags).register(registry);
            Gauge.builder("app.executor.pool.size", pool,
                    ThreadPoolExecutor::getPoolSize)
                .tags(tags).register(registry);
            Gauge.builder("app.executor.queue.depth", pool,
                    p -> p.getQueue().size())
                .tags(tags).register(registry);
            Gauge.builder("app.executor.queue.remaining", pool,
                    p -> p.getQueue().remainingCapacity())
                .tags(tags).register(registry);
        };
    }
}
~~~

Các kiểu `MeterBinder`, `Gauge`, `Tags` thuộc Micrometer. Đảm bảo bean executor đã khởi tạo trước khi gọi `getThreadPoolExecutor()`. Tên và tag `pool="order-io"` là **giá trị hữu hạn**, phù hợp làm metric label; không dùng request ID, customer ID hoặc job ID làm label. Khi exporter Prometheus được cấu hình, các tên tùy chỉnh này thường xuất hiện dưới dạng `app_executor_active`, `app_executor_pool_size`, `app_executor_queue_depth` và `app_executor_queue_remaining`.

Gauge chỉ là ảnh chụp tại thời điểm scrape; một queue đầy trong vài chục millisecond có thể không xuất hiện nếu scrape mỗi vài giây. Vì vậy cần bổ sung **counter rejected**, **timer thời gian chờ task** và **timer thời gian chạy**, nhất là khi burst ngắn gây lỗi dù `queue_depth` có lúc trông bằng 0.

### 5.2. Đo queue wait time và task execution time

Có thể tạo wrapper quanh tác vụ ở **điểm submit** để đo từ enqueue đến start và từ start đến completion:

~~~java
@Component
public class ObservedTaskSubmitter {
    private final ThreadPoolTaskExecutor executor;
    private final MeterRegistry metrics;

    public ObservedTaskSubmitter(
            @Qualifier("orderIoExecutor") ThreadPoolTaskExecutor executor,
            MeterRegistry metrics) {
        this.executor = executor;
        this.metrics = metrics;
    }

    public void submit(Runnable task) {
        long submittedAt = System.nanoTime();
        try {
            executor.execute(() -> {
                metrics.timer("app.executor.task.wait",
                        "pool", "order-io").record(
                    System.nanoTime() - submittedAt,
                    TimeUnit.NANOSECONDS);
                Timer.Sample runTime = Timer.start(metrics);
                try {
                    task.run();
                } finally {
                    runTime.stop(metrics.timer(
                        "app.executor.task.run", "pool", "order-io"));
                }
            });
        } catch (TaskRejectedException rejected) {
            metrics.counter("app.executor.rejected",
                    "pool", "order-io").increment();
            throw rejected;
        }
    }
}
~~~

Ví dụ đo được các task **đi qua `ObservedTaskSubmitter`**; nếu code khác gọi executor trực tiếp thì không được đo, cần chuẩn hóa điểm submit hoặc dùng decorator/instrumentation phù hợp. `System.nanoTime()` dành cho **elapsed time**, không dùng làm timestamp giữa các máy. `Timer.Sample` vẫn ghi thời gian chạy khi task ném exception; có thể bổ sung counter thất bại được phân loại bởi loại job hữu hạn.

Với `@Async` và `void` method, exception không nhất thiết được trả về caller; cần xác định `AsyncUncaughtExceptionHandler`, retry/dead-letter và nơi ghi kết quả. Nếu task đã được nhận nhưng process chết, executor queue trong JVM không có bảo đảm bền vững. Đối với nghiệp vụ bắt buộc phải hoàn tất, cần persisted job hoặc transactional outbox, không chỉ dùng `@Async`.

## 6. Quan sát HikariCP và connection pool của HTTP client

### 6.1. HikariCP: active, idle, pending phải đọc cùng nhau

Các số liệu HikariCP thường có:

- **active**: connection đang được mượn; không đồng nghĩa tất cả đang thực thi SQL.
- **idle**: connection sẵn sàng cho mượn.
- **total/max**: tổng connection hiện tại và giới hạn được cấu hình; pool có thể đang mở thêm connection nên total chưa đạt max.
- **pending**: số thread đang đợi connection; tăng liên tục là dấu hiệu pressure.
- **acquire time**: thời gian chờ lấy connection; tăng trước khi request timeout là tín hiệu sớm.
- **usage time**: thời gian connection được giữ từ mượn tới trả, không nhất thiết là đúng SQL execution duration.
- **timeout count**: lần mượn không thành công trong connection timeout, không phải query timeout.

Ví dụ phân tích:

| Quan sát | Khả năng cần điều tra | Bước kiểm tra tiếp theo |
| --- | --- | --- |
| `active≈max`, `pending>0`, `idle=0` | Pool bão hòa | SQL/transaction chậm, lock DB, connection leak, pool sizing |
| `active≈max` nhưng throughput thấp | Connection bị giữ lâu | Long transaction, query plan, network DB, external call trong `@Transactional` |
| `active` thấp mà API chậm | DB pool có thể không phải bottleneck | Thread pool HTTP, HTTP client, CPU/GC, lock ứng dụng |
| `pending` tăng, `hikaricp...timeout` tăng | Request không lấy được connection đúng hạn | Theo dõi exception, 5xx và thời gian chờ acquire |
| `total` tăng giảm liên tục | Connection churn | Max lifetime, idle timeout, DB/network reset, cấu hình Hikari |

Đừng chỉ tăng `maximumPoolSize` khi thấy pending. Nếu mỗi instance có 30 connection và hệ thống scale lên 10 instance, tổng kết nối tiềm năng là 300, chưa kể các dịch vụ khác và connection dự phòng cho vận hành. DB có giới hạn `max_connections`, RAM cho backend process và khả năng CPU/I/O; quá nhiều kết nối đồng thời đôi khi **giảm** throughput.

### 6.2. Kết hợp database telemetry

HikariCP cho biết **khách hàng đang đợi connection**; để tìm nguyên nhân cần nhìn thêm ở database:

1. Query duration theo câu truy vấn đã chuẩn hóa, execution plan và tần suất gọi.
2. Số transaction mở lâu, session ở trạng thái idle-in-transaction và lock wait.
3. Connection/session count theo ứng dụng, CPU/IO, DB disk latency và replication lag nếu liên quan.
4. Trạng thái DB failover, network timeout, DNS hoặc retry có thể tạo burst reconnect.
5. Phân tách thời gian **đợi connection**, **chạy SQL**, **map dữ liệu** và **trả response** bằng trace/span hoặc instrumentation.

`leakDetectionThreshold` của HikariCP có thể giúp điều tra connection bị giữ lâu, nhưng cần cấu hình thận trọng và dùng tạm thời để tránh log ồn; cảnh báo này có thể là query hợp lệ chậm chứ chưa chứng minh leak. Không ghi stack trace có dữ liệu nhạy cảm ra hệ thống log công khai.

### 6.3. HTTP client connection pool

REST API còn dùng connection pool khi gọi service khác. Với Apache HttpClient, Reactor Netty hoặc HTTP client có pooling, hãy quan sát:

- leased/active connections, available/idle, pending acquire;
- connection acquisition latency và timeout;
- connect/read/response timeout, TLS handshake failure;
- request latency, retry count, circuit breaker state và upstream 429/5xx.

Tên metric phụ thuộc thư viện và cấu hình. Một HTTP client pool đầy có thể làm request thread chờ và khiến HikariCP **trông hoàn toàn bình thường**. Không gộp metric connection pool HTTP và HikariCP vào một gauge tên `active_connections` không có tag loại pool.

## 7. Hàng chờ: in-memory, database job và message broker

### 7.1. Hàng chờ executor trong JVM

Ví dụ `queueCapacity=64` là giới hạn số task chờ trong executor. Nếu process khởi động lại, các task chưa được persist có thể mất. Nếu request `POST /api/v1/orders` trả `202 Accepted` chỉ vì đã gọi `executor.execute(...)`, hệ thống có thể tuyên bố đã nhận công việc dù task biến mất khi restart.

Với job quan trọng, nên tạo resource job hoặc outbox **trong database transaction**, commit rồi mới trả `202`. Worker lấy từ hàng chờ bền vững và cập nhật trạng thái. Client có thể gọi `GET /api/v1/jobs/{id}` để xem `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`; worker phải idempotent vì message có thể được chuyển nhiều lần.

### 7.2. Database-backed job queue

Các trạng thái nên được đo riêng:

| Trạng thái | Ý nghĩa | Điều cần quan sát |
| --- | --- | --- |
| `READY/QUEUED` | Job có thể được nhận | Queue depth và tuổi job cũ nhất |
| `CLAIMED/RUNNING` | Worker đã thuê/claim và đang xử lý | In-flight count, processing duration, lease expiration |
| `RETRY_SCHEDULED` | Sẽ thử lại sau thời điểm đặt lịch | Retry rate, số lần retry, thời gian chờ |
| `SUCCEEDED` | Hoàn tất, có thể lưu lịch sử | Completion rate, p95/p99 end-to-end latency |
| `DEAD/FAILED` | Hết số lần thử hoặc cần xử lý thủ công | Dead-letter count, alert và runbook |

Ví dụ schema tối giản:

~~~sql
CREATE TABLE background_job (
    id UUID PRIMARY KEY,
    type VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    available_at TIMESTAMP WITH TIME ZONE NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE,
    finished_at TIMESTAMP WITH TIME ZONE,
    attempts INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_background_job_pick
    ON background_job (status, available_at);
~~~

Đây mới là cấu trúc minh họa; cơ chế claim/lease, lock, retry và hoàn trả job khi worker chết phải được thiết kế thêm. Khi đo queue age, chỉ tính job thực sự cần xử lý tại thời điểm đó (ví dụ `READY` và `available_at <= now()`), đồng thời đo riêng retry-scheduled. Nếu gộp job đã hẹn sau một tuần vào oldest-ready age, dashboard sẽ báo sai.

Ví dụ query đếm job sẵn sàng trong PostgreSQL:

~~~sql
SELECT count(*) AS ready_jobs
FROM background_job
WHERE status = 'READY'
  AND available_at <= now();
~~~

Chạy query metric này với tần suất hợp lý và index thích hợp; không truy vấn full table count/scan cực nặng mỗi vài giây trên database production lớn. Có thể cập nhật counter khi enqueue/dequeue và lấy snapshot định kỳ được kiểm soát.

### 7.3. RabbitMQ và Kafka không cùng một kiểu backlog

- **RabbitMQ:** phân biệt message `ready`, `unacked`, consumer count, publish/deliver/ack rate, redelivery và dead-letter. Ready cao có thể do không đủ consumer; unacked cao có thể là worker đang xử lý chậm hoặc prefetch quá lớn.
- **Kafka:** theo dõi consumer lag theo group/topic/partition, records consumed rate, rebalance, poll duration, partition không tiến triển và thời gian xử lý sau fetch. Lag offset tăng có thể do producer nhanh hơn consumer hoặc consumer bị kẹt; một số record tương đương khối lượng xử lý khác nhau nên lag count không đo chính xác tuổi dữ liệu.
- **Outbox:** nhìn cả số event `NEW`, tuổi event cũ nhất chưa publish, publish attempts, retry và số lần xử lý trùng ở consumer. Database commit thành công nhưng publisher không chạy vẫn có thể khiến API “tạo đơn thành công” nhưng downstream chưa nhận được gì.

Không chỉ dùng hàng chờ để hấp thu tải vô hạn. Queue lớn có thể che overload trong thời gian ngắn nhưng làm **thời gian hoàn tất nghiệp vụ** kéo dài. Với API hứa “xử lý trong 30 giây”, một job xếp hàng 5 phút đã vi phạm hợp đồng dù không có HTTP `500`.

## 8. Liên hệ pool/queue với API latency, status và trace

Khi điều tra sự cố, cần một câu chuyện nhân quả nhất quán:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant H as HTTP thread
    participant P as Hikari pool
    participant D as Database
    participant Q as Job queue
    C->>H: POST /api/v1/orders
    H->>P: acquire connection
    Note over H,P: Connection acquisition wait
    P->>D: SQL transaction
    D-->>P: Commit
    P-->>H: Connection returned
    H->>Q: Persist job / outbox
    H-->>C: 201/202 theo contract
    Note over Q: Queue age có thể tăng sau HTTP response
~~~

Ở HTTP layer, nên có:

- **Rate:** request/giây theo `method`, `uri template`, `status class`; không dùng raw URI chứa ID làm label.
- **Errors:** 4xx/5xx tách theo nguyên nhân, đặc biệt `429` giới hạn quota và `503` overload/dependency unavailable.
- **Duration:** p50/p95/p99 HTTP latency và distribution, xét số lượng request đủ ý nghĩa.
- **Saturation:** HTTP active/busy threads, executor queue/rejections, DB pending/acquire wait, message backlog/oldest age.

Trace hữu ích để nối các span như `http.server` → `order.service` → `jdbc` hoặc `http.client shipping`. Instrumentation không tự tạo span cho **thời gian đợi queue trước khi task bắt đầu**; cần metric/timer enqueue-to-start hoặc span phù hợp ở điểm submit/consumer. Khi truyền context sang `@Async` hoặc broker, phải truyền trace context theo cơ chế được hỗ trợ và không coi cùng một trace ID là bảo đảm transaction được giữ xuyên thread.

Log có cấu trúc nên ghi `traceId`, `spanId`, `requestId`, tên nghiệp vụ hữu hạn, thời gian và error code. Không ghi access token, session cookie, mật khẩu, body PII hoặc raw SQL parameter vào log. **Request ID và job ID phù hợp cho log/trace**, nhưng thường **không phù hợp làm metric label** vì cardinality quá cao.

### 8.1. Bảng dấu hiệu và chẩn đoán

| Hiện tượng | Metric thường đi kèm | Chẩn đoán ban đầu | Điều cần loại trừ |
| --- | --- | --- | --- |
| p95 HTTP tăng, Tomcat busy gần max | Request rate và busy threads tăng | Request thread saturation | Thread đang chờ DB/HTTP client, GC, CPU |
| HTTP latency tăng, CPU thấp, Hikari pending cao | Hikari active=max, acquire time tăng | Đợi connection | Query/transaction chậm, leak, lock DB |
| Executor queue depth/age tăng | Completed/s nhỏ hơn submitted/s | Worker xử lý không kịp | Task bị block, queue poison, phụ thuộc downstream |
| Queue depth thấp nhưng oldest age cao | Một partition/job không tiến triển | Head-of-line blocking hoặc stuck consumer | Retry scheduled, metric age tính sai |
| Rejections tăng, queue depth đôi khi thấp | Burst và scrape interval thưa | Pool đầy rất ngắn hoặc executor shutdown | Counter instrumentation thiếu submit path |
| HTTP 202 bình thường nhưng job completion trễ | Backlog, retry, DLQ tăng | Chậm xử lý async | Sai diễn giải `202` là hoàn tất |
| DB pool bình thường, upstream p99 tăng | HTTP client pending/timeout cao | Nghẽn HTTP outbound pool/downstream | DNS, TLS, circuit breaker, retry storm |
| Latency tăng sau autoscaling | Tổng DB connections, DB CPU/locks tăng | Tăng instance gây quá tải DB | Pool per-replica và query plan |

Một dashboard chỉ có line chart “queue depth” sẽ không đủ. Nên đặt lên cùng trục thời gian các biến: **arrival rate, service rate, active/max, queue wait, p95 latency, errors/rejections và deployment markers** để nhìn thấy chuỗi nguyên nhân.

## 9. PromQL và dashboard kiểm tra bão hòa

Các truy vấn dưới đây minh họa khi dùng Prometheus exporter. **Tên thực tế, tag và sự hiện diện của metric phải được xác minh** trên dịch vụ đã chạy. Một số Hikari meter cần tag `pool`, một số executor dùng tag `name` hoặc `pool` tùy cách bind. Không sao chép query mà không kiểm tra nhãn.

### 9.1. HTTP request rate và độ trễ

~~~promql
# Request/s của route đã được chuẩn hóa, không dùng raw path.
sum(rate(http_server_requests_seconds_count{
  uri="/api/v1/orders"
}[5m]))
~~~

Nếu đã bật histogram phù hợp:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      uri="/api/v1/orders"
    }[5m])
  )
)
~~~

Kết quả percentile theo **phân bố latency trong cửa sổ** (đơn vị giây), không phải trung bình p95 của từng instance. Với classic histogram cần giữ nhãn `le` trong phép tổng; với Prometheus native histograms có cách truy vấn khác. URI phải là **route template**, tránh nhãn mỗi order ID.

### 9.2. Hikari pool pressure

~~~promql
# Tỷ lệ connection đang được mượn, theo instance/pool.
hikaricp_connections_active
/
clamp_min(hikaricp_connections_max, 1)
~~~

~~~promql
# Giá trị pending cao nhất trong 5 phút gần đây.
max_over_time(hikaricp_connections_pending[5m])
~~~

Tỷ lệ cao không phải lỗi nếu workload chủ động dùng pool hiệu quả, nhưng tỷ lệ cao **đi cùng pending, acquire time và lỗi timeout** cần điều tra. Không tính tổng `active` của toàn cụm rồi chia `max` của một instance. Các vector trong phép chia phải có tập nhãn khớp theo cách scrape thực tế.

### 9.3. Executor queue và rejections

~~~promql
# Gauge tùy chỉnh từ mục 5; giữ phân tách theo pool.
max_over_time(app_executor_queue_depth{
  pool="order-io"
}[5m])
~~~

~~~promql
# Counter tăng khi submit bị từ chối qua ObservedTaskSubmitter.
sum(rate(app_executor_rejected_total{
  pool="order-io"
}[5m]))
~~~

Nếu `app.executor.rejected` được đăng ký dạng Micrometer Counter, Prometheus thường xuất với hậu tố `_total`. Counter cho biết sự kiện xảy ra giữa các lần scrape tốt hơn chỉ quan sát queue size. Cần bổ sung metric queue wait và task duration để phân biệt burst ngắn với backlog kéo dài.

### 9.4. Queue processing age và throughput

Với các metric **tùy chỉnh** giả định đã instrument:

~~~promql
app_jobs_oldest_ready_age_seconds{queue="order-notification"}
~~~

~~~promql
sum(rate(app_jobs_completed_total{
  queue="order-notification"
}[5m]))
~~~

`app_jobs_oldest_ready_age_seconds` và `app_jobs_completed_total` không phải tên mặc định của Spring Boot; đội phát triển phải tự phát hành metric từ queue/worker. So sánh completed/s với enqueued/s cùng loại công việc và quan sát oldest age để biết backlog có thực sự được giải quyết. Nếu không còn job READY, bộ phát hành metric cần quy ước rõ giá trị 0 hoặc việc xóa series.

## 10. Cảnh báo theo SLO, không theo một ngưỡng chung

Chỉ số “pool sử dụng trên 80%” có thể phù hợp dịch vụ này nhưng vô nghĩa với dịch vụ khác. Hãy đặt alert dựa trên **trạng thái cần hành động**, độ kéo dài, baseline, SLO và tác động người dùng:

| Mức | Ví dụ tín hiệu | Ý nghĩa / hành động |
| --- | --- | --- |
| **Warning** | Hikari pending có xu hướng tăng cùng acquire wait | Điều tra query/transaction, pool và deploy mới |
| **Warning** | Executor queue wait p95 tăng, oldest age gần SLA | Kiểm tra worker throughput/downstream, chuẩn bị hạn chế đầu vào |
| **Critical** | Rejections/connection acquire timeouts kéo dài và 5xx tăng | Xử lý incident: giảm tải, khôi phục dependency hoặc rollback thay đổi |
| **Critical** | Job cũ nhất vượt deadline nghiệp vụ, DLQ tăng | Công việc không hoàn tất dù HTTP đã trả 202; kích hoạt runbook bù/khôi phục |
| **Capacity** | Arrival rate tăng bền vững, service rate không theo kịp | Đánh giá sizing, batching, scale consumer, tối ưu DB |

Một rule minh họa cho cảnh báo có pending connection (chưa đủ để paging riêng):

~~~yaml
groups:
  - name: api-pool-observation
    rules:
      - alert: DbPoolWaitersPersistent
        expr: max_over_time(hikaricp_connections_pending[5m]) > 0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Có request đang chờ mượn connection DB"
~~~

Không dùng nguyên rule này làm pager production nếu lượng pending nhỏ thường xuyên là bình thường; kết hợp thêm acquire latency, timeout counter và user-facing SLO. `for: 5m` có nghĩa điều kiện expression vẫn đúng trong thời gian quy định theo cách Prometheus đánh giá; nếu scrape bị mất, series vắng mặt có thể khiến alert không hoạt động đúng dự kiến. Bổ sung cảnh báo exporter/target down và kiểm tra recording rules khi cần.

### 10.1. Error budget và thời gian hoàn tất

Với API đồng bộ, SLO có thể là tỷ lệ request thành công dưới một ngưỡng latency. Với API trả `202 Accepted`, phải có **SLO hoàn tất job** (ví dụ phần lớn job xử lý xong trong khoảng đã cam kết) ngoài SLO tiếp nhận request. Không coi `202` là thành công cuối của nghiệp vụ.

Thời gian chờ queue thường chiếm phần lớn end-to-end latency khi worker bị nghẽn. Dashboard nên phân biệt:

~~~text
HTTP request latency
    = thời gian nhận và xử lý request đồng bộ

Async job end-to-end latency
    = enqueue → đợi consumer → thực thi → hoàn tất/ghi trạng thái
~~~

Hai đại lượng không nhất thiết cộng trừ đơn giản: job có thể được tạo trong transaction, có retry, có nhiều consumer stage và được xử lý sau khi HTTP response đã trả. Quy ước timestamp và định nghĩa “hoàn tất” theo hợp đồng nghiệp vụ.

## 11. Backpressure, bounded queue và HTTP status

Quan sát chỉ thực sự có giá trị nếu hệ thống biết **phản ứng khi không còn năng lực nhận tải**. Một số chiến lược:

1. **Bounded queue:** đặt giới hạn số task được nhận trong RAM; khi đầy, trả lỗi có kiểm soát hoặc chuyển sang cơ chế bền vững nếu đã thiết kế.
2. **Timeout và deadline:** giới hạn đợi connection, request HTTP ngoài, DB query và thời gian tổng để một request không giữ thread mãi.
3. **Bulkhead:** tách thread/connection pool cho dependency quan trọng nhằm tránh một đối tác chậm khóa toàn bộ API.
4. **Rate limit:** giới hạn theo client/tenant phù hợp; không để một người dùng chiếm hết thread và queue.
5. **Backoff/retry budget:** client và worker retry khi thực sự có lợi; ngừng retry nếu vượt deadline hoặc có nguy cơ duplicate side effect.
6. **Scaling và tối ưu:** tăng worker/consumer khi downstream còn khả năng phục vụ; không scale mù làm database nghẽn thêm.

### 11.1. 429, 503 và 202 nói gì với client?

| HTTP status | Dùng khi | Không nên dùng để |
| --- | --- | --- |
| `429 Too Many Requests` | Quota/rate limit áp dụng cho client, tenant hoặc chính sách lưu lượng | Che giấu một SQL bug hoặc connection leak |
| `503 Service Unavailable` | Service tạm thời không nhận thêm request do quá tải/bảo trì/dependency không sẵn sàng | Trả thành công giả khi task chưa được persist |
| `202 Accepted` | Yêu cầu đã được **ghi nhận bền vững** cho xử lý sau; có resource trạng thái hoặc cơ chế tra cứu | Hứa thao tác đã hoàn thành hoặc gửi job chỉ vào queue RAM có thể mất |
| `504 Gateway Timeout` | Gateway không nhận được response kịp hạn từ upstream | Khẳng định upstream chắc chắn chưa commit |

Ví dụ khi từ chối do overload:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/problem+json
Retry-After: 5
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/overloaded",
  "title": "Service temporarily unavailable",
  "status": 503,
  "detail": "Hệ thống đang bận, vui lòng thử lại sau."
}
~~~

`Retry-After` là một **gợi ý** cho client, không buộc client phải retry. Với thao tác ghi như `POST /orders`, việc retry chỉ an toàn khi có **Idempotency-Key** hoặc hợp đồng tương đương, vì server có thể đã commit trước khi kết nối timeout. Trả 503 không tự rollback transaction nếu code phát sinh lỗi sau khi đã ghi dữ liệu.

### 11.2. Chuyển task rejection thành lỗi có kiểm soát

Nếu controller submit một tác vụ không bắt buộc phải hoàn tất đồng bộ, có thể bắt `TaskRejectedException` tại ranh giới phù hợp, tăng counter và ánh xạ sang `503`. Ví dụ `ObservedTaskSubmitter` đã tăng `app.executor.rejected` rồi ném tiếp. Tại HTTP layer:

~~~java
@RestControllerAdvice
public class OverloadErrors {
    @ExceptionHandler(TaskRejectedException.class)
    ResponseEntity<ProblemDetail> overloaded(TaskRejectedException ex) {
        ProblemDetail problem = ProblemDetail.forStatus(
            HttpStatus.SERVICE_UNAVAILABLE);
        problem.setTitle("Service temporarily unavailable");
        problem.setDetail("Không thể nhận thêm công việc vào lúc này.");
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .header(HttpHeaders.RETRY_AFTER, "5")
            .body(problem);
    }
}
~~~

Đây là **cách ánh xạ lỗi khi từ chối task trước khi tạo tác dụng phụ**. Không dùng cơ chế này để che lỗi sau khi transaction đã commit hoặc khi công việc bắt buộc phải được lưu bền vững. Với `@Async`, exception xảy ra trên worker và exception khi submit có đường truyền khác nhau; phải kiểm tra tình huống cụ thể. Nếu service cần bảo đảm thực hiện, hãy dùng outbox/job persisted và thiết kế `202` rõ ràng.

## 12. Kiểm thử và diễn tập tình huống bão hòa

Không cần tạo load quá lớn trên production để thử metric. Bắt đầu bằng unit/integration test có kích thước nhỏ và giới hạn rõ, sau đó load test chọn lọc ở môi trường có dữ liệu gần thật.

### 12.1. Test bounded executor và rejection

Ví dụ JUnit 5 tạo executor có một thread và một ô queue. Dùng latch để buộc task đầu đang chạy, task thứ hai đang chờ, và task thứ ba bị từ chối:

~~~java
@Test
void rejectsWhenSingleWorkerAndQueueAreFull() throws Exception {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(1);
    executor.setMaxPoolSize(1);
    executor.setQueueCapacity(1);
    executor.setRejectedExecutionHandler(
        new ThreadPoolExecutor.AbortPolicy());
    executor.initialize();

    CountDownLatch started = new CountDownLatch(1);
    CountDownLatch release = new CountDownLatch(1);
    try {
        executor.execute(() -> {
            started.countDown();
            try {
                release.await(3, TimeUnit.SECONDS);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });
        assertThat(started.await(2, TimeUnit.SECONDS)).isTrue();
        executor.execute(() -> {}); // Task thứ hai ở hàng chờ.
        assertThat(executor.getThreadPoolExecutor()
            .getQueue().size()).isEqualTo(1);

        assertThatThrownBy(() -> executor.execute(() -> {}))
            .isInstanceOf(TaskRejectedException.class);
    } finally {
        release.countDown();
        executor.shutdown();
    }
}
~~~

Test này dùng Spring `ThreadPoolTaskExecutor`, JUnit và AssertJ; import đã lược bớt. Latch làm trạng thái test quyết định hơn `Thread.sleep`. Đây là test **chính sách queue/rejection**, không chứng minh hiệu năng production. Khi muốn kiểm tra counter `app.executor.rejected`, gửi task qua `ObservedTaskSubmitter`, xác nhận Counter tăng và kiểm tra metric có tag `pool="order-io"`.

### 12.2. Integration test metric với Micrometer

Khi có `MeterRegistry` và bean executor chạy thật, có thể xác minh meter đã được đăng ký:

~~~java
@SpringBootTest
class ExecutorMetricsIT {
    @Autowired MeterRegistry registry;

    @Test
    void exposesBoundedExecutorMetrics() {
        Gauge queued = registry.find("app.executor.queue.depth")
            .tag("pool", "order-io")
            .gauge();
        assertThat(queued).isNotNull();
        assertThat(queued.value()).isGreaterThanOrEqualTo(0);
    }
}
~~~

Nếu dùng `SimpleMeterRegistry`, test kiểm tra instrumentation chứ **chưa** kiểm tra Prometheus exporter/scrape. Cần có test hoặc smoke check riêng tại môi trường triển khai để xác minh series xuất hiện đúng tên, tag và security policy. Để chứng minh gauge tăng khi queue có task, test phải tự tạo công việc bị block có kiểm soát, quan sát meter trong trạng thái đó rồi giải phóng latch; không chỉ assert meter tồn tại.

### 12.3. Test Hikari saturation và queue backlog an toàn

- Với Hikari, dùng một datasource **test riêng** có `maximumPoolSize` nhỏ. Giữ một số connection bằng latch/transaction trong test có timeout, sau đó xác minh có pending/acquire wait; giải phóng connection trong `finally`. Không chiếm pool production hoặc gây deadlock chủ ý ngoài môi trường cách ly.
- Với persisted job queue, seed số job `READY` được kiểm soát, dừng consumer trong môi trường test, xác minh depth/oldest age tăng; bật consumer lại và xác minh completion rate, queue drain và không tạo duplicate side effect.
- Với HTTP client pool, mock upstream trả delay để kiểm tra pending acquire, timeout và circuit breaker, nhưng đảm bảo dừng mock server/giải phóng connection sau test.
- Khi load test, tăng tải từng bước, ghi điểm bắt đầu nghẽn, latency, error rate, pool wait, DB resource và queue age; ngừng test theo ngưỡng an toàn. Không kết luận dựa trên throughput cực đại nếu p95/p99 hoặc số lượng lỗi đã vượt SLO.

### 12.4. Kịch bản HTTP theo trạng thái pool

| Tình huống | Điều quan sát | Kỳ vọng HTTP/nghiệp vụ |
| --- | --- | --- |
| Load bình thường | Thread/connection có headroom, queue wait thấp | 2xx/4xx đúng contract, latency trong SLO |
| Hikari hết connection tạm thời | Pending/acquire time tăng, có thể timeout | Lỗi ổn định, không lộ JDBC stack; transaction rollback phù hợp |
| Executor full khi nhận task mới | Rejection counter tăng | `503` hoặc cơ chế durable `202` theo hợp đồng; không báo thành công giả |
| Worker ngừng tiêu thụ queue | Oldest age và backlog tăng | `202` vẫn có thể đúng khi job đã persist, nhưng SLO hoàn tất bị vi phạm và phải alert |
| Retry storm sau lỗi dependency | Outbound rate tăng, CPU/pool/queue bão hòa | Retry budget, rate limit/circuit breaker bảo vệ hệ thống |
| Shutdown/redeploy | Pool đang đóng, job in-flight | Drain có giới hạn hoặc retry từ job persisted, không mất nghiệp vụ |

## 13. Runbook: xử lý một incident API chậm

Một quy trình ngắn, có thể diễn tập:

1. **Xác định tác động:** route nào bị ảnh hưởng, p95/p99, error budget, số lượng `429`/`503`/`504`, tenant/region nào bị ảnh hưởng; tránh dùng raw tenant ID làm metric label.
2. **Kiểm tra pool tại thời điểm lỗi:** HTTP busy/max, executor active/queue/rejected, Hikari active/idle/pending/acquire, HTTP client pool pending.
3. **So sánh arrival và service rate:** request vào có tăng? job completed/s có giảm? oldest queue age có tăng?
4. **Tìm nguyên nhân bên dưới:** slow SQL, lock, long transaction, external API latency, DB CPU, GC pause, thread dump, retry storm, consumer rebalance.
5. **Khoanh thay đổi mới:** deployment, feature flag, tăng số replicas, thay đổi pool size, schema, traffic pattern hoặc đối tác đang bảo trì.
6. **Giảm tác động trước:** ngừng retry quá mức, giảm concurrency/tải đầu vào, bật circuit breaker, scale consumer khi downstream còn headroom, rollback deploy nếu có căn cứ.
7. **Xác nhận phục hồi:** error rate và latency hạ xuống, pending/queue age giảm, completion bắt kịp arrival; kiểm tra các job bị backlog và dead-letter, không chỉ HTTP trở lại 200.
8. **Hậu kiểm:** bổ sung metric bị thiếu, chỉnh alert có ý nghĩa, viết test tái hiện và lưu kinh nghiệm trong runbook.

Không lấy thread dump, heap dump hoặc log SQL chứa dữ liệu nhạy cảm và chia sẻ công khai. Chúng có thể chứa URL, token, stack, parameter hoặc thông tin khách hàng; cần lưu ở nơi có phân quyền và thời hạn retention phù hợp.

## 14. Các lỗi quan sát phổ biến cần tránh

1. **Tưởng CPU thấp nghĩa là server rảnh:** thread có thể bị block khi chờ DB/HTTP client.
2. **Tăng HTTP thread để chữa Hikari pending:** làm thêm request chen vào hàng chờ, có thể khiến latency và tài nguyên xấu đi.
3. **Chỉ nhìn active thread:** cần queue depth, wait time, rejection và throughput mới nhận biết saturation.
4. **Chỉ nhìn queue depth:** queue nhỏ nhưng oldest age cao vẫn có thể vi phạm deadline nghiệp vụ.
5. **Nhầm HTTP 202 với job hoàn tất:** phải đo end-to-end completion time và retry/DLQ.
6. **Dùng queue không giới hạn để “không lỗi”:** tạo nợ xử lý và có nguy cơ cạn bộ nhớ.
7. **Đặt tag theo request ID/user ID/job ID:** tạo cardinality bùng nổ, tốn bộ nhớ và chi phí lưu trữ.
8. **Tính utilization toàn cụm sai mẫu số:** phải ghép từng pool/instance, sau đó tổng hợp theo mục tiêu.
9. **Lấy trung bình latency để kết luận:** p95/p99 và những request bị timeout/rejected có thể bị che khuất.
10. **Tin instrumentation mặc định có mọi metric:** các meter Tomcat/Netty/executor/queue phụ thuộc binder và cách cấu hình.
11. **Chỉ tăng replica:** có thể đồng thời tăng tổng connection DB và gây bão hòa downstream.
12. **Bật actuator công khai:** metric và các endpoint quản trị có thể lộ kiến trúc, workload, trạng thái hệ thống.

## 15. Bài tập thực hành

**Bài tập 1 — Chẩn đoán bottleneck.** Một REST API có p95 latency tăng từ 200 ms lên 2 giây, CPU chỉ 30%, Hikari `active=max`, `pending=15` và acquisition time tăng. Hãy đưa ra ba giả thuyết có thể kiểm chứng, chỉ số cần bổ sung và lý do không nên tăng Tomcat threads ngay. So sánh với tình huống Hikari pending bằng 0 nhưng HTTP client pool pending cao.

**Bài tập 2 — Instrument executor.** Cấu hình `ThreadPoolTaskExecutor` với core 2, max 4 và queue capacity 8. Tạo Micrometer gauges cho active, pool size, queue depth/remaining; tạo counter cho rejected và timer cho queue wait. Viết test dùng latch ép pool bão hòa, xác minh giá trị meter thay đổi và task mới bị từ chối. Giải thích vì sao max thread có thể chưa tăng khi queue chưa đầy.

**Bài tập 3 — Queue bền vững.** Thiết kế `POST /api/v1/reports` trả `202 Accepted`, ghi job vào database rồi xử lý async. Định nghĩa metric depth, oldest age, enqueued/processed/failed rate, retry và DLQ; viết tiêu chí test chứng minh job không mất khi worker restart. Trình bày cách client truy vấn trạng thái qua `GET /api/v1/jobs/{id}`.

**Bài tập 4 — Dashboard và alert.** Viết PromQL cho request rate, p95 latency của `POST /api/v1/orders`, tỷ lệ Hikari active/max, pending connection, executor rejection rate và oldest ready job age. Vẽ dashboard theo cùng timeline; đề xuất warning/critical gắn với SLO thay vì dùng một ngưỡng cố định cho mọi dịch vụ.

**Bài tập 5 — Diễn tập khôi phục.** Giả lập API gọi provider bị timeout và client retry nhiều lần. Theo dõi HTTP thread busy, outbound connection pending, executor queue depth, rejected requests và completion rate. Thiết kế timeout, circuit breaker, retry budget và mã HTTP để tránh retry storm; kiểm tra `Idempotency-Key` vẫn giữ nguyên cho request tạo đơn.

**Bài tập 6 — Điều tra sau autoscale.** Mỗi replica Hikari tối đa 25 connections; deployment tăng từ 4 lên 12 replicas. Hãy tính tổng connection tiềm năng trước/sau, đối chiếu DB connection limit và giải thích vì sao throughput có thể giảm. Đề xuất cách đo DB CPU/locks/SQL latency trước khi tăng pool hoặc số replica.

### Tiêu chí hoàn thành

Một lời giải đạt yêu cầu cần (1) phân loại đúng thread/connection/job queue; (2) instrument được ít nhất một executor và HikariCP, có số liệu wait/rejection; (3) liên hệ được saturation với latency/status HTTP và bất biến nghiệp vụ; (4) chứng minh bằng test bão hòa có kiểm soát; (5) đề xuất alert gắn với SLO/tuổi job thay vì một ngưỡng chung; và (6) bảo vệ actuator, tag cardinality và thông tin nhạy cảm trong log/trace.

## 16. Checklist trước khi vận hành REST API

- [ ] Biết request HTTP đang chạy trên servlet worker hay event loop, các pool và queue thực tế được đặt tên rõ ràng.
- [ ] Có request rate, error rate, latency p95/p99 và saturation theo đúng service/route.
- [ ] Thread pool có active/pool size/max, queue depth/wait time, rejected counter và chính sách khi đầy.
- [ ] HikariCP có active/idle/max/pending, acquire/usage time và timeout; DB cũng có slow query/lock/transaction telemetry.
- [ ] HTTP client pool, timeout và retry được đo tách biệt khỏi JDBC pool.
- [ ] Job queue có depth, oldest ready age, enqueue/complete rate, retry, DLQ và completion SLO.
- [ ] Metric labels là tập hữu hạn; request ID/job ID được đặt trong log/trace thay vì metric label.
- [ ] HTTP `429`, `503`, `202` và `Retry-After` phản ánh đúng overload, quota và tính bền vững của job.
- [ ] Alert và dashboard có baseline, sự tương quan metric và runbook; không tự động tăng pool khi chưa biết bottleneck.
- [ ] Actuator/exporter được giới hạn truy cập; credentials, headers, PII và dump không bị công khai.
- [ ] Đã có load/integration test tái hiện bão hòa, timeout, task rejection, worker backlog và recovery.

**Kết luận:** pool và queue là những nơi thể hiện sớm áp lực của REST API. Chỉ số hữu ích không dừng ở “còn bao nhiêu thread/connection”, mà phải cho biết **có bao nhiêu việc đang đến, bao nhiêu việc hoàn tất, mất bao lâu để được phục vụ và điều gì xảy ra khi năng lực cạn**. Khi kết hợp metric, trace, log, bounded queue, timeout và runbook, nhóm vận hành có thể phát hiện nghẽn trước khi nó trở thành lỗi hàng loạt và bảo vệ tính nhất quán nghiệp vụ của API.
