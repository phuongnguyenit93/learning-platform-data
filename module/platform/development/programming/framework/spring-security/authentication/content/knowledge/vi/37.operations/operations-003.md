# Nhật ký đăng nhập, mã tương quan và bảo vệ dữ liệu cá nhân trong Spring Security

Khi vận hành một ứng dụng Spring Security, đội ngũ kỹ thuật cần trả lời những câu hỏi như: **ai đã thử đăng nhập, phương thức nào được dùng, yêu cầu thất bại ở đâu, và vì sao một người dùng nói họ không vào được hệ thống?** Nhật ký (log), audit events, mã tương quan (correlation IDs) và distributed tracing giúp điều tra những việc này. Tuy nhiên, nếu ghi không cẩn thận, chính hệ thống nhật ký lại trở thành nguồn rò rỉ **mật khẩu, access token, session cookie, email, địa chỉ IP hoặc dữ liệu tài khoản**.

Nguyên tắc cốt lõi: **ghi đủ sự kiện bảo mật để truy vết, nhưng không ghi credential hoặc dữ liệu cá nhân vượt mục đích**. Một dòng log đăng nhập tốt phải nêu được điều gì xảy ra, khi nào, ở dịch vụ nào và thuộc yêu cầu nào; nó **không cần** in ra toàn bộ HTTP request, đối tượng `Authentication`, mật khẩu hay nội dung exception.

Bài học thuộc phần **Vận hành** của module Spring Security – authentication, tập trung vào thiết kế schema, logging success/failure, mã request/trace/span, MDC, trust boundary của header, kiểm soát PII, chống log injection, vận hành log tập trung và các bài kiểm thử Java 17+.

## 1. Phân biệt application log, security event, audit trail và distributed trace

Bốn nguồn dữ liệu thường cùng xuất hiện nhưng không thay thế nhau:

| Loại | Mục tiêu chính | Ví dụ | Độ tin cậy và lưu trữ |
| --- | --- | --- | --- |
| **Application log** | Chẩn đoán kỹ thuật | “Password encoder timeout”, “Request completed” | Có thể thay đổi theo log level; không mặc định là audit bền vững |
| **Security event** | Mô tả hành vi an ninh | Authentication succeeded/failed, account locked | Cần chuẩn hóa category và giám sát |
| **Audit trail** | Truy vết hành động quan trọng | Ai đổi MFA, đổi mật khẩu, thu hồi session, thêm passkey | Cần tính toàn vẹn, quyền truy cập và retention rõ |
| **Distributed trace** | Theo dõi một công việc qua nhiều service | Gateway → identity-service → user-store | Dùng trace/span IDs; có thể bị sampling |

Ví dụ một sự cố login:

~~~text
Browser
   |
   v
API Gateway -------------------- traceId T / requestId R
   |
   v
Auth Service ------------------- auth_event=FAILURE reason=PROVIDER_ERROR
   |
   +----> Directory/IdP ---------- spanId S / timeout
   |
   +----> Audit/Observability ---- eventId E / severity=ERROR
~~~

Mã `requestId` giúp liên kết các dòng trong **một request**; `traceId` giúp liên kết các spans xuyên nhiều service; `spanId` nhận diện một bước riêng; `eventId` nhận diện **một bản ghi sự kiện cụ thể**.

**Không dùng session ID, access token hay username làm mã tương quan.** Chúng có mục đích khác, có thể mang quyền truy cập hoặc chứa dữ liệu cá nhân. Một correlation ID được tạo ngẫu nhiên không phải bằng chứng xác thực và không được phép dùng thay credential.

### Một lần HTTP request không phải luôn là một lần đăng nhập

Một request có thể đi qua nhiều authentication components; một login có thể bao gồm password, MFA hoặc redirect OIDC; một token refresh có thể tạo authentication mới nhưng không phải thao tác đăng nhập tương tác. Vì vậy khi xây dashboard cần phân biệt:

- `AUTH_ATTEMPT` — một lần backend xử lý credential;
- `AUTH_SUCCESS` / `AUTH_FAILURE` — kết quả xác thực được framework báo;
- `LOGIN_COMPLETED` — ứng dụng hoàn tất flow login và đã thiết lập session/token phù hợp;
- `MFA_CHALLENGE` / `MFA_COMPLETED` — các bước kiểm thêm yếu tố;
- `LOGOUT_COMPLETED` / `SESSION_REVOKED` — thay đổi phiên;
- `AUTHORIZATION_DENIED` — đã xác định principal nhưng không được phép truy cập resource.

Các khái niệm này phải được định nghĩa trong **event taxonomy** của tổ chức; không suy một-to-one giữa `AuthenticationSuccessEvent`, HTTP 200, và một người dùng đăng nhập thành công.

## 2. Tại sao ghi mọi request body/header lại nguy hiểm?

Một request đăng nhập có thể chứa:

~~~http
POST /login HTTP/1.1
Host: accounts.example.org
Cookie: SESSION=<session-secret>
Authorization: Bearer <access-token>
Content-Type: application/x-www-form-urlencoded

username=lan@example.org&password=<password-secret>
~~~

Nếu access logger ghi nguyên URL, body, headers hoặc exception objects, có thể làm lộ:

- Password, OTP, backup/recovery codes;
- Session cookie, access token, refresh token, API key;
- Password-reset token trong query string, OAuth authorization code;
- Raw email, username, số điện thoại, IP/user agent (có thể là dữ liệu cá nhân);
- Internal hostname, secret configuration, stack traces chứa credentials;
- `client_assertion` hoặc private-key material trong một số tích hợp.

**Mật khẩu, Bearer token và session identifier phải được xem là dữ liệu nhạy cảm có thể cấp quyền truy cập.** Redact trước khi log được tạo và chuyển qua bất kỳ sink nào; không chỉ xóa sau khi đã lưu trong SIEM.

Các vị trí thường quên:

| Tầng | Nguy cơ |
| --- | --- |
| Servlet access log / reverse proxy | Query string, URL đầy đủ, Cookie và Authorization headers |
| Request/response logging filter | Dump body/headers chứa credential |
| Spring Security DEBUG/TRACE | Chi tiết flow, exception hoặc objects nhạy cảm tùy cấu hình |
| HTTP client logging tới IdP | Authorization headers, token request/response |
| Exception handler | `exception.getMessage()` chứa username/query/endpoint |
| Distributed tracing | Span attributes/baggage chứa email, access token |
| MDC | Gắn userId/email rồi không cleanup giữa thread pool tasks |
| Error reporting/APM | Captured HTTP request, headers, form fields |
| Log aggregation/export | Sao chép sang nhiều sinks với quyền/retention khác |

Không nên bật body logging toàn cục tại `/login`, `/oauth2/token`, `/reset-password` hoặc `/webauthn/**`. Nếu thực sự cần gỡ lỗi, sử dụng log event/metadata có allowlist và kiểm thời gian bật, quyền truy cập và cách thu hồi.

## 3. Thiết kế schema sự kiện đăng nhập tối thiểu

Schema gợi ý dưới dạng JSON Lines — **không phải một cấu trúc do Spring Security mặc định tự phát**:

~~~json
{
  "eventId": "c8a62a8e-7b07-44f3-a218-6d73c7adfba2",
  "timestamp": "2026-11-06T03:00:00Z",
  "service": "identity-api",
  "environment": "production",
  "eventType": "AUTH_FAILURE",
  "authenticationMethod": "PASSWORD",
  "outcome": "FAILURE",
  "reasonCode": "BAD_CREDENTIALS",
  "requestId": "a640d00b-cf0c-4ee1-b5ce-36d547bc2bd0",
  "traceId": "ade6d79a3ebef5836a21ee27e4d60e70",
  "spanId": "8104c6c919a7b59f",
  "principalRef": null,
  "tenantRef": null
}
~~~

Đây là dữ liệu giả để minh họa; không phải ID/sự kiện thật.

| Trường | Hướng dẫn |
| --- | --- |
| `timestamp` | Timestamp UTC server, chuẩn ISO-8601; đảm bảo đồng bộ đồng hồ |
| `eventId` | ID riêng của bản ghi, giúp deduplication/điều tra |
| `eventType` | Danh mục nhỏ được duyệt: AUTH_SUCCESS/FAILURE, MFA, LOCKOUT… |
| `authenticationMethod` | PASSWORD, PASSKEY, OIDC, SAML, API_KEY… theo dữ liệu phía server |
| `outcome` | SUCCESS, FAILURE, DENIED, ERROR… không suy từ HTTP status đơn lẻ |
| `reasonCode` | Enum/allowlist ổn định, không chứa exception message |
| `requestId` | ID của HTTP request, random và không chứa credential |
| `traceId` / `spanId` | ID chuẩn tracing nếu có instrumentation |
| `principalRef` | Opaque ID được kiểm soát, chỉ khi thật sự cần; null cho attempt chưa xác thực |
| `tenantRef` | Opaque tenant ID từ nguồn tin cậy nếu chính sách cho phép |
| `sourceClass` | Ví dụ WEB, MOBILE, API, BATCH; tránh thu fingerprint không cần thiết |

**Không ghi raw `username` từ form vào thất bại login theo mặc định.** Người tấn công điều khiển trường username; nó có thể chứa PII của người khác hoặc payload log injection. Đối với investigation cần liên kết nhiều lần thử cùng identifier, có thể sử dụng HMAC keyed pseudonym từ giá trị đã chuẩn hóa theo policy, nhưng phải quản lý khóa, retention và giới hạn quyền xem; HMAC không làm dữ liệu tự nhiên trở thành vô danh tuyệt đối.

Nếu không có lợi ích rõ ràng cho `principalRef`, đừng đưa nó vào event. Dữ liệu tối thiểu có thể là eventType, outcome, reasonCode, service, timestamp, requestId.

## 4. Định nghĩa taxonomy và reason codes không gây lộ danh tính

Một bảng reason codes được backend kiểm soát:

| Reason code | Ý nghĩa nội bộ | Không đồng nhất với |
| --- | --- | --- |
| `BAD_CREDENTIALS` | Credential không hợp lệ | Một username chắc chắn tồn tại |
| `ACCOUNT_LOCKED` | Policy xác định account locked | Thông báo công khai về user existence |
| `ACCOUNT_DISABLED` | Account không được phép login | Lý do chi tiết cần trả cho anonymous caller |
| `CREDENTIAL_EXPIRED` | Credential đã hết hạn | Session hết hạn thông thường |
| `PROVIDER_ERROR` | IdP/LDAP/DB gặp sự cố | Sai password của user |
| `TOKEN_INVALID` | Bearer token hoặc credential không hợp lệ | Mọi request HTTP 401 đều là password login |
| `MFA_REQUIRED` | Cần hoàn tất bước MFA theo flow | Authentication failure cuối cùng |
| `AUTH_OTHER` | Không phân loại/không mapping được | Thông tin để in stack trace ra log public |

**Failure category có thể chi tiết hơn thông điệp gửi client.** Ví dụ UI nên trả lỗi login chung để tránh account enumeration, trong khi audit nội bộ phân biệt provider outage và credential failure. Nhưng chỉ nhân sự có quyền mới được xem chi tiết này.

Đừng cho client tự gửi reason code qua `X-Auth-Reason` rồi đưa vào dashboard. Mapping phải xuất phát từ AuthenticationManager/provider/exception đã kiểm.

## 5. Spring Security phát sự kiện xác thực như thế nào?

Spring Security cung cấp `AuthenticationEventPublisher` và `DefaultAuthenticationEventPublisher`, có thể phát:

- `AuthenticationSuccessEvent` khi một authentication path thông qua manager/publisher thành công;
- Các subtype `AbstractAuthenticationFailureEvent`, ví dụ `AuthenticationFailureBadCredentialsEvent`, `AuthenticationFailureLockedEvent`, `AuthenticationFailureDisabledEvent` hoặc `AuthenticationFailureServiceExceptionEvent`.

Một publisher có thể được khai báo:

~~~java
@Bean
AuthenticationEventPublisher authenticationEventPublisher(
        ApplicationEventPublisher applicationEvents) {
    return new DefaultAuthenticationEventPublisher(applicationEvents);
}
~~~

Đây là **mảnh Spring configuration**, cần imports và AppContext. Trong ứng dụng Spring Boot/Security, sự tích hợp publisher tùy authentication manager/provider đang được dùng. Nếu tự tạo `ProviderManager`, phải chắc nó thực sự nhận publisher; không suy rằng chỉ có `@EventListener` là mọi flow tự phát sự kiện.

Spring Security ánh xạ những `AuthenticationException` đã biết sang failure events; **custom exception subtype không tự hưởng mapping superclass** vì publisher dùng exact exception class match. Khi cần telemetry cho custom provider exception, có thể dùng `setAdditionalExceptionMappings(Map)` và fallback event tùy version.

**Sự kiện Spring không mặc nhiên là audit log bền vững:** listener chạy trong ApplicationContext, có thể synchronous và không tự chuyển sang Kafka/SIEM. Nếu cần lưu trữ có đảm bảo, phải thiết kế audit pipeline riêng; không giả định event mặc định được phân phối liên node hay sống qua restart.

## 6. Listener an toàn: ghi loại sự kiện, không dump Authentication

Ví dụ class **AuthenticationAuditListener.java** trong Spring Boot Servlet:

~~~java
package demo.authlogging;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.context.event.EventListener;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.security.authentication.event.AuthenticationFailureBadCredentialsEvent;
import org.springframework.security.authentication.event.AuthenticationFailureLockedEvent;
import org.springframework.security.authentication.event.AuthenticationFailureServiceExceptionEvent;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.stereotype.Component;

@Component
public class AuthenticationAuditListener {

    private static final Logger LOG =
            LoggerFactory.getLogger(AuthenticationAuditListener.class);

    @EventListener
    public void onSuccess(AuthenticationSuccessEvent event) {
        LOG.info("security_event=AUTH_SUCCESS requestId={}",
                requestIdForLog());
    }

    @EventListener
    public void onFailure(AbstractAuthenticationFailureEvent event) {
        String reason = "AUTH_OTHER";

        if (event instanceof AuthenticationFailureBadCredentialsEvent) {
            reason = "BAD_CREDENTIALS";
        } else if (event instanceof AuthenticationFailureLockedEvent) {
            reason = "ACCOUNT_LOCKED";
        } else if (event instanceof AuthenticationFailureServiceExceptionEvent) {
            reason = "PROVIDER_ERROR";
        }

        LOG.info("security_event=AUTH_FAILURE reason={} requestId={}",
                reason, requestIdForLog());
    }

    private static String requestIdForLog() {
        String value = MDC.get("requestId");
        return value == null ? "-" : value;
    }
}
~~~

Đây là Spring component, **không chạy độc lập với javac**. Cần dependency `spring-security-core`, `spring-context` và SLF4J, cùng publisher được tích hợp vào authentication flow.

Thiết kế có chủ ý:

1. Event category là constant hoặc đến từ subtype class của framework, không phải dữ liệu do user đặt.
2. `requestId` đến từ một filter/tracing layer đáng tin; nếu không có thì ghi dấu `-`, không tự suy ra principal.
3. Không gọi `getCredentials()`, không ghi raw `event.getAuthentication()`.
4. Không ghi `event.getException().getMessage()` hoặc stack trace chỉ để “biết lý do”; có thể chứa dữ liệu không kiểm soát.
5. Listener không gán quyền, không trả HTTP status và không sửa `SecurityContext`.
6. `AUTH_SUCCESS` là event ở authentication layer; nếu cần metric “user đã login tương tác”, phải định nghĩa thêm event nghiệp vụ sau khi hoàn tất password/MFA/OIDC flow.

Nếu listener được chạy bất đồng bộ, MDC của HTTP thread **không tự hiện diện** trên executor thread; cần propagation của tracing context hoặc truyền opaque event metadata phù hợp. Không dựa mù quáng vào `MDC.get("requestId")` khi đã đi qua async boundary.

## 7. Failure handler và application log có trách nhiệm khác nhau

Trong form login Servlet, `AuthenticationFailureHandler` thường quyết định response/redirect. Nó không đồng nghĩa `AuthenticationEventPublisher`.

| Cơ chế | Việc chính | Không nên làm |
| --- | --- | --- |
| `AuthenticationFailureHandler` | HTTP response login thất bại | Trả thông điệp khác nhau làm lộ account existence |
| `AuthenticationEventPublisher` | Phát success/failure events | Được coi là durable audit storage |
| `@EventListener` | Quan sát/audit/metrics từ event | Dump password/exception/user object |
| `AuthenticationEntryPoint` | Bắt đầu authentication hoặc trả 401 | Tự suy principal từ request header không tin |
| `AccessDeniedHandler` | Xử lý denial sau authorization | Đếm tất cả 403 như login failure |
| Access log filter | Request status, latency, requestId | Ghi body/header credential |

Một người dùng được xác thực nhưng thiếu quyền `ROLE_ADMIN` có thể nhận 403. Đây là **authorization denied**, không nên gán reason `BAD_CREDENTIALS`. Sự phân biệt này giúp dashboard không nhầm permission issues với password-guessing attacks.

## 8. Mã tương quan là gì và tạo từ đâu?

`requestId` là một ID opaque để nối các bản ghi trong cùng một HTTP request. Cần:

- Có tính duy nhất đủ tốt, chẳng hạn `UUID.randomUUID()` do server/gateway tin cậy sinh;
- Không chứa username/email/IP/session ID/token/tenant secret;
- Có định dạng/độ dài bounded, tránh ký tự điều khiển hoặc log forging;
- Được gắn ở ranh giới request; được dọn khi kết thúc thread context;
- Có thể trả qua response header `X-Request-ID` để người dùng gửi cho support, **nhưng không thể dùng ID này để truy cập dữ liệu riêng tư**;
- Có chiến lược nhất quán với tracing qua gateway/microservices.

Ví dụ:

~~~http
HTTP/1.1 401 Unauthorized
X-Request-ID: 7f1a9228-6ae6-4706-a8e7-8bb8e6ad2520
Content-Type: application/json

{"message":"Không thể xác thực yêu cầu."}
~~~

Request ID không xác định user nào, không phải reset token và không nên cho phép một API công khai tra chi tiết login chỉ nhờ biết ID.

### Xử lý header từ bên ngoài

Nếu client gửi:

~~~http
X-Request-ID: alice@example.org
~~~

hoặc:

~~~http
X-Request-ID: abc
X-Request-ID: attacker-injected
~~~

không được mặc định coi là nguồn tin cậy. Một lựa chọn an toàn nhất là **bỏ qua mọi inbound X-Request-ID và sinh UUID mới ở edge/backend**. Nếu tổ chức dùng gateway tin cậy để phát ID, phải strip/overwrite header từ Internet, giới hạn chiều dài/ký tự và xác thực đường mạng gateway–backend.

Có thể trả ID đã kiểm tra để support dùng, nhưng không đưa email hoặc dữ liệu cá nhân vào ID. Đừng tạo ID bằng cách nối `username + "-" + timestamp`.

## 9. MDC giúp gắn requestId vào log, nhưng MDC là ThreadLocal

SLF4J `MDC` (Mapped Diagnostic Context) là bộ key/value cho logger: logback encoder hoặc pattern có thể in `%X{requestId}` để các dòng phát trong thread hiện hành tự gắn cùng request ID.

Ví dụ pattern Logback:

~~~text
%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level [%thread] req=%X{requestId:-} %logger - %msg%n
~~~

Đây là mẫu trình bày, không phải mặc định tự được bật trong mọi cấu hình.

**MDC thường dựa trên thread-local state**: Servlet container dùng lại thread, nên nếu không clear trong `finally`, request Bob có thể ghi nhầm request ID của Alice. Với async và reactive, đơn giản `MDC.put(...)` trong một thread không bảo đảm context được giữ khi execution chuyển thread.

### Servlet OncePerRequestFilter: tạo ID và cleanup đúng boundary

Tệp **RequestIdFilter.java** trong ứng dụng Spring Boot 3+/Servlet Jakarta:

~~~java
package demo.authlogging;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.MDC;
import org.springframework.web.filter.OncePerRequestFilter;

public final class RequestIdFilter extends OncePerRequestFilter {

    private static final String KEY = "requestId";
    private static final String ATTR =
            RequestIdFilter.class.getName() + ".requestId";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        Object stored = request.getAttribute(ATTR);
        String id;
        if (stored instanceof String existing) {
            id = existing;
        } else {
            id = UUID.randomUUID().toString();
            request.setAttribute(ATTR, id);
        }

        String previous = MDC.get(KEY);
        MDC.put(KEY, id);
        response.setHeader("X-Request-ID", id);

        try {
            chain.doFilter(request, response);
        } finally {
            if (previous == null) {
                MDC.remove(KEY);
            } else {
                MDC.put(KEY, previous);
            }
        }
    }

    @Override
    protected boolean shouldNotFilterAsyncDispatch() {
        return false;
    }

    @Override
    protected boolean shouldNotFilterErrorDispatch() {
        return false;
    }
}
~~~

Điểm cần nhớ:

- Filter **tự sinh** UUID; không lấy inbound `X-Request-ID` từ client.
- Request attribute giữ cùng ID cho các dispatch của cùng request.
- `finally` restore giá trị MDC trước đó hoặc xóa key, kể cả khi filter/controller ném lỗi.
- `shouldNotFilterAsyncDispatch() = false` cho phép filter áp MDC ở một async dispatch **nếu Servlet container thực sự map filter cho ASYNC**.
- `shouldNotFilterErrorDispatch() = false` có ý nghĩa tương tự cho ERROR dispatch; cần kiểm với container và cách xử lý nested ERROR thực tế.
- Do `OncePerRequestFilter` chỉ bảo đảm một lần cho một request thread/dispatch theo semantics framework, không suy rằng chỉ có một invocation tổng cộng trong đời một HTTP request khi có async/error.

**Đây là class Servlet filter**, không phải standalone main. Khi filter được đăng ký trước `springSecurityFilterChain`, các authentication events phát đồng bộ trong request có thể đọc request ID từ MDC. Một ví dụ đăng ký (trong Spring Boot configuration):

~~~java
@Bean
FilterRegistrationBean<RequestIdFilter> requestIdFilterRegistration() {
    FilterRegistrationBean<RequestIdFilter> bean =
            new FilterRegistrationBean<>();

    bean.setFilter(new RequestIdFilter());
    bean.setOrder(Ordered.HIGHEST_PRECEDENCE + 10);
    bean.setDispatcherTypes(
            DispatcherType.REQUEST,
            DispatcherType.ASYNC,
            DispatcherType.ERROR);
    bean.setAsyncSupported(true);
    return bean;
}
~~~

Mảnh đăng ký này cần imports `org.springframework.context.annotation.Bean`, `org.springframework.boot.web.servlet.FilterRegistrationBean`, `org.springframework.core.Ordered`, `jakarta.servlet.DispatcherType`. Thứ tự phải được xác minh cùng các Servlet filters khác và cấu hình Spring Security thực tế, không giả định order này hợp lý trong mọi ứng dụng.

**Chỉ đăng ký filter một lần:** nếu đã dùng `FilterRegistrationBean`, không đồng thời tạo nó thành `@Component` để Servlet container tự đăng ký hoặc `addFilterBefore/After` lần nữa trong SecurityFilterChain mà chưa chủ đích. Nếu chỉ cần một ranh giới, đặt filter ở **một** chain có ownership rõ.

### Một chi tiết quan trọng của MDC cleanup

Mã dùng `previous` để phục hồi key nếu có một MDC context hợp lệ bao ngoài filter, thay vì xóa vô điều kiện. Nhưng nếu MDC đã có một giá trị rò rỉ từ request cũ **trước khi filter chạy**, phục hồi nó có thể che lỗi nguồn. Vì thế integration test phải xác minh servlet worker/entry boundary sạch, hoặc triển khai chính sách reset toàn bộ request-owned keys tại gateway filter. Không coi `try/finally` của một filter là bằng chứng toàn bộ MDC trong hệ thống không có dữ liệu dư.

## 10. Correlation ID với Micrometer Tracing trong Spring Boot

Nếu dự án dùng **Micrometer Tracing** và instrumentation phù hợp, Spring Boot có thể đưa `traceId` và `spanId` vào MDC rồi hiển thị correlation ID trong log. Tài liệu Spring Boot mô tả định dạng mặc định dựa trên hai giá trị này.

Ví dụ cấu hình Logback / Spring Boot có thể điều chỉnh hiển thị:

~~~properties
# Định dạng minh họa; cần Micrometer Tracing đã được cài.
logging.pattern.correlation=[%X{traceId:-},%X{spanId:-}]
~~~

Tài liệu Spring Boot hiện đại sử dụng property `logging.pattern.correlation`; nếu bạn đã có `requestId` riêng thì cần thiết kế tránh in trùng hoặc nhầm request ID với trace ID.

| ID | Scope điển hình | Ghi chú |
| --- | --- | --- |
| `requestId` | Một HTTP request | Có thể do edge hoặc app sinh |
| `traceId` | Một distributed trace, có nhiều spans | Truyền qua W3C trace context/tracing SDK |
| `spanId` | Một bước trong trace | Thường đổi khi qua operation/service khác |
| `eventId` | Một audit record | Dùng dedup/idempotency/integrity nếu cần |
| `sessionRef` | Một phiên nếu có chính sách | Không dùng raw session token làm correlation ID |

Một request có thể có nhiều spans. Nhiều requests có thể liên quan cùng một trace trong một số thiết kế. Vì vậy **không dùng traceId làm primary key của một lần login**.

**Sampling:** distributed traces có thể bị sample và không thu đủ spans. Audit bắt buộc về đổi MFA/password hoặc login nghi vấn không được phụ thuộc hoàn toàn vào tracing sampling. Hãy có audit events/pipeline đủ độ tin cậy riêng.

**W3C traceparent/tracestate/baggage** cần được xử lý bằng SDK/gateway được cấu hình tin cậy. Không xem mọi baggage key là dữ liệu đã xác minh, không đưa `username`, `Authorization` hoặc token vào baggage để thuận tiện correlation.

## 11. Bảo vệ dữ liệu cá nhân trong logs

Email, số điện thoại, địa chỉ IP, user-agent, device ID, account ID và tenant ID có thể là dữ liệu cá nhân hoặc dữ liệu có thể liên kết đến cá nhân trong ngữ cảnh cụ thể. Ngay cả opaque account ID có thể vẫn là thông tin cá nhân nếu backend có thể truy lại người đó.

Nguyên tắc vận hành:

1. **Purpose limitation:** trường dữ liệu được dùng để điều tra chuyện gì? Ai cần?
2. **Data minimization:** có thể bỏ trường đó mà vẫn điều tra được không?
3. **Access control:** ai được xem dữ liệu, có cần quyền tách riêng security/ops/support?
4. **Retention:** lưu bao lâu là cần thiết, có chính sách hết hạn và xóa tự động?
5. **Transparency và legal basis:** phối hợp với chính sách quyền riêng tư/pháp lý áp dụng, không suy một TTL pháp lý chung cho mọi nơi.
6. **Integrity:** chống sửa/giả mạo logs, ký/chuỗi hash hoặc WORM/immutable storage khi phù hợp.
7. **In-transit/at-rest protection:** TLS tới collector, encryption và quản lý key tại nơi lưu.
8. **Exports/backups:** CSV export, dashboard screenshot, backups và incident attachments phải cùng phân loại dữ liệu.

Một trường thường bị xem nhẹ là `clientIp`. Khi đứng sau proxy, `X-Forwarded-For` do client tự gửi có thể bị giả. Chỉ lấy “effective client IP” qua **trusted proxy configuration**; nếu không, vừa sai điều tra, vừa có nguy cơ log injection hoặc false attribution.

### Có nên log username/email lúc thất bại?

Mặc định nên **không ghi raw username/email** của attempt chưa được xác thực. Kẻ tấn công điều khiển input, nên event có thể tràn PII của người khác hoặc chứa payload phá log. Để liên kết nhiều attempts cùng identifier:

- Chuẩn hóa identifier đúng chính sách account (không tự dùng quy tắc email provider sai).
- Dùng **HMAC keyed pseudonym**, ví dụ HMAC-SHA-256 trên normalized identifier và key lưu ở secret manager; không dùng SHA-256 không khóa trên email dễ đoán nếu điều đó tạo nguy cơ dictionary attack.
- Cắt/giới hạn output, đặt retention và key rotation; không dùng pseudonym làm credential.
- Chỉ bật trường này khi threat model và pháp lý cho phép; mặc định log event không có identifier vẫn hữu ích.
- Không trả hash/HMAC này cho browser hoặc service không cần.

HMAC pseudonym vẫn là dữ liệu **có thể liên kết** trong cùng phạm vi key, không phải bảo đảm ẩn danh tuyệt đối. Đổi key có thể làm thay đổi khả năng correlation lịch sử; cần thiết kế thời hạn.

## 12. Java 17+: chỉ log các trường đã duyệt

Chương trình console sau mô phỏng một hàm định dạng event login an toàn. Nó **không chạy Spring Security và không ghi SIEM**; nó minh họa sinh ID không chứa PII, enum reason allowlist, chặn newline trong identifier bên ngoài, và không đưa password/email vào event.

Tạo tệp **SafeLoginAuditDemo.java**:

~~~java
import java.util.Set;
import java.util.UUID;

public class SafeLoginAuditDemo {

    private static final Set<String> REASONS = Set.of(
            "BAD_CREDENTIALS", "ACCOUNT_LOCKED", "PROVIDER_ERROR");

    static String reasonCode(String candidate) {
        return REASONS.contains(candidate) ? candidate : "AUTH_OTHER";
    }

    static String safeExternalId(String candidate) {
        return candidate != null
                && candidate.matches("[A-Za-z0-9-]{1,64}")
                ? candidate
                : "REJECTED";
    }

    static String auditLine(String requestId, String rawReason) {
        // Chỉ dùng ID server-generated và reason code allowlist.
        return "requestId=" + requestId
                + " event=AUTH_FAILURE reason=" + reasonCode(rawReason);
    }

    public static void main(String[] args) {
        String requestId = UUID.randomUUID().toString();
        String rawPassword = "s3cr3t";
        String rawEmail = "lan@example.org";

        String line = auditLine(requestId, "BAD_CREDENTIALS");

        System.out.println("Generated ID format = " +
                requestId.matches(
                        "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
                        + "[0-9a-f]{4}-[0-9a-f]{12}"));
        System.out.println("Known reason = "
                + reasonCode("BAD_CREDENTIALS"));
        System.out.println("Unknown reason = "
                + reasonCode("password=s3cr3t"));
        System.out.println("Injected ID = "
                + safeExternalId("abc\r\nFAKE_SUCCESS"));
        System.out.println("Raw password logged = "
                + line.contains(rawPassword));
        System.out.println("Raw email logged = "
                + line.contains(rawEmail));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac SafeLoginAuditDemo.java
java SafeLoginAuditDemo
~~~

Stdout chính xác:

~~~text
Generated ID format = true
Known reason = BAD_CREDENTIALS
Unknown reason = AUTH_OTHER
Injected ID = REJECTED
Raw password logged = false
Raw email logged = false
~~~

Giải thích:

- Mã UUID ngẫu nhiên có đúng hình thức được kiểm; chương trình **không in mã ID cụ thể** nên output có thể tái lập.
- Reason code là allowlist, không được suy từ raw exception message.
- Một header có CR/LF bị từ chối, không được đưa thẳng vào log.
- Raw password/email tồn tại trong demo để chứng minh **không được nối vào event line**.
- Với ứng dụng thật, tốt hơn **sinh requestId từ server và bỏ qua external ID** thay vì chỉ dùng `safeExternalId()`: format hợp lệ chưa chứng minh header đến từ nguồn tin cậy.

Lab này không đủ bảo đảm an ninh cho mọi logger/proxy; cần xem các sink khác, cấu trúc JSON encoding, MDC cleanup và kiểm thử tích hợp.

## 13. Log injection và cardinality attacks

Một attacker có thể nhập vào username:

~~~text
alice
2026-11-06 INFO auth_event=AUTH_SUCCESS user=admin
~~~

Nếu ứng dụng viết:

~~~java
// Sai: nối raw input vào dòng log.
log.info("Login failed for " + userSuppliedUsername);
~~~

thì ký tự xuống dòng có thể giả tạo một record “AUTH_SUCCESS”. Với JSON logger, dữ liệu không escape đúng cũng có thể làm hỏng schema hoặc đánh lừa dashboard; với logfmt có thể chèn dấu phân cách tạo trường giả.

Cần:

- Ưu tiên **structured logging** sử dụng logger/encoder tạo JSON đúng chuẩn, không xây JSON bằng nối chuỗi.
- Dùng enum/allowlist cho `eventType`, `reasonCode`, `authenticationMethod`.
- Kiểm giới hạn độ dài cho request ID/URL/path/reason, reject control characters (CR, LF, NULL, tab khi không cho phép).
- Không tin `Host`, `X-Forwarded-For`, `User-Agent`, baggage hoặc header correlation như giá trị an toàn chỉ vì framework đã parse.
- Không cho phép một attacker tạo vô hạn label riêng như mỗi email một Prometheus label: **high cardinality** có thể làm telemetry quá tải.
- Có rate limiting/backpressure cho event sink để flood login attempts không làm cạn disk, queue hoặc SIEM quota.

**Structured JSON không thay thế minimization.** Một encoder escape hoàn hảo vẫn gây rò rỉ nếu ứng dụng gửi `Authorization` hoặc password vào JSON field.

## 14. Sơ đồ xử lý login/audit có trust boundary rõ ràng

~~~text
External client (untrusted)
      |
      | POST /login
      v
Trusted ingress/gateway
      | strip untrusted forwarding/correlation headers
      | choose public host, maybe requestId/trace context
      v
Servlet request correlation filter
      | attach trusted requestId; MDC
      v
Spring Security AuthenticationManager
      | verify credential/account/policy
      +--> success/failure event publisher
      |         |
      |         v
      |     event listener / audit adapter
      |         | sanitize + allowlist fields
      |         +--> trusted async queue / secure audit store
      v
HTTP success/failure handler
      | generic client messaging, session/token policy
      v
Response with opaque X-Request-ID
      |
      v
Filter finally: clear/restore MDC thread scope
~~~

Trong kiến trúc nhiều service, tracing context được propagation riêng và phải được cấu hình an toàn. `requestId` có thể giúp support tra một request cụ thể; nhưng muốn biết một giao dịch cần xem log gì, server phải dùng RBAC và audit quyền truy cập log.

**Đừng dùng trực tiếp header từ request để xác định actor hay outcome.** Actor được xác định sau khi Authentication thành công từ server-side identity. Trước khi auth, mọi username là **claimed identifier**, không phải verified principal.

## 15. Một login event có thể chứa danh tính nào?

| Flow | Principal đáng tin tại thời điểm đó | Cách log phù hợp |
| --- | --- | --- |
| Login password thất bại | Không có authenticated user | AUTH_FAILURE, reasonCode, requestId; không raw username |
| Login password thành công | Authentication đã xác minh | AUTH_SUCCESS, opaque principalRef nếu cần |
| Passkey assertion không hợp lệ | Chưa xác thực credential | TOKEN/CREDENTIAL_INVALID, không khẳng định account |
| OIDC callback thành công | Subject được ID Token/UserInfo xác minh theo policy | Auth method OIDC, issuer/subject reference được kiểm và giảm PII |
| API key hợp lệ | App/service/account theo metadata được server xác minh | principalType, opaque keyId đã cấp, không raw key |
| Refresh token thất bại | Token bị từ chối | TOKEN_INVALID, không log raw token |
| Logout | Phiên/session context nếu đã xác thực | LOGOUT_COMPLETED, không raw session id |
| Account lock triggered by policy | Server biết account trạng thái nào | Internal audit event; không công khai trạng thái |

Nếu cần field `principalRef`, ưu tiên ID nội bộ **không trực tiếp là email/phone**, nhưng nó vẫn có thể là dữ liệu cá nhân theo ngữ cảnh. Hạn chế truy vấn ngược và quyền truy cập.

**Không dùng `getName()` trên Authentication object thất bại làm bằng chứng rằng người này đã login.** Đó có thể là giá trị client cố tình nhập hoặc token chưa xác minh.

## 16. Thiết lập log level và làm sạch debug logs

Spring Security có nhiều logger/cấp độ DEBUG/TRACE hữu ích khi chẩn đoán, nhưng cần kiểm soát:

~~~properties
# Ví dụ chính sách bình thường; điều chỉnh theo hệ thống thật.
logging.level.org.springframework.security=INFO
logging.level.demo.authlogging=INFO
~~~

Không bật trace toàn bộ request body/headers để “nhìn rõ token”. Nếu cần debug tạm:

1. Có ticket hoặc incident ID, chủ sở hữu và thời hạn tự tắt.
2. Chỉ bật tại service/endpoint không chứa credential hoặc dùng custom safe logging.
3. Kiểm logs generated thật trước khi bật diện rộng.
4. Bảo vệ quyền truy cập vào aggregator và export.
5. Theo dõi log volume/retention/cost.
6. Xóa/thu hồi các bản sao nhạy cảm theo quy định nếu phát hiện secret leak.
7. Sau sự cố, xem có cần rotate/revoke credentials đã lộ hay không.

**Không mặc định mọi Spring Security DEBUG line đều lộ bí mật.** Nội dung tùy logger và version. Điều cần làm là kiểm cụ thể pipeline và không cấu hình dump headers/body ở nơi chứa credential.

## 17. Bảo vệ log tập trung và tính toàn vẹn

Một hệ thống nhiều service thường gửi logs tới Fluent Bit/OpenTelemetry Collector/SIEM hoặc một log platform tương đương. Các điều kiện cần:

| Nguy cơ | Phương án |
| --- | --- |
| Người không có thẩm quyền đọc login events | RBAC theo vai trò, least privilege, review định kỳ |
| Insider export toàn bộ email/IP | Audit truy cập log, giới hạn export/download, approval nếu cần |
| Attacker sửa/xóa log sau khi chiếm host | Remote append-only/WORM khi phù hợp, integrity checks |
| Log collector truyền plaintext | TLS/mTLS hoặc kênh transport được bảo vệ |
| Lưu log không giới hạn | Retention policy, xóa tự động và backup lifecycle |
| Credential lọt vào log | Redaction tại nguồn + detection/quarantine và revocation |
| SIEM quá tải do login flood | Rate limit/event aggregation/backpressure mà không mất audit bắt buộc |
| Ingestion parser bị log injection | Structured JSON, escape/validation, schema validation |
| Đồng hồ các node lệch | NTP và UTC timestamp, lưu service/host metadata |
| Log và metrics bị pha lẫn | Correlation IDs chung, quyền truy cập và retention khác nhau |

Đối với audit có yêu cầu pháp lý, kiểm tra quy định, hợp đồng và privacy policy áp dụng; **không tự gán một số ngày retention cố định** chỉ vì một ví dụ hoặc tiêu chuẩn công khai. Việc xóa dữ liệu phải bao gồm các bản backup/replica/export theo chính sách đã phê duyệt.

Một correlation ID được công khai cho support **không trao quyền** cho support hoặc bất kỳ người nào để truy xuất toàn bộ audit records. Truy vấn log phải dựa trên RBAC, mục đích xử lý và record-level restrictions.

## 18. Truy tìm sự cố bằng requestId, traceId và eventId

Tình huống: người dùng báo “Tôi đăng nhập thất bại lúc 10:15 nhưng không rõ vì sao”.

Quy trình điều tra:

1. Thu **requestId** từ response/screenshot hoặc tìm trong khoảng thời gian, không yêu cầu người dùng gửi password/token.
2. Tra logs của gateway và identity service theo requestId/traceId.
3. Xác định `AUTH_FAILURE` và **reasonCode nội bộ** đã được allowlist, ví dụ PROVIDER_ERROR.
4. Xem spans liên quan directory/IdP (nếu có) để phân biệt outage với credential errors.
5. Đối chiếu metrics (failure rate, provider latency, error budget).
6. Nếu cần chi tiết account, truy vấn hệ thống danh tính qua quyền được cấp, không suy từ raw username input trong log.
7. Ghi incident record, hành động remediation và hạn chế việc sao chép log đầy đủ vào ticket công khai.

Nếu `reasonCode=BAD_CREDENTIALS`, không suy ngay rằng người dùng cố tình nhập sai: có thể client dùng token hết hạn, provider mapping sai hoặc bị automation. Dùng nhiều tín hiệu và kiểm service implementation.

Nếu trace sampling không giữ span, sự kiện audit vẫn cần có timestamp/service/eventId/requestId đủ để điều tra. Không coi thiếu trace là chứng cứ “không hề có request”.

## 19. Metrics và cảnh báo: tránh lộ PII qua labels

Các metrics hữu ích:

| Metric | Tags nên dùng | Tags không nên dùng |
| --- | --- | --- |
| `auth_attempt_total` | outcome, method, service, environment | Raw username, email, token |
| `auth_failure_total` | reasonCode allowlist, provider class | Exception message, sessionId |
| `auth_latency_seconds` | method, outcome | Request ID mỗi lần (cardinality quá cao) |
| `idp_error_total` | provider name allowlist | URL đầy đủ chứa query/credential |
| `mfa_stepup_total` | result, method | Raw user ID hoặc OTP |
| `security_audit_sink_failure_total` | sink, errorCategory | Toàn bộ event payload |

Không sử dụng mỗi requestId/traceId như label của Prometheus counter/histogram; số lượng chuỗi gần như vô hạn gây high cardinality. Những ID đó thuộc **log/tracing fields**, không phải dimension metrics.

Alert dựa trên tỷ lệ/thời gian:

- Credential failures tăng trên một nguồn hoặc endpoint (với bảo vệ privacy);
- Provider errors tăng cùng latency IdP;
- Một principal đã xác minh phát sinh nhiều thiết bị/địa điểm bất thường theo policy;
- Audit pipeline ngừng gửi hoặc retry kéo dài;
- Tốc độ login bất thường và tỷ lệ MFA failures tăng;
- Không còn request IDs hoặc thiếu trace correlation bất thường sau deploy.

Một sự kiện “login failure” không đủ để xác định tấn công; thiết kế ngưỡng và điều tra tín hiệu tổng hợp tránh false positive.

## 20. Kiểm thử unit: bảo đảm không đưa secret vào event

Với Java 17 demo ở mục 12, kiểm các trường hợp:

| Input | Expected |
| --- | --- |
| UUID do server tạo | Đúng định dạng, không dựa username |
| Reason known | Giữ enum code |
| Reason không biết | `AUTH_OTHER` |
| Raw reason chứa password | Bị thay `AUTH_OTHER` |
| External ID chứa CR/LF | `REJECTED` |
| Event line | Không chứa raw password/email |
| Trường user nhập rất dài | Bounded/reject theo policy |
| Field không có trong allowlist | Không đi vào event |
| Null/empty header | Không suy principal |
| Unicode/control payload | JSON encoder/validation giữ log hợp lệ |

Mục tiêu không phải chỉ `assertFalse(log.contains("password"))`, vì password thật có thể có nhiều dạng và được encode. Nên **kiểm schema allowlist** để xác nhận trường `password` hoặc `credentials` không thể được serialize, kết hợp scanning canary secrets trong integration test.

## 21. Kiểm thử Spring Security event và MDC

Với Spring Boot Test hoặc integration test có logging capture (ví dụ Logback test appender hoặc Spring Boot `OutputCaptureExtension`):

1. Dựng một authentication attempt hợp lệ bằng test credential.
2. Gửi request qua full Spring Security filter chain.
3. Kiểm một event thành công thuộc loại mong đợi (hoặc số event thực tế theo policy).
4. Gửi request sai credential và kiểm event category là FAILURE.
5. Đảm bảo cùng requestId xuất hiện trong các dòng đồng bộ của request.
6. Kiểm response header `X-Request-ID` có định dạng UUID và không chứa username/token.
7. Kiểm logs không chứa canary password, bearer token, Cookie, reset token, raw request body.
8. Gửi request B sau A trên cùng Servlet worker (hoặc test có kiểm thread reuse) và khẳng định requestId của A không bị dùng cho B.
9. Ép controller/filter ném exception và kiểm MDC vẫn dọn trong `finally`.
10. Nếu có ASYNC/ERROR dispatch, kiểm ID được giữ đúng trong cùng request và MDC không leak sang request khác.
11. Nếu có tracing, kiểm traceId/spanId đúng khi instrumentation bật; không buộc mọi test có span nếu tracing tắt.
12. Kiểm failure message trả client vẫn generic, không phản ánh internal reason/account state.

Mảnh test MockMvc/JUnit minh họa (cần test application, imports, assertion libraries):

~~~java
var first = mockMvc.perform(post("/login")
        .param("username", "lan")
        .param("password", "wrong-password")
        .with(csrf()))
        .andReturn().getResponse();

String firstId = first.getHeader("X-Request-ID");
assertNotNull(firstId);
assertTrue(firstId.matches("[0-9a-fA-F-]{36}"));

var second = mockMvc.perform(post("/login")
        .param("username", "lan")
        .param("password", "another-wrong-password")
        .with(csrf()))
        .andReturn().getResponse();

assertNotEquals(firstId, second.getHeader("X-Request-ID"));
~~~

Đây **không phải class Java chạy độc lập**. Nó cần `MockMvc` có Spring Security filters, `spring-security-test` với `csrf()`, FilterRegistrationBean thực, JUnit 5, và login endpoint được cấu hình. Thêm assertions capture log/event và cùng-thread cleanup; hai response IDs khác nhau **không tự chứng minh** MDC đã được dọn trên worker thread.

### Test rò MDC bằng task tái sử dụng thread

Nếu muốn kiểm thật sự thread cleanup, dùng single-thread executor hoặc test instrumentation để chạy hai tasks liên tiếp **trên cùng thread**. Nhìn vào `MDC.get("requestId")` sau task A kết thúc, trước task B bắt đầu; phải trống hoặc khôi phục đúng scope đã định.

Không dùng đơn thuần hai requests MockMvc liên tiếp rồi kết luận chúng chắc chắn cùng thread Servlet trong deployment thật. Cấu trúc test phải làm rõ thread ownership.

## 22. Kiểm thử negative và abuse cases

| Trường hợp | Expected behavior |
| --- | --- |
| Username có CR/LF hoặc JSON escape | Không tạo log entry giả |
| Password chứa chuỗi canary | Không có trong mọi sinks/log captures |
| Bearer token invalid | Có TOKEN_INVALID event, không in token |
| Session cookie | Không xuất hiện raw trong event/trace |
| Header X-Request-ID trùng/malformed | Không được tin; server ID mới |
| X-Forwarded-For giả | Không được ghi như IP đã xác minh |
| Trace baggage chứa email | Không forward/log PII trái chính sách |
| API key dùng cho service | Log key ID công khai được cấp nếu cần, không log secret |
| Password login account không tồn tại | Không lộ user existence qua client response |
| Login success nhưng MFA chưa xong | Không tự đếm LOGIN_COMPLETED |
| Provider outage | Reason PROVIDER_ERROR, không biến thành BAD_CREDENTIALS |
| Access denied 403 | Không nhầm với login failure |
| Audit sink unavailable | Fail-closed hoặc degradation theo policy được phê duyệt; có alert |
| Login attempt flood | Không làm cạn disk/SIEM; vẫn có tín hiệu an ninh cần thiết |
| Export logs | RBAC, retention và access audit được áp dụng |
| Service restart | Không đánh mất audit bắt buộc nếu pipeline có yêu cầu durability |

**Fail-closed hay degradation?** Không có một câu trả lời chung. Một sản phẩm tài chính có thể yêu cầu ghi audit bền vững trước khi cho thao tác nhạy cảm thành công; một dịch vụ khác có thể tiếp tục login khi log platform mất để giữ availability, nhưng phải có queue, alert và xử lý hậu kiểm. Quyết định phải được ghi trong security/compliance requirements, không để phụ thuộc vào exception ngẫu nhiên trong một listener đồng bộ.

## 23. Vận hành an toàn trong kiến trúc microservices

Khi request đi từ gateway tới nhiều services, cần:

- Có **một chính sách correlation** rõ: dùng request ID riêng cùng distributed trace, hoặc thống nhất cách liên kết.
- Gateway chỉ tin trace/request metadata theo quy tắc cụ thể; downstream không coi giá trị từ Internet là authenticated.
- Trace propagation bằng instrumentation chuẩn thay vì tự copy mọi MDC key sang Kafka headers.
- Async messaging: đưa opaque correlation metadata có allowlist vào message; không kèm password, session cookie hoặc PII mặc định.
- Consumer tạo span/event mới phù hợp nhưng giữ liên kết parent/correlation khi được phép.
- Tránh rò khi một thread xử lý nhiều messages; MDC cleanup đặt trong `finally` tại consumer boundary.
- Định nghĩa audit owner: service nào phát AUTHORITATIVE event để tránh ghi trùng mỗi khi gateway/service đều thấy login.
- Deduplicate bằng `eventId` khi audit sink retry; hiểu at-least-once delivery và không mặc định exactly-once.
- Cân bằng retention khác nhau: tracing có thể giữ ít ngày, audit nghiệp vụ lâu hơn theo chính sách.
- Có runbook điều tra theo requestId/traceId/eventId, không dùng user-supplied claims làm nguồn kết luận.

Nếu phải liên kết một user qua nhiều services, sử dụng subject ID được issuer/identity provider xác minh và scope phù hợp. Correlation ID **không chứng minh user**; nó chỉ kết nối những bản ghi.

## 24. Các lỗi vận hành phổ biến

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Log `Authentication.toString()` | Có thể lộ principal/metadata nhạy cảm | Ghi event type/outcome và opaque ref tối thiểu |
| Log exception message không kiểm | PII/credential hoặc log forging | Reason code allowlist, exception category |
| Log toàn bộ headers/body | Lộ password/token/cookie | Allowlist fields, disable sensitive body logging |
| Dùng username làm request ID | Rò PII và dễ bị giả | Server-generated UUID |
| Tin inbound X-Request-ID | Log spoofing/correlation poisoning | Strip/generate/trust boundary rõ |
| Không dọn MDC | Bob nhận request ID của Alice | `finally`/wrapper cleanup |
| MDC mất trong async | Thiếu correlation ở worker | Tracing/context propagation theo runtime |
| Dùng MDC ThreadLocal trong WebFlux không có bridge | Context sai khi scheduler đổi thread | Reactor/tracing instrumentation phù hợp |
| Map mọi exception là BAD_CREDENTIALS | Outage bị đếm là credential attack | Reason taxonomy đúng |
| Dùng AUTH_SUCCESS thay LOGIN_COMPLETED | MFA flows bị đếm sai | Định nghĩa event ở đúng boundary |
| Dùng requestId làm Prometheus label | High cardinality | Để ID trong log/trace, metrics dùng enum tags |
| Tin X-Forwarded-For từ Internet | IP audit bị giả | Proxy trust configuration |
| Giữ log mãi | Privacy/cost/compliance risk | Retention + deletion policy |
| Audit chỉ ở in-memory listener | Mất dữ liệu khi crash | Durable audit pipeline nếu bắt buộc |
| Log exporter dùng quyền quá rộng | Rò hàng triệu identity records | Least privilege/access audit |
| Debug bật không thời hạn | Tăng risk và log volume | Change control/expiry/monitor |
| Masking chỉ ở dashboard | Secret đã vào storage rồi | Redact tại source |
| In trace baggage toàn bộ claims | PII trôi qua services | Allowlist và hạn chế baggage |

## 25. Checklist áp dụng

1. Có schema chuẩn cho AUTH_SUCCESS/FAILURE, MFA, logout, session revoke và authorization denied không?
2. Có phân biệt `eventId`, `requestId`, `traceId`, `spanId` và session/token ID?
3. Có bảo đảm không log raw password, OTP, cookie, access/refresh token, reset token hoặc authorization header?
4. Log failure có dùng reason codes do backend xác định và tránh raw username/exception message?
5. Có kiểm trường dữ liệu cá nhân nào là thật sự cần, ai được xem và retention bao lâu?
6. Mã tương quan có do server/gateway tin cậy tạo, không phụ thuộc user input và không cấp quyền?
7. Servlet filter/MDC có cleanup trong finally và xử lý ASYNC/ERROR dispatch đúng cấu hình?
8. Async executors, Kafka consumer, WebFlux và tracing có propagation/cleanup đúng mô hình?
9. Có bảo vệ log integrity, encrypt in transit/at rest, RBAC, audit export và backup retention?
10. Có test log injection, canary secrets, correlation qua services, metric cardinality và filter exceptions?
11. Có đo delivery failures, log sink outages, sampling và duplicate events theo policy?
12. Có runbook điều tra sự cố mà không yêu cầu người dùng gửi credential?

**Kết luận:** Nhật ký đăng nhập có ích khi nó giữ được **ngữ cảnh và tính chính xác**, nhưng bảo mật chỉ đạt được khi nó đồng thời **giảm tối đa dữ liệu cá nhân và loại bỏ bí mật**. Spring Security cung cấp authentication events; Spring Boot/Micrometer có thể hỗ trợ trace correlation; MDC có thể gắn request ID trong Servlet thread. Mỗi cơ chế có ranh giới riêng. Thiết kế tốt cần schema có kiểm soát, IDs opaque, nguồn dữ liệu đáng tin, cleanup đúng thread/subscription, audit bền vững khi bắt buộc, kiểm soát truy cập và kiểm thử chống leak. **Không bao giờ đánh đổi credential của người dùng lấy vài dòng debug dễ đọc hơn.**

### Tài liệu tham khảo

- OWASP — Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP — Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP — Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- Spring Security — Authentication Events: https://docs.spring.io/spring-security/reference/servlet/authentication/events.html
- Spring Security — Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — Security Filter Chain: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Boot — Tracing and Logging Correlation IDs: https://docs.spring.io/spring-boot/reference/actuator/tracing.html
- Spring Framework — OncePerRequestFilter API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html
- SLF4J — MDC API: https://www.slf4j.org/apidocs/org/slf4j/MDC.html
- OpenTelemetry — Context Propagation: https://opentelemetry.io/docs/concepts/context-propagation/
