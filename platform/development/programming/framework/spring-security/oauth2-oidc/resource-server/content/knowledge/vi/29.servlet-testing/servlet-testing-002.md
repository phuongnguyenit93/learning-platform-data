# jwt() và tạo Jwt, claims, authorities cho kiểm thử phân quyền

Khi kiểm thử một ứng dụng **Spring Security OAuth 2.0 Resource Server trên Servlet**, ta thường cần xác nhận request được phép hay bị từ chối dựa trên scope, role, tenant hoặc claim của access token. Tạo JWT có chữ ký thật cho mọi test phân quyền sẽ làm test dài, phụ thuộc key/JWKS và khó tập trung vào luật authorization.

Spring Security Test cung cấp **`jwt()`**, một MockMvc request postprocessor tạo authentication dựa trên đối tượng **`Jwt`** để request được xử lý như đã có JWT authentication. Ta có thể tùy chỉnh JOSE header, claims, subject và authorities để kiểm tra luật phân quyền.

Điểm cần phân biệt: **`jwt()` kiểm thử authorization với JWT authentication giả lập**. Nó không gửi raw Bearer token qua toàn bộ quá trình xác thực, không gọi `JwtDecoder` để verify chữ ký và không chứng minh issuer/audience/expiration validators đang hoạt động. Khi cần kiểm tra các bước đó, phải có test riêng sử dụng Authorization header thật cùng decoder được kiểm soát hoặc token ký bằng test key.

> **Ngữ cảnh minh họa:** Orders API dùng Spring Boot 3.x / Spring Security 6.x, nhận JWT access token qua Bearer authentication. Endpoint GET yêu cầu `SCOPE_orders.read`, endpoint POST yêu cầu `SCOPE_orders.write`. Các ví dụ là test Servlet/MockMvc.

## 1. Vì sao dùng jwt() trong kiểm thử phân quyền?

Một test phân quyền cần tập trung vào câu hỏi: với Authentication có subject và authorities xác định, request có được phép không?

```java
mvc.perform(get("/api/orders")
        .with(jwt()))
    .andExpect(status().isOk());
```

Request postprocessor `jwt()` tạo JWT-based authentication để Spring Security xử lý authorization. Test không cần tạo Authorization Server thật, gọi JWKS endpoint hoặc ký JWT bằng private key production.

Các tình huống thường dùng:

- Người dùng có `SCOPE_orders.read` được đọc đơn hàng.
- Người dùng chỉ có `SCOPE_orders.read` không được tạo đơn hàng.
- Người dùng có role `ROLE_SUPPORT` được truy cập endpoint hỗ trợ.
- JWT có claim `tenant_id` để kiểm tra tenant boundary.
- Subject của JWT được dùng để kiểm tra ownership.
- Method security như `@PreAuthorize` được đánh giá dựa trên authorities.

### 1.1. jwt() tạo authentication cho request test

Với Servlet MockMvc, import:

```java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
```

Dùng postprocessor:

```java
mvc.perform(get("/api/orders")
        .with(jwt()))
    .andExpect(status().isOk());
```

`jwt()` cài JWT-backed authentication trong request test. Một số giá trị mặc định có thể được cung cấp bởi test helper; bài test có ý nghĩa nên khai báo rõ claims và authorities mà luật authorization cần.

### 1.2. jwt() không tạo JWT compact đã ký

`jwt()` không cần tạo chuỗi dạng:

```text
eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3Qta2V5In0...
```

Nó tạo đối tượng `Jwt` trong test và `JwtAuthenticationToken` tương ứng. Do đó không có bước cryptographic signature verification như khi Resource Server xử lý:

```http
Authorization: Bearer eyJ...
```

Đây là lý do `jwt()` tiện cho authorization tests và cũng là lý do không dùng nó làm bằng chứng rằng JWT decoder hoạt động đúng.

## 2. Dependencies và cấu hình MockMvc

### 2.1. Thêm Spring Security Test

Ví dụ Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

`spring-security-test` cung cấp request postprocessors, annotations và test helpers dành cho Spring Security. Dùng version train được Spring Boot quản lý; tránh ghép version test module không tương thích với Spring Security runtime.

### 2.2. Ứng dụng cần cấu hình Resource Server

Một cấu hình Servlet điển hình:

```java
@Configuration
@EnableWebSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

Trong ví dụ này, `http.oauth2ResourceServer(oauth2 -> oauth2.jwt(...))` cấu hình đường xác thực JWT thật khi request mang Bearer token. Còn `jwt()` trong test cài JWT authentication để kiểm tra authorization rules.

| API | Nơi sử dụng | Vai trò |
|---|---|---|
| `oauth2ResourceServer(...).jwt(...)` | Security configuration | Bật JWT Resource Server authentication |
| `SecurityMockMvcRequestPostProcessors.jwt()` | MockMvc test | Tạo JWT-backed authentication giả lập |
| `Jwt.withTokenValue(...)` | Test/helper code | Dựng đối tượng Jwt từ header và claims |
| `JwtDecoder.decode(...)` | Authentication pipeline | Decode và xác minh token theo decoder/validators |

### 2.3. Bật MockMvc security filters

Với Spring Boot:

```java
@SpringBootTest
@AutoConfigureMockMvc
class OrderAuthorizationTests {

    @Autowired
    MockMvc mvc;
}
```

`@AutoConfigureMockMvc` thường cấu hình MockMvc với filter chain của ứng dụng trong context. Nếu tự tạo MockMvc bằng `MockMvcBuilders.standaloneSetup(...)`, cần áp dụng Spring Security config phù hợp, thường qua `springSecurity()` và filter chain/repository đúng.

Cách standalone cần security configuration và filter chain được cung cấp rõ; không giả định chỉ gọi `springSecurity()` là tự tạo toàn bộ Resource Server configuration của ứng dụng.

## 3. Tạo Jwt với jwt().jwt(...)

Cách phổ biến là dùng `jwt()` rồi cấu hình builder bằng lambda:

```java
mvc.perform(get("/api/orders")
        .with(jwt().jwt(jwt -> jwt
            .subject("alice")
            .claim("scope", "orders.read")
            .claim("tenant_id", "tenant-a")
        )))
    .andExpect(status().isOk());
```

Lambda nhận `Jwt.Builder`. Ta có thể tùy chỉnh:

- `subject(...)` cho subject.
- `claim(name, value)` cho claim bất kỳ.
- `header(name, value)` cho JOSE header của đối tượng Jwt.
- `issuedAt(...)` và `expiresAt(...)` cho thời gian.
- `claim("iss", ...)` và `claim("aud", ...)` để tạo issuer/audience claims trong object test.

Nếu cần kiểm thử decoder/issuer/audience validation, `jwt()` không thực hiện validation đó; cần test decoder riêng.

### 3.1. Tạo claims có ý nghĩa cho API

Một JWT access token test có thể có:

```json
{
  "iss": "https://login.example.com",
  "sub": "alice",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "tenant-a",
  "iat": 2000000000,
  "exp": 2000000600
}
```

Tạo tương ứng:

```java
mvc.perform(get("/api/orders")
        .with(jwt().jwt(jwt -> jwt
            .claim("iss", "https://login.example.com")
            .subject("alice")
            .claim("aud", List.of("orders-api"))
            .claim("scope", "orders.read")
            .claim("tenant_id", "tenant-a")
            .issuedAt(Instant.parse("2033-05-18T03:33:20Z"))
            .expiresAt(Instant.parse("2033-05-18T03:43:20Z"))
        )))
    .andExpect(status().isOk());
```

Các timestamp chỉ minh họa cách tạo object; với test thực, chọn thời gian cố định có chủ đích hoặc dùng `Clock` để tránh test phụ thuộc đồng hồ hiện tại. Những giá trị này không được `JwtDecoder` kiểm tra khi dùng request postprocessor `jwt()`.

### 3.2. Tạo một Jwt trước rồi truyền vào jwt()

Khi cần dùng cùng token model cho nhiều test, có thể tạo helper:

```java
private Jwt ordersReadJwt() {
    Instant now = Instant.parse("2030-01-01T10:00:00Z");

    return Jwt.withTokenValue("test-access-token")
        .header("alg", "none")
        .claim("iss", "https://login.example.com")
        .claim("sub", "alice")
        .claim("aud", List.of("orders-api"))
        .claim("scope", "orders.read")
        .claim("tenant_id", "tenant-a")
        .issuedAt(now.minusSeconds(30))
        .expiresAt(now.plusSeconds(300))
        .build();
}
```

Dùng:

```java
mvc.perform(get("/api/orders")
        .with(jwt().jwt(ordersReadJwt())))
    .andExpect(status().isOk());
```

Header `alg=none` trong object test không phải chữ ký JWT hợp lệ và không dùng để kiểm thử cryptographic validation. Đây là object Jwt được tạo trực tiếp cho test postprocessor.

### 3.3. Tạo nhiều Jwt theo persona/permission

```java
private Jwt jwtFor(
        String subject,
        String scope,
        String tenantId) {

    Instant now = Instant.parse("2030-01-01T10:00:00Z");

    return Jwt.withTokenValue("token-for-" + subject)
        .header("alg", "none")
        .claim("iss", "https://login.example.com")
        .claim("sub", subject)
        .claim("aud", List.of("orders-api"))
        .claim("scope", scope)
        .claim("tenant_id", tenantId)
        .issuedAt(now.minusSeconds(30))
        .expiresAt(now.plusSeconds(300))
        .build();
}
```

Dùng helper:

```java
mvc.perform(get("/api/orders")
        .with(jwt().jwt(jwtFor("alice", "orders.read", "tenant-a"))))
    .andExpect(status().isOk());

mvc.perform(post("/api/orders")
        .with(jwt().jwt(jwtFor("alice", "orders.read", "tenant-a"))))
    .andExpect(status().isForbidden());
```

Hai request có cùng identity/scope, nhưng chỉ GET được phép theo rule. Tạo object riêng cho mỗi test hoặc dùng immutable builder; tránh mutable singleton test fixture.
## 4. Claims và authorities: khác nhau ở đâu?

**Claims** là dữ liệu trong access token. **Authorities** là quyền mà Spring Security dùng để ra quyết định authorization. Một số claims được converter ánh xạ thành authorities, nhưng không phải mọi claim đều tự động trở thành quyền.

Ví dụ:

```json
{
  "sub": "alice",
  "scope": "orders.read orders.write",
  "roles": ["SUPPORT"],
  "tenant_id": "tenant-a"
}
```

Có thể diễn giải:

- `sub` xác định subject.
- `scope` biểu diễn OAuth scopes.
- `roles` là claim riêng theo contract của issuer/application.
- `tenant_id` là dữ liệu tenant để application/domain policy kiểm tra.

Default JWT authority converter của Spring Security thường đọc scope claim (`scope` hoặc `scp`) và tạo authority có prefix `SCOPE_`. Ví dụ `orders.read` thành `SCOPE_orders.read`.

Claim `roles` không tự động trở thành `ROLE_SUPPORT` nếu ứng dụng chưa cấu hình converter tương ứng.

### 4.1. Scope claim

Ví dụ token:

```json
{
  "scope": "orders.read orders.write"
}
```

Với default `JwtGrantedAuthoritiesConverter`, scope values được ánh xạ thành:

```text
SCOPE_orders.read
SCOPE_orders.write
```

Do đó authorization rule `hasAuthority("SCOPE_orders.read")` cần đúng prefix và đúng tên scope.

### 4.2. scp claim

Một số issuer sử dụng claim `scp`, thường dưới dạng collection:

```json
{
  "scp": ["orders.read", "orders.write"]
}
```

Spring Security mặc định hỗ trợ các convention scope phổ biến; nếu issuer dùng schema khác, hãy cấu hình `JwtGrantedAuthoritiesConverter` và test mapping rõ ràng.

Không giả định mọi issuer đều dùng cùng claim name hoặc format.

### 4.3. Role claim

Token có thể chứa:

```json
{
  "roles": ["SUPPORT", "AUDITOR"]
}
```

Đây là claim ứng dụng. Muốn map sang `ROLE_SUPPORT` và `ROLE_AUDITOR`, cấu hình custom converter. Đừng nhầm `hasRole("SUPPORT")` với `hasAuthority("SUPPORT")`: `hasRole` mặc định thêm prefix `ROLE_`.

### 4.4. Tenant claim không phải authority mặc định

Ví dụ:

```json
{
  "tenant_id": "tenant-a"
}
```

Claim này không tự tạo authority. Nó thường được dùng để kiểm tra tenant context hoặc domain authorization. Không biến mỗi tenant ID thành một role nếu điều đó làm quyền phình to hoặc khó quản lý.

## 5. Tạo authorities trực tiếp với jwt().authorities(...)

Khi test chỉ cần kiểm tra authorization với một tập quyền cụ thể, có thể chỉ định authorities trực tiếp:

```java
mvc.perform(get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )))
    .andExpect(status().isOk());
```

Nhiều authorities:

```java
mvc.perform(get("/api/admin/reports")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"),
            new SimpleGrantedAuthority("ROLE_AUDITOR")
        )))
    .andExpect(status().isOk());
```

Khi chỉ định `authorities(...)`, test cung cấp authorities cho authentication thay vì dựa vào converter mặc định để suy ra chúng từ claims. Đây là cách tốt để cô lập authorization rule, nhưng không kiểm tra claim-to-authority mapping.

### 5.1. Dùng claims khi muốn test dữ liệu token

Ví dụ test tenant:

```java
mvc.perform(get("/api/tenants/tenant-a/orders")
        .with(jwt().jwt(jwt -> jwt
            .subject("alice")
            .claim("scope", "orders.read")
            .claim("tenant_id", "tenant-a")
        )))
    .andExpect(status().isOk());
```

Claims cần thiết được giữ trong Jwt principal để controller, argument resolver hoặc domain service đọc.

### 5.2. Dùng authorities khi muốn test một luật quyền

```java
mvc.perform(post("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.write")
        )))
    .andExpect(status().isCreated());
```

Test này tập trung vào việc endpoint có yêu cầu đúng authority hay không. Nó không chứng minh issuer thực sự cấp scope đó hoặc converter ánh xạ scope claim chính xác.

### 5.3. Không đưa authority vào claim rồi nghĩ Spring tự hiểu

Ví dụ token:

```json
{
  "authorities": ["ROLE_ADMIN"]
}
```

Default converter không nhất thiết đọc claim tên `authorities`. Nếu ứng dụng dùng claim này, phải cấu hình custom converter. Nếu test dùng `jwt().authorities(...)` thì authorities được gắn trực tiếp và có thể làm test pass dù claim mapping production đang sai.

## 6. JwtAuthenticationToken và principal

`jwt()` tạo JWT-based authentication. Trong controller, có thể nhận:

```java
@GetMapping("/api/orders")
public List<Order> orders(
        @AuthenticationPrincipal Jwt jwt) {
    String subject = jwt.getSubject();
    String tenantId = jwt.getClaimAsString("tenant_id");

    return orderService.findOrders(subject, tenantId);
}
```

Hoặc nhận Authentication:

```java
@GetMapping("/api/current-user")
public Map<String, Object> currentUser(Authentication authentication) {
    JwtAuthenticationToken jwtAuthentication =
        (JwtAuthenticationToken) authentication;

    Jwt jwt = jwtAuthentication.getToken();

    return Map.of(
        "subject", jwt.getSubject(),
        "authorities", jwtAuthentication.getAuthorities()
    );
}
```

Trong test:

```java
mvc.perform(get("/api/current-user")
        .with(jwt().jwt(jwt -> jwt
            .subject("alice")
            .claim("tenant_id", "tenant-a")
            .claim("scope", "orders.read")
        )))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.subject").value("alice"));
```

Tên principal mặc định của `JwtAuthenticationToken` thường lấy từ claim `sub`. Nếu ứng dụng cấu hình principal claim khác, cần test converter/configuration tương ứng.

### 6.1. Kiểm tra claims trong controller

Nếu controller dùng `@AuthenticationPrincipal Jwt`, test có thể xác nhận claims được đọc đúng. Nhưng đừng để controller tự quyết định quyền nhạy cảm chỉ dựa vào claim chưa được xác minh; trong test `jwt()` object được dựng trực tiếp, còn production phải qua decoder.

### 6.2. Kiểm tra authority trong response chỉ khi đó là contract

Không nên expose toàn bộ JWT claims/authorities trong API response chỉ để test. Nếu endpoint thông tin người dùng là API contract có chủ đích, chỉ trả những trường được phép. Nếu không, test authorization qua status/side effect là đủ.

## 7. Kiểm thử hasAuthority và hasAnyAuthority

Security configuration:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders/**")
        .hasAuthority("SCOPE_orders.write")
    .requestMatchers("/api/reports/**")
        .hasAnyAuthority(
            "SCOPE_reports.read",
            "ROLE_AUDITOR"
        )
    .anyRequest().authenticated()
)
```

Tests:

```java
@Test
void readerCanReadOrders() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isOk());
}

@Test
void readerCannotCreateOrders() throws Exception {
    mvc.perform(post("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isForbidden());
}

@Test
void auditorCanReadReports() throws Exception {
    mvc.perform(get("/api/reports")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("ROLE_AUDITOR")
            )))
        .andExpect(status().isOk());
}
```

### 7.1. hasRole và ROLE_ prefix

`hasRole("ADMIN")` thường tương đương kiểm tra authority `ROLE_ADMIN`. Ví dụ:

```java
.requestMatchers("/api/admin/**").hasRole("ADMIN")
```

Test:

```java
mvc.perform(get("/api/admin/reports")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("ROLE_ADMIN")
        )))
    .andExpect(status().isOk());
```

Không truyền `new SimpleGrantedAuthority("ADMIN")` rồi mong `hasRole("ADMIN")` tự chấp nhận. Nếu dùng `hasAuthority("ROLE_ADMIN")`, truyền chính xác chuỗi authority đó.

### 7.2. Test authority thiếu

Một JWT authentication hợp lệ nhưng không có authority phù hợp thường dẫn tới 403 ở endpoint yêu cầu quyền. Đây khác với request không authenticated, thường nhận 401 khi endpoint yêu cầu authentication.

```java
mvc.perform(get("/api/orders")
        .with(jwt().authorities(List.of())))
    .andExpect(status().isForbidden());
```

Nếu API cấu hình entry point/access denied handler riêng, response body có thể khác; status và security semantics vẫn cần được xác định theo contract.

## 8. Kiểm thử claims và domain authorization

Không phải mọi quyết định đều nên biểu diễn thành authority. Tenant, resource owner, account state và quan hệ nghiệp vụ thường cần domain checks.

Ví dụ controller/service nhận tenant claim:

```java
@GetMapping("/api/tenants/{tenantId}/orders")
public List<Order> tenantOrders(
        @PathVariable String tenantId,
        @AuthenticationPrincipal Jwt jwt) {

    String tokenTenant = jwt.getClaimAsString("tenant_id");

    if (!tenantId.equals(tokenTenant)) {
        throw new AccessDeniedException("Tenant mismatch");
    }

    return orderService.findByTenant(tenantId);
}
```

Test đúng tenant:

```java
mvc.perform(get("/api/tenants/tenant-a/orders")
        .with(jwt().jwt(jwt -> jwt
            .subject("alice")
            .claim("scope", "orders.read")
            .claim("tenant_id", "tenant-a")
        )))
    .andExpect(status().isOk());
```

Test sai tenant:

```java
mvc.perform(get("/api/tenants/tenant-b/orders")
        .with(jwt().jwt(jwt -> jwt
            .subject("alice")
            .claim("scope", "orders.read")
            .claim("tenant_id", "tenant-a")
        )))
    .andExpect(status().isForbidden());
```

Đây là test domain policy sử dụng claims của Jwt authentication. Nếu tenant policy nằm trong service layer hoặc method security, đặt test ở đúng boundary đó và xác nhận controller không thực hiện side effect khi tenant mismatch.

### 8.1. Ownership dựa trên sub

Ví dụ resource thuộc user:

```java
@PreAuthorize("@orderAuthorization.canRead(#orderId, authentication)")
public Order findOrder(String orderId) {
    return orderRepository.findById(orderId)
        .orElseThrow();
}
```

Trong test, thay subject:

```java
mvc.perform(get("/api/orders/order-42")
        .with(jwt().jwt(jwt -> jwt
            .subject("alice")
            .claim("scope", "orders.read")
        )))
    .andExpect(status().isOk());
```

Sau đó dùng subject khác để xác nhận policy từ chối. Không chỉ kiểm tra scope nếu quyền thực tế còn phụ thuộc owner.

### 8.2. Claim không tồn tại hoặc sai kiểu

Nếu application yêu cầu `tenant_id`, cần test token thiếu claim và claim sai type/null. Đừng mặc định claim luôn có vì test helper cho phép dựng Jwt tùy ý.

Ví dụ:

```java
mvc.perform(get("/api/tenants/tenant-a/orders")
        .with(jwt().jwt(jwt -> jwt
            .subject("alice")
            .claim("scope", "orders.read")
        )))
    .andExpect(status().isForbidden());
```

Domain policy nên fail closed khi dữ liệu tenant bắt buộc bị thiếu hoặc không hợp lệ.

## 9. Sử dụng jwt() với @PreAuthorize và method security

Nếu application dùng method security:

```java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

Service:

```java
@Service
public class OrderQueryService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public List<Order> findOrders() {
        return List.of();
    }

    @PreAuthorize("hasRole('SUPPORT')")
    public Order supportView(String orderId) {
        return new Order(orderId);
    }
}
```

MockMvc test với `jwt()`:

```java
@Test
void methodSecurityAllowsReader() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isOk());
}

@Test
void methodSecurityRejectsMissingAuthority() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt().authorities(List.of())))
        .andExpect(status().isForbidden());
}
```

### 9.1. MockMvc phải gọi qua Spring-managed proxy

Method security dựa trên Spring AOP proxy. Nếu test tự tạo service bằng `new OrderQueryService()`, annotation có thể không được thực thi. Dùng Spring context và inject bean được quản lý.

### 9.2. Test method trực tiếp khi cần

Có thể kiểm thử service method với Spring Security Test annotations hoặc context setup phù hợp, nhưng test trực tiếp method không chứng minh filter chain đã xác thực request. Chia test theo boundary:

- Unit test domain authorization logic.
- Method-security integration test qua Spring proxy.
- MockMvc test route/filter chain.
## 10. jwt() và @WithMockUser khác nhau thế nào?

Spring Security Test có `@WithMockUser` để tạo authentication giả lập với username/roles. Nhưng khi application nhận JWT, `jwt()` thường phù hợp hơn vì principal là Jwt và có claims.

| Đặc điểm | `@WithMockUser` | `jwt()` |
|---|---|---|
| Principal | UserDetails-like principal | Jwt |
| Authentication | Username/password style mock authentication | JwtAuthenticationToken |
| Claims | Không có JWT claims | Có thể dựng claims |
| Subject | Username | Claim `sub` |
| Authorities | Roles/authorities cấu hình qua annotation | Có thể map từ scope claim hoặc đặt trực tiếp |
| Hữu ích cho | Authorization tổng quát với user | JWT Resource Server, claims, scope, Jwt principal |
| Verify chữ ký JWT | Không | Không |
| Chạy JwtDecoder | Không | Không |

Ví dụ `@WithMockUser`:

```java
@Test
@WithMockUser(username = "alice", roles = "SUPPORT")
void supportEndpointAllowsSupportUser() throws Exception {
    mvc.perform(get("/api/support"))
        .andExpect(status().isOk());
}
```

Ví dụ `jwt()`:

```java
@Test
void supportEndpointAllowsJwtSupportAuthority() throws Exception {
    mvc.perform(get("/api/support")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("ROLE_SUPPORT")
            )))
        .andExpect(status().isOk());
}
```

Hai test không hoàn toàn tương đương nếu controller inject `Jwt` hoặc application đọc claims. Dùng `jwt()` cho test cần JWT principal.

## 11. Test scope-to-authority mapping

Khi không chỉ định authorities trực tiếp, `jwt()` sử dụng JWT authentication converter của test helper để ánh xạ scope claim.

Ví dụ:

```java
mvc.perform(get("/api/orders")
        .with(jwt().jwt(jwt -> jwt
            .claim("scope", "orders.read orders.write")
        )))
    .andExpect(status().isOk());
```

Default converter thường tạo:

```text
SCOPE_orders.read
SCOPE_orders.write
```

Do đó `hasAuthority("SCOPE_orders.read")` sẽ match với scope claim tương ứng.

### 11.1. Vì sao nên test cả mapping và authorization?

Một test dùng `jwt().authorities(...)` có thể chứng minh luật authorization hoạt động nhưng bỏ qua converter. Một test dùng `jwt().jwt(...)` với scope claim có thể kiểm tra đường mapping mặc định được request postprocessor sử dụng.

Tuy vậy, cả hai vẫn không chứng minh converter production được gắn đúng vào `oauth2ResourceServer().jwt()` khi dùng token header thật. Muốn kiểm tra wiring thật, gửi Authorization header và để filter chain tạo authentication.

### 11.2. Claim scope dạng list

Nếu issuer gửi `scp` dạng array, hãy tạo test tương ứng:

```java
mvc.perform(get("/api/orders")
        .with(jwt().jwt(jwt -> jwt
            .claim("scp", List.of("orders.read", "orders.write"))
        )))
    .andExpect(status().isOk());
```

Đảm bảo format claim khớp converter đang dùng. Không giả định list, space-delimited string và nested object được xử lý giống nhau.

## 12. Custom JwtGrantedAuthoritiesConverter cho roles claim

Giả sử Authorization Server phát hành:

```json
{
  "sub": "alice",
  "scope": "orders.read",
  "roles": ["SUPPORT", "AUDITOR"]
}
```

Ứng dụng muốn map roles thành `ROLE_...`:

```java
@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter scopes =
        new JwtGrantedAuthoritiesConverter();

    JwtGrantedAuthoritiesConverter roles =
        new JwtGrantedAuthoritiesConverter();

    roles.setAuthoritiesClaimName("roles");
    roles.setAuthorityPrefix("ROLE_");

    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();

    converter.setJwtGrantedAuthoritiesConverter(jwt -> {
        Collection<GrantedAuthority> authorities =
            new ArrayList<>(scopes.convert(jwt));

        authorities.addAll(roles.convert(jwt));
        return authorities;
    });

    return converter;
}
```

Trong cấu hình Resource Server:

```java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt
        .jwtAuthenticationConverter(jwtAuthenticationConverter())
    )
)
```

Đây là converter ví dụ cho claim roles dạng collection of strings. Trong dự án thực tế, có thể cần converter riêng để kiểm tra kiểu claim, từ chối value sai, xử lý nested roles hoặc tránh mapping trùng lặp.

### 12.1. Unit test converter trực tiếp

```java
@Test
void mapsScopesAndRoles() {
    Jwt jwt = Jwt.withTokenValue("test-token")
        .header("alg", "none")
        .claim("sub", "alice")
        .claim("scope", "orders.read")
        .claim("roles", List.of("SUPPORT", "AUDITOR"))
        .build();

    JwtAuthenticationConverter converter =
        jwtAuthenticationConverter();

    AbstractAuthenticationToken authentication =
        converter.convert(jwt);

    assertThat(authentication.getAuthorities())
        .extracting(GrantedAuthority::getAuthority)
        .contains(
            "SCOPE_orders.read",
            "ROLE_SUPPORT",
            "ROLE_AUDITOR"
        );
}
```

Test này kiểm tra logic converter. Nó không chứng minh converter đã được gắn vào Resource Server filter chain. Cần thêm integration test với Bearer header thật để xác minh wiring.

### 12.2. jwt().authorities(...) bỏ qua mapping từ claims

Nếu viết:

```java
.with(jwt().authorities(
    new SimpleGrantedAuthority("ROLE_SUPPORT")
))
```

test đã cung cấp authority trực tiếp. Nó không xác minh `roles` claim được converter ánh xạ. Khi mục tiêu là test mapping, hãy dùng Jwt claims và converter thật hoặc unit test converter.

### 12.3. Custom principal claim

Nếu application cấu hình principal claim name khác `sub`, test cần kiểm tra `Authentication.getName()` và principal theo converter. Không chỉ đổi claim trong Jwt rồi giả định Spring tự chọn claim đó.

## 13. Tạo Jwt với header và claims có chủ đích

`Jwt` lưu cả JOSE headers lẫn claims. Ví dụ:

```java
Jwt jwt = Jwt.withTokenValue("test-token")
    .header("alg", "RS256")
    .header("kid", "test-signing-key")
    .claim("iss", "https://login.example.com")
    .claim("sub", "alice")
    .claim("aud", List.of("orders-api"))
    .claim("scope", "orders.read")
    .claim("tenant_id", "tenant-a")
    .claim("client_id", "orders-frontend")
    .claim("azp", "orders-frontend")
    .claim("token_use", "access")
    .issuedAt(Instant.parse("2030-01-01T10:00:00Z"))
    .expiresAt(Instant.parse("2030-01-01T10:10:00Z"))
    .build();
```

Lưu ý:

- `alg` và `kid` ở đây chỉ là dữ liệu trong object Jwt test.
- Đặt `alg=RS256` không ký token.
- `iss`, `aud` và `exp` trong object test không được decoder kiểm tra nếu request dùng `jwt()` postprocessor.
- Claims tùy chỉnh chỉ có ý nghĩa với code/converter đọc chúng.
- Không dùng private key hoặc token production trong test fixture.

### 13.1. Claim kiểu số và boolean

Nếu application đọc claim typed, hãy tạo đúng kiểu:

```java
.claim("account_verified", true)
.claim("risk_score", 12)
.claim("permissions_version", 3L)
```

Không dùng chuỗi `"true"` nếu code mong Boolean, hoặc `"12"` nếu code mong Number. Test nên phản ánh JSON claim type thực tế.

### 13.2. Claim nested object

Ví dụ:

```java
.claim("tenant", Map.of(
    "id", "tenant-a",
    "region", "ap-southeast-1"
))
```

Khi đọc nested claim, kiểm tra null/type và không giả định mọi token issuer đều cung cấp object đầy đủ.

### 13.3. Không đưa dữ liệu nhạy cảm vào fixture

Dùng subject và tenant giả lập. Không sao chép access token, email thật, client secret hoặc dữ liệu production vào test source, test report hoặc snapshot.

## 14. Test 401, 403 và permitAll

Cần phân biệt:

- **401 Unauthorized:** request không có Authentication hợp lệ cho endpoint yêu cầu đăng nhập.
- **403 Forbidden:** request đã authenticated nhưng không có authority hoặc bị authorization/domain policy từ chối.
- **permitAll:** endpoint cho phép anonymous; không yêu cầu JWT.

### 14.1. Anonymous request nhận 401

```java
@Test
void anonymousCannotReadOrders() throws Exception {
    mvc.perform(get("/api/orders"))
        .andExpect(status().isUnauthorized());
}
```

Kết quả phụ thuộc endpoint được bảo vệ và entry point được cấu hình. Với Bearer Resource Server, kiểm tra thêm `WWW-Authenticate` nếu đó là API contract.

### 14.2. Authenticated nhưng thiếu scope nhận 403

```java
@Test
void authenticatedWithoutReadScopeIsForbidden() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt().authorities(List.of())))
        .andExpect(status().isForbidden());
}
```

### 14.3. Authenticated có scope được phép

```java
@Test
void readerCanReadOrders() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isOk());
}
```

### 14.4. Public endpoint không cần jwt()

```java
@Test
void publicEndpointAllowsAnonymous() throws Exception {
    mvc.perform(get("/api/public/catalog"))
        .andExpect(status().isOk());
}
```

Không gắn `jwt()` vào mọi test theo thói quen. Một test anonymous có ích để chứng minh endpoint public/protected và authentication entry point hoạt động đúng.

## 15. Kiểm tra Authorization header thật: khi nào cần JwtDecoder?

Nếu mục tiêu là xác nhận `BearerTokenAuthenticationFilter`, `BearerTokenResolver`, `JwtDecoder` và converter production hoạt động cùng nhau, hãy gửi header:

```http
Authorization: Bearer test-token
```

Trong test, thay decoder bằng mock có kiểm soát:

```java
@SpringBootTest
@AutoConfigureMockMvc
class BearerAuthenticationPipelineTests {

    @Autowired
    MockMvc mvc;

    @MockBean
    JwtDecoder jwtDecoder;

    @Test
    void authenticatesBearerHeaderUsingConfiguredDecoder()
            throws Exception {

        Jwt jwt = Jwt.withTokenValue("test-token")
            .header("alg", "none")
            .claim("sub", "alice")
            .claim("scope", "orders.read")
            .build();

        given(jwtDecoder.decode("test-token")).willReturn(jwt);

        mvc.perform(get("/api/orders")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    "Bearer test-token"
                ))
            .andExpect(status().isOk());

        then(jwtDecoder).should().decode("test-token");
    }
}
```

Đây là integration test cho đường Bearer authentication với decoder mock. `JwtDecoder` đã được mock nên test không xác minh chữ ký cryptographic hoặc validator thật; nó xác minh request đi qua pipeline và decoder được gọi.

`@MockBean` được dùng trong nhiều phiên bản Spring Boot 3.x; ở version Spring Framework/Boot mới hơn, có thể dùng annotation mock bean tương ứng như `@MockitoBean`. Chọn annotation được hỗ trợ bởi version dự án.

### 15.1. Kiểm tra converter production được gọi

Nếu cấu hình custom `JwtAuthenticationConverter`, test bằng Authorization header thật và decoder trả về Jwt có scope/roles claims. Sau đó xác nhận endpoint được phép/từ chối theo authorities do converter tạo.

Nếu test dùng `jwt().authorities(...)`, nó đã bỏ qua converter và không kiểm tra wiring này.

### 15.2. Kiểm tra validator issuer/audience/expiry thật

Dùng `NimbusJwtDecoder` với test public key/JWK set hoặc test Authorization Server/JWKS fixture. Ký token bằng test private key rồi gửi Authorization header thật.

Cần test riêng:

- Signature đúng và sai.
- Issuer đúng và sai.
- Audience đúng và sai.
- `exp` hết hạn.
- `nbf` ở tương lai.
- Allowed algorithm.
- Custom claim validators.
- Token profile hoặc token type nếu application yêu cầu.

Không dùng `jwt()` để kết luận các validator trên hoạt động, vì postprocessor tạo authentication trực tiếp.

## 16. Kiểm thử claim mapping và authorization theo từng tầng

Một bộ test có thể chia thành:

| Tầng | Test | Dữ liệu |
|---|---|---|
| Jwt builder/helper | Dựng claims đúng kiểu | `sub`, `scope`, `tenant_id` |
| Authorities converter | Scope/roles → authorities | `scope`, `roles` |
| Security filter chain | Rule URL | `SCOPE_orders.read` |
| Method security | `@PreAuthorize` | Authorities |
| Domain policy | Tenant/owner | `tenant_id`, `sub` |
| JWT authentication pipeline | Header → decoder → converter | Bearer header |
| JWT validation | Signature/issuer/audience/time | Signed test JWT |

### 16.1. Không gom tất cả thành một test khổng lồ

Một test duy nhất khởi tạo app, mock AS, mock database, dựng JWT, gọi endpoint và assert mọi thứ có thể khó chẩn đoán khi thất bại. Chia test theo trách nhiệm để biết lỗi nằm ở token fixture, converter, authentication, URL authorization, method authorization hoặc domain policy.

### 16.2. Nhưng vẫn cần một số integration tests

Unit test converter riêng không chứng minh cấu hình Resource Server đang dùng converter đó. Unit test service authorization riêng không chứng minh filter chain bảo vệ endpoint. Vì vậy vẫn cần một số MockMvc integration tests với security filters thật.

## 17. Helper methods để test dễ đọc

Một helper có thể đóng gói scope và claims:

```java
private RequestPostProcessor jwtReader(String subject) {
    return jwt().jwt(jwt -> jwt
        .subject(subject)
        .claim("scope", "orders.read")
        .claim("tenant_id", "tenant-a")
    );
}

private RequestPostProcessor jwtWriter(String subject) {
    return jwt().jwt(jwt -> jwt
        .subject(subject)
        .claim("scope", "orders.write")
        .claim("tenant_id", "tenant-a")
    );
}
```

Dùng:

```java
mvc.perform(get("/api/orders").with(jwtReader("alice")))
    .andExpect(status().isOk());

mvc.perform(post("/api/orders").with(jwtReader("alice")))
    .andExpect(status().isForbidden());

mvc.perform(post("/api/orders").with(jwtWriter("alice")))
    .andExpect(status().isCreated());
```

### 17.1. Helper cho authorities trực tiếp

```java
private RequestPostProcessor authenticatedWith(
        String... authorities) {

    List<GrantedAuthority> grantedAuthorities =
        Arrays.stream(authorities)
            .map(SimpleGrantedAuthority::new)
            .toList();

    return jwt().authorities(grantedAuthorities);
}
```

Nếu version API chỉ expose overload varargs hoặc collection tương ứng, điều chỉnh helper theo Javadoc version dự án. Tránh helper che giấu sự khác nhau giữa claims và authorities.

### 17.2. Tránh helper quá tổng quát

Không nên tạo helper với hàng chục tham số nullable. Helper như vậy khiến test khó đọc và dễ tạo combination không hợp lệ. Tạo các builder nhỏ theo persona/use case: reader, writer, support agent, cross-tenant actor.

## 18. Test với @AuthenticationPrincipal Jwt

Controller:

```java
@GetMapping("/api/current-tenant")
public String currentTenant(
        @AuthenticationPrincipal Jwt jwt) {
    return jwt.getClaimAsString("tenant_id");
}
```

Test:

```java
mvc.perform(get("/api/current-tenant")
        .with(jwt().jwt(jwt -> jwt
            .subject("alice")
            .claim("tenant_id", "tenant-a")
        )))
    .andExpect(status().isOk())
    .andExpect(content().string("tenant-a"));
```

Nếu controller dùng custom argument resolver hoặc principal claim mapping, test tương ứng. Đừng dùng `@WithMockUser` cho test này vì principal không phải Jwt.

## 19. Test lỗi khi claims thiếu hoặc sai

Một JWT có thể authenticated nhưng thiếu claim application mong đợi. Test các trường hợp:

- Không có `sub` nếu domain yêu cầu.
- Không có `tenant_id`.
- `tenant_id` là object thay vì string.
- `roles` là string thay vì collection.
- `scope` là list trong khi converter mong string, hoặc ngược lại.
- `aud` thiếu downstream resource.
- Claim chứa tenant không tồn tại hoặc không thuộc actor.

Ví dụ tenant claim sai kiểu:

```java
mvc.perform(get("/api/current-tenant")
        .with(jwt().jwt(jwt -> jwt
            .subject("alice")
            .claim("tenant_id", List.of("tenant-a", "tenant-b"))
        )))
    .andExpect(status().isForbidden());
```

Controller/service nên xử lý kiểu dữ liệu không đúng an toàn. Không cast mù hoặc trả 500 vì claim malformed.

## 20. Test authority prefix và tên scope

| Converter tạo | Rule kiểm tra | Kết quả |
|---|---|---|
| `SCOPE_orders.read` | `hasAuthority("SCOPE_orders.read")` | Match |
| `SCOPE_orders.read` | `hasAuthority("orders.read")` | Không match |
| `ROLE_SUPPORT` | `hasRole("SUPPORT")` | Match |
| `ROLE_SUPPORT` | `hasAuthority("SUPPORT")` | Không match |
| `ROLE_SUPPORT` | `hasAuthority("ROLE_SUPPORT")` | Match |

Test nên assert đúng prefix. Đừng đổi prefix trong helper test để làm test pass khi converter production vẫn sai.

## 21. Test nhiều security chains hoặc nhiều loại endpoint

Một ứng dụng có thể có chain cho API Bearer, web session và public endpoints. `jwt()` test cần gửi request tới URL thực tế để chain matcher được chọn đúng.

Ví dụ:

```java
@Test
void apiRouteUsesBearerAuthorizationRules() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isOk());
}

@Test
void webRouteUsesItsOwnAuthenticationMechanism() throws Exception {
    mvc.perform(get("/web/profile"))
        .andExpect(status().is3xxRedirection());
}
```

Test thứ hai chỉ phù hợp nếu web chain thực sự cấu hình login redirect. Điểm cần kiểm tra là mỗi route được xử lý bởi chain đúng, không phải gắn JWT test authentication cho mọi URL.

## 22. Các giới hạn quan trọng của jwt()

### 22.1. Không verify chữ ký

Object Jwt được dựng trực tiếp, không có cryptographic verification. Dùng signed token và real decoder test nếu cần.

### 22.2. Không chạy JwtDecoder

Request postprocessor cài JWT authentication vào request test. Nó không kiểm tra `JwtDecoder` được cấu hình đúng hoặc JWKS endpoint có hoạt động.

### 22.3. Không chứng minh Bearer header parser hoạt động

Nếu muốn test `Authorization: Bearer`, gửi header thật. `jwt()` không kiểm tra `DefaultBearerTokenResolver` hoặc custom `BearerTokenResolver`.

### 22.4. Không kiểm tra issuer/audience/time validators

Các claims trong Jwt test không tự được xác minh. Phải test validator qua decoder pipeline riêng.

### 22.5. Không tự kiểm tra mapping của converter production

Nếu chỉ định `jwt().authorities(...)`, authorities đã được cung cấp trực tiếp. Nếu dùng `jwt().jwt(...)`, postprocessor dùng converter của test helper; không nhất thiết là converter được cấu hình trong Resource Server.

### 22.6. Không kiểm tra token revocation/introspection

Với opaque token, cần test `OpaqueTokenIntrospector` và response `active`; `jwt()` tạo JWT authentication nên không kiểm tra introspection.

### 22.7. Không kiểm tra DPoP/mTLS proof-of-possession

`jwt()` không tạo DPoP proof, không so `cnf.jkt` và không kiểm tra certificate binding. Những phần này cần integration tests chuyên biệt.

## 23. Ví dụ một lớp MockMvc test đầy đủ

```java
package com.example.orders;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrdersAuthorizationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void readerCanReadOrders() throws Exception {
        mvc.perform(get("/api/orders")
                .with(jwt().jwt(jwt -> jwt
                    .subject("alice")
                    .claim("scope", "orders.read")
                    .claim("tenant_id", "tenant-a")
                )))
            .andExpect(status().isOk());
    }

    @Test
    void readerCannotWriteOrders() throws Exception {
        mvc.perform(post("/api/orders")
                .with(jwt().jwt(jwt -> jwt
                    .subject("alice")
                    .claim("scope", "orders.read")
                    .claim("tenant_id", "tenant-a")
                )))
            .andExpect(status().isForbidden());
    }

    @Test
    void writerCanWriteOrders() throws Exception {
        mvc.perform(post("/api/orders")
                .with(jwt().jwt(jwt -> jwt
                    .subject("alice")
                    .claim("scope", "orders.write")
                    .claim("tenant_id", "tenant-a")
                )))
            .andExpect(status().isCreated());
    }

    @Test
    void explicitAuthorityCanBeUsedForFocusedAuthorizationTest()
            throws Exception {
        mvc.perform(get("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read")
                )))
            .andExpect(status().isOk());
    }

    @Test
    void anonymousRequestIsUnauthorized() throws Exception {
        mvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized());
    }
}
```

Lớp này minh họa cách viết test. Để chạy trong dự án, cần endpoint, security configuration, decoder bean và dependencies tương ứng. Test anonymous phụ thuộc endpoint yêu cầu authentication; test writer phụ thuộc controller/service trả 201 khi thành công.

## 24. Những lỗi thường gặp

1. **Dùng `jwt()` rồi kết luận chữ ký JWT đã được kiểm tra.** Postprocessor tạo authentication trực tiếp.
2. **Dùng `jwt().authorities(...)` để kiểm tra scope mapping.** Authorities đã được chỉ định; converter claim có thể bị bỏ qua.
3. **Đưa claim `roles` vào Jwt và nghĩ default converter tự map.** Cần custom converter nếu issuer dùng schema riêng.
4. **Nhầm `hasRole("ADMIN")` với `hasAuthority("ADMIN")`.** Role prefix mặc định là `ROLE_`.
5. **Không set scope claim rõ ràng.** Dựa vào defaults làm test khó hiểu và phụ thuộc implementation/version.
6. **Dùng `@WithMockUser` khi controller yêu cầu Jwt principal.** Principal không phải Jwt.
7. **Test converter riêng nhưng không test wiring.** Converter có thể đúng nhưng không được gắn vào Resource Server.
8. **Không có anonymous test.** Có thể vô tình mở endpoint.
9. **Không phân biệt 401 và 403.** Thiếu authentication khác với authenticated nhưng thiếu quyền.
10. **Dùng claim tenant như authority.** Tenant context thường cần domain authorization.
11. **Tạo Jwt có issuer/audience sai rồi mong `jwt()` trả 401.** Request postprocessor không chạy validators.
12. **Gửi Bearer header nhưng mock decoder không được cấu hình.** Pipeline sẽ không có token authentication thành công.
13. **Dùng token/claims production trong test.** Tạo rủi ro lộ credential/PII.
14. **Dùng helper tạo quá nhiều combination tùy ý.** Test trở nên khó đọc và có thể không phản ánh token contract.

## 25. Quy trình chọn cách test

| Mục tiêu | Cách test phù hợp |
|---|---|
| Endpoint cho phép scope nào? | `jwt().authorities(...)` hoặc `jwt().jwt(...)` |
| Claim `sub`/`tenant_id` được đọc đúng? | `jwt().jwt(...)` với claims cụ thể |
| Scope claim map thành `SCOPE_...`? | `jwt().jwt(...)` với scope claim; thêm converter unit test |
| Custom roles claim map đúng? | Unit test custom converter và integration với Bearer header |
| Controller nhận `@AuthenticationPrincipal Jwt`? | `jwt().jwt(...)` |
| `@PreAuthorize` theo authority? | MockMvc `jwt()` qua Spring proxy/filter chain |
| Anonymous nhận 401? | MockMvc request không gắn postprocessor |
| Thiếu authority nhận 403? | `jwt()` với authorities rỗng/không phù hợp |
| Bearer header được parse? | Authorization header thật |
| JwtDecoder được gọi? | Authorization header thật và decoder mock/spy |
| Signature/issuer/audience/expiry được validate? | Signed test JWT và real decoder/validators |
| Opaque introspection? | Mock/test introspector, không dùng `jwt()` |
| DPoP proof/key binding? | DPoP-specific integration tests |

## 26. Checklist cho test phân quyền JWT

- [ ] Dùng `jwt()` khi mục tiêu là JWT-backed authentication trong MockMvc.
- [ ] Khai báo `sub` và claims cần thiết một cách rõ ràng.
- [ ] Phân biệt claims với authorities.
- [ ] Dùng `SCOPE_` prefix đúng cho OAuth scopes.
- [ ] Dùng `ROLE_` prefix đúng cho roles.
- [ ] Dùng `jwt().authorities(...)` chỉ khi muốn đặt quyền trực tiếp.
- [ ] Test scope mapping riêng nếu đó là contract quan trọng.
- [ ] Test tenant/owner claims ở domain boundary.
- [ ] Có test anonymous 401.
- [ ] Có test authenticated nhưng thiếu quyền 403.
- [ ] Có test thành công cho từng authority cần thiết.
- [ ] Test method security qua Spring-managed proxy.
- [ ] Dùng Bearer header thật khi cần kiểm tra filter/decoder/converter wiring.
- [ ] Dùng signed test token và real decoder khi cần kiểm tra cryptographic validation.
- [ ] Không dùng `jwt()` để kết luận issuer/audience/expiry/JWKS/revocation hoạt động.
- [ ] Không dùng access token hoặc dữ liệu nhạy cảm production trong fixture.

## 27. Tài liệu tham khảo

- [Spring Security — Testing OAuth 2.0](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): MockMvc support, `jwt()` và OAuth2 test request postprocessors.
- [Spring Security — MockMvc Setup](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html): tích hợp Spring Security filter chain với MockMvc.
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT authentication, decoder và authority mapping.
- [Spring Security API — Jwt](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/Jwt.html): tạo và truy cập Jwt headers/claims.
- [Spring Security API — JwtGrantedAuthoritiesConverter](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html): scope/authority conversion.
- [Spring Security API — JwtAuthenticationConverter](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html): chuyển Jwt thành JwtAuthenticationToken.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@PreAuthorize` và method authorization.
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html): test method security với Spring Security Test.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access token claims và validation profile.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer token presentation và error semantics.

**Kết luận:** `jwt()` là công cụ MockMvc để tạo JWT-backed Authentication và tập trung kiểm tra authorization. Dùng `jwt().jwt(...)` khi cần kiểm soát subject/claims và muốn test helper ánh xạ scope; dùng `jwt().authorities(...)` khi muốn kiểm tra một tập quyền cụ thể trực tiếp. Claims như `sub`, `scope`, `roles` và `tenant_id` có vai trò khác nhau; authority mapping phải khớp converter production. Khi cần xác nhận Bearer header, JwtDecoder, chữ ký, issuer, audience hoặc thời hạn, hãy gửi header thật và kiểm thử decoder/validator riêng. Phân chia rõ authorization tests và authentication tests giúp kết quả test phản ánh đúng lớp bảo mật mà ứng dụng cần bảo vệ.


