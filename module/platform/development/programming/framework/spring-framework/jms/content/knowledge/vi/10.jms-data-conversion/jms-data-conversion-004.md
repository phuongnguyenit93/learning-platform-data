# TextMessage so với BytesMessage cho JSON trong Spring JMS

## 1. Câu hỏi cốt lõi: JSON nên gửi dưới dạng text hay bytes?

**JSON là định dạng dữ liệu**, còn **TextMessage** và **BytesMessage** là hai kiểu *body* của Jakarta Messaging (JMS). Cùng một đối tượng nghiệp vụ, chẳng hạn sự kiện tạo đơn hàng, có thể được biểu diễn thành chuỗi JSON rồi đặt vào `TextMessage` hoặc mã hóa thành dãy byte UTF-8 rồi đặt vào `BytesMessage`. Cả hai cách đều hợp lệ; consumer phải có **hợp đồng dữ liệu** tương ứng để đọc đúng.

Ví dụ dữ liệu nghiệp vụ:

~~~json
{
  "eventId": "evt-42",
  "orderId": "O-42",
  "customer": "Hà",
  "amountVnd": 125000
}
~~~

Hai cách gửi:

~~~text
Cách A — TextMessage
  Message body = String JSON
  Session.createTextMessage(json)
  Consumer: ((TextMessage) message).getText()

Cách B — BytesMessage
  Message body = byte[] mang JSON UTF-8
  Session.createBytesMessage() + writeBytes(json.getBytes(UTF_8))
  Consumer: message.getBody(byte[].class) + decode UTF-8

Cả hai đều có:
  JMS headers: JMSMessageID, JMSDestination, ...
  JMS properties: eventId, schemaVersion, contentType, ...
~~~

Điểm dễ nhầm: **TextMessage không phải "JSON message" có khả năng parse JSON**, và **BytesMessage không mặc nhiên là định dạng nhị phân khác JSON**. JMS chỉ giữ/di chuyển body; trách nhiệm serialize/deserialize JSON thuộc producer, consumer hoặc Spring `MessageConverter`.

### Kết quả học tập

Sau bài này, bạn sẽ hiểu được:

1. Khác biệt giữa JMS String body và byte body.
2. Khi nào cần quan tâm tới UTF-8, BOM, byte length và charset mismatch.
3. Cách dùng JMS API và `JmsTemplate` để gửi cả hai dạng.
4. Cách `SimpleMessageConverter` và `MappingJackson2MessageConverter` chọn kiểu message.
5. Cách thiết kế hợp đồng type/encoding/schema để dịch vụ Java và dịch vụ khác ngôn ngữ hiểu nhau.
6. Các lỗi chuyển đổi thường gặp và cách viết kiểm thử thực tế.

## 2. So sánh trực tiếp

| Khía cạnh | TextMessage | BytesMessage dùng cho JSON |
| --- | --- | --- |
| Kiểu body JMS | `java.lang.String` | Dãy byte |
| API tạo | `session.createTextMessage(json)` | `session.createBytesMessage()` rồi `writeBytes(...)` |
| API đọc | `getText()` hoặc `getBody(String.class)` | `getBody(byte[].class)` hoặc `readBytes(...)` |
| Định dạng JSON | Chuỗi JSON do ứng dụng tạo | Byte của chuỗi JSON theo encoding đã thỏa thuận |
| Ai xử lý encoding? | JMS provider trừu tượng hóa việc vận chuyển chuỗi | Ứng dụng/converter phải thống nhất cách biến byte thành text |
| Dễ xem nội dung trong công cụ quản trị | Thường dễ hơn | Phụ thuộc công cụ có tự decode bytes hay không |
| Độc lập ngôn ngữ | Có nếu consumer hỗ trợ kiểu text và JSON | Có nếu byte protocol/charset được thống nhất |
| Phù hợp dữ liệu thực sự nhị phân | Không phải lựa chọn tự nhiên | Phù hợp hơn |
| Tính đúng JSON | Không tự validate | Không tự validate |
| Selector JMS | Chỉ truy cập header/property hỗ trợ, không tự đọc JSON body | Tương tự |
| Hiệu năng | Tùy provider, payload, converter và network | Tùy provider, payload, converter và network |

**Không có quy luật chuẩn JMS nào bảo đảm BytesMessage luôn nhanh hơn hoặc nhỏ hơn TextMessage.** Với JSON text, hai dạng thường mang cùng nội dung logic. Kích thước *on-wire*, copy bộ nhớ, cache và compression phụ thuộc provider, client và cách Jackson tạo dữ liệu. Muốn chọn vì hiệu năng cần benchmark với broker và workload thực.

## 3. TextMessage: JSON dưới dạng String

API Jakarta JMS:

~~~java
// Đoạn mã trong callback có jakarta.jms.Session session:
String json = "{\"orderId\":\"O-42\",\"customer\":\"Hà\"}";
jakarta.jms.TextMessage message = session.createTextMessage(json);
~~~

Nhận:

~~~java
// Đoạn mã trong consumer đã có jakarta.jms.Message message:
if (message instanceof jakarta.jms.TextMessage textMessage) {
    String json = textMessage.getText();
    // Đưa json cho Jackson ObjectMapper hoặc JSON decoder khác.
}
~~~

Có thể dùng API chung của JMS 2.0+:

~~~java
String json = message.getBody(String.class);
~~~

Chỉ dùng cách này khi biết body có thể gán thành `String`, chẳng hạn từ `TextMessage`. Với `BytesMessage`, không nên gọi `getBody(String.class)` rồi mong provider tự chuyển byte sang UTF-8.

**TextMessage được JMS mô hình hóa là chuỗi ký tự**, không phải một dãy byte theo encoding được ứng dụng quyết định. Provider có thể chọn cách mã hóa trên dây riêng; chuẩn không bắt bạn tự gọi `getBytes` trước khi tạo `TextMessage`. Vì vậy, không đoán kích thước network chỉ từ `json.length()` hoặc giả định provider luôn gửi UTF-8 nguyên trạng.

Phù hợp khi:

- Payload là JSON/XML/văn bản có thể biểu diễn tự nhiên thành `String`.
- Muốn hợp đồng dễ quan sát, dễ debug bằng JMS console.
- Producer và consumer chủ yếu trao đổi chuỗi JSON, không cần kiểm soát chính xác byte payload.
- Cần ghép nhanh với `SimpleMessageConverter` dùng `String`.

Điểm cần xử lý: `getText()` có thể trả `null` nếu TextMessage không có body; cần validate JSON trước khi parse. TextMessage cũng không cho phép tự động query trường `orderId` bằng JMS selector; muốn selector phải đưa metadata cần lọc sang properties.

## 4. BytesMessage: JSON được mã hóa thành byte[]

Ví dụ gửi UTF-8:

~~~java
import java.nio.charset.StandardCharsets;
import jakarta.jms.BytesMessage;

// Đoạn mã trong callback có Session session:
String json = "{\"orderId\":\"O-42\",\"customer\":\"Hà\"}";
byte[] body = json.getBytes(StandardCharsets.UTF_8);

BytesMessage message = session.createBytesMessage();
message.writeBytes(body);
message.setStringProperty("contentType", "application/json");
message.setStringProperty("charset", "UTF-8");
~~~

Nhận theo API `getBody`:

~~~java
// Đoạn mã trong consumer đã có Message message:
byte[] data = message.getBody(byte[].class);
String json = new String(data, StandardCharsets.UTF_8);
~~~

Với một `BytesMessage` thông thường đã được nhận, `getBody(byte[].class)` lấy byte body dưới dạng mảng. Cách này dễ hiểu khi body có kích thước nhỏ/vừa và không cần xử lý streaming từng phần.

**Hợp đồng thiết yếu:** producer dùng UTF-8 thì consumer phải dùng UTF-8, hoặc dùng decoder JSON có thể nhận trực tiếp UTF-8 bytes. `BytesMessage` không có một thuộc tính charset chuẩn JMS bắt buộc provider tự áp vào mọi byte body. Nếu bạn chọn property `charset`, đó là **quy ước ứng dụng**; hai đầu phải hiểu và kiểm tra nó.

### 4.1. Cẩn thận với ký tự tiếng Việt

Ví dụ:

~~~java
String json = "{\"name\":\"Hà\"}";
System.out.println(json.length());
System.out.println(json.getBytes(StandardCharsets.UTF_8).length);
~~~

Output:

~~~text
13
14
~~~

`String.length()` tính số đơn vị UTF-16; byte length là số byte sau khi mã hóa UTF-8. Ký tự `à` là một đơn vị UTF-16 nhưng mã hóa thành hai byte UTF-8. Với emoji, một ký tự Unicode có thể dài hai đơn vị UTF-16 và bốn byte UTF-8.

Không được lấy `String.length()` làm độ dài bộ đệm byte hoặc giả định mỗi Java `char` là một byte. Sai lầm này gây cắt nội dung giữa byte của ký tự UTF-8.

### 4.2. Khi cần reject byte UTF-8 không hợp lệ

Constructor `new String(bytes, StandardCharsets.UTF_8)` có thể thay byte sequence không hợp lệ bằng ký tự thay thế, khiến ứng dụng **không phát hiện được dữ liệu hỏng**. Khi payload cần bảo toàn chính xác hoặc dữ liệu ký số, nên decode nghiêm ngặt:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public static String decodeUtf8Strict(byte[] bytes)
        throws CharacterCodingException {
    return StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes))
            .toString();
}
~~~

Đoạn này là method tiện ích; đặt trong một class Java phù hợp. Nếu decoder báo lỗi, đừng tự động nhận nội dung có ký tự thay thế như JSON hợp lệ. Hãy quyết định retry, dead-letter hoặc báo lỗi schema theo chính sách ứng dụng.

### 4.3. Đọc BytesMessage theo từng phần

`BytesMessage` là một stream bytes có con trỏ đọc. Khi một message được nhận, body ở chế độ đọc (read-only) và có thể dùng:

~~~java
// Đoạn mã trong consumer đã biết message là BytesMessage:
BytesMessage bytesMessage = (BytesMessage) message;
long length = bytesMessage.getBodyLength();
byte[] buffer = new byte[4096];
int n;
while ((n = bytesMessage.readBytes(buffer)) != -1) {
    // Xử lý đúng n byte đầu tiên trong buffer.
}
~~~

`getBodyLength()` trả **long**; không ép sang `int` hoặc cấp phát mảng theo kích thước chưa kiểm soát. Nếu đọc theo chunk, ký tự UTF-8 có thể bị tách giữa hai chunk. Không decode từng chunk độc lập bằng `new String(buffer, 0, n, UTF_8)`; hãy dùng decoder giữ trạng thái hoặc chuyển byte đến parser streaming phù hợp.

Khi vừa tạo một `BytesMessage` trong producer, body khởi đầu ở **write-only mode**; nếu cần đọc nó trước khi gửi, gọi `reset()` để chuyển sang read-only và đưa con trỏ về đầu. Với message đã nhận, provider đã đặt body vào read-only mode. `clearBody()` xóa body và chuyển sang chế độ có thể ghi; không nên gọi nó chỉ để “đọc lại”.

### 4.4. Vì sao không dùng writeUTF để gửi JSON raw?

~~~java
// Không tương đương với writeBytes(json.getBytes(UTF_8)):
bytesMessage.writeUTF(json);
~~~

`writeUTF` ghi chuỗi theo **modified UTF-8 có metadata độ dài theo định dạng JMS stream**, không phải chỉ các byte JSON UTF-8 thuần. Một consumer ngoài Java đọc toàn bộ body rồi parse JSON có thể thất bại vì có byte prefix. Khi hợp đồng là “body chính là raw UTF-8 JSON”, hãy dùng `writeBytes(json.getBytes(StandardCharsets.UTF_8))`.

## 5. Headers/properties vẫn tách khỏi body JSON

Cả TextMessage và BytesMessage đều có JMS headers (như `JMSMessageID`, `JMSCorrelationID`) và JMS properties (tên–giá trị có kiểu). Những metadata này **không nằm trong JSON body**, dù đôi khi chứa thông tin lặp lại để broker lọc hoặc quan sát.

Ví dụ contract gợi ý:

| Trường | Kiểu/vị trí | Ví dụ |
| --- | --- | --- |
| `eventId` | String property JMS | `evt-42` |
| `schemaVersion` | int property JMS | `1` |
| `contentType` | String property của ứng dụng | `application/json` |
| `charset` | String property (nếu dùng bytes) | `UTF-8` |
| `payloadKind` | String property | `text` hoặc `bytes` |
| JSON `orderId` | Trường trong body | `O-42` |
| JSON `amountVnd` | Trường trong body | `125000` |

`contentType`, `charset` và `payloadKind` **không phải tên header JMS chuẩn có cơ chế tự động phổ quát**. Các property này chỉ hữu ích khi cả producer/consumer định nghĩa cùng một convention.

Ví dụ selector:

~~~sql
schemaVersion = 1 AND payloadKind = 'bytes'
~~~

Selector chỉ đánh giá property/header JMS mà chuẩn cho phép, **không truy vấn được** `body.orderId` trong JSON thuần. Nếu consumer cần chỉ nhận sự kiện một loại, hãy cân nhắc property `eventType` thay vì parse toàn bộ JSON tại broker.

Cảnh báo: tránh đặt thông tin nhạy cảm hoặc khóa API vào property chỉ vì dễ lọc; metadata có thể hiện trong công cụ giám sát/broker log.

## 6. Spring JmsTemplate và SimpleMessageConverter

`JmsTemplate.convertAndSend(...)` dùng `MessageConverter` để chuyển Java object thành một Jakarta JMS message. Theo tài liệu Spring, `SimpleMessageConverter` mặc định hỗ trợ:

| Giá trị Java đưa vào convertAndSend | Kiểu message tạo ra |
| --- | --- |
| `String` | `TextMessage` |
| `byte[]` | `BytesMessage` |
| `Map` | `MapMessage` |
| `Serializable` | Có thể tạo `ObjectMessage` theo converter và kiểu |

Với JSON đã serialize sẵn:

~~~java
String json = "{\"orderId\":\"O-42\"}";

// Với SimpleMessageConverter mặc định:
jmsTemplate.convertAndSend("orders.json.demo", json);
// -> TextMessage

jmsTemplate.convertAndSend(
        "orders.json.demo", json.getBytes(StandardCharsets.UTF_8));
// -> BytesMessage
~~~

Đây là **snippet minh họa** trong class đã inject `JmsTemplate` và import `StandardCharsets`, không phải file Java độc lập. Kết quả trên phụ thuộc **converter đang cấu hình**: nếu ứng dụng đăng ký một `MessageConverter` tùy biến thì hành vi có thể khác.

Quan trọng hơn:

- `convertAndSend(destination, someDto)` **không tự đảm bảo JSON**. Nếu dùng converter đơn giản, object `Serializable` có thể bị đưa vào `ObjectMessage` dựa trên Java serialization; điều này không phù hợp khi trao đổi giữa nhiều ngôn ngữ và có rủi ro deserialization.
- `convertAndSend(destination, jsonString)` tạo TextMessage vì Java value đã là `String`, không phải vì Spring đã parse JSON.
- `convertAndSend(destination, jsonBytes)` tạo BytesMessage vì Java value là `byte[]`; Spring không biết bytes đó là JSON hay ảnh, trừ khi bạn quy ước.
- `receiveAndConvert(...)` trả về object theo converter, nhưng với default converter TextMessage thường thành String và BytesMessage thường thành byte[], **không tự thành OrderCreated DTO**.

Nếu muốn DTO tự chuyển thành JSON, cần cấu hình converter JSON tương ứng hoặc serialize/deserialize bằng Jackson rõ ràng.

## 7. MappingJackson2MessageConverter: mặc định là BYTES, có thể đổi sang TEXT

Spring Framework cung cấp `MappingJackson2MessageConverter` sử dụng Jackson để chuyển object sang JSON và ngược lại.

Hai chi tiết quan trọng từ Javadoc Spring:

1. **Mặc định `targetType = MessageType.BYTES`**. Nghĩa là nếu dùng converter JSON này mà không chỉnh target, một DTO có thể thành **BytesMessage JSON**.
2. Đặt `converter.setTargetType(MessageType.TEXT)` nếu muốn DTO thành **TextMessage JSON**.
3. Khi muốn nhận message chuyển lại thành DTO dựa trên type ID, phải đặt `typeIdPropertyName` và thống nhất mapping type ID. Nếu không, việc suy ra Java class khi nhận không có hợp đồng rõ.

Ví dụ cấu hình **thay thế** cho chiến lược serialize thủ công ở bài thực hành bên dưới:

~~~java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageConverter;
import org.springframework.jms.support.converter.MessageType;

@Configuration
class JsonJmsConverterConfiguration {

    @Bean
    MessageConverter jsonJmsMessageConverter() {
        var converter = new MappingJackson2MessageConverter();

        // Muốn TextMessage; bỏ dòng này sẽ dùng mặc định BYTES.
        converter.setTargetType(MessageType.TEXT);

        // Cần cho chiều đọc message trở lại Java object:
        converter.setTypeIdPropertyName("_type");
        converter.setTypeIdMappings(
                Map.of("order.created.v1", OrderCreated.class));

        return converter;
    }
}
~~~

Đây là **cấu hình phương án khác**, không thêm vào dự án mẫu phía dưới nếu chưa đổi cách gửi/nhận: ví dụ mẫu cố ý tạo `TextMessage` và `BytesMessage` bằng `JmsTemplate.send(...)` để nhìn rõ khác biệt. Nếu chuyển sang `convertAndSend(dto)` và `@JmsListener(OrderCreated)`, hãy bảo đảm cả producer và consumer sử dụng converter tương thích, type ID hợp lệ và dependency Jackson.

**Tại sao nên mapping type ID ổn định?** Không nên đưa tên class Java đầy đủ như `com.example.OrderCreated` thành contract công khai giữa các dịch vụ khi chỉ cần một tên sự kiện logic `order.created.v1`. Spring có thể sử dụng class name làm type ID nếu không có mapping phù hợp; điều này tăng mức độ ghép nối giữa producer và consumer. Với hệ phân tán, chuẩn hóa các type ID/version bằng tài liệu độc lập với Java packages.

**Encoding converter:** `MappingJackson2MessageConverter` có `setEncoding(...)` và `setEncodingPropertyName(...)`; mặc định encoding là UTF-8 khi chuyển qua BytesMessage. Nếu producer dùng encoding khác, cần cấu hình và truyền metadata cho chiều đọc. Việc chọn TEXT giúp đối tượng JMS mang String; chọn BYTES khiến consumer phải hiểu byte encoding/JSON converter.

## 8. Dự án chạy được: cùng JSON, gửi bằng hai kiểu JMS message

Bài thực hành dùng:

- Java 17.
- Spring Boot 3.3.x, Spring JMS, Jakarta Messaging.
- Apache ActiveMQ Artemis làm broker local.
- Jackson `ObjectMapper` để biến DTO thành JSON, **không** phụ thuộc lựa chọn converter bí ẩn.
- `JmsTemplate.send(...)` tạo TextMessage và BytesMessage minh bạch.
- Một `@JmsListener` nhận raw `jakarta.jms.Message`, phân nhánh theo kiểu, decode JSON, parse về cùng record.

### 8.1. Chạy broker Artemis

Yêu cầu Docker đang chạy. Một lệnh dùng image Artemis chính thức:

~~~bash
docker run --detach --rm --name artemis-json-types -p 127.0.0.1:61616:61616 -p 127.0.0.1:8161:8161 -e ARTEMIS_USER=demo -e ARTEMIS_PASSWORD=demo apache/artemis:latest
~~~

Chờ broker sẵn sàng, xem log:

~~~bash
docker logs artemis-json-types
~~~

Ví dụ mở cổng trên loopback host và dùng tài khoản demo **chỉ cho phòng lab**. Tùy cấu hình broker, Queue `orders.json.demo` có thể được tạo tự động hoặc phải được quản trị viên tạo trước. Không dùng cấu hình demo làm chính sách security/persistence của production.

### 8.2. Cấu trúc dự án

~~~text
jms-json-types/
  settings.gradle
  build.gradle
  src/main/resources/application.properties
  src/main/java/demo/json/
    JsonTypesApplication.java
    OrderCreated.java
    OrderPublisher.java
    OrderReceiver.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'jms-json-types'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
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
    implementation 'com.fasterxml.jackson.core:jackson-databind'
}
~~~

Jackson được khai báo trực tiếp và version được Spring Boot dependency management quản lý. Dùng Gradle 8.x tương thích, JDK 17+. Spring Boot 3 sử dụng `jakarta.jms` chứ không phải `javax.jms`.

File `src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none
spring.artemis.mode=native
spring.artemis.broker-url=${JMS_BROKER_URL:tcp://localhost:61616}
spring.artemis.user=${JMS_BROKER_USER:demo}
spring.artemis.password=${JMS_BROKER_PASSWORD:demo}
spring.jms.pub-sub-domain=false
~~~

Trong văn bản cuối, các biểu thức `${...}` ở ví dụ phải được hiểu và lưu dưới dạng **placeholder Spring chuẩn** bắt đầu bằng ký hiệu dollar và dấu ngoặc nhọn. Các default `demo` chỉ có giá trị trong local lab; production phải dùng secret injection, không hardcode mật khẩu.

### 8.3. DTO dùng chung cho hai cách gửi

File `src/main/java/demo/json/OrderCreated.java`:

~~~java
package demo.json;

public record OrderCreated(
        String eventId,
        String orderId,
        String customer,
        long amountVnd) {
}
~~~

Record Java 17 định nghĩa dữ liệu nghiệp vụ; Jackson đọc/ghi JSON cho record tương ứng. Cả hai JMS message sẽ có **cấu trúc JSON như nhau**, nhưng khác body type và event ID để phân biệt hai lượt gửi demo.

### 8.4. Entry point

File `src/main/java/demo/json/JsonTypesApplication.java`:

~~~java
package demo.json;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;

@SpringBootApplication
@EnableJms
public class JsonTypesApplication {

    public static void main(String[] args) {
        SpringApplication.run(JsonTypesApplication.class, args);
    }

    @Bean
    ObjectMapper objectMapper() {
        return new ObjectMapper();
    }

    @Bean
    CommandLineRunner publishTwoFormats(OrderPublisher publisher) {
        return args -> {
            publisher.publishText(new OrderCreated(
                    "evt-text-42", "O-42", "Hà", 125000));
            publisher.publishBytes(new OrderCreated(
                    "evt-bytes-43", "O-43", "Hà", 125000));
        };
    }
}
~~~

Dùng một `ObjectMapper` bean nhất quán cho producer và consumer. `CommandLineRunner` chỉ tạo dữ liệu demo lúc startup; thực tế cần publish khi nghiệp vụ xảy ra, không gửi lại sự kiện mỗi lần deploy.

### 8.5. Producer: tạo TextMessage và BytesMessage một cách tường minh

File `src/main/java/demo/json/OrderPublisher.java`:

~~~java
package demo.json;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.jms.BytesMessage;
import jakarta.jms.TextMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderPublisher {

    private static final String DESTINATION = "orders.json.demo";

    private final JmsTemplate template;
    private final ObjectMapper mapper;

    public OrderPublisher(JmsTemplate template, ObjectMapper mapper) {
        this.template = template;
        this.mapper = mapper;
    }

    public void publishText(OrderCreated event)
            throws JsonProcessingException {
        String json = mapper.writeValueAsString(event);

        template.send(DESTINATION, session -> {
            TextMessage message = session.createTextMessage(json);
            message.setStringProperty("payloadKind", "text");
            message.setStringProperty("contentType", "application/json");
            message.setIntProperty("schemaVersion", 1);
            message.setStringProperty("eventId", event.eventId());
            return message;
        });
    }

    public void publishBytes(OrderCreated event)
            throws JsonProcessingException {
        byte[] utf8 = mapper.writeValueAsBytes(event);

        template.send(DESTINATION, session -> {
            BytesMessage message = session.createBytesMessage();
            message.writeBytes(utf8);
            message.setStringProperty("payloadKind", "bytes");
            message.setStringProperty("contentType", "application/json");
            message.setStringProperty("charset", "UTF-8");
            message.setIntProperty("schemaVersion", 1);
            message.setStringProperty("eventId", event.eventId());
            return message;
        });
    }
}
~~~

Điểm cần học:

- `ObjectMapper.writeValueAsString(event)` tạo JSON String cho TextMessage.
- `ObjectMapper.writeValueAsBytes(event)` tạo JSON byte[]; Jackson mặc định tạo JSON UTF-8 ở nhánh này.
- `Session.createTextMessage(json)` và `Session.createBytesMessage()` xác định **JMS message type**.
- `template.send(..., MessageCreator)` không gọi converter cho body; callback tự tạo `jakarta.jms.Message`.
- Metadata nằm trong JMS properties, không nằm trong JSON body dù cùng `eventId` xuất hiện ở cả hai nơi.
- `charset= UTF-8` là property do ứng dụng quy ước; provider không tự parse bytes thành JSON.

### 8.6. Consumer: nhận JMS Message nguyên bản

File `src/main/java/demo/json/OrderReceiver.java`:

~~~java
package demo.json;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.jms.BytesMessage;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderReceiver {

    private final ObjectMapper mapper;

    public OrderReceiver(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    @JmsListener(destination = "orders.json.demo", concurrency = "1")
    public void receive(Message message) throws Exception {
        if (!"application/json".equals(
                message.getStringProperty("contentType"))) {
            throw new IllegalArgumentException("Expected JSON contentType");
        }
        if (message.getIntProperty("schemaVersion") != 1) {
            throw new IllegalArgumentException("Unsupported schemaVersion");
        }

        String json;
        String representation;

        if (message instanceof TextMessage text) {
            json = text.getText();
            representation = "text";
        } else if (message instanceof BytesMessage bytes) {
            if (!"UTF-8".equalsIgnoreCase(
                    message.getStringProperty("charset"))) {
                throw new IllegalArgumentException("Expected UTF-8 bytes");
            }
            byte[] raw = bytes.getBody(byte[].class);
            json = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(raw))
                    .toString();
            representation = "bytes";
        } else {
            throw new IllegalArgumentException(
                    "Unsupported JMS message type: " + message.getClass());
        }

        OrderCreated event = mapper.readValue(json, OrderCreated.class);
        System.out.printf(
                "RECEIVED=%s orderId=%s customer=%s amountVnd=%d%n",
                representation, event.orderId(),
                event.customer(), event.amountVnd());
    }
}
~~~

Điều quan trọng:

1. Listener nhận `jakarta.jms.Message`, **không** buộc parameter luôn là String. Vì vậy có thể kiểm tra kiểu body gốc.
2. Với TextMessage, `getText()` trả JSON String.
3. Với BytesMessage, `getBody(byte[].class)` lấy raw bytes, decoder UTF-8 dùng `REPORT` khi gặp encoding sai thay vì âm thầm thay ký tự.
4. Sau khi có JSON String, cả hai nhánh đều dùng `mapper.readValue(json, OrderCreated.class)` nên nghiệp vụ không cần quan tâm cách body đã được vận chuyển.
5. Nếu parse/schema không hợp lệ, listener ném lỗi. ACK/redelivery/DLQ phụ thuộc transaction và error-handling configuration của listener/broker; ứng dụng production phải có policy phù hợp.

`payloadKind` có thể dùng làm metadata quan sát, nhưng ví dụ tin vào **JMS message type thực tế** hơn là chỉ tin chuỗi property do client gửi. Nếu property ghi "text" nhưng message thật là BytesMessage, hệ thống nên báo lỗi contract.

### 8.7. Chạy và giải thích kết quả

Với broker đã sẵn sàng:

~~~bash
gradle bootRun
~~~

Hai dòng do consumer in ra ở điều kiện bình thường:

~~~text
RECEIVED=text orderId=O-42 customer=Hà amountVnd=125000
RECEIVED=bytes orderId=O-43 customer=Hà amountVnd=125000
~~~

Spring và Artemis có thể ghi log khác xen kẽ. Trong Queue có một listener concurrency=1, message thường được tiêu thụ theo thứ tự publish của ví dụ, nhưng không thiết kế nghiệp vụ phụ thuộc chặt vào thứ tự log khi chạy với concurrency khác, retry hoặc nhiều consumer. Nếu broker chưa sẵn sàng, credentials sai hoặc thiếu permission, ví dụ không bảo đảm hai dòng xuất hiện.

Dừng broker sau khi xong:

~~~bash
docker stop artemis-json-types
~~~

## 9. Demo Java 17 độc lập: char length khác UTF-8 byte length

Chương trình này không phụ thuộc Spring/JMS, có thể biên dịch ngay bằng JDK 17; dùng nó để tự xác minh vấn đề charset trước khi ghép broker.

File `EncodingProof.java`:

~~~java
import java.nio.charset.StandardCharsets;

public class EncodingProof {
    public static void main(String[] args) {
        String json = "{\"name\":\"Hà\"}";
        byte[] utf8 = json.getBytes(StandardCharsets.UTF_8);
        String decoded = new String(utf8, StandardCharsets.UTF_8);

        System.out.println("utf16Units=" + json.length());
        System.out.println("utf8Bytes=" + utf8.length);
        System.out.println("roundTrip=" + json.equals(decoded));
    }
}
~~~

Chạy trong thư mục có file:

~~~bash
javac EncodingProof.java
java EncodingProof
~~~

Output:

~~~text
utf16Units=13
utf8Bytes=14
roundTrip=true
~~~

Đây là ví dụ **với bytes UTF-8 hợp lệ**. Nếu bytes đã bị hỏng, constructor `new String(...)` có thể thay thế ký tự không hợp lệ; khi cần kiểm tra dữ liệu chặt, sử dụng `CharsetDecoder` ở mục trước.

## 10. Chọn cách nào trong một hệ thống thật?

### 10.1. Ưu tiên TextMessage khi dữ liệu vốn là JSON text

TextMessage thường là lựa chọn dễ đọc khi:

- Dịch vụ gửi/nhận JSON chủ yếu để tích hợp API/event nghiệp vụ.
- Hệ thống cần kiểm tra payload bằng công cụ quản trị broker.
- Không có yêu cầu giữ nguyên **byte sequence** do hệ thống ngoài gửi vào.
- Hai phía đồng ý serialize/parse JSON dưới dạng String.
- Dùng Spring converter `MessageType.TEXT` hoặc `SimpleMessageConverter` với String.

Đổi lại, Java String và JSON parser vẫn tạo bộ nhớ/tài nguyên, và encoding nội bộ trên dây phụ thuộc broker; “TextMessage dễ đọc” không bảo đảm message nhỏ hơn.

### 10.2. Ưu tiên BytesMessage khi byte-level contract quan trọng

BytesMessage thích hợp khi:

- Consumer ngoài Java yêu cầu **raw UTF-8 bytes** đúng định dạng đã thỏa thuận.
- Payload đã được serialize thành byte[] từ thư viện JSON, schema registry hay một pipeline có sẵn.
- Có chuẩn truyền tải binary (Avro/Protobuf) hoặc payload có chữ ký/hash trên byte sequence; với JSON, phải có chính sách canonicalization riêng nếu chữ ký yêu cầu byte chính xác.
- Muốn kết hợp compression, encryption hoặc checksum ở application layer và có contract rõ ràng (thường body lúc đó không còn là raw JSON text, phải mô tả lại content encoding).
- Cần đồng bộ byte-level encoding giữa producer và consumer, không muốn phụ thuộc cách provider biểu diễn String.

Đổi lại, cần công bố charset và test invalid bytes; công cụ quản trị có thể hiển thị dạng hex/base64 thay vì JSON, và code phải phân biệt `BytesMessage` với TextMessage.

### 10.3. Không chọn chỉ vì “BytesMessage nhanh hơn”

Benchmark cần cùng payload, cùng schema, cùng broker, cùng network, cùng delivery mode, cùng consumer concurrency và cùng ACK/transaction. Đo:

- Message throughput và p50/p95/p99 latency.
- CPU và lượng cấp phát/GC ở Java producer/consumer.
- Kích thước message trên wire hoặc journal (nếu quan sát được).
- Số lần serialize/deserialize và copy byte trong converter.
- Mức độ dễ quan sát, debug và xử lý lỗi trong vận hành.

Jackson `writeValueAsBytes` có thể tránh một bước tạo String trong một số pipeline, nhưng JMS provider và network serialization vẫn có thể tạo copy khác. Không có “nhanh hơn tuyệt đối” chỉ từ tên JMS message type.

## 11. Contract dữ liệu: quan trọng hơn lựa chọn text hay bytes

Một message contract được version hóa cần nói rõ:

~~~yaml
destination: orders.json.demo
eventType: order.created
schemaVersion: 1
bodyFormat: application/json
messageTypesAccepted:
  - TextMessage
  - BytesMessage
bytesCharset: UTF-8
requiredProperties:
  eventId: string
  schemaVersion: integer
  contentType: string
businessFields:
  eventId: string
  orderId: string
  customer: string
  amountVnd: integer
~~~

Đây là **tài liệu contract YAML minh họa**, không phải file `application.yml` của Spring Boot. Các property như `contentType`, `charset`, `schemaVersion` phải được định nghĩa và validate nhất quán; không có cơ chế JMS chung tự biến chúng thành schema validator.

Đặc biệt quan trọng:

1. **Kiểu body**: dùng chỉ một kiểu (đơn giản hơn), hay cho phép hai kiểu trong giai đoạn migration? Nếu hai kiểu, decoder phải xử lý rõ cả hai.
2. **Charset**: với BytesMessage JSON, thống nhất UTF-8 và không dùng `writeUTF`; nếu nhận bytes khác encoding, từ chối theo policy.
3. **Schema version**: consumer phải biết có thể nhận phiên bản nào; không tự ép về DTO mới nếu đổi field không tương thích.
4. **Trường bắt buộc/nullable**: Jackson parse được JSON chưa có nghĩa business contract hợp lệ. Validate eventId/orderId/amountVnd sau deserialize.
5. **Định danh nghiệp vụ**: eventId trong property/body ổn định qua retry để consumer idempotent; không chỉ dựa vào `JMSMessageID`.
6. **Bảo mật**: payload có PII cần mã hóa đường truyền, ACL destination, tránh log toàn body; JSON text dễ nhìn cũng dễ bị lộ hơn khi debug không kiểm soát.
7. **Kích thước tối đa**: đặt giới hạn payload trước khi cấp phát mảng lớn, parse sâu, deserialize dữ liệu không tin cậy. Large message cần cơ chế riêng của broker hoặc lưu object ngoài và gửi reference.

## 12. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Cast `TextMessage` bị lỗi | Producer gửi `byte[]`/BytesMessage | Kiểm tra type gốc; xử lý nhánh BytesMessage hoặc chuẩn hóa contract |
| `getBody(String.class)` thất bại | Body thực sự là BytesMessage | Lấy `byte[].class` rồi decode charset |
| JSON bị thành `H�` hoặc dấu tiếng Việt sai | Charset mismatch hoặc invalid UTF-8 bị thay thế | Thống nhất UTF-8, dùng decoder strict, kiểm tra bytes thực |
| Parser gặp ký tự lạ đầu body | Có BOM/prefix từ `writeUTF` hoặc encoding khác | Gửi raw UTF-8 bằng `writeBytes`; không dùng stream writeUTF cho JSON |
| `MessageNotReadableException` | Đọc BytesMessage đang ở write-only mode | Gọi `reset()` trước khi đọc body vừa tạo; message nhận đã ở read mode |
| `MessageNotWriteableException` | Sửa body của received message đang read-only | Tạo message mới hoặc hiểu rõ `clearBody()` |
| `receiveAndConvert` trả `byte[]` thay vì DTO | Đang dùng SimpleMessageConverter | Dùng Jackson converter có type ID hoặc parse JSON rõ ràng |
| DTO gửi thành `ObjectMessage` | Converter mặc định chọn Java serialization | Đăng ký JSON converter và xác minh `targetType` |
| Đăng ký Jackson converter nhưng không nhận DTO | Chưa có type ID hoặc mapping không tương thích | Đặt `setTypeIdPropertyName` và thống nhất mapping |
| JSON parse được nhưng field sai | Schema/version drift | Kiểm tra version, nullable/bắt buộc và validation |
| Selector không lọc được `orderId` trong JSON | Selector không đọc body JSON | Đưa khóa lọc cần thiết vào JMS property |
| Body bytes quá lớn gây memory pressure | Đọc toàn bộ bằng mảng/cấp phát không giới hạn | Giới hạn kích thước, streaming/broker large-message policy |
| Consumer nhận trùng | Retry/redelivery | Dùng business eventId + idempotent consumer |
| Handler lỗi liên tục với JSON xấu | Poison message/invalid payload | Retry có giới hạn, DLQ, observability và schema validation |

Một lỗi conversion không nên bị retry vô hạn nếu payload không thể parse bởi schema đang triển khai. Hãy tách lỗi dữ liệu vĩnh viễn khỏi lỗi broker/network tạm thời; cấu hình retry/DLQ phù hợp để tránh chặn Queue.

## 13. Chiến lược kiểm thử từ thấp đến cao

### 13.1. Unit test serialize/deserialize

Không cần broker:

- Serialize `OrderCreated` thành String/byte[].
- Dùng Jackson đọc lại cả hai dạng.
- Kiểm tra trường tiếng Việt, ký tự đặc biệt, chữ số và null/empty case.
- Kiểm tra UTF-8 malformed phải bị reject nếu contract yêu cầu strict decoding.
- Thử schemaVersion không hỗ trợ, field bắt buộc thiếu, JSON sai cú pháp.

Không dùng byte length bằng String length; dùng `StandardCharsets.UTF_8` và chỉ kiểm tra các thuộc tính mà code thực sự cam kết.

### 13.2. Unit test JMS MessageConverter

Với `SimpleMessageConverter`, cần verify `String -> TextMessage`, `byte[] -> BytesMessage` bằng một JMS `Session` mock/provider fixture đủ chính xác. Với `MappingJackson2MessageConverter`, test hai giá trị `MessageType.TEXT` và `MessageType.BYTES`, type ID mapping và encoding property. Đừng chỉ test converter chiều gửi; chiều nhận thường là chỗ lộ vấn đề type ID.

### 13.3. Integration test với broker

Một integration test đáng tin cần:

1. Broker Artemis thật trong môi trường test (ví dụ Docker/Testcontainers).
2. Cấu hình `ConnectionFactory` và `JmsTemplate` như deployment thực.
3. Gửi một TextMessage và một BytesMessage với JSON giống contract.
4. Consumer nhận, phân biệt type gốc, decode đúng Unicode và deserialize DTO.
5. Xác minh metadata `schemaVersion`, `contentType`, `eventId`.
6. Thử negative cases (sai charset, JSON invalid, schema mới) cùng cơ chế DLQ/retry.
7. Kiểm tra timeout, ACK và rollback nếu hệ thống yêu cầu bảo đảm phân phối.

**Không nhầm unit test converter với kiểm chứng broker.** Mockito có thể xác minh `JmsTemplate.send` được gọi nhưng không chứng minh hai message tới Queue, persistence hoạt động hoặc consumer ACK.

### 13.4. Test tích hợp nhiều ngôn ngữ

Nếu Java producer trao đổi với Python, Node.js hoặc hệ thống khác, chạy **consumer thật của ngôn ngữ đó**. Thử cả payload tiếng Việt, emoji, dấu xuống dòng, field chưa biết và schemaVersion thay đổi. Một TextMessage của JMS không có nghĩa mọi client không-Java tự suy ra contract như nhau; phải dùng đúng protocol/client và kiểm tra kết quả end-to-end.

## 14. Câu hỏi tự đánh giá

**1.** JSON là kiểu JMS message hay định dạng dữ liệu?

JSON là định dạng dữ liệu. `TextMessage` và `BytesMessage` là kiểu JMS body; JSON có thể nằm ở cả hai.

**2.** `convertAndSend(queue, jsonString)` với SimpleMessageConverter tạo gì?

Thông thường `TextMessage` vì giá trị Java là `String`.

**3.** `convertAndSend(queue, jsonBytes)` với SimpleMessageConverter tạo gì?

`BytesMessage` vì giá trị Java là `byte[]`.

**4.** `MappingJackson2MessageConverter` mặc định gửi JSON DTO dạng TextMessage không?

Không. Theo Spring, target mặc định của converter này là `MessageType.BYTES`; muốn text phải `setTargetType(MessageType.TEXT)`.

**5.** Vì sao `bytesMessage.writeUTF(json)` không tương đương `writeBytes(json.getBytes(UTF_8))`?

`writeUTF` dùng biểu diễn modified UTF-8 có thành phần độ dài dành cho JMS stream; nó không phải raw UTF-8 JSON body.

**6.** Vì sao `String.length()` có thể khác số byte UTF-8?

Java `String.length()` đếm UTF-16 code units; ký tự Unicode có thể cần nhiều byte UTF-8.

**7.** `getBody(String.class)` dùng được cho một BytesMessage JSON UTF-8 bất kỳ?

Không. Với BytesMessage hãy nhận byte[] rồi decode theo contract.

**8.** Property `contentType=application/json` có khiến JMS broker tự parse JSON không?

Không. Đó là metadata ứng dụng; broker không tự biến body thành JSON AST.

**9.** Converter Jackson đã được đăng ký, muốn nhận lại DTO cần quan tâm gì?

Type ID property/mapping, body type, encoding và việc producer/consumer dùng converter tương thích.

**10.** BytesMessage có luôn nhanh hơn TextMessage không?

Không; phải benchmark toàn đường đi với cùng provider, workload, conversion và broker.

## 15. Tài liệu chính thức

- Jakarta Messaging 3.1 — Message Types, TextMessage, BytesMessage, `getBody`: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Jakarta Messaging API — `TextMessage`: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/textmessage
- Jakarta Messaging API — `BytesMessage`: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/bytesmessage
- Jakarta Messaging API — `Message#getBody`: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message
- Spring Framework — Sending a Message, SimpleMessageConverter: https://docs.spring.io/spring-framework/reference/integration/jms/sending.html
- Spring Framework — `MappingJackson2MessageConverter` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html
- Spring Guide — Messaging with JMS (Jackson converter target TEXT): https://spring.io/guides/gs/messaging-jms/
- Spring Boot — JMS/Artemis support: https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html

**Ghi nhớ:** Với JSON, chọn **TextMessage** khi muốn trao đổi String rõ ràng, dễ quan sát; chọn **BytesMessage** khi hợp đồng yêu cầu raw bytes/UTF-8 hoặc xử lý byte-level. Cả hai đều cần schema, charset/version contract, MessageConverter đúng và kiểm thử end-to-end; đừng coi kiểu JMS message là JSON parser hay bảo đảm phân phối.
