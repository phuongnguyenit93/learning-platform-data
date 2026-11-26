# jwt tạo Authentication cho kiểm thử phân quyền resource server

> **Chương:** JWT với MockMvc  
> **Module:** `SPRING_SECURITY_TESTING` — kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên ứng dụng Servlet và Reactive. Bài này tập trung vào helper `jwt()` của `MockMvc` để dựng một `JwtAuthenticationToken` cho request kiểm thử.

## 1. jwt() giải quyết bài toán gì?

Một API resource server thường bảo vệ endpoint bằng Bearer JWT. Ví dụ:

- `GET /api/reports` yêu cầu scope `reports.read`.
- `GET /api/admin/reports` yêu cầu authority quản trị.
- `GET /api/me` trả thông tin principal lấy từ JWT claims.
- Request không có token hoặc token không hợp lệ bị từ chối.
- Token hợp lệ nhưng thiếu scope bị từ chối theo authorization policy.

Nếu mọi bài test authorization đều phải tạo token thật, ký token, cấu hình key, issuer và decoder, bộ test sẽ phức tạp dù câu hỏi chỉ là: **principal đã được xác thực và có authority nào thì được gọi endpoint?**

`spring-security-test` cung cấp `SecurityMockMvcRequestPostProcessors.jwt()` để giải quyết phần đó. Helper tạo authentication JWT giả lập và gắn vào request của `MockMvc`. Nhờ vậy ta có thể kiểm tra request authorization, method security và cách controller sử dụng JWT principal với claims do test kiểm soát.

Ví dụ ngắn:

```java
mvc.perform(get("/api/reports")
        .with(jwt()))
    .andExpect(status().isOk());
```

Ví dụ trên không cần gửi một Bearer token đã ký qua HTTP. Test post-processor dựng một `JwtAuthenticationToken` cho request. Request vẫn đi qua phần security chain xử lý authorization của ứng dụng, nhưng **khâu đọc Bearer header và xác minh token bằng `JwtDecoder` không phải mục tiêu của helper này**.

Đây là ranh giới cần nhớ xuyên suốt bài:

- Dùng `jwt()` khi muốn kiểm tra quyền của một JWT principal đã được coi là hợp lệ.
- Gửi `Authorization: Bearer ...` qua decoder thật khi muốn kiểm tra chữ ký, thời hạn, issuer, audience hoặc ánh xạ claims bằng converter của ứng dụng.

## 2. Thêm spring-security-test và cấu hình resource server

Bài dùng Spring MVC/Servlet, `MockMvc` và Spring Security OAuth2 Resource Server. Module test cần có dependency `spring-security-test` cùng các dependency Spring Security resource server phù hợp với ứng dụng.

Với Maven, dependency test thường có dạng:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
```

Nếu dự án dùng Spring Boot dependency management, để Boot quản lý phiên bản thay vì tự chọn một phiên bản `spring-security-test` khác với các module Spring Security còn lại.

Một cấu hình resource server tối giản:

```java
@Configuration
@EnableWebSecurity
class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/status")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .requestMatchers(HttpMethod.GET, "/api/admin/reports")
                    .hasAuthority("REPORT_ADMIN")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

Cấu hình này minh họa hai cách đặt quyền:

- Scope chuẩn được ánh xạ thành authority có prefix `SCOPE_`; scope `reports.read` trở thành `SCOPE_reports.read` theo converter mặc định.
- `REPORT_ADMIN` là authority ứng dụng tự quy định. Nếu authority này đến từ custom claim, ứng dụng cần cấu hình converter tương ứng.

Một controller ví dụ:

```java
@RestController
class ReportController {

    @GetMapping("/api/reports")
    Map<String, Object> reports() {
        return Map.of(
            "reportId", "R-100",
            "tenant", "acme",
            "total", 125000
        );
    }

    @GetMapping("/api/me")
    Map<String, Object> me(@AuthenticationPrincipal Jwt jwt) {
        return Map.of(
            "subject", jwt.getSubject(),
            "tenant", jwt.getClaimAsString("tenant_id")
        );
    }
}
```

Controller `/api/me` minh họa cách nhận `Jwt` principal qua `@AuthenticationPrincipal`. Trong ứng dụng thực, chỉ trả claims được phép công bố; không serialize toàn bộ token hoặc mọi claim một cách tùy tiện.

## 3. Cấu trúc cơ bản của jwt() post-processor

Import static thường dùng:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
```

`jwt()` đến từ `SecurityMockMvcRequestPostProcessors`.

Dùng helper trong một request:

```java
mvc.perform(get("/api/reports").with(jwt()))
    .andExpect(status().isOk());
```

Có thể đọc request này như sau:

1. `MockMvc` tạo request GET.
2. `jwt()` dựng một JWT principal/authentication giả lập và cung cấp nó cho request test.
3. Security chain xử lý request với authentication đã được cung cấp.
4. Authorization rule kiểm tra authority.
5. Nếu đủ quyền, request đi tiếp đến controller; nếu thiếu quyền, response bị từ chối.

`jwt()` không tạo một access token có chữ ký để gửi trong HTTP header. Nó cũng không gọi `JwtDecoder` để kiểm tra token. Do đó, không dùng test này để kết luận chữ ký hoặc expiration validation đang hoạt động.

### jwt() mặc định

Helper cung cấp một JWT mặc định tiện cho smoke test. Tuy nhiên, đừng phụ thuộc vào các claim mặc định nếu test cần chứng minh một policy cụ thể. Hãy khai báo tường minh subject, scope, issuer, tenant và những claim mà code đọc để test dễ hiểu và ổn định.

## 4. Kiểm tra scope với authorities mặc định

Với `JwtGrantedAuthoritiesConverter` mặc định, Spring Security đọc scope từ claim `scope` hoặc `scp` và tạo authority có prefix `SCOPE_`.

Ví dụ token claims:

```json
{
  "sub": "partner-42",
  "scope": "reports.read reports.export",
  "tenant_id": "acme"
}
```

Các authority tương ứng thường là:

- `SCOPE_reports.read`
- `SCOPE_reports.export`

Nếu rule dùng `hasAuthority("SCOPE_reports.read")`, test có thể dựng claim scope:

```java
@Test
void readerScopeCanReadReports() throws Exception {
    mvc.perform(get("/api/reports")
            .with(jwt().jwt(jwt -> jwt
                .claim("sub", "partner-42")
                .claim("scope", "reports.read"))))
        .andExpect(status().isOk());
}
```

Để kiểm tra scope thiếu:

```java
@Test
void writeOnlyScopeCannotReadReports() throws Exception {
    mvc.perform(get("/api/reports")
            .with(jwt().jwt(jwt -> jwt
                .claim("sub", "partner-42")
                .claim("scope", "reports.write"))))
        .andExpect(status().isForbidden());
}
```

Hai test này minh họa policy allow/deny. Với helper `jwt()`, request đã có authentication giả lập; vì vậy ca thiếu scope thường trả `403` chứ không phải `401`.

### Đặt authority trực tiếp

Có thể bỏ qua việc chuyển scope thành authority và đặt authority cụ thể:

```java
mvc.perform(get("/api/reports")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isOk());
```

Cách này hữu ích khi câu hỏi chỉ là “authorization rule có cho phép authority này không?”. Tuy nhiên, nó **không kiểm tra việc scope claim được ánh xạ thành authority**. Nếu muốn kiểm tra default scope mapping, hãy dựng claim và để helper dùng quy tắc mặc định; nếu muốn kiểm tra custom converter của ứng dụng, cần một test riêng cho converter và một integration test qua decoder thật.

## 5. Tùy chỉnh claims và subject

`jwt().jwt(...)` cho phép sửa JWT dùng trong test. Ví dụ:

```java
mvc.perform(get("/api/me")
        .with(jwt().jwt(jwt -> jwt
            .claim("sub", "partner-42")
            .claim("tenant_id", "acme")
            .claim("scope", "reports.read")
            .claim("region", "south"))))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.subject").value("partner-42"))
    .andExpect(jsonPath("$.tenant").value("acme"));
```

Có thể tùy chỉnh nhiều loại claim:

| Claim | Ví dụ | Mục đích kiểm thử |
|---|---|---|
| `sub` | `partner-42` | Định danh principal |
| `scope` | `reports.read` | Scope đọc API |
| `scp` | `["reports.read"]` | Biến thể claim scope dạng collection |
| `tenant_id` | `acme` | Phạm vi tenant |
| `iss` | `https://idp.example.test` | Issuer mà code có thể đọc |
| `aud` | `["reports-api"]` | Audience mà code có thể đọc |
| `email` | `an@example.test` | Claim định danh nếu policy sử dụng |
| `groups` | `["report-readers"]` | Nhóm ứng dụng nếu converter/policy sử dụng |

Các claim này được gán cho JWT giả lập. Chúng không được xác thực bởi decoder trong test post-processor. Đặt `iss` hoặc `aud` trong JWT giả lập **không chứng minh** ứng dụng thực sự từ chối issuer/audience sai.

### Kiểm tra principal trong controller

Nếu controller nhận `Jwt`:

```java
@GetMapping("/api/profile")
Profile profile(@AuthenticationPrincipal Jwt jwt) {
    return new Profile(
        jwt.getSubject(),
        jwt.getClaimAsString("tenant_id"));
}
```

Test có thể xác minh dữ liệu được đọc từ claim đúng:

```java
mvc.perform(get("/api/profile")
        .with(jwt().jwt(jwt -> jwt
            .claim("sub", "user-100")
            .claim("tenant_id", "acme"))))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.userId").value("user-100"))
    .andExpect(jsonPath("$.tenantId").value("acme"));
```

Đây là test mapping principal-to-response. Nếu tenant được dùng để cấp quyền truy cập dữ liệu, cần thêm test object/tenant authorization với fixture khác tenant, không chỉ kiểm tra response profile.

## 6. Dựng JWT hoàn chỉnh để kiểm tra nhiều thuộc tính cùng lúc

Có thể tạo một `Jwt` tùy chỉnh trước, sau đó đưa vào request:

```java
Jwt token = Jwt.withTokenValue("test-token")
    .header("alg", "none")
    .subject("partner-42")
    .claim("scope", "reports.read")
    .claim("tenant_id", "acme")
    .issuedAt(Instant.now().minusSeconds(60))
    .expiresAt(Instant.now().plusSeconds(300))
    .build();

mvc.perform(get("/api/reports")
        .with(jwt().jwt(token)))
    .andExpect(status().isOk());
```

Ví dụ tạo object JWT phục vụ test. `tokenValue` và header ở đây không tạo một token đã ký để gửi cho decoder; helper đưa object JWT vào authentication giả lập. Trường `expiresAt` trong object không khiến test tự kiểm tra expiration validator.

Khi test cần nhiều claims, tạo fixture helper có tên thể hiện mục đích:

```java
private static Jwt reportReaderJwt() {
    return Jwt.withTokenValue("report-reader-test-token")
        .header("alg", "none")
        .subject("partner-42")
        .claim("scope", "reports.read")
        .claim("tenant_id", "acme")
        .issuedAt(Instant.now().minusSeconds(30))
        .expiresAt(Instant.now().plusSeconds(300))
        .build();
}
```

Rồi sử dụng:

```java
mvc.perform(get("/api/reports")
        .with(jwt().jwt(reportReaderJwt())))
    .andExpect(status().isOk());
```

Không cần tạo token fixture toàn cục với mọi claim cho mọi test. Mỗi fixture chỉ nên chứa các thuộc tính liên quan đến policy để test không vô tình phụ thuộc claim không cần thiết.

## 7. Kiểm tra authority tùy chỉnh và custom converter

Một ứng dụng có thể nhận role từ claim `roles` thay vì scope. Ví dụ token:

```json
{
  "sub": "an",
  "roles": ["REPORT_ADMIN"],
  "tenant_id": "acme"
}
```

Ứng dụng cấu hình `JwtAuthenticationConverter` hoặc converter riêng để ánh xạ `roles` thành `GrantedAuthority`. Cần phân biệt hai câu hỏi:

1. **Policy có cho phép authority `REPORT_ADMIN` không?**
2. **Converter của ứng dụng có biến claim `roles` thành authority `REPORT_ADMIN` đúng không?**

Nếu dùng:

```java
mvc.perform(get("/api/admin/reports")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("REPORT_ADMIN"))))
    .andExpect(status().isOk());
```

test chỉ chứng minh câu hỏi 1. Authority đã được cấp trực tiếp; converter không được kiểm tra.

Để test converter, gọi converter thật với JWT fixture:

```java
Jwt jwt = Jwt.withTokenValue("test-token")
    .header("alg", "none")
    .subject("an")
    .claim("roles", List.of("REPORT_ADMIN"))
    .build();

AbstractAuthenticationToken authentication =
    jwtAuthenticationConverter.convert(jwt);

assertThat(authentication.getAuthorities())
    .extracting(GrantedAuthority::getAuthority)
    .contains("REPORT_ADMIN");
```

Đoạn này là unit test cho converter. Nó chưa chứng minh converter đã được gắn vào resource server chain. Muốn kiểm tra wiring, gửi một Bearer token thật được ký bằng key test qua decoder thật và assert endpoint áp dụng authority từ claim.

### Khi nào dùng authorities(...)?

Dùng `authorities(...)` khi muốn dựng kết quả cuối cùng của authentication cho test authorization. Không dùng nó để kết luận claim mapping hoặc converter production đúng.

## 8. Dùng jwt() trong @WebMvcTest

`@WebMvcTest` tạo MVC slice. Để kiểm tra request authorization, cần bảo đảm security configuration phù hợp được đưa vào context và filters vẫn được áp dụng.

Ví dụ:

```java
@WebMvcTest(ReportController.class)
@Import(ApiSecurityConfiguration.class)
class ReportJwtMvcTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    JwtDecoder jwtDecoder;

    @Test
    void readerCanAccessReport() throws Exception {
        mvc.perform(get("/api/reports")
                .with(jwt().jwt(jwt -> jwt
                    .claim("sub", "partner-42")
                    .claim("scope", "reports.read"))))
            .andExpect(status().isOk());
    }

    @Test
    void writerCannotAccessReport() throws Exception {
        mvc.perform(get("/api/reports")
                .with(jwt().jwt(jwt -> jwt
                    .claim("sub", "partner-42")
                    .claim("scope", "reports.write"))))
            .andExpect(status().isForbidden());
    }
}
```

`@MockitoBean JwtDecoder` được dùng ở đây để cung cấp bean cần thiết cho resource server configuration trong slice nếu không có decoder thật trong test context. Request dùng `jwt()` không gọi decoder mock; test đang kiểm tra authorization sau authentication. Với Spring Framework cũ hơn, dự án có thể dùng annotation mock bean tương ứng của Spring Boot.

Không đặt `@AutoConfigureMockMvc(addFilters = false)` trong test này. Nếu bỏ filters, assertion không chứng minh request authorization của resource server.

Nếu dùng `@WebMvcTest` mà security configuration không được nạp, hãy import cấu hình thực cần kiểm tra hoặc chọn integration test phù hợp. Đừng tạo test-only chain `permitAll()` chỉ để controller test chạy qua.

## 9. Dùng jwt() trong @SpringBootTest và kiểm tra method security

Khi cần nhiều bean thực hoặc muốn kiểm tra service/method security, dùng application context đầy đủ:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ReportJwtIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void tokenWithReadScopeCanRead() throws Exception {
        mvc.perform(get("/api/reports")
                .with(jwt().jwt(jwt -> jwt
                    .claim("scope", "reports.read"))))
            .andExpect(status().isOk());
    }

    @Test
    void tokenWithoutReadScopeIsForbidden() throws Exception {
        mvc.perform(get("/api/reports")
                .with(jwt().jwt(jwt -> jwt
                    .claim("scope", "reports.write"))))
            .andExpect(status().isForbidden());
    }
}
```

Đây là integration test của application context nhưng vẫn giả lập authentication JWT. Nó có thể kiểm tra chain, controller, service và method-security wiring nếu các thành phần đó thật sự được nạp và gọi. Nó **không** trở thành test decoder chỉ vì dùng `@SpringBootTest`.

Nếu service có `@PreAuthorize`, bảo đảm method security được bật và service được gọi qua Spring-managed proxy. Nếu policy nằm ở owner/tenant trong service, dùng fixture có nhiều owner/tenant và assert cả response lẫn dữ liệu.

## 10. JWT và method security

Có thể dùng cùng JWT principal để kiểm tra `@PreAuthorize`:

```java
@Service
class ReportAdminService {

    @PreAuthorize("hasAuthority('REPORT_ADMIN')")
    public String readAdminReport() {
        return "admin-report";
    }
}
```

MockMvc test:

```java
@Test
void reportAdminCanCallSecuredService() throws Exception {
    mvc.perform(get("/api/admin/reports")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("REPORT_ADMIN"))))
        .andExpect(status().isOk());
}

@Test
void reportReaderCannotCallAdminService() throws Exception {
    mvc.perform(get("/api/admin/reports")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_reports.read"))))
        .andExpect(status().isForbidden());
}
```

Các test chỉ có ý nghĩa nếu controller thực sự gọi service bean được bảo vệ và method security được bật. Nếu service bị mock, method-security interceptor của service không chạy. Nếu muốn test trực tiếp service, inject bean thật và gọi qua proxy trong context có `@EnableMethodSecurity`.

`jwt()` giúp tạo `JwtAuthenticationToken`; `@PreAuthorize` vẫn kiểm tra authorities của authentication đó như các loại authentication khác.

## 11. Phân biệt jwt() với @WithMockUser và user()

Ba cách này đều có thể dựng principal/authentication cho request test, nhưng loại principal khác nhau:

| Helper | Authentication/principal | Phù hợp khi |
|---|---|---|
| `@WithMockUser` | `UsernamePasswordAuthenticationToken` với user mặc định hoặc user fixture | Policy chỉ cần username và authorities |
| `user("an")` | User authentication gắn vào request Servlet | Muốn đổi principal/authority theo từng request |
| `jwt()` | `JwtAuthenticationToken` với principal là `Jwt` | Code đọc JWT claims, scope hoặc resource-server principal |

Nếu controller dùng `@AuthenticationPrincipal Jwt`, `jwt()` phù hợp hơn `@WithMockUser` vì principal đúng kiểu. Nếu policy chỉ kiểm tra authority chung và không phụ thuộc kiểu principal, cả hai có thể dùng được; nên chọn helper gần với cách ứng dụng thực thi.

Không kết luận rằng `@WithMockUser` là kiểm thử JWT chỉ vì authority trùng với scope. Nó không tạo `Jwt` principal và không kiểm tra resource server behavior.

## 12. Những điều jwt() không kiểm tra

Đây là giới hạn quan trọng nhất của helper:

| Mục tiêu | `jwt()` có kiểm tra không? | Test phù hợp |
|---|---|---|
| Rule `hasAuthority("SCOPE_reports.read")` | Có | `jwt()` với authority/claim tương ứng |
| Controller đọc `sub` hoặc `tenant_id` | Có | `jwt()` với claims được dựng |
| `@PreAuthorize` dựa trên authority | Có, nếu gọi qua proxy thật | `jwt()` + application context/method security |
| Custom converter ánh xạ claim | Không nếu đặt authorities trực tiếp; helper không nên được xem là bằng chứng converter production được gọi | Unit test converter và integration với Bearer token thật |
| Token parse/format | Không | Bearer header qua decoder |
| Chữ ký token | Không | Decoder thật và token ký bằng test key |
| Expiration `exp` | Không | Decoder/validator thật với token hết hạn |
| Issuer `iss` | Không | Decoder thật có issuer validator |
| Audience `aud` | Không | Decoder thật có audience validator được cấu hình |
| Bearer header/filter hoạt động | Không | Gửi `Authorization: Bearer ...` qua filter chain |
| Token revocation/introspection | Không | Test introspection/revocation mechanism thật |
| OAuth2 authorization code / OIDC login flow | Không | Integration/E2E với IdP test |

`jwt()` có thể tạo claim `iss`, `aud` và `exp` nhưng chỉ đặt giá trị vào object JWT test. Sự hiện diện của claim không có nghĩa validator đã chạy. Nếu muốn xác minh token hết hạn bị từ chối, cần token thực sự được decoder xác minh và có thời điểm hết hạn trong quá khứ.

## 13. Kiểm tra token thật qua decoder với MockMvc

Khi muốn xác minh authentication, gửi Bearer header:

```java
mvc.perform(get("/api/reports")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + signedAccessToken))
    .andExpect(status().isOk());
```

Trong test này:

1. Request đi qua Bearer token authentication filter.
2. Filter trích token từ header.
3. `JwtDecoder` xác minh token theo cấu hình.
4. Validators kiểm tra claims như issuer và timestamp; audience cần validator nếu policy yêu cầu.
5. Converter tạo authorities từ claims.
6. Authorization rule quyết định request được phép hay bị từ chối.

### Tạo token kiểm thử an toàn

Một cách thông dụng là tạo cặp khóa RSA dành riêng cho test:

- Private key chỉ dùng ký token trong fixture test.
- Public key được cấu hình cho decoder test.
- Issuer và audience dùng giá trị test đã thống nhất.
- Không dùng private key production hoặc token production trong test.

Có thể dùng `NimbusJwtEncoder` để ký token với claims được tạo bằng `JwtClaimsSet`. Tạo ít nhất:

- Token hợp lệ có scope `reports.read`.
- Token hợp lệ nhưng thiếu scope.
- Token hết hạn nhưng chữ ký/issuer còn hợp lệ.
- Token ký bằng key khác.
- Token sai issuer.
- Token sai audience nếu ứng dụng có audience validator.

Mỗi test nên chỉ thay một thuộc tính so với token hợp lệ để biết validator nào đang được kiểm tra. Đặc biệt, `JwtValidators.createDefaultWithIssuer(...)` kiểm tra issuer và các validator mặc định; nếu yêu cầu audience, hãy cấu hình audience validator riêng, không giả định validator mặc định tự kiểm tra `aud`.

Ví dụ test token hết hạn:

```java
@Test
void expiredSignedTokenIsRejectedByDecoder() throws Exception {
    mvc.perform(get("/api/reports")
            .header(HttpHeaders.AUTHORIZATION,
                "Bearer " + expiredSignedToken))
        .andExpect(status().isUnauthorized());
}
```

`expiredSignedToken` phải được ký bằng key test mà decoder tin cậy, có issuer đúng và `exp` đã quá hạn. Nếu chỉ dùng chuỗi token ngẫu nhiên, test có thể chỉ chứng minh parse/signature failure chứ không chứng minh expiration validation.

### Có cả positive control

Nếu mọi token đều nhận `401`, test token hết hạn có thể xanh dù decoder bị cấu hình sai và từ chối tất cả. Cần có token hợp lệ được chấp nhận để xác nhận đường xác thực hoạt động.

## 14. Kiểm tra scope mapping thực tế

Với default converter, claim `scope` dạng chuỗi phân tách bằng khoảng trắng thường được chuyển thành authority có prefix `SCOPE_`. Nhưng ứng dụng có thể tùy biến:

- Dùng claim `roles`.
- Dùng `scp` dạng mảng.
- Thay prefix `SCOPE_`.
- Kết hợp nhóm và scope.
- Ánh xạ claim tenant/organization thành policy riêng.

Để kiểm tra mapping, có ba lớp bằng chứng:

1. **Unit test converter:** cung cấp JWT fixture và kiểm tra danh sách authority đầu ra.
2. **Authorization test bằng jwt():** đặt authority cuối cùng để kiểm tra rule có quyết định đúng không.
3. **Integration test token thật:** Bearer header qua decoder và converter production, rồi kiểm tra endpoint.

Ví dụ converter mặc định có thể được cấu hình thành bean:

```java
@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter authorities =
        new JwtGrantedAuthoritiesConverter();

    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();

    converter.setJwtGrantedAuthoritiesConverter(authorities);
    return converter;
}
```

Nếu custom converter dùng claim riêng, unit test cần tạo claim đó và xác minh authority. Integration test cần chắc chắn converter được gắn vào `oauth2ResourceServer().jwt()` của security chain.

## 15. CSRF và JWT trong MockMvc

Một API resource server thuần Bearer token thường nhận credentials qua Authorization header do client chủ động gửi, nên mô hình CSRF khác ứng dụng session/cookie. Không tự động áp dụng hoặc tắt CSRF chỉ vì endpoint dùng JWT; quyết định dựa trên cách credentials được trình duyệt gửi và kiến trúc ứng dụng.

Nếu endpoint có CSRF protection (ví dụ cùng ứng dụng có session-based web flow), `jwt()` không thay thế CSRF token. Với POST/PUT/PATCH/DELETE, test cần cung cấp token hợp lệ khi mục tiêu là authorization:

```java
mvc.perform(post("/api/reports/export")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.export")))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"format\":\"CSV\"}"))
    .andExpect(status().isAccepted());
```

Và test CSRF riêng:

```java
mvc.perform(post("/api/reports/export")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.export")))
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"format\":\"CSV\"}"))
    .andExpect(status().isForbidden());
```

Hai ca giả định CSRF được bật cho endpoint này. Nếu test thiếu CSRF nhưng mục tiêu là quyền scope, `403` có thể đến từ CSRF filter trước khi authorization rule được kiểm tra.

## 16. Data-driven tests cho nhiều scope

Khi nhiều endpoint có policy theo scope, dùng `@ParameterizedTest` để kiểm tra allow/deny:

```java
static Stream<Arguments> reportScopeCases() {
    return Stream.of(
        Arguments.of("reports.read", 200),
        Arguments.of("reports.write", 403),
        Arguments.of("orders.read", 403)
    );
}

@ParameterizedTest
@MethodSource("reportScopeCases")
void reportEndpointRequiresReadScope(
        String scope,
        int expectedStatus) throws Exception {

    mvc.perform(get("/api/reports")
            .with(jwt().jwt(jwt -> jwt.claim("scope", scope))))
        .andExpect(status().is(expectedStatus));
}
```

Cần có positive control scope đúng và ít nhất một negative control đã xác thực nhưng thiếu scope. Nếu endpoint hỗ trợ nhiều scope, tạo từng ca theo contract rõ ràng thay vì gộp thành một chuỗi test khó đọc.

Nếu app có custom converter, test data-driven dùng `jwt()` cần lưu ý helper có thể dựng authority theo cơ chế test của nó, không chạy converter production. Hãy dùng token thật qua decoder cho integration coverage của mapping.

## 17. Các lỗi thường gặp khi dùng jwt()

| Lỗi | Vì sao sai | Cách sửa |
|---|---|---|
| Dùng `jwt()` để kiểm tra chữ ký | Helper không gọi decoder xác minh token | Gửi Bearer token thật qua decoder |
| Đặt `authorities(...)` rồi kết luận scope mapping đúng | Authority được gán trực tiếp | Test converter riêng và integration token thật |
| Chỉ test scope đúng | Rule có thể bị mở thành authenticated-only | Thêm JWT đã xác thực nhưng thiếu scope |
| Dùng `@WithMockUser` khi controller cần `Jwt` principal | Principal mặc định không phải `Jwt` | Dùng `jwt()` với claims cần thiết |
| Tắt filters | Request không đi qua security chain | Giữ filter chain trong MockMvc |
| Mock `JwtDecoder` rồi kết luận token hết hạn bị chặn | Decoder thật không chạy | Dùng decoder và validator thật |
| Chỉ test `@SpringBootTest` rồi kết luận Bearer flow thật | Authentication vẫn có thể được helper dựng sẵn | Gửi Authorization header với token ký thật |
| Gán `iss`/`aud` trong mock JWT rồi kết luận validator hoạt động | Claims chỉ là dữ liệu test | Token thật qua decoder có validators |
| Không có positive control | Decoder có thể từ chối mọi token mà test vẫn xanh | Thêm token hợp lệ được chấp nhận |
| Nhầm scope với role | `SCOPE_reports.read` khác `ROLE_REPORTS` | Dùng authority đúng theo converter/policy |

## 18. Bài tập thực hành: resource server cho báo cáo đối tác

Một API có các endpoint:

- `GET /partner/reports` yêu cầu `SCOPE_reports.read`.
- `POST /partner/reports/export` yêu cầu `SCOPE_reports.export`.
- Claim `tenant_id` giới hạn dữ liệu theo tenant.
- Claim `iss` phải thuộc issuer được tin cậy.
- Claim `aud` phải chứa `reports-api`.
- Token phải còn hạn và có chữ ký hợp lệ.

Hãy viết các nhóm test:

1. **Authorization với jwt():** scope `reports.read` được phép; `reports.write` bị `403`.
2. **Principal claims:** `/api/me` trả đúng `sub` và tenant được dựng trong JWT fixture.
3. **Tenant policy:** cùng scope nhưng tenant khác bị từ chối khi truy cập report của tenant khác.
4. **Custom converter:** nếu app dùng claim `roles` hoặc `groups`, unit test converter và kiểm tra authority đầu ra.
5. **Authentication thật:** token hết hạn, sai chữ ký, sai issuer và sai audience đi qua decoder thật và bị từ chối.
6. **Positive control:** token hợp lệ, đúng issuer/audience, còn hạn và có scope phù hợp được phép.
7. **CSRF:** nếu export endpoint thuộc nhánh session/cookie có CSRF, kiểm tra token thiếu và hợp lệ riêng biệt; nếu API Bearer stateless, ghi rõ lý do policy khác.
8. **Side effect:** token thiếu scope hoặc sai tenant không gọi export service, không tạo file và không phát event.

Với mỗi test, ghi rõ helper hoặc credential được dùng, lớp nào thực sự chạy và điều gì **không** được test đó chứng minh.

**Tiêu chí hoàn thành:** Bạn có thể dùng `jwt()` để dựng đúng principal, claims và authorities cho các ca authorization của MockMvc; đồng thời biết lúc nào phải gửi Bearer token thật qua `JwtDecoder` để kiểm tra authentication. Khi phân biệt được hai phạm vi này, test sẽ vừa nhanh, dễ kiểm soát vừa không phóng đại bằng chứng về bảo mật resource server.
