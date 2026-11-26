# scope, scp và ánh xạ mặc định thành authorities

> **Chương:** JWT với MockMvc  
> **Module:** `SPRING_SECURITY_TESTING` — kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên ứng dụng Servlet và Reactive. Bài này tập trung vào cách claim `scope`/`scp` của JWT được chuyển thành `GrantedAuthority` và cách kiểm tra ánh xạ đó bằng `MockMvc`.

## 1. Từ scope trong token đến quyền mà Spring Security kiểm tra

OAuth2 access token thường chứa scope mô tả những hành động client được phép thực hiện. Ví dụ token của đối tác có:

```json
{
  "sub": "partner-42",
  "scope": "reports.read reports.export",
  "tenant_id": "acme"
}
```

Ứng dụng Spring Security không thường so sánh trực tiếp chuỗi `scope` trong từng rule. Resource server chuyển các scope thành `GrantedAuthority` rồi dùng chúng trong request authorization hoặc method security.

Với converter mặc định, ánh xạ thường là:

| Scope trong JWT | Authority trong Spring Security |
|---|---|
| `reports.read` | `SCOPE_reports.read` |
| `reports.export` | `SCOPE_reports.export` |
| `orders.read` | `SCOPE_orders.read` |

Do đó, rule có thể viết:

```java
.requestMatchers(HttpMethod.GET, "/api/reports")
    .hasAuthority("SCOPE_reports.read")
```

Hoặc ở method security:

```java
@PreAuthorize("hasAuthority('SCOPE_reports.export')")
public ExportJob exportReports() {
    // ...
}
```

Điểm quan trọng là **scope và authority không phải cùng một chuỗi**. Scope là dữ liệu trong token; authority là quyền Spring Security sử dụng sau bước chuyển đổi.

Bài học này giúp bạn:

- Hiểu claim `scope` và `scp` thường được biểu diễn như thế nào.
- Biết `JwtGrantedAuthoritiesConverter` mặc định chọn claim và tạo prefix `SCOPE_` ra sao.
- Dùng `jwt()` trong MockMvc để kiểm tra scope được ánh xạ thành authority.
- Phân biệt test claim-driven mapping với test gán authority trực tiếp.
- Nhận diện khi nào cần custom converter và khi nào phải kiểm tra bằng Bearer token thật.

## 2. Hai dạng claim phổ biến: scope và scp

Các issuer không nhất thiết dùng cùng một tên claim hoặc cùng kiểu dữ liệu.

### Claim scope dạng chuỗi

Một định dạng phổ biến là chuỗi scope được phân tách bằng dấu cách:

```json
{
  "scope": "reports.read reports.export orders.read"
}
```

Mỗi phần tử là một scope riêng. Với converter mặc định, delimiter là dấu cách; kết quả là ba authority:

- `SCOPE_reports.read`
- `SCOPE_reports.export`
- `SCOPE_orders.read`

Không thêm prefix `SCOPE_` vào giá trị scope ở phía issuer nếu ứng dụng cũng dùng prefix mặc định. Nếu claim đã chứa `SCOPE_reports.read`, converter có thể tạo authority `SCOPE_SCOPE_reports.read`.

### Claim scp dạng collection

Một số identity provider dùng claim `scp` dạng mảng:

```json
{
  "scp": [
    "reports.read",
    "reports.export"
  ]
}
```

Mỗi phần tử của collection được chuyển thành một authority. Dùng dạng collection khi đó là schema token do issuer quy định; đừng tự đổi kiểu dữ liệu claim chỉ để làm test tiện hơn.

### Dạng dữ liệu là một phần của contract

| Claim | Dạng thường gặp | Ví dụ |
|---|---|---|
| `scope` | Chuỗi phân tách bằng khoảng trắng | `"reports.read reports.export"` |
| `scp` | Collection các chuỗi | `["reports.read", "reports.export"]` |

Converter mặc định của Spring Security nhận diện các claim tên `scope` và `scp`; với giá trị chuỗi hoặc collection, nó tạo các authority tương ứng. Hãy giữ đúng schema mà issuer của ứng dụng thực sự phát hành.

## 3. JwtGrantedAuthoritiesConverter mặc định hoạt động thế nào?

`JwtGrantedAuthoritiesConverter` là converter tiêu chuẩn dùng để chuyển scope trong JWT thành collection `GrantedAuthority`.

Các quy tắc mặc định quan trọng:

1. Tìm claim authorities đã biết: `scope` hoặc `scp`.
2. Khi không cấu hình claim name riêng, converter tìm `scope` trước rồi mới đến `scp`.
3. Nếu giá trị là chuỗi, converter tách theo delimiter mặc định là dấu cách.
4. Nếu giá trị là collection, converter xử lý từng phần tử.
5. Mỗi giá trị được chuyển thành `SimpleGrantedAuthority` với prefix mặc định `SCOPE_`.

Ví dụ:

```text
JWT claim:
  scope = "reports.read reports.export"

JwtGrantedAuthoritiesConverter:
  "reports.read"   -> SCOPE_reports.read
  "reports.export" -> SCOPE_reports.export
```

Nếu token có cả `scope` và `scp`, converter mặc định chọn claim đầu tiên có mặt theo thứ tự tên claim đã biết (mặc định `scope` trước `scp`). Không nên phát hành token có cả hai claim với nội dung mâu thuẫn. Hãy thống nhất schema với issuer để tránh một bên nghĩ token có quyền đọc, trong khi converter lại chọn claim khác.

Nếu claim `scope` có mặt nhưng rỗng, đừng kỳ vọng converter tự bỏ qua nó để dùng `scp`. Trường hợp đó cần được xử lý theo contract token và kiểm tra riêng.

### Scope không tự trở thành role

Converter mặc định thêm `SCOPE_`, không thêm `ROLE_`. Vì thế:

- `hasAuthority("SCOPE_reports.read")` khớp authority mặc định.
- `hasRole("reports.read")` thường kiểm tra `ROLE_reports.read`, không khớp authority trên.
- `hasAuthority("reports.read")` cũng không khớp nếu prefix mặc định vẫn được giữ.

Dùng matcher theo đúng tên authority sau chuyển đổi.

## 4. Cấu hình resource server dùng ánh xạ mặc định

Nếu không cần custom mapping, cấu hình resource server có thể dùng JWT support mặc định:

```java
@Configuration
@EnableWebSecurity
class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .requestMatchers(HttpMethod.POST, "/api/reports/export")
                    .hasAuthority("SCOPE_reports.export")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

Với cấu hình này, resource server sử dụng `JwtAuthenticationConverter` mặc định và `JwtGrantedAuthoritiesConverter` để tạo authorities từ scope claim.

Một controller minh họa:

```java
@RestController
class ReportController {

    @GetMapping("/api/reports")
    Map<String, String> reports() {
        return Map.of("reportId", "R-100");
    }

    @PostMapping("/api/reports/export")
    ResponseEntity<Void> export() {
        return ResponseEntity.accepted().build();
    }
}
```

Nếu API dùng `scope` dạng chuỗi, token có `reports.read` sẽ truy cập GET. Token chỉ có `reports.export` không được đọc báo cáo. Với POST export, quyền tương ứng là `SCOPE_reports.export`.

Các ví dụ bỏ qua cấu hình decoder/JWKS để tập trung vào authorization. Trong ứng dụng thực, resource server còn cần cấu hình cách lấy khóa và xác minh token theo issuer, audience và chính sách của hệ thống.

## 5. Dùng jwt() để kiểm tra scope claim qua MockMvc

`SecurityMockMvcRequestPostProcessors.jwt()` tạo một JWT authentication giả lập cho request. Khi dùng builder để đặt claim `scope` mà không ghi đè authorities, helper sử dụng converter mặc định để tạo authorities cho test authentication.

Ví dụ:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ReportScopeAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void reportReadScopeCanRead() throws Exception {
        mvc.perform(get("/api/reports")
                .with(jwt().jwt(jwt -> jwt
                    .subject("partner-42")
                    .claim("scope", "reports.read"))))
            .andExpect(status().isOk());
    }

    @Test
    void reportExportScopeCannotRead() throws Exception {
        mvc.perform(get("/api/reports")
                .with(jwt().jwt(jwt -> jwt
                    .subject("partner-42")
                    .claim("scope", "reports.export"))))
            .andExpect(status().isForbidden());
    }
}
```

Hai test tạo một cặp đối chứng:

- Scope đủ: request được phép.
- JWT authentication đã có nhưng scope không phù hợp: request bị từ chối `403`.

Đây là **authorization test với JWT giả lập**. Test không gửi Bearer token compact và không kiểm tra chữ ký, issuer, audience hoặc expiration bằng decoder.

### Kiểm tra authority được tạo ra

Có thể kiểm tra trạng thái authentication trong kết quả MockMvc:

```java
mvc.perform(get("/api/reports")
        .with(jwt().jwt(jwt -> jwt
            .subject("partner-42")
            .claim("scope", "reports.read"))))
    .andExpect(status().isOk())
    .andExpect(authenticated().withUsername("partner-42")
        .withAuthorities(
            new SimpleGrantedAuthority("SCOPE_reports.read")));
```

Assertion này làm rõ rằng scope đã được chuyển thành authority mà policy mong đợi. Nó vẫn chỉ xác minh authentication do helper dựng trong test.

## 6. Kiểm tra claim scp dạng collection

Nếu issuer phát `scp` dưới dạng collection, dựng đúng kiểu trong JWT giả lập:

```java
@Test
void scpCollectionMapsToAuthorities() throws Exception {
    mvc.perform(get("/api/reports")
            .with(jwt().jwt(jwt -> jwt
                .subject("partner-42")
                .claim("scp", List.of(
                    "reports.read",
                    "reports.export")))))
        .andExpect(status().isOk())
        .andExpect(authenticated().withAuthorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"),
            new SimpleGrantedAuthority("SCOPE_reports.export")));
}
```

Một ca thiếu scope:

```java
@Test
void scpWithoutReadScopeCannotReadReports() throws Exception {
    mvc.perform(get("/api/reports")
            .with(jwt().jwt(jwt -> jwt
                .subject("partner-42")
                .claim("scp", List.of("reports.export")))))
        .andExpect(status().isForbidden());
}
```

Các test này hữu ích khi API nhận token từ issuer dùng `scp`. Đảm bảo claim là collection chuỗi như schema dự kiến; đừng dùng một chuỗi JSON được serialize thành text thay cho collection thật trong object JWT.

## 7. Scope nhiều giá trị và kiểm tra quyền độc lập

Một token có thể mang nhiều scope. Mỗi endpoint cần kiểm tra đúng scope cần thiết, không được suy ra có một scope là có tất cả quyền.

Giả sử:

| Token | Scope |
|---|---|
| T1 | `reports.read` |
| T2 | `reports.export` |
| T3 | `reports.read reports.export` |
| T4 | Không có scope |

Policy:

| Endpoint | T1 | T2 | T3 | T4 |
|---|---:|---:|---:|---:|
| `GET /api/reports` | Cho phép | Từ chối | Cho phép | Từ chối |
| `POST /api/reports/export` | Từ chối | Cho phép | Cho phép | Từ chối |

Parameterized test:

```java
static Stream<Arguments> reportReadCases() {
    return Stream.of(
        Arguments.of("reports.read", 200),
        Arguments.of("reports.export", 403),
        Arguments.of("reports.read reports.export", 200),
        Arguments.of("", 403)
    );
}

@ParameterizedTest
@MethodSource("reportReadCases")
void reportReadRequiresItsOwnScope(
        String scope,
        int expectedStatus) throws Exception {

    mvc.perform(get("/api/reports")
            .with(jwt().jwt(jwt -> jwt
                .subject("partner-42")
                .claim("scope", scope))))
        .andExpect(status().is(expectedStatus));
}
```

Ca chuỗi rỗng minh họa token đã được giả lập nhưng không có authority đọc. Nếu muốn kiểm tra **claim không tồn tại**, tạo một JWT không có claim `scope` và `scp` riêng; claim rỗng và claim vắng mặt không nhất thiết tương đương với mọi custom converter.

## 8. Đừng ghi đè authorities khi mục tiêu là kiểm tra ánh xạ

`jwt()` có thể đặt authorities trực tiếp:

```java
mvc.perform(get("/api/reports")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isOk());
```

Cách này rất hữu ích nếu câu hỏi chỉ là “policy có cho phép authority `SCOPE_reports.read` không?”. Nhưng nó bỏ qua bước chuyển claim sang authority.

So sánh hai cách:

| Cách dựng | Điều đang được kiểm tra | Điều không được chứng minh |
|---|---|---|
| `jwt().jwt(jwt -> jwt.claim("scope", "reports.read"))` | Claim-driven mapping mặc định trong helper và policy | Decoder/token signature thực |
| `jwt().authorities(new SimpleGrantedAuthority("SCOPE_reports.read"))` | Authorization policy với authority đã cấp | Claim `scope` được ánh xạ đúng |
| Bearer token thật qua decoder/converter | Đường authentication và mapping đã cấu hình trong ứng dụng | Không tự bao phủ mọi workflow ngoài scope test |

Nếu bài test muốn chứng minh `JwtGrantedAuthoritiesConverter` mặc định, hãy đặt claim và **không gọi `authorities(...)`**.

## 9. Unit test trực tiếp JwtGrantedAuthoritiesConverter

Có thể kiểm tra converter độc lập mà không cần dựng HTTP request:

```java
class JwtGrantedAuthoritiesConverterTest {

    private final JwtGrantedAuthoritiesConverter converter =
        new JwtGrantedAuthoritiesConverter();

    @Test
    void scopeStringCreatesPrefixedAuthorities() {
        Jwt jwt = Jwt.withTokenValue("test-token")
            .header("alg", "none")
            .subject("partner-42")
            .claim("scope", "reports.read reports.export")
            .build();

        Collection<GrantedAuthority> authorities =
            converter.convert(jwt);

        assertThat(authorities)
            .extracting(GrantedAuthority::getAuthority)
            .containsExactlyInAnyOrder(
                "SCOPE_reports.read",
                "SCOPE_reports.export");
    }

    @Test
    void scpCollectionCreatesPrefixedAuthorities() {
        Jwt jwt = Jwt.withTokenValue("test-token")
            .header("alg", "none")
            .subject("partner-42")
            .claim("scp", List.of("reports.read", "orders.read"))
            .build();

        Collection<GrantedAuthority> authorities =
            converter.convert(jwt);

        assertThat(authorities)
            .extracting(GrantedAuthority::getAuthority)
            .containsExactlyInAnyOrder(
                "SCOPE_reports.read",
                "SCOPE_orders.read");
    }
}
```

Unit test này xác minh trực tiếp hành vi converter của phiên bản Spring Security đang dùng. Nó không chứng minh resource server đã gắn converter đó vào chain. Vì vậy, nên kết hợp:

1. Unit test converter cho quy tắc chuyển đổi.
2. MockMvc test cho authorization theo claim.
3. Integration test qua Bearer token thật nếu cần xác minh converter được nối vào decoder/resource server configuration.

## 10. Khi token có cả scope và scp

Converter mặc định nhận diện cả `scope` và `scp`. Trong implementation mặc định, nó tìm `scope` trước; nếu claim đó không có mới xét `scp`.

Ví dụ token không nên phát hành:

```json
{
  "scope": "reports.write",
  "scp": ["reports.read"]
}
```

Nếu ứng dụng mong `reports.read` từ `scp` nhưng converter chọn `scope`, request đọc sẽ bị từ chối. Ngược lại, nếu `scope` chứa quyền rộng hơn, policy có thể nhận authority ngoài ý định.

Có thể viết test để hiểu hành vi của converter:

```java
@Test
void scopeClaimTakesPrecedenceWhenBothKnownClaimsExist() {
    Jwt jwt = Jwt.withTokenValue("test-token")
        .header("alg", "none")
        .claim("scope", "reports.write")
        .claim("scp", List.of("reports.read"))
        .build();

    Collection<GrantedAuthority> authorities =
        new JwtGrantedAuthoritiesConverter().convert(jwt);

    assertThat(authorities)
        .extracting(GrantedAuthority::getAuthority)
        .containsExactly("SCOPE_reports.write");
}
```

Đây là kiểm tra hành vi converter mặc định theo phiên bản thư viện. Trong contract token của ứng dụng, tốt hơn là chỉ định một claim authorities duy nhất hoặc cấu hình rõ claim name, tránh hai nguồn quyền mâu thuẫn.

## 11. Role khác scope: tránh nhầm ROLE_ và SCOPE_

Spring Security có thể dùng role và authority, nhưng hai cách đặt tên không tự đồng nhất:

- `hasRole("ADMIN")` thường tìm `ROLE_ADMIN`.
- `hasAuthority("REPORT_ADMIN")` tìm đúng chuỗi `REPORT_ADMIN`.
- Scope `reports.read` theo converter mặc định thành `SCOPE_reports.read`.
- Scope không tự động thành `ROLE_REPORTS_READ`.

Ví dụ sai:

```java
.requestMatchers("/api/reports")
    .hasRole("reports.read")
```

Nếu token chỉ có scope `reports.read`, authority tạo ra là `SCOPE_reports.read` nên rule trên không khớp.

Ví dụ đúng:

```java
.requestMatchers("/api/reports")
    .hasAuthority("SCOPE_reports.read")
```

Nếu ứng dụng chủ ý chuyển claim `roles` thành `ROLE_`, hãy dùng custom converter và test mapping riêng. Không đổi scope thành role chỉ để làm matcher ngắn hơn nếu semantics của issuer là OAuth2 scope.

## 12. Tùy chỉnh claim name, prefix và delimiter

Khi issuer không dùng schema mặc định, có thể cấu hình `JwtGrantedAuthoritiesConverter`:

```java
@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter authorities =
        new JwtGrantedAuthoritiesConverter();

    authorities.setAuthoritiesClaimName("permissions");
    authorities.setAuthorityPrefix("PERM_");

    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();
    converter.setJwtGrantedAuthoritiesConverter(authorities);

    return converter;
}
```

Ví dụ token:

```json
{
  "sub": "partner-42",
  "permissions": "reports.read reports.export"
}
```

Kết quả:

- `PERM_reports.read`
- `PERM_reports.export`

Gắn converter vào resource server:

```java
@Bean
SecurityFilterChain apiChain(
        HttpSecurity http,
        JwtAuthenticationConverter jwtAuthenticationConverter)
        throws Exception {

    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/reports")
                .hasAuthority("PERM_reports.read")
            .anyRequest().denyAll()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt
                .jwtAuthenticationConverter(jwtAuthenticationConverter)))
        .build();
}
```

Một số phiên bản Spring Security còn cho phép tùy chỉnh delimiter của chuỗi claim qua setter tương ứng. Kiểm tra API theo phiên bản dependency được quản lý trong dự án trước khi sử dụng.

Nếu muốn lấy quyền từ claim `roles` dạng collection, cấu hình claim name `roles` và prefix phù hợp, ví dụ `ROLE_`. Nhưng khi đó cần thống nhất rõ issuer đang phát role hay scope; không trộn hai semantics trong một claim không có schema.

## 13. Kiểm tra custom converter: unit test và wiring test

Khi đã custom claim name hoặc prefix, cần ít nhất hai loại test.

### Unit test converter

```java
@Test
void permissionsClaimUsesCustomPrefix() {
    JwtGrantedAuthoritiesConverter authorities =
        new JwtGrantedAuthoritiesConverter();
    authorities.setAuthoritiesClaimName("permissions");
    authorities.setAuthorityPrefix("PERM_");

    Jwt jwt = Jwt.withTokenValue("test-token")
        .header("alg", "none")
        .claim("permissions", "reports.read reports.export")
        .build();

    assertThat(authorities.convert(jwt))
        .extracting(GrantedAuthority::getAuthority)
        .containsExactlyInAnyOrder(
            "PERM_reports.read",
            "PERM_reports.export");
}
```

### Wiring test

Một converter đúng nhưng không được gắn vào `oauth2ResourceServer().jwt()` vẫn không ảnh hưởng đến request thật. Để kiểm tra wiring, gửi Bearer token được ký bằng test key qua decoder thật và xác minh authority cuối cùng cho phép/từ chối endpoint.

`jwt()` của MockMvc là helper dựng authentication cho request; không nên mặc định rằng custom converter bean của ứng dụng được gọi như khi decoder xử lý Bearer token. Nếu cần kiểm tra converter production được nối vào chain, hãy dùng integration test với token thật hoặc test trực tiếp cấu hình/converter ở boundary thích hợp.

## 14. Claims thiếu, rỗng hoặc sai kiểu

Không phải token nào cũng chứa scope. Converter không tìm thấy claim authorities phù hợp sẽ không tạo scope authorities. Với endpoint yêu cầu `SCOPE_reports.read`, principal đã xác thực nhưng không có authority này thường nhận `403`.

Các trường hợp nên kiểm tra:

| JWT | Kết quả mapping mong đợi |
|---|---|
| Không có `scope` và `scp` | Không có scope authorities |
| `scope` = `"reports.read"` | Có `SCOPE_reports.read` |
| `scope` = `""` | Không có scope authority hữu ích |
| `scp` = `["reports.read"]` | Có `SCOPE_reports.read` |
| `scp` = `[]` | Không có scope authorities |
| `scope` có mặt nhưng `scp` có giá trị khác | Claim được chọn theo quy tắc converter; tránh token mâu thuẫn |
| Claim có phần tử không phải chuỗi | Không phải schema scope hợp lệ; validate ở issuer/decoder boundary hoặc converter riêng |

Với claim vắng mặt, có thể dựng JWT không có scope:

```java
mvc.perform(get("/api/reports")
        .with(jwt().jwt(jwt -> jwt
            .subject("partner-42")
            .claim("tenant_id", "acme"))))
    .andExpect(status().isForbidden());
```

Đừng viết logic fail-open kiểu “không có scope thì cho phép user đã xác thực”. Endpoint bảo vệ phải yêu cầu authority rõ ràng; nếu scope không có, request không thỏa policy.

## 15. Tách kiểm thử scope mapping khỏi kiểm thử chữ ký JWT

Dùng `jwt()` là cách nhanh để kiểm tra claim-to-authority và authorization, nhưng nó không xác minh token được ký hoặc phát hành hợp lệ.

| Câu hỏi | Dùng `jwt()`? | Cách kiểm tra |
|---|---|---|
| Claim `scope` tạo authority `SCOPE_`? | Có, với claim-driven mapping mặc định | MockMvc test và converter unit test |
| Claim `scp` collection tạo authorities? | Có | MockMvc test và converter unit test |
| Endpoint yêu cầu đúng scope? | Có | Cặp allow/deny |
| Custom converter xử lý claim riêng? | Unit test converter; không giả định helper tự dùng bean converter | Converter test + Bearer integration |
| Token có chữ ký hợp lệ? | Không | Bearer token qua decoder thật |
| Token hết hạn? | Không | Token ký thật với `exp` quá hạn |
| Issuer/audience hợp lệ? | Không | Decoder và validators thật |
| Authorization header được parse? | Không | Gửi header `Authorization: Bearer` qua filter chain |

Khi kiểm tra decoder, tạo token compact được ký bằng private key test, cấu hình public key/JWKS cho decoder và gửi header Bearer. Có ca token hợp lệ đối chứng để chắc decoder không từ chối tất cả token.

## 16. Data-driven tests cho scope và endpoint

Khi nhiều endpoint dùng scope khác nhau, dữ liệu hóa test giúp giữ policy nhất quán:

```java
static Stream<Arguments> reportCases() {
    return Stream.of(
        Arguments.of("reports.read", 200),
        Arguments.of("reports.export", 403),
        Arguments.of("orders.read", 403),
        Arguments.of("", 403)
    );
}

@ParameterizedTest(name = "scope={0}, expected={1}")
@MethodSource("reportCases")
void reportReadRequiresReadScope(
        String scope,
        int expectedStatus) throws Exception {

    mvc.perform(get("/api/reports")
            .with(jwt().jwt(jwt -> jwt
                .subject("partner-42")
                .claim("scope", scope))))
        .andExpect(status().is(expectedStatus));
}
```

Với `scp` collection, có thể dùng một nguồn dữ liệu riêng trả về `List<String>`. Đừng chuyển list thành chuỗi JSON trong claim; đưa collection thực vào builder.

Nên có các test riêng cho:

- Claim `scope` chuỗi.
- Claim `scp` collection.
- Không có claim.
- Có cả hai claim nếu hệ thống cần xác minh thứ tự chọn.
- Custom converter nếu ứng dụng thay claim name/prefix.
- Token thật qua decoder nếu cần xác minh authentication.

## 17. Những lỗi thường gặp khi làm việc với scope và scp

| Lỗi | Hệ quả | Cách sửa |
|---|---|---|
| Viết `hasAuthority("reports.read")` | Thiếu prefix mặc định | Dùng `SCOPE_reports.read` |
| Dùng `hasRole("reports.read")` | Rule tìm `ROLE_` | Dùng `hasAuthority` cho scope |
| Đặt `SCOPE_` ngay trong claim scope | Có thể thành `SCOPE_SCOPE_...` | Issuer gửi giá trị scope thuần |
| Dùng `authorities(...)` rồi kết luận mapping đúng | Bỏ qua converter | Đặt claim `scope`/`scp` |
| Chỉ test scope đủ | Rule có thể bị mở rộng | Thêm token đã xác thực nhưng thiếu scope |
| Cho token cả scope và scp mâu thuẫn | Kết quả phụ thuộc claim được chọn | Chuẩn hóa contract, chỉ dùng một claim |
| Giả định scp luôn là chuỗi | Sai schema khi issuer phát collection | Dựng đúng kiểu collection |
| Dùng @WithMockUser để kiểm tra scope mapping | Principal không phải Jwt và không có converter | Dùng `jwt()` hoặc Bearer token thật tùy mục tiêu |
| Mock JwtDecoder rồi kết luận scope mapping production đúng | Decoder/converter production không chạy | Unit test converter + integration Bearer |
| Nhầm scope với chữ ký token | Test authorization bị diễn giải thành authentication | Tách test decoder/validator |

## 18. Bài tập thực hành: resource server báo cáo đối tác

Một API có các endpoint:

- `GET /api/reports` yêu cầu `reports.read`.
- `POST /api/reports/export` yêu cầu `reports.export`.
- `GET /api/orders` yêu cầu `orders.read`.
- Issuer có thể phát claim `scope` dạng chuỗi hoặc `scp` dạng collection.
- Ứng dụng dùng converter mặc định, không custom prefix.

Hãy viết các test:

1. `scope = "reports.read"` đọc báo cáo thành công.
2. `scope = "reports.export"` không được đọc báo cáo.
3. `scope = "reports.read reports.export"` có thể đọc và export theo đúng endpoint.
4. `scp = ["reports.read"]` được ánh xạ thành `SCOPE_reports.read`.
5. `scp = ["orders.read"]` không được đọc báo cáo.
6. Không có cả `scope` và `scp` thì không có scope authority.
7. Có cả hai claim với giá trị mâu thuẫn: xác minh behavior của converter phiên bản dự án và quyết định contract token có cần cấm trường hợp này không.
8. Dùng `JwtGrantedAuthoritiesConverter` unit test để kiểm tra prefix và tập authorities.
9. Viết một custom converter test nếu issuer chuyển sang claim `permissions`.
10. Gửi token thật qua decoder để kiểm tra chữ ký/issuer/expiry; giải thích vì sao `jwt()` không thể thay thế test đó.

Với mỗi test, ghi rõ claim đầu vào, authority mong đợi, endpoint, status và điều mà test không chứng minh.

**Tiêu chí hoàn thành:** Bạn có thể lần theo một scope từ claim `scope`/`scp` đến `GrantedAuthority`, viết matcher đúng với prefix `SCOPE_`, kiểm tra cả allow/deny bằng MockMvc và phân biệt rõ claim-driven mapping với việc gán authority trực tiếp. Khi đó bạn có thể chẩn đoán chính xác lỗi “token có scope nhưng API vẫn trả 403” mà không nhầm lỗi converter với lỗi chữ ký hoặc cấu hình decoder.
