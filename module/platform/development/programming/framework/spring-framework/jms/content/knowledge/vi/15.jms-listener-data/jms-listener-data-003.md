# Nhận org.springframework.messaging.Message để đọc payload và header trong Spring JMS

## 1. Mục tiêu và vấn đề thực tế

Trong Spring JMS, listener thường chỉ cần một `String` hoặc DTO từ message body. Tuy nhiên các nghiệp vụ quan trọng cũng cần metadata: `eventType`, `sourceSystem`, `attempt`, `JMSMessageID`, `JMSCorrelationID`, `JMSRedelivered`, v.v. Nếu chỉ viết `@JmsListener public void handle(String body)`, những thông tin đó không nằm trong biến `body`.

Spring cho phép nhận **`org.springframework.messaging.Message<T>`**, một abstraction gồm hai thành phần:

```java
public interface Message<T> {
    T getPayload();
    MessageHeaders getHeaders();
}
```

Cách dùng:

```java
@JmsListener(destination = "orders.in")
public void onOrder(Message<String> message) {
    String body = message.getPayload();
    String eventType =
            message.getHeaders().get("eventType", String.class);
    System.out.println(body + " / " + eventType);
}
```

Các import:

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
```

Đây là method **trong một Spring bean đã được đăng ký**, chưa phải chương trình chạy độc lập. Bài học giải thích cách Spring tạo wrapper `Message<T>`, cách đọc đúng payload/header, phân biệt `JmsHeaders` với `MessageHeaders`, xử lý header thiếu/sai kiểu, và cách chạy một ví dụ Java 17 + Spring Boot + Artemis.

## 2. Đừng nhầm Spring Message với Jakarta JMS Message

Có **hai interface cùng tên `Message`**:

| Đặc điểm | Spring Messaging | Jakarta Messaging |
| --- | --- | --- |
| Tên đầy đủ | `org.springframework.messaging.Message<T>` | `jakarta.jms.Message` |
| API chính | `getPayload()`, `getHeaders()` | `getJMSMessageID()`, `getJMSCorrelationID()`, `getObjectProperty()`... |
| Ý nghĩa | Wrapper chung payload + header | Message native do JMS provider quản lý |
| Kiểu body | Generic `T` sau khi convert | Native body tùy `TextMessage`, `BytesMessage`, `MapMessage`... |
| Lỗi checked | Không cần `JMSException` chỉ để đọc map | Nhiều native getter ném `JMSException` |
| Khi nào dùng | Muốn xử lý payload và mapped headers | Cần header/body API native hoặc thao tác đặc thù JMS |

Spring Message:

```java
@JmsListener(destination = "orders.in")
public void handle(org.springframework.messaging.Message<String> msg) {
    String body = msg.getPayload();
    Object type = msg.getHeaders().get("eventType");
}
```

Native JMS Message:

```java
@JmsListener(destination = "orders.in")
public void handleNative(jakarta.jms.TextMessage msg)
        throws jakarta.jms.JMSException {
    String body = msg.getText();
    String type = msg.getStringProperty("eventType");
}
```

**Không đăng ký cả hai ví dụ vào cùng Queue chỉ để mong một message được giao cho cả hai.** Với Queue, consumer cạnh tranh và một message có thể được một consumer nhận trước consumer khác.

Nếu IDE gợi ý import `jakarta.jms.Message` trong khi code cần `getPayload()`, hãy sửa import thành `org.springframework.messaging.Message`. `org.springframework.messaging.support.GenericMessage<T>` là một implementation của Spring Message dùng để tạo object trong memory; nó không tự là JMS message nằm trên broker.

## 3. Spring chuyển đổi message khi gọi @JmsListener

Đường đi điển hình:

```text
Producer:
  jakarta.jms.TextMessage("ORDER-101")
  JMS property: eventType="ORDER_CREATED"
  JMS header:   JMSCorrelationID="req-101"
                |
                v
          JMS Queue/broker
                |
                v
       Spring listener container
                |
                v
      JMS conversion + header mapping
                |
                v
  org.springframework.messaging.Message<String>
     getPayload() -> "ORDER-101"
     getHeaders() -> {
       eventType: ORDER_CREATED,
       jms_correlationId: req-101,
       jms_messageId: provider-generated ID,
       ...
     }
                |
                v
       @JmsListener method
```

Spring JMS annotated infrastructure hỗ trợ trực tiếp `org.springframework.messaging.Message`, raw `jakarta.jms.Message`, `jakarta.jms.Session`, và các tham số `@Header`, `@Headers`, `@Payload`. Thành phần chuyển đổi payload và mapper như `MessagingMessageConverter`, `SimpleMessageConverter`, `SimpleJmsHeaderMapper` quyết định giá trị thực tế được đưa vào handler.

- Body được convert thành kiểu `T`; với JMS `TextMessage`, cấu hình mặc định thường cho `String`.
- JMS API headers được map sang keys `JmsHeaders`.
- JMS custom properties được map sang header names ứng dụng, ví dụ `eventType`.
- Handler chạy khi adapter có thể resolve/convert các tham số cần thiết.

Lỗi conversion có thể phát sinh **trước khi thân method bắt đầu chạy**. Vì thế `try/catch` trong listener không bắt được mọi lỗi mapping; cần cấu hình error handling và transaction của container.

## 4. Đọc getPayload(): generic có ý nghĩa gì?

`Message<String>` mang payload kiểu `String`; `Message<OrderEvent>` mang payload kiểu `OrderEvent` **nếu converter tạo được object ấy**; `Message<?>` chưa giả định kiểu payload cụ thể.

```java
@JmsListener(destination = "orders.in")
public void handle(Message<String> msg) {
    String body = msg.getPayload();  // không cần cast
    if (body.isBlank()) {
        throw new IllegalArgumentException("Empty order payload");
    }
}
```

Nếu cần nhận nhiều dạng payload trong môi trường được cấu hình thích hợp:

```java
@JmsListener(destination = "mixed.in")
public void handleMixed(Message<?> msg) {
    Object payload = msg.getPayload();
    if (payload instanceof String text) {
        System.out.println("TEXT " + text);
    } else if (payload instanceof byte[] bytes) {
        System.out.println("BYTES " + bytes.length);
    } else {
        System.out.println(payload.getClass().getName());
    }
}
```

Đó là các snippet trong Spring bean, không phải class độc lập. Java 17 hỗ trợ pattern matching `instanceof`. **Generic không phải bộ giải mã JSON**: một `TextMessage` chứa `{"orderId":"A"}` vẫn thường có payload là `String` nếu không cấu hình JSON converter/type mapping. Đừng ép `(OrderEvent) msg.getPayload()` chỉ vì body nhìn giống JSON.

## 5. Đọc getHeaders() và phương thức lấy header

`MessageHeaders` chứa key–value metadata. Đọc như Map:

```java
MessageHeaders h = incoming.getHeaders();

Object raw = h.get("eventType");
String type = h.get("eventType", String.class);
Integer attempt = h.get("attempt", Integer.class);

java.util.UUID springId = h.getId();
Long springTimestamp = h.getTimestamp();
```

Snippet chạy trong method có `incoming: Message<?>`. `get(name, Class<T>)` giúp yêu cầu đúng kiểu, **không phải** một bộ chuyển đổi String sang Integer tùy ý. Nếu producer đặt `setStringProperty("attempt", "1")`, đừng suy rằng `h.get("attempt", Integer.class)` tự parse thành `1`.

Header có thể thiếu; trước khi dùng một key không bắt buộc:

```java
String correlationId = h.get(
        JmsHeaders.CORRELATION_ID, String.class);
if (correlationId == null || correlationId.isBlank()) {
    System.out.println("No JMS correlation ID");
}
```

`JmsHeaders` thuộc `org.springframework.jms.support.JmsHeaders` và xác định **tên key** chuẩn mà mapper sử dụng. Custom header thường dùng đúng tên property do producer đặt. Tên custom property có phân biệt chữ hoa/chữ thường.

### Không in toàn bộ header map trong production

Header có thể chứa định danh khách hàng, request ID, token hoặc dữ liệu nhạy cảm tùy ứng dụng. Chỉ log whitelist metadata an toàn, che hoặc băm identifier khi cần. `h.keySet()` giúp debug tên key, nhưng vẫn cần quy tắc vận hành phù hợp.

## 6. Các hằng số JmsHeaders quan trọng

```java
import org.springframework.jms.support.JmsHeaders;
```

| Key | Nguồn từ JMS | Điều nên nhớ |
| --- | --- | --- |
| `JmsHeaders.MESSAGE_ID` | `getJMSMessageID()` | Native JMS ID, thường là String provider tạo. |
| `JmsHeaders.CORRELATION_ID` | `getJMSCorrelationID()` | String dùng trong request–reply/correlation, có thể null. |
| `JmsHeaders.REDELIVERED` | `getJMSRedelivered()` | Boolean, phản ánh JMS redelivery flag. |
| `JmsHeaders.PRIORITY` | `getJMSPriority()` | Numeric, không phải business priority tùy ý. |
| `JmsHeaders.DESTINATION` | `getJMSDestination()` | Destination được provider xác định. |
| `JmsHeaders.REPLY_TO` | `getJMSReplyTo()` | Destination response, có thể vắng. |
| `JmsHeaders.TYPE` | `getJMSType()` | JMS type label, có thể vắng. |
| `JmsHeaders.TIMESTAMP` | `getJMSTimestamp()` | Native timestamp, phân biệt Spring timestamp. |
| `JmsHeaders.EXPIRATION` | `getJMSExpiration()` | JMS expiration timestamp, nếu có. |
| `JmsHeaders.DELIVERY_MODE` | `getJMSDeliveryMode()` | Persistent/nonpersistent theo JMS API. |

Không ép `DESTINATION` hay `REPLY_TO` thành String khi chưa kiểm tra: mapped value có thể là object `jakarta.jms.Destination`. Nhiều header chuẩn là read-only ở chiều outbound, do broker/provider gán khi gửi; header mapper còn có thể được tùy biến.

Ví dụ:

```java
String jmsId = h.get(JmsHeaders.MESSAGE_ID, String.class);
String correlation = h.get(
        JmsHeaders.CORRELATION_ID, String.class);
Boolean redelivered = h.get(
        JmsHeaders.REDELIVERED, Boolean.class);
```

Nếu muốn đọc priority, dùng `Integer` khi mapper cung cấp kiểu số tương ứng; trong môi trường mapper riêng, kiểm tra `Object` trước khi cast.

## 7. Đừng nhầm ID và timestamp của Spring với JMS

```java
java.util.UUID springId = incoming.getHeaders().getId();
String jmsMessageId = incoming.getHeaders().get(
        JmsHeaders.MESSAGE_ID, String.class);

Long springTimestamp = incoming.getHeaders().getTimestamp();
Object jmsTimestamp = incoming.getHeaders().get(
        JmsHeaders.TIMESTAMP);
```

Hai ID không tương đương:

- `MessageHeaders.ID`: định danh của Spring Message envelope (thường là UUID), có thể thay đổi khi tạo wrapper mới.
- `JmsHeaders.MESSAGE_ID`: native `JMSMessageID` được provider cấp cho lần gửi JMS.
- `JmsHeaders.CORRELATION_ID`: correlation ID do producer hoặc contract request–reply quyết định, **không mặc định bằng hai ID trên**.

Tương tự, `MessageHeaders.TIMESTAMP` thường mô tả thời điểm tạo Spring Message, còn `JmsHeaders.TIMESTAMP` là native `JMSTimestamp`. Khi đo độ trễ, phải xác định đúng mốc cần dùng.

Một log khái niệm:

```text
springId=<UUID của Spring wrapper>
jmsId=<ID do JMS provider cấp>
correlationId=req-101
```

Các placeholder trong block này mô tả **loại giá trị**, không phải dữ liệu cần điền vào code. Không lấy `MessageHeaders.ID` làm bằng chứng đã ACK một JMS message hay business event ID duy nhất khi retry.

## 8. Custom JMS properties: dữ liệu ngoài body

Producer có thể gắn property lên native JMS message:

```java
jmsTemplate.send("orders.in", session -> {
    TextMessage msg = session.createTextMessage("ORDER-101");
    msg.setStringProperty("eventType", "ORDER_CREATED");
    msg.setStringProperty("sourceSystem", "checkout");
    msg.setIntProperty("attempt", 1);
    msg.setBooleanProperty("urgent", false);
    msg.setJMSCorrelationID("req-101");
    return msg;
});
```

Đây là snippet trong method đã inject `JmsTemplate`, cần import `jakarta.jms.TextMessage`. `setJMSCorrelationID` là cách thiết lập **JMS standard header**; `setStringProperty("eventType", ...)` tạo **custom JMS property**.

Listener đọc:

```java
@JmsListener(destination = "orders.in")
public void handle(Message<String> incoming) {
    MessageHeaders h = incoming.getHeaders();
    String eventType = h.get("eventType", String.class);
    Integer attempt = h.get("attempt", Integer.class);
    Boolean urgent = h.get("urgent", Boolean.class);
    String correlation = h.get(
            JmsHeaders.CORRELATION_ID, String.class);
}
```

Những tên như `eventType` phải chính xác, `eventtype` là key khác. Body JSON có một field `"eventType"` **không tự tạo JMS property** để Spring map thành header.

### Property dùng trong selector

```java
@JmsListener(
        destination = "orders.in",
        selector = "eventType = 'ORDER_CREATED' AND attempt >= 1")
public void onCreated(Message<String> incoming) {
    // ...
}
```

Selector được áp dụng ở JMS consumer và xét JMS metadata có sẵn **trước** lúc Spring tạo `Message<T>`. JMS selector không truy cập Spring UUID và không tự parse JSON body. Property `attempt` nên được set bằng `setIntProperty` nếu selector cần so sánh số; `setStringProperty("attempt", "1")` không tương đương.

## 9. Ví dụ chạy được: Java 17 + Spring Boot + Artemis

Ví dụ sau gửi `TextMessage` có payload `"ORDER-101"`, custom properties `eventType`, `attempt`, `sourceSystem`, cùng `JMSCorrelationID`; sau đó `@JmsListener(Message<String>)` đọc lại những giá trị ấy qua Spring Messaging API.

Môi trường: Java 17, Spring Boot 3.3.13, Gradle 8.x tương thích, broker Apache ActiveMQ Artemis ở `localhost:61616`. Tên Queue: `demo.spring.headers`. Giả định broker cho phép auto-create Queue hoặc Queue đã được provision. Chỉ có một listener nhận Queue này.

### 9.1. Khởi động Artemis

Nếu có Docker:

```bash
docker run --detach --rm --name artemis-spring-headers -p 61616:61616 -e ARTEMIS_USER=demo -e ARTEMIS_PASSWORD=demo apache/artemis:2.57.0-alpine
```

Đợi broker sẵn sàng, kiểm tra `docker logs artemis-spring-headers`. Cổng `61616` dành cho JMS client. User/password `demo` chỉ dùng local; môi trường thật phải có quyền send/consume và cấu hình bảo mật/TLS phù hợp. Sau khi học xong: `docker stop artemis-spring-headers`.

### 9.2. Cấu trúc dự án

```text
spring-headers-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/jms/
    │   ├── SpringHeadersApplication.java
    │   └── HeadersListener.java
    └── resources/application.yml
```

Tệp `settings.gradle`:

```groovy
rootProject.name = 'spring-headers-demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories { mavenCentral() }

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
```

Tệp `src/main/resources/application.yml`:

```yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
    password: demo
  jms:
    pub-sub-domain: false
```

### 9.3. Gửi message có đầy đủ metadata

`src/main/java/demo/jms/SpringHeadersApplication.java`:

```java
package demo.jms;

import jakarta.jms.TextMessage;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
@EnableJms
public class SpringHeadersApplication {

    public static void main(String[] args) {
        SpringApplication.run(SpringHeadersApplication.class, args);
    }

    @Bean
    ApplicationRunner sendSample(JmsTemplate jmsTemplate) {
        return args -> {
            jmsTemplate.send("demo.spring.headers", session -> {
                TextMessage msg =
                        session.createTextMessage("ORDER-101");
                msg.setStringProperty(
                        "eventType", "ORDER_CREATED");
                msg.setStringProperty(
                        "sourceSystem", "checkout");
                msg.setIntProperty("attempt", 1);
                msg.setJMSCorrelationID("req-101");
                return msg;
            });
            System.out.println("SENT ORDER-101");
        };
    }
}
```

`ApplicationRunner` chạy sau khi Spring Boot khởi động; `JmsTemplate.send` dùng `Session` để tạo TextMessage và gửi qua provider. JMSMessageID được provider cấp, không phải ID do ứng dụng tự tạo trong Spring envelope.

### 9.4. Nhận Spring Message<String> trong listener

`src/main/java/demo/jms/HeadersListener.java`:

```java
package demo.jms;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.support.JmsHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.stereotype.Component;

@Component
public class HeadersListener {

    @JmsListener(destination = "demo.spring.headers")
    public void handle(Message<String> incoming) {
        String body = incoming.getPayload();
        MessageHeaders h = incoming.getHeaders();

        String type = h.get("eventType", String.class);
        String source = h.get("sourceSystem", String.class);
        Integer attempt = h.get("attempt", Integer.class);
        String correlation =
                h.get(JmsHeaders.CORRELATION_ID, String.class);
        String nativeId =
                h.get(JmsHeaders.MESSAGE_ID, String.class);

        if (!"ORDER_CREATED".equals(type) ||
                attempt == null || attempt < 1) {
            throw new IllegalArgumentException(
                    "Unexpected event metadata");
        }

        System.out.printf(
                "RECEIVED body=%s type=%s source=%s " +
                "attempt=%d correlation=%s idPresent=%s%n",
                body, type, source, attempt, correlation,
                nativeId != null && !nativeId.isBlank()
        );
    }
}
```

Điểm cần nhớ: `HeadersListener` **không import `jakarta.jms.Message`** vì tham số đầu vào là Spring `Message<String>`. Các header chuẩn đọc qua `JmsHeaders`, custom properties đọc qua tên `eventType`, `sourceSystem`, `attempt`.

### 9.5. Chạy và giải thích output

Từ thư mục chứa `build.gradle`:

```bash
gradle bootRun
```

Nếu dùng Gradle Wrapper: Linux/macOS `./gradlew bootRun`, Windows `gradlew.bat bootRun`.

Với broker sạch, Queue tồn tại/được tạo hợp lệ, consumer duy nhất và không có lỗi conversion, có thể thấy:

```text
SENT ORDER-101
RECEIVED body=ORDER-101 type=ORDER_CREATED source=checkout attempt=1 correlation=req-101 idPresent=true
```

Hai dòng trên **có thể đổi thứ tự**, vì listener chạy bất đồng bộ. Broker có thể trả header khác tùy policy; đây là **output dự kiến trong điều kiện phù hợp**, không phải kết quả một lần chạy Artemis đã được thực hiện khi biên soạn. Tránh suy từ `idPresent=true` rằng business transaction hay ACK đã hoàn tất.

Nếu broker giữ các message từ lần chạy cũ, có thêm consumer cạnh tranh, auto-create Queue bị tắt hoặc user thiếu quyền, output khác hoặc startup/send có thể lỗi. Xóa backlog thử nghiệm bằng công cụ broker một cách có kiểm soát, không xóa Queue production.

## 10. @Header, @Headers và @Payload: khi nào không cần cả Message<T>?

Spring có các dạng method signature thay thế.

### @Header cho một metadata

```java
@JmsListener(destination = "orders.in")
public void handle(
        @Payload String orderId,
        @Header("eventType") String eventType,
        @Header(name = JmsHeaders.CORRELATION_ID,
                required = false) String correlationId) {
    System.out.println(orderId + "/" + eventType);
}
```

Các import: `org.springframework.messaging.handler.annotation.Payload`, `org.springframework.messaging.handler.annotation.Header`, và `JmsHeaders`. Tham số `@Header` mặc định required; nếu header vắng có thể gây lỗi resolution. Với `required=false`, handler cần sẵn sàng nhận `null`.

### @Headers cho Map

```java
@JmsListener(destination = "orders.in")
public void inspect(
        @Payload String body,
        @Headers java.util.Map<String, Object> headers) {
    Object type = headers.get("eventType");
    Object id = headers.get(JmsHeaders.MESSAGE_ID);
}
```

Cần import `org.springframework.messaging.handler.annotation.Headers`. `@Headers` nhận Map các giá trị đã được mapper cung cấp, không phải toàn bộ broker internal metadata.

So sánh:

| Nhu cầu | Chữ ký |
| --- | --- |
| Chỉ cần nội dung | `String body` |
| Payload và một property | `String body, @Header("eventType") String type` |
| Payload và nhiều header | `Message<String> incoming` |
| Không biết các header nào có mặt | `@Headers Map<String,Object> headers` |
| Native JMS getter hoặc Session | `jakarta.jms.TextMessage`, `jakarta.jms.Session` |

Các snippet ở mục này là **các lựa chọn thay thế**, không đăng ký cùng một Queue trong demo để tránh consumer cạnh tranh.

## 11. Nhận DTO qua Message<OrderEvent> và converter

Spring reference cho phép listener có chữ ký `Message<OrderEvent>`:

```java
@JmsListener(destination = "orders.events")
public void onOrder(Message<OrderEvent> message) {
    OrderEvent order = message.getPayload();
    String eventType = message.getHeaders().get(
            "eventType", String.class);
}
```

Nhưng cần ứng dụng định nghĩa `OrderEvent` và cấu hình converter để biến JMS body thành DTO. Nếu producer chỉ gửi một JSON String trong TextMessage, kiểu generic **không** làm JSON tự deserialize.

Một cấu hình JSON converter có thể dùng:

```java
@Bean
public MappingJackson2MessageConverter jmsMessageConverter() {
    var converter = new MappingJackson2MessageConverter();
    converter.setTargetType(MessageType.TEXT);
    converter.setTypeIdPropertyName("_type");
    return converter;
}
```

Đây là method trong `@Configuration`, cần import `@Bean`, `MappingJackson2MessageConverter` và `MessageType` từ `org.springframework.jms.support.converter`, cùng dependency Jackson cần thiết. Converter phải được liên kết với đúng `JmsTemplate` và listener factory (Boot-configured hoặc custom) và producer–consumer phải thống nhất type id. Với custom factory, không mặc định rằng chỉ khai báo bean đã đủ.

Nếu conversion thất bại trước method invocation, cần error handler, transaction/rollback và DLQ phù hợp. Khi mới debug type mapping, dùng `Message<String>` để quan sát JSON raw trước khi đổi sang DTO.

## 12. Đọc header sai kiểu và thiếu header

Những trường hợp phổ biến:

- Producer không gắn `JMSCorrelationID`: `JmsHeaders.CORRELATION_ID` có thể null.
- Header custom `"attempt"` do producer gắn thành String `"1"`: không nên đọc bằng `Integer.class` khi chưa chuyển đổi đúng contract.
- Dữ liệu chỉ có trong JSON body: `headers.get("eventType")` có thể null.
- Mapper bị tùy chỉnh inbound prefix hoặc whitelist: một key có thể khác mặc định.
- Một số native JMS headers có kiểu `Destination` hoặc provider-specific type: không ép hết thành `String`.

Mẫu kiểm tra kiểu:

```java
Object attemptValue = incoming.getHeaders().get("attempt");

if (attemptValue instanceof Number n && n.intValue() > 0) {
    int attempt = n.intValue();
    System.out.println(attempt);
} else {
    throw new IllegalArgumentException(
            "Missing or invalid numeric attempt");
}
```

Đây là snippet trong method có `incoming: Message<?>`. Java 17 hỗ trợ `instanceof Number n`. Nếu schema thực sự cho phép String `"1"`, phải parse riêng và kiểm tra lỗi chứ không suy rằng getter typed tự parse.

## 13. MessageHeaders bất biến và MessageBuilder

Spring `MessageHeaders` cung cấp Map API để **đọc**, nhưng không nên gọi:

```java
incoming.getHeaders().put("validated", true);
```

Đây **không** phải cách sửa JMS message đã nhận; cấu trúc headers của Spring Message được xem là immutable. Khi cần một **Spring Message mới** có thêm metadata, dùng:

```java
Message<String> enriched = MessageBuilder
        .fromMessage(incoming)
        .setHeader("validated", true)
        .build();
```

Cần import `org.springframework.messaging.support.MessageBuilder`, trong method có `incoming: Message<String>`. Nó tạo wrapper mới ở tầng ứng dụng, **không** sửa message đang tồn tại trên broker và **không** ACK message.

Nếu trả về `Message<R>` từ `@JmsListener` và cấu hình response destination như `@SendTo` hoặc `JMSReplyTo`, Spring có thể tạo reply. Nhưng đó là đường gửi response riêng; các header read-only như JMSMessageID, priority, expiration không phải cứ đưa vào MessageBuilder là broker buộc dùng làm native outbound values. Cấu hình JMS producer/template QoS khi cần priority/TTL thực tế.

## 14. Cơ chế ACK, transaction và lỗi conversion

Chữ ký `@JmsListener(Message<String>)` không đổi trách nhiệm acknowledgment:

- Container tạo/lấy JMS Session, MessageConsumer rồi gọi listener.
- Container và transaction manager quyết định ACK/commit/rollback.
- `getPayload()` và `getHeaders()` **không phải** lệnh acknowledge.
- Spring `Message<T>` không có `message.acknowledge()` như native JMS Message.
- Nếu conversion lỗi trước method, exception được container xử lý theo cấu hình, không đi qua `try/catch` đặt trong thân listener.

Với locally transacted session, exception từ handler có thể dẫn đến rollback và broker redelivery; với non-transacted `AUTO_ACKNOWLEDGE`, **không được giả định** sẽ redeliver khi listener ném exception. Một handler bắt lỗi, log rồi return bình thường có thể khiến container coi lượt nhận thành công và commit.

```java
@JmsListener(destination = "orders.in")
public void handle(Message<String> message) {
    String type = message.getHeaders().get(
            "eventType", String.class);

    if (!"ORDER_CREATED".equals(type)) {
        throw new IllegalArgumentException(
                "Unexpected eventType: " + type);
    }

    processOrder(message.getPayload());
}
```

`processOrder` là method nghiệp vụ do ứng dụng cung cấp, không thuộc snippet độc lập. Nếu có DB update, local JMS transaction không tự tạo XA transaction với DB. Cần idempotent consumer, business event ID, retry/DLQ và transaction boundary rõ ràng.

## 15. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `getPayload()` không compile | Import nhầm `jakarta.jms.Message`. | Dùng `org.springframework.messaging.Message<T>`. |
| `getJMSMessageID()` không compile | Spring Message không có native JMS getter. | `getHeaders().get(JmsHeaders.MESSAGE_ID)`. |
| `headers.get("eventType") == null` | Producer chưa gắn property, hoặc key sai case. | Set JMS property và kiểm tra mapper. |
| `JmsHeaders.CORRELATION_ID` null | Producer không set JMSCorrelationID. | Xem contract, cho phép optional nếu cần. |
| UUID Spring khác JMS ID | Hai ID khác mục đích. | Tách `MessageHeaders.ID` và `JmsHeaders.MESSAGE_ID`. |
| `Message<OrderEvent>` không nhận DTO | Chưa có converter/type mapping. | Thiết lập JSON converter và schema. |
| `get("attempt", Integer.class)` lỗi | Producer dùng String property hoặc mapper khác. | Kiểm tra `get("attempt")`, sửa property type. |
| Thêm header bằng `put` không hoạt động | Headers của Spring Message immutable. | Dùng `MessageBuilder` tạo object mới. |
| Listener không được gọi dù broker có message | Selector, consumer cạnh tranh, conversion lỗi, ACL hoặc sai destination. | Kiểm tra broker, selector, converter, logs. |
| Error handler bị gọi liên tục | Poison message/transaction rollback và redelivery. | Retry policy, DLQ/quarantine, xử lý lỗi vĩnh viễn. |
| Log chứa mọi header và bị lộ dữ liệu | Dump map không lọc metadata. | Chỉ log header an toàn, redaction. |
| `redelivered=false` nhưng có duplicate nghiệp vụ | Producer retry hoặc failure giữa DB/JMS commit. | Business event ID + idempotency. |

Một quy trình debug hiệu quả: xác nhận đúng import; in header key names an toàn; kiểm tra producer setter `setJMSCorrelationID` và `setXxxProperty`; so Spring UUID với JMS ID; xem converter và Queue/Topic/selector; kiểm tra transaction, redelivery, DLQ khi có lỗi.

## 16. Kiểm thử và câu hỏi tự luyện

### Unit test trong memory

```java
Message<String> message = MessageBuilder
        .withPayload("ORDER-101")
        .setHeader("eventType", "ORDER_CREATED")
        .setHeader("attempt", 1)
        .setHeader(JmsHeaders.CORRELATION_ID, "req-101")
        .build();

String body = message.getPayload();
String eventType = message.getHeaders().get(
        "eventType", String.class);
Integer attempt = message.getHeaders().get(
        "attempt", Integer.class);
```

Đây là snippet dùng Spring Messaging và `MessageBuilder`, **không phải integration test broker**. Nó giúp kiểm tra logic xử lý map headers nhưng không chứng minh JMS header mapper hoạt động qua mạng.

### Integration test với Artemis

1. Gửi TextMessage có payload `"ORDER-101"`, custom `eventType`/numeric `attempt`, `JMSCorrelationID`.
2. Kiểm tra listener `Message<String>` nhận đúng body, custom property và `JmsHeaders.CORRELATION_ID`.
3. Kiểm tra `JmsHeaders.MESSAGE_ID` có mặt, khác Spring `headers.getId()`.
4. Thử thiếu correlation ID để chắc chắn handler không gặp NullPointerException.
5. Thử String property `"attempt"="1"` và kiểm tra typed header access xử lý sai schema đúng cách.
6. Thử JSON DTO với converter cấu hình riêng và xác minh conversion failure trước method.
7. Test rollback/redelivery khi handler ném lỗi trong session transacted, không lấy `JMSRedelivered` làm event ID.
8. Test trên Queue sạch, consumer duy nhất, không assert thứ tự log giữa publisher và listener.

### Câu hỏi

**1.** Tại sao `org.springframework.messaging.Message<String>` có `getPayload()` mà `jakarta.jms.Message` không có cùng method? — **Vì đó là hai interface khác nhau**, Spring dùng abstraction payload/header, Jakarta JMS dùng native message/body API.

**2.** `getHeaders().getId()` có phải `JMSMessageID` không? — **Không**. Đọc `JmsHeaders.MESSAGE_ID` để lấy native JMS message ID.

**3.** Field `eventType` trong JSON body có tự trở thành JMS header không? — **Không**. Cần JMS property hoặc mapping custom rõ ràng.

**4.** Vì sao `Message<OrderEvent>` không tự chuyển JSON thành DTO? — **Generic type không thay thế converter**. Phải cấu hình payload converter/type/schema.

**5.** Đọc `getPayload()` có ACK message chưa? — **Không**. Container/Session/transaction policy quản lý xác nhận và commit.

**6.** Nếu chỉ cần một header, API nào gọn hơn? — `@Header("eventType")`, kết hợp payload argument; header có thể đặt `required=false` khi không bắt buộc.

**7.** Tại sao không dùng `incoming.getHeaders().put(...)`? — Headers được xem là immutable. Dùng `MessageBuilder.fromMessage(...).setHeader(...).build()` để tạo Spring Message mới.

## 17. Tài liệu chính thức và kết luận

- [Spring Framework – Annotation-driven Listener Endpoints: hỗ trợ Message<T>](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html)
- [Spring Framework – JMS Message Listener](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html)
- [Spring Framework 6.2 – Spring Message<T>](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/messaging/Message.html)
- [Spring Framework 6.2 – MessageHeaders](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/messaging/MessageHeaders.html)
- [Spring Framework 6.2 – JmsHeaders](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/support/JmsHeaders.html)
- [Spring Framework 6.2 – SimpleJmsHeaderMapper](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/support/SimpleJmsHeaderMapper.html)
- [Spring Framework 6.2 – MessagingMessageConverter](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/support/converter/MessagingMessageConverter.html)
- [Spring Boot – Messaging with JMS](https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html)
- [Apache Artemis – Official Docker Images](https://artemis.apache.org/components/artemis/documentation/latest/docker.html)

**Kết luận:** Khi cần cả nội dung và metadata trong `@JmsListener`, nhận `org.springframework.messaging.Message<T>`; `getPayload()` cho payload đã được chuyển đổi, `getHeaders()` cho các headers và JMS properties đã ánh xạ. Dùng `JmsHeaders` cho native JMS fields, phân biệt `MessageHeaders.ID` với `JmsHeaders.MESSAGE_ID`, và cấu hình converter/transaction theo contract thực tế.
