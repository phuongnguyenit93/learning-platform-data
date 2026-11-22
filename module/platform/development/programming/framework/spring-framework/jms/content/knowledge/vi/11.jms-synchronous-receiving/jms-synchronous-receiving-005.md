# receiveAndConvert và kiểu dữ liệu sau chuyển đổi

**Chủ đề:** Spring Framework - jms → Nhận đồng bộ.

## 1. Vì sao cần receiveAndConvert?

JMS (Jakarta Messaging) truyền các đối tượng thuộc hệ giao diện `jakarta.jms.Message` như `TextMessage`, `BytesMessage`, `MapMessage` và `ObjectMessage`. Khi chỉ cần giá trị nghiệp vụ bên trong message, ứng dụng Spring không nhất thiết phải tự kiểm tra từng lớp JMS, gọi getter trên body và quản lý `Session`/`MessageConsumer`.

`org.springframework.jms.core.JmsTemplate` cung cấp:

~~~java
Object receiveAndConvert();
Object receiveAndConvert(String destinationName);
Object receiveAndConvert(jakarta.jms.Destination destination);
~~~

Đây là **chữ ký rút gọn để học**: trong Spring, giá trị có thể là `null` và các phương thức có thể ném `org.springframework.jms.JmsException` (unchecked).

`receiveAndConvert(...)` làm hai việc liên tiếp:

1. **Receive:** nhận **đồng bộ** một JMS message từ destination đã chọn, với giới hạn chờ theo cấu hình.
2. **Convert:** gọi `MessageConverter.fromMessage(message)` để lấy **đối tượng Java** tương ứng.

Ví dụ với một queue chỉ chứa `TextMessage` có body `"hello"`:

~~~java
Object value = jmsTemplate.receiveAndConvert("demo.messages");
if (value instanceof String text) {
    System.out.println(text);
}
~~~

Nếu lấy đúng message đó, chương trình in:

~~~text
hello
~~~

Đoạn trên là **trích đoạn**, giả định `jmsTemplate` được cấu hình với `ConnectionFactory` và broker hợp lệ. Nếu queue rỗng và hết timeout, `value` có thể là `null`; khi đó không có stdout trong đoạn code.

**Điểm cốt lõi:** loại Java trả về không dựa vào tên queue, biến đích hoặc kiểu mong muốn của người gọi. Nó phụ thuộc **loại JMS message thực nhận** và **MessageConverter đang được cấu hình**.

## 2. Quy trình nhận đồng bộ và chuyển đổi

~~~text
                      Caller / ApplicationRunner / Service
                                      |
                       JmsTemplate.receiveAndConvert(...)
                                      |
                          chọn destination thực tế
                                      |
                           ConnectionFactory / Session
                                      |
                             MessageConsumer.receive(...)
                                      |
                             JMS message hoặc null
                                      |
                          +-----------+-----------+
                          |                       |
                       null                  JMS Message
                          |                       |
                 return null                 MessageConverter
                                           .fromMessage(message)
                                                  |
                                           Java Object
                                                  |
                                      return Object cho caller
~~~

Vì đây là **synchronous receive**, thread đang gọi method có thể **bị chặn** đến khi nhận được message hoặc hết thời gian chờ. Khác với `@JmsListener`, cách này không duy trì sẵn một listener method xử lý bất đồng bộ.

Kết quả:

- Có message và converter thành công → trả về giá trị Java.
- Không nhận được message trong khoảng chờ → trả `null`.
- Mở kết nối, tạo consumer, nhận hoặc chuyển đổi lỗi → thường ném ngoại lệ theo API Spring/JMS.
- Với converter có thể trả `null` cho một body hợp lệ rỗng, **`null` một mình không luôn đủ để khẳng định timeout**, đặc biệt nếu dùng custom converter hoặc TextMessage có body `null`.

### 2.1. receive và receiveAndConvert khác gì nhau?

| Lời gọi | Kiểu trả về | Kết quả thực tế | Phù hợp khi |
| --- | --- | --- | --- |
| `jmsTemplate.receive("queue")` | `jakarta.jms.Message` hoặc `null` | JMS message gốc gồm headers, properties và body | Cần đọc `JMSCorrelationID`, `JMSReplyTo`, `JMSMessageID`, properties |
| `jmsTemplate.receiveAndConvert("queue")` | `Object` hoặc `null` | Giá trị Java sau conversion của message body | Chỉ cần xử lý payload nghiệp vụ |
| `jmsTemplate.receiveSelectedAndConvert("queue", selector)` | `Object` hoặc `null` | Payload sau khi nhận message thỏa selector | Cần lọc metadata ở broker |
| `@JmsListener(destination = "queue")` | Không phải lời gọi nhận đồng bộ | Spring listener container gọi handler khi message đến | Consumer liên tục, bất đồng bộ |

`receiveAndConvert` **không** tự tạo wrapper giữ toàn bộ JMS headers trong Java object kết quả. Nếu cần correlation hoặc thuộc tính như `eventType`, hãy cân nhắc nhận raw `Message` rồi đọc metadata và convert có chủ đích.

## 3. Kiểu Java nhận được với SimpleMessageConverter

Mặc định `JmsTemplate` sử dụng `org.springframework.jms.support.converter.SimpleMessageConverter`, nếu ứng dụng chưa cấu hình converter khác. Đây là converter hỗ trợ bốn loại JMS message phổ biến. Sau khi nhận:

| JMS message thực nhận | Nội dung JMS | Java object trả về từ `receiveAndConvert` | Ví dụ |
| --- | --- | --- | --- |
| `TextMessage` | Văn bản | `String` | `"order-42"` |
| `BytesMessage` | Dãy byte | `byte[]` | `new byte[]{1,2,3}` |
| `MapMessage` | Các entry tên–giá trị theo kiểu JMS | `Map<String, Object>` | `{"quantity":3, "orderId":"A42"}` |
| `ObjectMessage` | Object Java đã được serialize | Object được deserialize, thuộc kiểu Serializable đã gửi (nếu tương thích) | `Integer.valueOf(42)` hoặc DTO Serializable |
| Một JMS message type khác, ví dụ `StreamMessage` | Không thuộc bốn loại ở trên | **Chính JMS `Message` object** trong SimpleMessageConverter 6.x | Cần kiểm tra kiểu thực |

**Đặc biệt:** `SimpleMessageConverter.fromMessage` của Spring Framework 6.x trả **plain JMS Message** nếu không nhận diện một trong bốn nhóm. Không được mặc định suy luận mọi kiểu JMS khác sẽ bị ném `MessageConversionException`. Một custom converter có thể chọn hành vi khác.

Loại Java ở cột ba là **runtime type**, không phải generic return type của phương thức: chữ ký vẫn trả `Object`. Ứng dụng phải dùng `instanceof`, cast an toàn hoặc contract đã kiểm chứng trước khi truy cập.

### 3.1. TextMessage → String

Một producer:

~~~java
jmsTemplate.convertAndSend("demo.messages", "Xin chào JMS");
~~~

thường tạo `TextMessage` bằng converter mặc định. Khi caller nhận đúng message ấy:

~~~java
Object value = jmsTemplate.receiveAndConvert("demo.messages");
if (value instanceof String text) {
    System.out.println(text);
}
~~~

Kết quả:

~~~text
Xin chào JMS
~~~

**Chú ý:** TextMessage chứa chuỗi JSON, ví dụ `"{\"orderId\":\"A42\"}"`, vẫn trở thành **String**, không tự trở thành `Map` hoặc class `OrderEvent`. `SimpleMessageConverter` **không tự parse JSON**. Muốn nhận DTO Java từ JSON cần Jackson/converter riêng hoặc parse String sau khi nhận.

### 3.2. BytesMessage → byte[]

Producer gửi bytes:

~~~java
jmsTemplate.convertAndSend(
        "demo.messages", new byte[]{1, 2, 3});
~~~

Consumer nhận:

~~~java
import java.util.Arrays;

Object value = jmsTemplate.receiveAndConvert("demo.messages");
if (value instanceof byte[] bytes) {
    System.out.println(Arrays.toString(bytes));
}
~~~

Khi đúng message được nhận, stdout:

~~~text
[1, 2, 3]
~~~

**Không có giải mã charset mặc định.** `byte[]` chỉ là các byte; nếu chứa UTF-8, Avro, Protobuf, ảnh hoặc file, caller phải tự decode bằng schema/codec đúng. Đừng làm `(String) value` khi runtime type là `byte[]`.

Ví dụ chuyển `byte[]` sang văn bản khi hợp đồng thật sự là UTF-8:

~~~java
import java.nio.charset.StandardCharsets;

if (value instanceof byte[] bytes) {
    String text = new String(bytes, StandardCharsets.UTF_8);
    System.out.println(text);
}
~~~

Đây là **trích đoạn nhận kết quả có sẵn**, không phải chương trình độc lập. Với binary payload không phải text, thao tác decode UTF-8 có thể cho kết quả sai ý nghĩa.

### 3.3. MapMessage → Map<String, Object>

Producer có thể gửi một Java Map hợp lệ:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

Map<String, Object> order = new LinkedHashMap<>();
order.put("orderId", "A42");
order.put("quantity", 3);
order.put("express", true);

jmsTemplate.convertAndSend("demo.messages", order);
~~~

SimpleMessageConverter tạo `MapMessage` với các key/giá trị mà loại JMS này chấp nhận. Khi nhận:

~~~java
Object value = jmsTemplate.receiveAndConvert("demo.messages");

if (value instanceof Map<?, ?> data) {
    System.out.println("orderId=" + data.get("orderId"));
    System.out.println("quantity=" + data.get("quantity"));
    System.out.println("express=" + data.get("express"));
}
~~~

Kết quả nếu đúng message trên:

~~~text
orderId=A42
quantity=3
express=true
~~~

Đừng cast thành `LinkedHashMap` chỉ vì producer dùng `LinkedHashMap`; converter chỉ cam kết một `Map` phù hợp. Cũng không dựa vào thứ tự iteration của MapMessage. MapMessage body values chỉ hỗ trợ các kiểu theo JMS như primitives/wrappers, `String`, `byte[]`; nó không tự hỗ trợ nested DTO, `BigDecimal` hoặc `List` tùy ý.

### 3.4. ObjectMessage → Serializable object đã giải mã

Một đối tượng Serializable khác ba nhóm trên có thể được converter chuyển thành `ObjectMessage`. Ví dụ:

~~~java
jmsTemplate.convertAndSend(
        "demo.messages", Integer.valueOf(42));
~~~

Khi consumer nhận message dưới dạng `ObjectMessage` và nhà cung cấp JMS cho phép Java deserialization:

~~~java
Object value = jmsTemplate.receiveAndConvert("demo.messages");

if (value instanceof Integer number) {
    System.out.println(number);
}
~~~

Output:

~~~text
42
~~~

Nếu là DTO:

~~~java
import java.io.Serial;
import java.io.Serializable;

public record OrderNotice(String orderId)
        implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;
}
~~~

Đây là **file OrderNotice.java** riêng nếu dùng public record. Hai bên phải có class tương thích, cùng quy tắc serialization và chính sách tin cậy phù hợp. Java record **không tự implements Serializable**, nên phải khai báo nếu chọn đường ObjectMessage.

**Cảnh báo an toàn:** Java deserialization từ untrusted message có thể nguy hiểm. Không nới rộng mọi trusted package/class của JMS provider một cách tùy tiện. Với giao tiếp liên dịch vụ/đa ngôn ngữ, thường ưu tiên JSON TextMessage hoặc schema-based BytesMessage và mapping có kiểm soát thay ObjectMessage.

### 3.5. Kiểu JMS lạ không chắc bị lỗi conversion

Spring Framework 6.x `SimpleMessageConverter.fromMessage` nhận bốn loại trên. Khi gặp JMS Message type không được hỗ trợ đặc biệt (ví dụ `StreamMessage`), nó có thể **trả về nguyên object JMS Message**, không phải value đã giải mã. Do đó:

~~~java
Object result = jmsTemplate.receiveAndConvert("demo.messages");

if (result instanceof jakarta.jms.Message rawMessage) {
    System.out.println("No specific conversion for JMS type");
}
~~~

Đây là trích đoạn minh họa. Nó không có nghĩa mọi `result instanceof jakarta.jms.Message` là lỗi; có thể vì converter mặc định đã chọn đường fallback, hoặc custom converter cố ý trả nguyên message.

## 4. receiveAndConvert có những overload nào?

Trong Spring Framework 6.x, ba overload cơ bản:

~~~java
Object a = jmsTemplate.receiveAndConvert();
Object b = jmsTemplate.receiveAndConvert("demo.messages");
Object c = jmsTemplate.receiveAndConvert(destination);
~~~

- **Không đối số:** đọc từ `defaultDestination` hoặc `defaultDestinationName` đã được cấu hình trên **chính JmsTemplate** đó. Nếu không có default, method không biết cần nhận từ đâu và báo lỗi cấu hình.
- **String destinationName:** dùng `DestinationResolver` chuyển tên thành object `Destination`, rồi nhận từ đó. `pubSubDomain=false` thường resolve như Queue; `true` dùng Topic theo cấu hình resolver.
- **Destination object:** nhận trực tiếp từ object được cung cấp, chẳng hạn administered destination từ JNDI/provider.

Ba câu lệnh trên là **trích đoạn**, `destination` phải là `jakarta.jms.Destination` thực và template đã có kết nối.

Một ví dụ default:

~~~java
jmsTemplate.setDefaultDestinationName("demo.messages");
jmsTemplate.setReceiveTimeout(2_000L);

Object value = jmsTemplate.receiveAndConvert();
~~~

Đây là cấu hình **trước khi sử dụng template**, không nên đổi default/timing trên singleton template theo từng HTTP request đa luồng. Nếu xử lý nhiều destination, truyền destination tường minh hoặc dùng nhiều bean template cấu hình cố định.

### 4.1. receiveSelectedAndConvert và message selector

Khi muốn lấy một message thỏa điều kiện metadata:

~~~java
Object value = jmsTemplate.receiveSelectedAndConvert(
        "demo.messages",
        "eventType = 'ORDER_CREATED' AND priorityLevel >= 5");
~~~

Đây là overload **`receiveSelectedAndConvert(String destinationName, String messageSelector)`**. Selector dùng JMS message properties và một số standard headers được cho phép, **không** đọc body của TextMessage/MapMessage.

Để selector trên hoạt động, producer phải đặt property có đúng kiểu:

~~~java
jmsTemplate.convertAndSend(
        "demo.messages",
        "order-42",
        message -> {
            message.setStringProperty("eventType", "ORDER_CREATED");
            message.setIntProperty("priorityLevel", 7);
            return message;
        });
~~~

Khi receive một message phù hợp, converter mặc định vẫn trả **String** `"order-42"`. Selector quyết định **message nào được chọn**, không quyết định **kiểu Java sẽ được chuyển đổi**.

Lưu ý `priorityLevel` phải có kiểu numeric (ví dụ int) để so sánh `>= 5`, không phải String `"7"`; JMS selector **không áp dụng** bảng ép kiểu getter property.

## 5. receiveTimeout và ý nghĩa của null

Vì đây là nhận **đồng bộ**, cần hiểu `receiveTimeout` để tránh vô tình chặn thread lâu.

### 5.1. Quy tắc nhận chờ của JmsTemplate

| Cấu hình `receiveTimeout` | Ý nghĩa |
| --- | --- |
| `0` | **Chờ vô hạn** cho đến khi message đến hoặc có lỗi/đóng tài nguyên |
| Số dương, ví dụ `2_000` | Chờ tối đa xấp xỉ 2 giây |
| Số âm, ví dụ `-1` | **Không chờ**: thử nhận message có ngay lập tức rồi trả về |

Trường hợp mặc định của `JmsTemplate` là **indefinite wait** (giá trị 0). Đừng nhầm với Spring listener container hoặc Spring Integration inbound adapter, chúng có quy tắc timeout riêng.

~~~java
// Chỉ cấu hình một lần khi tạo bean, không mutate cho mỗi request.
jmsTemplate.setReceiveTimeout(2_000L);

Object value = jmsTemplate.receiveAndConvert("demo.messages");
if (value == null) {
    System.out.println("NO_MESSAGE_OR_NULL_BODY");
}
~~~

Nếu queue không có message trong khoảng chờ, `receiveAndConvert` trả `null` theo hợp đồng API. Tuy nhiên, một converter có thể trả `null` khi đã nhận một message có body rỗng hoặc converter tự chọn `null`. Nếu cần phân biệt **không có message** và **message có payload null**, dùng `receive(...)` trước để xét chính JMS Message rồi chuyển đổi thủ công.

Ví dụ dùng API raw:

~~~java
import jakarta.jms.Message;
import org.springframework.jms.support.converter.MessageConverter;

Message raw = jmsTemplate.receive("demo.messages");
if (raw == null) {
    System.out.println("TIMEOUT");
} else {
    MessageConverter converter = jmsTemplate.getMessageConverter();
    if (converter == null) {
        throw new IllegalStateException("Converter not configured");
    }
    Object payload = converter.fromMessage(raw);
    System.out.println(payload == null ? "NULL_BODY" : "GOT_BODY");
}
~~~

Đây là **đoạn trích**, với `jakarta.jms.Message` và converter của Spring JMS; getter/method `fromMessage` có thể phát sinh `JMSException`, nên method bao ngoài phải khai báo/catch ngoại lệ. Dùng raw message còn cho phép lấy `JMSCorrelationID`, `JMSMessageID` và application properties khi cần.

### 5.2. Spring Boot property

Với Spring Boot có JmsTemplate auto-configured:

~~~properties
spring.jms.template.receive-timeout=2s
~~~

Boot chuyển duration này thành cấu hình thời gian chờ của template. **Property này không thay đổi broker retention, consumer acknowledgment hoặc transaction.** Nếu tự định nghĩa `@Bean JmsTemplate`, cần bảo đảm bean ấy nhận đúng cấu hình hoặc set timeout trực tiếp theo Java Config.

### 5.3. Vì sao không nên chờ vô hạn trong HTTP request?

Nếu đặt một lệnh HTTP xử lý bằng thread servlet và gọi `receiveAndConvert()` không timeout, request có thể treo cho đến khi broker có message. Điều đó có thể làm cạn thread pool của server khi nhiều request đến cùng lúc. Với service liên tục tiêu thụ message, Spring `@JmsListener` thường là lựa chọn tự nhiên hơn; với polling có kiểm soát, đặt timeout, giới hạn concurrency và backpressure rõ ràng.

## 6. Object trả về và cách xử lý an toàn

Signature của `receiveAndConvert` trả về `Object`, không phải generic `T` có ép kiểu tự động:

~~~java
Object payload = jmsTemplate.receiveAndConvert("demo.messages");
~~~

**Không nên** viết khi queue có nhiều loại message:

~~~java
// Có thể lỗi ClassCastException nếu message thực là BytesMessage/MapMessage.
String text = (String) jmsTemplate.receiveAndConvert("demo.messages");
~~~

Cách an toàn hơn:

~~~java
Object payload = jmsTemplate.receiveAndConvert("demo.messages");

if (payload == null) {
    System.out.println("TIMEOUT_OR_NULL_PAYLOAD");
} else if (payload instanceof String text) {
    System.out.println("TEXT=" + text);
} else if (payload instanceof byte[] bytes) {
    System.out.println("BINARY_LENGTH=" + bytes.length);
} else if (payload instanceof java.util.Map<?, ?> map) {
    System.out.println("MAP_KEYS=" + map.keySet());
} else if (payload instanceof java.io.Serializable serializable) {
    System.out.println("SERIALIZABLE=" +
            serializable.getClass().getName());
} else {
    System.out.println("UNEXPECTED_TYPE=" +
            payload.getClass().getName());
}
~~~

Đây là một đoạn method với `jmsTemplate` đã được inject. Không so sánh `Map.keySet()` theo một thứ tự cố định; tùy loại Map được converter trả ra. Lưu ý `String`, `byte[]` và đa số Map cũng implements `Serializable`, nên kiểm tra các nhánh cụ thể **trước** nhánh Serializable để không bắt nhầm.

### 6.1. Khi dữ liệu Java còn cần schema

Ngay cả khi runtime type là String hoặc Map, nghiệp vụ vẫn cần xác minh:

- Một `String` có JSON hợp lệ không? Version/schema có tương thích không?
- Một Map có các key bắt buộc không? Value `quantity` có phải Integer, hay String?
- Một byte[] có MIME type, codec và giới hạn kích thước theo hợp đồng không?
- Một ObjectMessage có class compatible, allowlist hợp lệ và nguồn tin cậy không?

Converter chỉ cung cấp **giá trị Java ban đầu**, không bảo đảm toàn bộ semantic validation của dữ liệu nghiệp vụ.

## 7. Ví dụ chạy được: Spring Boot 3.x + Artemis, nhận đồng bộ bốn loại payload

Ví dụ Java 17+ này tạo bốn message bằng `convertAndSend` rồi dùng **chính một ApplicationRunner** gọi `receiveAndConvert` lần lượt để nhận. **Không dùng `@JmsListener` trên cùng queue**, nhằm tránh consumer cạnh tranh làm sai kết quả minh họa.

### 7.1. Chuẩn bị

Tạo dự án Maven từ [Spring Initializr](https://start.spring.io/) với Java 17+, Spring Boot 3.x, group `com.example`, artifact `receive-convert-demo` và dependency **Spring for Apache ActiveMQ Artemis** (`org.springframework.boot:spring-boot-starter-artemis`).

Yêu cầu hạ tầng:

- Apache ActiveMQ Artemis broker chạy ngoài ứng dụng tại `tcp://localhost:61616`.
- Queue `demo.receive.convert` tồn tại hoặc broker được cấu hình auto-create phù hợp.
- Tài khoản có quyền connect/send/consume trên queue.
- Broker/client cho phép deserialize `java.lang.Integer` trong ObjectMessage. Nếu provider/trust policy cấm ObjectMessage, phải chỉnh test scenario một cách an toàn hoặc bỏ riêng trường hợp đó, không mở allowlist rộng tùy tiện.
- Queue trống lúc bắt đầu và không có consumer khác cạnh tranh, để kết quả minh họa ổn định.

Đặt biến môi trường `ARTEMIS_USER` và `ARTEMIS_PASSWORD` theo môi trường broker.

Tệp `src/main/resources/application.properties`:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=${ARTEMIS_USER}
spring.artemis.password=${ARTEMIS_PASSWORD}

spring.jms.pub-sub-domain=false
spring.jms.template.receive-timeout=3s
~~~

Chế độ `native` **không tự khởi động broker**. Timeout 3 giây giới hạn thời gian chờ trong ví dụ; không quyết định TTL message.

Tệp `src/main/java/com/example/ReceiveConvertDemoApplication.java`:

~~~java
package com.example;

import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class ReceiveConvertDemoApplication {

    private static final String QUEUE = "demo.receive.convert";

    public static void main(String[] args) {
        SpringApplication.run(ReceiveConvertDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner demo(JmsTemplate template) {
        return args -> {
            // Producer: bốn kiểu Java -> bốn JMS message tương ứng.
            template.convertAndSend(QUEUE, "hello");
            template.convertAndSend(QUEUE, new byte[] {1, 2, 3});

            Map<String, Object> order = new LinkedHashMap<>();
            order.put("orderId", "A42");
            order.put("quantity", 3);
            template.convertAndSend(QUEUE, order);

            template.convertAndSend(QUEUE, Integer.valueOf(42));

            int received = 0;
            for (int i = 0; i < 4; i++) {
                Object value = template.receiveAndConvert(QUEUE);

                if (value == null) {
                    System.out.println("TIMEOUT");
                    break;
                }
                if (value instanceof String text) {
                    System.out.println("STRING=" + text);
                } else if (value instanceof byte[] bytes) {
                    System.out.println(
                            "BYTES=" + Arrays.toString(bytes));
                } else if (value instanceof Map<?, ?> map) {
                    System.out.println("MAP=orderId:"
                            + map.get("orderId") + ",quantity:"
                            + map.get("quantity"));
                } else if (value instanceof Integer number) {
                    System.out.println("OBJECT=" + number);
                } else {
                    throw new IllegalStateException(
                            "Unexpected Java type: "
                                    + value.getClass().getName());
                }
                received++;
            }
            System.out.println("RECEIVED=" + received);
        };
    }
}
~~~

Class có một public class duy nhất với tên trùng file. Dùng Java 17 pattern matching `instanceof`, không cần custom converter. Spring Boot với Artemis starter và cấu hình hợp lệ cung cấp `ConnectionFactory` và `JmsTemplate`. Cả gửi và nhận đều được thực hiện qua queue.

### 7.2. Lệnh chạy và stdout kỳ vọng

Tại thư mục gốc dự án Maven:

~~~bash
mvn spring-boot:run
~~~

Nếu dự án có Maven Wrapper trên Windows:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Với queue sạch, không có competing consumer và broker/credentials/deserialization policy phù hợp, sẽ thấy **bốn dòng payload** và **một dòng tổng kết**. Một cách sắp xếp hợp lệ của các dòng:

~~~text
STRING=hello
BYTES=[1, 2, 3]
MAP=orderId:A42,quantity:3
OBJECT=42
RECEIVED=4
~~~

Trong demo, `RECEIVED=4` được in cuối vì vòng lặp hoàn tất trước; **thứ tự các dòng payload không phải hợp đồng để phụ thuộc**, bởi JMS producer/consumer resource, provider và môi trường có thể ảnh hưởng thứ tự nếu có nhiều producer/consumer hoặc cấu hình ưu tiên. Spring còn có startup logs.

Nếu không nhận đủ bốn message trong 3 giây cho từng lần receive, chương trình có thể in `TIMEOUT` và `RECEIVED` nhỏ hơn 4. Nếu queue còn message cũ có schema khác, kết quả khác hoặc xuất hiện lỗi ép kiểu. Nếu Artemis chặn ObjectMessage deserialization, ví dụ có thể thất bại ở message thứ tư và cần kiểm tra cấu hình trust classes.

### 7.3. Vì sao đây là ví dụ nhận đồng bộ?

Trong ví dụ không tồn tại `@JmsListener`; `ApplicationRunner` chủ động gọi `receiveAndConvert(QUEUE)`. Thread chạy Runner chỉ tiếp tục sau khi receive trả về (hoặc timeout/lỗi). Trường hợp này phù hợp để học và làm worker polling ngắn, **khác với một long-running listener container**.

Lưu ý nếu ứng dụng khởi động khi broker không sẵn sàng, việc gửi có thể ném exception trước khi tới receive; không mặc định sẽ chỉ in `TIMEOUT`. Timeout ở đây điều khiển thời gian chờ khi consumer đã hoạt động.

## 8. Dùng custom MessageConverter có làm kiểu nhận thay đổi không?

**Có.** `receiveAndConvert` không có bộ quy tắc cứng “TextMessage luôn String” bất kể cấu hình. Nó gọi `MessageConverter` hiện hành của `JmsTemplate`.

Ví dụ một hệ thống dùng JSON `TextMessage` có thể muốn nhận trực tiếp một DTO thay vì String. Cách xử lý thường gặp:

1. Producer gửi JSON TextMessage có schema rõ.
2. Cấu hình converter JSON, ví dụ `MappingJackson2MessageConverter` (ở Spring Framework 6.x) cùng Jackson dependency.
3. Receiver dùng cùng quy ước type-id hoặc type mapping được cấu hình an toàn.
4. `receiveAndConvert` có thể trả một đối tượng domain như `OrderEvent`, không phải String.

Một cấu hình **minh họa**, không phải project chạy độc lập:

~~~java
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageConverter;
import org.springframework.jms.support.converter.MessageType;

MessageConverter converter() {
    MappingJackson2MessageConverter c =
            new MappingJackson2MessageConverter();
    c.setTargetType(MessageType.TEXT);
    c.setTypeIdPropertyName("_type");
    return c;
}
~~~

Phải **gắn converter vào JmsTemplate**, ví dụ:

~~~java
JmsTemplate template = new JmsTemplate(connectionFactory);
template.setMessageConverter(converter());
template.setReceiveTimeout(2_000L);
~~~

Đây là **hai trích đoạn**, giả định có `ConnectionFactory`, Jackson và method `converter()` phù hợp. Với JSON converter, type metadata, trusted mappings và object type hiện diện ở receiver đều cần được cấu hình đúng. **Không** nhận class name từ nguồn không tin cậy rồi tự deserialize mọi loại mà thiếu kiểm soát.

### 8.1. Một JmsTemplate không nhất thiết dùng converter của listener

`JmsTemplate` và `@JmsListener` có thể được cấu hình converter khác nhau. Listener container/adapter có message conversion path riêng. Việc thấy một DTO ở listener **không chứng minh** `jmsTemplate.receiveAndConvert` trên template khác cũng trả DTO. Luôn kiểm tra `jmsTemplate.getMessageConverter()` và cấu hình container khi so sánh kết quả.

### 8.2. Không dùng converter thì sao?

Một `JmsTemplate` có thể được cấu hình với `MessageConverter` custom, hoặc trong một số cấu hình cấp thấp converter có thể bị vô hiệu hóa. Khi cần **JMS Message gốc**, cách rõ ràng nhất là dùng `receive(...)`; đừng dựa vào `receiveAndConvert(...)` như một API luôn trả JMS Message.

## 9. Nếu muốn giữ header/property cùng payload

Khi code cần cả `JMSCorrelationID`, `JMSReplyTo`, `eventType` và payload, có hai hướng:

**Hướng 1 — Receive raw rồi convert có kiểm soát**

~~~java
import jakarta.jms.Message;
import org.springframework.jms.support.converter.MessageConverter;

Message raw = jmsTemplate.receive("demo.messages");

if (raw == null) {
    System.out.println("NO_MESSAGE");
} else {
    String correlationId = raw.getJMSCorrelationID();
    String eventType = raw.getStringProperty("eventType");

    MessageConverter converter = jmsTemplate.getMessageConverter();
    if (converter == null) {
        throw new IllegalStateException("Missing MessageConverter");
    }
    Object body = converter.fromMessage(raw);
    System.out.println("correlation=" + correlationId);
    System.out.println("eventType=" + eventType);
    System.out.println("bodyType="
            + (body == null ? "null" : body.getClass().getName()));
}
~~~

Đây là **đoạn trích** cần `jakarta.jms.Message`, Spring template và khai báo/xử lý `JMSException` trong method bao ngoài. Nó cho phép tách **header**, **properties** và **body** thay vì đánh đồng tất cả với một object.

**Hướng 2 — Thiết kế contract body**

Nếu consumer chỉ cần các trường nghiệp vụ, encode chúng vào một DTO/JSON có schema thay vì làm ứng dụng dựa vào metadata JMS. Tuy nhiên, với request/reply, correlation và routing, headers vẫn có vai trò riêng; đừng sao chép bí mật hoặc metadata nhạy cảm vào body vô lý.

## 10. Queue, competing consumers và lý do một lần receive lấy một message

`receiveAndConvert` **không** đọc toàn bộ queue, không có tính chất broadcast và không trả list các message.

- Một lời gọi thường lấy **tối đa một** message từ destination.
- Gọi nhiều lần để polling nhiều message, với timeout, shutdown signal và giới hạn số vòng.
- Nhiều consumers của cùng một queue **cạnh tranh** nhận message; một message không được phát cho cả caller `receiveAndConvert` lẫn `@JmsListener` của cùng queue như một bản sao tự động.
- Nếu destination là Topic, việc subscriber có nhận được message phụ thuộc subscription lifecycle, durable/shared subscription và thời điểm consumer được tạo; không dùng ví dụ queue để suy luận topic có lưu backlog giống queue.
- Với receive đồng bộ theo đợt, cần quản lý connection/session caching, concurrency và tốc độ để tránh tạo quá nhiều tài nguyên.

Ví dụ sai về kỳ vọng:

~~~java
jmsTemplate.convertAndSend("orders.queue", "order-42");

// Có một @JmsListener cũng nghe orders.queue.
// Không thể mong cả hai cùng nhận chắc chắn một message.
Object value = jmsTemplate.receiveAndConvert("orders.queue");
~~~

Một trong các consumer có thể lấy message trước. Khi `receiveAndConvert` trả `null` dù producer đã gửi, hãy kiểm tra **competing consumers** và queue depth trước khi kết luận converter không hỗ trợ kiểu dữ liệu.

## 11. Acknowledgment, transaction và lỗi chuyển đổi

Cần phân biệt ba sự kiện:

1. **Broker gửi message tới consumer**.
2. **JmsTemplate nhận message** trong session theo ack/transaction mode.
3. **Converter chuyển body** và ứng dụng xử lý dữ liệu.

Một ứng dụng không nên mặc định rằng ném exception sau `receiveAndConvert` sẽ làm message tự quay lại queue. Tùy session acknowledgment, transaction và ranh giới commit/rollback, message có thể đã được acknowledge hoặc commit. Trên `AUTO_ACKNOWLEDGE`, receipt/ack và conversion/business processing không đồng nghĩa một transaction end-to-end.

- `JmsTemplate` quản lý tài nguyên và xử lý exception JMS theo Spring.
- Converter có thể ném `org.springframework.jms.support.converter.MessageConversionException` hoặc lỗi runtime của custom converter.
- `ObjectMessage` có thể thất bại deserialization do security allowlist, classpath, version hoặc dữ liệu không tin cậy.
- Conversion thành công không bảo đảm logic nghiệp vụ/ghi database thành công.
- Muốn xử lý transactional, cần cấu hình JMS session transaction/transaction manager tương ứng và xác nhận thời điểm commit so với business operation trong test thực tế.
- Với tích hợp database và JMS, một JMS local transaction không tự đem lại atomic commit giữa hai hệ thống; cân nhắc outbox/inbox, JTA/XA hoặc idempotency tùy yêu cầu.

Khi conversion lỗi liên tục, đừng retry vô hạn một poison message. Thiết kế retry/backoff, redelivery limit và dead-letter queue (DLQ) tại consumer/broker theo chính sách cụ thể.

## 12. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `receiveAndConvert` trả `null` | Queue rỗng, timeout, consumer khác đã lấy hoặc body/converter trả null | Kiểm tra queue depth, timeout, cạnh tranh consumer, dùng raw receive để phân biệt |
| Thread treo trong receive | `receiveTimeout=0` (chờ vô hạn) | Đặt timeout dương hoặc negative no-wait theo mục đích |
| `ClassCastException` khi cast String | Message thực là BytesMessage, MapMessage, ObjectMessage | Dùng `instanceof`, log runtime type, xác định producer contract |
| Nhận String JSON thay vì DTO | SimpleMessageConverter chỉ convert TextMessage → String | Parse JSON hoặc cấu hình converter JSON và type metadata |
| Nhận `byte[]` thay vì text | Producer gửi BytesMessage | Giải mã codec/UTF-8 rõ ràng hoặc đổi sender contract |
| Map có thứ tự khác, hoặc cast LinkedHashMap lỗi | Converter trả Map nhưng không hứa implementation/thứ tự | Chỉ truy cập theo interface Map và key |
| ObjectMessage deserialization thất bại | Class khác phiên bản, không có class, security allowlist | Đồng bộ class/schema và policy, tránh broad trusted packages |
| Nhận raw `jakarta.jms.Message` từ `receiveAndConvert` | JMS Message type không được SimpleMessageConverter xử lý đặc biệt | Kiểm tra loại message thực (ví dụ StreamMessage) hoặc dùng converter tương ứng |
| Không thấy `JMSCorrelationID` trong object nhận | Converter trả body, không mang headers | Dùng `receive` và đọc headers trước khi convert |
| `receiveAndConvert()` không đối số báo thiếu default | Chưa cấu hình default destination | Đặt `defaultDestinationName` hoặc truyền tên đích |
| Nhận message không đúng loại khi queue có nhiều loại | Producer gửi nhiều schema cùng destination | Tách queue/schema, dùng selector/properties hoặc kiểm tra runtime |
| Cùng queue có listener và polling | Competing consumers | Không test hai đường trên một queue nếu muốn cả hai cùng thấy message |
| Consumer báo conversion error sau broker nhận | Message hợp lệ về giao hàng nhưng payload không tương thích | Điều tra converter, classpath, message schema, DLQ/retry |
| Lỗi kết nối/ACL/destination | Broker chưa chạy, sai URL, credentials, queue chưa provision | Kiểm tra Artemis health, log, quyền, endpoint |

### 12.1. Quy trình chẩn đoán nhanh

~~~text
JmsTemplate đang inject loại nào?
   |
   v
receiveTimeout + destination đúng chưa?
   |
   v
Broker có message? Có consumer cạnh tranh không?
   |
   v
Nhận JMS Message type nào? (Text/Bytes/Map/Object/Stream...)
   |
   v
Template dùng MessageConverter nào?
   |
   v
Result runtime type? Null do timeout/body/converter?
   |
   v
Lỗi schema/deserialization/cast hay lỗi business?
~~~

Khi cần quan sát chi tiết, log destination, class JMS message, class Java payload và business/correlation ID, tránh log thẳng dữ liệu cá nhân, token và serialized object không tin cậy.

## 13. Những ngộ nhận cần tránh

1. **“receiveAndConvert luôn trả String.”** Sai: nó trả Object có runtime type phụ thuộc JMS Message và converter.
2. **“TextMessage JSON được chuyển ngay thành Map.”** Sai với SimpleMessageConverter: kết quả là String.
3. **“BytesMessage tự được giải mã UTF-8.”** Không: kết quả là `byte[]`.
4. **“MapMessage chắc chắn thành LinkedHashMap.”** Không: chỉ nên dựa trên contract `Map`.
5. **“ObjectMessage luôn deserialize được.”** Không: cần class tương thích và trust policy.
6. **“Không nhận được message chắc converter lỗi.”** Không: có thể queue rỗng, timeout hoặc competing consumer.
7. **“receiveAndConvert(-) là API không chặn.”** Không: mặc định có thể chờ vô hạn, trừ khi cấu hình timeout thích hợp.
8. **“null luôn nghĩa là timeout.”** Không tuyệt đối: custom converter hoặc body null có thể trả null.
9. **“Ném exception sau khi nhận thì broker luôn redeliver.”** Không: tùy ack/transaction và điểm commit.
10. **“MapMessage body field được JMS selector đọc được.”** Không: selector đọc properties và một số header, không đọc body.
11. **“Converter thay đổi loại destination.”** Không: đích nhận do template/resolver và broker quyết định.
12. **“@JmsListener với receiveAndConvert cùng queue sẽ cùng nhận một message.”** Không: queue consumers cạnh tranh.
13. **“Kiểu trả về khai báo Object nghĩa là không biết gì về payload.”** Thực tế có thể kiểm tra `instanceof` và định nghĩa contract theo schema rõ ràng.
14. **“Mọi Message type lạ đều ném conversion exception.”** Không với SimpleMessageConverter 6.x: có fallback trả raw JMS Message.

## 14. Tự kiểm tra

**Câu 1.** Một `TextMessage` có body `"42"` được nhận bởi `receiveAndConvert` mặc định. Java type là gì?

**Đáp án:** `String`, không phải `Integer`. SimpleMessageConverter lấy text, không tự parse số.

**Câu 2.** Producer gửi `byte[] {1, 2, 3}` qua `convertAndSend`, consumer nhận gì?

**Đáp án:** `byte[]` nếu message thực là BytesMessage và converter mặc định được dùng.

**Câu 3.** Một `MapMessage` có field `quantity=3`. Consumer nhận kiểu gì? Có chắc là LinkedHashMap không?

**Đáp án:** Nhận đối tượng `Map`. Không cam kết implementation cụ thể hoặc iteration order.

**Câu 4.** `receiveAndConvert()` (không đối số) dùng queue nào?

**Đáp án:** Default destination đã đặt trên JmsTemplate đó; thiếu default sẽ báo lỗi cấu hình.

**Câu 5.** `setReceiveTimeout(0)` là không chờ hay chờ vô hạn?

**Đáp án:** Chờ vô hạn theo quy tắc của JmsTemplate. Số âm mới có ý nghĩa no-wait.

**Câu 6.** Nếu cần `JMSCorrelationID` và body, nên chọn cách nào?

**Đáp án:** Dùng `receive(...)` để lấy raw Message, đọc header rồi dùng `MessageConverter.fromMessage(raw)` hoặc tự trích body theo type.

**Câu 7.** Khi receiver thấy String JSON nhưng cần DTO, có phải message hỏng không?

**Đáp án:** Không. SimpleMessageConverter chỉ trả String; cần cấu hình JSON converter hoặc parse chủ động.

**Câu 8.** Hai consumer cùng queue: một @JmsListener và một receiveAndConvert. Có chắc cùng nhận một message không?

**Đáp án:** Không. Queue dùng competing consumers; một message không tự broadcast đến cả hai.

**Câu 9.** `SimpleMessageConverter.fromMessage` làm gì khi nhận một JMS message type không nằm trong bốn loại thông dụng?

**Đáp án:** Theo Javadoc Spring Framework 6.x, nó trả về chính plain JMS Message đó (fallback). Custom converter có thể khác.

**Câu 10.** `receiveAndConvert` có bảo đảm database transaction của ứng dụng atomic với JMS receive không?

**Đáp án:** Không. Cần thiết kế transaction/ack/redo/compensation đúng bối cảnh, kiểm thử tính nhất quán và idempotency.

## Nguồn tham khảo chính thức

- [Spring Framework Reference — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html): synchronous receive, blocking và timeout, so sánh với asynchronous listeners.
- [Spring Framework Reference — Using JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): JmsTemplate, receive timeout, message converter và cấu hình destination.
- [Spring Framework Javadoc 6.2 — JmsTemplate](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html): `receiveAndConvert`, `receiveSelectedAndConvert`, `getMessageConverter` và `setReceiveTimeout`.
- [Spring Framework Javadoc 6.2 — SimpleMessageConverter](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/jms/support/converter/SimpleMessageConverter.html): mapping Text/Bytes/Map/Object và fallback khi JMS type không được nhận diện.
- [Spring Framework Javadoc 6.2 — MessageConverter](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/support/converter/MessageConverter.html): hợp đồng `toMessage`/`fromMessage`.
- [Spring Boot Reference — JMS/Artemis](https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html): starter Artemis, native broker, auto-configured ConnectionFactory/JmsTemplate.
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): các JMS Message types, consumer, session acknowledgment và selector.
