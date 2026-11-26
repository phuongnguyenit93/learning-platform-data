# Khi nào dùng retry tại chỗ và khi nào chuyển sang queue trì hoãn?

Một `@RabbitListener` có thể gặp lỗi khi gọi database, HTTP API hoặc khi giải mã dữ liệu. Nếu tác vụ chỉ vấp một lỗi mạng trong 100 ms, thử lại ngay trong cùng consumer có thể là giải pháp đơn giản. Nhưng nếu đối tác trả `429 Too Many Requests` và yêu cầu đợi hai phút, giữ nguyên listener thread để ngủ rồi thử lại sẽ làm lãng phí tài nguyên, giữ delivery chưa ack và chặn những message khác. Trong trường hợp đó, **chuyển việc thử lại sang một queue trì hoãn** thường phù hợp hơn.

Bài thuộc chương **Thử lại thông điệp** của module **SPRING_AMQP**. Khi tích hợp RabbitMQ bằng `RabbitTemplate`, `@RabbitListener`, exchange, queue và binding, lựa chọn retry có tác động trực tiếp đến **acknowledgement, consumer concurrency, dead-letter, transaction, thứ tự xử lý, idempotency và khả năng quan sát**. Bài sẽ giúp bạn quyết định giữa **retry tại chỗ (in-process/local retry)** và **retry qua broker với độ trễ (delayed retry)**, đồng thời tránh biến message lỗi thành một vòng lặp vô hạn.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **local retry trong listener**, **broker requeue ngay** và **delayed retry qua queue** — ba cơ chế khác nhau thường bị gọi chung là “retry”.
2. Đánh giá thời gian lỗi có khả năng tự hết, số lần thử, tài nguyên thread/channel, throughput và độ ưu tiên nghiệp vụ để chọn cơ chế.
3. Cấu hình Spring Retry với `SimpleRabbitListenerContainerFactory`, `RetryInterceptorBuilder`, backoff và `RejectAndDontRequeueRecoverer`.
4. Thiết kế topology **work queue → delayed retry queue → work queue** có điểm dừng ở **terminal DLQ**.
5. Giải thích rủi ro **publish bản retry thành công nhưng ack bản gốc thất bại** và vì sao publisher confirms không tự tạo giao dịch nguyên tử.
6. Sử dụng retry budget/event ID thay vì hiểu sai `x-death` là số lần business retry tổng quát.
7. Kiểm thử retry, poison message, broker restart, DLQ, idempotency và độ trễ thực tế trước khi triển khai.

## 2. Ba cơ chế cần gọi đúng tên

| Cơ chế | Đường đi | Thời gian chờ ở đâu? | Message gốc đang ở trạng thái gì? |
|---|---|---|---|
| **Retry tại chỗ** | `@RabbitListener → lỗi → Spring Retry/backoff → gọi listener lại` | **Trong JVM**, thường chiếm listener thread | Delivery thường vẫn **unacked** cho tới khi hoàn tất/recover |
| **Requeue ngay** | `@RabbitListener → basic.reject/nack(requeue=true) → broker giao lại` | Broker **không bảo đảm có delay** | Delivery được trả lại queue và có thể được giao lại tức thì |
| **Delayed retry** | `@RabbitListener → publish/dead-letter → retry queue/delayed mechanism → work queue` | **Trong broker hoặc cơ chế lập lịch bền vững** | Delivery gốc cần được settled; một bản sẽ được giao lại sau |

~~~mermaid
flowchart TD
    Q["Work queue"] --> L["@RabbitListener"]
    L --> E{"Lỗi gì?"}
    E -->|"Transient rất ngắn"| R["Retry tại chỗ<br/>vài lần + backoff ngắn"]
    R -->|"Thành công"| A["Ack"]
    R -->|"Vẫn lỗi, cần chờ lâu"| H["Handoff sang delayed retry"]
    E -->|"Cần chờ lâu"| H
    E -->|"Permanent: schema sai"| D["Reject không requeue<br/>terminal DLQ"]
    H --> W["Retry queue / scheduler<br/>chờ có giới hạn"]
    W --> Q
~~~

**Điểm quyết định:** `Thread.sleep(30_000)` bên trong listener **không phải** delayed queue. Nó vẫn giữ thread, có thể giữ delivery unacked và chiếm prefetch credit. Ngược lại, `basicNack(tag, false, true)` **không phải** delayed retry: broker có thể giao lại gần như ngay lập tức.

## 3. Khái niệm “tại chỗ” trong Spring AMQP

Với một listener đồng bộ sử dụng `AcknowledgeMode.AUTO`, Spring AMQP có thể gắn một **retry interceptor** vào listener container. Khi method ném exception, interceptor gọi lại cùng handler trong phạm vi xử lý delivery hiện tại theo retry policy và backoff.

~~~mermaid
sequenceDiagram
    participant B as RabbitMQ
    participant C as Listener container
    participant R as Spring Retry
    participant S as Business service
    B-->>C: Giao delivery M1
    C->>R: Invoke handler
    R->>S: Attempt 1
    S-->>R: Timeout
    Note over R: Backoff 300 ms<br/>listener thread còn bận
    R->>S: Attempt 2
    S-->>R: Thành công
    R-->>C: Success
    C->>B: basic.ack(M1)
~~~

Trong **stateless local retry**, broker thường chỉ nhìn thấy **một delivery**, dù business method đã được gọi nhiều lần. Những lần thử này không tự tăng `x-death` hay cờ `redelivered`, vì chưa có một lần broker dead-letter/requeue mới.

Đặc điểm quan trọng:

- Handler và backoff chiếm **slot xử lý** của listener trong thời gian retry.
- Với `SimpleMessageListenerContainer` (SMLC), listener invoker chạy trên `TaskExecutor` của container.
- Với `DirectMessageListenerContainer` (DMLC), business callback chạy trên RabbitMQ Java client dispatch thread; ngủ lâu đặc biệt dễ làm nghẽn callback.
- Broker có thể đã giao trước các message khác theo `prefetch`; trong khi handler chờ backoff, các delivery đó tiếp tục chiếm credit chưa ack.
- Nếu ứng dụng/container mất kết nối, delivery chưa ack có thể được giao lại; bộ đếm retry chỉ nằm trong bộ nhớ JVM không phải lịch sử bền vững.

### Stateless và stateful không giống nhau

**Stateless retry** thử lại bên trong một lần gọi listener, phù hợp khi không có transaction bên ngoài cần rollback qua các lần thử. **Stateful retry** lưu trạng thái qua các lần xử lý delivery, phù hợp hơn với những thiết kế có transaction bên ngoài cần rollback, nhưng yêu cầu nhận diện message ổn định (`messageId` hoặc `MessageKeyGenerator`).

Không chọn stateful chỉ vì “muốn thử lại nhiều lần”, hoặc stateless chỉ vì cấu hình ngắn. Transaction boundary, message identity và cách recoverer xử lý khi hết retry mới là tiêu chí cần đánh giá.

## 4. Khi nào retry tại chỗ là lựa chọn tốt?

Local retry thường phù hợp khi:

1. Lỗi **có khả năng hết nhanh**, chẳng hạn optimistic lock conflict, HTTP timeout ngắn hoặc pool tạm bận.
2. **Số lần thử ít**: ví dụ tổng cộng 2–3 attempts, với backoff vài trăm mili giây.
3. Chờ trong listener thread có chi phí chấp nhận được đối với concurrency hiện tại.
4. Bạn muốn giữ xử lý đơn giản, không thêm exchange/queue/metadata cho retry dài.
5. Nghiệp vụ cho phép thử lại tác vụ vì đã có idempotency hoặc chưa thực hiện side effect không thể đảo.
6. Bạn đã có **recoverer/terminal handling** nếu hết số lần thử.

Ví dụ lỗi khi lấy optimistic lock:

~~~text
Attempt 1: cập nhật row → OptimisticLockException
Backoff: 100 ms
Attempt 2: đọc lại phiên bản row → cập nhật thành công
Ack message sau khi nghiệp vụ thành công
~~~

Nếu mỗi lần gọi database mất khoảng 40 ms và backoff 100 ms, giữ worker thêm một khoảng ngắn có thể hợp lý. Tuy nhiên, phải đo **p95/p99 latency**, tần suất lỗi và mức bão hòa thread thay vì lấy một con số cố định làm ngưỡng cho mọi hệ thống.

### Không nên retry tại chỗ khi nào?

- Service bên ngoài trả `Retry-After: 120` giây.
- Hệ thống phụ trợ outage nhiều phút.
- Có hàng nghìn message cùng lỗi; mỗi consumer ngủ dài làm backlog tăng nhanh.
- Handler đang giữ lock, database transaction hoặc tài nguyên khan hiếm trong lúc chờ.
- Cần thay đổi worker/deployment giữa các lần thử; JVM memory không phải nơi giữ lịch xử lý dài hạn.
- Bạn muốn điều phối riêng số lượt retry, dead-letter, cảnh báo và hạn mức lưu message.

**Ngưỡng không phải quy tắc cứng:** “dưới một giây thì local, trên một giây thì delayed” chỉ có thể là heuristic. Với 2 consumers, chờ 3 giây có thể ảnh hưởng rất lớn; với workload cực thấp, chờ 3 giây có thể vẫn chấp nhận được.

## 5. Cấu hình local retry bằng Spring Boot

Với các phiên bản Spring Boot 3.x có nhóm properties tương ứng, có thể cấu hình `SimpleRabbitListenerContainerFactory` mặc định:

~~~yaml
spring:
  rabbitmq:
    listener:
      type: simple
      simple:
        acknowledge-mode: auto
        default-requeue-rejected: false
        concurrency: 4
        prefetch: 10
        retry:
          enabled: true
          max-attempts: 3
          initial-interval: 300ms
          multiplier: 2.0
          max-interval: 2s
~~~

Với cấu hình đó, `max-attempts: 3` có ý nghĩa **tối đa ba lần gọi listener bao gồm lần đầu**, chứ không phải ba lần retry ngoài lần đầu. Trong kịch bản liên tục lỗi, các khoảng chờ minh họa là **300 ms** và **600 ms**, chưa tính thời gian chạy từng attempt.

Các điểm cần kiểm tra:

- Spring Boot áp các property cho **factory mặc định**; listener chỉ định `containerFactory="specialFactory"` có thể không dùng các giá trị trên.
- Không chỉ bật `retry.enabled` rồi mặc định mọi message luôn vào DLQ sau khi exhausted; phải xác định recoverer/error handler cuối cùng và cấu hình DLX.
- `default-requeue-rejected: false` giúp tránh broker hot requeue sau lỗi cuối, nhưng đồng thời có thể reject cả lỗi transient nếu không có recoverer/retry thích hợp.
- Tên/cách bind các properties có thể khác giữa Spring Boot versions, đặc biệt khi dự án có custom factory hoặc Spring AMQP dependency override. Hãy đối chiếu application properties của bản thực tế.

## 6. Cấu hình local retry bằng Java, có recoverer cuối

Nếu muốn gắn policy riêng cho một listener, bạn có thể tạo factory bằng Spring Boot configurer. Ví dụ này dành cho nhánh Spring Boot/Spring AMQP có các API tương ứng:

~~~java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.config.RetryInterceptorBuilder;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.retry.RejectAndDontRequeueRecoverer;
import org.springframework.boot.autoconfigure.amqp.SimpleRabbitListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class LocalRetryConfiguration {

    @Bean
    SimpleRabbitListenerContainerFactory localRetryFactory(
            SimpleRabbitListenerContainerFactoryConfigurer configurer,
            ConnectionFactory connectionFactory) {

        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        configurer.configure(factory, connectionFactory);
        factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
        factory.setDefaultRequeueRejected(false);

        factory.setAdviceChain(
                RetryInterceptorBuilder.stateless()
                        .maxAttempts(3)
                        .backOffOptions(300L, 2.0, 2000L)
                        .recoverer(new RejectAndDontRequeueRecoverer())
                        .build()
        );
        return factory;
    }
}
~~~

Lưu ý: `RetryInterceptorBuilder.stateless()` áp dụng **Spring Retry ngay trong listener chain**. `RejectAndDontRequeueRecoverer` sau khi exhausted yêu cầu container **reject không requeue**. Với work queue có DLX terminal hợp lệ, broker có thể đưa message vào DLQ; nếu thiếu DLX/binding, message có thể bị loại.

Không gắn advice thủ công **và** bật Boot retry thêm lần nữa mà không kiểm tra, vì có thể vô tình tạo retry lồng nhau khiến tổng attempts vượt ý định. Nếu listener có transaction bên ngoài, cân nhắc **stateful retry** thay vì áp dụng stateless một cách máy móc.

### Listener và phân loại exception

~~~java
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class InventoryUpdateListener {

    private final InventoryService inventoryService;

    public InventoryUpdateListener(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @RabbitListener(
        queues = "inventory.update.q",
        containerFactory = "localRetryFactory")
    public void onMessage(String orderId) {
        if (orderId == null || orderId.isBlank()) {
            throw new AmqpRejectAndDontRequeueException(
                    "Missing orderId");
        }
        inventoryService.updateForOrder(orderId);
    }
}
~~~

`InventoryService` là thành phần nghiệp vụ minh họa. Các exception do Spring Retry nhìn thấy có thể được bọc trong `ListenerExecutionFailedException`; **mặc định retry policy có thể retry cả lỗi vĩnh viễn** nếu không cấu hình classifier. Một exception dùng để reject cuối không tự chứng minh interceptor sẽ bỏ qua mọi attempts trước đó.

Muốn **loại lỗi schema khỏi retry ngay từ đầu**, nên cấu hình exception classifier có `traverseCauses`, hoặc dùng một error path dành riêng cho dữ liệu vĩnh viễn. Hãy kiểm tra behavior theo đúng Spring Retry version và dùng integration tests để xác nhận số lần listener được gọi.

## 7. Delayed retry: chuyển thời gian chờ khỏi listener thread

Khi dự kiến phải chờ nhiều giây, phút hoặc giờ, thường hợp lý hơn nếu **settle delivery gốc** rồi để broker/scheduler giữ bản message cần retry đến thời điểm sau.

~~~mermaid
sequenceDiagram
    participant B as RabbitMQ work queue
    participant L as Listener
    participant P as RabbitTemplate retry publisher
    participant R as RabbitMQ delayed retry queue
    B-->>L: Delivery M1
    L->>L: Attempt 1 → transient failure
    L->>P: Publish retry copy M1' + attempt=1
    P->>R: Gửi tới retry exchange/queue
    R-->>P: Publisher confirm (nếu bật)
    L->>B: Ack delivery gốc khi handoff đủ an toàn
    Note over R: Giữ ~30 giây theo message TTL
    R-->>B: Expired → dead-letter về work exchange
    B-->>L: Delivery M1'
~~~

Ưu điểm:

- Listener thread được giải phóng sau khi **handoff**.
- Không giữ một delivery unacked chỉ để ngủ trong thời gian dài.
- Dễ quan sát queue đang chờ retry và backlog của work queue riêng biệt.
- Có thể thay đổi số worker giữa các attempts và giới hạn tốc độ nhận sau khi hệ thống phục hồi.
- Thời gian trì hoãn có thể được tổ chức theo các mức backoff (ví dụ 30 giây, 2 phút, 10 phút).

Đổi lại, hệ thống phải quản lý **bản sao retry, routing, publisher confirms/returns, retry attempt metadata, idempotency, DLQ** và các rủi ro của việc publish/ack không nguyên tử.

## 8. Bảng quyết định: local hay delayed?

| Câu hỏi | Nghiêng về retry tại chỗ | Nghiêng về delayed retry |
|---|---|---|
| Lỗi thường phục hồi sau bao lâu? | Vài chục/vài trăm ms | Hàng chục giây đến nhiều phút |
| Số lần thử dự kiến | Ít (ví dụ 2–3) | Nhiều giai đoạn chờ có budget rõ |
| Listener concurrency | Có dư công suất và lỗi ít xảy ra | Thread/consumer khan hiếm, backlog lớn |
| Có thể giữ delivery unacked? | Trong khoảng ngắn chấp nhận được | Không muốn giữ unacked trong thời gian dài |
| Cần theo dõi lịch retry qua restart? | Không quan trọng hoặc xử lý lại an toàn | Cần lịch retry bền vững qua deploy/restart |
| Thứ tự xử lý | Muốn hạn chế thay đổi thứ tự trong một consumer | Chấp nhận retry đi sau message mới |
| Độ phức tạp hạ tầng | Muốn đơn giản | Chấp nhận thêm queue/exchange/monitoring |
| Lỗi dữ liệu vĩnh viễn | **Không chọn cả hai** | **Không chọn cả hai**: terminal DLQ/quarantine |
| Giao dịch nghiệp vụ chưa chắc đã commit? | Chỉ thử nếu side effect idempotent | Cần làm rõ trạng thái trước handoff/replay |

### Một quy tắc thực dụng

**Local retry** cho lỗi dự kiến tự hết nhanh và hiếm, với tổng thời gian chiếm worker nhỏ. **Delayed retry** khi điều quan trọng nhất là **nhường tài nguyên** trong lúc phụ thuộc bên ngoài chưa sẵn sàng. **Terminal reject/DLQ** cho dữ liệu hoặc hợp đồng không thể xử lý nếu không sửa code/message.

Không có ngưỡng thời gian tuyệt đối. Chọn theo **phần trăm thời gian worker bị chiếm khi lỗi**, throughput, service-level objectives và chi phí broker operation.

## 9. Tính nhanh ngân sách concurrency trước khi chọn

Giả sử bạn có:

~~~text
4 replicas
4 consumers / replica
= 16 consumer slots

Mỗi message bị lỗi:
  attempt 1: 200 ms
  backoff 1: 2 giây
  attempt 2: 200 ms
  backoff 2: 5 giây
  attempt 3: 200 ms

Tổng thời gian giữ một slot ≈ 7,6 giây.
~~~

Nếu **cả 16 consumer đồng thời** gặp lỗi, trong khoảng 7,6 giây tiếp theo không còn slot phục vụ message mới ở workload này. Con số này chưa kể I/O chậm, queueing trong JVM và thời gian transaction. Đặt prefetch=50 không tạo thêm 50 business threads; nó có thể khiến nhiều message **unacked** trong lúc consumer ngủ.

Khi chuyển sang retry queue, một lần xử lý lỗi ngắn cùng handoff có thể kết thúc sau vài trăm mili giây, cho phép thread phục vụ message khác. Đổi lại, broker đang giữ các bản cần thử lại; nếu có 100.000 message cùng chờ 10 phút, bạn phải theo dõi **dung lượng queue, quota, TTL/DLX và khả năng xử lý khi chúng quay về đồng loạt**.

### Tránh “retry storm” khi downstream phục hồi

Một outage lớn rồi retry sau cùng 30 giây có thể tạo sóng message quay trở lại cùng lúc. Hướng khắc phục:

- Exponential backoff với **jitter** ở nơi cơ chế scheduling cho phép.
- Giới hạn concurrency/throughput consumer theo downstream.
- Chia retry stage thành các bucket hợp lý hoặc dùng scheduler hỗ trợ delay per message.
- Circuit breaker ngăn yêu cầu mới làm tăng tải cho dependency đang lỗi.
- Theo dõi queue age và đặt thời hạn nghiệp vụ cho message.

Retry tốt không chỉ tránh mất message; nó còn phải **không làm sự cố lan rộng**.

## 10. Topology minh họa: work, delayed retry và terminal DLQ

Trong lab, ta dùng mô hình **application republish to retry queue** thay vì cho work queue luôn DLX sang retry queue. Lý do: quyết định retry bao nhiêu lần sẽ do ứng dụng kiểm soát, còn các lỗi vĩnh viễn hoặc exhausted đi vào **terminal DLQ**.

~~~mermaid
flowchart LR
    P["Producer"] --> WX["lab.retry.work.x<br/>direct"]
    WX -->|"work"| WQ["lab.retry.work.q"]
    WQ --> L["@RabbitListener"]
    L -->|"Transient, budget còn"| RX["lab.retry.delay.x<br/>direct"]
    RX -->|"delay"| RQ["lab.retry.delay.30s.q<br/>TTL 30s"]
    RQ -->|"TTL expired<br/>DLX về work.x"| WX
    L -->|"Permanent/exhausted<br/>reject false"| DX["lab.retry.dead.x"]
    DX -->|"dead"| DQ["lab.retry.dead.q<br/>terminal"]
~~~

**Nhìn kỹ hai luồng khác nhau:**

- Retry: consumer **publish một bản mới** sang `lab.retry.delay.x`, đợi xác nhận phù hợp rồi return để AUTO ack delivery gốc. Queue delay hết TTL mới dead-letter bản retry về work queue.
- Terminal: consumer ném `AmqpRejectAndDontRequeueException` hoặc container reject không requeue; broker dùng **DLX của work queue** đưa delivery gốc tới terminal queue.

Nếu cấu hình **work queue DLX thẳng sang retry queue** và retry queue TTL dead-letter ngược về work queue, topology **có thể chạy vô hạn**. Muốn dùng biến thể đó cần một tầng quyết định attempt budget và terminal destination; chỉ có TTL không phải retry limit.

## 11. Khai báo topology bằng Spring AMQP

Ví dụ dành cho một ứng dụng Spring Boot có `spring-boot-starter-amqp`, AMQP 0-9-1 và `RabbitAdmin`/hệ thống quản lý topology phù hợp:

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DelayedRetryTopology {

    @Bean
    DirectExchange retryWorkExchange() {
        return new DirectExchange("lab.retry.work.x", true, false);
    }

    @Bean
    DirectExchange retryDelayExchange() {
        return new DirectExchange("lab.retry.delay.x", true, false);
    }

    @Bean
    DirectExchange retryDeadExchange() {
        return new DirectExchange("lab.retry.dead.x", true, false);
    }

    @Bean
    Queue retryWorkQueue() {
        return QueueBuilder.durable("lab.retry.work.q")
                .deadLetterExchange("lab.retry.dead.x")
                .deadLetterRoutingKey("dead")
                .build();
    }

    @Bean
    Queue retryDelayQueue() {
        return QueueBuilder.durable("lab.retry.delay.30s.q")
                .ttl(30_000)
                .deadLetterExchange("lab.retry.work.x")
                .deadLetterRoutingKey("work")
                .build();
    }

    @Bean
    Queue retryTerminalQueue() {
        return QueueBuilder.durable("lab.retry.dead.q").build();
    }

    @Bean
    Binding retryWorkBinding(
            Queue retryWorkQueue, DirectExchange retryWorkExchange) {
        return BindingBuilder.bind(retryWorkQueue)
                .to(retryWorkExchange).with("work");
    }

    @Bean
    Binding retryDelayBinding(
            Queue retryDelayQueue, DirectExchange retryDelayExchange) {
        return BindingBuilder.bind(retryDelayQueue)
                .to(retryDelayExchange).with("delay");
    }

    @Bean
    Binding retryTerminalBinding(
            Queue retryTerminalQueue, DirectExchange retryDeadExchange) {
        return BindingBuilder.bind(retryTerminalQueue)
                .to(retryDeadExchange).with("dead");
    }
}
~~~

Đây là **topology lab**, không nên copy tên queue và TTL vào production mà không kiểm tra:

1. `30_000` tính bằng mili giây. Queue delay không có consumer nghiệp vụ; nó giữ message đến khi TTL hết.
2. Bản retry được **dead-letter từ delay queue**, nên header `x-death` sau khi quay về work queue có thể chứa `queue=lab.retry.delay.30s.q, reason=expired`.
3. Work queue chỉ DLX **về terminal queue**, không tự dead-letter đến retry queue.
4. Exchange/queue/binding phải được khai báo trong **đúng virtual host** và có quyền phù hợp. Nếu resource đã tồn tại khác argument/durable/type, redeclare có thể gây `PRECONDITION_FAILED`.
5. Trong production, RabbitMQ khuyến nghị quản lý TTL/DLX bằng **policies** khi cần thay đổi thường xuyên; hard-coded queue arguments không dễ sửa trên queue đã tồn tại.

## 12. Cơ chế handoff: publish retry trước, ack bản gốc sau

Giả sử consumer nhận `eventId=evt-201` và dependency đang tạm lỗi. Ứng dụng muốn gửi một bản sang delay queue rồi xác nhận bản gốc:

~~~text
1. Nhận delivery gốc M0 từ work.q.
2. Đọc retryAttempt và eventId theo hợp đồng.
3. Nếu còn budget, tạo bản M1 với retryAttempt+1.
4. Publish M1 sang delay exchange.
5. Kiểm tra publisher confirm và mandatory return.
6. Chỉ khi handoff được xác nhận, hoàn tất listener để container ack M0.
7. Nếu handoff lỗi, không ack M0 như thể đã chuyển việc thành công.
~~~

**Rủi ro không thể xóa chỉ bằng publisher confirm:**

~~~mermaid
sequenceDiagram
    participant L as Consumer
    participant P as Retry publisher
    participant B as RabbitMQ
    L->>P: Publish M1 retry copy
    P->>B: basic.publish(M1)
    B-->>P: Publisher confirm ACK
    Note over L: M1 đã được broker xác nhận
    L--xB: Mất connection trước ack M0
    Note over B: M0 có thể redeliver<br/>M1 vẫn đang chờ retry
~~~

Lúc đó hệ thống có thể có **hai bản của cùng logical event**. Đây là nhược điểm của handoff “publish copy + ack original” trên hai settlement độc lập. **Publisher confirms không phải distributed transaction** giữa publish và consumer ack, cũng không phải transaction với database nghiệp vụ. Hệ thống cần idempotency/event ID ổn định và thiết kế xử lý kết quả không chắc chắn.

### Nếu publish thất bại thì sao?

Không được return bình thường và để container ack bản gốc khi bản retry chưa chắc được broker nhận. Hãy báo lỗi để container đi theo chính sách settlement đã chọn, đồng thời cảnh báo sự cố retry infrastructure. Cũng không thể tự động `basicNack(requeue=true)` liên tục khi broker đang lỗi: việc đó tạo hot loop. Cần backoff/recovery, hạn mức thử lại và theo dõi publisher failures.

## 13. Ví dụ consumer chuyển message sang delay queue

Ví dụ sau ưu tiên **làm rõ cơ chế**, sử dụng `Message` raw để giữ nguyên body và các application headers thay vì trộn nhiều phiên bản JSON converter. Nó dành cho Spring AMQP 3.x có `CorrelationData.getFuture()` và callbacks tương ứng.

### 13.1. Cấu hình publisher confirms và returns

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
    listener:
      type: simple
      simple:
        acknowledge-mode: auto
        default-requeue-rejected: false
~~~

**Cấu hình trên là khung ví dụ, không phải bảo đảm độ bền đầy đủ.** Nếu dùng một custom `RabbitTemplate` hay `ConnectionFactory`, cần kiểm tra confirms/returns thực sự được bật. `mandatory=true` và `publisher-returns=true` giúp nhận diện message publish không route được; một broker confirm ack đơn lẻ **không chứng minh** message vào queue đích khi không có mandatory returns.

### 13.2. Listener có budget tối đa ba lần chuyển sang delay

~~~java
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Component;

@Component
public class DelayedRetryConsumer {

    private static final int MAX_DELAY_HANDOFFS = 3;
    private final RabbitTemplate rabbitTemplate;
    private final OrderProcessor orderProcessor;

    public DelayedRetryConsumer(
            RabbitTemplate rabbitTemplate, OrderProcessor orderProcessor) {
        this.rabbitTemplate = rabbitTemplate;
        this.orderProcessor = orderProcessor;
    }

    @RabbitListener(queues = "lab.retry.work.q")
    public void consume(Message source) throws Exception {
        MessageProperties original = source.getMessageProperties();
        String eventId = (String) original.getHeaders().get("event-id");
        if (eventId == null || eventId.isBlank()) {
            throw new AmqpRejectAndDontRequeueException(
                    "event-id is required");
        }

        Object raw = original.getHeaders().get("retry-attempt");
        int attempt = raw instanceof Number n ? n.intValue() : 0;
        if (attempt < 0 || attempt > MAX_DELAY_HANDOFFS) {
            throw new AmqpRejectAndDontRequeueException(
                    "Invalid retry-attempt");
        }

        try {
            orderProcessor.handle(eventId, source.getBody());
        } catch (PermanentOrderException error) {
            throw new AmqpRejectAndDontRequeueException(
                    "Permanent failure for event " + eventId, error);
        } catch (TemporaryOrderException error) {
            if (attempt >= MAX_DELAY_HANDOFFS) {
                throw new AmqpRejectAndDontRequeueException(
                        "Retry budget exhausted for " + eventId, error);
            }
            publishRetryCopy(source, eventId, attempt + 1);
            // AUTO listener return => container ack delivery gốc.
        }
    }

    private void publishRetryCopy(
            Message source, String eventId, int nextAttempt)
            throws Exception {

        MessageProperties old = source.getMessageProperties();
        MessageProperties copy = new MessageProperties();
        copy.setContentType(old.getContentType());
        if (old.getContentEncoding() != null) {
            copy.setContentEncoding(old.getContentEncoding());
        }
        copy.setDeliveryMode(MessageDeliveryMode.PERSISTENT);
        copy.setMessageId(old.getMessageId());
        copy.setCorrelationId(old.getCorrelationId());

        for (Map.Entry<String, Object> e : old.getHeaders().entrySet()) {
            if (!e.getKey().startsWith("x-")) {
                copy.setHeader(e.getKey(), e.getValue());
            }
        }
        copy.setHeader("retry-attempt", nextAttempt);
        copy.setHeader("event-id", eventId);
        Message retryMessage = new Message(
                source.getBody().clone(), copy);

        CorrelationData correlation = new CorrelationData(
                "retry:" + eventId + ":" + nextAttempt
                        + ":" + UUID.randomUUID());

        rabbitTemplate.send(
                "lab.retry.delay.x", "delay", retryMessage, correlation);

        CorrelationData.Confirm confirm =
                correlation.getFuture().get(5, TimeUnit.SECONDS);

        if (!confirm.isAck() || correlation.getReturned() != null) {
            throw new IllegalStateException(
                    "Retry copy not confirmed/routed: " + eventId);
        }
    }
}
~~~

Ở đây `OrderProcessor`, `PermanentOrderException` và `TemporaryOrderException` là **thành phần nghiệp vụ cần định nghĩa** trong ứng dụng. `CorrelationData.Confirm` và `getReturned()` phải được đối chiếu với **đúng phiên bản Spring AMQP**; đoạn code minh họa một nhánh API phù hợp, không phải mẫu drop-in cho mọi version.

**Đọc kĩ các ranh giới:**

- Header `event-id` phải do producer tạo **ổn định qua mọi lần retry**. Không tạo event ID mới khi republish cùng logical event.
- `retry-attempt` là **attempt budget của ứng dụng**, không phải `x-death.count`. `MAX_DELAY_HANDOFFS=3` nghĩa là tối đa ba lần **chuyển qua delay**, ngoài lần xử lý ban đầu.
- Đoạn code giữ application headers nhưng không cố chuyển tiếp các broker-generated `x-*` headers. Đây là quy ước minh họa; metadata thực tế cần được whitelist theo hợp đồng và kích thước headers.
- Chờ future confirm có timeout để **không ack gốc mù quáng**. Nếu confirm không chắc chắn, message gốc có thể vẫn cần được xử lý lại, vì vậy idempotency vẫn bắt buộc.
- Phần code cố tình **không gắn thêm Spring Retry advice**: lỗi publish copy và lỗi nghiệp vụ có chính sách khác nhau. Trong production, cần phân loại cách khôi phục khi retry exchange/broker gặp sự cố, tránh auto-requeue không giới hạn.
- Một publisher confirm ack vẫn chưa đồng nghĩa consumer của bản retry đã chạy. Retry queue và DLX trở lại work queue cũng phải được quan sát và kiểm thử.

### 13.3. Vì sao code này chưa phải exactly-once?

Vẫn có khoảng hở giữa **confirm bản retry** và **ack bản gốc**. Nếu ack thất lạc, cả hai bản có thể được xử lý. Nếu cần tính nhất quán cao, dùng event ID với idempotency, lưu trạng thái handoff/retry bền vững ở database, hoặc transactional outbox phù hợp. Không giải quyết bằng cách chỉ tăng publisher confirm timeout.

## 14. Điểm dừng: terminal DLQ và lỗi vĩnh viễn

Một retry system chỉ an toàn khi biết **khi nào không retry nữa**.

| Điều kiện | Quyết định | Lý do |
|---|---|---|
| Invalid JSON hoặc converter không đọc được | Reject/quarantine ngay | Cùng bytes sẽ tiếp tục thất bại |
| Schema version không hỗ trợ | Terminal DLQ, alert để nâng cấp producer/consumer | Chờ thêm thời gian không đổi khả năng giải mã |
| DB timeout 100 ms, lần đầu | Local retry ngắn có backoff | Khả năng phục hồi nhanh |
| HTTP 429, Retry-After 60s | Delayed retry có giới hạn | Giữ worker ngủ 60s không hiệu quả |
| Payment API timeout nhưng có thể đã charge | Kiểm tra trạng thái/idempotency trước retry | Không thể thử lại mù quáng |
| Hết retry budget | Terminal queue + alert/runbook | Tránh hot loop và delay loop vô hạn |
| Event đã quá hạn nghiệp vụ | Reject/quarantine hoặc compensating action | Retry thành công cũng có thể sai nghiệp vụ |

**Không nhầm “terminal DLQ” với “retry queue có TTL”.** Terminal DLQ là nơi message được giữ để điều tra/ra quyết định có kiểm soát; nó **không tự dead-letter trở lại work queue**. Một queue tên `*.dlq` nhưng cấu hình TTL và DLX quay lại work thực chất là retry queue, không phải terminal quarantine.

### Poison message và ConditionalRejectingErrorHandler

Spring AMQP có `ConditionalRejectingErrorHandler` để nhận diện một số lỗi fatal của conversion/method binding, có thể reject không requeue dù cấu hình chung muốn requeue. Nếu message fatal đã có `x-death`, tùy phiên bản và `discardFatalsWithXDeath`, handler còn có thể discard để ngắt vòng dead-letter.

Vì vậy, nếu thiết kế cần **bắt giữ mọi message lỗi để điều tra**, phải kiểm tra hành vi error handler thực tế và topology terminal, không giả định tất cả lỗi đều đi qua business listener rồi vào DLQ.

## 15. x-death có thể giúp quan sát, nhưng không phải retry budget tổng quát

Khi message bị dead-letter, RabbitMQ đặt header `x-death` (AMQP 0-9-1) với các phần tử được gộp theo **queue và reason**. Ví dụ:

~~~text
x-death:
  - queue: lab.retry.delay.30s.q
    reason: expired
    count: 2
~~~

Nó cho biết message đã **expired rồi dead-letter từ delay queue** hai lần theo lịch sử broker nhìn thấy. Nhưng:

- Local Spring Retry **không** tự tăng `x-death`.
- `basicNack(requeue=true)` trực tiếp **không** tạo dead-letter history chỉ vì requeue.
- Republish một bản copy mới có thể không giữ lịch sử broker của bản trước; RabbitMQ 4.0+ không chấp nhận client tự giả mạo `x-death` như metadata do broker quản lý.
- `x-death[0].count` chỉ mô tả **một queue/reason**, không phải tổng số business attempts.
- Replay thủ công từ DLQ phải có chính sách **reset hay giữ retry budget** được quyết định tường minh.

Trong mô hình của mục 13, `retry-attempt` do ứng dụng đặt giữ vai trò đếm số lần chuyển sang delay, còn `x-death` là dữ liệu quan sát broker. Cần bảo vệ các headers do producer không tin cậy gửi; dùng định danh event đáng tin và kiểm soát quyền publish/consume trong RabbitMQ.

## 16. TTL/DLX hay delayed exchange/quorum delayed retry?

Có nhiều cơ chế tạo độ trễ; chúng không hoàn toàn tương đương:

| Cơ chế | Cách hoạt động | Ưu điểm | Giới hạn |
|---|---|---|---|
| **TTL + DLX retry queue** | Message chờ trong queue; khi TTL hết được dead-letter về work exchange | Không cần plugin riêng; dễ minh họa | Thêm topology, dead-letter overhead, tính toán attempt budget |
| **Các delay buckets cố định** | `retry.10s.q`, `retry.1m.q`, `retry.5m.q` | Dễ kiểm soát giai đoạn và backoff | Nhiều queues/bindings, cần điều phối stage |
| **Per-message TTL trong một queue** | Mỗi message có expiration khác nhau | Tùy biến delay theo message | Có thể gặp **head-of-line blocking**: expired message nằm sau message chưa expired |
| **Delayed message exchange plugin** | Exchange giữ message đến thời điểm được phép route | Có thể hỗ trợ delay theo message | Phụ thuộc plugin, version và đặc điểm durability/operability; không sẵn có ở mọi broker |
| **Quorum delayed retry** | Tính năng broker trong các RabbitMQ versions hỗ trợ | Giảm nhu cầu tạo DLX loop, có semantics broker riêng | Phải xác minh queue type/version, cấu hình delay và delivery limit |
| **External durable scheduler/outbox** | Lịch retry nằm trong DB/service điều phối | Kiểm soát chính sách và audit linh hoạt | Phức tạp vận hành, cần giữ data consistency |

RabbitMQ có cơ chế **quorum queue delayed retry** trong các nhánh mới; với các hệ thống chạy RabbitMQ 4.3+ hãy kiểm tra tài liệu quorum queues/delayed retries trước khi tiếp tục xây vòng TTL/DLX mới. Không mặc định cluster đang chạy hỗ trợ tính năng này, hoặc classic queue có cùng hành vi.

### Head-of-line blocking và TTL

Nếu một queue chứa:

~~~text
M1: TTL = 5 phút, đến trước
M2: TTL = 10 giây, đến sau
~~~

Trên một số mô hình dùng **per-message TTL**, M2 đã hết hạn vẫn có thể chưa được dead-letter vì đứng sau M1 chưa hết hạn. Do đó, **một queue chứa nhiều TTL per-message không phải bộ lập lịch chính xác đến từng giây**. Dùng các retry buckets có **queue-level TTL cố định** giúp tránh kiểu xếp hàng này cho một số workload, hoặc chọn cơ chế scheduling phù hợp.

TTL hết hạn không phải lời hứa message sẽ được giao chính xác tại thời điểm đó. Broker load, queue semantics, dead-lettering và downstream backlog có thể làm thời gian thực tế dài hơn.

## 17. Thứ tự xử lý và khả năng idempotent

Khi chuyển message M2 sang delay queue vì lỗi, work queue có thể tiếp tục xử lý M3, M4 trước khi M2 quay về. Vì vậy delayed retry thường **thay đổi thứ tự hoàn thành** so với thứ tự publish ban đầu.

~~~text
Publish:    M1 → M2 → M3
Consume:    M1 ✔, M2 lỗi → retry 30s, M3 ✔
Sau 30s:   M2 quay lại và xử lý ✔
Completion: M1 → M3 → M2
~~~

Nếu mỗi event độc lập, điều này có thể chấp nhận được và giúp throughput tốt hơn. Nếu M3 **bắt buộc phụ thuộc vào M2**, không nên chỉ thay local retry bằng delayed retry rồi bỏ qua ordering constraint.

Các lựa chọn cần cân nhắc:

- Gắn sequence number cho từng aggregate và có logic trì hoãn sự kiện đến sớm.
- Phân vùng message theo aggregate key nếu workload và topology hỗ trợ.
- Xử lý theo **state machine** idempotent, không dựa hoàn toàn vào arrival order.
- Thiết kế khóa hoặc queue riêng cho những nhóm thực sự cần thứ tự mạnh, chấp nhận throughput thấp hơn.

**Idempotency là bắt buộc cho cả hai cách retry.** Ngay cả local retry cũng có thể làm side effect chạy hai lần nếu lần đầu thành công một phần rồi ném exception. Sau reconnect, broker còn có thể redeliver message chưa ack. Event ID ổn định và unique constraint trong transaction nghiệp vụ giúp giảm hậu quả duplicate.

## 18. Case study: chọn retry theo lỗi thực tế

### 18.1. Optimistic lock conflict khi cập nhật inventory

**Bối cảnh:** hai consumer cập nhật cùng SKU, một giao dịch bị optimistic lock conflict. Tài nguyên thường giải phóng rất nhanh.

**Chọn:** local retry 2–3 attempts, backoff ngắn (ví dụ 50–200 ms), đọc lại state trước khi thử. Nếu xung đột liên tục, terminal handling hoặc hàng đợi điều phối có kiểm soát.

**Không làm:** retry vô hạn trong transaction cũ đã bị rollback; phải tạo phạm vi transaction phù hợp cho attempt mới.

### 18.2. API gửi email trả HTTP 429, Retry-After 90 giây

**Bối cảnh:** retry sớm chắc chắn bị rate limit.

**Chọn:** delayed retry khoảng thời gian yêu cầu, cân đối jitter và giới hạn tổng attempts/tuổi message. Giải phóng listener slot để xử lý những event khác.

**Không làm:** giữ 100 listener threads ngủ 90 giây hoặc broker `basicNack(requeue=true)` liên tục.

### 18.3. JSON payload có schema version không hỗ trợ

**Bối cảnh:** code consumer không thể deserialize hoặc validate payload hiện tại.

**Chọn:** terminal reject/quarantine với metadata để điều tra producer/schema; sửa và replay có kiểm soát.

**Không làm:** local retry hoặc vòng TTL hàng giờ — cùng bytes, cùng converter thường vẫn lỗi.

### 18.4. Payment request timeout, kết quả không rõ

**Bối cảnh:** payment gateway có thể đã thu tiền, nhưng response bị mất.

**Chọn:** trước khi retry cần query trạng thái bằng idempotency key/transaction reference; nếu phải trì hoãn để chờ đối tác cập nhật, dùng delayed retry có giới hạn.

**Không làm:** thực hiện lại một charge mới ngay theo giả định “timeout nghĩa là chưa charge”.

### 18.5. Database outage trong 15 phút

**Bối cảnh:** mọi consumer cùng ném connection exception; 30.000 message đang chờ.

**Chọn:** circuit breaker, stop/pause consumption nếu phù hợp, delayed retry/backpressure với rate limit sau phục hồi. Giám sát DLQ và tuổi message.

**Không làm:** để `defaultRequeueRejected=true` tạo hot loop hay giữ toàn bộ worker chờ backoff dài.

## 19. Ma trận kiểm thử bắt buộc

| Test | Cấu hình/thao tác | Kết quả cần kiểm chứng |
|---|---|---|
| A | Local retry, lỗi lần 1 rồi thành công lần 2 | Method được gọi 2 lần, delivery ack; không tự tăng `x-death` |
| B | Local retry, thất bại suốt max attempts | Recoverer cuối chạy; message đi terminal theo DLX nếu hợp lệ |
| C | Local retry với thread pool gần đầy | Handler khác bị chờ trong lúc backoff; đo active threads, ready/unacked |
| D | Delayed retry, lỗi transient, budget còn | Publish copy có confirm/route, delivery gốc được ack, copy ở delay queue |
| E | Delay TTL hết | Copy được dead-letter về work exchange rồi được consume lại |
| F | Delayed retry hết budget | Reject không requeue và terminal DLQ nhận message |
| G | Retry exchange không tồn tại/binding sai | Handoff thất bại; không ack gốc như thể đã retry xong |
| H | Broker mất kết nối giữa confirm copy và ack gốc | Có thể duplicate; consumer idempotency ngăn side effect trùng |
| I | JSON hỏng | Không retry vô hạn; error handler/quarantine xử lý theo policy |
| J | `basicNack(requeue=true)` | Không có delay cam kết, có thể hot loop |
| K | Hai message có thứ tự phụ thuộc | Retry M2 có thể cho M3 hoàn thành trước; thiết kế ordering vẫn an toàn |
| L | DLX/TTL path sai | Alert/metrics phát hiện message không quay về work hoặc không tới terminal |

### Cách tổ chức test

1. Dùng broker RabbitMQ test và queue/exchange riêng, không dùng production.
2. Mỗi kịch bản có **eventId** riêng và queue sạch; chỉ bật những consumer cần thiết.
3. Với local retry, dùng counter/latch để xác minh **số business attempts** và backoff thực tế, không chỉ assert exception.
4. Với delayed queue, quan sát **message ở retry queue**, thời điểm TTL, callback confirm/return và lần xử lý sau.
5. Dùng Awaitility/latch hoặc cơ chế chờ có timeout để test bất đồng bộ, tránh assert ngay sau `convertAndSend`.
6. Có test queue terminal không tự quay về work, đồng thời thử broker restart/mất kết nối.
7. Kiểm tra số message unacked, DLQ depth, broker logs và tác động database để xác nhận end-to-end.

Không chạy hot-loop stress test trên broker chung. Với `defaultRequeueRejected=true`, phải có cơ chế dừng listener test sau một số attempts hoặc thời gian cố định.

## 20. Quan sát vận hành và cảnh báo

Đừng chỉ đo “retry succeeded”. Dashboard cần phân biệt cả **độ trễ retry** và **tài nguyên bị giữ**:

| Metric | Local retry | Delayed retry |
|---|---|---|
| Handler attempts / message | Counter Spring Retry hoặc business metric | Application `retry-attempt` và từng lần consume |
| Listener active threads | Tăng khi retry/backoff | Thường giảm sau handoff |
| `messages_unacknowledged` | Delivery có thể giữ unacked trong toàn bộ attempt | Delivery gốc được settled sau handoff |
| Queue ready backlog | Có thể tăng vì worker bị chiếm | Work queue có thể tiếp tục chảy, retry queue tích message |
| Queue retry depth/oldest age | Không có queue riêng | Quan trọng để thấy lịch chờ |
| Publisher confirm/return errors | Không phải thao tác bắt buộc cho local retries | Rất quan trọng khi publish retry copy |
| DLQ/quarantine count | Sau recoverer/reject cuối | Sau hết attempt budget, permanent errors |
| p95/p99 business latency | Bao gồm cả backoff tại chỗ | End-to-end bao gồm thời gian ở retry queue |

**Alert hữu ích:** retry queue oldest age vượt SLA; work queue backlog tăng khi local retry chiếm hết consumer slots; không có publisher confirms; returns tăng do binding sai; terminal DLQ tăng theo exception type; số event bị retry nhiều lần mà không có business progress.

Logs nên gắn `eventId`, `retry-attempt`, loại lỗi, scheduled delay, actual delay, exchange/routing key, confirm outcome và DLQ decision. Không log body chứa dữ liệu cá nhân hay token.

## 21. Lỗi thường gặp và cách sửa

| Lỗi thiết kế | Hậu quả | Cách sửa |
|---|---|---|
| Dùng `Thread.sleep(60_000)` trong listener để “delay” | Worker/channels bị giữ, backlog tăng | Chuyển sang delayed queue/scheduler |
| `basicNack(requeue=true)` để chờ 30 giây | Broker có thể giao lại ngay | Dùng broker delay mechanism hoặc queue TTL |
| `defaultRequeueRejected=true` mà không giới hạn | Poison hot loop | Classify + finite retry + terminal |
| Work DLX ↔ retry TTL tạo vòng vô hạn | Message lỗi quay lại mãi | Có attempt budget và terminal route |
| Publish copy rồi return mà không confirm | Có thể ack gốc dù copy không đến nơi | Confirms/returns và kiểm soát handoff |
| Tin publisher ack là copy đã vào queue kỳ vọng | Unroutable vẫn có thể được confirm | Mandatory returns và binding tests |
| Confirm copy rồi nghĩ không bao giờ duplicate | Ack gốc có thể thất lạc | Stable event ID, idempotency |
| Dùng `x-death[0].count` làm tổng retries | Đếm sai requeue/local/republish | Attempt metadata có hợp đồng riêng |
| Dùng cùng retry policy cho JSON lỗi và HTTP 503 | Tốn tài nguyên, delayed queue chứa poison | Phân loại permanent/transient |
| Retry M2 nhưng xử lý M3 như không phụ thuộc | Sai thứ tự nghiệp vụ | Ordering/state machine/aggregate sequencing |
| Quên quan sát retry queue oldest age | Message trì hoãn mãi không ai biết | Metrics, SLA, dead-letter alerts |
| Bật hai lớp retry cùng lúc không kiểm soát | Tăng số attempts ngoài ý muốn | Xác định thứ tự, budget và ownership |

## 22. Bài tập tự kiểm tra

### Bài 1 — Local retry hay delayed retry?

Một API thường trả lỗi 503 và phục hồi trong 200 ms; listener concurrency=20, lưu lượng thấp. Nên bắt đầu bằng cách nào?

**Đáp án gợi ý:** local retry vài lần với backoff ngắn, đo tổng thời gian giữ thread và tỷ lệ lỗi; hết attempts thì terminal/delayed stage có budget.

### Bài 2 — Retry-After 120 giây

Một service trả `429` kèm `Retry-After: 120`. Có nên giữ listener thread `sleep(120_000)`?

**Đáp án:** không nên khi concurrency/tài nguyên có giá trị. Chọn delayed retry hoặc scheduler bền vững với thời gian phù hợp, backpressure và giới hạn attempts.

### Bài 3 — Tại sao nack không phải delay?

Listener ném `ImmediateRequeueAmqpException`. Có chắc message được giao lại sau ít nhất một giây?

**Đáp án:** không. Đây là yêu cầu requeue; broker có thể giao lại ngay, không có lịch backoff mặc định.

### Bài 4 — Local max attempts

`maxAttempts(3)` với `backOffOptions(300, 2.0, 2000)` thường cho bao nhiêu lần gọi handler nếu luôn thất bại, và bao nhiêu khoảng backoff?

**Đáp án:** tổng cộng tối đa 3 attempts, hai khoảng chờ minh họa 300 ms và 600 ms, chưa tính thời gian business method và version-specific config.

### Bài 5 — Handoff không atomic

Consumer đã nhận confirm cho retry copy nhưng mất connection trước khi ack bản gốc. Hãy nêu rủi ro.

**Đáp án:** bản gốc có thể redeliver và bản retry cũng còn, dẫn đến duplicate. Cần event ID và idempotent consumer; confirms không tạo transaction nguyên tử.

### Bài 6 — x-death và attempts

Message bị Spring Retry gọi listener 3 lần trong cùng delivery rồi được ack. Có chắc `x-death.count=3`?

**Đáp án:** không. Không có dead-letter event chỉ vì local retry.

### Bài 7 — Terminal queue

Một queue `orders.dlq` có TTL và dead-letter trở về work queue. Có thật là DLQ cuối cùng không?

**Đáp án:** không, đó là một retry queue theo thời gian. Terminal queue không tự động đưa lại work khi chưa có replay được phê duyệt.

### Bài 8 — Thứ tự xử lý

M1, M2, M3 được publish theo thứ tự, M2 được delayed retry 30 giây. Có thể M3 hoàn tất trước M2 không?

**Đáp án:** có. Nếu M3 phụ thuộc M2, cần logic sequencing hoặc thiết kế thứ tự riêng, không chỉ dựa vào queue FIFO.

### Bài 9 — Khi nào tránh mọi retry?

Consumer gặp unsupported schema version. Tăng số lần local retry hay TTL delay có cải thiện không?

**Đáp án:** thường không; lỗi vĩnh viễn cần terminal/quarantine, sửa schema/code hoặc replay có kiểm soát sau khi khắc phục.

## 23. Checklist trước production

- [ ] Phân loại exception thành **permanent, transient, unknown outcome**; không retry mọi lỗi như nhau.
- [ ] Đặt retry budget và business deadline cụ thể; khi exhausted có terminal DLQ/quarantine.
- [ ] Với local retry, tính số consumer slots bị chiếm bởi attempts/backoff và prefetch unacked.
- [ ] Với DMLC, nhớ listener callback chạy trên RabbitMQ client dispatch thread; không ngủ dài tùy tiện.
- [ ] Dùng Spring Retry với `maxAttempts`, backoff, recoverer và exception classifier đúng phiên bản.
- [ ] Không cấu hình local retry advice trùng lặp với Boot retry mà không biết tổng attempts.
- [ ] Với delayed retry, xác nhận topology work/delay/terminal rõ ràng và không có vòng TTL/DLX vô hạn.
- [ ] Khi publish retry copy, bật confirms + returns/mandatory theo đường publish; không ack bản gốc khi handoff không chắc chắn.
- [ ] Chấp nhận khoảng hở publish-confirm/consumer-ack và có **event ID + idempotency**.
- [ ] Kiểm tra schema/headers khi copy message; không tự ghi broker-managed `x-death`.
- [ ] Đừng nhầm `basicNack(requeue=true)` với delayed retry.
- [ ] Cân nhắc queue-level TTL buckets, per-message TTL head-of-line và các tính năng delay của broker đúng version.
- [ ] Có backpressure/jitter để tránh retry storm khi downstream phục hồi.
- [ ] Nếu nghiệp vụ phụ thuộc thứ tự, thiết kế sequencing/aggregate key rõ ràng trước khi đẩy message sang delay.
- [ ] Theo dõi retry attempt, active threads, ready/unacked, delay queue oldest age, publish confirms/returns và DLQ.
- [ ] Test RabbitMQ thật: thành công sau retry, exhausted, poison JSON, thiếu binding, mất connection, duplicate, restart và replay.
- [ ] Nếu tự quản lý topology, kiểm tra quyền, vhost, queue type, TTL/DLX policies và durability.

## 24. Nguồn tài liệu chính thức

Các API và cơ chế delay có thể thay đổi theo **Spring AMQP, Spring Boot và RabbitMQ version**. Hãy đối chiếu với đúng phiên bản ứng dụng đang dùng:

- [Spring AMQP — Resilience: Recovering from Errors and Broker Failures](https://docs.spring.io/spring-amqp/reference/amqp/resilience-recovering-from-errors-and-broker-failures.html): local retry, stateful/stateless, `RetryInterceptorBuilder`, recoverers và error classification.
- [Spring AMQP 3.2 — Resilience](https://docs.spring.io/spring-amqp/reference/3.2/amqp/resilience-recovering-from-errors-and-broker-failures.html): mã mẫu Spring AMQP nhánh 3.x, retry qua broker và các recoverers.
- [Spring AMQP — Listener Container Attributes](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html): `AcknowledgeMode`, `defaultRequeueRejected`, `prefetch`, concurrency.
- [Spring AMQP — Publisher Confirms and Returns](https://docs.spring.io/spring-amqp/reference/amqp/template.html): `CorrelationData`, mandatory returns và kết quả publish.
- [Spring Boot — AMQP](https://docs.spring.io/spring-boot/reference/messaging/amqp.html): auto-configuration của listener factories và template.
- [RabbitMQ — Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx): DLX, retry cycles, x-death và delayed retries.
- [RabbitMQ — Time-To-Live and Expiration](https://www.rabbitmq.com/docs/ttl): queue-level TTL, per-message TTL và head-of-line.
- [RabbitMQ — Quorum Queues](https://www.rabbitmq.com/docs/quorum-queues): delivery limits, poison messages và các khả năng delayed retry theo version.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): giới hạn của ack/nack, redelivery và publisher confirms.

**Ghi nhớ:** **Retry tại chỗ** tốt cho lỗi có khả năng tự hết nhanh và chỉ cần vài lần thử; nó đơn giản nhưng **giữ listener thread và thường giữ delivery unacked**. **Queue trì hoãn** phù hợp khi cần chờ dài, kiểm soát lịch retry và nhường worker cho message khác; nó đòi hỏi **handoff an toàn, giới hạn attempts, idempotency và terminal DLQ**. Cả hai phải có điểm dừng — một `requeue=true` hoặc một vòng TTL/DLX không có budget có thể biến lỗi tạm thời thành sự cố kéo dài của toàn hệ thống.
