# Viết bộ chuyển đổi riêng và xác định điều kiện hỗ trợ trong Spring Messaging

Spring Messaging biểu diễn dữ liệu truyền qua channel bằng `Message<?>`, nhưng payload trong ứng dụng có thể là DTO, chuỗi, byte array hoặc một kiểu dữ liệu riêng. Khi cần chuyển đổi giữa đối tượng Java và dạng dữ liệu truyền đi, ta dùng **MessageConverter**.

Một bộ chuyển đổi riêng cần trả lời được hai câu hỏi:

1. **Nó hỗ trợ kiểu Java nào?** Ví dụ chỉ chuyển đổi `OrderCommand`, hay cả `OrderCommand` và `OrderReply`.
2. **Nó hỗ trợ định dạng nội dung nào?** Ví dụ `text/plain`, `application/json` hoặc một MIME type riêng.

Việc xác định đúng điều kiện hỗ trợ giúp Spring chọn converter phù hợp, tránh chuyển đổi nhầm payload hoặc diễn giải sai định dạng message.

## 1. MessageConverter trong Spring Messaging

Interface `org.springframework.messaging.converter.MessageConverter` có hai phương thức:

```java
public interface MessageConverter {

    Message<?> toMessage(Object payload, MessageHeaders headers);

    Object fromMessage(Message<?> message, Class<?> targetClass);
}
```

- `toMessage`: chuyển payload Java thành một `Message<?>`, thường bao gồm payload đã serialize và header `contentType`.
- `fromMessage`: đọc payload của message và chuyển thành kiểu Java mà caller yêu cầu.

Ví dụ, ứng dụng có một DTO:

```java
public record OrderCommand(String orderId, int quantity) {}
```

Khi gửi qua một transport chỉ nhận chuỗi hoặc byte array, converter có thể biến DTO thành chuỗi wire format. Ở phía nhận, converter đọc chuỗi đó và khôi phục thành `OrderCommand`.

`MessageConverter` chỉ định nghĩa hợp đồng chuyển đổi. Nó không tự gửi message qua channel, không tự định tuyến message và không bảo đảm message đã được consumer xử lý.

## 2. Chọn cách triển khai converter

Có hai cách phổ biến:

- **Implement trực tiếp `MessageConverter`:** phù hợp khi cần kiểm soát toàn bộ việc tạo message, kiểm tra headers và chuyển đổi.
- **Kế thừa `AbstractMessageConverter`:** phù hợp với đa số converter tùy chỉnh. Lớp cơ sở quản lý supported MIME types, content type, kiểm tra khả năng chuyển đổi và gọi các hook chuyển đổi.

`AbstractMessageConverter` triển khai `SmartMessageConverter`, nên có thêm khả năng nhận conversion hint. Khi chỉ cần converter thông thường, hãy bắt đầu từ `AbstractMessageConverter` để giảm phần mã lặp.

## 3. Xác định điều kiện hỗ trợ

### Kiểu Java: supports(Class<?>)

Khi kế thừa `AbstractMessageConverter`, cần cài đặt:

```java
@Override
protected boolean supports(Class<?> clazz) {
    return OrderCommand.class == clazz;
}
```

Điều kiện này xác định kiểu Java mà converter có thể xử lý. `supports` được dùng khi chuyển payload thành message và khi chuyển message về kiểu đích.

Có thể hỗ trợ nhiều kiểu:

```java
@Override
protected boolean supports(Class<?> clazz) {
    return OrderCommand.class == clazz
            || OrderReply.class == clazz;
}
```

Nên kiểm tra đúng kiểu hoặc đúng nhóm kiểu được định nghĩa rõ. Nếu trả về `true` cho mọi class, converter có thể nhận một payload mà nó không biết serialize hoặc deserialize, dẫn đến lỗi runtime.

Nếu hỗ trợ kiểu con, cân nhắc `OrderCommand.class.isAssignableFrom(clazz)`. Chỉ dùng điều kiện này khi converter thật sự hiểu cấu trúc của mọi subclass; việc nhận subclass không tự bảo đảm format của chúng tương thích.

### MIME type: supportedMimeTypes

Converter thường hỗ trợ một hoặc nhiều MIME type. `AbstractMessageConverter` nhận danh sách MIME type qua constructor:

```java
super(MimeTypeUtils.TEXT_PLAIN);
```

Hoặc hỗ trợ nhiều định dạng:

```java
super(
        MimeTypeUtils.TEXT_PLAIN,
        MimeTypeUtils.APPLICATION_JSON
);
```

Các MIME type này mô tả định dạng dữ liệu mà converter có thể đọc hoặc tạo. Header `MessageHeaders.CONTENT_TYPE` mang MIME type của payload message.

Ví dụ:

- `text/plain`: chuỗi văn bản.
- `application/json`: JSON.
- `application/octet-stream`: dữ liệu nhị phân.
- `application/vnd.example.order+json`: MIME type riêng cho một schema JSON của ứng dụng.

Không khai báo MIME type rộng hơn định dạng converter thực sự hỗ trợ. Ví dụ converter chỉ serialize chuỗi dạng `orderId|quantity` thì không nên tự nhận là converter JSON.

### strictContentTypeMatch

`AbstractMessageConverter` có cấu hình `setStrictContentTypeMatch(boolean)`.

- Khi strict matching bật, converter chỉ chuyển đổi nếu content type tương thích với MIME type được hỗ trợ. Nếu thiếu content type hoặc MIME type không phù hợp, converter không nhận message đó.
- Khi strict matching tắt (mặc định), converter có thể được xét ngay cả khi content type không khớp hoặc chưa được chỉ định. Đây là hành vi linh hoạt hơn, nhưng cần kiểm tra định dạng thực tế trong converter.

Với giao thức có hợp đồng rõ ràng, bật strict matching giúp từ chối message sai content type sớm:

```java
setStrictContentTypeMatch(true);
```

MIME type tương thích có thể bao gồm tham số như charset. Khi so sánh, Spring dùng quy tắc tương thích MIME type thay vì chỉ so sánh chuỗi thô.

## 4. Hook chuyển đổi của AbstractMessageConverter

Hai hook quan trọng:

```java
protected Object convertToInternal(
        Object payload,
        MessageHeaders headers,
        Object conversionHint);

protected Object convertFromInternal(
        Message<?> message,
        Class<?> targetClass,
        Object conversionHint);
```

- `convertToInternal`: chuyển đối tượng Java thành payload truyền đi, ví dụ DTO thành JSON string hoặc byte array.
- `convertFromInternal`: chuyển payload trong message thành kiểu Java đích.

Lớp cơ sở thực hiện các kiểm tra điều kiện hỗ trợ trước khi gọi hook. Nếu converter không hỗ trợ kiểu Java hoặc MIME type, phương thức chuyển đổi có thể trả về `null` để cho phép converter khác được thử.

Cần phân biệt hai tình huống:

- **Không hỗ trợ:** converter không nhận kiểu Java hoặc content type đó; trả về `null` là tín hiệu không thể chuyển đổi.
- **Dữ liệu sai định dạng:** converter đã nhận message thuộc phạm vi của nó nhưng payload không hợp lệ; nên ném exception chuyển đổi có ý nghĩa, không trả `null` như thể converter không hỗ trợ.

Cách phân biệt này giúp phát hiện dữ liệu hỏng thay vì âm thầm bỏ qua.

## 5. Ví dụ: converter riêng cho OrderCommand

Ví dụ sau dùng wire format dạng `orderId|quantity` và MIME type `text/plain`. Đây là định dạng minh họa đơn giản; trong hệ thống thực tế, cần cân nhắc escaping, versioning và schema nếu dữ liệu có thể chứa dấu phân cách hoặc phát triển theo thời gian.

Tạo file `src/main/java/CustomConverterDemo.java`:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.converter.AbstractMessageConverter;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

public class CustomConverterDemo {

    private record OrderCommand(String orderId, int quantity) {
        OrderCommand {
            if (orderId == null || orderId.isBlank() || quantity <= 0) {
                throw new IllegalArgumentException("Invalid order command");
            }
        }
    }

    private static final class OrderCommandConverter
            extends AbstractMessageConverter {

        OrderCommandConverter() {
            super(MimeTypeUtils.TEXT_PLAIN);
            setStrictContentTypeMatch(true);
        }

        @Override
        protected boolean supports(Class<?> clazz) {
            return OrderCommand.class == clazz;
        }

        @Override
        protected Object convertToInternal(
                Object payload,
                MessageHeaders headers,
                Object conversionHint) {

            OrderCommand command = (OrderCommand) payload;
            return command.orderId() + "|" + command.quantity();
        }

        @Override
        protected Object convertFromInternal(
                Message<?> message,
                Class<?> targetClass,
                Object conversionHint) {

            String[] fields = ((String) message.getPayload())
                    .split("\\|", -1);

            if (fields.length != 2) {
                throw new IllegalArgumentException(
                        "Invalid OrderCommand wire payload");
            }

            return new OrderCommand(
                    fields[0],
                    Integer.parseInt(fields[1]));
        }
    }

    public static void main(String[] args) {
        OrderCommandConverter converter = new OrderCommandConverter();

        OrderCommand source = new OrderCommand("ORD-42", 3);

        // Cung cấp contentType phù hợp vì converter bật strict matching.
        MessageHeaders textHeaders = MessageBuilder
                .withPayload("header-template")
                .setHeader(
                        MessageHeaders.CONTENT_TYPE,
                        MimeTypeUtils.TEXT_PLAIN)
                .build()
                .getHeaders();

        Message<?> wire = converter.toMessage(source, textHeaders);

        OrderCommand restored = (OrderCommand) converter.fromMessage(
                wire, OrderCommand.class);

        // Không hỗ trợ payload String.
        Message<?> unsupportedSource = converter.toMessage(
                "plain text", textHeaders);

        // Không hỗ trợ kiểu đích Integer.
        Object unsupportedTarget = converter.fromMessage(
                wire, Integer.class);

        // Không nhận MIME type application/json.
        Message<String> wrongMime = MessageBuilder
                .withPayload("ORD-42|3")
                .setHeader(
                        MessageHeaders.CONTENT_TYPE,
                        MimeTypeUtils.APPLICATION_JSON)
                .build();

        Object rejectedMime = converter.fromMessage(
                wrongMime, OrderCommand.class);

        // Content type hợp lệ nhưng payload không đúng wire format.
        Message<String> malformedWire = MessageBuilder
                .withPayload("ORD-42|not-a-number")
                .setHeader(
                        MessageHeaders.CONTENT_TYPE,
                        MimeTypeUtils.TEXT_PLAIN)
                .build();

        boolean malformedRejected;
        try {
            converter.fromMessage(malformedWire, OrderCommand.class);
            malformedRejected = false;
        }
        catch (IllegalArgumentException ex) {
            malformedRejected = true;
        }

        System.out.println("wire payload: " + wire.getPayload());
        System.out.println("wire contentType: "
                + wire.getHeaders().get(MessageHeaders.CONTENT_TYPE));
        System.out.println("restored: " + restored.orderId()
                + ", quantity=" + restored.quantity());
        System.out.println("unsupported source returns null: "
                + (unsupportedSource == null));
        System.out.println("unsupported target returns null: "
                + (unsupportedTarget == null));
        System.out.println("unsupported contentType returns null: "
                + (rejectedMime == null));
        System.out.println("malformed payload rejected: "
                + malformedRejected);
    }
}
```

Tạo `pom.xml` ở thư mục gốc:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>custom-message-converter-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>7.0.10</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>CustomConverterDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Chạy từ thư mục chứa `pom.xml`:

```bash
mvn -q clean compile exec:java
```

Kết quả stdout:

```text
wire payload: ORD-42|3
wire contentType: text/plain
restored: ORD-42, quantity=3
unsupported source returns null: true
unsupported target returns null: true
unsupported contentType returns null: true
malformed payload rejected: true
```

Ví dụ cho thấy ba điều kiện hỗ trợ hoạt động độc lập:

1. Payload đầu vào phải là `OrderCommand`.
2. Kiểu đích khi đọc phải là `OrderCommand`.
3. Content type phải tương thích với `text/plain` do converter khai báo.

Khi đủ điều kiện nhưng nội dung không hợp lệ, converter ném lỗi để caller biết dữ liệu không đúng định dạng.

## 6. Đăng ký converter với template

Khi dùng các phương thức chuyển đổi của messaging template, có thể gắn converter riêng bằng `setMessageConverter`:

```java
GenericMessagingTemplate template = new GenericMessagingTemplate();
template.setMessageConverter(new OrderCommandConverter());
```

Template dùng converter đã cấu hình cho các thao tác chuyển đổi payload, chẳng hạn `convertAndSend` và `convertSendAndReceive`. Nếu dùng request-reply, converter phải hỗ trợ cả kiểu request được gửi đi và kiểu reply mà caller muốn nhận.

Đối với `convertSendAndReceive`, luồng tổng quát là:

1. Converter biến request payload thành message.
2. Template gửi request và chờ reply.
3. Converter chuyển reply message thành kiểu đích mà caller yêu cầu.

Nếu converter chỉ hỗ trợ `OrderCommand` nhưng reply là `OrderReply`, cần mở rộng converter để hỗ trợ cả hai kiểu hoặc dùng một converter phù hợp khác. Đừng giả định converter chỉ cần hỗ trợ chiều gửi.

## 7. SmartMessageConverter và conversion hint

`SmartMessageConverter` mở rộng `MessageConverter` bằng hai overload có thêm `conversionHint`:

```java
Message<?> toMessage(
        Object payload,
        MessageHeaders headers,
        Object conversionHint);

Object fromMessage(
        Message<?> message,
        Class<?> targetClass,
        Object conversionHint);
```

Hint là metadata dành cho quá trình chuyển đổi, ví dụ thông tin generic type hoặc annotation mà framework truyền vào. Nó không thay thế payload type hay content type.

`AbstractMessageConverter` đã triển khai `SmartMessageConverter`. Nếu converter không cần hint, có thể bỏ qua tham số này như trong ví dụ. Nếu cần, override các hook có tham số `conversionHint` để điều chỉnh việc serialize/deserialize theo ngữ cảnh.

Không nên nhét dữ liệu nghiệp vụ tùy tiện vào conversion hint. Dùng headers cho metadata của message; dùng hint cho thông tin điều khiển chuyển đổi do caller/framework xác định.

## 8. CompositeMessageConverter và thứ tự converter

Khi một ứng dụng hỗ trợ nhiều kiểu dữ liệu, có thể dùng `CompositeMessageConverter` để kết hợp nhiều converter:

```java
MessageConverter composite = new CompositeMessageConverter(
        List.of(
                new OrderCommandConverter(),
                new ByteArrayMessageConverter(),
                new StringMessageConverter()
        )
);
```

Composite thử các converter theo danh sách đã cung cấp và dùng kết quả chuyển đổi đầu tiên phù hợp. Vì vậy thứ tự rất quan trọng:

- Đặt converter chuyên biệt trước converter tổng quát.
- Không để converter quá rộng nhận payload mà nó không thật sự hiểu.
- Mỗi converter cần trả về `null` khi không hỗ trợ để composite có thể thử converter kế tiếp.
- Khi dữ liệu thuộc phạm vi hỗ trợ nhưng sai định dạng, ném exception rõ ràng để không che giấu lỗi bằng một converter khác.

Khi kết hợp converter JSON, chuỗi và byte array, hãy xác định rõ MIME type và kiểu Java để tránh hai converter cùng nhận một message theo những cách khác nhau.

## 9. Quy tắc thiết kế converter riêng

### Kiểm tra cả kiểu và content type

Một converter chỉ nên nhận message khi:

- Payload hoặc target class nằm trong nhóm kiểu đã khai báo.
- Content type tương thích với định dạng converter hỗ trợ.
- Payload có cấu trúc hợp lệ theo schema/wire format của converter.

Không chỉ kiểm tra tên class rồi giả định mọi payload đều đúng cấu trúc.

### Không che giấu dữ liệu sai

Trả `null` khi converter không hỗ trợ là hợp lý. Nhưng khi converter đã nhận message và phát hiện payload sai định dạng, hãy ném exception có nguyên nhân cụ thể, ví dụ:

- Thiếu trường bắt buộc.
- Số không parse được.
- Phiên bản schema không hỗ trợ.
- JSON/XML/byte sequence không hợp lệ.
- Dữ liệu vượt giới hạn kích thước.

### Giữ content type chính xác

Đặt `contentType` tương ứng với wire format. Nếu converter serialize JSON, dùng JSON MIME type; nếu serialize văn bản, dùng `text/plain`. Không dùng content type chỉ để ép converter được chọn.

### Xử lý null và kiểu dữ liệu

Quy định rõ converter có chấp nhận payload null hay không. Với các DTO quan trọng, kiểm tra trường bắt buộc và miền giá trị ngay trong quá trình deserialize hoặc constructor của DTO.

### Versioning và tương thích ngược

Khi wire format thay đổi, cân nhắc:

- Thêm schema version hoặc content type có version.
- Duy trì khả năng đọc message phiên bản cũ trong thời gian chuyển đổi.
- Không thay đổi ý nghĩa trường hiện có mà không nâng version.
- Viết test cho cả dữ liệu hiện tại và dữ liệu lịch sử.

## 10. Kiểm thử điều kiện hỗ trợ

Một bộ test hữu ích nên kiểm tra ít nhất các trường hợp:

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Payload đúng class, content type đúng | Tạo message thành công |
| Message đúng wire format, target class đúng | Khôi phục DTO thành công |
| Payload class không hỗ trợ | Converter trả `null` |
| Target class không hỗ trợ | Converter trả `null` |
| Content type không được hỗ trợ khi strict match | Converter không nhận message |
| Content type bị thiếu khi strict match | Converter không nhận message |
| Content type đúng nhưng payload hỏng | Ném lỗi chuyển đổi |
| Payload có giá trị biên hoặc thiếu trường | Tuân theo validation đã định nghĩa |
| Có nhiều converter | Converter chuyên biệt được thử trước converter tổng quát |

Ngoài unit test, nên có integration test ở ranh giới transport thực tế. Một converter chạy tốt với `MessageBuilder` chưa chứng minh broker, WebSocket adapter hoặc JMS provider đang gửi đúng content type và encoding.

## 11. Lỗi thường gặp

1. **Chỉ override `convertToInternal` mà quên `convertFromInternal`.** Converter chỉ hoạt động một chiều.
2. **`supports` trả về true cho mọi class.** Converter có thể nhận dữ liệu mà nó không thể serialize hoặc deserialize.
3. **Khai báo MIME type sai hoặc quá rộng.** Converter có thể nhận message sai định dạng.
4. **Bật strict matching nhưng không gắn content type.** Converter từ chối message dù payload class đúng.
5. **Trả `null` khi payload sai định dạng.** Lỗi dữ liệu bị hiểu nhầm thành converter không hỗ trợ.
6. **Không kiểm tra target class khi deserialize.** Có thể trả về object không đúng kiểu caller yêu cầu.
7. **Đặt converter tổng quát trước converter chuyên biệt.** Composite có thể chọn nhầm converter.
8. **Không đăng ký converter vào template.** Code gọi `convertAndSend` vẫn dùng converter mặc định.
9. **Không kiểm thử hai chiều.** Producer serialize được nhưng consumer không thể deserialize cùng wire format.
10. **Không version hóa schema.** Thay đổi format có thể làm message tồn đọng hoặc producer/consumer khác phiên bản không tương thích.

## 12. Checklist triển khai

- Chọn implement `MessageConverter` trực tiếp hay kế thừa `AbstractMessageConverter`.
- Liệt kê rõ class được hỗ trợ trong `supports(Class<?>)`.
- Khai báo MIME type chính xác.
- Quyết định có bật `strictContentTypeMatch) hay không.
- Cài đặt cả chiều Java-to-message và message-to-Java.
- Trả `null` khi không hỗ trợ; ném lỗi khi dữ liệu thuộc phạm vi nhưng sai định dạng.
- Kiểm tra content type, encoding, schema và giới hạn kích thước.
- Đăng ký converter vào template hoặc composite converter phù hợp.
- Đặt converter chuyên biệt trước converter tổng quát.
- Kiểm thử unsupported type, unsupported MIME, malformed payload, round-trip và tương thích phiên bản.

## 13. Tài liệu tham khảo

- [Spring Framework – MessageConverter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/MessageConverter.html)
- [Spring Framework – AbstractMessageConverter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/AbstractMessageConverter.html)
- [Spring Framework – SmartMessageConverter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/SmartMessageConverter.html)
- [Spring Framework – CompositeMessageConverter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/CompositeMessageConverter.html)
- [Spring Framework – MessageHeaders Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHeaders.html)
