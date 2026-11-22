# hasAuthority cho scope và hasRole cho vai trò đã chuẩn hóa

## 1. Bài toán: OAuth2 scope không tự biến thành Spring Security role

Một OAuth2 access token hợp lệ có thể chứa:

```json
{
  "iss": "https://idp.example.org",
  "sub": "alice",
  "aud": ["api://documents"],
  "scope": "documents.read documents.write",
  "app_roles": ["USER"]
}
```

Với Spring Security Resource Server, các scope trong JWT được ánh xạ mặc định thành những `GrantedAuthority` có tiền tố `SCOPE_`. Theo đó, một token có `scope="documents.read documents.write"` thường tạo:

```text
SCOPE_documents.read
SCOPE_documents.write
```

Nhưng claim `app_roles` trong ví dụ **không tự động** trở thành `ROLE_USER`. Resource Server không thể biết `roles` hay `app_roles` của mọi identity provider có ý nghĩa gì. Ứng dụng cần cấu hình mapping roles theo issuer contract.

Do đó, hai biểu thức:

```java
@PreAuthorize("hasAuthority('SCOPE_documents.read')")
@PreAuthorize("hasRole('ADMIN')")
```

không thay thế nhau. Biểu thức đầu tìm authority chính xác `SCOPE_documents.read`; biểu thức sau, theo default role prefix, tìm `ROLE_ADMIN`. Cả hai kiểm tra `Authentication.getAuthorities()`, chứ không trực tiếp kiểm tra raw JSON trong JWT mỗi khi method được gọi.

**Mục tiêu của bài:** hiểu sự khác nhau giữa scope, role và authority; chuẩn hóa role an toàn; cấu hình mapping cả `SCOPE_` và `ROLE_`; dùng `hasAuthority` và `hasRole` trong HTTP/method security; kiểm thử role/scope không bị lẫn; và tránh cấp quyền ngoài dự kiến khi JWT chứa claim không đáng tin.

## 2. Phân biệt scope, role và GrantedAuthority

| Thuật ngữ | Ví dụ | Công dụng |
| --- | --- | --- |
| OAuth2 scope | `documents.read` | Quyền/khả năng access token được cấp đối với API |
| Scope authority | `SCOPE_documents.read` | Dạng Spring Security thường tạo từ `scope`/`scp` |
| Vai trò ứng dụng | `ADMIN`, `AUDITOR` | Nhóm trách nhiệm hoặc entitlement theo nghiệp vụ |
| Role authority | `ROLE_ADMIN` | Dạng Spring Security dùng mặc định với `hasRole('ADMIN')` |
| Object permission | Alice READ được Document 42 | Cần owner, ACL, tenant, trạng thái hoặc ABAC |
| Principal | `iss` + `sub` hoặc identity nội bộ | Ai đang được xác thực |
| Authentication | `JwtAuthenticationToken` | Principal, trạng thái authentication và authorities |
| GrantedAuthority | `SimpleGrantedAuthority("ROLE_ADMIN")` | Một authority cụ thể sau khi authentication/mapping |

OAuth2 không quy định mọi token phải có claim `roles`. Một IdP có thể dùng `groups`, `realm_access.roles`, `resource_access` hoặc claim riêng. Ngược lại, một token client-credentials có thể có scope rất rộng mà **không mang end-user role**. Ứng dụng phải xác định rõ role thuộc user, client, tenant hay tổ chức nào.

Ví dụ authentication có:

```text
Authentication.name = alice
Authentication.authorities =
    SCOPE_documents.read
    SCOPE_reports.export
    ROLE_USER
```

Lúc này `hasAuthority('SCOPE_documents.read')` đúng, `hasRole('USER')` đúng, nhưng `hasRole('ADMIN')` sai. Nếu chỉ thấy tên claim `app_roles=["ADMIN"]` ở token mà converter không cấp `ROLE_ADMIN` thì `hasRole('ADMIN')` vẫn sai.

## 3. hasAuthority kiểm tra authority chính xác

`hasAuthority(String)` kiểm tra caller có GrantedAuthority tương ứng. Nó **không tự thêm `SCOPE_` hay `ROLE_`** vào chuỗi đầu vào.

```java
@PreAuthorize("hasAuthority('SCOPE_documents.read')")
public DocumentView readDocument(String id) {
    return service.read(id);
}
```

Với authorities `[SCOPE_documents.read, ROLE_USER]`:

| Biểu thức | Kết quả mặc định |
| --- | --- |
| `hasAuthority('SCOPE_documents.read')` | true |
| `hasAuthority('documents.read')` | false |
| `hasAuthority('SCOPE_documents.write')` | false |
| `hasAuthority('ROLE_USER')` | true |
| `hasAuthority('USER')` | false |
| `hasAuthority('ROLE_ADMIN')` | false |

Nên dùng `hasAuthority('SCOPE_x')` cho scope OAuth2 khi converter đang dùng mặc định. Nếu một dự án chủ động thay `JwtGrantedAuthoritiesConverter#setAuthorityPrefix("")` thì authority sẽ không có `SCOPE_`, nhưng mọi expression cần nhất quán với converter đó. Với nhiều loại quyền, giữ các namespace riêng thường dễ kiểm toán hơn.

### hasAnyAuthority và hasAll

```java
@PreAuthorize(
    "hasAnyAuthority('SCOPE_documents.read','SCOPE_documents.audit')")
```

cho phép khi caller có **một** trong các authorities. Nếu nghiệp vụ yêu cầu hai scope đồng thời, hãy viết điều kiện AND hoặc dùng API hỗ trợ all-of trong phiên bản đang chạy. Không tự suy ra `documents.write` luôn bao hàm `documents.read` chỉ vì tên gọi: OAuth2 issuer/API policy quyết định quan hệ này.

## 4. hasRole thêm default role prefix

Với prefix tiêu chuẩn `ROLE_`, biểu thức:

```java
@PreAuthorize("hasRole('ADMIN')")
```

tìm authority `ROLE_ADMIN`. Nó thường tương ứng với:

```java
@PreAuthorize("hasAuthority('ROLE_ADMIN')")
```

khi cả hai áp dụng cùng role hierarchy và không có customization khác. Nhưng:

```java
@PreAuthorize("hasRole('documents.read')")
```

**không tương đương** `hasAuthority('SCOPE_documents.read')`; nó nhắm tới `ROLE_documents.read` trong cấu hình mặc định.

| Authority hiện có | hasRole('ADMIN') | hasAuthority('ROLE_ADMIN') |
| --- | --- | --- |
| `ROLE_ADMIN` | true | true |
| `SCOPE_ADMIN` | false | false |
| `ADMIN` | false | false |
| `ROLE_ROLE_ADMIN` | false | false |
| `SCOPE_documents.read` | false | false |

Bảng giả định không có role hierarchy hay custom prefix.

Trong Java request DSL, hãy dùng `.hasRole("ADMIN")`, **không** dùng `.hasRole("ROLE_ADMIN")`. Một số request authorization implementations sẽ từ chối role string đã có `ROLE_`. Nếu muốn so khớp chính xác `ROLE_ADMIN`, sử dụng `.hasAuthority("ROLE_ADMIN")`. Với SpEL method security, cách viết dễ đọc nhất vẫn là `hasRole('ADMIN')`.

### Role prefix có thể tùy biến

Spring Security hỗ trợ `GrantedAuthorityDefaults` và trong Spring Security 7.x có `AuthorizationManagerFactory` để cấu hình role prefix cho những manager tương ứng. Nếu đổi prefix sang `APP_ROLE_`, converter cũng phải tạo authorities tương ứng; không được chỉ thay một bên rồi mặc định mọi HTTP/method expressions sẽ tự đồng bộ. Đa số dự án không cần đổi mặc định `ROLE_`.

## 5. JWT scope mặc định được chuyển sang SCOPE_ như thế nào?

Theo Spring Security Resource Server documentation, JWT có claim `scope` hoặc `scp` thường được chuyển thành danh sách GrantedAuthority với tiền tố `SCOPE_`. Ví dụ:

```json
{
  "sub": "alice",
  "scope": "documents.read reports.export"
}
```

cho ra:

```text
SCOPE_documents.read
SCOPE_reports.export
```

Một issuer khác có thể dùng:

```json
{
  "sub": "bob",
  "scp": ["documents.read", "documents.write"]
}
```

và cho ra:

```text
SCOPE_documents.read
SCOPE_documents.write
```

Spring Security có `JwtGrantedAuthoritiesConverter` để xử lý scope mapping và `JwtAuthenticationConverter` để tạo `Authentication` từ token đã được giải mã/validate.

**Quan trọng:** JWT hợp lệ nghĩa là token được **xác minh** trước khi tin claims. Chỉ base64-decode token rồi đọc `scope`/`roles` không đủ; attacker có thể tự sửa payload.

Đường xử lý:

```text
Authorization: Bearer access-token
       |
       v
JwtDecoder
 - verify signature, key, algorithm
 - issuer and timestamps validation
 - audience/token purpose theo cấu hình API
       |
       v
JwtAuthenticationConverter
 - JwtGrantedAuthoritiesConverter: scope/scp -> SCOPE_...
 - application role converter: issuer-controlled roles -> ROLE_...
       |
       v
JwtAuthenticationToken
 - principal / name
 - GrantedAuthorities
       |
       v
HTTP hasAuthority/hasRole
method @PreAuthorize
       |
       v
object/tenant policy trước truy cập dữ liệu
```

Issuer và audience là hai ranh giới quan trọng: token hợp lệ về chữ ký nhưng được phát cho **API khác** không nên dùng tại Resource Server này. Spring Boot có cấu hình `issuer-uri`, `audiences` tương ứng ở các phiên bản hỗ trợ, nhưng bạn vẫn phải xác định đúng schema và token type.

## 6. Role claim không tự biến thành ROLE_ADMIN

Giả sử token:

```json
{
  "sub": "alice",
  "scope": "documents.read",
  "app_roles": ["ADMIN", "USER"]
}
```

Resource Server default scope converter không mặc nhiên hiểu `app_roles` là nguồn của vai trò. Nếu hệ thống muốn `hasRole('ADMIN')`, phải thêm mapping có chủ đích.

Thiết kế tốt:

```text
scope / scp
  "documents.read"  -> "SCOPE_documents.read"

trusted app_roles
  "ADMIN"           -> "ROLE_ADMIN"
  "USER"            -> "ROLE_USER"
```

Không nên dùng một dòng:

```java
JwtGrantedAuthoritiesConverter scopes =
        new JwtGrantedAuthoritiesConverter();
scopes.setAuthorityPrefix("ROLE_");
```

để “giúp hasRole chạy”. Dòng đó **đổi namespace của scope** thành `ROLE_documents.read` thay vì thêm một converter mới cho vai trò; kết quả `hasAuthority('SCOPE_documents.read')` sẽ sai. Nguy hiểm hơn, nếu token có scope tên `ADMIN`, cách cấu hình sai có thể tạo `ROLE_ADMIN` ngoài ý định.

### Vai trò đã chuẩn hóa nghĩa là gì?

Trước khi tạo `ROLE_...`, cần thỏa các bước:

1. Token/identity được issuer tin cậy xác minh.
2. Role claim đúng vị trí, đúng audience, đúng token purpose.
3. Claim có kiểu dữ liệu đã thống nhất, ví dụ danh sách strings.
4. Tên role có **vocabulary và allowlist**.
5. Ánh xạ legacy/group name bằng bảng cấu hình đã được phê duyệt.
6. Phân biệt platform role và tenant-local role.
7. Chỉ thêm prefix `ROLE_` một lần.
8. Nếu claim thiếu/sai/unknown, **không cấp role**.
9. Có test role bị revoke, issuer mới và token bị sửa.
10. Không lấy role từ header, request body hoặc cookie do client tự khai.

Ví dụ từ hai issuers:

| Nguồn | Role thô | Mapping |
| --- | --- | --- |
| IdP A, trusted claim | `ADMIN` | `ROLE_ADMIN` |
| IdP B, trusted group `/documents/admins` | group cần mapper riêng | Có thể `ROLE_ADMIN` theo contract |
| Tenant alpha membership | `OWNER` | Quyền OWNER trong **alpha**, không mặc định global ADMIN |
| Client `X-Role` | `ADMIN` | Không tin |
| Raw claim `ROLE_ADMIN` nhưng contract nhận `ADMIN` | sai format | Không cấp quyền |

Không chỉ `toUpperCase()` rồi chấp nhận mọi string; unknown role không nên được “làm cho hợp lệ”.

## 7. Truth table: scope và role là hai điều kiện độc lập

Giả sử chỉ dùng hai authorities `SCOPE_documents.read` và `ROLE_ADMIN`:

| Token sau mapping | hasAuthority('SCOPE_documents.read') | hasRole('ADMIN') |
| --- | --- | --- |
| `[SCOPE_documents.read]` | true | false |
| `[ROLE_ADMIN]` | false | true |
| `[SCOPE_documents.read, ROLE_ADMIN]` | true | true |
| `[SCOPE_ADMIN]` | false | false |
| `[ROLE_USER]` | false | false |
| `[]` | false | false |

Với endpoint xuất tài liệu dành cho admin:

```java
@PreAuthorize(
    "hasAuthority('SCOPE_documents.export') and hasRole('ADMIN')")
```

biểu thức này yêu cầu **cả scope export và role ADMIN**. Một token chỉ có role ADMIN không thể tự vượt client scope. Ngược lại, scope export không tự biến caller thành admin.

Ví dụ chỉ cần một trong hai loại grants:

```java
@PreAuthorize(
    "hasAuthority('SCOPE_reports.read') or hasRole('AUDITOR')")
```

chỉ hợp lệ khi nghiệp vụ **thực sự chấp thuận** AUDITOR bypass scope. Không dùng OR chỉ để chữa lỗi 403 do mapping chưa đúng.

## 8. Java 17 không dependency: mô phỏng semantics với stdout

Để thấy chính xác sự khác biệt, trước hết dùng một chương trình Java 17 độc lập. Nó mô phỏng phép so khớp authority (không phải implementation của Spring Security và **không xác minh JWT**).

Tệp `ScopeRoleSemanticsLab.java`:

```java
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public final class ScopeRoleSemanticsLab {

    record Principal(String subject, Set<String> authorities) {}

    private static Principal mapped(
            String subject,
            List<String> scopes,
            List<String> trustedCanonicalRoles) {

        Set<String> allowlisted = Set.of("USER", "AUDITOR", "ADMIN");
        Set<String> result = new LinkedHashSet<>();

        for (String scope : scopes) {
            if (scope != null && !scope.isBlank()) {
                result.add("SCOPE_" + scope);
            }
        }
        for (String role : trustedCanonicalRoles) {
            if (allowlisted.contains(role)) {
                result.add("ROLE_" + role);
            }
        }
        return new Principal(subject, Set.copyOf(result));
    }

    static boolean hasAuthority(Principal principal, String exact) {
        return principal.authorities().contains(exact);
    }

    static boolean hasRole(Principal principal, String role) {
        return hasAuthority(principal, "ROLE_" + role);
    }

    private static void show(String label, Principal principal) {
        System.out.println(label
                + ": read=" + hasAuthority(
                    principal, "SCOPE_documents.read")
                + ", admin=" + hasRole(principal, "ADMIN")
                + ", bare=" + hasAuthority(
                    principal, "documents.read"));
    }

    public static void main(String[] args) {
        show("alice", mapped("alice",
                List.of("documents.read"), List.of("USER")));
        show("bob", mapped("bob",
                List.of("documents.read"), List.of("ADMIN")));
        show("bot", mapped("bot",
                List.of("ADMIN"), List.of()));
        show("unknown", mapped("eve",
                List.of("documents.read"),
                List.of("ROLE_ADMIN", "OTHER")));
    }
}
```

Chạy:

```bash
javac ScopeRoleSemanticsLab.java
java ScopeRoleSemanticsLab
```

Stdout dự kiến:

```text
alice: read=true, admin=false, bare=false
bob: read=true, admin=true, bare=false
bot: read=false, admin=false, bare=false
unknown: read=true, admin=false, bare=false
```

- Alice có scope đọc, nhưng không có ADMIN role.
- Bob có scope đọc và canonical ADMIN role, nên cả hai kiểm tra thành công.
- Bot có **scope tên ADMIN**, nhưng không có `ROLE_ADMIN`.
- Claim role `ROLE_ADMIN` được coi là sai vocabulary canonical, không tự tạo `ROLE_ROLE_ADMIN` hay “sửa” thành admin.
- Hàm `mapped` chỉ dành cho học thuật. Production không lấy scopes/roles chưa verify từ client rồi gọi hàm này; mọi giá trị phải xuất phát từ trusted authentication/authorization boundary.

## 9. Converter Spring Security: giữ scopes và roles ở hai namespace

Spring Security 6.x cung cấp `JwtGrantedAuthoritiesConverter`, `DelegatingJwtGrantedAuthoritiesConverter` và `JwtAuthenticationConverter`. Ta dùng một converter mặc định cho scopes và một converter riêng cho role claim đã chuẩn hóa.

Tệp `JwtAuthorityConfiguration.java`:

```java
package example.auth;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.DelegatingJwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Configuration
public class JwtAuthorityConfiguration {

    private static final Set<String> ALLOWED_ROLES =
            Set.of("USER", "AUDITOR", "ADMIN");

    @Bean
    public JwtAuthenticationConverter jwtAuthenticationConverter() {
        // Không sửa prefix: JWT scope/scp -> SCOPE_...
        JwtGrantedAuthoritiesConverter scopes =
                new JwtGrantedAuthoritiesConverter();

        Converter<Jwt, Collection<GrantedAuthority>> roles =
                JwtAuthorityConfiguration::rolesFromTrustedClaim;

        DelegatingJwtGrantedAuthoritiesConverter combined =
                new DelegatingJwtGrantedAuthoritiesConverter(
                        scopes, roles);

        JwtAuthenticationConverter converter =
                new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(combined);
        return converter;
    }

    private static Collection<GrantedAuthority>
            rolesFromTrustedClaim(Jwt jwt) {

        Object raw = jwt.getClaims().get("app_roles");
        if (!(raw instanceof List<?> values)) {
            return List.of();
        }

        Set<GrantedAuthority> authorities =
                new LinkedHashSet<>();

        for (Object item : values) {
            if (item instanceof String role
                    && ALLOWED_ROLES.contains(role)) {
                authorities.add(
                        new SimpleGrantedAuthority("ROLE_" + role));
            }
        }
        return List.copyOf(authorities);
    }
}
```

Đây là một **file Java cấu hình hoàn chỉnh**, nhưng nó giả định `JwtDecoder` phía Resource Server đã kiểm tra token. `ALLOWED_ROLES` chỉ kiểm tra **tên role**, không phải chữ ký hay tính authoritative của issuer. Claim `app_roles` phải là claim được issuer quản trị, không phải user-editable metadata hoặc header do client đặt.

Hành vi quan trọng:

- `scope="documents.read"` → `SCOPE_documents.read`.
- `app_roles=["ADMIN"]` → `ROLE_ADMIN`.
- `scope="ADMIN"` → `SCOPE_ADMIN`, không tự thành `ROLE_ADMIN`.
- `app_roles=["ROLE_ADMIN"]` → **không cấp role ADMIN** do không thuộc allowlist unprefixed.
- `app_roles=["admin"]` → **không cấp** nếu contract yêu cầu uppercase.
- `app_roles` vắng mặt/sai kiểu → không cấp roles.
- Một token có thể có **cả** scope authorities lẫn role authorities.
- Unknown roles bị bỏ qua, nhưng không thể dùng việc “đã bỏ qua” làm bằng chứng token hợp lệ về cryptography.

### Nested role claims

Nếu IdP dùng:

```json
{
  "realm_access": {
    "roles": ["administrator", "reader"]
  }
}
```

đừng giả định `setAuthoritiesClaimName("realm_access.roles")` tự hiểu nested JSON path theo mọi version. Viết converter kiểm tra types:

```java
Object root = jwt.getClaims().get("realm_access");
if (root instanceof java.util.Map<?, ?> data) {
    Object roles = data.get("roles");
    if (roles instanceof List<?> values) {
        // Validate issuer contract + role allowlist.
    }
}
```

Đây là snippet tích hợp. Với nhiều issuers hoặc clients, role `administrator` có thể mang ý nghĩa khác nhau; mapping phải theo đúng trusted issuer/audience và resource server.

## 10. Cấu hình HttpSecurity: role trong HTTP, scope ở method

Tệp `ApiSecurityConfiguration.java`:

```java
package example.auth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class ApiSecurityConfiguration {

    @Bean
    public SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            JwtAuthenticationConverter converter) throws Exception {

        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(
                        HttpMethod.GET, "/api/http/admin")
                .hasRole("ADMIN")
                .requestMatchers(
                        HttpMethod.GET, "/api/**")
                .authenticated()
                .anyRequest().denyAll());

        http.oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt.jwtAuthenticationConverter(
                        converter)));

        return http.build();
    }
}
```

Với cấu hình này:

- `GET /api/http/admin` được bảo vệ trực tiếp bằng HTTP `hasRole("ADMIN")`.
- Các GET `/api/**` khác chỉ yêu cầu authenticated ở HTTP; do đó test 403 của service `@PreAuthorize` có thể chứng minh **method security** thật sự hoạt động.
- `@EnableMethodSecurity` bật các method-level annotations cho Spring-managed beans.
- `JwtAuthenticationConverter` được inject vào Resource Server, bảo đảm token đi qua mapper scopes và roles.
- Thứ tự matchers có ý nghĩa; rule cụ thể phải đi trước rule `/api/**`.
- `anyRequest().denyAll()` chặn các HTTP routes chưa được cấp chính sách.

Cấu hình ví dụ chỉ bảo vệ GET endpoints và không có browser-cookie workflow. Nếu thêm POST/PUT/DELETE hoặc session/cookie authentication, phải xét CSRF và session policy phù hợp. Không biến “REST API” thành lý do tắt CSRF cho mọi thiết kế.

## 11. Method security: scope đọc và role quản trị

Service theo mô hình học tập:

```java
@Service
class DocumentService {

    @PreAuthorize("hasAuthority('SCOPE_documents.read')")
    public String read(String documentId) {
        return "doc:" + documentId;
    }
}

@Service
class AdminService {

    @PreAuthorize("hasRole('ADMIN')")
    public String status() {
        return "admin-ok";
    }
}
```

Đây là đoạn source sẽ nằm trong file `DemoController.java` của project dưới đây; không tạo thêm file trùng class nếu bạn copy project.

Với Service dùng `@PreAuthorize`, Spring AOP proxy phải được gọi. Nếu một method trong cùng bean gọi `this.protectedMethod()`, advice có thể bị bỏ qua. Nếu controller tự `new DocumentService()`, object đó không được Spring proxy.

**Không dùng `hasRole('ADMIN')` thay scope read để “giúp admin đọc được” nếu business policy không cho phép bypass client-scoped permissions.** Một user có ADMIN role nhưng token thiếu `SCOPE_documents.read` vẫn phải bị chặn bởi scope policy.

Ngoài ra, method này chỉ trả text minh họa. Ở production phải kiểm tra document owner/tenant/ACL và query có điều kiện tenant; `SCOPE_documents.read` chỉ chứng minh token có quyền **gọi loại chức năng đọc**.

## 12. Project Maven Java 17 chạy thử cả converter và HTTP/method guards

Project dùng Spring Boot 3.5.16 (Spring Security 6.x do BOM quản lý), Java 17, Spring MVC Servlet Resource Server và JUnit 5. Release 3.5.16 có thật, nhưng đây là nhánh Boot đã kết thúc OSS support; production mới nên dùng một nhánh còn được hỗ trợ. Project là **ví dụ học tập**, không phải code triển khai production.

Cấu trúc:

```text
oauth-scope-role-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/auth/
    │   │   ├── ScopeRoleLabApplication.java
    │   │   ├── JwtAuthorityConfiguration.java
    │   │   ├── ApiSecurityConfiguration.java
    │   │   └── DemoController.java
    │   └── resources/application.yml
    └── test/
        └── java/example/auth/
            └── ScopeRoleLabTest.java
```

Hai tệp `JwtAuthorityConfiguration.java` và `ApiSecurityConfiguration.java` đã được trình bày đầy đủ ở mục 9–10. Không tạo thêm bản sao hai class đó.

### 12.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>oauth-scope-role-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### 12.2. application.yml

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/realms/documents
          audiences:
            - api://documents
```

URI/issuer/audience là **giá trị ví dụ**, chưa phải IdP thật. Để chạy server thực, thay bằng issuer thật, cấu hình key/JWKS, audience, time validators và scope claim contract. Trong integration tests bên dưới, một `JwtDecoder` test-only được tạo để kiểm tra converter/guards mà không cần network; nó **không kiểm chứng chữ ký JWT thật**.

### 12.3. ScopeRoleLabApplication.java

```java
package example.auth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ScopeRoleLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ScopeRoleLabApplication.class, args);
    }
}
```

### 12.4. DemoController.java

```java
package example.auth;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class DemoController {

    private final DocumentService documents;
    private final AdminService admins;

    public DemoController(
            DocumentService documents,
            AdminService admins) {
        this.documents = documents;
        this.admins = admins;
    }

    @GetMapping("/documents/{id}")
    public String document(@PathVariable String id) {
        return documents.read(id);
    }

    @GetMapping("/method/admin")
    public String methodAdmin() {
        return admins.status();
    }

    @GetMapping("/http/admin")
    public String httpAdmin() {
        return "http-admin-ok";
    }
}

@Service
class DocumentService {

    @PreAuthorize("hasAuthority('SCOPE_documents.read')")
    public String read(String id) {
        return "doc:" + id;
    }
}

@Service
class AdminService {

    @PreAuthorize("hasRole('ADMIN')")
    public String status() {
        return "admin-ok";
    }
}
```

Các service là Spring-managed beans và được constructor-inject vào controller, nên `@PreAuthorize` có thể được áp dụng qua AOP proxies. Route `/api/http/admin` có HTTP `hasRole("ADMIN")`, còn route `/api/method/admin` chỉ yêu cầu authenticated ở HTTP và sử dụng method security để chặn role thiếu.

### 12.5. ScopeRoleLabTest.java

```java
package example.auth;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@Import(ScopeRoleLabTest.StubJwtDecoderConfig.class)
class ScopeRoleLabTest {

    @Autowired MockMvc mvc;
    @Autowired JwtAuthenticationConverter converter;

    @Test
    void scopeReaderCanRead() throws Exception {
        mvc.perform(get("/api/documents/42")
                    .header(HttpHeaders.AUTHORIZATION, "Bearer reader"))
           .andExpect(status().isOk())
           .andExpect(content().string("doc:42"));
    }

    @Test
    void adminWithoutReadScopeCannotRead() throws Exception {
        mvc.perform(get("/api/documents/42")
                    .header(HttpHeaders.AUTHORIZATION, "Bearer admin"))
           .andExpect(status().isForbidden());
    }

    @Test
    void scopeReaderIsNotAdmin() throws Exception {
        mvc.perform(get("/api/method/admin")
                    .header(HttpHeaders.AUTHORIZATION, "Bearer reader"))
           .andExpect(status().isForbidden());
    }

    @Test
    void canonicalAdminCanUseMethodGuard() throws Exception {
        mvc.perform(get("/api/method/admin")
                    .header(HttpHeaders.AUTHORIZATION, "Bearer admin"))
           .andExpect(status().isOk())
           .andExpect(content().string("admin-ok"));
    }

    @Test
    void canonicalAdminCanUseHttpGuard() throws Exception {
        mvc.perform(get("/api/http/admin")
                    .header(HttpHeaders.AUTHORIZATION, "Bearer admin"))
           .andExpect(status().isOk())
           .andExpect(content().string("http-admin-ok"));
    }

    @Test
    void scopeNamedAdminIsNotAdminRole() throws Exception {
        mvc.perform(get("/api/http/admin")
                    .header(HttpHeaders.AUTHORIZATION, "Bearer scope-admin"))
           .andExpect(status().isForbidden());
    }

    @Test
    void wrongRoleVocabularyCannotEscalate() throws Exception {
        mvc.perform(get("/api/method/admin")
                    .header(HttpHeaders.AUTHORIZATION, "Bearer bad-role"))
           .andExpect(status().isForbidden());
    }

    @Test
    void missingTokenIsUnauthenticated() throws Exception {
        mvc.perform(get("/api/documents/42"))
           .andExpect(status().isUnauthorized());
    }

    @Test
    void converterDoesNotMixNamespaces() {
        Jwt jwt = StubJwtDecoderConfig.jwt(
                "unit", "alice", "documents.read",
                List.of("ADMIN", "UNLISTED", "ROLE_ADMIN"));

        Set<String> values = converter.convert(jwt)
                .getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .collect(Collectors.toSet());

        assertTrue(values.contains("SCOPE_documents.read"));
        assertTrue(values.contains("ROLE_ADMIN"));
        assertFalse(values.contains("SCOPE_ADMIN"));
        assertFalse(values.contains("ROLE_ROLE_ADMIN"));
        assertFalse(values.contains("ROLE_UNLISTED"));
    }

    @TestConfiguration
    static class StubJwtDecoderConfig {

        @Bean
        @Primary
        JwtDecoder stubDecoder() {
            return token -> switch (token) {
                case "reader" -> jwt(
                        token, "alice", "documents.read",
                        List.of("USER"));
                case "admin" -> jwt(
                        token, "alice", null,
                        List.of("ADMIN"));
                case "scope-admin" -> jwt(
                        token, "alice", "ADMIN",
                        List.of());
                case "bad-role" -> jwt(
                        token, "alice", "documents.read",
                        List.of("ROLE_ADMIN", "UNLISTED"));
                default -> throw new BadJwtException(
                        "Unknown test token");
            };
        }

        static Jwt jwt(String token, String subject,
                       String scope, List<String> roles) {
            Jwt.Builder builder = Jwt.withTokenValue(token)
                    .header("alg", "RS256")
                    .claim("sub", subject)
                    .claim("app_roles", roles);
            if (scope != null) {
                builder.claim("scope", scope);
            }
            return builder.build();
        }
    }
}
```

**Tại sao dùng stub JwtDecoder?** Để request HTTP thật sự đi qua `BearerTokenAuthenticationFilter`, `JwtAuthenticationConverter` và method/HTTP guards, nhưng không gọi IdP ngoài. Stub token “reader” không phải JWT có chữ ký; nó chỉ được chấp nhận trong test context. **Không copy stub decoder sang production.** Test thực về signature/issuer/audience cần một suite riêng với ký số và `JwtDecoder` thực.

Chạy:

```bash
java -version
mvn -version
mvn -q clean test
```

Dự kiến có **chín phép thử JUnit 5**: scope reader được đọc; role admin không thay scope; scope không thay role; method/HTTP hasRole đồng ý khi có ROLE_ADMIN; scope ADMIN không thành role; raw roles lỗi không được nâng quyền; request không token nhận 401; converter tạo authorities đúng. Output của Maven phụ thuộc môi trường, nên không bịa stdout Maven.

**Giới hạn của ví dụ:** chưa triển khai data repository/tenant, chưa test cryptographic JWT validation và không minh họa authorization server. Chỉ áp dụng làm nền tảng học cơ chế ánh xạ và kiểm tra authorities.

## 13. Vì sao cần test converter riêng bên cạnh HTTP tests?

Có nhiều cách tạo authentication giả khi test, và không phải cách nào cũng chạy qua converter thực.

```java
mvc.perform(get("/api/documents/42")
        .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_documents.read"))))
   .andExpect(status().isOk());
```

Đây là **snippet Spring Security Test**. `jwt()` request postprocessor thường tạo một test authentication, có thể bypass `JwtDecoder` và converter từ Resource Server cấu hình. Nó rất hữu ích để test HTTP authorization, nhưng **không chứng minh issuer-token roles mapping**.

Tương tự `@WithMockUser(roles = "ADMIN")` tạo `ROLE_ADMIN` cho test, không chứng minh một JWT thật mang role ADMIN sẽ chuyển được thành authority này. Cần các tầng:

1. **Converter unit test:** với JWT test object, assert scope/role authorities chính xác.
2. **Filter/method integration test:** với test decoder, assert 200/403/401 qua request thật.
3. **Decoder cryptography test:** với signed JWT test key, sai signature/issuer/audience/expiry phải bị chặn.
4. **Object authorization test:** dù scope/role hợp lệ vẫn không đọc resource khác owner/tenant.

Trong các tests nhánh DENY, kiểm tra không chỉ status mà cả **không có side effect** khi API thực hiện ghi; HTTP 403 sau một cập nhật DB là không đạt an toàn.

## 14. Vai trò thuộc tenant không phải ROLE_ADMIN global

Một user có quyền OWNER ở tenant alpha không tự có quyền ADMIN trên toàn platform.

```json
{
  "sub": "alice",
  "scope": "documents.read",
  "tenant": "alpha",
  "tenant_role": "OWNER"
}
```

Nếu app ánh xạ `tenant_role=OWNER` thành một global authority `ROLE_ADMIN` không gắn tenant, caller có thể vượt phạm vi khi truy cập beta.

Một policy đầy đủ hơn:

```text
ALLOW document READ
  = authenticated
  AND hasAuthority("SCOPE_documents.read")
  AND activeMembership(subject, authorizedTenant)
  AND resource.tenantId == authorizedTenant
  AND (isOwner(subject, resource) OR isShared(subject, resource))
```

Nếu cần tenant-specific admin, dùng service policy `tenantPolicy.isAdmin(auth, tenant)` hoặc canonical tenant-bound authorities được kiểm tra theo resource tenant, chứ không chỉ `hasRole('ADMIN')` toàn cục.

SQL phải ràng buộc tenant:

```sql
SELECT id, title
FROM documents
WHERE id = :document_id
  AND tenant_id = :authorized_tenant;
```

`hasAuthority('SCOPE_documents.read')` chỉ cho phép chức năng đọc theo token; **không thêm WHERE clause**, không chứng minh record 42 thuộc tenant alpha. Đây là sự tách biệt giữa function-level và object-level authorization.

## 15. OAuth2 Client, OIDC login và opaque token không giống JWT Resource Server

Các thành phần Spring Security có thể xây `Authentication` khác nhau:

| Tình huống | Cơ chế | Điều cần kiểm tra |
| --- | --- | --- |
| JWT Resource Server | `JwtDecoder`, `JwtAuthenticationConverter` | Scopes thường thành `SCOPE_`, roles cần mapping |
| Opaque Resource Server | Introspection + authenticated principal | Scopes từ introspection thường thành `SCOPE_`, role mapping tùy policy |
| OAuth2 Login | `OAuth2AuthenticationToken`/`OAuth2User` | Authorities có thể gồm `OAUTH2_USER` và mapped authorities |
| OIDC Login | `OidcUser` / authentication | Không mặc định mọi ID token role là API bearer authority |
| In-memory user | `UserDetailsService` | `roles("ADMIN")` tạo `ROLE_ADMIN`, nhưng không chứng minh JWT converter |
| Mock principal trong test | `@WithMockUser` | Authorities do test tự đặt |

Không giả định người dùng đăng nhập bằng OIDC sẽ có cùng `SCOPE_...` và `ROLE_...` như một resource server JWT. Nếu project kết hợp OAuth2 client và resource server, kiểm tra request filter chain và Authentication type trước khi viết expression.

Với opaque token, introspection phải được thực hiện qua endpoint tin cậy và scope/role mapping cũng phải có contract. Khi introspection timeout, hệ thống phải fail closed, không cấp scope/role giả.

## 16. WebFlux: cùng khái niệm, khác security DSL

WebFlux sử dụng `ServerHttpSecurity`/`SecurityWebFilterChain`, reactive authentication và `ReactiveSecurityContextHolder`. Nhưng tên authority vẫn có thể là `SCOPE_documents.read` và `ROLE_ADMIN`.

Mẫu reactive HTTP configuration:

```java
@Bean
SecurityWebFilterChain reactiveSecurity(
        ServerHttpSecurity http,
        Converter<Jwt, Mono<AbstractAuthenticationToken>> converter) {

    return http.authorizeExchange(exchanges -> exchanges
            .pathMatchers(HttpMethod.GET, "/api/documents/**")
            .hasAuthority("SCOPE_documents.read")
            .pathMatchers(HttpMethod.GET, "/api/admin/**")
            .hasRole("ADMIN")
            .anyExchange().denyAll())
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(
                jwt -> jwt.jwtAuthenticationConverter(converter)))
        .build();
}
```

Đây là **snippet tích hợp**, không thuộc project MVC phía trên. Cần imports reactive Spring Security, Reactor và `Converter`. Có thể dùng `ReactiveJwtAuthenticationConverterAdapter` để bọc `JwtAuthenticationConverter` đồng bộ cho WebFlux, hoặc tự viết reactive converter phù hợp.

Reactive method security:

```java
@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodConfig {
}

@Service
class ReactiveDocumentService {

    @PreAuthorize("hasAuthority('SCOPE_documents.read')")
    public Mono<String> read(String id) {
        return Mono.just("doc:" + id);
    }

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> admin() {
        return Mono.just("admin-ok");
    }
}
```

Spring-managed bean và Reactor Context phải đúng. Không đọc thread-local `SecurityContextHolder` rồi coi đó là identity hiện tại trên worker thread; không gọi `block()` trong event-loop để “kiểm tra role trước”.

## 17. hasAnyRole, role hierarchy và thay đổi prefix

`hasAnyRole('AUDITOR','ADMIN')` kiểm tra một trong các roles; `hasAnyAuthority('SCOPE_a','SCOPE_b')` kiểm tra một trong các authorities. Hai phương thức đều có thể phục vụ business policy, nhưng **chọn OR hay AND là quyết định bảo mật**, không phải chi tiết cú pháp.

Ví dụ:

```java
@PreAuthorize(
    "hasAuthority('SCOPE_reports.export') " +
    "and hasAnyRole('ADMIN','AUDITOR')")
```

Token phải có export scope và một trong hai roles. Nếu chỉ có scope READ, không được xuất. Nếu chỉ có role ADMIN nhưng token thiếu export scope, cũng không được xuất.

Spring Security hỗ trợ `RoleHierarchy`, ví dụ `ROLE_ADMIN > ROLE_AUDITOR`. Khi hierarchy được đưa vào đúng manager/expression handler, ADMIN có thể thỏa AUDITOR. Nhưng hierarchy **không tự biến ROLE_ADMIN thành mọi SCOPE_***; nếu cần quyền vượt scopes phải có policy đặc biệt đã được phê duyệt.

Một ví dụ `GrantedAuthorityDefaults`:

```java
@Bean
static GrantedAuthorityDefaults grantedAuthorityDefaults() {
    return new GrantedAuthorityDefaults("ROLE_");
}
```

Bean này minh họa role prefix mặc định trong method security. Khi thay `ROLE_` sang chuỗi khác, phải sửa converter cùng lúc và test các HTTP/method authorization managers. Trong Spring Security 7.x, một số managers sử dụng `AuthorizationManagerFactory` để cấu hình role prefix; không suy đoán một customization duy nhất sẽ tác động mọi lớp/version.

## 18. Trường hợp nhiều issuers và clients: tránh role collision

Cùng claim `app_roles=["ADMIN"]` có thể xuất hiện ở nhiều issuers:

- Issuer A: `ADMIN` nghĩa là quản trị docs platform.
- Issuer B: `ADMIN` nghĩa là quản trị portal riêng của đối tác.
- Token client credentials có `ADMIN` trong metadata nhưng không đại diện end user.

Nếu không ràng buộc issuer/audience/client trust, ứng dụng có thể cấp `ROLE_ADMIN` cho caller không đúng phạm vi. Với multi-issuer:

1. Chỉ chấp nhận issuers trong allowlist.
2. Kiểm tra issuer thật qua JWT decoder phù hợp trước khi đọc roles.
3. Xác minh audience của API này.
4. Có mapping role riêng theo trusted issuer/application.
5. Phân biệt `(issuer, subject)` khi chuyển thành internal principal.
6. Nếu quyền là tenant-local, không map thành global role.
7. Đặt expiry/revocation SLA cho role/membership.
8. Test cùng `sub` từ hai issuers khác nhau.

Không dùng `X-Tenant-Id`, `X-Role` hay query parameter để tăng quyền. Một token được ký hợp lệ nhưng roles do user tự chỉnh trong IdP profile cũng có thể không được coi là authority mạnh; nguồn claim phải có chính sách quản trị phù hợp.

## 19. Lỗi thường gặp và cách xử lý

| Vấn đề | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| JWT scope READ, hasRole READ trả 403 | Role tìm `ROLE_READ` | Dùng `hasAuthority('SCOPE_documents.read')` |
| JWT scope READ, hasAuthority bare read trả 403 | Converter đã thêm `SCOPE_` | Dùng tên authority đầy đủ |
| JWT app_roles ADMIN, hasRole ADMIN trả 403 | Role claim chưa được map | Cấu hình trusted role converter |
| Role bị `ROLE_ROLE_ADMIN` | Double prefix | Canonical role input chỉ chứa `ADMIN` |
| Scope bị `ROLE_documents.read` | Converter prefix cho scopes bị đổi | Giữ `SCOPE_`, tạo role converter riêng |
| JWT có `SCOPE_ADMIN`, hasRole ADMIN vẫn false | Scope khác role | Đây là hành vi đúng; không tự nâng quyền |
| HTTP cho qua nhưng method 403 | Method guard yêu cầu scope/role khác | Test từng layer |
| Converter test xanh nhưng token thật 401 | JWT signature/issuer/audience fail | Kiểm tra decoder/token |
| Test @WithMockUser ADMIN xanh, JWT ADMIN fail | Mock bypass converter | Unit test JWT converter + integration |
| Admin tenant alpha đọc được beta | Global role thiếu tenant isolation | Policy membership/resource tenant |
| Token scope missing | Không có `scope`/`scp` đúng contract | Kiểm tra issuer schema |
| Token role nested claim | Converter không đọc nested map | Viết converter type-safe |
| Unknown role thành admin | Fuzzy mapping, auto-uppercase | Allowlist và mapping bảng chính thức |
| Token vừa revoke vẫn có role | JWT/cache chưa hết hạn | TTL, introspection, entitlement revision |

Để chẩn đoán 403, kiểm tra theo thứ tự: token đã authenticated? Token có đúng audience? Authentication type là gì? `getAuthorities()` thực tế chứa gì? Converter có đúng claim name/prefix? HTTP hay method guard nào từ chối? Có object/tenant policy nào thêm không?

Không khắc phục 403 bằng cách chèn `permitAll()`, `or hasRole('ADMIN')` hoặc bỏ `@PreAuthorize` khi chưa xác định vì sao authority bị thiếu.

## 20. Bộ test khuyến nghị

| Tình huống | Kỳ vọng |
| --- | --- |
| JWT scope documents.read | `SCOPE_documents.read` được cấp |
| JWT scope documents.write | Không tự có scope read |
| JWT app_roles ADMIN | `ROLE_ADMIN` được cấp theo contract |
| Role ADMIN không có read scope | Document read bị DENY |
| Read scope không có ADMIN role | Admin method bị DENY |
| Token scope tên ADMIN | Không tự có `ROLE_ADMIN` |
| app_roles chứa ROLE_ADMIN (raw prefix) | Không cấp `ROLE_ROLE_ADMIN` |
| app_roles unknown | Không cấp role lạ |
| app_roles sai kiểu/null | Không cấp role |
| Token không scope/role | Protected route/method DENY |
| Unauthenticated | 401 |
| Token signature sai | 401/invalid token |
| Token issuer sai | 401 |
| Token audience sai | 401 |
| Token hết hạn | 401 |
| Trusted role không thuộc tenant | Object/tenant policy DENY |
| Scope READ cho document khác owner | Object policy DENY |
| Role hierarchy ADMIN>AUDITOR | Kiểm tra đúng manager đã config |
| User có role nhưng method được gọi bằng self-invocation | Test phát hiện proxy bypass |
| Mỗi issuer có ADMIN khác nghĩa | Không có privilege collision |
| Cached authority sau revocation | Không vượt revocation SLA |

Chú ý rằng tests ở project chỉ cover scope/role mapper + HTTP/method guard. Cần thêm decoder cryptography tests với signed test JWT, database tenant/object tests và regression tests sau khi nâng Spring Security/BOM.

## 21. Checklist áp dụng

- [ ] Phân biệt OAuth2 scope, business role, GrantedAuthority và object permission.
- [ ] `JwtDecoder` xác minh signature, issuer, audience, expiry/nbf và token purpose.
- [ ] Scope mặc định sử dụng prefix `SCOPE_`, expressions dùng đúng exact authority.
- [ ] Vai trò được lấy từ **issuer-controlled claim** theo hợp đồng, không lấy từ client input.
- [ ] Role mapper có allowlist/normalization rõ, thêm prefix `ROLE_` đúng một lần.
- [ ] Không dùng cùng một converter prefix ROLE_ cho cả OAuth scopes nếu vẫn muốn scope namespace.
- [ ] `hasRole('ADMIN')` chỉ dùng cho roles chuẩn hóa đúng semantics.
- [ ] `hasAuthority('SCOPE_x')` cho OAuth2 scopes, không dùng `hasRole('x')` thay thế.
- [ ] AND/OR giữa scope và role là policy có chủ đích, không “vá” 403.
- [ ] HTTP SecurityFilterChain và method security bật đúng và test riêng.
- [ ] RoleHierarchy/custom prefix được kiểm chứng trên đúng manager/version.
- [ ] Tenant/owner/ACL/resource state được kiểm tra ở service/repository.
- [ ] Không dùng global ROLE_ADMIN cho role chỉ thuộc một tenant.
- [ ] Positive authorization cache có TTL và revocation/invalidation strategy.
- [ ] Unit test converter, negative HTTP/method tests và signed JWT decoder tests đầy đủ.
- [ ] Test không dùng mock authorities để khẳng định cryptographic validation.
- [ ] Error/audit logs không chứa raw JWT, client secrets hoặc PII không cần thiết.

**Kết luận:** `hasAuthority` và `hasRole` đều xem GrantedAuthorities, nhưng diễn đạt hai nguồn quyền khác nhau. Với Spring Security OAuth2 Resource Server mặc định, scope `documents.read` thành `SCOPE_documents.read` và được kiểm tra qua `hasAuthority('SCOPE_documents.read')`. Role ứng dụng `ADMIN` cần được **xác minh, chuẩn hóa và map** thành `ROLE_ADMIN` trước khi `hasRole('ADMIN')` có ý nghĩa. Không tự chuyển scope thành role, không cho role bỏ qua client scope, và không xem cả hai là đủ để bỏ qua tenant/object authorization.

## Tài liệu chính thức

- [Spring Security 6.5 — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security 6.5 — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — JwtAuthenticationConverter JavaDoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html)
- [Spring Security — GrantedAuthorityDefaults JavaDoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/core/GrantedAuthorityDefaults.html)
- [Spring Boot 3.5.16 release](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)
