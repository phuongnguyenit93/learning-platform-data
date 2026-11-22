# Kiểm thử tích hợp bằng MockMvc, client thật và Testcontainers

Một Authorization Server có thể vượt qua unit test nhưng vẫn thất bại khi các thành phần làm việc cùng nhau. Security filter chain có thể chặn nhầm endpoint, authorization code không được lưu đúng, PKCE bị bỏ qua ở token endpoint, cookie phiên bị mất giữa các request hoặc dữ liệu authorization không được chia sẻ giữa các instance. Kiểm thử tích hợp cần xác minh những ranh giới này bằng cấu hình Spring thật và dependency gần với môi trường triển khai.

Với Spring Authorization Server, nên phối hợp ba cách tiếp cận:

- **MockMvc** gửi request qua Spring MVC và Security filter chain trong ApplicationContext kiểm thử. Cách này phù hợp để kiểm tra endpoint, status, header, redirect, cookie, lỗi OAuth và các luồng có thể điều khiển trực tiếp.
- **Client thật qua HTTP** gọi ứng dụng đang chạy trên cổng mạng thực. Có thể dùng HTTP client để kiểm tra endpoint hoặc một ứng dụng OAuth2 Client thực để hoàn tất đăng nhập, callback và xử lý token như hệ thống tích hợp bên ngoài.
- **Testcontainers** khởi chạy dependency thật như PostgreSQL hoặc Redis trong container riêng cho test. Cách này giúp phát hiện lỗi schema, SQL, transaction, persistence và session mà database giả lập có thể bỏ sót.

Mỗi cách kiểm tra một ranh giới khác nhau. MockMvc không tạo kết nối TCP/TLS thực; một HTTP client không tự chứng minh dữ liệu được lưu bền vững; Testcontainers không tự kiểm tra giao thức OAuth. Kết hợp chúng sẽ tạo bằng chứng tốt hơn về hành vi của Authorization Server.

## 1. Chọn đúng lớp kiểm thử

Trước khi viết test, xác định câu hỏi cần trả lời. Nếu mục tiêu là kiểm tra validator hoặc token customizer, unit test thường đủ. Nếu cần kiểm tra filter chain, endpoint và repository cùng hoạt động, dùng MockMvc với Spring context. Nếu cần xác minh TLS, reverse proxy, redirect qua trình duyệt hoặc nhiều instance, dùng client thật qua HTTP. Nếu cần kiểm tra JDBC authorization service, consent hoặc session store, đưa database/cache thật vào bằng Testcontainers.

| Lớp kiểm thử | Thành phần thật | Thành phần được mô phỏng | Phù hợp để xác minh |
|---|---|---|---|
| Unit | Class đang kiểm thử | Dependency bên ngoài | Quy tắc scope, claim, validator và customizer |
| MockMvc integration | ApplicationContext, MVC, Security filter chain, bean và repository được cấu hình | TCP, TLS, proxy, trình duyệt | Endpoint OAuth/OIDC, authentication, authorization, token, lỗi, cookie và redirect |
| HTTP integration | Server chạy trên cổng thật và các bean của nó | Có thể vẫn dùng dependency test | Request/response qua mạng, redirect, cookie và metadata |
| Testcontainers integration | Database/cache/service trong container | Dependency không thuộc test | SQL, migration, transaction, persistence và session |
| End-to-end với client thật | Authorization Server và OAuth2 Client riêng | Có thể dùng user/identity fixture | Login, consent, callback, token exchange, principal và session phía client |

Không nên dùng một test duy nhất để chứng minh mọi lớp. MockMvc trả về redirect đúng chỉ chứng minh response trong servlet environment. Nó không chứng minh reverse proxy công bố đúng scheme, certificate hợp lệ hoặc trình duyệt gửi lại cookie theo chính sách SameSite.

Một bộ test tích hợp cơ bản cho Authorization Server nên bao gồm:

1. Discovery và metadata công bố issuer, endpoint, JWKS đúng.
2. Authorization request được kiểm tra client, grant, scope và redirect URI.
3. Người dùng đã xác thực có thể hoàn thành Authorization Code Flow.
4. PKCE S256 được xác minh tại token endpoint.
5. Authorization code chỉ dùng được một lần và hết hạn theo chính sách.
6. Client authentication và grant type được áp dụng đúng.
7. Authorization, consent và token được lưu/đọc lại qua repository thật.
8. Refresh, revocation và introspection hoạt động theo cấu hình.
9. Cookie, session, CSRF và redirect hoạt động đúng qua HTTP.
10. Nhiều instance có thể đọc trạng thái authorization dùng chung nếu kiến trúc yêu cầu.

## 2. Chuẩn bị test dependencies

Ví dụ Maven dưới đây dùng Spring Boot test support, Spring Security test support và Testcontainers. Hãy dùng phiên bản Testcontainers tương thích với JDK, Spring Boot và dependency management của dự án. Nếu dự án đã quản lý Testcontainers bằng BOM, không khai báo version riêng cho từng module.

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>
~~~

Nếu dùng Testcontainers BOM, quản lý phiên bản tập trung tại dependencyManagement bằng artifact testcontainers-bom, type pom và scope import. Không cần thêm dependency Testcontainers cho loại database không được dùng.

Để chạy Testcontainers, máy phát triển hoặc CI runner cần Docker Engine hoặc runtime tương thích đang hoạt động. Nếu môi trường CI không có quyền khởi chạy container, cấu hình runner phù hợp trước khi chạy suite.

## 3. Khởi chạy PostgreSQL bằng Testcontainers

Với Spring Authorization Server lưu RegisteredClient, OAuth2Authorization và OAuth2AuthorizationConsent trong JDBC, PostgreSQL container giúp kiểm tra repository bằng database thực. Ví dụ dưới đây cung cấp URL, username và password động cho Spring Boot qua DynamicPropertySource.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class AuthorizationServerDatabaseIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("authorization_test")
                    .withUsername("test_user")
                    .withPassword("test_password");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Test
    void applicationContextStartsWithRealDatabase() {
        // ApplicationContext đã khởi động và kết nối PostgreSQL container.
    }
}
~~~

Đây là skeleton minh họa vòng đời container và cấu hình datasource. Trong dự án thật, class test cần chạy cùng migration/schema của ứng dụng. Nếu production dùng Flyway hoặc Liquibase, hãy để migration chạy trong test profile theo cùng thứ tự và cấu trúc schema. Nếu dùng schema script của Spring Authorization Server, quản lý script đó bằng migration của dự án thay vì dựa vào database đã chuẩn bị thủ công trên máy cá nhân.

Các bảng JDBC thường được dùng để lưu:

- Registered client: cấu hình client, grant type, redirect URI, scope và client settings.
- Authorization: authorization code, access token, refresh token, ID Token và metadata liên quan.
- Authorization consent: scope mà resource owner đã chấp thuận cho client.

Không đưa dữ liệu nhạy cảm production vào container test. Dùng fixture riêng và làm cho test độc lập với thứ tự chạy.

### Kiểm tra dữ liệu tồn tại sau khi khởi tạo repository

Một kiểm thử persistence nên lưu dữ liệu qua repository, sau đó đọc lại bằng repository hoặc application context khác. Mục tiêu là xác minh dữ liệu thực sự được ghi vào database, thay vì chỉ nằm trong object hoặc mock.

~~~java
@Autowired
RegisteredClientRepository registeredClientRepository;

@Test
void registeredClientCanBeReadBackFromJdbcStore() {
    String clientId = "jdbc-client-test";

    RegisteredClient client = RegisteredClient.withId(UUID.randomUUID().toString())
            .clientId(clientId)
            .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("https://client.example.test/callback")
            .scope(OidcScopes.OPENID)
            .clientSettings(ClientSettings.builder()
                    .requireProofKey(true)
                    .build())
            .build();

    registeredClientRepository.save(client);

    RegisteredClient loaded =
            registeredClientRepository.findByClientId(clientId);

    assertThat(loaded).isNotNull();
    assertThat(loaded.getClientId()).isEqualTo(clientId);
    assertThat(loaded.getClientSettings().isRequireProofKey()).isTrue();
}
~~~

Ví dụ giả định repository đang được cấu hình bằng JDBC và bảng đã được migration. Nếu test suite chạy song song, dùng client ID duy nhất hoặc tạo database/schema riêng cho từng test suite. Tránh dùng một client ID cố định trong database dùng chung giữa nhiều pipeline.

Chọn image và cấu hình gần với production: phiên bản PostgreSQL, collation, timezone, extension và kiểu dữ liệu có liên quan. Nếu production dùng MySQL, MariaDB hoặc SQL Server, hãy dùng container tương ứng để test migration và câu SQL trên đúng engine. Một test với PostgreSQL không chứng minh tương thích với MySQL.

Nếu ứng dụng dùng Redis để lưu Spring Session, có thể bổ sung Redis container. Chỉ thêm container khi Redis thực sự là dependency của ứng dụng.

## 4. Kiểm thử endpoint bằng MockMvc

MockMvc gửi request qua DispatcherServlet và filter chain trong Spring ApplicationContext mà không cần mở cổng TCP. Đây là cách phù hợp để kiểm tra hành vi HTTP của Authorization Server nhanh và có thể kiểm soát.

Với cấu hình bảo mật thực tế, dùng SpringBootTest kết hợp AutoConfigureMockMvc. Không tắt filter chỉ để test dễ pass. Nếu dùng WebMvcTest slice, phải cung cấp đầy đủ bean cần thiết và hiểu rõ slice có thể bỏ qua cấu hình Authorization Server hoặc Security filter chain nào.

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationServerEndpointTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void discoveryEndpointReturnsProviderMetadata() throws Exception {
        mockMvc.perform(get("/.well-known/openid-configuration"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.issuer").value(
                        "https://auth.example.test"))
                .andExpect(jsonPath("$.authorization_endpoint").exists())
                .andExpect(jsonPath("$.token_endpoint").exists())
                .andExpect(jsonPath("$.jwks_uri").exists());
    }
}
~~~

Đường dẫn discovery và các trường metadata phụ thuộc issuer, OIDC configuration và phiên bản framework. Nếu issuer có path hoặc metadata endpoint được cấu hình khác, dùng URL chính xác mà ứng dụng công bố. Không ép test mong đợi endpoint mà ứng dụng không bật.

### Kiểm tra token endpoint với client fixture

Token endpoint yêu cầu client authentication tùy theo loại client và phương thức đã đăng ký. Spring Security test cung cấp httpBasic request post processor cho confidential client dùng client_secret_basic.

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class TokenEndpointTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void rejectsUnknownAuthorizationCode() throws Exception {
        mockMvc.perform(post("/oauth2/token")
                .with(httpBasic("web-confidential-test", "test-secret"))
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("grant_type", "authorization_code")
                .param("code", "unknown-code")
                .param("redirect_uri",
                        "https://client.example.test/callback"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error").value("invalid_grant"))
            .andExpect(jsonPath("$.access_token").doesNotExist())
            .andExpect(jsonPath("$.refresh_token").doesNotExist());
    }
}
~~~

Fixture web-confidential-test phải được đăng ký trong repository với phương thức client_secret_basic, grant Authorization Code và redirect URI khớp. Nếu fixture dùng client_secret_post, private_key_jwt hoặc mTLS, cách xác thực trong request phải thay đổi tương ứng. Không dùng secret giả định để kiểm tra public client.

Test âm cần kiểm tra cả status, error code và việc không phát hành token. Không assert thông báo lỗi nội bộ cụ thể nếu thông báo đó có thể thay đổi giữa các phiên bản hoặc làm lộ thông tin nhạy cảm.

## 5. Kiểm thử Authorization Code Flow và PKCE bằng MockMvc

Có thể kiểm tra một luồng Authorization Code Flow bằng MockMvc mà không cần trình duyệt, miễn là mục tiêu là xác minh hành vi của Authorization Server. Test thiết lập principal đã đăng nhập, gửi authorization request, lấy code từ redirect rồi đổi code tại token endpoint.

Ví dụ sau dùng public client để tập trung kiểm tra PKCE. Client không có client secret, bắt buộc PKCE và không yêu cầu consent tương tác trong test này. Việc kiểm thử màn hình consent cần một test riêng.

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationCodePkceIntegrationTests {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    RegisteredClientRepository registeredClientRepository;

    private String clientId;

    private static final String REDIRECT_URI =
            "https://client.example.test/callback";

    private static final String VERIFIER =
            "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";

    private static final String CHALLENGE =
            "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM";

    @BeforeEach
    void registerPublicClient() {
        clientId = "mvc-public-" + UUID.randomUUID();

        RegisteredClient client = RegisteredClient.withId(
                        UUID.randomUUID().toString())
                .clientId(clientId)
                .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
                .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
                .redirectUri(REDIRECT_URI)
                .scope(OidcScopes.OPENID)
                .scope(OidcScopes.PROFILE)
                .clientSettings(ClientSettings.builder()
                        .requireProofKey(true)
                        .requireAuthorizationConsent(false)
                        .build())
                .build();

        registeredClientRepository.save(client);
    }

    @Test
    @WithMockUser(username = "alice")
    void authorizationCodeCanBeExchangedWithMatchingVerifier()
            throws Exception {

        MvcResult authorizationResult = mockMvc.perform(
                get("/oauth2/authorize")
                        .param("response_type", "code")
                        .param("client_id", clientId)
                        .param("redirect_uri", REDIRECT_URI)
                        .param("scope", "openid profile")
                        .param("state", "state-test-123")
                        .param("nonce", "nonce-test-123")
                        .param("code_challenge", CHALLENGE)
                        .param("code_challenge_method", "S256"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        String redirect = authorizationResult.getResponse()
                .getRedirectedUrl();

        assertThat(redirect).isNotBlank();

        String code = UriComponentsBuilder
                .fromUriString(redirect)
                .build()
                .getQueryParams()
                .getFirst("code");

        assertThat(code).isNotBlank();

        mockMvc.perform(post("/oauth2/token")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("grant_type", "authorization_code")
                        .param("client_id", clientId)
                        .param("code", code)
                        .param("redirect_uri", REDIRECT_URI)
                        .param("code_verifier", VERIFIER))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.access_token").isNotEmpty())
                .andExpect(jsonPath("$.token_type").value("Bearer"));
    }
}
~~~

Đây là ví dụ cấu trúc; cần có các import JUnit, Spring Security Test, MockMvc, UriComponentsBuilder, RegisteredClient và các class Spring Authorization Server tương ứng. Ứng dụng phải bật endpoint OIDC nếu muốn kiểm tra ID Token. Có thể bổ sung assertion id_token khi cấu hình OIDC của ứng dụng đã được bật.

Giá trị verifier/challenge trong ví dụ là test vector PKCE S256 đã biết. Trong suite lớn, nên có helper tạo verifier ngẫu nhiên và tính challenge bằng SHA-256/Base64 URL-safe để mỗi test độc lập. Không tái sử dụng authorization code giữa các test.

### Kiểm tra verifier sai và code replay

Mỗi test âm phải tạo authorization code mới. Sau khi lấy code, gửi verifier sai và xác minh token endpoint trả invalid_grant. Một test khác đổi code thành công rồi gửi lại cùng code để xác minh code không thể được dùng lần hai.

Các kiểm tra quan trọng:

- Authorization request thiếu PKCE bị từ chối nếu client yêu cầu PKCE.
- code_challenge_method không được phép bị từ chối theo chính sách.
- code_verifier không khớp challenge bị từ chối.
- redirect_uri tại token endpoint phải khớp URI đã dùng khi cấp code.
- Code hết hạn hoặc đã tiêu thụ không thể đổi lại.
- Token response không xuất hiện khi request thất bại.

Không gộp tất cả trường hợp âm vào một test. Mỗi test nên chỉ thay đổi một điều kiện để khi thất bại có thể xác định nguyên nhân.

MockMvc không tự mô phỏng hành vi trình duyệt. Nó không tự xử lý JavaScript, cookie policy của browser, SameSite cross-site navigation, TLS certificate, reverse proxy hay callback trên domain khác. Có thể kiểm tra header Set-Cookie và Location ở mức servlet, nhưng phải dùng browser/client thật để xác minh hành vi trình duyệt.

## 6. Dùng client HTTP thật với server đang chạy

Để kiểm tra kết nối mạng, khởi chạy Authorization Server trên cổng ngẫu nhiên bằng SpringBootTest webEnvironment RANDOM_PORT. Test dùng HTTP client thực để gọi endpoint qua TCP.

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class AuthorizationServerHttpTests {

    @LocalServerPort
    int port;

    private HttpClient httpClient;

    @BeforeEach
    void createHttpClient() {
        httpClient = HttpClient.newBuilder()
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
    }

    @Test
    void metadataCanBeReadOverHttp() throws Exception {
        URI metadataUri = URI.create(
                "http://localhost:" + port
                        + "/.well-known/openid-configuration");

        HttpRequest request = HttpRequest.newBuilder(metadataUri)
                .GET()
                .header("Accept", "application/json")
                .build();

        HttpResponse<String> response = httpClient.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.body()).contains("issuer");
        assertThat(response.body()).contains("jwks_uri");
    }
}
~~~

Trong ví dụ, redirect không được tự động follow để test có thể kiểm tra Location và các bước OAuth. Nếu bật follow redirect, HTTP client có thể che mất response trung gian hoặc đi theo callback không mong muốn. Với authorization endpoint, thường cần giữ redirect ở trạng thái thủ công để kiểm tra code và state.

### Gọi token endpoint bằng HTTP client

Đối với confidential client, có thể kiểm tra token exchange bằng HTTP client thật sau khi lấy authorization code hợp lệ từ một luồng test. Ví dụ minh họa phần gửi token request bằng client_secret_basic:

~~~java
String credentials = clientId + ":" + clientSecret;
String basic = Base64.getEncoder().encodeToString(
        credentials.getBytes(StandardCharsets.UTF_8));

String form = "grant_type=authorization_code"
        + "&code=" + URLEncoder.encode(code, StandardCharsets.UTF_8)
        + "&redirect_uri=" + URLEncoder.encode(
                redirectUri, StandardCharsets.UTF_8);

HttpRequest tokenRequest = HttpRequest.newBuilder(
                URI.create(baseUrl + "/oauth2/token"))
        .header("Authorization", "Basic " + basic)
        .header("Content-Type", "application/x-www-form-urlencoded")
        .POST(HttpRequest.BodyPublishers.ofString(form))
        .build();

HttpResponse<String> tokenResponse = httpClient.send(
        tokenRequest, HttpResponse.BodyHandlers.ofString());

assertThat(tokenResponse.statusCode()).isEqualTo(200);
assertThat(tokenResponse.body()).contains("access_token");
~~~

Nếu client dùng PKCE, thêm code_verifier vào form. Nếu dùng public client, không gửi Authorization Basic; gửi client_id theo yêu cầu của client type. Trong test code thực tế, nên dùng form encoder hoặc thư viện HTTP để encode từng parameter, không tự nối chuỗi với dữ liệu chưa encode.

HTTP client này xác minh kết nối mạng và token endpoint thực. Nó chưa phải một OAuth2 Client đầy đủ: nó không tự quản lý state, nonce, browser session, discovery, token validation hay authorized client lifecycle. Những hành vi đó cần được kiểm tra bằng ứng dụng client thực hoặc thư viện OAuth/OIDC client.

## 7. Kiểm thử với một ứng dụng OAuth2 Client thực

Một cách kiểm tra tích hợp có giá trị là chạy hai ứng dụng riêng:

~~~text
Browser / test automation
          |
          v
Ứng dụng client dùng Spring Security OAuth2 Client
          |
          | Authorization request / token exchange
          v
Spring Authorization Server
          |
          v
PostgreSQL / Redis test containers
~~~

Ứng dụng client dùng Spring Security OAuth2 Client như một bên tích hợp độc lập. Client được cấu hình bằng issuer URI, client ID, client secret (nếu confidential), redirect URI và scope. Nó bắt đầu đăng nhập tại endpoint /oauth2/authorization/{registrationId}; Spring Security điều hướng đến Authorization Server và xử lý callback tại /login/oauth2/code/{registrationId}.

Ví dụ cấu hình client trong application-test.yml:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          authorization-server:
            provider: authorization-server
            client-id: browser-test-client
            client-secret: test-client-secret
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          authorization-server:
            issuer-uri: https://auth.example.test
~~~

Cấu hình này minh họa confidential web client. Với SPA hoặc native public client, không cấu hình client secret và dùng PKCE theo chính sách. URI issuer trong test phải trỏ đến Authorization Server thực sự đang chạy. Nếu cổng hoặc domain được tạo động, cấp giá trị issuer/registration cho client test từ địa chỉ server đã khởi động thay vì giữ URL không tồn tại.

Một bài test browser end-to-end có thể:

1. Khởi chạy Authorization Server và client application với cấu hình test.
2. Mở trang client qua Playwright hoặc Selenium.
3. Truy cập endpoint bắt đầu OAuth login.
4. Đăng nhập bằng user fixture trong Authorization Server.
5. Chấp thuận consent nếu client yêu cầu.
6. Xác minh browser quay về đúng callback của client.
7. Xác minh client tạo Authentication principal và lưu authorized client.
8. Gọi endpoint phía client để xác minh thông tin user đã được lấy từ ID Token hoặc UserInfo theo cấu hình.
9. Kiểm tra logout và trạng thái session.

Đây là nơi nên kiểm tra state, nonce, cookie, SameSite, cross-site redirect và hành vi thực tế của trình duyệt. Không cần chạy browser automation cho mọi unit test; giữ nó ở nhóm end-to-end có thời gian chạy dài hơn.

Nếu module có API/resource server tiêu thụ access token, chạy resource server hoặc test endpoint tương ứng. Gửi access token được Authorization Server cấp và xác minh quyền truy cập theo scope/authority. Sau đó thử token hết hạn, sai audience, sai issuer hoặc chữ ký không hợp lệ. Điều này kiểm tra cả hai phía của hợp đồng: Authorization Server phát token đúng và resource server xác minh token đúng.

## 8. Dùng Testcontainers để kiểm tra authorization và consent persistence

Mock repository chỉ cho biết code gọi đúng method. Nó không chứng minh JDBC serialization, schema, transaction hay việc authorization được tìm lại sau request khác. Khi dùng JDBC store, nên chạy các test sau trên database container:

| Hành vi | Kiểm tra |
|---|---|
| RegisteredClient | Lưu và đọc lại client, authentication method, grant, redirect URI, scope và settings |
| Authorization code | Lưu code, đổi code, đánh dấu đã tiêu thụ và từ chối replay |
| Access token | Đọc lại token metadata, expiry, scope và principal association |
| Refresh token | Cập nhật hoặc thu hồi token theo chính sách |
| Consent | Lưu consent, đọc lại scope và áp dụng khi authorization request kế tiếp |
| Restart | Khởi động lại application context hoặc instance và xác minh dữ liệu vẫn còn |
| Concurrent access | Hai request đồng thời không tiêu thụ cùng authorization code thành công |
| Migration | Database trống được nâng cấp đúng schema; schema cũ được nâng cấp theo migration |

Một test hữu ích là tạo authorization code trên instance A, sau đó dùng token endpoint của instance B để đổi code. Nếu cả hai instance dùng chung PostgreSQL và cùng issuer/key configuration, instance B phải tìm được authorization và xử lý code đúng. Sau khi code đã được đổi, instance A phải từ chối replay. Đây là test tích hợp nhiều instance, có thể cần hai server process hoặc hai application context với cổng riêng.

Không chỉ kiểm tra database bằng cách đọc row. Cần xác minh hành vi qua repository/service public của ứng dụng hoặc endpoint giao thức để chứng minh toàn bộ mapping và serialization hoạt động.

### Transaction và test isolation

Với MockMvc trong cùng thread, một test có thể dùng transaction của test framework trong một số tình huống. Tuy nhiên, không dựa vào @Transactional để rollback mọi side effect khi ứng dụng chạy trên RANDOM_PORT. Request được xử lý ở server thread khác và có transaction riêng; transaction của test không bao trùm transaction của server.

Các chiến lược isolation phù hợp:

- Dùng database container riêng cho test suite và làm sạch dữ liệu fixture sau mỗi test.
- Dùng schema/database riêng theo worker hoặc pipeline.
- Tạo client ID, subject và state duy nhất cho từng test.
- Dùng migration để khởi tạo schema sạch.
- Tránh phụ thuộc vào thứ tự test hoặc dữ liệu do test trước tạo ra.

Nếu cần rollback dữ liệu, thực hiện qua transaction/cleanup ở phía ứng dụng hoặc xóa fixture theo khóa định danh sau khi test hoàn tất. Không truncate bảng authorization dùng chung khi các test đang chạy song song.

## 9. Kiểm thử session và Redis nếu ứng dụng sử dụng Spring Session

Nếu ứng dụng lưu HTTP session trong Redis, dùng Redis container để xác minh session có thể được đọc bởi instance khác và còn tồn tại sau khi application context restart. Chỉ dùng in-memory session khi đó đúng là kiến trúc được kiểm thử.

Các trường hợp cần có:

- Login tạo session mới và cookie phiên được trả về.
- Request kế tiếp dùng cookie đó tiếp tục phiên đăng nhập.
- Instance B đọc được session do instance A tạo.
- Logout xóa hoặc vô hiệu hóa session theo chính sách.
- Session hết hạn không được chấp nhận.
- Session ID được thay đổi sau authentication nếu session fixation protection được bật.
- Redis mất kết nối hoặc session không đọc được được xử lý theo hành vi đã định nghĩa.

Testcontainers có thể khởi chạy Redis bằng module tương ứng hoặc GenericContainer với image Redis được pin version. Cấu hình host/port động qua DynamicPropertySource giống cách cấu hình PostgreSQL. Nếu dùng TLS, ACL hoặc Redis Sentinel/Cluster trong production, test cần phản ánh cấu hình đó ở suite phù hợp; một Redis đơn giản không chứng minh topology production.

## 10. Kiểm tra reverse proxy và TLS bằng HTTP client

MockMvc không kiểm tra được TLS termination, certificate, DNS hoặc cách proxy ghi forwarded headers. Để kiểm tra deployment, chạy server sau reverse proxy trong môi trường test hoặc staging và dùng HTTP client/browser truy cập domain công khai.

Các trường hợp nên xác minh:

- Discovery và issuer dùng đúng scheme, host và path công khai.
- Authorization redirect quay về URI client đã đăng ký.
- Không tin Forwarded hoặc X-Forwarded-* do client tự gửi.
- Cookie phiên có Secure, HttpOnly và SameSite phù hợp.
- Endpoint backend chỉ nhận traffic từ proxy được phép.
- TLS certificate và hostname được client xác minh.
- HTTP request được redirect hoặc từ chối theo chính sách HTTPS.
- Prefix do proxy rewrite không bị lặp hoặc mất trong URL.

Không tắt certificate validation trong test chỉ để request chạy được. Nếu môi trường test dùng CA nội bộ, cấu hình trust store test cho HTTP client. Một test bỏ qua xác minh certificate sẽ không phát hiện lỗi chain hoặc hostname verification.

## 11. Tổ chức test suite trong CI

Các test có thời gian chạy và dependency khác nhau. Nên chia suite theo mục đích để pipeline phản hồi nhanh nhưng vẫn giữ được bằng chứng cần thiết.

| Nhóm | Ví dụ | Khi chạy |
|---|---|---|
| Unit | Validator, token customizer, scope mapper | Mỗi thay đổi liên quan |
| MockMvc integration | Authorization endpoint, token endpoint, discovery, error response | Pull request |
| JDBC/Testcontainers | RegisteredClient, authorization, consent, migration | Pull request hoặc build candidate |
| HTTP integration | RANDOM_PORT, real HTTP client, cookie và redirect | Build candidate |
| Client end-to-end | Spring Security OAuth2 Client + browser automation | Staging hoặc lịch chạy chuyên biệt |
| Multi-instance | Code exchange giữa node, session và shared persistence | Staging trước release |

Một số lưu ý khi cấu hình CI:

1. Docker daemon phải sẵn sàng trước khi Testcontainers bắt đầu.
2. Pin image version thay vì dùng latest để test có thể tái lập.
3. Dùng container lifecycle do JUnit/Testcontainers quản lý; không để container test tồn tại vô hạn sau pipeline.
4. Không chia sẻ database hoặc Redis test giữa pipeline không liên quan.
5. Nếu bật test parallel, cô lập fixture và schema để tránh tranh chấp.
6. Lưu log container khi test thất bại nhưng scrub dữ liệu nhạy cảm.
7. Phân biệt test fail do ứng dụng với test không khởi chạy được do Docker/CI runner.
8. Không bỏ qua failure của test bảo mật chỉ để pipeline pass.

Có thể gắn test theo Maven Surefire/Failsafe hoặc Gradle test task tùy cấu trúc dự án. Test có hậu tố IT thường được gom vào integration-test/verify bằng Maven Failsafe; tên class và task phải nhất quán với cấu hình build hiện tại. Không giả định một file test tự động chạy ở phase mong muốn nếu build chưa cấu hình plugin/task tương ứng.

### Kiểm soát dữ liệu test

- Dùng client ID, secret, user, redirect URI và signing key riêng cho test.
- Không commit secret production vào YAML hoặc test source.
- Không in access token, refresh token, authorization code, ID Token hoặc cookie vào log.
- Tạo test data tối thiểu, có thể tái tạo và dọn dẹp.
- Ghi rõ profile OAuth/OIDC, database image, migration version và commit SHA trong kết quả.
- Không dùng endpoint công khai của production làm target cho test phá hủy hoặc test tạo nhiều token.

## 12. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| MockMvc trả 401/302 ngoài dự kiến | Security filter chain, principal hoặc matcher khác test setup | Kiểm tra filter chain thật, request user và endpoint matcher |
| Authorization request bị invalid_request | Client, redirect URI, response type, scope hoặc PKCE không khớp | Đối chiếu RegisteredClient fixture và request |
| Authorization endpoint redirect tới consent | Consent được bật cho client hoặc scope mới | Thiết lập fixture riêng cho test consent và test không consent |
| Token endpoint trả invalid_client | Authentication method hoặc secret fixture sai | Kiểm tra RegisteredClient và cách gửi credential |
| Token endpoint trả invalid_grant | Code hết hạn, đã dùng, sai redirect hoặc PKCE verifier | Tạo code mới cho từng test và kiểm tra verifier |
| Không tìm thấy authorization sau restart | JDBC store chưa được cấu hình hoặc migration sai | Kiểm tra datasource, schema và JdbcOAuth2AuthorizationService |
| Testcontainers không khởi động | Docker daemon, image pull hoặc quyền runner | Kiểm tra Docker availability và log container |
| Test pass với H2 nhưng fail với PostgreSQL | Khác biệt SQL/schema/type/transaction | Chạy đúng database engine của production |
| Browser callback lỗi nhưng MockMvc pass | Cookie, SameSite, state, nonce, TLS hoặc redirect | Chạy test bằng browser/client thật |
| Node B không đổi được code do node A phát | Persistence không dùng chung hoặc issuer/key khác nhau | Kiểm tra database, cấu hình issuer, key set và clock |
| Logout không kết thúc phiên ở node khác | Session store cục bộ hoặc invalidation chưa chia sẻ | Kiểm tra Spring Session/Redis và cookie |

Khi một test thất bại, hãy tìm request đầu tiên có hành vi khác kỳ vọng. Lưu status, Location, header, response body đã scrub, correlation ID và trạng thái fixture. Đừng chỉ tăng timeout hoặc retry test khi nguyên nhân là race condition, database isolation hoặc trạng thái chia sẻ không đúng.

## 13. Checklist hoàn thành kiểm thử tích hợp

- [ ] MockMvc chạy với Spring ApplicationContext và Security filter chain thực.
- [ ] Authorization request kiểm tra client, grant, scope, redirect URI và PKCE.
- [ ] Token endpoint kiểm tra client authentication và response lỗi OAuth.
- [ ] Authorization code chỉ dùng được một lần.
- [ ] Dữ liệu RegisteredClient, authorization và consent được kiểm tra qua JDBC store nếu ứng dụng dùng JDBC.
- [ ] Testcontainers sử dụng database engine và migration phù hợp với production.
- [ ] Test HTTP qua cổng thật kiểm tra redirect, cookie và metadata.
- [ ] Một OAuth2 Client thực hoàn tất login/callback trong suite end-to-end.
- [ ] Access token và ID Token được xác minh theo đúng vai trò.
- [ ] Refresh, revocation và introspection được kiểm tra nếu bật.
- [ ] Redis/session được kiểm tra nếu là dependency của ứng dụng.
- [ ] Proxy/TLS được kiểm tra qua domain công khai ở môi trường phù hợp.
- [ ] Test không phụ thuộc thứ tự, không chia sẻ fixture và có cleanup rõ ràng.
- [ ] CI có Docker/runtime cần thiết, pin image và lưu bằng chứng an toàn.

MockMvc, client thật và Testcontainers tạo thành ba lớp bằng chứng bổ sung cho nhau. MockMvc giúp kiểm tra nhanh logic HTTP và Security trong ứng dụng; client thật xác minh giao thức qua kết nối thực và hành vi của bên tích hợp; Testcontainers xác minh persistence và dependency với công nghệ gần production. Khi mỗi lớp có mục tiêu và giới hạn rõ ràng, bộ kiểm thử của Spring Authorization Server sẽ phát hiện được cả lỗi cấu hình endpoint, lỗi tích hợp client và lỗi trạng thái bền vững trước khi thay đổi được đưa vào vận hành.

