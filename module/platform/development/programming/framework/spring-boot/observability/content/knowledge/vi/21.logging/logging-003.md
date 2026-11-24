# Correlation ID trong log của Spring Boot

Trong chương **Logging** của module **SPRING_BOOT_OBSERVABILITY**, Correlation ID là một định danh được ghi cùng log để liên kết các sự kiện thuộc một request hoặc workflow. Khi request đi qua gateway, orders-service và payment-service, cùng một Correlation ID giúp nhóm vận hành tìm các dòng log liên quan dù chúng được ghi bởi nhiều instance hoặc service.

Correlation ID đặc biệt hữu ích khi không có distributed trace đầy đủ, chẳng hạn trace bị sampling loại, instrumentation chưa bao phủ một thư viện hoặc hệ thống log là nguồn điều tra chính. Định danh này chỉ có giá trị khi được tạo/tiếp nhận theo quy ước rõ ràng, truyền qua đúng ranh giới, đưa vào logging context và được dọn khỏi thread sau mỗi lần xử lý.

Trong module **SPRING_BOOT_OBSERVABILITY**, log correlation phối hợp với Micrometer Observation, metrics và distributed tracing. Cần phân biệt **Correlation ID**, **Trace ID**, **Span ID** và **Business ID**; chúng có phạm vi và mục đích khác nhau, dù đôi khi cùng xuất hiện trong một log event.

## 1. Correlation ID giải quyết vấn đề gì?

Giả sử một request xác nhận đơn hàng đi qua ba service:

```text
Mobile client
    |
    v
API Gateway
    |
    v
orders-service
    |
    +----> inventory-service
    |
    +----> payment-service

Các log liên quan cùng mang:
correlationId = req-7f31c8a2
```

Khi người trực vận hành cần điều tra giao dịch, họ có thể tìm `correlationId=req-7f31c8a2` trên hệ thống tập trung để xem request được tiếp nhận, kiểm tra tồn kho, gọi thanh toán và trả kết quả như thế nào.

Không có correlation ID, việc tìm log thường phải dựa vào timestamp, hostname, user hoặc thông điệp gần giống nhau. Cách đó dễ bỏ sót log khi request đồng thời cao, clock giữa các máy lệch hoặc một bước xử lý chạy trễ.

Correlation ID giúp trả lời câu hỏi **“những log event nào thuộc cùng một request/workflow?”**. Nó không tự cung cấp thứ tự nhân quả chính xác, thời lượng từng bước hoặc quan hệ parent-child. Distributed tracing giải quyết các câu hỏi đó chi tiết hơn bằng spans và context propagation.

## 2. Phân biệt Correlation ID với Trace ID, Span ID và Business ID

| Định danh | Phạm vi | Mục đích |
| --- | --- | --- |
| Correlation ID | Theo quy ước ứng dụng, thường là một request hoặc workflow | Tìm log event có liên quan |
| Trace ID | Một distributed trace | Liên kết spans qua nhiều service/process |
| Span ID | Một span cụ thể trong trace | Xác định thao tác và quan hệ parent-child |
| Business ID | Thực thể nghiệp vụ như order/payment/customer | Tra cứu vòng đời nghiệp vụ theo quyền được cấp |
| Session ID | Một phiên tương tác | Gom request thuộc phiên nếu chính sách cho phép |

Một log có thể chứa nhiều định danh:

```json
{
  "timestamp": "2026-11-22T10:15:02.120Z",
  "level": "INFO",
  "service": "orders-service",
  "message": "Payment authorization started",
  "correlationId": "req-7f31c8a2",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "orderId": "ord-20481"
}
```

Correlation ID dùng để tìm log theo quy ước request của hệ thống; Trace ID dùng để mở distributed trace; Span ID chỉ thao tác cụ thể; Order ID dùng để tìm thực thể nghiệp vụ. Một order có thể trải qua nhiều request/retry và do đó có nhiều Correlation ID hoặc Trace ID.

**Không đặt Trace ID bằng Correlation ID theo mặc định.** Trace ID tuân theo định dạng và lifecycle của tracing system; Correlation ID có thể được tạo ở gateway, nhận từ header được tin cậy hoặc gắn với workflow theo chính sách ứng dụng. Nếu đã có Trace ID và chỉ cần log correlation trong một distributed trace, logging integration của Micrometer Tracing có thể đã đưa trace/span IDs vào MDC; không nhất thiết tạo thêm Correlation ID cùng giá trị.

## 3. Chọn nguồn tạo Correlation ID

Một quy ước phổ biến:

1. Gateway nội bộ đáng tin cậy tạo Correlation ID và truyền qua header được thống nhất.
2. Service nhận request kiểm tra header theo định dạng, độ dài và giới hạn cho phép.
3. Nếu header thiếu hoặc không hợp lệ, service tạo ID mới bằng bộ sinh ID an toàn và không đoán được.
4. Service đặt ID vào logging context trong thời gian xử lý và có thể trả ID trong response header để caller/support tra cứu.
5. Khi gọi downstream, service truyền Correlation ID theo allowlist header và dùng cùng giá trị cho các log liên quan.

Header ví dụ:

```http
X-Correlation-ID: req-7f31c8a2
```

Tên header là quy ước của ứng dụng, không phải chuẩn thay thế W3C Trace Context. Có thể dùng tên khác nếu hệ thống đã có convention; điều quan trọng là gateway và service hiểu cùng semantics.

### Có nên tin Correlation ID từ client?

Không nên chấp nhận mọi chuỗi client gửi mà không kiểm tra. Client bên ngoài có thể gửi giá trị rất dài, chứa ký tự điều khiển, newline hoặc cố tình dùng cùng ID cho nhiều request để gây nhầm lẫn.

Một chính sách an toàn:

- Đặt giới hạn độ dài nhỏ, ví dụ tối đa 64 ký tự.
- Chỉ chấp nhận allowlist ký tự ASCII chữ, số, gạch ngang và gạch dưới.
- Từ chối hoặc thay bằng ID mới nếu giá trị không hợp lệ.
- Không dùng Correlation ID làm credential, tenant authorization hoặc bằng chứng danh tính.
- Ở trust boundary, gateway có thể bỏ header từ Internet và tạo ID do hệ thống kiểm soát.

Correlation ID không cần chứa username, email, số điện thoại, order details hay dữ liệu cá nhân. Một giá trị ngẫu nhiên không mang ý nghĩa nghiệp vụ thường phù hợp hơn.

## 4. Đưa Correlation ID vào MDC trong Spring MVC

Với ứng dụng servlet Spring MVC, `OncePerRequestFilter` có thể xác định Correlation ID, đưa vào MDC trước khi controller chạy, thêm vào response và dọn MDC trong `finally`.

```java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;
import org.slf4j.MDC;
import org.springframework.web.filter.OncePerRequestFilter;

public class CorrelationIdFilter extends OncePerRequestFilter {
    private static final String HEADER = "X-Correlation-ID";
    private static final String MDC_KEY = "correlationId";
    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        String supplied = request.getHeader(HEADER);
        String correlationId = isValid(supplied)
                ? supplied
                : UUID.randomUUID().toString();

        String previous = MDC.get(MDC_KEY);
        MDC.put(MDC_KEY, correlationId);
        response.setHeader(HEADER, correlationId);

        try {
            filterChain.doFilter(request, response);
        } finally {
            if (previous == null) {
                MDC.remove(MDC_KEY);
            } else {
                MDC.put(MDC_KEY, previous);
            }
        }
    }

    private boolean isValid(String value) {
        return value != null && SAFE_ID.matcher(value).matches();
    }
}
```

Đây là ví dụ cho **request xử lý đồng bộ trên servlet thread**. Filter lưu giá trị MDC cũ rồi khôi phục sau khi request kết thúc, thay vì gọi `MDC.clear()` để xóa mọi key khác do framework hoặc tracing integration đã đặt. Cách này tránh làm mất `traceId`, `spanId` hoặc metadata hợp lệ của thành phần khác.

Trong ứng dụng thực tế, đăng ký filter bằng bean hoặc filter registration tương ứng. Kiểm tra filter order: filter phải chạy trước thành phần cần log Correlation ID; nếu muốn log chứa cả trace/span ID thì tracing instrumentation cũng phải mở context ở thời điểm log được ghi.

### Đăng ký filter

```java
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class CorrelationLoggingConfiguration {

    @Bean
    FilterRegistrationBean<CorrelationIdFilter> correlationIdFilter() {
        FilterRegistrationBean<CorrelationIdFilter> registration =
                new FilterRegistrationBean<>();
        registration.setFilter(new CorrelationIdFilter());
        registration.setOrder(-100);
        registration.addUrlPatterns("/*");
        return registration;
    }
}
```

Thứ tự `-100` chỉ là ví dụ; chọn order theo các filter thực tế của ứng dụng, security, tracing và request logging. Không đăng ký cùng một filter đồng thời bằng nhiều cách khiến nó chạy lặp ngoài ý muốn.

## 5. Ghi Correlation ID bằng Logback pattern

Khi ID đã ở MDC, Logback pattern có thể đọc nó bằng `%X{correlationId}`.

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level
                [%thread] service=orders-service
                correlationId=%X{correlationId:-}
                traceId=%X{traceId:-}
                spanId=%X{spanId:-}
                %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Ví dụ output:

```text
2026-11-22T10:15:02.120Z INFO
[http-nio-8080-exec-3] service=orders-service
correlationId=req-7f31c8a2
traceId=4bf92f3577b34da6a3ce929d0e0e4736
spanId=00f067aa0ba902b7
Order confirmation started
```

Tên MDC keys `traceId` và `spanId` phụ thuộc logging correlation integration/version; kiểm tra cấu hình runtime của Spring Boot/Micrometer Tracing. Nếu tracing bridge không cung cấp các key đó hoặc log chạy ngoài span scope, pattern có thể hiển thị rỗng. Không kết luận filter Correlation ID lỗi chỉ vì Trace ID chưa có.

Đối với structured logging, ưu tiên ghi các trường thành JSON riêng biệt thay vì nối vào message. Như vậy hệ thống log có thể filter chính xác theo `correlationId`, `traceId`, `spanId`, `service.name` và `level`.

## 6. Gọi downstream và giữ Correlation ID

Khi service A gọi service B, Correlation ID có thể được truyền bằng custom header theo hợp đồng nội bộ:

```text
orders-service
  correlationId = req-7f31c8a2
       |
       | HTTP request
       | X-Correlation-ID: req-7f31c8a2
       v
payment-service
  correlationId = req-7f31c8a2
```

Với client được Spring Boot auto-configure, có thể thêm interceptor chỉ cho custom header nghiệp vụ. Ví dụ với `RestClient.Builder`:

```java
import org.slf4j.MDC;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class PaymentClientConfiguration {

    @Bean
    RestClient paymentClient(RestClient.Builder builder) {
        return builder
                .baseUrl("http://payment-service")
                .requestInterceptor((request, body, execution) -> {
                    String id = MDC.get("correlationId");
                    if (id != null) {
                        request.getHeaders().set("X-Correlation-ID", id);
                    }
                    return execution.execute(request, body);
                })
                .build();
    }
}
```

Đoạn code đọc MDC ngay lúc client request được thực hiện. Nó phù hợp với lời gọi đồng bộ trong cùng execution context; nếu call chuyển qua executor/reactive pipeline, phải xác minh context đã được propagation trước khi đọc.

Không ghi đè `traceparent` bằng interceptor này. Trace context thuộc tracing propagator và client instrumentation. Correlation ID header là convention riêng, không thay thế Trace ID, Parent Span ID hay sampled flag của W3C.

Service B nên áp dụng cùng quy tắc validate/generate. Nếu nhận ID hợp lệ từ service nội bộ được tin cậy, có thể tiếp tục giá trị đó. Nếu ID không hợp lệ, không đưa raw value vào MDC hoặc log; tạo ID mới theo policy. Gateway thường là nơi chuẩn hóa header và trust boundary.

## 7. MDC không tự truyền sang thread khác

MDC của SLF4J thường được triển khai dựa trên ThreadLocal. Nếu request thread submit callback sang executor khác, callback không tự động nhận MDC values.

```java
try {
    MDC.put("correlationId", correlationId);
    CompletableFuture.runAsync(() -> {
        // Không giả định MDC được giữ ở thread worker.
        log.info("Background persistence started");
    });
} finally {
    MDC.remove("correlationId");
}
```

Callback có thể chạy sau khi thread request đã remove MDC; log trong worker sẽ thiếu Correlation ID. Không giữ ThreadLocal của request mở lâu chỉ để chờ background task.

### Dùng TaskDecorator để capture/restore context

Với Spring Framework hỗ trợ Micrometer Context Propagation, có thể dùng `ContextPropagatingTaskDecorator` trên executor:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
class LoggingTaskConfiguration {

    @Bean(name = "loggingExecutor")
    ThreadPoolTaskExecutor loggingExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
```

Task phải thực sự chạy qua executor này:

```java
CompletableFuture.runAsync(
        () -> log.info("Background persistence started"),
        loggingExecutor);
```

Context propagation chỉ hoạt động cho context accessor đã được đăng ký và tích hợp. Cần xác minh MDC correlation key được capture/restore theo dependency và version của ứng dụng; không giả định task decorator tự đọc mọi ThreadLocal tùy ý.

Nếu chỉ cần truyền một giá trị ứng dụng cụ thể, có thể capture trước khi submit rồi khôi phục trong try/finally ở worker:

```java
String capturedId = MDC.get("correlationId");

executor.execute(() -> {
    String previous = MDC.get("correlationId");
    if (capturedId != null) {
        MDC.put("correlationId", capturedId);
    }
    try {
        log.info("Processing async order");
        processOrder();
    } finally {
        if (previous == null) {
            MDC.remove("correlationId");
        } else {
            MDC.put("correlationId", previous);
        }
    }
});
```

Đây là cách truyền một key thủ công; nếu có nhiều context values, tracing context và baggage, dùng cơ chế context propagation thống nhất thường an toàn hơn. Luôn khôi phục MDC cũ để thread pool không làm rò ID giữa hai task.

## 8. Correlation ID trong reactive và message processing

Với WebFlux/Reactor, execution có thể đổi thread qua scheduler. MDC dựa trên ThreadLocal không tự phản ánh Reactor Context. Dùng reactive instrumentation/context-propagation integration phù hợp hoặc bridge MDC tại ranh giới logging theo version; không đặt MDC một lần ở đầu chain rồi giả định mọi operator downstream dùng cùng thread.

Với messaging:

- Producer đưa Correlation ID vào message header theo contract đã thống nhất.
- Consumer validate header trước khi đưa vào logging context.
- Scope MDC được mở trong lúc xử lý message và đóng trong finally.
- Retry/dead-letter nên giữ correlation convention có ý nghĩa, đồng thời có message ID riêng để phân biệt từng lần giao/attempt.
- Tracing context W3C được inject/extract riêng theo messaging instrumentation; không thay thế bằng Correlation ID.

Một batch có thể chứa nhiều message với nhiều Correlation ID. Không ép một ID duy nhất lên toàn batch nếu điều đó làm mất liên kết tới từng message; chọn log event ở cấp batch và cấp item phù hợp, giới hạn số trường để tránh log volume quá lớn.

## 9. Correlation ID, cardinality và quyền riêng tư

Correlation ID thường gần như duy nhất cho từng request. Đây là giá trị phù hợp để **search trong logs**, nhưng không phù hợp làm metric tag:

| Nơi sử dụng | Có nên gắn Correlation ID? | Lý do |
| --- | --- | --- |
| Structured log field | Có, nếu được kiểm soát | Tìm log liên quan nhanh |
| HTTP response header | Có thể | Giúp caller/support cung cấp ID để tra cứu |
| Internal downstream header | Có thể | Duy trì nhóm log theo contract |
| Metric labels | Không | Cardinality cao, tạo nhiều time series |
| Resource attributes | Không | Resource cần ổn định theo service/process |
| Authorization/identity | Không | ID không phải credential hoặc bằng chứng danh tính |

Không chứa user email, số điện thoại, access token, session secret hoặc dữ liệu nghiệp vụ trong ID. Nếu ID do client cung cấp và được echo lại, cần validate để ngăn log injection/header injection. Không ghi chuỗi có CR/LF hoặc dữ liệu có thể tạo dòng log giả.

Correlation ID không phải bí mật nhưng có thể trở thành khóa truy vấn dữ liệu nội bộ. Hạn chế quyền truy cập log backend, đặt retention phù hợp và tránh đưa ID vào URL public nếu không có yêu cầu.

## 10. Log correlation cùng Trace ID trong Spring Boot

Khi Micrometer Tracing được cấu hình, logging integration có thể bổ sung Trace ID và Span ID vào MDC cho span đang hoạt động. Correlation ID do ứng dụng quản lý có thể cùng tồn tại:

```text
timestamp=2026-11-22T10:15:02.120Z
service=orders-service
level=INFO
correlationId=req-7f31c8a2
traceId=4bf92f3577b34da6a3ce929d0e0e4736
spanId=00f067aa0ba902b7
message="Calling payment service"
```

Khi điều tra:

1. Tìm `correlationId` để gom log theo request/workflow.
2. Dùng `traceId` để mở distributed trace nếu trace được sampling và export thành công.
3. Dùng `spanId` để liên hệ log với thao tác cụ thể trong trace.
4. Dùng Business ID qua truy vấn có phân quyền để xem trạng thái nghiệp vụ.

Trace không tìm thấy trong backend không đồng nghĩa Correlation ID sai. Trace có thể bị sampling loại, exporter/collector lỗi hoặc retention đã hết. Ngược lại, logs có Correlation ID không chứng minh các service đã propagation đúng; cần kiểm tra header và log context ở từng service.

## 11. Quy trình điều tra khi thiếu log correlation

Giả sử log của hai service:

```text
orders-service correlationId=req-7f31c8a2 "Payment request started"
payment-service correlationId=req-99ab4d10 "Provider timeout"
```

Hai ID khác nhau là dấu hiệu correlation bị thay đổi hoặc hai log không thuộc cùng request. Điều tra theo thứ tự:

1. Xác nhận hai log thực sự thuộc cùng một lần gọi bằng thời gian, downstream route và business event được phép.
2. Kiểm tra gateway có tạo hoặc ghi đè `X-Correlation-ID` không.
3. Kiểm tra outgoing HTTP client có truyền custom header theo contract không.
4. Kiểm tra filter phía payment-service có validate và tiếp tục ID hợp lệ không.
5. Kiểm tra async/executor/reactive/message boundary có làm mất MDC/context không.
6. Kiểm tra filter order và cleanup để tránh context cũ hoặc filter chạy trùng.
7. Đối chiếu Trace ID/Span ID và traceparent riêng biệt để xác định distributed trace có còn liền mạch không.
8. Kiểm tra logging pattern/JSON encoder có đọc đúng MDC field ở mỗi service không.

### Bảng chẩn đoán nhanh

| Dấu hiệu | Nguyên nhân cần xem | Kiểm tra |
| --- | --- | --- |
| Correlation ID thiếu ở mọi log của request | Filter chưa chạy hoặc sai order | Filter registration và URL pattern |
| Chỉ một service có ID | Header outbound không được truyền hoặc downstream không đọc | Client interceptor, gateway, server filter |
| ID thay đổi ở downstream | Header bị tạo lại, không hợp lệ hoặc untrusted policy | Validation và trust boundary |
| ID của request trước xuất hiện ở request sau | MDC không được dọn/restore | try/finally, thread reuse |
| Log trong async thiếu ID | Context không qua executor | TaskDecorator hoặc capture/restore |
| Trace ID có nhưng Correlation ID không có | Tracing integration có, custom filter chưa có | MDC key và filter |
| Correlation ID có nhưng Trace ID rỗng | Không có active span hoặc trace integration chưa bật | Tracing bridge, scope và sampled context |
| JSON log không filter được theo ID | Encoder ghi ID vào message thay vì field | Structured logging encoder |

## 12. Kiểm thử filter và MDC

Một bài kiểm thử tích hợp nên xác minh:

| Input request | Kỳ vọng |
| --- | --- |
| Không có header | Ứng dụng sinh ID mới và trả response header |
| Header hợp lệ | ID được giữ theo policy và xuất hiện trong MDC/log |
| Header quá dài | Không đưa raw value vào MDC; tạo ID mới hoặc từ chối |
| Header chứa CR/LF | Bị loại vì không hợp lệ |
| Request ném exception | MDC vẫn được khôi phục trong finally |
| Hai request liên tiếp trên cùng thread | ID request thứ hai không bị ảnh hưởng bởi request đầu |
| Downstream HTTP call | Header custom được truyền theo contract |
| Executor task | ID được capture/restore và cleanup sau task |
| Logging pattern | Correlation ID, Trace ID và Span ID ở đúng field riêng |

Không kiểm thử bằng cách chỉ gọi `MDC.put()` trong unit test rồi kết luận HTTP filter chạy đúng. Cần kiểm tra qua servlet filter chain, response headers, log appender/encoder và nếu có thể cả downstream stub.

## 13. Bài tập tình huống

Một request đi vào `orders-service` không có Correlation ID. Filter tạo `req-a71c9d` và log:

```text
orders-service correlationId=req-a71c9d traceId=aaaa... "Order started"
orders-service correlationId=req-a71c9d traceId=aaaa... "Calling payment"
payment-service  correlationId=req-b208f1 traceId=aaaa... "Payment declined"
```

Trace ID giống nhau nhưng Correlation ID ở payment-service khác.

**Câu hỏi:**

1. Có thể kết luận distributed tracing propagation bị lỗi không?
2. Nguyên nhân nào có thể làm Correlation ID thay đổi trong khi Trace ID vẫn giống?
3. Nên kiểm tra thành phần nào trước?
4. Có nên bỏ Correlation ID và dùng Trace ID hoàn toàn không?

**Gợi ý phân tích:**

- Chưa thể kết luận tracing propagation sai vì Trace ID vẫn giống nhau; span relationship cần được kiểm tra riêng.
- Gateway/client interceptor có thể không truyền `X-Correlation-ID`, filter payment-service có thể tạo ID mới khi header thiếu/không hợp lệ, hoặc trust policy chủ động thay ID tại boundary.
- Kiểm tra outbound custom header, network/proxy behavior, validation filter và log context của payment-service.
- Nếu workflow nằm trong cùng distributed trace và Trace ID đáp ứng nhu cầu tìm log, có thể dùng trace/span IDs từ logging integration. Correlation ID riêng vẫn hữu ích cho workflow kéo dài qua nhiều trace, queue hoặc hệ thống không hỗ trợ distributed tracing. Chỉ giữ nó khi có semantics và quy tắc propagation rõ ràng.

### Checklist hoàn thành

| Nội dung | Xác nhận |
| --- | --- |
| Vai trò Correlation ID | Tìm log cùng request/workflow |
| Phân biệt Trace ID/Span ID | Không dùng thay cho Correlation ID |
| Nguồn tạo ID | Có quy tắc trust boundary và validation |
| Servlet filter | Tạo/nhận ID, đặt MDC, trả response header |
| MDC cleanup | Khôi phục giá trị cũ trong finally |
| Logging pattern | Ghi correlationId, traceId và spanId riêng |
| HTTP propagation | Truyền custom header theo contract, không ghi đè traceparent |
| Async/reactive/message | Có context propagation phù hợp |
| Cardinality/privacy | Không đưa ID vào metric labels hoặc dữ liệu nhạy cảm |
| Điều tra | Kết hợp logs, traces và metrics mà không nhầm vai trò |

**Ghi nhớ:** Correlation ID là định danh theo quy ước để gom log của cùng request hoặc workflow. Trong Spring Boot, có thể validate hoặc tạo ID ở filter, đặt nó vào MDC trong thời gian xử lý, ghi bằng Logback/JSON encoder và truyền qua downstream theo contract. MDC không tự truyền qua thread hoặc reactive scheduler; cần cơ chế context propagation và cleanup đúng lifecycle. Correlation ID khác Trace ID, Span ID và Business ID; hãy giữ chúng thành các trường riêng, không dùng làm metric tag, credential hay nơi chứa thông tin cá nhân.
