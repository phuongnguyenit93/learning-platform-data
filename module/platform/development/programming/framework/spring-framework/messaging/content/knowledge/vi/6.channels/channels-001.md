# MessageChannel và hợp đồng send trong Spring Messaging

## 1. MessageChannel là gì?

Trong Spring Framework, **org.springframework.messaging.MessageChannel** là abstraction đại diện cho một đầu gửi thông điệp. Publisher chỉ cần biết channel và gọi **send(message)**; nó không cần biết thành phần nhận là handler nào, được đăng ký ra sao hay đang chạy trên thread nào.

Một **Message<?>** chứa payload và headers. **MessageChannel** nhận message đó và chuyển quyền xử lý cho implementation cụ thể. Interface này tập trung vào thao tác gửi, không định nghĩa cách nhận message hoặc cách đăng ký subscriber.

Spring Messaging dùng các abstraction liên quan:

- **Message<T>**: dữ liệu được gửi, gồm payload có kiểu và headers.
- **MessageChannel**: hợp đồng gửi message.
- **SubscribableChannel**: mở rộng MessageChannel, quản lý các MessageHandler đăng ký để xử lý message được gửi đến.
- **PollableChannel**: mở rộng MessageChannel, cho phép consumer chủ động gọi receive() để lấy message.
- **MessageHandler**: hợp đồng xử lý message qua handleMessage(message).

Có thể hình dung mối quan hệ như sau:

~~~mermaid
classDiagram
    class MessageChannel {
        +send(Message) boolean
        +send(Message, timeout) boolean
    }
    class SubscribableChannel {
        +subscribe(MessageHandler) boolean
        +unsubscribe(MessageHandler) boolean
    }
    class PollableChannel {
        +receive() Message
        +receive(timeout) Message
    }
    MessageChannel <|-- SubscribableChannel
    MessageChannel <|-- PollableChannel
~~~

**MessageChannel** là interface ở package **org.springframework.messaging**, thuộc module **spring-messaging**. Nó cũng được dùng làm abstraction chung trong các thành phần Spring khác, bao gồm Spring Integration.

## 2. Hai phương thức send

Trong Spring Framework 7.0.10, MessageChannel khai báo hai cách gửi:

~~~java
boolean send(Message<?> message);

boolean send(Message<?> message, long timeout);
~~~

**send(Message<?>)** là phương thức mặc định. Nó gọi overload có timeout với **MessageChannel.INDEFINITE_TIMEOUT**, nghĩa là không đặt thời hạn chờ. Tùy implementation, lời gọi này có thể chờ vô thời hạn.

**send(Message<?>, long timeout)** gửi message và có thể block cho đến khi channel chấp nhận message hoặc thời gian chờ kết thúc. Đơn vị timeout là mili giây; giá trị **MessageChannel.INDEFINITE_TIMEOUT** là **-1L**, biểu thị không giới hạn thời gian chờ.

| Cách gọi | Ý nghĩa |
| --- | --- |
| **send(message)** | Gửi không chỉ định timeout; implementation có thể block vô thời hạn |
| **send(message, 500)** | Cho phép implementation chờ theo timeout 500 mili giây |
| **send(message, MessageChannel.INDEFINITE_TIMEOUT)** | Gửi với thời gian chờ không giới hạn |

Timeout chỉ điều khiển thời gian chờ theo khả năng của implementation. **MessageChannel** không quy định mọi channel phải có buffer, capacity hay cùng một chính sách khi timeout bằng 0. Hãy đọc hợp đồng của channel cụ thể trước khi dựa vào các chi tiết đó.

## 3. Ý nghĩa của giá trị trả về

Cả hai phương thức **send** trả về **boolean**:

- **true**: message đã được channel chấp nhận hoặc gửi thành công theo hợp đồng của implementation.
- **false**: message không được gửi vì một lý do không nghiêm trọng, chẳng hạn channel không thể nhận message trong thời hạn quy định hoặc thao tác gửi bị interrupt.
- **RuntimeException**: có thể được ném ra khi xảy ra lỗi không thể phục hồi.

Không nên diễn giải **true** thành “consumer đã xử lý xong”. Nó chỉ xác nhận kết quả gửi theo channel. Tùy loại channel, message có thể vừa được chuyển đến handler, được đưa vào hàng đợi, hoặc được bàn giao cho executor. Việc xử lý nghiệp vụ hoàn tất, lưu trữ bền vững hay xác nhận từ broker là các mức bảo đảm khác nhau.

Ví dụ kiểm tra kết quả gửi:

~~~java
boolean sent = channel.send(message, 500);

if (sent) {
    System.out.println("Message accepted by channel");
} else {
    System.out.println("Message was not accepted");
}
~~~

Nếu gửi thất bại, ứng dụng cần quyết định cách xử lý theo nghiệp vụ: ghi log, phát cảnh báo, thử lại có giới hạn, lưu vào outbox hoặc trả lỗi cho caller. Không tự động retry vô hạn vì có thể làm tăng tải hoặc tạo message trùng lặp.

Khi bắt exception, hãy bắt đúng loại lỗi mà implementation hoặc tầng gọi có thể phát sinh. Không nên bắt Exception chung rồi bỏ qua, vì như vậy sẽ che khuất lỗi lập trình và lỗi vận hành.

## 4. MessageChannel không quyết định cách nhận

**MessageChannel** chỉ định nghĩa cách gửi. Các interface con bổ sung cách consumer nhận message:

| Kiểu channel | Cách consumer lấy message | Đặc điểm |
| --- | --- | --- |
| **SubscribableChannel** | Handler đăng ký trước bằng subscribe | Channel chủ động gọi handler khi nhận message |
| **PollableChannel** | Consumer gọi receive() hoặc receive(timeout) | Consumer chủ động lấy message; implementation có thể buffer |
| **MessageChannel** thuần | Không có API nhận được quy định bởi interface | Chỉ biết hợp đồng gửi; cách xử lý phụ thuộc implementation |

Với **SubscribableChannel**, **subscribe(handler)** trả về true nếu đăng ký thành công và false nếu handler đã đăng ký. **unsubscribe(handler)** trả về true nếu hủy đăng ký được và false nếu handler chưa đăng ký.

Với **PollableChannel**, **receive()** có thể block vô thời hạn để chờ message. **receive(timeout)** chờ message trong khoảng thời gian chỉ định; trả về null nếu hết thời gian hoặc thread bị interrupt.

Đừng gọi **receive()** trên một **MessageChannel** chỉ vì biến có tên “channel”. Chỉ các kiểu có hợp đồng **PollableChannel** mới cung cấp API polling; chỉ **SubscribableChannel** mới cung cấp API quản lý subscriber.

## 5. Implementation ảnh hưởng đến hành vi send

Interface thống nhất cách gọi, nhưng implementation quyết định cách chuyển message, thời gian block và cách báo lỗi.

### 5.1. ExecutorSubscribableChannel trong Spring Framework

**ExecutorSubscribableChannel** là implementation của **SubscribableChannel** trong chính Spring Framework. Nó gửi message đến từng subscriber đã đăng ký.

- Constructor không tham số gửi message trên thread gọi send.
- Constructor nhận Executor gửi message thông qua executor được cung cấp.
- Nó cung cấp subscribe và unsubscribe để quản lý handler.
- Khi dùng executor, việc dispatch có thể bất đồng bộ; send trả về không đồng nghĩa mọi handler đã hoàn tất xử lý.

Ví dụ cấu hình channel trong ứng dụng:

~~~java
@Bean
public SubscribableChannel orderEvents() {
    return new ExecutorSubscribableChannel();
}
~~~

Ví dụ trên dùng constructor không tham số. Handler chạy trên thread gọi send. Nếu muốn chuyển dispatch sang thread pool, truyền một Executor đã được cấu hình và quản lý vòng đời phù hợp.

### 5.2. Các channel trong Spring Integration

Spring Integration bổ sung nhiều implementation phục vụ integration flow. Một số tên thường gặp:

- **DirectChannel**: phân phối point-to-point đến một handler phù hợp; handler thường được gọi trực tiếp trong thread gửi.
- **PublishSubscribeChannel**: phát message đến nhiều subscriber.
- **QueueChannel**: lưu message trong queue để consumer polling.
- **PriorityChannel**: queue sắp xếp message theo priority.

Các lớp như **DirectChannel**, **PublishSubscribeChannel** và **QueueChannel** thuộc Spring Integration, không phải các implementation cốt lõi của module **spring-messaging**. Muốn dùng chúng, dự án cần dependency Spring Integration tương ứng.

Khi đọc code, hãy kiểm tra import và dependency để biết channel đang dùng thuộc Spring Framework hay Spring Integration. Hai hệ sinh thái chia sẻ abstraction **MessageChannel**, nhưng danh sách implementation và cấu hình vận hành khác nhau.

## 6. Ví dụ chạy được với Spring Framework 7.0.10 và Java 17+

Ví dụ sau dùng **ExecutorSubscribableChannel** để minh họa publisher chỉ phụ thuộc vào interface **MessageChannel**. Channel được tạo bằng constructor không tham số, do đó handler chạy đồng bộ trên thread gửi.

Cấu trúc thư mục:

~~~text
message-channel-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── MessageChannelDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>message-channel-demo</artifactId>
    <version>1.0.0</version>

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
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>MessageChannelDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/MessageChannelDemo.java**

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.SubscribableChannel;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class MessageChannelDemo {

    public static void main(String[] args) {
        SubscribableChannel channel = new ExecutorSubscribableChannel();

        channel.subscribe(message ->
            System.out.println("handler.payload=" + message.getPayload())
        );

        Message<String> event = MessageBuilder
            .withPayload("order-72")
            .setHeader("eventType", "order.created")
            .build();

        MessageChannel publisherPort = channel;
        boolean sent = publisherPort.send(event);

        System.out.println("sent=" + sent);
    }
}
~~~

Chạy trong thư mục có **pom.xml**:

~~~bash
mvn -q clean compile exec:java
~~~

Stdout:

~~~text
handler.payload=order-72
sent=true
~~~

**publisherPort** có kiểu **MessageChannel**, dù object thực tế là **ExecutorSubscribableChannel**. Publisher chỉ gọi send; phần đăng ký handler được quản lý qua **SubscribableChannel**. Do channel dùng constructor không tham số, handler chạy trên thread gọi send, nên dòng handler.payload xuất hiện trước sent=true.

### 6.1. Minh họa overload có timeout

Có thể thay lời gọi **send(event)** bằng:

~~~java
boolean sent = publisherPort.send(event, 500);
~~~

Giá trị 500 là thời gian chờ tính bằng mili giây. Với channel cụ thể, cần đọc tài liệu implementation để biết việc chờ có áp dụng như thế nào. Ví dụ **ExecutorSubscribableChannel** không có buffer kiểu queue để chờ slot; không nên suy ra mọi channel đều block hoặc timeout giống nhau.

### 6.2. Minh họa hợp đồng bằng lambda

**MessageChannel** được đánh dấu **@FunctionalInterface**. Trong một unit test hoặc ví dụ đơn giản, có thể viết implementation tối thiểu bằng lambda:

~~~java
MessageChannel acceptingChannel = (message, timeout) -> true;
MessageChannel rejectingChannel = (message, timeout) -> false;
~~~

Hai lambda trên chỉ minh họa hai kết quả có thể có của hợp đồng send. Chúng không lưu message, không chuyển message đến consumer và không mô phỏng một broker thực tế.

## 7. Channel interceptor và điểm kiểm soát khi gửi

Một số implementation của Spring Framework hỗ trợ **InterceptableChannel**, cho phép gắn **ChannelInterceptor** vào đường đi của message. Interceptor hữu ích cho logging, metrics, tracing, kiểm tra metadata hoặc chặn message theo chính sách.

Các callback thường dùng:

- **preSend(message, channel)**: chạy trước khi message được gửi. Có thể trả về message đã biến đổi hoặc null để chặn gửi.
- **postSend(message, channel, sent)**: chạy sau thao tác gửi và nhận kết quả boolean.
- **afterSendCompletion(message, channel, sent, exception)**: chạy sau khi quá trình gửi hoàn tất, kể cả khi có exception.

Ví dụ interceptor ghi lại kết quả gửi:

~~~java
public class SendLoggingInterceptor implements ChannelInterceptor {

    @Override
    public void postSend(
            Message<?> message,
            MessageChannel channel,
            boolean sent) {
        System.out.println(
            "channel=" + channel + ", sent=" + sent
        );
    }
}
~~~

Đăng ký interceptor trên một channel hỗ trợ intercept:

~~~java
ExecutorSubscribableChannel channel = new ExecutorSubscribableChannel();
channel.addInterceptor(new SendLoggingInterceptor());
~~~

Interceptor là điểm quan sát và áp dụng cross-cutting concern. Không nên đặt toàn bộ logic nghiệp vụ vào interceptor vì nó khiến hành vi gửi khó theo dõi và khó kiểm thử.

## 8. Lỗi thường gặp khi gọi send

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| send trả về false | Channel từ chối message, hết timeout hoặc thread gửi bị interrupt | Ghi nhận kết quả; xử lý retry hoặc fallback theo chính sách |
| send block lâu | Implementation chờ capacity hoặc chờ message được chấp nhận | Chọn timeout hữu hạn nếu phù hợp và kiểm tra cấu hình channel |
| send trả về true nhưng nghiệp vụ chưa hoàn tất | Channel đã nhận hoặc dispatch message nhưng handler xử lý sau | Theo dõi kết quả xử lý ở consumer hoặc dùng acknowledgement phù hợp |
| Không có handler nhận message | Channel không có subscriber hoặc handler đã bị unsubscribe | Kiểm tra subscribe, vòng đời handler và loại channel |
| Gọi receive trên biến MessageChannel | Interface cơ sở không định nghĩa nhận message | Dùng PollableChannel nếu consumer cần polling |
| Gửi qua executor nhưng log xuất hiện sau | Handler chạy trên thread executor | Dùng log có correlation ID và giám sát lỗi bất đồng bộ |
| Retry làm xử lý trùng | Lần gửi trước có thể đã được chấp nhận nhưng caller không nhận được xác nhận nghiệp vụ | Thiết kế consumer idempotent và dùng event ID |

## 9. Nguyên tắc thiết kế khi dùng MessageChannel

- Giữ publisher phụ thuộc vào interface **MessageChannel** để giảm coupling với implementation.
- Chọn **SubscribableChannel** khi cần đăng ký handler; chọn **PollableChannel** khi cần consumer polling.
- Đặt timeout phù hợp với SLA và khả năng của channel; tránh mặc định chờ vô hạn ở luồng request quan trọng.
- Xử lý cả ba trường hợp: true, false và exception.
- Phân biệt channel đã nhận message với consumer đã hoàn tất xử lý.
- Khi dùng executor, cấu hình thread pool, queue và chính sách từ chối rõ ràng.
- Dùng correlation ID để truy vết từ publisher qua handler.
- Nếu yêu cầu message không mất qua restart hoặc cần xác nhận bền vững, chọn broker và cấu hình persistence phù hợp; **MessageChannel** tự nó không cung cấp bảo đảm lưu trữ.
- Dùng interceptor cho logging, metrics và tracing; giữ logic nghiệp vụ trong handler hoặc service.

## 10. Tài liệu tham khảo

- [Spring Framework API — MessageChannel](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/messaging/MessageChannel.html)
- [Spring Framework API — SubscribableChannel](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/messaging/SubscribableChannel.html)
- [Spring Framework API — PollableChannel](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/messaging/PollableChannel.html)
- [Spring Framework API — ExecutorSubscribableChannel](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/messaging/support/ExecutorSubscribableChannel.html)
- [Spring Framework API — ChannelInterceptor](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html)
- [Spring Framework — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Integration — Channel Interfaces](https://docs.spring.io/spring-integration/reference/7.0/channel/interfaces.html)
