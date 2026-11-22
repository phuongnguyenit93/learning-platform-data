# Runbook cho queue đầy, executor reject và error spike

Trong một hệ thống Spring Integration chạy thực tế, ba cảnh báo thường xuất hiện gần như cùng lúc:

- <code>QueueChannel</code> đạt giới hạn capacity; producer chậm, timeout hoặc bị block.
- <code>ThreadPoolTaskExecutor</code> hết khả năng tiếp nhận, khiến <code>ExecutorChannel</code> phát lỗi task rejected.
- Tần suất <code>ErrorMessage</code> hoặc exception tăng đột biến, kéo theo retry, redelivery, DLQ và độ trễ cao hơn.

Ba tín hiệu có thể tạo thành **một vòng khuếch đại**: downstream chậm làm queue đầy; producer chuyển sang executor hoặc retry nhiều hơn; executor bị bão hòa; retry thất bại lại làm tăng error spike. Nếu người vận hành chỉ tăng capacity, bật retry vô hạn hoặc xóa hàng đợi để “hết đỏ dashboard”, hệ thống có thể mất message, nhân đôi side effect hoặc quá tải database.

Bài thuộc chương **Vận hành** của module **SPRING_INTEGRATION_RUNTIME**, tập trung cách Spring Integration chạy và điều phối flow qua channel, endpoint, consumer, poller và executor. Ta xây dựng một runbook có thể mang vào ca trực, kết hợp lifecycle <code>IntegrationFlow</code>, transaction, retry, message store, error handling, correlation, threading, hiệu năng và kiểm thử phục hồi.

> **Quy tắc an toàn:** Không xóa queue, tắt error handler, chuyển lỗi tới <code>nullChannel</code> hoặc xác nhận ACK thành công cho một message chưa hoàn tất chỉ để làm đẹp metric. Mọi thao tác giảm tải phải giữ đúng hợp đồng xử lý, retention và khả năng replay của hệ thống.

## 1. Mục tiêu của runbook và ranh giới trách nhiệm

Khi sự cố xảy ra, người trực cần nhanh chóng trả lời:

1. **Thành phần nào bão hòa đầu tiên?** Input channel, poller, executor, database, broker hay dịch vụ HTTP downstream?
2. **Message đã được tiếp nhận ở mức nào?** Đã vào queue, được giao cho worker, hoàn tất handler, commit DB, ACK broker hay chỉ trả <code>send() == true</code>?
3. **Lỗi hiện ở thread nào?** Sender, worker executor, scheduled poller hay callback adapter?
4. **Có mất/trùng message không?** Nguồn có redelivery, hệ thống có idempotency, DLQ và persistent store không?
5. **Phương án phục hồi tối thiểu là gì?** Giảm ingress, cho consumer drain, sửa lỗi phụ thuộc, mở rộng tài nguyên có kiểm chứng hoặc chuyển sang chế độ degraded.

Runbook này giả định Spring Integration 6.x, Java 17+ và một ứng dụng có quan sát runtime. Các lựa chọn về ACK, rollback, pause/resume và khả năng thay cấu hình nóng **phải được xác nhận với adapter và phiên bản thực tế**. Runbook không thay thế thiết kế disaster recovery cho database hoặc broker.

### Khái niệm cần phân biệt

| Tên | Thực tế xảy ra | Không được suy luận |
|---|---|---|
| **Queue full** | Một buffer bounded không nhận thêm message trong điều kiện hiện tại | Mọi handler đều dừng hoặc tất cả message đã mất |
| **Executor reject** | Executor từ chối nhận một task theo policy/capacity | Handler đã chạy và ném lỗi nghiệp vụ |
| **Error spike** | Số/tỷ lệ exception hoặc <code>ErrorMessage</code> tăng | Chắc chắn có nhiều message nghiệp vụ khác nhau thất bại |
| **Backlog** | Message tồn đọng chờ xử lý | Chỉ cần tăng thread là xử lý nhanh hơn |
| **Slow consumer** | Throughput hoàn tất thấp hơn tốc độ đến | Lúc nào cũng do thiếu CPU |
| **Redelivery/retry** | Một logical event có thể được thử lại nhiều lần | Mỗi attempt tương ứng một business event mới |
| **Accepted** | Một bước nhận message/task thành công | Đã commit/ACK/toàn bộ flow hoàn tất |

## 2. Sơ đồ quyết định trong 60 giây

~~~mermaid
flowchart TD
    A["Cảnh báo: lag, rejection hoặc error rate tăng"] --> B["Xác định channel/endpoint + thời điểm bắt đầu"]
    B --> C{"Tín hiệu đầu tiên?"}
    C -->|Queue ở capacity| Q["Nhánh A: Queue full"]
    C -->|TaskRejectedException| X["Nhánh B: Executor reject"]
    C -->|onError / ErrorMessage tăng| E["Nhánh C: Error spike"]
    C -->|Không rõ| D["Kiểm tra timeline queue, executor, DB, broker và deploy"]
    D --> C
    Q --> R["Giảm ingress an toàn + kiểm tra consumer/poller"]
    X --> S["Cô lập executor + giảm tốc độ submit"]
    E --> T["Phân loại root cause + chặn retry storm"]
    R --> V["Xác minh ACK/transaction, backlog drain và SLO"]
    S --> V
    T --> V
    V --> W["Mở ingress theo từng bước; theo dõi tái phát"]
~~~

**Quy tắc chọn nhánh:** Đừng dựa duy nhất vào cảnh báo có số lượng lớn nhất. Ví dụ <code>MessageDeliveryException</code> tăng có thể chỉ là **hậu quả** của queue đầy. Hãy dựng timeline từ thời điểm p95/p99 latency tăng, queue depth bắt đầu leo, executor active đạt max và lần lỗi đầu tiên của downstream.

## 3. Checklist 5 phút đầu: giữ bằng chứng và giới hạn thiệt hại

Trong những phút đầu, ưu tiên **đánh giá tính toàn vẹn message** trước khi thay đổi cấu hình.

| Thứ tự | Thu thập hoặc thực hiện | Lý do |
|---|---|---|
| 1 | Ghi incident ID, giờ bắt đầu, phiên bản deploy, service/instance/pod, tenant hoặc partition bị ảnh hưởng | So khớp timeline |
| 2 | Xác định channel bean ID, loại channel, endpoint consumer ID và <code>isRunning()</code> | Phân biệt queue với endpoint không hoạt động |
| 3 | Chụp queue depth/capacity, oldest-message age, ingress rate và completed-throughput | Tính tốc độ backlog phát triển |
| 4 | Chụp executor core/max/pool/active/queue/rejected, scheduler và thread dump nếu có block | Tìm saturation hoặc deadlock |
| 5 | Chụp error count/rate **theo loại gốc** và tổng số attempt; đọc một vài stack trace có correlation | Không nhầm retry amplification với số request lỗi |
| 6 | Xác minh nguồn có broker ACK/redelivery, DB commit hoặc store bền vững; chọn chính sách pause/rate-limit | Tránh mất message khi giảm tải |
| 7 | Kiểm tra dependency: DB pool, HTTP 429/5xx, connection timeout, broker lag, disk/heap/GC | Tìm bottleneck ở bên ngoài channel |
| 8 | Thông báo incident và đặt người sở hữu từng đường khôi phục | Tránh nhiều operator đồng thời thay capacity/poller |

Nếu chưa biết một message đã được lưu bền vững hay chưa, **không chủ động phá hủy in-memory queue/restart pod hàng loạt**. Cần xác nhận đường nguồn có thể phát lại và business idempotency hoạt động.

### Ba nhóm tác động cần phân loại

- **Toàn vẹn dữ liệu:** có nguy cơ mất message, side effect trùng hoặc ghi DB sai thứ tự không?
- **Tính sẵn sàng:** request bị timeout, producer bị block, consumer không chạy hoặc retry vô hạn không?
- **Độ trễ:** queue lag, end-to-end SLA và thời gian drain còn trong ngân sách không?

Severity và ngưỡng alert phải dựa trên SLO của sản phẩm, không suy ra một ngưỡng toàn ngành. Ví dụ queue ở 80% chỉ có ý nghĩa nếu kết hợp tốc độ tăng, khả năng drain và thời gian tới khi đầy.

## 4. Nhánh A — QueueChannel đầy: nhận diện chính xác

<code>QueueChannel</code> là <code>PollableChannel</code>: nó chứa message cho tới khi consumer gọi <code>receive()</code>. Khi tạo <code>new QueueChannel(capacity)</code>, buffer có giới hạn. Tài liệu Spring Integration khuyến nghị đặt capacity rõ thay vì dùng queue mặc định gần như không giới hạn trong production.

Đối với queue in-memory bounded:

| Lệnh | Khi còn chỗ | Khi queue đầy |
|---|---|---|
| <code>send(message)</code> | Thường đưa message vào queue và trả về | Có thể **block chờ chỗ trống**, cần kiểm tra caller/gateway timeout |
| <code>send(message, 0)</code> | Trả <code>true</code> ngay | Trả <code>false</code> ngay, không chờ |
| <code>send(message, timeoutMillis)</code> | Nhận message nếu còn chỗ hoặc có chỗ trước hạn | Trả <code>false</code> khi hết hạn |
| <code>receive(0)</code> | Lấy message ngay nếu có | Trả <code>null</code> nếu queue rỗng |
| <code>receive(timeoutMillis)</code> | Lấy message hoặc chờ tới hạn | Không có message trước hạn thì trả <code>null</code> |

**Queue đầy không phải lỗi “Dispatcher has no subscribers”.** Nó không cần subscriber trực tiếp; xử lý thường diễn ra qua <code>PollingConsumer</code>. Nếu chỉ nhìn số subscriber rồi đăng ký một handler vào queue, bạn đang chẩn đoán sai loại channel.

### Tín hiệu xác nhận queue đầy

~~~text
queue_size ≈ queue_capacity
  + tốc độ enqueue > tốc độ dequeue hoàn tất
  + send latency hoặc send timeout tăng
  + oldest-message age tăng
~~~

Cần xác nhận metric phù hợp với triển khai: <code>QueueChannel</code> in-memory có thể đọc <code>getQueueSize()</code>; queue dựa trên <code>JdbcChannelMessageStore</code> có semantics và cách lấy size/metric khác. Metric queue depth không được coi là bằng chứng DB transaction/consumer success.

### Quy trình chẩn đoán queue full

1. **Tìm queue thật.** Kiểm tra bean type, capacity, số message đang chờ và số instance. Có thể nhiều pod có queue **riêng**, nên một pod đầy trong khi các pod khác trống.
2. **Kiểm tra consumer đã start.** Với <code>PollingConsumer</code>, xem <code>isRunning()</code>, trigger, <code>maxMessagesPerPoll</code>, <code>receiveTimeout</code>, task scheduler và lỗi startup.
3. **Đo completion rate.** Một poller có thể dequeue nhanh nhưng downstream xử lý thất bại liên tục; throughput dequeue không phải throughput thành công.
4. **Tìm giới hạn phía sau.** DB connection pool, lock, HTTP timeout, CPU, disk, GC, remote rate limit, slow query và retry advice.
5. **Đánh giá nguồn.** Input có burst tạm thời hay producer duy trì tốc độ cao hơn năng lực xử lý? ACK đã xảy ra trước khi đưa vào in-memory queue chưa?
6. **Đặt phương án giảm tải.** Pause/rate-limit inbound adapter theo khả năng source, giữ message ở broker bền vững nếu có; không thả vào <code>nullChannel</code>.
7. **Khôi phục consumer.** Sửa root cause, start đúng endpoint nếu bị stop có chủ đích kết thúc, hoặc mở rộng consumer theo key/partition khi an toàn.

### Hành động ưu tiên và điều kiện an toàn

| Hành động | Khi nào có ích? | Rủi ro cần xét |
|---|---|---|
| Giảm tốc độ producer/rate-limit | Enqueue vượt khả năng xử lý | Source không hỗ trợ pause có thể cần NACK/DLQ hoặc backpressure khác |
| Start lại polling endpoint **đang bị stop ngoài ý muốn** | Queue có message, consumer <code>isRunning=false</code> | Không start nếu đang bảo trì, tenant DELETING hoặc schema chưa sẵn sàng |
| Chỉnh <code>maxMessagesPerPoll</code>/trigger | Poller chưa tận dụng đủ tài nguyên và downstream còn headroom | Poll quá nhiều có thể làm cạn DB pool, giữ transaction/lock lâu |
| Scale consumer/partition | Có nhiều message độc lập và downstream chịu được | Ordering, correlation group, duplicate và lock |
| Tăng queue capacity có kiểm chứng | Burst ngắn, throughput dài hạn vẫn đủ | Chỉ trì hoãn cạn heap/storage; không sửa bottleneck |
| Dùng persistent store/broker | Cần chịu downtime/restart và replay | Phải thiết kế transaction/serializer/retention; không tự biến xử lý thành exactly-once |
| Xóa queue hoặc skip message | Chỉ khi policy nghiệp vụ cho phép và có audit/quarantine rõ ràng | Có thể mất dữ liệu vĩnh viễn |

## 5. Cấu hình queue bounded và poller có giới hạn

Ví dụ Java 17+, Spring Integration 6.x: một flow nhận đơn hàng từ <code>orders.backlog</code>, poll tối đa 10 message mỗi chu kỳ và gọi service đồng bộ.

**Payload và service nghiệp vụ minh họa:**

~~~java
public record OrderCommand(String eventId, String orderId, int quantity) {}

@Service
public class OrderService {
    @Transactional
    public void process(OrderCommand command) {
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        // Validation và cập nhật database theo eventId idempotent.
        // Transaction chỉ bao quanh thao tác phù hợp với manager hiện hành.
    }
}
~~~

**Channel và polling consumer:**

~~~java
@Configuration
@EnableIntegration
public class BacklogFlowConfig {
    @Bean(name = "orders.backlog")
    QueueChannel ordersBacklog() {
        return new QueueChannel(128);
    }

    @Bean
    IntegrationFlow orderWorkerFlow(OrderService orderService) {
        return IntegrationFlow.from("orders.backlog")
            .handle(orderService, "process", endpoint -> endpoint
                .id("orders.worker")
                .poller(Pollers.fixedDelay(200)
                    .maxMessagesPerPoll(10)
                    .receiveTimeout(0)))
            .get();
    }
}
~~~

<code>OrderService.process(...)</code> là service nghiệp vụ do ứng dụng định nghĩa, chịu trách nhiệm validation, transaction/idempotency. Các API chính: <code>org.springframework.integration.dsl.IntegrationFlow</code>, <code>org.springframework.integration.dsl.Pollers</code>, <code>org.springframework.integration.channel.QueueChannel</code>, <code>org.springframework.integration.config.EnableIntegration</code>.

**Lưu ý:** <code>fixedDelay(200)</code> là chu kỳ tính bằng mili giây **sau khi poll task hoàn tất**; <code>maxMessagesPerPoll(10)</code> là giới hạn số lượt receive mỗi chu kỳ. Đây không phải cam kết đạt 10 message/200 ms vì handler có thể chậm, receive không có dữ liệu hoặc scheduler không đủ worker.

Theo tài liệu Spring Integration, <code>PollingConsumer</code> nếu không cấu hình <code>maxMessagesPerPoll</code> có mặc định <code>-1</code> (lặp nhận đến khi hết message), khác với <code>SourcePollingChannelAdapter</code> mặc định <code>1</code>. Thay đổi tham số phải hiểu đúng loại endpoint. Với một queue liên tục có message, poll không giới hạn có thể chiếm scheduler lâu; giá trị dương hữu hạn thường dễ kiểm soát fairness và shutdown.

### Sender không được bỏ qua kết quả send

~~~java
public void submit(PollableChannel backlog, OrderCommand command) {
    Message<OrderCommand> message = MessageBuilder
        .withPayload(command)
        .setHeader("businessEventId", command.eventId())
        .build();

    boolean accepted = backlog.send(message, 500);
    if (!accepted) {
        throw new IllegalStateException("Order backlog hết chỗ trong 500 ms");
    }
}
~~~

Ví dụ giả định <code>OrderCommand.eventId()</code> là khóa nghiệp vụ đã định nghĩa trong ứng dụng. Khi timeout, **đường gọi bên ngoài** phải quyết định HTTP 429/503, NACK/requeue hoặc ghi durable retry theo hợp đồng. Throw exception không đảm bảo source tự redeliver nếu upstream đã ACK trước đó.

Không tăng timeout vô hạn ở API đồng bộ; cách đó có thể khiến số thread request bị block tăng và dẫn tới outage thứ cấp ở ingress.

## 6. Nhánh B — Executor reject: khác queue full như thế nào?

<code>ExecutorChannel</code> gọi một <code>TaskExecutor</code> để chạy subscriber. Nếu dùng <code>ThreadPoolTaskExecutor</code> bounded, việc tiếp nhận task phụ thuộc:

1. Có thể dùng thread tới <code>corePoolSize</code> không?
2. Nếu core đã bận, hàng đợi task còn chỗ không?
3. Nếu hàng đợi đã đầy, có thể mở thêm thread tới <code>maxPoolSize</code> không?
4. Nếu tất cả đã bão hòa, **rejection policy** quyết định throw, chạy ở caller hoặc loại bỏ task.

~~~mermaid
flowchart TD
    A["ExecutorChannel submit task"] --> B{"Có thread < corePoolSize?"}
    B -->|Có| C["Worker chạy task"]
    B -->|Không| D{"Queue executor còn chỗ?"}
    D -->|Có| E["Đưa task vào executor queue"]
    D -->|Không| F{"Pool < maxPoolSize?"}
    F -->|Có| C
    F -->|Không| G["RejectionHandler"]
    G --> H["Abort / CallerRuns / Discard / DiscardOldest"]
~~~

**Đừng nhầm executor queue với <code>QueueChannel</code>.** Executor queue chứa <code>Runnable</code>/task chưa chạy, còn <code>QueueChannel</code> chứa <code>Message</code> đang chờ polling consumer. Hai nơi có capacity, retry và ý nghĩa persisted khác nhau.

### Nhận diện exception và phạm vi lỗi

Spring <code>ThreadPoolTaskExecutor</code> có thể ném <code>TaskRejectedException</code> khi không nhận task theo policy mặc định <code>AbortPolicy</code>. Spring Integration dispatcher có thể bọc lỗi này trong một <code>MessagingException</code>/<code>MessageDeliveryException</code> tùy đường gọi và phiên bản.

**Tình huống cần tách:**

| Tín hiệu | Diễn giải đúng |
|---|---|
| <code>TaskRejectedException</code> ngay trong <code>send()</code> | Task **chưa được executor nhận**; phải xử lý lỗi tại sender/adapter |
| <code>send()</code> thành công, handler ném lỗi sau đó | Task đã được nhận; lỗi chạy ở **worker**, không còn call stack của sender |
| <code>CallerRunsPolicy</code> được dùng | Sender **có thể thực thi handler**; latency và transaction/thread boundary thay đổi |
| <code>DiscardPolicy</code> hoặc <code>DiscardOldestPolicy</code> | Có thể bỏ task mà không tạo tín hiệu thất bại như AbortPolicy | Không phù hợp với message nghiệp vụ bắt buộc giao nếu không có biện pháp bảo toàn |
| Executor đã shutdown | Task mới bị reject dù active/queue không cao | Kiểm tra lifecycle và deploy/shutdown timeline |

### Cấu hình executor bounded có chủ đích

~~~java
@Configuration
public class WorkerPoolConfig {
    @Bean(name = "ordersWorkerPool")
    ThreadPoolTaskExecutor ordersWorkerPool() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(64);
        executor.setThreadNamePrefix("orders-");
        executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.AbortPolicy());
        return executor; // Spring quản lý initialize/shutdown của bean.
    }

    @Bean(name = "orders.executor")
    ExecutorChannel ordersExecutor(
            @Qualifier("ordersWorkerPool") ThreadPoolTaskExecutor pool) {
        return new ExecutorChannel(pool);
    }
}
~~~

Các kiểu thuộc <code>org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor</code>, <code>org.springframework.integration.channel.ExecutorChannel</code>, <code>java.util.concurrent.ThreadPoolExecutor</code> và <code>org.springframework.beans.factory.annotation.Qualifier</code>. Cần thêm một consumer endpoint cho <code>orders.executor</code> trong ứng dụng thật; khai báo channel đơn độc **không** tạo subscriber.

Ví dụ này là **một topology thay thế** cho queue + poller ở mục 5, không dùng chung tên input để vô tình xử lý một message hai lần.

### Snapshot pool khi báo reject

~~~java
@Component
public class ExecutorSnapshot {
    private final ThreadPoolTaskExecutor pool;

    public ExecutorSnapshot(
            @Qualifier("ordersWorkerPool") ThreadPoolTaskExecutor pool) {
        this.pool = pool;
    }

    public void logSnapshot() {
        ThreadPoolExecutor delegate = pool.getThreadPoolExecutor();
        log.warn("poolSize={}, active={}, queued={}, remaining={}, " +
                 "completed={}, shutdown={}",
            pool.getPoolSize(),
            pool.getActiveCount(),
            delegate.getQueue().size(),
            delegate.getQueue().remainingCapacity(),
            delegate.getCompletedTaskCount(),
            delegate.isShutdown());
    }
}
~~~

Trong production, expose cùng thông tin qua Micrometer/Actuator hoặc instrumentation tương đương; không in một log nhiều lần/giây nếu lỗi đã tạo log storm. <code>getThreadPoolExecutor()</code> chỉ hợp lệ sau khi bean đã initialize; snapshot chỉ mô tả thời điểm đọc, không phải cam kết task kế tiếp sẽ được chấp nhận.

## 7. Runbook executor reject: hành động tại hiện trường

### Bước 1 — Xác định reject do saturation hay shutdown

Khi có <code>TaskRejectedException</code>, ghi lại:

~~~text
executorBeanName, poolSize, corePoolSize, maxPoolSize
activeCount, queueSize, queueRemainingCapacity
isShutdown, isTerminating
channelBeanName, endpointId, threadName
messageId, correlationId, businessEventId
rejectionPolicy, firstSeenAt, requestRate
~~~

Nếu <code>isShutdown=true</code> nhưng hệ thống vẫn có producer gửi vào <code>ExecutorChannel</code>, khả năng cao lifecycle order hoặc dynamic flow removal là nguyên nhân. Nếu active ở max, queue đầy và downstream latency tăng, đó là saturation. Nếu active thấp mà vẫn reject, kiểm tra custom <code>RejectedExecutionHandler</code>, executor proxy, shutdown state hoặc giới hạn khác.

### Bước 2 — Giảm lượng task được submit, giữ đường hồi phục

Ưu tiên giảm ingress ngay tại **đường nhận có khả năng backpressure**:

- HTTP ingress: đặt timeout/rate limit, trả 429/503 cho công việc **chưa được nhận bền vững**, cung cấp retry hint khi hợp đồng cho phép.
- JMS/Kafka/AMQP: pause consumer, điều chỉnh concurrency hoặc xử lý nack/requeue theo adapter; **không ACK khi task chưa có bảo đảm lưu trữ/hoàn tất**.
- Scheduler/poller: giảm tốc độ nhận, giới hạn <code>maxMessagesPerPoll</code> hoặc stop đúng adapter theo quy trình; kiểm tra công việc đang chạy.
- Internal producer: dùng bounded queue/persistent outbox và retry có backoff thay vì vòng gửi lặp không giới hạn.

Nếu chính producer cũng đang nằm trên executor bão hòa, hãy chẩn đoán chu kỳ deadlock hoặc thread starvation: một worker đang chờ task mà nó vừa submit vào **cùng pool** đã đầy có thể tự gây nghẽn.

### Bước 3 — Tìm handler giữ thread lâu

Kiểm tra thread dump ở lúc saturation và phân loại:

| Worker đang làm gì? | Hướng điều tra |
|---|---|
| JDBC query / chờ connection pool | Slow query, pool size, transaction giữ lock, DB saturation |
| HTTP client sync / TLS / DNS | Timeout, circuit breaker, remote 429/5xx, connection pooling |
| <code>LockRegistry.obtain()</code> / <code>lock()</code> | Hot business key, distributed lease, deadlock, time giữ lock |
| <code>Thread.sleep()</code> trong retry backoff | Retry advice, backoff không thích hợp, số attempt |
| Waiting on future của task cùng pool | Thread starvation/deadlock do nested submission |
| GC hoặc CPU-bound compute | CPU quota, GC, payload conversion, mã hóa, parse/serialize |

Đừng tăng thread cho tới khi hiểu bottleneck: 16 thread cùng chờ 8 connection JDBC không làm DB nhanh hơn và có thể nhân đôi queue wait hoặc timeout.

### Bước 4 — Quyết định rejection policy

| Policy | Hành vi khi pool/queue đầy | Khuyến nghị khi xử lý message quan trọng |
|---|---|---|
| <code>AbortPolicy</code> | Ném reject; sender biết task không được chấp nhận | Hợp lý khi upstream có failure contract, retry có giới hạn và idempotency |
| <code>CallerRunsPolicy</code> | Sender tự thực thi task trong một số trường hợp | Có thể tạo backpressure, nhưng **đổi thread/transaction/latency** bất ngờ |
| <code>DiscardPolicy</code> | Có thể bỏ task im lặng | Không dùng nếu message bắt buộc phải xử lý |
| <code>DiscardOldestPolicy</code> | Có thể loại task cũ trong queue | Nguy cơ mất/đảo thứ tự message, rất khó bảo đảm delivery |
| Custom reject handler | Tùy ứng dụng, có thể publish retry hoặc ghi bền vững | Phải chứng minh idempotency, failure handling và không loop vô hạn |

**Bẫy CallerRuns:** Nếu <code>ExecutorChannel</code> chạy handler ngay trên thread sender trong thời điểm quá tải, transaction thread-bound của sender có thể bao trùm handler **chỉ trong một số request**; lúc bình thường handler chạy ở worker khác. Đây là thay đổi ngữ nghĩa khó dự đoán, nên không dùng CallerRuns để “bảo đảm chung một transaction”.

### Bước 5 — Khôi phục rồi mở ingress theo bậc

1. Sửa dependency gốc hoặc cấu hình sai gây block/reject.
2. Xác nhận completed throughput tăng ổn định, queue task giảm và không có thread deadlock.
3. Xác minh message lỗi đã vào đúng đường retry/DLQ/quarantine hoặc sẽ redeliver từ nguồn.
4. Mở ingress từng phần, quan sát active/queue/reject và p99, không mở tối đa ngay.
5. Khi error rate và lag trở về ngân sách, đóng incident; giữ các bản ghi failed message phục vụ đối soát.

## 8. Nhánh C — Error spike: đếm lỗi ở đúng ranh giới

**Error spike** là sự tăng đột biến của **tần suất hoặc tỷ lệ lỗi**, không phải tên một exception. Có thể xuất hiện các dấu hiệu:

~~~text
integration handler error count tăng
errorChannel nhận nhiều ErrorMessage
HTTP/JDBC timeout tăng
broker redelivery/retry tăng
DLQ ingress tăng
executor rejected tăng
~~~

Một lỗi nguồn có thể tạo nhiều log, nhiều retry attempt và nhiều <code>ErrorMessage</code>. Ví dụ 100 logical event thất bại × 4 attempt = 400 handler failures; nếu mỗi failure được log ở hai tầng thì có thể có 800 dòng log. Vì vậy cần một metric **theo business event ID** hoặc đơn vị xử lý logic bên cạnh số attempt, để không diễn giải sai mức độ sự cố.

### Lỗi đồng bộ, bất đồng bộ và poller đi theo các đường khác nhau

| Ranh giới | Nơi lỗi có thể xuất hiện | Cách kiểm tra |
|---|---|---|
| <code>DirectChannel</code> → handler | Ngay trên thread của sender; exception đi ngược call stack | Gateway/caller logs và cause chain |
| <code>ExecutorChannel</code> → handler | Ở worker sau khi <code>send()</code> đã chấp nhận task | Executor error handling, <code>ErrorMessage</code> và worker logs |
| <code>QueueChannel</code> → polling consumer | Ở poller/scheduler thread | Poller error channel, <code>MessagePublishingErrorHandler</code>, transaction rollback |
| <code>SourcePollingChannelAdapter</code> | Ở scheduled poll task khi receive/dispatch thất bại | Source/adapter logs, error channel, receive và send semantics |
| Reactive endpoint | <code>onError</code> signal trong subscription | Subscriber, <code>onErrorResume</code>/<code>retryWhen</code>, context propagation |
| Broker inbound adapter | Callback/listener thread hoặc worker downstream | Adapter-specific ACK/requeue, retry topic/DLQ và offset |

Trong Spring Integration, asynchronous error handling thường chuyển exception thành <code>ErrorMessage</code> và gửi tới <code>errorChannel</code> theo header của message hoặc global channel. Với scheduled poller, framework thường sử dụng <code>MessagePublishingErrorHandler</code>; nếu cấu hình custom <code>TaskScheduler</code>, cần đảm bảo chính sách error handler được đặt phù hợp.

**Không khẳng định mọi exception tự vào global errorChannel.** Exception xảy ra trong handler đồng bộ qua <code>DirectChannel</code> thường được ném cho caller. Một <code>ExecutorChannel</code> có custom executor/error handler, một adapter broker hoặc một reactive subscription có thể có ranh giới lỗi riêng.

### Nguyên nhân gốc của error spike

| Nhóm | Dấu hiệu điển hình | Xác minh |
|---|---|---|
| Dependency outage | Connection refused, HTTP 503, socket timeout | Health/latency của DB, broker và remote API |
| Rate limit | HTTP 429, quota exceeded | Hạn mức remote, retry-after, concurrency hiện tại |
| Dữ liệu độc hại/poison message | Cùng payload hoặc business ID lỗi lặp lại | Root cause, deserialize/conversion, DLQ record |
| Schema/version drift | Class cast, JSON mapping, SQL column missing | Thời điểm deploy, serializer và migration |
| Thread/queue saturation | <code>TaskRejectedException</code>, send timeout | Executor queue và handler latency |
| Lock/transaction | Deadlock, lock wait timeout, rollback-only | DB locks, transaction logs, retries |
| Lifecycle/wiring | <code>Dispatcher has no subscribers</code>, missing bean | Endpoint ID, <code>isRunning()</code>, dynamic flow |
| Error flow bị lỗi | Lỗi mới khi publish <code>ErrorMessage</code> | Original exception và nested exception |

### Quy trình chẩn đoán error spike

1. Chụp error rate theo **endpoint, exception class được phân nhóm, result và thời gian**; giữ denominator tổng số logical attempt/event.
2. Xác định **exception đầu tiên theo timeline**, không chọn stack trace cuối cùng do recoverer tạo.
3. So sánh sự cố với deployment, cấu hình, certificate/secret rotation, DB migration, tăng tải hoặc lỗi hạ tầng.
4. Kiểm tra retry có đang nhân tải lên dependency đang hỏng không.
5. Với poison message, xác định có cần **quarantine** thay vì retry liên tục.
6. Với transient failure, đặt bounded retry + exponential backoff + jitter/circuit breaker phù hợp, tránh đồng loạt retry.
7. Xác nhận error flow còn subscriber và không có trường hợp log/error sink quá tải thành điểm nghẽn mới.
8. Đối soát trạng thái DB, broker ACK/offset, outbox, idempotency trước khi replay.

### Tránh vòng khuếch đại từ retry storm

~~~mermaid
flowchart LR
    A["Downstream trả lỗi"] --> B["Retry dồn dập"]
    B --> C["Pool / queue bão hòa"]
    C --> D["Timeout / reject"]
    D --> E["ErrorMessage và redelivery tăng"]
    E --> B
    F["Bounded attempts + backoff + quarantine"] -. "cắt vòng lặp" .-> B
~~~

Ví dụ, một dependency nhận được 100 request/s trước sự cố; nếu mỗi request lập tức retry thêm 3 lần, tải phát sinh có thể tăng lên tới **400 attempt/s** trong một khoảng ngắn. Đây là ví dụ giả định; phân bố thực tế phụ thuộc timeout, concurrency, backoff và success/failure. Hãy tính **attempt load**, không chỉ inbound business events.

## 9. Thiết kế error flow quan sát an toàn

Global <code>errorChannel</code> mặc định là <code>PublishSubscribeChannel</code> và có subscriber logging lỗi do framework cung cấp. Từ Spring Integration 5.4.3, global error channel mặc định yêu cầu có subscriber để tránh lỗi bị bỏ im lặng. Khi ứng dụng dừng, một <code>ErrorMessage</code> được phát nhưng không còn subscriber có thể tạo **<code>MessageDispatchingException</code> thứ cấp**.

Một consumer quan sát tùy chỉnh:

~~~java
@Component
public class OperationalErrorObserver {
    private final MeterRegistry meters;

    public OperationalErrorObserver(MeterRegistry meters) {
        this.meters = meters;
    }

    @ServiceActivator(inputChannel = "errorChannel")
    public void observe(ErrorMessage error) {
        Throwable cause = error.getPayload();
        String kind = classify(cause); // tập nhãn nhỏ, không lấy raw exception text

        meters.counter("integration.operation.errors",
            "kind", kind).increment();
    }

    private String classify(Throwable exception) {
        Throwable current = exception;
        while (current.getCause() != null && current.getCause() != current) {
            current = current.getCause();
        }
        if (current instanceof java.util.concurrent.RejectedExecutionException
                || current instanceof org.springframework.core.task.TaskRejectedException) {
            return "executor_rejected";
        }
        if (current instanceof java.net.SocketTimeoutException) {
            return "dependency_timeout";
        }
        if (current instanceof IllegalArgumentException) {
            return "invalid_message";
        }
        return "other";
    }
}
~~~

Các kiểu chính: <code>org.springframework.integration.annotation.ServiceActivator</code>, <code>org.springframework.messaging.support.ErrorMessage</code>, <code>io.micrometer.core.instrument.MeterRegistry</code>. Hàm <code>classify</code> chỉ minh họa **phân nhóm nguyên nhân**, không thay thế chính sách phân loại của hệ thống thật.

**Cảnh báo nghiệp vụ:** Subscriber trên <code>errorChannel</code> chỉ chứng minh <code>ErrorMessage</code> đã được quan sát. Việc method trả về bình thường **không có nghĩa** input message đã được rollback, requeued, ACK đúng hoặc phục hồi nghiệp vụ. Ở một số error/recovery path, việc nuốt exception có thể khiến caller/advice coi lỗi đã xử lý. Muốn retry hay DLQ phải cấu hình rõ và kiểm thử adapter tương ứng.

Không đưa <code>cause.getMessage()</code>, tenant ID hoặc business event ID làm meter tag mặc định: giá trị không giới hạn gây cardinality rất cao. Khi cần điều tra một message, lưu correlation và failed message metadata trong log/tracing có phân quyền hoặc DLQ phù hợp.

## 10. Ba sự cố liên quan nhau: tìm nút cổ chai đầu tiên

Một flow thực tế có thể có:

~~~text
Broker inbound
   → orders.backlog (QueueChannel bounded)
   → PollingConsumer
   → orders.executor (ExecutorChannel)
   → validation / JDBC / HTTP handler
   → outbound adapter
                 └→ errorChannel hoặc DLQ khi lỗi
~~~

Khi handler HTTP chậm hơn bình thường:

~~~mermaid
sequenceDiagram
    participant B as Broker producer
    participant Q as QueueChannel
    participant P as PollingConsumer
    participant X as ExecutorChannel
    participant D as Downstream HTTP/DB
    B->>Q: enqueue M1..Mn
    Q->>P: poll message
    P->>X: submit handler task
    X->>D: request chậm
    Note over X,D: Active workers tăng, executor queue đầy
    P->>X: submit task mới
    X--xP: reject
    Note over P,Q: Poller lỗi, retry/redelivery có thể tăng
    B->>Q: tiếp tục enqueue
    Note over B,Q: QueueChannel đạt capacity, send chậm/fail
~~~

Trong chuỗi này, chỉ tăng <code>QueueChannel</code> capacity **không chữa được** HTTP downstream đang chậm. Chỉ tăng executor threads có thể làm HTTP service hoặc DB sụp nhanh hơn. Chỉ tăng retry attempts sẽ tạo thêm request và lỗi.

### Quy tắc xác định điểm khởi phát

| Tín hiệu đầu tiên theo timeline | Khả năng cao | Thao tác ưu tiên |
|---|---|---|
| DB/HTTP latency tăng, rồi executor active tăng | Downstream chậm là gốc | Giới hạn concurrency/rate, sửa dependency |
| Executor <code>shutdown=true</code> ngay sau deploy | Lifecycle order/cấu hình | Xác minh flow registration và shutdown/restart policy |
| Queue depth tăng, poller <code>isRunning=false</code> | Consumer dừng hoặc không start | Kiểm tra startup/error state; start có kiểm soát |
| Queue depth tăng, poller vẫn chạy nhưng completion thấp | Slow handler/retry/DB lock | Đo throughput thành công và thread dump |
| Error spike bắt đầu ngay sau schema change | Incompatible payload/DB | Rollback deploy hoặc compatibility fix an toàn |
| Error spike toàn cùng một event ID | Poison message và retry loop | Cô lập event, ghi DLQ/quarantine, ngừng replay vô hạn |
| Chỉ một tenant/key khiến queue lag tăng | Hot partition, lock contention | Phân tích business key, phân vùng hoặc giảm tải tại key |

## 11. Tính backlog, headroom và thời gian drain

Không thể quyết định capacity chỉ từ con số “queue đã ở 90%”. Cần tốc độ ingress, throughput **hoàn tất thành công** và thời gian chờ tối đa được phép.

Ký hiệu:

- <code>λ</code>: số message mới/giây đến queue.
- <code>μ</code>: số message/giây được xử lý hoàn tất theo hợp đồng.
- <code>B</code>: số message đang tồn đọng.
- <code>C</code>: capacity của queue.

Khi <code>λ > μ</code> đủ lâu:

\[
\frac{dB}{dt} \approx \lambda - \mu
\]

Nếu tốc độ giữ ổn định và <code>B &lt; C</code>, thời gian lý thuyết trước khi đầy:

\[
t_{\mathrm{full}} \approx \frac{C-B}{\lambda-\mu}
\]

Khi ingress đã thấp hơn throughput (<code>μ > λ</code>), thời gian drain lý thuyết:

\[
t_{\mathrm{drain}} \approx \frac{B}{\mu-\lambda}
\]

**Ví dụ minh họa:** queue capacity 10.000, hiện có 4.000 message; ingress 600 msg/s, completion 450 msg/s. Backlog tăng khoảng 150 msg/s; nếu không đổi, còn 6.000 chỗ tương đương **khoảng 40 giây** trước khi đầy. Nếu giảm ingress xuống 300 msg/s nhưng completion giữ 450 msg/s, thời gian drain 4.000 message là **khoảng 27 giây**.

Đây là phép tính gần đúng, **không phải ETA có thể cam kết**: lưu lượng thường bursty, retry làm thay đổi <code>λ</code>, transaction rollback làm thay đổi <code>μ</code>, fan-out có thể nhân task, và nhiều queue nối tiếp nhau có thể có backlog khác nhau.

### Dùng Little's Law để nhìn độ trễ hàng đợi

Với hệ thống ổn định, số message trung bình đang chờ/xử lý <code>L</code> liên hệ throughput <code>λ</code> và thời gian lưu trú <code>W</code>:

\[
L = \lambda W
\]

Nếu throughput 500 msg/s mà có 5.000 message đang lưu trú trong một đoạn flow, thời gian trung bình nằm trong đoạn đó xấp xỉ 10 giây trong điều kiện ổn định. Công thức không được dùng máy móc khi hàng đợi đang tăng liên tục hoặc hệ thống đang retry storm.

**SLO thực tế cần xem p95/p99 và oldest age**, không chỉ trung bình. Một hàng đợi được ưu tiên theo key hoặc có poison message có thể khiến một nhóm event chờ rất lâu dù throughput trung bình trông tốt.

## 12. Bảng hành động: an toàn trước, tốc độ sau

| Thao tác | Queue full | Executor reject | Error spike | Điều kiện trước khi làm |
|---|---|---|---|---|
| Rate-limit ingress | Hữu ích | Hữu ích | Hữu ích nếu do load/retry | Có đường phản hồi/backpressure/NACK đúng |
| Pause adapter | Có thể cần | Có thể cần | Có thể cần khi downstream outage | Biết ACK/offset, lịch poll và in-flight state |
| Tăng consumer concurrency | Có thể | Có thể | Có thể **làm tệ hơn** | DB/broker có headroom, ordering/key an toàn |
| Tăng bounded capacity | Chỉ giảm áp lực ngắn hạn | Chỉ kéo dài thời gian nhận task | Thường không giải quyết gốc | Heap/storage đủ, có kế hoạch drain |
| Đổi <code>CallerRunsPolicy</code> | Không trực tiếp | Có thể throttling | Có thể đổi nguồn lỗi | Đã đánh giá transaction/thread semantics |
| Tạm giảm retries | Giảm áp lực | Giảm task | Có ích với retry storm | Message có persistent recovery/DLQ |
| Khôi phục poller bị stop | Giúp drain | Không trực tiếp | Giúp nếu nguồn lỗi là missing consumer | Stop không có chủ đích, hạ tầng đã sẵn sàng |
| Quarantine poison event | Có thể giảm backlog | Có thể giảm task lỗi | Rất hữu ích | Có audit, replay policy, không bỏ message |
| Restart app | Có nguy cơ mất queue in-memory | Có thể giải phóng task kẹt nhưng mất in-flight | Không tự sửa dependency | Đã hiểu persistence, redelivery, idempotency |
| Xóa message/queue | Không khuyến nghị | Không giải quyết gốc | Không khuyến nghị | Chỉ theo chính sách xóa dữ liệu đã phê duyệt |

**Mỗi thay đổi phải có điều kiện rollback rõ:** nếu giảm concurrency làm age tăng nhanh, điều chỉnh lại; nếu tăng pool làm DB 429/timeout nhiều hơn, quay về cấu hình trước và giới hạn ingress. Không thay đồng thời capacity, max threads và retry policy nếu không thể xác định thay đổi nào có tác dụng.

## 13. Transaction, ACK, retry và message store: điều không được bỏ qua

### 13.1. Gửi thành công có nghĩa gì?

~~~text
Channel.send() accepted
    ≠ MessageHandler completed
    ≠ JDBC transaction committed
    ≠ Broker message ACKed
    ≠ Outbound side effect done exactly once
~~~

Với <code>QueueChannel</code>, accepted thường có nghĩa message đã vào buffer. Với <code>ExecutorChannel</code>, accepted có thể chỉ có nghĩa executor đã nhận task. Khi handler chạy ở thread khác, JDBC transaction thread-bound của sender **không tự chuyển** sang handler. Vì vậy logic “send true → ACK upstream” chỉ an toàn khi kiến trúc có hợp đồng lưu bền vững/khôi phục phù hợp.

### 13.2. Retry phải đặt ở đúng boundary

| Retry ở đâu? | Lỗi nào được retry? | Rủi ro |
|---|---|---|
| Sender/adapter bên ngoài channel | Enqueue fail, no-subscriber, executor reject | Phải tránh submit trùng nếu trạng thái nhận không chắc chắn |
| <code>RequestHandlerRetryAdvice</code> quanh handler | Lỗi invocation của handler đã được gọi | Không bắt được reject xảy ra **trước khi handler chạy** |
| Poller advice / transaction rollback | Receive/handle theo phạm vi poller | Source có thể redeliver khác nhau; cần xác minh store |
| Broker retry/redelivery | Message chưa ACK/đã NACK theo policy | Có thể xử lý lại cùng business event nhiều lần |
| Reactor <code>retryWhen</code> | Resubscribe publisher upstream | Có thể lặp side effect đã phát một phần |

Không bật retry vô hạn cho lỗi validation/schema cố định. Với transient outage, dùng số lần thử có hạn, exponential backoff, jitter và recovery channel bền vững khi cần. Nếu transaction đã đánh dấu rollback-only, retry bên trong cùng transaction có thể không cứu được commit.

### 13.3. In-memory và persistent queue khác nhau khi restart

- <code>new QueueChannel(capacity)</code> dùng buffer in-memory theo mặc định; restart/crash có thể làm mất message vẫn nằm trong queue.
- <code>QueueChannel</code> có thể được cấp persistent <code>MessageGroupStore</code>; <code>JdbcChannelMessageStore</code> thường được dùng cho kênh queue lưu bền vững. Thực tế commit/receive/rollback phụ thuộc store và transaction.
- Một message đã rời queue nhưng đang xử lý trong worker **không tự quay lại** chỉ vì executor bị shutdown; phải kiểm tra source transaction, ACK và recovery.
- Delayer, aggregator/resequencer và outbox có thể giữ dữ liệu ở những store **khác**; không xóa tất cả row của tenant/queue bằng một lệnh SQL tùy tiện.
- Broker redelivery sau restart có thể tạo trùng side effect; unique constraint hoặc idempotency key nghiệp vụ là lớp bảo vệ quan trọng.

**Trước khi restart trong sự cố queue full**, hỏi: *Dữ liệu chưa commit đang ở đâu? Node có thể tự khôi phục gì? Broker đã ACK chưa? Có thể drain hoặc chuyển quarantine trước restart không?*

## 14. Lifecycle, shutdown và dynamic flow trong ca trực

Khi một endpoint đang <code>stop()</code> hoặc dynamic <code>IntegrationFlow</code> đang bị remove, producer có thể gửi tới channel không còn subscriber. Khi executor shutdown, task mới có thể bị reject dù queue vừa được drain. Hãy kiểm tra:

1. Bean endpoint có còn trong context không? <code>SmartLifecycle.isRunning()</code> là gì?
2. Poller/adaptor đang có <code>autoStartup=false</code> vì bảo trì hoặc tenant DELETING không?
3. <code>IntegrationFlowContext.getRegistrationById(flowId)</code> còn trả registration không?
4. Có lệnh stop/remove đang chạy, deployment rolling hoặc resource lease bị thu hồi không?
5. In-flight task đã hoàn tất/được chuyển recovery chưa?

**Không tự start lại** flow của tenant bị xóa chỉ vì subscriber count về 0. Quy trình cleanup đúng là chặn nhận mới, xử lý pending, stop/destroy registration và đóng resource **thuộc riêng tenant**. Việc bật lại không kiểm chứng có thể tạo duplicate hoặc xử lý bằng credentials đã thu hồi.

Nếu đang rolling deploy, cần quiesce ở ingress trước, drain hoặc xác nhận durable replay, sau đó mới stop consumer/executor theo thứ tự. Không scale-to-zero toàn bộ replica cùng lúc khi còn in-memory queue chưa được bảo toàn.

## 15. Dashboard và alert cần có trước incident

Runbook khó thực hiện nếu chỉ có một alert tên “Integration Errors”. Một bộ dashboard khả thi:

| Nhóm | Metric hoặc phép đo cần có | Mục đích |
|---|---|---|
| Ingress | Logical event received/s, request throttled/s | Biết tốc độ nguồn và áp lực còn lại |
| Queue | Current depth, capacity, utilization, oldest age, send timeout/s | Phát hiện đầy trước khi request timeout |
| Poller | <code>isRunning</code>, poll cycles/s, receive count, receive error, maxMessagesPerPoll | Phân biệt consumer stop với slow handler |
| Executor | Active, pool size, max, queue length/capacity, reject/s, completed/s | Phát hiện saturation và shutdown |
| Handler | Success/s, error/s, p50/p95/p99 duration, attempt count | Đo throughput hoàn tất và latency |
| Error flow | <code>ErrorMessage</code>/s theo loại **low-cardinality**, DLQ depth, recovery rate | Nhận diện spike và trạng thái recovery |
| Dependencies | DB pool active/wait, SQL latency, HTTP 429/5xx, broker lag | Tìm nguyên nhân gốc |
| Data safety | Duplicate business ID, uncommitted/requeued count, outbox pending | Đối soát mất/trùng message |

Spring Integration có metric channel/handler qua Micrometer/Observation khi được bật. Tên meter thực tùy phiên bản và loại instrumentation; một số queue có gauge như <code>spring.integration.channel.queue.size</code>, còn executor thường cần Micrometer binder/Spring Boot Actuator hoặc custom instrumentation. **Không đoán rằng mọi số liệu trong bảng sẽ tự xuất hiện** khi chỉ thêm dependency Actuator.

### Alert hữu ích hơn một ngưỡng tĩnh

Ví dụ **các điều kiện minh họa**, không phải giá trị mặc định nên áp dụng:

- Queue utilization tăng liên tục *và* ước lượng <code>time_to_full</code> nhỏ hơn ngân sách phản ứng on-call.
- Oldest-message age vượt SLO, dù queue depth chưa lớn.
- Executor reject rate lớn hơn 0 trong nhiều cửa sổ liên tiếp khi hệ thống **không** ở giai đoạn stop có chủ đích.
- Error ratio tăng so với baseline *và* completed throughput giảm.
- DLQ grow trong khi replay/consumer capacity thấp.
- Poller không running khi được kỳ vọng ACTIVE và queue còn message.

Nên đặt alert theo **business outcome và tính toàn vẹn**, không chỉ theo volume. Ví dụ 10.000 lỗi lặp từ một poison message khác tác động của 10.000 business event riêng biệt thất bại.

## 16. Kiểm thử tái hiện queue full và executor reject

Runbook phải có các bài test chứng minh **ngưỡng bị từ chối, đường exception và khả năng phục hồi**. Test dùng <code>Thread.sleep()</code> để “tạo áp lực ngẫu nhiên” rất dễ flaky; nên điều khiển thời điểm bằng latch và timeout hữu hạn.

### 16.1. QueueChannel bounded từ chối message đúng lúc đầy

~~~java
@Test
void boundedQueueRejectsSecondMessageWithoutWaiting() {
    QueueChannel backlog = new QueueChannel(1);
    Message<String> first = MessageBuilder.withPayload("A").build();
    Message<String> second = MessageBuilder.withPayload("B").build();

    assertTrue(backlog.send(first, 0));
    assertEquals(1, backlog.getQueueSize());
    assertFalse(backlog.send(second, 0));

    assertEquals("A", backlog.receive(0).getPayload());
    assertEquals(0, backlog.getQueueSize());
    assertTrue(backlog.send(second, 0));
    assertEquals("B", backlog.receive(0).getPayload());
}
~~~

Test này chứng minh capacity và khả năng enqueue lại **trong một JVM**. Nó không chứng minh transaction rollback, broker redelivery hay message persistence sau restart. Với queue backed by store, tạo integration test dùng database thực và cùng transaction manager.

### 16.2. ExecutorChannel reject khi một task chạy và queue đã đầy

~~~java
@Test
void executorRejectsWhenWorkerAndTaskQueueAreFull() throws Exception {
    ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
    pool.setCorePoolSize(1);
    pool.setMaxPoolSize(1);
    pool.setQueueCapacity(1);
    pool.setRejectedExecutionHandler(new ThreadPoolExecutor.AbortPolicy());
    pool.initialize(); // Unit test tự tạo pool, không có Spring container.

    CountDownLatch entered = new CountDownLatch(1);
    CountDownLatch release = new CountDownLatch(1);

    try {
        ExecutorChannel channel = new ExecutorChannel(pool);
        channel.subscribe(message -> {
            entered.countDown();
            try {
                if (!release.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Test latch timed out");
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(ex);
            }
        });

        assertTrue(channel.send(
            MessageBuilder.withPayload("first").build()));
        assertTrue(entered.await(2, TimeUnit.SECONDS));
        assertTrue(channel.send(
            MessageBuilder.withPayload("queued").build()));

        assertEquals(1, pool.getThreadPoolExecutor().getQueue().size());
        assertThrows(RuntimeException.class, () -> channel.send(
            MessageBuilder.withPayload("rejected").build()));
    } finally {
        release.countDown();
        pool.shutdown();
    }
}
~~~

Các kiểu chính: <code>ThreadPoolTaskExecutor</code>, <code>ExecutorChannel</code>, <code>CountDownLatch</code>, <code>TimeUnit</code>, <code>ThreadPoolExecutor</code>, <code>MessageBuilder</code> và assertions JUnit Jupiter.

Test chỉ assert <code>RuntimeException</code> để không khóa vào wrapper messaging ở một phiên bản cụ thể. Trong suite thật, nên unwrap cause và xác nhận một <code>TaskRejectedException</code>/<code>RejectedExecutionException</code> đúng với executor đã chọn; đồng thời xác nhận task bị reject **không tạo side effect**.

Nếu test dùng <code>CallerRunsPolicy</code>, kết quả không còn là reject: thread test có thể tự thực thi handler và **bị chặn trên latch**. Phải viết một test riêng cho policy đó, không tái sử dụng kỳ vọng của <code>AbortPolicy</code>.

### 16.3. Lỗi DirectChannel không mặc nhiên tới errorChannel

~~~java
@Test
void directChannelFailureIsVisibleToCaller() {
    DirectChannel input = new DirectChannel();
    AtomicInteger attempts = new AtomicInteger();
    input.subscribe(message -> {
        attempts.incrementAndGet();
        throw new IllegalStateException("dependency unavailable");
    });

    Message<String> request =
        MessageBuilder.withPayload("event-42").build();

    assertThrows(MessagingException.class, () -> input.send(request));
    assertEquals(1, attempts.get()); // Không có retry advice ở test này.
}
~~~

Test này kiểm tra exception đồng bộ. Nó **không có** asynchronous error publisher nên không thể dùng để chứng minh global error channel đã nhận lỗi. Nếu production chạy với executor hoặc poller, phải test đúng topology ấy và đọc error sink được cấu hình.

### 16.4. Kịch bản error spike với poller và recovery

Thiết kế integration test có một <code>QueueChannel</code> input, polling consumer, handler thất bại có kiểm soát và <code>QueueChannel</code> hoặc in-memory sink dành riêng cho error:

1. Gửi cùng một business event ID đã định danh vào nguồn test.
2. Cấu hình handler ném lỗi transient trong N attempt đầu, sau đó thành công; đặt retry policy **hữu hạn**.
3. Assert số attempt, số <code>ErrorMessage</code> theo policy, failed message/correlation và kết quả cuối.
4. Cố tình để handler luôn lỗi, xác minh recoverer gửi đúng DLQ/quarantine hoặc exception rollback để nguồn có thể redeliver.
5. Dừng poller giữa chừng và khởi động lại; kiểm tra in-flight message/transaction/replay theo loại store.
6. Lặp lại với lỗi validation không retry để chứng minh poison event không tạo retry storm.

Sử dụng <code>@SpringIntegrationTest</code>, <code>MockIntegrationContext</code>, latch/Awaitility hoặc các mechanism chờ theo điều kiện có timeout. Không dùng <code>Thread.sleep()</code> kéo dài để giả lập outage nếu có thể điều khiển fake downstream bằng latch, future hoặc stub có deadline.

## 17. Kiểm thử Game Day trước khi cần runbook thật

Một hệ thống chỉ được coi là có runbook khi **đã thử** nó trong staging hoặc môi trường mô phỏng tương ứng.

| Bài diễn tập | Cách gây sự cố có kiểm soát | Thành công khi |
|---|---|---|
| Queue đầy | Bounded queue nhỏ, pause poller, tăng producer test | Alert đúng, sender timeout có kiểm soát, không ACK sai |
| Executor reject | Core/max/queue nhỏ, giữ worker bằng latch | Reject được phân loại, ingress throttled, không rơi mất event |
| DB/HTTP outage | Fake dependency timeout hoặc 503 | Retry có ngân sách, không tạo retry storm, error flow nhận đúng |
| Poison message | Payload không thể deserialize hoặc validation sai | Được quarantine/DLQ, không chặn mãi toàn partition |
| Poller stop | Stop đúng consumer endpoint | Queue lag tăng có quan sát, restart an toàn |
| Shutdown giữa backlog | Dừng process với queue in-memory/persistent theo từng kịch bản | Hiểu rõ điều gì mất/được replay và không double side effect |
| Rolling deploy | Restart từng replica khi có in-flight task | Không no-subscriber ngoài chủ đích, không ACK sai |
| Hot correlation key | Nhiều message chung một key/lock | Phát hiện contention, không phá thứ tự hoặc group |
| Error sink mất subscriber | Tắt observer/error consumer theo kịch bản | Lỗi thứ cấp được phát hiện; exception gốc không mất dấu |

**Giữ bằng chứng:** input IDs, event ID, số attempt, kết quả ACK, DB state, metric trước/sau và thời gian khôi phục. Không diễn tập bằng cách phát message thật tới khách hàng hoặc ép dữ liệu production lỗi mà chưa có cơ chế cô lập/ủy quyền tương ứng.

## 18. Quy trình on-call theo mốc hoạt động

Không nên coi các mốc dưới đây là SLA cố định; chúng là **thứ tự ưu tiên** có thể áp dụng ngay.

### Giai đoạn phát hiện và bảo toàn (T0)

1. Acknowledge alert, tạo incident record, ghi bản deploy và phạm vi ảnh hưởng.
2. Xác định lỗi nào xuất hiện trước: queue full, executor rejected hay dependency/handler error.
3. Xác nhận message đang ở in-memory queue, durable store, broker hay chỉ trong executor task queue.
4. Thu thập vài trace/stack trace có correlation, snapshot thread/pool/queue, không dump payload bí mật.
5. Quyết định giảm ingress nếu nguy cơ mất message hoặc request đã vượt SLO.

### Giai đoạn giảm tác động

1. Chỉ định người chịu trách nhiệm cho ingress throttle, dependency, app flow và data reconciliation.
2. Áp dụng **một** biện pháp ít rủi ro nhất: pause/throttle producer hoặc cô lập poison event, tùy bằng chứng.
3. Chặn retry storm bằng backoff và giới hạn attempt; kiểm tra DLQ/quarantine hoạt động.
4. Khôi phục handler/poller/dependency sau khi xác minh transaction/ownership.
5. Theo dõi completed throughput, queue age, reject rate, error rate trong nhiều cửa sổ liên tiếp.

### Giai đoạn khôi phục và đối soát

1. Mở ingress từng bước theo headroom đo được.
2. Tính lại thời gian drain theo throughput thực, không chỉ theo giới hạn cấu hình.
3. Đối soát ACK/offset, DB rows, outbox/inbox và số business event ID unique.
4. Kiểm tra các message đến muộn, retry lại, partial group và lỗi lịch Delayer/aggregator nếu flow có chúng.
5. Chỉ đóng incident khi SLO ổn định, backlog không còn tăng, không có nguy cơ mất/trùng chưa được giải quyết và recovery data có owner.

### Mẫu bằng chứng bàn giao ca trực

~~~text
INCIDENT_ID:
STARTED_AT / CURRENT_TIME:
DEPLOY_VERSION / PODS / TENANTS_AFFECTED:
PRIMARY_SYMPTOM: QUEUE_FULL | EXECUTOR_REJECT | ERROR_SPIKE
ROOT_CAUSE_CATEGORY:
CHANNEL_BEAN / ENDPOINT_ID / EXECUTOR_BEAN:
INGRESS_RATE / COMPLETED_RATE:
QUEUE_SIZE / CAPACITY / OLDEST_AGE:
EXECUTOR_ACTIVE / MAX / QUEUED / REJECTS:
ERROR_ATTEMPTS / UNIQUE_BUSINESS_EVENTS / DLQ_DEPTH:
ACK_AND_TRANSACTION_BEHAVIOR_VERIFIED:
MITIGATION_APPLIED / ROLLBACK_PLAN:
REPLAY_OR_RECONCILIATION_OWNER:
RECOVERY_CRITERIA:
NEXT_CHECK:
~~~

Mẫu này cố ý chỉ yêu cầu **dữ liệu vận hành cần thiết**, không đề nghị dán toàn bộ payload/message headers hoặc thông tin truy cập bí mật vào ticket.

## 19. Các anti-pattern phải tránh

| Anti-pattern | Vì sao nguy hiểm | Hướng thay thế |
|---|---|---|
| Tăng queue capacity vô hạn | Heap/storage đầy muộn hơn nhưng nút cổ chai còn nguyên | Bounded queue, admission control, drain plan |
| Tăng executor maxPoolSize mà không xem queueCapacity | Với queue lớn/chưa đầy, pool có thể không tăng vượt core | Quan sát chính sách ThreadPoolExecutor và bottleneck downstream |
| Chuyển sang <code>DiscardPolicy</code> để giảm reject | Message có thể bị bỏ im lặng | Explicit failure, durable retry/DLQ, throttling |
| Bật <code>CallerRunsPolicy</code> mà không test | Sender bị block, transaction/thread semantics đổi | Test overload và documented tradeoff |
| Retry liên tục khi downstream 503 | Khuếch đại outage, queue càng đầy | Exponential backoff, jitter, circuit breaker |
| Xóa queue hoặc reset offset tùy tiện | Có thể mất message hoặc tạo duplicate | Reconcile + policy replay/idempotency |
| Stop tất cả consumer ngay khi queue đầy | Backlog không thể drain | Giảm nguồn, để consumer khỏe tiếp tục hoàn tất |
| Restart toàn bộ pod với in-memory queue | Chưa lưu message có thể mất | Drain, durable handoff hoặc xác nhận source redelivery |
| Nuốt exception ở error flow để giảm log | Upstream có thể coi xử lý thành công | Structured error routing và recovery xác định |
| Gắn message ID/order ID vào metric tag | Cardinality và chi phí collector tăng mạnh | Low-cardinality error category, correlation ở trace/log |
| Chỉ theo dõi <code>send()</code> success | Không thấy handler fail sau async handoff | Completion/ACK/commit telemetry |

## 20. Checklist production: kết thúc sự cố và ngăn tái diễn

- [ ] Có sơ đồ channel → poller/consumer → executor → handler → outbound/error flow theo bean ID ổn định.
- [ ] Queue có capacity rõ và sender có timeout/failure policy; không block vô hạn nếu không được thiết kế chủ ý.
- [ ] Dashboard có queue depth **và oldest age**, completed throughput, executor saturation/reject và error ratio.
- [ ] Đã xác định <code>PollingConsumer</code> hay <code>SourcePollingChannelAdapter</code>, <code>maxMessagesPerPoll</code>, trigger và receive timeout.
- [ ] Executor bounded có core/max/queue/rejection policy phù hợp, thread pool không vượt giới hạn DB/HTTP downstream.
- [ ] Phân biệt lỗi sender với lỗi worker/poller; <code>errorChannel</code> và recoverer có chủ sở hữu.
- [ ] Mỗi retry có giới hạn, backoff/jitter và đường dừng cho poison event.
- [ ] ACK/commit/redelivery được kiểm thử đúng adapter và transaction manager, không suy từ <code>send() == true</code>.
- [ ] Business event có idempotency key; DLQ/quarantine và replay có quy trình đối soát.
- [ ] Biết chính xác trạng thái message khi stop/restart và khác biệt giữa in-memory/persistent queue.
- [ ] Dynamic flow lifecycle/tenant deletion có admission gate và không khởi động lại ngoài chủ đích.
- [ ] Có game-day test cho queue full, executor reject, error spike, shutdown và retry amplification.
- [ ] Hậu điều kiện đóng incident gồm throughput ổn, backlog drain, error/reject giảm, SLO hồi phục và không còn dữ liệu cần đối soát vô chủ.

**Kết luận:** Trong Spring Integration, **queue đầy** là tín hiệu backpressure ở nơi chứa message, **executor reject** là thất bại tiếp nhận task của worker pool, còn **error spike** phản ánh các exception/attempt tại những ranh giới lỗi khác nhau. Một runbook hữu ích không chỉ “giảm cảnh báo” mà phải xác định điểm nghẽn đầu tiên, giữ đúng ACK/transaction/idempotency, giảm tải có kiểm soát, khôi phục consumer và đối soát dữ liệu. Vận hành an toàn dựa trên **bằng chứng về message completion**, không dựa vào số lần gửi hoặc số dòng log.

## Tài liệu tham khảo

- [Spring Integration Reference — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Integration Reference — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html)
- [Spring Integration Reference — Message Endpoints và Poller](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Spring Integration Reference — Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html)
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Spring Integration 6.5 Javadoc — Pollers](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/Pollers.html)
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Integration Reference — Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html)
