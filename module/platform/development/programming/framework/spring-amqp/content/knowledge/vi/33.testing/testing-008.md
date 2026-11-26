# Kiểm thử topology, converter và producer/consumer khác ngôn ngữ

## 1. Tại sao test “đã gọi `convertAndSend`” chưa đủ?

Trong ứng dụng dùng **Spring AMQP** và **RabbitMQ**, producer có thể publish thành công theo góc nhìn của Java nhưng consumer vẫn không nhận được dữ liệu đúng:

- Exchange tồn tại nhưng **binding** sai routing key; message không tới queue đích.
- `RabbitTemplate` gửi object Java bằng một converter, còn consumer Python chỉ hiểu UTF-8 JSON; body hoặc `contentType` không đúng hợp đồng.
- Cả producer và consumer Java cùng dùng header `__TypeId__` chứa tên class Java nên chạy tốt nội bộ, nhưng service Node.js/Python không hiểu class đó.
- Consumer parse được dữ liệu nhưng ACK trước khi database commit; khi lỗi xảy ra, message đã bị xóa.
- Một event được giao lại, service khác ngôn ngữ xử lý **hai lần** vì không dùng chung quy tắc idempotency.

Bài **“Kiểm thử topology, converter và producer/consumer khác ngôn ngữ”** thuộc chương **Kiểm thử** trong module `SPRING_AMQP`. Ta sẽ kiểm tra exchange, queue và binding trên broker thật; kiểm thử `MessageConverter`; thiết kế **wire contract độc lập Java**; sau đó thực hiện hai chiều **Java → Python** và **Python → Java** với dữ liệu, metadata và kết quả nghiệp vụ có thể đối chiếu.

Sau khi học, bạn cần viết được một test plan chứng minh:

1. **Route đúng:** event có routing key hợp lệ được đưa tới queue cần thiết; routing key sai được phát hiện, không âm thầm mất event.
2. **Giải mã đúng:** cùng body JSON/metadata được nhiều ngôn ngữ hiểu giống nhau.
3. **Xử lý đúng:** lỗi, ACK, retry, DLQ, duplicate và schema version có kết quả nhất quán.
4. **Phát hiện sai lệch:** một thay đổi exchange type, queue arguments, converter hoặc DTO làm test thất bại trước khi deploy.

## 2. Phân lớp kiểm thử

```mermaid
flowchart TB
    U["Unit tests<br/>DTO, schema, serializer, validator"] --> I["Spring AMQP component tests<br/>listener invocation, converter config"]
    I --> B["Broker integration tests<br/>exchange, queue, binding, confirms, ACK"]
    B --> P["Polyglot contract tests<br/>Java ↔ Python/Node.js"]
    P --> F["Failure & recovery tests<br/>redelivery, retry, DLQ, reconnect"]
```

| Lớp | Môi trường | Nên kiểm tra | Không chứng minh được |
| --- | --- | --- | --- |
| Unit | JVM, không broker | JSON schema, Jackson mapping, validation, idempotency logic | Broker route thật, xác nhận gửi, redelivery |
| `TestRabbitTemplate` hoặc mock | Spring context, không broker thật | Listener method, chuyển đổi/dispatch ở phạm vi mô phỏng | Binding, exchange type, queue durability, network failure |
| Broker integration | RabbitMQ Testcontainers/broker thử nghiệm | Declaration, routing, publisher confirms, ACK/reject, DLX | Service Python/Node hiểu contract nếu chưa chạy chúng |
| Polyglot contract | RabbitMQ thật + hai client khác ngôn ngữ | Bytes, charset, properties, JSON schema, hai chiều giao nhận | Độ tin cậy khi crash nếu chưa fault-inject |
| Fault injection | Broker và DB thử nghiệm | Lost confirm, duplicate, retry/DLQ, commit/ACK window, reconnect | Tính đúng trong mọi tình huống chưa được mô hình hóa |

Các công cụ `spring-rabbit-test` như `@RabbitListenerTest`, `RabbitListenerTestHarness`, `@SpringRabbitTest` và `TestRabbitTemplate` hữu ích cho lớp kiểm thử component. **Không dùng kết quả `TestRabbitTemplate` để khẳng định binding trên RabbitMQ là đúng**: template này định tuyến trực tiếp tới listener trong test context theo tên queue, không thực hiện exchange routing trên broker thật.

## 3. Thiết kế topology mẫu và các bất biến cần test

Ta có sự kiện `OrderCreated` từ ứng dụng đặt hàng:

```mermaid
flowchart LR
    J["Java / Python producer"] -->|"orders.created"| X["orders.events.x<br/>direct, durable"]
    X -->|"orders.created"| Q["orders.created.q<br/>durable"]
    Q --> L["Java / Python consumer"]
    Q -->|"reject requeue=false"| DLX["orders.dead.x"]
    DLX -->|"orders.failed"| DLQ["orders.dead.q"]
```

Một topology đúng cần chứng minh **nhiều bất biến cùng lúc**:

| Bất biến | Phép kiểm thử | Dấu hiệu lỗi |
| --- | --- | --- |
| `orders.events.x` là direct exchange durable | Khai báo trên broker thử, inspect type/durable | Mismatch dẫn đến channel error `PRECONDITION_FAILED` |
| `orders.created.q` tồn tại, durable | Passive declare hoặc `AmqpAdmin.getQueueProperties` | `404 NOT_FOUND` nếu queue thiếu |
| Binding có routing key `orders.created` | Publish event có ID duy nhất, đọc đúng queue | Event không xuất hiện ở queue, dù queue tồn tại |
| Sai key không được coi là đã route | `mandatory=true` + returns, đối chiếu ID | Publish có thể được confirm ACK nhưng không tới queue |
| Dead-letter đúng đích | Reject không requeue, xác minh event ở `orders.dead.q` | Event mất hoặc vòng retry sai |
| Queue arguments không bị đổi ngoài ý muốn | So sánh expected vs actual và kiểm tra redeclare | `PRECONDITION_FAILED` khi khác DLX/TTL/queue type |
| Consumer dùng đúng virtual host | Kiểm tra `ConnectionFactory`, auth, vhost | Client nhìn topology của vhost khác |

### 3.1. Khai báo bằng Spring AMQP

Ví dụ Java 17+, Spring Boot 3.x/Spring AMQP 3.x. Các tên cố định phục vụ lab; khi CI chạy song song, nên đặt namespace riêng theo test suite hoặc dùng broker container riêng.

```java
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Declarables;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderContractTopology {

    @Bean
    public Declarables orderContractDeclarables() {
        DirectExchange events =
                new DirectExchange("orders.events.x", true, false);
        DirectExchange dead =
                new DirectExchange("orders.dead.x", true, false);

        Queue work = QueueBuilder.durable("orders.created.q")
                .deadLetterExchange("orders.dead.x")
                .deadLetterRoutingKey("orders.failed")
                .build();
        Queue deadQueue =
                QueueBuilder.durable("orders.dead.q").build();

        return new Declarables(
                events, dead, work, deadQueue,
                BindingBuilder.bind(work)
                        .to(events).with("orders.created"),
                BindingBuilder.bind(deadQueue)
                        .to(dead).with("orders.failed")
        );
    }
}
```

Đối với production, có thể ưu tiên **RabbitMQ policies** cho các giới hạn phù hợp (TTL/DLX) để giảm nguy cơ thay immutable queue arguments. Trong test, định nghĩa topology phải khớp với cách provision thực tế. Không xóa queue đang có dữ liệu chỉ vì một test phát hiện mismatch.

### 3.2. Broker có thể xác nhận publish nhưng message không tới queue

Trong AMQP 0-9-1, `basic.publish` đến một **exchange tồn tại** nhưng **không có binding phù hợp** có thể bị broker drop nếu `mandatory=false`. Publisher confirm ACK chỉ xác nhận broker đã xử lý publish, **không chứng minh message được định tuyến vào queue**. Với yêu cầu không được mất event, bật `mandatory=true`, publisher returns và verifies tương quan `CorrelationData`.

Đối với **exchange không tồn tại**, broker có thể đóng channel bằng protocol exception. Do đó một test topology phải phân biệt **unroutable** với **exchange missing**, chứ không chỉ kiểm tra có exception hay không.

## 4. Dùng Testcontainers để kiểm thử topology trên RabbitMQ thật

Thư viện gợi ý cho Spring Boot 3.x:

```gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-amqp")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.boot:spring-boot-testcontainers")
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:rabbitmq")
    testImplementation("org.springframework.amqp:spring-rabbit-test")
}
```

Spring Boot BOM hoặc dependency management phải giữ các version tương thích. CI cần có Docker runtime được cho phép, đủ tài nguyên kéo và chạy RabbitMQ image. Test này **không** dựa vào một broker ở `localhost:5672` đang được developer chạy tình cờ.

Các snippet bên dưới dùng **Testcontainers Java 1.x** (artifact `org.testcontainers:rabbitmq`, package `org.testcontainers.containers.RabbitMQContainer`) phổ biến với Spring Boot 3.x. Khi dùng **Testcontainers 2.x**, kiểm tra module `org.testcontainers:testcontainers-rabbitmq` và import `org.testcontainers.rabbitmq.RabbitMQContainer` theo tài liệu phiên bản; đừng phối hợp dependency 2.x với ví dụ import 1.x một cách máy móc.

### 4.1. Tạo broker container và bind configuration

```java
import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.AmqpAdmin;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Declarables;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.core.ReturnedMessage;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.junit.jupiter.api.Assertions.*;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

@SpringBootTest(properties = {
        "spring.rabbitmq.publisher-returns=true",
        "spring.rabbitmq.template.mandatory=true"
})
@Testcontainers
class OrderTopologyIT {
    private static final String X = "it.order.events.x";
    private static final String Q = "it.order.created.q";

    @Container
    static final RabbitMQContainer rabbit = new RabbitMQContainer(
            DockerImageName.parse("rabbitmq:4-management"));

    @DynamicPropertySource
    static void rabbitProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.rabbitmq.host", rabbit::getHost);
        registry.add("spring.rabbitmq.port", rabbit::getAmqpPort);
        registry.add("spring.rabbitmq.username", rabbit::getAdminUsername);
        registry.add("spring.rabbitmq.password", rabbit::getAdminPassword);
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class Topology {
        @Bean
        Declarables integrationTopology() {
            DirectExchange exchange =
                    new DirectExchange(X, true, false);
            Queue queue = QueueBuilder.durable(Q).build();
            return new Declarables(
                    exchange,
                    queue,
                    BindingBuilder.bind(queue).to(exchange)
                            .with("order.created"));
        }
    }

    @Autowired
    AmqpAdmin admin;

    @Autowired
    RabbitTemplate template;

    @Test
    void declarationAndBindingReallyWork() {
        // Trong ứng dụng test chỉ dùng bộ topology IT này,
        // không có @RabbitListener khác consume cùng queue.
        assertNotNull(admin.getQueueProperties(Q));

        // Kết nối thực đến broker: kiểm tra binding gián tiếp.
        String id = UUID.randomUUID().toString();
        MessageProperties props = new MessageProperties();
        props.setContentType("application/json");
        props.setContentEncoding("UTF-8");
        props.setMessageId(id);
        String json = """
                {"eventId":"%s","schemaVersion":1,"orderId":"ORD-42"}
                """.formatted(id);

        template.send(X, "order.created",
                new Message(
                        json.getBytes(StandardCharsets.UTF_8), props));

        Message received = template.receive(Q, 10_000);
        assertNotNull(received, "Binding must route event to queue");
        assertEquals(id, received.getMessageProperties().getMessageId());
        assertEquals(json,
                new String(received.getBody(), StandardCharsets.UTF_8));
    }

    @Test
    void unroutableMessageMustBeReturned() throws Exception {
        // Không chạy song song test khác dùng cùng RabbitTemplate callback.
        CompletableFuture<ReturnedMessage> signal =
                new CompletableFuture<>();
        template.setReturnsCallback(signal::complete);

        template.convertAndSend(
                X, "routing.key.not.bound", "unroutable-fixture");

        ReturnedMessage returned = signal.get(10, TimeUnit.SECONDS);
        assertEquals("routing.key.not.bound", returned.getRoutingKey());
    }
}
```

Đây là **mẫu integration test tự chứa phần chính**, giả định test được chạy trong một Spring Boot app có auto-configuration cho AMQP. Lớp `@TestConfiguration` lồng trong test cung cấp exchange, queue và binding test. Test thứ hai xác minh **returned message** bằng publisher returns đã bật và `mandatory=true`; nó không thay thế publisher confirms. Phải cô lập các test suite để chúng không cùng consume `Q`; nếu không, `receive()` và `@RabbitListener` sẽ **cạnh tranh** lấy message khiến test thất thường. Callback trên template dùng chung cũng không nên bị nhiều test sửa cùng lúc.

**Điểm cần biết:** `RabbitTemplate.receive(...)` là **polling consumer** riêng, không kiểm chứng method `@RabbitListener` hay transaction nghiệp vụ. Test trên chứng minh topology + bytes/properties; listener cần một test khác để đo kết quả xử lý sau ACK/DB commit.

### 4.2. Khi nào cần kiểm tra *từng thuộc tính* topology?

`AmqpAdmin.getQueueProperties(...)` hữu ích để xác minh queue tồn tại và metadata cơ bản, **không đủ để so toàn bộ binding/arguments**. Với hệ thống có DLX, TTL, quorum/classic queue hay policies quan trọng, có thể:

- Dùng RabbitMQ Management HTTP API trên **container/vhost thử nghiệm** để đọc exchange type, queue arguments, bindings và policy áp dụng.
- Dùng RabbitMQ Java Client `queueDeclarePassive(...)`/`exchangeDeclarePassive(...)` để xác minh tồn tại, nhưng nhớ **passive declare không kiểm tra toàn bộ arguments**.
- Bắn message định tuyến và kiểm tra nơi đến để xác minh behavior, bao gồm cả dead-letter.
- Kiểm thử một trường hợp **redeclare sai thuộc tính** trên broker/queue thử riêng để xác nhận broker từ chối bằng `PRECONDITION_FAILED`, không làm hỏng channel đang dùng cho các test tiếp theo.

Không dùng management API với credentials production trong CI. Nếu CI khai báo queue rồi **xóa cả vhost thử nghiệm** khi kết thúc, cách ly giữa test runs sẽ tốt hơn chạy các lệnh purge lên queue chung.

## 5. MessageConverter: chỉ test round-trip Java là chưa đủ

Spring AMQP sử dụng `MessageConverter` để chuyển từ object ứng dụng sang `Message` (body + metadata) và ngược lại. `RabbitTemplate` và `@RabbitListener` có thể dùng converter **khác nhau** nếu cấu hình thiếu nhất quán.

### 5.1. Cần kiểm tra 5 lớp của hợp đồng

| Lớp | Ví dụ | Lỗi thường gặp |
| --- | --- | --- |
| Body bytes | UTF-8 JSON với dấu tiếng Việt | Producer dùng Java serialization hoặc charset sai |
| Content metadata | `contentType=application/json`, `contentEncoding=UTF-8` | Consumer bỏ qua body hoặc converter chọn sai |
| Business schema | `eventId`, `schemaVersion`, `orderId`, `occurredAt` | Đổi tên field, thêm enum value làm consumer cũ lỗi |
| AMQP properties | `messageId`, `correlationId`, `deliveryMode=PERSISTENT` | Missing ID, timestamp/expiration dùng đơn vị khác |
| Optional headers | `traceparent`, `x-business-correlation-id` | Bị mất header hoặc dùng value type không tương thích |

Hợp đồng **độc lập ngôn ngữ** nên đặc tả body bằng JSON Schema/Avro/Protobuf (tùy hệ thống) và định nghĩa các message properties cần thiết, không phụ thuộc tên class Java.

### 5.2. Ví dụ golden fixture

```json
{
  "eventId": "evt-2026-0001",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "orderId": "ORD-42",
  "customerLabel": "Khách hàng thử nghiệm",
  "totalMinorUnits": 150000,
  "currency": "VND",
  "occurredAt": "2026-11-26T03:00:00Z"
}
```

Quy tắc **contract** cần thống nhất:

1. `eventId` định danh **logical event**; khi retry cùng event giữ nguyên ID.
2. `schemaVersion` là số nguyên; không coi `1`, `"1"` và `1.0` là mặc nhiên tương đương nếu validation không cho phép.
3. Số tiền dùng **minor units integer** hoặc decimal string có định nghĩa chính xác; tránh số thực double khi nghiệp vụ tiền tệ đòi chính xác.
4. Timestamp dùng **UTC ISO-8601**; không dựa vào định dạng mặc định của `LocalDateTime`/Python `datetime`.
5. `customerLabel` kiểm chứng Unicode, không chứa dữ liệu khách hàng thật trong fixture công khai.
6. Trường mới phải có quy định forward/backward compatibility: bỏ qua unknown field, default khi thiếu, hoặc fail rõ ràng tùy version.

### 5.3. Kiểm tra JSON converter của Spring

Trong Spring AMQP **3.x**, converter JSON phổ biến là `Jackson2JsonMessageConverter`; Spring AMQP **4.x** chuyển sang `JacksonJsonMessageConverter` dùng Jackson 3. Đừng copy một converter class giữa hai major version mà không kiểm tra API/dependencies.

Ví dụ unit test cho Spring AMQP 3.x:

```java
import static org.junit.jupiter.api.Assertions.*;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;

class OrderJsonConverterTest {
    record OrderCreatedV1(
            String eventId,
            String orderId,
            int schemaVersion) {}

    private final Jackson2JsonMessageConverter converter =
            new Jackson2JsonMessageConverter();
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void javaObjectBecomesPortableJsonBody() throws Exception {
        OrderCreatedV1 event =
                new OrderCreatedV1("evt-001", "ORD-42", 1);

        Message message =
                converter.toMessage(event, new MessageProperties());

        assertEquals("application/json",
                message.getMessageProperties().getContentType());
        JsonNode json = mapper.readTree(message.getBody());
        assertEquals("evt-001", json.get("eventId").asText());
        assertEquals("ORD-42", json.get("orderId").asText());
        assertEquals(1, json.get("schemaVersion").asInt());
    }

    @Test
    void pythonStyleJsonDoesNotNeedJavaClassHeader()
            throws Exception {
        byte[] body = """
                {"eventId":"evt-002","orderId":"ORD-43",
                 "schemaVersion":1}
                """.getBytes(StandardCharsets.UTF_8);
        MessageProperties props = new MessageProperties();
        props.setContentType("application/json");
        props.setContentEncoding("UTF-8");
        Message incoming = new Message(body, props);

        // Không có __TypeId__: converter có thể trả Map mặc định.
        Object result = converter.fromMessage(incoming);
        assertInstanceOf(java.util.Map.class, result);
        var values = (java.util.Map<?, ?>) result;
        assertEquals("evt-002", values.get("eventId"));
        assertEquals(1, values.get("schemaVersion"));
    }
}
```

Trong unit test này ta kiểm tra **body và metadata**, không ép mọi message cross-language phải chứa `__TypeId__`. Khi `@RabbitListener` có tham số DTO kiểu **concrete**, converter JSON của Spring có thể suy ra kiểu từ tham số method dù message không có Java type headers. Nếu dùng interface/abstract target, class-level `@RabbitListener` hoặc generic phức tạp, quy tắc type inference có thể khác.

**Cảnh báo bảo mật:** `__TypeId__`, `__ContentTypeId__`, `__KeyTypeId__` do Java converter tạo là metadata phụ thuộc implementation. Không cho message bên ngoài tùy ý yêu cầu deserialize thành bất kỳ class nào bằng cách `trustedPackages("*")`; ưu tiên DTO/schema tường minh và tập package/class được phép.

### 5.4. Cấu hình converter ở cả template và listener

Ví dụ Spring Boot 3.x:

```java
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JsonMessagingConfiguration {

    @Bean
    public Jackson2JsonMessageConverter orderJsonConverter() {
        return new Jackson2JsonMessageConverter();
    }

    @Bean("jsonRabbitTemplate")
    public RabbitTemplate jsonRabbitTemplate(
            ConnectionFactory cf,
            Jackson2JsonMessageConverter converter) {
        RabbitTemplate template = new RabbitTemplate(cf);
        template.setMessageConverter(converter);
        return template;
    }

    @Bean("jsonListenerFactory")
    public SimpleRabbitListenerContainerFactory jsonListenerFactory(
            ConnectionFactory cf,
            Jackson2JsonMessageConverter converter) {
        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(cf);
        factory.setMessageConverter(converter);
        return factory;
    }
}
```

Với `@RabbitListener(queues = "...", containerFactory = "jsonListenerFactory")` nhận một DTO cụ thể, Spring có thể deserialize JSON từ Python (không có header class Java). Dù vậy cần test chính method signature dùng trong production, vì đổi signature từ DTO sang `Object` hoặc một interface có thể đổi cách converter xác định type.

## 6. Kiểm thử tương thích đa ngôn ngữ: thống nhất wire contract

Lựa chọn để bắt đầu là **AMQP 0-9-1 ở cả hai phía**: Spring AMQP phía Java và Pika phía Python. Không trộn lẫn **AMQP 1.0** và 0-9-1 mà không có một bài compatibility riêng cho protocol translation.

### 6.1. Contract cho `OrderCreated` (AMQP 0-9-1)

| Field | Java (`MessageProperties`) | Python (`pika.BasicProperties`) |
| --- | --- | --- |
| Body | `byte[]` chứa UTF-8 JSON | `bytes` từ `json.dumps(...).encode("utf-8")` |
| Content type | `setContentType("application/json")` | `content_type="application/json"` |
| Charset | `setContentEncoding("UTF-8")` | `content_encoding="utf-8"` |
| Message ID | `setMessageId(eventId)` | `message_id=event_id` |
| Correlation ID | `setCorrelationId(workflowId)` | `correlation_id=workflow_id` |
| Persistence | `MessageDeliveryMode.PERSISTENT` | `delivery_mode=2` |
| Schema version | Trong JSON body | Trong JSON body |
| Custom header | `setHeader("x-business-correlation-id", ...)` | `headers={"x-business-correlation-id": ...}` |

`content_type` là tên property trong Pika; `contentType` là API phía Spring. Kiểu dữ liệu trong JSON/headers phải được quy ước: số nguyên dùng kiểu JSON number phù hợp; ID dùng string; timestamp dùng chuỗi UTC. **Không** đặt tên Java class vào body hoặc buộc Python phải phát `__TypeId__`.

### 6.2. Python producer gửi cho Java consumer

Ví dụ script Python 3 dùng `pika` và môi trường RabbitMQ thử nghiệm:

```python
import json
import os
import pika

# Không hard-code password production vào mã.
url = os.environ.get(
    "AMQP_URL", "amqp://guest:guest@localhost:5672/%2F")
connection = pika.BlockingConnection(pika.URLParameters(url))
channel = connection.channel()

# Khai báo tương đương với phía Java.
channel.exchange_declare(
    exchange="orders.events.x", exchange_type="direct", durable=True)
channel.queue_declare(queue="orders.created.q", durable=True,
    arguments={
        "x-dead-letter-exchange": "orders.dead.x",
        "x-dead-letter-routing-key": "orders.failed"
    })
channel.queue_bind(
    queue="orders.created.q",
    exchange="orders.events.x",
    routing_key="orders.created")

event = {
    "eventId": "evt-python-001",
    "eventType": "OrderCreated",
    "schemaVersion": 1,
    "orderId": "ORD-42",
    "customerLabel": "Đơn hàng thử nghiệm",
    "totalMinorUnits": 150000,
    "currency": "VND",
    "occurredAt": "2026-11-26T03:00:00Z"
}
body = json.dumps(
    event, ensure_ascii=False, separators=(",", ":")
).encode("utf-8")

properties = pika.BasicProperties(
    content_type="application/json",
    content_encoding="utf-8",
    delivery_mode=2,
    message_id=event["eventId"],
    correlation_id="checkout-req-123",
    headers={"x-business-correlation-id": "checkout-req-123"}
)

# Publisher confirms + mandatory để không âm thầm mất event unroutable.
channel.confirm_delivery()
try:
    channel.basic_publish(
        exchange="orders.events.x",
        routing_key="orders.created",
        body=body,
        properties=properties,
        mandatory=True
    )
finally:
    connection.close()
```

**Điều kiện chạy:** Exchange `orders.dead.x` phải đã được provision nếu khai báo work queue dùng DLX và muốn dead-letter hoạt động; tên queue/exchange, DLX arguments phải **tương đương** với Java config. Khi có broker riêng cho test, nên provision topology bằng một công cụ duy nhất trước khi cả hai client kết nối. Ví dụ Python ở trên minh họa việc khai báo tương đương; không tự sửa queue production đang có arguments khác.

`channel.confirm_delivery()` của Pika đưa channel vào chế độ publisher confirms. Với `mandatory=True`, một publish không route được có thể được báo bằng `pika.exceptions.UnroutableError`. **Kết quả publish mất kết nối hoặc timeout có thể chưa xác định**; retry cùng logical event phải giữ `eventId`.

### 6.3. Java consumer nhận JSON từ Python

Một listener minh họa nhận **body bytes** để hoàn toàn không phụ thuộc Java type headers của sender:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class PythonCompatibleListener {
    private final ObjectMapper mapper;
    private final OrderProcessingService service;

    public PythonCompatibleListener(
            ObjectMapper mapper, OrderProcessingService service) {
        this.mapper = mapper;
        this.service = service;
    }

    @RabbitListener(queues = "orders.created.q")
    public void handle(Message incoming) throws Exception {
        if (!"application/json".equalsIgnoreCase(
                incoming.getMessageProperties().getContentType())) {
            throw new IllegalArgumentException("Expected JSON");
        }

        String json = new String(
                incoming.getBody(), StandardCharsets.UTF_8);
        JsonNode event = mapper.readTree(json);
        if (!event.hasNonNull("eventId")
                || event.path("schemaVersion").asInt(-1) != 1
                || !event.hasNonNull("orderId")) {
            throw new IllegalArgumentException("Invalid event contract");
        }

        String eventId = event.get("eventId").asText();
        String propertyId =
                incoming.getMessageProperties().getMessageId();
        if (propertyId == null || !eventId.equals(propertyId)) {
            throw new IllegalArgumentException("messageId mismatch");
        }

        // Bên dưới phải commit inbox + side effect trong một DB transaction.
        service.applyOnce(eventId, event);
        // AUTO ACK chỉ sau khi method trả về thành công.
    }
}

interface OrderProcessingService {
    void applyOnce(String eventId, JsonNode event);
}
```

Đoạn trên minh họa ranh giới wire protocol. Trong production, cần validate **đầy đủ** JSON Schema, giới hạn kích thước body, kiểm tra các giá trị enum/timestamp, và phân loại lỗi validation là lỗi vĩnh viễn để tránh requeue nóng. `ObjectMapper` ở đây là Jackson 2 theo Spring Boot 3.x; khi nâng Spring Boot/Jackson major version phải cập nhật dependency/API phù hợp.

Nếu dùng `@RabbitListener(OrderCreatedV1 event)` với `Jackson2JsonMessageConverter`, framework có thể suy kiểu DTO từ method signature. Đó là lựa chọn tiện hơn nhưng vẫn phải kiểm thử với **message thật do Python phát**, không chỉ một Java producer dùng cùng converter.

### 6.4. Java producer gửi cho Python consumer

Java chủ động xây body UTF-8 JSON và AMQP properties để không buộc Python biết tên Java class:

```java
import java.nio.charset.StandardCharsets;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.RabbitTemplate;

public class CrossLanguagePublisher {
    private final RabbitTemplate template;

    public CrossLanguagePublisher(RabbitTemplate template) {
        this.template = template;
    }

    public void publish(String json, String eventId) {
        MessageProperties props = new MessageProperties();
        props.setContentType("application/json");
        props.setContentEncoding("UTF-8");
        props.setMessageId(eventId);
        props.setCorrelationId("checkout-req-123");
        props.setDeliveryMode(MessageDeliveryMode.PERSISTENT);

        template.send(
                "orders.events.x",
                "orders.created",
                new Message(
                        json.getBytes(StandardCharsets.UTF_8), props));
    }
}
```

Ở đây `.send(...)` không đợi confirm. Khi xây test producer tin cậy, thêm `CorrelationData`, bật `publisher-confirm-type=correlated`, `publisher-returns=true`, `template.mandatory=true`, sau đó đợi confirm và kiểm tra returned message. Publisher confirm **không** có nghĩa Python consumer đã commit công việc.

Python consumer nhận một message rồi ACK **sau bước xử lý minh họa**:

```python
import json
import os
import pika

url = os.environ.get(
    "AMQP_URL", "amqp://guest:guest@localhost:5672/%2F")
connection = pika.BlockingConnection(pika.URLParameters(url))
channel = connection.channel()
channel.basic_qos(prefetch_count=1)

def on_order_created(ch, method, properties, body):
    try:
        if properties.content_type != "application/json":
            raise ValueError("Unexpected content type")

        event = json.loads(body.decode("utf-8"))
        if (event.get("schemaVersion") != 1
                or not isinstance(event.get("eventId"), str)
                or event.get("eventId") != properties.message_id):
            raise ValueError("Invalid event contract")

        # DEMO: trong ứng dụng thật, phải commit DB/inbox trước ACK.
        print("Received:", event["eventId"], event["orderId"])
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except (ValueError, UnicodeDecodeError, KeyError) as exc:
        print("Invalid payload:", exc)
        # Phụ thuộc queue có DLX phù hợp; không requeue vô hạn.
        ch.basic_reject(
            delivery_tag=method.delivery_tag, requeue=False)
    except Exception:
        # Lỗi tạm thời: cần retry có backoff/DLQ theo chính sách.
        ch.basic_nack(
            delivery_tag=method.delivery_tag, requeue=True)

channel.basic_consume(
    queue="orders.created.q",
    on_message_callback=on_order_created,
    auto_ack=False
)
try:
    channel.start_consuming()
finally:
    connection.close()
```

**Chỉ chạy một consumer nhận từ work queue khi cần so sánh toàn bộ message**: nếu Java và Python cùng subscribe `orders.created.q` thì chúng là **competing consumers** và có thể chia nhau các delivery, không phải mỗi ngôn ngữ đều nhận cùng message. Test hai chiều trên cùng queue phải chạy **tuần tự**, hoặc tạo hai queue độc lập được bind để nhận các bản copy.

## 7. Cross-language contract test matrix

Không dừng ở một message `"hello"` hoặc một DTO cực đơn giản. Cần có fixture đại diện cả dữ liệu hợp lệ và biên:

| Mã | Producer → Consumer | Test data | Kỳ vọng |
| --- | --- | --- | --- |
| CL-01 | Java → Java | JSON schema v1 chuẩn | Baseline parse đúng |
| CL-02 | **Python → Java** | Unicode tiếng Việt, `message_id`, `correlation_id` | Java nhận bytes và business IDs chính xác |
| CL-03 | **Java → Python** | Cùng event theo fixture | Python hiểu fields, số nguyên, timestamp |
| CL-04 | Node.js → Java | JSON từ `amqplib`, `contentType` rõ ràng | Java không cần `__TypeId__` |
| CL-05 | Java → Node.js | Bytes UTF-8, headers và persistent flag | Node không phụ thuộc Java serializer |
| CL-06 | Python → Java | Thiếu `schemaVersion`, sai kiểu `eventId` | Validation fail có chủ đích, reject/DLQ |
| CL-07 | Java → Python | Unknown field mới | Hành vi forward-compatible như hợp đồng |
| CL-08 | Python → Java | Decimal/large integer, zero, null | Không mất độ chính xác hoặc thay null thành mặc định sai |
| CL-09 | Hai ngôn ngữ | Cùng `eventId` được gửi lại | Side effect commit đúng một lần nhờ inbox |
| CL-10 | Hai ngôn ngữ | `contentType` sai, binary protobuf gửi vào JSON queue | Lỗi converter được bắt; không ACK như thành công |
| CL-11 | Hai ngôn ngữ | Publish tới key không binding | Có return/negative outcome, không báo success giả |
| CL-12 | Hai ngôn ngữ | Producer/consumer restart và mất kết nối | Redelivery + idempotency đúng |
| CL-13 | Hai ngôn ngữ | Correlation ID cho request/reply | Reply match chính xác, timeout có giới hạn |
| CL-14 | Hai ngôn ngữ | Message lớn gần giới hạn broker | Hệ thống từ chối/giới hạn rõ; không làm hỏng consumer |

**Node.js:** Nếu sử dụng `amqplib`, body được gửi bằng `Buffer.from(JSON.stringify(event), "utf8")` và properties có `contentType`, `contentEncoding`, `messageId`, `correlationId`, `persistent`; consumer nhận `msg.content` là `Buffer`, dùng `JSON.parse(msg.content.toString("utf8"))`. Một test Node.js cũng cần chờ publisher confirm khi dùng `ConfirmChannel` và chỉ ACK sau xử lý.

### So sánh output nghiệp vụ thay vì byte-for-byte

JSON object không có nghĩa **thứ tự key** phải giống giữa Java/Python/Node. Producer Python có thể xuất `"eventId"` trước `"orderId"` nhưng Java serializer đổi thứ tự. Các test schema nên parse JSON rồi so sánh cấu trúc:

```text
eventId            == "evt-2026-0001"
schemaVersion      == 1
totalMinorUnits    == 150000 (integer)
currency           == "VND"
occurredAt         parse thành cùng UTC instant
customerLabel      giữ nguyên Unicode
```

Nếu hệ thống dùng chữ ký số trên **raw bytes** thay vì JSON semantic value, phải quy định **canonical JSON serialization** riêng; khi đó test byte-for-byte là bắt buộc. Đây là một yêu cầu khác với kiểm thử thông thường về tương thích schema.

## 8. Test listener: quan sát đúng thời điểm xử lý và xác nhận

`@RabbitListenerTest` và `RabbitListenerTestHarness` trong `spring-rabbit-test` có thể spy/capture invocation của listener; một số test dùng latch/await để tránh ngủ cố định. Nhưng **kiểm tra method đã được gọi chưa đủ**:

- Method trả về trước khi database commit? Có thể gây ACK sớm.
- Có exception chuyển đổi payload trước khi method được gọi? Harness có thể không thấy một invocation thành công.
- Exception có khiến requeue, DLQ hoặc retry không? Cần test với broker thật.
- Khi listener đã commit nhưng ACK bị mất, handler có idempotent không?

Một business handler nên được tách khỏi listener để test độc lập. Ví dụ với PostgreSQL:

```sql
CREATE TABLE processed_events (
    event_id VARCHAR(128) PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Pseudo-code trong **một database transaction**:

```text
BEGIN
  inserted = INSERT INTO processed_events(event_id)
                 VALUES (:eventId)
                 ON CONFLICT DO NOTHING
  IF inserted:
      validate orderVersion
      apply business effect
COMMIT
ACK delivery
```

Đối với hai consumer chạy đồng thời hoặc một message bị redeliver, unique constraint phải ngăn duplicate trên database. Không chỉ dùng `if (!repository.exists(eventId)) insert` vì hai thread/process có thể cùng thấy event chưa tồn tại. `messageId` phải được producer giữ ổn định khi retry cùng logical event; nếu không, consumer cần dedup bằng `eventId` trong payload.

## 9. Failure tests: làm thế nào để chứng minh không mất dữ liệu?

```mermaid
sequenceDiagram
    participant P as Java/Python Publisher
    participant R as RabbitMQ
    participant C as Consumer
    participant DB as Database
    P->>R: Publish(eventId=E1)
    R-->>P: Confirm có thể thất lạc
    R->>C: Deliver E1
    C->>DB: BEGIN + insert inbox(E1) + side effect
    DB-->>C: COMMIT
    Note over C,R: Consumer chết trước ACK
    R->>C: Redeliver E1
    C->>DB: inbox(E1) đã tồn tại; không làm side effect
    C-->>R: ACK E1
```

| Failure injection | Cần chứng minh | Điều không được suy luận |
| --- | --- | --- |
| Exchange không tồn tại | Publish lỗi rõ ràng, channel được phục hồi/đóng đúng | “Không có exception” nghĩa là đã route |
| Binding thiếu, mandatory=false | Broker có thể discard message; test phải phát hiện config sai | Publisher confirm ACK nghĩa queue nhận |
| Binding thiếu, mandatory=true | Returned message được callback ghi nhận, không mark outbox published | `basic.return` là consumer reject |
| Consumer parse sai UTF-8/JSON | Reject/DLQ theo policy, không chạy side effect | Retry vô hạn là cách sửa schema |
| Database lỗi tạm thời | Không ACK như success; retry có backoff | Requeue nhanh luôn an toàn |
| Commit DB thành công nhưng ACK chưa tới broker | Có thể redeliver; inbox chặn xử lý lại | Delivery `redelivered=true` chứng minh DB đã commit |
| Publisher đã được broker nhận nhưng confirm thất lạc | Retry cùng `eventId`; chấp nhận duplicate và dedup | Timeout nghĩa broker chắc chắn chưa có message |
| DLX hoặc DLQ binding sai | Kiểm thử DLQ route riêng, cảnh báo failure | Chỉ cấu hình `x-dead-letter-exchange` là đủ |
| Hai consumer khác ngôn ngữ cùng queue | Không bị lỗi transaction/dedup khi cạnh tranh | Mỗi consumer nhận mọi message |
| Broker restart | Durable queue & persistent message phù hợp được khôi phục, producer xử lý uncertainty | Khai báo queue durable đảm bảo không mất mọi message trong mọi failure mode |

### Tại sao các test phải có thời hạn chờ?

Một hệ thống bất đồng bộ không thể dùng `Thread.sleep(100)` rồi kết luận message chưa đến. Dùng `CountDownLatch`, `Awaitility` hoặc receive timeout đủ thực tế, có giới hạn trên để CI không treo. **Điều kiện hoàn tất** nên là business state đã được commit/quan sát hoặc một ACK/confirm tương ứng, không phải “callback bắt đầu chạy”.

Ví dụ AssertJ/Awaitility giả lập:

```java
import static org.awaitility.Awaitility.await;
import java.time.Duration;

await().atMost(Duration.ofSeconds(15))
        .untilAsserted(() ->
            assertEquals(1, orderRepository.countByEventId(eventId)));
```

Ví dụ giả định `orderRepository` có method trên và tích hợp `awaitility` trong test dependencies; không dùng nó để khẳng định RabbitMQ ACK đã được broker ghi nhận nếu test không kiểm tra thêm phía broker.

## 10. Quy trình CI: unit → broker → polyglot → fault injection

### 10.1. Giai đoạn đầu: unit và schema contract

Chạy trên mọi pull request:

- JSON parsing, schema validation, converter configuration, unknown/missing fields, Unicode, số tiền và timestamp.
- Unit test cho logic listener/service, idempotency và business state transitions.
- So sánh fixture bằng JSON semantic equality, không phụ thuộc thứ tự key.
- Ghi nhận rõ DTO/schema version nào đang được hỗ trợ; tránh thay field required không kiểm soát.

### 10.2. Giai đoạn hai: RabbitMQ Testcontainers

Chạy khi thay đổi module AMQP hoặc mỗi pull request:

- Provision topology trên broker sạch.
- Test route đúng/sai, DLX, converter, properties, publisher confirms/returns và consumer acknowledgement.
- Tạo namespace/container riêng cho suite; cleanup sau test.
- Giữ broker version **tương thích với production**, đồng thời có pipeline kiểm tra bản RabbitMQ sẽ nâng cấp.

### 10.3. Giai đoạn ba: polyglot interoperability

Ví dụ test job gồm:

```text
start RabbitMQ container
provision canonical topology
publish fixture bằng Python
receive/assert bằng Java
reset queue hoặc dùng queue khác
publish fixture bằng Java
receive/assert bằng Python
chạy thêm Node.js khi có consumer/producer Node
assert contract + metadata + idempotency + outcome
```

Hai client phải dùng **cùng một broker/vhost** và các queue fixtures được phân tách để tránh race. Không chạy cùng lúc hai test cùng nhận từ một queue đã cấu hình competing consumers trừ khi chính đó là mục tiêu của test.

### 10.4. Giai đoạn bốn: fault injection và nightly

Các test gây crash, network partition, TTL/DLX, chậm consumer hoặc broker restart thường tốn thời gian. Có thể đưa vào pipeline định kỳ/nightly **nhưng phải có giới hạn thời gian và tiêu chí fail rõ ràng**, không để lỗi bị đánh dấu thành “flaky, retry CI cho qua” không điều tra.

Trong tất cả giai đoạn, thu thập log gắn `eventId`, `correlationId`, queue, exchange, routing key và lỗi converter. Không ghi body đầy đủ của message chứa dữ liệu thật, credential hoặc thông tin cá nhân lên CI artifacts.

## 11. Các lỗi phổ biến khi kiểm thử

1. **“Unit test `RabbitTemplate` mock pass nghĩa topology đúng.”** Mock không kiểm tra broker, queue hay binding.
2. **“Java producer và consumer cùng Jackson converter pass thì Python cũng đọc được.”** Java-to-Java có thể dựa vào type headers; cần fixture Python thật.
3. **“Mọi message mặc nhiên có `messageId`.”** Không: publisher cần gán hoặc định nghĩa `eventId` bền vững trong payload.
4. **“`CorrelationData.id` là `MessageProperties.correlationId`.”** Không: một cái ghép publisher confirm, cái kia thuộc message/application contract.
5. **“`contentType=application/json` là chắc body hợp lệ.”** Metadata có thể sai; phải parse/validate body thật.
6. **“Exchange và queue đã tồn tại thì routing đúng.”** Thiếu/sai binding vẫn làm message unroutable.
7. **“Publisher confirm ACK chứng minh consumer đã commit.”** Không: đây là hai quá trình độc lập.
8. **“Cứ bật `auto_ack=True` bên Python cho đơn giản.”** ACK tự động có thể xóa message khi handler chưa commit side effect.
9. **“Thêm `Thread.sleep` đủ lâu sẽ hết test flaky.”** Nên dùng điều kiện/latch/timeout và cô lập queue; sleep là phỏng đoán.
10. **“Java, Python, Node cùng consume một queue sẽ nhận giống nhau.”** Chúng là competing consumers; cần nhiều queue để fan-out bản copy.
11. **“Bật `trustedPackages("*")` giúp converter đa ngôn ngữ.”** Đây không phải giải pháp portability và làm tăng rủi ro deserialization.
12. **“Test chỉ cần payload happy path.”** Lỗi charset, version, missing header, duplicate, DLQ và lost ACK thường là nguồn incident.

## 12. Câu hỏi tự kiểm tra

1. Vì sao `TestRabbitTemplate` không thể chứng minh một binding giữa direct exchange và queue được khai báo đúng?
2. Nêu ba phép kiểm tra cần làm khi exchange và queue đã tồn tại nhưng `@RabbitListener` không nhận message.
3. `Jackson2JsonMessageConverter` có thể dùng `__TypeId__` cho việc gì? Vì sao không nên lấy tên class Java làm hợp đồng giữa Java và Python?
4. Khác biệt giữa kiểm thử `toMessage/fromMessage` trên JVM và kiểm thử Python gửi JSON cho Java listener là gì?
5. Khi đổi một field `totalMinorUnits` từ integer sang decimal string, cần cập nhật và chạy lại những test case nào?
6. Vì sao `messageId`, `correlationId` và publisher `CorrelationData.id` không thể thay nhau một cách tùy tiện?
7. Làm thế nào phân biệt một publish **unroutable** với publish đến exchange không tồn tại?
8. Nếu Java và Python cùng subscribe `orders.created.q`, ai sẽ nhận một message? Muốn so kết quả hai consumer nên thay topology test ra sao?
9. Test nào chứng minh không tạo hai shipment khi consumer crash sau DB commit trước ACK?
10. Nên dùng `@RabbitListenerTest` trong trường hợp nào, và khi nào bắt buộc có Testcontainers RabbitMQ?
11. Đề xuất bộ golden messages đủ kiểm chứng Unicode, timezone, số tiền, unknown field, missing schema version và header lỗi.
12. Hãy thiết kế pipeline CI chạy tối thiểu hai chiều Java ↔ Python, bao gồm cleanup queue và một nhánh lỗi `mandatory=true`.

**Ghi nhớ:** Muốn bảo đảm hệ thống Spring AMQP hoạt động với nhiều ngôn ngữ, hãy kiểm thử từ **topology thật → body/metadata → business outcome**. Unit test converter kiểm tra logic Java nhưng không thay được RabbitMQ Testcontainers; Java ↔ Python/Node contract tests phải dựa trên **schema độc lập ngôn ngữ**, không dựa vào `__TypeId__`. Với các message quan trọng, bổ sung publisher confirms/returns, ACK sau commit, retry/DLQ và idempotency để kiểm thử không chỉ delivery thành công mà cả các cửa sổ lỗi.

### Tài liệu tham khảo chính thức

- [Spring AMQP — Testing Support](https://docs.spring.io/spring-amqp/reference/testing.html): `spring-rabbit-test`, `@RabbitListenerTest`, `TestRabbitTemplate`, `@RabbitAvailable`.
- [Spring AMQP — Message Converters](https://docs.spring.io/spring-amqp/reference/amqp/message-converters.html): JSON converter, content type, `__TypeId__`, type inference và trusted packages.
- [Spring AMQP 3.2 — Message Converters](https://docs.spring.io/spring-amqp/reference/3.2/amqp/message-converters.html): `Jackson2JsonMessageConverter` cho dự án trên Spring AMQP 3.x.
- [Spring AMQP — Listener Argument Conversion](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/conversion.html): suy kiểu theo `@RabbitListener` signature.
- [Testcontainers — RabbitMQ Module](https://java.testcontainers.org/modules/rabbitmq/): chạy broker tách biệt trong integration tests.
- [RabbitMQ — Publishers and Unroutable Messages](https://www.rabbitmq.com/docs/publishers): publisher confirms, mandatory, returns và routing failure.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): ACK, reject, redelivery và publisher confirms.
- [Pika — Python RabbitMQ Client](https://pika.readthedocs.io/en/stable/): `BasicProperties`, `basic_publish`, consumer ACK và publisher confirms.
