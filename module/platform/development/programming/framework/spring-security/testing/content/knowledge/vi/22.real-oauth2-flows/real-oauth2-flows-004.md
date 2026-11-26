# Liên kết state với phiên và từ chối callback không khớp

Trong **Authorization Code flow** của OAuth2, ứng dụng đưa trình duyệt đến trang đăng nhập của Identity Provider (IdP), sau đó nhận một callback có `code` và `state`. Tham số `state` là giá trị liên kết **authorization response** quay về với **authorization request** mà chính trình duyệt hoặc phiên đăng nhập đó đã khởi tạo. Nếu callback không khớp yêu cầu đang chờ, ứng dụng phải từ chối trước khi sử dụng authorization code.

Đây là một ca kiểm thử giao thức quan trọng của chương **Luồng OAuth2 thực**, nằm trong module `SPRING_SECURITY_TESTING`: kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên Servlet và Reactive. Người học sử dụng `MockMvc` để khởi động một yêu cầu đăng nhập thật qua Spring Security filter chain, giữ `MockHttpSession`, lấy `state` từ redirect và thử callback hợp lệ hoặc bị chỉnh sửa. Bài cũng chỉ rõ giới hạn của `oauth2Login()`/`oidcLogin()` giả lập và cách tiếp cận tương đương khi dùng `WebTestClient`.

> Trọng tâm là **đối chiếu `state` với yêu cầu đăng nhập được lưu theo phiên**, không chỉ kiểm tra rằng URL callback có chứa một tham số tên `state`. Một callback mang giá trị ngẫu nhiên, giá trị từ phiên khác hoặc callback không có yêu cầu được lưu phải bị từ chối.

## 1. Vì sao callback không thể được tin chỉ vì có code?

Khi người dùng bắt đầu đăng nhập, ứng dụng được gọi là **OAuth2 Client** gửi authorization request đến IdP. Sau khi người dùng xác thực/đồng ý, IdP chuyển trình duyệt về `redirect_uri` cùng các tham số truy vấn.

Ví dụ request đến IdP:

```http
GET /authorize?response_type=code&client_id=reports-web&redirect_uri=https%3A%2F%2Fclient.example.test%2Flogin%2Foauth2%2Fcode%2Fdemo&scope=openid%20profile&state=N8c7sG... HTTP/1.1
Host: idp.example.test
```

Ví dụ callback quay về ứng dụng:

```http
GET /login/oauth2/code/demo?code=AUTH_CODE_123&state=N8c7sG... HTTP/1.1
Host: client.example.test
Cookie: JSESSIONID=<cookie-cua-phien-da-bat-dau-login>
```

`code` là một dữ liệu tạm thời mà ứng dụng **chưa nên đem đổi token** nếu không tìm được authorization request tương ứng. Giá trị `state` do client tạo khi bắt đầu flow, cần đủ khó đoán và phải được kiểm tra bằng giá trị đã lưu cho chính giao dịch đăng nhập đó.

Nếu ứng dụng bỏ qua đối chiếu `state`, nó có thể bị **login CSRF**: kẻ tấn công cố làm cho nạn nhân hoàn tất một phản hồi đăng nhập do kẻ tấn công khởi tạo, khiến phiên nạn nhân bị gắn với danh tính không mong muốn. Những đặc điểm cụ thể của cuộc tấn công còn phụ thuộc client, IdP và cấu hình session/cookie; mục tiêu kiểm thử là loại bỏ đường callback không gắn với authorization request hợp lệ.

```mermaid
sequenceDiagram
    autonumber
    actor Browser as Browser / Session A
    participant Client as Spring OAuth2 Client
    participant Repo as AuthorizationRequestRepository
    participant IdP as Identity Provider
    Browser->>Client: GET /oauth2/authorization/demo
    Client->>Repo: Lưu authorization request với state S_A
    Client-->>Browser: 302 tới IdP, kèm S_A
    Browser->>IdP: Authorization request (state S_A)
    IdP-->>Browser: Redirect về client: code C, state S_A
    Browser->>Client: GET /login/oauth2/code/demo?code=C&state=S_A (Session A)
    Client->>Repo: Lấy yêu cầu đã lưu cho Session A; so state
    alt Khớp với authorization request
        Client->>IdP: Đổi code C tại token endpoint
        IdP-->>Client: Token response
        Client-->>Browser: Hoàn tất login theo cấu hình
    else State sai / thiếu / phiên khác
        Client-->>Browser: Authentication failure; không đổi code
    end
```

## 2. Spring Security liên kết state và session ra sao?

Trong ứng dụng **Servlet** dùng `oauth2Login()` với các mặc định thông dụng:

1. `OAuth2AuthorizationRequestRedirectFilter` xử lý đường dẫn khởi tạo `/oauth2/authorization/{registrationId}`, xây dựng `OAuth2AuthorizationRequest` chứa `state`, `redirect_uri`, scopes và các tham số giao thức liên quan.
2. `AuthorizationRequestRepository<OAuth2AuthorizationRequest>` lưu yêu cầu trước khi trình duyệt được redirect đến IdP. Triển khai mặc định điển hình là `HttpSessionOAuth2AuthorizationRequestRepository`, lưu yêu cầu trong **HTTP session của trình duyệt đã bắt đầu đăng nhập**.
3. Khi browser quay về `/login/oauth2/code/{registrationId}`, `OAuth2LoginAuthenticationFilter` tìm authorization request đã lưu và đối chiếu `state` trước khi thực hiện token exchange.
4. Nếu không tìm thấy yêu cầu tương ứng, flow thất bại; failure handler quyết định cách phản hồi (thường là chuyển hướng đến `/login?error` với cấu hình đăng nhập mặc định).
5. Chỉ khi callback được liên kết với request hợp lệ, client mới tiếp tục xác thực authorization response, đổi code lấy token, dựng principal và cập nhật SecurityContext/session theo chính sách của ứng dụng.

**Session ID** và `state` có vai trò khác nhau. Cookie phiên cho Spring tìm **kho lưu authorization request của browser hiện tại**. `state` cho phép chọn và đối chiếu **giao dịch OAuth2 cụ thể** trong phạm vi kho đó. Một callback chỉ có đúng `state` nhưng dùng phiên khác không tự động trở thành hợp lệ.

Không nên hardcode tên session attribute nội bộ của `HttpSessionOAuth2AuthorizationRequestRepository`. Kiểm thử từ bên ngoài qua HTTP redirect và callback giúp chứng minh hành vi mà không phụ thuộc cấu trúc lưu trữ của thư viện.

### Tự cấu hình AuthorizationRequestRepository

Nếu ứng dụng dùng repository tùy chỉnh, ví dụ lưu authorization request trong cookie mã hóa hoặc kho phân tán, nguyên tắc vẫn là:

- Có **ràng buộc xác thực** giữa yêu cầu lúc bắt đầu, browser/phân vùng phiên và phản hồi callback.
- `state` phải được tạo đủ khó đoán, không được chấp nhận chỉ vì có định dạng hợp lệ.
- Dữ liệu lưu trữ cần được bảo vệ trước sửa đổi/tái sử dụng; nếu chuyển sang cookie phải xem xét integrity, hạn dùng, SameSite và phạm vi cookie.
- Một authorization response sai `state` không được khiến client gọi token endpoint hoặc tạo Authentication hợp lệ.

Chi tiết “mỗi session giữ bao nhiêu authorization requests” và cách tiêu thụ request tùy repository. Ví dụ repository mặc định lưu một yêu cầu trong session ở nhiều phiên bản; nếu người dùng mở nhiều tab đăng nhập, giao dịch sau có thể thay giao dịch trước. Đừng mặc định tất cả repository hỗ trợ nhiều flow đồng thời hay callback lỗi chắc chắn xóa mọi state còn lưu.

## 3. Phân biệt state, nonce và PKCE

Ba khái niệm này cùng xuất hiện trong OAuth2/OIDC nhưng bảo vệ những điều khác nhau:

| Cơ chế | Được tạo ở bước nào? | Được kiểm tra ở đâu? | Mục đích |
|---|---|---|---|
| `state` | Client tạo cùng authorization request | Khi nhận authorization response/callback | Gắn response với request do phiên tương ứng khởi tạo; chống login CSRF. |
| `nonce` (OIDC) | Client tạo cho OIDC authentication request | Khi xác thực `nonce` trong ID Token | Gắn ID Token với giao dịch OIDC, hạn chế replay/token substitution. |
| PKCE (`code_verifier`/`code_challenge`) | Client tạo trước redirect đến IdP | Authorization server kiểm tra `code_verifier` khi đổi authorization code | Ngăn kẻ khác dùng code bị chặn bắt mà không có verifier. |

PKCE **không thay thế** kiểm tra `state`, và `nonce` của OIDC cũng không phải là “state phiên”. Khi kiểm thử callback thiếu hoặc sai `state`, cần xác minh bị từ chối **trước token exchange**. Sau đó phải có ca kiểm thử riêng chứng minh PKCE/nonce/ID Token validation nếu đó là phạm vi bài test.

## 4. Ứng dụng Servlet mẫu cho ca kiểm thử

Ví dụ dùng Spring Boot Servlet với `spring-boot-starter-web`, `spring-boot-starter-security`, `spring-boot-starter-oauth2-client`, `spring-boot-starter-test` và `spring-security-test`.

Tạo cấu hình OAuth2 Client có `registrationId = "demo"`. Các endpoint tại `idp.example.test` chỉ để minh họa: các test **callback sai state** phải bị chặn trước khi có bất kỳ gọi mạng nào tới token endpoint; các ca callback thành công sẽ dùng IdP test server thực sự.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OAuth2ClientSecurityConfig {
    @Bean
    ClientRegistrationRepository clientRegistrations() {
        ClientRegistration demo = ClientRegistration.withRegistrationId("demo")
                .clientId("reports-web")
                .clientSecret("fixture-secret")
                .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
                .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
                .scope("profile")
                .authorizationUri("https://idp.example.test/authorize")
                .tokenUri("https://idp.example.test/token")
                .userInfoUri("https://idp.example.test/userinfo")
                .userNameAttributeName("id")
                .clientName("Reports Demo")
                .build();
        return new InMemoryClientRegistrationRepository(demo);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/private/**").authenticated()
                        .anyRequest().permitAll())
                .oauth2Login(Customizer.withDefaults())
                .build();
    }
}
```

Endpoint xác định có Authentication đã đăng nhập:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class PrivateController {
    @GetMapping("/private/ping")
    String ping() {
        return "authenticated";
    }
}
```

Trong các đoạn này, OAuth2 login là cơ chế **đăng nhập browser**, không phải cấu hình OAuth2 Resource Server để nhận Bearer JWT cho API. `GET /private/ping` được bảo vệ và chỉ dùng để xác định phiên có được xác thực hay không. Mã redirect và trang báo lỗi có thể được tùy chỉnh bởi `AuthenticationFailureHandler`/`AuthenticationEntryPoint` trong ứng dụng thực.

## 5. Khởi động login và thu state từ redirect thật

Bài kiểm thử **không tự tạo `state`**. Thay vào đó, gửi request qua `OAuth2AuthorizationRequestRedirectFilter` để Spring Security tạo `state` và lưu authorization request trong session.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.web.util.UriComponentsBuilder;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OAuth2StateSessionTest {
    @Autowired
    MockMvc mockMvc;

    record LoginStart(String state, MockHttpSession session) {}

    private LoginStart beginLogin() throws Exception {
        MvcResult start = mockMvc
                .perform(get("/oauth2/authorization/demo"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        String authorizationUrl = start.getResponse().getRedirectedUrl();
        assertThat(authorizationUrl)
                .startsWith("https://idp.example.test/authorize");

        String state = UriComponentsBuilder
                .fromUriString(authorizationUrl)
                .build()
                .getQueryParams()
                .getFirst("state");

        MockHttpSession session = (MockHttpSession)
                start.getRequest().getSession(false);
        assertThat(state).isNotBlank();
        assertThat(session).isNotNull();
        return new LoginStart(state, session);
    }

    // Các @Test đặt tiếp trong cùng lớp ở các mục dưới.
}
```

`beginLogin()` lấy hai dữ liệu quan trọng:

- `state` thực sự do Spring Security phát ra trong **redirect đến IdP**.
- `MockHttpSession` đã được Spring Security dùng để lưu authorization request.

Trong `MockMvc`, `.session(session)` mô phỏng browser tiếp tục dùng cùng session. Đừng chỉ sao chép chuỗi `state` rồi gửi callback bằng một request không có session: cách đó cố tình làm mất liên kết cần kiểm tra.

Khi hệ thống dùng repository không dựa vào HTTP session, hãy giữ đúng cơ chế lưu trữ và định danh browser mà ứng dụng cấu hình; mẫu trên dành cho `HttpSessionOAuth2AuthorizationRequestRepository`.

## 6. Callback bị sửa state phải thất bại

Ca quan trọng nhất: browser bắt đầu login đúng cách, nhưng callback mang `state` đã bị chỉnh sửa trong **cùng session**.

Thêm vào lớp `OAuth2StateSessionTest`:

```java
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.redirectedUrl;

@Test
void callbackWithTamperedState_isRejected() throws Exception {
    LoginStart start = beginLogin();
    String tamperedState = start.state() + "-changed";

    mockMvc.perform(get("/login/oauth2/code/demo")
                    .session(start.session())
                    .param("code", "untrusted-code")
                    .param("state", tamperedState))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));

    mockMvc.perform(get("/private/ping")
                    .session(start.session()))
            .andExpect(status().is3xxRedirection());
}
```

Với `oauth2Login()` mặc định trong ví dụ, login failure chuyển hướng về `/login?error`; tiếp tục truy cập `/private/ping` bằng chính session ấy vẫn chưa được xác thực nên được chuyển hướng đến login. Nếu ứng dụng có custom failure handler hoặc dùng JSON entry point, hãy thay assertion redirect bằng mã HTTP/JSON tương ứng, nhưng vẫn giữ yêu cầu **không có Authentication hợp lệ được thiết lập**.

**Tại sao dùng `"untrusted-code"`?** Callback sai state phải thất bại **trước khi** ứng dụng gọi token endpoint. Vì vậy giá trị code là dữ liệu giả bất kỳ; bài test không cần IdP trả token. Nếu callback đi tới IdP rồi thất bại do “code không hợp lệ”, đây là một lỗi kiểm thử: nó không chứng minh cơ chế chống login CSRF đã chặn ở bước đối chiếu state.

Muốn khẳng định chắc chắn **không có token exchange**, đặt `tokenUri` tới một HTTP test server có bộ đếm request (WireMock/MockWebServer), rồi assert có **0 request** tới `/token` sau callback không khớp:

```java
// Minh họa nếu dự án đã tạo WireMockServer tên tokenServer
// và ClientRegistration.tokenUri trỏ tới máy chủ này:
tokenServer.verify(
        0,
        postRequestedFor(urlEqualTo("/token")));
```

Đoạn xác minh trên dùng API của WireMock, không phải thành phần Spring mặc định. Cần thay URI của `ClientRegistration` từ `idp.example.test` sang đúng WireMock URL trong test để phép đếm có ý nghĩa; nếu không, kiểm tra số request ở một server không được sử dụng sẽ cho kết quả 0 giả.

## 7. State từ Session A không được dùng cho Session B

Một phép thử mạnh hơn chứng minh **ràng buộc phiên**: khởi tạo hai đăng nhập độc lập rồi gửi `state` của A trong callback thuộc session B.

```java
@Test
void stateFromAnotherSession_doesNotAuthenticate() throws Exception {
    LoginStart a = beginLogin();
    LoginStart b = beginLogin();

    assertThat(a.state()).isNotEqualTo(b.state());

    mockMvc.perform(get("/login/oauth2/code/demo")
                    .session(b.session())
                    .param("code", "code-for-session-a")
                    .param("state", a.state()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));

    mockMvc.perform(get("/private/ping")
                    .session(b.session()))
            .andExpect(status().is3xxRedirection());
}
```

Điểm quan trọng: session B có một authorization request **riêng**, nhưng `state` trong callback lấy từ A. Chỉ kiểm tra “state xuất hiện trong bất kỳ session nào” sẽ không đạt yêu cầu bảo vệ. Nếu hệ thống dùng một kho phân tán, test này còn giúp phát hiện lỗi gắn state với sai định danh phiên.

Một callback không mang session nào trước đó cũng phải thất bại:

```java
@Test
void callbackWithoutOriginalSession_isRejected() throws Exception {
    LoginStart a = beginLogin();

    mockMvc.perform(get("/login/oauth2/code/demo")
                    .session(new MockHttpSession())
                    .param("code", "untrusted-code")
                    .param("state", a.state()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));
}
```

`new MockHttpSession()` đại diện cho một phiên khác, không chứa authorization request của A. Đây không phải giả lập “cùng browser đổi tên cookie”; nó là ca **không có giao dịch đang chờ trong phiên nhận callback**.

## 8. Callback đúng state phải đi đến giai đoạn đổi code

Chỉ có các test từ chối chưa đủ: một hệ thống chặn mọi callback đều có thể khiến chúng xanh. Cần thêm **ca tích hợp thành công** để xác minh đường đi đúng.

Với ca thực tế, cấu hình IdP test server (WireMock/MockWebServer hoặc server HTTP tương đương) có `/authorize`, `/token` và `/userinfo` (hoặc `/jwks`/ID Token cho OIDC). Trong `ClientRegistration` của test, thay các URI bằng URI server cục bộ. Tại `/token`, trả response OAuth2 hợp lệ với access token test; với OAuth2 login không có scope `openid`, mock userinfo response theo `userNameAttributeName("id")`.

Trình tự:

1. Gọi `beginLogin()` để lấy `state` và session của browser.
2. Cấu hình IdP test server chấp nhận authorization code `good-code` và trả response token/userinfo hợp lệ.
3. Gửi callback `/login/oauth2/code/demo?code=good-code&state=<state-thật>` kèm **đúng session**.
4. Kiểm tra HTTP chuyển hướng sau login thành công theo cấu hình, và IdP test server ghi nhận request `POST /token` với `code=good-code`.
5. Sử dụng session sau callback để gọi `GET /private/ping` **không dùng `oauth2Login()`**; kỳ vọng 200 và response `authenticated`.

Ví dụ khung phần gọi callback (giả định server đã trả token/userinfo hợp lệ):

```java
LoginStart start = beginLogin();

MvcResult callback = mockMvc.perform(
                get("/login/oauth2/code/demo")
                        .session(start.session())
                        .param("code", "good-code")
                        .param("state", start.state()))
        .andExpect(status().is3xxRedirection())
        .andReturn();

MockHttpSession authenticatedSession = (MockHttpSession)
        callback.getRequest().getSession(false);

mockMvc.perform(get("/private/ping")
                .session(authenticatedSession))
        .andExpect(status().isOk());
```

Đây là **khung tích hợp có điều kiện**; không thể chạy nguyên vẹn nếu chưa dựng token/userinfo endpoint của IdP test server. Nó minh họa cách sử dụng **state thực + session thật + OAuth2LoginAuthenticationFilter thật**. Nếu Spring Security hoặc ứng dụng thay session lúc đăng nhập để chống session fixation, lấy session **sau callback** thay vì giữ cứng đối tượng session ban đầu.

Nếu kiểm thử OIDC (`scope=openid`), mock token endpoint phải trả **ID Token ký thật** với issuer, audience, thời gian và nonce phù hợp; JWKS test server công bố khóa công khai. Chữ ký, `iss`, `aud`, `exp` và `nonce` là các kiểm tra **bổ sung** sau khi state khớp. Không lấy một bài test chỉ kiểm tra state làm bằng chứng cho toàn bộ giao thức OIDC.

## 9. Khi state không khớp, cần quan sát gì?

Một assertion `status().is3xxRedirection()` đơn lẻ có thể cho cảm giác an toàn sai, vì **đăng nhập thành công cũng có thể redirect**. Nên kiểm tra nhiều dấu hiệu độc lập:

| Bằng chứng | Ca state không khớp | Vì sao cần |
|---|---|---|
| Login failure handler được gọi | Response trỏ tới failure URL hoặc thông tin lỗi theo cấu hình. | Phân biệt redirect lỗi với redirect thành công. |
| Token endpoint | **Không nhận request đổi code**. | Chứng minh state bị từ chối trước khi xử lý code. |
| Authentication/phiên sau callback | Không có phiên đã đăng nhập. | Tránh tình trạng response báo lỗi nhưng SecurityContext vẫn được lưu. |
| Tài nguyên được bảo vệ | Request kế tiếp chưa được phép truy cập. | Kiểm tra bảo vệ HTTP vẫn có hiệu lực. |
| Nghiệp vụ nhạy cảm | Không có lời gọi hoặc thay đổi trạng thái. | Ngăn ảnh hưởng ngoài ý muốn khi callback bị từ chối. |

Nếu test dùng Mockito cho service nghiệp vụ, có thể gọi `verifyNoInteractions(protectedService)` sau request tới API được bảo vệ. Cẩn trọng không mock chính bean được bảo vệ bởi `@PreAuthorize` nếu mục tiêu là kiểm chứng method security: hãy giữ service thật và mock những dependency ghi dữ liệu hoặc phát sự kiện phía sau.

Với IDP thật, có thể khó xác nhận trực tiếp token endpoint không được gọi. Trong test tích hợp kiểm soát toàn bộ IdP endpoint thì việc đếm request là cách có căn cứ nhất.

### Giá trị lỗi và vấn đề information leakage

Không nên ghi đầy đủ `code`, access token, ID Token hoặc cookie vào log khi callback bị từ chối. Hệ thống có thể ghi loại lỗi, registrationId, correlation ID không nhạy cảm và số lần thất bại để điều tra. Không để message lỗi tiết lộ bí mật, session ID hoặc raw authorization response.

## 10. Ma trận kịch bản kiểm thử

| Ca | Authorization request đã lưu | Callback | Kỳ vọng |
|---|---|---|---|
| A. Flow hợp lệ | Session A lưu `state=S_A` | Session A, `state=S_A`, code hợp lệ | Đi đến token exchange và có thể hoàn tất login. |
| B. State bị sửa | Session A lưu `S_A` | Session A, `state=S_X` | Failure trước token exchange. |
| C. State của phiên khác | Session B lưu `S_B` | Session B, `state=S_A` | Failure, không tạo Authentication cho B. |
| D. Không có session gốc | Request A đã được lưu | Session mới, `state=S_A` | Failure vì không tìm được yêu cầu tương ứng. |
| E. Không có state | Session A lưu `S_A` | Session A, chỉ có code | Failure; không đổi code. |
| F. Callback bất ngờ | Chưa từng khởi tạo login | Gửi code và state bất kỳ | Failure; không tạo phiên đăng nhập. |
| G. Code không hợp lệ nhưng state đúng | Session A lưu `S_A` | `state=S_A`, code giả | State có thể qua bước đối chiếu; token exchange thất bại riêng. |
| H. State đúng, OIDC nonce sai | Session A lưu state và nonce | State khớp, ID Token nonce sai | Thất bại ở bước ID Token validation. |
| I. Hai tab đăng nhập | Hai request cùng browser/session | Callback của request cũ | Kết quả theo repository; không tự giả định hỗ trợ nhiều request cùng lúc. |
| J. Callback lặp lại | Một flow đã hoàn tất | Dùng lại code/state cũ | Không được tự tạo thêm login thành công; kiểm tra chính sách tiêu thụ request và tính dùng một lần của code. |

**Mấu chốt:** Ca A là đối chứng tích cực; B–F trực tiếp kiểm tra liên kết state/phiên; G–H giúp phân biệt lỗi ở bước state với lỗi ở bước token/OIDC; I–J kiểm tra cạnh giao dịch, session và replay.

Đối với ca J, hành vi chi tiết của client repository và authorization server có thể khác nhau; mục tiêu an toàn là **không chấp nhận lại giao dịch cũ như một login mới** khi điều kiện bảo mật không cho phép.

## 11. Những sai lầm khiến test xanh nhưng bỏ sót lỗi

1. **Dùng `.with(oauth2Login())` hoặc `.with(oidcLogin())` rồi kết luận state an toàn.** Hai công cụ này cung cấp Authentication giả lập cho request; chúng không khởi động flow qua redirect và callback.
2. **Tự truyền state cố định cho cả hai request.** Điều này có thể thử parser, nhưng không chứng minh `OAuth2AuthorizationRequestRedirectFilter` tạo và lưu state đúng cho từng login.
3. **Chỉ kiểm tra callback 302.** Cần phân biệt redirect lỗi với redirect thành công, và xác nhận session vẫn chưa đăng nhập.
4. **Để token endpoint ngoài Internet và chờ lỗi mạng.** Nếu callback sai state mà client vẫn đổi code, test có thể fail do network chứ không phát hiện cơ chế đối chiếu bị bỏ qua.
5. **Không giữ session trong MockMvc.** Browser thật quay về với cookie phiên; test mất session sẽ luôn thất bại, kể cả state đúng.
6. **Dùng state từ session khác và cho rằng có thể được chấp nhận nếu chuỗi đúng.** State phải được gắn với authorization request của browser/phân vùng phiên hiện tại.
7. **Cho rằng PKCE hoặc nonce thay thế state.** Chúng bảo vệ các bước khác và cần ca riêng.
8. **Tin rằng callback lỗi luôn tiêu thụ state cũ.** Chính sách giữ/xóa authorization request khi lỗi tùy implementation; cần kiểm tra nếu đây là yêu cầu của hệ thống.
9. **Giả định nhiều tab đăng nhập hoạt động độc lập với repository mặc định.** Thử rõ ràng nếu sản phẩm cần hỗ trợ nhiều authorization requests đồng thời trong cùng session.
10. **Mock `OAuth2LoginAuthenticationFilter` hoặc `OAuth2AuthorizedClientService` trong bài test giao thức.** Thay thế sai tầng có thể khiến test không còn đại diện cho cơ chế đăng nhập cần kiểm chứng.
11. **Nhầm việc kiểm tra state với việc kiểm tra redirect URI hay ID Token.** State là một hàng rào cần thiết, nhưng không thay thế xác thực callback, client registration, token response và principal.

## 12. Mở rộng sang Reactive với WebTestClient

Ứng dụng WebFlux sử dụng `WebTestClient`, `ServerWebExchange`, `WebSession` và các thành phần reactive OAuth2 Client. Nguyên tắc vẫn tương tự:

1. Gửi yêu cầu bắt đầu đăng nhập qua endpoint tương ứng; lấy `state` từ `Location`.
2. Giữ cookie/WebSession mà server cấp và dùng lại khi gửi callback.
3. Gửi callback với state sai/của phiên khác; xác minh login failure, không có token exchange và không có WebSession đã xác thực.
4. Tạo ca state đúng với IdP HTTP test server, xác minh callback được xử lý và request được bảo vệ sau đó thành công.

`SecurityMockServerConfigurers.mockOAuth2Login()` và `mockOidcLogin()` hữu ích cho các ca **đã đăng nhập và phân quyền**, nhưng không đo giao thức state/session. Không dùng `mutateWith(mockOidcLogin())` làm bằng chứng cookie/WebSession đã liên kết đúng với flow thật.

Nếu Reactive ứng dụng dùng `WebSessionServerOAuth2AuthorizationRequestRepository` hoặc một repository tùy chỉnh khác, bài test phải phản ánh đúng cách lưu và tải authorization request của cấu hình đó. Không áp dụng nguyên xi tên bean hoặc nội bộ session repository của Servlet sang WebFlux.

## 13. Checklist hoàn thành ca kiểm thử state/session

- [ ] Request khởi tạo qua `/oauth2/authorization/{registrationId}` thật; state được lấy từ redirect, không tự bịa.
- [ ] Có giữ session/cookie của browser khi gửi callback.
- [ ] Callback với state đúng + code/token response hợp lệ tạo được phiên đăng nhập; đối chứng này dùng IdP test server có kiểm soát.
- [ ] Callback sai state ở cùng session bị từ chối trước token exchange.
- [ ] State từ session A không thể được sử dụng thành công trong session B.
- [ ] Callback không có authorization request đang chờ bị từ chối.
- [ ] Sau callback lỗi, request đến endpoint bảo vệ vẫn chưa được xác thực; nghiệp vụ không chạy.
- [ ] Có phân biệt state mismatch với code sai, token endpoint lỗi, OIDC nonce sai và ID Token validation lỗi.
- [ ] Test không phụ thuộc trạng thái của IdP production, không ghi secrets hoặc token vào log.
- [ ] Kỳ vọng về hai tab, session rotation và callback lặp lại được xác định theo repository và cấu hình thực tế.

**Ghi nhớ:** `state` chỉ có ý nghĩa bảo mật khi ứng dụng **tự tạo, lưu và đối chiếu nó với authorization request của đúng browser/phiên**. Kiểm thử tốt phải bắt đầu flow thật, đổi một phần của callback và chứng minh lần đăng nhập đó không được chấp nhận, không đổi code và không cấp quyền truy cập tài nguyên bảo vệ.
