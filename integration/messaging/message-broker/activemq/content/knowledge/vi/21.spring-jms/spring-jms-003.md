# MessageConverter cho JSON, kiểu dữ liệu và header ánh xạ

> **Chương:** Spring JMS  
> **Module:** `INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ` — tích hợp Java/JMS với ActiveMQ Artemis và ActiveMQ Classic.  
> **Phạm vi triển khai:** Spring Boot **3.x** + Spring Framework **6.x** + Jakarta Messaging (`jakarta.jms.*`) + Jackson **2.x**. Bài sử dụng `MappingJackson2MessageConverter`; nếu ứng dụng dùng Spring Framework **7.x/Jackson 3**, hãy xem phần tương thích phiên bản cuối bài.  
> **Mục tiêu:** Biến POJO/record thành JMS JSON message và nhận lại đúng Java type, đồng thời kiểm soát riêng **body**, **JMS message properties**, **JMS standard headers** và **Spring Messaging headers**.

## 1. Vì sao gửi JSON thành công nhưng listener vẫn không nhận được DTO?

Một dịch vụ đơn hàng gửi object Java:

~~~java
OrderCreatedV1 event = new OrderCreatedV1(
    "evt-100", "ORD-100", 159900L, 1
);
jmsTemplate.convertAndSend("lab.spring.orders", event);
~~~

Người viết thường kỳ vọng `@JmsListener` tự nhận `OrderCreatedV1`. Tuy nhiên, kết quả còn phụ thuộc vào **MessageConverter** mà `JmsTemplate` và listener container thực sự dùng:

- Converter mặc định `SimpleMessageConverter` hiểu một số loại như `String` → `TextMessage`, `byte[]` → `BytesMessage`, `Map` → `MapMessage`. Nó **không phải Jackson JSON serializer cho mọi DTO**.
- `MappingJackson2MessageConverter` dùng Jackson để chuyển Java object thành JSON trong JMS `TextMessage` hoặc `BytesMessage`. Mặc định converter này **gửi `BytesMessage`**, không phải `TextMessage`.
- Khi chuyển JSON về Java object, converter cần biết **Java type đích**; trong đường JMS converter thông thường, nó dùng một **message property chứa type id** được chỉ định bởi `setTypeIdPropertyName(...)`.
- Payload JSON có trường `eventId` không có nghĩa broker tự tạo JMS property `eventId`. Để consumer dùng selector hoặc `@Header("eventId")`, producer phải gắn property/header có thể ánh xạ riêng.
- `JMSCorrelationID`, `JMSMessageID`, `JMSPriority` là **JMS headers**, không phải JSON fields và cũng không phải JMS custom properties.

Một ứng dụng có thể gửi đi bytes JSON hoàn toàn hợp lệ, broker lưu message thành công, nhưng nhận message thất bại ở **giai đoạn chuyển đổi type** trước khi gọi logic nghiệp vụ. Nếu listener dùng transacted session, lỗi conversion có thể làm rollback rồi redelivery; nếu không nhận diện đúng, message có thể lặp cho tới DLQ.

### Mô hình đường đi

~~~mermaid
flowchart LR
    A["OrderCreatedV1 Java record"] --> C["JMS MessageConverter / Jackson"]
    C --> M["JMS TextMessage: JSON body"]
    C --> T["JMS property: eventTypeId"]
    M --> B[(Artemis queue)]
    T --> B
    H["MessagePostProcessor: tenantId, eventId, JMSCorrelationID"] --> B
    B --> L["JMS MessageConverter ở listener"]
    L --> D["OrderCreatedV1 Java record"]
    B --> J["JMS headers + properties qua HeaderMapper / @Header"]
    J --> E["Thông tin metadata ở listener"]
~~~

**Tư duy cần nhớ:** JSON conversion trả lời *nội dung body biến thành object nào*; header mapping trả lời *metadata trên JMS message xuất hiện ở API Spring như thế nào*. Hai việc liên quan nhưng **không đồng nhất**.

## 2. Hai hệ MessageConverter trong Spring không cùng interface

Spring có hai contract dễ bị import nhầm:

| Lớp API | Interface/converter | Đối tượng đầu vào/đầu ra | Được dùng ở đâu? |
|---|---|---|---|
| **Spring JMS** | `org.springframework.jms.support.converter.MessageConverter` | Java object ↔ `jakarta.jms.Message` | `JmsTemplate.convertAndSend/receiveAndConvert`, JMS listener adapter/container |
| **Spring Messaging** | `org.springframework.messaging.converter.MessageConverter` | Payload ↔ `org.springframework.messaging.Message<?>` / requested target type | Các messaging abstraction nói chung; `JmsMessagingTemplate`, `JmsClient` theo version và cấu hình |
| **Bridge giữa Spring Messaging và JMS** | `org.springframework.jms.support.converter.MessagingMessageConverter` | `org.springframework.messaging.Message<?>` ↔ JMS `Message` | Kết hợp **payload converter** và `JmsHeaderMapper` |
| **Header mapper** | `org.springframework.jms.support.JmsHeaderMapper` | Spring `MessageHeaders` ↔ JMS headers/properties | `SimpleJmsHeaderMapper` và messaging adapters |

Đây là lý do hai class cùng tên “MessageConverter” nhưng **không được thay thế trực tiếp cho nhau**. Trong mã thực hành, import phải là:

~~~java
import org.springframework.jms.support.converter.MessageConverter;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageType;
~~~

Không thay import thứ nhất thành `org.springframework.messaging.converter.MessageConverter`: phương thức `setMessageConverter(...)` của `JmsTemplate` trong Spring Framework 6.x yêu cầu **Spring JMS converter**.

### Vì sao không cấu hình Jackson ObjectMapper là đủ?

`ObjectMapper` biết serialize Java object thành chuỗi JSON. Nhưng việc gửi JMS còn cần:

1. Tạo đúng **JMS message type**: `TextMessage` hoặc `BytesMessage`.
2. Chọn encoding/representation phù hợp với consumer khác ngôn ngữ.
3. Gắn **type id** nếu receiver dùng converter kiểu từ JMS message.
4. Đặt các **JMS properties và headers** cần dùng cho routing, correlation, tracing.
5. Bảo đảm **producer và listener dùng cùng wire contract**.

`ObjectMapper` là một thành phần trong `MappingJackson2MessageConverter`; nó không tự cấu hình `JmsTemplate`, `@JmsListener` hay JMS headers.

## 3. MappingJackson2MessageConverter: loại message và thông tin type

### 3.1. TEXT hay BYTES là một quyết định có chủ đích

Trong Spring Framework 6.2, `MappingJackson2MessageConverter`:

- **Mặc định** tạo `BytesMessage` với JSON bytes.
- Khi đặt `setTargetType(MessageType.TEXT)`, tạo `TextMessage` chứa JSON string.
- Khi nhận, nó hỗ trợ đọc từ `TextMessage` và `BytesMessage` phù hợp với converter.
- Có thể cấu hình `setEncoding("UTF-8")` và `setEncodingPropertyName(...)` cho ngữ cảnh encoding của bytes.
- **Không** tạo `MapMessage` hay `ObjectMessage` bằng cách chỉ chuyển `targetType` sang một giá trị tùy ý.

Ví dụ cấu hình then chốt:

~~~java
MappingJackson2MessageConverter converter =
    new MappingJackson2MessageConverter(objectMapper);

converter.setTargetType(MessageType.TEXT);
converter.setTypeIdPropertyName("eventTypeId");
converter.setTypeIdMappings(
    Map.of("order-created-v1", OrderCreatedV1.class)
);
~~~

Kết quả outbound về mặt logic:

~~~text
JMS Message class: TextMessage

JMS body:
  {"eventId":"evt-100","orderId":"ORD-100",
   "amountMinor":159900,"schemaVersion":1}

JMS properties:
  eventTypeId = "order-created-v1"   (String)
~~~

**Phân biệt:** `eventTypeId` ở đây là **JMS property**, không phải bắt buộc là một field trong JSON body. Converter dùng property này để chọn Java type khi gọi `fromMessage(...)`. Nếu body JSON có field `"eventTypeId"` nhưng JMS property thiếu, converter không tự đọc field JSON đó để chọn type.

### 3.2. Type id alias giúp giảm phụ thuộc tên class Java

Nếu không cấu hình map type id, converter có thể dùng **fully qualified Java class name** trong property; cách đó khiến message contract phụ thuộc package/class của producer. Khi producer đổi package, consumer cũ có thể không đọc được message đang tồn.

Nên dùng alias theo phiên bản event:

| JMS property | Giá trị | Java type được đăng ký |
|---|---|---|
| `eventTypeId` | `order-created-v1` | `OrderCreatedV1.class` |
| `eventTypeId` | `order-cancelled-v1` | `OrderCancelledV1.class` |
| `eventTypeId` | `order-created-v2` | `OrderCreatedV2.class` |

Một event type mới cần được **đăng ký rõ** ở hệ thống nhận và triển khai theo chính sách tương thích/backward compatibility. Giữ type id ổn định trong thời gian message có thể lưu ở queue và DLQ.

**Quan trọng về an toàn:** `setTypeIdMappings` làm outbound dùng alias và cho receiver nhận alias; **không nên coi riêng map này là bộ lọc bảo mật đủ mạnh** cho mọi type id không tin cậy. Converter vẫn có chiến lược đọc class name khi không tìm được mapping ở một số bản. Với đầu vào không tin cậy, giới hạn loại message/producer, phân quyền queue, và kiểm chứng allowlist type id trước deserialization hoặc dùng converter custom chỉ chấp nhận type đã đăng ký.

### 3.3. Missing type id là lỗi contract

Với cấu hình trên, inbound message phải mang:

~~~text
eventTypeId = "order-created-v1"
~~~

Nếu producer bên ngoài chỉ gửi body JSON, không có JMS property `eventTypeId`, mã gọi `fromMessage()` có thể báo **MessageConversionException** thay vì tự suy từ signature `OrderCreatedV1` ở mọi đường đi.

Không chữa bằng cách bật default polymorphic typing hoặc deserialize class name do client bất kỳ cung cấp. Giải pháp là **thỏa thuận header/type id**, hoặc cung cấp **đường nhận raw JSON** rồi deserialize vào **type cố định đã biết**. Phần 9 minh họa hai chiến lược.

## 4. Phân biệt body JSON, message properties, standard JMS headers và Spring headers

### 4.1. Bốn vùng dữ liệu

| Vùng | Ví dụ | API đọc/ghi | Ngữ nghĩa chính |
|---|---|---|---|
| **Body** | `{"amountMinor":159900}` | `TextMessage.getText()` hoặc Jackson qua converter | Dữ liệu nghiệp vụ theo schema |
| **Custom JMS properties** | `tenantId="vn"`, `schemaVersion=1`, `eventTypeId="order-created-v1"` | `setStringProperty()`, `setIntProperty()`, `getObjectProperty()` | Metadata ứng dụng; selector thường đánh giá tại đây |
| **Standard JMS headers** | `JMSCorrelationID`, `JMSMessageID`, `JMSType`, `JMSReplyTo` | `setJMSCorrelationID()`, `getJMSMessageID()`… | Phần ngữ nghĩa của JMS provider |
| **Spring Messaging headers** | `jms_correlationId`, `tenantId`, `id`, `timestamp` | `@Header`, `MessageHeaders`, `JmsHeaderMapper` | Abstraction chung của Spring, được ánh xạ khi qua JMS |

**Vùng không giống nhau dù cùng ý nghĩa:** `OrderCreatedV1.amountMinor` trong JSON là một JSON number; `message.setLongProperty("amountMinor", 159900)` là một **JMS property kiểu long**. Broker không tự sao chép một field trong body ra property.

### 4.2. Headers tiêu chuẩn được ánh xạ theo tên Spring

Một số tên thường gặp trong `org.springframework.jms.support.JmsHeaders` (Spring Framework 6.x):

| JMS API header | Spring Messaging header key | Ghi chú |
|---|---|---|
| `JMSCorrelationID` | `JmsHeaders.CORRELATION_ID` = `jms_correlationId` | Dùng để correlating request/reply; ứng dụng có thể đặt |
| `JMSMessageID` | `JmsHeaders.MESSAGE_ID` = `jms_messageId` | Thường do provider tạo; **không dùng** như event id nghiệp vụ |
| `JMSType` | `JmsHeaders.TYPE` = `jms_type` | JMS type label; **không phải** `eventTypeId` của Jackson |
| `JMSReplyTo` | `JmsHeaders.REPLY_TO` = `jms_replyTo` | Destination trả lời |
| `JMSPriority` | `JmsHeaders.PRIORITY` = `jms_priority` | Thuộc QoS gửi; không phải JSON field |
| `JMSRedelivered` | `JmsHeaders.REDELIVERED` = `jms_redelivered` | Dấu hiệu delivery lại; không phải idempotency key |

Có thể dùng `@Header(JmsHeaders.CORRELATION_ID)` trong listener khi thao tác với Spring Messaging headers. Tuy nhiên, **dùng raw `jakarta.jms.Message.getJMSCorrelationID()` là cách chắc chắn nhất để kiểm tra header thực trên wire** khi đang debug mapping.

**Không nhầm:** Spring `MessageHeaders.ID`/`MessageHeaders.TIMESTAMP` được tạo trong abstraction của Spring; chúng không tự động là `JMSMessageID`/`JMSTimestamp` của broker.

### 4.3. HeaderMapper không phải JSON converter

`SimpleJmsHeaderMapper` ánh xạ các JMS headers phù hợp và custom properties giữa JMS `Message` với Spring `MessageHeaders`. Còn `MappingJackson2MessageConverter` xử lý **payload Java object ↔ JMS body** và property type id của chính nó.

Nếu dùng `JmsMessagingTemplate`/`MessagingMessageConverter`, có hai bước:

~~~text
Spring Message<OrderCreatedV1>
    ├── payload (OrderCreatedV1)
    │      └── Jackson JMS MessageConverter
    │              └── JMS TextMessage body
    └── headers (tenantId, jms_correlationId...)
           └── SimpleJmsHeaderMapper
                   └── JMS properties + standard headers
~~~

Trong ví dụ chính dùng `JmsTemplate`, ta đặt metadata bằng `MessagePostProcessor` để minh họa **chính xác JMS API** và không phụ thuộc vào các default mapper phức tạp.

### 4.4. Không gắn object tùy ý vào JMS property

JMS message property chỉ nhận các kiểu cơ bản được JMS hỗ trợ, như boolean, byte, short, int, long, float, double, String. Những cấu trúc như `Map<String,Object>`, DTO, `UUID` hay `Instant` không nên đưa thẳng bằng `setObjectProperty()` rồi kỳ vọng mọi JMS provider chấp nhận.

Dùng:

~~~java
message.setStringProperty("eventId", event.eventId());
message.setIntProperty("schemaVersion", event.schemaVersion());
message.setStringProperty("tenantId", tenantId);
message.setLongProperty("amountMinor", event.amountMinor());
~~~

Không dùng:

~~~java
// Không portable và không phù hợp JMS property contract:
message.setObjectProperty("event", event);
message.setObjectProperty("createdAt", java.time.Instant.now());
~~~

Với kiểu ngày giờ, truyền UTC ISO-8601 string trong JSON body hoặc string property nếu thực sự cần selector.

## 5. Chuẩn bị Artemis và dependency Spring Boot

### 5.1. Destination và loại routing

Ví dụ chọn **một anycast queue** `lab.spring.orders`. Đặt đoạn sau trong **section `<addresses>` hiện có** của `ARTEMIS_INSTANCE/etc/broker.xml`, chỉ khi address/queue chưa tồn tại:

~~~xml
<address name="lab.spring.orders">
    <anycast>
        <queue name="lab.spring.orders">
            <durable>true</durable>
        </queue>
    </anycast>
</address>
~~~

Đây chỉ là mảnh XML; không thay toàn bộ `broker.xml`. Broker cần acceptor Core/JMS ở `tcp://127.0.0.1:61616` và tài khoản có quyền `send`/`consume` tại address. Trong lab, restart broker sau thay cấu hình và xác nhận queue tồn tại. `JmsTemplate.convertAndSend()` chỉ gửi đến một destination; **nó không tự định nghĩa đúng address/queue hay cấp quyền trên broker**.

### 5.2. Maven trong một dự án Spring Boot 3.x

Các dependency cần thiết (được quản lý version bằng **Spring Boot 3.x BOM/parent** của dự án, ví dụ nhánh 3.5.x):

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-artemis</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-json</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

- `spring-boot-starter-artemis` cung cấp Spring JMS và Artemis client phù hợp trong ngữ cảnh Boot.
- `spring-boot-starter-json` bổ sung Jackson 2.x theo BOM Boot 3.x, bao gồm `ObjectMapper`.
- Không đồng thời thêm hai dòng `javax.jms.*` và `jakarta.jms.*` tùy tiện. Spring Boot 3.x dùng Jakarta Messaging.
- Spring Boot 4.x/Framework 7 có thay đổi quanh Jackson 3 và converter; xem mục 12 trước khi copy code nguyên trạng.

### 5.3. Connection settings

`application.yml`:

~~~yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://127.0.0.1:61616
    user: ${ARTEMIS_USER}
    password: ${ARTEMIS_PASSWORD}
  jms:
    pub-sub-domain: false
~~~

`native` nghĩa là kết nối tới broker Artemis đang chạy, không khởi động một embedded broker trong ứng dụng. Không hardcode password thật trong source; dùng biến môi trường hoặc secret mechanism của deployment.

## 6. Ví dụ hoàn chỉnh: record, converter, publisher và listener

Ví dụ sử dụng Spring Framework 6.2/Jackson 2.x. Mỗi khối được đặt vào một file Java cùng package (chẳng hạn `com.example.jmsjson`). Các import đã khai báo để tránh nhầm hai loại converter.

### 6.1. Định nghĩa schema ứng dụng

File `OrderCreatedV1.java`:

~~~java
package com.example.jmsjson;

public record OrderCreatedV1(
    String eventId,
    String orderId,
    long amountMinor,
    int schemaVersion
) {}
~~~

Hợp đồng JSON mong muốn:

~~~json
{
  "eventId": "evt-100",
  "orderId": "ORD-100",
  "amountMinor": 159900,
  "schemaVersion": 1
}
~~~

Giá trị `amountMinor` là **số nguyên đơn vị nhỏ nhất** để không có sai số floating-point. Producer và consumer phải thống nhất về đơn vị, currency và schema; việc Jackson parse thành `long` không tự bảo đảm dữ liệu nghiệp vụ hợp lệ.

### 6.2. Cấu hình cùng converter cho cả gửi lẫn nhận

File `JmsJsonConfiguration.java`:

~~~java
package com.example.jmsjson;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageType;

import java.util.Map;

@Configuration
@EnableJms
public class JmsJsonConfiguration {

    @Bean
    MappingJackson2MessageConverter jmsJsonMessageConverter(
            ObjectMapper objectMapper) {

        var converter =
            new MappingJackson2MessageConverter(objectMapper);

        // Mặc định là BYTES: chọn TEXT có chủ đích để tiện JSON.
        converter.setTargetType(MessageType.TEXT);
        converter.setTypeIdPropertyName("eventTypeId");
        converter.setTypeIdMappings(
            Map.of("order-created-v1", OrderCreatedV1.class)
        );
        return converter;
    }

    @Bean(name = "jmsListenerContainerFactory")
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory,
            MappingJackson2MessageConverter converter) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setMessageConverter(converter);
        factory.setSessionTransacted(true);
        factory.setPubSubDomain(false);
        factory.setConcurrency("1");
        return factory;
    }

    @Bean
    JmsTemplate jmsTemplate(
            ConnectionFactory connectionFactory,
            MappingJackson2MessageConverter converter) {

        var template = new JmsTemplate(connectionFactory);
        template.setMessageConverter(converter);
        template.setPubSubDomain(false);
        template.setSessionTransacted(true);
        template.setExplicitQosEnabled(true);
        template.setDeliveryMode(DeliveryMode.PERSISTENT);
        return template;
    }
}
~~~

**Vì sao cấu hình explicit cả hai đầu?**

1. `JmsTemplate` phải biết cách chuyển `OrderCreatedV1` → JSON `TextMessage`.
2. `@JmsListener` phải dùng **cùng converter** để đọc lại type id và ánh xạ JSON → `OrderCreatedV1`.
3. `sessionTransacted=true` giúp lỗi conversion/handler gây rollback JMS khi listener được container quản lý. Nó **không** tự mở rộng JMS transaction sang DB nghiệp vụ.
4. `concurrency("1")` làm kết quả lab dễ kiểm tra; đây **không** phải cách tối ưu throughput cho production.
5. Với `JmsTemplate`, `setExplicitQosEnabled(true)` cho phép áp dụng delivery mode đã cấu hình; local transacted send được template commit sau thao tác. Ứng dụng thật cần nhận biết ranh giới Spring transaction manager nếu có.
6. Spring Boot có auto-configuration cho converter bean trong các trường hợp mặc định, nhưng code này **không dựa vào auto-wiring ngầm**, tránh gửi bằng converter A và nhận bằng converter B.

### 6.3. Gửi JSON body và metadata

File `OrderPublisher.java`:

~~~java
package com.example.jmsjson;

import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderPublisher {
    private static final String QUEUE = "lab.spring.orders";

    private final JmsTemplate jmsTemplate;

    public OrderPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publish(
            OrderCreatedV1 event,
            String tenantId,
            String correlationId) {

        if (event == null || event.eventId() == null
                || event.eventId().isBlank()) {
            throw new IllegalArgumentException("eventId là bắt buộc");
        }
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("tenantId là bắt buộc");
        }

        jmsTemplate.convertAndSend(QUEUE, event, message -> {
            // Custom JMS properties: KHÁC body JSON.
            message.setStringProperty("eventId", event.eventId());
            message.setStringProperty("tenantId", tenantId);
            message.setIntProperty(
                "schemaVersion", event.schemaVersion());
            message.setLongProperty("amountMinor", event.amountMinor());

            // Content type là convention property, không phải JMS
            // standard header chính thức của mọi protocol.
            message.setStringProperty(
                "content_type", "application/json");

            // Standard JMS header, không phải custom property.
            message.setJMSCorrelationID(correlationId);
            return message;
        });
    }
}
~~~

Khi gọi `convertAndSend`:

1. Converter Jackson serialize `event` thành JSON `TextMessage` và đặt `eventTypeId=order-created-v1`.
2. `MessagePostProcessor` được gọi **sau conversion, trước send** để đặt `eventId`, `tenantId`, `schemaVersion`, `amountMinor` và `JMSCorrelationID`.
3. `JmsTemplate` dùng JMS producer gửi vào queue. Nếu transaction local được cấu hình và hoàn tất, message persistent có thể nằm trong broker để consumer nhận.

Chú ý `content_type` là một **custom JMS property** được Spring JMS `JmsHeaderMapper` nhận biết theo convention; nó **không** đồng nghĩa mọi AMQP/STOMP/MQTT client tự thấy một header content-type theo đúng giao thức khác. Interoperability vẫn cần hợp đồng và integration test.

### 6.4. Đọc DTO cùng header qua @JmsListener

File `OrderListener.java`:

~~~java
package com.example.jmsjson;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @JmsListener(
        destination = "lab.spring.orders",
        containerFactory = "jmsListenerContainerFactory"
    )
    public void handle(
            @Payload OrderCreatedV1 event,
            @Header("tenantId") String tenantId,
            Message rawMessage) throws JMSException {

        String eventIdHeader =
            rawMessage.getStringProperty("eventId");
        String typeId =
            rawMessage.getStringProperty("eventTypeId");
        int schemaHeader =
            rawMessage.getIntProperty("schemaVersion");

        if (!event.eventId().equals(eventIdHeader)) {
            throw new IllegalArgumentException(
                "eventId trong JSON và JMS property không khớp");
        }
        if (!"order-created-v1".equals(typeId)
                || event.schemaVersion() != schemaHeader) {
            throw new IllegalArgumentException(
                "Sai event type/schema version");
        }

        System.out.printf(
            "received event=%s tenant=%s type=%s "
            + "correlation=%s jmsMessageId=%s%n",
            event.eventId(),
            tenantId,
            typeId,
            rawMessage.getJMSCorrelationID(),
            rawMessage.getJMSMessageID()
        );

        // Business handler thật phải idempotent theo eventId.
        // Khi method hoàn thành không ném exception, listener
        // container transacted sẽ commit JMS delivery.
    }
}
~~~

Các tham số minh họa ba cơ chế **đồng thời**:

- `@Payload OrderCreatedV1 event`: Jackson JMS converter xử lý JSON body và type id.
- `@Header("tenantId")`: Spring trích custom JMS property thành metadata.
- `jakarta.jms.Message rawMessage`: nhận raw JMS message, dùng để kiểm tra standard header và property thực.

Không đặt `@Header("JMSCorrelationID")` theo phỏng đoán tên: trong abstraction Spring nên dùng `JmsHeaders.CORRELATION_ID`, còn ở đây truy cập trực tiếp `rawMessage.getJMSCorrelationID()` để tránh nhập nhằng.

### 6.5. Điểm khác nhau giữa body và property khi đọc

Với payload:

~~~json
{"eventId":"evt-100","orderId":"ORD-100",
 "amountMinor":159900,"schemaVersion":1}
~~~

bên nhận nhìn thấy:

| Trường | Trong `OrderCreatedV1` | Trong raw JMS message |
|---|---|---|
| `eventId` | `event.eventId() = "evt-100"` | `getStringProperty("eventId") = "evt-100"` khi producer đặt |
| `amountMinor` | `event.amountMinor() = 159900L` | `getLongProperty("amountMinor") = 159900L` khi producer đặt |
| `tenantId` | Không nằm trong record ví dụ | `getStringProperty("tenantId") = "vn"` |
| `eventTypeId` | Không nằm trong record ví dụ | `getStringProperty("eventTypeId") = "order-created-v1"` |
| `JMSCorrelationID` | Không nằm trong record | `getJMSCorrelationID()` từ JMS header |
| `JMSMessageID` | Không nằm trong record | `getJMSMessageID()` do provider tạo |

Nếu receiver khác sử dụng raw `TextMessage`, nó vẫn có thể parse JSON body theo schema. Nhưng để Spring Jackson converter tự tạo đúng `OrderCreatedV1`, receiver cần type-id contract như trên.

## 7. Gửi dữ liệu thử và quan sát với broker

Sau khi broker và application đã chạy, gọi `OrderPublisher.publish(...)` từ một `CommandLineRunner`, test hoặc một service khác. Ví dụ component thử một lần:

~~~java
package com.example.jmsjson;

import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DemoSendConfiguration {

    @Bean
    CommandLineRunner sendSample(OrderPublisher publisher) {
        return args -> publisher.publish(
            new OrderCreatedV1("evt-100", "ORD-100", 159900L, 1),
            "vn",
            "corr-100"
        );
    }
}
~~~

**Chỉ dùng `CommandLineRunner` này trong lab.** Mỗi lần khởi động lại ứng dụng sẽ gửi một message mới mang cùng `eventId`. Trong hệ thống thật, nên dùng endpoint/command có kiểm soát và outbox để tránh publish trùng ngoài ý muốn.

### Kỳ vọng

1. Producer sử dụng JMS `TextMessage`; broker queue `lab.spring.orders` nhận message.
2. Raw body là JSON chứa `eventId`, `orderId`, `amountMinor` và `schemaVersion`.
3. Custom JMS properties gồm `eventTypeId=order-created-v1`, `tenantId=vn`, `eventId=evt-100`, `schemaVersion=1`, `amountMinor=159900` và `content_type=application/json`.
4. `JMSCorrelationID=corr-100`, còn `JMSMessageID` do provider cấp (không cần trùng `eventId`).
5. Listener nhận được `OrderCreatedV1` và log các trường; khi handler hoàn thành, transaction JMS được container commit.
6. Nếu listener hoạt động ngay, queue có thể hết message trước khi bạn kịp quan sát console. Hãy quan sát bằng log hoặc tạm không chạy listener khi kiểm tra queue raw.

**Không gọi `receiveAndConvert()` ở một consumer khác trong khi `@JmsListener` cùng queue đang chạy** rồi kỳ vọng hai bên cùng nhận được một message: JMS queue có ngữ nghĩa competing consumer, một message được ACK bởi một consumer thì không còn cho consumer khác.

## 8. Type và selector: dữ liệu có trong JSON không có nghĩa selector truy cập được

Một người viết selector:

~~~sql
amountMinor >= 100000 AND tenantId = 'vn'
~~~

JMS selector đánh giá **message properties và các header thích hợp**, không parse JSON body. Trong ví dụ publisher, selector khớp vì đã gọi:

~~~java
message.setLongProperty("amountMinor", event.amountMinor());
message.setStringProperty("tenantId", tenantId);
~~~

Nếu chỉ gửi:

~~~java
jmsTemplate.convertAndSend(
    "lab.spring.orders",
    new OrderCreatedV1("evt-101", "ORD-101", 159900L, 1)
);
~~~

converter vẫn tạo JSON body và `eventTypeId`, nhưng **không tự thêm property `amountMinor` hay `tenantId`**; selector trên hai property này không khớp.

### Kiểu số ở JMS property không được đoán từ chuỗi

Hai cách gửi khác nhau:

~~~java
message.setLongProperty("amountMinor", 159900L);   // Numeric
message.setStringProperty("amountMinor", "159900"); // String
~~~

Với selector so số `amountMinor >= 100000`, trường gửi kiểu numeric đáp ứng hợp đồng mong muốn. Nếu gửi kiểu String, không nên trông chờ JMS broker tự chuyển thành số. Một client STOMP thường có header dạng text; khi kết nối khác giao thức cần kiểm thử mapping property type cụ thể.

**Khuyến nghị:** Thống nhất rõ trường nào bắt buộc làm **metadata phục vụ routing/filter**. Không sao chép mọi field JSON ra message property; điều đó tạo nhiều nguồn sự thật dễ lệch nhau. Chỉ duplicate trường cần selector, kiểm tra chúng khớp body và dùng property types đúng.

## 9. Khi nhận JSON từ producer ngoài Spring

Nếu producer là ứng dụng Node.js, Python, STOMP hoặc Java JMS tự tạo `TextMessage`, nó có thể không biết convention `eventTypeId` của Spring:

~~~text
Body JSON hợp lệ: có
JMS property eventTypeId: không có
~~~

Sử dụng trực tiếp `MappingJackson2MessageConverter.fromMessage(...)` trên message đó có thể thất bại vì không xác định type. Có hai chiến lược **khác nhau**:

### Chiến lược A — Chuẩn hóa type id ở các producer

Bên phát đặt:

~~~java
TextMessage message = session.createTextMessage(json);
message.setStringProperty("eventTypeId", "order-created-v1");
message.setStringProperty("tenantId", "vn");
~~~

Bên nhận đăng ký type mapping tương ứng trong converter. Đây là cách gọn nhất nếu các service đã đồng thuận contract và được kiểm soát.

### Chiến lược B — Đọc raw message, chọn Java type do ứng dụng quyết định

Nếu message ngoại lai không có type id, đừng giả mạo property để ép converter. Có thể đọc bằng **JMSContext transacted** và Jackson, chọn **type cố định đã biết từ destination**:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSConsumer;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;

// Bên trong một service đã được inject ConnectionFactory và ObjectMapper:
try (JMSContext context = connectionFactory.createContext(
        user, password, JMSContext.SESSION_TRANSACTED)) {

    Queue queue = context.createQueue("lab.spring.external");
    JMSConsumer consumer = context.createConsumer(queue);
    Message received = consumer.receive(5000);

    if (received != null) {
        try {
            if (!(received instanceof TextMessage text)) {
                throw new IllegalArgumentException(
                    "Expected JSON TextMessage");
            }
            OrderCreatedV1 event = objectMapper.readValue(
                text.getText(), OrderCreatedV1.class);

            // Validate schema/version và xử lý idempotent ở đây.
            process(event);
            context.commit();
        } catch (Exception error) {
            context.rollback();
            throw error;
        }
    }
}
~~~

Khối trên là **đoạn logic đặt trong một phương thức**, với `connectionFactory`, `user`, `password`, `objectMapper` và `process(event)` được cung cấp bởi service; không phải một file Java độc lập. Queue `lab.spring.external` là một destination khác, phải được provision trước nếu broker không auto-create.

**Điểm an toàn:** `readValue(..., OrderCreatedV1.class)` chọn type **theo code tin cậy**, không lấy class name trực tiếp từ một header bên ngoài. Transaction phải rollback nếu parse/validation/process lỗi; không ACK trước rồi mới parse JSON. Nếu muốn dùng `@JmsListener` nhận raw, cấu hình một **listener container factory riêng** không áp Jackson JMS converter yêu cầu type id, tránh lỗi conversion xảy ra trước khi handler nhận được raw message.

### Khi nào nên dùng converter custom?

Khi có nhiều message schema cùng destination và type id được định nghĩa bởi **một protocol contract riêng**, có thể triển khai `org.springframework.jms.support.converter.MessageConverter` để:

- Đọc event type/version từ một property đã allowlist.
- Chọn Java type trong tập đăng ký, không load class tùy ý từ header.
- Kiểm tra content type/charset, payload size và schema version.
- Tạo message type/text/bytes thống nhất.
- Giữ quy tắc lỗi rõ ràng: reject payload sai, rollback/retry có giới hạn, rồi DLQ.

Đây là trường hợp cần converter riêng, không phải lý do bật Jackson polymorphic default typing không kiểm soát.

## 10. Kiểm thử MessageConverter không cần broker

Trước khi test Artemis end-to-end, có thể kiểm tra **converter đúng wire contract** với Mockito. Dự án dùng `spring-boot-starter-test` và code record ở mục 6.

File `JmsJsonConverterTest.java`:

~~~java
package com.example.jmsjson;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageType;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.*;

class JmsJsonConverterTest {

    @Test
    void jsonTextAndTypeIdRoundTrip() throws Exception {
        Session session = mock(Session.class);
        TextMessage jmsMessage = mock(TextMessage.class);
        when(session.createTextMessage(anyString()))
            .thenReturn(jmsMessage);

        var converter =
            new MappingJackson2MessageConverter(new ObjectMapper());
        converter.setTargetType(MessageType.TEXT);
        converter.setTypeIdPropertyName("eventTypeId");
        converter.setTypeIdMappings(
            Map.of("order-created-v1", OrderCreatedV1.class)
        );

        var payload = new OrderCreatedV1(
            "evt-test", "ORD-test", 100_000L, 1
        );

        assertThat(converter.toMessage(payload, session))
            .isSameAs(jmsMessage);

        ArgumentCaptor<String> body =
            ArgumentCaptor.forClass(String.class);
        verify(session).createTextMessage(body.capture());
        assertThat(body.getValue())
            .contains("\"eventId\":\"evt-test\"");
        assertThat(body.getValue())
            .contains("\"amountMinor\":100000");

        verify(jmsMessage).setStringProperty(
            "eventTypeId", "order-created-v1");

        // Mock mô phỏng message broker trả lại cùng body và type id.
        when(jmsMessage.getText()).thenReturn(body.getValue());
        when(jmsMessage.getStringProperty("eventTypeId"))
            .thenReturn("order-created-v1");

        assertThat(converter.fromMessage(jmsMessage))
            .isEqualTo(payload);
    }
}
~~~

Test này **không chứng minh broker routing/ACK**, nhưng chứng minh converter:

1. Đã gọi `Session.createTextMessage(json)` thay vì tạo BytesMessage.
2. Serialize đúng field JSON và kiểu số mong muốn.
3. Đã ghi JMS type id theo alias.
4. Dùng alias để đọc ngược JSON về đúng record.

Các test thêm nên có:

| Test | Đầu vào | Kỳ vọng |
|---|---|---|
| Không có `eventTypeId` | TextMessage chỉ có JSON body | Converter từ chối hoặc báo lỗi thiếu type id theo implementation |
| Type id không biết | `eventTypeId=unknown-v9` | Không tùy ý deserialize class; tầng validation/allowlist từ chối |
| JSON sai | Body `{"eventId":` | Conversion thất bại, handler nghiệp vụ không được gọi |
| Schema v2 mới | `eventTypeId=order-created-v2` | Phải map vào DTO v2 hoặc quyết định tương thích rõ ràng |
| Custom JMS property numeric | `setLongProperty("amountMinor", 100000)` | `getObjectProperty("amountMinor")` có kiểu `Long` |
| Content type custom | `content_type=application/json` | Header có mặt, **không** làm thay đổi JMS message type một cách tự động |
| Correlation ID | `setJMSCorrelationID("corr-123")` | Raw message trả đúng `getJMSCorrelationID()` |

Không kiểm thử `JMSMessageID` bằng một chuỗi cố định của provider; chỉ kiểm tra nó xuất hiện khi message được broker cấp phát phù hợp.

## 11. Lỗi chuyển đổi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân điển hình | Cách kiểm tra |
|---|---|---|
| `convertAndSend(dto)` lỗi `MessageConversionException` | `SimpleMessageConverter` không chuyển DTO thành JSON như kỳ vọng | Kiểm tra bean/config của `JmsTemplate.getMessageConverter()` |
| Listener không nhận `OrderCreatedV1` | Listener factory dùng converter khác producer | Gán cùng converter qua `setMessageConverter(...)` cho factory |
| JSON hợp lệ nhưng listener lỗi trước handler | Thiếu/sai `eventTypeId` | Dùng raw message browser để xem JMS property thực |
| Receiver chờ `TextMessage` nhưng thấy `BytesMessage` | Jackson JMS converter mặc định chọn BYTES | Đặt `MessageType.TEXT` hoặc hỗ trợ cả hai loại |
| JSON body có `tenantId` nhưng `@Header("tenantId")` rỗng | Không gắn custom JMS property `tenantId` | Dùng `MessagePostProcessor.setStringProperty` |
| `@Header("JMSCorrelationID")` không lấy đúng giá trị | Nhầm tên header Spring và JMS native | Dùng `JmsHeaders.CORRELATION_ID` hoặc raw JMS getter |
| Selector so số không khớp | Property numeric không được set, hoặc bị gửi thành String | In `getObjectProperty` và Java class; fix producer |
| Spring MessageHeaders ID khác JMSMessageID | Hai hệ header có vòng đời ID khác nhau | Phân biệt `MessageHeaders.ID` và `JmsHeaders.MESSAGE_ID` |
| Listener chạy lặp khi payload sai | Conversion ném exception, transacted listener rollback | Quan sát redelivery/DLQ; sửa schema/contract trước replay |
| `JMSCorrelationID` thay đổi sau bridge | Header mapping provider/protocol khác nhau | Test trên đúng Core/AMQP/STOMP broker/client version |
| Body được parse nhưng field quan trọng bằng 0 | DTO primitive `long/int`, thiếu field trong JSON | Thêm schema validation; cân nhắc wrapper types nếu cần phát hiện thiếu |
| Không có `ObjectMapper` để inject | Thiếu Jackson dependency hoặc auto-config | Thêm starter JSON trong Spring Boot 3.x, kiểm tra config |
| App Spring 7 không thấy API khớp code | Dùng Jackson 3 và converter mới | Chọn `JacksonJsonMessageConverter` cùng API/version tương ứng |

### 11.1. Phân loại conversion failure và retry

Không nên để malformed JSON hoặc type id không được hỗ trợ bị **rollback vô hạn** mà không có cơ chế cách ly. Với `sessionTransacted=true`, exception từ converter/handler thường gây rollback JMS, broker có thể redeliver theo redelivery policy. Hãy:

- Phân biệt lỗi **vĩnh viễn** (schema sai, type alias không biết) với lỗi **tạm thời** (DB timeout, dependency 503).
- Cấu hình giới hạn delivery attempts/DLQ trên Artemis hoặc chính sách phù hợp của ActiveMQ Classic.
- Ghi nhận `eventId`, `JMSMessageID`, type id, exception class và phiên bản schema vào log chẩn đoán.
- Chỉ đưa message từ DLQ về main sau khi sửa producer/consumer hoặc payload theo quy trình được kiểm soát.
- Không ACK lỗi conversion để “dẹp hàng” nếu nghiệp vụ không cho phép bỏ message; nếu quyết định loại bỏ thì phải có audit.

**Lưu ý biên transaction:** Local JMS transaction của listener không nguyên tử với DB/HTTP ngoài broker. Khi xử lý DB thành công nhưng JMS commit thất bại, message có thể được giao lại. Idempotent handler theo `eventId` vẫn là yêu cầu độc lập với JSON converter.

### 11.2. Lưu ý schema và deserialization

- Đặt `schemaVersion` trong body, kiểm tra cùng type id; đừng chỉ dựa vào Java class name.
- Với primitive `long`, Jackson có thể dùng giá trị mặc định khi field thiếu, tùy cấu hình. Nếu cần phát hiện “không có amount”, cân nhắc `Long` nullable và validation trước xử lý.
- Không để producer ngoài hệ thống tự chọn type id dẫn tới deserialization bất kỳ class. Không bật Jackson default typing không kiểm soát.
- Hạn chế payload size và số lượng property; JSON hợp lệ vẫn có thể quá lớn hoặc chứa cấu trúc lồng sâu.
- Nếu cần hỗ trợ event schema v1/v2 song song, đăng ký converter và DTO tương thích, lập kế hoạch tồn đọng queue/DLQ trước khi xóa type cũ.
- Đừng coi `content_type` custom JMS property là một cơ chế xác minh payload hợp lệ: **phải parse và validate**.

## 12. Phiên bản, Artemis/Classic và giao thức khác

**Spring Framework 6.x + Jackson 2.x:** ví dụ này dùng `org.springframework.jms.support.converter.MappingJackson2MessageConverter`, phù hợp với Spring Boot 3.x.

**Spring Framework 7.x + Jackson 3.x:** `MappingJackson2MessageConverter` được đánh dấu deprecated/for removal, với lớp thay thế **`JacksonJsonMessageConverter`** trong package JMS converter. Không copy import, constructor hoặc loại ObjectMapper từ Spring 6.x một cách máy móc; đối chiếu API của đúng Spring/Boot/Jackson version khi nâng cấp.

**ActiveMQ Artemis và ActiveMQ Classic:** Spring JMS converter làm việc trên **JMS API**, nên các nguyên tắc body/header/type id vẫn hữu ích ở cả hai; nhưng ConnectionFactory, broker config, destination provisioning, redelivery và protocol mapping không giống nhau. Spring Boot dùng `spring.artemis.*` cho Artemis và `spring.activemq.*` cho Classic; không dùng cấu hình `broker.xml` Artemis trên broker Classic.

**Giao tiếp không đồng nhất:** nếu producer dùng STOMP/MQTT/AMQP native, chúng có cơ chế header/body riêng. JSON body còn đọc được không có nghĩa `eventTypeId` và kiểu property numeric của JMS tự nhiên xuất hiện. Phải định nghĩa wire contract và test consumer nhận từ đúng protocol.

### Câu hỏi tự kiểm tra

1. Vì sao `SimpleMessageConverter` không tự tạo JSON cho mọi Java DTO?
2. Spring Framework 6.x `MappingJackson2MessageConverter` mặc định tạo `BytesMessage` hay `TextMessage`? Cần gọi setter nào để chọn TEXT?
3. Tại sao `setTypeIdPropertyName("eventTypeId")` quan trọng khi muốn `fromMessage()` trả Java object?
4. `eventTypeId` do Jackson converter gắn khác `JMSType` như thế nào?
5. `tenantId` nằm trong JSON body, nhưng không được producer gắn JMS property. `@Header("tenantId")` có tự đọc được không?
6. Giải thích sự khác nhau giữa `MessagePostProcessor` và `JmsHeaderMapper`.
7. Vì sao `amountMinor >= 100000` trong JMS selector không đọc trực tiếp field JSON?
8. Khi type alias không có trong consumer mới, nên cố load Java class từ header do bên ngoài gửi hay kiểm soát allowlist?
9. `@JmsListener` ném exception vì JSON sai trong session transacted. Message thường đi theo hướng nào và phải cấu hình gì để không lặp vô hạn?
10. Tại sao khi chuyển từ Spring Boot 3.x sang 4.x không nên giả định converter Jackson 2 vẫn là API được khuyến nghị?

**Định hướng đáp án:** (1) chỉ có conversion cơ bản JMS message types; (2) BYTES, dùng `MessageType.TEXT`; (3) cần metadata chọn Java type khi deserialize; (4) custom type-id contract khác JMS standard header; (5) không, phải map property/header; (6) đặt sửa raw JMS message sau conversion so với mapper Spring Messaging ↔ JMS metadata; (7) selector dùng property/header, không parse body; (8) allowlist và type cố định; (9) rollback/redelivery/DLQ có giới hạn; (10) Spring Framework 7 chuyển sang converter Jackson 3.

## 13. Tài liệu chính thức

- [Spring Framework 6.2 — Sending a Message / Using JMS Message Converters](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/sending.html): `JmsTemplate.convertAndSend`, `receiveAndConvert`, `MessagePostProcessor` và `SimpleMessageConverter`.
- [Spring Framework 6.2 — Annotation-driven JMS Listener Endpoints](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html): `@JmsListener`, `@Payload`, `@Header`, raw `jakarta.jms.Message` và listener container.
- [Spring Framework 6.2 — MappingJackson2MessageConverter API](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html): `MessageType.TEXT/BYTES`, `setTypeIdPropertyName` và `setTypeIdMappings`.
- [Spring Framework 6.2 — SimpleJmsHeaderMapper API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/support/SimpleJmsHeaderMapper.html): quy tắc ánh xạ JMS standard headers và custom properties.
- [Spring Framework 6.2 — JmsHeaders API](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/jms/support/JmsHeaders.html): các tên header Spring như `jms_correlationId`.
- [Spring Boot — JMS / ActiveMQ Artemis](https://docs.spring.io/spring-boot/reference/messaging/jms.html): starter, cấu hình `spring.artemis.*` và listener/container auto-configuration; đối chiếu tài liệu đúng nhánh Boot 3.x trước khi copy.
- [Spring Framework 7 — JacksonJsonMessageConverter API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/converter/JacksonJsonMessageConverter.html): nhánh Jackson 3 và thay đổi khi nâng Spring.

**Kết luận:** Một message JSON dùng Spring JMS có **ba hợp đồng phải kiểm chứng riêng**: *(1) body ↔ Java type*, *(2) type id và custom JMS properties*, *(3) standard JMS headers ↔ Spring headers*. Dùng `MappingJackson2MessageConverter` cấu hình explicit `MessageType.TEXT` và type-id alias; dùng `MessagePostProcessor` để đặt property/header đúng kiểu; dùng cùng converter cho `JmsTemplate` và `@JmsListener`; thử cả happy path lẫn missing type id/schema lỗi trước khi đưa vào production.
