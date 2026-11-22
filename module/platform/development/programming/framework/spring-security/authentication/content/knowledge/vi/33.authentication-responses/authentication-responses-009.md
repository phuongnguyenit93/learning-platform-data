# Mã lỗi công khai, mã tương quan và thông tin chi tiết chỉ dành cho vận hành

## 1. Mục tiêu và nguyên tắc cốt lõi

Một người dùng đăng nhập thất bại trên ứng dụng Spring Security. Phía trình duyệt cần hiểu phải thử lại, đăng nhập, thực hiện xác thực mạnh hơn hay liên hệ hỗ trợ. Nhân viên vận hành cần biết chính xác lỗi liên quan đến tài khoản không tồn tại, khóa mật khẩu, JWKS không truy cập được, cơ sở dữ liệu quá tải hay policy bị từ chối. **Hai bên không được nhận cùng mức độ thông tin.**

Thiết kế đúng phân thành ba lớp:

1. **Mã lỗi công khai (public error code):** tên ổn định, giới hạn và an toàn để client viết logic xử lý; ví dụ `AUTH_FAILED`, `AUTH_REQUIRED`, `ACCESS_DENIED`. Không tiết lộ lý do nhạy cảm.
2. **Mã tương quan (correlation/request ID):** định danh opaque dùng để tìm đúng một request trong log/trace mà không cần gửi stack trace cho user. Có thể trả trong header `X-Request-ID` và body `requestId`.
3. **Thông tin chỉ dành cho vận hành:** loại exception thực, hệ thống phụ thuộc, failure stage, trace/span, server instance, kết quả xác minh JWT/MFA, reason code nội bộ, metrics và audit. Chúng ở **logs/traces được kiểm soát truy cập**, không được copy ra JSON công khai.

Trong Spring Security, xử lý response của bước xác thực có thể diễn ra **trước khi request đi vào Spring MVC controller**, nên chỉ viết `@RestControllerAdvice` là chưa đủ. Cần biết `AuthenticationFailureHandler`, `AuthenticationEntryPoint`, `AccessDeniedHandler`, và với Bearer API phải tôn trọng `WWW-Authenticate` theo RFC 6750.

### Sau bài học có thể làm gì?

- Tách code public khỏi error reason nội bộ và thiết kế danh mục code có versioning.
- Chọn đúng HTTP status `400/401/403/429/503` và không biến tất cả lỗi thành 401.
- Tạo request ID an toàn, ghi cùng ID vào response và structured logs; hiểu khác biệt giữa request ID với distributed trace ID.
- Áp dụng RFC 9457 `application/problem+json` cho API, bảo toàn semantics của OAuth2 Bearer challenge.
- Cấu hình Spring Security Servlet cho form login failure, protected API chưa xác thực và authenticated-but-forbidden.
- Phòng user enumeration, disclosure của token/PII, log injection và rò chi tiết vận hành.
- Viết Java 17 runnable demo và bộ test hành vi công khai/quan sát nội bộ.

**Phạm vi:** Spring Boot 3.x, Spring Security Servlet 6.x, Java 17+. Các đoạn Spring framework là ví dụ tích hợp minh họa cần dependencies/configuration phù hợp; riêng chương trình Java 17 thuần ở mục 7 có thể biên dịch bằng `javac` mà không cần Spring.

## 2. Hợp đồng phản hồi: public code, requestId và private diagnostics

Một response API cho đăng nhập thất bại có thể dùng RFC 9457:

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/problem+json
Cache-Control: no-store
X-Request-ID: c1d4e9f5-9fcb-48d2-9e2c-1037560fd229

{
  "type": "https://api.example.test/problems/authentication-failed",
  "title": "Authentication failed",
  "status": 401,
  "detail": "Thông tin đăng nhập không hợp lệ.",
  "instance": "urn:uuid:c1d4e9f5-9fcb-48d2-9e2c-1037560fd229",
  "code": "AUTH_FAILED",
  "requestId": "c1d4e9f5-9fcb-48d2-9e2c-1037560fd229"
}
~~~

Đây là **hợp đồng do ứng dụng tự thiết kế**, không phải body mặc định của mọi Spring Security filter. `type` là URI định danh loại lỗi; `title` và `detail` chỉ chứa thông tin an toàn; `status` nhất quán với HTTP status. `code` và `requestId` là **extension fields** theo RFC 9457. `instance` là URI reference cho một occurrence; ví dụ dùng UUID URN không chứa path/query nhạy cảm. Không đưa giá trị token, email, username hoặc SQL path vào `instance`.

**Lưu ý quan trọng:** mẫu trên dành cho **form login/JSON login**. Với OAuth2 Resource Server, request thiếu Bearer token thường phải có header `WWW-Authenticate: Bearer ...`; tham số `error` trong challenge do RFC 6750 quy định và **không trùng** tên mã lỗi business `AUTH_FAILED`.

### Ba lớp dữ liệu thực tế

| Dữ liệu | Gửi cho client? | Lưu logs/traces? | Ghi chú |
| --- | --- | --- | --- |
| HTTP status | Có | Có | Semantics chuẩn, không dùng 200 cho lỗi đăng nhập chỉ để ẩn nguyên nhân |
| Public code `AUTH_FAILED` | Có | Có | Tên ổn định để client xử lý |
| Text `"Thông tin đăng nhập không hợp lệ"` | Có | Có thể | Không nêu account tồn tại, password sai hay bị khóa |
| `requestId` opaque | Có | Có | Không chứa PII, không làm credential |
| `traceId`, `spanId` | Có thể, theo policy | Có | Cho observability/distributed tracing, không bắt buộc phơi ra |
| `BadCredentialsException` class | Không | Có, đã phân loại | Chi tiết kỹ thuật cho vận hành |
| `UsernameNotFoundException` | Không | Chỉ khi cần, được hạn chế | Có nguy cơ lộ việc tồn tại tài khoản |
| `user_id`/email/IP/User-Agent | Không tự lặp trong body | Hạn chế, có policy bảo vệ | PII, không gắn trực tiếp làm request ID |
| Giá trị password, OAuth code, Bearer token, cookie | **Không** | **Không** | Credential phải được redact; không lưu nguyên văn |
| DB connection string, host nội bộ, stack trace | Không | Có kiểm soát tùy sự cố | Giới hạn truy cập/retention |
| Thời gian dự đoán account unlock hoặc trạng thái khóa | Thận trọng | Có thể trong security audit | Có thể là user-enumeration side channel |

Một request ID **chỉ để tìm** sự kiện; nó không thay thế bằng chứng xác thực, OTP hoặc quyền xem log. Một user biết `requestId` không được cấp quyền đọc stack trace của người khác.

## 3. Danh mục mã lỗi công khai có chủ đích

Public code cần **ổn định qua refactor nội bộ**, có tài liệu và phân loại retry rõ ràng. Không gửi Java class name, SQLSTATE, tên microservice hoặc lý do mật khẩu/lockout chi tiết thành code public.

| HTTP | Public code ứng dụng | Client nên hiểu | Private reason có thể khác nhau |
| --- | --- | --- | --- |
| 401 | `AUTH_REQUIRED` | Cần xác thực trước khi gọi protected endpoint | Không có cookie/session/Bearer |
| 401 | `AUTH_FAILED` | Đăng nhập không thành công, không phân biệt tài khoản | UNKNOWN_USER, BAD_PASSWORD, ACCOUNT_LOCKED, BAD_MFA (theo threat model) |
| 401 | `INVALID_ACCESS_TOKEN` | Bearer credential không hợp lệ; lấy token mới đúng flow | JWT_SIGNATURE, EXPIRED, BAD_AUDIENCE, REVOKED |
| 403 | `ACCESS_DENIED` | Đã xác thực nhưng không đủ quyền hoặc policy từ chối | MISSING_SCOPE, DENIED_BY_ACL, TENANT_MISMATCH |
| 400 | `INVALID_AUTH_REQUEST` | Cú pháp/yêu cầu xác thực không hợp lệ | MALFORMED_BEARER_HEADER, INVALID_PARAMETER |
| 429 | `AUTH_RATE_LIMITED` | Gửi yêu cầu quá nhanh; đợi theo chính sách | IP_LIMIT, DEVICE_LIMIT, IDENTITY_LIMIT |
| 503 | `AUTH_SERVICE_UNAVAILABLE` | Dịch vụ xác thực tạm thời không sẵn sàng | IDP_TIMEOUT, DB_OUTAGE, JWK_PROVIDER_UNAVAILABLE |
| 500 | `INTERNAL_ERROR` | Sự cố không thể xử lý hiện tại | BUG, MISCONFIGURATION, SERIALIZATION_FAILURE |

Mọi mã ở bảng là **ví dụ policy của ứng dụng**, không mặc định được Spring sinh ra. Nếu client đang dùng chuẩn OAuth/OIDC, phải giữ code chuẩn ở protocol surface; `invalid_token` và `insufficient_scope` là Bearer challenge values do RFC quy định, khác danh mục extension JSON của ứng dụng.

**Không đánh đồng 401 và 403:** 401 nghĩa credential thiếu/không hợp lệ (HTTP authentication semantics); 403 thường nghĩa request đã xác thực nhưng không đủ quyền. Với browser form login, Spring có thể redirect (302) tới trang login thay vì JSON 401, tùy UX. Không ép UI HTML phải trả JSON khi nó cần redirect. Với OAuth2/OIDC `authorization endpoint` hoặc `token endpoint` do nhà cung cấp kiểm soát, protocol error format có quy tắc riêng.

**Không quy mọi exception thành `AUTH_FAILED 401`:** upstream IdP/JWKS hoặc database hỏng là lỗi khả dụng có thể cần 503/5xx và alert nội bộ. Chuyển chúng thành 401 khiến client lặp đăng nhập vô ích, tạo thêm tải và che mất outage.

### Versioning public code

- Mỗi public code có tên, semantics, HTTP status, action cho client, chủ sở hữu và mức độ nhạy cảm.
- Thêm code mới theo quy trình API versioning; client phải có fallback dựa trên HTTP status khi gặp code lạ.
- Không cho client parse `message/detail` để quyết định flow: văn bản có thể địa phương hóa và chỉnh UX.
- Không tạo public code riêng `USER_NOT_FOUND`, `PASSWORD_INCORRECT`, `TOTP_NOT_ENROLLED` ở endpoint anonymous nếu việc phân biệt có thể giúp dò tài khoản.
- Đối với phiên **đã xác thực** và đã qua step-up, có thể công khai code đủ cụ thể như `REAUTH_REQUIRED` hay `MFA_ENROLLMENT_REQUIRED` khi có lợi cho UX và không tiết lộ tình trạng của tài khoản khác.
- Tránh đưa `exception.getMessage()` trực tiếp vào `detail`; nội dung exception không phải hợp đồng public và có thể chứa PII/secrets.

## 4. Ngữ nghĩa HTTP và Bearer WWW-Authenticate

### Form login và API dùng session

Một request `POST /login` với username không tồn tại, password sai, account locked hoặc credential không hợp lệ nên dùng một thông báo công khai **như nhau** khi chưa xác thực, theo chính sách chống user enumeration. Spring Security có thể 302 redirect tới `/login?error` cho HTML browser, hoặc failure handler có thể trả 401 JSON cho AJAX login.

Một request đến protected resource khi chưa có authentication đi qua `AuthenticationEntryPoint`: browser có thể nhận redirect login, REST API thường 401. Còn request đã authenticated nhưng thiếu role/authority đi qua `AccessDeniedHandler`, thường 403. `@RestControllerAdvice` không xử lý mọi lỗi từ security filter chain vì nhiều trường hợp bị chặn **trước DispatcherServlet**.

### OAuth2 Resource Server — không phá protocol khi thêm JSON

RFC 6750 quy định response Bearer challenge. Một số mẫu:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="api"
X-Request-ID: c1d4e9f5-9fcb-48d2-9e2c-1037560fd229
~~~

Không có credential: `WWW-Authenticate` nên xuất hiện nhưng không cần `error=...` vì có thể gây tiết lộ thông tin không cần thiết.

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
X-Request-ID: c1d4e9f5-9fcb-48d2-9e2c-1037560fd229
~~~

Token expired, malformed, revoked hay chữ ký sai có thể cùng sử dụng `invalid_token`. Đừng phát `JWT_SIGNATURE_INVALID_FOR_TENANT_ACME` ra công khai. RFC cho phép thêm `error_description` trong trường hợp thích hợp, nhưng không nên đưa chi tiết secrets/claims/user identity.

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
X-Request-ID: c1d4e9f5-9fcb-48d2-9e2c-1037560fd229
~~~

`insufficient_scope` là protocol error cho trường hợp thiếu scope phù hợp. Với access-denied do business ACL (ví dụ user A đọc tài nguyên của user B) không nhất thiết nên trả kèm scope cụ thể: có thể làm lộ chính sách hoặc sự tồn tại của tài nguyên. Quyết định `403` hay `404` theo threat model và kiểm soát IDOR.

Spring Security có `BearerTokenAuthenticationEntryPoint` và `BearerTokenAccessDeniedHandler` hỗ trợ status/challenge; khi cần JSON custom hãy **delegate** cho chúng để giữ `WWW-Authenticate` thay vì trả Map JSON và quên header. Các handler của Spring có thể nhận `BearerTokenError` và chọn HTTP status tùy giao thức, ví dụ malformed Bearer header đôi khi là 400, không nên giả định mọi request không hợp lệ đều 401.

### Tự động retry có rủi ro

`401 invalid_token` thường có thể dẫn client đi xin **access token mới** theo OAuth flow; không có nghĩa browser phải gửi lại password vô hạn. `403` không nên tự động refresh Bearer rồi thử mãi khi thiếu scope. `429` cần rate-limit handling, cân nhắc `Retry-After` nếu không tạo side channel. `503` cần exponential backoff/circuit breaker, không biến thành credential stuffing.

## 5. Chống rò rỉ qua phản hồi và timing

OWASP khuyến nghị dùng **generic authentication error messages**. Người dùng không đăng nhập không được suy ra account tồn tại, mật khẩu sai, tài khoản bị disable/locked hay chính xác số lần còn lại.

Ví dụ không an toàn:

~~~json
{
  "code": "USER_NOT_FOUND",
  "message": "Không có người dùng alice@example.test",
  "userId": null,
  "sql": "select * from users where email=..."
}
~~~

Ví dụ an toàn hơn:

~~~json
{
  "code": "AUTH_FAILED",
  "message": "Thông tin đăng nhập không hợp lệ.",
  "requestId": "c1d4e9f5-9fcb-48d2-9e2c-1037560fd229"
}
~~~

**Cùng body chưa đủ:** HTTP status khác nhau, response length/redirect, header, cache behavior và độ trễ khác nhau có thể vẫn làm lộ account existence. Nếu user không tồn tại được từ chối tức thì còn user tồn tại chạy một phép hash mật khẩu tốn thời gian, attacker có thể đo; dùng cách xác thực phù hợp (ví dụ dummy hash comparison), rate limiting, giám sát và phân tích timing cho threat model.

Các ràng buộc nội dung:

- Không trả stack trace, exception class, source file, line number, SQL query, token claim chi tiết hoặc tên host/private IP.
- Không echo raw header `Authorization`, `Cookie`, request body mật khẩu/OTP, OAuth authorization code, refresh token, recovery code hoặc MFA seed.
- Không đưa username/email/userId nhạy cảm vào mã tương quan: request ID nên opaque và không có ý nghĩa danh tính.
- Nếu dùng `traceId` từ request header công khai, phải kiểm tra format, độ dài và trust boundary; không coi chuỗi tùy ý do client gửi là ID mà server xác minh.
- Đặt `Cache-Control: no-store` cho response xác thực chứa thông tin nhạy cảm và mọi chặng proxy phù hợp.
- Đừng phản hồi thông tin “provider X đang timeout” cho user anonymous nếu việc đó hỗ trợ dò cấu hình nội bộ; phía public chỉ cần biết dịch vụ tạm thời lỗi.
- Thông báo hỗ trợ có thể nói “cung cấp mã yêu cầu” thay vì “gửi ảnh chụp nguyên trang có token”.
- Không để thông tin private chạy qua `?error=SQLException...` hoặc URL redirect đến domain không tin cậy.

Chính sách có thể khác cho self-service sau khi người dùng đã thực hiện xác thực đủ mạnh (được phép biết chi tiết tình trạng MFA *của chính mình*). Quan trọng là **kiểm soát ngữ cảnh và quyền xem**, không phải giấu mọi trạng thái trong mọi trường hợp.

## 6. Correlation ID, trace ID và audit event ID

Một **requestId** gắn với **một HTTP request**. Một **traceId** (ví dụ OpenTelemetry/W3C Trace Context) có thể nối nhiều spans và nhiều service. Một **auditEventId** gắn với một sự kiện bảo mật nghiệp vụ như login thất bại hoặc thay phương thức xác thực; một request có thể sinh nhiều audit events.

~~~text
Browser
 POST /login
   |
   | X-Request-ID: 589d...  (server generated)
   v
Gateway -> Auth service -> User store / IdP
             |               |
             | trace_id=T-17 |
             | span_id=S-2   |
             |               |
             + audit_event_id=E-42
   |
   v
Response:
  requestId=589d...
  publicCode=AUTH_FAILED

Restricted logs:
  request_id=589d...
  trace_id=T-17
  audit_event_id=E-42
  internal_reason=UNKNOWN_USER
  result=FAILURE
~~~

IDs trong sơ đồ là ký hiệu minh họa. Với HTTP thực tế, request ID nên là UUID ngẫu nhiên hoặc ID opaque do server/gateway đáng tin sinh; `traceId` có format của hệ tracing, không tự chế bằng username và timestamp.

### Sinh, truyền và làm sạch

- Ở biên ingress, **sinh request ID mới** hoặc chỉ chấp nhận header từ **gateway đáng tin** sau kiểm tra allowlist, length và format. Client internet không được tự ép một ID gây giả mạo log.
- Đặt ID vào request attribute và response header, truyền vào MDC/structured logger với phạm vi request. Trong Java servlet thread pool, **luôn xóa MDC trong `finally`** để tránh request sau thừa hưởng nhãn request cũ.
- Với async processing hoặc executor, MDC không tự động lan sang thread khác. Cần cơ chế context propagation được kiểm soát; nếu không, log async mất correlation hoặc mang nhầm context.
- Khi sang service khác, phân biệt trusted distributed-tracing context với custom request ID; dùng W3C `traceparent` / `tracestate` theo OpenTelemetry/Micrometer nếu đã triển khai.
- Không tự động đưa client-provided request ID vào SQL query/log line không escape; chặn CR/LF và ký tự điều khiển để chống **log injection**.
- Tạo ID trước các filter xử lý auth để cả `AuthenticationFailureHandler` và `AuthenticationEntryPoint` nhìn thấy cùng ID.
- Không hứa request ID luôn tìm được log lâu dài: retention/sampling/incident policy khác nhau; audit sự kiện nhạy cảm không được phụ thuộc hoàn toàn vào tracing sampling.

### Structured logs vận hành

Ví dụ một event **chỉ ở hệ log quyền hạn chế**, không đưa nguyên bản cho client:

~~~json
{
  "timestamp": "2026-11-06T03:27:18Z",
  "service": "auth-api",
  "environment": "production",
  "event_type": "authentication.failure",
  "request_id": "c1d4e9f5-9fcb-48d2-9e2c-1037560fd229",
  "trace_id": "d7390c4f0e8541b682512646b49263e7",
  "public_code": "AUTH_FAILED",
  "internal_reason": "BAD_PASSWORD",
  "http_status": 401,
  "principal_ref": "hmac-sha256:restricted-pseudonym",
  "result": "DENIED"
}
~~~

Đây là log minh họa. `principal_ref` cần HMAC/pepper và chính sách khóa/rotation nếu dùng pseudonymization; hash thường của email có thể dễ dictionary attack. Nếu username không tồn tại, đừng tạo `user_id` giả gây nhầm. IP, user-agent, địa chỉ email và geolocation là dữ liệu nhạy cảm/phải có retention policy. `trace_id` đôi khi là input untrusted; sanitize và giới hạn length.

### Ai được xem private details?

- Client/public support chỉ xem mã an toàn và request ID.
- Nhân viên on-call/triage có quyền tìm log đã redact và audit theo role, có ghi lại hoạt động tra cứu.
- Security analyst có thể xem reason code, rate-limit signals và alert theo need-to-know.
- Quyền xem stack trace/PII đã bảo vệ phải hạn chế chặt, có retention, masking và audit trail.
- Dashboard công khai không được cho query log theo requestId mà không xác thực/ủy quyền. Không biến request ID thành “mật khẩu” mở trang lỗi.

**Kết luận phần này:** mã tương quan liên kết hai góc nhìn; không được dùng để chuyển toàn bộ thông tin góc nhìn vận hành ra response công khai.

## 7. Java 17 chạy độc lập: ánh xạ failure nội bộ sang public contract

Ví dụ sau sử dụng **JDK 17 thuần**, không cần Maven, Spring hay server. Nó minh họa trường hợp lý do nội bộ khác nhau nhưng response công khai giống nhau. Request ID truyền vào từ tầng nhận request, không được tạo bằng email. Mã không logging và không dùng làm hệ thống xác thực thực tế.

Lưu file `PublicAuthErrorsDemo.java`:

~~~java
import java.util.List;
import java.util.Objects;

public class PublicAuthErrorsDemo {

    enum InternalFailure {
        UNKNOWN_USER,
        WRONG_PASSWORD,
        ACCOUNT_LOCKED,
        NO_CREDENTIAL,
        BAD_BEARER_TOKEN,
        NOT_ENOUGH_PERMISSION,
        TOO_MANY_ATTEMPTS,
        IDP_UNAVAILABLE
    }

    record PublicError(
            int httpStatus,
            String code,
            String message,
            String requestId) {

        PublicError {
            Objects.requireNonNull(code);
            Objects.requireNonNull(message);
            Objects.requireNonNull(requestId);
        }
    }

    static PublicError toPublic(
            InternalFailure failure, String requestId) {
        Objects.requireNonNull(failure);
        Objects.requireNonNull(requestId);

        return switch (failure) {
            // Không tiết lộ account có tồn tại hoặc bị khóa hay không.
            case UNKNOWN_USER, WRONG_PASSWORD, ACCOUNT_LOCKED ->
                new PublicError(
                    401, "AUTH_FAILED",
                    "Thong tin dang nhap khong hop le", requestId);

            case NO_CREDENTIAL ->
                new PublicError(
                    401, "AUTH_REQUIRED",
                    "Can xac thuc", requestId);

            case BAD_BEARER_TOKEN ->
                new PublicError(
                    401, "INVALID_ACCESS_TOKEN",
                    "Thong tin xac thuc khong hop le", requestId);

            case NOT_ENOUGH_PERMISSION ->
                new PublicError(
                    403, "ACCESS_DENIED",
                    "Khong du quyen truy cap", requestId);

            case TOO_MANY_ATTEMPTS ->
                new PublicError(
                    429, "AUTH_RATE_LIMITED",
                    "Vui long thu lai sau", requestId);

            case IDP_UNAVAILABLE ->
                new PublicError(
                    503, "AUTH_SERVICE_UNAVAILABLE",
                    "Dich vu tam thoi gian doan", requestId);
        };
    }

    public static void main(String[] args) {
        String requestId = "req-0007";
        List<InternalFailure> attempts = List.of(
            InternalFailure.UNKNOWN_USER,
            InternalFailure.WRONG_PASSWORD,
            InternalFailure.ACCOUNT_LOCKED,
            InternalFailure.NO_CREDENTIAL,
            InternalFailure.NOT_ENOUGH_PERMISSION,
            InternalFailure.IDP_UNAVAILABLE
        );

        for (InternalFailure failure : attempts) {
            PublicError response = toPublic(failure, requestId);
            System.out.println(
                failure + " => " + response.httpStatus()
                + " " + response.code()
                + " " + response.requestId());
        }

        PublicError unknown =
            toPublic(InternalFailure.UNKNOWN_USER, requestId);
        PublicError wrongPassword =
            toPublic(InternalFailure.WRONG_PASSWORD, requestId);

        System.out.println(
            "samePublicLoginResponse="
            + unknown.equals(wrongPassword));
    }
}
~~~

Chạy:

~~~bash
javac PublicAuthErrorsDemo.java
java PublicAuthErrorsDemo
~~~

**Stdout chính xác** theo mã (không có random/time):

~~~text
UNKNOWN_USER => 401 AUTH_FAILED req-0007
WRONG_PASSWORD => 401 AUTH_FAILED req-0007
ACCOUNT_LOCKED => 401 AUTH_FAILED req-0007
NO_CREDENTIAL => 401 AUTH_REQUIRED req-0007
NOT_ENOUGH_PERMISSION => 403 ACCESS_DENIED req-0007
IDP_UNAVAILABLE => 503 AUTH_SERVICE_UNAVAILABLE req-0007
samePublicLoginResponse=true
~~~

Trong production, các request thực nên có **request ID riêng**. Việc cố định `req-0007` ở demo chỉ để stdout có thể tái hiện. Kiểm tra cuối cho thấy `UNKNOWN_USER` và `WRONG_PASSWORD` ánh xạ giống nhau ở toàn bộ record public nếu cùng ID; điều đó không nói gì về time/HTTP headers của hệ thống thật.

Điểm quan trọng:

- Public code khác **InternalFailure enum**; không serialize enum nội bộ ra ngoài.
- Quyết định status/code là policy ứng dụng và có thể điều chỉnh để đúng giao thức tại từng endpoint.
- Nếu `IDP_UNAVAILABLE`, trả 503 thay vì 401 để giữ sự khác biệt giữa credential sai và sự cố vận hành.
- Khi dùng OAuth Bearer, còn phải thiết lập `WWW-Authenticate` theo RFC 6750; chương trình thuần chỉ biểu diễn body semantics, không thay thế filter.
- Message demo cố ý không có chi tiết riêng của từng account, không phải nội dung đa ngôn ngữ production.

## 8. Spring Boot 3 / Spring Security 6: ghi request ID và trả JSON an toàn

### 8.1. Sự kiện xảy ra ở filter hay MVC?

~~~text
Incoming HTTP request
        |
        v
Request ID servlet filter (trước Spring Security)
        |
        v
Spring Security FilterChain
        |
        +-- POST /login, password sai
        |      -> UsernamePasswordAuthenticationFilter
        |      -> AuthenticationFailureHandler
        |
        +-- GET /api/private, thiếu credential
        |      -> AuthorizationFilter denies
        |      -> ExceptionTranslationFilter
        |      -> AuthenticationEntryPoint (401/challenge)
        |
        +-- GET /api/admin, authenticated nhưng thiếu scope
        |      -> AuthorizationFilter denies
        |      -> ExceptionTranslationFilter
        |      -> AccessDeniedHandler (403)
        |
        +-- Bearer JWT malformed/expired
        |      -> BearerTokenAuthenticationFilter
        |      -> AuthenticationEntryPoint / Bearer challenge
        |
        +-- MVC Controller/Service error
               -> @ControllerAdvice / ErrorResponse/ProblemDetail
~~~

`@RestControllerAdvice` xử lý lỗi MVC, nhưng **không tự bao phủ Spring Security filter failures** đã xảy ra trước DispatcherServlet. Một số exception có thể được ném trong method security và đi qua các handler khác; cần integration test cụ thể. Không có “một @ExceptionHandler bắt mọi lỗi auth” mặc định.

### 8.2. Request ID filter đặt trước security

Đoạn sau là **class Java độc lập trong dự án Spring Boot Servlet**, cần `spring-boot-starter-web` và logging SLF4J/MDC. Tạo file `RequestIdFilter.java` trong package ứng dụng:

~~~java
package example;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestIdFilter extends OncePerRequestFilter {

    public static final String ATTRIBUTE = "requestId";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        // Server-generated: không tin X-Request-ID do client gửi.
        String requestId = UUID.randomUUID().toString();

        request.setAttribute(ATTRIBUTE, requestId);
        response.setHeader("X-Request-ID", requestId);

        MDC.put("requestId", requestId);
        try {
            chain.doFilter(request, response);
        } finally {
            // Servlet threads được tái sử dụng; tránh leak qua request sau.
            MDC.remove("requestId");
        }
    }
}
~~~

Giới hạn: ví dụ sinh **mỗi HTTP request một ID**. Hệ thống gateway tin cậy có thể đã sinh ID; khi muốn giữ cùng ID giữa nhiều hop, chỉ nhận/truyền header từ nguồn được xác minh và validate format/length. Với async dispatch và executor, cấu hình context propagation riêng: MDC là ThreadLocal, không tự đi sang thread khác. `@Order(HIGHEST_PRECEDENCE)` nhằm đặt Servlet filter trước security; xác nhận thứ tự đăng ký thực tế trong app, tránh filter chạy hai lần nếu tự đăng ký thêm bean vào chain.

### 8.3. Public Problem Details writer

Spring Framework hỗ trợ `ProblemDetail` và RFC 9457 ở Spring MVC. Tuy nhiên trong Servlet security filter, ta có thể trực tiếp ghi JSON **sau khi kiểm tra response chưa committed**, bảo đảm mã công khai nhất quán.

Ví dụ sau là **utility dùng trong một ứng dụng Spring Boot đã có Jackson**. Tạo file `PublicAuthErrorWriter.java`:

~~~java
package example;

import java.io.IOException;
import java.util.Map;
import java.util.UUID;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.stereotype.Component;

@Component
public class PublicAuthErrorWriter {

    private final ObjectMapper mapper;

    public PublicAuthErrorWriter(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public void write(HttpServletRequest request,
                      HttpServletResponse response,
                      int status, String code,
                      String publicTitle, String publicDetail)
            throws IOException {

        if (response.isCommitted()) {
            return;
        }

        Object stored = request.getAttribute(RequestIdFilter.ATTRIBUTE);
        String requestId = stored instanceof String text
            ? text
            : UUID.randomUUID().toString();

        response.setStatus(status);
        response.setContentType("application/problem+json");
        response.setCharacterEncoding("UTF-8");
        response.setHeader("Cache-Control", "no-store");
        response.setHeader("X-Request-ID", requestId);

        // Map không cam kết thứ tự key; JSON serializer quyết định.
        // instance không chứa path/query có thể có token/PII.
        Map<String, Object> problem = Map.of(
            "type", "https://api.example.test/problems/" + code.toLowerCase(),
            "title", publicTitle,
            "status", status,
            "detail", publicDetail,
            "instance", "urn:uuid:" + requestId,
            "code", code,
            "requestId", requestId
        );

        mapper.writeValue(response.getOutputStream(), problem);
    }
}
~~~

**Về `instance`:** ở ví dụ filter, requestId luôn là UUID thực từ `RequestIdFilter`, nên `urn:uuid:<uuid>` hợp lệ. Fallback UUID chỉ để xử lý khi filter không chạy theo giả định. Nếu sử dụng requestId từ hệ thống khác không phải UUID, nên dùng một URI reference hợp lệ khác, đừng tự gắn `urn:uuid:` cho chuỗi bất kỳ. `type` của ví dụ là URI minh họa; production phải dùng namespace được tổ chức quản lý, có tài liệu ổn định.

`Map.of` trả body hợp lệ nhưng không bảo đảm thứ tự các thuộc tính; client phải parse JSON bằng tên key. Không gửi `Exception` vào writer, không ghép `exception.getMessage()` vào `detail`.

### 8.4. Wiring các handler đúng điểm vào của Spring Security

Một cấu hình gọn cho REST Bearer API (resource server) và web form là **hai `SecurityFilterChain`**. File `SecurityErrorConfig.java`:

~~~java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityErrorConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(
            HttpSecurity http, PublicAuthErrorWriter writer)
            throws Exception {

        var bearer401 = new BearerTokenAuthenticationEntryPoint();
        var bearer403 = new BearerTokenAccessDeniedHandler();

        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/admin/**")
                    .hasAuthority("SCOPE_admin")
                .anyRequest().authenticated())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            // Chỉ dành cho API xác thực bằng Authorization: Bearer;
            // không áp dụng cho endpoint cũng dùng browser cookie.
            .csrf(AbstractHttpConfigurer::disable)
            .oauth2ResourceServer(oauth -> oauth
                .authenticationEntryPoint((req, res, ex) -> {
                    bearer401.commence(req, res, ex);
                    // Giữ status và WWW-Authenticate của RFC 6750.
                    if (!res.isCommitted()) {
                        int status = res.getStatus();
                        String code = status == 400
                            ? "INVALID_AUTH_REQUEST"
                            : "INVALID_ACCESS_TOKEN";
                        writer.write(req, res, status, code,
                            "Authentication required",
                            "Yêu cầu xác thực không hợp lệ.");
                    }
                })
                .accessDeniedHandler((req, res, ex) -> {
                    bearer403.handle(req, res, ex);
                    if (!res.isCommitted()) {
                        writer.write(req, res, res.getStatus(),
                            "ACCESS_DENIED",
                            "Access denied",
                            "Bạn không có quyền thực hiện thao tác.");
                    }
                })
                .jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(
            HttpSecurity http, PublicAuthErrorWriter writer)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/error").permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form
                // JSON login UX: khác web page cần redirect.
                .failureHandler((req, res, ex) ->
                    writer.write(req, res,
                        HttpServletResponse.SC_UNAUTHORIZED,
                        "AUTH_FAILED",
                        "Authentication failed",
                        "Thông tin đăng nhập không hợp lệ.")))
            .build();
    }
}
~~~

**Đây là cấu hình minh họa**, không phải template production copy/paste không cần kiểm thử. Để chạy Bearer JWT cần `spring-boot-starter-oauth2-resource-server`, issuer/JWK, `JwtDecoder` và validator đúng; form login cần user store, CSRF form setup, session/cookie security. Không dùng `.csrf(disable)` trong `webChain`. Nếu dự án chỉ dùng web form HTML, `AuthenticationFailureHandler` nên redirect về trang lỗi **chung** thay vì ép client nhận JSON; route và `Accept` được thiết kế rõ.

**Chú ý cho Bearer:** `BearerTokenAuthenticationEntryPoint` có thể trả **status 400 hoặc 401 tùy `BearerTokenError`**. Ví dụ trên giữ nguyên status nhưng ánh xạ JSON code đơn giản; khi không có token, có thể chọn `AUTH_REQUIRED` thay `INVALID_ACCESS_TOKEN` nếu policy ứng dụng yêu cầu, bằng cách phân loại an toàn **dựa trên kết quả xác thực**, không đọc/echo token thô. Với 403, `BearerTokenAccessDeniedHandler` có thể sinh `insufficient_scope` khi authentication đủ điều kiện; writer không được xóa/chỉnh `WWW-Authenticate` mà handler đã ghi.

Cần test sự phối hợp giữa nhiều security chains, DSL `oauth2ResourceServer` và `exceptionHandling`, vì cấu hình entry point có thể khác theo route/phiên bản. Đừng giả định security filter sẽ luôn gọi `@ControllerAdvice`. Việc log chi tiết exception phải được xử lý ở **nội bộ** và tuyệt đối không nằm trong writer.

### Thông tin nào được log bên trong handler?

Chỉ log **metadata đã sanitize**, ví dụ: event type, reason code nội bộ được whitelist, requestId/MDC trace ID, HTTP status, thời gian, account pseudonym có policy và route template. Đừng log `ex.toString()` một cách vô tội vạ hoặc giữ raw `Authorization` trong context. Nếu cần stack trace để điều tra lỗi `503/500`, đưa vào log quyền hạn chế với sanitization/retention thay vì JSON trả user.

### Chỗ đứng của @ControllerAdvice

Ở MVC, có thể dùng `@RestControllerAdvice` và `ProblemDetail.forStatus(...)` / `ResponseEntityExceptionHandler` để trả cùng contract cho lỗi controller. Nhưng lỗi Spring Security filter và login failure vẫn cần các handler ở filter chain. Nếu có error serialization chung, tách một `PublicErrorFactory` dùng được bởi MVC lẫn filter, **nhưng không khiến Servlet security flow phụ thuộc vào DispatcherServlet**.

## 9. Test cases bắt buộc

| Thử nghiệm | Kết quả mong muốn |
| --- | --- |
| Username không tồn tại | Cùng public code/body/status với password sai, không lộ username |
| Password sai | Cùng response với account không tồn tại; private reason có audit riêng |
| Account locked/disabled | Generic response ở anonymous login theo threat model, không lộ trạng thái |
| Protected REST thiếu token | 401 + Bearer `WWW-Authenticate`; có requestId |
| Bearer token invalid/expired | Thường 401 + `invalid_token`, body không chứa JWT/claim |
| Malformed Bearer | Status/challenge đúng `BearerTokenError`, không ép 401 nếu chuẩn quy định 400 |
| Scope thiếu, token authenticated | 403; `insufficient_scope` khi đúng semantics |
| Business ACL từ chối | 403 hoặc 404 theo policy, không tiết lộ owner/resource |
| Brute-force vượt ngưỡng | 429/biện pháp chống automation, không rò account existence |
| IdP/JWK/DB unavailable | 503/5xx và alert, không trả `AUTH_FAILED 401` giả |
| Request ID trong header/body | Cùng một giá trị đã được server sinh |
| Input `X-Request-ID` có CRLF/quá dài | Không làm ô nhiễm log; server cấp ID hợp lệ |
| Nhiều request song song | Correlation ID không bị trộn giữa các Servlet thread |
| Async task | Context propagation đúng hoặc log ghi rõ thiếu context, không dùng MDC cũ |
| MVC exception | ProblemDetail public theo contract, không rò stack trace |
| Exception ở security filter | Vẫn có body/header an toàn dù không vào ControllerAdvice |
| Authorization grant không có scope | Không tự cho phép client thử liên tục |
| OAuth callback lỗi | Không lộ authorization code, `state`, `nonce`, IdP token |
| Security telemetry | Log có requestId + internal reason nhưng không có secrets |
| Support lookup | RequestId chỉ tra cứu bởi người có quyền, có audit truy vấn |

### MockMvc test snippets (không phải class độc lập)

Trong dự án có Spring Security Test, `MockMvc mvc`, JWT test config và controller test tương ứng:

~~~java
// 1. Không có Bearer token.
mvc.perform(get("/api/admin/report"))
   .andExpect(status().isUnauthorized())
   .andExpect(header().exists("X-Request-ID"))
   .andExpect(header().string(
       "WWW-Authenticate",
       org.hamcrest.Matchers.startsWith("Bearer")));

// 2. Có JWT Authentication giả lập nhưng không có scope admin.
mvc.perform(get("/api/admin/report")
       .with(jwt().authorities(
           new SimpleGrantedAuthority("SCOPE_read"))))
   .andExpect(status().isForbidden());

// 3. Không bao giờ đưa exception class ra public body.
mvc.perform(post("/login")
       .param("username", "someone")
       .param("password", "wrong")
       .with(csrf()))
   .andExpect(status().isUnauthorized())
   .andExpect(jsonPath("$.code").value("AUTH_FAILED"))
   .andExpect(jsonPath("$.requestId").isString());
~~~

Đoạn trên **cần static imports, MockMvc context, user store và route thật**. `jwt()` của Spring Security Test giả lập Authentication: nó **không kiểm tra chữ ký JWT thực**. Muốn xác nhận `invalid_token` và JWT validator, phải dùng decoder thật/test key, gửi Bearer token ký đúng/sai và kiểm tra HTTP challenge. Đừng chỉ assert `401` rồi coi response an toàn; assert thêm header, body redaction, timing, logs và no-store.

### Kiểm tra bằng test đơn vị của mã công khai

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class PublicAuthErrorsDemoTest {

    @Test
    void unknownUserAndWrongPasswordHaveSamePublicResponse() {
        String id = "req-1";
        assertEquals(
            PublicAuthErrorsDemo.toPublic(
                PublicAuthErrorsDemo.InternalFailure.UNKNOWN_USER, id),
            PublicAuthErrorsDemo.toPublic(
                PublicAuthErrorsDemo.InternalFailure.WRONG_PASSWORD, id)
        );
    }

    @Test
    void backendOutageIsNotReportedAsWrongPassword() {
        var result = PublicAuthErrorsDemo.toPublic(
            PublicAuthErrorsDemo.InternalFailure.IDP_UNAVAILABLE,
            "req-2");
        assertEquals(503, result.httpStatus());
        assertEquals("AUTH_SERVICE_UNAVAILABLE", result.code());
    }
}
~~~

Đây là JUnit 5 class cùng package với demo Java thuần, cần dependency Jupiter. Test mapping không kiểm tra filters, trace propagation, SQL/IdP hoặc tính bảo mật của log.

## 10. Quy trình vận hành: nhận mã tương quan rồi xử lý an toàn

Một quy trình hỗ trợ:

1. Client hiển thị: “Xác thực không thành công. Mã yêu cầu: `c1d4e9f5-...`”. Không hiển thị reason nội bộ.
2. Support tiếp nhận mã và kiểm tra quyền truy cập; không yêu cầu user gửi password, OTP hoặc ảnh chụp chứa access token.
3. Tìm requestId trong log index theo khoảng thời gian/tenant; nếu không có log vì sampling/retention, nêu giới hạn thay vì suy diễn.
4. Correlate với `trace_id`, `audit_event_id`, internal reason code và dependency status; xác định user enumeration attack, DB outage hay token validation failure.
5. Vận hành tạo incident/alert hoặc remediation theo runbook. Việc mở khóa account, reset MFA, thay password hoặc cấp token **không** được thực hiện chỉ dựa trên requestId.
6. Khi lỗi đã xử lý, cập nhật public status/message nếu cần mà không đưa stack trace/PII vào email phản hồi.

### Chỉ số và alerts có ý nghĩa

- `authentication.failure.count` theo **nhóm reason nội bộ**, không theo username/raw email làm metric labels.
- Tỷ lệ `401`/`403`/`429`/`5xx`, SLO login, latency và tỷ lệ thành công trên các phương thức (password/OIDC/MFA).
- IDP/JWK/LDAP outages và timeout, retry storms; lockout/brute-force detection với account pseudonym trong hệ thống bảo mật.
- Số lần fail liên tục trên một principal hoặc IP theo chính sách chống abuse; tránh ghi PII vào analytics công khai.
- Alert khi có chuỗi authentication failure bất thường hoặc lỗi 503 tăng, có context requestId/traceId đã redacted.

**Thận trọng với log/trace:** OWASP Logging Cheat Sheet khuyến nghị không lưu trực tiếp passwords, session identifiers, access tokens, encryption keys và dữ liệu nhạy cảm không cần thiết; bảo vệ logs bằng quyền truy cập, retention, integrity, time synchronization và giám sát. Correlation ID hữu ích nhưng không biến logging thành cơ chế thay thế audit security.

## 11. Các lỗi thiết kế thường gặp

1. Gửi `exception.getMessage()` hoặc stack trace cho client: có thể lộ SQL schema, host, provider, account state và secrets.
2. Tạo public code `USER_NOT_FOUND`, `WRONG_PASSWORD`, `ACCOUNT_LOCKED` ở login anonymous: user enumeration.
3. Chỉ sửa body mà quên HTTP status, header/redirect hoặc timing: vẫn có discrepancy factor.
4. Trả `200 OK` cho mọi lỗi auth: client/cache/proxy và monitoring xử lý sai semantics.
5. Trả `401` cho DB/JWK outage: che giấu sự cố, gây retry credential và khó vận hành.
6. Đổi `403` thiếu quyền thành `401`: client refresh access token vô hạn mà không giải quyết được policy.
7. Thêm JSON cho Bearer mà làm mất `WWW-Authenticate`: vi phạm kỳ vọng OAuth2 clients.
8. Dùng `@RestControllerAdvice` cho mọi lỗi Spring Security: một số lỗi bị chặn trước MVC.
9. Tin raw `X-Request-ID` do browser gửi: log injection, ID spoofing, độ dài không kiểm soát.
10. Không xóa MDC trong `finally`: metadata của user/request cũ có thể dính sang request khác.
11. Log toàn bộ HTTP headers/request body: lộ password, bearer/refresh token, cookie, OTP.
12. Gắn username/email/token vào metrics labels: lộ thông tin, tăng cardinality và chi phí.
13. Không bảo vệ endpoint xem chi tiết requestId: biến ID opaque thành đường vào log riêng tư.
14. Để `requestId` làm bằng chứng khôi phục tài khoản: không phải credential và không chứng minh ownership.
15. Không kiểm thử nhiều chains HTML/API và sự khác biệt 401/403/429/503: API contract lệch theo filter.
16. Cho client parse message đã dịch ngôn ngữ thay vì public code ổn định: dễ vỡ khi thay wording.
17. Dùng cùng correlation ID cho mọi request trong session: không phân biệt các lần thử và tạo leakage liên tục.
18. Coi `instance` RFC 9457 là nơi chứa full URL: có thể lộ token trong query string, path hay PII.

## 12. Checklist hoàn thành

- [ ] Danh mục public code có semantics và version; không phản ánh raw internal exception.
- [ ] Login thất bại anonymous trả phản hồi chung khi sai username/password/locked theo threat model.
- [ ] 401, 403, 400, 429, 503 phân biệt đúng; HTML browser redirect được thiết kế riêng.
- [ ] OAuth2 Bearer response giữ `WWW-Authenticate` và tham số RFC 6750 phù hợp.
- [ ] Correlation ID do server/gateway tin cậy tạo, opaque, cùng giá trị trong header/body/log.
- [ ] Không dùng request ID làm quyền truy cập hệ vận hành hoặc credential khôi phục.
- [ ] Structured logs có internal reason, request/trace/audit IDs và retention/access control; không có secrets.
- [ ] MDC được cleanup với try/finally, async context propagation được kiểm thử.
- [ ] Spring Security `AuthenticationFailureHandler`, `AuthenticationEntryPoint`, `AccessDeniedHandler` cùng các MVC errors trả hợp đồng nhất quán.
- [ ] Production test kiểm tra user enumeration qua status/body/headers/timing và rò thông tin trong lỗi.
- [ ] Có runbook support, alert và audit cho tra cứu sự cố theo requestId.

**Tóm tắt:** phía công khai chỉ cần **mã lỗi có thể lập trình + thông điệp chung + correlation ID opaque**, đúng HTTP/OAuth protocol; phía vận hành cần **reason code, trace, metric và audit được kiểm soát truy cập**. Nối hai góc nhìn bằng request ID, không phơi ngoại lệ Java/secret ra API, là cách tạo phản hồi xác thực vừa hữu ích vừa an toàn.

## 13. Tài liệu chính thức và thực hành bảo mật

- Spring Security — `ExceptionTranslationFilter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/access/ExceptionTranslationFilter.html
- Spring Security — Form Login Failure Handling: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html
- Spring Security — OAuth2 Resource Server Bearer: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html
- Spring Security API — `BearerTokenAuthenticationEntryPoint`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/BearerTokenAuthenticationEntryPoint.html
- Spring Security API — `BearerTokenAccessDeniedHandler`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/access/BearerTokenAccessDeniedHandler.html
- Spring Framework — Error Responses and `ProblemDetail`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
- RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457.html
- RFC 6750 — Bearer Token Usage, Section 3: https://www.rfc-editor.org/rfc/rfc6750.html
- OWASP — Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP — Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- W3C — Trace Context: https://www.w3.org/TR/trace-context/
