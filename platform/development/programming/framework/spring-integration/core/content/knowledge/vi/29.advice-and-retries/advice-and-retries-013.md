# Retry từng lần xử lý hay toàn flow

Trong chương **Advice và retry** của **SPRING_INTEGRATION_CORE**, một quyết định quan trọng là chọn phần công việc sẽ được thực hiện lại sau lỗi. Một lần gọi dịch vụ, một endpoint và toàn bộ quy trình nghiệp vụ có thể có những ranh giới hoàn toàn khác nhau.

Giả sử luồng đặt hàng gồm ba bước:

~~~text
A: Kiểm tra đơn → B: Giữ hàng → C: Lưu kết quả
~~~

Nếu B gặp lỗi tạm thời, gọi lại riêng B có thể đủ. Nếu cần đọc lại dữ liệu và tính lại quyết định trước khi giữ hàng, ta có thể cần chạy lại A và B. Nếu C thất bại sau khi B đã giữ hàng thành công, chạy lại toàn bộ luồng có thể giữ hàng thêm lần nữa.

**Retry phải bao quanh đơn vị công việc có thể thực hiện lại an toàn và nhận biết được kết quả thành công hoặc thất bại.** Số lần thử và backoff chỉ có ý nghĩa sau khi ranh giới này đã rõ.

## 1. Mục tiêu và phạm vi ví dụ

Sau bài này, bạn có thể:

- Phân biệt retry cục bộ ở handler với gửi lại đầu vào của một đoạn flow.
- Giải thích vì sao lỗi downstream không tự làm handler phía trước chạy lại.
- Dùng Java DSL để đặt `RequestHandlerRetryAdvice` tại endpoint hoặc tại gateway gọi một flow con.
- Nhận diện ảnh hưởng của channel, recovery, transaction và side effect đến retry.
- Thiết kế kiểm thử kiểm đếm số lần gọi thay vì chỉ kiểm tra kết quả cuối.

Ví dụ Java trong bài dùng **Spring Integration 6.5.x, Spring Retry 2.x và Java 17 trở lên**. Các lớp retry thuộc package `org.springframework.retry.*`. Đây là lựa chọn phiên bản để trình bày một cấu hình nhất quán.

Spring Integration 7.x chuyển retry advice sang retry support của Spring Framework; cấu hình có các khác biệt như `setRetryPolicy(...)` thay cho `setRetryTemplate(...)`. Khi áp dụng vào dự án 7.x, cần chuyển cấu hình theo đúng API của phiên bản đó; nguyên tắc chọn ranh giới xử lý vẫn giữ nguyên. Xem [retry advice 6.5](https://docs.spring.io/spring-integration/reference/6.5/handler-advice/classes.html) và [retry advice 7.0](https://docs.spring.io/spring-integration/reference/7.0/handler-advice/classes.html).

## 2. Phân biệt attempt, retry và replay

Một **attempt** là một lần thực thi đơn vị được bảo vệ. Một **retry** là attempt bổ sung sau lần thất bại trước đó.

Với `SimpleRetryPolicy(3)` của Spring Retry, có tối đa **ba attempt tổng cộng**: lần đầu và hai lần thử lại. Không phải lần đầu cộng thêm ba retry. Quy ước này được mô tả trong [Javadoc SimpleRetryPolicy](https://docs.spring.io/spring-retry/docs/2.0.12/apidocs/org/springframework/retry/policy/SimpleRetryPolicy.html).

Trong bài, **replay flow** nghĩa là gửi lại đầu vào của đoạn flow đã chọn. Đây là cách tổ chức công việc của ứng dụng, không phải khả năng tự động khôi phục mọi endpoint về trạng thái ban đầu.

| Khái niệm | Đơn vị thực thi lại | Đầu vào của lần tiếp theo |
| --- | --- | --- |
| Retry handler | Công việc bên trong handler được advise | Message đang được xử lý tại handler đó |
| Retry đoạn flow qua gateway | Lần trao đổi request–reply với flow được gọi | Request tại ranh giới gateway |
| Broker redelivery | Phần xử lý bắt đầu từ consumer nhận lại message | Message do broker giao lại |
| Tiếp tục từ checkpoint | Các bước còn lại theo trạng thái nghiệp vụ đã lưu | Command hoặc dữ liệu được dựng từ checkpoint |

Cụm “retry từng lần xử lý” ở đây chỉ retry cho một lời gọi handler. Nó không có nghĩa một hệ thống chỉ có một message, cũng không quy định stateless hay stateful.

### Ví dụ về số lần gọi

Giả sử B thất bại hai lần rồi thành công; A và C luôn thành công.

~~~text
Retry tại B:
A → B lỗi → B lỗi → B thành công → C

Retry cả A–B–C:
A → B lỗi
A → B lỗi
A → B thành công → C
~~~

| Ranh giới retry | A được gọi | B được gọi | C được gọi |
| --- | ---: | ---: | ---: |
| Chỉ B | 1 | 3 | 1 |
| A–B–C | 3 | 3 | 1 |

C chỉ chạy sau khi B thành công nên chưa bị lặp trong ví dụ này. Nếu lỗi xảy ra ở C, replay cả đoạn sẽ gọi lại cả A và B dù hai bước đó đã hoàn tất.

## 3. Ranh giới của RequestHandlerRetryAdvice

Với một endpoint tạo reply thông thường, `RequestHandlerRetryAdvice` bao quanh phần xử lý request của handler. Sau khi handler trả về thành công, việc gửi output sang các endpoint tiếp theo nằm ngoài phạm vi retry cục bộ này. Tài liệu [Adding Behavior to Endpoints](https://docs.spring.io/spring-integration/reference/6.5/handler-advice.html) mô tả rõ giới hạn đó.

~~~mermaid
flowchart LR
    A["A: kiểm tra đơn"] --> B
    subgraph R["Retry cục bộ"]
        B["B: giữ hàng"]
        B -. "lỗi tạm thời" .-> B
    end
    B --> C["C: lưu kết quả"]
~~~

Ví dụ:

~~~java
.handle(orderService, "reserve",
        endpoint -> endpoint.advice(reserveRetry))
.handle(orderService, "persist")
~~~

Nếu `reserve` thất bại bằng một exception được policy chấp nhận, advice gọi lại `reserve`. Nếu `reserve` đã trả về nhưng `persist` ném lỗi, advice ở `reserve` không tự gọi lại `reserve`.

Điều này vẫn đúng khi các endpoint nối với nhau bằng `DirectChannel`. Cùng thread giúp exception lan ngược call stack; phạm vi method mà advice bao quanh mới quyết định exception có kích hoạt retry hay không.

Cũng cần nhìn vào phần thân handler:

~~~java
public OrderResult process(OrderRequest request) {
    OrderRequest validated = validate(request);
    OrderRequest reserved = reserve(validated);
    return persist(reserved);
}
~~~

Nếu advise method `process`, cả ba lời gọi bên trong nó thuộc một attempt. “Một handler” vẫn có thể chứa nhiều thao tác và nhiều side effect. Hãy xét công việc thực sự được bao quanh, thay vì chỉ đếm số dòng DSL.

### Những gì retry cục bộ không tự cung cấp

Retry advice không tự:

- Gửi lại message vào đầu flow.
- Hoàn tác thao tác HTTP, email hoặc thay đổi ở hệ thống ngoài.
- Tạo transaction mới cho mỗi attempt.
- Lưu checkpoint của các endpoint đã thành công.
- Lặp lại một lỗi xuất hiện sau khi method trả về `Future` hoặc publisher.

Nếu handler trả về một tác vụ bất đồng bộ đang chờ hoàn tất, retry đồng bộ có thể đã kết thúc trước khi tác vụ đó báo lỗi. Với xử lý reactive, cần đặt retry vào vòng đời publisher hoặc dùng cơ chế advice phù hợp.

## 4. Khi nào retry riêng handler phù hợp?

Retry cục bộ thường phù hợp khi một thao tác thất bại tạm thời và có thể gọi lại với đầu vào hiện tại.

Ví dụ:

- Gọi dịch vụ tra cứu có lúc trả lỗi do kết nối.
- Giữ hàng qua API hỗ trợ idempotency key.
- Ghi một bản ghi bằng thao tác upsert có ràng buộc duy nhất phù hợp.
- Gọi một service transaction mà mỗi lần gọi có thể bắt đầu lại đơn vị công việc cần thiết.

Nên kiểm tra bốn điều:

1. **Lỗi có khả năng hết không?** Payload sai định dạng thường không tự đúng lên sau 200 ms.
2. **Đầu vào còn hợp lệ không?** Giá hoặc tồn kho đã thay đổi có thể đòi hỏi tính lại từ bước trước.
3. **Kết quả lần trước có chắc chắn chưa xảy ra không?** Timeout thường khiến kết quả ở hệ thống ngoài chưa xác định.
4. **Thao tác có thể lặp an toàn không?** Retry cục bộ vẫn có thể tạo trùng side effect.

Giả sử bước giữ hàng nhận `idempotencyKey = "reserve:O-42"`. Mọi attempt cho cùng thao tác phải giữ nguyên khóa này. Nếu mỗi lần gọi lại sinh một UUID mới, dịch vụ ngoài có thể coi đó là những yêu cầu giữ hàng khác nhau.

Idempotency key là một phần của hợp đồng xử lý: phía nhận cần lưu và kiểm tra khóa một cách nguyên tử, xử lý yêu cầu đồng thời và trả lại kết quả phù hợp. Chỉ thêm một header ở phía gửi chưa đủ để bảo đảm chống trùng.

## 5. Dùng gateway để đặt ranh giới replay cho một đoạn flow

Khi cần thực hiện lại nhiều endpoint, có thể tách đoạn công việc thành flow request–reply và để gateway gọi đoạn đó. Đặt retry advice trên gateway làm cho **lần gọi đoạn flow** trở thành đơn vị retry.

~~~mermaid
flowchart LR
    IN["Đầu vào"] --> PRE["Chuẩn bị request"]
    PRE --> G
    subgraph R["Retry tại gateway"]
        G["Gateway gọi flow con"] --> A["A: kiểm tra"]
        A --> B["B: giữ hàng"]
        B --> C["C: lưu"]
        C --> REPLY["Reply"]
        REPLY --> G
    end
    G --> OUT["Xử lý sau gateway"]
~~~

Trong mỗi attempt, gateway gửi request tới đầu flow con và chờ kết quả. Nếu lỗi từ flow con được truyền lại tới gateway dưới dạng exception phù hợp với policy, lời gọi flow con có thể được thực hiện lại.

`GatewayEndpointSpec` hỗ trợ cấu hình advice, reply timeout và `errorOnTimeout`; xem [Javadoc GatewayEndpointSpec 6.5](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/GatewayEndpointSpec.html).

Để mô hình này đúng với ý định, cần xác định:

- **Điểm bắt đầu:** message được gửi lại vào channel nào.
- **Điểm kết thúc:** reply nào thể hiện đoạn công việc đã hoàn thành.
- **Đường truyền lỗi:** thất bại phải tới được gateway đang chờ.
- **Trạng thái đầu vào:** request dùng lại phải đủ thông tin và có semantics rõ ràng.
- **Tác động được phép lặp:** mọi bước có thể đã thành công trong attempt trước.

Các bước trước gateway và sau gateway không thuộc đoạn được replay. Nếu cần tính lại một giá trị, đưa bước tính đó vào flow con. Giá trị đã được tính và đóng gói trước gateway sẽ không tự được tính lại.

### Tái sử dụng request không tạo bản sao sâu

`Message` không cho sửa tùy ý tập header, nhưng payload có thể là một object mutable. Nếu attempt đầu sửa trực tiếp object này rồi thất bại, attempt sau có thể nhìn thấy trạng thái đã bị sửa.

Ví dụ dùng `record` với dữ liệu bất biến để tránh vấn đề này. Với payload phức tạp, ưu tiên biến đổi tạo object mới hoặc dựng lại command từ dữ liệu gốc có kiểm soát. Không giả định gateway tự khôi phục object về trạng thái trước lần gọi đầu tiên.

## 6. Ví dụ Java DSL: so sánh hai ranh giới bằng bộ đếm

Ví dụ sau cung cấp hai đường vào độc lập:

- `endpointRetry.input`: chỉ retry bước giữ hàng.
- `flowRetry.input`: retry gateway gọi cả ba bước.

Dịch vụ giả lập làm bước giữ hàng lỗi hai lần đầu. Mỗi lần mở application context mới có bộ đếm và trạng thái lỗi mới. Đây là ví dụ quan sát ranh giới gọi lại, chưa mô phỏng lưu trữ bền vững hay một API giữ hàng thật.

Cần có `spring-integration-core`, `spring-retry` và các dependency Spring tương thích. Các kiểm thử ở phần sau dùng JUnit Jupiter. Không cần bật `@EnableRetry` cho ví dụ này vì advice được gắn trực tiếp vào endpoint.

### 6.1. Cấu hình và dịch vụ giả lập

~~~java
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;

@Configuration
@EnableIntegration
public class RetryScopeConfiguration {

    public record OrderRequest(String orderId) {
    }

    public record OrderResult(String orderId, String status) {
    }

    public static class TemporaryInventoryException extends RuntimeException {
        public TemporaryInventoryException(String message) {
            super(message);
        }
    }

    public static class DemoOrderService {
        private final AtomicInteger validationCalls = new AtomicInteger();
        private final AtomicInteger reservationCalls = new AtomicInteger();
        private final AtomicInteger persistenceCalls = new AtomicInteger();
        private final AtomicInteger failuresRemaining = new AtomicInteger(2);

        public OrderRequest validate(OrderRequest request) {
            validationCalls.incrementAndGet();
            if (request.orderId() == null || request.orderId().isBlank()) {
                throw new IllegalArgumentException("orderId must not be blank");
            }
            return request;
        }

        public OrderRequest reserve(OrderRequest request) {
            reservationCalls.incrementAndGet();
            int remaining = failuresRemaining.getAndUpdate(
                    value -> Math.max(0, value - 1));

            if (remaining > 0) {
                // Lỗi được giả lập trước side effect giữ hàng.
                throw new TemporaryInventoryException(
                        "Inventory temporarily unavailable");
            }
            return request;
        }

        public OrderResult persist(OrderRequest request) {
            persistenceCalls.incrementAndGet();
            return new OrderResult(request.orderId(), "ACCEPTED");
        }

        public int validationCalls() {
            return validationCalls.get();
        }

        public int reservationCalls() {
            return reservationCalls.get();
        }

        public int persistenceCalls() {
            return persistenceCalls.get();
        }
    }

    @Bean
    DemoOrderService orderService() {
        return new DemoOrderService();
    }

    @Bean
    RequestHandlerRetryAdvice reserveRetry() {
        return newRetryAdvice();
    }

    @Bean
    RequestHandlerRetryAdvice flowRetry() {
        return newRetryAdvice();
    }

    private static RequestHandlerRetryAdvice newRetryAdvice() {
        Map<Class<? extends Throwable>, Boolean> retryable = Map.of(
                TemporaryInventoryException.class, true);

        SimpleRetryPolicy policy = new SimpleRetryPolicy(
                3, retryable, true, false);

        ExponentialBackOffPolicy backOff = new ExponentialBackOffPolicy();
        backOff.setInitialInterval(100L);
        backOff.setMultiplier(2.0);
        backOff.setMaxInterval(1_000L);

        RetryTemplate template = new RetryTemplate();
        template.setRetryPolicy(policy);
        template.setBackOffPolicy(backOff);

        RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
        advice.setRetryTemplate(template);
        return advice;
    }

    @Bean
    IntegrationFlow endpointRetryFlow(
            DemoOrderService service,
            @Qualifier("reserveRetry") RequestHandlerRetryAdvice retry) {

        return IntegrationFlow.from("endpointRetry.input")
                .handle(service, "validate")
                .handle(service, "reserve", endpoint -> endpoint.advice(retry))
                .handle(service, "persist")
                .get();
    }

    @Bean
    IntegrationFlow replayBodyFlow(DemoOrderService service) {
        return IntegrationFlow.from("replayBody.input")
                .handle(service, "validate")
                .handle(service, "reserve")
                .handle(service, "persist")
                .get();
    }

    @Bean
    IntegrationFlow flowRetryFlow(
            @Qualifier("flowRetry") RequestHandlerRetryAdvice retry) {

        return IntegrationFlow.from("flowRetry.input")
                .gateway("replayBody.input", gateway -> gateway
                        .advice(retry)
                        .replyTimeout(5_000L)
                        .errorOnTimeout(true))
                .get();
    }
}
~~~

Các channel do DSL tạo trong ví dụ là channel đồng bộ mặc định; không có queue, executor hoặc nhánh xử lý song song. `persist` trả về `OrderResult` nên đoạn được gọi qua gateway có reply.

Hai advice có policy riêng để hai cấu hình dễ phân biệt. Không có retry cục bộ bên trong `replayBodyFlow`; số lần gọi ở đường replay vì vậy không bị nhân bởi retry lồng nhau.

### 6.2. Đọc cấu hình policy

Đối với constructor:

~~~java
new SimpleRetryPolicy(3, retryable, true, false)
~~~

Ý nghĩa lần lượt là:

| Thành phần | Ý nghĩa trong ví dụ |
| --- | --- |
| `3` | Tối đa ba attempt tổng cộng |
| `retryable` | Cho retry `TemporaryInventoryException` và lớp con |
| `true` | Tìm exception phù hợp trong cause chain |
| `false` | Exception không khớp mặc định không được retry |

Cause traversal cần thiết vì exception nghiệp vụ có thể được bọc trong `MessagingException`. `RequestHandlerRetryAdvice` cũng nêu yêu cầu này trong [Javadoc setRetryTemplate](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/handler/advice/RequestHandlerRetryAdvice.html).

Trong ví dụ, khoảng chờ trước hai retry là 100 ms và 200 ms. Backoff này chiếm thread đang xử lý trong thời gian chờ. Khi triển khai thực tế, cần đặt ngân sách thời gian và cân nhắc jitter để nhiều request không thử lại đồng loạt.

Policy không cho retry `IllegalArgumentException`. Nếu `orderId` rỗng, lỗi kiểm tra đầu vào sẽ kết thúc lần xử lý mà không lặp lại đoạn flow.

### 6.3. Kiểm thử số lần gọi

Đặt kiểm thử trong cùng package với cấu hình. Mỗi test tạo context mới để hai lỗi giả lập ban đầu không bị test khác tiêu thụ.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.core.MessagingTemplate;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class RetryScopeTest {

    @Test
    void endpointRetryRepeatsOnlyReservation() {
        assertCounts("endpointRetry.input", 1, 3, 1);
    }

    @Test
    void gatewayRetryReplaysTheSelectedFlow() {
        assertCounts("flowRetry.input", 3, 3, 1);
    }

    private void assertCounts(
            String channelName, int validation, int reservation, int persistence) {

        try (var context = new AnnotationConfigApplicationContext(
                RetryScopeConfiguration.class)) {

            MessagingTemplate template = new MessagingTemplate();
            template.setReceiveTimeout(5_000L);

            Message<?> reply = template.sendAndReceive(
                    context.getBean(channelName, MessageChannel.class),
                    MessageBuilder.withPayload(
                            new RetryScopeConfiguration.OrderRequest("O-42"))
                            .build());

            assertNotNull(reply);
            assertEquals(
                    new RetryScopeConfiguration.OrderResult("O-42", "ACCEPTED"),
                    reply.getPayload());

            var service = context.getBean(
                    RetryScopeConfiguration.DemoOrderService.class);
            assertEquals(validation, service.validationCalls());
            assertEquals(reservation, service.reservationCalls());
            assertEquals(persistence, service.persistenceCalls());
        }
    }
}
~~~

Kết quả mong đợi:

~~~text
endpointRetry.input: validation=1, reservation=3, persistence=1
flowRetry.input:     validation=3, reservation=3, persistence=1
~~~

Đếm số lần gọi giúp phát hiện việc replay một bước đã thành công. Chỉ assert `OrderResult("O-42", "ACCEPTED")` sẽ không phân biệt được hai chiến lược.

Các đoạn mã này là tài liệu thực hành với kết quả kỳ vọng; bài không khẳng định chúng đã được thực thi trong môi trường dự án của người đọc.

## 7. Channel và đường truyền lỗi quyết định retry có nhìn thấy thất bại không

Một retry chỉ phản ứng với lỗi mà nó quan sát được trong thời gian đơn vị công việc còn đang thực thi.

### 7.1. DirectChannel

`DirectChannel` chuyển message tới handler trên thread gửi. Một lời gọi đồng bộ tới flow con có thể bao gồm toàn bộ các handler phía sau cho đến khi có reply hoặc exception. Đây là cơ sở của ví dụ gateway ở trên. Xem [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/6.5/channel/implementations.html).

Tuy vậy, cùng thread không tự mở rộng phạm vi của `RequestHandlerRetryAdvice` đặt trên một handler thông thường. Để retry nhiều bước, ví dụ đã dùng gateway làm đơn vị gọi bao ngoài các bước đó.

### 7.2. QueueChannel và ExecutorChannel

Xét trường hợp:

~~~text
Producer → QueueChannel → Worker xử lý → Ghi dữ liệu
~~~

Nếu producer chỉ gửi một chiều, việc `send(...)` thành công có thể chỉ cho biết message đã được đưa vào queue. Worker thất bại về sau không tự biến lần gửi trước đó thành thất bại.

Với xử lý trên thread khác, lỗi thường đi bằng `ErrorMessage` tới error channel theo cấu hình. Không thể dựa vào exception Java lan ngược về một producer đã kết thúc lời gọi. Đây là khác biệt được giải thích trong [Error Handling](https://docs.spring.io/spring-integration/reference/6.5/error-handling.html).

Có hai cách tổ chức thường gặp:

- Retry ngay tại worker, nơi thao tác thực tế xảy ra.
- Giữ hợp đồng request–reply, để gateway còn chờ và nhận lỗi của worker thông qua cơ chế truyền lỗi tương ứng.

Vì vậy, có channel bất đồng bộ không đồng nghĩa gateway tuyệt đối không thể thấy lỗi. Điều cần xác minh là gateway có còn chờ không, error channel có đưa lỗi về đúng lời gọi không và có thành phần nào chuyển lỗi thành kết quả bình thường không.

Không dựa vào retry của producer gửi một chiều để bảo đảm hoàn thành công việc ở worker. Nếu cần trì hoãn retry lâu hoặc giữ việc xử lý qua restart, thiết kế redelivery và lưu trữ bền vững thay vì chỉ chặn thread bằng backoff.

### 7.3. Timeout không chứng minh thao tác chưa thành công

Ở gateway, `replyTimeout` giới hạn thời gian chờ reply trong những tình huống phù hợp. Nó không phải timeout có thể ngắt một handler đồng bộ đang chạy trên cùng thread. Cần cấu hình timeout riêng cho HTTP client, JDBC hoặc thao tác bên trong handler. Xem [Gateway Behavior When No Response Arrives](https://docs.spring.io/spring-integration/reference/6.5/gateway.html#gateway-behavior-no-response).

Trong ví dụ:

~~~java
.replyTimeout(5_000L)
.errorOnTimeout(true)
~~~

`errorOnTimeout(true)` giúp thiếu reply trở thành lỗi thay vì một kết quả `null`. Policy mẫu chỉ cho retry `TemporaryInventoryException`, nên cấu hình này **không tự cho retry lỗi timeout**.

Nếu muốn retry timeout, cần thêm phân loại exception phù hợp và đánh giá side effect trước. Một worker có thể đã ghi dữ liệu nhưng reply đến muộn; attempt mới có thể chạy trong khi attempt cũ vẫn tiếp tục. Timeout không hủy công việc cũ và không tạo rollback ở hệ thống ngoài.

## 8. Recovery có thể chấm dứt retry ở ranh giới bên ngoài

Xét một cấu trúc có hai mức:

~~~text
Retry ngoài → Gateway → Handler có retry trong → Recovery
~~~

Nếu retry trong hết lượt và recovery trả về một giá trị fallback hợp lệ, gateway có thể coi đó là reply thành công. Retry ngoài không nhìn thấy exception nên không có lý do thử lại.

Tương tự, error flow của gateway có thể chuyển exception thành một response bình thường. Hành vi chuyển lỗi thành reply được hỗ trợ bởi [Messaging Gateways — Error Handling](https://docs.spring.io/spring-integration/reference/6.5/gateway.html).

Khi thiết kế nhiều mức retry, hãy quyết định rõ một trong các kết quả:

| Kết quả sau khi retry cục bộ kết thúc | Mức ngoài quan sát được | Hệ quả |
| --- | --- | --- |
| Exception tiếp tục được ném | Thất bại | Có thể retry nếu policy mức ngoài chấp nhận |
| Fallback hợp lệ | Reply bình thường | Không kích hoạt retry dựa trên exception |
| Chuyển lỗi sang kênh khác, không tạo reply | Thiếu reply | Có thể chờ tới timeout |
| Kết quả nghiệp vụ như `REJECTED` | Reply bình thường | Ứng dụng phải xử lý theo hợp đồng nghiệp vụ |

Một payload có `status = "FAILED"` không tự được hiểu là exception. Nếu cần thử lại theo nội dung kết quả, hãy thiết kế cơ chế kiểm tra kết quả rõ ràng.

Gửi `ErrorMessage` để lưu dấu vết cũng chưa bảo đảm request–reply đã có kết quả cuối đúng kiểu. Cần phân biệt đường báo lỗi phục vụ vận hành với response mà caller đang chờ.

## 9. Retry, transaction và redelivery là ba vấn đề riêng

### 9.1. Retry không đồng nghĩa rollback

Giả sử attempt đầu thực hiện:

~~~text
Giữ hàng qua HTTP thành công
→ Ghi database thất bại
→ Retry toàn đoạn
~~~

Rollback database không tự giải phóng phần hàng đã giữ qua HTTP. Nếu replay cả đoạn, thao tác giữ hàng cần có idempotency hoặc có quy trình bù phù hợp.

Với nhiều hệ thống độc lập, có thể cần lưu trạng thái nghiệp vụ, outbox hoặc saga để điều phối việc tiếp tục và bù. Retry chỉ là một công cụ trong thiết kế đó.

### 9.2. Mỗi attempt có transaction nào?

Hai cấu trúc sau có ý nghĩa khác nhau:

~~~text
Retry bao ngoài:
Retry → Transaction mới cho attempt → Công việc → commit hoặc rollback

Transaction bao ngoài:
Transaction chung → Retry → nhiều attempt trong transaction đó
~~~

Trong cấu trúc thứ hai, một lỗi có thể khiến transaction bị đánh dấu rollback-only. Một attempt sau trả về thành công không tự xóa dấu này; lỗi khi commit còn có thể xảy ra sau khi retry bên trong đã kết thúc.

Nếu cần transaction độc lập cho mỗi attempt, hãy tổ chức lời gọi qua service Spring được proxy hoặc `TransactionTemplate` với propagation phù hợp. Cần kiểm tra cả thứ tự interceptor và transaction đang có từ caller; việc thêm `@Transactional` đơn thuần không bảo đảm luôn tạo transaction mới.

Ngữ cảnh transaction thông thường gắn với thread. Đổi sang executor hoặc queue không tự mang transaction đó sang worker. Tham khảo [Transaction Support](https://docs.spring.io/spring-integration/reference/6.5/transactions.html).

### 9.3. Stateless, stateful và phạm vi replay

| Chiều thiết kế | Câu hỏi cần trả lời |
| --- | --- |
| Phạm vi retry | Gọi lại một handler hay nhiều bước? |
| Stateless hoặc stateful | Các attempt diễn ra trong cùng lời gọi hay qua nhiều lần gửi lại? |
| Transaction | Thao tác nào cùng commit hoặc rollback? |
| Delivery | Ai giữ message và quyết định giao lại? |
| Khôi phục nghiệp vụ | Có tiếp tục từ trạng thái đã lưu không? |

Ví dụ chính dùng stateless retry: advice tự thử lại trong lời gọi hiện tại.

Stateful retry duy trì trạng thái retry qua các lần gửi lại và có thể ném lỗi để nguồn message thực hiện redelivery. Nó không tự tạo checkpoint cho từng endpoint. Trong Spring Integration 6.5, cấu hình stateful sử dụng `RetryStateGenerator`; xem [RequestHandlerRetryAdvice](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/handler/advice/RequestHandlerRetryAdvice.html).

Broker giao lại message thường làm consumer chạy lại từ đầu ranh giới nhận message. Nếu consumer thực hiện A–B–C, A và B vẫn có thể được gọi lại. Muốn tiếp tục từ C, ứng dụng cần lưu và kiểm tra trạng thái một cách chủ động.

`QueueChannel` lưu trong bộ nhớ theo cấu hình mặc định không tự cung cấp semantics redelivery và durability giống một broker bền vững.

## 10. Side effect và retry lồng nhau

### 10.1. Chọn khóa theo thao tác nghiệp vụ

Với đơn `O-42`, các thao tác khác nhau có thể dùng:

~~~text
reserve:O-42:v1
persist:O-42:v1
notify:O-42:accepted:v1
~~~

Một khóa phải ổn định qua các attempt của cùng thao tác. Khi nội dung yêu cầu nghiệp vụ thay đổi thực sự, cần quy tắc version hoặc command mới, thay vì tái sử dụng tùy tiện khóa cũ.

Không mặc định dùng `MessageHeaders.ID` làm idempotency key xuyên suốt hệ thống: khi dựng message mới hoặc chuyển qua transport khác, ID có thể thay đổi. Command ID hoặc operation ID nghiệp vụ thường diễn tả mục tiêu chống trùng rõ hơn.

Với thao tác ghi database, một kiểm tra `exists` rồi `insert` tách rời vẫn có race condition. Ràng buộc duy nhất, transaction và cách trả lại kết quả cũ phải cùng bảo vệ semantics chống trùng.

### 10.2. Retry nhiều tầng có thể nhân số lần gọi

Giả sử:

- Gateway ngoài thực hiện tối đa 3 attempt.
- Handler giữ hàng bên trong thực hiện tối đa 3 attempt cho mỗi lần gateway gọi.
- Mỗi lần handler được gọi, HTTP client cũng thử tối đa 2 lần.

Nếu lỗi tiếp tục đủ lâu và mỗi tầng đều cho phép thử lại, số request HTTP có thể lên tới:

~~~text
3 × 3 × 2 = 18
~~~

Đây là giới hạn trong giả định trên; kết quả thực tế phụ thuộc điểm lỗi, recovery và tầng nào ngừng trước.

Chưa kể broker có thể giao lại message sau khi toàn bộ xử lý này thất bại. Vì vậy, cần xác định tầng chịu trách nhiệm chính cho retry của từng loại lỗi.

Có thể dùng retry ngắn tại thao tác từ xa và redelivery có trì hoãn ở mức message cho lỗi kéo dài. Tổng số lần gọi, thời gian chờ và giới hạn tải vẫn phải được tính cho toàn bộ các tầng.

### 10.3. Tính ngân sách thời gian cho đơn vị được retry

Nếu một attempt của **đơn vị đang được bảo vệ** mất tối đa 800 ms, có ba attempt và hai khoảng backoff 100 ms, 200 ms:

~~~text
Thời gian xấp xỉ tối đa = 3 × 800 + 100 + 200 = 2.700 ms
~~~

Nếu đơn vị là cả flow, 800 ms phải bao gồm công việc trong cả đoạn đó. Không lấy timeout của riêng B thay cho thời gian tối đa của A–B–C.

Đây là phép tính ngân sách theo giả định, chưa bao gồm thời gian xếp hàng, lập lịch, serialize, recovery hoặc retry lồng nhau. Với thao tác chưa có timeout hữu hiệu, không thể suy ra giới hạn thời gian chỉ từ `maxAttempts`.

## 11. Chọn ranh giới trong các tình huống thực tế

Bảng sau là gợi ý thiết kế rút ra từ các ranh giới đã phân tích; mỗi lựa chọn còn phụ thuộc hợp đồng của hệ thống tham gia.

| Tình huống | Hướng xử lý ban đầu | Điều kiện cần xác minh |
| --- | --- | --- |
| API tra cứu lỗi kết nối ngắn hạn | Retry handler gọi API | Timeout hữu hiệu và giới hạn tải |
| Giữ hàng qua API có idempotency | Retry handler giữ hàng | Khóa ổn định và semantics phía nhận |
| Tính quyết định rồi ghi dữ liệu, cần tính lại sau xung đột | Retry cả đơn vị đọc–tính–ghi | Mỗi attempt có trạng thái và transaction phù hợp |
| Đã thu tiền, bước gửi thông báo thất bại | Retry bước thông báo hoặc tiếp tục từ trạng thái đã lưu | Không vô tình thu tiền lại |
| Message đã đưa vào queue, worker thất bại sau đó | Retry tại worker hoặc redelivery | Ack, đường lỗi và durability |
| Lỗi dữ liệu đầu vào | Trả lỗi hoặc chuyển luồng xử lý dữ liệu lỗi | Retry không sửa được nội dung |
| Flow có splitter và aggregator | Chọn retry từng nhánh hoặc thiết kế replay có kiểm soát | Trùng phần tử, correlation, release và trạng thái group |
| Lỗi kéo dài nhiều phút | Redelivery có trì hoãn hoặc cơ chế lập lịch bền vững | Giới hạn attempt, đường kết thúc lỗi và vận hành |

Với splitter–aggregator, replay request có thể sinh thêm các phần tử trong khi group của attempt trước chưa hết hạn. Không mở rộng ví dụ tuyến tính thành replay flow phân nhánh nếu chưa xác định cách cô lập hoặc khử trùng giữa các attempt.

Một điểm khởi đầu hữu ích là đặt retry sát thao tác có thể thất bại độc lập. Mở rộng sang nhiều bước khi nghiệp vụ thực sự cần tính lại hoặc thực hiện lại cả đơn vị đó và các side effect đã được kiểm soát.

## 12. Mở rộng thực hành để phát hiện chọn sai phạm vi

Sau khi đối chiếu hai kiểm thử mẫu, có thể mở rộng dịch vụ giả lập với các tình huống sau. Mỗi test nên tạo trạng thái đầu vào riêng và kiểm tra cả số lần gọi lẫn kết quả nghiệp vụ.

| Tình huống thử | Quan sát cần có |
| --- | --- |
| B lỗi hai lần rồi thành công, retry tại B | A=1, B=3, C=1 |
| B lỗi hai lần rồi thành công, retry tại gateway | A=3, B=3, C=1 |
| B luôn lỗi, ngân sách ba attempt | C không được gọi; lỗi cuối tới caller nếu không recovery |
| A phát hiện dữ liệu không hợp lệ | Không replay theo policy mẫu; B và C không được gọi |
| B thành công, C lỗi tạm thời; chỉ B có advice | B không chạy lại chỉ vì C lỗi |
| B thành công, C lỗi một lần; retry gateway cho phép lỗi đó | A, B, C có thể đều chạy hai lần |
| B hoàn tất side effect nhưng caller mất reply | Nhiều lời gọi vẫn chỉ tạo một hiệu lực nghiệp vụ nhờ idempotency |
| Recovery trong trả fallback | Retry ngoài không chạy lại theo exception |
| Payload bị sửa trong attempt đầu | Phát hiện attempt sau nhận dữ liệu đã bị thay đổi |
| Worker còn chạy sau khi gateway timeout | Xác minh hành vi khi attempt cũ và mới chồng lấn |

Đối với idempotency, hai assertion cần tách biệt:

~~~text
Số lần gọi reserve = 3
Số lượt giữ hàng có hiệu lực = 1
~~~

Bộ đếm gọi method không thể tự chứng minh side effect chỉ xảy ra một lần. Cần có kho giả lập theo operation ID hoặc tích hợp với phía nhận để kiểm tra hiệu lực thực tế.

Khi quan sát hệ thống, nên ghi operation ID, endpoint, phạm vi retry, số attempt, exception cuối và thời gian đã dùng. Operation ID và correlation ID giúp liên kết các lần thử; không nên đưa các ID có số lượng giá trị rất lớn thành nhãn metric.

Nếu thấy bước thanh toán chạy lại sau lỗi gửi email, hãy lần theo gateway, listener, poller hoặc tầng gọi bên ngoài đang replay cả quy trình. Tăng backoff không sửa được ranh giới retry sai.
