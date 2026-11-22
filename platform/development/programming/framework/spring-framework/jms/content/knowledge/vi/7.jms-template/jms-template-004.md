# JmsTemplate: phân biệt send và convertAndSend

**Phạm vi:** Spring Framework JMS, tập trung vào hai nhóm phương thức `JmsTemplate.send(...)` và `JmsTemplate.convertAndSend(...)`. Mục tiêu là đọc được chữ ký API, biết ai tạo `jakarta.jms.Message`, hiểu quá trình chuyển đổi payload, tự đặt header/property đúng thời điểm và chọn API phù hợp cho từng loại message.

**Môi trường minh họa:** Java 17+, Spring Framework 6.x / Spring Boot 3.x, Jakarta Messaging (`jakarta.jms`), broker JMS tương thích (ví dụ Apache ActiveMQ Artemis). Các ví dụ có thể dùng trực tiếp trong Spring Boot 3.x khi đã cấu hình `ConnectionFactory` và destination. Spring Framework thuần sử dụng cùng `JmsTemplate`, nhưng ứng dụng tự đăng ký các bean.

## 1. Câu trả lời trước tiên: cùng gửi JMS, khác người tạo Message

Cả hai API đều gửi một **JMS Message** tới **Destination** qua `ConnectionFactory`, `Session` và producer mà `JmsTemplate` quản lý. Điểm khác biệt nằm ở bước tạo message:

- **`send(...)`:** ứng dụng cung cấp một **`MessageCreator`**. Callback nhận `Session`, tự tạo `TextMessage`, `BytesMessage`, `MapMessage` hoặc kiểu message JMS cần thiết, tự đặt thuộc tính/header do ứng dụng sở hữu, rồi trả về `jakarta.jms.Message`. `JmsTemplate` đem message đó đi gửi. **Không có bước tự chuyển Object Java sang JMS Message bằng `MessageConverter`.**
- **`convertAndSend(...)`:** ứng dụng đưa một **Java object/payload**. `JmsTemplate` gọi **`MessageConverter.toMessage(object, session)`** để tạo JMS Message. Nếu cần thêm header/property, phiên bản có **`MessagePostProcessor`** cho phép sửa message **sau chuyển đổi nhưng trước khi gửi**.

~~~text
send(destination, MessageCreator)
    └─ callback: Session → tự tạo jakarta.jms.Message
                           → JmsTemplate gửi → provider/broker

convertAndSend(destination, Object)
    └─ MessageConverter: Object → jakarta.jms.Message
                                 → JmsTemplate gửi → provider/broker

convertAndSend(destination, Object, MessagePostProcessor)
    └─ MessageConverter: Object → jakarta.jms.Message
                                 → postProcessMessage(Message)
                                 → JmsTemplate gửi → provider/broker
~~~

Cả hai nhóm phương thức là **send của JmsTemplate**: `convertAndSend` không phải một giao thức JMS khác, không có nghĩa “bất đồng bộ”, và cũng không tự bảo đảm listener đã xử lý. Sau khi send thành công, message vẫn có thể đang chờ broker giao cho consumer.

## 2. Chữ ký API phải nhớ

Các overload điển hình của `org.springframework.jms.core.JmsTemplate`:

| Nhóm | Chữ ký | Điều ứng dụng đưa vào |
| --- | --- | --- |
| `send` | `send(String destinationName, MessageCreator creator)` | Tên destination và callback tự tạo JMS Message |
| `send` | `send(Destination destination, MessageCreator creator)` | Đối tượng JMS Destination và callback |
| `send` | `send(MessageCreator creator)` | Callback; cần cấu hình **default destination** |
| `convertAndSend` | `convertAndSend(String destinationName, Object message)` | Tên destination và Java object |
| `convertAndSend` | `convertAndSend(String destinationName, Object message, MessagePostProcessor postProcessor)` | Java object, sau đó callback chỉnh JMS Message |
| `convertAndSend` | `convertAndSend(Destination destination, Object message)` | Destination object và Java object |
| `convertAndSend` | `convertAndSend(Object message)` | Java object; cần **default destination** |

Hai callback có **kiểu và thời điểm khác nhau**:

~~~java
// Các snippet dưới đây giả định đã inject JmsTemplate jmsTemplate.
// MessageCreator: Session -> JMS Message.
jmsTemplate.send("orders.queue", session ->
        session.createTextMessage("OrderCreated"));

// MessagePostProcessor: JMS Message -> JMS Message.
// Nó chạy sau MessageConverter, trước send.
jmsTemplate.convertAndSend(
        "orders.queue",
        "OrderCreated",
        message -> {
            message.setStringProperty("eventType", "OrderCreated");
            return message;
        }
);
~~~

Trong Spring JMS:

- `MessageCreator` nằm ở `org.springframework.jms.core.MessageCreator`.
- `MessagePostProcessor` nằm ở `org.springframework.jms.core.MessagePostProcessor`.
- `MessageConverter` cho JMS nằm ở `org.springframework.jms.support.converter.MessageConverter`.
- `Message` mà creator/post-processor thao tác là **`jakarta.jms.Message`**; đừng nhầm với **`org.springframework.messaging.Message<?>`** ở Spring Messaging.

**Cả hai API trả về `void`.** Không có giá trị trả về mặc định là ID do broker tạo, status business, hay kết quả listener xử lý. `JmsTemplate` dịch các `JMSException` cần xử lý ở tầng JMS thành `org.springframework.jms.JmsException` (unchecked), còn lỗi conversion có thể là `MessageConversionException`.

## 3. Điểm giống nhau quan trọng hơn vẻ ngoài của tên hàm

| Khía cạnh | `send` | `convertAndSend` |
| --- | --- | --- |
| Kết nối broker | Dùng `ConnectionFactory` của `JmsTemplate` | Dùng cùng `ConnectionFactory` |
| Session/producer lifecycle | `JmsTemplate` tạo/lấy, sử dụng và cleanup theo cơ chế Spring | Tương tự |
| Destination | Theo tham số hoặc default destination | Tương tự |
| Cách dựng body | Ứng dụng tạo Message với `Session` | `MessageConverter` tạo Message từ Object |
| Kiểu Message | Do code của `MessageCreator` quyết định | Do converter quyết định |
| Properties/header do client đặt | Trong `MessageCreator` | Trong `MessagePostProcessor` hoặc converter tùy biến |
| Provider headers | Gán tại thời điểm send theo JMS | Tương tự |
| JMS QoS | Cấu hình trên `JmsTemplate`/provider | Tương tự |
| Transaction | Phụ thuộc Spring transaction/session/provider | Tương tự |
| Xử lý lỗi | `JmsException` và lỗi runtime khác | Thêm lỗi chuyển đổi payload |
| ACK của consumer | Không được xác nhận bởi việc gửi | Tương tự |
| Giá trị trả về | `void` | `void` |

**Không có chuyện** `send` mặc định “raw và nhanh hơn chắc chắn”, còn `convertAndSend` “đảm bảo reliable hơn”. Độ tin cậy chủ yếu liên quan delivery mode, transaction, broker policy, consumer ACK/commit, retry và idempotency. Converter có chi phí xử lý payload, nhưng quyết định hiệu năng phải dựa trên đo đạc với dữ liệu thực.

## 4. send: bạn nắm quyền tạo JMS Message

### 4.1. Tự tạo TextMessage kèm metadata

~~~java
import jakarta.jms.TextMessage;
import org.springframework.jms.core.JmsTemplate;

public final class ManualTextPublisher {
    private final JmsTemplate jmsTemplate;

    public ManualTextPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publish(String eventId, String correlationId) {
        jmsTemplate.send("orders.created", session -> {
            String json = """
                    {"type":"OrderCreated","orderId":"O-42","version":1}
                    """.strip();
            TextMessage message = session.createTextMessage(json);
            message.setStringProperty("eventId", eventId);
            message.setStringProperty("contentType", "application/json");
            message.setJMSCorrelationID(correlationId);
            return message;
        });
    }
}
~~~

Đây là class Java 17 **biên dịch trong dự án có Spring JMS**, không có `main` độc lập. Nó cần `JmsTemplate` được Spring cấu hình và broker/destination hợp lệ. `Session` truyền vào callback chính là session mà template sử dụng cho thao tác; bạn **không** tự tạo session khác rồi trả message thuộc context khác.

Ở đây:
1. Java text block tạo chuỗi JSON một cách tường minh.
2. `session.createTextMessage(json)` quyết định **kiểu JMS là `TextMessage`**.
3. `setStringProperty(...)` đặt application properties, dùng được cho selector/tracing nếu broker hỗ trợ.
4. `setJMSCorrelationID(...)` đặt client-controlled standard header; provider sẽ đặt các header thuộc trách nhiệm của provider trong send.
5. Callback trả message, Spring xử lý tài nguyên và send.

**Lợi thế của `send`:** bạn có toàn quyền điều khiển loại Message, encoding của bytes, cấu trúc MapMessage, custom headers, property names và những yếu tố không phù hợp với converter mặc định. Khi một message contract đòi định dạng/thuộc tính đặc biệt, đây là lựa chọn minh bạch.

### 4.2. Tạo BytesMessage và không vô tình ép sang TextMessage

~~~java
byte[] payload = new byte[] {0x01, 0x02, 0x03};

jmsTemplate.send("binary.tasks", session -> {
    var bytesMessage = session.createBytesMessage();
    bytesMessage.writeBytes(payload);
    bytesMessage.setStringProperty("contentType",
            "application/octet-stream");
    return bytesMessage;
});
~~~

Đoạn snippet giả định `jmsTemplate` đã có. Với `send`, kiểu và nội dung bytes được quyết định trực tiếp. Bạn chịu trách nhiệm **version/schema** của bytes và cách consumer giải mã; chỉ đặt `contentType` không giúp consumer tự hiểu format.

### 4.3. Không nên làm gì trong MessageCreator?

- Đừng đóng `Session`, `Connection` hoặc `MessageProducer` của Spring trong callback.
- Đừng thực hiện I/O, HTTP call hoặc DB transaction nặng chỉ để dựng một message; callback nên tập trung tạo message.
- Đừng giả định đã có `JMSMessageID`, `JMSTimestamp` hoặc `JMSExpiration` do provider cấp **trước khi send**. `MessageCreator` chạy **trước** thao tác send.
- Đừng tự set `JMSMessageID` với hy vọng đó là business event ID; provider quản lý ID JMS khi gửi. Hãy dùng property nghiệp vụ `eventId`/`commandId`.
- Đừng trả về message tạo từ một `Session` khác hoặc giữ reference của message để sửa bất đồng bộ sau khi callback kết thúc.

## 5. convertAndSend: bạn đưa Object, MessageConverter tạo JMS Message

Ví dụ tương đương với `TextMessage` ở trên nếu đang dùng **`SimpleMessageConverter` mặc định**:

~~~java
jmsTemplate.convertAndSend(
        "orders.created",
        "{\"type\":\"OrderCreated\",\"orderId\":\"O-42\",\"version\":1}",
        message -> {
            message.setStringProperty("eventId", eventId);
            message.setStringProperty("contentType", "application/json");
            message.setJMSCorrelationID(correlationId);
            return message;
        }
);
~~~

**Với default converter**, `String` thành `TextMessage`. Nội dung body và metadata có thể giống ví dụ `send` nếu các giá trị đầu vào tương đương. **Khác nhau trong trách nhiệm**: bạn không viết `session.createTextMessage(...)`; việc tạo Message do converter làm.

### 5.1. Phía dưới lớp abstraction có chuyện gì?

Một cách hình dung luồng thực thi (không phải source code nội bộ từng version):

~~~text
Ứng dụng gọi convertAndSend(destination, payload, postProcessor)
  ├─ JmsTemplate dùng MessageConverter đã cấu hình
  ├─ converter.toMessage(payload, Session)
  │     └─ tạo TextMessage / BytesMessage / MapMessage / ...
  ├─ postProcessor.postProcessMessage(jmsMessage)
  │     └─ thêm client properties/header hoặc chỉnh message
  ├─ provider send JMS Message
  ├─ provider có thể tạo ID/timestamp/QoS metadata
  └─ JmsTemplate giải phóng hoặc trả tài nguyên cho cache/pool
~~~

Nếu converter thất bại, `postProcessor` **chưa chạy**, và provider **chưa được yêu cầu gửi thông điệp đó**. Nếu callback ném lỗi, message cũng chưa được gửi thành công. Nếu provider send lỗi ở ranh giới mạng, trạng thái broker có thể **không chắc chắn**; đừng xem mọi exception là bằng chứng “chắc chắn chưa gửi”.

### 5.2. Object được chuyển không đồng nghĩa JSON

~~~java
jmsTemplate.convertAndSend("orders.created", "hello");
// Với SimpleMessageConverter → TextMessage, body là "hello".

jmsTemplate.convertAndSend(
        "orders.created",
        new byte[] {1, 2, 3});
// Với SimpleMessageConverter → BytesMessage.

jmsTemplate.convertAndSend(
        "orders.created",
        java.util.Map.of("orderId", "O-42", "status", "CREATED"));
// Với SimpleMessageConverter → MapMessage.
~~~

**Bẫy phổ biến:** `convertAndSend("orders.created", new OrderCreated(...))` **không tự hiểu rằng phải serialise POJO thành JSON**. Nếu dùng `SimpleMessageConverter`, một object có `Serializable` có thể được chuyển thành `ObjectMessage` (phụ thuộc khả năng serialize); object không phù hợp có thể gây `MessageConversionException`. `ObjectMessage` phụ thuộc Java classpath, có rủi ro deserialize từ dữ liệu không tin cậy, và thường không phù hợp giao tiếp đa ngôn ngữ.

Nếu muốn JSON chuẩn giữa các dịch vụ, **cấu hình một JMS `MessageConverter` cho JSON** và thống nhất schema/version/field names, không chỉ thay tên phương thức.

## 6. Bảng ánh xạ của SimpleMessageConverter

Đây là converter đơn giản Spring dùng theo mặc định khi không cấu hình khác:

| Đầu vào Java | JMS Message thường tạo | Lưu ý |
| --- | --- | --- |
| `String` | `TextMessage` | Không parse/kiểm tra xem chuỗi có phải JSON hợp lệ |
| `byte[]` | `BytesMessage` | Không tự mã hóa schema |
| `Map<String, ...>` | `MapMessage` | Value phải tương thích kiểu JMS MapMessage; nested POJO không tự thành JSON |
| Object `Serializable` không thuộc các dạng trên | `ObjectMessage` | Java serialization, class/schema phụ thuộc và rủi ro bảo mật |
| Object không hỗ trợ | Exception khi chuyển đổi | Không có “fallback JSON” mặc định |

Đối với **`MapMessage`**, JMS cho phép một tập kiểu dữ liệu cơ bản như boolean, byte, short, char, int, long, float, double, String và byte[]. Không nhầm với JSON object lồng nhau; `Map<String, Object>` với nested `Map` hoặc `List` sẽ không tự tạo JSON bằng `SimpleMessageConverter`.

`receiveAndConvert(...)` là phép chuyển đổi chiều nhận; nó dùng converter của template. `@JmsListener` còn phụ thuộc message converter của **listener container factory**, nên “producer convert được” **không chứng minh** listener nào cũng tự deserialize được POJO. Hai phía phải có hợp đồng tương thích.

## 7. MessageCreator khác MessagePostProcessor ở đúng thời điểm

| | `MessageCreator` | `MessagePostProcessor` |
| --- | --- | --- |
| Sử dụng chính ở | `send(...)` | `convertAndSend(..., postProcessor)` |
| Tham số callback | `jakarta.jms.Session` | `jakarta.jms.Message` |
| Giá trị trả về | `jakarta.jms.Message` mới tạo | `jakarta.jms.Message` sau chỉnh sửa (có thể là cùng object) |
| Nhiệm vụ | Tạo body và kiểu JMS, gán header/property | Hoàn thiện header/property sau khi converter tạo message |
| Converter có chạy trước không? | **Không**, vì ứng dụng đã dựng JMS message | **Có**, khi dùng `convertAndSend` |
| Có biết JMSMessageID do provider gán không? | **Không**, vì send chưa xảy ra | **Không**, vì post-processor vẫn chạy trước send |

Ví dụ tương đương về tác dụng:

~~~java
// A. Tự tạo message trong callback của send.
jmsTemplate.send("orders.created", session -> {
    var m = session.createTextMessage("OrderCreated");
    m.setStringProperty("eventId", "evt-1001");
    return m;
});

// B. Để converter tạo message, rồi thêm property.
jmsTemplate.convertAndSend(
        "orders.created",
        "OrderCreated",
        m -> {
            m.setStringProperty("eventId", "evt-1001");
            return m;
        }
);
~~~

Với default converter, cả A và B đều tạo `TextMessage` body `OrderCreated` cùng property `eventId`. Nhưng nếu sau đó đổi converter sang JSON và chuyển payload phức tạp, **kết quả B có thể đổi**, còn A vẫn do code tự dựng.

**Đặc biệt:** callback trong `convertAndSend` có overload `MessagePostProcessor`, không phải lambda nhận `Session`. Viết `session -> session.createTextMessage(...)` bên trong `convertAndSend` là sai mô hình; với `send` thì đúng.

## 8. Ví dụ Spring Boot 3.x có thể chạy: so sánh trên cùng broker

Bài thực hành này tạo **ba message** và gửi tới **một queue** để trực tiếp thấy kết quả:
- `send` tạo `TextMessage` thủ công.
- `convertAndSend` chuyển `String` thành `TextMessage`.
- `convertAndSend` chuyển `Map` thành `MapMessage`.

Ví dụ dùng **Spring Boot 3.3.13** để minh họa API Jakarta JMS của Spring 6.1; phiên bản này đã kết thúc open-source support, vì vậy dự án mới nên chọn nhánh Boot hiện còn được hỗ trợ theo chính sách tổ chức. Cần broker Artemis chạy ngoài ứng dụng, một user có quyền send/consume, và queue `demo.send-modes` tồn tại hoặc provider/broker cho phép tự tạo.

### 8.1. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
~~~

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'jms-send-modes'
~~~

### 8.2. application.yaml

~~~yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
  jms:
    pub-sub-domain: false
~~~

**Cung cấp mật khẩu qua biến môi trường `SPRING_ARTEMIS_PASSWORD`** của tiến trình khởi động hoặc secret manager, không ghi vào Git. `user: demo` chỉ là ví dụ: phải dùng tài khoản thật do broker cấp; nếu broker không bật authentication và có quy ước kết nối khác thì điều chỉnh cấu hình tương ứng. Không có broker thực thì ứng dụng không thể chứng minh send/receive đã chạy.

### 8.3. Java đầy đủ trong một tệp

Lưu vào `src/main/java/example/jmsdemo/SendModesApplication.java`:

~~~java
package example.jmsdemo;

import java.util.Map;

import jakarta.jms.JMSException;
import jakarta.jms.MapMessage;
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
public class SendModesApplication {

    public static void main(String[] args) {
        SpringApplication.run(SendModesApplication.class, args);
    }

    @Bean
    ApplicationRunner sendExamples(JmsTemplate template) {
        return args -> {
            String destination = "demo.send-modes";

            // 1. Tự dựng một TextMessage bằng Session.
            template.send(destination, session -> {
                TextMessage message =
                        session.createTextMessage("hello from send");
                message.setStringProperty("source", "send");
                return message;
            });

            // 2. String được SimpleMessageConverter đổi thành TextMessage.
            template.convertAndSend(
                    destination,
                    "hello from convertAndSend",
                    message -> {
                        message.setStringProperty(
                                "source", "convertAndSend");
                        return message;
                    }
            );

            // 3. Map được SimpleMessageConverter đổi thành MapMessage.
            template.convertAndSend(
                    destination,
                    Map.of("orderId", "O-42", "status", "CREATED"),
                    message -> {
                        message.setStringProperty("source", "map");
                        return message;
                    }
            );
        };
    }
}

@Component
class RawMessageInspector {

    @JmsListener(destination = "demo.send-modes")
    public void inspect(Message message) throws JMSException {
        String source = message.getStringProperty("source");

        if (message instanceof TextMessage text) {
            System.out.printf("%s | TextMessage | %s%n",
                    source, text.getText());
        } else if (message instanceof MapMessage map) {
            System.out.printf("%s | MapMessage | orderId=%s%n",
                    source, map.getString("orderId"));
        } else {
            System.out.printf("%s | %s%n",
                    source, message.getClass().getSimpleName());
        }
    }
}
~~~

### 8.4. Chạy và đọc kết quả

Khi đã cấu hình broker/credential/queue và có Gradle wrapper tương thích:

~~~bash
./gradlew bootRun
~~~

Các dòng nghiệp vụ có thể xuất hiện:

~~~text
send | TextMessage | hello from send
convertAndSend | TextMessage | hello from convertAndSend
map | MapMessage | orderId=O-42
~~~

**Đây là ví dụ các dòng có thể quan sát, không phải stdout đầy đủ hoặc thứ tự được đảm bảo.** Listener chạy bất đồng bộ; broker chưa sẵn sàng, lỗi credential, routing, nhiều consumer, retry hoặc log framework làm thời điểm/thứ tự khác nhau. `ApplicationRunner` gửi **mỗi khi ứng dụng khởi động**; đây là hành vi dành cho demo, không phải mẫu phát event từ giao dịch nghiệp vụ thật.

**Kết luận có thể kiểm chứng:** hai lệnh đầu ra cùng một **loại** JMS `TextMessage` dù cách tạo khác nhau; lệnh thứ ba là `MapMessage` do converter mặc định chọn. Queue và listener không phân biệt message được tạo bằng API send nào, vì nó chỉ nhận **JMS Message**.

## 9. Khi bạn cần gửi POJO dưới dạng JSON

Đối với event kiểu `OrderCreated`, cách tự xây dựng JSON string qua `send` hoạt động nhưng dễ trùng logic serialization/schema. `convertAndSend` với JSON converter sẽ gọn hơn nếu nhiều event dùng chung một format.

### 9.1. Đăng ký JMS converter phù hợp với Spring 6.x

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageConverter;
import org.springframework.jms.support.converter.MessageType;

@Configuration
class JmsJsonConfiguration {

    @Bean
    MessageConverter jmsMessageConverter() {
        var converter = new MappingJackson2MessageConverter();
        converter.setTargetType(MessageType.TEXT);
        converter.setTypeIdPropertyName("_type");
        return converter;
    }
}
~~~

Khi dùng class này, cần dependency Jackson 2 (`com.fasterxml.jackson.core:jackson-databind`) trong runtime; với Gradle thêm:

~~~groovy
dependencies {
    implementation 'com.fasterxml.jackson.core:jackson-databind'
}
~~~

Với Spring Boot 3.x, bean `MessageConverter` có thể được dùng bởi `JmsTemplate` và listener factory **do Boot auto-configure**, tùy phiên bản/điều kiện. Nếu bạn **tự khai báo** `JmsTemplate` hoặc một listener factory riêng, phải kiểm tra và gắn converter tương ứng; đừng mặc định mỗi đường đọc đều được cấu hình giống nhau.

### 9.2. Gửi domain object

~~~java
record OrderCreated(
        String eventId,
        String orderId,
        int schemaVersion
) {}

OrderCreated event =
        new OrderCreated("evt-1001", "O-42", 1);

jmsTemplate.convertAndSend(
        "orders.events",
        event,
        message -> {
            message.setStringProperty("eventId", event.eventId());
            message.setStringProperty(
                    "contentType", "application/json");
            return message;
        }
);
~~~

Đây là snippet Java 17 nằm trong class/method của ứng dụng có `JmsTemplate` và converter JSON đã cấu hình. `MappingJackson2MessageConverter` biến POJO thành JSON trong `TextMessage` khi `MessageType.TEXT` được chọn. `_type` là JMS **property** hỗ trợ converter quyết định kiểu Java khi deserialize; tên, mapping và mức tin cậy của type metadata cần được các ứng dụng thống nhất trước khi trao đổi xuyên service.

**Hạn chế interoperability:** type ID gắn class Java nội bộ không phải hợp đồng lý tưởng giữa các ngôn ngữ. Nếu trao đổi rộng rãi, thống nhất `eventType`, `schemaVersion` và schema ở tầng nghiệp vụ, giới hạn allowed types và cấu hình converter phù hợp; đừng tùy ý deserialize class do message bên ngoài chỉ định.

**Không ảnh hưởng `send`:** đoạn `jmsTemplate.send(..., session -> session.createTextMessage(json))` vẫn là TextMessage do code của bạn tạo, **không đi qua** bean JSON converter. Một thay đổi converter có thể tác động `convertAndSend` và `receiveAndConvert`, nhưng không tự rewrite những message được tạo thủ công.

### 9.3. Nếu consumer cần nhận object gì?

Producer tạo JSON TextMessage không khiến mọi consumer tự động nhận một record `OrderCreated`. Consumer phải có converter/schema tương thích hoặc tự parse JSON. Trong Spring:
- `@JmsListener` có thể nhận raw `jakarta.jms.Message` để kiểm tra trực tiếp.
- `@JmsListener` nhận `String`/POJO phụ thuộc cách Spring JMS listener argument resolution và converter được gắn với listener factory.
- Consumer ở ngôn ngữ khác cần schema/documentation và version policy; không hiểu Java class name.

**Giữ event envelope ổn định:** event ID, schema version, event type, thời gian nghiệp vụ và idempotency key nên nằm trong hợp đồng, không phó mặc JMSMessageID do provider tự tạo.

## 10. Header, property và JMS QoS: ở API nào đặt?

### 10.1. Metadata do ứng dụng đặt trước send

Hai cách hợp lệ:

~~~java
// send: đặt property trong MessageCreator.
jmsTemplate.send("orders.events", session -> {
    TextMessage message = session.createTextMessage("OrderCreated");
    message.setStringProperty("eventId", "evt-1001");
    message.setJMSCorrelationID("checkout-42");
    return message;
});

// convertAndSend: đặt property trong MessagePostProcessor.
jmsTemplate.convertAndSend(
        "orders.events", "OrderCreated",
        message -> {
            message.setStringProperty("eventId", "evt-1001");
            message.setJMSCorrelationID("checkout-42");
            return message;
        }
);
~~~

Ứng dụng nên dùng `setStringProperty`, `setIntProperty` và các setter JMS property tương ứng cho metadata do client sở hữu. `JMSCorrelationID` và `JMSReplyTo` là header ứng dụng có thể đặt. `JMSMessageID`, `JMSTimestamp`, `JMSDestination`, `JMSExpiration` và các header provider-controlled được provider xác lập khi send; đừng cố đặt chúng trước send để thay đổi policy.

**Điểm chốt:** `MessageCreator` và `MessagePostProcessor` **đều chạy trước provider send**. Vì vậy, cả hai đều **chưa có `JMSMessageID` đáng tin cho lần gửi hiện tại**. Muốn truy vết khi nhận, ghi cả `eventId` do ứng dụng tạo và `JMSMessageID` do provider cấp ở consumer hoặc ở nơi hỗ trợ đọc sau send.

### 10.2. QoS thuộc JmsTemplate/provider, không thuộc tên phương thức

~~~java
jmsTemplate.setExplicitQosEnabled(true);
jmsTemplate.setDeliveryMode(jakarta.jms.DeliveryMode.PERSISTENT);
jmsTemplate.setPriority(5);
jmsTemplate.setTimeToLive(60_000L);
~~~

Đây là **snippet cấu hình bean**, không nên thay đổi một singleton `JmsTemplate` liên tục trong từng request/thread. Khi muốn `setDeliveryMode`, `setPriority`, `setTimeToLive` trên template có hiệu lực tường minh, cần `setExplicitQosEnabled(true)`. Nếu không, Spring có thể để provider áp dụng default/administered QoS. Các setter ảnh hưởng tới **cả hai đường `send` và `convertAndSend`** trên template đó.

- `PERSISTENT` là yêu cầu bảo vệ message trước lỗi provider trong phạm vi chuẩn và broker config; **không** đồng nghĩa consumer đã xử lý.
- `priority` từ 0 đến 9 là ưu tiên, **không bảo đảm thứ tự xử lý tuyệt đối**.
- `timeToLive` tính bằng mili-giây, 0 thường nghĩa không đặt hạn qua TTL; message vẫn chịu broker policy/resource limits.
- Chọn queue/topic và delivery mode là **quyết định nghiệp vụ/độ tin cậy**, không phải một ưu thế riêng của `send`.

**Khi cần QoS riêng từng nhóm message**, cân nhắc hai template/factory cấu hình rõ ràng hoặc sử dụng mức JMS provider thấp hơn theo chính sách thống nhất; không thay đổi trạng thái template singleton đang được nhiều thread dùng chung chỉ để ưu tiên một message.

## 11. Destination tường minh so với destination mặc định

### 11.1. Tên destination

~~~java
jmsTemplate.send("order.commands", session ->
        session.createTextMessage("CreateInvoice"));

jmsTemplate.convertAndSend("order.events", "OrderCreated");
~~~

Hai lệnh này gửi **hai destination khác nhau** chỉ vì tên tham số. Chuỗi tên được `DestinationResolver` của template giải quyết; mặc định thường là queue nếu `pubSubDomain=false`. Tên queue/topic phải tương ứng routing/authorization của broker.

### 11.2. Default destination

~~~java
jmsTemplate.setDefaultDestinationName("orders.queue");

// Không cần truyền tên đích trên từng call.
jmsTemplate.send(session ->
        session.createTextMessage("Created"));

jmsTemplate.convertAndSend("Created");
~~~

Khi chưa cấu hình default destination, các overload **không truyền destination** có thể ném exception vì không biết gửi đi đâu. Đừng nhầm `convertAndSend(String destinationName, Object payload)` với `convertAndSend(Object payload)`: số lượng/thứ tự tham số quyết định `String` được hiểu là destination hay payload.

### 11.3. Nhiều queue và topic

Nếu một ứng dụng gửi cả queue lẫn topic, không tự động suy ra từ tên `...topic` rằng `JmsTemplate` đổi `pubSubDomain`. Tạo template/resolver riêng hoặc truyền `Destination` rõ ràng, thống nhất policy với broker. Điều này đúng cho **cả send và convertAndSend**.

## 12. Transaction, lỗi và retry: hai API không làm đổi hợp đồng JMS

### 12.1. Gửi thành công không phải là xử lý thành công

~~~text
send / convertAndSend
    → tạo JMS Message
    → provider nhận/send
    → broker lưu/định tuyến message
    → consumer nhận
    → handler ghi DB hoặc gọi hệ thống khác
    → consumer ACK/JMS commit
~~~

Khi lệnh `JmsTemplate` trả về, ứng dụng biết **thao tác send theo hợp đồng của provider** đã hoàn tất (hoặc được enlist vào transaction đang hoạt động), **không biết** side effect nghiệp vụ downstream đã commit. Đặc biệt, trong transaction, lời gọi send có thể hoàn tất **trước commit thực sự**.

### 12.2. Gửi trong local JMS transaction

Nếu cần hai lệnh send (bất kể nhóm nào) cùng commit/rollback tại broker, cần một transaction scope có chủ đích, ví dụ `JmsTransactionManager` và `@Transactional` phù hợp. Snippet minh họa Spring:

~~~java
@Bean
org.springframework.jms.connection.JmsTransactionManager
jmsTransactionManager(jakarta.jms.ConnectionFactory connectionFactory) {
    return new org.springframework.jms.connection.JmsTransactionManager(
            connectionFactory);
}
~~~

Sau đó, trong Spring-managed service:

~~~java
@org.springframework.transaction.annotation.Transactional(
        transactionManager = "jmsTransactionManager")
public void publishTwo(JmsTemplate template) {
    template.send("orders.events", session ->
            session.createTextMessage("OrderCreated"));
    template.convertAndSend("orders.audit", "Created");
}
~~~

Đây là **đoạn minh họa lồng trong class có Spring bean lifecycle**, không phải chương trình `main` độc lập. Cần bảo đảm cùng ConnectionFactory/transaction manager được sử dụng và method được gọi qua proxy Spring đúng cách; self-invocation bypass proxy sẽ không kích hoạt `@Transactional` như mong muốn.

**Giới hạn:** JMS local transaction chỉ gộp tài nguyên JMS thuộc transaction đó; **không tự gộp** DB, HTTP, email hoặc hai JMS provider khác nhau. Với use case “ghi DB và phát event” cần cân nhắc transactional outbox, retry với stable event ID và consumer idempotent; đừng cho rằng dùng `convertAndSend` sẽ tự mang DB transaction theo.

### 12.3. Phân loại lỗi chính xác

| Tình huống | `send` | `convertAndSend` | Cách xử lý |
| --- | --- | --- | --- |
| Không tạo được JMS Message | Lỗi trong `MessageCreator` | Lỗi trong converter | Sửa contract/type và kiểm thử |
| Custom metadata sai | Lỗi callback tạo message | Lỗi `MessagePostProcessor` | Validate property/schema trước send |
| Không resolve được destination | Có thể lỗi trước send | Tương tự | Sửa tên/resolver/routing |
| Provider/broker unreachable | `JmsException` | Tương tự | Retry/backoff với giới hạn, quan sát network |
| Message đã nhận nhưng ack từ broker không về | Kết quả có thể không chắc chắn | Tương tự | Không tạo business ID mới khi retry cùng sự kiện |
| Consumer lỗi sau send | Không báo ngay cho publisher bằng send return | Tương tự | DLQ, redelivery, idempotent consumer và tracing |

`MessageConversionException` ở `convertAndSend` thường là lỗi **không tương thích dữ liệu/định dạng**; retry giống hệt payload không sửa converter hiếm khi giải quyết. Với network timeout trong send, có thể xảy ra trường hợp broker **đã nhận** nhưng producer không biết chắc; retry có thể tạo duplicate messages.

### 12.4. Đúng một lần ở tầng nghiệp vụ

Giả sử producer phải retry vì không nhận phản hồi:

~~~text
eventId=evt-1001
     send attempt A → broker lưu message A → kết nối mất phản hồi
     send attempt B → broker lưu message B → producer biết thành công

consumer nhận A và B
    → không được tạo hai hóa đơn cho cùng eventId
~~~

`JMSMessageID` có thể khác giữa hai lần gửi; hãy dùng `eventId` do ứng dụng gán ổn định xuyên retry, unique constraint/idempotency trong DB, và transaction phù hợp. `send` và `convertAndSend` **không có khác biệt thần kỳ nào** ở bước này.

## 13. Hiểu rõ khi debug log JMS

Trong một request thực tế, hãy log những thông tin an toàn:

| Khi nào | Dữ liệu hữu ích |
| --- | --- |
| Trước send | `eventId`, destination, loại event, schema version, payload size (không log secret) |
| Lúc converter chạy | Java payload type, converter class, JMS message type tạo ra |
| Sau send | Thành công/lỗi, latency, transaction context; không mặc định đã có consumer ACK |
| Ở consumer | `JMSMessageID`, `eventId`, `JMSCorrelationID`, delivery count, redelivered flag, xử lý thành công/thất bại |
| Khi retry/DLQ | Error category, attempts, first failure, destination và replay policy |

**Lưu ý:** `MessagePostProcessor` chạy trước send; ghi `message.getJMSMessageID()` ở đó có thể cho `null`/ID cũ, không phải ID do provider gán cho lần send đang diễn ra. Nếu cần ID sau send, cân nhắc đường JMS API hoặc callback có thể quan sát sau provider-send, nhưng đồng thời phải hiểu transaction/lifecycle và không phá cách Spring quản lý tài nguyên.

## 14. Phân biệt JmsTemplate với các API “Message” khác

Một số tên rất giống nhau:

| API / class | Bản chất |
| --- | --- |
| `org.springframework.jms.core.JmsTemplate` | Thao tác trực tiếp với `jakarta.jms.Message` và JMS converter |
| `org.springframework.jms.core.MessageCreator` | Tạo JMS Message từ JMS `Session` |
| `org.springframework.jms.core.MessagePostProcessor` | Sửa JMS Message sau conversion, trước send |
| `org.springframework.jms.support.converter.MessageConverter` | Chuyển Java object ↔ JMS Message |
| `jakarta.jms.MessageProducer` | Producer cấp JMS API; khác với `JmsTemplate` |
| `jakarta.jms.JMSProducer` | JMS simplified API dùng với `JMSContext` |
| `org.springframework.messaging.Message<?>` | Message abstraction chung của Spring Messaging; **không phải JMS Message** |
| `org.springframework.jms.core.JmsMessagingTemplate` | Cầu nối cấp Spring Messaging; `send/convertAndSend` của nó có chữ ký khác |
| `org.springframework.jms.core.JmsClient` | API fluent xuất hiện trong những Spring Framework phiên bản mới hơn, không thay thế chữ ký `JmsTemplate` trong bài này |

Nếu IDE gợi ý `convertAndSend(String, Object, Map<String,Object>)`, hãy kiểm tra bạn đang dùng **`JmsMessagingTemplate` / `org.springframework.messaging`** hay `JmsTemplate`. Với `JmsTemplate`, overload hậu xử lý nhận **`MessagePostProcessor`**, không phải `Map` headers theo API Spring Messaging.

**Không làm điều này:**

~~~java
// SAI về ý nghĩa: một JMS Message object không phải MessageCreator.
// jmsTemplate.send("orders.queue", existingJmsMessage);

// SAI về kỳ vọng: convertAndSend không được đảm bảo dùng nguyên
// một Message JMS đã tạo sẵn mà bỏ qua MessageConverter.
// jmsTemplate.convertAndSend("orders.queue", existingJmsMessage);
~~~

Khi đã có JMS Message cần gửi, cách tự nhiên với `JmsTemplate` là **tạo nó từ `Session` do callback cấp**, hoặc cân nhắc API thấp hơn trong phạm vi transaction đã kiểm soát. Nếu dữ liệu ban đầu là Java object, dùng `convertAndSend` với converter phù hợp.

## 15. Khi nào nên chọn send, khi nào chọn convertAndSend?

| Bạn cần | Lựa chọn thường hợp lý | Lý do |
| --- | --- | --- |
| Gửi String đơn giản | `convertAndSend` | Ít mã, default converter tạo TextMessage |
| Gửi Map với kiểu JMS cơ bản | `convertAndSend` | Converter tạo MapMessage |
| Gửi POJO JSON đã có converter chuẩn hóa | `convertAndSend` | Một chỗ sở hữu schema/serialization |
| Gửi TextMessage với property/header đặc biệt | Cả hai | `send` dựng thủ công; `convertAndSend` kết hợp post-processor |
| Gửi BytesMessage có cấu trúc bytes đặc biệt | `send` | Kiểm soát chính xác body và message type |
| Cần khai báo JMSReplyTo/correlation, selectors | Cả hai | Đặt trước send trong creator hoặc post-processor |
| Muốn tránh phụ thuộc converter đang thay đổi | `send` | Body/type được quyết định tại callback |
| Muốn đồng nhất JSON giữa nhiều publisher | `convertAndSend` + custom converter | Giảm duplication và dễ version hóa |
| Cần retry/outbox/exactly-once business effect | **Thiết kế thêm ở tầng nghiệp vụ** | Cả hai chỉ là thao tác send |

**Quy tắc thực dụng:** chọn dựa trên **ai sở hữu hợp đồng message**. Nếu hợp đồng được định nghĩa như một **Java payload + converter** đã chuẩn hóa, `convertAndSend` tự nhiên hơn. Nếu hợp đồng yêu cầu kiểm soát chính xác từng byte/field JMS, `send` rõ ràng hơn. Cả hai phải dùng một chính sách nhất quán về destination, QoS, transaction, idempotency và observability.

## 16. Những lỗi phổ biến

1. **“convertAndSend tự chuyển mọi object sang JSON.”** Không; hãy xem `MessageConverter` thực tế.
2. **“send và convertAndSend là hai delivery mode.”** Không; cả hai tạo/gửi cùng kiểu JMS message, khác bước dựng.
3. **“MessageCreator nhận Object Java.”** Nó nhận JMS `Session` và trả JMS `Message`.
4. **“MessagePostProcessor chạy sau broker send.”** Nó chạy **trước** provider send, sau conversion.
5. **“Map là JSON.”** `SimpleMessageConverter` thường tạo `MapMessage`, với giới hạn kiểu JMS.
6. **“POJO không Serializable vẫn tự gửi được.”** Converter mặc định có thể ném conversion error.
7. **“MessageCreator tự tạo Connection/Session riêng sẽ tốt hơn.”** Trái với scope tài nguyên do template quản lý.
8. **“convertAndSend chắc chắn nhanh/chậm hơn send.”** Phải đo serialization/caching/broker overhead; không dựa vào tên API.
9. **“Cài JSON converter chỉ đổi outbound.”** Nó có thể thay cả inbound conversion nếu listener/template chia sẻ cấu hình, cần test tương thích.
10. **“Cấu hình QoS trên JmsTemplate luôn hiệu lực.”** Với explicit QoS setters, phải kiểm tra `setExplicitQosEnabled` và admin overrides.
11. **“Có JMSMessageID trong MessagePostProcessor.”** Chưa: provider gán nó lúc send.
12. **“convertAndSend gửi là listener đã xử lý.”** Send không thay consumer ACK hay DB commit.
13. **“Có transaction DB thì JMS tự rollback theo.”** JMS transaction và DB transaction khác nhau nếu chưa thiết kế phối hợp.
14. **“Thêm @JmsListener String thì mọi bytes/map/JSON đều được giải mã.”** Phụ thuộc converter, method signature và container factory.
15. **“Tên destination có .topic thì Spring hiểu topic.”** Tên string không tự thay `pubSubDomain`.
16. **“Tự sửa JmsTemplate singleton QoS theo mỗi request.”** Có thể ảnh hưởng concurrent publishers; cấu hình template theo policy ổn định.

## 17. Thực hành kiểm chứng theo thứ tự

**Bài 1 — Hai cách, một body:** gửi chuỗi `"hello"` tới queue bằng `send` và `convertAndSend`; consumer kiểm tra cả hai đều là `TextMessage` với default converter.

**Bài 2 — Post processor:** bổ sung `eventId`, `JMSCorrelationID` bằng hai cách, đọc tại consumer. Cố đọc `JMSMessageID` trong creator/post-processor để thấy vì sao nó chưa được đảm bảo.

**Bài 3 — Conversion table:** truyền `String`, `byte[]` và `Map` qua `convertAndSend`; consumer nhận raw `Message`, ghi kiểu thực tế. Thử map chứa nested object và ghi loại exception.

**Bài 4 — Thay converter:** đăng ký `MappingJackson2MessageConverter`, gửi `OrderCreated` record và quan sát `TextMessage` JSON. So sánh type metadata/schema trước và sau; kiểm tra listener conversion.

**Bài 5 — Sai default destination:** thử `send(MessageCreator)` và `convertAndSend(Object)` khi chưa cấu hình default destination; lý giải failure rồi sửa bằng tên destination tường minh.

**Bài 6 — QoS:** bật `setExplicitQosEnabled(true)`, cấu hình persistent/priority/TTL rồi thử cả hai cách gửi. Quan sát broker header sau send để chứng minh chính sách dùng chung.

**Bài 7 — Transaction:** dưới `JmsTransactionManager` gửi hai message bằng hai API trong một transaction, cố ném exception trước commit; kiểm tra broker không có hai message chưa commit. So sánh với hai send không có transaction scope.

**Bài 8 — Fault injection:** làm broker không sẵn sàng khi gửi; phân biệt lỗi conversion (trước mạng) với lỗi provider (sau khi attempt gửi), và xem retry có thể tạo duplicate như thế nào.

**Bài 9 — Consumer idempotency:** gửi lại hai lần cùng `eventId` theo hai API khác nhau; chứng minh unique constraint ở DB bảo vệ khỏi xử lý nghiệp vụ hai lần.

**Bài 10 — Tách queue/topic:** cùng payload nhưng chọn hai destination khác nhau; kiểm tra resolver/pubSubDomain và số consumer/subscription trước khi kết luận có nhận đúng.

## 18. Tự kiểm tra hiểu bài

Trả lời được các câu hỏi sau trước khi chuyển sang lesson JMS nâng cao:

- Có thể nói chính xác `send` nhận `MessageCreator` để tạo `jakarta.jms.Message`, còn `convertAndSend` nhận Java object và dùng `MessageConverter`?
- Vì sao `String` đi qua default converter thành `TextMessage`, `Map` thành `MapMessage`, còn POJO không mặc định thành JSON?
- Khi cần đặt `eventId` property và `JMSCorrelationID`, đặt ở đâu trong mỗi cách?
- Vì sao cả creator và post-processor đều không đảm bảo đọc được JMSMessageID mới nhất?
- Khi nào overload bỏ destination sẽ thất bại?
- Làm sao chứng minh listener và publisher đang dùng converter tương thích?
- Có thể giải thích cùng một chính sách TTL/delivery mode/transaction áp dụng cho cả hai nhóm method?
- Khi broker mất phản hồi, vì sao cả hai cách đều có nguy cơ gửi trùng và cần event ID nghiệp vụ?
- Có thể chạy ví dụ Boot 3.x với broker test và quan sát đủ ba loại message được tạo không?
- Có biết thời điểm cần chọn callback thủ công thay vì định nghĩa converter chung?

**Kết quả mong muốn:** đọc được một lệnh `JmsTemplate` và trả lời ba câu hỏi rõ ràng: “**Ai tạo JMS Message? Kiểu/body thực tế là gì? Metadata được đặt ở thời điểm nào?**”. Khi đã rõ ba câu này, việc chọn `send` hay `convertAndSend` trở thành quyết định kỹ thuật có thể giải thích và kiểm chứng, không phải lựa chọn theo tên hàm.

## 19. Tài liệu gốc

1. [Spring Framework Reference — Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html): `JmsTemplate.send`, `convertAndSend`, `MessageCreator`, `MessagePostProcessor` và các ví dụ của Spring.
2. [Spring Framework 6.1 — JmsTemplate API](https://docs.spring.io/spring-framework/docs/6.1.1/javadoc-api/org/springframework/jms/core/JmsTemplate.html): overload chính xác và exceptions.
3. [Spring Framework 6.1 — SimpleMessageConverter](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/jms/support/converter/SimpleMessageConverter.html): ánh xạ String/byte[]/Map/Serializable sang JMS.
4. [Spring Framework 6.1 — JMS converter package](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/jms/support/converter/package-summary.html): `MessageConverter`, `MappingJackson2MessageConverter`, `MessageConversionException`.
5. [Spring Framework Reference — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): `JmsTemplate`, connection/session management, destinations, transactions.
6. [Spring Boot Reference — JMS](https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html): Artemis starter, auto-configuration, template/converter và listener.
7. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): định nghĩa JMS Message, producer, delivery mode, transaction và metadata.