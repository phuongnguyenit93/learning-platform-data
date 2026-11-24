# Log exception đúng context trong Spring Boot

> **Chương:** Logging  
> **Bài:** Log exception đúng context  
> **Module:** SPRING_BOOT_OBSERVABILITY — Thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. Vì sao một stack trace riêng lẻ chưa đủ?

Khi một request gặp lỗi, log có thể chứa stack trace dài nhưng người trực vận hành vẫn không trả lời được những câu hỏi cơ bản:

- Lỗi xảy ra trong request, message hay scheduled job nào?
- Service và instance nào tạo log?
- Trace nào chứa span tương ứng?
- Request đang xử lý route/operation nào?
- Exception được ném ở đâu, được catch ở đâu và có được chuyển tiếp không?
- Đây là lỗi kỹ thuật, kết quả nghiệp vụ dự kiến hay một lần retry đã được xử lý?

**Log exception đúng context** nghĩa là ghi nhận exception cùng những metadata cần thiết để xác định hoạt động tạo ra lỗi, đồng thời giữ nguyên thông tin chẩn đoán. Một log record hữu ích thường có timestamp, severity, logger, message, exception type/stack trace, service identity và correlation context như trace ID/span ID khi có.

~~~mermaid
flowchart TD
  A["Request / message / scheduled task"] --> B["Context được tạo hoặc extract"]
  B --> C["Business operation"]
  C --> D{"Có exception?"}
  D -->|Không| E["Log kết quả phù hợp"]
  D -->|Có| F["Xác định nơi xử lý exception"]
  F --> G["Log một lần tại boundary phù hợp"]
  G --> H["Giữ exception object và stack trace"]
  G --> I["Gắn traceId / spanId / operation"]
  H --> J["Log backend"]
  I --> J
  J --> K["Điều tra cùng trace và metrics"]
~~~

Log đúng context không có nghĩa phải ghi tất cả request headers hoặc toàn bộ object. Chỉ ghi dữ liệu vừa đủ để định vị lỗi, tuân thủ chính sách bảo mật và giữ cardinality hợp lý.

## 2. Exception, error event và log record là ba khái niệm khác nhau

Một exception Java là đối tượng biểu diễn tình huống bất thường trong luồng thực thi. Log record là bản ghi sự kiện do ứng dụng phát ra. Trong tracing, exception có thể được ghi thành event trên span hoặc làm span mang trạng thái error thông qua Observation/tracing handler.

| Thành phần | Mục đích | Ví dụ |
| --- | --- | --- |
| Exception object | Biểu diễn lỗi và call stack trong runtime | java.net.SocketTimeoutException |
| Log record | Ghi thông tin để người vận hành tìm kiếm | Inventory request timed out |
| Stack trace | Cho thấy chuỗi lời gọi dẫn tới lỗi | Service → client → socket |
| Span event | Gắn sự kiện exception vào span | exception.type, exception.message |
| Span status | Diễn tả kết quả hoạt động theo tracing model | ERROR |
| Trace/span context | Liên kết log và span với request | traceId, spanId |

Một exception có thể tạo ra log, span event hoặc cả hai. Việc một log có stack trace không tự động làm span được đánh dấu ERROR; việc gọi Observation.error(ex) cũng không tự động ghi một log ứng dụng.

Thiết kế nên thống nhất: nơi nào sở hữu việc ghi log, nơi nào báo lỗi cho Observation, và nơi nào chuyển tiếp exception cho caller. Không để mỗi tầng catch cùng một exception rồi ghi lại stack trace đầy đủ.

## 3. Ghi exception bằng SLF4J đúng cách

Spring Boot dùng facade logging và backend được cấu hình theo dependency/runtime. Với SLF4J, phương thức logger có overload nhận exception object. Hãy truyền exception như đối số throwable cuối cùng để backend ghi stack trace.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {
    private static final Logger log =
            LoggerFactory.getLogger(InventoryService.class);

    public void reserve(String sku) {
        try {
            callInventory(sku);
        } catch (RuntimeException ex) {
            log.error("Inventory reservation failed for sku={}", sku, ex);
            throw ex;
        }
    }

    private void callInventory(String sku) {
        // Gọi hệ thống inventory.
    }
}
~~~

Trong ví dụ, SLF4J nhận message template, giá trị sku và exception. Backend có thể render message cùng stack trace. Exception vẫn được ném tiếp để tầng gọi quyết định response/retry.

### 3.1. Truyền Throwable, không chỉ truyền message của exception

Ví dụ đúng:

~~~java
log.error("Payment authorization failed for orderId={}", orderId, ex);
~~~

Ví dụ dễ mất stack trace:

~~~java
log.error("Payment authorization failed: {}", ex.getMessage());
~~~

Dòng thứ hai chỉ ghi message dạng text; nó không truyền Throwable cho logger. Khi cần điều tra nguyên nhân, ưu tiên overload nhận exception object. Nếu không thể ghi stack trace vì policy cụ thể, phải có chủ đích và đảm bảo thông tin chẩn đoán thay thế đủ dùng.

### 3.2. Dùng parameterized logging

Không ghép chuỗi thủ công khi logger hỗ trợ placeholder:

~~~java
// Nên dùng
log.warn("Request failed for customerRef={}", customerRef, ex);

// Tránh nếu không cần tính toán trước
log.warn("Request failed for customerRef=" + customerRef, ex);
~~~

Parameterized logging giúp backend kiểm soát format và có thể tránh tạo chuỗi khi log level bị tắt. Tuy nhiên vẫn phải kiểm tra value trước khi ghi để không lộ dữ liệu nhạy cảm.

## 4. Catch exception ở đâu và ghi log ở đâu?

Một quy tắc thực tế: **catch để xử lý; log tại boundary chịu trách nhiệm ghi nhận sự kiện lỗi**. Không phải mọi catch block đều cần log.

~~~mermaid
flowchart TD
  A["Database / HTTP client"] --> B["Repository / adapter"]
  B --> C["Service nghiệp vụ"]
  C --> D["Controller / message listener"]
  D --> E["Exception handler / boundary"]
  B -. "chỉ chuyển tiếp nếu không xử lý" .-> C
  C -. "chuyển tiếp hoặc chuyển thành domain result" .-> D
  D --> F["HTTP response / message retry / dead letter"]
~~~

Ví dụ:

- Repository gặp lỗi DB và chuyển tiếp exception: thường không cần log stack trace tại repository nếu service/boundary sẽ log cùng lỗi.
- Service catch exception để fallback thành công: nên ghi nhận ở mức phù hợp nếu fallback ảnh hưởng vận hành; không nhất thiết log stack trace ở mọi lần fallback.
- Controller hoặc global exception handler chuyển lỗi thành HTTP response: thường là nơi phù hợp để log lỗi không được xử lý ở tầng dưới, nếu chưa có log tương đương.
- Message listener quyết định retry hoặc dead-letter: boundary này cần ghi nhận attempt và outcome, tránh mỗi consumer/helper đều ghi cùng exception.

### 4.1. Một exception, một log đầy đủ tại boundary

~~~java
public Order createOrder(CreateOrderCommand command) {
    try {
        return orderGateway.create(command);
    } catch (InventoryUnavailableException ex) {
        // Chuyển thành lỗi nghiệp vụ/response phù hợp.
        throw ex;
    }
}
~~~

Nếu method chỉ chuyển tiếp exception như trên, log stack trace có thể thuộc exception handler ở tầng web/message. Nếu service thực hiện fallback, ghi một structured event nói rõ fallback được kích hoạt; log exception đầy đủ chỉ khi có giá trị chẩn đoán và chưa bị ghi ở nơi khác.

Không áp dụng quy tắc “log mọi lần catch”. Việc catch có thể chỉ nhằm cleanup, rollback, translate exception hoặc thực hiện retry.

## 5. Giữ nguyên nguyên nhân khi wrap exception

Khi chuyển exception kỹ thuật thành exception ở abstraction khác, giữ original cause:

~~~java
try {
    paymentClient.authorize(request);
} catch (SocketTimeoutException ex) {
    throw new PaymentGatewayException(
            "Payment gateway did not respond in time", ex);
}
~~~

Constructor nhận cause giúp stack trace thể hiện chuỗi nguyên nhân. Tránh tạo exception mới mà bỏ mất cause:

~~~java
// Không tốt: mất liên kết với nguyên nhân ban đầu.
throw new PaymentGatewayException("Payment gateway timeout");
~~~

Nếu translate exception, chọn loại exception phản ánh abstraction của tầng hiện tại. Không đưa nguyên văn response body/token từ đối tác vào exception message nếu có thể chứa dữ liệu nhạy cảm.

### 5.1. Không log rồi tạo exception mới không cần thiết

~~~java
try {
    return client.fetch();
} catch (RuntimeException ex) {
    log.error("Fetch failed", ex);
    throw new ServiceUnavailableException("Fetch failed", ex);
}
~~~

Nếu global handler cũng log stack trace của ServiceUnavailableException, cùng lỗi có thể xuất hiện hai lần. Hãy chọn boundary chịu trách nhiệm log đầy đủ; tầng dưới có thể translate exception và giữ cause nhưng không log lại.

## 6. Giữ trace context trong log

Trong distributed tracing, trace ID xác định trace và span ID xác định hoạt động cụ thể bên trong trace. Khi logging integration hỗ trợ correlation, các giá trị này có thể được đưa vào MDC hoặc context tương đương để xuất hiện trên log records.

Ví dụ log dạng minh họa:

~~~text
2026-11-22 10:15:21.104 ERROR [order-service,traceId=4bf9...,spanId=00f0...] Inventory reservation failed
java.net.SocketTimeoutException: Read timed out
    at ...
~~~

Một trace có thể chứa nhiều spans; log ghi tại span nào nên mang span ID của span hiện tại. Trace ID giúp tìm toàn bộ distributed trace, span ID giúp xác định operation tạo log.

**Không tự tạo trace ID mới trong catch block** để gắn vào log. Dùng context hiện hành do tracing integration quản lý. Nếu không có active trace, để field trống/absent hoặc dùng correlation ID riêng có nguồn gốc rõ ràng; không bịa giá trị để lấp log.

### 6.1. Logback pattern và MDC

Spring Boot hỗ trợ correlation IDs thông qua tracing integration và logging pattern phù hợp. Với Logback, một pattern minh họa có thể chứa MDC keys:

~~~xml
<configuration>
    <property name="CONSOLE_LOG_PATTERN"
              value="%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] traceId=%X{traceId:-} spanId=%X{spanId:-} %logger{36} - %msg%n%ex"/>
</configuration>
~~~

Đây là ví dụ pattern, không phải cấu hình hoàn chỉnh để thay thế toàn bộ mặc định của Spring Boot. Key MDC và cách integration đặt chúng có thể khác theo bridge/version. Trước khi custom pattern, hãy kiểm tra console/file output hiện tại; tránh vô tình bỏ màu, correlation fields hoặc throwable converter mặc định.

### 6.2. Correlation fields ngoài trace IDs

Có thể đưa một số baggage fields được cho phép vào logging correlation, chẳng hạn region hoặc workflow version. Chỉ thêm field có giá trị vận hành, hữu hạn và không nhạy cảm. Không đưa email, token, cookie hoặc toàn bộ request headers vào MDC.

## 7. Spring Boot và global exception handler

Với Spring MVC, một global exception handler có thể chuyển exception thành HTTP response nhất quán. Đây cũng có thể là boundary phù hợp để log exception chưa được xử lý.

~~~java
package example.orders;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {
    private static final Logger log =
            LoggerFactory.getLogger(ApiExceptionHandler.class);

    @ExceptionHandler(InventoryUnavailableException.class)
    public ProblemDetail handleInventoryUnavailable(
            InventoryUnavailableException ex) {

        log.error("Request failed because inventory is unavailable", ex);

        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.SERVICE_UNAVAILABLE);
        problem.setTitle("Inventory temporarily unavailable");
        problem.setDetail("Please retry the operation later.");
        return problem;
    }
}
~~~

Response trả cho client chỉ chứa thông tin an toàn và hữu ích. Không trả stack trace, database message, hostname nội bộ, token hoặc raw exception message trong production.

Nếu exception đã được log với stack trace ở service/interceptor trước đó, handler không nên lặp lại stack trace. Có thể log một outcome ngắn hoặc tăng counter phù hợp. Hãy chọn ownership rõ ràng và nhất quán giữa các exception categories.

### 7.1. Phân biệt lỗi dự kiến và lỗi không dự kiến

| Tình huống | Logging gợi ý |
| --- | --- |
| Input validation không hợp lệ | Thường không cần stack trace; ghi outcome/metric có kiểm soát nếu cần |
| Không tìm thấy resource theo contract | Có thể là kết quả nghiệp vụ bình thường, thường không cần ERROR stack trace |
| Business rule từ chối giao dịch | Ghi kết quả nghiệp vụ phù hợp, không tự động xem như lỗi kỹ thuật |
| Timeout dependency | Có thể log WARN/ERROR tùy ảnh hưởng, giữ exception ở boundary |
| Database unavailable | Thường cần ERROR cùng exception và service context |
| Programmer bug/uncaught exception | ERROR với stack trace và trace context |
| Client disconnect/cancel | Có thể là tình huống bình thường; tránh tạo noise ERROR |

Severity phụ thuộc semantics và tác động, không chỉ tên exception class. Một exception dùng cho control flow không mặc định là lỗi hệ thống.

## 8. Kết hợp log exception với Observation.error

Micrometer Observation cho phép báo exception để tracing/metrics handlers có thể ghi nhận lỗi trong lifecycle của operation. Ví dụ:

~~~java
Observation observation =
        Observation.createNotStarted("orders.create", registry).start();

try (Observation.Scope scope = observation.openScope()) {
    return createOrder();
} catch (RuntimeException ex) {
    observation.error(ex);
    throw ex;
} finally {
    observation.stop();
}
~~~

Đoạn code gọi error trên Observation trước khi stop. Tracing handler có thể gắn exception event hoặc đánh dấu span theo implementation. Metrics handler có thể ghi outcome phù hợp tùy convention/configuration.

Điều này **không tự ghi application log**. Nếu cần log, dùng logger tại boundary sở hữu việc ghi. Một lỗi có thể đồng thời:
- được báo cho Observation để span phản ánh error;
- được log một lần với stack trace và trace/span context;
- được đếm bằng metric có low-cardinality outcome.

Ba thao tác phục vụ ba signal khác nhau; tránh nhầm một thao tác thay thế toàn bộ các signal.

## 9. Exception trong async và reactive code

Context của request có thể bị mất khi tác vụ chuyển sang thread khác. Khi đó exception log vẫn có stack trace nhưng thiếu traceId/spanId hoặc mang context của một request khác nếu code quản lý ThreadLocal sai.

Với executor/CompletableFuture, dùng cơ chế context propagation được Spring/Micrometer hoặc tracing integration hỗ trợ. Không tự giữ một MDC map dùng chung giữa các tác vụ.

~~~java
CompletableFuture.supplyAsync(
        () -> paymentClient.authorize(command),
        contextAwareExecutor
).whenComplete((result, error) -> {
    if (error != null) {
        Throwable cause = unwrap(error);
        log.error("Asynchronous payment authorization failed", cause);
    }
});
~~~

Ví dụ giả định contextAwareExecutor được cấu hình để capture/restore context cần thiết và logger là field của class. Hàm unwrap phải bảo toàn cause khi bỏ CompletionException/ExecutionException wrapper. Không dùng common pool mặc định rồi giả định MDC/trace context sẽ tự truyền.

### 9.1. Reactor và WebFlux

Trong reactive flow, context gắn với subscription và Reactor Context, không phải lúc nào cũng gắn với thread hiện tại. Dùng instrumentation/context propagation tương thích với phiên bản Spring Boot, Reactor và Micrometer.

~~~java
return paymentClient.authorize(command)
    .doOnError(ex ->
        log.error("Reactive payment authorization failed", ex));
~~~

Operator này chỉ là điểm minh họa; logging callback cần chạy trong context đã được tích hợp với tracing. Kiểm thử bằng trace IDs ở log từ callback thực tế. Tránh chuyển sang ThreadLocal thuần túy hoặc gọi subscribe thủ công bên trong controller để “giữ” exception.

### 9.2. Unwrap exception wrapper một cách thận trọng

Async frameworks có thể bọc nguyên nhân trong CompletionException hoặc ExecutionException. Khi log, có thể chọn root cause để phân loại, nhưng đừng bỏ toàn bộ wrapper nếu nó hữu ích cho việc hiểu nơi async boundary chuyển lỗi.

~~~java
private Throwable unwrap(Throwable error) {
    Throwable current = error;
    while ((current instanceof CompletionException
            || current instanceof ExecutionException)
            && current.getCause() != null) {
        current = current.getCause();
    }
    return current;
}
~~~

Nếu log root cause, cần đảm bảo stack trace và context vẫn đủ để hiểu đường đi bất đồng bộ. Tránh unwrap tùy tiện các exception có ý nghĩa nghiệp vụ.

## 10. Exception trong message listener và scheduled job

Không phải mọi hoạt động đều bắt đầu từ HTTP request. Message consumer và scheduled job cũng cần correlation context phù hợp.

### 10.1. Message listener

Log của consumer nên có message key/opaque event ID đã được phê duyệt, destination, consumer operation, attempt và trace context nếu producer đã propagate context trong message headers.

~~~java
try {
    process(event);
} catch (RuntimeException ex) {
    log.error(
        "Message processing failed destination={} attempt={}",
        destination, attempt, ex);
    throw ex;
}
~~~

Nếu framework tự retry và listener được gọi nhiều lần, log mỗi attempt ở mức phù hợp có thể hữu ích nhưng stack trace đầy đủ ở mọi lần sẽ tạo noise. Có thể log lần đầu với chi tiết, các lần sau với attempt/outcome, và ghi ERROR cuối cùng khi message chuyển dead-letter theo policy.

Không log toàn bộ message payload. Chọn event type và ID kỹ thuật đã được chuẩn hóa.

### 10.2. Scheduled job

Scheduled task không có HTTP trace context tự nhiên. Tạo một Observation/span cho job hoặc lần chạy, thêm metadata ổn định như job name và run outcome. Sau đó exception log có thể mang context của job span.

~~~java
@Scheduled(fixedDelayString = "PT5M")
public void refreshCatalog() {
    try {
        refreshService.refresh();
    } catch (RuntimeException ex) {
        log.error("Catalog refresh job failed", ex);
        throw ex;
    }
}
~~~

Ví dụ này giả định logger được khai báo trong class. Nếu scheduler nuốt exception hoặc framework tiếp tục chạy lần kế tiếp, cần theo dõi run status bằng metric và log. Đừng đặt mỗi run ID thành metric label.

## 11. Logging severity và mức độ chi tiết

Mức log nên mô tả tác động và hành động cần thiết:

| Level | Dùng khi | Ví dụ |
| --- | --- | --- |
| TRACE | Thông tin rất chi tiết khi debug tạm thời | Chi tiết luồng xử lý nội bộ |
| DEBUG | Chẩn đoán không cần hiển thị thường xuyên | Retry decision trong test |
| INFO | Sự kiện vận hành bình thường | Job hoàn tất, fallback đã xử lý |
| WARN | Vấn đề có thể phục hồi hoặc cần chú ý | Một retry thất bại nhưng request tiếp tục |
| ERROR | Operation thất bại và cần điều tra | Dependency timeout làm request lỗi |

Không dùng ERROR cho mọi business rejection hoặc mọi 4xx; điều đó làm tỷ lệ lỗi log mất ý nghĩa. Không hạ lỗi nghiêm trọng xuống DEBUG chỉ để giảm noise. Chọn level theo semantics và alerting policy.

### 11.1. Đừng log stack trace ở mọi lần retry

Một request retry ba lần có thể tạo ba stack traces gần giống nhau, dù chỉ một operation cuối cùng thất bại. Có thể:
- Ghi DEBUG/WARN mỗi retry với attempt, dependency và delay.
- Ghi một ERROR đầy đủ tại boundary khi retry policy cạn.
- Ghi metric retry count và final failure.
- Giữ trace spans cho mỗi attempt nếu tracing policy cần thấy chi tiết.

Quy tắc này giúp log có thể tìm kiếm và giảm chi phí mà vẫn giữ dữ liệu chẩn đoán.

## 12. Dữ liệu nhạy cảm và an toàn khi log exception

Exception message và stack trace có thể chứa:
- SQL có literal values hoặc tên bảng/schema.
- URL có query parameters.
- Header/body từ dependency.
- File path, username, hostname hoặc thông tin hạ tầng.
- Token, password hoặc dữ liệu khách hàng do thư viện nhúng vào message.

Trước khi ghi log, đánh giá exception type/message và mọi context values được thêm vào. Không đưa secrets vào message template, MDC, baggage hoặc span attributes.

### 12.1. Log dữ liệu tham chiếu đã được giảm thiểu

~~~java
log.error(
    "Order fulfillment failed orderRef={} dependency={}",
    safeOrderReference,
    "inventory",
    ex);
~~~

safeOrderReference phải là ID opaque, được phép ghi log và không chứa thông tin trực tiếp nhận dạng cá nhân. Nếu không cần ID để điều tra, bỏ trường đó. Không log DTO đầy đủ bằng toString().

### 12.2. Tránh log injection

Giá trị người dùng có thể chứa newline hoặc ký tự điều khiển khiến log bị giả mạo nhiều dòng. Dùng structured logging/encoder hỗ trợ escaping, validate hoặc sanitize input theo policy. Không nối raw user input vào log message.

### 12.3. Kiểm soát access và retention

Logs có stack traces có thể nhạy cảm hơn logs thông thường. Hạn chế quyền đọc, mã hóa đường truyền/lưu trữ theo chính sách, áp dụng retention phù hợp và không bật DEBUG/TRACE rộng trên production trong thời gian dài nếu chưa đánh giá tác động.

## 13. Structured logging cho exception

Structured logging lưu các trường riêng thay vì một chuỗi không có cấu trúc. Backend có thể lọc theo severity, service, exception type, trace ID hoặc operation.

Ví dụ JSON minh họa:

~~~json
{
  "timestamp": "2026-11-22T10:15:21.104Z",
  "level": "ERROR",
  "service.name": "order-service",
  "event.name": "inventory.reservation.failed",
  "message": "Inventory reservation failed",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "exception.type": "java.net.SocketTimeoutException",
  "exception.message": "Read timed out"
}
~~~

Đây là schema minh họa; field names thực tế phụ thuộc logging encoder, OpenTelemetry Logs bridge và backend. OpenTelemetry semantic conventions định nghĩa cách biểu diễn exception/log attributes theo phiên bản convention tương ứng.

Không tạo JSON bằng cách nối chuỗi thủ công. Dùng encoder hoặc logging API có structured fields để escaping và kiểu dữ liệu đúng. Stack trace có thể được xuất thành field riêng hoặc throwable section.

## 14. Liên kết logs với traces và metrics

Khi một request gặp lỗi, quy trình điều tra hiệu quả thường bắt đầu từ metrics, chuyển sang trace rồi đến logs chi tiết.

~~~mermaid
flowchart TD
  A["Metrics: error rate / latency tăng"] --> B["Chọn service, route và thời gian"]
  B --> C["Tìm trace đã sample"]
  C --> D["Mở span có status/error event"]
  D --> E["Lấy traceId và spanId"]
  E --> F["Tìm log records tương ứng"]
  F --> G["Đọc exception stack và message"]
  G --> H["Đối chiếu dependency, version và instance"]
~~~

- **Metrics:** phát hiện xu hướng và quy mô ảnh hưởng.
- **Traces:** cho thấy request đi qua service nào và operation nào chậm/lỗi.
- **Logs:** cung cấp sự kiện và exception details tại một thời điểm cụ thể.
- **Trace ID/span ID:** nối logs và spans khi context propagation/correlation hoạt động.

Sampling có thể khiến một request không có trace lưu trên backend nhưng vẫn có log và metrics. Vì vậy không yêu cầu trace phải tồn tại mới được log lỗi. Khi trace không được sample, log vẫn nên có service/operation/time và correlation ID khác nếu được phép.

Không dùng trace ID làm metric label; high cardinality sẽ làm số time series tăng nhanh. Dùng exemplar hoặc cơ chế link được backend hỗ trợ khi cần điều hướng từ metric sang trace.

## 15. Anti-pattern: những cách ghi exception làm giảm chất lượng điều tra

| Anti-pattern | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ log ex.getMessage() | Mất stack trace và cause chain | Truyền Throwable cho logger |
| Catch rồi log và rethrow ở mọi tầng | Một lỗi có nhiều stack traces | Chọn boundary ghi log đầy đủ |
| Tạo exception mới không giữ cause | Mất nguồn gốc lỗi | Truyền cause vào constructor |
| Log raw request/response body | Lộ PII/secret, tăng dung lượng | Ghi metadata đã allowlist |
| Tự tạo trace ID trong catch | Log không khớp trace thật | Dùng current tracing context |
| Mọi business rejection đều ERROR | Nhiễu và sai semantics | Chọn level/outcome theo nghiệp vụ |
| Log mọi retry với stack trace | Khó đọc, chi phí cao | Log attempt gọn, ERROR khi cạn retry |
| Dùng Throwable.toString() như stack trace | Thiếu call stack | Ghi exception object |
| Log trong async mà mất context | Không nối được log với request | Bật context propagation phù hợp |
| Vừa log exception vừa log ở global handler | Duplicate records | Quy định ownership |
| Đưa ID riêng vào metric labels | Cardinality tăng mạnh | Dùng trace/log attributes được kiểm soát |

### Checklist trước khi thêm log

1. Ai là owner của log record này?
2. Exception có được chuyển tiếp không, hay được xử lý/fallback?
3. Có log stack trace ở tầng khác chưa?
4. Có active trace context và correlation fields không?
5. Message/attributes có thể lộ dữ liệu nhạy cảm không?
6. Level có phản ánh đúng outcome không?
7. Log có đủ service, operation, dependency và instance metadata cần thiết?
8. Retry có tạo log trùng không?

## 16. Tình huống thực tế: inventory timeout qua ba service

**Bối cảnh:** client gọi api-gateway, gateway gọi order-service, order-service gọi inventory-service. Metrics cho thấy p95 tạo đơn tăng và tỷ lệ fallback tăng. Một số request cuối cùng thất bại vì timeout.

### Bước 1 — metrics khoanh vùng

Dashboard báo latency tăng ở order-service và inventory client. Counter ghi số timeout/fallback theo các chiều low-cardinality như service, operation, outcome.

### Bước 2 — trace cho thấy đường đi

Một trace được sample có thể hiển thị:

~~~text
api-gateway: POST /orders
  order-service: orders.create
    inventory-service client: reserve
~~~

Client span của order-service kéo dài và kết thúc với lỗi. Nếu inventory server span tồn tại, so sánh cùng trace ID để xác định thời gian nằm ở network, queue hay xử lý server.

### Bước 3 — log exception tại boundary

OrderService bắt lỗi chỉ khi có fallback policy hoặc cần translate:

~~~java
try {
    inventoryClient.reserve(command);
} catch (SocketTimeoutException ex) {
    log.warn(
        "Inventory reservation timed out; fallback will be used dependency={}",
        "inventory",
        ex);
    return reserveUsingFallback(command);
}
~~~

Nếu fallback thành công và đây là tình huống vận hành cần theo dõi, log WARN với stack trace có thể hợp lý trong giai đoạn điều tra. Trong vận hành lâu dài, có thể log một event gọn cho từng fallback và giữ stack trace cho một tỷ lệ/điều kiện có kiểm soát. Observation cần được báo lỗi hoặc outcome theo semantics đã định nghĩa; không đánh dấu toàn bộ operation thất bại nếu fallback tạo kết quả thành công theo contract.

### Bước 4 — không ghi lại cùng lỗi ở mọi tầng

Nếu controller/global handler nhận exception không được xử lý, handler ghi ERROR đầy đủ cùng trace context. Service đã log fallback thì không cần thêm một ERROR stack trace nữa cho cùng lần timeout.

### Bước 5 — xác nhận sau thay đổi

Sau khi sửa pool/timeout hoặc dependency, theo dõi p95, error/fallback counters, trace waterfall và logs. Kiểm tra traceId/spanId hiện diện ở log của đúng operation và không có duplicate stack traces.

**Bài học:** log exception có ích khi chỉ rõ ai xử lý lỗi, operation nào bị ảnh hưởng, context nào liên kết trace và outcome cuối cùng ra sao.

## 17. Bài thực hành và câu hỏi tự kiểm tra

### Bài tập A — phân biệt log message và Throwable

Tạo một service cố ý ném IOException. Ghi log một lần chỉ với ex.getMessage(), một lần truyền exception object. So sánh backend output, stack trace, cause chain và khả năng tìm kiếm.

### Bài tập B — kiểm soát log ownership

Tạo Controller → Service → Client. Cho Client throw timeout. Thử catch/rethrow ở nhiều tầng. Thiết kế lại để chỉ một boundary ghi stack trace đầy đủ, còn các tầng khác translate hoặc chuyển tiếp exception mà không duplicate log.

### Bài tập C — log cùng trace context

Tạo một HTTP request có Observation/tracing. Ném exception trong service, log tại exception handler. Xác minh log có traceId/spanId và tìm được trace tương ứng nếu trace được sample.

### Bài tập D — async context

Chạy một CompletableFuture bằng executor tùy chỉnh. Kiểm tra MDC và trace context trước/sau callback. Bật cơ chế context propagation phù hợp, sau đó xác minh log callback có đúng traceId/spanId. Thử nhiều request đồng thời để phát hiện context bị lẫn.

### Bài tập E — bảo mật và severity

Tạo lỗi có message chứa URL/query hoặc input giả lập nhạy cảm. Thiết kế log chỉ chứa dependency, operation, opaque reference và exception type được phép. Phân loại INFO/WARN/ERROR cho validation failure, business rejection, retry và lỗi kỹ thuật.

### Câu hỏi tự kiểm tra

1. Vì sao log ex.getMessage() thường không đủ để điều tra?
2. SLF4J nhận Throwable như thế nào để ghi stack trace?
3. Catch block nào nên ghi log và catch block nào chỉ chuyển tiếp?
4. Khi wrap exception, vì sao phải giữ cause?
5. Exception log và Observation.error(ex) khác nhau ở đâu?
6. Trace ID và span ID giúp định vị log thế nào?
7. Vì sao không tự tạo trace ID trong catch block?
8. MDC có thể mất khi chạy async vì lý do gì?
9. WebFlux/Reactor context khác ThreadLocal như thế nào?
10. Vì sao không log mọi lần retry với stack trace?
11. Khi nào business rejection không nên là ERROR?
12. Làm sao tránh log duplicate ở service và global exception handler?
13. Những dữ liệu nào cần loại khỏi exception message và MDC?
14. Sampling traces ảnh hưởng gì tới khả năng tìm log?
15. Làm sao dùng metrics, traces và logs để điều tra timeout xuyên service?

**Tiêu chí hoàn thành:** log Throwable đúng cách; chọn đúng boundary ghi log; giữ cause chain; gắn service/operation/trace context; xử lý async; phân biệt exception log với span error; tránh duplicate logs, PII và high-cardinality metrics; kiểm chứng bằng một luồng HTTP thực tế.

## 18. Ghi nhớ

- Truyền exception object cho logger khi cần stack trace; chỉ ghi exception message thường làm mất call stack.
- Catch để xử lý; chỉ log đầy đủ tại boundary được chọn. Tránh ghi cùng stack trace ở mọi tầng rồi rethrow.
- Khi wrap exception, giữ original cause để không mất chuỗi nguyên nhân.
- Log record, exception event trên span và span status là các signal khác nhau. Observation.error(ex) không tự tạo application log.
- Dùng traceId/spanId của current context để liên kết log với distributed trace; không tự tạo ID giả.
- Async và reactive execution cần context propagation đúng; không dựa vào ThreadLocal/MDC mặc định giữa mọi thread.
- Chọn severity theo outcome và tác động. Business rejection/validation không tự động là lỗi hệ thống.
- Không ghi secrets, PII, request body hoặc raw headers vào message, MDC, baggage hay span attributes.
- Metrics định lượng xu hướng; traces mô tả đường đi; logs chứa chi tiết exception. Sampling trace không phải lý do bỏ log lỗi cần thiết.
- Kiểm thử log ownership, context, duplicate records và bảo mật trên đường đi thực tế.

## Tài liệu tham khảo

- [Spring Boot Reference — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [SLF4J Manual](https://www.slf4j.org/manual.html)
- [Logback — Architecture and Configuration](https://logback.qos.ch/manual/configuration.html)
- [Micrometer Observation Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/)
- [OpenTelemetry Semantic Conventions — Exceptions](https://opentelemetry.io/docs/specs/semconv/exceptions/exceptions-spans/)
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/)

