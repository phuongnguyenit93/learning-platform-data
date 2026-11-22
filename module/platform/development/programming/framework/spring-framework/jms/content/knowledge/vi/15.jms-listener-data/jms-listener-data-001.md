# Tham số payload và @Payload trong @JmsListener

**Chủ đề:** Spring Framework - jms → Dữ liệu listener

## 1. Payload là gì và vì sao listener cần tham số payload?

Trong một hệ thống JMS (Jakarta Messaging), mỗi message thường có ba phần:

- **Headers chuẩn JMS:** ví dụ `JMSMessageID`, `JMSCorrelationID`, `JMSReplyTo`, `JMSDestination`.
- **Message properties:** metadata do ứng dụng/provider đặt, ví dụ `eventType`, `tenantId`, `priorityLevel`.
- **Body:** nội dung nghiệp vụ thực tế như mã đơn hàng, chuỗi JSON, dữ liệu nhị phân hoặc đối tượng có cấu trúc.

Khi dùng Spring Framework, `@JmsListener` cho phép method nhận **phần body đã được chuyển đổi thành giá trị Java** mà không phải tự mở JMS session và gọi `TextMessage.getText()`.

Ví dụ đơn giản:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class OrderListener {

    @JmsListener(destination = "orders.incoming")
    public void receive(String orderId) {
        System.out.println("ORDER=" + orderId);
    }
}
~~~

Nếu producer gửi `TextMessage` chứa `"order-42"`, với converter phù hợp, Spring gọi `receive("order-42")` và method in:

~~~text
ORDER=order-42
~~~

Ở ví dụ này, tham số `String orderId` chính là **payload parameter**, dù không có annotation `@Payload`. Spring nhận ra vì `String` không thuộc các kiểu tham số đặc biệt mà endpoint có thể inject.

Có thể viết tường minh hơn:

~~~java
import org.springframework.messaging.handler.annotation.Payload;

@JmsListener(destination = "orders.incoming")
public void receive(@Payload String orderId) {
    System.out.println("ORDER=" + orderId);
}
~~~

Hai phiên bản có cùng ý nghĩa ở trường hợp đơn giản: sử dụng body của JMS message sau khi chuyển đổi. `@Payload` làm rõ ý định và cho phép gắn với các khả năng như validation. **Nó không tự biến một DTO thành JSON, không chọn destination và không thay thế MessageConverter.**

Bài này tập trung vào **dữ liệu listener**, đặc biệt là việc Spring quyết định tham số nào nhận payload, cách `@Payload` phối hợp `@Header`/`@Headers`, kiểu dữ liệu Java sau chuyển đổi, validation, ví dụ Java 17+ và lỗi thường gặp.

## 2. Kiến trúc: JMS Message → Spring Messaging Message → method argument

Khi `@JmsListener` hoạt động, Spring tạo message listener container, nhận JMS message từ broker và sử dụng listener adapter/method argument resolvers để gọi method. Một cách nhìn thực hành:

~~~text
Producer Java
    |
    | JmsTemplate.convertAndSend(...)
    v
JMS Queue / Topic trên broker
    |
    v
JMS listener container
    |
    | nhận jakarta.jms.Message
    v
Spring Messaging adapter / message conversion
    |
    +--> payload: String, byte[], Map, DTO ...
    |
    +--> mapped headers: JMS headers + application properties
    |
    v
@JmsListener method:
    onMessage(
        @Payload String body,
        @Header("eventType") String type
    )
    |
    v
Business logic
~~~

Cần phân biệt **hai lớp chuyển đổi** có thể liên quan:

1. **JMS message conversion:** `org.springframework.jms.support.converter.MessageConverter` chuyển giữa Java object và `jakarta.jms.Message`. Converter mặc định thường là `SimpleMessageConverter`.
2. **Spring Messaging argument resolution/conversion:** phương thức listener được gọi qua adapter, với `org.springframework.messaging.Message<?>`, các resolver cho `@Payload`, `@Header`, `@Headers` và tùy chọn validation. Một số trường hợp cần converter của listener adapter/handler được cấu hình phù hợp.

Việc một producer gửi đúng `TextMessage` **không đảm bảo** bất kỳ Java class nào cũng có thể được bind vào tham số `@Payload`. Kiểu tham số phải phù hợp với object được converter trả ra, hoặc phải có conversion khác có thể chuyển nó đến kiểu đích.

### 2.1. Payload không đồng nghĩa với toàn bộ message

Một payload `"order-42"` không chứa sẵn toàn bộ headers, properties và destination. Nếu listener cần cả mã đơn hàng lẫn `eventType`, nên nhận payload **và** header riêng:

~~~java
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@JmsListener(destination = "orders.incoming")
public void receive(
        @Payload String orderId,
        @Header("eventType") String eventType) {

    System.out.println(orderId + " / " + eventType);
}
~~~

Ở đây `orderId` thuộc **body**, còn `eventType` thuộc **message properties được ánh xạ sang Spring headers**. Nếu message thiếu header bắt buộc `eventType`, method argument resolution có thể báo lỗi trước khi thực thi thân method.

## 3. Import đúng annotation @Payload

Annotation dùng với `@JmsListener` đến từ **Spring Messaging**:

~~~java
import org.springframework.messaging.handler.annotation.Payload;
~~~

Không có một annotation `@Payload` chuẩn trong package `jakarta.jms`. Spring JMS phụ thuộc vào cơ chế method-argument resolution của Spring Messaging, nên cùng annotation Spring này cũng có thể xuất hiện ở một số loại messaging endpoints khác.

Mã minh họa:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;

@Component
class PaymentListener {

    @JmsListener(destination = "payments.incoming")
    public void receive(@Payload String paymentId) {
        System.out.println("PAYMENT=" + paymentId);
    }
}
~~~

**Chú ý import:** không nhầm `org.springframework.jms.annotation.JmsListener` với Spring Kafka/Rabbit annotations. Trong Spring Boot 3.x, các kiểu JMS API là `jakarta.jms.Message`, `jakarta.jms.Session`; các annotation `@Payload`, `@Header`, `@Headers` vẫn thuộc `org.springframework.messaging.handler.annotation`.

### 3.1. @Payload không bắt buộc với tham số nghiệp vụ thông thường

Spring Framework cho phép:

~~~java
@JmsListener(destination = "payments.incoming")
public void receive(String paymentId) { ... }
~~~

Một tham số không được nhận diện là raw `jakarta.jms.Message`, `jakarta.jms.Session` hoặc Spring `Message<?>` và không có annotation header thường sẽ được xem là **payload**.

Cách viết rõ ràng nhất ở method có nhiều tham số:

~~~java
@JmsListener(destination = "payments.incoming")
public void receive(
        @Payload String paymentId,
        @Header("sourceSystem") String sourceSystem) {
    // Business processing...
}
~~~

Code trên là **trích đoạn method**, phải nằm trong Spring-managed component với imports thích hợp. Chức năng không đổi chỉ vì `@Payload` xuất hiện; ưu điểm chính là **ý định dễ đọc** và giảm nhầm với header metadata.

### 3.2. Một method không nên có nhiều tham số payload độc lập

Tránh thiết kế:

~~~java
// Không nên trông đợi Spring tách một TextMessage thành hai tham số này.
@JmsListener(destination = "orders.incoming")
public void receive(@Payload String orderId, @Payload int quantity) {
    // ...
}
~~~

JMS message có một body; `@Payload` không tự chia một String thành hai trường khác nhau. Với dữ liệu có cấu trúc, tạo một DTO/record chứa các trường, hoặc nhận chuỗi JSON rồi parse có chủ đích. Nếu cần nhiều phần thông tin, dùng một tham số payload và các tham số header/session được hỗ trợ.

## 4. Các loại tham số hợp lệ của @JmsListener

Spring Framework hỗ trợ nhiều kiểu method signature. Sự khác biệt đáng chú ý:

| Tham số | Spring truyền vào | Phù hợp khi |
| --- | --- | --- |
| `String body` | Payload được convert, không cần `@Payload` | TextMessage có nội dung String |
| `@Payload String body` | Payload String, ý định tường minh | Dễ đọc, kết hợp header/validation |
| `@Payload byte[] bytes` | Payload binary nếu converter hỗ trợ | BytesMessage |
| `@Payload Map<String,Object> data` | Payload Map nếu JMS message converter hỗ trợ MapMessage | Body có nhiều field đơn giản |
| `@Payload OrderCreated dto` | DTO, cần converter/type mapping thích hợp | JSON/schema-based business payload |
| `@Header("eventType") String type` | Một Spring message header | Metadata được map từ JMS property |
| `@Headers Map<String,Object> headers` | Tập headers của Spring message | Quan sát nhiều header |
| `jakarta.jms.Message raw` | Raw JMS message | Cần native headers, properties, body |
| `jakarta.jms.TextMessage rawText` | Raw JMS TextMessage khi message type khớp | Dùng trực tiếp JMS-specific API |
| `jakarta.jms.Session session` | JMS session liên quan đến việc nhận | Thao tác JMS bổ sung, reply thủ công |
| `org.springframework.messaging.Message<T> message` | Spring Messaging message với payload và headers | Muốn dùng abstraction độc lập transport |

**Hai kiểu `Message` khác nhau hoàn toàn:**

~~~java
jakarta.jms.Message nativeMessage;
org.springframework.messaging.Message<String> springMessage;
~~~

Đây là **hai khai báo mẫu**, không phải hai biến đã được khởi tạo. Loại thứ nhất là JMS API và có `getJMSCorrelationID()`, `getStringProperty(...)`. Loại thứ hai là Spring abstraction và có `getPayload()`, `getHeaders()`.

**Không** áp dụng `@Payload` lên tham số raw `jakarta.jms.Message` rồi kỳ vọng Spring truyền nguyên JMS message như payload. Raw JMS Message là một tham số đặc biệt đã được hỗ trợ riêng; nó khác giá trị Java sau conversion.

### 4.1. Khi nào chọn raw Message?

Nếu cần xử lý cả payload lẫn `JMSMessageID`/`JMSReplyTo` hoặc các JMS properties không được map theo cấu hình:

~~~java
@JmsListener(destination = "orders.raw")
public void receive(jakarta.jms.TextMessage message)
        throws jakarta.jms.JMSException {

    String body = message.getText();
    String correlationId = message.getJMSCorrelationID();
    String type = message.getStringProperty("eventType");

    System.out.println(body + " / " + type + " / " + correlationId);
}
~~~

Đoạn method này cần đặt trong Spring-managed bean và chỉ thích hợp với **TextMessage**. Nếu broker giao BytesMessage/MapMessage, kiểu tham số không khớp; dùng `jakarta.jms.Message` rồi kiểm tra `instanceof` hoặc thiết kế destination với một schema rõ.

Nếu chỉ cần String business payload thì nhận `@Payload String` sẽ đơn giản và ít phụ thuộc JMS hơn.

## 5. Kiểu dữ liệu payload nào được converter mặc định hỗ trợ?

Theo `SimpleMessageConverter` của Spring JMS, những cặp phổ biến:

| JMS message nhận được | Object Java sau converter | Payload parameter điển hình |
| --- | --- | --- |
| `TextMessage` | `String` | `@Payload String` |
| `BytesMessage` | `byte[]` | `@Payload byte[]` |
| `MapMessage` | `Map<String,Object>` | `@Payload Map<String,Object>` |
| `ObjectMessage` | Java Serializable object sau deserialize | Kiểu Java tương thích, nếu chính sách deserialization cho phép |

Các chuyển đổi trên phụ thuộc vào converter thực tế của listener container. Trong ví dụ Java 17+ phần sau dùng **String**, `byte[]` và `Map` để không cần converter tùy chỉnh.

### 5.1. String và TextMessage

Producer:

~~~java
jmsTemplate.convertAndSend("demo.payload.text", "order-42");
~~~

Consumer:

~~~java
@JmsListener(destination = "demo.payload.text")
public void receive(@Payload String orderId) {
    System.out.println("TEXT=" + orderId);
}
~~~

Khi message ấy được giao và converter hoạt động, body `"order-42"` trở thành Java `String`.

Một String chứa `"{\"orderId\":\"A42\"}"` vẫn là String. **Không có chuyện annotation `@Payload OrderDto` tự đọc JSON** khi không có JSON converter phù hợp.

### 5.2. byte[] và BytesMessage

Producer:

~~~java
jmsTemplate.convertAndSend("demo.payload.binary",
        new byte[] {1, 2, 3});
~~~

Consumer:

~~~java
import java.util.Arrays;

@JmsListener(destination = "demo.payload.binary")
public void receive(@Payload byte[] bytes) {
    System.out.println("BYTES=" + Arrays.toString(bytes));
}
~~~

Payload nhận được là **raw bytes**. Spring không tự biết đó là UTF-8 text, ảnh, Avro, Protobuf hay tệp ZIP. Việc decode theo charset/schema là trách nhiệm của application contract.

### 5.3. Map và MapMessage

Producer:

~~~java
Map<String, Object> values = new java.util.LinkedHashMap<>();
values.put("orderId", "A42");
values.put("quantity", 3);

jmsTemplate.convertAndSend("demo.payload.map", values);
~~~

Consumer:

~~~java
@JmsListener(destination = "demo.payload.map")
public void receive(@Payload Map<String, Object> values) {
    System.out.println(values.get("orderId"));
}
~~~

Hai đoạn là **trích đoạn**, cần import `java.util.Map` và các biến bean phù hợp. Với `MapMessage`, Map values phải thuộc tập kiểu hỗ trợ của JMS MapMessage (primitives/wrappers, String, byte[] phù hợp). Không đặt tùy ý `Instant`, `List` hoặc nested DTO vào MapMessage rồi mong converter tự serialize sâu.

### 5.4. Serializable và ObjectMessage

Nếu producer gửi một đối tượng Serializable không thuộc ba nhóm trên, `SimpleMessageConverter` có thể tạo `ObjectMessage`. Consumer nhận được object đã deserialize khi classpath và trust policy của provider phù hợp.

Ví dụ một `record` Java:

~~~java
import java.io.Serial;
import java.io.Serializable;

public record OrderNotice(String orderId)
        implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;
}
~~~

Đây là mã cho file `OrderNotice.java` độc lập; record không tự Serializable nếu không khai báo. Nếu nhận ObjectMessage chứa `OrderNotice` và deserialization thành công, tham số kiểu `@Payload OrderNotice notice` có thể được bind.

**Cảnh báo:** ObjectMessage dùng Java serialization, có rủi ro deserialization khi nguồn không tin cậy, phụ thuộc class/version/trusted packages. Ưu tiên JSON hoặc schema-based binary format với type mapping kiểm soát khi giao tiếp giữa nhiều service, đặc biệt là liên ngôn ngữ.

## 6. @Payload kết hợp @Header và @Headers

Thông thường business method cần body và một số metadata để phân luồng/ghi log.

### 6.1. @Header cho từng property

Producer đặt String property:

~~~java
jmsTemplate.convertAndSend(
        "demo.orders",
        "order-42",
        message -> {
            message.setStringProperty("eventType", "ORDER_CREATED");
            return message;
        });
~~~

Listener:

~~~java
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@JmsListener(destination = "demo.orders")
public void receive(
        @Payload String orderId,
        @Header("eventType") String eventType) {

    System.out.println("ORDER=" + orderId);
    System.out.println("EVENT=" + eventType);
}
~~~

Với default JMS header mapper, application property `eventType` được đưa vào Spring message headers, để resolver `@Header("eventType")` lấy ra.

Phải phân biệt:

- `@Payload String orderId`: lấy body.
- `@Header("eventType") String eventType`: lấy một header được map từ property JMS.
- JMS selector `eventType = 'ORDER_CREATED'`: dùng cùng property ấy **ở provider**, trước khi gọi listener, nếu listener cấu hình selector.

Một header bị thiếu có thể làm `@Header` với `required=true` (mặc định) thất bại khi resolve argument. Có thể dùng:

~~~java
@Header(name = "sourceSystem", required = false)
String sourceSystem
~~~

Đây là **trích đoạn tham số**, cần đặt trong method. Khi header không có, có thể nhận `null` nếu kiểu tham số cho phép; sau đó ứng dụng phải xử lý fallback. Đừng dùng primitive `int` cho header có thể vắng mặt mà không có default/conversion hợp lệ.

### 6.2. @Headers cho nhiều header

Muốn xem tập header được ánh xạ sang Spring Messaging:

~~~java
import java.util.Map;
import org.springframework.messaging.handler.annotation.Headers;
import org.springframework.messaging.handler.annotation.Payload;

@JmsListener(destination = "demo.orders")
public void receive(
        @Payload String orderId,
        @Headers Map<String, Object> headers) {

    System.out.println("ORDER=" + orderId);
    System.out.println("HAS_EVENT=" + headers.containsKey("eventType"));
}
~~~

Tham số có `@Headers` phải tương thích với `Map`. Không nhầm với `@Payload Map<String,Object>`:

- `@Headers Map<...>` = **metadata headers** của Spring Messaging.
- `@Payload Map<...>` = **body** đã được converter xử lý, ví dụ MapMessage.

Hai Map có thể có các key trùng nhau, nhưng nguồn và ý nghĩa khác nhau. Không giả định mọi JMS header/provider-specific property đều được map vào headers: hành vi phụ thuộc `JmsHeaderMapper` và converter/adapters được sử dụng.

### 6.3. Standard JMS header với JmsHeaders

Spring cung cấp `org.springframework.jms.support.JmsHeaders` cho tên chuẩn trong Spring Messaging abstraction.

~~~java
import org.springframework.jms.support.JmsHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@JmsListener(destination = "demo.orders")
public void receive(
        @Payload String body,
        @Header(JmsHeaders.CORRELATION_ID) String correlationId) {

    System.out.println("CORR=" + correlationId);
}
~~~

Giá trị Spring header tên theo `JmsHeaders.CORRELATION_ID` tương ứng native `JMSCorrelationID`, nếu header được provider/mapper cung cấp. Nên dùng constant thay vì gõ nhầm `"JMSCorrelationID"`, vì **tên header trong Spring Messaging không nhất thiết giống tên trường JMS API**.

Producer nên đặt native correlation header bằng:

~~~java
message.setJMSCorrelationID("corr-42");
~~~

Đây là trích đoạn JMS `Message` trước khi send, **không** dùng `setStringProperty("JMSCorrelationID", "corr-42")` để thay thế native header.

## 7. Ví dụ hoàn chỉnh Java 17+ dùng Spring Boot và Artemis

Ví dụ minh họa ba kiểu binding trong một ứng dụng nhỏ:

1. `@Payload String` kết hợp `@Header("eventType")` và native `JMSCorrelationID` đã được map.
2. `String` **không** có `@Payload`, nhưng vẫn được hiểu là payload.
3. `@Payload byte[]`, kiểm tra payload của BytesMessage.
4. `@Payload Map<String,Object>`, kiểm tra MapMessage.

Mỗi listener dùng **một queue riêng** để tránh competing consumers và các kiểu message lẫn nhau. Đây là cách thử có chủ đích, không phải yêu cầu luôn tách queue theo kiểu payload trong production.

### 7.1. Điều kiện môi trường

Tạo project Maven trên [Spring Initializr](https://start.spring.io/) với:

- Group `com.example`; Artifact `jms-payload-demo`; Java **17+**; Spring Boot **3.x**.
- Dependency **Spring for Apache ActiveMQ Artemis** (artifact `org.springframework.boot:spring-boot-starter-artemis`).
- Broker **Apache ActiveMQ Artemis bên ngoài process** chạy tại `tcp://localhost:61616`.
- Tài khoản có quyền connect/send/consume và bốn queue đã được provision hoặc broker cho phép auto-create: `demo.payload.explicit`, `demo.payload.implicit`, `demo.payload.binary`, `demo.payload.map`.
- Để dễ quan sát, ban đầu bốn queue không có message tồn đọng và không có consumer khác đọc những queue này.

Đặt biến môi trường `ARTEMIS_USER` và `ARTEMIS_PASSWORD` theo tài khoản của broker. Không đưa mật khẩu thật vào Git.

Tệp `src/main/resources/application.properties`:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=${ARTEMIS_USER}
spring.artemis.password=${ARTEMIS_PASSWORD}

spring.jms.pub-sub-domain=false
~~~

`mode=native` **không khởi động broker nhúng**. Spring Boot với Artemis starter và auto-configuration hợp lệ sẽ tạo `ConnectionFactory`, `JmsTemplate` và listener infrastructure. Theo Spring Boot, thường **không cần** tự thêm `@EnableJms` trong ứng dụng Boot đã có đầy đủ JMS infrastructure.

### 7.2. Tệp Java đầy đủ

Tệp `src/main/java/com/example/JmsPayloadDemoApplication.java`:

~~~java
package com.example;

import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.JmsHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class JmsPayloadDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsPayloadDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner publish(JmsTemplate template) {
        return args -> {
            template.convertAndSend(
                    "demo.payload.explicit",
                    "order-42",
                    message -> {
                        message.setStringProperty(
                                "eventType", "ORDER_CREATED");
                        message.setJMSCorrelationID("corr-order-42");
                        return message;
                    });

            template.convertAndSend(
                    "demo.payload.implicit", "invoice-17");

            template.convertAndSend(
                    "demo.payload.binary", new byte[] {1, 2, 3});

            Map<String, Object> values = new LinkedHashMap<>();
            values.put("orderId", "A42");
            values.put("quantity", 3);
            template.convertAndSend("demo.payload.map", values);

            System.out.println("SENT=4");
        };
    }
}

@Component
class PayloadListeners {

    // Đặt @Payload tường minh, thêm property và JMS header.
    @JmsListener(destination = "demo.payload.explicit")
    public void explicit(
            @Payload String orderId,
            @Header("eventType") String eventType,
            @Header(JmsHeaders.CORRELATION_ID) String correlationId) {

        System.out.println("EXPLICIT_PAYLOAD=" + orderId);
        System.out.println("EXPLICIT_EVENT=" + eventType);
        System.out.println("EXPLICIT_CORRELATION=" + correlationId);
    }

    // Một String không có annotation vẫn được hiểu là payload.
    @JmsListener(destination = "demo.payload.implicit")
    public void implicit(String invoiceId) {
        System.out.println("IMPLICIT_PAYLOAD=" + invoiceId);
    }

    @JmsListener(destination = "demo.payload.binary")
    public void binary(@Payload byte[] data) {
        System.out.println(
                "BINARY_PAYLOAD=" + Arrays.toString(data));
    }

    @JmsListener(destination = "demo.payload.map")
    public void map(@Payload Map<String, Object> data) {
        System.out.println("MAP_ORDER=" + data.get("orderId"));
        System.out.println("MAP_QUANTITY=" + data.get("quantity"));
    }
}
~~~

**Kiểm tra cấu trúc Java:** File có một `public class JmsPayloadDemoApplication` đúng với tên file và một class `PayloadListeners` package-private có `@Component` trong package được Spring scan. Java 17 hỗ trợ các cú pháp sử dụng trong ví dụ.

**Kiểm tra JMS:** Hai lời gọi `convertAndSend(..., "order-42")` và `convertAndSend(..., "invoice-17")` tạo `TextMessage` với default converter. Mảng primitive byte[] tạo `BytesMessage`. Java Map với String keys và giá trị String/int phù hợp tạo `MapMessage`.

**Kiểm tra argument mapping:** `@Payload String` lấy body, `@Header("eventType")` lấy property đã được map, `@Header(JmsHeaders.CORRELATION_ID)` lấy native JMS correlation ID được map. Listener khác dùng tham số String ngầm định. Hai listener cuối dùng byte[] và Map. Nếu đã tùy biến JMS converter/header mapper trong project, phải kiểm tra lại contract trước khi áp dụng nguyên ví dụ.

### 7.3. Chạy bằng Maven

Trong thư mục gốc dự án:

~~~bash
mvn spring-boot:run
~~~

Với Maven Wrapper nếu dự án tạo ra `mvnw.cmd` trên Windows:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Khi broker, credentials, destination, message conversion và listener containers đều đúng, không có message cũ hoặc competing consumer, các **dòng nghiệp vụ kỳ vọng** là:

~~~text
EXPLICIT_PAYLOAD=order-42
EXPLICIT_EVENT=ORDER_CREATED
EXPLICIT_CORRELATION=corr-order-42
IMPLICIT_PAYLOAD=invoice-17
BINARY_PAYLOAD=[1, 2, 3]
MAP_ORDER=A42
MAP_QUANTITY=3
SENT=4
~~~

Đây là **tập dòng mong đợi, không phải thứ tự stdout bắt buộc**. Spring Boot có startup logs. `SENT=4` có thể xuất hiện trước hoặc sau output listener vì nhận bất đồng bộ. Các dòng in **bên trong cùng một method** giữ thứ tự như code; các listener khác nhau có thể chạy xen kẽ nhau. Nếu message tồn đọng hoặc có consumer khác, output có thể khác.

Nếu broker không hoạt động, thông tin đăng nhập sai hoặc queue không được cấp quyền, ứng dụng có thể lỗi kết nối/khởi tạo hoặc gửi/nhận thất bại. Không coi ví dụ này là một broker tự chứa; phần hạ tầng phải chuẩn bị thực tế.

### 7.4. Vì sao ví dụ cho thấy @Payload không bắt buộc?

Hai method:

~~~java
public void explicit(@Payload String orderId, ... ) { ... }
public void implicit(String invoiceId) { ... }
~~~

đều nhận body String. Method đầu minh họa annotation tường minh và phối hợp header; method sau chứng minh **tham số không thuộc loại đặc biệt được xem như payload theo mặc định**.

Trong code dài hoặc listener có nhiều tham số, `@Payload` làm ý định rõ ràng; trong listener đơn giản một tham số String, không đặt annotation vẫn hợp lệ và thường được sử dụng.

## 8. Payload kiểu DTO/record và JSON: cần converter, không chỉ annotation

Một lỗi phổ biến là viết:

~~~java
@JmsListener(destination = "orders.json")
public void receive(@Payload OrderCreated order) {
    // ...
}
~~~

rồi tin rằng Spring tự parse bất kỳ JSON `TextMessage` nào thành `OrderCreated`. **Không đúng nếu converter chưa được cấu hình**.

Với `SimpleMessageConverter`, `TextMessage` thường trở thành `String`. Để nhận DTO từ JSON, cần ánh xạ JSON/String → Java type rõ ràng. Spring JMS 6.x có `MappingJackson2MessageConverter`, nhưng phải chuẩn bị Jackson dependency, target JMS message type, type-id hoặc mapping an toàn và cấu hình converter trên listener container thực sự sử dụng.

### 8.1. DTO/record ví dụ

Tệp `src/main/java/com/example/OrderCreated.java`:

~~~java
package com.example;

public record OrderCreated(
        String orderId,
        int quantity) {
}
~~~

Đây là Java 17 record hợp lệ, **không cần implements Serializable nếu dùng JSON TextMessage**. Nó chỉ là model; không tự tạo JMS converter.

### 8.2. Cấu hình JSON converter ở Spring Framework 6.x

Ví dụ một cấu hình minh họa:

~~~java
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageConverter;
import org.springframework.jms.support.converter.MessageType;

@Configuration
class JsonConverterConfig {

    @Bean
    MessageConverter orderJsonJmsConverter() {
        MappingJackson2MessageConverter c =
                new MappingJackson2MessageConverter();
        c.setTargetType(MessageType.TEXT);
        c.setTypeIdPropertyName("_type");
        c.setTypeIdMappings(
                Map.of("order-created", OrderCreated.class));
        return c;
    }
}
~~~

**Đây là một configuration snippet, không phải project đầy đủ**; phải có Spring JMS, Jackson và `OrderCreated` class thực tế. Type-ID property `_type` là metadata cần thống nhất giữa producer và consumer; dữ liệu JSON trong body một mình chưa đủ để suy ra Java class nếu converter dựa trên type-id.

Để bảo đảm listener dùng converter ấy trong **Spring Framework thuần**, có thể cấu hình factory và chỉ định trên annotation:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.support.converter.MessageConverter;

@Configuration
class JsonListenerConfig {

    @Bean("jsonListenerFactory")
    DefaultJmsListenerContainerFactory jsonListenerFactory(
            ConnectionFactory connectionFactory,
            MessageConverter orderJsonJmsConverter) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setMessageConverter(orderJsonJmsConverter);
        return factory;
    }
}
~~~

Listener chọn factory:

~~~java
@JmsListener(
        destination = "orders.json",
        containerFactory = "jsonListenerFactory")
public void receive(@Payload OrderCreated order) {
    System.out.println(order.orderId());
}
~~~

Đây là ví dụ cấu hình kết hợp, **không phải mã chạy độc lập** vì còn cần bean `ConnectionFactory`, registration của `@JmsListener` (trong Spring thuần: `@EnableJms`) và producer dùng JSON converter/schema tương thích. Trong Spring Boot, cơ chế tự động liên kết `MessageConverter` bean còn phụ thuộc cấu hình và phiên bản; nên kiểm tra factory thực nhận thay vì chỉ tuyên bố mọi listener tự dùng mọi converter bean.

### 8.3. Tách conversion lỗi và binding lỗi

Một message chứa JSON không hợp lệ có thể lỗi **trước khi method listener được gọi**. Ngay cả khi JSON parse thành công, cấu trúc body có thể không tương thích với `OrderCreated`, hoặc type id bị thiếu/sai/trust mapping từ chối. Vì vậy log trong method không xuất hiện **không tự chứng minh queue trống**.

Đừng tạo type mapping bằng cách tin tùy ý mọi class name có trong message; chỉ ánh xạ tới tập domain types đã được ứng dụng cho phép. Đây là ranh giới bảo mật quan trọng khi deserialize dữ liệu từ messaging system.

## 9. Validation với @Valid @Payload

`@Payload` có thể kết hợp Bean Validation để kiểm tra object **sau khi conversion**, trước khi business logic của listener chạy.

Tệp DTO có constraints:

~~~java
package com.example;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record OrderCreated(
        @NotBlank String orderId,
        @Min(1) int quantity) {
}
~~~

Listener:

~~~java
import jakarta.validation.Valid;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.messaging.handler.annotation.Payload;

@JmsListener(
        destination = "orders.validated",
        containerFactory = "jsonListenerFactory")
public void handle(@Valid @Payload OrderCreated order) {
    System.out.println("VALID_ORDER=" + order.orderId());
}
~~~

**Điều kiện:** Có Jakarta Validation API/provider (ví dụ thêm `spring-boot-starter-validation`), JSON converter hoạt động, và một `Validator` được cấu hình đúng cho handler argument resolution. Chỉ thêm `@Valid` nhưng thiếu validator/messaging handler configuration không bảo đảm validation sẽ được kích hoạt trong mọi setup.

Trong Spring Framework thuần, tài liệu chính thức minh họa một `DefaultMessageHandlerMethodFactory` được cung cấp validator thông qua `JmsListenerConfigurer`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListenerConfigurer;
import org.springframework.jms.config.JmsListenerEndpointRegistrar;
import org.springframework.messaging.handler.annotation.support
        .DefaultMessageHandlerMethodFactory;
import org.springframework.validation.Validator;

@Configuration
@EnableJms
class JmsValidationConfig implements JmsListenerConfigurer {

    private final Validator validator;

    JmsValidationConfig(Validator validator) {
        this.validator = validator;
    }

    @Override
    public void configureJmsListeners(
            JmsListenerEndpointRegistrar registrar) {
        DefaultMessageHandlerMethodFactory handlerFactory =
                new DefaultMessageHandlerMethodFactory();
        handlerFactory.setValidator(validator);
        registrar.setMessageHandlerMethodFactory(handlerFactory);
    }
}
~~~

Đây là **configuration snippet** phụ thuộc vào Spring-managed `Validator` bean; các bean JMS connection/listener factory còn phải được cấu hình theo môi trường. Nếu validation thất bại, lỗi có thể phát sinh ở tầng resolver/handler **trước thân method**, và cơ chế rollback/redelivery phụ thuộc session transaction/ack của listener container. Không dùng validation như một phương thức bảo đảm message sẽ tự bị chuyển vào DLQ; retry/DLQ là cấu hình riêng.

### 9.1. @Payload(required = false) dùng khi nào?

`@Payload` có thuộc tính `required`, mặc định `true`. Có thể khai báo:

~~~java
public void receive(@Payload(required = false) String value) {
    // Xử lý nếu conversion cung cấp payload rỗng/null.
}
~~~

Đoạn này là **method minh họa**, không phải entire listener. Khi `required=false`, resolver không ép non-null ở trường hợp có khả năng biểu diễn empty payload. Tuy nhiên điều này **không làm method chạy khi queue rỗng**, không tạo JMS message giả và không bảo đảm mọi JMS Message body null có thể được converter/adapter xử lý. Nếu contract nghiệp vụ yêu cầu body, giữ `required=true` rồi validate rõ ràng.

Không dùng `@Payload(required=false)` để “bỏ qua lỗi chuyển đổi JSON”: JSON hỏng vẫn là lỗi conversion/schema chứ không phải một payload vắng mặt hợp lệ.

## 10. Nhận Spring Message<T> khi cần cả payload và headers

Nếu code muốn gói payload và metadata trong một abstraction không phụ thuộc trực tiếp JMS:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.messaging.Message;

@JmsListener(destination = "orders.incoming")
public void receive(Message<String> message) {
    String body = message.getPayload();
    Object eventType = message.getHeaders().get("eventType");

    System.out.println("BODY=" + body);
    System.out.println("EVENT_TYPE=" + eventType);
}
~~~

Đây là Spring-managed listener method snippet. Chú ý `org.springframework.messaging.Message<String>` **không phải** `jakarta.jms.Message`.

Ưu điểm:

- Giữ payload và headers trong một giá trị.
- Dễ test business logic theo messaging abstraction.
- Không cần gọi getter của JMS API khi chỉ cần metadata đã được map.

Giới hạn:

- Hành vi map header phụ thuộc `JmsHeaderMapper`/converter đang dùng.
- Nếu cần native `JMSReplyTo` object hoặc provider-specific feature, raw JMS Message có thể phù hợp hơn.
- `Message<T>` có type parameter, nhưng không chứng minh runtime payload chắc chắn thuộc `T` nếu config chuyển đổi sai; lỗi có thể phát sinh khi resolver/converter gọi method.

### 10.1. @Header và MessageHeaders khác nhau

Cùng một method có thể lấy header đơn lẻ hoặc toàn bộ headers:

~~~java
@JmsListener(destination = "orders.incoming")
public void receive(
        @Payload String body,
        @Header("eventType") String eventType,
        @Headers Map<String, Object> allHeaders) {

    // ...
}
~~~

Dùng `@Header` nếu chỉ quan tâm một trường; dùng `@Headers Map` khi thật sự cần nhiều metadata. Không tự ghi log toàn bộ headers trong production vì một số hệ thống có thể đặt dữ liệu nhạy cảm vào properties.

## 11. Các dạng payload khác: Boolean, Integer, POJO và collection

Một bẫy thường gặp: không phải mọi kiểu Java đều map thành một JMS Message type riêng.

- `String` thường tạo TextMessage.
- `byte[]` thường tạo BytesMessage.
- `Map` với value hợp lệ thường tạo MapMessage.
- `Serializable` khác các nhánh trên có thể tạo ObjectMessage.
- `Integer` và `Boolean` implements Serializable nên có thể đi theo ObjectMessage với `SimpleMessageConverter`; **không** có JMS `IntegerMessage`/`BooleanMessage` chuẩn.
- `List` không tương đương `MapMessage`. Một implementation Serializable có thể được xử lý qua ObjectMessage, nhưng không mặc định có ListMessage.
- `record` Java không tự implements Serializable; để nhận DTO JSON nên dùng custom JSON converter.

Ví dụ minh họa:

~~~java
// Nếu template dùng SimpleMessageConverter và provider cho phép ObjectMessage:
jmsTemplate.convertAndSend("orders.number", Integer.valueOf(42));
~~~

Listener nhận đúng object:

~~~java
@JmsListener(destination = "orders.number")
public void receive(@Payload Integer number) {
    System.out.println("NUMBER=" + number);
}
~~~

Tuy nhiên **ObjectMessage có rủi ro Java deserialization** và có thể bị provider/trust policy chặn. Đừng thiết kế luồng giao tiếp giữa service bằng ObjectMessage một cách mặc định nếu có thể dùng TextMessage JSON/BytesMessage schema với type mapping an toàn.

### 11.1. Khi nào phương thức nhận DTO sẽ hoạt động?

Có hai tình huống khác nhau:

1. JMS ObjectMessage thực sự chứa một object Serializable tương thích và policy cho phép deserialize: payload Java có thể là DTO ngay.
2. JMS TextMessage chứa JSON: cần JSON converter hoặc parsing chuyên dụng. `@Payload MyDto` không tự làm điều đó.

Một số ứng dụng thiết lập thêm conversion service của Spring Messaging để chuyển một kiểu đơn giản sang kiểu khác. Nhưng **conversion service không thay thế schema decoder tổng quát**. Không suy luận rằng Map, JSON text, byte[] luôn chuyển được sang DTO bất kỳ.

## 12. Thử nghiệm unit/integration cho @Payload

### 12.1. Unit-test business logic độc lập JMS

Một ưu điểm của việc nhận payload Java là business method dễ test đơn giản bằng Java:

~~~java
public class OrderService {

    public String normalize(String orderId) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId required");
        }
        return orderId.trim();
    }
}
~~~

Đây là một class Java thuần; bạn có thể test nó không cần broker. Listener chỉ adapter nhận message và gọi service:

~~~java
@JmsListener(destination = "orders.incoming")
public void handle(@Payload String orderId) {
    String normalized = orderService.normalize(orderId);
    System.out.println(normalized);
}
~~~

Đoạn listener cần một `orderService` bean/injected field; **không phải file Java độc lập**. Tách business logic như vậy giúp kiểm thử payload validation/processing không phụ thuộc listener container.

### 12.2. Integration test phải xác nhận đúng converter

Unit-test gọi trực tiếp `handle("order-42")` **không kiểm tra** liệu broker JMS có thể chuyển TextMessage thành String hoặc map properties thành `@Header`. Integration test cần broker thật hoặc test infrastructure tương thích, gửi message và xác nhận listener được gọi.

Checklist:

1. Gửi TextMessage với body String; kiểm tra `@Payload String` nhận đúng.
2. Gửi BytesMessage; kiểm tra `@Payload byte[]` không tự decode sang String.
3. Gửi MapMessage; kiểm tra `@Payload Map` có keys/values đúng kiểu.
4. Gửi TextMessage JSON nhưng chưa cấu hình JSON converter; không kỳ vọng method `@Payload OrderCreated` hoạt động.
5. Bật converter JSON và type-id mapping an toàn; kiểm tra method DTO được gọi.
6. Bỏ property `eventType`; xác nhận `@Header(required=true)` phát sinh lỗi trong pipeline.
7. Gửi DTO vi phạm `@Valid` khi đã có validator; kiểm tra error handling/redelivery policy.
8. Kiểm tra message conversion exception xảy ra **trước business method**, không chỉ bắt exception trong method.
9. Xác minh queue depth, listener consumer count và DLQ để biết message lỗi đã được xử lý như thế nào.
10. Chạy test trên queue sạch hoặc dùng unique IDs; tránh message tồn đọng và nhiều consumers làm kết quả không ổn định.

### 12.3. Không nhầm @Payload với JMS selector

Một listener:

~~~java
@JmsListener(
        destination = "orders.incoming",
        selector = "eventType = 'ORDER_CREATED'")
public void receive(@Payload String body) {
    // ...
}
~~~

có hai chức năng tách biệt:

- **`selector`** nằm ở consumer/JMS provider và quyết định **message nào được giao**.
- **`@Payload`** nằm ở listener argument resolver và quyết định **đối số method lấy dữ liệu body**.

Không thể dùng `@Payload` để thay selector và ngược lại. Selector chỉ có thể đọc application properties và các standard headers được JMS cho phép, không đọc trực tiếp JSON body.

## 13. Các lỗi phổ biến khi nhận payload

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Listener `@Payload String` không được gọi | Endpoint chưa đăng ký, sai destination/queue, broker chưa kết nối hoặc converter/selector lỗi | Kiểm tra listener infrastructure, broker metrics, queue, exception logs |
| `@Payload OrderCreated` không nhận được JSON TextMessage | Chưa cấu hình converter/type mapping | Dùng JSON converter phù hợp, thống nhất schema/metadata |
| `@Header("eventType")` báo thiếu header | Producer không đặt property, sai chính tả hoặc mapper bỏ qua | Đặt property đúng tên/kiểu, kiểm tra mapper |
| `@Headers Map` chứa nhiều header hơn mong đợi | Spring map cả standard JMS headers và application properties | Chỉ dùng keys cần thiết, không xem là payload Map |
| `@Payload byte[]` nhận binary nhưng code xử lý như String | Chưa decode theo charset/codec | Chọn schema/codec/charset rõ ràng |
| `@Payload Map` có value khác kiểu dự kiến | MapMessage body có primitive wrappers; schema drift | Kiểm tra contract và runtime type của từng entry |
| `ObjectMessage` bị từ chối deserialize | Trusted packages/classpath/serialVersionUID/security policy | Kiểm tra provider restrictions, tránh trust-all, cân nhắc JSON |
| Method `receive(String, String)` bị hiểu sai | Cả hai tham số thường đều được xem là payload, không tự tách body | Dùng một `@Payload` và một `@Header` hoặc DTO |
| Import sai `Message` | Nhầm `jakarta.jms.Message` và `org.springframework.messaging.Message<T>` | Dùng fully qualified class khi code dễ nhầm |
| DTO validation không chạy | Chưa có Jakarta Validator hoặc handler method factory wiring | Cấu hình provider/validator và xác nhận integration test |
| Lỗi conversion nhưng không thấy log trong method | Lỗi xảy ra trước khi method được invoke | Quan sát listener container error logs và DLQ |
| Dùng `@Payload(required=false)` rồi nghĩ queue rỗng sẽ gọi method | Annotation không tạo message | Dùng polling/timeout nếu cần biết queue rỗng |
| Payload được đọc đúng nhưng JMSCorrelationID mất | Chỉ nhận value Java, không nhận metadata | Dùng `@Header(JmsHeaders.CORRELATION_ID)` hoặc raw Message |
| Thấy message bị xử lý nhiều lần | Rollback/redelivery, nhiều consumers/attempts | Kiểm tra session transaction, idempotency, DLQ |
| Hệ thống dùng `javax.jms.*` với Boot 3 | API không tương thích Jakarta JMS | Dùng dependency/provider client thuộc Jakarta Messaging |

### 13.1. Phân biệt conversion failure và business failure

Lỗi **trước khi vào method** thường nằm ở:

~~~text
JMS message đến
     |
     v
JMS MessageConverter
     |
     v
Spring argument resolver
     |
     +--> payload type không khớp?
     +--> @Header bắt buộc bị thiếu?
     +--> @Valid từ chối DTO?
     |
     v
Listener method được gọi
     |
     +--> business validation / database / API / logic exception
~~~

Khi code không in được một dòng log đặt ngay đầu listener method, đừng vội kết luận không có message. Cần kiểm tra việc đăng ký listener, broker queue, selector, converter, header mapping và validation error logs.

### 13.2. Lưu ý transaction, retry và DLQ

`@Payload` không thay đổi JMS acknowledgment hoặc transaction. Nếu conversion/validation thất bại, message có được redeliver hay không còn phụ thuộc `DefaultJmsListenerContainerFactory`, session transaction, provider và cách error handler/rollback được cấu hình.

Với hệ thống production, cân nhắc:

- Bật session transaction phù hợp với yêu cầu reliability.
- Áp dụng idempotency cho nghiệp vụ có thể nhận lặp message.
- Giới hạn số lần retry và theo dõi dead-letter queue đối với poison messages.
- Ghi log đủ ID/correlation/type để debug nhưng không log raw payload chứa dữ liệu nhạy cảm.
- Không coi `@Valid` hay converter là thay thế cho authentication/authorization.
- Khi dùng database và JMS, local JMS session transaction không tự tạo atomic transaction hai hệ thống; dùng outbox/inbox hoặc transaction coordination khi cần.

## 14. Cách chọn chữ ký listener thực tế

| Nhu cầu | Chữ ký đề xuất | Lý do |
| --- | --- | --- |
| Chỉ cần mã đơn hàng String | `handle(@Payload String orderId)` | Ngắn, biểu đạt rõ payload |
| Chỉ có một tham số String đơn giản | `handle(String orderId)` | @Payload có thể bỏ |
| Body và một property bắt buộc | `handle(@Payload String body, @Header("eventType") String type)` | Tách body và metadata |
| Body và property có thể thiếu | `handle(@Payload String body, @Header(name="traceId", required=false) String trace)` | Xử lý header optional |
| Body và nhiều headers | `handle(@Payload String body, @Headers Map<String,Object> headers)` | Truy cập tập headers |
| Cần native JMS fields/Session | `handle(jakarta.jms.Message raw, jakarta.jms.Session session)` | Trực tiếp dùng JMS API |
| Muốn transport-independent envelope | `handle(org.springframework.messaging.Message<String> message)` | Payload và headers trong một object |
| Cần JSON business DTO | `handle(@Valid @Payload OrderCreated dto)` | Đòi JSON converter và validator đúng |
| Nhận BytesMessage | `handle(@Payload byte[] bytes)` | Payload binary theo contract |
| Nhận MapMessage | `handle(@Payload Map<String,Object> map)` | Payload Map với schema rõ |

**Nguyên tắc:** ưu tiên chữ ký **chỉ nhận những gì nghiệp vụ cần**. Nếu service chỉ cần orderId, đừng bắt nó phụ thuộc toàn bộ `jakarta.jms.Message`. Nếu cần correlation header, nhận nó qua `@Header` hoặc raw Message thay vì cố nhúng vào String payload.

Khi code có nhiều listeners và converters, đặt rõ destination, type mapping, schema version, error policy và transaction. Việc thêm `@Payload` không tự giải quyết những thông số ấy.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `@JmsListener(destination="orders") public void receive(String value)` có cần `@Payload` mới chạy không?

**Đáp án:** Không. Spring coi tham số nghiệp vụ String không thuộc kiểu đặc biệt là payload theo mặc định.

**Câu 2.** Khác nhau giữa `@Payload String body` và `@Header("eventType") String type`?

**Đáp án:** Cái đầu nhận body Java sau conversion; cái sau nhận metadata từ Spring headers đã được ánh xạ từ JMS header/property.

**Câu 3.** `@Payload Map<String,Object> values` khác `@Headers Map<String,Object> headers` thế nào?

**Đáp án:** Payload Map thường biểu diễn dữ liệu từ MapMessage/body; headers Map chứa metadata. Không thay thế cho nhau.

**Câu 4.** Tại sao TextMessage chứa JSON không tự bind vào `@Payload OrderCreated`?

**Đáp án:** SimpleMessageConverter mặc định biến TextMessage thành String, không tự parse JSON thành class tùy ý. Cần JSON converter và type mapping.

**Câu 5.** Muốn cả payload và JMSCorrelationID, có thể dùng gì?

**Đáp án:** `@Payload String` kết hợp `@Header(JmsHeaders.CORRELATION_ID) String`, hoặc nhận raw `jakarta.jms.Message`.

**Câu 6.** `@Payload` có áp dụng lên raw `jakarta.jms.Message` để nó trở thành payload String không?

**Đáp án:** Không. Raw JMS Message là kiểu argument riêng, không phải giá trị Java body đã convert.

**Câu 7.** Byte[] và byte[] có giống nhau khi SimpleMessageConverter gửi không?

**Đáp án:** Không. Mảng primitive `byte[]` đi nhánh BytesMessage; `Byte[]` không có cùng nhánh và có thể thành ObjectMessage nếu Serializable.

**Câu 8.** Muốn validate DTO bằng `@Valid @Payload` cần những gì?

**Đáp án:** Converter tạo DTO đúng, Jakarta validation provider và một Validator được tích hợp vào message handler factory; chính sách ack/transaction xử lý failure riêng.

**Câu 9.** `@Payload(required=false)` có khiến listener được gọi khi queue không có message không?

**Đáp án:** Không. Nó chỉ điều chỉnh cách resolver xử lý một payload vắng mặt trong message thực sự được giao, khi pipeline hỗ trợ.

**Câu 10.** Hai method listener cùng queue, một nhận String và một nhận Map, có tự định tuyến theo body type không?

**Đáp án:** Không nên dựa vào điều đó. Chúng là competing consumers; cần tách destinations, selector/property hoặc routing rõ ràng.

**Câu 11.** Tại sao unit-test gọi trực tiếp listener method chưa đủ kiểm tra JMS conversion?

**Đáp án:** Vì unit-test bỏ qua broker, JMS message converter, argument resolvers, header mapping và transaction. Cần integration test phù hợp.

**Câu 12.** Khi payload được chuyển đổi thành công, có chắc message được acknowledge hoặc database commit không?

**Đáp án:** Không. Delivery, transaction, retry và business processing là các phần riêng, phụ thuộc cấu hình container và hạ tầng.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html): `@JmsListener`, các kiểu method arguments, `@Payload`, `@Header`, `@Headers`, `Message<?>`, validation.
- [Spring Framework 6.2 Javadoc — @Payload](https://docs.spring.io/spring-framework/docs/6.2.4/javadoc-api/org/springframework/messaging/handler/annotation/Payload.html): thuộc tính `required`, payload binding và conversion.
- [Spring Framework 6.2 Javadoc — JmsListener](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/annotation/JmsListener.html): endpoint signature, factory, destination, selector và lifecycle.
- [Spring Framework 6.2 Javadoc — JmsHeaders](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/jms/support/JmsHeaders.html): tên Spring Messaging headers tương ứng JMS standard fields.
- [Spring Framework — Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html): `SimpleMessageConverter` và `MessagePostProcessor`.
- [Spring Framework 6.2 Javadoc — DefaultMessageHandlerMethodFactory](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/messaging/handler/annotation/support/DefaultMessageHandlerMethodFactory.html): resolver và validator cho annotated methods.
- [Spring Boot — Messaging with JMS](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): Artemis, auto-configuration, `@JmsListener`.
- [Spring Guide — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/): Spring Boot starter, producer, consumer và converter.
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): JMS message types, standard headers, properties, queue semantics.
