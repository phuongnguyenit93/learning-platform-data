# Retry advice quanh message handler trong Spring Integration

## 1. Mục tiêu và bối cảnh runtime

Trong **SPRING_INTEGRATION_RUNTIME**, các message được điều phối qua `MessageChannel`, consumer endpoint, poller và executor. Khi một handler gọi HTTP, truy vấn database hoặc đẩy message sang hệ thống khác, lỗi tạm thời có thể khiến việc xử lý thất bại dù message đầu vào hoàn toàn hợp lệ. Phần **Retry và recovery → Retry advice quanh message handler** giải thích cách thử lại **đúng thao tác của handler** và định tuyến lỗi cuối cùng để vận hành được quan sát, kiểm soát.

Ví dụ hệ thống có flow:

~~~mermaid
flowchart LR
    A["requests"] --> C["Consumer endpoint"]
    C --> R["RequestHandlerRetryAdvice"]
    R --> H["Gọi message handler\ngửi đơn đến dịch vụ vận chuyển"]
    H -->|Thành công| S["Hoàn tất thao tác"]
    H -->|Lỗi có thể retry| R
    H -->|Hết retry / không retry| E{"Có recoveryCallback?"}
    E -->|Có| F["ErrorMessageSendingRecoverer"]
    F --> G["recoveryChannel\nDLQ / audit / cảnh báo"]
    E -->|Không| X["Ném exception cho caller\nhoặc error flow phù hợp"]
~~~

Mục tiêu cụ thể:

- Gắn `RequestHandlerRetryAdvice` vào một message handler thay vì xử lý lại toàn bộ flow.
- Kiểm soát loại lỗi, số lần thử lại, khoảng dừng (backoff), thời gian chờ và phương án recovery.
- Phân biệt **stateless retry** (thử ngay trong cùng lần xử lý) với **stateful retry** (dựa vào nguồn phát lại message).
- Hiểu tác động của `DirectChannel`, poller, executor, transaction, lỗi bất đồng bộ và khả năng xử lý trùng.
- Theo dõi số lần gọi thực tế, lỗi cuối, message gốc, correlation và trạng thái endpoint.

**Nguyên tắc cốt lõi:** retry là hành vi lặp lại một thao tác có thể thất bại do nguyên nhân tạm thời. Retry không sửa được đầu vào sai vĩnh viễn, không tự tạo transaction và không bảo đảm "exactly once".

## 2. Retry advice bọc phần nào của flow?

`RequestHandlerRetryAdvice` là một dạng request-handler advice của Spring Integration. Nó bao quanh việc thực thi handler mục tiêu, giống một lớp `around advice`; khi handler ném exception, advice kiểm tra policy rồi quyết định thử lại, phục hồi hoặc đẩy exception ra ngoài.

Ví dụ flow:

~~~text
inbound-adapter -> transform -> httpOutboundGateway -> jdbcOutboundAdapter
                                      ^
                            retry advice đặt ở đây
~~~

Nếu gateway HTTP gặp lỗi tạm thời, gắn retry trực tiếp vào gateway giúp thử lại HTTP call, **không phải mặc nhiên chạy lại transformer và JDBC**. Nếu thay vào đó gắn retry ở **poller** bao quanh thao tác poll/dispatch, phạm vi có thể bao gồm nhiều endpoint downstream thực thi đồng bộ; lỗi ở bước JDBC có thể khiến HTTP gateway chạy lại. Cần lựa chọn ranh giới theo mục tiêu nghiệp vụ.

| Vị trí cấu hình | Đối tượng bị lặp lại | Khi phù hợp | Nguy cơ |
| --- | --- | --- | --- |
| Request handler advice cho HTTP outbound gateway | Lời gọi handler HTTP | Thử lại lỗi mạng/API tại điểm gọi | Gửi lại cùng request; endpoint bên ngoài cần idempotent |
| Request handler advice cho `@ServiceActivator` | Lời gọi method/handler đã được advice | Xử lý lại thao tác tại endpoint cụ thể | Side effect bên trong handler có thể lặp |
| Poller advice | Chu trình lấy và xử lý message theo cơ chế poller | Retry/transaction tại ranh giới polling | Có thể thực thi lại cả đoạn flow đồng bộ |
| Retry tại adapter/broker client | Chuyển tải/redelivery theo adapter/broker | Tận dụng ack, nack, rollback, retry broker | Có thể chồng nhiều tầng retry nếu handler cũng retry |

Chi tiết phạm vi: đối với handler tạo reply (`AbstractReplyProducingMessageHandler`), request-handler advice thường được áp dụng tại `handleRequestMessage()`; thao tác gửi reply tới downstream thông thường nằm **ngoài** advice đó. Để bao cả lời gọi `handleMessage()` và luồng bên dưới, cần cân nhắc cơ chế `HandleMessageAdvice`/`HandleMessageAdviceAdapter` hoặc đặt retry ở ranh giới khác. Hãy kiểm tra phạm vi thực sự thay vì giả định một advice ở endpoint bao toàn bộ pipeline.

Retry **chỉ kích hoạt khi có exception đi ra phạm vi advice**. Nếu handler tự bắt lỗi rồi trả giá trị "failed" hoặc chỉ log và nuốt exception, advice coi lần gọi là thành công và sẽ không retry.

## 3. Vòng đời của một lần retry và số lần gọi

Một execution theo kiểu stateless có diễn biến:

~~~mermaid
sequenceDiagram
    participant M as MessageChannel
    participant A as Retry advice
    participant H as Handler
    participant R as Recovery channel
    M->>A: Message
    A->>H: Attempt #1
    H-->>A: Exception
    A->>A: RetryPolicy? Backoff
    A->>H: Attempt #2
    H-->>A: Exception
    A->>A: RetryPolicy? Backoff
    A->>H: Attempt #3
    alt Attempt #3 thành công
        H-->>A: Kết quả / hoàn tất
        A-->>M: Kết thúc bình thường
    else Attempt #3 thất bại
        H-->>A: Exception cuối
        A->>R: RecoveryCallback (nếu có)
        A-->>M: Hoàn tất theo kết quả recovery
    end
~~~

### Lưu ý phiên bản quan trọng: Spring Integration 6.x và 7.x

API retry thay đổi giữa hai thế hệ Spring Integration. Không nên copy cấu hình chính sách retry từ bài hướng dẫn phiên bản khác:

| Đặc điểm | Spring Integration 6.x | Spring Integration 7.x |
| --- | --- | --- |
| Nền tảng retry | **Spring Retry** (`org.springframework.retry.*`) | **Spring Framework Retry** (`org.springframework.core.retry.*`) |
| Cấu hình trên `RequestHandlerRetryAdvice` | `setRetryTemplate(org.springframework.retry.support.RetryTemplate)` | `setRetryPolicy(org.springframework.core.retry.RetryPolicy)` hoặc `setBackOff(...)` |
| Tham số số lần | `maxAttempts` = **tổng số lần gọi**, gồm lần đầu | `maxRetries` = **số lần thử lại sau lần đầu** |
| Mặc định của advice | Thường **3 lần gọi tổng cộng**, không delay | **3 retries sau lần đầu** (tối đa 4 lần gọi), không delay |
| Stateful API | `RetryStateGenerator` | `setStateKeyFunction(...)` và state cache |
| Recovery | `setRecoveryCallback(...)`, thường `ErrorMessageSendingRecoverer` | Vẫn hỗ trợ `setRecoveryCallback(...)` |

**Ví dụ về số lần:** `maxAttempts(3)` của Spring Retry 6.x tương đương **một lần đầu + hai retry**. `maxRetries(2)` của Spring Framework Retry 7.x cũng tương đương **một lần đầu + hai retry**. Với bài học này, ví dụ chính dùng **Spring Integration 7.x**; mục 6 cung cấp phiên bản 6.x.

Không suy số lần dựa trên tên property đơn thuần: cần đo **số lần handler thực sự được gọi** và xem chính sách đang dùng. Ngoài ra, tính backoff mặc định của `RequestHandlerRetryAdvice` có thể khác `RetryPolicy.withDefaults()` dùng độc lập; hãy đặt cấu hình cụ thể cho flow quan trọng.

## 4. Cấu hình `RequestHandlerRetryAdvice` theo annotation (Spring Integration 7.x)

Có thể khai báo bean advice và tham chiếu từ `@ServiceActivator(adviceChain = "retryAdvice")`:

~~~java
// Spring Integration 7.x, Spring Framework 7.x
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.retry.RetryPolicy;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;

@Configuration
class HandlerRetryConfiguration {

    @Bean("retryAdvice")
    RequestHandlerRetryAdvice retryAdvice() {
        RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();

        // 1 initial attempt + tối đa 2 retries = tối đa 3 lời gọi.
        RetryPolicy policy = RetryPolicy.builder()
                .maxRetries(2)
                .delay(Duration.ofMillis(100))
                .multiplier(2.0)
                .maxDelay(Duration.ofMillis(400))
                .build();

        advice.setRetryPolicy(policy);
        return advice;
    }
}
~~~

~~~java
import org.springframework.integration.annotation.MessageEndpoint;
import org.springframework.integration.annotation.ServiceActivator;

@MessageEndpoint
class ShipmentHandler {

    @ServiceActivator(inputChannel = "shipmentRequests",
                      adviceChain = "retryAdvice")
    public void sendShipment(ShipmentRequest request) {
        shippingApi.submit(request); // ví dụ phụ thuộc nghiệp vụ
    }
}
~~~

Đoạn `ShipmentHandler` minh họa vị trí gắn annotation, không phải chương trình tự chạy: phải có type `ShipmentRequest`, bean `shippingApi`, channel `shipmentRequests` và cấu hình context. Ví dụ tự chứa hơn nằm ở mục 5.

Các yếu tố đáng chỉnh:

| Thuộc tính / chính sách | Vai trò | Gợi ý sử dụng |
| --- | --- | --- |
| `maxRetries(n)` | Cho phép nhiều nhất `n` lần retry sau lần đầu | Giới hạn rõ ràng theo SLA và tính chất lỗi |
| `delay(...)` | Khoảng chờ đầu tiên | Tránh retry dồn dập khi dịch vụ ngoài đang quá tải |
| `multiplier(...)` | Nhân thời gian chờ ở các lần sau | Exponential backoff phù hợp cho lỗi tạm thời |
| `maxDelay(...)` | Chặn delay tăng vô hạn | Bảo vệ latency và worker resources |
| `jitter(...)` | Tạo độ ngẫu nhiên cho delay | Giảm nhiều worker retry đồng loạt |
| `includes(...)` / `excludes(...)` | Khoanh vùng exception được retry | Chỉ retry lỗi tạm thời, loại trừ lỗi nghiệp vụ vĩnh viễn |
| `setRecoveryCallback(...)` | Chạy sau khi retry không thành công hoặc lỗi không retry | Ghi nhận/dồn sang error flow, hoàn trả fallback có kiểm soát |

Trong Spring Integration, exception của method đôi khi được bọc trong `MessageHandlingException`/`MessagingException`. Khi định nghĩa `includes`/`excludes`, phải xác nhận policy có xét cause chain và kiểm thử trên exception **thực tế quan sát được**. Đừng chỉ lọc theo một class nguyên thủy rồi bỏ qua wrapper.

### Registration và DSL

`@ServiceActivator`, `@Transformer`, `@Filter`, `@Splitter` hỗ trợ tham chiếu `adviceChain` đến tên bean tương ứng. Trong Java DSL có thể gắn advice ngay tại endpoint:

~~~java
@Bean
IntegrationFlow shipmentFlow(ShipmentService service,
                             RequestHandlerRetryAdvice retryAdvice) {
    return IntegrationFlow.from("shipmentRequests")
            .handle(service, "sendShipment", e -> e.advice(retryAdvice))
            .get();
}
~~~

Mã DSL là **lựa chọn thay thế** annotation endpoint ở trên; không đăng ký cả hai consumer cho cùng `shipmentRequests` nếu mục tiêu là xử lý mỗi message một lần. Với XML namespace, request-handler advice được đặt trong `<int:request-handler-advice-chain>` và có tag retry chuyên dụng; các attribute giữa 6.x và 7.x khác tên, nên tra tài liệu đúng version.

## 5. Ví dụ có thể chạy: thành công sau retry và recovery khi hết lượt

Ví dụ dưới đây dùng Spring Integration 7.x, Spring Framework 7.x, Java 17+ và Spring Boot tương thích. Đặt toàn bộ mã vào **một file** `RetryAdviceDemoApplication.java` trong package `demo.integration`; dependency cần có Spring Integration core/starter tương thích với Spring Boot. Demo dùng `DirectChannel` để nhìn thấy lời gọi đồng bộ và dùng bộ đếm trong bộ nhớ để mô phỏng lỗi.

~~~java
package demo.integration;

import java.time.Duration;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.retry.RetryPolicy;
import org.springframework.integration.annotation.MessageEndpoint;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.handler.advice.ErrorMessageSendingRecoverer;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootApplication
@EnableIntegration
public class RetryAdviceDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(RetryAdviceDemoApplication.class, args);
    }

    @Bean("requests")
    MessageChannel requests() {
        return new DirectChannel();
    }

    @Bean("recoveries")
    MessageChannel recoveries() {
        return new DirectChannel();
    }

    @Bean("retryAdvice")
    RequestHandlerRetryAdvice retryAdvice(
            @Qualifier("recoveries") MessageChannel recoveries) {

        RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
        advice.setRetryPolicy(RetryPolicy.builder()
                .maxRetries(2)                 // 3 calls total
                .delay(Duration.ofMillis(50))
                .multiplier(2.0)
                .maxDelay(Duration.ofMillis(200))
                .build());

        advice.setRecoveryCallback(
                new ErrorMessageSendingRecoverer(recoveries));
        return advice;
    }

    @Bean
    ApplicationRunner demo(@Qualifier("requests") MessageChannel requests) {
        return args -> {
            requests.send(MessageBuilder.withPayload("temporary")
                    .setHeader("traceId", "trace-101")
                    .build());
            requests.send(MessageBuilder.withPayload("permanent")
                    .setHeader("traceId", "trace-102")
                    .build());
        };
    }
}

@MessageEndpoint
class DemoHandlers {

    private final ConcurrentMap<String, AtomicInteger> invocations =
            new ConcurrentHashMap<>();

    @ServiceActivator(inputChannel = "requests", adviceChain = "retryAdvice")
    public void handle(Message<String> message) {
        String taskId = message.getPayload();
        int attempt = invocations
                .computeIfAbsent(taskId, id -> new AtomicInteger())
                .incrementAndGet();

        System.out.printf("handle %s attempt=%d thread=%s%n",
                taskId, attempt, Thread.currentThread().getName());

        // "temporary" thành công ở lần 3; "permanent" luôn lỗi.
        if (("temporary".equals(taskId) && attempt < 3)
                || "permanent".equals(taskId)) {
            throw new IllegalStateException("Simulated downstream failure");
        }
        System.out.println("DELIVERED " + taskId);
    }

    @ServiceActivator(inputChannel = "recoveries")
    public void onRecovery(ErrorMessage error) {
        Message<?> original = error.getOriginalMessage();
        Throwable cause = error.getPayload();

        System.out.printf("RECOVER original=%s error=%s%n",
                original == null ? "unknown" : original.getPayload(),
                cause.getClass().getSimpleName());
    }
}
~~~

Kết quả về mặt hành vi:

| Message | Các lần handler được gọi | Kết quả |
| --- | --- | --- |
| `temporary` | #1 lỗi, #2 lỗi, #3 thành công | Log `DELIVERED temporary`, không gửi recovery |
| `permanent` | #1 lỗi, #2 lỗi, #3 lỗi | Một `ErrorMessage` gửi đến `recoveries`; `onRecovery` ghi lỗi |
| Message có lỗi nhưng handler tự nuốt exception | Thường chỉ một lần | Advice không biết lỗi; không retry |

Thời điểm log có thể khác nhau theo scheduler/CPU; với `DirectChannel` và stateless retry, các lời gọi handler của cùng message trong ví dụ xảy ra theo chuỗi trên thread gửi. Phần `onRecovery` chạy đồng bộ vì `recoveries` cũng dùng `DirectChannel`.

**Điểm cần lưu ý về contract:** `ErrorMessageSendingRecoverer` gửi một `ErrorMessage` mang lỗi cuối tới recovery channel. Nó không tự cung cấp dead-letter store bền vững. Nếu consumer recovery xử lý thành công, advice có thể kết thúc mà không ném exception ra nguồn nhận message. Vì vậy, trong hệ thống dùng broker với ack, recovery cần đảm bảo đã lưu/định tuyến lỗi theo đúng guarantee mong muốn trước khi coi message đã xử lý xong.

Bộ đếm `ConcurrentMap` chỉ dùng để minh họa và **không** phải retry state production, không bền vững khi restart; production nên dùng idempotency key và lưu trạng thái công việc trong hệ thống phù hợp.

## 6. Nếu ứng dụng dùng Spring Integration 6.x

Không sử dụng import `org.springframework.core.retry.RetryPolicy` hoặc `setRetryPolicy(...)` trong Spring Integration 6.x. Thay bằng `RetryTemplate` của thư viện **Spring Retry** và `setRetryTemplate(...)`:

~~~java
// Spring Integration 6.x + Spring Retry 2.x
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.retry.support.RetryTemplate;

@Bean("retryAdvice")
RequestHandlerRetryAdvice retryAdvice() {
    RetryTemplate template = RetryTemplate.builder()
            .maxAttempts(3)               // 1 initial + 2 retries
            .exponentialBackoff(100, 2.0, 400)
            .build();

    RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
    advice.setRetryTemplate(template);
    return advice;
}
~~~

Đoạn này minh họa một method bean trong `@Configuration`, cần import `org.springframework.context.annotation.Bean`. Nếu muốn recovery như mục 5, thêm `advice.setRecoveryCallback(new ErrorMessageSendingRecoverer(recoveries))` với channel đã khai báo.

Với policy loại exception ở 6.x, lời gọi method có thể ném `MessagingException` bao bọc lỗi gốc; tài liệu API khuyến nghị bật **cause traversal** của policy khi cần phân loại theo nguyên nhân bên trong. API và tên thuộc tính XML của các thế hệ khác nhau; hãy dùng Javadoc trùng phiên bản dependency thực tế.

## 7. Recovery sau khi các lần thử đã hết

`RecoveryCallback` quyết định hành vi cuối vòng retry. Một triển khai phổ biến là `ErrorMessageSendingRecoverer`, phát `ErrorMessage` đến một channel để xử lý:

~~~java
RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
advice.setRecoveryCallback(
        new ErrorMessageSendingRecoverer(recoveryChannel));
~~~

Phân biệt các lựa chọn:

| Trạng thái cuối | Không có recovery callback | Có `ErrorMessageSendingRecoverer` |
| --- | --- | --- |
| Handler thành công | Chuyển tiếp bình thường | Chuyển tiếp bình thường, không có recovery |
| Hết số lần retry, vẫn lỗi | Exception lan về caller hoặc error flow tại ranh giới thích hợp | Gửi `ErrorMessage` đến recovery channel; callback có thể kết thúc lỗi theo contract của nó |
| Lỗi được policy xác định không retry | Lỗi thoát ra theo cơ chế policy/advice | Có thể kích hoạt recovery ngay tùy cách policy/callback xử lý |
| Consumer của recovery channel ném exception | Không áp dụng | Lỗi recovery có thể lan ngược; không coi recovery chắc chắn thành công |

Một recovery flow hữu ích cần có ít nhất: **khóa công việc gốc**, **loại lỗi + stack trace rút gọn**, **tần suất/attempt**, **timestamp**, **trace/correlation ID**, và **hành động tiếp theo**. Với retry có thể phát sinh duplicate, cần ghi nhận event theo khóa idempotency.

Trong môi trường gửi message bền vững, thường gặp ba chiến lược:

1. **Dead-letter:** chuyển payload + headers cần thiết + mô tả lỗi sang DLQ/bảng lỗi; sau đó xử lý lại có kiểm soát.
2. **Compensation:** ghi trạng thái thất bại và kích hoạt nghiệp vụ hoàn tác hoặc workflow sửa lỗi, nếu handler đã tạo side effect trước đó.
3. **Fallback:** trả kết quả thay thế khi thật sự có contract cho phép; không biến lỗi mất dữ liệu thành "thành công" bằng một giá trị mặc định tùy tiện.

Một `RecoveryCallback` có thể trả về object. Với handler tạo reply, giá trị đó có thể ảnh hưởng semantics reply; phải xác nhận output contract/`requiresReply`. Với handler `void` như ví dụ, dùng recoverer để phân luồng lỗi rõ ràng và không cần giả tạo reply.

### `errorChannel` và `recoveryChannel` không giống nhau hoàn toàn

- **Recovery channel** được truyền trực tiếp cho `ErrorMessageSendingRecoverer`; chỉ được gửi khi callback tương ứng chạy.
- **`errorChannel`** là cơ chế lỗi rộng hơn của Spring Integration tại các ranh giới hỗ trợ gửi `ErrorMessage`, đặc biệt quan trọng với consumer bất đồng bộ/polling.
- Nếu advice **không** có callback, exception có thể đi tới error flow theo cơ chế của inbound endpoint/poller hoặc truyền ngược sender nếu xử lý đồng bộ. Không thể suy rằng mọi exception sẽ tự động xuất hiện trên `errorChannel` trong mọi cấu hình.
- Nếu recovery callback **nuốt lỗi sau khi ghi nhận**, nó có thể khiến upstream coi message đã xử lý xong. Đảm bảo recovery channel có subscriber, persistence/reliability đúng nhu cầu và trạng thái thành công được định nghĩa minh bạch.

## 8. Stateless retry và stateful retry

### 8.1. Stateless: thao tác được lặp ngay tại handler

Đây là chế độ khi không cấu hình state key. Một message vào endpoint, advice chạy handler nhiều lần theo policy trong **cùng một lượt xử lý**. Nếu có delay, thread đang xử lý có thể chờ giữa các lần.

Ưu điểm: đơn giản, dễ kiểm thử, không phụ thuộc broker redelivery, phù hợp thao tác nhanh/idempotent.

Giới hạn: giữ worker thread trong thời gian retry/backoff; nếu handler dùng blocking I/O và có nhiều message lỗi, dễ nghẽn queue, thiếu thread, tăng latency toàn hệ thống.

### 8.2. Stateful: yêu cầu nguồn gửi lại message

Stateful retry phù hợp khi nguồn bên ngoài (JMS/AMQP/Kafka adapter hay broker theo cấu hình) có cơ chế redelivery. Khi handler lỗi, advice duy trì retry state theo một khóa ổn định và **ném exception ra ngoài** để nguồn có thể rollback/nack/requeue. Lần nhận lại cùng logical message sẽ tiếp tục vòng retry. Trong Spring Integration 7.x có thể chuyển chế độ bằng:

~~~java
RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();

advice.setStateKeyFunction(message -> {
    Object eventId = message.getHeaders().get("eventId");
    if (eventId == null) {
        throw new IllegalArgumentException("Missing stable eventId");
    }
    return eventId;
});

// Tùy chọn của stateful retry:
advice.setStateCacheSize(1000);
advice.setNewMessagePredicate(message -> false);
~~~

Đây là **cấu hình minh họa**, không ghép vào demo `DirectChannel` ở mục 5. `stateKeyFunction` dùng `eventId` từ nguồn dữ liệu; không nên dựa vào `MessageHeaders.ID` nếu mỗi lần broker redeliver tạo ra message mới có ID khác. Trong production, cần broker/client thực sự gửi lại message khi exception được propagate.

| Khía cạnh | Stateless | Stateful |
| --- | --- | --- |
| Ai kích hoạt lần thử tiếp? | Retry advice trong một invocation | Nguồn/broker gửi lại; advice nhận diện retry state |
| Cần khóa nhận dạng ổn định? | Không bắt buộc | Có |
| Chờ giữa các lần | Có thể giữ thread chờ xuyên suốt | Không giữ thread xuyên suốt nhiều lần redelivery; mỗi lần đến vẫn có thể chờ theo backoff |
| Có cần redelivery/rollback? | Không | Có, hoặc cơ chế resubmit tương đương |
| Trạng thái qua restart | Không có retry state ngoài invocation | Cache mặc định trong bộ nhớ; **không tự bền vững** qua restart |
| Rủi ro chính | Thread exhaustion, lặp side effect trong một call | Chìa khóa không ổn định, cache eviction, broker retry chồng tầng |

Trong Spring Integration 7.x, `stateCacheSize` giới hạn số state còn lưu (mặc định 100). `newMessagePredicate` quyết định lúc nào coi một message cùng khóa là chu kỳ mới. Nếu cache bị đẩy ra, nhiều instance giữ cache riêng hoặc app restart, retry state có thể mất. Vì thế, không dùng cache của advice làm nguồn sự thật cho số lần xử lý xuyên cluster.

**Cần phân biệt số lần:** broker có thể có retry policy riêng, advice có retry policy riêng và application có logic retry riêng. Nếu cả ba đều lặp 3 lần, số lần gọi tác vụ thực tế có thể lớn hơn kỳ vọng. Vẽ ranh giới retry và đo trước khi bật production.

## 9. Transaction và thứ tự advice: một quyết định làm thay đổi semantics

Request-handler advice có thể phối hợp với transaction advice. Advice chain áp dụng theo kiểu bao lồng nhau: phần tử **đầu tiên là vòng ngoài cùng**, phần tử cuối gần handler nhất.

~~~text
Chain A: [retryAdvice, transactionAdvice]
  retry {
      transaction { handler attempt #1 }
      transaction { handler attempt #2 }
      transaction { handler attempt #3 }
  }

Chain B: [transactionAdvice, retryAdvice]
  transaction {
      retry {
          handler attempt #1
          handler attempt #2
          handler attempt #3
      }
      recoveryCallback (nếu nằm trong transaction scope)
  }
~~~

Với **Chain A**, khi các transaction được tạo mới phù hợp, mỗi lần retry có thể diễn ra trong transaction riêng. Với **Chain B**, mọi lần thử có thể dùng cùng transaction và trạng thái rollback-only có thể tồn tại đến khi kết thúc. Không có chain nào đúng tuyệt đối; phải dựa vào tính nguyên tử của thao tác.

Cần xét thêm những ngữ cảnh sau:

- Transaction đã được mở từ poller/inbound adapter hoặc một method gọi ngoài advice: advice transaction bên trong có thể **join** transaction đang tồn tại tùy propagation. Chỉ sắp lại thứ tự chưa chắc tạo transaction mới.
- `DirectChannel` giữ thread đồng bộ, nhưng qua `ExecutorChannel` hoặc polling consumer, ngữ cảnh transaction **không tự truyền** sang thread khác.
- Recovery ghi DLQ/database cũng cần transaction/reliability phù hợp. Nếu transaction dùng cho việc nhận message bị rollback sau khi đã ghi nhận recovery, có thể phát sinh duplicate hoặc mất đồng bộ trạng thái.
- Khi handler có side effect đã commit trước lỗi (ví dụ API bên ngoài đã nhận lệnh nhưng response timeout), rollback database không hoàn tác được request bên ngoài.

**Thiết kế nên ưu tiên idempotency:** sử dụng `eventId`/`orderId` làm idempotency key, unique constraint/inbox table/deduplication store khi phù hợp. Cấu hình retry chỉ quyết định *lúc nào thử lại*; không thể đảm bảo tác vụ ngoài đúng một lần.

## 10. Threading, poller, executor và khả năng chịu tải

| Kiểu luồng | Retry tác động lên thread nào? | Điểm cần theo dõi |
| --- | --- | --- |
| `DirectChannel` + handler đồng bộ | Thường chính thread gọi `send()` | Latency của producer, timeout, exception lan về caller |
| `ExecutorChannel` trước endpoint | Worker thread từ executor | Queue backlog, pool size, tỷ lệ task bị từ chối, retry trong thread |
| `QueueChannel` + polling consumer | Thread poller/consumer | Batch size, polling interval, throughput, transaction/ack semantics |
| Inbound broker listener | Thread của container/listener hoặc thread được handoff | Broker redelivery, ack/nack, consumer concurrency |
| Handler dùng async/reactive contract | Tùy implementation/adapter; có thể qua thread khác | Advice có nhìn thấy lỗi trước khi handler trả kết quả hay không |

**Không giả định** rằng mọi lỗi được phát sinh sau khi handler trả một `Future`/publisher đều nằm trong phạm vi retry advice đồng bộ. Nếu tác vụ bất đồng bộ báo lỗi ở thời điểm khác, cần sử dụng retry/operator tương thích với abstraction đó hoặc thiết kế error flow riêng.

Với stateless retry, một ước lượng đơn giản về chi phí mỗi message:

~~~text
thời gian giữ worker ≈ tổng thời gian các attempt
                       + tổng các khoảng backoff
                       + overhead dispatch / recovery
~~~

Ví dụ handler timeout sau 2 giây, policy có một lần đầu và hai retry; chưa tính backoff, một message lỗi có thể chiếm worker **khoảng 6 giây**. Nếu có 100 message cùng lỗi, pool nhỏ dễ cạn worker và queue tăng nhanh. Vì vậy:

- Đặt timeout của từng I/O thấp hơn budget tổng thời gian; giới hạn số lần retry và delay.
- Áp dụng jitter cho trường hợp nhiều consumer cùng phục hồi từ một đợt lỗi.
- Dùng circuit breaker/rate limiter khi nguồn ngoài chậm hoặc quá tải, và bảo đảm thứ tự advice có chủ đích.
- Dùng retry stateful/redelivery hoặc giải pháp có khả năng chờ không giữ worker nếu bài toán yêu cầu delay dài và throughput cao.
- Theo dõi `active threads`, `queue depth`, latency p95/p99, tỷ lệ retry, số lỗi cuối và tốc độ recovery.

## 11. Chọn lỗi được retry và chống lặp side effect

| Tình huống | Có nên retry? | Ghi chú |
| --- | --- | --- |
| HTTP 503/429, connection reset, network timeout | Có thể | Exponential backoff, rate limit, deadline tổng, idempotency key |
| Lỗi deadlock/optimistic lock có thể giải quyết | Có thể | Phụ thuộc transaction boundary và nghiệp vụ |
| Input sai schema, thiếu trường bắt buộc | Thường không | Đưa sang validation/error flow |
| Authentication/authorization bị từ chối ổn định | Thường không | Cần sửa cấu hình hoặc token; retry vô hạn gây tải và log rác |
| HTTP 409 do xung đột nghiệp vụ vĩnh viễn | Tùy contract | Phân biệt xung đột tạm thời hay trạng thái cuối |
| Thao tác đã thành công phía ngoài nhưng response timeout | Rất thận trọng | Có thể gửi trùng; cần idempotency hoặc truy vấn trạng thái trước khi retry |

Đối với handler gọi dịch vụ ngoài, áp dụng phương án phòng trùng thực tế:

1. Cấp `operationId` ổn định cho cùng logical command.
2. Gửi `operationId` qua header hoặc body theo contract đích.
3. Hệ thống nhận lưu kết quả/dedup trong khoảng thời gian thích hợp.
4. Sau timeout, nếu có API tra cứu trạng thái, xác nhận trước khi gửi lại.
5. Tách thao tác không idempotent khỏi đoạn retry nếu có thể, hoặc dùng outbox/inbox pattern.

Lưu ý đặc biệt với router/filter: khi lời gọi trong scope advice gửi đồng bộ sang channel khác, lỗi downstream đôi khi đi lên cùng stack; song phạm vi chính xác phụ thuộc adapter và `handleRequestMessage`. Phải kiểm thử bằng lỗi giả lập ở **từng vị trí**, không dựa trên suy đoán rằng mọi nhánh đều được retry.

## 12. Quan sát và chẩn đoán runtime

Khi điều tra một message bị xử lý lặp hoặc biến mất, hỏi theo thứ tự:

1. **Điểm retry:** advice được gắn vào endpoint nào? Có nhầm `adviceChain` của handler với poller advice không? Handler bean có được tạo và lifecycle đang running?
2. **Kiểu exception:** exception đi ra khỏi handler là gì, có được bọc bởi `MessagingException` không, policy có nhận diện đúng loại lỗi?
3. **Đếm attempt:** thực tế handler được gọi mấy lần cho cùng logical event ID, có broker redelivery ngoài advice không?
4. **Điều kiện dừng:** max retries, timeout, backoff, recoverer và channel recovery đang cấu hình thế nào?
5. **Thread/transaction:** thread tên gì, có transaction đang active không, điểm async boundary ở đâu?
6. **Side effect:** external API/database đã commit một phần trước khi thất bại chưa? Cơ chế dedup có hoạt động không?
7. **Recovery:** `ErrorMessage` có đến recovery channel, có consumer, có lưu được error record trước ack không?

### Triệu chứng và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Handler chỉ chạy một lần dù có advice | Method nuốt exception, policy không retry, sai bean name, advice không gắn vào handler | Đặt counter/log ở đầu handler và xác nhận exception đi ra |
| Thấy số attempt khác dự kiến | Lẫn `maxRetries` với `maxAttempts`, broker tự redeliver, retry nhiều tầng | Xem version và đo tổng invocation theo eventId |
| Recovery không thấy message | Không có `RecoveryCallback`, lỗi chưa chạm callback, recovery channel không có consumer hoặc chính recovery fail | Kiểm tra callback bean, tên channel và stack trace |
| Producer bị treo lâu | Stateless backoff giữ thread, I/O timeout lớn | Đo thread dump, timeout, wait duration và executor saturation |
| Một payment/order bị xử lý hai lần | Handler đã tạo side effect rồi ném lỗi, retry không idempotent | Xem idempotency key, outbox và log phía service đích |
| Test direct flow bắt exception; production không bắt | Production dùng `ExecutorChannel`/poller, lỗi phát sinh thread khác | Cấu hình `errorChannel` và quan sát worker |
| Stateful không tăng retry count qua redelivery | Key thay đổi, state cache bị evict, nhiều instance hoặc restart | Dùng khóa nguồn ổn định, xem cache và broker delivery ID |
| Transaction cứ rollback dù handler sau retry thành công | Transaction đã bị đánh rollback-only từ attempt trước | Kiểm tra propagation và thứ tự advice/transaction |

Có thể tạo metric như `handler.retry.attempt`, `handler.retry.recovered`, `handler.retry.exhausted`, `handler.latency` với tag **endpoint**, **exception class** và **outcome**. Tránh tag trực tiếp orderId/eventId ở hệ thống metrics vì cardinality cao; đưa chúng vào trace/log có kiểm soát. Mọi log nên kèm `traceId`/`correlationId` để kết nối các bước sau khi đổi thread.

## 13. Bài tập thực hành

1. **Xác nhận stateless retry:** chạy code mục 5; đếm chính xác số lần gọi cho `temporary` và `permanent`, quan sát `recoveries` chỉ nhận message lỗi cuối.
2. **Loại lỗi không retry:** tạo exception riêng cho validation và dùng policy `excludes(...)` đúng version. Đảm bảo message bị từ chối nghiệp vụ không tốn ba lần gọi.
3. **Backoff và thread:** thử delay 100/200/400 ms trên luồng đồng bộ, log `Thread.currentThread().getName()` và latency của `send()`; ghi nhận chi phí giữ worker.
4. **Chuyển async:** thay `DirectChannel` ở input bằng `ExecutorChannel` có `TaskExecutor` cấu hình. So sánh nơi bắt exception, thời điểm trả về từ `send()` và cách error/recovery đi qua flow.
5. **Recovery failure:** cho consumer `recoveries` ném exception thử nghiệm, xem sender/transaction/broker phản ứng gì, sau đó khôi phục handler recovery.
6. **Stateful:** với inbound broker có redelivery thật, cấu hình khóa theo `eventId`; thử rollback rồi redeliver và kiểm tra retry state. Đảm bảo không dùng message ID sinh mới cho khóa.
7. **Transaction và idempotency:** dùng một database test có unique key theo `operationId`; thử tạo side effect trước lỗi và xác minh retry không tạo hai bản ghi.

### Checklist thiết kế trước production

- Retry nằm quanh đúng handler và đúng phạm vi, không vô tình chạy lại nhiều endpoint.
- Số lần retry được cấu hình theo API của **phiên bản đang dùng** và có giới hạn.
- Có timeout, backoff (và jitter nếu cần); policy loại trừ lỗi vĩnh viễn.
- Side effect an toàn khi lặp nhờ idempotency/deduplication.
- Recovery có consumer và nơi lưu lỗi bền vững khi contract đòi hỏi.
- Broker ack/redelivery, transaction, poller và executor được kiểm chứng cùng nhau.
- Có metric, log correlation, alert cho retry storm và số message đi vào recovery.

## 14. Tài liệu tham khảo chính thức

- [Spring Integration 7.x — Provided Advice Classes / Retry Advice](https://docs.spring.io/spring-integration/reference/handler-advice/classes.html): stateless/stateful, recovery callback, retry policy và cấu hình.
- [Spring Integration — Advising Endpoints Using Annotations](https://docs.spring.io/spring-integration/reference/handler-advice/advising-with-annotations.html): sử dụng `adviceChain` với endpoint annotation.
- [Spring Integration — Ordering Advices within Advice Chain](https://docs.spring.io/spring-integration/reference/handler-advice/order.html): thứ tự bao lồng giữa retry và transaction.
- [Spring Integration API — RequestHandlerRetryAdvice](https://docs.spring.io/spring-integration/api/org/springframework/integration/handler/advice/RequestHandlerRetryAdvice.html): API, state cache và các setter phiên bản 7.x.
- [Spring Integration API — ErrorMessageSendingRecoverer](https://docs.spring.io/spring-integration/api/org/springframework/integration/handler/advice/ErrorMessageSendingRecoverer.html): phát `ErrorMessage` sau khi retry exhaustion.
- [Spring Framework 7.x — Resilience Features](https://docs.spring.io/spring-framework/reference/core/resilience.html): `RetryPolicy`, `maxRetries`, backoff, exception classification.
- [Spring Integration 6.4 API — RequestHandlerRetryAdvice](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/handler/advice/RequestHandlerRetryAdvice.html): `setRetryTemplate` và stateful API của 6.x.
