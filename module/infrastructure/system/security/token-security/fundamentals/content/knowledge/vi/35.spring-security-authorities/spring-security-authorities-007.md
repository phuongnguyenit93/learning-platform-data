# Claim mapping trong Spring Security authorities

## 1. Claim mapping là gì và vì sao phải quan tâm?

Trong hệ thống OAuth 2.0/OIDC, **authorization server (AS)** phát hành **access token** và **resource server (RS)** quyết định một lời gọi API có được phép hay không. Với Spring Security, quyết định phân quyền thường dựa trên **GrantedAuthority** nằm trong đối tượng **Authentication** đã xác thực.

**Claim mapping** là quá trình chuyển các thông tin được AS cấp trong token hoặc metadata tin cậy — như **scope**, **scp**, **roles** hay **permissions** — thành một tập **GrantedAuthority** mà Spring Security có thể sử dụng trong các rule như:

~~~java
.hasAuthority("SCOPE_orders.read")
.hasAuthority("PERM_orders.approve")
.hasRole("ADMIN")
~~~

Ví dụ, AS cấp access token với claim:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "exp": 1795403600
}
~~~

Sau khi token được **xác thực hợp lệ**, Spring Security có thể ánh xạ:

~~~text
JWT scope claim: "orders.read orders.write"
                |
                v
GrantedAuthority:
  SCOPE_orders.read
  SCOPE_orders.write
~~~

Điểm quan trọng: **chuỗi có tên role hay scope trong JWT chưa tự trở thành quyền hợp lệ**. Trước khi mapping, token phải được kiểm tra đúng **chữ ký hoặc introspection**, **issuer**, **audience**, **thời hạn**, **loại token** và các điều kiện giao thức. Sau mapping, API vẫn phải kiểm tra **quyền đối với tài nguyên cụ thể**.

Bài học tập trung vào Spring Security authorities cho **resource server**, đặc biệt **JwtGrantedAuthoritiesConverter**, **JwtAuthenticationConverter**, custom claims và opaque token. Phần cuối phân biệt claim mapping này với mapping authorities trong **oauth2Login/OIDC login**.

### 1.1. Claim, scope, role, permission và authority

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Claim** | Thuộc tính do token hoặc nguồn xác thực cung cấp | iss, sub, aud, scope, roles |
| **Scope** | Phạm vi AS cấp cho client trong authorization | orders.read |
| **Role** | Nhóm trách nhiệm/chức năng theo chính sách ứng dụng hoặc tổ chức | ADMIN, SUPPORT |
| **Permission** | Quyền thao tác cụ thể lên một loại tài nguyên hoặc hành động | orders.approve |
| **GrantedAuthority** | Chuỗi authority được Spring Security đưa vào Authentication | SCOPE_orders.read, ROLE_ADMIN |
| **Business authorization** | Quyết định principal có được phép với một bản ghi cụ thể | User A chỉ đọc được đơn hàng của A |

Một **scope** không mặc nhiên là **role**; một **role** cũng không mặc nhiên cho phép mọi thao tác nghiệp vụ. Chúng cần được ánh xạ theo chính sách được định nghĩa trước, không phải nối chuỗi tùy tiện từ mọi claim.

## 2. Vị trí claim mapping trong Spring Security Resource Server

Với ứng dụng Spring Security Servlet xử lý Bearer access token:

~~~mermaid
flowchart TD
    A[HTTP Authorization: Bearer access_token] --> B[BearerTokenAuthenticationFilter]
    B --> C[AuthenticationManager]
    C --> D[JwtAuthenticationProvider]
    D --> E[JwtDecoder xác minh JWT]
    E --> F{iss, aud, signature, exp và policy hợp lệ?}
    F -- Không --> X[401 / invalid_token]
    F -- Có --> G[JwtAuthenticationConverter]
    G --> H[JwtGrantedAuthoritiesConverter / Custom mapper]
    H --> I[JwtAuthenticationToken với GrantedAuthority]
    I --> J[SecurityContext]
    J --> K[AuthorizationFilter / Method Security]
    K --> L{Có quyền?}
    L -- Không --> Y[403 / insufficient_scope hoặc denied]
    L -- Có --> M[Controller + kiểm tra quyền nghiệp vụ]
~~~

Đường đi chi tiết có thể khác theo phiên bản và cấu hình filter chain; sơ đồ nhấn mạnh **xác minh credential trước, ánh xạ quyền sau**.

Các lớp thường gặp:

| Thành phần | Trách nhiệm |
|---|---|
| **BearerTokenAuthenticationFilter** | Trích bearer token từ request và bắt đầu xác thực |
| **JwtDecoder** | Xác minh chữ ký, claims và validators theo chính sách |
| **JwtAuthenticationProvider** | Tạo kết quả Authentication bằng decoder và converter |
| **JwtAuthenticationConverter** | Chuyển Jwt đã xác thực thành JwtAuthenticationToken |
| **JwtGrantedAuthoritiesConverter** | Tạo GrantedAuthority từ scope/scp hoặc claim được cấu hình |
| **JwtAuthenticationToken** | Mang Jwt principal, authorities và tên principal |
| **AuthorizationFilter / @PreAuthorize** | Đọc authorities để quyết định quyền truy cập |
| **OpaqueTokenIntrospector** | Lấy trạng thái/claims của opaque token từ AS tin cậy, có thể tùy biến mapping |

### 2.1. Authentication khác authorization

- **Authentication:** token có hợp lệ, do issuer tin cậy phát hành, dành cho API này và chưa hết hạn hay không?
- **Claim mapping:** chuyển metadata đã được xác minh thành những authority được Spring Security hiểu.
- **Authorization:** authority có đủ cho method/route không, và người dùng có quyền trên đối tượng dữ liệu thực tế không?

Một JWT có scope **orders.read** nhưng **aud=billing-api** phải bị RS orders-api từ chối; không được mapping scope trước rồi coi là hợp lệ. Một JWT đúng aud và scope nhưng truy cập đơn hàng của người khác cũng phải bị business authorization từ chối.

## 3. Mặc định Spring Security ánh xạ scope như thế nào?

Khi dùng JWT Resource Server, **JwtGrantedAuthoritiesConverter** thường nhận diện claim **scope** hoặc **scp** theo cách Spring Security hỗ trợ. Với chuỗi scope, nó tách thành từng giá trị và thêm tiền tố **SCOPE_**.

### 3.1. Scope là chuỗi phân cách bởi khoảng trắng

~~~json
{
  "sub": "user-42",
  "scope": "orders.read orders.write"
}
~~~

Kết quả:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Một rule phù hợp:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

**Không viết hasAuthority("orders.read")** nếu converter đã thêm tiền tố SCOPE_. Tên authority cần được đối chiếu với kết quả mapping thực tế.

### 3.2. scp là danh sách

Một số AS dùng claim **scp** chứa danh sách:

~~~json
{
  "sub": "user-42",
  "scp": ["orders.read", "orders.write"]
}
~~~

Theo cấu hình thông dụng, Spring Security có thể chuyển thành cùng các authorities **SCOPE_orders.read** và **SCOPE_orders.write**.

**Không nên giả định mọi issuer đều có claim cùng tên và cùng kiểu dữ liệu**. AS khác có thể dùng scope dạng chuỗi, scp dạng mảng, permissions dạng object hoặc claim namespaced riêng. Hãy xác định hợp đồng claims của issuer, rồi cấu hình converter rõ ràng.

### 3.3. Nếu token không có scope/scp?

Trong cấu hình mặc định, thiếu claim scope phù hợp thường dẫn đến **không có authorities do scope mapping tạo ra**. Token vẫn có thể được xác thực nếu nó hợp lệ về mật mã và claims bắt buộc; sau đó endpoint yêu cầu **SCOPE_orders.read** sẽ từ chối do thiếu quyền.

Đây là hành vi **fail closed cho phân quyền scope**, không phải lý do để tự gán quyền mặc định như ROLE_USER, ROLE_ADMIN hoặc ALL.

### 3.4. Issuer cấp scope không đồng nghĩa người dùng sở hữu mọi tài nguyên

AS cấp scope cho client/ngữ cảnh ủy quyền. Resource server vẫn phải biết **chủ thể**, tenant, đối tượng và các chính sách liên quan. Phân quyền:

~~~text
Có SCOPE_orders.read
    +
Đơn hàng thuộc tenant đang được phép
    +
User hoặc client được đọc orderId cụ thể
    =
Cho phép đọc đơn hàng
~~~

Chỉ kiểm tra authority ở tầng route có thể để lại lỗ hổng **BOLA/IDOR** nếu business service không kiểm tra chủ sở hữu tài nguyên.

## 4. Phân biệt hasAuthority, hasRole và tiền tố

Spring Security sử dụng **GrantedAuthority** với giá trị chuỗi cụ thể. Việc tiền tố ảnh hưởng tới cách rule được kiểm tra:

| Expression | Giá trị authority mà rule thường đòi |
|---|---|
| **hasAuthority("SCOPE_orders.read")** | SCOPE_orders.read |
| **hasAuthority("PERM_orders.approve")** | PERM_orders.approve |
| **hasAuthority("ROLE_ADMIN")** | ROLE_ADMIN |
| **hasRole("ADMIN")** | ROLE_ADMIN (theo role prefix mặc định) |
| **hasRole("ROLE_ADMIN")** | Không nên dùng dạng này khi quy tắc hasRole tự thêm prefix |
| **hasAnyAuthority("SCOPE_a", "SCOPE_b")** | Ít nhất một authority khớp chính xác |

Chú ý: role prefix có thể được tùy biến ở một số cấu hình; ví dụ trên mô tả hành vi phổ biến với **ROLE_** mặc định. Nếu hệ thống thay default role prefix, cần cập nhật đồng nhất rule và converter.

Ví dụ:

~~~text
GrantedAuthority thực tế:
  SCOPE_orders.read

Rule:
  hasRole("orders.read")

Kết quả:
  Không khớp, vì rule thường tìm ROLE_orders.read.
~~~

Đừng đổi mọi scope thành **ROLE_** chỉ để dùng hasRole; điều đó có thể làm nhầm lẫn cấp quyền ứng dụng với quyền OAuth đã cấp cho một client.

## 5. Tùy biến claim và prefix bằng JwtGrantedAuthoritiesConverter

### 5.1. Đọc một claim tùy chỉnh

Giả sử AS đáng tin cậy phát hành token với claim **permissions**:

~~~json
{
  "iss": "https://identity.example.test",
  "aud": ["orders-api"],
  "sub": "user-42",
  "permissions": ["orders.read", "orders.approve"]
}
~~~

Có thể cấu hình converter chỉ lấy claim permissions và đặt tiền tố riêng:

~~~java
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

JwtGrantedAuthoritiesConverter permissionsConverter =
    new JwtGrantedAuthoritiesConverter();

permissionsConverter.setAuthoritiesClaimName("permissions");
permissionsConverter.setAuthorityPrefix("PERM_");
~~~

Kết quả mong muốn:

~~~text
PERM_orders.read
PERM_orders.approve
~~~

Lưu ý việc cấu hình **một JwtGrantedAuthoritiesConverter** theo permissions **thay thế nguồn claim mà converter đó đọc**, không tự động gộp với scope mặc định. Nếu ứng dụng cần **cả scope và permission**, phải thiết kế converter tổng hợp rõ ràng.

Trong những phiên bản Spring Security có setter cấu hình cách tách authorities claim kiểu chuỗi, có thể tùy biến delimiter. Tuy nhiên, cấu trúc claim **mảng string** thường ít mơ hồ hơn một chuỗi delimiter tùy ý. Kiểm tra API chính xác của phiên bản đang sử dụng.

### 5.2. Áp dụng JwtAuthenticationConverter trong SecurityFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter permissions =
            new JwtGrantedAuthoritiesConverter();

        permissions.setAuthoritiesClaimName("permissions");
        permissions.setAuthorityPrefix("PERM_");

        JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(permissions);
        return converter;
    }

    @Bean
    SecurityFilterChain apiChain(
            HttpSecurity http,
            JwtAuthenticationConverter jwtConverter
    ) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/orders/approve/**")
                    .hasAuthority("PERM_orders.approve")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt.jwtAuthenticationConverter(jwtConverter))
            );

        return http.build();
    }
}
~~~

Đoạn ví dụ chỉ nhấn mạnh claim mapping. Một ứng dụng hoàn chỉnh còn phải cấu hình **JwtDecoder, issuer/audience validators, HTTPS, CSRF/session policy và coverage của các SecurityFilterChain**. Ví dụ không tự ngầm khẳng định các phần đó đã được thiết lập đúng.

### 5.3. Quy tắc nguồn claim phải rõ ràng

Trước khi dùng một claim để cấp quyền, xác định:

1. Claim đó được **AS hoặc identity authority đáng tin cậy** tạo từ chính sách nào?
2. Đó là quyền dành cho **resource server hiện tại** hay quyền của một ứng dụng khác?
3. Kiểu dữ liệu hợp lệ là chuỗi, danh sách hay map?
4. Giá trị có nằm trong **allowlist** mà API chấp nhận không?
5. Claim có thể do **người dùng tự sửa** ở hồ sơ không?
6. Khi issuer/tenant thay đổi, cách hiểu claim có thay đổi không?

Claim có tên **roles** nhưng do người dùng chỉnh sửa trong trang profile **không phải một nguồn phân quyền đáng tin cậy**. Cần đặc tả rõ provenance của dữ liệu trước khi dùng nó cấp quyền.

## 6. Gộp scope và permission bằng converter có kiểm soát

Nhiều API cần đồng thời:

- Scope được AS ủy quyền cho client, ví dụ **orders.read**.
- Permission ứng dụng, ví dụ **orders.approve**, chỉ cấp từ nguồn đáng tin cậy.

Ví dụ cấu hình Java minh họa hai namespace:

~~~java
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Set;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

public class AuthorityMappingFactory {

    public static JwtAuthenticationConverter converter() {
        JwtGrantedAuthoritiesConverter scopes =
            new JwtGrantedAuthoritiesConverter();

        Set<String> allowedPermissions =
            Set.of("orders.read", "orders.approve", "orders.cancel");

        Converter<Jwt, Collection<GrantedAuthority>> mapping = jwt -> {
            Set<GrantedAuthority> result =
                new LinkedHashSet<>(scopes.convert(jwt));

            // Defense in depth: converter không thay thế JwtDecoder validator.
            if (!"https://identity.example.test"
                    .equals(jwt.getClaimAsString("iss"))
                    || !jwt.getAudience().contains("orders-api")) {
                return result;
            }

            Object raw = jwt.getClaims().get("permissions");
            if (raw instanceof Collection<?> permissions) {
                for (Object value : permissions) {
                    if (value instanceof String permission
                            && allowedPermissions.contains(permission)) {
                        result.add(new SimpleGrantedAuthority(
                            "PERM_" + permission
                        ));
                    }
                }
            }
            return result;
        };

        JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(mapping);
        return converter;
    }
}
~~~

Ví dụ dùng cú pháp Java hỗ trợ pattern matching cho instanceof; cần chọn phiên bản Java tương thích. Có thể trả về quyền **scope mặc định** khi claim permission không hợp lệ, nhưng **JwtDecoder phải từ chối token sai issuer/audience trước khi converter được gọi**. Điều kiện trong converter chỉ là *defense in depth*, **không phải cơ chế xác minh token**.

Nếu chính sách ứng dụng yêu cầu claim permissions **luôn đúng schema** thì thay vì lặng lẽ bỏ giá trị sai, hãy từ chối token trong validator hoặc tầng xác thực theo hợp đồng đã thiết kế. Ví dụ trên chọn cách không cấp **PERM_** cho giá trị sai dạng, với mục tiêu tránh privilege escalation trong mapping.

### 6.1. Vì sao phải kiểm tra kiểu dữ liệu?

Một token có thể chứa:

~~~json
{
  "permissions": [
    "orders.approve",
    123,
    {"name": "ADMIN"}
  ]
}
~~~

Mapper không nên gọi **toString()** cho mọi phần tử rồi coi kết quả là authority. Chỉ những giá trị **String đã được định nghĩa** mới nên được cấp quyền, và claim có cấu trúc khác thường cần được kiểm tra theo schema riêng.

### 6.2. Tránh mất scope khi dùng custom mapping

Nếu thay converter mặc định bằng converter chỉ đọc permissions, endpoint vốn yêu cầu **SCOPE_orders.read** có thể trả 403 dù JWT có scope. Điều này không nhất thiết là lỗi token; có thể **converter đã làm mất nguồn scope mặc định**. Giải pháp là gộp cả hai nguồn trong converter composite như ví dụ, hoặc thiết kế các rules chỉ dùng một namespace được chuẩn hóa.

### 6.3. Quyền không được cấp từ tham số request

Request:

~~~http
GET /api/orders/42?role=ADMIN HTTP/1.1
Authorization: Bearer <ACCESS_TOKEN>
~~~

Tham số **role=ADMIN** là dữ liệu do caller điều khiển, không được chuyển thành GrantedAuthority. Tương tự, header X-Role, X-Tenant hoặc JSON body không là nguồn cấp quyền nếu không có ranh giới xác thực đặc biệt, rõ ràng và được kiểm soát.

## 7. Mapping role từ claims lồng nhau

Một số identity providers cấp roles dưới claims có cấu trúc thay vì ở scope. Ví dụ minh họa:

~~~json
{
  "iss": "https://identity.example.test/tenant-a",
  "aud": ["orders-api"],
  "sub": "user-42",
  "realm_access": {
    "roles": ["offline_access", "viewer"]
  },
  "resource_access": {
    "orders-api": {
      "roles": ["viewer", "operator"]
    },
    "billing-api": {
      "roles": ["billing-admin"]
    }
  }
}
~~~

Các tên **realm_access/resource_access** minh họa cấu trúc gặp ở một số hệ thống như Keycloak; **đây không phải claims bắt buộc theo mọi JWT/OAuth token**.

Nếu API orders-api chỉ chấp nhận roles trong **resource_access.orders-api.roles**, việc đọc tất cả roles của mọi ứng dụng có thể cấp sai quyền. Đặc biệt **billing-admin** không được biến thành quyền quản trị Orders.

### 7.1. Pseudocode kiểm tra theo ngữ cảnh ứng dụng

~~~text
jwt = JWT đã được xác minh theo issuer, audience, thời gian, type

resourceAccess = jwt.claim("resource_access")
appRoles = resourceAccess["orders-api"]["roles"]

for role in appRoles:
    if role là string và thuộc allowlist {"viewer", "operator"}:
        grant "ROLE_ORDERS_" + uppercase(role)

Result:
    ROLE_ORDERS_VIEWER
    ROLE_ORDERS_OPERATOR
~~~

Cần kiểm tra kiểu dữ liệu ở **mọi tầng** của object và có chính sách rõ khi claim thiếu. Không đọc role từ **billing-api**, không nối mọi realm role với tiền tố ROLE_ và không biến bất kỳ chuỗi nào thành **ROLE_ADMIN**.

### 7.2. Phân quyền theo resource/tenant

Ngay cả khi token có **ROLE_ORDERS_OPERATOR**, nếu yêu cầu thay đổi đơn hàng thuộc tenant khác thì business policy vẫn phải từ chối. Hãy dùng:

~~~text
Đúng issuer
  + Đúng audience
  + ROLE_ORDERS_OPERATOR được cấp từ nguồn tin cậy
  + Người dùng có quyền với tenant/order cụ thể
  = Cho phép thao tác theo policy
~~~

Không nên coi một role toàn hệ thống là quyền xuyên tenant nếu chính sách không cho phép.

## 8. Principal claim name và authorities là hai việc khác nhau

Ngoài chuyển claims thành authorities, **JwtAuthenticationConverter** còn có thể chọn một claim để đặt tên principal.

Ví dụ:

~~~java
JwtAuthenticationConverter converter =
    new JwtAuthenticationConverter();

converter.setPrincipalClaimName("sub");
~~~

Mặc định thường dùng **sub**. Có thể thay bằng claim khác nếu hệ thống có hợp đồng định danh rõ ràng, ví dụ một account ID ổn định. Tuy nhiên:

- **preferred_username** và email có thể thay đổi, trùng giữa các issuers hoặc bị người dùng kiểm soát.
- **sub** thường chỉ có ý nghĩa duy nhất **trong phạm vi issuer**, không phải trên toàn Internet.
- **Principal name không tự tạo GrantedAuthority**. Một tên principal chứa chuỗi admin không có nghĩa principal có ROLE_ADMIN.
- Nếu có nhiều issuer, nên ánh xạ danh tính bền vững theo cặp **(iss, sub)** hoặc một internal ID tin cậy sau khi xác minh, thay vì dùng sub đơn lẻ.

Thay principal claim name để làm log dễ đọc **không thay thế** mô hình định danh và authorization.
## 9. Xác minh JWT trước khi áp dụng claim mapping

**Claim mapping không phải JWT validation.** Một developer có thể viết converter rất chặt nhưng vẫn mắc lỗ hổng nghiêm trọng nếu decoder chấp nhận token sai issuer, audience hoặc token type.

Thứ tự được khuyến nghị:

1. Tìm cấu hình **issuer đáng tin cậy** và tập khóa/algorithm được phép.
2. Xác minh chữ ký token và **iss** theo issuer đã cấu hình.
3. Kiểm tra **exp, nbf**, clock skew phù hợp, các điều kiện profile và loại token.
4. Kiểm tra **aud** chứa resource server hiện tại.
5. Nếu token là sender-constrained, thực hiện kiểm tra bằng chứng sở hữu khóa/chứng chỉ theo DPoP/mTLS qua thành phần hỗ trợ riêng.
6. Chỉ khi token được chấp nhận, chuyển claims đáng tin cậy thành **GrantedAuthority**.
7. Cuối cùng áp dụng route, method và **business authorization**.

~~~mermaid
flowchart TD
    A[Nhận access token] --> B[Decoder kiểm tra signature, issuer, exp, nbf]
    B --> C{Hợp lệ?}
    C -- Không --> X[401]
    C -- Có --> D[Audience, token type, binding nếu cần]
    D --> E{Đúng API và loại token?}
    E -- Không --> X
    E -- Có --> F[Claim mapping theo chính sách issuer/tenant]
    F --> G[Authentication với GrantedAuthority]
    G --> H[HTTP / Method authorization]
    H --> I{Quyền đủ?}
    I -- Không --> Y[403]
    I -- Có --> J[Business authorization từng đối tượng]
~~~

### 9.1. Cấu hình audience validator

Trong Spring Security, **issuer-uri** thường giúp tạo decoder và xác minh issuer theo cơ chế hỗ trợ. Nhưng **audience dành cho ứng dụng** không nên được giả định tự kiểm tra trong mọi cấu hình. Có thể khai báo decoder với validator riêng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Bean
JwtDecoder jwtDecoder() {
    String issuer = "https://identity.example.test";
    String jwksUri = "https://identity.example.test/oauth2/jwks";

    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withJwkSetUri(jwksUri).build();

    OAuth2TokenValidator<Jwt> issuerAndTime =
        JwtValidators.createDefaultWithIssuer(issuer);

    OAuth2TokenValidator<Jwt> audience = jwt ->
        jwt.getAudience().contains("orders-api")
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token", "Audience is not accepted", null
                )
            );

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
            issuerAndTime, audience
        )
    );
    return decoder;
}
~~~

Đây là ví dụ tối giản. Cần thêm **chính sách thuật toán ký, token type, claims bắt buộc, tenant hoặc client binding** theo hệ thống. Không lấy JWKS URL từ **iss, jku, x5u** chưa xác thực mà gọi Internet tùy ý; chỉ sử dụng địa chỉ JWKS của issuer được phép.

### 9.2. Tại sao không dùng ID token làm nguồn authorities cho API?

**OIDC ID token** chứng minh thông tin về sự kiện xác thực cho client và thường có **aud là client_id**, không phải API. Nếu API chỉ kiểm tra chữ ký JWT rồi map một claim roles từ ID token thành ROLE_ADMIN, nó có thể tạo **token confusion**: loại token dành cho login bị dùng như token gọi API.

Resource server nên chỉ nhận **access token hợp lệ** dành cho audience của mình và áp dụng token profile/chính sách phân biệt loại token. Dù ID token chứa claim roles, điều đó **không tự cho phép** đưa nó vào API như access token.

## 10. Claim mapping với opaque token và introspection

Với **opaque access token**, resource server không trực tiếp giải mã JWT. Thay vào đó, một **OpaqueTokenIntrospector** hỏi AS qua endpoint tin cậy để biết token có **active** không và lấy các thuộc tính được trả về. Provider sử dụng principal/authorities để tạo **BearerTokenAuthentication**.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant RS as Resource Server
    participant AS as Authorization Server
    C->>RS: Authorization: Bearer OPAQUE
    RS->>AS: Introspection qua kênh tin cậy
    AS-->>RS: active, scope, sub, metadata nếu có
    RS->>RS: Chấp nhận theo AS/resource policy
    RS->>RS: Mapping attributes thành authorities
    RS->>RS: Authorization theo route và đối tượng
    RS-->>C: Kết quả
~~~

Bản thân claim mapping cho opaque token vẫn cần quy tắc như JWT: **chỉ dùng metadata do AS tin cậy cung cấp**, kiểm tra đúng resource/audience, không tin cấu trúc claim tùy ý. **active=true** không đủ để cấp mọi quyền.

### 10.1. Tùy biến OpaqueTokenIntrospector

Một cách mở rộng là bọc **delegate introspector** đã được cấu hình xác thực với AS, sau đó thêm authorities được cho phép. Pseudocode gần Java:

~~~java
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Set;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

public final class PermissionMappingIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;

    public PermissionMappingIntrospector(
            OpaqueTokenIntrospector delegate
    ) {
        this.delegate = delegate;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        // Delegate đã kiểm tra response introspection từ AS tin cậy.
        OAuth2AuthenticatedPrincipal principal =
            delegate.introspect(token);

        Set<GrantedAuthority> authorities =
            new LinkedHashSet<>(principal.getAuthorities());

        // Cần ràng buộc resource/issuer bằng policy bên ngoài
        // khi AS không trả metadata tương ứng.
        Object raw = principal.getAttribute("permissions");

        if (raw instanceof Collection<?> permissions) {
            for (Object item : permissions) {
                if ("orders.approve".equals(item)) {
                    authorities.add(
                        new SimpleGrantedAuthority(
                            "PERM_orders.approve"
                        )
                    );
                }
            }
        }

        return new DefaultOAuth2AuthenticatedPrincipal(
            principal.getName(),
            principal.getAttributes(),
            authorities
        );
    }
}
~~~

**Không nên sao chép đoạn này thành production mà thiếu phần chọn AS/issuer và audience policy.** Lớp wrapper chỉ map **metadata đã được delegate chấp nhận**; nó không chứng minh endpoint introspection đã đúng, không xác thực HTTPS thay delegate và không tự kiểm tra token type.

Nếu nội dung introspection không có claim permissions, không cấp PERM_orders.approve. Nếu quy tắc dữ liệu yêu cầu claim này, hệ thống nên từ chối theo policy thay vì tự gán quyền.

### 10.2. Tránh rò rỉ quyền qua cache introspection

Nếu cache kết quả introspection hoặc principal/authorities, key cache phải bao gồm **AS tin cậy và token digest/định danh phù hợp**, cùng những yếu tố ngữ cảnh cần phân biệt. Không dùng một cache toàn cục nhận hai token cùng chuỗi từ AS khác nhau rồi trả quyền của AS thứ nhất cho AS thứ hai.

TTL cache còn ảnh hưởng tới **revocation**: nếu token đã bị thu hồi ở AS nhưng response active và authorities cũ vẫn nằm trong cache, RS có thể tiếp tục chấp nhận nó cho đến khi cache hết hạn.

## 11. oauth2Login/OIDC authorities khác Resource Server

Spring Security hỗ trợ hai trường hợp dễ nhầm:

1. **OAuth2 Resource Server:** API nhận **access token** trong Authorization header; xác thực JWT/opaque token và tạo Authentication để bảo vệ API.
2. **OAuth2 Login/OpenID Connect Login:** ứng dụng web chuyển hướng người dùng tới IdP và tạo **phiên đăng nhập cục bộ** sau callback; authorities có thể liên quan tới **OAuth2UserAuthority**, **OidcUserAuthority**, thông tin UserInfo và cơ chế **GrantedAuthoritiesMapper** hoặc custom user service.

Hai luồng có thể cùng tồn tại trong một ứng dụng nhưng không tự dùng chung ý nghĩa của claims.

| Trường hợp | Dữ liệu đầu vào | Điểm mở rộng thường gặp |
|---|---|---|
| JWT Resource Server | JWT access token đã xác thực | JwtGrantedAuthoritiesConverter, JwtAuthenticationConverter |
| Opaque Resource Server | Introspection metadata từ AS | OpaqueTokenIntrospector wrapper/custom authorities |
| OAuth2 Login | OAuth2 user attributes từ IdP | GrantedAuthoritiesMapper, OAuth2UserService |
| OIDC Login | ID token + UserInfo theo OIDC | GrantedAuthoritiesMapper, OidcUserService |

Khi ứng dụng dùng **OIDC login để tạo session cookie**, một role được gắn cho **principal phiên web** không có nghĩa resource server ở dịch vụ khác tự động có cùng authority. API nhận access token cần có chính sách xác thực token của riêng nó.

Không đưa **OIDC ID token** đến resource server thay cho access token chỉ để lấy role claim tiện lợi.

## 12. Áp dụng authorities trong HTTP và method authorization

### 12.1. HTTP authorization với scope và permission

~~~java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        JwtAuthenticationConverter authorityConverter
) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(
                HttpMethod.GET, "/api/orders/**"
            ).hasAuthority("SCOPE_orders.read")

            .requestMatchers(
                HttpMethod.POST, "/api/orders/*/approve"
            ).hasAuthority("PERM_orders.approve")

            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt ->
            jwt.jwtAuthenticationConverter(authorityConverter)
        ));

    return http.build();
}
~~~

Đây là cấu hình rút gọn; cần import, decoder, HTTPS, session/CSRF policy phù hợp. Hãy kiểm tra **request matcher** cho từng đường dẫn và method thực tế; nếu một rule rộng đứng trước rule hẹp, ứng dụng có thể cho quyền rộng ngoài ý muốn.

### 12.2. Method security

Trong ứng dụng dùng **@EnableMethodSecurity**, có thể bảo vệ service:

~~~java
@PreAuthorize("hasAuthority('PERM_orders.approve')")
public void approveOrder(
        String orderId,
        Authentication authentication
) {
    // Vẫn phải xác nhận orderId thuộc tenant/phạm vi
    // mà principal này có quyền phê duyệt.
    orderPolicy.requireCanApprove(authentication, orderId);
    orderRepository.approve(orderId);
}
~~~

Nếu chỉ dựa vào **@PreAuthorize** để kiểm tra quyền chuỗi mà không kiểm tra orderId, API có thể mắc lỗi truy cập đối tượng trái phép. Với hành động nhạy cảm, có thể cần **step-up authentication**, kiểm tra trạng thái tài khoản và phân tách nhiệm vụ.

### 12.3. Quyền tổng hợp cần điều kiện nào?

Ví dụ: endpoint phê duyệt đơn hàng cần **cả scope và permission**:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.write') " +
    "and hasAuthority('PERM_orders.approve')"
)
public void approveOrder(String id) {
    // Tiếp tục kiểm tra tenant/owner/business policy.
}
~~~

Ở đây scope thể hiện quyền client được ủy quyền, permission thể hiện khả năng nghiệp vụ của principal. Việc ghép **AND** hay **OR** phải do chính sách cấp quyền định nghĩa, không phải do người lập trình tiện tay chọn.

## 13. Multi-issuer và multi-tenant: mapping phải có ngữ cảnh

Một resource server có thể nhận token từ hai issuer:

~~~text
Issuer A: https://identity.company.example.test
Issuer B: https://partner-login.example.test

Cả hai đều có claim:
  roles = ["admin"]

Nhưng "admin" của issuer A và issuer B không nhất thiết
có cùng ý nghĩa hoặc quyền truy cập orders-api.
~~~

Nếu converter dùng mọi **roles** thành **ROLE_ADMIN** mà không kiểm tra issuer và audience, đối tác có thể nhận quyền quản trị nội bộ ngoài chủ đích.

Các biện pháp:

- **Allowlist issuer** được cấu hình từ nguồn tin cậy; lựa chọn decoder/manager theo issuer đã được cho phép, rồi xác minh chữ ký và iss chính xác.
- Cấu hình **audience/tenant** riêng cho mỗi API/nguồn phát hành; không để một token dành cho ứng dụng khác được quyền dùng chéo.
- Với từng issuer, quy định rõ **claim path, role prefix và allowlist quyền**. Có thể xây converter riêng theo **AuthenticationManager/issuer** nếu khác nhau.
- Đừng dùng **kid** làm định danh khóa toàn cục; cache JWKS/decoder theo issuer.
- Định danh người dùng ngoài hệ thống theo **(iss, sub)** khi liên kết tài khoản.
- Đối với roles tenant-specific, kiểm tra token thực sự chứa **tenant đáng tin cậy**, rồi kiểm tra resource. Không tin tenantId từ query/header để cấp quyền cao hơn.

### 13.1. Phân biệt issuer và nguồn quyền

Token đến từ issuer tin cậy **không tự chứng minh mọi claim có thể dùng làm quyền**. Một số claims như name, nickname, email, locale hoặc profile metadata có thể do người dùng chỉnh sửa. Không ánh xạ các trường ấy thành role quản trị.

Nguồn claims có thể cần kiểm tra **authorization policy tại AS**, ví dụ permissions chỉ được gán bởi role service nội bộ đáng tin cậy. Việc JWT được ký chỉ chứng minh issuer đã ký payload; nếu issuer sao chép dữ liệu role không tin cậy từ request, resource server vẫn có thể bị cấp quyền sai.

## 14. Sai sót claim mapping thường gặp

| Sai sót | Hậu quả | Khắc phục |
|---|---|---|
| Chỉ kiểm tra JWT signature rồi map roles | Token sai issuer/aud có thể được cấp quyền | Decoder kiểm tra iss, aud, exp, token type trước mapping |
| Dùng hasRole("orders.read") với SCOPE_orders.read | 403 do prefix không khớp | Dùng hasAuthority đúng tên đã map |
| Gắn ROLE_ADMIN cho mọi giá trị roles="admin" | Role từ tenant/issuer khác trở thành admin nội bộ | Allowlist issuer, claim path, role và phạm vi API |
| Coi email/username là authority | Tài khoản có thể tự thay profile để nâng quyền | Chỉ dùng claims quyền có nguồn tin cậy |
| Map mọi claim thành GrantedAuthority | Claim phụ bị diễn giải thành quyền trái ý | Allowlist claim names, values, types và prefix |
| Thay converter mặc định chỉ đọc permissions | Scope bị mất, API trả 403 | Tổng hợp scope + permissions có chủ đích |
| Dùng dữ liệu JSON request làm roles | Privilege escalation | Chỉ cấp quyền từ Authentication đã xác thực |
| Dùng OIDC ID token thay access token | Token substitution/cross-JWT confusion | Resource server đòi access token đúng aud/type |
| Tin opaque introspection active=true là đủ | Token từ sai AS/resource được cấp quyền | Kiểm tra trusted endpoint, audience và policy |
| Không kiểm tra kiểu claim lồng nhau | Exception/logic bất định, cấp quyền sai | Validate schema và fail closed |
| Gộp ROLE_ADMIN với SCOPE_admin tùy tiện | Nhầm vai trò người dùng và scope ủy quyền của client | Dùng namespace và quy tắc riêng |
| Chỉ kiểm tra route scope | Người dùng đọc/ghi dữ liệu tenant khác | Business authorization cấp đối tượng |
| Không phân biệt issuer khi cùng sub | Trộn tài khoản từ nhiều IdP | Dùng (iss, sub) hoặc internal principal tin cậy |
| Cache authorities không gắn token/issuer | Quyền cũ hoặc quyền của AS khác bị dùng lại | Cache key và TTL theo AS/token/policy |
| Tự fallback cấp ROLE_USER khi claim quyền sai | Token không đủ claims vẫn được cấp quyền | Chính sách rõ: từ chối hoặc authorities rỗng |
| Không kiểm thử validator thật | Unit test mapper PASS trong khi decoder sai | Có integration test signed JWT/introspection |

## 15. Kiểm thử claim mapping

### 15.1. Unit test converter

Tách converter thành một component có thể kiểm tra độc lập. Ví dụ đơn giản cho **scope default**:

~~~java
import java.time.Instant;
import java.util.Collection;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import static org.assertj.core.api.Assertions.assertThat;

class ScopeMappingTest {

    @Test
    void mapsScopeToGrantedAuthorities() {
        Jwt jwt = Jwt.withTokenValue("unit-test-placeholder")
            .header("alg", "RS256")
            .claim("iss", "https://identity.example.test")
            .claim("aud", List.of("orders-api"))
            .claim("sub", "user-42")
            .claim("scope", "orders.read orders.write")
            .issuedAt(Instant.now())
            .expiresAt(Instant.now().plusSeconds(300))
            .build();

        JwtGrantedAuthoritiesConverter converter =
            new JwtGrantedAuthoritiesConverter();

        Collection<GrantedAuthority> authorities =
            converter.convert(jwt);

        assertThat(authorities)
            .extracting(GrantedAuthority::getAuthority)
            .containsExactlyInAnyOrder(
                "SCOPE_orders.read", "SCOPE_orders.write"
            );
    }
}
~~~

**Giới hạn test này:** Jwt.withTokenValue tạo một object Jwt test; nó **không xác minh chữ ký hoặc audience**. Unit test này chỉ chứng minh converter đọc scope đúng. Mọi bất biến của JwtDecoder phải được kiểm thử riêng.

### 15.2. Test custom permission mapping

Cần đủ các trường hợp:

1. **Claim hợp lệ**: permissions=["orders.approve"] → có PERM_orders.approve.
2. **Claim thiếu**: không có permissions → không có permission bổ sung.
3. **Claim sai kiểu**: permissions là số hoặc object → không cấp quyền.
4. **Value ngoài allowlist**: permissions=["admin:all"] → không cấp ROLE_ADMIN hay quyền rộng.
5. **Scope và permission cùng tồn tại** → cả SCOPE_ và PERM_ đều có.
6. **Khác issuer/audience** → decoder từ chối; không chỉ dựa vào converter.
7. **Role lồng nhau của ứng dụng khác** → không được gán authority cho orders-api.
8. **Hai tokens cùng sub nhưng khác issuer** → danh tính và quyền không bị trộn.
9. **Principal claim name thay đổi** → authorities không bị ảnh hưởng ngoài ý muốn.
10. **Cache/thu hồi** → authorities không tồn tại lâu hơn hiệu lực token/policy.

### 15.3. MockMvc test và integration test không thay thế nhau

Spring Security Test hỗ trợ tạo Authentication mô phỏng bằng **jwt()**. Cách này tiện để kiểm tra route và method authorization, nhưng **không mặc nhiên thực thi JwtDecoder thật** và có thể bỏ qua converter production nếu trực tiếp cung cấp authorities giả.

Ví dụ:

~~~java
mockMvc.perform(get("/api/orders/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )))
    .andExpect(status().isOk());
~~~

Test này chứng minh rule hoạt động với SCOPE_orders.read, **chưa chứng minh JWT thật từ issuer được parse/map đúng**.

Nên có:

- **Unit test converter**: mọi dạng claim và permission value.
- **Web authorization test**: route/method phản hồi 401 hoặc 403 khi quyền thiếu.
- **Integration test decoder/filter**: gửi Authorization: Bearer với **JWT được ký bằng khóa kiểm thử**, JWKS tin cậy và token có iss/aud/exp khác nhau. Xác minh converter được gọi sau khi JWT hợp lệ.
- **Opaque introspection test**: AS test trả active/scopes/permissions; xác nhận đúng source và cache/thu hồi.
- **Multi-issuer test**: cùng role string nhưng issuer/tenant khác; xác nhận không cấp quyền sai.

### 15.4. Ma trận HTTP expected behavior

| Request | Điều kiện | Kỳ vọng |
|---|---|---|
| GET /api/orders/42 | Access token hợp lệ, đúng aud, có SCOPE_orders.read, đúng owner | Được phép |
| GET /api/orders/42 | Không token | 401 trên protected route |
| GET /api/orders/42 | JWT signature sai | 401 |
| GET /api/orders/42 | JWT issuer sai | 401 |
| GET /api/orders/42 | JWT aud không có orders-api | 401 |
| GET /api/orders/42 | JWT hết hạn | 401 |
| GET /api/orders/42 | Token đúng nhưng không có scope cần | 403 |
| POST /api/orders/42/approve | Có PERM_orders.approve, thiếu scope yêu cầu nếu policy cần cả hai | 403 |
| POST /api/orders/42/approve | Có đúng scope, permission và quyền trên order | Được phép |
| GET /api/orders/42 | Có scope nhưng khác tenant/owner | Business authorization từ chối |
| GET /api/orders/42 | ID token gửi thay access token | Bị từ chối theo token type/aud |
| POST /api/orders/42/approve | permissions sai kiểu hoặc ngoài allowlist | Không được cấp PERM_orders.approve |
| POST /api/orders/42/approve | Role từ issuer lạ hoặc app khác | Không được cấp quyền local |
| POST /api/orders/42/approve | Opaque token inactive | 401 |

## 16. Giám sát và vận hành

Nên quan sát các sự kiện theo nguyên nhân, thay vì chỉ thấy “403”:

- **authentication_invalid_token**: chữ ký/issuer/expiration/token type sai.
- **authentication_audience_mismatch**: access token không dành cho API.
- **authority_claim_missing**: nguồn claim được yêu cầu nhưng không tồn tại.
- **authority_claim_schema_invalid**: cấu trúc claim sai hợp đồng.
- **authority_mapping_denied**: role/permission nằm ngoài allowlist.
- **authorization_scope_denied**: thiếu SCOPE_.
- **authorization_permission_denied**: thiếu PERM_/ROLE_.
- **business_resource_denied**: claim hợp lệ nhưng principal không có quyền trên object cụ thể.
- **opaque_introspection_unavailable**: AS hoặc kênh introspection không khả dụng.

Ghi request ID, issuer **đã xác thực**, audience, policy ID, endpoint, authority cần có và loại lỗi. Không ghi **raw access token, refresh token, Authorization header, private keys hoặc toàn bộ JWT claims nhạy cảm**. Nếu cần correlation token, dùng fingerprint/digest không thể dùng làm credential theo chính sách lưu trữ và bảo mật.

### 16.1. Khi API trả 401

Kiểm tra decoder/introspection trước khi quan tâm mapper:

1. Token đúng **access token** hay client gửi nhầm ID token?
2. **iss** và nguồn khóa/JWKS có đúng không?
3. **aud** có API hiện tại hay không?
4. Token còn hạn và đúng thuật toán không?
5. Proxy có chuyển Authorization header không?

### 16.2. Khi API trả 403

Kiểm tra:

1. Authentication có những **GrantedAuthority** nào? Chỉ log tên authority đã được phê duyệt nếu cần.
2. JWT dùng **scope**, **scp**, **permissions** hay claim lồng nhau?
3. Converter có giữ scope mặc định khi thêm permissions không?
4. Rule dùng **hasRole** hay **hasAuthority**, tiền tố có khớp không?
5. Route matcher và method security có rule nào ghi đè/đòi thêm quyền không?
6. Business service có từ chối theo tenant, owner hoặc dữ liệu thực tế không?

### 16.3. Thay đổi policy mapping

Khi chuyển từ scope sang permission hoặc thay tên claim, cần:

- Phối hợp version giữa **AS phát hành claims** và **RS chuyển authorities**.
- Định nghĩa thời gian chuyển tiếp cho access token cũ, nhưng không mở rộng quyền không kiểm soát.
- Kiểm tra nguồn claim trước khi thêm prefix ROLE_ hoặc PERM_.
- Kiểm thử contract của mọi issuer/tenant và API có liên quan.
- Theo dõi sự thay đổi 401/403 và sự kiện quyền bất thường sau triển khai.

## 17. Tình huống tổng hợp: phê duyệt đơn hàng

Giả sử Orders API cho phép đọc đơn khi có scope **orders.read** và cho phép phê duyệt khi đồng thời:

- Client đã được cấp **orders.write**.
- Principal có permission **orders.approve**.
- Đơn hàng thuộc tenant được phép và đang ở trạng thái có thể phê duyệt.

Access token hợp lệ:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "permissions": ["orders.approve"],
  "tenant_id": "tenant-a",
  "exp": 1795403600
}
~~~

Sau mapping:

~~~text
Authentication principal: (iss, sub)
GrantedAuthority:
  SCOPE_orders.read
  SCOPE_orders.write
  PERM_orders.approve
~~~

Quyết định cuối:

~~~mermaid
flowchart TD
    A[POST /api/orders/42/approve] --> B{Token hợp lệ, đúng iss/aud?}
    B -- Không --> X[401]
    B -- Có --> C{Có SCOPE_orders.write?}
    C -- Không --> Y[403]
    C -- Có --> D{Có PERM_orders.approve?}
    D -- Không --> Y
    D -- Có --> E{Order 42 thuộc tenant và policy cho phép?}
    E -- Không --> Y
    E -- Có --> F[Thực hiện phê duyệt]
~~~

Nếu kẻ tấn công tạo JWT với **permissions=["orders.approve"]** nhưng ký bằng khóa không tin cậy, decoder phải từ chối **trước khi mapping**. Nếu token được issuer tin cậy ký nhưng **aud=billing-api**, Orders API cũng phải từ chối. Nếu token đúng và có đủ authorities nhưng order 42 thuộc tenant khác, service phải từ chối.

Bốn tầng bảo vệ — **token validation, claim mapping, authorization rules và business policy** — không được thay thế cho nhau.

## 18. Câu hỏi tự kiểm tra

1. Claim mapping khác xác thực chữ ký JWT và authorization nghiệp vụ ở điểm nào?
2. Vì sao claim **scope="orders.read orders.write"** thường tạo **SCOPE_orders.read** và **SCOPE_orders.write**?
3. **hasRole("ADMIN")** khác **hasAuthority("ROLE_ADMIN")** ra sao với prefix mặc định?
4. Nếu tùy biến JwtGrantedAuthoritiesConverter đọc **permissions**, điều gì có thể xảy ra với scopes mặc định?
5. Làm thế nào gộp cả **SCOPE_** và **PERM_** nhưng không cấp quyền cho giá trị ngoài allowlist?
6. Vì sao JWT từ issuer lạ chứa roles=["admin"] không được cấp ROLE_ADMIN?
7. Tại sao không thể coi **sub** duy nhất toàn hệ thống khi có nhiều issuer?
8. Sự khác nhau giữa **oauth2ResourceServer().jwt()** và **oauth2Login()** khi tạo authorities là gì?
9. Nếu opaque introspection trả active=true, resource server còn phải kiểm tra gì?
10. Vì sao ID token hợp lệ không mặc nhiên dùng được làm access token tại API?
11. Khi permissions có kiểu object thay vì mảng string, mapper nên xử lý thế nào?
12. Vì sao test **jwt()** của MockMvc không chứng minh JwtDecoder production đã hoạt động đúng?
13. Trong mô hình nhiều tenant, tại sao đã có SCOPE_orders.read vẫn cần kiểm tra order owner/tenant?
14. Khi đổi tên claim từ roles sang permissions, phải kiểm thử gì để không mất quyền hợp lệ hoặc cấp quyền mới ngoài ý muốn?
15. DPoP/mTLS hoặc cơ chế revocation liên quan tới claim mapping ở đâu, và vì sao authorities không tự chống token replay?

**Ghi nhớ:** Trong Spring Security, **claim mapping** chuyển **các claims đã được xác thực và được phép tin cậy** thành **GrantedAuthority**. Cấu hình mặc định thường tạo **SCOPE_** từ **scope/scp**; các role/permission tùy chỉnh cần **JwtGrantedAuthoritiesConverter, JwtAuthenticationConverter** hoặc mapper tương đương cho opaque token. Kiểm tra **issuer, audience, thời hạn, loại token, nguồn quyền, tenant và phân quyền theo tài nguyên** luôn phải được thiết kế độc lập, không được giao toàn bộ cho converter.

## Tài liệu tham khảo

- **Spring Security Reference — OAuth 2.0 Resource Server JWT:** xác minh JWT và ánh xạ authorities.
- **Spring Security API — JwtGrantedAuthoritiesConverter:** nguồn claim, tiền tố và chuyển claims thành GrantedAuthority.
- **Spring Security API — JwtAuthenticationConverter và JwtAuthenticationToken:** principal, authorities và JWT authentication.
- **Spring Security Reference — OAuth 2.0 Resource Server Opaque Tokens:** introspection và chuyển metadata thành authorities.
- **Spring Security Reference — OAuth2 Login / OpenID Connect Login:** OAuth2UserAuthority, OidcUserAuthority, GrantedAuthoritiesMapper và OidcUserService.
- **Spring Security Reference — Authorize HTTP Requests / Method Security:** hasAuthority, hasRole, @PreAuthorize và kiểm tra quyền.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** scope, client, authorization và access token.
- **RFC 6750 — Bearer Token Usage:** Authorization header và lỗi insufficient_scope.
- **RFC 7519 — JSON Web Token (JWT):** claims iss, sub, aud, exp.
- **RFC 7662 — OAuth 2.0 Token Introspection:** active và metadata của opaque token.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** access token claims, audience và token type.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** bảo vệ access/refresh token và ngăn token substitution/replay.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** sender-constrained access tokens.



