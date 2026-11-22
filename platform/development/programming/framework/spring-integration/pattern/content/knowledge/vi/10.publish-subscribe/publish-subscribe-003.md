# Subscriber độc lập và lỗi riêng từng nhánh

## 1. Bài toán: một sự kiện, nhiều bên quan tâm

Trong một hệ thống xử lý đơn hàng, khi `OrderCreated` xuất hiện, có thể có nhiều thành phần cùng cần biết:

- **Audit subscriber** ghi dấu sự kiện theo yêu cầu kiểm soát.
- **Notification subscriber** gửi thông báo cho người dùng.
- **Analytics subscriber** cập nhật số liệu vận hành.

Ba trách nhiệm này khác nhau. Notification bị lỗi SMTP không nên tự động khiến analytics không thể ghi nhận sự kiện; analytics chậm cũng không nhất thiết được phép làm API tạo đơn chậm theo. Đây là động cơ sử dụng mẫu **Publish–Subscribe** (*pub/sub*) trong Enterprise Integration Patterns.

~~~mermaid
flowchart LR
    G[Order Service] --> C[(orders.events)]
    C -->|fan-out| A[Audit subscriber]
    C -->|fan-out| N[Notification subscriber]
    C -->|fan-out| M[Analytics subscriber]
    A --> DA[(Audit store)]
    N --> E[Email provider]
    M --> T[(Metrics / Warehouse)]
~~~

Trong Spring Integration, `PublishSubscribeChannel` là một `SubscribableChannel` phát message cho các subscriber đang đăng ký. Việc tách endpoint giúp từng nhánh có **chủ sở hữu và logic nghiệp vụ riêng**. Tuy nhiên, **độc lập về trách nhiệm không đồng nghĩa tự động cách ly lỗi, độ trễ hay tài nguyên**:

1. Nếu channel chạy **đồng bộ**, một subscriber chậm có thể giữ thread của publisher; exception của một subscriber có thể ảnh hưởng dispatch đến các subscriber khác tùy cấu hình.
2. Nếu channel chạy **bất đồng bộ** với executor, publisher có thể thoát sớm, nhưng các subscriber có thể cùng tranh thread pool và lỗi của subscriber cần được xử lý ngoài call stack ban đầu.
3. Nếu cần khả năng tồn tại qua restart và retry riêng, chỉ một pub/sub channel trong bộ nhớ **không đủ**; có thể phải kết hợp queue/broker bền vững, idempotency và cơ chế recovery.

Bài học thuộc chương **Publish subscribe** của module `SPRING_INTEGRATION_PATTERN`. Mục tiêu của module là dùng Spring Integration để triển khai các Enterprise Integration Patterns như Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, tạo flow ít phụ thuộc, dễ mở rộng và có khả năng theo dõi từng nhánh.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích thế nào là một subscriber độc lập và những gì pub/sub **không bảo đảm**.
2. Phân biệt dispatch đồng bộ, dispatch bằng executor và phân phối qua broker.
3. Cấu hình hai hoặc nhiều subscriber bằng Spring Integration Java DSL.
4. Thiết kế chính sách lỗi theo **từng recipient/subscriber** thay vì retry toàn fan-out một cách mù quáng.
5. Xử lý subscriber chậm, bão hòa executor, retry, error channel, duplicate và khôi phục.
6. Kiểm thử tình huống một nhánh thất bại nhưng các nhánh khác vẫn hoạt động và truy nguyên được trạng thái từng nhánh.

## 2. Publish–Subscribe là gì và khác Recipient List như thế nào?

### 2.1. Một channel, nhiều consumer

`PublishSubscribeChannel` là một địa chỉ logic để các endpoint đăng ký nhận sự kiện. Publisher không cần biết có bao nhiêu subscriber, subscriber nào đang chạy và mỗi subscriber thực hiện công việc gì. Khi message được gửi, channel thực hiện broadcast theo các subscriber hiện có và chính sách dispatch tương ứng.

~~~text
                 Publisher
                     |
                     v
          PublishSubscribeChannel
            /       |       \
           v        v        v
         Audit   Notification Analytics
~~~

Trong cách dùng này, publisher chỉ phụ thuộc vào **hợp đồng event và channel**. Việc thêm Analytics subscriber không buộc Order Service gọi trực tiếp một Analytics Service mới.

### 2.2. So sánh với các mẫu liên quan

| Mẫu / thành phần | Điểm quyết định | Mục đích |
|---|---|---|
| **Publish–Subscribe Channel** | Subscriber đăng ký với một channel; message được phát theo cơ chế broadcast. | Nhiều bên cùng quan tâm đến một sự kiện. |
| **Recipient List Router** | Router chọn danh sách channel đích; có thể dựa trên điều kiện. | Chọn **những recipient cụ thể** cần nhận một message. |
| **Content-Based Router** | Router tính key để chọn một hoặc nhiều output theo chính sách. | Phân luồng xử lý tùy nội dung. |
| **DirectChannel** | Dispatch điểm-điểm qua subscriber/handler theo semantics kênh. | Xử lý đồng bộ thông thường, không phải broadcast tới tất cả. |
| **Splitter / Aggregator** | Chia thành các phần hoặc gom kết quả tương quan. | Xử lý nhiều phần của cùng một công việc. |
| **Scatter–Gather** | Phân phối yêu cầu rồi thu thập phản hồi. | Đưa ra kết luận phụ thuộc nhiều kết quả. |

**Một channel pub/sub không phải Aggregator.** Nếu Gateway muốn nhận một kết quả tổng hợp từ ba subscriber, việc broadcast không tự gom ba reply. Hãy dùng Scatter–Gather hoặc thiết kế correlation, group store, release strategy và timeout của Aggregator phù hợp.

### 2.3. “Subscriber độc lập” có ba cấp độ

| Cấp độ | Ý nghĩa | Pub/sub có tự bảo đảm không? |
|---|---|---|
| **Độc lập logic** | Mỗi subscriber chứa logic và quy tắc riêng, ít biết về subscriber khác. | Có thể đạt được nhờ thiết kế, nhưng handler vẫn có thể chia sẻ state không an toàn. |
| **Độc lập thực thi** | Subscriber chậm/lỗi không chặn thời gian thực thi của subscriber khác. | **Không mặc định**, nhất là dispatch đồng bộ hoặc executor dùng chung. |
| **Độc lập khôi phục** | Mỗi nhánh retry, lưu backlog, chết/khởi động lại và phục hồi riêng. | **Không mặc định**; cần hạ tầng lưu trữ, xử lý lỗi và idempotency riêng. |

Thiết kế tốt không chỉ tách class thành `AuditHandler`, `EmailHandler`, `MetricsHandler`, mà còn xác định **failure policy** và **delivery guarantee** ở từng nhánh.

## 3. Hành vi của PublishSubscribeChannel khi đồng bộ

### 3.1. Mặc định không có executor

Một `PublishSubscribeChannel` được tạo mà **không truyền `TaskExecutor`** dùng kiểu dispatch đồng bộ. Trong trường hợp bình thường, việc gửi một message và gọi các subscriber diễn ra trong quá trình thực thi của thread gửi. Do đó:

- Handler chậm có thể làm `send(...)` chậm.
- Handler ném exception có thể khiến `send(...)` không kết thúc như trường hợp thành công.
- Không nên suy luận rằng **tất cả** subscriber đã được gọi khi một subscriber thất bại và cơ chế dispatch cấu hình dừng khi gặp lỗi.
- Không dựa vào thứ tự subscriber để thực hiện chuỗi nghiệp vụ có thứ tự; thứ tự đăng ký hoặc dispatcher policy không thay thế một flow nối tiếp rõ ràng.

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant C as PublishSubscribeChannel
    participant A as Audit
    participant N as Notification
    participant M as Analytics
    P->>C: send(OrderCreated)
    C->>A: dispatch
    A-->>C: return
    C->>N: dispatch
    N--xC: exception
    Note over C,M: Một dispatcher fail-fast có thể không tới nhánh còn lại
    C--xP: send thất bại / exception
~~~

Sơ đồ minh họa **một cấu hình đồng bộ không bỏ qua lỗi**. Không được hiểu là thứ tự Audit → Notification → Analytics luôn cố định hoặc mọi cấu hình Spring Integration đều phát lỗi theo đúng thứ tự này.

### 3.2. `ignoreFailures` có nghĩa gì?

`PublishSubscribeChannel` hỗ trợ cấu hình để **bỏ qua lỗi dispatch ở một subscriber và tiếp tục với các subscriber khác** trong mô hình đồng bộ; thường thao tác qua `setIgnoreFailures(true)`. Khi lựa chọn này được áp dụng:

- Một subscriber ném exception không nhất thiết làm ngừng việc thử dispatch tới subscriber tiếp theo.
- Điều đó **không làm subscriber bị lỗi thành công**, không tự retry và không tự có một bản ghi sự cố bền vững.
- Với use case nhạy cảm, cần **ghi log, metric và recovery** riêng để không che mất lỗi.
- Không được dựa vào giá trị trả về của `send(...)` để tuyên bố tất cả subscriber đã commit thành công.

Sự khác biệt cần nhớ:

| Cách xử lý | Hệ quả mong muốn | Rủi ro |
|---|---|---|
| Không bỏ qua lỗi (fail-fast) | Báo failure lên sender; có thể ngừng dispatch các subscriber tiếp theo. | Một nhánh phụ chặn các nhánh quan trọng; partial side effect đã xảy ra. |
| Bỏ qua failure tại dispatcher | Tiếp tục thử gửi tới các subscriber khác. | Lỗi bị che nếu không có quan sát và cơ chế phục hồi riêng. |
| Bắt lỗi trong **subscriber boundary** | Ghi failure/outcome riêng, quyết định retry/recovery tại nhánh. | Nếu bắt và nuốt lỗi mà không lưu, vẫn mất tín hiệu khôi phục. |

**Không có một cấu hình chung đúng cho mọi luồng.** Audit phải thành công trước khi xác nhận giao dịch có thể cần fail closed hoặc một bước bền vững trước fan-out; email không quan trọng có thể xử lý async với retry riêng. Lựa chọn phải xuất phát từ hợp đồng nghiệp vụ, không phải chỉ để `send(...)` luôn thành công.

### 3.3. Một subscriber chậm có thể ảnh hưởng toàn channel

Giả sử Audit xử lý 20 ms, Email mất 2 giây vì SMTP timeout, Analytics xử lý 15 ms. Trong mô hình đồng bộ, publisher có thể bị giữ khoảng **tổng** thời gian xử lý các handler đang được gọi, không chỉ thời gian của handler nhanh nhất. Điều này có thể làm:

- HTTP inbound Gateway bị chậm hoặc timeout.
- Thread/connection của producer bị chiếm.
- Tăng queue ở upstream.
- Ảnh hưởng cả những subscriber **không có lỗi**.

Nếu không thể chấp nhận phụ thuộc vào thời gian thực thi của email, cần tách thực thi bằng executor, queue hoặc broker phù hợp. Nhưng tách thread **không tự bảo đảm durability**.

## 4. Java DSL: nhiều subscriber có lỗi được cô lập rõ ràng

### 4.1. Hợp đồng ví dụ

Ta triển khai flow đơn giản:

1. Producer gửi một event `OrderCreated(eventId, orderId)` tới `orders.events`.
2. `PublishSubscribeChannel` dispatch đồng bộ đến Audit, Notification và Analytics.
3. Notification được mô phỏng có thể ném lỗi.
4. **Ranh giới của Notification subscriber bắt lỗi, ghi failure có định danh và không ném tiếp**, để các subscriber khác tiếp tục theo chính sách ví dụ.
5. Không có bước gom reply: đây là **one-way event fan-out**, không phải request–reply chờ đủ ba kết quả.

~~~mermaid
flowchart LR
    P[Producer] --> C[(orders.events)]
    C --> A[Audit subscriber]
    C --> N[Notification subscriber]
    C --> M[Analytics subscriber]
    N -->|Thành công| NS[Delivery success]
    N -->|Lỗi| NE[Record failure + recovery]
    A --> AS[Audit processed]
    M --> MS[Analytics processed]
~~~

Ví dụ hướng tới Java 17+, Spring Boot 3.x và Spring Integration 6.x với dependency `spring-boot-starter-integration`. Để dễ đọc, các kiểu top-level có thể cùng package trong bài; trong dự án thật tách các kiểu cần `public` thành các file riêng. Những handler ví dụ chỉ tăng counter, chưa gửi email hoặc ghi DB thật.

### 4.2. Cấu hình Spring Integration

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

record OrderCreated(String eventId, String orderId) {}

final class BranchProbe {
    final AtomicInteger auditSuccess = new AtomicInteger();
    final AtomicInteger notificationSuccess = new AtomicInteger();
    final AtomicInteger notificationFailure = new AtomicInteger();
    final AtomicInteger analyticsSuccess = new AtomicInteger();
    final AtomicBoolean failNotification = new AtomicBoolean();

    void audit(OrderCreated event) {
        auditSuccess.incrementAndGet();
    }

    void notifyUser(OrderCreated event) {
        if (failNotification.get()) {
            throw new IllegalStateException("Simulated email failure");
        }
        notificationSuccess.incrementAndGet();
    }

    void analytics(OrderCreated event) {
        analyticsSuccess.incrementAndGet();
    }

    void recordNotificationFailure(
            OrderCreated event, RuntimeException cause) {
        // Demo: chỉ đếm failure. Production cần log và recovery
        // bền vững, có eventId để thực hiện retry/idempotency.
        notificationFailure.incrementAndGet();
    }
}

@Configuration
@EnableIntegration
class SubscriberIsolationConfiguration {

    @Bean(name = "orders.events")
    PublishSubscribeChannel eventsChannel() {
        // Không có TaskExecutor: dispatch đồng bộ.
        return new PublishSubscribeChannel();
    }

    @Bean
    BranchProbe branchProbe() {
        return new BranchProbe();
    }

    @Bean
    IntegrationFlow auditSubscriber(BranchProbe probe) {
        return IntegrationFlow.from("orders.events")
                .handle(OrderCreated.class, (event, headers) -> {
                    probe.audit(event);
                    return null; // One-way handler.
                })
                .get();
    }

    @Bean
    IntegrationFlow notificationSubscriber(BranchProbe probe) {
        return IntegrationFlow.from("orders.events")
                .handle(OrderCreated.class, (event, headers) -> {
                    try {
                        probe.notifyUser(event);
                    } catch (RuntimeException ex) {
                        probe.recordNotificationFailure(event, ex);
                        // Ví dụ: nhánh này tự chịu trách nhiệm
                        // ghi failure/recovery, không ném tiếp.
                    }
                    return null;
                })
                .get();
    }

    @Bean
    IntegrationFlow analyticsSubscriber(BranchProbe probe) {
        return IntegrationFlow.from("orders.events")
                .handle(OrderCreated.class, (event, headers) -> {
                    probe.analytics(event);
                    return null;
                })
                .get();
    }
}
~~~

**Tại sao cần đọc kỹ đoạn catch?**

- Notification failure được ghi tại **subscriber boundary**, nên thử gửi sự kiện tới Analytics/Audit không bị exception mô phỏng ở notification làm đứt đoạn.
- Nhưng `recordNotificationFailure` trong ví dụ chỉ tăng counter. **Nó không bảo đảm retry, durability hoặc alert.** Đây là nơi cần thay bằng cơ chế báo lỗi đáng tin cậy và hồi phục riêng khi đưa vào production.
- Các exception khác từ audit hoặc analytics **chưa được cô lập**. Nếu cần chính sách tương tự, phải xử lý ở ranh giới của các nhánh đó theo đúng mức quan trọng.
- Việc một subscriber gặp lỗi và **nuốt lỗi sau khi log** có thể làm sender nghĩ “mọi việc đã ổn”. Vì vậy API không được gán `send=true` với “email đã gửi”.

### 4.3. Producer publish sự kiện

~~~java
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.support.MessageBuilder;

boolean sent = eventsChannel.send(
        MessageBuilder.withPayload(
                new OrderCreated("EVT-1001", "ORD-1001"))
                .setHeader("traceId", "trace-order-1001")
                .build(), 1_000);

// Trong ví dụ đồng bộ, handler sẽ chạy theo dispatch.
// sent KHÔNG chứng minh mọi side effect đã ghi bền vững.
~~~

Publisher không cần gọi trực tiếp `BranchProbe.audit()` hoặc `notifyUser()`. Nó chỉ gửi đến một channel, còn các endpoint subscribe theo cấu hình. Đây là lợi ích chính của pub/sub trong việc giảm phụ thuộc giữa producer và các consumer.

### 4.4. Đánh đổi của xử lý lỗi trong subscriber

| Lựa chọn | Khi nào phù hợp | Phải bổ sung |
|---|---|---|
| Bắt lỗi và ghi recovery riêng | Nhánh phụ không được làm fail đường chính. | Durable failure record/queue, metric, retry, idempotency. |
| Ném lỗi để fail-fast | Một nhánh là điều kiện bắt buộc để request thành công. | Contract failure cho caller, quản lý side effect từng phần. |
| Dùng async channel/executor | Cần giảm phụ thuộc vào thời gian chạy handler. | Thread pool, queue bound, error handler và shutdown policy. |
| Dùng broker với consumer riêng | Cần tách tiến trình và phục hồi qua restart. | Delivery/ack, retention, DLQ, replay, idempotency. |

Đặc biệt, **không dùng exception của một email handler làm cơ chế rollback toàn bộ nghiệp vụ** nếu các nhánh audit/analytics đã tạo side effect. Pub/sub không tự tạo distributed transaction.

## 5. Chạy subscriber bất đồng bộ bằng TaskExecutor

### 5.1. Vì sao chuyển sang executor?

Với pub/sub đồng bộ, publisher có thể phải chờ subscriber chậm xử lý trong cùng luồng gọi. Nếu notification mất vài giây, API có thể bị ảnh hưởng dù chỉ cần công bố `OrderCreated`. Một lựa chọn là tạo `PublishSubscribeChannel` với `TaskExecutor` để channel **giao công việc dispatch cho executor**.

~~~mermaid
flowchart TD
    P[Publisher] --> C[(PublishSubscribeChannel)]
    C --> E[Shared TaskExecutor]
    E --> A[Audit task]
    E --> N[Notification task]
    E --> M[Analytics task]
    A --> SA[Audit complete]
    N --> SN[Email complete / failed]
    M --> SM[Analytics complete]
~~~

Khi executor nhận được task, publisher có thể hoàn tất thao tác gửi **trước khi handler thực hiện xong**. Đây là lợi ích về latency nhưng cũng thay đổi cách quan sát thành công/thất bại:

- `send(...)` thành công không chứng minh subscriber đã hoàn tất nghiệp vụ.
- Lỗi của handler ở thread executor không thể giả định được ném lại qua stack của thread publisher.
- Khi executor bão hòa, việc submit có thể thất bại, chặn hoặc chạy ở thread caller tùy loại executor và rejection policy.
- Nếu mọi subscriber dùng **chung một executor**, nhánh chậm vẫn có thể chiếm nhiều worker và làm nhánh khác chờ đợi.

### 5.2. Ví dụ cấu hình async

Đây là cấu hình **thay thế bean `orders.events` ở mục 4**, không được đăng ký đồng thời hai bean cùng tên trong một Spring context:

~~~java
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Bean
ThreadPoolTaskExecutor publicationExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(3);
    executor.setMaxPoolSize(6);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("order-event-");
    executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.AbortPolicy());
    executor.initialize();
    return executor;
}

@Bean(name = "orders.events")
PublishSubscribeChannel asyncEventsChannel(
        ThreadPoolTaskExecutor publicationExecutor) {
    return new PublishSubscribeChannel(publicationExecutor);
}
~~~

Chú ý hai lớp capacity khác nhau:

1. `PublishSubscribeChannel` không biến thành `QueueChannel` chỉ vì có executor.
2. `ThreadPoolTaskExecutor` có **task queue**, kích thước thread pool và rejection policy riêng.

Ví dụ `corePoolSize=3`, `maxPoolSize=6`, `queueCapacity=100` không đồng nghĩa luôn chạy ngay sáu task đồng thời rồi mới queue. Với executor dùng queue có dung lượng dương, việc tăng thread trên core thường xảy ra theo chiến lược của thread pool **sau khi task queue đã đầy**; cần load test theo workload thực tế.

### 5.3. Async không đủ để cách ly lỗi hoàn toàn

Một `PublishSubscribeChannel(executor)` duy nhất giúp tách thread nhưng vẫn có điểm chung:

- **Executor chung:** email handler có thể làm cạn thread khiến audit handler bị chậm.
- **Bộ nhớ chung:** queue task chứa trong process, bị mất khi JVM kết thúc đột ngột.
- **CPU/GC chung:** một subscriber xử lý payload lớn có thể ảnh hưởng mọi subscriber.
- **Hạ tầng chung:** DB pool hoặc HTTP client pool được chia sẻ có thể tạo nghẽn chéo.

Nếu yêu cầu mỗi subscriber **chịu lỗi độc lập mạnh**, có thể dùng kênh/broker riêng theo nhánh:

~~~mermaid
flowchart LR
    P[Publisher] --> C[(orders.events)]
    C --> A[(audit.queue / broker)]
    C --> N[(notification.queue / broker)]
    C --> M[(analytics.queue / broker)]
    A --> AW[Audit worker]
    N --> NW[Notification worker]
    M --> MW[Analytics worker]
~~~

Với cách này, mỗi worker có thể có concurrency, retry, timeout, message retention và dead-letter policy riêng. Tuy vậy **sơ đồ không tự bảo đảm** mỗi queue là durable: phải chọn transport/store và cấu hình acknowledgment, persistence, replication, retention, transaction phù hợp.

**Điểm thiết kế quan trọng:** Một shared publisher vẫn phải đưa message vào các đích. Nếu nó gửi thành công tới audit nhưng thất bại khi gửi tới notification, ta đã có **partial fan-out**. Muốn khôi phục, cần ghi **delivery status theo recipient** hoặc dựa trên hạ tầng pub/sub bền vững với delivery semantics đã xác minh.

## 6. Xử lý lỗi theo từng subscriber

### 6.1. Phân loại lỗi trước khi retry

Không phải “subscriber lỗi” chỉ có một nguyên nhân:

| Lỗi | Xuất hiện ở đâu? | Chính sách cần cân nhắc |
|---|---|---|
| **Routing/subscription failure** | Channel không có subscriber cần thiết hoặc subscriber stopped. | Xác minh cấu hình/lifecycle; không coi gửi thành công là đã xử lý. |
| **Dispatch rejection** | Executor/task queue bão hòa hoặc channel không tiếp nhận. | Bounded retry/backpressure, giảm tải, cảnh báo. |
| **Transient downstream failure** | SMTP/HTTP/DB timeout hoặc tạm mất kết nối. | Retry có giới hạn và backoff, idempotency. |
| **Permanent business failure** | Địa chỉ email không hợp lệ, payload không đạt schema. | Reject hoặc DLQ/manual repair; không retry vô hạn. |
| **Serialization/header failure** | Adapter không chuyển được message/header. | Sửa schema/mapper, quarantine và replay an toàn. |
| **Uncertain outcome** | Gọi API ngoài timeout sau khi đã có thể tạo side effect. | Dùng request ID/idempotency key, tra cứu trạng thái trước retry. |

Một lỗi nhất thời ở notification **không nhất thiết phải khiến audit thử lại**. Retry toàn bộ fan-out có thể khiến những nhánh đã thành công thực hiện lặp thao tác ngoài ý muốn.

### 6.2. Ranh giới chịu trách nhiệm xử lý lỗi

Một chiến lược phổ biến:

~~~text
Event Publisher
    |
    v
orders.events (publish/subscribe)
    |
    +--> Audit Subscriber
    |       -> attempt write
    |       -> audit-specific retry / recovery
    |
    +--> Notification Subscriber
    |       -> attempt email
    |       -> notify-specific retry / dead letter
    |
    +--> Analytics Subscriber
            -> attempt ingest
            -> analytics-specific retry / replay
~~~

Mỗi nhánh nên định nghĩa:

1. **Lỗi có thể retry:** mã lỗi hoặc exception loại nào.
2. **Số lần thử tối đa:** không retry không giới hạn.
3. **Backoff/jitter:** tránh bắn cùng lúc vào downstream đang lỗi.
4. **Deadline:** tổng thời gian được phép chờ.
5. **Idempotency key:** ngăn side effect trùng khi redelivery.
6. **Recovery destination:** DLQ/quarantine hoặc bản ghi thất bại bền vững.
7. **SLO/alert:** khi nào lỗi cần người vận hành can thiệp.

### 6.3. Phân biệt exception đồng bộ và `ErrorMessage`

Trong **đồng bộ**, exception có thể truyền về publisher nếu subscriber không tự bắt lỗi và dispatcher không cấu hình tiếp tục. Trong **bất đồng bộ**, exception xảy ra ở worker thread, nên phải kiểm tra cơ chế **`ErrorHandler`, `errorChannel`, `ErrorMessage`** và hạ tầng adapter cụ thể.

Các điểm cần nhớ:

- `errorChannel` không tự bảo đảm mọi exception ở mọi transport sẽ được chuyển vào đó.
- Một handler catch rồi không ném lại thì framework có thể coi nhánh đó là **đã kết thúc bình thường**; ứng dụng phải có bản ghi lỗi/recovery riêng.
- Một failure ở bước **đăng ký task** khác failure **trong handler đã bắt đầu chạy**. Hai lỗi này có thể không đi cùng đường error handling.
- `ErrorMessage` có payload là `Throwable`; với `MessagingException` có thể có `failedMessage`, nhưng không phải mọi exception đều cung cấp đầy đủ message gốc và header context.
- Không log toàn bộ exception payload kèm token hoặc dữ liệu cá nhân. Giữ các trường kỹ thuật cần thiết để truy nguyên.

### 6.4. `ignoreFailures` không phải hệ thống khôi phục

Có thể dùng cách cấu hình tương tự dưới đây **thay thế** bean channel đồng bộ ở mục 4 nếu mục tiêu là tiếp tục dispatch khi một subscriber ném lỗi:

~~~java
import org.springframework.integration.channel.PublishSubscribeChannel;

PublishSubscribeChannel events = new PublishSubscribeChannel();
events.setIgnoreFailures(true);
// Lưu ý: tiếp tục dispatch không đồng nghĩa retry hoặc ghi DLQ.
~~~

Không áp dụng nó như một thao tác vá lỗi production mà thiếu metric và recovery. Trong ứng dụng cần bảo đảm delivery audit, nếu `ignoreFailures(true)` khiến sender không thấy audit failure, hệ thống phải có cơ chế **khác** đảm bảo lỗi được ghi và xử lý.

### 6.5. Bản ghi failure riêng cho từng recipient

Để hỗ trợ retry mà không nhân đôi cả sự kiện, có thể định nghĩa:

~~~text
deliveryKey = eventId + ":" + subscriberId

EVT-1001:audit         -> COMPLETED
EVT-1001:notification  -> FAILED_RETRYABLE, attempt=2
EVT-1001:analytics     -> COMPLETED
~~~

Đây là **quy ước ứng dụng**, không phải header tự có. Với event mới, mỗi subscriber có một khóa delivery/idempotency riêng. Khi retry notification, không cần phát lại audit/analytics nếu những nhánh đó đã hoàn tất.

Một bảng delivery status mẫu:

| `eventId` | `subscriberId` | `attempt` | `state` | `nextRetryAt` |
|---|---|---:|---|---|
| EVT-1001 | audit | 1 | COMPLETED | — |
| EVT-1001 | notification | 2 | RETRY_PENDING | Sau backoff |
| EVT-1001 | analytics | 1 | COMPLETED | — |

Nếu dùng store, cần thiết kế **cập nhật nguyên tử, unique constraint cho delivery key và quy tắc trạng thái** thích hợp. Một `ConcurrentHashMap` trong một JVM chỉ có ích cho demo, không tự cung cấp độ bền, khả năng cạnh tranh nhiều node hoặc exactly-once.

## 7. Khi publisher và subscriber sống ở những thời điểm khác nhau

### 7.1. Subscriber đăng ký muộn hoặc đang stopped

`PublishSubscribeChannel` phát message tới **các subscriber hiện đang đăng ký theo dispatch configuration**. Nó không tự replay những message đã publish trước lúc subscriber mới được đăng ký.

Ví dụ:

~~~text
10:00  Audit và Notification subscriber đã đăng ký
10:01  Event E1 được publish
10:02  Analytics subscriber mới được đăng ký
10:03  Event E2 được publish
~~~

Analytics **không tự nhận lại E1** từ một pub/sub channel in-memory. Nếu nghiệp vụ yêu cầu catch-up/replay, cần event store, broker có retention và cơ chế consumer offset/cursor hoặc một backfill workflow phù hợp.

Tương tự, nếu subscriber bị stop, channel không biến thành “hàng đợi dành riêng cho subscriber đó” trừ khi bạn **thiết kế buffer/store tương ứng**.

### 7.2. Không có subscriber thì sao?

Một `PublishSubscribeChannel` thường hỗ trợ cấu hình **mức subscriber tối thiểu** hoặc các chính sách dispatch tương tự tùy phiên bản. Không nên suy từ `send(...)` rằng event đã được ít nhất một subscriber xử lý nếu cấu hình cho phép channel không có consumer.

**Cần xác minh tại runtime** những điều kiện như:

- Endpoint subscribe đã được Spring đăng ký và `isRunning()`?
- Có subscriber tối thiểu theo yêu cầu không?
- Có một nhánh nào hoàn tất thực sự không?
- Các receiver có đủ năng lực nhận task không?

Nếu audit là thành phần bắt buộc, việc “không ai subscribe mà publish vẫn trả thành công” sẽ vi phạm hợp đồng. Khi đó phải thiết kế kiểm soát readiness/subscription và nơi ghi event bền vững, thay vì chỉ dựa vào kết quả `send`.

### 7.3. Chính sách shutdown và backpressure

Với pub/sub đồng bộ, handler đang chạy có thể chặn đường shutdown; với executor, task có thể đang chờ trong queue. Các câu hỏi vận hành phải được trả lời:

- Dừng nhận event mới trước hay sau khi drain backlog?
- Task nào đang in-flight và có deadline hoàn tất không?
- Notification đang retry có thể tiếp tục sau restart như thế nào?
- Nếu executor queue đầy, publisher được chờ tối đa bao lâu hoặc bị từ chối ra sao?
- Có cần chờ broker ack hay DB commit trước khi báo `ACCEPTED` không?

Không thể bảo đảm **không mất message qua crash** chỉ bằng `stop()` hoặc `setWaitForTasksToCompleteOnShutdown(true)` trên executor. Graceful shutdown chỉ xử lý một số tình huống đóng ứng dụng có kiểm soát; crash, mất điện, kill -9 hoặc lỗi node cần cơ chế bền vững riêng.

## 8. Đảm bảo nhất quán nghiệp vụ mà không ép mọi subscriber thành một giao dịch

### 8.1. Đồng bộ không đồng nghĩa atomic

Giả sử Audit xử lý xong, Notification ném exception, Analytics chưa chạy. Dù tất cả nằm trên cùng thread, **side effect của Audit có thể đã commit**. Pub/sub không tự cung cấp distributed transaction để rollback:

~~~text
Publish E1
  |
  +-- Audit: COMMITTED
  +-- Notification: FAILED
  +-- Analytics: NOT_STARTED
~~~

Thử gửi lại `E1` cho toàn bộ channel có thể khiến Audit chạy lần hai. Để duy trì nhất quán, cần xác định rõ:

- **Sự kiện nghiệp vụ gốc** đã commit ở đâu?
- **Mốc công bố thành công** là lưu đơn, ghi outbox, broker acknowledgment hay mọi subscriber đã xong?
- **Subscriber nào bắt buộc**, subscriber nào có thể eventual consistency?
- Có cơ chế **idempotency/deduplication**, retry riêng hoặc compensation không?

### 8.2. Transactional outbox khi cần phát sự kiện đáng tin cậy

Một yêu cầu phổ biến là: “Đã commit đơn hàng thì cuối cùng phải có event tương ứng để các subscriber có thể xử lý.” Nếu ứng dụng commit DB rồi publish vào channel in-memory, crash giữa hai thao tác có thể làm mất event.

Mô hình **transactional outbox** giúp giảm rủi ro bằng cách lưu **đơn hàng và bản ghi event** trong cùng transaction DB, sau đó một publisher riêng đọc outbox và chuyển event đến broker hoặc các kênh tích hợp:

~~~mermaid
flowchart LR
    API[Order API] --> TX[DB transaction]
    TX --> ORD[(orders)]
    TX --> OUT[(outbox)]
    OUT --> PUB[Outbox publisher]
    PUB --> BRO[(Durable broker)]
    BRO --> A[Audit consumer]
    BRO --> N[Notification consumer]
    BRO --> M[Analytics consumer]
~~~

Đây là **mẫu kiến trúc bổ sung**, không phải tính năng tự kích hoạt bằng `PublishSubscribeChannel`. Outbox publisher có thể phát lặp sau crash hoặc ack không chắc chắn; subscriber vẫn cần idempotency. Hơn nữa, broker phải được cấu hình durability/retention/ack thực tế, không phải cứ gọi “broker” là chắc chắn không mất dữ liệu.

### 8.3. Không ép các nhánh phụ vào critical path

Nếu API chỉ cam kết “đơn đã được ghi nhận”, analytics có thể chạy sau. Nếu kiểm tra fraud là điều kiện bắt buộc để trả “đơn đã được duyệt”, fraud **không nên chỉ là subscriber fire-and-forget** rồi để API tuyên bố thành công ngay.

| Hoạt động | Mức nhất quán thường cần | Thiết kế tham khảo |
|---|---|---|
| Ghi đơn vào database | Hoàn tất trước reply “đã ghi nhận”. | Transaction DB + lỗi rõ ràng. |
| Phát `OrderCreated` đáng tin cậy | Không mất ý nghĩa event sau commit. | Outbox / broker với delivery contract. |
| Gửi email | Có thể eventual consistency. | Subscriber riêng, retry/DLQ, deduplication. |
| Analytics | Thường eventual consistency, có thể backfill. | Consumer riêng, checkpoint/replay. |
| Fraud/inventory để xác nhận đơn | Cần kết quả trước kết luận “confirmed”. | Request–reply/Gateway + Scatter–Gather hoặc workflow trạng thái. |
| Audit bắt buộc | Phụ thuộc yêu cầu kiểm soát. | Ghi bền vững trong critical path hoặc thiết kế delivery guarantee được kiểm chứng. |

Quyết định không chỉ là `sync` hay `async`, mà là **sự thật nghiệp vụ nào có thể được công bố ở thời điểm nào**.

## 9. Message Header, correlation và dữ liệu giữa các subscriber

### 9.1. Mỗi nhánh nhận message có cùng nội dung logic

Pub/sub phân phối cùng một event logic đến nhiều subscriber. Điều đó **không có nghĩa mỗi subscriber nhận một bản sao sâu (*deep copy*) của payload**. Nếu payload chứa đối tượng mutable và các subscriber cùng sửa nó, có thể xảy ra:

- Một subscriber đọc thấy dữ liệu đã bị subscriber khác thay đổi.
- Lỗi cạnh tranh dữ liệu khi xử lý song song.
- Message History/trace logs phản ánh những trạng thái không nhất quán.

**Khuyến nghị:** định nghĩa event DTO **bất biến**, ví dụ Java `record` với trường bất biến phù hợp; không nhét một collection mutable dùng chung vào payload rồi để các nhánh sửa trực tiếp. Nếu subscriber cần hình thức dữ liệu khác, dùng Transformer riêng ở nhánh đó.

### 9.2. Business ID, event ID, trace ID và correlation ID

| ID | Ý nghĩa | Ví dụ |
|---|---|---|
| `orderId` | Đối tượng nghiệp vụ. | `ORD-1001` |
| `eventId` | Sự kiện nghiệp vụ có thể được giao nhiều lần. | `EVT-1001` |
| `MessageHeaders.ID` | Một Spring message cụ thể. | UUID của message hiện tại |
| `traceId` | Hành trình quan sát qua nhiều bước/dịch vụ. | `trace-order-1001` |
| `correlationId` | Liên hệ nhiều message con/reply cùng một nhóm công việc. | `check-ORD-1001-v2` |
| `subscriberId` | Nhánh tiếp nhận. | `notification` |

Không dùng message ID thay `eventId` nếu cần deduplicate các lần broker redelivery tạo message mới. Cũng không tự tạo correlation group mới khi thêm mỗi subscriber: correlation phải phản ánh **nhóm nghiệp vụ cần gom kết quả**, chứ không phải số lượng endpoint trong flow.

### 9.3. Nếu cần Aggregator sau broadcast

Một số workflow thật sự phải chờ kết quả từ nhiều subscriber: inventory và fraud cùng phản hồi trước khi xác nhận đơn. Khi đó có thể kết hợp pub/sub với Scatter–Gather/Aggregator và **một hợp đồng reply có cấu trúc**:

~~~text
validationRequestId = VALIDATE-ORD-1001-2
expectedSubscribers = {inventory, fraud}

inventory reply: recipientId=inventory, PASS
fraud reply:     recipientId=fraud, PASS

Gatherer -> CONFIRMED
~~~

Cần kiểm tra **recipient duy nhất đã phản hồi**, timeout, duplicate/late replies và group expiry. Đếm `2` message không đủ để kết luận có đủ `2` subscriber: inventory có thể gửi hai reply trùng trong khi fraud chưa có.

Spring Integration có cơ chế sequence/correlation phục vụ một số mô hình fan-out khi được cấu hình, nhưng **không coi mọi cấu hình pub/sub là tự có Aggregator hoặc release strategy đúng nghiệp vụ**. Một `PublishSubscribeChannel` thường được sử dụng cho event một chiều; khi cần kết quả tổng hợp hãy chọn pattern và cấu hình dành cho tình huống đó.

### 9.4. Message History, executor và trace context

Khi bật Message History, Spring Integration có thể ghi lại những thành phần đã đi qua theo phạm vi tracking. Nó **không tự xác nhận** Audit đã ghi DB hay Email đã gửi thành công và **không tự làm distributed trace** qua mọi transport.

Với executor, MDC/thread-local của sender không tự lan truyền sang worker thread. Khi cần trace xuyên nhánh:

1. Giữ `eventId`, business ID và trace context trong message theo hợp đồng.
2. Dùng context propagation/observation instrumentation phù hợp với Spring Integration và transport đang dùng.
3. Khôi phục logging context ở consumer và cleanup sau khi xử lý.
4. Đối chiếu `PUBLISHED`, `SUBSCRIBER_STARTED`, `SUBSCRIBER_COMPLETED` hoặc `SUBSCRIBER_FAILED` thay vì suy luận chỉ từ một log ở publisher.

Ở ranh giới hệ thống, chọn lọc header được phép gửi; đừng serialize toàn bộ `replyChannel`, `errorChannel` hoặc security context nội bộ sang broker khác.

## 10. Theo dõi subscriber độc lập trong production

### 10.1. Structured event logs

Nên có schema chung nhưng **trạng thái riêng từng subscriber**:

~~~text
event=EVENT_PUBLISHED eventId=EVT-1001
  businessId=ORD-1001 channel=orders.events

event=SUBSCRIBER_STARTED eventId=EVT-1001
  subscriberId=audit attempt=1

event=SUBSCRIBER_COMPLETED eventId=EVT-1001
  subscriberId=audit outcome=SUCCESS durationMs=22

event=SUBSCRIBER_FAILED eventId=EVT-1001
  subscriberId=notification attempt=2
  errorCode=SMTP_TIMEOUT retryable=true

event=SUBSCRIBER_COMPLETED eventId=EVT-1001
  subscriberId=analytics outcome=SUCCESS durationMs=15
~~~

Đây là **schema do ứng dụng đề xuất**, không phải output mặc định của framework. Không ghi `SUBSCRIBER_COMPLETED` chỉ vì event đã được executor nhận task hoặc broker xác nhận lưu record.

### 10.2. Các metric có ý nghĩa

| Metric | Dùng để trả lời |
|---|---|
| Publish attempts / dispatch failures | Publisher có phát message thành công theo contract không? |
| Subscriber started/completed/failed count | Nhánh nào xử lý thành công hoặc lỗi? |
| Processing latency theo subscriber | Email chậm có kéo dài thời gian xử lý không? |
| Executor active threads / queued tasks | Thread pool dùng chung có bão hòa? |
| Per-branch backlog / oldest-event age | Nhánh nào bị trễ và cần scale? |
| Retry attempts / DLQ entries | Có retry storm hay event cần người xử lý? |
| Duplicate-skipped count | Idempotency hoạt động ra sao khi redelivery? |
| Last-success timestamp / rate | Subscriber có còn xử lý event khi traffic đến? |
| Group completion/expiration (nếu gather) | Yêu cầu chờ nhiều kết quả có bị treo? |

Chỉ dùng `subscriberId` và outcome có tập giá trị hữu hạn làm label metric. `eventId`, `orderId`, `traceId` nên nằm trong log/tracing có phân quyền; dùng chúng làm label làm tăng cardinality rất lớn.

### 10.3. Dashboard không được gom tất cả thành một trạng thái

Một dashboard chỉ có “`orders.events: OK`” che giấu nhánh Notification đang hỏng. Nên hiển thị riêng:

~~~text
Event publication:
  publisher: healthy
  outbound rejects: 0

Subscribers:
  audit        completionRate: 99.9%    queueAge: low
  notification completionRate: 72%      queueAge: high
  analytics    completionRate: 99.8%    queueAge: low
~~~

Các số ở trên **chỉ minh họa hình thức dashboard**, không phải chỉ số đo thật. Một nhánh chậm cần được xem riêng với publisher và các nhánh còn lại. Nếu các nhánh dùng chung executor hoặc DB pool, cũng cần metric ở tài nguyên chung.

## 11. Kiểm thử lỗi riêng từng nhánh

### 11.1. JUnit 5: một subscriber lỗi, các nhánh khác vẫn xử lý

Sử dụng `SubscriberIsolationConfiguration` ở mục 4. Trong cấu hình này, cả ba subscriber dùng channel đồng bộ và nhánh Notification **bắt exception của chính nó** để lưu thất bại theo chính sách minh họa.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(SubscriberIsolationConfiguration.class)
class SubscriberIsolationTest {

    @Autowired
    @Qualifier("orders.events")
    MessageChannel events;

    @Autowired
    BranchProbe probe;

    @Test
    void notificationFailureDoesNotStopAuditOrAnalytics() {
        int auditBefore = probe.auditSuccess.get();
        int notifyOkBefore = probe.notificationSuccess.get();
        int notifyFailBefore = probe.notificationFailure.get();
        int analyticsBefore = probe.analyticsSuccess.get();

        probe.failNotification.set(true);
        try {
            boolean sent = events.send(
                    MessageBuilder.withPayload(
                            new OrderCreated("EVT-TEST-1", "ORD-TEST-1"))
                            .build(), 1_000);
            assertTrue(sent);
        } finally {
            probe.failNotification.set(false);
        }

        assertEquals(auditBefore + 1, probe.auditSuccess.get());
        assertEquals(notifyOkBefore,
                probe.notificationSuccess.get());
        assertEquals(notifyFailBefore + 1,
                probe.notificationFailure.get());
        assertEquals(analyticsBefore + 1,
                probe.analyticsSuccess.get());
    }

    @Test
    void allBranchesCanSucceedWhenNoFailure() {
        int auditBefore = probe.auditSuccess.get();
        int notifyBefore = probe.notificationSuccess.get();
        int analyticsBefore = probe.analyticsSuccess.get();

        probe.failNotification.set(false);
        boolean sent = events.send(
                MessageBuilder.withPayload(
                        new OrderCreated("EVT-TEST-2", "ORD-TEST-2"))
                        .build(), 1_000);

        assertTrue(sent);
        assertEquals(auditBefore + 1, probe.auditSuccess.get());
        assertEquals(notifyBefore + 1,
                probe.notificationSuccess.get());
        assertEquals(analyticsBefore + 1,
                probe.analyticsSuccess.get());
    }
}
~~~

**Giải thích kết quả:** Test thứ nhất kiểm tra Notification có failure nhưng Audit/Analytics vẫn được gọi. Kết quả này đúng **vì ta chủ động catch và ghi lỗi tại Notification subscriber**, không phải vì pub/sub tự bảo đảm cách ly mọi exception. `sent=true` trong test thứ nhất **không** có nghĩa Notification đã thành công.

Các counter là state của Spring context: ví dụ lấy **giá trị trước test** thay vì giả định counter luôn bằng 0. Trong test suite phức tạp, nên dùng context độc lập, reset state hoặc cấu hình test concurrency phù hợp để tránh test lẫn nhau. Không chạy các test ghi vào cùng probe theo kiểu song song không kiểm soát rồi kỳ vọng số đếm độc lập.

### 11.2. Test chứng minh sai lầm với subscriber ném lỗi chưa được xử lý

Tạo một **cấu hình test riêng** với:

1. Một `PublishSubscribeChannel` đồng bộ.
2. Subscriber A tăng counter.
3. Subscriber B ném exception nhưng **không catch**.
4. Subscriber C tăng counter.
5. Dùng cơ chế dispatch mặc định **không bỏ qua lỗi** rồi quan sát lỗi `send(...)`.

**Điều cần khẳng định:** Publisher có thể nhìn thấy exception và không thể suy ra mọi subscriber đã hoàn tất. Không viết test phụ thuộc cố định vào thứ tự A/B/C nếu chưa điều khiển được thứ tự dispatch của cấu hình thử nghiệm; nếu cần test riêng việc tiếp tục khi có lỗi, cấu hình `ignoreFailures` và xác định bằng probe những nhánh nào thực sự đã chạy.

Không đặt test này chung trong context của ví dụ mục 4: khi đó Notification đã catch exception, không còn tái hiện được nhánh bị lỗi lan truyền.

### 11.3. Test async bằng latch thay vì `Thread.sleep`

Khi chuyển sang `PublishSubscribeChannel(publicationExecutor)` ở mục 5, việc `send` trả về chỉ nói về trạng thái dispatch/đăng ký task. Không được assert ngay rằng tất cả counter đã tăng xong.

Một cách kiểm thử có thể kiểm soát:

1. Subscriber test dùng `CountDownLatch started` để báo đã bắt đầu và `CountDownLatch release` để chờ lệnh cho phép tiếp tục.
2. Publisher gọi `send` và lưu thời điểm nhận kết quả theo **contract của executor**.
3. Khi `started` đã được báo, xác nhận handler chưa hoàn tất vì `release` chưa được mở.
4. Mở `release`, dùng `await(timeout)` để xác minh handler hoàn tất.
5. Trong `finally`, luôn mở latch và shutdown executor/context để tránh treo test.
6. Lặp lại với executor nhỏ và queue capacity hữu hạn để kiểm tra rejection/backpressure.

Không dùng `Thread.sleep(5000)` để khẳng định việc xử lý đã hoàn tất hoặc chưa hoàn tất; cách đó dễ flaky trên CI. Nếu cần test isolation khi một subscriber chậm, dùng **latch riêng từng nhánh**, đồng thời xác định pool có đủ thread để hai nhánh thật sự chạy song song.

### 11.4. Ma trận lỗi và phục hồi

| Kịch bản | Bằng chứng test cần thu |
|---|---|
| Ba subscriber đồng bộ đều thành công | Mỗi handler được gọi đúng theo contract, không nhầm với commit bên ngoài. |
| Notification ném lỗi và được catch riêng | Audit/Analytics vẫn xử lý; notification failure được ghi. |
| Notification ném lỗi chưa được xử lý | Publisher nhận failure theo dispatcher policy; không mặc định các nhánh sau được gọi. |
| Dispatcher bỏ qua failure | Các nhánh khác được thử dispatch; có metric/log riêng cho nhánh lỗi. |
| Subscriber async xử lý chậm | Sender không bị nhầm accepted với completed; timeout test hữu hạn. |
| Executor bão hòa | Rejection policy được kiểm chứng; không silent drop. |
| Subscriber mới đăng ký sau E1 | Không tự nhận E1 từ in-memory channel nếu không có replay. |
| Subscriber stopped | Hành vi send/subscription được xác minh; không coi event đã được xử lý. |
| Email retry ba lần | Audit/Analytics không bị gửi lại do retry riêng notification. |
| Email provider nhận rồi response timeout | Retry có idempotency hoặc reconciliation, không gửi lặp tùy tiện. |
| App crash khi task còn trong executor queue | Không tuyên bố message đã durable; kiểm tra recovery design. |
| Hai recipient trả kết quả để Aggregator gom | Có correlation, release strategy và xử lý duplicate/late reply. |
| Message đi qua HTTP/broker và mất trace header | Observability chỉ rõ điểm đứt context và có mapper đúng. |

## 12. Quy trình chẩn đoán một nhánh gặp sự cố

Giả sử người dùng phản ánh **đơn hàng đã tạo nhưng không nhận email**, trong khi Audit/Analytics vẫn bình thường. Một quy trình điều tra rõ ràng:

1. **Xác định event gốc** bằng `eventId`, business ID, thời gian và trace ID nếu có; kiểm tra Order Service đã commit đơn và publish theo contract chưa.
2. **Xác định subscription:** Notification endpoint có đang đăng ký/running? Event được phát trước hay sau lúc subscriber start?
3. **Kiểm tra mốc dispatch:** publisher đã phát event, executor/broker đã tiếp nhận, hay bị rejection/queue full?
4. **Kiểm tra nhánh Notification:** đã có `SUBSCRIBER_STARTED` chưa? Exception thuộc loại tạm thời, permanent hay kết quả không chắc chắn?
5. **Kiểm tra retry/recovery:** attempt count, backoff, idempotency key, dead-letter/quarantine và replay; tránh retry toàn event gây gửi trùng nhánh khác.
6. **So sánh các nhánh khác:** Audit và Analytics có cùng event ID không? Chúng thành công không chứng minh Notification cũng thành công.
7. **Kiểm tra tài nguyên chung:** executor/DB pool/network có bão hòa khiến notification bị starve không?
8. **Khôi phục có kiểm soát:** replay **đúng recipient cần phục hồi**, bảo đảm side effect không bị nhân đôi, bổ sung test hồi quy cho lỗi đã gặp.

Nếu không tìm thấy `eventId` ở Notification nhưng Analytics có, hãy kiểm tra fan-out/dispatch và tầng persistence trước khi nghi SMTP. Nếu Notification đã bắt đầu rồi thất bại, tập trung vào handler và hệ thống email.

## 13. Các sai lầm thường gặp

| Hiểu nhầm | Vấn đề gây ra | Cách tiếp cận đúng |
|---|---|---|
| “Mỗi subscriber là class riêng nên lỗi hoàn toàn độc lập.” | Shared thread/pool/DB vẫn tạo coupling. | Thiết kế isolation ở cấp thực thi, tài nguyên và recovery. |
| “`PublishSubscribeChannel` mặc định async.” | Subscriber chậm giữ thread gửi. | Phân biệt constructor có/không có `TaskExecutor`. |
| “Một subscriber ném lỗi không ảnh hưởng subscriber khác.” | Dispatcher đồng bộ có thể fail-fast. | Kiểm soát failure policy và test fan-out thực tế. |
| “`ignoreFailures(true)` nghĩa là đã xử lý lỗi.” | Lỗi bị che, không có retry/recovery. | Ghi failure riêng, metrics và durable recovery khi cần. |
| “`send=true` nghĩa là mọi subscriber commit thành công.” | Công bố sai trạng thái. | Phân biệt selected/accepted/processed/committed. |
| “Dùng executor là không bao giờ chặn.” | Queue full hoặc CallerRunsPolicy thay đổi latency. | Giới hạn pool, rejection policy và load test. |
| “Async pub/sub in-memory tương đương broker durable.” | Mất task/event khi crash/restart. | Dùng store/broker và delivery guarantees phù hợp. |
| “Retry toàn channel khi một email thất bại.” | Audit/Analytics có thể chạy lại. | Retry theo subscriber, idempotency key theo event+recipient. |
| “Subscriber mới được thêm tự nhận mọi event cũ.” | Mất khả năng replay/backfill. | Dùng retention + consumer offset hoặc event store. |
| “Cùng message là mỗi nhánh có payload copy độc lập.” | Mutable payload bị sửa cạnh tranh. | DTO bất biến, transform riêng từng subscriber. |
| “Broadcast tự gom mọi reply cho Gateway.” | Nhiều reply hoặc timeout không kiểm soát. | Dùng Scatter–Gather/Aggregator nếu cần chờ nhiều kết quả. |
| “Audit thành công thì Email chắc chắn thành công.” | Che lỗi từng nhánh. | Quan sát accepted/completed/failed theo `subscriberId`. |
| “`isRunning=true` nghĩa là subscriber khỏe.” | Bỏ sót lỗi downstream, backlog, retry. | Kết hợp processed rate, error rate, queue age, last success. |
| “Message History tự ghi mọi lỗi nhánh.” | Không có dữ liệu kết quả nghiệp vụ. | Structured logging/metrics/tracing theo subscriber. |

## 14. Bài tập thực hành

1. **Fan-out cơ bản:** tạo `PublishSubscribeChannel` với Audit, Notification và Analytics subscriber. Kiểm tra một event có được xử lý ở cả ba nhánh trong cấu hình đồng bộ không lỗi.
2. **Lỗi lan truyền:** cho Notification ném exception mà không catch. Quan sát sender, những subscriber nào đã chạy và khác biệt khi cấu hình bỏ qua failure tại dispatcher.
3. **Cô lập tại subscriber:** bắt lỗi Notification, ghi `eventId` và `subscriberId` vào failure store mô phỏng; xác nhận Audit/Analytics không bị dừng.
4. **Bất đồng bộ:** dùng `ThreadPoolTaskExecutor` với queue capacity hữu hạn. So sánh thời điểm `send` trả về với thời điểm từng handler hoàn tất; dùng latch có timeout.
5. **Chia executor:** đưa Notification vào executor/queue riêng, Audit sang nhánh lưu bền vững. Giả lập Notification rất chậm và đánh giá Audit có bị ảnh hưởng không.
6. **Retry riêng:** chỉ retry `EVT-1001:notification`, xác minh số lần gọi Audit/Analytics không tăng. Tạo kết quả response timeout sau khi email provider đã nhận để thử idempotency.
7. **Đăng ký muộn:** publish E1 trước khi Analytics subscriber chạy và E2 sau đó. Giải thích vì sao muốn Analytics nhận E1 cần một nguồn replay bền vững.
8. **Quá tải:** giới hạn thread pool rồi gửi burst lớn; ghi rõ khi nào task được nhận, bị từ chối hoặc bị chặn, và response của producer.
9. **Correlated replies:** dùng inventory và fraud subscriber trả về `CheckResult`. Thiết kế Scatter–Gather/Aggregator chỉ release khi đủ hai recipient **duy nhất** và timeout khi thiếu một.
10. **Quan sát:** tạo sự kiện `EVENT_PUBLISHED`, `SUBSCRIBER_STARTED`, `SUBSCRIBER_FAILED`, `SUBSCRIBER_COMPLETED`; truy nguyên một event khi Analytics thành công nhưng Notification thất bại.
11. **Transaction outbox:** mô tả sự cố crash giữa DB commit và in-memory publish; thiết kế transaction outbox rồi phân tích tình huống publisher phát lặp.
12. **Payload bất biến:** tạo event chứa collection có thể thay đổi, cho hai subscriber xử lý song song và quan sát rủi ro; chuyển sang DTO bất biến và kiểm thử.

### Câu hỏi tự kiểm tra

**Câu 1:** Có ba subscriber được kết nối với `PublishSubscribeChannel` đồng bộ; Notification mất 3 giây. Publisher có thể bị ảnh hưởng không? **Có.** Không có executor, dispatch và handler có thể giữ thread gửi trong quá trình thực thi.

**Câu 2:** `ignoreFailures(true)` có bảo đảm nhánh Notification bị lỗi được retry không? **Không.** Chính sách tiếp tục dispatch khác hẳn cơ chế retry và recovery.

**Câu 3:** Channel dùng executor, `send(...)` thành công. Có thể kết luận Email đã gửi xong chưa? **Chưa.** Có thể tác vụ mới được executor tiếp nhận.

**Câu 4:** Khi Notification thất bại nhưng Audit đã ghi thành công, có nên retry toàn bộ event fan-out không? **Không mặc định.** Ưu tiên retry nhánh lỗi, kiểm soát idempotency của từng recipient.

**Câu 5:** Nếu Analytics subscriber khởi động sau khi E1 được publish, nó có tự nhận E1 từ `PublishSubscribeChannel` in-memory không? **Không.** Cần event replay/retention nếu nghiệp vụ đòi catch-up.

**Câu 6:** Một `Message<OrderCreated>` gửi cho ba subscriber có bảo đảm mỗi nhánh nhận bản sao sâu của object payload không? **Không.** Nên dùng payload bất biến và tránh shared mutable state.

**Câu 7:** Muốn trả “đơn đã được xác nhận” khi inventory và fraud đều PASS, chỉ broadcast sự kiện có đủ không? **Không.** Cần thiết kế kết quả, correlation, release, timeout và workflow/Gateway phù hợp.

**Câu 8:** Vì sao vẫn cần retry/idempotency dù đã dùng transactional outbox? **Vì** publisher/consumer có thể thấy kết quả ack không chắc chắn hoặc redelivery, tạo bản gửi lặp trong mô hình at-least-once.

## 15. Kết luận

**Publish–Subscribe tách producer khỏi các subscriber về mặt trách nhiệm, nhưng không tự tạo cách ly lỗi hoàn toàn.** Trong Spring Integration, cần phân biệt `PublishSubscribeChannel` đồng bộ với channel sử dụng `TaskExecutor`, và tiếp tục phân biệt hai mô hình này với một hạ tầng broker/store bền vững.

Muốn **mỗi subscriber chịu lỗi riêng**, hãy thiết kế contract của từng nhánh: outcome và failure record, retry có giới hạn, idempotency, tài nguyên/queue phù hợp, dead-letter hoặc recovery, cùng log và metric có `subscriberId`. Nếu nghiệp vụ cần **đợi nhiều kết quả**, bổ sung Scatter–Gather/Aggregator, correlation và timeout; đừng buộc một event fan-out một chiều tự trở thành request–reply. Tổ chức như vậy giúp các flow Router, Filter, Transformer, Gateway và những Enterprise Integration Patterns khác ít phụ thuộc, dễ mở rộng, có thể kiểm thử và truy nguyên chính xác khi chỉ một nhánh gặp sự cố.
