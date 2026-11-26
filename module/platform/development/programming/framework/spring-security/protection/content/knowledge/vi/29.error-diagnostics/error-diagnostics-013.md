# Thu thập log cần thiết mà không ghi token hay nội dung nhạy cảm

> **Chương:** Chẩn đoán lỗi  
> **Mô-đun:** `SPRING_SECURITY_HTTP_PROTECTION` — áp dụng các lớp phòng vệ HTTP và trình duyệt trong Spring Security, từ CSRF, CORS, security headers, CSP, HSTS đến HTTP firewall và bảo vệ session. Người học cấu hình cho Servlet lẫn Reactive, kiểm thử các kịch bản tấn công web và chẩn đoán xung đột bảo mật khi triển khai.

## 1. Tình huống: để tìm lỗi 403, đội vận hành vô tình lưu session cookie

Sau khi cập nhật Spring Security, người dùng không thể gửi biểu mẫu cập nhật hồ sơ. API trả `403 Forbidden`. Người vận hành bật logging chi tiết và ghi vào hệ thống tập trung:

~~~text
2026-11-26T12:00:00Z ERROR POST /account/update?resetKey=<redacted>
Authorization: Bearer <redacted>
Cookie: JSESSIONID=<redacted>; XSRF-TOKEN=<redacted>
X-CSRF-TOKEN: <redacted>
requestBody: {"fullName":"<redacted>","address":"<redacted>"}
~~~

Ví dụ đã thay nội dung bí mật bằng `<redacted>`, nhưng **trong một cấu hình ghi raw request thật**, các trường đó có thể bị lưu nguyên văn. Một log record tưởng chỉ phục vụ debug lại có nguy cơ chứa:

- Bearer/access/refresh token, HTTP Basic credentials hoặc API key.
- Session ID, cookie authentication, CSRF token, signed URL hoặc one-time code.
- Mật khẩu, dữ liệu cá nhân, nội dung tài liệu, thông tin thanh toán.
- Query string có token reset password, invitation code, OAuth `code`/`state`.
- Response body chứa dữ liệu nghiệp vụ, exception message chứa URL/headers hoặc stack trace không được kiểm soát.

Điều cần biết để điều tra 403 có thể chỉ là:

~~~text
timestamp=2026-11-26T12:00:00Z
event=security_request_denied
request_id=88c1a4e2-7964-4cb6-bbdc-f30232135f0c
method=POST
route_template=/account/update
status=403
decision=csrf_rejected
csrf_reason=missing_or_invalid
security_chain=web
duration_ms=18
~~~

Không cần lưu giá trị token để xác định request bị CSRF filter từ chối. Nếu phải phân biệt **token vắng mặt** với **token có mặt nhưng sai**, lưu một trạng thái có tập giá trị cố định (`missing`/`invalid`/`accepted`/`not_checked`), không lưu token.

**Mục tiêu bài:** xây dựng hệ thống quan sát và runbook đủ chẩn đoán phòng vệ HTTP/browser của Spring Security, đồng thời ngăn logs/metrics/traces trở thành nơi tập trung credentials và dữ liệu nhạy cảm.

## 2. Kết quả học tập

Sau bài này, người học có thể:

1. Phân biệt **diagnostic evidence** với dữ liệu nhạy cảm không cần thiết.
2. Thiết kế security event schema tối thiểu dùng mã sự kiện, quyết định, route template, status, request ID, trace ID và thời gian.
3. Chọn đúng log level/category cho Spring Security Servlet và Reactive/WebFlux, không bật DEBUG/TRACE đại trà ở production.
4. Gắn request correlation có kiểm soát; hiểu giới hạn của `MDC` trên Servlet threads và Reactor async.
5. Định vị lỗi 401/403, CSRF, CORS/preflight, HTTP firewall, security headers, CSP, HSTS và session mà không ghi token/cookie/body.
6. Xử lý nguy cơ rò dữ liệu qua access logs, proxy/WAF/CDN, URL query, exception messages, tracing spans, baggage và log collectors.
7. Thực hiện kiểm thử chống rò bí mật trên cả logs, traces, exports và đường báo cáo lỗi.
8. Áp dụng chính sách retention, quyền truy cập, masking, sampling và incident response khi log bị lộ.

## 3. Mô hình an toàn: lưu *quyết định* thay vì lưu *bằng chứng bí mật*

Một security log tốt trả lời:

- Request đi qua lớp nào và bị chặn ở đâu?
- Kết quả là authentication challenge, authorization denied, CSRF failure, CORS rejection hay HTTP firewall rejection?
- Thuộc chain/route/policy version nào?
- Thời điểm, correlation ID, môi trường, latency và tần suất?
- Có thể tái hiện bằng dữ liệu tổng hợp không?

Nó **không cần** trả lời: mật khẩu người dùng là gì, session token nào đã gửi, bearer token có prefix nào, nội dung tài liệu trong request, địa chỉ của người dùng hoặc giá trị CSRF token.

~~~mermaid
flowchart LR
    R[HTTP request] --> S[Spring Security filters]
    S --> E[Security event classifier]
    E --> P[Allowlisted metadata only]
    P --> L[Structured log / metric / trace]
    L --> A[Alert, dashboard, investigation]
    R -. Không đưa credentials/body .-> L
~~~

### Ba lớp dữ liệu quan sát

| Lớp | Mục đích | Ví dụ dữ liệu nên dùng |
|---|---|---|
| **Metric** | Xu hướng, cảnh báo, SLO | Số 401/403 theo route group và loại lỗi, latency histogram |
| **Structured log** | Điều tra một sự kiện | Event code, sanitized route, status, request/trace ID |
| **Distributed trace** | Tìm hop chặn request | Trace ID, span name theo route, service identity, duration, outcome |

**Không coi trace là vùng an toàn hơn log.** Trace attributes, span events, HTTP URL, exception stacks và W3C baggage cũng có thể mang secrets; cùng nguyên tắc tối thiểu hóa phải áp dụng trên mọi luồng dữ liệu.

## 4. Phân loại dữ liệu: lưu gì, loại gì, và điều kiện nào?

| Trường | Mặc định | Lý do |
|---|---|---|
| Thời điểm UTC, event code | **Cho phép** | Nhóm sự kiện và tạo timeline |
| Service/environment/version | **Cho phép** | Phân biệt canary và chính sách đang áp |
| HTTP method chuẩn hóa | **Cho phép** | Phân biệt safe/unsafe request |
| Route template như `/users/{id}` | **Cho phép** | Không lưu giá trị ID trong actual path |
| HTTP status, duration, outcome | **Cho phép** | Chẩn đoán mà không cần body |
| Request ID mới do server tạo | **Cho phép** | Tương quan nhiều lớp |
| Trace ID hợp lệ, không bị client nhúng dữ liệu | **Cho phép có kiểm soát** | Tìm span nhưng không dùng làm authorization |
| Security chain/policy version code | **Cho phép có kiểm soát** | Tìm matcher/config regression |
| CSRF token present? / failure reason enum | **Cho phép** | Không tiết lộ token |
| Authentication present? / mechanism enum | **Cho phép** | Không ghi credential |
| Origin allowed? / method/header classification | **Cho phép** | CORS diagnosis không cần raw Origin nếu có thể phân nhóm |
| Raw URL path/query | **Mặc định không** | ID, email, token và dữ liệu nhạy cảm có thể nằm ở URL |
| `Authorization`/`Proxy-Authorization` | **Cấm giá trị** | Bearer/Basic credentials |
| `Cookie`/`Set-Cookie` | **Cấm giá trị** | Session, remember-me, CSRF, refresh tokens |
| CSRF token header/parameter value | **Cấm** | Token bảo vệ request |
| Password, access/refresh token, API key | **Cấm** | Bí mật tái sử dụng được |
| Request/response body | **Mặc định không** | Có thể chứa PII, tài chính, tài liệu, password |
| Raw stacktrace/exception message | **Chỉ qua chính sách giới hạn** | Có thể chứa URL, headers, input, SQL parameters |
| Full IP, email, username, tenant ID | **Cần mục đích và review riêng** | Dữ liệu liên kết tới cá nhân; có thể là personal data |
| User-Agent/Referer/Origin raw | **Hạn chế** | Client-controlled, có thể mang thông tin định danh hoặc URL |

**“Không log token” không có nghĩa chỉ cần che `Authorization`.** Secrets có thể nằm trong query, path, body, response, exception text, custom headers, service mesh traces và data exports. Một giải pháp chỉ regex sau khi log đã ghi là lớp phòng vệ cuối, không phải bảo đảm chính.

## 5. Các trường HTTP dễ trở thành nguồn rò rỉ

### 5.1. Authentication và session headers

Không ghi:

~~~http
Authorization: Bearer <secret>
Authorization: Basic <encoded-credentials>
Proxy-Authorization: <secret>
Cookie: SESSION=<secret>; JSESSIONID=<secret>
Set-Cookie: SESSION=<secret>; HttpOnly; Secure
X-API-Key: <secret>
X-CSRF-TOKEN: <secret>
X-XSRF-TOKEN: <secret>
~~~

Các dòng chỉ là ví dụ nhận diện **tên header nguy hiểm**, không phải gợi ý log nguyên giá trị. Header khác nhau giữa dự án: có thể có `X-Auth-Token`, `X-Session-ID` hoặc tên tùy chỉnh.

### 5.2. URL query và path

Hai URL có thể trông giống routing thông thường:

~~~text
/reset-password?token=<secret>
/login/oauth2/code/provider?code=<secret>&state=<secret>
~~~

Vì thế không nên mặc định log `request.getRequestURI()` hoặc `request.getQueryString()`: dù path có thể không chứa query trong API cụ thể, path segment vẫn có thể chứa email, account ID hoặc recovery code.

**Ưu tiên route template** do server định nghĩa:

~~~text
GET /users/{userId}
POST /reset-password
GET /login/oauth2/code/{provider}
~~~

Với request bị Spring Security chặn **trước handler mapping**, route template có thể chưa được xác định. Hãy dùng nhóm route/chain do application cấu hình, hoặc enum `unmatched_security_request`, **không rơi về raw URL**.

### 5.3. Đừng xem User-Agent, Referer và Origin là vô hại

User-Agent/Referer/Origin có thể là dữ liệu client kiểm soát hoặc liên quan tới URL cá nhân. Việc ghi toàn bộ:

~~~text
Referer: https://app.example.com/account?invite=<secret>
~~~

vẫn tiết lộ token. Để điều tra CORS, thường đủ ghi `origin_policy=allowed/rejected/absent` hoặc một **mã policy class**; nếu thật sự cần Origin, phải có allowlist/canonicalization, giới hạn độ dài, retention và security review.

## 6. Chọn mức log: ERROR/WARN/INFO so với DEBUG/TRACE

Không nên bật:

~~~properties
# PHẢN VÍ DỤ: không bật rộng/lâu dài trong production.
logging.level.root=TRACE
logging.level.org.springframework=TRACE
logging.level.org.springframework.security=TRACE
logging.level.org.springframework.web=TRACE
~~~

DEBUG/TRACE của framework có thể đưa thêm thông tin request, matcher, principal, exceptions hoặc headers vào hệ thống logs, tùy phiên bản và cấu hình. **Không thể mặc định mọi dòng framework log đều đã được redacted.**

### Chiến lược phù hợp hơn

| Môi trường | Mức log | Cách điều tra |
|---|---|---|
| Production bình thường | INFO/WARN/ERROR theo policy | Structured events tối thiểu, metrics/traces đã sanitize |
| Incident production | Bật tạm **logger cụ thể**, có phê duyệt | Sampling, giới hạn thời gian, phạm vi instance/route, rà soát field |
| Staging có dữ liệu tổng hợp | DEBUG chọn lọc | Tái hiện request/chain/exception nhưng không in secrets |
| Test/local | DEBUG/TRACE ngắn hạn | Dữ liệu giả, không copy logs thật vào issue |

Một cấu hình an toàn mặc định:

~~~properties
logging.level.root=INFO
logging.level.org.springframework.security=INFO
logging.level.org.springframework.web=INFO
~~~

Các cấu hình này chỉ hạn chế một phần rủi ro. Một custom filter dùng `logger.info("{}", request.getHeader("Authorization"))` vẫn làm lộ bí mật dù logger Spring Security ở INFO.

## 7. Log mục tiêu thay vì “full request dump”

Giả sử cần biết Spring Security chain nào từ chối preflight. Thay vì log mọi headers và query, lưu:

~~~json
{
  "event": "cors_preflight_rejected",
  "service": "SPRING_SECURITY_HTTP_PROTECTION",
  "request_id": "b4d245b7-0323-4c7c-9476-ac578621a81e",
  "method": "OPTIONS",
  "route_group": "api",
  "status_code": 403,
  "origin_policy": "not_allowed",
  "requested_method": "POST",
  "requested_headers_policy": "allowed",
  "security_chain": "api",
  "policy_version": "cors-v7"
}
~~~

**Không cần** log `Origin` nguyên văn, `Access-Control-Request-Headers` raw, Cookie hoặc Authorization. Trong ví dụ, tên requested method lấy từ một tập method được kiểm soát; các header names cũng có thể phản ánh metadata nhạy cảm, nên ưu tiên tình trạng policy thay vì ghi toàn bộ danh sách từ client.

### Phân biệt diagnostic log và audit log

Diagnostic log giúp tìm nguyên nhân lỗi kỹ thuật, thường có retention ngắn. Audit log ghi những hành động quan trọng về bảo mật/tuân thủ, có policy bảo vệ, retention và người truy cập khác. **Không vì mục tiêu audit mà ghi mật khẩu, token, session cookie hoặc body nhạy cảm**.

Nếu bài toán cần liên kết một sự kiện với tài khoản để điều tra gian lận, phải thiết kế riêng cơ chế pseudonymous subject reference, phân quyền và retention. Mặc định bài này **không ghi user ID/username**.

## 8. Một schema sự kiện bảo mật tối thiểu, có thể kiểm thử

Đề xuất schema cho Spring application:

~~~json
{
  "timestamp": "2026-11-26T12:00:00Z",
  "event": "security_request_denied",
  "event_version": 1,
  "service": "SPRING_SECURITY_HTTP_PROTECTION",
  "environment": "staging",
  "application_version": "2026.11",
  "request_id": "9db01f72-8c56-43fb-b619-5b3bb8f529b3",
  "trace_id": "d56f34d9a98e8a44e453d282392c1ef2",
  "method": "POST",
  "route_template": "/api/orders/{orderId}",
  "security_chain": "api",
  "status_code": 403,
  "decision": "authorization_denied",
  "reason": "insufficient_authority",
  "duration_ms": 23
}
~~~

| Field | Ràng buộc |
|---|---|
| `event`/`decision`/`reason` | **Enum allowlist**, không raw exception text |
| `request_id` | Sinh server-side, không dùng làm quyền truy cập |
| `trace_id` | Đúng định dạng, nhận từ trusted tracing pipeline khi áp dụng |
| `method` | Chỉ chấp nhận method hợp lệ hoặc `OTHER` |
| `route_template` | Do server định nghĩa, không chứa path params |
| `security_chain` | Tên logic do application định nghĩa, không ghi filter internals tùy ý |
| `duration_ms` | Số nguyên hợp lệ, không chứa request input |
| `application_version` | Build identifier, không chứa commit URL/credentials |
| `environment` | Giá trị cố định từ cấu hình server |

Không thêm trường `headers`, `cookies`, `body`, `exception.message` hoặc `url.raw` mặc định. Schema phải là **allowlist**: mọi trường mới cần review trước khi collector chấp nhận.

## 9. Ba mức nhận diện lỗi: status chưa phải nguyên nhân

| HTTP/status | Nguồn có thể tạo | Event/metadata tối thiểu |
|---|---|---|
| 401 | Authentication entry point | `authentication_required`, mechanism enum, request ID |
| 403 | Authorization denied | `authorization_denied`, policy/role class (không username) |
| 403 | Missing/invalid CSRF | `csrf_rejected`, reason enum, unsafe method |
| 403 | CORS processor từ chối | `cors_rejected`, origin/method/header policy flags |
| 400 | HTTP firewall/rejected request | `request_rejected`, reason code đã phân loại |
| 302 | Form login entry point | `authentication_redirect`, destination class (không raw URL) |
| 429 | Rate limit/gateway | `rate_limited`, policy id |
| Browser CSP violation | Trình duyệt, có thể không đến backend | `csp_violation`, directive/disp. đã chuẩn hóa |
| Header HSTS thiếu | Ở app/proxy/edge response | `header_policy_missing`, header name enum, public HTTPS flag |
| Session expired | Session/auth state | `session_unavailable` hoặc `authentication_required`, không session ID |

**Không viết `403 = thiếu role` hoặc `400 = chắc chắn firewall`.** Cần bằng chứng từ filter/proxy/handler hoặc quy trình đối chứng, không chỉ một HTTP status.

## 10. Request ID: tương quan sự kiện mà không cần session ID

Một request có thể đi qua:

~~~mermaid
flowchart LR
    B[Browser] --> C[CDN / WAF]
    C --> G[Gateway]
    G --> S[Spring Security]
    S --> D[Controller / downstream]
    C -. request ID, trace context đáng tin .-> G
    G -. correlation đã kiểm soát .-> S
~~~

Với một request ID không chứa dữ liệu cá nhân:

~~~text
edge:   request_id=6c52f8... upstream_status=403
api:    request_id=6c52f8... event=csrf_rejected status=403
client: X-Request-ID: 6c52f8...
~~~

ta có thể ghép sự kiện mà không ghi raw path, account name hoặc token.

### Nguy cơ với request ID đến từ client

Một client có thể gửi:

~~~http
X-Request-ID: <client-controlled-value>
~~~

Nếu ứng dụng ghi thẳng giá trị này, attacker có thể chèn chuỗi dài, newline, log forging payload hoặc cả secret vào logs. Vì vậy:

- **Đơn giản nhất:** sinh UUID ngẫu nhiên ở server, không tin ID từ client.
- Nếu ingress đã sinh ID, chỉ nhận qua **trusted proxy** và kiểm tra định dạng/độ dài nghiêm ngặt.
- Giới hạn một ID chuẩn; không dùng raw header làm tên file, metric label hay cấu trúc truy vấn.
- Request ID là **correlation handle**, không phải authentication token, secret hoặc quyền truy cập dữ liệu.

Trong hệ thống nhiều hops, đồng nhất quy tắc tạo/truyền ID và phản hồi cho browser. Một service sinh ID mới ở mọi hop có thể làm việc ghép logs khó khăn; trace context và mapping giữa IDs cần thiết kế trước.

## 11. Servlet: một filter logging tối thiểu, không đụng request body/headers

Đây là ví dụ Spring Boot Servlet dùng một filter ở tầng container để ghi **method, route template, status, duration và request ID**. Filter **không gọi** `getInputStream()`, `getReader()`, `getParameterMap()`, `getHeader("Authorization")`, `getCookies()`, `getQueryString()` hoặc log raw URI.

~~~java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.Set;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerMapping;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 20)
public final class SafeHttpRequestLogFilter
        extends OncePerRequestFilter {

    private static final Logger LOG =
        LoggerFactory.getLogger(SafeHttpRequestLogFilter.class);

    private static final Set<String> METHODS = Set.of(
        "GET", "HEAD", "POST", "PUT",
        "PATCH", "DELETE", "OPTIONS"
    );

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {

        String requestId = UUID.randomUUID().toString();
        String method = METHODS.contains(request.getMethod())
            ? request.getMethod() : "OTHER";
        long start = System.nanoTime();

        // Request ID do server tạo, không lấy trực tiếp từ client header.
        response.setHeader("X-Request-ID", requestId);

        try (MDC.MDCCloseable ignored =
                MDC.putCloseable("requestId", requestId)) {
            try {
                chain.doFilter(request, response);
            } finally {
                Object matched = request.getAttribute(
                    HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE
                );
                String route = matched instanceof String s
                        && s.length() <= 160
                    ? s : "UNMAPPED";

                long durationMs =
                    (System.nanoTime() - start) / 1_000_000;
                LOG.info(
                    "event=http_request_end request_id={} " +
                    "method={} route_template={} status={} duration_ms={}",
                    requestId, method, route,
                    response.getStatus(), durationMs
                );
            }
        }
    }
}
~~~

**Điều kiện kỹ thuật:** ví dụ sử dụng Java có hỗ trợ pattern matching cho `instanceof`, và Spring MVC request mapping metadata phải được gắn khi có handler match. Trường `UNMAPPED` là **chủ ý** cho pre-security rejection, static/error route hoặc path chưa có pattern: không dùng raw URL làm fallback.

### Điều ví dụ này bảo đảm

- Không tự log token, Cookie, query, body hoặc raw path.
- Có request ID do server sinh để đối chiếu client/server.
- Giữ route template do framework cung cấp nếu có.
- Dọn `MDC` trong `try-with-resources`, tránh lây ID sang request khác trên worker thread.

### Điều ví dụ này **không** tự bảo đảm

- Nó không lọc bí mật từ **mọi logger khác** trong ứng dụng và dependencies.
- Nếu exception phát sinh rồi error dispatch cập nhật status sau thời điểm filter ghi, status quan sát ở `finally` có thể chưa phản ánh final public response. Đối chiếu proxy/HTTP response.
- Nếu request chuyển sang Servlet async dispatch, `MDC` thread-local không tự theo nhiệm vụ bất đồng bộ; log ở `finally` có thể đo giai đoạn chưa hoàn tất. Cần AsyncListener/Observation hoặc cơ chế lifecycle phù hợp cho độ chính xác.
- Servlet filter được container đăng ký và Spring Security filter chain là **hai tầng khác nhau**. Một request bị `web.ignoring()` có thể vẫn vào filter này, nhưng **không** có nghĩa đã đi qua Spring Security.
- Một request bị HTTP parser từ chối trước Servlet filter sẽ **không tạo record từ filter này**; tìm tại container/proxy.

## 12. Servlet MDC: sử dụng đúng phạm vi và dọn sạch

`MDC` thường là thread-local context để formatter thêm request ID vào các log lines chạy trong cùng request thread:

~~~properties
logging.pattern.level=%5p [reqId:%X{requestId:-}]
~~~

Khi có sự kiện:

~~~text
WARN [reqId:6c52f8...] event=authorization_denied ...
~~~

Điều cần nhớ:

1. **Chỉ đặt metadata không nhạy cảm** vào MDC.
2. Dùng `try/finally` hoặc `MDC.putCloseable` để luôn xóa context.
3. Thread pools tái sử dụng threads; thiếu cleanup có thể gắn request ID/username cũ vào request mới.
4. Không nhét `sessionId`, `Authorization`, raw `Origin` hoặc request body vào MDC.
5. Khi dùng `@Async`, `CompletableFuture`, Servlet async hoặc Reactor, thread có thể đổi; MDC không tự propagate đúng.

**Không sửa bằng cách đưa một singleton mutable `currentRequestId` vào application.** Nhiều requests đồng thời sẽ overwrite nhau; nguy cơ trộn dữ liệu và sai điều tra.

## 13. Servlet: ghi sự kiện 403 từ AccessDeniedHandler có phân loại

Spring Security Servlet có thể chuyển `AccessDeniedException` (bao gồm một số lỗi CSRF) sang `AccessDeniedHandler`. Nếu muốn ghi một sự kiện chuyên biệt, **không log exception object hoặc message nguyên văn**.

~~~java
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.security.web.access.AccessDeniedHandlerImpl;
import org.springframework.security.web.csrf.CsrfException;

public final class SafeAccessDeniedHandler
        implements AccessDeniedHandler {

    private static final Logger LOG =
        LoggerFactory.getLogger(SafeAccessDeniedHandler.class);
    private final AccessDeniedHandler delegate =
        new AccessDeniedHandlerImpl();

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            AccessDeniedException exception)
            throws IOException, ServletException {

        String reason = exception instanceof CsrfException
            ? "csrf_rejected" : "authorization_denied";

        LOG.warn("event=security_request_denied reason={} " +
                 "status_expected=403", reason);

        // Giữ HTTP denial behavior, không trả 200 để che lỗi.
        delegate.handle(request, response, exception);
    }
}
~~~

Gắn vào **một chain Servlet có chủ đích**:

~~~java
http.exceptionHandling(handler -> handler
    .accessDeniedHandler(new SafeAccessDeniedHandler())
);
~~~

**Đây là minh họa, không phải cấu hình cần copy vô điều kiện.** Với Bearer resource server, một custom `AccessDeniedHandlerImpl` có thể làm mất chi tiết challenge/error protocol mà OAuth2-specific handler lẽ ra phát. Nếu ứng dụng dùng OAuth2/Bearer, hãy **bọc/delegate cho đúng handler của cơ chế đó** (ví dụ Bearer-specific handler) để giữ tiêu chuẩn status/WWW-Authenticate khi cần.

### Không log exception message

Không làm:

~~~java
LOG.warn("Access denied: " + exception.getMessage(), exception);
~~~

Exception message và stack trace có thể chứa request URL, principal hoặc dữ liệu do user kiểm soát trong custom exceptions. Dùng **reason enum** và một request ID hợp lệ để lần tới bằng nguồn kỹ thuật khác khi cần.

## 14. Servlet authentication failures: log kết quả, không principal/password

Authentication events có thể phát sinh ở nhiều cơ chế: form login, HTTP Basic, Bearer/OAuth2, session, remember-me hoặc authentication entry point. Đừng mặc định 401 luôn là “user nhập sai mật khẩu”.

### Event code tối thiểu

~~~text
event=authentication_required mechanism=bearer status=401
event=authentication_failed mechanism=form reason=bad_credentials
event=authentication_required mechanism=session reason=missing_session
event=authorization_denied mechanism=authenticated reason=insufficient_authority
~~~

**Không ghi** username/email trực tiếp, password đã gửi, raw `Authorization`, decoded JWT claims hoặc authentication object `toString()`.

### Tại sao exception object không phải field an toàn?

Một `AuthenticationException` có thể chứa nguyên nhân nested hoặc debug text, còn `Authentication`/`Credentials` object có thể lộ principal details khi tùy biến. Log **class/reason đã allowlist** (ví dụ `bad_credentials`, `invalid_token`, `session_missing`), không gọi `log.warn("{}", authentication)` hay dump toàn `SecurityContext`.

### Không thay đổi response để log đẹp hơn

HTTP Basic cần challenge, Bearer resource server có yêu cầu RFC cho WWW-Authenticate, form-login có thể redirect. Diagnostic logging **không nên đổi cơ chế xác thực hoặc mã response** chỉ để tạo một event format chung.

## 15. Phân biệt 401, 403, CSRF và session bằng sự kiện không có token

| Sự cố | Tập dữ liệu nhỏ đủ chẩn đoán | Tránh |
|---|---|---|
| 401 chưa xác thực | Route group, entry point type, auth mechanism enum, status | Bearer token, password, username raw |
| 403 thiếu role/scope | Decision `authorization_denied`, rule ID/role class | Full JWT claims/Authorities string không review |
| CSRF 403 | `csrf_state=missing/invalid`, method, route template | Header value, token cookie, session ID |
| Session timeout | `session_state=not_found/expired` nếu xác định được, status | Session IDs, raw Set-Cookie |
| Login redirect loop | Policy/chain, status, redirect target **class** | Full Location/query (OAuth code/state) |
| Multiple SecurityFilterChains | Chain ID được chuẩn hóa, request group | Dump filter graph chứa raw request |

### Thận trọng với log trạng thái CSRF

Không phải lúc nào cũng dễ xác định `missing` hay `invalid` ở mọi filter/stack. Nếu không có bằng chứng an toàn, ghi `csrf_rejected` thay vì đoán hoặc log token để phân tích. **Status 403 chưa đủ xác định CSRF**, vì authorization, CORS processor hoặc proxy cũng có thể trả 403.

## 16. CORS và preflight: log policy outcome, không log Origin và credentials thô

Preflight thường:

~~~http
OPTIONS /api/orders
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Một bản ghi gợi ý:

~~~json
{
  "event": "cors_preflight_evaluated",
  "method": "OPTIONS",
  "route_group": "orders_api",
  "requested_method": "POST",
  "origin_state": "approved",
  "requested_headers_state": "approved",
  "result": "accepted"
}
~~~

Với Origin sai:

~~~json
{
  "event": "cors_preflight_evaluated",
  "route_group": "orders_api",
  "origin_state": "rejected",
  "result": "denied"
}
~~~

### Khi nào cần thêm chi tiết?

Trong staging với origins test có thể cho phép **nhãn** `origin_group=frontend_staging` hoặc `origin_group=unrecognized`; không in raw Origin, URL, Cookie hay Bearer để tìm mismatch. Với method/header names do client gửi, dùng allowlist và length limit.

Phân biệt:

- OPTIONS 401/302 trước khi xử lý CORS.
- OPTIONS 403 do CORS policy thật sự từ chối.
- OPTIONS 403/405 do WAF/gateway, Spring không thấy.
- OPTIONS chấp thuận nhưng actual POST bị 403 do CSRF hoặc authorization.

Không gộp tất cả thành `cors_error` vì nó che mất tầng thực sự cần sửa.

## 17. HTTP firewall và RequestRejectedException: ít dữ liệu vẫn đủ

Trong Spring Security Servlet, `StrictHttpFirewall` có thể từ chối URL không hợp lệ trước khi request đi sâu vào security chain, tùy container/filter order.

~~~text
event=http_request_rejected
component=spring_security_firewall
reason_class=path_normalization
method=GET
status_class=4xx
request_id=...
~~~

**Không cần log URL rejected raw**. Một URL bất thường có thể chứa encoded secrets, username hoặc payload điều khiển log. Để điều tra một loại rejection, có thể dùng enum:

~~~text
path_normalization
invalid_method
invalid_header
url_encoding
other_request_rejection
~~~

Đây là **nhãn nghiệp vụ tự định nghĩa**, không khẳng định Spring cung cấp sẵn chính xác các enum đó. Phân loại dựa trên bằng chứng/version cụ thể; nếu không phân loại an toàn được, dùng `other_request_rejection`.

### Lỗi xảy ra trước ứng dụng

HTTP parser của reverse proxy/container có thể từ chối request trước cả Spring Security. Khi đó app **không có log**; xem ingress/container metrics và sanitized rejection category. Không bật packet capture toàn traffic chứa credentials chỉ vì thiếu một application log.

## 18. Reactive/WebFlux: không phụ thuộc MDC thread-local cho toàn request

Reactive xử lý bất đồng bộ; request có thể đi qua nhiều event-loop threads hoặc scheduler. Nếu code:

~~~java
MDC.put("requestId", id);
return chain.filter(exchange);
~~~

rồi kỳ vọng mọi `flatMap`/`publishOn`/`subscribeOn` giữ cùng `MDC`, log có thể mất ID hoặc mang ID request khác khi threads được tái sử dụng.

Trong WebFlux:

- `ServerWebExchange` chứa attributes sống theo lifecycle exchange.
- Reactor `Context` có thể mang metadata bất biến qua reactive chain.
- Micrometer Tracing/Observation có cơ chế context propagation riêng, cần cấu hình/version phù hợp.
- Nếu muốn tích hợp MDC, phải dùng **context propagation đã kiểm thử**, không tự giả định ThreadLocal là request-local trong Reactor.

### Một logger WebFilter không ghi header/body

~~~java
import java.util.Set;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import org.springframework.web.util.pattern.PathPattern;
import reactor.core.publisher.Mono;

@Component
public final class SafeReactiveRequestLogFilter
        implements WebFilter {

    private static final Logger LOG =
        LoggerFactory.getLogger(SafeReactiveRequestLogFilter.class);
    private static final Set<String> METHODS = Set.of(
        "GET", "HEAD", "POST", "PUT",
        "PATCH", "DELETE", "OPTIONS"
    );

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String requestId = UUID.randomUUID().toString();
        long started = System.nanoTime();
        exchange.getAttributes().put("safeRequestId", requestId);
        exchange.getResponse().getHeaders()
            .set("X-Request-ID", requestId);

        return chain.filter(exchange)
            .contextWrite(context ->
                context.put("safeRequestId", requestId))
            .doFinally(signal -> {
                Object matched = exchange.getAttribute(
                    HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE
                );
                String route = matched instanceof PathPattern pattern
                    ? pattern.getPatternString() : "UNMAPPED";

                String rawMethod = exchange.getRequest()
                    .getMethod().name();
                String method = METHODS.contains(rawMethod)
                    ? rawMethod : "OTHER";

                HttpStatusCode status =
                    exchange.getResponse().getStatusCode();
                String statusCode = status == null
                    ? "UNKNOWN"
                    : Integer.toString(status.value());

                long durationMs =
                    (System.nanoTime() - started) / 1_000_000;
                LOG.info(
                    "event=http_request_end request_id={} " +
                    "method={} route_template={} status={} " +
                    "signal={} duration_ms={}",
                    requestId, method, route, statusCode,
                    signal.name(), durationMs
                );
            });
    }
}
~~~

Ở đây:

- Mỗi exchange tự sinh ID, không lấy raw header client.
- Không gọi `getQueryParams()`, `getHeaders()` để ghi values, không đọc request/response body.
- Lấy route pattern do WebFlux handler mapping tạo; `UNMAPPED` khi request bị chặn sớm.
- `signal.name()` là enum Reactor, giúp phân biệt complete/error/cancel mà không in exception.
- `contextWrite(...)` cung cấp ID cho các phần reactive chain biết cách đọc Reactor Context; **nó không tự động nhét ID vào MDC**.

**Giới hạn kỹ thuật:** `doFinally` diễn ra theo lifecycle của reactive publisher, không phải bảo đảm mọi bytes đã được network flush. Trên error path, status có thể chưa được set, hoặc response lỗi được tạo bởi outer handler; với response public cuối cùng hãy đối chiếu proxy/HTTP logs. Nếu `matched` là loại khác `PathPattern`, logger cố tình ghi `UNMAPPED` thay vì `toString()` dữ liệu không kiểm soát.

### WebFlux: logger an toàn không thay thế SecurityWebFilterChain

Một `WebFilter` ghi event tối thiểu là **quan sát request**, không phải cấu hình authorization. Ứng dụng vẫn cần security chain đúng phạm vi:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveSecurityProtection {
    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        http.authorizeExchange(auth -> auth
            .pathMatchers("/api/public/**").permitAll()
            .pathMatchers("/api/**").authenticated()
            .anyExchange().denyAll()
        );
        http.httpBasic(Customizer.withDefaults());
        http.csrf(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Ví dụ sử dụng HTTP Basic cho minh họa authentication; với OAuth2 Bearer hoặc form/session cần cấu hình đúng cơ chế và CSRF threat model, không copy nguyên chain mà làm thay đổi chính sách ứng dụng. `SafeReactiveRequestLogFilter` ghi metadata riêng, không ghi credentials kể cả khi request bị 401/403.

## 19. Reactor Context và request metadata an toàn

Trong reactive service pipeline, code có thể đọc request ID từ Reactor context khi cần correlation:

~~~java
Mono<String> operation = Mono.deferContextual(ctx -> {
    String requestId = ctx.getOrDefault(
        "safeRequestId", "UNAVAILABLE"
    );
    // Chỉ dùng requestId để correlation; không dùng làm quyền truy cập.
    return Mono.just("event=operation_started request_id=" + requestId);
});
~~~

Đoạn code này chỉ minh họa cách đọc Context, không khuyến nghị mỗi service tự viết log-string thay cho centralized structured logger.

### Không dùng ThreadLocal thay cho Reactor Context

Một WebFlux request có thể tiếp tục ở thread khác sau DB call hoặc HTTP client request. Nếu muốn `traceId`/requestId đi xuyên các luồng, ưu tiên cơ chế Observation/Tracing và Reactor context propagation được hỗ trợ bởi stack/version dự án.

### Traces và baggage cũng cần allowlist

W3C `traceparent` phục vụ tương quan trace, nhưng incoming trace context có thể đến từ client. Không dùng trace ID làm token hoặc assume caller đáng tin. `baggage` có thể chứa nhiều key-value tự khai; **không truyền nguyên baggage vào logs/metrics**. Chỉ lan truyền keys được chính sách cho phép, có giới hạn kích thước, retention và tránh chèn PII.

## 20. Lấy correlation từ trusted edge khi có nhiều services

Nếu gateway sinh request ID trước Spring, application có thể muốn giữ ID để ghép toàn hệ thống. Cách làm cần có trust boundary:

~~~text
Internet client (headers không đáng tin)
   -> CDN/ingress:
      xóa inbound X-Request-ID không hợp lệ
      sinh hoặc validate ID chuẩn
      thêm X-Request-ID internal
   -> Spring (chỉ reachable từ ingress)
      đọc ID do proxy đáng tin cấp
      log field request_id
~~~

Lỗi thường gặp:

~~~text
X-Request-ID: <newline-or-long-user-controlled-string>
~~~

được chèn nguyên vào log formatter. Điều đó có thể tạo log forging hoặc chứa secret. **Sự có mặt của header không đủ chứng minh nguồn đáng tin**.

### W3C traceparent không mang thông tin định danh người dùng

Trace IDs được tạo ngẫu nhiên theo định dạng của tracing protocol. Đừng “mã hóa” user ID, token hoặc thông tin session vào trace ID. Tracing service có thể tạo root trace mới khi incoming context sai hoặc không đáng tin; chính sách sampling và upstream links phải được định nghĩa.

## 21. Spring Security logging categories: bật chính xác nơi cần tìm

Trong staging, có thể cân nhắc bật **một logger cụ thể** để chẩn đoán filter order:

~~~properties
# Chỉ bật ngắn hạn ở staging/canary có dữ liệu tổng hợp.
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
~~~

Reactive có thành phần tương ứng:

~~~properties
logging.level.org.springframework.security.web.server.WebFilterChainProxy=TRACE
~~~

**Ràng buộc quan trọng:**

- Các logger, thông điệp và nội dung được ghi thay đổi theo Spring Security/Boot version.
- TRACE/DEBUG có thể tiết lộ URI, matcher hoặc principal details qua framework hoặc custom filters.
- Không bật `org.springframework.security=TRACE` trên production traffic thật mà không có risk review.
- Không log toàn `SecurityContext`, Authentication/Exception objects để thay thế chain-selection diagnostics.
- Sau incident, **tắt lại** log level tạm, kiểm tra collector đã nhận những fields nào và retention.

### Logging để giải 401/403 nhưng không có token

Thu thập event classification **ở đúng điểm ra quyết định**:

| Điểm | Có thể ghi | Tránh ghi |
|---|---|---|
| Authentication entry point | Mechanism, status, request ID | Token value, raw username |
| AccessDeniedHandler | Reason class `csrf/authorization` | Exception message, CSRF token |
| CORS processor | Origin/method/header allowlist decision | Raw origin/header values không review |
| HTTP firewall handler | Rejection category, status | Raw rejected URL |
| Gateway/WAF | Rule code, correlation, upstream reachability | Full request dump, sensitive headers |
| WebFlux security filters | Sanitized decision/event | `ServerWebExchange.toString()`, body |

Không nhất thiết mọi component có sẵn điểm extension public để gắn logger. Nếu không có, dùng an toàn các metrics/test cases và chọn lọc logger của framework, không dựa vào reflection hoặc hack filter order.

## 22. Tomcat access log: đừng giữ query hay full request line mặc định

Một số access-log patterns có thể đưa URL/query hoặc client IP vào log files. Với Spring Boot Servlet dùng embedded Tomcat, một mẫu **tối thiểu cho troubleshooting aggregate**:

~~~properties
server.tomcat.accesslog.enabled=true
server.tomcat.accesslog.pattern=%t %m %s %D
~~~

Ở đây `%t` là timestamp, `%m` method, `%s` status và `%D` elapsed time theo mẫu Tomcat tương ứng. Cần xác minh placeholder/đơn vị theo container version thực tế.

**Không đặt**:

~~~properties
# PHẢN VÍ DỤ: %r/%q và header values có thể chứa secrets.
server.tomcat.accesslog.pattern=%h %l %u %t "%r" %s %b %{Authorization}i %{Cookie}i
~~~

`%h` có thể là IP/hostname client, `%u` identity và `%r` thường chứa request line, bao gồm URL/query. Trong hệ thống dùng Netty/WebFlux, cấu hình Tomcat này **không điều khiển Reactor Netty access logging**.

### Giới hạn của access log tối thiểu

Nó không cho route template hoặc CSRF reason. Đó là chủ ý: route classification nằm trong structured application event; access log chủ yếu kiểm tra traffic, method, status và thời gian. Khi cần ghép hai nguồn, dùng request/trace ID theo giải pháp được tin cậy.

## 23. Reverse proxy/WAF/CDN: bảo vệ log trước khi request đến Spring

Một request có thể bị chặn trước Spring Security:

~~~text
Browser -> CDN/WAF [403] -> không tới Spring Boot
Browser -> Nginx [400] -> không tới FilterChainProxy
Browser -> Gateway [302] -> không tới Controller
~~~

Vì vậy một incident 403 không có Spring logs **không chứng minh client không gửi request**. Cần sanitized logs tại edge.

### Mỗi tầng nên có cùng policy dữ liệu tối thiểu

| Tầng | Dữ liệu hữu ích | Tránh |
|---|---|---|
| CDN | Event, edge rule/policy ID, status, request ID, cache disposition | Cookies, auth headers, raw URL query |
| WAF | Rule category, allow/block/challenge, request group | Captured malicious payload raw nếu không có sandbox an toàn |
| Ingress/Gateway | Upstream selected?, status, duration, route group | Full request/response bodies |
| Servlet container/Netty | Parser rejection, status, method, timing | Raw request line có token |
| Spring Security | Chain/decision reason enum, status, request ID | Authentication/CSRF objects |
| App handler | Validation error code/class, route template | Form data, personal values |

Nếu WAF cần lưu payload phục vụ forensic investigation, đó là **workflow riêng** có phê duyệt, access controls, encryption và thời gian lưu ngắn, không phải mặc định của ứng dụng hay toàn production traffic.

### Proxy access log phải được rà riêng

Nginx, Envoy, Apache, CDN và API Gateway có cấu hình log khác nhau. Đừng mặc định Spring không log headers thì proxy cũng không. Một dòng access log ở edge với `$request` có thể chứa query; một “debug capture” trên WAF có thể lưu toàn body. Cần audit **toàn đường thu thập**, không chỉ application code.

## 24. CSP reports: report URL không nhất thiết vô hại

Browser có thể gửi CSP violation reports để giúp điều tra:

~~~text
event=csp_violation
disposition=enforce
effective_directive=script-src-elem
resource_class=inline_script
policy_version=csp-v12
~~~

Report thô có thể chứa `document-uri`, `blocked-uri`, `source-file`, đôi khi `sample` tùy reporting policy và browser behavior. Những URL/code samples có thể tiết lộ đường dẫn riêng tư, query secrets hoặc nội dung mã được chèn.

### Cách xử lý an toàn

1. Chỉ chấp nhận các fields đã review, theo version/schema của browser.
2. Trích `effectiveDirective`/`disposition`, phân loại resource; không lưu full `document-uri`/`blocked-uri` theo mặc định.
3. Không bật `'report-sample'` trên diện rộng nếu nó làm lộ inline code/dữ liệu người dùng.
4. Giới hạn kích thước, tốc độ và retention, vì collector nhận input không đáng tin.
5. Đặt CSP report endpoint trong monitoring policy riêng, không tắt CSRF toàn API để nhận reports.
6. Không tự đưa report đến bên thứ ba nếu nó chứa thông tin nhạy cảm chưa được xử lý.

**CSP report không phải bằng chứng script đã chạy.** Nó mô tả policy violation theo browser; với Report-Only, hành động có thể vẫn được thực hiện.

## 25. HSTS và security headers: ghi trạng thái chính sách, không ghi secrets

Để chẩn đoán HSTS thiếu sau reverse proxy, không cần log cookie/session:

~~~text
event=header_policy_check
header=Strict-Transport-Security
public_scheme=https
upstream_scheme=http
app_secure_detection=false
header_writer_enabled=true
result=missing_on_public_response
~~~

Những fields này là **kết quả phép đo ở môi trường được kiểm soát**, không phải mặc định Spring tự phát sẵn event như vậy. Cần đối chiếu:

- Browser HTTPS → proxy TLS termination → HTTP upstream.
- `Forwarded`/`X-Forwarded-Proto` do proxy **đáng tin** đặt.
- Spring Servlet `request.isSecure()` hoặc Reactive URI scheme.
- Selected security chain/header writer và HTTPS public response.

**Không log raw `Forwarded` hay toàn `X-Forwarded-*` chỉ để sửa HSTS.** Các header này có thể do client giả mạo; đối chiếu proxy config và chỉ ghi trạng thái đã chuẩn hóa. Nếu browser HTTPS nhưng app secure flag false, hướng sửa có thể là forwarded processing hoặc HSTS edge owner — không phải tắt cookie `Secure`.

## 26. Đường nhạy cảm: login, reset-password, OAuth và download

Những routes này dễ chứa secrets trong URL, form hoặc response:

| Route group | Điều nên log | Dữ liệu đặc biệt cần tránh |
|---|---|---|
| `/login` | `authn_failure`/reason class, status | Username, password, Basic credential |
| `/oauth2/authorization/{provider}` | Provider ID allowlist, event code | Raw authorization URL/query/state |
| `/login/oauth2/code/{provider}` | Route template, callback result | OAuth authorization code, state |
| `/reset-password` | Event code, outcome, rate limit | Reset token, email, secret URL |
| `/download/{id}` | Route template, status/latency | Filename, file ID nếu nhạy cảm, file body |
| `/api/payments/{id}` | Route template, status, outcome | Card/payment/financial details |
| `/api/profile` | HTTP method, status/validation code | Name, address, phone, date of birth |
| `/admin/**` | Policy class/denial type | Admin usernames, session IDs |

### Không tự động log exception arguments

Một validation exception có thể chứa rejected field value. Ví dụ ghi `BindingResult.toString()`, `ConstraintViolation.toString()` hoặc toàn DTO có thể lộ PII. Ưu tiên:

~~~text
event=request_validation_failed
route_template=/api/profile
validation_code=invalid_format
field_class=contact_info
status=400
~~~

với enums được định nghĩa trước, thay vì in raw invalid value hay dynamic field path do client tạo.

## 27. Request/response body logging: những tiện ích dễ bị dùng sai

Trong Spring MVC, developer có thể dùng `CommonsRequestLoggingFilter` hoặc `ContentCachingRequestWrapper` để debug request body. Trong WebFlux có thể dùng `WebFilter` kết hợp `ServerHttpRequestDecorator`/`ServerHttpResponseDecorator` hoặc framework codecs logging.

**Không bật các tiện ích này để ghi toàn body trong production.** Một endpoint đăng nhập, upload, thanh toán, OTP, form profile hoặc OAuth exchange có thể chứa secrets. Việc cache/buffer body để log còn có thể:

- Tăng memory usage và latency với payload lớn.
- Thay đổi đặc tính streaming/backpressure ở Reactive nếu triển khai sai.
- Làm rò file upload hoặc response body được mã hóa.
- Ghi lại payload không được phép lưu theo chính sách dữ liệu.
- Khi lỗi xảy ra, khiến exception logger hoặc APM capture body ngoài dự kiến.

### Một cấu hình *không nên* đưa vào production

~~~java
// PHẢN VÍ DỤ: không bật broad payload logging.
requestLoggingFilter.setIncludePayload(true);
requestLoggingFilter.setIncludeHeaders(true);
requestLoggingFilter.setIncludeQueryString(true);
~~~

Nếu bắt buộc điều tra payload trong lab, dùng **dữ liệu tổng hợp**, phạm vi endpoint được duyệt, thời hạn ngắn và tắt sau điều tra. Ở production, ưu tiên business error code và trạng thái validation mà không chứa field values.

### Log được độ dài body có an toàn không?

Ngay cả `Content-Length` cũng có thể trở thành tín hiệu nhạy cảm trong một số ứng dụng (ví dụ kích thước hồ sơ y tế/tệp riêng tư). Nếu dùng, làm tròn vào size buckets và chỉ cho mục đích quan sát đã duyệt. Không ghi hash tùy ý của body: hash có thể giúp liên kết/đoán dữ liệu entropy thấp.

## 28. Redaction: ưu tiên không thu thập, không chỉ “che sau”

Có ba cấp kiểm soát:

1. **Không thu thập**: code logging chỉ nhận các field allowlist không nhạy cảm.
2. **Validate, phân loại trước khi ghi**: nếu thật sự cần một giá trị từ request, chuyển thành enum/bucket đã kiểm soát; giới hạn độ dài và encoding.
3. **Redaction tại sink/collector**: lớp dự phòng để ngăn lỗi bất ngờ, không phải nguồn bảo vệ duy nhất.

### Vì sao regex đơn lẻ không đủ?

Secrets xuất hiện dưới nhiều biến thể:

~~~text
authorization / Authorization / AUTHORIZATION
X-API-Key / api_key / token / access_token / refreshToken
Cookie / Set-Cookie / session / csrf / _csrf
?code=...&state=...
JSON nested object, base64, URL-encoded, multipart
~~~

Một regex tìm `Bearer ` có thể bỏ sót Basic credentials, signed URLs, custom headers, nested JSON hoặc secrets trong exception. Ngược lại, regex redaction quá rộng có thể phá cấu trúc logs và làm mất diagnostic value.

**Cách đúng:** serializer/schema whitelist mặc định; test với các secrets giả ở nhiều vị trí; collector redaction làm defense-in-depth; audit exporters/tracing/log shipping.

### Đừng hash token rồi ghi như thể hoàn toàn an toàn

Hash không khóa của token/CSRF/session có thể cho phép liên kết hoạt động của người dùng hoặc nhận diện token có entropy thấp. Ngay cả HMAC với khóa bí mật vẫn tạo pseudonymous identifier có yêu cầu retention, key management và quyền truy cập; không mặc định ghi token fingerprint.

Nếu một incident forensic thực sự cần token correlation, phải có **phê duyệt thiết kế riêng**, không làm chuẩn logging của hệ thống.

## 29. Chống log forging và high-cardinality injection

Không nên đưa input tùy ý vào:

~~~java
LOG.warn("invalid route=" + request.getRequestURI());
LOG.warn("trace=" + request.getHeader("X-Request-ID"));
~~~

Vì URL/header do client kiểm soát, chúng có thể chứa ký tự điều khiển, newline hoặc chuỗi cực dài; đặc biệt nguy hiểm khi log collector phân tích log text và tự tạo các fields.

### Cách phòng vệ

- Không log raw user-controlled strings khi không cần.
- Dùng route template/enum do server định nghĩa.
- Nếu buộc phải ghi một giá trị đã review, giới hạn length, charset, validate và dùng structured serialization để escape ký tự điều khiển.
- Không dùng raw Origin, path, token, user ID hoặc request ID làm **metric label**.
- Không dùng exception messages làm tên event.
- Bảo đảm log input không thể thay đổi field `event`, `severity` hay `service` do server xác định.

### Vì sao metrics còn nhạy cảm với cardinality?

Một metric:

~~~text
http_requests_total{path="/users/123456",user="alice"}
~~~

có thể tạo cardinality rất cao và lộ định danh. Ưu tiên:

~~~text
http_requests_total{route="/users/{id}",outcome="4xx"}
~~~

với một danh sách route template hữu hạn. Quy tắc tương tự cho trace span names và dashboards.

## 30. Structured logging: JSON không mặc định bảo đảm riêng tư

JSON logs có lợi vì các fields rõ ràng, nhưng điều đó không có nghĩa chúng đã được sanitize.

**Không nên:**

~~~json
{
  "request": {
    "headers": "<raw headers>",
    "body": "<raw body>",
    "url": "/reset-password?token=<secret>"
  }
}
~~~

**Nên:**

~~~json
{
  "event": "request_rejected",
  "request_id": "eaf6d4c6-3d4b-487a-974b-8835f258c64c",
  "method": "POST",
  "route_template": "/reset-password",
  "status_code": 400,
  "reason": "invalid_request"
}
~~~

### Dữ liệu ngữ cảnh từ framework

Một APM/OTel integration có thể tự thêm `http.url`, `url.full`, `http.target` hoặc exception attributes tùy phiên bản/instrumentation. Cần kiểm tra **dữ liệu được xuất thật** thay vì kết luận vì application log JSON không có query thì trace cũng không có.

**Rà soát tất cả đường xuất dữ liệu:** stdout/files, sidecar logs, metrics, traces, alert webhooks, crash reports, support tickets và dashboard share links.

## 31. Sampling: giảm tải nhưng không biến nó thành cách bảo mật

Với traffic cao, có thể sample logs/traces:

| Loại sự kiện | Gợi ý thu thập | Lưu ý |
|---|---|---|
| Successful normal GET | Metrics tổng hợp + sample traces | Không thu body |
| 401/403 spike | Events tối thiểu theo route group | Không đưa IP/token thành label |
| CSRF rejects | Count theo route/method/reason | Không log CSRF token |
| CORS preflight failures | Count theo policy version và outcome | Không raw Origin hoặc headers |
| Firewall rejects | Count theo rejection category | Không raw malicious URI |
| HSTS/CSP deployment regression | Synthetic checks + sanitized events | Không capture HTML chứa dữ liệu cá nhân |
| Rare serious security event | Audit event có quyền truy cập giới hạn | Không tự động lưu đầy đủ payload |

**Sampling không khử nhạy cảm.** Một record có secret vẫn có thể bị leak dù chỉ giữ 1% request. Trước khi sampling, mọi event phải qua allowlist/minimization.

### Giới hạn kích thước record

Đặt max event size, max field length và giới hạn nested data trước exporter. Không để một user-controlled header khiến log record hàng MB, tạo pressure lên logging queue/collector. Đối với error storms, sử dụng rate limiting và aggregation.

## 32. Retention, access control và dữ liệu nhạy cảm trong log storage

Một hệ thống log an toàn cần:

- **Retention rõ ràng:** diagnostic log lưu vừa đủ điều tra; không kéo dài vô thời hạn.
- **Role-based access:** chỉ người cần vận hành mới truy cập; quyền export/download riêng.
- **Encryption in transit/at rest:** bảo vệ luồng và nơi lưu log.
- **Audit truy cập logs:** ai đọc/export dữ liệu nào; tránh lặp chính nội dung nhạy cảm trong audit.
- **Sửa/xóa theo chính sách:** khi lộ secret, có quy trình truy xuất và xử lý các bản sao/exports.
- **Data residency và tuân thủ:** tùy hợp đồng, quốc gia, ngành và loại dữ liệu; không suy có một TTL chung cho mọi hệ thống.
- **Dashboard guardrails:** không cho truy vấn tùy ý mở rộng phạm vi hoặc link public hóa records.

**Có masking nhưng cho tất cả nhân viên tải toàn bộ logs cũng chưa đủ.** Metadata như request route, request ID, thời điểm và policy decision vẫn có thể tiết lộ hoạt động của hệ thống; phải quản trị quyền truy cập và mục đích sử dụng.

## 33. Bật debug tạm khi có incident: thủ tục có hạn định

Trước khi tăng mức log:

1. Xác nhận có thể tái hiện bằng synthetic traffic trong staging hay không.
2. Liệt kê chính xác logger, instance, route group, sự kiện và thời gian cần.
3. Review rằng framework/custom logger không in secrets khi bật level đó.
4. Dùng canary hoặc instance hạn chế và **không đưa traffic thật nhạy cảm vào test** nếu không cần thiết.
5. Đặt TTL/rollback tự động theo quy trình vận hành; không để TRACE tồn tại sau incident.
6. Kiểm tra actual exported log fields trong collector, không chỉ source config.
7. Phân biệt lỗi framework, gateway và browser bằng request ID, không bật DEBUG toàn hệ thống.
8. Sau khi hoàn tất, hạ level, đánh giá dữ liệu đã sinh ra và cập nhật runbook.

Ví dụ lựa chọn tạm trong staging:

~~~properties
# Dùng cho mục đích minh họa, không phải default production.
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
~~~

**Nếu bản thân TRACE logger có khả năng chứa secrets, phải từ chối cấu hình đó cho production.** Tạo một diagnostic event allowlist an toàn hơn hoặc tái hiện trong môi trường tổng hợp.

### Khi log level thay đổi động

Spring Boot Actuator có thể hỗ trợ quản lý loggers theo cấu hình/version. Nếu expose endpoint thay log level, cần authentication/authorization quản trị và network restrictions. **Không expose endpoint thay log level công khai**; một người không được phép có thể bật debug để tạo rò rỉ dữ liệu hoặc làm giảm hiệu năng.

## 34. Khi log nhạy cảm đã bị ghi: không chỉ xóa dòng trong code

Giả sử phát hiện application/proxy đã ghi Bearer token hoặc session cookie. Các bước ứng phó được tổ chức theo quy trình incident:

1. **Ngăn ghi thêm:** tắt logger/filter/access-log field có lỗi, bảo đảm rollback an toàn.
2. **Xác định phạm vi:** thời gian, services, indexes, exports, alert payload, backups và bên có quyền truy cập.
3. **Đánh giá độ nhạy/khả năng sử dụng lại:** access/refresh token, session ID, OTP, credentials, PII.
4. **Thu hồi/rotate credentials bị ảnh hưởng** khi cần và khả thi, tránh làm lộ chính token trong ticket.
5. **Giới hạn truy cập/quarantine records** theo chính sách, không tiếp tục chia sẻ bản log thô.
6. **Xử lý xóa/retention/bản sao** theo nghĩa vụ pháp lý và vận hành, ghi nhận hành động có kiểm soát.
7. **Thông báo/escalate** theo quy trình security/privacy incident áp dụng.
8. **Thêm regression tests** bảo đảm logging pipeline không còn lưu nhóm dữ liệu đó.

**Không hứa “xóa log là token đã an toàn”.** Token có thể đã được export, cache hoặc người khác truy cập; cần xem xét thu hồi và scope của incident.

## 35. Không sao chép log thô vào ticket, chat hay hệ thống hỗ trợ

Một thói quen nguy hiểm:

~~~text
“Bạn gửi giúp tôi cURL từ browser hoặc toàn bộ request/response HAR để debug.”
~~~

Raw HAR/cURL có thể chứa `Authorization`, Cookie, `Set-Cookie`, token URL, form payload và dữ liệu người dùng. Thay bằng bộ chứng cứ đã lọc:

~~~text
Incident: POST /api/profile returns 403
Request ID: <server-generated-id>
UTC time: <timestamp>
Route template: /api/profile
Security decision: csrf_rejected
CSRF state: missing_or_invalid
Environment/build: staging/build-2026.11
Expected behavior: authorized POST with valid CSRF accepted
Actual behavior: 403; request reached Spring security filter
No token, cookie, body or user identifier attached
~~~

Nếu bắt buộc chuyển tệp HAR/log cho security team, phải qua kênh được phê duyệt, redaction có kiểm chứng và retention/access controls phù hợp. Không xem việc người dùng “đã đồng ý chia sẻ” là lý do bỏ nguyên tắc bảo vệ secrets.

## 36. Kiểm thử Servlet: gắn secret giả và chứng minh logger an toàn

Một phép thử quan trọng không chỉ hỏi “log có request ID không?”, mà còn hỏi: **khi request mang nhiều secrets giả, log output có chứa bất kỳ secret nào không?**

Trong ứng dụng Spring Boot Servlet, có thể kiểm tra riêng logger `SafeHttpRequestLogFilter` bằng Logback `ListAppender`:

~~~java
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

@SpringBootTest
@AutoConfigureMockMvc
class SafeLoggingServletTest {

    @Autowired MockMvc mockMvc;

    @Test
    void neverLogsFakeSecrets() throws Exception {
        String secret = "TEST_SECRET_DO_NOT_LOG_7319";

        Logger logger = (Logger) LoggerFactory.getLogger(
            SafeHttpRequestLogFilter.class
        );
        ListAppender<ILoggingEvent> appender = new ListAppender<>();
        appender.start();
        logger.addAppender(appender);

        try {
            mockMvc.perform(post("/api/profile")
                .queryParam("reset_token", secret)
                .header("Authorization", "Bearer " + secret)
                .header("Cookie", "SESSION=" + secret)
                .header("X-CSRF-TOKEN", secret)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"password\":\"" + secret + "\"}"))
                .andReturn();

            String captured = appender.list.stream()
                .map(ILoggingEvent::getFormattedMessage)
                .collect(Collectors.joining("\n"));

            assertFalse(captured.contains(secret));
            assertTrue(captured.contains("event=http_request_end"));
            assertTrue(captured.contains("request_id="));
            assertTrue(captured.contains("route_template="));
        } finally {
            logger.detachAppender(appender);
            appender.stop();
        }
    }
}
~~~

**Giả định:** test project dùng Logback làm logging implementation, `SafeHttpRequestLogFilter` được đăng ký, có Spring MVC và Spring Security. `post("/api/profile")` có thể trả 403/401/404 tùy fixture; test này **chỉ tập trung output của một logger**, không khẳng định cả hệ thống đã an toàn. Cần cô lập tests nếu chạy song song vì appender gắn vào logger dùng chung.

### Vì sao nên dùng một sentinel giả?

Vì không cần secret thật để kiểm chứng rò rỉ. Chuỗi có format dễ nhận diện giúp assert trên log output. **Tuyệt đối không lấy production token làm test data**.

### Mở rộng test ra toàn logging pipeline

ListAppender trên một logger **không bắt được** access logs Tomcat/Nginx, Reactor Netty wiretap, APM agent, trace exporter hoặc CDN. Với E2E staging test, cần truy vấn những sinks/log exports **được phép** và khẳng định sentinel không xuất hiện ở bất kỳ luồng nào có thể nhận request data.

## 37. Kiểm thử WebFlux: asynchronous logging cũng phải không lộ bí mật

Với Reactive, thử request chứa token giả trong query/header/body rồi kiểm tra event của `SafeReactiveRequestLogFilter`:

~~~java
String secret = "TEST_SECRET_DO_NOT_LOG_7319";

webTestClient.post()
    .uri(uriBuilder -> uriBuilder
        .path("/api/profile")
        .queryParam("reset_token", secret)
        .build())
    .header("Authorization", "Bearer " + secret)
    .header("Cookie", "SESSION=" + secret)
    .header("X-CSRF-TOKEN", secret)
    .contentType(org.springframework.http.MediaType.APPLICATION_JSON)
    .bodyValue("{\"password\":\"" + secret + "\"}")
    .exchange()
    .expectStatus().is4xxClientError();
~~~

Ví dụ giả định route yêu cầu xác thực/CSRF nên response là 4xx. **Cần gắn WebTestClient với application context có WebFilters và security WebFilterChain thật**, không chỉ bind trực tiếp controller.

### Cách assert log Reactive

Dùng một test appender đã cô lập và đồng bộ bằng một completion signal/latch hoặc await mechanism phù hợp, thay vì `Thread.sleep(...)` rồi đoán log đã flush. Kiểm tra:

- Có event `http_request_end` với request ID và method.
- Không có sentinel trong formatted message và structured arguments.
- Không có raw URI/query/header/body được thêm bởi another filter.
- MDC không lẫn ID giữa hai concurrent requests.
- Nếu response bị hủy/cancel, event dùng `signal=CANCEL` hoặc outcome được chuẩn hóa mà không ghi Throwable raw.

**Lưu ý:** kiểm thử WebTestClient chỉ bắt các sinks trong test context; exporter/tracing/edge production vẫn cần regression riêng.

## 38. Negative tests: chống log injection và dữ liệu tràn

Các ca kiểm thử giả lập trong môi trường an toàn:

| Ca | Input tổng hợp | Kết quả mong đợi |
|---|---|---|
| Bearer token ở header | `Authorization: Bearer TEST_SECRET...` | Không có secret trong logs |
| Session cookie | `Cookie: SESSION=TEST_SECRET...` | Không có cookie value |
| CSRF token | `X-CSRF-TOKEN: TEST_SECRET...` | Chỉ có state/reason enum |
| Query token | `?reset_token=TEST_SECRET...` | Không có raw query |
| Path chứa email giả | `/users/user@example.invalid` | Chỉ route template hoặc UNMAPPED |
| JSON password | `{"password":"TEST_SECRET..."}` | Không lưu body |
| Multipart upload giả | File content chứa sentinel | Không log payload hoặc filename nhạy cảm |
| Exception message giả | Exception chứa sentinel | Không log exception text |
| User-Agent với newline | Chuỗi control characters | Không log raw User-Agent, không tạo record giả |
| X-Request-ID cực dài | Nhiều ký tự không chuẩn | Server sinh hoặc reject, không ghi nguyên |
| Client-supplied trace baggage | `baggage: user=...` | Không đưa raw baggage vào log/metric |
| CORS Origin có subdomain PII | `https://user123.example.test` | Log allowed/rejected/policy group |
| CSP report blockedURI có query | URL giả chứa sentinel | Không lưu full blockedURI |
| 401/403/404/500 | Nhiều response paths | Không bypass safe logging |
| Concurrent requests | Nhiều request IDs | Không lẫn metadata/MDC |
| High-rate error burst | Hàng trăm lỗi tổng hợp | Rate limit/sample, không memory explosion |

**Chỉ dùng giá trị giả**, không tạo traffic tới các hệ thống ngoài phạm vi được cấp phép. Khi test 404/400 do parser/firewall, event từ app filter có thể không tồn tại; cần kiểm tra proxy/container sinks.

## 39. Một bộ test về quyết định bảo mật, không cần bí mật

Các phép thử chức năng của Spring Security vẫn phải xác minh đúng kết quả:

### Servlet/MockMvc

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

// Có user nhưng thiếu CSRF -> theo cấu hình Servlet session.
mockMvc.perform(post("/api/profile")
        .with(user("lab-user").roles("USER")))
    .andExpect(status().isForbidden());

// User + CSRF hợp lệ -> endpoint lab trả 204 nếu được cấp quyền.
mockMvc.perform(post("/api/profile")
        .with(user("lab-user").roles("USER"))
        .with(csrf()))
    .andExpect(status().isNoContent());
~~~

### Reactive/WebTestClient

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;

webTestClient.mutateWith(mockUser("lab-user").roles("USER"))
    .post().uri("/api/profile")
    .exchange().expectStatus().isForbidden();

webTestClient.mutateWith(mockUser("lab-user").roles("USER"))
    .mutateWith(csrf())
    .post().uri("/api/profile")
    .exchange().expectStatus().isNoContent();
~~~

Các snippets giả định endpoint demo tồn tại và trả 204 khi hợp lệ; trong dự án thực, phải cấu hình controller/body/auth tương ứng. **Không dùng username production**, và không log principal do test inject. Spring Security test helpers mô phỏng authentication/CSRF; chúng **không chứng minh browser thật đã lấy token và gửi session đúng**.

### Test logs và test chức năng là hai chiều độc lập

Một test `POST no CSRF -> 403` PASS không chứng minh không có secret trong log. Một test log không chứa secret PASS cũng không chứng minh CSRF được bật. **Cần cả test security behavior và test telemetry minimization**.

## 40. Phát hiện secret qua log export: kiểm tra pipeline chứ không chỉ source

Đối với staging với synthetic requests:

~~~text
Synthetic client
  -> HTTPS edge / WAF / gateway
  -> Spring (Servlet hoặc WebFlux)
  -> stdout / file / sidecar / collector
  -> log index / metrics / tracing backend
  -> alert webhook / dashboard / export
~~~

Kiểm tra một chuỗi sentinel giả ở từng destination có quyền truy cập:

1. Application logger.
2. Access log của container/Netty.
3. Edge/CDN/WAF/Gateway logs.
4. APM/traces/spans, baggage/attributes.
5. Error-reporting platform.
6. Alert messages và ticket/workflow tự động.
7. Raw export/data lake/archive/backup theo quy trình.

**Đừng copy raw log export qua chat** để nhờ đánh giá; thay bằng kết quả kiểm thử `sentinel_found=true/false`, vị trí và loại field đã làm sạch.

### Một tiêu chí PASS rõ ràng

> Không xuất hiện bất kỳ sentinel bí mật nào trong những sinks đã liệt kê; các sự kiện vẫn có timestamp, event code, request ID, route template, status và outcome đủ để chẩn đoán; 401/403/CSRF/CORS và các bảo vệ khác vẫn hoạt động.

Nếu một sink chưa kiểm tra được, ghi **NOT VERIFIED**, không đánh dấu toàn hệ thống đạt chuẩn.

## 41. Truy vết một lỗi 403 trong production mà không thu full payload

Giả sử backend nhận POST và trả 403:

~~~text
request_id=req-safe-001
time=2026-11-26T12:20:00Z
method=POST
route_template=/api/profile
status=403
~~~

Runbook có thể tiến hành:

1. Xác định response thực đến từ CDN/WAF, Spring Security hay application.
2. Đối chiếu request ID với gateway log `upstream_reached=true`.
3. Tìm một event `csrf_rejected`, `authorization_denied` hoặc `cors_rejected` do đúng component ghi.
4. Nếu CSRF: xác nhận token **present/missing/invalid** theo diagnostic state; không yêu cầu giá trị.
5. Nếu authorization: xem policy ID và required authority **class**, không dump JWT claims.
6. Nếu CORS: so origin policy outcome với preflight method/header classification.
7. Nếu không có Spring event: điều tra edge/HTTP firewall/container.
8. Tái hiện bằng test credentials/token **tổng hợp**, đo lại sau bản sửa.

**Không yêu cầu người dùng gửi screenshot Cookie/Authorization từ DevTools**. Nếu phiên đăng nhập có thể bị ảnh hưởng, hướng dẫn thu thập request ID/time/status; người vận hành dùng logs đã làm sạch.

## 42. Kịch bản A — Bật DEBUG để tìm CSRF 403 nhưng log cả token

**Hiện tượng:** Sau deploy, `POST /api/profile` trả 403. Developer thêm:

~~~java
// PHẢN VÍ DỤ: có nguy cơ lộ session/CSRF.
log.debug("headers={}", request.getHeaderNames());
log.debug("csrf={}", request.getHeader("X-CSRF-TOKEN"));
log.debug("body={}", requestBody);
~~~

Ghi header names riêng có thể vẫn tiết lộ ứng dụng đang dùng cơ chế gì, nhưng nguy cơ chính ở đây là **giá trị token và body** được ghi không cần thiết.

### Chẩn đoán đủ thông tin

~~~text
event=csrf_rejected
request_id=...
method=POST
route_template=/api/profile
csrf_state=missing
status=403
~~~

Tái hiện bằng MockMvc có và không có `with(csrf())`, xác nhận filter/handler ra quyết định đúng. Tránh lấy token thực để “so có trùng không”; nếu cần phân biệt missing/invalid, dùng enum được cung cấp bởi logic xử lý lỗi trong môi trường test.

**Fix:** bỏ mọi log raw header/body, giữ event reason; kiểm thử sentinel trên logger/collector, không tắt CSRF để làm response 200.

## 43. Kịch bản B — CORS preflight lỗi nhưng người vận hành log Origin và mọi headers

**Hiện tượng:** Browser báo CORS khi frontend staging gọi API. Spring nhận OPTIONS, đôi khi proxy trả 401 hoặc 403.

**Sai lầm:** ghi toàn bộ request headers/response headers, bao gồm Cookie, Authorization và Origin tùy ý, rồi kết luận mọi 403 là lỗi role.

### Chẩn đoán an toàn

~~~text
event=cors_preflight_evaluated
request_id=...
route_group=api
requested_method=POST
origin_policy=rejected
method_policy=accepted
header_policy=accepted
status=403
source=spring_cors_processor
~~~

Nếu status 401 do Basic entry point, ghi:

~~~text
event=authentication_required
request_id=...
method=OPTIONS
chain=api
status=401
~~~

**Fix đúng:** xác minh nơi chặn preflight trước CORS hay CORS processor từ chối hợp lệ. Giữ Origin allowlist, chỉ mở origin/method/header được review; không đưa Cookie/Authorization vào preflight logs hoặc nới wildcard.

## 44. Kịch bản C — Browser CSP chặn script nhưng Spring không có request

**Hiện tượng:** nút trên trang bị vô hiệu sau khi bật CSP, Spring controller không ghi nhận POST.

Nếu browser CSP chặn inline bootstrap script, **không có POST để log**, và không có CSRF rejection của POST. Ghi:

~~~text
event=csp_violation
disposition=enforce
effective_directive=script-src-elem
resource_class=inline_script
page_group=checkout
policy_version=csp-v12
~~~

Không ghi nguyên `document-uri` chứa query, `blocked-uri`, `script-sample` hoặc toàn inline script. Khi dùng nonce, kiểm tra **CSP header và HTML của cùng document response** trong lab; không lưu nonce production vào logs.

**Fix đúng:** sửa nonce/template/policy hoặc script loading, test browser allowed/blocked scripts. Không bật `'unsafe-inline'` chỉ để thấy chức năng chạy lại.

## 45. Kịch bản D — HSTS thiếu sau reverse proxy và log Forwarded thô

**Hiện tượng:** Browser dùng HTTPS public, nhưng Spring `request.isSecure()==false`, HSTS không xuất hiện.

**Sai:** đưa toàn bộ `Forwarded`/`X-Forwarded-*` từ client vào logs và dùng chúng như sự thật, hoặc tự tin header `X-Forwarded-Proto: https` từ bất kỳ nguồn nào.

### Những gì cần đo

~~~text
event=hsts_policy_mismatch
public_tls=true
upstream_transport=http
app_secure_detection=false
hsts_writer_expected=true
response_hsts_present=false
policy_owner=spring
~~~

Các giá trị phải đến từ **nguồn đo và trust boundary được xác minh**, không tin raw client headers. So HTTPS public response, proxy config, Boot forwarded strategy và matching chain.

**Fix đúng:** trusted forwarding hoặc edge-owned HSTS nhất quán; giữ cookie Secure, CSP và CSRF.

## 46. Kịch bản E — HTTP firewall từ chối request trước application filter

**Hiện tượng:** client nhận 400, application logger không thấy event, đội vận hành muốn bật raw request capture.

**Điều tra:**

1. Xác định response 400 do CDN, WAF, container HTTP parser hay Spring `RequestRejectedException`.
2. Tìm sanitized rejection category tại tầng đã từ chối, không yêu cầu raw URL.
3. Nếu request chưa tới Spring, application MDC/filter **không thể** tạo request ID; dùng edge ID.
4. Tái hiện bằng một URL tổng hợp trong lab; dùng test logger category và status.
5. Không giảm `StrictHttpFirewall` hoặc allow malformed path như cách làm hết lỗi log.

Ví dụ record:

~~~text
event=http_request_rejected
source=container_parser
reason_class=invalid_request_target
status=400
edge_request_id=...
~~~

**Không phải mọi 400 là firewall:** controller validation và malformed JSON cũng có thể trả 400. Phải xác định nơi sinh response.

## 47. Kịch bản F — Access log proxy chứa reset token dù Spring logging sạch

**Hiện tượng:** app đã dùng route template và không ghi body, nhưng một external collector vẫn tìm thấy URL reset password có token.

**Nguyên nhân có thể:**

- Nginx/Apache access log dùng raw request line.
- CDN log full URL/query.
- Tracing auto-instrumentation ghi `url.full` hoặc `http.target`.
- Alert gửi raw exception message kèm URL.
- HAR export của customer support mang query.

**Fix:** rà ở **tầng tạo record** và exporter; thay raw URL bằng route group, strip query/route params, điều chỉnh trace semantic fields theo instrumentation version, rồi chạy E2E synthetic sentinel test. Nếu token thật đã vào logs, thực hiện quy trình incident và revocation theo mức độ.

Không tuyên bố logging an toàn chỉ vì test unit của Spring filter đã PASS.

## 48. Kịch bản G — Concurrent WebFlux requests trộn MDC

**Hiện tượng:** hai requests khác nhau có cùng request ID trong một vài downstream logs, dù gateway IDs đúng. Một custom WebFilter dùng mutable singleton hoặc raw MDC mà không propagation/cleanup.

**Nguyên nhân:** Reactor có thể đổi threads giữa publishers; `ThreadLocal` không tự tương ứng với exchange lifetime. Nếu MDC bị bỏ lại trên event loop thread, một request khác có thể kế thừa metadata.

### Cách sửa

- Sinh ID theo exchange, lưu vào `ServerWebExchange` attribute hoặc Reactor Context.
- Dùng Micrometer/OTel context propagation được cấu hình đúng, không tự gắn token vào ThreadLocal.
- Dọn MDC theo lifecycle và scheduler/thread boundaries nếu có custom integration.
- Test nhiều concurrent requests, cancellation, error và timeout.
- Không dùng session ID làm correlation ID để “giữ ổn định”.

Một log bị trộn request ID không chỉ gây khó debug; nó có thể khiến audit/forensic kết luận sai về hoạt động người dùng.

## 49. Bảng chẩn đoán theo nơi thiếu hoặc rò dữ liệu

| Triệu chứng | Nguồn khả dĩ | Phép thử ngắn |
|---|---|---|
| App 403, chỉ thấy generic log | Thiếu event classifier | Ghi CSRF/authz/CORS reason enum |
| Log chứa Bearer dù code logger sạch | Framework TRACE, proxy, APM | Synthetic secret qua toàn pipeline |
| Token lộ ở URL trong access log | Raw request line/query | Thay access-log pattern và source field |
| Cookies xuất hiện trong traces | Instrumentation HTTP headers capture | Rà span attributes và exporter |
| CSP report chứa token ở query | Raw document/blocked URI | Collector allowlist + remove URL query |
| Không có Spring event, browser nhận 403 | Edge/WAF đã chặn | So edge request ID/upstream reached |
| HTTP 400 không có Spring log | Container parser/firewall trước app | Sanitized parser/edge logs |
| 401 nhưng log nói bad password | Phân loại authentication sai | Entry point/mechanism enum |
| Request ID user chèn newline | Tin raw X-Request-ID | ID server-side, validate ingress |
| WebFlux logs lẫn request IDs | MDC ThreadLocal sai | Reactor Context/concurrency test |
| Tăng TRACE gây spike logs | Debug quá rộng, no sampling | Logger cụ thể/TTL/incident review |
| App log không có Origin nhưng CDN log có | Edge policy riêng | Audit CDN fields/retention |
| Tracing baggage có email | Baggage keys không allowlist | Loại/giới hạn metadata |
| Metrics có hàng triệu labels | Raw path/user IDs | Route templates và enums |
| Access log không có route template | Container trước Spring MVC mapping | Dùng application structured event riêng |
| 500 logs đầy stacktrace có body | Raw exception logging | Sanitized error code + controlled diagnostics |
| Lộ secret qua alert webhook | Alert dùng raw log message | Sanitized event schema và webhook payload |
| Log đã bị chia sẻ ngoài nhóm | Access/export controls thiếu | Incident process và rotation nếu cần |

### Khi nào cần thông tin nhận dạng người dùng?

Một số kiểm toán có thể đòi subject linkage. Điều này **không hợp thức hóa logging trực tiếp session token**. Cần thiết kế data classification riêng: stable pseudonymous identifier nếu thực sự cần, khóa/rotation, retention và access controls; cân nhắc data privacy obligations. Với chẩn đoán một lỗi CSRF/CORS, thường không cần thông tin ấy.

## 50. Runbook chẩn đoán tám bước mà không ghi secrets

~~~mermaid
flowchart TD
    A[HTTP/browser security incident] --> B[Xác định request ID và public outcome]
    B --> C{Spring có nhận request?}
    C -- Không --> D[CDN/WAF/proxy/parser sanitized event]
    C -- Có --> E[Route template, selected chain, decision enum]
    E --> F{Lỗi loại nào?}
    F --> G[401 auth; 403 authz/CSRF/CORS; 400 firewall]
    F --> H[CSP/HSTS/header/session/browser]
    G --> I[Reproduce với credentials/token tổng hợp]
    H --> I
    D --> I
    I --> J[Test security behavior và log leakage]
    J --> K[Fix nhỏ nhất và verify all telemetry sinks]
~~~

### Bước 1 — Xác định triệu chứng, không xin request dump

Thu thập UTC timestamp, HTTP method, public hostname/path **theo route group**, status, user-visible error và request ID **do server/edge tạo**. Không yêu cầu người dùng gửi credentials, raw HAR hoặc screenshot Cookie từ DevTools.

### Bước 2 — Xác định nơi tạo response

Browser CSP có thể chặn trước network; gateway/WAF có thể chặn trước Spring; Spring Security có thể chặn trước controller. So public response, edge upstream status và Spring event. Đừng bật DEBUG tất cả services chỉ vì thiếu app log.

### Bước 3 — Xác định lớp bảo vệ theo event

Ưu tiên:

- 401: authentication mechanism/entry point.
- 403: CSRF, authorization, CORS processor hoặc edge rule.
- 400: input validation, parser hoặc firewall.
- Browser CSP: directive, disposition, policy version.
- HSTS/CSP header mismatch: HTTPS public response, proxy/chain/policy owner.

Chỉ lưu **reason class** có tập giá trị cố định; không lưu token, user ID/raw URL để phân loại.

### Bước 4 — Liên kết các hops an toàn

Dùng request/trace IDs đã kiểm soát. Nếu ID từ client không được trust, tạo mới tại edge hoặc app; với hệ thống phân tán, có mapping giữa IDs và trace context. Không lưu `Cookie` hay token hash làm “correlation key”.

### Bước 5 — Tái hiện bằng dữ liệu tổng hợp

Tạo synthetic token/cookie/body có sentinel trong staging, test OPTIONS/POST/login/CSRF/CORS và browser CSP. Không dùng production secrets hay raw customer requests để tái hiện.

### Bước 6 — Thu logs tối thiểu ở đúng nơi

Ghi event code, route template, status, policy/chain version, timestamps và latency. Nếu cần tăng log level, giới hạn logger, instance, thời gian, dữ liệu và review output. Không bật toàn HTTP body/wiretap.

### Bước 7 — Test cả chức năng lẫn logging

Security behavior phải đúng: anonymous request bị từ chối khi cần; CSRF token hợp lệ được chấp thuận; Origin không hợp lệ vẫn bị CORS từ chối. Đồng thời **không sentinel secret nào xuất hiện** trong logs/metrics/traces/alerts/export thuộc phạm vi kiểm tra.

### Bước 8 — Bàn giao và thu hồi debug

Hạ log level, đóng quyền tạm thời, lưu sanitized incident summary, retention và evidence scope. Nếu có bất kỳ credentials thật nào đã vào logs, kích hoạt security/privacy incident procedure; không tuyên bố xong chỉ vì code đã đổi.

## 51. Anti-pattern: những thói quen logging làm rủi ro lớn hơn sự cố

| Cách làm sai | Rủi ro | Hướng đúng |
|---|---|---|
| `log.info("request={}", request)` | Wrapper/toString có thể chứa input | Schema allowlist, route template |
| In tất cả request headers | Bearer, Cookie, CSRF/API key | Policy outcome và header presence enum |
| In body để tìm CSRF | Password, dữ liệu cá nhân, upload | Reason class của CSRF filter |
| Ghi response body lỗi 4xx/5xx | Thông tin người dùng, stack trace | Sanitized error code/status |
| Log `SecurityContext`/Authentication object | Principal/credentials/details | Event code và mechanism |
| Ghi `Exception.getMessage()` ở mọi lỗi | URL/query, rejected values | Enum/class allowlist |
| Log raw URL query | OAuth code/state, reset token | Route template hoặc route group |
| Bật `logging.level.root=TRACE` toàn prod | Không kiểm soát volume và dữ liệu | Logger cụ thể có TTL |
| Bật HTTP body wiretap Netty | Streaming payload và secrets | Reactive safe event metadata |
| Dùng session cookie làm correlation ID | Tiết lộ session và linkability | Random request ID |
| Tin raw client `X-Request-ID` | Log forging, input injection | Generate/validate tại trust boundary |
| Gắn userId/path raw vào metrics | High cardinality, PII | Route template và fixed labels |
| Đưa raw CSP report vào analytics | Sensitive URLs/code samples | Schema allowlist và privacy filtering |
| Copy HAR vào ticket công khai | Secrets/PII trong headers/body | Sanitized evidence |
| Regex scrub sau khi log đã được gửi | Một sink có thể đã nhận secret | Không thu thập ngay tại source |
| Hash JWT/token rồi lưu dài hạn | Linkability và token fingerprint risk | Không lưu token-derived IDs mặc định |
| Dùng DEBUG để chứng minh role thiếu | Framework có thể ghi identity | Authorization reason class |
| Bật Actuator loggers public | Attacker có thể kích hoạt TRACE | Authenticated admin-only access |
| Tắt CSRF/CORS/firewall để giảm log error | Mất bảo vệ HTTP/browser | Sửa policy/config đúng lớp |
| Giữ log “đề phòng” vô thời hạn | Tăng phạm vi rò rỉ và nghĩa vụ dữ liệu | Retention theo mục đích |
| Chỉ test app logs | Bỏ sót CDN/WAF/tracing exports | E2E telemetry sentinel tests |
| Bỏ log hoàn toàn để không lộ gì | Mất khả năng phát hiện sự cố | Event tối thiểu không chứa secrets |

**Mục tiêu không phải “không có log”.** Mục tiêu là **khả năng giải thích mỗi quyết định bảo mật bằng dữ liệu ít nhất**, đủ cho triage, kiểm thử và vận hành mà không tạo kho credentials thứ hai.

## 52. Bài thực hành tổng hợp: xây dựng secure diagnostics cho Servlet và WebFlux

### Môi trường lab

Tạo hai biến thể Spring Boot độc lập:

~~~text
Servlet:
  GET  /api/public/ping
  GET  /api/private
  POST /api/profile       (session + CSRF trong lab)

Reactive:
  GET  /api/public/ping
  GET  /api/private
  POST /api/profile       (reactive security)

Hạ tầng:
  HTTPS staging reverse proxy/WAF giả lập
  Collector/test sink cho logs + traces
  Browser automation trong môi trường kiểm soát
~~~

Đây là môi trường và đường dẫn **minh họa**, không phải các endpoints đang tồn tại. Chỉ dùng tài khoản/test credentials và synthetic payloads.

### Nhiệm vụ bắt buộc

1. **Thiết kế schema:** định nghĩa event codes cho authentication required, authorization denied, CSRF rejected, CORS preflight rejected, request rejected và header policy mismatch.
2. **Servlet:** thêm `SafeHttpRequestLogFilter` hoặc cách instrument tương đương, chỉ ghi request ID, method, route template, status/duration.
3. Dùng MDC request ID với cleanup trong `try/finally`; chứng minh hai requests liên tiếp không bị lẫn ID.
4. **Reactive:** dùng `SafeReactiveRequestLogFilter` với exchange attribute/Reactor Context; test concurrent requests và cancellation.
5. **Auth/CSRF:** xác minh GET private anonymous bị chặn, POST thiếu CSRF bị 403 trong flow lab, POST hợp lệ được xử lý; event chỉ có reason class.
6. **CORS:** gửi OPTIONS đúng Origin và Origin không được cấp phép. Event phải phân biệt policy rejection với authentication chặn sớm.
7. **HTTP firewall:** dùng một request URL bất thường tổng hợp trong Servlet lab; nếu container chặn trước app, tìm sanitized edge/container event thay vì đòi log Spring.
8. **CSP:** tạo violation từ một script inline thiếu nonce trong browser lab, thu `effectiveDirective`/`disposition` mà không lưu nguyên document URL/query.
9. **HSTS:** cho TLS termination sau proxy; đo public HTTPS STS và secure-detection state, không log toàn `Forwarded` headers.
10. **Access logs:** bật Tomcat log pattern an toàn (nếu Servlet dùng Tomcat); kiểm tra proxy/CDN logging fields không chứa query.
11. **Sentinel test:** gửi cùng chuỗi giả vào Bearer, Cookie, CSRF header, query và body. Assert không xuất hiện trong logs/appender/tracing export.
12. **Log injection:** gửi X-Request-ID với newline/chuỗi dài, User-Agent và custom header giả; kiểm tra không tạo records giả.
13. **Metrics labels:** đo 401/403 theo route template và outcome; không có user ID, raw path, token fingerprint.
14. **Trace:** bảo đảm trace ID hợp lệ được liên kết qua gateway, không propagate raw baggage nhạy cảm.
15. **Incident drill:** tạm tăng một logger đúng phạm vi trong staging, sau đó tắt và xác minh collector fields.
16. **Bàn giao:** lập bảng các sources/sinks đã kiểm tra, policy retention/access và các chỗ còn `NOT VERIFIED`.

### Bảng nghiệm thu

| Tiêu chí | PASS khi |
|---|---|
| CSRF 403 được chẩn đoán | Có event `csrf_rejected` không chứa token |
| Authentication/authorization phân biệt | Có reason/entry point class phù hợp |
| CORS preflight diagnosis | Có origin/method/header allowlist outcome, không raw headers |
| HTTP firewall/edge rejection | Tìm được nguồn rejection và sanitized category |
| CSP/HSTS diagnosis | Có policy version và status/secure flag, không raw URL/query |
| Request correlation | Request ID ngẫu nhiên, không phải cookie/client raw value |
| MVC route representation | Route template hoặc `UNMAPPED`, không user path |
| WebFlux propagation | Concurrent requests không lẫn context |
| Token sentinel | Không ở bất kỳ sink đã kiểm tra |
| Logging controls | Có TTL, role-based access, retention |
| Security regression | 401/403/CSRF/CORS/firewall vẫn hoạt động đúng |
| Reporting | Tickets chỉ chứa sanitized evidence; gap nêu rõ |

### Mẫu kết quả sự cố

~~~text
Incident type: CSRF rejection spike
Environment: staging
Time range (UTC): 2026-11-26 12:00–12:15
Service: SPRING_SECURITY_HTTP_PROTECTION
Route group: account_api
Affected operation: POST /api/profile
Event code: csrf_rejected
Observed status: 403
Observed count: synthetic test 12
Correlation: server-generated request IDs
Sensitive material collected: none
All test sinks checked: application, proxy, trace, alert
Unverified sinks: none in this lab
Remediation: restore browser CSRF token bootstrap
Post-fix behavior: valid CSRF -> expected success; invalid -> 403
Log-leakage regression: PASS
~~~

**Không copy nguyên bản mẫu số liệu này vào báo cáo sự cố thực.** Nó chỉ mô tả cấu trúc phù hợp và các giá trị giả dùng cho lab.

## 53. Câu hỏi tự đánh giá

1. Những thông tin nào đủ để chẩn đoán CSRF 403 mà không cần token?
2. Tại sao `request.getRequestURI()` có thể nhạy cảm dù không chứa query string?
3. Route template khác raw path như thế nào khi một URL chứa user ID?
4. Nếu security filter từ chối trước controller, phải làm gì khi chưa có route template?
5. Vì sao ghi toàn bộ `Authorization` và Cookie nguy hiểm, kể cả khi DEBUG chỉ bật vài phút?
6. Tại sao một số client headers như Origin/Referer/User-Agent vẫn cần review trước khi log?
7. Request ID do client gửi có thể gây log forging như thế nào?
8. Vì sao request ID không phải session ID và không được dùng làm authorization?
9. Dùng MDC trong Servlet cần cleanup như thế nào?
10. Vì sao raw MDC ThreadLocal không phù hợp mặc định với WebFlux Reactor?
11. `ServerWebExchange` attributes và Reactor Context giúp bảo đảm điều gì?
12. Nếu `doFinally` thấy status UNKNOWN, có nên tự bịa HTTP status cuối không?
13. Vì sao bật framework TRACE không đồng nghĩa logs đã sanitized?
14. Một HTTP 403 có thể đến từ những tầng nào?
15. Nếu WAF trả 403 trước Spring, nên tìm event ở đâu?
16. CSP violation report có thể chứa loại thông tin nhạy cảm nào?
17. HSTS thiếu sau proxy có thể chẩn đoán qua các cờ nào mà không ghi raw Forwarded?
18. Tại sao CORS preflight không cần Cookie/Authorization values để điều tra?
19. Access logs mặc định có thể làm lộ reset/OAuth tokens ở đâu?
20. Vì sao `Logback ListAppender` test trên một class không chứng minh toàn logging pipeline an toàn?
21. Synthetic secret sentinel nên được chèn vào những vị trí nào?
22. Làm sao kiểm thử concurrent WebFlux requests không bị lẫn request IDs?
23. Tại sao hash token thường không phải giải pháp logging mặc định tốt?
24. Một regex redact đơn giản có thể bỏ sót bí mật như thế nào?
25. High-cardinality metrics labels liên quan PII và hiệu năng như thế nào?
26. Sampling có khiến một log chứa secret trở nên an toàn không?
27. Retention và RBAC có vai trò gì ngay cả khi logs đã được sanitize?
28. Nếu token thật đã bị ghi vào SIEM, hành động cần làm ngoài sửa code là gì?
29. Vì sao không nên yêu cầu người dùng gửi raw HAR/cURL để chẩn đoán?
30. Những tiêu chí nào cần PASS để tuyên bố hệ thống có security diagnostics an toàn?

## 54. Ghi nhớ

**Thu thập log cần thiết mà không ghi token hay nội dung nhạy cảm** là việc thiết kế observability theo **allowlist metadata**: request/trace ID, event code, route template, method, status, duration, selected security chain và decision reason. Để chẩn đoán 401/403, CSRF, CORS/preflight, HTTP firewall, CSP, HSTS và session, không cần ghi mật khẩu, Bearer token, Cookie/Set-Cookie, CSRF token, raw URL/query, request/response body hoặc Authentication/Exception objects.

Trong **Servlet**, dùng request-scoped correlation và MDC có cleanup, hiểu giới hạn của `HeaderWriterFilter`/`FilterChainProxy`, MVC handler mapping, filter registration và servlet async. Trong **Reactive/WebFlux**, dùng `ServerWebExchange`/Reactor Context hoặc context propagation đã kiểm thử; không tin ThreadLocal MDC tự đi qua mọi event-loop thread. Cả hai cần events an toàn ở nơi ra quyết định, không chỉ broad DEBUG/TRACE logs.

**Security logging là bài toán toàn đường đi:** browser → CDN/WAF/gateway → HTTP parser/container → Spring Security → application → logs/metrics/traces/APM/alerts/exports. Một secret có thể không xuất hiện trong application logger nhưng vẫn bị lưu tại access log, CSP report, tracing attributes hoặc ticket. Dùng synthetic sentinel tests, retention/access controls và incident process để kiểm chứng thực tế.

Trong `SPRING_SECURITY_HTTP_PROTECTION`, bản sửa được coi là tốt khi người vận hành **nhìn rõ lớp phòng vệ nào từ chối request** mà không cần thu thập bí mật, đồng thời authentication, authorization, CSRF, CORS, security headers/CSP/HSTS, HTTP firewall và session protections **vẫn giữ nguyên hiệu lực**.
