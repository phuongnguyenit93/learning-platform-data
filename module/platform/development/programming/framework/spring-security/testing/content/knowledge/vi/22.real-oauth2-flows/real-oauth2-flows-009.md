# Không thay cấu hình production chỉ để thuận tiện cho test

Một bài kiểm thử OAuth2 rất dễ “xanh” nếu ứng dụng chỉ cần vượt qua lớp bảo mật đã được nới lỏng: mở tất cả endpoint bằng `permitAll()`, bỏ kiểm tra `state`, tắt CSRF, thay `SecurityFilterChain` bằng một bean giả, hoặc cho controller nhận thẳng principal do test tự tạo. Tuy nhiên, kết quả ấy không chứng minh **ứng dụng đang chạy thật** có thể hoàn tất đăng nhập và bảo vệ tài nguyên.

Trong chương **Luồng OAuth2 thực** của module **SPRING_SECURITY_TESTING**, mục tiêu là kiểm chứng xác thực, phân quyền và HTTP protection bằng `spring-security-test` trên Servlet và Reactive. Bài này tập trung vào nguyên tắc **giữ nguyên chính sách bảo mật production, thay thế phụ thuộc bên ngoài ở phạm vi test**. Chúng ta sẽ dùng `MockMvc` chạy `SecurityFilterChain` thật, giả lập Authorization Server ở localhost, và hiểu rõ khi nào `oauth2Login()`/`oidcLogin()` chỉ là phép thử nhanh.

## 1. Vì sao không nên sửa production để có test dễ chạy?

Giả sử ứng dụng production có các yêu cầu sau:

- `GET /private` chỉ dành cho người dùng đã xác thực.
- Bắt đầu OAuth2 Authorization Code qua `GET /oauth2/authorization/corporate`.
- Nhận authorization response tại `/login/oauth2/code/corporate`.
- Trao đổi authorization code với token endpoint; lấy thông tin người dùng theo cấu hình provider.
- Duy trì `state` để gắn callback với yêu cầu ủy quyền đã bắt đầu, đồng thời áp dụng các cơ chế như PKCE, nonce (khi dùng OIDC), kiểm tra token và session theo cấu hình.

Nếu vì khó thiết lập Authorization Server trong test mà ta sửa:

```java
// CÁCH KHÔNG NÊN LÀM: sửa cấu hình chính để mọi bài test đều qua.
.authorizeHttpRequests(auth -> auth
    .anyRequest().permitAll())
```

thì một test `GET /private -> 200` sẽ không còn đo được yêu cầu đăng nhập. Tương tự, tắt bộ lọc security trong MockMvc hoặc vô hiệu hóa cơ chế kiểm tra callback khiến bài test bỏ qua chính hành vi cần kiểm chứng.

| Hành động “cho tiện test” | Vấn đề phát sinh | Cách thay thế |
| --- | --- | --- |
| Đổi `/private` từ `authenticated()` sang `permitAll()` | Không còn kiểm tra protection của endpoint | Giữ nguyên filter chain; cung cấp request đã đăng nhập qua helper hoặc flow thật |
| Thêm điều kiện `if (testProfile) return success` vào controller/login handler | Runtime production có nhánh vượt qua xác thực | Dùng `@TestConfiguration`, test properties và mock Authorization Server bên ngoài |
| Bỏ kiểm tra `state`/PKCE/nonce để callback dễ ghép | Không kiểm tra được ràng buộc chống tráo response và các cơ chế quan trọng | Lấy `state` từ redirect thật; để bộ lọc kiểm tra callback |
| Tắt toàn bộ CSRF cho các request chỉ vì test POST bị 403 | Che mất lỗi CSRF của các chức năng cần bảo vệ | Dùng `.with(csrf())` cho POST form cần CSRF; kiểm thử token CSRF riêng |
| Hardcode URL hoặc client secret của mock server vào `application.yml` production | Thử nghiệm bị rò sang cấu hình vận hành | Override URL/credentials qua `@DynamicPropertySource` hoặc `application-test.yml` |
| Mock `SecurityFilterChain` hoặc bỏ `springSecurity()` trong MVC test | Filter, redirect, exception handling không chạy đúng | Tích hợp `MockMvc` với Spring Security, chẳng hạn `@AutoConfigureMockMvc` |
| Dùng `oauth2Login()` cho mọi kiểm thử rồi gọi đó là “full flow” | Helper đã tạo sẵn Authentication; không kiểm tra trao đổi authorization code | Có thêm bài test bắt đầu redirect, callback, token và user info thật qua local mock server |

Điều được phép **thay trong test** là môi trường và phụ thuộc bên ngoài: host Authorization Server, client credentials thử nghiệm, HTTP mock server, clock/test data, mock adapter ở điểm tích hợp có chủ đích. Quy tắc cấp quyền, bộ lọc đăng nhập và hợp đồng endpoint của ứng dụng nên giống production.

## 2. Ba cấp độ kiểm thử phục vụ ba mục đích

Không phải mọi test đều cần khởi động Authorization Server; cần chọn đúng loại test theo điều muốn chứng minh.

| Mức độ | Công cụ | Xác minh được | Chưa chứng minh được |
| --- | --- | --- | --- |
| Controller/authorization | `MockMvc` + `oauth2Login()`, `oidcLogin()`, `@WithMockUser` | Route, role/authority, logic với principal đã xác thực | Redirect OAuth2, lưu `state`, token exchange, UserInfo, xác minh ID token |
| Tích hợp OAuth2 Servlet | `@SpringBootTest` + `@AutoConfigureMockMvc` + mock Authorization Server HTTP | Các bộ lọc thật, redirect, session, `state`, xử lý callback, gọi token/UserInfo endpoint | Đăng nhập trong trình duyệt và tính tương thích tuyệt đối với nhà cung cấp thực |
| End-to-end gần production | Browser + Authorization Server test/tenant dành riêng | Cookie/SameSite, reverse proxy, HTTPS, redirect URI, PKCE/OIDC và trải nghiệm người dùng toàn tuyến | Không tự bảo đảm được các cấu hình bên ngoài không thay đổi sau test |

Ví dụ một phép thử **hợp lệ** với danh tính giả lập:

```java
mvc.perform(get("/private").with(oauth2Login()))
    .andExpect(status().isOk());
```

Phép thử trên đưa `OAuth2AuthenticationToken` và `OAuth2User` giả lập vào request. Nó hữu ích để kiểm tra rằng người dùng đã đăng nhập được truy cập `/private`. Nó **không gửi request tới Authorization Server** và không chứng minh endpoint `/login/oauth2/code/{registrationId}` hoạt động.

Bài thực hành bên dưới chọn mức thứ hai: giữ nguyên production `SecurityFilterChain`, giả lập **chỉ HTTP của Identity Provider**, và để Spring Security xử lý OAuth2 Authorization Code qua đường đi thực.

## 3. Cấu hình production minh họa: giữ nguyên trong quá trình test

Giả sử ứng dụng Spring Boot Servlet đã có `@SpringBootApplication`. Các dependency cần thiết:

```gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
}
```

Ví dụ `application.yml` cho OAuth2 Login bằng Authorization Code:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate
            client-id: ${OAUTH_CLIENT_ID}
            client-secret: ${OAUTH_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: profile
        provider:
          corporate:
            authorization-uri: https://login.example.test/oauth2/authorize
            token-uri: https://login.example.test/oauth2/token
            user-info-uri: https://login.example.test/oauth2/userinfo
            user-name-attribute: sub
```

Các URL thuộc `.example.test` chỉ mang tính minh họa; trong production cần cấu hình theo provider thực và lưu secret qua môi trường hay secret manager. Ví dụ dùng OAuth2 UserInfo thông thường để tập trung vào Authorization Code. Với **OIDC**, cần thêm `openid`, ID token, `nonce` và kiểm tra issuer/chữ ký/audience theo provider; không thể thay ID token bằng một JSON UserInfo đơn giản.

Cấu hình bảo mật của ứng dụng:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers("/private").authenticated()
                .anyRequest().denyAll())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
```

Controller cần bảo vệ:

```java
import java.security.Principal;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class PrivateController {

    @GetMapping("/private")
    String privatePage(Principal principal) {
        return principal.getName();
    }

    @GetMapping("/health")
    String health() {
        return "ok";
    }
}
```

Ở đây:

- `/health` có thể truy cập ẩn danh.
- `/private` chỉ được thực thi khi Spring Security đã tạo Authentication hợp lệ.
- `/oauth2/authorization/corporate` và callback `/login/oauth2/code/corporate` được xử lý bởi **các bộ lọc OAuth2 của Spring Security** trước khi request đến controller.
- `state` và cách lưu `OAuth2AuthorizationRequest` trong phiên thuộc cơ chế OAuth2 Login; không thêm mã “bỏ qua state nếu test” vào ứng dụng.

Khi `oauth2Login()` được bật, Spring Security mặc định dùng `OAuth2AuthorizationRequestRedirectFilter` cho yêu cầu bắt đầu ủy quyền và `OAuth2LoginAuthenticationFilter` cho callback. Nếu ứng dụng đã thay endpoint mặc định, bài test phải bám endpoint thật thay vì sửa production cho khớp ví dụ.

## 4. Chỉ override các đầu nối Authorization Server trong test

Một bài test đáng tin phải giữ cùng `SecurityFilterChain`, controller, redirect handling và chính sách session; chỉ đưa Authorization Server sang máy chủ cục bộ.

Dưới đây là cấu trúc test điển hình:

```text
src/main/
  java/.../WebSecurityConfig.java       # Giữ nguyên
  java/.../PrivateController.java       # Giữ nguyên
  resources/application.yml             # Cấu hình production

src/test/
  java/.../OAuth2AuthorizationCodeFlowTests.java
       @SpringBootTest
       @AutoConfigureMockMvc
       @DynamicPropertySource          # Override host và credentials riêng cho test
       MockWebServer                    # Phản hồi token + UserInfo
```

Trong test, `MockWebServer` lắng nghe một cổng localhost ngẫu nhiên, ví dụ `http://127.0.0.1:49231`. `@DynamicPropertySource` cung cấp cổng đó cho các property:

```text
spring.security.oauth2.client.provider.corporate.authorization-uri
spring.security.oauth2.client.provider.corporate.token-uri
spring.security.oauth2.client.provider.corporate.user-info-uri
```

Ta cũng cung cấp client ID và client secret **thử nghiệm** tại source test; không đọc secret production, không sửa `application.yml` chính. Điều quan trọng là `registrationId` vẫn là `corporate`, `redirect-uri` vẫn là `{baseUrl}/login/oauth2/code/{registrationId}` và `authorization-grant-type` vẫn là `authorization_code`.

Đối với các provider cấu hình bằng `issuer-uri` hoặc OIDC discovery, việc thay property có thể dẫn đến metadata/JWKS fetch tự động. Khi đó cần cung cấp metadata và JWKS từ mock server hoặc dùng test tenant phù hợp; không loại bỏ xác minh ID token để khiến test chạy nhanh.

## 5. MockMvc chạy thật redirect, callback, token exchange và UserInfo

Bài test sử dụng `MockWebServer` để mô phỏng **hai request HTTP outbound**: đổi authorization code lấy access token và đọc UserInfo. `MockMvc` chạy filter chain và MVC thật trong ứng dụng; không có trình duyệt nên test đóng vai trò trình duyệt, nhận redirect và gọi callback với đúng session/`state`.

Ví dụ Java 17+, Spring Boot 3.x, Spring Security 6.x:

```java
import java.io.IOException;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.web.util.UriComponentsBuilder;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "spring.security.oauth2.client.registration.corporate.client-id=test-client",
    "spring.security.oauth2.client.registration.corporate.client-secret=test-secret"
})
@AutoConfigureMockMvc
class OAuth2AuthorizationCodeFlowTests {

    // Một máy chủ dùng trong cả lớp; các ca ở đây chạy tuần tự.
    private static final MockWebServer idp = startMockIdp();

    @Autowired
    MockMvc mvc;

    private static MockWebServer startMockIdp() {
        try {
            MockWebServer server = new MockWebServer();
            server.start();
            return server;
        } catch (IOException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    @DynamicPropertySource
    static void localAuthorizationServer(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.security.oauth2.client.provider.corporate.authorization-uri",
            () -> idp.url("/authorize").toString());
        registry.add(
            "spring.security.oauth2.client.provider.corporate.token-uri",
            () -> idp.url("/token").toString());
        registry.add(
            "spring.security.oauth2.client.provider.corporate.user-info-uri",
            () -> idp.url("/userinfo").toString());
    }

    @AfterAll
    static void closeMockIdp() throws IOException {
        idp.shutdown();
    }

    @Test
    void authorizationCodeFlowCreatesAnAuthenticatedSession()
            throws Exception {

        // 1. Chưa đăng nhập: endpoint được bảo vệ.
        mvc.perform(get("/private"))
            .andExpect(status().is3xxRedirection());

        // 2. Bắt đầu flow: ứng dụng tạo authorization request và state.
        MvcResult start = mvc.perform(
                get("/oauth2/authorization/corporate"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        String location = start.getResponse().getRedirectedUrl();
        assertThat(location).startsWith(
            idp.url("/authorize").toString());

        String state = UriComponentsBuilder
            .fromUriString(location)
            .build()
            .getQueryParams()
            .getFirst("state");

        assertThat(state).isNotBlank();

        MockHttpSession session =
            (MockHttpSession) start.getRequest().getSession(false);
        assertThat(session).isNotNull();

        // 3. Authorization Server cục bộ trả token cho code thử nghiệm.
        idp.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "application/json")
            .setBody("""
                {
                  "access_token": "local-access-token",
                  "token_type": "Bearer",
                  "expires_in": 600,
                  "scope": "profile"
                }
                """));

        // 4. Spring OAuth2 Client gọi UserInfo bằng access token vừa nhận.
        idp.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "application/json")
            .setBody("""
                {
                  "sub": "alice",
                  "name": "Alice Example"
                }
                """));

        // 5. Giả lập trình duyệt được redirect về callback đã đăng ký.
        MvcResult callback = mvc.perform(
                get("/login/oauth2/code/corporate")
                    .session(session)
                    .param("code", "sample-authorization-code")
                    .param("state", state))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        // Lấy lại session sau login: session ID có thể đã thay đổi
        // theo chiến lược chống session fixation của Spring Security.
        MockHttpSession authenticatedSession =
            (MockHttpSession) callback.getRequest().getSession(false);
        assertThat(authenticatedSession).isNotNull();

        // 6. Yêu cầu tiếp theo được xử lý với principal từ UserInfo.
        mvc.perform(get("/private").session(authenticatedSession))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));

        // 7. Xác nhận ứng dụng thật đã gọi token endpoint.
        RecordedRequest tokenRequest =
            idp.takeRequest(1, TimeUnit.SECONDS);
        assertThat(tokenRequest).isNotNull();
        assertThat(tokenRequest.getMethod()).isEqualTo("POST");
        assertThat(tokenRequest.getPath()).isEqualTo("/token");
        assertThat(tokenRequest.getBody().readUtf8())
            .contains("grant_type=authorization_code")
            .contains("code=sample-authorization-code");

        // 8. UserInfo request phải mang đúng Bearer token thử nghiệm.
        RecordedRequest userInfoRequest =
            idp.takeRequest(1, TimeUnit.SECONDS);
        assertThat(userInfoRequest).isNotNull();
        assertThat(userInfoRequest.getPath()).isEqualTo("/userinfo");
        assertThat(userInfoRequest.getHeader("Authorization"))
            .isEqualTo("Bearer local-access-token");
    }

    @Test
    void callbackWithWrongStateIsRejected() throws Exception {
        MvcResult start = mvc.perform(
                get("/oauth2/authorization/corporate"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        String location = start.getResponse().getRedirectedUrl();
        String originalState = UriComponentsBuilder
            .fromUriString(location)
            .build()
            .getQueryParams()
            .getFirst("state");

        assertThat(originalState).isNotBlank();
        MockHttpSession session =
            (MockHttpSession) start.getRequest().getSession(false);

        mvc.perform(get("/login/oauth2/code/corporate")
                .session(session)
                .param("code", "sample-authorization-code")
                .param("state", originalState + "-altered"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));
    }
}
```

**Lưu ý khi áp dụng nguyên ví dụ:** các test dùng một mock server có hàng đợi phản hồi; cần chạy tuần tự. Nếu test runner chạy song song, hãy thiết kế server/response dispatcher cô lập cho từng test, hoặc chặn chạy song song ở lớp này để không tráo response. Mỗi HTTP request tới mock server phải tương ứng một response cụ thể.

### Những điểm quan sát quan trọng

| Chặng | Bằng chứng test thu được | Kết luận được phép rút ra |
| --- | --- | --- |
| `GET /private` ban đầu | Redirect tới login theo cấu hình | Endpoint được bảo vệ khi chưa xác thực |
| `GET /oauth2/authorization/corporate` | HTTP 302 tới `/authorize`, có `state` | Filter tạo authorization request |
| Callback mang lại cùng session và `state` | HTTP 302 sau xử lý callback | Bộ lọc nhận callback phù hợp với authorization request |
| Request `POST /token` từ server | Có `grant_type=authorization_code` và `code` | Ứng dụng thực hiện token exchange qua HTTP |
| Request `GET /userinfo` từ server | Mang `Authorization: Bearer local-access-token` | Ứng dụng dùng access token nhận được để lấy UserInfo |
| `GET /private` sau callback | HTTP 200 và principal `alice` | Phiên sau login có authentication được chấp nhận |
| Callback dùng `state` sai | Redirect `/login?error` | Callback giả mạo/mismatch không hoàn tất đăng nhập theo cấu hình này |

Test không cần thay bất cứ method nào của `WebSecurityConfig`. Nếu ai đó bỏ `oauth2Login()`, cho phép truy cập `/private` công khai hoặc thay controller trả principal cố định, các assertion phù hợp sẽ thất bại.

### Tại sao không cần truy cập HTTP GET /authorize thật?

Khi khởi tạo flow, Spring Security tạo URL redirect tới Authorization Server. Trong trình duyệt, người dùng sẽ đăng nhập/đồng ý ở trang `/authorize` và được redirect về callback. Trong `MockMvc`, test nhận Location, **tự mô phỏng bước trình duyệt quay lại** với một code thử nghiệm cùng `state` thật. Vì thế test đã chạy thực tế **khâu tạo authorization request và xử lý callback/token/UserInfo của ứng dụng**, nhưng chưa kiểm tra màn hình đăng nhập/consent hay quy tắc phát code của Authorization Server. Muốn kiểm tra phần đó, dùng browser E2E với Identity Provider test.

### Khi Authorization Server trả lỗi token exchange

Nếu Authorization Server từ chối code (chẳng hạn `invalid_grant`), không được tự coi đó là login thành công. Có thể thêm test:

```java
@Test
void invalidAuthorizationCodeDoesNotLogUserIn() throws Exception {
    MvcResult start = mvc.perform(
            get("/oauth2/authorization/corporate"))
        .andExpect(status().is3xxRedirection())
        .andReturn();

    String location = start.getResponse().getRedirectedUrl();
    String state = UriComponentsBuilder.fromUriString(location)
        .build().getQueryParams().getFirst("state");
    MockHttpSession session =
        (MockHttpSession) start.getRequest().getSession(false);

    idp.enqueue(new MockResponse()
        .setResponseCode(400)
        .addHeader("Content-Type", "application/json")
        .setBody("""
            {"error": "invalid_grant"}
            """));

    mvc.perform(get("/login/oauth2/code/corporate")
            .session(session)
            .param("code", "rejected-code")
            .param("state", state))
        .andExpect(status().is3xxRedirection())
        .andExpect(redirectedUrl("/login?error"));
}
```

Đặt test này trong **cùng lớp `OAuth2AuthorizationCodeFlowTests`** để dùng `mvc` và `idp` đã định nghĩa. Nó đo cách ứng dụng xử lý từ chối từ token endpoint, nhưng cũng không chứng minh Authorization Server thật có cùng chính sách mã code một lần, thời hạn code, redirect URI hay PKCE.

## 6. Những yếu tố bảo mật không được nới lỏng

### State, session và callback

`state` liên kết response với request OAuth2 đã khởi tạo; `OAuth2AuthorizationRequest` thường được lưu trong HttpSession ở cấu hình Servlet mặc định. Test phải lấy `state` từ **redirect thật** và dùng **cùng session** cho callback. Nếu test hardcode `state=abc` hoặc làm mới session giữa chừng, phép kiểm thử có thể thất bại vì chính cơ chế bảo vệ đang hoạt động đúng.

Không thêm tùy chọn bỏ qua kiểm tra `state` trong production để sửa lỗi test. Hãy sửa cách test thu thập và dùng `state`.

### PKCE

PKCE (Proof Key for Code Exchange) ràng buộc authorization code với `code_verifier` bí mật của client đã bắt đầu flow. Việc có dùng PKCE và cách truyền `code_challenge` phụ thuộc client registration và cấu hình provider. Nếu production bật PKCE, test cần giữ nguyên và có thể xác minh redirect chứa `code_challenge`/phương thức `S256`, còn token request có `code_verifier`. Không tháo PKCE chỉ vì mock Authorization Server chưa hiểu nó; cấu hình mock server để chấp nhận hoặc kiểm tra các tham số thích hợp.

### OIDC: nonce, ID token, issuer, audience và chữ ký

Ví dụ trên dùng OAuth2 Login với UserInfo; OIDC thêm `scope=openid` và ID token. Với OIDC, Spring Security cần xác minh ID token dựa trên khóa của provider và các claim như issuer/audience, thời gian, nonce theo cơ chế liên quan. Trong test OIDC thực, mock provider phải cấp ID token ký hợp lệ và JWKS phù hợp; hoặc dùng OIDC provider test. Dùng `oidcLogin()` giúp viết test authorization nhanh, nhưng nó **không phải phép chứng minh** rằng chữ ký ID token và nonce được xác minh trong luồng callback.

### CSRF không phải cùng một thứ với state

CSRF token trong Spring Security giúp bảo vệ các request có thể thay đổi trạng thái như POST form. `state` của OAuth2 giúp liên kết authorization response với authorization request. Hai cơ chế giải quyết những bài toán liên quan nhưng khác nhau. Nếu test POST cần CSRF, dùng:

```java
mvc.perform(post("/profile")
        .with(csrf())
        .param("displayName", "Alice"))
    .andExpect(status().is3xxRedirection());
```

Đây chỉ là ví dụ cú pháp, giả định ứng dụng có endpoint POST `/profile` với phản hồi redirect như thiết kế. Đừng thêm `.csrf(csrf -> csrf.disable())` vào `SecurityFilterChain` chính chỉ để test POST qua được. Callback OAuth2 thông thường trong ví dụ là GET và được bảo vệ bằng cơ chế state; không tự áp dụng quy tắc POST form cho mọi callback.

### Redirect URI và môi trường reverse proxy

Giá trị `redirect_uri` phải khớp cấu hình nhà cung cấp và địa chỉ public của ứng dụng. Trong MockMvc, `{baseUrl}` thường được tạo từ request test; trong môi trường có reverse proxy, HTTPS hoặc prefix, có thể cần cấu hình forwarded headers hợp lệ. Đừng sửa redirect URI production thành localhost để “thắng” bài test; cấp registration riêng cho test hoặc cấu hình địa chỉ test đúng với test Identity Provider.

## 7. Override cái gì, giữ nguyên cái gì?

| Thành phần | Cách làm trong test | Lý do |
| --- | --- | --- |
| `SecurityFilterChain` | Dùng chính bean ứng dụng | Kiểm tra được chính sách và filter chain đang triển khai |
| `authorizeHttpRequests`, method security | Giữ nguyên | Tránh kết quả 200 giả khi endpoint phải bị chặn |
| `oauth2Login()` và callback processing | Giữ nguyên | Kiểm tra flow thực và bảo vệ `state` |
| `ClientRegistration.registrationId` | Giữ như production khi có thể | Test đúng endpoint/registration |
| Authorization/token/UserInfo URL | Override sang localhost qua test properties | Cho phép gọi HTTP thật mà không phụ thuộc nhà cung cấp |
| Client ID, client secret | Dùng giá trị riêng cho test | Không dùng secret production |
| UserInfo/token response | Mock có kiểm soát | Cô lập ca thành công và lỗi |
| `OAuth2AuthorizationRequestRepository` | Giữ implementation production trong integration test | Bảo toàn chính sách lưu và kiểm tra `state` |
| Clock và dữ liệu thời hạn | Cô lập khi cần | Test expiration/clock skew ổn định |
| Browser, cookie, SameSite, proxy | Kiểm bằng E2E riêng | MockMvc không mô phỏng đầy đủ mạng/trình duyệt |

Nếu test đòi thay `SecurityFilterChain`, hãy tự hỏi đang cần **unit test một controller** hay **integration test OAuth2 Login**. Với unit test controller, mock Authentication là hợp lý; chỉ cần đặt tên và kết luận đúng phạm vi. Với integration test đăng nhập, việc thay chính logic security cần được xem xét lại.

## 8. Các lỗi phổ biến và cách điều tra

| Biểu hiện | Khả năng cần kiểm tra trước | Hướng xử lý |
| --- | --- | --- |
| `GET /private` trả 200 ngay cả khi chưa login | Endpoint đang `permitAll()` hoặc test đã gắn principal | Dùng request ẩn danh qua filter chain thật, assert bị chặn |
| `/oauth2/authorization/corporate` không trả 302 | Registration ID sai, thiếu `oauth2Login()`, không có filter | Kiểm tra registration `corporate`, đường dẫn, SecurityFilterChain |
| Callback trả `/login?error` dù token response 200 | Sai `state`/session, token/UserInfo JSON sai, không khớp provider | Xác minh Location, cùng session, log test có lọc thông tin nhạy cảm và request mock server |
| Không thấy request tới token endpoint | Callback bị chặn trước token exchange, `state` sai | Kiểm tra `state`, callback path, session |
| Token endpoint đã gọi nhưng UserInfo chưa gọi | Grant/scopes/provider/user-info configuration khác kỳ vọng | Kiểm tra `user-info-uri`, `user-name-attribute`, loại OAuth2/OIDC |
| `@WithMockUser` thành công nhưng flow thật lỗi | Helper bỏ qua redirect/token exchange | Thêm integration test qua token/UserInfo HTTP |
| Test pass khi tắt CSRF toàn cục | Test đang đo cấu hình đã bị nới lỏng | Phục hồi CSRF, bổ sung token CSRF cho request POST phù hợp |
| Test riêng lẻ pass, chạy cả suite fail | MockWebServer có response queue bị trộn hoặc shared session | Cô lập fixture, reset dữ liệu hợp lệ, không chạy song song khi dùng queue chung |
| URL redirect trên production sai scheme HTTPS | Forwarded header/proxy chưa khớp | Test thêm cấu hình proxy/HTTPS gần thực tế, không hardcode workaround production |
| Mỗi lần test đều gọi ra Identity Provider thật | Chưa override URI/metadata trong test | Sử dụng mock server cục bộ hoặc IdP test riêng, không phụ thuộc mạng ngoài cho integration test thông thường |

Không log access token, authorization code, client secret hoặc ID token trong quá trình debug. Khi cần quan sát, kiểm tra **sự hiện diện và cấu trúc** các tham số ở request đã bắt bằng mock server và che giá trị nhạy cảm khỏi báo cáo chạy test.

## 9. Mở rộng sang JWT, Resource Server và Reactive

### Resource Server nhận bearer JWT

Nếu ứng dụng vừa là OAuth2 Client để đăng nhập, vừa là Resource Server nhận Bearer JWT, hai đường đi cần được kiểm thử riêng. `jwt()` trong `spring-security-test` gắn một authentication giả lập, hữu ích cho quy tắc scope/role; nó không chứng minh `JwtDecoder` xác minh chữ ký, issuer hoặc audience. Để kiểm chứng bearer token thật, gửi `Authorization: Bearer <signed-token>` qua MockMvc và sử dụng decoder/validator phù hợp trong test.

### Opaque token

Tương tự, `opaqueToken()` mô phỏng principal đã qua introspection; nó không tạo request thật tới introspection endpoint. Kiểm thử `active=false` phải đi qua `OpaqueTokenIntrospector` và phản hồi HTTP từ mock Authorization Server.

### Spring WebFlux

Ở Reactive, `WebTestClient` kết hợp với `SecurityWebFilterChain` và các repository/manager reactive. `mockOAuth2Login()` hoặc `mockOidcLogin()` phù hợp với test đã có principal, nhưng không tự chạy Authorization Code thực. Một integration test WebFlux phải giữ `SecurityWebFilterChain`, cấu hình `ReactiveClientRegistrationRepository`, session/cookie và mô phỏng Authorization Server tương ứng.

Ví dụ test phân quyền nhanh:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOAuth2Login;

// WebTestClient đã được cấu hình với Spring Security:
webTestClient
    .mutateWith(mockOAuth2Login())
    .get()
    .uri("/private")
    .exchange()
    .expectStatus().isOk();
```

Khi cần đo full flow Reactive, phải kiểm tra riêng redirect/callback, `WebSession` và HTTP token/JWKS/UserInfo. Cần sử dụng đúng stack; không sử dụng `MockMvc` Servlet với `SecurityWebFilterChain` Reactive.

## 10. Bài tập thực hành

1. Chạy test thành công ở mục 5 rồi bỏ `.session(session)` khi gọi callback. Quan sát lỗi và giải thích vai trò của `OAuth2AuthorizationRequestRepository`.
2. Giữ session nhưng thay một ký tự trong `state`. Kiểm chứng callback không đăng nhập được; xác định bằng chứng HTTP phù hợp.
3. Thay phản hồi token endpoint từ 200 thành `400 {"error":"invalid_grant"}`. Kiểm tra ứng dụng không tạo phiên đã đăng nhập và không gọi UserInfo.
4. Thêm một test helper `oauth2Login()` cho `GET /private`, nêu chính xác điều mà test này xác minh và điều nó bỏ qua.
5. Đặt request đã được xác thực nhưng thiếu authority cho một endpoint mới yêu cầu `hasAuthority("ROLE_ADMIN")`. Kiểm chứng 403 mà không sửa rule production.
6. Nếu cấu hình production có PKCE, khẳng định redirect có `code_challenge` và token exchange gửi `code_verifier`. Không tắt PKCE trong test.
7. Chuyển ví dụ sang OIDC test provider: trả ID token ký bằng khóa thử nghiệm, cung cấp JWKS và kiểm chứng issuer/nonce. So sánh với `oidcLogin()` giả lập.
8. Bổ sung test browser E2E trên test Identity Provider với cookie `SameSite`, HTTPS và redirect URI. Liệt kê các hành vi MockMvc đã kiểm và các hành vi chỉ E2E mới quan sát được.

## 11. Ghi nhớ

- **Giữ nguyên cấu hình security production trong integration test.** Chỉ thay thế phụ thuộc bên ngoài và dữ liệu cấu hình ở phạm vi test khi cần.
- **Mock principal có giá trị nhưng phải gọi đúng tên mục đích.** `oauth2Login()`, `oidcLogin()`, `@WithMockUser` phục vụ kiểm thử request đã xác thực; không chứng minh token exchange hay callback thật.
- **Muốn kiểm thử Authorization Code, phải đi qua redirect và callback thực.** Lấy `state` từ redirect, dùng cùng session, để Spring Security gọi token/UserInfo endpoint và kiểm chứng kết quả.
- **Không bỏ cơ chế bảo vệ để làm test xanh.** State, PKCE, OIDC nonce, xác minh token, CSRF phù hợp và authorization rule là hành vi cần kiểm tra.
- **Hiểu giới hạn của mock HTTP server.** Nó xác minh tích hợp với HTTP và bộ lọc trong ứng dụng; để đo browser và provider thật phải có test E2E phù hợp.
- **Bằng chứng đáng tin đến từ điều kiện đối chứng.** Kiểm tra cả người chưa đăng nhập bị chặn, flow đúng được chấp nhận và callback sai `state` bị từ chối.

Đối với **SPRING_SECURITY_TESTING**, bài test có ý nghĩa khi nó trả lời được câu hỏi: **“Cấu hình đang bảo vệ người dùng trong production có thực sự được thực thi trong test này không?”** Giữ nguyên chính sách và kiểm soát môi trường thử nghiệm là cách tạo ra câu trả lời đáng tin cậy.

