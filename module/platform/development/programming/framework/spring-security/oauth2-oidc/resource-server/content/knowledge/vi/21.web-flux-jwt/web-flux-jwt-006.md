# ReactiveJwtAuthenticationConverter và ánh xạ authorities

Trong **Spring Security OAuth 2.0/OIDC Resource Server** chạy trên **Spring WebFlux**, xác thực JWT access token có hai công việc khác nhau: **xác minh token** và **biến các claims đã được xác minh thành danh tính/quyền mà Spring Security hiểu**. Sau khi `ReactiveJwtDecoder` xác nhận chữ ký, issuer, thời hạn và những điều kiện token cần thiết, **`ReactiveJwtAuthenticationConverter`** chuyển đối tượng `Jwt` sang một `Authentication` dùng được trong **Reactor Context**.

Phần dễ nhầm nằm ở việc **claims không tự đồng nghĩa với GrantedAuthority**. Một token có `"scope": "orders.read"` thường được chuyển thành authority `SCOPE_orders.read`; nhưng nếu issuer dùng `"permissions": ["orders.export"]` hoặc đặt `roles` trong `realm_access.roles`, ứng dụng cần cấu hình ánh xạ một cách có chủ đích. Tùy chỉnh nhầm nguồn claim hay tiền tố sẽ khiến endpoint trả **403** dù JWT hợp lệ; tùy chỉnh quá rộng có thể khiến Resource Server cấp quyền vượt mức token thực sự được phát hành.

Bài này đi từ **`ReactiveJwtAuthenticationConverter`**, `JwtGrantedAuthoritiesConverter` và **`ReactiveJwtGrantedAuthoritiesConverterAdapter`** đến cách viết converter reactive thật, gắn converter vào **`SecurityWebFilterChain`**, đọc authorities trong **`ReactiveSecurityContextHolder`**, và kiểm thử ánh xạ cũng như phản hồi WebFlux.

## 1. Vị trí converter trong kiến trúc JWT WebFlux

Giả sử Orders API nhận:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <jwt-access-token>
~~~

JWT access token minh họa có claims:

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "iat": 1763164800,
  "exp": 1893456000,
  "scope": "orders.read orders.export"
}
~~~

Đây **chỉ là ví dụ payload**, chưa phải JWT ký hợp lệ. Trong request thực, Spring Security phải xác minh token bằng cấu hình tin cậy trước khi dùng claims.

~~~mermaid
flowchart TD
    A["HTTP Authorization: Bearer JWT"] --> B["SecurityWebFilterChain"]
    B --> C["Bearer token extraction / AuthenticationWebFilter"]
    C --> D["ReactiveAuthenticationManager"]
    D --> E["ReactiveJwtDecoder"]
    E --> F{"Signature, iss, aud, exp, nbf, profile hợp lệ?"}
    F -- "Không" --> X["Authentication failure: thường 401"]
    F -- "Có" --> G["Jwt đã được xác minh"]
    G --> H["ReactiveJwtAuthenticationConverter"]
    H --> I["Converter JWT claims → Flux<GrantedAuthority>"]
    I --> J["JwtAuthenticationToken"]
    J --> K["Reactive SecurityContext trong Reactor Context"]
    K --> L["AuthorizationWebFilter / method security"]
    L --> M{"Authority / object policy đạt?"}
    M -- "Không" --> Y["Thường 403 hoặc 404 theo policy"]
    M -- "Có" --> N["Reactive Controller / Service"]
~~~

Sơ đồ trình bày **trách nhiệm logic**, không khẳng định đúng tên hoặc vị trí của mọi WebFilter trên mọi phiên bản Spring Security.

| Thành phần | Vai trò |
| --- | --- |
| `SecurityWebFilterChain` | Xác định WebFlux requests được bảo vệ thế nào |
| `ServerHttpSecurity` | DSL cấu hình reactive HTTP security |
| `ReactiveJwtDecoder` | Giải mã/xác minh JWT, áp dụng token validators |
| `ReactiveJwtAuthenticationConverter` | Tạo reactive `Authentication` từ `Jwt` đã xác minh |
| `JwtGrantedAuthoritiesConverter` | Đồng bộ chuyển scope/claim quyền thành `Collection<GrantedAuthority>` |
| `ReactiveJwtGrantedAuthoritiesConverterAdapter` | Thích nghi converter authorities đồng bộ thành `Flux<GrantedAuthority>` |
| `JwtAuthenticationToken` | Authentication thường gặp của JWT Resource Server, mang JWT và authorities |
| `ReactiveSecurityContextHolder` | Đọc `SecurityContext` của subscriber từ Reactor Context |
| `AuthorizationWebFilter` và method security | Kiểm tra rule chức năng; chính sách nghiệp vụ xử lý tenant/owner |

**Converter không phải decoder.** Thay đổi `ReactiveJwtAuthenticationConverter` không biến token chưa xác minh thành đáng tin. API vẫn cần decoder tin cậy, kiểm tra audience dành cho API và các claim/profile bắt buộc.

## 2. Kiểu dữ liệu: vì sao tên “Reactive” quan trọng?

Trong Spring Security Servlet, `JwtAuthenticationConverter` thường là converter **đồng bộ**:

~~~java
Converter<Jwt, AbstractAuthenticationToken>
~~~

Trong WebFlux, `ReactiveJwtAuthenticationConverter` theo API phổ biến thực hiện:

~~~java
Converter<Jwt, Mono<AbstractAuthenticationToken>>
~~~

Nó cho phép chuỗi xác thực tạo `Mono` rồi tích hợp với pipeline Reactor. Thành phần ánh xạ quyền mà converter reactive mong đợi có dạng:

~~~java
Converter<Jwt, Flux<GrantedAuthority>>
~~~

Không nên nhầm ba tầng kiểu dữ liệu:

~~~text
JWT đã được decoder xác minh: Jwt
             |
             v
Authorities converter:
     Jwt -> Flux<GrantedAuthority>
             |
             v
ReactiveJwtAuthenticationConverter:
     Jwt -> Mono<AbstractAuthenticationToken>
             |
             v
JwtAuthenticationToken:
     principal, token, collection authorities
~~~

Trong các dòng Spring Security thông dụng, converter có thể thu thập Flux authorities thành danh sách trước khi tạo `JwtAuthenticationToken`. Nếu Flux quyền bị lỗi, xác thực JWT sẽ không hoàn tất thành công theo chuỗi ấy.

### So sánh Servlet và WebFlux

| Nội dung | Servlet | WebFlux |
| --- | --- | --- |
| HTTP security | `HttpSecurity` + `SecurityFilterChain` | `ServerHttpSecurity` + `SecurityWebFilterChain` |
| JWT decoder | `JwtDecoder` | `ReactiveJwtDecoder` |
| JWT authentication converter thường dùng | `JwtAuthenticationConverter` | `ReactiveJwtAuthenticationConverter` |
| Authorities converter mặc định/tùy chỉnh | `JwtGrantedAuthoritiesConverter` | Có thể dùng cùng converter qua reactive adapter |
| Security context | Thường gắn với ThreadLocal | Reactor Context theo subscriber |
| Đối tượng JWT authentication | `JwtAuthenticationToken` | Cũng thường là `JwtAuthenticationToken` |
| Test HTTP | `MockMvc` | `WebTestClient` |

Các tên lớp gần nhau nhưng **không tự hoán đổi**. Đưa một `JwtAuthenticationConverter` đồng bộ thẳng vào DSL đòi `Mono<AbstractAuthenticationToken>` có thể gây lỗi type; phải dùng adapter tương ứng hoặc viết reactive converter.

## 3. Quy tắc mặc định: scope/scp → SCOPE_

Trong cấu hình thông dụng của Spring Security JWT Resource Server, quyền OAuth 2.0 được đọc từ một claim scope quen thuộc như **`scope`** hoặc **`scp`**.

Ví dụ:

~~~json
{
  "scope": "orders.read orders.write"
}
~~~

Kết quả thường là:

~~~text
JwtGrantedAuthoritiesConverter
  "orders.read"  -> SimpleGrantedAuthority("SCOPE_orders.read")
  "orders.write" -> SimpleGrantedAuthority("SCOPE_orders.write")
~~~

Hoặc issuer phát:

~~~json
{
  "scp": ["orders.read", "orders.export"]
}
~~~

Kết quả:

~~~text
SCOPE_orders.read
SCOPE_orders.export
~~~

Vì vậy rule:

~~~java
.pathMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

phù hợp với scope `orders.read`, trong khi `hasAuthority("orders.read")` **không tự khớp** nếu converter đã thêm tiền tố `SCOPE_`.

Một số lưu ý:

- `scope` thường là **chuỗi các scope cách nhau bằng dấu cách** theo OAuth 2.0.
- `scp` có thể là một mảng string theo hợp đồng của issuer.
- Thiếu claim được converter nhận diện thường tạo **tập authorities rỗng**, không phải tự cấp quyền mặc định.
- Nếu cùng có `scope` và `scp`, **không giả định mặc định tự hợp nhất cả hai**; converter có cơ chế chọn claim quen thuộc theo phiên bản.
- Claim tùy chỉnh như `permissions`, `groups` hoặc `roles` **không tự** thành authority chỉ vì có trong token.
- `SCOPE_` là **quy ước tên authority**, không phải claim JSON hoặc chứng cứ người gọi sở hữu đơn hàng.

### Scope khác với vai trò của người dùng

Scope thường thể hiện quyền OAuth 2.0 đã được **cấp cho token/client trong ngữ cảnh truy cập tài nguyên**. Role như `ORDER_MANAGER` có thể thuộc mô hình quyền nghiệp vụ của subject. Hai dữ liệu này không nhất thiết có cùng phạm vi.

Ví dụ một nhân viên có role `ORDER_MANAGER` nhưng client chỉ xin và được cấp `orders.read`; API không nên tự suy ra client được `orders.delete`. Những thao tác nhạy cảm có thể cần **cả scope và role**, cộng kiểm tra tenant/owner.

## 4. Dùng JwtGrantedAuthoritiesConverter thông qua reactive adapter

Khi issuer phát claim quyền dạng **string** hoặc **array string** đơn giản, cách ít code nhất là cấu hình `JwtGrantedAuthoritiesConverter` đồng bộ rồi đưa nó qua **`ReactiveJwtGrantedAuthoritiesConverterAdapter`**.

Ví dụ issuer có:

~~~json
{
  "sub": "user-42",
  "aud": ["orders-api"],
  "permissions": ["orders.read", "orders.export"]
}
~~~

Ta muốn chuyển `permissions` thành:

~~~text
PERMISSION_orders.read
PERMISSION_orders.export
~~~

Code:

~~~java
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtGrantedAuthoritiesConverterAdapter;

JwtGrantedAuthoritiesConverter permissionExtractor =
    new JwtGrantedAuthoritiesConverter();
permissionExtractor.setAuthoritiesClaimName("permissions");
permissionExtractor.setAuthorityPrefix("PERMISSION_");

ReactiveJwtAuthenticationConverter authenticationConverter =
    new ReactiveJwtAuthenticationConverter();
authenticationConverter.setJwtGrantedAuthoritiesConverter(
    new ReactiveJwtGrantedAuthoritiesConverterAdapter(permissionExtractor)
);
~~~

Ở đây:

1. `setAuthoritiesClaimName("permissions")` chọn **nguồn claim**.
2. `setAuthorityPrefix("PERMISSION_")` chọn **tên authority**.
3. `ReactiveJwtGrantedAuthoritiesConverterAdapter` biến output từ `Collection<GrantedAuthority>` thành `Flux<GrantedAuthority>` theo contract WebFlux.
4. `ReactiveJwtAuthenticationConverter` tiếp nhận `Flux` và xây Authentication cho JWT.

**Đổi nguồn sang `permissions` có thể làm mất authorities đến từ `scope`/`scp`** nếu chỉ dùng một extractor đã bị cấu hình lại. Muốn giữ cả hai, phải **kết hợp converters** hoặc viết custom converter rõ ràng.

### Thêm delimiter cho claim chuỗi tùy chỉnh

Một issuer có thể phát:

~~~json
{
  "permissions": "orders.read,orders.export"
}
~~~

Ở các phiên bản Spring Security cung cấp `setAuthoritiesClaimDelimiter(String)`, ví dụ Spring Security 6.1 trở lên, có thể:

~~~java
JwtGrantedAuthoritiesConverter converter =
    new JwtGrantedAuthoritiesConverter();
converter.setAuthoritiesClaimName("permissions");
converter.setAuthorityPrefix("PERMISSION_");
converter.setAuthoritiesClaimDelimiter(",");
~~~

Delimiter thường là **regex**, nên cần escape đúng theo Java và theo ngữ nghĩa issuer. Không coi dấu phẩy là chuẩn mặc định của OAuth 2.0 `scope`. Với mảng string, converter không cần tách một chuỗi bằng dấu phân cách.

**Lưu ý phiên bản:** nếu `setAuthoritiesClaimDelimiter(...)` không tồn tại trong thư viện hiện tại, dùng converter riêng hoặc nâng cấp có kiểm soát; không sao chép code rồi bỏ qua lỗi compile.

## 5. Gắn ReactiveJwtAuthenticationConverter vào ServerHttpSecurity

Một đối tượng converter chỉ có tác dụng khi **được gắn vào cấu hình WebFlux JWT Resource Server đang xử lý request**.

Dependency Maven thường dùng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

Ví dụ cấu hình WebFlux với permissions:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtGrantedAuthoritiesConverterAdapter;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class ReactiveOrdersSecurity {

    @Bean
    ReactiveJwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter permissions =
            new JwtGrantedAuthoritiesConverter();
        permissions.setAuthoritiesClaimName("permissions");
        permissions.setAuthorityPrefix("PERMISSION_");

        ReactiveJwtAuthenticationConverter converter =
            new ReactiveJwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(
            new ReactiveJwtGrantedAuthoritiesConverterAdapter(permissions));
        return converter;
    }

    @Bean
    SecurityWebFilterChain apiSecurity(
            ServerHttpSecurity http,
            ReactiveJwtAuthenticationConverter jwtAuthenticationConverter) {
        return http
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public/**").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("PERMISSION_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/reports/export")
                    .hasAuthority("PERMISSION_orders.export")
                .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt ->
                jwt.jwtAuthenticationConverter(jwtAuthenticationConverter)))
            .build();
    }
}
~~~

Kết quả:

~~~text
JWT.permissions = ["orders.read", "orders.export"]
          |
          v
ReactiveJwtGrantedAuthoritiesConverterAdapter
          |
          v
Flux<GrantedAuthority>:
  PERMISSION_orders.read
  PERMISSION_orders.export
          |
          v
JwtAuthenticationToken trong Reactor Context
          |
          v
WebFlux authorizeExchange().hasAuthority(...)
~~~

**Quan trọng:** cấu hình này **chỉ ánh xạ `permissions`**. Những rule dùng `SCOPE_orders.read` có thể trả 403 vì không còn converter scope mặc định. Nếu ứng dụng cần cả hai loại quyền, xem phần kết hợp phía dưới.

CSRF được tắt trong ví dụ vì giả định API **stateless, Bearer-only và không dựa vào cookie credential trình duyệt tự gửi**. Với ứng dụng có cookie/session, phải đánh giá CSRF và thay đổi cấu hình phù hợp.

Về bảo mật token, `issuer-uri` giúp cấu hình issuer/JWKS theo khả năng của Spring Security; **audience, token type/profile và các claim nghiệp vụ bắt buộc vẫn cần được kiểm tra theo hợp đồng API**. Tùy chỉnh converter không thay thế các validators đó.

## 6. Kết hợp scope và permissions mà không làm mất quyền cũ

Một JWT có thể chứa cả:

~~~json
{
  "scope": "orders.read",
  "permissions": ["orders.export", "reports.view"]
}
~~~

Ta muốn:

~~~text
SCOPE_orders.read
PERMISSION_orders.export
PERMISSION_reports.view
~~~

### 6.1. Kết hợp bằng converter đồng bộ rồi dùng reactive adapter

Ở những phiên bản Spring Security cung cấp `DelegatingJwtGrantedAuthoritiesConverter`, có thể dùng:

~~~java
import org.springframework.security.oauth2.server.resource.authentication.DelegatingJwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtGrantedAuthoritiesConverterAdapter;

JwtGrantedAuthoritiesConverter scopes =
    new JwtGrantedAuthoritiesConverter(); // scope/scp, SCOPE_

JwtGrantedAuthoritiesConverter permissions =
    new JwtGrantedAuthoritiesConverter();
permissions.setAuthoritiesClaimName("permissions");
permissions.setAuthorityPrefix("PERMISSION_");

DelegatingJwtGrantedAuthoritiesConverter combined =
    new DelegatingJwtGrantedAuthoritiesConverter(scopes, permissions);

ReactiveJwtAuthenticationConverter authentication =
    new ReactiveJwtAuthenticationConverter();
authentication.setJwtGrantedAuthoritiesConverter(
    new ReactiveJwtGrantedAuthoritiesConverterAdapter(combined));
~~~

`DelegatingJwtGrantedAuthoritiesConverter` kết hợp authorities của các converter con. Cách này phù hợp khi các nguồn đều có thể trích xuất **đồng bộ, nhanh và không cần I/O**.

Nếu class không có trong phiên bản dependency, có thể tự viết `Converter<Jwt, Collection<GrantedAuthority>>` để ghép kết quả bằng `LinkedHashSet`, sau đó đưa qua reactive adapter.

### 6.2. Kết hợp trực tiếp trong Flux

Một lựa chọn khác là tạo `Converter<Jwt, Flux<GrantedAuthority>>` bằng Reactor:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtGrantedAuthoritiesConverterAdapter;
import reactor.core.publisher.Flux;

public final class ScopesAndPermissionsConverter
        implements Converter<Jwt, Flux<GrantedAuthority>> {

    private final ReactiveJwtGrantedAuthoritiesConverterAdapter scopeAdapter;
    private final ReactiveJwtGrantedAuthoritiesConverterAdapter permissionAdapter;

    public ScopesAndPermissionsConverter() {
        JwtGrantedAuthoritiesConverter scopes =
            new JwtGrantedAuthoritiesConverter();

        JwtGrantedAuthoritiesConverter permissions =
            new JwtGrantedAuthoritiesConverter();
        permissions.setAuthoritiesClaimName("permissions");
        permissions.setAuthorityPrefix("PERMISSION_");

        this.scopeAdapter =
            new ReactiveJwtGrantedAuthoritiesConverterAdapter(scopes);
        this.permissionAdapter =
            new ReactiveJwtGrantedAuthoritiesConverterAdapter(permissions);
    }

    @Override
    public Flux<GrantedAuthority> convert(Jwt jwt) {
        return Flux.concat(
            scopeAdapter.convert(jwt),
            permissionAdapter.convert(jwt)
        ).distinct(GrantedAuthority::getAuthority);
    }
}
~~~

Gắn vào:

~~~java
ReactiveJwtAuthenticationConverter authentication =
    new ReactiveJwtAuthenticationConverter();
authentication.setJwtGrantedAuthoritiesConverter(
    new ScopesAndPermissionsConverter());
~~~

`distinct(GrantedAuthority::getAuthority)` tránh lặp tên authority khi các nguồn có giá trị trùng. Trật tự phát Flux không nên được dùng làm cơ sở quyết định quyền; authorization chỉ cần đúng tập tên authority.

**Kết hợp sources là quyết định policy.** Nếu `permissions` là quyền user tổng quát còn `scope` là quyền token đã cấp cho một client cụ thể, việc gộp có thể mở rộng khả năng gọi API của client. Hãy xác định rõ một rule cần **một authority bất kỳ** hay **nhiều điều kiện đồng thời**.

## 7. Ánh xạ roles nằm trong claims lồng nhau

Một số issuer cung cấp vai trò trong object thay vì một claim string trực tiếp. Ví dụ cấu trúc thường gặp:

~~~json
{
  "sub": "user-42",
  "scope": "orders.read",
  "realm_access": {
    "roles": ["USER", "REPORT_VIEWER"]
  },
  "resource_access": {
    "orders-api": {
      "roles": ["ORDER_EDITOR"]
    },
    "billing-api": {
      "roles": ["BILLING_ADMIN"]
    }
  }
}
~~~

Không nên giả định:

~~~java
// KHÔNG phải JSONPath mặc định:
roles.setAuthoritiesClaimName("resource_access.orders-api.roles");
~~~

`JwtGrantedAuthoritiesConverter` thông thường tra **tên claim ở cấp trực tiếp**. Dấu chấm không tự biến thành truy vấn nested JSON. Với nested object, cần converter hiểu schema.

### Converter đọc riêng roles dành cho orders-api

Ví dụ role mapping chỉ chấp nhận những vai trò đã định nghĩa:

~~~java
import java.util.Collection;
import java.util.Map;
import java.util.Set;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import reactor.core.publisher.Flux;

public final class OrdersResourceRolesConverter
        implements Converter<Jwt, Flux<GrantedAuthority>> {

    private static final String RESOURCE = "orders-api";
    private static final Set<String> ALLOWED_ROLES =
        Set.of("ORDER_READER", "ORDER_EDITOR", "ORDER_MANAGER");

    @Override
    public Flux<GrantedAuthority> convert(Jwt jwt) {
        return Flux.defer(() -> {
            Object rawResources = jwt.getClaim("resource_access");
            if (!(rawResources instanceof Map<?, ?> resources)) {
                return Flux.empty();
            }

            Object rawOrders = resources.get(RESOURCE);
            if (!(rawOrders instanceof Map<?, ?> orders)) {
                return Flux.empty();
            }

            Object rawRoles = orders.get("roles");
            if (!(rawRoles instanceof Collection<?> values)) {
                return Flux.empty();
            }

            return Flux.fromIterable(values)
                .filter(String.class::isInstance)
                .cast(String.class)
                .filter(ALLOWED_ROLES::contains)
                .map(role -> (GrantedAuthority)
                    new SimpleGrantedAuthority("ROLE_" + role));
        });
    }
}
~~~

Ở đây:

- Chỉ đọc roles trong **`resource_access["orders-api"]`**.
- Không tự thêm `BILLING_ADMIN` từ `billing-api`.
- Chỉ chuyển những role nằm trong **allowlist**.
- Trả `Flux.empty()` khi không có dữ liệu phù hợp, không tự cấp quyền.
- Tạo namespace `ROLE_`, dành cho rule role được ứng dụng định nghĩa.

**Vai trò cấp realm và vai trò riêng của resource có ý nghĩa khác nhau**. API phải quyết định có chấp nhận realm role không; ví dụ trên chỉ chấp nhận resource role để tránh lấy quyền ở nơi khác.

Khi profile yêu cầu cấu trúc quyền là bắt buộc, **claim sai kiểu có thể cần bị từ chối tại token validation**, chứ không chỉ bỏ qua và trả Flux rỗng. Cách xử lý phải được thống nhất theo hợp đồng với Authorization Server.

### Kết hợp roles với scopes

~~~java
public final class OrdersAuthoritiesConverter
        implements Converter<Jwt, Flux<GrantedAuthority>> {

    private final ReactiveJwtGrantedAuthoritiesConverterAdapter scopes =
        new ReactiveJwtGrantedAuthoritiesConverterAdapter(
            new JwtGrantedAuthoritiesConverter());

    private final OrdersResourceRolesConverter roles =
        new OrdersResourceRolesConverter();

    @Override
    public Flux<GrantedAuthority> convert(Jwt jwt) {
        return Flux.concat(
            scopes.convert(jwt),
            roles.convert(jwt)
        ).distinct(GrantedAuthority::getAuthority);
    }
}
~~~

Ví dụ skeleton trên cần các import `Converter`, `Jwt`, `Flux`, `GrantedAuthority` và classes đã được trình bày ở phần trước.

Khi gắn converter này, có thể yêu cầu **cả scope và role**:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.write') and hasRole('ORDER_EDITOR')")
public Mono<Void> updateOrder(String orderId, UpdateOrderRequest request) {
    // ...
}
~~~

Trong cấu hình Spring Security phổ biến, `hasRole('ORDER_EDITOR')` tìm authority `ROLE_ORDER_EDITOR`. Nếu cần kiểm tra tên đầy đủ, dùng `hasAuthority('ROLE_ORDER_EDITOR')`; không mặc định `hasRole('ROLE_ORDER_EDITOR')` là đúng.

## 8. Phân biệt authorities đồng bộ và xử lý I/O thực sự reactive

Tên class **`ReactiveJwtAuthenticationConverter` không có nghĩa mọi logic trong converter tự thành non-blocking**.

Khi ánh xạ scope/roles thuần túy từ claims trong bộ nhớ:

~~~text
Jwt -> đọc claims -> SimpleGrantedAuthority -> Flux
~~~

việc dùng `JwtGrantedAuthoritiesConverter` đồng bộ qua `ReactiveJwtGrantedAuthoritiesConverterAdapter` rất phù hợp.

Ngược lại, nếu mapper thực hiện:

~~~java
// KHÔNG NÊN trong event-loop:
List<String> roles = blockingRoleRepository.findRoles(jwt.getSubject());
~~~

thì nó vẫn **block thread** dù được đặt bên trong một reactive converter. Adapter không tự chuyển blocking I/O sang một scheduler an toàn.

### Khi thật sự phải dùng một dịch vụ quyền reactive

Có thể khai báo converter trả Flux từ một dịch vụ asynchronous:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import reactor.core.publisher.Flux;

public final class ReactivePolicyAuthoritiesConverter
        implements Converter<Jwt, Flux<GrantedAuthority>> {

    private final ReactiveRoleService roleService;

    public ReactivePolicyAuthoritiesConverter(ReactiveRoleService roleService) {
        this.roleService = roleService;
    }

    @Override
    public Flux<GrantedAuthority> convert(Jwt jwt) {
        return Flux.defer(() -> roleService
            .findAllowedRoles(jwt.getIssuer().toString(), jwt.getSubject())
            .filter(role -> role.startsWith("ORDER_"))
            .map(role -> (GrantedAuthority)
                new SimpleGrantedAuthority("ROLE_" + role)));
    }
}
~~~

`ReactiveRoleService` là **interface nghiệp vụ tự xây**, giả định `findAllowedRoles(...)` trả `Flux<String>` từ nguồn dữ liệu reactive tin cậy. Ví dụ minh họa khả năng compose publisher thay vì gọi `block()`. Trong production cần thêm kiểm tra danh sách role **chính xác** (allowlist, tenant, audience và chính sách), không chỉ `startsWith("ORDER_")` nếu việc đó tạo khả năng nâng quyền.

### Những đánh đổi khi tra quyền tại authentication

Nếu converter gọi DB hoặc policy service để tạo authorities, bạn phải xác định:

- **Latency:** mỗi lần xác thực có thể thêm I/O hoặc retry.
- **Availability:** nguồn role lỗi thì phải **fail closed**, không mặc định cấp quyền.
- **Revocation:** role thay đổi giữa lúc token được phát hành và lúc request được xác thực.
- **Scope/token semantics:** quyền nội bộ không được mở rộng chức năng vượt những scope client đã được cấp.
- **Tenant:** role thường thuộc tenant hoặc resource; cache theo subject không đủ nếu bỏ qua issuer/tenant.
- **Caching:** nếu cache authorities, cần TTL và invalidation theo độ nhạy quyền.
- **Resource authorization:** ngay cả role đã xác thực cũng không thay quyền trên từng bản ghi.

Trong nhiều hệ thống, converter nên **nhanh, thuần dữ liệu từ token**; membership, owner và share nên được đánh giá ở tầng service và repository nơi có ngữ cảnh tài nguyên đầy đủ. Không cố biến converter thành nơi thực hiện mọi chính sách nghiệp vụ.

### Không subscribe hoặc block trong converter

Tránh:

~~~java
// KHÔNG: tạo subscription độc lập, không đợi kết quả đúng.
roleService.findAllowedRoles(...).subscribe(role -> addAuthority(role));

// KHÔNG: chặn event-loop và tạo subscription khác.
List<String> roles = roleService.findAllowedRoles(...).collectList().block();
~~~

Thay vào đó **trả `Flux<GrantedAuthority>`** và để WebFlux/Spring Security quản lý việc subscribe trong authentication pipeline.

## 9. ReactiveJwtAuthenticationConverterAdapter khác gì?

Spring Security có một adapter tên gần giống:

**`ReactiveJwtAuthenticationConverterAdapter`**.

Hai adapter này có mục đích **khác nhau**:

| Class | Đầu vào được bọc | Kiểu kết quả đưa sang reactive |
| --- | --- | --- |
| `ReactiveJwtGrantedAuthoritiesConverterAdapter` | `Converter<Jwt, Collection<GrantedAuthority>>` | `Converter<Jwt, Flux<GrantedAuthority>>` |
| `ReactiveJwtAuthenticationConverterAdapter` | `Converter<Jwt, AbstractAuthenticationToken>` | `Converter<Jwt, Mono<AbstractAuthenticationToken>>` |

### Dùng adapter authentication khi chuyển từ Servlet

Nếu dự án đã có `JwtAuthenticationConverter` đồng bộ với policy mapping thuần claims, bạn có thể bọc toàn bộ:

~~~java
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtAuthenticationConverterAdapter;

JwtGrantedAuthoritiesConverter permissions =
    new JwtGrantedAuthoritiesConverter();
permissions.setAuthoritiesClaimName("permissions");
permissions.setAuthorityPrefix("PERMISSION_");

JwtAuthenticationConverter servletStyle =
    new JwtAuthenticationConverter();
servletStyle.setJwtGrantedAuthoritiesConverter(permissions);

ReactiveJwtAuthenticationConverterAdapter reactive =
    new ReactiveJwtAuthenticationConverterAdapter(servletStyle);
~~~

Rồi cấu hình:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt ->
    jwt.jwtAuthenticationConverter(reactive)))
~~~

Đây là cách **tái sử dụng converter đồng bộ**, không biến mọi tác vụ synchronous thành non-blocking. Nếu converter cũ có I/O blocking, phải thiết kế lại thay vì chỉ bọc adapter.

### Nên chọn cách nào?

- **Chỉ cần đổi claim/prefix/delimiter:** `JwtGrantedAuthoritiesConverter` + `ReactiveJwtGrantedAuthoritiesConverterAdapter`.
- **Đã có toàn bộ `JwtAuthenticationConverter` Servlet-style:** có thể dùng `ReactiveJwtAuthenticationConverterAdapter`.
- **Cần kết hợp nhiều nguồn thuần claims:** delegating converter đồng bộ + adapter, hoặc một converter trả Flux.
- **Cần quyền từ reactive service:** custom `Converter<Jwt, Flux<GrantedAuthority>>` có compose publisher và policy rõ ràng.

Hãy đối chiếu **kiểu generic** và API của Spring Security version hiện tại; tên gần giống là nguyên nhân phổ biến của lỗi compile hoặc gắn converter nhầm lớp.

## 10. Principal name và ánh xạ danh tính

`ReactiveJwtAuthenticationConverter` không chỉ tạo authorities; nó còn xác định principal name cho `JwtAuthenticationToken`.

Theo mặc định phổ biến, principal name dựa trên **`sub`** của JWT. Ví dụ:

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "a6be8cf9",
  "preferred_username": "alice",
  "scope": "orders.read"
}
~~~

Nếu dự án muốn `Authentication.getName()` hiển thị `preferred_username`, ở những phiên bản hỗ trợ `setPrincipalClaimName(...)`:

~~~java
ReactiveJwtAuthenticationConverter converter =
    new ReactiveJwtAuthenticationConverter();
converter.setPrincipalClaimName("preferred_username");
~~~

Điều này chỉ thay cách đặt tên Authentication. **Không thay đổi JWT `sub`, không cấp thêm authority và không biến username thành khóa ownership bất biến.**

Với multi-issuer Resource Server, định danh bền vững có thể cần cặp **`(iss, sub)`** đã được xác minh để ánh xạ sang internal user ID. Email và username thường có thể thay đổi, nên không dùng `preferred_username` làm bằng chứng quyền sở hữu bản ghi.

Với **Client Credentials**, token có thể đại diện **machine client** thay vì người dùng; chính sách owner/tenant và `getName()` phải được xác định theo hợp đồng client identity, không mặc định mọi `sub` đều là user ID.

## 11. Đọc authorities từ Reactor SecurityContext

Khi converter tạo thành công `JwtAuthenticationToken`, Spring Security WebFlux đặt Authentication trong **SecurityContext thuộc Reactor Context**, để các publisher downstream đọc được.

Trong reactive service:

~~~java
import java.util.List;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

public Mono<List<String>> currentAuthorities() {
    return ReactiveSecurityContextHolder.getContext()
        .flatMap(context ->
            Mono.justOrEmpty(context.getAuthentication()))
        .map(Authentication::getAuthorities)
        .map(authorities -> authorities.stream()
            .map(GrantedAuthority::getAuthority)
            .toList());
}
~~~

`ReactiveSecurityContextHolder.getContext()` trả **`Mono<SecurityContext>`**, không phải SecurityContext đồng bộ. Nó được giải quyết ở **subscription** trong context của request.

Đừng viết:

~~~java
// Không nên trong WebFlux request flow:
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
~~~

vì `SecurityContextHolder` theo kiểu ThreadLocal Servlet **không phải nguồn danh tính mặc định của Reactor subscriber**.

### Truy cập JWT trong reactive service

~~~java
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import reactor.core.publisher.Mono;

public Mono<Jwt> currentJwt() {
    return ReactiveSecurityContextHolder.getContext()
        .flatMap(ctx ->
            Mono.justOrEmpty(ctx.getAuthentication()))
        .ofType(JwtAuthenticationToken.class)
        .map(JwtAuthenticationToken::getToken)
        .switchIfEmpty(Mono.error(
            new AuthenticationCredentialsNotFoundException(
                "JWT Authentication required")));
}
~~~

Với JWT Resource Server, `JwtAuthenticationToken.getToken()` trả Jwt đã được decoder xử lý. Với opaque token, principal thường là `OAuth2AuthenticatedPrincipal` và Authentication thường là `BearerTokenAuthentication`; **không ép kiểu opaque principal thành Jwt**.

### Không block hoặc subscribe để lấy identity

Tránh:

~~~java
// KHÔNG NÊN: block trong event-loop, subscription độc lập.
Jwt jwt = currentJwt().block();

// KHÔNG NÊN: fire-and-forget, không bảo đảm lifecycle/context.
currentAuthorities().subscribe(System.out::println);
~~~

Hãy compose publisher để framework subscribe trong HTTP request flow. `publishOn`/`subscribeOn` trong cùng Reactor subscription không tự làm mất Reactor Context; rủi ro thường ở **tách subscription** hoặc bridge sang callback/executor không mang context.

## 12. HTTP authorization, method security và quyền trên đối tượng

Giả sử kết quả converter:

~~~text
SCOPE_orders.read
SCOPE_orders.write
ROLE_ORDER_EDITOR
PERMISSION_orders.export
~~~

Trong WebFlux, có thể dùng `authorizeExchange`:

~~~java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .pathMatchers(HttpMethod.POST, "/api/orders/**")
        .hasAuthority("SCOPE_orders.write")
    .pathMatchers("/api/reports/export")
        .hasAuthority("PERMISSION_orders.export")
    .anyExchange().authenticated())
~~~

**Thứ tự matcher quan trọng.** Đặt matcher cụ thể cho `/api/reports/export` trước matcher rộng hơn nếu các pattern chồng nhau; không để rule rộng vô tình bắt endpoint nhạy cảm trước.

Khi dùng `@EnableReactiveMethodSecurity`, service trả `Mono`/`Flux` có thể được bảo vệ bằng `@PreAuthorize`:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class OrderCommandService {

    private final ReactiveOrderRepository orders;
    private final CurrentActorService actors;

    public OrderCommandService(
            ReactiveOrderRepository orders,
            CurrentActorService actors) {
        this.orders = orders;
        this.actors = actors;
    }

    @PreAuthorize(
        "hasAuthority('SCOPE_orders.write') and hasRole('ORDER_EDITOR')")
    public Mono<Void> update(String tenantId, String orderId, UpdateOrderRequest input) {
        return actors.currentActor()
            .flatMap(actor -> orders.updateIfAllowed(
                tenantId, orderId, actor.userId(), input));
    }
}
~~~

Các interfaces/DTO trong ví dụ là **mã miền nghiệp vụ tự xây**, không phải Spring Security APIs. `updateIfAllowed(...)` phải kiểm tra actor có quyền trong **đúng tenant và order**. Chỉ có `SCOPE_orders.write` hay `ROLE_ORDER_EDITOR` không đủ để sửa đơn hàng của người khác.

Quy tắc an toàn có thể là:

~~~text
Access token hợp lệ
    AND có SCOPE_orders.write
    AND có ROLE_ORDER_EDITOR (nếu policy yêu cầu)
    AND actor là thành viên active của tenant
    AND (actor là owner OR được cấp EDIT share)
    AND order đang ở trạng thái cho phép sửa
~~~

Reactive method security thường dựa trên proxy/interceptor; **self-invocation** từ một method cùng bean tới method khác có `@PreAuthorize` có thể không đi qua interceptor. Đừng đặt tất cả bảo vệ ở một annotation rồi để những đường chạy khác truy vấn DB không có scope.

## 13. Converter tùy chỉnh không làm tăng độ tin cậy của claims

Một số nguy cơ cần phân biệt:

**Đọc claims từ JWT chưa được xác minh.** Base64URL decode một phần payload ở frontend hoặc controller không xác thực được signature. Authorities chỉ được tạo từ `Jwt` mà `ReactiveJwtDecoder` đã chấp nhận theo chính sách.

**Nhận ID token như access token.** OIDC ID token có thể mang `groups` hoặc `roles`, nhưng không tự là access token dành cho Resource Server. Kiểm tra `aud`, token type/profile và mục đích token đúng hợp đồng.

**Issuer sai hoặc bị đánh tráo.** Với nhiều issuer, không lấy JWKS URL bất kỳ từ claim `iss` chưa được xác minh rồi tin mọi khóa; sử dụng allowlist và resolver/decoder phù hợp miền tin cậy.

**Mapping role của resource khác.** Nếu JWT có `resource_access.billing-api.roles`, Orders API không nên chuyển `BILLING_ADMIN` thành role quản trị đơn hàng.

**Mapping mọi string thành permission.** Một array từ issuer có dữ liệu sai kiểu hoặc tên ngoài allowlist không nên tạo authority tùy ý. Cần schema, allowlist và policy lỗi.

**Giữ quyền đã bị thu hồi.** Nếu role/membership trong JWT cũ vẫn còn đến `exp`, converter sẽ đọc claim cũ. Các quyền cần thu hồi nhanh có thể phải tham chiếu trạng thái policy hiện hành hoặc token revocation/introspection phù hợp.

**Lộ thông tin trong log.** Không log raw JWT, Authorization header, private key hoặc token attributes nhạy cảm chỉ để debug mapping. Có thể ghi request ID, issuer đã xác minh, tên authority cần thiết và lý do lỗi ở mức phù hợp.

## 14. Kiểm thử unit converter bằng StepVerifier

Vì `ReactiveJwtAuthenticationConverter.convert(jwt)` trả `Mono<AbstractAuthenticationToken>`, có thể kiểm tra kết quả trong **Reactor Test** mà không cần HTTP server.

Ví dụ ánh xạ `permissions`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Instant;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtGrantedAuthoritiesConverterAdapter;
import reactor.test.StepVerifier;

class ReactiveJwtAuthenticationConverterTest {

    @Test
    void mapsPermissionsToAuthorities() {
        Jwt jwt = Jwt.withTokenValue("unit-test-token")
            .header("alg", "RS256")
            .issuer("https://auth.example.com/realms/shop")
            .subject("user-42")
            .issuedAt(Instant.parse("2026-01-01T00:00:00Z"))
            .expiresAt(Instant.parse("2031-01-01T00:00:00Z"))
            .claim("scope", "payments.write")
            .claim("permissions", List.of("orders.read", "orders.export"))
            .build();

        JwtGrantedAuthoritiesConverter extractor =
            new JwtGrantedAuthoritiesConverter();
        extractor.setAuthoritiesClaimName("permissions");
        extractor.setAuthorityPrefix("PERMISSION_");

        ReactiveJwtAuthenticationConverter converter =
            new ReactiveJwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(
            new ReactiveJwtGrantedAuthoritiesConverterAdapter(extractor));

        StepVerifier.create(converter.convert(jwt))
            .assertNext(authentication -> {
                assertTrue(authentication instanceof JwtAuthenticationToken);
                assertEquals("user-42", authentication.getName());

                Set<String> names = authentication.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .collect(Collectors.toSet());

                assertTrue(names.contains("PERMISSION_orders.read"));
                assertTrue(names.contains("PERMISSION_orders.export"));
                assertFalse(names.contains("SCOPE_payments.write"));
            })
            .verifyComplete();
    }
}
~~~

**Vì extractor được đặt nguồn `permissions`, scope `payments.write` không được chuyển thành authority** trong test này. Test cũng chứng minh principal name mặc định thông dụng dựa trên `sub`.

`"unit-test-token"` là chuỗi dummy; `Jwt` được dựng tay ở đây **không chứng minh chữ ký JWS hợp lệ**. Unit test chỉ kiểm tra chuyển đổi đối tượng Jwt → Authentication và names.

### Test thiếu claim quyền

Khi issuer không có claim mà converter mong đợi:

~~~java
Jwt jwt = Jwt.withTokenValue("unit-test")
    .header("alg", "RS256")
    .subject("user-42")
    .claim("scope", "orders.read")
    .build();

JwtGrantedAuthoritiesConverter permissions =
    new JwtGrantedAuthoritiesConverter();
permissions.setAuthoritiesClaimName("permissions");
permissions.setAuthorityPrefix("PERMISSION_");

ReactiveJwtAuthenticationConverter converter =
    new ReactiveJwtAuthenticationConverter();
converter.setJwtGrantedAuthoritiesConverter(
    new ReactiveJwtGrantedAuthoritiesConverterAdapter(permissions));

StepVerifier.create(converter.convert(jwt))
    .assertNext(auth -> assertTrue(auth.getAuthorities().isEmpty()))
    .verifyComplete();
~~~

Đây là hành vi hữu ích khi claim quyền tùy chọn. Nếu profile bắt buộc `permissions`, nên có **token validator** để từ chối JWT thiếu/sai schema thay vì chỉ tạo Authentication rỗng rồi chờ authorization.

### Test roles lồng nhau

Test `OrdersResourceRolesConverter` với JWT có `resource_access.orders-api.roles` và `resource_access.billing-api.roles`. Kỳ vọng chỉ có `ROLE_ORDER_EDITOR` khi đó là role được allowlist và namespace đúng; **không** có `ROLE_BILLING_ADMIN`. Kiểm tra cả trường hợp claim null, sai kiểu và array trống theo schema mà API hỗ trợ.

## 15. WebTestClient: kiểm thử mapping trong SecurityWebFilterChain

Để xác nhận converter **đã được gắn đúng vào WebFlux Resource Server**, cần một test HTTP đi qua `SecurityWebFilterChain` thay vì chỉ gọi `convert(jwt)` trực tiếp.

Spring Boot/WebFlux có thể dùng `@SpringBootTest` + `@AutoConfigureWebTestClient`. Mock đúng boundary là **`ReactiveJwtDecoder`**, giữ WebFilter, converter và authorization rules thật.

Ví dụ (giả định đã có endpoint GET `/api/reports/list` yêu cầu `PERMISSION_orders.read`):

~~~java
import static org.mockito.Mockito.when;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

@SpringBootTest
@AutoConfigureWebTestClient
class WebFluxJwtAuthoritiesTest {

    @Autowired WebTestClient client;

    @MockitoBean
    ReactiveJwtDecoder jwtDecoder;

    @Test
    void tokenWithPermissionIsAllowedByRealChain() {
        when(jwtDecoder.decode("token-with-permission"))
            .thenReturn(Mono.just(jwt(
                "token-with-permission",
                List.of("orders.read"))));

        client.get().uri("/api/reports/list")
            .headers(headers -> headers.setBearerAuth("token-with-permission"))
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void validTokenWithoutPermissionIsForbidden() {
        when(jwtDecoder.decode("token-without-permission"))
            .thenReturn(Mono.just(jwt(
                "token-without-permission",
                List.of("reports.other"))));

        client.get().uri("/api/reports/list")
            .headers(headers -> headers.setBearerAuth("token-without-permission"))
            .exchange()
            .expectStatus().isForbidden();
    }

    private static Jwt jwt(String tokenValue, List<String> permissions) {
        return Jwt.withTokenValue(tokenValue)
            .header("alg", "RS256")
            .issuer("https://auth.example.com/realms/shop")
            .subject("user-42")
            .issuedAt(Instant.parse("2026-01-01T00:00:00Z"))
            .expiresAt(Instant.parse("2031-01-01T00:00:00Z"))
            .claim("aud", List.of("orders-api"))
            .claim("permissions", permissions)
            .build();
    }
}
~~~

**Điều kiện áp dụng:** WebFlux app cần có đúng `ReactiveJwtAuthenticationConverter` được nối vào SecurityWebFilterChain và endpoint phù hợp. Nếu controller yêu cầu DB hoặc policy khác, phải có test fixture. `@MockitoBean` dùng được trong những dòng Spring Test mới hơn (ví dụ Spring Framework 6.2+); với dự án cũ hơn có thể dùng `@MockBean` của Spring Boot theo version.

Test này chứng minh **Bearer header → WebFilter → mock decoder → reactive converter → authorities → URL authorization**. Nó **không** chứng minh cryptographic signature, timestamp, audience và issuer validators thật vì decoder bị mock. Cần decoder/JWKS test riêng để xác nhận các ràng buộc đó.

### Vì sao mockJwt() chưa đủ chứng minh converter hoạt động?

Spring Security Test cung cấp `mockJwt()` cho WebTestClient:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

webTestClient.mutateWith(mockJwt().authorities(
        new SimpleGrantedAuthority("PERMISSION_orders.read")))
    .get().uri("/api/reports/list")
    .exchange()
    .expectStatus().isOk();
~~~

Đoạn này hữu ích để test **rule authorization** với một Authentication được gắn sẵn. Nhưng nó có thể **bỏ qua cả ReactiveJwtDecoder lẫn ReactiveJwtAuthenticationConverter thật**. Vì vậy:

| Kiểu test | Chứng minh | Chưa chứng minh |
| --- | --- | --- |
| `StepVerifier` gọi `convert(jwt)` | Logic ánh xạ authorities/name | Converter đã được gắn vào WebFilter chain |
| `WebTestClient.mutateWith(mockJwt())` | HTTP/method authorization với Authentication thử nghiệm | Claim mapping và decoder thật |
| `WebTestClient` Bearer header + mock ReactiveJwtDecoder | WebFilter, converter mapping và authorization | Chữ ký/JWKS, issuer/audience/time validation thật |
| Test Bearer JWS ký thật + ReactiveJwtDecoder/JWKS thật | Xác minh token và kết nối WebFlux thực | Quyền nghiệp vụ/DB nếu không có fixture |
| Service/repository integration test | Tenant, owner, sharing, relationship | JWT signature và web filters nếu không gọi HTTP |

Nhóm test khác nhau **bổ sung cho nhau**, không nên thay tất cả bằng một test `mockJwt()` thành công.

## 16. Những lỗi thường gặp khi dùng reactive JWT converter

### “Tôi đã viết bean converter nhưng request vẫn 403”

Có thể bean chưa được gắn bằng `jwt.jwtAuthenticationConverter(...)` cho **SecurityWebFilterChain xử lý endpoint đó**, hoặc bean gắn nhầm vào Servlet `HttpSecurity`. Nếu app có nhiều WebFilter chains, phải kiểm tra matcher và thứ tự.

### “JWT có roles rồi, sao hasRole('ADMIN') không chạy?”

Converter mặc định thường đọc `scope`/`scp`, không tự đọc `roles`. Nếu roles là nested JSON, phải viết converter hiểu schema. `hasRole('ADMIN')` thường tìm `ROLE_ADMIN`, không tìm `ADMIN` hay `SCOPE_admin`.

### “setAuthoritiesClaimName('permissions') làm mất SCOPE_orders.read”

Đúng trong cấu hình chỉ dùng một extractor đổi nguồn claim. Nếu cần giữ cả scope và permissions, phải ghép hai extractor có chủ đích. Đừng tự động cộng mọi claim có tên giống quyền vào cùng một tập không phân biệt nguồn.

### “Tôi gắn ReactiveJwtAuthenticationConverterAdapter và có I/O blocking, có phải đã non-blocking?”

Không. Adapter chỉ chuyển kiểu kết quả sang Reactor; code đọc DB hoặc gọi HTTP đồng bộ vẫn có thể block event-loop. Dùng reactive service thật hoặc tách blocking công việc khỏi event-loop theo kiến trúc cho phép.

### “Tôi có SCOPE_orders.read, sao vẫn bị 403 khi đọc order 123?”

Có thể service yêu cầu owner, tenant membership, sharing hoặc method security khác. **Authority là quyền chức năng**, không đồng nghĩa quyền trên bản ghi cụ thể.

### “Tôi gọi ReactiveSecurityContextHolder.getContext().block() mà không ra Authentication”

`getContext()` đọc context theo subscriber. `block()` tạo subscription riêng và có thể chạy sai ngữ cảnh; WebFlux event-loop cũng không phù hợp với blocking. Compose publisher thay vì block.

### “Tôi dùng tên preferred_username làm owner ID”

Tên người dùng có thể thay đổi/trùng nhau; dùng định danh được issuer xác minh và ánh xạ nội bộ, thường dựa trên `(iss, sub)`, rồi kiểm tra quyền nghiệp vụ.

### “JWT có aud dành cho API khác, nhưng converter vẫn tạo SCOPE_orders.read”

Đó là lý do phải đặt audience/profile validator trong decoder hoặc thành phần xác thực được tin cậy **trước khi convert**. Converter không tự biến sai audience thành hợp lệ và không nên là hàng rào duy nhất chống token nhầm mục đích.

### “Có thể trả toàn bộ authorities và raw token để debug không?”

Không nên. Token là credential, còn claims/authorities có thể chứa thông tin nội bộ. Dùng log được kiểm soát, không lưu Authorization header hoặc chuỗi JWS nguyên vẹn trong metrics/log.

## 17. Khung quyết định cho hệ thống thực tế

| Loại dữ liệu trong JWT | Cách tiếp cận | Điều cần xác định |
| --- | --- | --- |
| `scope` string hoặc `scp` array | `JwtGrantedAuthoritiesConverter` mặc định + reactive adapter | Prefix `SCOPE_`, rule tương ứng |
| `permissions` array string | `setAuthoritiesClaimName("permissions")` + prefix riêng | Schema issuer và quyền nào API chấp nhận |
| `permissions` string phân tách dấu phẩy | Delimiter theo version hoặc converter custom | Regex/delimiter thật của issuer |
| Scope cộng permissions | Delegating converter hoặc Flux merge | Có được phép hợp nhất hai nguồn quyền không? |
| `roles` array top-level | Converter với `ROLE_` khi đúng policy | Scope/role phải kết hợp thế nào |
| `realm_access.roles` | Custom converter đọc nested map | Phạm vi realm roles so với resource |
| `resource_access.orders-api.roles` | Custom converter chọn namespace client/resource | Không lấy roles của resource khác |
| Permissions là array object | Custom converter hiểu schema từng phần tử | Không `toString()` rồi cấp quyền bừa |
| Quyền từ reactive policy service | `Converter<Jwt, Flux<GrantedAuthority>>` | Timeout, fail-closed, tenant, cache, không blocking |
| Converter Servlet cũ cần tái dùng | `ReactiveJwtAuthenticationConverterAdapter` | Logic cũ phải thuần đồng bộ và không I/O blocking |

Trước khi chọn converter, trả lời các câu hỏi:

1. **Token đã được xác minh đủ chưa?** Chữ ký, issuer, audience, thời gian, token type/profile và các claim bắt buộc.
2. **Nguồn claim nào mang quyền hợp lệ cho Orders API?** `scope`, `scp`, `permissions` hay roles cụ thể.
3. **Tên authority mong muốn là gì?** `SCOPE_...`, `PERMISSION_...` hoặc `ROLE_...`; rule phải khớp tên đó.
4. **Có cần gộp nhiều nguồn hay yêu cầu cả hai điều kiện?** Tránh vô tình nâng quyền của client.
5. **Dữ liệu quyền có nằm trong nested JSON không?** Cần parser theo schema, không coi dấu chấm là JSONPath.
6. **Mapper có I/O không?** Nếu có, dùng publisher thật và đánh giá latency/failure, không block event-loop.
7. **Cần kiểm tra quyền đối tượng ở đâu?** Tenant/owner/share thuộc policy nghiệp vụ, không chỉ converter.
8. **Test có bao phủ đường đi thật không?** Unit StepVerifier và WebTestClient Bearer header xác minh những lớp khác nhau.

**Điểm cần nhớ:** `ReactiveJwtAuthenticationConverter` là **cầu nối giữa JWT đã được xác minh và Spring Security Authentication trong WebFlux**. Quyền mặc định thường được ánh xạ từ `scope`/`scp` sang `SCOPE_...`; muốn dùng claims riêng, hãy cấu hình `JwtGrantedAuthoritiesConverter` cùng `ReactiveJwtGrantedAuthoritiesConverterAdapter`, hoặc viết `Converter<Jwt, Flux<GrantedAuthority>>` theo schema rõ ràng. **Ánh xạ đúng không thay thế xác minh token và không tự cấp quyền trên từng tenant hay tài nguyên nghiệp vụ**.
