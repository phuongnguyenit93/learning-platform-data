# Giả lập producer, consumer hoặc adapter ở ranh giới nghiệp vụ

Trong **Spring Boot Messaging**, nếu mọi phép kiểm tra nghiệp vụ đều phải kết nối Kafka/RabbitMQ, tạo topic, chờ consumer group, gửi message rồi chờ xử lý, suite dễ chậm và flaky. Tuy nhiên, nếu mock tất cả và chỉ xác minh một lời gọi Mockito, test cũng không chứng minh payload, serialization, consumer subscription, retry hay broker acknowledgment đã đúng. Cách tiếp cận có giá trị là **đặt ranh giới nghiệp vụ rõ ràng, mock đúng dependency ở ranh giới đó và kiểm thử transport thật ở một lớp integration riêng**.

Bài này tập trung vào cách **giả lập producer, consumer hoặc adapter ở ranh giới nghiệp vụ** trong nhóm Messaging. Ví dụ sử dụng **Java 17, Spring Boot 3.4.5, Spring Kafka, Jackson, Mockito và JUnit Jupiter**. Một luồng payment nhỏ được chia thành:

~~~text
Kafka payments.received
    |
    v
PaymentKafkaConsumer        [inbound adapter]
  - nhận JSON String
  - deserialize thành PaymentAccepted
  - gọi PaymentHandler port
    |
    v
PaymentApplicationService   [business core]
  - validate event
  - tính reward points
  - tạo ReceiptIssued
  - gọi ReceiptPublisher port
    |
    v
KafkaReceiptPublisher       [outbound adapter]
  - serialize JSON
  - KafkaTemplate.send(topic, key, payload)
  - trả CompletableFuture
    |
    v
Kafka receipts.issued
~~~

**Unit tests không khởi động Kafka broker và không chạy Spring ApplicationContext.** Chúng kiểm tra logic và từng adapter bằng dependency giả lập. Muốn biết broker thực sự deliver, offset được commit hay DLT nhận lỗi, cần thêm **EmbeddedKafka/Testcontainers integration test**. Kết quả được mô tả là kỳ vọng theo code, không phải kết quả Gradle đã chạy trong quá trình soạn bài.

## 1. Mock tại boundary chứ không mock đối tượng cần kiểm tra

| Subject under test | Giữ thật | Giả lập | Bằng chứng |
| --- | --- | --- | --- |
| PaymentApplicationService | Rule validation và tính rewardPoints | ReceiptPublisher | Đúng dữ liệu business, gọi một lần, không gọi nếu invalid |
| PaymentKafkaConsumer | Deserialize JSON + dispatch method | PaymentHandler | Raw JSON thành đúng command; input sai và lỗi handler được xử lý đúng |
| KafkaReceiptPublisher | Serialize JSON + topic/key + future handling | KafkaTemplate | Đúng topic, key, payload và propagation khi send thất bại |
| Kafka producer client | Record được tạo theo Kafka API | MockProducer | ProducerRecord history trong bộ nhớ |
| Kafka consumer client | Poll Kafka client API | MockConsumer | Record thủ công được poll đúng |
| Spring Kafka listener container | Container thật, deserializer, group, retry, ack | Không thay bằng plain Mockito | Cần EmbeddedKafka hoặc Testcontainers Kafka |
| Nghiệp vụ chống trùng lặp | DB unique constraint/outbox/transaction | Fake có thể giúp unit | Cần integration/concurrency test để chứng minh an toàn |

**Không mock chính PaymentApplicationService** nếu đang test rewardPoints. **Không mock PaymentKafkaConsumer** nếu đang test mapping JSON. **Không mock KafkaReceiptPublisher** nếu đang test topic/key. Chỉ mock dependency nằm ngoài subject under test.

Mock là công cụ tách hệ thống thành hợp đồng, không phải công cụ chứng minh toàn bộ stack đã chạy.

### Mock, stub, fake và spy

- **Mock**: object do Mockito tạo, cho phép when/thenReturn, doThrow, verify, ArgumentCaptor. Hữu ích kiểm chứng interaction.
- **Stub**: cung cấp kết quả dự kiến, ví dụ ReceiptPublisher.publish trả CompletableFuture.completedFuture(null).
- **Fake**: implementation nhẹ có trạng thái thật như InMemoryReceiptPublisher lưu danh sách receipts; không có broker network/offset.
- **Spy**: wrap object thật và có thể thay đổi một phần hành vi. Dễ vô tình chạy side effect thật; chỉ dùng khi có lý do.
- **Kafka MockProducer/MockConsumer**: fake implementations trong kafka-clients, gần client API hơn Mockito nhưng **không phải Kafka cluster**.
- **EmbeddedKafka/Testcontainers Kafka**: hạ tầng broker dành cho integration tests, có chi phí startup và cần cleanup topics/groups.

**Chọn công cụ theo lỗi muốn bắt:** business rules → mock port; JSON mapping → real ObjectMapper; topic/key/future → mock KafkaTemplate; broker subscription/retry/offset → broker integration.

## 2. Thiết kế port-and-adapter trước khi test

Một application service bị coupling khi import KafkaTemplate và tự định tên topic ở giữa phép tính nghiệp vụ:

~~~java
@Service
class CoupledService {
    private final KafkaTemplate<String, String> template;

    void onPayment(PaymentAccepted message) {
        // validation ...
        template.send("receipts.issued", message.orderId(), "{...}");
    }
}
~~~

Đây là **trích đoạn phản ví dụ**, thiếu constructor/imports và không thuộc dự án runnable. Khi đổi Kafka sang RabbitMQ/outbox, service phải sửa. Unit test business cũng bị kéo vào serialization, future và broker API.

Thiết kế tốt hơn dùng hai interfaces:

~~~java
public interface PaymentHandler {
    void handle(PaymentAccepted payment);
}

public interface ReceiptPublisher {
    CompletableFuture<Void> publish(ReceiptIssued receipt);
}
~~~

**PaymentHandler** là inbound application port; adapter Kafka consumer chỉ parse và delegate. **ReceiptPublisher** là outbound port; business core tạo receipt mà không biết KafkaTemplate, topic hoặc serializer.

CompletableFuture<Void> ở outbound port là một **lựa chọn demo** giúp caller quan sát thành công/lỗi gửi bất đồng bộ. Production có thể dùng outbox/command queue, trả một receipt id hoặc transaction acknowledgment khác; đừng coi future là bắt buộc cho mọi hệ thống.

### Contract sự kiện

Input event:

~~~json
{
  "eventId": "evt-101",
  "orderId": "order-9",
  "amountMinor": 12345,
  "schemaVersion": 1
}
~~~

Output receipt:

~~~json
{
  "eventId": "evt-101",
  "orderId": "order-9",
  "amountMinor": 12345,
  "rewardPoints": 12,
  "schemaVersion": 1
}
~~~

**amountMinor** là đơn vị tiền nhỏ nhất do contract quy định, không tự giả sử mọi currency đều có hai chữ số thập phân. Rule demo: **1 point cho mỗi 1.000 minor units**, lấy phần nguyên. Dùng long để tránh binary floating-point khi xử lý số nguyên tiền. **eventId** ổn định phục vụ correlation và khả năng dedupe sau này; chỉ lưu nó trong payload **chưa tự tạo idempotency**.

## 3. KafkaTemplate.send trả CompletableFuture, không phải broker-delivery assertion

Spring Kafka 3.x cung cấp:

~~~java
CompletableFuture<SendResult<String, String>> result =
        template.send("receipts.issued",
                      "order-9",
                      "{\"eventId\":\"evt-101\"}");
~~~

Đây là trích đoạn giả định có template. Các cấp bằng chứng cần phân biệt:

1. **send() được gọi**: Mockito.verify xác nhận adapter đã invoke.
2. **send future hoàn tất thành công**: producer đã có result theo acks config, không nhất thiết downstream xử lý.
3. **send future hoàn tất lỗi**: network/timeout/broker/serializer hoặc lỗi khác phải tới caller.
4. **Consumer nhận record**: cần listener/broker integration.
5. **Business state được cập nhật đúng**: cần test handler/persistence.
6. **Exactly-once business effect**: cần idempotency, transactions/outbox và retry tests.

Không lấy verify(template).send(...) làm chứng minh message đã vào Kafka hoặc consumer đã ack.

Ví dụ business handler dưới đây dùng future.join() để **lan truyền lỗi gửi** qua boundary listener. Đây là cách đơn giản, có chủ đích cho bài kiểm thử, nhưng nó **blocking listener thread** và có thể giảm throughput. Production nên cân nhắc async listener, outbox, retry policy và backpressure.

## 4. Dự án runnable Java 17 / Spring Boot 3.4.5

### 4.1. Cấu trúc file

~~~text
settings.gradle
build.gradle
src/main/resources/application.yml
src/main/java/com/example/messagingqa/MessagingQaApplication.java
src/main/java/com/example/messagingqa/PaymentAccepted.java
src/main/java/com/example/messagingqa/ReceiptIssued.java
src/main/java/com/example/messagingqa/PaymentHandler.java
src/main/java/com/example/messagingqa/ReceiptPublisher.java
src/main/java/com/example/messagingqa/PaymentApplicationService.java
src/main/java/com/example/messagingqa/PaymentKafkaConsumer.java
src/main/java/com/example/messagingqa/KafkaReceiptPublisher.java
src/test/java/com/example/messagingqa/PaymentApplicationServiceTest.java
src/test/java/com/example/messagingqa/PaymentKafkaConsumerTest.java
src/test/java/com/example/messagingqa/KafkaReceiptPublisherTest.java
src/test/java/com/example/messagingqa/KafkaClientFakesTest.java
~~~

### 4.2. Gradle và Kafka String serialization

**settings.gradle**

~~~groovy
rootProject.name = 'messaging-boundary-testing'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-json'
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**spring-kafka** kéo theo Kafka clients types trong ví dụ; **spring-boot-starter-json** có Jackson ObjectMapper; **spring-boot-starter-test** cung cấp Mockito và JUnit Jupiter. Spring Boot BOM quản lý versions tương thích. Không ép thêm một phiên bản spring-kafka/client độc lập nếu không kiểm thử khả năng tương thích.

**src/main/resources/application.yml**

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: payments-demo
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
~~~

Kafka boundary dùng **String** cho value; ObjectMapper parse/serialize JSON tại adapter. **localhost:9092** là placeholder của môi trường app thật chạy với local broker; **unit test không mở Kafka** vì không khởi động Spring context. Trong Testcontainers, bootstrap servers phải lấy từ mapped host/port runtime.

### 4.3. Spring application class

**src/main/java/com/example/messagingqa/MessagingQaApplication.java**

~~~java
package com.example.messagingqa;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.kafka.annotation.EnableKafka;

@SpringBootApplication
@EnableKafka
public class MessagingQaApplication {
    public static void main(String[] args) {
        SpringApplication.run(MessagingQaApplication.class, args);
    }
}
~~~

**@EnableKafka** làm ý định đăng ký @KafkaListener rõ. Đừng khởi Spring context chỉ để test một phép chia số nguyên hoặc mapper đơn giản; plain MockitoExtension tests chạy nhanh và cô lập hơn.

### 4.4. Message DTO records

**src/main/java/com/example/messagingqa/PaymentAccepted.java**

~~~java
package com.example.messagingqa;

public record PaymentAccepted(
        String eventId,
        String orderId,
        long amountMinor,
        int schemaVersion) {
}
~~~

**src/main/java/com/example/messagingqa/ReceiptIssued.java**

~~~java
package com.example.messagingqa;

public record ReceiptIssued(
        String eventId,
        String orderId,
        long amountMinor,
        long rewardPoints,
        int schemaVersion) {
}
~~~

Không để DTO biết KafkaTemplate hoặc @KafkaListener. Event schemaVersion giúp reject format chưa hỗ trợ; production phải thiết kế backward/forward compatibility và contract evolution. eventId cần giữ ổn định qua retries để downstream có khả năng dedupe.

### 4.5. Inbound và outbound application ports

**src/main/java/com/example/messagingqa/PaymentHandler.java**

~~~java
package com.example.messagingqa;

public interface PaymentHandler {
    void handle(PaymentAccepted payment);
}
~~~

**src/main/java/com/example/messagingqa/ReceiptPublisher.java**

~~~java
package com.example.messagingqa;

import java.util.concurrent.CompletableFuture;

public interface ReceiptPublisher {
    CompletableFuture<Void> publish(ReceiptIssued receipt);
}
~~~

### 4.6. Business service là subject under test, không mock

**src/main/java/com/example/messagingqa/PaymentApplicationService.java**

~~~java
package com.example.messagingqa;

import java.util.Objects;
import java.util.concurrent.CompletableFuture;

import org.springframework.stereotype.Service;

@Service
public class PaymentApplicationService implements PaymentHandler {
    private final ReceiptPublisher publisher;

    public PaymentApplicationService(ReceiptPublisher publisher) {
        this.publisher = publisher;
    }

    @Override
    public void handle(PaymentAccepted payment) {
        Objects.requireNonNull(payment, "payment");

        if (payment.eventId() == null
                || payment.eventId().isBlank()) {
            throw new IllegalArgumentException(
                    "eventId must not be blank");
        }
        if (payment.orderId() == null
                || payment.orderId().isBlank()) {
            throw new IllegalArgumentException(
                    "orderId must not be blank");
        }
        if (payment.amountMinor() <= 0) {
            throw new IllegalArgumentException(
                    "amountMinor must be positive");
        }
        if (payment.schemaVersion() != 1) {
            throw new IllegalArgumentException(
                    "unsupported schema version");
        }

        long points = payment.amountMinor() / 1000L;
        ReceiptIssued receipt = new ReceiptIssued(
                payment.eventId(),
                payment.orderId(),
                payment.amountMinor(),
                points,
                1);

        CompletableFuture<Void> send = Objects.requireNonNull(
                publisher.publish(receipt),
                "publisher returned null future");

        // Demo đồng bộ: lỗi send sẽ propagate khỏi handler.
        // Khi production cần throughput, xem async/outbox.
        send.join();
    }
}
~~~

**Rule cần kiểm thử:** amountMinor=12345 cho rewardPoints=12. Invalid input không được gọi publisher. Future failed phải ném exception; future completed thì method return. Với code này, eventId trùng đến hai lần tạo **hai publish**: bài cố ý ghi nhận giới hạn đó, không giả vờ đã có idempotency.

### 4.7. Inbound Kafka consumer adapter

**src/main/java/com/example/messagingqa/PaymentKafkaConsumer.java**

~~~java
package com.example.messagingqa;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class PaymentKafkaConsumer {
    private final ObjectMapper mapper;
    private final PaymentHandler handler;

    public PaymentKafkaConsumer(
            ObjectMapper mapper, PaymentHandler handler) {
        this.mapper = mapper;
        this.handler = handler;
    }

    @KafkaListener(
        topics = "payments.received",
        groupId = "payments-demo")
    public void onMessage(String rawJson) {
        final PaymentAccepted payment;
        try {
            payment = mapper.readValue(
                    rawJson, PaymentAccepted.class);
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException(
                    "invalid payment JSON", ex);
        }
        handler.handle(payment);
    }
}
~~~

Adapter chỉ parse JSON rồi gọi port. Nó không chứa reward rule và không tự định nghĩa retry/DLT. Test gọi onMessage trực tiếp **không đi qua Kafka listener container**, do đó không test subscription, offset, acknowledgment hay consumer group rebalance.

Valid JSON có thể chứa values sai; business service sẽ validate eventId/orderId/amount/version. Nếu ứng dụng yêu cầu message schema validation ngay ở adapter, thêm một validator rõ ràng và test nhánh đó riêng.

### 4.8. Outbound Kafka producer adapter

**src/main/java/com/example/messagingqa/KafkaReceiptPublisher.java**

~~~java
package com.example.messagingqa;

import java.util.concurrent.CompletableFuture;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
public class KafkaReceiptPublisher implements ReceiptPublisher {
    public static final String TOPIC = "receipts.issued";

    private final KafkaTemplate<String, String> template;
    private final ObjectMapper mapper;

    public KafkaReceiptPublisher(
            KafkaTemplate<String, String> template,
            ObjectMapper mapper) {
        this.template = template;
        this.mapper = mapper;
    }

    @Override
    public CompletableFuture<Void> publish(ReceiptIssued receipt) {
        final String json;
        try {
            json = mapper.writeValueAsString(receipt);
        } catch (JsonProcessingException ex) {
            return CompletableFuture.failedFuture(
                    new IllegalStateException(
                        "cannot serialize receipt", ex));
        }

        return template.send(
                TOPIC,
                receipt.orderId(),
                json).thenApply(result -> null);
    }
}
~~~

**Topic** được đặt tại adapter, không phải service. **orderId là record key**, nhằm đưa events cùng key về cùng partition theo producer partitioner thông thường; ordering chỉ có phạm vi **một partition**, không toàn topic. **thenApply(result -> null)** giữ propagation: nếu KafkaTemplate future thất bại, returned future vẫn thất bại. Không log lỗi rồi trả completedFuture(null) giả thành công.

Khi cần headers (correlation ID, traceparent, event type), dùng ProducerRecord hoặc Spring Message<?> và kiểm tra headers ở adapter test. Ví dụ dùng eventId trong JSON, không tự giả định KafkaTemplate.send(topic,key,value) tạo thêm business headers.

## 5. JUnit test nghiệp vụ: mock outbound ReceiptPublisher

**src/test/java/com/example/messagingqa/PaymentApplicationServiceTest.java**

~~~java
package com.example.messagingqa;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class PaymentApplicationServiceTest {

    @Mock
    private ReceiptPublisher publisher;

    private PaymentApplicationService service;

    @BeforeEach
    void setUp() {
        service = new PaymentApplicationService(publisher);
    }

    @Test
    void validPaymentCreatesExactReceipt() {
        when(publisher.publish(any(ReceiptIssued.class)))
                .thenReturn(CompletableFuture.completedFuture(null));

        service.handle(new PaymentAccepted(
                "evt-101", "order-9", 12345L, 1));

        ArgumentCaptor<ReceiptIssued> captor =
                ArgumentCaptor.forClass(ReceiptIssued.class);
        verify(publisher, times(1)).publish(captor.capture());

        ReceiptIssued receipt = captor.getValue();
        assertEquals("evt-101", receipt.eventId());
        assertEquals("order-9", receipt.orderId());
        assertEquals(12345L, receipt.amountMinor());
        assertEquals(12L, receipt.rewardPoints());
        assertEquals(1, receipt.schemaVersion());
    }

    @Test
    void invalidFieldsCannotTriggerPublication() {
        assertThrows(IllegalArgumentException.class,
                () -> service.handle(new PaymentAccepted(
                    "", "order-9", 12345L, 1)));

        assertThrows(IllegalArgumentException.class,
                () -> service.handle(new PaymentAccepted(
                    "evt-101", " ", 12345L, 1)));

        assertThrows(IllegalArgumentException.class,
                () -> service.handle(new PaymentAccepted(
                    "evt-101", "order-9", 0L, 1)));

        assertThrows(IllegalArgumentException.class,
                () -> service.handle(new PaymentAccepted(
                    "evt-101", "order-9", 12345L, 99)));

        verifyNoInteractions(publisher);
    }

    @Test
    void publisherFailurePropagatesInsteadOfBeingSwallowed() {
        RuntimeException cause =
                new IllegalStateException("broker unavailable");

        when(publisher.publish(any(ReceiptIssued.class)))
                .thenReturn(CompletableFuture.failedFuture(cause));

        CompletionException thrown = assertThrows(
                CompletionException.class,
                () -> service.handle(new PaymentAccepted(
                    "evt-102", "order-10", 3000L, 1)));

        assertSame(cause, thrown.getCause());
        verify(publisher).publish(any(ReceiptIssued.class));
    }

    @Test
    void duplicateEventCurrentlyPublishesTwice() {
        when(publisher.publish(any(ReceiptIssued.class)))
                .thenReturn(CompletableFuture.completedFuture(null));

        PaymentAccepted payment =
                new PaymentAccepted("evt-dup", "order-11", 5000L, 1);
        service.handle(payment);
        service.handle(payment);

        verify(publisher, times(2))
                .publish(any(ReceiptIssued.class));
    }
}
~~~

**Vì sao cần ArgumentCaptor?** verify(publisher).publish(any()) vẫn xanh khi rewardPoints sai hoặc receipt chứa nhầm orderId. Captor biến payload thành assertion có ý nghĩa nghiệp vụ.

**Vì sao dùng completedFuture/failedFuture?** Đây là ranh giới bất đồng bộ, cần giả lập outcome theo hợp đồng. Một Mockito mock chưa stub phương thức trả future có thể trả null, gây NullPointerException vô ích khi subject gọi .join() hoặc .thenApply(). **Future thất bại thực sự** phải là failedFuture(exception), không phải null.

**Bài test duplicate có chủ đích:** nó nêu rõ implementation hiện tại chưa idempotent. Khi thêm processedEventRepository/outbox, cần đổi assertion để chứng minh cùng eventId chỉ tạo **một business effect**. Đừng coi verify(times(1)) của một lần gọi là bằng chứng exactly once khi Kafka có redelivery.

## 6. JUnit test consumer adapter: JSON thật, handler mock

**src/test/java/com/example/messagingqa/PaymentKafkaConsumerTest.java**

~~~java
package com.example.messagingqa;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

@ExtendWith(MockitoExtension.class)
class PaymentKafkaConsumerTest {

    @Mock
    private PaymentHandler handler;

    private PaymentKafkaConsumer consumer;

    @BeforeEach
    void setUp() {
        consumer = new PaymentKafkaConsumer(
                new ObjectMapper(), handler);
    }

    @Test
    void validJsonDispatchesExactCommand() {
        consumer.onMessage("""
                {
                  "eventId":"evt-101",
                  "orderId":"order-9",
                  "amountMinor":12345,
                  "schemaVersion":1
                }
                """);

        ArgumentCaptor<PaymentAccepted> captor =
                ArgumentCaptor.forClass(PaymentAccepted.class);
        verify(handler).handle(captor.capture());

        PaymentAccepted payment = captor.getValue();
        assertEquals("evt-101", payment.eventId());
        assertEquals("order-9", payment.orderId());
        assertEquals(12345L, payment.amountMinor());
        assertEquals(1, payment.schemaVersion());
    }

    @Test
    void malformedJsonNeverCallsHandler() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> consumer.onMessage("{broken-json"));

        assertEquals("invalid payment JSON", error.getMessage());
        verifyNoInteractions(handler);
    }

    @Test
    void handlerErrorPropagatesOutOfAdapter() {
        IllegalStateException cause =
                new IllegalStateException("processing failed");

        doThrow(cause).when(handler)
                .handle(any(PaymentAccepted.class));

        IllegalStateException thrown = assertThrows(
                IllegalStateException.class,
                () -> consumer.onMessage("""
                    {"eventId":"evt-2","orderId":"o-2",
                     "amountMinor":1000,"schemaVersion":1}
                    """));

        assertSame(cause, thrown);
        verify(handler).handle(any(PaymentAccepted.class));
    }
}
~~~

**ObjectMapper thật** trong consumer adapter test bảo vệ tên field, kiểu dữ liệu và Jackson record binding. Mock mapper ở success path sẽ bỏ qua logic parsing chính của adapter.

**Handler mock** giữ cho adapter test độc lập với business logic và Kafka producer. Test chỉ chứng minh JSON được chuyển thành PaymentAccepted và gọi port, JSON malformed không gọi port, lỗi nghiệp vụ propagate. Nó **không** chứng minh @KafkaListener container sẽ retry hoặc commit offset ra sao.

### Phân loại lỗi

- **Malformed JSON**: bản thân message không thể parse; retry y nguyên thường không sửa được lỗi, nên production có thể phân loại non-retryable và chuyển DLT.
- **Business validation error**: JSON parse được nhưng amountMinor=0/schemaVersion lạ; nên có error policy rõ, không tự retry mãi.
- **Temporary infra error**: DB/broker unavailable hoặc timeout; có thể retry với backoff.
- **Duplicate**: cùng eventId đã xử lý; idempotent handler nên có policy no-op/ack rõ.

Adapter demo chỉ propagate exceptions. **DefaultErrorHandler/retry-topic/DLT là trách nhiệm Spring Kafka listener container/config**, không thể khẳng định qua một unit test gọi Java method trực tiếp.

## 7. JUnit test producer adapter: mock KafkaTemplate, parse JSON thật

**src/test/java/com/example/messagingqa/KafkaReceiptPublisherTest.java**

~~~java
package com.example.messagingqa;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class KafkaReceiptPublisherTest {

    @Mock
    private KafkaTemplate<String, String> template;

    private ObjectMapper mapper;
    private KafkaReceiptPublisher publisher;

    @BeforeEach
    void setUp() {
        mapper = new ObjectMapper();
        publisher = new KafkaReceiptPublisher(template, mapper);
    }

    @Test
    void sendsExactTopicKeyAndJsonFields() throws Exception {
        CompletableFuture<SendResult<String, String>> ack =
                CompletableFuture.completedFuture(null);

        when(template.send(
                eq("receipts.issued"),
                eq("order-9"),
                anyString()))
                .thenReturn(ack);

        publisher.publish(new ReceiptIssued(
                "evt-101", "order-9", 12345L, 12L, 1)).join();

        ArgumentCaptor<String> payload =
                ArgumentCaptor.forClass(String.class);

        verify(template).send(
                eq("receipts.issued"),
                eq("order-9"),
                payload.capture());

        JsonNode data = mapper.readTree(payload.getValue());
        assertEquals("evt-101", data.path("eventId").asText());
        assertEquals("order-9", data.path("orderId").asText());
        assertEquals(12345L, data.path("amountMinor").asLong());
        assertEquals(12L, data.path("rewardPoints").asLong());
        assertEquals(1, data.path("schemaVersion").asInt());
    }

    @Test
    void futureFailureIsPropagatedToCaller() {
        RuntimeException cause =
                new IllegalStateException("send failed");

        when(template.send(
                eq("receipts.issued"),
                eq("order-9"),
                anyString()))
                .thenReturn(CompletableFuture.failedFuture(cause));

        ReceiptIssued event = new ReceiptIssued(
                "evt-102", "order-9", 1000L, 1L, 1);

        CompletionException thrown = assertThrows(
                CompletionException.class,
                () -> publisher.publish(event).join());

        assertSame(cause, thrown.getCause());
    }
}
~~~

**Subject là KafkaReceiptPublisher thật**, dependency được mock chỉ là KafkaTemplate. Dùng ObjectMapper thật để test serialization. Parse payload về JsonNode cho phép assert **các trường quan trọng**, tránh coupling với whitespace/property ordering trong JSON. Future completedFuture(null) giả lập send-result thành công nhưng **không có RecordMetadata của broker thật**; không được suy luận offset/partition/ack thực.

### Test serializer failure là một nhánh riêng

Adapter trả failed future khi ObjectMapper.writeValueAsString ném JsonProcessingException. Nếu cần coverage nhánh hiếm này, mock riêng mapper:

~~~java
ObjectMapper broken = mock(ObjectMapper.class);
when(broken.writeValueAsString(any()))
        .thenThrow(new JsonProcessingException("bad JSON") {});

KafkaReceiptPublisher adapter =
        new KafkaReceiptPublisher(template, broken);

CompletionException thrown = assertThrows(
        CompletionException.class,
        () -> adapter.publish(receipt).join());

assertInstanceOf(IllegalStateException.class, thrown.getCause());
verifyNoInteractions(template);
~~~

Đây là **trích đoạn bổ sung**, không thuộc file runnable; nó cần các imports Mockito/JUnit/Jackson, biến template và receipt từ test fixture. Trong success path, **không mock mapper**: nếu mock toàn bộ việc serialize thì test không phát hiện schema drift.

## 8. Kafka clients có sẵn MockProducer và MockConsumer

Mockito KafkaTemplate mock phù hợp khi adapter dùng Spring Kafka API. Nếu đang test trực tiếp Kafka clients API và muốn xem record history hoặc poll, có thể dùng các fake do kafka-clients cung cấp.

**src/test/java/com/example/messagingqa/KafkaClientFakesTest.java**

~~~java
package com.example.messagingqa;

import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.MockConsumer;
import org.apache.kafka.clients.consumer.OffsetResetStrategy;
import org.apache.kafka.clients.producer.MockProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.serialization.StringSerializer;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class KafkaClientFakesTest {

    @Test
    void producerRecordsMessageInMemory() {
        MockProducer<String, String> producer =
                new MockProducer<>(
                    true,
                    new StringSerializer(),
                    new StringSerializer());

        try {
            producer.send(new ProducerRecord<>(
                    "receipts.issued",
                    "order-9",
                    "{\"eventId\":\"evt-101\"}"));

            assertEquals(1, producer.history().size());
            ProducerRecord<String, String> record =
                    producer.history().get(0);
            assertEquals("receipts.issued", record.topic());
            assertEquals("order-9", record.key());
            assertEquals(
                    "{\"eventId\":\"evt-101\"}",
                    record.value());
        } finally {
            producer.close();
        }
    }

    @Test
    void consumerPollsPreparedRecordsInMemory() {
        MockConsumer<String, String> consumer =
                new MockConsumer<>(OffsetResetStrategy.EARLIEST);

        try {
            TopicPartition partition =
                    new TopicPartition("payments.received", 0);
            consumer.assign(List.of(partition));
            consumer.updateBeginningOffsets(
                    Map.of(partition, 0L));

            consumer.addRecord(new ConsumerRecord<>(
                    "payments.received", 0, 0L,
                    "order-9", "{\"eventId\":\"evt-101\"}"));

            ConsumerRecords<String, String> batch =
                    consumer.poll(Duration.ofMillis(1));

            assertEquals(1, batch.count());
            ConsumerRecord<String, String> record =
                    batch.iterator().next();
            assertEquals("payments.received", record.topic());
            assertEquals("order-9", record.key());
            assertEquals(0L, record.offset());
        } finally {
            consumer.close();
        }
    }
}
~~~

**MockProducer** ghi ProducerRecord vào history; constructor true dùng autoComplete sends. **MockConsumer** được assign partition và cấp beginning offset, rồi tự nạp record để poll. Hai mocks này không có Kafka cluster/consumer coordinator thật. Test MockConsumer.poll **không khởi PaymentKafkaConsumer** và không chứng minh annotation @KafkaListener hoạt động.

Spring Kafka còn có **MockProducerFactory/MockConsumerFactory** cho các bài test gắn fake client vào KafkaTemplate/listener container. Nó là một cấp test ở giữa Mockito adapter unit test và EmbeddedKafka/Testcontainers integration test; vẫn không giả lập mọi broker semantics.

## 9. Một fake in-memory cho outbound port

Với test luồng nghiệp vụ nhiều bước, fake có thể dễ đọc hơn Mockito interaction matching:

~~~java
final class InMemoryReceiptPublisher implements ReceiptPublisher {
    final java.util.List<ReceiptIssued> sent =
            new java.util.ArrayList<>();

    @Override
    public CompletableFuture<Void> publish(ReceiptIssued receipt) {
        sent.add(receipt);
        return CompletableFuture.completedFuture(null);
    }
}
~~~

Trích đoạn này có thể đặt trong test package và thêm import CompletableFuture. Một test minh họa:

~~~java
InMemoryReceiptPublisher fake = new InMemoryReceiptPublisher();
PaymentApplicationService service =
        new PaymentApplicationService(fake);

service.handle(new PaymentAccepted(
        "evt-1", "order-7", 5000L, 1));

assertEquals(1, fake.sent.size());
assertEquals(5L, fake.sent.get(0).rewardPoints());
~~~

Fake không cần broker và có thể thay thế mock publisher ở business tests. Nhưng List thường **không thread-safe** và không có partition, ack, offset, retry hay transaction. Mỗi test tạo **fake mới**, không để static mutable List làm test phụ thuộc thứ tự. Với concurrent tests, dùng synchronization/fake chuyên dụng hoặc test dưới infrastructure thật.

## 10. Khi nào dùng @MockitoBean?

Các tests runnable bên trên dùng **@ExtendWith(MockitoExtension.class)** và khởi tạo class qua constructor. Chúng không khởi Spring ApplicationContext, nên nhanh và dễ hiểu.

Nếu muốn chứng minh Spring DI/wiring thì dùng **@MockitoBean** (Spring Framework 6.2 và Boot 3.4). **@MockBean** của Spring Boot đã deprecated từ 3.4 để chuyển sang @MockitoBean. Ví dụ minh họa:

~~~java
@SpringBootTest(properties = {
    "spring.kafka.listener.auto-startup=false",
    "spring.kafka.admin.auto-create=false"
})
class ConsumerWiringExample {
    @Autowired
    PaymentKafkaConsumer consumer;

    @MockitoBean
    PaymentHandler handler;

    @Test
    void usesInjectedMockPort() {
        consumer.onMessage(
            "{\"eventId\":\"evt-1\",\"orderId\":\"o-1\","
            + "\"amountMinor\":1000,\"schemaVersion\":1}");

        verify(handler).handle(any(PaymentAccepted.class));
    }
}
~~~

Đây là **trích đoạn** cần imports tương ứng, không thuộc runnable tree. @MockitoBean thay PaymentHandler bean trong test ApplicationContext, trong khi PaymentKafkaConsumer là bean thật. **listener.auto-startup=false** tránh Kafka listener container tự poll trong test wiring; điều này **không chứng minh** Kafka broker delivery.

Nếu chỉ muốn kiểm tra mapper hoặc business, dùng unit test không context. Nhiều @SpringBootTest/@MockitoBean variants có thể tạo nhiều TestContext cache keys, khiến suite chậm và khó quản lý state.

## 11. Producer errors, future và đúng ý nghĩa acknowledge

**KafkaTemplate.send** trả CompletableFuture<SendResult>. Thao tác send invocation thành công chưa bảo đảm broker ack; future thành công dựa vào acks/producer config. Ngay cả khi broker acknowledged, downstream consumer có thể chưa xử lý record.

Trong mock adapter tests:
- **Success**: CompletableFuture.completedFuture(null) giúp test adapter result propagation, **không** xác nhận broker metadata.
- **Failure**: CompletableFuture.failedFuture(exception) chứng minh adapter không nuốt lỗi.
- **Missing stub**: mock future null gây NullPointerException, không phải một mô phỏng broker failure hợp lệ.
- **Serialization failure**: ObjectMapper ném trước KafkaTemplate.send, phải không publish message.
- **Callback**: khi dùng whenComplete/handle, chú ý callback có thể chạy trên thread khác; assertion phải chờ completion phù hợp.

Không nên viết:

~~~java
template.send(topic, key, payload)
        .whenComplete((result, ex) -> logger.error("{}", ex));
return CompletableFuture.completedFuture(null);
~~~

Đây là **trích đoạn phản ví dụ**, thiếu biến và return context; nó làm caller nhận success ngay cả khi send failed. Adapter chính trong bài trả future của template qua thenApply để **giữ trạng thái exceptional completion**.

### Unit test future vs integration test delivery

| Bằng chứng | Mockito | Broker integration |
| --- | --- | --- |
| Đúng topic/key/payload được gọi | Có | Có |
| Adapter serialize JSON đúng | Có, với ObjectMapper thật | Có |
| Future success/failure propagation | Có, bằng stub future | Có, theo broker behavior |
| Broker nhận/lưu record | Không | Có |
| Consumer group subscribe/poll | Không | Có |
| Deserializer/headers/offset/ack | Không toàn diện | Có |
| Retry attempts và DLT publish | Không toàn diện | Có |
| Duplicates dưới crash/rebalance | Không | Cần test scenario đặc biệt |
| Exactly-once business effect với DB | Không | Cần persistence + concurrency/end-to-end tests |

## 12. Consumer listener error không tự chứng minh retry

Khi @KafkaListener method ném exception, Spring Kafka listener container và **DefaultErrorHandler** quyết định retry/backoff/recovery theo cấu hình. Tùy error type và handler, poison JSON có thể bị retry, bỏ qua hoặc chuyển DLT. **assertThrows khi gọi onMessage trực tiếp chỉ chứng minh exception lan qua Java method**, không chứng minh offset được commit hay message chuyển DLT.

Tách lỗi:
- **Malformed JSON**: không parse được; thường cần non-retryable classification/DLT.
- **Unsupported schemaVersion**: business contract không hỗ trợ, thường không tự sửa bằng retry y nguyên.
- **Temporary infrastructure failure**: database/broker unavailable, có thể retry với backoff.
- **Duplicate business event**: idempotent handler nên bỏ qua tác động lặp lại một cách an toàn.
- **Permanent business rejection**: tùy policy sẽ DLT/audit/alert, tránh retry vô hạn.

Một integration test retry thật thường:
1. Cấu hình error handler cụ thể với attempts/backoff hữu hạn.
2. Gửi valid và poison records vào topic riêng.
3. Chờ observable outcome với timeout (không Thread.sleep đoán).
4. Assert số lần xử lý/DLT/offset theo policy.
5. Dọn topic/consumer group/state riêng, tránh test order dependency.

## 13. Idempotency, outbox và giới hạn exactly-once

Kafka có thể redeliver record khi consumer crash sau xử lý trước offset commit, rebalance hoặc retry. Producer cũng có thể gửi duplicate business events. Vì thế **một lần verify(times(1)) trong một unit test không chứng minh hệ thống đúng exactly-once**.

Một idempotent consumer thường ghi **eventId** vào bảng processed_events có unique constraint trong **cùng DB transaction** với business mutation. Chỉ check exists rồi insert ở hai bước không có unique constraint có thể race khi nhiều consumers chạy concurrent.

~~~text
BEGIN DB TRANSACTION
  INSERT processed_events(event_id) UNIQUE
  IF duplicate -> do not apply business mutation again
  ELSE
    UPDATE order/payment state
    INSERT outbox event in same transaction
COMMIT

Separate relay:
  load unsent outbox rows
  publish to Kafka, retry when needed
  mark delivery progress with safe concurrency/idempotency rules
~~~

Đây là **pseudocode**, không phải SQL hoàn chỉnh. Nếu service lưu processed_events trước rồi publish trực tiếp ngoài transaction và send failed, lần retry thấy eventId đã xử lý nên bỏ qua → **mất outbound message**. Vì vậy **outbox** thường phù hợp để đồng bộ database change và ý định gửi event, còn downstream consumer vẫn cần idempotency khi relay resend.

**Kafka exactly-once producer transactions** không tự biến mọi external SQL/HTTP side effect thành exactly-once. Nếu bài toán liên quan DB + message, phải thiết kế atomicity/compensation/outbox cụ thể và kiểm thử bằng database + broker thật.

Bài runnable không có DB và intentionally publish duplicate event hai lần. Đây là giới hạn phải sửa trước khi gọi implementation là production-ready cho tài chính/payments.

## 14. Contract của topic, key, schema và headers

**Topic:** adapter nhận payments.received, phát receipts.issued. Unit test assert topic cụ thể; gửi nhầm topic có thể làm consumer không bao giờ thấy message.

**Key:** ví dụ dùng orderId. Với Kafka partitioner mặc định, records cùng key thường vào cùng partition trong một topology ổn định. **Ordering chỉ được đảm bảo trong một partition**, không toàn topic và không bảo đảm khi thay đổi partition count/partitioning policy.

**eventId:** phải nhất quán qua retry để duplicate detection có ý nghĩa. Consumer không nên dùng offset đơn lẻ làm business idempotency key vì event có thể có nhiều offsets qua resend.

**schemaVersion:** trường input=1 được validation; một version=99 fail. Trong production, cần backward/forward compatibility, schema registry và deployment rollout nếu consumers không cập nhật đồng thời.

**amountMinor:** dùng integer minor units thay vì double để tránh sai số nhị phân. Với dữ liệu rất lớn, mọi phép toán nhân/cộng cần kiểm tra overflow; demo chỉ chia 1000.

**Headers:** ví dụ chỉ đặt eventId trong JSON, không gửi Kafka headers nghiệp vụ. Nếu contract yêu cầu correlation ID, traceparent, tenant ID hoặc content type trong headers, adapter phải tạo ProducerRecord/Message<?> và test exact headers. Không suy ra headers tự động xuất hiện chỉ nhờ KafkaTemplate.send(topic,key,value).

**Serializer:** YAML chỉ định StringSerializer và StringDeserializer. JSON được Jackson xử lý trong adapter. Nếu project đổi sang JsonSerializer/JsonDeserializer hoặc Avro/Protobuf, tests phải cập nhật đúng schema, type headers, trusted packages và compatibility.

## 15. Test với broker thật khi nào?

### @EmbeddedKafka

Thêm testImplementation 'org.springframework.kafka:spring-kafka-test', rồi dùng Spring Kafka @EmbeddedKafka với JUnit 5/SpringBootTest để tạo broker in-process. Một sketch annotation:

~~~java
@SpringBootTest
@EmbeddedKafka(
    partitions = 1,
    topics = {"payments.received", "receipts.issued"},
    bootstrapServersProperty =
        "spring.kafka.bootstrap-servers")
class BrokerContractExample {
    // Gửi record bằng KafkaTemplate thật.
    // Dùng test consumer để nhận receipts.issued.
    // Assert key, JSON, retry/DLT/side effect theo contract.
}
~~~

Đây là **phác thảo**, không thuộc runnable tree; nó cần imports, test consumer wiring, timeout/cleanup và assertions để trở thành integration test đầy đủ. Không coi đoạn minh họa này là bằng chứng tests đã kết nối broker.

### Testcontainers Kafka

Với Docker runner, Testcontainers có thể dựng Kafka broker thật gần production hơn. Spring Boot 3.4 hỗ trợ service connections cho các container được nhận diện, hoặc dùng @DynamicPropertySource truyền bootstrap servers. Chỉ bật integration class khi job có Docker daemon và image có thể pull. Một broker Testcontainers class thường chậm hơn unit tests; nên chia CI jobs fast-tests và integration-tests.

### Không chọn broker test nếu chỉ muốn tính rewardPoints

Nếu requirement là “12.345 minor units → 12 reward points”, plain Mockito business test là đúng cấp. Nếu requirement là “poison message được DLT sau N attempts, consumer group offset an toàn”, test với broker/container thật. **Tách đúng cấp giúp kết quả chẩn đoán rõ ràng**, không lạm dụng @SpringBootTest để chạy những quy tắc đơn giản.

## 16. Chạy unit tests và kết quả kỳ vọng

Với Gradle Wrapper tương thích JDK 17 và dependencies như trên:

~~~bash
./gradlew clean test
./gradlew test --tests com.example.messagingqa.PaymentApplicationServiceTest
./gradlew test --tests com.example.messagingqa.PaymentKafkaConsumerTest
./gradlew test --tests com.example.messagingqa.KafkaReceiptPublisherTest
./gradlew test --tests com.example.messagingqa.KafkaClientFakesTest
~~~

Trên Windows dùng **gradlew.bat** cùng arguments. Vì tests dùng MockitoExtension hoặc Kafka MockProducer/MockConsumer in-memory và **không có @SpringBootTest**, chúng **không cần Kafka chạy tại localhost:9092**. Kết quả dự kiến theo assertions:

| Nhóm test | Kết quả kỳ vọng |
| --- | --- |
| Business valid | Captured ReceiptIssued rewardPoints=12, đủ eventId/orderId/schemaVersion |
| Business invalid | IllegalArgumentException, publisher không nhận invocation |
| Business future failed | CompletionException chứa lỗi gốc |
| Business duplicate | Hai lần publish, phơi bày thiếu idempotency |
| Consumer JSON valid | PaymentAccepted fields đúng, handler được gọi |
| Consumer malformed JSON | IllegalArgumentException và handler không được gọi |
| Consumer handler failed | Exception lan ra adapter boundary |
| Producer send success | Đúng topic receipts.issued, key order-9, JSON fields đúng |
| Producer send failed | Exceptional future propagation |
| MockProducer | Một ProducerRecord xuất hiện trong history |
| MockConsumer | Poll đúng một record ở partition 0, offset 0 |

**Không bịa stdout, Kafka offset từ broker hoặc Gradle BUILD SUCCESSFUL khi chưa thực chạy**. Kafka MockConsumer offset 0 là giá trị **test tự nạp**, không phải offset được broker cấp.

## 17. Các lỗi thường gặp và cách sửa

| Lỗi thiết kế/test | Vì sao nguy hiểm | Hướng sửa |
| --- | --- | --- |
| Mock cả business service | Không chạy business rule | Giữ service thật; mock port |
| Mock mapper trên consumer success path | Che lỗi JSON field types | ObjectMapper thật |
| verify publisher(any()) | Không bắt payload sai | ArgumentCaptor + field assertions |
| verify template.send(any...) | Không bắt topic/key sai | eq topic/key + JSON assertion |
| Mock future bị null | NPE vô nghĩa, không mô phỏng broker | completedFuture/failedFuture |
| Adapter trả success dù future failed | Nuốt lỗi send | Trả future phụ thuộc send |
| Unit test gọi onMessage rồi bảo offset commit | Không có listener container | Broker integration |
| Dùng MockConsumer để xác nhận group rebalance | Fake không có coordinator | EmbeddedKafka/Testcontainers |
| Dùng Thread.sleep chờ message | Flaky theo máy/tải | Await observable condition với timeout |
| Producer ack nghĩa downstream processed | Hai công đoạn khác nhau | Consumer/DB integration assertions |
| Không có eventId/idempotency | Redelivery gây duplicate side effects | Unique processed-event ID + transaction |
| Ghi processed ID trước publish rồi fail send | Có nguy cơ mất event | Outbox + relay |
| Business code dùng KafkaTemplate trực tiếp | Coupling framework và rule | ReceiptPublisher port |
| Dùng @MockBean ở code mới Boot 3.4 | Deprecated | @MockitoBean khi cần Spring context |
| Mọi test đều @SpringBootTest | Slow suite và config flakiness | MockitoExtension cho unit boundaries |
| Assert hard-coded Kafka partition/offset không có broker | Sai mô hình | Chỉ assert offset giả nếu dùng MockConsumer |
| Fake lưu List static qua test classes | Phụ thuộc thứ tự và concurrency | Fresh fake mỗi test |
| Không kiểm tra poison message | Infinite retry hoặc DLT policy sai | Broker integration test lỗi |
| Không test async future failure | False success | failedFuture và assert cause |
| Xóa topic/data của test khác | Flaky parallel CI | Namespace/topic/group riêng |

## 18. Quy trình review một messaging feature

**Bước 1.** Viết rõ message contract: eventId, schemaVersion, topic, key, value schema, headers, authorization và privacy constraints.

**Bước 2.** Tách PaymentHandler/ReceiptPublisher hoặc các ports tương tự; business core không phụ thuộc Spring Kafka types.

**Bước 3.** Unit test business, dùng mock/fake outbound port, xác minh arguments và số lần side effect đúng trong một lần invocation.

**Bước 4.** Unit test inbound adapter với JSON thật, handler mock, malformed JSON, exception propagation.

**Bước 5.** Unit test outbound adapter với KafkaTemplate mock, ObjectMapper thật, topic/key/payload và exceptional future.

**Bước 6.** Nếu code trực tiếp thao tác Kafka clients API, dùng MockProducer/MockConsumer để test record/poll path, nhưng không ngộ nhận là broker.

**Bước 7.** Integration test với EmbeddedKafka/Testcontainers khi cần serialization thực, listener container, offset, retry/DLT, partition handling và transactions.

**Bước 8.** Test idempotency và state bằng DB unique constraints/outbox, bao gồm duplicate delivery và concurrency.

**Bước 9.** Test performance/operational riêng cho lag, throughput, partitions, startup/readiness và error recovery.

Một test nên thất bại ở đúng tầng nó bảo vệ: reward rule sai → business test fail; topic/key/JSON sai → adapter test fail; listener/container config sai → broker integration fail.

## 19. Câu hỏi tự kiểm tra

**1.** Muốn test rewardPoints thì mock gì? **ReceiptPublisher**, giữ PaymentApplicationService thật.

**2.** KafkaReceiptPublisher gửi nhầm topic nhưng đúng payload. verify(send(any...)) có đủ không? **Không**; assert exact topic.

**3.** KafkaTemplate.send trả về gì trong Spring Kafka 3.x? **CompletableFuture<SendResult<K,V>>**.

**4.** Gọi send thành công có nghĩa downstream consumer đã xử lý không? **Không**; future/broker/consumer/business state là các cấp khác nhau.

**5.** Gọi trực tiếp @KafkaListener method có kiểm thử consumer group không? **Không**.

**6.** Tại sao không mock ObjectMapper trong consumer success test? Vì muốn test JSON mapping thật.

**7.** JSON malformed nên retry vô hạn không? **Không nên mặc định**; cần non-retryable/DLT policy theo contract.

**8.** MockProducer có thật sự gửi record vào Kafka cluster không? **Không**, chỉ lưu history trong memory.

**9.** MockConsumer có thực sự được group coordinator assign partition không? **Không**, test tự assign.

**10.** Kafka key có bảo đảm ordering toàn topic không? **Không**, ordering trong partition.

**11.** eventId trong JSON tự làm handler idempotent chưa? **Chưa**, cần lưu/kiểm soát unique eventId và transaction state.

**12.** Producer future failed mà adapter trả completedFuture(null) là gì? **Nuốt lỗi**, có thể báo xử lý thành công giả.

**13.** @MockitoBean dùng khi nào? Khi cần override Spring bean trong ApplicationContext; pure unit thường dùng MockitoExtension.

**14.** Kafka @EmbeddedKafka cần module nào? **spring-kafka-test**.

**15.** Testcontainers Kafka yêu cầu gì? **Docker-compatible runtime/daemon** và dependency/container config phù hợp.

**16.** Join future trong listener đánh đổi gì? Dễ propagate exception nhưng **block listener thread**, ảnh hưởng throughput.

**17.** Vì sao DB updated rồi Kafka send failed có thể mất event? DB commit và Kafka send không atomic; cần outbox/pattern thích hợp.

**18.** Thay mock ReceiptPublisher bằng fake List có được không? **Có**, nếu test sở hữu state và không coi fake là broker.

**19.** Verify(times(1)) sau một lần gọi có chứng minh exactly-once khi redelivery không? **Không**.

**20.** Khi nào cần integration broker? Khi contract liên quan **real transport, serializer, consumer group, offset/ack, retry, DLT hoặc concurrency**.

### Checklist QA

- Business service có interface port thay vì import KafkaTemplate?
- Consumer adapter là subject thật khi test parsing/dispatch?
- Producer adapter là subject thật khi test topic/key/JSON?
- Unit tests dùng ObjectMapper thật ở success path?
- Mockito stubs trả future hợp lệ, có failedFuture path?
- Business tests assert chính xác message fields, validation, no interactions khi invalid?
- Consumer tests assert malformed JSON không dispatch và handler exception propagate?
- Producer tests assert topic, key và JSON content, không chỉ invocation count?
- Có phân biệt mock/fake clients với broker integration?
- Có ghi rõ offset/retry/DLT **không được chứng minh** bằng gọi trực tiếp listener?
- Kafka key, eventId, schemaVersion và ordering semantics đúng?
- Duplicate behavior được nhận diện, không giả vờ exactly-once?
- DB + event cần atomicity có idempotency/outbox strategy?
- Không dùng Thread.sleep hoặc state của test trước?
- Boot 3.4 context tests ưu tiên @MockitoBean thay @MockBean deprecated?
- Có bổ sung EmbeddedKafka/Testcontainers khi yêu cầu thực sự ở broker boundary?
- Không báo rằng Gradle/broker đã chạy khi chưa có bằng chứng?

**Kết luận:** Để kiểm thử Messaging hiệu quả, hãy **mock ở ranh giới phụ thuộc, không mock chủ thể đang test**. Business service thật với mock ReceiptPublisher chứng minh luật nghiệp vụ; consumer adapter thật với ObjectMapper thật và handler mock chứng minh mapping; producer adapter thật với KafkaTemplate mock chứng minh topic/key/payload/future. Những test ấy không thay broker integration: offset, retry, DLT, duplicate delivery và DB-message consistency vẫn cần kiểm thử ở hạ tầng phù hợp.

## Tài liệu chính thức

- Spring Kafka — Sending Messages và KafkaTemplate CompletableFuture: https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html
- Spring Kafka 3.3 — Testing Applications, EmbeddedKafka, MockProducerFactory/MockConsumerFactory: https://docs.spring.io/spring-kafka/reference/3.3/testing.html
- Spring Kafka — Receiving Messages bằng @KafkaListener: https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/listener-annotation.html
- Spring Kafka — Error Handling, DefaultErrorHandler: https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html
- Spring Framework 6.2 — @MockitoBean: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html
- Spring Boot 3.4 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.4/reference/testing/spring-boot-applications.html
- Apache Kafka Client API — MockProducer và MockConsumer: https://kafka.apache.org/documentation/
