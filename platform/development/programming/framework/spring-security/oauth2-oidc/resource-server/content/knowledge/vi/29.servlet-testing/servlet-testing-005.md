# Kiểm tra scope, role, phương thức HTTP và quyền truy cập tài nguyên

Một **Spring Security OAuth 2.0 Resource Server** có thể xác minh access token thành công nhưng vẫn phải từ chối request nếu token thiếu scope, user thiếu role, HTTP method không được phép hoặc người gọi không sở hữu tài nguyên đang truy cập.

Khi kiểm thử Servlet, cần tách bốn lớp quyết định:

1. **Authentication:** request đã có danh tính được xác minh chưa?
2. **Scope/authority:** access token có quyền OAuth2 cần thiết không?
3. **Role:** principal có vai trò ứng dụng cần thiết không?
4. **Resource authorization:** principal có quyền trên đúng bản ghi, tenant hoặc đối tượng nghiệp vụ không?

HTTP method và URL cũng là một phần của policy: quyền đọc bằng GET không tự cho phép POST, PUT hoặc DELETE trên cùng đường dẫn.

Bài học trình bày cách cấu hình authorization bằng **HttpSecurity**, cách phân biệt **SCOPE_** và **ROLE_**, kiểm tra method và quyền trên tài nguyên, sau đó dùng **MockMvc**, **Spring Security Test**, **@WithMockUser**, **jwt()** và **opaqueToken()** để kiểm thử. Một phần quan trọng là nhận biết test nào đang kiểm authorization, test nào thực sự kiểm JWT signature hoặc introspection.

## 1. Authentication và authorization là hai bước khác nhau

Với Resource Server Servlet, request Bearer thường đi qua:

~~~mermaid
flowchart TD
    R[HTTP request + Authorization Bearer] --> F[BearerTokenAuthenticationFilter]
    F --> V[JwtDecoder hoặc OpaqueTokenIntrospector]
    V -->|Không hợp lệ| U[401 Unauthorized]
    V -->|Hợp lệ| A[Authentication + GrantedAuthorities]
    A --> Z{Authorization policy}
    Z -->|Đủ scope, role, resource permission| OK[Controller / service]
    Z -->|Thiếu quyền| D[403 Forbidden hoặc policy 404]
    OK --> M[Domain operation]
~~~

**Authentication** trả lời: “Ai đang gọi và credential có hợp lệ không?”

**Authorization** trả lời: “Danh tính này có được phép thực hiện hành động cụ thể trên tài nguyên này không?”

Ví dụ access token:

~~~json
{
  "iss": "https://identity.example.com",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1893456000
}
~~~

Resource Server có thể xác minh chữ ký, issuer, audience và expiration thành công. Tuy nhiên, token chỉ có **orders.read**, nên không được tự cho phép tạo hoặc xóa đơn hàng.

Một request đã authenticated không có nghĩa là mọi endpoint đều được phép.

## 2. Scope được ánh xạ thành authority như thế nào?

Spring Security dùng **GrantedAuthority** làm đơn vị quyền tổng quát. Với JWT Resource Server, mặc định **JwtAuthenticationConverter** sử dụng **JwtGrantedAuthoritiesConverter** để chuyển scope thành authority.

Ví dụ claim:

~~~json
{
  "scope": "orders.read orders.write"
}
~~~

Các authority mặc định tương ứng:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Một số access token sử dụng claim **scp** thay cho **scope**. Converter mặc định của Spring Security hỗ trợ các quy ước scope phổ biến này; cần xác nhận contract thực tế của Authorization Server.

### 2.1. hasAuthority kiểm tra giá trị chính xác

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
)
~~~

**hasAuthority("SCOPE_orders.read")** yêu cầu đúng authority string đó.

Nếu token chỉ có **SCOPE_orders.write**, request không đạt rule đọc, trừ khi ứng dụng có policy khác cấp quyền tương ứng.

### 2.2. Scope là quyền được cấp cho access token

Scope thường biểu diễn phạm vi mà client/user được cấp khi xin access token, ví dụ:

~~~text
orders.read
orders.write
inventory.read
payments.refund
~~~

Scope có ý nghĩa theo contract giữa Authorization Server, client và Resource Server. Không được chỉ dựa vào tên scope để suy ra nó có cùng quyền ở mọi issuer hoặc mọi API.

### 2.3. Không nhầm claim scope với authority string

Nếu token chứa:

~~~json
{
  "scope": "orders.read"
}
~~~

thì mặc định authority thường là **SCOPE_orders.read**, không phải **orders.read** và cũng không phải **ROLE_orders.read**.

Nếu cấu hình authorization:

~~~java
.hasAuthority("orders.read")
~~~

request có thể bị từ chối dù JWT chứa scope orders.read, vì authority prefix không khớp.

Có thể thay đổi prefix qua converter, nhưng cần thống nhất toàn ứng dụng và test rõ mapping.

## 3. Role khác scope như thế nào?

Role thường biểu diễn vai trò trong ứng dụng hoặc tổ chức, ví dụ:

~~~text
ADMIN
ORDER_MANAGER
AUDITOR
SUPPORT_AGENT
~~~

Spring Security có quy ước prefix **ROLE_** cho các rule role-based.

~~~java
.hasRole("ADMIN")
~~~

tương đương với kiểm tra authority:

~~~java
.hasAuthority("ROLE_ADMIN")
~~~

**hasRole("ADMIN") tự thêm prefix ROLE_** theo cấu hình role prefix mặc định. Không truyền ROLE_ADMIN vào hasRole, vì có thể dẫn đến prefix lặp hoặc lỗi cấu hình tùy API.

### 3.1. Scope và role không tự động tương đương

| Tiêu chí | Scope | Role |
|---|---|---|
| Ý nghĩa thường gặp | Permission được cấp cho access token | Vai trò của user/client trong ứng dụng |
| Ví dụ | orders.read, orders.write | ADMIN, AUDITOR |
| Authority mặc định của JWT scope | SCOPE_orders.read | Không tự động map từ claim roles |
| Rule thường dùng | hasAuthority("SCOPE_orders.read") | hasRole("ADMIN") |
| Nguồn dữ liệu | OAuth2 access token contract | Có thể là claim đã xác minh hoặc UserDetails/policy service |

Đây là cách phân biệt hữu ích, không phải quy tắc bắt buộc của mọi hệ thống. Một Authorization Server có thể phát role claims, nhưng Resource Server phải quyết định rõ claim nào được tin và ánh xạ ra sao.

### 3.2. Claim roles không tự được map thành ROLE_

Ví dụ JWT:

~~~json
{
  "sub": "alice",
  "scope": "orders.read",
  "roles": ["ADMIN", "ORDER_MANAGER"]
}
~~~

Converter mặc định không tự giả định mọi claim tên roles đều là application roles. Nếu muốn dùng claim này, phải cấu hình **JwtAuthenticationConverter** hoặc một converter tùy chỉnh để ánh xạ.

Không cấp ROLE_ADMIN chỉ vì một request gửi header hoặc JSON tự khai roles. Chỉ đọc claims sau khi JWT đã được decoder xác minh.

## 4. Cấu hình authorization theo scope, role và HTTP method

Ví dụ một Orders API có policy:

- GET /api/orders/** cần scope orders.read.
- POST /api/orders/** cần scope orders.write.
- DELETE /api/orders/** cần role ADMIN.
- /api/admin/** cần role ADMIN.
- Các request còn lại bị từ chối.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers(HttpMethod.PUT, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers(HttpMethod.DELETE, "/api/orders/**")
                    .hasRole("ADMIN")
                .requestMatchers("/api/admin/**")
                    .hasRole("ADMIN")
                .anyRequest()
                    .denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

Ví dụ giả định ứng dụng đã cấu hình JwtDecoder và token validation phù hợp.

### 4.1. Thứ tự matcher rất quan trọng

Spring Security áp dụng authorization rules theo thứ tự matcher. Rule cụ thể nên được khai báo trước rule rộng.

Ví dụ sai:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers(HttpMethod.DELETE, "/api/orders/**").hasRole("ADMIN")
)
~~~

Rule /api/** đã khớp trước và chỉ yêu cầu authenticated; rule DELETE phía sau không được dùng cho request đó.

Sửa lại:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.DELETE, "/api/orders/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
)
~~~

Tốt hơn nữa, quy định scope/role cụ thể cho từng nhóm API và dùng **anyRequest().denyAll()** nếu hệ thống cần fail-closed khi route mới xuất hiện.

### 4.2. Cùng một path nhưng khác method

~~~text
GET    /api/orders/42  -> SCOPE_orders.read
POST   /api/orders     -> SCOPE_orders.write
PUT    /api/orders/42  -> SCOPE_orders.write
DELETE /api/orders/42  -> ROLE_ADMIN
~~~

Không nên dùng một rule authenticated chung cho tất cả methods nếu nghiệp vụ có quyền khác nhau.

### 4.3. HTTP method không phải resource permission

Rule GET + orders.read chỉ kiểm quyền ở mức route/method. Nó chưa chứng minh user được xem **đơn hàng số 42**.

Nếu hai users đều có scope orders.read, cả hai có thể qua rule HTTP nhưng chỉ owner hoặc thành viên đúng tenant mới được xem bản ghi cụ thể.

Vì vậy cần thêm authorization ở cấp resource/service.

## 5. Cấu hình custom role claim cho JWT

Giả sử Authorization Server phát claim:

~~~json
{
  "sub": "alice",
  "scope": "orders.read",
  "roles": ["ADMIN", "ORDER_MANAGER"]
}
~~~

Ta muốn:

- scope orders.read → SCOPE_orders.read
- role ADMIN → ROLE_ADMIN
- role ORDER_MANAGER → ROLE_ORDER_MANAGER

Có thể kết hợp **JwtGrantedAuthoritiesConverter** với converter roles:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Configuration
class JwtAuthorityConfiguration {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter scopeConverter =
            new JwtGrantedAuthoritiesConverter();

        JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();

        converter.setJwtGrantedAuthoritiesConverter(jwt -> {
            Collection<GrantedAuthority> authorities =
                new ArrayList<>(scopeConverter.convert(jwt));

            List<String> roles = jwt.getClaimAsStringList("roles");
            if (roles != null) {
                for (String role : roles) {
                    authorities.add(
                        new SimpleGrantedAuthority("ROLE_" + role)
                    );
                }
            }

            return authorities;
        });

        return converter;
    }
}
~~~

Gắn converter vào Resource Server:

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
            .anyRequest().denyAll()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt
                .jwtAuthenticationConverter(jwtAuthenticationConverter)
            )
        );

    return http.build();
}
~~~

### 5.1. Giới hạn nguồn cấp role

Không map mọi claim role từ mọi issuer thành quyền nội bộ.

Ví dụ, token của partner issuer có:

~~~json
{
  "roles": ["ADMIN"]
}
~~~

không nhất thiết được quyền trở thành **ROLE_ADMIN** trong hệ thống quản trị nội bộ.

Nếu có nhiều issuers, role mapping nên phụ thuộc issuer/resource contract đã xác minh. Có thể dùng converter riêng cho từng decoder/AuthenticationManager hoặc chuẩn hóa authorities theo namespace riêng.

### 5.2. Kiểm tra mapping độc lập

Có thể unit test converter bằng một Jwt đã dựng trong test:

~~~java
Jwt jwt = Jwt.withTokenValue("test-token")
    .header("alg", "none")
    .claim("sub", "alice")
    .claim("scope", "orders.read")
    .claim("roles", List.of("ADMIN"))
    .build();

JwtAuthenticationToken authentication =
    (JwtAuthenticationToken) jwtAuthenticationConverter.convert(jwt);

assertThat(authentication.getAuthorities())
    .extracting(GrantedAuthority::getAuthority)
    .contains("SCOPE_orders.read", "ROLE_ADMIN");
~~~

Đây là unit test mapping. Jwt được tạo trong test không phải token có chữ ký hợp lệ và không kiểm JwtDecoder.

## 6. Quyền truy cập tài nguyên: owner, tenant và bản ghi cụ thể

Một endpoint:

~~~http
GET /api/orders/42
~~~

có thể cần đồng thời:

- Token hợp lệ.
- Scope orders.read.
- Tenant của token khớp tenant của đơn hàng.
- Subject của token là owner hoặc có quyền quản lý đơn hàng.
- Đơn hàng tồn tại và đang ở trạng thái cho phép đọc.

Đây là **resource-level authorization**.

### 6.1. Vì sao path matcher không đủ?

Rule:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

không biết ai sở hữu order 42. Nó chỉ biết request có path/method phù hợp và Authentication có authority cần thiết.

Không được coi UUID khó đoán là cơ chế authorization. Attacker có thể lấy được ID qua log, URL, export hoặc một nguồn khác.

### 6.2. Dùng method security cho policy trên tài nguyên

Bật method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Ví dụ một authorization component kiểm subject, tenant và quyền sở hữu:

~~~java
import java.util.UUID;

import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;

@Component("orderAuthorization")
class OrderAuthorization {

    private final OrderRepository repository;

    OrderAuthorization(OrderRepository repository) {
        this.repository = repository;
    }

    public boolean canRead(
            Authentication authentication,
            UUID orderId,
            String subject,
            String tenantId) {

        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)) {
            return false;
        }

        String tokenSubject = jwtAuth.getToken().getSubject();
        String tokenTenant =
            jwtAuth.getToken().getClaimAsString("tenant_id");

        if (tokenSubject == null || tokenTenant == null) {
            return false;
        }

        if (!tokenSubject.equals(subject) || !tokenTenant.equals(tenantId)) {
            return false;
        }

        return repository.existsByIdAndTenantIdAndOwnerSubject(
            orderId, tenantId, subject
        );
    }
}
~~~

Trong code production, bỏ import không sử dụng và thay repository bằng API phù hợp. Ví dụ chỉ minh họa policy owner/tenant cho JWT-based API.

Bảo vệ service method:

~~~java
import java.util.UUID;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.parameters.P;
import org.springframework.stereotype.Service;

@Service
class OrderService {

    private final OrderRepository repository;

    OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize(
        "@orderAuthorization.canRead(authentication, #orderId, #subject, #tenantId)"
    )
    public Order getOrder(
            @P("orderId") UUID orderId,
            @P("subject") String subject,
            @P("tenantId") String tenantId) {

        return repository
            .findByIdAndTenantIdAndOwnerSubject(orderId, tenantId, subject)
            .orElseThrow(OrderNotFoundException::new);
    }
}
~~~

Controller lấy subject và tenant từ JWT đã được xác minh:

~~~java
import java.util.UUID;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/api/orders/{id}")
    Order getOrder(
            @PathVariable UUID id,
            @AuthenticationPrincipal Jwt jwt) {

        return orderService.getOrder(
            id,
            jwt.getSubject(),
            jwt.getClaimAsString("tenant_id")
        );
    }
}
~~~

Điểm quan trọng:

- Subject và tenant được lấy từ JWT đã xác minh, không lấy từ query parameter do client tự khai.
- Authorization component kiểm tra danh tính và repository.
- Truy vấn đọc dữ liệu cũng giới hạn theo tenant/owner, tránh kiểm tra một lần rồi tải dữ liệu không giới hạn ở truy vấn sau.
- Nếu API hỗ trợ opaque token hoặc nhiều principal types, hãy thiết kế identity abstraction chung thay vì ép mọi Authentication thành JwtAuthenticationToken.

### 6.3. Cân nhắc 403 hay 404

Khi user biết ID nhưng không sở hữu tài nguyên, API có thể:

- Trả **403 Forbidden** để nói rõ principal không có quyền.
- Trả **404 Not Found** để không tiết lộ tài nguyên có tồn tại hay không.

Đây là quyết định security/API contract. Cần nhất quán giữa GET, PUT, DELETE và các endpoint liên quan.

### 6.4. Không dùng @PostAuthorize cho mọi thao tác

**@PostAuthorize** kiểm tra quyền sau khi method đã thực thi. Nó có thể hữu ích khi cần kiểm kết quả trả về, nhưng method đã đọc dữ liệu hoặc thực hiện side effect trước khi bị từ chối.

Với thao tác thay đổi dữ liệu, nên kiểm quyền trước khi thực hiện. Với truy vấn danh sách, ưu tiên lọc ngay tại repository/database theo tenant/owner thay vì tải tất cả rồi dùng @PostFilter.

## 7. Bảo vệ service method bằng @PreAuthorize

Method security hữu ích khi cùng service được gọi từ nhiều controller hoặc từ các thành phần nội bộ.

Ví dụ:

~~~java
@Service
class PaymentService {

    @PreAuthorize("hasAuthority('SCOPE_payments.refund')")
    public void refund(UUID paymentId) {
        // Thực hiện hoàn tiền sau khi kiểm tra các domain rules khác
    }

    @PreAuthorize("hasRole('FINANCE_ADMIN')")
    public void exportFinancialReport() {
        // Xuất báo cáo tài chính
    }
}
~~~

Có thể kết hợp điều kiện:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.write') and hasRole('ORDER_MANAGER')"
)
public void updateOrder(UUID orderId) {
    // ...
}
~~~

Cần cả hai authorities mới qua được rule.

### 7.1. Method security không thay thế request authorization

Có thể dùng cả hai:

- HTTP layer: method/path yêu cầu scope đọc hoặc ghi.
- Service layer: user có quyền trên order/tenant cụ thể.

HTTP layer giúp chặn sớm request không phù hợp. Service layer bảo vệ nghiệp vụ ngay cả khi method được gọi từ một entry point khác.

### 7.2. Method security dựa trên Spring AOP proxy

Lệnh gọi method phải đi qua proxy do Spring quản lý để method security áp dụng. **Self-invocation** từ method này sang method khác trong cùng instance có thể bỏ qua proxy.

Ví dụ:

~~~java
public void outer() {
    this.sensitiveOperation(); // Có thể bypass proxy-based method interceptor
}

@PreAuthorize("hasRole('ADMIN')")
public void sensitiveOperation() {
    // ...
}
~~~

Không dựa vào annotation nếu đường gọi không đi qua proxy. Tách service bean hoặc thiết kế boundary phù hợp.

## 8. MockMvc và Spring Security Test

Spring Security cung cấp test support cho Servlet thông qua **spring-security-test**.

Gradle dependency:

~~~groovy
dependencies {
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

Nếu dùng Spring Boot dependency management, không tự đặt phiên bản khác với Spring Security của ứng dụng.

MockMvc cho phép gửi request HTTP giả lập qua MVC và các Spring Security filters được gắn vào test context.

### 8.1. Bật Spring Security filters trong MockMvc

Với Spring Boot:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderApiSecurityTests {

    @Autowired
    MockMvc mvc;
}
~~~

Với cấu hình thủ công:

~~~java
MockMvc mvc = MockMvcBuilders
    .webAppContextSetup(applicationContext)
    .apply(springSecurity())
    .build();
~~~

**Không dùng @AutoConfigureMockMvc(addFilters = false)** trong test có mục tiêu kiểm SecurityFilterChain. Khi tắt filters, request có thể đi thẳng tới controller và test không còn chứng minh authorization của HTTP layer.

Nếu dùng standaloneSetup, phải chủ động gắn Spring Security filters/configuration đúng cách; nếu không, security behavior có thể khác application thật.

## 9. Test JWT authorization bằng jwt()

Spring Security Test có RequestPostProcessor **jwt()** để tạo một JwtAuthenticationToken cho request.

Ví dụ:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void readOrdersWithReadScopeIsAllowed() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isOk());
}
~~~

Request được đưa vào SecurityContext với Authentication có authority đã chỉ định.

### 9.1. Test thiếu scope

~~~java
@Test
void readOrdersWithoutReadScopeIsForbidden() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.write")
            )))
        .andExpect(status().isForbidden());
}
~~~

JWT mock có thể authenticated nhưng thiếu authority cần thiết, nên authorization từ chối với 403.

### 9.2. Cấu hình claims của JWT mock

~~~java
mvc.perform(get("/api/orders")
        .with(jwt().jwt(jwt -> jwt
            .claim("sub", "alice")
            .claim("tenant_id", "tenant-a")
            .claim("scope", "orders.read")
        )))
    .andExpect(status().isOk());
~~~

RequestPostProcessor jwt() tạo JWT test với các claims có thể tùy chỉnh. Scope/scp được chuyển thành authorities theo converter được cấu hình cho Resource Server, trừ khi test ghi đè authorities trực tiếp.

### 9.3. Phân biệt test converter và test authorization

Khi viết:

~~~java
.with(jwt().authorities(
    new SimpleGrantedAuthority("ROLE_ADMIN")
))
~~~

test đang **cấp thẳng authority cho Authentication mock**. Nó kiểm tra rule hasRole/hasAuthority nhưng bỏ qua logic ánh xạ claim roles.

Nếu muốn test custom JwtAuthenticationConverter, viết unit test trực tiếp để kiểm Authentication và authorities mà converter tạo ra. Request post processor jwt().authorities(...) nhận một Converter<Jwt, Collection<GrantedAuthority>> riêng; nó không nhận JwtAuthenticationConverter vì hai converter có kiểu kết quả khác nhau.

### 9.4. jwt() không kiểm chữ ký thật

Theo Spring Security documentation, jwt() tạo một Jwt declarative để đưa Authentication vào request. JWT mặc định trong test có header alg=none và không cần hợp lệ theo chữ ký.

Điều này rất hữu ích khi trọng tâm là authorization, nhưng **không chứng minh JwtDecoder đã kiểm signature, issuer, audience hoặc expiration**.

## 10. Test opaque token bằng opaqueToken()

Với Resource Server opaque token, Spring Security Test có RequestPostProcessor **opaqueToken()**.

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.opaqueToken;

@Test
void partnerReadScopeAllowsRequest() throws Exception {
    mvc.perform(get("/api/partners/orders")
            .with(opaqueToken().authorities(
                new SimpleGrantedAuthority("SCOPE_partner.read")
            )))
        .andExpect(status().isOk());
}
~~~

Có thể cấu hình attributes và authorities của OAuth2AuthenticatedPrincipal để mô phỏng user, tenant hoặc client.

Tương tự jwt(), **opaqueToken() không gọi introspection endpoint thật**. Nó tạo BearerTokenAuthentication mock cho SecurityContext để test authorization.

Nếu mục tiêu là kiểm HTTP client, Basic client credentials, response active=false, timeout hoặc AS integration, cần test với introspection stub/server thật.

## 11. Test role với @WithMockUser hoặc user()

Đối với authorization dựa trên role, có thể dùng:

~~~java
import org.springframework.security.test.context.support.WithMockUser;

@Test
@WithMockUser(username = "alice", roles = "ADMIN")
void adminCanDeleteOrder() throws Exception {
    mvc.perform(delete("/api/orders/42"))
        .andExpect(status().isNoContent());
}
~~~

**roles = "ADMIN"** tạo authority **ROLE_ADMIN**.

Tương đương dùng request post processor:

~~~java
mvc.perform(delete("/api/orders/42")
        .with(user("alice").roles("ADMIN")))
    .andExpect(status().isNoContent());
~~~

### 11.1. @WithMockUser không phải JWT Authentication

@WithMockUser tạo Authentication kiểu username/password với User principal. Nó hữu ích cho:

- Rule role.
- Method security.
- Các policy không phụ thuộc JWT claims.
- Kiểm logic service theo authorities.

Nó không chứng minh Resource Server đã nhận và xác minh Bearer JWT. Với JWT-specific claims như tenant_id, sub, client_id, hãy dùng jwt() hoặc một Authentication phù hợp.

### 11.2. hasRole và roles() cùng dùng prefix

Ví dụ:

~~~java
@PreAuthorize("hasRole('ADMIN')")
~~~

test:

~~~java
@WithMockUser(roles = "ADMIN")
~~~

Hai bên khớp với **ROLE_ADMIN**.

Nếu dùng:

~~~java
@PreAuthorize("hasAuthority('ADMIN')")
~~~

thì @WithMockUser(roles = "ADMIN") không tạo authority ADMIN; nó tạo ROLE_ADMIN. Khi cần authority chính xác ADMIN, có thể dùng authorities:

~~~java
@WithMockUser(authorities = "ADMIN")
~~~

## 12. Test HTTP method và scope riêng

Giả sử cấu hình:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.requestMatchers(HttpMethod.POST, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
.requestMatchers(HttpMethod.DELETE, "/api/orders/**")
    .hasRole("ADMIN")
~~~

Có thể test ma trận:

~~~java
@Test
void readScopeCanGetButCannotCreateOrder() throws Exception {
    mvc.perform(get("/api/orders/42")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isOk());

    mvc.perform(post("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            ))
            .with(csrf()))
        .andExpect(status().isForbidden());
}

@Test
void writeScopeCanCreateOrder() throws Exception {
    mvc.perform(post("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {"productId":"p-100","quantity":2}
                """)
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.write")
            ))
            .with(csrf()))
        .andExpect(status().isCreated());
}
~~~

Ví dụ giả định API tạo order và có CSRF protection bật. Nếu API là Bearer-only stateless và CSRF đã được disable theo threat model, request test không cần csrf().

### 12.1. Vì sao test POST có thể cần csrf()?

Spring Security CSRF protection thường áp dụng cho unsafe HTTP methods. Một request POST có thể nhận 403 do thiếu CSRF token **trước khi authorization scope được đánh giá**.

Nếu test muốn chứng minh token thiếu orders.write thì bị từ chối, nhưng không gửi CSRF token trong ứng dụng có CSRF enabled, kết quả 403 chưa chắc đến từ scope rule.

Dùng:

~~~java
.with(csrf())
~~~

để vượt qua CSRF layer trong test authorization scope, hoặc test CSRF riêng biệt.

Không disable CSRF toàn ứng dụng chỉ để làm test xanh. Chỉ disable cho API thực sự không sử dụng browser-ambient credentials như session cookie hoặc JWT cookie.

### 12.2. 405 khác 403

- **403**: request đã bị security/authorization từ chối hoặc CSRF policy từ chối.
- **405 Method Not Allowed**: request tới được MVC handler mapping nhưng method không được endpoint hỗ trợ.
- **401**: chưa có Authentication hợp lệ.

Nếu anyRequest().denyAll() bắt một HTTP method không được khai báo rule, request có thể bị 403 trước khi MVC trả 405. Khi muốn test 405, cấp Authentication/authority đủ để request đi qua security layer và tới handler mapping.

## 13. Test resource-level authorization

Giả sử user Alice thuộc tenant A, user Bob thuộc tenant B.

| Người gọi | Order | Kết quả policy |
|---|---|---|
| Alice / tenant A | Order của Alice / tenant A | Cho phép |
| Alice / tenant A | Order của Bob / tenant A | Từ chối |
| Alice / tenant A | Order tenant B | Từ chối |
| Alice / tenant A | ID không tồn tại | 404 |
| Admin có quyền toàn tenant | Order cùng tenant | Theo admin policy |
| Admin tenant A | Order tenant B | Từ chối |

### 13.1. Test JWT claims và resource ownership

Ví dụ:

~~~java
@Test
void ownerCanReadOwnOrder() throws Exception {
    mvc.perform(get("/api/orders/42")
            .with(jwt().jwt(jwt -> jwt
                .claim("sub", "alice")
                .claim("tenant_id", "tenant-a")
            ).authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isOk());
}

@Test
void anotherUserCannotReadOrder() throws Exception {
    mvc.perform(get("/api/orders/42")
            .with(jwt().jwt(jwt -> jwt
                .claim("sub", "bob")
                .claim("tenant_id", "tenant-a")
            ).authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isForbidden());
}
~~~

Hai test này giả định order 42 thuộc Alice trong tenant A và service method có resource authorization. Test thứ hai giữ scope giống test thứ nhất nhưng đổi subject, để chứng minh **scope không tự cấp quyền trên mọi order**.

### 13.2. Test cross-tenant

~~~java
@Test
void userCannotReadOrderFromAnotherTenant() throws Exception {
    mvc.perform(get("/api/orders/42")
            .with(jwt().jwt(jwt -> jwt
                .claim("sub", "alice")
                .claim("tenant_id", "tenant-b")
            ).authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isNotFound());
}
~~~

Status 404 ở ví dụ là policy chống enumeration: không tiết lộ order có tồn tại ở tenant khác. Nếu contract của API dùng 403, hãy test đúng status đó.

### 13.3. Không chỉ test controller mock

Nếu chỉ mock service:

~~~java
when(orderService.getOrder(...)).thenReturn(order);
~~~

controller test có thể không đi qua method-security proxy hoặc repository ownership query. Khi test resource authorization, cần test service bean/proxy và repository policy thực sự.

Có thể dùng integration test với database test, hoặc test service method security riêng bằng Spring context có bật @EnableMethodSecurity.

## 14. Test method security

Bật:

~~~java
@EnableMethodSecurity
~~~

Ví dụ service:

~~~java
@Service
class AdminReportService {

    @PreAuthorize("hasRole('ADMIN')")
    public Report generate() {
        return new Report();
    }
}
~~~

Test:

~~~java
@SpringBootTest
class AdminReportServiceTests {

    @Autowired
    AdminReportService service;

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanGenerateReport() {
        assertThat(service.generate()).isNotNull();
    }

    @Test
    @WithMockUser(roles = "USER")
    void regularUserIsDenied() {
        assertThatThrownBy(() -> service.generate())
            .isInstanceOf(AccessDeniedException.class);
    }
}
~~~

Test này gọi service bean từ Spring context để method-security proxy áp dụng. Nếu test gọi một object được khởi tạo trực tiếp bằng new, annotation có thể không được intercept.

### 14.1. Scope method security

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.write')")
public void updateOrder(UUID orderId) {
    // ...
}
~~~

Test với Authentication có SCOPE_orders.read phải bị từ chối; SCOPE_orders.write mới được qua.

### 14.2. Quy tắc @PostAuthorize

~~~java
@PostAuthorize("returnObject.owner == authentication.name")
public Document getDocument(UUID id) {
    return repository.findById(id).orElseThrow();
}
~~~

Có thể kiểm quyền trên kết quả, nhưng document đã được tải trước khi policy chạy. Với dữ liệu nhạy cảm hoặc side effects, ưu tiên kiểm trước hoặc truy vấn giới hạn ngay trong database.

## 15. Kiểm thử JWT signature, issuer, audience và expiration thật

Test post processor **jwt()** bỏ qua cryptographic verification. Nếu mục tiêu là kiểm JwtDecoder, cần gửi token được ký bằng test key qua Bearer filter thật.

Các test quan trọng:

- JWT có signature hợp lệ, issuer/audience đúng, exp còn hạn → được authenticate.
- Signature bị sửa → 401.
- Issuer không tin cậy → 401.
- Audience không đúng API → 401.
- Token hết hạn → 401.
- nbf ở tương lai ngoài clock skew → 401.
- Thuật toán không được phép → 401.
- Scope đúng nhưng thiếu resource permission → 403 hoặc policy 404.

Có thể dùng test RSA/EC key pair và JwtEncoder/JwtDecoder hoặc JWKS test server. Test decoder bằng mock có ích để kiểm filter/exception handling, nhưng không chứng minh signature/JWKS behavior.

### 15.1. Tách test theo mục tiêu

| Mục tiêu | Cách test phù hợp |
|---|---|
| Scope authorization | MockMvc + jwt() |
| Opaque authorities authorization | MockMvc + opaqueToken() |
| Role-based authorization | @WithMockUser hoặc user() |
| Custom role converter | Unit test converter và integration test converter được gắn |
| HTTP method policy | MockMvc với các HTTP methods |
| Resource ownership/tenant | Method security + repository integration |
| JWT signature/issuer/aud/exp | Signed JWT + JwtDecoder thật |
| Opaque introspection | HTTP stub/AS test server |
| CSRF | Request unsafe có/không csrf() |
| SecurityFilterChain coverage | MockMvc chạy đầy đủ Spring Security filters |

## 16. Kiểm tra 401, 403, 404 và 405 đúng nguyên nhân

| Status | Ý nghĩa thường gặp | Cần kiểm |
|---|---|---|
| **401 Unauthorized** | Không có Authentication hợp lệ | Bearer token thiếu, sai chữ ký, expired, inactive |
| **403 Forbidden** | Đã authenticated nhưng không đủ quyền, hoặc CSRF bị từ chối | Scope, role, resource policy, CSRF |
| **404 Not Found** | Không có tài nguyên hoặc cố ý che giấu tài nguyên không được phép xem | Resource existence/tenant policy |
| **405 Method Not Allowed** | MVC không có handler cho method đó sau khi security cho qua | Request mapping và HTTP method |

Không chỉ assert status code. Khi test thất bại, xác định layer nào từ chối:

1. Bearer token extraction.
2. Authentication provider/decoder/introspector.
3. CSRF filter.
4. Request authorization.
5. Method security.
6. Resource/domain authorization.
7. MVC handler mapping.

Một status 403 do thiếu CSRF không chứng minh scope check hoạt động đúng.

## 17. Kiểm tra SecurityFilterChain thật sự được gắn vào MockMvc

Với test cấu hình:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class SecurityIntegrationTests {
    @Autowired
    MockMvc mvc;
}
~~~

Spring Boot auto-configures MockMvc cùng filters theo mặc định.

Nếu dùng:

~~~java
@AutoConfigureMockMvc(addFilters = false)
~~~

thì filters bị bỏ qua. Không dùng cấu hình này cho test authorization.

Với @WebMvcTest, cần bảo đảm SecurityFilterChain và những bean security cần thiết được import/mock đúng. Một slice test có thể không load đầy đủ cấu hình Resource Server của ứng dụng.

Kiểm cả thứ tự SecurityFilterChain nếu ứng dụng có nhiều chains: request /api/orders/** phải đi vào chain dự kiến, không bị chain rộng hơn chọn trước.

## 18. Kiểm tra OpaqueTokenAuthentication và authority mapping

Với opaque Resource Server, introspection response có thể mang attributes và scopes. Spring Security chuyển thông tin được introspector trả về thành principal/authorities theo cấu hình.

Dùng test:

~~~java
mvc.perform(get("/api/partners/orders")
        .with(opaqueToken()
            .authorities(
                new SimpleGrantedAuthority("SCOPE_partner.read")
            )
        ))
    .andExpect(status().isOk());
~~~

Đây là test authorization với principal giả lập. Để kiểm mapping từ introspection response thật, dùng một OpaqueTokenIntrospector test hoặc stub HTTP introspection endpoint.

Các trường hợp:

- active=false → authentication thất bại.
- active=true, đủ scope → authorization có thể thành công.
- active=true, thiếu scope → 403.
- introspection timeout/5xx → lỗi xác minh, không tạo Authentication thành công.
- issuer/audience/tenant attributes không phù hợp → custom validation/policy từ chối.

Không dùng opaqueToken() để kết luận HTTP introspection endpoint hoặc client credentials đang hoạt động.

## 19. Test role và scope cùng lúc

Một endpoint có thể yêu cầu đồng thời scope và role:

~~~java
.requestMatchers(HttpMethod.POST, "/api/orders/**")
    .access((authentication, context) ->
        new AuthorizationDecision(
            authentication.get().getAuthorities().stream()
                .anyMatch(a -> a.getAuthority().equals("SCOPE_orders.write"))
            &&
            authentication.get().getAuthorities().stream()
                .anyMatch(a -> a.getAuthority().equals("ROLE_ORDER_MANAGER"))
        )
    )
~~~

Ví dụ trên minh họa logic AND. Trong code production, nên viết custom AuthorizationManager/component riêng nếu policy phức tạp, dễ test và tránh lặp stream logic.

Một rule đơn giản có thể dùng:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.write') and hasRole('ORDER_MANAGER')"
)
~~~

### 19.1. Ma trận AND

| Scope | Role | Kết quả |
|---|---|---|
| orders.write | ORDER_MANAGER | Cho phép |
| orders.write | USER | Từ chối |
| orders.read | ORDER_MANAGER | Từ chối |
| orders.read | USER | Từ chối |

Test từng tổ hợp, không chỉ test case thành công.

## 20. Test list resource và tenant filtering

Với endpoint:

~~~http
GET /api/orders
~~~

nếu user thuộc tenant A, API chỉ nên trả orders thuộc tenant A và những bản ghi mà user được phép xem.

Không nên:

1. Tải tất cả orders.
2. Trả list về controller.
3. Lọc bằng cách so subject trong memory ở cuối.

Cách đó có thể gây rò rỉ dữ liệu qua logs, metrics, memory, pagination count hoặc lỗi logic.

Ưu tiên repository query có điều kiện tenant/owner:

~~~java
Page<Order> findByTenantIdAndOwnerSubject(
    String tenantId,
    String subject,
    Pageable pageable
);
~~~

Kiểm thử:

- User tenant A chỉ nhận dữ liệu tenant A.
- Pagination count cũng chỉ tính dữ liệu được phép xem.
- Sort/filter không làm lộ records tenant B.
- User không có role quản lý không thể bật query flag để xem toàn tenant.
- Tenant ID trong query được lấy từ identity đã xác minh, không tin parameter client gửi.

## 21. Cấu hình CSRF và kiểm thử POST/PUT/DELETE

Servlet Spring Security thường bật CSRF protection trong các cấu hình web mặc định. Với API stateless Bearer-only, có thể cấu hình khác nếu token được gửi chủ động trong Authorization header và không dùng browser-ambient credentials.

Nếu ứng dụng dùng session cookie, JWT cookie hoặc Basic auth mà browser tự gửi, CSRF vẫn cần được đánh giá.

Trong MockMvc, request POST/PUT/PATCH/DELETE có thể cần:

~~~java
.with(csrf())
~~~

Test CSRF riêng:

~~~java
@Test
void postWithoutCsrfIsRejectedWhenCsrfIsEnabled() throws Exception {
    mvc.perform(post("/web/profile"))
        .andExpect(status().isForbidden());
}

@Test
void postWithCsrfPassesCsrfLayer() throws Exception {
    mvc.perform(post("/web/profile")
            .with(user("alice"))
            .with(csrf()))
        .andExpect(status().isOk());
}
~~~

Ví dụ giả định endpoint web yêu cầu authentication và CSRF. Test thứ hai cần role/scope phù hợp nếu authorization rule yêu cầu thêm quyền.

Đừng xóa CSRF chỉ vì một test POST bị 403. Xác định nguyên nhân 403 trước.

## 22. Một bộ test mẫu theo ma trận authorization

Ví dụ policy:

| Method | Path | Yêu cầu |
|---|---|---|
| GET | /api/orders/** | SCOPE_orders.read |
| POST | /api/orders/** | SCOPE_orders.write |
| DELETE | /api/orders/** | ROLE_ADMIN |
| GET | /api/admin/** | ROLE_ADMIN |
| Any other request | Any path | denyAll |

Bộ test tối thiểu nên có:

~~~java
@Test
void anonymousRequestGets401() throws Exception {
    mvc.perform(get("/api/orders"))
        .andExpect(status().isUnauthorized());
}

@Test
void readScopeCanReadOrders() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isOk());
}

@Test
void writeScopeCannotReadWhenReadScopeIsRequired() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.write")
            )))
        .andExpect(status().isForbidden());
}

@Test
void readScopeCannotDeleteOrder() throws Exception {
    mvc.perform(delete("/api/orders/42")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isForbidden());
}

@Test
void adminRoleCanDeleteOrder() throws Exception {
    mvc.perform(delete("/api/orders/42")
            .with(user("admin").roles("ADMIN"))
            .with(csrf()))
        .andExpect(status().isNoContent());
}
~~~

Các test trên giả định:

- MockMvc đã gắn Spring Security filters.
- GET/DELETE có handler tương ứng.
- DELETE chain có CSRF disabled cho Bearer-only API hoặc test thêm csrf() nếu CSRF enabled.
- Endpoint thực sự trả các status đã nêu.
- Service/repository không có thêm điều kiện khiến kết quả khác.

Khi dùng @WithMockUser/user() cho role test, test tập trung vào role authorization. Dùng jwt() để test JWT authority path. Không trộn mục tiêu của hai loại Authentication mock.

## 23. Checklist kiểm thử theo từng lớp

### Authentication

- Không token → 401.
- Bearer token invalid → 401.
- JWT expired → 401.
- Wrong issuer/audience → 401.
- Opaque inactive → 401.
- Introspection/decoder infrastructure failure không được fail-open.

### Scope

- Đúng scope → qua.
- Thiếu scope → 403.
- Chỉ có write không tự đọc được nếu policy yêu cầu read.
- Scope claim mapping đúng prefix SCOPE_.
- Scope từ issuer khác không được map nhầm.

### Role

- ROLE_ADMIN qua rule hasRole("ADMIN").
- ROLE_USER bị từ chối.
- Claim roles chỉ được map khi converter được cấu hình.
- Không map role của partner issuer thành internal admin.

### HTTP method

- GET/POST/PUT/DELETE có rule riêng.
- Đúng method nhưng thiếu scope → 403.
- Sai method không vô tình qua rule rộng.
- Phân biệt 403 security với 405 MVC.

### Resource

- Owner được truy cập.
- Non-owner bị từ chối.
- Cross-tenant bị từ chối.
- Không tồn tại trả 404.
- List query được lọc ngay trong repository.
- Update/delete kiểm quyền trước side effect.

### Test harness

- MockMvc có Spring Security filters.
- Không dùng addFilters=false.
- CSRF được xử lý rõ.
- jwt()/opaqueToken() chỉ dùng cho authorization-focused tests.
- Có signed-token/AS integration tests cho decoder/introspection.
- Method security gọi qua Spring proxy.

## 24. Những anti-pattern thường gặp

**Chỉ test controller trả 200.** Không chứng minh scope, role, method hoặc resource ownership đã được kiểm.

**Dùng @WithMockUser để kiểm JWT signature.** @WithMockUser tạo username/password Authentication giả.

**Dùng jwt() rồi khẳng định decoder verify chữ ký.** jwt() inject mock JwtAuthenticationToken, không cần JWT hợp lệ.

**Dùng opaqueToken() rồi khẳng định AS introspection hoạt động.** Post processor không gọi introspection endpoint.

**Nhầm hasRole("ADMIN") với hasAuthority("ADMIN").** hasRole mặc định tìm ROLE_ADMIN.

**Nhầm scope orders.read với authority orders.read.** Default converter thường thêm SCOPE_.

**Map claim roles không tin cậy thành ROLE_ADMIN.** Chỉ dùng claims đã xác minh và issuer policy phù hợp.

**Dùng một rule authenticated cho mọi HTTP methods.** Có thể cho phép write/delete với token chỉ có quyền read.

**Dùng path matcher để thay resource ownership.** Scope đọc không đồng nghĩa quyền đọc mọi order ID.

**Chỉ kiểm quyền ở controller.** Một service có thể được gọi từ entry point khác; cần domain/service boundary.

**Dùng @PostAuthorize cho thao tác có side effects.** Method có thể đã thực hiện công việc trước khi bị từ chối.

**Dùng @PostFilter cho danh sách lớn thay query tenant-scoped.** Tốn tài nguyên và có nguy cơ lộ dữ liệu qua metadata/pagination.

**Bỏ CSRF để test POST.** Có thể che mất security bug trong browser/session flow.

**Dùng addFilters=false.** Test không còn kiểm security filters.

**Không test cross-tenant.** ID khó đoán không thay thế authorization.

## 25. Quy trình xây dựng test suite

**Bước 1 — Viết bảng policy.** Liệt kê method, path, scope, role và resource constraints.

**Bước 2 — Xác định Authentication type.** JWT Resource Server, opaque token, Basic, session hay custom principal.

**Bước 3 — Test authority mapping.** Scope/scp và roles được map thành GrantedAuthority đúng prefix.

**Bước 4 — Test request authorization.** Dùng MockMvc và jwt()/opaqueToken()/user() theo đúng loại policy.

**Bước 5 — Test method matrix.** Cùng path, các methods khác nhau và scopes khác nhau.

**Bước 6 — Test resource authorization.** Owner, non-owner, cross-tenant, missing resource và admin boundary.

**Bước 7 — Test method security.** Bật @EnableMethodSecurity, gọi service bean qua proxy.

**Bước 8 — Test CSRF riêng.** Phân biệt 403 do CSRF với 403 do thiếu authority.

**Bước 9 — Test cryptographic/authentication integration.** Signed JWT, JWKS/issuer/audience/expiration hoặc introspection stub.

**Bước 10 — Test qua SecurityFilterChain thật.** Đảm bảo filters, matcher order và fallback hoạt động như application.

**Bước 11 — Kiểm error contract.** 401, 403, 404 và 405 đúng layer/policy.

**Bước 12 — Giữ negative tests.** Mỗi lần thêm scope, role, route hoặc HTTP method mới, bổ sung test để chứng minh không mở rộng quyền ngoài ý muốn.

## 26. Câu hỏi tự kiểm tra

**1. JWT có scope orders.read thì authority mặc định thường là gì?**

SCOPE_orders.read.

**2. hasRole("ADMIN") kiểm authority nào?**

ROLE_ADMIN theo prefix mặc định.

**3. Claim roles trong JWT có tự map thành ROLE_ADMIN không?**

Không mặc định. Cần custom JwtAuthenticationConverter hoặc mapping phù hợp.

**4. User có scope orders.read có được DELETE order không?**

Không nếu DELETE yêu cầu ROLE_ADMIN hoặc scope khác.

**5. GET /api/orders/** có scope read nghĩa là user được xem mọi order không?**

Không. Cần kiểm owner, tenant hoặc quyền tài nguyên cụ thể.

**6. jwt() có verify JWT signature không?**

Không. Nó tạo Authentication mock cho test authorization.

**7. opaqueToken() có gọi introspection endpoint không?**

Không. Nó tạo BearerTokenAuthentication mock.

**8. @WithMockUser(roles="ADMIN") tạo authority nào?**

ROLE_ADMIN.

**9. Vì sao POST thiếu csrf() có thể trả 403 dù scope đúng?**

Vì CSRF filter có thể từ chối trước khi authorization rule được đánh giá.

**10. @EnableMethodSecurity dùng để làm gì?**

Bật các annotation như @PreAuthorize và @PostAuthorize cho Spring-managed method calls.

**11. Vì sao @PostAuthorize có thể không phù hợp cho DELETE?**

Method có thể đã thực hiện side effect trước khi kết quả authorization bị từ chối.

**12. Khi nào cần signed JWT integration test?**

Khi muốn kiểm chữ ký, key/JWKS, issuer, audience, exp/nbf và converter/decoder thật thay vì chỉ test authorization với Authentication mock.

## Kết luận

Kiểm thử authorization của Spring Security Resource Server cần đi từ **scope**, **role**, **HTTP method** tới **quyền trên tài nguyên cụ thể**. Một access token hợp lệ chỉ chứng minh credential được chấp nhận; nó không tự cho phép mọi thao tác hoặc mọi bản ghi.

Trong Servlet tests:

- Dùng **jwt()** để kiểm authorization với JwtAuthenticationToken giả lập.
- Dùng **opaqueToken()** để kiểm authorization với BearerTokenAuthentication giả lập.
- Dùng **@WithMockUser/user()** cho role và method-security policies không phụ thuộc JWT claims.
- Dùng signed JWT và decoder/JWKS thật khi cần chứng minh cryptographic validation.
- Dùng introspection stub/server khi cần chứng minh opaque-token authentication.
- Kiểm method, tenant, owner và repository query; phân biệt 401, 403, 404, 405 và CSRF failures.

**Một test suite tốt phải chứng minh cả những request được phép lẫn những request gần giống nhưng phải bị từ chối.** Đặc biệt, test cross-scope, cross-role, cross-method và cross-tenant giúp phát hiện việc mở rộng quyền ngoài ý muốn khi API phát triển.

### Tài liệu tham khảo

- [Spring Security — Testing OAuth 2.0 with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html)
- [Spring Security — Running a Test as a User in Spring MVC Test](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html)
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security API — JwtAuthenticationConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html)
- [Spring Security API — JwtGrantedAuthoritiesConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html)
- [Spring Security API — SecurityMockMvcRequestPostProcessors](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/servlet/request/SecurityMockMvcRequestPostProcessors.html)
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
