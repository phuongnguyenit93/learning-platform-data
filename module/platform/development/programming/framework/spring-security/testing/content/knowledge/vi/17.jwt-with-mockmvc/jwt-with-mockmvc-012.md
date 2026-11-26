# Phân biệt jwt helper, decoder giả lập và token được xác minh mật mã

Khi kiểm thử Spring Security Resource Server bằng `MockMvc`, việc endpoint trả `200 OK` sau khi dùng `jwt()` **không chứng minh ứng dụng xác minh được chữ ký JWT**. Helper này chuẩn bị một đối tượng `JwtAuthenticationToken` cho request kiểm thử, trong khi việc đọc Bearer token, gọi `JwtDecoder`, xác minh chữ ký JWS và kiểm tra các claim là những bước khác nhau.

Bài này thuộc module **SPRING_SECURITY_TESTING**: kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test`. Trọng tâm là ứng dụng **Servlet + MockMvc**; phần cuối liên hệ nhanh với `WebTestClient` cho Reactive. Sau bài học, bạn phải chọn được mức kiểm thử phù hợp, diễn giải chính xác một test đang bảo vệ điều gì, và phát hiện các test “xanh” nhưng chưa kiểm chứng tính hợp lệ của access token.

## 1. Ba mức kiểm thử JWT không có cùng phạm vi bảo đảm

Hãy hình dung Resource Server nhận request:

```http
GET /api/orders
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

Đường đi bình thường của một Bearer JWT qua Spring Security Servlet như sau:

```mermaid
flowchart TD
    A["HTTP Authorization: Bearer ..."] --> B["BearerTokenAuthenticationFilter"]
    B --> C["JwtAuthenticationProvider"]
    C --> D["JwtDecoder"]
    D --> E{"Chữ ký + validators hợp lệ?"}
    E -->|Không| F["401 Unauthorized"]
    E -->|Có| G["JwtAuthenticationConverter"]
    G --> H["JwtAuthenticationToken / SecurityContext"]
    H --> I{"Có authority cần thiết?"}
    I -->|Không| J["403 Forbidden"]
    I -->|Có| K["Controller / Service"]
```

Trong kiểm thử, có ba cách đi vào sơ đồ này:

| Cách kiểm thử | Điều bạn tạo trong test | Phần thực sự được đi qua | Điều **không** được chứng minh |
| --- | --- | --- | --- |
| `.with(jwt())` của `spring-security-test` | `Jwt` và `JwtAuthenticationToken` giả đặt vào security context | Các kiểm tra phân quyền sau khi đã có authentication; controller/service nhận principal | Bearer header, `JwtDecoder`, chữ ký, thời hạn và issuer/audience của token |
| Giả lập `JwtDecoder` | Header `Authorization: Bearer ...` + kết quả `decode(...)` do Mockito chỉ định | Bearer filter, authentication provider, converter, quyết định `401/403` | Chữ ký được xác minh thật; decoder giả chỉ trả dữ liệu đã sắp đặt |
| JWT được **ký thật** + decoder thật | Chuỗi JWT compact JWS và cặp khóa kiểm thử | HTTP Bearer flow, phân tích token, xác minh chữ ký, các validators được cấu hình, converter, authorization | Những phần ngoài phạm vi test như TLS, discovery/JWKS từ nhà cung cấp thật hoặc cấp phát token tại Identity Provider |

Tên `jwt()` của helper dễ gây nhầm lẫn: đây là **request post-processor**, không phải hàm phát hành JWT được ký mật mã. Theo tài liệu Spring Security, JWT mặc định của helper thậm chí có header `alg: none` và claim `scope: read`. Test vẫn có thể được phép khi policy chỉ cần quyền `SCOPE_read`, vì không có chữ ký nào được xác minh ở đường đi này.

> **Quy tắc đánh giá:** test sử dụng mock vẫn có giá trị. Chỉ cần mô tả đúng ranh giới nó chứng minh. Phân quyền, ánh xạ claim và xác minh mật mã là ba trách nhiệm nên có các test riêng.

## 2. Ứng dụng Servlet mẫu dùng chung cho các ca thử

Giả sử ứng dụng dùng Spring Boot, Spring MVC, Spring Security OAuth2 Resource Server và JUnit 5. Các ví dụ dưới đây dùng Java 17+, lược bỏ `package`/`import`; có thể chuyển thành test trong dự án đã cấu hình Spring Boot và Security.

Các dependency Gradle chính:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Tạo endpoint đọc principal dạng `Jwt`:

```java
@RestController
@RequestMapping("/api")
class OrderController {

    @GetMapping("/orders")
    Map<String, String> list(@AuthenticationPrincipal Jwt jwt) {
        return Map.of(
            "subject", jwt.getSubject(),
            "result", "orders-visible"
        );
    }
}
```

Cấu hình policy: caller phải có authority `SCOPE_orders.read`.

```java
@Configuration
class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

Khi xác thực JWT kiểu Resource Server theo mặc định, claim `scope` hoặc `scp` được chuyển thành authorities có tiền tố `SCOPE_`. Với `scope: "orders.read"`, policy trên nhận `SCOPE_orders.read`.

**Điều kiện của các test:** nạp `SecurityFilterChain` thật vào `MockMvc`. Trong Spring Boot, `@SpringBootTest` + `@AutoConfigureMockMvc` thường đảm nhiệm việc này. Với `MockMvcBuilders` tự dựng, cần áp dụng `springSecurity()` để kết nối các filter và security context. Resource Server cũng phải có một `JwtDecoder` bean hợp lệ trong test context; nếu thiếu, ứng dụng có thể không khởi tạo được dù test chỉ dùng helper `jwt()`.

Tất cả các ví dụ sau dùng URL `/api/orders` và cùng policy này, giúp so sánh kết quả trên một hành vi rõ ràng.

## 3. Mức 1: dùng jwt() để kiểm tra phân quyền nhanh và ổn định

`SecurityMockMvcRequestPostProcessors.jwt()` tạo một `JwtAuthenticationToken` và gắn nó với request kiểm thử. Khi đi qua cơ chế security test, controller đọc được `Jwt` từ `SecurityContext` mà không cần đưa Bearer token thật vào header.

Ví dụ với Spring Boot có Spring Framework 6.2+ / Spring Boot 3.4+:

```java
@SpringBootTest
@AutoConfigureMockMvc
class JwtHelperMvcTest {

    @Autowired MockMvc mvc;

    // Cho test context có JwtDecoder bean; helper không gọi decoder này.
    @MockitoBean JwtDecoder jwtDecoder;

    @Test
    void helperAllowsScopeWithoutAnySignedToken() throws Exception {
        mvc.perform(get("/api/orders")
                .with(jwt().jwt(jwt -> jwt
                    .claim("sub", "alice")
                    .claim("scope", "orders.read")
                )))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.subject").value("alice"));

        verifyNoInteractions(jwtDecoder);
    }

    @Test
    void helperDeniesMissingAuthority() throws Exception {
        mvc.perform(get("/api/orders")
                .with(jwt().jwt(jwt -> jwt
                    .claim("sub", "bob")
                    .claim("scope", "inventory.read")
                )))
            .andExpect(status().isForbidden());

        verifyNoInteractions(jwtDecoder);
    }
}
```

`@MockitoBean` thuộc `org.springframework.test.context.bean.override.mockito.MockitoBean`. Với các dự án Spring Boot cũ hơn chưa có annotation này, dùng `@MockBean` của Spring Boot theo phiên bản đang sử dụng. Không cần stubbing `decode` trong hai test này: request không mang Bearer header; `jwt()` đã chuẩn bị authentication.

Một ca dùng `jwt()` còn có thể cố tình tạo claim không đáng tin:

```java
mvc.perform(get("/api/orders")
        .with(jwt().jwt(jwt -> jwt
            .header("alg", "none")
            .claim("sub", "alice")
            .claim("scope", "orders.read")
            .claim("iss", "https://untrusted.example.invalid")
        )))
    .andExpect(status().isOk());
```

Kết quả `200` **không phải lỗ hổng của Resource Server**: đây là test cố ý tiêm authentication giả, nên decoder và validator của token chưa được gọi. Ca này rất hữu ích khi kiểm tra **authorization policy** độc lập với hệ thống cấp token.

### Khi nào tùy chỉnh authorities?

Mặc định helper suy ra authorities từ `scope`/`scp`. Bạn cũng có thể truyền thẳng quyền:

```java
mvc.perform(get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )))
    .andExpect(status().isOk());
```

Cách này tách kiểm thử **quyết định phân quyền** khỏi kiểm thử ánh xạ claim → authority. Nếu hệ thống có `JwtAuthenticationConverter` tùy biến, cấp thẳng `authorities(...)` **không kiểm tra** rằng converter sản xuất thực sự ánh xạ claim đúng. Hãy kiểm thử converter riêng hoặc dùng đường đi Bearer + decoder ở mục 4/5.

Cũng không nên dùng `@WithMockUser` để thay thế mọi trường hợp JWT: nó thường tạo `UsernamePasswordAuthenticationToken` với principal dạng `UserDetails`, trong khi Resource Server JWT dùng `JwtAuthenticationToken` và principal `Jwt`. Test dựa vào `@AuthenticationPrincipal Jwt`, `sub`, `aud`, scope hoặc custom JWT converter cần đúng loại authentication.

## 4. Mức 2: giả lập JwtDecoder nhưng vẫn đi qua Bearer filter

Một test muốn xác minh request truyền token qua `Authorization`, Spring Security đọc Bearer header, converter ánh xạ claim và endpoint trả `401` hay `403` nên sử dụng **header thật về mặt HTTP** cùng `JwtDecoder` giả lập.

Ở mức này, `BearerTokenAuthenticationFilter` nhận chuỗi token, `JwtAuthenticationProvider` gọi `decoder.decode(token)`, còn Mockito quyết định dữ liệu `Jwt` trả về hoặc exception ném ra. Vì vậy, test vẫn chưa kiểm tra chữ ký RSA/EC hoặc liên hệ với JWK Set thật.

```java
@SpringBootTest
@AutoConfigureMockMvc
class MockDecoderMvcTest {

    @Autowired MockMvc mvc;
    @MockitoBean JwtDecoder jwtDecoder;

    private static Jwt decodedJwt(String rawToken, String sub, String scope) {
        Instant now = Instant.now();
        return Jwt.withTokenValue(rawToken)
            .header("alg", "RS256")
            .claim("sub", sub)
            .claim("scope", scope)
            .issuedAt(now)
            .expiresAt(now.plusSeconds(300))
            .build();
    }

    @Test
    void bearerTokenDecodedByMockThenAuthorized() throws Exception {
        when(jwtDecoder.decode("fixture-token")).thenReturn(
            decodedJwt("fixture-token", "alice", "orders.read")
        );

        mvc.perform(get("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer fixture-token"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.subject").value("alice"));

        verify(jwtDecoder).decode("fixture-token");
    }

    @Test
    void decodedTokenWithoutRequiredScopeGets403() throws Exception {
        when(jwtDecoder.decode("limited-token")).thenReturn(
            decodedJwt("limited-token", "bob", "inventory.read")
        );

        mvc.perform(get("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer limited-token"))
            .andExpect(status().isForbidden());

        verify(jwtDecoder).decode("limited-token");
    }

    @Test
    void decoderRejectsBadTokenWith401() throws Exception {
        when(jwtDecoder.decode("invalid-token"))
            .thenThrow(new BadJwtException("JWT rejected by test decoder"));

        mvc.perform(get("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer invalid-token"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE, containsString("Bearer")
            ));

        verify(jwtDecoder).decode("invalid-token");
    }
}
```

Một request không mang token đến endpoint được bảo vệ thường nhận `401 Unauthorized` trong cấu hình Resource Server này. Trường hợp **đã xác thực nhưng không có scope cần thiết** nhận `403 Forbidden`.

| Trạng thái request | Nơi thất bại | Kết quả thường gặp |
| --- | --- | --- |
| Không có Bearer token và không có authentication hợp lệ | Authentication entry point | `401` |
| Header Bearer chứa token bị decoder từ chối | `JwtAuthenticationProvider` / `JwtDecoder` | `401` |
| Decoder trả `Jwt` hợp lệ theo fixture, nhưng thiếu `SCOPE_orders.read` | Authorization | `403` |
| Decoder trả `Jwt` có scope phù hợp | Controller | `200` |

### “alg: RS256” trong một mock không có giá trị mật mã

Trong `decodedJwt`, dòng `.header("alg", "RS256")` chỉ đặt **metadata trong đối tượng Java**. Không có chữ ký được tạo, không có phép tính RSA nào được thực hiện. Tương tự, `.expiresAt(...)` trong một `Jwt` do Mockito trả về không tự chứng minh việc kiểm tra thời gian hoạt động: hành vi đó thuộc decoder/validator thật, đã bị thay thế bằng mock.

Với một decoder được mock, test này chứng minh được:

- Ứng dụng đi qua Bearer filter và gọi `decode` với đúng raw token.
- `JwtAuthenticationConverter` đang cấu hình (nếu áp dụng trong flow Resource Server) chuyển claims thành authentication.
- HTTP authorization xử lý authentication thành công và thất bại theo tình huống đã stub.

Nó không chứng minh `exp`, `nbf`, `iss`, `aud`, `kid` hoặc chữ ký được hệ thống xác minh đúng. Để làm điều đó, cần decoder thật và token compact đã ký thật.

## 5. Mức 3: ký JWT thật và để NimbusJwtDecoder xác minh chữ ký

Mục tiêu ở mức này là giữ nguyên đường đi HTTP của Resource Server, **không mock `JwtDecoder`**, phát một JWT có chữ ký `RS256` bằng private key kiểm thử và cấu hình decoder tin cậy public key tương ứng.

Test chạy hoàn toàn local với khóa sinh tạm. Không cần gọi Identity Provider ngoài, không dùng khóa production, không ghi khóa riêng vào mã nguồn. Trong thực tế, JWKS có thể chứa nhiều khóa và luân phiên `kid`; ví dụ dưới đây cố ý kiểm chứng **một public key tin cậy** để tập trung vào phép xác minh chữ ký.

### 5.1. Tạo decoder thật và validators cần thiết

```java
@SpringBootTest
@AutoConfigureMockMvc
@Import(VerifiedJwtMvcTest.CryptoConfig.class)
class VerifiedJwtMvcTest {

    private static final String ISSUER = "https://issuer.example.test";
    private static final String AUDIENCE = "orders-api";
    private static final KeyPair TRUSTED_KEYS = generateRsaKeyPair();

    @Autowired MockMvc mvc;

    @TestConfiguration
    static class CryptoConfig {

        @Bean
        @Primary
        JwtDecoder jwtDecoder() {
            NimbusJwtDecoder decoder = NimbusJwtDecoder
                .withPublicKey((RSAPublicKey) TRUSTED_KEYS.getPublic())
                .build();

            OAuth2TokenValidator<Jwt> issuerAndTime =
                JwtValidators.createDefaultWithIssuer(ISSUER);

            OAuth2TokenValidator<Jwt> audience =
                new JwtClaimValidator<List<String>>(
                    "aud",
                    values -> values != null && values.contains(AUDIENCE)
                );

            decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
                issuerAndTime, audience
            ));

            return decoder;
        }
    }

    private static KeyPair generateRsaKeyPair() {
        try {
            KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
            generator.initialize(2048);
            return generator.generateKeyPair();
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException(ex);
        }
    }

    // Các test và hàm sign() được bổ sung ở phần tiếp theo.
}
```

`NimbusJwtDecoder.withPublicKey(...)` thực hiện kiểm tra chữ ký JWS bằng public key được cấu hình. `JwtValidators.createDefaultWithIssuer(...)` bổ sung kiểm tra issuer cùng các kiểm tra mặc định liên quan đến thời gian/token. `aud` là yêu cầu của API mẫu nên test cấu hình validator audience riêng; đừng mặc định cho rằng mọi decoder tự biết audience mà hệ thống cần.

Nếu ứng dụng đã tự đăng ký `JwtDecoder`, phải cô lập profile/context kiểm thử hoặc bảo đảm decoder test được chọn rõ ràng, tránh nhiều bean gây nhập nhằng. `@Primary` chỉ giúp lựa chọn khi autowire theo type, không khắc phục một filter chain đã cố định sử dụng decoder khác.

### 5.2. Ký compact JWS bằng private key

`SignedJWT` và `RSASSASigner` thuộc thư viện Nimbus JOSE + JWT, thường có trên classpath nhờ Spring Security OAuth2 JWT. Hàm này tạo token compact thực sự có ba phần `header.payload.signature`.

```java
private static String signToken(
        PrivateKey signingKey,
        String subject,
        String scope,
        Instant issuedAt,
        Instant expiresAt) throws JOSEException {

    JWTClaimsSet claims = new JWTClaimsSet.Builder()
        .issuer(ISSUER)
        .audience(AUDIENCE)
        .subject(subject)
        .issueTime(Date.from(issuedAt))
        .expirationTime(Date.from(expiresAt))
        .claim("scope", scope)
        .build();

    SignedJWT signed = new SignedJWT(
        new JWSHeader.Builder(JWSAlgorithm.RS256)
            .type(JOSEObjectType.JWT)
            .build(),
        claims
    );

    signed.sign(new RSASSASigner((RSAPrivateKey) signingKey));
    return signed.serialize();
}
```

Đặt `signToken` và `generateRsaKeyPair` làm các helper `static` bên trong test class ở mục 5.1. Vì vậy, `ISSUER`, `AUDIENCE` và `TRUSTED_KEYS` là cùng giá trị giữa issuer validator, signer và các test.

### 5.3. Kiểm tra token được chấp nhận và chữ ký sai bị loại

```java
@Test
void signedTokenFromTrustedKeyIsAccepted() throws Exception {
    Instant now = Instant.now();
    String token = signToken(
        TRUSTED_KEYS.getPrivate(),
        "alice",
        "orders.read",
        now,
        now.plusSeconds(300)
    );

    mvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.subject").value("alice"));
}

@Test
void tokenSignedByUnknownKeyIsRejected() throws Exception {
    KeyPair attackerKeys = generateRsaKeyPair();
    Instant now = Instant.now();

    String token = signToken(
        attackerKeys.getPrivate(), // Không khớp public key decoder tin cậy.
        "alice",
        "orders.read",
        now,
        now.plusSeconds(300)
    );

    mvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isUnauthorized());
}

@Test
void signedButExpiredTokenIsRejected() throws Exception {
    Instant now = Instant.now();

    String token = signToken(
        TRUSTED_KEYS.getPrivate(),
        "alice",
        "orders.read",
        now.minusSeconds(3600),
        now.minusSeconds(1800)  // Đã hết hạn lâu hơn clock skew.
    );

    mvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isUnauthorized());
}

@Test
void validSignatureWithoutScopeIsForbidden() throws Exception {
    Instant now = Instant.now();

    String token = signToken(
        TRUSTED_KEYS.getPrivate(),
        "alice",
        "inventory.read",
        now,
        now.plusSeconds(300)
    );

    mvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isForbidden());
}
```

Các test này tách hai loại lỗi:

- **`401`**: token không qua xác thực, chẳng hạn chữ ký không khớp khóa tin cậy, hết hạn hoặc sai issuer/audience theo validator.
- **`403`**: token có thể đã được xác thực đúng nhưng thiếu authority để gọi endpoint.

Nên bổ sung test `wrong issuer`, `wrong audience`, `not-before` trong tương lai bằng cách thay builder của `JWTClaimsSet`; **mỗi lỗi nên được chứng minh ở tầng decoder thật**. Nếu test thay trực tiếp `JwtDecoder` bằng Mockito để ném exception, ta chỉ thử xử lý exception chứ chưa kiểm tra validator thực sự bắt lỗi.

Một test ký với public key tĩnh vẫn **chưa** kiểm chứng tải khóa qua `jwks_uri`, lựa chọn khóa theo `kid`, cache, refresh hoặc xoay khóa. Muốn kiểm thử các phần đó, cấu hình `NimbusJwtDecoder.withJwkSetUri(...)` và chạy một HTTP server JWKS giả lập với các bộ khóa/thời điểm thay đổi có kiểm soát. Test đó vẫn có thể thực hiện local, không cần gọi máy chủ thật.

## 6. Bẫy kiểm thử JWT thường làm kết quả “xanh giả”

### 6.1. Gửi token vào HTTP header nhưng lại dùng jwt() helper

```java
mvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer garbage")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )))
    .andExpect(status().isOk());
```

Đây **không phải** phép thử rằng `garbage` là JWT hợp lệ. Helper đã nạp một authentication hợp lệ cho request. Một số cấu hình filter có thể cố xử lý Bearer header và cho kết quả khác, nên **không trộn hai kỹ thuật** để suy ra decoder đã hoạt động. Khi thử Bearer filter, chỉ gửi header và tạo decoder giả/decoder thật theo mục tiêu.

### 6.2. Bỏ qua SecurityFilterChain

`MockMvcBuilders.standaloneSetup(controller)` không tự động mang toàn bộ Spring Security filter. Với một test chỉ dựng controller, `.with(jwt())` có thể không được chuyển thành authentication theo cách mong đợi, hoặc policy HTTP chẳng được kiểm chứng. Hãy dùng context đủ cấu hình và áp dụng `springSecurity()` khi dựng `MockMvc` thủ công.

```java
MockMvc mvc = MockMvcBuilders
    .webAppContextSetup(webApplicationContext)
    .apply(springSecurity())
    .build();
```

Tránh tắt filter bằng `@AutoConfigureMockMvc(addFilters = false)` trong bài kiểm thử mục đích bảo vệ HTTP.

### 6.3. Test đúng 200 nhưng quên assert principal hoặc authority

`status().isOk()` chưa đủ khi endpoint public hay một test configuration vô tình `permitAll()`. Hãy kiểm tra claim identity được controller nhìn thấy (`jsonPath("$.subject")`), đồng thời viết ca `403` khi scope sai. Với chính sách trên tài nguyên cụ thể, dùng ít nhất hai tài khoản (chủ sở hữu và người ngoài).

### 6.4. Mock JwtDecoder nhưng nói đã “verify signature”

`when(jwtDecoder.decode("x")).thenReturn(jwt)` chứng minh mock trả về `Jwt` đã dàn dựng. Header `alg` của `Jwt` và các claim không chứng minh decoder kiểm tra chữ ký hay hết hạn. Cần một test sử dụng `NimbusJwtDecoder` thực và chuỗi token compact do signer phát hành.

### 6.5. Nhầm access token JWT với đăng nhập OIDC

Resource Server kiểm chứng **access token** đi vào API. `oidcLogin()` của `spring-security-test` là helper cho ứng dụng OAuth2/OIDC Client, nơi người dùng đã đăng nhập thông qua OIDC và có `OidcUser`. Một test `oidcLogin()` thành công không khẳng định endpoint Resource Server chấp nhận hoặc xác minh access token JWT. ID token cũng không tự động được dùng như access token của API: cần giữ đúng issuer, audience và token type theo hợp đồng xác thực.

### 6.6. Lẫn lộn kiểm thử crypto với xác thực thực tế ở Identity Provider

JWT ký bằng khóa test chỉ chứng minh verifier tin cậy public key tương ứng trong môi trường test. Nó không chứng minh token được nhà cung cấp thật phát, chu kỳ cấp lại token, giao thức OAuth2/OIDC, hoặc kết nối metadata/JWKS production. Những hành vi đó cần integration test với máy chủ mô phỏng hoặc môi trường thử nghiệm của nhà cung cấp, có kiểm soát đường mạng và khóa.

## 7. Chọn mức kiểm thử theo câu hỏi cần trả lời

| Câu hỏi của bài test | Chọn cách nào? | Khẳng định nên có |
| --- | --- | --- |
| Scope `orders.read` được vào endpoint, scope khác bị chặn? | `jwt()` | `200`/`403` và principal đúng |
| Tài khoản A được dữ liệu của mình nhưng B bị từ chối? | `jwt()` với hai principal hoặc token mock | Body/data đúng và `403` cho người ngoài |
| App đọc header Bearer và gọi decoder đúng raw token? | Mock `JwtDecoder` | `verify(decoder).decode(rawToken)` |
| JWT đã decode được map từ claim `scope` thành authority đúng? | Mock `JwtDecoder` + converter thật | `200`/`403` theo claims |
| Decoder ném lỗi thì API phản hồi gì? | Mock `JwtDecoder` | `401` và `WWW-Authenticate` |
| Chữ ký RSA sai có bị từ chối không? | Decoder thật + token ký bằng khóa khác | `401` |
| Token hết hạn, issuer hoặc audience sai có bị từ chối không? | Decoder thật + validators thật | `401` |
| App chọn `kid`, tải và refresh JWK Set đúng không? | Decoder thật + JWKS test server | Kết quả xác thực trước/sau khi đổi khóa |
| End-to-end OIDC login, nhận token từ Authorization Server? | OAuth2/OIDC client integration test | Redirect/callback/token exchange và session/principal đúng |

### Thêm một ca Reactive tương đương

Với **WebFlux/WebTestClient**, `mockJwt()` của `spring-security-test` có cùng mục đích tạo authentication giả cho test phân quyền; nó không tự kiểm chứng chữ ký JWT. Đường đi thực của resource server Reactive dùng `ReactiveJwtDecoder`, ví dụ `NimbusReactiveJwtDecoder`, thay vì `JwtDecoder` trên Servlet.

```java
webTestClient.mutateWith(mockJwt()
        .jwt(jwt -> jwt
            .claim("sub", "alice")
            .claim("scope", "orders.read")
        ))
    .get().uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
```

Đây là ví dụ **trong ứng dụng WebFlux đã cấu hình `SecurityWebFilterChain` và gắn `springSecurity()` với `WebTestClient`**. Không đưa `ReactiveJwtDecoder` vào test Servlet hoặc dùng `JwtDecoder` Servlet để kết luận đường đi Reactive. Khi muốn kiểm tra token ký thật ở WebFlux, tạo Bearer header và sử dụng `NimbusReactiveJwtDecoder` thật với validator tương ứng.

## 8. Bài thực hành kiểm chứng ba mức

1. Dựng `/api/orders` theo mục 2. Dùng `jwt()` với `scope=orders.read` và `scope=inventory.read`, khẳng định lần lượt `200` và `403`. Xác nhận mock `JwtDecoder` không được gọi.
2. Chuyển sang test truyền `Authorization: Bearer fixture-token`. Mock `JwtDecoder.decode` trả claim đúng, claim sai và ném `BadJwtException`. Khẳng định lần lượt `200`, `403` và `401`; xác nhận có lời gọi `decode`.
3. Bỏ mock decoder; tạo một cặp khóa RSA kiểm thử, cấu hình `NimbusJwtDecoder.withPublicKey(...)`, ký JWT thật với `RS256` và gửi compact token qua Bearer header.
4. Ký token bằng khóa không tin cậy hoặc đặt `exp` đã hết hạn; khẳng định decoder thật trả `401`. Ký hợp lệ nhưng scope sai, khẳng định `403`.
5. Thêm issuer/audience validator và các ca sai `iss`/`aud`. Bổ sung nhận xét trong tên test về điều mà từng test thực sự bảo đảm.

Để tự đánh giá, điền bảng kết quả sau:

| Test | `jwt()` | Mock `JwtDecoder` | Decoder thật |
| --- | :---: | :---: | :---: |
| Phân quyền theo scope | Có | Có | Có |
| Bearer filter nhận raw token | Không | Có | Có |
| `JwtAuthenticationConverter` thực nhận JWT từ decoder | Không mặc định | Có | Có |
| Chữ ký JWS được kiểm tra | Không | Không | Có |
| `exp`/`iss`/`aud` được xác minh theo validator thật | Không | Không | Có, nếu cấu hình |
| Cần hệ thống cấp token ngoài | Không | Không | Không bắt buộc khi ký bằng khóa test |

**Tiêu chí hoàn thành:** bạn không chỉ có các test chạy xanh mà còn mô tả được tầng bảo mật nào đã được đi qua. Một test `jwt()` xanh là bằng chứng tốt cho **policy phân quyền**; muốn khẳng định **chữ ký và claims của access token được kiểm chứng**, phải có test với decoder thật và token ký thật.

## Nguồn tham khảo

- [Spring Security — Testing OAuth 2.0 / Testing JWT Authentication](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): `jwt()`, tùy biến claims/authorities và lựa chọn mock `JwtDecoder`.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): Bearer flow, `NimbusJwtDecoder`, authority từ scope, issuer/audience validators.
- [Spring Security API — SecurityMockMvcRequestPostProcessors](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/servlet/request/SecurityMockMvcRequestPostProcessors.html): cơ chế cài `JwtAuthenticationToken` vào request.
- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): `ReactiveJwtDecoder` và `NimbusReactiveJwtDecoder`.
