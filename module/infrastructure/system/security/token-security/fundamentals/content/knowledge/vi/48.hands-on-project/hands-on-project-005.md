# Ánh xạ scope thành authority

## 1. Bài toán thực hành

Một hệ thống có Authorization Server phát hành access token cho các ứng dụng và một nhóm Spring Boot Resource Server tiếp nhận request. Token mang scope theo ngôn ngữ OAuth, ví dụ `orders:read` hoặc `inventory:read`. Trong ứng dụng, Spring Security cần một tập **GrantedAuthority** rõ ràng để quyết định endpoint nào được gọi.

Nếu mỗi controller tự đọc chuỗi scope, tự tách dấu cách và tự so sánh, logic phân quyền sẽ bị lặp lại, khó review và dễ sai khác giữa các API. Nếu ánh xạ scope tùy tiện thành role, một scope hẹp có thể vô tình trở thành quyền quản trị rộng. Dự án này xây dựng một Resource Server có hợp đồng scope rõ ràng, ánh xạ scope được cho phép thành authority của ứng dụng và dùng các authority đó trong URL authorization, method security và kiểm thử.

Bài thuộc chương **Dự án thực hành** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Dự án kết hợp mô hình tin cậy và vòng đời token bảo mật, JWT/opaque token, access/refresh token, OAuth 2.0/OIDC, issuer, claims, scope, audience, lưu trữ và thu hồi. Phần triển khai tập trung vào access token tại Resource Server; refresh token được xử lý ở Authorization Server/Client theo đúng vai trò của nó.

Sau khi hoàn thành, người học có thể:

1. Phân biệt OAuth scope với Spring Security authority và role.
2. Thiết kế bảng ánh xạ scope → authority theo nguyên tắc least privilege.
3. Cấu hình Spring Security Resource Server để chuyển scope trong JWT thành GrantedAuthority.
4. Kiểm tra issuer, audience, thời hạn và chữ ký trước khi cấp quyền.
5. Bảo vệ endpoint bằng `hasAuthority` và `@PreAuthorize`.
6. Viết unit test, integration test và negative test cho các trường hợp thiếu quyền hoặc token sai ngữ cảnh.

## 2. Kịch bản và phạm vi dự án

Xây dựng một phần của hệ thống quản lý đơn hàng gồm hai API:

- **Orders API:** đọc đơn hàng, tạo đơn hàng và hủy đơn hàng.
- **Inventory API:** đọc tồn kho.

Authorization Server cấp access token cho client. Resource Server xác minh token rồi chuyển scope thành authority nội bộ.

### 2.1. Hợp đồng scope

| OAuth scope | GrantedAuthority của ứng dụng | Quyền nghiệp vụ |
| --- | --- | --- |
| `orders:read` | `ORDER_READ` | Đọc đơn hàng. |
| `orders:write` | `ORDER_WRITE` | Tạo đơn hàng. |
| `orders:cancel` | `ORDER_CANCEL` | Hủy đơn hàng. |
| `inventory:read` | `INVENTORY_READ` | Đọc tồn kho. |

Ánh xạ này là allowlist. Chỉ scope được khai báo mới tạo authority. Scope lạ, scope sai chính tả hoặc scope chưa được ứng dụng hỗ trợ không được tự động biến thành quyền.

### 2.2. Những gì dự án thực hiện

- Nhận Bearer access token từ HTTP request.
- Xác minh chữ ký JWT, issuer, audience và thời gian.
- Đọc claim `scope` dạng chuỗi phân tách bằng khoảng trắng.
- Chuyển scope đã biết thành authority của ứng dụng.
- Áp dụng authority cho endpoint và method.
- Trả 401 khi token không hợp lệ; trả 403 khi token hợp lệ nhưng thiếu quyền.

### 2.3. Những gì nằm ngoài phạm vi

Dự án không tự xây Authorization Server, không tự phát hành refresh token và không tự tạo cơ chế đăng nhập người dùng. Trong production, issuer chịu trách nhiệm cấp token; Resource Server chịu trách nhiệm xác minh token và thực thi quyền cho API của nó.

## 3. Kiến trúc tổng thể

~~~mermaid
flowchart LR
    C[OAuth Client] -->|Bearer access token| RS[Spring Resource Server]
    AS[Authorization Server] -->|JWT + scope| C
    RS --> V[JWT Decoder / Validators]
    V -->|JWT hợp lệ| M[Scope-to-Authority Converter]
    M --> A[GrantedAuthority]
    A --> Z[URL / Method Authorization]
    Z --> API[Orders API / Inventory API]
    Z -->|Thiếu authority| D[403 Forbidden]
    V -->|Token invalid| U[401 Unauthorized]
~~~

Luồng xử lý:

1. Client gửi request kèm `Authorization: Bearer <access-token>`.
2. Spring Security Resource Server trích xuất Bearer token.
3. JWT decoder xác minh chữ ký và các validator như issuer, audience, `exp`, `nbf`.
4. `JwtAuthenticationConverter` gọi converter scope → authority.
5. Spring tạo `Authentication` có danh sách `GrantedAuthority`.
6. Authorization rule kiểm tra authority cần thiết.
7. Controller chỉ chạy khi request được cho phép.

Scope không thay thế việc xác minh token. Converter chỉ được chạy trong luồng xác thực sau khi JWT được decoder chấp nhận.

## 4. Phân biệt scope, authority và role

Ba khái niệm có liên quan nhưng không đồng nhất:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| OAuth scope | Quyền hoặc phạm vi mà client được cấp trong access token | `orders:read` |
| Spring `GrantedAuthority` | Quyền mà Spring Security dùng để ra quyết định | `ORDER_READ` |
| Role | Nhóm quyền theo mô hình tổ chức/ứng dụng | `ROLE_ORDER_OPERATOR` |

Một scope thường biểu diễn quyền mà client được cấp đối với resource. Authority là biểu diễn nội bộ mà ứng dụng dùng để bảo vệ endpoint hoặc method. Role có thể gom nhiều authority, nhưng không nên suy ra role quản trị chỉ từ một scope đọc/ghi.

### 4.1. Cách Spring Security xử lý scope mặc định

Khi dùng Resource Server JWT với cấu hình mặc định, Spring Security thường chuyển các giá trị trong claim `scope` (hoặc claim `scp` tùy cấu trúc token) thành authority có tiền tố `SCOPE_`.

Ví dụ:

| Scope trong token | Authority mặc định |
| --- | --- |
| `orders:read` | `SCOPE_orders:read` |
| `orders:write` | `SCOPE_orders:write` |

Khi đó có thể viết `hasAuthority("SCOPE_orders:read")`. Dự án này dùng tên authority nghiệp vụ như `ORDER_READ` để tách contract nội bộ khỏi cách đặt tên scope của issuer. Cả hai cách đều hợp lệ nếu được định nghĩa, kiểm thử và áp dụng nhất quán.

Không dùng `hasRole("ORDER_READ")` nếu converter tạo `ORDER_READ`: `hasRole` thường tự thêm tiền tố `ROLE_`. Hãy dùng `hasAuthority("ORDER_READ")`, hoặc cố ý tạo authority `ROLE_...` nếu đang thiết kế role model.

## 5. Thiết kế contract của access token

JWT mẫu cho Orders API:

~~~json
{
  "iss": "https://identity.example.com",
  "sub": "user-1842",
  "aud": ["orders-api"],
  "iat": 1893452400,
  "exp": 1893452700,
  "jti": "token-8b71",
  "scope": "orders:read inventory:read"
}
~~~

Đây là payload minh họa; chữ ký JWT được tạo bởi issuer và không được bỏ qua trong hệ thống thật. `aud` phải bao gồm resource server đích. Nếu cùng token cần gọi nhiều API, kiến trúc phải xác định rõ audience/resource theo profile; không mặc định mọi API đều chấp nhận cùng một token.

### 5.1. Quy tắc scope

- Scope là chuỗi có phân biệt chữ hoa/chữ thường; contract phải thống nhất chính tả.
- Claim `scope` theo cách dùng phổ biến là chuỗi các scope phân tách bằng khoảng trắng.
- Một số issuer dùng claim `scp` dạng mảng; chỉ hỗ trợ nếu contract của issuer quy định như vậy.
- Không tách scope bằng dấu phẩy nếu issuer không phát hành theo định dạng đó.
- Không tự đổi `orders:read` thành `orders:write` hoặc `ROLE_ADMIN` bằng quy tắc suy đoán.
- Scope không được ứng dụng nhận diện có thể bị bỏ qua; nó không được tạo authority mới.
- Nếu policy yêu cầu chỉ chấp nhận tập scope đã biết, có thể bổ sung validator riêng để từ chối token chứa scope ngoài contract.

### 5.2. Quy tắc audience

Scope đúng nhưng audience sai vẫn phải bị từ chối. Ví dụ token có `orders:read` nhưng chỉ dành cho `inventory-api` không được dùng để gọi Orders API. Authority mapping không thể sửa lỗi audience và không được dùng để thay thế audience validation.

## 6. Cấu trúc project gợi ý

Ví dụ package:

~~~text
src/main/java/com/example/security/
  config/
    SecurityConfig.java
    JwtDecoderConfig.java
  authorization/
    ScopeToAuthorityConverter.java
    ScopeAuthorityMapping.java
  orders/
    OrdersController.java
  inventory/
    InventoryController.java

src/test/java/com/example/security/
  authorization/
    ScopeToAuthorityConverterTest.java
  integration/
    ScopeAuthorizationIntegrationTest.java
~~~

Dependencies cần có:

- Spring Boot Web.
- Spring Security.
- OAuth2 Resource Server.
- Spring Security Test.
- JUnit 5 và AssertJ (hoặc assertion library tương đương).

Phiên bản Spring Boot/Spring Security phải thống nhất theo BOM của project. Các API trong ví dụ theo mô hình Spring Security 6; nếu project dùng phiên bản khác, kiểm tra signature tương ứng trước khi copy.

## 7. Khai báo bảng ánh xạ scope

Không rải chuỗi scope và authority khắp controller. Tạo một bảng ánh xạ tập trung:

~~~java
package com.example.security.authorization;

import java.util.Map;

public final class ScopeAuthorityMapping {

    private ScopeAuthorityMapping() {
    }

    public static final Map<String, String> SCOPE_TO_AUTHORITY = Map.of(
        "orders:read", "ORDER_READ",
        "orders:write", "ORDER_WRITE",
        "orders:cancel", "ORDER_CANCEL",
        "inventory:read", "INVENTORY_READ"
    );
}
~~~

Bảng này là contract bảo mật. Khi thêm scope mới, cần review:

1. Scope do issuer nào cấp và cho client nào?
2. Resource server nào được phép nhận scope?
3. Authority tương ứng cho phép thao tác gì?
4. Endpoint/method nào sử dụng authority?
5. Test positive và negative nào chứng minh quyền đúng?

Không tự động tạo authority bằng cách uppercase scope hoặc thay dấu `:`. Cách chuyển tên tự động dễ tạo quyền ngoài dự kiến khi issuer thêm scope mới.

## 8. Viết ScopeToAuthorityConverter

Converter đọc scope từ JWT và chỉ tạo authority có trong allowlist. Ví dụ hỗ trợ claim chuẩn `scope` dạng chuỗi và claim `scp` dạng mảng theo contract của một số issuer.

~~~java
package com.example.security.authorization;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;
import java.util.Arrays;

import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Component;

@Component
public final class ScopeToAuthorityConverter
        implements Converter<Jwt, Collection<GrantedAuthority>> {

    private final Map<String, String> scopeMapping =
        ScopeAuthorityMapping.SCOPE_TO_AUTHORITY;

    @Override
    public Collection<GrantedAuthority> convert(Jwt jwt) {
        Set<GrantedAuthority> authorities = new LinkedHashSet<>();

        for (String scope : extractScopes(jwt)) {
            String authority = scopeMapping.get(scope);
            if (authority != null) {
                authorities.add(new SimpleGrantedAuthority(authority));
            }
        }

        return authorities;
    }

    private Set<String> extractScopes(Jwt jwt) {
        Set<String> scopes = new LinkedHashSet<>();

        Object scopeClaim = jwt.getClaims().get("scope");
        Object scpClaim = jwt.getClaims().get("scp");
        if (scopeClaim instanceof String scopeValue) {
            Arrays.stream(scopeValue.trim().split("\\s+"))
                .filter(value -> !value.isBlank())
                .forEach(scopes::add);
        } else if (scpClaim instanceof Collection<?> values) {
            for (Object value : values) {
                if (value instanceof String scope && !scope.isBlank()) {
                    scopes.add(scope);
                }
            }
        }

        return scopes;
    }
}
~~~

Điểm cần chú ý:

- `LinkedHashSet` loại bỏ scope trùng và giữ thứ tự ổn định để test dễ đọc.
- Mapping chỉ tạo authority khi scope nằm trong allowlist.
- Claim sai kiểu dữ liệu không tạo quyền.
- Scope không biết bị bỏ qua; nếu không còn authority cần thiết, request sẽ bị từ chối ở authorization layer.
- Converter không xác minh chữ ký, issuer, audience hoặc expiry; những việc đó thuộc JWT decoder/validator.

Nếu issuer chỉ dùng claim `scope`, có thể bỏ nhánh `scp` để giữ contract tối thiểu. Khi cả hai claim xuất hiện, ví dụ ưu tiên `scope` dạng chuỗi và chỉ dùng `scp` khi `scope` không có kiểu chuỗi; hãy chọn một định dạng canonical theo contract issuer. Không hỗ trợ nhiều định dạng claim chỉ để “phòng xa” nếu chưa có issuer cụ thể và test tương ứng.

## 9. Gắn converter vào JwtAuthenticationConverter

Spring Security dùng `JwtAuthenticationConverter` để chuyển JWT hợp lệ thành `Authentication`. Cấu hình converter authority tùy chỉnh:

~~~java
@Bean
JwtAuthenticationConverter jwtAuthenticationConverter(
        ScopeToAuthorityConverter scopeConverter) {

    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();
    converter.setJwtGrantedAuthoritiesConverter(scopeConverter);
    converter.setPrincipalClaimName("sub");
    return converter;
}
~~~

`sub` được dùng làm principal name trong ví dụ. Nếu hệ thống cần định danh khác, phải chọn claim ổn định, đáng tin cậy và không gây nhầm giữa user subject với client/workload identity.

Không đưa dữ liệu nhạy cảm vào principal name hoặc log chỉ vì claim có sẵn. Principal là định danh phục vụ security context; nó không thay thế audit actor/workload metadata.

## 10. Cấu hình Resource Server và authorization

~~~java
@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            JwtAuthenticationConverter jwtAuthenticationConverter)
            throws Exception {

        return http
            // Chỉ disable CSRF khi đây là API stateless dùng Bearer token,
            // không xác thực bằng cookie/session của browser.
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("ORDER_READ")
                .requestMatchers(HttpMethod.POST, "/api/orders/*/cancel")
                    .hasAuthority("ORDER_CANCEL")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("ORDER_WRITE")
                .requestMatchers(HttpMethod.GET, "/api/inventory/**")
                    .hasAuthority("INVENTORY_READ")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt
                    .jwtAuthenticationConverter(jwtAuthenticationConverter)))
            .build();
    }
}
~~~

Thứ tự matcher rất quan trọng. Matcher cụ thể cho thao tác cancel cần được đặt trước matcher POST tổng quát, nếu không request hủy đơn có thể bị áp dụng `ORDER_WRITE`. Khi thiết kế endpoint thật, có thể dùng HTTP method/path rõ ràng hơn để tránh overlap.

Một controller có thể dùng method security để bảo vệ thao tác nghiệp vụ:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrdersController {

    @GetMapping
    @PreAuthorize("hasAuthority('ORDER_READ')")
    public List<OrderDto> findOrders() {
        return List.of();
    }

    @PostMapping
    @PreAuthorize("hasAuthority('ORDER_WRITE')")
    public OrderDto createOrder(@RequestBody CreateOrderRequest request) {
        return new OrderDto();
    }

    @PostMapping("/{id}/cancel")
    @PreAuthorize("hasAuthority('ORDER_CANCEL')")
    public void cancelOrder(@PathVariable String id) {
    }
}
~~~

Ví dụ controller trả dữ liệu giả để tập trung vào security. Ở ứng dụng thực, service layer còn phải kiểm tra quyền trên từng order/tenant/resource; `ORDER_READ` không tự cho phép đọc mọi đơn hàng của mọi tenant.

## 11. Xác minh issuer và audience

Một token có scope phù hợp vẫn phải bị từ chối nếu token không được issuer tin cậy ký hoặc không dành cho API hiện tại.

Ví dụ cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com

app:
  security:
    required-audience: orders-api
~~~

`issuer-uri` giúp Spring thiết lập nguồn metadata/JWKS và validator issuer/time theo cấu hình. Cần bổ sung audience validation theo API. Ví dụ bean cho Spring Security 6:

~~~java
@Bean
JwtDecoder jwtDecoder() {
    String issuer = "https://identity.example.com";
    String requiredAudience = "orders-api";

    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withIssuerLocation(issuer).build();

    OAuth2TokenValidator<Jwt> issuerAndTime =
        JwtValidators.createDefaultWithIssuer(issuer);

    OAuth2TokenValidator<Jwt> audience = jwt -> {
        if (jwt.getAudience().contains(requiredAudience)) {
            return OAuth2TokenValidatorResult.success();
        }
        OAuth2Error error = new OAuth2Error(
            "invalid_token",
            "Required audience is missing",
            null
        );
        return OAuth2TokenValidatorResult.failure(error);
    };

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(issuerAndTime, audience));
    return decoder;
}
~~~

Các validator này kiểm soát token trước khi authority mapping có ý nghĩa. Nếu project đã có `JwtDecoder` bean, cần tích hợp audience validator vào decoder hiện tại thay vì tạo bean thứ hai gây xung đột. Cấu hình JWKS, thuật toán và issuer phải đến từ nguồn tin cậy; không lấy `jku` hoặc key URL tùy ý từ token để xác minh.

YAML và bean phía trên dùng cùng một issuer/audience minh họa. Trong ứng dụng thật, bind hai giá trị này từ cấu hình theo environment (chẳng hạn `@ConfigurationProperties`) thay vì giữ literal trong source; chỉ có một `JwtDecoder` bean chịu trách nhiệm xác minh token.

## 12. Bảo vệ quyền ở tầng nghiệp vụ

Authority thường là quyền cấp API hoặc nhóm hành động. Nó chưa chắc đủ để quyết định người gọi có thể thao tác trên một bản ghi cụ thể.

Ví dụ:

- `ORDER_READ` cho phép gọi chức năng đọc đơn hàng.
- Service vẫn phải kiểm tra đơn hàng thuộc tenant mà subject được phép truy cập.
- `ORDER_CANCEL` cho phép gọi thao tác hủy, nhưng có thể cần kiểm tra trạng thái đơn và chính sách người phê duyệt.
- Service token có authority đọc tồn kho không mặc nhiên được xem dữ liệu tồn kho của mọi tenant.

Có thể lấy principal/claims đã xác minh để truyền subject và tenant context vào domain authorization. Không dùng `tenant_id` từ request body làm bằng chứng quyền; phải đối chiếu với claim đáng tin cậy hoặc policy server-side.

## 13. Unit test cho ScopeToAuthorityConverter

### 13.1. Scope đã biết được ánh xạ

~~~java
class ScopeToAuthorityConverterTest {

    private final ScopeToAuthorityConverter converter =
        new ScopeToAuthorityConverter();

    @Test
    void mapsKnownScopesToApplicationAuthorities() {
        Jwt jwt = Jwt.withTokenValue("test-token")
            .header("alg", "RS256")
            .claim("scope", "orders:read inventory:read")
            .build();

        Set<String> authorities = converter.convert(jwt).stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toSet());

        assertThat(authorities)
            .containsExactlyInAnyOrder("ORDER_READ", "INVENTORY_READ");
    }
}
~~~

### 13.2. Scope lạ không tạo authority

~~~java
@Test
void ignoresUnknownScopes() {
    Jwt jwt = Jwt.withTokenValue("test-token")
        .header("alg", "RS256")
        .claim("scope", "orders:read platform:super-admin")
        .build();

    Set<String> authorities = converter.convert(jwt).stream()
        .map(GrantedAuthority::getAuthority)
        .collect(Collectors.toSet());

    assertThat(authorities).containsExactly("ORDER_READ");
    assertThat(authorities).doesNotContain("ROLE_ADMIN", "PLATFORM_SUPER_ADMIN");
}
~~~

### 13.3. Xử lý khoảng trắng, trùng lặp và claim `scp`

~~~java
@Test
void parsesWhitespaceAndDeduplicatesScopes() {
    Jwt jwt = Jwt.withTokenValue("test-token")
        .header("alg", "RS256")
        .claim("scope", "  orders:read   orders:read  ")
        .build();

    assertThat(converter.convert(jwt))
        .extracting(GrantedAuthority::getAuthority)
        .containsExactly("ORDER_READ");
}

@Test
void supportsScpArrayWhenIssuerContractUsesIt() {
    Jwt jwt = Jwt.withTokenValue("test-token")
        .header("alg", "RS256")
        .claim("scp", List.of("orders:write", "inventory:read"))
        .build();

    assertThat(converter.convert(jwt))
        .extracting(GrantedAuthority::getAuthority)
        .containsExactlyInAnyOrder("ORDER_WRITE", "INVENTORY_READ");
}
~~~

Các unit test trên kiểm tra mapping thuần túy. Chúng không xác minh chữ ký JWT, issuer, audience hoặc việc Spring Security thực sự gọi converter trong filter chain.

## 14. Integration test cho authorization

Integration test cần kiểm tra request đi qua Security Filter Chain để chứng minh converter đã được gắn đúng.

Ví dụ ý tưởng với MockMvc và `JwtDecoder` giả lập trong test:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ScopeAuthorizationIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    JwtDecoder jwtDecoder;

    @Test
    void readScopeCanCallGetOrders() throws Exception {
        given(jwtDecoder.decode("test-token"))
            .willReturn(jwt("test-token", "orders:read"));

        mockMvc.perform(get("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer test-token"))
            .andExpect(status().isOk());
    }

    @Test
    void readScopeCannotCreateOrder() throws Exception {
        given(jwtDecoder.decode("test-token"))
            .willReturn(jwt("test-token", "orders:read"));

        mockMvc.perform(post("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer test-token")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"item\":\"book\"}"))
            .andExpect(status().isForbidden());
    }

    private Jwt jwt(String token, String scope) {
        return Jwt.withTokenValue(token)
            .header("alg", "RS256")
            .claim("iss", "https://identity.example.com")
            .claim("aud", List.of("orders-api"))
            .claim("sub", "user-1842")
            .claim("scope", scope)
            .build();
    }
}
~~~

Đây là integration test của authorization chain nhưng `JwtDecoder` đã được mock, nên không chứng minh chữ ký thật được xác minh. Cần có thêm test với issuer/JWKS test hoặc một decoder cấu hình thật để kiểm tra signature, issuer, audience và expiry.

### 14.1. Kỳ vọng 401 và 403

| Tình huống | HTTP status thường mong đợi | Lý do |
| --- | --- | --- |
| Không gửi Bearer token tới endpoint cần xác thực | 401 | Chưa có Authentication hợp lệ. |
| Token sai chữ ký/issuer/audience hoặc hết hạn | 401 | Token không được xác thực. |
| Token hợp lệ nhưng thiếu authority | 403 | Đã xác thực nhưng không được cấp quyền thao tác. |
| Token có scope đúng và authority được map | 200/201/204 theo endpoint | Authentication và authorization đều đạt. |

Response thực tế có thể được chuẩn hóa bởi exception handler/API gateway, nhưng không được biến lỗi thiếu quyền thành thành công.

## 15. Test matrix cho dự án

| ID | Trường hợp | Kết quả mong đợi |
| --- | --- | --- |
| SCOPE-001 | `orders:read` | Có `ORDER_READ`. |
| SCOPE-002 | `orders:write` | Có `ORDER_WRITE`. |
| SCOPE-003 | `orders:cancel` | Có `ORDER_CANCEL`. |
| SCOPE-004 | `inventory:read` | Có `INVENTORY_READ`. |
| SCOPE-005 | Nhiều scope hợp lệ | Tạo đúng tập authority tương ứng. |
| SCOPE-006 | Scope lạ | Không tạo authority. |
| SCOPE-007 | Scope trùng | Authority chỉ xuất hiện một lần. |
| SCOPE-008 | Khoảng trắng thừa | Parse theo contract, không tạo scope rỗng. |
| SCOPE-009 | Claim `scope` sai kiểu | Không cấp authority từ claim sai kiểu. |
| SCOPE-010 | Claim `scp` dạng mảng | Chỉ xử lý nếu issuer contract quy định hỗ trợ. |
| SCOPE-011 | Sai chữ hoa/thường | Không khớp mapping nếu contract phân biệt chữ hoa/chữ thường. |
| SCOPE-012 | Không có scope | Authentication có thể thành công nhưng không được gọi endpoint yêu cầu authority. |
| SCOPE-013 | Có `orders:read`, gọi GET Orders | Được phép nếu các validator khác đạt. |
| SCOPE-014 | Có `orders:read`, gọi POST Orders | 403. |
| SCOPE-015 | Có `orders:write`, gọi POST Orders | Được phép nếu các validator khác đạt. |
| SCOPE-016 | Có `orders:write`, gọi GET Orders | 403 nếu không có `orders:read`. |
| SCOPE-017 | Có `inventory:read`, gọi Orders API | 403. |
| SCOPE-018 | Token sai audience | 401; converter không cấp quyền để vượt qua. |
| SCOPE-019 | Token sai issuer/chữ ký | 401. |
| SCOPE-020 | Token hết hạn hoặc chưa tới `nbf` | 401 theo validator thời gian. |
| SCOPE-021 | Scope đúng nhưng tenant không thuộc subject | Domain authorization từ chối. |
| SCOPE-022 | Matcher URL và `@PreAuthorize` | Cả hai lớp áp dụng nhất quán. |
| SCOPE-023 | Client gửi token vào query string | API không chấp nhận cách truyền token này theo policy. |
| SCOPE-024 | Token raw xuất hiện trong log | Test log hygiene phải phát hiện và chặn. |

## 16. Chạy thử API

Giả sử ứng dụng chạy local và có một JWT test do issuer test ký. Không dùng token production trong terminal, tài liệu hoặc test fixture.

Request đọc đơn hàng:

~~~http
GET /api/orders HTTP/1.1
Host: localhost:8080
Authorization: Bearer <test-access-token-with-orders-read>
~~~

Request tạo đơn hàng:

~~~http
POST /api/orders HTTP/1.1
Host: localhost:8080
Authorization: Bearer <test-access-token-with-orders-write>
Content-Type: application/json

{
  "item": "book"
}
~~~

Đổi scope trong token test để quan sát 200/201 khi authority phù hợp và 403 khi thiếu authority. Nếu token có scope nhưng sai audience, expected là 401 vì decoder phải từ chối trước khi authorization được xét.

## 17. Lỗi thường gặp khi ánh xạ scope

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng `hasRole` cho authority không có tiền tố `ROLE_` | Quyền không khớp như dự kiến | Dùng `hasAuthority` hoặc chuẩn hóa role prefix có chủ đích. |
| Dùng scope nguyên bản ở một controller, authority nội bộ ở controller khác | Quy tắc phân quyền thiếu nhất quán | Chọn một contract và tập trung mapping. |
| Tự động uppercase mọi scope | Scope mới có thể tạo quyền ngoài ý muốn | Dùng allowlist scope → authority tường minh. |
| Tin claim scope trước khi xác minh JWT | Token giả có thể tự khai quyền | Chỉ chuyển đổi sau khi decoder xác minh token. |
| Bỏ kiểm audience | Token dành cho API khác vẫn được chấp nhận | Thêm audience validator theo resource server. |
| Nhầm 401 với 403 | Khó phân biệt lỗi xác thực và lỗi quyền | Token invalid trả 401; thiếu authority trả 403 theo contract. |
| Dùng `ORDER_READ` để đọc mọi tenant | Authority API bị hiểu nhầm thành quyền trên mọi record | Kiểm tra tenant/resource ở domain layer. |
| Map `admin` thành role quản trị quá rộng | Scope nhỏ trở thành đặc quyền hệ thống | Tách privileged policy và yêu cầu approval/claim tin cậy riêng. |
| Bỏ qua scope lạ mà không theo dõi | Contract issuer thay đổi mà không được phát hiện | Có metric/alert cho scope ngoài allowlist nếu cần. |
| Test converter nhưng không test filter chain | Converter có thể chưa được gắn vào Resource Server | Viết MockMvc integration test qua Bearer authentication. |

## 18. Yêu cầu bảo mật và vận hành

- Chỉ chấp nhận token từ issuer được cấu hình tin cậy.
- Kiểm tra chữ ký và chỉ cho phép thuật toán đã phê duyệt.
- Kiểm tra audience/resource, `exp`, `nbf` và token profile.
- Dùng allowlist scope; không tự động cấp authority cho claim không biết.
- Phân biệt scope, authority, role và domain permission.
- Không lưu hoặc log raw access token, refresh token hay Authorization header.
- Không cache authority/token giữa các subject, tenant, audience hoặc client context khác nhau.
- Theo dõi scope không biết, lỗi JWT validation, 401/403 và thay đổi mapping.
- Review mapping như một thay đổi bảo mật; cập nhật test cùng lúc.
- Khi scope bị thu hồi, xem xét token đã phát hành, cache và cơ chế revocation theo kiến trúc issuer/resource server.

Scope-to-authority converter chỉ là một mắt xích trong authorization. Nó không thay thế xác minh danh tính, kiểm tra quyền trên dữ liệu, tenant isolation hoặc quy trình thu hồi token.

## 19. Tiêu chí nghiệm thu và sản phẩm bàn giao

Dự án được xem là hoàn thành khi có đủ:

1. Bảng scope → authority được owner review và version control.
2. Resource Server xác minh JWT trước khi mapping authority.
3. Issuer, audience và thời gian được kiểm tra.
4. Converter chỉ ánh xạ scope nằm trong allowlist.
5. Endpoint/method sử dụng `hasAuthority` hoặc `@PreAuthorize` nhất quán.
6. Unit test bao phủ scope hợp lệ, scope lạ, trùng lặp, khoảng trắng và claim sai kiểu.
7. Integration test đi qua Security Filter Chain, chứng minh 200/403 đúng quyền.
8. Negative test chứng minh token sai chữ ký/issuer/audience/hết hạn bị 401.
9. Có test domain authorization cho tenant/resource.
10. Log và test output không chứa bearer token hoặc secret.

Sản phẩm bàn giao:

- Source code của scope mapping và JWT authentication converter.
- Security configuration và audience validator.
- Orders/Inventory endpoint mẫu.
- Unit test và integration test report.
- Tài liệu scope contract, bảng quyền và hướng dẫn thêm scope mới.

## 20. Mở rộng dự án

Sau khi hoàn thành phiên bản cơ bản, có thể mở rộng:

- **Opaque token:** thay JWT decoder bằng introspection, sau đó dùng cùng authority mapping trên attributes đã được authorization server xác nhận.
- **Role mapping:** thêm claim role riêng với allowlist và prefix `ROLE_`; không trộn role với scope nếu semantics khác nhau.
- **Tenant-aware authorization:** kiểm tra tenant và resource ownership tại service layer.
- **Policy engine:** tích hợp policy decision point cho quyền động theo subject, actor, resource và context.
- **Revocation:** đo độ trễ khi access token/grant bị revoke và cache introspection được cập nhật.
- **Audit:** ghi subject, client/actor, audience, authority decision, resource và correlation ID mà không ghi token raw.

## 21. Kết luận và tài liệu tham khảo

Ánh xạ scope thành authority tạo một ranh giới rõ ràng giữa quyền được issuer cấp trong access token và tên quyền mà ứng dụng dùng để bảo vệ API. Một bảng allowlist tường minh giúp tránh scope mới vô tình trở thành quyền mới. Spring Security có thể chuyển JWT thành `Authentication`, nhưng Resource Server vẫn phải xác minh chữ ký, issuer, audience và thời hạn trước khi dùng scope để ra quyết định.

Khi triển khai, hãy kiểm thử cả hai chiều: token hợp lệ có đúng authority được phép truy cập, và token sai audience/chữ ký hoặc thiếu scope bị từ chối. Authority API cũng cần kết hợp với kiểm tra tenant/resource ở tầng nghiệp vụ. Điều đó giữ cho quyền trong token phù hợp với ngữ cảnh thực tế của request.

Tài liệu tham khảo:

- **RFC 6749 — OAuth 2.0 Authorization Framework:** định nghĩa scope trong authorization request và access token context.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** cách truyền và bảo vệ Bearer access token.
- **RFC 7519 — JSON Web Token:** cấu trúc JWT và các registered claims.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** profile JWT dành cho access token.
- **RFC 7662 — OAuth 2.0 Token Introspection:** kiểm tra trạng thái opaque token.
- **Spring Security Reference — OAuth 2.0 Resource Server JWT:** JWT decoder, authentication converter và authority mapping.
- **Spring Security Reference — Method Security:** bảo vệ method bằng `@PreAuthorize` và authority.
