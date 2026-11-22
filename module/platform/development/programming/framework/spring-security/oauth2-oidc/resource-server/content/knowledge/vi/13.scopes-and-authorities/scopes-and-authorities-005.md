# JwtGrantedAuthoritiesConverter và tùy chỉnh nguồn claims

Trong **Spring Security OAuth 2.0 Resource Server**, sau khi JWT access token được giải mã và xác minh, ứng dụng cần chuyển thông tin quyền trong JWT thành các đối tượng **`GrantedAuthority`** để áp dụng quy tắc như `hasAuthority("SCOPE_orders.read")`, `hasRole("ADMIN")` hoặc `@PreAuthorize(...)`. Thành phần mặc định thường làm công việc này là **`JwtGrantedAuthoritiesConverter`**.

Một Authorization Server có thể phát hành access token với `scope` dạng chuỗi, `scp` dạng mảng, `permissions` do tổ chức định nghĩa hoặc các vai trò nằm trong một JSON object lồng nhau. Những định dạng đó không tự nhiên trở thành cùng một tập authority. Resource Server phải hiểu **nguồn claim nào đáng tin**, **claim có kiểu dữ liệu gì**, **tên authority cần đặt ra sao** và **bộ converter có thực sự được gắn vào chuỗi xác thực đang chạy hay chưa**.

Bài này tập trung vào cách `JwtGrantedAuthoritiesConverter` hoạt động, các tùy chọn đổi nguồn claim/tiền tố/tách chuỗi theo phiên bản Spring Security, cách kết hợp nhiều nguồn quyền và cách xử lý nested claims trong JWT cho một API Servlet Resource Server.

## 1. Từ access token đến `GrantedAuthority` trong Spring Security

Giả sử Orders API nhận request:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <access-token>
~~~

Client gửi **access token** do Authorization Server cấp. Resource Server trước hết phải xác thực token, sau đó mới áp dụng quyền.

~~~mermaid
flowchart TD
    A["Client gửi Bearer JWT"] --> B["BearerTokenAuthenticationFilter"]
    B --> C["JwtAuthenticationProvider"]
    C --> D["JwtDecoder / NimbusJwtDecoder"]
    D --> E{"Chữ ký, issuer, exp, aud, profile hợp lệ?"}
    E -- "Không" --> F["Từ chối xác thực: thường 401"]
    E -- "Có" --> G["JwtAuthenticationConverter"]
    G --> H["JwtGrantedAuthoritiesConverter / custom Converter"]
    H --> I["GrantedAuthority collection"]
    I --> J["JwtAuthenticationToken"]
    J --> K["SecurityContext"]
    K --> L{"Authorization: đủ quyền?"}
    L -- "Không" --> M["Từ chối quyền: thường 403"]
    L -- "Có" --> N["Controller / Service"]
~~~

Các lớp có trách nhiệm khác nhau:

| Thành phần | Nhiệm vụ |
| --- | --- |
| `JwtDecoder` | Xác minh token, chữ ký và các điều kiện token do ứng dụng cấu hình |
| `Jwt` | Đại diện cho token đã được decoder xử lý, gồm headers và claims |
| `JwtGrantedAuthoritiesConverter` | Chuyển một hoặc một nhóm claim quyền thành `Collection<GrantedAuthority>` |
| `JwtAuthenticationConverter` | Dùng authorities converter và principal name để tạo `AbstractAuthenticationToken`, thường là `JwtAuthenticationToken` |
| `SecurityContext` | Chứa `Authentication` của request sau khi xác thực thành công |
| `AuthorizationFilter` / method security | So khớp authorities với các điều kiện truy cập |

**Một claim không phải authority cho tới khi đã được ánh xạ.** Ví dụ JWT chứa `"roles":["ADMIN"]` không đồng nghĩa Spring Security mặc định đã tạo `ROLE_ADMIN`. Quy tắc `hasRole("ADMIN")` có thể trả 403 dù JWT hợp lệ nếu chưa có converter ánh xạ đúng.

Điểm quan trọng hơn: **converter không thay thế xác thực JWT**. Nó chỉ sử dụng dữ liệu đã được decoder chấp nhận. Chữ ký hợp lệ, issuer đúng, audience đúng và các token validator vẫn phải được duy trì khi tùy chỉnh authorities.

## 2. Mặc định: `scope` hoặc `scp` thành authority có tiền tố `SCOPE_`

Theo cấu hình mặc định thường gặp trong Spring Security Resource Server, `JwtGrantedAuthoritiesConverter` tìm một claim phạm vi quyền thuộc những tên quen thuộc, thường là **`scope`** hoặc **`scp`**.

Ví dụ access token mang:

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "exp": 1893456000,
  "scope": "orders.read orders.write"
}
~~~

Spring Security thường chuyển:

~~~text
JWT claim:
scope = "orders.read orders.write"

JwtGrantedAuthoritiesConverter:
"orders.read"  -> SimpleGrantedAuthority("SCOPE_orders.read")
"orders.write" -> SimpleGrantedAuthority("SCOPE_orders.write")
~~~

Với `scp` dạng JSON array:

~~~json
{
  "scp": ["orders.read", "orders.export"]
}
~~~

Kết quả tương ứng có thể là:

~~~text
SCOPE_orders.read
SCOPE_orders.export
~~~

Các điểm cần nhớ:

- Tiền tố mặc định thường là **`SCOPE_`**, vì vậy kiểm tra bằng `hasAuthority("SCOPE_orders.read")` chứ không phải `hasAuthority("orders.read")`.
- Chuỗi `scope` thường là các scope ngăn bằng **dấu cách** theo mô hình OAuth 2.0.
- Nếu claim dùng array, mỗi phần tử hợp lệ thường tương ứng một tên scope.
- Nếu JWT không có claim quyền mà converter nhận diện, kết quả thường là **tập authorities rỗng**.
- Nếu token có cả `scope` và `scp`, không nên giả định converter tự động **gộp hai claim**. Cách chọn tên claim phụ thuộc thứ tự và cơ chế dò tìm của converter. Nếu nghiệp vụ cần gộp, hãy cấu hình tường minh.

Một payload có `"permissions": ["orders.read"]` hoặc `"roles": ["ADMIN"]` sẽ **không tự được ánh xạ** bởi converter chỉ đang đọc `scope`/`scp` mặc định.

### Scope và authority không phải hai khái niệm đồng nhất

**Scope** là dữ liệu mang ý nghĩa quyền được Authorization Server cấp trong bối cảnh OAuth 2.0. **GrantedAuthority** là đối tượng mà Spring Security dùng để so khớp các chính sách phân quyền trong ứng dụng.

Resource Server có thể biến scope thành authority, nhưng cũng có thể tạo authority từ roles, permissions hoặc các claim đã được thẩm định. Bản thân `SCOPE_` chỉ là **quy ước đặt tên**. Nó không chứng minh người dùng sở hữu một bản ghi cụ thể hay tự động cho phép truy cập mọi tenant.

## 3. Các tùy chọn của `JwtGrantedAuthoritiesConverter`

Những phương thức thường dùng:

| API | Mục đích | Ví dụ |
| --- | --- | --- |
| `setAuthoritiesClaimName(String)` | Chỉ định claim mang quyền thay vì mặc định dò `scope`/`scp` | `"permissions"` |
| `setAuthorityPrefix(String)` | Đổi tiền tố tạo authority | `"PERMISSION_"`, `"ROLE_"` hoặc `""` |
| `setAuthoritiesClaimDelimiter(String)` | Đổi biểu thức chính quy tách chuỗi claim | `","` hoặc `"\\s+"` |

**Lưu ý phiên bản:** `setAuthoritiesClaimDelimiter(...)` được bổ sung từ các dòng Spring Security mới hơn (ví dụ Spring Security 6.1). Không nên sao chép cách gọi này vào một phiên bản cũ chưa có API. Nếu dependency không hỗ trợ, bạn có thể nâng cấp phù hợp hoặc sử dụng `Converter<Jwt, Collection<GrantedAuthority>>` tùy chỉnh để tách chuỗi theo quy ước của issuer.

### 3.1. Đổi nguồn sang claim `permissions`

Giả sử issuer phát hành:

~~~json
{
  "sub": "user-42",
  "aud": ["orders-api"],
  "permissions": ["orders.read", "orders.export"]
}
~~~

Ta muốn tạo các authority `PERMISSION_orders.read` và `PERMISSION_orders.export`.

~~~java
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

JwtGrantedAuthoritiesConverter permissions =
    new JwtGrantedAuthoritiesConverter();

permissions.setAuthoritiesClaimName("permissions");
permissions.setAuthorityPrefix("PERMISSION_");
~~~

Khi được sử dụng để chuyển JWT, converter trên đọc **`permissions`**, không còn mặc định đọc `scope` như trước. Một API có thể kiểm tra:

~~~java
.requestMatchers("/api/reports/**")
    .hasAuthority("PERMISSION_orders.export")
~~~

Đây là quyết định về **hợp đồng giữa issuer và API**. Không nên đổi sang tên claim khác chỉ vì tên đó trông gần giống “quyền”; cần hiểu giá trị ấy thực sự được Authorization Server cấp theo chính sách nào.

### 3.2. Đổi tiền tố cho claim chứa vai trò

Nếu issuer cung cấp:

~~~json
{
  "roles": ["ADMIN", "SUPPORT"]
}
~~~

thì có thể cấu hình:

~~~java
JwtGrantedAuthoritiesConverter roles =
    new JwtGrantedAuthoritiesConverter();
roles.setAuthoritiesClaimName("roles");
roles.setAuthorityPrefix("ROLE_");
~~~

Kết quả mong muốn:

~~~text
ROLE_ADMIN
ROLE_SUPPORT
~~~

Những authority này tương thích với biểu thức:

~~~java
hasRole("ADMIN")
~~~

vì `hasRole("ADMIN")` trong cấu hình Spring Security thông dụng kiểm tra authority có tiền tố `ROLE_`. **Không nên viết `hasRole("ROLE_ADMIN")` theo thói quen**: ở nhiều API biểu thức, `hasRole` tự thêm tiền tố và có thể từ chối đối số đã có prefix. Nếu cần kiểm tra tên đầy đủ, dùng `hasAuthority("ROLE_ADMIN")`.

**Đổi prefix không biến role thành scope.** Các giá trị `ROLE_ADMIN` và `SCOPE_admin` chỉ tương đương nếu chính sách của ứng dụng chủ động định nghĩa tương đương, điều này thường không nên làm một cách ngầm định.

### 3.3. Đổi delimiter cho claim chuỗi

Ví dụ một issuer dùng claim:

~~~json
{
  "permissions": "orders.read,orders.write,orders.export"
}
~~~

Nếu phiên bản Spring Security cung cấp `setAuthoritiesClaimDelimiter(...)`, có thể:

~~~java
JwtGrantedAuthoritiesConverter permissions =
    new JwtGrantedAuthoritiesConverter();
permissions.setAuthoritiesClaimName("permissions");
permissions.setAuthorityPrefix("PERMISSION_");
permissions.setAuthoritiesClaimDelimiter(",");
~~~

Khi đó chuỗi được tách bằng dấu phẩy. Trong nhiều phiên bản, delimiter là **biểu thức chính quy (regex)**, vì vậy phải chú ý ký tự đặc biệt. Với chuỗi phân tách bằng một hoặc nhiều khoảng trắng:

~~~java
permissions.setAuthoritiesClaimDelimiter("\\s+");
~~~

Đối với **array** `["orders.read","orders.write"]`, converter thường đọc các phần tử theo collection và không cần tách string bằng delimiter. Nếu issuer phát claim là mảng đối tượng như `[{"name":"orders.read"}]`, `JwtGrantedAuthoritiesConverter` đơn giản không phải là lựa chọn thích hợp; cần converter riêng có kiểm tra kiểu dữ liệu.

Đặc biệt, hãy phân biệt delimiter của chuỗi quyền tùy chỉnh với định dạng chuẩn của scope trong OAuth 2.0: không nên tự coi dấu phẩy là delimiter chuẩn của `scope` nếu Authorization Server không phát hành theo quy ước ấy.

## 4. Gắn converter vào `JwtAuthenticationConverter`

Tạo một `JwtGrantedAuthoritiesConverter` là **chưa đủ**: phải đưa nó vào `JwtAuthenticationConverter`, rồi gắn converter kết quả cho phần cấu hình Resource Server đang xử lý request.

Ví dụ Spring Boot Servlet API nhận `permissions`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfiguration {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter authorities =
            new JwtGrantedAuthoritiesConverter();
        authorities.setAuthoritiesClaimName("permissions");
        authorities.setAuthorityPrefix("PERMISSION_");

        JwtAuthenticationConverter authenticationConverter =
            new JwtAuthenticationConverter();
        authenticationConverter.setJwtGrantedAuthoritiesConverter(authorities);
        return authenticationConverter;
    }

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            JwtAuthenticationConverter jwtAuthenticationConverter
    ) throws Exception {
        return http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers("/api/reports/**")
                    .hasAuthority("PERMISSION_orders.export")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt ->
                jwt.jwtAuthenticationConverter(jwtAuthenticationConverter)))
            .build();
    }
}
~~~

Lưu ý:

1. `jwtAuthenticationConverter(...)` là chỗ **gắn** converter vào JWT Resource Server DSL.
2. `setJwtGrantedAuthoritiesConverter(...)` thay nguồn authority mặc định cho `JwtAuthenticationConverter` đó; nếu chỉ đọc `permissions` thì `scope`/`scp` có thể không còn được chuyển thành authority.
3. `hasAuthority(...)` phải sử dụng **đúng tên sau mapping**. Nếu prefix là `PERMISSION_` mà rule vẫn đòi `SCOPE_`, request có thể bị từ chối với 403.
4. Ví dụ tắt CSRF phù hợp khi API chỉ dùng **Bearer token**, không dựa vào cookie xác thực tự động do browser gửi. Với ứng dụng có session/cookie, cần thiết kế bảo vệ CSRF tương ứng.
5. Converter chỉ giải quyết **quyền được ánh xạ từ JWT**. API vẫn phải kiểm tra người dùng có được thao tác trên đúng tài nguyên hay không.

Configuration thường có JWT issuer:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

`issuer-uri` giúp thiết lập nguồn phát hành đáng tin cậy theo cơ chế hỗ trợ của Spring Security. Khi dùng custom decoder, vẫn phải kiểm tra chữ ký, issuer, audience, thời hạn và các claim/profile cần thiết. **Tùy chỉnh authorities không thay thế validator audience**.

## 5. Tùy chỉnh principal name là việc riêng

`JwtAuthenticationConverter` thường đặt tên principal dựa trên `sub` của JWT. Đổi nguồn authority sang `permissions` **không đồng thời** đổi tên principal.

Ví dụ issuer cung cấp:

~~~json
{
  "sub": "e18d76f1",
  "preferred_username": "alice",
  "permissions": ["orders.read"]
}
~~~

Nếu cần tên hiển thị đăng nhập là `preferred_username`:

~~~java
JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
converter.setJwtGrantedAuthoritiesConverter(permissions);
converter.setPrincipalClaimName("preferred_username");
~~~

Khi đó `Authentication.getName()` có thể dựa trên `preferred_username`. Nhưng việc đổi `getName()` **không thay đổi định danh bất biến của chủ thể**. Với logic quyền sở hữu bản ghi, nên dùng một định danh ổn định, được issuer bảo đảm và được ràng buộc với issuer/tenant; username hiển thị có thể thay đổi hoặc trùng nhau.

Trong một hệ thống nhiều issuer, chỉ lấy `sub` mà bỏ qua `iss` cũng có nguy cơ trùng định danh. Danh tính ở mức hệ thống nên được định nghĩa theo phạm vi tin cậy phù hợp, thay vì coi mọi `sub` trên toàn thế giới là duy nhất.

## 6. Kết hợp hai nguồn: giữ scope và bổ sung permissions

Một yêu cầu phổ biến là:

- Giữ `scope`/`scp` để dùng các rule `SCOPE_orders.read`.
- Đồng thời đọc `permissions` để dùng `PERMISSION_orders.export`.

Nếu chỉ gọi `setAuthoritiesClaimName("permissions")`, converter mới thường **thay thế** nguồn quyền mặc định. Muốn giữ cả hai, có thể dùng **`DelegatingJwtGrantedAuthoritiesConverter`** trong những phiên bản có API này.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.authentication.DelegatingJwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    // Đọc scope/scp bằng quy ước mặc định.
    JwtGrantedAuthoritiesConverter scopes =
        new JwtGrantedAuthoritiesConverter();

    // Đọc claim permissions riêng của issuer.
    JwtGrantedAuthoritiesConverter permissions =
        new JwtGrantedAuthoritiesConverter();
    permissions.setAuthoritiesClaimName("permissions");
    permissions.setAuthorityPrefix("PERMISSION_");

    DelegatingJwtGrantedAuthoritiesConverter allAuthorities =
        new DelegatingJwtGrantedAuthoritiesConverter(
            scopes,
            permissions
        );

    JwtAuthenticationConverter authentication =
        new JwtAuthenticationConverter();
    authentication.setJwtGrantedAuthoritiesConverter(allAuthorities);
    return authentication;
}
~~~

Giả sử JWT có:

~~~json
{
  "scope": "orders.read",
  "permissions": ["orders.export"]
}
~~~

Kết quả:

~~~text
SCOPE_orders.read
PERMISSION_orders.export
~~~

`DelegatingJwtGrantedAuthoritiesConverter` có nhiệm vụ gọi các converters thành phần rồi tập hợp authorities; ở những phiên bản có hỗ trợ, cơ chế này giúp giảm trùng lặp authority và giữ thứ tự hữu ích cho việc đọc/debug. Tuy nhiên, **đừng dựa vào thứ tự authorities để quyết định quyền**. Bản chất quyền là việc tên authority có xuất hiện trong tập hay không.

Nếu dự án chưa có `DelegatingJwtGrantedAuthoritiesConverter`, có thể tự viết một `Converter<Jwt, Collection<GrantedAuthority>>` ghép kết quả từ hai converter bằng `LinkedHashSet`; cần xử lý kết quả null/rỗng theo contract của từng converter.

### Cần giữ nguyên quan hệ quyền được cấp

Không phải cứ có hai claim là nên hợp nhất chúng. Ví dụ `scope` thể hiện quyền OAuth 2.0 đã cấp cho một **client cụ thể**, còn `roles` có thể mô tả vai trò nội bộ của người dùng. Nếu API tự lấy **toàn bộ vai trò của người dùng** rồi cho client mọi quyền tương ứng, có thể vô tình bỏ qua giới hạn scope mà Authorization Server định cấp.

Một API có thể cần cả hai điều kiện:

~~~text
Access token có SCOPE_orders.write
                 VÀ
Chủ thể có ROLE_ORDER_EDITOR
                 VÀ
Được sửa đúng order/tenant này
~~~

Khi thiết kế, hãy xác định rõ một quyền có thể **mở rộng** quyền được cấp cho client hay chỉ là một điều kiện **bổ sung** phải thỏa. Không nên gộp tùy ý để một vai trò mạnh có thể vượt qua giới hạn của access token.

## 7. Khi quyền nằm trong JSON object lồng nhau

Một số issuer (ví dụ cấu hình kiểu Keycloak) có thể cung cấp claims như:

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
    "payments-api": {
      "roles": ["PAYMENT_VIEWER"]
    }
  }
}
~~~

Ở đây `realm_access` và `resource_access` là **JSON objects**, không phải chuỗi scope. `JwtGrantedAuthoritiesConverter.setAuthoritiesClaimName("realm_access.roles")` **không mặc nhiên có nghĩa** truy cập đường dẫn lồng nhau. Với converter thông thường, tên claim được tìm ở **cấp claim trực tiếp**; dấu chấm không có ý nghĩa JSONPath.

Để đọc nested claims, dùng một `Converter<Jwt, Collection<GrantedAuthority>>` riêng. Ví dụ sau:

- Giữ quyền mặc định từ `scope`/`scp`.
- Đọc vai trò cấp realm tại `realm_access.roles`.
- Chỉ đọc vai trò dành cho **`orders-api`** tại `resource_access["orders-api"].roles`.
- Giới hạn các authority được tạo vào những tên mà policy API chấp nhận.

~~~java
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

public final class OrdersAuthoritiesConverter
        implements Converter<Jwt, Collection<GrantedAuthority>> {

    private static final String ORDERS_RESOURCE = "orders-api";

    private static final Set<String> SUPPORTED_ROLES =
        Set.of("USER", "REPORT_VIEWER", "ORDER_EDITOR");

    private final JwtGrantedAuthoritiesConverter scopes =
        new JwtGrantedAuthoritiesConverter();

    @Override
    public Collection<GrantedAuthority> convert(Jwt jwt) {
        Set<GrantedAuthority> result = new LinkedHashSet<>();

        Collection<GrantedAuthority> scopeAuthorities = scopes.convert(jwt);
        if (scopeAuthorities != null) {
            result.addAll(scopeAuthorities);
        }

        Object realmAccess = jwt.getClaim("realm_access");
        if (realmAccess instanceof Map<?, ?> realm) {
            addRoles(result, realm.get("roles"));
        }

        Object resourceAccess = jwt.getClaim("resource_access");
        if (resourceAccess instanceof Map<?, ?> resources) {
            Object orders = resources.get(ORDERS_RESOURCE);
            if (orders instanceof Map<?, ?> ordersClaims) {
                addRoles(result, ordersClaims.get("roles"));
            }
        }
        return result;
    }

    private static void addRoles(
            Set<GrantedAuthority> authorities,
            Object rawRoles) {

        if (!(rawRoles instanceof Collection<?> roles)) {
            return;
        }
        for (Object value : roles) {
            if (value instanceof String role
                    && SUPPORTED_ROLES.contains(role)) {
                authorities.add(
                    new SimpleGrantedAuthority("ROLE_" + role));
            }
        }
    }
}
~~~

Converter này có thể được gắn bằng:

~~~java
@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();
    converter.setJwtGrantedAuthoritiesConverter(
        new OrdersAuthoritiesConverter());
    return converter;
}
~~~

Ví dụ trên **cố ý không** đưa `PAYMENT_VIEWER` từ `payments-api` vào authorities của Orders API. Ngoài ra, danh sách `SUPPORTED_ROLES` minh họa một cách giới hạn vai trò mà API hiểu. Tên thực tế phải theo quyền đã được thiết kế và issuer phát hành.

**Lưu ý bảo mật:** Role cấp realm có thể áp dụng rộng hơn một resource; việc ánh xạ `ROLE_ORDER_EDITOR` từ một nguồn rộng như vậy là quyết định cần xem kỹ. Khi cần giới hạn theo client/resource, chỉ ánh xạ vai trò đúng namespace và đặt rule đòi scope phù hợp. Không coi sự hiện diện của vai trò trong JWT là bằng chứng chủ thể được thao tác trên mọi tài khoản hoặc tenant.

## 8. Chuyển claim có cấu trúc không phải mảng string

Một JWT có thể mang dạng:

~~~json
{
  "permissions": [
    {"resource": "orders", "action": "read"},
    {"resource": "orders", "action": "export"}
  ]
}
~~~

Đây là **mảng JSON object**. Cách xử lý `JwtGrantedAuthoritiesConverter` đơn giản có thể không phù hợp vì phần tử không phải tên quyền dạng string. Nếu hợp đồng thật sự dùng cấu trúc như vậy, converter tùy chỉnh phải kiểm tra kiểu và **tạo authority theo quy tắc có chủ đích**:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;

public static Collection<GrantedAuthority> mapStructuredPermissions(Jwt jwt) {
    Object raw = jwt.getClaim("permissions");
    List<GrantedAuthority> result = new ArrayList<>();

    if (!(raw instanceof Collection<?> entries)) {
        return result;
    }

    for (Object entry : entries) {
        if (!(entry instanceof Map<?, ?> permission)) {
            continue;
        }

        Object resource = permission.get("resource");
        Object action = permission.get("action");

        if ("orders".equals(resource) && "read".equals(action)) {
            result.add(new SimpleGrantedAuthority("PERMISSION_orders.read"));
        } else if ("orders".equals(resource)
                && "export".equals(action)) {
            result.add(new SimpleGrantedAuthority("PERMISSION_orders.export"));
        }
    }
    return result;
}
~~~

Ví dụ chỉ chấp nhận **các cặp quyền đã biết** và bỏ qua cấu trúc không đúng hợp đồng. Với hệ thống thực tế, nên xác định cách xử lý dữ liệu malformed rõ ràng: một số chính sách cần **từ chối cả token** thay vì lặng lẽ bỏ qua quyền không hợp lệ. Quyết định này thuộc thiết kế bảo mật của Resource Server, không phải chức năng tự động của converter mặc định.

### Đừng dùng `toString()` cho mọi phần tử

Nếu code chuyển một object thành string rồi thêm prefix, nó có thể sinh authority như:

~~~text
PERMISSION_{resource=orders, action=read}
~~~

Đây không phải quyền nghiệp vụ đã định nghĩa và có thể gây lỗi phân quyền khó chẩn đoán. Một claim cần được hiểu **theo schema** do issuer/API thống nhất, không phải bằng cách gọi `String.valueOf(...)` một cách tùy tiện.

## 9. `hasAuthority`, `hasRole` và method security sau mapping

Giả sử converter tạo:

~~~text
SCOPE_orders.read
SCOPE_orders.write
ROLE_ORDER_EDITOR
PERMISSION_orders.export
~~~

Có thể bảo vệ endpoint bằng:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders/**")
        .hasAuthority("SCOPE_orders.write")
    .requestMatchers(HttpMethod.GET, "/api/reports/export")
        .hasAuthority("PERMISSION_orders.export")
    .anyRequest().authenticated())
~~~

Chú ý **thứ tự request matcher**: nếu rule tổng quát GET `/api/orders/**` đứng trước rule GET cụ thể có yêu cầu chặt hơn trong cùng phạm vi, rule cụ thể có thể không bao giờ được xét. Hãy viết matcher theo mức độ đặc hiệu phù hợp.

Nếu muốn kết hợp scope và role trong cùng một điều kiện, có thể sử dụng method security:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class OrderApplicationService {

    @PreAuthorize(
        "hasAuthority('SCOPE_orders.write') and hasRole('ORDER_EDITOR')")
    public void updateOrder(String orderId) {
        // Ngoài rule trên, service cần kiểm tra tenant và quyền trên orderId.
    }
}
~~~

Để sử dụng `@PreAuthorize`, ứng dụng phải bật method security theo phiên bản tương ứng, ví dụ:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Rule `hasRole('ORDER_EDITOR')` thường tìm authority `ROLE_ORDER_EDITOR`. Nếu converter của bạn tạo `APP_ROLE_ORDER_EDITOR`, biểu thức phải được điều chỉnh để dùng đúng tên quyền.

**Quan trọng:** dù đã kiểm tra `SCOPE_orders.write` và `ROLE_ORDER_EDITOR`, service vẫn phải xác minh chủ thể có quyền **sửa đúng orderId thuộc đúng tenant**. Đây là kiểm tra quyền ở mức đối tượng (object-level authorization), không thể suy ra chỉ từ authorities toàn cục.

## 10. Sự khác biệt giữa claim conversion và token validation

Một Resource Server có thể gặp các lỗi khác nhau:

| Trường hợp | Tầng liên quan | Hành vi thường gặp |
| --- | --- | --- |
| JWT hết hạn hoặc chữ ký sai | Decoder/validators | Xác thực thất bại, thường **401** |
| JWT phát hành cho audience khác | Audience validation | Phải từ chối ở tầng xác thực theo chính sách API |
| JWT hợp lệ nhưng không có `scope`/`permissions` mà rule yêu cầu | Authority mapping + authorization | Converter tạo ít/không có authority; rule thường trả **403** |
| JWT có `permissions` dạng string nhưng converter kỳ vọng dạng khác | Claim mapping | Không có authority đúng; có thể lỗi mapping tùy implementation |
| JWT có `roles` nhưng converter chỉ đọc `scope` | Authority mapping | `hasRole(...)` thường trả **403** |
| JWT có authority phù hợp nhưng user không sở hữu bản ghi | Business authorization | Thường **403** hoặc phản hồi nghiệp vụ được thiết kế |

**Không giải quyết một lỗi 403 do mapping bằng cách tắt kiểm tra chữ ký hoặc bỏ audience validator.** Hãy kiểm tra sau khi xác thực token xem `Authentication.getAuthorities()` chứa những authority nào, và so với tên được rule yêu cầu.

Về mặt bảo mật:

- **Issuer:** chỉ nhận token do nguồn đã được cấu hình tin cậy phát hành.
- **Audience:** chỉ nhận access token dành cho API này.
- **Thời hạn, loại token:** `exp`, `nbf`, các claim bắt buộc và profile phù hợp.
- **Authorities:** chuyển đúng claim theo hợp đồng, không tùy ý mở rộng quyền.
- **Business policy:** giới hạn thao tác đến đúng bản ghi, tenant và ngữ cảnh.

Tầng JWT authority mapping phải chạy **sau** việc token được xác minh theo contract decoder. Đọc payload bằng Base64URL rồi xây authorities từ JSON chưa xác thực là **không an toàn**.

## 11. Khi claim là OIDC ID token hay token của issuer khác

OIDC ID token có thể mang `roles`, `groups` hoặc claim tùy chỉnh. Tuy nhiên **ID token dùng cho OIDC client để xác thực người dùng**; nó **không** tự động là access token hợp lệ cho Resource Server.

Ví dụ cùng một issuer cấp:

- **ID token** với `aud` là client đăng nhập `orders-web`.
- **Access token** với `aud` là `orders-api` và scope `orders.read`.

Resource Server phải kiểm tra access token đúng audience/profile. Không nên nhận ID token rồi ánh xạ `groups` thành authority API chỉ vì ID token có chữ ký hợp lệ.

Một hệ thống nhiều issuer cũng có thể có hai claim cùng tên `roles` nhưng ý nghĩa khác nhau. Issuer A định nghĩa `ADMIN` là quản trị đơn hàng; issuer B dùng `ADMIN` cho quản trị giao diện của ứng dụng khác. Không thể gộp chúng thành một `ROLE_ADMIN` toàn hệ thống mà thiếu chính sách phân biệt issuer/audience/tenant.

Khi cần nhiều issuer, các cơ chế như `AuthenticationManagerResolver<HttpServletRequest>` hoặc nhiều `SecurityFilterChain` có thể được thiết kế theo allowlist và hợp đồng token. Mỗi nhánh nên có decoder, validators và converter riêng nếu schema quyền khác nhau. Không tin bất kỳ `iss` hoặc JWKS URL chưa xác minh do token tự khai báo.

## 12. Các lỗi thường gặp khi tùy chỉnh nguồn authority

### Lỗi 1: Tạo converter nhưng không gắn vào Resource Server

~~~java
// Chỉ tạo bean hoặc object mà không liên kết vào jwtAuthenticationConverter
// của SecurityFilterChain áp dụng cho endpoint.
JwtGrantedAuthoritiesConverter converter =
    new JwtGrantedAuthoritiesConverter();
converter.setAuthoritiesClaimName("permissions");
~~~

Hãy bảo đảm `JwtAuthenticationConverter` sử dụng converter đó và Resource Server DSL gọi `jwtAuthenticationConverter(...)` cho đúng filter chain. Nếu ứng dụng có nhiều chain, một converter của chain A không tự áp dụng cho chain B.

### Lỗi 2: Đổi claim nguồn rồi mất scope

Khi chuyển từ mặc định `scope` sang `permissions`, scope authorities có thể biến mất. Nếu cần cả hai, dùng `DelegatingJwtGrantedAuthoritiesConverter` hoặc custom converter rõ ràng.

### Lỗi 3: Cấu hình prefix nhưng rule không đổi

Converter tạo `PERMISSION_orders.read`, nhưng rule vẫn kiểm tra `SCOPE_orders.read`. Token hợp lệ vẫn bị 403 vì Spring Security so tên authority **chính xác**, không tự suy luận quan hệ giữa hai tiền tố.

### Lỗi 4: Coi nested claim là dot path

`setAuthoritiesClaimName("realm_access.roles")` không phải JSONPath. Với `realm_access` là object chứa `roles`, cần converter đọc cấu trúc map và collection.

### Lỗi 5: Không xem kiểu JSON thực tế

Issuer có thể phát:

~~~json
{
  "scope": "orders.read orders.write",
  "scp": ["orders.read"],
  "roles": ["USER"],
  "permissions": [{"name": "orders.export"}]
}
~~~

Không thể áp dụng một quy tắc ép kiểu đơn giản cho tất cả. Định nghĩa schema và mapping cho từng claim, xử lý dữ liệu không đúng kiểu theo chính sách.

### Lỗi 6: Tự chuyển mọi role thành quyền của client

Claim `roles` ở cấp người dùng có thể bao trùm nhiều ứng dụng. Nếu client chỉ được cấp `orders.read`, việc biến role `ADMIN` thành quyền xóa đơn hàng có thể vượt ngoài scope dự kiến. Nên thiết kế rule kết hợp scope và quyền nghiệp vụ, phân biệt role cấp realm và role dành riêng cho resource.

### Lỗi 7: Nhầm `ROLE_` và `SCOPE_`

`hasRole("ADMIN")` thường đi với `ROLE_ADMIN`. `hasAuthority("SCOPE_admin")` đi với authority đúng tên `SCOPE_admin`. Đây là hai namespace quyền khác nhau và không tự thay thế cho nhau.

### Lỗi 8: Debug bằng cách ghi JWT vào log

Bearer access token là thông tin có thể được sử dụng để gọi API. Không ghi nguyên token, authorization header hoặc dữ liệu nhạy cảm từ claims vào log. Khi chẩn đoán, có thể ghi request ID, issuer đã được xác minh, nhóm lỗi và tên authorities cần thiết ở mức phù hợp.

## 13. Kiểm thử converter đúng lớp

Một converter có thể được kiểm thử trực tiếp mà không cần HTTP server. Ví dụ kiểm tra `permissions`:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Collection;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

class JwtGrantedAuthoritiesConverterTest {

    @Test
    void mapsPermissionsFromChosenClaim() {
        Jwt jwt = Jwt.withTokenValue("unit-test-only")
            .header("alg", "RS256")
            .subject("user-42")
            .claim("permissions", List.of("orders.read", "orders.export"))
            .claim("scope", "payments.write")
            .build();

        JwtGrantedAuthoritiesConverter converter =
            new JwtGrantedAuthoritiesConverter();
        converter.setAuthoritiesClaimName("permissions");
        converter.setAuthorityPrefix("PERMISSION_");

        Collection<GrantedAuthority> granted = converter.convert(jwt);
        List<String> names = granted.stream()
            .map(GrantedAuthority::getAuthority)
            .toList();

        assertTrue(names.contains("PERMISSION_orders.read"));
        assertTrue(names.contains("PERMISSION_orders.export"));
        assertFalse(names.contains("SCOPE_payments.write"));
    }
}
~~~

Test cho thấy **đổi nguồn claim có tác dụng**: `scope` không được ánh xạ khi converter đã được yêu cầu chỉ đọc `permissions`. Dữ liệu `Jwt` tạo bằng `withTokenValue(...)` là đối tượng unit test, **không phải JWT có chữ ký được xác minh**.

Một bài kiểm thử tích hợp cần xác minh thêm:

1. Token thật được ký bằng khóa thử nghiệm mà `JwtDecoder` tin cậy.
2. Token phải đúng issuer, audience, thời hạn và profile được API chấp nhận.
3. `SecurityFilterChain` sử dụng đúng `JwtAuthenticationConverter`.
4. Request với authority đủ quyền được chuyển tới endpoint, request thiếu quyền bị từ chối phù hợp.
5. Dữ liệu sai kiểu hoặc claim không được issuer cho phép không trở thành authority ngoài mong muốn.

Các helper như `jwt()` trong **Spring Security Test MockMvc** hữu ích để kiểm tra authorization với Authentication giả lập, nhưng thường **bỏ qua JwtDecoder thật và bước chuyển claim trong chuỗi Resource Server**. Vì thế, mock `jwt()` trực tiếp tạo authorities không chứng minh `JwtGrantedAuthoritiesConverter` đã được nối đúng trong production.

## 14. Quyết định chọn nguồn quyền theo từng mô hình

| Mô hình token | Cách ánh xạ thường phù hợp | Điểm cần bảo đảm |
| --- | --- | --- |
| `scope` chuỗi hoặc `scp` mảng | Converter mặc định | Quy tắc kiểm tra `SCOPE_...` nhất quán với scope issuer cấp |
| `permissions` là mảng string | `setAuthoritiesClaimName("permissions")`, prefix riêng | Schema quyền rõ ràng, rule dùng đúng prefix |
| `roles` là mảng string cấp trực tiếp | Converter với `ROLE_` nếu đúng chính sách | Không bỏ qua scope và ranh giới client/resource |
| Scope và permissions độc lập | `DelegatingJwtGrantedAuthoritiesConverter` | Quyết định đúng việc gộp hay yêu cầu nhiều điều kiện |
| Nested `realm_access.roles` | Custom converter đọc object | Không coi tên claim có dấu chấm là JSONPath |
| Nested `resource_access[client].roles` | Custom converter chọn namespace resource xác định | Không lấy role của ứng dụng khác |
| `permissions` là mảng object | Custom converter kiểm tra schema và allowlist | Không tự `toString()` cấu trúc bất kỳ |
| Nhiều issuer có claim quyền khác nhau | Mapping riêng theo issuer/chain được tin cậy | Không gộp quyền từ các miền tin cậy khác nhau |

Khi yêu cầu bảo vệ API được thiết kế rõ ràng, hãy trả lời ba câu hỏi: **claim nào thực sự là nguồn quyền đã được cấp**, **tên authority Spring Security phải tạo là gì**, và **rule ở API kiểm tra authority đó kết hợp với quyền trên tài nguyên ra sao**.

## 15. Các điểm cốt lõi cần ghi nhớ

- **`JwtGrantedAuthoritiesConverter`** chuyển scope/claim quyền trong JWT sang `GrantedAuthority` cho Spring Security.
- Mặc định thông dụng: `scope` hoặc `scp` → **`SCOPE_...`**. Không tự lấy mọi claim `roles`/`permissions`.
- `setAuthoritiesClaimName(...)` đổi **nguồn claim**, `setAuthorityPrefix(...)` đổi **tên authority**, `setAuthoritiesClaimDelimiter(...)` đổi **cách tách claim chuỗi** ở phiên bản hỗ trợ.
- Để sử dụng trong Servlet Resource Server, gắn vào **`JwtAuthenticationConverter`**, rồi gắn converter đó vào **JWT Resource Server DSL** của `SecurityFilterChain` thực sự xử lý request.
- Để kết hợp nhiều nguồn, dùng **`DelegatingJwtGrantedAuthoritiesConverter`** nếu có hoặc tự viết `Converter<Jwt, Collection<GrantedAuthority>>`.
- **Nested claims** cần code đọc object/list rõ ràng; dấu chấm trong tên claim không mặc nhiên là JSONPath.
- `SCOPE_`, `PERMISSION_` và `ROLE_` là các quy ước đặt tên riêng; `hasAuthority(...)` và `hasRole(...)` phải khớp chính xác.
- Converter **không thay thế** kiểm tra signature, issuer, audience, thời hạn, token profile và chính sách truy cập bản ghi.
- Nếu token hợp lệ nhưng map sai quyền, triệu chứng điển hình là **403**, còn JWT không hợp lệ ở tầng xác thực thường là **401**.

Thiết kế authority mapping tốt giúp Resource Server hiểu quyền mà Authorization Server đã cấp, nhưng **không tự mở rộng** phạm vi truy cập. Cách tiếp cận bền vững là quy định schema claims giữa issuer và API, ánh xạ có chủ đích, kiểm tra các quyền cần thiết tại endpoint và tiếp tục phân quyền trên từng tài nguyên nghiệp vụ.
