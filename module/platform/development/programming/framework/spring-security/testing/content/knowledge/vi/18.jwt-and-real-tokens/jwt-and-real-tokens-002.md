# Dùng khóa kiểm thử độc lập để ký và kiểm tra token

Khi kiểm thử JWT, test cần có một khóa để tạo chữ ký và một khóa công khai để xác minh chữ ký đó. Cặp khóa này nên thuộc riêng môi trường kiểm thử. Nó không phụ thuộc khóa ký của Identity Provider đang chạy và không sử dụng private key của production.

Cách tổ chức này giúp test chủ động tạo token hợp lệ, token hết hạn, token sai issuer hoặc token được ký bởi một khóa khác. Test cũng kiểm tra được decoder chỉ tin public key đã cấu hình. Các ví dụ dùng RSA và RS256 với Spring Boot 3, Spring Security 6 và Nimbus JOSE.

Sau bài học, người học có thể:

- Tạo cặp khóa RSA dành riêng cho test và phân biệt private key với public key.
- Cấu hình JwtEncoder ký bằng private key test.
- Cấu hình JwtDecoder xác minh bằng public key tương ứng.
- Chứng minh token ký bằng một cặp khóa khác bị từ chối.
- Quản lý key ID, test fixture và phạm vi sử dụng khóa trong test suite.

## 1. Vì sao cần khóa kiểm thử riêng?

Một JWT có chữ ký số gồm header, payload và signature. Khi tạo token, issuer dùng private key để ký. Resource Server dùng public key đáng tin cậy để kiểm tra chữ ký trước khi chấp nhận các claim.

Trong test, ta cần kiểm soát cả hai phía:

- **Signing key:** private key chỉ dùng để tạo token test.
- **Verification key:** public key tương ứng được cấu hình trong decoder đang được kiểm thử.
- **Untrusted key:** một cặp khóa khác, dùng để tạo token mà decoder phải từ chối.

Không lấy private key production, secret của IdP hay khóa đang dùng ở môi trường chia sẻ để chạy test. Nếu test dùng khóa thật, kết quả phụ thuộc cấu hình và vòng đời khóa bên ngoài; đồng thời private key có thể bị lộ qua log, artifact hoặc bản sao workspace.

| Loại khóa | Nơi sử dụng | Vai trò trong test |
|---|---|---|
| Private key test được tin cậy | JwtEncoder của test | Ký JWT hợp lệ |
| Public key test được tin cậy | JwtDecoder của ứng dụng trong test | Xác minh chữ ký |
| Private key test không được tin cậy | Encoder phụ của test | Ký JWT để kiểm tra trường hợp bị từ chối |
| Public key production/IdP | Môi trường triển khai | Không cần cho bài test độc lập này |

Một test tốt không chỉ chứng minh token hợp lệ được chấp nhận. Nó còn phải chứng minh token có claim giống hệt nhưng được ký bởi khóa khác sẽ không vượt qua bước xác minh chữ ký.

## 2. Sinh cặp RSA riêng cho test

Có thể tạo khóa ngay trong test configuration bằng Nimbus JOSE. Spring test context quản lý bean theo singleton, nên encoder và decoder trong cùng context dùng cùng một cặp khóa ổn định trong suốt lượt test đó. Phương thức sinh khóa được đặt trong fixture để mọi encoder và decoder dùng chung đúng một bộ khóa.

Cấu hình tạo hai cặp khóa độc lập:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class IndependentJwtTestConfiguration {

    static final String ISSUER = "https://issuer.test";
    static final String AUDIENCE = "inventory-api";

    record KeyMaterial(RSAKey trusted, RSAKey untrusted) {}

    @Bean
    KeyMaterial testKeyMaterial() throws JOSEException {
        return new KeyMaterial(
            generateSigningKey("trusted-test-key"),
            generateSigningKey("untrusted-test-key"));
    }

    private static RSAKey generateSigningKey(String keyId)
            throws JOSEException {
        return new RSAKeyGenerator(2048)
            .keyUse(KeyUse.SIGNATURE)
            .algorithm(JWSAlgorithm.RS256)
            .keyID(keyId)
            .generate();
    }
}
~~~

**trusted** và **untrusted** là hai cặp RSA khác nhau. Mỗi cặp có private key và public key riêng. Test dùng private key của **trusted** để ký token hợp lệ; decoder chỉ nhận public key của **trusted**. Cặp **untrusted** được giữ lại để tạo token giả mạo trong test âm.

Khóa được sinh khi Spring tạo test context. Điều này có nghĩa token có thể khác nhau giữa các lần chạy, nhưng test vẫn xác định được kết quả vì luôn ký và xác minh bằng cùng một fixture. Không nên viết assertion so sánh toàn bộ chuỗi JWT với một giá trị cố định; hãy kiểm tra status, claims hoặc kết quả decode.

## 3. Tạo JwtEncoder chỉ dùng private key test

**NimbusJwtEncoder** cần một **JWKSource**. Với fixture ở trên, tạo hai encoder riêng: encoder đáng tin cậy dùng private key của **trusted**; encoder còn lại dùng private key của **untrusted**.

~~~java
private static JwtEncoder encoderFor(RSAKey signingKey) {
    JWKSource<SecurityContext> jwkSource =
        new ImmutableJWKSet<>(new JWKSet(signingKey));
    return new NimbusJwtEncoder(jwkSource);
}

@Bean("trustedTestJwtEncoder")
JwtEncoder trustedTestJwtEncoder(KeyMaterial keys) {
    return encoderFor(keys.trusted());
}

@Bean("untrustedTestJwtEncoder")
JwtEncoder untrustedTestJwtEncoder(KeyMaterial keys) {
    return encoderFor(keys.untrusted());
}
~~~

Các phương thức **@Bean** này được đặt bên trong **IndependentJwtTestConfiguration**. **JWKSet** chứa khóa phục vụ ký, bao gồm private key trong test process. Chỉ inject encoder vào test cần phát hành token; không đưa private key hoặc encoder ký test vào cấu hình ứng dụng chạy production.

Khi tạo **JwsHeader**, thuật toán phải khớp với thuật toán của khóa:

~~~java
private static String issueToken(
        JwtEncoder encoder,
        String keyId,
        String scope,
        Instant expiresAt) {

    Instant now = Instant.now();

    JwtClaimsSet claims = JwtClaimsSet.builder()
        .issuer(IndependentJwtTestConfiguration.ISSUER)
        .subject("test-user")
        .audience(List.of(IndependentJwtTestConfiguration.AUDIENCE))
        .issuedAt(now.minusSeconds(5))
        .expiresAt(expiresAt)
        .claim("scope", scope)
        .build();

    JwsHeader headers = JwsHeader.with(SignatureAlgorithm.RS256)
        .keyId(keyId)
        .build();

    return encoder.encode(
        JwtEncoderParameters.from(headers, claims)).getTokenValue();
}
~~~

Tham số **keyId** giúp header token chỉ ra định danh khóa đã ký nó. Ví dụ, token được tạo bằng **trustedTestJwtEncoder** dùng **trusted-test-key**; token từ encoder còn lại dùng **untrusted-test-key**.

Đặt hàm **issueToken** trong test class hoặc một lớp helper của test. Các test ở phần sau gọi lại hàm này để tạo token từ encoder tương ứng.

**kid** không phải bí mật và cũng không tự làm cho token đáng tin. Nó là định danh để hệ thống chọn khóa ứng viên trong một tập khóa đã cấu hình. Chữ ký vẫn phải xác minh thành công bằng khóa công khai thuộc tập khóa được tin cậy.

## 4. Cấu hình JwtDecoder chỉ tin public key tương ứng

Decoder của test nhận public key từ **trusted**. Không truyền private key vào decoder. Ngoài chữ ký, validator cần kiểm tra issuer, thời hạn và audience để test phản ánh điều kiện chấp nhận token của Resource Server.

~~~java
@Bean
@Primary
JwtDecoder testJwtDecoder(KeyMaterial keys) {
    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withPublicKey(
            keys.trusted().toRSAPublicKey()).build();

    OAuth2TokenValidator<Jwt> issuerAndTime =
        JwtValidators.createDefaultWithIssuer(ISSUER);

    OAuth2TokenValidator<Jwt> audience = jwt ->
        jwt.getAudience().contains(AUDIENCE)
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Token không dành cho inventory-api",
                    null));

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(issuerAndTime, audience));

    return decoder;
}
~~~

**NimbusJwtDecoder.withPublicKey(...)** thiết lập khóa xác minh chữ ký. **JwtValidators.createDefaultWithIssuer(...)** kiểm tra issuer và các điều kiện thời gian mặc định như **exp** và **nbf**. Validator audience đảm bảo token được phát hành cho đúng API.

**@Primary** giúp Resource Server chọn decoder test khi context có nhiều bean cùng kiểu. Nếu ứng dụng đã khai báo decoder riêng hoặc có nhiều cấu hình bảo mật, hãy bảo đảm filter chain đang kiểm thử thực sự nhận bean test này. Có thể dùng **@Import(IndependentJwtTestConfiguration.class)** trong test context và kiểm tra cấu hình bean theo cách ứng dụng đang xây dựng Resource Server.

Không dùng **@Primary** như một biện pháp thay thế cho việc hiểu cấu hình. Nếu ứng dụng tạo **JwtDecoder** trực tiếp trong DSL hoặc dùng một bean có qualifier riêng, cần điều chỉnh test configuration để thay đúng decoder mà chuỗi filter đang sử dụng.

## 5. Chứng minh token đúng khóa được chấp nhận

Test tích hợp có thể import cấu hình khóa test và gửi token qua header Bearer. Ví dụ dùng MockMvc:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@Import(IndependentJwtTestConfiguration.class)
class IndependentSigningKeyMvcTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    @Qualifier("trustedTestJwtEncoder")
    JwtEncoder trustedEncoder;

    @Autowired
    @Qualifier("untrustedTestJwtEncoder")
    JwtEncoder untrustedEncoder;

    private String trustedToken() {
        return issueToken(
            trustedEncoder,
            "trusted-test-key",
            "inventory.read",
            Instant.now().plusSeconds(300));
    }

    private String untrustedToken() {
        return issueToken(
            untrustedEncoder,
            "untrusted-test-key",
            "inventory.read",
            Instant.now().plusSeconds(300));
    }

    @Test
    void acceptsTokenSignedByTrustedTestKey() throws Exception {
        mockMvc.perform(get("/api/inventory")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    "Bearer " + trustedToken()))
            .andExpect(status().isOk());
    }
}
~~~

Request gửi một compact JWT qua HTTP. Resource Server lấy token từ Bearer header, gọi decoder, xác minh chữ ký bằng public key **trusted**, kiểm tra các claim rồi mới áp dụng quy tắc authorization. Test này kiểm tra cấu hình xác thực đang gắn với filter chain của ứng dụng.

Endpoint trong ví dụ cần được cấu hình để yêu cầu scope **inventory.read**, ví dụ:

~~~java
.requestMatchers("/api/inventory/**")
    .hasAuthority("SCOPE_inventory.read")
~~~

Claim **scope** chứa **inventory.read**; converter mặc định của Resource Server ánh xạ nó thành authority **SCOPE_inventory.read**.

Các ví dụ dùng **MockMvc**, **JwtEncoder**, **JwtDecoder** và các lớp Nimbus. Hãy bảo đảm project có Spring Boot OAuth2 Resource Server starter để có các API JOSE/Resource Server cần thiết, cùng **spring-security-test** cho các tiện ích kiểm thử Spring Security.

## 6. Chứng minh token từ khóa khác bị từ chối

Token tiếp theo có issuer, subject, audience, thời hạn và scope giống token hợp lệ. Khác biệt nằm ở private key đã ký token. Decoder chỉ có public key **trusted**, vì vậy chữ ký từ **untrusted** không thể được xác minh.

~~~java
@Test
void rejectsTokenSignedByUntrustedTestKey() throws Exception {
    mockMvc.perform(get("/api/inventory")
            .header(
                HttpHeaders.AUTHORIZATION,
                "Bearer " + untrustedToken()))
        .andExpect(status().isUnauthorized());
}
~~~

Kết quả **401 Unauthorized** cho thấy request bị từ chối ở bước xác thực token. Đây là test quan trọng để tránh một cấu hình decoder vô tình tin nhầm khóa hoặc bỏ qua việc xác minh chữ ký.

Có thể bổ sung test decode trực tiếp để kiểm tra lớp decoder độc lập với HTTP:

~~~java
@Autowired
JwtDecoder jwtDecoder;

@Test
void decoderAcceptsTrustedSignature() {
    Jwt decoded = jwtDecoder.decode(trustedToken());

    assertThat(decoded.getSubject()).isEqualTo("test-user");
    assertThat(decoded.getAudience())
        .contains(IndependentJwtTestConfiguration.AUDIENCE);
}

@Test
void decoderRejectsSignatureFromAnotherKey() {
    assertThatThrownBy(() -> jwtDecoder.decode(untrustedToken()))
        .isInstanceOf(JwtException.class);
}
~~~

Test decode trực tiếp giúp khoanh vùng lỗi ở bước xác minh token. Test MockMvc xác nhận cùng cấu hình decoder hoạt động qua HTTP filter chain. Hai cấp test trả lời hai câu hỏi khác nhau và có thể cùng tồn tại trong một test suite.

## 7. Ma trận kiểm thử khóa và claim

Giữ nguyên public key đáng tin cậy trong decoder, sau đó thay đổi từng yếu tố của token để biết điều kiện nào đang được kiểm tra.

| Token test | Chữ ký | Claim | Kết quả xác thực mong đợi |
|---|---|---|---|
| Ký bằng private key **trusted** | Hợp lệ | Đúng issuer, audience, thời hạn | Thành công |
| Ký bằng private key **untrusted** | Không xác minh được bằng public key đã tin | Các claim còn lại hợp lệ | **401** |
| Ký bằng **trusted** | Hợp lệ | Sai issuer | **401** |
| Ký bằng **trusted** | Hợp lệ | Sai audience | **401** |
| Ký bằng **trusted** | Hợp lệ | Token hết hạn | **401** |
| Ký bằng **trusted** | Hợp lệ | Thiếu scope yêu cầu | **403** |

Bảng này tách xác thực khỏi phân quyền. Sai chữ ký hoặc claim xác thực làm decoder từ chối token và Resource Server thường trả **401**. Token hợp lệ nhưng không có authority phù hợp sẽ qua bước xác thực rồi bị từ chối ở bước authorization với **403**.

Khi test sai issuer hoặc audience, vẫn dùng encoder của khóa **trusted**; chỉ thay claim cần kiểm tra. Như vậy test không vô tình thất bại vì chữ ký sai trước khi tới validator tương ứng.

## 8. Dùng cùng fixture với WebTestClient

Cặp khóa test không phụ thuộc Servlet API. Với WebFlux, có thể cấu hình **NimbusReactiveJwtDecoder** bằng public key **trusted**, dùng cùng **JwtEncoder** để phát hành token, rồi gửi qua **setBearerAuth**.

~~~java
@Bean
@Primary
ReactiveJwtDecoder testReactiveJwtDecoder(KeyMaterial keys) {
    NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder.withPublicKey(
            keys.trusted().toRSAPublicKey()).build();

    OAuth2TokenValidator<Jwt> issuerAndTime =
        JwtValidators.createDefaultWithIssuer(ISSUER);

    OAuth2TokenValidator<Jwt> audience = jwt ->
        jwt.getAudience().contains(AUDIENCE)
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token"));

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(issuerAndTime, audience));

    return decoder;
}
~~~

Test gửi token:

~~~java
webTestClient.get()
    .uri("/api/inventory")
    .headers(headers -> headers.setBearerAuth(trustedToken()))
    .exchange()
    .expectStatus().isOk();
~~~

Để test trường hợp khóa không được tin cậy, thay token bằng kết quả từ **untrustedToken()** và kỳ vọng **401**. Cần import cùng **KeyMaterial** và các encoder test vào WebFlux test context; chỉ khác decoder được Resource Server reactive sử dụng.

## 9. Khi nào nên dùng khóa sinh động, khi nào dùng fixture cố định?

Sinh khóa bằng **RSAKeyGenerator** trong test context là lựa chọn phù hợp khi test chỉ cần kiểm tra hành vi ký và xác minh. Test không cần giữ một chuỗi JWT giống nhau giữa các lần chạy; private key cũng không phải lưu trong repository.

Một số hệ thống cần test tương thích giữa nhiều tiến trình hoặc cần kiểm tra luân chuyển khóa theo **kid**. Khi đó có thể lưu một cặp PEM dành riêng cho test trong **src/test/resources**, với các nguyên tắc:

- Private key chỉ được dùng trong test, có thể công khai cùng mã nguồn test nếu không được dùng ở môi trường thật.
- Public key tương ứng được nạp vào decoder hoặc JWKS test server.
- Không chép private key production, khóa staging hoặc secret của IdP vào test resources.
- Có thể có thêm cặp khóa thứ hai để kiểm tra token ký bằng khóa không được tin cậy.
- Nếu test kiểm tra JWKS rotation, cần kiểm tra cả việc chọn khóa theo **kid** và việc xác minh chữ ký bằng public key tương ứng.

Khóa cố định làm cho fixture có thể chia sẻ giữa nhiều tiến trình, nhưng cần quản lý cẩn thận để không bị nhầm với khóa vận hành. Khóa sinh động đơn giản hơn và thường đủ cho test trong một Spring context.

## 10. Lỗi thường gặp

**Encoder và decoder dùng hai cặp khóa khác nhau:** token được ký thành công nhưng decoder không thể xác minh chữ ký. Kiểm tra fixture có cấp đúng **trusted** cho encoder và decoder hay không.

**Decoder vô tình nhận private key:** decoder chỉ cần public key. Dùng **toRSAPublicKey()** khi cấu hình decoder để ranh giới giữa ký và xác minh rõ ràng.

**Test token sai khóa vẫn trả 200:** kiểm tra request có đi qua filter chain thật không; bảo đảm không gắn **jwt()**, **@WithMockUser** hoặc Authentication dựng sẵn. Kiểm tra decoder mà Resource Server thực sự sử dụng.

**Hai encoder dùng chung một key:** khi đó test không còn chứng minh được việc từ chối khóa khác. Sinh hai cặp RSA độc lập và đặt **kid** riêng để dễ đọc log.

**Token bị 401 dù ký đúng:** kiểm tra **iss**, **aud**, **exp**, **nbf**, thuật toán trong header và validator đang được gắn vào decoder. Đảm bảo thời gian test không làm token hết hạn trước khi request được gửi.

**Nhầm kid với xác thực:** **kid** chỉ giúp tìm khóa ứng viên. Token chỉ hợp lệ khi chữ ký được xác minh bằng public key nằm trong tập khóa mà Resource Server tin cậy.

## 11. Tự kiểm tra

1. Vì sao private key dùng để ký token test phải độc lập với private key của production?
2. Decoder cần public key hay private key để xác minh chữ ký RSA?
3. Vì sao token có claim hoàn toàn giống nhau nhưng được ký bởi khóa **untrusted** vẫn phải bị từ chối?
4. **kid** có đủ để chứng minh token đáng tin hay không? Giải thích.
5. Khi nào nên sinh khóa động trong test context và khi nào cần fixture PEM cố định?
6. Nếu test trả **403**, điều đó khác gì với trường hợp decoder từ chối chữ ký và trả **401**?

Khi test tạo được token bằng private key riêng, xác minh bằng public key tương ứng và từ chối token từ một cặp khóa khác, người học đã kiểm tra được ranh giới tin cậy của chữ ký JWT trong môi trường Spring Security Testing.

