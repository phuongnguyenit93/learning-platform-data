# Bộ xử lý đăng xuất và dữ liệu cần dọn

## 1. Đăng xuất không chỉ là chuyển về trang login

Khi người dùng bấm nút đăng xuất, ứng dụng cần kết thúc trạng thái xác thực hiện tại và dọn các dữ liệu liên quan đến phiên. Tùy kiến trúc, các dữ liệu cần xử lý có thể gồm HTTP session, `SecurityContext`, CSRF token, cookie remember-me, cookie phiên và token/phiên do ứng dụng tự quản lý. Sau khi dọn xong, ứng dụng mới trả phản hồi thành công như redirect hoặc HTTP 204.

Trong Spring Security Servlet, `LogoutFilter` điều phối quy trình này. Nó gọi một hoặc nhiều `LogoutHandler` để dọn trạng thái, sau đó gọi `LogoutSuccessHandler` để tạo response. Hai nhóm thành phần có trách nhiệm khác nhau: handler đăng xuất thực hiện cleanup; success handler định dạng kết quả gửi cho client.

Bài học thuộc chương **Kiểm thử thành phần** của mô-đun **SPRING_SECURITY_TESTING**. Mô-đun hướng tới kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế bằng `spring-security-test` trên ứng dụng Servlet và Reactive, sử dụng `MockMvc`, `WebTestClient`, `@WithMockUser`, `SecurityContext` và JWT/OAuth2/OIDC giả lập. Bài này tập trung vào quy trình logout và cách xác minh trạng thái cũ không còn được sử dụng sau khi đăng xuất.

Sau bài học, bạn có thể:

- Phân biệt `LogoutHandler` với `LogoutSuccessHandler`.
- Giải thích các bước mặc định của logout trong Servlet và vai trò của `LogoutFilter`.
- Kiểm thử việc vô hiệu hóa session, xóa `SecurityContext`, CSRF token và cookie.
- Dùng `MockMvc` để kiểm tra POST `/logout`, CSRF và response sau logout.
- Nhận diện giới hạn của logout trong ứng dụng stateless dùng JWT.
- Kiểm thử logout Reactive bằng `ServerLogoutHandler`, `ServerLogoutSuccessHandler` và `WebTestClient`.

## 2. Luồng logout trong Spring Security Servlet

Trong Servlet, `LogoutFilter` kiểm tra request có khớp logout request matcher hay không. Khi khớp, filter lấy `Authentication` hiện tại, gọi các logout handler theo thứ tự đã cấu hình, rồi gọi success handler.

~~~mermaid
flowchart TD
    A["POST /logout"] --> B["LogoutFilter kiểm tra request matcher"]
    B --> C{"Có phải logout request?"}
    C -- "Không" --> D["Tiếp tục filter chain"]
    C -- "Có" --> E["Lấy Authentication hiện tại"]
    E --> F["Gọi các LogoutHandler"]
    F --> G["Vô hiệu hóa session / xóa SecurityContext"]
    G --> H["Xóa remember-me / CSRF / cookie theo cấu hình"]
    H --> I["LogoutSuccessHandler"]
    I --> J["Redirect hoặc response 204 / JSON"]
~~~

Với cấu hình CSRF mặc định đang bật, logout thường được thực hiện bằng POST để tránh một trang web bên ngoài có thể ép trình duyệt đăng xuất người dùng chỉ bằng cách tải một URL. Request POST phải có CSRF token hợp lệ. URL mặc định thường là `/logout`; ứng dụng có thể đổi URL và matcher.

Các interface chính:

~~~java
public interface LogoutHandler {
    void logout(
            HttpServletRequest request,
            HttpServletResponse response,
            Authentication authentication);
}

public interface LogoutSuccessHandler {
    void onLogoutSuccess(
            HttpServletRequest request,
            HttpServletResponse response,
            Authentication authentication)
            throws IOException, ServletException;
}
~~~

`LogoutHandler` thường không ném checked exception và nên thực hiện cleanup an toàn, có thể gọi lặp lại. `LogoutSuccessHandler` chạy sau các handler; nó chịu trách nhiệm response cuối cùng như redirect đến `/login?logout`, trả 204 hoặc JSON. Nếu cleanup thất bại do lỗi hệ thống, cần có chính sách ghi nhận và xử lý phù hợp; không nên báo logout thành công trong khi trạng thái nhạy cảm vẫn còn hiệu lực.

## 3. Những dữ liệu thường cần dọn

| Thành phần | Dữ liệu cần xử lý | Cách kiểm thử |
| --- | --- | --- |
| `SecurityContextLogoutHandler` | Xóa `Authentication` khỏi context, xóa context hiện tại và mặc định vô hiệu hóa HTTP session | Xác minh session bị invalid và context không còn principal trong luồng logout |
| `CsrfLogoutHandler` | Xóa CSRF token khỏi repository/context theo cấu hình | Gửi logout có token hợp lệ rồi kiểm tra token cũ không còn được chấp nhận |
| Remember-me services | Xóa cookie remember-me và trạng thái token phía server nếu triển khai hỗ trợ | Kiểm tra cookie hết hạn và token cũ không đăng nhập lại được |
| `CookieClearingLogoutHandler` | Hết hạn cookie được chỉ định | Kiểm tra `Set-Cookie` có `Max-Age=0` hoặc `Expires` trong quá khứ |
| Session ứng dụng | Dữ liệu gắn với phiên như giỏ hàng tạm, trạng thái wizard hoặc dữ liệu nhạy cảm | Xác minh dữ liệu phiên không còn truy cập được sau logout |
| Token tùy chỉnh/refresh token | Thu hồi hoặc đánh dấu không còn hiệu lực ở nơi quản lý token | Thử sử dụng token cũ sau logout và xác minh bị từ chối |

Không phải mọi ứng dụng đều cần mọi handler. Ví dụ, API stateless không dùng HTTP session có thể không cần vô hiệu hóa session; ứng dụng không bật remember-me không có cookie remember-me để xóa. Hãy kiểm thử những cơ chế thực sự được cấu hình.

### SecurityContextLogoutHandler

Đây là handler mặc định quan trọng cho logout Servlet. Nó có thể:

- Vô hiệu hóa HTTP session nếu được cấu hình (mặc định thường bật).
- Xóa `Authentication` khỏi `SecurityContext`.
- Xóa `SecurityContextHolder` để thread hiện tại không giữ principal cũ.
- Lưu context rỗng vào repository theo cơ chế được cấu hình.

Việc xóa context giúp request tiếp theo không dùng lại danh tính của request vừa đăng xuất. Session invalidation ngăn session ID cũ tiếp tục đại diện cho phiên đăng nhập.

### CookieClearingLogoutHandler

Cookie phía trình duyệt là dữ liệu client giữ lại. `CookieClearingLogoutHandler` có thể yêu cầu browser hết hạn các cookie được chỉ định. Để xóa cookie thành công, thuộc tính path/domain cần tương thích với cookie đã tạo; nếu cookie ban đầu có path hoặc domain riêng, chỉ gửi cùng tên cookie với thuộc tính khác có thể không xóa đúng cookie cũ.

Cookie hết hạn không tự thu hồi token tương ứng ở server. Với remember-me hoặc refresh token, cần dọn cả trạng thái phía server nếu cơ chế đó có lưu token.

## 4. Kiểm thử SecurityContextLogoutHandler trực tiếp

Có thể kiểm tra handler độc lập với filter chain bằng `MockHttpServletRequest`, `MockHttpServletResponse` và `MockHttpSession`.

~~~java
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.logout.SecurityContextLogoutHandler;

import static org.assertj.core.api.Assertions.assertThat;

class SecurityContextLogoutHandlerTest {

    @AfterEach
    void clearThreadContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void invalidatesSessionAndClearsAuthentication() {
        var handler = new SecurityContextLogoutHandler();
        var request = new MockHttpServletRequest();
        var response = new MockHttpServletResponse();
        var session = new MockHttpSession();
        session.setAttribute("temporary-state", "private-data");
        request.setSession(session);

        Authentication authentication =
                UsernamePasswordAuthenticationToken.authenticated(
                        "lan", null, java.util.List.of());
        SecurityContextHolder.getContext().setAuthentication(authentication);

        handler.logout(request, response, authentication);

        assertThat(session.isInvalid()).isTrue();
        assertThat(SecurityContextHolder.getContext().getAuthentication())
                .isNull();
    }
}
~~~

Test này xác minh hai hiệu ứng quan trọng: session không còn hợp lệ và thread context không còn authentication. `@AfterEach` dọn context của test để trạng thái không rò sang test khác. Không nên chỉ assert `SecurityContextHolder.getContext()` khác null vì holder có thể tạo context rỗng theo chiến lược hiện tại; cần kiểm tra `getAuthentication()` đã null.

Nếu ứng dụng chủ động giữ session khi logout hoặc dùng stateless repository, cấu hình handler và assertion phải phản ánh chính sách đó. Đừng mặc định mọi ứng dụng phải invalidation một HTTP session không tồn tại.

## 5. Kiểm thử CookieClearingLogoutHandler

Ví dụ tạo handler để xóa cookie phiên tùy chỉnh và cookie remember-me:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.web.authentication.logout.CookieClearingLogoutHandler;

import static org.assertj.core.api.Assertions.assertThat;

class CookieClearingLogoutHandlerTest {

    @Test
    void expiresConfiguredCookies() {
        CookieClearingLogoutHandler handler =
                new CookieClearingLogoutHandler(
                        "APP_SESSION", "remember-me");
        MockHttpServletResponse response = new MockHttpServletResponse();

        handler.logout(
                new MockHttpServletRequest(),
                response,
                null);

        String setCookieHeaders = String.join(
                "\n", response.getHeaders("Set-Cookie"));

        assertThat(setCookieHeaders).contains("APP_SESSION=");
        assertThat(setCookieHeaders).contains("remember-me=");
        assertThat(setCookieHeaders).contains("Max-Age=0");
    }
}
~~~

Tên cookie trong ví dụ là tên minh họa. Kiểm tra header `Set-Cookie` thay vì chỉ kiểm tra cookie request đầu vào: logout cần gửi chỉ thị hết hạn về browser. Trong ứng dụng thực, hãy xác nhận path/domain được tạo ra phù hợp với cookie ban đầu và không xóa nhầm cookie của chức năng khác.

## 6. Cấu hình logout với handler tùy chỉnh

Spring Security DSL cho phép thêm logout handler và cấu hình success handler:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.logout.CookieClearingLogoutHandler;
import org.springframework.security.web.authentication.logout.LogoutSuccessHandler;

@Configuration
class ApplicationLogoutConfiguration {

    @Bean
    SecurityFilterChain applicationSecurityFilterChain(
            HttpSecurity http) throws Exception {

        LogoutSuccessHandler successHandler =
                (request, response, authentication) ->
                        response.setStatus(HttpStatus.NO_CONTENT.value());

        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated());

        http.logout(logout -> logout
                .logoutUrl("/logout")
                .addLogoutHandler(
                        new CookieClearingLogoutHandler(
                                "APP_SESSION", "remember-me"))
                .logoutSuccessHandler(successHandler));

        return http.build();
    }
}
~~~

`LogoutConfigurer` đã đăng ký các handler mặc định cần thiết cho cơ chế Spring Security được bật, chẳng hạn xử lý `SecurityContext`, remember-me và CSRF. `addLogoutHandler(...)` bổ sung cleanup tùy chỉnh. Không tự thay thế các handler mặc định nếu chưa hiểu tác động đến session/context của ứng dụng.

Success handler ví dụ trả `204 No Content`; không có response body. Nếu API cần JSON, hãy viết success handler tùy chỉnh và chỉ trả các trường công khai. Nếu ứng dụng dùng form login cho browser, redirect mặc định `/login?logout` có thể phù hợp hơn.

## 7. Kiểm thử logout qua MockMvc

`spring-security-test` cung cấp request postprocessor `csrf()` và `user(...)`, còn `MockMvc` gửi request qua filter chain. Với CSRF đang bật, dùng POST và cung cấp token hợp lệ.

Giả sử test context có `ApplicationLogoutConfiguration`, một endpoint `/api/profile` được bảo vệ và logout success handler trả 204:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LogoutHttpTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void authenticatedUserCanLogout() throws Exception {
        mockMvc.perform(post("/logout")
                        .with(user("lan"))
                        .with(csrf()))
                .andExpect(status().isNoContent());
    }

    @Test
    void logoutInvalidatesExistingSession() throws Exception {
        MockHttpSession session = new MockHttpSession();
        session.setAttribute("temporary-state", "private-data");

        mockMvc.perform(post("/logout")
                        .session(session)
                        .with(user("lan"))
                        .with(csrf()))
                .andExpect(status().isNoContent());

        assertThat(session.isInvalid()).isTrue();
    }
}
~~~

Các test giả định cấu hình session-based mặc định của Servlet và endpoint logout đúng URL. `user("lan")` dựng `Authentication` để cô lập hành vi logout; nó không chứng minh người dùng đã đăng nhập bằng mật khẩu thật. Nếu cần xác minh toàn bộ luồng đăng nhập rồi đăng xuất, hãy thực hiện login trước, giữ session trả về, rồi gửi POST logout bằng chính session đó.

### Kiểm tra trạng thái sau logout

Một bài test quan trọng là xác minh session cũ không thể dùng để truy cập tài nguyên yêu cầu đăng nhập. Có thể tổ chức test theo chuỗi:

1. Gửi request đã xác thực đến endpoint được bảo vệ và giữ session.
2. Gửi POST `/logout` với cùng session và CSRF token hợp lệ.
3. Xác minh session đã invalid.
4. Gửi request mới bằng session ID cũ và xác minh nó không khôi phục danh tính cũ.

Trong `MockMvc`, việc dùng lại trực tiếp một `MockHttpSession` đã invalid có thể làm test harness ném lỗi khi truy cập session. Khi đó, kiểm tra `session.isInvalid()` ở bước 3 là assertion trực tiếp; nếu cần chứng minh request tiếp theo, dùng client/session cookie qua server test phù hợp và gửi lại session ID cũ.

## 8. CSRF token, remember-me và cookie

### CSRF token

Khi CSRF đang bật, Spring Security có `CsrfLogoutHandler` để xóa token hiện tại khỏi `CsrfTokenRepository` khi logout. Nếu ứng dụng dùng `HttpSessionCsrfTokenRepository`, session invalidation cũng làm dữ liệu session cũ không còn được dùng. Nếu dùng `CookieCsrfTokenRepository`, cần xác minh cookie CSRF được làm mới/xóa theo cấu hình cụ thể.

Để kiểm tra bảo vệ logout:

- POST `/logout` có CSRF token hợp lệ phải đi qua logout filter.
- POST `/logout` thiếu token thường bị từ chối với `403` trước khi logout handler chạy.
- Sau logout, token/cookie cũ không nên được xem là trạng thái CSRF mới hợp lệ nếu chính sách yêu cầu làm mới.

Không diễn giải `403` từ request logout thiếu CSRF là logout handler đã từ chối; request có thể chưa đến `LogoutFilter`.

### Remember-me

Nếu bật remember-me, logout cần xóa cookie remember-me và thu hồi token phía server khi cơ chế lưu token có hỗ trợ. Kiểm tra cả hai mặt:

1. Response logout gửi cookie hết hạn.
2. Token/cookie cũ không thể tự động xác thực lại ở request tiếp theo.

Chỉ kiểm tra `Set-Cookie` là chưa đủ nếu remember-me dùng persistent token repository. Ngược lại, chỉ kiểm tra token server đã bị xóa cũng chưa bảo đảm browser đã nhận chỉ thị xóa cookie.

### Clear-Site-Data

Ứng dụng có thể gửi header `Clear-Site-Data` khi logout để yêu cầu browser xóa một số loại dữ liệu như cache, cookies hoặc storage trong phạm vi origin. Đây là hành vi phụ thuộc browser và cấu hình header; không thay thế việc server invalidation session hoặc thu hồi token. Nếu sử dụng, hãy kiểm tra header được gửi đúng directive đã chọn và cân nhắc tác động đến dữ liệu khác cùng origin.

## 9. Logout trong ứng dụng stateless dùng JWT

Với API resource server stateless, access token JWT thường là token tự chứa. Xóa `SecurityContext` trong request hiện tại không làm chữ ký JWT hết hiệu lực. Nếu token chưa hết hạn và không có cơ chế thu hồi bổ sung, client có thể gửi lại cùng JWT ở request sau và vẫn được xác thực.

Vì vậy, cần phân biệt:

| Cơ chế | Logout có thể làm gì? | Giới hạn |
| --- | --- | --- |
| Session-based authentication | Invalidate session, xóa context và cookie liên quan | Cần bảo vệ session ID cũ và dọn dữ liệu phía server |
| JWT access token ngắn hạn | Xóa token ở client và kết thúc trạng thái UI | JWT đã phát hành có thể vẫn hợp lệ đến khi hết hạn |
| Refresh token có lưu trạng thái | Thu hồi refresh token/token family ở server | Cần kiểm tra token cũ không thể cấp access token mới |
| JWT denylist/revocation registry | Đánh dấu `jti` hoặc token ID bị thu hồi | Resource server phải kiểm tra registry; có chi phí lưu trữ/độ trễ |
| OAuth2/OIDC session | Kết thúc local session; có thể khởi tạo logout với Identity Provider | Local logout và logout tại provider là hai thao tác riêng |

Trong hệ thống JWT, logout thường bao gồm xóa token khỏi nơi client lưu, thu hồi refresh token nếu có, và áp dụng denylist hoặc thời hạn access token ngắn theo yêu cầu bảo mật. Không khẳng định `POST /logout` đã vô hiệu hóa JWT nếu server không có cơ chế thu hồi.

Với OAuth2/OIDC, logout ứng dụng có thể chỉ kết thúc session cục bộ. Nếu cần đăng xuất khỏi Identity Provider, ứng dụng phải triển khai cơ chế logout phù hợp của nhà cung cấp/OIDC (ví dụ RP-Initiated Logout khi hỗ trợ) và kiểm thử redirect, callback, state và kết quả local session riêng.

## 10. Logout trong Spring WebFlux

Reactive stack dùng các hợp đồng riêng:

- `ServerLogoutHandler` nhận `WebFilterExchange` và `Authentication`, trả `Mono<Void>`.
- `ServerLogoutSuccessHandler` nhận `WebFilterExchange` và `Authentication`, trả `Mono<Void>`.

Các triển khai thường dùng:

| Thành phần | Vai trò |
| --- | --- |
| `SecurityContextServerLogoutHandler` | Xóa `SecurityContext` Reactive |
| `WebSessionServerLogoutHandler` | Invalidate `WebSession` |
| `DelegatingServerLogoutHandler` | Gọi nhiều logout handler theo thứ tự |
| `RedirectServerLogoutSuccessHandler` | Redirect sau khi cleanup |
| Success handler tùy chỉnh | Trả status hoặc JSON qua `ServerHttpResponse` |

Ví dụ cấu hình Reactive dùng handler xóa context và invalidate web session:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.logout.DelegatingServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.SecurityContextServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.WebSessionServerLogoutHandler;

@Configuration
class ReactiveLogoutConfiguration {

    @Bean
    SecurityWebFilterChain reactiveSecurityWebFilterChain(
            ServerHttpSecurity http) {
        var logoutHandler = new DelegatingServerLogoutHandler(
                new SecurityContextServerLogoutHandler(),
                new WebSessionServerLogoutHandler());

        return http
                .authorizeExchange(exchanges -> exchanges
                        .anyExchange().authenticated())
                .logout(logout -> logout
                        .logoutHandler(logoutHandler)
                        .logoutSuccessHandler((exchange, authentication) -> {
                            var response = exchange.getExchange().getResponse();
                            response.setStatusCode(HttpStatus.NO_CONTENT);
                            return response.setComplete();
                        }))
                .build();
    }
}
~~~

Đây là cấu hình minh họa cho WebFlux. Tùy phiên bản Spring Security, tên API hoặc cách cấu hình logout có thể khác; hãy dùng `ServerHttpSecurity` và các handler Reactive cùng phiên bản. Không trộn `LogoutHandler` Servlet với `ServerLogoutHandler`.

### Kiểm thử Reactive bằng WebTestClient

Giả sử ứng dụng WebFlux có logout handler trên và logout success handler trả 204:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveLogoutHttpTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void authenticatedUserCanLogout() {
        webTestClient.mutateWith(mockUser("lan"))
                .mutateWith(csrf())
                .post()
                .uri("/logout")
                .exchange()
                .expectStatus().isNoContent();
    }
}
~~~

Test giả lập `Authentication` để kiểm tra logout filter và handler; nó không chứng minh người dùng đã đăng nhập bằng mật khẩu hoặc token thật. Nếu cần xác minh `WebSession` bị invalid, có thể giữ session cookie từ response trước logout và gửi request sau logout để chứng minh session cũ không còn xác thực.

## 11. Những lỗi thường gặp

**Chỉ redirect về login mà không dọn trạng thái.** Response chuyển hướng không chứng minh session, context hoặc token đã bị vô hiệu hóa. Kiểm tra cleanup riêng.

**Nhầm LogoutHandler với LogoutSuccessHandler.** Handler thứ nhất dọn trạng thái; handler thứ hai tạo response sau cleanup. Không đặt logic thu hồi token chỉ trong success handler nếu response có thể lỗi hoặc bị thay đổi.

**Quên CSRF token khi gửi POST logout.** Request có thể bị chặn trước `LogoutFilter` và nhận 403. Dùng `csrf()` trong test hợp lệ; có một test riêng để xác minh request thiếu token bị từ chối.

**Giả định mọi cookie đều tự hết hạn khi session invalid.** Session invalidation và xóa cookie phía browser là hai việc khác nhau. Kiểm tra `Set-Cookie` nếu cần xóa cookie rõ ràng.

**Xóa cookie sai path/domain.** Browser phân biệt cookie theo thuộc tính phạm vi. Dùng cùng path/domain phù hợp với cookie ban đầu.

**Bỏ qua remember-me.** Session đã bị invalidate nhưng cookie remember-me vẫn có thể khởi tạo xác thực mới. Nếu bật remember-me, kiểm tra cả cookie lẫn persistent token.

**Cho rằng xóa SecurityContext làm JWT hết hiệu lực.** JWT tự chứa có thể vẫn hợp lệ đến khi hết hạn. Cần revoke refresh token, denylist hoặc chiến lược token ngắn hạn phù hợp.

**Dùng @WithMockUser để chứng minh login thật.** Annotation tạo sẵn `Authentication`. Nó hữu ích để kiểm tra logout/authorization trong một request đã xác thực, nhưng không kiểm tra provider hay password encoder.

**Dùng handler Servlet trong Reactive.** WebFlux có `ServerLogoutHandler` và `ServerLogoutSuccessHandler`, trả `Mono<Void>`.

**Dọn dữ liệu quá rộng.** Logout nên xóa trạng thái phiên và token thuộc phiên đăng nhập. Không xóa dữ liệu nghiệp vụ bền vững của người dùng như đơn hàng hoặc hồ sơ.

## 12. Bài thực hành

1. Viết test trực tiếp cho `SecurityContextLogoutHandler`: xác minh session invalid và `Authentication` bị xóa khỏi `SecurityContextHolder`.
2. Dùng `CookieClearingLogoutHandler` để hết hạn hai cookie. Kiểm tra `Set-Cookie`, `Max-Age` và phạm vi path/domain.
3. Cấu hình logout success handler trả 204. Dùng `MockMvc` gửi POST `/logout` có CSRF token và xác minh session cũ không còn hợp lệ.
4. Bỏ CSRF token khỏi request logout. Xác minh request bị từ chối trước khi cleanup chạy.
5. Bật remember-me và kiểm tra logout xóa cookie cùng token phía server; thử lại cookie cũ để xác nhận không thể đăng nhập.
6. Với resource server JWT, mô tả và kiểm thử chính sách logout: xóa token client, thu hồi refresh token hoặc kiểm tra denylist. Chứng minh một JWT chưa hết hạn không tự mất hiệu lực chỉ vì context của request trước đã bị xóa.
7. Viết `ServerLogoutHandler`/`ServerLogoutSuccessHandler` hoặc dùng các triển khai Reactive có sẵn. Dùng `WebTestClient` xác minh logout và trạng thái `WebSession` sau đó.

Một bộ kiểm thử logout có giá trị phải xác minh **các trạng thái cũ đã bị dọn, credentials/token cũ không thể tiếp tục khôi phục phiên trái với chính sách, và response thành công chỉ xuất hiện sau quy trình cleanup**. Kiểm tra cả handler trực tiếp lẫn request HTTP giúp bảo đảm logout hoạt động đúng trên Servlet và Reactive.
