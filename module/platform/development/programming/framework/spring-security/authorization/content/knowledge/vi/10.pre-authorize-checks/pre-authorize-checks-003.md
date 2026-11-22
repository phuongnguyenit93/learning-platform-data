# Tham chiếu authentication, principal và tên người dùng

> **Module:** Spring Security – authorization  
> **Nhóm:** Kiểm tra trước phương thức  
> **Trọng tâm:** Sử dụng các biểu thức `authentication`, `principal`, `authentication.name`, `principal.username` bên trong `@PreAuthorize`; so sánh tham số method với identity của người gọi; xử lý khác biệt giữa UserDetails, JWT, OAuth2 và anonymous; tránh nhầm tên hiển thị với định danh ổn định và quyền trên tài nguyên.

## 1. Bài toán: người gọi có thật là chủ hồ sơ?

Một ứng dụng có service:

~~~java
public ProfileDto getProfile(String username) {
    return repository.findByUsername(username);
}
~~~

Nếu Alice gọi `getProfile("alice")`, có thể cho phép đọc hồ sơ của mình. Nếu Bob gọi `getProfile("alice")`, phải từ chối trừ khi Bob có quyền được thiết kế riêng.

Spring Security cho phép viết:

~~~java
@PreAuthorize(
    "isAuthenticated() and #username == authentication.name"
)
public ProfileDto getProfile(String username) {
    return repository.findByUsername(username);
}
~~~

Expression này có ý định: **người gọi phải được xem là authenticated, và tham số `username` của lời gọi phải trùng tên do `Authentication#getName()` báo**.

Tuy nhiên, để dùng an toàn, cần hiểu:

- `authentication` là **object Authentication**, không phải chuỗi username.
- `principal` là **object danh tính** bên trong Authentication, không nhất thiết là `UserDetails`.
- `authentication.name` là **kết quả `getName()`**, có thể là username, ID trong JWT hoặc provider-specific identifier.
- `principal.username` chỉ đúng khi **kiểu principal có thuộc tính username**.
- `#username` là tham số method được Spring Security resolve trong SpEL, không phải giá trị được framework tự xác minh.
- User có đúng tên vẫn chưa được mặc nhiên đọc **bất kỳ bản ghi nào**: còn cần authority, owner, tenant và object policy.

**Thông điệp chính:** `authentication.name` thường hữu ích để so tên trong bài toán đơn giản, nhưng **không phải khóa phân quyền chung cho mọi resource hoặc mọi authentication mechanism**.

## 2. Bật method security và xác định thời điểm kiểm tra

Trong Spring Boot 3.x/Spring Security 6.x, khai báo:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Khi `@EnableMethodSecurity` hoạt động, Spring Security đăng ký method-security interceptors. Với `@PreAuthorize`, biểu thức được đánh giá **trước thân method** khi invocation đi qua Spring-managed proxy.

~~~text
Controller / scheduler / message listener
                |
                v
      Spring-managed service proxy
                |
                +--> @PreAuthorize
                |      |
                |      +--> Authentication hiện hành
                |      +--> Method arguments
                |      +--> Authorization expression
                |
            allow / deny
                |
                v
           Method body
~~~

Annotation không tự chạy nếu service được tạo bằng `new` thay vì Spring DI hoặc khi lời gọi bỏ qua Spring AOP advice. Trong proxy mode thông thường, `this.securedMethod()` là **self-invocation**, có thể bypass interceptor.

Một service có thể bị gọi từ HTTP, batch job hay event consumer. Rule HTTP `authorizeHttpRequests` và rule ở method là **hai tầng khác nhau**, không thay thế nhau. Với request HTTP, denial có thể được ánh xạ thành 401/403/redirect tùy authentication entry point và exception handling; không phải mọi `@PreAuthorize` false đều luôn trả một status giống nhau.

## 3. Nguồn của Authentication: SecurityContext

Trong Servlet stack thường gặp:

~~~text
SecurityContextHolder
    |
    v
SecurityContext
    |
    v
Authentication
    +--> getName()
    +--> getPrincipal()
    +--> getAuthorities()
    +--> getCredentials()
    +--> getDetails()
    +--> isAuthenticated()
~~~

`Authentication` có thể là dữ liệu đi vào `AuthenticationManager` khi đang xác thực hoặc là token đại diện cho người dùng đã được xác thực. Sau khi xác thực, Spring Security lưu nó trong `SecurityContext` thích hợp.

Để truy cập qua Java API:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

if (authentication != null) {
    String name = authentication.getName();
    Object principal = authentication.getPrincipal();
    var authorities = authentication.getAuthorities();
}
~~~

Đoạn trên cần dependency Spring Security và bối cảnh runtime; **không phải chương trình Java độc lập**.

Trong method-security SpEL, Spring Security cung cấp sẵn các security expression root fields và helpers:

~~~text
authentication              -> Authentication gắn với invocation
authentication.name         -> Authentication#getName()
authentication.principal    -> Authentication#getPrincipal()
principal                   -> Authentication#getPrincipal()
hasAuthority("document:read")-> Kiểm tra authority
hasRole("ADMIN")            -> Kiểm tra role với prefix mặc định ROLE_
isAuthenticated()          -> Helper của framework theo trust semantics
~~~

### 3.1. Authentication và principal không cùng một loại

Ví dụ username/password login:

~~~text
authentication:
  type        = UsernamePasswordAuthenticationToken
  name        = alice
  principal   = UserDetails(username=alice, ...)
  authorities = [ROLE_USER, profile:read]
~~~

`authentication` là **toàn token**; `principal` là **một trường của token**. Token còn có authorities và trạng thái xác thực. Không nên viết biểu thức so `#username == authentication` vì hai vế không cùng ý nghĩa.

## 4. authentication, principal, authentication.name, principal.username

| SpEL | Nghĩa | Ví dụ | Cần tránh |
|---|---|---|---|
| `authentication` | Object `Authentication` hiện hành | UsernamePasswordAuthenticationToken/JwtAuthenticationToken | Coi như String |
| `principal` | `authentication.getPrincipal()` | UserDetails/Jwt/OAuth2User/String | Giả định luôn UserDetails |
| `authentication.name` | `authentication.getName()` | `alice` hoặc `u-42` | Giả định là username/email |
| `authentication.principal` | Cùng object như `principal` | Một Jwt hoặc custom principal | Coi là ID đã chuẩn hóa |
| `principal.username` | Getter/property username **nếu tồn tại** | `UserDetails#getUsername()` | Dùng với String/Jwt |
| `authentication.authorities` | Tập GrantedAuthority | `ROLE_USER`, `SCOPE_read` | Tự so sánh sai prefix |
| `authentication.authenticated` | Token `isAuthenticated()` flag | Có thể true ở anonymous token | Coi là real login |
| `isAuthenticated()` | Expression helper theo Spring trust semantics | Nhận diện người đã xác thực phù hợp | Đánh đồng flag thô |

**Khác biệt cốt lõi:** `authentication.name` hỏi **token trả tên là gì**. `principal.username` hỏi **principal có thuộc tính username không**. Chúng có thể cùng giá trị trong form login nhưng không có contract chung giữa JWT, OAuth2 và anonymous.

### 4.1. UserDetails

Nếu principal là UserDetails, biểu thức sau thường hợp lệ:

~~~java
@PreAuthorize(
    "isAuthenticated() and #username == principal.username"
)
public String readOwnSettings(String username) {
    return "settings:" + username;
}
~~~

`principal.username` gọi property từ `UserDetails#getUsername()`. Tuy nhiên phải bảo đảm tham số `username` được discover đúng và method invocation chạy qua Spring proxy.

### 4.2. String hoặc Jwt

Trong một số luồng anonymous:

~~~text
principal = "anonymousUser"
~~~

String không có thuộc tính `username` theo contract UserDetails. Tương tự, principal `Jwt` có claims chứ không phải `getUsername()`.

Biểu thức `principal.username` trên loại principal không phù hợp **có thể gây lỗi SpEL property resolution** chứ không được bảo đảm trả false. SpEL null-safe operator không tự chuyển một String thành UserDetails.

Nếu ứng dụng có nhiều cơ chế xác thực, dùng `authentication.name` khi contract rõ ràng hoặc chuyển logic nhận diện sang một bean policy xử lý từng loại principal một cách fail closed.

## 5. Vì sao #username có dấu # còn authentication không có?

Ví dụ:

~~~java
@PreAuthorize("#username == authentication.name")
~~~

- `#username` là biến tham số method.
- `authentication` là property trên security expression root.
- `principal` cũng là root property.
- `hasAuthority('x')` là helper method của root.
- `authentication.name` truy cập property từ object Authentication.

Không mặc định đổi thành:

~~~java
@PreAuthorize("#username == #authentication.name")
~~~

và nghĩ `#authentication` là một biến tích hợp phổ quát. Theo tài liệu Spring Security, cú pháp chuẩn ở đây là **`authentication` không có `#`**.

### 5.1. Tên tham số phải được discover

Spring Security sử dụng `DefaultSecurityParameterNameDiscoverer`, với những nguồn tên như:

1. `@P("username")` của Spring Security.
2. `@Param` của Spring Data trong trường hợp hỗ trợ.
3. Metadata của Java compiler flag `-parameters`.
4. Debug symbols của concrete method trong những trường hợp phù hợp.

Ví dụ minh bạch:

~~~java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;

@PreAuthorize(
    "isAuthenticated() and #username == authentication.name"
)
public String selfProfile(@P("username") String username) {
    return "profile:" + username;
}
~~~

Trong một project đã bật `-parameters`, có thể không cần `@P`. Nhưng khi annotation nằm ở interface, debug local-variable metadata không cung cấp tên như concrete method, nên `@P` hoặc `-parameters` đặc biệt hữu ích.

Nếu build không giữ tên method parameters, SpEL có thể không resolve được `#username` và policy hoạt động sai. **Không bỏ điều kiện chỉ để test qua**; sửa parameter metadata và viết integration test.

## 6. Ví dụ Spring Service: hồ sơ của chính mình

Ví dụ đầy đủ trong lớp Spring-managed service:

~~~java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ProfileService {

    @PreAuthorize(
        "isAuthenticated() and #username == authentication.name"
    )
    public String selfProfile(@P("username") String username) {
        return "profile:" + username;
    }
}
~~~

Khi `authentication.name = "alice"`:

| Context | `#username` | Kết quả method pre-authorization |
|---|---|---|
| Alice đã login | `alice` | Cho phép |
| Alice đã login | `bob` | Từ chối |
| Bob đã login | `alice` | Từ chối |
| Anonymous | `anonymousUser` | Từ chối do `isAuthenticated()` |
| JWT name là `u-42` | `alice` | Không mặc nhiên khớp |
| Account bị thu hồi quyền nhưng token còn cũ | `alice` | Cần thêm kiểm tra freshness/revocation |

Lớp này chỉ trả chuỗi nhằm test concept; dữ liệu sản xuất cần truy vấn owner/tenant và quyền tương ứng.

### 6.1. Kết hợp permission

~~~java
@PreAuthorize(
    "hasAuthority('profile:read') and " +
    "isAuthenticated() and #username == authentication.name"
)
public ProfileDto readOwnProfile(@P("username") String username) {
    return repository.findByUsername(username);
}
~~~

Snippet phụ thuộc `ProfileDto` và repository có thật. Điều kiện yêu cầu **cả authority và username**. Nếu user có tên đúng nhưng thiếu `profile:read`, không được phép.

### 6.2. Nới quyền admin/support phải chủ đích

~~~java
@PreAuthorize(
    "hasAuthority('profile:read') and " +
    "(#username == authentication.name or hasRole('SUPPORT'))"
)
public ProfileDto readProfile(@P("username") String username) {
    return repository.findByUsername(username);
}
~~~

**Đây chỉ là minh họa:** một support user có thể được xem tất cả profiles nếu không có ràng buộc thêm. Trong hệ thống multi-tenant hoặc dữ liệu riêng tư, policy phải kiểm tra tenant, assignment, purpose và tài nguyên đích. Role SUPPORT không tự chứng minh được phép đọc PII của mọi khách hàng.

## 7. JWT: authentication.name có thể là sub

Spring Security OAuth2 Resource Server thường có luồng:

~~~text
Bearer token
  -> JwtDecoder + validators
  -> JwtAuthenticationConverter
  -> JwtAuthenticationToken
  -> SecurityContext
~~~

Ví dụ JWT đã được xác minh:

~~~json
{
  "iss": "https://id.example",
  "sub": "u-42",
  "preferred_username": "alice",
  "tenant": "tenant-7",
  "scope": "document:read"
}
~~~

Trong cấu hình mặc định thường gặp:

~~~text
authentication.name          = "u-42"
principal                    = Jwt
principal.claims['sub']      = "u-42"
principal.username           = không mặc định có
~~~

Người dùng có thể thấy tên `alice` trong UI nhưng `Authentication#getName()` là `u-42`. So `#username="alice"` với `authentication.name="u-42"` cho false.

`JwtAuthenticationConverter` có thể cấu hình principal claim khác, nên không khẳng định mọi ứng dụng JWT đều trả name=sub. Điều đúng là **phải xác minh converter và contract của từng authentication mechanism**.

### 7.1. Claim-based expression chỉ đúng khi biết type

Nếu biết chắc principal là Jwt đã được xác minh, ví dụ:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_document:read') " +
    "and principal.claims['sub'] == #subject"
)
public String readForSubject(@P("subject") String subject) {
    return "subject:" + subject;
}
~~~

Đây là snippet **phụ thuộc JWT Resource Server**; authority `SCOPE_document:read` chỉ đúng khi converter áp dụng mapping đó. Token cần kiểm chữ ký, issuer, audience, thời gian, thuật toán và các claim quan trọng theo kiến trúc. So sub với parameter chưa chứng minh user có quyền trên **tài liệu cụ thể**.

### 7.2. Định danh sub cần gắn với issuer

~~~text
(issuer A, sub=u-42)  !=  (issuer B, sub=u-42)
~~~

Hai providers có thể cấp cùng subject string cho những users khác nhau. Với multi-IdP, nên map issuer + subject sang một **internal user ID ổn định** trước khi áp business authorization.

Không lấy email hay preferred_username làm owner key chung nếu chúng có thể bị đổi, không unique hoặc chưa verified.

## 8. OAuth2 Login và OIDC

Với OAuth2 Login, principal thường là `OAuth2User` và trong OIDC có thể là `OidcUser`. Tên và attributes phụ thuộc nhà cung cấp:

~~~text
authentication.name
principal.name
principal.attributes
principal.claims     (tùy principal OIDC/JWT)
~~~

Không được giả định mọi OAuth2 principal đều có `username` hoặc `email`. Nếu so:

~~~java
@PreAuthorize("principal.attributes['email'] == #email")
~~~

để quyết định owner, phải cân nhắc email có verified không, có thể đổi không, trùng tài khoản/provider không. **Provider attribute không tự mang quyền trên dữ liệu ứng dụng**.

Giải pháp tốt là ánh xạ danh tính IdP đã xác thực về ID nội bộ và tenant memberships đáng tin, sau đó kiểm service policy bằng dữ liệu server.

## 9. Anonymous và remember-me không giống authenticated thực

Một `AnonymousAuthenticationToken` có thể có `isAuthenticated()==true` dù nó đại diện anonymous user. Vì vậy:

~~~java
authentication.isAuthenticated()
~~~

không nên được dùng **một mình** để nhận diện real login.

Các helper method-security expression như:

~~~java
@PreAuthorize("isAuthenticated()")
@PreAuthorize("isFullyAuthenticated()")
~~~

có semantics theo trust resolver của Spring Security, khác cờ thô của token.

| Expression/field | Tác dụng | Ghi nhớ |
|---|---|---|
| `authentication.authenticated` | Flag token | Có thể true với anonymous |
| `isAuthenticated()` | Người gọi được framework xem là authenticated | Không đồng nhất flag |
| `isAnonymous()` | Anonymous principal | Không phải user account |
| `isRememberMe()` | Remember-me context | Mức tin cậy thấp hơn full login |
| `isFullyAuthenticated()` | Full authentication, không chỉ remember-me | Có thể cần thêm MFA/step-up |

Không dùng string `anonymousUser` làm owner ID. Client có thể gửi path `/profiles/anonymousUser` nhưng đó **không** tạo nên danh tính đáng tin.

### 9.1. Account status và token/session freshness

Nếu một user bị khóa sau khi session/token đã được phát hành, `authentication.name` có thể không đổi. Độ mới của quyền, token expiry, revocation, account-status checks và cache invalidation phải được thiết kế theo mức độ nhạy cảm của action.

**Name trùng không chứng minh quyền vẫn còn hiệu lực.**

## 10. Custom principal và immutable user ID

Một ứng dụng có thể chuẩn hóa principal:

~~~java
public final class CurrentUser {
    private final String userId;
    private final String tenantId;
    private final String username;

    public CurrentUser(String userId, String tenantId, String username) {
        this.userId = userId;
        this.tenantId = tenantId;
        this.username = username;
    }

    public String getUserId() { return userId; }
    public String getTenantId() { return tenantId; }
    public String getUsername() { return username; }
}
~~~

Khi principal thật là `CurrentUser`, SpEL có thể đọc `principal.userId`, `principal.tenantId`, `principal.username`. Nhưng khai báo class này **không tự làm JWT/OAuth2User chuyển thành CurrentUser**; cần authentication provider/converter hoặc identity mapping rõ ràng.

Một biểu thức minh họa:

~~~java
@PreAuthorize(
    "isAuthenticated() and #userId == principal.userId"
)
public ProfileDto readProfile(@P("userId") String userId) {
    return repository.findByUserId(userId);
}
~~~

Điều này tốt hơn so username nếu ID là stable, principal được thiết lập từ nguồn xác thực đáng tin và method được gọi với đúng loại principal. Vẫn cần tenant/resource constraints khi truy cập data thật.

**Không tạo CurrentUser dựa trên `X-User-Id` hoặc `tenantId` do client tự khai mà chưa xác thực nguồn.**

## 11. Khi nào so username là không đủ?

Username/email là metadata có thể đổi hoặc tái sử dụng.

~~~text
Tháng 1: Alice username=alice,        internal userId=u-42
Tháng 4: Alice username=alice.nguyen, internal userId=u-42
Tháng 5: User khác lấy username=alice, internal userId=u-99
~~~

Nếu lưu owner bằng username, permission có thể bị ghép sai khi rename/reuse. Resource nên có stable owner ID và tenant ID:

~~~text
userId           = u-42
username         = alice.nguyen
verified subject = (issuer, sub)
tenant membership= dữ liệu server
document.ownerId = u-42
document.tenantId= tenant-7
~~~

Một API có đường `GET /users/u-42/documents/100` không được quyền chỉ vì user nhập đúng `u-42` vào path. Server cần lấy identity thực từ authentication, lấy tài liệu thật từ repository và kiểm owner/tenant/authority.

### 11.1. Authorization theo action và resource

Cho phép `document:read` không mặc nhiên cho phép `document:export`, `document:delete` hay `document:approve`. Mỗi action cần permission tương ứng, và object policy có thể xét trạng thái, owner, tenant, sharing, assignment hoặc mục đích xử lý.

## 12. Bean policy: chuyển Authentication vào logic kiểm tài nguyên

Thay vì nhồi kiểm tenant, owner và principal types vào SpEL:

~~~java
@PreAuthorize(
    "hasAuthority('document:read') and " +
    "@documentPolicy.canRead(authentication, #documentId)"
)
public DocumentDto readDocument(@P("documentId") long documentId) {
    return documentRepository.getDto(documentId);
}
~~~

Ở đây:

- `authentication` là object đầy đủ.
- `#documentId` là tham số được đặt tên bằng `@P`.
- `hasAuthority('document:read')` kiểm quyền chức năng.
- `@documentPolicy` là Spring bean dùng làm security decision.
- `canRead(...)` kiểm resource và identity trong code test được.

Ví dụ implementation minh họa:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {
    private final DocumentRepository repository;

    public DocumentPolicy(DocumentRepository repository) {
        this.repository = repository;
    }

    public boolean canRead(Authentication authentication, long documentId) {
        if (authentication == null || !authentication.isAuthenticated()) {
            return false;
        }

        Object principal = authentication.getPrincipal();
        if (!(principal instanceof CurrentUser user)) {
            return false;
        }

        return repository.existsReadableByOwnerAndTenant(
                documentId, user.getUserId(), user.getTenantId());
    }
}
~~~

Đây là **snippet phụ thuộc CurrentUser, DocumentRepository và dữ liệu ứng dụng**, không phải Java độc lập. Do `authentication.isAuthenticated()` có thể true với anonymous token, việc từ chối kiểu principal không hỗ trợ trong ví dụ là quan trọng; trong ứng dụng đa cơ chế cần thêm `AuthenticationTrustResolver` hoặc identity resolver để phân biệt trạng thái.

`existsReadableByOwnerAndTenant` đại diện cho query scoped theo owner và tenant. Chính sách thật có thể có users được chia sẻ quyền, organization memberships và trạng thái tài liệu.

### 12.1. Tránh time-of-check/time-of-use với write

Với xóa/phê duyệt tài liệu, chỉ check owner trước rồi thực hiện write ngoài transaction có thể bị race nếu trạng thái thay đổi. Cân nhắc transaction, locking, version check hoặc conditional update. Không thay `@PreAuthorize` bằng `@PostAuthorize` trên write có side effects, vì post-check xảy ra sau method body.

## 13. Chuẩn hóa identity khi có nhiều login flows

~~~text
Form login -> UserDetails ---------+
                                    |
JWT        -> Jwt ------------------+--> IdentityResolver
                                    |         |
OAuth2     -> OAuth2User -----------+         v
                                           InternalIdentity
                                          (userId,tenantId)
                                                |
                                                v
                                         Resource policy
~~~

Có hai cách:

1. Mỗi authentication provider/converter tạo cùng custom principal sau xác thực.
2. Giữ native principal nhưng `IdentityResolver` biết chuyển từ từng kiểu đã tin cậy sang internal identity.

Interface minh họa:

~~~java
public interface IdentityResolver {
    InternalIdentity requireIdentity(Authentication authentication);
}
~~~

Các loại token không hỗ trợ phải bị từ chối, không được coi anonymous hoặc String lạ là người dùng hợp lệ. Không đưa raw credentials/JWT vào log hay business identity DTO nếu không cần.

### 13.1. Authority namespace

JWT scope có thể được map thành `SCOPE_document:read`, role thành `ROLE_USER`, còn business permission thành `document:read`:

~~~text
ROLE_USER             : vai trò
SCOPE_document:read   : JWT scope theo converter phổ biến
document:read         : authority nghiệp vụ riêng
~~~

`hasAuthority('document:read')` và `hasAuthority('SCOPE_document:read')` không tự tương đương. Test converter production và policy đúng namespace.

## 14. @AuthenticationPrincipal trong controller khác gì principal trong SpEL?

Spring MVC hỗ trợ inject principal:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {
    @GetMapping("/whoami")
    public String whoami(@AuthenticationPrincipal Object principal) {
        return principal == null
                ? "unknown"
                : principal.getClass().getSimpleName();
    }
}
~~~

Đây là controller snippet trong Spring MVC, không phải Java thuần. Nếu principal thực là Jwt, không nên inject vào một parameter `UserDetails` rồi giả định binding thành công.

| Vị trí | Cách sử dụng |
|---|---|
| `@PreAuthorize` | Root properties `authentication` và `principal` |
| Spring MVC controller | `@AuthenticationPrincipal` hoặc `Authentication` |
| Service Java code | `SecurityContextHolder.getContext().getAuthentication()` |
| Policy bean | `@documentPolicy.canRead(authentication, #id)` |

Spring Security còn có `@CurrentSecurityContext` để lấy context hoặc một property từ context trong những nơi hỗ trợ. Trong `@PreAuthorize` đã có `authentication` nên thường không cần truyền từ controller xuống chỉ để so tên.

## 15. Async và scheduled method calls

Mặc định ở Servlet stack, `SecurityContextHolder` dùng ThreadLocal. Khi chuyển từ HTTP request thread sang executor:

~~~text
Request thread: Authentication của Alice
       |
       +--> submit async task
                    |
                    v
               Worker thread
               Không mặc định có cùng context
~~~

Nếu method bảo vệ bằng `@PreAuthorize("authentication.name == #username")` được gọi từ task không có SecurityContext, nó có thể bị từ chối hoặc đánh giá không đúng dự định.

Spring Security có các concurrency wrappers như `DelegatingSecurityContextExecutor`/`DelegatingSecurityContextRunnable` để truyền context đúng cách. Với scheduled jobs không có end-user, tạo **service identity và permissions riêng** hoặc một execution policy được kiểm soát. Không đặt một SecurityContext global chung cho mọi threads/users.

Quan trọng: context đã truyền phải được cleanup sau khi task hoàn tất để không rò identity giữa các tasks được chạy lại trên thread pool.

## 16. Java 17 độc lập: tên token khác stable subject

Chương trình sau sử dụng **Java thuần** để mô phỏng hai loại principal và anonymous token. Nó không dùng Spring Security, không xác minh JWT và không thay thế authentication provider. Mục tiêu là nhìn thấy `name` và `stable subject` có thể khác.

Tạo file `AuthenticationReferenceDemo.java`:

~~~java
import java.util.Map;
import java.util.Set;

public class AuthenticationReferenceDemo {
    record UserProfile(String username, String userId) {}
    record JwtLike(String subject, Map<String, String> claims) {}
    record AuthenticationView(
            Object principal, String name, Set<String> authorities,
            boolean authenticatedFlag, boolean anonymous) {}

    static boolean mayUseSelfProfile(AuthenticationView auth, String username) {
        return !auth.anonymous() && auth.authenticatedFlag()
                && auth.name().equals(username);
    }

    static String stableId(AuthenticationView auth) {
        if (auth.anonymous() || !auth.authenticatedFlag()) {
            return null;
        }
        if (auth.principal() instanceof UserProfile user) {
            return user.userId();
        }
        if (auth.principal() instanceof JwtLike jwt) {
            return jwt.subject();
        }
        return null;
    }

    static boolean canReadOwned(AuthenticationView auth, String ownerUserId) {
        String subject = stableId(auth);
        return subject != null
                && auth.authorities().contains("document:read")
                && subject.equals(ownerUserId);
    }

    public static void main(String[] args) {
        var password = new AuthenticationView(
                new UserProfile("alice", "u-42"),
                "alice", Set.of("document:read"), true, false);
        var jwt = new AuthenticationView(
                new JwtLike("u-42", Map.of("sub", "u-42")),
                "u-42", Set.of("document:read"), true, false);
        var anonymous = new AuthenticationView(
                "anonymousUser", "anonymousUser", Set.of(), true, true);

        System.out.println("password authentication.name: " + password.name());
        System.out.println("password principal.username: "
                + ((UserProfile) password.principal()).username());
        System.out.println("jwt authentication.name: " + jwt.name());
        System.out.println("jwt principal has username: "
                + (jwt.principal() instanceof UserProfile));
        System.out.println("same authentication.name: "
                + password.name().equals(jwt.name()));
        System.out.println("same stable subject: "
                + stableId(password).equals(stableId(jwt)));
        System.out.println("password self alice: "
                + mayUseSelfProfile(password, "alice"));
        System.out.println("password self bob: "
                + mayUseSelfProfile(password, "bob"));
        System.out.println("JWT can read own document: "
                + canReadOwned(jwt, "u-42"));
        System.out.println("JWT can read another document: "
                + canReadOwned(jwt, "u-99"));
        System.out.println("anonymous authenticated flag: "
                + anonymous.authenticatedFlag());
        System.out.println("anonymous accepted as user: "
                + mayUseSelfProfile(anonymous, "anonymousUser"));
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac --release 17 AuthenticationReferenceDemo.java
java AuthenticationReferenceDemo
~~~

Output chính xác đã kiểm tra:

~~~text
password authentication.name: alice
password principal.username: alice
jwt authentication.name: u-42
jwt principal has username: false
same authentication.name: false
same stable subject: true
password self alice: true
password self bob: false
JWT can read own document: true
JWT can read another document: false
anonymous authenticated flag: true
anonymous accepted as user: false
~~~

Diễn giải:

- Password principal có username `alice`, name cũng là `alice`.
- JWT-like principal không có kiểu UserProfile/username; name lấy theo subject `u-42` trong mô phỏng.
- Hai name khác nhau nhưng có cùng stable subject do demo cố ý map chúng vào một ID.
- Self-profile check từ chối Bob.
- Quyền đọc document còn cần permission và owner ID trùng.
- Anonymous có flag true nhưng không được đối xử như real user.

Mô phỏng **không bảo đảm mọi JWT có stable subject cùng namespace**. Production cần kiểm issuer + subject, chữ ký, audience, expiry và identity mapping trước khi tin token.

## 17. Integration test với @WithMockUser

Giả sử đã có `ProfileService` ở phần 6 và `@EnableMethodSecurity`.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class ProfileMethodSecurityTest {

    @Autowired
    ProfileService profiles;

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void aliceCanReadAlice() {
        assertEquals("profile:alice", profiles.selfProfile("alice"));
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void aliceCannotReadBob() {
        assertThrows(AccessDeniedException.class,
                () -> profiles.selfProfile("bob"));
    }

    @Test
    @WithMockUser(username = "bob", roles = "USER")
    void bobCannotReadAlice() {
        assertThrows(AccessDeniedException.class,
                () -> profiles.selfProfile("alice"));
    }
}
~~~

**Đây là test class trong dự án có Spring Boot, Spring Security Test và bean thật**, không chạy bằng một lệnh `javac`. Test phải inject Spring-managed proxy để annotation được evaluate.

### 17.1. Test @WithMockUser không đủ cho production JWT

`@WithMockUser` thường thiết lập principal kiểu UserDetails và name là username do test đưa vào. Nếu production JWT name là `sub`, test `@WithMockUser(username="alice")` có thể pass nhưng real JWT user bị deny khi expression so với `alice`.

Cần thêm JWT resource server test với claims, authorities, issuer/subject và converter phản ánh production. Test rằng principal có đúng type và policy chuyển sang stable identity thành công.

### 17.2. Negative tests là phần quan trọng nhất

| Case | Kết quả kỳ vọng |
|---|---|
| Alice xem Alice bằng username contract hợp lệ | Allow |
| Alice xem Bob | Deny |
| Bob xem Alice | Deny |
| Anonymous gửi `anonymousUser` | Deny |
| User không có `document:read` | Deny |
| User có authority nhưng khác owner | Deny |
| User có authority nhưng khác tenant | Deny |
| JWT name=sub, argument=username | Không giả định bằng nhau |
| Principal là Jwt, expression đòi `principal.username` | Phát hiện type mismatch, đổi policy |
| OAuth2 provider A/B dùng name khác | Có identity mapping |
| Token revoked/account disabled | Deny theo policy freshness |
| Thiếu `@P` và `-parameters` | Test detect parameter name issue |
| Service gọi qua `this.securedMethod()` | Test detect proxy bypass |
| Async task không có context | Deny hoặc service identity đúng |

Test resource với hai users, hai tenants và documents khác owner để phát hiện BOLA/IDOR. Một `404` do không tồn tại controller **không chứng minh** security đã chặn; với method security hãy gọi service bean thật.

## 18. Lỗi phổ biến

| Lỗi | Nguy cơ | Sửa |
|---|---|---|
| Coi `authentication` là String | So sánh sai type | Dùng `authentication.name` |
| Coi `principal` luôn UserDetails | JWT/OAuth2/String có kiểu khác | Biết principal runtime type |
| Dùng `principal.username` cho mọi flow | Property không tồn tại | Chuẩn hóa identity/policy bean |
| `authentication.name` bị coi là email | Có thể là `sub`/provider ID | Kiểm converter contract |
| Không có dấu `#` trước tham số | SpEL không lấy argument | `#username` |
| Dùng `#authentication` theo thói quen | Sai root property mặc định | `authentication` |
| Thiếu `@P`/`-parameters` | Không resolve parameter names | Cấu hình build/test |
| Đọc `authentication.authenticated` như “real login” | Anonymous có thể true | Trust-aware helper |
| Chỉ so username để đọc data | Bỏ qua owner/tenant | Stable ID + object policy |
| Tin tenantId/header client | Tenant spoof | Verified identity/server data |
| Email/display name làm owner key | Rename/reuse gây nhầm | Immutable user ID |
| Nhầm `SCOPE_document:read` với `document:read` | Authorization không như dự kiến | Authority mapping |
| Chỉ dùng `@WithMockUser` | Không test JWT principal type | JWT/OAuth2 integration test |
| Gọi `new Service()` hoặc `this.method()` | Bỏ qua AOP proxy | Spring DI/tách bean |
| Dùng `@PostAuthorize` cho write | Body chạy trước denial | `@PreAuthorize`/transaction guard |
| Async thread không có context | Thiếu/wrong authentication | Propagation và cleanup |
| Ghi log raw Authentication/JWT | Lộ credential/PII | Log tối thiểu và mask |

## 19. Checklist trước khi merge

- [ ] Đã bật `@EnableMethodSecurity` và gọi đúng Spring bean/proxy.
- [ ] Đã xác định kiểu Authentication và principal cho mọi login flow.
- [ ] Phân biệt `authentication`, `principal`, `authentication.name`, `principal.username`.
- [ ] Dùng `#argument` đúng và giữ tên bằng `@P`/`-parameters`.
- [ ] Không dùng token flag thô làm bằng chứng user thật.
- [ ] Không dùng username/email dễ đổi làm owner key.
- [ ] JWT issuer+subject được xác minh, mapping tới internal user ID.
- [ ] Authority prefixes `ROLE_`/`SCOPE_`/business permissions nhất quán.
- [ ] Object authorization kiểm resource owner, tenant, action và context.
- [ ] Không tin path/query/header làm chứng cứ quyền.
- [ ] Test Alice/Bob, anonymous, cross-tenant, thiếu permission và account revoked.
- [ ] Test JWT/OAuth2 runtime chứ không chỉ mock username.
- [ ] Không có proxy bypass qua self-invocation/new/final/private methods.
- [ ] Async/scheduler có service identity và SecurityContext lifecycle rõ.
- [ ] Không log secrets, raw JWT hoặc credentials.

**Ghi nhớ:** *Dùng `authentication.name` chỉ khi biết chắc nó đại diện loại tên nào; dùng `principal.username` chỉ khi principal thực có property đó; quyền trên tài nguyên phải dựa vào danh tính đã xác minh và dữ liệu server.*

## 20. Câu hỏi tự kiểm tra

**1. `authentication` là gì?**  
Là đối tượng `Authentication`, không phải một username String.

**2. `principal` là gì?**  
Là `Authentication#getPrincipal()`.

**3. `authentication.name` lấy ở đâu?**  
Từ `Authentication#getName()`.

**4. `principal.username` luôn tồn tại?**  
Không; chỉ khi principal có property username.

**5. Vì sao `#username` có dấu #, `authentication` không có?**  
Tham số method là SpEL variable, authentication là root property.

**6. JWT có `sub=u-42`, `preferred_username=alice`, so `authentication.name` với `alice` có chắc true không?**  
Không, name có thể là sub theo converter.

**7. Anonymous token có `isAuthenticated()==true` thì có phải real user không?**  
Không. Dùng trust-aware method-security expression/helper.

**8. Có `document:read` thì đọc được mọi tài liệu cùng hệ thống?**  
Không; còn owner, tenant, resource-specific policy.

**9. Vì sao @WithMockUser test pass nhưng JWT production fail?**  
Mock user có thể dùng UserDetails/username, JWT có principal Jwt/name là subject.

**10. Tại sao nên dùng stable internal user ID?**  
Username/email có thể đổi, bị tái sử dụng và không unique xuyên providers/tenants.

**11. Khi nào dùng `@documentPolicy.canRead(authentication,#id)`?**  
Khi cần mapping principal, authority, tenant/owner và object rules phức tạp.

**12. `this.securedMethod()` có chắc đánh giá @PreAuthorize không?**  
Không trong proxy mode thông thường; self-invocation có thể bỏ qua advice.

## 21. Tài liệu chính thức

- Spring Security – **Method Security**, phần *Expressing Authorization with SpEL* và *Using Method Parameters*: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security – **Servlet Authentication Architecture**: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security – **Authorization Architecture**: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security – **Anonymous Authentication**: https://docs.spring.io/spring-security/reference/servlet/authentication/anonymous.html
- Spring Security – **OAuth2 Resource Server JWT**: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security – **Authentication JavaDoc**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/Authentication.html
- Spring Security – **Method Security Testing**: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Framework – **Proxying Mechanisms**: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
