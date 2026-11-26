# Manual ack khi xử lý bất đồng bộ và tránh xác nhận quá sớm

Một ứng dụng **Spring AMQP** có thể nhận message bằng **@RabbitListener** rồi gọi database, REST API, service thanh toán hoặc một tác vụ chạy trong thread pool. Nếu listener **xác nhận ACK trước khi công việc bất đồng bộ thật sự hoàn tất**, RabbitMQ sẽ coi message đã xử lý xong. Khi ứng dụng crash sau ACK nhưng trước khi ghi dữ liệu, broker **không còn message đó để tự giao lại**. Đây là một lỗi nghiêm trọng dù phần publish bằng **RabbitTemplate** và định tuyến qua exchange, queue, binding đều đúng.

Bài học thuộc chương **Xác nhận tiêu thụ** của module **SPRING_AMQP**: thực hành consumer acknowledgement (ACK/NACK), xử lý bất đồng bộ, retry/dead-letter, giao dịch, idempotency và quan sát hệ thống để xây các luồng RabbitMQ đáng tin cậy.

**Nguyên tắc trung tâm:** ACK phải phản ánh **kết quả hoàn tất mà ứng dụng đã cam kết xử lý**, không chỉ phản ánh việc listener **đã khởi động** một tác vụ.

Sau bài học, bạn sẽ có thể:

1. Phân biệt **AUTO**, **MANUAL** và **NONE** của Spring listener container.
2. Chỉ ra anti-pattern **fire-and-forget** gây ACK quá sớm.
3. Dùng **CompletableFuture** hoặc **Mono** làm kết quả trả về của @RabbitListener để container ACK/NACK theo kết quả bất đồng bộ.
4. Thực hiện **Channel.basicAck/basicNack** thủ công đúng delivery tag khi cần chủ động điều khiển ACK.
5. Xử lý thất bại, backpressure, consumer timeout, redelivery và dead-letter mà không làm mất hoặc lặp side effect nghiệp vụ ngoài ý muốn.

## 1. ACK xác nhận điều gì?

RabbitMQ phân biệt **publisher confirm** ở chiều gửi với **consumer acknowledgement** ở chiều nhận.

~~~mermaid
sequenceDiagram
    participant P as Publisher / RabbitTemplate
    participant B as RabbitMQ
    participant C as @RabbitListener
    participant DB as Database / API
    P->>B: Publish qua exchange và binding
    B-->>P: Publisher confirm (nếu bật)
    B->>C: Delivery từ queue
    C->>DB: Xử lý nghiệp vụ
    DB-->>C: Commit / kết quả thành công
    C-->>B: Consumer basic.ack
~~~

**Consumer ACK** xác nhận rằng lần delivery với **delivery tag** cụ thể trên một AMQP channel đã được consumer chấp nhận hoàn tất. Khi broker nhận ACK hợp lệ, message được loại khỏi trạng thái chưa xác nhận của queue.

ACK **không phải** một distributed transaction giữa RabbitMQ và database. Nếu database commit nhưng ACK bị thất lạc vì connection đóng, broker có thể **redeliver** message. Vì vậy, ngay cả khi ACK đúng thời điểm, hệ thống vẫn phải sẵn sàng xử lý duplicate.

### Ba loại kết quả cần phân biệt

| Trạng thái | Điều đã xảy ra | Nên ACK chưa? |
| --- | --- | --- |
| Listener **nhận được** message | Broker giao bytes đến consumer | **Chưa** nếu nghiệp vụ chưa xong |
| Listener **lên lịch** tác vụ vào executor | Một Future/Mono được tạo, công việc có thể chưa chạy | **Chưa** |
| Tác vụ **hoàn tất thành công**, side effect cần thiết đã commit | Ứng dụng có bằng chứng hoàn tất theo hợp đồng nghiệp vụ | **Có thể ACK** |
| Tác vụ thất bại trước khi hoàn tất | Message chưa xử lý thành công | Cần **NACK/requeue hoặc reject/dead-letter** theo loại lỗi |
| Database commit nhưng connection chết trước ACK | Broker có thể giao lại | Dùng **idempotency** để xử lý lại an toàn |

## 2. Anti-pattern: listener trả về trước khi tác vụ hoàn thành

Giả sử một listener nhận sự kiện tạo đơn hàng rồi lập lịch ghi database:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class UnsafeOrderListener {
    private final AsyncOrderDispatcher dispatcher;

    public UnsafeOrderListener(AsyncOrderDispatcher dispatcher) {
        this.dispatcher = dispatcher;
    }

    @RabbitListener(queues = "lab.orders.unsafe")
    public void onOrder(String payload) {
        dispatcher.process(OrderEvent.parse(payload)); // Future bị bỏ qua!
    }
}
~~~

Ở chế độ Spring **AUTO acknowledge** thông thường:

1. Container gọi **onOrder(...)**.
2. **dispatcher.process(...)** trả về nhanh một **CompletableFuture** đang chạy.
3. Method listener **void** kết thúc mà không ném exception.
4. Container xem lượt gọi listener đã thành công và **có thể ACK** delivery.
5. Tác vụ async tiếp tục chạy, hoặc có thể thất bại/crash **sau khi broker đã nhận ACK**.

~~~mermaid
sequenceDiagram
    participant B as RabbitMQ
    participant L as Listener thread
    participant W as Async worker
    participant DB as Database
    B->>L: Deliver M1
    L->>W: Submit process(M1)
    W-->>L: CompletableFuture chưa hoàn tất
    L-->>B: AUTO ACK vì method void đã return
    W->>DB: Write M1
    DB--xW: Lỗi / ứng dụng crash
    Note over B,DB: M1 đã ACK, RabbitMQ không tự redeliver M1
~~~

**Lỗi không nằm ở CompletableFuture hay RabbitMQ**; lỗi là ở việc **không liên kết vòng đời completion của task với vòng đời acknowledgement của delivery**.

### Các biến thể cũng dễ gây ACK quá sớm

~~~java
@RabbitListener(queues = "lab.orders.unsafe")
public void wrong1(String payload) {
    executor.execute(() -> writeDatabase(payload));
    // return ngay; Spring AUTO có thể ACK
}

@RabbitListener(queues = "lab.orders.unsafe")
public void wrong2(String payload) {
    remoteApi.callAsync(payload);
    // không theo dõi kết quả callAsync
}

@RabbitListener(queues = "lab.orders.unsafe", ackMode = "MANUAL")
public void wrong3(String payload, Channel channel, long deliveryTag)
        throws IOException {
    channel.basicAck(deliveryTag, false); // ACK trước
    executor.execute(() -> writeDatabase(payload));
}
~~~

Ba đoạn này là **anti-pattern minh họa**, không phải mã hoàn chỉnh để chạy. Ngoài việc ACK sớm, ví dụ cuối còn phải truyền đúng delivery tag bằng **@Header(AmqpHeaders.DELIVERY_TAG)**; không được giả định một tham số long bất kỳ tự được ánh xạ thành delivery tag.

**Quy tắc:** nếu công việc chạy async và method listener không chờ kết quả, cần một cơ chế **deferred acknowledgement**. Hai hướng được hỗ trợ:

- **Ưu tiên:** method @RabbitListener **trả về CompletableFuture/Mono** để Spring AMQP tự ACK/NACK theo trạng thái completion.
- **Kiểm soát thấp tầng:** dùng **AcknowledgeMode.MANUAL**, lưu đúng channel/delivery tag và tự ACK/NACK **chỉ khi task đã hoàn tất**.

## 3. AUTO, MANUAL và NONE không tương đương

Spring AMQP cung cấp **AcknowledgeMode** tại listener container:

| Chế độ | Ai gửi ACK? | Ứng dụng nên làm gì? | Rủi ro |
| --- | --- | --- | --- |
| **AUTO** | Container ACK khi listener hoàn tất thành công và xử lý exception theo cấu hình | Method đồng bộ phải hoàn tất công việc trước khi return | Void fire-and-forget làm ACK trước khi task async xong |
| **MANUAL** | Listener hoặc cơ chế async-aware của framework gửi ACK/NACK | Bảo đảm mọi delivery có kết quả xác nhận rõ ràng | Quên ACK khiến message Unacked; ACK sớm gây mất xử lý |
| **NONE** | Không dùng consumer acknowledgement; broker coi đã xác nhận khi giao (*auto-ack/no-ack*) | Chỉ dùng khi chấp nhận nguy cơ mất message | Không có cơ chế redelivery khi ứng dụng chết sau delivery |

**Điểm dễ nhầm:** Spring **AUTO** nghĩa là **container tự xác nhận sau khi method xử lý thành công**, không giống AMQP **autoAck=true** (Spring **NONE**). Khi method trả về **Future/Mono được framework nhận diện**, việc ACK có thể được trì hoãn tới lúc Future/Mono hoàn tất theo cơ chế async listener, thay vì ACK ngay khi method return.

### Cấu hình global trong Spring Boot

Ví dụ **application.yml** cho các **simple listener container**:

~~~yaml
spring:
  rabbitmq:
    listener:
      simple:
        acknowledge-mode: manual
        prefetch: 5
        concurrency: 2
~~~

Nếu dùng **DirectRabbitListenerContainerFactory**, cấu hình nằm ở **spring.rabbitmq.listener.direct** thay vì simple. Khi cần duy nhất một listener manual, nên dùng factory riêng hoặc thuộc tính **ackMode = "MANUAL"** của chính annotation để tránh vô tình buộc tất cả listener dùng manual acknowledgement.

## 4. Hai cách trì hoãn ACK trong Spring AMQP

| Cách | Ai ACK khi async complete? | Ưu điểm | Điểm cần thận trọng |
| --- | --- | --- | --- |
| **@RabbitListener trả CompletableFuture<?>** | **Spring AMQP container/adapter** | Ngắn gọn, phù hợp API async, không tự dùng Channel | Future phải phản ánh kết quả thật; không nuốt exception |
| **@RabbitListener trả Mono<?>** | **Spring AMQP** khi kết quả reactive hoàn tất | Phù hợp Reactor và pipeline reactive | Đừng tự subscribe trong void listener; quản lý subscription/lỗi |
| **@RabbitListener void + Channel.basicAck/Nack** | **Code của bạn**, trong callback hoàn tất | Kiểm soát trực tiếp delivery tag và ACK | Thread safety, ACK trùng, channel đóng, xử lý mọi nhánh lỗi |

**Khuyến nghị:** khi nghiệp vụ được biểu diễn tự nhiên bằng **CompletableFuture** hoặc **Mono**, hãy để Spring AMQP quản lý ACK/NACK của async result. Chỉ tự gọi Channel.basicAck/basicNack khi thật sự cần điều khiển ở cấp giao thức và có cơ chế đảm bảo chỉ gửi **một kết quả** cho mỗi delivery.

### Về phiên bản Spring AMQP

Theo tài liệu Spring AMQP, async listener hỗ trợ **CompletableFuture<?>** và **Mono<?>**. Các bản từ **2.2.21, 2.3.13 và 2.4.1** bắt đầu tự điều chỉnh acknowledge mode sang **MANUAL** khi phát hiện async return type; trên các phiên bản hiện đại, hành vi này đã có sẵn. Tuy vậy, **cấu hình MANUAL rõ ràng** giúp người đọc và người vận hành thấy hợp đồng ACK trong code.

**Kotlin suspend** cũng được hỗ trợ trong các bản Spring AMQP hiện đại (từ 3.0.5 với dependency coroutine phù hợp). Bài này dùng **Java 17 và CompletableFuture** để tập trung vào nguyên tắc chính.

## 5. Chuẩn bị project và topology cho bài thực hành

Ví dụ sử dụng **Spring Boot 3.x, Java 17, Spring AMQP 3.x, RabbitMQ AMQP 0-9-1**. Dùng dependency:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-amqp")
    implementation("org.springframework.boot:spring-boot-starter-jdbc")
    runtimeOnly("org.postgresql:postgresql")
}
~~~

Hai dependency JDBC/PostgreSQL chỉ cần cho ví dụ lưu bền và **idempotency** ở phần sau. Nếu chỉ muốn thử timing của ACK, có thể dùng service mô phỏng delay thay vì kết nối DB.

Ví dụ kết nối RabbitMQ trong **application.yml**:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: app
    password: local_dev_password
    virtual-host: /
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: app
    password: local_db_password
~~~

Các tài khoản là **ví dụ môi trường lab**, cần tạo hoặc thay theo cấu hình thực tế. Không commit mật khẩu production vào repository; sử dụng secret manager hoặc biến môi trường.

### 5.1. Exchange, queue, binding và dead-letter

Ta khai báo một queue chính nhận các sự kiện **order.created** và một DLQ cho thông điệp lỗi không requeue:

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableRabbit
public class AsyncAckTopology {
    public static final String EXCHANGE = "lab.orders.events";
    public static final String QUEUE = "lab.orders.async";
    public static final String ROUTING_KEY = "order.created";
    public static final String DLX = "lab.orders.dlx";
    public static final String DLQ = "lab.orders.async.dlq";

    @Bean
    DirectExchange orderEventsExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    DirectExchange orderDeadLetterExchange() {
        return new DirectExchange(DLX, true, false);
    }

    @Bean
    Queue asyncOrderQueue() {
        return QueueBuilder.durable(QUEUE)
                .deadLetterExchange(DLX)
                .deadLetterRoutingKey("order.failed")
                .build();
    }

    @Bean
    Queue asyncOrderDlq() {
        return QueueBuilder.durable(DLQ).build();
    }

    @Bean
    Binding orderInputBinding(
            @Qualifier("asyncOrderQueue") Queue queue,
            @Qualifier("orderEventsExchange") DirectExchange exchange) {
        return BindingBuilder.bind(queue)
                .to(exchange).with(ROUTING_KEY);
    }

    @Bean
    Binding orderDlqBinding(
            @Qualifier("asyncOrderDlq") Queue queue,
            @Qualifier("orderDeadLetterExchange") DirectExchange exchange) {
        return BindingBuilder.bind(queue)
                .to(exchange).with("order.failed");
    }
}
~~~

Bean Java là **định nghĩa topology**, còn RabbitMQ phải thật sự được khai báo thông qua **RabbitAdmin** hoặc cơ chế quản lý hạ tầng khác. Nếu queue đã tồn tại với argument khác, khai báo lại có thể bị broker từ chối bằng **PRECONDITION_FAILED**; không tự xóa queue chứa dữ liệu quan trọng để sửa lỗi.

**DLQ không tự hoạt động chỉ vì có bean tên DLQ.** Cần cả DLX, binding phù hợp, quyền publish đến DLX và điều kiện dead-letter xảy ra. Queue chính ở ví dụ dùng argument DLX để minh họa; trong hệ thống vận hành, policy do quản trị RabbitMQ quản lý cũng là một lựa chọn.

### 5.2. Publisher gửi sự kiện có ID ổn định

Để dễ quan sát, body lab có dạng **eventId|orderId** thay vì JSON:

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class AsyncOrderPublisher {
    private final RabbitTemplate rabbitTemplate;

    public AsyncOrderPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publish(String eventId, String orderId) {
        rabbitTemplate.convertAndSend(
                AsyncAckTopology.EXCHANGE,
                AsyncAckTopology.ROUTING_KEY,
                eventId + "|" + orderId,
                message -> {
                    message.getMessageProperties().setMessageId(eventId);
                    message.getMessageProperties().setType("order.created");
                    return message;
                }
        );
    }
}
~~~

**eventId được tạo khi sự kiện nghiệp vụ hình thành**, không tạo mới trong một lần publish retry. Nếu gửi lại cùng sự kiện do confirm timeout, vẫn dùng eventId cũ. RabbitMQ không tự khử trùng các bản publish có cùng messageId; consumer phải idempotent.

Khi dùng JSON thực tế, có thể định nghĩa event envelope chứa **eventId, eventType, schemaVersion, occurredAt và data** rồi dùng converter tương ứng. Quy tắc ACK bất đồng bộ **không thay đổi** theo định dạng body.

## 6. Cách ưu tiên: @RabbitListener trả CompletableFuture

Với kiểu trả về **CompletableFuture<?>**, Spring AMQP có thể trì hoãn ACK đến khi future hoàn tất. Khi future **complete thành công**, adapter/container tiến hành ACK; khi future **complete exceptionally**, framework quyết định NACK/requeue/reject theo ngoại lệ và chính sách listener.

~~~mermaid
sequenceDiagram
    participant B as RabbitMQ
    participant L as @RabbitListener
    participant W as Async worker
    participant DB as Database
    B->>L: Deliver M1
    L->>W: Submit task và lấy CompletableFuture
    L-->>B: Chưa ACK, listener return future
    W->>DB: Ghi và commit
    DB-->>W: Thành công
    W-->>L: Future complete successfully
    L-->>B: Spring AMQP ACK M1
~~~

**Phần quyết định khác anti-pattern:** listener **trả lại chính future đại diện công việc thật**, không gọi async service rồi bỏ qua kết quả trong method **void**.

### 6.1. Cấu hình factory MANUAL và prefetch

Bạn có thể dùng thuộc tính **ackMode="MANUAL"** trực tiếp trên annotation hoặc một factory rõ mục đích. Ví dụ factory cho Spring Boot 3.x:

~~~java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.boot.autoconfigure.amqp.SimpleRabbitListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AsyncAckContainerConfig {

    @Bean("asyncAckFactory")
    SimpleRabbitListenerContainerFactory asyncAckFactory(
            SimpleRabbitListenerContainerFactoryConfigurer configurer,
            ConnectionFactory connectionFactory) {

        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        configurer.configure(factory, connectionFactory);

        factory.setAcknowledgeMode(AcknowledgeMode.MANUAL);
        factory.setConcurrentConsumers(2);
        factory.setMaxConcurrentConsumers(2);
        factory.setPrefetchCount(4);
        return factory;
    }
}
~~~

Cấu hình **MANUAL** là bắt buộc về mặt ngữ nghĩa: container **không được ACK lúc method mới trả future**. Với kiểu trả về async được hỗ trợ ở Spring AMQP hiện đại, framework cũng có khả năng tự chọn MANUAL. Cấu hình tường minh giúp khi review không nhầm rằng code đang chạy AUTO cho method void.

**Quan trọng:** khi dùng future return này, **không tự gọi Channel.basicAck** trong listener. Spring AMQP sẽ quản lý ACK/NACK dựa trên completion; tự ACK thêm có thể dẫn tới **double ACK / unknown delivery tag**.

### 6.2. Tách executor của công việc khỏi listener container

Sử dụng thread pool có giới hạn thay vì tạo thread mới vô hạn:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class OrderWorkExecutorConfig {

    @Bean("orderWorkExecutor")
    ThreadPoolTaskExecutor orderWorkExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("order-work-");
        return executor;
    }
}
~~~

Trong lab, pool có **4 worker threads** và **16 vị trí chờ**. Khi quá tải, submit có thể bị từ chối; vì vậy cần xử lý **RejectedExecutionException** hoặc ngoại lệ submit phù hợp, giám sát backlog và điều chỉnh concurrency/prefetch theo số liệu thật.

### 6.3. Tạo đối tượng sự kiện để validate đầu vào

~~~java
import java.util.UUID;

public record OrderEvent(UUID eventId, String orderId) {

    public static OrderEvent parse(String payload) {
        String[] parts = payload.split("\\|", -1);
        if (parts.length != 2 || parts[1].isBlank()) {
            throw new IllegalArgumentException(
                    "Expected eventId|orderId");
        }
        return new OrderEvent(UUID.fromString(parts[0]), parts[1]);
    }
}
~~~

Đây là định dạng minh họa rất nhỏ. Trong hệ thống thật cần validation hợp đồng JSON, schemaVersion, tenant và các giới hạn độ dài/kiểu dữ liệu. Lỗi dữ liệu đầu vào **không thể khắc phục bằng cách requeue vô hạn**.

### 6.4. Business service thực hiện transaction ở đúng thread

Ví dụ PostgreSQL dùng **eventId** chống duplicate trong **cùng DB transaction** với việc cập nhật projection:

~~~sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(80) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE order_projection (
    order_id TEXT PRIMARY KEY,
    last_event_id UUID NOT NULL
);
~~~

Service nghiệp vụ:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderWriteService {
    private final JdbcTemplate jdbc;

    public OrderWriteService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void applyOnce(OrderEvent event) {
        int inserted = jdbc.update(
                """
                INSERT INTO processed_event(consumer_name, event_id)
                VALUES (?, ?)
                ON CONFLICT DO NOTHING
                """,
                "order-projection", event.eventId());

        if (inserted == 0) {
            return; // Đã commit cùng eventId trước đó
        }

        jdbc.update(
                """
                INSERT INTO order_projection(order_id, last_event_id)
                VALUES (?, ?)
                ON CONFLICT (order_id)
                DO UPDATE SET last_event_id=EXCLUDED.last_event_id
                """,
                event.orderId(), event.eventId());
    }
}
~~~

**Transaction có tác dụng:** nếu cập nhật projection thất bại, dòng **processed_event** cũng rollback; nếu commit thành công nhưng consumer mất connection trước ACK, lần nhận lại sẽ thấy eventId đã xử lý và có thể ACK mà không lặp side effect.

Ví dụ này chỉ lưu event cuối trong một projection tối giản; nghiệp vụ có thứ tự cập nhật phức tạp cần thêm **aggregateVersion** hoặc điều kiện cập nhật trạng thái. PostgreSQL **ON CONFLICT** là cú pháp riêng; database khác cần cách tương ứng.

### 6.5. Dispatcher chạy việc ở executor và trả đúng future

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class AsyncOrderDispatcher {
    private final Executor executor;
    private final OrderWriteService orderWriteService;

    public AsyncOrderDispatcher(
            @Qualifier("orderWorkExecutor") Executor executor,
            OrderWriteService orderWriteService) {
        this.executor = executor;
        this.orderWriteService = orderWriteService;
    }

    public CompletableFuture<Void> process(OrderEvent event) {
        return CompletableFuture.runAsync(
                () -> orderWriteService.applyOnce(event),
                executor
        );
    }
}
~~~

Future chỉ **complete thành công sau khi applyOnce(...) trả về**. Vì **OrderWriteService** là bean Spring được gọi qua proxy từ worker thread, **@Transactional** có thể mở/commit DB transaction **trong chính thread thực thi**. Không giả định một transaction ở thread listener tự động được truyền sang thread executor.

Một điều cần tránh:

~~~java
public CompletableFuture<Void> wrong(OrderEvent event) {
    CompletableFuture.runAsync(
            () -> orderWriteService.applyOnce(event), executor);
    return CompletableFuture.completedFuture(null); // Hoàn tất giả!
}
~~~

Đây là **anti-pattern**: future trả về báo thành công ngay dù công việc thật chưa xong. Với async return listener, Spring sẽ ACK theo **future giả**, tạo ra lỗi tương tự void fire-and-forget.

### 6.6. Listener trả future đã nối với business completion

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class AsyncOrderListener {
    private final AsyncOrderDispatcher dispatcher;

    public AsyncOrderListener(AsyncOrderDispatcher dispatcher) {
        this.dispatcher = dispatcher;
    }

    @RabbitListener(
            queues = AsyncAckTopology.QUEUE,
            containerFactory = "asyncAckFactory")
    public CompletableFuture<Void> onOrder(String payload) {
        final OrderEvent event;
        try {
            event = OrderEvent.parse(payload);
        } catch (IllegalArgumentException ex) {
            // Poison message: cho framework reject không requeue.
            return CompletableFuture.failedFuture(
                    new AmqpRejectAndDontRequeueException(
                            "Invalid order event", ex));
        }

        try {
            // Spring giữ delivery Unacked đến khi future này hoàn tất.
            return dispatcher.process(event);
        } catch (RuntimeException ex) {
            // Kể cả lỗi submit executor trước khi future được tạo,
            // vẫn trả một async result thất bại để framework NACK.
            return CompletableFuture.failedFuture(ex);
        }
    }
}
~~~

**Vì sao phải có try/catch ở biên tạo future?** Tài liệu Spring AMQP lưu ý rằng nếu có exception **ngay trong method** khiến async result **chưa được tạo**, ứng dụng phải xử lý để trả về một đối tượng async result thất bại phù hợp. Với ví dụ trên:

- Sai định dạng event → **failed future** chứa **AmqpRejectAndDontRequeueException**, framework có thể reject không requeue để vào DLQ khi DLX được khai báo.
- Work task thành công và DB commit → future hoàn tất thành công → framework ACK.
- Work task lỗi → future hoàn tất exceptionally → framework áp dụng requeue/reject theo loại exception và error policy.
- Executor không nhận task → caller nhận failed future, **không tự đánh dấu đã xử lý thành công**.

**Không gọi** channel.basicAck/basicNack bên trong method này hoặc trong dispatcher. Cơ chế ACK chính thức là **Spring AMQP async-return completion**.

### 6.7. Khi trả về Mono<?> thay cho CompletableFuture<?>

Nếu ứng dụng dùng Reactor, method **@RabbitListener** có thể trả **Mono<?>**. Hãy để Spring subscribe và nhận completion:

~~~java
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Component
public class ReactiveStyleOrderListener {
    private final OrderWriteService writeService;

    public ReactiveStyleOrderListener(OrderWriteService writeService) {
        this.writeService = writeService;
    }

    @RabbitListener(
            queues = AsyncAckTopology.QUEUE,
            containerFactory = "asyncAckFactory")
    public Mono<Void> onOrder(String payload) {
        return Mono.fromRunnable(() ->
                    writeService.applyOnce(OrderEvent.parse(payload)))
                .subscribeOn(Schedulers.boundedElastic())
                .onErrorMap(
                        IllegalArgumentException.class,
                        ex -> new AmqpRejectAndDontRequeueException(
                                "Invalid event", ex))
                .then();
    }
}
~~~

Đây là **phương án thay thế** cho listener trả CompletableFuture, **không chạy cả hai listener cùng queue** nếu chỉ muốn kiểm tra một luồng xử lý. Để dùng Mono cần có **Reactor** tương ứng trên classpath; cấu hình này hợp với tác vụ blocking JDBC nhờ **boundedElastic**, nhưng các giới hạn capacity của scheduler vẫn cần được giám sát.

**Không làm thế này:**

~~~java
@RabbitListener(queues = AsyncAckTopology.QUEUE)
public void wrongReactive(String payload) {
    Mono.fromRunnable(() -> writeService.applyOnce(
            OrderEvent.parse(payload)))
        .subscribe();
    // void return có thể được AUTO ACK trước khi Mono hoàn tất.
}
~~~

**Sự khác biệt:** **return Mono** chuyển completion cho Spring AMQP quản lý; **subscribe trong void method rồi return** làm mất mối liên hệ giữa completion và ACK.

### 6.8. Không nuốt lỗi bằng exceptionally/onErrorResume

Ví dụ sai:

~~~java
return dispatcher.process(event)
        .exceptionally(ex -> {
            log.error("Failed", ex);
            return null; // Future đã chuyển thành COMPLETED SUCCESSFULLY!
        });
~~~

Khi future sau xử lý exception trở thành **thành công**, Spring AMQP có thể ACK dù DB chưa commit. Nếu chỉ muốn log mà giữ trạng thái lỗi, dùng **whenComplete**:

~~~java
return dispatcher.process(event)
        .whenComplete((result, failure) -> {
            if (failure != null) {
                log.error("Order processing failed", failure);
            }
        });
~~~

Đây là các đoạn minh họa nằm trong listener có biến **dispatcher**, **event**, **log** phù hợp; riêng các đoạn không có đầy đủ class/import là ví dụ so sánh hành vi.

Tương tự, với Reactor, **onErrorResume(error -> Mono.empty())** biến kết quả lỗi thành completion thành công. Chỉ làm vậy nếu chính sách nghiệp vụ **cố ý coi lỗi đó là đã xử lý** (ví dụ duplicate đã được xác định chắc chắn), không dùng như cách “ẩn lỗi khỏi log”.

## 7. Cách kiểm soát thấp tầng: ACK thủ công bằng Channel

Một số hệ thống cần tự quyết định ACK/NACK theo callback có sẵn của thư viện, hoặc không thể thay method signature sang future/Mono. Khi đó có thể dùng **@RabbitListener trả void + AcknowledgeMode.MANUAL** và lưu **Channel + deliveryTag** của **chính delivery đó**.

### 7.1. API RabbitMQ Java client

| Lệnh | Ý nghĩa |
| --- | --- |
| **channel.basicAck(tag, false)** | ACK đúng một delivery của tag tương ứng |
| **channel.basicNack(tag, false, true)** | NACK một delivery, **requeue=true** |
| **channel.basicNack(tag, false, false)** | NACK một delivery, **không requeue**; vào DLX khi đã cấu hình phù hợp |
| **channel.basicReject(tag, false)** | Reject một delivery và không requeue |
| **channel.basicAck(tag, true)** | ACK nhiều delivery tới tag đó trên **cùng channel**, không phù hợp cho async callback thông thường |

Delivery tag **không phải** messageId hay eventId. Nó do RabbitMQ cấp cho delivery trên một channel và có thể thay đổi khi message bị redeliver. Phải ACK/NACK bằng **đúng channel đã nhận delivery**, không dùng một RabbitTemplate channel tùy ý.

### 7.2. Manual ACK sau future completion

Đây là **phương án thay thế** cho AsyncOrderListener ở phần 6.6; không triển khai cả hai cùng một queue trong cùng bài thử:

~~~java
import com.rabbitmq.client.Channel;
import java.io.IOException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.support.AmqpHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
public class ChannelManagedAsyncListener {
    private static final Logger log =
            LoggerFactory.getLogger(ChannelManagedAsyncListener.class);

    private final AsyncOrderDispatcher dispatcher;

    public ChannelManagedAsyncListener(AsyncOrderDispatcher dispatcher) {
        this.dispatcher = dispatcher;
    }

    @RabbitListener(
            queues = AsyncAckTopology.QUEUE,
            ackMode = "MANUAL")
    public void onOrder(
            String payload,
            Channel channel,
            @Header(AmqpHeaders.DELIVERY_TAG) long deliveryTag)
            throws IOException {

        final OrderEvent event;
        try {
            event = OrderEvent.parse(payload);
        } catch (IllegalArgumentException invalid) {
            channel.basicReject(deliveryTag, false);
            return;
        }

        final CompletableFuture<Void> result;
        try {
            result = dispatcher.process(event);
        } catch (RuntimeException submitFailure) {
            // Executor chưa nhận task: chưa có kết quả nghiệp vụ.
            channel.basicNack(deliveryTag, false, true);
            return;
        }

        result.whenComplete((ignored, error) -> {
            try {
                if (error == null) {
                    channel.basicAck(deliveryTag, false);
                } else {
                    Throwable cause = error;
                    while (cause instanceof CompletionException
                            && cause.getCause() != null) {
                        cause = cause.getCause();
                    }
                    boolean permanent =
                            cause instanceof AmqpRejectAndDontRequeueException;
                    channel.basicNack(deliveryTag, false, !permanent);
                }
            } catch (IOException | RuntimeException ackFailure) {
                log.error(
                        "ACK/NACK failed on original channel; tag={}",
                        deliveryTag,
                        ackFailure);
                // Không ACK lại trên một channel mới với tag cũ.
            }
        });
    }
}
~~~

**Lợi ích:** container ở **MANUAL**, nên khi method void return sau khi đăng ký callback, RabbitMQ vẫn giữ delivery **Unacked**. Chỉ khi callback nhận kết quả cuối, mã mới ACK/NACK.

**Giới hạn thực tế của ví dụ:**

- Đoạn minh họa requeue lỗi tạm thời bằng **basicNack(..., true)**. Trong production cần **retry có backoff và giới hạn**, nếu không broker có thể tạo vòng requeue nóng liên tục.
- Khi channel/connection chết trước callback, lệnh ACK có thể thất bại. Broker sẽ requeue message chưa ACK khi phát hiện channel đóng; phải chịu được redelivery bằng idempotency.
- Đây là code dùng **Channel từ completion callback có thể chạy ở thread khác**. RabbitMQ Java client không khuyến khích dùng chung Channel tùy tiện giữa threads. ACK **từng delivery với multiple=false** có thể an toàn trong những điều kiện được tài liệu nêu, nhưng cần tránh gọi nhiều thao tác Channel không được đồng bộ hoặc kết hợp ACK hàng loạt trong callback khác thread.
- Nếu ứng dụng có cơ chế đồng thời phức tạp, nên **ưu tiên async return type do Spring quản lý** thay vì tự viết coordination cho ACK từ nhiều worker threads.

### 7.3. Không dùng multiple=true trong callback async

Giả sử một channel có ba delivery chưa xác nhận:

~~~text
tag=11 -> task rất chậm (chưa hoàn tất)
tag=12 -> task nhanh (đã hoàn tất)
tag=13 -> task trung bình (chưa hoàn tất)
~~~

Nếu callback của tag 12 gọi:

~~~java
channel.basicAck(12L, true);
~~~

Broker sẽ ACK các delivery chưa ACK **tới tag 12 trên cùng channel**, bao gồm **tag 11** dù tác vụ của nó chưa hoàn tất. Đây chính là xác nhận quá sớm.

Trong callback hoàn tất độc lập, hãy dùng:

~~~java
channel.basicAck(12L, false);
~~~

Với nhiều threads thao tác cùng Channel, **multiple=true còn có nguy cơ double-ack**, dẫn đến channel-level exception. Không áp dụng batch-ACK khi không quản lý chặt thứ tự hoàn tất và trạng thái mọi tag trên cùng channel.

## 8. Khi async task thất bại: ACK, requeue hay dead-letter?

Kết quả lỗi cần được phân loại; không thể xử lý mọi exception bằng cách ACK cho khỏi kẹt, cũng không nên requeue mọi exception mãi mãi.

| Loại kết quả | Hành vi mong muốn | Vì sao |
| --- | --- | --- |
| Công việc thành công và đã commit side effect cần thiết | **ACK** | Delivery có thể kết thúc |
| Event đã được xác nhận xử lý trước đó bằng khóa idempotency | **ACK** | Bản giao lại không tạo tác dụng phụ mới |
| JSON sai hoặc thiếu field bắt buộc, không thể sửa bằng retry | **Reject/NACK không requeue**; DLQ nếu có | Tránh poison-message loop |
| API phụ thuộc lỗi tạm thời, có khả năng hồi phục | Retry **có giới hạn + backoff**, có thể qua retry queue | Tránh retry nóng, tránh nghẽn |
| Executor đầy hoặc hạ tầng quá tải | Giảm nhận tải, retry an toàn theo chính sách | Không ACK khi công việc chưa được nhận để xử lý |
| Connection/channel mất trước ACK | Không thể kết luận broker đã nhận ACK | Chấp nhận redelivery; consumer idempotent |
| Future không bao giờ complete | Delivery tiếp tục Unacked đến khi bị timeout/đóng channel | Cần timeout và giám sát |

### 8.1. Spring AMQP phân loại failed async result

Theo tài liệu **Asynchronous @RabbitListener Return Types**, khi async result complete exceptionally:

- Với chính sách mặc định (**defaultRequeueRejected=true**), message thường được **requeue**.
- **AmqpRejectAndDontRequeueException** yêu cầu **không requeue**, bất kể defaultRequeueRejected.
- Khi **defaultRequeueRejected=false**, có thể dùng **ImmediateRequeueException** để ép requeue trong trường hợp phù hợp.
- Kết quả còn chịu ảnh hưởng từ exception type, error handler và cấu hình listener container.

Ví dụ trả failed future rõ ràng khi message sai hợp đồng:

~~~java
return CompletableFuture.failedFuture(
        new AmqpRejectAndDontRequeueException(
                "Invalid message, send to DLQ"));
~~~

Để tránh lặp vô hạn với lỗi tạm thời, có thể sử dụng retry advice với giới hạn/backoff, retry queue qua dead-letter/TTL hoặc một scheduler retry có trạng thái. Lựa chọn nào phù hợp tùy yêu cầu thứ tự, latency và độ bền dữ liệu.

**Không làm điều này một cách vô thức:** gặp exception thì trả `CompletableFuture.completedFuture(null)` chỉ để container ACK. Đó là cách đánh dấu thành công sai sự thật, có thể làm mất nhiệm vụ chưa thực hiện.

### 8.2. Dead-letter cần topology đúng

Với queue chính **lab.orders.async** đã có:

~~~text
x-dead-letter-exchange = lab.orders.dlx
x-dead-letter-routing-key = order.failed
~~~

Khi một message được reject/nack **không requeue** và broker dead-letter thành công, nó có thể đi tới **lab.orders.async.dlq** thông qua DLX và binding.

~~~mermaid
flowchart TD
    IN[("lab.orders.async")] --> H["Async @RabbitListener"]
    H -->|"Complete success"| ACK["ACK -> kết thúc delivery"]
    H -->|"Permanent failure"| NACK["Reject / NACK requeue=false"]
    NACK --> DLX{"lab.orders.dlx"}
    DLX --> DLQ[("lab.orders.async.dlq")]
    H -->|"Transient failure"| RET["Retry/backoff có giới hạn"]
~~~

**Không coi DLQ là biện pháp đảm bảo mọi message chắc chắn được lưu**: DLX/binding/queue đích phải tồn tại và có quyền; chính sách dead-letter, loại queue và cơ chế confirm nội bộ có thể ảnh hưởng mức bảo đảm. Cần theo dõi **DLQ Ready**, lỗi khai báo và chỉ số dead-letter.

### 8.3. Đừng để future lỗi bị “biến thành thành công”

Các phép biến đổi trên CompletableFuture/Reactor có thể thay đổi trạng thái cuối:

| Biến đổi | Có giữ lỗi không? | Ảnh hưởng tới ACK |
| --- | --- | --- |
| **whenComplete(...)** chỉ log, không throw mới | Thường **giữ** trạng thái thất bại ban đầu | Framework vẫn thấy lỗi |
| **exceptionally(ex -> null)** | **Không**; biến failure thành success | Có thể ACK dù nhiệm vụ lỗi |
| **handle((x,ex) -> defaultValue)** | Phụ thuộc callback; dễ nuốt lỗi | Có thể ACK nhầm |
| **onErrorResume(ex -> Mono.empty())** | **Không**, nếu trả Mono thành công | Có thể ACK nhầm |
| **CompletableFuture.failedFuture(ex)** | **Có** | Framework có cơ sở NACK/reject |
| **Mono.error(ex)** | **Có** | Framework có cơ sở NACK/reject |

Chỉ phục hồi thành “success” nếu chính sách nghiệp vụ cho phép, ví dụ khi phát hiện **event đã được xử lý và commit** bằng khóa idempotency.

## 9. Backpressure: prefetch và executor phải tương thích

ACK muộn làm message nằm **Unacked** lâu hơn. Đó là hành vi mong đợi khi giữ đúng ngữ nghĩa hoàn tất công việc, nhưng nếu không giới hạn năng lực xử lý, hệ thống có thể tích tụ task ở executor hoặc để broker gửi quá nhiều delivery.

### 9.1. Prefetch giới hạn message chưa ACK

RabbitMQ hỗ trợ **basic.qos/prefetch**; ở Spring Boot dùng:

~~~yaml
spring:
  rabbitmq:
    listener:
      simple:
        acknowledge-mode: manual
        prefetch: 4
        concurrency: 2
~~~

Với hai SMLC consumer và prefetch 4, một trường hợp bình thường là có tới khoảng **8 delivery chưa ACK** trên những consumer đó (trong điều kiện không có giới hạn/chính sách khác). Broker thường ngừng giao thêm tới consumer đã đạt giới hạn cho đến khi có ACK.

Đây là **giới hạn delivery đang bay (in flight)**, không phải giới hạn tuyệt đối số task mà toàn bộ ứng dụng có thể tạo từ nguồn khác. Với nhiều instance, số delivery có thể nhân lên theo consumer count.

### 9.2. Phối hợp worker pool và prefetch

Trong ví dụ:

~~~text
Listener container: 2 consumers x prefetch 4 ≈ 8 Unacked tối đa
Work executor:       4 worker threads + hàng đợi 16 task

Message chỉ được ACK khi task đã hoàn tất.
~~~

Nếu mỗi task xử lý vài giây, tỷ lệ ACK chậm làm broker giữ delivery Unacked; Ready có thể tăng khi publisher gửi nhanh hơn consumer. Tăng prefetch lên 100 không tự làm database nhanh hơn; nó có thể chỉ chuyển backlog từ broker vào client, tăng thời gian chờ và memory.

**Quy trình điều chỉnh:**

1. Đo p50/p95/p99 thời gian xử lý nghiệp vụ.
2. Đo số worker đang bận, kích thước hàng đợi executor và tỷ lệ task bị từ chối.
3. Đo Ready, Unacked, deliver rate, ACK rate và redelivery rate ở RabbitMQ.
4. Bắt đầu với prefetch nhỏ khi tác vụ chậm, rồi tăng từng bước dựa trên số liệu throughput/latency.
5. Cân nhắc thêm consumer hoặc instance nếu bottleneck nằm ở CPU và hệ thống đích còn sức chịu tải; nếu DB/API đã nghẽn, tăng consumer có thể làm tình hình tệ hơn.

**Nếu dùng Single Active Consumer (SAC):** dù có nhiều listener đang đăng ký, broker chỉ giao delivery cho một active consumer của queue. Mở rộng số standby không làm cùng queue xử lý song song nhanh hơn; vẫn cần kiểm soát prefetch, task concurrency và phạm vi thứ tự.

### 9.3. Executor bị từ chối task

Khi **ThreadPoolTaskExecutor** đầy, **CompletableFuture.runAsync(...)** có thể ném exception ngay lúc submit, **trước khi Future được tạo**. Đó là lý do **AsyncOrderListener.onOrder(...)** ở phần 6 bắt RuntimeException và trả **failedFuture(ex)**.

Điều đó **không tự làm retry an toàn**: nếu broker requeue ngay khi hệ thống vẫn quá tải, message có thể quay lại lập tức, gây vòng lặp nóng. Cần cơ chế giảm nhận tải, retry với backoff, giới hạn số consumer hoặc một retry queue có độ trễ; xem biểu đồ áp lực executor trước khi chỉnh lại prefetch.

## 10. Timeout, hủy tác vụ và thay đổi connection

Async không có deadline là một điểm yếu vận hành. Một Future không complete khiến message còn Unacked, chiếm prefetch và có thể gây timeout phía RabbitMQ nếu quá thời gian cho phép của broker.

### 10.1. Xác định timeout nghiệp vụ

Ví dụ có deadline ở tầng async:

~~~java
return dispatcher.process(event)
        .orTimeout(30, java.util.concurrent.TimeUnit.SECONDS);
~~~

Đoạn trên minh họa trong listener trả CompletableFuture. Nếu future không hoàn tất trong **30 giây**, nó có thể complete exceptionally; framework xử lý thất bại theo error policy. **Tuy nhiên, CompletableFuture timeout không bảo đảm công việc nền bị hủy**. Task có thể tiếp tục ghi DB hoặc gọi API sau khi message đã bị requeue cho consumer khác.

Điều này tạo rủi ro:

~~~text
Worker A bắt đầu tác vụ M1
    |
    +-- Deadline 30 giây hết
    +-- Future báo lỗi -> broker requeue M1
    +-- Worker B nhận lại M1
    |
    +-- Worker A vẫn có thể tiếp tục gọi DB/API
~~~

Do đó, khi dùng timeout:

- Phối hợp **timeout thực tế** của JDBC/HTTP/transaction và quy tắc hủy tác vụ, không chỉ timeout của CompletableFuture.
- Dùng **idempotency key** và điều kiện cập nhật DB, hoặc cơ chế fencing/versioning khi công việc có thể còn chạy sau thời điểm mất quyền nhận message.
- Tránh retry ngay nếu hệ thống đích chưa thoát khỏi trạng thái lỗi hoặc tải cao.
- Kiểm tra hậu quả nếu task cũ và task được redeliver cùng thực hiện side effect ngoài DB.

### 10.2. Broker có consumer delivery acknowledgement timeout

RabbitMQ có cơ chế giám sát delivery chưa ACK quá lâu theo cấu hình broker/queue. Nếu consumer giữ message Unacked vượt ngưỡng và broker đóng channel, các delivery chưa ACK có thể được **requeue**. Tên và ngưỡng cấu hình phụ thuộc phiên bản/triển khai RabbitMQ; không giả định luôn là một số phút cố định.

**Phân biệt**:

- **Heartbeat** phát hiện sự cố connection.
- **Application task timeout** giới hạn thời gian thực hiện nghiệp vụ.
- **Consumer acknowledgement timeout** bảo vệ broker khỏi delivery nằm Unacked quá lâu.

Đặt các giới hạn này có chủ đích; không chọn timeout async quá ngắn so với thời gian xử lý thực tế rồi liên tục phát sinh duplicate.

### 10.3. Connection mất trước hoặc sau ACK

~~~mermaid
flowchart TD
    S["Task đã commit DB"] --> A{"Broker có nhận ACK?"}
    A -->|"Có"| OK["Message kết thúc trên queue"]
    A -->|"Không / không rõ"| RE["Connection mất -> có thể redelivery"]
    RE --> D["Kiểm tra eventId đã xử lý"]
    D -->|"Đã commit"| SKIP["Bỏ qua side effect, ACK lần mới"]
    D -->|"Chưa commit"| PROCESS["Xử lý/commit rồi ACK"]
~~~

**Delivery tag không sống qua lần giao mới.** Khi message redeliver, broker cấp tag phù hợp channel mới. Không lưu tag cũ để ACK một delivery mới, không ACK bằng channel khác, và không giả định một lỗi gửi ACK luôn có thể khắc phục bằng cách gọi lại trên channel mới.

## 11. Manual ACK không phải exactly-once

Có hai cửa sổ lỗi quan trọng:

| Cửa sổ lỗi | Nếu không phòng vệ | Cách khắc phục |
| --- | --- | --- |
| **ACK trước DB commit**, rồi crash | Broker không redeliver; cập nhật nghiệp vụ bị mất | Chỉ ACK sau khi future có bằng chứng hoàn tất/commit |
| **DB commit trước ACK**, rồi mất connection | Broker có thể redeliver; side effect lặp | Idempotency trong transaction với side effect |

Không có thứ tự ACK/commit đơn giản nào tự tạo **atomic commit qua RabbitMQ và DB**. Ngay cả khi bật **channelTransacted** cho AMQP hoặc dùng @Transactional ở Java, cần hiểu phạm vi từng transaction. Một transaction database độc lập không tự biến thành distributed transaction ACID với broker.

### Mẫu xử lý an toàn theo eventId

~~~text
Delivery M1 (eventId = E-1001)
    |
    v
BEGIN DB TRANSACTION
  INSERT processed_event(consumer, eventId)
      ON CONFLICT DO NOTHING
  Nếu INSERT mới:
      ghi side effect nghiệp vụ
  Nếu đã tồn tại:
      không làm side effect lần hai
COMMIT
    |
    v
Future complete successfully
    |
    v
Consumer ACK
~~~

Khi side effect là **API thanh toán bên ngoài**, DB transaction của consumer không tự kiểm soát tính nguyên tử của HTTP request. Cần dùng **idempotency key ở hệ thống đích**, durable outbox hoặc đối soát phù hợp với API.

### Producer và consumer cùng phải tin cậy

Ngược lại chiều consume, publisher cũng có thể bị mất kết quả confirm, gửi lại sự kiện và tạo bản sao. Vì vậy luồng hoàn chỉnh có thể cần:

- **RabbitTemplate** publish với publisher confirms/returns và định tuyến đúng exchange/binding.
- **Transactional outbox** ở producer nếu sự kiện cần tồn tại bền cùng transaction nghiệp vụ.
- **eventId ổn định** xuyên retry/publish lại và redelivery.
- **Consumer async acknowledgement** chỉ sau khi xử lý hoàn tất.
- **Idempotent consumer** và retry/dead-letter có kiểm soát.

## 12. Bài thực hành: chứng minh ACK chỉ xuất hiện sau khi task hoàn tất

Mục tiêu là quan sát thông điệp đi qua ba giai đoạn:

~~~text
Ready -> Unacked (worker đang xử lý) -> ACK, rời queue
~~~

**Các thành phần của bài thực hành:**

1. RabbitMQ có plugin **Management** (thường ở cổng **15672** trong lab).
2. PostgreSQL có bảng **processed_event**, **order_projection** như phần 6.
3. Các bean **AsyncAckTopology**, **AsyncAckContainerConfig**, **OrderWorkExecutorConfig**, **OrderWriteService**, **AsyncOrderDispatcher**, **AsyncOrderListener** và **AsyncOrderPublisher**.
4. Chỉ bật **một implementation listener** tại một thời điểm; không bật đồng thời listener trả future, listener reactive và listener tự ACK channel trên cùng queue.

### 12.1. Tạo một delay có kiểm soát để quan sát Unacked

Trong môi trường lab, có thể tạm thay đổi hàm dispatcher để **đợi 5 giây trước khi bắt đầu DB transaction**:

~~~java
public CompletableFuture<Void> process(OrderEvent event) {
    return CompletableFuture.runAsync(() -> {
        try {
            Thread.sleep(5000);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", ex);
        }
        orderWriteService.applyOnce(event);
    }, executor);
}
~~~

Chỉ dùng `Thread.sleep` để **mô phỏng xử lý chậm** trong lab; không dùng sleep làm chiến lược retry hay rate limiting production. Đoạn này chạy trên executor thread, **không giữ DB transaction đang mở trong lúc sleep**.

### 12.2. Phát một message bằng RabbitTemplate

Để gọi publisher trong lab mà không xây API riêng, có thể thêm ApplicationRunner có cờ tắt mặc định:

~~~java
import java.util.UUID;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
class LabSenderConfig {

    @Bean
    ApplicationRunner sendDemo(
            AsyncOrderPublisher publisher,
            Environment environment) {
        return args -> {
            if (!environment.getProperty(
                    "demo.publish-on-start", Boolean.class, false)) {
                return;
            }

            String eventId = UUID.randomUUID().toString();
            publisher.publish(eventId, "O-1001");
        };
    }
}
~~~

Khi bật **demo.publish-on-start=true**, runner tạo **một sự kiện logic mới** để thử. Đối với **retry của cùng sự kiện**, phải giữ eventId đã tạo và **không chạy lại runner để giả lập publish retry**, vì lần chạy mới sẽ có UUID mới. Để kiểm tra dedupe, dùng cùng eventId và gọi **publisher.publish(eventId, "O-1001")** hai lần trong một luồng lab có chủ đích.

### 12.3. Quan sát broker từng thời điểm

1. Khởi động RabbitMQ, PostgreSQL và ứng dụng; xác minh queue **lab.orders.async**, DLQ và binding tồn tại.
2. Gửi một message qua **AsyncOrderPublisher**.
3. Trong khoảng 5 giây chờ task, mở **RabbitMQ Management → Queues → lab.orders.async**.
4. Quan sát **Unacked** có thể tăng trong khi worker đang chạy; message chưa bị ACK chỉ vì listener trả **CompletableFuture**.
5. Sau khi workService commit và future complete, kiểm tra **Unacked giảm**, **ACK rate tăng** và bảng **processed_event** có eventId.
6. Dùng cùng eventId publish thêm một bản, xác nhận service bỏ qua side effect trùng nhưng listener vẫn complete thành công, broker vẫn ACK lần delivery mới.

Số liệu Management có độ trễ cập nhật và message có thể được giao/ACK nhanh hơn kỳ lấy mẫu. Với delay 5 giây sẽ dễ quan sát hơn; nếu khó, kết hợp log và biểu đồ rates.

### 12.4. Mô phỏng message vĩnh viễn không hợp lệ

Gửi một body không đúng mẫu `eventId|orderId`, ví dụ:

~~~text
not-an-event
~~~

Listener ở phần 6.6 sẽ trả **failed future** chứa **AmqpRejectAndDontRequeueException**. Với DLX hợp lệ, message có thể xuất hiện ở **lab.orders.async.dlq** thay vì được requeue mãi.

Kiểm tra:

- Handler không ghi projection cho body không hợp lệ.
- Consumer không tự sinh eventId mới cho message lỗi.
- DLQ nhận message và có metadata dead-letter để chẩn đoán.
- Message không quay lại queue gốc liên tục.

Nếu không thấy DLQ, kiểm tra binding/queue arguments, quyền, phiên bản broker, logs và error handler. Không được kết luận message đã vào DLQ chỉ vì listener ném một exception.

### 12.5. Mô phỏng mất connection khi còn Unacked

Thử nghiệm trong **lab**:

1. Gửi một message hợp lệ và chờ đến khi thấy **Unacked**.
2. Dừng mạnh instance consumer hoặc đóng connection phục vụ consumer từ Management, chỉ trong môi trường không có dữ liệu quan trọng.
3. Sau khi broker phát hiện channel/connection đóng, message **chưa ACK** có thể trở lại Ready hoặc được giao cho consumer khác.
4. Chạy lại consumer, quan sát **redelivered** và trạng thái idempotency.

Nếu task đã commit trước khi connection mất nhưng ACK chưa tới broker, lần giao lại vẫn phải an toàn. Đừng kỳ vọng Spring AMQP có thể gửi ACK qua channel cũ sau khi mất connection.

## 13. Quan sát async acknowledgement trong môi trường vận hành

Trong RabbitMQ Management, các chỉ số quan trọng:

| Chỉ số | Ý nghĩa đối với manual/async ACK |
| --- | --- |
| **Messages Ready** | Bao nhiêu message chưa được broker giao |
| **Messages Unacked** | Bao nhiêu delivery đã giao nhưng chưa được ACK |
| **Deliver rate** | Tốc độ broker giao message cho consumer |
| **Ack rate** | Tốc độ broker nhận ACK |
| **Redelivered rate** | Tần suất có delivery được giao lại |
| **Consumers** | Số subscription, cần đối chiếu concurrency/replica |
| **Connection/Channel status** | Phát hiện reconnect, channel exception, consumer timeout |
| **DLQ Ready / dead-letter rate** | Mức lỗi bị reject/dead-letter |

Nếu RabbitMQ chạy bằng Docker Compose có service tên **rabbitmq**, dùng:

~~~bash
docker compose exec rabbitmq rabbitmqctl list_queues -p / name consumers messages_ready messages_unacknowledged
docker compose exec rabbitmq rabbitmqctl list_channels connection number consumer_count
~~~

Các lệnh này chỉ thể hiện trạng thái broker và có thể khác tên cột theo phiên bản. Để chứng minh **side effect đã commit**, phải quan sát thêm database hoặc hệ thống đích; **Unacked=0** không tự nói mọi công việc nghiệp vụ thành công vì message có thể đã bị reject/loại hoặc đưa vào DLQ.

### Log và metric của ứng dụng

Log nên có:

~~~text
eventId=e5b8... queue=lab.orders.async
phase=received deliveryTag=12

eventId=e5b8... phase=business_committed durationMs=5030
eventId=e5b8... phase=async_completed outcome=SUCCESS
~~~

Với async-return listener, framework là bên gửi ACK; log **async_completed** không phải xác nhận broker đã thực sự nhận ACK qua network. Nếu cần kiểm toán end-to-end, theo dõi trạng thái DB cùng số liệu broker và log connection.

Các metric hữu ích:

- **In-flight async task count** và tuổi của task lâu nhất.
- **Executor active threads, task queue size, rejected tasks**.
- **Business processing latency** theo queue/eventType.
- **Listener failures** phân loại lỗi transient/permanent.
- **RabbitMQ Ready/Unacked, consumer disconnects, dead-letter backlog**.

Không nên đặt **eventId** duy nhất của mọi message vào metric labels do cardinality rất cao. EventId thích hợp để truy vết trong log/trace có kiểm soát dữ liệu nhạy cảm.

## 14. Khắc phục lỗi thường gặp

| Triệu chứng | Nguyên nhân điển hình | Hướng khắc phục |
| --- | --- | --- |
| Listener void return ngay, queue Unacked giảm nhanh dù DB chưa ghi | **AUTO ACK** sau method return | Trả **CompletableFuture/Mono** hoặc dùng MANUAL ACK sau completion |
| Dùng CompletableFuture nhưng message vẫn ACK trước task thật | Trả **completedFuture(null)** hoặc future không đại diện công việc thật | Return chính future của DB/API operation |
| Future lỗi mà broker vẫn ACK | **exceptionally/onErrorResume** nuốt lỗi | Giữ exceptional completion hoặc xử lý lỗi có chủ đích |
| Đã cấu hình MANUAL nhưng Unacked cứ tăng | Một nhánh handler không ACK/NACK; Future không complete | Bảo đảm mọi nhánh kết thúc, có timeout/giám sát |
| basicAck gây **unknown delivery tag** | ACK trùng, dùng tag sai channel hoặc dùng multiple=true ngoài ý muốn | Mỗi delivery ACK một lần, đúng channel, **multiple=false** |
| DB commit rồi message bị xử lý lại | ACK thất lạc hoặc connection đóng trước ACK | Dedupe **consumer+eventId** cùng DB transaction |
| Lỗi parse tạo vòng requeue | Không phân loại poison message | **AmqpRejectAndDontRequeueException**, DLQ và retry policy |
| Lỗi API tạm thời gây requeue nóng | Requeue=true không có backoff | Retry có độ trễ và giới hạn; kiểm tra external dependency |
| Executor đầy, task chưa chạy nhưng listener báo success | Bỏ qua lỗi submit hoặc trả future thành công | Trả failed future và thiết kế backpressure |
| Timeout làm hai worker cùng ghi | Task cũ chưa dừng, message đã redeliver | Timeout thực của side effect, idempotency/fencing |
| Dùng AUTO và tự basicAck | Double ACK, channel có thể bị đóng | Chọn một cơ chế ACK nhất quán |
| Đã bật MANUAL nhưng không thấy DLQ | Queue chưa có DLX/binding hoặc lỗi route dead-letter | Kiểm tra topology và Management |
| Channel bị đóng do delivery ACK timeout | Task mất quá lâu hoặc future kẹt | Đặt deadline hợp lý, đo latency và cấu hình timeout |
| Chuyển từ SMLC sang DMLC nhưng cấu hình không có hiệu lực | Listener dùng factory khác | Kiểm tra **containerFactory** trên annotation và properties tương ứng |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Listener có chữ ký `void handle(String payload)`, gọi `CompletableFuture.runAsync(...)` rồi return bình thường. Trong AUTO ACK, chuyện gì có thể xảy ra trước khi async task hoàn tất?

**Câu 2.** Trong Spring AMQP hiện đại, @RabbitListener trả **CompletableFuture<Void>**. Khi Future chưa complete, container có nên ACK ngay sau khi listener return không?

**Câu 3.** Tại sao không nên dùng **exceptionally(ex -> null)** chỉ để log lỗi của Future trả cho listener?

**Câu 4.** Có ba delivery tag 11, 12, 13 trên cùng channel. Task của tag 12 xong trước tag 11. Có nên gọi **basicAck(12,true)** không? Vì sao?

**Câu 5.** DB commit thành công nhưng connection mất trước ACK. Broker có thể redeliver không? Cần bảo vệ gì?

**Câu 6.** Future không complete và broker giữ message Unacked nhiều phút. Bạn phải theo dõi những loại timeout nào?

**Câu 7.** Với async-return listener, khi message sai cấu trúc vĩnh viễn, làm sao để tránh requeue vô hạn và đưa nó về DLQ?

**Câu 8.** Một Future báo timeout sau 30 giây. Điều đó có chắc worker đang chạy JDBC/API call đã dừng không?

**Câu 9.** Có thể vừa trả CompletableFuture để Spring ACK theo completion, vừa tự basicAck trên cùng message không?

**Câu 10.** Tại sao tăng prefetch từ 4 lên 100 không đảm bảo ứng dụng xử lý nhanh hơn khi database đã đạt giới hạn?

**Đáp án gợi ý:**

1. Container có thể **ACK quá sớm** vì method void kết thúc trước khi async task hoàn tất.
2. **Không.** Spring dùng async completion để ACK/NACK; container cần **MANUAL** về mặt ngữ nghĩa.
3. Vì phép biến đổi đó biến exceptional Future thành **success**, dẫn đến ACK khi nghiệp vụ chưa hoàn tất.
4. **Không.** multiple=true ACK cả tag 11 còn chưa xong; dùng **basicAck(12,false)**.
5. **Có.** Dedupe theo eventId với side effect trong cùng transaction phù hợp.
6. **Application task timeout**, **consumer acknowledgement timeout**, connection/heartbeat và timeout của DB/API bên ngoài.
7. Trả failed future chứa **AmqpRejectAndDontRequeueException** và bảo đảm DLX/binding/DLQ hợp lệ.
8. **Không.** CompletableFuture timeout có thể không hủy công việc thực; cần cancellation/deadline của tác vụ và idempotency.
9. **Không.** Hai cơ chế ACK trên cùng delivery gây double ACK và channel exception.
10. Prefetch chỉ mở rộng lượng message **in flight**; bottleneck DB vẫn giữ nguyên, Unacked/memory còn có thể tăng.

## 16. Checklist trước khi triển khai

Trước khi đưa manual/async ACK vào production, hãy kiểm tra:

1. **Ai sở hữu ACK?** Spring AMQP async-return adapter hay code dùng Channel? Chỉ chọn **một**.
2. **Điều gì là hoàn tất?** Future/Mono có complete **sau khi** commit/call cần thiết thành công không?
3. **Có nuốt exception không?** Kiểm tra exceptionally, handle, onErrorResume và mọi fallback.
4. **Lỗi synchronous trước khi tạo Future?** Có trả failed future phù hợp thay vì ném lỗi không được kiểm soát không?
5. **Manual Channel ACK:** dùng đúng delivery tag/channel và **multiple=false** khi callback bất đồng bộ không?
6. **Backpressure:** prefetch × consumer count, executor size/queue và hệ thống đích có tương thích không?
7. **Timeout/cancellation:** Task quá lâu, ACK timeout và connection recovery đã được kiểm thử chưa?
8. **Retry/dead-letter:** lỗi permanent có bị loại khỏi vòng lặp, lỗi transient có backoff và giới hạn không?
9. **Idempotency:** eventId có ổn định qua publish retry và consumer redelivery, side effect có dedupe atomic chưa?
10. **Observability:** có Ready/Unacked, ACK/redelivery, DLQ, executor saturation và business latency không?
11. **Topology:** exchange, queue, binding, DLX và quyền RabbitMQ đã được khai báo đúng chưa?
12. **Recovery:** đã thử DB commit rồi mất ACK, future không complete và consumer restart chưa?

**Kết luận:** mục tiêu của **manual ACK khi xử lý bất đồng bộ** không phải “tự gửi ACK bằng tay bằng mọi giá”, mà là bảo đảm **RabbitMQ chỉ nhận ACK sau khi công việc thực sự hoàn tất**. Với Spring AMQP, **@RabbitListener trả CompletableFuture/Mono** thường là cách rõ ràng nhất để trì hoãn ACK; **Channel.basicAck/basicNack** là lựa chọn thấp tầng cần quản lý delivery tag, callback và thread safety kỹ hơn. Kết hợp đúng thời điểm ACK với **RabbitTemplate, exchange/queue/binding, retry, dead-letter, idempotency, giao dịch và quan sát** mới giúp pipeline xử lý bất đồng bộ bền vững.

### Tài liệu đọc thêm

- [Spring AMQP – Asynchronous @RabbitListener Return Types](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-returns.html)
- [Spring AMQP – Listener Container Configuration](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html)
- [Spring AMQP – Annotation-driven Listener Endpoints](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven.html)
- [Spring AMQP – Error Handling](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/error-handling.html)
- [RabbitMQ – Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms)
- [RabbitMQ – Java Client API: Channels and Concurrency](https://www.rabbitmq.com/client-libraries/java-api-guide)
- [RabbitMQ – Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx)
