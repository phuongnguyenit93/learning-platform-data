# Gửi một chiều và gửi yêu cầu chờ phản hồi trong Spring Messaging

Trong Spring Messaging, một message được gửi qua một channel để thành phần khác xử lý. Có hai hợp đồng trao đổi thường gặp:

- **Gửi một chiều (one-way):** gửi message và không chờ kết quả nghiệp vụ trả về.
- **Gửi yêu cầu chờ phản hồi (request-reply):** gửi request, cung cấp đường trả lời và chờ reply tương ứng.

Phần chính dưới đây dùng API của module `spring-messaging` trong Spring Framework: `MessageChannel`, `MessageHeaders`, `MessageBuilder` và `GenericMessagingTemplate`. Spring Integration có thêm gateway và endpoint ở tầng cao hơn; phần cuối phân biệt hai module để tránh nhầm API.

## 1. Các thành phần liên quan

Một message trong Spring có hai phần:

- **Payload:** dữ liệu chính, ví dụ `OrderCreated`, `String` hoặc một DTO.
- **Headers:** metadata như message ID, timestamp, content type, correlation ID, reply channel hoặc error channel.

Các kiểu API cốt lõi:

| Thành phần | Vai trò |
| --- | --- |
| `Message<T>` | Bao gói payload và headers |
| `MessageChannel` | Điểm gửi message đến một luồng xử lý |
| `MessageHandler` | Nhận và xử lý message |
| `SubscribableChannel` | Channel gọi các handler đã đăng ký |
| `PollableChannel` | Channel có thể được đọc bằng `receive()` |
| `GenericMessagingTemplate` | Cung cấp thao tác gửi, nhận và request-reply trên `MessageChannel` |

`MessageChannel` định nghĩa thao tác `send`; bản thân interface này không định nghĩa thao tác nhận reply. Việc chờ reply cần một cơ chế nhận riêng, thường được template quản lý.

## 2. Gửi một chiều

### Cách hoạt động

Luồng cơ bản:

1. Thành phần gửi tạo message.
2. Thành phần gửi gọi `MessageChannel.send(message)`.
3. Channel chuyển message đến handler hoặc hạ tầng tiếp nhận.
4. Thành phần gửi tiếp tục mà không đợi một reply nghiệp vụ.

Ví dụ:

```java
Message<String> event = MessageBuilder
        .withPayload("order-created:42")
        .build();

boolean accepted = eventChannel.send(event);
```

Giá trị trả về của `send` là `boolean`:

- `true`: channel đã chấp nhận message theo cơ chế của channel.
- `false`: message không được gửi thành công vì một lý do không nghiêm trọng, chẳng hạn channel không thể tiếp nhận.
- Một lỗi không thể phục hồi có thể được ném thành runtime exception.

**Không được xem `true` là xác nhận nghiệp vụ đã hoàn tất.** Nó không tự chứng minh rằng handler đã xử lý xong, dữ liệu đã được lưu bền vững hoặc hệ thống bên ngoài đã hoàn thành công việc. Mức đảm bảo phụ thuộc channel và transport cụ thể.

### Ví dụ chạy được

Ví dụ dùng `ExecutorSubscribableChannel` không truyền executor. Với constructor này, handler được gọi trên thread gửi message.

```java
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class OneWayDemo {

    public static void main(String[] args) {
        ExecutorSubscribableChannel events = new ExecutorSubscribableChannel();

        events.subscribe(message ->
                System.out.println("received: " + message.getPayload()));

        boolean accepted = events.send(
                MessageBuilder.withPayload("order-created:42").build());

        System.out.println("accepted: " + accepted);
    }
}
```

Kết quả:

```text
received: order-created:42
accepted: true
```

Trong ví dụ này, handler chạy đồng bộ nên dòng `received` xuất hiện trước dòng `accepted`. Điều đó không biến hợp đồng thành request-reply: handler không gửi kết quả về cho bên gọi.

Để chạy ví dụ, dùng Java 17+ và Maven. Tạo file `src/main/java/MessagingExchangeDemo.java` chứa ví dụ request-reply ở phần kế tiếp, sau đó dùng cấu hình tối thiểu sau trong `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>messaging-demo</artifactId>
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
                    <mainClass>MessagingExchangeDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Lệnh chạy từ thư mục chứa `pom.xml`:

```bash
mvn -q clean compile exec:java
```

Nếu muốn chạy riêng ví dụ `OneWayDemo`, đổi `mainClass` thành `OneWayDemo`.

Nếu truyền một `Executor` vào `ExecutorSubscribableChannel`, channel có thể dispatch handler qua executor. Khi đó handler có thể tiếp tục sau khi lời gọi gửi đã trả về. Vì vậy cần phân biệt:

- **One-way** mô tả việc bên gọi không chờ reply nghiệp vụ.
- **Synchronous/asynchronous** mô tả thời điểm và thread thực thi handler.

Hai khái niệm này độc lập. Một thao tác one-way vẫn có thể gọi handler đồng bộ.

### Khi nào nên dùng?

Dùng one-way khi bên gửi chỉ cần phát thông tin hoặc yêu cầu xử lý, ví dụ:

- Phát sự kiện đơn hàng vừa được tạo.
- Gửi thông báo hoặc telemetry.
- Ghi nhận một hoạt động để hệ thống khác xử lý.
- Khởi chạy một tác vụ nền mà bên gọi không cần kết quả ngay.

Nếu cần biết công việc đã hoàn tất hay thất bại, hãy thiết kế thêm một sự kiện trạng thái, callback hoặc API truy vấn trạng thái. Đừng suy luận kết quả đó từ boolean của `send`.

## 3. Gửi yêu cầu và chờ phản hồi

### Cách hoạt động

Request-reply bổ sung một đường trả lời cho message:

1. Bên gọi tạo request và gửi đến channel.
2. Bên gọi chờ reply trên reply channel.
3. Handler xử lý request và gửi reply về đúng reply channel.
4. Template nhận reply và trả message hoặc payload cho bên gọi.

Trong Spring Framework, `GenericMessagingTemplate.sendAndReceive(channel, request)` thực hiện trao đổi này. Template tạo một reply channel tạm thời cho lần gọi, đặt channel đó vào header `MessageHeaders.REPLY_CHANNEL`, gửi request rồi chờ nhận reply. Mỗi lần gọi có reply channel riêng nên các request đồng thời không phải dùng chung một hàng đợi reply.

Handler ở tầng `MessageHandler` cần chủ động gửi reply đến channel trong header. Interface `MessageHandler.handleMessage` không tự biến giá trị trả về của một method thành reply.

### Ví dụ chạy được

Tạo file `src/main/java/MessagingExchangeDemo.java`:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.core.GenericMessagingTemplate;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class MessagingExchangeDemo {

    public static void main(String[] args) {
        // One-way: gửi sự kiện, không chờ kết quả nghiệp vụ.
        ExecutorSubscribableChannel events = new ExecutorSubscribableChannel();
        events.subscribe(message ->
                System.out.println("event received: " + message.getPayload()));

        boolean accepted = events.send(
                MessageBuilder.withPayload("order-created:42").build());
        System.out.println("event accepted: " + accepted);

        // Request-reply: handler gửi kết quả về replyChannel của request.
        ExecutorSubscribableChannel requests = new ExecutorSubscribableChannel();
        requests.subscribe(request -> {
            String customer = (String) request.getPayload();
            Object replyTarget =
                    request.getHeaders().get(MessageHeaders.REPLY_CHANNEL);

            if (replyTarget instanceof MessageChannel replyChannel) {
                replyChannel.send(
                        MessageBuilder.withPayload("Hello, " + customer).build());
            }
        });

        GenericMessagingTemplate template = new GenericMessagingTemplate();
        template.setReceiveTimeout(2_000);

        Message<?> reply = template.sendAndReceive(
                requests,
                MessageBuilder.withPayload("Lan").build());

        System.out.println("request reply: "
                + (reply == null ? "<timeout>" : reply.getPayload()));
    }
}
```

Kết quả:

```text
event received: order-created:42
event accepted: true
request reply: Hello, Lan
```

Ở phần request-reply, template tự tạo reply channel tạm thời. Handler đọc header `MessageHeaders.REPLY_CHANNEL`, ép kiểu khi header chứa một `MessageChannel`, rồi gửi message trả lời vào channel đó. Nếu handler không gửi reply, bên gọi sẽ chờ đến khi hết receive timeout.

### `sendAndReceive` và `convertSendAndReceive`

| API | Đầu vào | Kết quả |
| --- | --- | --- |
| `sendAndReceive(channel, request)` | Một `Message<?>` | Reply dưới dạng `Message<?>` |
| `convertSendAndReceive(...)` | Payload, headers tùy chọn và kiểu đích | Payload reply được chuyển đổi sang kiểu yêu cầu |

Dùng `sendAndReceive` khi cần giữ nguyên message và headers của reply. Dùng `convertSendAndReceive` khi muốn template chuyển đổi payload qua `MessageConverter` và nhận về một kiểu Java cụ thể.

Các phương thức request-reply có thể trả về `null` khi không nhận được reply, ví dụ khi timeout. Vì vậy hãy xử lý trường hợp không có kết quả thay vì mặc định reply luôn tồn tại.

## 4. Timeout và lỗi

Có hai loại timeout cần phân biệt:

| Timeout | Ý nghĩa |
| --- | --- |
| Send timeout | Thời gian tối đa chờ channel chấp nhận message khi thao tác gửi có thể bị chặn |
| Receive timeout | Thời gian tối đa chờ reply sau khi request được gửi |

Với `GenericMessagingTemplate`, có thể cấu hình:

```java
GenericMessagingTemplate template = new GenericMessagingTemplate();
template.setSendTimeout(1_000);
template.setReceiveTimeout(2_000);
```

Các giá trị timeout tính bằng milliseconds. Trong implementation hiện tại, giá trị mặc định của cả send timeout và receive timeout là `-1`, tức không đặt giới hạn chờ. Với request-reply, nên chủ động đặt receive timeout hữu hạn để thread gọi không bị chờ vô thời hạn khi handler bị lỗi, không tạo reply hoặc message bị chuyển hướng.

Khi hết receive timeout:

- `sendAndReceive` trả về `null`.
- `convertSendAndReceive` cũng có thể trả về `null`.
- Một reply đến muộn không thể được coi là kết quả của lời gọi đã kết thúc. Theo mặc định, template ghi cảnh báo cho reply muộn; có thể bật `setThrowExceptionOnLateReply(true)` để ném `MessageDeliveryException`.

Khi gửi không thành công, template có thể ném `MessageDeliveryException`. Các lỗi messaging khác thường được biểu diễn bằng `MessagingException` hoặc lớp con. Hãy phân biệt lỗi gửi, lỗi xử lý và timeout chờ reply vì cách khắc phục khác nhau.

Với channel chạy handler trên thread gọi, lỗi xử lý có thể xuất hiện ngay trong luồng gửi. Với channel dispatch qua executor hoặc broker từ xa, việc gửi thành công không đồng nghĩa lỗi xử lý sẽ được ném về thread gửi. Khi đó cần thiết kế error channel, dead-letter handling, logging hoặc sự kiện lỗi phù hợp với transport.

## 5. Correlation và reply channel

Trong request-reply, hệ thống phải ghép reply với đúng request:

- Với `GenericMessagingTemplate` và channel nội bộ, template tạo reply channel tạm thời cho từng lần gọi.
- Với broker hoặc transport từ xa, reply channel có thể được ánh xạ thành địa chỉ reply của transport. Hệ thống thường cần correlation ID hoặc cơ chế tương đương để ghép response với request.
- Không nên để nhiều request đồng thời cùng chờ trên một reply channel dùng chung nếu không có cơ chế phân biệt và định tuyến reply chính xác.

Nếu tự triển khai giao thức request-reply, hãy xác định rõ request ID, correlation ID, reply destination, thời hạn phản hồi và cách xử lý response đến muộn. Khi retry request, cân nhắc idempotency key để tránh xử lý nghiệp vụ trùng lặp.

## 6. Chọn mô hình trao đổi

| Nhu cầu | Mô hình phù hợp | Lý do |
| --- | --- | --- |
| Phát sự kiện, không cần kết quả ngay | One-way | Bên gửi không phải giữ luồng để chờ reply |
| Gọi một xử lý và cần kết quả để quyết định bước tiếp theo | Request-reply | Kết quả được trả về cho đúng bên gọi |
| Công việc kéo dài, bên gọi không nên chờ | One-way + job ID/trạng thái hoặc xử lý bất đồng bộ | Tránh giữ thread trong thời gian dài |
| Cần xác nhận đã tiếp nhận | One-way với acknowledgement được thiết kế rõ | Phân biệt xác nhận tiếp nhận với kết quả nghiệp vụ |

Request-reply phù hợp với tra cứu, kiểm tra hoặc tính toán cần kết quả ngay. Với tác vụ kéo dài, thường nên trả về mã công việc sau khi tiếp nhận và phát sự kiện hoàn tất/thất bại, hoặc dùng một API bất đồng bộ có hợp đồng rõ ràng.

## 7. Phân biệt Spring Framework và Spring Integration

Không nên nhầm các API ở hai module:

- **Spring Framework – `spring-messaging`:** cung cấp `Message`, `MessageChannel`, `MessageHandler`, `GenericMessagingTemplate` và các thao tác `send`, `sendAndReceive`.
- **Spring Integration – `spring-integration-core`:** bổ sung gateway và endpoint để xây dựng luồng tích hợp. Các annotation như `@MessagingGateway`, `@Gateway` và `@ServiceActivator` thuộc Spring Integration.

Ví dụ gateway của Spring Integration:

```java
@MessagingGateway(defaultRequestChannel = "orders")
public interface OrderGateway {

    // One-way: không yêu cầu gateway trả kết quả nghiệp vụ.
    void publish(OrderCreated event);

    // Request-reply: caller nhận OrderStatus từ flow phía sau.
    OrderStatus findStatus(OrderQuery query);
}
```

Ví dụ này cần dependency Spring Integration và cấu hình gateway/channel tương ứng. Nó không phải API của riêng module `spring-messaging`.

Trong ứng dụng WebSocket/STOMP của Spring Framework, `SimpMessagingTemplate.convertAndSend(destination, payload)` là cách phổ biến để đẩy message đến destination hoặc subscriber. Lời gọi này không chờ từng client gửi kết quả nghiệp vụ về. Nếu cần response cho message từ client, có thể xử lý bằng `@MessageMapping` và định tuyến kết quả bằng `@SendTo` hoặc cơ chế reply tương ứng.

## 8. Lỗi thường gặp

1. **Coi `send() == true` là xử lý nghiệp vụ thành công.** Giá trị này chỉ cho biết channel chấp nhận message theo contract của nó.
2. **Cho rằng one-way luôn bất đồng bộ.** Channel có thể gọi handler ngay trên thread gửi.
3. **Gọi `sendAndReceive` nhưng handler không gửi reply.** Bên gọi sẽ nhận `null` sau timeout hoặc chờ vô hạn nếu không cấu hình timeout.
4. **Gửi reply đến sai channel.** Reply không về được temporary reply channel nên request bị timeout.
5. **Không xử lý `null`.** Timeout hoặc không có reply là tình huống hợp lệ của API.
6. **Nhầm send timeout với receive timeout.** Một timeout giới hạn việc gửi; timeout còn lại giới hạn thời gian chờ reply.
7. **Dùng reply channel chung cho nhiều request mà không correlation.** Reply có thể bị ghép nhầm với request khác.
8. **Dùng method `void` nhưng lại mong nhận kết quả.** Hợp đồng one-way không cung cấp payload reply cho caller.

## 9. Checklist khi triển khai

- Xác định rõ bên gửi có cần kết quả nghiệp vụ hay chỉ cần phát message.
- Chọn channel và transport có đặc tính phù hợp về đồng bộ, bất đồng bộ, lưu trữ và độ tin cậy.
- Với request-reply, xác định reply channel và cách ghép reply với request.
- Đặt send timeout và receive timeout phù hợp với SLA.
- Xử lý `null`, lỗi gửi, lỗi handler và reply đến muộn.
- Với sự kiện có thể retry, thiết kế idempotency và xử lý message trùng.
- Không dùng request-reply đồng bộ cho công việc kéo dài nếu có thể chuyển sang job ID và sự kiện trạng thái.

## 10. Tài liệu tham khảo

- [Spring Framework – MessageChannel Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageChannel.html)
- [Spring Framework – GenericMessagingTemplate Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/GenericMessagingTemplate.html)
- [Spring Framework – ExecutorSubscribableChannel Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ExecutorSubscribableChannel.html)
- [Spring Framework – Sending Messages over WebSocket/STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-send.html)
- [Spring Integration – Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html)
