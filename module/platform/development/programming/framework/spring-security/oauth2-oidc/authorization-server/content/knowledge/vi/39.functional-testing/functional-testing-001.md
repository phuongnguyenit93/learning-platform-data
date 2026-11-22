# Chuẩn bị test profile, client fixture và khóa ký dành cho kiểm thử

Trong Spring Authorization Server, một bài kiểm thử chức năng cần chạy qua cấu hình bảo mật và các endpoint OAuth 2.0 thực tế. Bộ kiểm thử phải có client đã đăng ký, dữ liệu cấp quyền và khóa ký có thể kiểm soát. Nếu dùng chung cấu hình production, test có nguy cơ phụ thuộc vào cơ sở dữ liệu thật, client thật hoặc private key đang được vận hành.

Bài này thuộc module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, nơi ta thiết kế và vận hành Authorization Server từ quản lý client, consent, cấp token, PKCE và refresh token đến bảo vệ endpoint, ký khóa và kiểm thử luồng bảo mật. Trong chương **Kiểm thử chức năng**, mục tiêu là dựng một môi trường kiểm thử riêng, tạo client fixture có hành vi rõ ràng và cấp khóa ký chỉ tồn tại trong test context.

## 1. Xác định ranh giới của test profile

Test profile thay đổi các phụ thuộc môi trường, chẳng hạn issuer kiểm thử, cổng HTTP, logging và nơi lưu dữ liệu. Nó vẫn phải giữ nguyên những hành vi bảo mật mà bài test cần xác minh:

- Security filter chain và endpoint matcher của Authorization Server vẫn được khởi tạo.
- Client authentication vẫn kiểm tra đúng phương thức xác thực và client secret.
- Authorization Code vẫn kiểm tra redirect URI, state và PKCE khi client yêu cầu.
- Consent vẫn được lưu và đọc qua service được cấu hình cho test.
- Token vẫn được ký bằng private key và có thể xác minh bằng public key tương ứng.

Không tắt toàn bộ Spring Security để làm test dễ chạy. Làm như vậy sẽ bỏ qua chính các filter, authentication provider và endpoint mà kiểm thử chức năng cần xác minh. Hãy dùng **@SpringBootTest** cùng **MockMvc** hoặc một HTTP server ngẫu nhiên để request đi qua filter chain thật.

Tạo **application-test.yml** trong thư mục cấu hình của ứng dụng:

~~~yaml
spring:
  application:
    name: authorization-server-test

server:
  port: 0

app:
  authorization-server:
    issuer: https://authorization-server.test

logging:
  level:
    org.springframework.security: INFO
    org.springframework.security.oauth2.server.authorization: DEBUG
~~~

**server.port: 0** yêu cầu hệ điều hành cấp cổng trống khi chạy test với web environment. Nếu dùng **MockMvc**, request được xử lý trong test context và không cần mở cổng thật. Thuộc tính **app.authorization-server.issuer** là thuộc tính ví dụ của ứng dụng; cấu hình **AuthorizationServerSettings** cần đọc thuộc tính này để issuer trong metadata và token nhất quán. Domain **.test** dành cho kiểm thử, không trỏ đến Authorization Server production.

Kích hoạt profile ngay trên test class:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(AuthorizationServerTestFixtures.class)
class TokenEndpointFunctionalTest {
    // Các bài test gửi request qua MockMvc
}
~~~

Không đặt **spring.profiles.active: test** trong **application-test.yml**; profile phải được chọn rõ từ lệnh chạy hoặc test class. Nhờ vậy, khi chạy ứng dụng bình thường, cấu hình test không tự kích hoạt.

Nếu ứng dụng dùng JDBC để lưu **RegisteredClient**, authorization hoặc consent, hãy cấu hình datasource riêng cho profile test, thường là H2 trong bộ test. Khởi tạo schema bằng script tương thích với đúng phiên bản Spring Authorization Server đang dùng. Không dựa vào **spring.jpa.hibernate.ddl-auto** để tự tạo các bảng JDBC của Authorization Server. Khi kiểm thử khả năng lưu trữ qua khởi động lại, hãy dùng các JDBC service thật trong test profile thay cho service in-memory.

## 2. Tạo client fixture cho từng luồng

Một fixture tốt biểu diễn một client có mục đích cụ thể. Không nên dùng một client với tất cả grant type và scope, vì test khó xác định điều kiện nào thực sự được kiểm tra.

| Fixture | Phương thức xác thực | Grant type | Điều kiện cần kiểm thử |
|---|---|---|---|
| **test-machine-client** | **client_secret_basic** | **client_credentials** | Client secret, scope và token endpoint |
| **test-browser-client** | **none** | **authorization_code**, **refresh_token** | Public client, redirect URI chính xác, PKCE và consent |

Client máy chủ là confidential client: nó giữ secret ở phía server và xác thực bằng HTTP Basic. Client trình duyệt là public client: nó không có khả năng giữ bí mật lâu dài, vì vậy fixture không gán client secret và bắt buộc Proof Key for Code Exchange (PKCE). Mỗi fixture chỉ nhận các scope cần cho bài test.

Có thể khai báo các bean test bằng **@TestConfiguration**. Ví dụ sau dùng repository và authorization service in-memory để kiểm thử luồng HTTP mà không cần database:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class AuthorizationServerTestFixtures {

    @Bean
    @Primary
    PasswordEncoder testPasswordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    @Primary
    RegisteredClientRepository testRegisteredClientRepository(
            PasswordEncoder passwordEncoder) {

        TokenSettings shortLivedTokens = TokenSettings.builder()
                .accessTokenTimeToLive(Duration.ofMinutes(5))
                .refreshTokenTimeToLive(Duration.ofMinutes(30))
                .reuseRefreshTokens(false)
                .build();

        RegisteredClient machineClient = RegisteredClient
                .withId("test-machine-client-id")
                .clientId("test-machine-client")
                .clientSecret(passwordEncoder.encode("test-secret"))
                .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
                .scope("message.read")
                .tokenSettings(shortLivedTokens)
                .build();

        RegisteredClient browserClient = RegisteredClient
                .withId("test-browser-client-id")
                .clientId("test-browser-client")
                .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
                .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
                .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
                .redirectUri("http://127.0.0.1:8080/authorized")
                .scope(OidcScopes.OPENID)
                .scope(OidcScopes.PROFILE)
                .clientSettings(ClientSettings.builder()
                        .requireProofKey(true)
                        .requireAuthorizationConsent(true)
                        .build())
                .tokenSettings(shortLivedTokens)
                .build();

        return new InMemoryRegisteredClientRepository(machineClient, browserClient);
    }

    @Bean
    @Primary
    OAuth2AuthorizationService testAuthorizationService() {
        return new InMemoryOAuth2AuthorizationService();
    }

    @Bean
    @Primary
    OAuth2AuthorizationConsentService testAuthorizationConsentService() {
        return new InMemoryOAuth2AuthorizationConsentService();
    }

    @Bean
    RSAKey testSigningRsaKey() throws JOSEException {
        return new RSAKeyGenerator(2048)
                .keyID(UUID.randomUUID().toString())
                .generate();
    }

    @Bean
    @Primary
    JWKSource<SecurityContext> testJwkSource(RSAKey testSigningRsaKey) {
        return new ImmutableJWKSet<>(new JWKSet(testSigningRsaKey));
    }

    @Bean
    @Primary
    AuthorizationServerSettings testAuthorizationServerSettings(
            @Value("${app.authorization-server.issuer}") String issuer) {
        return AuthorizationServerSettings.builder()
                .issuer(issuer)
                .build();
    }
}
~~~

Các import chính của lớp fixture thuộc những package **org.springframework.security.oauth2.server.authorization**, **org.springframework.security.oauth2.server.authorization.client**, **org.springframework.security.oauth2.server.authorization.settings**, **org.springframework.security.crypto** và **com.nimbusds.jose**. Những kiểu Nimbus gồm **RSAKey**, **RSAKeyGenerator**, **JWKSet**, **JWKSource**, **ImmutableJWKSet** và **SecurityContext**.

Secret fixture được mã hóa bằng cùng **PasswordEncoder** mà client authentication sử dụng. Khi xác thực, Authorization Server so sánh secret gửi lên với giá trị đã mã hóa trong **RegisteredClient**. Không lưu secret production trong test source, file cấu hình hoặc biến môi trường dùng chung.

**test-browser-client** dùng **ClientAuthenticationMethod.NONE**, không có client secret và bật **requireProofKey(true)**. Khi gửi authorization request, test phải tạo **code_challenge** từ một **code_verifier** ngẫu nhiên và dùng **code_challenge_method=S256**. Khi đổi authorization code lấy token, client gửi lại đúng **code_verifier**. Test nên xác minh cả trường hợp thiếu challenge, verifier sai và verifier đúng. Redirect URI trong request phải khớp chính xác với URI fixture đã đăng ký.

Nếu test OIDC discovery hoặc UserInfo, cấu hình Authorization Server phải bật OIDC endpoint bằng **authorizationServerConfigurer.oidc(Customizer.withDefaults())** theo cấu hình ứng dụng. Chỉ đăng ký scope **openid** trong fixture không tự bật các endpoint OIDC.

Các bean **@Primary** trong ví dụ giúp test context ưu tiên fixture khi ứng dụng cũng khai báo bean cùng kiểu. Trong dự án thực tế, nên đặt cấu hình repository production dưới profile phù hợp, ví dụ **@Profile("!test")**, để datasource hoặc adapter production không bị khởi tạo ngoài ý muốn. Với bài test persistence, thay các service in-memory bằng JDBC implementation và datasource test thay vì giữ nguyên fixture này.

## 3. Cấp khóa ký chỉ dành cho test

Access token dạng JWT phải được ký bằng private key. Bộ test cần public key tương ứng để xác minh chữ ký và cần kiểm tra endpoint JWKS công bố đúng public key. Fixture ở trên tạo RSA key 2048 bit khi Spring test context khởi tạo, sau đó đưa key vào **ImmutableJWKSet** để Spring Authorization Server sử dụng.

Private key chỉ tồn tại trong bộ nhớ của test context. Khi endpoint JWKS trả về khóa, Spring Authorization Server công bố phần public của JWK; private parameters không được gửi cho client. Không sao chép private key production vào **src/test/resources**, không dùng chung key giữa test và production, và không commit private key thật vào repository.

**kid** được tạo riêng cho key trong mỗi context. Bài test nên đọc **kid** từ header JWT hoặc phản hồi JWKS thay vì giả định một giá trị cố định. Cách này giúp test vẫn đúng khi key được tạo lại giữa các lần chạy.

Khóa ngẫu nhiên phù hợp với test cấp token và xác minh chữ ký trong cùng một context. Nó không phù hợp cho test khởi động lại ứng dụng rồi xác minh token cũ, vì lần khởi động mới sẽ sinh key pair khác. Với bài test persistence hoặc rotation qua nhiều lần khởi động, hãy cấp bộ key test cố định riêng, được quản lý như fixture test và tuyệt đối không dùng ở môi trường thật. Khi kiểm thử rotation, giữ public key cũ trong JWKS trong thời gian token cũ còn hiệu lực và xác minh token mới được ký bằng key đang hoạt động.

## 4. Kiểm thử token endpoint qua HTTP

Ví dụ sau xác minh confidential client có thể dùng client credentials để nhận access token. Request đi qua **MockMvc**, do đó kiểm tra được filter chain, client authentication provider, grant handler và token generator cùng hoạt động:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(AuthorizationServerTestFixtures.class)
class TokenEndpointFunctionalTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Autowired
    RSAKey testSigningRsaKey;

    @Test
    void issuesSignedAccessTokenForClientCredentialsClient() throws Exception {
        MvcResult result = mockMvc.perform(post("/oauth2/token")
                        .with(httpBasic("test-machine-client", "test-secret"))
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("grant_type", "client_credentials")
                        .param("scope", "message.read"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.token_type").value("Bearer"))
                .andReturn();

        JsonNode response = objectMapper.readTree(
                result.getResponse().getContentAsString());
        String accessToken = response.path("access_token").asText();

        assertThat(accessToken).isNotBlank();

        JwtDecoder decoder = NimbusJwtDecoder
                .withPublicKey(testSigningRsaKey.toRSAPublicKey())
                .build();
        Jwt jwt = decoder.decode(accessToken);

        assertThat(jwt.getClaimAsString("iss"))
                .isEqualTo("https://authorization-server.test");
        assertThat(jwt.getClaimAsStringList("scope"))
                .contains("message.read");
    }
}
~~~

Các import của test class gồm **MockMvc**, **MockMvcRequestBuilders.post**, **SecurityMockMvcRequestPostProcessors.httpBasic**, **MockMvcResultMatchers**, **MediaType**, **MvcResult**, **ObjectMapper**, **JsonNode**, **JwtDecoder**, **NimbusJwtDecoder**, **Jwt** và các assertion của AssertJ. Endpoint mặc định trong ví dụ là **/oauth2/token**; nếu ứng dụng thay đổi endpoint trong **AuthorizationServerSettings**, cập nhật đường dẫn test theo cấu hình đó.

Test không chỉ kiểm tra HTTP 200 và sự hiện diện của access token. Nó còn xác minh JWT bằng public key của fixture, sau đó kiểm tra issuer và scope. Như vậy, một lỗi cấu hình signing key hoặc issuer cũng làm bài test thất bại. Nếu ứng dụng phát hành opaque access token thay vì JWT, hãy kiểm tra response và introspection theo đúng token format đã cấu hình; không dùng **JwtDecoder** cho opaque token.

## 5. Lập ma trận kiểm thử cho fixture

Sau khi dựng profile và fixture, hãy triển khai các trường hợp theo từng luồng:

| Luồng | Trường hợp thành công | Trường hợp cần bị từ chối |
|---|---|---|
| Client credentials | Secret hợp lệ, grant và scope đã đăng ký | Secret sai, client không tồn tại, grant hoặc scope không được cấp |
| Authorization Code | Redirect URI khớp, state hợp lệ, PKCE S256 đúng | Redirect URI sai, thiếu code challenge, verifier sai hoặc authorization code đã dùng |
| Consent | Người dùng chấp thuận scope được yêu cầu | Người dùng từ chối hoặc client yêu cầu scope ngoài phạm vi được cấp |
| Refresh token | Refresh token hợp lệ được đổi theo chính sách client | Token hết hạn, bị thu hồi hoặc đã bị thay thế theo chính sách rotation |
| Signing và JWKS | JWT xác minh được bằng public key được công bố | Chữ ký sai, key không còn được tin cậy hoặc issuer không khớp |

Đối với client public, kiểm tra riêng **code_challenge_method=S256**; không dùng **plain** làm mặc định cho fixture. Đối với refresh token rotation, lưu ý rằng khi **reuseRefreshTokens(false)** được bật, refresh token cũ phải bị thay thế sau lần đổi thành công. Bài test cần xác minh hành vi của token cũ theo đúng chính sách của ứng dụng.

Các service in-memory giữ dữ liệu trong vòng đời của Spring context. Vì vậy, authorization hoặc consent tạo ở test trước có thể còn tồn tại khi test sau dùng lại context. Dùng fixture có định danh riêng, dọn dữ liệu rõ ràng với adapter có hỗ trợ, hoặc tạo context riêng khi thật sự cần trạng thái sạch. Không mặc định rằng **@Transactional** sẽ rollback dữ liệu được ghi bởi mọi service hoặc request HTTP.

## 6. Kiểm tra cấu hình trước khi chạy bộ test

Trước khi chạy toàn bộ test suite, kiểm tra các điểm sau:

- Profile **test** được kích hoạt rõ ràng và không tải secret hoặc datasource production.
- Security filter chain của Authorization Server vẫn được nạp trong test context.
- Mỗi client fixture có đúng client authentication method, grant type, redirect URI và scope.
- Public client bật PKCE; test dùng S256 và xác minh cả verifier hợp lệ lẫn không hợp lệ.
- Client secret fixture được mã hóa bằng password encoder mà client authentication provider sử dụng.
- JWKSource của test chỉ chứa khóa test; JWKS không công bố private parameters.
- Issuer trong **AuthorizationServerSettings**, discovery metadata và JWT nhất quán.
- Test persistence dùng database test cùng schema phù hợp với phiên bản Spring Authorization Server.

Khi các điều kiện này được giữ ổn định, test profile có thể chạy lặp lại mà không tác động đến client, dữ liệu cấp quyền hoặc khóa ký của môi trường đang vận hành. Bộ fixture cũng trở thành nền tảng để các bài tiếp theo kiểm tra authorization flow, PKCE, consent, refresh token, thu hồi token và key rotation.
