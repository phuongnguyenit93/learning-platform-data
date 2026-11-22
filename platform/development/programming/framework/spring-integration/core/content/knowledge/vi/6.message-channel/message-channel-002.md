# SubscribableChannel

## 1. Mục tiêu và tình huống sử dụng

Trong Spring Integration Core, message channel nối nơi tạo thông điệp với các thành phần xử lý như transformer, filter, router và service activator. Khi một thành phần cần được gọi ngay lúc có thông điệp đến, mô hình đăng ký handler của `SubscribableChannel` là một cơ chế nền tảng.

Xét hệ thống nhận đơn hàng:

- Một lệnh đặt hàng cần được một bộ xử lý tiếp nhận.
- Sau khi đơn được chấp nhận, nhiều thành phần cần nhận sự kiện: ghi nhật ký, gửi thông báo, cập nhật thống kê.
- Một tác vụ chậm có thể cần chuyển sang worker thread.

Cả ba nhu cầu đều có thể dùng channel hỗ trợ đăng ký, nhưng phải chọn implementation phù hợp. Sau bài học, bạn cần giải thích được việc đăng ký handler, phân biệt phân phối một nơi với phát đến nhiều nơi, và dự đoán thread cũng như đường đi của lỗi.

Các ví dụ dùng API thuộc `spring-messaging` và `spring-integration-core`. Khi đặt trong ứng dụng Spring Boot, dùng bộ phiên bản dependency do dự án quản lý; không ghép tùy ý các phiên bản Spring Framework và Spring Integration. Những lớp Java đầy đủ bên dưới dùng cú pháp Java 17 trở lên.

## 2. Hợp đồng của SubscribableChannel

### 2.1. Interface nằm ở đâu?

`SubscribableChannel` thuộc package `org.springframework.messaging` của Spring Framework. Spring Integration cung cấp các implementation phục vụ luồng tích hợp.

Hợp đồng cốt lõi có thể biểu diễn như sau; `send` được kế thừa từ `MessageChannel`:

~~~java
public interface SubscribableChannel extends MessageChannel {

    boolean subscribe(MessageHandler handler);

    boolean unsubscribe(MessageHandler handler);
}
~~~

Handler được đăng ký là một `MessageHandler`:

~~~java
@FunctionalInterface
public interface MessageHandler {

    void handleMessage(Message<?> message) throws MessagingException;
}
~~~

Các khai báo này minh họa hợp đồng API. Trong ứng dụng, hãy import interface có sẵn; không tạo lại chúng.

`subscribe(handler)` trả về `true` nếu đăng ký được handler, `false` nếu handler đó đã được đăng ký. `unsubscribe(handler)` trả về `true` khi gỡ được đăng ký, `false` khi handler không có trong danh sách. Đây là kết quả thay đổi đăng ký, không phải kết quả xử lý một thông điệp. Xem [Javadoc SubscribableChannel](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/SubscribableChannel.html).

`MessageHandler.handleMessage` có kiểu trả về `void`. Nếu nghiệp vụ cần kết quả trả lời, hãy dùng endpoint có khả năng tạo reply và cơ chế request-reply, chẳng hạn gateway; việc đăng ký handler tự nó không tạo một giá trị trả về cho `send`. Xem [Javadoc MessageHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHandler.html).

### 2.2. Ai chịu trách nhiệm gì?

| Thành phần | Trách nhiệm trong ví dụ đơn hàng |
| --- | --- |
| `Message<?>` | Mang payload đơn hàng và header như mã truy vết |
| Producer hoặc gateway | Đưa thông điệp vào channel |
| `SubscribableChannel` | Quản lý đăng ký và chuyển thông điệp theo chính sách của implementation |
| `MessageHandler` | Thực hiện một bước xử lý |
| Consumer endpoint | Kết nối handler với channel, quản lý vòng đời trong Spring |

Producer chỉ cần biết channel đích. Producer không phải tự giữ danh sách các service xử lý đơn hàng.

### 2.3. Push khác với polling thế nào?

`SubscribableChannel` cung cấp `subscribe`; `PollableChannel` cung cấp `receive`. Với channel hỗ trợ đăng ký, thao tác gửi kích hoạt việc dispatch đến handler. Với channel có thể polling, phía nhận chủ động lấy thông điệp, trực tiếp hoặc thông qua poller của Spring Integration. Xem [Javadoc PollableChannel](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/PollableChannel.html).

~~~mermaid
flowchart LR
    P["Producer"] -->|"send(message)"| C["SubscribableChannel"]
    C --> D["Dispatcher"]
    D -->|"handleMessage(message)"| H["Handler được chọn"]
~~~

Sơ đồ chỉ mô tả quan hệ gọi. Implementation có thể chọn một handler hoặc nhiều handler, và có thể giao việc dispatch cho executor.

`SubscribableChannel` không khai báo `receive()`. Vì vậy, một endpoint nhận từ `DirectChannel` không cần poller chỉ để nhận message từ channel đó. Cũng không nên suy từ chữ “subscribe” rằng đây là Reactive Streams: hợp đồng này không có `request(n)` để điều tiết nhu cầu nhận.

## 3. Hai lựa chọn độc lập: nơi nhận và thread xử lý

### 3.1. Bảng so sánh các implementation thường gặp

| Implementation | Phân phối thông thường | Thread gọi handler | Đệm thông điệp tại channel |
| --- | --- | --- | --- |
| `DirectChannel` | Một handler xử lý thành công mỗi lần dispatch; failover có thể thử handler khác khi lỗi | Thread của bên gửi | Không có hàng đợi thông điệp |
| `ExecutorChannel` | Một handler xử lý thành công; có cấu hình cân bằng tải và failover | Do executor quyết định, thường là worker thread | Không phải `QueueChannel`; executor có thể có hàng đợi task |
| `PublishSubscribeChannel` không executor | Phát đến các handler đã đăng ký | Thread của bên gửi | Không giữ lịch sử để phát lại |
| `PublishSubscribeChannel` có executor | Phát đến các handler qua executor | Theo executor | Hàng đợi task, nếu có, không phải kho thông điệp bền vững |
| `QueueChannel`, để đối chiếu | Mỗi lần `receive` lấy một message | Do phía nhận hoặc poller quyết định | Có hàng đợi; triển khai `PollableChannel` |

`DirectChannel` gọi subscriber trong thread của bên gửi. `ExecutorChannel` giao dispatch cho executor; điều đó thay đổi ranh giới thực thi nhưng vẫn giữ mô hình phân phối một nơi. Xem [Javadoc DirectChannel](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/channel/DirectChannel.html) và [Javadoc ExecutorChannel](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/channel/ExecutorChannel.html).

Như vậy, cần trả lời riêng hai câu hỏi khi chọn channel:

1. Một message cần một bộ xử lý hay cần nhiều bên cùng nhận?
2. Các bước đó chạy trong thread hiện tại hay cần giao cho executor?

### 3.2. DirectChannel có nhiều subscriber

Hai handler cùng subscribe vào `DirectChannel` trở thành các bộ xử lý cạnh tranh. Chúng không mặc nhiên tạo thành hai bước nối tiếp.

~~~mermaid
flowchart LR
    P["Đơn hàng"] --> C["DirectChannel"]
    C -->|"chọn một nơi xử lý"| A["Worker A"]
    C -.->|"lựa chọn khác"| B["Worker B"]
~~~

Nếu A là kiểm tra tồn kho và B là trừ tiền, việc đăng ký cả hai vào một `DirectChannel` không tạo quy trình “kiểm tra rồi trừ tiền”. Hãy nối chúng thành các endpoint liên tiếp. Nếu A và B là hai worker cùng thực hiện một nghiệp vụ tương đương, mô hình cạnh tranh mới phù hợp.

### 3.3. Broadcast chưa chắc là song song

`new PublishSubscribeChannel()` gọi handler trong thread gửi. Có nhiều subscriber không làm chúng tự chạy đồng thời. Muốn giao xử lý cho executor, dùng constructor nhận `Executor`. Xem [Javadoc PublishSubscribeChannel](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/channel/PublishSubscribeChannel.html).

Một nhánh broadcast có lỗi cũng có thể ảnh hưởng nhánh khác. Với dispatch đồng bộ và `ignoreFailures=false` mặc định, lỗi có thể ngăn những handler phía sau được gọi. Hãy xem broadcast là chính sách phân phối, không phải bảo đảm mọi tác dụng phụ đều thành công. Xem [Javadoc BroadcastingDispatcher](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/dispatcher/BroadcastingDispatcher.html).

## 4. Thực hành API đăng ký trực tiếp

Đây là chương trình độc lập minh họa đăng ký, gửi và gỡ đăng ký. Chương trình cần `spring-integration-core` cùng dependency Spring tương thích trên classpath.

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.SubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class SubscriptionDemo {

    public static void main(String[] args) {
        SubscribableChannel orders = new DirectChannel();
        List<String> received = new ArrayList<>();

        MessageHandler handler = message -> {
            String orderId = (String) message.getPayload();
            received.add(orderId);
            System.out.println(
                    orderId + " được xử lý bởi "
                            + Thread.currentThread().getName());
        };

        System.out.println(orders.subscribe(handler));   // true
        System.out.println(orders.subscribe(handler));   // false

        boolean sent = orders.send(
                MessageBuilder.withPayload("ORDER-1001")
                        .setHeader("traceId", "trace-1001")
                        .build());

        System.out.println(sent);                       // true
        System.out.println(received);                   // [ORDER-1001]

        System.out.println(orders.unsubscribe(handler)); // true
        System.out.println(orders.unsubscribe(handler)); // false
    }
}
~~~

`received` đã chứa phần tử khi `send` trả về vì handler đang chạy đồng bộ. `ArrayList` ở đây phù hợp với tình huống minh họa một thread; không được dùng kết luận này để chia sẻ cùng danh sách giữa nhiều worker mà không có cơ chế đồng bộ.

Giữ tham chiếu đến handler nếu cần gỡ đăng ký. Hai biểu thức lambda viết giống nhau không phải là cách đáng tin cậy để tham chiếu cùng một handler:

~~~java
MessageHandler handler = message -> process(message);
channel.subscribe(handler);

// Khi cần tháo kết nối:
channel.unsubscribe(handler);
~~~

Đoạn ngắn trên giả định `channel` là `SubscribableChannel` và `process` là phương thức nghiệp vụ có sẵn.

Đăng ký chỉ có hiệu lực với thông điệp được gửi trong thời gian handler đang được kết nối. Các channel dispatch trực tiếp nêu trên không lưu những thông điệp cũ để phát lại cho subscriber mới.

## 5. Endpoint đăng ký handler thay ứng dụng

Trong ứng dụng thực tế, bạn thường khai báo flow thay vì gọi `subscribe` bằng tay. `EventDrivenConsumer` là endpoint nối `MessageHandler` với `SubscribableChannel`; vòng đời endpoint quản lý việc kết nối và tháo kết nối. Xem [Javadoc EventDrivenConsumer](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/endpoint/EventDrivenConsumer.html).

Điều này giúp phân biệt ba tình huống:

- Có một bean nghiệp vụ chưa có nghĩa bean đã trở thành subscriber.
- Khai báo một `IntegrationFlow` có input channel và handler tạo ra cấu hình endpoint tương ứng.
- Một endpoint chưa chạy hoặc đã dừng có thể khiến channel không còn subscriber dự kiến.

Khi chẩn đoán lỗi “không có subscriber”, hãy kiểm tra cả việc tạo bean, tên channel và trạng thái endpoint.

## 6. Ví dụ Java DSL: nhận lệnh rồi phát sự kiện

### 6.1. Yêu cầu của luồng

Ta muốn:

1. Nhận một `Order` vào `orderInput`.
2. Từ chối đơn có giá trị không dương.
3. Chuyển đơn hợp lệ thành `OrderAccepted`.
4. Phát sự kiện đến hai nhánh độc lập.
5. Thu kết quả mỗi nhánh vào một queue để quan sát và kiểm thử.

~~~mermaid
flowchart LR
    P["Producer hoặc gateway"] --> I["orderInput: DirectChannel"]
    I --> F["Filter: totalCents > 0"]
    F --> T["Transformer: OrderAccepted"]
    T --> E["orderEvents: PublishSubscribeChannel"]
    E --> A["Nhánh audit"]
    E --> N["Nhánh notification"]
    A --> Q1["auditResults: QueueChannel"]
    N --> Q2["notificationResults: QueueChannel"]
~~~

Hai queue cuối là nơi thu kết quả cho bài thực hành. Trong hệ thống thật, có thể thay các nhánh này bằng service activator hoặc adapter đến hệ thống ngoài.

### 6.2. Cấu hình đầy đủ

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class OrderFlowConfiguration {

    public record Order(String id, long totalCents) {
    }

    public record OrderAccepted(String id, long totalCents) {
    }

    @Bean
    public DirectChannel orderInput() {
        DirectChannel channel = new DirectChannel();
        channel.setFailover(false);
        return channel;
    }

    @Bean
    public PublishSubscribeChannel orderEvents() {
        return new PublishSubscribeChannel(true);
    }

    @Bean
    public QueueChannel auditResults() {
        return new QueueChannel(100);
    }

    @Bean
    public QueueChannel notificationResults() {
        return new QueueChannel(100);
    }

    @Bean
    public IntegrationFlow acceptOrder(
            @Qualifier("orderInput") DirectChannel input,
            @Qualifier("orderEvents") PublishSubscribeChannel events) {

        return IntegrationFlow.from(input)
                .<Order>filter(
                        order -> order.totalCents() > 0,
                        endpoint -> endpoint.throwExceptionOnRejection(true))
                .<Order, OrderAccepted>transform(
                        order -> new OrderAccepted(
                                order.id(), order.totalCents()))
                .channel(events)
                .get();
    }

    @Bean
    public IntegrationFlow auditBranch(
            @Qualifier("orderEvents") PublishSubscribeChannel events,
            @Qualifier("auditResults") QueueChannel results) {

        return IntegrationFlow.from(events)
                .channel(results)
                .get();
    }

    @Bean
    public IntegrationFlow notificationBranch(
            @Qualifier("orderEvents") PublishSubscribeChannel events,
            @Qualifier("notificationResults") QueueChannel results) {

        return IntegrationFlow.from(events)
                .channel(results)
                .get();
    }
}
~~~

Java DSL xây dựng và đăng ký các thành phần của flow trong application context. Khi không chỉ định channel khác giữa các endpoint, DSL thường nối chúng bằng `DirectChannel`. Những nhánh chỉ nối hai channel được thực hiện qua bridge endpoint. Xem [Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html) và [Message Channels trong Java DSL](https://docs.spring.io/spring-integration/reference/dsl/java-channels.html).

Trong cấu hình này:

- Endpoint filter nhận message từ `orderInput`; bạn không gọi `subscribe` thêm lần nữa.
- Transformer tạo payload sự kiện rồi gửi đến `orderEvents`.
- Hai endpoint bridge ở đầu hai nhánh cùng nhận sự kiện broadcast.
- `true` trong `new PublishSubscribeChannel(true)` yêu cầu có subscriber; nó không có nghĩa bật xử lý bất đồng bộ.
- Hai queue có dung lượng hữu hạn. Khi queue đầy, việc gửi có thể chờ; một nhánh chậm có thể làm chậm đường gửi đồng bộ.

Các ví dụ thực hành chỉ gửi ít message để tránh đầy queue. Khi vận hành, cần chính sách về sức chứa, tốc độ tiêu thụ và timeout ở nơi gửi thích hợp.

### 6.3. Gửi và quan sát kết quả

Đặt lớp sau cạnh `OrderFlowConfiguration`:

~~~java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public class OrderFlowDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                OrderFlowConfiguration.class)) {

            MessageChannel input =
                    context.getBean("orderInput", MessageChannel.class);

            QueueChannel audit =
                    context.getBean("auditResults", QueueChannel.class);

            QueueChannel notifications =
                    context.getBean("notificationResults", QueueChannel.class);

            input.send(
                    MessageBuilder.withPayload(
                                    new OrderFlowConfiguration.Order(
                                            "ORDER-1001", 250_000))
                            .setHeader("traceId", "trace-1001")
                            .build());

            Message<?> audited = audit.receive(0);
            Message<?> notified = notifications.receive(0);

            if (audited == null || notified == null) {
                throw new IllegalStateException(
                        "Thiếu kết quả ở một nhánh");
            }

            System.out.println(audited.getPayload());
            System.out.println(notified.getPayload());
            System.out.println(
                    audited.getHeaders().get("traceId"));
        }
    }
}
~~~

Cả hai nhánh nhận payload `OrderAccepted` cho đơn `ORDER-1001`. `receive(0)` đủ cho ví dụ này vì toàn bộ đường gửi đến hai queue chạy đồng bộ trước khi `input.send` trả về.

Nếu đổi `orderEvents` sang dạng có executor, giả định trên không còn phù hợp: bên gửi có thể chạy tiếp trước khi worker ghi kết quả. Khi đó cần chờ có giới hạn bằng `receive(timeout)` hoặc cơ chế đồng bộ trong bài kiểm thử.

## 7. Cân bằng tải, failover và số lần xử lý

`DirectChannel` mặc định dùng round-robin và bật failover. Khi handler được chọn ném lỗi, dispatcher có thể thử handler tiếp theo. Vì thế “point-to-point” không phải cam kết rằng chỉ một handler từng được gọi trong mọi tình huống lỗi. Xem [DirectChannel Configuration](https://docs.spring.io/spring-integration/reference/channel/configuration.html#channel-configuration-directchannel).

Ví dụ nghiệp vụ do bài học đặt ra:

1. Worker A ghi đơn hàng xuống cơ sở dữ liệu.
2. A gặp lỗi khi gọi hệ thống ngoài sau khi đã ghi dữ liệu.
3. Dispatcher thử worker B.
4. B có thể tạo thêm tác dụng phụ nếu không nhận diện đơn đã xử lý.

Có thể cấu hình để lỗi dừng tại handler được chọn:

~~~java
DirectChannel commands = new DirectChannel();
commands.setFailover(false);
~~~

Cấu hình này không tạo bảo đảm “exactly once”. Để tránh ghi trùng nghiệp vụ, cần khóa nghiệp vụ hoặc thiết kế idempotent dựa trên mã đơn và giao dịch phù hợp.

Cũng cần phân biệt:

| Khái niệm | Điều xảy ra |
| --- | --- |
| Load balancing | Chọn handler nào nhận message trước |
| Failover | Thử handler khác khi handler được chọn lỗi |
| Retry | Thực hiện lại một thao tác theo chính sách thử lại |
| Broadcast | Chủ động gửi message đến nhiều subscriber |

Nếu các handler là những bước nghiệp vụ khác nhau, hãy mô tả thứ tự bằng flow. Thứ tự subscriber không thay thế cấu trúc quy trình.

## 8. Đổi thread với ExecutorChannel

### 8.1. Cấu hình một channel bất đồng bộ trong Spring

Cấu hình sau là ví dụ riêng, không phải phần thay thế ngầm cho lớp cấu hình đơn hàng:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageHandler;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableIntegration
public class AsyncJobConfiguration {

    @Bean
    public ThreadPoolTaskExecutor integrationExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(50);
        executor.setThreadNamePrefix("integration-worker-");
        return executor;
    }

    @Bean
    public ExecutorChannel asyncJobs(
            @Qualifier("integrationExecutor")
            ThreadPoolTaskExecutor executor) {

        ExecutorChannel channel = new ExecutorChannel(executor);
        channel.setFailover(false);
        return channel;
    }

    @Bean
    public QueueChannel jobErrors() {
        return new QueueChannel(20);
    }

    @Bean
    public IntegrationFlow jobFlow(
            @Qualifier("asyncJobs") ExecutorChannel jobs) {

        return IntegrationFlow.from(jobs)
                .handle((MessageHandler) message -> {
                    String job = (String) message.getPayload();

                    if ("FAIL".equals(job)) {
                        throw new IllegalArgumentException(
                                "Không thực hiện được tác vụ");
                    }

                    System.out.println(
                            job + " chạy trên "
                                    + Thread.currentThread().getName());
                })
                .get();
    }
}
~~~

Spring quản lý khởi tạo và đóng `ThreadPoolTaskExecutor` vì executor được khai báo thành bean. Số thread và sức chứa queue ở đây phục vụ minh họa; phải chọn lại theo tải và thời gian xử lý của ứng dụng. Xem [Javadoc ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html).

Hàng đợi của executor chứa task trong bộ nhớ. Nó không cung cấp khả năng khôi phục message sau khi tiến trình dừng như một thiết kế dùng kho thông điệp bền vững.

### 8.2. Quan sát lỗi phát sinh trong worker

Chạy đoạn sau trong ứng dụng có `AsyncJobConfiguration`:

~~~java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;

public class AsyncJobDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                AsyncJobConfiguration.class)) {

            MessageChannel jobs =
                    context.getBean("asyncJobs", MessageChannel.class);

            QueueChannel errors =
                    context.getBean("jobErrors", QueueChannel.class);

            jobs.send(
                    MessageBuilder.withPayload("FAIL")
                            .setErrorChannel(errors)
                            .build());

            Message<?> received = errors.receive(2_000);

            if (!(received instanceof ErrorMessage error)) {
                throw new IllegalStateException(
                        "Không nhận được ErrorMessage trong thời hạn");
            }

            System.out.println(error.getPayload().getMessage());
        }
    }
}
~~~

Trong hạ tầng Spring Integration được quản lý như trên, lỗi của task bất đồng bộ được chuyển thành `ErrorMessage`. Đường xử lý lỗi ưu tiên header `errorChannel`; nếu không có, dùng channel toàn cục tên `errorChannel`. Ví dụ chỉ thu lỗi để quan sát; ứng dụng thực tế còn phải quyết định ghi nhận, thử lại hay chuyển đến nơi xử lý lỗi cuối cùng. Xem [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

Không suy rộng hành vi này sang mọi `Executor` hoặc mọi channel tự tạo ngoài application context. Việc truyền lỗi phụ thuộc cả channel lẫn hạ tầng xử lý lỗi đã được thiết lập.

## 9. send thành công có nghĩa gì?

`MessageChannel.send` trả về `boolean` và cũng có thể ném exception. `true` thể hiện thao tác gửi thành công theo hợp đồng channel; nó không phải một biên nhận hoàn tất nghiệp vụ từ đầu đến cuối. Xem [Javadoc MessageChannel](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageChannel.html).

| Trường hợp | Cách hiểu kết quả gửi |
| --- | --- |
| Handler đồng bộ xử lý và trả về bình thường | Việc gọi handler đã kết thúc trên đường thực thi đó |
| Giao task cho executor thành công | Tác vụ được tiếp nhận; worker có thể chưa hoàn tất |
| Handler ghi thêm việc vào hệ thống ngoài | Chưa đủ bằng chứng rằng hệ thống ngoài đã hoàn thành việc |
| Muốn biết đơn hàng được xử lý thành công | Cần reply, sự kiện kết quả hoặc trạng thái nghiệp vụ rõ ràng |

### 9.1. Không có subscriber

Không được suy rằng mọi implementation đều trả `false` khi không có handler:

- Với `DirectChannel`, thiếu subscriber làm thao tác dispatch thất bại và thường được quan sát dưới dạng lỗi gửi message.
- Với `PublishSubscribeChannel` tạo mặc định, `minSubscribers` mặc định bằng `0`; một lần gửi có thể được coi là thành công dù chưa có nơi nhận.
- Constructor `PublishSubscribeChannel(true)` yêu cầu có subscriber. Nếu yêu cầu nghiệp vụ là phải có nhiều nhánh nhất định, cần thêm cấu hình và kiểm tra tương ứng.

Các đặc điểm về subscriber tối thiểu được mô tả tại [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html). Việc có đủ subscriber vẫn không chứng minh tất cả tác dụng phụ đã hoàn thành, đặc biệt khi dùng executor.

### 9.2. Timeout không tự dừng handler

Lời gọi:

~~~java
channel.send(message, 1_000);
~~~

không nên được hiểu là “sau một giây, mọi handler sẽ bị ngắt”.

Chẳng hạn, handler của `DirectChannel` có thể gọi HTTP và chờ lâu hơn một giây. Muốn giới hạn thao tác HTTP, phải cấu hình timeout của HTTP client. Với request-reply, cần xem thêm timeout chờ reply; với executor, cần xem thêm chính sách tiếp nhận và từ chối task.

## 10. Lỗi, giao dịch và trạng thái dùng chung

### 10.1. Lỗi trên đường đồng bộ

Với đường gọi đồng bộ, lỗi không được xử lý có thể truyền ngược về bên gửi. Chỉ gắn header `errorChannel` vào message rồi gửi vào `DirectChannel` không tự biến lỗi đó thành xử lý bất đồng bộ. Gateway có thể có chính sách xử lý lỗi riêng; cần đọc cấu hình tại điểm vào của flow.

Với đường có worker thread, `try/catch` quanh `send` vẫn hữu ích cho lỗi gửi hoặc executor từ chối task, nhưng không bắt được một lỗi nghiệp vụ xảy ra muộn trong worker như một lời gọi đồng bộ thông thường.

### 10.2. Ranh giới giao dịch

Một chuỗi xử lý bằng `DirectChannel` có thể tham gia giao dịch đang tồn tại trên thread gửi nếu những thành phần truy cập tài nguyên được cấu hình để tham gia giao dịch đó. Channel không tự mở giao dịch và không tự biến nhiều hệ thống ngoài thành một giao dịch nguyên tử.

Khi đi qua `ExecutorChannel`, đừng giả định giao dịch dựa trên thread của producer tự truyền sang worker. Worker có thể cần giao dịch riêng. Nếu producer cần đồng bộ việc ghi dữ liệu và phát sự kiện bền vững, phải thiết kế cơ chế phối hợp phù hợp ở cấp nghiệp vụ.

### 10.3. Đồng thời và thứ tự

Một `DirectChannel` không tạo worker mới, nhưng nhiều producer vẫn có thể gửi đồng thời từ nhiều thread. Do đó, một handler singleton vẫn có thể bị gọi đồng thời.

Khi thiết kế handler:

- Ưu tiên trạng thái cục bộ trong mỗi lần xử lý.
- Nếu chia sẻ bộ nhớ, dùng cấu trúc và cơ chế đồng bộ phù hợp.
- Không giả định một `Message` sẽ làm payload mutable bên trong trở nên bất biến.
- Với broadcast, tránh sửa một đối tượng payload chung ở nhiều nhánh.
- Khi có executor nhiều thread, không giả định thứ tự hoàn tất giống thứ tự gửi.

Ví dụ, `OrderAccepted` ở trên chỉ chứa `String` và `long` nên phù hợp để chia sẻ như một giá trị bất biến. Nếu payload chứa `List` hoặc `Map` có thể sửa, cần bảo vệ hoặc sao chép dữ liệu theo yêu cầu từng nhánh.

## 11. Quan sát mà không tạo thêm consumer cạnh tranh

Giả sử `orderInput` là `DirectChannel`. Thêm một handler “chỉ để ghi log” bằng `subscribe` sẽ tạo thêm consumer cạnh tranh với endpoint xử lý đơn. Một số message có thể đi đến handler log thay vì quy trình nghiệp vụ.

Để quan sát đường gửi, có thể dùng `ChannelInterceptor` hoặc wire tap. Với `SubscribableChannel`, các callback `preReceive` và `postReceive` không phải điểm quan sát phù hợp vì không có thao tác `receive`. Xem [Channel Interceptors](https://docs.spring.io/spring-integration/reference/channel/interceptors.html).

Ví dụ thêm interceptor vào bean `DirectChannel`:

~~~java
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;

public class ObservedChannelFactory {

    public static DirectChannel create() {
        DirectChannel channel = new DirectChannel();

        channel.addInterceptor(new ChannelInterceptor() {
            @Override
            public void afterSendCompletion(
                    Message<?> message,
                    MessageChannel target,
                    boolean sent,
                    Exception exception) {

                System.out.println(
                        "traceId=" + message.getHeaders().get("traceId")
                                + ", sent=" + sent
                                + ", failed=" + (exception != null));
            }
        });

        return channel;
    }
}
~~~

Trong ứng dụng thực tế, đưa thông tin vào hệ thống log hoặc metric thích hợp. Với channel bất đồng bộ, callback hoàn tất gửi không thể được dùng thay cho metric hoàn tất nghiệp vụ trong worker.

## 12. Kiểm thử hành vi quan trọng

Các bài kiểm thử bên dưới dùng JUnit Jupiter và lớp `OrderFlowConfiguration` ở phần 6. Chúng tập trung vào hành vi quan sát được: cùng thread, broadcast đến đủ nhánh, và phản hồi khi không có subscriber.

### 12.1. Handler DirectChannel chạy trước khi send trả về

~~~java
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.support.GenericMessage;

import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DirectChannelThreadTest {

    @Test
    void invokesHandlerOnSenderThread() {
        DirectChannel channel = new DirectChannel();
        AtomicReference<Thread> invokedOn = new AtomicReference<>();
        Thread sender = Thread.currentThread();

        channel.subscribe(message ->
                invokedOn.set(Thread.currentThread()));

        boolean sent = channel.send(new GenericMessage<>("ORDER-1001"));

        assertTrue(sent);
        assertSame(sender, invokedOn.get());
    }
}
~~~

Bài kiểm thử dùng danh tính đối tượng `Thread`, không so sánh tên thread và không cần `Thread.sleep`.

### 12.2. Một sự kiện đến cả hai nhánh

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OrderBroadcastTest {

    @Test
    void deliversAcceptedOrderToBothBranches() {
        try (var context = new AnnotationConfigApplicationContext(
                OrderFlowConfiguration.class)) {

            MessageChannel input =
                    context.getBean("orderInput", MessageChannel.class);
            QueueChannel audit =
                    context.getBean("auditResults", QueueChannel.class);
            QueueChannel notifications =
                    context.getBean("notificationResults", QueueChannel.class);

            assertTrue(input.send(
                    MessageBuilder.withPayload(
                                    new OrderFlowConfiguration.Order(
                                            "ORDER-1001", 250_000))
                            .setHeader("traceId", "trace-1001")
                            .build()));

            Message<?> auditMessage = audit.receive(0);
            Message<?> notificationMessage = notifications.receive(0);

            assertNotNull(auditMessage);
            assertNotNull(notificationMessage);

            var expected = new OrderFlowConfiguration.OrderAccepted(
                    "ORDER-1001", 250_000);

            assertEquals(expected, auditMessage.getPayload());
            assertEquals(expected, notificationMessage.getPayload());

            assertEquals(
                    "trace-1001",
                    auditMessage.getHeaders().get("traceId"));
            assertEquals(
                    "trace-1001",
                    notificationMessage.getHeaders().get("traceId"));

            assertNull(audit.receive(0));
            assertNull(notifications.receive(0));
        }
    }
}
~~~

Nếu vô tình đổi `orderEvents` thành `DirectChannel`, bài kiểm thử sẽ phát hiện một nhánh không nhận được kết quả. Nếu thêm executor, phải sửa cách chờ kết quả để phản ánh ranh giới bất đồng bộ.

### 12.3. So sánh channel rỗng

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.GenericMessage;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class EmptyChannelTest {

    @Test
    void directChannelWithoutSubscriberFails() {
        DirectChannel channel = new DirectChannel();

        assertThrows(
                MessagingException.class,
                () -> channel.send(new GenericMessage<>("ORDER-1001")));
    }

    @Test
    void defaultPublishSubscribeChannelAllowsNoSubscribers() {
        PublishSubscribeChannel channel = new PublishSubscribeChannel();

        assertTrue(channel.send(new GenericMessage<>("OrderAccepted")));
    }

    @Test
    void requiredSubscriberPreventsSilentEmptyBroadcast() {
        PublishSubscribeChannel channel = new PublishSubscribeChannel(true);

        assertThrows(
                MessagingException.class,
                () -> channel.send(new GenericMessage<>("OrderAccepted")));
    }
}
~~~

Các kiểm thử này không khẳng định bảo đảm giao nhận bền vững. Chúng chỉ mô tả hành vi của các implementation và cấu hình cụ thể.

## 13. Lỗi thường gặp và cách kiểm tra

| Biểu hiện | Nguyên nhân cần xem xét | Hướng kiểm tra |
| --- | --- | --- |
| Chỉ một trong hai bước nghiệp vụ được chạy | Hai bước subscribe vào cùng `DirectChannel` | Kiểm tra flow có nối tuần tự đúng yêu cầu không |
| Một nhánh broadcast không nhận message | Endpoint chưa chạy, nối sai channel, hoặc nhánh trước bị lỗi | Kiểm tra bean, vòng đời endpoint và đường lỗi |
| Gửi thành công nhưng chưa có kết quả | Worker chưa xong hoặc broadcast cho phép không có subscriber | Kiểm tra executor, kết quả nghiệp vụ và yêu cầu subscriber |
| Bên gửi không bắt được lỗi trong worker | Đã có ranh giới bất đồng bộ | Kiểm tra `errorChannel` và consumer xử lý lỗi |
| Một handler xử lý message hai lần về mặt nghiệp vụ | Có retry, failover hoặc gửi lại từ nguồn | Đối chiếu mã nghiệp vụ và thiết kế idempotent |
| Gắn log vào channel làm thiếu đơn hàng | Handler log cạnh tranh với handler nghiệp vụ | Chuyển sang interceptor hoặc thiết kế quan sát phù hợp |
| Đổi sang executor làm mất kỳ vọng giao dịch | Giao dịch cũ gắn với thread gửi | Xác định lại điểm bắt đầu và kết thúc giao dịch |
| Dữ liệu payload thay đổi bất thường giữa các nhánh | Nhiều nhánh sửa chung đối tượng | Kiểm tra tính bất biến và quyền sở hữu dữ liệu |

Khi log, ưu tiên tên channel, mã truy vết, mã nghiệp vụ và thông tin lỗi cần thiết. Đừng kết luận đã hoàn tất đơn hàng chỉ từ một dòng log “send=true”.

## 14. Bài thực hành củng cố

1. Dùng `DirectChannel` và hai handler tương đương, gửi sáu message khi không có lỗi. Đếm số lần mỗi handler được gọi. Không đưa tác dụng phụ thật vào thử nghiệm này.
2. Giữ hai handler, cho một handler ném exception. So sánh bật và tắt failover; ghi lại handler nào từng được gọi cho từng message.
3. Đổi channel của thí nghiệm đầu thành `PublishSubscribeChannel`. Kiểm tra mỗi handler nhận đủ sáu message khi tất cả đều xử lý thành công.
4. Đổi `orderEvents` sang cấu hình có executor và sửa kiểm thử để chờ kết quả có giới hạn, không dùng sleep cố định.
5. Gửi `Order` với `totalCents=0` vào flow phần 6. Kiểm tra bên gửi nhận lỗi và cả hai queue kết quả đều rỗng.
6. Cho tác vụ phần 8 ném lỗi và quan sát `ErrorMessage`. Xác định lỗi gốc cùng thông tin message cần để đối chiếu nghiệp vụ.

Tiêu chí hoàn thành là giải thích được vì sao kết quả thay đổi khi đổi implementation, cấu hình failover hoặc ranh giới thread. Việc thuộc tên interface chưa đủ để dự đoán hành vi của một flow.
