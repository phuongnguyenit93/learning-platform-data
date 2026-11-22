# Correlation giữa event nội bộ và message trong Spring Framework

## 1. Mục tiêu và bài toán

Một ứng dụng Spring có thể dùng `ApplicationEventPublisher.publishEvent(...)` để thông báo nghiệp vụ bên trong cùng JVM. Khi hệ thống cần tích hợp dịch vụ khác, một listener hoặc một outbound adapter có thể chuyển sự kiện đó thành message gửi Kafka, RabbitMQ, JMS, HTTP, outbox hay một transport khác. Ở đầu nhận, một message có thể tạo ra một **event nội bộ mới** để các component tiếp tục phản ứng.

Nếu chỉ truyền payload mà bỏ thông tin liên hệ, một hành trình có thể bị đứt:

~~~text
HTTP checkout
   |
   +-- Spring internal event: OrderPlaced
          |
          +-- outbound message: order.placed
                    |
                    +-- consumer receives message
                            |
                            +-- Spring internal event: OrderImported
                                      |
                                      +-- update projection / notify user
~~~

Khi cần điều tra lỗi hoặc theo dõi một quy trình nhiều bước, câu hỏi không chỉ là “message này có ID gì?” mà còn là:

- Nó phát sinh từ event nghiệp vụ nào?
- Những event/message nào thuộc **cùng một quy trình**?
- Tác nhân hay sự kiện nào **trực tiếp gây ra** công việc hiện tại?
- Đây là một message gửi lại do retry hay một **event nghiệp vụ mới**?
- Trace đang được ghi ở đâu và có còn context khi chuyển thread hoặc service không?
- Một listener đã nhận trùng message hay chỉ nhìn thấy cùng correlation ID?
- Những ID nào phải giữ qua broker, restart, replay, DLQ và schema upgrade?

Bài này hướng dẫn **correlation giữa event nội bộ và message** theo một hợp đồng rõ ràng, có ví dụ Java 17+ với Spring Framework, Spring Messaging và JUnit 5. Nó phân biệt correlation nghiệp vụ với distributed tracing, nêu giới hạn của `@EventListener` và chỉ ra cách nâng cấp lên transactional outbox/inbox khi phải bảo đảm giao nhận.

**Nguyên tắc chính:** Event ID định danh một sự kiện; correlation ID gom các bước cùng quy trình; causation ID chỉ nguyên nhân trực tiếp; message ID định danh một envelope/transport message. Không dùng một trường duy nhất thay thế cả bốn vai trò.

## 2. Ba lớp cần tách: event, message và trace

### 2.1. Spring Application Event

Spring chấp nhận object nghiệp vụ thông thường hoặc subclass của `ApplicationEvent`:

~~~java
publisher.publishEvent(new OrderPlaced(
        "evt-1001", "corr-9", "cmd-15", "ORD-101"));
~~~

Đoạn này chỉ minh họa, cần định nghĩa record và bean publisher.

Một `@EventListener` có thể nhận event đó ngay trong cùng JVM. Với multicaster mặc định, listener thông thường chạy đồng bộ; với `@Async` hoặc executor có thể xảy ra khác. Hợp đồng `ApplicationEventPublisher` xem bước publish là **handoff** tới multicaster, không mặc định bảo đảm xử lý hoàn tất hay lưu bền vững.

### 2.2. Integration message

Một message gửi qua hệ thống khác có ít nhất:

- **Payload**: dữ liệu được consumer đồng ý hiểu, thường phải serialize.
- **Metadata/headers**: loại message, schema version, identifiers, tracing context, content type, tenant scope nếu được chấp thuận.
- **Transport semantics**: topic/queue/routing key, offset, ack, retry, redelivery, partition và độ bền tùy hạ tầng.

`org.springframework.messaging.Message<T>` là một abstraction hữu ích để mô tả payload và headers. Nó không tự biến một chương trình Spring Context đơn giản thành Kafka producer.

### 2.3. Distributed trace

Tracing có một mô hình riêng: trace ID, span ID và trace context, chẳng hạn W3C `traceparent`/`tracestate`. Trace giúp quan sát những hoạt động trải qua nhiều service. Trace có thể bị sampling, bị cắt bởi trust boundary hoặc không được giữ lâu như dữ liệu nghiệp vụ.

Vì vậy, **business correlation ID không nên bị đồng nhất với trace ID**. Một workflow tồn tại hàng ngày hoặc tiếp tục sau DLQ replay có thể cần cùng correlation ID dù trace hiện tại đã kết thúc từ lâu.

## 3. Bốn định danh và ý nghĩa của chúng

| Trường | Câu hỏi trả lời | Có giữ qua retry không? | Có thay khi tạo bước nghiệp vụ mới không? |
| --- | --- | --- | --- |
| `eventId` | “Sự kiện nghiệp vụ logic nào?” | Có: giữ nguyên nếu gửi lại cùng sự kiện | Có: event mới cần ID mới |
| `messageId` | “Envelope/message gửi lần này hoặc logical outbox message nào?” | Theo thiết kế transport/outbox; không dùng để suy ra event identity | Thường có |
| `correlationId` | “Những bước này thuộc cùng một workflow?” | Có khi cùng workflow | Thường giữ; đổi khi mở workflow mới |
| `causationId` | “Điều gì trực tiếp dẫn tới event/message này?” | Giữ với cùng event | Thường đặt thành ID của bước cha trực tiếp |

Đây là **quy ước đề xuất của ứng dụng**, không phải bốn header có sẵn mà Spring Framework tự tạo cho bạn.

### 3.1. Event ID: ổn định cho một sự kiện logic

Ví dụ `evt-order-100` thể hiện một lần “OrderPlaced”. Nếu producer retry gửi cùng event vì chưa nhận ACK, **không sinh event ID mới**. Consumer có thể dùng `(producerSource, eventId, consumerId)` làm một phần deduplication key.

Nếu sau đó “PaymentCaptured” xảy ra, đó là sự kiện nghiệp vụ khác và phải có event ID mới, dù vẫn thuộc cùng checkout workflow.

### 3.2. Message ID: tùy hợp đồng envelope

Một event có thể được fan-out thành hai message gửi hai destination khác nhau. Mỗi message có ID hoặc offset/record identity riêng. Một message có thể retry với cùng logical outbox ID nhưng broker tạo một transport record ID hoặc offset mới.

Spring Messaging có `MessageHeaders.ID` kiểu UUID và `MessageHeaders.TIMESTAMP`, nhưng header ID có thể thay khi tạo message instance mới. Nó **không được mặc định coi là khóa idempotency ổn định xuyên adapter, serialization, broker và replay**.

Trong ví dụ, chúng ta khai báo thêm header ứng dụng `message_id` để minh họa. Production nên thống nhất nó tương ứng với **ID hàng outbox/logical message** hay **ID một lần phát qua transport**. Dùng đúng ngữ nghĩa đã định nghĩa, tránh giả định tất cả broker hỗ trợ cùng một message ID chuẩn.

### 3.3. Correlation ID: đi theo quy trình

Ví dụ quy trình checkout có `corr-checkout-09`:

~~~text
Command checkout        correlation=corr-checkout-09
OrderPlaced event        correlation=corr-checkout-09
order.placed message     correlation=corr-checkout-09
OrderImported event      correlation=corr-checkout-09
PaymentRequested event   correlation=corr-checkout-09
payment.requested msg    correlation=corr-checkout-09
~~~

Correlation ID cho phép tìm tất cả bước thuộc một flow. Nó **không chứng minh** các bước xảy ra theo thứ tự nào hoặc bước nào trực tiếp gây ra bước nào; vai trò đó của causation ID.

Một message mang correlation ID giống nhau **không phải duplicate** chỉ vì cùng correlation. Một checkout có thể sinh hàng chục event khác nhau cùng correlation ID.

### 3.4. Causation ID: trỏ tới nguyên nhân gần nhất

Nếu `OrderPlaced(evt-100)` phát ra `order.placed` và consumer tạo `OrderImported(evt-200)`, quy ước có thể là:

~~~text
evt-100:
    correlationId = corr-9
    causationId   = cmd-15

message order.placed:
    event_id       = evt-100
    correlation_id = corr-9
    causation_id   = cmd-15

evt-200 (event mới do consumer tạo):
    correlationId = corr-9
    causationId   = evt-100
~~~

Ở đây `evt-200` là một sự kiện **mới**, nên nó có event ID mới, nhưng causation ID cho biết nó được tạo vì `evt-100`. Nếu bạn **chỉ forward lại cùng một event** mà không tạo sự thật nghiệp vụ mới, giữ `eventId` cũ; không gán ID mới chỉ vì retry.

Nếu hệ thống có cả command và event, causation có thể tham chiếu command ID hoặc event ID. Để tránh trùng namespace, có thể lưu thêm `causationType`/`causationSource` nếu contract cần.

## 4. Ví dụ sơ đồ quan hệ cha–con qua ranh giới ứng dụng

~~~text
Service A / checkout
  |
  | commandId = cmd-001
  v
OrderPlaced(eventId=evt-101)
  correlationId = corr-900
  causationId   = cmd-001
  |
  | Outbound bridge
  v
Message(messageId=msg-301)
  event_id       = evt-101
  correlation_id = corr-900
  causation_id   = cmd-001
  |
  | Broker / transport
  v
Service B / inbound adapter
  |
  | publish NEW internal event
  v
OrderImported(eventId=evt-501)
  correlationId = corr-900
  causationId   = evt-101
  sourceMessage = msg-301
  |
  v
Projector / audit / notification
~~~

Các ID là dữ liệu giả lập để minh họa. Sơ đồ chỉ thể hiện **logic correlation**, không khẳng định có broker thật trong ví dụ Gradle bên dưới.

Mấu chốt: **giữ correlation, cập nhật causation theo cha trực tiếp và tạo ID mới khi có event mới**. Sự khác nhau giữa messageId và eventId giúp phân biệt nhiều lần gửi và một sự kiện logic duy nhất.

### 4.1. Ví dụ nhiều message từ cùng event

Nếu một event phát tới `billing.events` và `analytics.events`:

~~~text
evt-101
   +--> msg-billing-1  (event_id=evt-101)
   +--> msg-analytics-1 (event_id=evt-101)
~~~

Hai message khác nhau nhưng cùng sự kiện nguồn. Không dùng `messageId` làm khóa dedup nghiệp vụ xuyên mọi destination khi nghiệp vụ thực chất muốn idempotency theo `eventId + consumerId`.

### 4.2. Ví dụ replay

Nếu `msg-billing-1` thất bại rồi được gửi lại, message transport mới có thể có ID/offset khác, nhưng **event_id=evt-101** vẫn phải ổn định cho cùng sự kiện. Một consumer có idempotency store sẽ tránh cộng tiền hai lần chỉ vì redelivery.

Nếu operator sửa dữ liệu và thực sự phát một nghiệp vụ bù trừ mới, đó là event khác (ID mới), có causation/compensation link riêng.

## 5. Thiết kế metadata: header hay payload?

Có hai nơi thường đặt correlation:

- **Headers:** dễ tích hợp tracing, middleware, routing, log và adapter; broker phải hỗ trợ truyền/chuẩn hóa.
- **Payload/envelope:** rõ ràng trong event contract và outbox JSON, có thể tồn tại dù transport làm mất header.

Một mẫu hợp đồng:

~~~json
{
  "eventId": "evt-101",
  "correlationId": "corr-900",
  "causationId": "cmd-001",
  "eventType": "order.placed",
  "schemaVersion": 1,
  "occurredAt": "2026-11-11T01:00:00Z",
  "data": {
    "orderId": "ORD-101",
    "amountCents": 4200
  }
}
~~~

Đây là **mẫu envelope JSON**, không phải format bắt buộc của Spring. Có thể dùng metadata ở broker headers và payload business riêng. Chọn một nguồn chân lý nhất quán: nếu cùng field vừa có trong header vừa có trong body, cần định nghĩa cái nào authoritative và hành vi khi hai nơi mâu thuẫn.

Đề xuất thực dụng:

1. Event nội bộ có metadata tối thiểu cần thiết trong record immutable hoặc một `EventContext`.
2. Bridge đọc metadata **từ chính event**, không hy vọng mọi `ThreadLocal` còn nguyên.
3. Outbox lưu metadata + serialized payload trong cùng business transaction.
4. Transport adapter ánh xạ metadata sang headers theo naming/encoding contract.
5. Inbound adapter xác thực schema, header, provenance và quyền, rồi tạo event nội bộ phù hợp.

**Không bắt buộc phát toàn bộ các trường vào mọi topic.** Chỉ mang thông tin đáp ứng contract, data classification và giới hạn kích thước header của transport thực tế.

## 6. Quy ước header cho ví dụ

Bài này dùng các header ứng dụng:

| Header | Loại logic | Quy tắc |
| --- | --- | --- |
| `event_id` | String | Định danh event logic nguồn |
| `message_id` | String | ID envelope minh họa; production định nghĩa lifecycle rõ |
| `correlation_id` | String | Giữ khi thuộc cùng quy trình |
| `causation_id` | String | Nguyên nhân của event nguồn |
| `event_type` | String | Ví dụ `order.placed` |
| `schema_version` | Integer | Version của dữ liệu consumer hiểu |

Đây không phải header chung bắt buộc của Spring Kafka hay RabbitMQ. Khi dùng Kafka, header value thường được biểu diễn bằng `byte[]` và consumer phải thống nhất encoding (UTF-8, binary hoặc serializer phù hợp). Trong Spring Messaging `MessageHeaders` có thể chứa Java object. **Hai thế giới không tự đồng nhất 1:1**.

Khi message đến:

- Bắt buộc có event ID và correlation ID theo hợp đồng này.
- Kiểm tra `event_type` và `schema_version` để chọn decoder/handler.
- Validate kiểu, độ dài, charset và giá trị; không tin header do bên ngoài gửi.
- Causation ID được xác định từ event logic nguồn khi tạo **event nội bộ mới**.
- Message ID được giữ làm metadata hỗ trợ transport investigation, không dùng nó thay event ID.

Nếu một hệ thống cũ chưa có correlation ID, phải xác định chính sách fallback: generate một correlation ID mới ở **boundary** và ghi rõ nguồn đã mất context, hoặc đưa message vào quarantine/invalid-message flow. **Không tự âm thầm gán event ID làm correlation ID** rồi giả vờ đó là chuỗi nghiệp vụ gốc.

## 7. Ví dụ chạy được: Spring event → message → Spring event mới

Ví dụ sau dùng **Java 17+, Spring Framework 6.2.15 và Spring Messaging**. Một Spring event `OrderPlaced` được outbound bridge biến thành `Message<OrderPlacedPayload>` với metadata. Một `RecordingTransport` giữ message trong memory để mô phỏng ranh giới đi ra ngoài process. Sau đó inbound adapter nhận lại message và tạo **OrderImported event mới** với correlation giữ nguyên và causation trỏ về event nguồn.

**Giới hạn rõ ràng:** `RecordingTransport` không phải broker, không serialize JSON, không có network, transaction, durability, ACK, redelivery hay phân vùng. Nó làm rõ **mapping contract** bằng một chương trình chạy được không phụ thuộc Kafka/RabbitMQ. Phần production outbox, consumer và retry sẽ được thiết kế ở các mục sau.

### 7.1. Cấu trúc dự án

~~~text
event-message-correlation-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   └── java/
    │       └── demo/
    │           └── CorrelationBridgeDemo.java
    └── test/
        └── java/
            └── demo/
                └── CorrelationBridgeDemoTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'event-message-correlation-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.15'
    implementation 'org.springframework:spring-messaging:6.2.15'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

application {
    mainClass = 'demo.CorrelationBridgeDemo'
}

test {
    useJUnitPlatform()
}
~~~

`spring-context` chứa event publisher/listener; `spring-messaging` chứa `Message`, `MessageHeaders` và `MessageBuilder`. JUnit 5 chạy integration-style test với Spring context thật. Khi dùng Spring Boot, nên để BOM của Boot quản lý dependency Spring tương thích.

### 7.2. File Java đầy đủ

Lưu vào `src/main/java/demo/CorrelationBridgeDemo.java`:

~~~java
package demo;

import java.time.Instant;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class CorrelationBridgeDemo {

    public static final class Headers {
        public static final String EVENT_ID = "event_id";
        public static final String MESSAGE_ID = "message_id";
        public static final String CORRELATION_ID = "correlation_id";
        public static final String CAUSATION_ID = "causation_id";
        public static final String EVENT_TYPE = "event_type";
        public static final String SCHEMA_VERSION = "schema_version";

        private Headers() {}
    }

    public record OrderPlaced(
            String eventId,
            String correlationId,
            String causationId,
            String orderId,
            long amountCents,
            Instant occurredAt) {}

    public record OrderPlacedPayload(
            String orderId,
            long amountCents,
            String occurredAt) {}

    public record OrderImported(
            String eventId,
            String correlationId,
            String causationId,
            String orderId,
            String sourceMessageId) {}

    public interface OutboundTransport {
        void send(Message<OrderPlacedPayload> message);
    }

    // Chỉ mô phỏng bên ngoài JVM; KHÔNG phải broker thật.
    public static final class RecordingTransport
            implements OutboundTransport {

        private final CopyOnWriteArrayList<Message<OrderPlacedPayload>>
                messages = new CopyOnWriteArrayList<>();

        @Override
        public void send(Message<OrderPlacedPayload> message) {
            messages.add(message);
        }

        public Message<OrderPlacedPayload> last() {
            if (messages.isEmpty()) {
                throw new IllegalStateException("No message sent");
            }
            return messages.get(messages.size() - 1);
        }

        public int count() {
            return messages.size();
        }
    }

    // Outbound mapping: event nội bộ -> envelope message.
    public static final class OutboundOrderBridge {
        private final OutboundTransport transport;
        private final AtomicInteger messageCounter = new AtomicInteger();

        public OutboundOrderBridge(OutboundTransport transport) {
            this.transport = transport;
        }

        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            String messageId = String.format(
                    Locale.ROOT, "msg-%04d",
                    messageCounter.incrementAndGet());

            Message<OrderPlacedPayload> message =
                    MessageBuilder.withPayload(new OrderPlacedPayload(
                            event.orderId(),
                            event.amountCents(),
                            event.occurredAt().toString()))
                    .setHeader(Headers.EVENT_ID, event.eventId())
                    .setHeader(Headers.MESSAGE_ID, messageId)
                    .setHeader(Headers.CORRELATION_ID, event.correlationId())
                    .setHeader(Headers.CAUSATION_ID, event.causationId())
                    .setHeader(Headers.EVENT_TYPE, "order.placed")
                    .setHeader(Headers.SCHEMA_VERSION, 1)
                    .build();

            transport.send(message);
        }
    }

    // Inbound mapping: incoming message -> NEW internal event.
    public static final class InboundOrderBridge {
        private final ApplicationEventPublisher publisher;
        private final AtomicInteger eventCounter = new AtomicInteger();

        public InboundOrderBridge(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void accept(Message<OrderPlacedPayload> message) {
            String sourceEventId =
                    requiredHeader(message, Headers.EVENT_ID);
            String correlationId =
                    requiredHeader(message, Headers.CORRELATION_ID);
            String sourceMessageId =
                    requiredHeader(message, Headers.MESSAGE_ID);
            String eventType =
                    requiredHeader(message, Headers.EVENT_TYPE);

            if (!"order.placed".equals(eventType)) {
                throw new IllegalArgumentException(
                        "Unsupported event type");
            }

            Object version =
                    message.getHeaders().get(Headers.SCHEMA_VERSION);
            if (!(version instanceof Integer schemaVersion)
                    || schemaVersion != 1) {
                throw new IllegalArgumentException(
                        "Unsupported schema version");
            }

            String childEventId = String.format(
                    Locale.ROOT, "evt-consumer-%04d",
                    eventCounter.incrementAndGet());

            // correlation GIỮ NGUYÊN, causation = event nguồn.
            publisher.publishEvent(new OrderImported(
                    childEventId,
                    correlationId,
                    sourceEventId,
                    message.getPayload().orderId(),
                    sourceMessageId));
        }

        private static String requiredHeader(
                Message<?> message, String name) {
            Object value = message.getHeaders().get(name);
            if (!(value instanceof String text)
                    || text.isBlank()
                    || text.length() > 128) {
                throw new IllegalArgumentException(
                        "Missing or invalid header: " + name);
            }
            return text;
        }
    }

    // Observer chỉ nhận event MỚI được tạo ở đầu consumer.
    public static final class ImportedObserver {
        private final CopyOnWriteArrayList<OrderImported> received =
                new CopyOnWriteArrayList<>();

        @EventListener
        public void onImported(OrderImported event) {
            received.add(event);
        }

        public OrderImported last() {
            if (received.isEmpty()) {
                throw new IllegalStateException("No imported event");
            }
            return received.get(received.size() - 1);
        }

        public int count() {
            return received.size();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public RecordingTransport transport() {
            return new RecordingTransport();
        }

        @Bean
        public OutboundOrderBridge outboundOrderBridge(
                RecordingTransport transport) {
            return new OutboundOrderBridge(transport);
        }

        @Bean
        public InboundOrderBridge inboundOrderBridge(
                ApplicationEventPublisher publisher) {
            return new InboundOrderBridge(publisher);
        }

        @Bean
        public ImportedObserver importedObserver() {
            return new ImportedObserver();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            RecordingTransport transport =
                    context.getBean(RecordingTransport.class);
            InboundOrderBridge inbound =
                    context.getBean(InboundOrderBridge.class);
            ImportedObserver observer =
                    context.getBean(ImportedObserver.class);

            OrderPlaced source = new OrderPlaced(
                    "evt-producer-0001",
                    "corr-checkout-09",
                    "cmd-checkout-01",
                    "ORD-100",
                    4200L,
                    Instant.parse("2026-11-11T01:00:00Z"));

            context.publishEvent(source);
            Message<OrderPlacedPayload> wire = transport.last();

            // Mô phỏng consumer nhận message từ transport.
            inbound.accept(wire);
            OrderImported received = observer.last();

            System.out.println("producer.event=" + source.eventId());
            System.out.println("message.id=" +
                    wire.getHeaders().get(Headers.MESSAGE_ID));
            System.out.println("message.event.id=" +
                    wire.getHeaders().get(Headers.EVENT_ID));
            System.out.println("message.correlation=" +
                    wire.getHeaders().get(Headers.CORRELATION_ID));
            System.out.println("message.causation=" +
                    wire.getHeaders().get(Headers.CAUSATION_ID));
            System.out.println("consumer.event.id=" + received.eventId());
            System.out.println("consumer.correlation=" +
                    received.correlationId());
            System.out.println("consumer.causation=" +
                    received.causationId());
            System.out.println("consumer.source.message=" +
                    received.sourceMessageId());
            System.out.println("transport.count=" + transport.count());
        }
    }
}
~~~

### 7.3. Chạy và stdout dự kiến

Chạy từ thư mục `event-message-correlation-demo`, với JDK 17+ và Gradle:

~~~bash
gradle -q run
~~~

Nếu đã tạo Gradle Wrapper, dùng `./gradlew -q run` (Linux/macOS) hoặc `gradlew.bat -q run` (Windows).

Các dòng **do chương trình chủ động in ra** theo thứ tự:

~~~text
producer.event=evt-producer-0001
message.id=msg-0001
message.event.id=evt-producer-0001
message.correlation=corr-checkout-09
message.causation=cmd-checkout-01
consumer.event.id=evt-consumer-0001
consumer.correlation=corr-checkout-09
consumer.causation=evt-producer-0001
consumer.source.message=msg-0001
transport.count=1
~~~

Trong ví dụ, các ID được chọn cố định và bộ đếm bắt đầu từ 0 nên stdout dự kiến có thể kiểm tra bằng mắt. Khi dùng ID ngẫu nhiên ở production, **không kỳ vọng ID string cụ thể**, mà assert quan hệ giữa ID, độ duy nhất và sự bảo toàn correlation. Gradle/logging có thể xuất thêm dòng khác.

**Nhìn vào quan hệ:** `evt-consumer-0001` là một event mới, `causationId=evt-producer-0001`, còn `correlationId=corr-checkout-09` vẫn được giữ. `msg-0001` là định danh message minh họa; nó không thay thế ID sự kiện.

### 7.4. Vì sao trong demo không dùng broker?

Mục tiêu là test một **mapping contract** có thể hiểu và chạy ở bất kỳ máy nào có JDK/Gradle. `RecordingTransport` là một fake transport, không có Kafka/RabbitMQ server, serializer, topic, partition, ACK hoặc durable storage. Việc giữ cùng một `Message<T>` trong memory cũng không thể phát hiện lỗi mapping kiểu dữ liệu qua network.

Khi đổi sang transport thật, cần integration test để xác minh serialization, headers encoding, schema evolution, retry, redelivery và consumer idempotency. Phần code mapping rõ ràng này có thể được giữ làm adapter core, nhưng không được coi là “message đã tới service B” chỉ vì `transport.send(...)` của fake thành công.

### 7.5. Điểm cần nâng cấp trong production

- `AtomicInteger` sinh ID chỉ dùng trong demo. Production dùng UUID/ULID/ID generator có contract rõ và kiểm soát uniqueness.
- `event_id` phải ổn định khi retry một event logic, không sinh mới ở mỗi lần phát lại.
- `message_id` trong demo tăng mỗi lần bridge được gọi; production gắn logical outbox message ID ổn định qua retry nếu định nghĩa nó theo outbox record.
- `InboundOrderBridge` kiểm tra header nhưng không có authentication, replay protection hoặc idempotent inbox; tất cả cần bổ sung ở boundary.
- `RecordingTransport` không serialize và không chứng minh khả năng JSON/Avro/Protobuf tương thích.
- Không in raw PII/secrets. Dùng business IDs theo policy của hệ thống và log correlation đã được duyệt.
- Không tự phát event inbound mới hai lần nếu consumer đã xử lý cùng delivery; durable dedup phải đi cùng transaction của side effect.

## 8. JUnit 5: kiểm tra hợp đồng correlation hai chiều

Tạo `src/test/java/demo/CorrelationBridgeDemoTest.java`:

~~~java
package demo;

import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CorrelationBridgeDemoTest {

    private static CorrelationBridgeDemo.OrderPlaced sampleEvent() {
        return new CorrelationBridgeDemo.OrderPlaced(
                "evt-1", "corr-1", "cmd-1", "ORD-1",
                250L, Instant.parse("2026-11-11T01:00:00Z"));
    }

    @Test
    void outboundPreservesEventAndBusinessCorrelation() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             CorrelationBridgeDemo.Config.class)) {

            var transport = context.getBean(
                    CorrelationBridgeDemo.RecordingTransport.class);

            context.publishEvent(sampleEvent());

            Message<CorrelationBridgeDemo.OrderPlacedPayload> message =
                    transport.last();

            assertEquals("evt-1", message.getHeaders().get(
                    CorrelationBridgeDemo.Headers.EVENT_ID));
            assertEquals("corr-1", message.getHeaders().get(
                    CorrelationBridgeDemo.Headers.CORRELATION_ID));
            assertEquals("cmd-1", message.getHeaders().get(
                    CorrelationBridgeDemo.Headers.CAUSATION_ID));
            assertEquals("msg-0001", message.getHeaders().get(
                    CorrelationBridgeDemo.Headers.MESSAGE_ID));
            assertEquals("order.placed", message.getHeaders().get(
                    CorrelationBridgeDemo.Headers.EVENT_TYPE));
            assertEquals(1, message.getHeaders().get(
                    CorrelationBridgeDemo.Headers.SCHEMA_VERSION));
            assertEquals("ORD-1", message.getPayload().orderId());
            assertEquals(250L, message.getPayload().amountCents());
            assertEquals(1, transport.count());
        }
    }

    @Test
    void inboundCreatesNewEventWithSameCorrelationAndParentCausation() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             CorrelationBridgeDemo.Config.class)) {

            var transport = context.getBean(
                    CorrelationBridgeDemo.RecordingTransport.class);
            var inbound = context.getBean(
                    CorrelationBridgeDemo.InboundOrderBridge.class);
            var observer = context.getBean(
                    CorrelationBridgeDemo.ImportedObserver.class);

            context.publishEvent(sampleEvent());
            inbound.accept(transport.last());

            var imported = observer.last();

            assertEquals("evt-consumer-0001", imported.eventId());
            assertNotEquals("evt-1", imported.eventId());
            assertEquals("corr-1", imported.correlationId());
            assertEquals("evt-1", imported.causationId());
            assertEquals("msg-0001", imported.sourceMessageId());
            assertEquals("ORD-1", imported.orderId());
            assertEquals(1, observer.count());
        }
    }

    @Test
    void missingCorrelationHeaderIsRejectedBeforeNewInternalEvent() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             CorrelationBridgeDemo.Config.class)) {

            var inbound = context.getBean(
                    CorrelationBridgeDemo.InboundOrderBridge.class);
            var observer = context.getBean(
                    CorrelationBridgeDemo.ImportedObserver.class);

            var payload = new CorrelationBridgeDemo.OrderPlacedPayload(
                    "ORD-1", 250L, "2026-11-11T01:00:00Z");

            var message = MessageBuilder.withPayload(payload)
                    .setHeader(CorrelationBridgeDemo.Headers.EVENT_ID,
                            "evt-1")
                    .setHeader(CorrelationBridgeDemo.Headers.MESSAGE_ID,
                            "msg-1")
                    .setHeader(CorrelationBridgeDemo.Headers.EVENT_TYPE,
                            "order.placed")
                    .setHeader(CorrelationBridgeDemo.Headers.SCHEMA_VERSION,
                            1)
                    .build();

            var error = assertThrows(
                    IllegalArgumentException.class,
                    () -> inbound.accept(message));

            assertTrue(error.getMessage().contains("correlation_id"));
            assertEquals(0, observer.count());
        }
    }

    @Test
    void wrongSchemaVersionIsRejectedBeforePublishing() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             CorrelationBridgeDemo.Config.class)) {

            var transport = context.getBean(
                    CorrelationBridgeDemo.RecordingTransport.class);
            var inbound = context.getBean(
                    CorrelationBridgeDemo.InboundOrderBridge.class);
            var observer = context.getBean(
                    CorrelationBridgeDemo.ImportedObserver.class);

            context.publishEvent(sampleEvent());

            var wrongVersion = MessageBuilder
                    .fromMessage(transport.last())
                    .setHeader(CorrelationBridgeDemo.Headers.SCHEMA_VERSION, 99)
                    .build();

            assertThrows(IllegalArgumentException.class,
                    () -> inbound.accept(wrongVersion));
            assertEquals(0, observer.count());
        }
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

Bốn test có mục tiêu khác nhau:

1. Outbound bridge giữ event ID, correlation ID, causation ID và chuyển payload đúng.
2. Inbound bridge tạo event **mới**; giữ correlation ID, còn causation chỉ về event nguồn.
3. Header correlation bắt buộc bị thiếu → không publish event mới.
4. Schema version không được hỗ trợ → reject trước khi xử lý.

Bộ test dùng Spring context và `@EventListener` thật. Nó không cần broker để kiểm tra mapping, nhưng **chưa kiểm tra** serialization, network, retry, exactly-once hay delivery bền vững. Đây là kỳ vọng khi chạy Gradle, không phải kết quả thực thi đã quan sát trong nhiệm vụ này.

## 9. Correlation và distributed tracing: liên quan nhưng không giống nhau

**Business correlation** giữ logic của một workflow. **Distributed tracing** giữ quan hệ của những operation/span được instrument, thường phục vụ điều tra latency hoặc lỗi.

Bảng phân biệt:

| Câu hỏi | Business correlation | Trace context |
| --- | --- | --- |
| Định danh gì? | Quy trình nghiệp vụ hoặc saga | Trace/span thực thi |
| Thời hạn | Có thể hàng giờ/ngày, tùy workflow | Có thể vài ms/giây, sampling/retention |
| Khi retry sau DLQ | Thường giữ correlation cũ | Có thể mở trace mới và link trace cũ |
| Khi thêm bước nghiệp vụ | Correlation thường giữ, causation đổi | Span mới, parent/link theo tracing |
| Storage | Event/outbox/message metadata, audit được phép | Telemetry backend, context propagation |
| Có thay làm khóa idempotency? | Không | Không |
| Có mặc định chứa PII? | Không nên | Không nên |

W3C Trace Context định nghĩa `traceparent` và `tracestate` (đặc biệt cho truyền context qua HTTP). Với messaging, propagation phụ thuộc instrumentation và semantic conventions của client/broker; không được tự giả định mọi adapter sẽ sao chép chính xác từng header.

Một traceparent minh họa:

~~~text
traceparent: 00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01
~~~

Giá trị này thể hiện trace ID, parent span ID và flags theo W3C format. Nó **không phải correlation ID nghiệp vụ** và không nên tự đặt `correlationId = traceparent`. Một workflow có thể tạo nhiều traces khác nhau khi event đợi trong outbox hoặc được replay ngày hôm sau.

Nếu dùng Micrometer Tracing / OpenTelemetry, nên sử dụng propagator/instrumentation chuẩn để inject/extract trace context. Không tự viết chuỗi `traceparent` từ correlation ID hoặc lưu span ID cố định qua mọi bước, vì cách đó có thể tạo trace graph sai.

### 9.1. Context propagation qua async

ThreadLocal MDC, SecurityContext và trace current span của thread publisher không tự xuất hiện trong mọi worker thread. Event cần mang correlation nghiệp vụ **như dữ liệu rõ ràng**, hoặc được truyền bằng `EventContext` immutable.

Với `ThreadPoolTaskExecutor`, `ContextPropagatingTaskDecorator`/Micrometer Context Propagation có thể hỗ trợ truyền context quan sát được nếu cấu hình đúng; tuy nhiên nó không biến ThreadLocal transaction JDBC thành một transaction sống hợp lệ trong worker khác.

### 9.2. Baggage và giới hạn dữ liệu

Không đặt email, token, số giấy tờ hoặc full payload vào tracing baggage để tiện debug. Baggage có thể được truyền sang dịch vụ khác và xuất tới telemetry backend. Correlation ID cũng có thể liên kết hoạt động cá nhân nên cần có data classification, retention và quyền truy cập phù hợp.

## 10. Thiết kế outbound bridge trong Spring

Một outbound listener nên làm việc như **adapter**, không tự trộn schema transport vào domain event:

~~~text
Domain service
    |
    +--> publish DomainEvent(...)
             |
             +--> @EventListener OutboundBridge
                       |
                       +--> map event -> IntegrationMessage
                       +--> choose destination
                       +--> send via producer adapter
~~~

Ưu điểm:

- Domain event không cần biết Kafka topic, RabbitMQ exchange hoặc header encoding.
- Bridge có thể version hóa public integration schema mà không buộc mọi listener nội bộ đổi theo.
- Test mapping độc lập với broker, giống bộ test mục 8.
- Các quyết định security/PII được thực hiện tại outbound boundary.
- Có chỗ tập trung để thêm correlation, causation và validation.

### 10.1. Không serialise nguyên JPA entity

Tránh:

~~~java
publisher.publishEvent(new OrderPlacedJpa(orderEntity));
~~~

Rồi gửi nguyên entity ra Kafka. Nó có thể mang quan hệ lazy, PII, proxy hoặc object graph lớn, và thay đổi schema ngoài ý muốn. Dùng record/DTO nhỏ, immutable với version tường minh.

### 10.2. Đừng lấy correlation chỉ từ MDC

Nếu bridge chạy sau commit, trên executor khác hoặc trong một retry worker, MDC có thể không còn hoặc mang request context không đúng. Với dữ liệu nghiệp vụ cần ổn định, đặt correlation ID trong **event/outbox record**.

Nếu muốn log correlation, interceptor có thể copy một giá trị đã được validate từ event vào MDC **trong phạm vi try/finally** và dọn ngay sau xử lý. Không giữ global ThreadLocal qua thread pool, vì nó có thể rò context giữa các task.

### 10.3. Quy tắc khi phát event mới

Nếu adapter chỉ **chuyển biểu diễn** của event cũ (domain event → integration message cùng sự thật nghiệp vụ), giữ `eventId` và correlation ID. Nếu một consumer thực hiện hành động mới và phát event mới, cấp event ID mới và đặt `causationId` trỏ về event đã kích hoạt nó.

Một worker retry gửi một outbox record **không nên tạo một domain event mới** chỉ để có ID mới; điều đó phá idempotency/dedup.

## 11. Inbound adapter: validate rồi mới phát event

Một inbound consumer phải coi message từ broker là **input từ một trust boundary**:

~~~text
Transport listener / consumer
   |
   +--> authenticate provenance / ACL / tenant if applicable
   +--> validate headers and schema version
   +--> deserialize into versioned DTO
   +--> check duplicate / idempotency
   +--> execute business logic in transaction
   +--> publish NEW internal event with preserved correlation
   +--> ACK only when work is durably complete
~~~

Thứ tự thực thi và transaction/ack semantics cụ thể phụ thuộc broker/framework, nhưng các bước logic này hữu ích cho design review.

### 11.1. Validation

Không chỉ kiểm tra header có tồn tại; cần xét:

- Kiểu dữ liệu hợp lệ sau decoder.
- Độ dài giới hạn để tránh header injection hoặc log amplification.
- Format event ID và correlation ID theo contract.
- `eventType` và `schemaVersion` được consumer hỗ trợ.
- Source/tenant được ủy quyền gửi loại message đó.
- Business payload không vượt giới hạn và không chứa field cấm.
- Timestamp/TTL/retention nếu nghiệp vụ có yêu cầu.
- Trace context có thể bị giả mạo; không cho nó trở thành thông tin quyền.

Ví dụ mục 7 từ chối correlation trống và schema không hỗ trợ. Đó là validation **cơ bản**, không phải bộ kiểm tra security production đầy đủ.

### 11.2. Event mới khác với republish nguyên message

Nếu consumer tạo một trạng thái mới `OrderImported`, event mới có:

~~~text
newEventId = generateUniqueId()
correlationId = incoming.correlationId
causationId = incoming.eventId
~~~

Nếu consumer chỉ chuyển tiếp cùng message/event sang một queue khác mà không tạo sự thật nghiệp vụ mới, phải xác định semantics là forward, retry hay transformation; thường giữ logical event identity và không giả tạo causation chain mới.

### 11.3. Không mù quáng tin correlation do client gửi

Nếu một client bên ngoài tự điền `correlationId`, có thể dùng để làm nhiễu log hoặc theo dõi chéo người dùng. Ở trust boundary, validate và có thể sinh ID nội bộ riêng theo policy. Không dùng correlation ID như một access token; authorization phải kiểm tra principal, tenant và tài nguyên thật.

## 12. Outbox: bảo đảm event và message không bị rơi ở cửa sổ commit

Một rủi ro:

~~~text
Transaction business commit thành công
       |
       +-- JVM crash trước khi @TransactionalEventListener(AFTER_COMMIT)
           kịp gọi producer
       |
       +-- Không có message và không có durable work item
~~~

`@TransactionalEventListener(AFTER_COMMIT)` giúp chọn thời điểm xử lý sau commit, nhưng **không tự bảo đảm message được gửi** khi JVM chết. Một outbound listener gọi Kafka thành công cũng không thể tự rollback commit business đã xảy ra nếu broker sau đó lỗi.

Với message quan trọng, dùng **transactional outbox**:

~~~text
BEGIN TRANSACTION
   INSERT/UPDATE business table
   INSERT outbox row {
       outboxId,
       eventId,
       correlationId,
       causationId,
       type,
       schemaVersion,
       payload
   }
COMMIT

Outbox worker:
   claim row
   encode headers/payload
   send to broker
   await producer acknowledgement as configured
   mark delivered or schedule retry
~~~

Business state và outbox row commit **cùng một database transaction**. Nếu rollback, cả hai cùng không tồn tại. Nếu worker crash sau khi broker nhận message nhưng trước khi outbox row được đánh dấu delivered, message có thể được gửi lại — vì vậy thiết kế consumer vẫn cần idempotency.

### 12.1. Schema SQL minh họa

~~~sql
CREATE TABLE outbox_message (
    outbox_id        UUID PRIMARY KEY,
    producer_source  VARCHAR(128) NOT NULL,
    event_id         VARCHAR(128) NOT NULL,
    correlation_id   VARCHAR(128) NOT NULL,
    causation_id     VARCHAR(128),
    event_type       VARCHAR(128) NOT NULL,
    schema_version   INTEGER NOT NULL,
    payload_json     TEXT NOT NULL,
    created_at       TIMESTAMP NOT NULL,
    status           VARCHAR(24) NOT NULL,
    attempts         INTEGER NOT NULL DEFAULT 0,
    UNIQUE (producer_source, event_id, event_type)
);
~~~

Đây là schema **tham khảo**, không bắt buộc unique theo đúng ba trường nếu một event hợp lệ phát nhiều message cùng loại tới nhiều destination. Khi fan-out, thêm `destination` hoặc ID message logical riêng vào khóa. Về nguyên tắc, unique key phải biểu diễn **đơn vị công việc cần gửi**, không ngăn những message hợp lệ.

Một outbox implementation thực cần chọn status, lease, retry/backoff, concurrency và retention. Không giữ lock DB suốt thời gian network send nếu có thể tách claim và xác nhận; thiết kế crash recovery cho `PROCESSING` quá hạn.

### 12.2. Trường metadata phải được persist trước khi gửi

Đừng chỉ lưu payload rồi để worker tự sinh correlation ID mới khi gửi; nếu retry, correlation sẽ thay đổi. `eventId`, `correlationId`, `causationId` và schema version nên được lưu cùng outbox record và giữ ổn định trong các lần resend theo contract.

**Khác biệt quan trọng:** Outbox tăng độ bền tạo công việc gửi; nó không tự tạo exactly-once end-to-end. Nếu không có idempotency ở consumer, side effect vẫn có thể trùng.

## 13. Inbox và idempotency cho consumer

Message brokers và outbox worker thường có semantics **at-least-once** khi cấu hình retry; consumer phải chịu được duplicate.

Không dùng correlation ID làm khóa dedup: một workflow có nhiều event cùng correlation. Không dùng transport offset làm khóa dedup nghiệp vụ nếu cùng event có thể được gửi lại với offset mới.

Một inbox table:

~~~sql
CREATE TABLE consumed_event (
    consumer_name  VARCHAR(128) NOT NULL,
    producer_source VARCHAR(128) NOT NULL,
    event_id       VARCHAR(128) NOT NULL,
    processed_at   TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, producer_source, event_id)
);
~~~

Workflow thường là:

~~~text
receive message(event_id=evt-101)
   |
   +--> transaction
          |
          +--> insert inbox key (consumer, source, evt-101)
          |       |
          |       +-- conflict already processed -> skip side effect
          |
          +--> mutate business state / write audit / outbox
          |
          +--> commit
   |
   +--> ACK source according to broker contract
~~~

Cần ràng buộc atomicity: nếu insert inbox nhưng side effect rollback, inbox insert cũng phải rollback, nếu không lần nhận lại bị bỏ qua mất việc. Nếu side effect là HTTP/email ngoài transaction database, cần idempotency key ở downstream hoặc reconciliation; database transaction **không thể atomically commit** mọi hệ thống ngoài.

Nếu dùng Kafka, JMS hay RabbitMQ, ack/retry/rebalance semantics khác nhau. Không khẳng định đã xử lý đúng chỉ từ việc consumer callback được gọi. Test crash giữa side effect và ACK mới chứng minh thiết kế retry không gây lỗi nghiệp vụ.

### 13.1. Message mới và event cũ

Một số outbox worker có thể tạo **messageId mới trên mỗi physical send**. Consumer vẫn dedup bằng logical `eventId`, không nhầm message IDs đó là business events khác nhau. Nếu một business event có các handler độc lập, key có thể phải chứa `handlerId`/`consumerGroup` để mỗi handler được xử lý một lần trong scope riêng.

### 13.2. TTL và replay

Khi inbox retention hết hạn mà một message cũ được replay lại, unique key không còn để ngăn duplicate. Chọn retention theo replay window, SLA và business risk; với tác vụ tài chính có thể cần invariant/idempotency ở domain layer ngoài inbox TTL.

## 14. Phân biệt correlation, ordering và causality

Correlation ID **không** làm broker tự bảo toàn thứ tự message. Hai message cùng correlation có thể đi qua topic/partition khác nhau, bị retry hoặc chạy song song ở consumer.

Causation ID giúp diễn tả **mối quan hệ** nhưng không tự bảo đảm event cha đã được xử lý trước event con ở mọi service. Nếu cần ordering:

- Chọn partition/routing key phù hợp, ví dụ aggregateId.
- Xác định ordering guarantee của transport thật.
- Dùng aggregateVersion hoặc sequence number nếu domain cần phát hiện out-of-order.
- Thiết kế consumer chịu được duplicate, delayed, missing hoặc reordered delivery.
- Không lấy `occurredAt` làm thứ tự tuyệt đối giữa nhiều máy khi clock skew có thể xảy ra.

Ví dụ:

~~~text
OrderCreated:       eventId=evt-1, correlation=corr-1, version=1
OrderAddressChanged eventId=evt-2, correlation=corr-1, version=2

Consumer nhận evt-2 trước evt-1:
   correlation giống nhau không giải quyết thứ tự
   phải dùng version/ordering policy
~~~

Nếu cần ghi side effect theo trình tự tuyệt đối cho một aggregate, điều đó thuộc thiết kế state machine/consumer, không chỉ thêm correlation ID vào header.

## 15. CloudEvents và sự khác nhau với header tự đặt

CloudEvents là một đặc tả định dạng event có những thuộc tính như `id`, `source`, `type`, `specversion`, `time` và `data`, tùy binding/format. Khi dùng CloudEvents:

- `id` định danh event trong phạm vi `source` theo đặc tả.
- `source + id` là cặp hữu ích để nhận diện một sự kiện nguồn.
- `type` mô tả loại sự kiện.
- `specversion` là version của **đặc tả CloudEvents**, không phải business payload schema version.
- Business correlation/causation thường được biểu diễn qua extension attributes được thống nhất, không phải mọi hệ thống đều có sẵn.

Ví dụ khái niệm:

~~~json
{
  "specversion": "1.0",
  "source": "/orders-service",
  "id": "evt-101",
  "type": "com.example.order.placed",
  "time": "2026-11-11T01:00:00Z",
  "correlationid": "corr-900",
  "causationid": "cmd-001",
  "data": {
    "orderId": "ORD-101",
    "amountCents": 4200
  }
}
~~~

`correlationid` và `causationid` ở đây là **extension names minh họa của contract ứng dụng**. Không khẳng định chúng là core CloudEvents attributes. Nếu dự án đã dùng CloudEvents, nên tuân thủ chính xác serialization/binding của transport thay vì tự đổi `ce-id` và những custom headers theo suy đoán.

CloudEvents không tự cung cấp queue, retry hoặc transaction. Nó giúp chuẩn hóa cách biểu diễn event, không thay thế broker/delivery architecture.

## 16. Metrics, logging và truy vết hành trình

Một hệ thống observability có thể cần tìm được:

~~~text
correlation=corr-900
  producer: evt-101 -> msg-301
  broker: topic=orders, partition=2, offset=724
  consumer: msg-301 -> evt-501
  handler: evt-501 -> database projection updated
~~~

Đây là dữ liệu minh họa. Trong production, hãy xác định rõ nguồn nào có thể truy vấn những ID này và thời hạn giữ.

### 16.1. Structured logs

Một log hữu ích có thể chứa các trường **được cho phép**:

~~~json
{
  "stage": "outbound.send",
  "eventType": "order.placed",
  "eventId": "evt-101",
  "correlationId": "corr-900",
  "messageId": "msg-301",
  "result": "acknowledged"
}
~~~

Không đưa full payload, email, access token hoặc địa chỉ khách hàng vào log nếu không cần. IDs cũng có thể là dữ liệu liên kết được nên phải có access control và retention; không tự coi chúng là public.

### 16.2. Metrics tags

Không đặt `eventId`, `messageId`, `correlationId` hoặc `traceId` trong tag của Micrometer `Counter`/`Timer`. Giá trị có cardinality lớn, tạo quá nhiều time series và có thể lộ thông tin liên kết. Tags nên là `event_type`, `handler`, `destination`, `outcome`, `error_kind` với tập giá trị hữu hạn.

Một counter minh họa:

~~~java
registry.counter(
        "event.bridge.messages",
        "event_type", "order.placed",
        "outcome", "published").increment();
~~~

Đây là đoạn code minh họa cần Micrometer `MeterRegistry` và bean `registry`, không nằm trong Gradle demo mục 7.

### 16.3. Traces

Dùng OpenTelemetry/Micrometer Tracing để instrument producer/consumer và truyền W3C context qua headers bằng propagator phù hợp. Không thay các span IDs bằng business correlation ID. Khi replay sau nhiều giờ, có thể mở một trace mới và **link** sự kiện/tracing context cũ nếu sampling/retention cho phép.

Nếu broker không lưu hoặc consumer không extract trace context, trace sẽ bị đứt dù correlation ID vẫn được giữ trong message. Vì vậy phải kiểm thử hai thứ riêng: **business correlation correctness** và **trace propagation correctness**.

## 17. An toàn dữ liệu và ranh giới tin cậy

Correlation IDs có thể hỗ trợ tìm hàng loạt hoạt động của cùng một người/đơn hàng. Chúng cần được thiết kế theo data classification, không sinh từ email hay số điện thoại một cách dễ đoán rồi coi như an toàn.

Checklist dữ liệu:

- Dùng random/opaque identifiers cho correlation khi phù hợp, không dùng PII làm ID.
- Validate header size, encoding và characters để ngăn injection/DoS.
- Không log toàn bộ message payload khi có token/PII.
- Không phát `HttpServletRequest`, `SecurityContext` hoặc JPA entity nguyên vẹn vào event.
- Không coi một header `tenant_id` bên ngoài là bằng chứng đủ quyền.
- Không sử dụng correlation ID để authorize hoặc chứng minh identity.
- Không đặt user ID/correlation ID vào high-cardinality metrics tags.
- Có retention/deletion policy cho log, outbox, DLQ và inbox.
- Có error quarantine cho message sai schema hoặc bị nghi giả mạo.
- Phân biệt **business source identity** với trace source và broker delivery metadata.

Nếu một partner gửi message tự tạo correlation ID, gateway có thể thay bằng ID nội bộ hoặc tạo ánh xạ để tránh partner giả danh correlation của tenant khác. Điều cần quan trọng là **thẩm quyền của origin**, không phải chuỗi ID trông hợp lệ.

## 18. Tình huống lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Hướng sửa |
| --- | --- | --- |
| Event có correlation nhưng message không có | Outbound bridge không map header | Test event→message mapping |
| Message có correlation nhưng event inbound mất | Consumer chỉ lấy payload, bỏ header | Extract, validate, gắn vào context/event mới |
| Correlation đổi sau mỗi retry | Sinh ID mới trong send attempt | Persist correlation từ lúc tạo event/outbox |
| EventId đổi trên cùng sự kiện retry | Retry coi mỗi lần gửi là event mới | Giữ stable logical event ID |
| Dedupe không hoạt động | Dùng message ID/offset thay vì event identity | Key theo source+eventId+consumer |
| Consumer bỏ qua tất cả event cùng workflow | Dedupe bằng correlation ID | Correlation không phải event ID |
| Inbound event không biết nguyên nhân | Không đặt causation ID từ upstream event ID | Tạo new event có causation chỉ về parent |
| Trace bị đứt khi async | Không propagate context | Dùng propagator/context propagation, test riêng |
| Có trace nhưng business correlation biến mất | Dựa vào sampled trace ID làm business ID | Lưu correlation trong event/outbox |
| Duplicate side effects sau crash | ACK và side effect không atomic | Inbox/idempotency/reconciliation |
| Có AFTER_COMMIT nhưng message vẫn mất | Crash trước producer send hoặc ACK | Transactional outbox |
| Message order sai | Nhiều partitions hoặc retry | Aggregate version/partition key |
| Header bị đổi kiểu khi tới Kafka | Codec/byte encoding không thống nhất | Contract cho header serialization |
| SchemaVersion vắng | Producer/consumer khác contract | Validation + schema migration |
| Log quá nhiều series | Correlation ID thành metric tag | Low-cardinality tags |
| Header từ client bị lợi dụng | Tin input không kiểm tra source/tenant | AuthN/AuthZ theo origin và tenant |
| Cùng event phát hai destinations bị chặn | Unique outbox key quá hẹp | Thêm destination/logical message ID |
| Consumer nhìn thấy event mới mà replay bị lặp | Thiếu inbox state bền vững | Idempotency + đúng transaction |
| Causation bằng message ID không nhất quán | Đã trộn transport attempt với domain trigger | Dùng upstream event ID làm cause logic |
| CloudEvents `specversion` nhầm schema business | Trộn chuẩn event và schema payload | Dùng field riêng cho data schema version |

## 19. Kiểm thử tích hợp cần có với broker thật

Bộ test Java ở mục 8 kiểm tra **logic mapping**; production cần test lớp ranh giới thật.

1. **Serialization:** record/JSON/Avro/Protobuf đi qua codec và đọc lại đúng kiểu dữ liệu; xác minh ISO timestamp, số tiền minor units và version.
2. **Header encoding:** `event_id`, `correlation_id`, `causation_id` giữ nguyên qua broker; kiểu string/binary tương thích.
3. **Schema compatibility:** consumer version N có thể xử lý N-1 nếu contract yêu cầu, và reject version không hỗ trợ.
4. **Retry/redelivery:** một event logic có stable event ID qua retry; physical message metadata có thể khác.
5. **At-least-once:** gửi trùng hai lần, side effect chỉ được áp dụng một lần theo khóa idempotency.
6. **Crash window:** kill worker sau business commit trước send và sau broker ACK trước outbox ACK.
7. **Inbox atomicity:** insert dedup marker và business update commit/rollback cùng nhau.
8. **Out-of-order:** consumer nhận version 2 trước version 1, xử lý theo policy.
9. **Tracing:** có producer/consumer spans và context propagation theo instrumentation thật.
10. **Security:** header giả mạo và cross-tenant correlation bị từ chối, không rò PII trong log/DLQ.
11. **DLQ replay:** replay message cũ vẫn giữ correlation và causation hợp lệ, không tạo event mới sai semantics.
12. **Backpressure:** queue đầy, task rejected, metrics và retry state còn đúng.

Có thể dùng Testcontainers với broker, embedded broker hoặc fake adapter tùy hệ thống. Fake transport là lựa chọn tốt cho unit test mapping, nhưng **không thay thế** kiểm thử integration protocol.

## 20. Bài tập thực hành

**Bài tập 1 — Nhiều message cùng event.** Thay một `OutboundTransport` bằng hai transport: billing và analytics. Dùng cùng event ID, correlation ID, causation ID nhưng có message ID/destination riêng. Giải thích khóa unique của outbox cần thay đổi thế nào.

**Bài tập 2 — Duplicate và inbox.** Publish hai message có cùng `event_id` nhưng message ID khác nhau. Cài một bảng `consumed_event` với unique key `consumer_name + producer_source + event_id` và xác minh side effect chỉ diễn ra một lần. Kiểm tra rollback của marker khi side effect lỗi.

**Bài tập 3 — Missing correlation.** Gửi message thiếu header correlation vào inbound adapter. So sánh hai chính sách: reject/quarantine và sinh correlation ID mới có gắn cờ mất upstream context. Vì sao âm thầm gán `event_id` làm correlation có thể gây hiểu sai?

**Bài tập 4 — Causation chain.** Sau `OrderImported` phát `InventoryReserved` là một event mới. Hãy cấp ID mới, giữ correlation, đặt causation bằng ID của `OrderImported`. Vẽ timeline.

**Bài tập 5 — Outbox.** Ghi business row và outbox row trong cùng JDBC transaction; gây rollback và xác minh không có outbox. Sau commit, worker gửi message bằng metadata đã lưu, không tự sinh correlation.

**Bài tập 6 — Trace.** Tạo span producer và consumer bằng Micrometer Tracing/OpenTelemetry. Propagate W3C `traceparent` đúng binding, đồng thời giữ business correlation độc lập. Tạo retry kéo dài và quan sát hai trace sessions.

**Bài tập 7 — Broker contract.** Thay `RecordingTransport` bằng adapter Kafka/RabbitMQ hoặc Spring Cloud Stream phù hợp, viết integration test header encoding/string version và retry. Đừng cho rằng Spring `MessageHeaders.ID` được bảo toàn qua mọi transport.

**Bài tập 8 — Privacy.** Bỏ toàn bộ event/message IDs khỏi metrics labels, giữ các IDs ở structured logs với retention và quyền phù hợp. Test một message chứa email giả và xác minh serializer/logging không để lộ email ngoài policy.

## 21. Checklist trước khi đưa vào production

- [ ] Mỗi domain event có `eventId` ổn định qua retry.
- [ ] Có `correlationId` cho workflow nhiều bước, được truyền qua event/message/outbox.
- [ ] Event mới sinh `eventId` mới và `causationId` tham chiếu bước cha phù hợp.
- [ ] Message ID có định nghĩa rõ: logical outbox message hay transport attempt/record.
- [ ] Không dùng `MessageHeaders.ID` thay stable business event identity một cách ngầm định.
- [ ] Outbound bridge map dữ liệu vào contract tích hợp; không serialize JPA entity graph.
- [ ] Inbound adapter kiểm tra event type, schema version, headers, source/tenant và payload.
- [ ] Không tin correlation ID từ client như credential hoặc authorization proof.
- [ ] Đã phân biệt business correlation với trace ID/span ID.
- [ ] Trace propagator hoạt động qua async/broker khi cần, có sampling và policy dữ liệu.
- [ ] Correlation vẫn còn khi trace kết thúc, outbox retry hoặc DLQ replay.
- [ ] Message quan trọng được lưu bằng outbox/job bền vững trong transaction business.
- [ ] Consumer có inbox/idempotency và cơ chế ack/retry đúng broker.
- [ ] Không dùng correlation ID làm khóa dedup hoặc partition ordering giả tạo.
- [ ] Đã kiểm tra schema evolution, header encoding và replay cũ.
- [ ] Log, metrics và traces không làm lộ PII/token hay gây high cardinality.
- [ ] Có tests từ domain event→message và message→domain event, cùng integration test broker thật.
- [ ] Người vận hành có thể truy vết event nguồn, message, consumer event và kết quả xử lý mà không xem dữ liệu cấm.

## 22. Tài liệu tham khảo

- Spring Framework 6.2 — `ApplicationEventPublisher` Javadoc, publish là handoff: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework 6.2 — Standard and Custom Events / `@EventListener`: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2 — `SimpleApplicationEventMulticaster` và executor: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework 6.2 — `org.springframework.messaging.Message`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/messaging/Message.html
- Spring Framework 6.2 — `MessageHeaders`, ID và timestamp: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/messaging/MessageHeaders.html
- Spring Framework 6.2 — `MessageBuilder`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/messaging/support/MessageBuilder.html
- Spring Integration — Message headers và read-only ID/timestamp: https://docs.spring.io/spring-integration/reference/message.html
- Spring Framework Reference — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework Reference — Observability Support: https://docs.spring.io/spring-framework/reference/integration/observability.html
- W3C Trace Context Recommendation: https://www.w3.org/TR/trace-context/
- CloudEvents Specification: https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md
- Micrometer Context Propagation Reference: https://docs.micrometer.io/context-propagation/reference/
- Spring for Apache Kafka Reference — sending/receiving and message headers: https://docs.spring.io/spring-kafka/reference/
- Spring AMQP Reference — listener containers, converters and headers: https://docs.spring.io/spring-amqp/reference/
