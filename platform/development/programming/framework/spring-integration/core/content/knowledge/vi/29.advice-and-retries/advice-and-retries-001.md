# RequestHandlerRetryAdvice

## 1. Mục tiêu và phạm vi

Trong chương **Advice và retry** của module **SPRING_INTEGRATION_CORE**, bài này trình bày cách dùng `RequestHandlerRetryAdvice` để bảo vệ một bước xử lý thông điệp trước lỗi tạm thời. Nội dung nối các thành phần `Message`, `MessageChannel`, endpoint và Java DSL thành một luồng có đường thành công, đường phục hồi và cách kiểm chứng hành vi.

Sau bài học, bạn có thể:

- Gắn retry đúng vào handler cần bảo vệ.
- Phân biệt lần gọi đầu tiên với những lần thử lại.
- Chọn lỗi được retry, thời gian chờ và hành vi khi dừng retry.
- Dùng `ErrorMessageSendingRecoverer` mà không nhầm recovery với kết quả nghiệp vụ thành công.
- Phân biệt stateless retry với stateful retry và broker redelivery.
- Thiết kế idempotency và kiểm thử số lần gọi thực tế.

**Phạm vi phiên bản:** ví dụ chính dùng **Spring Integration 7.x và Spring Framework 7.x**, với Java 17 trở lên. Phần cuối minh họa cấu hình tương ứng cho **Spring Integration 6.x và Spring Retry 2.x**. Từ Spring Integration 7.0, retry chuyển sang API của Spring Framework; các ví dụ dùng `setRetryTemplate(...)` của 6.x cần được chuyển đổi khi nâng cấp. [Nguồn: hướng dẫn chuyển đổi 6.x sang 7.0](https://github.com/spring-projects/spring-integration/wiki/Spring-Integration-6.x-to-7.0-Migration-Guide).

Bài giả định bạn đã biết cấu trúc `Message<?>`, cách khai báo bean channel và một luồng `IntegrationFlow` đơn giản.

## 2. Bài toán: gọi đối tác gặp lỗi tạm thời

Giả sử một ứng dụng tiếp nhận yêu cầu giữ hàng:

~~~text
orderRequests -> chuẩn hóa -> gọi dịch vụ giữ hàng -> orderReplies
~~~

Dịch vụ đối tác đôi khi chưa sẵn sàng. Lần gọi đầu có thể thất bại, nhưng lần tiếp theo sau một khoảng chờ ngắn có thể thành công.

Hai loại lỗi cần được xử lý khác nhau:

| Tình huống | Nhận định trong ví dụ | Hướng xử lý |
| --- | --- | --- |
| Đối tác tạm ngừng nhận yêu cầu, có xác nhận chưa thực hiện thao tác | Có thể phục hồi sau một khoảng chờ | Retry có giới hạn |
| Payload chứa số lượng không hợp lệ | Gửi lại cùng payload không sửa được lỗi | Dừng retry, ghi nhận yêu cầu lỗi |
| Yêu cầu bị từ chối vì quy tắc nghiệp vụ | Cần quyết định nghiệp vụ mới | Trả kết quả từ chối hoặc chuyển nhánh xử lý |
| Timeout sau khi đã gửi yêu cầu giữ hàng | Chưa biết đối tác đã thực hiện hay chưa | Kiểm tra trạng thái hoặc dùng idempotency trước khi gửi lại |
| Dịch vụ đối tác ngừng hoạt động kéo dài | Retry ngắn hạn khó có ích | Cân nhắc circuit breaker, hàng đợi và lịch xử lý lại |

Việc chọn retry cần trả lời đồng thời ba câu hỏi: lỗi có khả năng hết, thao tác có thể được lặp an toàn và ngân sách thời gian còn đủ hay không.

Trong phần thực hành, lỗi `TransientPartnerException` mô phỏng đối tác chưa thực hiện thao tác. Đây là giả định của bài tập; một timeout mạng thực tế không tự mang bảo đảm đó.

## 3. Advice bao quanh phần nào của luồng?

`RequestHandlerRetryAdvice` là một advice dành cho message handler. Với handler sinh reply của Spring Integration, nó bao quanh phần xử lý yêu cầu tại endpoint. Nhờ vậy, ta có thể lặp lại lời gọi đối tác tại một endpoint cụ thể mà không chủ động chạy lại các bước chuẩn hóa trước đó hay xử lý reply phía sau. [Nguồn: Adding Behavior to Endpoints](https://docs.spring.io/spring-integration/reference/handler-advice.html).

~~~mermaid
flowchart LR
    A["Message yêu cầu"] --> B["Chuẩn hóa"]
    B --> C["Endpoint gọi đối tác"]
    C --> D["Xử lý reply"]
    D --> E["Kết quả"]
    subgraph R["Phạm vi request handler advice"]
        C --> F{"Handler thành công?"}
        F -->|"Lỗi được retry, còn lượt"| G["Backoff"]
        G --> C
    end
    F -->|"Dừng sau lỗi"| H["Recovery hoặc ném lỗi"]
~~~

Sơ đồ biểu diễn ranh giới xử lý; một reply thành công mới tiếp tục sang bước xử lý reply.

Ví dụ luồng:

~~~text
transformer -> reserveHandler [retry] -> auditHandler
~~~

- Nếu `reserveHandler` ném lỗi phù hợp policy, chính handler đó được gọi lại.
- Nếu transformer thất bại trước khi tới `reserveHandler`, advice này chưa được thực thi.
- Nếu `auditHandler` thất bại sau khi `reserveHandler` trả reply, không kỳ vọng advice tại `reserveHandler` sẽ retry `auditHandler`.
- Nếu code bên trong `reserveHandler` tự gọi ba dịch vụ liên tiếp, cả ba lời gọi đều nằm trong phần công việc có thể bị lặp.

Điểm cuối quyết định cách chia endpoint. Nên đặt một thao tác cần retry vào một handler có trách nhiệm rõ ràng, nhất là khi các thao tác có tác dụng phụ khác nhau.

Với một `MessageHandler` tùy biến, phạm vi chính xác còn phụ thuộc method được advice chặn và công việc handler tự thực hiện. `AbstractRequestHandlerAdvice` hỗ trợ `handleRequestMessage(...)` của reply-producing handler và `handleMessage(...)` của những message handler khác. [Nguồn: AbstractRequestHandlerAdvice](https://raw.githubusercontent.com/spring-projects/spring-integration/v7.0.0/spring-integration-core/src/main/java/org/springframework/integration/handler/advice/AbstractRequestHandlerAdvice.java).

### Phân biệt các vị trí retry

| Vị trí | Phần công việc có thể bị lặp | Điều cần xác định |
| --- | --- | --- |
| `endpoint.advice(retryAdvice)` | Xử lý yêu cầu tại handler được gắn advice | Handler đã nhỏ và an toàn để lặp chưa? |
| Advice bao quanh poller | Công việc nằm trong callback được poller bao quanh | Những endpoint đồng bộ nào thuộc cùng callback? |
| Retry ở HTTP client hoặc SDK | Lời gọi do client thực hiện | Client đã có retry mặc định chưa? |
| Retry ở tầng dịch vụ | Method hoặc khối code được bảo vệ | Có bị bọc thêm retry ở endpoint không? |
| Redelivery của broker | Message được giao lại vào luồng tiêu thụ | Các bước trước handler có chạy lại không? |

Từ vị trí advice, hãy vẽ lại đường đi thực tế của message trước khi quyết định số lượt retry.

## 4. Cấu trúc một chu kỳ retry trong 7.x

Các khái niệm chính:

| Thành phần | Vai trò |
| --- | --- |
| `RequestHandlerRetryAdvice` | Bao quanh lời gọi handler và điều phối xử lý lại |
| `org.springframework.core.retry.RetryPolicy` | Phân loại exception và cung cấp chiến lược backoff |
| Backoff | Quy định khoảng chờ và thời điểm hết lượt thử lại |
| `org.springframework.integration.core.RecoveryCallback` | Xử lý khi chu kỳ retry kết thúc bằng lỗi |
| `ErrorMessageSendingRecoverer` | Một recovery callback gửi thông điệp lỗi tới channel |
| `org.springframework.core.retry.RetryListener` | Theo dõi các sự kiện của quá trình retry |

Trong 7.x, cấu hình policy qua `setRetryPolicy(...)`. Khi không cung cấp state key, advice chạy theo cơ chế stateless. Cấu hình mặc định của advice cho phép tối đa **ba lần retry sau lần đầu**, không chờ giữa các lần gọi. Nên khai báo policy tường minh thay vì dựa vào mặc định. [Nguồn: RequestHandlerRetryAdvice API](https://docs.spring.io/spring-integration/api/org/springframework/integration/handler/advice/RequestHandlerRetryAdvice.html).

### 4.1. Đếm đúng số lần thực thi

Với policy trong bài:

~~~java
RetryPolicy.builder()
        .maxRetries(2)
        .delay(Duration.ofMillis(100))
        .multiplier(2.0)
        .maxDelay(Duration.ofSeconds(1))
        .build();
~~~

`maxRetries(2)` cho phép hai lần thử lại ngoài lần đầu. Công thức của Spring Framework là:

~~~text
Số lần gọi tối đa = 1 + maxRetries
~~~

Ví dụ trên cho phép tối đa ba lần gọi. `maxRetries(0)` vẫn cho phép thực hiện lần đầu. [Nguồn: RetryPolicy.Builder của Spring Framework 7.0](https://docs.spring.io/spring-framework/docs/7.0.0/javadoc-api/org/springframework/core/retry/RetryPolicy.Builder.html).

Với lỗi tạm thời liên tục và không cấu hình jitter:

| Lần thực thi handler | Vai trò | Khoảng chờ trước lần này |
| --- | --- | --- |
| 1 | Lần đầu | Không |
| 2 | Retry thứ nhất | 100 ms |
| 3 | Retry thứ hai | 200 ms |
| Sau lần 3 thất bại | Recovery hoặc truyền lỗi ra ngoài | Không có lần gọi thứ 4 |

Đây là số lần tối đa. Thành công ở lần thứ hai thì kết thúc ngay; lỗi không thuộc diện retry có thể kết thúc từ lần đầu.

### 4.2. Lỗi phải hiện diện bằng exception

Advice quan sát lỗi phát sinh trong phạm vi lời gọi handler. Nếu handler bắt exception rồi trả `null`, trả chuỗi `"FAILED"` hoặc trả một object chứa trạng thái lỗi, advice không tự diễn giải các giá trị đó là lý do retry.

~~~java
// Cách biểu diễn lỗi dành cho policy của ví dụ:
throw new TransientPartnerException("Đối tác tạm thời chưa sẵn sàng");
~~~

Với HTTP client, cần quyết định rõ mã phản hồi nào được chuyển thành exception tạm thời và mã nào là kết quả nghiệp vụ. Việc nhận HTTP 503 dưới dạng một object bình thường sẽ không tự kích hoạt policy dựa trên exception.

Một `Mono` hoặc `CompletableFuture` được trả về thành công cũng có thể báo lỗi sau khi method đã kết thúc. Ví dụ trong bài dùng xử lý đồng bộ; với xử lý bất đồng bộ hoặc reactive, phải đặt cơ chế retry tại ranh giới thật sự quan sát được lỗi.

## 5. Ví dụ Java DSL đầy đủ

### 5.1. Môi trường và hợp đồng của luồng

Trong ứng dụng đã quản lý dependency bằng Spring Boot/BOM, sử dụng dependency:

~~~xml
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-core</artifactId>
</dependency>
~~~

Chọn bộ phiên bản tương thích với Spring Integration 7.x và Spring Framework 7.x. Dependency ở trên không có version vì giả định project đã quản lý version tập trung. Với ví dụ chính, không cần thêm Spring Retry hay bật `@EnableRetry`: advice được tạo thành bean và gắn trực tiếp vào endpoint.

Luồng thực hành dùng:

- `orderRequests`: `DirectChannel`, xử lý đồng bộ trên thread gửi.
- `orderReplies`: `QueueChannel` chứa kết quả giữ hàng thành công.
- `exhaustedOrders`: `QueueChannel` chứa lỗi sau khi dừng retry.
- `SimulatedPartner`: đối tác giả lập để quan sát số lần gọi.

Hai queue trong bài nằm trong bộ nhớ và được đọc thủ công hoặc trong kiểm thử. Chúng chưa tạo thành hệ thống lưu trữ lỗi bền vững.

### 5.2. Cấu hình và handler

Đặt đoạn sau trong `RetryDemoConfig.java`. Các kiểu dữ liệu và exception được khai báo bên trong cùng lớp để ví dụ tự chứa.

~~~java
import java.time.Duration;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.retry.RetryPolicy;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.advice.ErrorMessageSendingRecoverer;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.messaging.MessageChannel;

@Configuration(proxyBeanMethods = false)
@EnableIntegration
public class RetryDemoConfig {

    @Bean
    public DirectChannel orderRequests() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel orderReplies() {
        return new QueueChannel();
    }

    @Bean
    public QueueChannel exhaustedOrders() {
        return new QueueChannel();
    }

    @Bean
    public SimulatedPartner simulatedPartner() {
        return new SimulatedPartner();
    }

    @Bean
    public RequestHandlerRetryAdvice orderRetryAdvice(
            @Qualifier("exhaustedOrders") MessageChannel recoveryChannel) {

        RetryPolicy policy = RetryPolicy.builder()
                .maxRetries(2)
                .delay(Duration.ofMillis(100))
                .multiplier(2.0)
                .maxDelay(Duration.ofSeconds(1))
                .includes(TransientPartnerException.class)
                .excludes(InvalidOrderException.class)
                .build();

        RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
        advice.setRetryPolicy(policy);
        advice.setRecoveryCallback(
                new ErrorMessageSendingRecoverer(recoveryChannel));
        return advice;
    }

    @Bean
    public IntegrationFlow orderFlow(
            SimulatedPartner partner,
            RequestHandlerRetryAdvice orderRetryAdvice) {

        return IntegrationFlow.from("orderRequests")
                .handle(OrderRequest.class,
                        (request, headers) -> partner.reserve(request),
                        endpoint -> endpoint
                                .id("reserveOrder")
                                .advice(orderRetryAdvice))
                .channel("orderReplies")
                .get();
    }

    public record OrderRequest(
            String orderId,
            int simulatedFailuresBeforeSuccess) {
    }

    public record OrderReceipt(String orderId, String status) {
    }

    public static class TransientPartnerException extends RuntimeException {
        public TransientPartnerException(String message) {
            super(message);
        }
    }

    public static class InvalidOrderException extends RuntimeException {
        public InvalidOrderException(String message) {
            super(message);
        }
    }

    public static class SimulatedPartner {

        private final ConcurrentHashMap<String, AtomicInteger> attempts =
                new ConcurrentHashMap<>();

        public OrderReceipt reserve(OrderRequest request) {
            if (request.orderId() == null || request.orderId().isBlank()) {
                throw new InvalidOrderException("orderId phải có giá trị");
            }

            int attempt = attempts
                    .computeIfAbsent(request.orderId(), key -> new AtomicInteger())
                    .incrementAndGet();

            if (request.simulatedFailuresBeforeSuccess() < 0) {
                throw new InvalidOrderException(
                        "Số lần lỗi giả lập không được âm");
            }

            if (attempt <= request.simulatedFailuresBeforeSuccess()) {
                throw new TransientPartnerException(
                        "Đối tác chưa sẵn sàng, lần gọi " + attempt);
            }

            return new OrderReceipt(request.orderId(), "RESERVED");
        }

        public int attemptsFor(String orderId) {
            AtomicInteger count = attempts.get(orderId);
            return count == null ? 0 : count.get();
        }
    }
}
~~~

Policy chỉ chọn `TransientPartnerException` để retry. Việc loại trừ `InvalidOrderException` làm ý định xử lý lỗi nghiệp vụ rõ ràng hơn. Trong API 7.x, phân loại exception cũng xét các cause lồng bên trong, hữu ích khi handler bọc lỗi gốc trong một exception messaging. [Nguồn: RetryPolicy](https://raw.githubusercontent.com/spring-projects/spring-framework/v7.0.0/spring-core/src/main/java/org/springframework/core/retry/RetryPolicy.java).

Giả lập sử dụng bộ đếm riêng theo `orderId`. Mỗi kịch bản nên dùng mã đơn hàng khác nhau hoặc application context mới để số lần gọi trước đó không ảnh hưởng kết quả. Bộ đếm này chỉ phục vụ bài tập, không phải cơ chế chống giữ hàng trùng.

### 5.3. Gửi một yêu cầu

Đoạn sau được đặt trong một method của chương trình chạy thử:

~~~java
try (var context =
        new org.springframework.context.annotation.AnnotationConfigApplicationContext(
                RetryDemoConfig.class)) {

    var input = context.getBean("orderRequests",
            org.springframework.messaging.MessageChannel.class);
    var replies = context.getBean("orderReplies",
            org.springframework.integration.channel.QueueChannel.class);

    var request = new RetryDemoConfig.OrderRequest("ORD-100", 2);

    input.send(org.springframework.messaging.support.MessageBuilder
            .withPayload(request)
            .setHeader("businessRequestId", "REQ-100")
            .build());

    var reply = replies.receive(1_000);
    System.out.println(reply == null ? "Không có reply" : reply.getPayload());
}
~~~

`ORD-100` được cấu hình lỗi hai lần rồi thành công. Handler được gọi ba lần, tạo đúng một `OrderReceipt` vào `orderReplies`.

Nếu đổi số lỗi giả lập thành `99`, cả ba lần gọi đều thất bại. Recovery gửi một `ErrorMessage` vào `exhaustedOrders` và luồng không sinh `OrderReceipt`.

Ở cấu hình đồng bộ này, backoff xảy ra bên trong `input.send(...)`. Thời hạn `replies.receive(1_000)` bắt đầu khi lời gọi `receive` được thực hiện; nó không giới hạn thời gian `send` đã tiêu tốn.

## 6. Recovery và đường lỗi

### 6.1. Không cấu hình recovery callback

Khi handler tiếp tục thất bại tới lúc policy dừng và không có callback phục hồi, lời gọi advice kết thúc bằng exception.

Với `DirectChannel` trong ví dụ, sender ở cùng call stack nên có thể nhận exception từ `send(...)`. Việc tự khai báo bean tên `errorChannel` không biến mọi lỗi đồng bộ thành một message trên channel đó. Đối với gateway hoặc consumer bất đồng bộ, đường truyền lỗi phải xét theo cấu hình của thành phần tương ứng. [Nguồn: Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

### 6.2. Cấu hình ErrorMessageSendingRecoverer

`ErrorMessageSendingRecoverer` đưa throwable cuối chu kỳ vào một `ErrorMessage` gửi tới recovery channel. Constructor nhận channel giúp chỉ định rõ nơi tiếp nhận lỗi của endpoint. [Nguồn: ErrorMessageSendingRecoverer API](https://docs.spring.io/spring-integration/api/org/springframework/integration/handler/advice/ErrorMessageSendingRecoverer.html).

Trong cấu hình đang dùng:

~~~text
Handler thành công -> OrderReceipt -> orderReplies
Handler dừng bằng lỗi -> ErrorMessage -> exhaustedOrders
~~~

Khi gửi lỗi thành công, recoverer trả `null`. Vì vậy, đường recovery không tự sinh một reply nghiệp vụ thay thế. [Nguồn: mã nguồn ErrorMessageSendingRecoverer 7.0](https://raw.githubusercontent.com/spring-projects/spring-integration/v7.0.0/spring-integration-core/src/main/java/org/springframework/integration/handler/advice/ErrorMessageSendingRecoverer.java).

Cần phân biệt:

- Handler hoàn tất nghiệp vụ.
- Hệ thống đã tiếp nhận thông tin thất bại vào recovery channel.
- Hệ thống đã lưu thông tin thất bại bền vững để xử lý sau.

Ba sự kiện này có ý nghĩa khác nhau. `send(...)` không ném lỗi sau recovery không chứng minh đối tác đã giữ hàng thành công.

Nếu endpoint bắt buộc phải trả reply, hoặc lời gọi đi qua gateway yêu cầu phản hồi, hãy thiết kế rõ hợp đồng khi recovery trả `null`. Có thể cần một kết quả thất bại có kiểu cụ thể, một exception được truyền ra ngoài hoặc cơ chế bất đồng bộ có mã tra cứu. Không dùng sự vắng mặt của reply như một kết quả thành công ngầm định.

### 6.3. Recovery không phải một lượt retry riêng

Trong nhánh stateless 7.x, việc dừng vì exception không được retry cũng có thể dẫn tới callback recovery ngay sau lần gọi đầu. Vì vậy, tên `exhaustedOrders` trong ví dụ có nghĩa là nơi nhận lỗi khi chu kỳ dừng; không bảo đảm message nào vào đây cũng đã được thử đủ ba lần.

Nếu cần `InvalidOrderException` trả về người gọi, còn lỗi đối tác mới chuyển sang hàng đợi phục hồi, hãy thiết kế nhánh validation trước endpoint hoặc viết recovery callback phân biệt hai nhóm.

Khi chính callback recovery gặp lỗi, chẳng hạn không gửi được message lỗi, lỗi recovery có thể lan ra caller. Callback không tự được retry bởi cùng vòng retry của handler. Trong mã nguồn 7.0, callback được gọi sau khi execution retry đã kết thúc bằng `RetryException`. [Nguồn: mã nguồn RequestHandlerRetryAdvice](https://raw.githubusercontent.com/spring-projects/spring-integration/v7.0.0/spring-integration-core/src/main/java/org/springframework/integration/handler/advice/RequestHandlerRetryAdvice.java).

### 6.4. Trả fallback có kiểu

`RecoveryCallback` của Spring Integration 7.x nhận hai tham số `context` và `cause`; kết quả trả về có thể thay thế kết quả xử lý thất bại. [Nguồn: RecoveryCallback](https://docs.spring.io/spring-integration/docs/7.0.0/api/org/springframework/integration/core/RecoveryCallback.html).

Ví dụ dưới đây là **phương án thay thế** cho recoverer gửi lỗi:

~~~java
public record ReservationOutcome(String status) {
}

// Trong method tạo advice:
advice.setRecoveryCallback((context, cause) ->
        new ReservationOutcome("PENDING_REVIEW"));
~~~

Trước khi dùng, cần đổi hợp đồng output để các bước sau hiểu được `ReservationOutcome`, hoặc dùng một kiểu kết quả chung cho cả thành công lẫn thất bại. Không thay thế kết quả giữ hàng bằng `"RESERVED"` nếu chưa biết thao tác thành công.

Nếu vừa gửi lỗi vừa trả fallback, hãy triển khai hai hành động đó tường minh trong callback và quyết định hệ thống phải phản ứng thế nào nếu việc gửi lỗi thất bại.

## 7. Chọn policy và backoff theo ngân sách thời gian

### 7.1. Phân loại lỗi sát với lời gọi thực tế

Nên xây dựng exception ở lớp client theo ý nghĩa xử lý:

~~~text
Lỗi mà thử lại có thể có ích -> TransientPartnerException
Lỗi dữ liệu hoặc quy tắc không đổi -> InvalidOrderException/kết quả từ chối
Lỗi không rõ đã có tác dụng phụ chưa -> quyết định dựa trên idempotency
~~~

Hạn chế bắt mọi `RuntimeException` rồi đổi thành lỗi tạm thời. Cách đó có thể khiến lỗi lập trình, sai cấu hình hoặc dữ liệu không hợp lệ bị gửi lại nhiều lần.

Với một API cụ thể, việc retry HTTP 429 hoặc 503 nên căn cứ hợp đồng dịch vụ, giới hạn lưu lượng và tín hiệu như `Retry-After`. Policy exception cố định trong bài không tự phân tích header HTTP để chọn lịch chờ.

### 7.2. Tính thời gian xấu nhất

Giả sử client có giới hạn thời gian cho mỗi lần gọi là `t`, số lần gọi tối đa là `A` và các khoảng backoff là `b1...b(A-1)`. Ước lượng lập kế hoạch:

~~~text
T ≈ A × t + tổng backoff + chi phí xử lý khác
~~~

Với ba lần gọi, mỗi lần có giới hạn 800 ms và backoff 100 ms, 200 ms:

~~~text
T ≈ 3 × 800 + 100 + 200 = 2.700 ms
~~~

Con số này chưa tính thời gian chờ connection pool, lịch thread, serialize, truyền reply và recovery. Đây là ước lượng dựa trên giả định mọi phần chờ trong một lần gọi đã được tính vào 800 ms.

Nếu caller có deadline một giây thì cấu hình trên không phù hợp. Giảm số lượt, rút ngắn timeout mỗi lượt hoặc chuyển sang xử lý bất đồng bộ có hợp đồng rõ ràng.

Retry không thay thế connect timeout, read timeout hay giới hạn thời gian của client. Một lời gọi bị treo sẽ giữ vòng retry tại lời gọi đó.

### 7.3. Tác động tới thread và tải hệ thống

Với stateless retry đồng bộ, thread xử lý chờ trong backoff. Một pool 20 worker đang đồng thời chờ đối tác có thể không còn worker tiếp nhận message khác.

Để đánh giá ảnh hưởng, hãy tính cả:

- Số message đang xử lý đồng thời.
- Tổng thời gian một message có thể chiếm worker.
- Số connection và giới hạn phía đối tác.
- Queue depth khi tốc độ tiếp nhận cao hơn tốc độ xử lý.

Exponential backoff giảm tần suất gọi lặp. Jitter giúp các instance tránh cùng thức dậy vào một nhịp. Ví dụ có thể bổ sung `.jitter(Duration.ofMillis(30))` vào builder; khi đó không dùng bảng chờ 100 ms, 200 ms như giá trị thời gian chính xác. Các giới hạn jitter và delay tuân theo API builder của phiên bản sử dụng. [Nguồn: RetryPolicy.Builder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/retry/RetryPolicy.Builder.html).

Nếu cần chờ hàng phút hoặc hàng giờ, hãy cân nhắc broker delay, hàng đợi xử lý lại hoặc scheduler phù hợp. Giữ worker chờ lâu thường làm giảm năng lực xử lý của luồng.

### 7.4. Tránh nhân số lần gọi ở nhiều tầng

Ví dụ thiết kế:

~~~text
Endpoint: tối đa 3 lần gọi handler
HTTP client: tối đa 3 lần gọi HTTP cho mỗi lần handler gọi client
Broker: tối đa 5 lần giao message trong toàn bộ vòng đời
~~~

Nếu cả ba cơ chế đều thực hiện đủ lượt và các lỗi tiếp tục được truyền ra để broker giao lại, số lời gọi HTTP có thể lên tới:

~~~text
3 × 3 × 5 = 45
~~~

Đây là phép tính theo các giả định đã nêu, không phải mặc định của Spring. Nếu recovery nuốt lỗi và listener xác nhận message, broker có thể không giao lại nữa.

Hãy giao trách nhiệm retry cho từng tầng và tính tổng số lần gọi tới hệ thống đích.

## 8. Stateless retry và stateful retry

### 8.1. Stateless: toàn bộ chu kỳ trong một lần vào handler

Ví dụ Java DSL phía trên dùng stateless:

~~~text
Một lần gửi message
  -> gọi handler lần 1: lỗi
  -> chờ
  -> gọi handler lần 2: lỗi
  -> chờ
  -> gọi handler lần 3: thành công hoặc recovery
~~~

Không cần caller gửi lại message để có lần retry thứ hai. Vì thế, đếm một lần gọi `send(...)` không đủ để suy ra chỉ có một lần tương tác với đối tác.

### 8.2. Stateful: giữ trạng thái qua các lần giao lại

Với stateful retry, exception được đưa về caller trong quá trình xử lý, còn trạng thái retry được giữ để nhận diện lần giao lại cùng thao tác. Nguồn message, chẳng hạn broker và listener được cấu hình phù hợp, phải có khả năng đưa message quay lại.

Trong 7.x, cung cấp `stateKeyFunction` để chuyển sang stateful. `newMessagePredicate` cho phép bắt đầu chu kỳ mới, còn `stateCacheSize` giới hạn cache trạng thái; mặc định cache có 100 mục. [Nguồn: Retry Advice](https://docs.spring.io/spring-integration/reference/handler-advice/classes.html).

Ví dụ bean stateful sau **không được dùng đồng thời thay cho ví dụ stateless nếu chưa có cơ chế redelivery**:

~~~java
@Bean
public RequestHandlerRetryAdvice statefulOrderRetryAdvice() {
    RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();

    advice.setRetryPolicy(RetryPolicy.builder()
            .maxRetries(2)
            .delay(Duration.ofMillis(100))
            .includes(RetryDemoConfig.TransientPartnerException.class)
            .build());

    advice.setStateKeyFunction(message -> {
        String key = message.getHeaders()
                .get("businessRequestId", String.class);

        if (key == null || key.isBlank()) {
            throw new IllegalArgumentException(
                    "Stateful retry cần businessRequestId ổn định");
        }
        return key;
    });

    advice.setStateCacheSize(1_000);
    return advice;
}
~~~

Đoạn này chỉ cấu hình advice; nó không tạo consumer broker, transaction, acknowledgment hay lịch giao lại message.

Ví dụ vòng đời:

~~~text
Giao lần 1, key=REQ-200 -> handler lỗi -> caller nhận lỗi
Nguồn message quyết định giao lại
Giao lần 2, key=REQ-200 -> tiếp tục trạng thái -> handler được thử lại
~~~

Không dùng `MessageHeaders.ID` làm khóa mặc định khi message có thể được dựng mới ở lần giao lại. Khóa cần ổn định theo **cùng thao tác nghiệp vụ**, có thể gồm tenant, loại thao tác và mã yêu cầu để tránh trộn hai công việc khác nhau.

Stateful không đồng nghĩa mọi backoff đều không chặn thread. Trong triển khai 7.0, lần giao lại có thể chờ theo backoff trước khi gọi handler; nguồn message vẫn chịu trách nhiệm redelivery. Cache trạng thái cũng nằm trong instance advice, không tự trở thành bộ nhớ chia sẻ bền vững giữa các node. [Nguồn: triển khai stateful retry 7.0](https://raw.githubusercontent.com/spring-projects/spring-integration/v7.0.0/spring-integration-core/src/main/java/org/springframework/integration/handler/advice/RequestHandlerRetryAdvice.java).

Nếu process khởi động lại hoặc một mục cache bị loại do đầy, không coi bộ đếm này là giới hạn toàn cục vĩnh viễn. Với yêu cầu như vậy, cần cơ chế bền vững ở broker hoặc kho dữ liệu phù hợp.

### 8.3. So sánh khi lựa chọn

| Tiêu chí | Stateless | Stateful |
| --- | --- | --- |
| Ai đưa message vào lần thử tiếp theo? | Advice gọi lại nội bộ | Caller hoặc nguồn message giao lại |
| Cần khóa nhận diện ổn định? | Không cần cho trạng thái retry nội bộ | Có |
| Có tự tạo broker redelivery? | Không | Không |
| Thread | Có thể chờ cả chu kỳ | Có thể chờ tại lần xử lý được giao lại |
| Mối quan hệ với transaction | Cần kiểm tra phạm vi transaction đang bao quanh | Thường phải phối hợp rollback/redelivery của nguồn |
| Phù hợp để bắt đầu học | Lời gọi đồng bộ, ngắn, lỗi tạm thời | Luồng broker có thiết kế giao lại rõ ràng |

## 9. Idempotency, transaction và thứ tự advice

### 9.1. Retry có thể lặp tác dụng phụ

Tình huống giả định:

1. Đối tác giữ hàng thành công.
2. Kết nối đứt trước khi ứng dụng nhận phản hồi.
3. Client báo timeout.
4. Handler gửi lại yêu cầu giữ hàng.

Nếu mỗi lời gọi tạo một lần giữ hàng mới thì retry có thể giữ hàng hai lần.

Một thiết kế có thể dùng `businessRequestId` làm idempotency key của cùng thao tác. Phía thực hiện giữ hàng cần lưu khóa và kết quả đủ bền vững, bảo đảm kiểm tra khóa và cập nhật nghiệp vụ theo cách nguyên tử phù hợp.

Chỉ thêm header vào `Message` chưa tạo ra idempotency. Client phải truyền khóa tới đối tác, và đối tác phải xử lý khóa theo hợp đồng đã thống nhất.

Cũng không thể coi stateful retry cache là kho chống trùng: cache phục vụ trạng thái thử lại và có vòng đời khác với kết quả nghiệp vụ.

### 9.2. Retry không tự tạo transaction

Gắn `RequestHandlerRetryAdvice` không mặc định mở một transaction mới cho từng lượt.

Nếu một transaction bao quanh cả chu kỳ retry, lần đầu có thể đã khiến transaction bị đánh dấu rollback-only. Lần gọi handler sau có vẻ thành công vẫn có thể thất bại khi commit.

Hai hình dạng cần phân biệt:

~~~text
Transaction
  -> Retry
      -> Handler
~~~

~~~text
Retry
  -> Transaction
      -> Handler
~~~

Hình thứ hai có thể cho phép transaction mới ở mỗi lượt nếu advice, proxy và propagation thực tế được cấu hình để làm như vậy. Thứ tự nhìn trên sơ đồ chưa đủ; cần kiểm tra cả transaction đang có ở bên ngoài.

Rollback cơ sở dữ liệu cục bộ cũng không hoàn tác một lời gọi HTTP đã thành công ở đối tác. Luồng có nhiều hệ thống thường cần idempotency, outbox hoặc cơ chế bù trừ phù hợp.

### 9.3. Advice có thứ tự lồng nhau

Trong Java DSL, `advice(a, b)` áp dụng advice theo thứ tự lồng nhau. [Nguồn: ConsumerEndpointSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/ConsumerEndpointSpec.html).

Khi phối hợp retry với advice đo thời gian hoặc transaction, hãy viết rõ cách lồng mong muốn:

~~~text
metrics -> retry -> handler
~~~

Có thể dùng để quan sát thời gian của toàn chu kỳ.

~~~text
retry -> metrics -> handler
~~~

Có thể dùng để quan sát từng lời gọi nằm bên trong vòng retry, tùy cách advice đo đạc được triển khai.

Cũng cần kiểm tra advice nào bắt và xử lý exception. Nếu một advice bên trong chuyển lỗi thành kết quả bình thường, advice retry bên ngoài sẽ không còn thấy lỗi đó.

## 10. Kiểm thử hành vi bằng số lần gọi và đường ra

Không chỉ kiểm tra ứng dụng khởi động được. Cần quan sát đồng thời số lần handler được gọi, số reply và số thông điệp lỗi.

### 10.1. Ma trận kiểm thử

Với cấu hình stateless của mục 5:

| Dữ liệu giả lập | Số lần gọi dự kiến | `orderReplies` | `exhaustedOrders` |
| --- | --- | --- | --- |
| Không lỗi | 1 | 1 receipt | 0 |
| Lỗi tạm thời hai lần rồi thành công | 3 | 1 receipt | 0 |
| Lỗi tạm thời liên tục | 3 | 0 | 1 ErrorMessage |
| `simulatedFailuresBeforeSuccess = -1`, orderId hợp lệ | 1 | 0 | 1 ErrorMessage |

Dòng cuối kiểm tra lỗi bị loại khỏi retry, nhưng vẫn đi vào recovery của nhánh stateless đang cấu hình.

### 10.2. Ví dụ JUnit 5

Đặt test trong cùng package với `RetryDemoConfig` và bổ sung JUnit Jupiter qua bộ dependency test của project. Mỗi test mở context mới để cô lập bộ đếm và queue.

~~~java
import org.junit.jupiter.api.Test;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class RetryDemoConfigTest {

    @Test
    void retriesTwiceThenProducesOneReceipt() {
        try (var context =
                new AnnotationConfigApplicationContext(RetryDemoConfig.class)) {

            var request = new RetryDemoConfig.OrderRequest("ORD-OK", 2);
            send(context, request);

            var partner = context.getBean(
                    RetryDemoConfig.SimulatedPartner.class);
            var replies = context.getBean("orderReplies", QueueChannel.class);
            var errors = context.getBean("exhaustedOrders", QueueChannel.class);

            Message<?> reply = replies.receive(0);

            assertEquals(3, partner.attemptsFor("ORD-OK"));
            assertNotNull(reply);
            assertEquals(
                    new RetryDemoConfig.OrderReceipt("ORD-OK", "RESERVED"),
                    reply.getPayload());
            assertNull(replies.receive(0));
            assertNull(errors.receive(0));
        }
    }

    @Test
    void publishesOneErrorAfterThreeFailedCalls() {
        try (var context =
                new AnnotationConfigApplicationContext(RetryDemoConfig.class)) {

            var request = new RetryDemoConfig.OrderRequest("ORD-FAIL", 99);
            assertDoesNotThrow(() -> send(context, request));

            var partner = context.getBean(
                    RetryDemoConfig.SimulatedPartner.class);
            var replies = context.getBean("orderReplies", QueueChannel.class);
            var errors = context.getBean("exhaustedOrders", QueueChannel.class);

            ErrorMessage error =
                    assertInstanceOf(ErrorMessage.class, errors.receive(0));

            assertEquals(3, partner.attemptsFor("ORD-FAIL"));
            assertNull(replies.receive(0));
            assertTrue(hasCause(error.getPayload(),
                    RetryDemoConfig.TransientPartnerException.class));
            assertNotNull(error.getOriginalMessage());
            assertEquals(request, error.getOriginalMessage().getPayload());
            assertNull(errors.receive(0));
        }
    }

    @Test
    void doesNotRetryInvalidOrder() {
        try (var context =
                new AnnotationConfigApplicationContext(RetryDemoConfig.class)) {

            send(context,
                    new RetryDemoConfig.OrderRequest("ORD-INVALID", -1));

            var partner = context.getBean(
                    RetryDemoConfig.SimulatedPartner.class);
            var errors = context.getBean("exhaustedOrders", QueueChannel.class);
            var replies = context.getBean("orderReplies", QueueChannel.class);

            ErrorMessage error =
                    assertInstanceOf(ErrorMessage.class, errors.receive(0));

            assertEquals(1, partner.attemptsFor("ORD-INVALID"));
            assertTrue(hasCause(error.getPayload(),
                    RetryDemoConfig.InvalidOrderException.class));
            assertNull(replies.receive(0));
            assertNull(errors.receive(0));
        }
    }

    private static void send(
            AnnotationConfigApplicationContext context,
            RetryDemoConfig.OrderRequest request) {

        MessageChannel input =
                context.getBean("orderRequests", MessageChannel.class);

        assertTrue(input.send(MessageBuilder.withPayload(request)
                .setHeader("businessRequestId", request.orderId())
                .build()));
    }

    private static boolean hasCause(
            Throwable failure,
            Class<? extends Throwable> expectedType) {

        Throwable current = failure;
        while (current != null) {
            if (expectedType.isInstance(current)) {
                return true;
            }
            Throwable next = current.getCause();
            if (next == current) {
                break;
            }
            current = next;
        }
        return false;
    }
}
~~~

Ở ví dụ này, `DirectChannel` hoàn tất xử lý trước khi `send` trả về nên test có thể đọc queue ngay bằng `receive(0)`. Nếu đổi sang `ExecutorChannel` hoặc consumer bất đồng bộ, test phải chờ có giới hạn cho kết quả tương ứng.

Đường lỗi có thể chứa nhiều lớp wrapper. Test dò chuỗi cause thay vì ép payload lỗi phải trực tiếp là exception nghiệp vụ. `RetryTemplate` 7.0 biểu diễn lần thất bại cuối trong cause của `RetryException` và giữ các lỗi trước đó trong suppressed exceptions. [Nguồn: RetryTemplate 7.0](https://raw.githubusercontent.com/spring-projects/spring-framework/v7.0.0/spring-core/src/main/java/org/springframework/core/retry/RetryTemplate.java).

Các test minh họa ưu tiên kiểm tra số lần gọi và routing. Nếu cần kiểm tra thời gian backoff chính xác, hãy dùng điểm thay thế chiến lược chờ phù hợp với API đang dùng, thay vì assertion thời gian sát từng mili giây.

### 10.3. Kiểm thử bổ sung cho ứng dụng thật

- Bỏ recovery callback và xác nhận sender đồng bộ nhận exception khi dừng retry.
- Làm bước downstream thất bại và kiểm tra lời gọi giữ hàng không bị lặp bởi advice ở endpoint giữ hàng.
- Mô phỏng thao tác thành công nhưng mất phản hồi để kiểm tra idempotency.
- Làm recovery channel không tiếp nhận được message và kiểm tra cơ chế báo lỗi.
- Với stateful, giao lại cùng khóa nghiệp vụ nhưng tạo `Message` mới.
- Với broker, kiểm tra cả acknowledgment, rollback, redelivery và nơi lưu lỗi cuối cùng.

Đây là kiểm thử hành vi của luồng. Chỉ kiểm thử một `RetryTemplate` tách rời sẽ chưa xác nhận advice đã gắn đúng endpoint.

## 11. Đọc cấu hình Spring Integration 6.x

Nếu ứng dụng đang dùng Spring Integration 6.x, advice nhận `org.springframework.retry.support.RetryTemplate` qua `setRetryTemplate(...)` và dùng API Spring Retry. Stateful retry của nhánh này dùng `RetryStateGenerator`, khác với `stateKeyFunction` của 7.x. [Nguồn: RequestHandlerRetryAdvice 6.5](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/handler/advice/RequestHandlerRetryAdvice.html).

Trong cùng cấu hình demo, có thể thay method `orderRetryAdvice(...)` bằng đoạn dưới khi project đã chọn hệ dependency 6.x và bổ sung Spring Retry 2.x. Không kết hợp imports retry của hai nhánh.

~~~java
@Bean
public RequestHandlerRetryAdvice orderRetryAdvice(
        @Qualifier("exhaustedOrders") MessageChannel recoveryChannel) {

    var template = new org.springframework.retry.support.RetryTemplate();

    var retryableExceptions =
            java.util.Map.<Class<? extends Throwable>, Boolean>of(
                    TransientPartnerException.class, true);

    template.setRetryPolicy(
            new org.springframework.retry.policy.SimpleRetryPolicy(
                    3,
                    retryableExceptions,
                    true));

    var backOff =
            new org.springframework.retry.backoff.ExponentialBackOffPolicy();
    backOff.setInitialInterval(100L);
    backOff.setMultiplier(2.0);
    backOff.setMaxInterval(1_000L);
    template.setBackOffPolicy(backOff);

    var advice = new RequestHandlerRetryAdvice();
    advice.setRetryTemplate(template);
    advice.setRecoveryCallback(
            new ErrorMessageSendingRecoverer(recoveryChannel));
    return advice;
}
~~~

Trong `SimpleRetryPolicy`, `maxAttempts = 3` **bao gồm lần đầu**. Tham số `true` ở constructor bật duyệt chuỗi cause để tìm exception phù hợp. [Nguồn: SimpleRetryPolicy](https://docs.spring.io/spring-retry/docs/2.0.12/apidocs/org/springframework/retry/policy/SimpleRetryPolicy.html).

| Ý định | Spring Integration 6.x / Spring Retry 2.x | Spring Integration 7.x / Spring Framework 7.x |
| --- | --- | --- |
| Tối đa ba lần gọi | `SimpleRetryPolicy(3, ...)` | `RetryPolicy.builder().maxRetries(2)` |
| Gắn cấu hình retry | `setRetryTemplate(template)` | `setRetryPolicy(policy)` |
| Backoff | `BackOffPolicy` từ Spring Retry | Cấu hình builder của `RetryPolicy` |
| Stateful | `setRetryStateGenerator(...)` | `setStateKeyFunction(...)` |
| Recovery callback | `org.springframework.retry.RecoveryCallback` | `org.springframework.integration.core.RecoveryCallback` |

Bảng dùng các API đã giới thiệu để đối chiếu hai ví dụ. Khi nâng cấp, cần xem lại cả import, callback và số lượt; thay tên class đơn thuần chưa đủ.

## 12. Quan sát vận hành

Khi đưa luồng vào ứng dụng, nên ghi nhận ít nhất:

| Thông tin | Mục đích |
| --- | --- |
| Tên endpoint | Biết bước nào đang retry |
| Mã yêu cầu nghiệp vụ trong log/trace | Ghép các lần gọi của cùng thao tác |
| Loại lỗi hoặc mã lỗi đã chuẩn hóa | Phân biệt lỗi tạm thời với dữ liệu không hợp lệ |
| Số lần handler thực thi | Đánh giá tải tăng do retry |
| Số chu kỳ thành công sau retry | Biết retry thực sự giúp bao nhiêu yêu cầu |
| Số chu kỳ dừng bằng lỗi | Theo dõi đầu ra cần phục hồi |
| Thời gian toàn chu kỳ | Đánh giá deadline của caller |
| Độ sâu và tuổi message của đường lỗi | Phát hiện công việc thất bại chưa được xử lý |

Đây là đề xuất thông tin cần quan sát, không phải danh sách metric được tự động tạo bởi advice.

Một số lưu ý khi thiết kế:

- Tách số lần thực thi handler khỏi số yêu cầu nghiệp vụ đầu vào.
- Dùng label metric ít giá trị như endpoint và nhóm lỗi; giữ `orderId` trong log/trace để tránh cardinality quá lớn.
- Hạn chế log stack trace đầy đủ ở mọi lượt nếu lỗi tạm thời có tần suất cao.
- Theo dõi riêng lỗi recovery để không nhầm chúng với lỗi phía đối tác.
- Tránh đưa dữ liệu nhạy cảm của payload vào log một cách mặc định.

Có thể dùng `RetryListener` cho các sự kiện retry, kết hợp quan sát ở endpoint để bao quát cả trường hợp thành công ngay lần đầu. Khi tính metric, hãy xác định sự kiện nào tương ứng một lần thực thi và sự kiện nào tương ứng một chu kỳ.

## 13. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Điểm cần kiểm tra |
| --- | --- |
| Chỉ chạy một lần dù đã tạo bean retry | Bean đã được gắn vào endpoint qua `advice(...)` hoặc `adviceChain` chưa? |
| Exception gốc đúng loại nhưng không retry | Có wrapper không; policy có xét cause không; lỗi có phát sinh trong phạm vi handler không? |
| Không có exception nhưng cũng không có reply | Handler hoặc recovery có trả `null`; đang chờ sai channel; có yêu cầu reply bắt buộc không? |
| Có nhiều lần giữ hàng cho cùng yêu cầu | Lời gọi có idempotency chưa; đang retry ở mấy tầng? |
| Queue đầu vào tăng nhanh khi đối tác lỗi | Worker có đang bị chiếm bởi timeout và backoff không? |
| Sender không thấy lỗi sau khi xử lý thất bại | Recovery có hoàn tất bình thường; có ranh giới bất đồng bộ không? |
| Stateful không tiếp tục chu kỳ cũ | Khóa nghiệp vụ có giữ nguyên; message có tới cùng instance; cache có bị mất không? |
| Lượt sau thành công nhưng commit vẫn lỗi | Transaction có bị đánh dấu rollback-only từ lượt đầu không? |
| Code `setRetryTemplate` không biên dịch trong 7.x | Có đang trộn ví dụ 6.x với dependency 7.x không? |
| Mong retry ba lần nhưng chỉ có ba lần gọi tổng cộng | Có đang dùng `maxAttempts` của Spring Retry, tính cả lần đầu không? |

Chẩn đoán theo thứ tự: xác định endpoint, quan sát exception thực tế, đếm số lần handler chạy, xác định channel đầu ra rồi kiểm tra transaction và cơ chế giao lại.

## 14. Bài tập thực hành

### Bài tập 1: đổi số lượt và dự đoán trước

Đổi policy chính thành `maxRetries(3)`, delay ban đầu 50 ms, multiplier 2 và không jitter.

Trước khi chạy, dự đoán:

- Một yêu cầu lỗi hai lần rồi thành công cần ba lần gọi.
- Một yêu cầu luôn lỗi cần tối đa bốn lần gọi.
- Các khoảng chờ trước ba lượt retry lần lượt là 50 ms, 100 ms và 200 ms.

Đối chiếu bằng bộ đếm và số message ở hai đường ra.

### Bài tập 2: chứng minh phạm vi endpoint

Thêm một bước audit sau handler giữ hàng. Cho audit ném exception trong khi giữ hàng thành công.

Kết quả cần quan sát: sender đồng bộ nhận lỗi downstream, nhưng advice tại handler giữ hàng không tự gọi lại thao tác giữ hàng vì lỗi audit.

### Bài tập 3: thiết kế đường lỗi bền vững

Thay queue lỗi trong bộ nhớ bằng một phương án lưu lỗi phù hợp với ứng dụng.

Thiết kế cần nêu rõ dữ liệu phải lưu, thời điểm xác nhận message nguồn, cách xử lý khi lưu lỗi thất bại và cách người vận hành gửi lại yêu cầu mà vẫn dùng đúng idempotency key.

### Bài tập 4: khảo sát stateful

Trong môi trường có broker, dùng cùng `businessRequestId` qua các lần redelivery và ghi lại số lần handler thực thi.

Sau đó thử đổi khóa ở mỗi lần nhận message. Giải thích vì sao advice không còn ghép được các lần giao lại vào cùng một chu kỳ. Đánh giá thêm trường hợp consumer khởi động lại giữa chu kỳ.

## 15. Các điểm cần ghi nhớ

`RequestHandlerRetryAdvice` giúp tập trung retry tại bước xử lý message cần bảo vệ. Một cấu hình hữu ích phải xác định rõ phạm vi handler, exception được retry, số lần gọi tối đa, thời gian chờ và kết quả khi chu kỳ dừng.

Trong Spring Integration 7.x, dùng `RetryPolicy` của Spring Framework và tính tổng số lần gọi bằng `1 + maxRetries`. Trong ví dụ 6.x dùng Spring Retry, `maxAttempts` đã tính cả lần đầu.

Recovery tiếp nhận thất bại; tính an toàn của thao tác lặp vẫn phụ thuộc idempotency, transaction và hợp đồng với hệ thống đích. Hãy kiểm chứng bằng số lần thực thi cùng đầu ra thực tế của cả đường thành công lẫn đường lỗi.
