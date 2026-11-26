# Claim thiếu, kiểu claim sai và token không đúng cấu trúc

## 1. Bài toán: token trông giống JWT nhưng không thể được tin cậy

Trong một API bảo vệ bằng OAuth2 Resource Server, client gửi:

```http
GET /api/orders/42 HTTP/1.1
Authorization: Bearer eyJhbGciOiJSUzI1NiJ9...
```

Không phải chuỗi có dạng JWT nào cũng là một **access token hợp lệ**. Một token có thể sai ngay từ cách biểu diễn, có chữ ký không hợp lệ, quá hạn, thiếu claim bắt buộc, chứa claim sai kiểu dữ liệu, hoặc hoàn toàn hợp lệ về mặt xác thực nhưng **không có quyền** đọc đơn hàng.

Chương **JWT và token thực** của module **SPRING_SECURITY_TESTING** tập trung vào việc kiểm chứng các kết quả này qua HTTP. Người học sẽ dùng `spring-security-test` cùng `MockMvc` cho Servlet, `WebTestClient` cho Reactive và đối chiếu với `@WithMockUser`, `SecurityContext`, `jwt()`, `oauth2Login()`, `oidcLogin()`. Mấu chốt là biết **test nào thực sự chạy bộ giải mã, xác minh và kiểm tra token**, test nào chỉ chèn sẵn một người dùng đã xác thực.

Trong bài học này, “token thực” nghĩa là **chuỗi token được ký trong môi trường test và gửi qua header `Authorization: Bearer ...` để bộ xử lý security của ứng dụng tự đọc và xác minh**. Không cần token của hệ thống production hoặc khóa bí mật thật.

Sau bài học, bạn có thể:

- Phân loại rõ **token sai cấu trúc**, **claim thiếu**, **claim sai kiểu**, **chữ ký hoặc thời hạn không hợp lệ** và **token thiếu quyền**.
- Định nghĩa hợp đồng claim theo ứng dụng, đặt kiểm tra đúng vị trí trong `JwtDecoder` / `ReactiveJwtDecoder`.
- Tạo JWT đã ký bằng khóa thử nghiệm và xác nhận kết quả **401 Unauthorized**, **403 Forbidden**, hoặc **200 OK** trên HTTP.
- Chỉ ra vì sao `with(jwt())`, `mockJwt()`, `@WithMockUser`, `oauth2Login()` và `oidcLogin()` không chứng minh được parser hay bộ xác minh JWT hoạt động đúng.
- Tránh những assertion quá cụ thể vào thông điệp lỗi, kiểu chuyển đổi claim hay chi tiết nội bộ phụ thuộc phiên bản Spring Security.

## 2. Phân loại lỗi trước khi viết test

JWT được ký theo định dạng **JWS Compact Serialization** thông dụng có ba đoạn Base64URL, phân tách bằng hai dấu chấm:

```text
base64url(protected-header).base64url(claims-payload).base64url(signature)
             (1)                    (2)                   (3)
```

Header và payload sau khi giải mã phải có cấu trúc JSON phù hợp; chữ ký phải được xác minh bằng thuật toán và khóa mà ứng dụng **chủ động chấp nhận**. Chuỗi chỉ có hai đoạn, mã Base64URL hỏng, JSON không hợp lệ hoặc cấu trúc header sai có thể bị từ chối trước khi hệ thống xét quyền.

**JWS ba đoạn khác JWE năm đoạn** (token mã hóa). API cấu hình bộ giải mã JWT ký bằng RSA không tự động chấp nhận JWE; cách kiểm tra phụ thuộc cơ chế token mà issuer và resource server đã thống nhất. Một chuỗi ngẫu nhiên hay opaque access token cũng không nên được ép phân tích như JWS nếu ứng dụng sử dụng introspection.

### 2.1. Bảng phân biệt nguyên nhân và phản hồi

| Trường hợp | Ví dụ | Điểm chặn mong muốn | Phản hồi HTTP thường thấy trong Resource Server chuẩn |
|---|---|---|---|
| Thiếu bearer credential | Không có header `Authorization` | Authentication entry point | **401** |
| Sai cấu trúc compact | `abc.def`, Base64URL/JSON hỏng, số đoạn sai | Parser/decoder | **401** |
| Chữ ký không hợp lệ | Payload đổi sau khi ký, khóa không đúng | Signature verification | **401** |
| Thuật toán không được phép | `alg` không nằm trong danh sách tin cậy, `alg=none` | JWS verification policy | **401** |
| Token quá hạn hoặc chưa đến lúc dùng | `exp`/`nbf` không phù hợp | Validator thời gian | **401** |
| Thiếu claim bắt buộc theo hợp đồng ứng dụng | Không có `tenant_id` | Validator claim do ứng dụng cấu hình | **401 nếu validator từ chối token** |
| Claim có kiểu không hợp lệ | `"tenant_id": 42` thay vì string | Parser, claim converter hoặc custom validator | **401 nếu được từ chối ở bước xác thực** |
| Token hợp lệ nhưng thiếu scope | `scope="profile"` trong khi API đòi `orders:read` | Authorization | **403** |
| Token hợp lệ và có đúng scope | `scope="orders:read"` | Cho phép gọi controller | **200** nếu controller thành công |

Các status trên giả định ứng dụng dùng Spring Security OAuth2 Resource Server, Bearer authentication, các validator được cấu hình đúng và không có handler tùy biến ghi đè kết quả. **Claim thiếu/sai kiểu không mặc nhiên tạo ra 401**: nếu ứng dụng không hề yêu cầu claim đó, hoặc chỉ dùng nó ở controller, kết quả có thể khác. Bài này chủ động xác thực claim khi **decode token** để lỗi xuất hiện ở HTTP authentication boundary.

**401 và 403 khác nhau về bản chất:** 401 thường là không tạo được authentication hợp lệ; 403 là đã xác thực nhưng không đủ thẩm quyền. Có thể gặp status khác với các header HTTP bị lỗi cú pháp hay exception không được xử lý. Không quy hết mọi lỗi liên quan token thành 403.

### 2.2. Minh họa claim thiếu và sai kiểu

```json
{
  "iss": "https://issuer.example.test",
  "sub": "alice",
  "aud": ["orders-api"],
  "exp": 1799999999,
  "scope": "orders:read",
  "tenant_id": "tenant-a"
}
```

Đây là *payload minh họa*, chưa phải token có chữ ký hợp lệ. Hợp đồng mẫu của ứng dụng yêu cầu:

- `iss` phải đúng issuer tin cậy.
- `aud` phải chứa `orders-api`.
- `exp` phải còn hiệu lực; `nbf` nếu có phải không nằm quá xa trong tương lai.
- `tenant_id` **bắt buộc có mặt**, **phải là JSON string** và không được rỗng.
- `scope` được ánh xạ thành authority; `orders:read` cấp quyền đọc API đơn hàng.

Hai payload sau khác nhau, nhưng cùng phải bị từ chối bởi **validator tenant của ứng dụng**:

```json
// Trường hợp A: thiếu tenant_id
{"iss":"https://issuer.example.test","sub":"alice","aud":["orders-api"],"scope":"orders:read"}

// Trường hợp B: tenant_id sai kiểu JSON
{"iss":"https://issuer.example.test","sub":"alice","aud":["orders-api"],"scope":"orders:read","tenant_id":42}
```

Các dòng bắt đầu bằng `//` là chú thích để đọc ví dụ; JSON gửi trên mạng không cho phép chú thích. Khi đưa vào phép thử JWT ký thật, phải có thêm các claim thời gian phù hợp và chữ ký hợp lệ.

**Lưu ý về claim tiêu chuẩn:** `exp` và `nbf` là JWT NumericDate (giá trị số tính bằng giây từ Unix epoch theo RFC 7519), `aud` có thể là chuỗi hoặc mảng chuỗi, còn `scope`/`scp` có các quy ước khác nhau tùy issuer. Spring Security và thư viện JWT có thể chuyển đổi một số claim tiêu chuẩn trước khi trả về `Jwt.getClaims()`. Vì vậy, không nên viết test dựa trên giả định rằng mọi sai kiểu đều bị decoder mặc định từ chối, hoặc rằng mọi issuer đều dùng cùng một biểu diễn scope.

## 3. Pipeline xử lý token: xác định chính xác nơi lỗi phải xuất hiện

```mermaid
flowchart TD
    A["HTTP Authorization: Bearer ..."] --> B{"Có bearer token phù hợp?"}
    B -->|Không| U["401 / authentication entry point"]
    B -->|Có| C["Giải cấu trúc JWT, JSON và JWS"]
    C -->|Sai| U
    C -->|Đúng| D["Xác minh thuật toán, chữ ký và khóa tin cậy"]
    D -->|Sai| U
    D -->|Đúng| E["Kiểm tra iss, aud, exp, nbf, tenant_id..."]
    E -->|Sai| U
    E -->|Đúng| F["Tạo JwtAuthenticationToken và authorities"]
    F --> G{"Có SCOPE_orders:read?"}
    G -->|Không| V["403 Forbidden"]
    G -->|Có| H["Controller trả 200 (nếu xử lý thành công)"]
```

Sơ đồ này mô tả **hành vi mục tiêu**, không khẳng định thứ tự nội bộ của từng thư viện luôn giống hệt ở mọi phiên bản. Ví dụ, một số bước parse và verify có thể nằm chung trong Nimbus.

Một thiết kế kiểm thử hiệu quả chia thành ba ranh giới:

1. **Giải mã/kiểm tra claim:** gọi `JwtDecoder.decode(token)` hoặc gửi bearer token thật qua HTTP. Đây là nơi kiểm tra token sai cấu trúc, sai chữ ký, hết hạn hoặc vi phạm validator.
2. **Ánh xạ authentication/authorization:** dùng JWT hợp lệ để kiểm tra mapper tạo đúng authorities; có thể dùng `jwt()`/`mockJwt()` cho phép thử authorization nhanh.
3. **Xử lý endpoint:** sau khi authentication và authorization thành công, kiểm tra controller trả đúng dữ liệu/HTTP status.

Nếu mục tiêu của bài là **phát hiện claim sai kiểu ở decoder**, chỉ viết `@WithMockUser` và assert 200/403 sẽ bỏ sót lỗi chính.

## 4. Tạo một hợp đồng bảo mật rõ ràng cho API Servlet

Ví dụ dùng Spring Boot 3, Spring Security 6, Java 17 trở lên và API mẫu `GET /api/orders/42`. Trong ứng dụng thật, chọn phiên bản dependency tương thích với Spring Boot đang sử dụng.

```kotlin
// build.gradle.kts (minh họa các dependency liên quan)
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-resource-server")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
```

### 4.1. Security filter chain dành cho bearer token

```java
@Configuration
@EnableWebSecurity
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(AbstractHttpConfigurer::disable)
            .build();
    }
}
```

`@EnableWebSecurity` có thể được bật bởi auto-configuration trong một số cấu hình Spring Boot; ở đây khai báo rõ để dễ đọc. `csrf(...disable)` chỉ có chủ đích cho **API stateless xác thực qua bearer header**, không áp dụng mặc định cho một ứng dụng web đăng nhập bằng cookie.

Để kiểm tra kết quả `200` trong ví dụ, ứng dụng cần có endpoint thực:

```java
@RestController
class OrderController {

    @GetMapping("/api/orders/42")
    String findOrder() {
        return "order-42";
    }
}
```

Spring Security mặc định thường chuyển `scope="orders:read"` thành authority `SCOPE_orders:read` qua `JwtGrantedAuthoritiesConverter`. Nếu issuer dùng `scp`, danh sách scope, claim role riêng hoặc prefix khác, hãy cấu hình `JwtAuthenticationConverter` / `JwtGrantedAuthoritiesConverter` tương ứng và kiểm thử mapping đó. Không suy diễn authority chỉ từ sự tồn tại của một claim bất kỳ.

### 4.2. Validator bắt buộc kiểm tra claim tùy biến

Trong mô hình ví dụ, ta quyết định **tenant_id phải là string không rỗng** và audience phải dành cho API. Các ràng buộc này cần được thực thi trên token **sau khi xác minh chữ ký**, trước khi authentication được chấp nhận:

```java
static OAuth2TokenValidator<Jwt> applicationClaimsValidator() {
    return jwt -> {
        Object tenant = jwt.getClaims().get("tenant_id");

        if (!(tenant instanceof String value) || value.isBlank()) {
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "tenant_id is required and must be a nonblank string",
                    null
                )
            );
        }

        List<String> audiences = jwt.getAudience();
        if (audiences == null || !audiences.contains("orders-api")) {
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "audience is not accepted",
                    null
                )
            );
        }

        return OAuth2TokenValidatorResult.success();
    };
}
```

Đây là **hàm tiện ích** cần đặt trong lớp cấu hình hoặc một class dùng chung. Nó không đọc một kiểu chưa được kiểm tra bằng phép ép kiểu cưỡng bức, nên cả claim **vắng mặt**, **number**, **boolean**, **array**, **object** và **string rỗng** đều dẫn tới kết quả validator rõ ràng.

Khi ghép với các validator chuẩn, lưu ý giữ **bộ kiểm tra issuer và timestamp**, không vô tình thay bằng mỗi validator tùy biến:

```java
static OAuth2TokenValidator<Jwt> allValidators() {
    return new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(
            "https://issuer.example.test"),
        applicationClaimsValidator()
    );
}

@Bean
JwtDecoder jwtDecoder(RSAPublicKey trustedIssuerPublicKey) {
    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withPublicKey(trustedIssuerPublicKey).build();

    decoder.setJwtValidator(allValidators());
    return decoder;
}
```

Ở production, `trustedIssuerPublicKey` phải lấy từ cấu hình trust/issuer/JWKS phù hợp; không được lấy public key do chính request đưa vào để “xác minh”. Đoạn `JwtDecoder` trên trình bày cách gắn validator khi ứng dụng quản lý public key trực tiếp; phần tiếp theo tạo **khóa thử nghiệm riêng** và thay thế bean trong test.

Nếu ứng dụng đã dùng `issuer-uri`, `jwk-set-uri` hoặc `JwtDecoder` do Boot tạo, việc tự khai báo bean có thể thay đổi cơ chế auto-configuration. Hãy gắn validator vào decoder thật theo thiết kế dự án. Không tắt xác minh chữ ký chỉ để viết một test claim.

**Về message lỗi:** ứng dụng có thể ghi nhận mã lỗi và lý do chi tiết trong log có kiểm soát, nhưng HTTP 401 nên được kiểm tra chủ yếu bằng status và header `WWW-Authenticate` phù hợp. Không dựa vào toàn bộ chuỗi lỗi chi tiết vì format có thể khác giữa các phiên bản và không nên vô tình tiết lộ cấu trúc bảo mật nội bộ.

## 5. Fixture token thực trong test: tự ký RSA, xác minh bằng public key

Để kiểm tra parser và chữ ký mà không phụ thuộc mạng hay identity provider, tạo một cặp khóa RSA **chỉ dùng trong test**. `JwtEncoder` ký bằng private key; `NimbusJwtDecoder` xác minh bằng public key. Token đi qua header `Authorization` sẽ được Spring Security xử lý như bearer token thực.

Ví dụ sau là một cấu hình thử nghiệm hoàn chỉnh về mặt mật mã và validator. Đặt `@TestConfiguration` bên trong lớp test hoặc ở package test được import rõ ràng:

```java
@TestConfiguration
class TestJwtCryptography {

    private static final String ISSUER =
        "https://issuer.example.test";

    @Bean
    KeyPair localTestKeyPair() throws NoSuchAlgorithmException {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        return generator.generateKeyPair();
    }

    @Bean
    JwtEncoder jwtEncoder(KeyPair localTestKeyPair) {
        RSAKey jwk = new RSAKey.Builder(
                (RSAPublicKey) localTestKeyPair.getPublic())
            .privateKey((RSAPrivateKey) localTestKeyPair.getPrivate())
            .keyID("test-rsa-key")
            .build();

        return new NimbusJwtEncoder(
            new ImmutableJWKSet<>(new JWKSet(jwk)));
    }

    @Bean
    @Primary
    JwtDecoder jwtDecoder(KeyPair localTestKeyPair) {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withPublicKey(
                (RSAPublicKey) localTestKeyPair.getPublic())
                .build();

        OAuth2TokenValidator<Jwt> appClaims = jwt -> {
            Object tenant = jwt.getClaims().get("tenant_id");
            if (!(tenant instanceof String value) || value.isBlank()) {
                return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token", "invalid tenant_id", null));
            }

            List<String> audiences = jwt.getAudience();
            if (audiences == null ||
                    !audiences.contains("orders-api")) {
                return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token", "invalid audience", null));
            }

            return OAuth2TokenValidatorResult.success();
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                appClaims
            )
        );
        return decoder;
    }
}
```

Những import đáng chú ý:

- Java: `java.security.KeyPair`, `KeyPairGenerator`, `NoSuchAlgorithmException`, `interfaces.RSAPublicKey`, `interfaces.RSAPrivateKey`, `java.util.List`.
- Spring Security: `org.springframework.security.oauth2.jwt.*`, `org.springframework.security.oauth2.core.*`, `org.springframework.security.oauth2.core.validator.*`.
- Nimbus JOSE JWT: `com.nimbusds.jose.jwk.RSAKey`, `JWKSet`, `com.nimbusds.jose.jwk.source.ImmutableJWKSet`.
- Spring Test: `org.springframework.boot.test.context.TestConfiguration`, `org.springframework.context.annotation.Bean`, `org.springframework.context.annotation.Primary`.

Mỗi lần khởi tạo test context tạo một cặp khóa mới. Đừng đưa private key thử nghiệm vào source kiểm thử cố định dùng lại cho production, và không copy access token production vào log hoặc snapshot test. Phần `JwtEncoder` thuộc fixture test; ở production, **resource server chỉ cần thông tin xác minh**, không cần private signing key của issuer.

### 5.1. Helper tạo token đã ký với từng dạng claim

```java
private String signedToken(
        Object tenantId,
        String scope,
        Instant issuedAt,
        Instant expiresAt
) {
    JwtClaimsSet.Builder claims = JwtClaimsSet.builder()
        .issuer("https://issuer.example.test")
        .subject("alice")
        .audience(List.of("orders-api"))
        .issuedAt(issuedAt)
        .expiresAt(expiresAt);

    // null mô phỏng hoàn toàn thiếu claim tenant_id.
    if (tenantId != null) {
        claims.claim("tenant_id", tenantId);
    }
    if (scope != null) {
        claims.claim("scope", scope);
    }

    JwsHeader header = JwsHeader.with(SignatureAlgorithm.RS256)
        .keyId("test-rsa-key")
        .build();

    return jwtEncoder.encode(
        JwtEncoderParameters.from(header, claims.build())
    ).getTokenValue();
}

private String activeToken(Object tenantId, String scope) {
    Instant now = Instant.now();
    return signedToken(
        tenantId, scope, now.minusSeconds(5), now.plusSeconds(300));
}
```

Các đoạn Java trong mục này dự kiến nằm trong **lớp test có field `@Autowired JwtEncoder jwtEncoder`**. Với `tenantId = null`, helper không thêm claim; với `tenantId = 42`, nó tạo JSON number (sai kiểu theo hợp đồng); với `tenantId = "tenant-a"`, nó tạo giá trị string hợp lệ. Tất cả vẫn được ký bằng RSA để lỗi claim không bị che bởi lỗi chữ ký.

Việc test token thật khác việc tự lấy một JSON, mã hóa Base64 và nối thêm chữ ký giả. **Payload nhìn đúng không chứng minh chữ ký hợp lệ**.

## 6. MockMvc: phân biệt lỗi authentication với authorization trên HTTP

Giả sử dự án có `ApiSecurityConfig` và `OrderController` như mục 4. Ta dùng `@SpringBootTest` để khởi động security chain; import fixture test để thay nguồn khóa và decoder. Phần cốt lõi của lớp test:

```java
@SpringBootTest
@AutoConfigureMockMvc
@Import(TestJwtCryptography.class)
class RealJwtServletTest {

    @Autowired MockMvc mvc;
    @Autowired JwtEncoder jwtEncoder;

    // Đặt signedToken(...) và activeToken(...) của mục 5.1 ở đây.

    private ResultActions withBearer(String token) throws Exception {
        return mvc.perform(
            get("/api/orders/42")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
        );
    }

    @Test
    void missingBearerIs401() throws Exception {
        mvc.perform(get("/api/orders/42"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void missingTenantClaimIs401() throws Exception {
        withBearer(activeToken(null, "orders:read"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void numericTenantClaimIs401() throws Exception {
        withBearer(activeToken(42, "orders:read"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void blankTenantClaimIs401() throws Exception {
        withBearer(activeToken("  ", "orders:read"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void malformedCompactJwtIs401() throws Exception {
        withBearer("abc.def")
            .andExpect(status().isUnauthorized());
    }

    @Test
    void invalidSignatureIs401() throws Exception {
        String valid = activeToken("tenant-a", "orders:read");
        String[] segments = valid.split("\\.");

        // Giữ header/payload, thay chữ ký bằng bytes không hợp lệ.
        String invalidSignature = Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(new byte[256]);

        withBearer(
            segments[0] + "." + segments[1] + "." + invalidSignature)
            .andExpect(status().isUnauthorized());
    }

    @Test
    void expiredTokenIs401() throws Exception {
        Instant now = Instant.now();

        String expired = signedToken(
            "tenant-a",
            "orders:read",
            now.minusSeconds(900),
            now.minusSeconds(600)
        );

        withBearer(expired).andExpect(status().isUnauthorized());
    }

    @Test
    void validTokenWithoutRequiredScopeIs403() throws Exception {
        withBearer(activeToken("tenant-a", "profile"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validTokenWithScopeIs200() throws Exception {
        withBearer(activeToken("tenant-a", "orders:read"))
            .andExpect(status().isOk())
            .andExpect(content().string("order-42"));
    }
}
```

Các import đặc trưng: `@SpringBootTest`, `@AutoConfigureMockMvc`, `@Import`, `@Test`, `@Autowired`; `MockMvc`, `ResultActions`, `HttpHeaders`, `Instant`, `Base64`, `List`, `JwtEncoder`, `JwtClaimsSet`, `JwtEncoderParameters`, `JwsHeader`, `SignatureAlgorithm`; static imports `MockMvcRequestBuilders.get`, `MockMvcResultMatchers.status` và `content`. Hai helper ở mục 5.1 phải được đặt cùng lớp test, đúng như chú thích.

**Các điều kiện để chạy ví dụ:** Spring Boot phải nhận ra ứng dụng `@SpringBootApplication`, bean security chain cần tải trong test context, endpoint `GET /api/orders/42` phải tồn tại, fixture `JwtDecoder` phải thật sự là decoder được resource server dùng. Nếu đã có bean `JwtDecoder` trong ứng dụng, `@Primary` của fixture chỉ giúp chọn bean ưu tiên; cần xác nhận không có cấu hình trực tiếp của filter chain làm lệch việc chọn decoder. Kiểm thử không đòi internet, JWK endpoint hay thông tin đăng nhập của issuer thật.

Một cách gia cố phép thử là assert `WWW-Authenticate` có Bearer challenge khi trả 401:

```java
withBearer(activeToken(42, "orders:read"))
    .andExpect(status().isUnauthorized())
    .andExpect(header().string(
        HttpHeaders.WWW_AUTHENTICATE,
        containsString("Bearer")
    ));
```

Chỉ nên kiểm tra mã HTTP và phần header ổn định, trừ khi ứng dụng có contract bắt buộc cho `error` / `error_description`. Mô tả lỗi chi tiết của decoder có thể được chuẩn hóa hoặc ẩn đi bởi framework.

### 6.1. Cùng một chữ ký hợp lệ có thể cho 401, 403 hoặc 200

Ba token được tạo bởi `activeToken(...)` đều có chữ ký RSA hợp lệ, issuer đúng, thời gian hợp lệ và audience hợp lệ:

| Cách gọi helper | Kết quả | Nguyên nhân |
|---|---|---|
| `activeToken(42, "orders:read")` | 401 | Claim `tenant_id` sai kiểu nên validator từ chối authentication |
| `activeToken("tenant-a", "profile")` | 403 | Authentication thành công nhưng không có `SCOPE_orders:read` |
| `activeToken("tenant-a", "orders:read")` | 200 | Authentication và authorization đều đạt |

Nhờ vậy, lỗi “claim sai kiểu” không bị nhầm với “người dùng thiếu quyền”. Test còn chứng minh quy tắc kiểm tra claim được **kích hoạt trên tuyến HTTP**, không chỉ tồn tại trong một helper mà filter chain không hề sử dụng.

### 6.2. Kiểm thử sai thuật toán và token không có chữ ký

JWS header ghi `alg=none` hoặc một thuật toán không được cho phép **không biến token thành hợp lệ chỉ vì payload có claim đúng**. Bộ giải mã dùng public key RSA phải từ chối token không có chữ ký đúng chính sách.

Có thể xây một chuỗi giả với header/payload Base64URL, nhưng vì không ký bằng private key nên kết quả mong muốn là lỗi authentication. Không dùng kiểu:

```java
// Sai: kiểm tra payload JSON hoặc Base64URL riêng lẻ rồi coi là token hợp lệ.
String payload = "...";
assertThat(payload).contains("tenant_id");
```

Assertion trên không kiểm tra cấu trúc compact, thuật toán, chữ ký, thời hạn, issuer hay audience. Tương tự, không cho phép token tự xác định public key của nó thông qua header không đáng tin cậy như `jku`/`jwk` nếu ứng dụng chưa có chính sách khóa đã kiểm soát.

### 6.3. Khi token sai cấu trúc nhưng HTTP không trả 401

Đừng mặc định tất cả các trường hợp “Authorization hỏng” cho cùng kết quả. Chuỗi `Bearer abc.def` thường được tiếp nhận như một bearer credential và bị decoder từ chối → 401. Nhưng nếu header vi phạm ngữ pháp Bearer HTTP, có nhiều credential mâu thuẫn hoặc bộ lọc tùy biến ném exception, framework có thể trả lỗi `invalid_request` (đôi khi 400) hoặc response riêng. Khi viết test hãy xác định **đầu vào hợp đồng**: “có một bearer token nhưng compact JWT sai” khác với “header Authorization sai cú pháp”.

## 7. Test riêng bộ giải mã: biết lỗi nằm ở claim hay HTTP

Integration test HTTP chứng minh filter chain hoạt động; unit/integration test trực tiếp decoder giúp chỉ ra **validator nào** đang từ chối token:

```java
@Autowired JwtDecoder decoder;

@Test
void decoderRejectsNumericTenant() {
    String token = activeToken(42, "orders:read");

    assertThatThrownBy(() -> decoder.decode(token))
        .isInstanceOf(JwtException.class);
}

@Test
void decoderAcceptsValidTenant() {
    Jwt jwt = decoder.decode(
        activeToken("tenant-a", "orders:read"));

    assertThat(jwt.getClaimAsString("tenant_id"))
        .isEqualTo("tenant-a");
}
```

Với `assertThatThrownBy` của AssertJ, test không phụ thuộc vào message chính xác. Nếu muốn xác nhận mã lỗi validator và loại exception cụ thể, kiểm tra contract của phiên bản Spring Security mà dự án đang dùng; đừng ép mọi lỗi parse, key, issuer và claim thành cùng một subclass.

**Không kiểm chứng claim bằng cách bắt exception ở controller.** Nếu token có claim cần thiết cho quy tắc authentication, hãy chặn trước khi controller nhận request. Nếu chỉ một endpoint yêu cầu claim đó, có thể thực thi rule tại authorization layer, nhưng cần quy định rõ hành vi 401/403 và dùng test phù hợp với ranh giới đã chọn.

## 8. Reactive: cùng một token thực, khác decoder và test client

Spring WebFlux dùng `SecurityWebFilterChain` và `ReactiveJwtDecoder`, không sử dụng `HttpSecurity` hay `JwtDecoder` của Servlet:

```java
@Configuration
@EnableWebFluxSecurity
class ReactiveApiSecurityConfig {

    @Bean
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .build();
    }
}
```

Với test Reactive, phải có `ReactiveJwtDecoder` xác minh cùng public key mà `JwtEncoder` thử nghiệm đã dùng để ký:

```java
@Bean
ReactiveJwtDecoder reactiveJwtDecoder(KeyPair localTestKeyPair) {
    NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder.withPublicKey(
            (RSAPublicKey) localTestKeyPair.getPublic())
            .build();

    OAuth2TokenValidator<Jwt> tenantValidator = jwt -> {
        Object tenant = jwt.getClaims().get("tenant_id");
        List<String> audience = jwt.getAudience();

        if (!(tenant instanceof String value) || value.isBlank()
                || audience == null
                || !audience.contains("orders-api")) {
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "claim contract failed",
                    null
                )
            );
        }
        return OAuth2TokenValidatorResult.success();
    };

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(
                "https://issuer.example.test"),
            tenantValidator
        )
    );
    return decoder;
}
```

Đoạn này là **bean của fixture Reactive**. Nếu chạy đồng thời cấu hình WebFlux và Servlet trong một ứng dụng, phải đảm bảo framework và test slice dùng đúng stack; không nhập cả hai security chain vào một test context rồi mong các bean tự thay thế lẫn nhau.

`WebTestClient` có thể gửi bearer token thật qua header:

```java
@Autowired WebTestClient webTestClient;

@Test
void numericTenantReturns401() {
    String token = activeToken(42, "orders:read");

    webTestClient.get()
        .uri("/api/orders/42")
        .headers(headers -> headers.setBearerAuth(token))
        .exchange()
        .expectStatus().isUnauthorized();
}

@Test
void validTenantMissingScopeReturns403() {
    String token = activeToken("tenant-a", "profile");

    webTestClient.get()
        .uri("/api/orders/42")
        .headers(headers -> headers.setBearerAuth(token))
        .exchange()
        .expectStatus().isForbidden();
}

@Test
void validTenantWithScopeReturns200() {
    String token = activeToken("tenant-a", "orders:read");

    webTestClient.get()
        .uri("/api/orders/42")
        .headers(headers -> headers.setBearerAuth(token))
        .exchange()
        .expectStatus().isOk();
}
```

Các phương thức trên giả định một WebFlux test context đã cấu hình security filter chain, `ReactiveJwtDecoder`, endpoint và fixture `JwtEncoder` tương ứng. Có thể dùng `@SpringBootTest` + `@AutoConfigureWebTestClient` với ứng dụng WebFlux, hoặc `@WebFluxTest` + `@Import` các bean cần thiết. Với `@WebFluxTest`, phải đảm bảo security chain và reactive decoder được nạp vào slice. Đó là điều kiện để token đi qua cơ chế xác thực thật.

Nếu test chạy với `@SpringBootTest(webEnvironment = RANDOM_PORT)`, `WebTestClient` gửi HTTP thực qua cổng ứng dụng: JWT vẫn phải được ký bằng khóa test mà **server** tin cậy. Các helper mock dành cho context-bound WebTestClient không tự trở thành authentication bên phía server chỉ vì client gọi chúng.

**Lưu ý khi triển khai:** `JwtEncoder` từ `spring-security-oauth2-jose` có thể được dùng trong cả hai loại test để tạo chuỗi token. Nhưng đối với decoder, Servlet dùng `JwtDecoder` và Reactive dùng `ReactiveJwtDecoder`; matcher/entry point/status vẫn phải kiểm chứng ở đúng filter chain.

## 9. Vì sao @WithMockUser, jwt(), mockJwt() không bắt được lỗi token thật?

`spring-security-test` cung cấp các helper mạnh để kiểm thử authorization nhanh:

```java
// Servlet: chèn một Authentication đã có authorities.
mvc.perform(get("/api/orders/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders:read"))))
    .andExpect(status().isOk());

// Reactive: tương tự, chèn mock JWT Authentication.
webTestClient
    .mutateWith(mockJwt().authorities(
        new SimpleGrantedAuthority("SCOPE_orders:read")))
    .get().uri("/api/orders/42")
    .exchange().expectStatus().isOk();
```

Dù ứng dụng đã thêm validator yêu cầu `tenant_id`, hai đoạn test trên **có thể vẫn PASS** vì helper đã tạo authentication để kiểm tra quyền mà không đi qua khâu giải mã bearer token từ header. Đó không phải bug của `spring-security-test`, mà là mục tiêu của hai loại test khác nhau.

| Kỹ thuật | Kiểm tra được điều gì? | Không chứng minh được |
|---|---|---|
| `@WithMockUser` | Rule access với user/roles giả lập trong SecurityContext | JWT compact parser, chữ ký, issuer, audience, thời hạn |
| `SecurityContext`/`authentication(...)` | Quyền của một `Authentication` do test dựng | Token có thể decode/verify từ HTTP hay không |
| Servlet `with(jwt())` | Mapping/authorization khi dùng `JwtAuthenticationToken` giả lập | Chữ ký, thuật toán, claim validation của decoder thật |
| Reactive `mutateWith(mockJwt())` | Authorization với JWT authentication giả lập trong mock exchange | Đường đi HTTP bearer qua `ReactiveJwtDecoder` |
| `oauth2Login()` | Hành vi khi có OAuth2 authentication giả lập | Authorization-code callback và access token validation |
| `oidcLogin()` | Hành vi khi có OIDC principal giả lập | Chữ ký ID Token, nonce, OIDC provider flow thực tế |
| Gửi `Authorization: Bearer <JWT ký thật>` | Parser, verify, validate, authenticate, authorize trên HTTP | Tự động chứng minh mọi tích hợp production (mạng JWKS, rotation, clock skew, issuer thực) |

Khi muốn kiểm tra **thiếu claim**, phải ký một token thật **không chứa claim đó** và gửi qua header. Khi muốn kiểm tra **sai kiểu**, phải ký token thật có claim kiểu JSON ngoài hợp đồng và xác minh request bị từ chối ở authentication. `with(jwt())` vẫn có thể dùng để test nhánh “thiếu scope → 403” một cách nhanh chóng, nhưng không thay cho bài test claim thực.

OIDC và JWT access token cũng không đồng nhất. `oidcLogin()` đưa `OidcUser` vào phiên đăng nhập giả lập; nó không tự kiểm chứng một **bearer access token** dành cho resource server. ID Token của OIDC và JWT access token có mục đích, audience và quy tắc xác minh khác nhau. Cần test đúng loại token mà endpoint thực sự chấp nhận.

## 10. Những trường hợp biên của claim nên đưa vào test

Hợp đồng claim cần cụ thể trước khi chọn kết quả kỳ vọng:

| Claim / cấu trúc | Ca lỗi gợi ý | Điểm cần kiểm chứng |
|---|---|---|
| `sub` | Thiếu, `""`, number thay string | Nếu ứng dụng bắt buộc chủ thể định danh, thêm validator rõ ràng |
| `iss` | Thiếu hoặc khác issuer tin cậy | Issuer validator phải từ chối |
| `aud` | Không chứa audience API, thiếu, sai kiểu | Định nghĩa đúng audience; chấp nhận biến thể array/string hợp lệ theo chuẩn |
| `exp` | Quá hạn, sai kiểu, thiếu nếu ứng dụng yêu cầu | Timestamp validator; cân nhắc clock skew và quy định có bắt buộc exp hay không |
| `nbf` | Thời điểm chưa hiệu lực | Kiểm tra phép thử vượt quá clock skew |
| `iat` | Tương lai quá xa, không có nếu issuer bỏ qua | Chỉ kết luận lỗi nếu policy ứng dụng thực sự kiểm tra |
| `scope`/`scp` | Thiếu, sai format, không chứa quyền yêu cầu | Phân biệt lỗi format token (401 nếu policy từ chối) và thiếu authority (403) |
| `tenant_id` | Thiếu, `null`, `42`, `true`, `[]`, `{}`, `""` | Validator custom kiểm tra type và business contract |
| JWT compact | 1/2 đoạn, base64url hỏng, JSON không hợp lệ | Decoder phải từ chối mà không xử lý controller |
| JWS header | `alg=none`, thuật toán lạ, `kid` không khớp trust config | Chỉ cho phép thuật toán/khóa tin cậy |
| JWS signature | Đổi payload hoặc signature sau khi ký | Chữ ký bị từ chối |
| Token đúng nhưng không đủ quyền | Có tenant hợp lệ, scope `profile` | 403, tránh nhầm với 401 |

Ví dụ `"aud": "orders-api"` và `"aud": ["orders-api"]` đều phù hợp chuẩn JWT; nếu ứng dụng chỉ nhận một biểu diễn do đặc thù issuer, cần ghi rõ đó là **policy riêng**, không gọi biến thể chuẩn còn lại là token sai cấu trúc. Đối với `scope`, RFC và implementation của từng issuer có thể khác: hãy kiểm tra converter thay vì tự mặc định JSON array hay string sẽ luôn dẫn đến lỗi.

### 10.1. Không để phép thử thời gian bị flakey

Thay vì tạo `exp` chỉ cách hiện tại một giây rồi assert 401, đặt quá hạn cách xa thời gian cho phép lệch đồng hồ (clock skew). Ví dụ `exp = now - 10 phút`, `iat = now - 15 phút` trong bài test expired. Muốn kiểm tra chính xác biên `exp`/`nbf`, có thể cấu hình `JwtTimestampValidator` với `Clock`/leeway phù hợp theo API của phiên bản đang dùng; chỉ cố định kết quả khi xác định được clock và skew.

### 10.2. Không khẳng định mọi sai kiểu đều được framework bắt sẵn

Decoder và claim converter có thể chuyển đổi claim tiêu chuẩn (ví dụ `aud`) sang kiểu nhất quán, hoặc ném lỗi khi gặp giá trị không thể parse. Với claim riêng `tenant_id`, nếu không có validator như mục 4.2, việc token có giá trị `42` không đảm bảo Spring Security mặc định trả 401. Có thể authentication vẫn thành công và lỗi chỉ xuất hiện khi code nghiệp vụ ép kiểu.

Thiết kế đáng tin cậy gồm hai phần: **định nghĩa hợp đồng** và **viết phép thử thất bại đúng tại ranh giới**. Không viết assertion 401 cho policy chưa từng được triển khai.

## 11. An toàn với issuer, thuật toán, khóa và thông tin lỗi

Một test “token thực” có ý nghĩa khi cấu hình của nó vẫn giữ các bảo đảm bảo mật:

1. **Khóa/thuật toán được tin cậy:** decoder giới hạn thuật toán và nguồn khóa; không chấp nhận `alg=none` hay khóa nhúng tùy ý trong token. Test nên có trường hợp chữ ký giả mạo.
2. **Issuer và audience rõ ràng:** `iss` chứng minh nguồn phát hành mong đợi, `aud` chứng minh token được dành cho đúng API. Tránh chỉ kiểm tra mỗi signature.
3. **Thời gian:** kiểm tra `exp`/`nbf`, cân nhắc clock skew; quyết định rõ việc thiếu `exp` có bị cấm hay không.
4. **Đúng loại token:** ID token dùng để đăng nhập OIDC không mặc nhiên thay thế access token để gọi API; phân biệt bearer JWT với opaque token.
5. **Không lộ bí mật:** dùng khóa tạo tại runtime test, không commit khóa production, không in access token/secret vào log kiểm thử.
6. **Không tùy tiện tái sử dụng quyền:** token đã decode nhưng có authority sai vẫn phải bị 403 tại endpoint bảo vệ.
7. **Đảm bảo xử lý lỗi:** dữ liệu bất thường không được dẫn đến exception 500 không kiểm soát; nếu một kiểu claim gây lỗi runtime, tìm cách kiểm tra/chuẩn hóa ở boundary.

Đừng tự viết thuật toán xác minh JWT bằng cách so sánh Base64URL string. Hãy dùng `JwtDecoder` / `ReactiveJwtDecoder` và validator thích hợp; chỉ dùng parsing payload thuần túy để *quan sát* dữ liệu, không làm bằng chứng authentication.

## 12. Bài thực hành: ma trận kiểm thử hoàn chỉnh

Giả sử API `GET /api/orders/42` có hợp đồng `iss` đúng issuer, `aud` chứa `orders-api`, `tenant_id` là string không rỗng và cần `SCOPE_orders:read`.

Hãy tạo một `JwtEncoder` test và cùng một public key cho decoder rồi thực hiện:

1. **Không có credential:** gửi GET không có `Authorization` → 401.
2. **Sai compact JWS:** gửi `Authorization: Bearer abc.def` → bị parser/decoder từ chối; xác minh 401 theo resource server mặc định.
3. **Sai chữ ký:** tạo JWT đã ký rồi đổi signature → 401.
4. **Quá hạn:** ký JWT với `exp` quá khứ rõ rệt → 401.
5. **Claim thiếu:** ký JWT không có `tenant_id` → 401 qua custom validator.
6. **Claim sai kiểu:** ký JWT có `tenant_id = 42` hoặc `tenant_id = []` → 401 qua custom validator.
7. **Sai audience:** JWT ký đúng nhưng `aud` không chứa `orders-api` → 401.
8. **Thiếu scope:** JWT đúng hoàn toàn nhưng chỉ có `profile` → 403.
9. **Happy path:** JWT đúng có `orders:read` → 200, controller trả dữ liệu.
10. **Đối chứng mock:** kiểm tra cùng endpoint bằng `with(jwt())` hoặc `mockJwt()` với authority đúng → pass authorization; ghi nhận phép thử này không xác minh bất kỳ chuỗi JWT nào.

Để phân tích lỗi, ghi kết quả thành ba cột: **token đầu vào**, **lớp xử lý từ chối** và **HTTP status**. Nếu test claim sai kiểu bất ngờ cho 200 hoặc 403, hãy kiểm tra claim có được validate ở decoder không. Nếu token hoàn toàn hợp lệ lại cho 401, kiểm tra bộ khóa, issuer, audience và thời gian trước khi chỉnh rule phân quyền.

**Tiêu chí hoàn thành bài:** Bộ test phải chứng minh rõ ba kết quả độc lập: **token không đạt hợp đồng xác thực bị từ chối (thường 401); token đã xác thực nhưng thiếu quyền nhận 403; token đã xác thực và đủ quyền đi đến controller thành công (200)**. Tối thiểu một số phép thử phải gửi **Bearer token được ký thật** qua HTTP; chỉ có `@WithMockUser` hoặc `jwt()` giả lập chưa đủ để kiểm chứng lỗi claim và cấu trúc JWT.
