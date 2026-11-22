# Đặt property có kiểu trên message (Spring Framework JMS)

**Ngữ cảnh:** Spring Framework - jms → Gửi thông điệp.

## 1. Property có kiểu là gì và dùng để làm gì?

Trong **JMS (Java Message Service, hiện thuộc Jakarta Messaging)**, một message có ba vùng thông tin: **standard headers**, **properties** và **body**. Body chứa dữ liệu nghiệp vụ; properties chứa metadata dưới dạng **tên và giá trị có kiểu**. Ví dụ một ứng dụng đặt hàng gửi body `"order-42"` nhưng gắn thêm các thuộc tính:

~~~text
Message
├── Headers: JMSMessageID, JMSDestination, JMSCorrelationID, ...
├── Properties:
│   ├── eventType      (String)  = "ORDER_CREATED"
│   ├── priorityLevel  (int)     = 7
│   ├── express        (boolean) = true
│   ├── amountMinor    (long)    = 125000
│   └── attempt        (int)     = 1
└── Body: TextMessage("order-42")
~~~

Property giúp các consumer đọc metadata mà không cần parse body và đặc biệt hỗ trợ **JMS message selector**. Ví dụ một consumer chỉ muốn nhận các sự kiện tạo đơn ưu tiên cao, giao nhanh:

~~~sql
eventType = 'ORDER_CREATED' AND priorityLevel >= 5 AND express = TRUE
~~~

Chính **kiểu được ghi** quyết định selector có thể so sánh đúng hay không: `priorityLevel = 7` kiểu `int` khác `priorityLevel = "7"` kiểu `String`, dù khi in log trông giống nhau.

Điều quan trọng cần nhớ:

- Properties nằm trong **JMS Message**, không phải method của `JmsTemplate` hay thuộc tính của broker.
- Producer đặt properties **trước khi gửi**; consumer đọc chúng từ message đã nhận.
- Một property nghiệp vụ như `priorityLevel` **không tự đặt** JMS standard header `JMSPriority`.
- Properties có thể giúp broker lọc message; chúng **không** tạo queue, không tự retry và không bảo đảm nghiệp vụ thành công.

Ví dụ trong bài dùng **Java 17+**, **Spring Framework 6.x / Spring Boot 3.x** và API `jakarta.jms.*`. Ứng dụng JMS cũ có thể dùng `javax.jms.*`; cần chọn library API và provider client đồng nhất, không trộn hai namespace không tương thích.

## 2. Tám kiểu property tiêu chuẩn của JMS

Interface `jakarta.jms.Message` hỗ trợ property values thuộc đúng **tám kiểu**:

| Kiểu | Setter | Getter | Một giá trị minh họa |
| --- | --- | --- | --- |
| `boolean` | `setBooleanProperty` | `getBooleanProperty` | `true` |
| `byte` | `setByteProperty` | `getByteProperty` | `(byte) 3` |
| `short` | `setShortProperty` | `getShortProperty` | `(short) 84` |
| `int` | `setIntProperty` | `getIntProperty` | `7` |
| `long` | `setLongProperty` | `getLongProperty` | `125_000L` |
| `float` | `setFloatProperty` | `getFloatProperty` | `0.75f` |
| `double` | `setDoubleProperty` | `getDoubleProperty` | `0.125d` |
| `String` | `setStringProperty` | `getStringProperty` | `"ORDER_CREATED"` |

Mọi setter/getter trên nhận **tên property** là tham số đầu tiên. Với một `Message message` vừa tạo và đang writable:

~~~java
message.setStringProperty("eventType", "ORDER_CREATED");
message.setIntProperty("priorityLevel", 7);
message.setBooleanProperty("express", true);
message.setLongProperty("amountMinor", 125_000L);
message.setByteProperty("shard", (byte) 3);
message.setShortProperty("regionCode", (short) 84);
message.setFloatProperty("score", 0.75f);
message.setDoubleProperty("ratio", 0.125d);
~~~

Đây là **đoạn trích**, cần tạo `message` từ một `jakarta.jms.Session` trước khi dùng. Các literal `125_000L`, `0.75f`, `0.125d` tuân theo cú pháp Java; trên message chỉ lưu giá trị tương ứng và kiểu.

Không có `setCharProperty`, `setBytesProperty`, `setDateProperty` hoặc `setBigDecimalProperty`. Đừng nhầm với `MapMessage` hay `StreamMessage`: những lớp đó có cách đặt field **trong body**, khác với message properties.

### 2.1. setObjectProperty nhận được những object nào?

Hai phương thức bổ sung:

~~~java
message.setObjectProperty("attempt", Integer.valueOf(1));
Object attempt = message.getObjectProperty("attempt");
~~~

`setObjectProperty(String, Object)` chỉ được JMS chuẩn cho phép lưu **Boolean, Byte, Short, Integer, Long, Float, Double và String**. Đó là các wrapper của primitive và String. `getObjectProperty` trả object cùng kiểu đã lưu, ví dụ một `Integer` nếu producer đặt `Integer.valueOf(1)` hoặc dùng `setIntProperty`.

~~~java
Object attempt = message.getObjectProperty("attempt");
if (attempt instanceof Integer value) {
    System.out.println("attempt=" + value);
}
~~~

Sau khi property `attempt` được đặt thành số 1 kiểu int/Integer, dòng minh họa in:

~~~text
attempt=1
~~~

**Không hợp lệ** nếu muốn lưu trực tiếp các object tùy ý như `UUID`, `BigDecimal`, `Instant`, `LocalDate`, DTO/POJO, enum hoặc `byte[]` bằng `setObjectProperty`. JMS provider phải từ chối kiểu không nằm trong danh sách; không có cơ chế tự serialize object tùy ý ở cấp property.

Muốn lưu UUID hoặc thời điểm như metadata, chuyển có chủ đích:

~~~java
import java.time.Instant;
import java.util.UUID;

// Các phép chuyển giá trị có schema rõ ràng:
message.setStringProperty("eventId", UUID.randomUUID().toString());
message.setLongProperty("occurredAtMs", Instant.now().toEpochMilli());
~~~

Trong hệ thống thật, nên tạo `eventId`, `occurredAtMs` **một lần cho sự kiện** trước khi gửi; tránh mỗi lần retry tạo ID mới nếu business contract cần nhận diện trùng lặp.

Với số tiền, thường chọn `long` biểu diễn **minor units** (ví dụ đồng nhỏ nhất được hệ thống định nghĩa) hoặc chuyển decimal thành String theo một định dạng thống nhất, không dùng `float/double` để tính toán tiền tệ chính xác.

## 3. Phân biệt properties với JMS headers và body

Các tên như `JMSCorrelationID`, `JMSMessageID`, `JMSPriority` là **standard headers**. Dù tồn tại trong Message, chúng không phải các application properties bình thường.

| Muốn đặt | Dùng API nào? | Ý nghĩa |
| --- | --- | --- |
| `eventType` | `message.setStringProperty("eventType", "...")` | Loại sự kiện cho selector |
| `priorityLevel` | `message.setIntProperty("priorityLevel", 7)` | Độ ưu tiên **nghiệp vụ** |
| `JMSCorrelationID` | `message.setJMSCorrelationID("corr-42")` | Liên hệ request/reply |
| `JMSReplyTo` | `message.setJMSReplyTo(destination)` | Nơi mong nhận phản hồi |
| `JMSPriority` | Producer QoS / Spring explicit QoS | Mức ưu tiên giao message theo JMS |
| `TextMessage` body | `session.createTextMessage("order-42")` | Nội dung nghiệp vụ |

Không thay header chuẩn bằng cách tự đặt một property cùng tên:

~~~java
// Sai ý định: dùng API property cho tên header chuẩn.
message.setStringProperty("JMSCorrelationID", "corr-42");

// Đúng: sử dụng API header chuyên dụng.
message.setJMSCorrelationID("corr-42");
~~~

Dòng đầu là **ví dụ phản diện**, có thể bị provider từ chối vì namespace đặc biệt; không dùng nó như một cách đặt correlation.

Một `MapMessage` cũng có các setter như `mapMessage.setInt("quantity", 3)` nhưng đây là **field trong body**. Selector không được truy cập field đó. Nếu muốn broker lọc trên `quantity`, bạn phải đưa một bản metadata thích hợp lên property:

~~~java
message.setIntProperty("quantity", 3); // property có thể tham gia selector
~~~

Đặt property là **quyết định thiết kế contract**, không phải bước tự động chuyển toàn bộ JSON hoặc MapMessage body thành hàng loạt properties.

## 4. Tên property: cú pháp, phân biệt chữ hoa, namespace

Property name phải phù hợp quy tắc **message selector identifier** (gần với identifier Java nhưng có các từ khóa riêng). Không dùng tên `null`, rỗng, bắt đầu bằng chữ số, có khoảng trắng hoặc dấu gạch nối. Tránh tên trùng các từ khóa `NULL`, `TRUE`, `FALSE`, `NOT`, `AND`, `OR`, `BETWEEN`, `LIKE`, `IN`, `IS` và `ESCAPE`.

Nên đặt:

~~~text
eventType
priorityLevel
express
amountMinor
attempt
tenantId
traceId
occurredAtMs
~~~

Những tên này dễ dùng trong selector. Property names **phân biệt hoa/thường**: `eventType` khác `EventType`. Đừng đổi tên chỉ ở một phía producer/consumer.

Cẩn thận với namespace:

- `JMSX...` được **Jakarta Messaging** dành cho properties chuẩn như `JMSXGroupID`, `JMSXGroupSeq`; không tự đặt tên ứng dụng mới bằng tiền tố này.
- `JMS_...` dành cho **provider-specific properties**. Không dùng nó cho nghiệp vụ thông thường.
- JMS standard headers như `JMSCorrelationID` có getter/setter riêng, không xuất hiện như một application property thông thường.

Một số JMSX property (ví dụ `JMSXDeliveryCount`) do provider gán/điều khiển theo hợp đồng. Không tự giả mạo delivery count bằng setter tùy ý. Nếu muốn theo dõi số lần retry nghiệp vụ, dùng tên riêng `attempt` với semantics rõ ràng, phân biệt với broker redelivery.

## 5. Quy tắc chuyển kiểu khi đọc

JMS quy định bảng chuyển đổi **khi gọi getter**. Nếu property được ghi với kiểu ở cột trái, có thể đọc bằng getter cùng kiểu và một số kiểu mở rộng như sau:

| Ghi bằng | Ngoài getter cùng kiểu, còn có thể đọc bằng |
| --- | --- |
| `boolean` | `getStringProperty` |
| `byte` | `getShortProperty`, `getIntProperty`, `getLongProperty`, `getStringProperty` |
| `short` | `getIntProperty`, `getLongProperty`, `getStringProperty` |
| `int` | `getLongProperty`, `getStringProperty` |
| `long` | `getStringProperty` |
| `float` | `getDoubleProperty`, `getStringProperty` |
| `double` | `getStringProperty` |
| `String` | Getter các primitive nếu String parse được |

Ví dụ đúng:

~~~java
message.setIntProperty("attempt", 2);

int exact = message.getIntProperty("attempt");      // 2
long widened = message.getLongProperty("attempt");  // 2L
String text = message.getStringProperty("attempt"); // "2"
~~~

Ví dụ sai:

~~~java
message.setLongProperty("amountMinor", 125_000L);
int amount = message.getIntProperty("amountMinor");
~~~

Phép chuyển từ `long` sang `int` **không** nằm trong bảng JMS. Lệnh getter không phù hợp có thể ném `MessageFormatException`, dù giá trị tình cờ còn nằm trong giới hạn `int`.

Với String, JMS cho phép parse sang primitive nếu nội dung hợp lệ:

~~~java
message.setStringProperty("attempt", "2");
int parsed = message.getIntProperty("attempt"); // 2

message.setStringProperty("attempt", "two");
int broken = message.getIntProperty("attempt"); // lỗi parse
~~~

Dòng cuối **cố ý là ví dụ lỗi**. Khi String không phải biểu diễn hợp lệ, getter số có thể ném `NumberFormatException`. Vì vậy, nếu dữ liệu thực chất là số, hãy gửi bằng `setIntProperty`/`setLongProperty` ngay từ đầu.

### 5.1. Selector không dùng bảng chuyển kiểu của getter

Đây là điểm cần đặc biệt nhớ. Với:

~~~java
message.setStringProperty("priorityLevel", "7");
~~~

selector:

~~~sql
priorityLevel >= 5
~~~

**không tự parse "7" thành int**. JMS selector so sánh trên **kiểu đã lưu**, khác với hành vi `getIntProperty("priorityLevel")` của code Java.

Muốn selector so sánh số:

~~~java
message.setIntProperty("priorityLevel", 7);
~~~

Và muốn lọc boolean:

~~~java
message.setBooleanProperty("express", true);
~~~

thì selector dùng:

~~~sql
priorityLevel >= 5 AND express = TRUE
~~~

Đặt `express` bằng `setStringProperty("express", "true")` sẽ lưu String, không có semantics boolean trong selector. String literal của selector dùng **nháy đơn**, chẳng hạn `eventType = 'ORDER_CREATED'`.

## 6. Gửi message có typed properties bằng JMS API thuần

Với Jakarta Messaging classic API, producer tạo `Message` bằng `Session`, đặt properties rồi gửi:

~~~java
package com.example;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

public final class ClassicTypedPropertySender {

    private ClassicTypedPropertySender() {}

    public static void send(ConnectionFactory factory) throws JMSException {
        try (Connection connection = factory.createConnection()) {
            Session session = connection.createSession(
                    false, Session.AUTO_ACKNOWLEDGE);
            Queue queue = session.createQueue("demo.orders.typed");

            try (MessageProducer producer = session.createProducer(queue)) {
                TextMessage message =
                        session.createTextMessage("order-42");
                message.setStringProperty("eventType", "ORDER_CREATED");
                message.setIntProperty("priorityLevel", 7);
                message.setBooleanProperty("express", true);
                message.setLongProperty("amountMinor", 125_000L);
                message.setObjectProperty(
                        "attempt", Integer.valueOf(1));
                producer.send(message);
            }
        }
    }
}
~~~

Đây là **class không có hàm main**; có thể biên dịch với API JMS nhưng để gửi cần provider-specific `ConnectionFactory` thực tế, broker, credentials và queue hợp lệ. `Connection.start()` bắt buộc cho message delivery ở consumer classic API, nhưng không bắt buộc cho producer gửi message.

API `JMSContext` rút gọn cũng có thể làm tương tự:

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;

// factory là ConnectionFactory đã cấu hình.
try (JMSContext context = factory.createContext()) {
    Queue queue = context.createQueue("demo.orders.typed");
    TextMessage message = context.createTextMessage("order-42");
    message.setIntProperty("priorityLevel", 7);
    message.setStringProperty("eventType", "ORDER_CREATED");

    context.createProducer().send(queue, message);
}
~~~

Đây là trích đoạn bên trong một method, không phải file độc lập. Tên `createQueue` chỉ tạo object destination logic: việc broker provision queue có thể đòi hỏi cấu hình/chuẩn bị riêng.

## 7. Cách làm trong Spring JMS: MessagePostProcessor

Ứng dụng Spring thường dùng `JmsTemplate.convertAndSend(...)`. Template gọi `MessageConverter` biến payload thành JMS Message, sau đó có thể cho phép chỉnh message trước khi gửi qua callback **`org.springframework.jms.core.MessagePostProcessor`**.

~~~java
import org.springframework.jms.core.JmsTemplate;

// jmsTemplate là Spring bean đã được inject.
jmsTemplate.convertAndSend(
        "demo.orders.typed",
        "order-42",
        message -> {
            message.setStringProperty("eventType", "ORDER_CREATED");
            message.setIntProperty("priorityLevel", 7);
            message.setBooleanProperty("express", true);
            message.setLongProperty("amountMinor", 125_000L);
            message.setObjectProperty("attempt", Integer.valueOf(1));
            return message;
        });
~~~

Trình tự:

1. `"demo.orders.typed"` là destination được truyền tường minh; `"order-42"` là payload.
2. Converter mặc định chuyển `String` thành `TextMessage`.
3. `MessagePostProcessor` nhận một `jakarta.jms.Message` **đã được tạo và còn writable**.
4. Callback đặt properties và trả lại message.
5. `JmsTemplate` gửi message thông qua JMS provider.

Không nhầm `org.springframework.jms.core.MessagePostProcessor` với một interface xử lý `org.springframework.messaging.Message<?>`. Đó là hai lớp abstraction khác nhau. Đoạn trên đặt **native JMS properties** trên đối tượng JMS Message.

### 7.1. Dùng MessageCreator khi muốn tự tạo message

~~~java
jmsTemplate.send("demo.orders.typed", session -> {
    var text = session.createTextMessage("order-42");
    text.setStringProperty("eventType", "ORDER_CREATED");
    text.setIntProperty("priorityLevel", 7);
    text.setBooleanProperty("express", true);
    return text;
});
~~~

Đoạn trên dùng callback `MessageCreator`, nơi bạn trực tiếp tạo JMS Message bằng `Session`. Cách này hữu ích nếu muốn `BytesMessage`, `MapMessage` hoặc logic tạo message tùy biến.

| Nhu cầu | Lựa chọn |
| --- | --- |
| Payload String/byte[]/loại đã được converter hỗ trợ, chỉ cần gắn property | `convertAndSend(..., MessagePostProcessor)` |
| Muốn tạo message thủ công, chọn chính xác message type | `send(..., MessageCreator)` |
| Không dùng Spring | JMS `Session` hoặc `JMSContext` và producer |
| Cần lọc ở consumer | Typed properties đúng contract kết hợp selector |

**Lưu ý:** typed properties không quyết định `Destination` hoặc ack/transaction. Các cấu hình đó vẫn ở `JmsTemplate`, container, `ConnectionFactory` và broker.

## 8. Ví dụ chạy được: Java 17+, Spring Boot 3.x, Apache ActiveMQ Artemis

Ví dụ hoàn chỉnh gồm producer đặt các property nhiều kiểu, consumer dùng selector và đọc lại.

### 8.1. Chuẩn bị

Tạo dự án Maven từ [Spring Initializr](https://start.spring.io/) với Java 17+, group `com.example`, artifact `jms-typed-properties` và dependency **Spring for Apache ActiveMQ Artemis** (starter `org.springframework.boot:spring-boot-starter-artemis`). Khởi động Artemis broker ngoài ứng dụng ở `tcp://localhost:61616`, có quyền send/consume queue `demo.orders.typed`. Queue phải được provision hoặc broker được cấu hình auto-create phù hợp.

Đặt biến môi trường `ARTEMIS_USER` và `ARTEMIS_PASSWORD`. Tạo file `src/main/resources/application.properties`:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=${ARTEMIS_USER}
spring.artemis.password=${ARTEMIS_PASSWORD}
spring.jms.pub-sub-domain=false
~~~

`native` kết nối tới broker đã chạy; nó **không** tự tạo broker nhúng.

Tạo file `src/main/java/com/example/JmsTypedPropertiesApplication.java`:

~~~java
package com.example;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class JmsTypedPropertiesApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsTypedPropertiesApplication.class, args);
    }

    @Bean
    ApplicationRunner publish(JmsTemplate template) {
        return args -> {
            template.convertAndSend(
                    "demo.orders.typed",
                    "order-42",
                    message -> {
                        message.setStringProperty(
                                "eventType", "ORDER_CREATED");
                        message.setIntProperty("priorityLevel", 7);
                        message.setBooleanProperty("express", true);
                        message.setLongProperty(
                                "amountMinor", 125_000L);
                        message.setObjectProperty(
                                "attempt", Integer.valueOf(1));
                        return message;
                    });
            System.out.println("SENT order-42");
        };
    }
}

@Component
class TypedOrderConsumer {

    @JmsListener(
            destination = "demo.orders.typed",
            selector = "eventType = 'ORDER_CREATED' "
                    + "AND priorityLevel >= 5 AND express = TRUE")
    public void receive(Message message) throws JMSException {
        if (!(message instanceof TextMessage textMessage)) {
            throw new IllegalArgumentException(
                    "Expected TextMessage");
        }

        System.out.println("BODY=" + textMessage.getText());
        System.out.println("eventType="
                + message.getStringProperty("eventType"));
        System.out.println("priorityLevel="
                + message.getIntProperty("priorityLevel"));
        System.out.println("priorityAsLong="
                + message.getLongProperty("priorityLevel"));
        System.out.println("express="
                + message.getBooleanProperty("express"));
        System.out.println("amountMinor="
                + message.getLongProperty("amountMinor"));
        System.out.println("attemptIsInteger="
                + (message.getObjectProperty("attempt")
                        instanceof Integer));
        System.out.println("hasUnknownProperty="
                + message.propertyExists("unknownProperty"));
    }
}
~~~

Một file Java có đúng một public class với tên khớp file; class listener package-private vẫn được Spring component-scan. Spring Boot với starter Artemis và cấu hình đúng tạo JMS infrastructure và `JmsTemplate`. Consumer nhận **raw `jakarta.jms.Message`**, nên đọc property bằng các getter JMS chuẩn, không qua JSON converter.

### 8.2. Lệnh chạy và output

Ở thư mục dự án:

~~~bash
mvn spring-boot:run
~~~

Trên Windows, nếu dùng Maven Wrapper:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Trong lần chạy sạch với broker/destination/credentials đúng, không có message cũ và không có consumer khác lấy message, các dòng nghiệp vụ kỳ vọng:

~~~text
SENT order-42
BODY=order-42
eventType=ORDER_CREATED
priorityLevel=7
priorityAsLong=7
express=true
amountMinor=125000
attemptIsInteger=true
hasUnknownProperty=false
~~~

Các startup logs khác cũng xuất hiện. Listener chạy bất đồng bộ nên `SENT order-42` có thể xuất hiện trước hoặc sau khối log của consumer; các dòng bên trong một lần gọi `receive()` có thứ tự như code. Đây là output **kỳ vọng theo điều kiện**, không phải bằng chứng đã khởi chạy broker/Maven trong môi trường soạn bài.

Giải thích:

- Message converter mặc định biến `"order-42"` thành `TextMessage`.
- Callback đặt `eventType` String, `priorityLevel` int và `express` boolean, vì vậy selector có thể match.
- `getLongProperty("priorityLevel")` trả 7 vì chuyển kiểu `int → long` được JMS cho phép.
- `attempt` được lưu bằng `Integer`, nên `instanceof Integer` là true.
- `propertyExists("unknownProperty")` trả false, vì producer không đặt property ấy.

## 9. Đọc và kiểm tra properties an toàn ở consumer

API của `Message` có thêm:

~~~java
boolean propertyExists(String name) throws JMSException;
Object getObjectProperty(String name) throws JMSException;
java.util.Enumeration<?> getPropertyNames() throws JMSException;
~~~

Ví dụ trích đoạn với message đã nhận:

~~~java
if (message.propertyExists("attempt")) {
    Object value = message.getObjectProperty("attempt");
    if (value instanceof Integer attempt) {
        System.out.println("attempt=" + attempt);
    }
}

var propertyNames = message.getPropertyNames();
while (propertyNames.hasMoreElements()) {
    String name = (String) propertyNames.nextElement();
    System.out.println(
            name + "=" + message.getObjectProperty(name));
}
~~~

Thứ tự các tên do `getPropertyNames()` trả về **không được JMS chuẩn bảo đảm**. Đừng so sánh stdout có thứ tự cố định từ vòng lặp ấy. API này liệt kê properties, **không** liệt kê standard headers như `JMSMessageID`.

Khi property không tồn tại:

~~~java
boolean exists = message.propertyExists("traceId"); // false
Object value = message.getObjectProperty("traceId"); // null
String text = message.getStringProperty("traceId");  // null
~~~

Các kết quả trên giả định message thực sự không có property `traceId`. **Không mặc định** mọi primitive getter cho property thiếu sẽ trả 0 hoặc false: hãy kiểm tra `propertyExists` trước khi đọc property bắt buộc. Với message không tin cậy, còn cần validation tên, kiểu, khoảng giá trị và business schema.

### 9.1. Properties nhận được là read-only

Một message mới do producer tạo có properties writable. Khi consumer nhận message, properties chuyển sang **read-only**. Vì vậy:

~~~java
// incoming là message vừa được consumer nhận.
incoming.setIntProperty("attempt", 2);
~~~

có thể ném `MessageNotWriteableException`. Phương thức `clearProperties()` xóa **tất cả properties** và làm phần properties ghi được trở lại; nó **không** xóa body hay standard headers.

Tuy nhiên không nên `clearProperties` trên message đã nhận nếu chỉ muốn sửa một trường, vì bạn sẽ vô tình xóa metadata khác. Khi muốn gửi tiếp hoặc trả lời, thường dễ kiểm soát hơn nếu **tạo một message mới** rồi copy những trường cần thiết, với kiểu/contract rõ ràng. Mutate một Java object đã nhận cũng không có nghĩa broker tự cập nhật message gốc hoặc tự gửi lại message.

## 10. Selector vận hành theo kiểu property được ghi

Một JMS selector là biểu thức dạng SQL92 hạn chế, đánh giá dựa trên **properties và một số standard headers được phép**. Nó **không thể** đọc field trong JSON, `MapMessage` hoặc body String.

| Property được ghi | Selector | Diễn giải |
| --- | --- | --- |
| `setIntProperty("priorityLevel", 7)` | `priorityLevel >= 5` | So sánh số đúng |
| `setStringProperty("priorityLevel", "7")` | `priorityLevel >= 5` | Không tự parse String thành số |
| `setBooleanProperty("express", true)` | `express = TRUE` | So sánh Boolean |
| `setStringProperty("express", "true")` | `express = TRUE` | Khác kiểu, không match như Boolean |
| `setStringProperty("eventType", "ORDER_CREATED")` | `eventType = 'ORDER_CREATED'` | So sánh String đúng |
| Không có `tenantId` | `tenantId IS NULL` | Property thiếu có giá trị NULL |
| Không có `tenantId` | `tenantId = 'A'` | Kết quả UNKNOWN, không match |

Cú pháp String selector dùng **dấu nháy đơn**. Tên identifier phân biệt chữ hoa/thường. Nếu chuỗi literal có nháy đơn, cần escape theo quy tắc selector bằng nháy đơn kép. Không ghép trực tiếp user input chưa kiểm soát vào selector.

Với `@JmsListener`:

~~~java
@JmsListener(
    destination = "demo.orders.typed",
    selector = "eventType = 'ORDER_CREATED' AND priorityLevel >= 5")
public void consume(Message message) {
    // Chỉ các message thỏa selector mới được chuyển tới listener này.
}
~~~

Đây là trích đoạn, muốn biên dịch cần imports và class chứa method. Selector nằm ở **consumer side**, nhưng producer phải chịu trách nhiệm đặt đúng **kiểu metadata**. Một sai khác giữa producer và selector có thể khiến consumer không nhận message, chứ không nhất thiết ném exception trong method listener.

Các standard headers được selector cho phép tham chiếu có tập giới hạn (ví dụ `JMSCorrelationID`, `JMSPriority`); không dùng `JMSDestination` hay `JMSReplyTo` như selector header chuẩn.

## 11. Những lỗi triển khai và cách khắc phục

| Lỗi/triệu chứng | Nguyên nhân | Khắc phục |
| --- | --- | --- |
| Selector `attempt > 1` không match `"2"` | Producer ghi String thay vì int | Ghi `setIntProperty` |
| `MessageFormatException` khi gọi getter | Kiểu chuyển không hợp lệ | Dùng getter đúng kiểu hoặc conversion chuẩn |
| `NumberFormatException` | String không parse được thành số | Kiểm tra dữ liệu, ghi số có kiểu ngay từ producer |
| `setObjectProperty` với DTO/UUID/Instant thất bại | Không nằm trong tập object hợp lệ | Dùng String/epoch long hoặc để trong body |
| `propertyExists` false | Sai tên, sai chữ hoa/thường, chưa đặt | Kiểm tra schema và producer |
| Không ghi được property trên message đã nhận | Properties read-only | Tạo message mới hoặc hiểu đúng `clearProperties` |
| Không đọc được metadata trong selector | Metadata chỉ có trong body | Đặt property dành cho broker-side filtering |
| `JMSCorrelationID` bị hiểu là application property | Dùng nhầm header API | Dùng `setJMSCorrelationID` |
| Set `priorityLevel` mà broker không ưu tiên delivery | Application property không phải `JMSPriority` | Dùng producer QoS nếu thật sự cần |
| Message tồn đọng khi consumer đổi selector | Tên/kiểu property giữa producer và listener lệch | Đồng bộ contract, versioning, quan sát queue depth |
| Gửi được nhưng listener không nhận | Sai queue, ACL, selector hoặc container lỗi | Kiểm tra broker metrics, logs và destination |
| Copy received message mất properties | `clearProperties` hoặc tạo message mới không copy | Chỉ rõ danh sách metadata bắt buộc khi forward |

### 11.1. Không lạm dụng metadata

Properties có thể được provider lưu và dùng để đánh giá selector nên có thể có chi phí xử lý riêng. Không nhét JSON lớn hay dữ liệu nhạy cảm vào properties nếu không cần. Body dùng cho nội dung nghiệp vụ; properties dùng cho metadata cần **selection, routing hoặc observability**. Tránh đặt password, token, dữ liệu cá nhân không cần thiết vào property vì broker admin/log có thể quan sát được.

### 11.2. Chuẩn hóa message contract

Producer và consumer cần thống nhất:

~~~yaml
destination: demo.orders.typed
body:
  type: TextMessage
  description: orderId
properties:
  eventType: {type: String, example: ORDER_CREATED}
  priorityLevel: {type: int, example: 7}
  express: {type: boolean, example: true}
  amountMinor: {type: long, example: 125000}
  attempt: {type: int, example: 1}
selector: "eventType = 'ORDER_CREATED' AND priorityLevel >= 5 AND express = TRUE"
~~~

Đây là **ví dụ tài liệu hợp đồng**, không phải file cấu hình `application.yml` chạy trực tiếp. Khi thay đổi tên property, kiểu hoặc đơn vị đo, phải kiểm tra compatibility với **message cũ còn trong broker** và các consumer chưa nâng cấp. Dùng field version phù hợp nếu hai phiên bản schema cùng hoạt động trong một giai đoạn.

## 12. Hướng dẫn kiểm chứng nhanh

1. Chạy Artemis broker và Spring Boot demo ở phần 8.
2. Quan sát listener nhận message có `priorityLevel=7` và `express=true`.
3. Thử đổi producer sang `setStringProperty("priorityLevel", "7")` trong môi trường test, giữ selector số `priorityLevel >= 5`. Message mới không thỏa so sánh numeric theo JMS selector.
4. Quan sát queue depth nếu message không match; không suy ra message biến mất chỉ vì listener không in log.
5. Đổi lại `setIntProperty`, chạy lại với destination/queue sạch để tránh message cũ làm nhiễu.
6. Kiểm tra property bằng `getObjectProperty`/`propertyExists` và xác nhận kiểu boxing đúng contract.

Tách riêng việc xác nhận **send hoàn tất** với **consumer đã xử lý thành công**. Typed properties giúp truyền metadata và lọc message; không tự bảo đảm transactional processing, idempotency, retry hay exactly-once theo nghiệp vụ.

## 13. Tự kiểm tra

**Câu 1.** Tại sao `setIntProperty("attempt", 2)` khác `setStringProperty("attempt", "2")`?

**Đáp án:** Một message lưu int, một message lưu String. Getter có thể hỗ trợ chuyển String sang số, nhưng selector không tự ép kiểu theo bảng getter.

**Câu 2.** `getLongProperty("attempt")` có hợp lệ nếu property được đặt bằng `setIntProperty("attempt", 2)`?

**Đáp án:** Có. Chuyển int sang long thuộc các conversion được JMS chuẩn yêu cầu.

**Câu 3.** Còn `getIntProperty("amountMinor")` khi producer đã gọi `setLongProperty("amountMinor", 125000L)`?

**Đáp án:** Không hợp lệ theo bảng chuyển kiểu JMS vì đây là chuyển hẹp long → int.

**Câu 4.** Có thể gọi `setObjectProperty("eventTime", Instant.now())` không?

**Đáp án:** Không. Instant không thuộc tập object JMS cho phép. Hãy chuyển sang String/epoch milliseconds hoặc body.

**Câu 5.** Tại sao `getPropertyNames()` không liệt kê `JMSCorrelationID`?

**Đáp án:** Vì đó là JMS standard header, không phải property.

**Câu 6.** Spring `MessagePostProcessor` đặt properties trước hay sau khi JMS provider nhận message?

**Đáp án:** Trước: sau khi converter tạo JMS Message và trước lời gọi gửi.

**Câu 7.** `setBooleanProperty("express", true)` so với `setStringProperty("express", "true")` ảnh hưởng thế nào đến selector `express = TRUE`?

**Đáp án:** Chỉ Boolean property khớp đúng kiểu; String không được selector tự parse thành boolean.

**Câu 8.** Có nên gọi `clearProperties()` trên received message chỉ để tăng số lần thử `attempt`?

**Đáp án:** Thường không, vì sẽ xóa toàn bộ properties khác. Tạo message mới/copy metadata theo contract nếu muốn forward hoặc retry nghiệp vụ.

## Tài liệu tham khảo chính thức

- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html) — mục 3.5 về message properties, bảng chuyển kiểu 3.5.4 và mục 3.8 về selector.
- [Jakarta Messaging API — Message](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message) — các typed setters/getters, `setObjectProperty`, `getPropertyNames`, `propertyExists`, `clearProperties` và read-only semantics.
- [Spring Framework — Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html) — `JmsTemplate`, `MessageCreator`, `MessagePostProcessor`.
- [Spring Framework — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html) — `@JmsListener` và message selectors.
- [Spring Boot — ActiveMQ Artemis and JMS](https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html) — JMS starter, auto-configuration, `native` broker mode.
