# Lỗi consent, code không hợp lệ, callback lặp và token endpoint thất bại trong luồng OAuth2 thực

Trong một ứng dụng đăng nhập bằng OAuth2 hoặc OpenID Connect (OIDC), test `.with(oauth2Login())` hay `.with(oidcLogin())` có thể nhanh chóng tạo một người dùng đã đăng nhập. Tuy nhiên, các test đó **không thực hiện authorization redirect, không nhận authorization code từ trình duyệt và không trao đổi code lấy token**. Vì vậy, chúng không phát hiện được lỗi người dùng từ chối consent, code hết hạn, callback bị phát lại hoặc lỗi từ token endpoint.

Đây là nội dung của chương **Luồng OAuth2 thực** trong module **`SPRING_SECURITY_TESTING`**, nơi người học kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng Spring Security Test trên Servlet và Reactive. Bài này tập trung vào **luồng Authorization Code có redirect thật qua các Spring Security filters** và **nhà cung cấp định danh giả lập qua HTTP**, để mô phỏng các tình huống lỗi mà không phụ thuộc tài khoản hoặc mạng của IdP bên ngoài.

Sau bài này, bạn sẽ có thể:

- Phân biệt giai đoạn **authorization request/consent**, **callback**, **trao đổi code lấy token** và **tạo Authentication/phiên**.
- Kiểm tra đúng vai trò của `state`, session, authorization code dùng một lần, PKCE (`code_verifier`) và `nonce` của OIDC.
- Dùng `MockMvc` và một HTTP stub server như WireMock để mô phỏng `access_denied`, `invalid_grant`, callback lặp và `temporarily_unavailable`.
- Đọc mã HTTP, `Location`, trạng thái đăng nhập và số lượt gọi token endpoint để biết lỗi xuất hiện ở bước nào.
- Hiểu vì sao một response `302` không tự chứng minh đăng nhập thành công và vì sao các helper `oauth2Login()`/`oidcLogin()` không thay thế các test luồng thực.

## 1. Luồng Authorization Code và các điểm có thể thất bại

Trong Spring Security Servlet, URL bắt đầu đăng nhập thường là `/oauth2/authorization/{registrationId}`; callback mặc định thường là `/login/oauth2/code/{registrationId}`. Các URL này có thể thay đổi theo cấu hình `authorizationEndpoint(...)` hoặc `redirectionEndpoint(...)`.

```mermaid
sequenceDiagram
    participant B as Browser / MockMvc
    participant C as OAuth2 Client (Spring Security)
    participant P as Authorization Server (IdP)
    B->>C: GET /oauth2/authorization/demo
    C->>C: Tạo state, lưu OAuth2AuthorizationRequest trong session
    C-->>B: 302 Location: /authorize?...&state=...
    B->>P: Mở authorization URL, đăng nhập và xác nhận consent
    alt Consent bị từ chối
        P-->>B: Redirect callback?error=access_denied&state=...
        B->>C: GET callback với error và state
        C-->>B: Login failure theo failure handler
    else Consent được chấp nhận
        P-->>B: Redirect callback?code=...&state=...
        B->>C: GET callback với code và state
        C->>C: Tìm authorization request theo state/session
        C->>P: POST token endpoint với authorization_code
        alt Token exchange thất bại
            P-->>C: OAuth2 error (invalid_grant, temporarily_unavailable...)
            C-->>B: Login failure theo failure handler
        else Token exchange thành công
            P-->>C: access_token (và id_token nếu OIDC)
            C->>C: Xử lý user/ID token; tạo Authentication
            C-->>B: 302 Location: success URL
        end
    end
```

Ở tầng Servlet, các thành phần chính gồm:

| Thành phần | Công việc |
| --- | --- |
| `OAuth2AuthorizationRequestRedirectFilter` | Tạo authorization request và redirect người dùng tới IdP |
| `OAuth2AuthorizationRequestRepository` | Lưu request ban đầu cùng `state`, mặc định thường gắn với HTTP session |
| `OAuth2LoginAuthenticationFilter` | Nhận callback thành công hoặc lỗi; đối chiếu request trước đó |
| `OAuth2AuthorizationCodeAuthenticationProvider` | Đổi authorization code lấy access token cho OAuth2 Login |
| `OAuth2AccessTokenResponseClient` | Gửi yêu cầu HTTP đến token endpoint và xử lý response |
| `OidcAuthorizationCodeAuthenticationProvider` | Xử lý nhánh OIDC, bao gồm kiểm tra ID token và lấy thông tin user phù hợp |
| `AuthenticationSuccessHandler` / `AuthenticationFailureHandler` | Chọn redirect hoặc phản hồi sau khi xác thực thành công/thất bại |

**Ba dữ liệu không thể hoán đổi:**

- `state` liên kết authorization request với callback, giúp chống CSRF/login CSRF và nhầm request. Test phải lấy `state` thực từ redirect rồi gửi lại cùng session.
- `code` là authorization code ngắn hạn, **chỉ được đổi lấy token một lần** theo quy tắc Authorization Server. Callback chứa code chưa đồng nghĩa xác thực đã thành công.
- `nonce` trong OIDC giúp liên kết ID token với yêu cầu đăng nhập OIDC trước đó. Nó không thay thế `state`. Với các client dùng PKCE, `code_challenge`/`code_verifier` còn ràng buộc token exchange với authorization request ban đầu.

## 2. Bốn nhánh lỗi và các kết quả cần quan sát

| Tình huống | Dấu hiệu ở đầu vào | Bước lỗi | Điều cần xác minh |
| --- | --- | --- | --- |
| Người dùng từ chối consent | Callback có `error=access_denied`, `state` | Authorization endpoint / callback | Không có token exchange; chạy failure handler; không tạo login mới |
| Authorization code không hợp lệ/hết hạn/đã dùng | Callback có `code` và `state` hợp lệ; token endpoint trả `invalid_grant` | Token exchange | Có POST token endpoint; không có `Authentication` thành công |
| Callback được gọi lại | Cùng `code` và `state` xuất hiện lần hai | Request correlation hoặc token exchange | Authorization request đã bị tiêu thụ; không tạo lần login thứ hai |
| Token endpoint lỗi | Timeout/network hoặc HTTP 5xx / OAuth2 `temporarily_unavailable` | Back-channel token request | Không xác thực thành công; phân biệt lỗi hạ tầng với `invalid_grant` |

Trong cấu hình browser login mặc định, nhiều lỗi được **redirect về trang login kèm thông báo lỗi**, chẳng hạn `302 Location: /login?error`. Đó là kết quả của **failure handler**, không phải status mà IdP trả về. Ứng dụng có thể chọn custom failure handler để trả JSON 4xx/5xx; vì vậy test phải theo cấu hình của chính ứng dụng.

Những mã lỗi OAuth2 như `access_denied`, `invalid_grant`, `invalid_request`, `temporarily_unavailable` là **giá trị trường `error` trong giao thức**. Chúng không phải lúc nào cũng trùng với HTTP status của callback response. Một token endpoint có thể trả HTTP 400 với JSON `{"error":"invalid_grant"}`, trong khi browser chỉ nhìn thấy redirect `302` về login sau khi Spring xử lý lỗi.

## 3. Thiết kế môi trường test: filter thật, IdP HTTP giả lập

Một test luồng tương đối sát thực tế nên giữ các thành phần sau:

1. Spring Security filter chain, `ClientRegistrationRepository` và OAuth2 Login config thật trong test context.
2. `MockMvc` gọi endpoint bắt đầu authorization và callback theo cùng session.
3. HTTP stub server đóng vai IdP, có authorization URI dùng để sinh redirect; token endpoint và user-info endpoint trả response theo kịch bản.
4. Assertion HTTP trên application **và** assertion số lần/chi tiết request đi tới stub token endpoint.

Không cần mở trình duyệt thật trong các test này. MockMvc chủ động mô phỏng hai lượt HTTP ở phía browser; HTTP stub server nhận back-channel request từ Spring Security khi đổi code lấy token.

Các dependency điển hình cho Java 17+, Spring Boot 3.x, Spring Security 6.x:

```text
Implementation:
  spring-boot-starter-web
  spring-boot-starter-security
  spring-boot-starter-oauth2-client

Test:
  spring-boot-starter-test
  spring-security-test
  WireMock 3.x (ví dụ org.wiremock:wiremock-standalone, phiên bản phù hợp)
```

Để tập trung vào lỗi Authorization Code, ví dụ dưới đây dùng một **OAuth2 Login provider thông thường**, không yêu cầu OIDC `id_token`. Phần OIDC sẽ được phân tích riêng ở mục 8 vì cần thêm xác minh chữ ký, issuer, audience và nonce. Các URL `localhost`/`example.test` và credentials bên dưới chỉ dùng trong test.

## 4. Ví dụ tích hợp MockMvc + WireMock

Ví dụ minh họa một lớp test có application context riêng với endpoint `/private`, filter chain `oauth2Login()` và registration `demo`. Test bắt đầu bằng `GET /oauth2/authorization/demo`, lấy **state và session thật**, sau đó gọi callback với response do IdP giả lập cung cấp.

### 4.1. Khởi tạo ứng dụng test và ClientRegistration

```java
import com.github.tomakehurst.wiremock.WireMockServer;
import com.github.tomakehurst.wiremock.client.WireMock;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.UriComponentsBuilder;

import static com.github.tomakehurst.wiremock.client.WireMock.aResponse;
import static com.github.tomakehurst.wiremock.client.WireMock.containing;
import static com.github.tomakehurst.wiremock.client.WireMock.postRequestedFor;
import static com.github.tomakehurst.wiremock.client.WireMock.urlEqualTo;
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.wireMockConfig;
import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(classes = OAuth2FlowFailuresTest.TestApplication.class)
@AutoConfigureMockMvc
class OAuth2FlowFailuresTest {

    private static final WireMockServer idp = startIdp();

    private static WireMockServer startIdp() {
        WireMockServer server =
                new WireMockServer(wireMockConfig().dynamicPort());
        server.start();
        return server;
    }

    @Autowired
    MockMvc mvc;

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import({SecurityConfig.class, ProviderConfig.class, PrivateEndpoint.class})
    static class TestApplication {}

    @Configuration(proxyBeanMethods = false)
    static class ProviderConfig {

        @Bean
        ClientRegistrationRepository registrations() {
            ClientRegistration demo = ClientRegistration
                    .withRegistrationId("demo")
                    .clientId("demo-client")
                    .clientSecret("test-only-client-secret")
                    .clientAuthenticationMethod(
                            ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                    .authorizationGrantType(
                            AuthorizationGrantType.AUTHORIZATION_CODE)
                    .redirectUri(
                            "{baseUrl}/login/oauth2/code/{registrationId}")
                    .authorizationUri(idp.baseUrl() + "/authorize")
                    .tokenUri(idp.baseUrl() + "/token")
                    .userInfoUri(idp.baseUrl() + "/userinfo")
                    .userNameAttributeName("sub")
                    .scope("profile")
                    .clientName("Demo IdP")
                    .build();
            return new InMemoryClientRegistrationRepository(demo);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class SecurityConfig {
        @Bean
        SecurityFilterChain testSecurity(HttpSecurity http)
                throws Exception {
            return http
                    .authorizeHttpRequests(auth -> auth
                            .requestMatchers("/login", "/error").permitAll()
                            .anyRequest().authenticated())
                    .oauth2Login(login -> login
                            .defaultSuccessUrl("/private", true)
                            .failureUrl("/login?error"))
                    .build();
        }
    }

    @RestController
    static class PrivateEndpoint {
        @GetMapping("/private")
        String privateData(Authentication authentication) {
            return "Hello " + authentication.getName();
        }
    }

    @BeforeEach
    void resetIdp() {
        idp.resetAll();
    }

    @AfterAll
    static void stopIdp() {
        idp.stop();
    }

    record StartedLogin(MockHttpSession session, String state) {}

    private StartedLogin beginLogin() throws Exception {
        MvcResult launched = mvc.perform(
                    get("/oauth2/authorization/demo"))
                .andExpect(status().isFound())
                .andExpect(header().string(
                        HttpHeaders.LOCATION, containsString("/authorize?")))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) launched.getRequest().getSession(false);
        String redirect = launched.getResponse().getRedirectedUrl();
        String state = UriComponentsBuilder
                .fromUriString(redirect)
                .build()
                .getQueryParams()
                .getFirst("state");

        assertThat(session).isNotNull();
        assertThat(state).isNotBlank();
        return new StartedLogin(session, state);
    }

    private MockHttpServletRequestBuilder callback(
            StartedLogin started, String code) {
        return get("/login/oauth2/code/demo")
                .session(started.session())
                .param("code", code)
                .param("state", started.state());
    }

    // Các @Test được đặt tiếp trong cùng lớp.
}
```

Trong Java, những đoạn `@Test` ở các mục tiếp theo được đặt **bên trong `OAuth2FlowFailuresTest` trước dấu `}` cuối của lớp**. Đây là một bộ khung để ghép vào project test; các lớp cấu hình nested chỉ phục vụ bài tập.

**Điểm chủ chốt:** `beginLogin()` không tự nghĩ ra state; nó lấy giá trị từ redirect thật của `OAuth2AuthorizationRequestRedirectFilter` rồi giữ `MockHttpSession`. Trong ứng dụng mặc định, `HttpSessionOAuth2AuthorizationRequestRepository` lưu authorization request ở session đó. Callback dùng state khác hoặc không mang session sẽ không tìm được request thích hợp. Các test không nên hardcode state, bỏ session hay tự dựng `OAuth2AuthenticationToken` rồi khẳng định đã kiểm thử luồng thực.

Client registration dùng `scope("profile")` và `userInfoUri(...)` để sau khi nhận access token, `DefaultOAuth2UserService` có thể lấy thông tin người dùng tại `/userinfo`. Nếu dùng một IDP chỉ phục vụ OIDC với scope `openid` thì còn phải xử lý `id_token` và các quy tắc OIDC khác.

### 4.2. Consent bị từ chối: không có bước đổi code lấy token

Người dùng bấm “Cancel” hoặc từ chối chia sẻ quyền trên màn hình consent của IdP. Theo OAuth2, IdP trả trình duyệt về `redirect_uri` với lỗi:

```http
GET /login/oauth2/code/demo?error=access_denied&state=<state-da-phat>
```

Test:

```java
@Test
void consentDenied_redirectsToFailureWithoutTokenExchange()
        throws Exception {
    StartedLogin started = beginLogin();

    mvc.perform(get("/login/oauth2/code/demo")
                    .session(started.session())
                    .param("error", "access_denied")
                    .param("error_description", "User denied consent")
                    .param("state", started.state()))
            .andExpect(status().isFound())
            .andExpect(redirectedUrl("/login?error"));

    idp.verify(0, postRequestedFor(urlEqualTo("/token")));
}
```

Đây là lỗi **front-channel authorization response**, do đó **không có authorization code để trao đổi** và token endpoint không được gọi. Việc xác thực thất bại được ánh xạ qua `AuthenticationFailureHandler`; ví dụ đã cấu hình rõ `failureUrl("/login?error")`.

Kiểm tra thêm trên ứng dụng thực: giao diện không nên coi lỗi consent là sự cố mật khẩu; client có thể hiển thị thông báo từ chối cấp quyền hoặc cho phép người dùng thử lại. Không log/access token vì không có token. `error_description` do IdP cung cấp là dữ liệu bên ngoài: không hiển thị nguyên văn không kiểm soát vào HTML.

### 4.3. Authorization code sai hoặc hết hạn: token endpoint trả `invalid_grant`

IdP đã redirect callback thành công về mặt URL, nhưng token endpoint từ chối authorization code. Theo OAuth2, các lý do có thể là code sai, hết hạn, đã sử dụng hoặc không khớp client/redirect URI/PKCE verifier.

HTTP giả lập từ token endpoint:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "invalid_grant",
  "error_description": "Authorization code invalid, expired or already used"
}
```

Test:

```java
@Test
void invalidCode_failsAfterCallingTokenEndpoint()
        throws Exception {
    idp.stubFor(WireMock.post(urlEqualTo("/token"))
            .willReturn(aResponse()
                    .withStatus(400)
                    .withHeader("Content-Type", "application/json")
                    .withBody(
                        "{\"error\":\"invalid_grant\","
                        + "\"error_description\":\"code rejected\"}")));

    StartedLogin started = beginLogin();

    mvc.perform(callback(started, "code-invalid"))
            .andExpect(status().isFound())
            .andExpect(redirectedUrl("/login?error"));

    idp.verify(1, postRequestedFor(urlEqualTo("/token")));
}
```

Lúc này **callback có state đúng và đã được xử lý**, khác với nhánh consent denial. Spring Security mới thực hiện HTTP POST đến token endpoint và thất bại khi nhận OAuth2 error. Đừng chỉ assert `302`: cả redirect login thành công lẫn redirect lỗi đều có thể là 302. Cần thêm `redirectedUrl("/login?error")` và `verify(1, token POST)`.

`invalid_grant` là mã lỗi trong response OAuth2, không phải một HTTP status riêng. Không nên dịch nó thành 403 “thiếu quyền”: ứng dụng chưa tạo phiên đăng nhập hợp lệ; đây là **authentication failure**, không phải authorization failure sau đăng nhập.

### 4.4. Callback lặp sau khi đăng nhập thành công

Authorization code là dữ liệu sử dụng một lần. Ngoài ra, authorization request được lưu bởi client thường bị **lấy ra và loại khỏi repository trong lần xử lý callback đầu tiên**. Vì vậy một callback giống hệt gửi lần hai có thể thất bại ngay ở bước lấy lại authorization request, **trước khi** cố đổi code thêm lần nữa.

Để mô phỏng một lượt đăng nhập thành công trước khi phát lại callback, stub hai HTTP endpoint:

```java
private void stubSuccessfulProvider() {
    idp.stubFor(WireMock.post(urlEqualTo("/token"))
            .willReturn(aResponse()
                    .withStatus(200)
                    .withHeader("Content-Type", "application/json")
                    .withBody(
                        "{\"access_token\":\"token-for-tests\","
                        + "\"token_type\":\"Bearer\","
                        + "\"expires_in\":600,"
                        + "\"scope\":\"profile\"}")));

    idp.stubFor(WireMock.get(urlEqualTo("/userinfo"))
            .willReturn(aResponse()
                    .withStatus(200)
                    .withHeader("Content-Type", "application/json")
                    .withBody(
                        "{\"sub\":\"alice\",\"name\":\"Alice\"}")));
}
```

Sau đó:

```java
@Test
void callbackReplay_isRejected_withoutAnotherTokenExchange()
        throws Exception {
    stubSuccessfulProvider();
    StartedLogin started = beginLogin();

    MvcResult first = mvc.perform(callback(started, "code-once"))
            .andExpect(status().isFound())
            .andExpect(redirectedUrl("/private"))
            .andReturn();

    // Sau login có thể xảy ra session fixation protection;
    // lấy session sau callback thay vì cứng nhắc dùng session cũ.
    MockHttpSession afterLogin =
            (MockHttpSession) first.getRequest().getSession(false);
    assertThat(afterLogin).isNotNull();

    mvc.perform(get("/private").session(afterLogin))
            .andExpect(status().isOk())
            .andExpect(content().string("Hello alice"));

    mvc.perform(get("/login/oauth2/code/demo")
                    .session(afterLogin)
                    .param("code", "code-once")
                    .param("state", started.state()))
            .andExpect(status().isFound())
            .andExpect(redirectedUrl("/login?error"));

    idp.verify(1, postRequestedFor(urlEqualTo("/token")));
}
```

Assertion có ý nghĩa nhất là **hai callback nhưng chỉ một token exchange**. Lần thứ hai không có authorization request tương ứng để tiếp tục. Với callback thành công lần đầu, browser có thể đang giữ phiên đăng nhập; việc callback lặp bị báo lỗi **không nhất thiết chứng minh phiên đầu tiên đã bị thu hồi**. Phải tách rõ: “callback lặp không tạo một giao dịch xác thực thành công mới” và “session hiện tại có còn xác thực hay không” là hai điều kiện kiểm thử khác nhau.

Có một kịch bản khác: trình duyệt **bắt đầu một authorization request mới** với state mới, nhưng cố dùng lại **code đã tiêu thụ**. Lúc đó Spring Security vẫn tìm được authorization request mới, gửi code sang token endpoint và **IdP phải trả `invalid_grant`** do code một lần. Đây là kiểm thử nghĩa vụ của Authorization Server, có thể được mô phỏng bằng stub `invalid_grant` như mục 4.3.

### 4.5. Token endpoint thất bại do HTTP 503

Token endpoint có thể không khả dụng dù authorization code và state đều đúng. Ví dụ trả response OAuth2 error có cấu trúc:

```http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json

{
  "error": "temporarily_unavailable",
  "error_description": "Token service is temporarily unavailable"
}
```

Trong cấu hình/phiên bản mà token client chuyển response lỗi OAuth2 này thành `OAuth2AuthorizationException`, failure handler của OAuth2 Login được kích hoạt:

```java
@Test
void tokenEndpointOAuthError_doesNotCreateLogin()
        throws Exception {
    idp.stubFor(WireMock.post(urlEqualTo("/token"))
            .willReturn(aResponse()
                    .withStatus(503)
                    .withHeader("Content-Type", "application/json")
                    .withBody(
                        "{\"error\":\"temporarily_unavailable\","
                        + "\"error_description\":\"upstream unavailable\"}")));

    StartedLogin started = beginLogin();

    mvc.perform(callback(started, "code-valid-but-upstream-down"))
            .andExpect(status().isFound())
            .andExpect(redirectedUrl("/login?error"));

    idp.verify(1, postRequestedFor(urlEqualTo("/token")));
}
```

**Giới hạn của assertion:** không phải mọi lỗi token endpoint đều có cùng đường xử lý. Socket timeout, DNS failure, TLS error, HTTP 500 không có body OAuth2 hợp lệ hoặc response không đọc được có thể đi qua exception khác tùy `OAuth2AccessTokenResponseClient` và Spring Security version. Với nhánh timeout/network, hãy xác nhận contract của ứng dụng rồi kiểm tra kết quả phù hợp: có thể là redirect login error, một response lỗi 5xx đã được handler ánh xạ hoặc một exception để tầng khác xử lý. Không tự khẳng định “mọi lỗi IdP đều thành 302” và cũng không biến lỗi mạng thành “mật khẩu/token của người dùng sai”.

Ứng dụng nên **fail closed**: khi không đổi được authorization code thành token hợp lệ, không tạo Authentication mới đã được chứng thực. Retry tự động token exchange cũng cần cân nhắc: code dùng một lần có thể đã bị IdP tiêu thụ trước khi client gặp lỗi đọc response; gửi lại cùng code có thể nhận `invalid_grant`.

## 5. Dùng đúng session, state và saved request trong test

Các lỗi nhầm lẫn phổ biến đều bắt nguồn từ việc mô phỏng thiếu context của browser. Hãy giữ ba dữ liệu riêng biệt:

| Dữ liệu | Lấy ở đâu? | Dùng ở đâu? |
| --- | --- | --- |
| `MockHttpSession` | Từ request bắt đầu `/oauth2/authorization/demo` | Truyền vào callback qua `.session(session)` |
| `state` | Từ query string của header `Location` redirect tới IdP | Gửi lại nguyên vẹn qua callback `.param("state", state)` |
| `code` | IdP cấp khi người dùng chấp nhận consent | Gửi trong callback; Spring dùng nó để gọi token endpoint |

Ví dụ một callback mất session:

```java
StartedLogin started = beginLogin();

// Không gửi session đã lưu authorization request.
mvc.perform(get("/login/oauth2/code/demo")
                .param("code", "any-code")
                .param("state", started.state()))
        .andExpect(status().isFound())
        .andExpect(redirectedUrl("/login?error"));

idp.verify(0, postRequestedFor(urlEqualTo("/token")));
```

Theo repository mặc định gắn session, lỗi sẽ xảy ra **trước token endpoint** vì không tìm thấy authorization request. Nếu ứng dụng dùng cookie repository hoặc repository phân tán tùy biến, cần điều chỉnh test để mang đúng dữ liệu tương ứng.

Callback có `state` sai cũng phải bị từ chối trước khi trao đổi code trong cấu hình chuẩn:

```java
StartedLogin started = beginLogin();

mvc.perform(get("/login/oauth2/code/demo")
                .session(started.session())
                .param("code", "any-code")
                .param("state", "tampered-state"))
        .andExpect(status().isFound())
        .andExpect(redirectedUrl("/login?error"));

idp.verify(0, postRequestedFor(urlEqualTo("/token")));
```

Trong trường hợp state không khớp, việc repository có giữ hay xóa request ban đầu sau callback lỗi phụ thuộc implementation. Bài test nên kiểm tra **không có token exchange và không có login mới**; đừng suy diễn cơ chế cleanup nội bộ nếu đó không phải hợp đồng được thiết kế cần bảo đảm.

### Vì sao cần giữ session *sau* login?

Spring Security có thể đổi session ID khi xác thực thành công nhằm chống session fixation. Nếu test gọi tiếp `GET /private` bằng một session cũ đã bị thay thế/invalidated, lỗi test có thể xuất phát từ cách mô phỏng browser, không phải từ OAuth2. Dùng session từ `MvcResult` của callback thành công (hoặc cơ chế cookie/HTTP client được quản lý phù hợp) để kiểm tra request tiếp theo.

### Khi trước login có saved request

Nếu user vào `GET /private` trước, ứng dụng có thể lưu request bị chặn, sau đó redirect tới màn hình login. Success handler mặc định có thể đưa user về URL ban đầu. Trong bộ ví dụ trên, `defaultSuccessUrl("/private", true)` được chọn rõ để assert ổn định. Nếu bỏ `true` và dùng saved request, test phải giữ đúng session từ request bị chặn, đăng nhập rồi kỳ vọng redirect theo request cache, không cứng nhắc kỳ vọng một URL.

## 6. Phân biệt HTTP status của IdP và của ứng dụng

Khi debug lỗi, luôn ghi rõ bạn đang quan sát **đoạn HTTP nào**:

```text
Browser -> App:
  GET /oauth2/authorization/demo
  <- 302 Location: https://idp/authorize?...&state=...

IdP -> Browser -> App:
  GET /login/oauth2/code/demo?code=...&state=...

App -> IdP (back-channel):
  POST /token   -> 400 JSON {"error":"invalid_grant"}

App -> Browser:
  <- 302 Location: /login?error  (failure handler theo ví dụ)
```

Các mã HTTP ở ba kênh trên khác trách nhiệm:

- `302` từ app khi **bắt đầu OAuth2** chỉ báo trình duyệt đến authorization endpoint.
- `302` từ app sau **callback thành công** chỉ báo trang tiếp theo; phải xác nhận session/danh tính hoặc truy cập được endpoint bảo vệ.
- `302` từ app sau **callback lỗi** chỉ báo failure handler đã chọn redirect tới trang login.
- `400 invalid_grant` hoặc `503 temporarily_unavailable` thuộc **HTTP trao đổi giữa app và token endpoint**; browser không tự nhìn thấy response đó.
- `401` hoặc `403` từ **endpoint bảo vệ sau đăng nhập** phản ánh authentication/authorization cho request mới, không phải thay thế cho mã lỗi OAuth2 bên trong callback.

Một test chỉ assert `status().isFound()` cho callback có thể PASS cả lúc login thành công lẫn lúc thất bại. Bổ sung `redirectedUrl(...)`, trạng thái principal sau login, và kiểm tra đúng số lượt gọi token endpoint.

## 7. Kiểm tra request thật gửi tới token endpoint

Sau khi test `invalidCode_failsAfterCallingTokenEndpoint`, có thể tăng mức xác minh:

```java
idp.verify(1, postRequestedFor(urlEqualTo("/token"))
        .withRequestBody(containing("grant_type=authorization_code"))
        .withRequestBody(containing("code=code-invalid")));
```

Khi dùng `ClientAuthenticationMethod.CLIENT_SECRET_BASIC`, request thường có HTTP Basic client authentication. Nếu kiểm tra giá trị thật của header, hãy chỉ dùng credentials thử nghiệm và tránh in header ra log. Trong các phiên bản cấu hình khác (client secret POST, private key JWT, public client), cách xác thực client và nội dung request body sẽ khác.

Kiểm chứng thêm các hợp đồng quan trọng:

1. `redirect_uri` trong token request nhất quán với URI được đăng ký và đã dùng ở authorization request.
2. Nếu PKCE được bật, token request chứa `code_verifier` tương ứng `code_challenge` ở authorization request; thiếu/mismatch phải bị IdP từ chối.
3. Với lỗi consent hoặc callback không khớp state, số lần gọi token endpoint phải là **0**.
4. Với code không hợp lệ, token endpoint được gọi **1 lần**, nhận `invalid_grant`, không tạo login thành công.
5. Với callback lặp sau thành công, repository tiêu thụ authorization request khiến lượt phát lại không tạo exchange mới; số lần gọi token endpoint trong ví dụ tổng cộng vẫn là **1**.

Nếu muốn kiểm chứng token request bằng các trường chính xác, dùng WireMock `matching(...)` hoặc truy xuất request journal; tránh dựa vào thứ tự query/body không có ý nghĩa hoặc in toàn bộ authorization header.

**Không kiểm thử PKCE chỉ bằng cách kiểm tra chuỗi `code_challenge` xuất hiện.** Một test đúng cần kiểm tra việc Authorization Server hoặc token endpoint giả lập thực sự từ chối mismatch `code_verifier`. Spring Security hỗ trợ PKCE tùy cấu hình/client profile; điều kiện bật, công thức và các API cấu hình cụ thể phải được xem theo phiên bản đang dùng.

## 8. Khi chuyển từ OAuth2 Login sang OIDC Login

OIDC sử dụng Authorization Code trên nền OAuth2, nhưng thêm một bước quan trọng: xác minh **ID token** chứa claims về danh tính người dùng. Sau token exchange, OIDC provider thường trả:

```json
{
  "access_token": "opaque-or-jwt-access-token",
  "token_type": "Bearer",
  "expires_in": 600,
  "id_token": "<signed-oidc-id-token>"
}
```

ID token không thể thay bằng một chuỗi tùy ý trong bài test OIDC thực. Spring Security cần kiểm tra các điều kiện thích hợp như chữ ký (theo cấu hình issuer/JWK), `iss`, `aud`, thời điểm hiệu lực và `nonce` khi nonce được sử dụng. Sau đó mới có `OidcUser`/`OAuth2AuthenticationToken` để ứng dụng dùng.

Trong test OIDC tích hợp, thường cần thêm:

- Một `ClientRegistration` OIDC có scope `openid` và metadata provider đúng.
- Một endpoint JWKS giả lập hoặc khóa kiểm chứng đã cấu hình, ID token được ký bằng khóa thử nghiệm tương ứng.
- Claims `iss`, `aud`, `sub`, `iat`, `exp`, `nonce` nhất quán với authorization request và quy tắc validation.
- Test riêng cho `access_denied` ở callback, `invalid_grant` ở token endpoint, lỗi JWKS và lỗi ID token `nonce`/`aud`/`iss` không khớp.

Ví dụ ma trận lỗi OIDC:

| Nhánh | OAuth2 hay OIDC? | Giai đoạn chặn |
| --- | --- | --- |
| `error=access_denied` | Cả hai | Callback, trước token exchange |
| `invalid_grant` | Cả hai | Token exchange |
| State sai/mất session | Cả hai | Callback correlation |
| Code bị dùng lại | Cả hai | Callback repository hoặc token endpoint |
| ID token sai chữ ký/issuer/audience | OIDC | Validation ID token sau token exchange |
| Nonce không khớp | OIDC | Binding ID token với request đăng nhập |

**State và nonce phục vụ hai mục tiêu khác nhau.** State ràng buộc authorization response với request và browser đã khởi tạo; nonce ràng buộc ID token với phiên OIDC authentication. Đừng thay thế một test bằng test kia, hoặc dùng `.with(oidcLogin())` rồi kết luận được rằng các kiểm tra đó đã chạy.

## 9. Vì sao `oauth2Login()` và `oidcLogin()` không đủ cho các lỗi này?

Spring Security Test cung cấp cách tạo principal nhanh:

```java
mockMvc.perform(get("/private")
        .with(oauth2Login()))
        .andExpect(status().isOk());

// Ứng dụng OIDC có thể sử dụng:
mockMvc.perform(get("/private")
        .with(oidcLogin()))
        .andExpect(status().isOk());
```

Các post-processors này đặt sẵn authentication thử nghiệm vào request, có thể tạo authorized client giả lập liên quan đến login. Chúng phù hợp để kiểm tra authorization hoặc controller **sau khi đã xác thực**, nhưng không chạy `OAuth2AuthorizationRequestRedirectFilter`, callback, `state`, authorization code exchange hay token endpoint.

| Mục tiêu | Công cụ phù hợp |
| --- | --- |
| Controller trả dữ liệu theo OAuth2/OIDC principal | `oauth2Login()` hoặc `oidcLogin()` |
| Route với role/scope được phép hay bị chặn | Mock principal + MockMvc/WebTestClient |
| Có tạo redirect đúng tới authorization endpoint không? | MockMvc gọi `/oauth2/authorization/{id}` |
| Có xử lý `error=access_denied` mà không gọi token endpoint không? | MockMvc callback + session/state thực + WireMock verify |
| Code bị token endpoint từ chối `invalid_grant` | MockMvc callback + token endpoint HTTP stub |
| Callback bị phát lại | Hai callback dùng cùng code/state; kiểm tra token exchange và login |
| OIDC ID token validation | Provider/JWKS giả lập với ID token ký thật |
| Network timeout/token endpoint 503 | HTTP stub server + kiểm chứng exception/error contract |

Với WebFlux, chọn `WebTestClient` và `SecurityWebFilterChain`; HTTP OAuth2 redirect/callback cũng cần state, session/cookie và IdP stub tương ứng. `mockOAuth2Login()`/`mockOidcLogin()` ở Reactive là các shortcut cho authentication, tương tự các helper Servlet. **Không dùng `MockMvc` để xác minh filter chain Reactive**, và không cho rằng test có mock principal là test exchange thật.

## 10. Các lỗi triển khai và test thường gặp

**Tự chế `state` rồi gọi trực tiếp callback:** Spring Security không tìm được authorization request đã lưu. Khi muốn kiểm tra token endpoint, bắt buộc đi qua request bắt đầu OAuth2 và dùng lại session/state thật.

**Bỏ session giữa redirect và callback:** `HttpSessionOAuth2AuthorizationRequestRepository` không nhận ra request ban đầu; test có thể báo lỗi correlation trước khi chạm token endpoint. Hãy truyền session hoặc cookie phù hợp theo repository được cấu hình.

**Coi redirect `/login?error` là một HTTP 401:** Đó là redirect do failure handler. Nếu cần JSON 401/503 ở API, ứng dụng phải định nghĩa contract và handler thích hợp, rồi test theo contract đó.

**Stub `GET /token` thay cho `POST /token`:** Authorization Code grant đổi code bằng HTTP POST. Một stub sai method sẽ không khớp và kết quả lỗi có thể gây hiểu lầm.

**Cho token endpoint luôn trả success dù code đã dùng:** Stub đơn giản không tự thực thi quy tắc code dùng một lần. Nếu test khả năng replay của chính Authorization Server, phải lập stub/state machine để token thứ hai trả `invalid_grant` hoặc dùng IdP thử nghiệm có hành vi thật.

**Khẳng định callback lặp nhất định phải POST token lần hai:** Phần lớn luồng dùng session authorization request được loại bỏ sau lần xử lý đầu; lỗi replay có thể xuất hiện trước token exchange. Test nên chỉ ra chính xác bước thất bại.

**Nhầm lỗi `invalid_grant` với lỗi thiếu quyền sau login:** `invalid_grant` nghĩa là không đổi được code; `403` ở resource cần phân quyền thường nghĩa là đã có principal nhưng thiếu authority.

**Trộn OIDC ID token với access token:** `id_token` có validation dành cho danh tính và nonce; access token phục vụ resource access. Cần kiểm thử cả hai mục tiêu khi ứng dụng hỗ trợ OIDC.

**Hardcode mọi lỗi token endpoint thành 302:** OAuth2 error JSON có thể được chuyển thành authentication failure, còn timeout/TLS/invalid payload có thể đi qua nhánh exception khác. Mô phỏng từng loại lỗi và ghi rõ error contract của ứng dụng.

**Dùng HTTP stub mà không xác minh request journal:** Một test 302 có thể PASS dù không gọi token endpoint. `verify(0)` hoặc `verify(1)` làm rõ request thật đã đi qua bước nào.

**Đặt credentials/token thật trong test:** Chỉ dùng giá trị thử nghiệm, không commit client secret production hoặc ghi authorization code/access token thật vào log. Có thể assert header/body theo matcher mà không xuất bản toàn bộ dữ liệu nhạy cảm.

**Test không mô phỏng trình duyệt qua cookie/session:** Sau callback thành công, cần dùng session mới/current để kiểm tra resource được bảo vệ. Nếu muốn kiểm tra tính liên tục qua reverse proxy, SameSite cookie hoặc domain redirects, cần bổ sung test HTTP/browser ở mức cao hơn.

## 11. Checklist kiểm chứng và bài tập thực hành

Một bộ test luồng OAuth2 thật nên có đủ các bằng chứng sau:

1. **Bắt đầu authorization**: response redirect đúng authorization endpoint, có `client_id`, `response_type=code`, `redirect_uri` và `state`; session đã lưu request.
2. **Consent denied**: callback chứa `error=access_denied` và state, failure handler chạy, token endpoint có **0 request**.
3. **Code invalid/expired**: callback state hợp lệ; token endpoint nhận POST đúng grant/code và trả `invalid_grant`; app không tạo login thành công.
4. **Callback replay**: gửi cùng callback hai lần; lần đầu thành công khi token/user-info hợp lệ, lần hai bị từ chối và không có token exchange mới.
5. **Token endpoint 5xx/timeout**: application fail-closed; behavior HTTP/exception theo policy; log đã loại bỏ secret.
6. **State/session bị sai**: request thất bại trước token endpoint; không tạo Authentication.
7. **Nếu có OIDC**: ID token được ký và validate đúng; thêm ca nonce sai, issuer/audience sai và JWKS không khả dụng.
8. **Sau thành công**: request mới mang session/cookie hợp lệ truy cập tài nguyên bảo vệ; sau thất bại không tạo login mới ngoài ý muốn.

**Bài tập 1:** Thêm test cho `error=login_required` ở callback (IdP không thể xác thực người dùng), kiểm tra failure redirect và `verify(0, POST /token)`. So sánh kết quả với `access_denied`.

**Bài tập 2:** Tạo callback với đúng session nhưng sai `state`. Giải thích vì sao `GET /login/oauth2/code/demo` được gọi nhưng token endpoint vẫn có thể không có request nào.

**Bài tập 3:** Thay stub `invalid_grant` bằng một response HTTP 500 không chứa OAuth2 JSON hợp lệ. Quan sát exception/status thực tế theo dependency/version của dự án; định nghĩa contract mà ứng dụng mong muốn và viết assertion tương ứng.

**Bài tập 4:** Giữ nguyên code lần đầu nhưng khởi tạo authorization request mới và dùng state mới cho callback lần hai. Stub IdP từ chối code đã sử dụng bằng `invalid_grant`; giải thích sự khác nhau giữa kiểm tra replay ở client và quy tắc code một lần ở IdP.

**Bài tập 5:** Xây dựng một nhánh OIDC với JWKS test và ID token được ký bằng khóa thử nghiệm. Thay đổi `nonce` trong ID token và kiểm tra cơ chế OIDC từ chối token sau token exchange.

### Tài liệu tham khảo

- [Spring Security — OAuth2 Login (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html)
- [Spring Security — Testing OAuth2 with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html)
- [OAuth 2.0 Authorization Framework — RFC 6749, mục Authorization Code](https://www.rfc-editor.org/rfc/rfc6749#section-4.1)
- [Proof Key for Code Exchange — RFC 7636](https://www.rfc-editor.org/rfc/rfc7636)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)

Một test OAuth2/OIDC có giá trị phải xác nhận được **lỗi xảy ra tại giai đoạn nào và request nào đã thực sự được thực hiện**. MockMvc giữ luồng Servlet filter và session; IdP HTTP stub cho phép điều khiển consent callback, response của token endpoint và user-info; assertion phối hợp `state`, `Location`, `Authentication` cùng số lần exchange giúp phân biệt lỗi xác thực thực sự với lỗi mô phỏng test. Khi hiểu ranh giới này, người học có thể dùng cả mock principal cho kiểm thử phân quyền nhanh lẫn các test luồng OAuth2 thực để bảo vệ những điểm nhạy cảm của đăng nhập.
