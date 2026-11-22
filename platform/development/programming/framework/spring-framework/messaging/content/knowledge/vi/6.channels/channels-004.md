# SubscribableChannel và đăng ký MessageHandler

## Mục tiêu

Trong Spring Messaging, `SubscribableChannel` là một loại `MessageChannel` quản lý danh sách các thành phần đăng ký nhận message. Mỗi thành phần đăng ký là một `MessageHandler`, tức đối tượng biết cách xử lý một `Message<?>`.

Hiểu đúng hai abstraction này giúp bạn trả lời được:

- Handler được đăng ký với channel như thế nào?
- `subscribe()` và `unsubscribe()` trả về điều gì?
- Một message được chuyển tới một subscriber hay tất cả subscriber?
- Việc xử lý diễn ra trong thread gửi hay thread của executor?
- Khi handler lỗi, lỗi được trả về sender hay đi qua error flow?
- Khi nào nên chọn `SubscribableChannel`, `DirectChannel`, `PublishSubscribeChannel` hoặc `QueueChannel`?

Điểm quan trọng nhất: **`SubscribableChannel` định nghĩa hợp đồng quản lý subscriber; cách dispatch cụ thể phụ thuộc implementation.** Đừng suy luận broadcast hay point-to-point chỉ từ tên interface.

## 1. MessageChannel và SubscribableChannel

Spring Messaging cung cấp các abstraction cơ bản trong package `org.springframework.messaging`:

- `Message<T>`: gói dữ liệu gồm payload và headers.
- `MessageChannel`: nơi gửi message; cung cấp `send(message)` và `send(message, timeout)`.
- `SubscribableChannel`: mở rộng `MessageChannel`, quản lý các `MessageHandler` đã đăng ký.
- `PollableChannel`: một loại channel có thao tác `receive()` để consumer chủ động lấy message.
- `MessageHandler`: hợp đồng xử lý một message.

Khai báo rút gọn của `SubscribableChannel`:

~~~java
public interface SubscribableChannel extends MessageChannel {

    boolean subscribe(MessageHandler handler);

    boolean unsubscribe(MessageHandler handler);
}
~~~

Một `SubscribableChannel` duy trì registry các subscriber. Khi message được gửi qua channel, implementation gọi các handler đã đăng ký theo quy tắc dispatch của nó.

Khác với `PollableChannel`, `SubscribableChannel` không có phương thức `receive()`. Consumer không gọi poll để lấy message; handler được channel gọi khi message được gửi tới.

### Channel không đồng nghĩa với broker

Một `SubscribableChannel` thường là abstraction trong runtime của ứng dụng Spring. Đăng ký handler có nghĩa là gắn một đối tượng Java vào registry của channel. Điều đó không tạo queue/topic trên RabbitMQ, Kafka hoặc JMS broker và cũng không đăng ký một subscription từ xa.

Nếu cần trao đổi giữa các tiến trình hoặc lưu message bền vững, ứng dụng cần adapter/client và broker/provider tương ứng.

## 2. MessageHandler là gì?

`org.springframework.messaging.MessageHandler` là functional interface với một phương thức:

~~~java
@FunctionalInterface
public interface MessageHandler {

    void handleMessage(Message<?> message) throws MessagingException;
}
~~~

Handler nhận toàn bộ message, không chỉ payload. Từ tham số `message`, handler có thể đọc:

~~~java
Object payload = message.getPayload();
MessageHeaders headers = message.getHeaders();

Object traceId = headers.get("traceId");
~~~

Các đặc điểm cần nhớ:

- `handleMessage` trả về `void`; đây không phải API trả kết quả trực tiếp cho sender.
- Tham số là `Message<?>`, nên handler phải kiểm tra hoặc chuyển đổi payload theo hợp đồng mà nó hỗ trợ.
- Handler có thể ném `MessagingException` khi không xử lý được message.
- Vì là functional interface, có thể dùng lambda hoặc method reference thay cho một class riêng.
- Nếu cần tạo reply, handler phải gửi một message khác qua reply channel hoặc channel tiếp theo của flow; không thể trả reply bằng giá trị return của `handleMessage`.

Ví dụ handler dạng lambda:

~~~java
MessageHandler orderHandler = message -> {
    String orderId = (String) message.getPayload();
    System.out.println("processing order=" + orderId);
};
~~~

Ví dụ class riêng:

~~~java
public final class AuditHandler implements MessageHandler {

    @Override
    public void handleMessage(Message<?> message) {
        System.out.println("audit payload=" + message.getPayload());
    }
}
~~~

Lambda phù hợp với xử lý ngắn. Class riêng phù hợp khi handler có nhiều dependency, nhiều nhánh xử lý hoặc cần được kiểm thử độc lập.

## 3. Đăng ký subscriber bằng subscribe()

Phương thức `subscribe(handler)` thêm một `MessageHandler` vào registry của channel.

~~~java
SubscribableChannel channel = new ExecutorSubscribableChannel();

MessageHandler handler = message ->
        System.out.println("received=" + message.getPayload());

boolean added = channel.subscribe(handler);
~~~

Giá trị trả về:

| Kết quả | Ý nghĩa |
|---|---|
| `true` | Handler đã được đăng ký thành công. |
| `false` | Handler đó đã được đăng ký trước đó, nên lần gọi này không tạo thêm một đăng ký mới. |

Nếu muốn kiểm tra lại, có thể gọi `subscribe` lần nữa với cùng biến handler:

~~~java
boolean first = channel.subscribe(handler);  // true nếu mới đăng ký
boolean second = channel.subscribe(handler); // false nếu đã đăng ký
~~~

Hãy giữ reference của handler khi cần hủy đăng ký sau này. Không nên tạo một lambda mới trong lời gọi `unsubscribe` rồi mong nó tự khớp với lambda trước đó:

~~~java
MessageHandler handler = message -> process(message);

channel.subscribe(handler);

// Dùng đúng reference đã đăng ký.
channel.unsubscribe(handler);
~~~

Trong ứng dụng Spring, subscriber thường được đăng ký trong quá trình khởi tạo context thông qua bean, endpoint hoặc cấu hình Integration. Không nên đăng ký lặp lại mỗi lần một request đến, vì điều đó có thể khiến một message bị xử lý nhiều lần bởi các handler trùng vai trò.

## 4. Hủy đăng ký bằng unsubscribe()

`unsubscribe(handler)` gỡ handler khỏi registry.

~~~java
boolean removed = channel.unsubscribe(handler);
~~~

Giá trị trả về:

- `true`: handler đã được gỡ khỏi registry.
- `false`: handler không được đăng ký tại thời điểm gọi.

Một vòng đời đơn giản:

~~~text
Tạo channel
    |
    v
Tạo MessageHandler
    |
    v
subscribe(handler)
    |
    v
Gửi message -> channel dispatch tới subscriber
    |
    v
unsubscribe(handler)
    |
    v
Handler không còn nhận message từ lần dispatch sau
~~~

Việc unsubscribe không phải thao tác thu hồi một message đã được gửi hoặc một tác vụ đã bắt đầu chạy. Nếu implementation dispatch bất đồng bộ, một task đã được đưa vào executor có thể vẫn tiếp tục chạy sau khi handler bị gỡ khỏi registry. Hãy thiết kế vòng đời handler và shutdown của executor phù hợp với vòng đời ứng dụng.

## 5. Một message được gửi cho ai?

Đây là chỗ dễ nhầm nhất. Interface `SubscribableChannel` chỉ định nghĩa registry subscriber. Nó không quy định mọi implementation phải gửi tới đúng một handler hay gửi tới tất cả handler.

Một số implementation tiêu biểu:

| Implementation | Module | Cách dispatch |
|---|---|---|
| `ExecutorSubscribableChannel` | Spring Framework / `spring-messaging` | Gửi message tới từng subscriber đã đăng ký. |
| `DirectChannel` | Spring Integration | Point-to-point: chọn một handler cho mỗi message; có thể load-balance giữa nhiều subscriber. |
| `PublishSubscribeChannel` | Spring Integration | Broadcast message tới tất cả subscriber. |
| `ExecutorChannel` | Spring Integration | Point-to-point như DirectChannel nhưng dispatch qua TaskExecutor. |

Vì vậy, nếu yêu cầu nghiệp vụ là “mỗi message chỉ do một worker xử lý”, hãy chọn implementation point-to-point như `DirectChannel`. Nếu yêu cầu là “mọi listener đều nhận cùng một event”, dùng `PublishSubscribeChannel` hoặc implementation broadcast phù hợp.

### ExecutorSubscribableChannel

Đây là implementation thuộc Spring Framework, trong module `spring-messaging`.

~~~java
SubscribableChannel channel = new ExecutorSubscribableChannel();
~~~

Constructor không tham số dùng thread của bên gọi để dispatch message. Có thể truyền một `Executor` nếu muốn gửi task xử lý qua executor:

~~~java
Executor executor = Executors.newFixedThreadPool(4);
SubscribableChannel channel = new ExecutorSubscribableChannel(executor);
~~~

Implementation này gửi message tới từng subscriber. Khi không truyền executor, handler được gọi trong thread thực hiện `send`; khi truyền executor, việc gọi handler được thực hiện thông qua executor.

Tên class có chữ `Executor` không có nghĩa constructor mặc định luôn chạy bất đồng bộ. No-argument constructor được tài liệu API mô tả rõ là chạy trong caller thread.

### DirectChannel

`DirectChannel` thuộc Spring Integration, không phải implementation nằm trong module `spring-messaging`.

~~~java
@Bean
MessageChannel ordersChannel() {
    return new DirectChannel();
}
~~~

`DirectChannel` có point-to-point semantics: một message được chuyển tới một handler được chọn trong số các subscriber. Khi có nhiều handler, cấu hình mặc định dùng round-robin load balancing và failover được bật. Khi failover xảy ra, dispatcher có thể thử handler kế tiếp nếu handler trước đó ném exception.

Mặc định, handler được gọi trực tiếp trong thread gửi. Điều này hữu ích khi cần giữ cùng call stack và transaction context qua ranh giới channel. Nếu handler ném exception đồng bộ, exception có thể truyền ngược về sender.

### PublishSubscribeChannel

`PublishSubscribeChannel` cũng thuộc Spring Integration. Nó phát cùng một message tới tất cả subscriber.

~~~java
@Bean
MessageChannel orderEventsChannel() {
    return new PublishSubscribeChannel();
}
~~~

Kênh này phù hợp với event notification: ví dụ một sự kiện OrderCreated cần được audit, cập nhật analytics và gửi notification. Các handler độc lập cùng nhận message.

Có thể cấu hình `TaskExecutor` để dispatch bất đồng bộ. Khi có executor, việc gửi thường không chờ tất cả handler hoàn tất. `minSubscribers` điều chỉnh số subscriber tối thiểu cần có để việc dispatch được xem là thành công; mặc định là 0.

### QueueChannel là loại khác

`QueueChannel` thuộc Spring Integration và triển khai `PollableChannel`, không phải `SubscribableChannel`.

- Message được lưu trong queue nội bộ.
- Consumer gọi `receive()` để lấy message.
- Nếu queue đầy, thao tác send có thể block hoặc timeout.
- Queue mặc định nằm trong bộ nhớ tiến trình; muốn persistence cần cấu hình MessageStore hoặc dùng broker-backed channel.

Không nhầm việc một channel có nhiều consumer với việc nó là SubscribableChannel. Pollable và subscribable là hai kiểu nhận message khác nhau.

## 6. Vòng dispatch của message

Một luồng subscribable channel cơ bản:

~~~mermaid
flowchart LR
    P["Producer"] --> M["Message"]
    M --> S["SubscribableChannel"]
    S --> R["Subscriber registry"]
    R --> H1["MessageHandler A"]
    R --> H2["MessageHandler B"]
    R --> HN["MessageHandler N"]
~~~

Trình tự tổng quát:

1. Producer tạo message, thường bằng `MessageBuilder`.
2. Producer gọi `channel.send(message)`.
3. Channel chạy các interceptor nếu có.
4. Implementation lấy danh sách subscriber hiện tại.
5. Dispatcher gọi handler theo semantics của implementation.
6. Handler xử lý payload và headers; có thể phát message tiếp theo.
7. Kết quả send hoặc lỗi được trả về/xử lý theo cách dispatch, executor và error handling đã cấu hình.

Không phải channel nào cũng thực hiện mọi bước giống nhau. Sơ đồ mô tả khái niệm; thứ tự, số handler và thread phụ thuộc implementation.

## 7. Đồng bộ, bất đồng bộ và thread

### Dispatch đồng bộ

Với `ExecutorSubscribableChannel()` không truyền executor hoặc Spring Integration `DirectChannel`, handler được gọi trong thread gửi.

~~~java
System.out.println("before");
channel.send(message);
System.out.println("after");
~~~

Nếu handler xử lý chậm, dòng `after` phải đợi handler hoàn tất. Nếu handler ném exception không được xử lý, exception có thể quay về caller.

Ưu điểm:

- Luồng điều khiển dễ theo dõi.
- Có thể giữ transaction context trong cùng thread với DirectChannel.
- Kết quả xử lý đồng bộ có thể ảnh hưởng trực tiếp đến kết quả lời gọi send.

Nhược điểm:

- Handler chậm làm chậm producer.
- Handler lỗi có thể làm lời gọi send thất bại.
- Không tách biệt tải xử lý giữa các thread.

### Dispatch bất đồng bộ

Khi cấu hình executor, channel gửi task tới executor:

~~~java
ExecutorService executor = Executors.newFixedThreadPool(4);
SubscribableChannel channel = new ExecutorSubscribableChannel(executor);
~~~

Lúc này:

- Handler có thể chạy trong thread khác.
- `send()` thường kết thúc sau khi task được chuyển cho executor, trước khi nghiệp vụ của handler hoàn tất.
- Exception xảy ra trong task không thể được ném ngược về sender theo call stack thông thường.
- Transaction gắn với thread gửi không tự động truyền sang thread xử lý.
- Thứ tự hoàn tất giữa các handler hoặc giữa nhiều message có thể thay đổi do scheduling.

Phải quản lý executor: giới hạn thread và queue, chính sách từ chối task, shutdown và quan sát lỗi. Một thread pool không giới hạn hoặc queue không giới hạn có thể khiến hệ thống tích lũy công việc vượt quá khả năng xử lý.

### send() true không phải business acknowledgement

`MessageChannel.send` trả về boolean. Ý nghĩa chính xác phụ thuộc implementation. Với `ExecutorSubscribableChannel`, message được gửi tới các subscriber theo implementation; nếu dùng executor, việc handler thực sự xử lý có thể xảy ra sau khi send trả về.

Do đó, không diễn giải `send() == true` thành:

- Tất cả handler đã hoàn tất nghiệp vụ.
- Dữ liệu đã được commit vào database.
- Message đã được lưu bền vững.
- Broker đã xác nhận message.
- Không có lỗi xảy ra trong xử lý bất đồng bộ.

Nếu nghiệp vụ cần xác nhận hoàn tất, hãy thiết kế reply/event trạng thái hoặc cơ chế acknowledgement riêng.

## 8. Xử lý lỗi trong MessageHandler

`MessageHandler.handleMessage` có thể ném `MessagingException`. Ví dụ:

~~~java
MessageHandler handler = message -> {
    String orderId = (String) message.getPayload();

    if (orderId.isBlank()) {
        throw new MessageHandlingException(
                message,
                "orderId must not be blank"
        );
    }

    processOrder(orderId);
};
~~~

Cần phân biệt lỗi theo mô hình dispatch:

- **Đồng bộ:** exception thường truyền về caller; với Spring Integration DirectChannel, hành vi này giống lời gọi Java thông thường.
- **Bất đồng bộ:** sender đã tiếp tục nên không thể nhận exception trực tiếp qua call stack. Cần error handler hoặc error channel phù hợp.
- **Nhiều subscriber:** một handler lỗi có thể ảnh hưởng các handler còn lại tùy dispatcher. Không giả định mọi subscriber luôn được gọi dù một handler trước đó ném exception.

Trong implementation `ExecutorSubscribableChannel`, nếu handler ném `MessagingException`, exception đó được ném tiếp; một exception khác thuộc loại `Exception` được bọc trong `MessageDeliveryException` bởi send task. Đây là lỗi dispatch/handling của Spring Messaging, không có nghĩa broker bên ngoài bị lỗi.

Spring Integration có cơ chế gửi lỗi dưới dạng `ErrorMessage` tới channel từ header `errorChannel` hoặc global `errorChannel` trong các task bất đồng bộ do Integration quản lý. Cơ chế này phụ thuộc Spring Integration flow và cấu hình; không phải bảo đảm chung của mọi `SubscribableChannel` trong Spring Framework.

Nên log message ID/correlation ID, handler name và exception type để điều tra. Tránh log payload hoặc headers nhạy cảm. Nếu có retry, cần bảo đảm handler idempotent để tránh lặp tác dụng phụ.

## 9. ChannelInterceptor và MessageHandler khác nhau thế nào?

Cả hai đều có thể tham gia vào đường đi của message nhưng trách nhiệm khác nhau:

| Thành phần | Vai trò |
|---|---|
| `MessageHandler` | Thực hiện nghiệp vụ hoặc xử lý message ở phía subscriber. |
| `ChannelInterceptor` | Can thiệp vào quá trình gửi/nhận của channel, ví dụ kiểm tra, bổ sung metadata, từ chối hoặc quan sát message. |

Một interceptor không phải là subscriber thay thế handler. Nó chạy quanh thao tác send/dispatch theo callback của channel. Một số interceptor có thể trả về `null` từ `preSend` để ngăn message tiếp tục đi qua channel.

Dùng handler cho xử lý nghiệp vụ. Dùng interceptor cho concern xuyên suốt như tracing, metrics, logging có kiểm soát hoặc kiểm tra chính sách chung.

## 10. Đăng ký handler trong Spring Integration

Nếu dùng Spring Integration, có thể đăng ký handler thủ công bằng `subscribe` hoặc khai báo endpoint để framework kết nối handler với channel.

Ví dụ annotation:

~~~java
@Service
public class OrderHandlers {

    @ServiceActivator(inputChannel = "ordersChannel")
    public void handle(OrderCreated event) {
        System.out.println("order=" + event.orderId());
    }
}
~~~

`@ServiceActivator` là annotation của Spring Integration. Endpoint được tạo từ phương thức sẽ đăng ký xử lý trên input channel khi application context khởi tạo.

Ví dụ khai báo channel:

~~~java
@Configuration
@EnableIntegration
public class MessagingConfiguration {

    @Bean
    public MessageChannel ordersChannel() {
        return new DirectChannel();
    }
}
~~~

Với cấu hình trên, phương thức `handle` là consumer của `ordersChannel`. Producer có thể gửi qua `MessageChannel` hoặc `MessagingTemplate`. Spring Integration quản lý endpoint lifecycle và subscription; thông thường không cần tự gọi `subscribe` trong mỗi request.

## 11. Ví dụ Java 17+ chạy được

Ví dụ dưới đây dùng `ExecutorSubscribableChannel` của Spring Framework. Channel được tạo không truyền executor nên dispatch diễn ra trong thread gọi `send()`. Chương trình đăng ký một handler, kiểm tra kết quả đăng ký trùng, gửi message rồi hủy đăng ký.

Cấu trúc project:

~~~text
subscribable-channel-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          SubscribableChannelDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>subscribable-channel-demo</artifactId>
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

### SubscribableChannelDemo.java

~~~java
package demo;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.SubscribableChannel;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class SubscribableChannelDemo {

    public static void main(String[] args) {
        SubscribableChannel channel = new ExecutorSubscribableChannel();

        MessageHandler handler = message ->
                System.out.println("received=" + message.getPayload());

        System.out.println("subscribed=" + channel.subscribe(handler));
        System.out.println("subscribedAgain=" + channel.subscribe(handler));

        Message<String> message = MessageBuilder
                .withPayload("order-42")
                .setHeader("source", "checkout-service")
                .build();

        System.out.println("sent=" + channel.send(message));

        System.out.println("unsubscribed=" + channel.unsubscribe(handler));
        System.out.println("unsubscribedAgain=" + channel.unsubscribe(handler));
    }
}
~~~

Chạy bằng Java 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.SubscribableChannelDemo
~~~

Kết quả stdout:

~~~text
subscribed=true
subscribedAgain=false
received=order-42
sent=true
unsubscribed=true
unsubscribedAgain=false
~~~

Giải thích:

1. `ExecutorSubscribableChannel` tạo registry subscriber.
2. `handler` là một `MessageHandler` được đăng ký.
3. Lần đăng ký đầu trả về `true`; lần đăng ký lại cùng reference trả về `false`.
4. `MessageBuilder` tạo message có payload `order-42` và header `source`.
5. `send` dispatch tới subscriber. Vì channel không dùng executor, handler chạy ngay trong caller thread.
6. `unsubscribe` trả về `true`; lần hủy tiếp theo trả về `false`.

Kết quả `sent=true` trong ví dụ cho biết thao tác send của implementation đã được chấp nhận. Nó không đại diện cho broker acknowledgement hoặc xác nhận nghiệp vụ từ một service bên ngoài.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Handler không nhận message | Chưa subscribe, đăng ký vào channel khác hoặc endpoint chưa khởi tạo. | Kiểm tra đúng bean/channel và vòng đời đăng ký. |
| Một message bị xử lý nhiều lần | Cùng một vai trò handler bị đăng ký lặp bằng các instance khác nhau. | Đăng ký một lần ở application lifecycle; giữ reference handler nếu cần unsubscribe. |
| Chỉ một handler nhận message | Dùng DirectChannel có semantics point-to-point. | Dùng PublishSubscribeChannel hoặc implementation broadcast nếu cần tất cả nhận. |
| Nhiều handler cùng nhận message | Dùng ExecutorSubscribableChannel hoặc PublishSubscribeChannel. | Chọn implementation theo semantics mong muốn. |
| Sender bị chậm | Handler chạy đồng bộ trong caller thread hoặc xử lý blocking. | Đánh giá executor/async channel và giới hạn thread pool. |
| Sender không bắt được lỗi handler | Handler chạy bất đồng bộ trong executor. | Cấu hình error handling/error channel phù hợp. |
| Gỡ đăng ký nhưng một task vẫn chạy | Task đã được dispatch trước khi unsubscribe. | Phối hợp shutdown, cancellation và vòng đời handler. |
| Nghĩ send thành công nghĩa là xử lý xong | Nhầm kết quả gửi với kết quả nghiệp vụ. | Dùng reply hoặc event xác nhận hoàn tất nếu cần. |
| Dùng QueueChannel nhưng gọi subscribe | QueueChannel là PollableChannel, không phải SubscribableChannel. | Consumer dùng receive hoặc poller. |

## 13. Checklist thiết kế subscriber

- [ ] Chọn channel theo semantics: một handler, nhiều handler hay queue/polling.
- [ ] Mỗi handler có trách nhiệm rõ ràng và có thể kiểm thử độc lập.
- [ ] Đăng ký subscriber ở đúng vòng đời application context.
- [ ] Giữ reference handler nếu cần unsubscribe.
- [ ] Không đăng ký lặp lại theo từng request.
- [ ] Quyết định rõ chạy đồng bộ hay bất đồng bộ.
- [ ] Nếu dùng executor, giới hạn tài nguyên và theo dõi task rejection/lỗi.
- [ ] Thiết kế error flow cho handler bất đồng bộ.
- [ ] Không giả định send là durable hoặc business acknowledgement.
- [ ] Làm handler idempotent nếu có retry/redelivery ở tầng bên ngoài.
- [ ] Không chia sẻ mutable state không an toàn giữa các handler/thread.
- [ ] Kiểm tra observability và không log dữ liệu nhạy cảm.

## Ghi nhớ

- `SubscribableChannel` mở rộng `MessageChannel` và quản lý registry của `MessageHandler`.
- `subscribe` và `unsubscribe` trả về boolean để báo trạng thái thêm/gỡ đăng ký.
- `MessageHandler` xử lý một `Message<?>` qua `handleMessage`; nó không trả reply bằng return value.
- Interface không quyết định một message được broadcast hay gửi cho một handler; implementation quyết định.
- `ExecutorSubscribableChannel` của Spring Framework dispatch tới từng subscriber; constructor mặc định chạy trong caller thread.
- `DirectChannel` của Spring Integration point-to-point; `PublishSubscribeChannel` broadcast; `QueueChannel` là pollable.
- Async dispatch tách thread sender và handler, nên error và transaction cần được thiết kế riêng.
- `send() == true` không chứng minh nghiệp vụ đã hoàn tất.

## Tài liệu chính thức

- [Spring Framework Javadoc: SubscribableChannel](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/SubscribableChannel.html)
- [Spring Framework Javadoc: MessageHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHandler.html)
- [Spring Framework Javadoc: ExecutorSubscribableChannel](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ExecutorSubscribableChannel.html)
- [Spring Integration: MessageChannel interface](https://docs.spring.io/spring-integration/reference/channel/interfaces.html)
- [Spring Integration: Message channel implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Integration: Configuring message channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html)
- [Spring Integration: Error handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
