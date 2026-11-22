# Log, trace tương quan và che token, secrets, claims nhạy cảm

## 1. Vì sao logging và tracing cần được thiết kế cùng bảo mật?

Một Resource Server thường nằm giữa nhiều thành phần: API Gateway, ứng dụng khách, Authorization Server, các service nội bộ và cơ sở dữ liệu. Khi request thất bại, nhóm vận hành cần biết request đã đi qua đâu, mất bao lâu, bị từ chối ở bước nào và lỗi đến từ service nào.

Nhưng log và trace cũng là nơi dễ làm lộ credential. Một dòng log chứa Authorization header, refresh token, client secret hoặc toàn bộ JWT claims có thể biến hệ thống quan sát thành một kho dữ liệu nhạy cảm. Người có quyền đọc log đôi khi nhiều hơn người có quyền truy cập token production.

Mục tiêu của bài này là tạo đủ ngữ cảnh để điều tra sự cố mà không lưu credential hoặc dữ liệu cá nhân không cần thiết:

- Tương quan log và trace qua request bằng request ID, trace ID và span ID.
- Ghi sự kiện authentication/authorization theo dạng có cấu trúc.
- Chỉ ghi các trường đã được cho phép, thay vì dump request, Authentication hoặc JWT.
- Che hoặc loại bỏ token, secrets, cookies và claims nhạy cảm ở mọi lớp ghi log.
- Truyền trace context qua các service mà không đưa credential vào baggage.
- Kiểm tra bằng test rằng log không chứa giá trị bí mật.

## 2. Phân biệt request ID, trace ID và span ID

Ba định danh này có liên quan nhưng không thay thế cho nhau.

| Định danh | Phạm vi | Dùng để |
| --- | --- | --- |
| Request ID | Một request hoặc transaction nghiệp vụ theo quy ước của ứng dụng | Tìm toàn bộ log gắn với request. |
| Trace ID | Một distributed trace, có thể đi qua nhiều service | Gom các span của một hành trình request. |
| Span ID | Một operation cụ thể bên trong trace | Xác định service/operation tạo ra log hoặc latency. |

Ví dụ:

```text
Browser
  │ request.id = req-7f2a
  │ trace.id   = 4bf92f3577b34da6a3ce929d0e0e4736
  ▼
API Gateway
  │ span.id = 00f067aa0ba902b7
  ▼
Orders API
  │ span.id = 7a085853722dc6d2
  ▼
Inventory API
  │ span.id = 2e4b8c1a7f90d311
  ▼
Database
```

Một trace có thể có nhiều span. Mỗi service ghi log với trace ID chung và span ID của operation hiện tại. Request ID có thể được giữ xuyên suốt hoặc được tạo lại ở từng boundary tùy quy ước, nhưng phải có mapping rõ ràng.

### 2.1. Request ID không phải credential

Request ID chỉ là mã tương quan. Nó không chứng minh danh tính người dùng, không cấp quyền và không được dùng làm session ID hoặc bearer credential.

Nếu nhận header X-Request-ID từ caller:

- Xem nó là dữ liệu đầu vào không tin cậy.
- Giới hạn độ dài và bộ ký tự.
- Không cho phép newline/control characters.
- Có thể thay bằng ID do hệ thống sinh nếu giá trị không hợp lệ.
- Không dùng nó làm khóa authorization, cache quyền hoặc idempotency token nếu chưa có contract riêng.

Với request từ Internet, tổ chức có thể chọn luôn sinh request ID nội bộ và lưu ID từ gateway trong một trường riêng đã kiểm tra.

### 2.2. Trace ID không phải bằng chứng xác thực

W3C Trace Context định nghĩa traceparent và tracestate để truyền thông tin trace giữa các process. Chúng phục vụ observability, không phải identity protocol.

Không dùng trace ID, span ID hoặc baggage để quyết định:

- Người dùng có quyền truy cập tài nguyên không.
- Service gọi có được tin cậy không.
- Token có hợp lệ không.
- Tenant hoặc subject là ai.

Authorization vẫn dựa trên Authentication và policy đã xác minh.

## 3. Tạo request ID và quản lý MDC trong Servlet

Với Spring MVC/Servlet, OncePerRequestFilter có thể tạo hoặc xác thực request ID rồi đặt nó vào SLF4J MDC. MDC cho phép logger tự thêm trường tương quan vào các log trong cùng thread.

Ví dụ:

```java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;

@Component
public class RequestIdFilter extends OncePerRequestFilter {

    private static final String HEADER = "X-Request-ID";
    private static final String MDC_KEY = "requestId";
    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9._-]{1,64}");

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        String supplied = request.getHeader(HEADER);
        String requestId = isSafe(supplied)
                ? supplied
                : UUID.randomUUID().toString();

        String previous = MDC.get(MDC_KEY);
        MDC.put(MDC_KEY, requestId);
        response.setHeader(HEADER, requestId);

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

    private boolean isSafe(String value) {
        return value != null && SAFE_ID.matcher(value).matches();
    }
}
```

Khối finally là bắt buộc. Servlet container thường tái sử dụng thread; nếu không xóa hoặc khôi phục MDC, request tiếp theo có thể ghi log bằng request ID của request trước.

### 3.1. Đặt filter đúng một lần

Nếu filter được khai báo là Spring bean Filter và đồng thời thêm thủ công vào SecurityFilterChain, nó có thể chạy hai lần do cả servlet container và security chain cùng đăng ký.

Chọn một cơ chế đăng ký:

- Đăng ký ở servlet container để request ID có mặt cả trước security chain.
- Hoặc đăng ký trong SecurityFilterChain tại vị trí đã xác định.

Đừng vừa để auto-registration vừa add filter vào chain mà không disable registration còn lại.

### 3.2. Chỉ phản hồi lại ID đã được kiểm tra

Header response giúp caller và đội vận hành tham chiếu cùng một request ID. Chỉ đưa giá trị đã được kiểm tra vào response. Nếu cần giữ cả ID do gateway cung cấp và ID nội bộ, dùng hai trường riêng, ví dụ requestId và upstreamRequestId.

Không đưa nội dung header tùy ý vào MDC hoặc response mà không giới hạn ký tự/độ dài.

## 4. Dùng Micrometer Tracing và W3C Trace Context

Trong Spring Boot có Micrometer Observation/Tracing, ứng dụng có thể tích hợp tracer và exporter (ví dụ OpenTelemetry hoặc Brave) để tạo trace/span và truyền trace context qua các client đã được instrument.

Khi dùng tracing bridge phù hợp, trace ID và span ID thường được đưa vào MDC theo cấu hình logging của ứng dụng. Log pattern có thể tham chiếu các trường traceId và spanId; tên key chính xác phụ thuộc bridge và cấu hình.

Ví dụ Logback pattern minh họa:

```xml
<pattern>
  %d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX}
  %-5level
  [%thread]
  [requestId=%X{requestId}]
  [traceId=%X{traceId}]
  [spanId=%X{spanId}]
  %logger{36} - %msg%n
</pattern>
```

Đây là pattern minh họa. Kiểm tra key MDC được bridge thực tế sử dụng trước khi cấu hình.

### 4.1. Truyền trace context qua HTTP client

Khi HTTP client được instrument bởi Micrometer Observation/Tracing, trace context W3C có thể được inject vào outbound request. Ở service đích, instrumentation extract context và tạo child span.

```text
Orders API
  trace.id = 4bf92f3577b34da6a3ce929d0e0e4736
  span.id  = 7a085853722dc6d2
       │
       │ traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-7a085853722dc6d2-01
       ▼
Inventory API
  trace.id = 4bf92f3577b34da6a3ce929d0e0e4736
  span.id  = 2e4b8c1a7f90d311
```

Header traceparent chứa version, trace ID, parent span ID và trace flags. Nó không chứa access token. Tuy nhiên, đừng tự thêm token, email, subject hoặc dữ liệu nhạy cảm vào tracestate/baggage.

### 4.2. Trace flags không phải security policy

Trace flags có thể ảnh hưởng việc lấy mẫu trace (sampling). Không dùng flag do caller gửi để quyết định quyền truy cập hoặc mức tin cậy. Sampler nên được cấu hình theo chính sách observability của hệ thống.

### 4.3. Không tạo trace context thủ công nếu đã có instrumentation

Tự tạo header traceparent bằng chuỗi ngẫu nhiên ở mỗi service sẽ làm đứt distributed trace. Dùng tracer/instrumentation để tạo trace mới khi chưa có context, tiếp tục trace khi context hợp lệ được truyền tới, tạo span con cho outbound call và inject/extract theo chuẩn.

Nếu gateway biên nhận trace context từ bên ngoài, cân nhắc trust boundary và sampling policy; trace context vẫn không được coi là thông tin xác thực.

## 5. Log có cấu trúc: ghi sự kiện, không dump object

Log có cấu trúc giúp truy vấn theo trường ổn định thay vì parse câu văn tự do. Một authentication event có thể có dạng:

```json
{
  "timestamp": "2026-11-15T10:00:00.000Z",
  "level": "INFO",
  "event": "resource_server.authentication",
  "service": "orders-api",
  "requestId": "req-7f2a",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "7a085853722dc6d2",
  "authOutcome": "success",
  "authMethod": "bearer",
  "issuerId": "internal-oidc",
  "resource": "orders-api"
}
```

Event này đủ để tìm request và biết authentication thành công ở API nào. Nó không cần lưu raw JWT, toàn bộ claims, Authorization header hoặc Authentication object.

### 5.1. Trường nên cân nhắc

| Trường | Mục đích | Lưu ý |
| --- | --- | --- |
| event | Tên sự kiện ổn định | Ví dụ resource_server.authentication_failed. |
| service | Tên service | Không dùng hostname/URL tùy ý từ request. |
| requestId | Tương quan request | Đã validate hoặc do hệ thống sinh. |
| traceId, spanId | Tương quan distributed trace | Lấy từ tracer/MDC. |
| http.method | HTTP method | Giá trị enum thông thường. |
| http.route | Route template | Ví dụ /api/orders/{id}, tránh raw URL có query. |
| http.status_code | Status code | Hữu ích cho dashboard. |
| auth.outcome | success/failure | Không ghi token. |
| auth.failure_reason | Mã lỗi đã chuẩn hóa | Ví dụ invalid_signature, invalid_issuer, invalid_audience, expired. |
| auth.scheme | Cơ chế | Ví dụ bearer. |
| resource | API identifier | Dùng tên cấu hình ổn định. |
| scope.required | Quyền cần cho operation | Chỉ log nếu policy cho phép. |
| duration_ms | Thời gian xử lý | Không kèm credential. |

Không phải ứng dụng nào cũng cần tất cả trường. Chỉ thêm trường nếu nó phục vụ một câu hỏi vận hành hoặc audit cụ thể.

### 5.2. Trường không nên log

Không ghi trực tiếp:

- Authorization header hoặc raw Bearer token.
- ID token, access token, refresh token, DPoP proof hoặc client assertion.
- client_secret, password, private key, signing key, API key.
- Authorization code, PKCE code_verifier, session cookie hoặc CSRF token.
- Toàn bộ request/response body của OAuth Token Endpoint.
- Toàn bộ JWT claims hoặc Authentication.toString().
- Email, số điện thoại, địa chỉ, ngày sinh, tên thật hoặc định danh cá nhân nếu không có nhu cầu hợp lệ.
- Claim groups/roles dài hoặc tenant membership nếu không cần cho điều tra.
- URL đầy đủ có query string chứa code, token, state, session hoặc thông tin cá nhân.

Không dựa vào việc JWT đã mã hóa Base64URL để coi payload là an toàn. Phần payload của JWS thường chỉ được encode, ai có token đều có thể đọc claims.

## 6. Ghi authentication event an toàn trong Spring Security

Khi cần ghi authentication outcome, lấy đúng các trường cần thiết từ Authentication, không log toàn bộ object.

Ví dụ helper cho JWT:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

final class SecurityEventLogger {

    private static final Logger log =
            LoggerFactory.getLogger(SecurityEventLogger.class);

    static void authenticationSucceeded(
            JwtAuthenticationToken authentication,
            String resource) {

        String issuer = authentication.getToken().getIssuer() == null
                ? "unknown"
                : safeIssuerId(authentication.getToken().getIssuer().toString());

        log.atInfo()
                .addKeyValue("event", "resource_server.authentication")
                .addKeyValue("outcome", "success")
                .addKeyValue("scheme", "bearer")
                .addKeyValue("issuerId", issuer)
                .addKeyValue("resource", resource)
                .log("Resource Server authentication succeeded");
    }

    static void authenticationRejected(String reason, String resource) {
        log.atWarn()
                .addKeyValue("event", "resource_server.authentication")
                .addKeyValue("outcome", "failure")
                .addKeyValue("failureReason", reason)
                .addKeyValue("resource", resource)
                .log("Resource Server authentication rejected");
    }

    private static String safeIssuerId(String issuer) {
        // Map issuer URI sang tên đã cấu hình, không log URL tùy ý.
        if ("https://login.example.test".equals(issuer)) {
            return "internal-oidc";
        }
        return "unrecognized";
    }

    private SecurityEventLogger() {
    }
}
```

SLF4J fluent key-value logging cần SLF4J 2.x. Nếu dự án dùng logger API khác, giữ cùng nguyên tắc: event name và fields có cấu trúc, allowlist trường, không stringify toàn bộ authentication.

### 6.1. Không log Authentication hoặc Jwt nguyên vẹn

Tránh:

```java
// KHÔNG AN TOÀN: object có thể chứa token và claims.
log.info("Authentication: {}", authentication);

// KHÔNG AN TOÀN: có thể dump tất cả claims.
log.debug("JWT claims: {}", jwt.getClaims());

// TUYỆT ĐỐI KHÔNG: raw token.
log.debug("Bearer token: {}", jwt.getTokenValue());
```

Authentication và Jwt là object có thể mang credential, claims hoặc thông tin định danh. toString() có thể thay đổi giữa các version; không dựa vào nó như một bộ lọc dữ liệu nhạy cảm.

### 6.2. Chuẩn hóa failure reason

Không đưa nguyên exception message hoặc error description vào log mặc định. Chuyển lỗi sang tập mã đã định nghĩa:

| Lỗi authentication | Mã log gợi ý |
| --- | --- |
| Signature invalid | invalid_signature |
| Issuer không được tin | invalid_issuer |
| Audience không khớp | invalid_audience |
| Token hết hạn | expired_token |
| Token chưa có hiệu lực | not_yet_valid |
| Token malformed | malformed_token |
| Introspection báo inactive | inactive_token |
| JWKS/issuer dependency lỗi | identity_provider_unavailable |
| Không có credential | missing_bearer_token |

Không phải mọi JwtException đều cho biết chắc nguyên nhân cụ thể; chỉ gán mã chi tiết khi loại exception thực sự xác định được. Trường hợp không rõ có thể dùng token_validation_failed.

### 6.3. Authentication failure handler

Nếu cần log tại điểm chuyển authentication exception thành HTTP response, có thể bọc AuthenticationEntryPoint hoặc dùng event listener. Chỉ log error code đã chuẩn hóa và request context.

Ví dụ khung entry point:

```java
http.exceptionHandling(exceptions ->
        exceptions.authenticationEntryPoint((request, response, exception) -> {
            String requestId = MDC.get("requestId");

            log.atWarn()
                    .addKeyValue("event", "resource_server.authentication_failed")
                    .addKeyValue("requestId", requestId)
                    .addKeyValue("reason", "invalid_or_missing_token")
                    .log("Bearer authentication failed");

            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setHeader(
                    HttpHeaders.WWW_AUTHENTICATE,
                    "Bearer error=\"invalid_token\"");
        }));
```

Đây là ví dụ rút gọn; production handler cần phân biệt thiếu credential và invalid token nếu API contract cần, đồng thời tránh ghi exception message chứa token. Đừng log request headers hoặc toàn bộ exception object.

## 7. Pseudonymize subject khi cần tương quan

Đôi khi điều tra sự cố cần biết cùng một subject đã gặp lỗi ở nhiều request. Raw sub có thể là định danh ổn định và nhạy cảm. Có thể dùng HMAC để tạo mã giả danh:

```java
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.util.Base64;

final class SubjectPseudonymizer {

    private final byte[] hmacKey;

    SubjectPseudonymizer(byte[] hmacKey) {
        this.hmacKey = hmacKey.clone();
    }

    String pseudonym(String issuer, String subject) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(hmacKey, "HmacSHA256"));

            String input = issuer + "|" + subject;
            byte[] digest = mac.doFinal(
                    input.getBytes(StandardCharsets.UTF_8));

            return Base64.getUrlEncoder()
                    .withoutPadding()
                    .encodeToString(digest);
        } catch (Exception exception) {
            throw new IllegalStateException(
                    "Cannot create subject pseudonym", exception);
        }
    }
}
```

HMAC key phải đến từ secret manager/KMS và có rotation policy. Không hardcode key trong source hoặc log key. Kết hợp issuer và subject để hai issuer có cùng chuỗi sub không bị coi là cùng danh tính.

Mã giả danh vẫn là dữ liệu có thể liên kết qua nhiều sự kiện. Chỉ lưu nếu có mục đích rõ, giới hạn quyền truy cập và retention.

## 8. Token fingerprint khi cần điều tra token cụ thể

Trong một số incident, đội bảo mật cần biết nhiều service đã nhìn thấy cùng một token hay chưa. Không log raw token. Có thể tạo fingerprint HMAC từ token value:

```java
String tokenFingerprint(String token, byte[] fingerprintKey) {
    try {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(fingerprintKey, "HmacSHA256"));
        byte[] digest = mac.doFinal(
                token.getBytes(StandardCharsets.US_ASCII));

        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(digest)
                .substring(0, 16);
    } catch (Exception exception) {
        throw new IllegalStateException(
                "Cannot fingerprint token", exception);
    }
}
```

Fingerprint là tùy chọn, không phải trường bắt buộc. Cân nhắc:

- Dùng HMAC key riêng cho fingerprint, không dùng signing key hoặc encryption key.
- Giới hạn người có quyền đọc fingerprint.
- Có thể truncate digest để giảm dữ liệu, nhưng phải đánh giá collision risk.
- Xoay key để giảm khả năng liên kết lâu dài.
- Không dùng fingerprint làm credential, lookup authorization hoặc bằng chứng token hợp lệ.
- Không tạo fingerprint từ refresh token/client secret nếu không có use case được phê duyệt.

Nếu không có nhu cầu tương quan token cụ thể, bỏ trường này hoàn toàn.

## 9. Che token và secrets ở mọi lớp ghi log

Chỉ che trong application logger là chưa đủ. Credential có thể xuất hiện ở reverse proxy, ingress, API gateway, servlet access log, HTTP client wire log, APM agent, exception handler hoặc log tập trung.

### 9.1. Application logs

- Không log Authorization, Cookie, Set-Cookie, token request body hoặc claims map.
- Dùng structured event với allowlist.
- Không nối request header/body vào message.
- Không log exception message nếu nó có thể chứa request/token.
- Dùng safe failure code thay vì dump object.

### 9.2. Reverse proxy, ingress và API gateway

Kiểm tra access-log format và custom variables. Không cấu hình log toàn bộ request headers. Đặc biệt loại bỏ:

- Authorization
- Cookie và Set-Cookie
- Query parameters như access_token, id_token, code, state, session
- Header nội bộ có secret hoặc user data

Chỉ log method, route/path đã loại query, status, duration, request ID và trace ID cần thiết.

### 9.3. Servlet container access logs

Tomcat/Jetty access logs có thể được cấu hình với các pattern khác nhau. Kiểm tra pattern thực tế và custom valve/filter. Không thêm Authorization header vào access log để debug.

### 9.4. HTTP client logs

Wire logging của Reactor Netty, Apache HttpClient hoặc các HTTP client khác có thể ghi request/response headers và body. Tắt wiretap/body logging ở production hoặc dùng filter allowlist chỉ ghi method, route template, status và duration.

Đặc biệt cẩn thận với:

- OAuth Token Endpoint: request body có client_secret, subject_token, actor_token, authorization code hoặc refresh token.
- Introspection Endpoint: request chứa token cần introspect.
- UserInfo/API downstream: response body có thể chứa PII.
- DPoP: proof JWT và access token có thể xuất hiện cùng request.

### 9.5. APM, tracing collector và crash reporting

Kiểm tra agent và exporter có tự capture headers, query string, exception attributes hoặc request body không. Cấu hình denylist/allowlist ở collector và backend observability; đừng giả định agent luôn che Authorization header mặc định.

## 10. WebClient: chỉ ghi metadata an toàn

Không bật wiretap ở production chỉ để xem request. Nếu cần log outbound call, dùng filter ghi các trường đã chọn:

```java
ExchangeFilterFunction safeRequestLog =
        (request, next) -> {
            log.atDebug()
                    .addKeyValue("event", "http.client.request")
                    .addKeyValue("method", request.method().name())
                    .addKeyValue("path", request.url().getPath())
                    .log("Calling downstream service");

            return next.exchange(request)
                    .doOnNext(response ->
                            log.atDebug()
                                    .addKeyValue("event", "http.client.response")
                                    .addKeyValue(
                                            "status",
                                            response.statusCode().value())
                                    .log("Downstream response received"));
        };
```

Filter này không ghi request headers, URI query hoặc body. Trong ứng dụng thật, nên dùng route template hoặc tên downstream service thay cho path động có thể chứa identifier nhạy cảm.

Nếu cần ghi duration, đo bằng Micrometer Observation/Timer hoặc thêm timestamp theo API phù hợp; tránh giữ request/response body để tính thời gian.

## 11. Không log raw URL hoặc query string

Một số OAuth flow có thể dùng query parameters hoặc callback URL mang dữ liệu nhạy cảm. Ví dụ:

```text
/login/oauth2/code/oidc?code=...&state=...
/callback?access_token=...
/reset-password?token=...
```

Access log nên ghi route template:

```text
GET /login/oauth2/code/{registrationId}
GET /callback
POST /reset-password
```

Không log raw query string. Nếu cần điều tra một parameter, chỉ ghi tên parameter hoặc trạng thái có/không, tuyệt đối không ghi giá trị credential.

## 12. Claims nhạy cảm và nguyên tắc allowlist

JWT claims thường gồm nhiều loại dữ liệu:

| Claim/dữ liệu | Rủi ro | Khuyến nghị |
| --- | --- | --- |
| sub | Định danh ổn định, có thể liên kết người dùng | Bỏ qua hoặc pseudonymize nếu thật sự cần. |
| email, phone_number, name | PII trực tiếp | Không log mặc định. |
| address, birthdate, locale | Dữ liệu cá nhân | Không log mặc định. |
| groups, roles, entitlements | Tiết lộ cấu trúc tổ chức/quyền | Chỉ log mã policy cần thiết, không dump danh sách. |
| tenant, organization | Có thể nhạy cảm hoặc tiết lộ quan hệ khách hàng | Dùng tenant code đã phê duyệt hoặc pseudonym. |
| scope | Tiết lộ quyền ứng dụng | Chỉ ghi scope cần thiết cho security event; không dump tất cả claims. |
| iss, aud | Metadata về trust/resource | Map sang identifier đã cấu hình, tránh URL tùy ý. |
| exp, iat, nbf | Metadata thời gian token | Chỉ log nếu phục vụ điều tra; không cần log toàn bộ token. |
| cnf, key thumbprint | Metadata sender-constrained credential | Hạn chế quyền đọc; chỉ ghi khi cần điều tra binding. |
| Custom claims | Phụ thuộc issuer/domain | Mặc định không log cho tới khi được duyệt. |

### 12.1. Allowlist tốt hơn denylist

Denylist cố tìm mọi claim nhạy cảm có thể có. Khi issuer thêm claim mới, denylist dễ bỏ sót.

Allowlist chỉ ghi những trường đã được chọn:

```java
Map<String, Object> safeClaims = new LinkedHashMap<>();

safeClaims.put("issuerId", "internal-oidc");
safeClaims.put("resource", "orders-api");
safeClaims.put("subjectRef",
        subjectPseudonymizer.pseudonym(issuer, subject));
```

Không làm:

```java
// KHÔNG AN TOÀN: claims có thể tăng hoặc chứa PII/token metadata.
log.debug("claims={}", jwt.getClaims());
```

Khi issuer thêm claim mới, allowlist không tự động ghi claim đó. Đây là đặc tính mong muốn.

### 12.2. Không đưa claims vào trace baggage

Baggage được truyền qua nhiều service và có thể xuất hiện trong telemetry. Không đưa:

- sub, email, phone hoặc tên.
- Access/refresh/ID token.
- Client secret hoặc private key material.
- Full roles/groups hoặc entitlement list.
- Session ID hoặc tenant data nhạy cảm.

Nếu cần truyền business context, chỉ truyền mã không nhạy cảm đã được phê duyệt, với kích thước nhỏ và thời gian sống phù hợp.

## 13. MDC trong async execution

MDC thường gắn với thread. Khi dùng @Async, executor hoặc thread pool, task có thể chạy trên thread khác và không tự có MDC của request ban đầu.

Có thể dùng TaskDecorator để capture và restore context:

```java
import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

import java.util.Map;

public class MdcTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable task) {
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                if (captured == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(captured);
                }
                task.run();
            } finally {
                if (previous == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previous);
                }
            }
        };
    }
}
```

Gắn decorator vào executor do ứng dụng quản lý. Context cần được khôi phục trong finally vì worker thread được tái sử dụng.

### 13.1. MDC propagation không đồng nghĩa SecurityContext propagation

MDC chỉ truyền log context. Nó không truyền authentication hoặc quyền truy cập.

Nếu async task cần thực hiện thao tác có security identity, dùng cơ chế Spring Security phù hợp như DelegatingSecurityContextExecutor hoặc DelegatingSecurityContextAsyncTaskExecutor, và chỉ khi việc truyền security context là đúng với mô hình nghiệp vụ.

Không dùng MDC để khôi phục principal hoặc token.

## 14. Reactor/WebFlux và context propagation

Trong WebFlux, request có thể đổi thread qua các operator. MDC dựa trên ThreadLocal nên không phải nguồn context đáng tin cho reactive pipeline.

Nguyên tắc:

- Dùng Reactor Context và Micrometer Context Propagation/Observation để mang trace context.
- Dùng tracing instrumentation tương thích để tạo span và inject/extract W3C context.
- Không gọi MDC.put() rồi giả định giá trị còn đúng sau publishOn/subscribeOn.
- Không nhét token hoặc claims nhạy cảm vào Reactor Context để log.
- Khi log trong reactive chain, lấy trace context từ cơ chế instrumentation hoặc context accessor phù hợp với version.

Ví dụ ghi một event trong reactive flow mà không đọc raw token:

```java
return inventoryClient.getInventory(sku)
        .doOnSuccess(result ->
                log.atDebug()
                        .addKeyValue("event", "inventory.lookup")
                        .addKeyValue("outcome", "success")
                        .log("Inventory lookup completed"));
```

Trace/span correlation nên do Micrometer/Observation instrumentation đảm nhiệm. Nếu ứng dụng tự tích hợp MDC với Reactor, dùng Context Propagation đúng version và kiểm tra bằng test có thread switch.

## 15. Correlation ID qua service boundary

Khi request đi qua nhiều service, cần thống nhất cách truyền context:

| Header | Mục đích | Có phải credential? |
| --- | --- | --- |
| traceparent | W3C trace context | Không. |
| tracestate | Vendor-specific trace state | Không; không chứa secrets. |
| baggage | Context propagation bổ sung | Không; không chứa token/PII. |
| X-Request-ID | Request correlation theo contract nội bộ | Không. |
| Authorization | Bearer/client authentication | **Có, phải bảo vệ.** |

Ví dụ outbound request an toàn:

```http
GET /api/inventory/SKU-100 HTTP/1.1
Host: inventory.internal
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-7a085853722dc6d2-01
X-Request-ID: req-7f2a
Authorization: Bearer <access-token>
```

Trace context và request ID được truyền để tương quan. Authorization header được gửi vì protocol yêu cầu, nhưng phải được loại khỏi log.

### 15.1. Correlation ID không được dùng làm authorization input

Attacker có thể gửi một request ID trùng với ID của request khác. Vì vậy:

- Không truy vấn dữ liệu người dùng chỉ dựa trên request ID.
- Không cấp quyền vì request có trace ID thuộc một trace đã biết.
- Không cho phép request ID override subject/tenant.
- Không dùng trace context làm CSRF protection hoặc replay protection.

Correlation giúp tìm log; authorization phải dựa trên credential và policy.

## 16. Logging authentication và authorization là hai sự kiện khác nhau

Có thể ghi hai loại event:

**Authentication event** trả lời credential có được chấp nhận không:

```json
{
  "event": "resource_server.authentication",
  "outcome": "success",
  "scheme": "bearer",
  "issuerId": "internal-oidc",
  "resource": "orders-api"
}
```

**Authorization event** trả lời principal có được phép thực hiện operation không:

```json
{
  "event": "resource_server.authorization",
  "outcome": "denied",
  "reason": "insufficient_scope",
  "httpMethod": "POST",
  "route": "/api/orders",
  "requiredAuthority": "SCOPE_orders:write",
  "resource": "orders-api"
}
```

Không cần ghi subject thô. Nếu audit bắt buộc xác định actor, dùng pseudonymous subject reference hoặc identity reference được bảo vệ theo policy.

### 16.1. Không log mỗi request như một security incident

Một request hợp lệ có thể tạo nhiều log kỹ thuật. Chọn event có ý nghĩa:

- Authentication success: có thể chỉ cần metric/trace hoặc audit theo risk.
- Authentication failure: ghi event đã chuẩn hóa, có rate limiting/aggregation.
- Authorization denied: ghi resource, route, policy reason đã chuẩn hóa.
- Privileged action: audit riêng theo yêu cầu nghiệp vụ.

Tránh ghi lặp cùng một failure ở mọi filter, entry point, controller và exception handler.

## 17. Audit log khác application log và trace

| Loại dữ liệu | Mục đích | Đặc tính |
| --- | --- | --- |
| Application log | Debug và vận hành | Có thể nhiều, có mức DEBUG/INFO/WARN/ERROR. |
| Distributed trace | Phân tích latency và dependency | Span có parent/child, sampling, retention riêng. |
| Security audit log | Ghi nhận hành động và quyết định bảo mật quan trọng | Schema ổn định, kiểm soát truy cập, retention và integrity chặt hơn. |

Không dùng trace làm audit record duy nhất: trace có thể bị sampling hoặc hết hạn nhanh. Không dùng application debug log làm audit trail duy nhất: log có thể bị rotate, thiếu integrity hoặc chứa dữ liệu thừa.

Một audit event nên ghi ai thực hiện theo identity reference đã được bảo vệ, hành động nào, resource/object nào với identifier đã được phân loại, kết quả allow/deny, thời điểm và request/trace correlation, policy hoặc reason code.

Không ghi token để chứng minh ai đã gọi. Ghi identity reference đã xác minh và quyết định của hệ thống.

## 18. Log injection và dữ liệu do caller kiểm soát

Header, query, user-agent, URL path và error text có thể do caller kiểm soát. Nếu ghi nguyên văn vào log, attacker có thể chèn newline hoặc chuỗi giống log event khác.

Biện pháp:

- Dùng structured logging thay vì nối chuỗi tự do.
- Validate độ dài và ký tự của request ID.
- Dùng route template thay raw path khi path có identifier.
- Không log raw query string.
- Không ghi trực tiếp exception description do upstream trả về.
- Giới hạn độ dài các field từ bên ngoài.
- Dùng encoder JSON có escaping đúng.

Không tự sanitize bằng cách xóa một vài ký tự rồi cho rằng dữ liệu an toàn. Tốt nhất là chỉ log giá trị có định dạng đã định nghĩa.

## 19. Sampling, retention và quyền truy cập

Tracing sampling giúp kiểm soát chi phí, nhưng không nên làm mất các security audit event bắt buộc.

Khuyến nghị:

- Dùng trace sampling policy phù hợp traffic và incident response.
- Ghi audit events quan trọng theo chính sách riêng, không phụ thuộc trace sampling.
- Có thể ghi metric counter cho mọi authentication failure và lấy mẫu trace tương ứng.
- Rate-limit hoặc aggregate log failure có thể bị attacker tạo hàng loạt.
- Đồng bộ thời gian giữa service để điều tra theo timestamp.
- Giới hạn người đọc log/trace theo least privilege.
- Mã hóa dữ liệu khi truyền và khi lưu.
- Đặt retention theo mục đích và quy định, tự động xóa khi hết hạn.
- Có audit trail cho việc truy cập/export log chứa dữ liệu nhạy cảm.
- Không gửi production logs vào môi trường phát triển hoặc dịch vụ ngoài chưa được phê duyệt.

## 20. Kiểm thử rằng secrets không xuất hiện trong log

Một bài test tốt không chỉ kiểm tra status code. Nó còn xác nhận canary secret không bị ghi ra log.

Ví dụ ý tưởng với Logback ListAppender:

```java
String canaryToken = "test-secret-token-do-not-log";
String canaryEmail = "private-user@example.test";

// Gửi request test hoặc gọi component logging với các giá trị canary.

String capturedLogs = listAppender.list.stream()
        .map(ILoggingEvent::getFormattedMessage)
        .collect(Collectors.joining("\n"));

assertThat(capturedLogs).doesNotContain(canaryToken);
assertThat(capturedLogs).doesNotContain(canaryEmail);
```

Đây là skeleton: cấu hình ListAppender trên logger cần kiểm tra, thực hiện request qua test filter chain và gom cả formatted message lẫn structured key-value fields nếu encoder lưu chúng riêng.

### 20.1. Kiểm tra cả structured fields và MDC

Secret có thể không xuất hiện trong formatted message nhưng vẫn có trong key-value fields, MDC hoặc JSON encoder output. Test nên kiểm tra serialized event cuối cùng hoặc event object đầy đủ:

- Message.
- Argument array.
- Structured key-value pairs.
- MDC properties.
- Exception message/stack trace.
- Captured HTTP request/response logs nếu test client.

### 20.2. Dùng canary values riêng cho từng loại secret

Tạo giá trị dễ nhận biết cho Bearer token, refresh token, client secret, cookie/session value, email/phone claim và query parameter code/state.

Sau request, assert không giá trị nào xuất hiện trong application log, access log hoặc outbound HTTP logger được capture.

### 20.3. Test request ID và trace propagation

Kiểm tra:

1. Request ID hợp lệ được đặt vào MDC và response header.
2. Request ID có newline/độ dài quá mức bị thay bằng ID mới.
3. MDC được dọn sau request kể cả khi controller throw exception.
4. Hai request liên tiếp trên cùng thread không dùng chung request ID.
5. Outbound call có trace context theo instrumentation.
6. Không có Authorization hoặc sensitive baggage trong outbound logs.

## 21. Ma trận vận hành

| Tình huống | Log/trace cần có | Dữ liệu phải tránh |
| --- | --- | --- |
| JWT hợp lệ | requestId, traceId, resource, outcome=success | Raw token, toàn bộ claims. |
| Signature sai | outcome=failure, reason=invalid_signature, traceId | Token, payload JWT. |
| Audience sai | reason=invalid_audience, API identifier | ID token/access token nguyên vẹn. |
| Thiếu scope | authorization denied, route, required authority | Full roles/groups nếu không cần. |
| JWKS endpoint timeout | dependency name, duration, error category | HTTP headers/body có credential. |
| Token exchange thất bại | AS dependency, grant category, error code đã chuẩn hóa | subject_token, actor_token, client_secret. |
| Downstream 5xx | service name, route template, status, duration, trace ID | Authorization header, response body nhạy cảm. |
| UserInfo trả PII | outcome và latency | UserInfo response body, email, phone. |
| Request có query chứa code | route template, status | Raw query string và authorization code. |

## 22. Ví dụ log an toàn và log không an toàn

### 22.1. Log an toàn

```json
{
  "level": "WARN",
  "event": "resource_server.authentication_failed",
  "service": "orders-api",
  "requestId": "req-7f2a",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "7a085853722dc6d2",
  "resource": "orders-api",
  "reason": "invalid_audience",
  "httpMethod": "GET",
  "route": "/api/orders"
}
```

Log này đủ để tìm trace và biết token bị từ chối vì audience. Không cần lưu aud nguyên văn nếu API identifier đã biết.

### 22.2. Log không an toàn

```text
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
JWT claims: {sub=user@example.test, email=user@example.test, ...}
OAuth token request body: subject_token=...&client_secret=...
Cookie: SESSION=...
```

Các giá trị này có thể cho phép tái sử dụng credential hoặc tiết lộ dữ liệu cá nhân. Không ghi chúng ở bất kỳ log level nào, kể cả DEBUG/TRACE.

## 23. Các sai lầm thường gặp

1. **Log toàn bộ Authentication:** object có thể mang JWT và claims; chỉ lấy trường allowlist.
2. **Log raw JWT để debug:** payload có thể đọc được và token có thể dùng lại.
3. **Che token chỉ trong application logger:** proxy, access log, HTTP client và APM vẫn có thể ghi token.
4. **Dùng request ID làm identity:** correlation ID không phải authentication.
5. **Đưa token vào baggage:** baggage được truyền qua nhiều service và telemetry.
6. **Không xóa MDC:** thread pool có thể mang request ID cũ sang request khác.
7. **Giả định MDC tự truyền qua async/reactive:** thread switch có thể làm mất hoặc trộn context.
8. **Log raw URL:** query string có thể chứa code, token, state hoặc PII.
9. **Dùng denylist claims:** claim mới từ issuer có thể lọt qua; ưu tiên allowlist.
10. **Ghi exception message tùy ý:** upstream có thể đưa dữ liệu nhạy cảm vào message.
11. **Dùng trace thay audit:** trace sampling và retention không phù hợp làm audit duy nhất.
12. **Ghi mọi authentication failure không giới hạn:** attacker có thể tạo log flood.
13. **Dùng hash thường cho subject/token:** hash không khóa vẫn có thể bị dò hoặc liên kết; nếu cần pseudonymization, cân nhắc HMAC và rotation.
14. **Cho rằng DEBUG không cần bảo vệ:** log debug vẫn có thể được thu thập và giữ trong hệ thống tập trung.

## 24. Checklist triển khai

- [ ] Có request ID được validate hoặc sinh nội bộ.
- [ ] MDC được set và cleanup trong finally.
- [ ] Filter được đăng ký đúng một lần.
- [ ] Trace ID/span ID đến từ Micrometer Tracing hoặc instrumentation tương thích.
- [ ] W3C trace context được truyền qua outbound clients theo cấu hình.
- [ ] Không dùng trace/request ID làm identity hoặc authorization input.
- [ ] Structured logs dùng event name và field allowlist.
- [ ] Không log Authorization, cookies, tokens, secrets, OAuth request bodies.
- [ ] Không dump Authentication, Jwt, claims hoặc exception tùy ý.
- [ ] Không log raw query string hoặc URL có credential.
- [ ] Claims nhạy cảm được bỏ qua hoặc pseudonymize theo policy.
- [ ] Không đưa token/PII vào trace baggage.
- [ ] Async executor truyền MDC có cleanup; SecurityContext được xử lý riêng.
- [ ] WebFlux dùng Reactor/Micrometer context propagation thay ThreadLocal assumptions.
- [ ] Reverse proxy, ingress, access logs, HTTP clients và APM đều được kiểm tra.
- [ ] Security audit events có retention/access policy riêng.
- [ ] Log injection và log flooding được kiểm soát.
- [ ] Có canary tests xác nhận token, secrets và PII không xuất hiện trong logs.

## 25. Câu hỏi tự kiểm tra

**1. Request ID dùng để làm gì?** Tìm các log liên quan một request theo contract của hệ thống.

**2. Trace ID và span ID khác nhau thế nào?** Trace ID gom distributed trace; span ID nhận diện operation cụ thể.

**3. Traceparent có phải credential không?** Không. Nó là W3C trace context.

**4. Có thể dùng trace ID để quyết định authorization không?** Không.

**5. Vì sao phải cleanup MDC trong finally?** Servlet/executor thread được tái sử dụng; MDC cũ có thể rò sang request khác.

**6. Có nên log Authentication.toString() không?** Không; nó có thể chứa credential hoặc claims.

**7. Có nên log toàn bộ JWT claims không?** Không. Dùng allowlist trường đã được duyệt.

**8. Vì sao allowlist tốt hơn denylist?** Claim mới không tự động bị ghi log.

**9. Có thể log raw access token ở DEBUG không?** Không.

**10. HMAC subject pseudonym dùng để làm gì?** Tương quan cùng subject mà không ghi raw subject, với key được bảo vệ.

**11. Token fingerprint có phải credential không?** Không; nó chỉ là mã tương quan và vẫn cần bảo vệ.

**12. Có thể đưa access token vào baggage không?** Không; baggage được truyền và có thể xuất hiện trong telemetry.

**13. MDC có tự truyền qua WebFlux thread switch không?** Không nên giả định; dùng Reactor/Micrometer context propagation.

**14. Vì sao phải kiểm tra reverse proxy logs?** Token có thể bị ghi trước khi request đến ứng dụng.

**15. Vì sao không log raw query string?** OAuth code/state và nhiều loại credential có thể nằm trong query.

**16. Trace có thay audit log không?** Không; trace có thể sampling và retention khác audit.

**17. Có nên log mọi authentication failure vô hạn?** Không; cần rate limit/aggregation để tránh log flooding.

**18. Test nào phát hiện token bị log?** Gửi canary token/secret rồi kiểm tra serialized log event không chứa giá trị đó.

## 26. Tài liệu tham khảo

- **Spring Boot Reference — Logging:** cấu hình logging và MDC/correlation trong ứng dụng Boot. https://docs.spring.io/spring-boot/reference/features/logging.html
- **Spring Boot Reference — Actuator Observability:** Observation, tracing và propagation context. https://docs.spring.io/spring-boot/reference/actuator/observability.html
- **Spring Security Reference — OAuth 2.0 Resource Server:** JWT/opaque authentication trong Resource Server. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html
- **Micrometer Tracing Reference:** tracer, span, context propagation và bridges. https://docs.micrometer.io/tracing/reference/
- **W3C Trace Context:** chuẩn traceparent và tracestate. https://www.w3.org/TR/trace-context/
- **W3C Baggage:** chuẩn truyền baggage context và các cân nhắc privacy. https://www.w3.org/TR/baggage/
- **OpenTelemetry Specification — Context Propagation:** propagation giữa process và instrumentation. https://opentelemetry.io/docs/specs/otel/context/
- **OWASP Logging Cheat Sheet:** dữ liệu không nên ghi log, log injection và bảo vệ log. https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- **OWASP Secrets Management Cheat Sheet:** quản lý secret và vòng đời credential. https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html

## 27. Kết luận

Logging và tracing tốt giúp lần theo request qua nhiều service, xác định lỗi authentication/authorization và đo latency. Chúng chỉ an toàn khi mỗi event ghi đúng lượng dữ liệu cần thiết. Dùng request ID để tìm log, trace ID/span ID để nối distributed trace, structured events để ghi outcome và reason code; giữ token, secrets, raw claims và PII ngoài message, MDC, baggage, access logs và APM.

Trong Spring Security Resource Server, không dump Authentication, Jwt hoặc request headers. Hãy ghi các trường allowlist như resource, outcome, failure reason, route template và correlation IDs. Với subject cần tương quan, dùng pseudonymization có khóa và policy; với token fingerprint, chỉ triển khai khi có nhu cầu điều tra rõ ràng.

Cuối cùng, kiểm tra toàn bộ đường đi của dữ liệu: ứng dụng, servlet container, proxy, gateway, HTTP client, tracing agent và log backend. Một canary test chứng minh token/secret không xuất hiện trong serialized logs có giá trị hơn một cấu hình che header chỉ ở một logger. Correlation phải giúp điều tra sự cố mà không trở thành một kênh rò credential mới.
