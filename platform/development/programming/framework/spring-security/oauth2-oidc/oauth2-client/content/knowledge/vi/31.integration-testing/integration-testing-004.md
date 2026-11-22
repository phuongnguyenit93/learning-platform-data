# 31.4. Kiểm thử consent bị từ chối, sai state và callback trùng lặp

## Mục tiêu bài học

Trong **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client**, một luồng đăng nhập không chỉ có happy path “người dùng đồng ý → nhận authorization code → đổi token → tạo session”. Ở môi trường thực tế, người dùng có thể **từ chối consent**, browser có thể quay lại với **`state` sai hoặc thiếu**, và callback có thể bị **gửi hai lần** vì refresh trang, retry của client, proxy, tab cũ hoặc chủ ý replay.

Ba tình huống này đáng được kiểm thử tích hợp vì chúng nằm ở **ranh giới giữa Authorization Server, browser, session, Spring Security OAuth2 Login filter và authorized-client storage**.

Ví dụ:

~~~text
GET /oauth2/authorization/company
    -> 302 tới OP với state=S1

Trường hợp A:
    GET /login/oauth2/code/company?error=access_denied&state=S1

Trường hợp B:
    GET /login/oauth2/code/company?code=C1&state=WRONG

Trường hợp C:
    GET /login/oauth2/code/company?code=C1&state=S1
    GET /login/oauth2/code/company?code=C1&state=S1
~~~

Kỳ vọng không phải mọi trường hợp đều có cùng HTTP status; HTTP response phụ thuộc custom failure handler và `AuthenticationEntryPoint`. Những bất biến quan trọng là:

- **Không tạo Authentication thành công ngoài ý muốn.**
- **Không dùng authorization code/token của transaction khác.**
- **Không bỏ kiểm tra state để “chữa” lỗi callback.**
- **Không trao đổi cùng authorization code hai lần trong một giao dịch chuẩn.**
- **Không giữ hoặc tiết lộ token/authorized client sai sau khi failure.**
- **Không chấp nhận callback của session khác.**

Sau bài học, bạn có thể:

1. Phân biệt consent denial ở OP với API `403 Forbidden` và token-endpoint `invalid_grant`.
2. Mô phỏng `error=access_denied` + `state` hợp lệ qua MockMvc.
3. Lấy `state` thực sự do Spring Security sinh từ authorization redirect thay vì hardcode.
4. Giữ `MockHttpSession` xuyên request bắt đầu login và callback.
5. Kiểm tra `state` thiếu, sai, hết hạn, thuộc session khác và bị thay đổi.
6. Hiểu vai trò của `OAuth2AuthorizationRequestRepository` khi tương quan callback.
7. Kiểm thử callback trùng lặp sau một lần thành công hoặc thất bại.
8. Quan sát số lần gọi token endpoint bằng fake OpenID Provider/Authorization Server.
9. Tạo fake OIDC ID token/JWKS/nonce phục vụ happy-path integration test khi cần.
10. Kiểm tra absence of Authentication và authorized-client persistence sau callback lỗi.
11. Phân biệt authorization-response error với network error và token response error.
12. Viết positive/negative test cho flow nhiều sessions, nhiều tabs và account switching.
13. Tránh false positives do dùng `oidcLogin()` hoặc mock `SecurityContext` trực tiếp.
14. Biết những gì MockMvc có thể kiểm tra và giới hạn của MockMvc không có browser/OP thật.
15. Xây test có thể chạy lặp lại, cô lập, không phụ thuộc AS production và không rò rỉ credentials.

---

## 1. Ba nhánh lỗi cần được phân biệt

Bắt đầu từ một luồng Authorization Code + OIDC:

~~~mermaid
flowchart TD
    A["Portal tạo Authorization Request và state"] --> B["Browser đến Authorization Server"]
    B --> C{"Kết quả ở OP"}
    C -->|"User từ chối consent"| D["Callback error=access_denied + state"]
    C -->|"User chấp nhận"| E["Callback code + state"]
    D --> F["Spring OAuth2 Login failure"]
    E --> G{"state có khớp request đã lưu?"}
    G -->|"Không"| H["Từ chối callback"]
    G -->|"Có"| I["Đổi code tại token endpoint"]
    I --> J{"Code/token hợp lệ?"}
    J -->|"Không"| K["Authorization failure"]
    J -->|"Có"| L["OIDC validation + Authentication"]
    L --> M["Authorized client/session được lưu"]
    M --> N["Callback bị gửi lại"]
    N --> O["Không còn pending request / code đã dùng"]
~~~

### 1.1. Consent bị từ chối

Người dùng hoặc policy tại Authorization Server không cấp authorization. AS thường redirect về client với một OAuth error response:

~~~http
GET /login/oauth2/code/company?error=access_denied&state=S1
~~~

Không có authorization code thành công để đổi token.

### 1.2. Sai `state`

Browser gửi code nhưng `state` không khớp Authorization Request mà client đã lưu:

~~~http
GET /login/oauth2/code/company?code=C1&state=OTHER
~~~

Spring Security không nên sử dụng response này để tạo Authentication.

### 1.3. Callback trùng lặp

Một callback đã được xử lý, rồi được gửi lại:

~~~text
Callback #1: code=C1, state=S1
Callback #2: code=C1, state=S1
~~~

Sau callback thành công, pending Authorization Request đã được tiêu thụ. Authorization code cũng phải là single-use tại AS. Callback thứ hai phải **không hoàn thành một authorization mới**.

### 1.4. Không gom ba loại lỗi thành một nguyên nhân

| Tình huống | Nguồn vấn đề | Kiểm tra quan trọng |
|---|---|---|
| `access_denied` | AS/OP không cấp authorization | Error response, state, failure flow |
| State mismatch | Correlation giữa browser request và callback thất bại | AuthorizationRequestRepository |
| Callback replay | Transaction/code đã được xử lý | One-time request/code, token call count |
| `invalid_grant` tại token endpoint | AS từ chối đổi code hoặc refresh | Token exchange failure |
| ID token issuer/nonce sai | OIDC validation | RP token validation |
| API `403` | Resource Server/domain authorization | Scope/role/owner/tenant |

Việc người dùng từ chối consent **không đồng nghĩa Orders API đã từ chối access token**; thậm chí client có thể chưa nhận được access token nào.

## 2. Các thành phần Spring Security liên quan

| Thành phần | Trách nhiệm trong flow |
|---|---|
| `ClientRegistrationRepository` | Cấu hình OAuth client, AS endpoints, redirect URI |
| `DefaultOAuth2AuthorizationRequestResolver` | Tạo Authorization Request, state, OIDC parameters |
| `OAuth2AuthorizationRequestRedirectFilter` | Xử lý `/oauth2/authorization/{registrationId}` và redirect |
| `OAuth2AuthorizationRequestRepository` | Lưu request chờ callback, thường trong HttpSession |
| `OAuth2LoginAuthenticationFilter` | Xử lý callback tại `/login/oauth2/code/*` |
| `AuthenticationManager` và OAuth2/OIDC providers | Token exchange, OIDC token validation, user authentication |
| `OAuth2AuthorizedClientRepository` / `Service` | Lưu authorized client sau thành công |
| `AuthenticationSuccessHandler` | Điều hướng/xử lý login thành công |
| `AuthenticationFailureHandler` | Điều hướng/xử lý login thất bại |
| `SecurityContextRepository` | Quản lý SecurityContext/session theo cấu hình |

### 2.1. Một authorization request có state riêng

Khi browser gọi:

~~~text
/oauth2/authorization/company
~~~

resolver dựng request có thể chứa:

~~~text
client_id=portal-test-client
response_type=code
scope=openid
redirect_uri=http://localhost/login/oauth2/code/company
state=S1
nonce=N1
~~~

Spring Security lưu request trước redirect để có thể đối chiếu callback.

### 2.2. Callback phải dùng cùng session

Với `HttpSessionOAuth2AuthorizationRequestRepository`, dữ liệu pending authorization gắn với HTTP session.

Nếu bạn bắt đầu flow trong session A mà gửi callback từ session B, callback không có pending request tương ứng.

### 2.3. `state` không thay CSRF token của mọi POST

OAuth state giúp correlate authorization response và giảm login CSRF. Nó không thay CSRF protection cho các POST state-changing requests của Portal sử dụng session cookie.

### 2.4. OIDC còn có nonce và token validation

Ngay cả khi state hợp lệ, OIDC callback thành công còn cần ID token được xác minh signature, issuer, audience, time, nonce khi áp dụng. Bài này tập trung **ba nhánh lỗi**, nhưng happy path test cần thiết lập những điều kiện OIDC đó.

## 3. Chọn cấp độ kiểm thử

### 3.1. Unit test thuần

Có thể gọi trực tiếp `OAuth2AuthorizationRequestRepository` để kiểm tra load/remove semantics.

Phù hợp với custom repository, TTL, one-time consumption và concurrent states.

### 3.2. MockMvc integration test

Chạy Servlet filter chain, bắt đầu flow, lấy redirect state, gửi callback với cùng session.

Phù hợp để test:

- `access_denied`.
- Sai state/thiếu state.
- Failure handler.
- Không tạo session Authentication.
- One-time callback handling.

### 3.3. MockMvc + fake Authorization Server

Bổ sung test HTTP token endpoint, JWKS/ID token và callback thành công rồi replay.

Phù hợp để kiểm tra:

- Code exchange chỉ xảy ra một lần.
- ID token validation.
- Authorized client được lưu.
- Duplicate callback không trao đổi token lần hai.

### 3.4. Browser/E2E

Trình duyệt thật còn liên quan cookies, SameSite, reverse proxy, external origin, navigation và user consent UI. MockMvc không tự mô phỏng đầy đủ những yếu tố đó.

### 3.5. Chọn công cụ theo câu hỏi

| Câu hỏi | Mức test |
|---|---|
| access_denied có đi vào login failure không? | MockMvc |
| callback không đúng state có bị từ chối? | MockMvc |
| state chỉ dùng một lần? | MockMvc/repository test |
| code chỉ đổi token một lần? | MockMvc + fake AS |
| OP phát ID token hợp lệ và principal tạo thành công? | MockMvc + JWKS/ID token test |
| Cookie SameSite đúng trên browser thật? | Browser/E2E |
| AS thật có consent screen đúng? | Staging E2E theo policy |
| API từ chối token sai audience? | Resource Server test riêng |

## 4. Dependencies cho test

Ví dụ Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-client</artifactId>
    </dependency>

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
</dependencies>
~~~

Để fake HTTP AS, bổ sung một server test như WireMock hoặc OkHttp MockWebServer bằng **version tương thích dependency management** của dự án.

Ví dụ dependency minh họa với MockWebServer:

~~~xml
<dependency>
    <groupId>com.squareup.okhttp3</groupId>
    <artifactId>mockwebserver</artifactId>
    <scope>test</scope>
</dependency>
~~~

Nếu build/BOM không quản lý version của dependency này, cần khai báo version test được phê duyệt.

### 4.1. Không cần AS thật cho error-only tests

Nếu test chỉ gửi `error=access_denied` hoặc `state` sai, Spring Security phải từ chối **trước khi gọi token endpoint**.

Bạn có thể dùng fake registration có Authorization/Token/JWKS URIs thuộc `example.test` mà không cần chạy server thực, miễn cấu hình không kích hoạt discovery network ở startup.

### 4.2. Không gửi credential production tới fake AS

Client ID, client secret, code, ID token và access token đều dùng dữ liệu giả.

### 4.3. Test độc lập với Internet

Mỗi negative integration test nên chạy được mà không có kết nối tới OP production hoặc Internet.

## 5. Thiết lập ClientRegistration test

Một fake OIDC registration:

~~~java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

public final class OAuthTestRegistrations {

    private OAuthTestRegistrations() {}

    public static ClientRegistration company() {
        return ClientRegistration
                .withRegistrationId("company")
                .clientId("portal-test-client")
                .clientSecret("test-only-secret")
                .clientAuthenticationMethod(
                        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                        AuthorizationGrantType.AUTHORIZATION_CODE)
                .authorizationUri(
                        "https://op.example.test/authorize")
                .tokenUri(
                        "https://op.example.test/token")
                .jwkSetUri(
                        "https://op.example.test/jwks")
                .issuerUri(
                        "https://op.example.test")
                .redirectUri(
                        "{baseUrl}/login/oauth2/code/{registrationId}")
                .scope("openid", "profile")
                .clientName("Company Test OP")
                .build();
    }
}
~~~

### 5.1. Tại sao không dùng `issuer-uri` discovery từ OP thật?

Bài test muốn kiểm tra client callback handling, không kiểm tra network discovery hoặc tính sẵn sàng của nhà cung cấp ngoài.

Builder với endpoints giả giúp dựng registration mà không cần gọi OP metadata.

### 5.2. OIDC scope

Registration dùng `openid` nên happy path (nếu có) phải có ID token hợp lệ, không chỉ access token JSON.

### 5.3. Redirect template

`{baseUrl}/login/oauth2/code/{registrationId}` là callback mặc định phổ biến của Spring Security OAuth2 Login.

Trong test, `baseUrl` có thể là `http://localhost` do MockHttpServletRequest tạo. Callback path thực cần khớp registration.

### 5.4. Không dùng registration của producer từ test khác

Một testcase nên có registration ID xác định và fake OP riêng để tránh rò state/authorized clients giữa tests.

## 6. Cấu hình SecurityFilterChain cho negative integration tests

Có thể dùng một custom failure handler **chỉ dành cho test** để biến OAuth2 error code thành assertion rõ ràng.

### 6.1. Vì sao custom failure handler?

Default login failure behavior thường redirect browser về `/login?error`. Response có thể là 302 chứ không phải 401.

Nếu test chỉ assert 302, khó biết failure do `access_denied`, `state` sai hay một exception khác.

Test handler dưới đây trả 401 và header chứa **error code đã chuẩn hóa**, không log raw tokens hoặc untrusted error descriptions.

### 6.2. Cấu hình minh họa

~~~java
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class CallbackTestSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error", "/login")
                        .permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(oauth2 -> oauth2
                        .failureHandler((request, response, exception) -> {
                            String code =
                                    "authentication_failed";

                            if (exception
                                    instanceof OAuth2AuthenticationException e) {
                                code = e.getError().getErrorCode();
                            }

                            // Chỉ phục vụ assertion trong test.
                            response.setHeader(
                                    "X-Test-OAuth-Error", code);
                            response.setStatus(
                                    HttpServletResponse.SC_UNAUTHORIZED);
                        }))
                .build();
    }
}
~~~

### 6.3. Cách dùng trong test

Dùng `@SpringBootTest` + `@AutoConfigureMockMvc` và nạp configuration này trong test context, cùng `ClientRegistrationRepository` chứa registration giả.

Không import test-only failure handler vào production. Một ứng dụng production có thể dùng safe redirect/flash message với correlation ID thay vì phơi internal error details cho browser.

### 6.4. Không tin `error_description` từ callback

`error_description` ở HTTP callback là input đi qua browser. Không hiển thị raw value trong HTML/log mà không sanitize, không dùng nó quyết định role hoặc redirect URL.

## 7. Test context hoàn chỉnh cho error callbacks

Một test configuration không cần toàn bộ application:

~~~java
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.web.SecurityFilterChain;

import jakarta.servlet.http.HttpServletResponse;

@SpringBootConfiguration
@EnableAutoConfiguration
public class OAuthErrorTestApplication {

    @Bean
    ClientRegistrationRepository clientRegistrations() {
        return new InMemoryClientRegistrationRepository(
                OAuthTestRegistrations.company());
    }

    @Bean
    SecurityFilterChain testSecurity(HttpSecurity http)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/login", "/error")
                        .permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(oauth2 -> oauth2
                        .failureHandler((request, response, exception) -> {
                            String code =
                                    "authentication_failed";

                            if (exception
                                    instanceof OAuth2AuthenticationException e) {
                                code = e.getError().getErrorCode();
                            }

                            response.setHeader(
                                    "X-Test-OAuth-Error", code);
                            response.setStatus(
                                    HttpServletResponse.SC_UNAUTHORIZED);
                        }))
                .build();
    }
}
~~~

Tên class/package theo project thực tế; có thể đặt test configuration là nested static class trong test source. Những class minh họa như `OAuthTestRegistrations` cần nằm trong test source hoặc được import.

### 7.1. Tại sao không cần controller cho authorization endpoint?

`OAuth2AuthorizationRequestRedirectFilter` bắt `/oauth2/authorization/company` trước MVC controller, tạo redirect.

### 7.2. Tại sao không cần controller cho callback?

`OAuth2LoginAuthenticationFilter` xử lý `/login/oauth2/code/company` qua filter chain.

### 7.3. Không bỏ Spring Security filters

Dùng `@AutoConfigureMockMvc` với filters được bật. Nếu dùng manual `MockMvcBuilders`, phải apply `springSecurity()`/chain phù hợp.

### 7.4. Context rộng hay hẹp?

Nếu ứng dụng có security config phức tạp, test này có thể dùng test-specific configuration để cô lập error behavior. Ngoài ra cần một nhóm integration test khác nạp actual production config để đảm bảo wiring của hệ thống không khác expectation.

## 8. Bắt đầu authorization flow và lấy state thật

**Không hardcode `state=S1` trong integration test** khi dùng resolver/repository thật. Phải lấy state mà Spring Security vừa sinh.

### 8.1. Helper `beginLogin()`

~~~java
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.util.UriComponentsBuilder;

import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

record LoginAttempt(
        MockHttpSession session,
        String state,
        String nonce,
        String authorizationRedirect) {
}

LoginAttempt beginLogin(MockMvc mvc) throws Exception {
    MvcResult result = mvc.perform(
                    get("/oauth2/authorization/company"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

    String redirect = result.getResponse().getRedirectedUrl();

    var query = UriComponentsBuilder
            .fromUriString(redirect)
            .build()
            .getQueryParams();

    String state = query.getFirst("state");
    String nonce = query.getFirst("nonce");

    MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);

    org.assertj.core.api.Assertions.assertThat(state)
            .isNotBlank();
    org.assertj.core.api.Assertions.assertThat(session)
            .isNotNull();

    return new LoginAttempt(
            session, state, nonce, redirect);
}
~~~

### 8.2. Vì sao giữ `MockHttpSession`?

Authorization Request repository mặc định gắn với session. Nếu callback dùng session mới, bạn chỉ đang test “không tìm được authorization request”, không test đầy đủ case user từ chối consent với **state đúng**.

### 8.3. `nonce` dùng cho happy-path OIDC test

Nếu scope có `openid`, authorization redirect thường chứa nonce theo cấu hình. Khi fake OP phát ID token trong positive test, claim nonce phải tương ứng giá trị mà OP nhìn thấy trong authorization request.

### 8.4. Redirect URI là dữ liệu cần quan sát

Bên cạnh state, có thể assert:

~~~text
response_type=code
client_id=portal-test-client
redirect_uri=...
scope chứa openid
state không rỗng
~~~

Một test state mismatch có ý nghĩa khi Authorization Request thật đã được tạo từ đúng registration và lưu trong cùng session.

### 8.5. Dùng query parser thay regex

State có thể chứa ký tự cần URL encoding. Dùng URI parser hoặc decode đúng chuẩn thay vì cắt chuỗi bằng `substring` dựa trên vị trí cố định.

## 9. Test A — Consent bị từ chối với state hợp lệ

Một user chọn “Deny” ở consent screen hoặc AS quyết định không cấp authorization. AS trả error response:

~~~http
GET /login/oauth2/code/company?error=access_denied&state=STATE
~~~

### 9.1. Test với MockMvc

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest(classes = OAuthErrorTestApplication.class)
@AutoConfigureMockMvc
class ConsentDenialIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void userDenyingConsentFailsWithoutLogin()
            throws Exception {

        LoginAttempt pending = beginLogin(mvc);

        mvc.perform(get("/login/oauth2/code/company")
                        .session(pending.session())
                        .param("error", "access_denied")
                        .param("state", pending.state()))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        "X-Test-OAuth-Error", "access_denied"));
    }
}
~~~

Helper `beginLogin(...)` và record `LoginAttempt` ở mục trước được đặt vào class/utility test thích hợp.

### 9.2. Tại sao assert code `access_denied`?

AS trả error code theo OAuth authorization response. Spring Security xử lý callback như một authentication failure, không có successful authorization code để đổi token.

### 9.3. Không khẳng định HTTP status bắt buộc là 401

Trong ví dụ test-only handler chọn trả 401. Ở production, failure handler mặc định hoặc custom có thể trả 302 tới trang login kèm thông báo, hoặc một response khác theo UX.

**Cần assert status theo handler mà ứng dụng thực sự cấu hình.**

### 9.4. Không xem user refusal là application exception “không mong đợi”

Đây là nhánh nghiệp vụ bình thường: user hoặc AS có quyền từ chối consent. UI nên cho lựa chọn quay lại hoặc thử với quyền hạn khác, không tạo vòng lặp redirect vô hạn.

## 10. Test consent denial không tạo authenticated session

Sau denial, browser vẫn có thể giữ HttpSession đã chứa pending Authorization Request trước đó. Điều cần bảo đảm là **không tạo user Authentication thành công**.

### 10.1. Truy cập tài nguyên protected sau failure

~~~java
LoginAttempt pending = beginLogin(mvc);

mvc.perform(get("/login/oauth2/code/company")
                .session(pending.session())
                .param("error", "access_denied")
                .param("state", pending.state()))
        .andExpect(status().isUnauthorized());

mvc.perform(get("/private")
                .session(pending.session()))
        .andExpect(status().is3xxRedirection());
~~~

Ví dụ assume `/private` được bảo vệ bằng `authenticated()` và entry point browser của test redirect về login. Nếu test chain trả 401 thay redirect, adjust assertion theo chính sách.

### 10.2. Session còn tồn tại không có nghĩa login thành công

Việc `MockHttpSession` chưa bị invalidate không chứng minh có Authentication. Session có thể tồn tại để giữ saved request, CSRF tokens hoặc error attributes.

### 10.3. Không tự lưu `OidcUser` vào session khi denial

Không gọi custom success logic khi callback có error response. Failure handler không nên tạo `OAuth2AuthorizedClient` mới.

### 10.4. Kiểm tra authorized client store

Nếu ứng dụng dùng `OAuth2AuthorizedClientService`, có thể assert:

~~~java
OAuth2AuthorizedClient client =
        authorizedClientService.loadAuthorizedClient(
                "company", "alice");

assertThat(client).isNull();
~~~

Điều này chỉ có ý nghĩa nếu setup test dùng **đúng service/repository mà production flow lưu token** và `alice` là principal key kỳ vọng. Với session repository, phải kiểm tra session store tương ứng; đừng kiểm tra nhầm một in-memory service không được wiring vào filter.

## 11. Test consent denial không gọi token endpoint

Khi callback chứa `error=access_denied`, **không có authorization code thành công** để gửi đến token endpoint.

Trong test có fake AS, đặt counter:

~~~java
AtomicInteger tokenEndpointCalls =
        new AtomicInteger();
~~~

Sau callback denied:

~~~java
assertThat(tokenEndpointCalls.get()).isZero();
~~~

### 11.1. Không test bằng token endpoint thật

Dùng fake HTTP server và đếm request tới `/token`; không gửi client secret hoặc token production.

### 11.2. Vì sao kiểm tra request count?

Một bug nghiêm trọng có thể cố đổi code dù authorization response là error. Negative test nên phát hiện việc token endpoint bị gọi ngoài ý muốn.

### 11.3. Fake OP cần phân biệt endpoints

~~~text
/authorize  -> redirect do client tạo, browser chưa thật tới fake OP
/token      -> fake server đếm token requests
/jwks       -> fake server trả public keys cho OIDC happy path
/userinfo   -> chỉ nếu flow sử dụng UserInfo
~~~

Với test denial, thường chỉ cần inspect authorization redirect và gửi callback trực tiếp; không cần triển khai consent UI thật.

## 12. Consent bị từ chối khác thiếu scope

Hai trường hợp có thể bị nhầm:

### 12.1. Consent refusal

~~~text
Authorization endpoint response:
  error=access_denied
  state=S1
~~~

Không có successful authorization result.

### 12.2. Token có scope ít hơn kỳ vọng

AS có thể trả successful token response nhưng với scopes theo policy (tùy profile). Khi đó client/API phải kiểm tra scopes được cấp trước khi thực hiện tác vụ.

### 12.3. API trả 403

Nếu Portal đã có access token nhưng Orders API từ chối `orders.write`, đó là resource authorization, **không phải consent denial callback**.

### 12.4. `access_denied` có thể có nhiều nguyên nhân

AS có thể trả `access_denied` vì user từ chối, policy chặn client, admin consent chưa được cấp hoặc lý do khác. Client không nên khẳng định chắc chắn user đã bấm nút “Deny” nếu không có thông tin tin cậy.

## 13. Test B — Sai state

Bắt đầu flow hợp lệ:

~~~text
Browser -> /oauth2/authorization/company
  -> state = S1
  -> session có pending Authorization Request S1
~~~

Sau đó callback bị sửa:

~~~http
GET /login/oauth2/code/company?code=C1&state=ATTACKER_STATE
~~~

### 13.1. Test bằng MockMvc

~~~java
@Test
void rejectsCallbackWithWrongState() throws Exception {
    LoginAttempt pending = beginLogin(mvc);

    mvc.perform(get("/login/oauth2/code/company")
                    .session(pending.session())
                    .param("code", "fake-code")
                    .param("state", "totally-wrong-state"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().exists("X-Test-OAuth-Error"));
}
~~~

### 13.2. Vì sao không hardcode error code duy nhất?

Tùy Spring Security version và nhánh xử lý, callback state không khớp có thể được biểu diễn bằng một OAuth2 authentication error như `authorization_request_not_found` hoặc một code khác.

Invariant cần test là:

- Không thành công.
- Không có token endpoint exchange.
- Không có authorized client mới.
- Authentication không được tạo từ callback.

Nếu product contract yêu cầu error code chính xác, assert code sau khi khóa version/config và biết rõ error mapping.

### 13.3. State mismatch cần được phát hiện trước token exchange

Đặc biệt quan trọng: không gửi `fake-code` đến token endpoint đã cấu hình khi không có pending Authorization Request khớp.

### 13.4. Không tin redirect URI path một mình

`/login/oauth2/code/company` cho biết routing, không đủ để chứng minh browser đã khởi tạo request phù hợp. State correlation là lớp bảo vệ quan trọng.

## 14. State sai có thể không xóa pending request hợp lệ

Với session-backed request repository, một callback state sai thường **không tìm được request tương ứng**.

Điều đó không đồng nghĩa mọi implementation tự động xóa pending request có state S1.

### 14.1. Cần hiểu behavior của repository

Một repository có thể:

- Không remove S1 vì incoming state không khớp.
- Remove S1 do failure cleanup custom.
- Có TTL và giới hạn pending requests.
- Hỗ trợ một hoặc nhiều requests tùy implementation.

Đừng tự viết test mặc định rằng state mismatch luôn consume request ban đầu.

### 14.2. Nếu S1 vẫn đang pending?

Một callback đúng S1 sau đó có thể tiếp tục flow tùy state store/session/AS code validity.

Đây là lý do quan trọng để test **policy xử lý callback sai**, thay vì chỉ xem một HTTP response 401.

### 14.3. Tránh tạo cửa sổ replay quá rộng

Pending request cần có TTL ngắn và cleanup phù hợp. Một callback sai không được khiến trạng thái lưu vô hạn hoặc rò sang user/session khác.

### 14.4. Không “fallback” sang state khác trong session

Nếu state không tìm thấy, không chọn pending request mới nhất hoặc registration có cùng client ID rồi tiếp tục. Cách này phá correlation và có thể gây login CSRF/mix-up.

## 15. Test state thiếu, empty hoặc duplicated query

Không chỉ state sai, callback có thể:

~~~text
?code=C1
?code=C1&state=
?code=C1&state=S1&state=S2
~~~

### 15.1. Missing state

~~~java
@Test
void rejectsCallbackWithoutState() throws Exception {
    LoginAttempt pending = beginLogin(mvc);

    mvc.perform(get("/login/oauth2/code/company")
                    .session(pending.session())
                    .param("code", "fake-code"))
            .andExpect(status().isUnauthorized());
}
~~~

### 15.2. Empty state

~~~java
mvc.perform(get("/login/oauth2/code/company")
                .session(pending.session())
                .param("code", "fake-code")
                .param("state", ""))
        .andExpect(status().isUnauthorized());
~~~

### 15.3. Duplicated state parameters

~~~java
mvc.perform(get("/login/oauth2/code/company")
                .session(pending.session())
                .param("code", "fake-code")
                .param("state", pending.state(), "different-state"))
        .andExpect(status().isUnauthorized());
~~~

Hành vi exact parsing của duplicated HTTP parameters phụ thuộc framework/container/version; đây là test input để ghi nhận policy của ứng dụng. **Không chấp nhận parameter ambiguity** làm một state bị diễn giải khác giữa security filter và business logic.

### 15.4. Encoding edge cases

Có thể test state chứa URL encoding, whitespace, UTF-8 hoặc input quá dài nếu ứng dụng có custom parsing/proxy. Không dùng regex tự chế để quyết định state có hợp lệ trước khi Spring Security correlate authorization request.

## 16. Test C — Callback từ session khác

Một attacker có thể cố sử dụng callback của session A trong session B.

~~~text
Session A:
  pending state=S1

Session B:
  không có request S1

Callback trên B:
  code=C1, state=S1
~~~

### 16.1. Test

~~~java
import org.springframework.mock.web.MockHttpSession;

@Test
void rejectsCallbackFromDifferentSession() throws Exception {
    LoginAttempt pending = beginLogin(mvc);

    MockHttpSession anotherSession =
            new MockHttpSession();

    mvc.perform(get("/login/oauth2/code/company")
                    .session(anotherSession)
                    .param("code", "fake-code")
                    .param("state", pending.state()))
            .andExpect(status().isUnauthorized());
}
~~~

### 16.2. Vì sao kiểm tra case này?

State không chỉ là chuỗi ngẫu nhiên, mà còn phải được ràng buộc với pending Authorization Request đúng browser/session.

### 16.3. Không tìm toàn bộ sessions theo state

Khi callback session B không có request S1, backend không được search state trong tất cả sessions rồi tạo Authentication trên B.

### 16.4. Cookie và SameSite

MockMvc có thể giả lập session, nhưng không mô phỏng đầy đủ browser cookie policies. Kiểm tra Secure/HttpOnly/SameSite/forwarded headers trong browser/E2E tests nếu có yêu cầu.

## 17. Test D — Callback trùng lặp sau consent denial

Ngay cả error callback cũng có thể được gửi lại bởi browser.

~~~text
Begin:
  pending state = S1

Callback #1:
  error=access_denied&state=S1

Callback #2:
  error=access_denied&state=S1
~~~

### 17.1. Kỳ vọng

- Lần đầu là failure do `access_denied`.
- Lần hai không được “mở lại” transaction.
- Không trao token.
- Không tạo Authentication hoặc authorized client.

### 17.2. Ví dụ

~~~java
@Test
void repeatedDenialDoesNotCreateLogin()
        throws Exception {

    LoginAttempt pending = beginLogin(mvc);

    mvc.perform(get("/login/oauth2/code/company")
                    .session(pending.session())
                    .param("error", "access_denied")
                    .param("state", pending.state()))
            .andExpect(status().isUnauthorized());

    mvc.perform(get("/login/oauth2/code/company")
                    .session(pending.session())
                    .param("error", "access_denied")
                    .param("state", pending.state()))
            .andExpect(status().isUnauthorized())
            .andExpect(header().exists("X-Test-OAuth-Error"));
}
~~~

### 17.3. Error code lần hai có thể khác

Lần đầu báo `access_denied`; lần hai có thể báo missing authorization request vì S1 đã bị remove. Test không nên luôn đòi code `access_denied` ở cả hai lần trừ khi đó là contract riêng.

### 17.4. Giới hạn của test này

Nó kiểm tra duplicate **failure callback**. Để chứng minh callback **thành công** không bị xử lý hai lần và token endpoint chỉ được gọi một lần, cần happy-path integration setup ở những mục tiếp theo.

## 18. Vì sao callback thành công cần fake OP?

Một callback:

~~~text
code=C1&state=S1
~~~

với state hợp lệ sẽ khiến Spring Security cố đổi code tại token endpoint. Nếu `token-uri` là `https://op.example.test/token` nhưng không có fake server, test sẽ lỗi mạng và **không đạt được happy path**.

### 18.1. Không nên fake success bằng `oidcLogin()`

`oidcLogin()` chỉ đặt OIDC principal giả cho MockMvc request, không chạy:

- OAuth2 Login callback filter.
- State correlation.
- Authorization code token exchange.
- ID token verification.
- Authorized-client persistence.

Dùng nó để test callback replay sẽ tạo **false positive**.

### 18.2. Không nên bypass AuthenticationManager

Nếu tự mock `AuthenticationManager` để luôn trả Authentication thành công mà không chạy OIDC validator, có thể kiểm tra một phần filter wiring nhưng không chứng minh ID token validation. Hãy mô tả rõ phạm vi khi chọn mức mock này.

### 18.3. Fake OP nên hỗ trợ tối thiểu

~~~text
GET /jwks
  -> public RSA JWK

POST /token
  -> JSON access_token + id_token ký bằng private key test

GET /userinfo
  -> chỉ nếu OIDC flow cấu hình cần UserInfo
~~~

Không cần fake consent UI; MockMvc đã có thể gửi browser callback trực tiếp.

## 19. Fake Authorization Server và request counting

Bạn có thể dùng WireMock hoặc MockWebServer. Ví dụ cấu trúc một fake OP với test HTTP server:

~~~text
Fake OP:
  issuer = http://127.0.0.1:<dynamic-port>
  authorization endpoint = issuer + /authorize
  token endpoint = issuer + /token
  JWKS = issuer + /jwks

Test shared state:
  tokenCalls: AtomicInteger
  expectedCode: "code-first"
  expectedNonce: lấy từ Authorization Request
  idToken: JWT ký RS256 bởi test key
~~~

### 19.1. Token response hợp lệ

~~~json
{
  "access_token": "test-access-A1",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "openid",
  "id_token": "SIGNED_TEST_ID_TOKEN"
}
~~~

Để Spring Security OIDC Client chấp nhận response, `id_token` cần là JWT test được ký hợp lệ và claims đáp ứng client registration/nonce.

### 19.2. Mỗi test nên có server state riêng

Không dùng một tokenCalls counter/static mock response bị chia sẻ giữa tests chạy song song mà không reset/isolate.

### 19.3. Authorization endpoint không cần nhận HTTP trong MockMvc

Spring Security tạo redirect URL; MockMvc không tự follow redirect ra fake OP. Test đọc redirect, lấy `state`/`nonce`, rồi gửi callback giả như browser quay lại.

### 19.4. Dynamic port

Fake server nên bind port 0 (random) rồi dựng `ClientRegistration` theo URL thực nhận, tránh port collision giữa test runs.

### 19.5. Không trỏ fake issuer/JWKS vào OP production

Đây là test identity provider, dùng private key tạm và HTTP localhost. Production phải có HTTPS/trust policies riêng.

## 20. Dựng ID token ký bằng test RSA key

Nếu dùng OIDC happy path, access token JSON **chưa đủ**; Spring Security cần ID token hợp lệ.

Có thể dùng Nimbus JOSE JWT (thường là dependency gián tiếp của Spring Security OAuth2 JOSE).

### 20.1. Sinh RSA key

~~~java
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;

RSAKey testRsaKey = new RSAKeyGenerator(2048)
        .keyID("test-key-1")
        .generate();
~~~

### 20.2. Public JWKS

~~~java
import com.nimbusds.jose.jwk.JWKSet;

String jwksJson =
        new JWKSet(testRsaKey.toPublicJWK())
                .toString();
~~~

Fake OP `GET /jwks` trả JSON với public RSA key; không phát private key qua JWKS.

### 20.3. Ký ID token

~~~java
import java.time.Instant;
import java.util.Date;

import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

static String signIdToken(
        RSAKey key,
        String issuer,
        String clientId,
        String nonce) throws Exception {

    Instant now = Instant.now();

    JWTClaimsSet claims = new JWTClaimsSet.Builder()
            .issuer(issuer)
            .subject("alice-123")
            .audience(clientId)
            .issueTime(Date.from(now))
            .expirationTime(Date.from(now.plusSeconds(600)))
            .claim("nonce", nonce)
            .build();

    JWSHeader header = new JWSHeader.Builder(
            JWSAlgorithm.RS256)
            .keyID(key.getKeyID())
            .build();

    SignedJWT jwt = new SignedJWT(header, claims);
    jwt.sign(new RSASSASigner(key.toPrivateKey()));

    return jwt.serialize();
}
~~~

### 20.4. Nonce phải khớp yêu cầu từ browser

Spring Security có thể đưa nonce dưới dạng đã biến đổi/hash vào authorization redirect theo implementation. Khi fake OP xây ID token, hãy **echo chính giá trị nonce mà OP nhận từ authorization request**, không tự lấy random nonce khác.

### 20.5. Issuer và audience

- `iss`: phải khớp expected issuer của ClientRegistration.
- `aud`: phải chứa client ID của test RP.
- `exp` và `iat`: hợp lệ theo clock và policy.
- `sub`: có giá trị và đúng profile.
- `nonce`: đúng authentication transaction nếu yêu cầu.

### 20.6. UserInfo

Nếu registration chỉ yêu cầu `openid` và không cấu hình UserInfo endpoint, happy path có thể tránh thêm HTTP UserInfo request. Nếu cần UserInfo, fake server phải trả claims đúng contract, bao gồm `sub` khớp ID token theo OIDC rules.

### 20.7. Không dùng JWT test để chứng minh OP thật

Chữ ký hợp lệ bởi test key chỉ chứng minh Spring Security có thể verify một test ID token qua test JWKS. Nó không thay kiểm thử cấu hình production issuer/keys/metadata.

## 21. Điều phối fake server: HTTP token endpoint

Một test double có thể nhận các requests:

~~~http
POST /token HTTP/1.1
Host: 127.0.0.1:<port>
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <test-client-credentials>

grant_type=authorization_code&code=code-first&redirect_uri=...
~~~

Ở request đầu tiên với code hợp lệ, trả access token/ID token. Ở request thứ hai với cùng code, trả lỗi:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{"error":"invalid_grant"}
~~~

### 21.1. Counter

~~~java
AtomicInteger tokenEndpointCalls = new AtomicInteger();

int call = tokenEndpointCalls.incrementAndGet();
~~~

### 21.2. Code phải single-use

Fake AS nên lưu trạng thái code đã được redeem:

~~~text
code-first -> unused
First POST  -> used, return token response
Second POST -> invalid_grant
~~~

### 21.3. Vì sao cần fake AS bảo vệ code replay?

Giả sử client bị lỗi và gọi token endpoint lần hai. Nếu fake AS trả token cho mọi request, test có thể không phát hiện việc code redemption không đúng.

### 21.4. Kiểm tra client authentication

Đối với confidential client dùng `client_secret_basic`, fake endpoint có thể kiểm tra Authorization Basic header. Không log raw client secret hoặc header trong test output.

### 21.5. Token response không được trả ID token sai audience

Nếu ID token dành cho client khác, happy-path callback phải thất bại do OIDC validation. Tạo valid fixture trước rồi mới test replay để tránh nhầm nguyên nhân.

## 22. Test E — Callback thành công được xử lý một lần

Khi fake OP/JWKS đã được cấu hình đúng, test tiến hành:

1. Bắt đầu Authorization Request.
2. Lấy state và nonce.
3. Fake OP phát ID token hợp lệ với nonce đó.
4. Gửi callback `code=code-first`, `state=S1`.
5. Assert authentication success và/hoặc redirect theo success handler.
6. Đọc `MockHttpSession` sau success.
7. Gửi lại **cùng code và state**.
8. Assert callback thứ hai bị từ chối.
9. Assert token endpoint chỉ có **một** code redemption.
10. Assert authorized client không bị tạo mới hoặc bị thay đổi bởi replay.

### 22.1. Test skeleton

~~~java
@Test
void successfulCallbackIsNotProcessedTwice()
        throws Exception {

    LoginAttempt pending = beginLogin(mvc);

    // Fake OP chuẩn bị id_token ký bằng test key,
    // issuer/audience đúng và nonce = pending.nonce().
    fakeOp.prepareSuccessfulCode(
            "code-first",
            pending.nonce(),
            "alice-123");

    MvcResult first = mvc.perform(
                    get("/login/oauth2/code/company")
                            .session(pending.session())
                            .param("code", "code-first")
                            .param("state", pending.state()))
            .andExpect(status().is3xxRedirection())
            .andReturn();

    assertThat(fakeOp.tokenCalls()).isEqualTo(1);

    MockHttpSession activeSession =
            (MockHttpSession) first.getRequest()
                    .getSession(false);

    mvc.perform(
                    get("/login/oauth2/code/company")
                            .session(activeSession)
                            .param("code", "code-first")
                            .param("state", pending.state()))
            .andExpect(status().isUnauthorized());

    assertThat(fakeOp.tokenCalls()).isEqualTo(1);
}
~~~

`fakeOp.prepareSuccessfulCode(...)` và `fakeOp.tokenCalls()` là **test harness API do ứng dụng tự hiện thực**, không phải class có sẵn của Spring Security. Nó được mô tả tại các mục 19–21.

### 22.2. Vì sao lấy session sau success?

Spring Security có thể đổi session ID theo session-fixation protection và lưu SecurityContext trong session đã được cập nhật.

Trong MockMvc, cần giữ session state chính xác cho request replay; không tự tạo session khác rồi ngộ nhận đã test duplicate callback cùng browser.

### 22.3. Success redirect chưa đủ

Một 302 có thể là redirect thành công hoặc failure redirect, tùy handler. Với positive test nên assert Location/success marker hoặc user Authentication/session theo cấu hình cụ thể.

Nếu dùng test failure handler trả 401, callback success mặc định redirect 302; vẫn cần thêm positive assertion để tránh false positive do redirect khác.

### 22.4. Counter là bằng chứng trực tiếp

Nếu replay bị chặn **trước token exchange**, fake AS chỉ nhận một request tới token endpoint.

### 22.5. Nếu counter thành hai?

Có thể pending Authorization Request chưa được consume đúng hoặc test setup đã tạo transaction thứ hai. Cần phân biệt lỗi client correlation với fake AS behavior.

### 22.6. Token response second attempt

Nếu lỗi cho phép token exchange hai lần, fake AS phải trả `invalid_grant` cho lần hai. Lúc đó callback cũng không được tạo Authentication mới.

## 23. Sau replay, authorized client phải không bị thay đổi

Callback trùng lặp không chỉ là vấn đề HTTP status; nó có thể tác động authorized-client storage.

### 23.1. Kiểm tra store

Với `OAuth2AuthorizedClientService` và principal key tương ứng:

~~~java
OAuth2AuthorizedClient beforeReplay =
        service.loadAuthorizedClient(
                "company", "alice-123");

assertThat(beforeReplay).isNotNull();

performDuplicateCallback();

OAuth2AuthorizedClient afterReplay =
        service.loadAuthorizedClient(
                "company", "alice-123");

assertThat(afterReplay.getAccessToken().getTokenValue())
        .isEqualTo(
                beforeReplay.getAccessToken().getTokenValue());
~~~

`performDuplicateCallback()` chỉ là helper mô tả; test cần sử dụng session/callback đúng như mục 22.

### 23.2. Lưu ở session hay service?

Nếu ứng dụng dùng `HttpSessionOAuth2AuthorizedClientRepository`, phải kiểm tra nơi nó thực sự lưu token. Đừng assert vào một `InMemoryOAuth2AuthorizedClientService` không được filter sử dụng rồi kết luận không có token.

### 23.3. Không xóa session đã authenticated do replay sai ngoài policy

Một duplicate callback bất hợp lệ sau login có thể được failure handler xử lý. Cần xác định policy: giữ session đã authenticated hay logout để an toàn.

Không mặc định handler failure của callback thứ hai phải giữ login đầu tiên; đó là lựa chọn ứng dụng cần test và thiết kế rõ ràng.

### 23.4. Tránh login session bị thay bằng identity khác

Nếu replay hoặc mix-up callback dẫn tới Authentication khác, đây là security issue. Test nên kiểm tra principal `iss` + `sub` trước/sau theo policy.

## 24. Code replay và state replay là hai hàng rào độc lập

### 24.1. State correlation

Client phải có Authorization Request tương ứng với incoming state/session.

### 24.2. Authorization code single-use

Authorization Server không được đổi một authorization code thành token nhiều lần.

### 24.3. Khi state bị mất

Client nên từ chối **trước token endpoint**. Do đó code single-use không phải lớp thay thế state validation.

### 24.4. Khi state bị tái tạo trái phép

Nếu custom repository cho phép reuse state/pending transaction, AS code single-use vẫn giúp giảm rủi ro, nhưng client logic vẫn sai.

### 24.5. Callback lần hai với code khác nhưng state cũ

Một attacker có thể thử:

~~~text
First:  code=C1, state=S1
Second: code=C2, state=S1
~~~

Dù code C2 mới, pending request S1 đã bị consume sau first callback. Client phải không cho phép response thứ hai dùng state cũ.

## 25. Test F — Callback sai state không làm token exchange

Cần một fake OP token counter để chứng minh behavior.

~~~java
@Test
void invalidStateNeverReachesTokenEndpoint()
        throws Exception {

    LoginAttempt pending = beginLogin(mvc);

    int before = fakeOp.tokenCalls();

    mvc.perform(
                    get("/login/oauth2/code/company")
                            .session(pending.session())
                            .param("code", "code-first")
                            .param("state", "wrong-state"))
            .andExpect(status().isUnauthorized());

    assertThat(fakeOp.tokenCalls()).isEqualTo(before);
}
~~~

### 25.1. Vì sao không chỉ assert 401?

Một implementation có thể gửi code đi token endpoint rồi mới thất bại. Kết quả cuối là 401 nhưng secret/code đã đi sai ranh giới.

### 25.2. Không cần code thật để test wrong state

Vì state phải bị từ chối trước token exchange, code chỉ cần là fixture bất kỳ và fake server count vẫn bằng zero.

### 25.3. Sai registration và state

Bạn cũng có thể gửi response tới callback path registration khác:

~~~text
Begin /oauth2/authorization/company
Callback /login/oauth2/code/other-client?code=C1&state=S1
~~~

Tùy Spring Security implementation, registration được xác định từ stored Authorization Request, không chỉ từ URL suffix. Test cần khẳng định callback/mapping policy **không cho mix-up** và không dùng token endpoint/provider không mong đợi.

### 25.4. Không tự suy ra mix-up protection chỉ từ callback path

State và OIDC issuer/audience/nonce validation vẫn là những kiểm tra cần thiết. Khi hỗ trợ nhiều Authorization Servers, còn cần AS issuer identification nếu protocol/profile/framework hỗ trợ.

## 26. Test nhiều tabs và pending requests

Một browser có thể mở hai tab:

~~~text
Tab A: GET /oauth2/authorization/company -> state=A
Tab B: GET /oauth2/authorization/partner -> state=B
~~~

### 26.1. Vấn đề repository mặc định

`HttpSessionOAuth2AuthorizationRequestRepository` ở một số phiên bản/implementation giữ một pending Authorization Request cho mỗi session. Flow B có thể ghi đè flow A.

Không nhầm hành vi này với một state mismatch security bug khi hai tabs đua nhau.

### 26.2. Nếu sản phẩm yêu cầu concurrent login tabs

Dùng custom `OAuth2AuthorizationRequestRepository` hỗ trợ nhiều pending states, TTL, giới hạn số entry, one-time removal và session binding.

### 26.3. Tests cần có

- Bắt đầu A và B trong cùng session.
- Nhận callback B trước A.
- Callback nào được cho phép/theo policy?
- Pending state còn lại có bị dùng nhầm?
- Không tạo Authentication sai issuer/tenant?
- Không consume cùng state hai lần.

### 26.4. Không “sửa” bằng cách bỏ state validation

Nếu flow A bị mất correlation, user nên bắt đầu lại login A. Không chấp nhận callback không khớp chỉ vì browser có session còn sống.

## 27. State replay và tenant binding

Trong SaaS, một authorization transaction có thể còn gắn:

~~~text
state=S1
tenant=acme
registration=company
expectedIssuer=https://op.example.test
returnPath=/t/acme/home
~~~

### 27.1. Đúng tenant ở callback

Không đọc tenant từ query callback. Nó phải được bind với pending state ở server-side store.

### 27.2. Duplicate callback không được tạo tenant context mới

Nếu state S1 đã được consume, callback replay không được làm app đổi active tenant sang Acme hoặc tạo thêm local user membership.

### 27.3. Test cross-tenant mix-up

- Start Acme flow, callback state từ Globex.
- Start Company registration, callback có issuer khác.
- Start với returnPath Acme, callback cố redirect Globex.
- User authenticated nhưng không thuộc tenant được chọn.

### 27.4. Không dùng email làm identity toàn cục

Hai issuers có thể cùng `sub` hoặc email. Identity key nên dựa trên issuer+subject và ứng dụng còn phải kiểm tra membership trong tenant.

## 28. Failure handler cần có chính sách rõ ràng

Các failure states có thể xảy ra khi user chưa authenticated, hoặc user đang có session login trước và cố liên kết thêm provider.

### 28.1. Trang lỗi an toàn

Nên thông báo mức vừa đủ:

~~~text
Không hoàn thành đăng nhập hoặc cấp quyền.
Vui lòng thử lại hoặc liên hệ quản trị viên.
~~~

Không in raw `state`, authorization code, ID token, refresh token hoặc stack trace ra browser.

### 28.2. Không redirect tới URL lấy từ callback

Nếu callback chứa `returnTo=https://attacker.example`, không dùng tham số đó để điều hướng sau lỗi.

### 28.3. Phân biệt voluntary denial với security incident

`access_denied` có thể là user refusal bình thường, không nhất thiết báo động bảo mật. State mismatch/replay nhiều lần có thể đáng ghi nhận theo policy.

### 28.4. Logging

Có thể log:

~~~text
correlationId=...
registrationId=company
category=OAUTH_LOGIN_FAILURE
errorCode=access_denied
statePresent=true
sessionBoundRequestFound=true
~~~

Tránh log raw code/state/session cookie. Dữ liệu log phải được hạn chế truy cập và retention phù hợp.

### 28.5. Session cũ sau failure

Nếu user đã đăng nhập trước khi bắt đầu một OAuth2 authorization flow khác, failure handler có thể giữ hoặc clear existing session tùy chính sách security/account linking.

Test phải có case “user đã authenticated sẵn” nếu ứng dụng hỗ trợ account linking hoặc đăng nhập lại, không chỉ anonymous start.

## 29. Test matrix tổng hợp

| Nhóm | Tình huống | Kết quả chính |
|---|---|---|
| Consent | `error=access_denied`, state đúng | Login failure, không token exchange |
| Consent | `error=access_denied`, state sai | Reject; không token |
| Consent | `error_description` độc hại | Không reflected XSS/log leak |
| State | State đúng + code hợp lệ | Có thể hoàn tất happy path |
| State | State sai | Reject trước token request |
| State | Không có state | Reject |
| State | State rỗng | Reject |
| State | Nhiều state parameters | Reject hoặc xử lý deterministic an toàn |
| Session | Callback ở session khác | Reject |
| Session | Session hết hạn | Reject, khởi tạo flow mới |
| Callback | Lặp denial callback | Không tạo login/token |
| Callback | Lặp success callback | Không exchange code lần hai |
| Callback | Cùng state, code khác | Không cho reuse transaction |
| Callback | Callback tới wrong registration | Không mix-up |
| Token | Fake AS phát invalid_grant | Failure; không tạo principal |
| Token | Fake AS phát ID token sai issuer | Reject trong OIDC validation |
| Token | Fake AS phát ID token sai nonce | Reject |
| Token | Fake AS token endpoint 503 | Failure/retry policy |
| Persistence | Success save authorized client | Token được lưu đúng principal |
| Persistence | Failure không save client mới | Không có token mới |
| Identity | Replay sau user A login | Không thay Authentication thành B |
| Tenant | State thuộc tenant A, callback giả tenant B | Không đổi active tenant |
| Concurrency | Hai tabs khác state | Theo repository/policy; không lẫn |
| CSRF | POST ứng dụng không có csrf token | Reject theo web policy |
| Browser | SameSite/cookie redirect | E2E browser test |

## 30. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
|---|---|---|
| Consent denied test gọi token endpoint | Callback error bị xử lý sai | OAuth2Login filter branch |
| Test denial nhận 302 thay 401 | Default failure redirect | Assert failure URL hoặc custom test handler |
| State đúng nhưng callback vẫn fail | Không giữ cùng HttpSession | MockHttpSession |
| `authorization_request_not_found` | Pending request mất hoặc state mismatch | Repository/session |
| Sai state nhưng không nhận failure | Test tắt filters | MockMvc SecurityFilterChain |
| Replay success lần hai vẫn call token | Pending state chưa consume/custom repo lỗi | One-time removal |
| Replay success bị 401 nhưng tokenCalls=2 | Client đã gọi AS lần hai | Token counter |
| Happy-path OIDC test lỗi issuer | Test ID token issuer sai | ID token vs registration |
| Happy-path lỗi nonce | Token không echo authorization nonce | Extract nonce từ redirect |
| Happy-path lỗi signature | JWKS không khớp private key | RSA JWK/test signer |
| Happy-path lỗi audience | ID token aud sai client ID | ClientRegistration |
| UserInfo gọi unexpected | Scope/config yêu cầu UserInfo | Fake UserInfo endpoint |
| Test hoạt động riêng lẻ nhưng fail khi chạy suite | Shared fake OP/session/state | Test isolation |
| Hai tabs làm state A fail | Repository chỉ giữ một pending request | Concurrency policy |
| Callback sau session rotation fail | Session ID/storage binding không đồng bộ | Session strategy |
| Authorized client vẫn tồn tại sau failure | Token cũ thuộc flow trước hoặc wrong store | Principal/registration/store |
| Test kiểm tra service nhưng token ở session | Sai repository fixture | Actual storage wiring |
| `oidcLogin()` luôn cho pass | Helper bypass login flow | Dùng callback integration |
| AS production bị gọi trong test | Issuer discovery/token URI trỏ thật | Fake ClientRegistration |
| Consent text làm XSS | Reflect untrusted error_description | Sanitize UI/log |
| Proxy biến đổi callback URL | Forwarded headers/baseUrl | Browser/E2E và ingress policy |

## 31. Những hiểu nhầm cần tránh

**“Nếu người dùng từ chối consent thì API trả 403.”**

Không nhất thiết. Đây là OAuth authorization response error ở callback; API có thể chưa nhận request nào.

**“Consent denied luôn có nghĩa user chủ động bấm Deny.”**

Không. AS policy cũng có thể tạo `access_denied`.

**“Có code thì có thể đổi token dù state sai.”**

Không. Phải correlate callback với pending Authorization Request trước.

**“Sai state thì repository mặc định chắc chắn xóa request cũ.”**

Không được giả định; cần hiểu version/implementation và cleanup policy.

**“Callback trùng lặp chỉ cần trả HTTP 401 là đủ.”**

Chưa đủ. Cần kiểm tra token endpoint không bị gọi lần hai và không tạo authorized client mới.

**“Authorization code single-use tại AS nên client không cần consume state.”**

Không. Hai lớp bảo vệ độc lập.

**“`oidcLogin()` dùng để kiểm thử callback OIDC.”**

Không. Helper này giả lập principal sau login.

**“Fake OP phát access token là đủ cho OIDC Login.”**

Không. OIDC scope `openid` yêu cầu ID token hợp lệ theo profile.

**“Callback path có registration ID nên không cần issuer verification.”**

Không. Cần state correlation và OIDC validation.

**“Hai tabs cùng session phải luôn thành công trên repository mặc định.”**

Không nhất thiết; phải hiểu khả năng lưu nhiều pending requests của implementation.

**“Failure handler nên log toàn bộ query để debug.”**

Không. Query có authorization code và state nhạy cảm.

**“MockMvc có thể xác minh SameSite như browser thật.”**

Không đầy đủ. Cookie/browser behavior cần E2E test.

## 32. Tình huống thực hành

### A. Người dùng từ chối consent

Browser bắt đầu flow S1 và OP trả `access_denied`.

**Test:** cùng session, state đúng, xác minh login failure và không token endpoint call.

### B. Callback bị sửa state

Browser có pending S1, callback gửi S2.

**Test:** reject trước token exchange; không tạo Authentication.

### C. Callback thiếu state

Redirect từ OP trở về chỉ có `code=C1`.

**Test:** reject, không fallback vào pending request mới nhất.

### D. Callback qua session khác

Start ở session A, callback tại session B.

**Test:** reject; không tìm state ở session A để authenticate B.

### E. Người dùng reload callback đã thành công

First callback C1/S1 tạo OIDC principal. Reload cùng URL.

**Test:** second callback failure; token endpoint chỉ được gọi một lần; không tạo authorized client mới.

### F. AS token endpoint nhận cùng code hai lần

Fake AS trả token lần đầu, `invalid_grant` lần sau.

**Test:** code single-use; client replay không được thành công.

### G. Callback bị duplicate khi user đã đăng nhập trước

Alice đã có session, thử login Partner rồi denial hoặc replay.

**Test:** kiểm tra policy về việc giữ/clear Alice session, không chuyển sang principal sai.

### H. Multi-tab login

Tab A và B có states riêng nhưng cùng session.

**Test:** theo chính sách repository; không bỏ state validation để “sửa” race.

### I. Tenant bị thay đổi trong callback

Start tenant Acme, browser sửa query `tenant=Globex`.

**Test:** không lấy tenant từ callback; membership/context đúng pending state.

### J. Fake ID token nonce sai

State đúng, token endpoint trả signed ID token với nonce khác.

**Test:** OIDC validation từ chối, không tạo login thành công.

## 33. Câu hỏi tự kiểm tra

**1. `access_denied` ở callback là lỗi của API Resource Server phải không?**

Không. Nó là error response từ OAuth Authorization Server khi authorization không được cấp.

**2. Nếu consent bị từ chối, client có authorization code thành công để đổi token không?**

Không.

**3. Vì sao test phải dùng state thật được tạo từ authorization redirect?**

Để kiểm tra Spring Security correlation với pending Authorization Request thật, không chỉ một chuỗi hardcode.

**4. Vì sao giữ MockHttpSession giữa start và callback?**

Authorization Request thường được lưu theo browser/session.

**5. Khi state sai, cần assert gì ngoài HTTP status?**

Không token endpoint call, không Authentication hoặc authorized client mới.

**6. State sai có luôn xóa pending request đúng S1 không?**

Không mặc định; tùy repository/cleanup policy.

**7. Nếu callback đến từ session khác với state đúng thì có được login không?**

Không nên, vì không có pending request được session đó khởi tạo.

**8. Callback trùng lặp sau success phải làm gì?**

Không reprocess transaction hoặc đổi authorization code thêm lần nữa.

**9. Vì sao dùng fake AS token counter?**

Để chứng minh duplicate callback không gửi code tới token endpoint lần hai.

**10. AS cần kiểm tra gì với authorization code?**

Code phải gắn client/redirect và single-use theo OAuth policy.

**11. OIDC happy path mock cần gì ngoài access token?**

ID token hợp lệ, JWKS public key, issuer/audience/time và nonce khớp khi áp dụng.

**12. `oidcLogin()` có test state/nonce/PKCE callback thật không?**

Không.

**13. Consent denial luôn trả HTTP 401 ở Portal phải không?**

Không. Status do failure handler quyết định; có thể redirect 302.

**14. UserInfo có nhất thiết bị gọi trong mọi OIDC login không?**

Không. Tùy scope/provider/config.

**15. Fake OP có nên dùng client secret production không?**

Không.

**16. Khi two-tab login lỗi state, có nên bỏ state validation không?**

Không. Xem repository/concurrent pending request policy.

**17. Replay callback có thể làm mất session login cũ không?**

Có thể tùy failure handler; cần test chính sách giữ/clear session khi đã authenticated.

**18. Có nên log raw authorization code/state để debug không?**

Không. Log metadata/correlation ID an toàn thay vì credentials.

**19. Vì sao cần kiểm tra authorized client store sau failure?**

Để chắc không có token mới hoặc principal sai được lưu từ callback lỗi.

**20. MockMvc có test đầy đủ cookie SameSite của browser thực không?**

Không. Cần browser/E2E tests khi policy phụ thuộc hành vi cookie/redirect.

## Ghi nhớ

- **Consent refusal (`error=access_denied`), state mismatch và callback replay là ba failure paths khác nhau** của OAuth2/OIDC Login, cần kiểm thử riêng.
- **Bắt đầu authorization flow bằng Spring Security và đọc state thật từ redirect**, giữ đúng MockHttpSession để callback test phản ánh correlation thực.
- **Consent bị từ chối không được trao authorization code, không gọi token endpoint và không tạo login mới**; HTTP status/redirect tùy failure handler.
- **State sai, thiếu hoặc đến từ session khác phải bị từ chối trước token exchange**. Không fallback vào pending request khác.
- **Callback trùng lặp không được xử lý thành công lần hai**; kiểm tra thêm token endpoint call count và authorized client persistence.
- **State correlation phía client và authorization-code single-use phía AS là hai lớp độc lập**. Không bỏ state chỉ vì AS chống reuse code.
- **`oidcLogin()` chỉ giả lập principal sau login**, không kiểm thử callback, consent error, state, PKCE/nonce hoặc ID token validation thật.
- **Happy-path OIDC integration cần fake AS phát ID token ký bằng test key, JWKS và nonce đúng**; access token JSON đơn lẻ không đủ.
- **Failure handler, session cleanup, multi-tab, tenant binding và account switching có policy riêng**; không để callback lỗi thay Authentication hoặc tenant ngoài ý muốn.
- **Không dùng OP production hay token thật trong test**, không log raw code/state/secret và chỉ đưa thông tin lỗi đã sanitize cho browser.
