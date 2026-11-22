# Che token, mật khẩu và dữ liệu cá nhân trong log hoặc thông điệp lỗi

Trong hệ thống Spring Boot tích hợp qua HTTP client, cơ sở dữ liệu, cache, broker thông điệp và các adapter của Spring Integration, dữ liệu nhạy cảm có thể đi qua nhiều lớp: request, header, kết nối, message payload, exception, log, trace và dead-letter queue. Chỉ cần một dòng `log.error("request failed", exception)` hoặc một công cụ HTTP wire logging được bật sai thời điểm, token hoặc dữ liệu cá nhân có thể bị ghi vào hệ thống giám sát có số người và dịch vụ truy cập lớn hơn hệ thống gốc.

Bài học này giải thích cách **không để bí mật xuất hiện trong log từ đầu**, cách che hoặc loại bỏ dữ liệu khi cần ghi chẩn đoán, và cách thiết kế thông điệp lỗi an toàn nhưng vẫn đủ thông tin để vận hành luồng tích hợp. Đây là một phần của **bảo mật kết nối**: mã hóa TLS và lưu mật khẩu trong secret manager chỉ bảo vệ một số chặng; bản sao của dữ liệu trong log, exception và message lỗi vẫn cần được kiểm soát độc lập.

## 1. Kết quả học tập và tình huống thực tế

Sau bài học, bạn có thể:

- Phân loại token, mật khẩu, khóa truy cập, dữ liệu cá nhân và thông tin chẩn đoán được phép ghi.
- Nhận ra những nơi Spring Boot/Spring Integration có thể vô tình log header, request/response body hoặc exception chứa bí mật.
- Thiết kế logging theo **danh sách trường an toàn được cho phép (allowlist)**, kết hợp redaction như một lớp phòng vệ bổ sung.
- Trả thông điệp lỗi HTTP theo hợp đồng ổn định mà không lộ URL có credential, access token, dữ liệu đầu vào hay stack trace.
- Kiểm soát thông tin nhạy cảm trong log của HTTP client, JDBC/JPA/MongoDB, cache, JMS/Kafka/RabbitMQ và error channel.
- Kiểm thử cả log, response, trace và dead-letter data trước khi phát hành.
- Xử lý sự cố nếu bí mật đã được ghi ra log hoặc hệ thống quan sát.

**Tình huống:** một API nhận yêu cầu thanh toán, gọi đối tác bằng bearer token, lưu trạng thái giao dịch vào database rồi gửi sự kiện tới broker. Đối tác trả lỗi `401` kèm một nội dung phản hồi, trong đó có thể chứa phần header hoặc dữ liệu khách hàng. Nếu ứng dụng ghi nguyên exception hoặc trả trực tiếp nội dung lỗi đối tác cho người gọi, dữ liệu nhạy cảm có thể bị phát tán qua nhiều hệ thống ngay cả khi kết nối HTTPS được cấu hình đúng.

## 2. Phân loại dữ liệu trước khi quyết định ghi log

Không phải mọi giá trị giống nhau về độ nhạy cảm hoặc yêu cầu chẩn đoán.

| Nhóm dữ liệu | Ví dụ | Quy tắc thực hành |
|---|---|---|
| **Bí mật xác thực** | Password, bearer/access/refresh token, API key, cookie phiên, mã OTP, khóa riêng, connection string chứa credential | **Không ghi** vào log, metric, trace, HTTP error response, DLQ metadata hay thông báo hỗ trợ |
| **Dữ liệu cá nhân** | Tên, email, số điện thoại, địa chỉ, định danh cá nhân, IP tùy ngữ cảnh, dữ liệu tài chính | Chỉ dùng khi có mục đích rõ ràng và kiểm soát truy cập/lưu giữ; ưu tiên bỏ hoặc dùng mã định danh giả |
| **Dữ liệu nghiệp vụ cần bảo vệ** | Nội dung hợp đồng, số dư, payload giao dịch, dữ liệu khách hàng trong message | Không log toàn bộ đối tượng; chỉ ghi loại thao tác và trạng thái đã phân loại |
| **Metadata chẩn đoán tương đối an toàn** | Tên adapter cố định, loại thao tác, HTTP status, error code nội bộ, thời lượng, số lần retry | Có thể ghi nếu không chứa dữ liệu do người dùng tự do cung cấp |
| **ID liên kết luồng** | Correlation ID do hệ thống sinh, trace ID, job ID ngẫu nhiên | Có thể dùng để liên kết sự kiện; hạn chế thông tin cá nhân và tránh dùng token làm ID |

Ví dụ:

```text
KHÔNG AN TOÀN
Authorization: Bearer eyJhbGciOi...
GET /partner/customer?email=example@domain.test&api_key=...
jdbc:postgresql://db.example/app?user=service&password=...
Message failed: CustomerUpdate(email=..., phone=..., accessToken=...)

CÓ THỂ CHẤP NHẬN SAU KHI XEM XÉT
event=partner_call_failed
partner=billing
operation=createPayment
httpStatus=401
errorCode=UPSTREAM_AUTH_REJECTED
correlationId=7c8d...             # ID ngẫu nhiên do ứng dụng sinh
durationMs=184
retryable=false
```

**“Che” không đồng nghĩa luôn giữ lại một phần giá trị.** Với token, password và API key, lựa chọn mặc định là **loại bỏ hoàn toàn**. Hiển thị vài ký tự đầu/cuối của một token vẫn có thể hữu ích cho kẻ tấn công khi ghép dữ kiện hoặc khi token có định dạng ngắn/dự đoán được. Nếu thật sự cần nhận diện một credential bị lặp, hãy dùng mã định danh do hệ thống quản lý hoặc một fingerprint được thiết kế, kiểm soát khóa và thời gian lưu giữ riêng.

Đối với email, số điện thoại hay định danh khách hàng, việc che bớt ký tự hoặc băm đơn thuần chưa chắc khiến dữ liệu trở nên vô danh. Dữ liệu giả danh (*pseudonymized*) vẫn cần được quản trị như dữ liệu có thể liên kết tới cá nhân.

## 3. Các đường rò rỉ thường gặp trong Spring Boot Integration

```mermaid
flowchart LR
    A["HTTP request / message"] --> B["Spring Boot service"]
    B --> C["HTTP client / database / cache"]
    B --> D["JMS / Kafka / RabbitMQ"]
    C --> E["Exception / retry handler"]
    D --> E
    B --> F["Application log"]
    E --> F
    E --> G["HTTP error body"]
    E --> H["Error channel / DLQ"]
    F --> I["Log collector / APM"]
    H --> I
```

Dữ liệu có thể bị lộ tại nhiều nơi hơn một lời gọi `logger.info(...)`:

1. **Tự động in đối tượng:** Java record, Lombok `@Data` hoặc `@ToString`, Kotlin data class và các object mapper có thể tạo chuỗi chứa đầy đủ field nhạy cảm.
2. **Log HTTP request/response:** client interceptor, proxy, gateway access log, wiretap, trace filter hoặc API debug dump có thể ghi header `Authorization`, `Cookie`, query parameter và body.
3. **Exception và stack trace:** `Throwable#getMessage()` và `Throwable#toString()` có thể chứa URL, SQL, payload, response body hoặc thông tin do hệ thống ngoài trả về. Log cả throwable thường kéo theo message của toàn bộ cause chain.
4. **Validation errors:** đối tượng binding error có thể giữ `rejectedValue`, ví dụ password do người dùng vừa nhập.
5. **Messaging error:** Spring Integration `ErrorMessage` hoặc `MessagingException#getFailedMessage()` có thể chứa message thất bại, header và payload gốc; dead-letter message cũng có thể lưu bản sao đó.
6. **Dữ liệu truy vấn:** ORM SQL bind-value logging, MongoDB command logging, cache key hoặc log deserialization có thể ghi payload cá nhân và credential.
7. **Observability:** span attributes, baggage, metric tags, audit event và dashboard có thể chứa URL/query/body/headers hoặc user ID có tính định danh.
8. **File và storage:** tên tệp, đường dẫn hoặc metadata của adapter có thể chứa tên khách hàng, email hoặc secret trong signed URL.

Vì log được sao chép sang hệ thống tập trung, bản sao lưu và công cụ cảnh báo, việc xóa một log line khỏi console ứng dụng **không đảm bảo** mọi bản sao đã biến mất.

## 4. Chiến lược ưu tiên: không ghi dữ liệu nhạy cảm từ đầu

Thứ tự bảo vệ nên là:

1. **Không tạo log chứa bí mật.** Mỗi sự kiện log chỉ có những trường cần thiết để vận hành.
2. **Dùng DTO hoặc sự kiện log riêng.** Không truyền nguyên request, response, message, entity hoặc exception có thể giữ dữ liệu nhạy cảm vào logger.
3. **Chuẩn hóa lỗi.** Biến lỗi bên ngoài thành error code và trường chẩn đoán an toàn; không chuyển nguyên lỗi cho client khác.
4. **Dùng redaction ở biên log/export.** Đây là lớp giảm tác hại nếu một đường log vô ý xuất hiện; không thể thay kiểm soát ở bước 1.
5. **Giới hạn quyền và thời gian lưu giữ.** Áp dụng cho log, traces, audit, DLQ và kho dữ liệu chẩn đoán.

### 4.1. Tránh log toàn bộ DTO

Ví dụ không phù hợp:

```java
record PaymentRequest(
        String customerEmail,
        String cardToken,
        String authorizationToken,
        long amountInMinorUnits
) {}

log.info("Processing payment: {}", paymentRequest);
```

Với Java record, `toString()` mặc định thường bao gồm giá trị của các thành phần. Ngay cả khi một field dùng `@JsonIgnore` hoặc `@JsonProperty(access = WRITE_ONLY)` để điều khiển JSON, điều đó **không phải** cơ chế che giá trị trong `toString()` của Java record hay trong mọi thư viện log.

Thay bằng thông tin cho phép:

```java
log.info(
    "payment_request_received operation={} amountCurrency={} correlationId={}",
    "createPayment",
    "VND",
    correlationId
);
```

Nếu cần biết số tiền để điều tra lỗi, hãy cân nhắc yêu cầu bảo vệ dữ liệu, độ chính xác và quyền xem log; không tự động đưa mọi field nghiệp vụ vào log chỉ vì nó “không phải password”.

### 4.2. Tránh truyền `Throwable` không kiểm soát

```java
// Rủi ro: exception có thể chứa response body, URL có token,
// SQL bind values hoặc thông tin trong nested cause.
log.error("Partner request failed", exception);

// An toàn hơn khi loại lỗi đã được phân loại:
log.warn(
    "partner_call_failed partner={} operation={} status={} correlationId={}",
    "billing",
    "createPayment",
    safeHttpStatus,
    correlationId
);
```

Điều này **không có nghĩa bỏ toàn bộ khả năng chẩn đoán stack trace**. Với exception không chứa dữ liệu nhạy cảm đã được kiểm soát, có thể ghi stack trace ở kênh phù hợp. Với lỗi từ HTTP client, database driver hoặc nguồn ngoài, đừng giả định message của exception luôn sạch. Có thể ghi tên loại exception đã kiểm tra, mã lỗi do hệ thống tự định nghĩa và correlation ID; dùng cơ chế thu thập chẩn đoán hạn chế quyền khi thực sự cần dữ liệu sâu hơn.

## 5. Tạo correlation ID an toàn cho một luồng tích hợp

Correlation ID giúp nối log từ controller, HTTP client, database, retry handler và message consumer mà không cần in payload. Mã định danh nên độc lập với credential và dữ liệu người dùng.

Ví dụ cho ứng dụng Spring Boot 3.x Servlet:

```java
import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class CorrelationIdFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {
        String correlationId = UUID.randomUUID().toString();
        response.setHeader("X-Correlation-Id", correlationId);

        try (MDC.MDCCloseable ignored =
                     MDC.putCloseable("correlationId", correlationId)) {
            filterChain.doFilter(request, response);
        }
    }
}
```

Đây là ví dụ Servlet đồng bộ. Với WebFlux, `@Async`, Reactor hoặc `ExecutorChannel` của Spring Integration, MDC vốn gắn với thread **không tự động đi qua mọi ranh giới bất đồng bộ**. Cần dùng cơ chế truyền context tương ứng với framework và phiên bản ứng dụng. Nếu hệ thống chấp nhận correlation ID từ request header bên ngoài, phải kiểm tra giới hạn độ dài, ký tự và độ tin cậy; có thể sinh ID mới và lưu liên hệ với ID bên ngoài trong vùng kiểm soát.

Không đặt access token, email hay số điện thoại vào `MDC` hoặc tracing baggage chỉ để dễ tìm log: những giá trị đó có thể được sao chép tới nhiều span, log appender và downstream service.

## 6. Che dữ liệu trong HTTP client và log kết nối

### 6.1. Những thông tin phải loại trừ

Khi dùng `RestClient`, `RestTemplate`, `WebClient`, Feign hoặc thư viện HTTP nền, tránh ghi:

- Header xác thực: `Authorization`, `Proxy-Authorization`, `Cookie`, `Set-Cookie`, `X-API-Key` và các tên credential riêng của đối tác.
- Query chứa `token`, `code`, `key`, `password`, signed URL, presigned URL hoặc chuỗi truy vấn tự do chưa được duyệt.
- Request/response body có thông tin khách hàng, card token, credential, thông điệp lỗi upstream hoặc payload nghiệp vụ bí mật.
- Raw URI nếu phần userinfo hoặc query có thể chứa credential.
- Kết nối có chứng chỉ, key material hoặc client secret.

Tránh bật HTTP **wire logging** hoặc body logging tràn lan trong môi trường xử lý dữ liệu thật. Debug level của HTTP library, interceptor tự viết, request-response logging filter hoặc APM instrumentation đều cần được kiểm tra riêng: việc set application logger thành `INFO` không chắc vô hiệu hóa mọi kênh ghi ở lớp gateway/agent.

### 6.2. Ví dụ: log metadata khi upstream trả lỗi

Với `RestClient` trên Spring Boot 3.x, mã minh họa:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

@Service
public class PaymentGateway {

    private static final Logger log =
            LoggerFactory.getLogger(PaymentGateway.class);

    private final RestClient restClient;

    public PaymentGateway(RestClient restClient) {
        this.restClient = restClient;
    }

    public PaymentReceipt charge(
            PaymentCommand command,
            String correlationId
    ) {
        try {
            return restClient.post()
                    .uri("/payments")
                    .body(command)
                    .retrieve()
                    .body(PaymentReceipt.class);
        } catch (RestClientResponseException ex) {
            log.warn(
                "payment_upstream_rejected operation={} httpStatus={} correlationId={}",
                "charge",
                ex.getStatusCode().value(),
                correlationId
            );

            // Không chuyển ex.getResponseBodyAsString(), ex.getMessage(),
            // response headers hoặc raw URI sang API error/ordinary log.
            throw new PaymentGatewayUnavailableException();
        }
    }
}
```

`PaymentCommand`, `PaymentReceipt` và `PaymentGatewayUnavailableException` là các kiểu nghiệp vụ minh họa; `RestClient` phải được cấu hình endpoint, timeout và credential qua bean/configuration tương ứng của dự án. Ví dụ giữ lại **mã HTTP** và correlation ID để vận hành, không ghi nội dung trả về từ đối tác.

Trong thực tế, lỗi `4xx` có thể biểu thị request nghiệp vụ không hợp lệ, còn `5xx` hoặc timeout có thể được retry. Hãy phân loại thành error code nội bộ riêng; không dùng cùng một exception cho mọi trạng thái nếu điều đó làm sai chính sách retry. Đối với lỗi I/O/timeout không có HTTP status, log `failureKind` được phân loại thay vì in nguyên exception.

### 6.3. Với interceptor hoặc filter HTTP

Nếu cần một interceptor ghi hoạt động HTTP, hãy chọn trường được phép theo **đường dẫn đã chuẩn hóa**:

```text
method=POST
route=/partners/{partnerId}/payments   # template tĩnh, không phải full URL
partner=billing
status=502
durationMs=215
attempt=2
correlationId=<UUID nội bộ>
```

Không ghi `request.getURI().toString()` khi query có thể chứa token. Không tự lưu request/response body vào buffer chỉ để logging: ngoài rủi ro dữ liệu, buffering còn làm tăng bộ nhớ và có thể ảnh hưởng tới streaming.

## 7. Thông điệp lỗi HTTP an toàn với `ProblemDetail`

Thông điệp lỗi trả về người gọi cần đủ rõ để khách hàng biết cách xử lý, nhưng không nên chứa exception nội bộ hoặc dữ liệu của đối tác. Với Spring Framework 6/Spring Boot 3.x, có thể dùng `ProblemDetail` trong `@RestControllerAdvice`.

Ví dụ:

```java
import org.slf4j.MDC;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class SafeApiErrorHandler {

    @ExceptionHandler(PaymentGatewayUnavailableException.class)
    public ResponseEntity<ProblemDetail> paymentUnavailable(
            PaymentGatewayUnavailableException ex
    ) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_GATEWAY,
                "Không thể hoàn tất giao dịch với dịch vụ phụ thuộc lúc này."
        );
        problem.setTitle("Dịch vụ phụ thuộc chưa sẵn sàng");
        problem.setProperty("code", "PAYMENT_PROVIDER_UNAVAILABLE");

        String correlationId = MDC.get("correlationId");
        if (correlationId != null) {
            problem.setProperty("correlationId", correlationId);
        }

        return ResponseEntity.status(HttpStatus.BAD_GATEWAY).body(problem);
    }
}
```

Ví dụ phản hồi:

```json
{
  "type": "about:blank",
  "title": "Dịch vụ phụ thuộc chưa sẵn sàng",
  "status": 502,
  "detail": "Không thể hoàn tất giao dịch với dịch vụ phụ thuộc lúc này.",
  "code": "PAYMENT_PROVIDER_UNAVAILABLE",
  "correlationId": "0a63e52c-7f06-49e8-bd32-5916b0ad4391"
}
```

Ở đây, `status`, `code` và `correlationId` có ý nghĩa hỗ trợ vận hành; response không chứa token, body lỗi upstream, stack trace, host nội bộ hoặc cấu hình database.

### 7.1. Không trả thẳng `exception.getMessage()`

Tránh các kiểu xử lý:

```java
// Không an toàn:
return ResponseEntity.status(500).body(
        Map.of("error", exception.getMessage())
);

// Không an toàn:
return ResponseEntity.status(500).body(exception);

// Không an toàn nếu BindingResult chứa rejectedValue (ví dụ password):
return ResponseEntity.badRequest().body(bindingResult.getAllErrors());
```

Lỗi validation nên trả một mã như `VALIDATION_FAILED` và danh sách **tên trường được phép** cùng các thông báo cố định, ví dụ `email: INVALID_FORMAT`. Đừng đưa giá trị bị từ chối (`rejectedValue`) hoặc chuỗi input chưa kiểm soát vào response và log.

Một exception xảy ra từ JDBC, MongoDB hay HTTP client có thể bao gồm chuỗi kết nối, URI, câu truy vấn hoặc message do máy chủ ngoài tạo ra. Cần tách thành **internal error classification** và **public error contract**, thay vì dùng nguyên message của driver.

### 7.2. Cấu hình lỗi mặc định và Actuator

Với cấu hình Spring Boot 3.x, một baseline bảo thủ là:

```yaml
server:
  error:
    include-message: never
    include-stacktrace: never
    include-binding-errors: never
    include-exception: false

spring:
  mvc:
    log-request-details: false
  codec:
    log-request-details: false

management:
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never

logging:
  level:
    org.springframework.web: INFO
    reactor.netty.http.client: INFO
```

Các thuộc tính này chỉ tác động tới những cơ chế Spring Boot tương ứng. `server.error.*` không thay thế việc kiểm soát JSON tự tạo bởi `@RestControllerAdvice`; `show-values: never` giúp hạn chế việc hiển thị giá trị cấu hình ở Actuator endpoint tương ứng, nhưng **không bảo vệ** những thông tin đã bị ghi bởi logger hoặc thư viện khác. Các endpoint Actuator vẫn cần giới hạn exposure và bảo vệ bằng xác thực/phân quyền/mạng.

Tùy phiên bản Spring Boot và ứng dụng Servlet hay WebFlux, hãy đối chiếu tên property và cấu hình logging thực tế; không giả định một thuộc tính YAML có thể kiểm soát mọi thư viện nền.

## 8. Redaction khi bắt buộc phải xử lý nội dung động

Khi có yêu cầu ghi một phần dữ liệu động để hỗ trợ vận hành, hãy xác định ranh giới rõ:

- **Allowlist trường:** chỉ serialize các trường đã được đánh giá an toàn, thay vì serialize mọi field rồi cố xóa một số.
- **Phân loại theo cấu trúc:** xử lý JSON, HTTP headers, query parameter và message properties dưới dạng field/value. Mask tên header phân biệt hoa thường; các tên bí mật do từng đối tác định nghĩa phải được bổ sung.
- **Giá trị thay thế nhất quán:** ví dụ `[REDACTED]`; không giữ lại prefix token nếu không có nhu cầu được phê duyệt.
- **Giới hạn kích thước và định dạng:** không cần ghi payload lớn, binary body, file attachment hoặc đối tượng chưa xác định schema.
- **Escaping và chuẩn hóa:** dữ liệu do đối tác/người dùng cung cấp có thể chứa xuống dòng, ký tự điều khiển hoặc chuỗi giả dạng log; không cho dữ liệu thô phá cấu trúc log.

Ví dụ biểu diễn log của một tập header đã được kiểm tra:

```java
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

public final class HeaderRedactor {
    private HeaderRedactor() {}

    private static final Set<String> SENSITIVE = Set.of(
            "authorization",
            "proxy-authorization",
            "cookie",
            "set-cookie",
            "x-api-key"
    );

    public static Map<String, String> redact(Map<String, String> headers) {
        return headers.entrySet().stream().collect(Collectors.toMap(
                Map.Entry::getKey,
                entry -> SENSITIVE.contains(
                        entry.getKey().toLowerCase(Locale.ROOT)
                ) ? "[REDACTED]" : entry.getValue()
        ));
    }
}
```

**Giới hạn quan trọng:** hàm trên chỉ minh họa cách che theo tên header. Nó **không phải** một bộ lọc log đầy đủ hoặc đủ an toàn để ghi tất cả header. Những header khác vẫn có thể chứa dữ liệu cá nhân, token riêng của đối tác hoặc chuỗi gây log injection. Trong production, nên sử dụng **allowlist các tên header cụ thể được phép ghi**, và chỉ cần redactor như một lớp phòng vệ phụ.

### Vì sao regex tổng quát không đủ?

Một regex tìm chuỗi `password=...` thường không phát hiện credential nằm trong:

- JSON lồng nhau, URL-encoded form, Basic auth hoặc bearer token bị chia chuỗi.
- Header có tên riêng, chữ hoa/thường khác nhau, token nhiều dòng hoặc nhiều lớp encoding.
- Exception message và stack trace không có tên trường nhất quán.
- Dữ liệu cá nhân nằm trong giá trị tự do không có từ khóa như `password`.

Có thể bổ sung lọc dựa trên pattern để giảm thiệt hại tại log collector, nhưng nên kiểm thử trên định dạng thật, coi thất bại redaction là lỗi bảo mật và giữ thiết kế **không ghi payload ban đầu** làm chính.

## 9. Log ở database, cache và cấu hình kết nối

Đặc biệt thận trọng với các cơ chế logging dưới tầng truy cập dữ liệu.

| Thành phần | Điểm rủi ro | Hướng bảo vệ |
|---|---|---|
| JDBC/JPA/Hibernate | SQL bind parameter, query chứa PII hoặc password; URL kết nối | Tránh bind-value logging trên dữ liệu thật; không log datasource URL có credentials |
| MongoDB | Command/driver debug logs có thể phản ánh document hoặc filter nhạy cảm | Giới hạn log level; quan sát latency/status thay vì raw command/payload |
| Redis/cache | Cache key/entry chứa email, session ID, token hoặc dữ liệu cá nhân | Thiết kế key không nhúng bí mật; không log nguyên entry/value |
| Connection pool | Exception khi kết nối, cấu hình host/user hoặc property | Chỉ ghi mã loại lỗi và tên datasource logic; không đưa password hay DSN vào logger |
| Config/secret resolution | Secret trong environment variable, application properties, config dump | Không in cấu hình toàn bộ khi khởi động; dùng secret manager và quyền Actuator phù hợp |

Ví dụ, SQL bind tracing giúp debug câu truy vấn nhưng có thể ghi trực tiếp email, số tài khoản hoặc access token trong điều kiện `WHERE`/`INSERT`. Khi cần xử lý sự cố có thời hạn, hãy dùng môi trường kiểm soát, dữ liệu thử nghiệm hoặc cơ chế quan sát không xuất raw parameter.

Đừng gửi password database tới HTTP error response chỉ vì cấu hình đã được tải từ environment variable: exception của driver hoặc connection pool vẫn có thể chứa chi tiết kết nối.

## 10. Bảo vệ message, error channel và dead-letter queue

Trong luồng JMS/Kafka/RabbitMQ và Spring Integration, một lỗi xử lý có thể làm message gốc được ghi vào log hoặc lưu vào DLQ. Payload có thể chứa thông tin cá nhân; header có thể chứa credential hoặc dữ liệu ủy quyền.

### 10.1. Rủi ro với `ErrorMessage`

Spring Integration có thể đưa exception vào `errorChannel` dưới dạng `ErrorMessage`. Với `MessagingException`, `getFailedMessage()` có thể tham chiếu message đã thất bại, bao gồm payload và headers. Vì vậy:

```java
// Rủi ro: có thể in payload/header và exception message.
log.error("Spring Integration error: {}", errorMessage);
log.error("Flow failed", messagingException);
log.error("Failed message: {}", messagingException.getFailedMessage());
```

Thay vào đó, một error handler nên xuất **bản tóm tắt được kiểm soát**:

```java
public void handleIntegrationError(
        String flowName,
        String failureCode,
        String correlationId,
        String destinationAlias
) {
    log.warn(
        "integration_flow_failed flow={} code={} destination={} correlationId={}",
        flowName, failureCode, destinationAlias, correlationId
    );
}
```

`flowName`, `failureCode` và `destinationAlias` trong ví dụ phải là các giá trị đã chuẩn hóa hoặc từ danh mục cấu hình tin cậy; không lấy nguyên `toString()` của message/header làm tham số. Nếu cần chuyển bản ghi lỗi đi xa hơn, tạo một **error envelope riêng** chứa message ID, flow ID, error code, thời điểm và tham chiếu đến dữ liệu được bảo vệ, không tự sao chép nguyên exception.

### 10.2. DLQ không phải nơi chứa thông tin công khai

Trong một số hệ thống, việc đưa message thất bại vào DLQ là cần thiết để có thể phát lại hoặc điều tra. Tuy nhiên, DLQ có thể lưu toàn bộ payload gốc; hành động đó không tự tương đương với “đã redacted”.

Phân biệt:

- **DLQ cần payload để retry:** mã hóa khi lưu/truyền khi phù hợp, kiểm soát ACL, người tiêu thụ, retention, công cụ xem và chính sách xóa. Tránh thêm stack trace hoặc credential vào headers DLQ.
- **Error telemetry:** chỉ xuất ID, mã lỗi, retry count, trạng thái và loại flow đã được phép.
- **Bản ghi hỗ trợ hoặc dashboard:** có thể chỉ dẫn tới message ID/job ID đã kiểm soát; không cho phép nhấn để xem raw payload nếu người dùng thiếu quyền.

Khi publish sang broker, cần tránh đưa bearer token của HTTP request vào message header để “truyền context”. Consumer phải được cấp credential phù hợp bằng cơ chế danh tính/dịch vụ của nó; correlation ID không phải credential.

### 10.3. Retry, idempotency và tính quan sát

Che dữ liệu không được làm mất khả năng phân tích lỗi xử lý trùng. Hãy dùng `eventId`/`requestId` an toàn, loại event đã chuẩn hóa, `attemptCount`, `failureCode` và timestamp để biết một message đã được retry bao nhiêu lần. Đừng chọn toàn bộ payload hoặc token làm khóa chống trùng. Idempotency key cần có cấu trúc và chính sách lưu giữ phù hợp; nếu chứa dữ liệu cá nhân thì vẫn phải được bảo vệ.

## 11. Tracing, metrics và các lớp ghi ngoài ứng dụng

Ngay cả khi tất cả lời gọi `Logger` đã an toàn, dữ liệu vẫn có thể đi qua:

- **APM/tracing:** URL đầy đủ, HTTP headers, SQL statement, exception message, baggage và custom span attributes.
- **Metrics:** nhãn `userId`, `email`, `orderId` hoặc full URL dẫn đến vừa lộ dữ liệu vừa gây cardinality rất cao.
- **Reverse proxy/API gateway:** access log có query string; các plugin request logging hoặc WAF audit có thể giữ request body.
- **Infrastructure:** container stdout, service mesh, ingress/controller, audit logs, crash dump hoặc support bundle.
- **Notification:** alert gửi Slack/email/ticket có thể đính kèm nguyên log chứa dữ liệu nhạy cảm.

Một span có thể đủ thông tin với các thuộc tính được duyệt như:

```text
integration.system = "billing"
integration.operation = "charge"
integration.status = "failed"
error.type = "UPSTREAM_TIMEOUT"
http.response.status_code = 504
retry.attempt = 2
```

Đây là ví dụ về tên trường cho quan sát nội bộ, không phải cam kết mọi exporter có cùng tên chuẩn. Với Micrometer Observation/OpenTelemetry, hãy kiểm tra các observation convention và instrumentations đang bật, loại khỏi span attributes các header nhạy cảm, raw URI, body và thông tin cá nhân. Metric labels nên có tập giá trị hữu hạn, từ danh mục tĩnh.

## 12. Kiểm thử che dữ liệu và hợp đồng lỗi

Chỉ đọc code không chứng minh mọi dữ liệu đã được loại bỏ. Kiểm thử phải tạo ra tình huống chứa **chuỗi nhạy cảm giả** rồi quan sát đầu ra thật.

### 12.1. Ma trận kiểm thử

| Đường dữ liệu | Dữ liệu giả cần đưa vào | Kết quả phải xác minh |
|---|---|---|
| HTTP input | Password và token trong JSON/header | Response và application log không chứa giá trị |
| HTTP client upstream | Lỗi `401/500` với response body chứa token/email | Log chỉ có mã lỗi, status, correlation ID; response client an toàn |
| Validation | Giá trị bị từ chối là chuỗi nhạy cảm | Không có `rejectedValue`/raw input trong body/log |
| JDBC/MongoDB | Lỗi có dữ liệu nhạy cảm trong message | Không có raw exception/SQL bind/payload trong log |
| Spring Integration | `ErrorMessage` có failed message chứa secret | Error channel handler và log chỉ ghi error summary |
| Broker DLQ | Message thất bại có dữ liệu cá nhân | ACL, encryption/retention và header DLQ theo chính sách; log không dump payload |
| Trace/metrics | Header `Authorization` và URL có query `token=...` | Exporter không đưa giá trị vào span attributes hoặc labels |
| Cấu hình | Secret và datasource URL có password | Startup log, `/actuator/env`, `/actuator/configprops` không lộ giá trị |

### 12.2. Ví dụ kiểm thử response không lộ token

Trong Spring MVC với `MockMvc`, có thể assert nguyên body phản hồi không chứa marker bí mật của fixture:

```java
@Test
void doesNotExposeSecretsInPublicError() throws Exception {
    String marker = "SECRET_TEST_ONLY_9a8f7c";

    mockMvc.perform(post("/payments")
                    .contentType(MediaType.APPLICATION_JSON)
                    .header("Authorization", "Bearer " + marker)
                    .content("""
                        {"customerEmail":"test@example.invalid",
                         "cardToken":"SECRET_TEST_ONLY_9a8f7c"}
                        """))
            .andExpect(status().isBadRequest())
            .andExpect(content().string(not(containsString(marker))))
            .andExpect(content().string(
                    not(containsString("test@example.invalid"))
            ));
}
```

Ví dụ giả định endpoint có nhánh validation trả `400`; nếu nghiệp vụ dùng status khác thì phải điều chỉnh fixture và assertion theo hợp đồng thật. Các hàm `post`, `status`, `content` và Hamcrest matcher dùng static import trong test thực tế.

Kiểm thử tương tự với capture appender để đọc **dòng log đã được format thật**, kể cả throwable/cause đã được render; đừng chỉ kiểm tra message template trước khi encoder xử lý. Với log JSON, kiểm tra JSON đã ghi ra stream/collector thử nghiệm. Với trace, kiểm tra span được export, không chỉ object trong ứng dụng.

### 12.3. Kiểm tra log-injection và giới hạn độ dài

Ngoài bí mật, hãy đưa vào fixture các chuỗi có newline, ký tự điều khiển và nội dung giống log giả:

```text
username = "guest\nERROR authenticated_as_admin=true"
reason   = "\r\nAuthorization: Bearer SECRET_TEST_ONLY_9a8f7c"
```

Nếu thật sự phải ghi một trường từ input, cần mã hóa/escape theo định dạng log, cắt độ dài hợp lý và áp dụng kiểm soát dữ liệu nhạy cảm trước khi ghi. Không đưa các giá trị này vào tên metric/span attribute.

## 13. Khi phát hiện bí mật đã bị ghi ra log

Việc che log trong phiên bản mới chỉ ngăn phát tán tiếp, không vô hiệu hóa token đã lộ. Khi có bằng chứng credential hoặc dữ liệu cá nhân xuất hiện trong log:

1. **Chặn nguồn rò rỉ:** tắt cấu hình logging gây lộ hoặc triển khai thay đổi hạn chế trường ghi; có thể cần giảm quyền truy cập khẩn cấp.
2. **Xác định phạm vi:** loại dữ liệu, thời gian, hệ thống nhận log, index, exporter, dashboard, alert, backup và công cụ hỗ trợ đã sao chép nó.
3. **Thu hồi/luân chuyển credential:** revoke và rotate token, mật khẩu hoặc khóa bị lộ theo quy trình của hệ thống; kiểm tra tác động tới client đang dùng.
4. **Hạn chế truy cập và xử lý bản sao:** theo chính sách bảo mật và yêu cầu pháp lý hiện hành, xác định phương án xóa hoặc rút ngắn retention ở các bản sao có thể xử lý, đồng thời bảo toàn bằng chứng cần thiết cho điều tra.
5. **Phòng tái diễn:** bổ sung test marker giả, policy kiểm tra logging, cấu hình APM/Actuator và review ở các luồng integration tương tự.

Không đưa chính token bị lộ vào ticket, chat, báo cáo sự cố hoặc nội dung gửi hỗ trợ. Dùng mã sự cố và ID của kho bí mật để trao đổi; phân phối thông tin chi tiết qua kênh kiểm soát phù hợp.

## 14. Checklist trước khi triển khai

- [ ] Đã lập danh mục secret, PII và payload nghiệp vụ theo từng HTTP endpoint, database, cache, broker và integration adapter.
- [ ] Application log dùng allowlist; không in nguyên request, response, entity, message hoặc exception từ nguồn chưa tin cậy.
- [ ] DTO `toString()`, validation `rejectedValue` và custom logger/interceptor được xem xét.
- [ ] Các loại header `Authorization`, cookie, API key và credential riêng đã bị loại khỏi mọi request/response logging.
- [ ] HTTP error body có `code`/correlation ID ổn định, không trả raw exception, stack trace hoặc upstream body.
- [ ] Cấu hình error mặc định, Actuator, HTTP debug/wiretap và data bind logging đã được kiểm soát.
- [ ] Spring Integration error channel và DLQ không thêm payload/credential vào log hoặc error metadata ngoài chính sách.
- [ ] Trace/span attributes, baggage, metric labels, gateway và logging sidecar đã được rà soát.
- [ ] Có integration test với token/password/PII giả, kiểm tra log sau format, response và dữ liệu export.
- [ ] Có chính sách truy cập, retention, mã hóa và xử lý sự cố dành riêng cho log, trace, DLQ và bản sao lưu.
- [ ] Correlation ID được sinh/kiểm soát an toàn và hoạt động qua các ranh giới asynchronous cần thiết.
- [ ] Thông tin hỗ trợ điều tra vẫn còn: route/operation chuẩn hóa, status, error code, latency, retry count và trace ID.

**Ghi nhớ:** biện pháp hiệu quả nhất để che token, mật khẩu và dữ liệu cá nhân trong Spring Boot Integration là **không đưa chúng vào log hoặc thông điệp lỗi ngay từ đầu**. Ghi metadata chẩn đoán theo allowlist, chuẩn hóa lỗi, kiểm soát các kênh ngoài ứng dụng và kiểm thử dữ liệu đã được xuất thực tế sẽ giảm rủi ro rò rỉ mà vẫn cho phép điều tra luồng HTTP, database, cache và broker.

