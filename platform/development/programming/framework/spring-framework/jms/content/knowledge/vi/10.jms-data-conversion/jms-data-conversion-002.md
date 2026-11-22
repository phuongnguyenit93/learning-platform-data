# SimpleMessageConverter và các kiểu dữ liệu được hỗ trợ

**Chủ đề:** Spring Framework - jms → Chuyển đổi dữ liệu

## 1. SimpleMessageConverter giải quyết bài toán nào?

Khi dùng API JMS trực tiếp, ứng dụng phải tạo một `jakarta.jms.Message` cụ thể bằng `Session`, chẳng hạn `TextMessage`, `BytesMessage`, `MapMessage` hoặc `ObjectMessage`. Trong Spring Framework, `JmsTemplate` có các phương thức `convertAndSend(...)` và `receiveAndConvert(...)` giúp chuyển đổi giữa **giá trị Java** và **JMS Message**.

Lớp `org.springframework.jms.support.converter.SimpleMessageConverter` là cách chuyển đổi mặc định của `JmsTemplate` khi chưa chỉ định converter khác. Nó thực hiện quy tắc đơn giản theo kiểu Java đầu vào hoặc theo kiểu JMS message đầu vào:

- `String` ↔ `TextMessage`.
- `byte[]` ↔ `BytesMessage`.
- `java.util.Map` ↔ `MapMessage`.
- Đối tượng `java.io.Serializable` ↔ `ObjectMessage`.

Ví dụ, không cần tự tạo `TextMessage`:

~~~java
// jmsTemplate là bean org.springframework.jms.core.JmsTemplate hợp lệ.
jmsTemplate.convertAndSend("orders.queue", "order-42");
~~~

Spring lấy chuỗi `"order-42"`, sử dụng converter tạo `TextMessage` và gửi tới destination `orders.queue`. Ở phía nhận, `receiveAndConvert("orders.queue")` có thể trả một `String` tương ứng.

**Giới hạn quan trọng:** SimpleMessageConverter **không** mặc định biến bất kỳ POJO thành JSON, không tự chuyển một record Java thành `MapMessage`, và không biết schema nghiệp vụ của ứng dụng. Nó phân loại theo **kiểu Java** và các quy tắc JMS sẵn có.

Bài tập trung vào **chuyển đổi dữ liệu** trong Spring JMS, dùng Java **17+**, Spring Framework **6.x / Spring Boot 3.x** với package `jakarta.jms.*`. Hệ thống cũ sử dụng `javax.jms.*`; cần chọn đúng JMS client API cho runtime, không trộn hai namespace không tương thích.

## 2. Bức tranh tổng thể: Java object và JMS message

~~~text
                         PRODUCER
 Java value                              JMS message
 ─────────────────────────────────────────────────────────
 String "hello"                      ->  TextMessage
 byte[] {1,2,3}                      ->  BytesMessage
 Map<String,Object>                  ->  MapMessage
 Serializable object                 ->  ObjectMessage
          |                                    |
          |     JmsTemplate.convertAndSend     |
          +---------- SimpleMessageConverter -+
                                               |
                                           JMS provider
                                               |
                                            BROKER
                                               |
                         CONSUMER
 JMS message                            Java value
 ─────────────────────────────────────────────────────────
 TextMessage                         -> String
 BytesMessage                        -> byte[]
 MapMessage                          -> Map<String, Object>
 ObjectMessage                       -> Serializable object
          |                                    |
          +--- SimpleMessageConverter ---------+
                JmsTemplate.receiveAndConvert
~~~

| Giá trị Java khi gửi | JMS message khi gửi | Kết quả sau khi nhận và convert | Điểm cần nhớ |
| --- | --- | --- | --- |
| `String` | `TextMessage` | `String` | Không tự parse JSON dù nội dung chuỗi nhìn giống JSON |
| `byte[]` | `BytesMessage` | `byte[]` | Giữ byte thô, không có charset tự động |
| `Map<?, ?>` với key/giá trị hợp lệ | `MapMessage` | `Map<String, Object>` | Giá trị trong Map phải thuộc kiểu body mà JMS hỗ trợ |
| `Serializable` không thuộc ba nhóm trên | `ObjectMessage` | Object deserialize được | Java serialization, phải lưu ý bảo mật và phiên bản class |

**Thứ tự phân loại có ý nghĩa:** một `HashMap` thường cũng implements `Serializable` nhưng converter ưu tiên nhánh **Map → MapMessage**. Ngược lại, một `ArrayList` (Serializable nhưng không là Map) có thể đi theo nhánh **ObjectMessage**, không có JMS `ListMessage` tương ứng.

Mặt khác, `Byte[]` (mảng wrapper, chữ B viết hoa) **khác** `byte[]` (mảng primitive); nó không match nhánh `byte[] → BytesMessage`. Vì là một mảng đối tượng Serializable, nó có thể được xử lý như ObjectMessage. Hãy dùng `byte[]` khi muốn chính xác một `BytesMessage`.

## 3. API và chỗ Spring thực hiện chuyển đổi

Spring JMS định nghĩa interface:

~~~java
package org.springframework.jms.support.converter;

public interface MessageConverter {
    jakarta.jms.Message toMessage(
            Object object, jakarta.jms.Session session)
            throws jakarta.jms.JMSException, MessageConversionException;

    Object fromMessage(jakarta.jms.Message message)
            throws jakarta.jms.JMSException, MessageConversionException;
}
~~~

Đây là **hình thức diễn giải chữ ký API**, không phải file Java để dán vào project (interface Spring đã tồn tại trong dependency). Hai hướng:

1. **`toMessage(Object, Session)`:** Java object → JMS Message. Spring cần một `Session` để tạo đúng loại message.
2. **`fromMessage(Message)`:** JMS Message → Java object. Converter đọc nội dung message theo JMS type.

`JmsTemplate.convertAndSend(...)` sử dụng `toMessage` trước khi send. `JmsTemplate.receiveAndConvert(...)` nhận message rồi dùng `fromMessage`. Các thao tác này **không thay đổi** ý nghĩa của queue/topic, transaction, acknowledgment hay quyền truy cập broker.

### 3.1. Chỗ converter không được gọi

~~~java
// Có chuyển đổi Java object sang JMS Message.
jmsTemplate.convertAndSend("orders.queue", "hello");

// Có chuyển đổi JMS Message sang Java object.
Object result = jmsTemplate.receiveAndConvert("orders.queue");

// Tự tạo JMS Message, không cần toMessage của SimpleMessageConverter.
jmsTemplate.send("orders.queue",
        session -> session.createTextMessage("hello"));

// Nhận raw JMS Message, không gọi fromMessage.
jakarta.jms.Message raw = jmsTemplate.receive("orders.queue");
~~~

Các đoạn đều là **minh họa bên trong một phương thức đã có `jmsTemplate` bean**. Trường hợp nhận đồng bộ có thể block tùy receive timeout, và `receiveAndConvert` có thể trả `null` khi hết thời gian chờ. Không lấy `null` làm bằng chứng rằng converter thất bại.

### 3.2. Converter xử lý phần body, không đồng nghĩa với header mapper

Một `TextMessage` có thể có `JMSCorrelationID`, `JMSReplyTo` và các message properties. `SimpleMessageConverter.fromMessage` trả **body dưới dạng Java object**, chứ không biến toàn bộ JMS headers/properties thành một Map nghiệp vụ.

Muốn thêm header/property trước khi send, sử dụng `MessagePostProcessor`:

~~~java
jmsTemplate.convertAndSend(
        "orders.queue",
        "order-42",
        message -> {
            message.setStringProperty("eventType", "ORDER_CREATED");
            message.setJMSCorrelationID("corr-42");
            return message;
        });
~~~

Ở đây converter tạo `TextMessage`, sau đó callback nhận **JMS Message** để thêm metadata trước khi gửi. Không nhầm `org.springframework.jms.core.MessagePostProcessor` với header mapping của `org.springframework.messaging.Message<?>`.

## 4. String ↔ TextMessage

Đây là trường hợp đơn giản nhất. Khi gửi một `String`:

~~~java
jmsTemplate.convertAndSend("demo.converter", "Xin chào JMS");
~~~

Converter tạo `TextMessage` chứa text chính xác theo nội dung chuỗi. Khi gọi `fromMessage` trên một `TextMessage`, nó đọc `getText()` và trả Java `String`.

Minh họa API mức thấp tương đương:

~~~java
// session là jakarta.jms.Session hợp lệ.
jakarta.jms.TextMessage message =
        session.createTextMessage("Xin chào JMS");
String text = message.getText();
System.out.println(text);
~~~

Output:

~~~text
Xin chào JMS
~~~

Đoạn trích yêu cầu một JMS Session, không chạy độc lập nếu thiếu provider/broker. Nhưng quy tắc converter không phụ thuộc vào nội dung chuỗi: chuỗi `"{\"id\":1}"` vẫn chỉ là **String → TextMessage**; SimpleMessageConverter không parse nó thành POJO, Map hay JSON tree.

**Ví dụ dễ nhầm:** một String chứa XML hoặc JSON không làm message tự mang định dạng dữ liệu được kiểm chứng. Đây chỉ là bytes/văn bản trong TextMessage. JSON parsing/deserialization cần Jackson hoặc một converter riêng, có xác định charset/schema và validation phù hợp.

### 4.1. Khi nào nên dùng String?

- Log, command đơn giản hoặc payload text đã serialize sẵn.
- JSON text đã tạo bằng `ObjectMapper.writeValueAsString(...)` trong ứng dụng.
- Muốn dễ quan sát bằng JMS console và tránh Java ObjectMessage serialization.
- Khi producer và consumer thống nhất encoding, format và version của body.

Không gửi đối tượng phức tạp rồi kỳ vọng `SimpleMessageConverter` tự chuyển POJO thành JSON. Nếu đã serialize thành String ở phía ứng dụng, converter chỉ đảm nhiệm lớp **String ↔ TextMessage**.

## 5. byte[] ↔ BytesMessage

Với dữ liệu nhị phân, truyền `byte[]` vào `convertAndSend`:

~~~java
byte[] payload = new byte[] {1, 2, 3, 4};
jmsTemplate.convertAndSend("demo.converter", payload);
~~~

Converter tạo `BytesMessage`, ghi lần lượt bốn byte. Khi chuyển ngược, nó đọc nội dung của `BytesMessage` và trả về `byte[]`.

**Khác với `ObjectMessage`:** converter không cần Java serialization cho mảng `byte[]` theo nhánh này; đây là raw bytes. Không mặc định coi bytes là UTF-8, Java serialization stream hay JSON. Consumer phải biết cách decode theo contract.

Nếu business payload là UTF-8 text được encode vào bytes:

~~~java
import java.nio.charset.StandardCharsets;

byte[] encoded = "Xin chào".getBytes(StandardCharsets.UTF_8);
// Producer gửi byte[] -> BytesMessage.
jmsTemplate.convertAndSend("demo.converter", encoded);

// Consumer khi nhận lại byte[]:
String decoded = new String(encoded, StandardCharsets.UTF_8);
~~~

Đây là minh họa encoding/decoding với mảng byte có sẵn, không phải logic nhận từ broker hoàn chỉnh. Trong hệ thống thực, decode **mảng byte được receiveAndConvert trả về** chứ không dùng lại mảng producer.

### 5.1. Lưu ý về kích thước và memory

Khi `fromMessage` đọc `BytesMessage`, ứng dụng có thể cần cấp một mảng `byte[]` chứa toàn bộ payload. Với message rất lớn, hãy kiểm tra **giới hạn message size** của broker và memory phía consumer. JMS không phải hệ thống upload file lớn mặc định; dùng object storage và gửi reference có thể phù hợp hơn.

Nếu muốn nén, mã hóa hoặc áp dụng schema nhị phân như Avro/Protobuf, hãy thực hiện qua một bước riêng trước/sau SimpleMessageConverter. Lớp mặc định **không tự nén, mã hóa hoặc validate schema**.

## 6. Map ↔ MapMessage: metadata có cấu trúc trong body

Một `Map<String, Object>` với các key và value phù hợp có thể được convert thành JMS `MapMessage`:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

Map<String, Object> order = new LinkedHashMap<>();
order.put("orderId", "A42");    // String
order.put("quantity", 3);       // Integer
order.put("express", true);     // Boolean

jmsTemplate.convertAndSend("demo.converter", order);
~~~

Converter tạo `MapMessage` rồi gán từng phần tử theo các API kiểu được JMS hỗ trợ. Khi chuyển ngược, nó đọc các tên phần tử và trả về một `Map` Java.

**Giới hạn quan trọng:** MapMessage **không** lưu tùy ý mọi object Java như `Map<String, Object>` ngoài ứng dụng. Các kiểu body value hợp lệ theo JMS gồm boolean/byte/short/char/int/long/float/double, các wrapper tương ứng, `String`, `byte[]` (và các trường hợp null theo hợp đồng provider/spec). Map key phải dùng **String**. Nếu Map chứa value là `BigDecimal`, `Instant`, `List` hoặc nested `Map`, việc convert có thể thất bại; hãy serialize body thành JSON hoặc thiết kế schema phù hợp thay vì dựa vào tự chuyển đổi.

### 6.1. MapMessage field khác message property

MapMessage lưu các phần tử trong **message body**:

~~~text
MapMessage:
  body:
    orderId   -> "A42"
    quantity  -> 3
    express   -> true

  properties:
    tenantId  -> "blue"
  headers:
    JMSMessageID -> ID:...
~~~

Đây là ba tầng dữ liệu khác nhau. Việc `MapMessage` có body entry `quantity=3` **không làm selector** `quantity >= 2` truy cập được field đó. JMS selector đọc **message properties và một số standard headers**, không đọc body.

Muốn broker lọc theo quantity:

~~~java
jmsTemplate.convertAndSend(
        "demo.converter",
        order,
        message -> {
            message.setIntProperty("quantity", 3);
            return message;
        });
~~~

Bây giờ có **body entry** `quantity=3` và một **property** `quantity=3`. Dù trùng tên, đó là hai vùng dữ liệu riêng. Nên chỉ copy metadata lên properties khi thật sự phục vụ selector/routing, tránh trùng lặp không cần thiết.

### 6.2. MapMessage không đồng nghĩa với JSON

Một `MapMessage` dùng JMS native body format. Nó không phải `TextMessage` chứa JSON như:

~~~json
{"orderId":"A42","quantity":3,"express":true}
~~~

Do đó consumer mong nhận JSON String không thể mặc định ép `MapMessage` thành chuỗi JSON. Khi hệ thống giao tiếp nhiều nền tảng hoặc dùng HTTP/REST song song, cân nhắc một chuẩn JSON converter rõ ràng.

### 6.3. Thứ tự phần tử Map không được bảo đảm theo contract

Trong Java, `LinkedHashMap` bảo toàn thứ tự khi producer tạo object. Nhưng `MapMessage` là một message type khác và JMS không hứa vòng lặp qua các field sẽ giữ đúng thứ tự chèn ban đầu. Khi test, nên so các **field theo key**, không so thứ tự enumeration hoặc chuỗi `Map.toString()` từ phía receive.

## 7. Serializable ↔ ObjectMessage

Nếu đối tượng Java implements `java.io.Serializable` nhưng không thuộc các nhánh String, byte[] hoặc Map, SimpleMessageConverter có thể tạo một JMS `ObjectMessage`:

~~~java
// Integer implements java.io.Serializable:
jmsTemplate.convertAndSend("demo.converter", Integer.valueOf(42));
~~~

JMS Message tương ứng là một `ObjectMessage`. Khi nhận và convert, object deserialize thành một `Integer` có giá trị 42 (giả sử provider/deserialization policy cho phép).

Một DTO tự định nghĩa phải triển khai `Serializable` nếu muốn theo cách này:

~~~java
import java.io.Serial;
import java.io.Serializable;

public record OrderNotice(String orderId, boolean express)
        implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;
}
~~~

Đây là **kiểu dữ liệu Java có thể biên dịch trong file OrderNotice.java**. Muốn gửi:

~~~java
jmsTemplate.convertAndSend(
        "demo.converter",
        new OrderNotice("A42", true));
~~~

Nhưng **không nên mặc nhiên chọn ObjectMessage cho hệ thống production hoặc cross-service**. Nó có nhiều rủi ro:

1. **Java serialization** gắn chặt các class/serialVersionUID/serialization compatibility giữa producer và consumer.
2. Receiver phải có class phù hợp trên classpath. Thay package/class hoặc cấu trúc serialized object có thể làm deserialization thất bại.
3. Deserialization dữ liệu không tin cậy có thể gây **lỗ hổng bảo mật**, nhất là khi provider cho phép deserialize class tùy ý. Dùng allowlist/trusted packages theo provider và không nhận untrusted ObjectMessage bừa bãi.
4. Broker/provider có thể hạn chế hoặc từ chối ObjectMessage theo chính sách an toàn.
5. Đối tượng Java không có nghĩa là một dạng wire format di động sang JavaScript, Python hay hệ thống khác.

### 7.1. Record không tự động Serializable

Một Java `record` không tự implements `Serializable` chỉ vì nó là record. Chẳng hạn:

~~~java
public record OrderEvent(String orderId) { }
~~~

Đây là một record hợp lệ về cú pháp Java, **nhưng không tự thỏa nhánh Serializable** của SimpleMessageConverter. Khi gọi `convertAndSend` với một object không nằm trong String, byte[], Map hay Serializable, converter sẽ không có quy tắc chuyển phù hợp và có thể ném `MessageConversionException`.

Nếu cần JSON cho DTO/record, dùng converter JSON chuyên dụng thay vì gắn `implements Serializable` chỉ để vượt qua một lỗi chuyển đổi.

## 8. Ví dụ đầy đủ: Spring Boot 3.x, Java 17+ và Artemis

Ví dụ này cho thấy **cả bốn loại JMS Message** xuất hiện sau khi gửi từ Java object, rồi được SimpleMessageConverter giải mã trở lại. Không cần custom message converter bean. Chúng ta dùng một consumer nhận raw JMS Message để quan sát loại chính xác; Spring có thể cấu hình listener auto-conversion cho tham số business khác trong các ứng dụng thông thường.

### 8.1. Điều kiện chạy

- JDK 17+, Maven hoặc Maven Wrapper.
- Dự án Spring Boot **3.x** với dependency **Spring for Apache ActiveMQ Artemis** (Maven coordinate `org.springframework.boot:spring-boot-starter-artemis`). Có thể tạo dự án ở [Spring Initializr](https://start.spring.io/), group `com.example`, artifact `simple-converter-demo`.
- **Artemis broker ngoài process** chạy tại `tcp://localhost:61616`; cho phép user/password kết nối, gửi và nhận queue `demo.converter`. Provision queue hoặc bật auto-create theo chính sách broker.
- Môi trường receiver phải cho phép deserialize loại `java.lang.Integer` sử dụng trong ObjectMessage. Mặc dù đây là loại Java chuẩn, một số provider cấu hình allowlist nghiêm ngặt vẫn có thể từ chối ObjectMessage. Không nới toàn bộ trust list trong production chỉ để chạy ví dụ.
- Đặt biến môi trường `ARTEMIS_USER`, `ARTEMIS_PASSWORD` bằng tài khoản broker thực tế.

Tệp `src/main/resources/application.properties`:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=${ARTEMIS_USER}
spring.artemis.password=${ARTEMIS_PASSWORD}
spring.jms.pub-sub-domain=false
~~~

`mode=native` không tạo broker nhúng. Dòng `spring.jms.pub-sub-domain=false` dùng queue semantics trong ví dụ.

Tệp `src/main/java/com/example/SimpleConverterDemoApplication.java`:

~~~java
package com.example;

import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;

import jakarta.jms.BytesMessage;
import jakarta.jms.JMSException;
import jakarta.jms.MapMessage;
import jakarta.jms.Message;
import jakarta.jms.ObjectMessage;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.converter.SimpleMessageConverter;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class SimpleConverterDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SimpleConverterDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner publish(JmsTemplate template) {
        return args -> {
            // String -> TextMessage.
            template.convertAndSend("demo.converter", "hello");

            // byte[] -> BytesMessage.
            template.convertAndSend(
                    "demo.converter", new byte[] {1, 2, 3});

            // Map<String,Object> -> MapMessage.
            Map<String, Object> data = new LinkedHashMap<>();
            data.put("orderId", "A42");
            data.put("quantity", 3);
            template.convertAndSend("demo.converter", data);

            // Serializable Integer -> ObjectMessage.
            template.convertAndSend(
                    "demo.converter", Integer.valueOf(42));

            System.out.println("SENT=4");
        };
    }
}

@Component
class ConverterInspector {

    private final SimpleMessageConverter converter =
            new SimpleMessageConverter();

    @JmsListener(destination = "demo.converter")
    public void inspect(Message message) throws JMSException {
        Object value = converter.fromMessage(message);

        if (message instanceof TextMessage
                && value instanceof String text) {
            System.out.println("TEXT=" + text);
        } else if (message instanceof BytesMessage
                && value instanceof byte[] bytes) {
            System.out.println("BYTES=" + Arrays.toString(bytes));
        } else if (message instanceof MapMessage
                && value instanceof Map<?, ?> data) {
            System.out.println(
                    "MAP=orderId:" + data.get("orderId")
                    + ",quantity:" + data.get("quantity"));
        } else if (message instanceof ObjectMessage
                && value instanceof Integer number) {
            System.out.println("OBJECT=" + number);
        } else {
            throw new IllegalStateException(
                    "Unexpected JMS message type/payload");
        }
    }
}
~~~

**Tại sao ví dụ này biên dịch?** File chứa một `public class SimpleConverterDemoApplication` đúng với filename và một `@Component` package-private. Dùng Java 17 cho pattern matching `instanceof`. Tất cả bốn nhánh dùng những kiểu Java và JMS được SimpleMessageConverter hỗ trợ; không cần tạo một POJO/deserialization class riêng.

### 8.2. Chạy bằng Maven

Tại thư mục gốc dự án:

~~~bash
mvn spring-boot:run
~~~

Nếu project có Maven Wrapper trên Windows:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Với broker, queue, credentials, policy deserialization đúng và **không có message tồn từ lần trước**, các dòng nghiệp vụ trên đường chạy thành công gồm:

~~~text
SENT=4
TEXT=hello
BYTES=[1, 2, 3]
MAP=orderId:A42,quantity:3
OBJECT=42
~~~

**Thứ tự trên là trình bày để học, không phải thứ tự stdout bắt buộc.** Consumer nhận bất đồng bộ; `SENT=4` có thể xuất hiện trước hoặc sau các dòng nhận, thứ tự ba/ bốn loại message còn phụ thuộc cách broker và listener container phân phối. Spring còn in startup logs. Nếu broker không có destination/quyền, hoặc provider từ chối deserialization, sẽ có lỗi thay vì đủ các dòng.

### 8.3. Phân tích bốn nhánh

| Producer gửi | Loại JMS Message ở listener | Kết quả `fromMessage` | Dòng log |
| --- | --- | --- | --- |
| `"hello"` | `TextMessage` | `String` | `TEXT=hello` |
| `new byte[]{1,2,3}` | `BytesMessage` | `byte[]` | `BYTES=[1, 2, 3]` |
| `Map<String,Object>` | `MapMessage` | `Map` | `MAP=orderId:A42,quantity:3` |
| `Integer.valueOf(42)` | `ObjectMessage` | `Integer` | `OBJECT=42` |

Nếu muốn kiểm tra thật sự **converter là mặc định**, có thể inject `JmsTemplate` và kiểm tra `template.getMessageConverter()` trong một môi trường Boot chưa thay converter. Ví dụ:

~~~java
System.out.println(
        jmsTemplate.getMessageConverter().getClass().getSimpleName());
~~~

Ở một cấu hình mặc định tương ứng, output là:

~~~text
SimpleMessageConverter
~~~

**Lưu ý:** đây là một dòng debug minh họa, không phải dòng có sẵn trong code chạy phần 8; nếu đã đăng ký converter bean/custom template, tên lớp có thể khác. Đừng bắt buộc class name này ở test khi dự án cố ý cấu hình converter khác.

## 9. Khi nhận message: receiveAndConvert và @JmsListener

Có hai hướng nhận cần phân biệt.

### 9.1. Nhận đồng bộ bằng receiveAndConvert

~~~java
// template đã có ConnectionFactory hợp lệ.
jmsTemplate.setReceiveTimeout(2_000L);

Object payload = jmsTemplate.receiveAndConvert("demo.converter");
if (payload == null) {
    System.out.println("NO_MESSAGE");
} else {
    System.out.println(payload.getClass().getName());
}
~~~

Đoạn trên **không độc lập** và chỉ hoạt động khi broker/queue khả dụng. `receiveAndConvert` dùng `SimpleMessageConverter.fromMessage` nếu template chưa được cấu hình converter khác. Kết quả có thể là String, byte[], Map, đối tượng Serializable đã được deserialize, hoặc `null` nếu không có message trước timeout.

Không chạy đồng thời ví dụ này với listener đang consume **cùng queue** rồi kỳ vọng cả hai đều nhận cùng một message. Queue có competing consumers: một message thường chỉ được giao cho **một** consumer trong một lần delivery.

### 9.2. Nhận qua @JmsListener

Một listener có thể nhận raw `jakarta.jms.Message` (như code phần 8), rồi gọi `SimpleMessageConverter` để thấy rõ hành vi. Nó cũng có thể nhận kiểu payload business nhờ các adapter/converter được cấu hình trên listener container, nhưng **converter mà listener dùng không nhất thiết là bean/cấu hình y hệt một JmsTemplate custom khác**.

Nếu method chỉ nhận `String`:

~~~java
@JmsListener(destination = "demo.text")
public void consumeText(String payload) {
    System.out.println(payload);
}
~~~

đó là **trích đoạn trong một Spring component**, cần listener infrastructure. Nó phù hợp với TextMessage. Nhưng một queue chứa đồng thời BytesMessage, MapMessage và ObjectMessage không nên được tiêu thụ bởi một method ép toàn bộ payload thành String; cần quy ước message type/contract hoặc các listener phân tách.

## 10. Những điều SimpleMessageConverter KHÔNG tự làm

| Mong đợi sai | Thực tế |
| --- | --- |
| Đưa DTO bất kỳ vào `convertAndSend` sẽ thành JSON | Không. DTO phải được hỗ trợ bởi nhánh cụ thể; nếu Serializable thì có thể thành ObjectMessage |
| `String` chứa JSON được tự parse thành Map/POJO | Không. Nó vẫn là TextMessage và khi nhận trở lại là String |
| Map có value là DTO/nested Map/Instant sẽ tự hoạt động | Không. MapMessage chỉ hỗ trợ tập kiểu JMS body value giới hạn |
| `Byte[]` và `byte[]` là như nhau | Không. Byte[] không đi theo nhánh BytesMessage mặc định |
| ObjectMessage không cần class tương thích tại consumer | Sai. Java serialization/deserialization phụ thuộc class và trust policy |
| Converter tự tạo queue/topic | Không. Destination do JmsTemplate/provider/broker quản lý riêng |
| Converter tự chuyển properties thành field của POJO | Không. Đây chủ yếu là chuyển đổi body; header/property mapping là vấn đề khác |
| Converter tự đảm bảo exactly-once hoặc retry | Không. Ack, transaction, redelivery và idempotency thuộc các tầng khác |
| Dùng `receiveAndConvert` cùng `@JmsListener` trên một queue thì cả hai đều nhận | Không. Queue semantics là competing consumers |
| Bean converter của JmsTemplate mặc định cũng áp dụng cho mọi listener custom | Không thể suy ra; phải kiểm tra converter của từng container/adapter |

### 10.1. Truyền kiểu unsupported gây lỗi gì?

Khi `SimpleMessageConverter.toMessage` không có nhánh cho giá trị, ví dụ `new Object()` không Serializable, nó báo `MessageConversionException` của Spring JMS (một runtime exception). Khi MapMessage không chấp nhận value, hoặc ObjectMessage bị provider chặn, lỗi có thể đến từ `JMSException`/chuyển đổi của provider và được Spring bao bọc theo đường gọi.

Ví dụ phản diện:

~~~java
// Java Object không implements Serializable, không là String/byte[]/Map.
jmsTemplate.convertAndSend("demo.converter", new Object());
~~~

Đoạn này có thể **biên dịch**, nhưng bị từ chối khi converter cố chuyển payload. Đừng xử lý bằng cách ép `toString()` trên mọi object trong hệ thống: chuỗi `Object.toString()` thường không phải format ổn định cho giao tiếp dịch vụ.

### 10.2. Khi nào cần converter khác?

Nếu hệ thống dùng **DTO/record**, muốn **JSON** thay cho Java serialization và cần giao tiếp đa ngôn ngữ, sử dụng converter JSON phù hợp, chẳng hạn `MappingJackson2MessageConverter` trong Spring Framework 6.x với Jackson 2 dependency phù hợp.

Một cấu hình minh họa:

~~~java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageConverter;
import org.springframework.jms.support.converter.MessageType;

@Configuration
class JsonJmsConverterConfig {

    @Bean
    MessageConverter jsonMessageConverter() {
        MappingJackson2MessageConverter converter =
                new MappingJackson2MessageConverter();

        converter.setTargetType(MessageType.TEXT);
        converter.setTypeIdPropertyName("_type");
        return converter;
    }
}
~~~

**Đây chỉ là ví dụ cấu hình converter, không phải toàn bộ ứng dụng.** Cần Jackson dependency, xác định type-id/trust mappings và kiểm tra bean này có được gắn thật vào JmsTemplate/listener container hay không trong phiên bản Boot đang sử dụng. Không tự cho phép deserialize mọi class do message chỉ định. Với Spring 7+, một số API converter được đổi mới; khi nâng phiên bản phải theo Javadoc phiên bản thực tế.

Nếu cần định dạng JSON nhưng vẫn giữ SimpleMessageConverter, có thể serialize thành String ở producer và parse ở consumer. Tuy nhiên code sẽ phải tự kiểm soát format, lỗi và schema; không gọi đó là SimpleMessageConverter tự chuyển Java DTO thành JSON.

## 11. Khác biệt giữa MapMessage và ObjectMessage

Một câu hỏi thực tế: cả `Map` và `ArrayList` Java thường implements `Serializable`, vậy SimpleMessageConverter sẽ tạo loại JMS message nào?

~~~java
Map<String, Object> map = Map.of("orderId", "A42");
jmsTemplate.convertAndSend("demo.converter", map);
// MapMessage, vì nhánh Map được xét riêng.

java.util.List<String> list = java.util.List.of("A42", "B7");
jmsTemplate.convertAndSend("demo.converter", list);
// Có thể là ObjectMessage do List implementation Serializable.
~~~

Đây là trích đoạn trong một method; `List.of(...)` trả object thuộc implementation JDK thực tế, việc Serializable không phải hợp đồng API chung cho mọi implementation List. Với ví dụ cần bảo đảm rõ ràng, dùng `new java.util.ArrayList<>(...)` (Serializable). Ý chính: **chỉ Map thuộc nhánh MapMessage**, không có chuyển đổi tự động List → MapMessage.

Phân biệt MapMessage vs ObjectMessage:

| Điểm | MapMessage | ObjectMessage |
| --- | --- | --- |
| Body format | Các field key/value JMS | Một Serializable object |
| Chuyển kiểu | Dựa vào tập kiểu MapMessage hợp lệ | Java serialization |
| Portability | Có thể tương tác JMS client khác nếu tuân theo JMS type | Gắn Java/class/serialization, khó liên thông đa ngôn ngữ |
| Selector | Không đọc field trong body; vẫn đọc message properties | Không đọc trường object trong body |
| Rủi ro | Value type không hỗ trợ, schema drift | Class version, security deserialization, trust-list |
| Thay thế | JSON/Avro/Protobuf với custom converter khi cần | JSON/format schema rõ cho cross-service |

Vì vậy không thể nói `SimpleMessageConverter` là “bộ JSON serializer” hay “bộ JavaBean mapper”. Nó chỉ là một mapping mặc định của **bốn nhóm JMS message phổ biến**.

## 12. Quy tắc thiết kế message contract

Hãy thống nhất producer và consumer về **payload Java**, **JMS message type**, **body schema** và **metadata**. Một contract minh họa:

~~~yaml
destination: demo.converter
jmsMessageType: MapMessage
bodyFields:
  orderId: {type: String, example: A42}
  quantity: {type: int, example: 3}
properties:
  eventType: {type: String, example: ORDER_CREATED}
  schemaVersion: {type: int, example: 1}
~~~

Đây là **tài liệu mô tả contract**, không phải nội dung `application.yml` của Spring Boot. Nếu không ghi contract, một consumer chỉ thấy `MapMessage` có thể không biết field `quantity` được gửi theo `int` hay `String`, hoặc `eventType` nằm trong body hay properties.

Một vài nguyên tắc:

1. Nếu dùng `TextMessage` chứa JSON, chỉ rõ encoding, schema version, validation và giới hạn kích thước.
2. Nếu dùng `BytesMessage`, chỉ rõ MIME/schema/codec (nếu cần) và tránh decode bytes theo một charset không thống nhất.
3. Nếu dùng `MapMessage`, dùng key String, values nằm trong tập JMS chấp nhận, không lồng DTO tùy ý.
4. Nếu dùng `ObjectMessage`, kiểm soát classpath và allowlist, tránh nguồn không tin cậy; cân nhắc JSON thay thế.
5. Giữ `JMSCorrelationID`, `JMSReplyTo`, `JMSDestination` và message properties đúng tầng, không nhét lẫn vào body chỉ để “tiện convert”.
6. Không dùng converter để che giấu lỗi routing, transaction hoặc message selection.

## 13. Lỗi phổ biến và chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `MessageConversionException` khi `convertAndSend(new Object())` | Object không thuộc String, byte[], Map hay Serializable | Dùng kiểu hỗ trợ hoặc converter tùy chỉnh |
| Gửi DTO nhưng receiver không đọc được | DTO Serializable thành ObjectMessage, class/serialVersionUID lệch | Đồng bộ class/compatibility hoặc chuyển JSON |
| Artemis/Java báo deserialize bị từ chối | ObjectMessage có class nằm ngoài allowlist hoặc bị chặn | Xem chính sách provider, chỉ trust những class cần thiết |
| Gửi Map có `List`/`Instant` value lỗi | MapMessage không hỗ trợ tùy ý mọi Java object | Encode body JSON hoặc sửa schema value |
| Consumer kỳ vọng String nhưng nhận MapMessage | Producer gửi Map, không phải String JSON | Đồng bộ message contract và converter |
| Consumer nhận byte[] rồi decode ra chữ lỗi | Sai charset/codec | Đồng bộ UTF-8 hoặc định dạng nhị phân rõ |
| `Byte[]` nhận kiểu khác `byte[]` | Mảng wrapper đi qua nhánh Serializable | Dùng `byte[]` primitive |
| `receiveAndConvert` trả null | Timeout/queue rỗng/chưa có message phù hợp | Kiểm tra receive timeout, queue metrics và competing consumers |
| Test flakey vì có listener và receive đồng bộ cùng queue | Hai consumer cạnh tranh | Test tách queue hoặc dừng listener khi đo receive |
| Lỗi khi dùng Map key không phải String | MapMessage cần key kiểu tên String | Chuẩn hóa key String |
| Properties không xuất hiện trong `fromMessage` body | Converter chỉ lấy body | Đọc headers/properties trên raw JMS Message |
| JSON text không thành POJO | SimpleMessageConverter không parse JSON | Gắn JSON converter/parse rõ ràng |
| `@JmsListener` không nhận được | Sai queue/topic, ACL, selector hoặc container | Kiểm tra broker, destination, quyền và listener configuration |

### 13.1. Khắc phục theo chuỗi nguyên nhân

Khi chuyển đổi gặp lỗi, kiểm tra theo thứ tự:

~~~text
Kiểu Java ở producer
      ↓
toMessage() chọn JMS Message type nào?
      ↓
Map values/Serializable có hợp lệ?
      ↓
Provider có chấp nhận payload và quyền gửi?
      ↓
Consumer thật sự nhận JMS Message type nào?
      ↓
fromMessage() đọc body và deserialize được không?
      ↓
Ứng dụng kiểm tra kiểu kết quả và schema ra sao?
~~~

Ghi log loại Java producer, JMS type ở receiver, destination, correlation/business ID và error class. Tránh log dữ liệu nhạy cảm hoặc toàn bộ raw ObjectMessage. Sự tồn tại message trên broker không có nghĩa converter phía receiver có đủ class/permission để đọc nó.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `jmsTemplate.convertAndSend("queue", "hello")` tạo TextMessage, chứ không phải ObjectMessage dù String implements Serializable?

**Đáp án:** SimpleMessageConverter ưu tiên nhánh String → TextMessage trước nhánh Serializable → ObjectMessage.

**Câu 2.** `Map<String, Object>` chứa `quantity=3` có cho selector `quantity > 2` lọc tự động không?

**Đáp án:** Không. MapMessage chứa quantity trong **body**. Selector chỉ thấy JMS properties và các header được hỗ trợ; producer phải đặt property riêng nếu cần lọc ở broker.

**Câu 3.** Gửi `byte[] {1,2,3}` và `Byte[] {1,2,3}` có giống JMS type không?

**Đáp án:** Không. `byte[]` dùng nhánh BytesMessage; `Byte[]` không match nhánh primitive byte array và có thể thành ObjectMessage theo Serializable.

**Câu 4.** Một record Java không implements Serializable và không thuộc String/byte[]/Map. SimpleMessageConverter tự biến thành JSON không?

**Đáp án:** Không. Nó không có quy tắc JSON tự động; cần converter riêng hoặc serialize payload thành chuỗi trước.

**Câu 5.** `JmsTemplate.send(session -> session.createTextMessage(...))` có gọi SimpleMessageConverter.toMessage không?

**Đáp án:** Không. Bạn đã tự tạo JMS Message; `send` chỉ gửi nó theo đường template.

**Câu 6.** Vì sao ObjectMessage cần chú ý bảo mật hơn TextMessage chứa JSON?

**Đáp án:** ObjectMessage dùng Java deserialization, chịu rủi ro khi deserialize class không đáng tin và phụ thuộc trust list/classpath; JSON cũng cần validation và type mapping an toàn, nhưng không mặc định yêu cầu Java object deserialization.

**Câu 7.** `receiveAndConvert` trả Map hay JSON String khi consumer nhận một MapMessage?

**Đáp án:** Một Java Map theo quy tắc SimpleMessageConverter, không phải JSON String.

**Câu 8.** Khi `receiveAndConvert("queue")` trả null sau timeout, có kết luận converter sai không?

**Đáp án:** Không. Có thể không nhận được message trong thời gian chờ. Cần kiểm tra broker queue, listener cạnh tranh và timeout.

**Câu 9.** Có thể nhận `Integer` bằng ObjectMessage không?

**Đáp án:** Có: `Integer` implements Serializable và không thuộc String, byte[] hay Map, với điều kiện provider cho phép serialization/deserialization.

**Câu 10.** Khi nào dùng `MappingJackson2MessageConverter` thay SimpleMessageConverter?

**Đáp án:** Khi cần JSON theo schema, ánh xạ DTO/record và tránh phụ thuộc Java ObjectMessage trong giao tiếp giữa các service, với cấu hình Jackson, type-id và trust controls phù hợp.

## Tài liệu tham khảo chính thức

- [Spring Framework — Sending a Message, Using JMS Message Converters](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/sending.html): mô tả SimpleMessageConverter mặc định, `convertAndSend`, `receiveAndConvert` và `MessagePostProcessor`.
- [Spring Framework API — SimpleMessageConverter (6.1.8)](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/jms/support/converter/SimpleMessageConverter.html): tập TextMessage, BytesMessage, MapMessage, ObjectMessage và quy tắc Java type.
- [Spring Framework API — MessageConverter (6.2.14)](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/support/converter/MessageConverter.html): `toMessage(Object, Session)` và `fromMessage(Message)`.
- [Spring Framework API — MappingJackson2MessageConverter (6.2.19)](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html): converter JSON và cấu hình message type.
- [Spring Boot 3.4 — JMS, ActiveMQ Artemis](https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html): starter, `native` mode và `ConnectionFactory`.
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): JMS message types, MapMessage, ObjectMessage, selector và message properties.
