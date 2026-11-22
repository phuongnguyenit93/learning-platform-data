# preReceive, postReceive và afterReceiveCompletion trên kênh có thao tác nhận

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích ba callback nhận message của `ChannelInterceptor`.
- Xác định loại channel nào hỗ trợ thao tác `receive()` và vì sao receive interceptor chỉ chạy trên `PollableChannel`.
- Dùng `preReceive` để cho phép hoặc chặn một lần nhận.
- Dùng `postReceive` để quan sát, biến đổi hoặc loại message sau khi lấy khỏi channel.
- Dùng `afterReceiveCompletion` để dọn tài nguyên dù receive thành công, không có message hay phát sinh exception.
- Hiểu thứ tự callback khi có nhiều interceptor và vì sao không thể suy ra thứ tự tổng thể giữa send với receive.
- Viết interceptor có thể kiểm thử, không làm mất message ngoài ý muốn và không phụ thuộc vào callback không được gọi.

## 1. Vì sao có receive interceptor?

Spring Messaging định nghĩa `ChannelInterceptor` để quan sát hoặc thay đổi message khi message được gửi vào hoặc nhận ra khỏi một `MessageChannel`.

Các callback phía gửi thường gặp:

- `preSend`: trước khi gửi message vào channel.
- `postSend`: ngay sau thao tác send.
- `afterSendCompletion`: sau khi send kết thúc, kể cả khi có exception, để dọn tài nguyên.

Bài này tập trung vào ba callback phía nhận:

- `preReceive`
- `postReceive`
- `afterReceiveCompletion`

Chúng có ý nghĩa khi consumer chủ động gọi `receive()` trên một channel có khả năng nhận message. Interceptor có thể kiểm soát việc bắt đầu nhận, quan sát message vừa được lấy khỏi channel và thực hiện cleanup khi thao tác nhận kết thúc.

## 2. Chỉ PollableChannel mới có receive()

Trong Spring Messaging, có hai kiểu channel phổ biến:

| Loại | Interface | Cách nhận message |
|---|---|---|
| Pollable | `PollableChannel` | Consumer gọi `receive()` hoặc `receive(timeout)` |
| Subscribable | `SubscribableChannel` | Channel dispatch message tới các `MessageHandler` đã subscribe khi producer gọi `send()` |

Ví dụ channel pollable trong Spring Integration:

- `QueueChannel`
- `PriorityChannel`
- `RendezvousChannel`

Ví dụ channel subscribable:

- `DirectChannel`
- `PublishSubscribeChannel`
- `ExecutorChannel`
- `ExecutorSubscribableChannel`

`SubscribableChannel` không định nghĩa phương thức `receive()`. Consumer đăng ký handler với channel; việc dispatch diễn ra từ phía send. Vì thế, `preReceive`, `postReceive` và `afterReceiveCompletion` không chạy trên các channel subscribable.

Luồng nhận của một PollableChannel:

~~~text
Consumer gọi receive()
        |
        v
    preReceive()
        |
        +-- false --> không lấy message
        |
        +-- true
              |
              v
         channel lấy message
              |
              v
         có message?
              |
              +-- có --> postReceive(message)
              |               |
              |               +-- message mới --> trả cho consumer
              |               |
              |               +-- null --> hủy việc trả message
              |
              +-- không có --> bỏ qua postReceive
              |
              v
    afterReceiveCompletion(...)
              |
              v
       receive() kết thúc
~~~

Sơ đồ mô tả một lần gọi receive đơn lẻ. Khi có nhiều interceptor, thứ tự giữa các callback được thực hiện theo chuỗi interceptor như phần sau.

## 3. preReceive: quyết định có bắt đầu lấy message hay không

Chữ ký:

~~~java
boolean preReceive(MessageChannel channel)
~~~

`preReceive` chạy khi consumer bắt đầu gọi `receive()`, trước khi channel lấy message ra khỏi queue.

- Trả về `true`: cho phép thao tác nhận tiếp tục.
- Trả về `false`: chặn thao tác nhận; channel không thực hiện việc lấy message.
- Có thể ném runtime exception nếu điều kiện trước khi nhận gặp lỗi.

Ví dụ chỉ cho phép nhận trong thời gian hệ thống đang mở:

~~~java
public class ReceiveWindowInterceptor implements ChannelInterceptor {

    private final AtomicBoolean accepting = new AtomicBoolean(true);

    @Override
    public boolean preReceive(MessageChannel channel) {
        return accepting.get();
    }

    public void stopReceiving() {
        accepting.set(false);
    }
}
~~~

Khi `accepting` là `false`, lần gọi `receive()` bị chặn trước khi message được lấy khỏi channel. Message vẫn nằm trong queue để lần nhận sau có thể lấy, nếu channel và consumer còn hoạt động.

### preReceive chưa nhìn thấy message

Callback này chỉ nhận tham số `MessageChannel`, không nhận `Message<?>`. Vì message chưa được lấy ra, `preReceive` phù hợp với các quyết định dựa trên trạng thái channel hoặc trạng thái consumer, ví dụ:

- Tạm dừng nhận trong lúc bảo trì.
- Kiểm tra một feature flag.
- Giới hạn một loại consumer đang được phép poll.
- Thiết lập tài nguyên hoặc context cần thiết cho thao tác nhận.

Không thể dùng `preReceive` để kiểm tra `orderId`, payload hoặc header của message sắp nhận vì callback chưa có message. Nếu cần kiểm tra nội dung, dùng `postReceive` hoặc xử lý trong consumer.

Nếu `preReceive` trả về `false`, `postReceive` không được gọi. `afterReceiveCompletion` của chính interceptor trả về false cũng không được gọi vì interceptor đó chưa hoàn thành bước preReceive thành công. Với nhiều interceptor, các interceptor trước đó đã trả về true vẫn được gọi cleanup theo thứ tự ngược lại.

## 4. postReceive: xử lý message sau khi lấy khỏi channel

Chữ ký:

~~~java
Message<?> postReceive(Message<?> message, MessageChannel channel)
~~~

Callback này chạy sau khi channel đã lấy được message nhưng trước khi message được trả về cho consumer.

Có ba cách xử lý:

1. Trả lại chính message: giữ nguyên dữ liệu.
2. Trả về message mới: biến đổi payload hoặc header trước khi consumer nhận.
3. Trả về `null`: dừng chuỗi interceptor nhận và không trả message đó cho consumer.

Ví dụ bổ sung header cho biết message đã đi qua receive boundary:

~~~java
public class ReceiveMarkingInterceptor implements ChannelInterceptor {

    @Override
    public Message<?> postReceive(
            Message<?> message,
            MessageChannel channel) {

        return MessageBuilder.fromMessage(message)
                .setHeader("receivedByChannel", true)
                .build();
    }
}
~~~

Vì Spring Message và MessageHeaders được thiết kế theo hướng bất biến, không sửa trực tiếp map header. Dùng `MessageBuilder` để tạo message mới.

### Dùng postReceive để lọc message

Có thể kiểm tra nội dung sau khi lấy message:

~~~java
@Override
public Message<?> postReceive(
        Message<?> message,
        MessageChannel channel) {

    if (!isAllowed(message)) {
        return null;
    }

    return message;
}
~~~

Khi trả về `null`, message đã được lấy khỏi channel nhưng không được chuyển tiếp đến consumer qua lần gọi `receive()` đó. Đây là hành vi loại message, không phải cơ chế rollback hoặc tự động đưa message trở lại queue.

Vì vậy, chỉ dùng cách này khi chính sách loại bỏ đã rõ ràng. Nếu cần retry, quarantine hoặc audit message bị từ chối, hãy triển khai quy trình chuyển message sang channel lỗi hoặc lưu lại thông tin trước khi bỏ nó. Không dùng `null` như cách từ chối tạm thời nếu không muốn mất message.

### postReceive chỉ chạy khi có message

Từ Spring Integration 5.1, `postReceive` không còn được gọi khi channel không lấy được message. Consumer không cần xử lý trường hợp message null trong callback này. Với lần poll rỗng, hãy dùng `afterReceiveCompletion` nếu cần cleanup hoặc ghi nhận kết quả của lần nhận.

Điều này đặc biệt quan trọng với polling consumer: một lần `receive(timeout)` có thể kết thúc mà không có message, và việc đó không đồng nghĩa với lỗi.

## 5. afterReceiveCompletion: cleanup sau thao tác nhận

Chữ ký:

~~~java
void afterReceiveCompletion(
        Message<?> message,
        MessageChannel channel,
        Exception ex)
~~~

Callback được gọi sau khi thao tác receive kết thúc, kể cả khi thao tác gặp exception, nhằm hỗ trợ cleanup.

Các tham số:

- `message`: message nhận được hoặc message sau khi interceptor chain xử lý; có thể là `null` nếu không lấy được message, message bị lọc hoặc có lỗi trước khi có kết quả.
- `channel`: channel thực hiện receive.
- `ex`: exception phát sinh trong quá trình nhận; `null` khi không có exception.

Callback này chỉ được gọi cho interceptor mà `preReceive` đã hoàn thành và trả về `true`. Nếu `preReceive` trả về false, interceptor đó không được đưa vào stack cleanup.

Ví dụ:

~~~java
public class ReceiveTimingInterceptor implements ChannelInterceptor {

    private final ThreadLocal<Long> startedAt = new ThreadLocal<>();

    @Override
    public boolean preReceive(MessageChannel channel) {
        startedAt.set(System.nanoTime());
        return true;
    }

    @Override
    public void afterReceiveCompletion(
            Message<?> message,
            MessageChannel channel,
            Exception ex) {

        Long start = startedAt.get();

        try {
            if (start != null) {
                long elapsedNanos = System.nanoTime() - start;
                System.out.println("receiveNanos=" + elapsedNanos);
            }

            if (ex != null) {
                System.out.println(
                        "receiveFailed=" + ex.getClass().getSimpleName()
                );
            }
        }
        finally {
            startedAt.remove();
        }
    }
}
~~~

Dùng `System.nanoTime()` để đo thời lượng vì đây là đồng hồ monotonic phù hợp cho đo elapsed time. Không dùng `MessageHeaders.TIMESTAMP` hoặc `System.currentTimeMillis()` để đo duration chính xác.

### Những trường hợp cần cleanup

| Kết quả receive | preReceive | postReceive | afterReceiveCompletion |
|---|---|---|---|
| Nhận được message | true | Có | Có |
| Queue rỗng / timeout | true | Không gọi từ Spring Integration 5.1 | Có, message thường null, ex null |
| postReceive trả về null | true | Có | Có |
| Lấy message hoặc interceptor phát sinh exception | true | Có thể chưa chạy hoặc đã chạy | Có, nhận exception nếu được truyền vào completion |
| preReceive trả về false | false | Không | Không gọi cho interceptor trả false |

`afterReceiveCompletion` là nơi phù hợp để giải phóng resource, xóa ThreadLocal, dừng timer hoặc kết thúc context đã mở trong `preReceive`. Dùng `try/finally` bên trong callback nếu cleanup có nhiều bước và một bước có thể lỗi.

## 6. Thứ tự khi có nhiều interceptor

Giả sử channel đăng ký ba interceptor theo thứ tự A, B, C và cả ba đều cho phép nhận.

Thứ tự trên đường nhận thành công:

~~~text
A.preReceive
B.preReceive
C.preReceive
        |
        v
Channel lấy message
        |
        v
A.postReceive
B.postReceive
C.postReceive
        |
        v
C.afterReceiveCompletion
B.afterReceiveCompletion
A.afterReceiveCompletion
~~~

Các điểm cần nhớ:

- `preReceive` chạy theo thứ tự đăng ký.
- `postReceive` chạy theo thứ tự đăng ký nếu message vẫn còn sau callback trước đó.
- `afterReceiveCompletion` chạy theo thứ tự ngược lại cho các interceptor đã qua `preReceive`.
- Nếu một `preReceive` trả false, các interceptor sau không được gọi.
- Nếu một `postReceive` trả null, các `postReceive` phía sau không được gọi; cleanup vẫn chạy cho các interceptor đã qua preReceive.

Đây là mô hình tương tự stack resource: mở theo thứ tự A → B → C, đóng theo thứ tự C → B → A. Nhờ vậy, interceptor có thể mở resource hoặc thiết lập context trong `preReceive` và khôi phục chúng trong `afterReceiveCompletion`.

### Không có thứ tự tổng thể cố định giữa send và receive

Send và receive có thể chạy trên hai thread độc lập. Một consumer có thể đang block trong `receive()` trước khi producer gửi message; hoặc producer có thể gửi xong rồi consumer mới poll.

Ví dụ thứ tự có thể là:

~~~text
Trường hợp consumer đang chờ:
preSend -> preReceive -> postReceive -> postSend
~~~

Hoặc:

~~~text
Trường hợp producer gửi trước:
preSend -> postSend -> ... -> preReceive -> postReceive
~~~

Khoảng thời gian giữa hai thao tác phụ thuộc loại queue, timeout, lịch chạy thread và tải hệ thống. Không dựa vào thứ tự giữa send và receive để thực hiện nghiệp vụ. Chỉ dựa vào quan hệ nội bộ của từng operation: `preReceive` trước `postReceive`, và completion chạy sau khi receive kết thúc.

## 7. Ví dụ Java 17 hoàn chỉnh với QueueChannel

Ví dụ dùng Java 17 và Spring Integration 6.5.2. Nó đăng ký một interceptor trên `QueueChannel`, nhận một message thành công rồi thực hiện một lần poll rỗng để quan sát ba callback.

Cấu trúc thư mục:

~~~text
receive-interceptor-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ReceiveInterceptorDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>receive-interceptor-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.integration</groupId>
            <artifactId>spring-integration-core</artifactId>
            <version>6.5.2</version>
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

Tệp `src/main/java/demo/ReceiveInterceptorDemo.java`:

~~~java
package demo;

import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageBuilder;

public class ReceiveInterceptorDemo {

    public static void main(String[] args) {
        QueueChannel channel = new QueueChannel(10);

        channel.addInterceptor(new ChannelInterceptor() {

            @Override
            public boolean preReceive(MessageChannel channel) {
                System.out.println("preReceive");
                return true;
            }

            @Override
            public Message<?> postReceive(
                    Message<?> message,
                    MessageChannel channel) {
                System.out.println(
                        "postReceive payload=" + message.getPayload()
                );
                return message;
            }

            @Override
            public void afterReceiveCompletion(
                    Message<?> message,
                    MessageChannel channel,
                    Exception ex) {
                System.out.println(
                        "afterReceiveCompletion messagePresent="
                                + (message != null)
                                + ", exception="
                                + (ex == null
                                    ? "none"
                                    : ex.getClass().getSimpleName())
                );
            }
        });

        channel.send(
                MessageBuilder.withPayload("ORD-1001").build()
        );

        Message<?> received = channel.receive(1000);
        System.out.println("caller received=" + received.getPayload());

        Message<?> empty = channel.receive(10);
        System.out.println("empty poll=" + (empty == null));
    }
}
~~~

Chạy từ thư mục chứa `pom.xml`:

~~~bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.5.0:java -Dexec.mainClass=demo.ReceiveInterceptorDemo
~~~

Kết quả stdout:

~~~text
preReceive
postReceive payload=ORD-1001
afterReceiveCompletion messagePresent=true, exception=none
caller received=ORD-1001
preReceive
afterReceiveCompletion messagePresent=false, exception=none
empty poll=true
~~~

Giải thích:

1. Lần receive đầu tiên lấy được message nên `preReceive`, `postReceive` và `afterReceiveCompletion` đều chạy.
2. Consumer nhận payload `ORD-1001` sau khi receive interceptor hoàn tất.
3. Lần receive thứ hai queue rỗng. `preReceive` vẫn chạy vì consumer bắt đầu poll.
4. Không có message nên `postReceive` không được gọi.
5. `afterReceiveCompletion` vẫn chạy để cleanup; message và exception đều null.

## 8. Ví dụ chặn nhận và lọc message

Có thể chặn lần nhận dựa trên trạng thái:

~~~java
public class PausingInterceptor implements ChannelInterceptor {

    private volatile boolean paused;

    public void pause() {
        paused = true;
    }

    public void resume() {
        paused = false;
    }

    @Override
    public boolean preReceive(MessageChannel channel) {
        return !paused;
    }
}
~~~

Khi `paused` là true, consumer không lấy message khỏi channel. Cần có cơ chế bên ngoài gọi `resume()`; nếu không, message có thể tồn tại trong queue nhưng không được xử lý.

Có thể lọc message sau khi đã lấy:

~~~java
public class OrderFilterInterceptor implements ChannelInterceptor {

    @Override
    public Message<?> postReceive(
            Message<?> message,
            MessageChannel channel) {

        Object payload = message.getPayload();

        if (payload instanceof String value
                && value.startsWith("TEST-")) {
            return null;
        }

        return message;
    }
}
~~~

Trong ví dụ này, message có payload bắt đầu bằng `TEST-` bị loại khỏi lần nhận. Message đã rời queue; interceptor không tự đưa nó trở lại. Nếu cần lưu lại hoặc chuyển sang dead-letter channel, hãy thực hiện việc đó trước khi trả null hoặc thiết kế endpoint chuyên trách.

## 9. Đăng ký interceptor và phạm vi áp dụng

Có thể đăng ký trực tiếp trên channel:

~~~java
QueueChannel channel = new QueueChannel(100);
channel.addInterceptor(new ReceiveTimingInterceptor());
~~~

Trong Spring Integration, channel thường được khai báo như bean:

~~~java
@Configuration(proxyBeanMethods = false)
public class ChannelConfiguration {

    @Bean
    public QueueChannel inboundChannel() {
        QueueChannel channel = new QueueChannel(100);
        channel.addInterceptor(new ReceiveTimingInterceptor());
        return channel;
    }
}
~~~

Nếu một interceptor cần áp dụng cho nhiều channel, có thể đăng ký qua cơ chế global channel interceptor của Spring Integration. Cần xác định rõ phạm vi channel và thứ tự interceptor; global interceptor có thể ảnh hưởng cả channel được tạo động tùy cách đăng ký và phiên bản.

Một interceptor gắn với channel chỉ quan sát các thao tác đi qua channel đó. Nó không tự động chặn mọi message của ứng dụng hoặc mọi transport bên ngoài.

## 10. Lỗi thường gặp

1. **Đăng ký receive interceptor trên DirectChannel.** DirectChannel là subscribable; nó không có thao tác receive để kích hoạt ba callback này.
2. **Dùng preReceive để kiểm tra payload.** Callback chưa nhận message. Hãy dùng postReceive hoặc logic trong consumer.
3. **Cho rằng postReceive chạy cả khi queue rỗng.** Từ Spring Integration 5.1, callback này chỉ chạy khi có message thực sự được lấy.
4. **Dùng afterReceiveCompletion chỉ để xử lý thành công.** Callback được thiết kế cho cleanup cả khi receive gặp exception hoặc không có message.
5. **Cho rằng afterReceiveCompletion luôn chạy sau preReceive false.** Interceptor trả false chưa qua preReceive thành công nên không nhận completion callback của chính nó.
6. **Trả null từ postReceive nhưng mong message được retry.** Message đã được lấy khỏi channel; trả null làm dừng việc trả message cho consumer, không rollback queue.
7. **Giả định thứ tự send và receive cố định.** Hai operation có thể chạy trên các thread khác nhau và thứ tự tương đối phụ thuộc timing.
8. **Không dọn ThreadLocal.** Polling thread pool tái sử dụng worker; context cũ có thể rò sang lần nhận sau. Xóa hoặc khôi phục trong afterReceiveCompletion.
9. **Thực hiện công việc nặng trong postReceive.** Callback chạy trong đường nhận và làm tăng thời gian consumer chờ. Đưa xử lý nghiệp vụ nặng vào handler/service.
10. **Dùng interceptor như nơi chứa nghiệp vụ chính.** Interceptor phù hợp cho cross-cutting concern như logging, metrics, kiểm soát receive và context; logic nghiệp vụ nên nằm trong consumer/service.
11. **Không kiểm thử lần poll rỗng.** Đây là trường hợp phổ biến của poller; cần xác minh cleanup vẫn diễn ra.
12. **Không xử lý nhiều interceptor.** Cleanup nên chạy theo thứ tự ngược; không giả định thứ tự registration giống nhau cho mọi callback.

## 11. Checklist triển khai

- [ ] Xác nhận channel triển khai `PollableChannel`.
- [ ] Xác nhận consumer thực sự gọi `receive()`.
- [ ] Dùng `preReceive` cho điều kiện trước khi lấy message, không dùng để đọc payload.
- [ ] Dùng `postReceive` khi cần quan sát hoặc biến đổi message đã lấy.
- [ ] Chỉ trả null từ `postReceive` khi chấp nhận loại message khỏi luồng nhận.
- [ ] Dùng `afterReceiveCompletion` để cleanup cả khi queue rỗng hoặc có exception.
- [ ] Kiểm tra hành vi khi `preReceive` trả false.
- [ ] Kiểm tra thứ tự khi có nhiều interceptor.
- [ ] Đo thời lượng bằng đồng hồ monotonic nếu cần latency.
- [ ] Không dựa vào thứ tự tổng thể giữa send và receive.
- [ ] Kiểm thử success, timeout, empty poll, filtering và exception.
- [ ] Giữ logic nghiệp vụ trong consumer/service; dùng interceptor cho hành vi xuyên suốt.

## 12. Kết luận

Ba callback nhận có ba trách nhiệm riêng: `preReceive` cho phép hoặc chặn việc lấy message; `postReceive` quan sát hoặc biến đổi message sau khi channel đã lấy được nó; `afterReceiveCompletion` dọn tài nguyên khi thao tác nhận kết thúc. Chúng chỉ áp dụng cho `PollableChannel`, vì `SubscribableChannel` dispatch message từ phía send và không có `receive()`. Khi triển khai, hãy xử lý cả trường hợp poll rỗng, exception và nhiều interceptor; đặc biệt không nhầm việc trả null với retry hoặc rollback message.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2.18 Javadoc: ChannelInterceptor](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html) — contract và vòng đời của preReceive, postReceive, afterReceiveCompletion.
- [Spring Framework 6.2.18 Javadoc: PollableChannel](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/PollableChannel.html) — thao tác receive và receive với timeout.
- [Spring Framework 6.2.18 Javadoc: SubscribableChannel](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/SubscribableChannel.html) — đăng ký handler và semantics dispatch.
- [Spring Integration Reference: Channel Interceptors](https://docs.spring.io/spring-integration/reference/channel/interceptors.html) — receive interceptor chỉ áp dụng cho PollableChannel, postReceive khi queue rỗng, thứ tự callback và global interceptors.
- [Spring Integration Reference: Message Channels](https://docs.spring.io/spring-integration/reference/channel.html) — các loại channel pollable và subscribable.
- [Spring Integration Javadoc: QueueChannel](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/channel/QueueChannel.html) — queue channel hỗ trợ poll/receive.
