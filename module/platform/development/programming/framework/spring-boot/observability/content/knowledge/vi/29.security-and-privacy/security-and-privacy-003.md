# Không log access token trong Spring Boot

Access token là credential dạng bearer: bên nào sở hữu token có thể sử dụng nó trong phạm vi quyền và thời hạn được cấp. Nếu token xuất hiện trong application logs, access logs, exception messages, traces hoặc telemetry export, người đọc log có thể dùng token để giả mạo client cho tới khi token hết hạn hoặc bị thu hồi. Logs thường được sao chép sang nhiều hệ thống, giữ lâu và cấp quyền cho nhiều nhóm, vì vậy một lần ghi nhầm có thể mở rộng phạm vi lộ lọt đáng kể.

Bài **Không log access token** thuộc chương **Security và privacy** của module **SPRING_BOOT_OBSERVABILITY**. Module hướng dẫn thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; học context propagation, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

Sau bài học, bạn có thể nhận diện nơi token dễ bị ghi vào telemetry, thiết kế logging theo allowlist, lọc thông tin nhạy cảm ở nguồn, áp dụng redaction nhiều lớp, kiểm soát MDC/trace attributes và kiểm thử để chứng minh token giả không xuất hiện trong log output.

## 1. Vì sao access token không được xuất hiện trong logs?

Bearer token là thông tin xác thực. Với OAuth 2.0, access token được gửi trong HTTP Authorization header theo dạng Bearer. Người có token có thể gọi resource server như client đã được cấp token, tùy scopes, audience, expiry và server policy.

Token có thể bị lộ qua:

- Application logs ghi toàn bộ request headers.
- Reverse proxy, gateway hoặc web server access logs.
- Debug logs của HTTP client/server.
- Exception message chứa request/response headers.
- Log request body, query parameters hoặc URL có token.
- MDC, structured logging fields hoặc custom trace/span attributes.
- APM agent, tracing exporter, support bundle và crash diagnostics.
- CI output, test reports, terminal history hoặc screenshots.

Không dựa vào việc token có thời hạn ngắn để xem nhẹ rủi ro. Trong khoảng thời gian còn hiệu lực, token vẫn có thể bị dùng lại; refresh token hoặc client secret bị log nhầm còn có thể tạo rủi ro dài hơn.

## 2. Các vị trí nhạy cảm trong HTTP request

| Vị trí | Ví dụ | Quy tắc logging |
| --- | --- | --- |
| Authorization header | Bearer access token | Không log giá trị |
| Cookie | Session/access token | Không log giá trị cookie |
| Query parameter | access_token=... | Không đặt token trong URL; lọc nếu legacy system buộc phải nhận |
| Request body | JSON có token hoặc credential | Không log body mặc định |
| Response body | Token được cấp mới | Không log body mặc định |
| Exception | Client exception chứa headers | Không log nguyên văn nếu có thể chứa credential |
| MDC/context | token, authorization, credential | Không đưa token vào context fields |
| Trace attributes | http.request.header.authorization | Không capture secret headers |

Ví dụ request hợp lệ thường dùng:

```http
GET /api/orders HTTP/1.1
Host: orders.example.internal
Authorization: Bearer <access-token>
Accept: application/json
```

Giá trị Authorization chỉ phục vụ authentication giữa client và resource server. Nó không phải thông tin cần thiết để hiểu request đã xử lý ra sao.

Không truyền access token trong URL. URL có thể xuất hiện trong browser history, proxy logs, referrer headers, analytics và monitoring. Nếu hệ thống legacy buộc dùng query parameter, cần lập kế hoạch loại bỏ và redaction chính xác trước khi ghi request target.

## 3. Logging theo allowlist thay vì ghi toàn bộ request

Một quy tắc an toàn là chỉ ghi những field cần thiết để vận hành:

| Field | Có thể log? | Ghi chú |
| --- | --- | --- |
| HTTP method | Có | Tập giá trị hữu hạn |
| Route template | Có | Dùng template, không dùng raw URI có ID |
| Response status | Có | Không chứa credential |
| Duration | Có | Đơn vị rõ ràng |
| Service name | Có | Giá trị ổn định |
| Trace ID/span ID | Có điều kiện | Theo correlation policy, không dùng làm metric tags |
| Authorization | Không | Luôn loại khỏi logs |
| Cookie/Set-Cookie | Không | Có thể chứa session/token |
| Request/response body | Mặc định không | Chỉ log cấu trúc đã lọc nếu có yêu cầu rõ |
| Password/client secret/API key | Không | Credential |
| Raw query string | Tránh | Có thể chứa token, PII hoặc dữ liệu nghiệp vụ |

Structured logging giúp chọn field cụ thể thay vì serialize cả request object:

```json
{
  "event": "http.server.request.completed",
  "service.name": "orders-service",
  "http.request.method": "GET",
  "http.route": "/api/orders",
  "http.response.status_code": 200,
  "event.duration_ms": 42,
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
}
```

Ví dụ này chỉ chứa metadata vận hành. Không thêm authorization, cookie, raw payload hoặc token vào cùng event.

## 4. Đừng log toàn bộ headers

Các HTTP headers có giá trị vận hành khác nhau. Logging toàn bộ headers thường tạo rủi ro lớn hơn lợi ích. Thay vào đó, chọn một allowlist nhỏ:

```java
import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;

final class SafeRequestFields {
    private SafeRequestFields() {}

    static Map<String, String> from(HttpServletRequest request) {
        return Map.of(
            "method", request.getMethod(),
            "route", safeRoute(request),
            "requestId", safeRequestId(request)
        );
    }

    private static String safeRoute(HttpServletRequest request) {
        // Use a route template supplied by handler mapping in real code.
        return request.getRequestURI();
    }

    private static String safeRequestId(HttpServletRequest request) {
        // Validate length and allowed characters before logging.
        String value = request.getHeader("X-Request-Id");
        if (value == null || !value.matches("[A-Za-z0-9_-]{1,64}")) {
            return "unavailable";
        }
        return value;
    }
}
```

Đây là ví dụ minh họa allowlist, không phải implementation route resolver hoàn chỉnh. Trong ứng dụng thực, lấy route template từ handler mapping sau khi mapping hoàn tất; raw URI có thể chứa identifiers. Request ID do client cung cấp phải được giới hạn độ dài và ký tự để tránh log injection.

Không dùng đoạn code kiểu request.getHeaderNames() rồi ghi mọi cặp name/value. Header names có thể bị viết hoa/thường khác nhau; denylist chỉ kiểm tra một cách viết có thể bỏ sót biến thể.

## 5. Redaction là lớp bảo vệ bổ sung

Nếu một thành phần legacy hoặc framework vẫn ghi headers, cần redaction tại logging pipeline. Ví dụ cấu hình logging có thể che các field đã biết:

```text
Authorization: Bearer [REDACTED]
Cookie: [REDACTED]
Set-Cookie: [REDACTED]
```

Redaction cần:

- Không phân biệt hoa/thường đối với header names.
- Nhận diện Bearer scheme với khoảng trắng/format hợp lệ.
- Che toàn bộ cookie values, không chỉ cookie tên phổ biến.
- Xử lý JSON/form fields có tên nhạy cảm theo schema đã biết.
- Không làm hỏng nội dung log khiến điều tra không thể thực hiện.
- Có test với nhiều biến thể tên field và token format.

Redaction regex trên toàn bộ dòng log không phải giải pháp duy nhất. Structured fields có thể được lọc trước khi serialize; đây thường là điểm kiểm soát rõ ràng hơn. Redaction ở collector/backend chỉ là lớp phòng vệ cuối, vì dữ liệu nhạy cảm đã rời process trước khi được che.

## 6. Spring Security: xác thực token mà không log token

Spring Security Resource Server có thể xác thực Bearer token qua filter chain và JwtDecoder hoặc opaque token introspection. Business controller thường chỉ cần principal/claims đã được xác minh, không cần token thô.

Ví dụ controller dùng principal:

```java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProfileController {
    @GetMapping("/api/profile")
    ProfileView profile(@AuthenticationPrincipal Jwt jwt) {
        return new ProfileView(
            jwt.getSubject(),
            jwt.getClaimAsString("tenant")
        );
    }
}
```

Ví dụ cho thấy controller sử dụng claims cần thiết sau khi token được xác thực. Không gọi jwt.getTokenValue() để ghi log. Claims cũng có thể chứa PII hoặc dữ liệu nhạy cảm; chỉ sử dụng và log các claim đã được phê duyệt.

Không log toàn bộ Authentication object, SecurityContext hoặc Jwt object bằng toString(). Object có thể chứa token credentials, authorities, claims và principal details.

## 7. Filter/interceptor và access logging

Một servlet filter có thể ghi request completion metadata. Hãy thiết kế nó theo allowlist và không đọc/serialize headers tùy tiện:

```java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.filter.OncePerRequestFilter;

class SafeAccessLogFilter extends OncePerRequestFilter {
    private static final Logger log =
        LoggerFactory.getLogger(SafeAccessLogFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {
        long start = System.nanoTime();
        try {
            chain.doFilter(request, response);
        } finally {
            long elapsedMs =
                (System.nanoTime() - start) / 1_000_000;
            log.info("http_request method={} status={} duration_ms={}",
                request.getMethod(),
                response.getStatus(),
                elapsedMs);
        }
    }
}
```

Đây là filter tối giản minh họa metadata an toàn. Production access logging nên lấy route template phù hợp, phân biệt async dispatch, tránh log một request nhiều lần và phối hợp với server/container access log hiện có. Nếu framework đã tạo access event, không thêm filter chỉ để ghi lại cùng thông tin.

## 8. Exception và HTTP client logs

HTTP client exceptions đôi khi chứa request URL, headers hoặc response body. Các thư viện HTTP có thể ghi chi tiết request khi bật wire logging hoặc DEBUG logging.

Tránh:

- Bật wire logging toàn bộ request/response trong production.
- Log exception object có message chứa Authorization header.
- Ghi request configuration object hoặc client request object trực tiếp.
- Log curl command được dựng từ request có bearer token.

Thay vào đó, log exception class, error category, status code, destination service và trace correlation. Nếu cần debug giao thức, dùng môi trường test với token giả, payload giả và thời gian bật logging giới hạn.

## 9. MDC, tracing và baggage

MDC hữu ích để gắn correlation fields như trace ID vào log. Tuy nhiên, không đưa access token vào MDC. MDC có thể được copy qua thread pool, async executor hoặc reactive context và tồn tại lâu hơn dự kiến nếu cleanup không đúng.

Không làm các việc sau:

- MDC.put("access_token", token).
- Baggage chứa token để propagate giữa services.
- Span attribute chứa Authorization/Cookie header.
- Metric tag chứa token hoặc hash token.
- Log trace context object có custom fields nhạy cảm.

Trace ID không phải credential và thường hữu ích để nối log với trace. Token là credential và phải luôn được loại khỏi telemetry. Không hash token để log thay cho redaction: hash ổn định vẫn tạo định danh nhạy cảm, có thể hỗ trợ correlation trái phép hoặc tấn công từ điển trong một số hệ thống.

## 10. Reverse proxy, gateway và container access logs

Ứng dụng có thể không log Authorization nhưng gateway, ingress, service mesh hoặc servlet container lại ghi request headers. Kiểm tra toàn bộ đường đi:

1. Load balancer / ingress access logs.
2. API gateway request/response logging.
3. Service mesh proxy access logs.
4. Servlet container access log valves.
5. Spring application logging.
6. HTTP client wire logging.
7. APM agent và telemetry collector.

Mỗi lớp có cấu hình riêng. Một policy chỉ áp dụng trong Logback/Log4j không thể ngăn gateway ghi header. Cần tắt header capture hoặc đặt explicit exclude/redact ở từng lớp có khả năng log request.

## 11. Kiểm thử để phát hiện token bị log

Một test quan trọng là tạo token giả có marker duy nhất rồi xác minh marker không xuất hiện trong bất kỳ log event nào:

```java
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class AccessTokenLoggingTest {
    @Test
    void accessTokenNeverAppearsInCapturedLogs() {
        String sentinel = "test-access-token-DO-NOT-LOG-7f31";

        // Arrange a test request with:
        // Authorization: Bearer <sentinel>
        // Capture application and access-log output.
        // Invoke the secured endpoint.
        // Assert the sentinel is absent from every captured event.
        assertThat(capturedLogs()).doesNotContain(sentinel);
    }

    private String capturedLogs() {
        // Replace with the test appender / log capture implementation.
        return "";
    }
}
```

Đây là skeleton test, cần nối với test appender hoặc log capture của dự án. Test hoàn chỉnh nên kiểm tra cả:

- Application logs và access logs.
- HTTP client/server debug output nếu được bật trong test.
- Exception paths (401, 403, 5xx, timeout).
- Header names viết hoa/thường.
- Cookie và query parameter legacy.
- Structured JSON fields và MDC.
- Trace/span attributes được export trong in-memory exporter.

Không dùng token production thật làm test fixture. Dùng sentinel giả có thể tìm kiếm chính xác và rotate/xóa dữ liệu test sau khi hoàn tất.

## 12. Logging policy và cấu hình vận hành

Một logging policy rõ ràng nên quy định:

| Nhóm dữ liệu | Policy |
| --- | --- |
| Credentials | Không log |
| Authorization/Cookie headers | Không capture hoặc redact tại nguồn |
| PII | Chỉ log field được phê duyệt, giảm thiểu và giới hạn retention |
| Request/response bodies | Tắt mặc định; chỉ dùng sanitized schema trong môi trường phù hợp |
| Correlation IDs | Được phép theo format/length policy |
| Route/method/status/duration | Được phép theo allowlist |
| Exception | Log class/category và stack trace theo policy; loại secret khỏi message |
| Debug/wire logging | Chỉ bật có kiểm soát, token giả, thời gian ngắn |

Ngoài code, cần kiểm soát quyền đọc log, retention, encryption at rest/in transit, export destinations và audit truy cập. Nếu token đã lọt vào log, việc xóa một dòng trong ứng dụng không xóa các bản sao ở collector, index, archive, backup và downstream SIEM.

## 13. Xử lý khi access token đã bị log

Nếu phát hiện token thật trong logs, xử lý như credential exposure:

1. Xác định token loại nào, issuer, audience, scope, expiry và phạm vi hệ thống chứa log.
2. Hạn chế quyền truy cập log/index liên quan và ngăn tiếp tục ingest dữ liệu nhạy cảm.
3. Revoke/invalidate token nếu cơ chế cấp phát hỗ trợ; cân nhắc thu hồi session/refresh token liên quan theo incident policy.
4. Tìm các bản sao trong application logs, proxy, collector, SIEM, archive, backup và ticket attachments.
5. Xóa hoặc redact theo quy trình retention/legal hold của tổ chức; ghi lại phạm vi xử lý.
6. Kiểm tra access audit để xác định có truy cập bất thường vào logs hay không.
7. Sửa logging source và thêm regression tests trước khi mở lại luồng ingest.

Không chỉ dựa vào expiry nếu token còn hiệu lực. Nếu token không thể revoke độc lập, phối hợp issuer/security team để đánh giá biện pháp vô hiệu hóa phù hợp.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Token xuất hiện trong access log | Proxy/container ghi toàn bộ headers | Tắt header capture hoặc cấu hình redact tại proxy |
| Token nằm trong exception message | HTTP client exception serialize request | Log error category/status, không log raw request |
| Token xuất hiện trong MDC | Middleware copy credentials vào context | Xóa field, allowlist MDC keys |
| Redaction bỏ sót Authorization | So khớp header name phân biệt hoa/thường | Normalize header names trước khi lọc |
| Token trong trace backend | Header capture hoặc custom span attribute | Exclude secret headers và kiểm tra exporter payload |
| Token trong URL | Legacy query parameter hoặc curl log | Loại token khỏi URL và redact request target |
| Token trong JSON body log | Request/response body logging | Tắt body logging hoặc dùng schema sanitized |
| Token hash xuất hiện trong metrics | Hash token được dùng làm tag | Xóa tag; không dùng token-derived identifiers |
| Log vẫn còn sau khi sửa app | Collector/index/archive đã lưu bản cũ | Thực hiện incident cleanup toàn bộ copies |
| Test không phát hiện rò rỉ | Chỉ capture một appender hoặc một status path | Mở rộng test qua proxy, exception và trace output |

## 15. Tình huống thực tế: Authorization header xuất hiện trong DEBUG logs

**Bối cảnh giả định:** Một service bật DEBUG cho HTTP client để điều tra lỗi gọi payment provider. Log collector ghi lại request headers và một dòng chứa Authorization Bearer token.

Quy trình:

1. **Ngăn phát sinh mới:** tắt wire/header logging hoặc chuyển logger về mức an toàn.
2. **Xác định phạm vi:** tìm token marker trong app logs, container logs, collector, index và archive.
3. **Thu hồi credential:** revoke token nếu hỗ trợ và đánh giá refresh/session credentials liên quan.
4. **Giới hạn truy cập:** khóa quyền đọc log index, audit access và phối hợp security response.
5. **Sửa nguồn:** cấu hình client logger không capture Authorization/Cookie; dùng allowlist metadata.
6. **Kiểm thử:** gửi request test với sentinel token, xác minh không xuất hiện trong appender, proxy logs và trace exporter.
7. **Phòng ngừa:** policy cấm log credentials, automated secret scanning và review cấu hình DEBUG trước production.

Việc token xuất hiện trong log là sự cố credential exposure ngay cả khi chưa có bằng chứng bị sử dụng. Xử lý dựa trên khả năng truy cập dữ liệu và thời hạn hiệu lực, không chờ phát hiện hành vi lạm dụng.

## 16. Bài tập tự kiểm tra

**Bài 1.** Vì sao Bearer access token được xem là secret?

*Gợi ý:* Người sở hữu token có thể dùng nó để truy cập resource trong phạm vi quyền được cấp.

**Bài 2.** Có nên log toàn bộ request headers để debug HTTP 401 không?

*Gợi ý:* Không. Log method, route, status, client category và trace correlation; loại Authorization/Cookie.

**Bài 3.** Vì sao redaction chỉ ở log collector chưa đủ?

*Gợi ý:* Token đã rời process và có thể được lưu trong buffer, transport hoặc hệ thống trung gian trước khi redact.

**Bài 4.** Có nên lưu hash của access token trong MDC để correlation?

*Gợi ý:* Không. Hash token vẫn là identifier nhạy cảm; dùng trace ID hoặc request ID riêng.

**Bài 5.** Controller có nên log toàn bộ Jwt object?

*Gợi ý:* Không. Object có thể chứa raw token và claims nhạy cảm; chỉ dùng/log claim đã được allowlist.

**Bài 6.** Vì sao cần kiểm tra cả gateway và servlet container logs?

*Gợi ý:* Mỗi tầng có logging config riêng; sửa application logger không ngăn proxy capture headers.

**Bài 7.** Làm sao kiểm thử token không xuất hiện trong logs?

*Gợi ý:* Gửi sentinel token giả, capture mọi log outputs và trace attributes, assert marker không xuất hiện.

**Bài 8.** Nếu token thật đã bị log, cần làm gì?

*Gợi ý:* Hạn chế log access, revoke token, tìm và xử lý mọi bản sao, audit truy cập và thêm regression tests.

## 17. Ghi nhớ

- Access token là credential dạng bearer; không ghi raw token vào application logs, access logs, traces, metrics, MDC hoặc baggage.
- Dùng **allowlist** cho structured logging; ưu tiên method, route template, status, duration và correlation ID đã validate.
- Không log toàn bộ HTTP headers, cookies, query strings, request/response bodies, SecurityContext hoặc Jwt object.
- Redaction là defense-in-depth; lọc dữ liệu nhạy cảm ngay tại nguồn trước khi serialize/export.
- Kiểm tra mọi tầng có thể ghi request: gateway, ingress, service mesh, servlet container, HTTP client, APM agent và collector.
- Không hash token để thay thế redaction và không đưa token-derived values vào metric tags.
- Dùng sentinel token giả trong automated tests để xác minh không rò rỉ qua success/error paths, structured logs và trace exporters.
- Nếu token thật đã lọt vào logs, xử lý như credential exposure: hạn chế truy cập, revoke, tìm mọi bản sao, audit và sửa nguồn phát sinh.
