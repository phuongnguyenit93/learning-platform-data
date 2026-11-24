# RetryTemplate và retry policy trong Spring Integration Adapters

> **Chương:** Reliability  
> **Bài học:** RetryTemplate và retry policy  
> **Phạm vi:** Kết nối hệ thống ngoài vào Spring Integration bằng inbound/outbound adapter, gateway, poller và MessageChannel. Thực hành luồng trao đổi qua **file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu**, đồng thời quản lý hợp đồng message, lỗi, tính nhất quán và vòng đời kết nối.

## 1. Mục tiêu học tập

Hoàn thành bài này, người học có thể:

1. Giải thích **retry** giải quyết dạng lỗi nào và phân biệt lỗi tạm thời với lỗi vĩnh viễn.
2. Nhận biết các thành phần **RetryTemplate, RetryPolicy, BackOffPolicy, RetryContext, RetryCallback và RecoveryCallback** trong Spring Retry.
3. Cấu hình retry giới hạn số lần, phân loại exception, backoff theo cấp số nhân và giới hạn thời gian chờ.
4. Tích hợp **RequestHandlerRetryAdvice** tại request handler của Spring Integration, hiểu phạm vi retry so với poller, gateway và message channel.
5. Giải thích khác nhau giữa **retry trong tiến trình**, **redelivery từ broker** và **replay từ kho dữ liệu**, tránh tạo các vòng retry lồng nhau ngoài kiểm soát.
6. Thiết kế **idempotency, transaction, acknowledgement, error channel, dead-letter và recovery** phù hợp với từng adapter.
7. Phân tích kịch bản lỗi qua **File, SFTP, HTTP, JMS, AMQP, Kafka, JDBC** và xác định chính xác đâu là điểm commit/ack.
8. Viết kiểm thử và bộ chỉ số để đo **attempts, exhaustion, delay, duplicate effects, backlog và thời gian phục hồi**.

## 2. Bối cảnh: Spring Integration và một lần trao đổi thất bại

Một Integration Flow thường nhận thông điệp từ **inbound adapter** hoặc **gateway**, đưa qua **MessageChannel**, xử lý bằng transformer/router/filter/service activator, rồi chuyển tới **outbound adapter** hoặc **outbound gateway**.

Ví dụ:

~~~text
File/SFTP inbound adapter
    -> inputChannel
    -> parse/validate
    -> enrichHeaders(eventId, correlationId)
    -> processChannel
    -> HTTP outbound gateway
    -> partner-resultChannel
~~~

Các bước đều có thể lỗi nhưng **không phải lỗi nào cũng nên thử lại**:

- Poller chưa đọc được file vì file đang được ghi dở: có thể **đợi** lần poll tiếp theo, không nhất thiết retry toàn bộ.
- SFTP mất kết nối tạm thời: có thể khôi phục sau backoff.
- Payload JSON thiếu trường bắt buộc: gửi lại cùng dữ liệu thường vẫn thất bại.
- HTTP 503/429: có thể tạm thời, cần tôn trọng khả năng của đích và chính sách an toàn.
- HTTP 401/403: thường cần sửa credential hoặc quyền, không lặp request không điều kiện.
- JDBC gặp deadlock/serialization conflict: có thể retry **transaction** nếu thiết kế đúng.
- JMS/Kafka consumer thất bại: cần phối hợp **acknowledgement/offset commit** và cơ chế redelivery của broker.
- HTTP POST đã được phía đối tác xử lý nhưng response bị mất: thử lại có thể **tạo nghiệp vụ trùng**.

**Retry không đồng nghĩa bảo đảm thành công.** Nó chỉ cho một lỗi có khả năng phục hồi thêm cơ hội xử lý; retry sai có thể tạo tải lớn, nhân đôi side effect hoặc giữ message ở trạng thái không thể xử lý.

## 3. Mục tiêu độ tin cậy: đúng tác vụ và đúng số lần tác động

Hãy tách ba câu hỏi:

1. **Có thể thử lại thao tác không?** Xét exception, operation, khả năng phục hồi, nguồn dữ liệu và giới hạn thời gian.
2. **Lần thử lại có an toàn không?** Xét idempotency, transaction và khả năng đối tác đã nhận request trước khi timeout.
3. **Nếu đã hết lượt thì làm gì?** Xét recovery, dead-letter, lưu bằng chứng, cảnh báo, replay có kiểm soát và ack/rollback.

### Ba thuật ngữ giao hàng

| Thuật ngữ | Ý nghĩa thường gặp | Cẩn trọng |
|---|---|---|
| **At-most-once** | Không cố gửi lại khi có khả năng đã xử lý; có thể mất tác vụ | Không tự phù hợp với dữ liệu tài chính cần xử lý đầy đủ |
| **At-least-once** | Có thể thử lại hoặc redeliver để tránh bỏ sót | Phải xử lý tác vụ trùng |
| **Exactly-once effect** | Hiệu ứng nghiệp vụ không bị tạo trùng theo phạm vi được thiết kế | Thường cần idempotency/transaction/dedupe; không được suy ra chỉ từ việc bật retry |

Một message có thể được giao nhiều lần nhưng vẫn tạo **một hiệu ứng nghiệp vụ** nếu có khóa idempotency và nơi lưu kết quả có tính nhất quán.

**Không có lựa chọn RetryPolicy nào tự biến hệ thống phân tán thành exactly-once end-to-end.**

## 4. Những thành phần nền tảng của Spring Retry

Spring Retry cung cấp những khái niệm áp dụng được bên trong ứng dụng Java/Spring, còn Spring Integration giúp gắn chúng vào điểm xử lý message.

| Thành phần | Trách nhiệm | Ghi nhớ |
|---|---|---|
| **RetryTemplate** | Điều phối nhiều attempt và kết thúc thành công hoặc exhausted | Là cơ chế in-process, không phải kho retry bền vững |
| **RetryCallback** | Khối công việc được thực thi ở mỗi attempt | Chọn scope cẩn thận để tránh chạy lại side effect không liên quan |
| **RetryPolicy** | Quyết định còn được retry không và khi nào kết thúc | Dựa trên số attempt, exception, timeout hoặc policy kết hợp |
| **BackOffPolicy** | Quy định khoảng nghỉ giữa các attempt | Tránh dồn request liên tục vào hệ thống đang lỗi |
| **RetryContext** | Trạng thái của một chuỗi retry, số lần đã thử, exception gần nhất và metadata | Không được nhầm với message header hoặc trạng thái lưu bền |
| **RecoveryCallback** | Hành động sau khi retry không còn tiếp tục được | Có thể ghi failure, chuyển dead-letter, trả fallback hoặc ném lỗi |
| **RetryListener** | Quan sát mở attempt, lỗi và kết thúc | Phù hợp metrics/tracing với dữ liệu được bảo vệ |
| **RequestHandlerRetryAdvice** | Bọc request handler của Spring Integration bằng retry | Scope phụ thuộc endpoint/advice chain được gắn |

Trong một Spring Integration Flow, adapter và gateway là thành phần nối với hệ thống ngoài; **RetryTemplate không tự biết cách broker ack message, lưu checkpoint SFTP hoặc commit Kafka offset**. Các việc đó do adapter/container/transaction/recovery thiết kế riêng.

### Sơ đồ vòng đời một RetryTemplate

~~~mermaid
flowchart TD
    A["Message đi tới handler có retry"] --> B["Mở RetryContext"]
    B --> C{"RetryPolicy còn cho phép?"}
    C -->|"Có"| D["Gọi RetryCallback / handler"]
    D -->|"Thành công"| S["Trả kết quả, kết thúc"]
    D -->|"Exception"| E["Phân loại exception và cập nhật context"]
    E --> C
    C -->|"Không"| F{"Có RecoveryCallback?"}
    F -->|"Có"| G["Recovery: DLQ, error flow, fallback hoặc rethrow"]
    F -->|"Không"| H["Exception nổi lên caller/container"]
    G --> I["Đóng retry context"]
    H --> I
    S --> I
    E -.-> J["BackOffPolicy trước attempt kế tiếp"]
    J -.-> C
~~~

*Đây là mô hình logic*: retry policy và backoff được dùng theo hợp đồng của Spring Retry; một exception không được retry có thể đi ngay tới recovery/exhaustion. Không nên suy luận từ sơ đồ rằng mọi recovery đều thành công hoặc broker tự xác nhận message.

## 5. RetryPolicy: số lần thử gồm những lần nào?

**SimpleRetryPolicy** thường dùng để giới hạn số attempt. Nếu đặt **maxAttempts = 4**, nghĩa là:

- **Attempt 1:** lần gọi đầu tiên;
- **Retry 1:** lần gọi thứ hai;
- **Retry 2:** lần gọi thứ ba;
- **Retry 3:** lần gọi thứ tư.

Vậy có **4 attempts tổng**, trong đó nhiều nhất **3 lần thử lại**.

### Ví dụ tính tổng độ trễ

Giả sử mỗi lần gọi HTTP có timeout tối đa 2 giây và backoff là 300 ms, 600 ms, 1.200 ms giữa bốn attempts.

**Thời gian xấu nhất xấp xỉ = 4 × 2.000 ms + (300 + 600 + 1.200) ms = 10.100 ms**, chưa tính scheduling, xử lý serialization, queue, TLS handshake và overhead khác.

Từ đó:

- Nếu API caller chỉ có deadline 5 giây thì cấu hình trên không phù hợp.
- Nếu worker đang dùng một thread cố định, retry liên tiếp có thể giữ thread hơn 10 giây.
- Nếu 500 message cùng lỗi và cùng schedule, backoff đồng bộ có thể gây **retry storm**.

**Timeout của từng attempt không phải timeout tổng của cả chuỗi retry.** Cần quản lý deadline và ngân sách thời gian ở nhiều tầng.

### Phân biệt các kiểu policy

| Policy / cách phân loại | Khi hữu ích | Lưu ý |
|---|---|---|
| **SimpleRetryPolicy** | Giới hạn attempts, phân loại exception cơ bản | Không tự biết mức an toàn nghiệp vụ của operation |
| **TimeoutRetryPolicy** | Giới hạn khoảng thời gian retry theo policy | Cần kết hợp timeout thực của lời gọi bên ngoài |
| **ExceptionClassifierRetryPolicy** | Các nhóm exception cần chiến lược retry khác nhau | Classifier phải hiểu wrapper exception của Spring Integration |
| **CompositeRetryPolicy** | Ghép một số điều kiện như số attempts và thời hạn | Semantics AND/OR cần kiểm chứng đúng cấu hình |
| **CircuitBreakerRetryPolicy** hoặc circuit breaker độc lập | Hạn chế lặp lại lỗi liên tục theo chiến lược | Không nhầm với circuit breaker phân tán có state/metric riêng |
| **NeverRetryPolicy** | Lỗi không nên retry | Đẩy sang recovery hoặc trả lỗi ngay |
| **AlwaysRetryPolicy** | Dùng trong trường hợp rất có kiểm soát | Dễ tạo vòng vô hạn; tránh sử dụng mù với hệ thống bên ngoài |

Danh sách trên nói về **khái niệm/API của thư viện**, khả năng và cách dựng chính xác có thể khác giữa các phiên bản Spring Retry. Trong hệ thống thật, luôn khai báo rõ **max attempts và deadline/giới hạn tổng**.

## 6. Phân loại exception: lỗi tạm thời và lỗi cố định

Không phải cứ có exception là request cần chạy lại. Hãy phân loại theo **nguyên nhân và khả năng an toàn của operation**.

| Nhóm lỗi | Ví dụ | Chiến lược thường hợp lý |
|---|---|---|
| **Transient network** | Socket timeout, connection reset, DNS/service discovery gián đoạn ngắn | Retry có giới hạn, backoff; chú ý request có thể đã tới đích |
| **Rate limit / overload** | HTTP 429, broker/thành phần đích đang quá tải | Backoff, jitter, tôn trọng Retry-After nếu có |
| **Unavailable tạm thời** | HTTP 503, dịch vụ bảo trì ngắn | Retry có budget; circuit breaker khi lỗi lan rộng |
| **Transient concurrency** | Deadlock, optimistic lock conflict, serialization error | Retry đơn vị transaction đúng phạm vi |
| **Invalid input** | JSON sai schema, thiếu trường bắt buộc, business rule fail | Không retry không điều kiện; đưa invalid message sang xử lý riêng |
| **Authentication/authorization** | HTTP 401/403, quyền JMS/Kafka sai, khóa bị thu hồi | Dừng và sửa credential/policy; không lặp request vô ích |
| **Không tìm thấy** | HTTP 404 | Phụ thuộc hợp đồng API; thường không retry trừ trường hợp eventual consistency đã biết |
| **Xung đột nghiệp vụ** | HTTP 409 | Phải hiểu conflict có thể giải quyết tự động hay không; không coi tất cả đều transient |
| **Permanent filesystem** | Permission denied, đường dẫn sai, quota cấu hình sai | Sửa hệ thống/permission trước; tránh loop |
| **Không biết kết quả gửi** | Response timeout sau POST | Phải dùng idempotency key/query trạng thái trước khi gửi lại |

### Quyết định retry nên dựa trên hai chiều

**Retryability = loại lỗi có thể phục hồi × mức an toàn chạy lại thao tác.**

Ví dụ HTTP 503 có thể tạm thời, nhưng POST tạo đơn hàng **không có idempotency key** vẫn có nguy cơ tạo đơn trùng nếu lần đầu đã được ghi trước khi trả 503.

Một phương án ra quyết định:

1. Nếu payload không hợp lệ hoặc thiếu quyền → **không retry**, chuyển xử lý có chủ đích.
2. Nếu lỗi tạm thời và operation idempotent → **retry có giới hạn**.
3. Nếu trạng thái thực thi không rõ nhưng operation có idempotency key → retry theo hợp đồng idempotency của đích.
4. Nếu trạng thái không rõ, operation không idempotent → **tra cứu trạng thái/đối soát**, không gửi lại mù.
5. Nếu đã hết retries → recovery/parking/DLQ và cảnh báo; không xóa dấu vết lỗi.

### Cẩn trọng với exception wrapper

Trong Spring Integration, handler có thể bọc lỗi của hệ thống ngoài trong **MessagingException/MessageHandlingException** hoặc một exception khác. Nếu RetryPolicy chỉ so exact class và không xem cause chain, lỗi IOException thật có thể bị phân loại sai.

**Không nên retry toàn bộ MessagingException.** Cần xem nguyên nhân gốc và loại action: cùng một wrapper có thể chứa IOException tạm thời hoặc ValidationException vĩnh viễn.

## 7. BackOffPolicy: giảm tải và tránh retry storm

Backoff quyết định **đợi bao lâu giữa hai attempts**.

| Kiểu backoff | Mô tả | Trường hợp phù hợp |
|---|---|---|
| Không backoff | Gửi lại gần như ngay | Chỉ với lỗi rất ngắn, giá rẻ và được kiểm soát |
| **FixedBackOffPolicy** | Khoảng chờ cố định, ví dụ 500 ms | Tình huống ngắn, ít client |
| **ExponentialBackOffPolicy** | Khoảng chờ tăng theo hệ số đến maxInterval | Dịch vụ đích quá tải hoặc lỗi mạng ngắn |
| **ExponentialRandomBackOffPolicy** / jitter | Khoảng chờ có thành phần ngẫu nhiên | Nhiều client retry đồng thời, giảm herd effect |
| Retry-After-aware | Điều chỉnh theo thông báo của đích | HTTP 429/503 có Retry-After hợp lệ; cần tích hợp logic cụ thể |

### Ví dụ exponential backoff

- initialInterval = 300 ms;
- multiplier = 2;
- maxInterval = 2.000 ms;
- maxAttempts = 4.

Khoảng chờ giữa attempts lần lượt khoảng **300, 600, 1.200 ms** nếu không có jitter. Nếu thêm nhiều attempts, khoảng chờ sẽ không tăng vượt trần 2.000 ms theo policy.

**ExponentialBackOffPolicy thông thường không tự thêm jitter.** Muốn giảm nguy cơ client đồng thời, cần chọn policy ngẫu nhiên hoặc tự thiết kế khoảng nghỉ ngẫu nhiên phù hợp.

### Retry budget

Ngoài maxAttempts, nên đặt:

- **Per-attempt timeout** cho lời gọi mạng;
- **Total deadline** của request hoặc job;
- **Concurrency limit** cho số request đang retry;
- **Rate limit** tới đối tác;
- **Retry budget** theo tỷ lệ so với request gốc;
- **Quy tắc dừng** khi circuit breaker open hoặc client đã hủy request.

Ví dụ người dùng đợi HTTP gateway trong 3 giây; không nên cấu hình adapter retry hàng chục giây rồi mới trả response nếu hợp đồng trải nghiệm không cho phép.

## 8. Cấu hình RetryTemplate bằng Java

Ví dụ sau thể hiện **phân loại exception cụ thể** và backoff có giới hạn. Nó phù hợp để học cấu trúc API của Spring Retry; cần đối chiếu dependency/version của dự án khi triển khai.

~~~java
import java.io.IOException;
import java.util.HashMap;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.retry.support.RetryTemplate;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;

@Configuration
class PartnerRetryConfiguration {

    @Bean
    RetryTemplate partnerRetryTemplate() {
        Map<Class<? extends Throwable>, Boolean> retryable = new HashMap<>();

        // Ví dụ: chỉ những lỗi có khả năng tạm thời.
        retryable.put(IOException.class, true);
        retryable.put(HttpClientErrorException.TooManyRequests.class, true);
        retryable.put(HttpServerErrorException.ServiceUnavailable.class, true);

        // 4 attempts tổng, có thể xét cause chain, mặc định class khác = false.
        SimpleRetryPolicy retryPolicy =
                new SimpleRetryPolicy(4, retryable, true, false);

        ExponentialBackOffPolicy backOff = new ExponentialBackOffPolicy();
        backOff.setInitialInterval(300L);
        backOff.setMultiplier(2.0);
        backOff.setMaxInterval(2_000L);

        RetryTemplate template = new RetryTemplate();
        template.setRetryPolicy(retryPolicy);
        template.setBackOffPolicy(backOff);
        return template;
    }
}
~~~

**Những điểm cần hiểu:**

- **4** là tổng attempts, không phải bốn lần retry sau lần đầu.
- Bằng cách dùng danh sách lỗi cụ thể và mặc định **false**, ví dụ không retry toàn bộ IllegalArgumentException hoặc lỗi quyền.
- Cấu hình traverseCauses giúp nhận diện nguyên nhân bên trong wrapper khi thư viện hỗ trợ theo chính sách.
- Retry của IOException không bảo đảm an toàn cho HTTP POST; tính idempotent phải được kiểm soát ở tầng nghiệp vụ.
- Ví dụ chưa có jitter, deadline tổng, retry budget hoặc chính sách riêng cho phản hồi **502/504**. Đây là phần cần thiết kế thêm nếu ứng dụng yêu cầu.
- HttpClientErrorException.TooManyRequests và HttpServerErrorException.ServiceUnavailable là những loại từ Spring Web; retry theo status/exception cụ thể vẫn phụ thuộc cách HTTP client và gateway chuyển lỗi.

### Thử RetryTemplate trực tiếp

~~~java
RetryTemplate template = partnerRetryTemplate();

String response = template.execute(context -> {
    // Tác vụ này có thể được thực hiện nhiều lần.
    // Chỉ làm vậy khi đã xác nhận idempotency.
    return partnerClient.getStatus();
});
~~~

Tham số callback có thể cung cấp **retryCount** và thông tin lỗi của chuỗi retry, nhưng đừng dùng retryCount làm business event ID: nó thay đổi theo từng attempt và không ổn định giữa các lần redelivery từ broker.

### Khi nào dùng execute trực tiếp?

Dùng khi muốn kiểm soát một **khối thao tác** bên ngoài handler hoặc trong service. Nhưng nếu Spring Integration endpoint đã có retry advice, việc gọi thêm RetryTemplate bên trong service có thể tạo **retry lồng nhau**. Nên xác định một owner cho retry ở từng ranh giới, và ghi tài liệu số attempts tổng.

## 9. Gắn RetryTemplate vào Spring Integration bằng RequestHandlerRetryAdvice

Spring Integration hỗ trợ cơ chế **advice** ở request handler endpoint. **RequestHandlerRetryAdvice** cho phép một lần gọi handler bị lỗi có thể thực hiện lại theo RetryTemplate.

### Cấu hình advice

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.retry.support.RetryTemplate;

@Configuration
class IntegrationRetryAdviceConfiguration {

    @Bean
    RequestHandlerRetryAdvice partnerRetryAdvice(
            RetryTemplate partnerRetryTemplate) {

        RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
        advice.setRetryTemplate(partnerRetryTemplate);

        // Hết retry: tiếp tục phát lỗi để luồng phía trên
        // hoặc error-handling policy giải quyết.
        advice.setRecoveryCallback(context -> {
            throw new IllegalStateException(
                    "Partner request exhausted retry policy",
                    context.getLastThrowable()
            );
        });

        return advice;
    }
}
~~~

**Lưu ý:** mã trên chủ động **rethrow** khi exhausted. Nếu RecoveryCallback trả về giá trị hợp lệ thay vì ném lỗi, tầng gọi có thể coi handler đã được xử lý theo ngữ nghĩa endpoint, nên phải thiết kế kết quả và ack/broker recovery một cách rõ ràng.

### Integration Flow với HTTP outbound gateway

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.integration.http.dsl.Http;

@Configuration
class PartnerHttpFlowConfiguration {

    @Bean
    IntegrationFlow partnerPingFlow(RequestHandlerRetryAdvice partnerRetryAdvice) {
        return IntegrationFlow.from("partnerPingRequests")
                .handle(
                        Http.outboundGateway(
                                "https://partner.example.invalid/health"
                        )
                        .httpMethod(HttpMethod.GET)
                        .expectedResponseType(String.class),
                        endpoint -> endpoint.advice(partnerRetryAdvice)
                )
                .channel("partnerPingResponses")
                .get();
    }
}
~~~

Ví dụ dùng **GET** để tập trung vào wiring của retry, không minh họa một thao tác POST có side effect. Domain example.invalid chỉ mang tính mô tả; cần thay endpoint, timeout, HTTP message converter và chính sách lỗi phù hợp khi tích hợp thật.

**Phạm vi được retry:** advice đặt tại outbound handler này bao quanh **lời gọi của handler đó**, không tự retry transformer trước nó hay mọi bước sau channel partnerPingResponses. Nếu cần retry toàn bộ workflow, phải chọn ranh giới giao dịch/đơn vị công việc riêng; không mặc định kéo cả flow vào một callback.

### Không nên đặt advice một cách đại trà

- Handler ghi dữ liệu **không idempotent**: cần cơ chế chống trùng trước khi retry.
- Handler gửi email hoặc webhook: có thể đã gửi xong dù phía gọi timeout.
- Handler có nhiều tác dụng phụ: retry lại toàn bộ có thể lặp tác dụng phụ đầu tiên.
- Handler đang nằm trong broker container có redelivery: cần cộng tổng retry budget giữa các tầng.
- Handler đang trong transaction: cần rõ transaction rollback/reopen thế nào giữa attempts.

## 10. Retry advice, poller, gateway và MessageChannel khác nhau thế nào?

Một trong những nguồn nhầm lẫn phổ biến là **đặt retry ở đâu**.

| Vị trí | Đơn vị công việc được thử lại | Nguy cơ |
|---|---|---|
| **Bên trong service** dùng RetryTemplate.execute | Khối code của callback | Nếu có side effect trước lỗi, callback chạy lại nó |
| **RequestHandlerRetryAdvice** tại endpoint | Invocation của handler được bọc | Không tự retry upstream source hoặc downstream handler |
| **Poller advice** | Một phần hoạt động polling theo thứ tự advice/poller | Có thể retry việc poll, không đồng nghĩa retry cùng message đã lấy |
| **Error flow / scheduled replay** | Message đã lưu/trạng thái lỗi được phát lại sau | Cần storage, idempotency, giới hạn redrive |
| **JMS/AMQP broker redelivery** | Delivery của message sau rollback/nack/reject theo chính sách | Số lần giao và DLQ phụ thuộc container/broker |
| **Kafka consumer retry/redelivery** | Record/batch qua cơ chế container/error handler/seek/retry topics | Commit offset, partition ordering và concurrency rất quan trọng |
| **HTTP caller retry** | Toàn HTTP request được client gửi lại | Có thể cộng với retry server hoặc gateway, tăng số lần xử lý |

### DirectChannel và ExecutorChannel

**DirectChannel** thường gọi subscriber handler đồng bộ trên thread của bên gửi; exception có thể quay về caller. Nếu một handler giữ thread trong backoff, nguồn inbound/gateway có thể phải đợi.

**ExecutorChannel** có ranh giới bất đồng bộ: exception thường không còn nổi trực tiếp về thread của sender theo cùng cách; cần thiết kế error channel, reject handling và acknowledgement. **MessageChannel không tự tạo retry bền vững**.

Với **QueueChannel** hoặc message store, thông điệp có thể được lưu/đọc lại theo cơ chế riêng, nhưng cũng phải định nghĩa transaction, duplicate detection và quy tắc tiêu thụ.

### Poller là lịch lấy message, không phải broker retry

Một poller có thể gọi adapter theo lịch, ví dụ mỗi 2 giây. Nếu nguồn chưa có file, “không có message” thường không phải exception cần retry. Nếu poller lỗi kết nối, lần poll tiếp theo có thể thử lại; nếu đã lấy message rồi và downstream lỗi, cần xem **acknowledgement và metadata/filter** để biết có đọc lại đúng message đó không.

Không nên giả định “poller chạy lại = message thất bại được redeliver an toàn”.

## 11. Error channel và RecoveryCallback: hết retry thì đi đâu?

Khi RetryPolicy không còn cho phép thêm attempt, hệ thống cần một **terminal outcome** có chủ ý:

- Đẩy message tới **error channel** với metadata lỗi để xử lý/giám sát.
- Ghi vào **dead-letter queue/topic** hoặc kho parking bền vững.
- Chuyển sang hàng **manual review** khi lỗi thuộc dữ liệu/nghiệp vụ.
- Đặt lịch **delayed replay** có giới hạn, nếu lỗi kéo dài vượt phạm vi retry in-process.
- Trả fallback **chỉ khi hợp đồng nghiệp vụ cho phép**.
- Ném lỗi trở lại consumer/gateway để cơ chế bên ngoài quyết định rollback, nack hoặc trả error response.

### Lưu ý quan trọng về recovery

**RecoveryCallback trả về bình thường có thể làm invocation của retry được xem là đã xử lý.** Nếu caller/container dựa vào exception để quyết định không ack, việc nuốt exception có thể gây **mất message không mong muốn**.

Ví dụ chính sách sai:

~~~text
onRetryExhausted:
    log.error("Delivery failed")
    return null

Broker/container:
    handler returned normally -> may acknowledge/commit
Result:
    message đã mất khỏi nguồn, chưa chắc có bản lưu khôi phục
~~~

Hướng đúng phải xác định rõ:

1. Đã ghi message và lỗi vào **kho thất bại bền vững** chưa?
2. Đã xác nhận thành công việc ghi DLQ/parking chưa?
3. Ai chịu trách nhiệm ack/commit nguồn?
4. Nếu ghi DLQ thất bại, exception có được propagate để nguồn **redeliver** không?
5. Có giới hạn số lần **redrive** và đường xử lý poison message không?

Trong Spring Integration, **ErrorMessage** có thể mang exception và original failed message theo ngữ cảnh. Khi sử dụng recovery đưa về error channel, cần hiểu semantics của thành phần được chọn và **kiểm thử end-to-end** trước khi coi việc đẩy vào error channel tương đương “an toàn đã lưu”.

### Mẫu thông tin thất bại

~~~json
{
  "eventId": "order-sync-20261123-0412",
  "correlationId": "corr-77f3",
  "source": "sftp-inbound",
  "destination": "partner-http",
  "operation": "order.upsert",
  "attempts": 4,
  "terminalReason": "RETRY_EXHAUSTED",
  "errorCategory": "TRANSIENT_REMOTE_UNAVAILABLE",
  "lastErrorType": "ServiceUnavailable",
  "payloadReference": "secure-message-store/item-0412",
  "occurredAt": "2026-11-23T08:20:00Z",
  "replayState": "PARKED"
}
~~~

Ví dụ là schema nghiệp vụ, không phải format mặc định của Spring Integration. **Không ghi password, access token, private key, toàn bộ payload khách hàng hoặc credential SFTP vào log thất bại**. PayloadReference chỉ tới kho được quản lý với phân quyền/retention phù hợp.

## 12. Idempotency: điều kiện nền tảng để retry không tạo dữ liệu trùng

**Idempotent** có nghĩa là gọi lại cùng một operation với cùng ý nghĩa không làm kết quả nghiệp vụ phát sinh thêm tác dụng phụ ngoài dự kiến.

### Các tình huống cần cảnh giác

| Operation | Rủi ro retry | Biện pháp |
|---|---|---|
| GET tìm trạng thái | Thường không tạo thay đổi | Vẫn giới hạn retry để tránh tải |
| PUT cập nhật resource bằng nội dung xác định | Thường dễ thiết kế idempotent hơn | Kiểm tra version/concurrency, side effect ẩn |
| POST tạo order/payment | Có thể tạo hai bản ghi | **Idempotency key** và lưu trạng thái kết quả |
| Gửi email | Có thể gửi trùng | Outbox/dedupe và hợp đồng provider nếu có |
| Ghi một dòng database | Có thể insert trùng | Unique constraint theo business event ID; UPSERT phù hợp |
| Consume Kafka/JMS | Broker có thể redeliver | Inbox/dedupe theo event ID, commit/ack đúng thời điểm |
| Copy/move file SFTP | Có thể copy trùng hoặc ghi dở | Temp file, atomic rename khi phù hợp, checksum/manifest, process state |
| Trigger batch job | Có thể tạo nhiều job | Idempotent job launch với stable job key |

### Khóa idempotency ổn định

Nên tạo hoặc nhận **business event ID ổn định** từ upstream, ví dụ order-8291/version-3, thay vì dựa vào MessageHeaders.ID được tạo mới mỗi lần message đi qua flow hoặc mỗi lần broker redelivery.

~~~text
Business event:
    eventId = order-8291-v3
    operation = partner.order.upsert
    target = partner-X

Attempt 1:
    Idempotency-Key = order-8291-v3
    response timeout; outcome unknown

Attempt 2:
    Idempotency-Key = order-8291-v3
    partner trả kết quả đã xử lý trước đó

Local result:
    Một order hợp lệ, không tạo order thứ hai
~~~

Cơ chế này chỉ an toàn nếu **đối tác thực sự hỗ trợ và duy trì idempotency key**, bao gồm phạm vi, tuổi lưu key và cách xử lý request cùng key nhưng payload khác nhau.

### Inbox/outbox và khóa duy nhất

**Inbox/dedupe** ghi nhận business event đã xử lý ở phía nhận, thường đặt cùng transaction với dữ liệu nghiệp vụ nếu cùng database.

**Transactional outbox** ghi trạng thái nghiệp vụ và event cần gửi trong cùng một transaction database; worker công bố event sau và có thể gửi lặp, nên consumer vẫn cần idempotent.

Ví dụ ràng buộc:

~~~sql
-- Bảng minh họa: một eventId chỉ được áp dụng một lần trong phạm vi consumer.
CREATE TABLE processed_events (
    consumer_name VARCHAR(80) NOT NULL,
    event_id VARCHAR(120) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Chỉ đặt unique key chưa đủ nếu thao tác side effect ở hệ thống ngoài đã xảy ra nhưng không thể transaction cùng với bảng này. Khi đó cần **hợp đồng idempotency với phía ngoài**, trạng thái saga/compensation hoặc quy trình đối soát outcome.

## 13. Transaction và acknowledgement: retry không thể tách khỏi commit

Hãy hình dung một message được broker giao tới ứng dụng. Sau khi handler xử lý, consumer có thể phải **ack** hoặc **commit offset**. Nếu handler retry rồi thất bại, điều gì xảy ra phụ thuộc cơ chế transaction/ack ở adapter/container.

### Ba ranh giới khác nhau

1. **Retry attempt:** một lời gọi handler/service được thử nhiều lần.
2. **Transaction:** một đơn vị dữ liệu thay đổi được commit hoặc rollback.
3. **Source acknowledgement/checkpoint:** nguồn tin rằng message/record đã được xử lý xong.

Không phải lúc nào ba ranh giới trùng nhau. Đặc biệt:

- Retry in-process có thể xảy ra **bên trong** một transaction đã bắt đầu.
- Broker có thể **redeliver** cả message sau rollback.
- Kafka có thể **replay record** nếu offset chưa được commit.
- File/SFTP có thể hoặc không có cơ chế chọn lại file dựa trên filter/metadata.

### Lỗi thường gặp: transaction đã bị đánh dấu rollback-only

Giả sử JDBC operation tạo deadlock khiến transaction bị rollback-only. Nếu RetryTemplate nằm **bên trong cùng transaction**, attempt tiếp theo có thể sử dụng context không thể commit được. Một số trường hợp cần **transaction mới cho từng attempt**.

**Nguyên tắc thiết kế:** xác định ranh giới retry so với transaction advice/transaction template; test với deadlock/commit failure thật. Không tự giả định retry lại statement sẽ phục hồi toàn bộ transaction.

### Bảng ra quyết định

| Kiểu nguồn | Khi handler thành công | Khi handler exhausted |
|---|---|---|
| HTTP inbound gateway | Trả response theo hợp đồng | Trả lỗi phù hợp; client có thể retry |
| File/SFTP inbound poller | Cập nhật trạng thái xử lý/file theo flow | Cần chính sách re-poll/parking; không có broker ack mặc định |
| JMS listener | Commit/ack theo container/transaction | Rollback/redelivery hoặc DLQ theo thiết kế |
| AMQP listener | Ack hoặc transaction commit | Nack/reject/requeue/DLX/DLQ tùy container/broker |
| Kafka consumer | Commit offset theo container/ack mode | Seek/redelivery/retry topic/DLT theo cấu hình |
| JDBC polling | Update trạng thái hàng/transaction theo thiết kế | Row có thể được chọn lại; cần trạng thái lease/retry/dead |

**Không nên suy từ tên adapter rằng cơ chế ack giống nhau**. Cần xem cấu hình adapter/container và kiểm thử trường hợp lỗi.

## 14. File inbound/outbound: retry cần biết trạng thái file

Spring Integration File adapters là ví dụ rõ về khác biệt giữa **retry thao tác I/O** và **retry xử lý message**.

### Inbound file

Một poller lấy file từ thư mục. Các tình huống:

- File đang ghi dở: ứng dụng đọc được một phần nhưng parse lỗi.
- File có nội dung invalid: retry parse không làm nó đúng lên.
- File đã được chọn một lần qua accept-once filter: handler lỗi không bảo đảm lần poll sau lại thấy file.
- Metadata store chỉ lưu in-memory: restart có thể nhận file lại và tạo duplicate.
- File đã move/archive trước khi downstream thành công: retry khó tìm source.

### Một quy trình an toàn hơn

1. Nguồn ghi file bằng tên tạm, ví dụ order-8291.part.
2. Sau khi ghi xong và xác nhận, nguồn **rename** sang order-8291.ready trên cùng filesystem khi hỗ trợ atomic rename.
3. Inbound adapter chỉ nhận file sẵn sàng.
4. Tạo eventId ổn định từ tên file/manifest hoặc nội dung được ký theo hợp đồng.
5. Parse/validate; invalid đưa sang quarantine với lý do.
6. Xử lý nghiệp vụ idempotent; chỉ archive/delete sau khi xác nhận thành công.
7. Nếu lỗi tạm thời downstream, retry có giới hạn; nếu exhausted, lưu trạng thái PARKED và có đường replay.

**Không phải mọi file system hỗ trợ rename atomic theo cùng cách.** Nếu nguồn là object storage hoặc hệ thống ngoài, cần cơ chế manifest/ready flag hoặc hợp đồng xuất bản tương ứng.

### Outbound file

Ghi file cũng có vấn đề partial output. Nếu lần ghi trước tạo file dở rồi retry, có thể:

- Ghi đè gây dữ liệu không nhất quán;
- Tạo nhiều file;
- Người nhận đọc file chưa hoàn chỉnh.

Giải pháp: ghi ra temporary path, đồng bộ/đóng file, sau đó publish bằng rename/manifest theo khả năng đích, xác định chính sách overwrite và checksum. Với file outbound qua adapter, phải kiểm soát lựa chọn tên file và xử lý collision theo eventId.

## 15. SFTP: reconnect không phải replay an toàn

SFTP inbound/outbound thường đối diện **mất mạng, timeout, session stale, permission denied hoặc transfer dở**.

### Phân loại lỗi

| Sự cố | Retry? | Lý do |
|---|---|---|
| Kết nối tạm mất/timeout | Có thể, giới hạn và backoff | Network có thể phục hồi |
| Server SFTP quá tải | Có thể, với delay/jitter | Tránh retry storm |
| Sai private key hoặc host key validation | Không tự retry vô hạn | Cần sửa xác thực/trust; không giảm kiểm tra host key |
| Permission denied trên thư mục đích | Thường không | Cần sửa quyền/trạng thái đích |
| File nguồn không tồn tại | Tùy hợp đồng | Có thể nguồn chưa publish, hoặc tên file sai |
| Upload hoàn tất nhưng mất ACK | Không rõ outcome | Kiểm tra file đích/checksum/manifest trước khi gửi lại |
| File bị lấy trong lúc đang ghi | Không retry parse vô hạn | Cần quy tắc file ready/rename |

### Inbound đồng bộ file từ SFTP

Thông thường cần quan tâm:

- Cơ chế nhận biết **file đã hoàn tất upload**;
- Remote/local filter và trạng thái accept-once;
- Metadata store có bền qua restart không;
- Hành vi tải file tạm, rename local, xóa remote;
- Chính sách xử lý lỗi parse hoặc downstream;
- Replay file dựa theo eventId và checksum, không dựa duy nhất vào timestamp.

**Retry advice ở handler HTTP phía sau không tự khiến SFTP inbound adapter tải lại file**. Nếu file đã được đánh dấu đã nhận, phải có chiến lược parking/replay độc lập.

### Outbound SFTP

Nếu outbound upload thành công nhưng response thất lạc, retry cùng tên file có thể ghi đè hoặc tạo phiên bản mới. Nên thiết kế tên đích xác định bởi eventId, upload tạm rồi publish, đối soát size/hash/manifest và quy tắc overwrite rõ. Không giả định mọi remote SFTP hỗ trợ atomic rename khi vượt filesystem.

## 16. HTTP outbound gateway: chọn lỗi và hợp đồng idempotency

**HTTP outbound gateway** gửi request và chờ response, thường phù hợp với request–reply. Retry ở handler làm **gửi lại request HTTP**, nên an toàn phụ thuộc vào HTTP method và hợp đồng của đối tác.

### Bảng quyết định gợi ý

| Status/exception | Có thể retry? | Điều kiện |
|---|---|---|
| Timeout kết nối/đọc | Có thể | Có timeout/budget; outcome của request có thể không rõ |
| 429 Too Many Requests | Thường có, nhưng không ngay lập tức | Tôn trọng Retry-After/rate limit; có idempotency nếu có side effect |
| 503 Service Unavailable | Có thể | Backoff/jitter và giới hạn attempts |
| 502/504 | Có thể trong một số trường hợp | Cân nhắc outcome và khả năng lặp tác dụng phụ |
| 400 Bad Request | Thường không | Cần sửa payload/schema |
| 401 Unauthorized | Thường không retry cùng credential | Refresh/rotate credential theo luồng riêng nếu được phép |
| 403 Forbidden | Không retry thông thường | Xác minh quyền/policy |
| 404 Not Found | Tùy hợp đồng | Eventual consistency có thể cho phép retry có hạn |
| 409 Conflict | Tùy nghiệp vụ | Có thể là already-processed hoặc xung đột không thể tự xử |
| 500 Internal Server Error | Không mặc định tất cả đều retry | Một số server vẫn đã commit side effect trước lỗi |

### Không xóa dấu vết outcome unknown

~~~text
Client                     Partner
  | -- POST /payments ------> |
  |                           | ghi payment thành công
  | <--- response bị mất ----- |
  |                           |
  | -- POST lại ------------> |
  |                           | có nguy cơ payment thứ hai
~~~

Nếu không có idempotency contract, một timeout **không chứng minh request chưa được xử lý**. Giải pháp có thể là:

- Gửi cùng **Idempotency-Key** ổn định qua mọi attempt.
- Gọi API tra cứu trạng thái theo transactionId trước khi retry.
- Hợp đồng upsert theo business key/version.
- Dùng outbox và đối soát sau timeout.
- Escalate thủ công khi không thể xác minh kết quả.

### Phân biệt Gateway inbound và outbound

- **HTTP inbound gateway:** client gọi vào ứng dụng; nếu server trả 5xx/timeout, **client** có thể retry. Cần idempotency phía inbound.
- **HTTP outbound gateway:** ứng dụng gọi partner; RetryAdvice có thể gửi lại HTTP request.
- Khi inbound lại gọi outbound, nếu cả client lẫn service cùng retry **4 attempts**, partner có thể nhận tối đa **4 × 4 = 16 lần gọi** cho một business event nếu tất cả lần đều lỗi và không có giới hạn khác.

Vì vậy cần **ngân sách retry end-to-end**. Không cấu hình retry độc lập ở mọi tầng chỉ vì mỗi tầng đều hỗ trợ RetryTemplate.

## 17. JMS và AMQP: phối hợp retry với broker redelivery

JMS/AMQP hỗ trợ các cơ chế **delivery, acknowledge/commit, rollback hoặc dead-letter** nhưng chi tiết thuộc broker và container. Spring Integration có inbound/outbound adapters/gateways liên quan; retry in-process chỉ là một tầng.

### Ba mô hình phổ biến

1. **Short in-process retry:** handler thử nhanh vài lần với lỗi transient, backoff ngắn.
2. **Broker redelivery:** sau exhaustion, xử lý rollback/nack/requeue để broker giao lại theo cấu hình.
3. **Dead-letter / delayed replay:** sau ngưỡng thất bại, chuyển sang DLQ/parking, xử lý hoặc replay có kiểm soát.

Nếu **cả retry advice và broker redelivery** cùng lặp 5 lần, tổng số handler invocation có thể thành **25**, chưa tính các lớp khác. Số lần thực tế phụ thuộc container, requeue và recovery.

### JMS

Đối với JMS listener/gateway:

- Xác định **session transacted** hoặc acknowledgement mode.
- Khi handler thất bại và exception được truyền ra, container có thể rollback/redeliver theo cấu hình.
- Nếu RecoveryCallback nuốt lỗi rồi trả bình thường, container có thể xem message đã xử lý.
- Message có thể được giao lại sau crash dù handler đã tạo side effect bên ngoài; cần idempotency.
- Poison message cần giới hạn redelivery và DLQ, không chặn mãi cả consumer.

### AMQP/RabbitMQ

Đối với AMQP:

- Manual/auto ack, reject/nack, requeue, dead-letter exchange và prefetch ảnh hưởng đến recovery.
- **Requeue liên tục không có backoff** có thể tạo hot loop và tiêu tốn CPU/broker.
- Nếu cần delayed retry, có thể dùng **retry queue có TTL, delayed exchange nếu được hỗ trợ, hoặc cơ chế retry của listener/framework** được cấu hình rõ.
- Giới hạn số lần redelivery bằng metadata/cơ chế đáng tin; không hoàn toàn dựa vào một header do nguồn không tin cậy gửi.

### Một luồng an toàn tham chiếu

~~~mermaid
flowchart TD
    B["Broker giao message"] --> H["Consumer / Integration handler"]
    H --> P{"Xử lý thành công?"}
    P -->|"Có"| A["Commit / ack theo container"]
    P -->|"Không"| R{"Retry in-process còn budget?"}
    R -->|"Có"| W["Backoff rồi thử handler lại"]
    W --> P
    R -->|"Không"| D{"Recovery được bảo đảm?"}
    D -->|"Có kho bền vững"| Q["DLQ / parking / delayed retry"]
    Q --> K["Ack nguồn sau khi bảo toàn message theo thiết kế"]
    D -->|"Chưa bảo toàn"| E["Propagate error, rollback/nack theo chính sách"]
    E --> B
~~~

Sơ đồ mô tả **trách nhiệm nghiệp vụ**. Không suy rằng việc ghi DLQ và ack nguồn là atomic nếu sử dụng **hai hệ thống độc lập** mà không có transaction/hợp đồng bảo đảm tương ứng.

## 18. Kafka: offset commit, retry và thứ tự partition

Kafka làm rõ khác biệt giữa **retry handler** và **replay record**. Nếu consumer nhận một record, xử lý sai rồi chưa commit offset, record đó có thể được xử lý lại. Nếu offset được commit trước khi side effect hoàn tất, có thể mất message.

### Những điều cần quyết định

- Consumer sử dụng **record hay batch**?
- Ai quản lý **ack/commit offset**?
- Lỗi được xử lý bằng cơ chế của listener container/Spring Kafka, bằng RequestHandlerRetryAdvice, hay retry topics?
- Record lỗi có làm **block partition** không?
- Nếu chuyển sang retry topic, thứ tự xử lý giữa các record cùng key còn được bảo đảm như trước không?
- Khi hết lần thử, record vào DLT như thế nào và ai duyệt replay?
- Một record được xử lý lại có tạo duplicate database/outbound API không?

### Điểm quan trọng

**RetryTemplate ở service activator không tự thực hiện seek Kafka, không tự commit offset và không tự cấu hình retry topic/DLT.** Những trách nhiệm này thuộc về cơ chế Kafka consumer/listener container, cấu hình Spring Kafka và thiết kế flow.

Một chiến lược có thể là:

~~~text
Kafka record
  -> consumer/adapter
  -> validate
  -> business handler với retry ngắn cho transient dependency
  -> success: commit theo cấu hình container
  -> exhausted: propagate tới error handling
  -> container retry / DLT theo policy
  -> DLT được giám sát và có manual/scheduled redrive
~~~

Nếu ứng dụng dùng **Kafka transaction** hoặc cơ chế exactly-once trong phạm vi Kafka, vẫn không được tự suy ra HTTP partner hoặc database ngoài transaction sẽ có exactly-once side effect. Cần idempotent consumer/outbox hoặc giao thức phối hợp riêng.

### Thứ tự và throughput

Một poison record trên partition có thể làm giảm throughput nếu consumer liên tục retry nó. Chuyển record sang retry topic hoặc DLT giúp giải phóng đường xử lý, nhưng **có thể làm mất thứ tự nghiệp vụ** nếu record sau được xử lý trước record đang retry. Phải quyết định yêu cầu ordering theo aggregate/key; không chọn retry topology chỉ dựa trên độ trễ.

## 19. Database/JDBC polling: transaction và chọn lại bản ghi

Spring Integration có adapter để polling dữ liệu hoặc ghi database. Retry ở đây thường liên quan:

- DB connection timeout;
- Deadlock hoặc serialization conflict;
- Lock timeout có thể tạm thời;
- Vi phạm unique constraint;
- Schema migration chưa tương thích;
- Downstream lỗi sau khi row đã được đánh dấu processed.

### Pattern polling với trạng thái

~~~text
NEW -> CLAIMED -> PROCESSING -> DONE
                  |
                  v
               RETRY_WAIT -> PROCESSING
                  |
                  v
                 PARKED
~~~

Một hàng cần có **stable ID**, số lần thử, owner/lease, trạng thái, nextAttemptAt và lý do lỗi. Nếu worker crash ở PROCESSING, cần cơ chế lease expiry/claim lại có kiểm soát; nếu không sẽ có hàng kẹt vĩnh viễn.

### Ví dụ schema logic

~~~sql
CREATE TABLE integration_jobs (
    id BIGINT PRIMARY KEY,
    business_event_id VARCHAR(120) NOT NULL UNIQUE,
    status VARCHAR(32) NOT NULL,
    attempt_count INT NOT NULL,
    next_attempt_at TIMESTAMP,
    lease_owner VARCHAR(100),
    lease_until TIMESTAMP,
    last_error_category VARCHAR(64)
);
~~~

**Mẫu này chưa hoàn chỉnh cho concurrency production.** Cần transaction, claim atomic, index, optimistic locking/skip locked khi phù hợp, cùng chính sách retry và idempotency.

### Transaction boundary

- Deadlock trong xử lý database có thể cần **rollback toàn transaction và mở transaction mới** trước attempt sau.
- Nếu đã gửi HTTP thành công rồi transaction local rollback, chạy lại transaction có thể **gửi HTTP hai lần**.
- Nếu cập nhật status DONE trước khi gửi outbound thành công, có thể mất message.
- **Transactional outbox** giúp ghi dữ liệu và ý định gửi trong một transaction; sender retry theo event ID và phía nhận xử lý idempotent.

Không gộp mọi việc vào một RetryCallback khổng lồ mà không có thiết kế cho side effects.

## 20. Retry trong hệ thống bất đồng bộ: thread, backpressure và deadline

RetryTemplate với backoff thông thường giữ quá trình thực thi trong một chuỗi attempt. Khi xử lý trên số thread nhỏ:

- Nhiều handler chờ backoff có thể làm queue tăng.
- MessageChannel kiểu synchronous có thể khiến inbound HTTP gateway bị chậm theo.
- Broker consumer có thể giữ delivery/partition lâu, ảnh hưởng rebalance, prefetch hoặc throughput.
- Nhiều instance retry đồng thời làm tăng áp lực vào dịch vụ đã quá tải.
- Nếu deadline của business request đã hết, retries muộn có thể gây side effect không còn mong muốn.

### Công thức ước lượng năng lực

Giả sử một worker thread xử lý mỗi message thành công trong 100 ms. Khi bình thường, thông lượng lý thuyết là khoảng **10 message/s/thread** (chưa tính overhead).

Nếu đối tác lỗi và mỗi message tốn 10 giây cho chuỗi retry, thông lượng giảm xuống khoảng **0,1 message/s/thread**. Với 10 threads, hệ thống chỉ xử lý khoảng 1 message/s và backlog có thể tăng nhanh.

Đây chỉ là mô hình đơn giản, không phải dự báo chính xác. Cần đo **P95/P99 handler latency, concurrent retries, queue depth và broker lag** để quyết định giới hạn retries in-process.

### Khi nên chuyển sang delayed retry

Nếu lỗi dự kiến phục hồi sau vài phút hoặc hàng giờ, không nên giữ thread hoặc giữ một HTTP connection trong thời gian dài. Nên lưu message và schedule retry bền vững qua queue/topic/job store, có:

- Retry state và nextAttemptAt;
- Attempt count bền qua restart;
- Stable eventId và idempotency;
- Giới hạn tuổi message;
- Giám sát backlog và khả năng replay thủ công;
- Terminal DLQ/PARKED và người chịu trách nhiệm.

**Retry tại handler và delayed replay là hai tầng có ranh giới khác nhau**, cần thống nhất tổng retry budget.

## 21. Circuit breaker, rate limit và timeout bổ trợ retry thế nào?

Retry chỉ hợp lý khi lỗi có cơ hội tự phục hồi. Nếu cả hệ thống đích đang down, hàng trăm instance cùng retry có thể khiến tình trạng xấu hơn.

| Cơ chế | Giải quyết | Điểm cần nhớ |
|---|---|---|
| **Retry** | Lỗi tạm thời cho từng operation | Giới hạn attempts và kiểm soát side effect |
| **Timeout** | Tránh một attempt chờ vô hạn | Phân biệt timeout kết nối, đọc và tổng deadline |
| **Circuit breaker** | Giảm lời gọi vào hệ thống đang lỗi liên tục | Khi open, thường không gọi đích; có half-open/khôi phục theo policy |
| **Rate limiter** | Giới hạn số request theo thời gian | Quan trọng với 429 và đối tác có quota |
| **Bulkhead** | Cô lập tài nguyên cho nhóm workload/phụ thuộc | Tránh một partner down giữ hết thread |
| **Backpressure** | Hạn chế upstream đẩy nhanh hơn downstream xử lý được | Tránh tồn đọng queue vô hạn |
| **DLQ/parking** | Bảo toàn failed message cho điều tra/redrive | Không tự sửa invalid payload |
| **Idempotency** | Ngăn side effect trùng khi message được gửi lại | Là yêu cầu riêng, không do retry cung cấp |
| **Outbox/inbox** | Giảm khoảng hở giữa dữ liệu nghiệp vụ và message | Vẫn cần transaction/uniqueness và recovery |

### Thứ tự áp dụng không có đáp án chung

Một phương án thực dụng:

1. Kiểm tra dữ liệu và phân loại operation;
2. Lấy quyền sử dụng rate limit/bulkhead khi phù hợp;
3. Circuit breaker đánh giá trạng thái dependency;
4. Một attempt với timeout rõ;
5. Retry có backoff nếu lỗi phù hợp và còn deadline;
6. Sau exhausted, durable recovery.

Việc ghép advice/circuit breaker theo thứ tự khác nhau sẽ tạo **ngữ nghĩa số lần gọi khác nhau**. Cần ghi cấu hình và chạy test chứng minh khi circuit open không xảy ra thêm cuộc gọi ngoài ý muốn.

## 22. Logging, tracing và metrics cho retry

Không nên chỉ log “Retrying request...” từng lần rồi coi hệ thống có observability. Cần biết số attempts, nguyên nhân, thời gian, trạng thái cuối và nguồn message.

### Các trường nên ghi

| Trường | Mục đích |
|---|---|
| eventId | Nhận dạng business event ổn định qua redelivery/replay |
| correlationId/traceId | Liên kết inbound, outbound và downstream |
| flowId/endpointId | Biết adapter/handler nào retry |
| attemptNumber/maxAttempts | Phân biệt attempt và retry; tránh nhầm 4 attempts = 4 retries |
| errorCategory | Transient, rate limit, invalid data, auth, unknown outcome |
| exceptionType | Phân loại kỹ thuật; không cần nguyên payload |
| backoffDuration | Đo thời gian chờ |
| targetSystem | Đối tác HTTP, SFTP, JMS/AMQP, Kafka hoặc DB |
| finalOutcome | SUCCESS, RETRY_EXHAUSTED, PARKED, DLQ, CANCELLED |
| ackOrCommitOutcome | Broker/source đã được xác nhận hoàn tất chưa |
| processingLatency | Độ trễ tổng và mỗi attempt |
| idempotencyKeyRef | Tham chiếu đã xử lý thích hợp; không chứa secret |

**Không log** password, private key SFTP, bearer token, full payment payload hoặc thông tin khách hàng không cần thiết. Giữ trace context theo cách không vô tình phát tán thông tin nhạy cảm sang đối tác.

### Metric đề xuất

| Metric | Định nghĩa | Tại sao cần |
|---|---|---|
| **retry_attempts_total** | Tổng số attempts theo flow và error category | Tìm endpoint có lỗi tăng |
| **retry_exhausted_total** | Số chuỗi retry kết thúc không thành công | Phát hiện recovery load |
| **retry_success_after_retry_total** | Số message thành công sau ít nhất một retry | Đánh giá hiệu quả retry |
| **retry_backoff_seconds** | Phân phối thời gian chờ | Kiểm tra budget và latency |
| **outbound_duration_seconds** | Thời gian attempt và tổng xử lý theo nhãn tách biệt | Phát hiện bottleneck |
| **dead_letter_backlog** | Message đang PARKED/DLQ theo tuổi và criticality | Ngăn thông điệp lỗi bị bỏ quên |
| **duplicate_effect_prevented_total** | Duplicate business event được dedupe | Theo dõi redelivery và idempotency |
| **source_redeliveries_total** | Số lần broker/file/job redrive giao lại | Tách redelivery với in-process retries |
| **broker_lag / queue_depth** | Số message đang chờ | Đánh giá backpressure |
| **terminal_failure_age** | Tuổi lỗi chưa xử lý lớn nhất và P95 | Ưu tiên backlog có tác động nghiệp vụ |

**Cardinality:** không gắn eventId hoặc orderId trực tiếp vào nhãn metric (ví dụ Prometheus labels), vì mỗi message sẽ tạo time series mới. Dùng ID trong log/tracing, nhãn metric chỉ theo flow, endpoint, error category và outcome có số lượng hữu hạn.

### Bộ SLO minh họa

- Tỷ lệ message hợp lệ xử lý thành công theo cửa sổ 24 giờ/7 ngày;
- P95 end-to-end processing latency với N rõ;
- Không có message business-critical trong PARKED quá deadline;
- Tỷ lệ duplicate business effects = 0 trong các bài kiểm thử đã định nghĩa;
- Tỷ lệ terminal errors có đủ metadata để replay;
- Lỗi đối tác không làm tăng backlog vượt ngưỡng vận hành quá thời gian quy định.

Các ngưỡng phải do tổ chức xác định theo nghiệp vụ; không có một mức retry và SLO phù hợp cho mọi hệ thống.

## 23. Bộ kiểm thử bắt buộc

Kiểm thử retry cần kiểm tra **kết quả cuối cùng và side effect**, không chỉ xác nhận mock được gọi đủ số lần.

| ID | Kịch bản | Kết quả mong đợi |
|---|---|---|
| R1 | Handler thành công ngay attempt đầu | Một lần gọi; không backoff |
| R2 | Hai lỗi transient rồi thành công | Ba attempts; trả kết quả đúng |
| R3 | Transient lỗi liên tục với maxAttempts=4 | Chính xác bốn attempts và đi recovery |
| R4 | Payload invalid | Không retry; đi nhánh xử lý invalid |
| R5 | HTTP 401/403 | Không lặp lại request với cùng credential |
| R6 | HTTP 429 + Retry-After | Delay phù hợp chính sách; không retry storm |
| R7 | HTTP POST thành công nhưng response timeout | Không tạo hai business records nhờ idempotency/đối soát |
| R8 | RecoveryCallback ném exception | Caller/container nhận lỗi phù hợp; không ack nhầm |
| R9 | RecoveryCallback ghi DLQ rồi trả bình thường | Chỉ ack khi message đã bảo toàn đúng theo thiết kế |
| R10 | Ghi DLQ thất bại | Không mất message; rollback/nack hoặc đường bảo toàn thay thế |
| R11 | Hai tầng retry lồng nhau | Tính được và giới hạn tổng attempts |
| R12 | Exponential backoff | Khoảng nghỉ phù hợp, không vượt trần |
| R13 | Nhiều consumer lỗi đồng thời | Không vượt concurrency/rate budget |
| R14 | File inbound parse invalid | Quarantine một lần, không poll vô hạn gây duplicate |
| R15 | SFTP upload bị timeout sau khi remote đã nhận | Có đối soát/checksum, không nhân đôi file |
| R16 | JMS listener rollback sau exhausted | Redelivery/DLQ theo cấu hình; business effect không trùng |
| R17 | AMQP consumer nack/requeue | Không hot loop không giới hạn; có DLQ |
| R18 | Kafka record xử lý lỗi | Offset không bị commit sai; thứ tự theo hợp đồng |
| R19 | Kafka DLT replay cùng eventId | Deduplication vẫn bảo đảm |
| R20 | JDBC deadlock | Retry transaction theo scope mới, commit đúng một lần |
| R21 | Crash giữa outbound side effect và local commit | Dedupe/outbox/đối soát xử lý được outcome unknown |
| R22 | Backlog lớn khi đối tác down | Giới hạn threads/memory, có alert |
| R23 | Error channel thiếu subscriber | Không nuốt terminal failure; đường phục hồi rõ |
| R24 | Chính sách retry được sửa maxAttempts | Contract tests phát hiện thay đổi số calls và latency |
| R25 | Worker/ứng dụng restart giữa lần retry | Phân biệt retry in-memory mất và durable replay |
| R26 | Credential hết hạn hoặc sai quyền | Không retry mãi; chuyển xử lý vận hành phù hợp |

### Ví dụ kiểm thử RetryTemplate không cần hệ thống ngoài

~~~java
import java.io.IOException;
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger invocations = new AtomicInteger();

String result = retryTemplate.execute(ctx -> {
    int current = invocations.incrementAndGet();
    if (current < 3) {
        throw new IOException("Temporary remote failure");
    }
    return "OK";
});

// Kỳ vọng:
// result == "OK"
// invocations.get() == 3
// backoff diễn ra giữa attempt 1/2 và 2/3
~~~

Mẫu này giả sử RetryPolicy cho phép IOException và maxAttempts ít nhất 3. Để kiểm chứng thời gian backoff ổn định, có thể dùng **BackOffPolicy test double/clock abstraction** thay vì assert chặt thời gian wall clock (dễ flaky do scheduling).

### Kiểm thử thực tế phải có negative cases

Một test chỉ kiểm tra “retry gặp lỗi 503 thì cuối cùng thành công” chưa đủ. Cần test rằng:

- Một request không idempotent **không** tạo hai side effects;
- Một invalid message **không** bị retry vô hạn;
- Một message thất bại **không** bị ack rồi mất trước khi vào kho recovery;
- Retry trên SFTP/File **không** làm state filter/metadata store sai;
- Broker redelivery và retry handler **không** nhân tổng attempts vượt budget;
- Khi worker restart, thông điệp pending còn được quản lý đúng.

## 24. Bài tập tình huống: đồng bộ đơn hàng qua SFTP và HTTP

### Bối cảnh

Một doanh nghiệp nhận file đơn hàng từ đối tác bằng SFTP. Spring Integration tải file, parse mỗi record thành message, sau đó gọi HTTP outbound gateway để tạo đơn hàng trên hệ thống ERP. Kết quả được ghi database và gửi thông báo qua AMQP.

Luồng:

~~~text
SFTP inbound adapter / poller
   -> local file staging
   -> parse + validate
   -> message(eventId=orderId/version)
   -> HTTP outbound gateway (ERP)
   -> database status update
   -> AMQP outbound adapter
   -> archive file
~~~

Các điều kiện:

- Đối tác SFTP đôi khi upload file chậm.
- ERP trả 503 vài phút mỗi ngày.
- ERP có lúc ghi đơn hàng xong nhưng response timeout.
- Một số record thiếu customerId.
- Database đôi khi gặp deadlock.
- RabbitMQ đôi khi mất kết nối.
- Hệ thống có **maxAttempts=4** cho outbound HTTP nhưng cũng có lịch replay file khi thất bại.
- Tổ chức yêu cầu không tạo đơn hàng trùng và không để record lỗi biến mất.

### Diễn biến giả lập

| Thời điểm | Sự kiện |
|---|---|
| 08:00 | File orders-001.part đang upload, chưa sẵn sàng |
| 08:02 | Đối tác đổi tên thành orders-001.ready |
| 08:03 | Poller nhận file; record A hợp lệ, record B thiếu customerId |
| 08:04 | HTTP tạo order A: ERP ghi xong nhưng response timeout |
| 08:04–08:05 | RetryTemplate thử lại với backoff, có nguy cơ tạo duplicate |
| 08:06 | Database update status A bị deadlock |
| 08:07 | Outbound AMQP không gửi được thông báo |
| 08:10 | Replay scheduler thử xử lý lại file |
| 09:00 | Đội vận hành thấy số file processed cao nhưng ERP có đơn hàng trùng |

### Nhiệm vụ

1. Xác định lỗi nào cần retry và lỗi nào không nên retry.
2. Chọn **ranh giới RetryTemplate** phù hợp: tại HTTP outbound gateway, JDBC transaction, AMQP send hay cả flow?
3. Đề xuất **idempotency key và trạng thái xử lý** cho từng record.
4. Thiết kế khi HTTP response timeout nhưng ERP có thể đã tạo order.
5. Thiết kế recovery/DLQ/parking cho record B invalid và record A exhausted.
6. Giải thích tác động của replay file tới accept-once filter và duplicate effect.
7. Xác định đâu là **ack/commit/transaction boundary** ở mỗi hệ thống.
8. Đề xuất ít nhất năm metric và sáu test case để xác nhận hệ thống đáng tin.

### Gợi ý lời giải

**1. Phân loại lỗi.** File đang upload chưa hoàn tất nên không xử lý; dùng temporary filename/ready marker. Record B thiếu customerId là lỗi payload, không retry tự động. HTTP 503 có thể retry có backoff/rate budget. Timeout sau POST là outcome unknown, chỉ retry nếu ERP hỗ trợ idempotency hoặc có API tra cứu trạng thái. JDBC deadlock có thể retry transaction phù hợp; AMQP mất kết nối tạm có thể retry/durable publish.

**2. Ranh giới.** Retry ngắn ở handler HTTP với operation idempotent; transaction retry riêng cho cập nhật DB; message gửi AMQP nên cân nhắc transactional outbox để đảm bảo event không mất nếu DB commit nhưng broker down. **Không retry cả flow từ lúc nhận file** vì dễ gửi lại HTTP, DB và notification trùng.

**3. EventId ổn định.** Mỗi record có khóa **partnerId + orderId + businessVersion**, không lấy message UUID của mỗi attempt. Lưu trạng thái như RECEIVED, VALIDATED, ERP_PENDING, ERP_CONFIRMED, NOTIFICATION_PENDING, DONE, PARKED cùng attempt count và payload reference bền vững. DB unique constraint ngăn hai record cùng eventId.

**4. Outcome unknown.** Gửi cùng Idempotency-Key tới ERP nếu hợp đồng hỗ trợ; nếu không, tra cứu orderId trước khi thử lại, hoặc đưa vào đối soát thủ công. Không coi timeout là chắc chắn chưa ghi.

**5. Recovery.** Invalid record B vào quarantine với reason code; record A exhausted vào PARKED/DLQ có replay được kiểm soát. Chỉ đánh dấu file hoàn tất khi mọi record đã DONE hoặc được bảo toàn ở trạng thái terminal theo quy tắc nghiệp vụ. Khi ghi parking thất bại, không được xóa file/source state gây mất dữ liệu.

**6. Replay.** Accept-once filter/metadata store có thể khiến file không được poll lại, hoặc nếu reset metadata thì file được nhận lại với message IDs mới. Vì vậy phải replay theo **business event IDs và trạng thái lưu bền**, không đặt kỳ vọng vào in-memory retry context.

**7. Các ranh giới.** SFTP không có ack message kiểu Kafka; cần quản lý file staging/archive/metadata. HTTP có request/response nhưng outcome có thể không rõ. DB transaction commit riêng; RabbitMQ publish và consumer ack/confirm riêng. Không có distributed transaction tự động giữa SFTP, ERP, DB và RabbitMQ. Outbox/inbox và idempotency giảm khoảng hở.

**8. Metrics/tests.** Theo dõi retry attempts theo error category, retry exhausted, ERP duplicate prevented, parking backlog age, HTTP latency, DB deadlock retries, AMQP publish failure. Test file đang upload, invalid record, ERP 503, response timeout đã ghi order, DB rollback, AMQP down, process restart và replay cùng eventId.

### Phương án kiến trúc cải thiện

~~~mermaid
flowchart TD
    S["SFTP file hoàn tất"] --> V["Stage + parse/validate"]
    V -->|"Invalid"| Q["Quarantine record có lý do"]
    V -->|"Valid"| I["Inbox: unique business eventId"]
    I --> P["ERP sync state machine"]
    P --> H{"ERP request idempotent?"}
    H -->|"Có"| R["Retry ngắn + backoff + budget"]
    H -->|"Không / outcome unknown"| C["Tra cứu trạng thái / reconcile"]
    R --> O["ERP_CONFIRMED"]
    C --> O
    R -->|"Exhausted"| K["PARKED / durable delayed retry"]
    O --> D["DB transaction: trạng thái + Outbox event"]
    D --> A["Outbox publisher gửi AMQP"]
    A -->|"Broker unavailable"| A
    A --> F["Confirm publish + mark outbox sent"]
    F --> Z["DONE + archive theo policy"]
    K --> M["Alert + controlled redrive"]
    Q --> M
~~~

Sơ đồ mô tả **mục tiêu nghiệp vụ**, không phải flow có sẵn trong framework. Vòng lặp gửi AMQP phải có delayed scheduling, backoff, giới hạn attempts và giám sát; không được là busy loop vô hạn. Việc xác nhận publish còn phụ thuộc broker confirm semantics và idempotency ở consumer.

## 25. Anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách sửa |
|---|---|---|
| Retry mọi Exception | Lỗi vĩnh viễn vẫn giữ thread, tăng tải | Classifier theo loại lỗi và operation |
| maxAttempts không tính lần đầu | Vượt số request dự kiến | Ghi rõ attempt vs retry |
| Không có backoff | Retry storm khi partner down | Backoff + jitter + rate budget |
| Retry HTTP POST không idempotency | Order/payment trùng | Idempotency key/query status/outbox |
| Nuốt exception trong RecoveryCallback | Broker có thể ack message chưa bảo toàn | Durable parking/DLQ hoặc propagate |
| Không phân biệt retry và redelivery | Tổng số lần gọi nhân lên | Tổng retry budget end-to-end |
| Dùng message UUID làm business key | Dedupe thất bại sau redelivery | Stable eventId từ nghiệp vụ |
| Dùng retry advice để chữa file invalid | Message poison không bao giờ thành công | Quarantine và sửa dữ liệu |
| Retry JDBC trong transaction đã rollback-only | Vẫn lỗi commit | Tái tạo transaction đúng ranh giới |
| Tin rằng Kafka offset commit tự bao side effect ngoài Kafka | Duplicate hoặc mất nghiệp vụ | Idempotent consumer/outbox |
| Dùng errorChannel như kho bền vững mặc định | Mất message khi restart hoặc subscriber lỗi | Bền vững hóa parking/DLQ |
| Không đặt timeout | Attempt treo, không có retry | Per-attempt timeout + total deadline |
| Cho retries giữ hết worker threads | Backlog và latency tăng | Delayed retry, bulkhead, concurrency limit |
| Gửi lại SFTP upload khi không biết outcome | File trùng/partial | Temporary name, checksum, reconcile |
| Bật mọi retry layer mặc định | 4 × 4 × 4 attempts vô ý | Chủ sở hữu retry, giới hạn từng ranh giới |
| Không có terminal outcome | Message lỗi bị quên hoặc loop vĩnh viễn | PARKED/DLQ với owner, alert, replay |

## 26. Checklist triển khai thực tế

- [ ] Có **hợp đồng message**: eventId, schema/version, correlationId, payload reference, expiry và sensitivity.
- [ ] Xác định từng điểm inbound/outbound adapter, gateway, poller, channel và handler trong flow.
- [ ] Phân loại lỗi **transient/permanent/unknown outcome**, không retry tất cả.
- [ ] RetryPolicy có **maxAttempts tổng**, điều kiện dừng và deadline rõ.
- [ ] BackOffPolicy có giới hạn, dùng jitter/rate limit khi nhiều client có thể retry đồng thời.
- [ ] Mỗi lời gọi ngoài có connect/read/operation timeout phù hợp.
- [ ] Không lồng retry ở handler, HTTP client, gateway và broker mà không tính budget.
- [ ] RequestHandlerRetryAdvice chỉ bọc đúng handler mục tiêu; biết upstream/downstream nào không nằm trong scope.
- [ ] RecoveryCallback có terminal outcome rõ, không nuốt exception trước khi bảo toàn message.
- [ ] Error channel, parking, DLQ và redrive có owner, retention, reason code và giới hạn số lần.
- [ ] HTTP POST/payment/order dùng idempotency hoặc outcome reconciliation.
- [ ] File/SFTP có quy tắc ready, partial file, checksum, accept-once metadata và replay.
- [ ] JMS/AMQP có ack/transaction/requeue/DLQ đúng cấu hình broker.
- [ ] Kafka có offset/ack/error-handler/DLT theo hợp đồng ordering và concurrency.
- [ ] JDBC retry đúng transaction; có unique key/UPSERT hoặc outbox/inbox khi cần.
- [ ] Service accounts, token SFTP/HTTP/broker được quản lý an toàn, không ghi credential vào log.
- [ ] Có metrics attempts, exhaustion, latency, broker lag, parking backlog và duplicate effects.
- [ ] Kiểm thử crash/restart, timeout sau success, duplicate delivery, DLQ failure và recovery.
- [ ] Có runbook khi đối tác down dài, poison messages, backlog vượt ngưỡng hoặc credential bị lỗi.

## 27. Từ khóa và tài liệu đọc tiếp

### Thuật ngữ

| Thuật ngữ | Ý nghĩa |
|---|---|
| **RetryTemplate** | Điều phối nhiều attempts cho callback/handler |
| **RetryPolicy** | Quyết định exception/điều kiện nào được retry và giới hạn attempts |
| **SimpleRetryPolicy** | Policy giới hạn số lần và phân loại lỗi cơ bản |
| **BackOffPolicy** | Quy định khoảng chờ giữa attempts |
| **RetryContext** | Trạng thái một chuỗi retry đang chạy |
| **RecoveryCallback** | Đường xử lý sau khi retry exhausted |
| **RequestHandlerRetryAdvice** | Advice retry tại request handler của Spring Integration |
| **ErrorChannel** | Kênh nhận lỗi theo cấu trúc messaging, không mặc định là kho bền vững |
| **Redelivery** | Broker/source giao lại message sau lỗi hoặc chưa ack |
| **Idempotency** | Gọi lại cùng business event không tạo thêm side effect ngoài dự kiến |
| **Poison message** | Message không thể xử lý thành công nếu không sửa dữ liệu/chính sách |
| **DLQ/DLT** | Dead-letter queue/topic giữ message không thể xử lý trong luồng chính |
| **Outbox/Inbox** | Pattern bảo toàn ý định gửi và dedupe nhận theo transaction/khóa nghiệp vụ |
| **Ack / offset commit** | Nguồn đánh dấu message/record đã được xử lý theo cơ chế tương ứng |
| **Retry storm** | Nhiều client cùng retry khiến dịch vụ đang lỗi càng quá tải |
| **Retry budget** | Giới hạn tài nguyên/số lần/thời gian cho retries của hệ thống |
| **Outcome unknown** | Không biết hệ thống đích đã áp dụng side effect hay chưa |

### Tài liệu tham khảo

- **Spring Retry Reference:** RetryTemplate, RetryPolicy, RetryContext, BackOffPolicy, RecoveryCallback và listeners.
- **Spring Integration Reference — Retry and More / Message Handler Advice:** RequestHandlerRetryAdvice, advice chain và xử lý lỗi.
- **Spring Integration Reference — Polling Consumer, Message Channels, Error Handling:** phạm vi poller, synchronous/asynchronous error và error channel.
- **Spring Integration Reference — File/SFTP Adapters:** inbound file filters, metadata stores, local/remote transfer và outbound file handling.
- **Spring Integration Reference — HTTP, JMS, AMQP, Kafka, JDBC Adapters/Gateways:** semantics riêng của mỗi transport.
- **Spring for Apache Kafka và Spring AMQP Reference:** consumer error handling, redelivery, acknowledgement, offset, DLQ/DLT, publisher confirms.
- **Enterprise Integration Patterns:** Idempotent Receiver, Dead Letter Channel, Guaranteed Delivery, Message Store, Transactional Client.
- **Spring Framework Transaction Management:** transaction boundaries, rollback behavior và retry phối hợp với transaction.

**Điểm cần ghi nhớ:** RetryTemplate giúp **thử lại một khối công việc có giới hạn và có kiểm soát**; RetryPolicy quyết định khi nào có thể retry và BackOffPolicy quyết định đợi bao lâu. Độ tin cậy của **Spring Integration Adapters** chỉ đạt được khi retry được đặt đúng **ranh giới message/handler**, phân loại lỗi chính xác, kiểm soát **idempotency và transaction/ack**, đồng thời có **terminal recovery bền vững** nếu vẫn thất bại. Hãy luôn chứng minh được: **“Nếu lời gọi bị timeout, ứng dụng có thể thử lại mà không mất message hoặc nhân đôi hiệu ứng nghiệp vụ hay không?”**
