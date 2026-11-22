# RecoveryCallback

## 1. Mục tiêu và bối cảnh

Trong chương **Advice và retry** của module **SPRING_INTEGRATION_CORE**, `RecoveryCallback` giúp xác định cách một endpoint kết thúc khi thao tác được retry vẫn thất bại. Kiến thức này nối `Message`, `MessageChannel`, endpoint và gateway thành một luồng có hành vi rõ ràng cả khi thành công lẫn khi gặp lỗi.

Sau bài học, bạn có thể:

- Phân biệt nhiệm vụ của retry policy và recovery callback.
- Lấy message liên quan đến lỗi để xây dựng kết quả thay thế hoặc bản ghi cần xử lý lại.
- Gắn recovery vào `RequestHandlerRetryAdvice` bằng Java DSL.
- Chọn giữa trả lời gateway, chuyển lỗi sang recovery channel và tiếp tục báo lỗi.
- Xác định những điều cần kiểm thử về số lần gọi, kiểu phản hồi và đường đi của lỗi.

**Phạm vi phiên bản:** ví dụ chính dùng **Spring Integration 7.0 và Spring Framework 7.0, Java 17 trở lên**. Mục 10 trình bày API của **Spring Integration 6.x kết hợp Spring Retry 2.x**. Từ Spring Integration 7.0, cơ chế retry chuyển sang Spring Framework Core; `RecoveryCallback` cũng đổi package và chữ ký. Không trộn hai nhóm import trong cùng một cấu hình. [Thay đổi của Spring Integration 7.0](https://docs.spring.io/spring-integration/reference/7.0/whats-new.html).

## 2. Retry kết thúc rồi thì message đi đâu?

Giả sử hệ thống nhận yêu cầu lấy giá từ một đối tác. Endpoint gọi dịch vụ đối tác, nhưng dịch vụ đang tạm thời không sẵn sàng. Với một lần gọi đầu và hai lần retry, có hai hướng kết thúc:

1. Một lần gọi thành công: endpoint trả giá nhận được; recovery không chạy.
2. Không thể gọi tiếp theo policy: hệ thống cần quyết định trả trạng thái không có giá, chuyển lỗi để xử lý sau, hoặc báo thất bại cho bên gọi.

`RecoveryCallback` biểu diễn quyết định ở bước thứ hai. Callback này không làm cho thao tác nghiệp vụ ban đầu tự thành công. Nó thực hiện một hành động khác đã được thiết kế trước.

~~~mermaid
flowchart TD
    A["Message đầu vào"] --> B["Endpoint có retry advice"]
    B --> C["Gọi handler"]
    C -->|Thành công| D["Kết quả nghiệp vụ"]
    C -->|Thất bại| E{"Policy còn cho retry?"}
    E -->|Có| F["Backoff nếu được cấu hình"]
    F --> C
    E -->|Không| G{"Có recovery callback?"}
    G -->|Không| H["Lỗi truyền ra khỏi advice"]
    G -->|Có| I["RecoveryCallback"]
    I --> J["Trả kết quả thay thế"]
    I --> K["Gửi ErrorMessage rồi kết thúc"]
    I --> L["Ném lỗi tiếp"]
~~~

Đây là mô hình của **stateless retry** trong bài. Với **stateful retry**, các lần thử có thể nằm ở nhiều lượt giao lại message; recovery không nhất thiết diễn ra ngay trong lượt nhận đầu tiên. `RequestHandlerRetryAdvice` hỗ trợ cả hai kiểu, nhưng các ví dụ dưới đây không bật stateful retry. [Retry advice của Spring Integration](https://docs.spring.io/spring-integration/reference/7.0/handler-advice/classes.html).

### 2.1. Các thành phần có trách nhiệm khác nhau

| Thành phần | Câu hỏi nó trả lời |
|---|---|
| Retry policy | Lỗi nào được thử lại và có thể thử lại bao nhiêu lần? |
| Backoff | Chờ bao lâu trước lần thử tiếp theo? |
| `RecoveryCallback` | Làm gì khi retry kết thúc với lỗi? |
| `RetryListener` | Quan sát những sự kiện nào trong vòng retry? |
| Error flow | Xử lý `ErrorMessage` đã được gửi đến channel nào? |

Recovery callback không thay thế router, filter hay transformer. Tuy nhiên, kết quả recovery có thể được router phân nhánh; lỗi chuyển sang recovery channel có thể được transformer chuyển thành bản ghi sự cố.

### 2.2. Không phải lúc nào cũng đủ số lần thử mới recovery

Policy có thể từ chối retry ngay sau lỗi đầu tiên vì lỗi đó không nằm trong danh sách cho phép. Với stateless retry ở Spring Integration 7.0, khi `RetryTemplate` kết thúc bằng `RetryException`, advice gọi recovery nếu đã cấu hình.

Vì vậy, callback không được suy luận rằng “đã gọi recovery thì chắc chắn đã thử đủ ba lần” hoặc “đây chắc chắn là lỗi tạm thời”. Chính callback cần phân loại lỗi trước khi quyết định trả fallback. [Mã nguồn retry template 7.0](https://github.com/spring-projects/spring-framework/blob/v7.0.0/spring-core/src/main/java/org/springframework/core/retry/RetryTemplate.java).

## 3. Hợp đồng RecoveryCallback trong Spring Integration 7.0

Dạng rút gọn của interface:

~~~java
package org.springframework.integration.core;

public interface RecoveryCallback<T> {
    T recover(
            org.springframework.core.AttributeAccessor context,
            Throwable cause);
}
~~~

Hai tham số có ý nghĩa:

- `context` chứa các thuộc tính liên quan đến lần xử lý thất bại, chẳng hạn message đầu vào.
- `cause` là lỗi được advice chuyển cho callback. Không nên mặc định đây là exception nghiệp vụ nằm ở lớp sâu nhất.

Giá trị trả về có thể thay cho kết quả của thao tác đã thất bại. Đây là lý do callback có thể tạo phản hồi cho gateway. Interface này không phải `org.springframework.retry.RecoveryCallback` của Spring Retry. [Javadoc RecoveryCallback 7.0](https://docs.spring.io/spring-integration/docs/7.0.0/api/org/springframework/integration/core/RecoveryCallback.html).

### 3.1. Lấy message từ context

Khi dùng với `RequestHandlerRetryAdvice` 7.0, có thể lấy message bằng hằng số của framework:

~~~java
Object candidate = context.getAttribute(
        ErrorMessageUtils.FAILED_MESSAGE_CONTEXT_KEY);

if (!(candidate instanceof Message<?> failedMessage)) {
    throw new IllegalStateException(
            "Recovery thiếu message cần xử lý", cause);
}
~~~

Các import cần có:

~~~java
import org.springframework.integration.support.ErrorMessageUtils;
import org.springframework.messaging.Message;
~~~

Dùng hằng số thay cho việc viết chuỗi `"message"`. `INPUT_MESSAGE_CONTEXT_KEY` và `FAILED_MESSAGE_CONTEXT_KEY` có vai trò riêng; trong advice 7.0, context được tạo từ message đang được advice xử lý cho cả hai vị trí. “Message đầu vào” ở đây là đầu vào của endpoint đó, không nhất thiết là message ở đầu toàn bộ pipeline sau các transformer hoặc splitter. [Mã nguồn ErrorMessageUtils](https://github.com/spring-projects/spring-integration/blob/v7.0.0/spring-integration-core/src/main/java/org/springframework/integration/support/ErrorMessageUtils.java), [mã nguồn RequestHandlerRetryAdvice](https://github.com/spring-projects/spring-integration/blob/v7.0.0/spring-integration-core/src/main/java/org/springframework/integration/handler/advice/RequestHandlerRetryAdvice.java).

### 3.2. Đọc nguyên nhân mà vẫn giữ đủ thông tin lỗi

Trong advice 7.0, callback nhận `RetryException` khi retry template kết thúc bằng lỗi. Exception đó có thể chứa exception cuối cùng và một chuỗi nguyên nhân bên dưới; handler cũng có thể đã bọc lỗi nghiệp vụ trong `MessagingException`.

Khi cần phân loại, hãy kiểm tra chuỗi nguyên nhân. Khi lưu hoặc truyền lỗi, nên giữ exception được nhận thay vì chỉ giữ chuỗi `getMessage()`, để còn stack trace và ngữ cảnh. Không ép kiểu trực tiếp `cause` thành exception nghiệp vụ.

## 4. Chọn kết quả recovery theo hợp đồng của luồng

| Cách kết thúc callback | Hành vi cần hiểu | Tình huống phù hợp |
|---|---|---|
| Trả một object khác `null` | Object trở thành kết quả của lời gọi handler được advice bao quanh | Gateway cần một phản hồi nghiệp vụ có kiểu rõ ràng |
| Trả một `Message<?>` | Có thể chủ động đặt payload và các header cần thiết | Luồng cần thêm dấu hiệu như `recovered=true` |
| Trả `null` | Không tạo phản hồi từ endpoint này | Luồng một chiều hoặc luồng có chủ đích kết thúc tại đó |
| Ném runtime exception | Recovery cũng thất bại; lỗi tiếp tục truyền ra ngoài | Không có fallback hợp lệ hoặc không ghi được bản ghi phục hồi |

Với endpoint sinh reply, kết quả khác `null` được gửi theo cấu hình output channel hoặc `replyChannel` của request. Kết quả `null` có thể làm luồng dừng; nếu endpoint yêu cầu reply thì có thể phát sinh `ReplyRequiredException`. [Hành vi của service activator](https://docs.spring.io/spring-integration/reference/7.0/service-activator.html).

### 4.1. Fallback phải thể hiện đúng trạng thái nghiệp vụ

Một API lấy giá có thể trả:

~~~json
{
  "requestId": "quote-001",
  "state": "UNAVAILABLE",
  "price": null
}
~~~

Trạng thái này cho biết hệ thống chưa lấy được giá. Không dùng giá `0` hoặc trạng thái `OK` để che lỗi. Nếu dùng giá cache, cần phân biệt kết quả cache với giá mới nhận từ đối tác.

Nếu một luồng aggregator đang chờ phản hồi của từng phần tử sau splitter, fallback có kiểu rõ ràng có thể giúp mỗi phần tử đều có kết quả để tập hợp. Việc trả `null` cho một phần tử có thể khiến group chờ đến timeout. Khi tự dựng `Message` mới, phải cân nhắc giữ các header tương quan, số thứ tự và thông tin trả lời cần thiết.

### 4.2. Gửi lỗi không đồng nghĩa đã trả lời gateway

`ErrorMessageSendingRecoverer` gửi lỗi rồi trả `null` khi việc gửi hoàn tất. Nó không tự tạo `QuoteResult` hoặc phản hồi khác theo kiểu khai báo của gateway. [Mã nguồn ErrorMessageSendingRecoverer 7.0](https://github.com/spring-projects/spring-integration/blob/v7.0.0/spring-integration-core/src/main/java/org/springframework/integration/handler/advice/ErrorMessageSendingRecoverer.java).

Với gateway yêu cầu phản hồi, cần chọn rõ: trả fallback có kiểu phù hợp, ném lỗi tiếp, hoặc thiết kế một error flow có cơ chế trả lời riêng. Nếu không có reply, gateway có thể chờ hết `replyTimeout`.

`replyTimeout` cũng không phải timeout tổng cho tác vụ đang chạy đồng bộ qua `DirectChannel`: nó không ngắt lời gọi HTTP hoặc backoff đang giữ cùng thread. Dịch vụ đối tác vẫn cần connect/read timeout riêng. [Gateway timeouts và các tình huống không có reply](https://docs.spring.io/spring-integration/reference/7.0/gateway.html#gateway-timeouts).

## 5. Ví dụ đầy đủ: gateway nhận fallback có kiểu rõ ràng

### 5.1. Bài toán và điều kiện thực hành

Một gateway nhận yêu cầu lấy giá. Đối tác không sẵn sàng thì thử lại tối đa hai lần; nếu vẫn lỗi, trả `UNAVAILABLE`. Lỗi dữ liệu hoặc lỗi lập trình phải tiếp tục báo ra ngoài.

Ví dụ dùng:

- Java 17 trở lên.
- `spring-integration-core` 7.0.x và các dependency Spring Framework 7.0.x tương thích, được quản lý thống nhất bằng BOM hoặc dependency management của ứng dụng.
- Cấu hình annotation và Java DSL.
- Một dịch vụ đối tác giả lập luôn lỗi để quan sát đường recovery, không cần kết nối mạng.

Toàn bộ lớp sau nằm trong package riêng cho ví dụ, chẳng hạn `example.recovery`. `@IntegrationComponentScan` tìm gateway interface trong package đó.

~~~java
package example.recovery;

import java.math.BigDecimal;
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.AttributeAccessor;
import org.springframework.core.retry.RetryPolicy;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.core.RecoveryCallback;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.integration.support.ErrorMessageUtils;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandlingException;

@Configuration
@EnableIntegration
@IntegrationComponentScan(basePackageClasses = QuoteRecoveryConfig.class)
public class QuoteRecoveryConfig {

    public record QuoteRequest(String requestId, String sku) {
    }

    public record QuoteResult(
            String requestId,
            String state,
            BigDecimal price) {
    }

    public interface PartnerClient {
        QuoteResult fetch(QuoteRequest request);
    }

    public static class PartnerUnavailableException
            extends RuntimeException {

        public PartnerUnavailableException(String message) {
            super(message);
        }
    }

    @MessagingGateway(
            defaultRequestChannel = "quoteRequests",
            defaultReplyTimeout = "2000")
    public interface QuoteGateway {
        QuoteResult quote(QuoteRequest request);
    }

    @Bean
    public DirectChannel quoteRequests() {
        return new DirectChannel();
    }

    @Bean
    public PartnerClient partnerClient() {
        // Bean minh họa: thay bằng client thật trong ứng dụng.
        return request -> {
            throw new PartnerUnavailableException(
                    "Đối tác tạm thời không sẵn sàng");
        };
    }

    @Bean
    public RecoveryCallback<Object> quoteRecovery() {
        return (context, cause) -> {
            Message<?> failedMessage = requireFailedMessage(context, cause);

            if (!(failedMessage.getPayload()
                    instanceof QuoteRequest request)) {
                throw new MessageHandlingException(
                        failedMessage,
                        "Payload không phù hợp để phục hồi",
                        cause);
            }

            if (!containsCause(
                    cause, PartnerUnavailableException.class)) {
                throw new MessageHandlingException(
                        failedMessage,
                        "Lỗi không có fallback nghiệp vụ",
                        cause);
            }

            return new QuoteResult(
                    request.requestId(), "UNAVAILABLE", null);
        };
    }

    @Bean
    public RequestHandlerRetryAdvice quoteRetryAdvice(
            RecoveryCallback<Object> quoteRecovery) {

        RetryPolicy policy = RetryPolicy.builder()
                .maxRetries(2)
                .delay(Duration.ofMillis(100))
                .includes(PartnerUnavailableException.class)
                .build();

        RequestHandlerRetryAdvice advice =
                new RequestHandlerRetryAdvice();
        advice.setRetryPolicy(policy);
        advice.setRecoveryCallback(quoteRecovery);
        return advice;
    }

    @Bean
    public IntegrationFlow quoteFlow(
            PartnerClient partnerClient,
            RequestHandlerRetryAdvice quoteRetryAdvice) {

        return IntegrationFlow.from("quoteRequests")
                .handle(partnerClient, "fetch",
                        endpoint -> endpoint
                                .requiresReply(true)
                                .advice(quoteRetryAdvice))
                .get();
    }

    private static Message<?> requireFailedMessage(
            AttributeAccessor context, Throwable cause) {

        Object candidate = context.getAttribute(
                ErrorMessageUtils.FAILED_MESSAGE_CONTEXT_KEY);

        if (candidate instanceof Message<?> message) {
            return message;
        }

        throw new IllegalStateException(
                "Recovery thiếu message cần xử lý", cause);
    }

    private static boolean containsCause(
            Throwable failure,
            Class<? extends Throwable> expectedType) {

        for (Throwable current = failure;
                current != null;
                current = current.getCause()) {
            if (expectedType.isInstance(current)) {
                return true;
            }
        }

        return false;
    }
}
~~~

Ở đây `maxRetries(2)` nghĩa là **tối đa ba lần gọi handler**: một lần đầu và hai lần thử lại. Builder của Spring Framework kiểm tra cả exception trực tiếp lẫn các cause khi áp dụng `includes(...)`. Điều này phù hợp với trường hợp exception nghiệp vụ bị endpoint bọc lại. [Javadoc RetryPolicy.Builder 7.0](https://docs.spring.io/spring-framework/docs/7.0.0/javadoc-api/org/springframework/core/retry/RetryPolicy.Builder.html).

### 5.2. Gọi gateway và quan sát kết quả

Đoạn sau khởi tạo context trực tiếp, không cần Spring Boot:

~~~java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import example.recovery.QuoteRecoveryConfig;
import example.recovery.QuoteRecoveryConfig.QuoteGateway;
import example.recovery.QuoteRecoveryConfig.QuoteRequest;

public class RecoveryDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                QuoteRecoveryConfig.class)) {

            QuoteGateway gateway = context.getBean(QuoteGateway.class);

            var result = gateway.quote(
                    new QuoteRequest("quote-001", "SKU-001"));

            System.out.println(result);
        }
    }
}
~~~

Kết quả dự kiến:

~~~text
QuoteResult[requestId=quote-001, state=UNAVAILABLE, price=null]
~~~

Dịch vụ giả lập được gọi ba lần; hai khoảng backoff cấu hình là `100 ms` mỗi khoảng. Sau lần thất bại cuối, callback trả `QuoteResult`. Tổng thời gian còn bao gồm thời gian thực thi từng lần gọi và chi phí xử lý của framework.

Khi thay client giả lập bằng client thật:

- Nếu thành công ở lần đầu hoặc một lần retry, trả kết quả từ client; callback không chạy.
- Nếu liên tục gặp `PartnerUnavailableException`, nhận fallback.
- Nếu gặp lỗi khác, policy không tiếp tục retry và callback từ chối fallback bằng cách ném lỗi tiếp.

Việc kiểm tra loại lỗi trong callback là cần thiết dù policy đã có `includes(...)`: policy quyết định thử lại; callback quyết định liệu lỗi đã kết thúc đó có được chuyển thành kết quả thay thế hay không.

## 6. Chuyển lỗi sang recovery channel bằng ErrorMessageSendingRecoverer

Cách thứ hai phù hợp với luồng một chiều: sau khi retry thất bại, gửi một `ErrorMessage` sang nhánh riêng để ghi nhận hoặc xử lý lại.

Đây là **cấu hình thay thế** cho chiến lược trả fallback ở mục 5. Không gắn cả hai advice vào cùng handler chỉ để thực hiện hai cách recovery.

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.handler.advice.ErrorMessageSendingRecoverer;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.core.retry.RetryPolicy;

// Các phương thức này đặt trong một lớp @Configuration.
@Bean
public QueueChannel recoveryChannel() {
    return new QueueChannel(100);
}

@Bean
public ErrorMessageSendingRecoverer errorRecoverer(
        QueueChannel recoveryChannel) {

    ErrorMessageSendingRecoverer recoverer =
            new ErrorMessageSendingRecoverer(recoveryChannel);
    recoverer.setSendTimeout(1000);
    return recoverer;
}

@Bean
public RequestHandlerRetryAdvice recoveryPublishingAdvice(
        ErrorMessageSendingRecoverer errorRecoverer) {

    RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
    advice.setRetryPolicy(RetryPolicy.builder()
            .maxRetries(2)
            .delay(Duration.ofMillis(100))
            .build());
    advice.setRecoveryCallback(errorRecoverer);
    return advice;
}
~~~

Policy ở đoạn này thử lại mọi loại exception theo mặc định của builder, nhằm giữ ví dụ tập trung vào gửi lỗi. Trong ứng dụng, cần giới hạn các lỗi được retry theo nghiệp vụ.

`QueueChannel(100)` chỉ là bộ đệm trong bộ nhớ có sức chứa giới hạn. Nó giúp tách việc gửi lỗi khỏi consumer trong ví dụ; không phải broker, không phải kho lỗi bền vững và không tự có consumer. `setSendTimeout(1000)` giới hạn thời gian chờ gửi vào channel có thể block, chẳng hạn khi queue đã đầy. [Cơ chế gửi lỗi trong ErrorMessagePublisher](https://github.com/spring-projects/spring-integration/blob/v7.0.0/spring-integration-core/src/main/java/org/springframework/integration/core/ErrorMessagePublisher.java).

Nếu áp dụng advice này cho service activator một chiều, không đặt `requiresReply(true)` và không dùng gateway đòi `QuoteResult` như trong mục 5, trừ khi đã bổ sung cơ chế phản hồi riêng.

### 6.1. Đọc ErrorMessage trong ví dụ

Có thể đọc queue bằng đoạn mã quan sát sau:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;

Message<?> received = recoveryChannel.receive(1000);

if (!(received instanceof ErrorMessage errorMessage)) {
    throw new IllegalStateException("Chưa nhận được ErrorMessage");
}

Throwable failure = errorMessage.getPayload();
Message<?> original = errorMessage.getOriginalMessage();

if (original != null) {
    Object payloadToInspect = original.getPayload();
    Object correlationId = original.getHeaders().get("correlationId");
    // Dùng thông tin cần thiết để xây bản ghi lỗi của ứng dụng.
}
~~~

Payload của `ErrorMessage` là `Throwable`, không phải payload nghiệp vụ gốc. Với advice 7.0 và strategy mặc định trong ví dụ, `originalMessage` được tạo từ message đầu vào trong context. Với nguồn lỗi hoặc strategy khác, thuộc tính này có thể không tồn tại. [DefaultErrorMessageStrategy 7.0](https://github.com/spring-projects/spring-integration/blob/v7.0.0/spring-integration-core/src/main/java/org/springframework/integration/support/DefaultErrorMessageStrategy.java).

Trong các API và phiên bản khác, message thất bại còn có thể nằm trong `MessagingException.getFailedMessage()` ở chuỗi nguyên nhân. Không giả định mọi `Throwable` đều có phương thức `getFailedMessage()`.

### 6.2. Consumer của recovery channel làm gì?

Consumer thực tế có thể chuyển lỗi thành một bản ghi gồm:

| Trường | Mục đích |
|---|---|
| `requestId` hoặc khóa nghiệp vụ | Tra cứu và chống xử lý trùng |
| Tên endpoint hoặc thao tác | Xác định nơi thất bại |
| Loại lỗi và thông tin chẩn đoán | Hỗ trợ điều tra |
| Thời điểm thất bại | Theo dõi tồn đọng |
| Thông tin tối thiểu để dựng lại yêu cầu | Phục vụ xử lý lại |
| Trạng thái xử lý | Phân biệt đang chờ, đã xử lý, cần can thiệp |

Không nên lưu nguyên object exception hoặc tất cả header vào JSON một cách tùy tiện. Một số header chứa channel trong bộ nhớ, payload có thể nhạy cảm, và stack trace không phải dữ liệu nghiệp vụ để phát lại. Cần định nghĩa định dạng bản ghi lỗi có thể lưu và đọc lại ổn định.

## 7. RecoveryCallback và errorChannel không phải cùng một cơ chế

Cả hai đều tham gia xử lý lỗi nhưng được kích hoạt ở những vị trí khác nhau:

| Cơ chế | Thời điểm hoặc nơi tham gia | Điểm cần kiểm soát |
|---|---|---|
| `RecoveryCallback` | Bên trong retry advice khi vòng retry kết thúc bằng lỗi | Trả kết quả gì, gửi lỗi hay ném tiếp |
| `ErrorMessageSendingRecoverer` | Một implementation của recovery callback | Gửi đến channel được chọn rồi trả `null` |
| `errorChannel` của nguồn hoặc gateway | Khi cơ chế xử lý lỗi của thành phần đó nhận được lỗi | Thành phần nào xuất bản `ErrorMessage`, nhánh đó có reply không |
| Exception trên `DirectChannel` | Có thể truyền ngược trên cùng call stack | Bên gọi hoặc gateway xử lý thế nào |

Không nên coi việc đặt header `errorChannel` là cách bắt mọi exception của mọi luồng. Với lời gọi đồng bộ thông thường, exception có thể truyền trực tiếp về sender; việc chuyển exception thành `ErrorMessage` phụ thuộc thành phần đang điều phối xử lý lỗi. [Error handling của Spring Integration](https://docs.spring.io/spring-integration/reference/7.0/error-handling.html).

Các ví dụ trong bài truyền recovery channel trực tiếp vào `ErrorMessageSendingRecoverer`. Cách này thể hiện rõ đích đến của lỗi, thay vì phụ thuộc vào tên channel mặc định hoặc kỳ vọng một header sẽ được mọi component hiểu giống nhau.

Nếu callback đã trả fallback hoặc gửi lỗi thành công rồi trả `null`, lỗi handler đã được xử lý tại ranh giới advice đó. Không nên kỳ vọng cùng lỗi ấy tiếp tục được một error flow bên ngoài nhận thêm một lần. Ngược lại, nếu callback ném lỗi, bên ngoài vẫn có thể xử lý lỗi mới đó theo cấu hình.

## 8. Điều gì xảy ra nếu recovery cũng thất bại?

Recovery vẫn thực hiện I/O và vẫn có thể lỗi:

- Database lưu bản ghi lỗi không hoạt động.
- Recovery queue đầy và hết thời gian gửi.
- Channel không có subscriber phù hợp.
- Consumer đồng bộ của recovery channel ném exception.
- Callback nhận payload không đúng kiểu.

Khi đó không nên ghi log rồi trả thành công nếu yêu cầu nghiệp vụ đòi phải lưu được công việc để xử lý sau. Callback có thể ném exception kèm nguyên nhân; lỗi này cần được bên gọi hoặc cơ chế nhận message xử lý.

Một lỗi xảy ra bên trong callback không mặc nhiên được chính vòng retry của handler thử lại. Advice đã chuyển sang giai đoạn recovery. Nếu thao tác lưu lỗi cần retry riêng, hãy cấu hình giới hạn riêng và kiểm soát tổng thời gian.

### 8.1. Tránh tạo vòng lặp recovery

Không đưa lỗi trở lại ngay channel đang chạy cùng handler mà không có khóa chống trùng, bộ đếm và chính sách thời gian. Nếu handler vẫn thất bại, hệ thống có thể tạo một vòng:

~~~text
handler lỗi -> recovery -> gửi lại cùng channel -> handler lỗi -> ...
~~~

Tách channel lỗi khỏi channel xử lý chính giúp kiểm soát đường đi. Nếu cần xử lý lại, hãy thiết kế thành một tác vụ có lịch, giới hạn và trạng thái riêng.

### 8.2. Quan hệ với transaction và redelivery

Giả sử một consumer nhận message từ broker trong transaction và retry advice nằm bên trong transaction đó:

- Nếu handler ném lỗi ra ngoài, transaction có thể rollback và broker có thể giao lại message theo cấu hình.
- Nếu callback xử lý lỗi rồi trả bình thường, transaction bên ngoài có thể nhìn thấy một lời gọi kết thúc bình thường; không còn exception đó để tự kích hoạt rollback.
- Việc handler hoặc tài nguyên đã đánh dấu transaction là rollback-only vẫn có thể khiến commit thất bại.

Đây là các hệ quả cần kiểm tra trên transaction boundary cụ thể; không phải bảo đảm “recovery thành công thì luôn ack” hoặc “ném lỗi thì broker luôn giao lại”.

Nếu phải lưu bản ghi lỗi trước khi xác nhận xử lý, cần bảo đảm tính nhất quán giữa lưu lỗi và ack/commit. Gửi vào một `QueueChannel` trong bộ nhớ không cung cấp tính nhất quán đó. Một phương án thiết kế là lưu công việc cần xử lý sau cùng dữ liệu nghiệp vụ trong transaction thích hợp rồi để publisher riêng chuyển ra ngoài; phương án khác phụ thuộc khả năng transaction của broker và ứng dụng.

### 8.3. Stateful retry cần khóa ổn định

Với stateful retry, advice giữ trạng thái qua các lượt nhận lại. Khóa phải đại diện cho cùng yêu cầu nghiệp vụ khi được giao lại, chẳng hạn `requestId` do hệ thống phát sinh ban đầu.

Không dùng một `MessageHeaders.ID` mới được tạo mỗi lần dựng lại message làm khóa mặc định cho mọi tình huống. Khi khóa thay đổi, hệ thống có thể coi mỗi lượt giao lại là một yêu cầu mới và không đạt đến điều kiện recovery như dự định.

Trong Spring Integration 7.0, stateful retry được cấu hình bằng `setStateKeyFunction(...)`; trong 6.x là `RetryStateGenerator`. Ví dụ của bài không bật chúng, để việc đếm số lần gọi và quan sát callback nằm trong một lượt gửi. [Cấu hình stateless và stateful retry](https://docs.spring.io/spring-integration/docs/7.0.0/api/org/springframework/integration/handler/advice/RequestHandlerRetryAdvice.html).

## 9. Kiểm thử hành vi quan sát được

Kiểm thử cần phân biệt kết quả nghiệp vụ, số lần gọi dịch vụ và đường đi của lỗi.

### 9.1. Các tình huống cần bao phủ

Với policy `maxRetries(2)` trong mục 5:

| Tình huống | Số lần gọi client dự kiến | Kết quả cần xác nhận |
|---|---:|---|
| Thành công ngay | 1 | Kết quả thật, không có fallback |
| Lỗi tạm thời rồi thành công ở lần hai | 2 | Kết quả thật |
| Lỗi tạm thời liên tục | 3 | `UNAVAILABLE` và giữ đúng `requestId` |
| Lỗi không thuộc nhóm cho retry | 1 | Exception tiếp tục truyền ra ngoài |
| Recovery không lấy được message hợp lệ | Theo lỗi đã xảy ra trước đó | Không trả fallback sai dữ liệu |
| Recoverer gửi lỗi thành công | Theo policy của endpoint | Có một `ErrorMessage` ở recovery channel |
| Recovery channel đầy | Theo policy của endpoint | Lỗi gửi không bị che thành thành công |

Không khẳng định chính xác thời gian thực thi bằng các con số sát nhau như `200 ms` và `201 ms`. Scheduler, máy chạy test và thời gian mock đều có thể làm kết quả dao động. Số lần gọi và nội dung phản hồi phản ánh mục đích bài học rõ hơn.

### 9.2. Ví dụ JUnit cho cấu hình trả fallback

Đoạn test sau dùng cấu hình ở mục 5, `spring-test` 7.0.x, JUnit Jupiter và Mockito. `@MockitoBean` thay bean client bằng mock để chủ động điều khiển từng lần gọi. [Javadoc MockitoBean](https://docs.spring.io/spring-framework/docs/7.0.0/javadoc-api/org/springframework/test/context/bean/override/mockito/MockitoBean.html).

~~~java
package example.recovery;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.messaging.MessagingException;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import example.recovery.QuoteRecoveryConfig.PartnerClient;
import example.recovery.QuoteRecoveryConfig.PartnerUnavailableException;
import example.recovery.QuoteRecoveryConfig.QuoteGateway;
import example.recovery.QuoteRecoveryConfig.QuoteRequest;
import example.recovery.QuoteRecoveryConfig.QuoteResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@SpringJUnitConfig(QuoteRecoveryConfig.class)
class QuoteRecoveryTest {

    @Autowired
    QuoteGateway gateway;

    @MockitoBean(enforceOverride = true)
    PartnerClient partnerClient;

    @Test
    void returnsActualQuoteWhenFirstAttemptSucceeds() {
        QuoteRequest request = new QuoteRequest("q-1", "SKU-001");
        QuoteResult actualQuote = new QuoteResult(
                "q-1", "OK", new BigDecimal("125000"));

        when(partnerClient.fetch(request)).thenReturn(actualQuote);

        assertEquals(actualQuote, gateway.quote(request));
        verify(partnerClient, times(1)).fetch(request);
    }

    @Test
    void returnsActualQuoteAfterOneTransientFailure() {
        QuoteRequest request = new QuoteRequest("q-2", "SKU-001");
        QuoteResult actualQuote = new QuoteResult(
                "q-2", "OK", new BigDecimal("125000"));

        when(partnerClient.fetch(request))
                .thenThrow(new PartnerUnavailableException("Tạm thời lỗi"))
                .thenReturn(actualQuote);

        assertEquals(actualQuote, gateway.quote(request));
        verify(partnerClient, times(2)).fetch(request);
    }

    @Test
    void returnsUnavailableAfterRetryLimit() {
        QuoteRequest request = new QuoteRequest("q-3", "SKU-001");

        when(partnerClient.fetch(request))
                .thenThrow(new PartnerUnavailableException("Vẫn lỗi"));

        QuoteResult result = gateway.quote(request);

        assertAll(
                () -> assertEquals("q-3", result.requestId()),
                () -> assertEquals("UNAVAILABLE", result.state()),
                () -> assertNull(result.price()));
        verify(partnerClient, times(3)).fetch(request);
    }

    @Test
    void propagatesFailureWithoutBusinessFallback() {
        QuoteRequest request = new QuoteRequest("q-4", "SKU-INVALID");

        when(partnerClient.fetch(request))
                .thenThrow(new IllegalArgumentException("SKU không hợp lệ"));

        assertThrows(
                MessagingException.class,
                () -> gateway.quote(request));
        verify(partnerClient, times(1)).fetch(request);
    }
}
~~~

Đối với chiến lược gửi lỗi, hãy dùng một recovery channel riêng cho từng test, lấy message với timeout hữu hạn, kiểm tra kiểu `ErrorMessage` và thông tin request gốc, rồi kiểm tra không có message lỗi thứ hai ngoài dự kiến. Một test chỉ kiểm tra “không ném exception” chưa chứng minh rằng công việc thất bại đã được lưu hoặc chuyển đến đúng nơi.

Các đoạn code kiểm thử trong bài là tài liệu thực hành; cần đưa chúng vào dự án có dependency tương ứng để biên dịch và chạy.

## 10. Khi dự án dùng Spring Integration 6.x và Spring Retry 2.x

### 10.1. Điểm khác nhau cần nhớ

| Nội dung | Spring Integration 6.x | Spring Integration 7.0 |
|---|---|---|
| Recovery callback | `org.springframework.retry.RecoveryCallback<T>` | `org.springframework.integration.core.RecoveryCallback<T>` |
| Chữ ký callback | `recover(RetryContext context) throws Exception` | `recover(AttributeAccessor context, Throwable cause)` |
| Nguồn lấy exception | `context.getLastThrowable()` | Tham số `cause` |
| Cấu hình retry trong advice | `setRetryTemplate(...)` | `setRetryPolicy(...)` |
| Số lần thử trong ví dụ | `maxAttempts(3)` hoặc `SimpleRetryPolicy(3, ...)`: tổng cộng 3 lần | `maxRetries(2)`: 1 lần đầu + 2 lần retry |
| Trạng thái qua nhiều lượt nhận | `RetryStateGenerator` | `setStateKeyFunction(...)` |

Đây là thay đổi API, không chỉ là đổi tên import. Callback một tham số của Spring Retry không thể được chuyển nguyên xi sang setter yêu cầu callback hai tham số của Spring Integration 7.0. [RecoveryCallback của Spring Retry 2.x](https://docs.spring.io/spring-retry/docs/2.0.12/apidocs/org/springframework/retry/RecoveryCallback.html), [hướng dẫn chuyển từ Spring Integration 6.x sang 7.0](https://github.com/spring-projects/spring-integration/wiki/Spring-Integration-6.x-to-7.0-Migration-Guide).

### 10.2. Cấu hình tương đương cho 6.x

Đoạn sau là phần cấu hình **thay thế** các bean recovery và retry của mục 5 khi chạy trên 6.x. Các kiểu nghiệp vụ và helper `containsCause(...)`, `requireFailedMessage(...)` vẫn là những thành phần đã giải thích ở trên. Cần thêm dependency `spring-retry` 2.x tương thích với dependency management của dự án.

~~~java
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandlingException;
import org.springframework.retry.RecoveryCallback;
import org.springframework.retry.backoff.FixedBackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;

// Đặt trong QuoteRecoveryConfig thay cho các bean tương ứng của bản 7.0.
@Bean
public RequestHandlerRetryAdvice quoteRetryAdvice() {
    Map<Class<? extends Throwable>, Boolean> retryable =
            Map.of(PartnerUnavailableException.class, true);

    // 3 là tổng số lần gọi; true bật kiểm tra các cause.
    SimpleRetryPolicy policy =
            new SimpleRetryPolicy(3, retryable, true);

    FixedBackOffPolicy backOff = new FixedBackOffPolicy();
    backOff.setBackOffPeriod(100);

    RetryTemplate template = new RetryTemplate();
    template.setRetryPolicy(policy);
    template.setBackOffPolicy(backOff);

    RecoveryCallback<Object> recovery = context -> {
        Throwable cause = context.getLastThrowable();
        Message<?> message = requireFailedMessage(context, cause);

        if (!(message.getPayload() instanceof QuoteRequest request)) {
            throw new MessageHandlingException(
                    message, "Payload không phù hợp để phục hồi", cause);
        }

        if (!containsCause(cause, PartnerUnavailableException.class)) {
            throw new MessageHandlingException(
                    message, "Lỗi không có fallback nghiệp vụ", cause);
        }

        return new QuoteResult(
                request.requestId(), "UNAVAILABLE", null);
    };

    RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
    advice.setRetryTemplate(template);
    advice.setRecoveryCallback(recovery);
    return advice;
}
~~~

`RetryContext` của Spring Retry là một `AttributeAccessor` nên helper đọc message có thể nhận context này. Advice 6.x bổ sung message đang xử lý dưới `FAILED_MESSAGE_CONTEXT_KEY`. [Javadoc RetryContext](https://docs.spring.io/spring-retry/docs/2.0.12/apidocs/org/springframework/retry/RetryContext.html), [mã nguồn advice 6.5](https://github.com/spring-projects/spring-integration/blob/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/handler/advice/RequestHandlerRetryAdvice.java).

`SimpleRetryPolicy` tính cả lần gọi đầu trong `maxAttempts`. Bật `traverseCauses` giúp policy nhận ra exception nghiệp vụ bị bọc trong exception của messaging. Ngoài ra, Spring Retry 2.x có khả năng đánh dấu một số lỗi là không recoverable; do đó “không retry” và “không recovery” là hai quyết định khác nhau. [Javadoc SimpleRetryPolicy](https://docs.spring.io/spring-retry/docs/2.0.12/apidocs/org/springframework/retry/policy/SimpleRetryPolicy.html).

### 10.3. RecoveryCallback khác @Recover

`RecoveryCallback` là callback được cấu hình tường minh cho retry template hoặc advice phù hợp với phiên bản. `@Recover` thuộc cách sử dụng Spring Retry qua annotation và proxy.

Chỉ thêm một phương thức có `@Recover` vào service không có nghĩa `RequestHandlerRetryAdvice` tự tìm và gọi phương thức đó. Với cấu hình advice trong bài, đường recovery được chỉ định qua `setRecoveryCallback(...)`.

## 11. Những quyết định thiết kế trước khi đưa vào luồng thật

### 11.1. Phân loại lỗi và chọn hành động

| Loại lỗi | Hướng xem xét |
|---|---|
| Dịch vụ đối tác tạm ngừng | Retry có giới hạn; fallback nếu nghiệp vụ chấp nhận |
| Yêu cầu sai định dạng | Từ chối sớm; không retry cùng dữ liệu không đổi |
| Không đủ quyền truy cập | Báo lỗi cấu hình hoặc quyền; tránh retry dồn dập |
| Tác vụ có thể đã thực hiện nhưng mất phản hồi | Tra cứu trạng thái bằng khóa idempotency trước khi thực hiện lại |
| Không ghi được bản ghi recovery bắt buộc | Giữ trạng thái thất bại bằng cách báo lỗi ra ngoài |

Bảng này là gợi ý thiết kế; việc phân loại cụ thể phải dựa trên hợp đồng của dịch vụ đối tác. Một mã lỗi HTTP hay một timeout không tự chứng minh rằng thao tác chưa tạo tác dụng phụ.

### 11.2. Retry và recovery đều cần idempotency

Ví dụ lấy giá là thao tác đọc nên dễ minh họa. Với thanh toán hoặc tạo đơn, lần gọi đầu có thể đã thành công ở hệ thống ngoài nhưng phản hồi bị mất. Retry mù có thể tạo giao dịch trùng.

Cần khóa idempotency ổn định, cơ chế tra cứu trạng thái và quy tắc bù trừ nếu có. Callback gửi thông báo, ghi bản ghi lỗi hoặc tạo công việc xử lý lại cũng cần chống trùng khi broker giao lại message sau lỗi hoặc khi tiến trình khởi động lại.

Không dùng fallback kiểu “đã thanh toán” chỉ vì hệ thống không nhận được phản hồi. Recovery phải bảo toàn ý nghĩa nghiệp vụ của trạng thái chưa biết.

### 11.3. Giới hạn thời gian và số tầng retry

Ngân sách một vòng xử lý có thể ước lượng bằng:

~~~text
Tổng thời gian ≈
    tổng thời gian các lần gọi handler
    + tổng các khoảng backoff
    + thời gian thực hiện recovery
~~~

Nếu HTTP client tự retry, endpoint có retry advice, broker lại có redelivery, số lần gọi thực tế có thể tăng mạnh. Cần xác định một nơi chịu trách nhiệm chính cho mỗi loại lỗi và theo dõi tổng số lần xử lý theo khóa nghiệp vụ.

### 11.4. Quan sát đúng trạng thái

Nên phân biệt các số liệu:

- Handler thành công mà không retry.
- Handler thành công sau retry.
- Vòng retry kết thúc bằng lỗi.
- Callback trả fallback.
- Callback gửi lỗi thành công.
- Callback cũng thất bại.

Một gateway nhận được object hợp lệ sau fallback không có nghĩa dịch vụ đối tác hoạt động tốt. Nên theo dõi tỷ lệ fallback riêng và thời gian tồn đọng trong kho lỗi. Log cần chứa request ID hoặc khóa tương quan phù hợp, đồng thời giới hạn dữ liệu nhạy cảm và payload lớn.

## 12. Lỗi thường gặp và cách nhận biết

| Biểu hiện | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Callback không biên dịch sau nâng cấp | Dùng callback một tham số hoặc import Spring Retry trong cấu hình 7.0 | Kiểm tra package, chữ ký và setter |
| Dịch vụ bị gọi nhiều hơn dự kiến | Nhầm `maxRetries` với `maxAttempts` hoặc có nhiều tầng retry | Đếm lời gọi client theo request ID |
| Lỗi dữ liệu cũng biến thành fallback | Callback không phân loại lỗi cuối cùng | Kiểm thử lỗi không nằm trong nhóm được retry |
| Gateway chờ dù đã gửi lỗi | Recoverer trả `null`, chưa có phản hồi đúng hợp đồng | Kiểm tra reply channel và kiểu trả về |
| Có log lỗi nhưng không có công việc chờ xử lý | Chỉ ghi log hoặc chỉ gửi vào queue trong bộ nhớ | Kiểm tra bản ghi bền vững và consumer |
| Có thông báo lỗi trùng | Recovery tự publish rồi còn ném lỗi vào cơ chế khác | Vẽ đường đi thực tế và đếm message |
| Recovery không bao giờ đạt ngưỡng khi redelivery | Khóa stateful thay đổi giữa các lần nhận | So sánh khóa nghiệp vụ ở từng lượt |
| Mất tương quan sau recovery | Tạo message mới nhưng thiếu header cần thiết | Kiểm tra headers trước aggregator hoặc gateway |

## 13. Bài thực hành tự kiểm chứng

1. Chạy ví dụ mục 5 với client giả lập luôn lỗi. Xác nhận gateway nhận `UNAVAILABLE` và request ID đúng.
2. Dùng mock làm client thất bại một lần rồi thành công. Xác nhận kết quả là giá thật và tổng cộng hai lần gọi.
3. Cho client ném `IllegalArgumentException`. Xác nhận không chuyển lỗi đó thành trạng thái `UNAVAILABLE`.
4. Dựng một luồng một chiều riêng sử dụng cấu hình mục 6. Gửi một message và đọc đúng một `ErrorMessage` từ recovery channel.
5. Giới hạn recovery queue còn một phần tử, không chạy consumer và gửi đủ để làm queue đầy. Quan sát lỗi gửi khi hết timeout.
6. Thay queue bộ nhớ bằng nơi lưu lỗi phù hợp với ứng dụng. Xác định điều kiện nào cho phép consumer ban đầu xác nhận xử lý.
7. Nếu thêm splitter và aggregator, xác định mỗi phần tử thất bại sẽ tạo fallback hay bị chuyển riêng sang error flow; sau đó kiểm tra điều kiện hoàn tất group.

Tiêu chí hoàn thành là giải thích được **ai nhận kết quả**, **message lỗi đi đâu**, **khi nào hệ thống vẫn báo thất bại** và **điều gì được bảo đảm sau khi recovery trả về** cho từng cấu hình đã chọn.
