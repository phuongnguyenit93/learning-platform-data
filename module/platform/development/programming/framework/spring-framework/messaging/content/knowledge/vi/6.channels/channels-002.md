# Ý nghĩa giá trị trả về và thời gian chờ khi gửi message trong Spring Messaging

Trong Spring Messaging, thao tác gửi message qua `MessageChannel` trả về một giá trị `boolean`. Giá trị này cho biết channel có chấp nhận message hay không theo cơ chế gửi của nó. Khi channel có thể phải chờ để tiếp nhận message, overload `send(message, timeout)` cho phép giới hạn thời gian chờ.

Hai điểm cần nhớ ngay từ đầu:

- `true` nghĩa là message đã được gửi/chấp nhận bởi channel.
- `false` nghĩa là message không được gửi vì một lý do không nghiêm trọng, ví dụ timeout hoặc thao tác gửi bị interrupt. Lỗi không thể phục hồi có thể được ném thành runtime exception.

Giá trị trả về không phải là xác nhận rằng consumer đã hoàn thành xử lý nghiệp vụ hoặc dữ liệu đã được lưu bền vững. Điều đó phụ thuộc vào loại channel và transport.

## 1. Hai phương thức send của MessageChannel

Interface `org.springframework.messaging.MessageChannel` định nghĩa hai phương thức:

```java
boolean send(Message<?> message);

boolean send(Message<?> message, long timeout);
```

### `send(message)`

Đây là cách gửi đơn giản. Phương thức mặc định sử dụng timeout không giới hạn. Tùy implementation, lời gọi có thể trả về ngay hoặc block vô thời hạn khi channel chưa thể nhận message.

```java
boolean sent = channel.send(message);
```

Không nên dùng overload này một cách vô thức trên một channel có thể bị đầy hoặc có cơ chế gửi chặn. Nếu consumer dừng xử lý, producer có thể bị giữ lại lâu hơn dự kiến.

### `send(message, timeout)`

Overload này cho phép đặt giới hạn chờ:

```java
boolean sent = channel.send(message, 500);
```

Tham số `timeout` tính bằng milliseconds. Lời gọi chờ cho đến khi channel chấp nhận message hoặc thời hạn kết thúc.

| Tham số | Ý nghĩa |
| --- | --- |
| `0` | Thử gửi ngay, không chờ thêm trong các implementation queue phổ biến |
| `500` | Chờ tối đa khoảng 500 milliseconds |
| `2_000` | Chờ tối đa khoảng 2 giây |
| `MessageChannel.INDEFINITE_TIMEOUT` | Không đặt giới hạn thời gian chờ |

Hãy dùng hằng số `MessageChannel.INDEFINITE_TIMEOUT` khi thật sự muốn chờ vô thời hạn, thay vì ghi trực tiếp một số âm trong code. Các implementation có thể xử lý timeout theo đặc tính riêng, nên hãy kiểm tra contract của channel đang dùng.

## 2. Ý nghĩa của true, false và exception

| Kết quả | Ý nghĩa | Cách xử lý |
| --- | --- | --- |
| `true` | Channel chấp nhận message theo cơ chế gửi của nó | Tiếp tục luồng producer; nếu cần biết kết quả nghiệp vụ, dùng acknowledgement hoặc trạng thái riêng |
| `false` | Channel không gửi được vì lý do không nghiêm trọng, chẳng hạn hết thời gian chờ hoặc thread gửi bị interrupt | Ghi nhận tình huống, quyết định retry hoặc chuyển sang xử lý lỗi |
| Runtime exception | Có lỗi không thể phục hồi hoặc lỗi trong quá trình gửi/dispatch | Bắt lỗi phù hợp, ghi log và chuyển sang luồng xử lý lỗi |

Ví dụ kiểm tra kết quả:

```java
boolean sent = channel.send(message, 500);

if (sent) {
    System.out.println("Channel accepted the message");
}
else {
    System.out.println("Message was not accepted");
}
```

Không nên diễn giải `true` thành “message đã được xử lý xong”. Ví dụ, một channel có thể đưa message vào executor rồi trả về trước khi handler bắt đầu chạy. Với broker từ xa, kết quả còn phụ thuộc ý nghĩa acknowledgement mà adapter hoặc broker cung cấp.

Nếu `send` trả về `false`, producer không nên âm thầm bỏ qua kết quả khi message quan trọng. Có thể retry có giới hạn, ghi vào outbox hoặc chuyển sang dead-letter/error flow. Khi retry một message có tác động nghiệp vụ, cần có idempotency key hoặc cơ chế chống xử lý trùng.

## 3. Timeout giới hạn thời gian chờ gửi, không giới hạn thời gian xử lý

Send timeout đo khoảng thời gian producer sẵn sàng chờ channel tiếp nhận message. Nó không phải thời gian tối đa mà consumer được phép xử lý message.

Ví dụ với channel có buffer hữu hạn:

1. Producer gửi message đầu tiên; buffer còn chỗ nên message được nhận ngay.
2. Producer gửi message thứ hai khi buffer đã đầy.
3. Producer có thể chờ consumer lấy bớt message để giải phóng chỗ.
4. Nếu có chỗ trước khi timeout kết thúc, send trả về `true`.
5. Nếu hết timeout mà vẫn không có chỗ, send trả về `false`.

Nếu consumer nhận message nhưng xử lý nghiệp vụ mất 30 giây, send timeout 500 ms không tự dừng consumer sau 500 ms. Muốn giới hạn thời gian xử lý cần timeout riêng ở tầng handler, service hoặc transport.

Cũng cần phân biệt send timeout với receive timeout:

- **Send timeout:** producer chờ channel nhận message.
- **Receive timeout:** consumer hoặc request-reply caller chờ message/reply đến.

`PollableChannel.receive(timeout)` là thao tác nhận có timeout riêng. Khi không có message hoặc thao tác nhận bị interrupt, phương thức có thể trả về `null`.

## 4. Thời gian chờ phụ thuộc loại channel

`MessageChannel` chỉ định nghĩa hợp đồng gửi. Nó không bắt buộc mọi channel phải buffer message hoặc block theo cùng một cách.

### SubscribableChannel

`SubscribableChannel` gửi message trực tiếp đến các `MessageHandler` đã đăng ký. Nó không cung cấp thao tác `receive()` để producer hoặc consumer tự polling.

`ExecutorSubscribableChannel` là implementation của Spring Framework:

- Constructor không truyền executor dispatch message trên thread của caller.
- Constructor có executor dispatch message thông qua executor đã cung cấp.

Khi dùng executor, việc channel chấp nhận/dispatch message không có nghĩa handler đã xử lý xong. Nếu executor bận hoặc từ chối task, hành vi cụ thể phụ thuộc executor và implementation; hãy quan sát exception, log và cấu hình hàng đợi của executor.

### PollableChannel

`PollableChannel` mở rộng `MessageChannel` và cung cấp `receive()` cùng `receive(timeout)` để consumer chủ động lấy message. Interface này mô tả khả năng polling; khả năng buffer, dung lượng và chính sách chờ phụ thuộc implementation cụ thể.

Trong hệ sinh thái Spring, một số channel có buffer được cung cấp bởi Spring Integration. Không nên nhầm các implementation đó với API cốt lõi của riêng module `spring-messaging`.

### Kết luận khi chọn channel

- Với channel dispatch trực tiếp, send có thể gắn chặt với thời gian dispatch handler trên thread gửi.
- Với channel dispatch qua executor, send có thể kết thúc trước khi handler hoàn tất.
- Với channel có buffer hữu hạn, send có thể phải chờ chỗ trống.
- Với adapter broker, ý nghĩa “đã gửi” phụ thuộc contract của adapter và acknowledgement của transport.

Vì thế, hãy đọc tài liệu của implementation đang dùng thay vì suy ra thời gian chờ chỉ từ tên `MessageChannel`.

## 5. Ví dụ Java 17+: channel có buffer giới hạn

Ví dụ sau tự triển khai một `MessageChannel` tối giản bằng `ArrayBlockingQueue` của JDK. Đây là adapter minh họa contract của `MessageChannel`, không phải một channel dựng sẵn của Spring. Buffer có dung lượng một message để dễ quan sát timeout.

Tạo file `src/main/java/SendTimeoutDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public class SendTimeoutDemo {

    private static MessageChannel backedBy(BlockingQueue<Message<?>> queue) {
        return (message, timeout) -> {
            try {
                if (timeout == MessageChannel.INDEFINITE_TIMEOUT) {
                    queue.put(message);
                    return true;
                }
                if (timeout < 0) {
                    throw new IllegalArgumentException(
                            "Unsupported timeout: " + timeout);
                }
                return queue.offer(message, timeout, TimeUnit.MILLISECONDS);
            }
            catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return false;
            }
        };
    }

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<Message<?>> buffer = new ArrayBlockingQueue<>(1);
        MessageChannel channel = backedBy(buffer);

        Message<String> first =
                MessageBuilder.withPayload("event-1").build();
        Message<String> second =
                MessageBuilder.withPayload("event-2").build();

        System.out.println("first accepted: " + channel.send(first, 100));
        System.out.println("second accepted while full: "
                + channel.send(second, 100));
        System.out.println("received: " + buffer.take().getPayload());
        System.out.println("second accepted after capacity freed: "
                + channel.send(second, 100));
        System.out.println("received: " + buffer.take().getPayload());
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
    <artifactId>send-timeout-demo</artifactId>
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
                    <mainClass>SendTimeoutDemo</mainClass>
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
first accepted: true
second accepted while full: false
received: event-1
second accepted after capacity freed: true
received: event-2
```

Diễn giải:

- Message đầu tiên được đưa vào buffer đang trống nên kết quả là `true`.
- Message thứ hai được gửi khi buffer đầy. Không có consumer lấy message trong 100 ms tiếp theo nên kết quả là `false`.
- Sau khi lấy `event-1`, buffer có chỗ trống; gửi lại `event-2` thành công.
- `buffer.take()` là thao tác nhận của hàng đợi JDK trong adapter minh họa. Với channel thực tế, consumer sẽ nhận theo API của channel đó.

## 6. Cấu hình send timeout qua GenericMessagingTemplate

Nếu gửi thông qua `GenericMessagingTemplate`, có thể đặt timeout mặc định cho các thao tác gửi:

```java
GenericMessagingTemplate template = new GenericMessagingTemplate();
template.setSendTimeout(500);

template.send(channel, message);
```

`setSendTimeout` nhận giá trị milliseconds. Template dùng giá trị đã cấu hình khi gửi; cấu hình riêng cho từng message có thể ghi đè nếu ứng dụng bật cơ chế send-timeout header của template.

Điểm cần phân biệt:

- Gọi trực tiếp `channel.send(message, 500)` truyền timeout ngay tại lần gọi.
- Gọi `template.setSendTimeout(500)` đặt chính sách timeout mặc định cho các lần gửi qua template đó.
- Cấu hình timeout ở template không tự thay đổi cấu hình của channel khi những thành phần khác gọi trực tiếp channel.

Nên đặt timeout dựa trên latency mục tiêu và khả năng chịu tải của hệ thống. Timeout quá ngắn có thể tạo nhiều lần gửi thất bại khi hệ thống chỉ đang quá tải tạm thời; timeout quá dài có thể giữ thread producer và làm tăng độ trễ dây chuyền.

## 7. Xử lý kết quả gửi trong ứng dụng

Một cách xử lý rõ ràng là tách ba trường hợp: được chấp nhận, không được chấp nhận và exception.

```java
try {
    boolean accepted = channel.send(message, 500);

    if (!accepted) {
        // Ghi nhận thất bại có thể phục hồi:
        // retry có giới hạn, lưu outbox hoặc chuyển sang error flow.
    }
}
catch (RuntimeException ex) {
    // Lỗi gửi không thể phục hồi hoặc lỗi dispatch:
    // log đầy đủ message ID/correlation ID và xử lý theo chính sách ứng dụng.
    throw ex;
}
```

Nếu thread bị interrupt trong lúc chờ gửi, implementation có thể trả về `false`. Với code tự triển khai channel, hãy khôi phục interrupt flag bằng `Thread.currentThread().interrupt()` trước khi trả về. Không nên nuốt interrupt vì nó có thể là tín hiệu shutdown hoặc hủy công việc từ tầng quản lý thread.

Với message quan trọng, chính sách retry cần xác định:

- Số lần retry tối đa và khoảng nghỉ giữa các lần.
- Loại lỗi nào có thể retry.
- Cách chống xử lý trùng bằng message key hoặc idempotency key.
- Nơi lưu message khi channel liên tục từ chối.
- Cách cảnh báo khi queue hoặc executor thường xuyên đầy.

Không retry vô hạn trong vòng lặp nóng. Cách đó có thể làm hệ thống quá tải nặng hơn.

## 8. Những nhầm lẫn thường gặp

1. **Coi `true` là consumer đã xử lý xong.** Nó chỉ xác nhận kết quả gửi theo contract của channel.
2. **Coi `false` luôn là timeout.** Đây cũng có thể là một lý do không nghiêm trọng khác hoặc thao tác gửi bị interrupt.
3. **Nghĩ `send(message)` luôn trả về ngay.** Phương thức có thể block vô thời hạn tùy implementation.
4. **Dùng timeout như thời gian xử lý handler.** Send timeout chỉ giới hạn việc producer chờ channel nhận message.
5. **Giả định mọi channel đều có buffer.** SubscribableChannel dispatch đến subscriber; PollableChannel cho phép consumer polling; chi tiết lưu trữ do implementation quyết định.
6. **Nghĩ timeout 500 ms bảo đảm toàn bộ thao tác gửi kết thúc chính xác sau 500 ms.** Đây là giới hạn chờ theo contract; scheduling và xử lý nội bộ có thể khiến thời gian thực tế chênh lệch.
7. **Bỏ qua runtime exception vì đã kiểm tra boolean.** Exception vẫn có thể xảy ra với lỗi không thể phục hồi.
8. **Retry message không có idempotency.** Một lỗi ở tầng transport có thể khiến producer không chắc message đã được tiếp nhận đến đâu; thiết kế chống trùng ở tầng nghiệp vụ là cần thiết.

## 9. Checklist thiết kế

- Xác định loại channel và cách channel tiếp nhận message.
- Chọn timeout hữu hạn khi producer không thể chờ vô thời hạn.
- Dùng milliseconds rõ ràng và ưu tiên hằng số `MessageChannel.INDEFINITE_TIMEOUT` cho trường hợp không giới hạn.
- Xử lý đầy đủ `true`, `false` và runtime exception.
- Không suy luận consumer đã hoàn tất chỉ từ kết quả `send`.
- Tách send timeout khỏi receive timeout và processing timeout.
- Theo dõi queue depth, executor rejection, send latency, số lần timeout và tỷ lệ retry.
- Thiết kế retry có giới hạn, backoff và idempotency cho message quan trọng.

## 10. Tài liệu tham khảo

- [Spring Framework – MessageChannel Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageChannel.html)
- [Spring Framework – AbstractMessageChannel Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/AbstractMessageChannel.html)
- [Spring Framework – ExecutorSubscribableChannel Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ExecutorSubscribableChannel.html)
- [Spring Framework – PollableChannel Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/PollableChannel.html)
- [Spring Framework – GenericMessagingTemplate Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/GenericMessagingTemplate.html)
