# Mask request body trong Spring Boot observability

## 1. Mục tiêu và bối cảnh

Request body thường chứa dữ liệu nghiệp vụ mà đội phát triển cần xem khi debug: thông tin đăng ký, địa chỉ giao hàng, nội dung thanh toán, token hoặc dữ liệu người dùng gửi lên. Ghi toàn bộ body vào application logs, traces hay APM có thể biến telemetry thành một bản sao dữ liệu nhạy cảm, lan sang nhiều hệ thống và được giữ lâu hơn dữ liệu gốc.

**Mask request body** là quá trình loại bỏ hoặc thay thế các trường nhạy cảm trước khi body được ghi vào log/telemetry. Mục tiêu là giữ lại cấu trúc và metadata đủ để điều tra request, đồng thời không lưu giá trị bí mật hoặc thông tin cá nhân không cần thiết.

Bài thuộc chương **Security và privacy** của module **SPRING_BOOT_OBSERVABILITY**. Module hướng dẫn thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; học context propagation, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

Sau bài học, bạn có thể:
1. Xác định các đường đi khiến request body lọt vào logs, traces và APM.
2. Phân loại field nhạy cảm theo content type và schema.
3. Thiết kế allowlist và redaction mặc định an toàn.
4. Hiểu giới hạn của ContentCachingRequestWrapper và request body buffering.
5. Xử lý streaming, multipart và binary payload mà không làm hỏng request.
6. Tránh rò rỉ body qua exception, debug logs và observability agents.
7. Kiểm thử masking trên mọi telemetry sink bằng sentinel values.

**Baseline:** Spring Boot 3.5.x, Java 17+, Spring MVC/Servlet hoặc WebFlux. Ví dụ logging filter tập trung vào Servlet stack; WebFlux có DataBuffer/reactive lifecycle riêng.

## 2. Vì sao không nên log toàn bộ request body?

Body có thể chứa:
- Password, access token, refresh token, API key và session secrets.
- Email, số điện thoại, địa chỉ, ngày sinh và thông tin định danh.
- Payment details, account numbers hoặc dữ liệu giao dịch.
- Hồ sơ sức khỏe, thông tin nhân sự hoặc dữ liệu pháp lý.
- File upload, ảnh, tài liệu hoặc nội dung tự do do người dùng nhập.
- Dữ liệu nội bộ chưa được phân loại.

Rủi ro không chỉ nằm ở log file. Body có thể xuất hiện trong:

| Nguồn | Ví dụ |
| --- | --- |
| Servlet filter/interceptor | Log request/response payload |
| API gateway/reverse proxy | Request capture hoặc debug trace |
| APM agent | HTTP body capture và span attributes |
| Exception handler | Log DTO hoặc request body khi validation thất bại |
| Validation/debug code | In toàn bộ object hoặc binding errors |
| Audit pipeline | Copy request payload vào audit event |
| Test/support tooling | Wire logs, mock server recordings, support bundles |

Tắt một application logger không đảm bảo các agent, gateway hoặc sidecar khác ngừng capture. Cần kiểm tra toàn bộ telemetry path.

## 3. Nguyên tắc: không ghi body nếu không cần

Ưu tiên ghi metadata an toàn thay vì payload:
- HTTP method, route template và status.
- Content-Type, Content-Length nếu có.
- Request duration và outcome.
- Correlation ID/traceId theo policy.
- Operation name và validation error category.
- Một số field đã được allowlist và redact theo schema nếu có nhu cầu thực sự.

Nếu cần debug payload, dùng synthetic/anonymized data hoặc môi trường được kiểm soát. Đừng bật body logging toàn cục trong production chỉ để tái hiện một lỗi.

## 4. Thiết kế chính sách redaction

Chính sách nên theo **allowlist**: chỉ những field được phân loại an toàn mới được giữ. Field không biết, schema mới hoặc content type không hỗ trợ phải được redact toàn bộ hoặc bỏ qua body.

Ví dụ policy cho JSON:

| Field | Cách xử lý | Lý do |
| --- | --- | --- |
| password | `[REDACTED]` | Secret |
| accessToken / refreshToken | `[REDACTED]` | Credential |
| email | `[REDACTED]` hoặc bỏ field | PII |
| phone | `[REDACTED]` | PII |
| cardNumber | `[REDACTED]` | Payment data |
| amount | Giữ nếu được duyệt | Business value |
| currency | Giữ nếu được duyệt | Enum hữu hạn |
| requestType | Giữ nếu allowlist | Operation metadata |
| unknown field | Redact hoặc bỏ toàn body | Schema chưa phân loại |

Không dựa vào tên field duy nhất để quyết định an toàn. `metadata`, `value`, `data`, `notes` hoặc field lồng nhau có thể chứa secrets/PII. Cần policy theo endpoint/schema và recursive traversal.

### 4.1. Ví dụ body trước và sau

Request body đầu vào:

```json
{
  "requestType": "CREATE_ORDER",
  "email": "alice@example.test",
  "password": "SECRET_SENTINEL_91",
  "cardNumber": "4111111111111111",
  "amount": 125000,
  "currency": "VND"
}
```

Body được phép ghi sau redaction:

```json
{
  "requestType": "CREATE_ORDER",
  "email": "[REDACTED]",
  "password": "[REDACTED]",
  "cardNumber": "[REDACTED]",
  "amount": 125000,
  "currency": "VND"
}
```

Đây là ví dụ minh họa. Việc giữ amount/currency cũng cần được policy dữ liệu của tổ chức phê duyệt; giá trị giao dịch có thể là dữ liệu nhạy cảm trong một số domain.

## 5. Servlet stack: ContentCachingRequestWrapper

Trong Spring MVC, `ContentCachingRequestWrapper` có thể cache bytes khi downstream đọc request body để filter đọc lại sau đó. Wrapper không tự đọc toàn bộ body ngay khi được tạo và không tự redaction.

Ví dụ filter chỉ log metadata, không log raw body:

```java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import java.io.IOException;

@Component
public class RequestMetadataLoggingFilter extends OncePerRequestFilter {
    private static final Logger log =
            LoggerFactory.getLogger(RequestMetadataLoggingFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {
        long started = System.nanoTime();
        try {
            filterChain.doFilter(request, response);
        } finally {
            long durationMs = (System.nanoTime() - started) / 1_000_000;
            log.info("HTTP request completed method={} uri={} status={} durationMs={}",
                    request.getMethod(),
                    request.getRequestURI(),
                    response.getStatus(),
                    durationMs);
        }
    }
}
```

Ví dụ trên vẫn cần chuẩn hóa URI thành route template nếu path chứa identifiers. Không log query string mặc định vì query parameters cũng có thể chứa secrets hoặc PII.

### 5.1. Khi nào dùng ContentCachingRequestWrapper?

Chỉ dùng khi có use case cần inspect body sau khi ứng dụng đã đọc. Một số lưu ý:
- Cache limit phải hữu hạn để tránh memory exhaustion.
- Body chưa được downstream đọc có thể chưa xuất hiện đầy đủ trong cache.
- Multipart/file upload không nên bị copy vào memory để logging.
- Wrapper không parse JSON và không mask fields.
- Không log cached bytes trực tiếp; decode rồi redaction theo schema nếu thực sự cần.
- Cẩn thận charset, binary content, malformed payload và request quá lớn.

Nếu muốn đọc body trước downstream, cần wrapper hỗ trợ replay stream đúng cách. Đọc InputStream trong filter mà không thay thế/replay có thể khiến controller nhận body rỗng.

## 6. Ví dụ redaction JSON có giới hạn

Nếu policy cho phép ghi một số JSON request, có thể parse vào JSON tree, redaction theo allowlist/denylist đã được phê duyệt rồi serialize bản đã xử lý. Ví dụ với Jackson:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.util.Set;

public final class RequestBodyRedactor {
    private static final Set<String> SENSITIVE_FIELDS = Set.of(
            "password", "accessToken", "refreshToken",
            "email", "phone", "cardNumber"
    );

    private final ObjectMapper mapper;

    public RequestBodyRedactor(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public String redact(String json) {
        try {
            JsonNode root = mapper.readTree(json);
            redactNode(root);
            return mapper.writeValueAsString(root);
        } catch (Exception ex) {
            return "[BODY_OMITTED:UNPARSEABLE_OR_UNSUPPORTED]";
        }
    }

    private void redactNode(JsonNode node) {
        if (node instanceof ObjectNode object) {
            object.fieldNames().forEachRemaining(name -> {
                if (SENSITIVE_FIELDS.contains(name)) {
                    object.put(name, "[REDACTED]");
                } else {
                    redactNode(object.get(name));
                }
            });
        } else if (node.isArray()) {
            node.forEach(this::redactNode);
        }
    }
}
```

Đây là ví dụ khởi đầu, không phải redactor production hoàn chỉnh. Nó chỉ xử lý JSON object/array và danh sách field tĩnh; cần bổ sung policy cho nested schema, field aliases, case normalization, polymorphic payload và unknown fields. Nếu parse thất bại, ví dụ bỏ toàn body thay vì log raw input.

Đừng gọi redactor trên mọi request một cách tự động. Chỉ kích hoạt cho endpoint/content type được allowlist, giới hạn kích thước và đánh giá chi phí parse thêm lần nữa.

## 7. Content type, multipart và binary

Không phải request body nào cũng là JSON:

| Content-Type | Chính sách logging |
| --- | --- |
| application/json | Chỉ log bản đã redaction theo schema được duyệt |
| application/x-www-form-urlencoded | Redact từng field; token/password mặc định bỏ |
| multipart/form-data | Không log file bytes; chỉ log metadata đã duyệt |
| application/octet-stream | Bỏ body |
| image/*, audio/*, video/* | Bỏ body; không encode thành text log |
| text/plain | Mặc định bỏ hoặc áp dụng giới hạn/allowlist rõ ràng |
| application/*+json | Chỉ xử lý khi schema/content type được hỗ trợ |

Multipart filenames cũng có thể chứa thông tin cá nhân hoặc path do người dùng kiểm soát. Chỉ log file size, media type hoặc file count nếu cần và đã được duyệt; không log filename/path mặc định.

## 8. Response body và exception leakage

Response body cũng có thể chứa access token, reset link, personal data hoặc nội dung do downstream trả về. Nếu filter log cả request lẫn response, áp dụng policy riêng cho cả hai hướng.

Validation exception có thể chứa rejected value. Ví dụ binding error đôi khi giữ object/value đầu vào; không serialize toàn bộ BindingResult hoặc DTO vào log. Chỉ log field name và error code đã được kiểm soát, không log rejected value.

Không log toàn bộ request object trong controller/service bằng `toString()`. Generated `toString()` có thể bao gồm tất cả fields, nested objects hoặc secrets.

APM agent, gateway wiretap và HTTP client/server debug logging cũng có thể capture payload. Kiểm tra các cấu hình body capture và tắt hoặc redact tại nguồn trước khi gửi exporter.

## 9. WebFlux và streaming bodies

WebFlux dùng reactive streams và `DataBuffer`. Việc consume body để logging có thể ảnh hưởng backpressure, memory và lifecycle buffer.

Nguyên tắc:
- Không subscribe thêm lần nữa chỉ để log body.
- Không aggregate stream lớn thành một byte array chỉ để ghi log.
- Không block event loop để parse/redact payload.
- Nếu custom đọc DataBuffer, phải tuân thủ ownership/release semantics để tránh leak.
- Với streaming request, log metadata và event summaries thay vì toàn bộ nội dung.
- Context/trace propagation cần còn đúng khi xử lý chuyển scheduler.

Với reactive stack, ưu tiên WebFilter/ExchangeFilterFunction hoặc instrumentation có hỗ trợ body semantics. Không copy Servlet ContentCachingRequestWrapper pattern sang WebFlux.

## 10. Buffer size, performance và denial of service

Body logging có thể nhân đôi memory use: một bản cho request processing và một bản cache/serialized log. Với payload lớn hoặc request đồng thời cao, điều này có thể tạo heap pressure, GC pause và DoS vector.

Thiết kế cần:
- Giới hạn maximum body bytes được inspect.
- Không cache file upload hoặc streaming payload.
- Dùng timeout và giới hạn kích thước tại server/container.
- Không parse cùng JSON nhiều lần nếu không cần.
- Sampling chỉ dùng cho dữ liệu đã được redact và không áp dụng để hợp thức hóa việc ghi secrets.
- Đo overhead của filter/redactor bằng load test.

Nếu vượt giới hạn, bỏ toàn body hoặc ghi marker như BODY_OMITTED_TOO_LARGE; không cắt ngẫu nhiên JSON rồi log một phần có thể chứa secret.

## 11. Kiểm thử masking bằng sentinel values

Dùng giá trị giả có thể nhận diện để kiểm tra rò rỉ:
- Email: `mask-user-731@example.test`.
- Token: `BODY_SECRET_SENTINEL_42`.
- Phone: `+84981234567`.
- Card-like test value: `4111111111111111` (chỉ dùng dữ liệu test).

Test matrix:
1. JSON hợp lệ có nested sensitive fields: raw values không xuất hiện trong logs.
2. JSON malformed: body được bỏ qua, không fallback sang raw logging.
3. JSON vượt size limit: body bị bỏ và marker được ghi.
4. Form-urlencoded: password/token được redact.
5. Multipart: file bytes và filename không bị log.
6. Binary/streaming: body không bị consume hoặc buffer để logging.
7. Validation error: rejected value không xuất hiện trong exception logs.
8. Response body: token/reset link không xuất hiện.
9. APM/exporter/gateway: sentinel không xuất hiện ở bất kỳ sink nào.
10. Concurrent requests: wrapper/cache/context không trộn body giữa request.

Ví dụ assertion:

```java
assertThat(capturedTelemetry)
        .doesNotContain("mask-user-731@example.test")
        .doesNotContain("BODY_SECRET_SENTINEL_42")
        .doesNotContain("+84981234567")
        .doesNotContain("4111111111111111");
```

Chỉ kiểm tra một appender là chưa đủ nếu ứng dụng còn stdout collector, tracing exporter, APM agent hoặc gateway logging.

## 12. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Log vẫn có password sau khi bật filter | Agent/gateway/appender khác capture body | Kiểm tra toàn bộ telemetry path |
| Controller nhận body rỗng | Filter đã consume InputStream mà không replay | Dùng wrapper replay đúng cách hoặc không đọc trước |
| Body cache rỗng | Downstream chưa đọc body hoặc wrapper đặt sai thứ tự | Kiểm tra filter order và lifecycle |
| Heap tăng sau bật body logging | Cache body lớn hoặc concurrency cao | Giới hạn bytes, bỏ upload/streaming |
| JSON nested field không được mask | Redactor chỉ xử lý root hoặc schema chưa đầy đủ | Recursive traversal và test nested payload |
| JSON parse lỗi làm raw body xuất hiện | Fallback log raw input | Fail closed: bỏ body khi parse không hỗ trợ |
| Multipart log chứa filename | File metadata chưa được phân loại | Bỏ filename/path, chỉ giữ metadata allowlist |
| WebFlux DataBuffer leak | Custom filter không release buffer đúng | Tuân thủ buffer ownership/lifecycle |
| Validation log lộ rejected value | Log toàn bộ BindingResult/DTO | Chỉ log field/error code an toàn |
| Response token xuất hiện trong trace | Response body capture ở APM/client | Tắt body capture hoặc redact trước export |
| Request latency tăng | Parse/serialize thêm lần nữa | Log metadata; benchmark redactor và giới hạn scope |

## 13. Checklist production

- [ ] Không log request/response body mặc định.
- [ ] Endpoint/content type được allowlist rõ nếu cần body diagnostics.
- [ ] Unknown fields và parse failures mặc định bị bỏ/redact.
- [ ] Password, token, payment data và PII không xuất hiện trong telemetry.
- [ ] ContentCachingRequestWrapper có giới hạn; không consume body ngoài ý muốn.
- [ ] Multipart, binary và streaming bodies không bị buffer/log.
- [ ] WebFlux xử lý DataBuffer và backpressure đúng lifecycle.
- [ ] Exception/validation errors không log rejected values hoặc DTO.toString().
- [ ] APM agents, gateways, appenders và exporters đã được kiểm tra.
- [ ] Body size limit và load test bảo vệ memory/CPU.
- [ ] Sentinel tests xác nhận không rò rỉ qua tất cả sinks.
- [ ] Retention/access controls và incident response được xác định.

## 14. Câu hỏi tự luyện

1. Vì sao request body logging có thể tạo data exposure?
2. Tại sao allowlist thường an toàn hơn blocklist?
3. ContentCachingRequestWrapper có tự đọc và mask body không?
4. Điều gì xảy ra nếu filter đọc InputStream nhưng không replay?
5. Vì sao JSON parse failure phải fail closed?
6. Multipart và binary payload cần policy gì?
7. Tại sao không nên aggregate Flux/DataBuffer lớn chỉ để log?
8. Validation exception có thể làm lộ rejected value như thế nào?
9. APM agent và gateway có thể bypass application masking ra sao?
10. Sentinel test cần kiểm tra những telemetry sinks nào?
11. Vì sao body size limit là một biện pháp bảo vệ availability?
12. Khi nào metadata là đủ thay cho request body?

## Tài liệu tham khảo

- [Spring Framework — Logging](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/filters.html)
- [Spring Framework — ContentCachingRequestWrapper](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/util/ContentCachingRequestWrapper.html)
- [Spring Framework — WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html)
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP — Logging Vocabulary Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Vocabulary_Cheat_Sheet.html)
- [OWASP — REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
- [OpenTelemetry — HTTP Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/http/)

