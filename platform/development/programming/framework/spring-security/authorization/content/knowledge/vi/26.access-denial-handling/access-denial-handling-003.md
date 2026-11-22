# AuthenticationEntryPoint với người chưa xác thực trong Spring Security

Trong một ứng dụng được bảo vệ bởi Spring Security, request vào tài nguyên yêu cầu đăng nhập có thể đến khi người dùng chưa cung cấp thông tin xác thực, phiên đăng nhập đã hết hạn hoặc token không hợp lệ. `AuthenticationEntryPoint` quyết định **cách bắt đầu quy trình xác thực hoặc cách báo cho client rằng cần xác thực**. Nó là một phần của cơ chế xử lý từ chối ở tầng HTTP, đặc biệt hữu ích khi phân biệt người **chưa xác thực** với người **đã xác thực nhưng thiếu quyền**.

Bài này tập trung vào **Spring Security Servlet** (`HttpSecurity`, `SecurityFilterChain`, `jakarta.servlet`). Ứng dụng WebFlux dùng giao diện khác là `ServerAuthenticationEntryPoint`.

## 1. Vai trò và ranh giới

`org.springframework.security.web.AuthenticationEntryPoint` có một phương thức chính:

```java
void commence(HttpServletRequest request,
              HttpServletResponse response,
              AuthenticationException authException)
        throws IOException, ServletException;
```

- `request`: HTTP request cần được yêu cầu xác thực.
- `response`: HTTP response để gửi status, header hoặc redirect tới client.
- `authException`: ngoại lệ xác thực đã dẫn tới việc kích hoạt entry point; không nên đưa thông điệp nội bộ của ngoại lệ trực tiếp ra client.
- `commence(...)` **không kiểm tra mật khẩu, không giải mã JWT, không cấp quyền**. Các bước đó thuộc authentication filter, `AuthenticationManager`/`AuthenticationProvider` hoặc cơ chế xác thực tương ứng.
- Entry point có thể trả `401 Unauthorized` kèm `WWW-Authenticate`, chuyển hướng `302` đến trang login, hoặc thực hiện phản hồi phù hợp khác. **Không có quy tắc mọi `AuthenticationEntryPoint` đều trả 401.**

Hãy phân biệt ba thành phần:

| Thành phần | Trách nhiệm |
| --- | --- |
| `AuthorizationFilter` / quy tắc `authorizeHttpRequests` | Xác định request hiện tại có đủ quyền truy cập hay không; có thể từ chối bằng `AccessDeniedException`. |
| `ExceptionTranslationFilter` | Chuyển một số lỗi xác thực/phân quyền phát sinh bên trong phần filter chain mà nó bao quanh thành hành vi HTTP thích hợp. |
| `AuthenticationEntryPoint` | Bắt đầu xác thực hoặc trả phản hồi yêu cầu client xác thực. |
| `AccessDeniedHandler` | Xử lý trường hợp quyền truy cập bị từ chối đối với chủ thể đã được coi là xác thực, thường trả `403 Forbidden`. |

## 2. Khi nào `AuthenticationEntryPoint` được gọi?

Luồng điển hình khi request chưa xác thực truy cập `/api/report` đã cấu hình `.authenticated()`:

1. Request qua các authentication filter. Nếu không có credential hợp lệ, chưa có người dùng đăng nhập thực sự; cơ chế anonymous có thể đặt `AnonymousAuthenticationToken` vào `SecurityContext`.
2. Kiểm tra phân quyền kết luận request không được phép truy cập và ném `AccessDeniedException`.
3. `ExceptionTranslationFilter` dùng thông tin về trạng thái xác thực (thông qua `AuthenticationTrustResolver`) để xác định cần yêu cầu đăng nhập. Với chủ thể anonymous, nó kích hoạt `AuthenticationEntryPoint` thay vì mặc định trả 403.
4. Entry point tạo phản hồi phù hợp với cơ chế xác thực: ví dụ `401` cho REST API dùng Basic/Bearer, hoặc redirect đến trang login cho giao diện web.
5. Client gửi lại credential; bộ lọc xác thực sẽ xử lý credential ở request tiếp theo. Khi đã xác thực, quyết định phân quyền được đánh giá lại.

Cùng `ExceptionTranslationFilter` còn có thể gọi entry point khi nó bắt được `AuthenticationException`. Riêng một số authentication filter (chẳng hạn `BasicAuthenticationFilter`) có thể tự gọi entry point khi xác thực thất bại, nên không được hiểu rằng **mọi** lời gọi entry point đều đi qua `ExceptionTranslationFilter`.

Phân biệt các tình huống:

| Request | Kết quả điển hình |
| --- | --- |
| Chưa đăng nhập, truy cập endpoint yêu cầu `.authenticated()` | Kích hoạt `AuthenticationEntryPoint`; API thường trả 401, ứng dụng form login thường redirect. |
| Đã đăng nhập là `READER`, truy cập endpoint yêu cầu `ADMIN` | Kích hoạt `AccessDeniedHandler`, thường là 403. |
| Gửi sai username/password qua HTTP Basic | Authentication filter xử lý thất bại và dùng entry point phù hợp, thường 401 kèm HTTP Basic challenge. |
| Bearer token hết hạn hoặc sai chữ ký | Cơ chế resource server từ chối xác thực; phản hồi thường là 401 với thông tin Bearer tương ứng. |
| POST thiếu CSRF token | Có thể là 403 do bảo vệ CSRF; không thể chỉ nhìn mã trạng thái mà kết luận thiếu quyền hay chưa đăng nhập. |

**Lưu ý:** `AnonymousAuthenticationToken` có thể có `isAuthenticated() == true` theo ý nghĩa nội bộ của token. Không dùng riêng cờ này để kết luận người dùng đã đăng nhập. Spring Security có cơ chế phân biệt anonymous và authenticated/remember-me thích hợp.

## 3. Chọn kiểu entry point theo giao thức

- **HTTP Basic:** `BasicAuthenticationEntryPoint` trả 401 cùng `WWW-Authenticate: Basic realm="..."` để client hiểu cơ chế cần dùng. Header challenge quan trọng đối với hành vi của browser và client Basic.
- **OAuth2 Resource Server:** `BearerTokenAuthenticationEntryPoint` tuân theo cơ chế Bearer, có thể gửi `WWW-Authenticate: Bearer ...` cùng thông tin lỗi hợp lệ. Không tùy tiện thay nó bằng phản hồi JSON chung nếu việc thay thế làm mất các header được giao thức yêu cầu.
- **Form login:** `LoginUrlAuthenticationEntryPoint` chuyển hướng đến đường dẫn login; response thường là 302. Trang login phải được cho phép truy cập để tránh vòng lặp redirect.
- **API cần status cố định:** `HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)` là lựa chọn gọn khi chỉ cần trả mã trạng thái.
- **Tùy biến:** tự triển khai interface hoặc dùng lambda để tạo mã lỗi JSON, header và status thống nhất với API contract.

Đừng đồng nhất `AuthenticationEntryPoint` với trang login: entry point chỉ quyết định **cách bắt đầu xác thực**. Nó cũng không thay thế `AuthenticationFailureHandler` chuyên xử lý một lần submit form login thất bại.

## 4. Ví dụ Java 17+ với HTTP Basic và JSON 401

Ví dụ sau chạy trong **một dự án Spring Boot 3.x dùng Servlet/MVC**, có các starter `spring-boot-starter-web`, `spring-boot-starter-security` và (để chạy phần test) `spring-boot-starter-test`, `spring-security-test`. Đây là ví dụ API học tập: người dùng `reader` có role `READER`; `/api/report` cần đăng nhập, còn `/api/admin` cần role `ADMIN`. Tất cả request thử nghiệm là GET nên không cần tắt CSRF.

Tạo `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Tạo `src/main/java/com/example/demo/ApiSecurityConfig.java`:

```java
package com.example.demo;

import java.nio.charset.StandardCharsets;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    AuthenticationEntryPoint apiAuthenticationEntryPoint() {
        return (request, response, authException) -> {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setHeader(HttpHeaders.WWW_AUTHENTICATE,
                    "Basic realm=\"demo-api\"");
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.getWriter().write(
                    "{\"error\":\"authentication_required\"}");
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationEntryPoint apiAuthenticationEntryPoint)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().permitAll())
            .exceptionHandling(exceptions -> exceptions
                .authenticationEntryPoint(apiAuthenticationEntryPoint))
            .httpBasic(basic -> basic
                .authenticationEntryPoint(apiAuthenticationEntryPoint));

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("demo-pass"))
                .roles("READER")
                .build();
        return new InMemoryUserDetailsManager(reader);
    }
}
```

Tạo `src/main/java/com/example/demo/DemoController.java`:

```java
package com.example.demo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/api/report")
    public String report(Authentication authentication) {
        return "report for " + authentication.getName();
    }

    @GetMapping("/api/admin")
    public String admin() {
        return "admin";
    }
}
```

Điểm đáng chú ý của cấu hình:

1. `authorizeHttpRequests` quy định quyền. Thứ tự matcher quan trọng: `/api/admin` có yêu cầu `ADMIN` phải đứng trước `/api/**`.
2. `exceptionHandling(...authenticationEntryPoint(...))` thiết lập điểm bắt đầu xác thực khi việc kiểm tra quyền trong filter chain yêu cầu đăng nhập.
3. `httpBasic(...authenticationEntryPoint(...))` giúp cả trường hợp HTTP Basic sai credential dùng chung phản hồi đã định nghĩa. Nếu chỉ tùy biến `exceptionHandling`, có thể không bao phủ đường xử lý lỗi riêng của Basic filter.
4. Header `WWW-Authenticate: Basic realm="demo-api"` được giữ lại vì ví dụ **chủ động sử dụng HTTP Basic**. Với JWT/Bearer cần dùng challenge tương ứng thay vì sao chép header Basic.
5. `BCryptPasswordEncoder` được dùng cho ví dụ xác thực. Tài khoản và mật khẩu trong mã chỉ dành cho môi trường thử nghiệm; ứng dụng thực tế cần quản lý thông tin xác thực an toàn.

Chạy ứng dụng bằng `./gradlew bootRun` (hoặc `gradlew.bat bootRun` trên Windows) nếu dự án sử dụng Gradle. Khi chạy ở cổng mặc định 8080, thử:

```bash
curl -i http://localhost:8080/api/report
curl -i -u reader:demo-pass http://localhost:8080/api/report
curl -i -u reader:demo-pass http://localhost:8080/api/admin
curl -i http://localhost:8080/public
```

Các kết quả chính (lược bỏ header không liên quan):

```http
GET /api/report
HTTP/1.1 401
WWW-Authenticate: Basic realm="demo-api"
Content-Type: application/json;charset=UTF-8

{"error":"authentication_required"}
```

```http
GET /api/report
Authorization: Basic <credentials hợp lệ>
HTTP/1.1 200

report for reader
```

```http
GET /api/admin
Authorization: Basic <credentials của reader>
HTTP/1.1 403
```

```http
GET /public
HTTP/1.1 200

public
```

Ví dụ phân biệt rõ: thiếu credential ở `/api/report` gây **401 do entry point**; có credential hợp lệ nhưng thiếu role tại `/api/admin` gây **403 do phân quyền**. Các dòng HTTP ở trên là minh họa kết quả cần quan sát; thứ tự và tập header thực tế có thể khác theo server/cấu hình.

## 5. Khi nào chỉ cần cấu hình có sẵn?

Nếu muốn login form chuẩn:

```java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/login", "/assets/**").permitAll()
        .anyRequest().authenticated())
    .formLogin(form -> form
        .loginPage("/login")
        .permitAll());
```

Đây là **đoạn cấu hình bên trong một `SecurityFilterChain` hiện có**, không phải chương trình Java độc lập. Cần tự triển khai `GET /login` khi dùng trang login tùy chỉnh. Client browser chưa đăng nhập thường nhận redirect đến `/login`; không nên buộc luồng HTML trả JSON 401 nếu sản phẩm muốn chuyển hướng người dùng.

Nếu chỉ cần trả status cho API, có thể dùng:

```java
http.exceptionHandling(ex -> ex.authenticationEntryPoint(
        new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)));
```

Hai đoạn trên là các **lựa chọn thay thế** cho hành vi entry point; cần import `org.springframework.security.web.authentication.HttpStatusEntryPoint` và `org.springframework.http.HttpStatus` cho đoạn thứ hai. Nếu sử dụng HTTP Basic/Bearer, phải cân nhắc giữ đúng `WWW-Authenticate` theo giao thức; `HttpStatusEntryPoint` chỉ đặt status.

Khi ứng dụng có cả trang HTML và API, có thể dùng nhiều `SecurityFilterChain` với `securityMatcher(...)` và entry point riêng cho từng nhóm request, hoặc chọn entry point theo `RequestMatcher`. Tránh áp một redirect HTML cho mọi `/api/**`, khiến client REST nhận trang login thay cho lỗi xác thực mà nó có thể xử lý.

## 6. Kiểm thử đúng hành vi từ chối

Với `spring-security-test`, `spring-boot-starter-test` và ví dụ ở mục 4, tạo `src/test/java/com/example/demo/AuthenticationEntryPointTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthenticationEntryPointTest {

    @Autowired
    MockMvc mvc;

    @Test
    void noCredentialsUsesEntryPoint() throws Exception {
        mvc.perform(get("/api/report"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                "Basic realm=\"demo-api\""))
            .andExpect(jsonPath("$.error")
                .value("authentication_required"));
    }

    @Test
    void validCredentialsCanAccessProtectedResource() throws Exception {
        mvc.perform(get("/api/report")
                .with(httpBasic("reader", "demo-pass")))
            .andExpect(status().isOk());
    }

    @Test
    void authenticatedUserWithoutAdminRoleGets403() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("reader", "demo-pass")))
            .andExpect(status().isForbidden());
    }
}
```

Chạy `./gradlew test` hoặc `gradlew.bat test` tùy hệ điều hành. Bộ test cần ba kết quả độc lập: **401 + challenge + JSON** khi chưa xác thực, **200** khi credential hợp lệ và đủ quyền, **403** khi đã xác thực nhưng thiếu role. Với app Bearer, test cần xác minh `WWW-Authenticate` theo Bearer và cả token hết hạn/không hợp lệ.

## 7. Lỗi thường gặp và cách chẩn đoán

- **Trả 403 cho mọi request chưa đăng nhập:** kiểm tra entry point, anonymous authentication, vị trí/cấu hình filter và matcher; không tự viết logic `isAuthenticated()` dựa trên `AnonymousAuthenticationToken`.
- **Nhầm 401 và 403:** lỗi xuất phát từ `AccessDeniedException` không có nghĩa response luôn 403. `ExceptionTranslationFilter` còn xét người dùng đã thực sự xác thực hay chưa.
- **Ghi đè entry point của Resource Server:** có thể làm mất `WWW-Authenticate: Bearer` và thông tin `invalid_token` chuẩn giao thức. Chỉ thay khi đã xác định đầy đủ yêu cầu client và OAuth2.
- **Custom Basic 401 nhưng thiếu `WWW-Authenticate`:** một số client/browser không biết cần thực hiện Basic challenge.
- **Redirect `/login` lặp vô hạn:** cần cho phép người chưa đăng nhập truy cập chính trang login và những tài nguyên tĩnh nó cần.
- **Bắt lỗi bằng `@ControllerAdvice` nhưng không xử lý được:** nhiều lỗi bảo mật phát sinh ở servlet filter **trước** controller; xử lý ở đúng tầng bằng `AuthenticationEntryPoint`/`AccessDeniedHandler`.
- **Đưa `authException.getMessage()` vào JSON trả về:** có thể tiết lộ cấu hình hoặc chi tiết xác thực. Hãy trả mã lỗi ổn định, ghi log nội bộ an toàn và dùng request ID nếu cần tra cứu.
- **Thấy 403 rồi tắt CSRF:** 403 cũng có thể do thiếu CSRF token. Kiểm tra loại request, logging và cấu hình CSRF trước khi thay đổi chính sách bảo mật.
- **Response đã được ghi xong:** không thể bắt đầu redirect hoặc viết body 401 đáng tin cậy sau khi response đã committed. Cấu hình filter và xử lý lỗi phải diễn ra trước thời điểm đó.

Khi debug, bật log Spring Security ở mức `DEBUG` hoặc `TRACE` trong môi trường phát triển, quan sát thứ tự security filter, endpoint matcher, trạng thái Authentication và response header. Không bật log chi tiết credential/token ở môi trường production.

## 8. Tự kiểm tra kiến thức

1. Một request chưa login truy cập `/api/admin` yêu cầu role `ADMIN`: vì sao có thể là 401 thay vì 403? — Vì chưa xác thực, `ExceptionTranslationFilter` có thể chuyển lỗi từ chối quyền thành hành động bắt đầu xác thực qua entry point.
2. Người dùng `READER` đã login gọi cùng endpoint: thành phần nào thường phản hồi? — `AccessDeniedHandler`, thông thường trả 403.
3. Tại sao `AuthenticationEntryPoint` có thể trả 302? — Vì với form login, hành động bắt đầu xác thực có thể là redirect đến trang đăng nhập.
4. Vì sao không sao chép JSON 401 + Basic header cho API JWT? — Client Bearer cần challenge và thông tin lỗi theo chuẩn Bearer, có thể được `BearerTokenAuthenticationEntryPoint` xử lý.
5. Khi nào nên kiểm tra cả `httpBasic` và `exceptionHandling`? — Khi muốn phản hồi nhất quán cho request chưa xác thực do kiểm tra quyền và cho lần gửi HTTP Basic credential không hợp lệ.

## Tài liệu chính thức

- [AuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/AuthenticationEntryPoint.html)
- [ExceptionTranslationFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/access/ExceptionTranslationFilter.html)
- [Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Anonymous Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/anonymous.html)
- [HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html)
- [OAuth2 Resource Server Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html)