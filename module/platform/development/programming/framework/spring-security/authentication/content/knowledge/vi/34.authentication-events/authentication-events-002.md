# Sự kiện thành công và nhóm sự kiện xác thực thất bại

## 1. Mục tiêu bài học

Trong Spring Security, việc đăng nhập bằng password, kiểm tra bearer token hoặc gọi một `AuthenticationManager` có thể dẫn tới **sự kiện xác thực thành công** hoặc **sự kiện xác thực thất bại**. Các Spring application events giúp ghi audit, theo dõi sai mật khẩu, phát hiện bất thường và giám sát sự cố của backend xác thực mà không buộc mỗi controller tự triển khai logging.

Những khái niệm trọng tâm:

- `AuthenticationSuccessEvent`: phản ánh một lần xác thực thành công khi `AuthenticationEventPublisher` được dùng.
- `AbstractAuthenticationFailureEvent`: lớp cơ sở cho các sự kiện thất bại như sai credentials, tài khoản disabled/locked/expired hoặc backend lỗi.
- `DefaultAuthenticationEventPublisher`: ánh xạ `AuthenticationException` sang các event classes rồi phát qua Spring `ApplicationEventPublisher`.
- `@EventListener`: cách lắng nghe sự kiện trong Spring container.

**Phân biệt quan trọng:** một HTTP `200` không đồng nghĩa một lần login mới; một HTTP `401` không chắc tạo failure event; và một `403` do thiếu quyền là **authorization denial**, không phải lỗi xác thực.

Các sự kiện cung cấp thông tin phục vụ quan sát và audit, **không tự chặn tấn công, không tự cấp quyền, không tự đảm bảo lưu bền vững**. Kiểm soát bắt buộc như rate limiting, account lockout, MFA và phân quyền phải được đặt ở enforcement path phù hợp.

## 2. Kiến trúc phát sự kiện

~~~text
Browser / API client
       |
       v
Authentication filter
       |
       v
AuthenticationManager (thường là ProviderManager)
       |
       +--> AuthenticationProvider A
       +--> AuthenticationProvider B ...
       |
       +-- successful Authentication
       |        |
       |        v
       |   AuthenticationEventPublisher
       |        |
       |   AuthenticationSuccessEvent
       |
       +-- final AuthenticationException
                |
                v
          DefaultAuthenticationEventPublisher
                |
          AbstractAuthenticationFailureEvent subclass
                |
                v
         Spring ApplicationEventPublisher
                |
         @EventListener / ApplicationListener
                |
         Audit / metrics / detection
~~~

`AuthenticationProvider` kiểm tra credential hoặc token và trả `Authentication` hợp lệ, `null` nếu không xử lý, hoặc ném một `AuthenticationException`. `ProviderManager` phối hợp các providers để ra **kết quả cuối cùng**. Không giả định một lỗi từ provider A chắc chắn phát failure event nếu provider B sau đó xác thực thành công.

Theo API Spring Security 6.x, `ProviderManager` ủy nhiệm sự kiện cho một `AuthenticationEventPublisher` đã cấu hình; nếu tự tạo manager nhưng không gán publisher, bạn có thể không nhận sự kiện. Với parent manager, tránh để cả parent và child cùng publish dẫn đến trùng số liệu.

Các handlers của filter (`AuthenticationSuccessHandler`, `AuthenticationFailureHandler`) điều khiển HTTP redirect/status sau login, **khác** với application-event publisher. Listener có thể chạy cả trong flow không dùng Servlet.

## 3. Sự kiện xác thực thành công

`AuthenticationSuccessEvent` thuộc package `org.springframework.security.authentication.event` và có thể truy cập đối tượng xác thực qua `getAuthentication()`.

Ví dụ audit schema **do ứng dụng tự định nghĩa**, không phải payload Spring tự sinh:

~~~json
{
  "eventId": "evt-s01",
  "outcome": "SUCCESS",
  "eventType": "AuthenticationSuccessEvent",
  "principalRef": "usr-1042",
  "mechanism": "PASSWORD",
  "occurredAt": "2026-11-06T09:00:00Z",
  "correlationId": "req-a42"
}
~~~

Một success event nói rằng **AuthenticationManager đã chấp nhận authentication theo provider**. Nó không tự chứng minh:

- Browser đã tạo cookie HTTP session mới.
- Người dùng vừa nhập mật khẩu tại thời điểm phát event; resource server có thể chỉ đang kiểm tra access token.
- MFA đã hoàn thành hoặc có assurance cao, nếu flow chỉ mới qua password phase.
- Tài khoản được cấp mọi role, hoặc request tiếp theo được phép xem mọi tài nguyên.
- Đây là user login duy nhất; API stateless có thể xác thực token trên từng request.

Trong thống kê, hãy ghi rõ **authentication mechanism, source và semantics**. Nếu dashboard muốn đếm *human interactive logins*, không được đếm mọi success của JWT bearer token như một lần người dùng đăng nhập.

### `InteractiveAuthenticationSuccessEvent`

Spring Security có class `InteractiveAuthenticationSuccessEvent` biểu thị xác thực tương tác thành công trong một số web flows. Nó **không kế thừa `AuthenticationSuccessEvent`**, vì API thiết kế để tránh gửi duplicate `AuthenticationSuccessEvent` tới một listener của class đó. Nếu muốn đếm browser-login completions, kiểm tra đúng filter/flow và xử lý hai loại event theo mục tiêu đo lường, không tự cộng cả hai.

## 4. Cây kế thừa nhóm thất bại

Ở Spring Security 6.x, lắng nghe `AbstractAuthenticationFailureEvent` để nhận các subclass.

~~~text
AbstractAuthenticationEvent
|
+-- AuthenticationSuccessEvent
+-- InteractiveAuthenticationSuccessEvent
|
+-- AbstractAuthenticationFailureEvent
    |
    +-- AuthenticationFailureBadCredentialsEvent
    +-- AuthenticationFailureDisabledEvent
    +-- AuthenticationFailureLockedEvent
    +-- AuthenticationFailureExpiredEvent
    +-- AuthenticationFailureCredentialsExpiredEvent
    +-- AuthenticationFailureProviderNotFoundEvent
    +-- AuthenticationFailureServiceExceptionEvent
    +-- AuthenticationFailureProxyUntrustedEvent
    +-- Custom failure events ...
~~~

Các failure events kế thừa `getAuthentication()` và có `getException()`. Với failure, `Authentication` là **authentication attempt**, không phải principal đã được xác minh; có thể có username chưa được chứng thực hoặc dữ liệu nhạy cảm trong credentials/details. Không ghi nguyên object ra log.

Tên `AbstractAuthenticationFailureEvent` là API cần dùng trong code mới. Các bản tài liệu rất cũ có thể đề cập `AuthenticationFailureEvent`; tránh dựa trên tên của một tài liệu khác phiên bản mà không kiểm tra import/class thực tế.

## 5. Ánh xạ mặc định: exception nào cho event nào?

Trong tài liệu Spring Security 6.5, `DefaultAuthenticationEventPublisher` có các mapping mặc định:

| Exception được ném | Sự kiện | Diễn giải |
|---|---|---|
| `BadCredentialsException` | `AuthenticationFailureBadCredentialsEvent` | Credential không hợp lệ. |
| `UsernameNotFoundException` | `AuthenticationFailureBadCredentialsEvent` | User lookup thất bại, gom về bad credentials. |
| `InvalidBearerTokenException` | `AuthenticationFailureBadCredentialsEvent` | Bearer token không hợp lệ khi flow đi qua publisher tương ứng. |
| `DisabledException` | `AuthenticationFailureDisabledEvent` | Account disabled. |
| `LockedException` | `AuthenticationFailureLockedEvent` | Account locked. |
| `AccountExpiredException` | `AuthenticationFailureExpiredEvent` | Account quá hạn. |
| `CredentialsExpiredException` | `AuthenticationFailureCredentialsExpiredEvent` | Credential đã hết hạn. |
| `ProviderNotFoundException` | `AuthenticationFailureProviderNotFoundEvent` | Không có provider hỗ trợ loại `Authentication`. |
| `AuthenticationServiceException` | `AuthenticationFailureServiceExceptionEvent` | Lỗi dịch vụ/xác thực nội bộ. |

`AuthenticationFailureProxyUntrustedEvent` cũng là class hợp lệ, liên quan tình huống CAS proxy không đáng tin; **không khẳng định nó xuất hiện mặc định trong mọi ứng dụng**.

Điểm dễ bỏ sót: publisher dùng **exact exception-class match**. Nếu một custom exception kế thừa `BadCredentialsException`, nó **không tự nhận mapping của lớp cha**. Cần khai báo `setAdditionalExceptionMappings(...)` hoặc một failure event dự phòng (fallback) đã cấu hình, rồi test.

Ngoài ra, không phải mọi failure ở filter đều đến từ một `AuthenticationManager` có publisher: request thiếu token, lỗi phân tích header bị chặn trước manager hoặc custom filter tự xử lý có thể không tạo event này.

## 6. Chuẩn hóa nhóm lỗi để giám sát và ứng phó

| Category nội bộ | Event | Cách dùng |
|---|---|---|
| `SUCCESS` | `AuthenticationSuccessEvent` | Theo dõi login/kiểm tra token thành công với đúng mechanism. |
| `INVALID_CREDENTIALS` | `AuthenticationFailureBadCredentialsEvent` | Tín hiệu credential guessing/invalid token. |
| `ACCOUNT_DISABLED` | `AuthenticationFailureDisabledEvent` | Thử truy cập tài khoản đã disabled. |
| `ACCOUNT_LOCKED` | `AuthenticationFailureLockedEvent` | Thử trên tài khoản đang locked. |
| `ACCOUNT_EXPIRED` | `AuthenticationFailureExpiredEvent` | Account hết hiệu lực. |
| `CREDENTIALS_EXPIRED` | `AuthenticationFailureCredentialsExpiredEvent` | Cần đổi credential hoặc re-enroll. |
| `NO_AUTH_PROVIDER` | `AuthenticationFailureProviderNotFoundEvent` | Sai AuthenticationProvider/filter chain configuration. |
| `AUTH_SYSTEM_ERROR` | `AuthenticationFailureServiceExceptionEvent` | Outage của DB/LDAP/IdP/verifier. |
| `PROXY_NOT_TRUSTED` | `AuthenticationFailureProxyUntrustedEvent` | CAS/trust configuration đặc thù. |
| `CUSTOM_POLICY_FAILURE` | Event custom của ứng dụng. | Tenant/device/risk/assurance theo policy riêng. |

Đây là taxonomy **do hệ thống định nghĩa**, độc lập với tên Spring class. Mục đích là phân biệt **thử đoán mật khẩu** với **lỗi cấu hình hoặc backend outage**, để cảnh báo đúng và không vô tình lock account vì service bị mất kết nối.

Một `AuthenticationFailureLockedEvent` cũng **không chứng minh** chính request vừa làm account bị khóa. Nó có thể chỉ phát sinh khi user cố đăng nhập vào account đã locked từ trước.

## 7. Cấu hình publisher trong Spring Security

Ví dụ Spring Boot 3.x / Spring Security 6.x:

~~~java
package example.security;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;

@Configuration
public class AuthenticationEventConfiguration {
    @Bean
    AuthenticationEventPublisher authenticationEventPublisher(
            ApplicationEventPublisher publisher) {
        return new DefaultAuthenticationEventPublisher(publisher);
    }
}
~~~

`DefaultAuthenticationEventPublisher` chuyển kết quả xác thực thành Spring application events khi manager dùng publisher này. **Kiểm tra bean hiện tại** trước khi tạo bean mới: một số cấu hình Spring Boot/Spring Security đã có publisher hoặc custom manager. Không tạo hai bean cùng purpose rồi cho rằng framework sẽ tự chọn đúng hoặc tự deduplicate.

Nếu dự án tự tạo `ProviderManager` ngoài framework:

~~~java
// Integration snippet, không phải Java độc lập:
ProviderManager manager = new ProviderManager(providerA, providerB);
manager.setAuthenticationEventPublisher(authenticationEventPublisher);
~~~

`providerA`/`providerB` phải là `AuthenticationProvider` thực, và `authenticationEventPublisher` phải là object được nối với Spring application context. Không chỉ tạo `new DefaultAuthenticationEventPublisher()` mà quên cung cấp `ApplicationEventPublisher` rồi mong listener nhận event.

**Cấu hình đúng được chứng minh bằng test qua authentication flow thực**, không chỉ bằng việc bean tồn tại.

## 8. Lắng nghe bằng `@EventListener`

Có thể xử lý cả success lẫn failure trong một component:

~~~java
package example.security;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.security.authentication.event.AuthenticationFailureBadCredentialsEvent;
import org.springframework.security.authentication.event.AuthenticationFailureDisabledEvent;
import org.springframework.security.authentication.event.AuthenticationFailureLockedEvent;
import org.springframework.security.authentication.event.AuthenticationFailureServiceExceptionEvent;

@Component
public class AuthenticationEventObserver {

    @EventListener
    public void onSuccess(AuthenticationSuccessEvent event) {
        String mechanism =
                event.getAuthentication().getClass().getSimpleName();
        safeAudit("SUCCESS", mechanism);
    }

    @EventListener
    public void onFailure(AbstractAuthenticationFailureEvent event) {
        String category;
        if (event instanceof AuthenticationFailureBadCredentialsEvent) {
            category = "INVALID_CREDENTIALS";
        } else if (event instanceof AuthenticationFailureDisabledEvent) {
            category = "ACCOUNT_DISABLED";
        } else if (event instanceof AuthenticationFailureLockedEvent) {
            category = "ACCOUNT_LOCKED";
        } else if (event instanceof AuthenticationFailureServiceExceptionEvent) {
            category = "AUTH_SYSTEM_ERROR";
        } else {
            category = "OTHER_AUTH_FAILURE";
        }
        safeAudit(category,
                event.getException().getClass().getSimpleName());
    }

    private void safeAudit(String category, String source) {
        // Tích hợp audit/metrics đã kiểm soát tại ứng dụng.
        // Không ghi full Authentication, credentials, token hay PII.
    }
}
~~~

Đây là **integration snippet**, không phải executable Java standalone: method `safeAudit` hiện là no-op minh họa, project phải nối với audit sink đáng tin và kiểm tra policies. Sử dụng `AbstractAuthenticationFailureEvent` giúp nhận tất cả failure subclasses. Có thể tiếp tục phân loại `AuthenticationFailureCredentialsExpiredEvent`, `AuthenticationFailureExpiredEvent`, `AuthenticationFailureProviderNotFoundEvent` nếu cần taxonomy đầy đủ.

Nếu listener vừa nhận `AbstractAuthenticationFailureEvent` vừa có listener khác nhận subclass, cùng một sự kiện có thể đi đến cả hai listener. Muốn **một bản ghi audit cho một kết quả** thì nên thống nhất một lớp điều phối hoặc dùng eventId/deduplication rõ ràng.

## 9. Tùy chỉnh exception mapping theo ứng dụng

Giả sử có policy chặn credential của một thiết bị không hợp lệ. Để tránh gộp nó thành sai password, tạo exception riêng:

~~~java
package example.security;

import org.springframework.security.core.AuthenticationException;

public final class DevicePolicyException extends AuthenticationException {
    public DevicePolicyException(String message) {
        super(message);
    }
}
~~~

Tạo event riêng kế thừa lớp abstract:

~~~java
package example.security;

import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;

public final class AuthenticationFailureDevicePolicyEvent
        extends AbstractAuthenticationFailureEvent {
    public AuthenticationFailureDevicePolicyEvent(
            Authentication authentication, AuthenticationException exception) {
        super(authentication, exception);
    }
}
~~~

Sau đó dùng **một bean publisher đã cấu hình**, thay vì tạo publisher thứ hai:

~~~java
@Bean
AuthenticationEventPublisher authenticationEventPublisher(
        ApplicationEventPublisher publisher) {
    DefaultAuthenticationEventPublisher result =
            new DefaultAuthenticationEventPublisher(publisher);
    result.setAdditionalExceptionMappings(
        java.util.Map.of(
            DevicePolicyException.class,
            AuthenticationFailureDevicePolicyEvent.class
        )
    );
    return result;
}
~~~

Các imports của bean đã trình bày trong phần 7; ví dụ này **thay thế** phiên bản bean cơ bản và cần để các public classes vào tệp riêng. `setAdditionalExceptionMappings(Map)` mở rộng mapping mặc định, không phải xóa toàn bộ mappings.

Spring còn có `setDefaultAuthenticationFailureEvent(...)` cho các `AuthenticationException` không có mapping; hãy sử dụng một **concrete event subclass** có constructor `(Authentication, AuthenticationException)` phù hợp và kiểm thử. Không truyền một abstract class chỉ vì tên nó bao quát mọi lỗi.

**Đặc biệt:** một subclass của `BadCredentialsException` phải khai báo mapping riêng nếu muốn bảo đảm phát sự kiện. Không dùng tên exception trùng ngẫu nhiên hoặc suy từ HTTP status để phân loại.

## 10. Auth success event khác success handler và HTTP response

| Thành phần | Nhiệm vụ |
|---|---|
| `AuthenticationSuccessEvent` | Thông báo một kết quả xác thực thành công từ event publisher. |
| `AuthenticationSuccessHandler` | Redirect/trả HTTP response sau browser authentication filter success. |
| `AuthenticationFailureHandler` | Trả lỗi/redirect/flash messages sau filter login failure. |
| `AuthenticationEntryPoint` | Khởi động authentication/đáp ứng request chưa authenticated. |
| `AccessDeniedHandler` | Xử lý authenticated request không đủ quyền, thường `403`. |
| `AuthorizationManager` | Quyết định quyền truy cập request/action cụ thể. |
| `LogoutSuccessEvent` | Tín hiệu logout thành công trong flow phù hợp. |

Một request `GET /reports` trả `200` vì có session đã authenticate từ trước **không phát login success event mới** chỉ vì kết quả HTTP là thành công. Ngược lại, login đã xác thực có thể thất bại ở bước tạo session/redirect hoặc bước authorization tiếp theo; event và HTTP lifecycle khác nhau.

Một request có bearer token hợp lệ nhưng thiếu `ROLE_ADMIN` có thể dẫn đến `403` do `AuthorizationManager`/method security, **không phải `AuthenticationFailureBadCredentialsEvent`**. Nếu cần giám sát authorization failures, hãy tạo telemetry ở điểm authorization phù hợp, phân loại riêng với invalid credentials.

## 11. Những tình huống đặc biệt theo cơ chế xác thực

### Form login / `DaoAuthenticationProvider`

Password-login qua `AuthenticationManager` có thể phát success/failure nếu publisher đã được cấu hình. `UsernameNotFoundException` và `BadCredentialsException` được publisher map về bad-credentials event. Đừng tiết lộ username tồn tại hay không trong phản hồi công khai.

### LDAP / Active Directory

LDAP bind không thành công có thể do mật khẩu sai hoặc do directory không thể truy cập; provider phải dùng exception semantics phù hợp. **Lỗi LDAP outage không nên trở thành password guessing event**. Tạo metrics riêng cho backend health và authentication failures.

### Resource Server JWT

Token JWT sai issuer/audience/signature/expiry có thể dẫn tới `InvalidBearerTokenException` trong một số đường processing; khi exception này đi qua `DefaultAuthenticationEventPublisher`, nó được map sang bad-credentials event. Nhưng request **thiếu token header** có thể bị entry point từ chối trước khi có manager event. Kiểm thử với `oauth2ResourceServer().jwt()` thật.

### OIDC/SAML SSO

OIDC/SAML authentication có flow callback và provider đặc thù. Một lần authentication success sau callback không chứng minh user vừa nhập password tại app hoặc đã hoàn thành step-up MFA. Không dùng listener thay cho việc xác minh assertion/token signature, issuer, audience và thời hạn.

### API key / custom filter

Một custom `OncePerRequestFilter` tự parse header và set `SecurityContextHolder` mà không dùng `AuthenticationManager` có thể không phát những Spring authentication events này. Nếu audit là yêu cầu, hãy tổ chức đường provider/manager hoặc phát event theo contract riêng có chống trùng.

### MFA nhiều bước

Password phase success chưa có nghĩa session đạt `MFA_COMPLETE`. Theo dõi factor verification với sự kiện riêng từ trusted verifier: factor type, challenge ID, `verifiedAt`, purpose, assurance và trạng thái consumed/revoked. Không tự gắn `ROLE_ADMIN` chỉ vì listener thấy password thành công.

## 12. Phân biệt sai mật khẩu, locked, disabled, expired và lỗi hệ thống

**Sai credential – `AuthenticationFailureBadCredentialsEvent`:** được dùng trong các lần credential/token không hợp lệ; cũng có thể phản ánh user lookup thất bại. Không mặc nhiên kết luận user tồn tại hoặc password sai về mặt cryptography từ event class.

**Tài khoản bị khóa – `AuthenticationFailureLockedEvent`:** biểu thị provider nhận thấy trạng thái locked. Nó không có nghĩa **request này đã vừa khóa tài khoản**; lockout có thể do policy trước đó.

**Tài khoản disabled – `AuthenticationFailureDisabledEvent`:** hữu ích cho offboarding/security incident. Nhưng session/JWT cũ có thể tồn tại nếu authorization layer không kiểm tra account status, nên event không thay online state enforcement.

**Account expired – `AuthenticationFailureExpiredEvent`:** tài khoản đã hết thời hạn hoạt động theo chính sách; khác với password hết hạn.

**Credentials expired – `AuthenticationFailureCredentialsExpiredEvent`:** credential như password bị coi là đã hết hạn, có thể cần quy trình cập nhật credential an toàn.

**Provider không tồn tại – `AuthenticationFailureProviderNotFoundEvent`:** thường là tín hiệu sai cấu hình AuthenticationProvider/filter chain hoặc custom authentication token type, không phải một password sai của người dùng.

**Service exception – `AuthenticationFailureServiceExceptionEvent`:** tín hiệu lỗi nội bộ verifier/repository/LDAP/IdP. Không biến nó thành tăng bộ đếm sai mật khẩu và khóa hàng loạt account khi backend down. Phản hồi bên ngoài vẫn phải an toàn, không tiết lộ topology.

Những nguyên nhân này cần response policy riêng; thường nên giữ **thông điệp đăng nhập công khai không tiết lộ tồn tại account**, dù audit nội bộ lưu category chi tiết với quyền truy cập hạn chế.

## 13. Account enumeration và sự khác nhau giữa audit với response

Kẻ tấn công có thể thử email trong login form để dò account. Nếu UI trả:

~~~text
unknown user -> "Email không tồn tại"
bad password -> "Sai mật khẩu"
disabled     -> "Tài khoản của bạn đã bị khóa do HR"
~~~

thì sự khác nhau về message, status, redirect hoặc timing có thể tiết lộ trạng thái tài khoản. Một response công khai có thể dùng:

~~~json
{"message":"Thông tin đăng nhập không hợp lệ."}
~~~

Trong audit nội bộ, nếu có cơ sở cần thiết, vẫn có thể phân biệt `INVALID_CREDENTIALS`, `DISABLED_ACCOUNT`, `SYSTEM_ERROR` để hỗ trợ điều tra. Không hiển thị exception class, account status, username-found flag hay số lần thử sai trong public response nếu điều đó tạo side channel.

Cần kiểm soát cả timing và quota: một identifier tồn tại nhưng bị cooldown khác với identifier không tồn tại có thể cho tín hiệu. Áp anti-enumeration policy cả ở response handler, rate limiter và recovery flow; **event listener không tự giải quyết** vấn đề này.

## 14. Event payload có thể chứa credential: log theo allowlist

Một `Authentication` trong event có thể chứa `principal`, `credentials`, `details`, authorities, request metadata hoặc token. `AuthenticationException` có thể chứa cause/message nhạy cảm. Không ghi nguyên event:

~~~java
// Ví dụ cần tránh:
logger.info("Authentication={}", event.getAuthentication());
logger.error("Failure {}", event.getException());
~~~

Bản ghi audit an toàn nên có các trường **được chọn**:

~~~json
{
  "schemaVersion": 1,
  "eventId": "evt-f28",
  "outcome": "FAILURE",
  "category": "INVALID_CREDENTIALS",
  "mechanism": "PASSWORD",
  "occurredAt": "2026-11-06T09:05:00Z",
  "subjectRef": "pseudonymous-ref",
  "application": "employee-portal",
  "requestId": "req-190"
}
~~~

Đây là **schema đề xuất**, không phải fields có sẵn. `subjectRef` ở failure **không có nghĩa định danh đã xác thực**; nó có thể chỉ là một identifier do client tự nhập. Nếu phải correlate attempts, dùng HMAC/pseudonymization và retention phù hợp.

Không đưa vào log: password, OTP/TOTP, bearer/API key, refresh token, session cookie, raw Authorization header, request body, query string chứa secret, toàn bộ Authentication object hoặc exception stack trace không được sanitize.

Client IP hoặc user-agent chỉ nên được lấy từ nguồn đáng tin và có lý do privacy rõ. Sau reverse proxy, `X-Forwarded-For` có thể bị giả nếu edge không strip/rewrite. Spring event listener không phải lúc nào cũng có HTTP request context; không assume `RequestContextHolder` luôn hoạt động.

`event.getTimestamp()` là timestamp của Spring application event, không mặc nhiên là thời điểm một MFA factor cụ thể được xác minh hoặc một authorization commit.

## 15. Listener nên nhẹ, idempotent và không làm sai kết quả login

Spring `ApplicationEventPublisher` phát **in-process events**, listener thường đồng bộ với request thread theo cấu hình mặc định. `@Async` hoặc custom multicaster có thể thay đổi thực thi, nhưng **không biến event thành durable queue**.

Thực hành:

1. Phân loại outcome/category nhanh.
2. Đưa envelope đã làm sạch sang audit sink, queue hoặc metrics với giới hạn tải.
3. Xử lý duplicate và đảm bảo correlation nếu có nhiều AuthenticationManagers/listeners.
4. Không gọi mạng chậm trong synchronous listener mà không có timeout/backpressure.
5. Định nghĩa chính sách khi audit sink gặp lỗi: retry, buffer, alert, degrade hay fail closed cho tác vụ thật sự bắt buộc audit.
6. Không để exception từ listener vô tình khiến kết quả authentication bị thay đổi theo cách không dự kiến.
7. Dùng durable outbox/queue và idempotent consumers nếu có yêu cầu đảm bảo audit không bị mất khi process crash.

**Không dùng event listener là cơ chế bảo vệ duy nhất** cho rate limit, account lockout, MFA hoặc permission checks. Listener có thể không nhận event trong custom authentication path, có thể nhận trùng từ parent/child managers hoặc bị gián đoạn trong sự cố process.

### Sự kiện "một lần đăng nhập" khác "một request"

Với API stateless, cùng JWT có thể được xác thực lại trên hàng trăm request. Đếm mọi `AuthenticationSuccessEvent` thành số lượt đăng nhập sẽ phóng đại số liệu. Tách metrics theo `PASSWORD_LOGIN_SUCCESS`, `OIDC_CALLBACK_SUCCESS`, `BEARER_TOKEN_ACCEPTED` hoặc một taxonomy tương đương dựa trên mechanism đáng tin.

## 16. Rate limiting, lockout và alerting

Các failure events hữu ích để theo dõi:

- Nhiều `INVALID_CREDENTIALS` cho một identifier từ các nguồn khác nhau.
- Nhiều identifier bị thử sai từ một IP/network.
- Invalid bearer tokens tăng bất thường theo client/application.
- Attempts vào account disabled sau khi offboarding.
- `NO_AUTH_PROVIDER` tăng sau một deployment.
- `AUTH_SYSTEM_ERROR` tăng do database/LDAP/IdP outage.

Nhưng hệ thống nhiều node không nên chỉ đếm event trong `ConcurrentHashMap` của một JVM rồi lấy đó làm nguồn khóa account. Rate limit cần shared store/atomic counters và enforcement trước hoặc trong authentication flow.

Những chiều quota thường xét:

| Dimension | Mục đích | Rủi ro |
|---|---|---|
| Normalized identifier | Hạn đoán một account. | Phải áp cho identifier tồn tại và không tồn tại để tránh dò account. |
| IP/network | Hạn flood đơn nguồn. | NAT, proxy trust, botnet/IP rotation. |
| Client/tenant | Giới hạn abuse theo integration. | Tránh attacker lock cả tenant. |
| Device/risk signal | Phân tích hành vi. | Device cookie không phải proof độc lập. |
| Global auth backend | Bảo vệ DB/LDAP/IdP. | Outage không được bị tính thành sai mật khẩu. |

Khóa account sau nhiều lần sai có nguy cơ DoS nếu attacker cố tình spam vào nạn nhân. Policy cần giới hạn, challenge, recovery và audit, không đơn giản "cứ nhận 5 failure events là disable vĩnh viễn".

## 17. Java 17 chạy độc lập: mô phỏng taxonomy

Ví dụ sau dùng **JDK 17 Standard Library**, không cần Spring. Nó mô phỏng bước **chuẩn hóa nhóm audit** từ tên kết quả/exception. Chương trình **không** xác thực user, không publish Spring events và không thay implementation listener; trong app thật phải dùng event instances/subclasses.

~~~java
public class AuthenticationEventClassifierDemo {
    static String classify(String event, String exceptionType) {
        if ("AuthenticationSuccessEvent".equals(event)) {
            return "SUCCESS";
        }
        if (!"AbstractAuthenticationFailureEvent".equals(event)) {
            return "NOT_AUTH_RESULT";
        }
        return switch (exceptionType) {
            case "BadCredentialsException",
                 "UsernameNotFoundException",
                 "InvalidBearerTokenException" -> "INVALID_CREDENTIALS";
            case "DisabledException" -> "ACCOUNT_DISABLED";
            case "LockedException" -> "ACCOUNT_LOCKED";
            case "AccountExpiredException" -> "ACCOUNT_EXPIRED";
            case "CredentialsExpiredException" -> "CREDENTIALS_EXPIRED";
            case "ProviderNotFoundException" -> "NO_AUTH_PROVIDER";
            case "AuthenticationServiceException" -> "AUTH_SYSTEM_ERROR";
            default -> "UNMAPPED_FAILURE";
        };
    }

    static void show(String label, String event, String exception) {
        System.out.println(label + ": " + classify(event, exception));
    }

    public static void main(String[] args) {
        String fail = "AbstractAuthenticationFailureEvent";
        show("login", "AuthenticationSuccessEvent", "");
        show("bad password", fail, "BadCredentialsException");
        show("unknown username", fail, "UsernameNotFoundException");
        show("bad bearer", fail, "InvalidBearerTokenException");
        show("disabled", fail, "DisabledException");
        show("locked", fail, "LockedException");
        show("expired account", fail, "AccountExpiredException");
        show("expired credentials", fail, "CredentialsExpiredException");
        show("no provider", fail, "ProviderNotFoundException");
        show("backend error", fail, "AuthenticationServiceException");
        show("custom", fail, "MyCustomException");
        show("access denied", "AccessDeniedEvent", "");
    }
}
~~~

Lưu tệp `AuthenticationEventClassifierDemo.java` rồi chạy:

~~~bash
javac AuthenticationEventClassifierDemo.java
java AuthenticationEventClassifierDemo
~~~

**Stdout chính xác:**

~~~text
login: SUCCESS
bad password: INVALID_CREDENTIALS
unknown username: INVALID_CREDENTIALS
bad bearer: INVALID_CREDENTIALS
disabled: ACCOUNT_DISABLED
locked: ACCOUNT_LOCKED
expired account: ACCOUNT_EXPIRED
expired credentials: CREDENTIALS_EXPIRED
no provider: NO_AUTH_PROVIDER
backend error: AUTH_SYSTEM_ERROR
custom: UNMAPPED_FAILURE
access denied: NOT_AUTH_RESULT
~~~

Điểm cần hiểu: user không tồn tại và bad password được gom nhóm, internal service outage được phân biệt khỏi guessing, còn access denied không nằm trong cây authentication result. Với custom exception, app phải cấu hình publisher mapping/fallback **trước khi** listener có event để phân loại.

## 18. Kịch bản ứng dụng thực tế

### A. Login đúng mật khẩu

~~~text
POST /login
  -> DaoAuthenticationProvider authenticates
  -> ProviderManager returns Authentication
  -> AuthenticationSuccessEvent
  -> audit SUCCESS / mechanism PASSWORD
  -> filter success handler redirects or returns response
~~~

Nếu sau đó còn bước TOTP, đây không tự là kết quả MFA-complete. Hãy ghi event riêng của factor verifier.

### B. Thử email không tồn tại

~~~text
User lookup returns UsernameNotFoundException
  -> publisher maps it to AuthenticationFailureBadCredentialsEvent
  -> audit INVALID_CREDENTIALS
  -> public response uses generic message
~~~

Không làm lộ tồn tại email qua HTTP body/status/timing.

### C. Account đã locked

~~~text
Provider detects LockedException
  -> AuthenticationFailureLockedEvent
  -> internal audit ACCOUNT_LOCKED
  -> policy decides recovery/unlock
~~~

Đừng dùng event như bằng chứng rằng chính request này vừa tăng failed-attempt counter đến ngưỡng lock.

### D. LDAP/IdP backend outage

~~~text
Provider throws AuthenticationServiceException
  -> AuthenticationFailureServiceExceptionEvent
  -> alert AUTH_SYSTEM_ERROR
  -> authentication fails closed
~~~

Không xem outage thành password guessing, không cho qua chỉ vì backend tạm lỗi.

### E. API bearer JWT hợp lệ nhưng thiếu quyền

~~~text
JWT signature/issuer/audience/exp validated
  -> authenticated principal exists
  -> authorization checks missing PAYMENT_APPROVE
  -> request denied (typically 403)
~~~

Đây là authorization denial, **không** là `AuthenticationFailureBadCredentialsEvent`.

## 19. Kiểm thử theo từng lớp

| Test case | Mong đợi |
|---|---|
| Correct password qua manager có publisher. | Đúng một success event cho logical attempt. |
| Sai password. | `AuthenticationFailureBadCredentialsEvent`. |
| Username không tồn tại. | Bad-credentials mapping và response chung chống enumeration. |
| Account disabled. | `AuthenticationFailureDisabledEvent`. |
| Account locked. | `AuthenticationFailureLockedEvent`. |
| Account expired. | `AuthenticationFailureExpiredEvent`. |
| Credentials expired. | `AuthenticationFailureCredentialsExpiredEvent`. |
| Không có AuthenticationProvider. | `AuthenticationFailureProviderNotFoundEvent`. |
| Provider ném AuthenticationServiceException. | `AuthenticationFailureServiceExceptionEvent`; không tăng bad-password counter. |
| Bearer token lỗi qua publisher. | Mapping `InvalidBearerTokenException` theo flow thực. |
| Không gửi token tới API. | Không mặc nhiên đòi event; kiểm tra entry point/filter. |
| Valid token nhưng thiếu quyền. | Authorization denial, không bị đếm auth failure. |
| Custom exception subclass của bad credentials. | Không tự map nếu chưa khai báo exact mapping/fallback. |
| Custom exception đã map. | Nhận đúng custom event. |
| Listener superclass và subclass. | Không double-count bản ghi audit. |
| Parent/child AuthenticationManager đều publish. | Không đếm duplicate sau khi chỉnh cấu hình. |
| JWT stateless gửi 100 request. | Không suy ra 100 lần human login. |
| Audit sink tạm lỗi. | Behavior theo SLA, không làm rò credentials hay bypass security. |
| Listener ghi Authentication object. | Log canary test phát hiện và chặn rò password/token. |
| User enumeration. | Public status/body/redirect không lộ trạng thái. |
| Nhiều app instances. | Aggregation/rate limit đúng, không phụ thuộc listener memory. |

Nên test bằng `MockMvc` trên đường form login, provider test với exception mappings, context test cho `@EventListener`, integration test JWT/OIDC/LDAP nếu ứng dụng có và privacy tests kiểm tra logs. Test "login trả 302 tới dashboard" **không đủ** để chứng minh event taxonomy hoạt động.

## 20. Checklist triển khai và tổng kết

- [ ] Xác định AuthenticationManagers, Providers và publisher của từng filter chain.
- [ ] Đảm bảo `DefaultAuthenticationEventPublisher` được cấu hình đúng, tránh chồng bean.
- [ ] Lắng nghe `AuthenticationSuccessEvent` và `AbstractAuthenticationFailureEvent`.
- [ ] Phân loại đủ BadCredentials, UsernameNotFound, InvalidBearerToken, Disabled, Locked, AccountExpired, CredentialsExpired, ProviderNotFound, AuthenticationService.
- [ ] Custom exceptions có exact mappings hoặc fallback event concrete class.
- [ ] Không nhầm interactive login, per-request token validation, MFA success và authorization denied.
- [ ] Không log nguyên Authentication, credentials, bearer tokens hoặc exception messages nhạy cảm.
- [ ] Public response tránh account enumeration.
- [ ] Service errors không bị coi là sai mật khẩu dẫn đến lockout hàng loạt.
- [ ] Listener chỉ làm audit/observability; bảo vệ bắt buộc ở enforcement path.
- [ ] Có chính sách duplicate handling, timeout, backpressure và audit durability.
- [ ] Rate limiter dùng state/atomic counter phù hợp khi multi-instance.
- [ ] Có integration tests cho các cơ chế thực sự dùng.
- [ ] Audit data có retention, access controls, source trust và correlation ID.

**Kết luận:** `AuthenticationSuccessEvent` mô tả kết quả được chấp nhận từ luồng xác thực; các subclass của `AbstractAuthenticationFailureEvent` giúp tách sai credentials, account disabled/locked/expired, provider configuration và backend service errors. `DefaultAuthenticationEventPublisher` quyết định mapping **theo exact exception class** và Spring listeners có thể chuẩn hóa chúng thành audit/metrics an toàn. Cần bảo đảm publisher thực sự được sử dụng, event không bị đếm trùng, dữ liệu nhạy cảm không bị log và authentication events không bị nhầm với session lifecycle hoặc authorization failures.

## Tài liệu tham khảo

- [Spring Security 6.5 – Authentication Events](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/events.html): publisher, listener, mappings và exact-match.
- [Spring Security 6.5 – DefaultAuthenticationEventPublisher](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/DefaultAuthenticationEventPublisher.html): publish success/failure, additional mappings, fallback event.
- [Spring Security 6.5 – AuthenticationEventPublisher](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationEventPublisher.html): interface contract.
- [Spring Security 6.5 – AbstractAuthenticationFailureEvent](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/event/AbstractAuthenticationFailureEvent.html): base class, authentication và exception.
- [Spring Security 6.5 – ProviderManager](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html): provider chain và event publishing.
- [Spring Security 6.5 – InteractiveAuthenticationSuccessEvent](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/event/InteractiveAuthenticationSuccessEvent.html): interactive success và tránh duplicate.
- [Spring Security – Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): AuthenticationManager, Provider, SecurityContext.
- [OWASP – Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): generic responses, brute force và enumeration.
- [OWASP – Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): security audit và dữ liệu không được log.
