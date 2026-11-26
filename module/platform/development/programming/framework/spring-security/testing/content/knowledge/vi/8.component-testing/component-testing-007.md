# AuthenticationEntryPoint và phản hồi chưa xác thực

## 1. Vì sao phản hồi khi chưa đăng nhập cần được kiểm thử?

Một người dùng gọi API được bảo vệ nhưng chưa đăng nhập. Ứng dụng phải quyết định cách bắt đầu quá trình xác thực: trả HTTP `401 Unauthorized` kèm challenge `WWW-Authenticate`, chuyển hướng đến trang đăng nhập, hay trả JSON theo hợp đồng API. Khi người dùng đã đăng nhập nhưng thiếu quyền, ứng dụng thường trả `403 Forbidden` thay vì yêu cầu đăng nhập lại.

Trong Spring Security Servlet, `AuthenticationEntryPoint` định nghĩa cách ứng dụng phản hồi khi cần bắt đầu xác thực. Đây là điểm tích hợp quan trọng giữa security filter chain và giao thức HTTP. Một entry point cấu hình sai có thể làm API trả redirect HTML cho client máy, thiếu header challenge, hoặc tiết lộ thông tin nội bộ trong thông báo lỗi.

Bài học thuộc chương **Kiểm thử thành phần** của mô-đun **SPRING_SECURITY_TESTING**. Mô-đun hướng tới kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế bằng `spring-security-test` trên ứng dụng Servlet và Reactive, sử dụng `MockMvc`, `WebTestClient`, `@WithMockUser`, `SecurityContext` và JWT/OAuth2/OIDC giả lập. Bài này tập trung vào phản hồi dành cho request chưa xác thực, đồng thời phân biệt entry point với failure handler và access denied handler.

Sau bài học, bạn có thể:

- Giải thích vai trò của `AuthenticationEntryPoint` và thời điểm `commence(...)` được gọi.
- Phân biệt `401`, `403`, redirect đăng nhập và các challenge HTTP Basic/Bearer.
- Kiểm thử entry point trực tiếp bằng mock request/response.
- Kiểm thử phản hồi của security filter chain bằng `MockMvc`.
- Thiết kế entry point JSON cho REST API mà không làm lộ thông tin nhạy cảm.
- Nhận biết entry point tương ứng trong WebFlux và kiểm thử bằng `WebTestClient`.

## 2. AuthenticationEntryPoint làm gì?

Trong Servlet, giao diện `org.springframework.security.web.AuthenticationEntryPoint` có phương thức:

~~~java
public interface AuthenticationEntryPoint {
    void commence(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException authException)
            throws IOException, ServletException;
}
~~~

`commence(...)` nhận request gốc, response cần tạo và ngoại lệ xác thực. Nó **bắt đầu hoặc yêu cầu client thực hiện xác thực** theo cơ chế ứng dụng đã chọn. Entry point không kiểm tra mật khẩu, không cấp authorities và không tự thực hiện đăng nhập thành công.

Các cách triển khai phổ biến:

| Entry point | Hành vi thường thấy | Trường hợp sử dụng |
| --- | --- | --- |
| `BasicAuthenticationEntryPoint` | Trả `401` và header `WWW-Authenticate: Basic ...` | API dùng HTTP Basic |
| `BearerTokenAuthenticationEntryPoint` | Trả `401` và challenge Bearer, có thể kèm mã lỗi OAuth2 | Resource server dùng bearer token |
| `LoginUrlAuthenticationEntryPoint` | Chuyển hướng đến URL đăng nhập, thường là `302` | Ứng dụng web dùng form login |
| `HttpStatusEntryPoint` | Trả một HTTP status được cấu hình | API cần status đơn giản, không cần challenge riêng |
| Entry point tùy chỉnh | Trả JSON, XML hoặc response theo hợp đồng ứng dụng | REST API hoặc giao thức nội bộ |
| `DelegatingAuthenticationEntryPoint` | Chọn entry point dựa trên `RequestMatcher` | Một ứng dụng phục vụ nhiều loại client |

Với HTTP `401`, server thường gửi challenge phù hợp qua header `WWW-Authenticate`, để client biết cách cung cấp credentials. HTTP `403` biểu thị server hiểu request nhưng từ chối thực hiện; nó không yêu cầu client đăng nhập lại.

### Luồng xử lý trong security filter chain

`ExceptionTranslationFilter` là thành phần quan trọng chuyển các ngoại lệ bảo mật thành phản hồi HTTP. Khi nhận `AccessDeniedException`, nó kiểm tra trạng thái xác thực:

- Nếu người gọi chưa được xác thực đầy đủ (ví dụ anonymous), filter khởi động xác thực bằng cách gọi `AuthenticationEntryPoint`.
- Nếu người gọi đã xác thực nhưng không đủ quyền, filter chuyển cho `AccessDeniedHandler` để tạo phản hồi bị từ chối, thường là `403`.

~~~mermaid
flowchart TD
    A["Request đến tài nguyên được bảo vệ"] --> B["Security filter chain"]
    B --> C["AccessDeniedException hoặc AuthenticationException"]
    C --> D["ExceptionTranslationFilter / filter xác thực"]
    D --> E{"Người gọi đã xác thực đầy đủ?"}
    E -- "Chưa" --> F["AuthenticationEntryPoint.commence(...)"]
    F --> G["401 challenge hoặc redirect đăng nhập"]
    E -- "Rồi" --> H["AccessDeniedHandler"]
    H --> I["403 Forbidden"]
~~~

Sơ đồ mô tả luồng điển hình của một request bị chặn bởi kiểm soát truy cập. Một số filter xác thực, chẳng hạn HTTP Basic hoặc Bearer token, có thể gọi entry point trực tiếp khi credentials không hợp lệ. Form login thường dùng `AuthenticationFailureHandler` cho lần gửi thông tin đăng nhập thất bại. Vì vậy, không phải mọi lỗi đăng nhập đều đi qua cùng một đường gọi.

## 3. Phân biệt entry point, failure handler và access denied handler

Ba thành phần này giải quyết ba tình huống khác nhau:

| Thành phần | Thời điểm | Kết quả thường thấy |
| --- | --- | --- |
| `AuthenticationEntryPoint` | Client cần bắt đầu xác thực để truy cập tài nguyên được bảo vệ; hoặc filter cần phản hồi một lỗi xác thực | `401`, challenge hoặc redirect |
| `AuthenticationFailureHandler` | Người dùng gửi credentials qua một cơ chế đăng nhập như form login nhưng xác thực thất bại | Redirect về trang lỗi hoặc response tùy chỉnh |
| `AccessDeniedHandler` | Người gọi đã xác thực nhưng không được phép truy cập | `403 Forbidden` |

Ví dụ: một request không có credentials đến `/api/profile` có thể khiến `ExceptionTranslationFilter` gọi entry point. Một request HTTP Basic có mật khẩu sai có thể khiến `BasicAuthenticationFilter` gọi entry point. Còn một form login gửi mật khẩu sai thường gọi failure handler của `UsernamePasswordAuthenticationFilter`.

**Không nên dùng entry point để thay thế mọi xử lý lỗi xác thực.** Nếu mục tiêu là kiểm thử form login thất bại, hãy kiểm tra failure handler. Nếu mục tiêu là kiểm thử người đã đăng nhập thiếu role, hãy kiểm tra access denied handler. Cần kiểm tra đúng thành phần tạo ra phản hồi trong luồng ứng dụng.

### 401 và 403 trong các trường hợp thường gặp

| Trạng thái người gọi | Ví dụ | Kết quả điển hình |
| --- | --- | --- |
| Không có credentials | Gọi endpoint yêu cầu đăng nhập với HTTP Basic | `401` và challenge Basic |
| Credentials không hợp lệ | HTTP Basic password sai | `401` và challenge Basic |
| Bearer token thiếu hoặc không hợp lệ | Gọi resource server không có token hoặc token sai | Thường `401`, challenge Bearer |
| Đã xác thực nhưng thiếu authority | User có `REPORT_READ` gọi endpoint yêu cầu `ADMIN` | `403` |
| Anonymous truy cập URL cần đăng nhập trong web app form login | Trình duyệt mở trang cần xác thực | Thường redirect `302` đến trang login |
| Request POST thiếu CSRF token khi CSRF bật | User có quyền nhưng request thiếu CSRF | Thường `403` trước khi kiểm tra quyền nghiệp vụ |

Các status trong bảng là hành vi phổ biến, không phải cam kết bất biến. `AuthenticationEntryPoint`, `AccessDeniedHandler`, cấu hình CSRF, loại filter và content negotiation đều có thể làm thay đổi response.

## 4. Kiểm thử AuthenticationEntryPoint trực tiếp

Kiểm thử component trực tiếp giúp xác nhận response mà entry point tạo ra, độc lập với filter chain. Ví dụ sau dùng `HttpStatusEntryPoint` để trả `401`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.http.HttpStatus;

import static org.assertj.core.api.Assertions.assertThat;

class HttpStatusEntryPointTest {

    @Test
    void returnsUnauthorizedStatus() throws Exception {
        HttpStatusEntryPoint entryPoint =
                new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED);
        MockHttpServletRequest request = new MockHttpServletRequest();
        MockHttpServletResponse response = new MockHttpServletResponse();

        entryPoint.commence(
                request,
                response,
                new org.springframework.security.authentication
                        .InsufficientAuthenticationException(
                                "Authentication is required"));

        assertThat(response.getStatus()).isEqualTo(401);
    }
}
~~~

Test này chỉ xác nhận status. `HttpStatusEntryPoint` không tự thêm challenge Basic hoặc JSON body. Nếu hợp đồng của API yêu cầu header hay nội dung cụ thể, hãy kiểm thử một entry point đáp ứng chính hợp đồng đó.

### Kiểm thử BasicAuthenticationEntryPoint

`BasicAuthenticationEntryPoint` trả challenge cho client. Ví dụ test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.web.authentication.www.BasicAuthenticationEntryPoint;

import static org.assertj.core.api.Assertions.assertThat;

class BasicAuthenticationEntryPointTest {

    @Test
    void sendsBasicChallengeAndUnauthorizedStatus() throws Exception {
        BasicAuthenticationEntryPoint entryPoint =
                new BasicAuthenticationEntryPoint();
        entryPoint.setRealmName("reports-api");
        entryPoint.afterPropertiesSet();

        MockHttpServletResponse response = new MockHttpServletResponse();

        entryPoint.commence(
                new MockHttpServletRequest(),
                response,
                new BadCredentialsException("Invalid credentials"));

        assertThat(response.getStatus()).isEqualTo(401);
        assertThat(response.getHeader("WWW-Authenticate"))
                .startsWith("Basic")
                .contains("reports-api");
    }
}
~~~

Không nên assert toàn bộ header theo chuỗi quá cứng nếu ứng dụng cho phép thay đổi realm hoặc tham số challenge. Hãy kiểm tra scheme, realm và status cần thiết.

## 5. Xây dựng entry point JSON cho REST API

Một API thường cần response JSON thống nhất thay vì HTML redirect. Entry point tùy chỉnh có thể trả status `401`, content type JSON và một mã lỗi ổn định:

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
import org.springframework.security.web.AuthenticationEntryPoint;

final class JsonAuthenticationEntryPoint implements AuthenticationEntryPoint {

    private final ObjectMapper objectMapper;

    JsonAuthenticationEntryPoint(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public void commence(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException authException)
            throws IOException, ServletException {

        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());

        objectMapper.writeValue(response.getOutputStream(), Map.of(
                "error", "unauthorized",
                "message", "Authentication is required",
                "path", request.getRequestURI()));
    }
}
~~~

Response ví dụ:

~~~json
{
  "error": "unauthorized",
  "message": "Authentication is required",
  "path": "/api/profile"
}
~~~

Không đưa `authException.getMessage()` trực tiếp vào response công khai. Thông báo ngoại lệ có thể chứa chi tiết nội bộ hoặc thông tin không nên tiết lộ. Nếu cần correlation ID, hãy lấy từ cơ chế trace tin cậy của ứng dụng.

### Kiểm thử JSON entry point

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.InsufficientAuthenticationException;

import static org.assertj.core.api.Assertions.assertThat;

class JsonAuthenticationEntryPointTest {

    private final JsonAuthenticationEntryPoint entryPoint =
            new JsonAuthenticationEntryPoint(new ObjectMapper());

    @Test
    void writesStableJsonResponseWithoutLeakingExceptionMessage()
            throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.setRequestURI("/api/profile");
        MockHttpServletResponse response = new MockHttpServletResponse();

        entryPoint.commence(
                request,
                response,
                new InsufficientAuthenticationException(
                        "internal authentication detail"));

        assertThat(response.getStatus()).isEqualTo(401);
        assertThat(response.getContentType())
                .isEqualTo(MediaType.APPLICATION_JSON_VALUE);

        String body = response.getContentAsString();
        assertThat(body).contains("\"error\":\"unauthorized\"");
        assertThat(body).contains("\"path\":\"/api/profile\"");
        assertThat(body).doesNotContain("internal authentication detail");
    }
}
~~~

Assertion kiểm tra nội dung response theo các trường ổn định. Nếu thứ tự field JSON không phải một phần hợp đồng, đừng so sánh toàn bộ JSON dưới dạng chuỗi; có thể parse JSON rồi kiểm tra từng trường.

## 6. Cấu hình entry point cho SecurityFilterChain

Ví dụ ứng dụng Servlet dùng HTTP Basic và entry point JSON:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfiguration {

    @Bean
    AuthenticationEntryPoint apiAuthenticationEntryPoint(
            ObjectMapper objectMapper) {
        return new JsonAuthenticationEntryPoint(objectMapper);
    }

    @Bean
    SecurityFilterChain apiSecurityFilterChain(
            HttpSecurity http,
            AuthenticationEntryPoint apiAuthenticationEntryPoint)
            throws Exception {

        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/public/**").permitAll()
                .anyRequest().authenticated());

        http.httpBasic(basic -> basic
                .authenticationEntryPoint(apiAuthenticationEntryPoint));

        http.exceptionHandling(exceptions -> exceptions
                .authenticationEntryPoint(apiAuthenticationEntryPoint));

        return http.build();
    }
}
~~~

Đặt entry point ở cấu hình HTTP Basic giúp filter dùng response đã chọn khi credentials Basic sai. Cấu hình `exceptionHandling(...)` đặt entry point mặc định cho trường hợp `ExceptionTranslationFilter` cần bắt đầu xác thực khi truy cập tài nguyên được bảo vệ. Khi ứng dụng kết hợp nhiều cơ chế xác thực, hãy kiểm tra entry point cụ thể của từng filter và matcher; một cấu hình mặc định không nhất thiết thay thế cấu hình riêng của mọi filter.

Với form login, response khi form credentials sai thường do `AuthenticationFailureHandler` điều khiển. Entry point chủ yếu được gọi khi anonymous truy cập tài nguyên cần xác thực, chẳng hạn redirect đến trang login.

## 7. Kiểm thử HTTP bằng MockMvc

Giả sử ứng dụng Spring Boot có `ApiSecurityConfiguration` ở trên, endpoint `GET /api/profile` yêu cầu đăng nhập và endpoint `GET /api/public/ping` cho phép truy cập công khai. Test context cũng cần có một `UserDetailsService` và `PasswordEncoder` hợp lệ để HTTP Basic hoạt động.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthenticationEntryPointHttpTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void anonymousRequestReceivesJson401() throws Exception {
        mockMvc.perform(get("/api/profile"))
                .andExpect(status().isUnauthorized())
                .andExpect(content().contentTypeCompatibleWith("application/json"))
                .andExpect(content().json("""
                        {
                          "error": "unauthorized",
                          "message": "Authentication is required",
                          "path": "/api/profile"
                        }
                        """));
    }

    @Test
    void invalidBasicCredentialsReceiveJson401() throws Exception {
        mockMvc.perform(get("/api/profile")
                        .with(httpBasic("lan", "wrong-password")))
                .andExpect(status().isUnauthorized())
                .andExpect(content().contentTypeCompatibleWith("application/json"));
    }

    @Test
    void publicEndpointDoesNotInvokeEntryPoint() throws Exception {
        mockMvc.perform(get("/api/public/ping"))
                .andExpect(status().isOk());
    }
}
~~~

Đây là mẫu tích hợp phụ thuộc endpoint và bean test đã cấu hình. Nếu entry point JSON được dùng đúng, request anonymous và credentials Basic sai đều có thể trả `401` JSON. Test này chứng minh cấu hình entry point được áp dụng trong filter chain, khác với test trực tiếp `commence(...)`.

### Phân biệt 403 do thiếu quyền

Giả sử `/api/admin` yêu cầu `ROLE_ADMIN`. Khi người dùng đã xác thực nhưng không có quyền, response nên được xử lý bởi `AccessDeniedHandler`, không phải entry point:

~~~java
import org.springframework.security.test.context.support.WithMockUser;

@Test
@WithMockUser(username = "lan", authorities = "ROLE_READER")
void authenticatedUserWithoutAdminRoleReceives403() throws Exception {
    mockMvc.perform(get("/api/admin"))
            .andExpect(status().isForbidden());
}
~~~

`@WithMockUser` tạo sẵn `Authentication` trong `SecurityContext`, phù hợp để cô lập kiểm tra phân quyền. Nó không kiểm tra mật khẩu, `UserDetailsService` hoặc provider. Test này chỉ chứng minh người dùng đã được xem là xác thực nhưng thiếu quyền.

Nếu `POST` bị CSRF bảo vệ, request thiếu token cũng có thể trả `403` trước khi đến authorization rule. Khi kiểm tra entry point hoặc quyền nghiệp vụ, hãy gửi CSRF token hợp lệ khi cần:

~~~java
mockMvc.perform(post("/api/profile")
        .with(csrf())
        .with(user("lan").authorities(
                new SimpleGrantedAuthority("PROFILE_WRITE"))))
    .andExpect(status().isForbidden()); // nếu rule từ chối PROFILE_WRITE
~~~

Đoạn này là minh họa cho test authorization, cần import `csrf()`, `user(...)` và `SimpleGrantedAuthority`. Không diễn giải `403` do CSRF thành bằng chứng entry point hoạt động.

## 8. Redirect entry point cho ứng dụng web

Với ứng dụng trình duyệt dùng form login, entry point có thể chuyển hướng anonymous đến trang đăng nhập:

~~~java
import org.springframework.security.web.authentication.LoginUrlAuthenticationEntryPoint;

LoginUrlAuthenticationEntryPoint entryPoint =
        new LoginUrlAuthenticationEntryPoint("/login");
~~~

Khi truy cập một URL được bảo vệ, response thường là `302 Found` với header `Location: /login` (có thể bao gồm tham số lưu request hoặc context path tùy cấu hình). Test trực tiếp có thể xác nhận redirect:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.InsufficientAuthenticationException;
import org.springframework.security.web.authentication.LoginUrlAuthenticationEntryPoint;

import static org.assertj.core.api.Assertions.assertThat;

class LoginRedirectEntryPointTest {

    @Test
    void redirectsToLoginPage() throws Exception {
        LoginUrlAuthenticationEntryPoint entryPoint =
                new LoginUrlAuthenticationEntryPoint("/login");
        MockHttpServletRequest request = new MockHttpServletRequest();
        MockHttpServletResponse response = new MockHttpServletResponse();

        entryPoint.commence(
                request,
                response,
                new InsufficientAuthenticationException("Login required"));

        assertThat(response.getStatus()).isEqualTo(302);
        assertThat(response.getRedirectedUrl()).isEqualTo("/login");
    }
}
~~~

Không nên dùng redirect entry point cho mọi API JSON. Một client máy thường mong nhận `401` có cấu trúc ổn định, không phải trang HTML đăng nhập. Ứng dụng phục vụ cả browser và API có thể chọn entry point theo `RequestMatcher` hoặc loại nội dung request.

## 9. DelegatingAuthenticationEntryPoint và nhiều loại client

`DelegatingAuthenticationEntryPoint` cho phép chọn entry point theo `RequestMatcher`. Ví dụ, một ứng dụng có thể trả JSON cho `/api/**` và redirect cho trang web:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.authentication.DelegatingAuthenticationEntryPoint;
import org.springframework.security.web.authentication.LoginUrlAuthenticationEntryPoint;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

Map<RequestMatcher, AuthenticationEntryPoint> entryPoints =
        new LinkedHashMap<>();
entryPoints.put(
        new AntPathRequestMatcher("/api/**"),
        jsonAuthenticationEntryPoint);

DelegatingAuthenticationEntryPoint entryPoint =
        new DelegatingAuthenticationEntryPoint(entryPoints);
entryPoint.setDefaultEntryPoint(
        new LoginUrlAuthenticationEntryPoint("/login"));
~~~

Đoạn code minh họa việc chọn theo URL; các lớp matcher có thể khác theo phiên bản Spring Security. Trong test, cần kiểm tra ít nhất:

- URL `/api/profile` gọi JSON entry point.
- URL `/web/account` gọi redirect entry point mặc định.
- URL khớp nhiều matcher dùng entry point đầu tiên theo thứ tự đã cấu hình.

Nếu quyết định dựa trên `Accept` header, hãy kiểm tra các giá trị `application/json`, `text/html` và trường hợp không có header. Không dựa vào User-Agent làm căn cứ bảo mật.

## 10. Bearer token và phản hồi của resource server

Với OAuth2 Resource Server, `BearerTokenAuthenticationEntryPoint` tạo challenge Bearer theo giao thức. Những trường hợp phổ biến:

| Tình huống | Response thường gặp |
| --- | --- |
| Không có bearer token trên endpoint yêu cầu xác thực | `401` và `WWW-Authenticate: Bearer` |
| Token sai hoặc hết hạn | `401`, có thể có `error="invalid_token"` |
| Token hợp lệ nhưng thiếu scope | `403`, thường có challenge `insufficient_scope` |

Để kiểm thử resource server:

- Dùng `jwt()` trong `spring-security-test` để tạo `JwtAuthenticationToken` giả lập và kiểm tra phân quyền.
- Dùng token/decoder/validator phù hợp trong test tích hợp nếu cần xác minh chữ ký, issuer, audience, thời hạn hoặc entry point thực sự nhận lỗi từ bearer authentication.

`jwt()` bỏ qua việc giải mã và xác minh chữ ký JWT. Vì vậy test `jwt().authorities(...)` nhận `403` hay `200` chỉ chứng minh logic authorization với ngữ cảnh giả lập, không chứng minh `BearerTokenAuthenticationEntryPoint` hay `JwtDecoder` xử lý token thật.

## 11. Entry point trong Spring WebFlux

Ứng dụng Reactive dùng hợp đồng `ServerAuthenticationEntryPoint`, nhận `ServerWebExchange` và `AuthenticationException`, rồi trả `Mono<Void>`:

~~~java
public interface ServerAuthenticationEntryPoint {
    Mono<Void> commence(
            ServerWebExchange exchange,
            AuthenticationException ex);
}
~~~

Các triển khai thường gặp gồm:

- `HttpStatusServerEntryPoint`: trả status đã cấu hình.
- `RedirectServerAuthenticationEntryPoint`: chuyển hướng đến trang đăng nhập.
- Entry point tùy chỉnh: ghi response JSON qua `ServerHttpResponse`.

Ví dụ entry point JSON Reactive:

~~~java
import java.util.Map;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

final class JsonServerAuthenticationEntryPoint
        implements ServerAuthenticationEntryPoint {

    private final ObjectMapper objectMapper;

    JsonServerAuthenticationEntryPoint(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public Mono<Void> commence(
            ServerWebExchange exchange,
            AuthenticationException exception) {
        var response = exchange.getResponse();
        response.setStatusCode(HttpStatus.UNAUTHORIZED);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);

        byte[] body;
        try {
            body = objectMapper.writeValueAsBytes(Map.of(
                    "error", "unauthorized",
                    "message", "Authentication is required",
                    "path", exchange.getRequest().getPath().value()));
        } catch (JsonProcessingException ex) {
            return Mono.error(ex);
        }

        var buffer = response.bufferFactory().wrap(body);
        return response.writeWith(Mono.just(buffer));
    }
}
~~~

Đây là ví dụ tối giản; response Reactive chỉ được ghi một lần. Trong ứng dụng thực, cần xử lý trường hợp response đã được commit và thống nhất chính sách lỗi serialization.

### Kiểm thử WebTestClient

Khi ứng dụng WebFlux cấu hình `SecurityWebFilterChain` dùng entry point JSON và endpoint `/api/profile` yêu cầu xác thực, có thể kiểm thử:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveAuthenticationEntryPointTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void anonymousRequestGetsJson401() {
        webTestClient.get()
                .uri("/api/profile")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().contentTypeCompatibleWith("application/json")
                .expectBody()
                .jsonPath("$.error").isEqualTo("unauthorized");
    }
}
~~~

Test này cần chạy trong ứng dụng WebFlux thật có endpoint và cấu hình entry point tương ứng. Không ghép `MockMvc` với `SecurityFilterChain` Servlet vào test Reactive; hai stack có filter, request/response và entry point khác nhau.

## 12. Các lỗi thường gặp

**Dùng entry point để kiểm tra mật khẩu.** `AuthenticationEntryPoint` chỉ tạo phản hồi khi cần bắt đầu xác thực. Kiểm tra mật khẩu thuộc về provider/manager hoặc failure handler của cơ chế đăng nhập.

**Trả 403 cho mọi request anonymous.** Với tài nguyên yêu cầu đăng nhập, HTTP Basic thường dùng `401` để client biết cần xác thực. `403` phù hợp hơn với người đã xác thực nhưng thiếu quyền, dù cấu hình cụ thể có thể tùy chỉnh.

**Dùng redirect HTML cho API.** Client API thường không xử lý trang login. Hãy chọn entry point JSON hoặc challenge thích hợp cho `/api/**`.

**Bỏ sót WWW-Authenticate.** Với Basic/Bearer, test chỉ kiểm tra status `401` có thể bỏ qua challenge cần thiết cho client. Kiểm tra scheme và tham số cần thiết.

**Làm lộ authException trong response.** Không trả nguyên văn exception message hoặc stack trace. Dùng mã lỗi công khai ổn định và lưu chi tiết chẩn đoán ở log an toàn.

**Nhầm AuthenticationFailureHandler với AuthenticationEntryPoint.** Form login gửi password sai thường đi qua failure handler; anonymous truy cập tài nguyên được bảo vệ thường gọi entry point. Kiểm thử đúng điểm vào của luồng.

**Nhầm AccessDeniedHandler với entry point.** Người dùng đã xác thực nhưng thiếu quyền cần được xử lý bởi access denied handler. Nếu test nhận `403`, không kết luận entry point đã được gọi.

**Bỏ qua CSRF khi test POST.** `403` có thể xuất phát từ CSRF trước khi authorization chạy. Khi kiểm tra quyền, gửi CSRF hợp lệ; khi kiểm tra CSRF, cố ý bỏ token.

**Chỉ test trực tiếp commence(...).** Test component không chứng minh entry point đã được gắn vào đúng filter chain. Cần ít nhất một test HTTP cho request anonymous.

**Giả định Servlet và Reactive dùng chung interface.** `AuthenticationEntryPoint` dùng `HttpServletRequest/Response`; `ServerAuthenticationEntryPoint` dùng `ServerWebExchange` và `Mono<Void>`. Test cần dùng đúng stack.

## 13. Bài thực hành

1. Viết entry point JSON trả `401`, content type JSON và mã lỗi ổn định. Kiểm thử trực tiếp status, header và body; bảo đảm không đưa exception message nội bộ ra ngoài.
2. Cấu hình HTTP Basic dùng entry point đó. Dùng `MockMvc` kiểm tra request không credentials và password sai đều trả `401` theo hợp đồng API.
3. Thêm endpoint chỉ cho `ADMIN`. Dùng `@WithMockUser` với `ROLE_READER` để xác minh `403`; giải thích vì sao test này không đi qua entry point.
4. Tạo ứng dụng web có form login. Kiểm tra anonymous được redirect đến `/login`, còn form credentials sai được xử lý bởi `AuthenticationFailureHandler`.
5. Dùng `DelegatingAuthenticationEntryPoint` chọn JSON cho `/api/**` và redirect cho `/web/**`. Viết test chứng minh matcher chọn đúng entry point.
6. Với resource server, phân biệt test `jwt()` dùng để kiểm tra authorization và test decoder/entry point để kiểm tra token không hợp lệ.
7. Viết `ServerAuthenticationEntryPoint` Reactive trả JSON và dùng `WebTestClient` kiểm tra request anonymous.

Một bộ kiểm thử tốt xác minh được **ai tạo response, response có đúng giao thức và nội dung không, và filter chain có thực sự gọi entry point đã cấu hình hay không**. Tách biệt `401`, `403`, redirect và lỗi đăng nhập giúp ứng dụng phản hồi nhất quán cho browser, REST client và resource server.
