# Giữ phương thức listener ngắn và ủy quyền nghiệp vụ trong Spring JMS

## 1. Mục tiêu và vấn đề thực tế

Trong Spring JMS, phương thức gắn `@JmsListener` là **điểm vào của message từ broker**, không nhất thiết là nơi đặt toàn bộ quy trình nghiệp vụ. Một listener vừa giải mã JSON, kiểm tra hợp đồng, truy vấn database, tính tiền, gọi API bên ngoài, cập nhật trạng thái, gửi email và tự quyết định retry sẽ nhanh chóng trở thành khối mã khó kiểm thử, khó tái sử dụng và dễ mắc lỗi transaction.

Nguyên tắc thiết kế nên là **thin listener / message adapter**: listener nhận dữ liệu từ JMS, thu thập metadata tối thiểu, chuyển sang dạng đầu vào của ứng dụng, **ủy quyền cho service nghiệp vụ**, và **để cơ chế transaction/acknowledgment xử lý kết quả**. Logic nghiệp vụ nên nằm trong service, không trộn lẫn với chi tiết `jakarta.jms.Message`, Queue name hoặc JMS Session.

Sau bài học, bạn có thể:

1. Phân biệt trách nhiệm **JMS listener adapter**, **message decoder/validator**, **application service** và **domain layer**.
2. Viết `@JmsListener` ngắn nhưng vẫn rõ nghĩa, xử lý đúng `@Payload`, `@Header`, schema version và correlation/event ID.
3. Hiểu vì sao **không nuốt exception**, không tự ack/rollback tùy tiện, không tạo thread hay `@Async` fire-and-forget trong listener.
4. Cấu hình JMS session transacted, retry/redelivery/DLQ và idempotency theo ranh giới đúng.
5. Kiểm soát concurrency, transaction DB, side effects, observability và bảo mật dữ liệu.
6. Chạy một ví dụ **Java 17+, Spring Boot 3.5.7, ActiveMQ Artemis embedded, Jackson** với một listener chỉ có hai lệnh chính.
7. Viết unit/integration test riêng cho adapter, decoder và nghiệp vụ.

Bài thuộc nhóm **Dữ liệu listener**, nên trọng tâm là cách listener **tiếp nhận payload và headers**, kiểm soát ranh giới dữ liệu, rồi chuyển quyền xử lý cho service.

## 2. Listener là adapter, không phải toàn bộ ứng dụng

Spring cho phép khai báo một message-driven POJO đơn giản:

~~~java
@Component
public class OrderListener {

    @JmsListener(destination = "orders.commands")
    public void onMessage(String payload) {
        // Gọi phần xử lý đơn hàng.
    }
}
~~~

Spring tạo message listener container phía sau annotation, nhận từ Queue/Topic đã cấu hình, convert/resolve tham số và gọi method trên bean. **Container** sở hữu cơ chế receive, Session, MessageConsumer, threading, startup/shutdown và transaction JMS; method listener là **callback của ứng dụng**.

Mô hình phân lớp:

~~~mermaid
flowchart LR
    A[("JMS Queue")] --> B["Spring listener container"]
    B --> C["@JmsListener: adapter"]
    C --> D["Decoder / contract validator"]
    D --> E["Application service"]
    E --> F["Domain + repository + ports"]
    F --> G["Database / external systems"]
~~~

Các nhiệm vụ nên tách:

| Lớp | Nên chịu trách nhiệm | Không nên bị buộc chịu |
| --- | --- | --- |
| **JMS listener adapter** | Nhận payload và metadata, gọi decoder/delegate, để exception đi qua theo chính sách. | Tính toán nghiệp vụ phức tạp, SQL, tự điều khiển broker transaction một cách rời rạc. |
| **Decoder / message contract validator** | Parse JSON/Bytes/Map, kiểm tra schema version, field bắt buộc và coherence giữa header/body. | Tự quyết định ghi DB, gửi email, thay trạng thái đơn hàng. |
| **Application service** | Điều phối use case, transaction nghiệp vụ, idempotency, gọi domain/repository/ports. | Phải biết tên JMS Queue hoặc sống phụ thuộc `jakarta.jms.Session`. |
| **Domain model/service** | Invariants nghiệp vụ, quy tắc tính toán và trạng thái. | Phụ thuộc `@JmsListener`, Spring JMS hoặc selector. |
| **Listener container / broker** | Receive/dispatch, session transaction, redelivery/recovery, DLQ theo cấu hình. | Định nghĩa business success hay quyết định dữ liệu hợp lệ. |

**“Listener ngắn” không phải cuộc thi giảm số dòng.** Một method dài 5 dòng nhưng gọi một “god service” 2.000 dòng không tự trở thành thiết kế tốt. Điểm cần tối ưu là **ranh giới trách nhiệm và khả năng kiểm thử độc lập**, không phải ép mọi listener chỉ còn một biểu thức.

### 2.1. Vì sao điều này quan trọng với dữ liệu listener?

JMS chỉ giao một `Message` với header, properties và body. Ứng dụng phải hiểu:

- Body là `TextMessage` JSON, `BytesMessage` hay định dạng khác?
- `schemaVersion` có còn được consumer hỗ trợ?
- `eventId`/`JMSCorrelationID` có khớp hợp đồng không?
- Payload đã có đủ dữ liệu để xử lý nghiệp vụ chưa?
- Thông tin nào đến từ broker, thông tin nào do producer tự đặt?
- Nếu decode/validation thất bại thì có nên retry lại đúng message đó không?

Nếu các bước này nằm lẫn trong logic cập nhật DB, một lỗi body dễ bị hiểu nhầm thành lỗi transaction hoặc ngược lại. Decoder/validator độc lập giúp tạo **đường ranh rõ** giữa dữ liệu vận chuyển và dữ liệu nghiệp vụ.

## 3. Phản ví dụ: listener ôm mọi trách nhiệm

Ví dụ phản diện dưới đây chỉ là **mã minh họa**, không phải class hoàn chỉnh; các dependency chưa khai báo:

~~~java
@JmsListener(destination = "orders.created")
public void onOrder(String json) {
    try {
        OrderDto dto = objectMapper.readValue(json, OrderDto.class);
        if (dto.orderId() == null) {
            return;
        }

        OrderEntity order = repository.findById(dto.orderId()).orElseThrow();
        order.setStatus("CONFIRMED");
        repository.save(order);

        paymentClient.capture(dto.orderId());
        mailClient.sendConfirmation(dto.orderId());
        jmsTemplate.convertAndSend("orders.audit", json);

    } catch (Exception ex) {
        log.error("Cannot process message", ex);
        // Chỉ log rồi return -> có thể khiến container coi là thành công.
    }
}
~~~

Vấn đề không chỉ là method dài. Nó trộn **transport parsing**, **validation**, **DB transaction**, **external API**, **JMS publishing**, **error policy** và **logging** trong một callback.

Các rủi ro cụ thể:

1. `return` khi thiếu `orderId` có thể khiến một message sai bị **ack như xử lý thành công**, không còn cơ hội phân loại/quarantine.
2. `catch(Exception)` rồi return khiến container **không thấy lỗi**; với session transacted, listener có thể commit JMS dù business thất bại.
3. DB commit có thể thành công nhưng gọi payment/email/JMS audit thất bại; không có transaction nguyên tử tự động giữa các hệ thống.
4. Khi message được giao lại, payment/email có nguy cơ **thực hiện hai lần** nếu không có idempotency.
5. Đổi định dạng JSON buộc sửa method JMS lẫn logic nghiệp vụ.
6. Unit test phải mock database, HTTP client, JMS template, object mapper, transaction — khó định vị lỗi.
7. Một consumer khác (REST API, batch, Kafka) khó tái sử dụng use case nếu nó gắn chặt `@JmsListener`.

**Cách sửa:** đưa parsing/validation vào một decoder có contract riêng; đưa xử lý use case vào application service; giữ JMS callback làm adapter. Lỗi từ service phải đi qua transaction/error policy đúng, không bị nuốt.

## 4. Mẫu listener ngắn, rõ ranh giới

~~~java
@Component
public class OrderCreatedJmsListener {

    private final OrderMessageDecoder decoder;
    private final OrderApplicationService applicationService;

    public OrderCreatedJmsListener(
            OrderMessageDecoder decoder,
            OrderApplicationService applicationService) {
        this.decoder = decoder;
        this.applicationService = applicationService;
    }

    @JmsListener(destination = "orders.created")
    public void onMessage(
            @Payload String json,
            @Header("eventId") String eventId,
            @Header("schemaVersion") int schemaVersion) {

        OrderCreatedEvent event =
                decoder.decode(json, eventId, schemaVersion);

        applicationService.process(event);
    }
}
~~~

**Đây là fragment cấu trúc**, chưa có package và định nghĩa `OrderMessageDecoder`, `OrderApplicationService`, `OrderCreatedEvent`; bản đầy đủ xuất hiện ở mục demo.

Hai lệnh nghiệp vụ của listener:

1. `decoder.decode(...)` chuyển payload/headers thành **event object hợp lệ theo contract**.
2. `applicationService.process(event)` thực thi use case.

Listener **không tự** gọi `message.acknowledge()`, commit JMS, mở HTTP connection hoặc catch mọi exception. Những việc đó thuộc container, transaction configuration và service/ports tương ứng.

Có thể tổ chức chỉ **một** lệnh `service.handleIncoming(json, metadata)` nếu application service có inbound adapter rõ ràng, nhưng đừng để service nghiệp vụ phải biết JMS header names nếu có thể tránh.

### 4.1. Dùng constructor injection

Ưu tiên constructor injection, fields `final`. Nó làm dependency bắt buộc rõ ràng, đơn giản hóa unit tests và tránh trạng thái bean chưa hoàn chỉnh. Không gọi `new OrderApplicationService()` trong method listener: Spring không còn kiểm soát transaction proxy/DI và bạn tự tạo lại đối tượng cho từng message.

### 4.2. Không nhầm Spring bean lifecycle với message lifecycle

Bean listener thường là singleton. Một bean có thể được gọi hàng nghìn lần bởi listener container. Nó **không** được Spring tạo mới cho từng JMS message. Thêm `@PostConstruct` vào bean listener không làm callback đó chạy trước mỗi message; `@PreDestroy` không có nghĩa “ack message cuối cùng”.

Một container có thể start/stop/recover trong khi bean listener/application service vẫn sống. Do đó đừng lưu trạng thái xử lý **của một message** trong mutable field của singleton listener.

## 5. Nhận payload và headers đúng API

Spring `@JmsListener` có method signature linh hoạt: nhận `jakarta.jms.Message` (raw), `jakarta.jms.Session`, `org.springframework.messaging.Message<T>`, `@Payload`, `@Header`, `@Headers` hoặc payload param không annotation. Đó là API của **listener method**, không phải cơ chế tự bảo đảm payload đã hợp lệ nghiệp vụ.

### 5.1. String body + custom headers

~~~java
@JmsListener(destination = "orders.created")
public void onMessage(
        @Payload String json,
        @Header("eventId") String eventId,
        @Header("schemaVersion") int schemaVersion) {

    applicationService.process(
            decoder.decode(json, eventId, schemaVersion));
}
~~~

`@Header("eventId")` đọc **JMS custom property** được Spring mapping vào message headers. `schemaVersion` phải được publisher đặt đúng type (ví dụ `setIntProperty`). Nếu một property bắt buộc vắng mặt hoặc conversion lỗi, exception có thể phát sinh ở **argument resolution** trước khi method được gọi. Monitor phải bao gồm **listener adapter/container errors**, không chỉ logs trong business service.

### 5.2. Raw Jakarta JMS Message khi thực sự cần

~~~java
@JmsListener(destination = "orders.created")
public void onMessage(jakarta.jms.Message message)
        throws jakarta.jms.JMSException {

    String eventId = message.getStringProperty("eventId");
    int version = message.getIntProperty("schemaVersion");

    if (!(message instanceof jakarta.jms.TextMessage text)) {
        throw new IllegalArgumentException("Expected TextMessage");
    }

    applicationService.process(
            decoder.decode(text.getText(), eventId, version));
}
~~~

Fragment này phù hợp khi cần kiểm soát rõ `TextMessage`/`BytesMessage`, đọc `JMSCorrelationID` hoặc `JMSXDeliveryCount`. Nhưng nếu mọi listener đều tự xử lý thô hàng chục JMS headers, nên tách `JmsEnvelopeMapper` hoặc adapter thành phần riêng thay vì lặp ở mọi method.

Không dựa vào header do client tự đặt (`tenantId`, `role`) như bằng chứng duy nhất về quyền truy cập. Broker ACL và logic validation là các lớp khác nhau. Không dùng raw `ObjectMessage` deserialization cho dữ liệu không đáng tin nếu chưa cấu hình trusted types.

### 5.3. Typed payload

Khi một `MessageConverter` được cấu hình phù hợp, Spring có thể gọi:

~~~java
@JmsListener(destination = "orders.created")
public void onMessage(@Payload OrderCreatedEvent event) {
    applicationService.process(event);
}
~~~

Nhưng **điều kiện quan trọng**: `SimpleMessageConverter` mặc định **không tự biến mọi JSON String thành domain record**. Nếu dùng DTO typed trong method, phải cấu hình converter/JSON type mapping và kiểm thử schema evolution. Nếu không, nhận `String` rồi dùng decoder đã định nghĩa sẽ minh bạch hơn.

`@Valid @Payload` có thể kích hoạt bean validation khi Spring method-argument infrastructure được cấu hình validator phù hợp; không mặc nhiên nghĩ thêm annotation là đủ để tất cả ràng buộc trên payload chạy trong mọi Spring setup.

### 5.4. Header nào nên truyền vào business service?

| Metadata | Adapter cần không? | Nên làm gì? |
| --- | --- | --- |
| `eventId` (custom property) | Thường có | Dùng trong idempotency/audit, kiểm tra trùng body. |
| `schemaVersion` | Có nếu format tiến hóa | Chọn decoder/contract, từ chối version không hỗ trợ. |
| `JMSCorrelationID` | Khi cần trace/request-reply | Có thể map sang `CorrelationContext` ứng dụng; không biến thành domain ID mặc định. |
| `JMSType` | Khi hợp đồng dùng type JMS | Kiểm tra event kind nếu cần; tránh tên mâu thuẫn với property khác. |
| `JMSMessageID` | Dùng để chẩn đoán | ID một lần send, không thay `eventId` nghiệp vụ. |
| `JMSXDeliveryCount` | Khi quan sát redelivery | Có thể đưa vào log/metrics; không tự sửa hay làm nguồn duy nhất để quyết định business retry. |
| `tenantId` | Khi đa tenant | Validate với danh tính/ACL; tránh tin mù quáng giá trị do producer gửi. |
| Mọi headers/properties | Không nên truyền bừa | Chỉ giữ những field service thực sự cần. |

**Không ép business service nhận nguyên `jakarta.jms.Message` hoặc `JmsHeaders` nếu chỉ cần `OrderCreatedEvent` và `eventId`.** Nếu service bắt buộc biết JMS type, nó trở nên phụ thuộc transport và khó tái dùng qua API khác.

## 6. Phân biệt validation tại ranh giới và business validation

Tách hai tầng:

**Contract/input validation** (decoder hoặc adapter): JSON hợp lệ? schemaVersion được hỗ trợ? Trường bắt buộc có tồn tại? `eventId` header khớp body? Kiểu `amountMinor` có đúng integer? Đây là điều kiện để dữ liệu có thể được hiểu.

**Business validation** (application/domain): đơn hàng có tồn tại? đã thanh toán chưa? được phép chuyển trạng thái không? tiền có âm không theo domain invariant? event đã xử lý chưa? Đây là các quy tắc quyết định side effects.

| Ví dụ lỗi | Phát hiện ở đâu? | Chính sách gợi ý |
| --- | --- | --- |
| JSON bị cắt cụt | Decoder | Permanent-format error → quarantine/DLQ có kiểm soát. |
| `schemaVersion=99` chưa hỗ trợ | Decoder | Không retry vô hạn đúng payload; version upgrade/quarantine. |
| Header `eventId=A` nhưng body `eventId=B` | Decoder | Từ chối, audit producer contract. |
| `orderId` rỗng | Decoder/contract | Từ chối trước side effect. |
| Đơn hàng đã hoàn tất | Domain/application | Xử lý idempotent hoặc business reject theo contract. |
| Database tạm unreachable | Repository/application | Có thể retry với rollback/backoff. |
| HTTP payment timeout | Outbound port | Có thể retry nhưng cần idempotency key và hiểu trạng thái không chắc chắn. |

**Không để message sai schema chạy nửa transaction rồi mới phát hiện.** Validate đầu vào sớm và thống nhất. Tuy nhiên listener “ngắn” không đồng nghĩa phải thực hiện mọi phép validation ngay trong annotation method; decoder/service mới là nơi thích hợp.

## 7. Ví dụ chạy được: Spring Boot + Artemis + listener hai lệnh

Demo sử dụng **Java 17+**, **Spring Boot 3.5.7**, **Maven**, **Apache ActiveMQ Artemis embedded**, Jackson. Ứng dụng:

- Gửi một JSON `TextMessage` vào Queue `demo.order-events`.
- Gắn hai JMS properties: `eventId` (String) và `schemaVersion` (int).
- Listener chỉ gọi decoder rồi application service.
- Decoder parse/validate và đối chiếu header với body.
- Business service in một dòng và báo hoàn tất qua `CountDownLatch`.
- ApplicationRunner kiểm tra handler đã được gọi, sau đó đóng context.

**Lưu ý:** đây là demo một message, không có database, không mô phỏng exactly-once. Idempotency và transaction DB production được giải thích riêng ở các mục sau.

### 7.1. Cấu trúc

~~~text
jms-thin-listener-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/jmsthin/
    │   ├── ThinListenerApplication.java
    │   ├── OrderCreatedEvent.java
    │   ├── OrderEventDecoder.java
    │   ├── OrderApplicationService.java
    │   └── OrderJmsListener.java
    └── resources/
        └── application.properties
~~~

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>jms-thin-listener-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-server</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-json</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter-artemis` cung cấp Spring JMS integration/client, `artemis-jakarta-server` cho broker nhúng và `spring-boot-starter-json` cung cấp Jackson `ObjectMapper`. Boot parent quản lý versions tương thích.

### 7.3. application.properties

~~~properties
spring.artemis.mode=embedded
spring.artemis.embedded.queues=demo.order-events
spring.artemis.embedded.persistent=false

spring.jms.pub-sub-domain=false
spring.jms.listener.session.transacted=true
spring.jms.listener.min-concurrency=1
spring.jms.listener.max-concurrency=1

spring.main.web-application-type=none
spring.main.banner-mode=off
~~~

- `spring.artemis.embedded.queues` provision Queue thử nghiệm khi broker nhúng start.
- `spring.jms.listener.session.transacted=true` yêu cầu container sử dụng **local JMS transacted session**; exception từ handler thông thường sẽ làm session rollback, nhưng broker redelivery/DLQ policy vẫn cần được cấu hình khi thực sự triển khai.
- Đặt concurrency một consumer để demo dễ quan sát.
- `persistent=false` chỉ phục vụ demo, **không** bảo đảm message được lưu qua restart.
- `web-application-type=none` tránh web server không cần thiết.

Các thuộc tính trên là **Spring Boot 3.5**; nếu bạn thay bằng custom `JmsListenerContainerFactory`, cần bảo đảm factory dùng thật có cùng transaction/concurrency settings.

### 7.4. OrderCreatedEvent.java

~~~java
package com.example.jmsthin;

public record OrderCreatedEvent(
        String eventId,
        String orderId,
        long amountMinor) {
}
~~~

Record là **domain-facing input model** đơn giản. `amountMinor` là đơn vị tiền nhỏ nhất (ví dụ cent), tránh dùng floating-point khi minh họa tiền. Demo chỉ kiểm tra `amountMinor > 0`; production cần biết currency, max value, rounding và invariants khác.

### 7.5. OrderEventDecoder.java

~~~java
package com.example.jmsthin;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.stereotype.Component;

@Component
public class OrderEventDecoder {

    private final ObjectMapper objectMapper;

    public OrderEventDecoder(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public OrderCreatedEvent decode(
            String json,
            String headerEventId,
            int schemaVersion) {

        if (schemaVersion != 1) {
            throw new IllegalArgumentException(
                    "Unsupported schemaVersion: " + schemaVersion);
        }

        try {
            OrderCreatedEvent event =
                    objectMapper.readValue(json, OrderCreatedEvent.class);

            if (event.eventId() == null
                    || event.eventId().isBlank()
                    || event.orderId() == null
                    || event.orderId().isBlank()
                    || event.amountMinor() <= 0
                    || !event.eventId().equals(headerEventId)) {
                throw new IllegalArgumentException(
                        "Invalid event contract or eventId mismatch");
            }

            return event;
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException(
                    "Invalid OrderCreated JSON", ex);
        }
    }
}
~~~

Decoder chỉ giải mã và xác minh **contract**:

- `schemaVersion=1` là phiên bản duy nhất được demo hỗ trợ.
- `ObjectMapper` từ Spring Boot chuyển JSON thành Java record.
- `eventId` trong body phải khớp JMS custom property.
- `orderId` không rỗng, `amountMinor` dương.

Nếu message sai contract, decoder ném exception **trước khi application service làm side effects**. Trong môi trường transacted, exception propagate sẽ khiến JMS transaction không commit bình thường; để tránh poison message được retry vô hạn, cần có max-delivery/DLQ/quarantine policy ở broker.

Đây là decoder đơn giản. Với contract JSON phức tạp, cân nhắc JSON Schema validator, giới hạn kích thước/độ sâu message, kiểu dữ liệu và xử lý unknown fields/duplicate JSON keys theo chính sách. Đừng dùng “Jackson parse được” thay cho toàn bộ business validation.

### 7.6. OrderApplicationService.java

~~~java
package com.example.jmsthin;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.stereotype.Service;

@Service
public class OrderApplicationService {

    private final CountDownLatch processed =
            new CountDownLatch(1);

    public void process(OrderCreatedEvent event) {
        // Demo đại diện cho business operation.
        System.out.println(
                "BUSINESS_PROCESSED=" + event.orderId()
                        + " amountMinor=" + event.amountMinor());

        processed.countDown();
    }

    public boolean awaitProcessed(long timeout, TimeUnit unit)
            throws InterruptedException {
        return processed.await(timeout, unit);
    }
}
~~~

Service **không có annotation JMS**, không biết Queue name và không nhận `jakarta.jms.Message`. Nó có thể được unit test trực tiếp bằng một `OrderCreatedEvent`. Demo dùng `CountDownLatch` để quan sát một lần xử lý; nó **không phải idempotency store** hay implementation production của service.

Quan trọng: service `process` trong thực tế có thể có DB transaction, domain validation và các outbound ports, nhưng không nên trực tiếp làm transport parsing và điều khiển JMS acknowledgment.

### 7.7. OrderJmsListener.java — method listener ngắn

~~~java
package com.example.jmsthin;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;

@Component
public class OrderJmsListener {

    private final OrderEventDecoder decoder;
    private final OrderApplicationService service;

    public OrderJmsListener(
            OrderEventDecoder decoder,
            OrderApplicationService service) {
        this.decoder = decoder;
        this.service = service;
    }

    @JmsListener(id = "ordersThinListener", destination = "demo.order-events")
    public void onMessage(
            @Payload String json,
            @Header("eventId") String eventId,
            @Header("schemaVersion") int schemaVersion) {

        OrderCreatedEvent event =
                decoder.decode(json, eventId, schemaVersion);

        service.process(event);
    }
}
~~~

**Đây là hai lệnh có ý nghĩa trong listener**, nhưng không vì ép số dòng: phương thức thể hiện chính xác quá trình **transport data → validated event → business use case**.

Không có `catch (Exception)`, `new Thread`, `@Async`, `jmsTemplate.receive()` hay `message.acknowledge()` ở đây. Runtime JMS/transaction được container quản lý; service test được độc lập.

### 7.8. ThinListenerApplication.java

~~~java
package com.example.jmsthin;

import java.util.concurrent.TimeUnit;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
@EnableJms
public class ThinListenerApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(ThinListenerApplication.class, args)) {
            // Khi ApplicationRunner xong, đóng context demo.
        }
    }

    @Bean
    ApplicationRunner sendOneEvent(
            JmsTemplate template,
            OrderApplicationService service) {

        return args -> {
            String json =
                    "{\"eventId\":\"EV-188\","
                            + "\"orderId\":\"O-188\","
                            + "\"amountMinor\":12550}";

            template.convertAndSend("demo.order-events", json, message -> {
                message.setStringProperty("eventId", "EV-188");
                message.setIntProperty("schemaVersion", 1);
                return message;
            });

            if (!service.awaitProcessed(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Listener did not process message in 10 seconds");
            }

            System.out.println("HANDLER_OBSERVED=true");
        };
    }
}
~~~

`@EnableJms` được viết tường minh cho dễ theo dõi annotation infrastructure; Spring Boot JMS auto-configuration cũng có thể cung cấp nó. Producer là `JmsTemplate`, gửi String nên `SimpleMessageConverter` tạo `TextMessage`; hai custom properties được đặt bằng `MessagePostProcessor`. Listener nhận String và properties đã được mapping qua Spring listener adapter.

Một `ApplicationRunner` gửi message sau khi context khởi tạo; JMS listener container thông thường đã có cơ hội auto-start ở giai đoạn context refresh. Ngay cả nếu consumer chưa kịp receive, Queue demo có thể giữ message cho đến khi consumer sẵn sàng theo broker policy.

Dùng `try-with-resources` để đóng context khi demo xong, tránh ứng dụng console chạy mãi vì listener threads.

### 7.9. Lệnh chạy và output

Từ thư mục `jms-thin-listener-demo`:

~~~bash
mvn spring-boot:run
~~~

Các dòng do mã ứng dụng in, không tính log Maven/Spring/Artemis, dự kiến:

~~~text
BUSINESS_PROCESSED=O-188 amountMinor=12550
HANDLER_OBSERVED=true
~~~

`BUSINESS_PROCESSED` được in **trước** khi CountDownLatch giảm về 0 nên xuất hiện trước dòng từ runner. Tuy nhiên `HANDLER_OBSERVED=true` chỉ chứng minh service đã đi tới điểm latch, **không phải chứng thư rằng database hay JMS transaction đã commit**. Ví dụ chưa được thực thi Maven trong tài liệu này; đây là output kỳ vọng khi dependencies/broker hoạt động theo cấu hình đã nêu.

### 7.10. Thí nghiệm thay đổi

1. Đổi `eventId` trong JMS property từ `EV-188` thành `EV-DIFFERENT`, giữ body: decoder từ chối trước khi gọi business service. Với transacted session, broker có thể redeliver; đừng để test lỗi này chạy vô hạn ở production.
2. Đổi `schemaVersion` từ `1` sang `2`: decoder hiện tại từ chối version chưa hỗ trợ.
3. Đổi `amountMinor` trong JSON thành `0`: decoder từ chối theo hợp đồng.
4. Xóa custom property `eventId`: Spring `@Header` argument resolution có thể thất bại **trước khi listener method chạy**.
5. Tạm thời chuyển logic decode vào listener: số trách nhiệm tăng và unit test method JMS trở nên khó hơn dù output giống nhau.
6. Nâng listener concurrency lên nhiều consumers và thêm nhiều messages: cùng singleton service có thể được gọi đồng thời, nên state và DB transaction phải thread-safe.
7. Giữ nguyên listener nhưng thay `OrderApplicationService` thành fake trong unit test: có thể xác minh delegation mà không cần broker.

## 8. Vì sao không nên catch rồi log và return?

Một lỗi phổ biến:

~~~java
@JmsListener(destination = "orders.created")
public void onMessage(String json) {
    try {
        service.process(decoder.decode(json));
    } catch (Exception ex) {
        log.error("Order failed", ex);
        // Sai nếu cần rollback/redelivery nhưng method trả về bình thường.
    }
}
~~~

Đây là fragment phản ví dụ, `service`, `decoder`, `log` chưa được định nghĩa. Khi method trả về **bình thường**, listener container có thể coi lời gọi thành công, và với JMS local transacted session có thể **commit** việc nhận message. Message có thể biến mất khỏi Queue dù đơn hàng chưa xử lý.

**Cách đúng không phải “luôn throw mọi exception vô hạn”.** Cần phân loại lỗi:

- **Transient**: database không kết nối được, downstream tạm fail, lock timeout. Thường cho exception propagate để JMS transaction rollback và broker redeliver theo backoff/max delivery.
- **Permanent payload/contract error**: JSON sai, version không hỗ trợ, field bắt buộc thiếu. Không nên retry vô hạn cùng payload; dùng DLQ/quarantine và alert theo broker/application policy.
- **Đã xử lý trước đó (duplicate)**: consumer idempotent có thể coi là **thành công**, trả về bình thường và commit/ack message, **sau khi xác nhận** sự kiện đã được xử lý trước.
- **Business reject hợp lệ**: phải xác định outcome nghiệp vụ, có thể ghi trạng thái reject vào DB/outbox rồi ack có chủ đích; không “nuốt lỗi” ngẫu nhiên.

Nếu cần log:

~~~java
@JmsListener(destination = "orders.created")
public void onMessage(String json) {
    try {
        service.process(decoder.decode(json));
    } catch (RuntimeException ex) {
        log.warn("Order message failed", ex);
        throw ex; // Cho container xử lý theo transaction/error policy.
    }
}
~~~

Fragment trên **không phải khuyến nghị catch mọi nơi**; nếu service/logging infrastructure đã ghi đủ, bạn có thể không catch trong listener. Không log payload nhạy cảm và stack trace lặp vô hạn. Error classification nên ở nơi có đủ context để phân biệt transient/permanent và được kiểm thử.

## 9. Session transaction, acknowledgment và retry

**Listener ngắn không làm cho luồng xử lý tự nhiên đáng tin hơn** nếu JMS transaction sai.

Trong `DefaultMessageListenerContainer`, khi dùng `AUTO_ACKNOWLEDGE` không transaction, Spring có thể xác nhận message **trước khi listener business method chạy**, nên exception trong method không đảm bảo redelivery. Với workload cần độ tin cậy, Spring khuyến nghị **transacted session** hoặc cấu hình transaction manager phù hợp.

Spring Boot 3.5 có property:

~~~properties
spring.jms.listener.session.transacted=true
~~~

Ở ví dụ, điều này nghĩa là listener invocation chạy trong **JMS local transaction**: thành công thì container tiến hành commit nhận; lỗi propagate bình thường thì rollback, broker có thể giao lại theo policy. Đó là **transaction của JMS Session**, không phải transaction của database.

| Tình huống | Với JMS local transacted listener, về nguyên tắc |
| --- | --- |
| Decoder + service return thành công | Container có thể commit JMS receive. |
| Decoder/service ném exception ra khỏi listener | Container rollback JMS receive; message có thể redeliver. |
| Listener catch exception rồi return | Container có thể commit, dẫn tới mất lần xử lý business. |
| Business DB đã commit nhưng JMS commit thất bại | Message có thể redeliver; cần idempotent service. |
| Exception được bắt và xử lý như duplicate hợp lệ | Có thể return bình thường để ack/commit, nếu đã xác minh duplicate. |
| Process bị kill giữa handling | Không bảo đảm callback cleanup, broker có thể redeliver. |

**Không bảo đảm exactly-once business outcome** chỉ nhờ `sessionTransacted=true`. Chẳng hạn DB đã commit thành công rồi JMS session rollback do mất kết nối; cùng message sẽ tới lại. Kết quả phụ thuộc idempotency/transaction design của service.

### 9.1. Retry thuộc nhiều lớp

Phân biệt:

1. **Broker redelivery**: message được giao lại sau rollback/session failure; cấu hình delay, max attempts, DLQ ở broker.
2. **Application retry**: service retry một cuộc gọi tạm thất bại bên trong cùng lần receive; có backoff/time budget, không để kéo dài vô hạn JMS transaction.
3. **Producer retry**: producer có thể gửi lại một message mới, thường có `JMSMessageID` mới nhưng `eventId` nghiệp vụ cũ.
4. **Recovery của listener container**: kết nối lại broker, khác với retry domain operation.
5. **Replay từ DLQ**: thao tác vận hành có kiểm soát sau khi sửa decoder/logic.

Không trộn tất cả vào `for` loop trong listener. Đặc biệt không gọi `Thread.sleep(60_000)` trong listener để trì hoãn retry cho mỗi message; nó giữ consumer thread/session bận và làm giảm throughput. Broker redelivery delay/backoff thường phù hợp hơn để chờ giữa các lần delivery.

### 9.2. Dead-letter / quarantine

Khi message có schema sai hoặc lỗi không thể hồi phục, một số broker cho phép đưa vào DLQ sau số lần giao thất bại. Artemis có `dead-letter-address` và `max-delivery-attempts` trong address settings. Cần cài đặt **đích và ACL thực tế**, alert, retention và replay procedure.

Một Queue có message độc hại (poison message) không nên quay vòng rollback vô hạn gây kẹt backlog. Nhưng cũng không tự ack và bỏ nó khỏi hệ thống không có dấu vết. Giải pháp cần rõ: **quarantine/DLQ + reason code + observability + kiểm soát replay**.

## 10. @Async và fire-and-forget trong listener: bẫy lớn

Phản ví dụ:

~~~java
@JmsListener(destination = "orders.commands")
public void onMessage(String payload) {
    asyncOrderService.processAsync(payload); // Trả về ngay.
}
~~~

Nếu `processAsync` chạy qua `@Async` hoặc trả `CompletableFuture` chưa hoàn thành mà method listener đã return, **container có thể commit/ack JMS trước khi tác vụ thật xử lý xong**. Khi background task fail, broker có thể không còn message để retry tự nhiên.

**Không sửa bằng cách “thêm @Async” để listener nhanh hơn.** Listener method ngắn ≠ thời gian xử lý ngắn. Một listener chỉ gọi `service.process(...)` **đồng bộ** vẫn chiếm container thread cho tới khi service hoàn thành; đây là điều bình thường khi success/failure cần gắn với ack.

Nếu phải tách quá trình xử lý dài khỏi JMS transaction, cần một kiến trúc bảo đảm **handoff bền vững**:

- Transactional inbox: lưu event vào DB/idempotency store với trạng thái `PENDING` trước khi commit nhận, sau đó worker nền xử lý.
- Outbox/job queue bền vững: ghi job/side effect request atomically theo phạm vi DB transaction được thiết kế; có retry và dedup riêng.
- Một Queue thứ hai: chỉ coi chuyển giao thành công khi publish và ack có semantics phù hợp; không giả định hai broker sends là atomic nếu không cấu hình transaction.
- Duy trì `eventId` ổn định, visibility timeout/retry/monitoring ở tầng worker mới.

Để tính đúng đắn, phải chỉ ra **điểm nào durable**, **khi nào ack**, **ai retry** và **làm sao không xử lý hai lần**. Không chỉ thay synchronous call bằng một thread pool.

## 11. Idempotency thuộc application service

Với JMS/DB phổ biến, message **có thể được giao lại**. Một message `eventId=EV-188` có thể được nhận hai lần dù producer chỉ phát một lần, ví dụ DB commit thành công rồi JMS commit thất bại.

Một cấu trúc DB tối thiểu:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(128) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Lược đồ trên là **ví dụ SQL**, cú pháp timestamp/identity có thể thay đổi theo database. `event_id` cần unique constraint thực thi tại DB; một câu kiểm tra `existsById` trước khi insert **không đủ** chống race khi nhiều consumers đồng thời.

Application service có thể thực hiện **trong cùng DB transaction**:

~~~java
// Fragment minh họa ý tưởng, KHÔNG phải class độc lập.
// processedEventRepository và orderRepository là ports/repos ứng dụng.

@Transactional
public void process(OrderCreatedEvent event) {
    boolean firstTime = processedEventRepository.tryInsert(event.eventId());

    if (!firstTime) {
        return; // Duplicate đã xử lý: thành công theo chính sách.
    }

    orderRepository.applyOrderCreated(event.orderId(), event.amountMinor());
}
~~~

`tryInsert` là **API do ứng dụng tự định nghĩa**, cần dùng INSERT unique constraint hoặc chiến lược tương đương và xử lý đúng transaction. DB transaction rollback phải hủy cả record inbox và business update nếu có lỗi. Không dùng một `ConcurrentHashMap` memory-only làm idempotency production vì dữ liệu mất khi restart và không chia sẻ giữa replicas.

**Trật tự đúng:** xác nhận duplicate qua database/unique key; nếu chưa có thì cập nhật business trong transaction; khi service return thành công, JMS container mới có cơ sở ack/commit message. Trường hợp DB đã commit nhưng JMS commit fail, redelivery vào `tryInsert` sẽ nhận duplicate và return bình thường, tránh side effect lặp.

Nếu outcome business yêu cầu gọi payment/email ngoài DB, transaction SQL không bao trùm API đó; dùng outbox, provider idempotency keys và các pattern phù hợp.

## 12. Không kéo cả JMS API vào domain layer

Một cách thiết kế phụ thuộc transport:

~~~java
public void placeOrder(jakarta.jms.Message message)
        throws jakarta.jms.JMSException {
    String eventId = message.getStringProperty("eventId");
    // Business logic còn phụ thuộc JMS Session/header/property.
}
~~~

Điểm yếu: service khó gọi từ REST, batch hoặc unit test thuần; thay JMS provider/converter kéo theo sửa business code.

Thay vào đó, đưa thông tin cần thiết vào object ứng dụng:

~~~java
// Java 17 record, fragment khi cần context nghiệp vụ.
public record IncomingEventContext(
        String eventId,
        String correlationId,
        String tenantId) {
}
~~~

Ví dụ listener map thông tin transport:

~~~java
// Fragment: đã có decoder, service và các headers phù hợp.
OrderCreatedEvent event = decoder.decode(json, eventId, version);
IncomingEventContext ctx =
        new IncomingEventContext(eventId, correlationId, tenantId);

applicationService.process(event, ctx);
~~~

`IncomingEventContext` là hợp đồng **application-layer**, không phải JMS native message. Giới hạn các fields thực sự cần cho business/observability. Trường `tenantId` phải được kiểm chứng với danh tính/ACL; không truyền vào domain rồi tin mặc nhiên là an toàn.

Cũng tránh để application service phụ thuộc `JmsTemplate` chỉ để gửi email/HTTP response. Nếu use case cần phát domain event, định nghĩa `EventPublisher` port và implement adapter bằng JMS/outbox. Như vậy core logic có thể test mà không bật broker.

## 13. @Transactional ở service và ranh giới JMS–DB

Dùng `@Transactional` ở service là hữu ích khi xử lý DB, nhưng **không tự khiến DB và JMS là một distributed transaction**.

Ví dụ:

~~~java
@Service
public class OrderApplicationService {

    @Transactional
    public void apply(OrderCreatedEvent event) {
        // Ghi bảng orders và processed_events trong cùng DB transaction.
    }
}
~~~

Đây là fragment; cần import `@Transactional` và cấu hình `PlatformTransactionManager` của datasource, repository implementation. Nếu có nhiều transaction managers (JMS/DB), cần chọn đúng manager bằng qualifier hoặc policy thống nhất.

**Hai lớp transaction:**

- `spring.jms.listener.session.transacted=true`: JMS Session local receive/commit/rollback.
- `@Transactional` với DB transaction manager: database transaction độc lập.

Khi service DB commit và method listener return, JMS commit có thể xảy ra **sau**; crash ở giữa dẫn tới redelivery. Thiết kế idempotency/outbox xử lý tình huống này. Muốn nguyên tử trên nhiều resources có thể cần JTA/XA phù hợp, không chỉ annotation.

**Proxy trap:** Nếu service gọi method `@Transactional` của **chính nó** qua `this.process(...)`, Spring proxy-based transaction có thể bị bypass. Listener adapter gọi một Spring service bean được inject là cách giúp tách rõ proxy boundary.

**Không catch `DataAccessException` trong listener rồi return** nếu service chưa có một outcome thành công có chủ đích. Để exception propagate hoặc phân loại theo policy rõ để điều khiển rollback.

## 14. Error handling ở nhiều lớp

Không phải lỗi nào cũng xuất hiện bên trong listener body. Một pipeline:

~~~mermaid
flowchart TD
    Q[("Queue")] --> A["JMS receive / container"]
    A --> B["Message conversion + argument resolution"]
    B --> C["@JmsListener method"]
    C --> D["Decoder validation"]
    D --> E["Application service"]
    E --> F["DB / external ports"]
    B --> X["Conversion error"]
    D --> Y["Contract error"]
    F --> Z["Business / transient error"]
    X --> T["Container transaction / error policy"]
    Y --> T
    Z --> T
    T --> R["Commit / rollback / redelivery / DLQ"]
~~~

**Bốn vùng lỗi:**

1. **Trước listener**: `MessageConverter` không đọc được body, hoặc `@Header` bắt buộc không tồn tại. Method `onMessage` có thể **không chạy**, nên log trong method không bao quát các lỗi này.
2. **Decoder**: JSON invalid, schema version không hỗ trợ, header-body mismatch; classification permanent thường cần quarantine.
3. **Service**: DB unavailable, optimistic lock, thiếu nghiệp vụ, duplicate; có thể transient hoặc permanent tùy nguyên nhân.
4. **Sau service**: JMS commit/connection lỗi, dù business đã hoàn thành; cần idempotency khi redelivery.

Tùy cấu hình, Spring có `ErrorHandler` trên `DefaultMessageListenerContainer` để log/quan sát lỗi; đừng coi handler chỉ log là đã tự động ra quyết định đưa vào DLQ. Ranh giới rollback và acknowledgment vẫn do container/session/provider. Cần xem cause chain và tests trên broker thật.

Không triển khai một `catch (Throwable)` trong listener để “giữ ứng dụng sống”: nó có thể nuốt cả lỗi nghiêm trọng và làm message bị commit sai. Với lỗi permanente, chọn policy rõ: **reject/quarantine** hoặc broker redelivery-limit/DLQ, không im lặng.

## 15. Concurrency: listener ngắn vẫn cần service thread-safe

Một singleton `@Component` listener có thể bị nhiều JMS consumer threads gọi đồng thời khi tăng `spring.jms.listener.min-concurrency`/`max-concurrency` hoặc `@JmsListener(concurrency="...")`.

**Chú ý:** container concurrency lớn **không tạo service bean mới cho mỗi message**; nhiều thread cùng gọi singleton service/proxy.

Phản ví dụ:

~~~java
@Service
public class UnsafeOrderCounter {

    private int count;

    public void process(OrderCreatedEvent event) {
        count++; // Race condition khi nhiều messages xử lý đồng thời.
    }
}
~~~

Đây là code fragment phản ví dụ. Dùng thread-safe metrics counters cho thống kê, DB transaction với unique key cho dữ liệu nghiệp vụ, không cất `currentEventId`, `currentTenant` vào field mutable dùng chung.

Khi concurrency tăng:

- Ràng buộc DB connection pool/transaction latency phải phù hợp.
- Idempotency phải chống race giữa replicas và consumers.
- Không giả định FIFO business completion vì nhiều worker parallel và JMSPriority/redelivery.
- Trong Queue, một message thường giao cho một competing consumer tại một thời điểm, nhưng có thể **redeliver** sau lỗi.
- Trong Topic, mỗi subscription có semantics riêng; không suy ra giống Queue.
- MDC/ThreadLocal context phải được set/clear phù hợp, tránh rò trace/tenant ID giữa messages.

**Giữ method listener ngắn không làm thời gian xử lý ngắn.** Nếu service thực hiện một công việc 30 giây đồng bộ, JMS consumer thread vẫn bị chiếm 30 giây; cách giải quyết throughput là kiến trúc, concurrency, bulkhead và durable handoff, không đơn thuần “bớt dòng”.

## 16. Quan sát được hệ thống đang xử lý gì

Một thin listener vẫn cần observability, nhưng hãy quan sát **đúng lớp**:

| Lớp | Metrics/logs phù hợp |
| --- | --- |
| JMS broker/container | Queue depth, message age, consumer count, redelivery, DLQ, recovery/connection errors. |
| Listener adapter | Endpoint ID, `JMSMessageID`, correlation ID, schema version, decode success/failure (không log body nhạy cảm). |
| Decoder | Unsupported version, malformed JSON, invalid contract, header mismatch. |
| Application service | Use-case duration, idempotent duplicate count, business rejection, DB latency. |
| Outbound ports | HTTP errors, retry budgets, remote idempotency keys, timeout rates. |

Gắn `eventId` theo hợp đồng để nối log giữa producer–consumer–database; `JMSMessageID` là provider-generated ID của một lần gửi, không thay `eventId` cho retry/idempotency.

### 16.1. Không đưa dữ liệu nhạy cảm vào log

Tránh:

~~~java
log.info("Received entire message: {}", json);
~~~

Payload có thể chứa tên khách hàng, địa chỉ, tài khoản, access token. Thay bằng metadata đã được phép:

~~~java
log.info(
        "Processing eventId={} schemaVersion={}",
        eventId, schemaVersion);
~~~

Hai fragment trên giả định có `org.slf4j.Logger log`, `json` và metadata; không phải class tự chạy. Xác định masking, retention, trace context và audit policy trước khi đưa log vào production.

### 16.2. Listener success khác transaction committed

Ghi `"listener returned"` chưa đảm bảo JMS commit hoặc DB commit trong mọi failure mode. `CountDownLatch`/metric handler invoked chỉ xác nhận **đã đến bước đó**. Với integration test reliability, phải kiểm tra DB side effect, JMS redelivery/queue metrics và transaction boundaries riêng.

## 17. Kiểm thử theo từng tầng

### 17.1. Unit test decoder

Cho `OrderEventDecoder` với một `ObjectMapper`:

- JSON hợp lệ/version 1/eventId khớp → trả `OrderCreatedEvent` đúng.
- JSON sai syntax → ném `IllegalArgumentException` có cause Jackson.
- `schemaVersion=2` chưa hỗ trợ → từ chối trước business side effects.
- Header/body eventId lệch nhau → từ chối.
- `orderId` rỗng, `amountMinor=0` → từ chối.
- Giá trị boundary numeric, Unicode/escaped JSON, null vs missing theo contract.
- Nếu có schema evolution, kiểm tra unknown fields và version map có chủ đích.

Unit test decoder **không cần broker** và không nên giả lập transaction JMS.

### 17.2. Unit test listener adapter

Dùng fake `OrderEventDecoder`/`OrderApplicationService` hoặc Mockito:

1. Gọi trực tiếp `listener.onMessage(validJson, "EV-188", 1)`.
2. Assert decoder nhận đúng payload, eventId, schemaVersion.
3. Assert service được gọi **một lần** với event đã decode.
4. Cho decoder ném exception: verify service không được gọi.
5. Cho service ném exception: verify listener **không nuốt lỗi**.
6. Không kỳ vọng test này chứng minh JMS rollback, vì bạn chưa chạy container/broker.

Nếu mục đích chỉ kiểm tra việc method JMS có đúng annotation/queue/header mapping, hãy bổ sung integration test.

### 17.3. Unit test application service

Test với `OrderCreatedEvent` thuần:

- Quy tắc nghiệp vụ đúng (state transitions, invariants).
- DB transaction rollback khi repository lỗi.
- Duplicate eventId được xử lý idempotently.
- Tác vụ payment/email có idempotency key và timeout policy.
- Không phải start Artemis để unit test một rule tính tiền.

Một **service test không phụ thuộc JMS** là bằng chứng mạnh rằng bạn đã tách ranh giới; không phải toàn bộ code vẫn truy cập `JmsTemplate` qua helper ẩn.

### 17.4. Integration test với broker

Trên Queue test riêng, không có competing consumers:

1. Khởi động Spring context với Artemis embedded/test broker.
2. Gửi `TextMessage` có JSON body cùng JMS properties.
3. Dùng latch hoặc Awaitility có timeout để đợi service được gọi.
4. Kiểm tra body/headers được converter mapping đúng; version mismatch bị từ chối.
5. Với `session.transacted=true`, tạo service ném exception, quan sát redelivery đúng broker policy.
6. Kiểm tra broker DLQ/quarantine với bounded attempts; không tạo poison message thử nghiệm trên production.
7. Nếu có database, inject failure giữa DB commit và JMS commit theo cách kiểm soát, chứng minh idempotency.
8. Tăng concurrency và kiểm tra duplicate race, transaction isolation, session-thread usage.
9. Kiểm tra shutdown trong lúc in-flight; không giả định `@PreDestroy` luôn chạy nếu process bị kill.
10. Kiểm tra dữ liệu nhạy cảm không lộ trong headers/logs/DLQ.

### 17.5. Ma trận test lỗi

| Input/điều kiện | Listener gọi service? | Kết quả kỳ vọng |
| --- | --- | --- |
| JSON hợp lệ, version 1, eventId khớp | Có | Service xử lý. |
| JSON invalid | Không | Decoder ném, transaction/error policy xử lý. |
| schemaVersion không hỗ trợ | Không | Contract error, quarantine/DLQ policy. |
| eventId thiếu trong JMS property | Không chắc method được gọi | Argument resolution error trước method; theo dõi container logs. |
| DB timeout | Có rồi thất bại | Exception propagate; rollback/retry policy. |
| Duplicate event đã commit | Có thể | Service nhận diện duplicate và return thành công. |
| Service trả `CompletableFuture` chưa xong nhưng listener return | Listener kết thúc sớm | **Nguy cơ ack quá sớm**; không dùng fire-and-forget thiếu durable handoff. |
| Broker disconnect khi commit | Service có thể đã chạy | Redelivery có thể xảy ra; cần idempotency. |

## 18. Refactor dần một listener đang quá lớn

Không cần rewrite toàn bộ ngay trong một lần:

1. **Khoanh vùng**: liệt kê mọi trách nhiệm của method (decode, validate, SQL, HTTP, publish, logging, retry).
2. **Khóa hành vi bằng tests**: golden payload và các case success/failure, ack/redelivery.
3. **Trích decoder**: move JSON/schema/header parsing sang component thuần; verify không đổi contract.
4. **Trích application service**: đặt use case và transaction vào service được Spring inject; tránh self-invocation proxy trap.
5. **Định nghĩa ports** cho repository/outbound API; test business không cần broker.
6. **Xóa catch-and-swallow** sau khi xác nhận JMS transaction/error policy; test poison message riêng.
7. **Thêm idempotency** với event ID và unique constraint/outbox nếu cần.
8. **Đo latency và concurrency**; tránh “listener trông ngắn” nhưng side effects chạy lâu không kiểm soát.
9. **Giữ adapter mỏng và rõ**: nhận payload/headers, decode, delegate, không làm thêm side effects.
10. **Rollout có giám sát**: DLQ, redelivery, backlog, success/error rate và khả năng rollback phiên bản code.

Trước–sau:

~~~text
TRƯỚC
  @JmsListener
    -> parse JSON
    -> validate
    -> SQL + domain logic
    -> HTTP payment + email
    -> send JMS audit
    -> catch all + log + return

SAU
  @JmsListener / inbound adapter
    -> decoder.decode(payload, headers)
    -> applicationService.process(event)
         -> domain policy
         -> repository / transaction / idempotency
         -> durable outbox / integration ports
  container + broker
    -> receive / session transaction / redelivery / DLQ
~~~

Phần “SAU” không biến DB + JMS thành một transaction thống nhất tự động. Nó **làm rõ nơi đặt transaction, idempotency và outbox để có thể kiểm thử**.

## 19. Những lỗi phổ biến khi áp dụng thin listener

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Listener chỉ một dòng nhưng service nhận raw `jakarta.jms.Message` | Đã chuyển coupling vào service. | Map payload/metadata thành DTO application-level. |
| Bắt `Exception` rồi log và return | Có thể commit message chưa xử lý. | Propagate hoặc phân loại outcome có chủ đích. |
| Đưa `@Async` vào service rồi return ngay | JMS ack có thể xảy ra trước business completion. | Synchronous handling hoặc durable inbox/handoff. |
| Dùng Java mutable singleton fields cho `currentEventId` | Race giữa listener threads. | Biến local/immutable DTO, storage transaction. |
| Trả lỗi cho mọi duplicate | Redelivery lặp vô hạn dù side effect đã xong. | Idempotency key/unique constraint và xử lý duplicate là success. |
| Gọi `message.acknowledge()` tùy ý trong container transacted | Sai ownership/transaction semantics. | Để container quản lý theo factory/session. |
| Tin `schemaVersion` header là dữ liệu đã được validate | Header và body có thể mâu thuẫn. | Decoder validate header + payload. |
| Dùng `@Payload OrderCreatedEvent` không có JSON converter | Default converter không tự tạo mọi domain record. | Cài converter hoặc nhận String + decoder. |
| `@Header` missing gây lỗi mà không log trong method | Lỗi ở argument resolution, method chưa được gọi. | Monitor container-level errors. |
| DB `@Transactional` được coi là JMS XA | Hai local transactions vẫn độc lập. | Idempotency/outbox hoặc XA thật khi phù hợp. |
| Tăng concurrency để chữa latency HTTP vô hạn | Có thể làm cạn DB/HTTP connections và tăng duplicate/race. | Timeout, bulkhead, backpressure, worker design. |
| Cắt listener quá mức thành hàng chục wrapper rỗng | Làm luồng xử lý khó theo dõi. | Tách theo trách nhiệm thực, giữ hợp đồng rõ. |
| Log full payload có PII/secret | Dữ liệu nhạy cảm lộ vào logs và DLQ. | Structured metadata logs, redaction, ACL. |

## 20. Câu hỏi tự luyện

1. **Vai trò chính của `@JmsListener`?** Nhận payload/metadata từ adapter và ủy quyền xử lý.
2. **Business service có cần biết Queue name không?** Không, nếu ranh giới đã tách đúng.
3. **Hai lệnh trong listener mẫu là gì?** `decoder.decode(...)` rồi `service.process(...)`.
4. **Vì sao không catch rồi return sau lỗi DB?** Container có thể coi xử lý thành công và commit JMS receive.
5. **Có nên dùng `@Async` fire-and-forget để listener “nhanh” không?** Không nếu thiếu durable handoff vì acknowledgment có thể diễn ra quá sớm.
6. **`spring.jms.listener.session.transacted=true` bảo đảm cả DB + JMS cùng commit nguyên tử?** Không; chỉ local JMS Session nếu không có transaction coordination khác.
7. **Vì sao cần `eventId` ngoài `JMSMessageID`?** Idempotency và retry cùng sự kiện có thể dùng JMS ID khác.
8. **Cần làm gì khi JSON sai syntax?** Từ chối trước business side effects, phân loại permanent error, giới hạn retries và quarantine/DLQ.
9. **Vì sao decoder nên kiểm tra header/body eventId?** Ngăn metadata–payload mismatch khiến xử lý/tracing sai.
10. **Default `SimpleMessageConverter` có tự đổi mọi JSON String thành record domain?** Không; cần cấu hình converter hoặc decoder.
11. **Trường hợp missing `@Header` lỗi ở đâu?** Có thể ở argument resolution trước method listener.
12. **Một singleton service có thể được nhiều listener threads gọi cùng lúc?** Có; phải thread-safe.
13. **Service xử lý xong rồi JMS commit fail thì sao?** Message có thể redeliver; dùng idempotency.
14. **Đã có `@Transactional` DB thì listener nên catch lỗi và tự ack?** Không; phải giữ đúng transaction boundary và error policy.
15. **Khi nào gọi duplicate event là thành công?** Khi idempotency store xác nhận tác động đã được commit theo contract.
16. **`@PostConstruct` của listener có chạy từng message không?** Không, nó thuộc bean initialization.
17. **Kiểm thử listener có nhất thiết phải khởi động broker?** Unit test delegation không; integration test mapping/retry cần broker.
18. **Mục tiêu cuối cùng của thin listener?** Cô lập transport, dễ kiểm thử use case, và xử lý lỗi/transaction có thể dự đoán.

## 21. Tài liệu chính thức

- [Spring Framework 6.2 — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html): method signatures `@Payload`/`@Header`, `@EnableJms`, listener factory và registry.
- [Spring Framework 6.2 — Using Spring JMS](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html): message-driven POJOs, listener container, local JMS transactions và redelivery.
- [Spring Framework 6.2 — DefaultMessageListenerContainer](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html): acknowledgment, recovery, threading, transaction manager.
- [Spring Framework 6.2 — @JmsListener](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/annotation/JmsListener.html): `destination`, `containerFactory`, `concurrency`, listener ID.
- [Spring Boot 3.5 — JMS/Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): Artemis embedded và `JmsTemplate` auto-configuration.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): `spring.jms.listener.session.transacted`, listener concurrency và embedded Queue.
- [Spring Boot 3.5 — Disable Transacted JMS Session](https://docs.spring.io/spring-boot/3.5/how-to/messaging.html): lưu ý transaction default và custom listener factory.
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): message headers/properties, acknowledgment, transaction và redelivery.
- [Apache ActiveMQ Artemis — Undelivered Messages](https://artemis.apache.org/components/artemis/documentation/latest/undelivered-messages.html): delivery attempts, redelivery delay và dead-letter handling.

**Ghi nhớ:** listener lý tưởng là một **inbound adapter rõ trách nhiệm**: nhận message, chuyển thành input hợp lệ, ủy quyền application service và để exception/transaction policy xử lý kết quả. “Ngắn” không phải mục tiêu hình thức: mục tiêu thực là **tách biệt transport và business, test được từng lớp, không ack quá sớm, không mất lỗi, an toàn khi retry và concurrency**.
