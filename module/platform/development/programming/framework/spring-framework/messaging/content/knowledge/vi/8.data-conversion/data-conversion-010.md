# MessageConversionException khi dữ liệu hoặc kiểu nội dung không hợp lệ

## Mục tiêu

Khi Spring chuyển payload từ dạng truyền tải sang object Java, hoặc chuyển object Java thành payload để gửi đi, quá trình chuyển đổi có thể thất bại. `MessageConversionException` biểu diễn lỗi phát sinh trong quá trình chuyển đổi message của Spring Messaging.

Sau bài này, bạn có thể:

- Nhận diện đúng `org.springframework.messaging.converter.MessageConversionException`.
- Phân biệt lỗi chuyển đổi thực sự với trường hợp converter không hỗ trợ kiểu dữ liệu hoặc MIME type.
- Hiểu vai trò của `MessageHeaders.CONTENT_TYPE`, target class và payload.
- Đọc failed message và nguyên nhân gốc từ exception.
- Xác định lỗi xảy ra ở bước converter, handler hay transport.
- Xử lý lỗi trong luồng đồng bộ, bất đồng bộ và Spring Integration.
- Phân biệt exception cùng tên của Spring Messaging, JMS và AMQP.
- Viết converter có thông báo lỗi rõ ràng và kiểm thử dữ liệu sai định dạng.

## 1. MessageConversionException là gì?

Lớp `org.springframework.messaging.converter.MessageConversionException` là exception do các implementation của Spring Messaging `MessageConverter` phát sinh khi việc chuyển đổi payload thất bại.

Kế thừa của lớp:

~~~text
RuntimeException
  └── NestedRuntimeException
       └── MessagingException
            └── MessageConversionException
~~~

Các đặc điểm:

- Là unchecked exception vì `MessagingException` kế thừa `NestedRuntimeException`, cuối cùng từ `RuntimeException`.
- Thuộc package `org.springframework.messaging.converter`.
- Có thể giữ message gây lỗi trong thuộc tính `failedMessage`.
- Có thể giữ exception gốc trong `cause`.
- Có thể được tạo với message mô tả, với cause, hoặc với cả failed message và cause.

Các constructor chính trong Spring Framework 7:

~~~java
new MessageConversionException("Cannot decode payload");

new MessageConversionException(
        "Cannot decode payload",
        originalException
);

new MessageConversionException(
        failedMessage,
        "Invalid payload",
        originalException
);
~~~

Khi có failed message, có thể truy cập qua:

~~~java
Message<?> failed = exception.getFailedMessage();
Throwable cause = exception.getCause();
Throwable rootCause = exception.getRootCause();
Throwable mostSpecificCause = exception.getMostSpecificCause();
~~~

Không phải constructor nào cũng có failed message. Ví dụ, lỗi outbound xảy ra khi đang chuyển một object trước khi tạo message mới; khi đó converter có thể dùng constructor chỉ nhận mô tả và cause.

## 2. Lỗi chuyển đổi xảy ra ở đâu?

Một luồng chuyển đổi thường có hai chiều.

### Inbound: payload truyền tải thành object Java

~~~mermaid
flowchart LR
    A["Payload nhận được"] --> B["Spring Message"]
    B --> C["Đọc contentType"]
    C --> D["Chọn MessageConverter"]
    D --> E["fromMessage(message, targetClass)"]
    E --> F["Object Java"]
    E --> X["MessageConversionException"]
~~~

Ví dụ: ứng dụng nhận payload JSON bytes, header ghi `application/json`, rồi yêu cầu converter tạo `OrderCreated.class`. Nếu JSON bị cắt, sai cú pháp hoặc không thể ánh xạ theo cấu hình converter, quá trình parse có thể thất bại.

### Outbound: object Java thành payload truyền tải

~~~mermaid
flowchart LR
    A["Object Java"] --> B["toMessage(payload, headers)"]
    B --> C["Chọn định dạng và serialize"]
    C --> D["Spring Message"]
    D --> E["Adapter / transport"]
    C --> X["MessageConversionException"]
~~~

Ví dụ: ứng dụng muốn gửi một object nhưng converter không thể serialize một trường hoặc kiểu dữ liệu. Lỗi có thể xuất hiện trước khi message được gửi tới broker.

Converter không tự gửi message qua mạng. `MessageConversionException` nói về việc chuyển đổi; lỗi kết nối broker, quyền truy cập, timeout hoặc giao nhận thuộc các lớp lỗi khác.

## 3. Phân biệt null với MessageConversionException

Đây là điểm cần hiểu chính xác khi đọc API.

Hợp đồng `MessageConverter` quy định:

- `fromMessage(message, targetClass)` trả về object nếu chuyển đổi thành công.
- `toMessage(payload, headers)` trả về message nếu chuyển đổi thành công.
- Nếu converter không hỗ trợ media type, kiểu payload hoặc không thể nhận chuyển đổi theo hợp đồng, nó nên trả về `null`.

Vì vậy, không phải mọi trường hợp converter không thể xử lý đều tự động tạo `MessageConversionException`.

| Tình huống | Kết quả thường gặp |
|---|---|
| Converter không hỗ trợ `application/xml` | Trả về `null` để converter khác có thể thử. |
| Target class không thuộc kiểu converter hỗ trợ | Trả về `null`. |
| Content type không khớp khi bật strict matching | Trả về `null`. |
| JSON được chọn đúng converter nhưng cú pháp JSON bị hỏng | Converter có thể ném `MessageConversionException` với lỗi parser làm cause. |
| Payload là văn bản nhưng converter mong đợi byte array | Có thể trả về `null` hoặc ném exception tùy implementation và đường gọi. |
| Custom converter nhận đúng định dạng nhưng dữ liệu không đáp ứng quy tắc | Nên ném `MessageConversionException` mô tả lỗi dữ liệu. |

Cần phân biệt ba trạng thái:

1. **Không nhận xử lý:** converter trả về `null`.
2. **Chuyển đổi thất bại:** converter đã nhận xử lý nhưng dữ liệu không thể chuyển đổi; có thể ném `MessageConversionException`.
3. **Không có converter nào phù hợp:** composite hoặc tầng gọi có thể báo lỗi vì không tìm được converter. Exception cụ thể phụ thuộc thành phần điều phối.

Nếu ứng dụng dùng `CompositeMessageConverter`, giá trị `null` thường cho phép thử converter tiếp theo. Exception do converter ném ra thường làm quá trình hiện tại thất bại, thay vì được hiểu là lời từ chối nhẹ nhàng.

## 4. Content type không hợp lệ và MIME type không được hỗ trợ

`MessageHeaders.CONTENT_TYPE` mô tả định dạng payload. Ví dụ:

| Content type | Định dạng |
|---|---|
| `application/json` | JSON |
| `text/plain` | Văn bản thuần |
| `application/octet-stream` | Dữ liệu nhị phân |
| `application/xml` | XML |

Các converter kế thừa `AbstractMessageConverter` thường kiểm tra hai điều kiện trước khi chuyển đổi:

- Target class hoặc payload class có nằm trong nhóm được converter hỗ trợ không.
- Content type có khớp với MIME type mà converter hỗ trợ không.

Có thể cấu hình strict content type matching:

~~~java
converter.setStrictContentTypeMatch(true);
~~~

Khi bật strict matching, converter cần phân giải được content type phù hợp. Nếu header bị thiếu hoặc MIME type không khớp, converter có thể trả về `null` vì nó không nhận xử lý message đó.

Cần phân biệt:

- **MIME type hợp lệ nhưng không được hỗ trợ:** converter từ chối nhận message; thường trả về `null`.
- **Không có content type:** kết quả phụ thuộc resolver và strict matching.
- **MIME type có cú pháp sai:** lỗi có thể phát sinh ngay trong bước phân tích MIME type, từ resolver hoặc parser. Không mặc định exception đó luôn là `MessageConversionException`.
- **MIME type hợp lệ nhưng payload không đúng định dạng:** converter có thể bắt đầu parse rồi ném `MessageConversionException`.

Content type phải phản ánh bytes thực tế. Đặt `application/json` cho một chuỗi không phải JSON sẽ không biến chuỗi đó thành JSON hợp lệ.

## 5. Những nguyên nhân phổ biến

### Payload sai cú pháp

Ví dụ JSON không hợp lệ:

~~~json
{
  "orderId": "ORD-42",
  "total": 250000,
}
~~~

Dấu phẩy cuối không hợp lệ trong JSON chuẩn. JSON converter có thể ném exception khi parser đọc payload.

### Payload không khớp target class

Consumer yêu cầu `OrderCreated.class`, nhưng payload thực tế chứa một kiểu dữ liệu hoặc cấu trúc khác. Ví dụ, consumer yêu cầu một object có trường `orderId` kiểu String, trong khi dữ liệu truyền tải lại chứa giá trị có cấu trúc không thể ánh xạ theo cấu hình.

Không phải mọi khác biệt schema đều gây exception: một số mapper có thể bỏ qua field lạ hoặc gán giá trị mặc định. Hành vi phụ thuộc mapper và cấu hình.

### Sai charset hoặc encoding

Producer gửi UTF-8 nhưng consumer giải mã bằng charset khác. Dữ liệu có dấu hoặc ký tự ngoài ASCII có thể bị biến dạng, dẫn tới lỗi parse hoặc sai nội dung.

Hãy thống nhất charset ở cả hai phía và khai báo content type chính xác, ví dụ `text/plain;charset=UTF-8`.

### Sai kiểu payload

Converter mong đợi `byte[]` nhưng nhận một object Java không được hỗ trợ, hoặc mong đợi String nhưng nhận object khác. Nếu converter không nhận kiểu đó, nó có thể trả về `null`; nếu custom converter đã nhận xử lý nhưng không thể diễn giải, nó có thể ném exception.

### Schema hoặc phiên bản dữ liệu không tương thích

Producer thêm field, đổi tên field, thay kiểu dữ liệu hoặc thay version schema. Consumer cũ có thể không hiểu dữ liệu mới, tùy chính sách tương thích của serializer/deserializer.

### Header hoặc metadata không đúng

Content type, type header, charset hoặc metadata dùng để xác định target class có thể không khớp với payload. Không nên tin cậy mù quáng type header đến từ message bên ngoài; hãy kiểm tra allowlist kiểu dữ liệu và quy tắc mapping.

## 6. Cấu trúc exception và cách đọc nguyên nhân

Ví dụ một exception có failed message và cause:

~~~java
throw new MessageConversionException(
        message,
        "Expected payload format orderId=<id>",
        new IllegalArgumentException("Missing order id")
);
~~~

Thông tin cần kiểm tra:

| Thành phần | Ý nghĩa |
|---|---|
| `getMessage()` | Mô tả lỗi do converter hoặc tầng gọi cung cấp. |
| `getFailedMessage()` | Message đã gây lỗi, nếu exception được tạo với message đó. |
| `getCause()` | Nguyên nhân trực tiếp được bọc lại, ví dụ parser exception. |
| `getRootCause()` | Nguyên nhân sâu nhất trong cause chain. |
| `getMostSpecificCause()` | Cause cụ thể nhất có thể xác định. |
| Stack trace | Vị trí converter, mapper hoặc adapter phát sinh lỗi. |

Ví dụ log có ích:

~~~java
catch (MessageConversionException ex) {
    Message<?> failed = ex.getFailedMessage();

    log.error(
            "Message conversion failed: messageId={}, contentType={}, payloadType={}, reason={}",
            failed != null ? failed.getHeaders().getId() : null,
            failed != null ? failed.getHeaders().get(MessageHeaders.CONTENT_TYPE) : null,
            failed != null ? failed.getPayload().getClass().getName() : null,
            ex.getMessage(),
            ex
    );

    throw ex;
}
~~~

Đoạn code là ví dụ minh họa cách thu thập metadata. Cần bảo đảm payload không phải null trước khi gọi `getClass()` nếu hợp đồng message của ứng dụng cho phép payload null. Không log toàn bộ payload hoặc toàn bộ headers nếu có token, credential hay dữ liệu cá nhân.

## 7. Phân biệt với các exception messaging khác

Không nên bắt mọi lỗi message bằng một exception duy nhất. Các lớp dưới đây thể hiện những giai đoạn khác nhau:

| Exception | Ý nghĩa |
|---|---|
| `MessagingException` | Lớp cơ sở cho lỗi liên quan tới Spring Messaging. |
| `MessageConversionException` | Converter không thể chuyển payload theo định dạng/kiểu đã nhận xử lý. |
| `MessageHandlingException` | Handler không thể xử lý message hoặc nghiệp vụ của handler thất bại. |
| `MessageDeliveryException` | Message không thể được chuyển tới channel/đích xử lý theo yêu cầu. |
| `MethodArgumentResolutionException` | Không thể phân giải/bind tham số của handler method. |
| `InvalidMimeTypeException` | MIME type có cú pháp không hợp lệ khi được parse; đây không phải tên khác của MessageConversionException. |

Một ví dụ để phân biệt:

- JSON hỏng khi converter parse: lỗi chuyển đổi.
- JSON parse thành object thành công nhưng dữ liệu không thỏa quy tắc đặt hàng: lỗi validation/nghiệp vụ ở handler.
- Channel không tìm được đích hoặc không thể dispatch: lỗi delivery/routing.
- Handler method không thể bind tham số theo khai báo: lỗi argument resolution.

Việc xác định đúng giai đoạn giúp sửa đúng nguyên nhân và tránh retry không cần thiết.

## 8. Cùng tên exception trong JMS và AMQP

Trong hệ sinh thái Spring có nhiều class cùng tên `MessageConversionException`, nhưng package và hierarchy khác nhau.

| Module | Fully qualified class | Base class |
|---|---|---|
| Spring Messaging | `org.springframework.messaging.converter.MessageConversionException` | `MessagingException` |
| Spring JMS | `org.springframework.jms.support.converter.MessageConversionException` | `JmsException` |
| Spring AMQP | `org.springframework.amqp.support.converter.MessageConversionException` | `AmqpException` |

Không dùng nhầm import. Nếu import wildcard từ nhiều package, tên class có thể bị trùng và gây lỗi biên dịch hoặc khiến code bắt nhầm loại exception.

Spring AMQP cũng mô tả conversion exception là lỗi phía client khi converter không thể chuyển đổi object/message; bản thân lỗi đó không phải protocol error hay broker failure. JMS và AMQP có converter, listener container và cơ chế acknowledgement riêng.

Trong một flow có adapter, exception của protocol converter có thể được bọc hoặc chuyển thành error message ở tầng Integration. Hãy kiểm tra root cause và class thực tế trong stack trace thay vì chỉ nhìn tên exception ngoài cùng.

## 9. Xử lý lỗi trong Spring Integration

Cách exception được trả về phụ thuộc flow chạy đồng bộ hay bất đồng bộ.

### Luồng đồng bộ với DirectChannel

Với `DirectChannel`, handler thường chạy trong thread gọi send. Nếu converter hoặc handler ném exception trong call stack này, exception có thể truyền về sender.

~~~text
Producer
   |
   v
DirectChannel
   |
   v
Converter / Handler
   |
   +---- success ---> tiếp tục flow
   |
   +---- exception ---> caller nhận exception
~~~

Đây là hành vi gần với một lời gọi Java thông thường.

### Luồng bất đồng bộ

Với `ExecutorChannel`, queue/poller hoặc task executor, sender có thể đã tiếp tục trước khi handler hoàn tất. Không thể dùng exception thông thường để truyền lỗi ngược về sender qua call stack đã kết thúc.

Spring Integration hỗ trợ chuyển lỗi thành `ErrorMessage` và gửi tới:

1. `errorChannel` được chỉ định trong header `MessageHeaders.ERROR_CHANNEL`, nếu có.
2. Global `errorChannel` nếu không có channel riêng.

Điều này áp dụng cho các task do Spring Integration quản lý theo cơ chế async tương ứng. Không nên giả định mọi exception ở bất kỳ thread nào đều tự động xuất hiện trên error channel.

### Gateway

Gateway có thể nhận lỗi downstream và mặc định ném lỗi về caller. Có thể cấu hình `error-channel` để chuyển exception thành một flow xử lý lỗi hoặc tạo response lỗi theo hợp đồng của ứng dụng.

Nếu error flow tiêu thụ lỗi và trả kết quả bình thường, caller có thể nhận response đã được chuyển đổi thay vì exception ban đầu. Hãy xác định rõ liệu lỗi conversion là lỗi phải dừng workflow hay có thể chuyển thành kết quả nghiệp vụ.

## 10. Lỗi conversion khi nhận message từ RabbitMQ

Khi dùng Spring Integration AMQP inbound adapter/gateway, message từ RabbitMQ được chuyển đổi sang Spring Messaging `Message<?>` bằng converter.

Theo tài liệu Spring Integration 7.1.1:

- Nếu không có error channel, conversion error được ném về listener container để error handler xử lý.
- Default error handler xem conversion error là fatal; message có thể bị reject và được route tới dead-letter exchange nếu queue đã cấu hình.
- Nếu có error channel, payload của `ErrorMessage` có thể là `ListenerExecutionFailedException`, kèm failed message và cause.
- Với acknowledge mode AUTO, nếu error flow tiêu thụ lỗi mà không ném tiếp exception, message gốc có thể được acknowledge.
- Nếu error flow ném exception, listener container và error handler quyết định có requeue hay không.
- Với acknowledge mode MANUAL, error context có thể chứa channel và delivery tag để flow quyết định ack/nack/reject.

Không suy luận rằng mọi conversion error đều tự động được retry hoặc tự động vào dead-letter queue. Kết quả phụ thuộc acknowledge mode, error handler, error channel, queue/DLX và cấu hình broker.

## 11. Quy trình chẩn đoán

Khi gặp `MessageConversionException`, kiểm tra theo thứ tự:

1. **Xác định class đầy đủ.** Đọc package để biết đây là exception của Spring Messaging, JMS hay AMQP.
2. **Xác định chiều chuyển đổi.** Lỗi xảy ra ở `fromMessage` hay `toMessage`?
3. **Kiểm tra content type.** MIME type có hợp lệ và được converter hỗ trợ không? Có charset không?
4. **Kiểm tra target class.** Handler yêu cầu kiểu gì? Converter có hỗ trợ kiểu đó không?
5. **Kiểm tra payload runtime type.** Payload thực tế là String, byte array hay object?
6. **Kiểm tra bytes/nội dung.** Có bị cắt, encode sai, thiếu field hoặc sai cấu trúc không?
7. **Đọc cause/root cause.** Tìm parser exception, charset decoder exception, reflection/binding error hoặc lỗi custom validation trong converter.
8. **Kiểm tra converter selection.** Có nhiều converter không? Thứ tự composite có khiến converter tổng quát nhận message trước không?
9. **Kiểm tra adapter và header mapper.** Content type, native headers hoặc type metadata có bị thay đổi khi qua transport không?
10. **Kiểm tra retry/acknowledgement.** Lỗi là dữ liệu sai có tính cố định hay lỗi hạ tầng tạm thời?

Không sửa lỗi bằng cách bắt exception rồi trả `null` một cách im lặng. Điều đó có thể làm mất message hoặc khiến flow tiếp tục với dữ liệu không đầy đủ.

## 12. Ví dụ Java 17+ chạy được: custom converter ném MessageConversionException

Ví dụ sau tạo converter chỉ nhận `text/plain` và target class `OrderData`. Payload phải có định dạng `orderId=<id>`. Nếu dữ liệu sai định dạng, converter ném `MessageConversionException` và giữ failed message cùng cause.

Một message có MIME type không được hỗ trợ sẽ được converter từ chối bằng `null`, giúp thấy rõ khác biệt giữa “không nhận xử lý” và “đã nhận nhưng dữ liệu sai”.

Cấu trúc project:

~~~text
message-conversion-error-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          MessageConversionErrorDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>message-conversion-error-demo</artifactId>
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

### MessageConversionErrorDemo.java

~~~java
package demo;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.converter.AbstractMessageConverter;
import org.springframework.messaging.converter.MessageConversionException;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

public class MessageConversionErrorDemo {

    public record OrderData(String orderId) {
    }

    static final class OrderTextConverter extends AbstractMessageConverter {

        private static final String PREFIX = "orderId=";

        OrderTextConverter() {
            super(MimeTypeUtils.TEXT_PLAIN);
            setStrictContentTypeMatch(true);
        }

        @Override
        protected boolean supports(Class<?> clazz) {
            return OrderData.class == clazz;
        }

        @Override
        protected Object convertFromInternal(
                Message<?> message,
                Class<?> targetClass,
                Object conversionHint) {

            Object payload = message.getPayload();

            if (!(payload instanceof String text)) {
                throw new MessageConversionException(
                        message,
                        "Expected a String payload",
                        new IllegalArgumentException("Payload must be text")
                );
            }

            if (!text.startsWith(PREFIX) || text.length() == PREFIX.length()) {
                throw new MessageConversionException(
                        message,
                        "Expected payload format orderId=<id>",
                        new IllegalArgumentException("Missing or invalid order id")
                );
            }

            return new OrderData(text.substring(PREFIX.length()));
        }
    }

    public static void main(String[] args) {
        OrderTextConverter converter = new OrderTextConverter();

        Message<String> malformed = MessageBuilder
                .withPayload("not-an-order")
                .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.TEXT_PLAIN)
                .build();

        try {
            converter.fromMessage(malformed, OrderData.class);
        }
        catch (MessageConversionException ex) {
            System.out.println("exception=" + ex.getClass().getSimpleName());
            System.out.println("failedMessagePresent="
                    + (ex.getFailedMessage() != null));
            System.out.println("cause=" + ex.getCause().getClass().getSimpleName());
        }

        Message<String> unsupportedContentType = MessageBuilder
                .withPayload("orderId=ORD-42")
                .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
                .build();

        Object result = converter.fromMessage(
                unsupportedContentType,
                OrderData.class
        );

        System.out.println("unsupportedContentTypeResult=" + result);
    }
}
~~~

Chạy từ thư mục project bằng Java 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.MessageConversionErrorDemo
~~~

Kết quả stdout:

~~~text
exception=MessageConversionException
failedMessagePresent=true
cause=IllegalArgumentException
unsupportedContentTypeResult=null
~~~

Giải thích:

1. Converter khai báo hỗ trợ `text/plain` và chỉ nhận target class `OrderData`.
2. `setStrictContentTypeMatch(true)` yêu cầu content type phải khớp MIME type đã khai báo.
3. Message đầu có content type hợp lệ nhưng payload không đúng format `orderId=<id>`.
4. Converter đã nhận xử lý và chủ động ném `MessageConversionException`.
5. Exception giữ failed message và `IllegalArgumentException` làm cause.
6. Message thứ hai có `application/json`, không nằm trong MIME type được hỗ trợ. Converter từ chối xử lý và trả về `null`, không ném exception trong trường hợp này.

Đây là custom converter để minh họa quy tắc. Converter JSON thực tế sẽ dùng parser/mapper riêng và có thể bọc lỗi parser thành `MessageConversionException` theo implementation.

## 13. Kiểm thử và phòng ngừa

Nên có các test riêng cho từng nhóm dữ liệu:

- Payload hợp lệ với content type hợp lệ.
- Payload sai cú pháp nhưng content type đúng.
- Payload đúng cú pháp nhưng target class không phù hợp.
- Content type được hỗ trợ nhưng charset sai.
- Content type hợp lệ nhưng converter không hỗ trợ.
- Content type bị thiếu khi strict matching bật.
- Header hoặc type metadata không đáng tin cậy.
- Payload vượt giới hạn kích thước.
- Schema cũ và mới trong quá trình rolling deployment.

Một test nên xác nhận cả kết quả lẫn ngữ cảnh exception:

- Có đúng loại exception không?
- Failed message có được gắn vào không?
- Cause có giữ nguyên parser/decoder error không?
- Thông tin lỗi có đủ để xác định converter và target class không?
- Message có bị retry vô hạn hoặc bị acknowledge sai không?

### Quy tắc xử lý theo loại lỗi

| Loại lỗi | Hướng xử lý |
|---|---|
| Dữ liệu malformed, không thể sửa bằng retry | Reject hoặc đưa vào dead-letter/quarantine; lưu metadata để điều tra. |
| Schema version không tương thích | Sửa hợp đồng producer/consumer hoặc triển khai migration/compatibility. |
| Content type sai | Sửa producer/header mapper; không đổi target class để che lỗi. |
| Charset sai | Đồng bộ encoding và content type ở cả hai đầu. |
| Converter không hỗ trợ định dạng | Đăng ký converter phù hợp hoặc điều chỉnh định dạng đã thống nhất. |
| Lỗi hạ tầng tạm thời trong downstream handler | Retry có giới hạn theo chính sách; không coi lỗi parse cố định là lỗi tạm thời. |

Không retry vô hạn một message có payload malformed. Mỗi lần thử lại vẫn nhận cùng bytes và cùng lỗi, đồng thời có thể gây nghẽn queue hoặc làm tăng tải log. Nếu dùng error channel, phải xác định rõ error flow sẽ rethrow, reject, ack hay chuyển message sang nơi lưu lỗi.

## 14. Checklist trước khi đưa vào production

- [ ] Dùng đúng class `org.springframework.messaging.converter.MessageConversionException` khi làm việc với Spring Messaging.
- [ ] Xác định converter được gọi ở chiều inbound hay outbound.
- [ ] Phân biệt `null` (converter không nhận xử lý) với exception (conversion đã thất bại).
- [ ] Content type, charset và payload format thống nhất.
- [ ] Target class và schema tương thích với producer.
- [ ] Cause gốc được giữ lại trong exception.
- [ ] Failed message được giữ khi phù hợp để điều tra.
- [ ] Log có message ID, content type, payload type và converter; không log secret/raw payload nhạy cảm.
- [ ] Error channel hoặc gateway error flow được cấu hình đúng với sync/async processing.
- [ ] Acknowledge, retry, requeue và dead-letter policy đã được kiểm thử.
- [ ] Conversion error cố định không bị retry vô hạn.
- [ ] Có test với malformed payload, content type sai và schema cũ/mới.

## Ghi nhớ

- `MessageConversionException` của Spring Messaging nằm trong package `org.springframework.messaging.converter` và kế thừa `MessagingException`.
- Exception có thể chứa failed message và cause; dùng chúng để tìm payload và nguyên nhân gốc.
- Converter không hỗ trợ MIME type hoặc kiểu dữ liệu thường trả về `null` theo hợp đồng `MessageConverter`.
- Payload malformed sau khi converter nhận xử lý có thể làm converter ném `MessageConversionException`.
- Content type sai không phải lúc nào cũng tạo exception này; strict matching có thể khiến converter trả về `null`.
- Lỗi conversion khác lỗi handler, delivery, routing hoặc broker connection.
- Spring Integration xử lý lỗi khác nhau giữa flow đồng bộ và bất đồng bộ; AMQP còn phụ thuộc listener container và acknowledgement mode.
- Không retry vô hạn dữ liệu sai cố định; hãy sửa producer/schema hoặc đưa message lỗi vào quarantine/DLQ.

## Tài liệu chính thức

- [Spring Framework Javadoc: MessageConversionException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/MessageConversionException.html)
- [Spring Framework Javadoc: MessagingException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessagingException.html)
- [Spring Framework Javadoc: MessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/MessageConverter.html)
- [Spring Framework Javadoc: AbstractMessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/AbstractMessageConverter.html)
- [Spring Integration Reference: Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Spring Integration Reference: Inbound AMQP Message Conversion](https://docs.spring.io/spring-integration/reference/amqp/conversion-inbound.html)
- [Spring JMS Javadoc: MessageConversionException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/converter/MessageConversionException.html)
- [Spring AMQP Javadoc: MessageConversionException](https://docs.spring.io/spring-amqp/docs/current/api/org/springframework/amqp/support/converter/MessageConversionException.html)
