# `jwt` helper làm test đạt dù decoder hoặc converter thật vẫn sai

Trong chương **Chẩn đoán sự cố** của module **SPRING_SECURITY_TESTING**, một lỗi kiểm thử đặc biệt nguy hiểm là: bài test dùng `jwt()` của MockMvc hoặc `mockJwt()` của WebTestClient trả `200 OK`, nhưng request mang **Bearer JWT thật** lại bị `401 Unauthorized` hoặc `403 Forbidden`. Điều này không mâu thuẫn. Các helper của `spring-security-test` được thiết kế để đưa **`Authentication` đã được xác thực** vào ngữ cảnh kiểm thử, giúp kiểm tra quyền và logic ứng dụng **sau khi xác thực**. Chúng không tự gọi `JwtDecoder`, không xác minh chữ ký/`iss`/`aud`/`exp`, và có thể bỏ qua cả `JwtAuthenticationConverter` mà production sử dụng để biến claims thành authorities.

Đối với ứng dụng **Servlet/MockMvc** và **Reactive/WebTestClient**, người học cần biết cách phân biệt *test được phép theo một principal giả* với *test cơ chế tiếp nhận Bearer JWT thật*. Bài này xây dựng quy trình chẩn đoán: tái hiện tình huống test xanh giả, chứng minh vị trí bị bỏ qua, kiểm tra converter độc lập, chạy token **ký bằng khóa test** qua decoder/filter thật, rồi khẳng định HTTP `200/401/403` và không rò rỉ dữ liệu.

## 1. Hiện tượng: mock JWT thành công nhưng Bearer thật thất bại

Giả sử API `GET /api/documents/{id}` phải yêu cầu authority `PERM_documents.read`. JWT do hệ thống cấp có claim:

```json
{
  "iss": "https://issuer.test.invalid",
  "sub": "fixture-reader-42",
  "aud": ["documents-api"],
  "permissions": ["documents.read"],
  "exp": 1893456300,
  "iat": 1893456000
}
```

Các thời điểm Unix trong JSON chỉ minh họa cấu trúc; **không** dùng nguyên giá trị này làm JWT hợp lệ tại mọi thời điểm chạy. Trong test tích hợp thực, tạo `iat`/`exp` tương đối với mốc thời gian kiểm soát được hoặc `Instant.now()` cách xa ranh giới hết hạn.

Một test MockMvc sau có thể xanh:

```java
mvc.perform(get("/api/documents/42")
        .with(jwt().jwt(token -> token
            .subject("fixture-reader-42")
            .claim("permissions", List.of("documents.read")))
            .authorities(new SimpleGrantedAuthority(
                "PERM_documents.read"))))
    .andExpect(status().isOk());
```

Nhưng nếu ứng dụng cấu hình `JwtAuthenticationConverter` để đọc claim `scope` thay vì `permissions`, JWT thật chỉ tạo authority trống hoặc sai prefix, khiến URL rule từ chối với **403**. Test trên **không phát hiện được lỗi**, vì `.authorities(...)` đã đặt kết quả phân quyền bằng tay, không để converter production tính toán.

Tương tự, nếu `JwtDecoder` sai `issuer-uri`, tải nhầm JWKS, chỉ tin khóa cũ, từ chối thuật toán hợp lệ, hoặc thiếu validator bắt buộc, test dùng `jwt()` vẫn có thể xanh. Chỉ test gửi `Authorization: Bearer <signed-fixture-token>` mới đi qua đường giải mã/xác thực đó.

### Các vị trí cần phân biệt

```mermaid
flowchart TD
    A[HTTP Authorization: Bearer JWT] --> B[BearerTokenAuthenticationFilter hoặc AuthenticationWebFilter]
    B --> C[JwtDecoder hoặc ReactiveJwtDecoder]
    C --> D{Chữ ký, issuer, thời gian, audience hợp lệ?}
    D -- Không --> E[Authentication failure: thường 401]
    D -- Có --> F[JwtAuthenticationConverter]
    F --> G[JwtAuthenticationToken + GrantedAuthority]
    G --> H{Đủ quyền?}
    H -- Không --> I[Access denied: thường 403]
    H -- Có --> J[Controller / Service 200]

    M[MockMvc jwt() / WebTestClient mockJwt()] --> K[JwtAuthenticationToken giả + authorities fixture]
    K --> H
```

Sơ đồ là logic kiểm thử, không hàm ý các lớp Servlet và Reactive có cùng tên. Trong Spring Security Servlet, `BearerTokenAuthenticationFilter` lấy Bearer header; trong WebFlux, cơ chế reactive filter tiếp nhận bearer và gọi `ReactiveJwtDecoder`. Điểm chung: helper mock có thể **bỏ qua đoạn từ Bearer header đến decoder và converter**, nhưng vẫn cho kiểm tra authorization ở đoạn sau.

## 2. Hiểu hợp đồng của `jwt()` và `mockJwt()`

| Tiện ích test | Nơi sử dụng | Điều thực sự được giả lập | Điều **không** chứng minh |
| --- | --- | --- | --- |
| `jwt()` | `SecurityMockMvcRequestPostProcessors` trong Servlet MockMvc | `JwtAuthenticationToken`/security context gắn cho request | Bearer header parser, `JwtDecoder`, chữ ký và validator; converter thật nếu tự đặt authorities |
| `mockJwt()` | `SecurityMockServerConfigurers` trong WebTestClient Reactive | JWT principal và authorities trong reactive security context | `ReactiveJwtDecoder`, HTTP bearer authentication và converter thật |
| `@WithMockUser` | Spring Security Test | Principal username/roles thông thường | Không tạo principal `Jwt`, không kiểm tra JWT |
| HTTP `Authorization: Bearer ...` | MockMvc qua filter thật hoặc server HTTP | Gửi chuỗi token qua đường xử lý thực | Chỉ có ý nghĩa nếu cấu hình decoder/converter không bị mock/bypass |

Trong nhiều bản Spring Security, `jwt()`/`mockJwt()` có giá trị mặc định thuận tiện cho claims/authorities. **Đừng dựa vào default để kiểm chứng mapping production**. Khi test cần một authority xác định, hãy gắn nó rõ ràng bằng `.authorities(...)`, đồng thời ghi rõ đây là **test authorization sau xác thực**.

Để test thật có ý nghĩa, cần xác minh các điều kiện: client request đi qua **security filter chain thật**, bean decoder là implementation cần kiểm thử (hoặc decoder triển khai bằng khóa test nhưng vẫn làm chữ ký/validator), converter production được gắn vào security DSL, và không dùng post-processor mock principal trên cùng request.

## 3. Phân loại lỗi: 401 và 403 chỉ ra các tầng khác nhau

| Hiện tượng khi gửi token thật | Khả năng gốc | Bước kiểm tra |
| --- | --- | --- |
| HTTP 401, token sai chữ ký | Public key/JWKS không khớp, JWT bị sửa, `alg` không được chấp nhận | Decoder thật, public key test, JWT header, log lỗi đã che dữ liệu |
| HTTP 401, issuer sai | `iss` của token khác issuer tin cậy hoặc validator issuer không khớp | Cấu hình issuer và validation chain |
| HTTP 401, hết hạn/chưa hợp lệ | `exp`/`nbf`, đồng hồ, clock skew | Kiểm tra validator và mốc thời gian test |
| HTTP 401, audience không được phép | **Chỉ khi ứng dụng cấu hình kiểm tra `aud`** | Xác minh audience validator thực sự có mặt |
| HTTP 403 với JWT đã xác thực | Không có authority cần thiết hoặc policy tenant/resource từ chối | `JwtAuthenticationConverter`, prefix, URL/method rule |
| HTTP 200 với token đáng lẽ phải bị từ chối | Validation bị thiếu, security chain sai, matcher `permitAll`, decoder bị mock | Test âm tính với Bearer token lỗi và no-access assertion |
| Mock JWT 200 nhưng Bearer thật 403 | Authorities trong mock khác kết quả converter thật | Test converter độc lập và test HTTP signed-token |
| Mock JWT 200 nhưng Bearer thật 401 | Mock bỏ qua decoder/validator đang lỗi | Chạy JWT ký test qua decoder thực, kiểm tra issuer/JWKS |

HTTP 401/403 là **kỳ vọng phổ biến** của API OAuth2 Resource Server dùng Bearer token. Nếu ứng dụng có custom `AuthenticationEntryPoint`, `AccessDeniedHandler`, proxy hoặc error mapper, mã/status có thể theo contract riêng. Khi đó vẫn phải bảo đảm request không được xác thực hoặc không đủ quyền **không truy cập nội dung bảo vệ**.

**Không đánh đồng hai loại lỗi:** JWT hợp lệ nhưng thiếu scope là lỗi **authorization** (thường 403); JWT có chữ ký hoặc issuer sai là lỗi **authentication** (thường 401). Nếu test nhận 401 khi mong 403, hãy chẩn đoán decoder trước khi chỉnh converter.

## 4. Bug converter minh họa: đọc sai claim hoặc sai prefix

Giả sử tài liệu contract nói JWT chứa `permissions: ["documents.read"]` và endpoint cần authority `PERM_documents.read`. Converter đúng:

```java
@Bean
JwtAuthenticationConverter documentsJwtConverter() {
    JwtGrantedAuthoritiesConverter granted =
        new JwtGrantedAuthoritiesConverter();
    granted.setAuthoritiesClaimName("permissions");
    granted.setAuthorityPrefix("PERM_");

    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();
    converter.setJwtGrantedAuthoritiesConverter(granted);
    converter.setPrincipalClaimName("sub");
    return converter;
}
```

Nếu lập trình viên vô tình dùng:

```java
granted.setAuthoritiesClaimName("scope");  // Sai so với contract.
granted.setAuthorityPrefix("SCOPE_");       // Sai so với URL rule.
```

thì `JwtGrantedAuthoritiesConverter` có thể không tạo ra `PERM_documents.read`. Nhưng test viết `jwt().authorities(new SimpleGrantedAuthority("PERM_documents.read"))` vẫn thành công, vì **tự chọn trước kết quả chuyển đổi**.

Mặt khác, chỉ thêm claim `permissions` trong `jwt().jwt(...)` cũng **không bảo đảm** converter production đã chạy. Nhiều helper tự tạo authentication từ JWT test, hoặc dùng converter mặc định của fixture, chứ không gọi bean converter đã gắn vào resource server thật.

### Tách ba hợp đồng

1. **Claim parsing:** `JwtDecoder` tạo một `Jwt` chứa claims đúng kiểu, đã xác minh chữ ký và validation theo policy.
2. **Authority conversion:** `JwtAuthenticationConverter` biến `Jwt` thành authentication có đúng principal và authorities.
3. **HTTP authorization:** `SecurityFilterChain`/`SecurityWebFilterChain` chặn hoặc cho phép request dựa trên authorities đã được tạo.

Test mỗi tầng riêng, rồi có ít nhất một test **đi qua cả ba tầng** bằng Bearer JWT ký với khóa test.

## 5. Test converter trực tiếp: không cần HTTP, nhưng phải dùng đúng bean production

Để bắt bug mapping, trước hết kiểm tra converter bằng một `Jwt` fixture có claims đúng với contract:

```java
@Test
void converterMapsPermissionsFromActualClaim() {
    Jwt jwt = Jwt.withTokenValue("fixture-not-a-real-token")
        .header("alg", "RS256")
        .subject("fixture-reader-42")
        .claim("permissions", List.of("documents.read", "documents.write"))
        .build();

    JwtAuthenticationConverter converter = documentsJwtConverter();
    AbstractAuthenticationToken authentication = converter.convert(jwt);

    assertNotNull(authentication);
    assertEquals("fixture-reader-42", authentication.getName());
    assertTrue(authentication.getAuthorities().contains(
        new SimpleGrantedAuthority("PERM_documents.read")));
    assertTrue(authentication.getAuthorities().contains(
        new SimpleGrantedAuthority("PERM_documents.write")));
    assertFalse(authentication.getAuthorities().contains(
        new SimpleGrantedAuthority("SCOPE_documents.read")));
}
```

Trong bài test thực tế, **inject bean converter của ứng dụng** bằng `@Autowired JwtAuthenticationConverter converter` (nếu nó được khai báo là bean) thay vì tạo một converter mới trong test. Đoạn trên gọi factory `documentsJwtConverter()` chỉ để minh họa cấu trúc; bản test thật phải kiểm tra converter đang được **DSL sử dụng**. Nếu converter được dựng inline trong `SecurityFilterChain`, hãy refactor ra bean hoặc factory chung cho cấu hình production và test, không viết một converter thứ hai khác hành vi.

Tránh viết assertion rằng JWT đã có signature hợp lệ trong test converter này: `Jwt.withTokenValue(...)` chỉ tạo **đối tượng dữ liệu**; không có JWS signature hoặc cryptographic decoder tham gia.

### Tạo test khiến converter sai chắc chắn bị phát hiện

```java
@Test
void wrongClaimNameProducesNoRequiredAuthority() {
    Jwt fixture = Jwt.withTokenValue("fixture")
        .header("alg", "RS256")
        .claim("sub", "fixture-reader")
        .claim("permissions", List.of("documents.read"))
        .build();

    JwtGrantedAuthoritiesConverter wrong =
        new JwtGrantedAuthoritiesConverter();
    wrong.setAuthoritiesClaimName("scope"); // Claim không có trong fixture.
    wrong.setAuthorityPrefix("SCOPE_");

    assertFalse(wrong.convert(fixture).contains(
        new SimpleGrantedAuthority("PERM_documents.read")));
}
```

Đây là test minh họa **nguyên nhân lỗi**, không phải test chấp nhận cấu hình sai. Regression test của ứng dụng phải kiểm tra **converter production** tạo authority mong đợi; khi cố ý làm sai tên claim/prefix trong code cấu hình, regression test phải chuyển đỏ.

Nếu mapping có nhiều nguồn như `scope`, `scp`, `realm_access.roles` hay `permissions`, hãy ghi rõ **schema token đã được nhà phát hành cam kết**. Không tự cộng mọi chuỗi trong claims thành authority tin cậy; converter cần kiểm tra kiểu dữ liệu và prefix theo policy.

## 6. Cấu hình Servlet đảm bảo converter thật được gọi

Ví dụ một resource server Servlet chỉ cho đọc tài liệu khi có `PERM_documents.read`:

```java
@Configuration
class DocumentsApiSecurity {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http,
            JwtAuthenticationConverter documentsJwtConverter)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/documents/**")
                    .hasAuthority("PERM_documents.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth -> oauth.jwt(jwt ->
                jwt.jwtAuthenticationConverter(documentsJwtConverter)))
            .build();
    }
}
```

Đoạn này cần `JwtDecoder` được cung cấp theo cấu hình thật hoặc test. Nếu dự án đã cấu hình một converter khác trong `SecurityFilterChain`, việc khai báo một bean converter mới **không tự làm DSL dùng bean đó**; cần đi theo đường cấu hình trên hoặc cơ chế tương đương. Khi có nhiều security chains, matcher và `@Order` cũng quyết định chain nào xử lý request.

Một bộ MockMvc test **chỉ kiểm tra authorization sau xác thực** có thể tiếp tục dùng:

```java
@Test
void helperAuthorizesSuppliedAuthorities() throws Exception {
    mvc.perform(get("/api/documents/42")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("PERM_documents.read"))))
        .andExpect(status().isOk());
}

@Test
void helperRejectsOtherAuthorities() throws Exception {
    mvc.perform(get("/api/documents/42")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("PERM_profile.read"))))
        .andExpect(status().isForbidden());
}
```

Test trên cần controller fixture trả response hợp lệ và security filters thực sự được áp dụng (`@SpringBootTest` + `@AutoConfigureMockMvc` hoặc MockMvc builder có `springSecurity()`). Hai kết quả 200/403 cho thấy URL rule đang sử dụng authorities của authentication test; chúng **không chứng minh claim-to-authority mapping của request Bearer thật**.

## 7. Dựng JWT ký bằng khóa test để đi qua `JwtDecoder`

Để kiểm tra cả decoder và converter, phải gửi một **chuỗi JWT thực sự có chữ ký**. Dùng cặp khóa RSA riêng của test; public key được đưa vào decoder và private key chỉ dùng để ký fixture. Ví dụ tạo bean decoder có xác minh signature, issuer, audience và timestamp theo validator được cấu hình:

```java
@TestConfiguration(proxyBeanMethods = false)
class TestJwtDecoderConfig {

    static final String ISSUER = "https://issuer.test.invalid";

    @Bean
    KeyPair fixtureRsaKeyPair() throws GeneralSecurityException {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        return generator.generateKeyPair();
    }

    @Bean
    @Primary
    JwtDecoder fixtureJwtDecoder(KeyPair fixtureRsaKeyPair) {
        RSAPublicKey publicKey =
            (RSAPublicKey) fixtureRsaKeyPair.getPublic();

        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withPublicKey(publicKey).build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(ISSUER);
        OAuth2TokenValidator<Jwt> audience =
            new JwtClaimValidator<List<String>>(
                JwtClaimNames.AUD,
                values -> values != null
                    && values.contains("documents-api"));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(issuerAndTime, audience));
        return decoder;
    }
}
```

Đây là **cấu hình test**, không đưa private key hoặc logic tạo khóa vào runtime production. `JwtValidators.createDefaultWithIssuer(...)` kiểm tra issuer và các validator mặc định (bao gồm timestamp theo chính sách được hỗ trợ), còn `JwtClaimValidator` bổ sung audience theo hợp đồng ứng dụng. **Không mặc định audience tự được kiểm tra** chỉ vì decoder đọc được claim `aud`. Với nhu cầu kiểm thử thời điểm sát biên `exp`/`nbf`, phải điều khiển clock của validator theo phiên bản Spring Security tương ứng; ví dụ dưới dùng token cách xa biên để tránh flaky test.

Tạo token RS256 bằng Nimbus JOSE + JWT (có thể khai báo helper `throws Exception` trong lớp test):

```java
String signFixtureJwt(KeyPair keyPair,
        String issuer,
        List<String> audiences,
        Instant issuedAt,
        Instant notBefore,
        Instant expiration,
        List<String> permissions) throws JOSEException {

    JWTClaimsSet claims = new JWTClaimsSet.Builder()
        .issuer(issuer)
        .subject("fixture-reader-42")
        .audience(audiences)
        .issueTime(Date.from(issuedAt))
        .notBeforeTime(Date.from(notBefore))
        .expirationTime(Date.from(expiration))
        .claim("permissions", permissions)
        .build();

    SignedJWT token = new SignedJWT(
        new JWSHeader.Builder(JWSAlgorithm.RS256)
            .type(JOSEObjectType.JWT)
            .build(),
        claims);
    token.sign(new RSASSASigner(
        (RSAPrivateKey) keyPair.getPrivate()));
    return token.serialize();
}
```

Các type từ `java.security.*`, `java.security.interfaces.*`, `java.time.Instant`, `java.util.*`, `com.nimbusds.jose.*`, `com.nimbusds.jwt.*`, Spring Security OAuth2 JWT và Spring Boot Test. Đây là các **đoạn ghép** vào lớp test đã có context; cần import đúng với dependency và phiên bản dự án. Cặp khóa tạo bởi test là fixture ngắn hạn, không chia sẻ với môi trường triển khai.

**Lưu ý cấu hình:** khi dùng `@Primary JwtDecoder`, bảo đảm context không có hai decoder cùng qualifier gây nhập nhằng và security chain thực sự chọn decoder đang kiểm thử. Nếu muốn test chính cấu hình `issuer-uri`/`jwk-set-uri` và JWKS discovery, dùng HTTP JWKS/provider stub thay cho decoder public-key trực tiếp; ví dụ này kiểm tra **quy trình chữ ký/validator/converter** với public key được xác định tường minh, không kiểm chứng discovery endpoint.

## 8. MockMvc với Bearer token thật: để decoder và converter cùng chạy

Với `@SpringBootTest` và `@AutoConfigureMockMvc`, import `TestJwtDecoderConfig` để ứng dụng dùng decoder fixture có chữ ký thật, còn converter/authorization rule phải giữ như production:

```java
@SpringBootTest
@AutoConfigureMockMvc
@Import(TestJwtDecoderConfig.class)
class SignedJwtHttpSecurityTest {

    @Autowired MockMvc mvc;
    @Autowired KeyPair fixtureRsaKeyPair;

    @Test
    void signedJwtWithRequiredPermissionIsAccepted() throws Exception {
        Instant now = Instant.now();
        String token = signFixtureJwt(
            fixtureRsaKeyPair,
            TestJwtDecoderConfig.ISSUER,
            List.of("documents-api"),
            now,
            now.minusSeconds(5),
            now.plusSeconds(600),
            List.of("documents.read"));

        mvc.perform(get("/api/documents/42")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
            .andExpect(status().isOk());
    }
}
```

Test này **không dùng `.with(jwt())`**. Request đi qua security filter xử lý header, `JwtDecoder` xác minh JWS và claim validator, rồi converter tạo `PERM_documents.read`. Nếu converter production vẫn sai tên claim hoặc prefix, test **phải thất bại với 403** dù chữ ký hợp lệ. Nếu decoder không tin khóa hoặc issuer, test **phải thất bại ở tầng xác thực**, thường 401.

Trong một ứng dụng có controller `GET /api/documents/42`, nên khẳng định cả **body mong đợi** và service chỉ chạy khi đủ quyền, không chỉ HTTP status. Nếu endpoint cần database, dùng fixture cô lập để kiểm chứng không lộ dữ liệu của tenant khác.

### Chẩn đoán khi HTTP signed-token trả 401

1. Kiểm tra JWT có đúng cú pháp compact JWS ba phần và Bearer header đúng hay không.
2. Kiểm tra thuật toán `alg` được cho phép và public key test khớp private key đã ký.
3. Kiểm tra issuer của token và validator `iss`; tránh trộn giá trị của realm/tenant khác.
4. Kiểm tra `exp`, `nbf` và clock skew; token hết hạn hoặc chưa hiệu lực sẽ bị từ chối trước converter.
5. Kiểm tra audience validator **đã được cấu hình** và claim `aud` khớp API target.
6. Xác minh không còn mock `JwtDecoder` hoặc post-processor `jwt()` trên chính request cần kiểm tra decoder.

### Chẩn đoán khi HTTP signed-token trả 403

1. Xác minh JWT đã được decoder chấp nhận (khác nhánh 401).
2. Đọc danh sách authorities từ authentication **trong request test** bằng một endpoint/chế độ quan sát test-only hoặc test converter trực tiếp; không log raw JWT.
3. So tên claim `permissions`/`scope`/`scp` và kiểu dữ liệu (list/string) với contract token.
4. So prefix và chuỗi authority chính xác: `PERM_documents.read` khác `SCOPE_documents.read` và `ROLE_documents.read`.
5. So rule `hasAuthority`/`hasRole`, URL matcher, method security và security chain được chọn.
6. Nếu có tenant/ownership policy, kiểm tra điều kiện này **sau khi xác định converter đã đúng**.

## 9. Ma trận âm tính: token sai phải bị từ chối ở đúng tầng

| Ca thử | Fixture | Kỳ vọng chính |
| --- | --- | --- |
| Token hợp lệ, đúng permission | Ký bằng RSA test key, `iss`/`aud`/`exp` hợp lệ | 200 và nội dung hợp đồng |
| Token hợp lệ, thiếu permission | Cùng key/issuer/audience nhưng claim `permissions` rỗng | 403; không gọi nghiệp vụ bảo vệ |
| Token sai chữ ký | Ký bằng khóa khác public key decoder | 401; không gọi converter thành công |
| Token bị sửa payload | Sửa claims sau khi ký mà không ký lại | 401 do chữ ký không hợp lệ |
| Token sai issuer | `iss` khác `TestJwtDecoderConfig.ISSUER` | 401 nếu issuer validator đang hoạt động |
| Token sai audience | `aud` không chứa `documents-api` | 401 nếu audience validator đang hoạt động |
| Token hết hạn | `exp` trong quá khứ đủ xa so với skew | 401; không đi đến URL authorization thành công |
| Token chưa hiệu lực | `nbf` trong tương lai đủ xa so với skew | 401 |
| Thiếu Bearer header | Không có authentication | 401 với bearer entry point minh họa |
| Converter sai tên claim/prefix | Token ký hợp lệ, claim `permissions` vẫn đúng | 403; **regression test cần chuyển đỏ** |

Không gộp nhiều lỗi trong cùng fixture: nếu token vừa sai chữ ký vừa sai audience, test 401 **không chứng minh** audience validator đã hoạt động. Giữ một baseline hợp lệ và thay **đúng một điều kiện** ở mỗi ca. Với HTTP response thất bại, kiểm tra thêm controller/repository không bị gọi hoặc không có side effect; 401/403 không có giá trị nếu dữ liệu đã bị ghi trước khi authorization chạy.

Một ví dụ ngắn cho token hết hạn:

```java
@Test
void signedExpiredJwtIsRejectedByRealDecoder() throws Exception {
    Instant now = Instant.now();
    String expired = signFixtureJwt(
        fixtureRsaKeyPair,
        TestJwtDecoderConfig.ISSUER,
        List.of("documents-api"),
        now.minusSeconds(7_200),
        now.minusSeconds(7_100),
        now.minusSeconds(3_600),
        List.of("documents.read"));

    mvc.perform(get("/api/documents/42")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + expired))
        .andExpect(status().isUnauthorized());
}
```

Helper nhận riêng `issuedAt`, `notBefore` và `expiration`: ca trên đặt `iat`/`nbf` ở quá khứ trước `exp`, nên các mốc thời gian nhất quán và đủ xa clock skew. Với ca `nbf` trong tương lai, cũng cần giữ `iat`/`exp` hợp lý và đúng các validator khác, để lỗi chỉ xuất phát từ `nbf`.

## 10. WebFlux: `mockJwt()` có cùng giới hạn, dùng `ReactiveJwtDecoder` thật khi cần

Ở Reactive, helper điển hình:

```java
webTestClient.mutateWith(mockJwt()
        .jwt(token -> token
            .subject("fixture-reader-42")
            .claim("permissions", List.of("documents.read")))
        .authorities(new SimpleGrantedAuthority(
            "PERM_documents.read")))
    .get().uri("/api/documents/42")
    .exchange()
    .expectStatus().isOk();
```

Đây vẫn là test **authorization sau khi có JWT principal giả**. Nó không gọi `ReactiveJwtDecoder` và có thể bypass cả converter reactive của ứng dụng.

Cấu hình WebFlux sử dụng cùng logic mapping qua adapter:

```java
@Bean
SecurityWebFilterChain reactiveApiSecurity(ServerHttpSecurity http,
        JwtAuthenticationConverter documentsJwtConverter) {
    return http.authorizeExchange(exchanges -> exchanges
            .pathMatchers(HttpMethod.GET, "/api/documents/**")
                .hasAuthority("PERM_documents.read")
            .anyExchange().denyAll())
        .oauth2ResourceServer(oauth -> oauth.jwt(jwt ->
            jwt.jwtAuthenticationConverter(
                new ReactiveJwtAuthenticationConverterAdapter(
                    documentsJwtConverter))))
        .build();
}
```

Spring Security Reactive có thể sử dụng converter reactive tự định nghĩa thay adapter. Dù cách nào, phải bảo đảm `ReactiveJwtDecoder` và converter thực sự được gắn vào `SecurityWebFilterChain` được chọn. Một bean converter nằm trong context nhưng **không được security DSL sử dụng** sẽ không ảnh hưởng request.

Đối với request **HTTP qua WebTestClient**, cần dùng Bearer header:

```java
webTestClient.get().uri("/api/documents/42")
    .headers(headers -> headers.setBearerAuth(signedTestJwt))
    .exchange()
    .expectStatus().isOk()
    .expectBody(String.class).isEqualTo("document:42");
```

`signedTestJwt` phải là token được ký bằng key test mà `ReactiveJwtDecoder` trong **server/application context** tin cậy. Nếu dùng `WebTestClient.bindToApplicationContext(context)`, client được cấu hình filter chain đúng; nếu dùng `bindToServer()`, các mock configurer trong test **không truyền principal qua socket**, nhưng Bearer header thì được gửi thật. Khi kiểm tra converter/decoder, không gọi `.mutateWith(mockJwt())` trên cùng request.

Một cặp test Reactive cần có: (a) token hợp lệ, đủ quyền → 200 và body đúng; (b) token hợp lệ, thiếu permission → 403; sau đó thêm JWT chữ ký/issuer sai → 401. Nếu service còn dùng `@PreAuthorize`, bật `@EnableReactiveMethodSecurity` và chạy qua bean proxy thật; đừng mock chính service chứa method security.

## 11. Gỡ rối cấu hình test context: mock sai bean làm lỗi biến mất

Cùng một ứng dụng có thể có nhiều cách dựng test:

| Test context | Cấu hình dễ gây nhầm | Cách kiểm tra |
| --- | --- | --- |
| `@WebMvcTest` controller slice | `JwtDecoder` được mock để context khởi động | Chỉ gọi đây là test controller/authorization; thêm integration test decoder thật |
| `@SpringBootTest` + `@AutoConfigureMockMvc` | `.with(jwt())` bypass decoder; test vẫn 200 | Gửi Bearer header từ JWS test, xác minh decoder/converter |
| `MockMvcBuilders.standaloneSetup(...)` | Security filters không được nạp đúng | Nạp filter chain + `springSecurity()` hoặc dùng Spring Boot integration |
| `@WebFluxTest` | `@MockitoBean ReactiveJwtDecoder` chỉ thỏa dependency | Không coi `mockJwt()` là decoder test |
| `WebTestClient.bindToController(...)` | Handler chạy mà không có toàn bộ security WebFilter | Bind application context có `springSecurity()` hoặc server thật |
| Nhiều `SecurityFilterChain` | Matcher/`@Order` chọn chain khác | Kiểm tra URL và filter/authorization policy của chain được chọn |
| Custom converter bean | Bean tồn tại nhưng DSL vẫn dùng converter mặc định | Inject converter đúng vào DSL, test authority từ Bearer thật |
| Test disable security | `addFilters=false` hoặc cấu hình test `permitAll` | Xóa bypass, thêm anonymous 401 và thiếu quyền 403 |

Khi dùng Spring Boot 3.4+ có thể gặp `@MockitoBean` thay `@MockBean`; việc đổi annotation **không khiến một decoder mock trở thành decoder thật**. Kiểm tra kiểu bean và nơi được inject. Nếu test bảo mật phụ thuộc vào một decoder mock chỉ để context tạo được, đó là **dấu hiệu cần tách hai loại test**: helper principal cho authorization, decoder thực cho authentication.

### Quan sát có giới hạn và không lộ dữ liệu nhạy cảm

Trong profile test, có thể bật log DEBUG của Spring Security để quan sát chain nào xử lý request, lỗi xác thực hay từ chối quyền; không xuất nguyên Bearer token, raw JWT, Authorization header, cookies hoặc key. Với converter, ưu tiên assertion kiểm tra **tên authority đã chuẩn hóa** và loại authentication, không cần in toàn bộ claims người dùng. Với lỗi signature/JWKS, ghi issuer/`kid` fixture và loại lỗi, không ghi private key hoặc secret.

## 12. Bộ kiểm thử đủ mạnh phải “đỏ” khi phá decoder hoặc converter

Một cách đánh giá chất lượng regression test là thử *mutation* có kiểm soát trong nhánh test:

1. Đổi `setAuthoritiesClaimName("permissions")` thành `"scope"`. **Converter unit test và HTTP signed-token happy path phải thất bại**, nhưng test `jwt().authorities(...)` có thể vẫn xanh. Đây là minh chứng trực tiếp nguyên nhân dương tính giả.
2. Đổi prefix `"PERM_"` thành `"SCOPE_"`. Ca required authority `PERM_documents.read` phải thất bại nếu đang kiểm tra converter thực.
3. Thay public key của decoder bằng key khác. Test JWT có chữ ký hợp lệ theo key cũ **phải nhận 401**; mock `jwt()` không phát hiện được.
4. Tạm bỏ issuer/audience validator **trong fixture thử nghiệm**. Ca âm tính sai `iss`/`aud` phải chuyển đỏ nếu thật sự đang bảo vệ chính sách đó.
5. Tạm thay URL rule thành `permitAll()`. Ca thiếu permission phải chuyển đỏ; nếu không, test đang assert nhầm rule hoặc filter chain.

Không commit những thay đổi cố ý làm yếu security. Mục đích là xác minh bộ test có thể phát hiện **đúng hạng lỗi**, không phải chấp nhận phiên bản code đã bỏ validator.

### Phân lớp suite để vừa nhanh vừa đủ tin cậy

| Lớp test | Dữ liệu/thiết lập | Phát hiện |
| --- | --- | --- |
| Unit converter | `Jwt` fixture với claims rõ ràng | Sai claim name, prefix, principal claim, authority mapping |
| Mock HTTP authorization | MockMvc `jwt()` / WebTestClient `mockJwt()` | URL/method policy, 200/403, logic sau xác thực |
| Signed-JWT integration | Public/private key test, decoder/converter thực | Signature/issuer/audience/time + mapping + security filter |
| Real HTTP/server test (khi cần) | Random port và Bearer token ký test | HTTP serialization, filters qua socket, cấu hình server thật |
| Database side-effect test | Repository/database test cô lập | 401/403 không ghi sai dữ liệu; 200 ghi đúng dữ liệu |

Các lớp **bổ sung**, không thay thế nhau. Chạy unit converter và mock authorization thường xuyên; giữ ít nhất một signed-token integration test trong CI để phát hiện wiring decoder/converter sai. Nếu ứng dụng có nhiều issuer, tenant hoặc claim schema, thêm đại diện cho từng contract để ngăn token của nhóm này được tin sai ở nhóm khác.

## 13. Bài thực hành: biến test xanh giả thành hồi quy có giá trị

Cho Spring Boot resource server có API `GET /api/documents/{id}`, rule cần `PERM_documents.read` và token contract dùng `permissions: ["documents.read"]`. Có một lỗi cố ý: converter đặt claim `scope` hoặc prefix `SCOPE_`.

1. **Tái hiện xanh giả:** dùng `jwt().authorities(PERM_documents.read)` trong MockMvc, hoặc `mockJwt().authorities(...)` trên WebTestClient. Xác nhận request đủ authority trả 200, nhưng giải thích vì sao kết quả không chứng minh converter đúng.
2. **Test converter:** tạo `Jwt` với claim `permissions` và inject converter **thực**. Assert authority `PERM_documents.read` được tạo. Test phải đỏ khi cấu hình đang sai.
3. **Sửa wiring:** cấu hình `JwtAuthenticationConverter` đọc `permissions` với prefix `PERM_` và chắc chắn DSL resource server dùng đúng converter; với Reactive dùng converter reactive/adapter phù hợp.
4. **Test Bearer ký thật:** tạo RSA key pair test, dùng `NimbusJwtDecoder` với public key, issuer và audience validators, ký JWS bằng private key; gửi `Authorization: Bearer ...` **không dùng `jwt()/mockJwt()`**. Assert 200 và body đúng.
5. **Bốn ca âm tính:** token ký đúng nhưng thiếu permission → 403; token sai chữ ký → 401; token sai issuer → 401; token sai audience → 401 nếu đã cấu hình audience validator.
6. **Thời gian:** tạo token hết hạn ngoài clock skew → 401; nếu cần sát ranh giới, kiểm soát clock validator thay vì dùng `Thread.sleep`.
7. **Đa tenant:** giữ permission nhưng đổi tenant claim; nếu policy kiểm tra tenant, request không được đọc tài liệu tenant khác.
8. **Reactive:** lặp lại ca mock vs Bearer thật với `WebTestClient` và `ReactiveJwtDecoder`; xác minh security filter chain thật được chọn.
9. **Độ mạnh assertion:** cố ý đổi converter claim name lần nữa để kiểm tra test signed-token và converter unit chuyển đỏ trong khi helper mock có thể vẫn xanh.
10. **CI an toàn:** không dùng private key production, token thật hoặc IdP triển khai; chỉ ghi seed, case ID, loại lỗi và thông tin fixture không nhạy cảm.

### Tiêu chí hoàn thành

- Giải thích rõ vì sao `jwt()`/`mockJwt()` có thể xanh khi `JwtDecoder` hoặc `JwtAuthenticationConverter` production sai.
- Có ít nhất **một test converter trực tiếp** dùng chính converter được DSL sử dụng.
- Có ít nhất **một test Bearer token ký bằng khóa test** đi qua decoder, validator, converter và URL security rule.
- Phân biệt đúng lỗi **401** (authentication) và **403** (authorization) theo entry point/handler đã cấu hình.
- Không test signature, `exp`, `nbf`, issuer, audience chỉ bằng mock principal.
- Các ca bị từ chối không truy cập dữ liệu và không sinh side effect bảo vệ trái phép.
- Bộ test phải thất bại khi cố ý làm sai tên claim, prefix, key hoặc validator; không chỉ kiểm tra 200 happy path.

## Ghi nhớ

**Helper `jwt()` và `mockJwt()` giúp kiểm tra phần sau xác thực, không phải `JwtDecoder` hoặc converter thực.** Nếu test tự gắn `PERM_documents.read` bằng `.authorities(...)`, nó có thể che hoàn toàn bug mapping từ claim `permissions`; nếu test chỉ dùng JWT giả, nó cũng không phát hiện sai chữ ký, issuer, audience hoặc clock skew. Trong **SPRING_SECURITY_TESTING**, hãy tách rõ **test authority bằng mock**, **test converter với claims**, và **test JWT ký thật qua Bearer header**. Chỉ khi các ca 200/401/403 được kiểm tra qua đúng đường xử lý và không lộ dữ liệu, bộ test mới đủ sức bảo vệ ứng dụng khỏi lỗi decoder/converter mà fixture giả dễ bỏ qua.
