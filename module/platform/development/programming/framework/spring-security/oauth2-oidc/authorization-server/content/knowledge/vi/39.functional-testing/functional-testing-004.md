# Kiểm thử Client Credentials, Refresh Token và token rotation

Trong Spring Authorization Server, Client Credentials và Refresh Token là hai luồng có mục đích khác nhau. Client Credentials cấp access token cho chính ứng dụng máy chủ đang xác thực; Refresh Token cho phép một client tiếp tục phiên ủy quyền đã được người dùng cấp mà không yêu cầu người dùng đăng nhập và chấp thuận lại ở mỗi lần cấp access token. Bộ kiểm thử chức năng cần phân biệt rõ hai luồng này, xác minh client binding, thời hạn token và hành vi sau khi refresh token được xoay vòng.

Bài này thuộc module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**. Module hướng dẫn thiết kế và vận hành Authorization Server với quản lý client, consent, cấp token, PKCE, refresh token, bảo vệ endpoint, ký khóa và lưu trữ dữ liệu cấp quyền. Trong chương **Kiểm thử chức năng**, ta tập trung kiểm tra hai grant type ở token endpoint, bao gồm cả các trường hợp token không hợp lệ, hết hạn và bị sử dụng lại.

## 1. Phân biệt hai vòng đời token

Với **Client Credentials**, client confidential xác thực bằng thông tin của chính nó, thường qua HTTP Basic với client secret. Authorization Server kiểm tra client, grant type và scope rồi cấp access token. Không có người dùng cuối tham gia vào grant này. Theo OAuth 2.0, authorization server không nên phát hành refresh token cho Client Credentials. Khi access token hết hạn, ứng dụng máy chủ gửi lại yêu cầu Client Credentials bằng thông tin xác thực của client để nhận access token mới.

Với **Refresh Token**, client đã hoàn tất một luồng ủy quyền có người dùng, thường là Authorization Code. Authorization Server đã lưu authorization cùng refresh token được gắn với client và các scope được chấp thuận. Khi access token hết hạn, client gửi refresh token đến token endpoint để nhận access token mới. Nếu client được cấu hình xoay vòng, server đồng thời cấp refresh token mới và làm token cũ mất hiệu lực.

| Nội dung | Client Credentials | Refresh Token |
|---|---|---|
| Mục đích | Xác thực ứng dụng máy chủ | Tiếp tục authorization đã được cấp |
| Danh tính được đại diện | Client | Người dùng cùng client |
| Grant type tại token endpoint | **client_credentials** | **refresh_token** |
| Refresh token | OAuth 2.0 khuyến nghị không phát hành cho grant này | Là credential đầu vào của grant |
| Cách lấy access token mới | Gửi lại Client Credentials | Đổi refresh token hợp lệ |
| Điều kiện quan trọng | Client authentication, grant và scope | Client binding, token còn hạn, authorization còn hiệu lực và scope hợp lệ |

Không thêm grant type **refresh_token** vào client chỉ dùng Client Credentials với kỳ vọng nó sẽ nhận được refresh token từ grant đó. Một client có thể được đăng ký nhiều grant type, nhưng test phải xác định rõ request đang kiểm tra luồng nào.

## 2. Cấu hình token lifetime và rotation cho test

Nên đặt thời hạn token ngắn trong test profile để kiểm tra các mốc hết hạn nhanh và dễ lặp lại. Ví dụ sau tạo access token có thời hạn hai phút và refresh token có thời hạn ba mươi phút. Thuộc tính **reuseRefreshTokens(false)** yêu cầu Spring Authorization Server phát hành refresh token mới khi xử lý refresh grant:

~~~java
TokenSettings testTokenSettings = TokenSettings.builder()
        .accessTokenTimeToLive(Duration.ofMinutes(2))
        .refreshTokenTimeToLive(Duration.ofMinutes(30))
        .reuseRefreshTokens(false)
        .build();
~~~

**reuseRefreshTokens(false)** là thiết lập cho hành vi rotation. Khi refresh thành công, response cần chứa refresh token mới. Client phải thay token cũ bằng token mới một cách an toàn. Nếu cấu hình **reuseRefreshTokens(true)**, server có thể tiếp tục sử dụng refresh token hiện tại; khi đó test không được kỳ vọng giá trị refresh token sẽ thay đổi.

Tạo hai client fixture riêng. Client thứ nhất chỉ được cấp Client Credentials. Client thứ hai dùng Authorization Code và Refresh Token để kiểm thử vòng đời ủy quyền của người dùng:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class TokenGrantTestFixtures {

    @Bean
    @Primary
    PasswordEncoder testPasswordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    @Primary
    RegisteredClientRepository testRegisteredClientRepository(
            PasswordEncoder passwordEncoder) {

        TokenSettings tokenSettings = TokenSettings.builder()
                .accessTokenTimeToLive(Duration.ofMinutes(2))
                .refreshTokenTimeToLive(Duration.ofMinutes(30))
                .reuseRefreshTokens(false)
                .build();

        RegisteredClient serviceClient = RegisteredClient.withId("service-client-id")
                .clientId("test-service-client")
                .clientSecret(passwordEncoder.encode("service-secret"))
                .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
                .scope("inventory.read")
                .tokenSettings(tokenSettings)
                .build();

        RegisteredClient userClient = RegisteredClient.withId("user-client-id")
                .clientId("test-user-client")
                .clientSecret(passwordEncoder.encode("user-secret"))
                .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
                .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
                .redirectUri("http://127.0.0.1:8080/callback")
                .scope("profile")
                .clientSettings(ClientSettings.builder()
                        .requireProofKey(true)
                        .requireAuthorizationConsent(true)
                        .build())
                .tokenSettings(tokenSettings)
                .build();

        return new InMemoryRegisteredClientRepository(serviceClient, userClient);
    }

    @Bean
    @Primary
    OAuth2AuthorizationService testAuthorizationService() {
        return new InMemoryOAuth2AuthorizationService();
    }
}
~~~

Các kiểu được sử dụng trong fixture thuộc những package **org.springframework.security.oauth2.server.authorization**, **org.springframework.security.oauth2.server.authorization.client**, **org.springframework.security.oauth2.server.authorization.settings**, **org.springframework.security.oauth2.core** và **org.springframework.security.crypto**. Cấu hình ứng dụng cần có **JWKSource** chứa khóa test nếu access token được phát hành dưới dạng JWT.

Client secret được mã hóa bằng **PasswordEncoder** mà client authentication sử dụng. Không ghi secret production vào test fixture. Trong dự án thực tế, hãy bảo đảm repository production không được khởi tạo cùng repository in-memory trong test context; có thể dùng profile hoặc điều kiện cấu hình phù hợp. Với test persistence, thay **InMemoryRegisteredClientRepository** và **InMemoryOAuth2AuthorizationService** bằng JDBC implementation cùng datasource riêng cho test.

Kích hoạt fixture trên test class:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(TokenGrantTestFixtures.class)
class TokenGrantFunctionalTest {
    // Các test gửi HTTP request đến token endpoint.
}
~~~

Giữ nguyên filter chain của Authorization Server trong test context. Nếu tắt bảo mật hoặc gọi thẳng token generator, bài test sẽ bỏ qua client authentication và xử lý grant tại token endpoint.

## 3. Kiểm thử Client Credentials

Một request Client Credentials dùng client authentication và khai báo grant type cùng scope. Ví dụ sau kiểm tra response thành công, access token được cấp và response không chứa refresh token:

~~~java
@Autowired
MockMvc mockMvc;

@Test
void issuesAccessTokenForClientCredentials() throws Exception {
    mockMvc.perform(post("/oauth2/token")
                    .with(httpBasic("test-service-client", "service-secret"))
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("grant_type", "client_credentials")
                    .param("scope", "inventory.read"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.token_type").value("Bearer"))
            .andExpect(jsonPath("$.access_token").isNotEmpty())
            .andExpect(jsonPath("$.expires_in").value(greaterThan(0)))
            .andExpect(jsonPath("$.refresh_token").doesNotExist())
            .andExpect(jsonPath("$.scope").value("inventory.read"));
}
~~~

**/oauth2/token** là endpoint mặc định. Nếu **AuthorizationServerSettings** của ứng dụng thay đổi token endpoint URI, dùng URI đã cấu hình. Test cũng cần xác minh client authentication thất bại khi secret sai:

~~~java
@Test
void rejectsClientCredentialsWithWrongSecret() throws Exception {
    mockMvc.perform(post("/oauth2/token")
                    .with(httpBasic("test-service-client", "wrong-secret"))
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("grant_type", "client_credentials")
                    .param("scope", "inventory.read"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error").value("invalid_client"));
}
~~~

Thêm ca kiểm thử scope không được đăng ký hoặc không được cấp cho client. Token endpoint phải trả lỗi OAuth phù hợp, thường là **invalid_scope**, và không tạo authorization hoặc access token có quyền vượt quá scope của client. Không chỉ kiểm tra HTTP status; kiểm tra cả trường **error** trong response để xác định server trả đúng lỗi giao thức.

Để kiểm tra thời hạn, đặt **accessTokenTimeToLive** ngắn trong test profile và xác minh **expires_in** dương, không vượt quá lifetime đã cấu hình (có tính đến thời gian request). Với JWT access token, có thể giải mã bằng public key test và xác minh **iat**, **exp**, **iss** cùng scope. Với opaque token, kiểm tra token qua introspection hoặc resource server theo cấu hình thực tế.

Sau khi access token hết hạn, client máy chủ gọi lại Client Credentials với cùng phương thức xác thực. Test cần xác minh access token mới được cấp và token cũ không còn được chấp nhận sau thời điểm hết hạn. Không gửi refresh token trong request này.

## 4. Chuẩn bị authorization có refresh token

Refresh token được cấp trong một luồng ủy quyền hỗ trợ refresh token, thường là Authorization Code. Client phải được đăng ký với cả **authorization_code** và **refresh_token**; người dùng phải hoàn tất đăng nhập và consent theo cấu hình. Nếu client yêu cầu PKCE, authorization request phải dùng **code_challenge_method=S256**, và token request đổi authorization code phải gửi đúng **code_verifier**.

Có hai mức kiểm thử nên duy trì:

1. **End-to-end authorization flow:** gửi authorization request, xác thực người dùng, xử lý consent, đổi authorization code và xác minh response có refresh token khi chính sách client cho phép.
2. **Refresh endpoint test:** nạp một authorization fixture đã có refresh token vào **OAuth2AuthorizationService**, sau đó gửi request refresh trực tiếp đến token endpoint. Cách này giúp cô lập việc kiểm tra rotation, hết hạn, client binding và replay mà không phải lặp lại màn hình đăng nhập và consent trong từng test.

Ví dụ helper dưới đây tạo authorization fixture để kiểm tra refresh endpoint. Nó chỉ là dữ liệu chuẩn bị cho test token endpoint; cần có ít nhất một bài end-to-end riêng để chứng minh luồng Authorization Code thực sự phát hành refresh token:

~~~java
private String saveRefreshAuthorization(
        RegisteredClient client,
        OAuth2AuthorizationService authorizationService,
        Instant refreshTokenExpiresAt) {

    Instant now = Instant.now();
    OAuth2RefreshToken refreshToken = new OAuth2RefreshToken(
            "refresh-fixture-" + UUID.randomUUID(),
            now.minusSeconds(30),
            refreshTokenExpiresAt);

    OAuth2AccessToken previousAccessToken = new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            "expired-access-" + UUID.randomUUID(),
            now.minusSeconds(120),
            now.minusSeconds(1),
            Set.of("profile"));

    Authentication userPrincipal = new UsernamePasswordAuthenticationToken(
            "alice",
            "N/A",
            AuthorityUtils.createAuthorityList("ROLE_USER"));

    OAuth2Authorization authorization = OAuth2Authorization
            .withRegisteredClient(client)
            .principalName("alice")
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .authorizedScopes(Set.of("profile"))
            .attribute(Principal.class.getName(), userPrincipal)
            .token(previousAccessToken)
            .token(refreshToken)
            .build();

    authorizationService.save(authorization);
    return refreshToken.getTokenValue();
}
~~~

Helper cần các import **java.security.Principal**, **java.time.Instant**, **java.util.Set**, **java.util.UUID**, **org.springframework.security.core.Authentication**, **org.springframework.security.core.authority.AuthorityUtils**, **org.springframework.security.authentication.UsernamePasswordAuthenticationToken**, **org.springframework.security.oauth2.core.OAuth2AccessToken**, **org.springframework.security.oauth2.core.OAuth2RefreshToken**, **org.springframework.security.oauth2.core.AuthorizationGrantType**, **org.springframework.security.oauth2.server.authorization.OAuth2Authorization** và **org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService**.

Trong test class, lấy client bằng **RegisteredClientRepository.findByClientId("test-user-client")** và truyền vào helper. Refresh token phải được lưu trong authorization gắn với đúng registered client. **principalName**, principal attribute và authorized scopes cung cấp ngữ cảnh mà refresh grant cần để tạo token mới. Fixture dùng access token cũ đã hết hạn để mô phỏng tình huống client cần refresh.

## 5. Kiểm thử refresh token rotation và replay

Với **reuseRefreshTokens(false)**, lần đổi refresh token thành công phải trả về access token mới và refresh token mới. Test lưu lại refresh token cũ, kiểm tra giá trị mới khác giá trị cũ, sau đó thử dùng lại token cũ:

~~~java
@Autowired
RegisteredClientRepository registeredClientRepository;

@Autowired
OAuth2AuthorizationService authorizationService;

@Test
void rotatesRefreshTokenAndRejectsThePreviousValue() throws Exception {
    RegisteredClient client = registeredClientRepository
            .findByClientId("test-user-client");
    String oldRefreshToken = saveRefreshAuthorization(
            client,
            authorizationService,
            Instant.now().plus(Duration.ofMinutes(20)));

    MvcResult result = mockMvc.perform(post("/oauth2/token")
                    .with(httpBasic("test-user-client", "user-secret"))
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("grant_type", "refresh_token")
                    .param("refresh_token", oldRefreshToken))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.access_token").isNotEmpty())
            .andExpect(jsonPath("$.refresh_token").isNotEmpty())
            .andReturn();

    JsonNode body = objectMapper.readTree(
            result.getResponse().getContentAsString());
    String newRefreshToken = body.path("refresh_token").asText();

    assertThat(newRefreshToken)
            .isNotBlank()
            .isNotEqualTo(oldRefreshToken);

    mockMvc.perform(post("/oauth2/token")
                    .with(httpBasic("test-user-client", "user-secret"))
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("grant_type", "refresh_token")
                    .param("refresh_token", oldRefreshToken))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error").value("invalid_grant"));
}
~~~

Test cần có **ObjectMapper** để đọc JSON và AssertJ để kiểm tra giá trị token. Response refresh thành công cũng nên được kiểm tra về **token_type**, **expires_in** và scope. Nếu client gửi tham số **scope**, giá trị yêu cầu phải là tập con của scope đã được authorization ban đầu chấp thuận; server không được mở rộng quyền trong lúc refresh.

Có thể kiểm tra token mới thực sự dùng được bằng cách gửi một request refresh tiếp theo với token mới. Nếu chính sách rotation được bật, lần thứ hai phải phát hành một token khác nữa và token ở lần trước trở thành token cũ. Bài test replay phải dùng đúng token đã bị thay thế, không dùng token mới.

## 6. Kiểm thử refresh token hết hạn, sai client và bị thu hồi

Refresh token có lifetime riêng, độc lập với access token. Một access token hết hạn không làm refresh token tự hết hạn. Ngược lại, refresh token đã hết hạn phải bị từ chối ngay cả khi client authentication hợp lệ.

Tạo fixture với **refreshTokenExpiresAt** ở quá khứ và xác minh server trả **invalid_grant**:

~~~java
@Test
void rejectsExpiredRefreshToken() throws Exception {
    RegisteredClient client = registeredClientRepository
            .findByClientId("test-user-client");
    String expiredRefreshToken = saveRefreshAuthorization(
            client,
            authorizationService,
            Instant.now().minusSeconds(1));

    mockMvc.perform(post("/oauth2/token")
                    .with(httpBasic("test-user-client", "user-secret"))
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("grant_type", "refresh_token")
                    .param("refresh_token", expiredRefreshToken))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error").value("invalid_grant"));
}
~~~

Ngoài hết hạn và replay, cần có các trường hợp sau:

- **Sai client:** dùng refresh token của **test-user-client** với một client khác. Server phải từ chối vì refresh token gắn với client đã được cấp.
- **Client authentication sai:** gửi refresh token đúng nhưng secret của client sai. Server phải từ chối xác thực client trước khi cấp token.
- **Token bị thu hồi:** xóa hoặc vô hiệu hóa authorization chứa refresh token qua cơ chế revoke của ứng dụng; lần refresh sau phải thất bại.
- **Scope vượt quyền:** yêu cầu scope chưa được người dùng chấp thuận. Server phải trả lỗi và không cấp access token có scope bổ sung.
- **Grant không được đăng ký:** client không có **refresh_token** grant không được đổi refresh token.

Với test thu hồi, hãy dùng đúng cơ chế mà ứng dụng vận hành, chẳng hạn cập nhật hoặc xóa authorization qua **OAuth2AuthorizationService**. Không chỉ xóa refresh token khỏi một map phụ nếu luồng production dùng JDBC hoặc một kho lưu trữ khác.

## 7. Kiểm tra tính nhất quán khi chạy nhiều instance

Rotation chỉ có ý nghĩa khi token cũ không thể tiếp tục được chấp nhận sau khi token mới được lưu. Trong môi trường một instance, bài test replay cơ bản xác minh điều này. Trong môi trường nhiều instance, cần kiểm tra thêm tình huống hai request cùng gửi một refresh token gần như đồng thời.

Nếu hai instance cùng đọc authorization trước khi một instance kịp lưu trạng thái mới, cả hai có thể xử lý trên cùng trạng thái cũ nếu kho lưu trữ không có cơ chế đồng bộ phù hợp. **reuseRefreshTokens(false)** quy định tạo token mới; nó không tự thay thế chiến lược transaction, locking hoặc kiểm soát cập nhật đồng thời của kho lưu trữ.

Với JDBC hoặc kho dữ liệu dùng chung, kiểm tra:

- Việc đọc và cập nhật authorization có transaction phù hợp hay không.
- Hai request refresh đồng thời có thể cùng chấp nhận token cũ hay không.
- Bản ghi authorization mới có được các instance khác nhìn thấy ngay hay không.
- Token cũ có bị từ chối sau khi rotation được commit hay không.
- Khi lưu token mới thất bại, trạng thái cũ có còn nhất quán và có thể phục hồi hay không.

Nếu hệ thống yêu cầu refresh token chỉ được sử dụng một lần kể cả khi có request đồng thời, hãy xác định và kiểm thử rõ cơ chế atomic consume hoặc optimistic locking ở tầng persistence. Một bài test tuần tự không chứng minh được thuộc tính này.

## 8. Ma trận kiểm thử và chẩn đoán

| Kịch bản | Kết quả mong đợi |
|---|---|
| Client Credentials với secret và scope hợp lệ | **200 OK**, có access token, không có refresh token |
| Client Credentials với secret sai | **401**, lỗi **invalid_client** |
| Client Credentials yêu cầu scope không được cấp | Lỗi **invalid_scope**, không cấp token vượt quyền |
| Refresh token hợp lệ, rotation bật | **200 OK**, có access token và refresh token mới |
| Dùng lại refresh token cũ sau rotation | **400**, lỗi **invalid_grant** |
| Refresh token hết hạn hoặc bị thu hồi | **400**, lỗi **invalid_grant** |
| Refresh token thuộc client khác | Bị từ chối, không cấp token |
| Refresh request yêu cầu scope ngoài quyền ban đầu | Bị từ chối, không mở rộng scope |
| Hai request đồng thời dùng một refresh token | Kết quả phù hợp chính sách atomicity đã thiết kế; không để hai lần sử dụng ngoài ý muốn cùng thành công |

Khi test thất bại, kiểm tra theo thứ tự: client có được tìm thấy không; phương thức client authentication có khớp fixture không; grant type đã đăng ký chưa; refresh token có được lưu với đúng client ID không; token đã hết hạn hoặc bị invalidated chưa; **reuseRefreshTokens** có đúng giá trị mong muốn không; và authorization service có lưu trạng thái mới thành công không.

Không ghi access token, refresh token hoặc client secret vào log để chẩn đoán. Có thể log client ID, grant type, mã lỗi OAuth, correlation ID và kết quả thao tác lưu trữ. Khi cần đối chiếu một token trong test log, dùng giá trị giả lập hoặc fingerprint một chiều thay cho token nguyên bản.

## 9. Checklist hoàn tất

Trước khi xem bộ kiểm thử là đạt, xác minh các điểm sau:

- Client Credentials và Authorization Code/Refresh Token dùng fixture riêng, có grant type và scope tối thiểu.
- Client Credentials chỉ phát hành access token; client lấy token mới bằng cách xác thực lại khi access token hết hạn.
- Refresh token chỉ được kiểm thử trong client và authorization đã được cấp quyền phù hợp.
- Refresh token gắn với đúng client, principal và scope đã chấp thuận.
- Rotation được bật rõ bằng **reuseRefreshTokens(false)** và test xác minh token mới khác token cũ.
- Token cũ bị từ chối sau rotation; token hết hạn, bị thu hồi hoặc thuộc client khác cũng bị từ chối.
- Scope của access token mới không vượt quá quyền đã được cấp.
- Test persistence dùng cùng loại authorization service và transaction semantics với môi trường mục tiêu.
- Test đồng thời được chạy nếu hệ thống yêu cầu refresh token chỉ được tiêu thụ một lần trên nhiều instance.

Khi các ca này được kiểm tra qua token endpoint thật trong test context, nhóm phát triển có thể phát hiện lỗi đăng ký client, client authentication, thời hạn token, rotation và lưu trữ authorization trước khi thay đổi được đưa vào môi trường vận hành.
