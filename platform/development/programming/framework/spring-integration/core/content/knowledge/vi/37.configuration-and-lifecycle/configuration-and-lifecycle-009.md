# TaskScheduler trong Spring Integration

Trong module **SPRING_INTEGRATION_CORE**, `TaskScheduler` là thành phần hạ tầng giúp các endpoint thực hiện công việc theo thời gian. Hiểu thành phần này giúp bạn thiết kế luồng thông điệp có nhịp xử lý phù hợp, tránh để một handler chậm làm đình trệ những luồng khác, đồng thời quản lý việc khởi động và dừng ứng dụng.

Bài học thuộc chương **Cấu hình và lifecycle**, tập trung vào mối quan hệ giữa scheduler, poller, channel và endpoint. Các ví dụ sử dụng Java 17+, API Spring Integration 6.5 và Spring Framework 6.2; phiên bản thư viện cần được quản lý đồng bộ bằng BOM hoặc phiên bản Spring Boot phù hợp. Đây là phạm vi của ví dụ, không phải khẳng định về phiên bản đang có trong một dự án cụ thể.

Sau bài học, bạn có thể:

- Xác định endpoint nào cần lập lịch và endpoint nào hoạt động theo sự kiện.
- Phân biệt `TaskScheduler`, `Trigger`, poller và `TaskExecutor`.
- Cấu hình scheduler dùng chung và executor cho một poller bằng Java DSL.
- Lựa chọn fixed delay, fixed rate hoặc cron theo yêu cầu xử lý.
- Quan sát tình trạng thiếu luồng, xử lý lỗi bất đồng bộ và điều khiển lifecycle của endpoint.

## 1. TaskScheduler giải quyết vấn đề gì?

Giả sử ứng dụng nhận đơn hàng vào một `QueueChannel`. Việc gửi thông điệp vào channel chỉ đưa thông điệp vào hàng đợi. Cần có một consumer chủ động lấy thông điệp ra và chuyển cho handler.

Với một polling endpoint thông thường, quá trình đó có ba phần:

1. `Trigger` xác định lần thực thi tiếp theo.
2. `TaskScheduler` sắp xếp thực thi tác vụ theo thời điểm đó.
3. Polling endpoint thực hiện thao tác nhận thông điệp và gọi handler.

Scheduler không tự hiểu đơn hàng, quy tắc định tuyến hay cách biến đổi payload. Những trách nhiệm đó thuộc về các thành phần của luồng tích hợp.

| Thành phần | Trách nhiệm | Ví dụ trong luồng đơn hàng |
| --- | --- | --- |
| `Message` | Mang payload và headers | Một đơn hàng cùng mã tương quan |
| `MessageChannel` | Kết nối producer với consumer | `QueueChannel` chứa đơn đang chờ |
| `Trigger` | Tính thời điểm thực thi tiếp theo | Sau mỗi lần hoàn tất, chờ 500 ms |
| `TaskScheduler` | Lập lịch và kích hoạt tác vụ | Đánh thức tác vụ polling |
| Polling endpoint | Điều phối việc nhận và xử lý | Lấy tối đa 5 thông điệp mỗi lượt |
| `TaskExecutor` | Thực thi tác vụ được giao | Chạy polling task trên pool riêng |
| Handler | Thực hiện nghiệp vụ | Kiểm tra số lượng rồi chấp nhận đơn |

`TaskScheduler` thuộc Spring Framework. Spring Integration sử dụng abstraction này trong hạ tầng của các endpoint có nhu cầu lập lịch. Các API cơ bản bao gồm lập lịch một lần, lập lịch theo `Trigger`, fixed rate và fixed delay; kết quả thường là một `ScheduledFuture<?>` để theo dõi hoặc hủy tác vụ. Xem [API TaskScheduler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/TaskScheduler.html).

## 2. Endpoint nào cần scheduler?

### 2.1. Consumer lấy thông điệp từ PollableChannel

Một service activator đọc từ `QueueChannel` cần polling endpoint vì channel không đẩy thông điệp trực tiếp vào handler.

~~~text
Producer -> QueueChannel -> PollingConsumer -> Handler
                                  ^
                                  |
                         TaskScheduler + Trigger
~~~

Khi cấu hình một handler trên pollable channel, bạn cần cung cấp cấu hình poller trực tiếp hoặc có default poller phù hợp.

### 2.2. Inbound adapter thăm dò nguồn dữ liệu

Một nguồn dữ liệu có thể không tự phát sự kiện. Ví dụ, ứng dụng phải định kỳ gọi một `MessageSource` để tìm dữ liệu mới. `SourcePollingChannelAdapter` đảm nhiệm việc gọi nguồn và gửi kết quả vào channel đầu ra.

~~~text
TaskScheduler -> SourcePollingChannelAdapter -> MessageSource.receive()
                              |
                              v
                        Output channel
~~~

Nếu nguồn trả về `null`, lần nhận đó không tạo thông điệp đầu ra. Chu kỳ polling vẫn có thể tiếp tục ở lần kích hoạt sau.

### 2.3. Consumer nhận sự kiện qua SubscribableChannel

Với `DirectChannel`, handler được gọi đồng bộ khi có thông điệp gửi đến. Endpoint đó không cần poller chỉ để nhận thông điệp.

Với `ExecutorChannel`, việc dispatch sử dụng executor của channel; điều này cũng không biến channel thành một hàng đợi cần poller.

Sự khác biệt nằm ở cách endpoint nhận thông điệp, không nằm ở việc handler là transformer, filter, router hay service activator. Cùng một loại handler có thể được đặt sau những loại channel khác nhau. Xem [Poller](https://docs.spring.io/spring-integration/reference/polling-consumer.html) và [Message Endpoints](https://docs.spring.io/spring-integration/reference/6.5/endpoint.html).

## 3. Ranh giới luồng: hiểu trước khi chỉnh pool size

### 3.1. Poller không có executor riêng

`ThreadPoolTaskScheduler` thực thi tác vụ bằng chính các luồng scheduler. Nó không mặc nhiên chuyển công việc sang một pool nghiệp vụ khác.

~~~mermaid
sequenceDiagram
    participant S as Scheduler thread
    participant Q as QueueChannel
    participant H as Handler
    S->>Q: receive(timeout)
    Q-->>S: Message
    S->>H: handleMessage(message)
    Note over S,H: Scheduler thread chạy cả handler
    H-->>S: Hoàn tất
~~~

Nếu handler gọi một dịch vụ mất ba giây, scheduler thread có thể bị giữ trong suốt ba giây đó. Nếu các bước tiếp theo nối qua `DirectChannel`, chúng vẫn chạy trên luồng hiện tại cho đến khi gặp một ranh giới bất đồng bộ.

Vì vậy, một chuỗi transformer, router rồi service activator đồng bộ có thể chiếm cùng luồng scheduler. Chỉ nhìn thời gian thực thi của handler đầu tiên sẽ đánh giá thiếu thời gian chiếm luồng của toàn bộ chuỗi.

### 3.2. Poller có taskExecutor

Khi poller được cấu hình `taskExecutor`, scheduler giao polling task cho executor. Tác vụ này bao gồm việc nhận và xử lý thông điệp theo cấu hình poller, không chỉ riêng một câu lệnh gọi handler.

~~~mermaid
sequenceDiagram
    participant S as Scheduler thread
    participant E as Poll executor
    participant Q as QueueChannel
    participant H as Handler
    S->>E: submit polling task
    Note over S: Có thể phục vụ lịch khác
    E->>Q: receive(timeout)
    Q-->>E: Message
    E->>H: handleMessage(message)
    H-->>E: Hoàn tất
~~~

Một executor riêng giúp cách ly công việc chậm, nhưng tạo thêm khả năng tồn đọng tác vụ và thực thi đồng thời. Bạn phải thiết kế cả kích thước pool, hàng đợi executor và cách xử lý khi executor đầy.

Lưu ý một trường hợp đặc biệt: nếu dùng `CallerRunsPolicy`, luồng gửi tác vụ có thể phải tự chạy tác vụ khi executor bão hòa. Trong tình huống này, công việc có thể quay lại chiếm luồng scheduler.

Hành vi thực thi trên luồng scheduler được mô tả trong [ThreadPoolTaskScheduler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html); API [PollerSpec.taskExecutor](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/PollerSpec.html) xác định executor thực hiện polling task.

## 4. Scheduler mặc định và tên bean quan trọng

Spring Integration tìm scheduler trung tâm theo tên bean `taskScheduler`, tương ứng hằng số `IntegrationContextUtils.TASK_SCHEDULER_BEAN_NAME`.

Nếu cung cấp scheduler tùy chỉnh, hãy khai báo tên bean này một cách rõ ràng. Chỉ đặt `@Primary` cho một bean tên khác không thay thế được việc đáp ứng tên hạ tầng mà Spring Integration sử dụng.

Cần phân biệt hai giá trị mặc định:

| Trường hợp | Kích thước pool mặc định |
| --- | --- |
| Tự tạo `new ThreadPoolTaskScheduler()` mà không đặt pool size | 1 luồng |
| Scheduler mặc định do hạ tầng Spring Integration cung cấp, theo cấu hình chuẩn của dòng 6.5 | 10 luồng |

Giá trị thứ hai có thể thay đổi bằng global property `spring.integration.taskScheduler.poolSize`. Property này điều khiển scheduler mặc định của Spring Integration; nó không tự ghi đè `setPoolSize(...)` trên một scheduler bạn tự khai báo. Tham khảo [cấu hình scheduler](https://docs.spring.io/spring-integration/reference/6.5/configuration/namespace-taskscheduler.html) và [Global Properties](https://docs.spring.io/spring-integration/reference/6.5/configuration/global-properties.html).

Trong môi trường có Spring Boot, cũng có cấu hình scheduling riêng của Boot. Khi chẩn đoán, hãy xác định bean thực tế được dùng thay vì giả định mọi property liên quan đến scheduling đều tác động vào cùng một pool.

`@EnableIntegration` bật hạ tầng Spring Integration trong ví dụ Java thuần của bài. `@EnableScheduling` phục vụ cơ chế xử lý các phương thức `@Scheduled`; bạn không cần thêm annotation đó chỉ để một poller của Spring Integration có thể hoạt động.

## 5. Chọn fixed delay, fixed rate hay cron

### 5.1. Fixed delay: khoảng nghỉ sau khi tác vụ hoàn tất

~~~java
Pollers.fixedDelay(Duration.ofMillis(500))
~~~

Với polling đồng bộ, giả sử một lượt mất 300 ms:

~~~text
0 ms       300 ms             800 ms      1100 ms
|--- chạy ---|--- chờ 500 ms ---|--- chạy ---|
~~~

Khoảng cách giữa hai lần bắt đầu xấp xỉ 800 ms. Fixed delay phù hợp khi muốn có khoảng nghỉ giữa các lượt thăm dò và thời gian xử lý không cố định.

### 5.2. Fixed rate: bám mốc bắt đầu theo chu kỳ

~~~java
Pollers.fixedRate(Duration.ofSeconds(1))
~~~

Các mốc mục tiêu là `t0`, `t0 + 1s`, `t0 + 2s`, ... Nếu tác vụ chạy chậm hoặc thiếu luồng, thời gian bắt đầu thực tế có thể trễ hơn những mốc này.

Fixed rate không tạo thêm năng lực xử lý. Nó cũng không mặc nhiên biến một tác vụ đồng bộ thành nhiều bản chạy song song. Với một lịch lặp đồng bộ trên `ThreadPoolTaskScheduler`, tăng pool size không làm cùng tác vụ đó tự chồng lấn.

Fixed delay và fixed rate được phân biệt theo thời điểm hoàn tất hoặc thời điểm bắt đầu dự kiến trong [PeriodicTrigger](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/support/PeriodicTrigger.html).

### 5.3. Khi có executor, thời điểm hoàn tất cần được hiểu lại

Nếu runnable mà scheduler thực thi chỉ giao polling task cho executor rồi trả về, scheduler có thể coi lần kích hoạt đó đã hoàn tất trước khi handler hoàn tất nghiệp vụ.

Ví dụ:

- Fixed delay là 500 ms.
- Handler cần ba giây.
- Scheduler giao tác vụ cho executor gần như ngay lập tức.
- Các tác vụ polling tiếp theo có thể tiếp tục được giao trong khi tác vụ trước còn chạy hoặc nằm trong hàng đợi executor.

Do đó, không dùng fixed delay làm bằng chứng rằng các lượt xử lý nghiệp vụ chắc chắn không chồng lấn khi đã thêm executor. Nếu bắt buộc chỉ có một tác vụ thực thi tại một thời điểm, cần thiết kế giới hạn thực thi và tồn đọng rõ ràng; nếu chạy nhiều instance, còn cần cơ chế điều phối giữa các instance.

### 5.4. Cron: gắn với lịch trên đồng hồ

~~~java
Pollers.cron(
        "0 */5 * * * *",
        TimeZone.getTimeZone("Asia/Ho_Chi_Minh"))
~~~

Ví dụ này yêu cầu polling ở giây 0, mỗi năm phút, theo múi giờ Việt Nam. Biểu thức cron Spring ở đây có sáu trường, bắt đầu bằng trường giây.

Cron phù hợp cho lịch nghiệp vụ như quét dữ liệu theo phút hoặc chạy trong khung giờ xác định. Nó không đảm bảo thời gian thực, cũng không tự cung cấp lưu trữ lịch bền vững hay khôi phục đầy đủ các lần kích hoạt khi tiến trình ngừng chạy.

Các overload Java DSL cho `Duration`, initial delay và cron kèm `TimeZone` được liệt kê tại [Pollers](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/Pollers.html).

## 6. Ví dụ cấu hình đầy đủ bằng Java DSL

Ví dụ sau có luồng:

~~~text
pendingOrders
    -> polling endpoint với executor riêng
    -> kiểm tra số lượng của đơn hàng
    -> acceptedOrders

Lỗi polling hoặc xử lý
    -> pollingErrors
    -> ghi log
~~~

Các channel hàng đợi đều có giới hạn dung lượng. Endpoint nhận đơn được đặt `autoStartup(false)` để phần minh họa lifecycle có thể chủ động gọi `start()`.

Ứng dụng cần dependency `org.springframework.integration:spring-integration-core` cùng các dependency Spring tương thích. Các import dưới đây dùng API của thư viện đó, không dùng thư viện Java DSL tách rời của các phiên bản cũ.

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.MessagePublishingErrorHandler;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration(proxyBeanMethods = false)
@EnableIntegration
public class OrderPollingConfiguration {

    private static final System.Logger LOG =
            System.getLogger(OrderPollingConfiguration.class.getName());

    public record Order(String id, int quantity) {
    }

    @Bean
    public QueueChannel pendingOrders() {
        return new QueueChannel(100);
    }

    @Bean
    public QueueChannel acceptedOrders() {
        return new QueueChannel(100);
    }

    @Bean
    public PublishSubscribeChannel pollingErrors() {
        PublishSubscribeChannel channel = new PublishSubscribeChannel();
        channel.setRequireSubscribers(true);
        return channel;
    }

    @Bean
    public MessagePublishingErrorHandler pollingErrorHandler(
            @Qualifier("pollingErrors")
            PublishSubscribeChannel errors) {

        MessagePublishingErrorHandler handler =
                new MessagePublishingErrorHandler();
        handler.setDefaultErrorChannel(errors);
        handler.setSendTimeout(1_000);
        return handler;
    }

    @Bean(name = "taskScheduler")
    public ThreadPoolTaskScheduler taskScheduler(
            @Qualifier("pollingErrorHandler")
            MessagePublishingErrorHandler errorHandler) {

        ThreadPoolTaskScheduler scheduler =
                new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("si-scheduler-");
        scheduler.setRemoveOnCancelPolicy(true);
        scheduler.setErrorHandler(errorHandler);
        scheduler.setContinueExistingPeriodicTasksAfterShutdownPolicy(false);
        scheduler.setExecuteExistingDelayedTasksAfterShutdownPolicy(false);
        scheduler.setWaitForTasksToCompleteOnShutdown(true);
        scheduler.setAwaitTerminationSeconds(10);
        return scheduler;
    }

    @Bean
    public ThreadPoolTaskExecutor orderPollExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("order-poll-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }

    @Bean
    public IntegrationFlow orderPollingFlow(
            @Qualifier("pendingOrders") QueueChannel pending,
            @Qualifier("acceptedOrders") QueueChannel accepted,
            @Qualifier("orderPollExecutor")
            ThreadPoolTaskExecutor executor,
            @Qualifier("pollingErrorHandler")
            MessagePublishingErrorHandler errorHandler) {

        return IntegrationFlow.from(pending)
                .handle(Order.class, (order, headers) -> {
                    if (order.quantity() <= 0) {
                        throw new IllegalArgumentException(
                                "Số lượng phải lớn hơn 0: " + order.id());
                    }

                    LOG.log(System.Logger.Level.INFO,
                            "Xử lý " + order.id() + " trên "
                                    + Thread.currentThread().getName());
                    return "ACCEPTED:" + order.id();
                }, endpoint -> endpoint
                        .id("orderPollingEndpoint")
                        .autoStartup(false)
                        .poller(Pollers
                                .fixedDelay(Duration.ofMillis(500))
                                .maxMessagesPerPoll(5)
                                .receiveTimeout(0)
                                .taskExecutor(executor)
                                .errorHandler(errorHandler)))
                .channel(accepted)
                .get();
    }

    @Bean
    public IntegrationFlow pollingErrorFlow(
            @Qualifier("pollingErrors")
            PublishSubscribeChannel errors) {

        return IntegrationFlow.from(errors)
                .handle(message -> {
                    Throwable failure =
                            (Throwable) message.getPayload();
                    LOG.log(System.Logger.Level.ERROR,
                            "Polling hoặc xử lý đơn hàng thất bại",
                            failure);
                })
                .get();
    }
}
~~~

### 6.1. Vì sao cấu hình như vậy?

- `taskScheduler` có tên đúng với scheduler trung tâm của Spring Integration.
- Pool scheduler có hai luồng; các tác vụ polling của luồng đơn hàng được giao cho `orderPollExecutor`.
- `receiveTimeout(0)` giúp tác vụ trả về ngay nếu channel đang rỗng.
- `maxMessagesPerPoll(5)` giới hạn số thông điệp được xử lý trong một polling task.
- Executor có hàng đợi hữu hạn, giúp bộc lộ tình trạng quá tải thay vì tăng tồn đọng không giới hạn.
- Error handler được nối ở cả scheduler và poller để minh họa rõ hai vị trí có thể phát sinh lỗi.
- Scheduler và executor được Spring quản lý dưới dạng bean; không cần tự gọi `initialize()` trong phương thức `@Bean`.

Các giá trị 2, 4, 20, 100 và 500 ms là số minh họa. Hãy điều chỉnh dựa trên thời gian xử lý, lượng đơn hàng và giới hạn downstream.

`acceptedOrders` cũng có thể đầy nếu không có consumer nhận kết quả. Khi đó việc gửi đầu ra có thể làm polling task chờ hoặc thất bại theo timeout gửi. Trong ứng dụng thực tế, cần nối consumer đầu ra và đặt timeout thích hợp.

### 6.2. Giới hạn của ví dụ

`QueueChannel` mặc định trong bộ nhớ không cung cấp khả năng khôi phục thông điệp sau khi tiến trình bị dừng. Việc dùng scheduler hoặc executor không tự bổ sung độ bền dữ liệu.

Error flow hiện chỉ ghi log. Nếu đơn hàng không được phép mất sau khi xử lý lỗi, ứng dụng cần thiết kế việc lưu lỗi, retry hoặc chuyển thông điệp đến nơi có thể xử lý lại. Không coi việc đã có log là đã có cơ chế phục hồi.

## 7. Khởi động và dừng đúng endpoint

Lớp dưới đây chạy trực tiếp với cấu hình ở trên. Không cần Spring Boot để quan sát hành vi.

~~~java
import org.springframework.context.Lifecycle;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class OrderPollingDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                        OrderPollingConfiguration.class)) {

            QueueChannel pending =
                    context.getBean("pendingOrders", QueueChannel.class);
            QueueChannel accepted =
                    context.getBean("acceptedOrders", QueueChannel.class);
            Lifecycle endpoint =
                    context.getBean("orderPollingEndpoint", Lifecycle.class);

            Message<?> request = MessageBuilder.withPayload(
                    new OrderPollingConfiguration.Order("ORD-101", 2))
                    .build();

            if (!pending.send(request, 1_000)) {
                throw new IllegalStateException("Hàng đợi đầu vào đã đầy");
            }

            // Endpoint đang autoStartup(false), chưa nhận đơn.
            if (accepted.receive(0) != null) {
                throw new IllegalStateException("Có kết quả ngoài dự kiến");
            }

            endpoint.start();
            try {
                Message<?> reply = accepted.receive(3_000);

                if (reply == null
                        || !"ACCEPTED:ORD-101".equals(reply.getPayload())) {
                    throw new IllegalStateException("Không nhận đúng kết quả");
                }

                System.out.println(reply.getPayload());
            }
            finally {
                endpoint.stop();
            }
        }
    }
}
~~~

Bạn có thể quan sát ba điểm:

1. Thông điệp vẫn nằm chờ khi endpoint chưa chạy.
2. Sau `start()`, log xử lý hiển thị tiền tố `order-poll-`.
3. `stop()` dừng lịch polling của endpoint; đóng context chịu trách nhiệm dọn các bean hạ tầng.

Không dùng `taskScheduler.stop()` như thao tác thông thường để tạm dừng một luồng. Scheduler dùng chung có thể phục vụ nhiều endpoint hoặc tác vụ thời gian khác. Điều khiển đúng endpoint giúp phạm vi tác động dễ dự đoán hơn.

Dừng endpoint không đồng nghĩa mọi tác vụ đã giao cho executor đều hoàn tất hoặc bị hủy. Khi cần xác nhận công việc đã kết thúc, phải quan sát trạng thái thực thi và kết quả nghiệp vụ, không chỉ kiểm tra `isRunning()` của endpoint.

## 8. Điều chỉnh poller như một hệ thống có giới hạn

### 8.1. receiveTimeout và thời gian chiếm luồng

`receiveTimeout` là thời gian chờ lấy thông điệp từ pollable channel, tính bằng mili giây trong cấu hình `PollerSpec`. Nó không phải timeout của HTTP, JDBC hoặc toàn bộ chuỗi xử lý.

Nếu nhiều poller cùng chờ trên các channel đang rỗng, số lượng luồng bị giữ có thể lớn dù CPU gần như nhàn rỗi. Giảm receive timeout hoặc chuyển polling task sang executor phù hợp giúp giảm ảnh hưởng đến scheduler.

Đặt timeout bằng 0 cùng chu kỳ rất ngắn có thể tạo nhiều lượt kiểm tra rỗng. Hãy cân bằng độ trễ mong muốn với chi phí polling.

### 8.2. maxMessagesPerPoll không phải mức song song

Giá trị 5 nghĩa là một polling task có thể xử lý tối đa năm thông điệp, dừng sớm hơn khi không nhận được thông điệp. Nó không tạo ra năm thread và không đảm bảo luôn có năm thông điệp trong lượt đó.

Trong một polling task thông thường, các thông điệp được xử lý tuần tự. Nhiều polling task khác nhau có thể chạy đồng thời khi bạn cấu hình executor.

Nếu mỗi thông điệp tốn 200 ms, một lượt có đủ năm thông điệp có thể giữ luồng khoảng một giây, chưa kể thời gian nhận và gửi. Đặt giới hạn quá lớn có thể khiến một endpoint chiếm tài nguyên lâu hơn mong muốn.

### 8.3. Có hai hàng đợi khác nhau

~~~text
QueueChannel:
    chứa Message chưa được polling task nhận.

Hàng đợi của executor:
    chứa Runnable polling task đã được scheduler giao,
    nhưng chưa có luồng executor thực hiện.
~~~

Một hàng đợi executor dài có thể chứa nhiều lượt polling chưa bắt đầu, ngay cả khi channel nguồn đã hết thông điệp. Khi các lượt đó chạy, chúng có thể chỉ kiểm tra channel rỗng rồi kết thúc.

Ngược lại, một hàng đợi executor ngắn không chứng minh lượng thông điệp tồn đọng thấp. Thông điệp vẫn có thể nằm nhiều trong `QueueChannel`.

Vì vậy, cần đo riêng độ sâu channel và số tác vụ đang chờ trong executor.

### 8.4. Thứ tự thông điệp và transaction

Khi có nhiều polling task chạy đồng thời, thứ tự hoàn tất không nhất thiết giống thứ tự lấy thông điệp ra khỏi hàng đợi. Đơn B có thể xử lý xong trước đơn A nếu A gọi downstream chậm hơn.

Nếu nghiệp vụ cần thứ tự theo khách hàng hoặc tài khoản, hãy thiết kế partition, một consumer cho mỗi nhóm hoặc cơ chế tuần tự hóa tương ứng.

Transaction gắn với thread cũng cần được xem xét khi thêm ranh giới bất đồng bộ. Một transaction ở producer không tự đi theo thông điệp sang thread executor. Nếu cần transaction ở polling endpoint, hãy cấu hình transaction tại đúng nơi và kiểm tra khả năng tham gia transaction của nguồn dữ liệu hoặc message store.

## 9. Xử lý lỗi: thông điệp lỗi và lỗi lập lịch

Có thể phân biệt ba nhóm để chẩn đoán:

| Vị trí xảy ra lỗi | Ví dụ | Việc cần kiểm tra |
| --- | --- | --- |
| Nhận hoặc xử lý thông điệp | Nguồn dữ liệu lỗi, handler ném exception | Error handler của poller và error flow |
| Giao tác vụ | Executor đầy hoặc đã shutdown | Rejection policy, error handler và log hạ tầng |
| Gửi thông điệp lỗi | Error channel không có subscriber hoặc consumer lỗi | Khả năng tiếp nhận và độ tin cậy của error flow |

Trong xử lý bất đồng bộ, producer có thể đã gửi thông điệp thành công và tiếp tục công việc trước khi handler thất bại. Producer không thể bắt lỗi đó bằng một khối `try/catch` quanh lệnh gửi ban đầu như với chuỗi gọi đồng bộ.

`MessagePublishingErrorHandler` chuyển lỗi thành `ErrorMessage`. Khi lỗi có ngữ cảnh thông điệp phù hợp, header `errorChannel` của thông điệp có thể được ưu tiên; nếu không có, error handler sử dụng kênh mặc định được cấu hình. Trong ví dụ, kênh mặc định là `pollingErrors`, thay cho kênh toàn cục `errorChannel`.

Bạn có thể thử một đơn `new Order("ORD-BAD", 0)`: sẽ có log lỗi và không có kết quả `ACCEPTED:ORD-BAD`. Đây không phải hành vi tự gửi lại đơn vào `pendingOrders`.

Một số lỗi hạ tầng xảy ra trước khi nhận được thông điệp, vì vậy không phải mọi `ErrorMessage` đều có một đơn hàng gốc để retry. Code xử lý lỗi phải kiểm tra ngữ cảnh thay vì ép rằng lúc nào cũng có `failedMessage`.

Cơ chế định tuyến lỗi được mô tả tại [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html); các phương thức cấu hình kênh mặc định nằm tại [MessagePublishingErrorHandler](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/MessagePublishingErrorHandler.html).

Với `PublishSubscribeChannel` không có executor như ví dụ, error handler đầu cuối chạy đồng bộ trên luồng phát lỗi. Đừng để nó thực hiện một cuộc gọi mạng không có timeout; nếu error flow bị treo, chính luồng đang xử lý lỗi cũng bị giữ lại.

## 10. Lifecycle và shutdown có kiểm soát

### 10.1. Phân biệt các cấp điều khiển

| Thao tác | Phạm vi |
| --- | --- |
| `endpoint.start()` hoặc `endpoint.stop()` | Một endpoint cụ thể |
| Điều khiển scheduler dùng chung | Các tác vụ phụ thuộc scheduler đó |
| Shutdown executor | Khả năng tiếp nhận và thực thi tác vụ của executor |
| Đóng `ApplicationContext` | Lifecycle và hủy các bean do context quản lý |

Với `SmartLifecycle`, phase nhỏ hơn thường được khởi động trước; khi dừng, thứ tự phase đi theo chiều ngược lại. Quan hệ phụ thuộc bean và hành vi shutdown của executor cũng ảnh hưởng đến quá trình thực tế. Đặt phase chỉ là một phần của thiết kế dừng ứng dụng.

### 10.2. Ý nghĩa các tùy chọn trong ví dụ

- `setRemoveOnCancelPolicy(true)`: giúp loại bỏ tác vụ đã hủy khỏi hàng đợi scheduler, hữu ích khi nhiều lịch được tạo rồi hủy.
- `setContinueExistingPeriodicTasksAfterShutdownPolicy(false)`: không tiếp tục lịch lặp sau khi scheduler shutdown.
- `setExecuteExistingDelayedTasksAfterShutdownPolicy(false)`: không tiếp tục thực thi tác vụ trì hoãn chưa chạy sau khi shutdown.
- `setWaitForTasksToCompleteOnShutdown(true)`: yêu cầu cách shutdown cho phép công việc đang có được hoàn tất theo chính sách tương ứng.
- `setAwaitTerminationSeconds(10)`: giới hạn thời gian chặn chờ executor kết thúc tại bước shutdown liên quan.

Giá trị chờ mười giây không phải timeout cưỡng bức cho từng handler. Hết khoảng chờ đó cũng không có nghĩa Java đã chắc chắn dừng được một thao tác I/O bị treo. Các client HTTP, JDBC và kết nối ngoài vẫn cần timeout riêng.

Các tùy chọn chờ còn ảnh hưởng đến cách executor tham gia giai đoạn đóng context; hãy đối chiếu đúng phiên bản tại [ExecutorConfigurationSupport](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/concurrent/ExecutorConfigurationSupport.html).

### 10.3. Trình tự nghiệp vụ nên đạt được

Với một hệ thống có yêu cầu hoàn tất công việc trước khi tắt, hãy thiết kế để:

1. Ngừng tiếp nhận hoặc phát sinh công việc mới.
2. Ngừng tạo thêm lượt polling tại thời điểm phù hợp với chiến lược xử lý tồn đọng.
3. Cho phép các tác vụ đã nhận hoàn tất trong giới hạn thời gian.
4. Giữ tài nguyên downstream cần thiết cho tới khi các tác vụ đó kết thúc.
5. Lưu hoặc bàn giao phần việc còn lại theo cơ chế phục hồi đã chọn.

Chỉ gọi `stop()` cho endpoint không tự rút hết thông điệp trong channel. Nếu mục tiêu là xử lý hết hàng đợi trước khi tắt, cần một quy trình drain riêng trước khi ngừng consumer, đồng thời có giới hạn thời gian và cách xử lý phần còn lại.

## 11. Chọn kích thước pool dựa trên tải

Một cách ước lượng ban đầu cho số luồng thực thi công việc blocking là:

~~~text
Số tác vụ đồng thời trung bình ≈
    tốc độ tác vụ đến mỗi giây × thời gian mỗi tác vụ tính bằng giây
~~~

Đây là ước lượng tải trung bình khi hệ thống ở trạng thái ổn định, không phải công thức tự động cho pool size.

Ví dụ, 40 thông điệp/giây với thời gian xử lý trung bình 0,2 giây cần khoảng tám lượt xử lý đồng thời chỉ để theo kịp tải trung bình. Tuy nhiên, một poller đồng bộ chỉ chạy một lượt mỗi lần sẽ không có tám thông điệp xử lý đồng thời chỉ vì scheduler có tám luồng.

Cần phân biệt mức song song thực sự của luồng với số luồng có sẵn. Trong thiết kế dùng executor cho polling, nhịp giao tác vụ, số thông điệp mỗi lượt và thời gian mỗi lượt cùng quyết định mức đồng thời.

Ngoài giá trị trung bình, cần xem:

- Thời gian xử lý ở p95/p99 và các đợt tăng tải.
- Giới hạn connection pool của database hoặc HTTP client.
- Số kết nối và mức song song mà downstream cho phép.
- Nhu cầu giữ thứ tự hoặc giới hạn theo một khóa nghiệp vụ.
- Dung lượng hàng đợi và độ trễ tối đa chấp nhận được.

Tăng pool từ 4 lên 40 có thể làm downstream bị quá tải nếu chỉ có tám kết nối khả dụng. Khi đó số lượng thread tăng nhưng throughput không tăng tương ứng.

## 12. Quan sát và chẩn đoán sự cố

Đặt tiền tố tên thread riêng cho scheduler và executor giúp đọc log hoặc thread dump dễ hơn. Với ví dụ, công việc chậm xuất hiện trên `order-poll-` thay vì thường xuyên giữ `si-scheduler-`.

| Dấu hiệu | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Nhiều poller cùng trễ, CPU thấp | Scheduler thread chờ I/O hoặc chờ nhận thông điệp | Xem thread dump, timeout và executor riêng |
| QueueChannel tăng đều | Tốc độ xử lý nhỏ hơn tốc độ đến | Đo thời gian xử lý, mức đồng thời và downstream |
| Hàng đợi executor tăng, channel ít dữ liệu | Giao lượt polling nhanh hơn khả năng thực hiện | Giảm nhịp, giới hạn tồn đọng, xem receive timeout |
| Xuất hiện `TaskRejectedException` | Executor đầy hoặc đang đóng | Xem pool, queue, chính sách rejection và lifecycle |
| Handler vẫn chạy sau khi endpoint stop | Tác vụ đã được giao trước đó chưa kết thúc | Theo dõi in-flight và thiết kế drain |
| Lịch cron chạy khác giờ nghiệp vụ | Múi giờ cấu hình không đúng | Chỉ định timezone và kiểm tra giờ hệ thống |
| Kết quả hoàn tất đảo thứ tự | Nhiều tác vụ xử lý đồng thời | Thiết kế tuần tự hóa theo yêu cầu nghiệp vụ |

Các số liệu hữu ích gồm thời gian từ mốc dự kiến đến lúc tác vụ bắt đầu, thời gian mỗi polling task, lượng thông điệp mỗi lượt, active count, queue depth và số lỗi hoặc rejection.

Không mặc định mọi số liệu này đều được tự động xuất thành metric. Một số cần instrument thêm tại endpoint, executor hoặc lớp giám sát phù hợp.

## 13. Kiểm chứng hành vi trong bài thực hành

Để kiểm chứng ví dụ mà không phụ thuộc vào một khoảng `Thread.sleep` tùy ý, có thể viết test JUnit 5 sử dụng timeout nhận thông điệp. Test dưới đây kiểm tra việc chủ động khởi động endpoint và quan sát kết quả.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.context.Lifecycle;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class OrderPollingConfigurationTest {

    @Test
    void processesOrderAfterEndpointStarts() {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                        OrderPollingConfiguration.class)) {

            QueueChannel pending =
                    context.getBean("pendingOrders", QueueChannel.class);
            QueueChannel accepted =
                    context.getBean("acceptedOrders", QueueChannel.class);
            Lifecycle endpoint =
                    context.getBean("orderPollingEndpoint", Lifecycle.class);

            assertFalse(endpoint.isRunning());
            assertTrue(pending.send(MessageBuilder.withPayload(
                    new OrderPollingConfiguration.Order("ORD-TEST", 3))
                    .build(), 1_000));
            assertNull(accepted.receive(0));

            endpoint.start();
            try {
                Message<?> result = accepted.receive(3_000);

                assertNotNull(result);
                assertEquals("ACCEPTED:ORD-TEST", result.getPayload());
            }
            finally {
                endpoint.stop();
            }
        }
    }
}
~~~

Timeout ba giây là giới hạn chờ để test không treo vô hạn, không phải yêu cầu scheduler phải chính xác tới mili giây. Nếu môi trường CI có tải cao, cần đặt giới hạn theo ngân sách chạy test phù hợp.

Khi mở rộng kiểm chứng, hãy dùng latch, một kênh kết quả hoặc công cụ chờ có timeout để quan sát lỗi và tác vụ đang chạy. Muốn kiểm tra việc stop ngăn nhận thêm đơn, phải kiểm soát cả tác vụ đã được giao cho executor; không suy luận từ một lần nhận rỗng tức thời.

Nếu cần kiểm tra riêng transformer hoặc quy tắc nghiệp vụ, hãy gọi và kiểm tra phần đó trực tiếp. Test lịch chỉ nên chịu trách nhiệm cho hành vi phụ thuộc scheduling, để lỗi thời gian không làm nhiễu các kiểm tra nghiệp vụ đơn giản.

## 14. Những nguyên tắc cần giữ khi thiết kế

Một luồng sử dụng `TaskScheduler` dễ vận hành khi bạn trả lời rõ được bốn câu hỏi: ai xác định thời điểm chạy, luồng nào nhận thông điệp, luồng nào thực hiện nghiệp vụ và lỗi được chuyển đi đâu.

Từ đó, hãy chọn nhịp polling theo độ trễ cần đạt; dùng executor có giới hạn nếu công việc cần cách ly; đo riêng tồn đọng thông điệp và tồn đọng tác vụ; điều khiển lifecycle ở đúng endpoint. Khi thêm transformer, filter, router hoặc aggregator phía sau, tiếp tục kiểm tra ranh giới luồng và thời gian chiếm tài nguyên của cả chuỗi.

Scheduler cung cấp cơ chế điều phối theo thời gian. Độ bền thông điệp, phục hồi lỗi, thứ tự xử lý và điều phối giữa nhiều instance phải được thiết kế cùng channel, endpoint và hạ tầng tích hợp tương ứng.

