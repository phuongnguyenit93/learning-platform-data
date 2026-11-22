# TextMessage và nội dung văn bản trong Spring JMS

## 1. TextMessage là gì?

Trong **Jakarta Messaging (JMS)**, `TextMessage` là một kiểu `jakarta.jms.Message` có **body là một chuỗi `java.lang.String`**. Khi producer cần chuyển một câu thông báo, đoạn văn bản, XML hoặc JSON dạng text qua broker JMS, `TextMessage` là kiểu message trực tiếp, dễ dùng.

Ví dụ body:

```text
Đơn hàng #42 đã được xác nhận.
```

Hoặc nội dung JSON vẫn là *chuỗi văn bản*:

```json
{
  "eventId": "evt-42",
  "eventType": "ORDER_CONFIRMED",
  "orderId": 42,
  "customerName": "Nguyễn An"
}
```

JSON ở đây **chưa tự biến thành Java object**. Với JMS, body vẫn là một `String`; ứng dụng nhận phải tự parse hoặc cấu hình `MessageConverter` phù hợp.

Hình dung một message:

```text
JMS Message
├── Header: JMSMessageID, JMSTimestamp, JMSCorrelationID, ...
├── Properties: contentType="application/json", schemaVersion=1, ...
└── Body (TextMessage): "{\"eventId\":\"evt-42\", ...}"
```

**Phân biệt ba tầng:** `TextMessage` nói về **kiểu dữ liệu của body**; `Queue` hay `Topic` nói về **destination/định tuyến**; `Content-Type` tự đặt trong property nói về **quy ước diễn giải văn bản** giữa các ứng dụng. Một `TextMessage` có thể được gửi tới Queue hoặc Topic. Nó không tự quyết định một hay nhiều consumer nhận message.

## 2. API cốt lõi và vòng đời body

Đây là interface `jakarta.jms.TextMessage`, không phải `javax.jms.TextMessage` trong các thư viện JMS đời cũ. Spring Boot 3 / Spring Framework 6 sử dụng namespace `jakarta.jms`.

| API | Vai trò | Điều cần nhớ |
| --- | --- | --- |
| `session.createTextMessage()` | Tạo `TextMessage` với body ban đầu `null`. | `getText()` lúc này trả `null`. |
| `session.createTextMessage(String)` | Tạo message và đặt body ngay. | Chuỗi có thể là plain text, XML, JSON. |
| `message.setText(String)` | Ghi hoặc thay nội dung body khi message cho phép ghi. | Nhận được message thường có body read-only. |
| `message.getText()` | Đọc nguyên chuỗi body (có thể `null`). | Không có bước parse JSON/XML ngầm. |
| `message.getBody(String.class)` | Đọc body qua API chung `Message`. | Với `TextMessage` hợp lệ, nhận được `String` hoặc `null`. |
| `message.isBodyAssignableTo(String.class)` | Hỏi liệu body có thể đọc thành `String`. | Hữu ích khi nhận một `Message` chưa biết kiểu. |
| `message.clearBody()` | Xóa body và đưa nó về trạng thái có thể ghi. | Không phải cách cập nhật message đã lưu trong broker. |

Cả `TextMessage#getText()` và `setText()` đều có thể ném `JMSException`. Nếu body đang ở chế độ chỉ đọc, `setText()` có thể ném `MessageNotWriteableException`.

### `null`, chuỗi rỗng và khoảng trắng là ba trường hợp khác nhau

| Body được tạo | Giá trị `getText()` | Ý nghĩa gợi ý |
| --- | --- | --- |
| `createTextMessage()` | `null` | Chưa thiết lập body |
| `createTextMessage("")` | `""` (độ dài 0) | Có chuỗi nhưng rỗng |
| `createTextMessage("   ")` | `"   "` (độ dài 3) | Có ba dấu cách |
| `createTextMessage("Xin chào")` | `"Xin chào"` | Chuỗi bình thường |

Nếu nghiệp vụ không chấp nhận dữ liệu rỗng, hãy kiểm tra cả `null` và `isBlank()`; **không** tự động `trim()` mọi message vì khoảng trắng hoặc xuống dòng có thể là dữ liệu có nghĩa. JMS không áp đặt một chính sách kiểm tra nội dung hợp lệ cho ứng dụng.

### Cách tạo và đọc bằng JMS thuần

Đoạn mã sau minh họa API **bên trong một phương thức đã có `jakarta.jms.Session session` hợp lệ**; nó không phải chương trình Java độc lập:

```java
TextMessage outgoing = session.createTextMessage("Xin chào, JMS!");
outgoing.setStringProperty("contentType", "text/plain");
outgoing.setIntProperty("schemaVersion", 1);

String text = outgoing.getText();              // "Xin chào, JMS!"
String type = outgoing.getStringProperty("contentType"); // "text/plain"
int version = outgoing.getIntProperty("schemaVersion");  // 1
```

Người gửi phải lấy `Session` từ kết nối/provider JMS hoặc để `JmsTemplate` cấp cho callback. **Không** khởi tạo một triển khai `TextMessage` tùy ý bằng `new TextMessage()`: đây là interface, provider tạo đối tượng thực tế.

Khi đã nhận một đối tượng `Message` chung, có thể kiểm tra kiểu rồi đọc:

```java
if (message instanceof TextMessage textMessage) {
    String body = textMessage.getText();
    // Kiểm tra và xử lý body.
} else {
    // Xử lý riêng kiểu body khác, hoặc từ chối theo hợp đồng.
}
```

Với API JMS 2.0+/Jakarta Messaging 3.x, `message.getBody(String.class)` là lựa chọn gọn hơn **khi hợp đồng đã bảo đảm kiểu body tương thích**. Nếu body thực tế không thể gán thành `String`, việc gọi sai kiểu có thể gây `MessageFormatException`. Nên kiểm tra `isBodyAssignableTo(String.class)` khi xử lý message tổng quát.

## 3. Body văn bản, header và property phục vụ những việc khác nhau

Giả sử bạn gửi thông báo đã tạo đơn:

```text
Header:
  JMSMessageID: do broker/provider gán
  JMSTimestamp: do provider quản lý
  JMSCorrelationID: request-734 (nếu ứng dụng đặt)

Properties:
  eventType: ORDER_CREATED
  contentType: application/json
  schemaVersion: 1

Body:
  {"eventId":"evt-734","orderId":734,"total":199000}
```

- **Body** chứa dữ liệu chính; có thể dài và có cấu trúc.
- **Header JMS chuẩn** chứa metadata về định danh, routing, ưu tiên, correlation, redelivery... Các trường không phải lúc nào cũng có giá trị do ứng dụng đặt.
- **Property** là metadata tùy biến có kiểu cơ bản như `String`, `int`, `boolean`; thích hợp cho phân loại, định tuyến hoặc selector. Property không phải nơi nhét cả đối tượng Java/JSON lớn.
- `contentType` trong ví dụ là **property do ứng dụng quy ước**, không phải header `Content-Type` bắt buộc của JMS. JMS không tự nhận diện `application/json` rồi parse nội dung.
- `JMSType` là một header JMS khác; **không mặc nhiên đồng nghĩa MIME Content-Type**.
- `JMSMessageID` là định danh message do provider gán. Nếu cần định danh sự kiện ổn định qua producer retry/deduplication, dùng thêm `eventId` nghiệp vụ riêng.

Property có thể dùng với **JMS selector**; selector xem header/property hợp lệ, **không tìm kiếm trong text body**. Ví dụ consumer chỉ quan tâm `eventType = 'ORDER_CREATED'` nên đặt `eventType` thành property. Nếu chỉ có `"eventType"` bên trong JSON body, selector JMS không tự lọc được theo trường JSON đó.

## 4. TextMessage hỗ trợ Unicode, nhưng vẫn cần hợp đồng định dạng

Trong Java, `String` biểu diễn nội dung Unicode (đơn vị lưu trữ UTF-16); code JMS làm việc với `String`, không phải một `byte[]` do bạn tự mã hóa. Các chuỗi như `"Tiếng Việt có dấu"`, `"こんにちは"` hoặc `"🌿"` có thể là body `TextMessage` hợp lệ. Provider/protocol JMS đảm nhiệm chuyển dữ liệu giữa client và broker.

Đừng nhầm ba khái niệm:

1. **Ký tự trong `String`**: dữ liệu text mà ứng dụng nhìn thấy.
2. **Số đơn vị UTF-16 `String.length()`**: không phải số ký tự người đọc nhìn thấy; emoji thường chiếm hai code unit.
3. **Số byte trên đường truyền/broker**: phụ thuộc vào provider/protocol/encoding và metadata; không suy từ `String.length()`.

Nếu chương trình tự chuyển text thành bytes (`text.getBytes(charset)`) rồi ghi vào `BytesMessage`, lúc đó **phải thống nhất charset** với consumer, thường là UTF-8. Với `TextMessage`, không nên tự `getBytes()` rồi khai báo nhầm rằng body vẫn là `String`.

Các định dạng hợp lý cho `TextMessage`:

| Nội dung | Ví dụ | Cách xử lý đúng |
| --- | --- | --- |
| Plain text | `Đơn hàng đã giao` | Hiển thị, xác thực, lưu văn bản |
| JSON | `{"status":"DONE"}` | Parse JSON thành schema/DTO đã kiểm tra |
| XML | `<status>DONE</status>` | Parse bằng XML parser cấu hình an toàn |
| CSV nhỏ | `id,status\n1,DONE` | Dùng CSV parser, quy định delimiter và quoting |
| Chuỗi mã hóa Base64 | `SGVsbG8=` | Chỉ dùng khi giao thức yêu cầu; binary trực tiếp thường hợp với `BytesMessage` |

**Không có luật JMS rằng mọi JSON phải là `TextMessage`**; nhưng đó là lựa chọn thông dụng khi cần giao tiếp dễ đọc, liên ngôn ngữ và có schema rõ ràng. Chỉ dùng văn bản không tự tạo ra bảo mật, tính toàn vẹn hay versioning.

## 5. Cách Spring JMS làm việc với TextMessage

Spring cung cấp `JmsTemplate` và listener `@JmsListener` để ứng dụng ít phải quản lý `Connection`, `Session`, `MessageProducer`, `MessageConsumer` thủ công.

Có hai lối gửi phổ biến:

**Tạo `TextMessage` bằng tay:** bạn cần kiểm soát kiểu body và property/header cụ thể.

```java
jmsTemplate.send("orders.text", session -> {
    TextMessage msg = session.createTextMessage("Đơn hàng #42 đã xác nhận");
    msg.setStringProperty("contentType", "text/plain");
    msg.setStringProperty("eventType", "ORDER_CONFIRMED");
    return msg;
});
```

**Chuyển `String` tự động:** khi đang dùng `SimpleMessageConverter` mặc định, Spring biến `String` thành `TextMessage`:

```java
jmsTemplate.convertAndSend("orders.text", "Đơn hàng #42 đã xác nhận");
```

`send(..., MessageCreator)` để callback tự tạo `TextMessage`. `convertAndSend(..., Object)` nhờ **`MessageConverter`** được cấu hình, vì thế kết quả thực tế có thể khác nếu ứng dụng thay converter. Khi chỉ cần body `String`, `convertAndSend` giúp code ngắn hơn; khi cần property, dùng `MessagePostProcessor`:

```java
jmsTemplate.convertAndSend(
    "orders.text",
    "Đơn hàng #42 đã xác nhận",
    message -> {
        message.setStringProperty("eventType", "ORDER_CONFIRMED");
        return message;
    }
);
```

Với Spring Boot cấu hình mặc định, listener có thể nhận:

```java
@JmsListener(destination = "orders.text")
public void onText(String text) {
    System.out.println(text);
}
```

Hoặc nhận **đối tượng JMS nguyên bản** để truy cập metadata/body trực tiếp:

```java
@JmsListener(destination = "orders.text")
public void onRaw(TextMessage message) throws JMSException {
    System.out.println(message.getText());
    System.out.println(message.getJMSMessageID());
}
```

**Chọn một cách nhận theo nhu cầu.** Nếu khai báo **hai** listener như trên cùng một Queue và chạy đồng thời thì chúng là hai consumer **cạnh tranh**, không phải một message được callback tới cả hai. Ví dụ chạy đầy đủ bên dưới dùng **hai Queue khác nhau** để tránh nhầm cơ chế delivery.

## 6. Ví dụ đầy đủ: Spring Boot + Artemis, gửi và nhận hai dạng văn bản

Mục tiêu: thấy được (1) producer chủ động tạo `TextMessage`, consumer nhận `TextMessage` thô; và (2) `String` tự được chuyển thành `TextMessage` qua `SimpleMessageConverter`, consumer nhận body `String`. Dùng **Java 17+, Spring Boot 3.3.13, Gradle và Apache ActiveMQ Artemis**.

### 6.1. Chạy broker thử nghiệm

Với Docker đang chạy, dùng một dòng lệnh sau (port 61616 dành cho kết nối JMS):

```bash
docker run --detach --rm --name artemis-text-demo -p 61616:61616 -e ARTEMIS_USER=demo -e ARTEMIS_PASSWORD=demo apache/artemis:latest-alpine
```

Đợi Artemis sẵn sàng rồi mới chạy ứng dụng. Đây là credential demo dùng trên máy local, không dùng nguyên mẫu cho môi trường thực tế. Image chính thức mặc định có thể tự tạo address/queue khi broker cho phép; nếu broker của bạn tắt `auto-create`, quản trị viên cần tạo hai Queue `demo.text.raw` và `demo.text.converted` trước. Để dừng broker: `docker stop artemis-text-demo`.

### 6.2. Cấu hình Gradle

Tạo `settings.gradle`:

```groovy
rootProject.name = 'jms-text-demo'
```

Tạo `build.gradle`:

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

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

Tạo `src/main/resources/application.yml`:

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

`pub-sub-domain: false` chỉ rõ demo sử dụng **Queue**, không dùng Topic. Spring Boot tạo `ConnectionFactory`, `JmsTemplate` và hạ tầng listener khi có starter tương ứng.

### 6.3. Ứng dụng Java đầy đủ

Tạo đúng file `src/main/java/demo/jms/TextMessageDemoApplication.java`:

```java
package demo.jms;

import jakarta.jms.JMSException;
import jakarta.jms.TextMessage;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class TextMessageDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(TextMessageDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner sendExamples(JmsTemplate jmsTemplate) {
        return args -> {
            // Ví dụ A: tạo rõ ràng một TextMessage.
            jmsTemplate.send("demo.text.raw", session -> {
                TextMessage message =
                        session.createTextMessage("Xin chào JMS 🌿");
                message.setStringProperty("contentType", "text/plain");
                message.setIntProperty("schemaVersion", 1);
                return message;
            });

            // Ví dụ B: SimpleMessageConverter đổi String -> TextMessage.
            jmsTemplate.convertAndSend(
                    "demo.text.converted",
                    "Dòng một\nDòng hai"
            );
        };
    }
}

@Component
class TextMessageListeners {

    @JmsListener(destination = "demo.text.raw")
    public void onRaw(TextMessage message) throws JMSException {
        System.out.printf(
                "RAW text=%s | type=%s%n",
                message.getText(),
                message.getStringProperty("contentType")
        );
    }

    @JmsListener(destination = "demo.text.converted")
    public void onConverted(String text) {
        System.out.printf(
                "CONVERTED body=%s%n",
                text.replace("\n", "\\n")
        );
    }
}
```

**Diễn giải:** `@EnableJms` kích hoạt cơ chế listener annotation (Spring Boot cũng tự cấu hình hỗ trợ tương ứng khi có JMS). Khi application context sẵn sàng, `ApplicationRunner` gửi hai message tới hai Queue. Broker cấp message cho listener tương ứng.

`TextMessageListeners.onRaw` nhận trực tiếp **`jakarta.jms.TextMessage`**, dùng `getText()` và `getStringProperty()`. `onConverted` nhận **`String`**, nhờ Spring chuyển payload từ `TextMessage`. Đây là hai kiểu chữ ký cho hai trường hợp sử dụng, cùng đọc body văn bản.

### 6.4. Chạy và kiểm tra

Dùng Gradle 8.5+ đã cài, tại thư mục dự án:

```bash
gradle bootRun
```

Nếu đã tạo Gradle Wrapper, trên Linux/macOS dùng `./gradlew bootRun`, trên Windows dùng `gradlew.bat bootRun`. Bảo đảm broker ở `localhost:61616` hoạt động và user/password khớp.

Ngoài log khởi động Spring/Artemis, khi mỗi message được xử lý một lần, ứng dụng sẽ in **hai dòng nội dung sau (thứ tự giữa hai dòng không được bảo đảm)**:

```text
RAW text=Xin chào JMS 🌿 | type=text/plain
CONVERTED body=Dòng một\nDòng hai
```

Trong output, `\\n` là hai ký tự dấu gạch chéo ngược và `n` được in ra để biểu diễn newline, do code `replace("\n", "\\n")`; body được gửi thực tế chứa **một ký tự xuống dòng** giữa “Dòng một” và “Dòng hai”. Dấu tiếng Việt và biểu tượng vẫn giữ nội dung vì `TextMessage` thao tác trên `String`; file mã nguồn đặt UTF-8 để compiler đọc đúng ký tự literal.

Nếu không thấy output, kiểm tra logs kết nối broker và listener startup, tên Queue, quyền truy cập và liệu message đã được consumer khác lấy chưa. Với Queue có thể tồn tại message chưa xử lý từ lần chạy cũ; không dùng số dòng log để suy ra bảo đảm đúng-một-lần tuyệt đối trong điều kiện lỗi/retry.

## 7. JSON trong TextMessage: định dạng text hay object đã chuyển đổi?

Cùng một message JSON có thể được xử lý theo hai mức:

**Mức A – raw text:** producer đưa JSON vào `String` (thường serialize bằng Jackson), gửi `TextMessage`; consumer nhận `String`, xác thực và parse. Khi hệ thống có ngôn ngữ khác Java, cách này giúp hợp đồng dễ trao đổi, nhưng cần thống nhất schema, version, trường bắt buộc, giới hạn kích thước và xử lý lỗi parse.

```java
// Minh họa trong một producer đã có JmsTemplate và ObjectMapper.
String json = objectMapper.writeValueAsString(
        new OrderCreated("evt-42", 42L)
);
jmsTemplate.send("order.events", session -> {
    TextMessage m = session.createTextMessage(json);
    m.setStringProperty("contentType", "application/json");
    m.setIntProperty("schemaVersion", 1);
    return m;
});
```

Trong snippet này, `OrderCreated` là một DTO/record của ứng dụng và `objectMapper` là Jackson `ObjectMapper` được cấu hình; snippet **không độc lập biên dịch** nếu chưa khai báo hai thành phần ấy. Đừng nối chuỗi kiểu `"{\"name\":\"" + input + "\"}"` để tạo JSON: dấu ngoặc kép, backslash, newline trong input sẽ phá dữ liệu hoặc làm phát sinh lỗi injection ở tầng xử lý phía sau. Dùng serializer chuẩn.

**Mức B – converter tự động:** Spring có `MappingJackson2MessageConverter`. Khi muốn **JMS body là JSON text**, cấu hình target `MessageType.TEXT`, vì converter này có thể mặc định sinh `BytesMessage` nếu không đặt target. Ví dụ cấu hình **riêng, thay thế cấu hình converter mặc định trong demo trên**:

```java
@Bean
public org.springframework.jms.support.converter.MessageConverter jsonConverter() {
    var converter =
            new org.springframework.jms.support.converter.MappingJackson2MessageConverter();
    converter.setTargetType(
            org.springframework.jms.support.converter.MessageType.TEXT
    );
    converter.setTypeIdPropertyName("_type");
    return converter;
}
```

Cấu hình này yêu cầu Jackson (`com.fasterxml.jackson.core:jackson-databind`, thường có qua `spring-boot-starter-json`). Việc đọc ngược object cũng cần type-id property hợp lệ và mapping/trust policy phù hợp; ứng dụng hai phía phải thống nhất converter và schema. **Không bật bean này vào demo trước rồi mặc định kỳ vọng `convertAndSend(String)` và tất cả các listener hoạt động hệt converter cũ.** Đối với hợp đồng JSON liên dịch vụ, cân nhắc dùng tên type ổn định và cấu hình type-id mapping rõ ràng, tránh ràng buộc wire format vào tên class nội bộ.

### Khi nào ưu tiên TextMessage JSON, khi nào cân nhắc BytesMessage?

- **TextMessage JSON:** khi bên nhận cần nội dung có thể đọc, log an toàn có chọn lọc, schema dạng text, dễ tích hợp đa ngôn ngữ; thường phù hợp sự kiện nghiệp vụ nhỏ và trung bình.
- **BytesMessage:** khi payload vốn là binary (ảnh, protobuf, compressed payload), hoặc wire format yêu cầu bytes/charset cụ thể được thống nhất.
- **ObjectMessage:** chứa Java `Serializable`, gắn với mô hình Java và có rủi ro deserialization nếu nhận nguồn không tin cậy; không phải lựa chọn mặc định tốt cho tích hợp đa hệ thống.

Đừng dựa vào việc dữ liệu có dạng JSON để tự suy ra converter. Hai bên phải thống nhất chính xác loại JMS message và schema nội dung.

## 8. Trường hợp lỗi và hành vi runtime cần hiểu

### 8.1. Nhận sai loại message

Nếu listener khai báo `String` nhưng producer gửi `BytesMessage` hoặc object phức tạp mà converter không biết chuyển, quá trình chuyển đổi có thể lỗi; Spring không tự biết bytes đó là UTF-8 hay nội dung nghiệp vụ. Khi hợp đồng đòi `TextMessage`, consumer có thể nhận tham số `TextMessage` và fail rõ ràng khi loại khác xuất hiện.

Với JMS thuần, `Message#getBody(String.class)` không phải câu lệnh “ép mọi body thành chuỗi”: chỉ hoạt động với kiểu body tương thích. Đừng bắt lỗi rồi coi dữ liệu mất/không hợp lệ là chuỗi rỗng.

### 8.2. Body rỗng, `null`, JSON lỗi hoặc version không tương thích

`TextMessage` chấp nhận `null`. Consumer nên kiểm tra payload trước khi parse:

```java
String body = message.getText();
if (body == null || body.isBlank()) {
    throw new IllegalArgumentException("Text body is missing or blank");
}
```

Đây là đoạn xử lý **trong một listener đã nhận `TextMessage message`**, không phải một class Java độc lập. Với JSON, xử lý riêng lỗi parse, schema thiếu trường, version không hỗ trợ và nội dung quá kích thước; không coi một JSON hợp cú pháp là mặc nhiên hợp lệ nghiệp vụ.

### 8.3. Transaction, acknowledge và redelivery

`TextMessage` chỉ quy định **kiểu body**. Message được acknowledge/commit/rollback như các JMS message khác. Nếu listener xử lý lỗi và session bị rollback hoặc chưa ACK hợp lệ, broker có thể giao lại cùng message; `JMSRedelivered` có thể báo lần giao lại.

Nếu xử lý có ghi database hoặc gọi HTTP, không được suy ra “exactly once” chỉ từ việc dùng `TextMessage`. Để tránh lặp tác động nghiệp vụ, đưa `eventId` ổn định vào body/property và dùng idempotency (unique key, inbox table...). Config transaction, retry, DLQ theo broker và yêu cầu độ tin cậy. Không ACK trước khi xử lý hoàn tất nếu kiến trúc cần tránh mất thông điệp.

### 8.4. Độ dài body và vận hành

JMS **không định nghĩa một số ký tự tối đa chung** cho `TextMessage`; giới hạn thực tế phụ thuộc broker, memory, quota, protocol, timeout và policy. Đừng gửi file lớn hoặc text vô hạn qua queue mà không có quy ước size limit. Với payload rất lớn, cân nhắc lưu object vào object storage rồi gửi tham chiếu phù hợp (kèm phân quyền và thời hạn truy cập).

Giữ log có giới hạn: tránh in nguyên body chứa PII, token, số tài khoản hoặc dữ liệu nhạy cảm. Đặt `correlationId`/`eventId` để truy vết; ghi nhận message type, contentType, schemaVersion, kích thước dự kiến và trạng thái xử lý có chọn lọc.

### 8.5. Không sửa message đã nhận để “cập nhật trong broker”

Message đến consumer thường có body/properties read-only; `setText()` không được phép cho tới khi thay đổi trạng thái body phù hợp (`clearBody()`). Kể cả khi có thể sửa đối tượng trong JVM, thao tác đó **không chỉnh sửa bản đã gửi trong broker**. Muốn tạo sự kiện/response mới, hãy tạo **một message mới** và gửi tới destination phù hợp.

## 9. Các lỗi tư duy thường gặp

1. **“TextMessage là Queue dành riêng cho văn bản.”** Sai: `TextMessage` là body type; Queue/Topic là destination.
2. **“TextMessage luôn là text/plain.”** Sai: có thể chứa JSON, XML, CSV, log...; nội dung được hiểu theo hợp đồng ứng dụng.
3. **“JSON trong TextMessage được tự đổi thành POJO.”** Sai trừ khi ứng dụng cấu hình converter/parser phù hợp.
4. **“`convertAndSend` luôn sinh TextMessage.”** Sai: kết quả phụ thuộc kiểu payload và `MessageConverter`; `String` với `SimpleMessageConverter` mặc định mới là trường hợp điển hình.
5. **“`getText()` không bao giờ `null`.”** Sai: body của message mới tạo mà chưa gán text mặc định là `null`.
6. **“Body rỗng và body `null` giống nhau.”** Sai: hai giá trị khác nhau, dù cả hai thường bị validator nghiệp vụ từ chối.
7. **“JMS selector có thể lọc trường JSON nằm trong body.”** Sai: selector xét những header/property được hỗ trợ, không tự parse body JSON.
8. **“`String.length()` là số byte broker gửi.”** Sai: `String.length()` là đơn vị UTF-16, khác số byte trên wire.
9. **“Nhận xong là có thể sửa TextMessage để broker cập nhật.”** Sai: body nhận thường read-only; muốn publish nội dung mới phải gửi message mới.
10. **“Có TextMessage thì xử lý chỉ một lần.”** Sai: transaction, ACK, retry và idempotency là các vấn đề giao nhận độc lập với kiểu body.

## 10. Câu hỏi tự luyện

**Câu 1:** Hai đoạn sau khác nhau thế nào?

```java
TextMessage a = session.createTextMessage();
TextMessage b = session.createTextMessage("");
```

**Đáp án:** `a.getText() == null`; `b.getText().equals("")` và độ dài của b là 0. Đoạn code giả định đã có `Session session` hợp lệ.

**Câu 2:** Producer dùng `jmsTemplate.convertAndSend("q", "hello")` với `SimpleMessageConverter` mặc định. Body/message type là gì?

**Đáp án:** `TextMessage` với body `"hello"`. Nếu thay converter, cần kiểm tra lại mapping.

**Câu 3:** TextMessage chứa JSON `{"priority":"HIGH"}`. Consumer đặt JMS selector `priority = 'HIGH'` nhưng producer không đặt property `priority`. Có lọc được nhờ body không?

**Đáp án:** Không. Selector không đọc JSON body; phải thêm property `priority` hợp lệ lúc gửi (hoặc thực hiện lọc trong handler sau khi nhận).

**Câu 4:** `TextMessage` có thể chứa chữ tiếng Việt có dấu, emoji và xuống dòng không? Có cần tự tạo UTF-8 `byte[]`?

**Đáp án:** Có thể chứa những ký tự đó trong `String`. Không cần tự biến thành `byte[]` để dùng `TextMessage`; cần bảo đảm charset của source code/file/biên dịch và sự tương thích provider/client.

**Câu 5:** Một listener xử lý message, ghi DB thành công rồi lỗi trước khi commit/ACK JMS; broker gửi lại. Có phải lỗi của `TextMessage`?

**Đáp án:** Không. Đây là tình huống của transaction/redelivery và side effect; cần xử lý idempotent theo event ID và thiết kế transaction/ack phù hợp.

## 11. Tài liệu gốc

- [Jakarta Messaging 3.1 – `TextMessage` API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/textmessage)
- [Jakarta Messaging 3.1 – `Message` (headers, properties, body)](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message)
- [Spring Framework – Sending a Message và Message Converters](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html)
- [Spring Framework – Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html)
- [Spring Boot – Messaging with JMS](https://spring.io/guides/gs/messaging-jms/)
- [Apache ActiveMQ Artemis – Docker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html)

**Điểm cần nhớ:** `TextMessage` vận chuyển một **`String`** qua JMS. Muốn ứng dụng đọc đúng ý nghĩa chuỗi, hãy thống nhất **format, schema, metadata, conversion và xử lý lỗi**; muốn delivery đáng tin, thiết kế riêng transaction, acknowledge và idempotency.
