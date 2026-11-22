# Before, after và exception advice trong Spring Integration

## 1. Vì sao cần advice quanh message handler?

Trong module **SPRING_INTEGRATION_RUNTIME**, message được chuyển qua channel đến consumer endpoint, rồi endpoint gọi handler nghiệp vụ. Thực tế, ngoài việc xử lý payload, mỗi handler còn cần log, đo thời gian, kiểm tra điều kiện, ghi audit, phân loại lỗi, tạo metric, transaction và đôi khi retry. Nếu đưa toàn bộ logic này vào từng method xử lý đơn hàng hoặc gửi API, code sẽ lặp và khó kiểm soát thứ tự thực thi.

Chủ đề **Advice chain → Before, after và exception advice** tập trung vào việc chèn xử lý **trước**, **sau khi thành công** và **khi handler ném exception** mà không sửa logic nghiệp vụ của handler.

Ví dụ:

~~~mermaid
flowchart LR
    I["Message đầu vào"] --> E["Endpoint consumer"]
    E --> B["BEFORE: log / timer / audit"]
    B --> H["Handler: gọi shipping API"]
    H -->|Thành công| S["AFTER SUCCESS: metric / audit"]
    H -->|Exception| X["ON ERROR: log / classify"]
    S --> O["Reply / kết thúc"]
    X --> D{"Đẩy lỗi ra ngoài?"}
    D -->|Có| F["error flow / caller / broker"]
    D -->|Không, có chủ đích| R["Fallback / kết thúc theo contract"]
~~~

**Điểm quan trọng:** trong Spring Integration, phần lớn handler advice là **around advice**: cùng một interceptor có thể thực thi cả before, after và exception path bằng `try/catch/finally`. Chúng không phải ba annotation riêng của Spring Integration. Hành vi cụ thể phụ thuộc advice class, thứ tự advice trong chain, loại handler, cùng ranh giới thread/transaction của flow.

## 2. Mô hình thực thi: advice bọc lời gọi handler

`MessageChannel` vận chuyển message. `MessageHandler` nhận message và xử lý. Một consumer endpoint (chẳng hạn service activator) kết nối channel với handler và có thể cài một **advice chain** lên handler đó.

Giả sử có hai advice:

~~~text
adviceChain = [A, B]

A.before
  B.before
    handler()
  B.afterSuccess hoặc B.onException
A.afterSuccess hoặc A.onException
~~~

Advice đầu tiên là **ngoài cùng**, advice cuối cùng nằm gần handler nhất. Đây là thứ tự *bao lồng* (nested), không phải A.before → B.before → handler → A.after → B.after.

~~~mermaid
sequenceDiagram
    participant C as Consumer endpoint
    participant A as Advice A (outer)
    participant B as Advice B (inner)
    participant H as Handler
    C->>A: invoke(message)
    A->>A: before A
    A->>B: proceed()
    B->>B: before B
    B->>H: proceed()
    alt Thành công
        H-->>B: result
        B->>B: afterSuccess B
        B-->>A: result
        A->>A: afterSuccess A
        A-->>C: result
    else Exception
        H--xB: exception
        B->>B: onException B
        B--xA: propagate
        A->>A: onException A
        A--xC: propagate
    end
~~~

Nếu B **bắt và nuốt exception**, A có thể thấy lời gọi B là thành công và chạy nhánh after-success. Nếu A ném exception trong before, B và handler chưa được gọi. Nếu B ném exception trong chính after-success, A đi vào nhánh exception. Vì vậy, cần mô tả "success" là **thành công trong phạm vi quan sát của advice**, không phải một cam kết rằng toàn bộ flow đã commit.

### Ba pha thường được gọi trong lập trình

| Pha | Thời điểm | Việc thường làm | Điều cần lưu ý |
| --- | --- | --- | --- |
| **Before** | Trước khi gọi handler / advice bên trong | Kiểm tra header, mở timer, log request ID, áp dụng policy | Nếu before ném lỗi, handler không chạy |
| **After success** | Handler/advice bên trong trả về bình thường | Ghi metric thành công, publish audit, kiểm tra kết quả | Không chạy khi exception chưa được xử lý; chưa chắc reply đã tới downstream |
| **On exception** | Handler/advice bên trong ném ngoại lệ | Ghi failure metric, thêm ngữ cảnh, rethrow, recovery | Nuốt lỗi thay đổi semantics ack/transaction/retry |
| **Finally / after completion** | Khi trả về **hoặc** khi ném lỗi | Dừng timer, giải phóng tài nguyên | Chạy cả lúc lỗi; lỗi trong finally có thể che lỗi gốc |

Một method trả về `null` bình thường **không đồng nghĩa exception**. Nếu endpoint cho phép không có reply, after-success vẫn có thể chạy; nếu reply bắt buộc, exception do kiểm tra reply có thể xảy ra *ngoài* phạm vi một request-handler advice thông thường.

## 3. Phân biệt request-handler advice, handle-message advice và poller advice

Không phải mọi advice đều bao cùng một đoạn message flow.

| Cơ chế | Phạm vi thường gặp | Ứng dụng chính |
| --- | --- | --- |
| `AbstractRequestHandlerAdvice` / `MethodInterceptor` trong endpoint advice chain | Handler của endpoint đó; với reply-producing handler thường là `handleRequestMessage()` | Log, audit, retry, timing, circuit breaker cho thao tác cụ thể |
| `HandleMessageAdvice` hoặc `HandleMessageAdviceAdapter` | `MessageHandler.handleMessage()`, bao cả xử lý reply và đoạn downstream đồng bộ theo cấu trúc hiện tại | Trường hợp cần quan sát hoặc kiểm soát toàn bộ xử lý ở mức `handleMessage` |
| **Poller advice** | Vòng lấy/dispatch message từ pollable channel hoặc inbound adapter | Transaction/retry và kiểm soát việc poll |
| `ChannelInterceptor` | `preSend`, `postSend`, `afterSendCompletion`, `preReceive`... của channel | Quan sát/chặn thao tác gửi/nhận channel, bất kể handler phía sau |

Các method tạo reply như `@ServiceActivator` hoặc outbound gateway thường dựa trên `AbstractReplyProducingMessageHandler`. Với chúng, **request-handler advice** áp vào `handleRequestMessage()`, còn bước gửi reply và các consumer downstream nằm bên ngoài phạm vi advice này. Với handler không tạo reply, advice có thể bao quanh `handleMessage()`.

Ví dụ `input → @Transformer → DirectChannel → @ServiceActivator`: nếu advice áp tại transformer và service activator downstream bị lỗi, request-handler advice ở transformer không nhất thiết bắt được lỗi đó, vì việc gửi reply downstream diễn ra sau `handleRequestMessage()`. Đây là khác biệt quan trọng khi triển khai exception handling và transaction.

**Ngoại lệ về thứ tự:** các implementation của `HandleMessageAdvice` có thể được tách khỏi request-handler advice chain và áp ở mức `handleMessage()`. Với reply-producing handler, thứ tự cấu hình trong một danh sách không bảo đảm thứ tự chạy chung như mong đợi khi trộn hai loại advice. Cần thiết kế scope rõ ràng và kiểm chứng bằng log.

## 4. Cách viết custom advice có before, after và exception

Spring Integration khuyên mở rộng `org.springframework.integration.handler.advice.AbstractRequestHandlerAdvice` khi cần behavior liên quan đến message handler. Thay vì thao tác trực tiếp `MethodInvocation` và AOP proxy, class cung cấp phương thức:

~~~java
protected Object doInvoke(
        ExecutionCallback callback,
        Object target,
        Message<?> message) throws Exception
~~~

- `callback.execute()` gọi handler (hoặc advice bên trong) **một lần** và trả kết quả.
- `target` là handler mục tiêu, hữu ích để gắn state/metric theo handler nếu advice tái sử dụng cho nhiều endpoint.
- `message` là message đầu vào **trước khi handler xử lý**, cho phép lấy header, correlation và payload để ghi audit.
- Giá trị trả về từ `doInvoke()` được đưa lại cho xử lý của endpoint. Đừng tự ý đổi result thành `null` hoặc kiểu khác nếu không có contract về fallback.

### Ví dụ: đo thời gian và ghi trạng thái

~~~java
import org.springframework.integration.handler.advice.AbstractRequestHandlerAdvice;
import org.springframework.messaging.Message;

public final class TimingAuditAdvice extends AbstractRequestHandlerAdvice {

    @Override
    protected Object doInvoke(
            ExecutionCallback callback,
            Object target,
            Message<?> message) throws Exception {

        long startedAt = System.nanoTime();
        Object trace = message.getHeaders().get("traceId");
        System.out.println("BEFORE trace=" + trace);

        try {
            Object result = callback.execute(); // Một lần, không tự retry.
            System.out.println("AFTER_SUCCESS trace=" + trace);
            return result;
        }
        catch (Exception ex) {
            System.err.println("ON_EXCEPTION trace=" + trace
                    + " type=" + ex.getClass().getSimpleName());
            throw ex; // Giữ nguyên semantics lỗi của handler.
        }
        finally {
            long elapsed = System.nanoTime() - startedAt;
            System.out.println("AFTER_COMPLETION nanos=" + elapsed);
        }
    }
}
~~~

Trong code này, `AFTER_COMPLETION` luôn chạy sau khi `callback.execute()` trả về hoặc ném lỗi. Nó đo thời gian của **scope được advice bọc**, không phải toàn bộ latency từ producer tới hệ thống đích.

Trong ứng dụng thật nên dùng logger có cấu trúc và metric (đếm success/error, histogram latency), tránh `System.out`/`System.err` và hạn chế log payload nhạy cảm. Nếu advice lưu state, sử dụng cấu trúc thread-safe hoặc đo theo biến cục bộ như `startedAt`, không dùng field mutable chung cho nhiều message.

**Không gọi `callback.execute()` hai lần để mô phỏng retry.** Khi advice cần lặp invocation, phải sử dụng `callback.cloneAndExecute()` để reset tiến trình AOP trước mỗi lần gọi; Spring Integration đã cung cấp `RequestHandlerRetryAdvice` nên ưu tiên dùng sẵn và điều chỉnh retry policy thay vì tự viết vòng lặp.

### Bọc và ném lại exception

Nếu muốn thêm ngữ cảnh lỗi:

~~~java
catch (Exception ex) {
    // Log có context và giữ nguyên cause.
    logger.error("Handler failed, traceId={}", traceId, ex);
    throw ex;
}
~~~

Không tạo một exception mới mà bỏ cause hoặc failed message; như vậy sẽ làm mất thông tin của `MessagingException` / `MessageHandlingException`. Nếu cố ý chuyển exception thành lỗi nghiệp vụ khác, cần nêu rõ contract, giữ `cause` và cập nhật logic retry/recovery cho loại lỗi mới.

## 5. Advice có sẵn cho after-success và after-failure

Spring Integration cung cấp `ExpressionEvaluatingRequestHandlerAdvice` để đánh giá hai biểu thức SpEL tách biệt, tương ứng với thành công và thất bại của **handler trong phạm vi advice**.

Các thuộc tính phổ biến:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `setOnSuccessExpressionString(...)` | Biểu thức đánh giá khi handler thành công, gốc là message đầu vào |
| `setSuccessChannel(...)` / `setSuccessChannelName(...)` | Nơi gửi kết quả biểu thức thành công |
| `setOnFailureExpressionString(...)` | Biểu thức đánh giá khi handler thất bại; có biến `#exception` |
| `setFailureChannel(...)` / `setFailureChannelName(...)` | Nơi gửi thông tin lỗi |
| `setTrapException(true)` | Bắt và **không ném lại** exception handler, thay đổi hành vi lỗi của endpoint |
| `setReturnFailureExpressionResult(true)` | Dùng kết quả biểu thức lỗi làm kết quả của handler reply-producing trong các trường hợp được hỗ trợ |
| `setPropagateEvaluationFailures(true)` | Cho phép exception của biểu thức success lan lên caller, thay vì mặc định bỏ qua lỗi đánh giá biểu thức success |

Ví dụ registration:

~~~java
@Bean("outcomeAdvice")
ExpressionEvaluatingRequestHandlerAdvice outcomeAdvice() {
    ExpressionEvaluatingRequestHandlerAdvice advice =
            new ExpressionEvaluatingRequestHandlerAdvice();

    advice.setSuccessChannelName("auditSuccess");
    advice.setOnSuccessExpressionString("payload");

    advice.setFailureChannelName("auditFailure");
    advice.setOnFailureExpressionString("payload");

    advice.setTrapException(false); // Handler exception vẫn lan ra caller.
    return advice;
}
~~~

Cấu hình này tạo **hai nhánh audit phụ** mà không thay đổi reply bình thường của handler.

### Nhánh thành công phát message gì?

Khi handler thành công, advice có thể gửi `AdviceMessage<?>` đến `auditSuccess`:

- `payload` là **kết quả biểu thức**, ví dụ `"ORDER-42"` nếu expression là `payload`.
- Thuộc tính `inputMessage` giữ **message gốc đã vào endpoint**, không phải object reply do handler trả về.
- Message gửi audit là event phụ; output handler tiếp tục theo contract của endpoint.

Vì biểu thức đánh giá trên **message đầu vào**, `onSuccessExpression = "payload"` thường trả payload gốc. Nếu transformer chuyển `" abc "` thành `"ABC"`, event success có thể vẫn mang `" abc "`; đừng kỳ vọng tự động chứa giá trị đã chuyển đổi.

### Nhánh thất bại phát message gì?

Khi handler ném exception, advice có thể gửi `ErrorMessage` đến `auditFailure` với:

- `payload` là `MessageHandlingExpressionEvaluatingAdviceException` (loại exception của advice).
- `cause` là exception do handler gây ra hoặc wrapper phù hợp.
- `failedMessage` trỏ về message lỗi để chẩn đoán.
- `evaluationResult` là giá trị biểu thức `onFailureExpression`; ví dụ ID từ payload đầu vào.

Theo mặc định, sau khi phát event lỗi, **exception gốc vẫn được truyền ra ngoài**. Khi bật `trapException = true`, lời gọi có thể kết thúc bình thường và trả `null`; nếu endpoint `requiresReply`, một lỗi khác có thể xảy ra vì thiếu reply. Không dùng `trapException` chỉ để làm hệ thống “hết báo lỗi”: upstream có thể ack message hoặc commit transaction theo trạng thái thành công.

Nếu có channel mà không cấu hình expression, advice sử dụng biểu thức mặc định `payload`. Việc đánh giá biểu thức success bị lỗi không tự động kích hoạt biểu thức failure; dùng `propagateEvaluationFailures` khi audit expression cần được xem là lỗi quan trọng.

## 6. Ví dụ hoàn chỉnh: hai advice và hai nhánh audit

Ví dụ dưới đây dùng **Spring Boot + Spring Integration**, Java 17+ và package `demo.integration`. Đặt toàn bộ code vào một file `AdviceChainDemoApplication.java`; class duy nhất được khai báo `public` là application. Các channel là `DirectChannel` để quan sát thứ tự gọi đồng bộ.

~~~java
package demo.integration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.annotation.MessageEndpoint;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.handler.advice.AbstractRequestHandlerAdvice;
import org.springframework.integration.handler.advice.ExpressionEvaluatingRequestHandlerAdvice;
import org.springframework.integration.message.AdviceMessage;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootApplication
@EnableIntegration
public class AdviceChainDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(AdviceChainDemoApplication.class, args);
    }

    @Bean("requests")
    MessageChannel requests() {
        return new DirectChannel();
    }

    @Bean("results")
    MessageChannel results() {
        return new DirectChannel();
    }

    @Bean("auditSuccess")
    MessageChannel auditSuccess() {
        return new DirectChannel();
    }

    @Bean("auditFailure")
    MessageChannel auditFailure() {
        return new DirectChannel();
    }

    @Bean("timingAdvice")
    TimingAdvice timingAdvice() {
        return new TimingAdvice();
    }

    @Bean("outcomeAdvice")
    ExpressionEvaluatingRequestHandlerAdvice outcomeAdvice() {
        ExpressionEvaluatingRequestHandlerAdvice advice =
                new ExpressionEvaluatingRequestHandlerAdvice();

        advice.setSuccessChannelName("auditSuccess");
        advice.setOnSuccessExpressionString("payload");
        advice.setFailureChannelName("auditFailure");
        advice.setOnFailureExpressionString("payload");
        advice.setTrapException(false); // Mặc định: vẫn ném lỗi ra caller.
        return advice;
    }

    @Bean
    ApplicationRunner sample(@Qualifier("requests") MessageChannel input) {
        return args -> {
            input.send(MessageBuilder.withPayload("ok")
                    .setHeader("traceId", "trace-001").build());

            try {
                input.send(MessageBuilder.withPayload("fail")
                        .setHeader("traceId", "trace-002").build());
            }
            catch (RuntimeException ex) {
                System.out.println("UPSTREAM_CAUGHT "
                        + ex.getClass().getSimpleName());
            }
        };
    }
}

// Bean advice do Spring quản lý và có thể dùng lại cho nhiều endpoint.
class TimingAdvice extends AbstractRequestHandlerAdvice {

    @Override
    protected Object doInvoke(
            ExecutionCallback callback,
            Object target,
            Message<?> input) throws Exception {

        long started = System.nanoTime();
        Object traceId = input.getHeaders().get("traceId");
        System.out.println("BEFORE " + traceId);

        try {
            Object reply = callback.execute();
            System.out.println("AFTER_SUCCESS " + traceId);
            return reply;
        }
        catch (Exception ex) {
            System.out.println("ON_EXCEPTION " + traceId);
            throw ex;
        }
        finally {
            System.out.println("AFTER_COMPLETION " + traceId
                    + " tookNs=" + (System.nanoTime() - started));
        }
    }
}

@MessageEndpoint
class AdviceDemoEndpoints {

    @ServiceActivator(
            inputChannel = "requests",
            outputChannel = "results",
            adviceChain = {"timingAdvice", "outcomeAdvice"})
    public String handle(String payload) {
        if ("fail".equals(payload)) {
            throw new IllegalStateException("Simulated handler failure");
        }
        return "processed:" + payload;
    }

    @ServiceActivator(inputChannel = "results")
    public void onResult(String result) {
        System.out.println("RESULT " + result);
    }

    @ServiceActivator(inputChannel = "auditSuccess")
    public void onSuccess(AdviceMessage<?> audit) {
        System.out.println("AUDIT_SUCCESS payload=" + audit.getPayload()
                + " original=" + audit.getInputMessage().getPayload());
    }

    @ServiceActivator(inputChannel = "auditFailure")
    public void onFailure(ErrorMessage error) {
        Throwable exception = error.getPayload();
        Object evaluated = "unknown";

        if (exception instanceof
                ExpressionEvaluatingRequestHandlerAdvice
                        .MessageHandlingExpressionEvaluatingAdviceException ex) {
            evaluated = ex.getEvaluationResult();
        }
        System.out.println("AUDIT_FAILURE evaluation=" + evaluated
                + " exception=" + exception.getClass().getSimpleName());
    }
}
~~~

> Demo yêu cầu dependency Spring Integration Core (hoặc Spring Boot Integration starter) phù hợp với phiên bản Boot. Khi tích hợp vào dự án thật, đăng ký channel/advice trong cùng application context và bảo đảm package được component scan. `System.out` chỉ phục vụ thử nghiệm.

### Kỳ vọng quan sát

Với message `"ok"`:

~~~text
BEFORE trace-001
AUDIT_SUCCESS payload=ok original=ok
AFTER_SUCCESS trace-001
AFTER_COMPLETION trace-001 tookNs=...
RESULT processed:ok
~~~

Với message `"fail"`:

~~~text
BEFORE trace-002
AUDIT_FAILURE evaluation=fail exception=MessageHandlingExpressionEvaluatingAdviceException
ON_EXCEPTION trace-002
AFTER_COMPLETION trace-002 tookNs=...
UPSTREAM_CAUGHT ...
~~~

Tên exception được in ở `UPSTREAM_CAUGHT` phụ thuộc lớp wrapper của Spring Integration; không dựa vào chuỗi log đó để viết code nghiệp vụ. `tookNs` thay đổi theo môi trường. Các log trên phản ánh thứ tự synchronous ở ví dụ, không phải guarantee về thứ tự ở executor, broker hoặc message flow song song.

Vì `outcomeAdvice` là advice trong cùng, nó phát audit trước khi `timingAdvice` chạy after-success/on-exception. Bước gửi reply tới `results` xảy ra sau phần handler được advice, nên `RESULT` có thể xuất hiện **sau** `AFTER_COMPLETION`. Đây là minh họa cho ranh giới advice của reply-producing handler.

## 7. Đổi thứ tự chain làm thay đổi điều gì?

Khi cấu hình:

~~~java
@ServiceActivator(
    inputChannel = "requests",
    outputChannel = "results",
    adviceChain = {"timingAdvice", "outcomeAdvice"})
~~~

thì `timingAdvice` là vòng ngoài cùng. Nếu đổi thành `{"outcomeAdvice", "timingAdvice"}`, thứ tự gọi sẽ là:

~~~text
outcomeAdvice
    timingAdvice
        handler
    timingAdvice (after / exception)
outcomeAdvice (publish audit)
~~~

Điều này ảnh hưởng đến: thứ tự log, thời gian đo có bao gồm việc ghi audit hay không, advice nào nhìn thấy exception và advice nào được coi là thành công.

### Ví dụ kết hợp retry và audit

Giả sử chain dùng `{"auditAdvice", "retryAdvice"}` và handler thất bại hai lần rồi thành công ở lần thứ ba:

~~~text
audit.before
    retry attempt #1 -> exception
    retry attempt #2 -> exception
    retry attempt #3 -> success
audit.afterSuccess  (một lần)
~~~

Nếu chain là `{"retryAdvice", "auditAdvice"}`:

~~~text
retry attempt #1 -> audit.before -> handler exception -> audit.onException
retry attempt #2 -> audit.before -> handler exception -> audit.onException
retry attempt #3 -> audit.before -> handler success   -> audit.afterSuccess
~~~

Hai cách đều hợp lệ nhưng tạo metric hoàn toàn khác:

- **Audit ngoài retry:** một event cho logical message, chỉ ghi thành công sau khi toàn bộ chu kỳ retry thành công; nếu retry exhausted sẽ ghi một sự kiện thất bại.
- **Audit trong retry:** một event cho từng **attempt**, phù hợp đo số lần gọi API và phân tích lỗi; không được nhầm số event với số message nghiệp vụ.

Khi advice có `trapException(true)` ở bên trong retry, retry bên ngoài sẽ không nhìn thấy lỗi đã bị nuốt. Đây là lỗi thứ tự phổ biến: retry không chạy dù handler có exception.

### Ví dụ kết hợp transaction

~~~text
retryAdvice -> transactionAdvice -> handler
  Mỗi attempt đi qua transactionAdvice.

transactionAdvice -> retryAdvice -> handler
  Các attempt nằm trong phạm vi transactionAdvice bao ngoài.
~~~

Nếu transaction advice thực sự mở transaction mới cho mỗi invocation, cách đầu có thể tạo transaction theo attempt. Cách sau có thể tạo một transaction chung cho toàn bộ retry, dễ gặp `rollbackOnly` sau attempt lỗi. Tuy nhiên propagation, transaction có sẵn từ poller, và thao tác trong executor quyết định kết quả cuối cùng; **thứ tự advice không tự bảo đảm transaction mới**.

## 8. Filter, lỗi loại bỏ và after advice

`@Filter` là trường hợp đáng chú ý: method predicate trả `false` nghĩa là **từ chối message**, không nhất thiết là exception. Có thể kết hợp `discardChannel` để chuyển message sang một nhánh khác.

Theo mặc định, logic discard của filter có thể xảy ra **trong scope advice**. Với `discardWithinAdvice = "false"`, discard (hoặc exception từ cấu hình rejection) được xử lý **sau** khi chain đã hoàn tất.

~~~java
@Filter(
    inputChannel = "validate",
    outputChannel = "accepted",
    discardChannel = "rejected",
    discardWithinAdvice = "false",
    adviceChain = {"timingAdvice"})
public boolean valid(Order order) {
    return order.amount() > 0;
}
~~~

Hệ quả khi chọn phạm vi:

| Cấu hình | Advice có thể quan sát điều gì? | Rủi ro |
| --- | --- | --- |
| Discard nằm trong advice | Có thể bao cả logic discard/consumer downstream đồng bộ của discard channel | Một lỗi ở nhánh reject có thể kích hoạt retry tại filter |
| `discardWithinAdvice = "false"` | Advice tập trung vào predicate/filter handler, discard chạy sau scope | Audit-after-success của advice không cho biết nhánh reject đã xử lý thành công |

Đừng dùng after-success để đếm `accepted` nếu filter trả `false` mà không ném lỗi. Đếm trạng thái được chấp nhận bằng metric/flow ở các nhánh tương ứng hoặc một cơ chế quan sát phù hợp.

## 9. Exception advice nên xử lý lỗi như thế nào?

Có ba cách xử lý exception và ý nghĩa của từng cách rất khác nhau:

| Chiến lược | Cách làm | Hành vi upstream |
| --- | --- | --- |
| **Quan sát rồi ném lại** | Log/audit, `throw ex` | Caller, poller hoặc error flow vẫn nhìn thấy lỗi |
| **Recovery có chủ đích** | Ghi failure record bền vững, tạo fallback/recovery result theo contract | Có thể kết thúc bình thường và upstream ack |
| **Nuốt lỗi không có kế hoạch** | Catch rồi trả `null`/giá trị mặc định để bỏ qua | Dễ tạo mất dữ liệu và dấu hiệu “success giả” |

Đối với `ExpressionEvaluatingRequestHandlerAdvice`, `failureChannel` dùng để **phát event lỗi**; nó không đồng nghĩa lỗi đã được khôi phục. `trapException = false` là mặc định phù hợp nếu muốn cơ chế transaction, retry và error channel phía ngoài tiếp tục thấy exception.

Khi thật sự cần `trapException = true`, xác định:

1. Message có phải được acknowledge/commit ngay hay không?
2. Recovery flow đã lưu lỗi vào hệ thống đáng tin cậy hay mới chỉ log?
3. Endpoint reply-producing có yêu cầu reply không? `null` có kích hoạt lỗi `requiresReply` không?
4. Có duplicate khi consumer retry hoặc broker redeliver không?
5. Monitoring có phân biệt “đã phục hồi” với “thành công nghiệp vụ” không?

Nếu lỗi chỉ là timeout HTTP tạm thời, cân nhắc `RequestHandlerRetryAdvice` với giới hạn attempts, backoff và recovery callback phù hợp. Nếu đó là schema sai hoặc dữ liệu nghiệp vụ không hợp lệ, retry lặp lại nguyên dữ liệu thường không giúp ích.

## 10. Threading, poller, errorChannel và message store

Advice chạy ở **thời điểm handler được gọi**. Thread của advice phụ thuộc channel và endpoint:

| Điều phối | Thời điểm gọi advice | Nơi nhìn thấy exception |
| --- | --- | --- |
| `DirectChannel` + handler đồng bộ | Trên thread gọi `send()` | Thường truyền ngược `send()` nếu không bị trap/recovery |
| `ExecutorChannel` | Trên worker thread của `TaskExecutor` | Error handler/error flow của async boundary, không nhất thiết catch được ở sender |
| `QueueChannel` + polling consumer | Khi poller lấy message và dispatch | Poller error handler hoặc transaction/retry tương ứng |
| Inbound JMS/AMQP/Kafka adapter | Trên thread listener hoặc worker do adapter cấu hình | Quy tắc ack/redelivery/error channel của adapter |
| Reactive/async handler | Tùy thời điểm subscription/completion | Error xảy ra sau return có thể nằm ngoài advice đồng bộ |

**Một advice nhìn thấy handler trả về bình thường không nhất thiết biết một `Future`/reactive publisher sẽ lỗi sau đó.** Với handler async, cần cơ chế đo completion hoặc retry tương thích với abstraction xử lý.

### Transaction

Transaction thường gắn với thread. Khi advice bao transaction advice, độ bao phủ thực tế phụ thuộc transaction propagation và vị trí bắt đầu transaction. `ExecutorChannel` cắt ranh giới thread; transaction context không tự truyền sang worker. Nếu audit sau-success gọi database riêng, cần xác định nó chạy trong hay ngoài transaction; phát audit trước commit có thể tạo record “thành công” rồi transaction nghiệp vụ rollback.

Đối với yêu cầu chặt chẽ (ví dụ đơn hàng đã ghi DB phải có audit event), cân nhắc outbox pattern hoặc phát event sau commit đúng cơ chế, thay vì coi `afterSuccess` tương đương `afterCommit`.

### Retry

`RequestHandlerRetryAdvice` có thể retry phần handler nếu exception đi ra ngoài. `ExpressionEvaluatingRequestHandlerAdvice` đặt trong retry và bật `trapException(true)` có thể chặn retry. Nếu recovery callback xử lý xong và trả bình thường, advice bên ngoài có thể đếm “success”, dù nghiệp vụ đã chuyển sang đường khôi phục.

### Message store và correlation

`AdviceMessage`/`ErrorMessage` gửi sang audit channel không tự bảo đảm lưu bền vững. Khi audit cần survive restart hoặc phục vụ replay, đưa message vào message store/broker/DB được cấu hình rõ. Chọn `eventId`/`correlationId` và `traceId` ổn định, đặc biệt khi có retry và fan-out; một message bị xử lý lại có thể tạo nhiều audit event.

Tránh dùng payload như khóa metric/tag vì cardinality cao hoặc chứa dữ liệu nhạy cảm; dùng endpoint name, advice type, exception class, outcome và trace trong log có kiểm soát.

## 11. Lifecycle của endpoint và advice chain

Advice được đăng ký như bean trong ApplicationContext rồi được tham chiếu bởi endpoint. Nếu consumer chưa start, bị stop hoặc không có subscriber, việc gửi message có thể thất bại hoặc không đến được advice. Cần kiểm tra lifecycle của endpoint và sự sẵn có của channel.

Với `IntegrationFlow` đăng ký động qua `IntegrationFlowContext`, hãy phân biệt lifecycle của **flow registration** với bean advice dùng chung. Stop/remove flow ảnh hưởng endpoint thuộc flow; nó không có nghĩa bean advice sẽ tự bị xóa nếu được chia sẻ ở context chính. Advice có state như circuit breaker, rate limiter hoặc counter tùy biến cần được quản lý theo target và vòng đời riêng.

Nếu advice có retry/backoff đồng bộ trong consumer thread, một endpoint đang running vẫn có thể không tăng throughput vì worker bị giữ chờ. Theo dõi số active thread, queue backlog và tỷ lệ lỗi trước khi tăng concurrency.

## 12. Chẩn đoán những tình huống khó

| Hiện tượng runtime | Nguyên nhân thường gặp | Cách điều tra |
| --- | --- | --- |
| Không có log BEFORE | Advice chưa được gắn bằng tên bean đúng, endpoint không được scan/start hoặc message chưa tới | Kiểm tra `adviceChain`, channel, endpoint lifecycle |
| Có BEFORE nhưng không có AFTER_SUCCESS | Handler/inner advice ném lỗi hoặc after-success bên trong ném lỗi | Xem ON_EXCEPTION, exception root cause |
| Có AFTER_SUCCESS dù handler từng lỗi | Inner retry phục hồi thành công hoặc exception bị trap | Xem thứ tự advice, `trapException`, recovery |
| Không có ON_EXCEPTION dù xử lý nghiệp vụ bị từ chối | Filter trả `false` bình thường; return code thất bại không phải exception | Thiết kế metric reject riêng |
| Audit success xuất hiện trước RESULT, nhưng RESULT consumer lỗi | Request-handler advice không bao bước gửi reply downstream | Xác định `handleRequestMessage` vs `handleMessage` |
| Advice outer không chạy theo thứ tự thiết lập | Trộn `HandleMessageAdvice` với request-handler advice trên reply-producing endpoint | Xem loại advice và scope thực tế |
| Audit failure gửi được nhưng upstream vẫn nhận exception | `failureChannel` chỉ ghi nhận lỗi, `trapException` mặc định false | Xem quyết định rethrow/recovery |
| Chuyển `DirectChannel` sang `ExecutorChannel` khiến sender không bắt được lỗi | Lỗi phát sinh sau async boundary | Cấu hình error flow, log thread và trace |
| Retry không chạy | Inner advice nuốt exception, handler tự bắt lỗi, hoặc retry ngoài scope lỗi | Test fault injection theo từng handler |
| Transaction rollback nhưng audit nói thành công | Audit sau handler, trước transaction commit | Chọn after-commit/outbox nếu cần semantics commit |

### Checklist kỹ thuật

- Xác định advice bọc **handler nào**, có reply hay không và bước gửi reply nằm ở đâu.
- Chỉ định thứ tự chain theo mục tiêu: per-message hay per-attempt, transaction và retry.
- Với custom advice, gọi `callback.execute()` đúng một lần; dùng `cloneAndExecute()` nếu thật sự tự triển khai repeated invocation.
- Giữ root cause khi ném lại exception; không trap lỗi trừ khi đã có recovery contract.
- Phân biệt event audit thành công với **commit** transaction/hoàn thành downstream.
- Đồng bộ tên bean, channel và consumer cho success/failure audit.
- Kiểm tra thread, queue, errorChannel, message store, correlation và retry khi triển khai async.
- Dùng log/metric có endpoint, outcome, duration và correlation; hạn chế payload nhạy cảm.

## 13. Bài thực hành

1. **Thứ tự advice:** chạy ví dụ mục 6 với `"ok"` và `"fail"`; ghi lại log. Đổi `adviceChain` thành `{"outcomeAdvice", "timingAdvice"}` để quan sát thứ tự thay đổi.
2. **Trường hợp before ném lỗi:** thêm validation trong `TimingAdvice`, ném exception khi thiếu `traceId`; xác nhận handler không chạy.
3. **Phân biệt success/failure:** cho handler trả về `null` trong endpoint không bắt buộc reply, rồi thử yêu cầu reply. Quan sát lỗi nào xảy ra trong/ngoài scope advice.
4. **Trap exception:** bật `setTrapException(true)` ở môi trường thử nghiệm; quan sát việc `send()` có còn ném lỗi không. Tắt lại và giải thích nguy cơ ack nhầm.
5. **Thử retry order:** thêm `RequestHandlerRetryAdvice` phù hợp phiên bản, đặt trước hoặc sau `TimingAdvice`; ghi lại metric per-message và per-attempt.
6. **Async boundary:** thay `requests` thành `ExecutorChannel` với executor có giới hạn; log thread của sender, advice và handler; chuyển cách quan sát lỗi sang error flow.
7. **Exception downstream:** tạo consumer `results` ném lỗi; xác nhận request-handler advice trên handler tạo reply có bắt được lỗi downstream hay không.
8. **Bảo toàn audit:** mô phỏng crash sau khi handler thành công nhưng trước commit, phân tích vì sao một `AdviceMessage` đơn thuần không thay được outbox/message store.

## 14. Tài liệu chính thức

- [Spring Integration — Adding Behavior to Endpoints](https://docs.spring.io/spring-integration/reference/handler-advice.html): handler advice scope, poller advice, chain.
- [Spring Integration — Ordering Advices within Advice Chain](https://docs.spring.io/spring-integration/reference/handler-advice/order.html): advice ngoài/trong và transaction vs retry.
- [Spring Integration — Custom Advice Classes](https://docs.spring.io/spring-integration/reference/handler-advice/custom.html): `AbstractRequestHandlerAdvice` và `ExecutionCallback`.
- [Spring Integration — Provided Advice Classes](https://docs.spring.io/spring-integration/reference/handler-advice/classes.html): `ExpressionEvaluatingRequestHandlerAdvice` và success/failure channels.
- [Spring Integration — Handling Message Advice](https://docs.spring.io/spring-integration/reference/handler-advice/handle-message.html): `HandleMessageAdvice`, thứ tự và phạm vi `handleMessage`.
- [Spring Integration — Advising Endpoints Using Annotations](https://docs.spring.io/spring-integration/reference/handler-advice/advising-with-annotations.html): `adviceChain` trên `@ServiceActivator`, `@Transformer`, `@Filter`, `@Splitter`.
- [Spring Integration API — AdviceMessage](https://docs.spring.io/spring-integration/api/org/springframework/integration/message/AdviceMessage.html), [ExpressionEvaluatingRequestHandlerAdvice](https://docs.spring.io/spring-integration/api/org/springframework/integration/handler/advice/ExpressionEvaluatingRequestHandlerAdvice.html): loại message và thuộc tính của advice.
