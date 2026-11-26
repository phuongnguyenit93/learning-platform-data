# Tùy chỉnh subject, header và claims trong Jwt giả lập

> **Chương:** JWT với MockMvc  
> **Module:** `SPRING_SECURITY_TESTING` — kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên ứng dụng Servlet và Reactive. Bài này hướng dẫn tạo JWT giả lập có subject, JOSE header và claims theo từng tình huống để kiểm thử resource server bằng `MockMvc`.

## 1. Vì sao cần tùy chỉnh Jwt trong test?

Một request đến resource server thường được xác thực từ Bearer token. Sau khi decoder chấp nhận token, ứng dụng có thể đọc nhiều thuộc tính:

- `sub` xác định subject, thường là người dùng hoặc service account.
- `iss` cho biết issuer phát hành token.
- `aud` xác định API hoặc nhóm API mà token hướng đến.
- `exp` và `iat` biểu diễn thời điểm hết hạn và thời điểm phát hành.
- `scope` hoặc `scp` mô tả quyền theo OAuth2 scope.
- `tenant_id`, `roles`, `groups` hoặc claim riêng mang dữ liệu nghiệp vụ do issuer tin cậy cung cấp.
- JOSE header như `kid`, `typ` và `alg` mô tả metadata của token ở phần header.

Trong kiểm thử authorization, ta thường muốn thay đổi từng thuộc tính mà không phải tạo token ký thật cho mọi trường hợp. Helper `jwt()` trong `spring-security-test` cho phép dựng `Jwt` giả lập và gắn một `JwtAuthenticationToken` vào request MockMvc.

Ví dụ:

```java
mvc.perform(get("/api/reports")
        .with(jwt().jwt(jwt -> jwt
            .subject("partner-42")
            .claim("tenant_id", "acme")
            .claim("scope", "reports.read"))))
    .andExpect(status().isOk());
```

Test này có thể kiểm tra policy sử dụng subject, tenant hoặc scope của principal. Nó không cần gửi một compact JWT đã ký qua HTTP header.

Điều cần phân biệt:

- **JWT giả lập:** object `Jwt` được tạo trong test; test kiểm soát header và claims.
- **JWT thật:** chuỗi token được gửi trong `Authorization: Bearer ...` và được `JwtDecoder` xác minh.
- **Authentication giả lập:** `jwt()` cung cấp authentication cho request để test phần sau authentication.
- **Authentication thực:** Bearer filter đọc token, decoder/validators kiểm tra token, converter ánh xạ authorities.

Bài này tập trung vào cách dựng JWT object có dữ liệu đúng với kịch bản test và cách hiểu giới hạn của bằng chứng đó.

## 2. Phân biệt JOSE header với claims

JWT dạng JWS compact thường gồm ba phần: header, payload và signature. JWE có cấu trúc compact khác. Header và payload của JWS đều chứa dữ liệu JSON nhưng có mục đích khác nhau.

```text
BASE64URL(header) . BASE64URL(payload) . signature

Header:
  alg, kid, typ, ...

Claims / payload:
  iss, sub, aud, exp, iat, jti, scope, tenant_id, ...
```

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| JOSE header `alg` | `RS256` | Thuật toán ký được khai báo trong token |
| JOSE header `kid` | `rsa-test-01` | Gợi ý định danh khóa trong JWKS/key set |
| JOSE header `typ` | `JWT` | Loại nội dung token |
| Claim `iss` | `https://idp.example.test` | Issuer |
| Claim `sub` | `partner-42` | Subject |
| Claim `aud` | `["reports-api"]` | Audience |
| Claim `exp` | Thời điểm tương lai/quá khứ | Thời điểm hết hạn |
| Claim `scope` | `reports.read reports.export` | Scope |
| Claim `tenant_id` | `acme` | Tenant theo hợp đồng của issuer |

Trong `Jwt` của Spring Security:

- Header được đọc qua `jwt.getHeaders()` hoặc `jwt.getHeaders().get("kid")`.
- Claims được đọc qua `jwt.getClaims()`, `jwt.getClaim("tenant_id")` hoặc các accessor như `getSubject()`, `getIssuer()`, `getAudience()`, `getExpiresAt()`.
- `sub` không phải header; `kid` không phải claim.
- Việc đặt header `alg` hoặc claim `iss` trong object giả lập không chứng minh chữ ký hay issuer đã được xác minh.

Một lỗi test dễ gặp là đặt `kid` trong payload rồi kiểm tra code đọc header, hoặc đặt `tenant_id` trong header rồi kỳ vọng controller đọc nó như claim. Hãy đặt dữ liệu đúng phần mà ứng dụng thực sự sử dụng.

## 3. Cấu trúc Jwt.Builder và hai cách truyền vào jwt()

`SecurityMockMvcRequestPostProcessors.jwt()` hỗ trợ tạo authentication với một JWT mặc định hoặc nhận JWT đã dựng.

Cách thứ nhất: cấu hình builder qua consumer:

```java
mvc.perform(get("/api/reports")
        .with(jwt().jwt(jwt -> jwt
            .subject("partner-42")
            .claim("tenant_id", "acme")
            .claim("scope", "reports.read"))))
    .andExpect(status().isOk());
```

Cách thứ hai: tạo object `Jwt` trước rồi truyền vào:

```java
Jwt mockToken = Jwt.withTokenValue("mock-token")
    .header("alg", "none")
    .subject("partner-42")
    .claim("tenant_id", "acme")
    .claim("scope", "reports.read")
    .issuedAt(Instant.parse("2026-01-01T00:00:00Z"))
    .expiresAt(Instant.parse("2027-01-01T00:00:00Z"))
    .build();

mvc.perform(get("/api/reports")
        .with(jwt().jwt(mockToken)))
    .andExpect(status().isOk());
```

Các fluent method thường dùng trên `Jwt.Builder`:

| Method | Dữ liệu được thiết lập |
|---|---|
| `header(name, value)` | Một JOSE header |
| `headers(consumer)` hoặc thao tác header tương ứng của builder | Nhiều header |
| `claim(name, value)` | Một claim |
| `claims(consumer)` | Cập nhật nhiều claims |
| `subject(value)` | Claim `sub` |
| `issuer(uri)` | Claim `iss` |
| `audience(list)` | Claim `aud` |
| `issuedAt(instant)` | Claim `iat` |
| `expiresAt(instant)` | Claim `exp` |
| `id(value)` | Claim `jti` |

Tên API và overload cần khớp phiên bản Spring Security mà dự án đang dùng. Ví dụ trên sử dụng các fluent method phổ biến của `Jwt.Builder`.

`tokenValue("mock-token")` chỉ đặt giá trị token trong object. Nó không ký chuỗi, không tạo compact JWT hợp lệ và không khiến decoder xác minh chữ ký.

## 4. Tùy chỉnh subject và ý nghĩa của principal name

`sub` là subject của JWT. Với `JwtAuthenticationToken` mặc định, tên authentication thường được lấy từ subject claim. Vì vậy, thay subject có thể thay đổi kết quả của `Authentication.getName()`.

Ví dụ:

```java
@Test
void subjectBecomesAuthenticationName() throws Exception {
    mvc.perform(get("/api/me")
            .with(jwt().jwt(jwt -> jwt
                .subject("partner-42")
                .claim("tenant_id", "acme"))))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.subject").value("partner-42"));
}
```

Controller:

```java
@GetMapping("/api/me")
Map<String, String> me(Authentication authentication) {
    JwtAuthenticationToken jwtAuth =
        (JwtAuthenticationToken) authentication;

    return Map.of(
        "subject", jwtAuth.getName(),
        "tenant", jwtAuth.getToken().getClaimAsString("tenant_id")
    );
}
```

Có thể kiểm tra authentication state qua matcher:

```java
mvc.perform(get("/api/me")
        .with(jwt().jwt(jwt -> jwt.subject("partner-42"))))
    .andExpect(authenticated().withUsername("partner-42"));
```

Lưu ý:

- `@AuthenticationPrincipal Jwt jwt` nhận object JWT làm principal trong resource server flow.
- `Authentication.getName()` thường dựa trên `sub` mặc định của `JwtAuthenticationToken`.
- Ứng dụng có thể cấu hình claim khác làm principal name thông qua converter. Khi đó không được giả định username luôn bằng `sub`.
- Nếu code dùng custom principal thay vì `Jwt`, hãy test đúng kiểu principal mà ứng dụng thực sự tạo.

## 5. Tùy chỉnh JOSE header

Header có thể được thêm bằng `header(name, value)` khi dựng JWT:

```java
mvc.perform(get("/api/me")
        .with(jwt().jwt(jwt -> jwt
            .subject("partner-42")
            .header("kid", "rsa-test-01")
            .header("typ", "JWT")
            .claim("scope", "reports.read"))))
    .andExpect(status().isOk());
```

Controller hoặc service có thể đọc header qua `Jwt.getHeaders()` nếu ứng dụng có use case hợp lệ. Thông thường `kid` phục vụ việc chọn khóa khi decoder xử lý token đã ký; code nghiệp vụ không nên dùng header tùy ý như nguồn cấp quyền.

### Header alg trong JWT giả lập

Một object test có thể có header:

```java
Jwt token = Jwt.withTokenValue("mock-token")
    .header("alg", "RS256")
    .header("kid", "test-key-01")
    .subject("partner-42")
    .claim("scope", "reports.read")
    .build();
```

Điều đó **không có nghĩa token đã được ký bằng RS256**. Header chỉ là dữ liệu trong object. Không thể dùng ví dụ này để kiểm tra thuật toán ký, key selection, signature verification hoặc algorithm allow-list của decoder.

Nếu muốn kiểm tra `kid` thực sự chọn đúng public key, hãy tạo token compact được ký bằng private key test, cấu hình JWKS/key source phù hợp và gửi Bearer header qua decoder thật.

## 6. Tùy chỉnh standard claims

Các standard claims thường được cung cấp bằng fluent method để giữ đúng kiểu dữ liệu:

```java
Jwt token = Jwt.withTokenValue("mock-token")
    .header("alg", "none")
    .subject("partner-42")
    .issuer(URI.create("https://idp.example.test"))
    .audience(List.of("reports-api"))
    .issuedAt(Instant.parse("2026-11-25T08:00:00Z"))
    .expiresAt(Instant.parse("2026-11-25T09:00:00Z"))
    .id("jwt-test-100")
    .claim("scope", "reports.read")
    .build();
```

| Claim | Accessor thường dùng | Ý nghĩa |
|---|---|---|
| `iss` | `getIssuer()` | Issuer URI |
| `sub` | `getSubject()` | Subject |
| `aud` | `getAudience()` | Danh sách audience |
| `exp` | `getExpiresAt()` | Expiration instant |
| `iat` | `getIssuedAt()` | Issued-at instant |
| `jti` | `getId()` | JWT identifier |
| Custom | `getClaim(name)` | Claim theo tên |

Có thể dùng `claim("custom_name", value)` cho dữ liệu riêng. Với standard claims, fluent method giúp biểu đạt rõ mục đích và kiểu dữ liệu mong đợi.

### Thời gian nên cố định trong test

Tránh dùng `Instant.now()` tùy tiện trong test kiểm tra policy không liên quan thời gian. Thời gian động làm test khó tái hiện và có thể gây flaky ở ranh giới hết hạn.

Dùng thời điểm cố định hoặc một `Clock` được kiểm soát nếu code nghiệp vụ thực sự đọc thời gian. Tuy nhiên, nhớ rằng JWT giả lập qua `jwt()` không tự chạy expiration validator; test expiration phải qua decoder thật.

## 7. Tùy chỉnh custom claims

Custom claims thường mô tả tenant, tổ chức, nhóm, vùng dữ liệu hoặc thuộc tính nghiệp vụ:

```java
mvc.perform(get("/api/partner/profile")
        .with(jwt().jwt(jwt -> jwt
            .subject("partner-42")
            .claim("tenant_id", "acme")
            .claim("partner_type", "reseller")
            .claim("region", "south")
            .claim("account_status", "ACTIVE"))))
    .andExpect(status().isOk());
```

Một số kiểu dữ liệu phổ biến:

| Kiểu | Ví dụ | Dùng khi |
|---|---|---|
| String | `"acme"` | ID, code, trạng thái |
| Number | `3` hoặc `125000` | Hạn mức, cấp độ |
| Boolean | `true` | Cờ theo contract |
| List | `List.of("REPORT_READ", "EXPORT")` | Nhóm hoặc scope dạng collection |
| Map | `Map.of("region", "south")` | Claim lồng nhau theo schema |
| Instant | Dùng fluent `issuedAt`/`expiresAt` cho thời gian chuẩn | `iat`/`exp` |

Claims cuối cùng cần có kiểu dữ liệu mà converter/controller/policy mong đợi. Một claim `tenant_id` là chuỗi nhưng test lại cung cấp số có thể dẫn đến hành vi khác; đừng chỉ kiểm tra response status mà bỏ qua kiểu dữ liệu.

### Claim lồng nhau

Ví dụ issuer gửi:

```json
{
  "sub": "partner-42",
  "organization": {
    "tenant": "acme",
    "region": "south"
  }
}
```

Có thể dựng:

```java
mvc.perform(get("/api/partner/profile")
        .with(jwt().jwt(jwt -> jwt
            .subject("partner-42")
            .claim("organization", Map.of(
                "tenant", "acme",
                "region", "south")))))
    .andExpect(status().isOk());
```

Nếu policy đọc claim lồng nhau, kiểm tra cả trường hợp map thiếu key hoặc có giá trị sai kiểu. Không giả định claim luôn đầy đủ chỉ vì issuer bình thường gửi đủ; test biên giúp phát hiện null dereference hoặc fail-open.

## 8. Sử dụng claims(consumer) để dựng nhiều claim

Khi có nhiều claim, có thể nhóm chúng trong consumer thay vì nối nhiều lời gọi `claim`:

```java
mvc.perform(get("/api/reports")
        .with(jwt().jwt(jwt -> jwt
            .subject("partner-42")
            .claims(claims -> {
                claims.put("tenant_id", "acme");
                claims.put("scope", "reports.read reports.export");
                claims.put("partner_type", "reseller");
            }))))
    .andExpect(status().isOk());
```

Cách này hữu ích khi fixture được dựng từ dữ liệu test hoặc cần xóa/thay đổi claim trong một block. Hãy giữ mỗi fixture ngắn và chỉ chứa claim liên quan đến tình huống.

Ví dụ helper:

```java
private static RequestPostProcessor partnerJwt(
        String subject,
        String tenant,
        String scope) {

    return jwt().jwt(jwt -> jwt
        .subject(subject)
        .claim("tenant_id", tenant)
        .claim("scope", scope));
}
```

Dùng helper:

```java
mvc.perform(get("/api/reports")
        .with(partnerJwt("partner-42", "acme", "reports.read")))
    .andExpect(status().isOk());
```

Helper nên đặt tên theo vai trò nghiệp vụ như `partnerReaderJwt` hoặc `tenantAdminJwt`, tránh tên chung như `defaultJwt` khi nhiều policy cần claim khác nhau.

## 9. Phân biệt claim vắng mặt, null, rỗng và sai kiểu

Đây là các trường hợp khác nhau và có thể làm thay đổi quyết định:

| Trạng thái | Ví dụ | Điều cần kiểm tra |
|---|---|---|
| Không có claim | Không thêm `tenant_id` | Policy xử lý thiếu tenant như thế nào? |
| Claim có giá trị null | `tenant_id = null` nếu fixture/API cho phép | Có fail closed không? |
| Chuỗi rỗng | `tenant_id = ""` | Có bị coi là tenant hợp lệ không? |
| Chuỗi khoảng trắng | `tenant_id = " "` | Có normalize/validate không? |
| Sai kiểu | `tenant_id = 123` | Converter/policy có xử lý an toàn không? |
| Giá trị không tồn tại | `tenant_id = "unknown"` | Có truy cập nhầm dữ liệu mặc định không? |

Để tạo claim null, không dùng `Map.of` vì Java không cho phép null value; dùng consumer:

```java
mvc.perform(get("/api/reports")
        .with(jwt().jwt(jwt -> jwt
            .subject("partner-42")
            .claims(claims -> claims.put("tenant_id", null)))))
    .andExpect(status().isForbidden());
```

Kỳ vọng `403` chỉ phù hợp nếu policy của endpoint quy định thiếu/null tenant bị từ chối. Nếu API cố tình trả `404` để che giấu tài nguyên, dùng status đó theo contract.

Trong code ứng dụng, phân biệt `containsClaim("tenant_id")` với `getClaimAsString("tenant_id")` trả null. Đừng chuyển claim thiếu thành tenant mặc định như `public` hoặc tenant của hệ thống nếu không có policy rõ ràng.

## 10. Scope claim: string, scp collection và authority

Với cấu hình mặc định thường gặp, scope trong claim `scope` dạng chuỗi được phân tách bằng khoảng trắng và chuyển thành authority có prefix `SCOPE_`:

```java
mvc.perform(get("/api/reports")
        .with(jwt().jwt(jwt -> jwt
            .subject("partner-42")
            .claim("scope", "reports.read reports.export"))))
    .andExpect(status().isOk());
```

Kết quả authority dự kiến gồm `SCOPE_reports.read` và `SCOPE_reports.export` khi dùng converter mặc định tương ứng.

Một issuer khác có thể phát claim `scp` dạng collection:

```java
mvc.perform(get("/api/reports")
        .with(jwt().jwt(jwt -> jwt
            .subject("partner-42")
            .claim("scp", List.of("reports.read", "reports.export")))))
    .andExpect(status().isOk());
```

Cách ánh xạ thực tế phụ thuộc `JwtGrantedAuthoritiesConverter`/custom converter và cách `jwt()` dựng authentication. Nếu test cần kiểm tra custom mapping production, đừng chỉ gán authority cuối cùng bằng `authorities(...)`. Viết unit test converter và integration test với Bearer token thật qua decoder/converter được cấu hình.

### Đặt authorities trực tiếp

`jwt().authorities(...)` cho phép cấp authority cụ thể:

```java
mvc.perform(get("/api/admin/reports")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("REPORT_ADMIN"))))
    .andExpect(status().isOk());
```

Đây là cách cô lập policy authorization. Nó không chứng minh claim `roles`, `groups` hoặc `scope` được chuyển thành `REPORT_ADMIN` đúng cách.

## 11. Header và claims có thể được đọc trong controller như thế nào?

Nếu controller nhận `Jwt` qua `@AuthenticationPrincipal`, có thể đọc header và claims:

```java
@GetMapping("/api/token-info")
Map<String, Object> tokenInfo(@AuthenticationPrincipal Jwt jwt) {
    return Map.of(
        "subject", jwt.getSubject(),
        "tenant", jwt.getClaimAsString("tenant_id"),
        "keyId", String.valueOf(jwt.getHeaders().get("kid"))
    );
}
```

Test:

```java
mvc.perform(get("/api/token-info")
        .with(jwt().jwt(jwt -> jwt
            .subject("partner-42")
            .header("kid", "test-key-01")
            .claim("tenant_id", "acme"))))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.subject").value("partner-42"))
    .andExpect(jsonPath("$.tenant").value("acme"))
    .andExpect(jsonPath("$.keyId").value("test-key-01"));
```

Ví dụ chỉ để minh họa cách object JWT cung cấp header/claims. Trong API production, không nên trả thông tin nội bộ của token chỉ để test. Nếu `kid` không phải dữ liệu công khai cần thiết, kiểm tra nó ở tầng converter/decoder hoặc trong test component, không đưa ra response người dùng.

**Không dùng JOSE header làm quyền nghiệp vụ.** `kid` chỉ định danh khóa, `alg` mô tả thuật toán, `typ` mô tả loại token. Không nên cho phép thao tác admin chỉ vì header chứa `typ = "admin"` hoặc `kid` có tên đặc biệt.

## 12. Dùng Jwt giả lập trong @WebMvcTest

`@WebMvcTest` nạp MVC slice. Khi test resource server authorization, cần đưa security configuration cần kiểm tra vào context và bảo đảm filters được áp dụng.

Ví dụ:

```java
@WebMvcTest(ReportController.class)
@Import(ApiSecurityConfiguration.class)
class ReportClaimsMvcTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    JwtDecoder jwtDecoder;

    @Test
    void reportReaderFromAcmeCanRead() throws Exception {
        mvc.perform(get("/api/reports")
                .with(jwt().jwt(jwt -> jwt
                    .subject("partner-42")
                    .claim("tenant_id", "acme")
                    .claim("scope", "reports.read"))))
            .andExpect(status().isOk());
    }

    @Test
    void writerScopeCannotRead() throws Exception {
        mvc.perform(get("/api/reports")
                .with(jwt().jwt(jwt -> jwt
                    .subject("partner-42")
                    .claim("tenant_id", "acme")
                    .claim("scope", "reports.write"))))
            .andExpect(status().isForbidden());
    }
}
```

Trong một số web slice, bean `JwtDecoder` có thể cần hiện diện để resource server configuration khởi tạo; có thể cung cấp mock bean nếu test chỉ dùng `jwt()` và không kiểm tra decoder. Request post-processor `jwt()` dựng authentication trực tiếp nên không gọi decoder mock.

Với Spring Framework phiên bản hỗ trợ `@MockitoBean`, dùng annotation đó; dự án cũ có thể dùng mock-bean annotation tương ứng. Không dùng `addFilters = false` và không thay security configuration bằng `permitAll()`.

## 13. Dùng Jwt fixture trong @SpringBootTest

Khi cần application context rộng hơn, dùng `@SpringBootTest` và `@AutoConfigureMockMvc`:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ReportTenantJwtIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void acmePartnerReadsAcmeReport() throws Exception {
        mvc.perform(get("/api/reports/R-100")
                .with(jwt().jwt(jwt -> jwt
                    .subject("partner-42")
                    .claim("tenant_id", "acme")
                    .claim("scope", "reports.read"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.tenant").value("acme"));
    }

    @Test
    void betaPartnerCannotReadAcmeReport() throws Exception {
        mvc.perform(get("/api/reports/R-100")
                .with(jwt().jwt(jwt -> jwt
                    .subject("partner-99")
                    .claim("tenant_id", "beta")
                    .claim("scope", "reports.read"))))
            .andExpect(status().isForbidden());
    }
}
```

Ví dụ giả định policy tenant thực sự dùng claim `tenant_id` và dữ liệu `R-100` thuộc `acme`. Nếu service kiểm tra tenant, service và policy phải là thành phần thật trong test; mock repository chỉ phù hợp khi mục tiêu là unit test policy. Nếu muốn chứng minh query DB có tenant filter, dùng integration test với database test.

`@SpringBootTest` không biến JWT giả lập thành token thật. Nó chỉ mở rộng phạm vi application context.

## 14. Kiểm tra custom claim với method security

Method security có thể dùng authority, hoặc gọi bean policy để kiểm tra claim/tenant. Ví dụ service được bảo vệ bằng authority:

```java
@Service
class PartnerReportService {

    @PreAuthorize("hasAuthority('SCOPE_reports.read')")
    public String read() {
        return "partner-report";
    }
}
```

MockMvc test:

```java
mvc.perform(get("/partner/reports")
        .with(jwt().jwt(jwt -> jwt
            .subject("partner-42")
            .claim("scope", "reports.read"))))
    .andExpect(status().isOk());

mvc.perform(get("/partner/reports")
        .with(jwt().jwt(jwt -> jwt
            .subject("partner-42")
            .claim("scope", "reports.write"))))
    .andExpect(status().isForbidden());
```

Để kiểm chứng `@PreAuthorize`, service phải là Spring-managed bean thật, method security phải được bật và controller phải gọi qua proxy. Nếu mock service, annotation trên implementation không chạy.

Với policy tenant phức tạp, có thể dùng bean policy:

```java
@PreAuthorize("@tenantPolicy.canRead(authentication, #tenantId)")
public Report read(String tenantId) {
    return repository.load(tenantId);
}
```

Test cần dựng claim tenant đúng/sai, gọi service thật qua proxy và kiểm tra dependency. Nếu expression đọc `JwtAuthenticationToken.getToken()` hoặc custom principal, fixture phải có đúng loại authentication và claim.

## 15. Những gì việc tùy chỉnh Jwt không chứng minh

Dù có thể tùy chỉnh `alg`, `kid`, `iss`, `aud`, `exp` và `iat`, helper vẫn dựng object JWT trong request test. Nó không thay thế decoder.

| Điều muốn chứng minh | Tùy chỉnh Jwt với `jwt()` có đủ không? | Bằng chứng cần thêm |
|---|---|---|
| Controller đọc đúng `sub` | Có | Assertion body/principal |
| Policy dùng `tenant_id` đúng | Có thể, nếu policy thật chạy | Fixture tenant khác nhau và integration test |
| Matcher yêu cầu scope đúng | Có | Ca scope đủ và scope thiếu |
| Custom converter ánh xạ `roles` | Không nếu helper gán authority trực tiếp; cần kiểm tra converter | Unit test converter + integration wiring |
| `kid` chọn đúng public key | Không | Token ký thật, JWKS/key source và decoder thật |
| `alg` được allow-list đúng | Không | Signed token qua decoder thật với thuật toán được cấu hình |
| `exp` bị kiểm tra | Không | Token ký thật hết hạn qua decoder/validators |
| `iss` được xác minh | Không | Decoder thật và issuer validator |
| `aud` được xác minh | Không | Audience validator được cấu hình và token thật |
| Bearer header được parse | Không | Request Authorization header qua filter chain |
| Token bị revoke/introspect | Không | Introspection/revocation mechanism thật |

Một claim có giá trị “đúng” trong object giả lập không có nghĩa issuer đã ký hoặc xác thực claim đó. Hãy dùng thuật ngữ chính xác trong báo cáo: **authorization test với JWT principal giả lập**, không gọi đó là kiểm thử xác thực token.

## 16. Kiểm tra JWT thật bằng MockMvc khi mục tiêu là decoder

Khi cần kiểm tra chữ ký, issuer, audience hoặc expiration, tạo compact JWT có chữ ký bằng private key test và gửi Bearer header:

```java
mvc.perform(get("/api/reports")
        .header(HttpHeaders.AUTHORIZATION,
            "Bearer " + signedAccessToken))
    .andExpect(status().isOk());
```

Thiết kế test tối thiểu:

- Token hợp lệ: đúng chữ ký, issuer, audience, còn hạn và scope đủ.
- Token thiếu scope: authentication thành công nhưng authorization bị từ chối.
- Token hết hạn: chữ ký đúng nhưng `exp` trong quá khứ.
- Token sai issuer: chữ ký đúng nhưng `iss` không được tin cậy.
- Token sai audience: chữ ký đúng, issuer đúng nhưng `aud` không chứa API audience.
- Token sai chữ ký hoặc `kid` không tìm thấy: decoder từ chối.

Nếu muốn kiểm tra riêng audience, phải có audience validator trong ứng dụng. Các validator mặc định không nên được giả định tự kiểm tra mọi claim tùy chỉnh. Mỗi test nên có positive control để tránh tình huống decoder từ chối tất cả token.

## 17. Parameterized tests cho subject, tenant và claim variants

Có thể dùng `@MethodSource` để kiểm tra nhiều tenant/subject:

```java
static Stream<Arguments> tenantCases() {
    return Stream.of(
        Arguments.of("partner-42", "acme", 200),
        Arguments.of("partner-99", "beta", 403),
        Arguments.of("partner-00", "", 403)
    );
}

@ParameterizedTest
@MethodSource("tenantCases")
void reportAccessUsesTenantClaim(
        String subject,
        String tenant,
        int expectedStatus) throws Exception {

    mvc.perform(get("/api/reports/R-100")
            .with(jwt().jwt(jwt -> jwt
                .subject(subject)
                .claim("tenant_id", tenant)
                .claim("scope", "reports.read"))))
        .andExpect(status().is(expectedStatus));
}
```

Ví dụ giả định report `R-100` thuộc tenant `acme` và policy trả `403` cho tenant rỗng/khác. Nếu API che giấu tài nguyên, có thể dùng `404` theo contract.

Khi test nhiều claim variants, tránh thay đồng thời subject, tenant, scope và state nếu mục tiêu là xác định một điều kiện. Dùng cặp test chỉ khác một claim giúp xác định policy đang hoạt động vì lý do nào.

## 18. Những lỗi thường gặp khi tùy chỉnh subject, header và claims

| Lỗi | Hệ quả | Cách làm đúng |
|---|---|---|
| Nhầm `kid` là claim | Code đọc header không thấy giá trị | Dùng `header("kid", ...)` |
| Nhầm `sub` là header | Principal name không được thiết lập như mong đợi | Dùng `subject(...)` hoặc claim `sub` |
| Đặt `alg = RS256` rồi kết luận token đã ký | Không có chữ ký nào được xác minh | Gửi compact token ký thật qua decoder |
| Dùng `jwt()` để kiểm tra `exp` | Không chạy expiration validator | Token thật qua decoder |
| Đặt `authorities(...)` rồi kết luận scope mapping đúng | Converter không được chứng minh | Test converter và integration token thật |
| Chỉ test claim hợp lệ | Policy có thể fail open khi claim thiếu | Test absent/null/empty/wrong type |
| Dùng claim tenant do client gửi trong body | Không chứng minh tenant từ issuer/principal | Lấy tenant từ JWT principal đã được xác minh |
| Dùng `Instant.now()` khiến test phụ thuộc thời gian | Test dễ flaky | Dùng Instant cố định hoặc Clock kiểm soát |
| Dùng principal mặc định khi controller cần Jwt | Sai kiểu principal hoặc thiếu claims | Dựng Jwt đúng subject/claims |
| Gộp nhiều thay đổi trong một test | Không biết claim nào làm quyết định đổi | Mỗi ca thay một yếu tố |
| Chỉ assert status | Không phát hiện sai subject/body/tenant | Assert principal, response và dữ liệu |
| Gọi toàn bộ claims ra response | Có thể lộ dữ liệu token | Chỉ expose field được phép |

## 19. Bài tập thực hành: JWT đối tác nhiều tenant

Một resource server cung cấp:

- `GET /partner/reports/{id}` yêu cầu scope `reports.read`.
- Report có tenant sở hữu.
- JWT chứa `sub`, `iss`, `aud`, `exp`, `scope` và `tenant_id`.
- Một số đối tác có claim `partner_type` và `region` để áp dụng policy riêng.
- Custom converter ánh xạ claim `roles` thành authority quản trị.

Hãy viết các test:

1. **Subject:** thay `sub` và kiểm tra `Authentication.getName()`/principal theo contract.
2. **Header:** đặt `kid`/`typ` và kiểm tra code đọc header nếu có use case; giải thích vì sao không dùng header để cấp quyền.
3. **Standard claims:** dựng issuer, audience, issuedAt, expiresAt và id với kiểu dữ liệu đúng.
4. **Custom claims:** dựng tenant, partner type, region và kiểm tra policy.
5. **Claim biên:** thiếu tenant, null, rỗng, sai kiểu và tenant không tồn tại đều fail closed.
6. **Scope:** scope đủ được phép; scope thiếu bị từ chối.
7. **Converter:** unit test claim `roles` thành authority và integration test xác nhận converter được gắn vào resource server.
8. **Decoder:** token thật sai chữ ký, hết hạn, sai issuer/audience bị từ chối; token hợp lệ đối chứng được chấp nhận.
9. **Tenant isolation:** cùng scope nhưng tenant khác không đọc report của tenant khác.
10. **Side effect:** token thiếu quyền hoặc sai tenant không gọi export/gateway và không tạo file.

Với từng test, ghi rõ phần nào dùng `jwt()`, phần nào phải gửi Bearer token thật, thành phần nào chạy thật và điều gì test không chứng minh.

**Tiêu chí hoàn thành:** Bạn có thể tạo JWT giả lập với subject, JOSE header, standard claims và custom claims đúng kiểu; phân biệt rõ claim được controller/policy đọc với authority được converter tạo; đồng thời không nhầm object JWT giả lập với token đã ký. Khi đó `jwt()` trở thành công cụ chính xác để kiểm thử authorization trên MockMvc, còn decoder integration tests chịu trách nhiệm xác minh credentials JWT thật.
