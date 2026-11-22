# MessageConverter và hai chiều chuyển đổi payload

## Mục tiêu

Trong Spring Messaging, `MessageConverter` chuyển payload giữa đối tượng Java mà ứng dụng làm việc và dạng biểu diễn phù hợp cho message. Chiều gửi chuyển object thành payload đã serialize; chiều nhận đọc payload đã serialize thành kiểu Java mà handler yêu cầu.

Sau bài này, bạn có thể:

- Phân biệt `toMessage` và `fromMessage`.
- Hiểu vai trò của `MessageHeaders.CONTENT_TYPE` và MIME type.
- Chọn converter phù hợp cho String, byte array, JSON hoặc chuyển đổi kiểu cơ bản.
- Biết khi nào converter trả về `null`, khi nào ném `MessageConversionException`.
- Dùng `CompositeMessageConverter` và `SmartMessageConverter`.
- Phân biệt Spring Messaging converter với converter của HTTP, JMS và AMQP.
- Kiểm thử cả hai chiều chuyển đổi trước khi kết nối với broker.

## 1. MessageConverter giải quyết vấn đề gì?

Một thành phần nghiệp vụ thường làm việc với object có kiểu:

~~~java
OrderCreated event = new OrderCreated("ORD-42", 250000);
~~~

Nhưng khi message đi qua một ranh giới giao tiếp, payload thường cần một dạng biểu diễn có thể truyền được, ví dụ:

- `byte[]` chứa JSON hoặc dữ liệu nhị phân.
- `String` chứa văn bản hoặc JSON.
- Một message protobuf đã được encode.
- Một dạng XML hoặc định dạng khác mà hai đầu cùng hiểu.

Ở phía nhận, ứng dụng cần biến payload đó trở lại thành object phù hợp với handler.

Nếu tự viết việc serialize/deserialize ở mọi producer và consumer, mã nghiệp vụ sẽ bị gắn chặt với định dạng vận chuyển. `MessageConverter` gom trách nhiệm chuyển đổi vào một abstraction có thể thay thế hoặc cấu hình.

Spring Messaging định nghĩa interface:

~~~java
public interface MessageConverter {

    Object fromMessage(Message<?> message, Class<?> targetClass);

    Message<?> toMessage(Object payload, MessageHeaders headers);
}
~~~

Hai phương thức là hai chiều của cùng một hợp đồng:

| Phương thức | Hướng | Đầu vào | Kết quả |
|---|---|---|---|
| `toMessage(payload, headers)` | Outbound | Object Java và metadata tùy chọn | Message mới có payload đã chuyển sang dạng biểu diễn |
| `fromMessage(message, targetClass)` | Inbound | Message nhận được và kiểu Java đích | Object có kiểu mà ứng dụng cần |

`MessageConverter` chỉ chuyển đổi payload và tạo/đọc message. Nó không tự mở kết nối mạng, gửi message đến broker, lưu dữ liệu bền vững, mã hóa TLS hoặc bảo đảm giao nhận.

## 2. Hai chiều chuyển đổi

### Outbound: object Java thành payload có thể truyền

~~~mermaid
flowchart LR
    A["Object Java"] --> B["MessageConverter.toMessage"]
    B --> C["Message<byte[]> hoặc Message<String>"]
    C --> D["Adapter / transport"]
    D --> E["Broker hoặc hệ thống nhận"]
~~~

Ví dụ, producer có một object `OrderCreated`. Converter có thể serialize object thành JSON UTF-8 trong `byte[]`, đồng thời đặt `contentType=application/json` vào headers.

Kết quả vẫn là một Spring `Message<?>`; chỉ payload được chuyển đổi. Các header nghiệp vụ có thể được truyền vào phương thức `toMessage` để giữ lại trong message mới.

### Inbound: payload đã truyền thành object Java

~~~mermaid
flowchart LR
    A["Broker / transport"] --> B["Adapter tạo Spring Message"]
    B --> C["MessageConverter.fromMessage"]
    C --> D["Object Java theo targetClass"]
    D --> E["MessageHandler / method"]
~~~

Ở phía nhận, adapter tạo message từ dữ liệu protocol. Converter đọc payload cùng content type rồi tạo object theo kiểu đích.

Ví dụ, message có payload là JSON bytes và `contentType=application/json`; consumer yêu cầu `OrderCreated.class`, nên converter parse JSON thành object `OrderCreated`.

Hai chiều cần thống nhất về định dạng, charset, schema và phiên bản dữ liệu. Producer tạo JSON nhưng consumer lại xử lý payload như văn bản thuần sẽ gây lỗi dù cả hai đều dùng cùng một broker.

## 3. Vai trò của contentType và MIME type

`MessageHeaders.CONTENT_TYPE` cho biết định dạng payload. Giá trị thường là một `MimeType` hoặc chuỗi MIME type có thể phân tích được.

Ví dụ:

| Content type | Ý nghĩa thường gặp | Converter phù hợp |
|---|---|---|
| `text/plain` | Văn bản thuần | `StringMessageConverter` |
| `application/json` | JSON | `JacksonJsonMessageConverter` hoặc converter JSON tương ứng |
| `application/octet-stream` | Dữ liệu nhị phân tổng quát | `ByteArrayMessageConverter` |
| `application/xml` | XML | Converter XML được cấu hình |
| `application/x-protobuf` | Dữ liệu Protocol Buffers | `ProtobufMessageConverter` với MIME type tương ứng |

Có thể đặt content type bằng `MessageBuilder`:

~~~java
Message<String> message = MessageBuilder
        .withPayload("{\"orderId\":\"ORD-42\"}")
        .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
        .build();
~~~

Hoặc truyền header vào `toMessage`:

~~~java
MessageHeaders headers = new MessageHeaders(
        Map.of(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
);

Message<?> encoded = converter.toMessage(orderCreated, headers);
~~~

Content type là hợp đồng về định dạng, không phải phép biến đổi. Chỉ đặt `application/json` không tự biến object Java thành JSON; converter thực hiện việc serialize.

### Khi content type thiếu hoặc không khớp

Các converter kế thừa `AbstractMessageConverter` có danh sách MIME type hỗ trợ và một `ContentTypeResolver`. Mặc định resolver đọc `MessageHeaders.CONTENT_TYPE`. Converter cũng có thể chọn content type mặc định từ MIME type hỗ trợ đầu tiên khi tạo message mà chưa có content type.

`strictContentTypeMatch` mặc định là `false`. Nếu bật `setStrictContentTypeMatch(true)`, converter yêu cầu resolver tìm được content type khớp với MIME type được hỗ trợ; message không có content type có thể bị bỏ qua bởi converter đó.

Nếu producer khai báo `application/json` nhưng payload thực tế là văn bản không phải JSON, consumer có thể ném lỗi parse. Nếu khai báo sai charset, dữ liệu có dấu hoặc ký tự ngoài ASCII có thể bị đọc sai. Hãy đặt content type và charset theo đúng bytes thực tế.

## 4. Các converter thường gặp trong Spring Messaging

Các lớp dưới đây thuộc package `org.springframework.messaging.converter`. Chúng không có cùng trách nhiệm:

| Converter | Vai trò |
|---|---|
| `SimpleMessageConverter` | Bọc payload thành message và mở payload nếu đã đúng target class. Không thực hiện serialize/deserialize thực sự và bỏ qua content type. |
| `GenericMessageConverter` | Mở rộng `SimpleMessageConverter`; dùng Spring `ConversionService` để chuyển payload hiện có sang kiểu đích. |
| `StringMessageConverter` | Chuyển payload String và dạng biểu diễn văn bản; hỗ trợ MIME type `text/plain`. |
| `ByteArrayMessageConverter` | Làm việc với payload `byte[]`; hỗ trợ `application/octet-stream`. |
| `JacksonJsonMessageConverter` | Chuyển object Java và JSON bằng Jackson 3.x; có trong Spring Framework 7.0 trở lên. |
| `MappingJackson2MessageConverter` | Converter JSON dựa trên Jackson 2. Trong Spring Framework 7.0, API này đã deprecated để chuyển sang `JacksonJsonMessageConverter`. |
| `MarshallingMessageConverter` | Chuyển đổi XML thông qua Spring OXM `Marshaller` và `Unmarshaller`. |
| `ProtobufMessageConverter` | Chuyển đổi các message Protocol Buffers. |
| `CompositeMessageConverter` | Thử nhiều converter theo thứ tự cho đến khi một converter trả kết quả khác `null`. |

### SimpleMessageConverter và GenericMessageConverter

Đây là hai tên dễ gây hiểu nhầm.

`SimpleMessageConverter` của Spring Messaging chỉ unwrap payload khi payload đã tương thích với target class; chiều gửi chỉ wrap object vào message. Nó bỏ qua content type và không phải JSON converter hay byte serializer.

`GenericMessageConverter` sử dụng `ConversionService` để chuyển đổi kiểu object ở chiều nhận. Ví dụ, nó có thể chuyển một payload String `"42"` thành `Integer` nếu ConversionService có converter phù hợp. Chiều `toMessage` được kế thừa từ `SimpleMessageConverter`, nên nó vẫn chỉ bọc payload thay vì serialize thành bytes.

Nếu cần biến object thành JSON bytes, hãy chọn converter JSON thực sự.

### StringMessageConverter và ByteArrayMessageConverter

`StringMessageConverter` xử lý String và hỗ trợ `text/plain`. Charset cần được thống nhất giữa hai đầu; có thể truyền charset vào constructor.

`ByteArrayMessageConverter` xử lý payload `byte[]` và `application/octet-stream`. Nó phù hợp khi dữ liệu đã được encode ở nơi khác hoặc khi ứng dụng muốn giữ nguyên bytes.

Hai converter này không tự hiểu cấu trúc nghiệp vụ trong payload. Chúng xử lý biểu diễn văn bản hoặc bytes.

### JacksonJsonMessageConverter

Trong Spring Framework 7, `JacksonJsonMessageConverter` là converter JSON dựa trên Jackson 3.x. Constructor mặc định tạo `JsonMapper` và tìm các Jackson module trên classpath. Có thể truyền một `JsonMapper` tùy chỉnh hoặc danh sách MIME type được hỗ trợ.

Ví dụ:

~~~java
JacksonJsonMessageConverter converter = new JacksonJsonMessageConverter();

Message<?> outbound = converter.toMessage(orderCreated, null);

OrderCreated inbound = (OrderCreated) converter.fromMessage(
        outbound,
        OrderCreated.class
);
~~~

Đoạn trên minh họa API; project cần có Jackson 3 và kiểu `OrderCreated` phù hợp để chạy. Trong Spring Framework 7, `MappingJackson2MessageConverter` bị deprecated từ 7.0 và được thay thế bởi `JacksonJsonMessageConverter`. Với ứng dụng trên Framework 6.x vẫn dùng Jackson 2, hãy dùng converter tương ứng với release line đang chạy và kiểm tra Javadoc của phiên bản đó.

## 5. MessageConverter trả về null hay ném exception?

Theo hợp đồng của interface:

- `fromMessage` trả về object nếu có thể chuyển payload sang target class.
- `toMessage` trả về message mới nếu có thể chuyển payload.
- Nếu converter không hỗ trợ media type hoặc không thể thực hiện phép chuyển đổi theo hợp đồng, nó có thể trả về `null`.

`null` thường có nghĩa là converter này không nhận xử lý payload/định dạng đó. Điều này hữu ích khi có nhiều converter trong một composite.

Nếu converter đã nhận xử lý nhưng payload bị hỏng, JSON không hợp lệ, charset không đọc được hoặc quá trình parse gặp lỗi, implementation có thể ném `MessageConversionException`. Đây là một `MessagingException` dùng để biểu diễn lỗi chuyển đổi.

Cần phân biệt:

| Tình huống | Kết quả thường gặp |
|---|---|
| Converter không hỗ trợ MIME type | Trả về `null` |
| Payload không thuộc kiểu converter hỗ trợ | Trả về `null` |
| JSON malformed hoặc dữ liệu không thể parse | Ném `MessageConversionException` |
| Không có converter nào trong composite nhận xử lý | Composite trả về `null`; tầng gọi quyết định cách báo lỗi |
| Chuyển đổi thành công | Trả object hoặc message mới |

Không nên dùng `null` để biểu thị dữ liệu nghiệp vụ rỗng nếu điều đó có thể bị hiểu thành “converter không hỗ trợ”. Hãy phân biệt payload hợp lệ có giá trị null với việc converter từ chối xử lý.

## 6. AbstractMessageConverter: nền tảng để xây converter

Nhiều converter của Spring kế thừa `AbstractMessageConverter`. Lớp này cung cấp logic chung:

- Danh sách MIME type được hỗ trợ.
- Kiểm tra payload class và content type.
- Phân giải MIME type qua `ContentTypeResolver`.
- Hỗ trợ chuyển đổi hai chiều và conversion hint.
- Cấu hình kiểu payload serialized ưu tiên là `byte[]` hoặc `String`.
- Tùy chọn strict content type matching.

Các extension point quan trọng:

| API | Mục đích |
|---|---|
| `supports(Class<?> clazz)` | Xác định class payload mà converter hỗ trợ. |
| `convertToInternal(payload, headers, hint)` | Chuyển object Java sang dạng payload đã serialize. |
| `convertFromInternal(message, targetClass, hint)` | Đọc payload đã serialize thành object đích. |
| `getDefaultContentType(payload)` | Chọn content type mặc định khi outbound message chưa có content type. |
| `setSerializedPayloadClass(byte[].class)` | Chọn bytes làm dạng payload serialized. |
| `setSerializedPayloadClass(String.class)` | Chọn String làm dạng payload serialized. |
| `setStrictContentTypeMatch(true)` | Yêu cầu content type khớp MIME type được hỗ trợ. |

Trong `AbstractMessageConverter`, kiểu payload serialized mặc định là `byte[]`. Converter con có thể thay đổi nếu cần.

Khi viết custom converter, nên khai báo MIME type cụ thể và chỉ nhận payload class mà converter thật sự hiểu. Không nên đăng ký `*/*` một cách tùy tiện vì converter có thể nhận nhầm message của converter khác.

## 7. SmartMessageConverter và conversion hint

`SmartMessageConverter` mở rộng `MessageConverter` bằng hai overload có thêm `conversionHint`:

~~~java
Object fromMessage(
        Message<?> message,
        Class<?> targetClass,
        Object conversionHint
);

Message<?> toMessage(
        Object payload,
        MessageHeaders headers,
        Object conversionHint
);
~~~

Conversion hint là thông tin bổ sung cho quá trình chuyển đổi. Một ví dụ là `MethodParameter` của tham số hoặc giá trị trả về trong một handler method. Converter có thể dùng hint để đọc annotation hoặc thông tin generic mà chỉ `Class<?>` không mô tả đầy đủ.

Ví dụ về mục đích sử dụng:

- Một handler nhận kiểu collection có generic element type.
- Một method parameter có annotation chỉ định serialization view.
- Một return value có metadata bổ sung ảnh hưởng cách serialize.

Không phải converter nào cũng cần hint. Nếu converter không triển khai `SmartMessageConverter`, framework chỉ có thể gọi hợp đồng cơ bản.

## 8. CompositeMessageConverter và thứ tự lựa chọn

`CompositeMessageConverter` chứa một danh sách converter. Khi nhận message hoặc tạo message, nó gọi lần lượt các converter cho đến khi một converter trả kết quả khác `null`.

~~~java
List<MessageConverter> converters = List.of(
        new StringMessageConverter(StandardCharsets.UTF_8),
        new ByteArrayMessageConverter(),
        new JacksonJsonMessageConverter()
);

CompositeMessageConverter composite =
        new CompositeMessageConverter(converters);
~~~

Thứ tự quan trọng:

1. Converter đầu tiên được thử trước.
2. Nếu converter trả về `null`, composite thử converter tiếp theo.
3. Converter đầu tiên trả kết quả sẽ kết thúc quá trình tìm kiếm.
4. Nếu tất cả đều trả `null`, composite không thể chuyển đổi message đó.

Khi cấu hình custom converter, đặt converter chuyên biệt trước converter tổng quát nếu cả hai có thể nhận cùng một loại payload. Nếu converter quá rộng đứng trước, nó có thể xử lý message trước khi converter phù hợp hơn được thử.

Composite không tự sửa content type sai hoặc biến một payload malformed thành hợp lệ. Nó chỉ điều phối việc thử các converter.

## 9. Phân biệt các loại MessageConverter trong hệ sinh thái Spring

Tên `MessageConverter` xuất hiện ở nhiều module nhưng các interface không giống nhau.

| Loại | Package | Phạm vi |
|---|---|---|
| Spring Messaging | `org.springframework.messaging.converter` | Chuyển payload của Spring `Message` giữa object và dạng biểu diễn. |
| Spring AMQP | `org.springframework.amqp.support.converter` | Chuyển object/Spring message với AMQP message và message properties. |
| Spring JMS | `org.springframework.jms.support.converter` | Chuyển object/Spring message với `jakarta.jms.Message` hoặc JMS message tương ứng. |
| Spring MVC / HTTP | `org.springframework.http.converter` | Đọc và ghi HTTP request/response body qua `HttpMessageConverter`. |

Các interface có tên gần giống nhau vì đều giải quyết bài toán chuyển đổi, nhưng chúng thuộc các ranh giới protocol khác nhau. Đừng truyền một converter từ package Spring Messaging vào API yêu cầu converter của Spring AMQP hoặc JMS nếu không có adapter tương thích.

Với Kafka, Spring Kafka có serializer/deserializer và record/message converter riêng. Việc chọn serializer của Kafka không đồng nghĩa đã cấu hình `org.springframework.messaging.converter.MessageConverter`.

## 10. Converter được dùng ở đâu trong messaging flow?

### Spring WebSocket và STOMP

Spring WebSocket sử dụng các converter để chuyển payload của message STOMP giữa dữ liệu nhận/gửi và object Java. Ví dụ, một client gửi JSON đến destination, method handler nhận object đã được chuyển đổi. Khi server gửi object tới `/topic/orders`, converter tạo payload văn bản hoặc bytes phù hợp với cấu hình broker.

~~~java
messagingTemplate.convertAndSend("/topic/orders", orderCreated);
~~~

Phương thức này sử dụng converter được cấu hình trong messaging broker của ứng dụng. Nếu cần thay đổi JSON mapping hoặc thêm định dạng mới, cấu hình danh sách converter của broker.

### Spring Integration

Các endpoint có thể dùng converter để chuyển inbound message payload thành kiểu tham số của handler method dựa trên content type. Spring Integration cũng có thể sử dụng `ConversionService` cho chuyển đổi kiểu Java đơn giản. Đây là hai cơ chế có liên quan nhưng không đồng nhất.

### JMS, AMQP và Kafka

Các adapter của JMS, AMQP hoặc Kafka thường có lớp chuyển đổi riêng giữa Spring message và message/record của protocol. Trong một flow có thể có nhiều bước:

1. Converter của Spring Messaging chuyển object thành payload bytes.
2. Adapter map headers sang properties của protocol.
3. Client gửi message qua protocol.
4. Adapter ở phía nhận tạo Spring message.
5. Converter inbound chuyển bytes thành object cho handler.

Không mặc định mọi bước đều dùng cùng một converter. Hãy kiểm tra đúng module và API đang cấu hình.

## 11. Ví dụ Java 17+ chạy được: String sang bytes và trở lại String

Ví dụ này dùng `StringMessageConverter` để thể hiện hai chiều chuyển đổi. Chiều gửi chuyển String thành payload `byte[]`; chiều nhận đọc bytes trở lại String. Chương trình không cần broker hoặc Jackson.

Cấu trúc project:

~~~text
message-converter-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          MessageConversionDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>message-converter-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring-framework.version>7.0.10</spring-framework.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>${spring-framework.version}</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### MessageConversionDemo.java

~~~java
package demo;

import java.nio.charset.StandardCharsets;
import java.util.Objects;

import org.springframework.messaging.Message;
import org.springframework.messaging.converter.StringMessageConverter;

public class MessageConversionDemo {

    public static void main(String[] args) {
        StringMessageConverter converter =
                new StringMessageConverter(StandardCharsets.UTF_8);

        // Chọn byte[] làm dạng payload được serialize.
        converter.setSerializedPayloadClass(byte[].class);

        // Outbound: String Java -> Message có payload byte[].
        Message<?> outbound = Objects.requireNonNull(
                converter.toMessage("hello-spring", null)
        );

        byte[] wirePayload = (byte[]) outbound.getPayload();

        System.out.println("wirePayloadType="
                + wirePayload.getClass().getSimpleName());
        System.out.println("wirePayload="
                + new String(wirePayload, StandardCharsets.UTF_8));

        // Inbound: payload byte[] -> String Java.
        String inbound = (String) Objects.requireNonNull(
                converter.fromMessage(outbound, String.class)
        );

        System.out.println("decoded=" + inbound);
    }
}
~~~

Chạy từ thư mục project bằng Java 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.MessageConversionDemo
~~~

Kết quả stdout:

~~~text
wirePayloadType=byte[]
wirePayload=hello-spring
decoded=hello-spring
~~~

Cách đọc ví dụ:

1. Tạo `StringMessageConverter` với charset UTF-8.
2. Cấu hình payload serialized là `byte[]`.
3. Gọi `toMessage`: converter tạo message có payload là bytes.
4. Đọc bytes để thấy nội dung thực tế mà transport có thể truyền.
5. Gọi `fromMessage` với target class `String.class`: converter giải mã bytes thành String.
6. Giá trị nhận được giống giá trị ban đầu vì cùng converter, charset và định dạng được dùng ở cả hai chiều.

Trong ứng dụng thực tế, message outbound sẽ được adapter gửi đi. Consumer nhận message mới từ transport rồi gọi `fromMessage`; ví dụ dùng lại cùng object message chỉ để kiểm tra tính đảo chiều của converter.

## 12. Ví dụ JSON với JacksonJsonMessageConverter

Khi payload là object nghiệp vụ, JSON converter có thể serialize object thành JSON bytes và deserialize JSON thành kiểu Java.

~~~java
JacksonJsonMessageConverter converter = new JacksonJsonMessageConverter();

Message<?> outbound = converter.toMessage(orderCreated, null);

OrderCreated restored = (OrderCreated) converter.fromMessage(
        outbound,
        OrderCreated.class
);
~~~

Ví dụ này yêu cầu Jackson 3 có trên classpath và kiểu `OrderCreated` có thể được Jackson ánh xạ. Trong Spring Framework 7, converter JSON được khuyến nghị là `JacksonJsonMessageConverter`. Nếu cần cấu hình naming strategy, date/time module hoặc custom serializer, hãy tạo `JsonMapper` phù hợp rồi truyền vào constructor.

Đối với hệ thống phân tán, nên xem JSON là hợp đồng dữ liệu giữa các service. Dùng field có ý nghĩa ổn định, kiểm soát thay đổi schema và tránh phụ thuộc vào tên class Java của producer. Consumer nên xử lý field mới/thiếu theo chính sách tương thích đã thống nhất.

## 13. Lỗi thường gặp khi chuyển đổi payload

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| `fromMessage` trả về `null` | Converter không hỗ trợ payload class hoặc MIME type. | Xem target class, supported MIME types và content type. |
| `toMessage` trả về `null` | Converter không serialize được payload hoặc không hỗ trợ MIME type đích. | Kiểm tra payload class và headers truyền vào. |
| `MessageConversionException` | Payload malformed, charset sai hoặc serializer/deserializer thất bại. | Kiểm tra raw bytes, charset, content type và nguyên nhân gốc. |
| JSON không parse được | Producer và consumer không thống nhất schema hoặc JSON bytes bị hỏng. | Kiểm tra raw payload và JSON parser error. |
| Consumer nhận `byte[]` thay vì object | Chỉ có byte-array/pass-through converter hoặc converter JSON không được đăng ký. | Kiểm tra composite converter và dependency Jackson. |
| Object được wrap nguyên trạng | Đang dùng `SimpleMessageConverter` thay vì converter serialize. | Chọn converter theo định dạng thực tế. |
| Chuyển String sang số thất bại | ConversionService không có converter phù hợp hoặc target type sai. | Kiểm tra `GenericMessageConverter` và ConversionService. |
| Ký tự tiếng Việt bị lỗi | Charset outbound và inbound khác nhau hoặc content type thiếu charset. | Dùng UTF-8 thống nhất và khai báo content type chính xác. |
| Converter JSON không được tạo | Jackson 3 chưa có trong classpath hoặc đang dùng nhầm version/module. | Kiểm tra dependency graph và classpath. |
| Converter không được gọi | Adapter/handler đang sử dụng converter khác hoặc bypass bước conversion. | Kiểm tra module cụ thể, cấu hình endpoint và method argument resolver. |

## 14. Bảo mật và tính tương thích của payload

Chuyển đổi payload là một ranh giới tin cậy. Payload có thể đến từ service, client hoặc broker bên ngoài. Một số nguyên tắc:

- Giới hạn kích thước payload trước khi parse để tránh tiêu thụ bộ nhớ quá mức.
- Xác thực dữ liệu sau khi deserialize; deserialize thành object không đồng nghĩa dữ liệu hợp lệ về nghiệp vụ.
- Tránh Java native serialization cho message liên service vì nó gắn chặt producer/consumer với class Java và làm tăng rủi ro khi nhận dữ liệu không đáng tin.
- Không bật Jackson polymorphic default typing một cách tùy tiện. Không cho dữ liệu bên ngoài tự quyết định class cần khởi tạo.
- Kiểm soát các type header hoặc class name nếu converter sử dụng chúng để chọn kiểu đích.
- Không đưa secret hoặc token vào payload/header nếu không cần; áp dụng mã hóa và chính sách log phù hợp.
- Thiết kế schema có versioning, quy tắc thêm field và quy tắc xử lý field không biết.
- Kiểm thử tương thích giữa phiên bản producer và consumer trong quá trình nâng cấp.

## 15. Checklist chọn và cấu hình converter

- [ ] Xác định payload object ở phía producer.
- [ ] Chọn dạng truyền: text, JSON, bytes, XML hoặc protobuf.
- [ ] Chọn converter đúng MIME type và target payload class.
- [ ] Đặt `MessageHeaders.CONTENT_TYPE` chính xác.
- [ ] Thống nhất charset ở hai đầu.
- [ ] Xác định target class/generic type ở phía nhận.
- [ ] Kiểm tra converter có trả `null` hay ném `MessageConversionException` khi không hỗ trợ/dữ liệu lỗi.
- [ ] Nếu dùng composite, kiểm tra thứ tự converter.
- [ ] Kiểm tra dependency và phiên bản Jackson/serializer.
- [ ] Kiểm thử cả `toMessage` và `fromMessage`.
- [ ] Kiểm thử bằng payload bytes thực tế qua adapter/broker.
- [ ] Xác thực schema và giới hạn kích thước payload.
- [ ] Kiểm tra converter thuộc đúng module: Messaging, HTTP, JMS, AMQP hay Kafka.

## Ghi nhớ

- `toMessage` chuyển object Java thành payload đã serialize; `fromMessage` chuyển payload thành object đích.
- `MessageHeaders.CONTENT_TYPE` cho biết MIME type để chọn cách đọc/ghi payload.
- `null` thường biểu thị converter không hỗ trợ; lỗi parse/serialize có thể ném `MessageConversionException`.
- `SimpleMessageConverter` trong Spring Messaging chỉ wrap/unwrap; `GenericMessageConverter` dùng ConversionService cho chuyển đổi kiểu.
- `StringMessageConverter`, `ByteArrayMessageConverter` và `JacksonJsonMessageConverter` xử lý các dạng payload cụ thể.
- `CompositeMessageConverter` thử các converter theo thứ tự; `SmartMessageConverter` hỗ trợ conversion hint.
- Spring Messaging, HTTP, JMS và AMQP có các interface converter riêng; hãy dùng đúng API của module.
- Converter không gửi message qua mạng. Adapter hoặc transport đảm nhiệm việc truyền dữ liệu sau khi chuyển đổi.

## Tài liệu chính thức

- [Spring Framework Javadoc: MessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/MessageConverter.html)
- [Spring Framework Javadoc: AbstractMessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/AbstractMessageConverter.html)
- [Spring Framework Javadoc: SmartMessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/SmartMessageConverter.html)
- [Spring Framework Javadoc: StringMessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/StringMessageConverter.html)
- [Spring Framework Javadoc: GenericMessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/GenericMessageConverter.html)
- [Spring Framework Javadoc: CompositeMessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/CompositeMessageConverter.html)
- [Spring Framework Javadoc: JacksonJsonMessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/JacksonJsonMessageConverter.html)
- [Spring Framework Javadoc: MappingJackson2MessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/MappingJackson2MessageConverter.html)
- [Spring Framework Reference: HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)
- [Spring AMQP Reference: Message Converters](https://docs.spring.io/spring-amqp/reference/amqp/message-converters.html)
