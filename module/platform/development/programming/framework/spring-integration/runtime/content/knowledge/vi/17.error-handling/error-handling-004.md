# MessagePublishingErrorHandler trong Spring Integration

Một integration flow thường hoạt động qua nhiều ranh giới thực thi: sender đẩy message vào channel, endpoint nhận message, handler gọi nghiệp vụ, poller lấy message từ queue, còn executor chuyển công việc sang thread khác. Khi handler chạy **khác thread với sender**, exception không thể tự động quay về lời gọi gửi ban đầu theo cách ném exception thông thường. Spring Integration giải quyết một phần bài toán này bằng cách phát lỗi dưới dạng message.

**<code>MessagePublishingErrorHandler</code>** là thành phần trung tâm của cơ chế đó: nó nhận một <code>Throwable</code> từ hạ tầng xử lý task và phát một <code>ErrorMessage</code> tới error channel phù hợp. Bài học thuộc chương **Error runtime** của **SPRING_INTEGRATION_RUNTIME**, tập trung vào cách thành phần này phối hợp với channel, consumer, poller, executor, transaction, retry, message store, correlation và việc quan sát trạng thái runtime.

> <code>MessagePublishingErrorHandler</code> **không phải** một bộ retry, không tự đưa message vào dead-letter queue và không bảo đảm mọi exception trong ứng dụng đều biến thành <code>ErrorMessage</code>. Phải có thành phần runtime thực sự gọi nó hoặc sử dụng nó làm <code>ErrorHandler</code>.

## 1. Chức năng và vị trí trong runtime

Lớp <code>org.springframework.integration.channel.MessagePublishingErrorHandler</code> kế thừa <code>org.springframework.integration.core.ErrorMessagePublisher</code> và triển khai <code>org.springframework.util.ErrorHandler</code>. API quan trọng của nó bao gồm:

| Thành phần API | Vai trò |
|---|---|
| <code>handleError(Throwable ex)</code> | Điểm nhận exception từ task/poller/channel, sau đó phát <code>ErrorMessage</code> |
| <code>setDefaultErrorChannel(MessageChannel)</code> | Chỉ định channel dự phòng dưới dạng đối tượng |
| <code>setDefaultErrorChannelName(String)</code> | Chỉ định channel dự phòng bằng tên bean |
| <code>getDefaultErrorChannel()</code> | Đọc channel mặc định đã cấu hình |
| <code>setErrorMessageStrategy(...)</code> | Tùy biến cách tạo <code>ErrorMessage</code> qua API kế thừa |
| <code>setSendTimeout(...)</code> | Giới hạn thời gian gửi lỗi khi channel đích có thể block, qua API kế thừa |

Vai trò của các thành phần nên được phân biệt:

- **Handler nghiệp vụ** xử lý payload và có thể ném exception.
- **Consumer endpoint** gọi handler trên thread hiện hành hoặc thread mà runtime đã chọn.
- **<code>ErrorHandler</code>** nhận exception ở ranh giới có cơ chế bắt lỗi.
- **<code>MessagePublishingErrorHandler</code>** tạo và phát <code>ErrorMessage</code>.
- **Error channel** đưa lỗi đến một hoặc nhiều consumer để log, cảnh báo, quyết định recovery hay lưu bản tin lỗi.

~~~mermaid
flowchart LR
    A["Sender"] --> B["Channel / Queue"]
    B --> C["Worker / Poller"]
    C --> D["Consumer endpoint"]
    D --> E["Business handler"]
    E -. "Throwable" .-> F["MessagePublishingErrorHandler"]
    F --> G{"errorChannel header<br/>hợp lệ?"}
    G -->|"Có"| H["Per-message error channel"]
    G -->|"Không"| I["Default / global errorChannel"]
    H --> J["Error consumer"]
    I --> J
    J --> K["Log / alert / quarantine / recovery"]
~~~

Sơ đồ mô tả đường đi khi **task executor hoặc poller có cơ chế bắt lỗi và dùng <code>MessagePublishingErrorHandler</code>**. Một lời gọi đồng bộ qua <code>DirectChannel</code> thường ném exception trở lại sender mà không đi theo đường này.

## 2. Từ exception đến ErrorMessage

Đường xử lý có thể được nhìn theo các bước:

1. Message được giao cho một tác vụ bất đồng bộ hoặc polling consumer.
2. Trong quá trình xử lý, endpoint, transformer hoặc handler ném exception.
3. Hạ tầng phụ trách task bắt exception và gọi <code>handleError(Throwable)</code>.
4. <code>MessagePublishingErrorHandler</code> tạo <code>ErrorMessage</code> với payload là <code>Throwable</code> hoặc exception đã được hạ tầng bao gói.
5. Error message được gửi đến error channel của message lỗi, nếu lấy được header hợp lệ; nếu không, sử dụng channel dự phòng/toàn cục theo cấu hình.
6. Consumer trên error channel xử lý lỗi theo chính sách của ứng dụng.

### Cấu trúc dữ liệu quan trọng

<code>ErrorMessage</code> là một <code>Message&lt;Throwable&gt;</code>, không phải một <code>Message&lt;String&gt;</code> ghi nội dung lỗi. Nó có thể chứa:

- <code>error.getPayload()</code>: exception dùng để điều tra hoặc phân loại.
- <code>error.getOriginalMessage()</code>: message ban đầu, **có thể null** nếu không có ngữ cảnh tương ứng.
- <code>((MessagingException) cause).getFailedMessage()</code>: message tại điểm thất bại, nếu payload là <code>MessagingException</code> và thông tin này được đính kèm.
- Headers riêng của <code>ErrorMessage</code>: không nên mặc định chúng giống hệt headers của message đầu vào.

<code>originalMessage</code> và <code>failedMessage</code> có mục đích khác nhau. Sau một transformer, message thất bại có thể là payload đã biến đổi, trong khi message gốc là dữ liệu được đưa vào flow trước đó. Không phải exception nào cũng chứa cả hai. Nếu lỗi xuất hiện trước khi inbound adapter tạo được Spring <code>Message</code>, framework có thể chỉ còn exception hoặc metadata từ adapter.

~~~java
@ServiceActivator(inputChannel = "orders.errors")
public void observe(ErrorMessage error) {
    Throwable failure = error.getPayload();

    Message<?> failed = failure instanceof MessagingException messagingEx
        ? messagingEx.getFailedMessage()
        : null;

    Message<?> original = error.getOriginalMessage();
    Message<?> context = original != null ? original : failed;

    String correlationId = context != null
        ? (String) context.getHeaders().get("correlationId")
        : null;

    log.error("Order flow failed; correlationId={}", correlationId, failure);
    // Phân loại lỗi, ghi metric hoặc chuyển bản tin cần điều tra sang kho phù hợp.
}
~~~

Đoạn code minh họa dùng <code>org.springframework.messaging.support.ErrorMessage</code>, <code>org.springframework.messaging.MessagingException</code> và <code>org.springframework.messaging.Message</code>. Khi đọc correlation ID thực tế, cần thống nhất kiểu dữ liệu header trong hợp đồng: ví dụ trên giả định header là <code>String</code>.

## 3. Quy tắc chọn error channel

Thứ tự định tuyến lỗi quan trọng hơn tên class:

| Điều kiện | Nơi nhận <code>ErrorMessage</code> |
|---|---|
| Message thất bại có <code>MessageHeaders.ERROR_CHANNEL</code> trỏ tới channel hợp lệ và handler có ngữ cảnh message | Channel được chỉ định trong header |
| Không có header phù hợp và <code>MessagePublishingErrorHandler</code> đã được cấu hình default channel | Channel mặc định đã cấu hình |
| Không có định tuyến riêng và ứng dụng dùng hạ tầng error mặc định của Spring Integration | Global bean tên <code>errorChannel</code> |
| Channel đích không tồn tại, bị chặn hoặc không nhận message | Quá trình **phát lỗi cũng có thể thất bại**; phải xem log/cấu hình của error publisher và caller |

Header chuẩn là <code>MessageHeaders.ERROR_CHANNEL</code>; giá trị thường là một <code>MessageChannel</code> hoặc tên channel có thể được resolver tìm thấy. Header có mức ưu tiên cao hơn channel dự phòng, nên thay đổi default channel không có tác dụng với một message đã mang header <code>errorChannel</code> trỏ sang nơi khác.

Global <code>errorChannel</code> mặc định là <code>PublishSubscribeChannel</code>. Spring Integration cung cấp subscriber ghi log ở mức ERROR; từ phiên bản 5.4.3, kênh mặc định yêu cầu có subscriber để tránh âm thầm bỏ qua lỗi khi không có người nhận. Nếu ứng dụng định nghĩa bean <code>errorChannel</code> riêng, chính ứng dụng phải thiết kế subscriber, capacity và hành vi lỗi phù hợp.

**Chú ý:** Gửi thành công vào error channel chỉ chứng minh *lỗi đã được công bố*. Điều đó chưa chứng minh message nghiệp vụ đã được retry, được rollback hoặc đã được lưu bền vững.

## 4. Khi nào MessagePublishingErrorHandler được dùng?

### 4.1. Poller và task scheduler

Polling consumer lấy message từ <code>PollableChannel</code> hoặc nguồn có cơ chế polling. Lời gọi xử lý chạy trong task do scheduler kích hoạt. Spring Integration tích hợp <code>MessagePublishingErrorHandler</code> với <code>taskScheduler</code> mặc định để phát lỗi từ các poller task lên error channel.

Nếu ứng dụng thay scheduler bằng một bean <code>taskScheduler</code> tùy chỉnh, cần bảo đảm cơ chế xử lý lỗi tương ứng vẫn được gắn vào scheduler nếu muốn giữ cách báo lỗi này. Framework cung cấp bean <code>integrationMessagePublishingErrorHandler</code> để tái sử dụng trong trường hợp đó.

### 4.2. PublishSubscribeChannel có executor

Khi <code>PublishSubscribeChannel</code> dùng một executor, các subscriber có thể chạy trên thread khác; channel hỗ trợ <code>ErrorHandler</code> và mặc định dùng <code>MessagePublishingErrorHandler</code>. Nếu channel **không có executor**, exception ở subscriber được ném theo lời gọi gửi đồng bộ, còn error handler cấu hình cho kênh này không được áp dụng.

### 4.3. ExecutorChannel và các ranh giới bất đồng bộ khác

<code>ExecutorChannel</code> cũng chuyển việc xử lý qua executor, vì vậy exception ở consumer thường không thể tự ném trở lại thread của sender. Tuy nhiên, **không nên suy diễn rằng mọi <code>ExecutorChannel</code>, mọi adapter hoặc mọi <code>TaskExecutor</code> độc lập đều gọi cùng một instance <code>MessagePublishingErrorHandler</code>**. Cần kiểm tra bộ dispatcher/error handling thực tế của thành phần đang dùng.

Một số adapter (HTTP, AMQP, Kafka, JMS...) có error handler, retry, acknowledgement và dead-letter policy riêng. Lỗi deserialize xảy ra *trước khi tạo Spring Message* có thể nằm hoàn toàn ở listener/container, không đi vào integration error channel nếu adapter không nối cơ chế đó.

| Bối cảnh | Sender thường thấy gì? | Điều cần kiểm tra |
|---|---|---|
| <code>DirectChannel</code> đồng bộ | Exception phát sinh cùng call stack | Xử lý ở caller/gateway hoặc endpoint advice thích hợp |
| <code>PublishSubscribeChannel</code> có executor | <code>send()</code> có thể hoàn tất trước khi subscriber lỗi | Error handler của channel và header <code>errorChannel</code> |
| Poller nhận từ <code>QueueChannel</code> | Sender không trực tiếp thấy lỗi xử lý sau này | Scheduler error handler, poller transaction và recovery |
| <code>ExecutorChannel</code> | Giao việc và xử lý có thể khác thread | Dispatcher, error path, rejected task và timeout |
| Inbound listener của broker | Phụ thuộc vào adapter và ACK mode | Listener error handler, retry/backoff, requeue/DLQ |

Ngay cả với executor, không được giả định <code>send()</code> **luôn** trả về ngay: task rejection, giới hạn queue hoặc chính sách chạy trên caller thread có thể thay đổi hành vi thực tế.

## 5. Ví dụ Java: bắt lỗi từ PublishSubscribeChannel bất đồng bộ

Ví dụ này dùng Spring Integration Java/annotation configuration, Java 17+ và một service activator luôn ném exception khi đơn hàng có số lượng không hợp lệ. Tất cả bean/method dưới đây đặt trong ứng dụng Spring đã có Spring Integration dependency.

**Bước 1 — khai báo channel, executor và chính MessagePublishingErrorHandler:**

~~~java
@Configuration
@EnableIntegration
public class OrderErrorConfig {

    @Bean
    public ThreadPoolTaskExecutor orderExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("orders-worker-");
        return executor;
    }

    @Bean(name = "orders.errors")
    public MessageChannel ordersErrors() {
        return new DirectChannel();
    }

    @Bean
    public MessagePublishingErrorHandler ordersPublishingErrorHandler(
            @Qualifier("orders.errors") MessageChannel fallbackErrors) {
        MessagePublishingErrorHandler handler = new MessagePublishingErrorHandler();
        handler.setDefaultErrorChannel(fallbackErrors);
        return handler;
    }

    @Bean(name = "orders.input")
    public MessageChannel ordersInput(
            ThreadPoolTaskExecutor orderExecutor,
            @Qualifier("ordersPublishingErrorHandler")
            MessagePublishingErrorHandler errorHandler) {
        PublishSubscribeChannel channel = new PublishSubscribeChannel(orderExecutor);
        channel.setErrorHandler(errorHandler);
        return channel;
    }
}
~~~

Các import chính: <code>org.springframework.integration.channel.MessagePublishingErrorHandler</code>, <code>PublishSubscribeChannel</code>, <code>DirectChannel</code>; <code>org.springframework.integration.config.EnableIntegration</code>; <code>org.springframework.messaging.MessageChannel</code>; <code>org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor</code>; <code>org.springframework.beans.factory.annotation.Qualifier</code>.

Trong ví dụ này, <code>orders.errors</code> là error channel mặc định cho publisher đã cấu hình. Ứng dụng có thể chọn dùng trực tiếp cơ chế <code>MessagePublishingErrorHandler</code> mặc định của <code>PublishSubscribeChannel</code> nếu không có nhu cầu đặt default riêng.

**Bước 2 — consumer nghiệp vụ và consumer lỗi:**

~~~java
public record OrderCommand(String orderId, int quantity) {}

@Component
public class OrderConsumers {

    @ServiceActivator(inputChannel = "orders.input")
    public void process(OrderCommand order) {
        if (order.quantity() <= 0) {
            throw new IllegalArgumentException(
                "quantity phải lớn hơn 0 cho " + order.orderId()
            );
        }
        // Gọi service nghiệp vụ trong trường hợp hợp lệ.
    }

    @ServiceActivator(inputChannel = "orders.errors")
    public void onError(ErrorMessage error) {
        Throwable failure = error.getPayload();
        log.error("orders.errors received", failure);
        // Phân loại lỗi và quyết định cảnh báo, recovery hoặc quarantine.
    }
}
~~~

<code>@ServiceActivator</code> thuộc <code>org.springframework.integration.annotation</code>, <code>@Component</code> thuộc Spring Context. Ví dụ giả định ứng dụng có logger <code>log</code> (như SLF4J) và bật Spring component scanning cho lớp <code>OrderConsumers</code>.

**Bước 3 — gửi một message có error channel riêng:**

~~~java
Message<OrderCommand> request = MessageBuilder
    .withPayload(new OrderCommand("O-42", 0))
    .setHeader(MessageHeaders.ERROR_CHANNEL, ordersErrors)
    .setHeader("correlationId", "req-42")
    .build();

ordersInput.send(request);
~~~

Trong đó <code>ordersInput</code> và <code>ordersErrors</code> lần lượt là các bean <code>orders.input</code> và <code>orders.errors</code>; <code>MessageBuilder</code> thuộc <code>org.springframework.integration.support</code>, còn <code>MessageHeaders</code> thuộc <code>org.springframework.messaging</code>. Ví dụ gắn **đối tượng channel** vào header để tránh phụ thuộc vào việc resolve tên channel bằng chuỗi.

Diễn biến dự kiến:

~~~mermaid
sequenceDiagram
    participant S as Sender
    participant P as PubSubChannel + Executor
    participant H as OrderConsumers.process()
    participant E as MessagePublishingErrorHandler
    participant C as orders.errors
    participant O as OrderConsumers.onError()
    S->>P: send(Message<OrderCommand>)
    P-->>S: gửi/đăng ký task xong
    P->>H: dispatch trên worker thread
    H--xP: IllegalArgumentException
    P->>E: handleError(Throwable)
    E->>C: ErrorMessage
    C->>O: handle(ErrorMessage)
    Note over S,O: Sender không tự nhận exception của consumer qua call stack cũ
~~~

<code>orders.errors</code> dùng <code>DirectChannel</code>, do đó consumer lỗi sẽ được gọi đồng bộ **trong thread đang publish error**. Nếu <code>onError()</code> xử lý nặng, worker nghiệp vụ có thể bị giữ lâu; khi tải cao, nên thiết kế error-processing pipeline có backpressure, durability và giới hạn tài nguyên phù hợp.

### Điều gì thay đổi nếu bỏ executor?

Nếu tạo <code>new PublishSubscribeChannel()</code> không truyền executor, lời gọi <code>process()</code> chạy ngay trên thread gửi. Exception thường lan từ <code>ordersInput.send(request)</code> về caller; cấu hình <code>setErrorHandler(...)</code> trên channel sẽ không biến tình huống này thành xử lý bất đồng bộ.

## 6. Thực hành trực tiếp: header ưu tiên hơn default channel

Có thể kiểm chứng quy tắc định tuyến mà không cần dựng cả application context bằng một ví dụ nhỏ sử dụng hai <code>QueueChannel</code>. Các channel được truyền trực tiếp dưới dạng đối tượng.

~~~java
QueueChannel perMessageErrors = new QueueChannel();
QueueChannel fallbackErrors = new QueueChannel();

MessagePublishingErrorHandler handler = new MessagePublishingErrorHandler();
handler.setDefaultErrorChannel(fallbackErrors);

Message<String> failedRequest = MessageBuilder.withPayload("invalid")
    .setHeader(MessageHeaders.ERROR_CHANNEL, perMessageErrors)
    .build();

handler.handleError(new MessageHandlingException(failedRequest, "bad payload"));

Message<?> published = perMessageErrors.receive(1000);
assertInstanceOf(ErrorMessage.class, published);
assertNull(fallbackErrors.receive(0));
~~~

Lớp <code>QueueChannel</code> thuộc <code>org.springframework.integration.channel</code>; <code>MessageHandlingException</code> thuộc <code>org.springframework.messaging</code>; hai assertion ở cuối thuộc JUnit 5. Một kiểm thử độc lập như vậy minh họa **cơ chế publish**, không thay thế integration test xác nhận runtime có thực sự gọi error handler.

Nếu bỏ <code>ERROR_CHANNEL</code> khỏi <code>failedRequest</code>, error publisher mới sử dụng kênh dự phòng khi không có channel ưu tiên. Trong môi trường có nhiều flow, lỗi phổ biến là message bị gắn header <code>errorChannel</code> bởi gateway hoặc adapter từ trước, khiến handler phát lỗi vào nơi khác với channel mặc định mà người vận hành đang theo dõi.

## 7. TaskScheduler tùy chỉnh và poller

Khi tự khai báo một <code>taskScheduler</code> để kiểm soát số thread hoặc tên thread, cần gắn error handler tương thích. Đây là **cấu hình thay thế** cho scheduler mặc định và phải được cân nhắc trong cấu hình Spring Integration hiện có.

~~~java
@Bean(name = "taskScheduler")
ThreadPoolTaskScheduler integrationTaskScheduler(
        @Qualifier("integrationMessagePublishingErrorHandler")
        ErrorHandler integrationErrors) {

    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(8);
    scheduler.setThreadNamePrefix("integration-poller-");
    scheduler.setErrorHandler(integrationErrors);
    return scheduler;
}
~~~

<code>ThreadPoolTaskScheduler</code> thuộc <code>org.springframework.scheduling.concurrent</code>; <code>ErrorHandler</code> thuộc <code>org.springframework.util</code>. Bean <code>integrationMessagePublishingErrorHandler</code> là error handler mà Spring Integration cung cấp trong cấu hình thông thường. Trước khi thay scheduler, kiểm tra cách ứng dụng khởi tạo và quản lý <code>taskScheduler</code> để tránh cấu hình trùng bean.

Poller có thể được thiết lập bằng annotation:

~~~java
@ServiceActivator(inputChannel = "orders.queue",
                  poller = @Poller(fixedDelay = "1000"))
public void consume(OrderCommand order) {
    orderService.process(order);
}
~~~

Ví dụ giả định <code>orders.queue</code> là một <code>PollableChannel</code> đã khai báo và <code>orderService</code> được inject vào component. <code>@Poller</code> là annotation của Spring Integration. Nếu consumer ném lỗi trong poller task và không có advice phục hồi/nuốt lỗi trước đó, scheduler error handler có thể phát <code>ErrorMessage</code>.

**Ranh giới transaction:** Nếu poller mở transaction cho receive/handle, exception có thể làm transaction rollback trước khi lỗi được báo qua scheduler. Nhưng <code>MessagePublishingErrorHandler</code> tự nó không quyết định rollback, xác nhận message với broker hay gửi lại message sau thất bại. Các hành vi ấy do transaction manager, adapter, message store và chính sách ACK/redelivery quyết định.

## 8. Phân biệt xử lý lỗi, retry và recovery

Ba cơ chế dễ bị gộp nhầm:

| Cơ chế | Làm gì? | Không tự làm gì? |
|---|---|---|
| <code>MessagePublishingErrorHandler</code> | Công bố lỗi dưới dạng <code>ErrorMessage</code> | Không retry handler, không rollback hoặc persist payload |
| <code>RequestHandlerRetryAdvice</code> | Thử lại một handler invocation theo retry policy | Không tự bao phủ lỗi xảy ra trước endpoint đã được advice |
| <code>ErrorMessageSendingRecoverer</code> | Được dùng như recovery callback để publish lỗi sau khi retry thất bại | Không quyết định retry policy hoặc bảo đảm redelivery từ nguồn |

Ví dụ một downstream service lỗi do database tạm thời không truy cập được:

1. Retry advice quanh handler thử lại có giới hạn và backoff.
2. Nếu thành công, flow tiếp tục như bình thường.
3. Nếu hết lượt, một recovery callback có thể publish <code>ErrorMessage</code> hoặc để exception tiếp tục lan tới ranh giới runtime.
4. Nếu exception cuối cùng lan đến một scheduled task có <code>MessagePublishingErrorHandler</code>, scheduler có thể phát thêm error message. **Tránh thiết kế hai đường publish không kiểm soát**, vì có thể phát cảnh báo hoặc lưu quarantine hai lần.

Với lỗi cố định như JSON sai cú pháp hoặc dữ liệu nghiệp vụ không hợp lệ, retry vô hạn chỉ làm đầy queue và tiêu thụ thread. Nên đưa message sang đường kiểm tra/quarantine theo tiêu chí rõ ràng và giữ đủ dữ liệu để khắc phục.

## 9. Điều gì xảy ra nếu phát ErrorMessage cũng thất bại?

Đây là tình huống thực tế cần thiết kế ngay từ đầu, đặc biệt khi error flow cũng có endpoint, executor hoặc message store.

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không thấy consumer lỗi chạy | Message có header <code>errorChannel</code> trỏ nơi khác; không có subscriber; endpoint chưa start | Ghi nhận header khi thất bại và kiểm tra channel subscription/lifecycle |
| Thấy exception trong log nhưng không có <code>ErrorMessage</code> | Luồng đồng bộ; task dùng error handler khác; lỗi xảy ra trước khi có Spring Message | Xác định thread boundary và error handler đang được gắn thực tế |
| Worker xử lý lỗi bị nghẽn | Error consumer xử lý lâu trên <code>DirectChannel</code>, queue đầy hoặc gửi lỗi bị block | Tách luồng xử lý lỗi, giới hạn thời gian và bổ sung backpressure |
| Error flow tiếp tục ném exception | Consumer lỗi phát sinh lỗi thứ cấp | Giảm phụ thuộc của error consumer, có fallback log/alert đáng tin cậy |
| Log lỗi có nhưng message nguồn mất | Message đã ACK/remove, error channel in-memory hoặc hệ thống restart | Thiết kế DLQ/quarantine bền vững và quy tắc ACK rõ ràng |
| Có nhiều thông báo cho một lỗi | Retry recoverer và scheduler đều publish, hoặc nhiều subscriber cùng tạo side effect | Chuẩn hóa điểm sở hữu recovery và idempotency cho error handling |

Một <code>ErrorMessage</code> nằm trong <code>PublishSubscribeChannel</code> mặc định chỉ là message trong bộ nhớ khi được phát và giao cho subscriber; bản thân nó **không phải bản ghi đã được persist**. Nếu cần điều tra và xử lý lại sau restart, hệ thống phải chủ động lưu thông tin phù hợp vào storage, broker DLQ hoặc message store có cơ chế bền vững.

Trong Spring Integration, channel mặc định có thể được cấu hình <code>requireSubscribers</code> để không bỏ qua message khi thiếu subscriber. Đây là một tín hiệu hữu ích nhưng không thay thế quy trình kiểm tra tình trạng error consumer, thống kê lỗi publish và việc lưu bản tin thô.

## 10. Correlation, tracing và quan sát hiệu năng

Khi message đi qua transformer, splitter, aggregator và nhiều executor, cùng một lỗi có thể liên quan tới nhiều message ID. Nên chuẩn hóa thông tin quan sát:

- **Correlation ID nghiệp vụ/flow:** giá trị ổn định được đưa vào header có hợp đồng rõ ràng; dùng để nối sự kiện qua thread.
- **Message ID hiện tại:** nhận diện từng message, không tự tương đương khóa idempotency; có thể thay đổi khi tạo message mới.
- **Failed/original message:** dùng để xác định payload và endpoint nào thực sự lỗi; kiểm tra null và quyền truy cập.
- **Component/endpoint name, thread, timestamp:** hỗ trợ phân biệt poller, executor và subscriber; stack trace trong Spring Messaging có thể chứa thông tin component nguồn.
- **Metric:** số lần lỗi theo exception class/endpoint, error publishing failure, độ sâu queue, active threads, executor rejection, retry count và thời gian xử lý error consumer.

Không log toàn bộ payload nhạy cảm lên error channel hoặc log tập trung. Chỉ ghi định danh cần thiết và một phiên bản đã che dữ liệu; nếu cần lưu payload gốc để replay, quản lý quyền truy cập và thời gian lưu phù hợp.

### Chẩn đoán khi không có ErrorMessage

Thực hiện lần lượt:

1. Xác định message thực sự đã đến endpoint nào bằng log/metric ở adapter và channel.
2. Kiểm tra exception xảy ra **cùng thread với sender** hay trong task của executor/poller.
3. Xác minh task/channel nào sở hữu <code>ErrorHandler</code>; đừng chỉ tìm bean <code>MessagePublishingErrorHandler</code> trong context rồi suy ra nó đã được sử dụng.
4. Nếu đã publish, kiểm tra <code>MessageHeaders.ERROR_CHANNEL</code> trên failed message, bean/channel mặc định, subscriber và trạng thái start/stop của endpoint lỗi.
5. Nếu channel đích có queue hay message store, kiểm tra capacity, khả năng receive, tính bền vững và timeout.
6. Nếu exception đến từ inbound adapter, kiểm tra deserialize, ACK/nack, retry container và DLQ của adapter đó.
7. Nếu có retry/recovery, kiểm tra exception được lan ra hay đã bị advice/handler bắt và coi là xử lý xong.

## 11. Kiểm thử cơ chế này

Tối thiểu nên có các trường hợp sau:

| Kịch bản | Điều cần xác nhận |
|---|---|
| Lỗi trong subscriber trên channel có executor | Có một <code>ErrorMessage</code> được chuyển tới error consumer phù hợp |
| Lỗi trên channel đồng bộ không có executor | Caller nhận exception; không mặc định kỳ vọng error channel nhận lỗi |
| Message có header <code>ERROR_CHANNEL</code> | Header ưu tiên so với default error channel |
| Message không có header | Lỗi được gửi tới fallback/global channel đã cấu hình |
| Error consumer bị stop hoặc channel không có subscriber | Có tín hiệu thất bại hoặc fallback phù hợp; không mất lỗi trong im lặng |
| Poller ném exception | Scheduler error handler và transaction/recovery hoạt động như đã thiết kế |
| Lỗi sau khi hết retry | Không có side effect trùng lặp hoặc nhiều bản ghi quarantine ngoài chủ đích |

Với test bất đồng bộ, nên dùng <code>CountDownLatch</code>, <code>BlockingQueue</code> hoặc công cụ chờ có timeout để đợi consumer lỗi, thay vì gọi <code>send()</code> xong rồi assert ngay. Một test sync chỉ gọi trực tiếp <code>MessagePublishingErrorHandler.handleError(...)</code> chứng minh API publish; nó **không** chứng minh framework đã cấu hình và gọi error handler trên thread worker.

## 12. Checklist trước khi vận hành

- Xác định chính xác thread boundary và nguồn phát lỗi: sender, executor, poller hay adapter.
- Cấu hình error handler tại đúng runtime component; hiểu thứ tự <code>errorChannel</code> header, default channel và global channel.
- Có error consumer thực sự hoạt động; phân biệt báo lỗi với retry, rollback, ACK và redelivery.
- Quy định rõ lỗi transient/permanent, số lần retry, backoff, quarantine và cơ chế xử lý poison message.
- Giữ correlation ID, endpoint name và thông tin failed/original message khi có, đồng thời tránh rò rỉ payload nhạy cảm.
- Kiểm soát thread pool, capacity, timeout và độ tin cậy của chính error flow; có metric/cảnh báo cho lỗi thứ cấp.
- Kiểm thử start/stop endpoint, timeout, broker redelivery và failure trong chính error channel.

**Kết luận:** <code>MessagePublishingErrorHandler</code> là cầu nối giữa **exception trong runtime task** và **error message trong message flow**. Khi hiểu ai gọi <code>handleError()</code>, error channel được chọn ra sao và transaction/retry thuộc về thành phần nào, ta có thể chẩn đoán lỗi theo đúng thread và endpoint, tránh mất bản tin hoặc nhầm việc “đã phát lỗi” với “đã phục hồi thành công”.

## Tài liệu tham khảo

- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/7.0/error-handling.html)
- [Spring Integration Reference — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html)
- [Spring Integration Reference — Configuring the Task Scheduler](https://docs.spring.io/spring-integration/reference/configuration/namespace-taskscheduler.html)
- [Spring Integration Javadoc — MessagePublishingErrorHandler](https://www.springframework.org/spring-integration/docs/6.5.x/api/org/springframework/integration/channel/MessagePublishingErrorHandler.html)
