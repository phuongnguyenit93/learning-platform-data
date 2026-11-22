# JmsTemplate và JmsMessagingTemplate trong tầng gửi nhận

> **Chương:** Spring JMS  
> **Phạm vi:** Ứng dụng Java/Spring Boot gửi và nhận thông điệp qua ActiveMQ Classic hoặc Apache Artemis bằng **Jakarta Messaging** (`jakarta.jms`). Bài tập trung vào hai abstraction `JmsTemplate` và `JmsMessagingTemplate`: API gửi/nhận, chuyển đổi payload/header, cấu hình provider, quản lý resource và ranh giới transaction. Ví dụ dùng **Spring Boot 3.5.x / Spring Framework 6.2.x / Java 17**; Spring Framework 7 vẫn có hai template và bổ sung `JmsClient` dạng fluent.

## 1. Hai mức trừu tượng trên cùng JMS provider

`JmsTemplate` và `JmsMessagingTemplate` không phải hai wire protocol. Cả hai dùng `jakarta.jms.ConnectionFactory` và client của broker tương ứng; chúng khác nhau ở **đối tượng mà tầng nghiệp vụ thao tác**.

```text
                       Business service / adapter
                                  │
                  ┌───────────────┴────────────────┐
                  ▼                                ▼
            JmsTemplate                     JmsMessagingTemplate
          jakarta.jms.Message              Spring Message<T>
           MessageCreator                  payload + headers
                  │                                │
                  │                      (ủy quyền cho JmsTemplate)
                  └───────────────┬────────────────┘
                                  ▼
                    jakarta.jms.ConnectionFactory
                                  │
                  Classic client      Artemis client
                    (OpenWire)             (Core)
                                  │
                             Queue / Topic
```

| Tiêu chí | `JmsTemplate` | `JmsMessagingTemplate` |
|---|---|---|
| Package | `org.springframework.jms.core.JmsTemplate` | `org.springframework.jms.core.JmsMessagingTemplate` |
| Mô hình | JMS `Message`, `Session`, `MessageCreator` | Spring `org.springframework.messaging.Message<T>` |
| Gửi đơn giản | `convertAndSend("queue", payload)` | `convertAndSend("queue", payload)` |
| Gửi có metadata | `send(..., MessageCreator)` hoặc `MessagePostProcessor` | `send("queue", MessageBuilder.withPayload(...).build())` |
| Nhận đồng bộ | `receive` / `receiveAndConvert` | `receive` / `receiveAndConvert("queue", Target.class)` |
| Chuyển đổi | JMS `MessageConverter` | Spring Messaging converter + JMS message converter |
| Runtime exception | Họ `org.springframework.jms.JmsException` | Họ `org.springframework.messaging.MessagingException` |
| Phù hợp | Cần làm việc sát JMS header/property và callback Session | Service muốn envelope `Message<?>` nhất quán với Spring Messaging |

**Cả hai đều quản lý việc tạo/đóng tài nguyên JMS cần cho một thao tác**. Chúng không tự triển khai consumer chạy nền, tự tạo queue bắt buộc trên broker hay bảo đảm gửi message cùng DB transaction.

### Không dùng hai template một cách máy móc

`JmsMessagingTemplate` xây trên `JmsTemplate`. Nó thêm lớp Spring Messaging với payload và headers, nhưng khi cần tác động tới `jakarta.jms.Session`, `BytesMessage`, JMS correlation ID hoặc message selector thì `JmsTemplate` thường rõ ràng hơn. Chọn **một abstraction chính cho một luồng nghiệp vụ**, cấu hình `ConnectionFactory` ở một nơi.

## 2. Kết nối ActiveMQ Classic hoặc Artemis với Spring Boot

Spring Boot tự cấu hình `ConnectionFactory` và các template khi starter hợp lệ hiện diện. Hai template có thể inject thành bean dùng chung; đừng `new Connection` hoặc `new JmsTemplate` trong mỗi lần gửi.

### 2.1. Chọn một starter, không trộn provider

**ActiveMQ Classic 6.x**:

```xml
<!-- Spring Boot dependency management quản lý version. -->
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-activemq</artifactId>
</dependency>
```

**Apache Artemis 2.x** (phương án thay thế):

```xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-artemis</artifactId>
</dependency>
```

Classic client mặc định nói **OpenWire**; Artemis client mặc định nói **Core**. Hai client có thể cùng dùng `jakarta.jms` nhưng không vì thế mà đổi broker chỉ bằng cách thay URI khi listener không hỗ trợ protocol. Với Spring Boot 3.x cần client Jakarta, không ghép nhầm dependency `javax.jms` cũ của Classic 5.x.

### 2.2. `application.yml` của ứng dụng Classic

```yaml
spring:
  activemq:
    broker-url: ${JMS_BROKER_URL:tcp://127.0.0.1:61616}
    user: ${JMS_BROKER_USER}
    password: ${JMS_BROKER_PASSWORD}
  jms:
    pub-sub-domain: false
    cache:
      session-cache-size: 5
    template:
      receive-timeout: 2s
```

`spring.activemq.broker-url` trỏ broker riêng; tránh vô tình dùng Classic embedded broker khi `activemq-broker` được thêm vào classpath. `pub-sub-domain: false` chọn **queue** làm default destination type khi resolve tên. Trong production, secrets lấy từ cơ chế quản lý bí mật của deployment, không ghi password vào Git.

### 2.3. `application.yml` của ứng dụng Artemis

```yaml
spring:
  artemis:
    mode: native
    broker-url: ${JMS_BROKER_URL:tcp://127.0.0.1:61616}
    user: ${JMS_BROKER_USER}
    password: ${JMS_BROKER_PASSWORD}
  jms:
    pub-sub-domain: false
    cache:
      session-cache-size: 5
    template:
      receive-timeout: 2s
```

`mode: native` kết nối broker đang chạy riêng bằng TCP. Queue/address thật phải đã tồn tại, hoặc broker được bật auto-create phù hợp và user đủ quyền; một tên queue Java không thay quy trình provisioning production.

**Vòng đời:** Spring Boot thường bọc native factory bằng `CachingConnectionFactory`, giúp tái sử dụng Connection/Session/Producer theo giới hạn cấu hình. Tối ưu cache hoặc pool cần đo tải thật; không tự tạo ConnectionFactory cho mỗi HTTP request.

### 2.4. Nếu tự cấu hình Spring Framework không qua Boot

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsMessagingTemplate;
import org.springframework.jms.core.JmsTemplate;

@Configuration(proxyBeanMethods = false)
public class TemplateConfig {
    @Bean
    JmsTemplate appJmsTemplate(ConnectionFactory cf) {
        JmsTemplate template = new JmsTemplate(cf);
        template.setReceiveTimeout(2_000L);
        return template;
    }

    @Bean
    JmsMessagingTemplate appMessagingTemplate(JmsTemplate appJmsTemplate) {
        return new JmsMessagingTemplate(appJmsTemplate);
    }
}
```

Đây là **phương án tự tạo bean**, chỉ dùng khi không để Boot tự tạo hai bean, hoặc chủ động thay thế đúng bean. Constructor `JmsMessagingTemplate(JmsTemplate)` reuse cấu hình template cơ sở. Tránh tạo nhiều template cùng kiểu mà không dùng qualifier rồi gặp `NoUniqueBeanDefinitionException`.

## 3. `JmsTemplate`: gửi chuỗi, JMS header và nhận đồng bộ

### 3.1. Dùng `convertAndSend` và `MessagePostProcessor`

```java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@Component
public final class OrderTextGateway {
    private static final String QUEUE = "lab.spring.orders.raw";
    private final JmsTemplate jms;

    public OrderTextGateway(JmsTemplate jms) {
        this.jms = jms;
    }

    public void publish(String eventId, String payload) {
        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("eventId is required");
        }
        jms.convertAndSend(QUEUE, payload, message -> {
            message.setStringProperty("eventId", eventId);
            message.setJMSCorrelationID(eventId);
            return message;
        });
    }

    public String pollOnce() {
        Object received = jms.receiveAndConvert(QUEUE);
        if (received == null) {
            return null; // Hết receiveTimeout mà không có message.
        }
        if (received instanceof String text) {
            return text;
        }
        throw new IllegalStateException(
            "Expected TextMessage, got " + received.getClass().getName());
    }
}
```

`convertAndSend` chuyển `String` thành JMS `TextMessage` bằng converter mặc định. `MessagePostProcessor` chạy **sau conversion nhưng trước send**, thích hợp đặt JMS property/header. `JMSCorrelationID` là **header chuẩn**; `eventId` là **application property**. Để hai giá trị bằng nhau là một quy ước của ứng dụng, không phải ràng buộc JMS.

**Converter mặc định `SimpleMessageConverter`** xử lý `String` ↔ `TextMessage`, `byte[]` ↔ `BytesMessage`, và `Map` ↔ `MapMessage`. Không giả định `convertAndSend(new OrderDto(...))` tự tạo JSON portable giữa mọi Java/broker.

### 3.2. Khi cần callback `MessageCreator`

```java
public void publishBinary(JmsTemplate jms, String eventId, byte[] bytes) {
    jms.send("lab.spring.binary", session -> {
        jakarta.jms.BytesMessage message = session.createBytesMessage();
        message.writeBytes(bytes);
        message.setStringProperty("eventId", eventId);
        return message;
    });
}
```

`MessageCreator` được Spring gọi với `Session` hợp lệ cho **thao tác hiện tại**. Không giữ `session` hoặc `MessageProducer` từ callback để dùng về sau; không gọi `close()` hoặc `commit()` trong callback vì chúng thuộc quyền quản lý của template/transaction manager.

### 3.3. Các kiểu nhận đồng bộ

| Phương thức | Kết quả | Khi dùng |
|---|---|---|
| `jms.receive("queue")` | `jakarta.jms.Message` hoặc `null` | Cần đọc JMS headers/properties và loại message |
| `jms.receiveAndConvert("queue")` | Payload Java hoặc `null` | Chỉ cần body |
| `jms.receiveSelected("queue", "eventId = 'abc'")` | JMS message phù hợp selector | Chỉ quan tâm một ID (phải tạo selector hợp lệ) |
| `jms.receiveSelectedAndConvert(...)` | Payload đã convert | Cần selector + body |

Sử dụng `receive()` trong đường HTTP request có thể làm thread block; `JmsTemplate` mặc định có **indefinite receive** nếu không đặt timeout. `spring.jms.template.receive-timeout: 2s` khiến polling rỗng trả `null` sau thời gian giới hạn, **không phải** lỗi broker. Nhận đồng bộ theo `AUTO_ACKNOWLEDGE` không tự bao trùm database write xảy ra sau `receive`; xem mục transaction.

## 4. `JmsMessagingTemplate`: Spring `Message<T>` với payload và headers

`org.springframework.messaging.Message<T>` gói **payload** và **headers** như một envelope. `JmsMessagingTemplate` chuyển đổi envelope sang JMS rồi ủy quyền thao tác gửi/nhận cho `JmsTemplate`.

### 4.1. Gửi envelope và nhận lại header

```java
import java.util.Map;
import org.springframework.jms.core.JmsMessagingTemplate;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

@Component
public final class OrderEnvelopeGateway {
    private static final String QUEUE = "lab.spring.orders.envelope";
    private final JmsMessagingTemplate messaging;

    public OrderEnvelopeGateway(JmsMessagingTemplate messaging) {
        this.messaging = messaging;
    }

    public void publish(String eventId, String payload) {
        Message<String> envelope = MessageBuilder.withPayload(payload)
            .setHeader("eventId", eventId)
            .setHeader("schemaVersion", "1")
            .build();
        messaging.send(QUEUE, envelope);
    }

    public void publishConverted(String eventId, String payload) {
        messaging.convertAndSend(
            QUEUE, payload, Map.of("eventId", eventId, "schemaVersion", "1"));
    }

    public Message<?> pollEnvelope() {
        return messaging.receive(QUEUE); // null nếu không có message.
    }

    public String pollBody() {
        // Đây là LẦN receive khác, tiêu thụ message khác.
        return messaging.receiveAndConvert(QUEUE, String.class);
    }
}
```

Ví dụ đọc envelope:

```java
Message<?> msg = gateway.pollEnvelope();
if (msg != null) {
    String eventId = (String) msg.getHeaders().get("eventId");
    Object payload = msg.getPayload();
    System.out.println("eventId=" + eventId +
        " payloadType=" + payload.getClass().getSimpleName());
}
```

`pollEnvelope` và `pollBody` là **hai lựa chọn**, không phải hai phép đọc cùng một message. Mỗi lần gọi có thể consume một message riêng. Header tùy chọn như `eventId` và `schemaVersion` kiểu String thường được map thành JMS properties. Không giả định header object/UUID hoặc tên chứa ký tự đặc biệt đều được vận chuyển nguyên vẹn; tên và kiểu JMS properties có ràng buộc riêng.

### 4.2. Hai interface `MessageConverter` khác nhau

```text
Spring Message<String>
  ├── payload = "ORDER_CREATED"
  └── headers = {eventId: "o-123", schemaVersion: "1"}
                       │
                       ▼
            MessagingMessageConverter
             ├── payload converter ─▶ JMS TextMessage
             └── header mapper      ─▶ JMS headers/properties
                       │
                       ▼
                   JMS provider
```

| Nơi cấu hình | Interface | Việc thực hiện |
|---|---|---|
| `JmsTemplate.setMessageConverter` | `org.springframework.jms.support.converter.MessageConverter` | `Object ⇄ jakarta.jms.Message` |
| `JmsMessagingTemplate.setMessageConverter` | `org.springframework.messaging.converter.MessageConverter` | Payload Java ⇄ Spring Messaging representation |
| `JmsMessagingTemplate.setJmsMessageConverter` | `org.springframework.jms.support.converter.MessageConverter` | Spring `Message<?>` ⇄ JMS `Message`, mặc định dùng `MessagingMessageConverter` |
| `MessagingMessageConverter` | `org.springframework.jms.support.converter` | Kết hợp chuyển payload và map headers |

**Tên interface giống nhau, package khác nhau.** Dùng String đơn giản thì converter mặc định đủ. Với DTO JSON phải thống nhất schema, version/type ID và xác định rõ converter được dùng ở **cả đường gửi lẫn nhận**; không suy rằng hai template cấu hình converter giống nhau trong mọi trường hợp tùy biến.

Ví dụ **JMS JSON converter trên Spring Framework 6.2** (tùy chọn, có Jackson tương thích):

```java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageConverter;
import org.springframework.jms.support.converter.MessageType;

@Configuration(proxyBeanMethods = false)
class JmsJsonConfig {
    @Bean
    MessageConverter jmsMessageConverter() {
        MappingJackson2MessageConverter converter =
            new MappingJackson2MessageConverter();
        converter.setTargetType(MessageType.TEXT);
        converter.setTypeIdPropertyName("_type");
        converter.setTypeIdMappings(
            Map.of("OrderCreatedV1", OrderCreatedV1.class));
        return converter;
    }
}
```

`OrderCreatedV1` là DTO **do dự án định nghĩa**, không phải class Spring có sẵn. Spring Boot 3.5 có thể gắn bean converter JMS vào `JmsTemplate` được auto-configure. Khi tự tạo `JmsMessagingTemplate` hoặc custom converter, **phải xác nhận** đường chuyển đổi envelope cũng sử dụng type mapping thích hợp. Với Spring Framework 7 kiểm tra API converter/Jackson tương ứng; ví dụ trên có mục tiêu tương thích 6.2. Tránh `ObjectMessage` cho hợp đồng liên ngôn ngữ và đừng bật trust-all deserialization để chữa lỗi classpath.

## 5. Các núm cấu hình ảnh hưởng trực tiếp tới gửi/nhận

| Thuộc tính | Chức năng | Điểm cần tránh |
|---|---|---|
| `spring.jms.template.receive-timeout: 2s` | Timeout **đợi khi nhận đồng bộ** | Không dùng thay send timeout |
| `spring.jms.template.default-destination` | Destination khi gọi method không truyền tên | Không đặt một default mơ hồ cho mọi service |
| `spring.jms.template.time-to-live: 30s` | TTL gửi message mới | Không phải timeout kết nối hoặc gửi |
| `spring.jms.template.delivery-mode: persistent` | Delivery mode khi send | Phải có broker/queue durable để đạt độ bền mong muốn |
| `spring.jms.template.qos-enabled: true` | Dùng giá trị QoS do template chỉ định | Có thể thay default của provider |
| `spring.jms.template.session.transacted` | Session transacted cho thao tác độc lập | Hai thao tác gọi tách rời **không** tự có cùng local transaction |
| `spring.jms.cache.session-cache-size` | Tái sử dụng session theo loại session | Không tự chia sẻ Session đồng thời giữa các thread |
| `spring.jms.pub-sub-domain` | Default queue/topic cho destination resolver | Không nhầm queue thành topic |

Ví dụ đặt QoS cố định cho **một loại message**:

```yaml
spring:
  jms:
    template:
      receive-timeout: 2s
      qos-enabled: true
      delivery-mode: persistent
      time-to-live: 30s
```

TTL này áp dụng cho các lần gửi qua template, **không** phù hợp nếu deadline thay đổi cho từng message. Không `setTimeToLive(...)` lên singleton `JmsTemplate` trong từng HTTP request vì cấu hình chung có thể bị thread khác thay đổi. Dùng dedicated template hoặc cơ chế gửi QoS theo từng call.

### Request/reply có timeout

Hai template đều hỗ trợ send-and-receive; bản Spring Messaging có thể chuyển reply về kiểu đích:

```java
String response = messaging.convertSendAndReceive(
    "lab.spring.requests", "PING", String.class);
if (response == null) {
    throw new IllegalStateException("Reply not received before timeout");
}
```

Cần **responder thực sự** và quyền tạo temporary destination; nếu không sẽ chờ đến `receiveTimeout` hoặc lỗi. Request/reply là thao tác đồng bộ có thể giữ thread lâu, không nên lạm dụng để biến pipeline bất đồng bộ thành chuỗi RPC nhiều hop.

## 6. Resource lifecycle, conversion error và giới hạn của template

- Template là **Spring bean dùng chung**, an toàn khi cấu hình xong rồi inject cho nhiều component. Không giữ JMS `Session`/`MessageProducer` lấy từ callback để dùng sau.
- `JmsMessagingTemplate` dùng cùng nền `JmsTemplate`/`ConnectionFactory`. Không tạo factory mới trên mỗi message chỉ để khởi tạo template.
- Các API thường chuyển lỗi checked của JMS thành **runtime exception Spring**; phân loại lỗi broker/protocol, conversion, authorization và timeout tại biên service. Gửi timeout có thể là **IN_DOUBT**, không tự retry tạo ID mới.
- `receiveAndConvert` thích hợp cho polling có điều kiện; với consumer chạy lâu, dùng `@JmsListener` và listener container để quản lý threads, rollback/recovery và shutdown.
- Một message đã nhận trong `AUTO_ACKNOWLEDGE` không tự rollback khi bước DB/REST tiếp theo thất bại; muốn atomic JMS receive/send cần transaction như mục 7.

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không inject được `JmsTemplate` | Thiếu starter/provider, auto-config không chạy | Kiểm tra dependency tree và `ConnectionFactory` bean |
| Không kết nối được broker | Classic OpenWire và Artemis Core client/acceptor lệch | Đối chiếu provider và protocol listener |
| `receiveAndConvert` luôn `null` | Queue rỗng, timeout hoặc consumer khác lấy message | Đọc broker queue metrics và đích đang dùng |
| `receive` treo vô thời hạn | Chưa đặt receive timeout | Đặt `spring.jms.template.receive-timeout` |
| Converter ném exception hoặc trả sai kiểu | Default converter, schema, type ID không khớp | Inspect JMS body và cấu hình từng converter |
| Một số Spring headers không có ở JMS | Kiểu header không phù hợp, mapper bỏ qua | Dùng String/primitive headers và kiểm tra actual properties |
| TTL/priority không có hiệu lực | QoS config chưa bật hoặc bị override | Đọc `qos-enabled`, QoS do provider dùng |
| Gửi lại gây trùng | Hiểu nhầm mọi send exception đều chưa gửi | Giữ `eventId` ổn định, có idempotency |

## 7. Nhận–xử lý–gửi tiếp: giao dịch mà hai template không tự tạo

Hai thao tác `jms.receiveAndConvert("input")` rồi `jms.convertAndSend("output", result)` **không mặc nhiên nguyên tử**. Nếu ứng dụng chết giữa chúng, input có thể đã được acknowledge mà chưa có output.

Để gộp các thao tác JMS trong **một local transaction**, dùng Spring `JmsTransactionManager` với cùng `ConnectionFactory`:

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.connection.JmsTransactionManager;

@Configuration(proxyBeanMethods = false)
class LocalJmsTxConfig {
    @Bean("jmsTransactionManager")
    JmsTransactionManager jmsTransactionManager(ConnectionFactory cf) {
        return new JmsTransactionManager(cf);
    }
}
```

```java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderRelay {
    private final JmsTemplate jms;

    public OrderRelay(JmsTemplate jms) {
        this.jms = jms;
    }

    @Transactional("jmsTransactionManager")
    public boolean moveOne() {
        Object body = jms.receiveAndConvert("lab.spring.orders.input");
        if (body == null) {
            return false;
        }
        jms.convertAndSend("lab.spring.orders.output", body);
        return true;
    }
}
```

Để transaction áp dụng, lời gọi `moveOne()` phải **qua Spring proxy**, manager phải thực sự được sử dụng, và các thao tác dùng **cùng ConnectionFactory** với manager để `JmsTemplate` lấy Session ràng buộc theo thread. Manager commit cả input và output khi method thành công, rollback nếu exception phù hợp rollback rules. **Chỉ đặt `spring.jms.template.session.transacted=true` rồi gọi hai method ngoài một Spring transaction không bảo đảm chúng dùng cùng Session**.

Không suy rằng `@Transactional` mặc định sẽ đúng khi còn có `DataSourceTransactionManager`. Chỉ rõ tên `jmsTransactionManager` như trên; local JMS transaction **không bao phủ database**. Nếu muốn DB + JMS nhất quán, dùng transactional outbox/idempotent consumer hoặc XA/JTA được cấu hình thực sự. Khi commit mất phản hồi, tình trạng transaction vẫn có thể **không xác định**, dù có Spring.

## 8. Kiểm chứng hai template trên broker lab

### 8.1. Chuẩn bị

- Khởi động **một broker Classic hoặc Artemis** dành cho lab; chọn **một** starter và cấu hình URI/protocol đúng.
- Provision queue `lab.spring.orders.raw` và `lab.spring.orders.envelope`. Với Artemis, xác nhận address/queue tồn tại hoặc auto-create được phép; user có quyền send/consume.
- Tắt các `@JmsListener`/consumer khác trên hai queue trong lúc test để không tranh chấp message.
- Đặt `receive-timeout: 2s`; không chạy thử bằng queue có dữ liệu nghiệp vụ thật.

### 8.2. Integration test đơn giản

Thêm `spring-boot-starter-test` theo Spring Boot BOM; trong ứng dụng Spring Boot chứa hai gateway ở trên:

```java
import static org.assertj.core.api.Assertions.assertThat;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.messaging.Message;

@SpringBootTest
class SpringJmsGatewayIT {
    @Autowired OrderTextGateway raw;
    @Autowired OrderEnvelopeGateway envelope;

    @Test
    void jmsTemplateRoundTrip() {
        String eventId = "raw-" + UUID.randomUUID();
        raw.publish(eventId, "ORDER_A");
        assertThat(raw.pollOnce()).isEqualTo("ORDER_A");
    }

    @Test
    void messagingTemplateRoundTrip() {
        String eventId = "env-" + UUID.randomUUID();
        envelope.publish(eventId, "ORDER_B");
        Message<?> received = envelope.pollEnvelope();
        assertThat(received).isNotNull();
        assertThat(received.getPayload()).isEqualTo("ORDER_B");
        assertThat(received.getHeaders().get("eventId")).isEqualTo(eventId);
    }
}
```

**Giới hạn của test:** `@SpringBootTest` chỉ khởi tạo Spring context, **không bảo đảm broker ngoài đang chạy**. Cần test infrastructure khởi động broker và chờ ready; dùng queue lab rỗng/queue riêng theo mỗi run để tránh nhận nhầm message. Không tự purge queue có thể chứa message của người khác. Bài chỉ là code mẫu, chưa chạy thực tế trong bước soạn Markdown.

### 8.3. Ma trận thử nghiệm cần có

| Phép thử | Thao tác | Kết quả kỳ vọng |
|---|---|---|
| Payload đơn giản | `JmsTemplate.convertAndSend` String | Nhận đúng `TextMessage`/String |
| Spring envelope | `JmsMessagingTemplate.send` kèm header | Nhận đúng payload và `eventId` |
| Queue rỗng | Gọi `receiveAndConvert` | Trả `null` sau khoảng 2 giây |
| Sai provider | Classic client nối Core-only acceptor | Lỗi handshake/connection |
| Converter không khớp | Gửi DTO chưa cấu hình serializer | Exception/chuyển kiểu sai, phải sửa converter |
| Send bị mất kết nối | Cắt mạng lúc publish | Exception nhưng có thể **IN_DOUBT**, không khẳng định message chưa tồn tại |
| JMS rollback | Gây exception sau send output trong `OrderRelay` | Input có thể được giao lại, output không được commit |

## 9. Checklist chọn abstraction

| Yêu cầu | Ưu tiên |
|---|---|
| Gửi/nhận String, byte[], JMS headers/properties | `JmsTemplate` |
| Cần `MessageCreator`/`MessagePostProcessor`/`SessionCallback` | `JmsTemplate` |
| API service dùng Spring `Message<T>` và custom headers | `JmsMessagingTemplate` |
| Nhận payload bằng đích kiểu `receiveAndConvert("queue", Type.class)` | `JmsMessagingTemplate`, với converter tương ứng |
| Consumer bất đồng bộ dài hạn | `@JmsListener` và listener container |
| Framework 7 muốn fluent API mới | Xem thêm `JmsClient`, không cần loại bỏ hai template |

**Tiêu chí nghiệm thu:** dependency JMS provider tương thích Classic/Artemis; bean template dùng chung factory; gửi/nhận đúng body; Spring headers tương ứng JMS properties; polling có timeout; payload converter được cấu hình rõ; không mặc định hai lời gọi tách rời có cùng transaction.

**Kết luận:** `JmsTemplate` là lớp làm việc sát JMS API và thích hợp khi cần kiểm soát chi tiết message, selector, callback. `JmsMessagingTemplate` bổ sung Spring `Message<T>` với payload/headers, thuận lợi khi tầng service đã dùng Spring Messaging. Cả hai **dùng cùng nền JMS**, không tự thay thế broker reliability, transaction hoặc idempotency.

## Tài liệu chính thức

1. [Spring Framework 6.2 — Using Spring JMS](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html): `JmsTemplate`, `JmsMessagingTemplate`, resource lifecycle và thread safety.
2. [Spring Framework 6.2 — Sending a Message](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/sending.html): `MessageCreator`, `MessagePostProcessor`, converter và request/reply.
3. [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html): nhận đồng bộ, `receiveTimeout` và `@JmsListener`.
4. [Spring Framework 6.2 Javadoc — JmsTemplate](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html): `convertAndSend`, `receiveAndConvert`, QoS và timeout.
5. [Spring Framework 6.2 Javadoc — JmsMessagingTemplate](https://docs.spring.io/spring-framework/docs/6.2.5/javadoc-api/org/springframework/jms/core/JmsMessagingTemplate.html): `send`, `receiveAndConvert` và JMS message converter.
6. [Spring Boot 3.5 — JMS](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): starter Classic/Artemis, bean template và listener.
7. [Spring Boot 3.5 — Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `spring.jms.template.*`, `spring.activemq.*` và `spring.artemis.*`.
