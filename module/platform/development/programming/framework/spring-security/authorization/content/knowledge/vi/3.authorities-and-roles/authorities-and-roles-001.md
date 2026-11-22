# Authentication, principal và tập GrantedAuthority được dùng khi kiểm tra quyền

> **Module:** Spring Security - authorization  
> **Nhóm kiến thức:** Authority và role  
> **Đích học tập:** Hiểu cách Spring Security mang danh tính đã xác thực và các quyền tổng quát vào một quyết định authorization; phân biệt `Authentication`, `principal`, `GrantedAuthority`, `role` và `scope`; biết cách đọc, dùng, kiểm thử và xử lý các trường hợp dễ gây vượt quyền.

## 1. Khi hệ thống kiểm tra quyền, nó đang đọc thông tin gì?

Giả sử Alice đăng nhập thành công, được gắn các authority:

```text
principal = alice
authorities = [
  "ROLE_EDITOR",
  "document:read",
  "document:edit"
]
```

Alice gửi `GET /api/documents/42`. Bộ kiểm tra `hasAuthority("document:read")` có thể cho qua ở tầng HTTP vì trong tập authority của Alice có chính xác chuỗi `document:read`. Nếu Alice gửi `DELETE /api/documents/42` mà ứng dụng yêu cầu `document:delete`, phép kiểm tra tương ứng sẽ từ chối nếu authority đó không có.

Thế còn Alice có được sửa **tài liệu số 42** không? `document:edit` chỉ chứng minh quyền chức năng tổng quát; nếu tài liệu thuộc tenant khác, được khóa hoặc Alice không phải owner/editor được phân công, vẫn phải từ chối theo policy nghiệp vụ. Đó là lý do cần tách ba câu hỏi:

1. **Authentication:** người gọi là ai và đã xác thực bằng cơ chế tin cậy chưa?
2. **Authority/role:** các quyền tổng quát nào đã được hệ thống cấp cho danh tính đó?
3. **Resource authorization:** với tài nguyên và ngữ cảnh cụ thể, luật nghiệp vụ có cho thực hiện hành động này không?

Trong Spring Security, đối tượng trung tâm nối câu hỏi 1 và 2 với bước quyết định quyền là `Authentication`. Nó chứa principal và tập `GrantedAuthority`; nhiều `AuthorizationManager` đọc các authority này để quyết định.

## 2. Năm khái niệm không nên nhầm lẫn

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| `SecurityContextHolder` | Điểm truy cập vào ngữ cảnh bảo mật hiện tại trong ứng dụng Servlet | Lấy `SecurityContext` của luồng đang xử lý |
| `SecurityContext` | Chứa `Authentication` hiện tại | `context.getAuthentication()` |
| `Authentication` | Biểu diễn yêu cầu xác thực hoặc danh tính hiện đã xác thực | `UsernamePasswordAuthenticationToken`, `JwtAuthenticationToken` |
| `principal` | Thực thể nhận dạng người gọi, là một thuộc tính bên trong `Authentication` | `UserDetails`, `Jwt`, `OidcUser`, custom principal |
| `GrantedAuthority` | Một quyền/role/scope được cấp cho principal | `ROLE_ADMIN`, `document:read`, `SCOPE_files.read` |

`Authentication` là một interface mở rộng `java.security.Principal` và cung cấp những method quan trọng như `getName()`, `getPrincipal()`, `getCredentials()`, `getDetails()`, `getAuthorities()`, `isAuthenticated()`. **`getPrincipal()` trả về `Object`**, không đảm bảo luôn là `String` hay `UserDetails`.

Một cách hình dung:

```text
SecurityContextHolder
  └── SecurityContext
       └── Authentication
            ├── principal: danh tính
            ├── authorities: Collection<? extends GrantedAuthority>
            ├── credentials: bằng chứng xác thực; thường được xóa khi đã xác thực
            ├── details: metadata tùy cơ chế
            └── authenticated: trạng thái theo loại Authentication

AuthorizationManager
  ├── đọc Authentication, khi quy tắc cần danh tính/quyền
  ├── đối chiếu authority/role hoặc chạy policy tùy biến
  └── ALLOW / DENY theo loại quyết định của phiên bản sử dụng
```

**Điều cần nhớ:** principal trả lời “là ai”, authority trả lời “được cấp những quyền tổng quát nào”. Cả hai đều là **dữ liệu đầu vào** của authorization; chúng chưa tự quyết định quyền trên từng đối tượng nghiệp vụ.

## 3. Authentication có hai vòng đời: chưa xác thực và đã xác thực

`Authentication` có thể được sử dụng ở hai thời điểm khác nhau:

**Trước xác thực:** bộ lọc đọc credential từ request và tạo một `Authentication` yêu cầu xác thực. Ví dụ, token chứa tên đăng nhập + mật khẩu, trạng thái thường là chưa xác thực. Nó được đưa cho `AuthenticationManager`, thường được hiện thực bằng `ProviderManager` phối hợp với một hoặc nhiều `AuthenticationProvider`.

**Sau xác thực:** provider kiểm tra bằng chứng, xác định principal và authorities đáng tin, rồi trả về `Authentication` đại diện cho danh tính đã xác thực. Tùy cơ chế, nó được lưu vào `SecurityContext` để các bộ chặn authorization sử dụng trong request hiện tại. Với session, context có thể được tải/lưu qua `SecurityContextRepository`. Với bearer token, quá trình xác thực token thường diễn ra theo từng request.

```text
HTTP request
   |
   v
Authentication filter
   |
   | credentials/token từ request
   v
AuthenticationManager / AuthenticationProvider
   |
   | xác minh credential/token và nạp quyền từ nguồn tin cậy
   v
Authentication đã xác thực
   |
   v
SecurityContext
   |
   v
Authorization filter / method interceptor
   |
   | dùng getAuthorities(), getName(), principal, tài nguyên...
   v
ALLOW hoặc DENY
```

Ví dụ thực tế: user có `ROLE_ADMIN` trong database không có nghĩa client được tự gửi header `X-Role: ADMIN` để có authority. Provider hoặc converter do server tin cậy phải kiểm tra nguồn, ánh xạ và cấp authority vào `Authentication`.

**Không tự đặt `isAuthenticated=true`** cho dữ liệu request chưa qua xác thực. Giá trị này là một trạng thái bên trong token, không phải bằng chứng mật mã hay bảo đảm rằng quyền đến từ nguồn đáng tin. Việc phát hành token đã xác thực phải thuộc hạ tầng authentication hợp lệ.

## 4. Bên trong Authentication: field nào dùng để làm gì?

| Thành phần | Chức năng | Lưu ý khi authorization |
| --- | --- | --- |
| `getPrincipal()` | Trả đối tượng principal | Có thể là `UserDetails`, `Jwt`, principal OIDC hoặc loại tùy biến; cần xác định kiểu trước khi ép |
| `getName()` | Trả tên định danh theo implementation | Có thể là username hoặc claim `sub`; không mặc định là ID DB/tenant |
| `getAuthorities()` | Trả tập quyền tổng quát dưới dạng collection | Kiểm tra chuỗi authority đúng giá trị hoặc dùng manager/policy phù hợp |
| `getCredentials()` | Bằng chứng xác thực, chẳng hạn password/token | Không dùng như nguồn cấp quyền, không ghi log; có thể đã bị xóa sau xác thực |
| `getDetails()` | Metadata liên quan quy trình xác thực | Có thể gồm địa chỉ IP, session ID tùy cơ chế; không mặc định là dữ kiện đáng tin cho domain policy |
| `isAuthenticated()` | Trạng thái của token theo implementation | **Không đủ** để xác định request là user thật thay vì anonymous |
| `getName()` qua `Principal` | Tên đại diện danh tính | Không phải mô hình phân quyền hay ACL |

Ví dụ Servlet sau đây **chỉ minh họa cách đọc** trong code chạy dưới Spring Security; cần bảo vệ endpoint trước khi truy cập. Không phải file Java độc lập:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;

import java.util.List;
import java.util.Objects;

class CurrentAuthenticationView {
    static void inspectCurrentAuthentication() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null) {
            return; // Chưa có Authentication trong context này.
        }

        String name = authentication.getName();
        Object principal = authentication.getPrincipal();
        List<String> authorities = authentication.getAuthorities()
            .stream()
            .map(GrantedAuthority::getAuthority)
            .filter(Objects::nonNull)
            .sorted()
            .toList();

        // Sử dụng trong xử lý nội bộ có kiểm soát.
        // Không ghi credentials/token hay toàn bộ principal vào log.
    }
}
```

`SecurityContextHolder` dùng `ThreadLocal` theo chiến lược mặc định trên Servlet. Spring Security cung cấp cơ chế thiết lập và dọn context trong filter chain. Không giữ tham chiếu `Authentication` trong biến `static` dùng chung cho nhiều request và không tin rằng một task chạy ở thread khác tự có context chính xác.

## 5. Principal không phải lúc nào cũng là username

Kiểu principal thay đổi theo cách ứng dụng xác thực:

| Cơ chế xác thực | Principal thường gặp | Điều nên biết |
| --- | --- | --- |
| Form login / username-password | `UserDetails` hoặc custom principal | Có thể đọc `getUsername()`, định danh nội bộ từ loại custom |
| HTTP Basic với `UserDetailsService` | Thường là `UserDetails` | Có thể là đối tượng từ service hoặc wrapper khác tùy cấu hình |
| OAuth2 Resource Server JWT | Thường là `Jwt` trong `JwtAuthenticationToken` | `getName()` thường lấy claim `sub` theo converter mặc định |
| OAuth2 Login / OIDC | `OAuth2User` / `OidcUser` | Có attributes/claims; kiểu và name mapping tùy provider |
| Anonymous authentication | `anonymousUser` hoặc giá trị được cấu hình | Không đại diện cho danh tính đăng nhập thật |
| Hệ thống custom | Principal do ứng dụng thiết kế | Định nghĩa contract ổn định và kiểm tra ở adapter |

Trong Spring MVC có thể lấy principal thuận tiện bằng `@AuthenticationPrincipal`:

```java
// Chỉ hợp lý khi cơ chế xác thực thực sự dùng UserDetails.
@GetMapping("/api/my-username")
public String myUsername(@AuthenticationPrincipal UserDetails user) {
    return user.getUsername();
}
```

Với resource server JWT, tham số `UserDetails` như trên thường không phù hợp; sử dụng kiểu `Jwt` nếu đã xác nhận converter:

```java
// Snippet MVC với bearer JWT, dùng khi principal thật sự là Jwt.
@GetMapping("/api/my-subject")
public String mySubject(@AuthenticationPrincipal Jwt jwt) {
    return jwt.getSubject();
}
```

Các snippet là các method của controller với import/bean tương ứng, **không phải** chương trình Java độc lập để chạy bằng `javac`. Trong controller có thể nhận `Authentication` trực tiếp hoặc dùng `@CurrentSecurityContext` khi cần toàn context. Đừng ép `(UserDetails) authentication.getPrincipal()` ở mọi nơi; JWT/OIDC/anonymous có thể gây `ClassCastException`.

### Định danh nghiệp vụ nên được chuẩn hóa

`authentication.getName()` thường hữu ích để biểu diễn subject, nhưng ứng dụng nhiều tenant cần quy định rõ:
- Subject ID là định danh bất biến/ổn định thuộc issuer nào?
- Nếu có hai identity provider cùng phát `sub="123"` thì có bị trùng không? Khi cần, khóa định danh gồm issuer + subject.
- Người dùng có thể đổi email/username không? Nếu có, không dùng email hiển thị làm khóa quyền lâu dài.
- Tenant đang được truy cập có thực sự thuộc danh tính đó không?
- User có tài khoản cá nhân nhưng đang thay mặt tổ chức thì ngữ cảnh tổ chức được xác minh ở đâu?

Một adapter như `AuthenticatedActorResolver` có thể biến `Authentication` đã xác thực thành `Actor(userId, tenantId, memberships)` đáng tin. Policy nghiệp vụ nhận `Actor` thay vì gắn trực tiếp tất cả logic vào cấu trúc JWT/UserDetails.

## 6. GrantedAuthority hoạt động như thế nào?

Interface `GrantedAuthority` có một method chính:

```java
public interface GrantedAuthority extends java.io.Serializable {
    String getAuthority();
}
```

Dạng hay gặp nhất là `SimpleGrantedAuthority`, chứa một chuỗi như `ROLE_EDITOR` hoặc `document:read`. Bộ kiểm tra `hasAuthority("document:read")` cần một `GrantedAuthority#getAuthority()` bằng đúng chuỗi đó; nó không tự suy ra từ tên role và không tự phân tích quan hệ owner/tenant.

Có loại `GrantedAuthority` phức tạp mà `getAuthority()` trả `null` vì không thể biểu diễn gọn bằng một chuỗi. Khi ấy các manager dựa trên chuỗi thông thường không hiểu quyền phức tạp này; cần một `AuthorizationManager` tùy biến biết xử lý kiểu authority đó.

Ví dụ giả sử một `Authentication` có đúng ba authority:

```text
ROLE_EDITOR
document:read
SCOPE_documents.write
```

| Kiểm tra | Kết quả thông thường | Lý do |
| --- | --- | --- |
| `hasAuthority("ROLE_EDITOR")` | ALLOW | Khớp chuỗi authority |
| `hasRole("EDITOR")` | ALLOW | Mặc định tìm `ROLE_EDITOR` |
| `hasAuthority("EDITOR")` | DENY | Không có chuỗi `EDITOR` |
| `hasRole("ROLE_EDITOR")` | Không nên viết | `hasRole` đã áp dụng quy ước tiền tố; API DSL có thể từ chối đối số này |
| `hasAuthority("document:read")` | ALLOW | Khớp chính xác |
| `hasAuthority("document:write")` | DENY | Không có quyền này |
| `hasAuthority("SCOPE_documents.write")` | ALLOW | Khớp chuỗi scope đã chuyển đổi |
| `hasAuthority("documents.write")` | DENY | Thiếu `SCOPE_` |
| `hasRole("ADMIN")` | DENY | Không có `ROLE_ADMIN` |

Kết quả trên giả định luồng đã xác thực hợp lệ và quy ước mặc định của Spring Security, không có custom prefix hay manager tùy biến. Chính sách cần xác định authority nào là quyền chức năng, authority nào là vai trò và authority nào phản ánh scope từ hệ thống bên ngoài.

## 7. Role thực chất liên quan thế nào đến GrantedAuthority?

Trong Spring Security, **role thường là một authority có tiền tố** `ROLE_`. Ở cấu hình mặc định:

```text
hasRole("ADMIN")            ~= hasAuthority("ROLE_ADMIN")
hasRole("EDITOR")           ~= hasAuthority("ROLE_EDITOR")
hasAuthority("document:edit")  = kiểm tra đúng chuỗi "document:edit"
```

Ký hiệu `~=` nghĩa là tương đương về yêu cầu authority trong tình huống thông dụng, không phải mọi custom `AuthorizationManager` đều giống nhau. Tiền tố mặc định có thể được tùy biến qua `GrantedAuthorityDefaults` hoặc cấu hình liên quan. Khi thay prefix, phải nhất quán với cách tạo authorities, kiểm tra HTTP, method security, test, dữ liệu cũ và converter JWT.

Một role có thể đại diện cho nhiều permission trong thiết kế miền ứng dụng, nhưng Spring Security **không tự biết** “EDITOR ngầm có `document:read` và `document:edit`” chỉ từ cái tên `ROLE_EDITOR`. Nếu policy kiểm tra `hasAuthority("document:edit")`, bạn phải thực sự cấp authority `document:edit` hoặc dùng luật quy đổi role → permission rõ ràng.

Ví dụ:

```text
Alice:
  GrantedAuthority("ROLE_EDITOR")

Policy A: hasRole("EDITOR")             -> cho phép
Policy B: hasAuthority("document:edit") -> không cho phép
```

Nếu team muốn role EDITOR bao gồm permission sửa tài liệu, có thể ánh xạ role đó thành bộ authorities khi đăng nhập hoặc dùng policy service rõ ràng. Không kỳ vọng hai cách kiểm tra tự đồng nhất với nhau.

Đối với việc đặt tên, nên:
- Dùng `ROLE_*` cho role theo quy ước mặc định.
- Dùng các mã nhất quán như `document:read`, `document:edit` cho permission tổng quát.
- Dùng `SCOPE_*` khi authority được ánh xạ từ OAuth2 scopes theo quy ước resource server.
- Xác nhận phân biệt chữ hoa/chữ thường: `ROLE_ADMIN` khác `ROLE_admin`.
- Không tạo authority riêng cho mỗi một trong hàng triệu bản ghi để thay thế ACL/policy theo tài nguyên.

## 8. Ví dụ Java 17+ chạy độc lập: dữ liệu quyền và cách so khớp

Mục tiêu ví dụ là mô phỏng **cách so chuỗi authority**. Đây không phải mã nội bộ Spring Security, không thực hiện đăng nhập và không được dùng như lớp xác thực; việc gán `AuthSnapshot` trong demo được coi là dữ liệu **đã do server cấp và xác minh**.

Lưu thành file `AuthorityCheckDemo.java`:

```java
import java.util.List;

public class AuthorityCheckDemo {

    record AuthSnapshot(String subjectId, List<String> authorities) {}

    static boolean hasAuthority(AuthSnapshot auth, String required) {
        return auth.authorities().contains(required);
    }

    static boolean hasRole(AuthSnapshot auth, String role) {
        return hasAuthority(auth, "ROLE_" + role);
    }

    static boolean mayEditDocument(
        AuthSnapshot auth, String documentOwnerId
    ) {
        return hasAuthority(auth, "document:edit")
            && auth.subjectId().equals(documentOwnerId);
    }

    public static void main(String[] args) {
        AuthSnapshot alice = new AuthSnapshot("alice", List.of(
            "ROLE_EDITOR",
            "document:read",
            "document:edit"
        ));

        AuthSnapshot bob = new AuthSnapshot("bob", List.of(
            "ROLE_VIEWER",
            "document:read"
        ));

        System.out.println("Alice hasRole EDITOR: "
            + hasRole(alice, "EDITOR"));
        System.out.println("Alice hasAuthority EDITOR: "
            + hasAuthority(alice, "EDITOR"));
        System.out.println("Alice hasAuthority ROLE_EDITOR: "
            + hasAuthority(alice, "ROLE_EDITOR"));
        System.out.println("Bob read: "
            + hasAuthority(bob, "document:read"));
        System.out.println("Bob edit: "
            + hasAuthority(bob, "document:edit"));
        System.out.println("Alice edits own doc: "
            + mayEditDocument(alice, "alice"));
        System.out.println("Alice edits Bob's doc: "
            + mayEditDocument(alice, "bob"));
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac AuthorityCheckDemo.java
java AuthorityCheckDemo
```

Kết quả chính xác:

```text
Alice hasRole EDITOR: true
Alice hasAuthority EDITOR: false
Alice hasAuthority ROLE_EDITOR: true
Bob read: true
Bob edit: false
Alice edits own doc: true
Alice edits Bob's doc: false
```

Các quan sát:

1. `hasRole("EDITOR")` theo quy ước tìm `ROLE_EDITOR`; kiểm tra authority `EDITOR` đơn thuần không khớp.
2. Bob có quyền đọc nhưng không có quyền sửa.
3. Alice có `document:edit` vẫn không được sửa tài liệu của Bob trong policy giả lập vì thiếu điều kiện owner.
4. Trong ứng dụng thật còn phải kiểm tra tenant, trạng thái, dữ kiện từ database, quyền được ủy nhiệm và cách bảo vệ transaction.
5. Đoạn thuần Java không biểu diễn `AuthenticationTrustResolver`, anonymous, token validation hay toàn bộ `AuthorizationManager`. Nó cố ý chỉ tập trung vào phép tra authority.

## 9. Cấu hình HTTP: authority được sử dụng thế nào?

Ví dụ **một phần** cấu hình Servlet Spring Boot 3 / Spring Security 6.x:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
            .requestMatchers(HttpMethod.GET, "/api/public/**")
                .permitAll()
            .requestMatchers(HttpMethod.GET, "/api/documents/**")
                .hasAuthority("document:read")
            .requestMatchers(HttpMethod.PATCH, "/api/documents/**")
                .hasAuthority("document:edit")
            .requestMatchers("/api/admin/**")
                .hasRole("ADMIN")
            .requestMatchers(HttpMethod.GET, "/api/me")
                .authenticated()
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
```

Đoạn này định nghĩa các **luật phân quyền**, chưa cấu hình hạ tầng đăng nhập, session, token decoder hoặc CSRF; không thể coi riêng class là ứng dụng đầy đủ chạy ngay.

Cách diễn giải:

- `GET /api/documents/42` yêu cầu `document:read` trong `Authentication#getAuthorities()`.
- `PATCH /api/documents/42` yêu cầu `document:edit`, nhưng vẫn cần policy trên bản ghi 42 sau khi tải từ nguồn tin cậy.
- `/api/admin/**` yêu cầu authority `ROLE_ADMIN` theo mặc định.
- `GET /api/me` yêu cầu một danh tính được nhận biết là đã xác thực hợp lệ.
- Các request không khớp luật cụ thể bị chặn bởi `denyAll`.

**Thứ tự matcher có ý nghĩa:** các rule được xét theo thứ tự khai báo, rule khớp đầu tiên quyết định. Vì vậy, một matcher rộng như `/api/**.permitAll()` đặt trước các matcher cụ thể có thể làm vô hiệu mục đích bảo vệ của các rule phía sau.

Với endpoint dùng session/cookie để thực hiện PATCH/POST/DELETE, cần cấu hình và kiểm thử CSRF theo kiến trúc; không tắt CSRF chỉ để yêu cầu qua được. Lớp authorization không thay thế xác thực, CORS/CSRF hoặc chính sách nghiệp vụ.

## 10. Method security đọc cùng Authentication

HTTP security là điểm chặn ở biên request; method security là điểm chặn trên method của Spring bean. Bật bằng `@EnableMethodSecurity` rồi dùng `@PreAuthorize`:

```java
// Snippet service; các kiểu repository, document, policy tự do ứng dụng định nghĩa.
@Service
class DocumentService {
    private final DocumentRepository repository;
    private final DocumentPolicy documentPolicy;

    DocumentService(DocumentRepository repository,
                    DocumentPolicy documentPolicy) {
        this.repository = repository;
        this.documentPolicy = documentPolicy;
    }

    @PreAuthorize("hasAuthority('document:edit')")
    @Transactional
    public void rename(long id, String newTitle, Actor actor) {
        Document document = repository
            .findByIdAndTenantId(id, actor.tenantId())
            .orElseThrow(DocumentNotFoundException::new);

        if (!documentPolicy.mayRename(actor, document)) {
            throw new AccessDeniedException("No permission to rename");
        }

        document.rename(newTitle);
    }
}
```

Đoạn trên minh họa tích hợp, không phải file Java độc lập: repository, entity, Actor và exception là type nghiệp vụ ứng dụng định nghĩa; cần import annotation/exception từ Spring tương ứng.

Tầng `@PreAuthorize` hỏi “người gọi có `document:edit` hay không?”; policy service hỏi “trên bản ghi này, trong tenant và trạng thái này, người này có được phép đổi tên hay không?”.

**Điều kiện quan trọng:** `Actor` phải do server ánh xạ từ `Authentication` tin cậy, không nhận `Actor`/`tenantId`/`role` nguyên vẹn từ body do client tự khai. Khi service có nhiều entry point (HTTP, job, listener), không được chỉ dựa vào HTTP matcher.

Method security thường đi qua AOP proxy. Lời gọi `this.rename(...)` từ method khác của cùng object có thể bỏ qua interceptor `@PreAuthorize`. Nếu một use case cần bảo vệ ở mọi đường gọi, hãy thiết kế một policy guard trong service hoặc bảo đảm điểm gọi qua bean/proxy đúng.

## 11. Truy cập Authentication và principal trong controller/service

Ba cách thông dụng trong Servlet:

**Cách A — Nhận `Authentication` trong controller Spring MVC:** ở endpoint bảo vệ phù hợp, Spring MVC có thể đưa principal đã xác thực vào method.

```java
@GetMapping("/api/me")
public String currentName(Authentication authentication) {
    return authentication.getName();
}
```

**Cách B — Lấy từ context khi xử lý cùng thread:**

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

if (authentication != null) {
    String subject = authentication.getName();
}
```

Đây chỉ là cách đọc, không phải phép kiểm tra “đã đăng nhập” đầy đủ. Một `Authentication` tồn tại có thể là anonymous. Với thành phần singleton dùng chung, tránh cache tên user trong field. Đối với cấu trúc cần kiểm tra quyền, nên dùng Spring Security authorization API thay vì tự viết nhiều lần `if (authentication != null)`.

**Cách C — Lấy principal theo kiểu đã cấu hình bằng `@AuthenticationPrincipal`:** phù hợp khi chắc chắn principal là `UserDetails` hoặc `Jwt`. Nếu muốn đọc toàn context, dùng `@CurrentSecurityContext`.

| API | Bạn nhận được gì? | Điểm cần chú ý |
| --- | --- | --- |
| `@AuthenticationPrincipal` | `Authentication#getPrincipal()` | Type phụ thuộc cơ chế authentication |
| Tham số `Authentication` trong MVC | Đối tượng authentication đại diện principal request | Với anonymous, cách MVC lấy từ Servlet principal có thể trả null |
| `@CurrentSecurityContext` | `SecurityContext` | Lấy được authentication đang chứa, kể cả loại anonymous tùy filter |
| `SecurityContextHolder.getContext()` | Context hiện tại theo chiến lược holder | Mặc định gắn thread Servlet |
| `authentication.getAuthorities()` | Collection authority | Không nên log toàn bộ nếu chứa thông tin nhạy cảm về quyền nội bộ |

Khi cần truyền danh tính sâu vào domain, hãy ánh xạ sang `Actor` của ứng dụng tại biên và truyền rõ ràng, để domain không lệ thuộc vào `SecurityContextHolder` hoặc kiểu token.

## 12. Anonymous authentication và bẫy isAuthenticated()

Spring Security hỗ trợ `AnonymousAuthenticationToken`. Nếu request chưa có người dùng thật đăng nhập, `AnonymousAuthenticationFilter` có thể đặt một authentication đại diện cho khách vô danh vào `SecurityContext`. Điều này giúp hệ thống xử lý các luồng anonymous nhất quán.

Bẫy:

```java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();

// KHÔNG dùng điều kiện này làm kết luận đã đăng nhập thật:
if (auth != null && auth.isAuthenticated()) {
    // Có thể chứa AnonymousAuthenticationToken.
}
```

Một số `AnonymousAuthenticationToken` được đánh dấu authenticated theo implementation, mặc dù người gọi vẫn là khách vô danh theo nghĩa bảo mật. Do đó:

- `isAuthenticated()` của token **không đồng nghĩa** “người dùng thật đã chứng minh danh tính”.
- DSL `.authenticated()` và biểu thức `isAuthenticated()` trong các điểm kiểm tra Spring Security áp dụng cơ chế phân biệt anonymous/trust resolution phù hợp.
- `permitAll` là cấp phép truy cập công khai theo cấu hình, không phải đánh dấu client có quyền nghiệp vụ.
- Nếu cần phân biệt anonymous/remember-me/fully authenticated, sử dụng những khả năng do framework cung cấp (ví dụ `fullyAuthenticated()`) với hợp đồng xác thực rõ.
- Tránh tự gán quyền nhạy cảm như `ROLE_ADMIN` cho anonymous token hay dùng `ROLE_ANONYMOUS` làm dấu hiệu quyền người dùng thật.

Với anonymous request trong MVC, tham số `Authentication` theo cơ chế resolve từ Servlet principal có thể là `null` dù `SecurityContext` chứa `AnonymousAuthenticationToken`. Nếu cần nhìn trực tiếp anonymous auth, dùng `@CurrentSecurityContext`.

## 13. Tập authority có nguồn gốc từ đâu?

Tập authorities thường được tạo/ánh xạ trong quá trình xác thực, ví dụ:

| Nguồn | Cách hình thành authority | Điều cần kiểm soát |
| --- | --- | --- |
| Username/password + `UserDetailsService` | `UserDetails#getAuthorities()` từ kho user/role | Quyền được nạp từ DB/config đáng tin; hiểu thời điểm refresh |
| LDAP/AD | Mapper của authentication provider | Phân biệt group thực và permission nội bộ |
| HTTP Basic | Sau khi xác thực credential, dùng authorities của principal | Basic chỉ là transport credential, không phải nguồn quyền |
| OAuth2 Resource Server JWT | Converter đưa claims/scopes đã xác minh thành authorities | Validate signature, expiry, issuer, audience theo yêu cầu triển khai; mapping claim rõ ràng |
| OAuth2 Login/OIDC | Mapper của user authority/claims | Phân biệt identity claim với quyền thực sự được cấp |
| Custom SSO/token | `AuthenticationProvider`/converter riêng | Không chấp nhận authorities do client tự khai |

Spring Security Resource Server JWT theo mặc định thường lấy scope từ claim `scope`/`scp` và ánh xạ thành authority có tiền tố `SCOPE_`. Ví dụ claim scope là `documents.read` thì có thể nhận:

```text
JWT scope: "documents.read"
    |
    v
GrantedAuthority("SCOPE_documents.read")
    |
    v
hasAuthority("SCOPE_documents.read") -> ALLOW
```

Điều này **không tự tạo** `ROLE_ADMIN` và cũng không tự tạo `document:read`. Muốn dùng `hasRole("ADMIN")` hoặc `hasAuthority("document:read")`, ứng dụng phải có mapping rõ, được kiểm thử, từ claim/nguồn quyền đáng tin. Khi tự cấu hình `JwtGrantedAuthoritiesConverter`, tên claim và prefix có thể thay đổi.

**Lưu ý về JWT:** claim `sub` xác định subject; `scope` mô tả phạm vi token; `roles` nếu xuất hiện là dữ liệu theo issuer đã thỏa thuận, không mặc nhiên là role của ứng dụng. Token phải được kiểm tra chữ ký, thuật toán hợp lệ, hiệu lực, issuer/audience và các yêu cầu hệ thống tương ứng. Không lấy quyền từ payload JWT chưa được verifier tin cậy chấp nhận.

**Lưu ý về session:** authorities gắn trong một `Authentication` lưu ở session có thể phản ánh snapshot khi đăng nhập. Nếu role thay đổi trong database nhưng session chưa refresh/invalidate, quyền cũ có thể còn tác dụng. Phải thiết kế cơ chế thu hồi, cập nhật context, session invalidation hoặc tra cứu lại policy tại thời điểm xử lý hành động nhạy cảm.

## 14. Một Authentication chứa authority không có nghĩa owner của mọi object

Giả sử Bob và Alice đều có `ROLE_EDITOR`, nhưng chỉ Alice là owner tài liệu 42.

```text
Authentication(Alice)
  principal = alice
  authorities = ["ROLE_EDITOR", "document:edit"]

Authentication(Bob)
  principal = bob
  authorities = ["ROLE_EDITOR", "document:edit"]

Document 42:
  owner = alice
  tenant = org-a
  status = DRAFT
```

Cả hai có thể vượt qua `hasAuthority("document:edit")` khi gọi cùng API. Nhưng khi kiểm tra `policy.canEdit(actor, document)`:
- Alice được sửa nếu đúng tenant và tình trạng cho phép.
- Bob bị từ chối nếu policy yêu cầu owner hoặc grant cụ thể và Bob không có quyền tương ứng.

Vì vậy, cách thiết kế đầy đủ có thể là:

```text
ALLOW khi
   isAuthenticatedByTrustedMechanism
AND hasAuthority("document:edit")
AND actor.tenantId == document.tenantId
AND (actor.id == document.ownerId OR hasResourceGrant(actor, document, WRITE))
AND document.status == DRAFT
```

Không dùng `principal.name` một cách máy móc để so owner nếu domain lưu ID bất biến, tenant và issuer khác. Mối quan hệ giữa principal và entity phải được xác nhận qua một mapper đáng tin.

**Không nhét một authority riêng cho mỗi tài liệu** như `DOCUMENT_42_EDITOR` vào danh tính của hàng triệu bản ghi. Quyền trên từng object thường nên nằm ở ACL, policy service hoặc query có scope theo actor, thay vì phình tập authorities trong session/token.

## 15. Quy tắc kiểm tra có thể kết hợp nhiều authority

Tùy API/DSL và phiên bản, có thể có nhiều kiểu quyết định:

- `hasAuthority("document:read")`: cần đúng một authority.
- `hasAnyAuthority("document:read", "document:admin")`: thỏa **ít nhất một** authority.
- `hasRole("ADMIN")`: kiểm tra role theo convention.
- `hasAnyRole("EDITOR", "ADMIN")`: chấp nhận một trong các role.
- Kiểm tra kết hợp bằng một policy tùy biến: có role phù hợp **và** thuộc tenant **và** đang thao tác loại tài nguyên được phép.
- `@PreAuthorize("hasAuthority('document:edit') and ...")`: diễn đạt logic có điều kiện ở method security, nhưng cần tránh SpEL dài khó audit.
- `AuthorizationManager` tùy biến: dùng khi có quy tắc tái sử dụng phức tạp hoặc cần dữ liệu từ service/domain.

Đối với yêu cầu “có cả READ và WRITE”, không dùng `hasAnyAuthority("READ", "WRITE")` rồi tưởng đó là phép AND. Phải xây rule thực sự yêu cầu cả hai hoặc dùng policy service. Tương tự, nếu `ROLE_ADMIN` phải đi qua một kiểm tra tenant, đừng viết nhánh OR cho ADMIN vô tình bỏ toàn bộ điều kiện tenant.

Trong các cấu hình dựa trên authorities, authorization không nên bị phân tán thành các kiểm tra thủ công không thống nhất ở controller, service, event listener và query. Một policy thống nhất, được gọi ở các entry point thích hợp, sẽ dễ kiểm thử hơn.

## 16. Runtime Servlet, thread khác và WebFlux

Trong ứng dụng **Servlet**, `SecurityContextHolder` theo mặc định dùng `ThreadLocal`. Mã trên cùng thread của request có thể đọc context. Nhưng khi bạn tạo thread mới, dùng `@Async`, executor hoặc scheduler, đừng mặc định rằng context của request được truyền qua an toàn.

Các cơ chế như `DelegatingSecurityContextRunnable` hoặc `DelegatingSecurityContextExecutor` có thể giúp truyền context trong tác vụ Servlet khi có lý do chính đáng. Cần kiểm soát vòng đời, không giữ user cũ ngoài phạm vi tác vụ, không dùng `MODE_GLOBAL` trong web app nhiều người dùng.

Trong ứng dụng **Reactive WebFlux**, context gắn với chuỗi Reactor qua `ReactiveSecurityContextHolder`, không thể giả định đọc bằng `SecurityContextHolder` kiểu Servlet trong một luồng reactive là đúng. Những đoạn `SecurityContextHolder` trong bài này dành cho **Servlet**.

Một job nền chạy theo service account cần danh tính/capability rõ ràng và áp dụng authorization phù hợp; đừng tự lấy ngẫu nhiên người dùng cuối cùng còn trong thread hoặc dùng quyền admin ngầm định.

## 17. Kết quả lỗi: xác thực và phân quyền là hai nhánh khác nhau

Các trường hợp thông dụng:

| Tình huống | Kết quả chính | HTTP phổ biến |
| --- | --- | --- |
| Không có credential hợp lệ cho endpoint cần đăng nhập | Bắt đầu quá trình authentication hoặc từ chối | 401 với API, có thể 302 sang login cho web form |
| Đã đăng nhập nhưng thiếu `document:read` | Authorization deny | Thường 403 |
| Có `document:read` nhưng không có quyền xem object 42 | Resource authorization deny | 403 hoặc 404 theo chiến lược tránh lộ sự tồn tại |
| Có quyền nhưng object không tồn tại | Resource không tìm thấy | 404 |
| Có quyền nhưng object đã APPROVED, không thể sửa | Điều kiện nghiệp vụ từ chối thao tác | Mã lỗi domain thích hợp, ví dụ 409 |

Lưu ý phản hồi cụ thể còn phụ thuộc `AuthenticationEntryPoint`, `AccessDeniedHandler`, exception handling của ứng dụng và cơ chế login. Không cho rằng cứ `auth != null` thì phải trả 403; anonymous request có thể chứa authentication kỹ thuật nhưng vẫn cần được mời xác thực.

Tránh log credential, raw bearer token, mật khẩu, nội dung claim nhạy cảm hoặc toàn bộ `principal`. Để chẩn đoán authorization, ghi mã request/correlation ID, actor ID đã chuẩn hóa, action, resource ID, decision và reason an toàn theo chính sách audit.

## 18. Kiểm thử đúng việc cấp authority và đúng điểm chặn

Một ma trận đơn giản để kiểm thử:

| Principal và authorities | Yêu cầu | Kết quả kỳ vọng |
| --- | --- | --- |
| Alice: `ROLE_EDITOR`, `document:read` | `hasRole("EDITOR")` | ALLOW |
| Alice: `ROLE_EDITOR`, `document:read` | `hasAuthority("EDITOR")` | DENY |
| Alice: `ROLE_EDITOR`, `document:read` | `hasAuthority("ROLE_EDITOR")` | ALLOW |
| Alice: `ROLE_EDITOR`, `document:read` | `hasAuthority("document:edit")` | DENY |
| Bob: `SCOPE_documents.read` | `hasAuthority("SCOPE_documents.read")` | ALLOW |
| Bob: `SCOPE_documents.read` | `hasAuthority("document:read")` | DENY nếu chưa map |
| Anonymous | `authenticated()` | DENY |
| Alice có `document:edit` nhưng không có quyền object 42 | Policy trên object | DENY |
| Alice có `document:edit` và là owner object 42 cùng tenant DRAFT | Policy trên object | ALLOW |

Có thể dùng Spring Security Test để mock danh tính ở tầng method hoặc HTTP:

```java
// Snippet kiểm thử; cần spring-security-test và môi trường test phù hợp.
@Test
@WithMockUser(username = "alice", authorities = {"document:read"})
void readerCanRead() {
    // Gọi endpoint/service yêu cầu document:read; assert 200/allow.
}

@Test
@WithMockUser(username = "alice", roles = {"EDITOR"})
void editorHasRole() {
    // Gọi endpoint/service yêu cầu hasRole("EDITOR").
}
```

`@WithMockUser(roles={"EDITOR"})` tạo authority `ROLE_EDITOR` theo convention; `authorities={"document:read"}` tạo authority theo chuỗi literal. **Không suy ra** mock user đồng thời có `document:read` chỉ vì đang có `ROLE_EDITOR`. Nếu cấu hình cần cả role lẫn permission, truyền rõ tập authorities trong fixture hoặc cung cấp custom security context.

Các cấp kiểm thử quan trọng:

1. **Unit:** quyền được map đúng từ dữ liệu user/role; helper/policy có ALLOW, DENY, thiếu authority và case khác.
2. **Method security:** bật `@EnableMethodSecurity`, bảo đảm annotation thực sự chạy qua proxy, test cả self-invocation/alternate path theo kiến trúc.
3. **HTTP:** kiểm tra matchers GET/PATCH/DELETE, quyền thiếu/đủ, anonymous/authenticated, 401/403 và CSRF theo cấu hình.
4. **JWT integration:** dùng token/decoder được kiểm thử để xác minh role/scope converter, issuer/audience, expiry, claim khác tên và quyền không tự xuất hiện.
5. **Domain policy:** chỉ đổi owner/tenant/status của object để chứng minh có hoặc không quyền trên bản ghi, không chỉ kiểm tra role ở biên.
6. **Revocation:** đổi role, khóa tài khoản, gỡ nhóm rồi thử lại qua session/cache/token cũ theo hợp đồng hết hạn/quyền hiện hành.

**Bẫy test:** một POST/PATCH trả 403 do thiếu CSRF token không chứng minh `hasAuthority` đang chặn. Test phải loại bỏ nguyên nhân nhiễu, tạo đúng authentication và request hợp lệ, rồi thay đổi **duy nhất** tập authority hoặc điều kiện resource để kiểm chứng kết luận.

## 19. Những sai lầm gây lỗ hổng hoặc khiến quyền không hoạt động

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Ép mọi principal sang `UserDetails` | Lỗi khi dùng JWT/OIDC/anonymous | Xác định kiểu principal thực tế hoặc dùng adapter ánh xạ |
| Coi `getName()` luôn là user ID DB | Quyền gán sai user, nhầm tenant/issuer | Chuẩn hóa stable ID từ nguồn tin cậy |
| Chỉ kiểm tra `auth != null && auth.isAuthenticated()` | Có thể nhận nhầm anonymous | Dùng DSL `authenticated()`/trust resolver chuẩn |
| Coi `hasRole("EDITOR")` bằng `hasAuthority("EDITOR")` | Deny không mong đợi | Hiểu prefix mặc định `ROLE_` |
| Truyền `ROLE_ADMIN` vào `hasRole` | Dùng API sai convention, có thể lỗi cấu hình | Gọi `hasRole("ADMIN")` hoặc `hasAuthority("ROLE_ADMIN")` |
| Nghĩ JWT có `scope` thì sẽ có `document:read` | Endpoint bị deny hoặc rule dùng nhầm quyền | Cấu hình converter và test `SCOPE_` |
| Tin header/body `role=admin` | Leo thang đặc quyền | Authorities chỉ do authentication infrastructure cấp |
| Chỉ kiểm tra quyền chung ở URL | IDOR/BOLA trên từng tài liệu | Bổ sung tenant/object policy |
| Gắn mọi quyền object vào authorities | Token/session phình lớn, khó thu hồi | ACL/resource policy/query scoped |
| Cất `Authentication` vào biến static | Rò danh tính chéo request | Giữ context đúng phạm vi và vòng đời |
| Dùng `SecurityContextHolder` như Servlet ở WebFlux | Sai/mất context reactive | Dùng `ReactiveSecurityContextHolder` |
| Dùng `@PreAuthorize` rồi gọi cùng bean qua `this` | Có thể bypass method interceptor | Chuyển điểm gọi qua proxy/guard trong use case |
| Chỉ đổi role ở database | Session/token/cache cũ vẫn có quyền | Thiết kế refresh/revoke/invalidation |
| Log toàn bộ principal/credentials | Lộ secret/thông tin người dùng | Audit tối thiểu, có kiểm soát |

## 20. Checklist khi thêm một rule authorization

1. **Danh tính:** principal thật là loại nào? `getName()` ánh xạ thế nào sang actor ID của domain và tenant?
2. **Nguồn cấp quyền:** authority được tạo ở `UserDetailsService`, provider, JWT converter hay custom mapper? Có đáng tin không?
3. **Tên quyền:** dùng `ROLE_*`, `SCOPE_*` hay mã permission như `document:read`? Prefix có được đổi không?
4. **Quy tắc:** cần một authority, nhiều authority theo OR/AND, hay cần policy dựa trên object/context?
5. **Điểm chặn:** cần bảo vệ HTTP matcher, method, service use case, background job, list/export/download nào?
6. **Giới hạn domain:** tenant, owner, nhóm, trạng thái, ủy nhiệm và kiểm tra transaction có được áp dụng sau quyền tổng quát không?
7. **Danh tính đặc biệt:** anonymous, remember-me, token từ issuer khác, session cũ và request thiếu context được xử lý thế nào?
8. **Thu hồi:** role/scope thay đổi có hiệu lực khi nào, đối với session/JWT/cache thế nào?
9. **Kiểm thử:** có case ALLOW/DENY, thiếu quyền, prefix, JWT claim, alternate entry point, CSRF và object khác tenant không?
10. **Quan sát:** lỗi authentication/authorization/domain và audit có phân biệt rõ mà không tiết lộ dữ liệu không?

**Tự kiểm tra:**

- Alice có `ROLE_EDITOR` nhưng chỉ có `document:read`. Một API dùng `hasAuthority("document:edit")` có cho qua không? → **Không**. Role EDITOR không tự động sinh quyền edit nếu chưa được map.
- JWT có scope `documents.read`, converter mặc định ánh xạ thành authority gì? → Thông thường là `SCOPE_documents.read`; `hasAuthority("documents.read")` không khớp.
- Controller lấy `authentication.getPrincipal()` rồi ép thành `UserDetails`, khi chuyển sang Resource Server JWT điều gì xảy ra? → Principal thường là `Jwt` nên ép kiểu có thể thất bại; phải thay adapter hoặc cách đọc.
- Một `AnonymousAuthenticationToken` có `isAuthenticated() == true`. Có được xem là user đăng nhập? → **Không**; dùng trust resolver/cơ chế kiểm tra authenticated của Spring Security.
- Bob có `document:edit` nhưng tài liệu thuộc tenant Alice. Có được sửa? → **Không**, nếu policy yêu cầu đúng tenant và chưa có ủy quyền hợp lệ.

**Ý chính:** `Authentication` là biểu diễn danh tính trong security context, `principal` là thông tin nhận diện nằm trong đó, còn `GrantedAuthority` là tập quyền tổng quát được cấp bởi nguồn xác thực/ủy quyền tin cậy. Spring Security có thể đối chiếu role/authority bằng `hasRole`/`hasAuthority`, nhưng quyền trên **từng đối tượng nghiệp vụ** vẫn phải được ứng dụng kiểm tra đầy đủ.

## Tài liệu tham khảo

- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security — Anonymous Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/anonymous.html)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
