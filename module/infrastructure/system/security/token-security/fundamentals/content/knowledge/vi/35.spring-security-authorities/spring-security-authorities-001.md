# GrantedAuthority từ scope

Giả sử Invoice API của một hệ thống Java dùng **Spring Security 6** để bảo vệ endpoint `GET /api/invoices/INV-42`. Authorization Server (AS) phát **access token** với scope `invoice:read`. Resource Server (RS) kiểm token hợp lệ, Spring chuyển scope này thành một `GrantedAuthority` mang tên **`SCOPE_invoice:read`**, rồi kiểm quyền tại route hoặc method:

~~~java
@PreAuthorize("hasAuthority('SCOPE_invoice:read')")
public InvoiceDto findInvoice(String invoiceId) {
    // Vẫn phải kiểm user có quyền với CHÍNH hóa đơn này.
    return invoiceService.loadAuthorizedInvoice(invoiceId);
}
~~~

Đoạn mã có ý nghĩa **chỉ khi** người dùng/ứng dụng đã được xác thực bởi trusted access-token validation pipeline, Spring đã bật **method security**, và phần business code thực hiện kiểm quyền object. Việc token chứa `scope=invoice:read` **không có nghĩa** người cầm token được xem mọi hóa đơn của mọi tenant.

Bài **“GrantedAuthority từ scope”** thuộc chương **Spring Security authorities** của module **Security Token Security Fundamentals**. Trọng tâm là đường đi từ **OAuth 2.0 scope trong JWT hoặc opaque token** đến **`GrantedAuthority`/`Authentication`** trong Spring Security, cách cấu hình `JwtGrantedAuthoritiesConverter`, `JwtAuthenticationConverter`, opaque introspection, `hasAuthority` so với `hasRole`, xử lý multi-issuer/multi-tenant và kiểm thử các lỗi phân quyền.

**Nguyên tắc xuyên suốt:** **Scope là quyền được Authorization Server cấp cho một access token; `GrantedAuthority` là cách Spring Security biểu diễn quyền trong một phiên xác thực.** Mapping scope → authority phải dựa trên **token đã được xác minh**, theo **issuer, audience, token type và chính sách của chính API**. Mapping đúng không thay authorization đối tượng, xác minh token, giới hạn scope, revoke hoặc chống token bị đánh cắp/phát lại.

## 1. Bốn tầng phải phân biệt: token, scope, authority và quyền nghiệp vụ

Một request đến Invoice API đi qua những tầng độc lập:

~~~mermaid
flowchart TD
    A["Client gửi access token"] --> B{"RS xác minh JWT hoặc introspection"}
    B -- "Token sai/expired/inactive" --> X["401 Unauthorized / invalid_token"]
    B -- "Hợp lệ" --> C["Lấy trusted scope/scp metadata"]
    C --> D["Converter: scope -> GrantedAuthority SCOPE_*"]
    D --> E["Authentication trong SecurityContext"]
    E --> F{"Route/method yêu cầu đúng authority?"}
    F -- "Không" --> Y["403 Forbidden / insufficient_scope khi phù hợp"]
    F -- "Có" --> G{"Tenant, ownership và policy đối tượng?"}
    G -- "Không" --> Y
    G -- "Có" --> H["Thực hiện API và audit"]
~~~

| Khái niệm | Thuộc về | Ví dụ | Câu hỏi nó trả lời |
|---|---|---|---|
| **Access token** | OAuth 2.0, do AS cấp | JWT JWS, JWE hoặc opaque string | Credential nào đang được trình tới RS? |
| **Scope** | AS cấp cho grant/token, RS hiểu theo contract | `invoice:read`, `invoice:write` | Token được phép thực hiện **loại thao tác** nào? |
| **`GrantedAuthority`** | Spring Security | `SimpleGrantedAuthority("SCOPE_invoice:read")` | Spring đã map claim thành một quyền ứng dụng ra sao? |
| **`Authentication`** | Spring Security | `JwtAuthenticationToken` / `BearerTokenAuthentication` | Principal nào đã được xác thực và có authorities nào? |
| **Domain/business permission** | Application/Resource Server | “An được xem hóa đơn INV-42 của tenant A” | Actor có quyền trên **đối tượng cụ thể** không? |

**Không đánh đồng `scope` với vai trò `ROLE_ADMIN`**, và cũng không coi `Authentication.isAuthenticated() == true` là bằng chứng user có quyền làm mọi thao tác.

### Hai quyết định khác nhau

~~~text
Route-level permission:
  Does Authentication have "SCOPE_invoice:read"?

Object-level permission:
  Does current issuer+subject/client+tenant have read access
  to invoice INV-42?
~~~

Thứ nhất có thể kiểm bằng Spring `hasAuthority`. Thứ hai thường cần domain service, repository query đã giới hạn owner/tenant hoặc một authorization policy engine. Bỏ tầng thứ hai có thể tạo **BOLA/IDOR** dù OAuth token hoàn toàn hợp lệ.

## 2. Scope OAuth 2.0 là gì và vì sao chỉ scope được cấp mới có giá trị?

Theo OAuth 2.0, `scope` mô tả phạm vi quyền được đề nghị và được AS cấp theo chính sách. Client có thể *request* scope, nhưng **AS quyết định grant cuối cùng**. Request:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <redacted-client-authentication>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=invoice%3Aread
~~~

Không phải lời tuyên bố “Client xin `invoice:admin` thì lập tức có `invoice:admin`”. AS phải kiểm client registration, grant type, user consent/delegation khi có, resource/audience và policy trước khi cấp token.

### Access token JWT minh họa

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user:an",
  "aud": ["invoice-api"],
  "client_id": "invoice-web",
  "scope": "invoice:read invoice:export",
  "iat": 1800000000,
  "nbf": 1800000000,
  "exp": 1800000900,
  "jti": "token-id-illustrative-001"
}
~~~

Đây là **payload minh họa**, chưa phải một JWT đã được ký. Bất kỳ ai cũng có thể viết JSON như vậy; RS chỉ được tin claims **sau** khi signature/issuer/audience/time/token type đã được kiểm hoặc sau introspection trusted.

### Cú pháp scope thường là một chuỗi có các phần tử phân tách bằng dấu cách

~~~text
scope = "invoice:read invoice:export"

Parsed scopes:
  "invoice:read"
  "invoice:export"

DO NOT:
  "invoice:read" in "invoice:read-all" by substring
~~~

Trong RFC 6749, một chuỗi scope là **danh sách scope-token phân cách bằng SP**; từng token có định danh riêng. `invoice:read-all` không tự tương đương `invoice:read`. Scope **có thể mang dạng phân cấp theo convention của AS**, nhưng **không có quyền kế thừa “admin implies read” mặc định từ OAuth hoặc Spring**.

### Scope, audience và resource indicator

Hai token có cùng scope nhưng audience khác nhau:

~~~text
Token A:
  iss=https://auth.example.test
  aud=invoice-api
  scope=read

Token B:
  iss=https://auth.example.test
  aud=payroll-api
  scope=read
~~~

**Invoice API phải từ chối token B**, dù `read` có vẻ phù hợp. Scope được diễn giải trong **ngữ cảnh issuer + resource/audience + API contract**. RFC 8707 Resource Indicators có thể giúp AS cấp token đúng tài nguyên; RS vẫn phải kiểm audience.

### Client credentials không đại diện cho người dùng cuối

Token từ `client_credentials` có thể đại diện cho **workload/client identity**, không cho `sub=user:an`. Nếu nó mang `invoice:read`, API có thể cho **service** đọc hóa đơn theo một workload permission riêng; không được tự gán người dùng An hoặc bỏ tenant isolation.

## 3. `GrantedAuthority`: giá trị quyền mà Spring hiểu

Trong Spring Security, interface `GrantedAuthority` biểu diễn một quyền được gắn với `Authentication`. Với quyền đơn giản, framework thường dùng `SimpleGrantedAuthority`:

~~~java
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

GrantedAuthority readInvoice =
    new SimpleGrantedAuthority("SCOPE_invoice:read");

String value = readInvoice.getAuthority();
// value = "SCOPE_invoice:read"
~~~

### `Authentication` gói principal và authorities

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;

Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

if (authentication != null && authentication.isAuthenticated()) {
    for (GrantedAuthority authority :
            authentication.getAuthorities()) {
        // Chỉ log loại quyết định đã khử nhạy cảm nếu cần;
        // không log raw bearer token/principal secrets.
        String name = authority.getAuthority();
    }
}
~~~

**Không tạo một `Authentication` với `authenticated=true` từ `scope` do browser gửi trong JSON body.** Framework phải tạo principal sau trusted authentication provider: JWT verification, opaque introspection, session authentication hoặc một mechanism được review.

### `GrantedAuthority` không phải tự nhiên đến từ mọi JWT claim

JWT có thể chứa:

~~~json
{
  "scope": "invoice:read",
  "custom_permissions": ["print"],
  "role": "superadmin"
}
~~~

Spring Security **không mặc định chuyển mọi claim thành authority**. Mapping phụ thuộc converter và token profile. Một custom converter có thể thêm roles/permissions, nhưng không được biến các claims **chưa được AS cấp quyền và RS thỏa thuận** thành quyền admin.

### Authority thường là chuỗi, không phải ACL hoàn chỉnh

`SCOPE_invoice:read` chỉ là một tên authority. Không có thông tin record `INV-42`, tenant `A`, người thụ hưởng, số tiền hay điều kiện thời gian trong chuỗi đó. Nếu hệ thống cố nhồi mọi object ID vào scope, token/authority có thể phình to, khó revoke và không phản ánh quyền động. Dùng domain authorization khi cần.

## 4. Default mapping: từ `scope`/`scp` sang `SCOPE_*` trong JWT

Trong Spring Security OAuth2 Resource Server, **`JwtGrantedAuthoritiesConverter`** có thể đọc claims thường gặp `scope` hoặc `scp` của `Jwt` và tạo `GrantedAuthority` với **prefix mặc định `SCOPE_`**.

~~~json
{
  "sub": "user:an",
  "scope": "invoice:read invoice:export",
  "aud": ["invoice-api"]
}
~~~

Các authorities kỳ vọng với converter mặc định:

~~~text
SCOPE_invoice:read
SCOPE_invoice:export
~~~

Một token có thể dùng `scp` tùy issuer/contract:

~~~json
{
  "sub": "user:an",
  "scp": ["invoice:read", "invoice:export"]
}
~~~

Trong các phiên bản Spring Security 6.x phổ biến, converter hỗ trợ well-known authorities claims, trong đó có `scope` và `scp`, và xử lý string/collection theo contract. **Đừng dựa vào suy đoán nếu AS đưa cả hai claims với giá trị khác nhau**: cần chọn một nguồn authoritative rõ bằng cấu hình, kiểm dependency/version và viết test.

### Luồng mặc định của JWT Resource Server

~~~text
HTTP request:
  Authorization: Bearer <signed-jwt-access-token>
       |
       v
BearerTokenAuthenticationFilter
       |
       v
JwtAuthenticationProvider
       |
       +-- JwtDecoder.decode(token):
       |      verify JWS + configured issuer/expiry/audience validators
       |
       +-- JwtAuthenticationConverter:
              JwtGrantedAuthoritiesConverter -> SCOPE_invoice:read
       |
       v
JwtAuthenticationToken(principal=Jwt, authorities)
       |
       v
AuthorizationManager / @PreAuthorize / business authorization
~~~

**Trật tự là yếu tố bảo mật:** Không đọc `scope` từ `Jwt` payload chưa verify rồi cấp `SimpleGrantedAuthority`. Đầu tiên RS phải xác thực JWT đúng issuer/JWKS/algorithm/time/audience/token type, sau đó mới map scopes.

### Prefix `SCOPE_` do Spring tạo, không phải OAuth claim

~~~text
JWT claim:      scope = "invoice:read"
Spring authority:     "SCOPE_invoice:read"

JWT claim:      scope = "invoice:write"
Spring authority:     "SCOPE_invoice:write"
~~~

OAuth scope **không nhất thiết chứa chuỗi `SCOPE_`**. Nếu token bất ngờ chứa `scope="SCOPE_invoice:read"`, converter mặc định có thể tạo `SCOPE_SCOPE_invoice:read`; đó thường là lỗi contract/claim mapping. Đừng sửa bằng cách bắt đầu so sánh substring.

## 5. `hasAuthority`, `hasRole` và `ROLE_` khác nhau thế nào?

`hasAuthority` kiểm **tên authority chính xác**. `hasRole` thường áp **role prefix `ROLE_`** theo Spring Security conventions; hệ thống có thể cấu hình role prefix khác, nên phải kiểm application configuration.

~~~java
// Scope authority:
@PreAuthorize("hasAuthority('SCOPE_invoice:read')")

// Role authority:
@PreAuthorize("hasRole('ADMIN')")
// Thông thường kiểm authority "ROLE_ADMIN".

// Tên exact:
@PreAuthorize("hasAuthority('ROLE_ADMIN')")
~~~

| Điều kiện | Thực tế thường kiểm | Token chỉ có `scope=invoice:read` có đáp ứng? |
|---|---|---|
| `hasAuthority("SCOPE_invoice:read")` | Authority đúng chuỗi đó | **Có**, nếu converter đã map chuẩn |
| `hasAuthority("invoice:read")` | Authority không prefix | **Không** theo converter mặc định |
| `hasRole("invoice:read")` | Thường `ROLE_invoice:read` | **Không**, vì scope không thành role |
| `hasRole("ADMIN")` | Thường `ROLE_ADMIN` | **Không**, trừ khi app cấp role có kiểm |
| `isAuthenticated()` | Authentication được framework coi đã xác thực | **Không chứng minh có scope cần thiết** |
| `permitAll()` | Bỏ điều kiện authentication/authorization ở matcher này | **Không** thích hợp cho private business API |

### Anti-pattern thường gặp

~~~java
// SAI với JWT default scope -> SCOPE_invoice:read.
@PreAuthorize("hasRole('invoice:read')")
public InvoiceDto getInvoice(String id) { /* ... */ }
~~~

Lỗi phổ biến có hai dạng:

1. **False deny:** Token có scope nhưng method kiểm sai prefix, dẫn tới 403.
2. **Privilege escalation:** Developer thấy lỗi rồi cho `permitAll()` hoặc đổi prefix global không kiểm toàn bộ role policy, vô tình mở endpoint.

**Cách sửa đúng:** xác định source claim và converter output, sau đó sử dụng `hasAuthority("SCOPE_invoice:read")` hoặc custom mapping **được thiết kế và kiểm thử nhất quán**.

### Không tự suy roles từ scope

`scope=invoice:admin` **không tự sinh** `ROLE_ADMIN`. Nếu hệ thống có chính sách ánh xạ một OAuth scope thành application role, hãy khai báo **chính sách explicit theo issuer/resource/client**, không dùng `replace("SCOPE_", "ROLE_")` để “tiện lợi”.

## 6. Đừng để converter trở thành lỗ hổng authorization

Converter chạy sau xác thực nhưng **đầu vào scope vẫn phản ánh quyền AS cấp theo một contract**. Rủi ro xuất hiện khi:

- RS tin **issuer sai**, không kiểm audience hoặc chấp nhận ID token thay access token.
- AS cấp scope chưa giới hạn theo client/resource nhưng RS xem như quyền toàn cục.
- Converter map một custom claim như `user_supplied_roles` thành `ROLE_ADMIN`.
- Multi-issuer RS gộp scope của hai nhà cung cấp không cùng nghĩa.
- Code đặt `SCOPE_*` vào authentication trước khi token được verify.
- Ứng dụng map `scope=read` thành quyền `read-all-tenants` không có tenant binding.
- Quyền bị revoke nhưng **JWT cũ còn `exp`**, còn converter vẫn map claims cũ.

### Threat model ngắn

~~~text
AS-A issues JWT for Payroll API:
  aud=payroll-api
  scope=admin

Invoice API mistakenly validates signature only:
  decode token -> map "admin" -> SCOPE_admin
  route checks SCOPE_admin
  -> unauthorized cross-API access

Correct:
  verify trusted issuer, exact invoice-api audience,
  token purpose and lifetime BEFORE authority mapping.
~~~

**Độ tin cậy của `GrantedAuthority` phụ thuộc toàn bộ chuỗi**: AS đã cấp quyền hợp lệ, token được xác minh đúng, converter map đúng semantics, và RS còn thực thi quyền tài nguyên. Một claim đúng cú pháp nhưng sai nguồn hoặc sai audience vẫn phải bị từ chối.

## 7. Spring Security 6: cấu hình JWT Resource Server và route authorities

Ví dụ Invoice API **chỉ nhận access token bằng `Authorization: Bearer` header**, không chấp nhận `HttpSession`/cookie làm authentication tại các API routes. Đây là giả định quan trọng khi cấu hình CSRF và stateless session.

### Trusted issuer và JWKS

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test
          jwk-set-uri: https://auth.example.test/oauth2/jwks
~~~

Hai URI chỉ là **ví dụ**; production phải lấy từ trusted issuer registration/discovery. Khi đặt cả `issuer-uri` và `jwk-set-uri`, Spring Boot/Security phiên bản tương thích có thể dùng JWKS URI trực tiếp nhưng vẫn kiểm issuer; **phải xác minh config/version thực tế**. Dù cấu hình đúng, **audience của Invoice API không tự xuất hiện từ tên issuer**: cần validator audience riêng khi API contract yêu cầu.

### Route-level authorization

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class InvoiceJwtRouteSecurity {

    @Bean
    SecurityFilterChain invoiceJwtRoutes(HttpSecurity http)
            throws Exception {
        http
            .securityMatcher("/api/invoices/**")
            // Chỉ dành cho endpoint Bearer-header-only.
            // Nếu chấp nhận browser auth cookie, phải giữ CSRF defense.
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/invoices/**")
                    .hasAuthority("SCOPE_invoice:read")
                .requestMatchers(HttpMethod.POST, "/api/invoices/**")
                    .hasAuthority("SCOPE_invoice:write")
                .requestMatchers(HttpMethod.DELETE, "/api/invoices/**")
                    .hasAuthority("SCOPE_invoice:delete")
                .anyRequest().denyAll())
            .oauth2ResourceServer(rs -> rs.jwt(withDefaults()));

        return http.build();
    }
}
~~~

**Đọc chính xác đoạn cấu hình:** `requestMatchers(HttpMethod.GET, ...).hasAuthority(...)` kiểm authority trên request **sau khi Resource Server đã xác thực JWT**. `STATELESS` chỉ nói không dùng HTTP session để lưu authentication state trên những routes này; nó **không** làm request miễn khỏi issuer/audience/expiry validation.

### Lưu ý filter chain

- `securityMatcher("/api/invoices/**")` giới hạn **filter chain**, còn `requestMatchers` giới hạn quyền **bên trong chain**.
- **Filter chain khác** phải bảo vệ các routes còn lại; nếu không có catch-all an toàn, một endpoint có thể bị bỏ qua các security filters tùy cấu hình.
- Nếu có BFF cùng process dùng browser cookie ở `/web/**`, phải có chain riêng với **CSRF enabled**, session protection và thứ tự matcher đúng.
- Chỉ disable CSRF vì **credential trên route này không được browser tự đính kèm**. Nếu một gateway/bộ lọc khác chấp nhận cookie làm auth, phải đánh giá lại.
- Việc một scope được cấp không thay ownership check tại service/repository.

### `401` hay `403`?

~~~text
No Bearer token / invalid signature / expired token / wrong audience:
  401 Unauthorized (invalid_token when appropriate)

Valid access token but missing SCOPE_invoice:write:
  403 Forbidden (insufficient_scope when appropriate)

Valid scope but invoice belongs to another user:
  403 or 404 according to privacy / resource policy
~~~

Các response và `WWW-Authenticate` details cần tuân **RFC 6750** và policy che thông tin về tài nguyên. Đừng chuyển lỗi thiếu quyền thành `permitAll()` để “sửa 403”.

## 8. `JwtGrantedAuthoritiesConverter`: chọn claim và prefix chủ động

Đôi khi AS phát token có `scp` thay vì `scope` hoặc yêu cầu **prefix khác** vì application đã có naming convention riêng.

### Khi AS dùng `scp`

~~~json
{
  "iss": "https://auth.example.test",
  "aud": ["invoice-api"],
  "sub": "user:an",
  "scp": ["invoice:read", "invoice:export"],
  "exp": 1800000900
}
~~~

Ánh xạ tường minh:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Configuration
class InvoiceScopeMapping {

    @Bean
    JwtAuthenticationConverter invoiceJwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter scopes =
            new JwtGrantedAuthoritiesConverter();

        // Không phụ thuộc "scope" hay "scp" được tự phát hiện
        // khi token của AS có contract rõ ràng.
        scopes.setAuthoritiesClaimName("scp");
        scopes.setAuthorityPrefix("SCOPE_");

        JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(scopes);
        return converter;
    }
}
~~~

Bean converter chỉ có tác dụng khi được **wiring vào Resource Server JWT authentication pipeline**; một cách làm rõ ràng trong cùng `SecurityFilterChain`:

~~~java
.oauth2ResourceServer(rs -> rs
    .jwt(jwt -> jwt.jwtAuthenticationConverter(
        invoiceJwtAuthenticationConverter
    )))
~~~

Trong snippet, `invoiceJwtAuthenticationConverter` là **biến/bean đã được inject** vào phương thức cấu hình (không phải một tên có sẵn của framework). Các dòng trên là **một mảnh DSL để gắn vào chain**, không phải file Java độc lập.

**Không cấu hình `scp` khi AS thực tế chỉ trả `scope`**, nếu không mọi request có thể nhận empty authorities và bị 403. Tương tự, nếu AS trả cả `scope` và `scp` nhưng với giá trị khác nhau, phải chọn **nguồn authoritative** theo hợp đồng AS/RS; không tự cộng tất cả để mở quyền.

### Thay prefix có rủi ro gì?

~~~java
scopes.setAuthorityPrefix("PERM_");
// scope "invoice:read" -> authority "PERM_invoice:read"
~~~

Khi đổi prefix, mọi `hasAuthority("SCOPE_invoice:read")` cũ **không còn khớp**. Nếu muốn tiếp tục dùng conventions Spring Resource Server, giữ `SCOPE_` trừ khi có lý do rõ và test toàn bộ method/web rules.

Có thể đặt prefix rỗng trong các profile cần thiết, nhưng cách đó dễ gây **va chạm tên** giữa scope và roles hoặc internal authorities. Hãy đặt namespace có chủ đích thay vì xóa prefix chỉ để viết ít ký tự trong `@PreAuthorize`.

### Khi `scope` là chuỗi chứa dấu cách

~~~text
scope="invoice:read invoice:export"

Expected:
  SCOPE_invoice:read
  SCOPE_invoice:export
~~~

Một số Spring Security versions cho phép tùy biến delimiter của converter; không dựa vào tùy chọn đó nếu dependency/version không hỗ trợ. Với claims có schema đặc biệt, **nên normalize ở một converter explicit đã được test** thay vì dùng parser tự `split(",")` trên dữ liệu có semantics chưa rõ.

### Không suy ra scope từ `aud` hoặc `sub`

~~~text
aud = invoice-api
sub = user:an
scope = invoice:read

Wrong mapping:
  aud=invoice-api -> SCOPE_invoice:admin

Correct:
  scope claim -> SCOPE_invoice:read
  aud claim   -> validated resource binding
  sub claim   -> validated principal identity
~~~

Ba claims có tác dụng khác nhau; đừng biến việc token dành cho API thành một scope admin.

## 9. `JwtAuthenticationConverter`: principal name và authorities là hai cấu hình riêng

`JwtAuthenticationConverter` tạo `JwtAuthenticationToken` từ verified JWT, gồm principal và authorities. Ngoài ánh xạ authority, nó có thể cho phép chọn claim dùng làm tên principal:

~~~java
JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
converter.setJwtGrantedAuthoritiesConverter(scopes);
converter.setPrincipalClaimName("sub");
~~~

Với user-delegated access token, `sub` thường mô tả end-user theo issuer. Với `client_credentials`, `sub` có thể là client/workload hoặc không mang nghĩa user, tùy AS profile.

### Chọn `client_id` làm principal name có thể gây nhầm

Nếu đổi:

~~~java
converter.setPrincipalClaimName("client_id");
~~~

thì `Authentication.getName()` có thể trở thành `invoice-web`, **không còn là `user:an`**. Nếu domain service dùng `getName()` để kiểm owner, nó có thể so client ID với user ID và gây bug authorization. **Không đổi principal claim chỉ để hiển thị tên trong log**; xác định rõ actor vs client vs subject.

### Multi-issuer và subject mapping

`sub` thường chỉ unique **trong scope của issuer**. Hai AS có thể phát `sub="123"` cho hai người khác nhau:

~~~text
AS A: iss=https://login-a.example.test, sub=123  -> Alice
AS B: iss=https://login-b.example.test, sub=123  -> Bob

Unsafe identity key:
  subject = "123"

Safer identity key:
  issuer + subject + tenant/trust context
~~~

Nếu ứng dụng chỉ dùng `Authentication.getName()` và bỏ issuer trong multi-issuer, quyền trên object có thể bị gộp nhầm. Một trusted identity adapter nên giữ **issuer, subject, clientId, tenant và loại grant**.

### Nguyên tắc cho custom principal

Không dựng principal bằng `X-User-Id`, `tenant` từ request body hoặc một JWT payload chưa xác minh. Spring converter chỉ được đọc claims từ **trusted decoder output**; business authorization lấy identity từ SecurityContext do framework quản lý.

## 10. JwtDecoder phải xác minh token **trước khi** mapper cấp scope authority

Nếu token là JWS access token, một payload tự chứa `scope=invoice:admin` là **dữ liệu không tin cậy** cho tới khi RS verify:

1. **JWS chữ ký** với AS trusted verification key và algorithm allowlist.
2. **`iss` exact match**, không chấp nhận issuer tự khai.
3. **`aud` chứa invoice-api**, đúng resource của chính RS.
4. **`exp`, `nbf`** và `iat`/max lifetime khi policy yêu cầu.
5. **Token type/purpose** là OAuth access token, không phải OIDC ID token hoặc refresh token.
6. **Sender binding** nếu token là DPoP/mTLS-bound.
7. **Revocation/state** nếu security policy yêu cầu chặn trước expiry.

### Spring JWT validator minh họa

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class TrustedInvoiceJwtValidation {
    private static final String ISSUER =
        "https://auth.example.test";
    private static final String JWKS =
        "https://auth.example.test/oauth2/jwks";

    @Bean
    JwtDecoder invoiceJwtDecoder() {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(JWKS)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            if (jwt.getAudience() != null &&
                jwt.getAudience().contains("invoice-api")) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Unexpected token audience",
                    null));
        };

        // Ví dụ skew=10s; production chọn theo clock drift và TTL.
        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                new JwtIssuerValidator(ISSUER),
                new JwtTimestampValidator(Duration.ofSeconds(10)),
                audience));

        return decoder;
    }
}
~~~

**Quan trọng:** `setJwtValidator` có thể **thay** validator chain mặc định; khi tự cấu hình phải giữ toàn bộ issuer/time/audience/profile validators cần thiết. Snippet cho ba validators cụ thể, **chưa** triển khai mọi yêu cầu `typ`/RFC 9068, DPoP/mTLS và revoke. Những kiểm soát còn thiếu phải được triển khai theo token contract.

### Vì sao mapping scope không thể thay chữ ký và audience?

~~~text
Attacker sends:
  JWT payload:
    scope = "invoice:write"
    iss   = "https://evil.invalid"
    aud   = "invoice-api"

UNSAFE:
  parse payload
  map scope -> SCOPE_invoice:write
  allow POST

SAFE:
  verify trusted AS signature + issuer + aud + time + token purpose
  reject before any scope mapping.
~~~

### Chỉ nhận một token profile đã thỏa thuận

Đừng tự đưa token vào `JwtDecoder` chỉ vì nó có 3 phần ngăn bằng dấu chấm; một **opaque token** vẫn có thể chứa ký tự dấu chấm. Format nên được chọn theo trusted issuer/resource/client contract, không theo input attacker để tránh fallback/downgrade authentication.

## 11. Opaque token: scope thành authority sau introspection `active=true`

Với opaque/reference access token, RS gọi **RFC 7662 Token Introspection** để kiểm trạng thái token:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.test
Authorization: Basic <redacted-rs-credential>
Content-Type: application/x-www-form-urlencoded

token=<percent-encoded-access-token>&token_type_hint=access_token
~~~

Response hợp lệ **minh họa**:

~~~json
{
  "active": true,
  "iss": "https://auth.example.test",
  "sub": "user:an",
  "client_id": "invoice-web",
  "aud": ["invoice-api"],
  "scope": "invoice:read invoice:export",
  "exp": 1800000900,
  "token_type": "Bearer"
}
~~~

Trong Spring Security Opaque Token Resource Server, `OpaqueTokenIntrospector` xử lý thông tin introspection và tạo principal; các scopes có thể được map thành `GrantedAuthority` với prefix **`SCOPE_`** theo pipeline tương ứng. Không có JWS signature verify ở RS đối với một **opaque reference token**, nhưng có yêu cầu **TLS/AS authentication/trusted endpoint** nghiêm ngặt.

### `active=false` luôn phải từ chối

~~~json
{"active": false}
~~~

HTTP introspection **200 OK** với `active=false` **không có quyền**. Không được tạo authenticated principal và authority chỉ vì response 200. Nếu JSON `active` vắng, `null` hoặc chuỗi `"true"` thay vì boolean, **phải reject theo schema/contract**, không ép kiểu lỏng.

### Các fields tùy chọn trong RFC 7662

`iss`, `aud`, `scope`, `exp` có thể **tùy chọn** trong response tùy AS. Nếu Invoice API cần audience isolation hoặc expiry enforcement, **AS/RS phải có contract cung cấp đủ bằng chứng**; không coi thiếu `aud` là “được dùng ở mọi API”. Một token active nhưng không có scope route yêu cầu **không được tự map thành quyền đọc/ghi**.

### Opaque pipeline

~~~text
Authorization: Bearer <opaque-token>
        |
        v
BearerTokenAuthenticationFilter
        |
        v
OpaqueTokenAuthenticationProvider
        |
        v
OpaqueTokenIntrospector.introspect(token)
  trusted AS + RS credential + active check + attributes
        |
        v
Authenticated principal + SCOPE_invoice:read
        |
        v
Route/method authorization + tenant/object ACL
~~~

**Không dùng một converter để bypass `active=false` hoặc tin claims từ client body**. `GrantedAuthority` phải được tạo **sau** introspection thành công và policy validation.

## 12. Spring Security opaque configuration và authority mapping

Ví dụ Boot properties cho **một API opaque-token-only**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.test/oauth2/introspect
          client-id: invoice-resource-server
          client-secret: <secret-from-protected-config>
~~~

Không commit **real introspection client secret** vào Git hoặc Java source. Đây là credential của **RS dùng tại AS**, khác `client_id` của Invoice Web và khác access token mà browser trình.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class InvoiceOpaqueRouteSecurity {
    @Bean
    SecurityFilterChain invoiceOpaqueRoutes(HttpSecurity http)
            throws Exception {
        http
            .securityMatcher("/opaque-api/invoices/**")
            // Chỉ dành cho Bearer header, không nhận auth cookie.
            .csrf(csrf -> csrf.disable())
            .sessionManagement(s -> s
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/opaque-api/invoices/**")
                    .hasAuthority("SCOPE_invoice:read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(rs -> rs
                .opaqueToken(withDefaults()));
        return http.build();
    }
}
~~~

Spring `OpaqueTokenIntrospector` và mapping có thể tùy biến cho AS custom claim schema. Bất kỳ custom introspector nào cũng phải giữ **`active`, issuer/trust, audience, expiry và scope normalization** theo contract; không tự trả mọi caller một authority như `ROLE_ADMIN` cho tiện test.

### JWT và opaque không nhất thiết dùng chung một principal class

Thông thường:

~~~text
JWT:
  JwtAuthenticationToken
  principal = Jwt
  authorities from JwtAuthenticationConverter

Opaque:
  BearerTokenAuthentication
  principal implements OAuth2AuthenticatedPrincipal
  authorities from introspection results
~~~

**Business code không nên phụ thuộc mù quáng vào `@AuthenticationPrincipal Jwt` nếu route cũng hỗ trợ opaque token.** Hãy dùng một trusted adapter tạo domain identity thống nhất (issuer, subject, clientId, tenant, authorities) sau token validation, không parse token string trong controller.

## 13. Custom `OpaqueTokenIntrospector`: kiểm token state trước, rồi map scope

Giả sử AS trả scope trong introspection response như chuỗi:

~~~json
{
  "active": true,
  "iss": "https://auth.example.test",
  "aud": "invoice-api",
  "sub": "user:an",
  "scope": "invoice:read invoice:export",
  "exp": 1800000900
}
~~~

RS muốn áp thêm policy **chỉ ánh xạ các scopes mà Invoice API nhận biết**: `invoice:read`, `invoice:write` và `invoice:export`. Ví dụ decorator sau **giả định delegate là một introspector đáng tin đã xử lý `active` và gọi đúng AS**. Không dùng một delegate trả principal từ body HTTP của caller.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

final class TrustedInvoiceScopeIntrospector
        implements OpaqueTokenIntrospector {

    private static final String ISSUER = "https://auth.example.test";
    private static final String AUDIENCE = "invoice-api";
    private static final Set<String> ALLOWED_SCOPES =
        Set.of("invoice:read", "invoice:write", "invoice:export");

    private final OpaqueTokenIntrospector delegate;
    private final Clock clock;

    TrustedInvoiceScopeIntrospector(
            OpaqueTokenIntrospector delegate,
            Clock clock) {
        this.delegate = delegate;
        this.clock = clock;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String accessToken) {
        // Delegate: HTTPS + RS client authentication,
        // validate active=true (Boolean) with trusted AS.
        OAuth2AuthenticatedPrincipal principal =
            delegate.introspect(accessToken);

        if (!ISSUER.equals(principal.getAttribute("iss"))) {
            throw invalid("Unexpected token issuer");
        }
        if (!audienceMatches(principal.getAttribute("aud"))) {
            throw invalid("Unexpected token audience");
        }

        Instant exp = normalizedExp(principal.getAttribute("exp"));
        if (exp == null || !clock.instant().isBefore(exp)) {
            throw invalid("Token expired or missing exp");
        }

        // Contract ví dụ yêu cầu scope string, không tùy tiện
        // nhận JSON array hoặc một type khác.
        Object rawScope = principal.getAttribute("scope");
        if (!(rawScope instanceof String scopesText)) {
            throw invalid("Unexpected scope schema");
        }

        Set<GrantedAuthority> authorities = new LinkedHashSet<>();
        for (String scope : scopesText.trim().split("\\s+")) {
            if (ALLOWED_SCOPES.contains(scope)) {
                authorities.add(
                    new SimpleGrantedAuthority("SCOPE_" + scope));
            }
        }

        // Không tự nâng custom role từ user-controlled claims.
        return new DefaultOAuth2AuthenticatedPrincipal(
            principal.getName(),
            principal.getAttributes(),
            authorities);
    }

    private static boolean audienceMatches(Object raw) {
        if (raw instanceof String value) {
            return AUDIENCE.equals(value);
        }
        return raw instanceof Collection<?> values &&
            values.contains(AUDIENCE);
    }

    private static Instant normalizedExp(Object raw) {
        if (raw instanceof Instant instant) return instant;
        if (raw instanceof Number epochSeconds) {
            return Instant.ofEpochSecond(epochSeconds.longValue());
        }
        return null;
    }

    private static OAuth2AuthenticationException invalid(String reason) {
        return new OAuth2AuthenticationException(
            new OAuth2Error("invalid_token", reason, null));
    }
}
~~~

### Cách hiểu giới hạn của ví dụ

1. Delegate **đã phải xác minh `active=true`**, AS credentials và TLS. Decorator không kiểm lại `active` ở đây, cũng không tự gửi HTTP request; một delegate làm sai sẽ phá security model.
2. Mục này giả định AS contract **bắt buộc trả `iss`, `aud`, `exp` và `scope`**. RFC 7662 không làm tất cả claims đó bắt buộc; nếu AS khác schema, phải **sửa adapter/contract có kiểm soát**, không default wildcard.
3. Một số introspectors **normalize `scope` thành collection** và `exp` thành `Instant`; snippet cố ý yêu cầu `scope` string. Khi framework/provider có schema khác, test thực tế và hỗ trợ kiểu đã được phê duyệt.
4. Nếu `scope` rỗng, converter tạo **không có SCOPE authorities**. API protected bằng `hasAuthority("SCOPE_invoice:read")` sẽ từ chối.
5. Những scopes không thuộc `ALLOWED_SCOPES` bị **bỏ qua**, không map thành roles. Việc chọn allowlist là chính sách **của Invoice API**; với resource khác phải thiết kế lại.
6. `exp` có thể có precision/kiểu NumericDate khác; production phải validate schema/overflow/clock-skew theo policy. Snippet minh họa strict expiration.
7. Converter không kiểm `client_id`/subject/tenant, DPoP/mTLS và object ownership. Các ràng buộc đó cần được thực thi riêng.
8. **Không để lỗi introspection HTTP 401/5xx/timeout biến thành principal `active=true`**. Fail closed hoặc dùng cache còn hợp lệ theo policy.

### Wiring decorator tránh circular dependency

Trong Spring, một `@Bean OpaqueTokenIntrospector` không nên inject một bean **cùng loại** mà chính nó cung cấp mà không có `@Qualifier`/khởi tạo rõ: dễ xảy ra circular dependency. Hãy tạo **trusted delegate** bằng provider-supported builder/class, hoặc đăng ký một bean riêng với qualifier, sau đó wrap:

~~~text
Trusted AS HTTP introspector (qualified "trustedDelegate")
   |
   v
TrustedInvoiceScopeIntrospector(trustedDelegate, Clock.systemUTC())
   |
   v
OAuth2 Resource Server opaqueToken authentication
~~~

Các class/builder tạo delegate thay đổi theo **phiên bản Spring Security**; xác nhận đúng signature và authentication method (Basic/mTLS/khác) thay vì copy một constructor không có trong dependency. Khi ghi test, **mock delegate trả verified principal**, không để test decorator vô tình bỏ kiểm HTTP `active=false` của provider.

### Audit mapping từ scope thành authority

~~~text
AS scope (trusted):    invoice:read invoice:export
RS allowlisted scopes: invoice:read, invoice:write, invoice:export
Mapped authorities:   SCOPE_invoice:read, SCOPE_invoice:export

Not mapped:
  ROLE_ADMIN
  SCOPE_payroll:write
  SCOPE_invoice:write   (not granted by AS)
~~~

**Tuyệt đối không tự thêm `SCOPE_invoice:write` chỉ vì client có `invoice:read`**. Quyền ghi là một quyền khác, phải được AS cấp hoặc được domain policy cấp rõ ràng theo một mô hình tách biệt.

## 14. Method security: `@PreAuthorize` dùng authority và policy object

Route-level check ngăn request không có scope cần thiết. **Method security** giúp đặt điều kiện gần business operation hơn, kể cả khi phương thức được gọi từ nhiều endpoints.

### Bật method authorization

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodAuthorizationConfiguration {}
~~~

Trong Spring Security 6, `@EnableMethodSecurity` kích hoạt các method-security mechanisms, bao gồm `@PreAuthorize`. **Không mặc định annotation có hiệu lực nếu chưa bật mechanism** trong application.

### Kiểm scope ở service boundary

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.parameters.P;
import org.springframework.stereotype.Service;

@Service
public class InvoiceQueryService {

    @PreAuthorize("hasAuthority('SCOPE_invoice:read')")
    public InvoiceDto getInvoiceSummary(
            @P("invoiceId") String invoiceId) {
        // Chưa đủ: cần kiểm ownership/tenant ở bước data access.
        return readWithOwnerAndTenantConstraint(invoiceId);
    }
}
~~~

`@P("invoiceId")` bảo đảm parameter name được dùng cho Spring Security expression khi compiled Java parameter metadata không sẵn; bạn cũng có thể dùng `-parameters` theo cấu hình build đã kiểm.

### Kết hợp scope với object authorization

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.parameters.P;

@PreAuthorize(
    "hasAuthority('SCOPE_invoice:read') and " +
    "@invoicePolicy.canRead(authentication, #invoiceId)")
public InvoiceDto findInvoice(@P("invoiceId") String invoiceId) {
    return invoiceRepository.load(invoiceId);
}
~~~

`invoicePolicy` là Spring bean **đã được đăng ký**, với method `canRead(Authentication, invoiceId)` kiểm trusted identity và quyền trên object. Snippet là **method-level illustration**, không phải một class độc lập có sẵn `invoiceRepository`.

Ví dụ policy cho một **single trusted issuer, user-delegated route**:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

interface InvoiceOwnershipRepository {
    boolean ownerCanRead(
        String invoiceId, String trustedUserSubject);
}

@Component("invoicePolicy")
final class InvoicePolicy {
    private final InvoiceOwnershipRepository ownership;

    InvoicePolicy(InvoiceOwnershipRepository ownership) {
        this.ownership = ownership;
    }

    public boolean canRead(Authentication authentication,
                           String invoiceId) {
        if (authentication == null ||
            !authentication.isAuthenticated() ||
            invoiceId == null || invoiceId.isBlank()) {
            return false;
        }

        // ĐÚNG CHỈ KHI authentication.getName() đã được
        // cấu hình là trusted user sub thuộc đúng issuer.
        return ownership.ownerCanRead(
            invoiceId, authentication.getName());
    }
}
~~~

**Production đa tenant/đa issuer không nên chỉ dùng `getName()`**. Phải truyền domain identity `(issuer, subject, tenant, delegatedActor...)` từ trusted adapter và truy vấn **đúng tenant + owner**. `client_credentials` không phải user subject.

### Proxy và self-invocation

Với AOP proxy-based method security, **lời gọi nội bộ `this.method()` trong cùng object** có thể không đi qua proxy và do đó không kích hoạt `@PreAuthorize` theo cơ chế mặc định. Đừng đặt toàn bộ quyền chỉ trong một method annotation rồi gọi trực tiếp từ internal helper. Kiểm implementation mode/proxy behavior và giữ **object-level authorization tại điểm thực thi dữ liệu**.

### Chọn nơi đặt kiểm tra

| Tầng | Nên kiểm | Không nên suy |
|---|---|---|
| `SecurityFilterChain`/request matcher | Route cần scope nào, token phải được xác thực | URL matcher đồng nghĩa mọi object có quyền |
| `@PreAuthorize` ở service | Scope + policy được gọi với parameters | Tất cả lời gọi nội bộ đều qua proxy |
| Domain service/repository | Tenant/owner, trạng thái hóa đơn, delegation | Token có `invoice:read` là owner mặc định |
| Database authorization constraints | Ràng buộc row/tenant/tài nguyên | Chỉ cần filter ở UI sẽ đủ |

Đối với API trả danh sách, **lọc theo principal/tenant trong query** thay vì tải toàn bộ dữ liệu rồi dựa vào frontend ẩn record. Scope chỉ quyết định loại truy cập, không bảo đảm row isolation.

## 15. Scope không phải role, role hierarchy hay permission inheritance

Một mô hình có thể có cả:

~~~text
OAuth scope:   invoice:read
Spring auth:   SCOPE_invoice:read

Application role: InvoiceReviewer
Spring auth:     ROLE_INVOICE_REVIEWER

Domain permission:
  canApproveInvoice(invoiceId, amount, tenant)
~~~

**Chúng không tự đồng nghĩa.** Một role nội bộ có thể đại diện nhiều domain permissions, còn OAuth scope kiểm khách hàng/ứng dụng được AS ủy quyền thao tác ở cấp API.

### Nếu cần ánh xạ custom role claim

Giả sử AS phát claim `app_roles` **theo một hợp đồng đã review**, không phải một field user tự chỉnh trong profile:

~~~json
{
  "iss": "https://auth.example.test",
  "aud": "invoice-api",
  "scope": "invoice:read",
  "app_roles": ["invoice_reviewer"]
}
~~~

Một converter có thể thêm `ROLE_INVOICE_REVIEWER` **chỉ khi** trusted issuer/resource/client/claim semantics cho phép. Với các claims tùy biến:

- Áp allowlist role names và namespace riêng, không dùng mọi chuỗi từ claim làm `ROLE_*`.
- Định nghĩa mapping trong security policy được version hóa.
- Không cho role từ ID token hoặc user profile tự khai thay role trong access-token contract.
- Không cho AS-B `app_roles=admin` tự động tương đương ROLE_ADMIN của AS-A.
- Kiểm role expiration/revoke policy tương tự scopes khi role thay đổi sau issuance.

### Role hierarchy không phải OAuth scope hierarchy

Spring Security có hỗ trợ cơ chế hierarchy cho authorities/roles theo cấu hình. Một khai báo nội bộ như:

~~~text
ROLE_INVOICE_ADMIN > ROLE_INVOICE_REVIEWER
~~~

không có nghĩa OAuth `scope=invoice:admin` tự cấp `invoice:read`. Nếu cần hierarchy, phải thiết kế và test **đúng namespace, resource và issuer**. Không để role hierarchy vượt qua boundary tenant hoặc bỏ qua điều kiện tài chính/approval.

### Không map bằng chuỗi thay thế

~~~text
UNSAFE:
  authority = "ROLE_" + rawScope

  rawScope could be "ADMIN" from an AS profile
  where ADMIN has a different or untrusted meaning.

SAFER:
  explicitly grant SCOPE_... from trusted AS scope.
  explicitly grant ROLE_... only from reviewed role contract.
~~~

**Fail closed với claims không biết:** Không phải cứ AS trả một trường mới thì RS phải tự map nó thành authority. Việc thiếu authority có thể gây 403 và cần sửa contract, nhưng không nên “sửa” bằng việc mở toàn bộ roles.

## 16. Multi-issuer và multi-resource: cùng tên scope có thể không cùng quyền

Một Resource Server phục vụ nhiều tenant/issuer có thể nhận:

~~~text
AS-A:
  iss = https://auth-a.example.test
  aud = invoice-api
  scope = read
  meaning = read own invoices

AS-B:
  iss = https://auth-b.example.test
  aud = invoice-api
  scope = read
  meaning = read shared reports only
~~~

Nếu converter của cả hai phát ra cùng `SCOPE_read` và route kiểm `hasAuthority("SCOPE_read")`, hệ thống có thể **gộp sai quyền** giữa hai security domains.

### Biện pháp

1. Dùng **trusted issuer allowlist** và decoder/introspector riêng hoặc resolver được cấu hình rõ cho mỗi issuer.
2. Bảo đảm token `aud` đúng resource, `typ` đúng profile và client/grant được phép.
3. Map scopes thành **internal capabilities** theo `issuer + resource + token profile`, không cộng mọi scope strings vào một namespace chung.
4. Với tenants có chính sách khác, kiểm tenant authority riêng và **row-level constraints**.
5. Chống AS mix-up, key confusion và remote JWKS lookup từ token chưa verify.
6. Audit mapping thay đổi: một issuer thêm scope mới không được mở quyền trên API khác chỉ vì tên trùng.

### Không cho caller chọn verifier qua input tự khai

~~~text
Attacker-controlled request:
  X-Issuer: https://evil.invalid
  ?validationMode=opaque

UNSAFE:
  choose issuer/JWKS/introspection endpoint directly from header/query.

SAFER:
  trusted route + allowlisted issuer registration
  + token cryptographic/trust validation
  + normalized authorities per issuer/resource policy.
~~~

Một bộ lọc chọn issuer dựa vào `iss` đọc từ JWT **chưa verified** chỉ có thể sử dụng nó như **untrusted routing hint vào một allowlist nhỏ**, không được mở rộng trust để fetch issuer mới từ Internet. Sau routing, issuer phải được kiểm chính xác bởi verifier đã tin cậy.

### Mô hình identity nên giữ đủ chiều

~~~java
record VerifiedActor(
    String issuer,
    String subject,
    String clientId,
    String tenantId,
    java.util.Set<String> capabilities
) {}
~~~

Đối với user route, `subject` là user được xác thực; với service-to-service `client_credentials`, actor có thể là workload và các nghiệp vụ không có end-user. Không ép mọi access token thành “người dùng hiện tại” để tránh confused deputy.

## 17. Authority trong JWT là một **snapshot**: thay scope/role không tự sửa token cũ

Một access token JWT được AS ký với:

~~~json
{
  "scope": "invoice:read invoice:approve",
  "iat": 1800000000,
  "exp": 1800000900
}
~~~

Nếu quản trị viên thu hồi quyền `invoice:approve` vào phút thứ hai, **JWT đã ký trước đó không tự thay đổi payload**. `JwtGrantedAuthoritiesConverter` vẫn có thể map `SCOPE_invoice:approve` cho token cũ tới expiry, trừ khi RS có **policy state/revocation khác**.

### Revocation theo hai kiểu token

| Điều kiện | JWT RS kiểm offline | Opaque RS dùng introspection |
|---|---|---|
| Scope/role bị gỡ trong AS | JWT cũ vẫn mang authority snapshot | AS có thể trả inactive hoặc metadata theo state/policy |
| User logout RP | Cookie/session RP hết hạn; JWT bearer vẫn có thể còn hợp lệ | Token có thể bị AS revoke nếu flow/policy thực hiện |
| Access token bị revoke | RS không tự biết nếu chỉ verify JWS | AS có thể trả `active=false` ở lần check mới |
| RS cache quyết định | JWT `exp` và denylist state phải được kiểm | Cache `active=true` có thể kéo dài revoke lag |
| Key rotation | Public signing key cũ có thể còn verify JWT | Introspection thường không phụ thuộc việc RS cache JWS signing key |

### Nguyên tắc cho thay đổi quyền nhạy cảm

- **Access-token TTL ngắn** giảm thời gian stale authority trong token nhưng **không thu hồi ngay**.
- **Refresh token rotation/revoke grant** ngăn phát token mới qua credential cũ, nhưng không tự vô hiệu JWT access token đã phát.
- **Opaque introspection** hoặc JWT denylist/event-driven revocation có thể thực thi policy sớm hơn nếu cache/revoke propagation đáp ứng SLO.
- **Domain permission check** động ở service/repository có thể chặn thao tác ngay khi ACL thay đổi, nhưng vẫn cần quản lý latency/consistency/cache.
- Với hành động rất nhạy cảm, dùng **step-up authentication, transaction approval**, audience/scope hẹp và trạng thái policy tại thời điểm commit.

### Không cache `Authentication` vô thời hạn

Trong stateless bearer RS, một request mới phải được xác thực theo token/policy; nếu code lưu `GrantedAuthority` từ request đầu rồi dùng lại vô thời hạn trong singleton/static cache, expiry và revoke sẽ bị bypass.

Nếu cần cache authorization decision, khóa cache theo **verified issuer + subject/client + tenant + resource + policy version + expiry/revoke semantics**, và giới hạn TTL. Tuyệt đối không dùng raw token trong metrics/logged cache key.

## 18. GrantedAuthority không tự chống CSRF, bearer replay hoặc token substitution

Một `GrantedAuthority` đúng là điều kiện **phân quyền**, không phải bằng chứng người gửi hiện tại giữ token một cách hợp pháp.

### Bearer token theft/replay

~~~text
T0: AS issues access token A1:
    scope=invoice:read, aud=invoice-api, exp=T0+5min.

T1: Attacker obtains A1 from client logs.

T2: Attacker sends Authorization: Bearer A1.
    JwtDecoder verifies signature and claims.
    Converter maps -> SCOPE_invoice:read.
    Route authorizes GET /api/invoices/INV-42.

Risk:
    If A1 remains valid and unbound to client key,
    attacker can reuse identical bearer token.
~~~

Giảm token lifetime thu hẹp replay window; không ngăn việc token bị dùng ngay sau khi mất. Với mức rủi ro cao, cần xét:

- **DPoP (RFC 9449):** RS kiểm proof JWT cho request, key thumbprint `cnf.jkt`, `htm`, `htu`, `iat`, `jti` replay store, `ath` và nonce khi yêu cầu.
- **mTLS-bound token (RFC 8705):** kiểm client certificate của kết nối và `cnf.x5t#S256`.
- **Revocation/introspection/denylist** khi cần ngăn access token trước `exp`.
- **Bảo vệ TLS, logs, storage, gateway headers** để không làm lộ bearer token.

**Không suy rằng chỉ bật `oauth2ResourceServer().jwt()` hoặc `opaqueToken()` đã tự động kiểm DPoP/mTLS**. Sender proof là **lớp token validation riêng theo profile và phiên bản framework**, trước khi chấp nhận mapped authority.

### CSRF khi access token nằm trong cookie

Nếu server cho browser tự gửi **JWT access token trong `HttpOnly` cookie**, một cross-site request có thể đi kèm cookie theo `SameSite`/cookie policy. Chữ ký JWT và `SCOPE_invoice:write` **không xác nhận browser request do người dùng chủ động khởi tạo**.

~~~text
Browser -> BFF:
  Cookie: __Host-session=<opaque>
  Requires CSRF proof / Origin policy for unsafe requests.

BFF -> Resource Server:
  Authorization: Bearer <access token>
  Requires issuer/audience/scope/object authorization.
~~~

Trong BFF architecture, **CSRF guard ở BFF** cần chạy **trước downstream side effect**. Không tắt CSRF toàn ứng dụng vì “đã có JWT”; chỉ những routes thực sự **Bearer-header-only** và không dựa vào ambient browser credentials mới có threat model khác.

### Không sử dụng OIDC ID token để cấp Resource Server authorities

~~~text
ID token:
  aud = invoice-web
  purpose = authenticate user to relying party

Access token:
  aud = invoice-api
  purpose = authorize API request
~~~

ID token có thể chứa custom roles hoặc scope-like claims, nhưng không được chấp nhận như **OAuth access token** tại Invoice API chỉ vì chữ ký OP hợp lệ. RS phải kiểm token purpose/profile và audience, nếu không một ID token dành cho RP có thể bị dùng làm credential API.

### Gateway header propagation

Một gateway có thể chuyển danh tính cho backend bằng trusted headers (sau khi verify JWT/introspection), nhưng:

- Gateway phải **xóa/ghi đè headers caller tự gửi** như `X-User`, `X-Scopes`, `X-Roles`.
- Backend phải chỉ nhận các headers này qua **trusted mTLS/network path** hoặc signed internal assertion có kiểm.
- Gateway phải kiểm đúng issuer/audience/token type và backend vẫn kiểm **domain permissions**, hoặc thực hiện thêm end-to-end token verification theo kiến trúc.
- Không map `X-Scope: invoice:admin` từ Internet trực tiếp thành `SCOPE_invoice:admin`.

**Một authority chỉ đáng tin nếu cả nguồn claims và đường truyền tới điểm sử dụng đáng tin.**

## 19. Kiểm thử mapping scope: unit, web và integration

Kiểm thử cần chia thành **ba cấp**, bởi một số mock test Spring Security chỉ đặt Authentication giả vào context và **không đi qua `JwtDecoder` hoặc AS introspection thật**.

### Cấp 1 — Unit test `JwtGrantedAuthoritiesConverter`

Với JWT **được dựng chỉ trong test**, kiểm conversion độc lập:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

class InvoiceScopeConverterTest {
    @Test
    void mapsSpaceSeparatedScopeWithPrefix() {
        Jwt jwt = Jwt.withTokenValue("test-only-token")
            .header("alg", "RS256")
            .issuer("https://auth.example.test")
            .audience(java.util.List.of("invoice-api"))
            .issuedAt(Instant.parse("2026-11-23T00:00:00Z"))
            .expiresAt(Instant.parse("2026-11-23T00:15:00Z"))
            .claim("scope", "invoice:read invoice:export")
            .build();

        JwtGrantedAuthoritiesConverter converter =
            new JwtGrantedAuthoritiesConverter();

        assertThat(converter.convert(jwt))
            .extracting(authority -> authority.getAuthority())
            .containsExactlyInAnyOrder(
                "SCOPE_invoice:read",
                "SCOPE_invoice:export");
    }
}
~~~

**Cực kỳ quan trọng:** `Jwt.withTokenValue("test-only-token")` **không ký JWT**, và converter unit test **không chứng minh một bearer token giả mạo bị RS từ chối**. Đây chỉ là test mapping. Test không có AS trusted signature/key nên không sử dụng kết quả nó làm bằng chứng token security end-to-end.

### Cấp 2 — Web authorization test qua Spring Security Test

Ví dụ `MockMvc` với `jwt()` request post-processor:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Ví dụ trong một @SpringBootTest/@AutoConfigureMockMvc test class:
// mockMvc là MockMvc được inject.
//
// Test này đặt một JWT Authentication giả vào request;
// KHÔNG đi qua JwtDecoder signature validation.

mockMvc.perform(get("/api/invoices/INV-42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_invoice:read"))))
    .andExpect(status().isOk());

mockMvc.perform(get("/api/invoices/INV-42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_invoice:export"))))
    .andExpect(status().isForbidden());
~~~

**Lưu ý:** Snippet là **mảnh test** cần imports/fixtures (`MockMvc`, `SimpleGrantedAuthority`, invoice test data và mock repository) trong class test thật. Trường hợp trả **200** còn phụ thuộc invoice tồn tại và policy owner/tenant cho actor test; nếu không, assert trạng thái/decision theo fixture.

`jwt()` test helper hỗ trợ kiểm route/method authorization theo authorities, nhưng có thể **bỏ qua decoder, ký token, issuer, audience, alg, expiry**. Để chứng minh những phần đó được thực thi, phải làm integration test sử dụng **token được ký bởi test AS key** và trusted JWKS endpoint của test, không chỉ `jwt()`.

### Cấp 3 — End-to-end JWT hoặc opaque validation

**JWT integration test** nên:

1. Tạo test AS key pair/JWKS trong test fixture **không dùng production secrets**.
2. Ký JWS access tokens với `iss`, `aud`, `scope`, `exp` và profile thật.
3. Gửi `Authorization: Bearer` tới một app context dùng **JwtDecoder thật**.
4. Thử chữ ký sai, `alg` lạ, `kid` lạ, wrong issuer/audience, ID token và token hết hạn.
5. Kiểm **401 khi authentication fail**, **403 khi scope thiếu**, **denial** khi object ownership sai.

**Opaque integration test** nên:

1. Có một **fake/test Authorization Server introspection endpoint** do test sở hữu, kiểm RS client authentication và form encoding.
2. Trả `{"active":true}`, `{"active":false}`, malformed JSON, missing fields, 401, 429, 503, timeout.
3. Kiểm mapped authorities trong `Authentication` chỉ xuất hiện khi response **đã trusted và active**.
4. Test scope parser chính xác và mọi audience/issuer/expiry contract checks.
5. Test cache TTL không vượt `exp` và revocation SLO; giả lập revoke event + stale response race.

**Không chạy các test này trên production AS/token endpoint** và không lưu thật token trong test snapshots/console log.

### Kiểm mặc định scope/scp bằng unit test

~~~text
JWT scope claim string:
  "invoice:read invoice:write"
Expected:
  SCOPE_invoice:read
  SCOPE_invoice:write

JWT scp claim list:
  ["invoice:read", "invoice:export"]
Expected with supported/default or explicit converter:
  SCOPE_invoice:read
  SCOPE_invoice:export

JwtAuthenticationConverter configured for claim "scp":
  JWT only has "scope" -> no SCOPE authorities.

Wrongly configured prefix "":
  authority="invoice:read" not "SCOPE_invoice:read".
~~~

**Đừng coi test chỉ chạy với `@WithMockUser(roles="ADMIN")` là đã kiểm mapping OAuth scope.** `@WithMockUser(roles="ADMIN")` tạo role-style authorities (thường `ROLE_ADMIN`), không đại diện mặc định cho `SCOPE_invoice:read` từ verified access token.

## 20. Ma trận kiểm thử âm tính và ranh giới quyền

Giả định:

~~~text
Trusted AS issuer:     https://auth.example.test
Invoice Resource:      aud=invoice-api
JWT profile:           signed RS256 / expected access token type
Opaque profile:        RFC7662 introspection active=true
Default converter:     scope/scp -> SCOPE_*
GET invoice route:     requires SCOPE_invoice:read
POST invoice route:    requires SCOPE_invoice:write
DELETE invoice route:  requires SCOPE_invoice:delete
User-subject:          user:an
Invoice INV-42:        owner=user:an, tenant=org-A
Invoice INV-99:        owner=user:binh, tenant=org-B
~~~

| Ca kiểm thử | Đầu vào/trạng thái | Kỳ vọng |
|---|---|---|
| **Scope đơn hợp lệ** | `scope=invoice:read` | Có `SCOPE_invoice:read` |
| **Nhiều scope trong chuỗi** | `scope="invoice:read invoice:export"` | Hai `SCOPE_*` riêng |
| **`scp` dạng collection** | `["invoice:read","invoice:export"]` | Mapping đúng theo converter/contract |
| **Không có scope/scp** | JWT hợp lệ nhưng không scope | Không tự gán `SCOPE_invoice:read` |
| **Scope rỗng** | `scope=""` | Không có quyền read/write |
| **Duplicate scope** | `scope="invoice:read invoice:read"` | Không cấp quyền mới, semantics set |
| **Scope substring** | `invoice:read-all` thay `invoice:read` | Không khớp `SCOPE_invoice:read` |
| **Scope chữ hoa/thường** | `Invoice:Read` vs `invoice:read` | Không coi tương đương khi contract phân biệt |
| **Scope có tiền tố sẵn** | `scope=SCOPE_invoice:read` | Không tự bỏ/thêm prefix tùy ý; test contract mismatch |
| **Custom scp only** | Converter buộc `scope`, token chỉ `scp` | Không map, thấy config bug, không permitAll |
| **Cả scope và scp trái nhau** | Một claim read, claim khác admin | Chọn authoritative claim explicit, không union |
| **Unknown scope** | `scope=finance:superuser` | Không tự map thành Invoice admin |
| **Role-like scope** | `scope=ADMIN` | Không mặc nhiên cấp `ROLE_ADMIN` |
| **`hasAuthority` đúng prefix** | Authentication có `SCOPE_invoice:read` | GET qua authority guard |
| **`hasAuthority` sai prefix** | Guard đòi `invoice:read` | 403, không bỏ guard |
| **`hasRole` thay scope** | Guard `hasRole("invoice:read")` | 403 theo default ROLE convention |
| **`hasRole("ADMIN")`** | Token chỉ có scope read | 403 |
| **`isAuthenticated()` làm quyền ghi** | Token chỉ có read, POST route chỉ check authenticated | Test fail; POST phải cần write |
| **`permitAll()` nhầm route** | Private endpoint mở public | Test fail, deny-by-default |
| **JWT signature sai** | Attacker đổi payload scope thành admin | 401 trước authority mapping |
| **JWT `alg=none`** | Header unsigned | 401, không fallback |
| **JWT key attacker** | JWS ký bởi key không trusted | 401 |
| **JWT `kid` lạ** | Trỏ key ngoài JWKS allowlist | 401, không remote fetch |
| **JWT wrong issuer** | Token từ OP/AS khác | 401 |
| **JWT wrong audience** | `aud=payroll-api` | 401 trước scope mapping |
| **JWT thiếu audience** | Không có `aud` theo required contract | 401 |
| **JWT expired** | `now >= exp` với skew=0 | 401 |
| **JWT not-before future** | `nbf` chưa đạt | 401 |
| **JWT có exp rất dài** | Vượt maximum lifetime policy | Reject nếu RS contract có max lifetime |
| **ID token dùng như access token** | Token đúng chữ ký nhưng `aud=invoice-web` | 401, token purpose/audience |
| **Refresh token tại RS** | Không thuộc access-token profile | 401 |
| **JWE bị gửi vào JWT-only decoder** | Encrypted access token ngoài profile | Reject/route theo trusted config |
| **Opaque active=true và read** | AS trusted, aud/iss đúng | `SCOPE_invoice:read`, tiếp tục ACL |
| **Opaque active=false** | HTTP 200 với `{"active":false}` | 401, zero authorities |
| **Opaque HTTP 200 nhầm lẫn** | Body active=false | Không coi HTTP success là token success |
| **Opaque active string** | `{"active":"true"}` | Reject JSON schema |
| **Opaque active null** | `{"active":null}` | Reject |
| **Opaque thiếu issuer/audience** | Contract yêu cầu mà metadata thiếu | Fail closed |
| **Opaque scope kiểu sai** | Object thay vì string/allowed list | Reject schema hoặc normalize đúng explicit contract |
| **Opaque response scope admin lạ** | `scope=invoice:admin` ngoài allowlist | Không tự cấp `ROLE_ADMIN` |
| **Opaque introspection 401** | RS client secret sai | Fail closed, alert, không map authorities |
| **Opaque introspection 5xx** | AS unavailable | Không tạo principal từ cache hết hạn |
| **Opaque cache stale** | `active=true` đã hết TTL, AS đã revoke | Revalidate hoặc reject theo policy |
| **Opaque cache vượt exp** | Cache còn record nhưng `exp` qua | Reject |
| **Opaque response từ RS khác** | Cross-RS cache reuse | Không chuyển audience/authority qua tài nguyên sai |
| **Wrong token type** | Response là refresh token hoặc token khác | Không map thành API access rights |
| **User object ACL sai** | Token của An xem INV-99 | 403/404 theo policy dù scope read |
| **Tenant isolation sai** | Org-B record trong route Org-A | Từ chối |
| **Client_credentials dùng user route** | Token service có scope read nhưng không user subject | Từ chối nếu route yêu cầu delegated user |
| **Delegation thiếu** | User token không được delegate access người khác | Từ chối |
| **Role claim attacker** | Body/query gửi `role=ADMIN` | Không tạo ROLE_ADMIN |
| **Subdomain cookie CSRF** | Browser tự gửi JWT auth cookie | CSRF guard phải chặn unsafe request |
| **Bearer token replay** | Attacker có access token còn hiệu lực | Có nguy cơ được nhận nếu Bearer; test cho thấy cần DPoP/mTLS/revoke |
| **DPoP proof thiếu** | Token có `cnf.jkt` nhưng caller không gửi proof | Reject |
| **DPoP proof trùng jti** | Replayed proof trong freshness window | Reject theo profile |
| **mTLS cert sai** | Token certificate-bound với cert khác | Reject |
| **Authority snapshot sau downgrade** | User vừa mất scope nhưng JWT cũ còn hạn | Có thể còn authority, cần revoke/dynamic ACL theo SLO |
| **Method security chưa bật** | `@PreAuthorize` có nhưng không được active | Integration test phải phát hiện bypass |
| **Self-invocation bypass** | `this.approveInvoice()` gọi nội bộ | Test fail nếu annotation bị bypass; dùng proxy/đặt guard đúng |
| **Multiple chains sai thứ tự** | Catch-all permissive match trước JWT chain | Test phát hiện route không qua expected validation |
| **Scope parser default thay đổi** | Nâng Spring version | Regression test output authorities/prefix |
| **Mapped authority trong log** | Có principal/session/token raw | Redaction test fail |
| **Test jwt() thay test thật** | `jwt()` post-processor cho token unsigned | Không coi mapping/mock success là crypto integration PASS |
| **Multi-issuer cùng scope** | AS-A/AS-B `read` nhưng khác semantics | Explicit issuer/resource authority translation |
| **New custom role claim** | AS thêm `roles=superadmin` ngoài contract | Không auto-map thành admin |

### Bộ kiểm thử giả lập các đường xác thực riêng

~~~text
Unit:
  JwtGrantedAuthoritiesConverter -> exact authorities.

Web:
  MockMvc jwt()/opaqueToken() helpers -> route/method authorization.

JWT integration:
  real signed JWS + trusted JWKS + issuer/audience/time/token purpose.

Opaque integration:
  trusted test AS introspection + active=true/false
  + RS authentication + schema + cache/revoke.

Domain:
  ownership/tenant/approval and database side-effect checks.
~~~

**Đừng đánh dấu PASS chỉ vì response trả 403 sau khi database đã bị ghi sai**. Với những trường hợp bị từ chối, test phải assert **không có business side effect** và không có downstream privileged call.

## 21. Tình huống thực hành: Invoice API, Payroll API và hai Authorization Servers

Một doanh nghiệp vận hành:

~~~text
AS-A:
  issuer = https://auth-a.example.test
  grant = authorization_code + PKCE
  token = JWT access token RS256

AS-B:
  issuer = https://auth-b.example.test
  grant = client_credentials
  token = opaque reference token

Invoice API:
  expected audience = invoice-api
  GET /api/invoices/{id} -> SCOPE_invoice:read
  POST /api/invoices   -> SCOPE_invoice:write
  owner/tenant checks  -> always required

Payroll API:
  expected audience = payroll-api
  GET /api/payslips   -> SCOPE_payslip:read

User An:
  subject=user:an, tenant=org-A

Invoice INV-42:
  owner=user:an, tenant=org-A

Invoice INV-99:
  owner=user:binh, tenant=org-B
~~~

### Bước 1: AS-A cấp JWT access token cho Invoice API

Claims:

~~~json
{
  "iss": "https://auth-a.example.test",
  "sub": "user:an",
  "aud": ["invoice-api"],
  "client_id": "invoice-web",
  "scope": "invoice:read invoice:export",
  "tenant_id": "org-A",
  "iat": 1800000000,
  "exp": 1800000300
}
~~~

Invoice RS verify JWT theo AS-A keys/issuer/audience/time/profile rồi converter map:

~~~text
SCOPE_invoice:read
SCOPE_invoice:export
~~~

### Bước 2: Client gọi ba API operations

| Request | Route authority | Dữ liệu domain | Kết quả |
|---|---|---|---|
| `GET /api/invoices/INV-42` | Có `SCOPE_invoice:read` | INV-42 thuộc An/org-A | Cho phép khi mọi validation đạt |
| `GET /api/invoices/INV-99` | Có `SCOPE_invoice:read` | INV-99 thuộc Bình/org-B | Từ chối do ownership/tenant |
| `POST /api/invoices` | Thiếu `SCOPE_invoice:write` | Dù payload hợp lệ | Từ chối thiếu scope |

### Bước 3: Một token khác do AS-A phát cho Payroll

~~~json
{
  "iss": "https://auth-a.example.test",
  "aud": ["payroll-api"],
  "scope": "invoice:read",
  "iat": 1800000000,
  "exp": 1800000300
}
~~~

Token có tên scope `invoice:read`, nhưng **audience không phải Invoice API**. Invoice RS phải từ chối **trước khi** `JwtGrantedAuthoritiesConverter` có thể cấp quyền sử dụng tại route.

### Bước 4: AS-B cấp opaque token cho batch worker

Introspection:

~~~json
{
  "active": true,
  "iss": "https://auth-b.example.test",
  "client_id": "billing-worker",
  "aud": ["invoice-api"],
  "scope": "invoice:read",
  "exp": 1800000300
}
~~~

Nếu Invoice API **chỉ tin AS-A**, opaque token từ AS-B **không tự được nhận**, dù `active=true` ở AS-B. Nếu Invoice API **đã đăng ký tin AS-B cho route M2M cụ thể**, phải có trusted AS-B introspection client, audience/scope normalization và **workload-specific business authorization**, không giả định worker là `user:an`.

### Bước 5: User bị gỡ quyền trong AS-A

Admin gỡ `invoice:export` lúc access token ở bước 1 chưa hết hạn. JWT đã ký có thể tiếp tục mang `SCOPE_invoice:export` tới `exp`. Nếu xuất dữ liệu là hành động nhạy cảm, Invoice API cần:

- Access token lifetime phù hợp.
- Grant/token revocation và RS enforcement theo SLO nếu muốn chặn trước expiry.
- Kiểm quyền export động ở domain ACL hoặc policy store khi cần.
- Cơ chế reauthentication/step-up nếu hành động nhạy cảm.

Không thể yêu cầu `JwtGrantedAuthoritiesConverter` tự cập nhật một payload JWT đã ký từ quá khứ.

### Câu hỏi và đáp án

**Câu 1. Tại sao scope `invoice:read` thành `SCOPE_invoice:read` thay vì `ROLE_invoice:read`?**

Vì Spring Security OAuth2 Resource Server sử dụng **prefix authority `SCOPE_`** theo converter mặc định để biểu diễn OAuth scopes. Role namespace `ROLE_` phục vụ các role conventions riêng và không tự sinh từ scopes.

**Câu 2. Nếu code dùng `hasRole("invoice:read")` với JWT trên thì request có qua không?**

Không theo cấu hình mặc định; `hasRole` thường yêu cầu `ROLE_invoice:read`, còn converter cấp `SCOPE_invoice:read`. Dùng đúng `hasAuthority` hoặc cấu hình mapping explicit và kiểm thử.

**Câu 3. Nếu JWT có `scope=invoice:read invoice:export`, `hasAuthority("SCOPE_invoice:write")` có qua không?**

Không. Scope write là quyền riêng; đừng tự suy từ read/export.

**Câu 4. Nếu token ký đúng nhưng `aud=payroll-api` và `scope=invoice:read`, có nên tạo authority rồi cho Invoice GET không?**

Không. RS phải **reject sai audience** ở bước xác thực/validation. Scope không thay resource isolation.

**Câu 5. Tại sao An không được xem INV-99 dù có authority đọc?**

`SCOPE_invoice:read` chỉ cho phép loại thao tác đọc theo grant; INV-99 không thuộc user/tenant được ủy quyền. Business authorization phải kiểm object ownership/tenant.

**Câu 6. Nếu user gửi JSON `{"scope":"invoice:admin"}` thì converter có map thành authority không?**

Không. Converter đọc scopes **từ trusted authenticated token/AS introspection**, không từ request body do caller kiểm soát.

**Câu 7. AS-B opaque introspection trả `active=true` có đủ để Invoice API nhận token không?**

Chưa đủ. Invoice API phải có **trust registration cho AS-B**, kiểm audience, token purpose, time, scope và M2M actor policy. `active=true` chỉ có nghĩa AS-B coi token active trong contract của nó.

**Câu 8. BFF nhận session cookie từ browser, sau đó gửi JWT đến Invoice API. Có còn CSRF risk không?**

Có ở **browser → BFF**. BFF cần CSRF defense cho unsafe cookie-authenticated requests. Invoice API vẫn validate bearer token và authorities tại boundary.

**Câu 9. Vì sao token JWT đã phát vẫn chứa authority export khi admin vừa rút quyền?**

JWT là **claims snapshot**; converter map claims tại lúc request dựa vào token đang còn được RS chấp nhận. Cần revoke state/introspection/dynamic authorization để chặn sớm.

**Câu 10. Nếu attacker lấy được JWT của An nhưng không có private DPoP key thì sao?**

Nếu token thực sự **DPoP-bound** và RS thực thi đầy đủ proof/`cnf.jkt`, bản sao token đơn lẻ không đủ. Nhưng nếu API nhận token như **Bearer** thuần, chỉ scope authority không ngăn replay.

**Câu 11. Nếu đổi `JwtGrantedAuthoritiesConverter` sang claim `scp` nhưng AS-A vẫn chỉ trả `scope`?**

Converter sẽ không nhận đúng scopes, dẫn đến thiếu `SCOPE_*` và 403. Kiểm claim schema và converter output; không cho `permitAll()` làm workaround.

**Câu 12. Nếu AS-A và AS-B cùng phát `scope=read`, có nên map cả hai thành `SCOPE_read` không?**

Không mặc định. Phải kiểm **issuer/resource/client/grant semantics**. Tên scope giống nhau không bảo đảm quyền giống nhau giữa hai security domains.

**Câu 13. Vì sao `jwt()` trong MockMvc test không chứng minh JWT signature validation đúng?**

Vì test helper có thể đặt authentication giả vào context và bypass `JwtDecoder`. Nó hữu ích cho authority authorization test, nhưng test cryptographic validation cần signed JWS và trusted test JWKS.

**Câu 14. Có thể bỏ object ACL nếu scope là `invoice:admin` không?**

Không tự động. `invoice:admin` chỉ là một scope string; việc có quyền vượt tenant/ownership phải được **business policy explicit** định nghĩa, có audit và giới hạn riêng.

**Câu 15. Nếu access token có scope read nhưng tenant_id do caller sửa trong header `X-Tenant-ID`, nên tin giá trị nào?**

Không tin tenant header tự khai như authority. Tenant context phải được ràng buộc với verified identity/allowed memberships và kiểm với resource owner; path/header do caller chọn chỉ là **request selector**.

**Câu 16. Nếu introspection AS outage mà cache `active=true` đã hết hạn, API có nên vẫn tạo `SCOPE_invoice:read` để giữ availability?**

Không. Phải fail closed hoặc dùng một cơ chế cache/status **còn hiệu lực theo security policy**; không nâng stale principal thành authenticated chỉ vì upstream unavailable.

## 22. Checklist triển khai `GrantedAuthority` từ scope

1. **Xác định scope contract:** Tên `scope/scp`, kiểu string/list, delimiter và semantics được AS/RS đăng ký rõ?
2. **AS quyết định grant:** Client request scope không phải quyền đương nhiên; AS kiểm registration, consent, grant và resource?
3. **Phân biệt token classes:** Access token, ID token và refresh token không bị dùng lẫn tại Resource Server?
4. **JWT verify trước mapping:** Chữ ký/key/algorithm thuộc trusted AS, không chỉ Base64 decode?
5. **Issuer exact:** `iss` so với trusted issuer, multi-issuer registry không auto-trust arbitrary input?
6. **Audience exact:** `aud` chứa đúng API/resource, không chấp nhận token dành cho Payroll tại Invoice?
7. **Thời hạn:** `exp`, `nbf`, `iat`/max lifetime và clock skew được kiểm theo profile?
8. **Token purpose:** `typ`/RFC 9068 access-token profile được áp khi contract yêu cầu?
9. **Opaque AS trust:** HTTPS, RS credentials và introspection endpoint đã pin, không dùng token của caller làm introspection auth?
10. **`active` strict:** Opaque `active=false`/missing/null/string không được map thành authorities?
11. **Claims schema:** `scope` string hoặc `scp` collection theo AS contract; không bỏ qua kiểu dữ liệu lạ?
12. **Prefix nhất quán:** `scope=invoice:read` -> `SCOPE_invoice:read` nếu default mapping được chọn?
13. **`hasAuthority` đúng:** Route/method dùng exact `SCOPE_*`, không nhầm `hasRole`/`ROLE_*`?
14. **Không so scope substring:** `invoice:read-all` không tương đương `invoice:read`?
15. **Custom converter rõ:** `JwtGrantedAuthoritiesConverter` chọn authoritative claim/prefix, test sau nâng Spring version?
16. **`JwtAuthenticationConverter` đúng:** Principal claim được xác định rõ, tránh đổi `sub` thành `client_id` gây nhầm user?
17. **JWT validators không bị mất:** Khi override `setJwtValidator` vẫn có issuer, expiry, audience và các profile checks cần thiết?
18. **Role mapping có allowlist:** Không auto-map `scope=ADMIN` hay custom user profile field thành `ROLE_ADMIN`?
19. **Scope/role không tự kế thừa:** Hierarchy chỉ có hiệu lực nếu security policy explicit, không suy admin implies read từ OAuth?
20. **Client credentials đúng actor:** Service identity không bị coi là người dùng cuối, route M2M và delegated route tách biệt?
21. **Multi-issuer namespace:** Scope cùng tên từ AS khác không tự cùng quyền, issuer+resource+tenant policy rõ?
22. **Domain identity bảo toàn:** Dùng issuer, subject, client, tenant và grant context đáng tin thay vì request body/header chưa verify?
23. **Route security deny-by-default:** `SecurityFilterChain` matchers/ordering/catch-all bảo vệ mọi private API?
24. **CSRF đúng transport:** Bearer-only routes khác cookie/BFF routes; không tắt CSRF cho cookie-authenticated flows?
25. **Method security bật:** `@EnableMethodSecurity` và `@PreAuthorize` thực sự có hiệu lực trong production?
26. **Proxy/self-invocation đã test:** Không có đường gọi business method bypass security annotation ngoài ý muốn?
27. **Object-level authorization:** Có kiểm owner/tenant/ACL/transaction constraints dù scope đã pass?
28. **Không dùng UI làm quyền:** Frontend ẩn nút không thay RS authorization; DB query được tenant-bound?
29. **Revocation/expiry được đo:** JWT authority snapshot không sống ngoài `exp` và revoke SLO; opaque cache đúng hạn?
30. **Opaque cache theo RS:** `active=true` không cache vượt `exp`/security SLO hoặc dùng chéo AS/RS client?
31. **Sender constraint:** Khi dùng DPoP/mTLS, RS verify proof/chứng chỉ; không coi `SCOPE_*` là đủ chống replay?
32. **Bảo vệ Bearer:** TLS, header transport, log redaction, secure storage; không lộ token trong query/metrics?
33. **Phân biệt 401/403:** Token invalid/inactive → 401; thiếu scope/quyền → 403 theo RFC/policy?
34. **Không fail open:** AS introspection/JWKS lỗi không tạo authenticated principal với scopes giả?
35. **Unit test converter:** `scope`, `scp`, prefix, empty/malformed/duplicate/unknown scope được test?
36. **Web authorization test:** GET/POST/DELETE đúng scope; `jwt()`/`opaqueToken()` mocks không bị nhầm với cryptographic validation?
37. **Integration test thật:** JWT signed test AS + JWKS và opaque test AS active=false/timeout/scope/issuer/aud?
38. **Đường lỗi không side effect:** Dữ liệu không bị ghi/thực thi downstream trước khi token và object quyền được kiểm?
39. **Audit/observability có kiểm soát:** Log authority mapping failures/issuer alias/correlation ID, không raw token/PII không cần?
40. **Review khi thay đổi AS/Spring:** Claim schema, authority prefix, scope semantics, issuer trust và role hierarchy được regression test?

**Ghi nhớ:** Trong Spring Security OAuth2 Resource Server, **verified token scope thường được map thành `GrantedAuthority("SCOPE_" + scope)`**. `JwtGrantedAuthoritiesConverter` xử lý claim `scope`/`scp` của JWT, còn opaque-token pipeline dùng **trusted introspection** để lấy scopes và tạo authorities. `hasAuthority("SCOPE_invoice:read")` khác `hasRole("ADMIN")`, và không scope nào tự tạo quyền trên **mọi bản ghi/tenant**. Trước mapping phải xác minh **issuer, audience, chữ ký/token state, thời hạn và token purpose**; sau mapping phải kiểm **scope, principal/client semantics, object ACL, revoke và sender-binding khi cần**. Quyền thật sự chỉ tồn tại nếu **toàn bộ chuỗi tin cậy và authorization** đều đạt.

### Chuẩn và tài liệu tham khảo

- **RFC 6749 — The OAuth 2.0 Authorization Framework:** scope, authorization grant, client và AS/RS roles; client yêu cầu scope khác scope được cấp.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** bearer token transport, `invalid_token`, `insufficient_scope`, lỗi `401/403` và token theft.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** JWT access-token claims/type, audience/issuer, signature và scope.
- **RFC 7662 — OAuth 2.0 Token Introspection:** `active`/`scope`/`aud`/`iss`/`exp`, endpoint auth, state, optional claims và cache.
- **RFC 7009 — OAuth 2.0 Token Revocation:** thu hồi token/grant, khác với mapping authority của JWT cũ.
- **RFC 7519 — JSON Web Token (JWT):** `iss`/`aud`/`sub`/`iat`/`nbf`/`exp` và NumericDate.
- **RFC 7515 — JSON Web Signature (JWS)** và **RFC 7517 — JSON Web Key (JWK):** chữ ký, trusted verification key, `kid` và JWKS.
- **RFC 8725 — JSON Web Token Best Current Practices:** token purpose confusion, algorithm/key trust, substitution và JWT verification.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** token theft/replay, scopes, resource binding, audience, refresh protection và sender constraints.
- **RFC 8707 — Resource Indicators for OAuth 2.0:** ràng buộc access token với đúng Resource Server.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** `cnf.jkt`, proof `jti/iat/htm/htu/ath` và replay detection.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** `cnf.x5t#S256` và certificate-bound bearer protection.
- **OpenID Connect Core 1.0:** ID token phục vụ Relying Party authentication, không thay OAuth API access token.
- **Spring Security Reference — OAuth2 Resource Server JWT:** `JwtDecoder`, `NimbusJwtDecoder`, `JwtGrantedAuthoritiesConverter`, `JwtAuthenticationConverter`, default `SCOPE_` mapping và validators.
- **Spring Security Reference — OAuth2 Resource Server Opaque Token:** `OpaqueTokenIntrospector`, principal authorities và customization.
- **Spring Security Reference — Authorization & Method Security:** `GrantedAuthority`, `SimpleGrantedAuthority`, `hasAuthority`/`hasRole`, `@EnableMethodSecurity` và `@PreAuthorize`.
- **Spring Security Reference — Testing Servlet Security:** `MockMvc`, `jwt()`/`opaqueToken()` request post-processors và phân biệt mocks với real token validation.
- **OWASP Authorization Cheat Sheet và OWASP API Security Top 10:** BOLA/IDOR, least privilege, role/permission mapping và tenancy.
- **OWASP OAuth 2.0 Cheat Sheet:** scopes, audience, bearer token protection, refresh/revocation và OAuth trust boundaries.
