# Ánh xạ scope, role rồi bảo vệ thao tác đọc, sửa theo phương thức HTTP

Một **Spring Security OAuth 2.0 Resource Server** cần chuyển quyền có trong access token thành authorities mà Spring Security hiểu, sau đó dùng các authorities đó để quyết định request nào được phép đọc, tạo, sửa hoặc xóa tài nguyên. Bài thực hành này xây dựng một policy nhất quán: scope biểu thị quyền truy cập API theo hành động, role biểu thị nhóm trách nhiệm rộng hơn, còn HTTP method xác định thao tác đang được yêu cầu.

Ví dụ API quản lý đơn hàng:

| HTTP method | Endpoint | Quyền yêu cầu |
|---|---|---|
| GET | /api/orders hoặc /api/orders/{id} | SCOPE_orders.read |
| POST | /api/orders | SCOPE_orders.write |
| PUT | /api/orders/{id} | SCOPE_orders.write |
| PATCH | /api/orders/{id} | SCOPE_orders.write |
| DELETE | /api/orders/{id} | ROLE_ORDER_ADMIN |

Access token có thể chứa:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "alice",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "roles": ["ORDER_OPERATOR"],
  "exp": 1893459600
}
~~~

Spring Security ánh xạ scope thành SCOPE_... theo mặc định. Claim roles là claim riêng theo contract của issuer, vì vậy ứng dụng cần converter để ánh xạ thành ROLE_.... Sau khi có authorities, request authorization có thể kiểm tra kết hợp HTTP method và path.

> **Nguyên tắc thiết kế:** scope nên cấp quyền cụ thể cho API/action; role nên mô tả trách nhiệm rộng hơn. Chỉ cấp đúng authority cần thiết, và đặt rule theo HTTP method trước rule tổng quát cho path.

## 1. Hiểu scope, role và authority

### 1.1. Scope

OAuth scope là chuỗi quyền được client yêu cầu và Authorization Server cấp theo policy. Với API đơn hàng, issuer có thể phát hành:

~~~text
orders.read
orders.write
~~~

Ý nghĩa cụ thể do API và issuer thống nhất. Một convention dễ hiểu là:

- orders.read cho phép đọc đơn hàng.
- orders.write cho phép tạo hoặc cập nhật đơn hàng.
- orders.cancel nếu nghiệp vụ cần quyền hủy riêng.

Scope nên có phạm vi rõ ràng, tránh scope quá rộng như admin nếu API có thể phân tách hành động cụ thể hơn.

### 1.2. Role

Role mô tả trách nhiệm hoặc nhóm người dùng:

~~~text
ORDER_OPERATOR
ORDER_ADMIN
SUPPORT_AGENT
~~~

Role thường rộng hơn một scope. Ví dụ ORDER_ADMIN có thể được phép xóa đơn hàng; ORDER_OPERATOR có thể được phép tạo và cập nhật. Không nên suy ra mọi quyền từ tên role một cách ngầm định. Hãy định nghĩa rõ role nào được ánh xạ thành authority nào, ở lớp nào.

### 1.3. Authority

Spring Security kiểm tra GrantedAuthority. Chuỗi authority là giá trị ứng dụng dùng trong các biểu thức:

~~~text
SCOPE_orders.read
SCOPE_orders.write
ROLE_ORDER_ADMIN
ROLE_ORDER_OPERATOR
~~~

Tiền tố là convention quan trọng:

- hasAuthority("SCOPE_orders.read") so khớp chính xác chuỗi authority.
- hasRole("ORDER_ADMIN") mặc định kiểm tra authority ROLE_ORDER_ADMIN.
- hasAuthority("ROLE_ORDER_ADMIN") cũng kiểm tra chính xác chuỗi đó.

hasRole("ROLE_ORDER_ADMIN") thường là sai convention vì Spring tự thêm prefix ROLE_; hãy truyền tên role không có prefix vào hasRole, hoặc dùng hasAuthority với chuỗi đầy đủ.

### 1.4. Scope không tự động là role

Không nên trộn hai loại quyền thành một namespace:

~~~text
orders.read       -> SCOPE_orders.read
ORDER_ADMIN       -> ROLE_ORDER_ADMIN
~~~

Điều này giúp policy dễ đọc và tránh việc một scope vô tình thỏa điều kiện role hoặc ngược lại.

## 2. Thỏa thuận claim giữa Authorization Server và Resource Server

Trước khi viết converter, thống nhất schema access token:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "alice",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "roles": ["ORDER_OPERATOR"],
  "exp": 1893459600
}
~~~

Các quyết định cần rõ:

| Claim | Contract cần thống nhất |
|---|---|
| scope | Chuỗi scope phân tách bằng dấu cách hay một mảng |
| scp | Có dùng thay scope hay không |
| roles | Mảng role hay chuỗi; role có/không có prefix |
| aud | Identifier của Resource Server |
| iss | Issuer chính xác mà Resource Server tin cậy |
| sub | Subject người dùng hay service; uniqueness trong phạm vi issuer |

Spring Security mặc định có thể đọc scope từ claim phổ biến scope hoặc scp và thêm prefix SCOPE_. Nếu issuer dùng claim khác như permissions, cấu hình converter rõ ràng. Không tự suy đoán schema dựa trên token của một môi trường.

Không lấy role từ query parameter, request body hoặc header do client tự đặt. Role/scope phải đến từ token đã được Resource Server xác minh chữ ký/issuer/audience/time và các điều kiện tin cậy khác. Converter chỉ chạy trong authentication pipeline; nó không thay thế xác minh token.

## 3. Cấu hình ánh xạ scope mặc định

Spring Security cung cấp JwtGrantedAuthoritiesConverter. Converter này đọc claim scope/scp theo cấu hình, tách các giá trị và tạo authorities có prefix mặc định SCOPE_.

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

Converter<Jwt, Collection<GrantedAuthority>> scopeConverter =
    new JwtGrantedAuthoritiesConverter();
~~~

Với token:

~~~json
{
  "scope": "orders.read orders.write"
}
~~~

Authorities được tạo:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

### 3.1. Tùy chỉnh claim chứa scope

Nếu issuer phát hành quyền trong claim permissions:

~~~json
{
  "permissions": "orders.read orders.write"
}
~~~

có thể cấu hình:

~~~java
JwtGrantedAuthoritiesConverter scopeConverter =
    new JwtGrantedAuthoritiesConverter();

scopeConverter.setAuthoritiesClaimName("permissions");
scopeConverter.setAuthorityPrefix("SCOPE_");
scopeConverter.setAuthoritiesClaimDelimiter(" ");
~~~

setAuthoritiesClaimDelimiter có trong các phiên bản Spring Security hỗ trợ API này. Nếu version của dự án chưa có method đó, dùng converter riêng để tách định dạng claim. Với claim là JSON array, kiểm tra behavior của version hiện tại hoặc tự viết converter nhận Collection; không áp dụng delimiter string cho dữ liệu mảng.

### 3.2. Dùng claim scp dạng mảng

Một issuer có thể phát hành:

~~~json
{
  "scp": ["orders.read", "orders.write"]
}
~~~

Nếu converter mặc định trong version đang dùng không xử lý định dạng claim cụ thể theo contract, tạo converter riêng:

~~~java
Collection<GrantedAuthority> convertScopes(Jwt jwt) {
    Object claim = jwt.getClaims().get("scp");
    if (claim instanceof Collection<?> scopes) {
        return scopes.stream()
            .filter(String.class::isInstance)
            .map(String.class::cast)
            .filter(scope -> !scope.isBlank())
            .map(scope -> new SimpleGrantedAuthority("SCOPE_" + scope))
            .toList();
    }
    return List.of();
}
~~~

Converter phải xử lý kiểu dữ liệu đúng theo schema issuer. Không biến object hoặc nested JSON tùy ý thành quyền.

## 4. Tạo converter ánh xạ role

Giả sử issuer phát hành:

~~~json
{
  "roles": ["ORDER_OPERATOR", "SUPPORT_AGENT"]
}
~~~

Ta muốn tạo:

~~~text
ROLE_ORDER_OPERATOR
ROLE_SUPPORT_AGENT
~~~

Converter:

~~~java
import java.util.Collection;
import java.util.List;

import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;

final class JwtRolesConverter
        implements Converter<Jwt, Collection<GrantedAuthority>> {

    private static final String CLAIM_NAME = "roles";
    private static final String PREFIX = "ROLE_";

    @Override
    public Collection<GrantedAuthority> convert(Jwt jwt) {
        Object claim = jwt.getClaims().get(CLAIM_NAME);
        if (!(claim instanceof Collection<?> roles)) {
            return List.of();
        }

        return roles.stream()
            .filter(String.class::isInstance)
            .map(String.class::cast)
            .map(String::trim)
            .filter(role -> !role.isEmpty())
            .map(JwtRolesConverter::normalizeRole)
            .distinct()
            .map(SimpleGrantedAuthority::new)
            .toList();
    }

    private static String normalizeRole(String role) {
        return role.startsWith(PREFIX) ? role : PREFIX + role;
    }
}
~~~

Ví dụ trên chấp nhận role có hoặc không có prefix và tránh tạo prefix kép. Trong hệ thống production, tốt nhất issuer phát hành role theo một định dạng thống nhất. Nếu contract quy định role luôn không có ROLE_, có thể từ chối giá trị đã chứa prefix thay vì âm thầm chuẩn hóa.

### 4.1. Không tin claim sai kiểu

Nếu roles là object hoặc một chuỗi không đúng schema, converter trả danh sách rỗng. Có thể chọn policy nghiêm ngặt hơn: validator từ chối token khi claim role có kiểu sai. Điều này hữu ích nếu issuer contract bắt buộc claim phải là mảng.

Không cast trực tiếp mà không kiểm tra kiểu:

~~~java
List<String> roles = (List<String>) jwt.getClaim("roles");
~~~

Token có thể chứa kiểu dữ liệu khác, gây ClassCastException và làm authentication thất bại theo cách khó chẩn đoán. Kiểm tra kiểu và xử lý dữ liệu không đúng contract một cách rõ ràng.

### 4.2. Giới hạn số role

Nếu role claim có thể phình to, đặt giới hạn số lượng trước khi tạo authority:

~~~java
private static final int MAX_ROLES = 50;

if (roles.size() > MAX_ROLES) {
    throw new IllegalArgumentException("Too many role values");
}
~~~

Trong một thiết kế hoàn chỉnh, nên kiểm tra claim budget bằng token validator để lỗi được biểu diễn như token invalid trước khi authentication được cấp. Đừng tạo hàng nghìn SimpleGrantedAuthority từ một claim không giới hạn.

## 5. Kết hợp scope và role authorities

Một JWT có thể chứa cả scope và role. Ta cần một converter kết hợp cả hai nguồn:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

final class JwtAuthoritiesConverter
        implements Converter<Jwt, Collection<GrantedAuthority>> {

    private final Converter<Jwt, Collection<GrantedAuthority>> scopes =
        new JwtGrantedAuthoritiesConverter();

    private final Converter<Jwt, Collection<GrantedAuthority>> roles =
        new JwtRolesConverter();

    @Override
    public Collection<GrantedAuthority> convert(Jwt jwt) {
        Set<GrantedAuthority> result = new LinkedHashSet<>();
        Collection<GrantedAuthority> scopeAuthorities =
            this.scopes.convert(jwt);
        Collection<GrantedAuthority> roleAuthorities =
            this.roles.convert(jwt);

        if (scopeAuthorities != null) {
            result.addAll(scopeAuthorities);
        }
        if (roleAuthorities != null) {
            result.addAll(roleAuthorities);
        }
        return new ArrayList<>(result);
    }
}
~~~

Dùng LinkedHashSet để loại duplicate trong khi giữ thứ tự ổn định. Nếu một token có scope/role trùng nhau sau mapping, chỉ cần một authority tương ứng.

### 5.1. Gắn converter vào JwtAuthenticationConverter

~~~java
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;

JwtAuthenticationConverter authenticationConverter =
    new JwtAuthenticationConverter();

authenticationConverter.setJwtGrantedAuthoritiesConverter(
    new JwtAuthoritiesConverter());
~~~

Khi decoder xác minh token thành công, Spring Security dùng converter này để tạo JwtAuthenticationToken cùng authorities đã ánh xạ.

### 5.2. Đặt converter trong Resource Server DSL

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt
        .jwtAuthenticationConverter(authenticationConverter)));
~~~

Converter này chỉ định cách biến claims đã xác minh thành authorities. Nó không xác minh chữ ký, issuer, audience hoặc expiry; các validator và decoder vẫn phải được cấu hình riêng.

## 6. Bảo vệ thao tác theo HTTP method

Giả sử API có policy:

| Method | Path | Authority |
|---|---|---|
| GET | /api/orders/** | SCOPE_orders.read |
| POST | /api/orders | SCOPE_orders.write |
| PUT | /api/orders/** | SCOPE_orders.write |
| PATCH | /api/orders/** | SCOPE_orders.write |
| DELETE | /api/orders/** | ROLE_ORDER_ADMIN |

Điều quan trọng là thứ tự matcher. Các rule cụ thể theo method phải đứng trước rule tổng quát cho path.

### 6.1. Servlet SecurityFilterChain hoàn chỉnh

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OrdersSecurityConfiguration {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(
            new JwtAuthoritiesConverter());
        return converter;
    }

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            JwtAuthenticationConverter jwtAuthenticationConverter)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()

                .requestMatchers(
                    HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")

                .requestMatchers(
                    HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")

                .requestMatchers(
                    HttpMethod.PUT, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")

                .requestMatchers(
                    HttpMethod.PATCH, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")

                .requestMatchers(
                    HttpMethod.DELETE, "/api/orders/**")
                    .hasAuthority("ROLE_ORDER_ADMIN")

                // Method chưa được liệt kê trên resource này bị từ chối.
                .requestMatchers("/api/orders/**").denyAll()

                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt
                    .jwtAuthenticationConverter(
                        jwtAuthenticationConverter)))
            .build();
    }
}
~~~

Rule cuối cho /api/orders/** từ chối các method không được liệt kê, ví dụ TRACE hoặc một method mới được thêm mà chưa có policy. Nếu thay bằng authenticated(), một principal bất kỳ có thể đi qua path đó dù không có quyền đọc/sửa được thiết kế.

Ví dụ trên dùng denyAll() cho các path còn lại để minh họa API chỉ expose những route đã khai báo. Ứng dụng có health, docs hoặc route khác cần matcher riêng theo policy.

### 6.2. Vì sao phải phân biệt GET và PUT?

Một token chỉ có SCOPE_orders.read phải đọc được đơn hàng nhưng không thể sửa. Một token chỉ có SCOPE_orders.write không tự động được đọc nếu policy yêu cầu quyền read riêng.

Không giả định write bao hàm read trừ khi issuer và API contract quy định như vậy. Việc tách scope cho phép client chỉ nhận quyền tối thiểu cần thiết.

### 6.3. POST collection và PUT/PATCH item

Thông thường:

- POST tạo resource trong collection.
- PUT thay thế trạng thái resource tại URI cụ thể.
- PATCH cập nhật một phần resource.
- DELETE xóa resource.

Policy có thể dùng cùng scope orders.write cho POST/PUT/PATCH và role admin riêng cho DELETE. Nếu nghiệp vụ yêu cầu quyền khác nhau, tách scope rõ như orders.create, orders.update và orders.delete.

### 6.4. Matcher cụ thể phải đứng trước matcher tổng quát

Ví dụ dễ sai:

~~~java
.requestMatchers("/api/orders/**").authenticated()
.requestMatchers(HttpMethod.DELETE, "/api/orders/**")
    .hasAuthority("ROLE_ORDER_ADMIN")
~~~

Rule tổng quát đã match request trước nên rule DELETE phía sau không được dùng. Đặt các matcher method/path cụ thể lên trước, sau đó mới có fallback deny hoặc rule tổng quát.

## 7. Dùng hasAuthority và hasRole đúng cách

Các biểu thức sau:

~~~java
.hasAuthority("SCOPE_orders.read")
.hasAuthority("ROLE_ORDER_ADMIN")
.hasRole("ORDER_ADMIN")
~~~

có ý nghĩa:

| Expression | Authority cần có |
|---|---|
| hasAuthority("SCOPE_orders.read") | SCOPE_orders.read |
| hasAuthority("ROLE_ORDER_ADMIN") | ROLE_ORDER_ADMIN |
| hasRole("ORDER_ADMIN") | ROLE_ORDER_ADMIN |
| hasRole("ROLE_ORDER_ADMIN") | Thường tạo prefix kép, không nên dùng |

Scope thường dùng hasAuthority vì tên scope là giá trị chính xác. Role có thể dùng hasRole nếu tuân theo prefix ROLE_. Dùng hasAuthority cho cả hai loại cũng hợp lệ và thường làm mapping hiển thị rõ hơn.

Không đổi role prefix ở một nơi mà quên cập nhật nơi khác. Nếu converter tạo ROLE_ORDER_ADMIN, policy hasRole("ORDER_ADMIN") hoặc hasAuthority("ROLE_ORDER_ADMIN") sẽ khớp; policy hasAuthority("ORDER_ADMIN") sẽ không khớp.

## 8. Kết hợp HTTP authorization với method security

HTTP matcher bảo vệ request ở biên ứng dụng. Method security bảo vệ service operation ngay cả khi method được gọi từ một đường khác, ví dụ message listener, scheduled job hoặc một controller khác.

### 8.1. Bật method security

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

### 8.2. Bảo vệ service đọc đơn hàng

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
class OrderService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    Order getOrder(String orderId) {
        // Load order and return it.
        return repository.findById(orderId)
            .orElseThrow(OrderNotFoundException::new);
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.write')")
    Order updateOrder(String orderId, UpdateOrderCommand command) {
        // Validate ownership/business rules and update.
        return repository.update(orderId, command);
    }

    @PreAuthorize("hasAuthority('ROLE_ORDER_ADMIN')")
    void deleteOrder(String orderId) {
        repository.delete(orderId);
    }
}
~~~

Các repository/command trong ví dụ là thành phần ứng dụng minh họa. Method security kiểm authority; nó không thay thế kiểm tra ownership hoặc business invariants của đơn hàng.

### 8.3. Kiểm tra ownership theo resource

Scope orders.write chỉ nói principal có quyền cập nhật đơn hàng ở mức API. Nó không có nghĩa người dùng được sửa mọi đơn hàng. Có thể thêm domain authorization:

~~~java
@PreAuthorize("""
    hasAuthority('SCOPE_orders.write')
    and @orderAccess.canEdit(authentication, #orderId)
    """)
Order updateOrder(String orderId, UpdateOrderCommand command) {
    return repository.update(orderId, command);
}
~~~

orderAccess.canEdit có thể kiểm tra tenant, owner hoặc trạng thái workflow. Đây là lớp kiểm soát dữ liệu theo resource; đừng thay bằng role rộng nếu nghiệp vụ yêu cầu ownership.

Nếu dùng parameter name trong SpEL, cấu hình compiler giữ tên tham số (ví dụ -parameters) hoặc dùng annotation hỗ trợ parameter binding theo Spring Security version. Kiểm tra method proxy và parameter discovery trong test.

### 8.4. Method security phải đi qua Spring proxy

Method security dựa vào proxy/interceptor. Nếu gọi method được bảo vệ từ một method khác trong cùng object (self-invocation), lời gọi có thể không đi qua proxy và annotation không được áp dụng như mong đợi. Test bằng cách gọi Spring-managed bean từ bên ngoài và thiết kế service boundary rõ.

## 9. Controller và service mẫu

Một controller có thể để service thực hiện nghiệp vụ:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrdersController {

    private final OrderService orderService;

    OrdersController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping
    List<Order> list() {
        return orderService.listOrders();
    }

    @GetMapping("/{id}")
    Order get(@PathVariable String id) {
        return orderService.getOrder(id);
    }

    @PostMapping
    Order create(@RequestBody CreateOrderCommand command) {
        return orderService.createOrder(command);
    }

    @PutMapping("/{id}")
    Order replace(
            @PathVariable String id,
            @RequestBody UpdateOrderCommand command) {
        return orderService.updateOrder(id, command);
    }

    @PatchMapping("/{id}")
    Order patch(
            @PathVariable String id,
            @RequestBody UpdateOrderCommand command) {
        return orderService.updateOrder(id, command);
    }

    @DeleteMapping("/{id}")
    void delete(@PathVariable String id) {
        orderService.deleteOrder(id);
    }
}
~~~

Trong thực tế, kiểu trả về có thể là DTO, ResponseEntity, Page hoặc Mono tùy stack. Ví dụ này tập trung vào quyền theo method. Không trả entity nội bộ trực tiếp nếu nó chứa dữ liệu không dành cho client.

## 10. Luồng xử lý end-to-end

~~~mermaid
flowchart TD
    A[HTTP request + Bearer access token] --> B[Bearer token resolver]
    B --> C[JwtDecoder verifies signature and validators]
    C --> D[JwtAuthenticationConverter]
    D --> E[JwtGrantedAuthoritiesConverter maps scopes]
    D --> F[JwtRolesConverter maps roles]
    E --> G[JwtAuthenticationToken]
    F --> G
    G --> H{HTTP method + path rule}
    H -->|GET + orders.read| I[Read controller/service]
    H -->|POST/PUT/PATCH + orders.write| J[Write controller/service]
    H -->|DELETE + ORDER_ADMIN| K[Delete controller/service]
    H -->|No matching authority| L[403 Forbidden]
    I --> M[Domain/ownership checks]
    J --> M
    K --> M
~~~

Nếu token không có hoặc không xác minh được, request bị từ chối ở authentication trước khi tạo principal. Nếu token đã xác minh nhưng thiếu authority, authorization trả 403. Nếu có authority phù hợp nhưng không sở hữu resource, domain authorization vẫn có thể từ chối.

## 11. Kiểm thử mapping và authorization

Nên tách hai câu hỏi:

1. Claims được ánh xạ thành authorities đúng không?
2. HTTP method/path yêu cầu authority đúng không?

Sau đó có thể thêm integration test Bearer token đã ký để chứng minh decoder, converter và filter chain được nối với nhau.

### 11.1. Unit test converter

~~~java
@Test
void mapsScopesAndRolesToAuthorities() {
    Jwt jwt = Jwt.withTokenValue("test-token")
        .header("alg", "RS256")
        .claim("scope", "orders.read orders.write")
        .claim("roles", List.of("ORDER_ADMIN", "SUPPORT_AGENT"))
        .build();

    Collection<GrantedAuthority> authorities =
        new JwtAuthoritiesConverter().convert(jwt);

    assertThat(authorities)
        .extracting(GrantedAuthority::getAuthority)
        .containsExactlyInAnyOrder(
            "SCOPE_orders.read",
            "SCOPE_orders.write",
            "ROLE_ORDER_ADMIN",
            "ROLE_SUPPORT_AGENT");
}
~~~

Test này kiểm converter trực tiếp. JWT fixture không có chữ ký và không chứng minh decoder production xác minh token.

### 11.2. MockMvc test GET cần read scope

Với Spring Security Test, có thể dùng jwt() request post-processor để kiểm authorization:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;

mockMvc.perform(get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

### 11.3. MockMvc test thiếu read scope

~~~java
mockMvc.perform(get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.write"))))
    .andExpect(status().isForbidden());
~~~

Principal đã authenticated nhưng chỉ có write scope; policy GET cần read scope nên trả 403.

### 11.4. MockMvc test PUT cần write scope

~~~java
mockMvc.perform(put("/api/orders/123")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.write")))
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {"status":"CONFIRMED"}
            """))
    .andExpect(status().isOk());
~~~

### 11.5. GET scope không được sửa

~~~java
mockMvc.perform(put("/api/orders/123")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")))
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {"status":"CONFIRMED"}
            """))
    .andExpect(status().isForbidden());
~~~

### 11.6. DELETE yêu cầu role admin

~~~java
mockMvc.perform(delete("/api/orders/123")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("ROLE_ORDER_ADMIN"))))
    .andExpect(status().isNoContent());
~~~

Một user có SCOPE_orders.write nhưng không có ROLE_ORDER_ADMIN vẫn phải bị từ chối DELETE nếu policy đã định nghĩa như vậy.

### 11.7. Không có token và thiếu quyền là hai trường hợp khác nhau

~~~java
@Test
void missingTokenIsUnauthorized() throws Exception {
    mockMvc.perform(get("/api/orders"))
        .andExpect(status().isUnauthorized());
}

@Test
void authenticatedTokenWithoutReadScopeIsForbidden() throws Exception {
    mockMvc.perform(get("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.write"))))
        .andExpect(status().isForbidden());
}
~~~

jwt() test post-processor tạo authentication cho request; test đó phù hợp để kiểm authorization. Nó không gửi compact JWT qua decoder và không kiểm mapping production converter.

## 12. Integration test với Bearer JWT đã ký

Để kiểm tra toàn bộ đường đi, tạo access token test có chữ ký thật, gửi qua Authorization header và để Resource Server thực hiện:

1. Đọc Bearer token.
2. Xác minh signature.
3. Chạy issuer/audience/time/type validators.
4. Ánh xạ scope và role qua converter production.
5. Áp dụng matcher theo HTTP method.

Ví dụ test token factory có thể dùng NimbusJwtEncoder với RSA test key:

~~~java
String issueToken(
        JwtEncoder encoder,
        String scope,
        List<String> roles) {

    Instant now = Instant.now();
    JwtClaimsSet claims = JwtClaimsSet.builder()
        .issuer("https://identity.example.test")
        .subject("alice")
        .audience(List.of("orders-api"))
        .issuedAt(now.minusSeconds(10))
        .expiresAt(now.plusSeconds(300))
        .claim("scope", scope)
        .claim("roles", roles)
        .build();

    JwsHeader headers = JwsHeader
        .with(SignatureAlgorithm.RS256)
        .keyId("test-key")
        .build();

    return encoder.encode(
        JwtEncoderParameters.from(headers, claims))
        .getTokenValue();
}
~~~

Sau đó gửi token:

~~~java
String token = issueToken(
    testJwtEncoder,
    "orders.read",
    List.of("ORDER_OPERATOR"));

mockMvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
    .andExpect(status().isOk());

mockMvc.perform(put("/api/orders/123")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"status\":\"CONFIRMED\"}"))
    .andExpect(status().isForbidden());
~~~

Test trên kiểm converter production nếu decoder/authentication provider của test context thực sự dùng cùng JwtAuthenticationConverter đã cấu hình. Đảm bảo decoder tin public key tương ứng với encoder test và issuer/audience validators chấp nhận claims. Không thay decoder bằng mock hoặc dùng jwt() post-processor trong integration test này.

## 13. WebFlux Resource Server

Với WebFlux, policy scope/role và HTTP method giống Servlet, nhưng converter trả về reactive authorities.

### 13.1. Reactive role/scope converter

JwtGrantedAuthoritiesConverter vẫn có thể được dùng để tạo collection; bọc collection trong Flux cho ReactiveJwtAuthenticationConverter:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtAuthenticationConverter;
import reactor.core.publisher.Flux;

Converter<Jwt, Flux<GrantedAuthority>> authoritiesConverter = jwt -> {
    Collection<GrantedAuthority> scopes =
        new JwtGrantedAuthoritiesConverter().convert(jwt);
    Collection<GrantedAuthority> roles =
        new JwtRolesConverter().convert(jwt);

    return Flux.concat(
        Flux.fromIterable(scopes == null ? List.of() : scopes),
        Flux.fromIterable(roles));
};

ReactiveJwtAuthenticationConverter authenticationConverter =
    new ReactiveJwtAuthenticationConverter();
authenticationConverter.setJwtGrantedAuthoritiesConverter(
    authoritiesConverter);
~~~

Trong code production, khởi tạo scope converter và role converter một lần như bean thay vì tạo mới cho mỗi request. Có thể tái sử dụng logic kết hợp từ JwtAuthoritiesConverter rồi dùng Flux.fromIterable.

### 13.2. Reactive SecurityWebFilterChain

~~~java
@Bean
SecurityWebFilterChain reactiveApiSecurity(
        ServerHttpSecurity http,
        ReactiveJwtAuthenticationConverter authenticationConverter) {

    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/public/**").permitAll()

            .pathMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")

            .pathMatchers(HttpMethod.POST, "/api/orders")
                .hasAuthority("SCOPE_orders.write")

            .pathMatchers(HttpMethod.PUT, "/api/orders/**")
                .hasAuthority("SCOPE_orders.write")

            .pathMatchers(HttpMethod.PATCH, "/api/orders/**")
                .hasAuthority("SCOPE_orders.write")

            .pathMatchers(HttpMethod.DELETE, "/api/orders/**")
                .hasAuthority("ROLE_ORDER_ADMIN")

            .pathMatchers("/api/orders/**").denyAll()
            .anyExchange().denyAll())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt
                .jwtAuthenticationConverter(authenticationConverter)))
        .build();
}
~~~

Tên DSL và reactive converter API cần khớp Spring Security version của dự án. Policy vẫn giữ nguyên: method-specific rules đứng trước path fallback deny.

### 13.3. Reactive method security

Với service trả Mono/Flux, bật:

~~~java
@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodSecurityConfiguration {
}
~~~

Ví dụ:

~~~java
@Service
class ReactiveOrderService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    Mono<Order> getOrder(String id) {
        return repository.findById(id);
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.write')")
    Mono<Order> updateOrder(String id, UpdateOrderCommand command) {
        return repository.update(id, command);
    }
}
~~~

Không gọi block() để lấy principal hoặc kết quả service trong reactive path. Spring Security duy trì security context trong Reactor context; giữ pipeline reactive từ filter đến controller/service.

## 14. OPTIONS, CORS và method authorization

Browser có thể gửi CORS preflight OPTIONS trước request GET/PUT/PATCH/DELETE. Nếu API được gọi từ browser:

- Cấu hình CORS policy cho allowed origins, methods và headers.
- Cho phép preflight xử lý trước khi yêu cầu Bearer token nếu policy CORS cần như vậy.
- Chỉ cho phép method thực sự hỗ trợ.
- Không dùng permitAll rộng cho mọi method chỉ để preflight hoạt động.

Preflight OPTIONS không phải thao tác đọc/sửa tài nguyên. Hãy cấu hình CORS integration theo Spring Security version và test preflight riêng. Nếu API không dùng browser cross-origin, không cần thêm rule CORS tùy tiện.

## 15. Quyền scope/role không thay thế kiểm soát dữ liệu

Một authority như SCOPE_orders.read chỉ quyết định principal có thể gọi chức năng đọc ở mức API. Ứng dụng còn phải kiểm tra:

- Người dùng có thuộc tenant của đơn hàng không?
- Đơn hàng có thuộc organization mà principal được phép truy cập không?
- Trạng thái hiện tại có cho phép sửa không?
- Người dùng có phải owner/assignee không?
- Trường dữ liệu được phép cập nhật có bị giới hạn không?

Ví dụ, scope write không cho phép thay đổi giá trị ownerId hoặc tenantId tùy ý. Dùng DTO cho phép cập nhật field hợp lệ và domain authorization ở service. Không coi role admin là lý do bỏ qua mọi business invariant hoặc audit.

## 16. Ma trận quyền hoàn chỉnh

Với policy ví dụ:

| Authorities trong token | GET | POST | PUT/PATCH | DELETE |
|---|---:|---:|---:|---:|
| SCOPE_orders.read | Cho phép | 403 | 403 | 403 |
| SCOPE_orders.write | 403 | Cho phép | Cho phép | 403 |
| ROLE_ORDER_OPERATOR | 403 | 403* | 403* | 403 |
| ROLE_ORDER_ADMIN | 403** | 403** | 403** | Cho phép |
| SCOPE_orders.read + SCOPE_orders.write | Cho phép | Cho phép | Cho phép | 403 |
| SCOPE_orders.read + ROLE_ORDER_ADMIN | Cho phép | 403 | 403 | Cho phép |
| Không có token | 401 | 401 | 401 | 401 |

*Chỉ cho phép ROLE_ORDER_OPERATOR tạo/sửa nếu policy có thêm rule ánh xạ role đó thành quyền hoặc matcher chấp nhận role. Bảng này minh họa policy hiện tại chỉ dùng scope cho read/write.

**Nếu admin cần đọc và sửa tất cả đơn hàng, thêm các authority tương ứng vào policy/matcher; ví dụ trên chỉ cấp role admin cho DELETE.

Ma trận giúp reviewer nhìn thấy quyền nào được cấp. Khi thay đổi mapping hoặc thêm method, cập nhật test cho tất cả cột liên quan.

## 17. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng hasRole("ROLE_ADMIN") | Prefix ROLE_ có thể bị thêm hai lần | Dùng hasRole("ADMIN") hoặc authority đầy đủ |
| Dùng hasAuthority("orders.read") | Không khớp authority mặc định SCOPE_orders.read | Dùng prefix đúng |
| Chỉ map scope, bỏ role claim | Role-based rule luôn fail | Thêm role converter |
| Converter role không kiểm kiểu claim | ClassCastException hoặc mapping sai | Kiểm Collection/String theo schema |
| Role prefix bị lặp | ROLE_ROLE_ADMIN | Chuẩn hóa một lần và thống nhất issuer contract |
| Map mọi claim thành authority | Quyền ngoài ý muốn | Chỉ map claim được cho phép |
| Rule path tổng quát đứng trước method rule | Rule cụ thể không chạy | Đặt method/path matcher cụ thể trước |
| Fallback authenticated() cho mọi method trên orders | Method chưa được policy vẫn được truy cập | Dùng path fallback denyAll() |
| Cho write scope tự động đọc | Vi phạm least privilege | Tách read và write nếu nghiệp vụ yêu cầu |
| Chỉ kiểm HTTP matcher | Service có thể được gọi từ đường khác | Thêm method security/domain authorization |
| Gọi service qua self-invocation | Method security proxy có thể bị bỏ qua | Gọi qua Spring bean proxy |
| Dùng jwt() test rồi kết luận converter hoạt động | Test post-processor bỏ qua decoder/converter production | Unit test converter và Bearer integration test |
| Không kiểm tenant/owner | User có scope có thể sửa dữ liệu người khác | Domain authorization theo resource |
| Cho phép OPTIONS bằng permitAll rộng | Mở thêm method không cần thiết | Cấu hình CORS/preflight riêng |

## 18. Trình tự triển khai

1. **Chốt token contract:** tên claim, kiểu dữ liệu, scope format, role format, issuer và audience.
2. **Cấu hình decoder/validators:** xác minh chữ ký, issuer, audience, thời gian và token profile.
3. **Map scope:** dùng JwtGrantedAuthoritiesConverter hoặc converter riêng theo claim.
4. **Map role:** chuyển role claim sang authority có prefix thống nhất.
5. **Kết hợp authorities:** dùng một JwtAuthenticationConverter cho cả scope và role.
6. **Viết HTTP policy:** khai báo từng method/path và authority cần thiết.
7. **Từ chối method chưa định nghĩa:** thêm path fallback denyAll() cho resource nhạy cảm.
8. **Bảo vệ service:** dùng method security và kiểm tra ownership/tenant.
9. **Viết test:** converter, GET/read, POST/PUT/PATCH/write, DELETE/admin, 401 và 403.
10. **Integration test:** gửi JWT đã ký qua Bearer header để kiểm tra decoder → converter → authorization.

## 19. Kết luận

~~~text
JWT CLAIMS
  scope: orders.read orders.write
  roles: ORDER_OPERATOR
       |
       v
AUTHORITY MAPPING
  scope -> SCOPE_orders.read
          SCOPE_orders.write
  roles -> ROLE_ORDER_OPERATOR
       |
       v
HTTP METHOD POLICY
  GET            -> SCOPE_orders.read
  POST/PUT/PATCH -> SCOPE_orders.write
  DELETE         -> ROLE_ORDER_ADMIN
       |
       v
DOMAIN AUTHORIZATION
  tenant / owner / workflow / field-level rules
       |
       v
CONTROLLER + SERVICE
~~~

Scope và role chỉ hữu ích khi Resource Server ánh xạ chúng thành authorities theo contract rõ ràng. Dùng JwtGrantedAuthoritiesConverter cho scope phổ biến, converter riêng cho role claim và kết hợp hai nguồn trong JwtAuthenticationConverter. Sau đó bảo vệ từng HTTP method/path bằng authority cụ thể, đặt matcher chi tiết trước fallback deny và thêm method/domain security ở service.

Kiểm thử cần phân biệt authentication với authorization: không có hoặc token không hợp lệ thường là 401; token đã xác thực nhưng thiếu scope/role là 403. Mock JWT phù hợp để kiểm nhanh policy; integration test Bearer token đã ký mới chứng minh decoder và converter production cùng tham gia vào request.

## Tài liệu tham khảo

- [Spring Security Reference — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT decoder, authentication converter và authorities.
- [Spring Security API — JwtGrantedAuthoritiesConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html): ánh xạ scope claims thành GrantedAuthority.
- [Spring Security API — JwtAuthenticationConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html): tạo JwtAuthenticationToken và cấu hình authorities converter.
- [Spring Security Reference — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): request matcher, authority và method-based authorization.
- [Spring Security Reference — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): PreAuthorize, EnableMethodSecurity và method interception.
- [Spring Security Reference — Testing MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): JWT request post-processor cho authorization tests.
- [Spring Security Reference — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): ReactiveJwtAuthenticationConverter và WebFlux JWT support.
- [Spring Security Reference — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): reactive method authorization.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): scope parameter và authorization grants.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access-token profile.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer access-token request semantics.
