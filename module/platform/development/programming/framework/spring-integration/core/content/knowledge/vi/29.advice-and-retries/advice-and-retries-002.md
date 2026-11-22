# RetryTemplate

## 1. Mục tiêu và phạm vi phiên bản

Trong chương **Advice và retry** của mô-đun **SPRING_INTEGRATION_CORE**, `RetryTemplate` giúp thực hiện lại một thao tác khi thao tác đó gặp lỗi có khả năng tự hết. Ví dụ: endpoint gọi hãng vận chuyển nhận lỗi dịch vụ tạm thời; ứng dụng chờ một khoảng ngắn rồi thử lại trước khi chuyển yêu cầu sang luồng xử lý thất bại.

Sau bài này, bạn có thể xác định đoạn xử lý được thử lại, cấu hình số lần thử và thời gian chờ, phân loại exception, gắn retry vào một endpoint Java DSL và kiểm tra kết quả khi retry thành công hoặc cạn lượt.

Có hai lớp cùng tên `RetryTemplate` thuộc hai thế hệ API. Bài dùng **Java 17+, Spring Integration 6.5.x và Spring Retry 2.0.x** cho các ví dụ chính ở mục 2–12; mục 13 trình bày API tương ứng của Spring Integration 7.x. Việc chọn nhánh 6.5 nhằm giải thích đầy đủ mô hình `RetryContext`, `BackOffPolicy` và `RecoveryCallback` của Spring Retry, không phải yêu cầu hạ phiên bản dự án đang dùng 7.x.

| Nội dung | Ví dụ chính: Integration 6.5 + Spring Retry 2.0 | Integration 7.x + Spring Framework 7.x |
| --- | --- | --- |
| Lớp template | `org.springframework.retry.support.RetryTemplate` | `org.springframework.core.retry.RetryTemplate` |
| Cấu hình số lần | `maxAttempts(n)`: tính cả lần đầu | `maxRetries(n)`: số lần thử thêm sau lần đầu |
| Gắn vào retry advice | `setRetryTemplate(template)` | `setRetryPolicy(policy)` |
| Recovery trong Integration | `org.springframework.retry.RecoveryCallback` | `org.springframework.integration.core.RecoveryCallback` |

Spring Integration 7.0 chuyển từ Spring Retry sang retry API trong Spring Framework Core và thay đổi API của `RequestHandlerRetryAdvice`. Vì vậy, chỉ đổi câu lệnh `import` là chưa đủ để nâng cấp ví dụ. Nguồn: [thay đổi từ Spring Integration 6.5 sang 7.0](https://docs.spring.io/spring-integration/reference/changes-6.5-7.0.html).

## 2. Retry ở đâu trong một luồng thông điệp?

Xét luồng tạo vận đơn:

```text
Message<ShippingRequest>
    -> shippingRequests: DirectChannel
    -> service activator gọi hãng vận chuyển, có retry advice
    -> shippingResults: QueueChannel

Nếu thao tác được bảo vệ không thành công:
    -> recovery callback
    -> shippingFailures: QueueChannel chứa ErrorMessage
```

`Message` mang yêu cầu và headers; `MessageChannel` vận chuyển message; endpoint thực hiện thao tác nghiệp vụ; advice bao quanh phần thực thi của endpoint đó. `RetryTemplate` quản lý chu kỳ thử, còn `RequestHandlerRetryAdvice` nối cơ chế retry với việc xử lý message.

Ranh giới cần đặt là **thao tác có thể gọi lại một cách an toàn**. Với ví dụ trên, đó là lời gọi tạo vận đơn có mã chống trùng; không nên bao trùm cả chuỗi trừ tồn kho, thu tiền và gửi email nếu cả ba bước sẽ bị lặp khi chỉ bước cuối thất bại.

Advice gắn trên một service activator không tự biến toàn bộ flow thành một đơn vị retry. Đặc biệt, lỗi gửi reply xuống channel tiếp theo không nên mặc nhiên được coi là lỗi của lời gọi được bảo vệ. Muốn retry một đoạn gồm nhiều endpoint, phải thiết kế rõ một ranh giới gọi, chẳng hạn qua gateway, đồng thời xem xét lại mọi tác dụng phụ trong đoạn đó. Cơ chế cơ bản được mô tả trong [Retry Advice của Spring Integration 6.5](https://docs.spring.io/spring-integration/reference/6.5/handler-advice/classes.html).

## 3. Những thành phần phối hợp với RetryTemplate

| Thành phần | Câu hỏi mà nó giải quyết |
| --- | --- |
| `RetryCallback<T, E>` | Thao tác nào sẽ được thực hiện lại? |
| `RetryPolicy` | Với số lần thất bại và loại lỗi hiện tại, còn được thử không? |
| `BackOffPolicy` | Nếu còn được thử, phải chờ bao lâu? |
| `RetryContext` | Chu kỳ hiện tại đã thất bại bao nhiêu lần, lỗi gần nhất là gì? |
| `RecoveryCallback<T>` | Khi không tiếp tục thử, kết quả thay thế hoặc hành động xử lý cuối là gì? |
| `RetryListener` | Theo dõi bắt đầu, lỗi từng lần và kết thúc chu kỳ bằng cách nào? |

Các bước thực thi stateless có thể hình dung như sau:

```text
Mở context
    -> gọi callback
        -> thành công: trả kết quả, kết thúc
        -> exception: ghi nhận lần thất bại
            -> còn được retry: backoff rồi gọi lại callback
            -> không được retry nữa:
                -> có recovery phù hợp: gọi recovery
                -> không có recovery: ném lỗi ra ngoài
```

Nếu callback bắt exception rồi trả một giá trị bình thường, template nhìn thấy một lần thực thi thành công. Việc trả về `null`, mã lỗi hoặc một đối tượng có `status = FAILED` không tự kích hoạt retry. Muốn retry dựa trên phản hồi từ hệ thống bên ngoài, lớp client cần phân loại phản hồi và chuyển trường hợp phù hợp thành exception.

Một instance `RetryTemplate` có thể dùng đồng thời cho nhiều thao tác; trạng thái đếm lượt nằm trong context của từng chu kỳ. Điều đó không làm cho callback, client hoặc biến đếm do ứng dụng tự viết trở nên an toàn khi chạy đồng thời. Xem [Javadoc RetryTemplate của Spring Retry](https://docs.spring.io/spring-retry/docs/2.0.12/apidocs/org/springframework/retry/support/RetryTemplate.html).

## 4. Đếm số lần thử cho đúng

Trong Spring Retry, `maxAttempts(3)` nghĩa là **tối đa ba lần thực thi tổng cộng: một lần đầu và hai lần thử lại**. `maxAttempts(1)` vẫn thực hiện thao tác một lần nhưng không thử thêm. Quy ước này cũng áp dụng cho `SimpleRetryPolicy`; xem [Javadoc SimpleRetryPolicy](https://docs.spring.io/spring-retry/docs/2.0.12/apidocs/org/springframework/retry/policy/SimpleRetryPolicy.html).

Ví dụ độc lập sau mô phỏng hai lần thất bại rồi thành công ở lần thứ ba:

```java
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.retry.support.RetryTemplate;

public class RetryCountingExample {

    static class TemporaryCarrierException extends RuntimeException {
        TemporaryCarrierException(String message) {
            super(message);
        }
    }

    public static void main(String[] args) {
        AtomicInteger calls = new AtomicInteger();

        RetryTemplate template = RetryTemplate.builder()
                .maxAttempts(3)
                .noBackoff()
                .retryOn(TemporaryCarrierException.class)
                .build();

        String trackingCode = template.execute(context -> {
            int attempt = context.getRetryCount() + 1;
            int call = calls.incrementAndGet();
            System.out.println("attempt=" + attempt);

            if (call < 3) {
                throw new TemporaryCarrierException("Carrier unavailable");
            }
            return "TRACK-A001";
        });

        System.out.println(trackingCode + ", calls=" + calls.get());
    }
}
```

Kết quả dự kiến:

```text
attempt=1
attempt=2
attempt=3
TRACK-A001, calls=3
```

Ở đầu callback lần thứ nhất, `getRetryCount()` bằng `0`. Sau một lần thất bại, giá trị bằng `1`; nếu callback tiếp tục chạy thì đó là lần thực thi thứ hai. Nếu cả ba lần đều thất bại, recovery nhìn thấy số đếm bằng `3`. Do đó, khi ghi log phải xác định log nằm trước lần gọi hay sau một lỗi, tránh cộng `1` ở mọi vị trí. Context cũng cung cấp `getLastThrowable()` để xem lỗi gần nhất; xem [Javadoc RetryContext](https://docs.spring.io/spring-retry/docs/2.0.12/apidocs/org/springframework/retry/RetryContext.html).

## 5. Chọn lỗi được retry

### 5.1. Phân loại theo khả năng phục hồi

Retry có ích khi cùng một yêu cầu có thể thành công sau một khoảng chờ mà không cần sửa dữ liệu đầu vào. Bảng dưới là định hướng thiết kế cho ví dụ hãng vận chuyển; cách phân loại cuối cùng phụ thuộc hợp đồng API của đối tác.

| Tình huống | Hành động dự kiến |
| --- | --- |
| Đối tác báo dịch vụ tạm thời không sẵn sàng | Có thể retry với giới hạn và backoff |
| Kết nối bị ngắt trước khi xác định kết quả | Xem xét retry cùng mã chống trùng, hoặc tra cứu kết quả trước |
| Đối tác giới hạn lưu lượng | Tuân thủ khoảng chờ trong hợp đồng API, kiểm soát tổng số yêu cầu |
| Địa chỉ thiếu trường bắt buộc | Không retry; cần sửa dữ liệu |
| Thông tin xác thực sai hoặc quyền truy cập bị từ chối | Không lặp ngay cùng yêu cầu; cần xử lý cấu hình/quyền |
| Lỗi lập trình như `NullPointerException` | Không che bằng vòng retry rộng |

Ví dụ cấu hình chỉ thử lại lỗi tạm thời:

```java
RetryTemplate template = RetryTemplate.builder()
        .maxAttempts(3)
        .fixedBackoff(200)
        .retryOn(TemporaryCarrierException.class)
        .traversingCauses()
        .build();
```

Trong các ví dụ ngắn, `TemporaryCarrierException` là exception nghiệp vụ đã khai báo ở ví dụ tương ứng. Các khoảng thời gian dạng số của builder Spring Retry ở đây có đơn vị **mili giây**.

### 5.2. Chú ý exception bị bọc trong messaging

Một lỗi client có thể nằm trong chuỗi nguyên nhân:

```text
MessageHandlingException
    -> TemporaryCarrierException
```

Nếu chỉ kiểm tra exception ngoài cùng, bộ phân loại có thể không nhận ra lỗi tạm thời. `.traversingCauses()` cho phép xét chuỗi `cause` khi phân loại. Cấu hình này đặc biệt có ích khi callback của bạn chủ động gọi một thành phần messaging có bọc exception; không nên giả định mọi endpoint đều bọc lỗi theo cùng một cách.

Chỉ thêm `retryOn(Exception.class)` để làm cho retry “hoạt động” sẽ mở rộng phạm vi sang cả lỗi dữ liệu và lỗi lập trình. Thay vào đó, xác định exception thực sự đi qua ranh giới được bảo vệ rồi chọn lớp lỗi phù hợp. API builder và các tùy chọn phân loại được mô tả tại [RetryTemplateBuilder](https://docs.spring.io/spring-retry/docs/2.0.12/apidocs/org/springframework/retry/support/RetryTemplateBuilder.html).

## 6. Backoff và ngân sách thời gian

### 6.1. Chọn khoảng chờ

| Cấu hình Spring Retry | Hành vi |
| --- | --- |
| `.noBackoff()` | Không chủ động chờ giữa các lần; phù hợp cho kiểm thử đếm lượt |
| `.fixedBackoff(200)` | Chờ 200 ms giữa hai lần thực thi liên tiếp |
| `.exponentialBackoff(100, 2.0, 1000)` | Bắt đầu ở 100 ms, nhân 2, giới hạn khoảng chờ ở 1.000 ms |
| `.exponentialBackoff(100, 2.0, 1000, true)` | Dùng biến thể exponential có ngẫu nhiên; không áp dụng nguyên xi lịch chờ cố định |

Với exponential không ngẫu nhiên, khoảng chờ thứ `k`, tính từ `k = 1` trước lần thực thi thứ hai, được mô hình hóa:

```text
d(k) = min(initialInterval × multiplier^(k - 1), maxInterval)
```

Đây là mô hình tính lịch chờ; khi dùng số không nguyên có thể có khác biệt do làm tròn. Với `maxAttempts(4)`, `initialInterval = 100`, `multiplier = 2` và `maxInterval = 1000`, ba khoảng chờ là `100, 200, 400` ms. Tổng chờ là `700` ms. Không có khoảng chờ trước lần đầu hoặc sau lần thất bại cuối cùng. Thuộc tính của policy được mô tả trong [ExponentialBackOffPolicy](https://docs.spring.io/spring-retry/docs/2.0.12/apidocs/org/springframework/retry/backoff/ExponentialBackOffPolicy.html).

Ngẫu nhiên hóa khoảng chờ giúp nhiều instance tránh cùng thử lại ở một thời điểm. Nó không thay thế giới hạn số lượt, kiểm soát tải hoặc circuit breaker khi dịch vụ đích ngừng hoạt động lâu.

### 6.2. Tính cùng timeout của client và gateway

Giả sử mỗi lần gọi có giới hạn thời gian thực tế không quá `800` ms, có ba lần thực thi và hai khoảng chờ `100, 200` ms. Ước lượng ngân sách cho phần gọi và chờ là:

```text
T ≈ 3 × 800 + 100 + 200 = 2.700 ms
```

Đây là phép tính thiết kế với giả định trên; chưa bao gồm thời gian xếp hàng, chờ connection pool, xử lý channel hay recovery. Cần đặt timeout tương ứng cho client và các tài nguyên thực sự tham gia lời gọi, rồi dành thêm ngân sách cho toàn bộ request.

`maxAttempts` giới hạn số lần chứ không ngắt một lời gọi mạng đang treo. Tương tự, một chính sách giới hạn thời gian retry không mặc nhiên hủy được I/O đang thực thi. Timeout chờ reply của gateway cũng không phải cơ chế bảo đảm dừng công việc nền.

Stateless retry với backoff đồng bộ giữ thread của endpoint trong suốt chu kỳ. Với `DirectChannel`, đó còn là thread của bên gửi. Nếu mỗi message chờ vài chục giây trong một pool nhỏ, pool có thể cạn trước khi đạt lưu lượng mong muốn. Khi khoảng chờ dài là một phần yêu cầu nghiệp vụ, hãy cân nhắc retry queue hoặc cơ chế redelivery có lưu bền và lập lịch phù hợp.

## 7. Ví dụ đầy đủ: gắn RetryTemplate vào Java DSL

### 7.1. Chuẩn bị dependency

Đối với nhánh ví dụ 6.5, cần `spring-integration-core` và `spring-retry`. Đoạn Maven sau giả định dependency management/BOM của dự án đã quản lý hai phiên bản tương thích; nếu chưa có dependency management thì phải khai báo phiên bản tương ứng.

```xml
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-core</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.retry</groupId>
    <artifactId>spring-retry</artifactId>
</dependency>
```

Ví dụ cấu hình trực tiếp bean `RetryTemplate` và endpoint advice nên không cần `@EnableRetry`. Annotation đó phục vụ mô hình proxy dùng `@Retryable`, là cách áp dụng khác.

### 7.2. Cấu hình luồng và client giả lập

Đặt mã sau trong `ShippingRetryConfiguration.java`. Client giả lập có ba hành vi: mã đơn bắt đầu bằng `DOWN-` luôn gặp lỗi tạm thời; yêu cầu thiếu địa chỉ gặp lỗi dữ liệu ngay; yêu cầu còn lại thất bại hai lần rồi thành công. Đây là mô phỏng cục bộ, không gọi API thật.

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.advice.ErrorMessageSendingRecoverer;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.retry.support.RetryTemplate;

@Configuration
@EnableIntegration
public class ShippingRetryConfiguration {

    public record ShippingRequest(String orderId, String address) {}

    public record ShippingResult(String orderId, String trackingCode) {}

    public static class TemporaryCarrierException extends RuntimeException {
        public TemporaryCarrierException(String message) {
            super(message);
        }
    }

    public static class DemoCarrierClient {
        private final ConcurrentMap<String, AtomicInteger> calls =
                new ConcurrentHashMap<>();

        public ShippingResult createShipment(ShippingRequest request) {
            int attempt = calls.computeIfAbsent(
                    request.orderId(), key -> new AtomicInteger())
                    .incrementAndGet();

            if (request.address() == null || request.address().isBlank()) {
                throw new IllegalArgumentException("Shipping address is required");
            }
            if (request.orderId().startsWith("DOWN-") || attempt < 3) {
                throw new TemporaryCarrierException("Carrier temporarily unavailable");
            }
            return new ShippingResult(
                    request.orderId(), "TRACK-" + request.orderId());
        }

        public int attempts(String orderId) {
            AtomicInteger count = calls.get(orderId);
            return count == null ? 0 : count.get();
        }
    }

    @Bean
    public DemoCarrierClient carrierClient() {
        return new DemoCarrierClient();
    }

    @Bean
    public DirectChannel shippingRequests() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel shippingResults() {
        return new QueueChannel(100);
    }

    @Bean
    public QueueChannel shippingFailures() {
        return new QueueChannel(100);
    }

    @Bean
    public RetryTemplate shippingRetryTemplate() {
        return RetryTemplate.builder()
                .maxAttempts(3)
                .exponentialBackoff(100, 2.0, 1000)
                .retryOn(TemporaryCarrierException.class)
                .traversingCauses()
                .build();
    }

    @Bean
    public RequestHandlerRetryAdvice shippingRetryAdvice(
            RetryTemplate shippingRetryTemplate,
            @Qualifier("shippingFailures") QueueChannel failures) {

        ErrorMessageSendingRecoverer recoverer =
                new ErrorMessageSendingRecoverer(failures);
        recoverer.setSendTimeout(1000);

        RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
        advice.setRetryTemplate(shippingRetryTemplate);
        advice.setRecoveryCallback(recoverer);
        return advice;
    }

    @Bean
    public IntegrationFlow shippingFlow(
            DemoCarrierClient carrierClient,
            RequestHandlerRetryAdvice shippingRetryAdvice) {

        return IntegrationFlow.from("shippingRequests")
                .handle(ShippingRequest.class,
                        (request, headers) -> carrierClient.createShipment(request),
                        endpoint -> endpoint.advice(shippingRetryAdvice))
                .channel("shippingResults")
                .get();
    }
}
```

Điểm kết nối là `endpoint.advice(shippingRetryAdvice)`: bean template chỉ có tác dụng đối với endpoint khi được đưa vào advice và advice được gắn vào endpoint đó. Method `.handle(...)` tạo bước gọi client nhận payload `ShippingRequest`; xem [Java DSL với service activator](https://docs.spring.io/spring-integration/reference/6.5/dsl/java-handle.html) và [API RequestHandlerRetryAdvice 6.5](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/handler/advice/RequestHandlerRetryAdvice.html).

Client giả lập đếm theo `orderId` để minh họa. Trong ứng dụng thực, cần kiểm tra `orderId` và các trường bắt buộc trước ranh giới gọi client. Map trong ví dụ không phải kho chống trùng hay kho trạng thái retry dùng cho production.

### 7.3. Kết quả mong đợi

Với mỗi yêu cầu mới trong một application context mới:

| Payload | Số lần gọi client | Kết quả |
| --- | --- | --- |
| `new ShippingRequest("A-1", "12 Nguyen Trai")` | 3 | Một `ShippingResult` ở `shippingResults` |
| `new ShippingRequest("DOWN-1", "12 Nguyen Trai")` | 3 | Một `ErrorMessage` ở `shippingFailures` |
| `new ShippingRequest("BAD-1", " ")` | 1 | Một `ErrorMessage` ở `shippingFailures`, không thử thêm |

Lỗi dữ liệu ở hàng cuối không được retry nhưng vẫn đi qua recovery trong cấu hình này. **Không được retry** và **không được recovery** là hai quyết định khác nhau. Nếu yêu cầu nghiệp vụ cần ném một loại lỗi ra ngoài thay vì gửi vào failure channel, phải thể hiện điều đó trong chính sách/recovery thích hợp.

Hai queue trong ví dụ dùng bộ nhớ, có dung lượng hữu hạn và được đọc trực tiếp trong kiểm thử. Trong một flow chạy liên tục, chúng cần consumer; lưu bền hay không phải là quyết định riêng. Việc đặt tên `shippingFailures` không tự tạo dead-letter queue trên message broker. Khi queue đầy và gửi recovery vượt timeout đã cấu hình, bản thân recovery có thể thất bại.

## 8. Recovery và error channel

### 8.1. Recovery trả về một kết quả thay thế

Khi gọi template trực tiếp, recovery có thể tạo một kết quả nghiệp vụ rõ nghĩa. Ví dụ sau đặt trong một phương thức đã có `request`, `carrierClient` và `template`, dùng các kiểu dữ liệu của mục 7:

```java
record ShippingDecision(String orderId, String status, String trackingCode) {}

ShippingDecision decision = template.execute(
        context -> {
            var result = carrierClient.createShipment(request);
            return new ShippingDecision(
                    result.orderId(), "CREATED", result.trackingCode());
        },
        context -> new ShippingDecision(
                request.orderId(), "PENDING_REVIEW", null));
```

`PENDING_REVIEW` biểu thị chưa có kết quả tạo vận đơn, không phải một vận đơn đã tạo thành công. Bên nhận phải xử lý trạng thái đó. Nếu recovery thực hiện ghi dữ liệu hoặc phát một message khác, hành động đó cũng cần cơ chế phát hiện thất bại và tránh trùng phù hợp.

### 8.2. Recovery gửi ErrorMessage

Ở mục 7, `ErrorMessageSendingRecoverer` gửi lỗi cuối dưới dạng `ErrorMessage` tới channel đã chỉ định. Payload của error message là một `Throwable`, không phải trực tiếp `ShippingRequest`. Khi cần khôi phục request, phải xét thông tin message gốc/`failedMessage` mà exception hoặc chiến lược tạo error message cung cấp; không nên ép kiểu payload lỗi thành payload nghiệp vụ. Xem [ErrorMessageSendingRecoverer](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/handler/advice/ErrorMessageSendingRecoverer.html).

Khi recoverer gửi thành công và trả `null`, endpoint không tạo reply nghiệp vụ cho nhánh `shippingResults`. Nếu thay flow bằng gateway request–reply, phải thiết kế kết quả thất bại hoặc luồng trả lời tương ứng; nếu không, caller có thể tiếp tục chờ đến hết timeout.

Recovery hoàn tất cũng làm thay đổi ý nghĩa mà bên gọi nhìn thấy: chu kỳ được coi là đã xử lý qua nhánh recovery, dù thao tác tạo vận đơn không thành công. Đừng suy ra `channel.send(...) == true` có nghĩa là vận đơn đã được tạo. Với adapter có transaction/acknowledgment, việc không còn exception có thể ảnh hưởng đến commit hoặc ack; cần xem cấu hình adapter và transaction cụ thể.

### 8.3. Nếu không cấu hình recovery

Để lỗi cuối thoát khỏi advice ở ví dụ 6.5, bỏ `setRecoveryCallback(...)`. Với luồng đồng bộ đi qua `DirectChannel`, lỗi có thể truyền về bên gửi, thường dưới dạng exception messaging có chứa nguyên nhân gốc.

Việc chỉ đặt header `errorChannel` không tự chuyển mọi exception đồng bộ thành một error message. Trong xử lý bất đồng bộ, error handler của framework/adapter mới là thành phần xuất bản lỗi; gateway cũng có quy tắc xử lý lỗi riêng. Do đó, luôn xác định **ai bắt exception cuối** và **ai gửi ErrorMessage** trong từng luồng. Xem [Error Handling của Spring Integration 6.5](https://docs.spring.io/spring-integration/reference/6.5/error-handling.html).

## 9. Stateless, stateful và redelivery

| Khía cạnh | Stateless retry | Stateful retry |
| --- | --- | --- |
| Cách tiếp tục | Thử tiếp trong một lần gọi template | Lưu trạng thái theo khóa và tiếp tục qua các lần gọi lại |
| Bên gọi có thể nhận lỗi trung gian không? | Thường chỉ sau khi chu kỳ không tiếp tục/recovery không xử lý | Có; lỗi có thể được ném ra để upstream rollback và giao lại |
| Nhận diện cùng một yêu cầu | Một context của một lần gọi | Cần khóa ổn định giữa các lần giao lại |
| Ai bảo đảm có lần giao lại? | Không cần upstream cho các lượt trong chu kỳ | Broker, container hoặc ứng dụng gọi lại |

Ví dụ mục 7 là stateless: ba lần thực thi có thể xảy ra trong một lần `shippingRequests.send(...)`. Không có message mới được gửi lại vào input channel giữa ba lần đó.

Trong Integration 6.5, stateful retry dùng `RetryStateGenerator` với retry advice. Trong Integration 7.x, cơ chế này chuyển sang `stateKeyFunction`. Khóa thường nên thể hiện cùng một thao tác nghiệp vụ, chẳng hạn `tenantId + orderId + operation`, thay vì dùng một message ID có thể thay đổi mỗi lần broker giao lại.

Stateful retry không tự tạo redelivery và không mặc nhiên làm cho khoảng chờ trở thành bất đồng bộ. Cần kiểm tra ai giao lại, khi nào giao lại, trạng thái được lưu ở đâu và điều gì xảy ra nếu ứng dụng khởi động lại. Cache cục bộ không bảo đảm giữ nguyên ngân sách retry sau khi mất tiến trình.

Một rủi ro khác là nhiều tầng đều retry. Giả sử client HTTP thử tối đa 3 lần cho mỗi lần handler gọi, advice gọi handler tối đa 3 lần và broker giao lại message tối đa 5 lần; nếu cả ba tầng đều đi hết lượt mà không có recovery kết thúc sớm, số request tới đối tác có thể đạt:

```text
3 × 3 × 5 = 45 request cho một yêu cầu nghiệp vụ
```

Đây là phép tính cho cấu hình giả định trên, không phải mặc định của các framework. Hãy xác định một ngân sách tổng và phân bổ nó cho từng tầng, bao gồm cả thời gian chờ và điều kiện dừng.

## 10. Idempotency, transaction và tác vụ bất đồng bộ

### 10.1. Retry không chứng minh lần trước chưa thành công

Một tình huống tạo vận đơn thường gặp:

1. Hãng vận chuyển tạo vận đơn thành công.
2. Phản hồi bị mất trên đường về.
3. Client timeout và ném exception.
4. Retry gọi tạo lại với cùng dữ liệu.

Nếu không có chống trùng phía đối tác, hệ thống có thể tạo hai vận đơn. Với mỗi thao tác tạo mới, nên có một `idempotencyKey` ổn định qua tất cả lần thử và redelivery. Đối tác phải thực thi hợp đồng chống trùng bằng khóa đó; chỉ thêm một header trong message nội bộ chưa tạo ra bảo đảm.

Nếu đối tác không hỗ trợ idempotency, cân nhắc tra cứu bằng mã tham chiếu nghiệp vụ hoặc đưa kết quả chưa xác định sang đối soát. Không nên trả một tracking code giả để làm cho flow trông như thành công.

### 10.2. Mỗi lần thử có transaction nào?

Một transaction bên ngoài bao toàn bộ chu kỳ khác với một transaction mới cho từng lần thử. Ví dụ, sau một lỗi database, transaction hiện tại có thể đã ở trạng thái rollback-only; thử tiếp trong transaction đó không bảo đảm phục hồi.

Khi cần transaction riêng cho mỗi lần thử, ranh giới retry phải bao ngoài ranh giới tạo transaction cho từng lần gọi. Với nhiều advice, thứ tự áp dụng có ý nghĩa; không nên suy ra thứ tự chỉ từ việc hai bean cùng tồn tại. Hãy kiểm tra bằng tình huống rollback thực tế và xác nhận commit/rollback ở từng lượt.

Rollback transaction cục bộ cũng không thu hồi một vận đơn đã tạo ở hệ thống từ xa. Idempotency và cơ chế đối soát vẫn cần thiết.

### 10.3. Exception phải xảy ra trong đoạn được bảo vệ

Nếu handler chỉ khởi chạy `CompletableFuture` hoặc trả về một publisher rồi kết thúc, lỗi xảy ra về sau có thể nằm ngoài lần gọi mà advice đang bảo vệ. `RetryTemplate` đồng bộ không tự đăng ký theo dõi mọi tác vụ bất đồng bộ hoặc reactive mà handler tạo ra.

Hãy đặt retry tại nơi nhận được kết quả/lỗi thực sự, hoặc dùng cơ chế retry phù hợp với kiểu xử lý đó. Đồng thời giữ ranh giới retry đủ nhỏ để tránh lặp lại những bước đã có tác dụng phụ.

## 11. Quan sát chu kỳ retry

Với Spring Retry 2.x, có thể đăng ký `RetryListener` để quan sát mà không đưa logic log vào mọi client:

```java
import org.springframework.retry.RetryCallback;
import org.springframework.retry.RetryContext;
import org.springframework.retry.RetryListener;

template.registerListener(new RetryListener() {
    @Override
    public <T, E extends Throwable> void onError(
            RetryContext context,
            RetryCallback<T, E> callback,
            Throwable throwable) {

        System.out.printf(
                "operation=create-shipment failedAttempts=%d exception=%s%n",
                context.getRetryCount(),
                throwable.getClass().getSimpleName());
    }
});
```

Ở đây `template` là instance đã tạo. Đăng ký listener trong bước cấu hình bean trước khi flow nhận tải. `onError` được gọi sau mỗi lần thất bại, bao gồm cả lần cuối; một sự kiện `onError` chưa đủ để kết luận toàn bộ yêu cầu đã thất bại. Các hook `open`, `onSuccess` và `close` phục vụ các thời điểm khác nhau của vòng đời; xem [RetryListener](https://docs.spring.io/spring-retry/docs/2.0.12/apidocs/org/springframework/retry/RetryListener.html).

Các số đo hữu ích cho flow tạo vận đơn gồm số lần gọi thật đến đối tác, số yêu cầu thành công sau retry, số yêu cầu đi recovery và tổng thời gian xử lý một yêu cầu. Nên phân biệt “đã tạo vận đơn” với “đã tiếp nhận để đối soát”.

Dùng tên endpoint, tên thao tác và nhóm exception làm nhãn metric có số lượng giá trị hữu hạn. `orderId`, địa chỉ và toàn bộ payload không thích hợp làm nhãn metric; mã đối soát có thể đặt trong log có kiểm soát. Listener cũng cần chạy nhanh và không làm phát sinh một lỗi mới che mất lỗi đang quan sát.

## 12. Kiểm thử hành vi, không phụ thuộc thời gian chờ thật

### 12.1. Kiểm thử flow thành công, cạn lượt và lỗi không retry

Đặt lớp sau cùng package với `ShippingRetryConfiguration`, thêm JUnit Jupiter vào dependency kiểm thử. Mỗi test tạo context riêng để dữ liệu mô phỏng không ảnh hưởng lẫn nhau. Helper thay backoff bằng `NoBackOffPolicy` trước khi gửi message, giữ nguyên giới hạn và phân loại exception.

```java
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.GenericMessage;
import org.springframework.retry.backoff.NoBackOffPolicy;
import org.springframework.retry.support.RetryTemplate;

import static org.junit.jupiter.api.Assertions.*;

class ShippingRetryFlowTest {

    private AnnotationConfigApplicationContext newContext() {
        var context = new AnnotationConfigApplicationContext(
                ShippingRetryConfiguration.class);
        context.getBean("shippingRetryTemplate", RetryTemplate.class)
                .setBackOffPolicy(new NoBackOffPolicy());
        return context;
    }

    private void send(AnnotationConfigApplicationContext context,
                      String orderId, String address) {
        var request = new ShippingRetryConfiguration.ShippingRequest(
                orderId, address);
        context.getBean("shippingRequests", MessageChannel.class)
                .send(new GenericMessage<>(request));
    }

    @Test
    void succeedsOnThirdAttempt() {
        try (var context = newContext()) {
            send(context, "A-1", "12 Nguyen Trai");

            var client = context.getBean(
                    ShippingRetryConfiguration.DemoCarrierClient.class);
            var results = context.getBean("shippingResults", QueueChannel.class);
            var failures = context.getBean("shippingFailures", QueueChannel.class);

            assertEquals(3, client.attempts("A-1"));
            Message<?> reply = results.receive(0);
            assertNotNull(reply);
            assertEquals(
                    new ShippingRetryConfiguration.ShippingResult(
                            "A-1", "TRACK-A-1"),
                    reply.getPayload());
            assertNull(results.receive(0));
            assertNull(failures.receive(0));
        }
    }

    @Test
    void sendsOneErrorAfterRetryExhaustion() {
        try (var context = newContext()) {
            send(context, "DOWN-1", "12 Nguyen Trai");

            var client = context.getBean(
                    ShippingRetryConfiguration.DemoCarrierClient.class);
            var results = context.getBean("shippingResults", QueueChannel.class);
            var failures = context.getBean("shippingFailures", QueueChannel.class);

            assertEquals(3, client.attempts("DOWN-1"));
            assertNull(results.receive(0));
            assertInstanceOf(ErrorMessage.class, failures.receive(0));
            assertNull(failures.receive(0));
        }
    }

    @Test
    void doesNotRetryInvalidAddress() {
        try (var context = newContext()) {
            send(context, "BAD-1", " ");

            var client = context.getBean(
                    ShippingRetryConfiguration.DemoCarrierClient.class);
            var results = context.getBean("shippingResults", QueueChannel.class);
            var failures = context.getBean("shippingFailures", QueueChannel.class);

            assertEquals(1, client.attempts("BAD-1"));
            assertNull(results.receive(0));
            assertInstanceOf(ErrorMessage.class, failures.receive(0));
            assertNull(failures.receive(0));
        }
    }
}
```

`receive(0)` đọc ngay vì đầu vào là `DirectChannel`: khi `send` hoàn tất bình thường, phần handler và recovery đồng bộ trong cấu hình này đã chạy xong. Nếu đổi sang `ExecutorChannel` hoặc một consumer dùng poller, cần chờ theo một giới hạn thời gian rõ ràng thay vì giữ nguyên giả định này.

### 12.2. Kiểm thử riêng việc duyệt nguyên nhân exception

Test sau có thể thêm vào một lớp JUnit riêng. Nó chủ động tạo exception bọc để chứng minh cấu hình phân loại, không dựa vào giả định endpoint sẽ bọc lỗi thế nào:

```java
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.MessageHandlingException;
import org.springframework.messaging.support.GenericMessage;
import org.springframework.retry.support.RetryTemplate;
import static org.junit.jupiter.api.Assertions.assertEquals;

class WrappedCauseRetryTest {
    @Test
    void retriesWhenTemporaryFailureIsWrapped() {
        AtomicInteger calls = new AtomicInteger();
        var message = new GenericMessage<>("create-shipment");
        var template = RetryTemplate.builder()
                .maxAttempts(3)
                .noBackoff()
                .retryOn(ShippingRetryConfiguration.TemporaryCarrierException.class)
                .traversingCauses()
                .build();

        String result = template.execute(context -> {
            if (calls.incrementAndGet() < 3) {
                throw new MessageHandlingException(message,
                        new ShippingRetryConfiguration.TemporaryCarrierException(
                                "Temporary failure"));
            }
            return "OK";
        });

        assertEquals("OK", result);
        assertEquals(3, calls.get());
    }
}
```

Khi cần kiểm tra chính lịch exponential backoff, có thể dùng `ExponentialBackOffPolicy#setSleeper(...)` để ghi nhận các khoảng chờ mà không ngủ thật, rồi so sánh danh sách thu được với lịch mong đợi. Kiểm thử tải, timeout của client và transaction là các kiểm thử khác; các test đếm lượt ở trên không thay thế chúng.

## 13. API tương ứng trong Spring Integration 7.x

Mục này dùng **Spring Framework 7.x**, độc lập với các đoạn mã Spring Retry ở trên. Template mới có callback không nhận `RetryContext`; giới hạn số lượt nằm trong `RetryPolicy` và cấu hình là số lần thử thêm.

Ví dụ tối đa ba lần thực thi tổng cộng:

```java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.core.retry.RetryPolicy;
import org.springframework.core.retry.RetryTemplate;

public class FrameworkRetryExample {

    static class TemporaryCarrierException extends RuntimeException {}

    public static void main(String[] args) {
        RetryPolicy policy = RetryPolicy.builder()
                .maxRetries(2)
                .delay(Duration.ofMillis(100))
                .multiplier(2.0)
                .maxDelay(Duration.ofSeconds(1))
                .includes(TemporaryCarrierException.class)
                .build();

        RetryTemplate template = new RetryTemplate(policy);
        AtomicInteger calls = new AtomicInteger();

        String result = template.execute(() -> {
            if (calls.incrementAndGet() < 3) {
                throw new TemporaryCarrierException();
            }
            return "TRACK-A001";
        });

        System.out.println(result + ", calls=" + calls.get());
    }
}
```

Trong API này, `.maxRetries(2)` cho phép một lần đầu cộng hai lần thử thêm. Builder cũng có các tùy chọn `delay`, `multiplier`, `maxDelay` và bộ lọc exception; xem [RetryPolicy.Builder của Spring Framework 7](https://docs.spring.io/spring-framework/docs/7.0.x/javadoc-api/org/springframework/core/retry/RetryPolicy.Builder.html).

Nếu `execute(...)` không thành công, template mới ném `org.springframework.core.retry.RetryException`; lỗi của lần cuối nằm ở `cause`, các lỗi trước có thể nằm trong `suppressed exceptions`. Muốn recovery khi gọi trực tiếp, dùng `try/catch` tương ứng thay vì truyền `RecoveryCallback` của Spring Retry vào `execute`. Đây là hành vi của [RetryTemplate trong Spring Framework](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/retry/RetryTemplate.html).

Để áp dụng cùng policy cho một endpoint Integration 7.x:

```java
// policy là org.springframework.core.retry.RetryPolicy đã tạo ở trên.
var advice = new org.springframework.integration.handler.advice.RequestHandlerRetryAdvice();
advice.setRetryPolicy(policy);

// Đăng ký advice làm bean và gắn vào endpoint của IntegrationFlow:
// .handle(..., endpoint -> endpoint.advice(advice))
```

Không truyền `org.springframework.retry.support.RetryTemplate` hoặc gọi `setRetryTemplate(...)` trên advice của nhánh này. Khi chuyển ứng dụng, cần kiểm tra cả import, cách đếm lượt, loại exception cuối, recovery và stateful retry. API cụ thể được liệt kê trong [RequestHandlerRetryAdvice của Integration 7.x](https://docs.spring.io/spring-integration/api/org/springframework/integration/handler/advice/RequestHandlerRetryAdvice.html).

## 14. Bài tập áp dụng

1. Trong cấu hình 6.5, giảm `maxAttempts` từ `3` xuống `2`. Với client giả lập chưa thành công trước lượt thứ ba, xác định channel nhận kết quả và số lần gọi trước khi chạy thử.
2. Bỏ recovery khỏi advice và giữ nguyên `DirectChannel`. Gửi `DOWN-1`, kiểm tra exception mà bên gửi nhận được và chuỗi nguyên nhân của nó.
3. Thêm mã chống trùng ổn định vào yêu cầu. Mô phỏng đối tác đã tạo vận đơn nhưng client nhận timeout, rồi thiết kế cách lần thử tiếp theo lấy lại cùng vận đơn.
4. Đặt một bước gửi thông báo sau endpoint tạo vận đơn. Làm bước thông báo thất bại và kiểm tra xem lời gọi tạo vận đơn có thực sự nằm trong ranh giới retry của lỗi đó hay không.
5. Chuyển cấu hình sang Integration 7.x, giữ yêu cầu tối đa ba lần thực thi. Viết lại phần policy và kiểm thử để phát hiện việc vô tình tăng số lượt khi đổi `maxAttempts` sang `maxRetries`.

Với mỗi phương án, hãy giải thích được: thao tác nào được gọi lại, vì sao lỗi có thể phục hồi, tổng số request tối đa là bao nhiêu và yêu cầu sẽ đi đâu sau khi không còn thử tiếp. Đó là những quyết định làm cho retry trở thành một phần có thể kiểm soát của luồng thông điệp.
