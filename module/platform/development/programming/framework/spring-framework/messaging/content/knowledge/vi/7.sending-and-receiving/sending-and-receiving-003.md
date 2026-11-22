# MessageRequestReplyOperations và trao đổi yêu cầu phản hồi trong Spring Messaging

Trong Spring Messaging, request-reply là mô hình một thành phần gửi request đến destination rồi chờ response tương ứng. Interface `MessageRequestReplyOperations<D>` mô tả hợp đồng này: gửi một message yêu cầu và nhận message phản hồi, hoặc chuyển đổi payload request/reply qua `MessageConverter`.

Interface này thuộc package `org.springframework.messaging.core`. Nó là **hợp đồng thao tác**, không phải một channel hay transport cụ thể. Một implementation như `GenericMessagingTemplate` có thể dùng `MessageChannel`; template chuyên biệt khác có thể làm việc với destination của một transport như JMS.

## 1. MessageRequestReplyOperations là gì?

Khai báo rút gọn:

```java
public interface MessageRequestReplyOperations<D> {
    Message<?> sendAndReceive(Message<?> requestMessage);

    Message<?> sendAndReceive(D destination, Message<?> requestMessage);

    <T> T convertSendAndReceive(Object request, Class<T> targetClass);

    <T> T convertSendAndReceive(D destination,
                               Object request,
                               Class<T> targetClass);
}
```

Đây là phần cốt lõi của API; interface còn có overload để truyền headers và `MessagePostProcessor`.

Tham số kiểu `D` biểu diễn kiểu destination mà implementation sử dụng. Ví dụ:

- Với `GenericMessagingTemplate`, destination là `MessageChannel`.
- Với template tích hợp JMS, destination có thể là đối tượng `Destination` của JMS.
- Với `DestinationResolvingMessageRequestReplyOperations`, có thêm các overload nhận tên destination dạng `String` để implementation phân giải thành destination thực.

Không khởi tạo trực tiếp interface. Trong ứng dụng Spring Messaging, thường dùng `GenericMessagingTemplate` rồi tham chiếu nó qua interface để code phụ thuộc vào hợp đồng request-reply:

```java
GenericMessagingTemplate template = new GenericMessagingTemplate();
MessageRequestReplyOperations<MessageChannel> operations = template;
```

Cách khai báo này giúp phần gọi không cần biết class triển khai cụ thể ngoài kiểu destination đã chọn.

## 2. Hai nhóm phương thức chính

### `sendAndReceive`: gửi và nhận Message

`sendAndReceive` nhận một `Message<?>` đã được tạo sẵn và trả về reply cũng dưới dạng `Message<?>`:

```java
Message<?> reply = operations.sendAndReceive(destination, requestMessage);
```

Dùng API này khi cần kiểm soát payload và headers của request, hoặc khi cần đọc cả headers của response như correlation ID, content type hay metadata do handler trả về.

Có hai dạng:

- `sendAndReceive(requestMessage)`: gửi đến default destination đã cấu hình trên template.
- `sendAndReceive(destination, requestMessage)`: chỉ rõ destination cho lần gọi.

### `convertSendAndReceive`: chuyển đổi payload request và reply

`convertSendAndReceive` nhận một đối tượng payload thông thường, đóng gói/chuyển đổi nó thành message, gửi đi, nhận reply rồi chuyển payload reply sang kiểu đích:

```java
String reply = operations.convertSendAndReceive(
        destination,
        "Lan",
        String.class);
```

Các overload cho phép:

- Truyền headers dưới dạng `Map<String, Object>`.
- Truyền `MessagePostProcessor` để chỉnh message request sau khi nó được tạo/chuyển đổi.
- Kết hợp cả headers và post-processor.
- Dùng default destination hoặc truyền destination rõ ràng.

| Phương thức | Request | Kết quả |
| --- | --- | --- |
| `sendAndReceive` | `Message<?>` | Reply nguyên dạng `Message<?>` |
| `convertSendAndReceive` | Payload bất kỳ | Payload reply chuyển đổi sang `Class<T>` |
| Có `headers` | Payload + metadata | Headers được gắn vào request |
| Có `MessagePostProcessor` | Message request đã tạo | Cho phép bổ sung/chỉnh message trước khi gửi |

`MessagePostProcessor` áp dụng cho request message. Nó hữu ích để thêm correlation ID, version, tenant hoặc metadata mà không cần tự tạo toàn bộ message từ đầu.

## 3. Luồng request-reply

Với một implementation dựa trên `MessageChannel`, luồng trao đổi thường diễn ra như sau:

1. Caller tạo request.
2. Template chuẩn bị cơ chế nhận reply cho lần gọi và gửi request đến destination.
3. Handler nhận request, xử lý payload.
4. Handler gửi reply về reply destination/channel được template cung cấp trong message.
5. Template nhận reply và trả lại cho caller.
6. Nếu không nhận được reply trong receive timeout, phương thức trả về `null`.

Trong `GenericMessagingTemplate`, template quản lý reply channel tạm thời cho request-reply. Handler có thể lấy channel đó từ header `MessageHeaders.REPLY_CHANNEL` rồi gửi response về. Mỗi lần gọi có kênh nhận riêng, nhờ đó reply có thể được ghép với đúng caller khi nhiều request đang chờ đồng thời.

Interface `MessageRequestReplyOperations` không bắt handler phải trả về một giá trị Java từ `handleMessage`. Handler phải gửi một message reply theo cơ chế của transport/template. Nếu handler chỉ xử lý request mà không phát reply, caller sẽ tiếp tục chờ đến khi timeout.

## 4. Ví dụ Java 17+ với GenericMessagingTemplate

Ví dụ dùng `ExecutorSubscribableChannel` để nhận request và gửi reply. Nó minh họa cả `sendAndReceive`, `convertSendAndReceive`, headers, post-processor và trường hợp timeout.

Tạo file `src/main/java/RequestReplyOperationsDemo.java`:

```java
import java.util.Map;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.core.GenericMessagingTemplate;
import org.springframework.messaging.core.MessageRequestReplyOperations;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class RequestReplyOperationsDemo {

    public static void main(String[] args) {
        ExecutorSubscribableChannel requests = new ExecutorSubscribableChannel();

        requests.subscribe(request -> {
            if ("no-reply".equals(request.getPayload())) {
                return;
            }

            String name = (String) request.getPayload();
            Object version = request.getHeaders().get("requestVersion");
            String greeting = version == null
                    ? "Hello, " + name
                    : "v" + version + ": Hello, " + name;

            Object target = request.getHeaders().get(MessageHeaders.REPLY_CHANNEL);
            if (target instanceof MessageChannel replyChannel) {
                replyChannel.send(MessageBuilder
                        .withPayload(greeting)
                        .setHeader("correlationId",
                                request.getHeaders().get("correlationId"))
                        .build());
            }
        });

        GenericMessagingTemplate template = new GenericMessagingTemplate();
        template.setReceiveTimeout(200);

        MessageRequestReplyOperations<MessageChannel> operations = template;

        // API giữ nguyên Message request và Message reply.
        Message<String> request = MessageBuilder
                .withPayload("Lan")
                .setHeader("correlationId", "req-42")
                .build();

        Message<?> reply = operations.sendAndReceive(requests, request);

        // API chuyển đổi payload và áp dụng post-processor cho request.
        String converted = operations.convertSendAndReceive(
                requests,
                "Minh",
                Map.of("correlationId", "req-43"),
                String.class,
                message -> MessageBuilder.fromMessage(message)
                        .setHeader("requestVersion", 1)
                        .build());

        // Handler cố ý không trả lời; template hết receive timeout và trả null.
        String noReply = operations.convertSendAndReceive(
                requests, "no-reply", String.class);

        System.out.println("reply payload: "
                + (reply == null ? "<timeout>" : reply.getPayload()));
        System.out.println("reply correlationId: "
                + (reply == null ? null : reply.getHeaders().get("correlationId")));
        System.out.println("converted reply with post-processor: " + converted);
        System.out.println("no reply result: " + noReply);
    }
}
```

Tạo `pom.xml` ở thư mục gốc của project Maven:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>request-reply-operations-demo</artifactId>
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
                    <mainClass>RequestReplyOperationsDemo</mainClass>
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
reply payload: Hello, Lan
reply correlationId: req-42
converted reply with post-processor: v1: Hello, Minh
no reply result: null
```

Trong ví dụ:

- Lần gọi đầu dùng `sendAndReceive`, vì vậy caller nhận cả reply message và đọc được header `correlationId`.
- Lần gọi thứ hai dùng `convertSendAndReceive`; payload `String` được chuyển đổi qua message converter. Header `requestVersion` được thêm bởi post-processor và handler dùng nó để tạo nội dung reply.
- Lần gọi cuối không nhận reply. Với receive timeout 200 ms, kết quả là `null`.

## 5. Cấu hình timeout và xử lý lỗi

`MessageRequestReplyOperations` mô tả các thao tác request-reply, nhưng không khai báo tham số timeout trên từng method. Timeout được cấu hình bởi implementation cụ thể.

Với `GenericMessagingTemplate`:

```java
GenericMessagingTemplate template = new GenericMessagingTemplate();
template.setSendTimeout(500);
template.setReceiveTimeout(2_000);
```

Hai giá trị tính bằng milliseconds:

- **Send timeout:** giới hạn thời gian chờ khi gửi request đến destination/channel.
- **Receive timeout:** giới hạn thời gian chờ reply sau khi request được gửi.

Với request-reply, receive timeout hữu hạn giúp caller không chờ vô thời hạn nếu handler không gửi reply, reply bị thất lạc hoặc luồng xử lý gặp lỗi. Các phương thức `sendAndReceive` và `convertSendAndReceive` có thể trả về `null` khi không nhận được reply, ví dụ do timeout. Hãy kiểm tra `null` trước khi dùng payload.

Các thao tác có thể ném `MessagingException` hoặc lớp con khi có lỗi messaging. Cần phân biệt:

- Lỗi không gửi được request.
- Handler xử lý request thất bại.
- Không nhận được reply trước timeout.
- Reply đến sau khi caller đã timeout.

Với `GenericMessagingTemplate`, reply đến muộn được ghi log ở mức WARN theo mặc định. Có thể bật `setThrowExceptionOnLateReply(true)` để template ném `MessageDeliveryException` khi reply channel không còn được caller chờ nhận.

Không nên retry mọi lỗi một cách mù quáng. Nếu request có thể đã được xử lý trước khi response bị mất, retry có thể chạy nghiệp vụ hai lần. Dùng request ID/correlation ID để theo dõi và idempotency key để bảo vệ thao tác có tác động như tạo đơn, trừ tiền hoặc cập nhật trạng thái.

## 6. Headers, correlation và MessagePostProcessor

### Headers của request

Overload có `Map<String, Object>` cho phép truyền metadata:

```java
String reply = operations.convertSendAndReceive(
        requests,
        "Lan",
        Map.of(
                "correlationId", "req-100",
                "tenantId", "tenant-a"
        ),
        String.class);
```

Các header có thể dùng để định tuyến, kiểm tra quyền, phân vùng dữ liệu hoặc quan sát luồng xử lý. Chỉ truyền những header mà destination và handler hiểu; không nên sao chép toàn bộ metadata của một message khác nếu chúng không còn phù hợp.

### MessagePostProcessor

Post-processor nhận request message đã được tạo và trả về message sau khi chỉnh sửa:

```java
String reply = operations.convertSendAndReceive(
        requests,
        "Lan",
        String.class,
        message -> MessageBuilder.fromMessage(message)
                .setHeader("correlationId", "req-101")
                .setHeader("schemaVersion", 2)
                .build());
```

Có thể dùng nó để chuẩn hóa metadata, thêm correlation ID hoặc áp dụng thông tin theo từng lần gọi. Nếu cần thay payload, post-processor cũng có thể tạo message mới với payload mới; tuy nhiên hãy giữ đúng kiểu payload mà handler mong đợi.

### Correlation ID và Message ID

`MessageHeaders.ID` định danh một message instance. Correlation ID liên kết request với reply hoặc với nhiều message trong cùng một nghiệp vụ. Hai khái niệm này có mục đích khác nhau:

- ID của request và ID của reply có thể khác nhau.
- Reply nên mang correlation ID tương ứng request nếu transport/template không tự quản lý correlation theo cách khác.
- Không dùng message ID như một ID nghiệp vụ xuyên suốt nhiều bước.
- Với broker từ xa, adapter có thể ánh xạ correlation ID sang thuộc tính riêng của transport.

## 7. Destination và implementation

`MessageRequestReplyOperations<D>` không khóa ứng dụng vào một loại destination. Kiểu `D` và implementation quyết định cách tìm destination, gửi request và nhận reply.

| Implementation/contract | Destination | Ghi chú |
| --- | --- | --- |
| `GenericMessagingTemplate` | `MessageChannel` | Dùng cho Spring Messaging channel |
| `DestinationResolvingMessageRequestReplyOperations` | Tên destination dạng `String` | Bổ sung khả năng phân giải tên thành destination |
| `JmsMessagingTemplate` | JMS `Destination` hoặc tên destination | Tích hợp với JMS request-reply và quy tắc reply/correlation của JMS |

Khi dùng `GenericMessagingTemplate`, có thể cấu hình default destination hoặc truyền `MessageChannel` cụ thể cho từng lời gọi. Nếu dùng tên destination, template cần một `DestinationResolver` hoặc cơ chế phân giải tương ứng.

Với JMS, template và provider xử lý các chi tiết reply-to/correlation theo quy tắc JMS. Không giả định cơ chế header `MessageHeaders.REPLY_CHANNEL` nội bộ của `GenericMessagingTemplate` giống hệt cơ chế của broker.

## 8. Khi nào nên dùng request-reply?

Request-reply phù hợp khi caller cần kết quả để tiếp tục quyết định, ví dụ:

- Tra cứu trạng thái hoặc thông tin của một thực thể.
- Kiểm tra điều kiện nghiệp vụ trước khi thực hiện bước tiếp theo.
- Yêu cầu một dịch vụ tính toán và trả kết quả trong thời gian ngắn.
- Gửi command cần acknowledgement hoặc kết quả có cấu trúc.

Không nên giữ caller chờ một công việc kéo dài nhiều phút. Trong trường hợp đó, thường nên gửi command one-way, nhận job ID, rồi theo dõi trạng thái bằng event hoặc API truy vấn. Điều này tránh giữ thread và connection trong thời gian dài.

Request-reply qua message cũng không tự bảo đảm exactly-once. Hệ thống vẫn cần xác định timeout, retry, duplicate handling, correlation và cách phục hồi khi caller không nhận được response dù handler đã hoàn tất.

## 9. Lỗi thường gặp

1. **Khởi tạo trực tiếp `MessageRequestReplyOperations`.** Đây là interface; hãy dùng một implementation như `GenericMessagingTemplate`.
2. **Nhầm `sendAndReceive` với `convertSendAndReceive`.** Một API trả toàn bộ reply message; API kia trả payload đã chuyển đổi sang kiểu đích.
3. **Quên handler phải gửi reply.** Việc handler nhận request không tự tạo response.
4. **Không cấu hình receive timeout.** Caller có thể bị chờ lâu hoặc vô hạn tùy template.
5. **Không xử lý `null`.** Không có reply trước timeout là kết quả có thể xảy ra.
6. **Đặt sai correlation ID.** Response có thể khó ghép với request, nhất là khi có nhiều request đồng thời.
7. **Dùng sai kiểu destination `D`.** `GenericMessagingTemplate` làm việc với `MessageChannel`; JMS template dùng destination của JMS.
8. **Cho rằng MessagePostProcessor xử lý reply.** Nó được áp dụng cho request message trước khi gửi.
9. **Retry mà không chống trùng.** Request có thể đã được xử lý dù caller không nhận được reply.

## 10. Checklist triển khai

- Chọn đúng implementation và kiểu destination.
- Dùng `sendAndReceive` nếu cần cả payload lẫn headers của reply.
- Dùng `convertSendAndReceive` nếu cần chuyển đổi payload request/reply.
- Chỉ truyền những headers cần thiết; đặt correlation ID rõ ràng.
- Dùng `MessagePostProcessor` cho metadata cần thêm sau bước chuyển đổi request.
- Cấu hình send timeout và receive timeout phù hợp với SLA.
- Xử lý `null`, `MessagingException`, reply muộn và lỗi handler.
- Thiết kế retry có giới hạn và idempotency cho command có tác động nghiệp vụ.
- Dùng one-way + job ID/trạng thái cho công việc dài.

## 11. Tài liệu tham khảo

- [Spring Framework – MessageRequestReplyOperations Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/MessageRequestReplyOperations.html)
- [Spring Framework – GenericMessagingTemplate Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/GenericMessagingTemplate.html)
- [Spring Framework – DestinationResolvingMessageRequestReplyOperations Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/DestinationResolvingMessageRequestReplyOperations.html)
- [Spring Framework – MessagePostProcessor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/MessagePostProcessor.html)
