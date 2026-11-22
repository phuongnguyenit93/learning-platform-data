# Phân biệt converter của spring-jms với spring-messaging

> **Module:** Spring Framework – JMS  
> **Chủ đề cha:** Chuyển đổi dữ liệu  
> **Trọng tâm:** Hai interface cùng tên `MessageConverter` nhưng thuộc hai tầng API khác nhau; cách phối hợp với `JmsTemplate`, `JmsMessagingTemplate` và `@JmsListener`.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Chỉ đúng package và chữ ký hàm của `org.springframework.jms.support.converter.MessageConverter` và `org.springframework.messaging.converter.MessageConverter`.
2. Phân biệt ba loại dữ liệu dễ bị gọi chung là “Message”: `jakarta.jms.Message` của broker, `org.springframework.messaging.Message<?>` của Spring và **payload Java** như `String`, `byte[]` hoặc DTO.
3. Giải thích **wire conversion** (payload Java ↔ JMS Message) và **method-argument conversion** (Spring Message payload ↔ kiểu tham số handler); tránh nhầm chúng chỉ là một thao tác.
4. Cấu hình Spring JMS converter đúng tại `JmsTemplate.setMessageConverter(...)` hoặc `DefaultJmsListenerContainerFactory.setMessageConverter(...)`.
5. Hiểu vì sao `JmsMessagingTemplate` có **hai điểm cấu hình**: `setMessageConverter(...)` theo Spring Messaging và `setJmsMessageConverter(...)` cho cầu nối JMS.
6. Sử dụng `MessagingMessageConverter` và `JmsHeaderMapper` để kết nối hai message model nhưng không nhầm adapter này với interface converter của spring-messaging.
7. Thiết kế JSON/DTO conversion đúng schema và type-id, giảm phụ thuộc vào Java class name và tránh Java native serialization không tin cậy.
8. Phân biệt lỗi conversion khi gửi, khi nhận JMS, khi bind tham số `@JmsListener` và khi mapping headers.

## 1. Từ khóa quan trọng: cùng một tên, hai trách nhiệm khác nhau

Tên **`MessageConverter`** xuất hiện ở hai package chính:

- **JMS-specific:** `org.springframework.jms.support.converter.MessageConverter`.
- **Transport-independent Spring Messaging:** `org.springframework.messaging.converter.MessageConverter`.

Chúng **không phải cùng interface**, không kế thừa nhau và **không thể thay thế trực tiếp cho nhau**. Việc cả hai đều có phương thức tên `toMessage`/`fromMessage` dễ khiến IDE tự import nhầm.

Hai model message cũng không giống nhau:

```text
  Java application
   OrderCreated / String / byte[]             (business payload)
                  |
                  v
     Spring Messaging Message<?>
       payload + MessageHeaders
                  |
       [bridge / payload converter]
                  |
                  v
        Jakarta JMS Message
       TextMessage / BytesMessage / ...
       JMS headers + JMS properties
                  |
                  v
              JMS broker
```

Đường đi ngược là broker → `jakarta.jms.Message` → payload/headers đã giải mã → `org.springframework.messaging.Message<?>` hoặc đối tượng method-argument trong handler.

**Nhớ một câu:**

> `spring-jms` converter hiểu **`Session` và JMS wire message**; `spring-messaging` converter hiểu **Spring `Message<?>` và kiểu payload đích**, không cần biết JMS `Session` là gì.

Tên module `spring-messaging` **không phải tên một broker khác**. Đây là abstraction chung dùng được qua nhiều transport (JMS, STOMP/WebSocket, message channels và những integration khác), tùy infrastructure cụ thể.

### 1.1. Sơ đồ ranh giới package

```text
org.springframework.jms.support.converter
  └── MessageConverter
        toMessage(Object, jakarta.jms.Session)
        fromMessage(jakarta.jms.Message)
              ^
              | implements
              └── MessagingMessageConverter
                   (JMS-specific adapter, hiểu Spring Message<?>)


org.springframework.messaging.converter
  └── MessageConverter
        toMessage(Object, org.springframework.messaging.MessageHeaders)
        fromMessage(org.springframework.messaging.Message<?>, Class<?>)
              ^
              | implements
              ├── SimpleMessageConverter
              ├── GenericMessageConverter
              └── MappingJackson2MessageConverter (Spring Messaging variant)
```

Tên `MappingJackson2MessageConverter` cũng xuất hiện trong nhiều package khác nhau. **Không suy ra lớp nào chỉ từ simple class name**; phải đọc package import và method signature.

## 2. So sánh hai interface theo chữ ký thực tế

### 2.1. Converter của spring-jms

Hợp đồng trong package `org.springframework.jms.support.converter`:

```java
// Phác họa chữ ký interface để học API; không tự khai báo
// lớp/interface này trong source của ứng dụng.
jakarta.jms.Message toMessage(
        Object object,
        jakarta.jms.Session session
) throws jakarta.jms.JMSException, MessageConversionException;

Object fromMessage(
        jakarta.jms.Message message
) throws jakarta.jms.JMSException, MessageConversionException;
```

Các phương thức cụ thể:

- `toMessage(Object, Session)`: chuyển một object Java thành **`jakarta.jms.Message`** thông qua `Session` hiện tại. Session cần thiết để tạo `TextMessage`, `BytesMessage`, `MapMessage`, v.v.
- `fromMessage(jakarta.jms.Message)`: đọc một message **đã nhận từ broker** và trả về Java object phù hợp.
- Không có tham số `Class<?> targetClass` trong interface cơ bản; implementation có thể dựa vào body type, JMS property chứa type-id, hoặc cấu hình converter để tìm kiểu đích.
- Có thể ném checked `JMSException` từ API JMS hoặc `org.springframework.jms.support.converter.MessageConversionException` khi dữ liệu không phù hợp.
- Điểm cấu hình thường gặp: `JmsTemplate.setMessageConverter(...)`, `DefaultJmsListenerContainerFactory.setMessageConverter(...)`, `MessageListenerAdapter.setMessageConverter(...)`.

### 2.2. Converter của spring-messaging

Hợp đồng trong package `org.springframework.messaging.converter`:

```java
// Phác họa chữ ký interface: sử dụng Spring Messaging types.
org.springframework.messaging.Message<?> toMessage(
        Object payload,
        org.springframework.messaging.MessageHeaders headers);

Object fromMessage(
        org.springframework.messaging.Message<?> message,
        Class<?> targetClass);
```

Các phương thức cụ thể:

- `toMessage(payload, headers)`: tạo **Spring `Message<?>`**, gồm payload đã chuyển đổi và các `MessageHeaders` (nếu có). **Không cần JMS Session**.
- `fromMessage(springMessage, targetClass)`: chuyển payload của Spring Message sang **kiểu Java cụ thể** do caller yêu cầu.
- Interface cho phép trả `null` nếu không hỗ trợ media type hoặc không thể thực hiện conversion; bên gọi phải xử lý điều kiện này.
- Có thể dùng `MessageHeaders.CONTENT_TYPE` và các MIME types để chọn converter; logic MIME support phụ thuộc implementation.
- Thường dùng ở `org.springframework.messaging.core`, `JmsMessagingTemplate` phía Spring-facing, và conversion/binding tham số của annotated handler qua `DefaultMessageHandlerMethodFactory`.
- Ngoại lệ thuộc Spring Messaging/ConversionService khi conversion lỗi, **không nhất thiết là `JMSException`**.

### 2.3. Bảng đối chiếu

| Tiêu chí | `spring-jms MessageConverter` | `spring-messaging MessageConverter` |
| --- | --- | --- |
| Full package | `org.springframework.jms.support.converter` | `org.springframework.messaging.converter` |
| Model đầu vào đặc trưng khi đọc | `jakarta.jms.Message` | `org.springframework.messaging.Message<?>` |
| Model trả về khi ghi | `jakarta.jms.Message` | `org.springframework.messaging.Message<?>` |
| Có cần `jakarta.jms.Session` để tạo output? | **Có** | **Không** |
| `fromMessage` có `targetClass`? | Không ở interface cơ bản | **Có** |
| Nội dung converter hiểu | TextMessage, BytesMessage, MapMessage, JMS properties/body | Payload/MessageHeaders, class đích, content type |
| Điểm cấu hình | `JmsTemplate`, JMS listener factory | `JmsMessagingTemplate`, handler method factory, Spring messaging template |
| Default phổ biến | JMS `SimpleMessageConverter` | Messaging `SimpleMessageConverter`/`GenericMessageConverter` theo hạ tầng |
| Loại lỗi điển hình | JMS API, payload không map được sang JMS body | ConversionService, target class/MIME conversion |
| Có thể cast giữa hai interface? | **Không** | **Không** |

**Không viết:**

```java
import org.springframework.messaging.converter.MessageConverter;

// Lỗi kiểu: JmsTemplate.setMessageConverter đòi
// org.springframework.jms.support.converter.MessageConverter.
// template.setMessageConverter(new GenericMessageConverter());
```

Đây là **anti-pattern không biên dịch** được đặt trong ví dụ để nhấn mạnh lỗi import, không phải mã cần chạy. Spring Messaging `GenericMessageConverter` không triển khai converter interface của `spring-jms`.

## 3. Ba tầng dữ liệu thường bị nhập nhằng

### Tầng A — JMS Message (wire/protocol-aware)

Type: `jakarta.jms.Message` và subtype:

- `TextMessage`: body String.
- `BytesMessage`: body binary.
- `MapMessage`: map có các kiểu giá trị JMS hỗ trợ.
- `ObjectMessage`: Java object serialization, cần cân nhắc rủi ro deserialization và tương thích class.
- `StreamMessage`: chuỗi các primitive value.
- `Message` không body: vẫn có headers/properties, tùy use case.

Ngoài body, có `JMSMessageID`, `JMSCorrelationID`, `JMSReplyTo`, `JMSDeliveryMode`, `JMSPriority`, và application properties theo quy tắc JMS.

JMS body **không được mô tả chỉ bằng một đối tượng Java record** trừ khi converter cụ thể biết cách encode record vào một trong các wire type trên.

### Tầng B — Spring Message<?> (transport-agnostic)

Type: `org.springframework.messaging.Message<T>`. Nó chứa:

```java
message.getPayload();  // T
message.getHeaders();  // MessageHeaders
```

Spring Message không yêu cầu `Session`, không có method `getJMSReplyTo()` trực tiếp và không tự thể hiện toàn bộ JMS-specific APIs. JMS metadata có thể được biểu diễn thành Spring headers sau mapping, ví dụ thông qua `JmsHeaders`.

Một Spring Message có thể bọc `String`, DTO, `byte[]` hoặc đối tượng khác; nó **không phải** một instance của `jakarta.jms.Message`.

### Tầng C — Payload object để handler xử lý

Type: `String`, `byte[]`, `OrderCreated`, v.v.

Với:

```java
@JmsListener(destination = "orders.created")
public void handle(OrderCreated event) {
    // event là payload, không phải JMS Message.
}
```

Method parameter `OrderCreated` có thể đến từ JMS-specific conversion ra DTO **hoặc** từ việc Spring Messaging chuyển payload trung gian sang kiểu `OrderCreated` theo handler factory. Không tự nhận rằng cả hai bước luôn xảy ra hoặc rằng hai converter có cùng trách nhiệm.

### Ví dụ tư duy về cùng một nội dung

```text
JMS TextMessage:
  getText() = "{\"orderId\":\"ORD-42\"}"

Spring Message<String>:
  payload = "{\"orderId\":\"ORD-42\"}"
  headers = { contentType="application/json", ... }

Spring Message<OrderCreated>:
  payload = OrderCreated("ORD-42")

Listener method:
  void handle(OrderCreated event)
```

Đây là **ba trạng thái biểu diễn khác nhau**. JSON String trong `TextMessage` không tự biến thành DTO chỉ vì tham số listener có kiểu `OrderCreated`; phải có đường chuyển đổi tương ứng được cấu hình.

## 4. spring-jms: converter nằm sát JMS Session

### 4.1. JmsTemplate.convertAndSend sử dụng converter nào?

`JmsTemplate` thuộc package `org.springframework.jms.core`. Các overload như:

```java
jmsTemplate.convertAndSend("orders.created", "ORD-42");
Object payload = jmsTemplate.receiveAndConvert("orders.created");
```

sử dụng `org.springframework.jms.support.converter.MessageConverter` mà template đã cấu hình.

Luồng gửi:

```text
Java object
     |
     v
JmsTemplate.convertAndSend(...)
     |
     v
JMS-specific converter.toMessage(object, session)
     |
     v
jakarta.jms.TextMessage / BytesMessage / ...
     |
     v
MessageProducer.send(destination, jmsMessage)
```

Luồng nhận đồng bộ:

```text
MessageConsumer.receive(...)
     |
     v
jakarta.jms.Message
     |
     v
JMS-specific converter.fromMessage(jmsMessage)
     |
     v
Java object
```

Điểm khác: `JmsTemplate.send(..., MessageCreator)` cho phép tự tạo JMS Message bằng callback `Session`; nó **không bắt buộc đi qua converter** của `convertAndSend`. Với `receive(...)` nhận raw `jakarta.jms.Message`, không được tự hiểu rằng đã giải mã như `receiveAndConvert(...)`.

### 4.2. JMS SimpleMessageConverter mặc định

`org.springframework.jms.support.converter.SimpleMessageConverter` thường là default của `JmsTemplate`. Một số đường chuyển đổi tiêu biểu:

| Payload Java | JMS type khi gửi |
| --- | --- |
| `String` | `TextMessage` |
| `byte[]` | `BytesMessage` |
| `Map<String, ?>` với kiểu giá trị hợp lệ | `MapMessage` |
| `Serializable` object | Có thể được đưa qua `ObjectMessage` |

Ở chiều nhận, converter đọc subtype JMS và trích xuất String, byte[], Map hoặc Serializable object tùy loại. **Đừng xem nó là JSON converter**. Một Java record tùy ý **không tự động thành JSON text** chỉ vì gọi `convertAndSend(record)`.

Lưu ý về `ObjectMessage`: Java serialization đòi class tương thích giữa publisher và consumer, tiềm ẩn lỗi version/classloader và nguy cơ deserialization dữ liệu không tin cậy. Trong hệ thống tích hợp liên dịch vụ, ưu tiên schema JSON/Avro/Protobuf có xác thực thay vì phát tán arbitrary Java object.

### 4.3. Đặt converter tại JmsTemplate

Trong một Spring project có `jakarta.jms.ConnectionFactory`:

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.converter.SimpleMessageConverter;

@Configuration
public class JmsConversionConfiguration {

    @Bean
    JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setMessageConverter(new SimpleMessageConverter());
        return template;
    }
}
```

Đây là class **dùng trong dự án Spring có dependencies và broker**, không phải file chạy độc lập bằng JDK. Thực tế không cần set converter nếu bạn chấp nhận default; ở đây set rõ để chứng minh **đúng loại interface**.

Khi code dùng `send(destination, session -> ...)` để tự tạo raw TextMessage, method đó không dựa vào `SimpleMessageConverter`; callback tạo message thay conversion.

### 4.4. Đưa metadata JMS sau khi converter chạy

`MessagePostProcessor` của `JmsTemplate` là callback ở tầng JMS sau conversion, trước send:

```java
jmsTemplate.convertAndSend(
        "orders.created",
        "ORD-42",
        jmsMessage -> {
            jmsMessage.setStringProperty("eventType", "OrderCreated");
            jmsMessage.setJMSCorrelationID("request-42");
            return jmsMessage;
        });
```

Ở đây callback thao tác trực tiếp `jakarta.jms.Message`, không phải `org.springframework.messaging.Message<?>`. Không nhầm `org.springframework.jms.core.MessagePostProcessor` với `org.springframework.messaging.core.MessagePostProcessor`: chúng cũng là hai contract khác nhau.

**Chú ý:** property `eventType` là JMS custom property có tên hợp lệ, không tự thay đổi TTL/priority/delivery mode. Nếu muốn JMS QoS, dùng producer/template QoS API; không nhét vào custom property rồi mong broker điều khiển.

## 5. spring-messaging: converter thao tác Spring Message và targetClass

### 5.1. Spring Messaging SimpleMessageConverter không phải JMS SimpleMessageConverter

Spring Messaging cũng có class tên:

```text
org.springframework.messaging.converter.SimpleMessageConverter
```

Class này chuyển đổi payload khi thích hợp vào/ra **Spring Message<?>**, không nhận JMS `Session`. Chỉ nhìn `SimpleMessageConverter` mà không xem import là cách dễ viết nhầm code.

Một converter chung có thể dựa vào `Class<?> targetClass`, ví dụ String `"42"` có thể được chuyển thành `Integer` nếu `ConversionService` có converter String → Integer.

### 5.2. GenericMessageConverter và ConversionService

`org.springframework.messaging.converter.GenericMessageConverter` thường ủy quyền conversion cho `ConversionService` để đổi payload sang kiểu method mong muốn.

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.converter.GenericMessageConverter;
import org.springframework.messaging.support.MessageBuilder;

Message<String> springMessage =
        MessageBuilder.withPayload("42").build();

GenericMessageConverter converter = new GenericMessageConverter();
Object converted =
        converter.fromMessage(springMessage, Integer.class);
```

Đây là **mảnh code trong project Spring Messaging**, không phải tệp Java standalone chỉ dùng JDK. `GenericMessageConverter` mặc định dùng ConversionService được cấu hình; với cấu hình Spring mặc định có thể đổi `"42"` thành `Integer.valueOf(42)`. Nếu payload không chuyển được sang kiểu đích, converter có thể trả null hoặc phát sinh lỗi phù hợp; không suy rộng mọi object đều convertible.

`targetClass` xuất hiện **trong converter Spring Messaging**, không nằm trong interface cơ bản của converter JMS. Đây là dấu hiệu hữu ích nhất khi mở code của `@JmsListener`.

### 5.3. Content type là tín hiệu, không phải phép màu

Spring Message có `MessageHeaders.CONTENT_TYPE`. Converter theo MIME như `org.springframework.messaging.converter.MappingJackson2MessageConverter` (Spring 6 với Jackson 2) có thể chọn JSON khi content type phù hợp và được cấu hình.

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

Message<String> jsonMessage = MessageBuilder
        .withPayload("{\"orderId\":\"ORD-42\"}")
        .setHeader(MessageHeaders.CONTENT_TYPE,
                   MimeTypeUtils.APPLICATION_JSON)
        .build();
```

Đây mới là **Spring Message<String> có header JSON**. Nó chưa là `jakarta.jms.TextMessage`, chưa gửi broker, và chưa là `OrderCreated` DTO. Cần component khác để dùng MIME converter chuyển payload sang kiểu đích, và cần bridge/JMS converter để tạo body JMS khi gửi.

Không mặc định mọi header của Spring sẽ chuyển thành JMS property nguyên vẹn: JMS property name/type có giới hạn và các header như `id`, `timestamp` không có quan hệ một-một với `JMSMessageID`/`JMSTimestamp`.

## 6. JmsMessagingTemplate: nơi hai tầng converter gặp nhau

Spring hỗ trợ `org.springframework.jms.core.JmsMessagingTemplate`, đóng vai trò JMS adapter cho Spring Messaging message abstraction.

Nó dùng mô hình:

```text
Spring app
  |
  | convertAndSend(payload) / send(Message<?>)
  v
Spring Messaging MessageConverter           [nếu cần convert payload]
  |
  v
org.springframework.messaging.Message<?>
  |
  | JmsMessagingTemplate
  v
JMS-specific MessagingMessageConverter      [cầu nối wire]
  |
  +-- payloadConverter (JMS-specific MessageConverter)
  +-- JmsHeaderMapper
  |
  v
jakarta.jms.Message
  |
  v
JmsTemplate / broker
```

**Hai setter khác nhau, dù đều có từ “converter”:**

- `JmsMessagingTemplate.setMessageConverter(org.springframework.messaging.converter.MessageConverter)`: method kế thừa từ `AbstractMessageSendingTemplate`; dùng cho conversion ở **Spring Messaging API** khi ứng dụng gọi `convertAndSend(...)` hoặc `receiveAndConvert(..., targetClass)`.
- `JmsMessagingTemplate.setJmsMessageConverter(org.springframework.jms.support.converter.MessageConverter)`: converter biến Spring Message sang JMS message và ngược lại, dùng cho **transport boundary**. Mặc định ở đây là `MessagingMessageConverter`, kết hợp JMS `SimpleMessageConverter` cho payload.

**Không nhầm `setJmsMessageConverter(...)` với `JmsTemplate.setMessageConverter(...)`:** cả hai nhận JMS-specific interface, nhưng `JmsMessagingTemplate` đang cấu hình bộ bridge của riêng nó. Đừng cho rằng thay converter của một `JmsTemplate` đang được dùng ở nơi khác sẽ tự động đồng bộ mọi pipeline/chế độ conversion của `JmsMessagingTemplate`.

### 6.1. Ví dụ gửi Spring Message qua JMS

Trong project có `spring-jms`, `spring-messaging` và broker:

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.jms.core.JmsMessagingTemplate;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public final class MessagingGateway {
    private final JmsMessagingTemplate messagingTemplate;

    public MessagingGateway(ConnectionFactory cf) {
        this.messagingTemplate = new JmsMessagingTemplate(cf);
    }

    public void publish() {
        Message<String> event = MessageBuilder.withPayload("ORD-42")
                .setHeader("eventType", "OrderCreated")
                .build();
        messagingTemplate.send("orders.created", event);
    }
}
```

Đây là class tích hợp, **không chạy chỉ với JDK**. `JmsMessagingTemplate` làm bridge từ Spring Message<String> thành `TextMessage` theo payload converter mặc định. Tên `"orders.created"` là destination name, cần broker/queue được cấu hình phù hợp. Bản thân message có header `eventType` không bảo đảm mọi JMS provider sẽ map property tùy ý giống nhau nếu custom mapper được cài đặt; cần test với cấu hình cụ thể.

### 6.2. Cấu hình rõ hai layer

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsMessagingTemplate;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.converter.MessagingMessageConverter;
import org.springframework.messaging.converter.GenericMessageConverter;

@Configuration
public class MessagingBridgeConfig {

    @Bean
    JmsMessagingTemplate jmsMessagingTemplate(ConnectionFactory cf) {
        JmsTemplate jmsTemplate = new JmsTemplate(cf);
        JmsMessagingTemplate template =
                new JmsMessagingTemplate(jmsTemplate);

        // Tầng Spring Messaging: payload + target type.
        template.setMessageConverter(new GenericMessageConverter());

        // Tầng JMS boundary: Spring Message<?> <-> JMS Message.
        MessagingMessageConverter bridge = new MessagingMessageConverter();
        template.setJmsMessageConverter(bridge);
        return template;
    }
}
```

Cấu hình này minh họa **đúng kiểu tham số của hai setter**. Default `MessagingMessageConverter` đã được Spring cung cấp; đặt lại explicit chỉ để thấy ranh giới. Khi dùng DTO/JSON thực, một `GenericMessageConverter` đơn lẻ không tự bảo đảm serialize DTO thành JSON trên wire: cần cấu hình converter/serializer có schema và type mapping ở đúng tầng.

### 6.3. MessagingMessageConverter thực chất thuộc package nào?

Full name:

```text
org.springframework.jms.support.converter.MessagingMessageConverter
```

Dù tên có chữ “Messaging”, class này **implements `org.springframework.jms.support.converter.MessageConverter`**, không implements interface Spring Messaging converter. Nó nhận Java object trong `toMessage(Object, Session)`; object có thể là `org.springframework.messaging.Message<?>`, rồi class:

1. Trích xuất **payload** của Spring Message.
2. Chuyển payload qua một **JMS-specific payload converter** (default `SimpleMessageConverter`).
3. Map những Spring headers phù hợp sang JMS properties/headers thông qua `JmsHeaderMapper`.
4. Làm chiều ngược khi nhận JMS message.

Nó là **adapter**, không phải dấu hiệu rằng hai interface converter có cùng chữ ký.

Nếu cần Jackson JMS payload converter:

```java
MessagingMessageConverter bridge =
        new MessagingMessageConverter();
bridge.setPayloadConverter(jmsJsonConverter);
bridge.setHeaderMapper(new SimpleJmsHeaderMapper());
template.setJmsMessageConverter(bridge);
```

Đoạn này giả định các biến và imports ở scope Spring config:
`jmsJsonConverter` phải là `org.springframework.jms.support.converter.MessageConverter` (không phải Spring Messaging Jackson converter), `template` là `JmsMessagingTemplate`, và `SimpleJmsHeaderMapper` ở `org.springframework.jms.support`. Khi dùng JSON converter, type-id, target type và content headers phải được thiết kế tương thích hai chiều.

### 6.4. Vì sao “set converter rồi nhưng vẫn lỗi” xảy ra?

Vì một ứng dụng có thể có nhiều entry point:

- `JmsTemplate.convertAndSend(...)` → nhìn converter của **JmsTemplate**.
- `JmsMessagingTemplate.convertAndSend(...)` → trước hết có conversion của **Spring Messaging**, sau đó bridge JMS.
- `JmsMessagingTemplate.send(SpringMessage)` → đã có Spring Message, chủ yếu cần bridge JMS; không nhất thiết đi qua generic conversion của `convertAndSend`.
- `@JmsListener` với raw `jakarta.jms.Message` → có thể không cần payload conversion; method tự đọc raw.
- `@JmsListener` với `@Payload OrderCreated` → có thể phụ thuộc JMS-specific converter, Spring Messaging handler-argument converter hoặc cả hai, tùy cấu hình và dạng inbound.

**Không có một setter “toàn cục” bắt buộc mọi API conversion theo cùng một bean.** Cần xác định class đang gọi và đi qua tầng nào.

## 7. @JmsListener: hai giai đoạn conversion và method argument

Một `@JmsListener` nhận **JMS message từ provider** nhưng method handler có thể khai báo:

```java
@JmsListener(destination = "orders.created")
public void handle(String orderId) { ... }

@JmsListener(destination = "orders.created")
public void handleRaw(jakarta.jms.Message raw) { ... }

@JmsListener(destination = "orders.created")
public void handleSpring(org.springframework.messaging.Message<String> msg) { ... }

@JmsListener(destination = "orders.created")
public void handleDto(@Payload OrderCreated created) { ... }
```

Đây là **những chữ ký minh họa**, không phải bốn method cùng đăng ký trên một queue để chạy đồng thời. Nếu khai báo như thế thật, bốn listener sẽ cạnh tranh tiêu thụ message của một queue; đừng dự đoán một event được gửi sẽ gọi đủ bốn method. Dùng mỗi ví dụ riêng hoặc queue test riêng.

Với annotated endpoint, logic có thể gồm:

```text
JMS provider
  |
  v
jakarta.jms.Message
  |
  | JMS-specific MessageConverter
  | (configured on listener factory/adapter)
  v
Java payload / Spring Message representation
  |
  | Spring argument resolution and method-argument conversion
  | (DefaultMessageHandlerMethodFactory)
  v
@Payload OrderCreated event / String / Message<T>
  |
  v
Application method
```

**Hai bước có mục đích khác nhau:**

- **Transport decoding:** biến `TextMessage`/`BytesMessage` thành Java payload, do JMS-specific converter của listener adapter xử lý.
- **Argument adaptation:** dùng Spring handler infrastructure để tạo tham số method, lấy `@Header`/`@Payload`, validation, hoặc chuyển payload sang `targetClass` nếu cần.

Nếu payload đã là đúng `OrderCreated`, argument resolver có thể đưa thẳng vào method, không nhất thiết phải decode lại bằng Messaging converter.

### 7.1. Đặt JMS converter ở listener container factory

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.support.converter.MessageConverter;

@Configuration
@EnableJms
public class ListenerConfig {

    @Bean("customJmsListenerFactory")
    DefaultJmsListenerContainerFactory customFactory(
            ConnectionFactory cf,
            MessageConverter wireConverter) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(cf);
        factory.setMessageConverter(wireConverter);
        factory.setSessionTransacted(true);
        return factory;
    }
}
```

Ở ví dụ này, `wireConverter` phải **implements `org.springframework.jms.support.converter.MessageConverter`**. Nếu inject nhầm `org.springframework.messaging.converter.MessageConverter`, code **không biên dịch**. Vì đây là method @Bean trong Spring project, cần cung cấp đúng bean converter để dependency injection không ambiguous; không thể chạy độc lập bằng `javac`.

`setSessionTransacted(true)` phục vụ reliability phía consumer, **không liên quan trực tiếp đến interface converter**. Conversion failure khi consumer xử lý có thể ảnh hưởng rollback/redelivery; cần retry/DLQ và idempotency phù hợp.

### 7.2. Đặt Spring Messaging converter cho method arguments

Spring cung cấp `DefaultMessageHandlerMethodFactory` để quản lý conversion/validation của annotated method arguments. Đây là tầng khác với `DefaultJmsListenerContainerFactory.setMessageConverter(...)`.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListenerConfigurer;
import org.springframework.jms.config.JmsListenerEndpointRegistrar;
import org.springframework.messaging.converter.GenericMessageConverter;
import org.springframework.messaging.handler.annotation.support
        .DefaultMessageHandlerMethodFactory;

@Configuration
@EnableJms
public class MethodArgumentConversionConfig implements JmsListenerConfigurer {

    @Override
    public void configureJmsListeners(JmsListenerEndpointRegistrar registrar) {
        registrar.setMessageHandlerMethodFactory(handlerMethodFactory());
    }

    @Bean
    DefaultMessageHandlerMethodFactory handlerMethodFactory() {
        var factory = new DefaultMessageHandlerMethodFactory();
        factory.setMessageConverter(new GenericMessageConverter());
        return factory;
    }
}
```

Đây là **class Spring config**, không phải chương trình JDK standalone. `factory.setMessageConverter(...)` ở đây nhận **`org.springframework.messaging.converter.MessageConverter`**. Một `GenericMessageConverter` thường xử lý các chuyển đổi đơn giản qua `ConversionService`; nếu cần JSON → DTO, phải cung cấp converter hỗ trợ JSON/content-type và xác nhận wire payload phù hợp.

**Quan trọng:** cấu hình method factory chỉ ảnh hưởng đường method-argument conversion, **không tự biến `JmsTemplate.convertAndSend(dto)` ở producer thành JSON TextMessage**. Publisher vẫn cần wire converter có thể encode DTO. Hai phía phải đồng ý schema.

### 7.3. Chuẩn hóa chuỗi JSON thành DTO: chọn một chiến lược rõ

Có hai thiết kế hợp lý, không nên trộn ngẫu nhiên:

**Chiến lược A — JMS converter giải JSON thành DTO:**

```text
JMS TextMessage JSON
    |
    +-- JMS MappingJackson2MessageConverter
    |      with typeIdPropertyName + mappings
    v
OrderCreated DTO
    |
    +-- @JmsListener method argument đã đúng kiểu
    v
handle(OrderCreated event)
```

**Chiến lược B — JMS converter chỉ đọc String, Spring Messaging converter đổi String → DTO:**

```text
JMS TextMessage JSON
    |
    +-- JMS SimpleMessageConverter
    v
String JSON
    |
    +-- Spring Messaging MappingJackson2MessageConverter
    |      with matching contentType / targetClass
    v
OrderCreated DTO
    |
    v
handle(OrderCreated event)
```

Ở chiến lược B, **content type phải đi qua header mapping** và converter phải hỗ trợ payload representation. Không phải chỉ thêm `@Payload OrderCreated` là Jackson tự chạy. Nếu ứng dụng đang dùng Spring JMS trực tiếp với DTO, chiến lược A thường dễ diễn giải hơn vì một nơi xác định Java ↔ JMS body contract. Nếu cần architecture chia sẻ converter với WebSocket/Messaging channels, chiến lược B có thể hữu ích khi mapping được thiết kế rõ.

## 8. Ví dụ JSON: cấu hình đúng converter phía JMS

### 8.1. JSON DTO và type-id contract

Giả sử ứng dụng dùng Spring 6.x, Jakarta Messaging, Jackson 2 và broker có queue `orders.created`. Với JMS `MappingJackson2MessageConverter`, cần xác định **JMS target type** và **type-id property** cho việc đọc lại DTO.

**File `OrderCreated.java`:**

```java
public record OrderCreated(String orderId, long amount) { }
```

**File `JsonJmsConfiguration.java`:**

```java
import jakarta.jms.ConnectionFactory;
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
public class JsonJmsConfiguration {

    @Bean
    MappingJackson2MessageConverter jsonJmsConverter() {
        var converter = new MappingJackson2MessageConverter();

        // Không dùng BytesMessage mặc định của Jackson JMS converter.
        converter.setTargetType(MessageType.TEXT);

        // Khi nhận từ JMS, dùng property này để xác định Java type.
        converter.setTypeIdPropertyName("_type");
        converter.setTypeIdMappings(
                Map.of("order-created-v1", OrderCreated.class));
        return converter;
    }

    @Bean("jsonJmsTemplate")
    JmsTemplate jsonJmsTemplate(
            ConnectionFactory cf,
            MappingJackson2MessageConverter jsonJmsConverter) {

        var template = new JmsTemplate(cf);
        template.setMessageConverter(jsonJmsConverter);
        return template;
    }

    @Bean("jsonListenerFactory")
    DefaultJmsListenerContainerFactory jsonListenerFactory(
            ConnectionFactory cf,
            MappingJackson2MessageConverter jsonJmsConverter) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(cf);
        factory.setMessageConverter(jsonJmsConverter);
        factory.setSessionTransacted(true);
        factory.setPubSubDomain(false);
        return factory;
    }
}
```

**File `OrderPublisher.java`:**

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderPublisher {
    private final JmsTemplate template;

    public OrderPublisher(@Qualifier("jsonJmsTemplate") JmsTemplate template) {
        this.template = template;
    }

    public void publish(OrderCreated event) {
        template.convertAndSend("orders.created", event);
    }
}
```

**File `OrderCreatedListener.java`:**

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    @JmsListener(
            destination = "orders.created",
            containerFactory = "jsonListenerFactory")
    public void handle(OrderCreated event) {
        System.out.println("Processed order " + event.orderId());
    }
}
```

Bộ code trên là **nhiều file trong cùng một Spring project**, không chạy độc lập bằng `javac` nếu thiếu Spring/Jackson/JMS provider. Ở consumer, JMS Jackson converter giải `TextMessage` JSON thành `OrderCreated` theo `_type` và mapping. Bean listener factory dùng **cùng JMS-specific converter**; chỉ cấu hình sender mà quên listener không đủ.

**Output có điều kiện** nếu broker hoạt động, queue tồn tại và lời gọi `publish(new OrderCreated("ORD-42", 1500))` diễn ra một lần thành công:

```text
Processed order ORD-42
```

Không hứa output xuất hiện đúng một lần trong mọi tình huống: JMS redelivery có thể khiến listener chạy lại, consumer có thể offline, broker có thể cần resource provisioning. Với business effect, cần idempotency theo `orderId` hoặc event ID.

### 8.2. Tại sao cấu hình _type và mapping?

JMS `MappingJackson2MessageConverter` của Spring 6 sử dụng type-id property để xác định Java class khi **đọc** message; nếu không cấu hình `setTypeIdPropertyName`, việc conversion từ JMS message về Java object sẽ không hoạt động như mong đợi.

Có thể map tên type ổn định `"order-created-v1"` thay vì truyền trực tiếp full Java class name. Cách này giúp giảm coupling giữa producer và consumer, và cho phép kiểm soát tập class có thể giải mã.

**Bảo mật:** dù có mapping, đừng cho producer không tin cậy tùy ý đưa class name hoặc payload object graph không kiểm soát. Xác thực schema/version, giới hạn size, kiểm tra ACL, và tránh deserialization Java native nếu không cần thiết. Với JSON, thư viện/class hỗ trợ của Spring có thể thay đổi theo phiên bản; dùng Javadoc của **version thực tế trong project**.

### 8.3. Khác gì Messaging MappingJackson2MessageConverter?

Lớp trong ví dụ là:

```text
org.springframework.jms.support.converter.MappingJackson2MessageConverter
```

Nó nhận `Session` để tạo `TextMessage` hoặc `BytesMessage`. Spring Messaging JSON converter là class **cùng simple name** nhưng ở package:

```text
org.springframework.messaging.converter.MappingJackson2MessageConverter
```

Nó convert payload của **Spring Message<?>** theo `targetClass` và MIME type. Hai lớp không thể import thay cho nhau; naming collision còn nguy hiểm nếu IDE auto-import sai.

## 9. Ví dụ custom JMS converter tự viết

Khi wire format rất đơn giản hoặc cần version marker rõ ràng, có thể tự implement JMS-specific interface.

**File `PrefixedTextJmsConverter.java`:**

```java
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

import org.springframework.jms.support.converter.MessageConverter;
import org.springframework.jms.support.converter.MessageConversionException;

public final class PrefixedTextJmsConverter implements MessageConverter {
    private static final String PREFIX = "v1:";

    @Override
    public Message toMessage(Object object, Session session)
            throws JMSException, MessageConversionException {

        if (!(object instanceof String text)) {
            throw new MessageConversionException(
                    "Expected a String payload");
        }
        return session.createTextMessage(PREFIX + text);
    }

    @Override
    public Object fromMessage(Message message)
            throws JMSException, MessageConversionException {

        if (!(message instanceof TextMessage textMessage)) {
            throw new MessageConversionException(
                    "Expected a TextMessage");
        }

        String wireText = textMessage.getText();
        if (wireText == null || !wireText.startsWith(PREFIX)) {
            throw new MessageConversionException(
                    "Unsupported text message version");
        }
        return wireText.substring(PREFIX.length());
    }
}
```

Đây là một class Java 17+ hợp lệ **trong project có Jakarta JMS + Spring JMS**, không chạy chỉ với JDK. Khi `JmsTemplate.convertAndSend("test.queue", "hello")` với converter này, message wire có body `"v1:hello"`. `receiveAndConvert` dùng converter tương ứng sẽ trả `"hello"`.

Ưu điểm: hợp đồng byte/string rõ. Hạn chế: chỉ hỗ trợ `String`, không hỗ trợ DTO/BytesMessage/MapMessage và không giải quyết header mapping. Nếu bừa bãi dùng converter này thay default trên mọi destination, những message không có `v1:` sẽ gặp conversion error.

### 9.1. Test logic cần có

- Input `"A"` → `TextMessage("v1:A")` → output `"A"`.
- Input `"v1:A"` → wire text `"v1:v1:A"` → decode còn `"v1:A"` (không lầm strip hai lần).
- Input DTO không phải String → fail sớm, không rơi sang `ObjectMessage`.
- Inbound `BytesMessage` → fail kiểu rõ.
- Inbound `TextMessage` body không bắt đầu `"v1:"` → fail version rõ.
- Kiểm tra unicode như `"Đơn-42"` không bị hỏng trong encode/decode.

Những test đó là **unit test converter JMS**. Trong integration test vẫn cần provider thật để xác minh body JMS, properties và transaction.

## 10. Kiểm thử hai tầng, không chụp tất cả vào một test

### 10.1. Unit test Spring Messaging converter

Test một Spring `Message<?>` đã có:

```java
// Đoạn test minh họa trong class JUnit đã có dependency Spring.
var message = MessageBuilder.withPayload("42").build();
var converter = new GenericMessageConverter();
Object result = converter.fromMessage(message, Integer.class);

// Với ConversionService mặc định hỗ trợ String -> Integer:
assertEquals(42, result);
```

Không cần JMS broker, Session hoặc `ConnectionFactory` để kiểm thử converter Spring Messaging. Đây là lý do nên giữ tầng chung tách biệt khỏi hạ tầng vận chuyển.

### 10.2. Unit test JMS converter

Để test `toMessage`/`fromMessage` JMS, có thể dùng:

- JMS `Session` mock/stub phù hợp với converter cần test; tránh mock một phần không đủ các API tạo message.
- Provider embedded/test broker nếu cần kiểm tra `TextMessage`/`BytesMessage` thật.
- Assertions về JMS message class, body, custom properties và round trip.

Không dùng `MockHttpServletRequest`, `MessageBuilder` của Spring hay Spring `ConversionService` như một thay thế đương nhiên cho JMS Session: chúng thuộc những contract khác.

### 10.3. Integration test @JmsListener

Khi producer dùng Jackson JMS converter và listener factory dùng converter tương ứng:

1. Provision queue test.
2. Gửi DTO `OrderCreated("ORD-42", 1500)`.
3. Kiểm tra JMS body là JSON text và có property `_type`.
4. Đảm bảo listener nhận DTO đúng, không phải String JSON hay `Map`.
5. Thử thiếu `_type`, unknown type ID, payload sai schema, body null, version lỗi; xác minh policy rollback/handling.
6. Thử idempotency và redelivery để không tạo side effect trùng.

Nếu muốn method-argument converter xử lý JSON, hãy test thêm **content-type mapping** và target class, không chỉ test đơn lẻ JMS converter.

### 10.4. Kiểm tra header mapping

Cho Spring Message có:

```text
payload=ORD-42
headers={eventType=OrderCreated, contentType=application/json}
```

Qua bridge, xác minh ở broker/consumer:

- Custom header `eventType` có được mapping thành JMS property phù hợp không?
- `contentType` có được giữ hoặc chuyển thành property nào theo mapper đang dùng?
- `JMSCorrelationID` có được map đúng nếu yêu cầu request/reply không?
- Có header nào bị bỏ do tên không hợp lệ/giá trị không được JMS property hỗ trợ?
- `MessageHeaders.ID` và `TIMESTAMP` có được sinh mới khác với `JMSMessageID` và `JMSTimestamp` không?

**Không so sánh toàn bộ Spring headers và JMS headers bằng object equality.** Chỉ so sánh các trường đã được hợp đồng quy định, bởi JMS và Spring có header semantics khác nhau.

## 11. Java 17 chạy độc lập: mô phỏng hai bước chuyển đổi

Ví dụ sau dùng **chỉ JDK 17**, mô phỏng pipeline “application envelope → wire message → application envelope → typed method argument”. Nó không implement các interface thật, không tạo `Session` và không gọi broker; mục tiêu là minh họa **ranh giới dữ liệu**, không giả vờ thay thế Spring JMS.

Tạo tệp **`ConverterBoundaryDemo.java`**:

```java
import java.util.Map;

public final class ConverterBoundaryDemo {

    record SpringEnvelope(
            String payload, Map<String, String> headers) {}

    record WireText(
            String body, Map<String, String> properties) {}

    static WireText toWire(SpringEnvelope springMessage) {
        return new WireText(
                "v1:" + springMessage.payload(),
                Map.of("eventType",
                       springMessage.headers().getOrDefault(
                               "eventType", "UNKNOWN")));
    }

    static SpringEnvelope fromWire(WireText wire) {
        if (!wire.body().startsWith("v1:")) {
            throw new IllegalArgumentException("Unsupported wire format");
        }
        return new SpringEnvelope(
                wire.body().substring(3),
                Map.of("eventType",
                       wire.properties().getOrDefault(
                               "eventType", "UNKNOWN")));
    }

    static Integer toMethodArgument(SpringEnvelope message) {
        // Mô phỏng conversion payload String sang target Integer.
        return Integer.valueOf(message.payload());
    }

    public static void main(String[] args) {
        SpringEnvelope original = new SpringEnvelope(
                "42", Map.of("eventType", "NUMBER"));

        WireText wire = toWire(original);
        SpringEnvelope restored = fromWire(wire);
        Integer argument = toMethodArgument(restored);

        System.out.println("Wire body: " + wire.body());
        System.out.println("Wire property: "
                + wire.properties().get("eventType"));
        System.out.println("Spring payload: " + restored.payload());
        System.out.println("Method argument: " + argument);
    }
}
```

Lệnh:

```bash
javac ConverterBoundaryDemo.java
java ConverterBoundaryDemo
```

**Stdout chính xác:**

```text
Wire body: v1:42
Wire property: NUMBER
Spring payload: 42
Method argument: 42
```

Ý nghĩa:

- `toWire` và `fromWire` đại diện thao tác kiểu **JMS converter/bridge**: biết wire body, properties.
- `toMethodArgument` đại diện **Spring Messaging converter**: chỉ quan tâm payload và kiểu tham số đích.
- Dù giá trị in ra có vẻ giống nhau, type và thời điểm xử lý khác nhau.
- Code không mô phỏng MessageHeaders/JmsHeaderMapper đầy đủ, broker ack/transaction, error conversion contract hay target MIME. Cần test integration trên Spring/JMS thật.

## 12. Vì sao nhiều converter cùng tên dễ gây bug?

### 12.1. IDE tự import nhầm MessageConverter

```java
// Sai package cho JmsTemplate:
import org.springframework.messaging.converter.MessageConverter;

// Đúng package cho JmsTemplate:
import org.springframework.jms.support.converter.MessageConverter;
```

Khi file cần cả hai type, sử dụng fully-qualified name trong khai báo biến hoặc tách class config; Java **không có import alias**:

```java
org.springframework.messaging.converter.MessageConverter general;
org.springframework.jms.support.converter.MessageConverter jmsSpecific;
```

Nếu compile lỗi `incompatible types`, hãy kiểm tra fully-qualified types **trước khi** thử cast. Không thể ép kiểu giữa hai interface không có quan hệ chỉ vì tên giống nhau.

### 12.2. IDE tự import nhầm MappingJackson2MessageConverter

```text
org.springframework.jms.support.converter.MappingJackson2MessageConverter
org.springframework.messaging.converter.MappingJackson2MessageConverter
```

- JMS variant có `setTargetType(MessageType.TEXT)`, `setTypeIdPropertyName(...)`; dùng để tạo JMS TextMessage/BytesMessage.
- Messaging variant làm việc với `org.springframework.messaging.Message<?>`, target type và MIME. Nó **không dùng JMS Session** và không thể đưa trực tiếp vào `JmsTemplate.setMessageConverter`.

Nếu thấy method `setTypeIdPropertyName` không tồn tại, có thể bạn đã import nhầm Spring Messaging converter. Nếu thấy `toMessage(Object, Session)` không có, có thể tương tự.

### 12.3. “Đã set converter trên JmsTemplate nhưng @JmsListener vẫn nhận String”

Không chắc converter setter trên sender được dùng ở receiver. Listener có adapter/container và converter riêng. Hãy kiểm tra bean `DefaultJmsListenerContainerFactory`, `containerFactory` annotation, và converter đang được inject vào listener.

### 12.4. “Đã set GenericMessageConverter nhưng DTO vẫn thành ObjectMessage”

Đó là hai pipeline khác nhau. Spring Messaging Generic converter không phải JMS wire serializer. Nếu dùng `JmsTemplate.convertAndSend(dto)`, wire output phụ thuộc **JMS-specific converter của JmsTemplate**, có thể là SimpleMessageConverter, không phụ thuộc generic converter ở handler method factory.

### 12.5. “Jackson JMS converter không đọc được JSON vừa gửi”

JMS Jackson converter có **type-id** và body type cần cấu hình nhất quán. Theo Spring 6 JMS Jackson converter, thiếu `setTypeIdPropertyName` có thể không biết chuyển message về Java class nào. Kiểm tra `_type` property, mapping và version. Không tự gán Java class name từ external input thành type an toàn.

### 12.6. “Spring Message header giống hệt JMS property”

Không. `MessageHeaders.ID/TIMESTAMP` của Spring được tạo theo Spring Message lifecycle, khác `JMSMessageID/JMSTimestamp`; `JmsHeaderMapper` định nghĩa ánh xạ. JMS property chỉ cho phép các tên/kiểu nhất định, nên custom header phức tạp có thể không roundtrip.

### 12.7. “Bật contentType=application/json là record tự biến JSON”

Không. Header chỉ giúp converter chọn representation. Cần converter JSON phù hợp, schema, type mapping và receiver target type. Không thể giao việc chuyển đổi payload cho một header đơn độc.

### 12.8. “Có thể coi Null converter result như payload rỗng”

Không. Spring Messaging MessageConverter có thể trả `null` khi không hỗ trợ. JMS converter có thể ném `MessageConversionException`. Nếu conversion không được hỗ trợ, cần fail rõ ràng thay vì âm thầm phát message rỗng.

### 12.9. “@JmsListener luôn gọi converter dù tham số raw JMS Message”

Không đúng. Khi handler nhận raw `jakarta.jms.Message`, nó có thể được cung cấp trực tiếp theo infrastructure, giúp application tự đọc headers/body. Không suy ra typed payload converter chắc chắn chạy trong mọi chữ ký.

### 12.10. “Cùng class DTO Java là đủ để hai service tương thích”

Không đủ. Wire contract còn gồm field name, encoding, JSON version, target JMS message type, type-id metadata, backward compatibility, null handling và schema validation. Consumer version khác có thể lỗi dù cùng class name logic.

## 13. Lựa chọn converter theo use case

| Nhu cầu | Lựa chọn gợi ý | Vì sao |
| --- | --- | --- |
| String/byte[]/MapMessage đơn giản qua JMS | JMS `SimpleMessageConverter` | Ít cấu hình, xử lý trực tiếp JMS body |
| DTO JSON gửi bằng `JmsTemplate.convertAndSend` | JMS Jackson converter với type-id/schema | Cần Java ↔ Text/BytesMessage rõ ràng |
| Handler method chuyển String → Integer, Date… | Spring Messaging `GenericMessageConverter` + `ConversionService` | Có targetClass từ method argument |
| Cần content type JSON/byte[] chung cho messaging channels | Spring Messaging JSON converter | Không phụ thuộc JMS Session |
| Gửi Spring `Message<?>` có headers qua JMS | `JmsMessagingTemplate` + `MessagingMessageConverter` bridge | Phân tách Spring envelope với JMS wire representation |
| Cần convert JMS body và headers riêng | JMS `MessagingMessageConverter` với payloadConverter/HeaderMapper | Tùy biến boundary, không viết lại toàn bộ JMS API |
| Đọc raw JMS headers/body, không chuyển payload | `@JmsListener` nhận `jakarta.jms.Message` hoặc raw listener | Giữ quyền kiểm soát provider-specific data |
| Nhiều hệ thống/ngôn ngữ cùng tiêu thụ | JSON/Avro/Protobuf có schema/version rõ | Không dựa vào Java ObjectMessage serialization |

**Chọn converter ở đúng tầng, không theo tên class quen thuộc.** Một Spring app có thể đồng thời dùng JMS-specific converter cho wire, Spring Messaging converter cho method payload và mapper cho headers. Đây là bình thường, miễn trách nhiệm mỗi tầng được xác định.

## 14. Reliability và bảo mật của conversion

Converter không quyết định cơ chế routing hay bảo đảm exactly-once. Nó chỉ quyết định biểu diễn payload/headers.

### 14.1. Conversion failure và transaction

Nếu listener lấy một JMS message không hợp schema:

1. Broker giao message tới listener.
2. JMS-specific converter cố giải body và thất bại.
3. Handler method có thể **chưa từng được gọi**.
4. Nếu session transacted, exception có thể dẫn tới rollback/redelivery.
5. Message “độc” không sửa được có thể tiếp tục lặp tới khi broker chuyển DLQ theo policy.

Thiết kế retry cho lỗi tạm thời và xử lý DLQ cho lỗi payload/schema cố định. Không retry vô hạn một JSON malformed chỉ vì converter throw; log type-id/schema version và tracking ID đủ chẩn đoán nhưng không lộ dữ liệu nhạy cảm.

### 14.2. Header mapping không phải bypass security

Dù gửi `Spring Message` rồi chuyển headers qua mapper, mọi JMS property vẫn phải tuân thủ quyền broker và naming constraints. Không tin metadata như `sourceSystem`, `userRole` hoặc `tenantId` do sender không xác thực tự đặt, và không dùng chúng làm căn cứ cấp quyền mà không kiểm tra authentication/authorization.

### 14.3. Không mặc định Java object serialization an toàn

`ObjectMessage` có thể khiến receiver deserializes class do input chi phối nếu trust boundary không kiểm soát. Nếu không bắt buộc, dùng JSON/binary schema có validation và allowlist; với type-id mapping, ưu tiên logical ids thay vì mở rộng classloader tùy ý.

### 14.4. Performance và kích thước message

- JSON converter có chi phí parse và allocate object.
- Binary format có thể tiết kiệm băng thông nhưng cần schema và framing.
- Message rất lớn có thể gây broker quota/backpressure; cân nhắc lưu object vào storage và gửi reference/checksum.
- Không cache mutable JMS `Session`/`Message` hoặc chia sẻ giữa threads ngoài quy tắc JMS.
- Converter bean có thể được dùng đồng thời từ nhiều consumer threads: tránh mutable state theo mỗi request trong singleton converter; config một lần rồi reuse một cách thread-safe.

### 14.5. Converters không tự giải quyết schema evolution

Ví dụ chuyển `OrderCreated(orderId)` thành `OrderCreated(orderId, currency)` có thể ảnh hưởng consumer cũ. Xác định version trong body/properties, chính sách backward compatibility, xử lý missing/unknown fields, canary rollout và test producer vNext với consumer vCurrent. Type-id giúp chọn Java class nhưng không tự đảm bảo wire schema ổn định.

## 15. Checklist debugging khi Spring JMS conversion không như mong đợi

1. **Entry point:** gọi `JmsTemplate.convertAndSend`, `JmsMessagingTemplate.convertAndSend`, `JmsMessagingTemplate.send`, `JmsClient`, hay `MessageCreator` raw?
2. **Package:** converter đang được dùng có full name `org.springframework.jms.support.converter...` hay `org.springframework.messaging.converter...`?
3. **Phía producer:** Java payload type gì? Converter nào tạo `TextMessage`/`BytesMessage`? Có type-id/encoding/content-type?
4. **Wire:** broker thấy JMS body class nào, JMS custom properties nào, message headers nào?
5. **Phía consumer:** listener factory nào? JMS-specific converter trên adapter đang là bean nào?
6. **Handler:** method nhận raw JMS Message, Spring Message<?> hay DTO? Có `@Payload`, `@Header` và validator không?
7. **Spring Messaging:** handler factory dùng converter nào? `targetClass` là gì? Có content type và ConversionService tương ứng không?
8. **HeaderMapper:** custom headers có được map qua JMS không, tên/property types có hợp lệ không?
9. **Error:** lỗi là `JMSException`, JMS `MessageConversionException`, Spring Messaging conversion exception hay method argument resolution?
10. **Transaction:** conversion error có rollback/redelivery/DLQ? Có idempotency tránh effect trùng?
11. **Version:** Spring Framework 6.x hay 7.x, Jackson 2 hay 3? API converter variant cần đúng version đang chạy.
12. **Test:** đã có unit test converter ở đúng tầng và integration test thực sự đi qua broker không?

### Ma trận xác định “nên sửa ở đâu”

| Triệu chứng | Đầu mối đúng |
| --- | --- |
| DTO gửi qua `JmsTemplate` bị serialize sai JMS body | JMS converter trên `JmsTemplate` |
| JMS TextMessage JSON nhận mà không thành DTO | JMS listener converter/type-id hoặc Spring Messaging handler converter |
| Spring Message header mất sau send | `MessagingMessageConverter`/`JmsHeaderMapper` và JMS property constraints |
| `@Payload String` cần thành `Integer` | Spring Messaging `ConversionService`/`GenericMessageConverter` |
| Setting converter gây lỗi incompatible types | Nhầm package `MessageConverter` |
| `@JmsListener` không được gọi vì malformed body | JMS transport conversion, exception/retry/DLQ |
| Spring Message<?> gửi nhưng JMS Simple converter không hiểu | Dùng `JmsMessagingTemplate`/`MessagingMessageConverter` bridge |
| Gửi đúng body nhưng sai queue/topic | DestinationResolver/pubSubDomain, **không phải** converter |
| Message đã nhận nhưng nghiệp vụ chạy lặp | Transaction/ack/redelivery/idempotency, **không phải** lỗi converter |

## 16. Bài tập kiểm tra

**Bài 1 — Import diagnosis**

```java
import org.springframework.messaging.converter.GenericMessageConverter;
JmsTemplate template = new JmsTemplate(cf);
template.setMessageConverter(new GenericMessageConverter());
```

Hỏi: code có biên dịch không? Vì sao?

**Đáp án:** Không. `JmsTemplate.setMessageConverter` cần `org.springframework.jms.support.converter.MessageConverter`; `GenericMessageConverter` implements interface của Spring Messaging.

**Bài 2 — JSON type resolution**

Một JMS `MappingJackson2MessageConverter` đã `setTargetType(TEXT)` nhưng không có `setTypeIdPropertyName`. Producer gửi DTO, consumer cố `fromMessage` thành DTO. Cần kiểm tra gì?

**Đáp án:** Cấu hình type-id property và mapping/typing strategy cho chiều nhận; JMS Jackson converter cần metadata để biết class đích theo hợp đồng. Có thể dùng logical type ID và schema version thay vì raw class name.

**Bài 3 — Hai setter JmsMessagingTemplate**

```java
template.setMessageConverter(genericConverter);
template.setJmsMessageConverter(wireBridge);
```

Hỏi: mỗi setter nhận interface nào?

**Đáp án:** `setMessageConverter` nhận `org.springframework.messaging.converter.MessageConverter`; `setJmsMessageConverter` nhận `org.springframework.jms.support.converter.MessageConverter`.

**Bài 4 — Jackson cùng simple name**

Có hai class `MappingJackson2MessageConverter` ở Spring. Hỏi class nào nhận JMS `Session` trong `toMessage`?

**Đáp án:** `org.springframework.jms.support.converter.MappingJackson2MessageConverter`.

**Bài 5 — Header confusion**

`MessageBuilder.withPayload(...).setHeader("eventType","X")` có bảo đảm JMS `JMSPriority` thay đổi?

**Đáp án:** Không. `eventType` chỉ là application header; JMS QoS được cấu hình qua producer/JmsTemplate, không qua custom property.

**Bài 6 — Raw receive**

`JmsTemplate.receive("orders.created")` trả gì, và `receiveAndConvert(...)` trả gì?

**Đáp án:** `receive` trả raw `jakarta.jms.Message` (hoặc null timeout); `receiveAndConvert` trả Java object theo JMS-specific converter. Output type không nhất thiết là DTO nếu converter không được cấu hình.

**Bài 7 — Handler typed parameter**

JMS Simple converter đọc TextMessage JSON ra String, listener nhận `@Payload OrderCreated`. DTO có tự xuất hiện không?

**Đáp án:** Không tự động. Cần Spring Messaging converter cho JSON → target type, đúng content type; hoặc đổi JMS listener converter để ngay tầng wire nhận được DTO.

**Bài 8 — Converter class security**

Vì sao không nên cho untrusted JMS property tự nêu full Java class name để Jackson instantiate class tùy ý?

**Đáp án:** Có rủi ro unsafe polymorphic deserialization/type confusion và coupling; dùng logical type IDs, allowlist mappings, schema validation và quyền broker.

**Bài 9 — MessageBuilder**

`MessageBuilder.withPayload("ORD-42").build()` tạo `jakarta.jms.Message` hay Spring `Message<?>`?

**Đáp án:** Spring `org.springframework.messaging.Message<String>`; muốn gửi JMS qua API Spring Messaging cần bridge/adapter như `JmsMessagingTemplate`.

**Bài 10 — Conversion exception**

JSON malformed khiến JMS converter ném exception trước khi `@JmsListener` chạy. Làm sao xử lý?

**Đáp án:** Theo dõi conversion errors, dùng retry hữu hạn và DLQ, không retry vô hạn; lưu metadata đủ debug, bảo toàn message/payload theo chính sách bảo mật.

**Bài 11 — Spring 6 và Spring 7**

Code copy từ tutorial Spring 6 dùng `MappingJackson2MessageConverter` cho JMS. Có thể giả định mọi version mới đều có đúng class/constructor và Jackson setup như cũ?

**Đáp án:** Không. Phải kiểm tra Javadoc và dependency version chính xác; Spring 7 bổ sung/đổi các adapter liên quan Jackson. **Hợp đồng hai interface vẫn phải được phân biệt**.

**Bài 12 — Exactly once**

Cấu hình JSON converter hoàn hảo có đảm bảo một order event chỉ tạo một bản ghi DB không?

**Đáp án:** Không. Transaction/ack/redelivery và idempotency ở business layer quyết định; conversion không giải quyết at-least-once semantics.

## Tóm tắt ghi nhớ

- **`org.springframework.jms.support.converter.MessageConverter`**: Java object ↔ `jakarta.jms.Message`; cần `Session` để tạo JMS message. `JmsTemplate` và listener factory sử dụng interface này ở ranh giới JMS.
- **`org.springframework.messaging.converter.MessageConverter`**: payload + Spring `Message<?>` ↔ payload kiểu `targetClass`; không cần JMS Session. Được dùng trong Spring Messaging API và method-argument conversion.
- **`MessagingMessageConverter` nằm trong `spring-jms`**: là adapter giúp Spring `Message<?>` đi qua ranh giới JMS; nó dựa vào JMS payload converter và header mapper.
- **`JmsMessagingTemplate` có hai setting converter**: `setMessageConverter` cho generic Spring Messaging; `setJmsMessageConverter` cho JMS bridge.
- **`@JmsListener` có thể trải qua hai tầng**: JMS transport decoding và Spring handler argument conversion, tùy signature/configuration; không mặc định converter nào cũng chạy.
- **`SimpleMessageConverter` và `MappingJackson2MessageConverter` có nhiều lớp trùng simple name**: luôn kiểm tra package import và chữ ký.
- **JSON và headers không tự an toàn/tự tương thích**: thiết kế schema, type-id, content type, property mapping, validation, retry/DLQ và idempotency.

### Tài liệu chính thức

1. [Spring Framework – Sending a Message (JMS Message Converters)](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html): hướng dẫn `JmsTemplate.convertAndSend`, JMS-specific converter và sự phân biệt Spring Messaging converter.
2. [Spring Framework – Annotation-driven JMS Listener](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): signature `@JmsListener`, Spring `Message<?>`, `@Payload`, `@Header` và `DefaultMessageHandlerMethodFactory`.
3. [Spring Framework 6.2 – JMS MessageConverter API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/support/converter/MessageConverter.html): chữ ký `toMessage(Object, Session)`, `fromMessage(jakarta.jms.Message)`.
4. [Spring Framework 6.2 – GenericMessageConverter](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/messaging/converter/GenericMessageConverter.html): conversion theo `targetClass` qua Spring ConversionService.
5. [Spring Framework 6.2 – JMS MessagingMessageConverter](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/support/converter/MessagingMessageConverter.html): adapter Spring Message ↔ JMS Message, payload converter và header mapper.
6. [Spring Framework 6.2 – JmsMessagingTemplate](https://docs.spring.io/spring-framework/docs/6.2.5/javadoc-api/org/springframework/jms/core/JmsMessagingTemplate.html): hai tầng `setMessageConverter` và `setJmsMessageConverter`.
7. [Spring Framework 6.2 – JMS MappingJackson2MessageConverter](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html): JSON, target JMS message type, type-id property và mappings.
8. [Spring Framework 6.2 – DefaultJmsListenerContainerFactory](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html): điểm cấu hình JMS converter của listener.
9. [Spring Framework – Messaging Concepts](https://docs.spring.io/spring-framework/reference/integration/spring-integration.html): Spring Messaging và hướng kiến trúc transport-independent; đối chiếu với JMS adapter.
