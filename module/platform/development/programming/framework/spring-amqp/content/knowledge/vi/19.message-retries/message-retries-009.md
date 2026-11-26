# RejectAndDontRequeueRecoverer và RepublishMessageRecoverer

Một ứng dụng Spring AMQP đang tiêu thụ sự kiện đặt hàng từ RabbitMQ. Listener gọi dịch vụ thanh toán nhưng gặp timeout. Sau khi thử lại nhiều lần mà vẫn lỗi, hệ thống phải quyết định **làm gì với message thất bại**. Nếu không có kết thúc rõ ràng, message có thể bị giao lại vô hạn, chiếm consumer và gây bão log.

Trong Spring AMQP, hai `MessageRecoverer` thường dùng để xử lý **sau khi retry đã hết lượt**:

- **`RejectAndDontRequeueRecoverer`**: phát tín hiệu `AmqpRejectAndDontRequeueException`, khiến container **reject/nack không requeue**. Nếu queue nguồn có dead-letter exchange (DLX) hợp lệ, **RabbitMQ broker** chuyển message sang DLQ.
- **`RepublishMessageRecoverer`**: ứng dụng **publish một bản message lỗi** tới error exchange/routing key được chỉ định, kèm metadata về exception và nguồn message. Nếu recovery trở về bình thường ở chế độ container `AUTO`, delivery gốc **được container ACK**.

Hai phương án giải quyết cùng tình huống hết retry nhưng **khác ai chuyển message lỗi, metadata được giữ lại, thời điểm ACK và rủi ro khi đường chuyển lỗi thất bại**. Bài thuộc chương **Thử lại thông điệp** của module **SPRING_AMQP**, kết hợp `RabbitTemplate`, `@RabbitListener`, exchange, queue, binding, acknowledgment, publisher confirms, retry, dead-letter, giao dịch và quan sát hệ thống để xây dựng xử lý bất đồng bộ đáng tin cậy.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xác định lúc nào `MessageRecoverer` được gọi trong chuỗi Spring Retry.
2. Phân biệt `RejectAndDontRequeueRecoverer` và `RepublishMessageRecoverer` đến tận queue lỗi.
3. Cấu hình `RetryInterceptorBuilder.stateless()` với `maxAttempts` và backoff.
4. Gắn retry advice và recoverer lên đúng `SimpleRabbitListenerContainerFactory`.
5. Phân biệt `x-death` của broker DLX với `x-exception-*` và `x-original-*` của republish.
6. Giải thích tại sao republish + ACK không nguyên tử và khi nào cần publisher confirms/returns.
7. Thử nghiệm cùng một `@RabbitListener` ở hai chế độ recoverer và quan sát RabbitMQ Management.

## 2. Recoverer nằm ở đâu trong đường xử lý?

~~~mermaid
flowchart TD
    P["RabbitTemplate producer"] --> E["Exchange + binding"]
    E --> Q["Work queue"]
    Q --> C["Listener container"]
    C --> R["Retry interceptor"]
    R --> L["@RabbitListener"]
    L -->|"Thành công"| A["Container ACK"]
    L -->|"Còn retry"| B["Backoff và gọi handler lại"]
    B --> L
    L -->|"Hết attempts, vẫn lỗi"| M{"MessageRecoverer"}
    M -->|"RejectAndDontRequeueRecoverer"| RJ["Reject requeue=false"]
    RJ --> DX["Broker DLX → DLQ nếu có binding"]
    M -->|"RepublishMessageRecoverer"| RP["RabbitTemplate publish error message"]
    RP -->|"Recovery thành công"| OA["Container ACK original"]
    RP -->|"Recovery thất bại"| U["Container xử lý exception tiếp<br/>cần chính sách an toàn"]
~~~

**Retry interceptor** điều khiển số lần gọi handler và khoảng chờ. **Recoverer** chỉ xử lý khi các lần thử đều thất bại và retry kết thúc; nó không tự quyết định `maxAttempts` hay backoff.

| Thành phần | Trách nhiệm | Ví dụ |
|---|---|---|
| `@RabbitListener` | Xử lý message nghiệp vụ | Lưu đơn, gọi API |
| `RetryOperationsInterceptor` | Gọi lại listener sau exception, theo retry policy | Ba attempts và backoff |
| `MessageRecoverer` | Quyết định kết thúc sau retry exhausted | Reject hoặc republish |
| `ConditionalRejectingErrorHandler` | Phân loại lỗi tầng container, gồm lỗi pre-listener | Conversion fatal không requeue |
| `RabbitTemplate` | Publish event hoặc message lỗi | Publish tới error exchange |
| `basicAck/basicReject/basicNack` | Xác nhận/từ chối delivery trên consumer channel | ACK, requeue hoặc dead-letter |
| DLX / DLQ | Broker xử lý message bị dead-letter | Work queue → DLX → DLQ |

**Không phải mọi exception đều chắc chắn qua recoverer.** Lỗi conversion/argument binding trước khi phương thức `@RabbitListener` chạy có thể đi qua container error handler. Exception đặc biệt và vị trí advice chain cũng ảnh hưởng đường xử lý. Bài tập trung vào lỗi nghiệp vụ ném **trong listener**.

## 3. `maxAttempts` và stateless retry

Trong Spring Retry, `maxAttempts(3)` nghĩa là **tối đa ba lần gọi handler tổng cộng** (lần đầu và tối đa hai lần thử lại), không phải ba lần retry cộng lần đầu.

~~~text
Một lần broker giao deliveryTag=17:
  attempt 1 → listener ném lỗi
  backoff
  attempt 2 → listener ném lỗi
  backoff
  attempt 3 → listener ném lỗi
  MessageRecoverer(message, lastException)
~~~

Với **stateless retry**, chuỗi attempts diễn ra bên trong một lần xử lý delivery ở ứng dụng. Broker **không phải gửi thêm một `basic.deliver` cho mỗi attempt**:

- `deliveryTag` thường không đổi giữa các local attempts.
- `redelivered` có thể vẫn là `false` suốt ba lần gọi listener.
- `x-death` không đếm số local attempts; nó liên quan **dead-letter tại broker**.
- Chỉ khi kết thúc bằng reject không requeue, broker mới có thể chuyển delivery sang DLX.

**Stateful retry** có cơ chế giữ trạng thái giữa các lần xử lý/giao lại tùy cách cấu hình và yêu cầu nhận diện message. Không áp dụng máy móc nhận xét về stateless cho stateful retry hoặc broker-side retry qua TTL/DLX.

| Cơ chế retry | Lặp ở đâu? | Có delay tự động? | Dấu hiệu |
|---|---|---|---|
| Spring Retry stateless | Bên trong lời gọi listener | Có, nếu cấu hình backoff | Nhiều log attempts trong một delivery |
| `basicNack(..., requeue=true)` | Broker đưa message về queue | Không tự tạo backoff hữu hạn | Có thể redeliver liên tục |
| Retry qua TTL/DLX hoặc delayed exchange | Broker/topology | Có thể thiết kế delay | Có lần enqueue/dead-letter mới |

Không kết hợp stateless retry hữu hạn với `requeue=true` vô hạn; như vậy cùng message vẫn có thể quay vòng mãi.

## 4. `RejectAndDontRequeueRecoverer`: broker dead-letter

`RejectAndDontRequeueRecoverer` nằm trong package `org.springframework.amqp.rabbit.retry`. Khi được gọi sau khi retry exhausted, nó ghi nhận lỗi và ném `AmqpRejectAndDontRequeueException`. Container xử lý bằng đường **reject hoặc NACK với requeue=false**, thay vì đưa message về work queue ngay.

~~~text
Work queue
  → listener thất bại ở attempt 1/2/3
  → RejectAndDontRequeueRecoverer
  → AmqpRejectAndDontRequeueException
  → Consumer reject/nack (requeue=false)
  → Broker dead-letter qua DLX nếu được cấu hình
  → DLQ nếu binding/routing hợp lệ
~~~

**Recoverer này không dùng `RabbitTemplate` để tạo bản copy message và không tự tạo DLQ.** Việc chuyển từ work queue sang DLQ do RabbitMQ thực hiện.

### Điều kiện để vào được DLQ

1. Queue nguồn có DLX được cấu hình đúng (queue arguments hoặc policy phù hợp).
2. DLX tồn tại, binding và routing key đưa message tới DLQ.
3. Queue đích tồn tại và broker có thể thực hiện dead-letter.
4. Message đi theo đường **không requeue**, chứ không phải `requeue=true`.

Nếu không có đường dead-letter hợp lệ, message bị reject không requeue **có thể bị loại**, không được giữ tự động trong một queue bí mật nào.

### Header `x-death`

Message được broker dead-letter thường có header **`x-death`** mô tả lịch sử dead-letter (chẳng hạn reason `rejected`, nguồn queue và dữ liệu liên quan). Nó **không phải số lần `@RabbitListener` được Spring Retry gọi**. Ba attempts nội bộ rồi broker dead-letter một lần không tự biến thành ba `x-death` events.

### Khi nào chọn?

Phù hợp khi queue nguồn đã có cơ chế DLX/DLQ do broker quản lý và bạn muốn **sau retry hết lượt, bàn giao message lỗi cho broker**. Ưu điểm là đường chuyển lỗi đơn giản ở ứng dụng; để điều tra exception chi tiết, cần bổ sung log/tracing hoặc hệ thống xử lý lỗi phù hợp, vì DLX chủ yếu lưu metadata broker.

## 5. `RepublishMessageRecoverer`: ứng dụng phát bản message lỗi

`RepublishMessageRecoverer` cũng thuộc `org.springframework.amqp.rabbit.retry`, dùng `RabbitOperations` (thường là `RabbitTemplate`) để **republish message** sang error exchange và routing key được chọn, bổ sung thông tin exception.

~~~text
Work queue
  → listener thất bại ở attempt 1/2/3
  → RepublishMessageRecoverer
  → RabbitTemplate.send(errorExchange, errorRoutingKey, message)
  → Error exchange → Error queue
  → Recoverer hoàn tất bình thường
  → Container AUTO ACK delivery gốc
~~~

Khác với broker DLX:

- Queue nguồn **không cần DLX** để dùng đường republish.
- Error exchange, binding, error queue và quyền publish phải hợp lệ.
- Bản message mới có thể kèm headers giải thích exception và nguồn publication.
- Khi recoverer trả về thành công trong mô hình `AcknowledgeMode.AUTO`, delivery gốc được container **ACK**, không phải reject để broker dead-letter.
- Đây là **một lần publication mới**, không phải một transaction nguyên tử với ACK message gốc.

### Metadata thường thấy

| Header | Vai trò |
|---|---|
| `x-exception-message` | Thông điệp lỗi cuối dẫn đến recovery |
| `x-exception-stacktrace` | Stack trace phục vụ điều tra |
| `x-original-exchange` | Exchange gốc theo metadata của delivery |
| `x-original-routingKey` | Routing key gốc theo metadata của delivery |

Header cụ thể có thể thay đổi theo Spring AMQP version/cách cấu hình. **Đừng tự suy rằng `x-death` sẽ xuất hiện** trong message do ứng dụng republish: broker gắn `x-death` theo đường dead-letter, không phải mọi lần publish vào một error queue.

Stack trace và exception messages có thể chứa dữ liệu nhạy cảm, đồng thời làm message rất lớn; hạn chế quyền đọc queue lỗi, retention, logging và kích thước metadata.

### Khi nào chọn?

Phù hợp khi cần **error exchange riêng, routing theo loại lỗi, hoặc metadata exception phục vụ điều tra**. Đổi lại, ứng dụng phải biết lần republish **có thực sự được broker xác nhận và định tuyến** hay không; nếu không kiểm tra, original delivery có thể đã ACK mà error queue chưa giữ được bản lỗi.

## 6. So sánh hai recoverer

| Tiêu chí | `RejectAndDontRequeueRecoverer` | `RepublishMessageRecoverer` |
|---|---|---|
| Sau retry exhausted | Ném exception yêu cầu reject không requeue | Tự publish bản message lỗi |
| Ai vận chuyển bản lỗi? | **RabbitMQ broker** qua DLX | **Ứng dụng** qua `RabbitTemplate` |
| Queue nguồn cần DLX? | Có nếu muốn giữ lỗi trong DLQ | Không bắt buộc |
| Đường tới queue lỗi | DLX + binding | Error exchange + binding |
| Kết thúc delivery gốc | Reject/NACK không requeue | Container ACK khi recovery trả về bình thường trong `AUTO` |
| Metadata điển hình | `x-death` do broker thêm | `x-exception-*`, `x-original-*` |
| Nguy cơ chính | DLX/binding sai, dead-letter không tới queue đích | Republish thất bại/unroutable, chưa confirm, bản lỗi trùng |
| Cần giám sát | Reject/DLQ, broker dead-letter | Publisher confirms/returns, error queue, retry ID |

**Không thể kết luận recoverer nào an toàn hơn chỉ từ API**. Mức độ bảo đảm còn phụ thuộc broker queue type, durability, routing, publisher confirms, timeout, idempotency và vận hành.

## 7. Lab với Spring Boot và RabbitMQ

Các ví dụ nhắm tới **Java 17+, Spring Boot 3.x, Spring AMQP 3.x và Spring Retry tương thích**. Với các dòng mới hơn, chọn API theo version thực tế thay vì trộn dependency từ nhiều thế hệ.

### 7.1. Broker local

~~~bash
docker run -d --name rabbitmq-recoverer-lab -p 127.0.0.1:5672:5672 -p 127.0.0.1:15672:15672 -e RABBITMQ_DEFAULT_USER=lab -e RABBITMQ_DEFAULT_PASS=lab123456 rabbitmq:4-management
~~~

Management thường ở `http://localhost:15672`, tài khoản `lab/lab123456`. Chỉ dùng thông tin này trong lab local; production cần TLS, secret management và quyền vhost phù hợp. Nếu máy đã có RabbitMQ trên các cổng đó, dùng broker hiện tại hoặc đổi port mapping.

### 7.2. Maven dependencies

Trong ứng dụng Spring Boot có parent/BOM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-amqp</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.retry</groupId>
        <artifactId>spring-retry</artifactId>
    </dependency>
</dependencies>
~~~

Không tự chọn một phiên bản `spring-rabbit`/`spring-retry` mâu thuẫn với BOM. `spring-retry` cung cấp hạ tầng retry interceptor được dùng ở dưới.

### 7.3. `application.yml`: chọn một recoverer

~~~yaml
server:
  port: 8080

demo:
  retry:
    recoverer: reject # đổi thành republish để thử hướng thứ hai

spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: lab
    password: lab123456
    listener:
      type: simple
      simple:
        concurrency: 1
        max-concurrency: 1
        prefetch: 1
        acknowledge-mode: auto
        default-requeue-rejected: true
~~~

`default-requeue-rejected: true` chỉ để làm nổi bật hành vi recoverer trong lab. **Không dùng giá trị này như toàn bộ retry policy cho production**, vì những exception không được interceptor/recoverer xử lý có thể gây requeue nóng. Cần phân loại exception và retry hữu hạn.

**Không bật thêm** `spring.rabbitmq.listener.simple.retry.enabled=true` nếu bạn đã gắn interceptor bằng Java ở phần sau: hai lớp retry có thể chồng nhau và làm tổng attempts khác dự tính.

## 8. Topology: DLQ của broker và error queue của ứng dụng

Ta tạo hai đường lỗi để so sánh:

~~~mermaid
flowchart TD
    P["RabbitTemplate"] --> EX["demo.retry.events"]
    EX -->|"order.created"| W["demo.retry.work"]
    W --> L["@RabbitListener + 3 attempts"]
    L -->|"thành công"| A["ACK"]
    L -->|"reject recoverer"| RJ["Reject requeue=false"]
    RJ --> DX["demo.retry.dlx"]
    DX -->|"order.dead"| DLQ["demo.retry.dlq"]
    L -->|"republish recoverer"| RP["RabbitTemplate republish"]
    RP --> ER["demo.retry.errors"]
    ER -->|"order.failed"| EQ["demo.retry.error.queue"]
    RP -->|"recovery thành công"| AO["ACK original delivery"]
~~~

**Đây là hai chế độ thay thế nhau**. Một message lỗi không tự đi vào cả hai queue chỉ vì cả hai queue tồn tại.

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RetryLabTopology {

    @Bean
    DirectExchange retryEvents() {
        return new DirectExchange("demo.retry.events", true, false);
    }

    @Bean
    DirectExchange retryDlx() {
        return new DirectExchange("demo.retry.dlx", true, false);
    }

    @Bean
    DirectExchange retryErrors() {
        return new DirectExchange("demo.retry.errors", true, false);
    }

    @Bean
    Queue retryWorkQueue() {
        return QueueBuilder.durable("demo.retry.work")
                .deadLetterExchange("demo.retry.dlx")
                .deadLetterRoutingKey("order.dead")
                .build();
    }

    @Bean
    Queue retryDeadQueue() {
        return QueueBuilder.durable("demo.retry.dlq").build();
    }

    @Bean
    Queue retryErrorQueue() {
        return QueueBuilder.durable("demo.retry.error.queue").build();
    }

    @Bean
    Binding retryWorkBinding(Queue retryWorkQueue,
                             DirectExchange retryEvents) {
        return BindingBuilder.bind(retryWorkQueue)
                .to(retryEvents)
                .with("order.created");
    }

    @Bean
    Binding retryDeadBinding(Queue retryDeadQueue,
                             DirectExchange retryDlx) {
        return BindingBuilder.bind(retryDeadQueue)
                .to(retryDlx)
                .with("order.dead");
    }

    @Bean
    Binding retryErrorBinding(Queue retryErrorQueue,
                              DirectExchange retryErrors) {
        return BindingBuilder.bind(retryErrorQueue)
                .to(retryErrors)
                .with("order.failed");
    }
}
~~~

Spring Boot có thể khai báo các bean exchange/queue/binding trên broker qua `RabbitAdmin` khi auto-declaration phù hợp. Nếu queue cũ đã tồn tại với DLX arguments khác, RabbitMQ có thể báo `PRECONDITION_FAILED inequivalent arg`. Không xóa queue có dữ liệu chỉ để demo chạy được.

## 9. Listener factory: chọn recoverer bằng property

Chỉ **một listener factory và một `@RabbitListener`** tiêu thụ work queue. Thay `demo.retry.recoverer` rồi restart app để so sánh mà không gặp hai consumer khác mode cạnh tranh trên cùng queue.

~~~java
import org.springframework.amqp.rabbit.config.RetryInterceptorBuilder;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.rabbit.retry.MessageRecoverer;
import org.springframework.amqp.rabbit.retry.RejectAndDontRequeueRecoverer;
import org.springframework.amqp.rabbit.retry.RepublishMessageRecoverer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.amqp.SimpleRabbitListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.interceptor.RetryOperationsInterceptor;

@Configuration
public class RetryLabListenerConfig {

    @Bean("ordersRetryFactory")
    SimpleRabbitListenerContainerFactory ordersRetryFactory(
            SimpleRabbitListenerContainerFactoryConfigurer configurer,
            ConnectionFactory connectionFactory,
            RabbitTemplate rabbitTemplate,
            @Value("${demo.retry.recoverer:reject}") String mode) {

        if (!mode.equals("reject") && !mode.equals("republish")) {
            throw new IllegalArgumentException(
                    "demo.retry.recoverer must be reject or republish");
        }

        MessageRecoverer recoverer = mode.equals("republish")
                ? new RepublishMessageRecoverer(
                        rabbitTemplate, "demo.retry.errors", "order.failed")
                : new RejectAndDontRequeueRecoverer();

        RetryOperationsInterceptor retryInterceptor =
                RetryInterceptorBuilder.stateless()
                        .maxAttempts(3)
                        .backOffOptions(500L, 2.0, 2000L)
                        .recoverer(recoverer)
                        .build();

        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();

        // Kế thừa connection, prefetch, ACK và các cài đặt Boot.
        configurer.configure(factory, connectionFactory);
        factory.setAdviceChain(retryInterceptor);
        return factory;
    }
}
~~~

Giải thích:

1. `stateless()` lặp invocation trong một delivery.
2. `maxAttempts(3)`: tối đa **ba lần gọi handler**, gồm lần đầu.
3. `backOffOptions(500L, 2.0, 2000L)`: khoảng chờ đầu 500 ms, nhân 2, giới hạn 2000 ms; không phải TTL tại broker.
4. `recoverer(...)`: xử lý sau khi toàn bộ attempts thất bại.
5. `configurer.configure(...)`: giữ các cài đặt Spring Boot trước khi gắn advice.
6. `factory.setAdviceChain(...)`: retry interceptor phải thuộc **factory mà listener dùng**.

Ví dụ này đọc payload kiểu raw `Message` để lỗi mô phỏng phát sinh **trong phương thức listener**, tránh gây nhầm lẫn với đường lỗi conversion tiền-listener. Production cần retry policy **chỉ áp dụng cho exception phù hợp**; builder trong lab cố ý đơn giản và chưa phân loại từng exception.

## 10. Consumer mô phỏng attempts và kết quả

Ta dùng ba loại order:

- `OK-`: thành công ngay lần đầu; không cần recoverer.
- `FLAKY-`: thất bại hai lần đầu, thành công lần ba; **không cần recoverer**.
- `FAIL-`: thất bại cả ba attempts; **recoverer được gọi**.

~~~java
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class RetryLabOrderListener {
    private static final Logger log =
            LoggerFactory.getLogger(RetryLabOrderListener.class);

    // Chỉ để quan sát trong lab; không phải retry store bền vững.
    private final ConcurrentHashMap<String, AtomicInteger> calls =
            new ConcurrentHashMap<>();

    @RabbitListener(
            id = "retryLabOrderListener",
            queues = "demo.retry.work",
            containerFactory = "ordersRetryFactory")
    public void receive(Message message) {
        MessageProperties properties = message.getMessageProperties();
        String eventId = properties.getMessageId();
        String orderId = new String(
                message.getBody(), StandardCharsets.UTF_8);

        if (eventId == null || eventId.isBlank()) {
            throw new IllegalStateException(
                    "This lab expects messageId");
        }

        int attempt = calls.computeIfAbsent(
                eventId, key -> new AtomicInteger()).incrementAndGet();

        log.info(
                "ATTEMPT eventId={} orderId={} attempt={} "
                        + "deliveryTag={} redelivered={} thread={}",
                eventId, orderId, attempt,
                properties.getDeliveryTag(),
                properties.isRedelivered(),
                Thread.currentThread().getName());

        if (orderId.startsWith("FAIL-")
                || (orderId.startsWith("FLAKY-") && attempt <= 2)) {
            throw new IllegalStateException(
                    "Simulated downstream failure for " + orderId);
        }

        // Production: validate, xử lý idempotent, commit DB rồi mới ACK.
        log.info("SUCCESS eventId={} attempt={}", eventId, attempt);
        calls.remove(eventId);
    }
}
~~~

**Bộ đếm `calls` không được dùng ở production.** Nó mất khi restart, không nhất quán giữa nhiều instance và có thể giữ key vô hạn cho message fail. **Spring Retry interceptor** mới là cơ chế giới hạn attempts ở lab; bộ đếm chỉ để in log.

Với một message `FLAKY-` mới, log thường hiển thị attempts 1, 2, 3 rồi `SUCCESS`. Với `FAIL-`, cả ba attempts đều ném exception nên vào recoverer. Nếu connection đứt giữa chừng, original có thể được broker giao lại, tạo vòng thực thi mới; log count lưu trong bộ nhớ lúc đó không còn phản ánh chính xác attempts trong một delivery.

## 11. Producer phát message bằng `RabbitTemplate`

Ta gửi text UTF-8 nhưng vẫn đặt `messageId` làm khóa truy vết event:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.UUID;

import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/lab/recoverer")
public class RetryLabPublisher {
    private final RabbitTemplate rabbitTemplate;

    public RetryLabPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    @PostMapping("/send")
    public ResponseEntity<Map<String, String>> send(
            @RequestParam(defaultValue = "FAIL-1001") String orderId) {

        if (!orderId.startsWith("FAIL-")
                && !orderId.startsWith("FLAKY-")
                && !orderId.startsWith("OK-")) {
            return ResponseEntity.badRequest().body(
                    Map.of("error", "Use FAIL-, FLAKY- or OK- prefix"));
        }

        String eventId = UUID.randomUUID().toString();
        MessageProperties properties = new MessageProperties();
        properties.setMessageId(eventId);
        properties.setContentType(MessageProperties.CONTENT_TYPE_TEXT_PLAIN);
        properties.setContentEncoding("utf-8");
        properties.setDeliveryMode(MessageDeliveryMode.PERSISTENT);
        properties.setHeader("eventId", eventId);

        Message message = new Message(
                orderId.getBytes(StandardCharsets.UTF_8), properties);

        rabbitTemplate.send(
                "demo.retry.events", "order.created", message);

        return ResponseEntity.accepted().body(
                Map.of("eventId", eventId, "orderId", orderId));
    }
}
~~~

HTTP `202 Accepted` ở đây chỉ nghĩa là endpoint đã gọi `send` và chưa thấy lỗi đồng bộ; **không phải publisher confirm hoặc consumer ACK**. Nếu nghiệp vụ cần kiểm tra broker đã nhận publication và không return, bật publisher confirms/returns với cấu hình phù hợp.

## 12. Thực hành A: `RejectAndDontRequeueRecoverer`

Trong `application.yml`, chọn:

~~~yaml
demo:
  retry:
    recoverer: reject
~~~

Khởi động broker rồi Spring Boot và gửi:

~~~bash
curl -X POST "http://localhost:8080/lab/recoverer/send?orderId=FAIL-1001"
~~~

Windows PowerShell có thể dùng `curl.exe` thay vì alias `curl` nếu cú pháp khác.

Kết quả log minh họa:

~~~text
ATTEMPT eventId=E1 orderId=FAIL-1001 attempt=1 deliveryTag=1 redelivered=false
ATTEMPT eventId=E1 orderId=FAIL-1001 attempt=2 deliveryTag=1 redelivered=false
ATTEMPT eventId=E1 orderId=FAIL-1001 attempt=3 deliveryTag=1 redelivered=false
... RejectAndDontRequeueRecoverer: retries exhausted ...
~~~

Điểm cần kiểm chứng:

1. `attempt` tăng qua 1, 2, 3 nhưng `deliveryTag` có thể giữ nguyên vì đây là **stateless local retry**.
2. Recoverer không sử dụng `demo.retry.errors`; nó khiến container **reject không requeue**.
3. Broker chuyển message qua `demo.retry.dlx` sang `demo.retry.dlq` khi topology hợp lệ.
4. Message đến DLQ bằng dead-letter có thể mang `x-death` ghi lý do `rejected`.

Trong RabbitMQ Management, vào **Queues and Streams → demo.retry.dlq**. Không gắn consumer vào queue lỗi trong lab nên message còn ở `Ready` để kiểm tra.

### Kiểm chứng message thành công không chạy recoverer

~~~bash
curl -X POST "http://localhost:8080/lab/recoverer/send?orderId=OK-1002"
curl -X POST "http://localhost:8080/lab/recoverer/send?orderId=FLAKY-1003"
~~~

`OK-` thành công attempt 1; `FLAKY-` thành công attempt 3. Recoverer **chỉ được gọi khi không attempt nào thành công**, vì vậy các message này không đi vào DLQ theo đường recovery.

## 13. Thực hành B: `RepublishMessageRecoverer`

Đổi property:

~~~yaml
demo:
  retry:
    recoverer: republish
~~~

**Khởi động lại ứng dụng** để listener factory dùng recoverer mới. Không chạy đồng thời hai ứng dụng khác mode trên cùng `demo.retry.work` khi cần đối chiếu từng kịch bản: chúng sẽ là competing consumers, dẫn đến kết quả khó đoán.

Gửi event mới:

~~~bash
curl -X POST "http://localhost:8080/lab/recoverer/send?orderId=FAIL-2001"
~~~

Sau ba attempts thất bại, `RepublishMessageRecoverer`:

1. Gửi bản message qua `RabbitTemplate` đến `demo.retry.errors` bằng routing key `order.failed`.
2. Broker định tuyến bản republish tới `demo.retry.error.queue`.
3. Error message thường có `x-exception-message`, `x-exception-stacktrace`, `x-original-exchange` và `x-original-routingKey`.
4. Nếu recoverer hoàn tất bình thường trong `AUTO`, container **ACK delivery gốc**. Message gốc không đi vào DLX bằng reject ở nhánh này.

Log minh họa:

~~~text
ATTEMPT eventId=E2 orderId=FAIL-2001 attempt=1 deliveryTag=2 redelivered=false
ATTEMPT eventId=E2 orderId=FAIL-2001 attempt=2 deliveryTag=2 redelivered=false
ATTEMPT eventId=E2 orderId=FAIL-2001 attempt=3 deliveryTag=2 redelivered=false
... RepublishMessageRecoverer: republished to error exchange ...
~~~

Mở **RabbitMQ Management → demo.retry.error.queue** và xem headers. **Không giả định `x-death` có sẵn**, vì đây là một publication mới của ứng dụng, không phải broker dead-letter từ queue nguồn.

### Bảng so sánh kết quả lab

| Message | Attempts trong một delivery | Recoverer? | Mode `reject` | Mode `republish` |
|---|---:|---|---|---|
| `OK-...` | 1 | Không | ACK, không vào DLQ | ACK, không vào error queue |
| `FLAKY-...` | 3 | Không, thành công attempt 3 | ACK | ACK |
| `FAIL-...` | 3, đều lỗi | **Có** | Reject `requeue=false` → broker DLQ | Publish error exchange → error queue; ACK original nếu recovery thành công |

Nếu broker mất kết nối hoặc error publish thất bại, kết quả có thể khác. Đây là kịch bản **đường đi bình thường**, không phải cam kết exactly-once khi có sự cố.

## 14. Khi republish thất bại: mất, trùng và xác nhận

### 14.1. Lệnh gửi thành công không chứng minh error queue nhận được message

Nếu `demo.retry.errors` tồn tại nhưng binding `order.failed` bị xóa, bản republish có thể **unroutable**. Nếu producer không bật `mandatory`, broker có thể loại bản đó mà không gửi publisher return; publisher confirm ACK (nếu bật) cũng không tự chứng minh đã đến queue.

Với recoverer thường, nếu `RabbitTemplate.send` không ném exception và recoverer trả về bình thường, container `AUTO` có thể ACK delivery gốc. **Không kiểm tra error routing là nguy cơ làm thất lạc thông tin lỗi**.

### 14.2. Publisher confirms/returns cho error publication

Với luồng lỗi quan trọng, nên đánh giá:

- Bật **correlated publisher confirms** để biết broker ACK/NACK lần republish.
- Bật **`mandatory` và publisher returns** để phát hiện bản republish không tới queue nào.
- Sử dụng **`RepublishMessageRecovererWithConfirms`** nếu phiên bản Spring AMQP của bạn hỗ trợ hoặc implement recoverer có kiểm tra confirm/return tương đương.
- Có timeout rõ ràng; nếu không nhận confirm, trạng thái là **UNKNOWN**, không mặc nhiên kết luận broker chưa nhận.

**Không suy rằng `RepublishMessageRecoverer` mặc định tự đợi đủ tất cả confirm/return chỉ vì bạn đặt `publisher-confirm-type: correlated`.** Cơ chế chờ/kiểm tra xác nhận cần được chọn và cấu hình thực sự, phù hợp phiên bản framework và connection factory.

### 14.3. Bản republish và ACK gốc không phải transaction nguyên tử

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Listener + Recoverer
    participant B as RabbitMQ
    participant E as Error queue
    B->>C: Deliver original
    C->>C: Retry exhausted
    C->>B: Publish failed message
    B->>E: Route error copy
    B-->>C: Publisher confirm (khi bật)
    Note over B,C: Mất connection/crash có thể xảy ra tại đây
    C-->>B: ACK original delivery
~~~

Nếu error queue **đã nhận bản republish** nhưng ACK delivery gốc không tới broker, message gốc có thể được giao lại, retry lại rồi tạo **bản lỗi thứ hai**. Error consumer cần idempotency theo `eventId` hoặc khóa nghiệp vụ bền vững.

Ngược lại, nếu container ACK original khi error publication chưa được broker xác nhận/định tuyến thực sự, message có thể không còn ở cả work queue lẫn error queue. Tăng độ tin cậy đòi hỏi xác nhận publication, trạng thái đối soát, idempotency và kế hoạch xử lý lỗi.

### 14.4. Broker DLX cũng không hoàn toàn miễn nhiễm sự cố

Đường `RejectAndDontRequeueRecoverer` không phải tự động tuyệt đối an toàn chỉ vì do broker thực hiện. Queue type, durability, chính sách dead-letter, broker failures và version RabbitMQ ảnh hưởng kết quả. Với thông điệp quan trọng, xem xét quorum queues, cơ chế dead-letter bảo đảm hơn nếu broker hỗ trợ và giám sát số message thật sự tới DLQ.

## 15. Spring AUTO/MANUAL và lỗi tiền-listener

### 15.1. Lab dùng AUTO để rõ trách nhiệm ACK

Khi `spring.rabbitmq.listener.simple.acknowledge-mode=auto`, container quản lý consumer ACK:

- Listener thành công → container ACK.
- Retry hết lượt + reject recoverer → handler ném exception yêu cầu **reject không requeue**.
- Retry hết lượt + republish recoverer trả về bình thường → container ACK original.

**Spring `AUTO` khác RabbitMQ consumer `autoAck=true`**. Với `AUTO`, broker vẫn giữ message ở trạng thái Unacked cho đến khi container xác nhận.

### 15.2. Không sao chép nguyên hành vi này sang MANUAL

Ở `MANUAL`, ứng dụng cần quản lý `Channel` và `deliveryTag`. Recoverer trả về bình thường **không thay thế trách nhiệm ACK thủ công trong mọi cấu hình**; phải quyết định ai ACK original sau recovery, ai reject và lỗi conversion trước handler được xử lý thế nào.

~~~text
MANUAL ACK phải định nghĩa:
  Xử lý thành công → khi nào ACK sau business commit?
  Retry hết lượt + reject recoverer → container hay code reject?
  Retry hết lượt + republish recoverer → ai ACK original?
  Lỗi conversion tiền-listener → error handler nào xử lý?
  Republish thành công nhưng ACK gốc thất lạc → chống trùng thế nào?
~~~

Không ACK hai lần, không ACK trên channel khác và không lưu `deliveryTag` làm event ID. Tag chỉ hợp lệ trên channel của delivery hiện tại; ACK sai có thể làm broker đóng channel với lỗi `unknown delivery tag`.

### 15.3. `ConditionalRejectingErrorHandler` khác `MessageRecoverer`

`ConditionalRejectingErrorHandler` ở tầng container thường nhận diện lỗi fatal như conversion/argument binding trước khi handler chạy. Nó có thể dẫn tới `AmqpRejectAndDontRequeueException` **không cần qua hết chuỗi retry nghiệp vụ**.

Chính sách thực tế phải phân loại:

- Lỗi dữ liệu cố định → không retry mãi cùng bytes, quarantine/DLQ.
- Lỗi hạ tầng tạm thời → bounded retry/backoff và recoverer.
- Lỗi lập trình → alert, cách ly và chính sách rõ, không mặc định retry vô hạn.

## 16. Thiết kế retry cho production

### 16.1. Bảng lựa chọn theo điều kiện

| Tình huống | Hướng xử lý | Lý do |
|---|---|---|
| JSON sai cú pháp/schema không hỗ trợ | Fatal → reject/quarantine | Retry không tự sửa dữ liệu |
| Database timeout/API 503 | Retry có giới hạn/backoff, sau đó recoverer | Có thể phục hồi sau thời gian chờ |
| Queue nguồn có broker DLX được kiểm soát | Có thể chọn reject recoverer | Tận dụng đường dead-letter broker |
| Cần exception metadata và error routing linh hoạt | Có thể chọn republish recoverer | Ứng dụng chọn error exchange/routing |
| Không biết error publish đã được confirm hay chưa | Đánh dấu UNKNOWN, đối soát/retry idempotent | Tránh ACK original khi recovery chưa chắc chắn |
| Business DB đã commit nhưng original ACK thất lạc | Idempotent consumer | Broker có thể redeliver |

### 16.2. Xử lý nghiệp vụ và ACK đúng thứ tự

~~~text
Nhận event có eventId ổn định
  → Validate schema + required fields
  → Kiểm tra processed_event(eventId)
  → Thực hiện business transaction
  → Ghi processed_event(eventId) trong cùng DB transaction
  → COMMIT
  → Consumer ACK

Nếu lỗi tạm thời:
  → Retry hữu hạn + backoff
  → Exhausted → recoverer theo policy

Nếu lỗi không thể khắc phục:
  → Reject/quarantine hoặc trạng thái nghiệp vụ đã quy định
~~~

RabbitMQ consumer ACK và database commit **không nằm trong một transaction nguyên tử theo mặc định**. Nếu commit thành công rồi ACK bị thất lạc, broker có thể giao lại. `eventId` ổn định cùng unique constraint/idempotency store giúp ngăn xử lý side effect lần nữa.

Nếu ứng dụng vừa commit DB vừa phát event khác, cân nhắc **transactional outbox**. Publisher confirms/returns bảo vệ phía publish; consumer ACK, retry và recoverer bảo vệ phía tiêu thụ. Không cơ chế đơn lẻ nào tự tạo exactly-once processing.

### 16.3. Giữ ID nghiệp vụ qua lần retry và publish lại

- `eventId`: định danh **cùng nghiệp vụ**, không đổi sau retry.
- `publishAttemptId`: định danh **mỗi lần publication** nếu cần đối chiếu confirm/return.
- `messageId`: AMQP property do producer kiểm soát, nên có quy tắc nhất quán.
- `deliveryTag`: định danh delivery **trên một channel**, không ổn định sau reconnect.
- `consumerTag`: định danh consumer subscription, không phải khóa idempotency.

Chú ý bản republish có thể giữ một số metadata của message cũ; không mặc nhiên giả định mọi header đều có ý nghĩa giống trước khi republish, nhất là routing, receive timestamps và dead-letter history.

## 17. Quan sát RabbitMQ Management và log

Mở `http://localhost:15672` và xem:

| Queue | Dùng cho | Điều cần quan sát |
|---|---|---|
| `demo.retry.work` | Consumer chính | Ready, Unacked, Consumers, deliver/ack rate |
| `demo.retry.dlq` | Broker dead-letter sau reject | `x-death`, message ID, lý do `rejected` |
| `demo.retry.error.queue` | App republish sau retry exhausted | `x-exception-*`, `x-original-*`, event ID |

Không tạo consumer đọc queue lỗi trong lab; message có thể ở `Ready` để xem. Khi dùng **Get messages** trong Management, chọn tùy chọn ACK/requeue cẩn thận: thao tác quan sát có thể thay đổi trạng thái message.

### Các trường log nên có

~~~text
timestamp, eventId, publishAttemptId, queue, exchange, routingKey,
deliveryTag, consumerTag, redelivered, retryAttempt, exceptionClass,
recovererType, recoveryExchange, recoveryRoutingKey,
publisherConfirm, publisherReturn, finalDeliveryDecision
~~~

Không log payload chứa token/PII một cách vô điều kiện. Exception stack trace trên error message cũng cần retention/permission phù hợp.

### Dấu hiệu cảnh báo

1. Tốc độ retry và số lỗi/attempt tăng nhanh.
2. DLQ hoặc error queue liên tục tích tụ.
3. Work queue Ready/Unacked tăng, Consumer count giảm.
4. Error publication gặp confirm NACK, timeout hoặc publisher return.
5. Trùng `eventId` tăng sau reconnect/retry.
6. Error queue không có quy trình điều tra/replay và retention.

`Ready=0` không chứng minh nghiệp vụ thành công: message có thể đã ACK, bị dead-letter, republish hoặc bị loại.

## 18. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Ba attempts xong message vẫn lặp vô hạn | Sai listener factory/advice, recoverer không chạy, hoặc exception khác bị requeue | Kiểm tra `containerFactory`, interceptor chain, error handler |
| Reject recoverer chạy nhưng DLQ trống | DLX/binding không đúng, queue nguồn thiếu DLX | Kiểm tra queue arguments, exchange, routing key, permissions |
| Republish recoverer chạy nhưng error queue trống | Error exchange/routing key sai, chưa kiểm tra publisher returns/confirm | Kiểm tra binding và publish result |
| Hai attempts thay vì ba | Sai `maxAttempts`, handler thành công sớm hoặc có interceptor khác | Nhớ `maxAttempts` gồm lần đầu |
| `redelivered=false` dù có ba log attempts | Stateless local retry không tạo broker redelivery | Đếm attempts tại Spring interceptor/log |
| Không có `x-death` trên error message | Message đi đường republish từ ứng dụng | Tìm `x-exception-*` và `x-original-*` |
| Republish tạo các bản error trùng | Original ACK thất lạc hoặc nhiều retry publications | Idempotency theo `eventId` và theo dõi attempts |
| JSON malformed không đi qua recoverer | Lỗi conversion xảy ra trước lời gọi/advice hoặc bị container coi fatal | Kiểm tra converter, `ConditionalRejectingErrorHandler` |
| MANUAL ACK làm Unacked tăng | Recovery không đi kèm ACK rõ ràng | Thiết kế ACK theo từng nhánh trên đúng channel |
| Thay property nhưng mode không đổi | Chưa restart hoặc listener dùng factory khác | Kiểm tra config, bean, number of consumers |
| Error headers quá lớn/lộ dữ liệu | Republish thêm stack trace và exception text | Giới hạn log/headers, phân quyền error queue |
| Producer nhận ACK nhưng consumer fail | Publisher confirm độc lập với consumer result | Theo dõi listener ACK, DLQ, business state |

**Thứ tự chẩn đoán:** lấy `eventId` → xác định listener factory và advice → đếm attempts → tìm recoverer thực sự → xem ACK/reject delivery gốc → xem DLX hoặc error exchange → kiểm tra headers/confirm/return → đối soát kết quả nghiệp vụ.

## 19. Bài tập thực hành

**Bài A — Đối chiếu hai recoverer.** Gửi `FAIL-...` ở mode `reject` và `republish` riêng rẽ. So sánh attempts, queue lỗi, headers và cách original delivery kết thúc. Giải thích broker DLX khác app publish ra sao.

**Bài B — Thành công ở attempt cuối.** Gửi `FLAKY-...`. Vì sao cả hai mode đều không gọi recoverer dù handler đã ném exception hai lần?

**Bài C — Sai binding error exchange.** Trong lab riêng, gỡ binding `order.failed` ở `demo.retry.errors`. Phân tích hậu quả nếu chỉ dựa vào `RabbitTemplate.send` mà không có mandatory/returns/confirms.

**Bài D — Không có DLX.** Trong lab riêng, tạo queue nguồn không có DLX rồi dùng reject recoverer. Dự đoán điều gì xảy ra và viết checklist thiết lập DLQ trước khi deploy.

**Bài E — Broker redelivery khác local retry.** So sánh `deliveryTag`/`redelivered` trong ba stateless attempts với một lần `basicNack(requeue=true)` thật. Không thử requeue vô hạn.

**Bài F — Republish trước khi ACK bị mất kết nối.** Nếu error queue đã nhận bản lỗi nhưng original chưa ACK, broker có thể làm gì? Đề xuất idempotency cho error consumer và trạng thái UNKNOWN khi confirm thất lạc.

**Bài G — Thiết kế production.** Cho workload 10 triệu event/ngày, lưu message lỗi bảy ngày, dữ liệu nhạy cảm và cần routing theo đối tác. Đề xuất recoverer, bảo mật headers, retry/backoff, dead-letter, confirms, monitoring và quy trình replay.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** `RejectAndDontRequeueRecoverer` có tự publish một bản message vào DLQ không?

**Đáp án:** Không. Nó tạo quyết định reject không requeue; **broker** mới dead-letter qua DLX nếu topology hợp lệ.

**Câu 2.** `RepublishMessageRecoverer` có bắt buộc work queue có DLX không?

**Đáp án:** Không. Nó dùng `RabbitTemplate` publish tới **error exchange** và cần binding/error queue phù hợp.

**Câu 3.** `maxAttempts(3)` có nghĩa thử lại ba lần sau lần đầu không?

**Đáp án:** Không. Nó thường gồm **một lần đầu + hai lần retry**, tổng ba attempts.

**Câu 4.** Vì sao `redelivered=false` không chứng minh handler chỉ được gọi một lần?

**Đáp án:** Stateless retry có thể gọi handler nhiều attempts **trong một broker delivery**.

**Câu 5.** `x-death` và `x-exception-stacktrace` có cùng ý nghĩa không?

**Đáp án:** Không. `x-death` phản ánh lịch sử broker dead-letter; `x-exception-stacktrace` thường do republish recoverer thêm để điều tra exception.

**Câu 6.** Republish thành công có bảo đảm original delivery và error message đã được xử lý exactly-once không?

**Đáp án:** Không. Republish và original ACK không nguyên tử; confirm/return, idempotency và đối soát vẫn cần.

**Câu 7.** Vì sao không để `requeue=true` vô hạn khi downstream lỗi?

**Đáp án:** Có thể gây vòng lặp nóng, CPU/log tăng và không có tiến triển. Dùng bounded retry/backoff và recovery cuối.

**Câu 8.** Nếu error exchange tồn tại nhưng không có binding khớp, điều gì có thể xảy ra?

**Đáp án:** Bản republish không tới error queue. Nếu không phát hiện qua mandatory/returns/confirm thích hợp, container vẫn có thể ACK original sau khi recoverer trả về.

**Câu 9.** Vì sao không áp giả định “recoverer trả về là ACK” sang mọi listener `MANUAL`?

**Đáp án:** Trong `MANUAL` ứng dụng phải tự quản lý xác nhận delivery, kể cả các đường lỗi và recovery.

## 21. Ghi nhớ

- **`MessageRecoverer` xử lý sau retry exhausted**, không tự quyết định số attempts hoặc backoff.
- **`RejectAndDontRequeueRecoverer` → reject không requeue → broker DLX/DLQ** nếu routing hợp lệ. **`RepublishMessageRecoverer` → app republish error exchange → container ACK original** trong đường recovery thành công với `AUTO`.
- **Metadata hai đường khác nhau**: `x-death` là lịch sử dead-letter broker, còn `x-exception-*`/`x-original-*` thường đi cùng bản republish.
- **Republish + ACK không phải transaction nguyên tử**. Cần kiểm tra publisher confirms/returns, timeout/UNKNOWN, điều kiện unroutable và idempotency.
- **Retry đáng tin cậy cần phân loại lỗi, maxAttempts, backoff, ACK phù hợp, transaction/outbox và quan sát**; không recoverer nào tự tạo exactly-once processing.
