# Mapping scope sang authority

Trong OAuth 2.0, **scope** mô tả phạm vi quyền truy cập mà authorization server cấp cho một access token, ví dụ `invoices.read` hoặc `invoices.write`. Trong ứng dụng Java dùng **Spring Security**, quyết định truy cập thường dựa trên một tập **`GrantedAuthority`** gắn với đối tượng `Authentication`. Vì vậy, resource server cần một bước chuyển đổi đáng tin cậy: **scope đã được xác minh trong access token → authority mà ứng dụng dùng để thực thi chính sách**.

Ví dụ, access token được cấp scope `invoices.read`; Spring Security có thể tạo authority `SCOPE_invoices.read`. Endpoint đọc hóa đơn kiểm tra `hasAuthority("SCOPE_invoices.read")`. Bước ánh xạ này trông đơn giản, nhưng nếu bỏ qua issuer, audience, loại token, quyền sở hữu hóa đơn hoặc ngữ cảnh tenant, một scope hợp lệ vẫn có thể bị sử dụng sai mục đích.

Trong chương **Scope** của module bảo mật token, bài học tập trung vào quy tắc ánh xạ, cách cấu hình **JWT/opaque token** trong Spring Security, phân biệt scope với role/permission, cách kiểm tra quyền tại API và những lỗi có thể tạo leo thang quyền hoặc truy cập chéo tài nguyên.

## 1. Scope và authority nằm ở hai lớp khác nhau

**OAuth scope** là khái niệm của **giao thức ủy quyền**. Nó thường được client yêu cầu tại authorization server, sau đó server quyết định quyền nào thực sự được cấp trong token. **GrantedAuthority** là khái niệm của **framework bảo mật ứng dụng**: một chuỗi/đối tượng quyền được Spring Security dùng trong các biểu thức như `hasAuthority(...)`.

| Khái niệm | Nơi hình thành/được dùng | Ví dụ | Ý nghĩa |
| --- | --- | --- | --- |
| **Requested scope** | Client gửi tới authorization server | `scope=invoices.read invoices.write` | Quyền client **đề nghị**, chưa chắc được cấp |
| **Granted scope** | Authorization server phê duyệt và gắn với access token | `invoices.read` | Quyền token thực sự có sau khi áp policy |
| **JWT claim `scope` / `scp`** | Biểu diễn quyền được cấp theo profile issuer | `"scope": "invoices.read"` | Dữ liệu chỉ đáng tin sau validation token |
| **GrantedAuthority** | Resource server tạo trong `Authentication` | `SCOPE_invoices.read` | Quyền mà Spring Security kiểm tra tại endpoint |
| **Role** | Chính sách vai trò của tổ chức/ứng dụng | `ROLE_ACCOUNTANT` | Có thể bao gồm nhiều quyền nghiệp vụ, thường cần ràng buộc tenant |
| **Permission/business rule** | Logic của API và dữ liệu | “Chỉ được xem hóa đơn thuộc tenant hiện tại” | Kiểm tra trên **tài nguyên thực tế**, vượt ra ngoài scope |

Scope trả lời gần với câu hỏi **“access token được cấp cho loại thao tác nào tại resource nào?”**; authority trả lời **“Spring Security nhìn thấy quyền nào để ra quyết định?”**. Cả hai đều chưa tự trả lời **“user có sở hữu đúng bản ghi này không?”**.

### 1.1. Vì sao phải ánh xạ?

Một API Spring Security không nên để controller tự phân tích chuỗi JWT thô ở mọi request. Thay vào đó, tầng resource server thực hiện:

1. Nhận credential, thường từ `Authorization: Bearer <access-token>`.
2. Xác minh token, kiểm tra issuer, audience, hạn, loại token và chính sách áp dụng.
3. Trích xuất **granted scopes** từ nguồn đã được xác minh.
4. Chuyển từng scope theo quy tắc **được server kiểm soát** thành `GrantedAuthority`.
5. Đưa authorities vào `Authentication` trong `SecurityContext`.
6. Áp dụng luật endpoint, method security và **phân quyền trên dữ liệu**.

~~~mermaid
flowchart LR
    C["OAuth client"] -->|"Bearer access token"| API["Resource server"]
    API --> V{"Xác minh token:\niss, aud, exp, signature / introspection"}
    V -->|"Sai"| E1["401"]
    V -->|"Đúng"| S["Lấy granted scopes"]
    S --> M["Mapping scope → GrantedAuthority"]
    M --> P{"Endpoint policy +\nquyền trên tài nguyên"}
    P -->|"Thiếu quyền"| E2["403 / 404 theo policy"]
    P -->|"Đủ quyền"| OK["Truy cập dữ liệu hợp lệ"]
~~~

**Không có phép ánh xạ nào biến token chưa xác minh thành đáng tin.** `SCOPE_invoices.read` được tạo từ payload do attacker tự gửi vẫn không an toàn, dù chuỗi authority có vẻ đúng.

## 2. Scope xuất hiện trong OAuth 2.0 như thế nào?

### 2.1. Scope được yêu cầu khác scope được cấp

Một client có thể đề nghị:

~~~http
GET /authorize?response_type=code&client_id=invoice-web&scope=openid%20invoices.read%20invoices.write&state=<state>&code_challenge=<challenge>&code_challenge_method=S256 HTTP/1.1
Host: auth.example.com
~~~

Authorization server kiểm tra đăng ký client, grant, consent/user, policy và tài nguyên đích. Nó **có thể chỉ cấp một tập con** như `invoices.read`. Resource server **phải dựa trên token được cấp**, không dựa vào `scope` trong URL yêu cầu ban đầu hay một trường tự khai từ client.

Ví dụ phản hồi token endpoint:

~~~json
{
  "access_token": "<opaque-or-jwt-access-token>",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "invoices.read"
}
~~~

Theo OAuth 2.0, scope thông thường là **danh sách các giá trị phân tách bằng dấu cách**. Các tên như `read`, `invoices.read` hoặc `api://example/invoices.read` **không có ngữ nghĩa chung cho mọi nhà cung cấp**. API và authorization server phải có **hợp đồng về tên, ý nghĩa và audience** của từng scope.

### 2.2. Scope trong JWT access token

Ví dụ payload JWT access token minh họa:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "https://api.example.com/invoices",
  "client_id": "invoice-web",
  "scope": "invoices.read invoices.write",
  "iat": 1795410600,
  "exp": 1795411500
}
~~~

Đây **không phải JWT hợp lệ có chữ ký**. JSON chỉ để minh họa cách mang scope. Trong **JWT Profile for OAuth 2.0 Access Tokens (RFC 9068)**, claim `scope` khi có được biểu diễn bằng **chuỗi scope phân cách bằng dấu cách**. Một số nhà cung cấp dùng claim `scp` (có thể là chuỗi hoặc mảng tùy hệ thống) hoặc tên khác. Spring Security có converter mặc định hỗ trợ những tên claim thông dụng, nhưng **hình dạng claim và ý nghĩa phải được cấu hình theo issuer**.

### 2.3. Scope trong opaque access token

Opaque token là một chuỗi mà client không cần biết cấu trúc. API có thể nhận metadata từ authorization server qua **token introspection (RFC 7662)**:

~~~json
{
  "active": true,
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "client_id": "invoice-web",
  "aud": "https://api.example.com/invoices",
  "scope": "invoices.read",
  "exp": 1795411500
}
~~~

Chỉ khi kết quả introspection đến từ **kênh tin cậy**, token còn active, audience và metadata phù hợp, ứng dụng mới được chuyển scope thành authority. **Không lấy chuỗi opaque rồi tự giải mã hay suy đoán scope**.

## 3. Quy tắc mặc định trong Spring Security

Với Spring Security Resource Server sử dụng JWT, `JwtGrantedAuthoritiesConverter` mặc định tìm các claim scope quen thuộc (thường `scope` hoặc `scp`) và biến từng giá trị thành `GrantedAuthority` có tiền tố **`SCOPE_`**.

Ví dụ:

~~~text
JWT claim:
  "scope": "invoices.read invoices.write"

Spring Security authorities mặc định:
  SCOPE_invoices.read
  SCOPE_invoices.write
~~~

Thứ tự cơ bản:

~~~text
JwtDecoder: JWT hợp lệ
     ↓
JwtAuthenticationConverter
     ↓
JwtGrantedAuthoritiesConverter
     ↓
JwtAuthenticationToken(principal, authorities)
     ↓
hasAuthority("SCOPE_invoices.read")
~~~

### 3.1. `hasAuthority` khác `hasRole`

| Biểu thức Spring Security | Authority thực sự cần có | Ghi chú |
| --- | --- | --- |
| `hasAuthority("SCOPE_invoices.read")` | `SCOPE_invoices.read` | Phù hợp mapping scope mặc định |
| `hasAnyAuthority("SCOPE_invoices.read", "SCOPE_invoices.admin")` | Một trong hai authority | Logic “hoặc” cho endpoint |
| `hasRole("ADMIN")` | `ROLE_ADMIN` theo tiền tố role mặc định | Kiểm tra role, **không phải** scope |
| `hasAuthority("ROLE_ADMIN")` | `ROLE_ADMIN` chính xác | Tương đương role mặc định trong tình huống này |
| `hasAuthority("invoices.read")` | `invoices.read` chính xác | **Không khớp** `SCOPE_invoices.read` nếu dùng converter mặc định |

Hai prefix `SCOPE_` và `ROLE_` là **quy ước tại ứng dụng/framework**; chúng **không** phải một phần bắt buộc của giá trị scope trong OAuth token.

Sai lầm phổ biến:

~~~java
// JWT có scope = "invoices.read" và Spring tạo SCOPE_invoices.read.
// SAI: mặc định không có ROLE_invoices.read.
.hasRole("invoices.read")

// ĐÚNG khi dùng converter mặc định:
.hasAuthority("SCOPE_invoices.read")
~~~

Không nên gắn `ROLE_ADMIN` tùy tiện chỉ vì token chứa scope `admin`. **Quyền quản trị nghiệp vụ và scope OAuth là hai lớp chính sách khác nhau**.

## 4. Cấu hình Resource Server JWT trong Spring Security

Giả sử API hóa đơn tin issuer `https://auth.example.com` và yêu cầu các quyền:

- `GET /api/invoices/**` cần `invoices.read`.
- `POST /api/invoices/**` cần `invoices.write`.
- Các request khác cần người gọi có credential hợp lệ; policy cụ thể bổ sung tại controller/service.

Trong Spring Boot, khai báo issuer tin cậy theo cấu hình tương ứng:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com
~~~

**Issuer URI một mình chưa đủ làm hợp đồng quyền truy cập.** Resource server còn phải kiểm tra token **dành đúng audience của API**, loại token và các ràng buộc profile. Việc xây dựng audience validator cần nhất quán với cách AS cấp token; xem mục tiếp theo.

### 4.1. SecurityFilterChain minh họa

Ví dụ Java theo phong cách **Spring Security 6**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        JwtGrantedAuthoritiesConverter scopes =
            new JwtGrantedAuthoritiesConverter();

        // Claim được AS cam kết sử dụng. Đây là chuỗi scope OAuth.
        scopes.setAuthoritiesClaimName("scope");
        scopes.setAuthorityPrefix("SCOPE_");

        JwtAuthenticationConverter jwtAuthentication =
            new JwtAuthenticationConverter();
        jwtAuthentication.setJwtGrantedAuthoritiesConverter(scopes);

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/invoices/**")
                    .hasAuthority("SCOPE_invoices.read")
                .requestMatchers(HttpMethod.POST, "/api/invoices/**")
                    .hasAuthority("SCOPE_invoices.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt.jwtAuthenticationConverter(jwtAuthentication))
            )
            .build();
    }
}
~~~

Đoạn này minh họa **scope mapping và authorization rules**; để chạy trong ứng dụng cần dependencies/cấu hình Resource Server/JwtDecoder và các thiết lập HTTP khác phù hợp. Với **API chỉ nhận Bearer header và không dùng cookie đăng nhập**, cấu hình CSRF thường được xem xét khác ứng dụng web dùng session cookie; nếu endpoint POST trả `403` do CSRF filter, **không vội kết luận scope sai**. Chỉ tắt CSRF khi đã chắc kiến trúc không dựa trên credential trình duyệt tự gửi và đã đánh giá các đường request khác.

Lưu ý tính ưu tiên của `requestMatchers`: luật cụ thể phải đứng trước `.anyRequest()`. Những endpoint không được khai báo rõ scope nên có policy cố định theo yêu cầu nghiệp vụ; `.authenticated()` chỉ yêu cầu xác thực credential, **không thay thế phân quyền tài nguyên**.

### 4.2. Không quên audience và issuer

JWT được ký đúng bởi issuer vẫn có thể dành cho **API khác**. Ví dụ `aud=https://api.example.com/profile` không nên được dùng tại `https://api.example.com/invoices` dù token chứa chuỗi `invoices.read`.

Giả sử cấu hình dùng `NimbusJwtDecoder`, có thể bổ sung validator cho audience:

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
class TrustedJwtConfig {
    private static final String ISSUER = "https://auth.example.com";
    private static final String API_AUDIENCE =
        "https://api.example.com/invoices";

    @Bean
    JwtDecoder jwtDecoder() {
        // URI JWKS được lấy từ cấu hình issuer đáng tin cậy;
        // không tải từ URL do header của JWT chưa xác minh đưa ra.
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri("https://auth.example.com/.well-known/jwks.json")
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience() != null &&
                    jwt.getAudience().contains(API_AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", "Unexpected audience", null)
            );
        };

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(ISSUER),
            audienceValidator
        ));
        return decoder;
    }
}
~~~

Ví dụ **cố ý** thể hiện cả kiểm tra issuer/time và audience. Ứng dụng thực phải bổ sung/giữ các kiểm tra theo profile access token được sử dụng, chẳng hạn JWT `typ` phù hợp, thuật toán ký được phép, các claim bắt buộc, quy tắc tenant và principal type. JWKS URL trong ví dụ chỉ là endpoint giả định; với provider thật hãy lấy từ metadata/đăng ký tin cậy.

**Không tạo authority trước khi decoder/introspector xác minh token.** Thứ tự validation và mapping là ranh giới bảo mật, không chỉ là lựa chọn kiến trúc.

## 5. Khi issuer dùng `scp` hoặc định dạng scope riêng

Không phải nhà cung cấp nào cũng đặt scope trong claim `scope`. Một issuer có thể trả:

~~~json
{
  "iss": "https://login.partner.example",
  "aud": "https://api.example.com/invoices",
  "sub": "user-42",
  "scp": ["invoices.read", "invoices.write"],
  "exp": 1795411500
}
~~~

Trong trường hợp này, sau khi xác minh định dạng/token theo hợp đồng issuer, resource server có thể cấu hình:

~~~java
JwtGrantedAuthoritiesConverter converter =
    new JwtGrantedAuthoritiesConverter();
converter.setAuthoritiesClaimName("scp");
converter.setAuthorityPrefix("SCOPE_");

JwtAuthenticationConverter authentication =
    new JwtAuthenticationConverter();
authentication.setJwtGrantedAuthoritiesConverter(converter);
~~~

`JwtGrantedAuthoritiesConverter` hỗ trợ các claim scope phổ biến theo quy tắc của thư viện, nhưng **không suy diễn tùy ý** từ mọi claim custom như `permissions`, `roles`, `tenant`. Việc đặt tên `scp` không tự bảo đảm claim luôn là danh sách; cần đọc profile issuer và kiểm thử kiểu dữ liệu thực tế.

### 5.1. Khi vừa có `scope` vừa có `scp`

Một token có cả hai claim có thể tạo ý nghĩa mơ hồ, nhất là khi chúng khác nhau:

~~~json
{
  "scope": "invoices.read",
  "scp": ["invoices.write"]
}
~~~

**Không tự gộp thành tất cả quyền** trừ khi profile đã định nghĩa rõ điều đó. Một converter có thể chọn một claim theo ưu tiên, dẫn đến sai lệch với kỳ vọng của API. Nên thống nhất **một nguồn authority chính** cho mỗi issuer/token profile, rồi từ chối hoặc ghi nhận cấu hình sai khi dữ liệu mâu thuẫn theo chính sách.

### 5.2. Đổi prefix có thể làm thay đổi toàn bộ policy

Nếu cấu hình:

~~~java
converter.setAuthorityPrefix("PERM_");
~~~

Scope `invoices.read` sẽ thành `PERM_invoices.read`; `hasAuthority("SCOPE_invoices.read")` **không còn khớp**. Khi đổi prefix, phải cập nhật đồng bộ endpoint rules, method security, test và tài liệu hợp đồng. Tránh dùng prefix rỗng nếu việc đó khiến scope va chạm với role/authority do nguồn khác tạo.

## 6. Mapping trực tiếp hay mapping qua permission nội bộ?

Có hai chiến lược phổ biến:

**A. Mapping trực tiếp:** `invoices.read → SCOPE_invoices.read`. Phù hợp khi tên scope đã ổn định, gắn với một API và policy của endpoint có thể kiểm tra trực tiếp.

**B. Mapping có whitelist:** `invoices.read → invoice:read` theo quy tắc do resource server sở hữu. Hữu ích khi ngôn ngữ quyền nghiệp vụ khác với tên scope bên ngoài hoặc cần tránh phụ thuộc trực tiếp vào nhà cung cấp.

Không có chiến lược nào tự động an toàn hơn. Rủi ro nằm ở **nguồn dữ liệu, khả năng bị giả mạo, ánh xạ quá rộng và việc quên kiểm tra tài nguyên**.

| Scope nhận từ issuer | Authority nội bộ minh họa | Ý nghĩa |
| --- | --- | --- |
| `invoices.read` | `invoice:read` | Được gọi chức năng đọc hóa đơn |
| `invoices.write` | `invoice:write` | Được gọi chức năng tạo/sửa trong chính sách |
| `invoices.approve` | `invoice:approve` | Được xét quyền phê duyệt hóa đơn |
| `profile` | *Không ánh xạ vào business authority* | OIDC scope liên quan claims hồ sơ |
| `unrecognized.scope` | *Bỏ qua hoặc từ chối theo policy* | Không tự cấp quyền ngoài hợp đồng |

### 6.1. Ví dụ whitelist converter Java

Đoạn code minh họa chỉ hỗ trợ `scope` **dạng chuỗi phân cách bằng dấu cách** theo hợp đồng JWT profile đã chọn. Claim không hợp lệ hoặc scope không nằm trong whitelist **không được tự động trở thành quyền**:

~~~java
import java.util.Arrays;
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;

public final class InvoiceAuthorityConverter
        implements Converter<Jwt, Collection<GrantedAuthority>> {

    private static final Map<String, String> ALLOWED_MAPPINGS = Map.of(
        "invoices.read",    "invoice:read",
        "invoices.write",   "invoice:write",
        "invoices.approve", "invoice:approve"
    );

    @Override
    public Collection<GrantedAuthority> convert(Jwt jwt) {
        Object rawClaim = jwt.getClaims().get("scope");
        if (!(rawClaim instanceof String rawScope) ||
                rawScope.isBlank()) {
            return Set.of();
        }

        return Arrays.stream(rawScope.strip().split("\\s+"))
            .map(ALLOWED_MAPPINGS::get)
            .filter(java.util.Objects::nonNull)
            .map(name -> (GrantedAuthority) new SimpleGrantedAuthority(name))
            .collect(Collectors.toCollection(LinkedHashSet::new));
    }
}
~~~

Để sử dụng converter:

~~~java
JwtAuthenticationConverter jwtAuth = new JwtAuthenticationConverter();
jwtAuth.setJwtGrantedAuthoritiesConverter(
    new InvoiceAuthorityConverter()
);

// Sau khi config jwtAuthenticationConverter(jwtAuth):
// .hasAuthority("invoice:read")
// .hasAuthority("invoice:approve")
~~~

Điểm tốt của whitelist là **thay đổi claim bất thường từ token không sinh ra quyền bất kỳ** như `ROLE_SUPER_ADMIN`. Tuy nhiên, nếu API cần biết token có claim scope sai cấu trúc hay không, hệ thống nên **từ chối token theo hợp đồng** thay vì chỉ bỏ qua. Việc *bỏ qua scope lạ* có thể thích hợp với compatibility policy; việc *từ chối token chứa scope ngoài hợp đồng* có thể thích hợp với policy chặt hơn. Cả hai phải **fail closed về quyền**.

### 6.2. Không gộp role và scope bừa bãi

Giả sử token có:

~~~json
{
  "scope": "invoices.read",
  "roles": ["tenant-admin"],
  "tenant_id": "tenant-acme"
}
~~~

Không nên tự ánh xạ `tenant-admin` thành **`ROLE_ADMIN` toàn hệ thống**, vì quyền này có thể chỉ có giá trị **trong tenant-acme**. Nếu cần mapping role, hãy có converter/authorization service riêng dựa trên issuer, token profile, tenant context và quyền tài nguyên; đánh giá liệu role trong token có thể lỗi thời sau khi membership thay đổi hay không.

## 7. Scope, role và object-level authorization

**Scope đủ để truy cập endpoint chưa chắc đủ để đọc hoặc sửa bản ghi cụ thể.** Đây là khác biệt cốt lõi giữa quyền gọi **chức năng API** và quyền trên **đối tượng dữ liệu**.

Giả sử user `user-42` có:

~~~text
Bearer access token đã xác minh:
  sub       = user-42
  tenant_id = tenant-acme
  scope     = invoices.read

Request:
  GET /api/invoices/inv-123
~~~

API cần kiểm tra:

- Token hợp lệ, issuer/audience và token type đúng.
- Authority `SCOPE_invoices.read` (hoặc authority tương đương theo mapping nội bộ) hiện diện.
- `inv-123` có thật và thuộc `tenant-acme`.
- User có membership/role hoặc quyền sở hữu phù hợp đối với hóa đơn đó.
- Hóa đơn có đang ở trạng thái cho phép xem không, có bị khóa bởi quy tắc nghiệp vụ khác không.

### 7.1. Method security kết hợp kiểm tra tài nguyên

Có thể bật method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {}
~~~

Ví dụ dịch vụ có policy ở cả authority và repository query:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class InvoiceService {
    private final InvoiceRepository repository;
    private final TenantPolicy tenantPolicy;

    public InvoiceService(
            InvoiceRepository repository,
            TenantPolicy tenantPolicy) {
        this.repository = repository;
        this.tenantPolicy = tenantPolicy;
    }

    @PreAuthorize("hasAuthority('SCOPE_invoices.read')")
    public InvoiceDto readInvoice(
            String invoiceId,
            VerifiedPrincipal principal) {
        String tenantId = tenantPolicy.requireActiveTenant(principal);
        return repository.findVisibleInvoice(
                tenantId, invoiceId, principal.subject()
            )
            .orElseThrow(ResourceNotFoundException::new);
    }
}
~~~

`VerifiedPrincipal`, `TenantPolicy`, `InvoiceRepository`, `InvoiceDto` và `ResourceNotFoundException` ở đây là **kiểu minh họa thuộc ứng dụng**, không phải các lớp dựng sẵn của Spring Security. Khi triển khai, `VerifiedPrincipal` phải đến từ security context đã được xác thực; không nhận một object principal tự khai trong JSON body.

Ví dụ query có phạm vi tenant:

~~~sql
SELECT i.*
FROM invoices AS i
WHERE i.id = :invoice_id
  AND i.tenant_id = :verified_tenant_id
  AND (
      i.owner_user_id = :verified_subject
      OR EXISTS (
          SELECT 1
          FROM tenant_invoice_permissions AS p
          WHERE p.tenant_id = i.tenant_id
            AND p.invoice_id = i.id
            AND p.user_id = :verified_subject
            AND p.permission = 'read'
      )
  );
~~~

Ở đây cả `verified_tenant_id` và `verified_subject` đều do tầng server lấy từ **credential và nguồn quyền đã xác minh**, không lấy từ header `X-User-Id` hoặc `X-Tenant-Id` do client gửi. Nếu API chỉ có `hasAuthority` nhưng repository truy vấn theo `invoice_id` mà không kiểm tra owner/tenant, đó là nguy cơ **Broken Object Level Authorization (BOLA/IDOR)**.

### 7.2. Một scope có thể ánh xạ ra nhiều business permission không?

Có thể, **nếu đây là chính sách đã được chủ sở hữu API định nghĩa**. Ví dụ `invoices.manage` có thể bao gồm `invoice:read` và `invoice:write`, nhưng không nên **tự mặc định** `invoices.read` bao hàm `invoices.approve` hay `admin`. Một scope càng rộng thì yêu cầu least privilege và đánh giá rủi ro càng cao.

Tránh tự tạo wildcard từ tên scope nếu AS không cam kết semantics:

~~~text
SAI: invoices.* tự động là mọi quyền quản trị tương lai
ĐÚNG: scope và capability được cấp/ánh xạ theo allowlist công khai
~~~

## 8. Ngữ cảnh người dùng, ứng dụng và tenant

### 8.1. Delegated user token

Authorization Code + PKCE thường liên quan một người dùng. Scope `invoices.write` trên access token cho biết client được cấp khả năng gọi thao tác ghi trong giới hạn grant; resource server còn phải kiểm tra **user, tenant, role và trạng thái dữ liệu**.

**User đăng nhập thành công không tự đồng nghĩa token có mọi scope.** Authorization server có thể từ chối scope được yêu cầu do client registration, consent hoặc chính sách người dùng.

### 8.2. App-only token từ Client Credentials

Một dịch vụ chạy theo lịch có thể nhận:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "billing-batch-service",
  "client_id": "billing-batch-service",
  "aud": "https://api.example.com/invoices",
  "scope": "invoices.export",
  "exp": 1795411500
}
~~~

Token đó có thể có authority `SCOPE_invoices.export`, nhưng **không chứng minh user nào đã đăng nhập**. API nên phân biệt **app-only** và **delegated user** theo token profile/claim đáng tin; không dùng `sub` như thể nó chắc chắn là human user. Service có thể chỉ được export dữ liệu của tenant đã cấp grant.

### 8.3. Scope không bao hàm tất cả tenant

Một user là admin ở Acme nhưng viewer ở Globex. Nếu token có `scope=invoices.write` trong **tenant-acme**, API **không được** dùng scope đó để sửa hóa đơn của **tenant-globex**.

Nên truyền tenant context qua claim/access-token metadata đã được issuer xác minh hoặc nguồn phân quyền server-side, rồi đối chiếu resource tenant. Nếu token không chứa tenant, API có thể dùng lookup tin cậy để xác định membership; không nhận `X-Tenant-Id` tự khai làm bằng chứng được quyền.

### 8.4. Scope của OIDC và scope nghiệp vụ

OIDC định nghĩa các scope như `openid`, `profile`, `email` để yêu cầu xác thực user và claims. Chúng **không nên** được coi là quyền `invoices.read`, `payments.write` hoặc `users.admin`. **ID token** hướng tới OIDC client, còn **access token** hướng tới API theo audience được cấp.

Một resource server không được chấp nhận ID token của client chỉ vì nó có claims `sub`, `email` hoặc `acr`. Mỗi token có **mục đích và đối tượng nhận** riêng.

## 9. Scope và audience luôn phải đi cùng nhau

Giả sử authorization server phát hai access token:

~~~text
Token A:
  aud   = https://api.example.com/invoices
  scope = invoices.read

Token B:
  aud   = https://api.example.com/reports
  scope = invoices.read
~~~

API hóa đơn **chỉ được chấp nhận token dành cho API hóa đơn** theo profile, dù token B có cùng tên scope. Việc scope giống nhau giữa hai resource server không tạo quyền dùng chéo.

Với OAuth 2.0 **Resource Indicators (RFC 8707)**, client có thể chỉ định resource đích khi yêu cầu token nếu AS hỗ trợ. AS xác định audience và phạm vi hợp lệ cho resource đó; API không chấp nhận một access token chỉ vì client tự khai `resource` trong request.

### 9.1. Multiple audiences và shared scopes

Một số hệ thống phát token có nhiều audience. Điều này có thể hợp lệ theo profile, nhưng tăng khó khăn về least privilege và token replay giữa các API. Mỗi resource server phải kiểm tra mình là **audience hợp lệ**, scope có semantics phù hợp và các yêu cầu bổ sung của mình; không mặc định mọi API diễn giải một scope rộng như nhau.

Đối với hệ thống phức tạp, cân nhắc **token cho từng resource/audience**, downscoping hoặc token exchange theo chính sách. Token nhỏ, đúng audience và quyền tối thiểu thường dễ kiểm tra hơn token “mọi API, mọi scope”.

## 10. Opaque token và authority mapping

Trong Spring Security Resource Server, opaque access token thường được xử lý qua `OpaqueTokenIntrospector`; kết quả introspection cung cấp principal/attributes/authorities mà framework dùng để tạo authentication. Cấu hình cơ bản có thể như:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: invoice-api-introspection
          client-secret: <secret-from-protected-configuration>
~~~

Ví dụ chỉ minh họa **các khóa cấu hình**; không đặt secret thật trong repository. Introspection cần TLS, credential của resource server được bảo vệ và kiểm tra `active` cùng audience, token type và quyền theo policy.

Tùy phiên bản/framework, scope introspection có thể được ánh xạ thành authorities với prefix `SCOPE_`; nếu yêu cầu đặc thù, ứng dụng có thể tùy biến cách chuyển principal/authorities sau khi đã xác thực kết quả introspection. Không mặc định mọi opaque-token provider trả cùng định dạng `scope`, `scp`, `roles` hoặc tenant.

### 10.1. Vì sao không dùng header `X-Scope`?

Giả sử client gửi:

~~~http
GET /api/invoices HTTP/1.1
Authorization: Bearer <token>
X-Scope: invoices.write
~~~

Nếu API tạo authority từ `X-Scope` mà không xác minh nguồn, attacker có thể tự nâng quyền bằng cách sửa header. Header nội bộ do API gateway thêm **chỉ có thể được tin khi đường truyền, nguồn gốc, hop stripping, mTLS và chính sách mạng bảo đảm client không giả mạo được**; mô hình đơn giản và an toàn hơn thường là API trực tiếp xác minh token hoặc tiêu thụ token/identity assertion có ranh giới tin cậy rõ ràng.

## 11. Khi nào trả 401, 403 hoặc insufficient_scope?

| Trường hợp | Phản hồi thường gặp | Ý nghĩa |
| --- | --- | --- |
| Không có Bearer token ở endpoint yêu cầu xác thực | `401 Unauthorized` | Cần credential |
| Token sai chữ ký/issuer/audience/hết hạn | `401`, có thể `WWW-Authenticate: Bearer error="invalid_token"` | Chưa chấp nhận credential |
| Token hợp lệ, nhưng thiếu scope cần thiết | `403 Forbidden`, có thể `WWW-Authenticate: Bearer error="insufficient_scope"` | Credential được nhận nhưng thiếu quyền được cấp |
| Scope đủ nhưng user không sở hữu hóa đơn | `403` hoặc `404` theo policy tránh lộ tài nguyên | Thiếu quyền trên object cụ thể |
| Token thiếu thông tin tenant cần thiết | Từ chối theo policy, thường `403` nếu token hợp lệ | Không được suy đoán tenant mặc định |
| POST bị CSRF filter chặn trong web app dùng cookie | Thường `403` | Không nhất thiết liên quan scope |

Ví dụ yêu cầu scope bổ sung theo giao thức Bearer:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope",
  scope="invoices.write"
~~~

Scope trong challenge là **điều kiện cần cho thao tác**, không hứa rằng client/user chắc chắn được authorization server cấp scope đó. Client không nên tự thêm chuỗi scope vào token, cũng không nên retry vô hạn để vượt chính sách consent hoặc quản trị.

Nếu yêu cầu người dùng **xác thực mạnh hơn hoặc mới hơn**, đó là **step-up authentication** và có cơ chế challenge riêng (ví dụ `insufficient_user_authentication` theo RFC 9470); việc đổi scope không tự thay `acr` hay `auth_time`.

## 12. Vòng đời token ảnh hưởng đến mapping scope

### 12.1. Thu hồi scope trong khi JWT còn hiệu lực

User mất role `invoice-editor` lúc 10:00; JWT đã phát lúc 09:50 còn `scope=invoices.write` đến 10:30. Với kiểm tra JWT offline, resource server có thể vẫn tạo `SCOPE_invoices.write` cho đến khi token hết hạn nếu không có cơ chế phát hiện thu hồi.

Các lựa chọn:

- Cấp access token ngắn hạn và scope tối thiểu.
- Dùng opaque token với introspection/lookup và kiểm soát cache phù hợp.
- Dùng version/denylist hoặc lookup quyền hiện hành cho thao tác nhạy cảm.
- Ràng buộc role/tenant tại bước kiểm tra business policy, không hoàn toàn tin claims quyền dài hạn.

**Xóa cookie hoặc refresh token của client không nhất thiết vô hiệu hóa JWT access token đã bị đánh cắp**. Vòng đời/thu hồi phải được thiết kế theo từng loại credential.

### 12.2. Refresh token không tự cho thêm scope

Client có refresh token được cấp cho `invoices.read` không nên tự xin rộng hơn thành `invoices.write` nếu không có grant/consent/chính sách mới. Authorization server chịu trách nhiệm giới hạn scope khi refresh. API chỉ tin **scope trên access token được cấp thực tế**, không tin tên scope trong request refresh.

### 12.3. Replay và bearer token

Một access token Bearer có scope `invoices.write` có thể bị kẻ tấn công dùng lại nếu bị lộ, cho đến khi hết hạn/thu hồi theo thiết kế. Mapping thành `GrantedAuthority` không chống được việc đó. Cần TLS, hạn ngắn, tránh log token, lưu trữ phù hợp, chống XSS/CSRF theo kiến trúc và cân nhắc **sender-constrained tokens** như DPoP hoặc mTLS khi phù hợp.

## 13. Kiểm thử mapping scope sang authority

**Đừng chỉ kiểm tra request thành công với token có scope đúng**. Cần kiểm thử các ngữ cảnh sai phạm khác nhau:

| Test case | Kỳ vọng |
| --- | --- |
| JWT hợp lệ, `scope="invoices.read"`, GET danh sách hóa đơn | Tạo `SCOPE_invoices.read`; tiếp tục kiểm tra quyền dữ liệu |
| JWT hợp lệ chỉ có `scope="invoices.read"`, POST hóa đơn | Không có `SCOPE_invoices.write`; bị từ chối |
| JWT có `scope="invoices.read invoices.write"` | Tạo đúng 2 authorities được hỗ trợ, không nhân quyền khác |
| Token dùng `scp` nhưng converter đang chỉ đọc `scope` | Không tự cấp quyền; sửa cấu hình claim theo issuer |
| Token có `scope` và `scp` mâu thuẫn | Theo policy rõ ràng; không tự gộp tăng quyền |
| Scope lạ `admin` hoặc `ROLE_SUPER_ADMIN` | Không được ánh xạ sang quyền quản trị ngoài allowlist |
| JWT sai chữ ký nhưng payload có scope đúng | Bị từ chối **trước khi mapping** |
| JWT đúng chữ ký nhưng sai `aud` | Bị từ chối trước khi mapping |
| ID token OIDC có custom claim `scope` | Không được dùng như access token cho API |
| Token app-only có `invoices.export` | Chỉ vào policy dịch vụ, không được coi là user |
| Token Acme có `invoices.write`, request của Globex | Bị từ chối vì tenant/resource mismatch |
| Access token còn hạn nhưng role user đã bị thu hồi | Bị xử lý theo revocation/membership policy |
| `hasRole("ADMIN")` nhưng chỉ có `SCOPE_admin` | Không match |
| Opaque introspection trả `active=false` | Bị từ chối trước khi có authorities |
| Endpoint yêu cầu `invoices.read` nhưng user đoán được ID của người khác | Không được trả dữ liệu trái quyền |

### 13.1. Lưu ý khi dùng test mock của Spring Security

Trong unit/web-layer test, mock JWT có thể **bỏ qua việc xác minh chữ ký thực** để tập trung kiểm tra rule. Điều đó hữu ích cho policy, nhưng **không chứng minh decoder đã kiểm tra issuer, audience và thuật toán**.

Ví dụ minh họa MockMvc với Spring Security test support:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

// Trong test class có MockMvc được cấu hình Spring Security:
JwtGrantedAuthoritiesConverter scopes =
    new JwtGrantedAuthoritiesConverter();

mockMvc.perform(get("/api/invoices")
        .with(jwt()
            .jwt(token -> token.claim("scope", "invoices.read"))
            .authorities(scopes)))
    .andExpect(status().isOk());
~~~

Test trên chỉ có giá trị khi endpoint và dữ liệu fixture phù hợp; mock được Spring Security test tạo ra **không phải access token thật từ AS**. Bổ sung integration/security tests với decoder hoặc introspector thật/giả lập có validation đầy đủ để chắc token sai `iss`, `aud`, signature, `exp`, `typ` bị từ chối như thiết kế.

### 13.2. Quan sát log mà không làm lộ token

Có thể ghi **issuer đã chuẩn hóa, audience, client ID, subject nội bộ, số lượng scope/authority, quyết định policy và correlation ID** theo chính sách bảo vệ dữ liệu. Không ghi toàn bộ `Authorization` header, JWT, refresh token hoặc client secret chỉ để debug mismatch `hasAuthority`.

Khi báo lỗi “scope không khớp”, nên kiểm tra theo thứ tự: **token có hợp lệ không → đúng audience/loại token không → issuer dùng claim nào → converter tạo authority nào → endpoint đang đòi authority nào → resource policy có cho phép không**. Cách này giúp phân biệt lỗi mapping với lỗi validation, CSRF hoặc BOLA.

## 14. Những sai lầm thường gặp

| Phát biểu | Vấn đề | Cách sửa |
| --- | --- | --- |
| “Client request scope nào thì API có quyền đó.” | Requested scope có thể bị AS từ chối/giới hạn | Lấy scope từ access token **đã xác minh** |
| “JWT có claim scope là đủ, khỏi kiểm tra aud.” | Token của API khác có thể bị replay | Kiểm tra issuer, audience và loại token |
| “`hasRole('invoices.read')` sẽ khớp `SCOPE_invoices.read`.” | `hasRole` mặc định đòi `ROLE_` | Dùng `hasAuthority("SCOPE_invoices.read")` |
| “Scope admin là role admin.” | Quyền OAuth khác role/tenant của ứng dụng | Có policy mapping rõ, whitelist và tenant boundary |
| “`scope=read` cho phép đọc mọi bản ghi.” | Thiếu object-level authorization | Kiểm tra owner/tenant/permission trên từng tài nguyên |
| “ID token có sub và scope thì gửi thẳng API.” | ID token dành cho OIDC client | API yêu cầu access token đúng audience |
| “Chỉ cần đổi prefix để hợp mọi thư viện.” | Rule và converter có thể lệch nhau | Kiểm thử converter + `hasAuthority` đồng bộ |
| “Token vừa refresh nghĩa là mọi quyền đã được cập nhật.” | Chính sách phát hành/cache tùy AS | Kiểm tra granted scopes và revocation/membership |
| “Header `X-Scope` của client là đáng tin.” | Client tự gửi/sửa được | Chỉ tin credential/metadata từ ranh giới đã xác minh |
| “Một authority đủ thì không cần kiểm tra đối tượng.” | Dẫn đến BOLA/IDOR | Bổ sung resource/tenant/ownership policy |

## 15. Checklist thiết kế và triển khai

1. **Định nghĩa hợp đồng scope:** tên, audience/resource, mục đích, principal type, tenant context và những quyền nghiệp vụ tương ứng.
2. **Đăng ký đúng grant/client:** Authorization Code + PKCE khi có user; Client Credentials khi app-only; AS quyết định scopes được cấp.
3. **Xác minh token trước mapping:** chữ ký hoặc introspection, `iss`, `aud`, thời gian, token type/profile và active status.
4. **Chọn claim nguồn:** `scope`, `scp` hay custom theo issuer; kiểm tra chuỗi/mảng và dữ liệu mâu thuẫn.
5. **Chọn quy tắc authority:** `SCOPE_` mặc định hay whitelist permission nội bộ; không làm lộ `ROLE_` qua mapping tùy tiện.
6. **Đồng bộ cấu hình với policy:** `JwtGrantedAuthoritiesConverter`, `JwtAuthenticationConverter`, `hasAuthority`, `@PreAuthorize` và unit tests.
7. **Phân biệt 401 và 403:** token sai/thiếu với token hợp lệ nhưng thiếu quyền; dùng `insufficient_scope` theo Bearer protocol khi phù hợp.
8. **Kiểm tra quyền trên resource:** owner, tenant, membership, business state và dữ liệu thực; scope không thay logic này.
9. **Xử lý đổi quyền/thu hồi:** token TTL, opaque introspection cache, denylist/version và policy yêu cầu quyền hiện hành.
10. **Bảo vệ credential:** TLS, tránh token trong URL/log, ngăn replay và lưu trữ phù hợp với browser/mobile/backend.
11. **Kiểm thử cả đường sai:** invalid signature, wrong audience, wrong claim, unknown scope, app-only giả user, ID token đưa vào API, cross-tenant và resource ID đoán được.
12. **Theo dõi vận hành:** cảnh báo mapping mismatch, thiếu scope bất thường, token validation failure; log metadata đã lọc thay vì credential.

## 16. Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749), mục 3.3: cách yêu cầu và diễn giải scope trong OAuth 2.0.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): truyền Bearer token và phản hồi `invalid_token`, `insufficient_scope`.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token, claim `scope` và yêu cầu validation.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): kiểm tra opaque token và scope qua metadata tin cậy.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): ràng buộc token với resource/audience đích.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): quản lý quyền, token và các kiểm soát OAuth 2.0.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `JwtGrantedAuthoritiesConverter`, `SCOPE_` và cấu hình resource server.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, kiểm tra authorities ở tầng phương thức.
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): phân quyền theo đối tượng ở resource API.

**Ghi nhớ:** Mapping scope sang authority là **bước chuyển từ dữ liệu ủy quyền đã được xác minh sang ngôn ngữ policy của resource server**. Với Spring Security, scope `invoices.read` thường thành `SCOPE_invoices.read`, nhưng phép chuyển chỉ có ý nghĩa khi token đúng issuer, audience, loại và thời hạn. Sau `hasAuthority`, API vẫn phải kiểm tra principal, tenant, quyền sở hữu và tài nguyên thực tế; **scope cho phép xét một hành động, không tự cấp quyền trên mọi đối tượng**.
