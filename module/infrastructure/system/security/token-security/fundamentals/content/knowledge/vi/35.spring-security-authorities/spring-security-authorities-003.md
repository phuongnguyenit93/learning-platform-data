# ROLE_ prefix và khác biệt với scope

Trong **Spring Security**, một principal sau khi được xác thực có thể có danh sách các **`GrantedAuthority`**. Những giá trị thường gặp là **`ROLE_ADMIN`**, **`ROLE_USER`**, **`SCOPE_orders:read`** hoặc **`SCOPE_profile`**. Dù tất cả đều được Spring biểu diễn như **chuỗi authority**, chúng **không mang cùng ý nghĩa**:

- **`ROLE_`** là **quy ước prefix cho vai trò** trong Spring Security. Ví dụ `hasRole("ADMIN")` thường kiểm tra authority **`ROLE_ADMIN`**.
- **`SCOPE_`** là **prefix mặc định** do một số converter OAuth2 Resource Server của Spring Security thêm vào **OAuth access-token scopes**. Ví dụ access token có `scope=orders:read` có thể được đổi thành authority **`SCOPE_orders:read`**.
- **OAuth scope** là phạm vi quyền mà Authorization Server (AS) cấp cho **client/access token** theo OAuth grant; scope **không phải role của user** và không tự nói user có quyền trên mọi bản ghi.
- **Authority** là cách Spring Security đưa những bằng chứng quyền đã được hệ thống xác minh vào **`Authentication`** để sử dụng khi phân quyền URL, method hay object.

Bài **“ROLE_ prefix và khác biệt với scope”** thuộc chương **Spring Security authorities** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Bài liên hệ mô hình tin cậy/vòng đời token, JWT và opaque token, access/refresh/ID token, claims, scope, audience, OAuth 2.0/OIDC, phát hành, xác minh, lưu trữ và thu hồi token cùng chống token bị đánh cắp hoặc phát lại.

> **Nhớ nhanh:** `hasRole("ADMIN")` nhìn theo mặc định vào **`ROLE_ADMIN`**, còn `hasAuthority("SCOPE_orders:read")` so **đúng authority string**. **Không** tự biến `SCOPE_orders:read` thành `ROLE_ADMIN`, **không** dùng `ROLE_ADMIN` thay kiểm tra `aud`/`iss`/`exp` của JWT, và **không** lấy role từ header do client tự đặt.

## 1. Bốn tầng: token → identity → authorities → authorization

Một API Spring Security dùng OAuth 2.0 Resource Server thường có các bước:

~~~mermaid
flowchart TD
    A["HTTP request + Bearer access token"] --> B["Authentication filter / provider"]
    B --> C{"JWT verify hoặc opaque introspection?"}
    C -->|"Invalid / missing"| D["401 + Bearer challenge"]
    C -->|"Trusted access token"| E["Xác minh issuer, audience, type, time, sender binding"]
    E -->|"Sai"| D
    E -->|"Đúng"| F["JwtAuthenticationConverter / trusted mapping"]
    F --> G["GrantedAuthority: SCOPE_orders:read, ROLE_SUPPORT ..."]
    G --> H{"Route/method checks?"}
    H -->|"Thiếu scope/authority"| I["403 Forbidden"]
    H -->|"Qua"| J{"Tenant + object-level policy?"}
    J -->|"Không"| K["403 hoặc 404 theo privacy policy"]
    J -->|"Có"| L["Business operation"]
~~~

**Thứ tự có ý nghĩa**: Spring không nên dùng một giá trị `ROLE_ADMIN` lấy từ JWT **chưa xác minh chữ ký** để quyết định quyền. Một token có chữ ký hợp lệ nhưng **sai audience** vẫn không phải access token được Resource Server hiện tại chấp nhận.

### Phân biệt ba câu hỏi

| Tầng | Câu hỏi | Ví dụ |
|---|---|---|
| **Authentication / token validation** | Credential này có hợp lệ cho **Orders API** không? | `iss`, `aud`, `typ`, `exp`, chữ ký hoặc `active:true` |
| **Authority mapping** | Credential đáng tin mang scope/role nào theo **contract**? | `orders:read` → `SCOPE_orders:read`; app role `ADMIN` → `ROLE_ADMIN` nếu có mapping được phê duyệt |
| **Authorization** | Request này có được phép thực hiện trên đối tượng này không? | `hasAuthority`, `hasRole`, tenant/owner, ABAC, transaction rules |

Một API có thể **xác thực thành công** nhưng **từ chối phân quyền**. Đó là lý do thường thấy **401** khi token invalid và **403** khi token hợp lệ nhưng thiếu quyền.

## 2. `GrantedAuthority` là gì?

Trong Spring Security, `GrantedAuthority` là interface thể hiện một quyền/authority gắn với `Authentication`. Một implementation thường dùng là `SimpleGrantedAuthority`, chứa **chuỗi authority**.

~~~java
import java.util.List;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public final class AuthorityStringsDemo {
    public static void main(String[] args) {
        List<GrantedAuthority> authorities = List.of(
                new SimpleGrantedAuthority("ROLE_ADMIN"),
                new SimpleGrantedAuthority("SCOPE_orders:read"),
                new SimpleGrantedAuthority("orders:export")
        );

        for (GrantedAuthority authority : authorities) {
            System.out.println(authority.getAuthority());
        }
        // ROLE_ADMIN
        // SCOPE_orders:read
        // orders:export
    }

    private AuthorityStringsDemo() {}
}
~~~

**Spring không kiểm tra nguồn gốc của `SimpleGrantedAuthority` chỉ từ chuỗi.** Bạn có thể tạo `new SimpleGrantedAuthority("ROLE_ADMIN")` bằng Java, nhưng việc đó **không chứng minh user thực sự là admin**; bằng chứng phải đến từ **UserDetailsService**, chính sách identity nội bộ hoặc **AS claims đã xác minh và được cho phép map**.

`Authentication.getAuthorities()` trả về các authority mà hệ thống dùng để kiểm tra quyền. Không nên nghĩ rằng **mọi string đều là role**, hoặc **mọi authority bắt đầu bằng `SCOPE_` đều chắc chắn được cấp qua OAuth** nếu converter của ứng dụng tự tạo chuỗi đó từ nguồn không đáng tin.

## 3. `ROLE_` là convention của Spring, không phải OAuth claim chuẩn

Theo quy ước mặc định của nhiều cơ chế Spring Security:

~~~text
Spring expression: hasRole("ADMIN")
                ↓ thêm default role prefix
GrantedAuthority required: "ROLE_ADMIN"

Spring expression: hasRole("USER")
                ↓
GrantedAuthority required: "ROLE_USER"
~~~

**`ROLE_` không phải từ khóa bắt buộc trong RFC 6749, RFC 9068 hay OIDC Core**. Đây là **tên authority** dùng bởi Spring security expressions và một số authorization managers.

Ví dụ:

~~~java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public final class RoleAuthorityDemo {
    public static void main(String[] args) {
        var admin = new SimpleGrantedAuthority("ROLE_ADMIN");
        var support = new SimpleGrantedAuthority("ROLE_SUPPORT");
        System.out.println(admin.getAuthority());
        System.out.println(support.getAuthority());
    }

    private RoleAuthorityDemo() {}
}
~~~

Các prefix như `ROLE_` và `SCOPE_` **không phải bằng chứng mật mã**, và Spring **không tự liên hệ** chúng với database role tables hay AS policy. **Quy ước naming chỉ hiệu quả khi có một nguồn cấp authority đáng tin và quy tắc mapping nhất quán.**

### Khi nào prefix có thể thay đổi?

Spring hỗ trợ một số cấu hình thay đổi **default role prefix** (ví dụ `GrantedAuthorityDefaults` cho những ngữ cảnh có áp dụng). Nhưng hành vi có thể **khác nhau theo API**:

- Một số method expression xử lý role prefix qua expression handler.
- `AuthorityAuthorizationManager.hasRole` mặc định tự gắn `ROLE_` và có kiểm tra tham số.
- Một số chương trình có **custom authorization manager**/role hierarchy tự định nghĩa.

**Không bỏ `ROLE_` hoặc đổi prefix toàn ứng dụng chỉ để “chữa hasRole không chạy”**. Việc thay đổi phải được test trên **request rules, method security, hierarchy, custom annotations và library version**. Trong đa số dự án, **giữ convention mặc định và map đúng dữ liệu** dễ kiểm toán hơn.

## 4. `hasRole` khác `hasAuthority` ra sao?

**`hasRole("ADMIN")`** là cách thuận tiện để kiểm tra một **role authority** với default role prefix. **`hasAuthority("ROLE_ADMIN")`** so sánh **chuỗi nguyên vẹn**. Tương tự `hasAuthority("SCOPE_orders:read")` kiểm tra đúng authority dành cho scope.

| Authorities hiện có | Check | Kết quả mặc định | Vì sao? |
|---|---|---|---|
| `ROLE_ADMIN` | `hasRole("ADMIN")` | **True** | Kỳ vọng `ROLE_ADMIN` |
| `ROLE_ADMIN` | `hasAuthority("ROLE_ADMIN")` | **True** | Exact string |
| `ROLE_ADMIN` | `hasAuthority("ADMIN")` | **False** | Không tự thêm prefix |
| `ADMIN` | `hasRole("ADMIN")` | **False** | Thiếu `ROLE_` |
| `SCOPE_orders:read` | `hasAuthority("SCOPE_orders:read")` | **True** | Exact authority |
| `SCOPE_orders:read` | `hasRole("orders:read")` | **False** | Kỳ vọng `ROLE_orders:read` |
| `ROLE_orders:read` | `hasAuthority("SCOPE_orders:read")` | **False** | Khác prefix |
| `ROLE_ADMIN` | `hasRole("admin")` | **False** | Authority string phân biệt chữ hoa–thường |
| `ROLE_ADMIN`, `SCOPE_orders:read` | `hasRole("ADMIN") and hasAuthority("SCOPE_orders:read")` | **True** | Cả hai điều kiện đạt |

**Không truyền sẵn `"ROLE_ADMIN"` vào `hasRole(...)` theo thói quen.** Với một số Spring Security APIs như `AuthorityAuthorizationManager.hasRole("ROLE_ADMIN")`, điều đó có thể bị từ chối bằng `IllegalArgumentException` vì tham số được mong đợi **không chứa prefix**. Dùng `hasRole("ADMIN")` hoặc `hasAuthority("ROLE_ADMIN")` để tránh nhập nhằng.

### `hasAnyRole` và `hasAnyAuthority`

~~~text
hasAnyRole("ADMIN", "SUPPORT")
    => theo mặc định tìm ROLE_ADMIN hoặc ROLE_SUPPORT

hasAnyAuthority("SCOPE_orders:read", "SCOPE_orders:write")
    => so exact một trong hai chuỗi authority

hasAuthority("ROLE_ADMIN")
    => không phải cách kiểm tra OAuth scope orders:read
~~~

Trong Spring Security expressions và các Java DSL tương ứng, nên xem **roles là một tập con authority có prefix được quy ước**, không phải một kiểu token khác.

## 5. Vì sao `SCOPE_` xuất hiện khi dùng JWT Resource Server?

OAuth 2.0 scope là chuỗi cách nhau bởi dấu cách trong token response/profile, biểu thị **phạm vi quyền cấp**. Với JWT access token, AS có thể đưa scope vào claim `scope` hoặc `scp` theo hợp đồng.

Payload access-token minh họa:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-42",
  "aud": "https://orders-api.example.test",
  "client_id": "orders-web",
  "scope": "orders:read orders:write",
  "exp": 1800003600
}
~~~

Đây chỉ là JSON minh họa, **không phải JWT đã ký**. Trong Spring Security OAuth2 Resource Server, **`JwtGrantedAuthoritiesConverter`** theo cấu hình mặc định thường:

1. Tìm các well-known authority claims như `scope` hoặc `scp`.
2. Tách `scope` string theo separator mặc định phù hợp profile, hoặc xử lý collection claims theo adapter.
3. Gắn authority prefix mặc định **`SCOPE_`**.
4. Đưa kết quả vào `Authentication.getAuthorities()`.

~~~text
JWT claim scope = "orders:read orders:write"
                  ↓ JwtGrantedAuthoritiesConverter
GrantedAuthorities = [
    "SCOPE_orders:read",
    "SCOPE_orders:write"
]
~~~

Vậy:

~~~java
.hasAuthority("SCOPE_orders:read")
~~~

sẽ hoạt động **nếu** JWT được verify đúng và converter thực sự tạo authority này.

**Không nói “OAuth 2.0 định nghĩa SCOPE_orders:read”**. OAuth scope tên thực là `orders:read`; prefix `SCOPE_` là **representation của Spring**, có thể cấu hình khác hoặc không có ở framework khác.

## 6. Scope và role là hai phép quyết định độc lập

### Role

Role mô tả **chức năng/vai trò của principal trong ứng dụng hoặc tổ chức**: `ADMIN`, `SUPPORT`, `CUSTOMER`. Nhiều hệ thống gán role bằng **user directory, IAM, database role assignment**, đôi khi đưa role vào token đã ký.

### Scope

Scope mô tả **quyền hạn mà token/client được cấp** theo OAuth grant/resource policy: `orders:read`, `orders:write`, `profile`. Scope thường được sử dụng để giới hạn **delegation và API action**.

| Thuộc tính | Role | OAuth scope |
|---|---|---|
| Chủ thể chính | User/service principal trong ứng dụng/tổ chức | Client/access-token grant, resource/API |
| Nguồn phổ biến | IAM/DB/IdP app roles | Authorization Server + grant/consent/policy |
| Giá trị mẫu | `ADMIN`, `SUPPORT` | `orders:read`, `orders:write` |
| Spring authority mẫu | `ROLE_ADMIN` | `SCOPE_orders:read` |
| Check điển hình | `hasRole("ADMIN")` | `hasAuthority("SCOPE_orders:read")` |
| Tự suy ra quyền trên object? | **Không** | **Không** |
| Tự chứng minh token đúng issuer/aud? | **Không** | **Không** |
| Có thể thay đổi/revoke? | Có, theo IAM/app state | Có, theo grant/token lifecycle và AS policy |
| Có bắt buộc có trên mọi OAuth AT? | **Không** | **Không phải mọi grant/profile đều bắt buộc có cùng claim** |

**Scope và role không có quan hệ 1–1 bắt buộc.** Một role có thể cần nhiều scope khi gọi API; một scope có thể được cấp cho nhiều loại client/role khác nhau. User **ADMIN** không tự động sở hữu token `orders:write`; token `orders:write` không tự động biến user thành ADMIN.

### Áp dụng “AND”, không “OR” khi rủi ro cao

Ví dụ endpoint duyệt hoàn tiền:

~~~text
Required:
    access token valid for payments-api
    AND scope contains "refunds:approve"
    AND principal has application role "FINANCE_APPROVER"
    AND request amount within current policy
    AND transaction belongs to allowed tenant
~~~

Nếu code dùng `hasRole("FINANCE_APPROVER") OR hasAuthority("SCOPE_refunds:approve")`, một caller **chỉ có một trong hai** có thể vượt chính sách. Khi nghiệp vụ yêu cầu cả delegated scope **và** quyền nội bộ, dùng **AND** và thêm object-level checks.

## 7. Một JWT hợp lệ chưa chắc là token cho API đang gọi

Ví dụ Billing token có role `ADMIN`:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-42",
  "aud": "https://billing-api.example.test",
  "client_id": "orders-web",
  "scope": "billing:read",
  "app_roles": ["ADMIN"],
  "exp": 1800003600
}
~~~

Nếu **Orders API** chỉ đọc `app_roles` rồi map `ADMIN → ROLE_ADMIN`, token này có thể bị dùng sai tài nguyên. **Đúng vai trò không thay `aud`.**

RS phải xác minh **chữ ký và `iss` từ AS tin cậy, `aud` đúng Orders, token purpose/`typ` đúng access token, `exp`/`nbf`, sender proof nếu có** trước khi chuyển claims thành authorities.

**Một token JWT self-contained có thể mang roles còn hiệu lực theo claims nhưng DB đã thay đổi quyền**. Phải có chiến lược TTL ngắn, introspection/denylist/epoch hoặc DB authorization theo độ nhạy cảm; **không bảo đảm role change tức thì chỉ nhờ Spring đọc JWT**.

## 8. Phân biệt user authentication, client credentials và OIDC ID token

Không phải mọi access token đại diện một user đăng nhập:

| Token/use case | Principal thường là ai? | Authorities nên xuất phát từ đâu? |
|---|---|---|
| **Authorization Code + PKCE cho user** | User, thông qua OAuth client | Scope được cấp; app role/user permission nếu được AS/RS xác minh |
| **`client_credentials`** | Client/service workload | Client-granted scopes/workload permissions, không tự gán user role |
| **OIDC ID token** | Bằng chứng authentication user đối với **Relying Party** | Dùng theo OIDC validation tại RP, **không** dùng làm OAuth API bearer token |
| **Refresh token** | Credential tại **AS/token endpoint** | Không dùng làm resource-server `Authentication` |
| **Opaque access token** | Theo introspection result/context | Validated scopes, token type, audience, AS–RS contract |
| **JWT access token** | Theo AS-issued profile | Claims đã được verifier kiểm chứng và được mapping theo contract |

Ví dụ một service gọi `POST /orders/123/dispatch` bằng `client_credentials` và `scope=orders:dispatch`. Nó có thể được cấp quyền theo **service identity**, không cần và **không nên tự nhận `ROLE_ADMIN` của người dùng**.

**`client_id` không đồng nghĩa `sub` của người dùng**, và `sub` không chứng minh một authority hợp lệ nếu token sai audience. Tại RP dùng OIDC, ID token `aud=client_id` không thể dùng thay Orders API access token.

## 9. Authentication trong Spring Security được xây dựng thế nào?

Một `Authentication` object trong `SecurityContext` có thể mang:

- **Principal**: `Jwt`, `UserDetails`, OIDC user hoặc loại principal do ứng dụng định nghĩa.
- **Credentials**: thông tin xác thực tùy cơ chế; tránh lưu/lộ bí mật trong logs.
- **Authorities**: `Collection<? extends GrantedAuthority>`, là kết quả được provider/converter xây từ **nguồn đáng tin**.
- **Authenticated state**: kết quả của authentication pipeline, không phải quyền trên mọi API.

~~~mermaid
sequenceDiagram
    autonumber
    participant Client as OAuth Client
    participant Filter as BearerTokenAuthenticationFilter
    participant Provider as JwtAuthenticationProvider
    participant Decoder as JwtDecoder
    participant Conv as JwtAuthenticationConverter
    participant Policy as AuthorizationManager / Method Security

    Client->>Filter: Authorization: Bearer <ACCESS_TOKEN>
    Filter->>Provider: Authentication request
    Provider->>Decoder: Decode + verify JWS/issuer/audience/time
    Decoder-->>Provider: Validated Jwt hoặc error
    Provider->>Conv: Convert validated Jwt
    Conv-->>Provider: JwtAuthenticationToken + GrantedAuthorities
    Provider-->>Filter: Authenticated principal hoặc failure
    Filter->>Policy: SecurityContext Authentication
    Policy->>Policy: hasAuthority / hasRole / object ACL
~~~

Với opaque token, thay decoder bằng authenticated **token introspection**/adapter, nhưng **ý tưởng tách token validation và authority mapping** vẫn giữ nguyên.

**Không để controller tự parse JWT bằng Base64url, đọc claim `roles` rồi tự gán `SecurityContextHolder`**. Nếu bypass validator, user có thể tự sửa payload hoặc đưa token sai issuer/audience.

## 10. Default JwtGrantedAuthoritiesConverter có những giới hạn gì?

`JwtGrantedAuthoritiesConverter` là converter dành cho **scope-like claims** của JWT đã xác minh. Một default configuration **không tự hiểu**:

- App role claim tên `app_roles`, `roles` hoặc `groups`.
- Provider-specific nested claim như `realm_access.roles` hay `resource_access.<client>.roles`.
- Tenant-local role, RBAC hierarchy hoặc object ACL trong database.
- User đã bị khóa/revoke sau khi JWT được ký nếu RS không tra trạng thái mới.
- Những scopes dành riêng cho Resource Server khác.

Ví dụ converter mặc định:

~~~java
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

public class ScopeConverterDemo {
    public static JwtGrantedAuthoritiesConverter defaultScopes() {
        JwtGrantedAuthoritiesConverter converter =
                new JwtGrantedAuthoritiesConverter();
        converter.setAuthorityPrefix("SCOPE_");
        return converter;
    }
}
~~~

`setAuthorityPrefix("SCOPE_")` ở ví dụ này **nhắc rõ convention mặc định**, không buộc AS đổi claim `scope` thành chuỗi có sẵn prefix. **Không** gọi `setAuthorityPrefix("ROLE_")` cho scope chỉ để biến mọi OAuth scope thành role: điều đó có thể làm một client có scope `admin` vô tình sở hữu `ROLE_admin` và tạo privilege escalation khi developer dùng `hasRole`.

Nếu AS phát claim đặc thù, hãy thiết kế **converter riêng với allowlist rõ** và **đúng token profile**.

## 11. Spring Security 6: JWT Resource Server với scope check

Ví dụ cấu hình **Bearer-only API**. Các route `/api/orders/**` yêu cầu scope; route admin đòi cả role và scope theo chính sách.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableMethodSecurity
public class OrdersApiSecurity {
    @Bean
    SecurityFilterChain ordersApiChain(
            HttpSecurity http,
            JwtAuthenticationConverter jwtAuthenticationConverter
    )
            throws Exception {
        http
            .securityMatcher("/api/**")
            // Chỉ an toàn khi chain này tuyệt đối không xác thực
            // bằng browser session cookie; cần chain khác cho web UI.
            .csrf(csrf -> csrf.disable())
            .cors(withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.OPTIONS, "/api/**")
                    .permitAll() // CORS allowlist vẫn phải cấu hình.
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:write")
                .requestMatchers("/api/admin/**")
                    .access((authentication, context) -> {
                        var authorities =
                            authentication.get().getAuthorities();
                        boolean admin = authorities.stream()
                            .anyMatch(a -> "ROLE_ADMIN".equals(
                                    a.getAuthority()));
                        boolean manageScope = authorities.stream()
                            .anyMatch(a -> "SCOPE_admin:manage".equals(
                                    a.getAuthority()));
                        return new AuthorizationDecision(admin && manageScope);
                    })
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth -> oauth
                .jwt(jwt -> jwt
                    .jwtAuthenticationConverter(
                        jwtAuthenticationConverter
                    )
                )
            );
        return http.build();
    }
}
~~~

**Ví dụ cho thấy cách thêm điều kiện AND**, không phải khuyến khích viết custom lambda dài trong production. Với policy đơn giản, có thể dùng method security `@PreAuthorize("hasRole('ADMIN') and hasAuthority('SCOPE_admin:manage')")` hoặc custom `AuthorizationManager` được kiểm thử riêng.

**Giới hạn quan trọng:**

1. `HttpSecurity` chain này chỉ phù hợp **API nhận Bearer token**, không cho cookie session làm phương thức auth. **Không tắt CSRF** ở mixed-mode web app chỉ vì có OAuth.
2. CORS `OPTIONS permitAll` **không có nghĩa cho phép mọi origin**; CORS config vẫn phải dùng allowlist.
3. Phải cấu hình **issuer/audience/key/type validation**, không chỉ mapping authority.
4. Nếu roles từ token chưa được converter map, `ROLE_ADMIN` sẽ **không tồn tại**, khiến admin route trả 403. Đó là lỗi cấu hình cần sửa ở **trusted mapping**, không phải lý do xóa role check.
5. Với Spring Security 6 API/phiên bản khác, cách viết AuthorizationManager có thể thay đổi; test compile và behavior trong ứng dụng thực.
6. Những endpoint ngoài `/api/**` cần **security filter chain riêng** có thứ tự và deny-by-default; không coi example này đã khóa toàn bộ ứng dụng.

## 12. Spring Security 6: map scope và app role từ JWT

Giả sử AS tin cậy phát:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-42",
  "aud": "https://orders-api.example.test",
  "client_id": "orders-web",
  "scope": "orders:read orders:write",
  "app_roles": ["SUPPORT"],
  "exp": 1800003600
}
~~~

**`app_roles` là claim riêng do AS/RS thống nhất**, không phải claim chuẩn bắt buộc của OAuth hay RFC 9068. Code dưới đây chỉ map **allowlisted roles** và **validated JWT**; không tạo role từ một claim tên tùy ý do client gửi.

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Configuration
public class JwtAuthoritiesMapping {
    private static final Set<String> ALLOWED_APP_ROLES =
            Set.of("USER", "SUPPORT", "ADMIN");

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter scopeConverter =
                new JwtGrantedAuthoritiesConverter();
        scopeConverter.setAuthorityPrefix("SCOPE_");

        Converter<Jwt, Collection<GrantedAuthority>> converter =
                jwt -> {
                    Set<GrantedAuthority> result =
                            new LinkedHashSet<>();

                    Collection<GrantedAuthority> scopes =
                            scopeConverter.convert(jwt);
                    if (scopes != null) {
                        result.addAll(scopes);
                    }

                    Object claim = jwt.getClaim("app_roles");
                    if (claim instanceof Collection<?> roles) {
                        for (Object candidate : roles) {
                            if (candidate instanceof String role
                                    && ALLOWED_APP_ROLES.contains(role)) {
                                result.add(
                                    new SimpleGrantedAuthority(
                                        "ROLE_" + role
                                    )
                                );
                            }
                        }
                    }
                    // Missing, malformed hoặc unknown roles:
                    // không tự nâng quyền. Theo AS contract, có thể
                    // chủ động reject token ở validator riêng.

                    return new ArrayList<>(result);
                };

        JwtAuthenticationConverter jwtConverter =
                new JwtAuthenticationConverter();
        jwtConverter.setJwtGrantedAuthoritiesConverter(converter);
        return jwtConverter;
    }
}
~~~

**Những ràng buộc bảo mật:**

- `JwtAuthenticationConverter` chỉ nhận Jwt từ provider đã **verify chữ ký và profile**, nhưng converter không tự bắt buộc `aud`/`iss`: phải cấu hình decoder validator riêng.
- Chỉ role trong **allowlist** được thêm; giá trị `"ROLE_ADMIN"` đến từ claim không trở thành `"ROLE_ROLE_ADMIN"` vì không có trong allowlist.
- Nếu claim `app_roles` sai schema, code **không cấp role** (fail privilege-closed). Tùy AS–RS contract, nên **reject token** ở validator thay vì chỉ bỏ roles để dễ phát hiện data quality/security incident.
- Scope mapping phải nhất quán với `scope`/`scp` của AS. `JwtGrantedAuthoritiesConverter` theo default không tự kiểm tra scope có đúng resource mapping không; AS phải cấp và RS phải validate audience.
- Code **không ràng buộc user role vào tenant**; một role `ADMIN` trong tenant A **không được mặc định có quyền tenant B**.
- Không đọc role từ `X-Role`, `role` request parameter, query string, unsigned JWT hoặc cấu hình client tự khai.

### Kết nối converter vào JWT DSL

Ở **ví dụ SecurityFilterChain mục 11**, phương thức `ordersApiChain` nhận bean `JwtAuthenticationConverter` và truyền vào `jwt(jwt -> jwt.jwtAuthenticationConverter(jwtAuthenticationConverter))`. Bean này được tạo tại `JwtAuthoritiesMapping` mục 12, nên pipeline giữ **scope converter mặc định** đồng thời thêm những **app roles được allowlist**. Nếu project dùng cách cấu hình khác, phải đảm bảo converter được nối vào **đúng filter chain**. **Kiểm tra authorities trong integration test**, không debug bằng cách bật log raw JWT.

## 13. Spring `JwtDecoder`: issuer/audience phải đúng trước khi có role

Một JWT có `app_roles=["ADMIN"]` nhưng sai audience không thể được nhận ở Orders API. Ví dụ decoder cấu hình issuer và audience:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class OrdersJwtDecoderConfig {
    private static final String ISSUER =
            "https://auth.example.test";
    private static final String AUDIENCE =
            "https://orders-api.example.test";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withIssuerLocation(ISSUER).build();

        OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains(AUDIENCE)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                            "invalid_token",
                            "Token audience mismatch",
                            null
                        )
                );

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                    JwtValidators.createDefaultWithIssuer(ISSUER),
                    audience
                )
        );
        return decoder;
    }
}
~~~

**Đây là ví dụ Spring Security 6**, không phải profile enforcement hoàn chỉnh. Nếu dùng **RFC 9068**, còn phải kiểm tra JOSE `typ` là access-token profile cho phép (ví dụ `at+jwt`), allowed `alg`, mandatory claims và profile contract; chống ID token confusion. `withIssuerLocation` sử dụng metadata từ **issuer cấu hình tin cậy**, không lấy URL từ input không tin cậy.

**Không** bỏ `JwtValidators.createDefaultWithIssuer` khi thêm audience validator, vì mất checks cho issuer/time theo framework. **Không** đưa issuer tùy ý từ claim token vào lookup URL/JWKS và bỏ validation khi network fail.

## 14. `@PreAuthorize`: role và scope ở method security

Bật method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {}
~~~

Ví dụ service:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class RefundService {
    @PreAuthorize(
        "hasRole('FINANCE_APPROVER') and " +
        "hasAuthority('SCOPE_refunds:approve')"
    )
    public void approveRefund(String refundId) {
        // CẦN kiểm tra tenant, owner và business policy
        // dựa trên dữ liệu server trước khi commit.
    }

    @PreAuthorize("hasAuthority('SCOPE_refunds:read')")
    public String getRefundSummary(String refundId) {
        return "Demo only";
    }
}
~~~

**Trường hợp đầu yêu cầu cả `ROLE_FINANCE_APPROVER` và `SCOPE_refunds:approve`.** Trường hợp thứ hai chỉ có scope gate; nó **không chứng minh** user được đọc refundId đó. Với object quyền nhạy cảm, thêm bean đáng tin:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders:read') and " +
    "@orderPermission.canRead(authentication, #orderId)"
)
~~~

`@orderPermission` phải truy cập **database/tenant binding được xác thực** thay vì so user ID mà client truyền. Đây là phần của **authorization business logic**, không phải JWT signature check.

### Vì sao method security quan trọng?

URL matching dễ bỏ qua những đường truy cập nội bộ, batch job, service method hoặc GraphQL resolver. Một service-level decision được thiết kế tốt giảm tình trạng endpoint A có ACL còn endpoint B gọi cùng service thì không. Nhưng chỉ thêm annotation mà **không bật `@EnableMethodSecurity`** sẽ khiến `@PreAuthorize` không có hiệu lực như mong đợi.

## 15. `UserDetails`/login truyền thống tạo ROLE_ như thế nào?

Không phải mọi Spring Security app đều là OAuth Resource Server. Với login **username/password + session**, roles có thể được tạo khi load user từ database hoặc `UserDetailsService`.

~~~java
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;

public final class UserDetailsRoleDemo {
    public static UserDetails demo() {
        return User.withUsername("demo-user")
            // Chỉ DEMO; không dùng noop/plaintext password ở production.
            .password("{noop}demo-only-password")
            .roles("ADMIN", "USER")
            .build();
    }

    private UserDetailsRoleDemo() {}
}
~~~

`roles("ADMIN", "USER")` trong builder này tạo authorities theo convention **`ROLE_ADMIN` và `ROLE_USER`**. Đừng truyền `roles("ROLE_ADMIN")` rồi nghĩ kết quả tốt hơn; nhiều builder tự thêm prefix và có validation chống truyền sẵn prefix.

Nếu bạn muốn chỉ định chuỗi đúng:

~~~java
User.withUsername("demo-user")
    .password("{noop}demo-only-password")
    .authorities("ROLE_ADMIN", "SCOPE_orders:read")
    .build();
~~~

**`authorities(...)` cấp chính xác authority string**, còn `roles(...)` mang ý nghĩa role prefix. Với hệ thống dùng database, hãy **load role từ server-controlled assignments**, không chấp nhận danh sách role do user truyền trong login form. Khi dùng production, bắt buộc password encoder an toàn, không dùng `{noop}`.

### UserDetails roles không tự xuất hiện trong JWT

Nếu một user đăng nhập bằng `UserDetailsService` ở một ứng dụng, điều đó **không khiến mọi Spring Resource Server đọc Bearer JWT tự có `ROLE_ADMIN`**. Các hệ thống có thể có **hai authentication providers và hai authority-mapping pipelines** hoàn toàn khác nhau. Hãy test chúng riêng theo route, token type và user state.

## 16. Chỉ dùng `@Secured`, `@RolesAllowed` khi hiểu prefix

Spring Security hỗ trợ nhiều kiểu method authorization:

- `@PreAuthorize("hasRole('ADMIN')")`: Spring expression, có thể kết hợp scope và object permission.
- `@Secured("ROLE_ADMIN")`: khi tính năng được bật, dùng authority string theo cơ chế annotation tương ứng.
- `@RolesAllowed("ADMIN")` theo JSR-250/Jakarta: ngữ nghĩa role/prefix phụ thuộc cấu hình và support của Spring Security.
- Java DSL `.hasRole("ADMIN")` và `.hasAuthority("ROLE_ADMIN")`: theo các nguyên tắc đã phân biệt.

**Không chuyển đổi máy móc annotation** mà không kiểm thử. Đặc biệt, `@EnableMethodSecurity` mặc định bật một số kiểu annotation như `@PreAuthorize`, còn `@Secured`/JSR-250 có **các tùy chọn enable riêng** theo Spring version. Không được giả định thêm annotation vào code luôn làm security engine áp dụng nó.

**Khuyến nghị cho bài tập:** chọn một convention rõ (ví dụ `@PreAuthorize` + `hasAuthority`/`hasRole`) thay vì trộn nhiều kiểu mà không document evaluator và role prefix.

## 17. Role hierarchy không tự cho OAuth scopes

Một số ứng dụng có hierarchy:

~~~text
ROLE_ADMIN
    > ROLE_MANAGER
        > ROLE_USER
~~~

Nếu policy có cấu hình `RoleHierarchy` tương ứng, authority `ROLE_ADMIN` có thể được diễn giải là có role hiệu lực `ROLE_MANAGER` và `ROLE_USER` ở những authorization managers/expressions dùng hierarchy.

**Nhưng**:

~~~text
ROLE_ADMIN != SCOPE_orders:read
ROLE_MANAGER != SCOPE_orders:write
ROLE_USER != SCOPE_profile
~~~

Role hierarchy là **quy tắc nội bộ của role resolution**, không phải cơ chế AS tự cấp scope mới. Đừng tự đặt rule “admin có toàn bộ scopes” nếu OAuth grant và Resource Server audience không cho phép.

### Khi nào hierarchy có ích?

- Định nghĩa cấp bậc chức năng nội bộ ổn định (`ADMIN > SUPPORT > VIEWER`).
- Giảm lặp policy, ví dụ API quản trị cho phép role Admin kế thừa một số quyền đọc.
- Chuẩn hóa role checks tại web/backend có một role model chung.

### Khi nào nên tránh?

- Multi-tenant: Admin tenant A **không** nên tự kế thừa quyền trong tenant B.
- Delegated OAuth: một user có role Admin nhưng token được cấp **read-only**; scope phải vẫn chặn write.
- Role tạm thời/điều kiện theo resource: hierarchy toàn cục có thể làm mất điều kiện thời gian hoặc object.
- Admin từ **client_credentials** không đồng nghĩa admin user.

## 18. Mapping roles từ JWT: nơi dễ xảy ra privilege escalation

Một converter không an toàn:

~~~java
// CHỐNG CHỈ ĐỊNH: role lấy từ request do client tự đặt.
String role = request.getHeader("X-Role");
authentication = authenticatedWith(
    new SimpleGrantedAuthority("ROLE_" + role)
);
~~~

Một converter rủi ro khác:

~~~java
// CHỐNG CHỈ ĐỊNH: không có allowlist và không ràng buộc
// role từ claim với issuer/audience/tenant/application.
for (String role : tokenRoles) {
    authorities.add(
        new SimpleGrantedAuthority("ROLE_" + role)
    );
}
~~~

Dù JWT đã ký, claim roles có thể:

- Thuộc **resource khác** (Billing Admin không phải Orders Admin).
- Thuộc **tenant khác**.
- Là **realm-wide role** chứ không phải application role.
- Được phát cho **client_credentials** và không đại diện user.
- Đã **stale** sau khi admin revoke role.
- Có schema lạ và bị converter hiểu nhầm (string vs array, nested map).
- Bị map thành role quá quyền do tự động bỏ/thêm prefix mà không kiểm soát.

### Contract role mapping an toàn

1. **Chỉ dùng JWT access token đã verified** đúng issuer/audience/type/expiry.
2. Chọn **claim cụ thể** gắn resource/tenant (`app_roles` hoặc cấu trúc provider được AS bảo đảm).
3. **Allowlist role names**, case-sensitivity, namespace, schema validation và policy version.
4. Không suy từ token scope thành role nếu không có một quy tắc explicit, được threat-model.
5. Nếu role là dynamic/sensitive, lấy từ **server-controlled DB/IAM** hoặc kiểm tra auth epoch/entitlement version.
6. Test admin cross-tenant, client credentials, stale role, role name injection và unknown claim values.

## 19. Provider-specific roles không phải một RFC bắt buộc

Ví dụ một IdP có thể phát JSON:

~~~json
{
  "iss": "https://login.example.test/realms/retail",
  "aud": "https://orders-api.example.test",
  "scope": "orders:read",
  "realm_access": {
    "roles": ["customer", "support"]
  },
  "resource_access": {
    "orders-api": {
      "roles": ["order-reviewer"]
    }
  }
}
~~~

Đây là **cấu trúc provider-specific giả lập**, không phải mọi AS bắt buộc có `realm_access` hay `resource_access`. Nếu ứng dụng map `realm_access.roles` thành mọi `ROLE_...` trên Orders API, một role toàn realm có thể bị hiểu quá rộng. Nếu role thực sự dành **orders-api**, mapping nên dựa vào **resource-specific claim đã được AS chứng thực** và ranh giới tenant.

### Prefix từ provider có nên giữ nguyên?

Nếu AS gửi `"ROLE_ADMIN"`, còn converter lại gắn `"ROLE_"`, kết quả có thể thành `"ROLE_ROLE_ADMIN"` — không khớp `hasRole("ADMIN")`. Chọn **một convention** và kiểm tra dữ liệu bằng tests; không áp heuristic “nếu chuỗi chứa ADMIN thì cấp quyền”.

### Scope provider có thể là array

Một provider có thể gửi:

~~~json
{
  "scp": [
    "orders:read",
    "profile"
  ]
}
~~~

Nếu đó là contract đã chấp thuận, cấu hình converter dùng đúng claim, separator hoặc list representation. Không dùng `String.contains("orders:read")`, vì `orders:read:any` không phải `orders:read`.

## 20. Opaque token và introspection cũng có authority mapping

Với **opaque access token**, RS không tự parse JWT. Nó có thể dùng **RFC 7662 Token Introspection**:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.test
Authorization: Basic <RESOURCE_SERVER_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded

token=<OPAQUE_ACCESS_TOKEN>&token_type_hint=access_token
~~~

Ví dụ AS trả:

~~~json
{
  "active": true,
  "iss": "https://auth.example.test",
  "aud": "https://orders-api.example.test",
  "client_id": "orders-web",
  "scope": "orders:read",
  "sub": "user-42",
  "exp": 1800003600
}
~~~

Một Spring Security **opaque-token introspector/converter** có thể map `scope=orders:read` thành `SCOPE_orders:read`, nhưng cách mapping phụ thuộc Spring/provider profile.

**`active:true` không đủ để chấp nhận mọi quyền**:

- RS phải được phép introspect; AS phải trả metadata phù hợp **RS context**.
- Cần ràng buộc đúng token **purpose**, issuer/audience/resource và expiry hoặc hợp đồng tương đương.
- Không dùng `token_type_hint` như bằng chứng rằng credential thực sự là access token.
- Role nội bộ chỉ được cấp nếu có claim và mapping **được tin cậy** theo RS/grant/tenant policy.
- Nếu AS trả `active:false`, RS không tạo Authentication có quyền, thường **401 invalid_token** cho Bearer-protected API.
- Nếu AS timeout/RS credentials sai, đây là **dependency error**, không phải user tự mất role; phải **fail closed** và phân loại vận hành.

Opaque vs JWT là **hình thức biểu diễn**; hai loại vẫn cần **authority model rõ** và authorization nghiệp vụ sau token validation.

## 21. 401 hay 403 khi role/scope không đúng?

| Trạng thái request | HTTP thường phù hợp | Lý do |
|---|---:|---|
| Không có Bearer token cho protected API | **401** | Thiếu credentials |
| JWT signature/issuer/audience sai | **401** | Không có access credential hợp lệ cho RS |
| JWT hết hạn hoặc opaque `active:false` | **401** | Credential invalid/inactive |
| Token hợp lệ nhưng **không có `SCOPE_orders:write`** | **403** | Thiếu OAuth scope cần thiết |
| Token hợp lệ có scope nhưng thiếu `ROLE_ADMIN` | **403** | Thiếu role/policy; không mặc định `insufficient_scope` |
| Token đúng role/scope nhưng order thuộc tenant khác | **403 hoặc 404** | Object/tenant policy |
| JWT đúng role nhưng AT audience Billing gửi Orders | **401** | Sai recipient token |
| Introspection timeout, không có verdict | **503/5xx** theo policy | Dependency failure, **không** quy thành thiếu role |
| CSRF token thiếu tại cookie-authenticated web endpoint | **403** thường gặp | CSRF policy, không phải OAuth `insufficient_scope` |

Với **OAuth 2.0 Bearer** theo RFC 6750:

- **`401 + WWW-Authenticate: Bearer error="invalid_token"`** thường dùng cho access token invalid.
- **`403 + WWW-Authenticate: Bearer error="insufficient_scope"`** thường dùng khi token hợp lệ nhưng **thiếu OAuth scope**, có thể có tham số `scope` khi phù hợp.
- **403 vì role/object ACL** có thể trả generic Forbidden; **không tự gắn `insufficient_scope`** nếu thêm scope cũng không giải quyết được vấn đề.

**Không map mọi `AccessDeniedException` thành 401** để frontend liên tục refresh token. Client cần phân biệt **reauthentication** với **xin quyền mới** và **từ chối vì object policy**.

## 22. Vai trò runtime có thể stale vì JWT/AS cache

Giả sử user `U42` có role `ADMIN` lúc AS cấp JWT access token:

~~~text
10:00  AS issue JWT AT:
       aud=orders-api, app_roles=["ADMIN"], exp=10:15

10:05  Security admin gỡ quyền ADMIN khỏi U42 ở IAM
10:06  Orders RS verify JWT offline:
       signature valid, exp future, role claim vẫn ADMIN

Nếu không check trạng thái quyền mới:
       ROLE_ADMIN có thể tiếp tục hiện diện đến exp
~~~

**Spring Security không tự đồng bộ việc thu hồi role trong IAM khi đang dùng self-contained JWT offline.**

Các lựa chọn:

| Cách | Điều đạt được | Trade-off |
|---|---|---|
| JWT TTL ngắn | Giới hạn thời gian role stale | Không tức thì; tăng refresh requests |
| Opaque token introspection | AS có thể trả active/metadata theo grant hiện hành | AS dependency, cache TTL |
| JWT + entitlement version/auth epoch | RS đối chiếu version của user/grant | Thêm state query/caching |
| JWT + denylist/revocation event | Chặn JWT trước `exp` khi event đã tới RS | Event consistency/latency, cần retry |
| Tra DB/IAM cho role nhạy cảm | Authorization gần real-time theo system of record | Độ trễ/availability và transactional consistency |
| Admin step-up/reauthentication | Giảm rủi ro hành động quyền cao | UX và luồng auth bổ sung |

**Role revocation và token revocation liên quan nhưng không đồng nghĩa**. Thu hồi **refresh-token family** chặn **cấp AT mới**, nhưng không bảo đảm mọi JWT AT đã cấp **ngay lập tức mất `ROLE_ADMIN`** nếu RS chỉ verify offline.

## 23. Multi-tenant: `ROLE_ADMIN` không tự là global admin

Xét SaaS có hai tenant:

~~~text
User U42:
   tenant shop-A: role ADMIN
   tenant shop-B: role VIEWER

AT for shop-A:
   aud = orders-api
   scope = orders:read orders:write
   tenant = shop-A
   app_roles = [ADMIN]
~~~

Nếu Orders API dùng mỗi `hasRole("ADMIN")` và cho `/tenants/shop-B/orders`, token của shop-A có thể bị dùng để quản trị shop-B.

### Chính sách đúng

1. AS/RS xác thực `iss`, `aud`, token type và thời gian.
2. Xác định **trusted tenant context** theo grant/policy và request target.
3. Map role **theo tenant**, không biến role tenant-local thành global `ROLE_ADMIN`.
4. Kiểm tra `scope` cho hành động trong API.
5. Query **user–tenant membership**, owner/ACL và object relationship từ nguồn tin cậy.
6. Không nhận `X-Tenant-Role` hoặc `tenant_id` từ body là bằng chứng quyền.

Một app có thể biểu diễn tenant role như `TENANT_shop-A_ADMIN` hoặc dùng custom `AuthorizationManager` để đánh giá binding. **Không có một convention role prefix chuẩn chung cho multi-tenant**; quy tắc phải nhất quán, tránh dynamic authority string injection và lộ tenant IDs qua logs.

## 24. Service-to-service: role của user không tự đi theo delegated token

Khi Orders API cần gọi Shipping API:

~~~text
Client user token:
  aud = orders-api
  scope = orders:read
  app_roles = ["SUPPORT"]

Orders API -> Shipping API:
  Không tự forward AT_ORDERS như access token cho Shipping.
~~~

Các cách đúng:

- Xin **access token dành cho Shipping API** qua AS, có audience/scope mục tiêu.
- Nếu yêu cầu hành động thay user, dùng **OAuth Token Exchange RFC 8693** hoặc cơ chế On-Behalf-Of theo provider contract, ràng buộc subject, actor, resource và scope.
- Nếu tác vụ độc lập với user, dùng `client_credentials` với workload identity và service-specific permissions.
- Shipping API vẫn kiểm tra issuer/audience/scope/service policy và object authorization theo hợp đồng.

**Không tự propagate `ROLE_ADMIN` qua HTTP header giữa services** trừ khi có **mô hình authenticated internal trust boundary** (mTLS/service identity, header stripping, signed context, route restrictions) được thiết kế rõ. Nếu chỉ nhận `X-User-Roles: ADMIN` từ mạng, attacker có thể tự cấp quyền.

Role của một ứng dụng không nhất thiết có nghĩa trong ứng dụng khác. Cần **delegation semantics**, không giả định “chuyển JWT qua là đủ”.

## 25. Role hierarchy, scope và principle of least privilege

Có thể tưởng tượng một policy matrix:

| Action | Scope access token | App role | Object rule |
|---|---|---|---|
| Xem order của chính mình | `orders:read` | `CUSTOMER` hoặc `SUPPORT` | Owner/tenant |
| Xem order để hỗ trợ | `orders:read` | `SUPPORT` | Ticket assigned/tenant |
| Hủy order | `orders:cancel` | `CUSTOMER` hoặc `OPERATIONS` | Status/time/ownership |
| Điều chỉnh tiền hoàn | `refunds:approve` | `FINANCE_APPROVER` | Amount limit và dual approval |
| Quản lý policy | `admin:manage` | `ADMIN` | Step-up, tenant scope và audit |

Trong một hệ thống thực tế, không phải mọi action đều cần cả role và scope giống ví dụ; điều quan trọng là **role/scope là hai tín hiệu độc lập** và policy phải **có chủ đích**.

**Đừng vô tình cấp role dựa vào scope trùng tên**, ví dụ:

~~~text
scope="admin"        -- KHÔNG tự động => ROLE_ADMIN
scope="support"      -- KHÔNG tự động => ROLE_SUPPORT
scope="orders:read"  -- KHÔNG tự động => ROLE_ORDERS_READ
~~~

Một OAuth client có thể được cấp scope `admin` theo một legacy profile, nhưng **không có bằng chứng đó là user có role ADMIN** nếu AS/RS không thiết kế ràng buộc.

## 26. Quan sát authorities mà không lộ token

Để debug 403, nên thu thập **các lý do an toàn**, không ghi nguyên `Authorization`/JWT.

Ví dụ event:

~~~json
{
  "event_type": "authorization.denied",
  "occurred_at": "2026-11-23T10:20:00Z",
  "resource_server": "orders-api",
  "route_template": "POST /api/orders/{id}/cancel",
  "issuer": "https://auth.example.test",
  "client_id": "orders-web",
  "reason": "MISSING_REQUIRED_SCOPE",
  "required_authority": "SCOPE_orders:cancel",
  "authority_mapping_version": "v3",
  "token_ref": "hmac-pseudonym-not-raw-token",
  "raw_token_logged": false
}
~~~

**`raw_token_logged=false` là mong muốn audit**, không bảo đảm reverse proxy, tracing, APM hay exception handler đã redaction. Các dữ liệu như `sub`, tenant, role cao cấp, object IDs có thể là PII/business secrets; hạn chế fields, quyền truy cập và thời gian lưu.

Các reason categories hữu ích:

- `INVALID_TOKEN_SIGNATURE`, `WRONG_ISSUER`, `WRONG_AUDIENCE`.
- `TOKEN_EXPIRED`, `REVOKED_OR_INACTIVE`.
- `SCOPE_NOT_MAPPED`, `ROLE_CLAIM_UNKNOWN`, `MISSING_REQUIRED_SCOPE`.
- `ROLE_NOT_GRANTED`, `TENANT_CONTEXT_DENIED`, `OBJECT_PERMISSION_DENIED`.
- `AUTHENTICATION_PROVIDER_UNAVAILABLE`, `INTROSPECTION_FAILURE`.

**Không suy từ mỗi HTTP 403 rằng vấn đề là role prefix.** Có thể là scope thiếu, sai tenant, method security, CSRF, policy DB hoặc AS token contract.

## 27. Troubleshooting: vì sao `hasRole` luôn false?

| Hiện tượng | Nguyên nhân thường gặp | Điều cần kiểm tra |
|---|---|---|
| `hasRole("ADMIN")` false nhưng JWT có `"roles":["ADMIN"]` | Spring JWT converter mặc định chỉ map scope-like claims | Chưa có trusted role claim converter |
| `hasRole("ADMIN")` false, authorities chứa `ADMIN` | Thiếu `ROLE_` prefix | Map thành `ROLE_ADMIN` hoặc dùng hasAuthority("ADMIN") có chủ đích |
| `hasRole("ADMIN")` false, authorities có `ROLE_ROLE_ADMIN` | Prefix bị thêm hai lần | Chuẩn hóa claim/input, allowlist |
| `hasAuthority("SCOPE_orders:read")` false, JWT `scope` đúng | Custom converter đã thay thế default scope mapping | Gộp scopes + roles, không xóa scopes |
| `hasAuthority("orders:read")` false | Spring map thành `SCOPE_orders:read` | Dùng đúng prefix hoặc cấu hình converter rõ |
| User có role tại IAM, RS vẫn trả 403 | Token chưa mang role hoặc AS/RS cache stale | Token issuance, roles claim, version/epoch, IAM source |
| User có `ROLE_ADMIN` nhưng Orders trả 401 | JWT sai `aud`/`iss`/hết hạn | Authentication precedes authority checks |
| `@PreAuthorize` không chạy | Chưa enable method security hoặc call bypass proxy | `@EnableMethodSecurity`, proxy/self-invocation, test |
| Service call từ method trong cùng class bỏ qua annotation | Proxy-based method interception không được gọi | Tách bean hoặc kiểm tra invocation model |
| Role đúng ở tenant A, thao tác tenant B bị deny | Tenant-object authorization | Đây là hành vi bảo mật cần có |
| Scope case mismatch | `orders:read` khác `Orders:Read` | So authority strings exact |
| `@Secured` không hoạt động | Chưa bật hỗ trợ annotation tương ứng | Method security settings/version |
| 403 sau khi bật CORS/CSRF | CSRF token/Origin policy fail | Phân biệt browser CSRF 403 vs OAuth missing authority |
| Opaque introspection active nhưng authorities trống | AS response không có scope/adapter contract sai | Kiểm tra RS-specific introspection/mapping |
| JWT role claim là string thay vì array | Converter đòi list | Sửa AS schema, reject/ignore theo contract |
| Login session có ROLE_ADMIN, API JWT lại không | Hai authentication providers khác nhau | UserDetails mapper vs JWT converter |
| Đổi `GrantedAuthorityDefaults`, một số checks sai | Prefix defaults không nhất quán trên APIs | Test tất cả route/method/AuthorizationManager |
| Client credentials có `ROLE_ADMIN` bất ngờ | Map user roles sang service token | Tách workload vs user authorities |
| Role thay đổi nhưng token cũ vẫn có quyền | JWT offline còn hạn | TTL/epoch/denylist/DB entitlement |
| Service boundary thêm `X-Role: ADMIN` | Header không được xóa/xác minh | Gateway mTLS, header stripping, authz contract |

### Quy trình debug an toàn

1. Kiểm tra HTTP **401 hay 403**. Nếu 401, xác minh **issuer, audience, signature, type, expiry**, không chỉnh `hasRole` vội.
2. Với 403, xác định **route vs method vs object/tenant** đã deny.
3. Trong **staging**, inspect **tên authorities** từ authenticated `SecurityContext` sau converter, **không dump raw JWT**.
4. So `hasRole(...)` và `hasAuthority(...)` với authority strings thực tế, có prefix/case đúng.
5. Kiểm tra **AS claim schema** và audience của token, converter `scope`/`scp`, role allowlist.
6. Kiểm tra role data source và **staleness** (JWT TTL, DB membership, cache, revocation events).
7. Thêm regression test positive/negative: **role-only**, **scope-only**, **both**, **neither**, **wrong audience**, **cross tenant**.

## 28. Case study: Refund API có ba tầng quyền

Hệ thống minh họa có:

- Client `finance-portal` sử dụng OAuth Authorization Code + PKCE.
- AS `https://auth.example.test` cấp JWT access token cho **Refund API** audience `https://refunds-api.example.test`.
- Chính sách duyệt hoàn tiền đòi **scope `refunds:approve`**, **role `FINANCE_APPROVER`** và **giới hạn số tiền/two-person approval**.
- User `U42` là Finance Approver **trong tenant A**, không phải tenant B.

### Token A: đúng scope nhưng không có role

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "U42",
  "aud": "https://refunds-api.example.test",
  "scope": "refunds:approve",
  "app_roles": [],
  "tenant": "A",
  "exp": 1800003600
}
~~~

Spring converter tạo **`SCOPE_refunds:approve`** nhưng không có **`ROLE_FINANCE_APPROVER`**. Nếu endpoint yêu cầu **AND**, request **403** — đúng thiết kế.

### Token B: đúng role nhưng thiếu scope

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "U42",
  "aud": "https://refunds-api.example.test",
  "scope": "refunds:read",
  "app_roles": ["FINANCE_APPROVER"],
  "tenant": "A",
  "exp": 1800003600
}
~~~

Với mapping cho phép `FINANCE_APPROVER`, có **`ROLE_FINANCE_APPROVER`** nhưng **không có `SCOPE_refunds:approve`**. Không được cho vượt chỉ vì role cao: request **403 insufficient_scope**.

### Token C: đủ role/scope nhưng sai audience

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "U42",
  "aud": "https://billing-api.example.test",
  "scope": "refunds:approve",
  "app_roles": ["FINANCE_APPROVER"],
  "tenant": "A",
  "exp": 1800003600
}
~~~

Refund API phải trả **401 invalid_token** do **audience mismatch** trước khi map role hoặc chạy `@PreAuthorize`.

### Token D: đúng role/scope/audience nhưng tenant sai

Token có scope và role thích hợp cho tenant A, request lại thao tác refund thuộc tenant B. **403 hoặc 404** theo privacy policy; token **không** vượt tenant boundary nhờ `ROLE_FINANCE_APPROVER`.

### Token E: đủ điều kiện nhưng thiếu dual approval

Một user có quyền thực hiện thao tác trong hạn mức nhưng policy yêu cầu **hai người duyệt độc lập**. Đây là **authorization/business policy**; đừng giả mạo OAuth error `invalid_token` hoặc thêm `ROLE_SUPER_ADMIN` để bỏ bước dual approval.

**Tổng kết case:** `ROLE_` là thông tin về chức năng, `SCOPE_` là quyền trên access token, **`aud`** xác định RS nhận, còn **tenant/object constraints** bảo vệ dữ liệu cụ thể. Mỗi lớp cần được kiểm tra và audit độc lập.

## 29. Ma trận kiểm thử role prefix và scope mapping

| Test | Kịch bản | Kết quả mong đợi |
|---|---|---|
| **T1 — hasRole positive** | Authorities `ROLE_ADMIN`, `hasRole("ADMIN")` | **Allow** theo role check |
| **T2 — hasRole negative** | Authorities `ADMIN`, `hasRole("ADMIN")` | **Deny** theo default prefix |
| **T3 — hasAuthority exact** | Authorities `ROLE_ADMIN`, `hasAuthority("ROLE_ADMIN")` | Allow |
| **T4 — hasAuthority without prefix** | Authorities `ROLE_ADMIN`, `hasAuthority("ADMIN")` | Deny |
| **T5 — Wrong case** | `ROLE_ADMIN` vs `hasRole("admin")` | Deny |
| **T6 — Wrong hasRole argument** | `hasRole("ROLE_ADMIN")` ở API bắt role name trần | Fail configuration/test; không tự bỏ prefix mù |
| **T7 — hasAnyRole** | `ROLE_SUPPORT`, `hasAnyRole("ADMIN","SUPPORT")` | Allow |
| **T8 — Scope default** | JWT `scope="orders:read"` | Có `SCOPE_orders:read` |
| **T9 — Multiple scopes** | `scope="orders:read orders:write"` | Hai SCOPE_ authorities |
| **T10 — Scope array** | `scp=["orders:read","profile"]` theo AS contract | Mapping đúng các phần tử |
| **T11 — Unknown scope claim** | AS dùng claim custom không được config | Deny until mapped by trusted contract |
| **T12 — Scope exact** | `orders:read:any` thay `orders:read` | Không match substring |
| **T13 — Scope case** | `Orders:Read` thay `orders:read` | Deny exact |
| **T14 — Scope vs role** | Chỉ `SCOPE_admin`, method `hasRole("ADMIN")` | Deny |
| **T15 — Role vs scope** | Chỉ `ROLE_ADMIN`, method `hasAuthority("SCOPE_admin:manage")` | Deny |
| **T16 — AND** | `ROLE_ADMIN` + `SCOPE_admin:manage` | Qua hai checks, còn object policy |
| **T17 — Role only missing scope** | `ROLE_ADMIN`, không scope cần | 403 |
| **T18 — Scope only missing role** | `SCOPE_refunds:approve`, thiếu `ROLE_FINANCE_APPROVER` | 403 |
| **T19 — Role claim allowlist** | `app_roles=["SUPPORT"]` được AS cấp | Map `ROLE_SUPPORT` |
| **T20 — Unknown role** | `app_roles=["GLOBAL_ROOT"]` | Không cấp role; schema policy reject/alert |
| **T21 — Double prefix** | `app_roles=["ROLE_ADMIN"]` | Không tạo `ROLE_ROLE_ADMIN` |
| **T22 — Wrong role claim type** | `app_roles="ADMIN"` nhưng contract array | Không cấp quyền; reject/alert theo policy |
| **T23 — Forged HTTP header** | Client gửi `X-Role: ADMIN` | Không có `ROLE_ADMIN` từ header |
| **T24 — Unsigned JWT** | Payload tự gắn `app_roles=["ADMIN"]` | 401 invalid_token |
| **T25 — Tampered signature** | Role claim bị sửa sau ký | 401 invalid_token |
| **T26 — Wrong issuer** | Token trusted elsewhere, sai `iss` | 401 |
| **T27 — Wrong audience** | Billing AT có role admin gửi Orders | 401 |
| **T28 — ID token substitution** | OIDC ID token có role claim gửi RS | 401, sai token purpose |
| **T29 — Refresh token substitution** | RT trình như access token | 401 |
| **T30 — Expired JWT** | `now >= exp` | 401 trước khi authorize |
| **T31 — Revoked opaque** | Introspection `active:false` | 401 |
| **T32 — Introspection active** | `active:true` và đúng contract | Map scopes, sau đó route checks |
| **T33 — Introspection wrong aud** | Active token dành API khác | 401/deny |
| **T34 — AS outage** | Introspection timeout | Fail closed; dependency 5xx, không auto-role |
| **T35 — RS credential invalid** | AS introspection trả 401 | Dependency/auth service problem, không cáo user |
| **T36 — Client credentials grant** | Service AT scope=orders:dispatch | Không tạo user admin role tự động |
| **T37 — Cross-tenant admin** | Admin tenant A thao tác tenant B | Deny ACL 403/404 |
| **T38 — Same role different app** | Billing role ADMIN dùng Orders policy | Không tự map thành Orders ADMIN |
| **T39 — App role stale** | IAM revoke ADMIN, JWT cũ chưa exp | Test behavior TTL/epoch/denylist theo SLA |
| **T40 — Scope revoked** | AS revoke grant, RS cache introspection | Test propagation/cache TTL |
| **T41 — Missing @EnableMethodSecurity** | Annotation `@PreAuthorize` không được enable | Integration test phải bắt lỗi |
| **T42 — Self invocation** | Secured method gọi nội bộ bypass proxy | Test phát hiện đường không được intercept |
| **T43 — URL permitAll** | Endpoint public có policy riêng | Không tự tạo authenticated roles |
| **T44 — Default deny routes** | Unknown API path | Deny by default |
| **T45 — OPTIONS CORS** | Preflight từ trusted origin không Bearer | CORS policy xử lý, không cấp business rights |
| **T46 — CSRF mixed app** | Cookie-auth endpoint thiếu token CSRF | Deny; không tắt CSRF toàn app |
| **T47 — Role hierarchy** | `ROLE_ADMIN > ROLE_USER` được config | Kế thừa role khi manager hỗ trợ |
| **T48 — No implicit scope hierarchy** | ROLE_ADMIN nhưng thiếu `SCOPE_orders:write` | Không cấp scope mới |
| **T49 — Custom prefix** | App thay defaultRolePrefix | Test route + method + Java managers |
| **T50 — Multiple authentication providers** | Session UserDetails role khác Jwt roles | Test map authority từng flow |
| **T51 — Nested IdP role claim** | `resource_access.orders-api.roles` | Chỉ đọc đúng resource contract |
| **T52 — Wrong realm claim** | Realm role không dành cho app | Không map sang app admin |
| **T53 — String injection** | Role chứa whitespace/prefix/colon lạ | Không vượt allowlist/schema |
| **T54 — Role mapping removed scopes** | Custom converter chỉ trả role | Test fail vì mất `SCOPE_` authority |
| **T55 — Wrong JWT typ** | ID-token/unknown typ gửi API RFC9068 | Reject token theo profile |
| **T56 — Object ownership** | Role/scope đúng nhưng owner sai | Deny object policy |
| **T57 — Fine-grained ABAC** | Refund amount vượt hạn mức | Deny theo transaction policy |
| **T58 — Token exchange** | Orders gọi Shipping | Chỉ dùng token audience Shipping và delegated scopes |
| **T59 — Header forgery gateway** | Client tự gửi `X-User-Roles` | Strip/verify internal context |
| **T60 — Unknown kid** | JWT header key ID lạ | No attacker URL fetch, fail closed |
| **T61 — 401 invalid token** | Wrong audience or expired token | `WWW-Authenticate: Bearer invalid_token` |
| **T62 — 403 insufficient scope** | Valid token thiếu scope | 403, không refresh vô hạn |
| **T63 — 403 role deny** | Valid token có scope, thiếu app role | 403 generic, không giả `insufficient_scope` |
| **T64 — 404 conceal** | Không có quyền biết object có tồn tại | 404 theo policy nhất quán |
| **T65 — Log canary** | Token giả qua staging APM/proxy | Không log raw JWT/RT/client secret |
| **T66 — Authorization audit** | Route deny role/scope/tenant | Event reason tách biệt, có correlation |
| **T67 — Role-specific regression** | Thêm role mới vào AS | Không cấp production role trước allowlist/policy review |
| **T68 — Cross-service user role** | Service B nhận role header từ A | Không tin nếu thiếu authenticated boundary |
| **T69 — Legit admin success** | Valid AT, correct aud, scope, role, ACL | 2xx phù hợp business operation |
| **T70 — Method check AND** | Refund approval cần role + scope | Chỉ pass nếu đủ cả hai và object rule |

**Test phải có cả token hợp lệ về chữ ký nhưng sai audience**, không chỉ JWT chữ ký hỏng; và có cả **scope-only / role-only / both / neither**. Các unit tests thuần mock authority strings **không đủ** để chứng minh JwtDecoder + converter + method security + gateway thực sự hoạt động.

## 30. Checklist áp dụng trong production

1. **Định nghĩa authority vocabulary**: `ROLE_` cho role của ứng dụng; `SCOPE_` cho OAuth scopes; không nhập nhằng.
2. Giữ quy tắc **`hasRole("ADMIN")` ↔ `ROLE_ADMIN`**, `hasAuthority("...")` exact theo convention; không thêm prefix hai lần.
3. **Ghi rõ AS token contract**: JWT/opaque, issuer, audience, token type, `scope`/`scp`, role claim schema, tenant/resource namespace.
4. **Chỉ map authorities sau khi token đã được xác thực tin cậy** theo signature/introspection, issuer/audience/expiry/purpose.
5. **Không coi role claim là RFC mandatory**; với provider-specific claims, chọn đường dẫn/resource phù hợp.
6. **Map scope bằng converter nhất quán**, không dùng substring matching và không xóa scope khi thêm role converter.
7. **Allowlist app roles**, kiểm tra schema/case/prefix, không cấp dynamic role tùy input.
8. **Không lấy role từ header/body/query do client đặt**; JWT signature cũng không đủ nếu aud/tenant sai.
9. **Không mặc định scope=admin tạo ROLE_ADMIN**, và không tự cho ROLE_ADMIN mọi scopes.
10. **Kết hợp role + scope + ACL khi policy yêu cầu**; không thay AND bằng OR do tiện coding.
11. **Tách user roles và service client-credentials permissions**, không tự giả mạo principal người dùng.
12. **Bảo vệ tenant isolation**, role ở tenant A không áp cho tenant B.
13. **Bật method security thực sự**, test @PreAuthorize/proxy/self-invocation và deny-by-default.
14. **Dùng SecurityFilterChain scoped đúng**: Bearer-only API có thể có CSRF policy khác cookie-auth web; không tắt CSRF toàn hệ thống.
15. **Cấu hình CORS allowlist và OPTIONS preflight** riêng, không coi permitAll là unrestricted cross-origin access.
16. **Validate token purpose/`typ` theo AS profile**; không nhận ID token/refresh token như API access token.
17. **Giới hạn token staleness**: thời hạn, revoke, role epoch/denylist/DB entitlements theo risk.
18. **Tách 401 authentication failure với 403 authorization failure**, và object policy 403/404.
19. **Không gắn `insufficient_scope` cho mọi 403** do role/tenant/CSRF/object ACL.
20. **Dùng integration tests qua gateway/RS**, với positive/negative cases scope/role/audience.
21. **Audit và monitoring an toàn**: reason categories, mapping version, no raw token/secret.
22. **Không mở rộng cấp quyền âm thầm** khi IdP thay schema, claim hoặc role name.
23. **Document role hierarchy** và phạm vi effect; hierarchy không tự tạo OAuth scopes.
24. **Test multi-tenant, microservice delegation, client_credentials** trước release.
25. **Rà soát method/route/object authorization khi thêm endpoint**, không chỉ khi sửa token converter.

### Tài liệu tham khảo

- [Spring Security — Authorization architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): authorities, role prefix và authorization decision model.
- [Spring Security — Authorize HTTP requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `hasRole`, `hasAuthority` và route policy.
- [Spring Security — Method security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@PreAuthorize`, role/authority expression.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JwtGrantedAuthoritiesConverter, JwtAuthenticationConverter và JWT validation.
- [Spring Security — OAuth2 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection, authorities và token validation.
- [Spring Security — Authentication architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): SecurityContext, Authentication, GrantedAuthority.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): scopes, OAuth roles, access/refresh tokens và grants.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): token usage, invalid_token, insufficient_scope.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active`/metadata cho opaque tokens.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token claims/type, `scope`/`aud` validation.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): token replay, audience restriction, grant security.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): verify JWT và cross-JWT confusion.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): actor/delegation và audience giữa services.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): resource targeting của access token.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token và distinction với OAuth access token.
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): object/tenant ACL.
- [OWASP OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): access token và OAuth threat controls.

**Kết luận:** Trong Spring Security, **`ROLE_` là convention cho role authority**, còn **`SCOPE_` là converter convention thường dùng với OAuth scopes**. `hasRole("ADMIN")` thường tìm **`ROLE_ADMIN`**, trong khi `hasAuthority("SCOPE_orders:read")` yêu cầu đúng **`SCOPE_orders:read`**. Hai authority types không thay nhau và không tự được tạo bởi mọi token. Để phân quyền chính xác, **verify access token trước, map claims từ AS/DB tin cậy, ràng buộc issuer/audience/tenant, kiểm tra scope và role theo policy, rồi kiểm tra object ACL**. Áp dụng đúng thứ tự này giúp ngăn cross-resource token confusion, role injection, nhầm scope thành quyền admin, và 403 khó debug ở Spring Security.
