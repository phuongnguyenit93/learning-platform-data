# Giới hạn và dữ liệu độc lập khi kiểm thử một authorization server

Khi một hệ thống triển khai OAuth2, kiểm thử có thể tạo được access token, đăng nhập thành công hoặc gọi được API bảo vệ mà vẫn chưa thực sự kiểm tra **authorization server**. Chẳng hạn, `oauth2Login()` giả lập một người dùng đã đăng nhập; `jwt()` giả lập một danh tính JWT trên Resource Server; và `oauth2Client()` cung cấp authorized client cho ứng dụng. Các công cụ này rất hữu ích, nhưng chúng không chứng minh authorization server đã xác thực client, xử lý grant, phát hành token, lưu authorization hay áp dụng chính sách đồng ý cấp quyền.

Trong chương **Luồng OAuth2 thực** của module **SPRING_SECURITY_TESTING**, chúng ta tìm hiểu **ranh giới của từng cấp kiểm thử** và cách chuẩn bị **dữ liệu độc lập** khi kiểm tra authorization server (AS). Nội dung kết hợp Spring Security Test, MockMvc, WebTestClient và các ca được phép/bị từ chối; đặc biệt chú ý đến việc chạy nhiều test song song, tránh dùng chung token/session/consent và không phụ thuộc môi trường IdP sản xuất.

Mục tiêu là trả lời rõ ba câu hỏi:

1. Test đang kiểm chứng **logic của client hoặc resource server**, hay thực sự đang chạy **giao thức trên authorization server**?
2. Dữ liệu nào phải được tạo mới, cô lập, hoặc xóa sau mỗi test để kết quả không phụ thuộc thứ tự chạy?
3. Một kết quả `200`, `302` hoặc có `access_token` đã chứng minh được điều gì, và còn những điều kiện nào cần một test khác?

## 1. Xác định đúng hệ thống đang được kiểm thử

Một kiến trúc OAuth2 thường có ba vai trò:

| Vai trò | Trách nhiệm điển hình | Ví dụ điều cần kiểm tra |
| --- | --- | --- |
| **Authorization Server (AS)** | Đăng ký client, xác thực client/người dùng, xử lý authorization grant, cấp và có thể thu hồi token, cung cấp metadata/JWKS/introspection | `/oauth2/authorize`, `/oauth2/token`, `/oauth2/revoke`, `/oauth2/introspect` |
| **OAuth2 Client** | Khởi tạo authorization request, giữ `state`, gửi code + PKCE verifier, lưu authorized client, làm mới access token | `/oauth2/authorization/{registrationId}`, callback, `OAuth2AuthorizedClientService` |
| **Resource Server (RS)** | Nhận Bearer token, kiểm tra JWT hoặc introspection, kiểm tra scope/authority trước khi gọi controller | HTTP `401` khi token sai, `403` khi token hợp lệ nhưng thiếu quyền |

~~~mermaid
sequenceDiagram
    participant Browser as Browser/User
    participant Client as OAuth2 Client
    participant AS as Authorization Server
    participant RS as Resource Server
    Browser->>Client: Yêu cầu trang cần kết nối OAuth2
    Client-->>Browser: 302 tới /authorize với state + PKCE challenge
    Browser->>AS: Đăng nhập và đồng ý cấp quyền
    AS-->>Browser: 302 về redirect_uri với code + state
    Browser->>Client: Callback chứa authorization code
    Client->>AS: POST /token với code + code_verifier
    AS-->>Client: Access token (và có thể refresh token)
    Client->>RS: Authorization: Bearer access_token
    RS-->>Client: 200 hoặc 401/403 tùy token và quyền
~~~

Trong một test OAuth2 Client, bạn có thể **giả lập AS** bằng WireMock. Khi ấy test xác nhận **client xử lý AS giả lập đúng**, chứ không xác nhận một AS thật triển khai đúng giao thức. Nếu muốn test chính AS do ứng dụng xây dựng bằng Spring Authorization Server, phải đưa request vào các endpoint/filter của **AS đang được kiểm thử**. WireMock có thể tiếp tục giả lập thành phần bên ngoài như upstream identity provider, nhưng không được thay thế luôn thành phần AS mà ta đang muốn kiểm chứng.

## 2. Phân tầng kiểm thử và giới hạn chứng cứ

| Cấp kiểm thử | Công cụ thường dùng | Chứng minh được | Chưa chứng minh được |
| --- | --- | --- | --- |
| Controller/authorization giả lập | `@WithMockUser`, `oauth2Login()`, `oauth2Client()`, `jwt()`, `opaqueToken()` | Quy tắc truy cập, ánh xạ principal, hành vi endpoint khi đã có danh tính | AS cấp code/token, kiểm tra secret/PKCE, lưu authorization, xác minh chữ ký thật |
| AS chạy trong ứng dụng Servlet test | `@SpringBootTest` + `@AutoConfigureMockMvc`, request tới `/oauth2/*` | Spring Security filter chain của AS, grant, client authentication và phản hồi HTTP trong context | TLS, reverse proxy, cookie/redirect trên trình duyệt thật, cấu hình triển khai ngoài JVM |
| AS chạy trên cổng HTTP trong môi trường kiểm thử | `@SpringBootTest(RANDOM_PORT)`, HTTP client, WebTestClient kết nối server | HTTP transport thật, headers/cookies, redirect, endpoint và lưu trữ tích hợp | Sự khác biệt vận hành của production, IdP thật, chứng chỉ, network policy và hệ thống ngoài nếu đang stub |
| Tích hợp nhiều thành phần ở môi trường riêng | Browser/client thật, AS, RS, database test, IdP giả lập hoặc sandbox | Luồng OAuth2/OIDC giữa các ứng dụng, session, JWKS, token exchange và phân quyền xuyên dịch vụ | Không thể suy ra mọi chính sách production nếu dùng dữ liệu/keys/config khác |

Điều kiện “real OAuth2 flow” phải được nói **cụ thể theo phạm vi**. Một test dùng MockMvc gọi endpoint token thật của Spring Authorization Server có thể kiểm chứng quá trình cấp token ở tầng ứng dụng rất tốt; nó chưa phải bài test TLS hoặc SSO qua browser. Ngược lại, một test sử dụng `mockOAuth2Login()`/`oauth2Login()` có thể bao phủ controller của ứng dụng nhưng bỏ qua quy trình AS.

Trong WebFlux, `WebTestClient` có thể gắn trực tiếp vào application context (không mở TCP socket) hoặc `bindToServer()` tới cổng HTTP đang chạy. Hai cách phục vụ những cấp kiểm thử khác nhau. Không khẳng định đã kiểm tra mạng chỉ vì sử dụng tên lớp `WebTestClient`.

## 3. Những dữ liệu phải cô lập giữa các bài test

AS thường có trạng thái nhiều hơn một bộ kiểm thử controller đơn giản:

| Loại dữ liệu | Nguồn lưu thường gặp | Rủi ro khi dùng chung test | Cách cô lập |
| --- | --- | --- | --- |
| **Registered clients** | `RegisteredClientRepository` | Test sửa redirect URI/scope/secret của client dùng chung khiến test khác thay đổi kết quả | Dùng client riêng theo test hoặc repository mới cho mỗi context |
| **Người dùng và thông tin xác thực** | User store, security provider | Quyền/khóa tài khoản bị thay đổi, test khác đăng nhập nhầm danh tính | Tạo user giả và seed role/status rõ ràng; rollback hoặc reset |
| **Authorization và token** | `OAuth2AuthorizationService` | Code một lần bị tiêu thụ, refresh token bị rotate, token bị revoke ở test khác | Cấp token mới cho mỗi ca; store độc lập hoặc xóa an toàn |
| **Consent** | `OAuth2AuthorizationConsentService` | Consent cũ khiến lần authorize mới không còn màn hình xin đồng ý | Seed/clear consent theo principal + client |
| **Session và cookie** | HTTP session/WebSession, Redis | Browser thứ hai thừa hưởng login hoặc `state` của test trước | Client/cookie jar/session mới cho từng test |
| **PKCE verifier, `state`, `nonce`** | Bộ nhớ của OAuth2 client / session | Dùng lại state/verifier khiến test không còn kiểm tra chống giả mạo thực sự | Sinh ngẫu nhiên cho mỗi authorization request, giữ trong đúng session |
| **Signing keys và JWKS** | JWK set, key vault, cấu hình AS | Token của môi trường/test khác được chấp nhận hoặc `kid`/cache gây nhiễu | Bộ khóa test riêng; kiểm soát vòng đời và JWKS cache |
| **Issuer, audience, redirect URI** | AS settings và client registration | Token từ môi trường khác được tin cậy, callback không khớp | Cấu hình issuer/redirect URI riêng cho test |
| **Thời gian, hạn token** | `Clock`, token settings, validator | Test chập chờn khi token sát hạn, thời gian trên các dịch vụ lệch | Clock có thể kiểm soát, thời hạn đủ xa, kiểm tra leeway có chủ đích |
| **Database/schema và cache** | JDBC/Redis | Dữ liệu ghi ở test A còn tồn tại khi B bắt đầu hoặc chạy song song | Database/schema/container/namespace độc lập, dọn theo run |

**Dữ liệu độc lập không đơn giản là đặt tên token khác nhau.** Nếu hai test dùng client ID riêng nhưng cùng bảng `oauth2_authorization`, cùng một principal và cùng một session, hành vi vẫn có thể ảnh hưởng lẫn nhau. Mỗi test cần xác định **tất cả trạng thái mà luồng đang đọc và ghi**.

Ví dụ tách ba danh tính:

~~~text
test A:
  clientId        = reporting-app-A
  principalName   = alice-test-A
  redirectUri     = http://127.0.0.1:9081/callback
  scope           = report.read
  sessionCookie   = session-A
  state           = random-state-A
  codeVerifier    = random-verifier-A

test B:
  clientId        = reporting-app-B
  principalName   = bob-test-B
  redirectUri     = http://127.0.0.1:9082/callback
  scope           = billing.read
  sessionCookie   = session-B
  state           = random-state-B
  codeVerifier    = random-verifier-B
~~~

Giá trị trong ví dụ là nhãn minh họa, không phải mật khẩu hoặc bearer token thật. Với các ca bảo mật, có thể **cố tình** cho client A gửi code của B hoặc dùng redirect URI của B để chứng minh AS từ chối vượt ranh giới. Điều quan trọng là sự kết hợp sai được tạo *có chủ đích*, không phải do dữ liệu rò từ test trước.

## 4. Chọn chiến lược reset phù hợp với nơi lưu dữ liệu

Có vài phương pháp, mỗi phương pháp đi kèm điều kiện:

1. **Tạo repository/service in-memory mới theo context hoặc test fixture.** Phù hợp với kiểm thử grant/HTTP nhanh; cần nhớ Spring Test thường cache `ApplicationContext` giữa các test, nên `@BeforeEach` **không tự tái tạo các singleton bean**.
2. **Dùng `@DirtiesContext` khi một test làm thay đổi trạng thái singleton.** Chẳng hạn `@DirtiesContext(classMode = AFTER_EACH_TEST_METHOD)` yêu cầu Spring tạo lại context sau mỗi test; đơn giản nhưng tốn thời gian.
3. **Dùng database test riêng và dọn có kiểm soát.** Có thể dùng Testcontainers, schema tách theo run hoặc transaction phù hợp. Với HTTP request chạy trên server thread khác, `@Transactional` trên phương thức test **không bảo đảm** rollback những ghi nhận đã commit trong request đó.
4. **Đặt namespace/khóa nhận diện theo run.** Tốt cho phép chạy song song, nhưng phải biết cách dọn đầy đủ token, authorization, consent, session và cache.
5. **Tạo một AS container/process mới cho từng nhóm test.** Chi phí lớn hơn, đổi lại ranh giới dữ liệu và cấu hình rõ. Khi tái sử dụng container giữa các test, vẫn cần chiến lược reset database và cache.

Đừng xóa toàn bộ bảng, xóa session Redis hoặc reset JWKS trên một môi trường đang được chia sẻ bởi tiến trình khác. Trong bộ test riêng, cleanup chỉ nên thao tác trên database/schema/namespace do test sở hữu.

Nếu test chạy song song, một fixture static mutable chứa `currentToken`, `currentUser` hoặc `currentSession` là nguồn lỗi phổ biến. `UUID.randomUUID()` chỉ giảm trùng định danh; nó không tạo sự cô lập cho singleton store, cookie jar hoặc thời gian giả lập có thể bị các test khác sửa chung.

## 5. Fixture Spring Authorization Server cho một môi trường kiểm thử độc lập

Spring Authorization Server có các interface lưu dữ liệu quan trọng:

- `RegisteredClientRepository` quản lý ứng dụng khách đã đăng ký.
- `OAuth2AuthorizationService` quản lý authorization, code/token và các trạng thái liên quan.
- `OAuth2AuthorizationConsentService` lưu quyết định đồng ý cấp quyền.

Ví dụ dưới đây tạo **các store riêng cho test**. Nó là một phần cấu hình của ứng dụng Spring Authorization Server đang kiểm thử; ứng dụng vẫn cần `SecurityFilterChain` của AS, `AuthorizationServerSettings`, token encoder/JWK thích hợp và phần xác thực người dùng nếu kiểm thử authorization code.

~~~java
import java.time.Duration;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.InMemoryOAuth2AuthorizationConsentService;
import org.springframework.security.oauth2.server.authorization.InMemoryOAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationConsentService;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.client.InMemoryRegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

@TestConfiguration(proxyBeanMethods = false)
class IsolatedAuthorizationServerStores {

    @Bean
    RegisteredClientRepository testRegisteredClients() {
        RegisteredClient allowed = RegisteredClient
            .withId("allowed-client-test-id")
            .clientId("allowed-client")
            .clientSecret("{noop}allowed-test-secret")
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                AuthorizationGrantType.CLIENT_CREDENTIALS)
            .scope("orders.read")
            .tokenSettings(TokenSettings.builder()
                .accessTokenTimeToLive(Duration.ofMinutes(10))
                .build())
            .build();

        RegisteredClient other = RegisteredClient
            .withId("other-client-test-id")
            .clientId("other-client")
            .clientSecret("{noop}other-test-secret")
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                AuthorizationGrantType.CLIENT_CREDENTIALS)
            .scope("metrics.read")
            .build();

        return new InMemoryRegisteredClientRepository(allowed, other);
    }

    @Bean
    OAuth2AuthorizationService testAuthorizationService() {
        return new InMemoryOAuth2AuthorizationService();
    }

    @Bean
    OAuth2AuthorizationConsentService testConsentService() {
        return new InMemoryOAuth2AuthorizationConsentService();
    }
}
~~~

Hãy gắn cấu hình test này với **một Spring Test context dành riêng** đã có AS filter chain, và tránh đồng thời tạo bean cùng loại từ cấu hình production. `{noop}` chỉ dùng cho secret giả trong ví dụ; hệ thống thật nên lưu client secret đã được hash và bảo vệ phù hợp. Client `client_credentials` ở đây không cần phiên đăng nhập người dùng hay consent; nhờ vậy có thể kiểm tra client authentication và phát hành token trước khi chuyển sang flow phức tạp hơn.

Để tái sử dụng context an toàn trong nhiều phương thức test, cần làm sạch state của `InMemoryOAuth2AuthorizationService` và consent store, hoặc dùng context mới theo từng test. Đặt hai `RegisteredClient` vào một bean singleton trong test **không có nghĩa** toàn bộ trạng thái AS sẽ tự động reset sau mỗi request.

## 6. MockMvc kiểm thử endpoint token của AS thật

Sau khi cấu hình Spring Authorization Server test context với fixture mục 5, có thể kiểm tra grant `client_credentials` bằng HTTP POST tới **endpoint thật của AS**. Ví dụ sau giả định đường token endpoint mặc định là `/oauth2/token` và test app đã nạp `IsolatedAuthorizationServerStores`.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@DirtiesContext(classMode =
    DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class AuthorizationServerClientCredentialsTest {

    @Autowired
    MockMvc mvc;

    @Test
    void registeredClientGetsAccessTokenForAllowedScope()
            throws Exception {
        mvc.perform(post("/oauth2/token")
                .with(httpBasic("allowed-client", "allowed-test-secret"))
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("grant_type", "client_credentials")
                .param("scope", "orders.read"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.access_token").isString())
            .andExpect(jsonPath("$.token_type").value("Bearer"));
    }

    @Test
    void wrongClientSecretIsRejected() throws Exception {
        mvc.perform(post("/oauth2/token")
                .with(httpBasic("allowed-client", "wrong-secret"))
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("grant_type", "client_credentials"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error").value("invalid_client"));
    }

    @Test
    void clientCannotRequestScopeItWasNotGranted() throws Exception {
        mvc.perform(post("/oauth2/token")
                .with(httpBasic("allowed-client", "allowed-test-secret"))
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("grant_type", "client_credentials")
                .param("scope", "metrics.read"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error").value("invalid_scope"));
    }

    @Test
    void anotherClientHasDifferentScopes() throws Exception {
        mvc.perform(post("/oauth2/token")
                .with(httpBasic("other-client", "other-test-secret"))
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("grant_type", "client_credentials")
                .param("scope", "metrics.read"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.access_token").isString());
    }
}
~~~

Đây là **mẫu test cần ghép với ứng dụng Spring Authorization Server đã cấu hình đúng**. `@SpringBootTest` tự tìm application class, còn `@TestConfiguration` mục 5 phải được import hoặc đưa vào đúng test context. Nếu ứng dụng đã dùng JDBC store, hãy cấu hình test profile để AS thực sự chọn store test trước khi chạy. Các kết quả HTTP theo hợp đồng OAuth2 trong ví dụ giả định endpoint/token handler mặc định; custom exception handlers có thể thay đổi body hoặc status.

Điều được kiểm chứng:

- AS xử lý `POST /oauth2/token` qua filter chain của Spring Authorization Server.
- Client có secret hợp lệ và scope được đăng ký nhận được token.
- Secret sai bị từ chối **trước khi** cấp token.
- Client không thể xin scope không được đăng ký.
- Hai client có policy scope khác nhau.

Điều **chưa** được kiểm chứng là TLS, HTTP socket ngoài JVM, JWT signature được Resource Server xác minh, key rotation, cookie trình duyệt hoặc authorization code + PKCE. `MockMvc` không gửi request tới một process AS bên ngoài, nhưng vẫn chạy security filter và logic grant/token của AS trong ứng dụng đang test.

### Tăng độ tin cậy bằng readback dữ liệu AS

Với các phép thử yêu cầu chứng minh token đã được lưu, inject `OAuth2AuthorizationService` của test context rồi đọc authorization tương ứng bằng `findByToken(tokenValue, tokenType)`. Hãy lấy `access_token` từ response và sử dụng đúng kiểu `OAuth2TokenType.ACCESS_TOKEN`:

~~~java
MvcResult result = mvc.perform(post("/oauth2/token")
        .with(httpBasic("allowed-client", "allowed-test-secret"))
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("grant_type", "client_credentials")
        .param("scope", "orders.read"))
    .andExpect(status().isOk())
    .andReturn();

String json = result.getResponse().getContentAsString();
String accessToken = objectMapper.readTree(json)
    .path("access_token").asText();

OAuth2Authorization authorization =
    authorizationService.findByToken(
        accessToken, OAuth2TokenType.ACCESS_TOKEN);

assertThat(authorization).isNotNull();
assertThat(authorization.getRegisteredClientId())
    .isEqualTo("allowed-client-test-id");
~~~

Đoạn mở rộng giả định test inject `ObjectMapper` và `OAuth2AuthorizationService`, đồng thời dùng các import `MvcResult`, `OAuth2Authorization`, `OAuth2TokenType` và AssertJ tương ứng. Đối với test phát hành JWT, có thể thêm phép thử Resource Server xác minh signature/issuer/audience của access token; readback lưu trữ và xác minh cryptographic là hai loại bằng chứng khác nhau.

Không ghi giá trị access token thực vào log hoặc ảnh chụp lỗi CI. Các token trong response test dù chỉ tồn tại ngắn vẫn nên được coi là dữ liệu xác thực trong phạm vi môi trường kiểm thử.

## 7. Authorization Code + PKCE: các trạng thái dễ ảnh hưởng lẫn nhau

Flow Authorization Code phức tạp hơn `client_credentials` vì có **browser session, đăng nhập người dùng, consent, authorization code dùng một lần, redirect URI, state và PKCE**.

Giả sử public client có:

~~~text
client_id                 = browser-client-test
redirect_uri              = http://127.0.0.1:9080/callback
response_type             = code
code_challenge_method     = S256
scope                     = openid profile
state                     = generated-per-request
nonce                     = generated-per-request (OIDC)
~~~

Để test thực sự đi qua AS, các bước cần diễn ra theo đúng thứ tự:

1. **Đăng ký client test** với `authorization_code`, redirect URI chính xác và yêu cầu PKCE; public client thường dùng `ClientAuthenticationMethod.NONE`, `requireProofKey(true)` và không dựa vào client secret.
2. **Sinh `code_verifier` mới cho từng authorization request** rồi tính `code_challenge = BASE64URL(SHA256(ASCII(code_verifier)))`. Giữ verifier riêng trong test client/session.
3. Gửi `GET /oauth2/authorize` với `client_id`, `redirect_uri`, `response_type=code`, `scope`, `state` và PKCE challenge. Đừng chỉ tự dựng một chuỗi code giả.
4. **Xác thực người dùng với AS** hoặc tạo principal có kiểm soát trong test. Nếu dùng `@WithMockUser`/`user()` tại bước này, đang bỏ qua lớp xác thực mật khẩu nhưng vẫn có thể kiểm tra phần xử lý grant của AS; phải mô tả giới hạn ấy.
5. Nếu server yêu cầu consent, hoàn tất consent bằng test fixture riêng và kiểm tra quyết định được lưu. Nếu muốn test màn hình đồng ý, không seed consent từ trước.
6. Nhận `302` về callback, kiểm tra redirect URI và `state`, sau đó **trích authorization code từ Location**, không gán code cố định.
7. Gửi `POST /oauth2/token` với code, redirect URI và **đúng `code_verifier`**; kiểm tra response token.
8. **Dùng lại code đã tiêu thụ** hoặc đổi verifier/redirect URI; AS phải từ chối theo điều kiện của OAuth2. Sau đó thử code của client A với client B để kiểm tra ranh giới client.

Code helper tạo PKCE dùng Java:

~~~java
record Pkce(String verifier, String challenge) {}

static Pkce newPkce() throws Exception {
    byte[] randomBytes = new byte[32];
    new SecureRandom().nextBytes(randomBytes);

    String verifier = Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(randomBytes);

    byte[] hash = MessageDigest.getInstance("SHA-256")
        .digest(verifier.getBytes(StandardCharsets.US_ASCII));

    String challenge = Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(hash);

    return new Pkce(verifier, challenge);
}
~~~

Một verifier mới mỗi ca và phép so khớp S256 giúp kiểm thử có ý nghĩa hơn việc dùng một verifier cố định cho tất cả các bài. Các import cần thiết gồm `java.security.SecureRandom`, `java.security.MessageDigest`, `java.nio.charset.StandardCharsets` và `java.util.Base64`. Không hardcode authorization code hoặc access token trong test flow; chúng do AS đang kiểm thử phát hành.

### Các ca negative quan trọng

| Tình huống | Kỳ vọng cần kiểm chứng |
| --- | --- |
| Dùng `code_verifier` sai | Token exchange bị từ chối |
| Dùng lại cùng authorization code | Code một lần không thể đổi token lần hai |
| Code được cấp cho client A nhưng dùng bởi client B | Token endpoint từ chối |
| Redirect URI khi đổi code khác URI ban đầu | Token endpoint từ chối theo policy/protocol |
| `state` callback khác request ban đầu | **OAuth2 Client** phải từ chối callback trước token exchange |
| User A đã consent nhưng user B chưa consent | Không coi consent của A là consent của B |
| Scope yêu cầu vượt client policy | AS từ chối hoặc giới hạn theo hợp đồng đã cấu hình |

**`state` thường do OAuth2 Client xác minh**, không phải một bảo đảm có thể kết luận chỉ bằng việc nhìn vào token endpoint của AS. `nonce` trong OIDC được client xác minh trong ID token theo protocol tương ứng. Khi test AS, cần kiểm tra AS gắn/khôi phục giá trị đúng; khi test client, cần kiểm tra client từ chối callback hoặc ID token không phù hợp. Không gộp hai vai trò thành một assertion mơ hồ.

## 8. Tạo test user và consent không phụ thuộc lần chạy trước

Trong Spring Authorization Server, quyền đồng ý cấp cho client thường gắn với cặp **registeredClientId + principalName**. Vì vậy:

~~~text
consent(alice, browser-client-test) != consent(bob, browser-client-test)
consent(alice, browser-client-A)    != consent(alice, browser-client-B)
~~~

Một test thử màn hình consent phải bắt đầu với **không có consent** cho đúng cặp principal/client. Sau khi lưu consent, test khác có thể chỉ được chuyển hướng cấp code mà không gặp consent nữa. Nếu hai test dùng chung in-memory service singleton hoặc database, kết quả sẽ phụ thuộc test nào chạy trước.

Tương tự, tạo người dùng `alice` chỉ trong test A nhưng reuse chính username và session ở test B có thể khiến B bỏ qua bước đăng nhập. Dùng session/cookie mới, user store test có reset, hoặc user riêng theo run nếu kịch bản đòi hỏi.

Khi mô phỏng lỗi:

- User bị khóa/vô hiệu hóa phải được từ chối ở **authentication của AS** nếu luồng thật đang dùng user store; việc đặt `@WithMockUser` không kiểm tra chính sách đó.
- Client secret sai liên quan đến **client authentication** ở token endpoint; không nhầm với mật khẩu người dùng.
- User không consent scope yêu cầu là vấn đề **authorization/consent**, không đồng nhất với lỗi signature JWT ở Resource Server.

Nếu ứng dụng dùng OIDC, những thông tin như `nonce`, `auth_time`, ID token claims, metadata provider và `jwks_uri` cũng có thể cần test độc lập. Tạo mới user, session và consent không thay thế việc kiểm tra chữ ký ID token hoặc audience của từng client.

## 9. Phân biệt token hợp lệ, đã thu hồi và khóa ký đã thay đổi

Một AS có thể phát hành **JWT self-contained** hoặc **opaque access token**. Phương pháp kiểm chứng chúng khác nhau:

| Loại token | Test trên AS | Test ở Resource Server |
| --- | --- | --- |
| JWT | AS phát hành token có chữ ký và claims phù hợp; JWK/`kid` đúng | Decoder xác minh chữ ký, issuer, audience, thời gian và authority |
| Opaque | AS lưu token/authorization và trả trạng thái introspection chính xác | RS gửi Bearer qua introspector, xử lý `active=true/false`, scope và lỗi |
| Refresh token | AS thực hiện refresh grant theo policy, có thể rotate và vô hiệu hóa token cũ | Resource Server thường không dùng refresh token làm Bearer để truy cập API |

**Thu hồi JWT** không tự động khiến mọi Resource Server đang chỉ kiểm tra chữ ký và `exp` từ chối ngay token ấy. Việc thu hồi token tại AS phải được phản ánh bằng cơ chế phù hợp ở RS (ví dụ introspection, denylist hoặc thời hạn ngắn), nếu nghiệp vụ yêu cầu hiệu lực tức thời. Test cần nêu rõ thiết kế đang áp dụng.

Khi kiểm tra JWKS hoặc luân chuyển khóa:

1. Tạo bộ khóa **chỉ cho môi trường test**, không dùng private key production.
2. Xác nhận AS ký bằng private key mong đợi và JWKS công bố public key tương ứng.
3. Dùng decoder thật của Resource Server trong test để kiểm tra token được xác minh.
4. Thử khóa không tin cậy hoặc `kid` lạ; kiểm tra bị từ chối theo chính sách.
5. Mô phỏng chuyển khóa và kiểm soát cache JWKS; tránh giả định RS đọc khóa mới ngay nếu cache chưa hết hạn.

Không đưa private key và refresh token vào log test/CI artifact. Nếu cần kiểm tra cấu hình issuer/`jwks_uri` ở môi trường chạy cổng ngẫu nhiên, đặt issuer nhất quán với AS đang test; không sao chép URL production để tạo thành công giả tạo.

## 10. Chạy kiểm thử trên HTTP thật và WebTestClient

Với Spring Authorization Server thường chạy trên Servlet stack, `MockMvc` đủ kiểm tra filter chain và grant logic trong JVM. Khi muốn kiểm tra HTTP socket, redirect, cookie hoặc cách client gọi một AS trên cổng riêng, có thể khởi động AS bằng `@SpringBootTest(webEnvironment = RANDOM_PORT)` rồi dùng một HTTP client có kiểm soát.

`WebTestClient` có hai cách sử dụng thường bị nhầm:

~~~java
// Bind tới một ứng dụng WebFlux đang nằm trong test context:
WebTestClient boundToApplication = WebTestClient
    .bindToApplicationContext(applicationContext)
    .apply(springSecurity())
    .build();

// Thực sự tạo HTTP request tới AS đang chạy trên một cổng:
WebTestClient httpClient = WebTestClient
    .bindToServer()
    .baseUrl("http://127.0.0.1:" + port)
    .build();

httpClient.post()
    .uri("/oauth2/token")
    .headers(h -> h.setBasicAuth(
        "allowed-client", "allowed-test-secret"))
    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
    .body(BodyInserters.fromFormData(
        "grant_type", "client_credentials")
        .with("scope", "orders.read"))
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.access_token").isNotEmpty();
~~~

Đoạn `bindToApplicationContext` chỉ phù hợp với **WebFlux application context** và yêu cầu cấu hình `springSecurity()` tương ứng; nó không tự biến Servlet AS thành WebFlux. Đoạn `bindToServer` là HTTP client, có thể gửi tới **Servlet AS** thực sự đang chạy nếu `port` là cổng test server. Cần dependency Spring WebFlux ở test classpath cho `WebTestClient`/`BodyInserters` dù AS ở phía server dùng Servlet.

Nếu không muốn kéo WebFlux dependency vào test cho một Servlet AS, dùng `TestRestTemplate`, `RestClient`, Java `HttpClient` hoặc một HTTP client phù hợp để gửi form token request. Kết quả cần kiểm tra vẫn là status, response schema, client authentication, token lifecycle và dữ liệu phía AS.

Đối với OIDC authorize/login qua browser, hãy cân nhắc một browser test thực trên môi trường riêng để kiểm tra cookie, redirect và màn hình consent. `MockMvc` vẫn tốt để kiểm tra các điều kiện giao thức tách nhỏ; hai loại kiểm thử bổ sung cho nhau.

## 11. Kiểm soát thời gian và tính tái lập của dữ liệu

Authorization code, access token, refresh token và session đều có thời hạn. Các test dễ chập chờn khi:

- Sử dụng `Instant.now()` gần ngay mốc hết hạn.
- Chạy chậm trên CI khiến code/token đã hết hạn trước assertion.
- AS và RS dùng hai clock khác nhau mà không kiểm soát.
- Test thời gian sửa global/system clock hoặc một fake clock dùng chung.
- Làm mới token ở test trước khiến refresh token cũ bị vô hiệu trong test sau.

Ưu tiên inject một `Clock` hoặc cơ chế test clock có thể kiểm soát nếu thành phần ứng dụng hỗ trợ. Với JWT decoder và các validator có clock riêng, phải cấu hình cùng ý nghĩa thời gian hoặc dùng token có khoảng hiệu lực đủ xa. Đừng chỉ dùng `Thread.sleep(...)` lâu rồi hy vọng test qua; sleep làm chậm CI và không bảo đảm chính xác khi load cao.

Một fixture tốt nên xác định rõ `issuedAt`, `expiresAt` và `clockSkew`. Khi kiểm tra chính sách hết hạn, dùng các mốc nằm rõ hai phía thời điểm hết hạn, không chọn mốc sát ranh giới. Với authorization code một lần, kiểm tra **tiêu thụ lại code** mà không cần chờ code hết hạn để phân biệt hai cơ chế.

## 12. Checklist kiểm thử ranh giới và dữ liệu độc lập

| Nhóm | Ca kiểm thử cốt lõi | Dữ liệu cần cô lập |
| --- | --- | --- |
| Client authentication | Đúng/sai client secret, client không tồn tại, grant bị cấm | Client ID, secret, grant policy |
| Scope | Scope được phép, scope vượt đăng ký, nhiều scope | RegisteredClient, principal, consent |
| Authorization code | Đổi code thành token, dùng lại code, code thuộc client khác | Authorization store, code, client, redirect URI |
| PKCE | Đúng/sai verifier, thiếu challenge khi client bắt buộc PKCE | Verifier, challenge, authorization request |
| Login/Consent | User có/không có quyền, user A/B consent riêng | User store, session, consent service |
| Token lifecycle | Cấp mới, refresh, rotate, revoke, introspect | Authorization store, token, clock |
| OIDC | `nonce`, ID token, claims, issuer/audience, JWKS | Client registration, user, signing keys, issuer |
| Resource Server | JWT/opaque hợp lệ, invalid, thiếu scope | Decoder/introspector, keys, RS policy |
| Session/Redirect | `state`, cookie, callback URI, CSRF | Browser session, client state |
| Chạy song song | Test A và B không tác động lẫn nhau | Database/schema, cache, keys, namespace |

Một số tình huống dễ bị bỏ sót:

**Test A cấp code, test B dùng lại code.** Kết quả B phụ thuộc thứ tự chạy và thậm chí có thể trả lỗi `invalid_grant` vì code A đã bị tiêu thụ. Cần để từng ca tự tạo code qua luồng authorization.

**Test consent dùng lại user/client cố định.** Nếu consent từ test trước còn tồn tại, test sau có thể bỏ qua màn hình cấp quyền và thất bại khi chờ redirect tới trang consent. Hãy reset consent hoặc tạo cặp client/principal riêng.

**Chỉ dùng `jwt()` rồi tuyên bố AS đã ký đúng.** `jwt()` giả lập authentication ở RS; không gửi token do AS ký qua decoder. Muốn chứng minh chữ ký, phải lấy JWT do AS phát hành rồi cho decoder kiểm tra.

**Lưu client secret vào repository dùng chung CI.** Test tạo một registration mới nhưng không dọn nó sẽ khiến những run sau có thể tìm thấy cùng client, hoặc test khác bất ngờ được cấp scope mới. Dùng môi trường/namespace riêng và cleanup có thể kiểm chứng.

**Dùng `@Transactional` cho test HTTP và cho rằng rollback đã xóa dữ liệu server.** HTTP request chạy ở transaction khác có thể commit độc lập. Hãy kiểm tra thực tế nơi dữ liệu đã được ghi; sử dụng reset/schema/container riêng nếu cần.

**Gọi “end-to-end” khi mọi bước đều là mock.** Test mock có giá trị cho behavior của client/RS nhưng không phải bằng chứng AS thực sự chấp nhận grant, xác thực client hay quản lý one-time code.

**Tạo issuer và redirect URI theo môi trường rồi bỏ qua mismatch.** Redirect URI phải được đăng ký/so khớp theo protocol; issuer/audience cần nhất quán giữa AS và client/RS. Không nới lỏng validation chỉ để test đi qua.

## 13. Bài tập thực hành

1. Tạo hai `RegisteredClient` riêng cho `client_credentials` với scope `orders.read` và `metrics.read`. Dùng MockMvc gọi `/oauth2/token`, chứng minh mỗi client chỉ xin được scope đã đăng ký.
2. Dùng `InMemoryOAuth2AuthorizationService` của test context đọc lại token đã phát hành; so sánh `registeredClientId` với client được xác thực. Thử token của client B với chính sách cấp cho A và xác nhận ranh giới.
3. Chạy cùng test với `@DirtiesContext(AFTER_EACH_TEST_METHOD)`, rồi thử chiến lược database/schema riêng. Ghi lại dữ liệu nào tồn tại sau mỗi phương thức và tại sao.
4. Tạo public client yêu cầu PKCE. Thực hiện authorization code flow với `code_verifier`/`code_challenge` được sinh riêng; kiểm tra đổi code thành công, code sai verifier và code dùng hai lần đều bị từ chối.
5. Seed consent cho Alice nhưng không seed cho Bob đối với cùng client. Đảm bảo luồng authorize của Bob vẫn yêu cầu consent theo chính sách test.
6. Đặt test token có hạn phù hợp và kiểm tra RS chấp nhận JWT do AS ký bằng khóa test. Đổi issuer hoặc public key trên RS để quan sát `401`.
7. Gửi HTTP request tới AS trên cổng ngẫu nhiên bằng `WebTestClient.bindToServer()` hoặc HTTP client khác; so sánh với MockMvc về việc kiểm tra transport, cookie và redirect.
8. Chạy hai bộ test song song trên môi trường test có namespace khác nhau. Thêm các assertion bảo đảm user, client, token và consent của run A không xuất hiện trong kết quả run B.
9. Giả lập lỗi token endpoint hoặc introspection endpoint nếu hệ thống có thành phần ngoài. Ghi rõ đang kiểm thử **AS**, **client** hay **resource server** ở mỗi ca, tránh nhận nhầm phạm vi chứng cứ.

### Tiêu chí hoàn thành

Một bộ kiểm thử đáng tin cậy cần ghi rõ **điểm vào hệ thống**, **thành phần được chạy thật**, **thành phần được giả lập** và **dữ liệu nào được reset**. Khi test một authorization server, hãy kiểm tra thêm trạng thái được tạo ra: registered client, authorization code, consent, access/refresh token, signing key, session và issuer. Chỉ khi những ranh giới này được kiểm soát, các kết quả `200`, `302`, `401` hay `403` mới phản ánh đúng tính năng cần kiểm chứng.

### Tài liệu tham khảo

- [Spring Authorization Server — Reference](https://docs.spring.io/spring-authorization-server/reference/)
- [Spring Security — Testing OAuth2](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html)
- [Spring Security — Reactive WebTestClient Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html)
- [OAuth 2.0 Authorization Framework — RFC 6749](https://www.rfc-editor.org/rfc/rfc6749)
- [Proof Key for Code Exchange (PKCE) — RFC 7636](https://www.rfc-editor.org/rfc/rfc7636)
