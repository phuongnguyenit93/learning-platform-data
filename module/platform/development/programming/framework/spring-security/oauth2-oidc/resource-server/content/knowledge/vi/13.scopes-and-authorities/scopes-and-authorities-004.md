# hasAuthority, hasRole và tiền tố ROLE_

Trong **Spring Security OAuth 2.0/OIDC Resource Server**, sau khi một Bearer access token được xác minh, Spring Security tạo **Authentication** có tập **GrantedAuthority**. Các phương thức **hasAuthority(...)** và **hasRole(...)** dùng tập quyền đó để quyết định request có được đi vào endpoint hoặc method hay không.

Hai cách kiểm này dễ gây nhầm lẫn vì cùng nói về quyền nhưng có quy ước khác nhau:

- **hasAuthority("SCOPE_orders.read")**: yêu cầu chính xác authority **SCOPE_orders.read**.
- **hasAuthority("ROLE_ADMIN")**: yêu cầu chính xác authority **ROLE_ADMIN**.
- **hasRole("ADMIN")**: theo mặc định, yêu cầu authority **ROLE_ADMIN**, vì Spring Security áp dụng tiền tố **ROLE_** cho role.
- **hasRole("ROLE_ADMIN")**: không phải cách viết nên dùng ở HTTP request authorization DSL; một số API sẽ báo lỗi vì đối số đã mang tiền tố.

Trong Resource Server JWT, OAuth2 scope **orders.read** thường được ánh xạ thành **SCOPE_orders.read**, **không** phải **ROLE_orders.read**. Tương tự, nếu JWT mang claim **roles** chứa giá trị **ADMIN**, Spring Security **không tự chuyển claim đó thành ROLE_ADMIN** khi chưa có converter thích hợp.

Bài học giải thích bản chất authority, sự khác nhau giữa scope và role, cách viết rule, cấu hình converter, quyền theo tenant và những lỗi 403 thường gặp.

## 1. Authentication, GrantedAuthority, scope và role

### 1.1. Authentication đến từ đâu?

Trong OAuth2 JWT Resource Server, luồng điển hình là:

~~~mermaid
flowchart LR
    A[Authorization: Bearer JWT] --> B[BearerTokenAuthenticationFilter]
    B --> C[JwtAuthenticationProvider]
    C --> D[JwtDecoder xác minh token]
    D -->|Không hợp lệ| E[401 Unauthorized]
    D -->|Hợp lệ| F[JwtAuthenticationConverter]
    F --> G[JwtAuthenticationToken có GrantedAuthority]
    G --> H[hasAuthority / hasRole]
    H -->|Thiếu quyền| I[403 Forbidden]
    H -->|Đủ quyền| J[Controller / Service]
~~~

Các vai trò chính:

- **JwtDecoder** kiểm chữ ký JWT với khóa tin cậy, issuer, thời hạn và các validator đã cấu hình, trong đó cần kiểm audience của API.
- **JwtAuthenticationConverter** chuyển token đã được chấp nhận thành Authentication và authorities.
- **Authentication** đại diện cho chủ thể đã được xác thực. Trong JWT Resource Server, triển khai thường gặp là **JwtAuthenticationToken**.
- **GrantedAuthority** đại diện cho một quyền mà Spring Security có thể so khớp với rule.
- **hasAuthority/hasRole** chỉ kiểm authority trên Authentication, không tự xác minh JWT signature.

Một token hợp lệ chứa:

~~~json
{
  "iss": "https://login.example.com/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "exp": 1893456000
}
~~~

có thể tạo Authentication với:

~~~text
principal: Jwt(...)
name: user-123
authorities:
  - SCOPE_orders.read
  - SCOPE_orders.write
~~~

**Quan trọng:** các claims chỉ nên trở thành authority **sau khi token đã qua xác thực nguồn phát hành và các validator**. Nếu code tự đọc JSON từ Bearer token chưa được xác minh rồi tạo Authentication, các rule hasRole/hasAuthority có thể bị đánh lừa.

### 1.2. GrantedAuthority là đơn vị so khớp quyền

Spring Security có giao diện **GrantedAuthority** và triển khai phổ biến **SimpleGrantedAuthority**:

~~~java
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

GrantedAuthority readOrders =
    new SimpleGrantedAuthority("SCOPE_orders.read");

GrantedAuthority admin =
    new SimpleGrantedAuthority("ROLE_ADMIN");

GrantedAuthority approve =
    new SimpleGrantedAuthority("PERM_orders.approve");
~~~

Bản thân ba chuỗi trên không có tính mật mã hoặc quyền tự động. Chúng có ý nghĩa vì **code authorization của ứng dụng quyết định kiểm chúng**.

Spring Security hỗ trợ quy ước prefix để giảm nhầm lẫn:

| Authority | Ý nghĩa theo quy ước |
|---|---|
| **SCOPE_orders.read** | Token có OAuth2 scope **orders.read** |
| **SCOPE_orders.write** | Token có OAuth2 scope **orders.write** |
| **ROLE_ADMIN** | Chủ thể mang vai trò **ADMIN** theo mô hình ứng dụng |
| **ROLE_SUPPORT** | Chủ thể mang vai trò **SUPPORT** |
| **PERM_orders.approve** | Một quyền chi tiết do ứng dụng tự thiết kế |
| **ADMIN** | Một authority chính xác tên **ADMIN**, không mặc định đồng nghĩa ROLE_ADMIN |

Không phải mọi ứng dụng đều dùng đầy đủ những prefix trên. **ROLE_** và **SCOPE_** là các convention thường gặp của Spring Security; **PERM_** chỉ là ví dụ naming convention tự định nghĩa.

### 1.3. Role và OAuth2 scope khác nhau thế nào?

**Scope** trong OAuth2 là phạm vi mà access token được cấp, chẳng hạn **orders.read**, **orders.write**, **reports.export**. Nó gắn với việc ủy quyền cho một token, client và resource cụ thể.

**Role** thường là nhóm quyền của một chủ thể trong ứng dụng hoặc tổ chức, chẳng hạn **ADMIN**, **AUDITOR**, **SUPPORT**. Role có thể được Authorization Server phát hành trong JWT hoặc được ứng dụng tính từ cơ sở dữ liệu/quy tắc nội bộ, nhưng phải có một nguồn danh tính và quyền được tin cậy.

Ví dụ cùng một chủ thể có vai trò ADMIN nhưng access token chỉ có scope **orders.read**. Không được kết luận token đó mặc nhiên có **orders.write** hay quyền export dữ liệu nếu chính sách API yêu cầu scope tương ứng.

Tương tự, token có scope **openid**, **profile**, **email** không tự có quyền nghiệp vụ chỉ vì Spring Security tạo ra các authority **SCOPE_openid**, **SCOPE_profile**, **SCOPE_email**.

## 2. hasAuthority kiểm khớp chuỗi chính xác

Phương thức **hasAuthority** yêu cầu Authentication có một authority với tên đã chỉ định.

Ví dụ:

~~~java
.requestMatchers("/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

Để rule đạt, danh sách GrantedAuthority phải chứa **SCOPE_orders.read**.

Nếu Authentication chỉ có:

~~~text
ROLE_ADMIN
SCOPE_email
~~~

thì **hasAuthority("SCOPE_orders.read")** không đạt. Spring Security không coi **ROLE_ADMIN** hoặc **SCOPE_email** tương đương **SCOPE_orders.read**.

Những ví dụ khác:

~~~java
.hasAuthority("ROLE_ADMIN")
.hasAuthority("PERM_orders.approve")
.hasAuthority("SCOPE_reports.export")
~~~

Cả ba đều so khớp chuỗi authority tương ứng, không tự thêm hoặc bỏ tiền tố. **hasAuthority("ADMIN")** khác **hasAuthority("ROLE_ADMIN")**.

### 2.1. Exact matching giúp tránh cấp quyền ngoài ý muốn

Khi dùng explicit authority, policy dễ đọc:

~~~text
Access token scope:       orders.read
Spring GrantedAuthority:  SCOPE_orders.read
Endpoint rule:            hasAuthority("SCOPE_orders.read")
~~~

Ngược lại, nếu rule dùng tên **ROLE_orders.read**, trong khi converter phát sinh **SCOPE_orders.read**, request thường bị từ chối với 403.

Dù exact matching là nguyên tắc chính, hệ thống vẫn có thể cung cấp custom authorization manager hoặc role hierarchy; khi đó phải hiểu rõ cách rule và custom policy hoạt động, không dựa hoàn toàn vào tên phương thức.

## 3. hasRole và tiền tố ROLE_

Trong Spring Security, **role thường được biểu diễn như một GrantedAuthority có tiền tố ROLE_**.

Với prefix mặc định:

~~~java
.requestMatchers("/api/admin/**")
    .hasRole("ADMIN")
~~~

tương đương về quyền yêu cầu với:

~~~java
.requestMatchers("/api/admin/**")
    .hasAuthority("ROLE_ADMIN")
~~~

Nếu Authentication có **ROLE_ADMIN**, rule có thể đạt. Nếu chỉ có **ADMIN** hoặc **SCOPE_ADMIN**, rule mặc định không đạt.

### 3.1. Không đưa tiền tố ROLE_ hai lần

Không nên viết:

~~~java
// Không dùng kiểu này cho hasRole mặc định trong HTTP DSL:
.requestMatchers("/api/admin/**")
    .hasRole("ROLE_ADMIN")
~~~

Các API request authorization như **AuthorityAuthorizationManager.hasRole** yêu cầu đối số là tên role không có **ROLE_**; một số implementation ném **IllegalArgumentException** khi đối số đã có tiền tố.

Hai lựa chọn rõ ràng:

~~~java
// Muốn diễn đạt vai trò theo convention:
.hasRole("ADMIN")

// Muốn diễn đạt chính xác tên GrantedAuthority:
.hasAuthority("ROLE_ADMIN")
~~~

Ở **@PreAuthorize** trong method security, cách viết thông thường cũng là **hasRole('ADMIN')** thay vì nhúng sẵn tiền tố.

### 3.2. hasRole không đi tìm claim roles trong JWT

Giả sử JWT đã được issuer ký hợp lệ:

~~~json
{
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "roles": ["ADMIN"]
}
~~~

Nếu ứng dụng chỉ dùng converter scope mặc định, Authentication có thể chỉ là:

~~~text
SCOPE_orders.read
~~~

Kết quả:

- **hasAuthority("SCOPE_orders.read")**: đạt.
- **hasRole("ADMIN")**: không đạt.
- **hasAuthority("ROLE_ADMIN")**: không đạt.

Spring Security không xem JSON field **roles** như một luật bắt buộc của OAuth2/OIDC; không có chuyện thấy chữ ADMIN trong claim là tự tạo ROLE_ADMIN. Muốn dùng role, Resource Server cần **ánh xạ claim vào GrantedAuthority** theo hợp đồng tin cậy.

## 4. Bảng so sánh hasAuthority và hasRole

| Rule | GrantedAuthority cần có theo cấu hình mặc định | Tình huống sử dụng |
|---|---|---|
| **hasAuthority("SCOPE_orders.read")** | **SCOPE_orders.read** | Bảo vệ endpoint bằng OAuth2 scope |
| **hasAuthority("SCOPE_reports.export")** | **SCOPE_reports.export** | Chỉ token được cấp scope export mới dùng được |
| **hasAuthority("ROLE_ADMIN")** | **ROLE_ADMIN** | Kiểm tường minh authority role |
| **hasRole("ADMIN")** | **ROLE_ADMIN** | Kiểm role theo convention |
| **hasRole("SUPPORT")** | **ROLE_SUPPORT** | Kiểm vai trò support |
| **hasAuthority("ADMIN")** | **ADMIN** | Chỉ khi application tạo authority literal ADMIN |
| **hasRole("orders.read")** | **ROLE_orders.read** | Thường sai nếu đang kiểm scope orders.read |

Với những Authentication đã xác thực:

| Authentication | Authorities |
|---|---|
| **A** | SCOPE_orders.read |
| **B** | ROLE_ADMIN |
| **C** | SCOPE_orders.read, ROLE_ADMIN |
| **D** | ADMIN |
| **E** | SCOPE_openid, SCOPE_profile, SCOPE_email |

Ta có ma trận kết quả:

| Rule | A | B | C | D | E |
|---|:---:|:---:|:---:|:---:|:---:|
| **hasAuthority("SCOPE_orders.read")** | ✓ | ✗ | ✓ | ✗ | ✗ |
| **hasRole("ADMIN")** | ✗ | ✓ | ✓ | ✗ | ✗ |
| **hasAuthority("ROLE_ADMIN")** | ✗ | ✓ | ✓ | ✗ | ✗ |
| **hasAuthority("ADMIN")** | ✗ | ✗ | ✗ | ✓ | ✗ |
| **hasAuthority("SCOPE_email")** | ✗ | ✗ | ✗ | ✗ | ✓ |

Ma trận chỉ nói về **cách so khớp authority**. Điều kiện để authority xuất hiện phải dựa trên token đã xác thực; việc một rule đạt chưa chứng minh nghiệp vụ nên cấp quyền tương ứng. Ví dụ **SCOPE_email** không phải quyền xuất dữ liệu khách hàng.

## 5. Scope từ JWT được ánh xạ thành SCOPE_* như thế nào?

**JwtGrantedAuthoritiesConverter** là lớp Spring Security thường dùng để chuyển scope JWT thành authorities. Mặc định, nó biết những tên claim scope phổ biến như **scope** hoặc **scp**.

Ví dụ 1 — scope dạng chuỗi cách nhau bởi dấu cách:

~~~json
{
  "scope": "orders.read orders.write"
}
~~~

Ví dụ 2 — scp dạng mảng:

~~~json
{
  "scp": ["orders.read", "orders.write"]
}
~~~

Với cấu hình mặc định thích hợp, các scope tương ứng được ánh xạ thành:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Các ý quan trọng:

- **SCOPE_** là prefix mặc định của converter cho scope.
- Claim **scope/scp** được đọc theo logic lựa chọn claim của converter; nếu token chứa cả hai, không giả định framework tự gộp mọi giá trị mà không cấu hình.
- Converter mặc định **không** quét toàn bộ JWT để suy đoán roles, permissions hoặc tenant quyền.
- Giá trị **SCOPE_orders.read** có thể được kiểm bằng **hasAuthority("SCOPE_orders.read")**.
- Không nên dùng **hasRole("orders.read")** để kiểm OAuth scope vì nó kiểm quyền thuộc nhóm **ROLE_**.

### 5.1. Các scope OIDC không tự thành quyền nghiệp vụ

Token có thể chứa:

~~~json
{
  "scope": "openid profile email"
}
~~~

Spring Security có thể tạo:

~~~text
SCOPE_openid
SCOPE_profile
SCOPE_email
~~~

Các scope này liên quan tới OpenID Connect và dữ liệu định danh. Không được tự suy diễn **SCOPE_email** tương đương quyền xem danh sách email của tất cả khách hàng, hay **SCOPE_profile** tương đương quyền chỉnh sửa hồ sơ của người khác.

OAuth scope và nghiệp vụ phải có hợp đồng rõ ràng giữa Authorization Server và Resource Server. Nếu Orders API cần quyền đọc đơn, nên có scope/permission cụ thể như **orders.read**, không tái sử dụng identity scopes.

### 5.2. Nếu claim tên khác thì sao?

Giả sử Authorization Server gửi:

~~~json
{
  "permissions": ["orders.read", "orders.approve"]
}
~~~

Đây **không** phải tên scope claim mặc định. Ứng dụng có thể cấu hình converter:

~~~java
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

JwtGrantedAuthoritiesConverter permissionsConverter =
    new JwtGrantedAuthoritiesConverter();

permissionsConverter.setAuthoritiesClaimName("permissions");
permissionsConverter.setAuthorityPrefix("PERM_");
~~~

Khi converter xử lý claim phù hợp, quyền có thể trở thành:

~~~text
PERM_orders.read
PERM_orders.approve
~~~

Sau đó dùng:

~~~java
.hasAuthority("PERM_orders.approve")
~~~

Việc đổi converter sang claim **permissions** có thể khiến mapping **scope** mặc định không được giữ lại. Nếu muốn dùng đồng thời scopes và permissions, phải **kết hợp converter** hoặc thêm authorities từ nhiều nguồn một cách có chủ đích.

## 6. Cấu hình SecurityFilterChain cho Orders API

Giả sử policy:

| Endpoint | Điều kiện |
|---|---|
| **GET /api/public/** | Công khai |
| **GET /api/orders/** | OAuth2 scope orders.read |
| **POST /api/orders/** | OAuth2 scope orders.write |
| **PUT /api/orders/** | OAuth2 scope orders.write |
| **/api/admin/** | Ứng dụng role ADMIN |
| Endpoint còn lại | Ít nhất đã xác thực; thực tế cần policy riêng |

Cấu hình **Spring Security Servlet**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers(HttpMethod.PUT, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers("/api/admin/**")
                    .hasRole("ADMIN")
                .anyRequest()
                    .authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

Điều cần lưu ý:

1. **JwtDecoder** phải xác minh chữ ký, issuer, audience, thời hạn và token profile phù hợp trước khi rule đọc authorities.
2. Các matcher có thứ tự; đặt rule cụ thể trước rule rộng và review toàn bộ endpoint/HTTP method.
3. **anyRequest().authenticated()** chỉ đòi authentication, không có yêu cầu scope cụ thể; với API nhạy cảm phải xây dựng chính sách đủ chặt, tránh để endpoint bị bỏ sót.
4. Role **ADMIN** chỉ có tác dụng nếu converter hoặc cơ chế cấp quyền đã tạo **ROLE_ADMIN**.
5. Kiểm endpoint dựa trên scope/role mới là **coarse-grained authorization**; phải kiểm quyền trên bản ghi/tenant tại tầng service hoặc domain.

### 6.1. JWT token đúng nhưng rule vẫn trả 403

Giả sử token hợp lệ có:

~~~json
{
  "iss": "https://login.example.com/realms/shop",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "roles": ["ADMIN"],
  "exp": 1893456000
}
~~~

Nếu decoder và converter mặc định chỉ tạo **SCOPE_orders.read**, một request tới **/api/admin/reports** không có **ROLE_ADMIN** nên **hasRole("ADMIN")** từ chối, thường trả **403 Forbidden**.

Đây không nhất thiết là lỗi JWT signature. Nên kiểm **Authentication.authorities** (chỉ log các metadata cần thiết và không log raw token) và mapping claim. Không sửa lỗi bằng cách bỏ kiểm JWT hoặc mở endpoint thành **permitAll()**.

## 7. Ánh xạ claim roles thành ROLE_* có chủ đích

Nếu Authorization Server đáng tin cậy phát hành claim **roles** và API có hợp đồng sử dụng nó làm nguồn vai trò, hãy cấu hình **JwtAuthenticationConverter**.

Ví dụ token:

~~~json
{
  "iss": "https://login.example.com/realms/shop",
  "aud": ["orders-api"],
  "sub": "user-123",
  "scope": "orders.read reports.read",
  "roles": ["ADMIN", "SUPPORT"]
}
~~~

Mục tiêu authorities:

~~~text
SCOPE_orders.read
SCOPE_reports.read
ROLE_ADMIN
ROLE_SUPPORT
~~~

### 7.1. Converter giữ scope và thêm roles

~~~java
import java.util.Collection;
import java.util.LinkedHashSet;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Configuration
public class JwtAuthoritiesConfiguration {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter scopeConverter =
            new JwtGrantedAuthoritiesConverter();

        Converter<Jwt, Collection<GrantedAuthority>> combined = jwt -> {
            Collection<GrantedAuthority> authorities =
                new LinkedHashSet<>();

            Collection<GrantedAuthority> scopes =
                scopeConverter.convert(jwt);
            if (scopes != null) {
                authorities.addAll(scopes);
            }

            Object rawRoles = jwt.getClaim("roles");
            if (rawRoles instanceof Collection<?> roles) {
                for (Object value : roles) {
                    if (value instanceof String role
                            && role.matches("[A-Z][A-Z0-9_]*")) {
                        authorities.add(
                            new SimpleGrantedAuthority("ROLE_" + role)
                        );
                    }
                }
            }

            return authorities;
        };

        JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(combined);
        return converter;
    }
}
~~~

Giải thích:

- **JwtGrantedAuthoritiesConverter** mặc định xử lý scope/scp thành **SCOPE_***.
- **rawRoles** được lấy từ claim **roles**, giả định issuer đã được API tin cậy và token đã qua JwtDecoder.
- **LinkedHashSet** giảm trùng lặp authorities khi gộp nhiều nguồn.
- Chuỗi role được kiểm format trước khi tạo **ROLE_***. Đây chỉ là lớp kiểm tra đơn giản; production còn phải có **allowlist vai trò** và quy tắc tenant/resource phù hợp.
- Nếu token không có roles, mapping scope vẫn hoạt động.
- Nếu roles không phải mảng chuỗi, đoạn ví dụ không cấp role từ dữ liệu sai format.

**Cực kỳ quan trọng:** converter không phải nơi xác lập issuer tin cậy. Nó chỉ xử lý **Jwt đã được decoder xác thực** trong authentication flow chuẩn. Không tự gọi converter trên Jwt được dựng từ JSON do client gửi rồi coi là đã login.

### 7.2. Tránh nhân đôi tiền tố ROLE_

Converter ở trên mong đợi:

~~~json
{
  "roles": ["ADMIN", "SUPPORT"]
}
~~~

và tạo:

~~~text
ROLE_ADMIN
ROLE_SUPPORT
~~~

Nếu issuer gửi:

~~~json
{
  "roles": ["ROLE_ADMIN"]
}
~~~

rồi converter nối tiếp **ROLE_**, có thể tạo **ROLE_ROLE_ADMIN**. Đó không phải authority mà **hasRole("ADMIN")** cần.

Ứng dụng nên thống nhất một hợp đồng:

- Claim chứa role name **ADMIN** rồi ứng dụng thêm prefix; hoặc
- Claim chứa authority literal **ROLE_ADMIN**, ứng dụng kiểm/chuẩn hóa không nhân đôi.

Không trộn hai format mà không có quy tắc validation/normalization và tests.

### 7.3. Gắn converter vào Resource Server

Trong SecurityFilterChain:

~~~java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        JwtAuthenticationConverter jwtAuthenticationConverter)
        throws Exception {

    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .requestMatchers("/api/admin/**")
                .hasRole("ADMIN")
            .anyRequest()
                .authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt
                .jwtAuthenticationConverter(jwtAuthenticationConverter)
            )
        );

    return http.build();
}
~~~

Đoạn này là phần bean method minh họa, sử dụng các import cho **HttpSecurity**, **SecurityFilterChain**, **HttpMethod** và **@Bean** tương tự ví dụ trước.

Sau khi decoder chấp nhận JWT, Spring Security gọi converter; **hasRole("ADMIN")** khi ấy mới có thể đạt nếu Authentication mang **ROLE_ADMIN**.

### 7.4. Role có thể nằm ở claim lồng nhau

Một số identity providers biểu diễn roles dưới dạng cấu trúc lồng:

~~~json
{
  "realm_access": {
    "roles": ["ADMIN"]
  },
  "resource_access": {
    "orders-api": {
      "roles": ["ORDER_APPROVER"]
    }
  }
}
~~~

Các field trên là ví dụ về một kiểu mô hình role provider-specific, **không phải định dạng role bắt buộc theo OAuth2/OIDC**. Resource Server phải biết chính xác:

- Role là toàn realm, toàn ứng dụng hay chỉ cho một resource?
- Role dành cho audience/client nào?
- Role có phạm vi tenant không?
- Issuer nào có quyền cấp loại role đó?
- Mapping ROLE_ có được dùng toàn hệ thống hay cần quyền chi tiết như PERM_orders.approve?

Không ánh xạ mọi role của mọi client thành role toàn hệ thống chỉ vì claim có chữ **roles**.

## 8. @PreAuthorize và method security

Ngoài HTTP authorization, Spring Security cung cấp **method security** với annotation **@PreAuthorize**.

Bật method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Một service minh họa:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class OrderApplicationService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public OrderDetails readOrder(long orderId) {
        // Domain policy phải tiếp tục kiểm tenant và ownership.
        throw new UnsupportedOperationException("Implement in application");
    }

    @PreAuthorize("hasRole('ADMIN')")
    public void runAdminOperation() {
        // Yêu cầu ROLE_ADMIN theo mặc định.
    }

    @PreAuthorize("hasAuthority('ROLE_SUPPORT')")
    public void runSupportOperation() {
        // Kiểm chính xác ROLE_SUPPORT.
    }
}
~~~

**OrderDetails** là kiểu nghiệp vụ giả định để minh họa annotation. Các method cần được triển khai trong ứng dụng thật.

Từ ví dụ:

- **hasAuthority('SCOPE_orders.read')** kiểm authority chính xác.
- **hasRole('ADMIN')** dùng role prefix và kiểm **ROLE_ADMIN**.
- **hasAuthority('ROLE_SUPPORT')** kiểm đúng tên **ROLE_SUPPORT**.

### 8.1. Kết hợp scope với policy kiểm bản ghi

Ví dụ khi một request phải có scope và chỉ được đọc đơn của đúng tenant:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.read') " +
    "and @orderPolicy.canRead(authentication, #orderId)"
)
public OrderDetails readOrder(long orderId) {
    return orderService.load(orderId);
}
~~~

Ở đây **orderPolicy** là bean ứng dụng tự xây dựng, kiểm tenant, quan hệ sở hữu, trạng thái và những điều kiện dữ liệu thực tế. Biểu thức giả định tham số **orderId** được Spring Security truy cập bằng tên theo cấu hình compiler/parameter metadata phù hợp.

Kể cả một principal có **ROLE_ADMIN**, quyền có thể chỉ hợp lệ trong một tenant. **hasRole('ADMIN')** không tự kiểm tài nguyên có thuộc phạm vi tenant được phép hay không.

### 8.2. @PreAuthorize cũng cần Authentication đáng tin cậy

Method security dùng Authentication trong SecurityContext. Nó **không tự xác minh chữ ký JWT** và không tự truy xuất JWKS của issuer.

Nếu một custom filter tự tạo Authentication từ role chưa xác minh rồi đặt vào SecurityContext, biểu thức **hasRole('ADMIN')** có thể bị đánh lừa. Thiết kế đúng vẫn là:

~~~text
JwtDecoder verify access token
 -> JwtAuthenticationConverter tạo GrantedAuthority
 -> SecurityContext giữ Authentication
 -> @PreAuthorize so khớp quyền
 -> domain policy xác nhận tài nguyên
~~~

Trong ứng dụng dùng Spring proxy method security, cũng cần hiểu các giới hạn gọi method nội bộ cùng instance và khả năng annotation không được áp dụng qua đường gọi bỏ qua proxy. Cần thiết kế và kiểm thử method authorization thực tế.

## 9. hasAnyAuthority, hasAnyRole và biểu thức kết hợp

Khi endpoint cho phép một trong nhiều quyền, có thể dùng:

~~~java
.hasAnyAuthority("SCOPE_reports.read", "PERM_reports.read")
~~~

hoặc:

~~~java
.hasAnyRole("ADMIN", "AUDITOR")
~~~

Theo mặc định, **hasAnyRole("ADMIN", "AUDITOR")** kiểm **ROLE_ADMIN** hoặc **ROLE_AUDITOR**.

Trong method security:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_reports.export') or hasRole('ADMIN')"
)
public byte[] exportReport() {
    return new byte[0];
}
~~~

Biểu thức **or** cho phép một trong hai cách đạt. Tuy nhiên, điều này **chỉ nên dùng khi chính sách nghiệp vụ cho phép role ADMIN thay thế scope export**. Với Resource Server, có những thao tác mà access token vẫn bắt buộc cần scope cụ thể dù chủ thể có role quản trị; không mở rộng quyền token ngoài hợp đồng cấp quyền mà không có lý do.

Nếu cần **cả** scope và role:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.approve') and hasRole('MANAGER')"
)
public void approveOrder(long orderId) {
    // Kiểm thêm tenant/ownership và trạng thái đơn.
}
~~~

Việc dùng **and** hay **or** phải xuất phát từ yêu cầu authorization, không phải chỉ để xử lý 403 cho thuận tiện.

## 10. ROLE_ có thể được tùy biến, nhưng không nên đổi tùy tiện

Trong nhiều thành phần của Spring Security, tiền tố role mặc định là **ROLE_**. Có các extension point như **GrantedAuthorityDefaults** nhằm tùy biến default role prefix trong những ngữ cảnh hỗ trợ.

Tuy nhiên, cần thận trọng:

- Không giả định việc đổi prefix tác động đồng nhất lên mọi API request authorization, method security, custom expression hoặc các integration theo tất cả phiên bản Spring Security.
- Một số request authorization factory method như **hasRole** có quy tắc prefix cố định theo implementation của chính nó.
- Đổi prefix có thể làm rule hiện có, annotation và test helper hoạt động khác nhau.
- Nếu mục tiêu là kiểm chính xác một authority riêng, **hasAuthority("...")** rõ nghĩa hơn.

Với JWT Resource Server, cách thiết kế dễ hiểu là giữ:

~~~text
SCOPE_  -> OAuth2 scopes
ROLE_   -> application roles
PERM_   -> fine-grained permissions do ứng dụng đặt quy ước
~~~

và cấu hình converter/authorization rule đồng bộ. Chỉ đổi prefix khi có một yêu cầu kiến trúc rõ ràng, đã được kiểm thử với chính phiên bản Spring Security đang sử dụng.

### 10.1. ROLE_ADMIN có tự bao gồm mọi scope không?

Không.

Nếu Authentication có:

~~~text
ROLE_ADMIN
~~~

thì:

- **hasRole("ADMIN")**: đạt.
- **hasAuthority("ROLE_ADMIN")**: đạt.
- **hasAuthority("SCOPE_orders.read")**: không tự đạt.

Nếu ứng dụng muốn role ADMIN được phép thực hiện chức năng cụ thể, có thể xây dựng policy hoặc role hierarchy rõ ràng. Nhưng việc tự mặc định ADMIN có mọi OAuth scope có thể vi phạm hạn chế của access token và nguyên tắc least privilege.

## 11. Những lỗi phổ biến khi phối hợp role và scope

### 11.1. Dùng hasRole để kiểm scope

JWT được map thành **SCOPE_orders.read**, nhưng rule:

~~~java
.hasRole("orders.read")
~~~

kiểm **ROLE_orders.read** nên thường trả 403. Với OAuth scope:

~~~java
.hasAuthority("SCOPE_orders.read")
~~~

### 11.2. Dùng hasAuthority("ADMIN") trong khi có ROLE_ADMIN

Authentication chứa **ROLE_ADMIN** nhưng rule yêu cầu **ADMIN**. Hai chuỗi không khớp. Sửa thành **hasRole("ADMIN")** hoặc **hasAuthority("ROLE_ADMIN")** nếu policy đúng là role ADMIN.

### 11.3. Token có roles nhưng converter chỉ đọc scope

JWT claim **roles: ["ADMIN"]** không tự biến thành **ROLE_ADMIN**. Cần converter rõ ràng hoặc dùng một nguồn authority khác được ứng dụng tin cậy.

### 11.4. Converter tạo ROLE_ROLE_ADMIN

Claim đã chứa **ROLE_ADMIN**, nhưng converter lại thêm **ROLE_**. Phải thống nhất định dạng role name và normalization.

### 11.5. Custom converter làm mất SCOPE_*

Nếu thay converter mặc định bằng converter chỉ đọc roles, các scope đã map theo quy ước có thể biến mất. Dùng converter tổ hợp khi cần cả scope và role.

### 11.6. Role được cấp cho tenant A nhưng truy cập tenant B

Một token có **ROLE_ADMIN** theo một tenant có thể bị hiểu nhầm là admin toàn hệ thống. Cần ràng buộc tenant/resource trong domain policy; một authority đơn giản không luôn mô tả đủ phạm vi.

### 11.7. Scope OIDC bị dùng làm quyền dữ liệu

Có **SCOPE_email** hoặc **SCOPE_profile** không tự cho phép export dữ liệu hoặc chỉnh hồ sơ người dùng khác. Đặt scopes/permissions riêng cho nghiệp vụ.

### 11.8. Rule được đặt sau matcher rộng

Trong DSL authorizeHttpRequests, thứ tự request matcher quan trọng. Nếu một matcher rộng xuất hiện trước rule bảo vệ cụ thể, các request có thể không nhận đúng policy dự định. Đặt rule cụ thể trước và kiểm tất cả HTTP method.

### 11.9. Chỉ kiểm role mà bỏ qua kiểm nguồn JWT

Nếu authentication flow bị custom để đọc JWT JSON trực tiếp, attacker có thể tự ghi roles ADMIN và đạt hasRole. **JwtDecoder** phải xác minh token trước khi mapping.

### 11.10. Nhầm 401 và 403

- **401** thường liên quan tới thiếu hoặc không hợp lệ Bearer token: signature, issuer, audience, expiration.
- **403** thường là token đã được xác thực nhưng thiếu authority hoặc bị domain authorization chặn.
- Có ứng dụng trả **404** để che giấu tài nguyên không thuộc quyền.

Không khắc phục 403 bằng cách bỏ verification hoặc chuyển endpoint nhạy cảm sang permitAll.

## 12. Kiểm thử các rule một cách có mục đích

### 12.1. MockMvc với JWT Authentication mô phỏng

Spring Security Test cung cấp **jwt() request post-processor** để mô phỏng Authentication cho một request Servlet.

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.springframework.security.core.authority.SimpleGrantedAuthority;

// Trong test class đã cấu hình MockMvc và controller/fixture phù hợp.
@Test
void adminCanAccessRoleEndpoint() throws Exception {
    mockMvc.perform(get("/api/admin/reports")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("ROLE_ADMIN")
            )))
        .andExpect(status().isOk());
}

@Test
void oauthScopeOnlyDoesNotGrantAdminRole() throws Exception {
    mockMvc.perform(get("/api/admin/reports")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isForbidden());
}
~~~

Các assertion trên là ví dụ: **200** phụ thuộc controller và fixture của ứng dụng; API thật có thể trả mã thành công khác hoặc lỗi tài nguyên sau khi qua authorization.

Quan trọng hơn: **jwt() trong kiểu test trên thường bỏ qua JwtDecoder thật**. Nó kiểm authorization khi đã có Authentication, không chứng minh JWT giả mạo bị từ chối ở production.

### 12.2. @WithMockUser: roles và authorities

~~~java
@WithMockUser(roles = "ADMIN")
~~~

thường tạo **ROLE_ADMIN**.

~~~java
@WithMockUser(authorities = "SCOPE_orders.read")
~~~

tạo chính xác **SCOPE_orders.read**.

Đây là công cụ test method/request authorization, không phải xác nhận JWT signature, issuer hay audience.

### 12.3. Test converter và decoder riêng

Nên có hai lớp test:

**Converter tests:** Dựng một Jwt test có **scope = orders.read** và **roles = ["ADMIN"]**, gọi converter rồi kiểm authorities:

~~~text
SCOPE_orders.read
ROLE_ADMIN
~~~

Đồng thời kiểm role format không hợp lệ, role bị nhân đôi tiền tố và các trường hợp thiếu scope/roles.

**Decoder/integration tests:** Cấu hình issuer/JWKS test và gửi token được ký bằng private key test. Token giả chữ ký, sai audience, hết hạn hoặc đến từ issuer không được tin phải bị từ chối **trước khi converter tạo authorities**.

Chỉ mock principal/authorities là chưa đủ để chứng minh một JWT có roles ADMIN tự ký sẽ bị chặn.

### 12.4. Ma trận test gợi ý

| Tình huống | API đọc đơn cần scope | API admin cần role |
|---|---|---|
| Không có token | 401 | 401 |
| Token giả chữ ký, claims có đủ scope/role | 401 | 401 |
| JWT đã xác thực, chỉ có SCOPE_orders.read | Qua rule scope | 403 |
| JWT đã xác thực, chỉ có ROLE_ADMIN | Không qua rule scope nếu bắt buộc | Qua rule role |
| JWT đã xác thực, có SCOPE_orders.read và ROLE_ADMIN | Qua rule scope | Qua rule role |
| JWT ký đúng nhưng aud không dành cho API | 401 | 401 |
| JWT đủ authorities nhưng sai tenant | Domain policy từ chối | Tùy policy tenant |

Bảng minh họa các phản hồi thông dụng; mã cụ thể có thể phụ thuộc vào exception handling và policy che giấu tài nguyên.

## 13. Một số tình huống thực tế cần phân biệt

### 13.1. Dự án chỉ dùng OAuth2 scope, không có role

Nếu API chỉ kiểm các scope như **orders.read**, **orders.write** và **reports.export**, có thể hoàn toàn không cần **ROLE_***.

Ví dụ:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.requestMatchers(HttpMethod.POST, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
~~~

Đây thường là mô hình rõ ràng cho service-to-service API, nơi access token biểu diễn delegated authorization. Đừng thêm role converter chỉ vì Spring Security có phương thức hasRole.

### 13.2. Dự án có role nhưng không dùng trong mọi endpoint

Có thể sử dụng:

~~~java
.requestMatchers("/api/admin/**")
    .hasRole("ADMIN")
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

Role và scope được dùng song song theo mục đích. Cần bảo đảm JWT role claim được cấp hợp lệ và các endpoint yêu cầu role không vô tình bỏ kiểm scope nếu policy bắt buộc cả hai.

### 13.3. Quyền cấp duyệt đơn không nên mặc định là role ADMIN

Ví dụ quy tắc:

~~~text
Action: approve order
Requires:
  - Access token có quyền orders.approve
  - Chủ thể là người phê duyệt được phân công
  - Đơn ở trạng thái WAITING_APPROVAL
  - Tenant trùng phạm vi được cấp
~~~

Có thể dùng **hasAuthority("SCOPE_orders.approve")** hoặc **hasAuthority("PERM_orders.approve")** cho quyền kỹ thuật, rồi kiểm điều kiện domain. Một role ADMIN chung không đủ mô tả các điều kiện này.

### 13.4. JWT access token khác ID Token

OIDC **ID Token** cũng có thể chứa claims về người dùng, nhưng dành cho OIDC client để xác nhận đăng nhập. Resource Server phải nhận **access token** đúng audience và token type/profile; không nhận ID Token chỉ vì nó có role hoặc được ký cùng JWKS.

### 13.5. Opaque token cũng tạo authorities

Nếu Resource Server dùng **opaque token introspection**, Authentication có thể lấy scope/authorities từ kết quả introspection đáng tin cậy theo implementation. **hasAuthority** và **hasRole** vẫn kiểm GrantedAuthority, nhưng nguồn xác thực token là introspection chứ không phải JwtDecoder.

## 14. Quy trình thiết kế authority cho Resource Server

Một trình tự thực hành:

1. **Định nghĩa trust:** issuer nào được phép cấp JWT, audience nào dành cho API, thuật toán và JWKS nguồn nào được dùng xác minh.
2. **Xác định scope/role/permission:** quyền nào gắn với access token, quyền nào là vai trò ứng dụng, quyền nào thuộc tenant hoặc bản ghi.
3. **Thống nhất tên claim:** **scope/scp**, **roles**, **permissions** hoặc cấu trúc provider-specific.
4. **Đặt naming convention:** ví dụ **SCOPE_*** cho scope, **ROLE_*** cho role, **PERM_*** cho permission.
5. **Cấu hình converter:** chỉ ánh xạ claim đã được issuer đáng tin cậy cấp; giữ các authority cần thiết khi gộp nhiều nguồn.
6. **Viết HTTP/method rules:** dùng **hasAuthority** cho chuỗi cụ thể, **hasRole** cho role convention.
7. **Thêm domain policy:** tenant, owner, trạng thái, phân công và dữ liệu được phép.
8. **Kiểm thử các lớp:** decoder, converter, request authorization và quyền theo tài nguyên.
9. **Theo dõi vận hành:** ghi lỗi xác thực/phân quyền phù hợp, không log raw Bearer token hoặc claims nhạy cảm.

Ví dụ quy ước:

~~~text
JWT scope          orders.read         -> SCOPE_orders.read
JWT role           ADMIN               -> ROLE_ADMIN
JWT permission     orders.approve      -> PERM_orders.approve

GET /api/orders    hasAuthority("SCOPE_orders.read")
POST /api/approve  hasAuthority("PERM_orders.approve")
GET /api/admin     hasRole("ADMIN")
~~~

Một hệ thống có thể chọn mô hình khác, nhưng phải nhất quán từ issuer, converter tới authorization rule.

## 15. Giải đáp nhanh

**Tại sao hasAuthority("ROLE_ADMIN") chạy được nhưng hasAuthority("ADMIN") không?**

Vì Authentication chứa **ROLE_ADMIN**, không chứa **ADMIN**. hasAuthority kiểm chuỗi chính xác.

**hasRole("ADMIN") có giống hasAuthority("ROLE_ADMIN") không?**

Với prefix vai trò mặc định, chúng kiểm cùng authority **ROLE_ADMIN**. Khác nhau ở cách biểu đạt: hasRole dùng convention, hasAuthority chỉ định literal authority.

**Tôi có nên viết hasRole("ROLE_ADMIN") không?**

Không. Trong request DSL mặc định hãy dùng **hasRole("ADMIN")**; nếu muốn nêu rõ prefix thì dùng **hasAuthority("ROLE_ADMIN")**.

**JWT có scope orders.read mà hasRole("orders.read") trả 403 vì sao?**

Vì JWT scope mặc định thành **SCOPE_orders.read**, trong khi hasRole mặc định tìm **ROLE_orders.read**. Dùng **hasAuthority("SCOPE_orders.read")**.

**JWT có roles ["ADMIN"] mà hasRole("ADMIN") vẫn 403 vì sao?**

Spring Security không tự ánh xạ claim roles tùy ý thành ROLE_ADMIN. Cần converter đúng và issuer/claim policy đáng tin cậy.

**Có ROLE_ADMIN thì tự có mọi SCOPE_* không?**

Không. ROLE_ADMIN và SCOPE_orders.read là hai authority khác tên, trừ khi ứng dụng tạo thêm logic authorization có chủ đích.

**Có SCOPE_email thì được xuất email khách hàng không?**

Không. **email** là scope liên quan tới thông tin danh tính trong OIDC, không mặc định là quyền nghiệp vụ export dữ liệu khách hàng.

**Có thể đổi ROLE_ không?**

Một số thành phần Spring Security hỗ trợ custom default role prefix, nhưng không nên giả định mọi API đều nhận cùng cấu hình. Nếu dùng prefix tùy chỉnh, kiểm cả HTTP và method security trên đúng phiên bản. Với authority literal, **hasAuthority** thường dễ kiểm soát hơn.

**Có nên map role sang SCOPE_ không?**

Chỉ khi có hợp đồng bảo mật rõ ràng. Trong nhiều ứng dụng, giữ scope và role tách biệt giúp tránh nhầm quyền được cấp cho access token với vai trò của người dùng.

## Kết luận

Trong Spring Security, **GrantedAuthority** là dữ liệu mà các rule phân quyền kiểm tra. **hasAuthority("X")** so khớp đúng chuỗi **X**, còn **hasRole("ADMIN")** theo mặc định kiểm **ROLE_ADMIN**. JWT Resource Server thường ánh xạ OAuth scope **orders.read** thành **SCOPE_orders.read**, vì vậy rule đúng là **hasAuthority("SCOPE_orders.read")**, không phải **hasRole("orders.read")**.

Nếu access token có claim **roles**, ứng dụng phải **chủ động ánh xạ** dữ liệu role đáng tin cậy thành **ROLE_*** trước khi hasRole hoạt động. Cả hasAuthority và hasRole đều **không thay thế** chữ ký JWT, issuer/audience validation hoặc kiểm quyền theo tenant/bản ghi.

Chuỗi xử lý đúng là **xác minh token → ánh xạ claims đã được tin cậy thành authorities → kiểm hasAuthority/hasRole → kiểm policy nghiệp vụ trên tài nguyên**.

### Tài liệu tham khảo

- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security API — JwtGrantedAuthoritiesConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html)
- [Spring Security API — JwtAuthenticationConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html)
- [Spring Security API — AuthorityAuthorizationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorityAuthorizationManager.html)
- [Spring Security API — GrantedAuthorityDefaults](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/core/GrantedAuthorityDefaults.html)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
