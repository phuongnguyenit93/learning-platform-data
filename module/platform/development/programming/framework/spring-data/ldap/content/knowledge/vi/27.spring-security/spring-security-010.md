# Tách chi tiết lỗi nội bộ khỏi phản hồi đăng nhập công khai

Khi ứng dụng dùng **Spring Security kết hợp Spring Data LDAP**, một lần đăng nhập thất bại có thể đến từ nhiều nguyên nhân: người dùng nhập sai mật khẩu, không tìm thấy DN, tài khoản bị khóa, tài khoản bị vô hiệu hóa, mật khẩu hết hạn, LDAP server không phản hồi, chứng chỉ TLS lỗi hoặc cấu hình search/bind sai. Những nguyên nhân này cần được phân loại để vận hành và điều tra sự cố. Tuy nhiên, nếu trả nguyên nhân chi tiết về trình duyệt, API có thể tiết lộ tài khoản có tồn tại hay không, trạng thái khóa, cấu trúc directory hoặc thông tin nội bộ của hạ tầng.

Bài thuộc chương **Spring Security**, tập trung vào chủ đề **“Tách chi tiết lỗi nội bộ khỏi phản hồi đăng nhập công khai”**. Mục tiêu là xây dựng hai lớp thông tin riêng: **phản hồi công khai ổn định, tối thiểu** cho người đăng nhập và **diagnostic nội bộ có kiểm soát** cho audit, cảnh báo và xử lý sự cố. Bài cũng chỉ ra vị trí của `AuthenticationFailureHandler`, `AuthenticationEntryPoint`, `AccessDeniedHandler` và authentication events trong luồng Spring Security.

Trong phạm vi **SPRING_DATA_LDAP**, ứng dụng tìm DN, xác thực bằng bind qua LDAP server, đọc attribute và lấy authorities. Directory server có thể trả diagnostic khác nhau theo sản phẩm và phiên bản; ứng dụng cần phân loại theo adapter đã xác minh, không chuyển raw exception hoặc LDAP diagnostic trực tiếp thành nội dung HTTP.

> **Nguyên tắc:** người dùng cần biết lần đăng nhập không thành công hoặc dịch vụ xác thực tạm thời không sẵn sàng. Nhân viên vận hành cần biết nhóm nguyên nhân, bước LDAP bị lỗi và correlation ID. Hai nhu cầu này không cần dùng chung một thông điệp.

## 1. Rủi ro khi trả nguyên nhân lỗi LDAP cho client

Một API đăng nhập có thể vô tình tiết lộ nhiều thông tin nếu phản hồi dựa trực tiếp trên exception:

| Phản hồi công khai | Thông tin bị tiết lộ |
|---|---|
| “Không tìm thấy user u1001” | Có thể kiểm tra username nào tồn tại trong directory |
| “Tài khoản u1002 đang bị khóa” | Xác nhận tài khoản tồn tại và đang locked |
| “Tài khoản đã bị vô hiệu hóa” | Tiết lộ trạng thái nhân sự hoặc provisioning |
| “Password hết hạn ngày 30/11” | Tiết lộ policy và dữ liệu vòng đời tài khoản |
| “Bind DN cn=manager,dc=example,dc=org sai mật khẩu” | Tiết lộ cấu trúc DN và danh tính service account |
| “LDAP server ldap01.internal:636 từ chối kết nối” | Tiết lộ hostname, topology và cổng nội bộ |
| Trả raw diagnostic của AD/OpenLDAP | Tiết lộ mã lỗi vendor, trạng thái account hoặc chi tiết cấu hình |

Kẻ tấn công có thể tự động gửi nhiều username và so sánh status code, body, header hoặc thời gian phản hồi. Nếu mỗi trạng thái có một response khác nhau, endpoint đăng nhập trở thành **account enumeration oracle**.

Thông tin chi tiết không chỉ xuất hiện trong body. Cũng cần kiểm tra:

- HTTP status khác nhau giữa user không tồn tại và mật khẩu sai.
- Redirect đến trang “account locked” chỉ với username hợp lệ.
- Header hoặc error code riêng cho từng trạng thái.
- Response time khác biệt rõ rệt giữa search miss và bind failure.
- GraphQL error, validation error hoặc tracing metadata vô tình chứa exception message.
- Frontend hiển thị nguyên nội dung exception message.

## 2. Tách các lớp kết quả xác thực

Không nên gom mọi thất bại thành một biến boolean duy nhất. Hãy phân loại nội bộ theo nhóm nguyên nhân:

| Nhóm nội bộ | Ví dụ | Ý nghĩa vận hành |
|---|---|---|
| `BAD_CREDENTIALS` | Password không khớp | Credential không hợp lệ |
| `USER_NOT_FOUND` | Search không tìm được DN | Principal không được định vị |
| `ACCOUNT_LOCKED` | Server xác nhận account bị khóa | Cần xử lý lockout theo policy |
| `ACCOUNT_DISABLED` | Account bị admin disable | Cần kiểm tra vòng đời/provisioning |
| `ACCOUNT_EXPIRED` | Account hết hạn | Cần workflow gia hạn |
| `PASSWORD_EXPIRED` | Password hết hạn | Có thể cần luồng đổi password |
| `DIRECTORY_UNAVAILABLE` | Timeout, connection refused, server unavailable | Dependency không sẵn sàng |
| `TLS_FAILURE` | Trust chain hoặc hostname verification lỗi | Cần kiểm tra TLS/certificate |
| `DIRECTORY_CONFIGURATION` | Search base, bind identity hoặc schema sai | Lỗi cấu hình/triển khai |
| `AMBIGUOUS_PRINCIPAL` | Search trả nhiều DN | Định danh không duy nhất, cần điều tra |
| `UNKNOWN` | Không phân loại được | Cần điều tra nội bộ |

Đây là taxonomy của ứng dụng, không phải một tập LDAP result code chuẩn. Một số provider có thể gom nhiều lỗi account thành `BadCredentialsException`; server khác có thể cung cấp diagnostic chi tiết. Chỉ phân loại sâu khi có nguồn dữ liệu đáng tin và adapter theo đúng directory product/version.

### Ba kết quả cần phân biệt

1. **Authentication failure do người dùng:** credential hoặc trạng thái account không cho phép bind.
2. **Authentication unavailable do hạ tầng:** không thể kết nối hoặc xác minh với directory.
3. **Authorization failure:** người dùng đã xác thực nhưng không có quyền truy cập tài nguyên.

Không đổi lỗi hạ tầng thành “sai mật khẩu”. Điều đó làm người dùng hiểu sai, có thể kích hoạt quy trình reset password hoặc tăng số lần đăng nhập thất bại không cần thiết.

## 3. Phản hồi công khai nên giữ ổn định

Đối với lỗi liên quan đến trạng thái hoặc credential của một tài khoản, dùng cùng một response:

```json
{
  "code": "AUTHENTICATION_FAILED",
  "message": "Tên đăng nhập hoặc thông tin xác thực không hợp lệ."
}
```

Dùng cùng contract cho các trường hợp:

- Username không tồn tại.
- Password sai.
- Account locked.
- Account disabled.
- Account expired.
- Password expired, nếu luồng đăng nhập hiện tại không hỗ trợ password-change challenge.

Không trả `404 User not found`, `423 Locked`, `403 Disabled` hoặc các mã riêng cho từng trạng thái trong endpoint đăng nhập công khai. Các trạng thái này có thể được hiển thị trong kênh quản trị đã xác thực và phân quyền.

Một response chung không có nghĩa bỏ qua trạng thái thật. Backend vẫn ghi nhận category nội bộ để audit và hỗ trợ người dùng qua quy trình phù hợp.

### Khi nào có thể trả thông báo khác?

Lỗi phụ thuộc hạ tầng có thể dùng response riêng, ví dụ:

```json
{
  "code": "AUTHENTICATION_UNAVAILABLE",
  "message": "Hiện không thể xác thực. Vui lòng thử lại sau."
}
```

Thông báo này cho biết dịch vụ tạm thời không sẵn sàng, không xác nhận username có tồn tại hay không. Không gửi hostname, exception class, LDAP result code hoặc diagnostic raw.

## 4. Chọn HTTP status theo loại lỗi

Một quy ước có thể áp dụng cho REST API:

| HTTP status | Trường hợp | Response công khai |
|---|---|---|
| `400 Bad Request` | Request thiếu field bắt buộc hoặc sai định dạng | Lỗi input chung, không phản ánh trạng thái directory |
| `401 Unauthorized` | Credential hoặc account không được chấp nhận | `AUTHENTICATION_FAILED` |
| `403 Forbidden` | Đã xác thực nhưng không có quyền | Thông báo truy cập bị từ chối |
| `429 Too Many Requests` | Rate limit hoặc throttling | Yêu cầu thử lại sau |
| `503 Service Unavailable` | LDAP dependency hoặc authentication service tạm thời không sẵn sàng | `AUTHENTICATION_UNAVAILABLE` |
| `500 Internal Server Error` | Lỗi ứng dụng ngoài dự kiến | Thông báo lỗi chung và request ID nếu có |

Không dùng status `401` cho mọi lỗi LDAP bất kể nguyên nhân. Nếu LDAP server mất kết nối nhưng API trả “sai mật khẩu”, client có thể yêu cầu đổi password và người vận hành khó nhận ra sự cố hạ tầng.

Ngược lại, không trả `503` cho account locked hay user không tồn tại. Các lỗi này là kết quả xác thực của principal, không phải directory outage.

HTTP status là một phần của public contract. Hãy kiểm thử body, status và header cùng nhau; chỉ kiểm tra nội dung message là chưa đủ.

## 5. Luồng Spring Security: ai xử lý lỗi ở đâu?

Trong servlet authentication, luồng phổ biến gồm:

```text
HTTP login request
       │
       ▼
Authentication filter
       │
       ▼
AuthenticationManager
       │
       ▼
ProviderManager
       │
       ▼
LdapAuthenticationProvider
       │
       ▼
LdapAuthenticator
(search DN / bind user)
       │
       ├── thành công → Authentication → SecurityContext
       │
       └── thất bại → AuthenticationException
                            │
                            ▼
                  AuthenticationFailureHandler
                            │
                            ▼
                  Public response ổn định
```

Các thành phần có trách nhiệm khác nhau:

- `AuthenticationProvider` thực hiện một loại xác thực.
- `ProviderManager` điều phối các provider.
- `LdapAuthenticationProvider` dùng `LdapAuthenticator` để xác thực và `LdapAuthoritiesPopulator` để lấy authorities.
- `AuthenticationFailureHandler` xử lý phản hồi khi authentication filter thất bại.
- `AuthenticationEventPublisher` có thể phát event để listener ghi nhận kết quả nội bộ.

**Không đặt logic hiển thị lỗi LDAP rải rác trong repository, controller và mapper.** Provider/service nên phân loại nguyên nhân nội bộ; failure handler quyết định public response.

## 6. Spring Security LDAP không đọc password từ directory để so sánh

Với bind authentication, ứng dụng gửi credential người dùng tới LDAP server qua kết nối được bảo vệ. Server thực hiện xác minh. Spring Security LDAP dùng `LdapAuthenticator`; nó không dựa vào `UserDetailsService` để đọc password hoặc hash password từ LDAP rồi tự so sánh.

Điều này có hai hệ quả:

1. Ứng dụng không nên đọc `userPassword` hoặc attribute tương tự để tự xác minh password.
2. Một số trạng thái account hoặc diagnostic chỉ được biết qua kết quả bind, response control hoặc thuộc tính server-specific mà service account được phép đọc.

Ví dụ cấu hình bind theo search filter:

```java
@Bean
AuthenticationManager ldapAuthenticationManager(
        BaseLdapPathContextSource contextSource) {

    LdapBindAuthenticationManagerFactory factory =
            new LdapBindAuthenticationManagerFactory(contextSource);

    factory.setUserSearchBase("ou=people");
    factory.setUserSearchFilter(
            "(&(objectClass=inetOrgPerson)(uid={0}))");

    return factory.createAuthenticationManager();
}
```

Đoạn code cấu hình cơ chế search user rồi bind. Nó không tự đảm bảo mọi diagnostic của AD/OpenLDAP sẽ được giữ nguyên hoặc map thành exception cụ thể. Hành vi phụ thuộc server, client provider và phiên bản Spring Security/Spring LDAP.

## 7. Phân biệt AuthenticationFailureHandler, AuthenticationEntryPoint và AccessDeniedHandler

Ba thành phần này thường bị dùng nhầm:

| Thành phần | Khi nào chạy? | Trách nhiệm |
|---|---|---|
| `AuthenticationFailureHandler` | Authentication filter nhận credential nhưng xác thực thất bại | Xử lý kết quả login failure |
| `AuthenticationEntryPoint` | Request cần authentication nhưng caller chưa được xác thực | Yêu cầu credential hoặc trả challenge/401 |
| `AccessDeniedHandler` | Caller đã xác thực nhưng không đủ quyền | Trả 403 hoặc xử lý access denied |

Ví dụ:

- `POST /login` với password sai: `AuthenticationFailureHandler`.
- `GET /api/private` không có token/session: `AuthenticationEntryPoint`.
- User đã đăng nhập nhưng không có `ROLE_ADMIN`: `AccessDeniedHandler`.

Nếu dùng `AuthenticationEntryPoint` để xử lý mọi login failure, có thể làm mất phân biệt giữa credential submission và request truy cập tài nguyên được bảo vệ.

## 8. Cấu hình failure handler trả JSON chung

Ví dụ sau dùng `AuthenticationFailureHandler` để trả JSON cho form login hoặc authentication filter tương ứng:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.http.MediaType;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

@Component
public final class PublicLoginFailureHandler
        implements AuthenticationFailureHandler {

    private final ObjectMapper objectMapper;
    private final LoginFailureClassifier classifier;

    public PublicLoginFailureHandler(
            ObjectMapper objectMapper,
            LoginFailureClassifier classifier) {
        this.objectMapper = objectMapper;
        this.classifier = classifier;
    }

    @Override
    public void onAuthenticationFailure(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception)
            throws IOException, ServletException {

        boolean unavailable =
                classifier.isDirectoryUnavailable(exception);

        response.setStatus(unavailable
                ? HttpServletResponse.SC_SERVICE_UNAVAILABLE
                : HttpServletResponse.SC_UNAUTHORIZED);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setHeader("Cache-Control", "no-store");

        LoginFailureResponse body = unavailable
                ? new LoginFailureResponse(
                        "AUTHENTICATION_UNAVAILABLE",
                        "Hiện không thể xác thực. Vui lòng thử lại sau.")
                : new LoginFailureResponse(
                        "AUTHENTICATION_FAILED",
                        "Tên đăng nhập hoặc thông tin xác thực không hợp lệ.");

        objectMapper.writeValue(response.getOutputStream(), body);
    }

    public record LoginFailureResponse(String code, String message) {}
}
```

Điểm quan trọng:

- Handler không trả `exception.getMessage()`.
- Handler không đọc raw LDAP diagnostic để tạo message.
- Các trạng thái user-level có cùng body và status.
- Lỗi dependency được phân loại thành `503` bằng classifier có kiểm soát.
- `Cache-Control: no-store` tránh lưu response đăng nhập trong cache thông thường.

Nếu endpoint là REST login tự viết thay vì filter form login, cần tích hợp cùng policy vào authentication flow của endpoint. Không gọi `AuthenticationFailureHandler` từ mọi controller một cách tùy tiện; hãy dùng filter hoặc một service/response mapper dùng chung, có test rõ ràng.

## 9. Phân loại lỗi hạ tầng bằng allowlist nguyên nhân

Một classifier không nên suy luận lỗi từ chuỗi message. Hãy kiểm tra exception type/cause đã biết và những exception mà provider thực sự phát ra trong phiên bản đang dùng.

Ví dụ minh họa cho một số lỗi transport:

```java
import javax.naming.CommunicationException;
import javax.naming.ServiceUnavailableException;
import java.net.ConnectException;
import java.net.SocketTimeoutException;
import javax.net.ssl.SSLException;

import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.core.AuthenticationException;
import org.springframework.stereotype.Component;

@Component
public final class LoginFailureClassifier {

    public boolean isDirectoryUnavailable(
            AuthenticationException exception) {

        if (exception instanceof AuthenticationServiceException) {
            return true;
        }

        for (Throwable cause = exception;
                cause != null;
                cause = cause.getCause()) {

            if (cause instanceof CommunicationException
                    || cause instanceof ServiceUnavailableException
                    || cause instanceof ConnectException
                    || cause instanceof SocketTimeoutException
                    || cause instanceof SSLException) {
                return true;
            }
        }

        return false;
    }
}
```

Đây là điểm bắt đầu, không phải classifier dùng nguyên xi cho mọi hệ thống. Một số provider bọc exception trong loại khác; một số lỗi TLS là lỗi cấu hình cần xử lý như incident thay vì retry. Hãy kiểm tra cause chain của đúng client/provider, viết test cho từng tình huống và mở rộng allowlist theo bằng chứng.

Không làm:

```java
// Không an toàn và không ổn định giữa các version/server.
if (exception.getMessage().contains("49")) {
    return false;
}
```

Message có thể được dịch, thay đổi, bị provider rút gọn hoặc chứa dữ liệu nhạy cảm. Dùng exception type, LDAP result code/control có cấu trúc hoặc adapter vendor-specific; nếu không đủ bằng chứng, phân loại `UNKNOWN`.

## 10. Không để exception chi tiết đi thẳng tới HTTP

Các anti-pattern thường gặp:

```java
// Không trả nguyên message nội bộ cho client.
return ResponseEntity.status(401)
        .body(exception.getMessage());
```

```java
// Không đưa raw cause vào JSON.
return ResponseEntity.status(401)
        .body(Map.of(
                "error", exception.toString(),
                "cause", exception.getCause()));
```

```java
// Không chuyển diagnostic LDAP thành mã công khai trực tiếp.
return ResponseEntity.status(401)
        .body(Map.of("ldapError", ldapResult.getDiagnosticMessage()));
```

Thay vào đó, tạo một lớp chuyển đổi có allowlist:

- Nhận exception hoặc failure category nội bộ.
- Phân loại thành `AUTHENTICATION_FAILED`, `AUTHENTICATION_UNAVAILABLE` hoặc lỗi public contract đã định.
- Chỉ chọn status code và message từ hằng số.
- Tạo request/correlation ID từ middleware tin cậy.
- Ghi diagnostic nội bộ ở sink được bảo vệ.

Không serialize toàn bộ `AuthenticationException`, `Authentication`, `DirContext`, `NamingException` hoặc `LdapResult` vào response.

## 11. Giữ diagnostic nội bộ có cấu trúc

Một record nội bộ có thể biểu diễn những gì vận hành cần:

```java
public enum DirectoryFailureCategory {
    BAD_CREDENTIALS,
    USER_NOT_FOUND,
    ACCOUNT_LOCKED,
    ACCOUNT_DISABLED,
    ACCOUNT_EXPIRED,
    PASSWORD_EXPIRED,
    DIRECTORY_UNAVAILABLE,
    TLS_FAILURE,
    DIRECTORY_CONFIGURATION,
    AMBIGUOUS_PRINCIPAL,
    UNKNOWN
}

public record AuthenticationDiagnostic(
        DirectoryFailureCategory category,
        String operation,
        String directoryAlias,
        String requestId,
        String causeType
) {}
```

Các field này giúp trả lời:

- Lỗi xảy ra ở search DN, user bind hay group lookup?
- Directory logical alias nào gặp sự cố?
- Có phải lỗi transport, TLS, account state hay credential?
- Request nào tương ứng với log/trace?
- Adapter nào đã phân loại lỗi?

Không cần đưa toàn bộ diagnostic LDAP vào record. Nếu cần điều tra sâu, có thể lưu result code đã chuẩn hóa hoặc mã vendor đã xác minh trong hệ thống log có quyền truy cập riêng.

## 12. Ánh xạ diagnostic theo server/version

Một directory server có thể cung cấp mã hoặc control riêng. Ví dụ Active Directory có thể trả result code `invalidCredentials` cùng diagnostic `data` code; OpenLDAP có thể hỗ trợ Password Policy response control khi ppolicy overlay được cấu hình.

Quy trình phân loại nên là:

1. Xác định product và version của directory.
2. Xác minh diagnostic/control thực tế bằng integration test.
3. Tạo adapter riêng cho server đó.
4. Map tín hiệu đã xác minh sang failure category nội bộ.
5. Giữ `UNKNOWN` nếu diagnostic thiếu, không hợp lệ hoặc không được expose.
6. Không để adapter thay đổi public response trực tiếp.

Ví dụ mapping khái niệm:

| Tín hiệu nội bộ đã xác minh | Category nội bộ |
|---|---|
| AD diagnostic code đã xác minh cho locked | `ACCOUNT_LOCKED` |
| AD diagnostic code đã xác minh cho disabled | `ACCOUNT_DISABLED` |
| Ppolicy response xác nhận password expired | `PASSWORD_EXPIRED` |
| Connection timeout đến LDAP | `DIRECTORY_UNAVAILABLE` |
| TLS certificate/hostname validation failure | `TLS_FAILURE` |
| Không hiểu response | `UNKNOWN` |

Các mã vendor không phải LDAP result code portable. Không copy bảng mã từ một môi trường AD sang OpenLDAP hoặc một sản phẩm khác. Đặc biệt, đừng parse chuỗi diagnostic bằng regex chung trong controller.

## 13. Dùng Authentication Events cho quan sát nội bộ

Spring Security có authentication events cho thành công và thất bại. Một số failure events gồm:

- `AuthenticationFailureBadCredentialsEvent`.
- `AuthenticationFailureLockedEvent`.
- `AuthenticationFailureDisabledEvent`.
- `AuthenticationFailureExpiredEvent`.
- `AuthenticationFailureCredentialsExpiredEvent`.
- `AuthenticationFailureServiceExceptionEvent`.
- `AuthenticationFailureProviderNotFoundEvent`.

Các event này có thể hỗ trợ metrics, audit và cảnh báo. Chúng phản ánh loại exception mà `AuthenticationManager` phát ra; chúng không đảm bảo provider đã phân biệt mọi diagnostic vendor-specific của LDAP.

Để publish event, có thể cấu hình `DefaultAuthenticationEventPublisher` với Spring `ApplicationEventPublisher` theo tài liệu Spring Security:

```java
@Bean
AuthenticationEventPublisher authenticationEventPublisher(
        ApplicationEventPublisher applicationEventPublisher) {

    return new DefaultAuthenticationEventPublisher(
            applicationEventPublisher);
}
```

Đảm bảo publisher được gắn vào `AuthenticationManager`/`ProviderManager` thực tế của ứng dụng. Cách cấu hình cụ thể phụ thuộc cách bạn tạo manager (auto-configuration, DSL hay factory riêng).

## 14. Listener ghi audit mà không lộ credential

Một listener có thể ghi nhận failure event:

```java
import org.springframework.context.event.EventListener;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.stereotype.Component;

@Component
public final class AuthenticationAuditListener {

    private final SubjectReferenceHasher subjectHasher;
    private final AuditLogger auditLogger;

    public AuthenticationAuditListener(
            SubjectReferenceHasher subjectHasher,
            AuditLogger auditLogger) {
        this.subjectHasher = subjectHasher;
        this.auditLogger = auditLogger;
    }

    @EventListener
    public void onFailure(AbstractAuthenticationFailureEvent event) {
        String subjectRef = subjectHasher.hmac(
                event.getAuthentication().getName());

        auditLogger.authenticationFailed(
                event.getClass().getSimpleName(),
                subjectRef);
    }
}
```

Ví dụ dùng HMAC có khóa để tạo subject reference ổn định cho audit. Không dùng plain hash của username nếu có thể dò ngược bằng dictionary. Khóa HMAC cần được bảo vệ và có quy trình rotation.

Trong hệ thống thật, bổ sung request ID, logical directory alias, operation và timestamp. Không log `event.toString()`, toàn bộ `Authentication` hoặc `event.getException().getMessage()` vì các object này có thể chứa credential hoặc dữ liệu nhạy cảm.

## 15. Những gì không được ghi vào log/trace/metric

| Dữ liệu | Cách xử lý |
|---|---|
| Password người dùng | Tuyệt đối không ghi |
| Service account password | Tuyệt đối không ghi |
| `Authentication.getCredentials()` | Không log hoặc đưa vào trace |
| Raw LDAP filter chứa input | Không log nguyên văn; redact hoặc log template đã chuẩn hóa |
| Full DN | Chỉ ghi nếu thực sự cần, giới hạn quyền và retention |
| Raw vendor diagnostic | Chỉ lưu ở sink hạn chế, đã scrub; ưu tiên mã đã chuẩn hóa |
| Username/email | Hạn chế; dùng keyed pseudonymous reference khi phù hợp |
| LDAP hostname/IP nội bộ | Dùng logical alias trong log phổ thông |
| Exception message | Kiểm tra và scrub trước khi ghi |
| Session ID/token | Không ghi raw token; chỉ ghi identifier an toàn nếu cần |

### Metrics phải có cardinality thấp

Không dùng username, DN, email, IP hoặc request ID làm metric label. Chúng tạo cardinality rất lớn và có thể làm lộ dữ liệu cá nhân.

Label phù hợp hơn:

- `outcome=success|failure|unavailable`.
- `category=bad_credentials|locked|directory_unavailable|unknown`.
- `operation=search|bind|group_lookup`.
- `directory=primary|secondary`.

Metrics giúp phát hiện tỷ lệ lỗi tăng; audit log giúp điều tra từng request. Hai loại dữ liệu có mục đích và retention khác nhau.

## 16. Correlation ID nối public response với log nội bộ

Khi response cần hỗ trợ người dùng liên hệ helpdesk, có thể trả một request ID do server tạo:

```json
{
  "code": "AUTHENTICATION_UNAVAILABLE",
  "message": "Hiện không thể xác thực. Vui lòng thử lại sau.",
  "requestId": "01JQ..."
}
```

ID này chỉ là tham chiếu để tra cứu, không chứa username, DN, host hoặc error code. Server ghi cùng ID trong structured log, trace và audit event.

Không tin một correlation ID tùy ý do client gửi rồi dùng nó làm định danh duy nhất. Nếu chấp nhận request ID từ gateway, phải xác minh gateway là nguồn tin cậy và chuẩn hóa giá trị. Nếu không, tạo ID phía server.

Không đưa exception message vào trường request ID hoặc mã lỗi.

## 17. Chống account enumeration và timing side-channel

Cùng response body/status là cần thiết nhưng chưa đủ. Kẻ tấn công còn có thể so sánh thời gian phản hồi.

Ví dụ:

- User không tồn tại: search trả ngay.
- User tồn tại: search xong mới bind, mất thêm thời gian.
- User locked: server trả diagnostic sớm.
- Directory unavailable: timeout vài giây.

Không thể bảo đảm mọi request có thời gian tuyệt đối bằng nhau vì network, server load và policy khác nhau. Tuy vậy, có thể giảm tín hiệu dễ khai thác:

1. Dùng cùng message/status cho user-not-found, bad-password và account-state failures.
2. Không thực hiện truy vấn status bổ sung chỉ để tạo response khác cho một username.
3. Tránh trả chi tiết theo từng nhánh exception.
4. Áp dụng rate limit theo IP, client và subject reference đã chuẩn hóa.
5. Theo dõi phân bố latency để phát hiện chênh lệch quá rõ.
6. Không thêm delay cố định lớn một cách máy móc; nó có thể tạo DoS và làm tăng tải.
7. Không xác nhận account tồn tại qua endpoint “check username” công khai.

Rate limit phải phối hợp với lockout policy của LDAP. Một lần nhập sai không nên kích hoạt retry tự động nhiều lần; ứng dụng không được khuếch đại lockout bằng retry loop.

## 18. Password expired và account locked cần luồng hỗ trợ riêng

Response đăng nhập công khai có thể trung tính, nhưng sản phẩm vẫn cần hỗ trợ người dùng hợp lệ:

- Password expired: cung cấp quy trình đổi password sau khi xác minh danh tính qua kênh được phép.
- Must change password: không cấp session đầy đủ trước khi hoàn tất bước đổi password theo policy.
- Account locked: hướng dẫn liên hệ helpdesk hoặc chờ lockout duration theo policy, nhưng không xác nhận account đang locked chỉ từ public login response.
- Account disabled/expired: workflow HR/IAM hoặc directory admin xử lý.
- Directory unavailable: thông báo thử lại sau, không yêu cầu đổi password.

Một endpoint reset password cũng không nên trả “username này không tồn tại”. Với request reset, có thể dùng response chung như “Nếu tài khoản đủ điều kiện, hướng dẫn sẽ được gửi qua kênh đã đăng ký.” Cách gửi thông báo và chống lạm dụng cần được thiết kế riêng.

## 19. Tách lỗi authentication khỏi lỗi authorization

Sau khi bind thành công, Spring Security có thể tạo `Authentication` và đặt nó vào `SecurityContext`. Authorities thường được lấy từ group lookup hoặc mapper.

Nếu user đã đăng nhập nhưng truy cập chức năng không có quyền:

- Đây là authorization failure.
- Không ghi nhận như password sai.
- Không tăng bộ đếm login failure.
- Dùng `AccessDeniedHandler` cho HTTP 403.
- Audit resource/action bị từ chối theo policy.

Ngược lại, request chưa được xác thực truy cập tài nguyên bảo vệ sẽ đi qua `AuthenticationEntryPoint`. Phân biệt rõ hai trường hợp giúp log và metrics không làm sai tỷ lệ authentication failure.

## 20. Kiểm thử public contract và internal diagnostics

Kiểm thử phải chứng minh cả hai phía: client không nhận chi tiết nhạy cảm, còn vận hành vẫn nhận category đủ dùng.

### 20.1 Ma trận phản hồi công khai

| Tình huống | HTTP | Code công khai | Có lộ trạng thái account? |
|---|---:|---|---|
| User không tồn tại | 401 | `AUTHENTICATION_FAILED` | Không |
| Password sai | 401 | `AUTHENTICATION_FAILED` | Không |
| Account locked | 401 | `AUTHENTICATION_FAILED` | Không |
| Account disabled | 401 | `AUTHENTICATION_FAILED` | Không |
| Account expired | 401 | `AUTHENTICATION_FAILED` | Không |
| Password expired | 401 hoặc flow challenge đã xác minh | Theo contract chung | Không lộ trước khi xác minh |
| LDAP timeout | 503 | `AUTHENTICATION_UNAVAILABLE` | Không |
| TLS trust failure | 503 hoặc lỗi dịch vụ theo policy | `AUTHENTICATION_UNAVAILABLE` | Không |
| User đã đăng nhập nhưng thiếu role | 403 | `ACCESS_DENIED` | Không liên quan account state |
| Rate limit | 429 | `TOO_MANY_REQUESTS` | Không |

### 20.2 Unit test cho handler

Các assertion nên bao gồm:

- Body của bad credentials và locked account giống nhau.
- Body của user-not-found và disabled account giống nhau.
- Không có `exception.getMessage()` trong JSON.
- Không có raw DN, hostname, LDAP result code hoặc diagnostic.
- `Cache-Control` là `no-store`.
- Directory unavailable trả status/body theo contract đã chọn.
- Cause chain không nhận diện được thì đi vào fallback an toàn, không tự phân loại từ message.

### 20.3 Integration test với LDAP server

Chuẩn bị user active, locked, disabled và expired trong lab phù hợp:

1. Thử user không tồn tại và password sai; so sánh status/body/header.
2. Thử account locked và disabled; xác minh public response không phân biệt.
3. Gây timeout hoặc dừng test directory; xác minh lỗi dependency không bị báo là password sai.
4. Thử TLS với truststore/hostname sai; xác minh không có credential bị log.
5. Cấu hình service account thiếu quyền search; xác minh internal category là configuration/ACL issue, public response không lộ chi tiết.
6. Kiểm tra event publisher phát event khi đã cấu hình.
7. Kiểm tra listener không log credentials, raw authentication object hoặc raw diagnostic.
8. Thử rate limit và lockout policy để tránh retry khuếch đại failure.
9. So sánh response time ở mức phân bố; tìm chênh lệch quá rõ có thể dùng để enumerate.
10. Kiểm tra request ID xuất hiện trong response và internal log nhưng không chứa dữ liệu người dùng.

### 20.4 Ví dụ test contract

```java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class PublicLoginResponsePolicyTest {

    @Test
    void userSpecificFailuresUseSamePublicCode() {
        var badCredentials = new LoginFailureResponse(
                "AUTHENTICATION_FAILED",
                "Tên đăng nhập hoặc thông tin xác thực không hợp lệ.");

        var lockedAccount = new LoginFailureResponse(
                "AUTHENTICATION_FAILED",
                "Tên đăng nhập hoặc thông tin xác thực không hợp lệ.");

        assertEquals(badCredentials, lockedAccount);
    }
}
```

Test trên minh họa contract object. Trong dự án thật, nên test trực tiếp HTTP response của failure handler và kiểm tra cả status, body, header.

## 21. Checklist triển khai

Trước khi phát hành luồng đăng nhập LDAP:

- [ ] Phân biệt credential/account failure, directory unavailable và authorization failure.
- [ ] Dùng cùng public response cho user-not-found, bad-password, locked, disabled và expired.
- [ ] Không trả `exception.getMessage()`, raw LDAP diagnostic hoặc full DN.
- [ ] Dùng `AuthenticationFailureHandler` cho login filter failure.
- [ ] Dùng `AuthenticationEntryPoint` cho request chưa xác thực và `AccessDeniedHandler` cho authorization failure.
- [ ] Không nhầm web login failure với directory dependency outage.
- [ ] Phân loại lỗi hạ tầng bằng exception/control đã xác minh, không parse message tùy tiện.
- [ ] Có adapter riêng cho AD/OpenLDAP và fallback `UNKNOWN`.
- [ ] Publish authentication events nếu cần audit/metrics; xác minh publisher được gắn vào manager thực tế.
- [ ] Listener không log raw `Authentication`, credentials hoặc exception message.
- [ ] Dùng structured log với request ID, operation và category nội bộ.
- [ ] Hạn chế username/DN; dùng keyed pseudonymous reference khi phù hợp.
- [ ] Không dùng PII/request ID làm metric labels.
- [ ] Có rate limit và kiểm soát retry để tránh lockout amplification.
- [ ] Có quy trình password reset/unlock/enable được xác minh và phân quyền.
- [ ] Có test response equality giữa các trạng thái account.
- [ ] Có integration test với directory server, TLS, ACL và outage.
- [ ] Kiểm tra log/trace/metric không chứa password, raw filter hoặc token.
- [ ] Đánh giá timing side-channel và không tạo endpoint username enumeration.
- [ ] Có retention/access policy cho audit log và diagnostic nội bộ.

### Tài liệu tham khảo

- [Spring Security — LDAP Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html) — bind authentication và `LdapAuthenticator`.
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html) — `AuthenticationManager`, filter và failure handler.
- [Spring Security — Authentication Events](https://docs.spring.io/spring-security/reference/servlet/authentication/events.html) — publish và lắng nghe authentication events.
- [Spring Security API — AbstractAuthenticationFailureEvent](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/event/AbstractAuthenticationFailureEvent.html).
- [Spring Security API — AuthenticationFailureServiceExceptionEvent](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/event/AuthenticationFailureServiceExceptionEvent.html).
- [Spring Security API — LdapAuthenticationProvider](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/ldap/authentication/LdapAuthenticationProvider.html).
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511).
- [RFC 4513 — LDAP Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513).

**Kết luận:** phân loại lỗi chi tiết là việc của backend, còn phản hồi đăng nhập công khai cần ổn định và tối thiểu. Dùng `AuthenticationFailureHandler` để tạo response chung, phân biệt lỗi credential với lỗi directory availability, dùng authentication events và structured audit cho vận hành, đồng thời bảo vệ log/trace khỏi password, DN và raw diagnostic. Khi các lớp này được tách rõ, ứng dụng vừa hỗ trợ điều tra sự cố LDAP vừa hạn chế account enumeration và rò rỉ thông tin nội bộ.
