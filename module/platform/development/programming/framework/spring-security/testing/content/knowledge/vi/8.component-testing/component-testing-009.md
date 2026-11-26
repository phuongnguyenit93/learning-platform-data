# AuthenticationSuccessHandler và AuthenticationFailureHandler

## 1. Vai trò của hai handler

Khi người dùng gửi thông tin đăng nhập, ứng dụng cần quyết định phản hồi sau khi xác thực thành công hoặc thất bại. Spring Security tách hai trường hợp thành hai callback: **AuthenticationSuccessHandler** xử lý đăng nhập thành công và **AuthenticationFailureHandler** xử lý lần đăng nhập thất bại.

Bài học thuộc chương **Kiểm thử thành phần** của mô-đun **SPRING_SECURITY_TESTING**, tập trung kiểm chứng xác thực, phân quyền và bảo vệ HTTP trên Servlet và Reactive bằng **spring-security-test**, **MockMvc**, **WebTestClient**, **@WithMockUser**, **SecurityContext** và các cơ chế JWT/OAuth2/OIDC giả lập.

Sau bài học, bạn có thể phân biệt hai handler với **AuthenticationEntryPoint** và **AccessDeniedHandler**, kiểm thử từng handler trực tiếp, rồi xác minh chúng được gắn đúng vào filter chain qua HTTP.

## 2. Hợp đồng và thời điểm được gọi

Trong Servlet, success handler có hợp đồng:

~~~java
public interface AuthenticationSuccessHandler {
    void onAuthenticationSuccess(
            HttpServletRequest request,
            HttpServletResponse response,
            Authentication authentication)
            throws IOException, ServletException;
}
~~~

Failure handler có hợp đồng:

~~~java
public interface AuthenticationFailureHandler {
    void onAuthenticationFailure(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception)
            throws IOException, ServletException;
}
~~~

Success handler được gọi sau khi filter xác thực credentials thành công. Nó có thể chuyển hướng về URL đã lưu, đưa người dùng đến trang mặc định hoặc trả JSON. Failure handler được gọi khi lần đăng nhập chủ động thất bại; nó có thể redirect về trang lỗi hoặc trả JSON/HTTP status.

Một số triển khai có sẵn:

| Handler | Hành vi |
| --- | --- |
| **SavedRequestAwareAuthenticationSuccessHandler** | Ưu tiên quay lại URL được lưu trước khi đăng nhập; nếu không có thì dùng URL mặc định |
| **SimpleUrlAuthenticationSuccessHandler** | Chuyển hướng đến URL đích đã cấu hình |
| **ForwardAuthenticationSuccessHandler** | Forward đến URL nội bộ |
| **SimpleUrlAuthenticationFailureHandler** | Redirect đến URL lỗi hoặc trả status lỗi nếu không cấu hình URL |
| **ExceptionMappingAuthenticationFailureHandler** | Chọn URL lỗi theo loại ngoại lệ |
| **DelegatingAuthenticationFailureHandler** | Chọn failure handler theo loại ngoại lệ, có handler mặc định |

Success handler không xác minh mật khẩu và không cấp quyền. Failure handler cũng không quyết định một người dùng đã đăng nhập có được truy cập tài nguyên hay không. Những việc đó thuộc provider/manager và authorization rule.

## 3. Phân biệt với entry point và access denied handler

| Thành phần | Thời điểm | Phản hồi điển hình |
| --- | --- | --- |
| **AuthenticationSuccessHandler** | Credentials được gửi và xác thực thành công | Redirect hoặc response thành công |
| **AuthenticationFailureHandler** | Credentials được gửi nhưng xác thực thất bại | Redirect trang lỗi hoặc response 401 tùy cấu hình |
| **AuthenticationEntryPoint** | Request cần xác thực nhưng chưa có credentials phù hợp | 401 challenge hoặc redirect login |
| **AccessDeniedHandler** | Người gọi đã xác thực nhưng thiếu quyền | 403 Forbidden |

Với form login, **UsernamePasswordAuthenticationFilter** nhận form, gọi **AuthenticationManager**, rồi gọi success hoặc failure handler tương ứng. Anonymous truy cập một URL cần đăng nhập thường đi qua **ExceptionTranslationFilter** và **AuthenticationEntryPoint**. Người đã đăng nhập nhưng thiếu role thường đi qua **AccessDeniedHandler**.

HTTP Basic thường hoạt động khác: **BasicAuthenticationFilter** xử lý credentials trên từng request rồi tiếp tục filter chain; không mặc định gọi **AuthenticationSuccessHandler** cho mỗi request Basic thành công. Vì vậy, khi kiểm thử callback success/failure, hãy xác định filter cụ thể đang sử dụng handler, ví dụ form login hoặc **AuthenticationFilter**.

## 4. Kiểm thử handler chuyển hướng trực tiếp

Success handler chuyển hướng đến URL mặc định:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationSuccessHandler;

import static org.assertj.core.api.Assertions.assertThat;

class SimpleUrlAuthenticationSuccessHandlerTest {

    @Test
    void redirectsToConfiguredDefaultUrl() throws Exception {
        var handler = new SimpleUrlAuthenticationSuccessHandler("/dashboard");
        Authentication authentication =
                UsernamePasswordAuthenticationToken.authenticated(
                        "lan", null,
                        AuthorityUtils.createAuthorityList("ROLE_USER"));
        var request = new MockHttpServletRequest();
        var response = new MockHttpServletResponse();

        handler.onAuthenticationSuccess(request, response, authentication);

        assertThat(response.getStatus()).isEqualTo(302);
        assertThat(response.getRedirectedUrl()).endsWith("/dashboard");
    }
}
~~~

Test xác nhận handler chuyển hướng đến URL mặc định. Trong ứng dụng có saved request, **SavedRequestAwareAuthenticationSuccessHandler** có thể ưu tiên URL đã lưu; khi đó cần test cả trường hợp có và không có saved request.

Failure handler chuyển hướng đến URL báo lỗi:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;

import static org.assertj.core.api.Assertions.assertThat;

class SimpleUrlAuthenticationFailureHandlerTest {

    @Test
    void redirectsToConfiguredFailureUrl() throws Exception {
        var handler = new SimpleUrlAuthenticationFailureHandler("/login?error");
        var request = new MockHttpServletRequest();
        var response = new MockHttpServletResponse();

        handler.onAuthenticationFailure(
                request, response,
                new BadCredentialsException("Invalid credentials"));

        assertThat(response.getStatus()).isEqualTo(302);
        assertThat(response.getRedirectedUrl()).endsWith("/login?error");
    }
}
~~~

Nếu không cấu hình failure URL, **SimpleUrlAuthenticationFailureHandler** có thể trả status lỗi thay vì redirect. Với saved request, URL đã lưu có thể được ưu tiên hơn URL mặc định; nên kiểm thử riêng trường hợp có và không có saved request.

## 5. JSON handler cho REST API

API thường cần response JSON thay vì redirect HTML. Success handler chỉ trả principal name và trạng thái đăng nhập; không trả credentials hoặc toàn bộ đối tượng Authentication.

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.MediaType;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;

final class JsonAuthenticationSuccessHandler
        implements AuthenticationSuccessHandler {

    private final ObjectMapper objectMapper;

    JsonAuthenticationSuccessHandler(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public void onAuthenticationSuccess(
            HttpServletRequest request,
            HttpServletResponse response,
            Authentication authentication)
            throws IOException, ServletException {
        response.setStatus(HttpServletResponse.SC_OK);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        objectMapper.writeValue(response.getOutputStream(), Map.of(
                "status", "authenticated",
                "username", authentication.getName()));
    }
}
~~~

Failure handler dùng thông báo chung để không tiết lộ tài khoản có tồn tại hay không hoặc nguyên nhân nội bộ:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.MediaType;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;

final class JsonAuthenticationFailureHandler
        implements AuthenticationFailureHandler {

    private final ObjectMapper objectMapper;

    JsonAuthenticationFailureHandler(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public void onAuthenticationFailure(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception)
            throws IOException, ServletException {
        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        objectMapper.writeValue(response.getOutputStream(), Map.of(
                "error", "authentication_failed",
                "message", "Username or password is incorrect"));
    }
}
~~~

Kiểm thử trực tiếp:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;

import static org.assertj.core.api.Assertions.assertThat;

class JsonAuthenticationHandlersTest {

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void successHandlerReturnsPrincipalName() throws Exception {
        var handler = new JsonAuthenticationSuccessHandler(mapper);
        Authentication authentication =
                UsernamePasswordAuthenticationToken.authenticated(
                        "lan", null,
                        AuthorityUtils.createAuthorityList("ROLE_USER"));
        var response = new MockHttpServletResponse();

        handler.onAuthenticationSuccess(
                new MockHttpServletRequest(), response, authentication);

        assertThat(response.getStatus()).isEqualTo(200);
        assertThat(response.getContentType())
                .isEqualTo(MediaType.APPLICATION_JSON_VALUE);
        assertThat(response.getContentAsString())
                .contains("\"status\":\"authenticated\"")
                .contains("\"username\":\"lan\"");
    }

    @Test
    void failureHandlerReturnsGeneric401WithoutLeakingException()
            throws Exception {
        var handler = new JsonAuthenticationFailureHandler(mapper);
        var response = new MockHttpServletResponse();

        handler.onAuthenticationFailure(
                new MockHttpServletRequest(), response,
                new BadCredentialsException("internal user lookup detail"));

        assertThat(response.getStatus()).isEqualTo(401);
        assertThat(response.getContentType())
                .isEqualTo(MediaType.APPLICATION_JSON_VALUE);
        assertThat(response.getContentAsString())
                .contains("\"error\":\"authentication_failed\"")
                .contains("Username or password is incorrect")
                .doesNotContain("internal user lookup detail");
    }
}
~~~

Các test trực tiếp xác nhận cách tạo response, nhưng chưa chứng minh filter chain gọi đúng handler. Cần có test HTTP để xác minh tích hợp.

## 6. Cấu hình form login và MockMvc

Với ứng dụng Servlet, DSL **formLogin(...)** cho phép gắn hai handler:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class FormLoginSecurityConfiguration {

    @Bean
    SecurityFilterChain formLoginSecurityFilterChain(
            HttpSecurity http, ObjectMapper objectMapper) throws Exception {
        var successHandler =
                new JsonAuthenticationSuccessHandler(objectMapper);
        var failureHandler =
                new JsonAuthenticationFailureHandler(objectMapper);

        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public/**", "/login").permitAll()
                .anyRequest().authenticated());

        http.formLogin(form -> form
                .successHandler(successHandler)
                .failureHandler(failureHandler)
                .permitAll());

        return http.build();
    }
}
~~~

Ứng dụng cần có UserDetailsService và PasswordEncoder tương thích với tài khoản test. Khi dùng handler JSON, response sau form login là JSON thay vì redirect đến trang mặc định.

**spring-security-test** cung cấp request builder **formLogin()** để gửi form login qua filter thật. Giả sử test context có tài khoản lan với mật khẩu test correct-password, endpoint xử lý login mặc định /login và hai handler ở trên:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.security.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FormLoginHandlerHttpTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void validCredentialsInvokeSuccessHandler() throws Exception {
        mockMvc.perform(formLogin()
                        .user("lan")
                        .password("correct-password"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith("application/json"))
                .andExpect(content().json("""
                        {
                          "status": "authenticated",
                          "username": "lan"
                        }
                        """));
    }

    @Test
    void invalidCredentialsInvokeFailureHandler() throws Exception {
        mockMvc.perform(formLogin()
                        .user("lan")
                        .password("wrong-password"))
                .andExpect(status().isUnauthorized())
                .andExpect(content().contentTypeCompatibleWith("application/json"))
                .andExpect(content().json("""
                        {
                          "error": "authentication_failed",
                          "message": "Username or password is incorrect"
                        }
                        """));
    }
}
~~~

Ví dụ giả định filter dùng URL login mặc định và test context có provider thật. Nếu đổi loginProcessingUrl, username/password parameter hoặc CSRF policy, điều chỉnh request builder cho đúng cấu hình. **formLogin()** trong các phiên bản spring-security-test hiện đại hỗ trợ request form login với CSRF; nếu test context tùy chỉnh không thêm token, có thể bổ sung request postprocessor csrf().

Không dùng **@WithMockUser** cho hai ca trên: annotation tạo sẵn Authentication, bỏ qua việc gửi credentials đến filter. Nó phù hợp để kiểm tra authorization sau khi đã có principal, không chứng minh success/failure handler đã chạy.

## 7. Saved request và redirect sau đăng nhập

Với ứng dụng web dùng session, **SavedRequestAwareAuthenticationSuccessHandler** thường được dùng để quay lại URL mà người dùng muốn mở trước khi bị chuyển đến trang login. Khi không có saved request, handler dùng URL mặc định theo cấu hình.

Khi kiểm thử tính năng này, cần giữ cùng session giữa hai request:

1. Gọi một URL được bảo vệ trong trạng thái anonymous.
2. Xác nhận ứng dụng chuyển hướng đến trang đăng nhập và lưu request ban đầu.
3. Gửi form login hợp lệ trong cùng session.
4. Xác nhận success handler chuyển hướng về URL đã lưu.

Không tạo session mới giữa bước 1 và bước 3, nếu không saved request có thể bị mất. Nếu cấu hình alwaysUseDefaultTargetUrl, handler sẽ bỏ qua saved request và chuyển đến URL mặc định; test cần phản ánh lựa chọn này.

## 8. AuthenticationFilter tùy chỉnh

**AuthenticationFilter** cũng có thể dùng **AuthenticationConverter**, **AuthenticationManager**, success handler và failure handler. Luồng tổng quát:

~~~mermaid
flowchart TD
    A["Request đến filter"] --> B["AuthenticationConverter"]
    B --> C{"Có Authentication?"}
    C -- "Không" --> D["Bỏ qua filter / tiếp tục chain"]
    C -- "Có" --> E["AuthenticationManager.authenticate"]
    E --> F{"Xác thực thành công?"}
    F -- "Có" --> G["Thiết lập SecurityContext"]
    G --> H["AuthenticationSuccessHandler"]
    F -- "Không" --> I["Xử lý thất bại"]
    I --> J["AuthenticationFailureHandler"]
~~~

Các ca cần kiểm thử:

| Ca | Kết quả cần xác minh |
| --- | --- |
| Converter trả null | Filter không gọi manager và request đi tiếp theo cấu hình |
| Converter tạo token, manager xác thực thành công | Success handler được gọi đúng một lần |
| Converter tạo token, manager ném AuthenticationException | Failure handler được gọi |
| Xác thực thành công nhưng context không được lưu theo cấu hình | Request tiếp theo không có trạng thái đăng nhập như mong đợi |

Không chỉ kiểm tra mock handler được gọi. Nên có ít nhất một test HTTP qua filter để xác nhận response và trạng thái SecurityContext phù hợp với ứng dụng.

## 9. Success/failure handler trong WebFlux

Reactive stack dùng các hợp đồng riêng:

- **ServerAuthenticationSuccessHandler** nhận **WebFilterExchange** và **Authentication**, trả **Mono<Void>**.
- **ServerAuthenticationFailureHandler** nhận **WebFilterExchange** và **AuthenticationException**, trả **Mono<Void>**.

Không dùng handler Servlet với HttpServletRequest/HttpServletResponse trong WebFlux. Một số triển khai có sẵn hỗ trợ redirect; ứng dụng có thể viết handler Reactive tùy chỉnh để trả JSON.

Ví dụ success handler JSON Reactive:

~~~java
import java.util.Map;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.server.WebFilterExchange;
import org.springframework.security.web.server.authentication.ServerAuthenticationSuccessHandler;
import reactor.core.publisher.Mono;

final class JsonServerAuthenticationSuccessHandler
        implements ServerAuthenticationSuccessHandler {

    private final ObjectMapper objectMapper;

    JsonServerAuthenticationSuccessHandler(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public Mono<Void> onAuthenticationSuccess(
            WebFilterExchange webFilterExchange,
            Authentication authentication) {
        var response = webFilterExchange.getExchange().getResponse();
        response.setStatusCode(HttpStatus.OK);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);

        byte[] body;
        try {
            body = objectMapper.writeValueAsBytes(Map.of(
                    "status", "authenticated",
                    "username", authentication.getName()));
        } catch (JsonProcessingException ex) {
            return Mono.error(ex);
        }

        var buffer = response.bufferFactory().wrap(body);
        return response.writeWith(Mono.just(buffer));
    }
}
~~~

Ví dụ failure handler Reactive:

~~~java
import java.util.Map;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.server.WebFilterExchange;
import org.springframework.security.web.server.authentication.ServerAuthenticationFailureHandler;
import reactor.core.publisher.Mono;

final class JsonServerAuthenticationFailureHandler
        implements ServerAuthenticationFailureHandler {

    private final ObjectMapper objectMapper;

    JsonServerAuthenticationFailureHandler(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public Mono<Void> onAuthenticationFailure(
            WebFilterExchange webFilterExchange,
            AuthenticationException exception) {
        var response = webFilterExchange.getExchange().getResponse();
        response.setStatusCode(HttpStatus.UNAUTHORIZED);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);

        byte[] body;
        try {
            body = objectMapper.writeValueAsBytes(Map.of(
                    "error", "authentication_failed",
                    "message", "Username or password is incorrect"));
        } catch (JsonProcessingException ex) {
            return Mono.error(ex);
        }

        var buffer = response.bufferFactory().wrap(body);
        return response.writeWith(Mono.just(buffer));
    }
}
~~~

Đây là ví dụ tối giản. Trong ứng dụng thực, cần bảo đảm response chưa được commit, chỉ ghi body một lần và không trả exception message nội bộ.

### Kiểm thử Reactive handler trực tiếp

Có thể tạo **MockServerWebExchange**, gọi handler và dùng **StepVerifier** để kiểm tra publisher hoàn tất. Sau đó xác minh status/header của response. Với body JSON và việc handler được filter gọi đúng, nên có test **WebTestClient** gắn vào ứng dụng Reactive.

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.server.WebFilterExchange;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class JsonServerAuthenticationSuccessHandlerTest {

    @Test
    void returnsOkForAuthenticatedPrincipal() {
        var handler = new JsonServerAuthenticationSuccessHandler(
                new ObjectMapper());
        var exchange = MockServerWebExchange.from(
                MockServerHttpRequest.post("/login").build());
        Authentication authentication =
                UsernamePasswordAuthenticationToken.authenticated(
                        "lan", null, java.util.List.of());
        var webFilterExchange =
                new WebFilterExchange(exchange, chain -> Mono.empty());

        StepVerifier.create(handler.onAuthenticationSuccess(
                        webFilterExchange, authentication))
                .verifyComplete();

        assertThat(exchange.getResponse().getStatusCode())
                .isEqualTo(HttpStatus.OK);
    }
}
~~~

Test cần các dependency Spring WebFlux và Reactor Test. Khi kiểm tra failure handler, tạo một AuthenticationException, gọi `onAuthenticationFailure(...)`, rồi xác minh status 401. `WebTestClient` vẫn cần thiết để chứng minh handler được gắn vào authentication web filter.

### Kiểm thử form login Reactive qua WebTestClient

Với ứng dụng WebFlux có cấu hình form login và hai handler Reactive ở trên, có thể gửi form qua filter chain:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveFormLoginHandlerTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void validCredentialsReachReactiveSuccessHandler() {
        webTestClient.mutateWith(csrf())
                .post()
                .uri("/login")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("username", "lan")
                        .with("password", "correct-password"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.status").isEqualTo("authenticated");
    }

    @Test
    void invalidCredentialsReachReactiveFailureHandler() {
        webTestClient.mutateWith(csrf())
                .post()
                .uri("/login")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("username", "lan")
                        .with("password", "wrong-password"))
                .exchange()
                .expectStatus().isUnauthorized()
                .expectBody()
                .jsonPath("$.error").isEqualTo("authentication_failed");
    }
}
~~~

Ví dụ giả định ứng dụng Reactive có tài khoản test, form login xử lý tại `/login` và các handler JSON được gắn vào cơ chế xác thực. `csrf()` bổ sung token cho request POST khi CSRF đang bật. Nếu ứng dụng dùng tên field hoặc URL xử lý khác, điều chỉnh body và URI theo cấu hình thực tế.

## 10. Những lỗi thường gặp

**Nhầm failure handler với entry point.** Password sai trong form login thường gọi `AuthenticationFailureHandler`; anonymous truy cập một trang được bảo vệ thường gọi `AuthenticationEntryPoint`.

**Dùng success handler để cấp quyền.** Handler chạy sau xác thực thành công. Không dùng nó để thêm role tùy ý; authorities phải đến từ nguồn dữ liệu tin cậy.

**Trả toàn bộ Authentication cho client.** Đối tượng này có thể chứa credentials hoặc chi tiết nội bộ. Chỉ trả các trường công khai cần thiết như principal name và trạng thái.

**Trả exception message khi đăng nhập thất bại.** Không tiết lộ tài khoản có tồn tại, trạng thái bị khóa hay lỗi nội bộ. Dùng thông báo chung và log an toàn nếu cần điều tra.

**Giả định HTTP Basic luôn gọi AuthenticationSuccessHandler.** `BasicAuthenticationFilter` thường xử lý xác thực trong mỗi request và tiếp tục filter chain. Success/failure handler thường gắn với form login hoặc `AuthenticationFilter`; hãy kiểm tra filter cụ thể.

**Dùng @WithMockUser để kiểm tra success/failure handler.** Annotation tạo sẵn `Authentication`, bỏ qua việc gửi credentials đến filter. Dùng `formLogin()` hoặc request đăng nhập thật để xác minh hai handler.

**Không giữ session khi kiểm thử saved request.** Chức năng quay lại URL trước đăng nhập cần request cache và session. Nếu test tạo session mới cho từng request, saved request sẽ không còn.

**Không phân biệt status redirect và JSON.** Handler redirect thường trả 3xx; handler JSON có thể trả 200 sau thành công và 401 sau thất bại. Assertion cần khớp hợp đồng API.

**Dùng handler Servlet trong Reactive.** WebFlux sử dụng `ServerAuthenticationSuccessHandler` và `ServerAuthenticationFailureHandler`, trả `Mono<Void>`.

**Không kiểm tra filter chain.** Unit test handler chỉ chứng minh cách tạo response. Test `MockMvc`/`WebTestClient` mới xác nhận handler được gắn vào đúng filter và được gọi trong luồng thực.

## 11. Bài thực hành

1. Viết JSON success/failure handler. Kiểm thử trực tiếp status, content type, principal name và thông báo lỗi chung.
2. Cấu hình hai handler trong `formLogin(...)`. Dùng `MockMvc` với `formLogin()` để kiểm tra password đúng và sai đều đi qua handler tương ứng.
3. Thay success handler JSON bằng `SavedRequestAwareAuthenticationSuccessHandler`. Kiểm tra anonymous truy cập URL được bảo vệ, đăng nhập thành công và được redirect về URL đã lưu.
4. Viết một `AuthenticationFilter` tùy chỉnh dùng `AuthenticationConverter`. Kiểm tra converter trả `null`, xác thực thành công và xác thực thất bại.
5. Dùng `@WithMockUser` để kiểm tra endpoint phân quyền sau đăng nhập, rồi giải thích vì sao test này không chứng minh success/failure handler đã chạy.
6. Viết handler Reactive trả JSON và kiểm tra bằng `StepVerifier` trực tiếp cùng `WebTestClient` qua filter chain.
7. So sánh form login thất bại với anonymous truy cập endpoint bảo vệ; xác định response do `AuthenticationFailureHandler` và `AuthenticationEntryPoint` tạo ra.

Một bộ kiểm thử hoàn chỉnh cần chứng minh **credentials đúng gọi success handler, credentials sai gọi failure handler và request chưa đăng nhập được xử lý bởi entry point theo đúng giao thức**. Khi kiểm tra cả handler trực tiếp lẫn filter chain, bạn có thể bảo đảm phản hồi đăng nhập nhất quán cho browser và REST client trên Servlet cũng như Reactive.
