# Ánh xạ exception tùy chỉnh sang sự kiện xác thực phù hợp trong Spring Security

**Authentication events** giúp ứng dụng ghi nhận việc đăng nhập thành công/thất bại, tạo metrics, cảnh báo hoặc audit mà không trộn toàn bộ logic quan sát vào Servlet filter hay trang đăng nhập. Trong Spring Security, **`DefaultAuthenticationEventPublisher`** chuyển một số `AuthenticationException` thành những sự kiện như `AuthenticationFailureBadCredentialsEvent`, `AuthenticationFailureLockedEvent` hoặc `AuthenticationFailureServiceExceptionEvent`.

Vấn đề phát sinh khi dự án định nghĩa **exception tùy chỉnh**. Ví dụ `DirectoryTemporarilyUnavailableException` kế thừa `AuthenticationServiceException`, nhưng mặc định không nhất thiết phát cùng event với lớp cha. Nguyên nhân quan trọng: bộ publisher mặc định **ánh xạ theo chính xác lớp exception**, không tự đi ngược cây kế thừa. Muốn sự kiện đúng ý nghĩa, cần đăng ký mapping tường minh, chọn loại event phù hợp, và kiểm thử cả hành vi phát sự kiện lẫn bảo mật thông tin.

Bài học giải thích đường đi exception → event, mapping mặc định, cách tạo custom exception/custom event, cấu hình `AuthenticationEventPublisher` và `@EventListener`, phân biệt với `AuthenticationFailureHandler`, kiểm thử và lưu ý vận hành. Mã ví dụ dùng **Java 17+ / Spring Security Servlet**; phần nào cần Spring context sẽ được ghi rõ, không đánh đồng với chương trình Java thuần có thể chạy bằng `javac`.

## 1. AuthenticationException và Authentication Event khác nhau thế nào?

Một `AuthenticationException` biểu diễn một **lần xác thực không thành công**; nó được ném trong quá trình kiểm tra credential, account status, provider hoặc nguồn danh tính. Một **authentication event** là thông tin được publish tới Spring ApplicationContext để các listener phản ứng với kết quả đó.

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `Authentication` | Yêu cầu xác thực hoặc kết quả sau xác thực | `UsernamePasswordAuthenticationToken` |
| `AuthenticationManager` / `ProviderManager` | Điều phối các `AuthenticationProvider` | Chọn provider, xử lý kết quả |
| `AuthenticationException` | Lý do xác thực thất bại | `BadCredentialsException`, custom exception |
| `AuthenticationEventPublisher` | Giao diện phát sự kiện | `publishAuthenticationFailure(...)` |
| `DefaultAuthenticationEventPublisher` | Publisher ánh xạ exception → event mặc định | `LockedException` → locked event |
| `AbstractAuthenticationFailureEvent` | Lớp cơ sở của các sự kiện thất bại | Chứa `getAuthentication()` / `getException()` |
| `AuthenticationSuccessEvent` | Sự kiện xác thực thành công | Đếm số lần thành công |
| `@EventListener` | Xử lý event trong Spring context | Audit, telemetry, cảnh báo |

Điểm quan trọng: **exception là quyết định thất bại ở đường xác thực; event là thông báo để quan sát việc thất bại đó**. Cấu hình một event không tự động đổi HTTP status, đổi `Authentication` thành thành công hay mở khóa account.

Sơ đồ luồng phổ biến:

~~~text
HTTP Login / API authentication
          |
          v
Authentication filter / caller
          |
          v
AuthenticationManager (thường là ProviderManager)
          |
          v
AuthenticationProvider kiểm credential + policy
          |
          +-- success -> trả Authentication đã xác thực
          |                 |
          |                 v
          |       AuthenticationEventPublisher
          |                 |
          |                 +--> AuthenticationSuccessEvent
          |
          +-- failure -> ném AuthenticationException
                            |
                            v
                  AuthenticationEventPublisher
                            |
                            v
                  Exception type -> Event mapping
                            |
                            +--> AbstractAuthenticationFailureEvent
                            |
                            v
                    @EventListener / metrics / audit
          |
          v
HTTP authentication success/failure handler quyết định response
~~~

Đây là một sơ đồ mô hình; thứ tự thực tế phụ thuộc filter/provider và cách cấu hình. Nếu exception bị bắt rồi bị nuốt trước khi tới `AuthenticationManager`, hoặc bạn tự tạo `ProviderManager` mà chưa cài event publisher, **không có đảm bảo sự kiện được phát**.

## 2. Những mapping mặc định đáng biết

Tài liệu Spring Security 7.x về Authentication Events nêu các ánh xạ quan trọng:

| AuthenticationException chính xác | Failure event |
| --- | --- |
| `BadCredentialsException` | `AuthenticationFailureBadCredentialsEvent` |
| `UsernameNotFoundException` | `AuthenticationFailureBadCredentialsEvent` |
| `AccountExpiredException` | `AuthenticationFailureExpiredEvent` |
| `CredentialsExpiredException` | `AuthenticationFailureCredentialsExpiredEvent` |
| `DisabledException` | `AuthenticationFailureDisabledEvent` |
| `LockedException` | `AuthenticationFailureLockedEvent` |
| `ProviderNotFoundException` | `AuthenticationFailureProviderNotFoundEvent` |
| `AuthenticationServiceException` | `AuthenticationFailureServiceExceptionEvent` |
| `InvalidBearerTokenException` | `AuthenticationFailureBadCredentialsEvent` |

Đây là **event mapping**, không phải bảng HTTP status. Ví dụ `LockedException` thường có thể dẫn tới `AuthenticationFailureLockedEvent` trong nội bộ, nhưng giao diện đăng nhập công khai vẫn nên trả một **thông báo chung** để tránh account enumeration.

Một số exception khác hoặc custom subclass **không có mapping mặc định**. Tùy việc cấu hình fallback, chúng có thể không tạo failure event. Khi tài liệu framework thay đổi theo phiên bản, kiểm lại Javadoc và danh sách mapping đúng với dependency đang chạy.

### Không dùng event “đặc biệt” chỉ để làm giao diện thông báo

Ví dụ một account bị disabled có thể được ghi nhận nội bộ bằng `AuthenticationFailureDisabledEvent`. Điều đó **không** có nghĩa trả ra browser “Tài khoản này tồn tại nhưng bị vô hiệu hóa”. Event dùng cho backend; client error messaging phải tuân theo bảo mật của ứng dụng.

Tương tự, hệ thống OAuth bearer token có thể phát event loại bad credentials cho một token không hợp lệ, nhưng không nên tự suy từ event class rằng loại credential của request luôn là password.

## 3. Bẫy lớn nhất: exact exception class, không kế thừa mapping

Giả sử bạn tạo:

~~~java
public final class DirectoryTemporarilyUnavailableException
        extends AuthenticationServiceException {

    public DirectoryTemporarilyUnavailableException(String message) {
        super(message);
    }
}
~~~

Nhà phát sự kiện có mapping mặc định:

~~~text
AuthenticationServiceException.class
    -> AuthenticationFailureServiceExceptionEvent.class
~~~

**Không được suy ra:**

~~~text
DirectoryTemporarilyUnavailableException.class
    -> AuthenticationFailureServiceExceptionEvent.class
~~~

Mặc định publisher dùng phép tra theo **lớp exception cụ thể** (tương đương ý tưởng `exception.getClass()`), không tự tìm mapping của superclass. Vì thế subclass không nhất thiết phát sự kiện như người viết tưởng, dù `instanceof AuthenticationServiceException` trả true.

Một bảng minh họa:

| Exception thực sự được ném | Có mapping tường minh? | Event dự kiến |
| --- | --- | --- |
| `AuthenticationServiceException` | Có mặc định | Service exception event |
| `DirectoryTemporarilyUnavailableException` | Không | Không có event hoặc fallback tùy cấu hình |
| `DirectoryTemporarilyUnavailableException` | Có map tới service event | Service exception event |
| `InvalidOtpException extends BadCredentialsException` | Không | Không tự hưởng bad credentials event |
| `InvalidOtpException` | Có map tới bad credentials event | Bad credentials event |
| `UnknownCustomAuthenticationException` | Không, có fallback | Catch-all event |

**Kết luận kỹ thuật:** thay đổi hierarchy của một exception có thể làm mất hoặc đổi event telemetry nếu team không xem lại danh sách mapping. Mỗi custom `AuthenticationException` có ý nghĩa vận hành cần được liệt kê và kiểm thử một cách tường minh.

## 4. Chọn event theo bản chất failure, không chỉ theo tên exception

Đầu tiên hãy xác định failure thực sự thuộc lớp nào:

| Tình huống | Loại event gợi ý | Lưu ý |
| --- | --- | --- |
| Password/OTP/token sai | Bad credentials event | Không công khai user nào tồn tại |
| Account bị khóa | Locked event | Trạng thái phải xác định bởi nguồn identity đáng tin |
| Account disabled | Disabled event | Không dùng event để tự mở khóa |
| Credential hết hạn | Credentials expired event | Khác với account hết hạn |
| Account hết hiệu lực | Expired event | Dựa vào chính sách vòng đời |
| Nguồn danh tính không khả dụng | Service exception event | Không quy lỗi hạ tầng thành user sai mật khẩu |
| Không có provider hỗ trợ loại token | Provider not found event | Kiểm cấu hình ProviderManager |
| Luật xác thực tùy chỉnh bị từ chối | Custom failure event | Đặt tên/ý nghĩa rõ, không tiết lộ lý do nhạy cảm |

Ví dụ: `DirectoryTemporarilyUnavailableException` nghĩa là IdP/LDAP không phản hồi. Nếu map nó thành `AuthenticationFailureBadCredentialsEvent`, dashboard sẽ báo sai rằng người dùng nhập sai mật khẩu; hệ thống có thể kích hoạt credential-stuffing alert nhầm hoặc tăng counter lockout không đúng. Nên map về **service failure event**.

Ngược lại, `OtpCodeMismatchException` là một credential verification failure, nên bad credentials event có thể phù hợp — trừ khi ứng dụng cần một custom event riêng để phân biệt *loại yếu tố xác thực* theo chính sách nội bộ.

**Cảnh báo về phân quyền:** khi user đã authenticated mà truy cập resource không có quyền, thông thường đây là **authorization failure** (ví dụ `AccessDeniedException`/HTTP 403), **không phải authentication exception**. Đừng ép mọi lỗi 403 thành `AuthenticationFailureBadCredentialsEvent`; điều đó làm nhiễu định nghĩa sự kiện và có thể đếm sai các lần đăng nhập thất bại.

**MFA/step-up đang chờ:** việc người dùng còn phải hoàn tất một bước bổ sung chưa chắc là authentication failure cuối cùng. Nếu flow được thiết kế nhiều giai đoạn, đừng tự ném một failure exception chỉ để kích hoạt metric mỗi khi cần OTP; hãy mô hình hóa trạng thái challenge/flow cho đúng.

## 5. API quan trọng của DefaultAuthenticationEventPublisher

Bộ publisher hỗ trợ các API:

~~~java
DefaultAuthenticationEventPublisher publisher =
        new DefaultAuthenticationEventPublisher(applicationEventPublisher);

publisher.setAdditionalExceptionMappings(mappings);

publisher.setDefaultAuthenticationFailureEvent(
        UnmappedAuthenticationFailureEvent.class);
~~~

Ở đây `applicationEventPublisher` là Spring `ApplicationEventPublisher`, còn `mappings` là:

~~~java
Map<Class<? extends AuthenticationException>,
    Class<? extends AbstractAuthenticationFailureEvent>>
~~~

Các đặc tính:

- `setAdditionalExceptionMappings(Map)` **bổ sung hoặc điều chỉnh** ánh xạ bên cạnh mapping mặc định; dùng key là class của exception, value là class event.
- Event được chỉ định phải là subclass cụ thể của `AbstractAuthenticationFailureEvent`, có constructor phù hợp nhận `(Authentication, AuthenticationException)`.
- `setDefaultAuthenticationFailureEvent(...)` cấu hình event fallback cho một exception **không có mapping**. Không nên dùng fallback để che việc thiếu mapping của những lỗi nghiệp vụ quan trọng.
- Overload nhận `Properties` đã được đánh dấu deprecated trong các phiên bản Spring Security hiện đại; ưu tiên typed `Map` để tránh dùng class names dưới dạng String và lỗi cấu hình runtime.
- Nếu dùng constructor truyền `ApplicationEventPublisher`, event sẽ được publish tới context tương ứng; nếu tạo publisher như một Spring bean, framework có thể tự inject publisher qua `ApplicationEventPublisherAware`.

Không tạo một bean `AuthenticationEventPublisher` cho mỗi exception. Một publisher với map rõ ràng giúp quản lý toàn bộ policy phát sự kiện và tránh các publisher khác nhau tranh quyền.

## 6. Ví dụ cấu hình hoàn chỉnh cho custom exception và event

Tình huống: hệ thống xác thực thông qua một directory bên ngoài. Khi directory không khả dụng, provider ném `DirectoryTemporarilyUnavailableException`; team muốn event loại service failure. Khi một điều kiện xác thực nội bộ bị từ chối, provider ném `CredentialPolicyRejectedException`; team muốn **custom event** để phân tích riêng. Các exception này phải được ném trong **authentication flow**, không chỉ từ một controller bất kỳ.

Tệp **AuthenticationEventConfig.java** — code trong ứng dụng Spring Boot Servlet dùng Spring Security 6.x/7.x:

~~~java
package demo.auth.events;

import java.util.Map;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.security.authentication.event.AuthenticationFailureServiceExceptionEvent;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;

@Configuration(proxyBeanMethods = false)
public class AuthenticationEventConfig {

    public static final class DirectoryTemporarilyUnavailableException
            extends AuthenticationServiceException {
        public DirectoryTemporarilyUnavailableException(String message) {
            super(message);
        }
    }

    public static final class CredentialPolicyRejectedException
            extends AuthenticationException {
        public CredentialPolicyRejectedException(String message) {
            super(message);
        }
    }

    public static final class AuthenticationFailurePolicyRejectedEvent
            extends AbstractAuthenticationFailureEvent {
        public AuthenticationFailurePolicyRejectedEvent(
                Authentication authentication,
                AuthenticationException exception) {
            super(authentication, exception);
        }
    }

    public static final class AuthenticationFailureUnmappedEvent
            extends AbstractAuthenticationFailureEvent {
        public AuthenticationFailureUnmappedEvent(
                Authentication authentication,
                AuthenticationException exception) {
            super(authentication, exception);
        }
    }

    @Bean
    AuthenticationEventPublisher authenticationEventPublisher(
            ApplicationEventPublisher applicationEvents) {

        Map<Class<? extends AuthenticationException>,
            Class<? extends AbstractAuthenticationFailureEvent>> mappings =
                Map.of(
                    DirectoryTemporarilyUnavailableException.class,
                    AuthenticationFailureServiceExceptionEvent.class,
                    CredentialPolicyRejectedException.class,
                    AuthenticationFailurePolicyRejectedEvent.class);

        DefaultAuthenticationEventPublisher publisher =
                new DefaultAuthenticationEventPublisher(applicationEvents);

        publisher.setAdditionalExceptionMappings(mappings);
        publisher.setDefaultAuthenticationFailureEvent(
                AuthenticationFailureUnmappedEvent.class);
        return publisher;
    }
}
~~~

### Giải thích code

- Hai exception đều là `AuthenticationException` hoặc subclass; có thể được `AuthenticationProvider` ném khi quá trình xác thực thất bại.
- Mapping thứ nhất giữ đúng nghĩa **lỗi dịch vụ/directory**, không báo user nhập sai password.
- Mapping thứ hai tạo event riêng vì lỗi có ý nghĩa giám sát nghiệp vụ cụ thể.
- Event riêng mở rộng `AbstractAuthenticationFailureEvent` và có constructor nhận đúng hai tham số mà publisher cần.
- Fallback event `AuthenticationFailureUnmappedEvent` giúp ghi nhận các loại custom failure khác chưa có mapping.
- `@Bean` trả về interface `AuthenticationEventPublisher` để những authentication manager do Spring Security cấu hình có thể sử dụng.

**Phạm vi chạy:** Đây là class cấu hình trong một ứng dụng Spring Boot có Spring Security; nó **không tự dựng AuthenticationManager hay provider**, không chạy độc lập bằng `javac`. Cần main Spring Boot, dependency tương thích, một authentication flow thực sự sử dụng publisher này, và user/provider để ném các exception mẫu.

**Vì sao dùng concrete fallback event?** `AbstractAuthenticationFailureEvent` là abstract. Mặc dù ví dụ tài liệu ở một số phiên bản dùng tên lớp abstract để minh họa catch-all, trong code ứng dụng nên chọn **lớp event cụ thể, có constructor hợp lệ** như `AuthenticationFailureUnmappedEvent` để tránh lỗi khởi tạo runtime.

Nếu doanh nghiệp không cần phân loại policy-specific, thay mapping thứ hai bằng một **built-in event** phù hợp cũng được. Nhưng không nên dùng một event “BadCredentials” chỉ vì nó phổ biến; telemetry phải phản ánh nguyên nhân xác thực được server xác định.

## 7. AuthenticationProvider phải ném đúng exception

Một authentication provider của ứng dụng có thể ném custom exception ở thời điểm thích hợp:

~~~java
// Mảnh bên trong AuthenticationProvider.authenticate(...):
try {
    directoryClient.verifyCredential(username, password);
} catch (DirectoryTimeoutException ex) {
    throw new AuthenticationEventConfig
            .DirectoryTemporarilyUnavailableException(
                    "Authentication directory temporarily unavailable");
}

if (!policy.allowsAuthentication(username, loginContext)) {
    throw new AuthenticationEventConfig
            .CredentialPolicyRejectedException(
                    "Authentication policy rejected");
}

// Chỉ khi mọi bước đủ điều kiện mới trả Authentication đã xác thực.
~~~

Đây là **pseudocode Java phụ thuộc interface ứng dụng**; `directoryClient`, `policy`, `DirectoryTimeoutException` và `loginContext` phải do dự án tự định nghĩa. Không phải lớp độc lập có thể biên dịch.

Các nguyên tắc:

1. Chỉ ném custom exception thuộc **failure của xác thực**, không lạm dụng cho lỗi phân quyền sau login.
2. Giữ nguyên semantic khi chuyển đổi exception từ LDAP/IdP/KMS thành Spring `AuthenticationException`.
3. Không ghi raw password/token trong exception message hoặc cause chain đưa ra log công khai.
4. Tránh bắt `AuthenticationException`, log rồi trả success token giả. Manager cần thấy thất bại để phát event và filter xử lý kết quả.
5. Không tạo `new AuthenticationSuccessEvent(...)` thủ công khi chưa thực sự xác thực thành công.

**Lưu ý:** lỗi dịch vụ thật cần được theo dõi riêng để on-call phân biệt với người dùng nhập sai mật khẩu. Đừng biến outage thành một đợt lockout hàng loạt do đánh nhầm loại failure.

## 8. Nhận event bằng @EventListener

Spring Framework hỗ trợ `@EventListener`. Ví dụ tệp **AuthenticationAuditListener.java**:

~~~java
package demo.auth.events;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;

@Component
public class AuthenticationAuditListener {

    private static final Logger log =
            LoggerFactory.getLogger(AuthenticationAuditListener.class);

    @EventListener
    public void onFailure(AbstractAuthenticationFailureEvent event) {
        // Chỉ ghi loại event/exception; không in credentials hoặc message.
        log.info("auth_failure event={} exception={}",
                event.getClass().getSimpleName(),
                event.getException().getClass().getSimpleName());
    }

    @EventListener
    public void onSuccess(AuthenticationSuccessEvent event) {
        log.info("auth_success");
    }
}
~~~

Tệp này chạy **trong Spring context**, không chạy độc lập. Nó xử lý mọi subtype của `AbstractAuthenticationFailureEvent`, kể cả custom và fallback. Bạn có thể dùng các listener riêng cho `AuthenticationFailurePolicyRejectedEvent` hoặc `AuthenticationFailureServiceExceptionEvent` nếu cần metric riêng.

Không log:

~~~java
// Không làm:
log.info("credential={}", event.getAuthentication().getCredentials());
log.info("exceptionMessage={}", event.getException().getMessage());
~~~

Request authentication object có thể chứa password/token/certificate hoặc dữ liệu nhạy cảm; exception message có thể chứa username, tenant, endpoint nội bộ hoặc nguyên nhân provider. Audit nên dùng **event category được allowlist**, correlation ID, environment và các identifier đã được xử lý PII hợp lệ, không dump toàn bộ `Authentication`.

**Đừng cài listener trả 401/403 qua HttpServletResponse**. Event listener có thể chạy trong ngữ cảnh khác Servlet request. HTTP response nên thuộc `AuthenticationFailureHandler`, `AuthenticationEntryPoint` hoặc web filter tương ứng.

## 9. Phân biệt AuthenticationFailureHandler và Authentication Event

Hai khái niệm dễ bị nhầm vì cùng nghe tới “failure”:

| Cơ chế | Được dùng ở đâu | Việc chính |
| --- | --- | --- |
| `AuthenticationFailureHandler` | Servlet filter, ví dụ form login | Chọn redirect, status và message sau failure |
| `AuthenticationEventPublisher` | AuthenticationManager hoặc flow được tích hợp | Publish sự kiện để hệ thống quan sát |
| `@EventListener` | Spring ApplicationContext | Ghi audit/metric/alert hoặc logic phụ |
| `AuthenticationEntryPoint` | Khi request cần authentication | Bắt đầu flow login hoặc trả 401 |
| `AccessDeniedHandler` | Khi người dùng thiếu quyền | Xử lý authorization denial, thường 403 |

Ví dụ một `CredentialPolicyRejectedException` có thể dẫn tới **một custom failure event nội bộ**; còn HTTP login vẫn trả “Tên đăng nhập hoặc mật khẩu không đúng” hoặc thông báo generic theo chính sách. Chúng không mâu thuẫn.

**Không dùng event mapping để che một response leak:** dù có map sang bad credentials event, nếu failure handler trả “User bị vô hiệu hóa” cho `DisabledException` thì browser vẫn có thể thấy thông tin nhạy cảm. Phải bảo vệ riêng public messaging.

## 10. ProviderManager phải thực sự sử dụng publisher đã cấu hình

Khi ứng dụng sử dụng authentication manager do Spring Security/Boot xây dựng, bean `AuthenticationEventPublisher` thường được tích hợp theo cấu hình security. Tuy nhiên, nếu bạn tự tạo `ProviderManager`, không được mặc định cho rằng nó tự tìm và gắn publisher ở ApplicationContext.

Mảnh code minh họa:

~~~java
AuthenticationProvider provider = ...; // provider đã cấu hình thật

ProviderManager manager = new ProviderManager(provider);
manager.setAuthenticationEventPublisher(authenticationEventPublisher);
~~~

Đây là **mảnh Java phụ thuộc provider và publisher thực**. Cần import `org.springframework.security.authentication.ProviderManager` và `org.springframework.security.authentication.AuthenticationProvider`; class/method cụ thể phải được đặt trong cấu hình ứng dụng.

Theo Javadoc, `ProviderManager` mặc định có thể dùng publisher no-op khi tạo thủ công, vì thế việc bạn có listener bean chưa đảm bảo sẽ nhận được event từ manager này.

### Parent AuthenticationManager có thể gây sự kiện trùng

Một `ProviderManager` có thể có **parent AuthenticationManager**. Javadoc cảnh báo: manager con có thể publish event cho kết quả/lỗi được parent trả về; nếu parent cũng có publisher của riêng nó, **cùng attempt có thể sinh nhiều event**.

Biện pháp:

- Kiểm kiến trúc parent/child managers khi dùng nhiều filter chains.
- Chỉ cấu hình nơi chịu trách nhiệm publish để không double-count metrics/lockout.
- Test một attempt dẫn tới đúng số event mong muốn.
- Listener phải idempotent nếu sự kiện dùng cho downstream audit/metrics.

Không lấy số lượng event là số lần HTTP request tuyệt đối nếu authentication manager bị gọi nhiều lần trong một request hoặc hệ thống có nhiều bước xác thực.

## 11. Có cần fallback event cho mọi exception không?

`setDefaultAuthenticationFailureEvent(...)` có ích để không bỏ sót các exception chưa lập mapping. Nhưng **fallback không thay thế phân loại đúng**.

Ví dụ:

~~~text
CustomUnknownException
    |
    v
Không tìm thấy exact mapping
    |
    v
AuthenticationFailureUnmappedEvent
    |
    v
Metric: auth_failure_unmapped
~~~

Một hệ thống nên:

- Dùng fallback để phát hiện exception mới cần review.
- Đặt dashboard/alert khi fallback tăng đột biến.
- Không dùng fallback “bad credentials” cho mọi loại lỗi; outage rồi sẽ bị đếm thành credential attack.
- Giữ danh sách custom exception và owner nghiệp vụ.
- Bổ sung mapping/tài liệu/test ngay khi giới thiệu exception mới.
- Không tự ném exception fallback sau khi listener xử lý event, gây vòng lặp hoặc làm hỏng luồng đăng nhập.

Nếu một subtype mới của `AuthenticationException` xuất hiện từ dependency upgrade, fallback có thể giúp nhận thấy thay đổi; nhưng vẫn phải kiểm rằng publisher đang được gắn vào đúng manager và listener đã đăng ký.

## 12. Mapping và public error response phải tách rời

Một tình huống thực tế:

~~~text
username không tồn tại -> UsernameNotFoundException
password sai          -> BadCredentialsException
account bị khóa       -> LockedException
directory không sống  -> DirectoryTemporarilyUnavailableException
~~~

Ở backend, chúng có thể được phân loại thành các event khác nhau để điều tra. Tuy nhiên, response ra Internet không được tùy tiện công bố những khác biệt làm lộ user existence.

Ví dụ chính sách:

| Trường hợp | Event nội bộ | Response công khai gợi ý |
| --- | --- | --- |
| Wrong password | BadCredentials event | Generic authentication failure |
| Unknown user | BadCredentials event (nếu provider ném đúng loại) | Cùng generic failure |
| Locked account | Locked event | Thông báo được thiết kế chống enumeration |
| Disabled account | Disabled event | Không xác nhận account state cho anonymous caller |
| Directory outage | Service failure event | Lỗi xác thực chung, hỗ trợ vận hành theo policy |
| OTP mismatch | Custom hoặc BadCredentials event | Không lộ giá trị/độ đúng của OTP |
| Permission thiếu sau login | Authorization event/handler riêng | 403/điều hướng theo policy |

**Không dùng metric hoặc event subtype để thay đổi thời gian trả response một cách có thể khai thác.** Nếu listener thực hiện RPC/SMTP đồng bộ chỉ khi account tồn tại, nó có thể tạo timing side-channel dù login failure handler trả cùng body.

Với các event nhạy cảm, chỉ thực hiện xử lý nhẹ, hạn chế logging/PII và đưa các tác vụ chậm vào hàng đợi được bảo vệ nếu cần.

## 13. Hiểu event listener đồng bộ, bất đồng bộ và độ tin cậy

Spring ApplicationEvent thường được xử lý **đồng bộ** với multicaster mặc định. Điều này có thể có hệ quả:

- Một listener quá chậm kéo dài thời gian xử lý authentication.
- Listener ném unchecked exception có thể ảnh hưởng caller và làm failure flow khó dự đoán.
- Các side effects audit/notification có thể xảy ra trước khi HTTP response hoàn tất.
- Không nên dựa vào application events trong memory làm **hàng đợi durable** được bảo đảm giao nhận một lần.

Nếu cần gửi thông báo an ninh, SIEM hoặc audit compliance:

1. Listener xử lý nhẹ hoặc ghi một event record qua cơ chế durable phù hợp.
2. Tách side effects chậm sang worker/queue, có retry/idempotency.
3. Định nghĩa rõ những sự kiện nào phải ghi thành công trước khi cho phép login (business/compliance requirement).
4. Tránh tạo dependency vòng lặp: listener gọi lại AuthenticationManager hoặc ném exception khó xử lý.
5. Đo drop/failure rate của event pipeline; không chỉ dựa vào việc có code `@EventListener`.
6. Trong cluster nhiều ứng dụng, event trong một JVM không tự broadcast sang node khác.

**Quan trọng:** event authentication được publish không nhất thiết mang đầy đủ HTTP request context. Nếu cần IP/user agent/session correlation, lấy từ một component được phép trong cùng security flow hoặc correlation context tin cậy, không giả định `AbstractAuthenticationFailureEvent` có sẵn các trường đó.

## 14. Test logic exact-class bằng Java 17 thuần

Trước khi kiểm với Spring runtime, có thể dùng một mini lab Java 17 minh họa **tra mapping bằng class chính xác**. Chương trình này không dùng Spring Security và không phát ApplicationEvent thật; nó diễn giải nguyên tắc mà tài liệu publisher mô tả.

Tạo tệp **ExactExceptionEventMappingDemo.java**:

~~~java
import java.util.Map;

public class ExactExceptionEventMappingDemo {

    static class CredentialFailure extends RuntimeException {}
    static class CustomCredentialFailure extends CredentialFailure {}
    static class DirectoryFailure extends RuntimeException {}
    static class UnknownFailure extends RuntimeException {}

    private static final Map<Class<? extends RuntimeException>, String>
            EVENTS = Map.of(
                    CredentialFailure.class, "BAD_CREDENTIALS",
                    DirectoryFailure.class, "SERVICE_FAILURE");

    static String eventFor(RuntimeException exception) {
        return EVENTS.getOrDefault(exception.getClass(), "UNMAPPED");
    }

    public static void main(String[] args) {
        System.out.println("Base = "
                + eventFor(new CredentialFailure()));
        System.out.println("Subclass = "
                + eventFor(new CustomCredentialFailure()));
        System.out.println("Service = "
                + eventFor(new DirectoryFailure()));
        System.out.println("Unknown = "
                + eventFor(new UnknownFailure()));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ExactExceptionEventMappingDemo.java
java ExactExceptionEventMappingDemo
~~~

Stdout chính xác:

~~~text
Base = BAD_CREDENTIALS
Subclass = UNMAPPED
Service = SERVICE_FAILURE
Unknown = UNMAPPED
~~~

Giải thích:

- `CredentialFailure.class` có mapping nên ra BAD_CREDENTIALS.
- `CustomCredentialFailure` là subclass nhưng **không được tự áp mapping superclass** nên ra UNMAPPED.
- Lỗi directory được map riêng sang SERVICE_FAILURE.
- Lỗi không có mapping rơi vào fallback UNMAPPED.
- Nếu thêm `CustomCredentialFailure.class` vào map, kết quả sẽ đổi theo mapping mới.

Từ đây áp dụng vào Spring Security với `Class<? extends AuthenticationException>` → `Class<? extends AbstractAuthenticationFailureEvent>`. **Không thay mã mini lab cho một Spring Security AuthenticationEventPublisher thực**; nó chỉ giúp người học hiểu exact-match và rủi ro quan sát thiếu sự kiện.

## 15. Kiểm thử Spring publisher mà không cần HTTP

Nên có một test nhỏ trực tiếp gọi publisher để kiểm rằng mapping hoạt động. Một hướng Spring Framework test là dùng ApplicationContext/listener giữ danh sách events.

Pseudocode test JUnit 5/Spring (cần dự án và imports thực):

~~~java
// Dựng context có @Bean AuthenticationEventPublisher từ mục 6.
// Đăng ký một listener gom event trong môi trường test.
Authentication attempted =
        new UsernamePasswordAuthenticationToken("user", "test-secret");

// Gọi trực tiếp để kiểm mapping, không tự khẳng định login thất bại.
publisher.publishAuthenticationFailure(
        new AuthenticationEventConfig
                .DirectoryTemporarilyUnavailableException("directory down"),
        attempted);

// Assertion: nhận đúng 1 AuthenticationFailureServiceExceptionEvent.
// Không được yêu cầu nhận AuthenticationFailureBadCredentialsEvent.
~~~

Đây là **mảnh test định hướng**, không phải class JUnit hoàn chỉnh hoặc lệnh chạy độc lập. Test thực nên dùng `ApplicationEvents` trong Spring Boot Test hoặc một Spring `ApplicationContext` có test listener, và xác minh count/type của event.

Điều cần test riêng:

- Direct call `publishAuthenticationFailure` kiểm **publisher mapping**.
- Gọi `AuthenticationManager.authenticate(...)` kiểm **integration publisher wiring**.
- Request thật qua filter chain kiểm response/failure handler/CSRF/session.
- Nếu có nhiều AuthenticationManager hoặc nhiều security chains, kiểm không có duplicate events.

Không lấy kết quả unit test publisher để kết luận mọi route đã phát event.

## 16. Ma trận kiểm thử đầy đủ

| Tình huống | Expected event / hành vi |
| --- | --- |
| `BadCredentialsException` chính xác | `AuthenticationFailureBadCredentialsEvent` |
| `LockedException` | `AuthenticationFailureLockedEvent` |
| `DisabledException` | `AuthenticationFailureDisabledEvent` |
| `CredentialsExpiredException` | `AuthenticationFailureCredentialsExpiredEvent` |
| `DirectoryTemporarilyUnavailableException` với mapping | `AuthenticationFailureServiceExceptionEvent` |
| `CredentialPolicyRejectedException` với mapping | `AuthenticationFailurePolicyRejectedEvent` |
| Exception không có mapping và fallback | `AuthenticationFailureUnmappedEvent` |
| Subclass custom mới không map | Fallback, không tự map theo superclass |
| Thêm custom mapping cho subclass mới | Event đúng loại đã cấu hình |
| Authentication thành công | `AuthenticationSuccessEvent` nếu publisher được gọi |
| Auth provider trả thất bại không ném `AuthenticationException` đúng flow | Điều tra vì có thể không phát event |
| Tạo `ProviderManager` thủ công nhưng quên gắn publisher | Listener không thấy event, không kết luận login không có lỗi |
| Parent và child managers đều publish | Có nguy cơ double event; cần thiết kế/test |
| Không có listener | Publisher vẫn phát nhưng không có handler audit cụ thể |
| Listener ném RuntimeException | Có thể ảnh hưởng flow; cần xử lý vận hành |
| Listener log credentials | Test/security review phải chặn |
| Login handler trả thông điệp khác theo lỗi | Kiểm chống account enumeration độc lập event mapping |
| Authorization 403 sau login | Không mặc định là authentication failure event |
| Directory outage | Không đếm thành password brute force |
| App chạy nhiều node | Các node phải có telemetry/audit tổng hợp phù hợp |

### Test regression khi nâng phiên bản

Lưu lại bộ test các class exception mà team dựa vào. Sau nâng Spring Security:

1. Xác nhận mapping mặc định và API còn tương thích.
2. Kiểm các `AuthenticationException` mới hoặc đổi hierarchy.
3. Đảm bảo `@Bean AuthenticationEventPublisher` được inject đúng manager.
4. Kiểm listener nhận event khi provider ném exception thực.
5. Kiểm không lộ account state hoặc credentials qua HTTP/log.
6. Kiểm số event và độ trễ trong tải thật.

## 17. Troubleshooting: vì sao custom exception không có event?

| Triệu chứng | Câu hỏi cần kiểm | Hướng xử lý |
| --- | --- | --- |
| Không thấy event cho custom exception | Đã có exact mapping cho class thực tế chưa? | Bổ sung Map entry |
| Subclass của BadCredentialsException không có event | Publisher có exact match, không tự thừa kế | Map subclass tường minh |
| Cấu hình @Bean rồi vẫn không thấy event | AuthenticationManager nào đang chạy? | Gắn publisher vào manager đúng |
| Event có ở test nhưng không có ở API | Filter/provider có đi qua manager hay tự bắt exception? | Kiểm call chain |
| Event loại bad credentials khi IdP outage | Exception được ném hoặc map sai | Chuyển về service failure |
| Listener được gọi hai lần | Parent/child manager hoặc nhiều listener? | Kiểm double publish và bean registration |
| Login chậm sau khi thêm listener | Listener gửi HTTP/SMTP đồng bộ | Dùng xử lý nhanh/queue |
| Event logging làm lộ mật khẩu | Log toàn bộ Authentication/Exception | Redact, allowlist fields |
| Không có event khi user 403 | Đây là authorization chứ không phải authentication | Xử lý AccessDenied riêng |
| Thêm Properties mapping gặp warning deprecated | Đang dùng API cũ | Dùng Map<Class,Class> |
| Fallback không được phát | Chưa cấu hình hoặc constructor event sai | Dùng concrete failure event hợp lệ |
| Một attempt có nhiều events | Nhiều provider/manager hoặc event publication trùng | Test trực tiếp manager wiring |

## 18. Checklist thiết kế mapping an toàn

1. Custom exception có thật sự đại diện **authentication failure**, hay chỉ là authorization/business error?
2. Đã xác định semantic: bad credential, locked, disabled, expired, service issue hay custom policy?
3. Class nào **thực sự được ném**? Có subclass mới không? Có mapping chính xác cho nó?
4. `DefaultAuthenticationEventPublisher` có được tạo như bean hoặc gắn vào đúng manager không?
5. Event class cụ thể có extends `AbstractAuthenticationFailureEvent` và constructor hợp lệ?
6. Có dùng typed `Map` thay `Properties` deprecated?
7. Fallback event có giúp bắt trường hợp bỏ sót mà không trộn sai semantic?
8. Listener có giới hạn thông tin, không log credentials/token/PII hoặc exception message nhạy cảm?
9. Listener chậm/lỗi có ảnh hưởng authentication latency hoặc phát tán sự cố không?
10. Có tách HTTP failure handler khỏi event listener và chống account enumeration?
11. Có kiểm integration với provider/manager thật, parent/child duplication và ứng dụng nhiều node?
12. Có test mapping + event count + status HTTP + authorization phân biệt riêng không?

**Kết luận:** Khi Spring Security phát sự kiện xác thực, **exception class cụ thể quyết định failure event** theo bảng mapping. Vì publisher mặc định **không tự suy mapping từ superclass**, custom exception nên được đăng ký qua `setAdditionalExceptionMappings(Map)` hoặc có fallback event được thiết kế rõ. Chọn event đúng bản chất lỗi, gắn publisher vào đúng `AuthenticationManager`, xử lý audit an toàn và kiểm thử cả mapping lẫn đường auth thực tế để tránh thiếu sự kiện, sai metrics và lộ dữ liệu nhạy cảm.

### Tài liệu tham khảo chính thức

- Spring Security — Authentication Events (Servlet, 7.0): https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/events.html
- Spring Security — DefaultAuthenticationEventPublisher API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/DefaultAuthenticationEventPublisher.html
- Spring Security — AuthenticationEventPublisher API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationEventPublisher.html
- Spring Security — AbstractAuthenticationFailureEvent API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/event/AbstractAuthenticationFailureEvent.html
- Spring Security — AuthenticationFailureBadCredentialsEvent API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/event/AuthenticationFailureBadCredentialsEvent.html
- Spring Security — ProviderManager API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ProviderManager.html
- Spring Framework — EventListener API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/EventListener.html
- Spring Security — Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
