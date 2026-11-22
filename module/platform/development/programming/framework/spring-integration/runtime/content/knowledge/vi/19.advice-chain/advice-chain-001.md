# Advice chain của endpoint trong Spring Integration

Trong Spring Integration, một **endpoint** nối message channel với phần xử lý: nhận message, gọi handler, rồi chuyển kết quả hoặc lỗi tới bước tiếp theo. Ngoài logic nghiệp vụ, ta thường cần retry, đo thời gian, kiểm tra trùng lặp, transaction hoặc phát cảnh báo. Nếu đưa toàn bộ các cơ chế này vào handler, mỗi use case sẽ phải tự xử lý những chi tiết của message runtime và khó duy trì hành vi nhất quán.

**Advice chain** là chuỗi các thành phần bao quanh một lần thực thi để bổ sung hành vi trước, sau hoặc khi lời gọi gặp exception. Bài học thuộc chương **Advice chain** của **SPRING_INTEGRATION_RUNTIME**, nơi Spring Integration điều phối message flow qua channel, consumer endpoint, poller, executor, đồng thời quản lý lifecycle, transaction, retry, message store, error flow và correlation. Mục tiêu là biết advice được gắn ở đâu, bao quanh đoạn xử lý nào và hệ quả của thứ tự các advice.

> **Điểm cốt lõi:** Advice gắn vào *handler invocation* và advice gắn vào *poller task* có phạm vi khác nhau. Cả hai thường được gọi là “advice của endpoint”, nhưng không thể thay thế cho nhau.

## 1. Advice chain hoạt động như thế nào?

Hình dung handler có nhiệm vụ <code>process(OrderCommand)</code>, được bao quanh bởi hai advice A và B:

~~~text
MessageChannel
    │
    ▼
Consumer endpoint
    │
    ▼
Advice A: trước khi gọi
    │
    ▼
Advice B: trước khi gọi
    │
    ▼
Handler: xử lý message
    │
    ▼
Advice B: xử lý kết quả / exception
    │
    ▼
Advice A: xử lý kết quả / exception
    │
    ▼
Reply hoặc chuyển tới flow tiếp theo
~~~

Đây là dạng **around invocation**: lời gọi đi vào chain theo thứ tự cấu hình và thoát ra theo thứ tự ngược lại, miễn các advice đều gọi tiếp callback. Nếu một advice không gọi tiếp, trả kết quả thay thế hoặc ném exception, handler hoặc các advice phía trong có thể không chạy.

Ví dụ khi có advice đo thời gian bao ngoài advice retry:

~~~mermaid
sequenceDiagram
    participant C as Consumer endpoint
    participant T as Timing advice
    participant R as Retry advice
    participant H as Business handler
    C->>T: invoke(message)
    T->>R: proceed()
    R->>H: attempt 1
    H--xR: transient exception
    R->>H: attempt 2
    H-->>R: success
    R-->>T: success
    T-->>C: result
    Note over T,R: Timing bên ngoài đo cả thời gian chờ và các lần retry
~~~

Nếu đổi thứ tự để timing nằm **trong** retry, số lần đo có thể bằng số lần thử, mỗi lần đo chỉ bao quanh một lần handler invocation. Vì thế, thứ tự advice là một phần của hành vi nghiệp vụ có thể quan sát được, không chỉ là cách trình bày cấu hình.

## 2. Những loại advice cần phân biệt

| Cơ chế | Phạm vi | Dùng khi nào? |
|---|---|---|
| **Request handler advice** (ví dụ <code>RequestHandlerRetryAdvice</code>) | Bao quanh xử lý request của message handler hỗ trợ cơ chế advice tương ứng | Retry, đánh giá kết quả/lỗi, kiểm soát xử lý tại handler |
| **Advice của poller** | Bao quanh tác vụ polling, có thể gồm nhận message rồi xử lý | Transaction tại ranh giới receive/process, điều tiết lịch poll, quản lý polling task |
| **AOP advice trên Spring service** | Bao quanh lời gọi method của bean thông qua Spring proxy | Transaction nghiệp vụ, bảo mật, metric hoặc logic dùng chung của application service |
| **Channel interceptor** | Can thiệp trước/sau thao tác send/receive trên channel | Quan sát lưu lượng, thêm/kiểm tra header và policy của channel |
| **Error handler/error flow** | Nhận exception hoặc <code>ErrorMessage</code> từ ranh giới runtime có cơ chế báo lỗi | Log, cảnh báo, quarantine, recovery và xử lý lỗi bất đồng bộ |

Ba điểm cần nhớ:

1. <code>Advice</code> của Spring AOP là một khái niệm chung, nhưng **khả năng gắn advice phụ thuộc loại endpoint và API mà handler hỗ trợ**. Không phải tất cả endpoint đều sử dụng cùng một điểm chặn.
2. <code>AbstractRequestHandlerAdvice</code> của Spring Integration hướng đến xử lý request tại các message handler thích hợp. Một custom advice cần can thiệp bao quanh toàn bộ <code>handleMessage()</code> có thể phải sử dụng cơ chế <code>HandleMessageAdvice</code> hoặc cấu hình interceptor được endpoint hỗ trợ, thay vì giả định mọi request handler advice bao phủ mọi bước.
3. Advice không tự di chuyển giữa thread của sender và worker. Điểm đặt advice quyết định thread nào chạy nó, exception nào nó thấy và transaction nào nó có thể tham gia.

### “Endpoint” khác “handler” ở đâu?

Một consumer endpoint, ví dụ <code>EventDrivenConsumer</code> hoặc <code>PollingConsumer</code>, chịu trách nhiệm đăng ký với channel hoặc chủ động polling. Message handler phía sau thực hiện tác vụ xử lý message. Trong Java DSL, thao tác:

~~~java
.handle(orderService, "process", e -> e.advice(retryAdvice))
~~~

gắn advice thông qua cấu hình endpoint/handler mà DSL hỗ trợ cho handler invocation. Không nên suy luận rằng advice đó tự động bao quanh việc nhận message từ queue, polling scheduler, chuyển đổi ở upstream, hoặc thao tác ACK của broker.

## 3. Ví dụ thực tế: retry advice quanh Service Activator

Giả sử hệ thống nhận lệnh đặt hàng; một lỗi database tạm thời nên được thử lại có giới hạn, còn dữ liệu nghiệp vụ không hợp lệ thì không nên thử lại. Service nhận command thuần Java, không phụ thuộc API của Spring Integration.

**Bước 1 — xây dựng use case:**

~~~java
public record OrderCommand(String orderId, int quantity) {}

public interface OrderStore {
    // Cần constraint/transaction thích hợp để tránh ghi trùng theo orderId.
    void saveIdempotently(OrderCommand order);
}

@Service
public class OrderService {
    private final OrderStore store;

    public OrderService(OrderStore store) {
        this.store = store;
    }

    @Transactional
    public void process(OrderCommand command) {
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException("quantity phải lớn hơn 0");
        }
        store.saveIdempotently(command);
    }
}
~~~

<code>OrderStore</code> là cổng lưu trữ minh họa; ứng dụng cần cung cấp implementation thực. <code>@Transactional</code> có tác dụng khi <code>OrderService</code> được gọi qua Spring proxy và đã cấu hình transaction manager phù hợp.

**Bước 2 — cấu hình <code>RequestHandlerRetryAdvice</code> và một endpoint bằng Java DSL:**

~~~java
@Configuration
@EnableIntegration
public class OrderIntegrationConfig {

    @Bean(name = "orders.input")
    MessageChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean
    RequestHandlerRetryAdvice orderRetryAdvice() {
        RetryTemplate template = new RetryTemplate();

        // 3 lần gọi tối đa, bao gồm lần đầu.
        template.setRetryPolicy(new SimpleRetryPolicy(3));

        FixedBackOffPolicy backOff = new FixedBackOffPolicy();
        backOff.setBackOffPeriod(250);
        template.setBackOffPolicy(backOff);

        RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
        advice.setRetryTemplate(template);
        return advice;
    }

    @Bean
    IntegrationFlow orderFlow(
            OrderService service,
            @Qualifier("orderRetryAdvice")
            RequestHandlerRetryAdvice retryAdvice) {
        return IntegrationFlow.from("orders.input")
            .handle(service, "process", e -> e.advice(retryAdvice))
            .get();
    }
}
~~~

Các kiểu quan trọng: <code>org.springframework.integration.dsl.IntegrationFlow</code>, <code>org.springframework.integration.handler.advice.RequestHandlerRetryAdvice</code>, <code>org.springframework.integration.channel.DirectChannel</code>, <code>org.springframework.integration.config.EnableIntegration</code>, <code>org.springframework.messaging.MessageChannel</code>; <code>org.springframework.retry.support.RetryTemplate</code>, <code>org.springframework.retry.policy.SimpleRetryPolicy</code>, <code>org.springframework.retry.backoff.FixedBackOffPolicy</code>. Cần dependency Spring Retry phù hợp với phiên bản ứng dụng.

**Bước 3 — gửi message đến endpoint:**

~~~java
OrderCommand command = new OrderCommand("O-104", 2);
Message<OrderCommand> request = MessageBuilder.withPayload(command)
    .setHeader("correlationId", "trace-O-104")
    .build();

ordersInput.send(request);
~~~

Trong đó <code>ordersInput</code> là bean <code>orders.input</code>. <code>MessageBuilder</code> thuộc <code>org.springframework.integration.support</code>. Với <code>DirectChannel</code>, consumer xử lý trên thread của lời gọi <code>send()</code>; khi handler thất bại rồi advice thử lại, chính thread đó phải chờ các lần thử.

**Lưu ý về mã ví dụ:** <code>SimpleRetryPolicy(3)</code> ở trên là thiết lập cơ bản để nhìn rõ cơ chế retry, **chưa phải chính sách production**: nó có thể retry cả exception không đáng retry, ví dụ <code>IllegalArgumentException</code>. Trong hệ thống thật cần phân loại lỗi transient/permanent và giới hạn backoff, thời gian xử lý, khả năng quá tải theo ngân sách độ trễ.

### Luồng gọi trong ví dụ

~~~mermaid
flowchart LR
    IN["orders.input<br/>DirectChannel"] --> EP["Service activator endpoint"]
    EP --> RA["RequestHandlerRetryAdvice"]
    RA --> SV["OrderService.process"]
    SV --> DB["OrderStore"]
    SV -. "exception" .-> RA
    RA -. "thử lại nếu policy cho phép" .-> SV
    RA -. "hết lượt: propagate/recover" .-> EX["Caller hoặc error flow tùy runtime"]
~~~

Advice retry bao quanh invocation của <code>process()</code>. Nó không đảm bảo đoạn xử lý trước endpoint (ví dụ transformer parse JSON) sẽ được chạy lại. Nếu conversion lỗi ở transformer upstream, advice đặt trên <code>process()</code> có thể không được gọi lần nào.

## 4. Thứ tự nhiều advice và tác dụng phụ

Giả sử có hai advice <code>metricsAdvice</code> và <code>retryAdvice</code> đều được endpoint hỗ trợ:

~~~java
.handle(service, "process",
    e -> e.advice(metricsAdvice, retryAdvice))
~~~

Trong một chain chạy theo thứ tự khai báo, advice đầu tiên bao ngoài advice phía sau:

~~~text
metricsAdvice.enter
  retryAdvice.enter
    process attempt #1 -> lỗi
    process attempt #2 -> thành công
  retryAdvice.exit
metricsAdvice.exit
~~~

Metric ngoài retry đếm **một** message được xử lý, còn thời gian đo bao gồm backoff và các lần thử. Đảo thứ tự hai advice làm thay đổi cái được quan sát (mỗi attempt so với toàn bộ logical request). Nếu advice có thể short-circuit, lần gọi phía trong cũng có thể không xảy ra.

Điều tương tự áp dụng với idempotent receiver, circuit breaker hay recovery advice:

- **Kiểm tra idempotency trước retry:** chặn một message đã xử lý thành công từ đầu; nhưng trạng thái “đang xử lý” và khi nào ghi khóa phải được thiết kế cẩn thận.
- **Retry bên trong idempotency:** một logical request có thể thử nhiều lần; phải bảo đảm retry không làm ghi trùng dữ liệu hoặc phát sự kiện trùng.
- **Recovery trước hay sau advice quan sát:** quyết định lỗi cuối cùng có được nhìn thấy là exception hay được chuyển thành kết quả hồi phục.

Không có “thứ tự tốt nhất” độc lập với mục tiêu. Khi chọn, hãy vẽ đoạn **before / proceed / after / catch** cho từng advice và ghi rõ trường hợp nào được coi là thành công.

## 5. Advice của poller khác advice của handler

Với <code>SubscribableChannel</code> (chẳng hạn <code>DirectChannel</code>), consumer nhận message khi sender gửi đến. Với <code>PollableChannel</code> (chẳng hạn <code>QueueChannel</code>), polling consumer chủ động <code>receive()</code> theo lịch.

~~~mermaid
flowchart TD
    Q["QueueChannel / nguồn polling"]
    POL["Poller task"]
    RX["receive()"]
    H["Handler"]
    ADV1["Poller advice<br/>bao quanh polling task"]
    ADV2["Handler advice<br/>bao quanh invocation"]
    Q --> RX
    ADV1 --> POL
    POL --> RX
    RX --> ADV2
    ADV2 --> H
~~~

**Poller advice** thường dùng khi cần bao quanh chu trình nhận và xử lý, ví dụ muốn một transaction do poller quản lý bao phủ <code>receive()</code> và phần xử lý message. **Handler advice** bao quanh handler được cấu hình, ví dụ retry một thao tác truy vấn hoặc gọi service. Một handler advice không thể rollback hoạt động nhận message đã commit ở một transaction độc lập.

Ví dụ annotation cho polling consumer (các bean <code>orders.queue</code> và <code>pollerTxAdvice</code> được giả định đã định nghĩa):

~~~java
@ServiceActivator(
    inputChannel = "orders.queue",
    poller = @Poller(
        fixedDelay = "1000",
        adviceChain = "pollerTxAdvice"
    )
)
public void consume(OrderCommand command) {
    orderService.process(command);
}
~~~

<code>@Poller</code> thuộc <code>org.springframework.integration.annotation</code>. <code>pollerTxAdvice</code> có thể là transaction advice được tạo từ Spring Transaction và transaction manager phù hợp. Ví dụ minh họa **điểm gắn** advice, chưa khai báo đầy đủ bean, store hay transaction manager.

| Câu hỏi | Advice ở handler | Advice ở poller |
|---|---|---|
| Bao quanh lời gọi handler? | Có, tại điểm interceptor được cấu hình | Có thể bao phủ khi handler chạy trong poll task |
| Bao quanh <code>receive()</code>? | Thường không | Có thể, tùy cấu hình advice/transaction |
| Phù hợp với <code>DirectChannel</code>? | Có với handler hỗ trợ | Không có polling task để can thiệp |
| Phù hợp khi lấy message từ queue? | Retry logic riêng của handler | Điều khiển hành vi toàn chu kỳ nhận/xử lý |
| Ảnh hưởng ACK/redelivery? | Gián tiếp nếu exception lan ra | Phụ thuộc transaction của nguồn, message store và adapter |

Lưu ý: Retry logic tại handler có thể thực hiện lại lời gọi xử lý trên **cùng message đã nhận**, còn redelivery của broker hoặc message store là một cơ chế khác: nguồn phát message trở lại cho consumer. Không nên coi hai cơ chế này là tương đương.

## 6. Transaction và retry: đặt thứ tự đúng

Giả sử có retry advice và transaction advice. Hai cấu hình tưởng giống nhau nhưng có hệ quả khác:

### A. Retry bao ngoài transaction của service

~~~text
RetryAdvice
  ├─ attempt 1
  │    └─ @Transactional OrderService -> rollback khi lỗi
  ├─ attempt 2
  │    └─ @Transactional OrderService -> rollback khi lỗi
  └─ attempt 3
       └─ @Transactional OrderService -> commit nếu thành công
~~~

Mô hình này thường phù hợp khi muốn **mỗi attempt có transaction mới**, miễn rằng không tồn tại một transaction bên ngoài đã bao lấy cả chuỗi và lời gọi service đi qua Spring proxy. <code>@Transactional</code> mặc định dùng propagation <code>REQUIRED</code>, nên nếu caller đã có transaction, nó có thể tham gia transaction đó thay vì tạo transaction mới.

### B. Transaction bao ngoài retry

~~~text
PollerTransactionAdvice
  └─ RetryAdvice
       ├─ attempt 1 -> lỗi
       ├─ attempt 2 -> lỗi
       └─ attempt 3 -> thành công
  └─ commit / rollback cho toàn bộ poll task
~~~

Các attempt có thể cùng nằm trong một transaction. Một exception trong lần đầu có thể khiến transaction bị đánh dấu rollback-only; dù một attempt sau thành công, commit cuối vẫn có thể thất bại. Với database, JPA persistence context, lock và transaction timeout, retry trong cùng transaction có thể gây lỗi thứ cấp khó hiểu.

**Cách quyết định:** Xác định transaction cần bao gồm phần nào: chỉ thay đổi dữ liệu của service, hay cả thao tác lấy message khỏi transactional channel/source. Nếu cần retry toàn bộ transaction, hãy dùng cấu trúc advice và propagation làm cho **mỗi attempt thật sự có transaction mới**. Nếu cần nhận message và thay đổi database nguyên tử, phải xem tính chất transactional của message source/broker và transaction manager; advice không tự tạo một giao dịch phân tán.

### Chú ý idempotency và side effect

Retry có thể thực thi service nhiều lần. Một attempt thất bại **sau khi** đã gửi email, gọi API thanh toán hoặc phát sự kiện có thể để lại side effect bên ngoài dù database rollback. Sử dụng idempotency key theo nghiệp vụ, unique constraint, inbox/outbox hoặc cơ chế bù phù hợp. <code>MessageHeaders.ID</code> và correlation ID không đương nhiên là khóa idempotency ổn định.

## 7. Exceptions, recovery và error channel

Một advice có thể **quan sát**, **thử lại**, **biến đổi** hoặc **nuốt** exception. Cần ghi rõ chính sách để người vận hành không hiểu nhầm:

| Kết quả sau chain | Handler/endpoint phía ngoài nhìn thấy | Tác động runtime |
|---|---|---|
| Handler thành công ngay | Kết quả bình thường | Flow tiếp tục |
| Handler lỗi rồi retry thành công | Kết quả thành công sau nhiều attempt | Metrics/log nên ghi nhận retry đã xảy ra |
| Hết retry, advice ném lại exception | Exception lan tới caller/consumer boundary | Đồng bộ có thể báo lỗi trực tiếp; bất đồng bộ/poller xử lý theo error handler |
| Recovery callback trả kết quả/thay thế | Endpoint có thể thấy một kết quả đã recover | Không tự động tạo rollback/redelivery; cần phân biệt “đã khôi phục” và “đã xử lý nghiệp vụ” |
| Advice nuốt exception và trả <code>null</code> / trạng thái thành công | Phía ngoài có thể không biết thất bại | Có thể dẫn tới ACK/remove message mà không có recovery mong muốn |

<code>RequestHandlerRetryAdvice</code> có thể được cấu hình recovery callback; với chiến lược phù hợp, ứng dụng có thể dùng <code>ErrorMessageSendingRecoverer</code> để gửi lỗi khi đã hết lượt thử. Tuy nhiên, nếu exception cũng tiếp tục lan đến scheduler error handler hoặc adapter recovery, có thể xuất hiện **hai đường báo lỗi** cho một message. Phải xác định rõ thành phần nào chịu trách nhiệm publish lỗi cuối cùng.

Trong runtime:

- Với <code>DirectChannel</code>, exception chưa được xử lý ở handler thường lan về sender theo call stack; có thể được Spring Messaging wrap thành <code>MessagingException</code>.
- Với <code>ExecutorChannel</code> hoặc subscriber chạy trên executor, xử lý diễn ra ở thread khác; cần kiểm tra cơ chế error handling thực tế của channel/dispatcher và error channel được cấu hình.
- Với poller, exception trong task có thể được task scheduler/error handler chuyển thành <code>ErrorMessage</code>. <code>MessagePublishingErrorHandler</code> là một thành phần thường gặp trong cơ chế này.
- Với broker inbound adapter, ACK, requeue, dead-letter và lỗi deserialize có thể do listener/container quyết định; advice của handler trong Spring Integration không tự bao phủ các bước trước khi tạo message.

Error channel, retry advice và dead-letter queue là các thành phần **khác nhau**. Đã gửi <code>ErrorMessage</code> không có nghĩa message nguồn sẽ tự được retry hoặc đã được lưu bền vững.

## 8. Threading, poller và hiệu năng

Advice thực thi ở ranh giới mà nó được gắn:

| Topology | Thread chạy handler advice | Rủi ro vận hành |
|---|---|---|
| Sender → <code>DirectChannel</code> → handler | Thread sender | Retry/backoff kéo dài thời gian <code>send()</code>, có thể làm gateway timeout |
| Sender → <code>ExecutorChannel</code> → handler | Thường là worker thread | Retry giữ worker lâu; thread pool/queue có thể bão hòa |
| <code>QueueChannel</code> → poller → handler | Poller/scheduler thread hoặc thread được cấu hình | Retry kéo dài một poll cycle, giảm tốc độ tiêu thụ và tăng queue depth |
| Adapter bên ngoài → integration channel | Phụ thuộc thread dispatch của adapter và channel | Có thể giữ thread listener, ảnh hưởng ACK và throughput |

**Backoff đồng bộ** trong retry thường giữ thread chờ. Nếu có 20 worker, mỗi message retry nhiều lần với thời gian chờ lớn, throughput giảm dù logic service thực tế chỉ chạy vài mili giây. Tính ngân sách thời gian:

~~~text
Tổng thời gian ≈ Σ thời gian thực thi mỗi attempt
              + Σ khoảng backoff
              + overhead tại endpoint/channel
~~~

Ví dụ minh họa: ba attempt, mỗi attempt mất khoảng 100 ms và hai lần chờ 250 ms, tổng khoảng 800 ms (chưa kể overhead). Đây chỉ là phép tính minh họa, không phải một cam kết latency. Với request–reply gateway cần kiểm tra timeout của gateway, output channel, thread pool và upstream client để tránh việc caller timeout nhưng worker vẫn tiếp tục thực hiện side effect.

Nếu chọn retry policy theo loại exception, có thể giảm retry vô ích và giữ tài nguyên cho các message có cơ hội phục hồi. Metric hữu ích gồm: số lần retry/attempt, thời gian bao quanh handler, thời gian chờ, số lỗi sau hết lượt, queue depth, số thread active, rejected tasks, tỷ lệ timeout và tình trạng endpoint <code>isRunning</code>.

## 9. Lifecycle của flow có ảnh hưởng gì đến advice?

Spring Integration có thể quản lý endpoint thông qua <code>SmartLifecycle</code> và quản lý flow đăng ký động qua <code>IntegrationFlowContext</code>. Advice chain được gắn khi endpoint/handler được xây dựng và khởi tạo; việc start/stop endpoint không đồng nghĩa advice tự dọn dẹp các tác vụ đang retry.

- **Start:** endpoint có thể nhận/poll message và advice được áp dụng cho invocation thuộc phạm vi cấu hình.
- **Stop:** ngăn việc nhận/poll mới tùy endpoint, nhưng công việc đã giao executor hoặc đang backoff có thể còn chạy; cần graceful shutdown và quan sát in-flight work.
- **Đổi cấu hình chain:** thường phải thay đổi cấu hình bean/endpoint hoặc đăng ký lại flow phù hợp. Không giả định sửa một danh sách advice tùy ý khi runtime đang chạy là an toàn.
- **Restart ứng dụng:** trạng thái in-memory của retry counter hoặc duplicate detector có thể mất; nếu muốn bảo toàn lịch sử xử lý, dùng store phù hợp.

Advice chain không phải “bộ điều phối toàn flow”. Một advice đặt ở handler A sẽ không tự áp dụng cho handler B ở phía sau, trừ khi đã gắn vào B hoặc nằm ở một phạm vi lớn hơn theo thiết kế.

## 10. Kiểm thử advice chain

Nên kiểm thử **hành vi quan sát được** thay vì chỉ kiểm tra bean đã tồn tại.

| Kịch bản | Kết quả mong đợi |
|---|---|
| Handler thành công ở lần đầu | Một lần gọi service, không có backoff |
| Lỗi transient ở hai lần đầu, lần ba thành công | Ba invocation; side effect cuối cùng đúng một lần theo hợp đồng |
| Lỗi permanent | Chính sách không retry hoặc dừng đúng số lần; caller/error flow nhận lỗi |
| Hai advice cùng gắn | Thứ tự vào/ra đúng; metric ngoài retry đo tổng, metric trong retry đo từng attempt |
| Retry kết thúc bằng recovery | Kết quả và error message phù hợp; không vừa ACK thành công vừa làm mất dữ liệu |
| Poller có transaction advice | Biên transaction của <code>receive</code>/<code>handle</code> đúng như thiết kế và rollback có thể nhận lại message nếu nguồn hỗ trợ |
| Handler chạy ở executor | Error routing quan sát được ở thread worker; caller không dựa vào exception từ <code>send()</code> |
| Stop endpoint khi đang retry | Có xử lý hợp lý cho in-flight work và dữ liệu chưa hoàn tất |

**Ví dụ unit test ý tưởng**: fake <code>OrderStore</code> ném lỗi transient hai lần rồi thành công; gọi message qua <code>orders.input</code> trong Spring context; xác nhận store được gọi ba lần, message có kết quả mong muốn và không có bản ghi trùng. Kiểm tra riêng trường hợp quantity không hợp lệ để bảo đảm retry policy không lặp một lỗi chắc chắn thất bại. Dùng spy/mock hoặc bộ đếm ở biên store, tránh kiểm thử bằng cách chờ thời gian cố định rồi suy ra lỗi đã được xử lý.

Với test transaction nên dùng database/test store có semantics thực thay vì chỉ mock <code>@Transactional</code>. Với flow bất đồng bộ nên chờ theo điều kiện có timeout (latch/queue hoặc công cụ polling assertion), không assert ngay sau khi gọi <code>send()</code>.

## 11. Sai lầm thường gặp và cách sửa

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Handler không được retry | Advice gắn vào endpoint khác hoặc lỗi xảy ra trước handler đích | Xác định endpoint thực sự ném lỗi; gắn advice đúng vị trí |
| Cùng một message được xử lý hai lần | Retry/redelivery, side effect không idempotent | Unique key, inbox/outbox, kiểm soát recovery và transaction |
| Giao dịch rollback dù retry cuối thành công | Retry diễn ra trong transaction đã bị đánh dấu rollback-only | Thiết kế lại thứ tự retry/transaction và propagation |
| Caller không thấy exception | Handler chạy ở executor hoặc advice đã recover/nuốt lỗi | Xem ranh giới thread và đường <code>ErrorMessage</code> |
| Queue phình to khi database chậm | Retry giữ thread worker/poller quá lâu | Giới hạn attempts/backoff, bảo vệ pool, cân nhắc cơ chế retry theo lịch |
| Metric đếm một message thành nhiều requests | Advice metrics nằm bên trong retry | Đặt metric theo đúng đơn vị đo: logical message hay attempt |
| Không rollback được message nhận từ queue | Queue/message store không transactional hoặc receive đã commit | Rà soát transaction của nguồn và cơ chế redelivery |
| Flow đã stop nhưng vẫn có log xử lý | Task đã chạy/được giao trước lúc stop | Theo dõi in-flight task và shutdown behavior |
| Error channel không nhận lỗi | Lỗi được xử lý trong advice, hoặc flow đồng bộ ném về caller | Làm rõ điểm sở hữu error/recovery và thử nghiệm từng đường |

## 12. Checklist trước khi đưa vào production

1. Xác định advice được gắn ở **handler**, **poller** hay **Spring service proxy**; mô tả đoạn gọi mà advice thực sự bao quanh.
2. Ghi rõ thứ tự vào/ra của từng advice; xác định khi nào advice retry, return, short-circuit, recover hoặc ném lại exception.
3. Phân loại lỗi transient/permanent, giới hạn retries và backoff; đặt ngân sách thời gian phù hợp với timeout của gateway, poller và executor.
4. Xác định transaction boundary cho từng attempt và thao tác receive/ACK; kiểm tra với nguồn dữ liệu/message store thực.
5. Bảo đảm side effect có idempotency key hoặc phương án chống trùng, nhất là với broker redelivery và retry.
6. Quan sát được correlation, endpoint/thread, attempt count, latency, số lỗi và độ sâu queue; không log dữ liệu nhạy cảm.
7. Có chủ sở hữu rõ ràng cho recovery/error channel/DLQ; kiểm thử trường hợp advice nuốt lỗi và trường hợp publish error thất bại.
8. Kiểm tra lifecycle start/stop, shutdown executor và hành vi khi hệ thống restart giữa các attempt.

**Kết luận:** Advice chain giúp bổ sung các chính sách runtime quanh consumer endpoint mà không buộc service nghiệp vụ phụ thuộc vào chi tiết message flow. Để dùng đúng, phải nhìn rõ **điểm gắn advice**, **thứ tự bao quanh lời gọi**, **ranh giới transaction và thread**, cùng **chính sách retry/recovery**. Những quyết định này chi phối lỗi sẽ đi đâu, message có thể bị xử lý lại hay không và hệ thống giữ được throughput ra sao.

## Tài liệu tham khảo

- [Spring Integration Reference](https://docs.spring.io/spring-integration/reference/)
- [Spring Integration Javadoc](https://docs.spring.io/spring-integration/api/)
- [Spring Retry Reference](https://docs.spring.io/spring-retry/reference/)
