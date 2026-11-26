# Gửi Authorization Bearer thật qua chuỗi filter

Trong một bài kiểm thử phân quyền, ta có thể dùng **jwt()** để dựng sẵn một **JwtAuthenticationToken** với subject và authorities mong muốn. Cách đó hữu ích khi chỉ cần kiểm tra endpoint cho phép hay từ chối một quyền. Tuy nhiên, nó không chứng minh ứng dụng có thể nhận và xác minh một JWT được gửi qua HTTP.

Bài này kiểm tra luồng xác thực của Resource Server bằng một JWT có chữ ký thật: test tạo token bằng khóa riêng RSA, gửi token trong header **Authorization: Bearer**, rồi để chính cấu hình bảo mật của ứng dụng đọc và xác minh token. Không cần gọi Identity Provider bên ngoài; một issuer dành riêng cho test cùng cặp khóa test là đủ để kiểm tra chuỗi filter và các validator.

Sau bài học, người học có thể:

- Phân biệt kiểm thử **jwt()**/**@WithMockUser** với kiểm thử Bearer token đi qua Resource Server.
- Tạo JWT có chữ ký bằng khóa riêng test và cấu hình decoder chỉ tin khóa công khai tương ứng.
- Kiểm tra chữ ký, issuer, audience và thời hạn của token.
- Phân biệt kết quả **401 Unauthorized** khi token không hợp lệ với **403 Forbidden** khi người dùng đã xác thực nhưng thiếu quyền.
- Gửi cùng loại Bearer token qua MockMvc hoặc WebTestClient.

## 1. Luồng nào đang được kiểm tra?

Với Servlet Resource Server, request mang Bearer token đi qua các bước chính:

1. **BearerTokenAuthenticationFilter** tìm token trong header **Authorization**.
2. Filter chuyển token tới **AuthenticationManager**.
3. **JwtAuthenticationProvider** gọi **JwtDecoder**.
4. Decoder phân tích JWT, xác minh chữ ký và chạy các validator.
5. Nếu hợp lệ, Spring Security tạo **JwtAuthenticationToken** cùng các authorities được ánh xạ từ claim.
6. Authorization filter kiểm tra quyền trên endpoint trước khi request tới controller.

Với WebFlux, **AuthenticationWebFilter** và **ReactiveJwtDecoder** thực hiện luồng tương ứng theo kiểu reactive.

Điểm quan trọng là token phải được gửi như một HTTP credential. Test không tự đặt Authentication vào **SecurityContext**, vì làm như vậy sẽ bỏ qua phần trích xuất Bearer token và giải mã JWT.

| Cách kiểm thử | Cơ chế | Phần được kiểm tra |
|---|---|---|
| **@WithMockUser** | Đưa một user giả lập vào SecurityContext | Quy tắc authorization và method security |
| **jwt()** | Tạo JwtAuthenticationToken giả lập cho request | Quy tắc dựa trên JWT claims/authorities đã được dựng sẵn |
| Header **Authorization: Bearer <token>** | Gửi compact JWT có chữ ký qua HTTP | Bearer extraction, JwtDecoder, chữ ký, validators, ánh xạ authority và authorization |

Ví dụ dùng **jwt()**:

~~~java
mockMvc.perform(get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

Đây là kiểm thử tốt cho quy tắc quyền. Nhưng request post-processor này cung cấp Authentication đã được tạo sẵn; nó không gửi một JWT đã ký qua **BearerTokenAuthenticationFilter** và không gọi **JwtDecoder**. Khi mục tiêu là kiểm tra xác thực token, hãy gửi header thật.

## 2. Cấu hình Resource Server và các điều kiện xác minh

Ví dụ dưới đây dùng Spring Boot 3 và Spring Security 6. Endpoint **/api/orders/** yêu cầu scope **orders.read**. Resource Server xác minh JWT bằng khóa công khai RSA và chỉ chấp nhận token có issuer cùng audience đã định.

Cấu hình chuỗi filter cho Servlet:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
        .build();
}
~~~

Decoder cần xác minh cả chữ ký và các claim quan trọng. **NimbusJwtDecoder.withPublicKey(...)** xác minh chữ ký RSA bằng khóa công khai. **JwtValidators.createDefaultWithIssuer(...)** kết hợp kiểm tra thời gian mặc định, gồm **exp** và **nbf**, với kiểm tra issuer. Audience thường cần validator riêng theo định danh API mà Resource Server bảo vệ.

~~~java
private static final String ISSUER = "https://issuer.test";
private static final String AUDIENCE = "orders-api";

@Bean
JwtDecoder jwtDecoder(RSAPublicKey verificationKey) {
    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withPublicKey(verificationKey).build();

    OAuth2TokenValidator<Jwt> issuerAndTime =
        JwtValidators.createDefaultWithIssuer(ISSUER);

    OAuth2TokenValidator<Jwt> audience = jwt -> {
        if (jwt.getAudience().contains(AUDIENCE)) {
            return OAuth2TokenValidatorResult.success();
        }

        OAuth2Error error = new OAuth2Error(
            "invalid_token", "Token không có audience được yêu cầu", null);
        return OAuth2TokenValidatorResult.failure(error);
    };

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(issuerAndTime, audience));

    return decoder;
}
~~~

Ở đây **https://issuer.test** là giá trị issuer dành riêng cho môi trường test. Khi dùng decoder được cấu hình trực tiếp bằng public key, Spring chỉ so sánh claim **iss** với giá trị mong đợi; nó không cần truy cập địa chỉ này. Điều đó giúp test chạy ổn định, không phụ thuộc DNS, mạng hoặc một IdP đang hoạt động.

Nếu ứng dụng dùng **issuer-uri** để Spring tự khám phá metadata và JWKS, đó là một luồng khác: kiểm thử discovery/JWKS cần một endpoint HTTP cục bộ giả lập metadata và JWKS. Ví dụ trong bài tập trung vào xác minh chữ ký bằng public key đã biết.

## 3. Tạo token ký thật trong test

Test cần giữ khóa riêng để ký token và đưa khóa công khai tương ứng cho decoder. Cặp khóa được sinh trong test context, vì vậy mỗi lần chạy có thể dùng một cặp mới. Không dùng khóa riêng của môi trường thật trong test.

Có thể khai báo cấu hình test như sau. Ví dụ dùng Nimbus JOSE, thư viện được đưa vào qua dependency OAuth2 JOSE của Spring Security.

~~~java
@TestConfiguration(proxyBeanMethods = false)
class JwtTestConfiguration {

    static final String ISSUER = "https://issuer.test";
    static final String AUDIENCE = "orders-api";

    @Bean
    RSAKey testRsaKey() throws JOSEException {
        return new RSAKeyGenerator(2048)
            .keyUse(KeyUse.SIGNATURE)
            .algorithm(JWSAlgorithm.RS256)
            .keyID("test-key")
            .generate();
    }

    @Bean
    JwtEncoder testJwtEncoder(RSAKey key) {
        JWKSource<SecurityContext> jwkSource =
            new ImmutableJWKSet<>(new JWKSet(key));
        return new NimbusJwtEncoder(jwkSource);
    }

    @Bean
    @Primary
    JwtDecoder testJwtDecoder(RSAKey key) throws JOSEException {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withPublicKey(key.toRSAPublicKey()).build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains(AUDIENCE)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token",
                        "Token không có audience được yêu cầu", null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(issuerAndTime, audience));
        return decoder;
    }
}
~~~

**RSAKey** ở đây chứa cả public key và private key. **JwtEncoder** dùng private key để ký token; **JwtDecoder** chỉ nhận public key để xác minh chữ ký. Bean decoder test được đánh dấu **@Primary** để Resource Server chọn decoder test trong context tích hợp. Nếu ứng dụng có cấu hình decoder riêng, hãy đặt cấu hình test trong profile/context test phù hợp để bean được chọn là decoder đang dùng cặp khóa test.

Hàm tạo token có thể nhận issuer, audience, scope và thời điểm phát hành/hết hạn để mỗi test chủ động tạo tình huống cần kiểm tra:

~~~java
private String issueToken(
        JwtEncoder encoder,
        String issuer,
        List<String> audience,
        String scope,
        Instant issuedAt,
        Instant expiresAt) {

    JwtClaimsSet claims = JwtClaimsSet.builder()
        .issuer(issuer)
        .subject("alice")
        .audience(audience)
        .issuedAt(issuedAt)
        .expiresAt(expiresAt)
        .claim("scope", scope)
        .build();

    JwsHeader headers = JwsHeader.with(SignatureAlgorithm.RS256)
        .keyId("test-key")
        .build();

    return encoder.encode(
        JwtEncoderParameters.from(headers, claims)).getTokenValue();
}
~~~

Token trả về là compact JWT đã ký, có dạng ba phần được phân tách bằng dấu chấm. Claim **scope** chứa chuỗi scope phân tách bằng khoảng trắng; converter mặc định của Resource Server ánh xạ **orders.read** thành authority **SCOPE_orders.read**.

Đặt hàm **issueToken** trong test class hoặc một lớp fixture dùng chung; các ví dụ tiếp theo gọi lại hàm này để tạo token theo từng tình huống.

## 4. Gửi Bearer token qua MockMvc

Dùng **@SpringBootTest** cùng **@AutoConfigureMockMvc** để tạo MockMvc có Spring Security filter chain của ứng dụng. Import cấu hình test để encoder ký token và decoder xác minh bằng cùng cặp khóa.

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@Import(JwtTestConfiguration.class)
class RealBearerTokenMvcTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    JwtEncoder jwtEncoder;

    private String validToken() {
        Instant now = Instant.now();
        return issueToken(
            jwtEncoder,
            JwtTestConfiguration.ISSUER,
            List.of(JwtTestConfiguration.AUDIENCE),
            "orders.read",
            now.minusSeconds(5),
            now.plusSeconds(300));
    }

    @Test
    void acceptsSignedBearerToken() throws Exception {
        String token = validToken();

        mockMvc.perform(get("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
            .andExpect(status().isOk());
    }
}
~~~

Trong request trên, test không gọi **.with(jwt())**. Header được gửi qua MockMvc, Spring Security filter chain trích xuất Bearer token, decoder xác minh chữ ký và các claim, rồi authorization mới kiểm tra scope.

Nếu dùng MockMvc được dựng thủ công thay vì **@AutoConfigureMockMvc**, cần gắn Spring Security filter chain vào MockMvc, thường bằng **apply(springSecurity())**. Nếu filter chain không được đăng ký trong MockMvc, test có thể không đi qua các filter mà bài đang muốn kiểm tra.

## 5. Kiểm tra token bị từ chối và quyền bị thiếu

Một test tích hợp nên kiểm tra các trường hợp ở cả bước xác thực và bước phân quyền. Với cấu hình mặc định của Resource Server, token thiếu hoặc không hợp lệ thường dẫn tới **401**; token hợp lệ nhưng không có authority cần thiết dẫn tới **403**.

~~~java
@Test
void rejectsExpiredToken() throws Exception {
    Instant now = Instant.now();
    String token = issueToken(
        jwtEncoder,
        JwtTestConfiguration.ISSUER,
        List.of(JwtTestConfiguration.AUDIENCE),
        "orders.read",
        now.minusSeconds(120),
        now.minusSeconds(60));

    mockMvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isUnauthorized());
}

@Test
void rejectsWrongAudience() throws Exception {
    Instant now = Instant.now();
    String token = issueToken(
        jwtEncoder,
        JwtTestConfiguration.ISSUER,
        List.of("billing-api"),
        "orders.read",
        now.minusSeconds(5),
        now.plusSeconds(300));

    mockMvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isUnauthorized());
}

@Test
void forbidsValidTokenWithoutRequiredScope() throws Exception {
    Instant now = Instant.now();
    String token = issueToken(
        jwtEncoder,
        JwtTestConfiguration.ISSUER,
        List.of(JwtTestConfiguration.AUDIENCE),
        "orders.write",
        now.minusSeconds(5),
        now.plusSeconds(300));

    mockMvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isForbidden());
}
~~~

Có thể bổ sung các ca sau để tăng độ bao phủ:

| Tình huống | Kết quả thường mong đợi | Thành phần được kiểm tra |
|---|---:|---|
| Không gửi Authorization | **401** | Resource Server yêu cầu xác thực |
| Token hết hạn (**exp** trong quá khứ) | **401** | Timestamp validator |
| **iss** không khớp | **401** | Issuer validator |
| **aud** không chứa **orders-api** | **401** | Audience validator |
| Token ký bằng khóa riêng khác | **401** | Xác minh chữ ký bằng public key được tin cậy |
| Token hợp lệ nhưng thiếu **orders.read** | **403** | Authorization theo authority |
| Token hợp lệ, đúng audience và có **orders.read** | **200** | Toàn bộ luồng xác thực và phân quyền |

Để kiểm tra chữ ký sai, tạo một encoder khác dùng cặp RSA khác rồi gửi token do encoder đó ký. Decoder vẫn chỉ có public key của **testRsaKey**, nên phải từ chối token. Không sửa payload của token sau khi ký để tạo ca này: thay đổi payload sẽ làm chữ ký không còn hợp lệ, nhưng dùng khóa khác giúp test thể hiện rõ việc decoder chỉ tin khóa đã cấu hình.

Nếu token bị từ chối, hãy xem cả status và log bảo mật để phân biệt lỗi parse, chữ ký, thời hạn, issuer hay audience. Không nên khẳng định mọi lỗi token đều có cùng thông điệp phản hồi; Resource Server thường trả phản hồi 401 tổng quát và ghi chi tiết ở phía server.

## 6. Gửi cùng token qua WebTestClient

Với ứng dụng WebFlux, cấu hình chuỗi bảo mật dùng **SecurityWebFilterChain** và Resource Server reactive:

~~~java
@Bean
SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
    return http
        .authorizeExchange(authorize -> authorize
            .pathMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyExchange().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
        .build();
}
~~~

Trong test WebFlux, cấu hình test cần cung cấp **ReactiveJwtDecoder** dùng public key từ cùng cặp khóa với **JwtEncoder**. Có thể khai báo decoder trong một test configuration riêng:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class ReactiveJwtTestConfiguration {

    @Bean
    @Primary
    ReactiveJwtDecoder testReactiveJwtDecoder(RSAKey key) throws JOSEException {
        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withPublicKey(key.toRSAPublicKey()).build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(
                JwtTestConfiguration.ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains(JwtTestConfiguration.AUDIENCE)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token",
                        "Token không có audience được yêu cầu", null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(issuerAndTime, audience));
        return decoder;
    }
}
~~~

Import cả **JwtTestConfiguration** (cung cấp RSA key và **JwtEncoder**) cùng **ReactiveJwtTestConfiguration** (cung cấp **ReactiveJwtDecoder**). Sau đó gửi token bằng **setBearerAuth**:

~~~java
@SpringBootTest
@AutoConfigureWebTestClient
@Import({JwtTestConfiguration.class, ReactiveJwtTestConfiguration.class})
class RealBearerTokenWebFluxTest {

    @Autowired
    WebTestClient webTestClient;

    @Autowired
    JwtEncoder jwtEncoder;

    @Test
    void acceptsSignedBearerToken() {
        Instant now = Instant.now();
        String token = issueToken(
            jwtEncoder,
            JwtTestConfiguration.ISSUER,
            List.of(JwtTestConfiguration.AUDIENCE),
            "orders.read",
            now.minusSeconds(5),
            now.plusSeconds(300));

        webTestClient.get()
            .uri("/api/orders")
            .headers(headers -> headers.setBearerAuth(token))
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

**setBearerAuth(token)** tạo header **Authorization: Bearer <token>**. Request đi qua WebFlux security web filters và **ReactiveJwtDecoder**. Các trường hợp token hết hạn, sai issuer/audience, sai chữ ký hoặc thiếu scope có thể được kiểm tra tương tự các test MockMvc.

## 7. Cách chọn loại test phù hợp

Không phải test nào cũng cần ký token. Hãy chọn công cụ theo phần cần chứng minh:

- Dùng **@WithMockUser** khi cần kiểm tra quyền theo role/authority hoặc method security mà không phụ thuộc JWT.
- Dùng **jwt()** khi cần nhanh chóng kiểm tra cách endpoint xử lý một tập claims/authorities đã biết.
- Dùng header Bearer với JWT được ký bằng khóa test khi cần xác minh filter chain, token extraction, decoder, chữ ký và validators.
- Dùng mock JWKS server hoặc issuer server cục bộ khi cần kiểm tra thêm metadata discovery, tải khóa, cache hoặc luân chuyển khóa.

Một test gửi Bearer token thật qua chuỗi filter vẫn là test tích hợp trong tiến trình ứng dụng. Nó chứng minh Resource Server xử lý đúng token theo khóa và validator được cấu hình. Nó không chứng minh IdP bên ngoài đã phát hành token, cũng không kiểm tra kết nối mạng tới IdP nếu test dùng public key được cung cấp trực tiếp.

## 8. Lỗi thường gặp

**Token đúng chữ ký nhưng nhận 401:** kiểm tra **iss**, **aud**, **exp**, **nbf**, thuật toán ký và public key decoder đang sử dụng. Kiểm tra đồng hồ hệ thống nếu test phụ thuộc thời điểm. Đảm bảo issuer trong token trùng chính xác với issuer validator, kể cả scheme và dấu **/** cuối nếu có.

**Token hợp lệ nhưng nhận 403:** xác thực đã thành công nhưng authority không khớp quy tắc. Với claim **scope: "orders.read"**, quy tắc thường cần **SCOPE_orders.read**. Nếu ứng dụng dùng **JwtGrantedAuthoritiesConverter** tùy chỉnh, token test phải phù hợp với cách ánh xạ đó.

**Test luôn trả 200 dù token sai:** xác nhận request đang đi qua đúng Spring Security filter chain và test không gắn **.with(jwt())**, **@WithMockUser** hoặc một cơ chế khác đã dựng sẵn Authentication. Kiểm tra MockMvc có cài security filters hay không.

**Test gọi ra mạng ngoài:** kiểm tra cấu hình có dùng **issuer-uri** hoặc JWKS URI cần discovery hay không. Với bài test chữ ký bằng khóa cố định, cấu hình decoder trực tiếp bằng public key test và validator issuer sẽ không cần gọi IdP.

**Không tìm thấy thuật toán hoặc lớp Nimbus:** xác nhận ứng dụng có dependency Resource Server/OAuth2 JOSE phù hợp với phiên bản Spring Security đang dùng. Với Spring Boot, dependency thường là:

~~~gradle
implementation("org.springframework.boot:spring-boot-starter-oauth2-resource-server")
testImplementation("org.springframework.security:spring-security-test")
~~~

Các API và package có thể thay đổi giữa các dòng Spring Security. Hãy dùng phiên bản do Spring Boot dependency management quản lý và giữ các module Spring Security cùng phiên bản.

## 9. Tự kiểm tra

1. Vì sao **jwt()** không chứng minh **BearerTokenAuthenticationFilter** đã trích xuất và xác minh token?
2. Thành phần nào xác minh chữ ký JWT, và vì sao decoder chỉ cần public key?
3. Vì sao token có issuer hợp lệ nhưng sai audience vẫn phải bị từ chối?
4. Một token có chữ ký, issuer, audience và thời hạn hợp lệ nhưng thiếu **orders.read** sẽ nhận 401 hay 403? Giải thích.
5. Khi nào cần dựng JWKS server cục bộ thay vì cấu hình decoder trực tiếp bằng public key test?

Khi trả lời được các câu hỏi này và có test cho cả token hợp lệ, token không hợp lệ cùng trường hợp thiếu quyền, người học đã kiểm tra được đường đi của một Bearer JWT qua Resource Server từ HTTP request tới quyết định authorization.

