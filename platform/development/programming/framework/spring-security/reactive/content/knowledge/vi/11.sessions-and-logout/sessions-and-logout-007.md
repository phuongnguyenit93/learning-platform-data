# Cấu hình logout, địa chỉ đăng xuất và phương thức HTTP

## Mục tiêu

Bài học thuộc nhóm **Phiên và đăng xuất** trong **Spring Security reactive / Spring WebFlux**. Sau bài này, bạn có thể:

- Phân biệt logout trên một HTTP session với việc chuyển trang, xóa cookie ở browser hoặc thu hồi bearer token.
- Giải thích vai trò của `LogoutWebFilter`, `ServerWebExchangeMatcher`, `ServerLogoutHandler` và `ServerLogoutSuccessHandler`.
- Cấu hình địa chỉ đăng xuất bằng `ServerHttpSecurity.logout(...).logoutUrl(...)` mà vẫn giữ **POST** làm phương thức logout.
- Dùng `requiresLogout(...)` khi cần kiểm soát rõ URL **và** HTTP method.
- Hiểu tại sao **POST với CSRF token** là cách thông thường để logout khỏi một ứng dụng dùng cookie/session; tại sao dùng **GET logout** không được khuyến nghị.
- Viết một ví dụ Java 17+ chạy trên WebFlux, đăng nhập form qua `WebSession`, gọi logout ở URL tùy chỉnh, và kiểm thử status, phương thức, CSRF cùng việc không còn Authentication sau logout.

> Chỉ dùng các API reactive như `ServerHttpSecurity`, `SecurityWebFilterChain`, `ServerWebExchange`. Đừng nhầm với `HttpSecurity`, `LogoutFilter`, `HttpSession` và `LogoutHandler` của stack Servlet; cú pháp và các handler khác nhau.

## 1. Logout thật sự làm thay đổi điều gì?

Với form login dùng session, server có thể lưu `SecurityContext` chứa `Authentication` trong `WebSession`. Client thường mang session ID qua cookie. Nếu logout hợp lệ, request tiếp theo với cookie đó không được khôi phục thành người dùng đã đăng nhập.

~~~text
Đăng nhập qua POST /login
    |
    +-- Authentication hợp lệ
    +-- SecurityContext được lưu trong WebSession
    +-- Browser giữ session cookie
    |
    v
GET /api/me -> đã xác thực
    |
    v
POST /account/logout + cookie + CSRF hợp lệ
    |
    v
LogoutWebFilter
    |
    +-- ServerLogoutHandler: xóa SecurityContext,
    |                        có thể invalidate WebSession
    |
    +-- ServerLogoutSuccessHandler: redirect hoặc trả 204
    |
    v
GET /api/me với cookie cũ -> không còn authenticated
~~~

Cần tách rõ các hành động:

| Hành động | Ý nghĩa | Có tương đương logout đầy đủ không? |
|---|---|---|
| Trả 200/204 và thông báo “Đăng xuất thành công” | Phản hồi HTTP cho client | Không, nếu chưa xóa phiên/context. |
| Redirect tới `/login` | Chuyển giao diện | Không tự xóa dữ liệu phía server. |
| Xóa `SecurityContext` trong repository | Request sau không load context từ repository đó | Có ích, nhưng có thể còn WebSession/app state. |
| Invalidate `WebSession` | Phiên hiện tại không còn hiệu lực | Thường cần với ứng dụng session-based. |
| Xóa cookie session trên client | Không gửi ID cũ nữa | Không thay thế invalidate server-side. |
| Thu hồi JWT/refresh token | Vô hiệu hóa credential theo token policy | Không tự được thực hiện chỉ vì dọn WebSession. |

Một logout handler dùng đúng repository mới có thể xóa SecurityContext đã lưu. Nếu bạn chỉ xóa context khỏi Reactor Context của request hiện tại, nhưng repository vẫn giữ bản lưu trong WebSession, request sau có thể lấy lại Authentication. Ngược lại, một session đã invalidate ở server không thể được “khôi phục” chỉ bằng cách gửi lại cùng cookie cũ.

## 2. Những thành phần logout của Spring Security WebFlux

### 2.1. LogoutWebFilter

`LogoutWebFilter` nhận một `ServerWebExchange`, dùng `ServerWebExchangeMatcher` để quyết định request hiện tại có phải logout hay không. Nếu matcher không khớp, request đi tiếp trong chuỗi filter/handler bình thường. Nếu khớp, filter chạy các logout handler rồi success handler theo pipeline reactive; không cần một controller `@PostMapping` trùng URL.

~~~text
Request -> SecurityWebFilterChain
                   |
                   v
             LogoutWebFilter
                   |
       +-----------+-----------+
       |                       |
   Matcher không khớp      Matcher khớp
       |                       |
   filter tiếp theo       ServerLogoutHandler
                               |
                               v
                         ServerLogoutSuccessHandler
                               |
                               v
                       HTTP status / redirect
~~~

Đây là sơ đồ chức năng; trong thực tế CSRF filter có thể từ chối POST thiếu token **trước** khi logout handler chạy. Thứ tự cụ thể phụ thuộc cấu hình và phiên bản Spring Security.

### 2.2. ServerLogoutHandler

Interface handler trả `Mono<Void>`, dùng cho thao tác dọn dữ liệu xác thực. Những class phổ biến trong package `org.springframework.security.web.server.authentication.logout`:

- `SecurityContextServerLogoutHandler`: xóa SecurityContext thông qua `ServerSecurityContextRepository`.
- `WebSessionServerLogoutHandler`: invalidate active `WebSession`.
- `DelegatingServerLogoutHandler`: kết hợp các logout handler để dọn nhiều phạm vi cùng lúc.

Tài liệu Spring Security reactive nhấn mạnh: mặc định logout xử lý xóa context/CSRF theo cấu hình, nhưng nếu bạn muốn **invalidate toàn bộ WebSession**, hãy cấu hình thêm `WebSessionServerLogoutHandler`. Không mượn hành vi mặc định của Servlet để kết luận WebFlux sẽ tự invalidate toàn bộ session trong mọi tình huống.

Một cách kết hợp:

~~~java
ServerLogoutHandler cleanup =
    new DelegatingServerLogoutHandler(
        new SecurityContextServerLogoutHandler(),
        new WebSessionServerLogoutHandler());
~~~

Đây là đoạn trong class cấu hình, cần import các class reactive tương ứng. Nếu tự gọi setter `logoutHandler(...)`, hãy chủ động giữ đủ logic mặc định cần thiết; đừng mặc định các handler cũ vẫn được ghép sau khi thay thế.

### 2.3. ServerLogoutSuccessHandler

Success handler chạy sau logout handler; nó quyết định cách client nhận kết quả:

- `RedirectServerLogoutSuccessHandler`: chuyển hướng về trang đăng nhập hoặc trang công khai.
- `HttpStatusReturningServerLogoutSuccessHandler`: trả HTTP 200 mặc định hoặc mã status tùy chọn, ví dụ 204 No Content, thường thuận tiện cho API.

**Success handler không phải cleanup handler.** Trả 204 không chứng minh session đã bị hủy nếu logic dọn chưa chạy. Kiểm thử đúng luôn gồm một request tiếp theo dùng credential/cookie cũ.

## 3. Hành vi mặc định: GET /logout và POST /logout

Với WebFlux security hỗ trợ logout, tài liệu Spring Security 6.5 mô tả hai hành vi mặc định:

1. **GET /logout**: có thể hiển thị trang xác nhận đăng xuất do framework cung cấp. Đây là thao tác **xem trang xác nhận**, không phải lời cam kết rằng GET sẽ xóa session.
2. **POST /logout**: là request **thực hiện logout**, với các điều kiện của CSRF/matcher và handler. Sau khi thành công, response mặc định có thể redirect về login, ví dụ `/login?logout`.

Hành vi GET chính xác còn tùy trang xác nhận/default login page được bật và custom configuration. Nếu đã đổi URL hoặc tự tạo controller, đừng kỳ vọng mọi GET `/logout` đều vẫn có trang xác nhận.

**Điểm cốt lõi:** Trong DSL WebFlux, `logoutUrl(String)` mô tả **URL mà HTTP POST tới đó sẽ kích hoạt logout**. Chỉ thay chuỗi URL không thay sang GET.

## 4. Cấu hình địa chỉ đăng xuất

### 4.1. Đổi logout URL nhưng giữ POST (khuyến nghị)

~~~java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated())
        .logout(logout -> logout.logoutUrl("/account/logout"))
        .build();
}
~~~

Đoạn này là method cấu hình, cần import `@Bean`, `ServerHttpSecurity`, `SecurityWebFilterChain`. Nó giữ trigger logout ở **POST /account/logout**. Không suy luận rằng GET cùng URL sẽ logout.

| HTTP request | Có khớp logout matcher của ví dụ? | Giải thích |
|---|---|---|
| `POST /account/logout` | Có | Cần vượt qua CSRF filter khi CSRF bật. |
| `GET /account/logout` | Không | Có thể do controller/trang khác xử lý hoặc trả 404/redirect. |
| `POST /logout` | Không | URL mặc định không còn là trigger của matcher mới. |
| `DELETE /account/logout` | Không | Không tự kích hoạt logout dù cùng path. |

Nếu GET không khớp logout matcher, nó **không đồng nghĩa** chắc chắn 405. Tùy router, authorization và exception handler, request có thể trở thành 200, 302, 401, 404, 405, v.v. Muốn biết có logout thật hay không, phải kiểm tra Authentication/session ở request tiếp theo.

### 4.2. Cấu hình matcher tường minh

`requiresLogout(...)` dùng khi muốn custom điều kiện match. Ví dụ tương đương POST + path:

~~~java
http.logout(logout -> logout.requiresLogout(
    new PathPatternParserServerWebExchangeMatcher(
        "/account/logout", HttpMethod.POST)));
~~~

Đây là mảnh cấu hình Java cần import `org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher` và `org.springframework.http.HttpMethod`. Với một POST URL đơn giản, `logoutUrl(...)` ngắn hơn và ít khả năng cấu hình sai.

**Cẩn thận khi bỏ giới hạn HTTP method:**

~~~java
// Không khuyến nghị cho website dùng browser cookie.
http.logout(logout -> logout.requiresLogout(
    new PathPatternParserServerWebExchangeMatcher("/account/logout")));
~~~

Matcher chỉ phụ thuộc path nên có thể khớp cả GET. Spring Security có ví dụ cho thấy điều này khả thi nhưng cảnh báo rủi ro. Đây là một **thay đổi an ninh**, không chỉ là cách viết URL ngắn.

### 4.3. Phân biệt các matcher

| Cấu hình | Chức năng |
|---|---|
| `logoutUrl(...)` | Chọn POST URL kích hoạt LogoutWebFilter. |
| `requiresLogout(...)` | Chọn matcher tùy chỉnh, gồm method nếu cần. |
| `securityMatcher(...)` | Chọn `SecurityWebFilterChain` nào bao phủ request. |
| `authorizeExchange().pathMatchers(...).permitAll()` | Đặt rule authorization; không tự tạo logout endpoint hay đổi method. |
| `logoutSuccessHandler(...)` | Đặt response sau khi cleanup hoàn thành; không đổi request URL. |

Với nhiều bean `SecurityWebFilterChain`, URL logout phải đi qua đúng chain có cấu hình `LogoutWebFilter`. Một `/account/logout` nằm ngoài tất cả chain có thể không được logout handler nào xử lý.

## 5. Vì sao dùng POST và CSRF thay vì GET?

HTTP GET là phương thức có ngữ nghĩa **đọc**. Nó có thể bị kích hoạt bởi click link, trang bên ngoài, preview bot, crawler, prefetch hoặc điều hướng browser. Logout thay đổi trạng thái phiên và có thể phá một workflow đang mở, nên không nên kích hoạt trực tiếp bằng GET.

Một kịch bản logout CSRF:

1. Người dùng đã đăng nhập vào một ứng dụng bằng session cookie.
2. Bên ngoài gửi đường dẫn `https://app.example.test/logout` để browser truy cập.
3. Nếu GET tự logout, trình duyệt có thể đính kèm cookie và người dùng bị đăng xuất trái ý muốn.

Với **POST + CSRF token**, browser cần cung cấp một giá trị khó đoán mà attacker không đơn giản biết được từ một website khác. Cookie `SameSite` có thể hỗ trợ giảm rủi ro, nhưng không thay thế việc thiết kế phương thức, token và origin policy đúng cho ứng dụng.

### 5.1. CSRF filter làm gì?

Theo mặc định, Spring Security WebFlux bảo vệ các request có khả năng thay đổi trạng thái, bao gồm POST. Request thiếu/sai CSRF token thường nhận **403 Forbidden**. Một POST logout bị CSRF từ chối **không nên chạy logout handler**.

~~~text
POST /account/logout
    |
    v
CsrfWebFilter
    | thiếu / sai token ----> HTTP 403; không logout
    |
    | token hợp lệ
    v
LogoutWebFilter
    |
    v
ServerLogoutHandler
    |
    v
ServerLogoutSuccessHandler
~~~

**Đừng tắt CSRF trên toàn ứng dụng chỉ vì POST /logout trả 403.** Hãy cung cấp token hợp lệ qua form hidden input hoặc header theo Spring Security configuration. Với API bearer token không dựa vào browser tự gửi cookie, threat model CSRF có thể khác và cần được đánh giá riêng.

### 5.2. Cách đưa token vào request

Trong WebFlux, CSRF token mặc định được lưu trong `WebSession` bởi `WebSessionServerCsrfTokenRepository`. Spring Security có thể cấp token cho view dưới dạng `Mono<CsrfToken>` gắn vào `ServerWebExchange`. Từ Spring Security 6, mặc định `XorServerCsrfTokenRequestAttributeHandler` giúp giảm nguy cơ BREACH.

Một form logout điển hình:

~~~html
<form method="post" action="/account/logout">
  <input type="hidden" name="_csrf" value="CSRF_TOKEN_FROM_SERVER">
  <button type="submit">Đăng xuất</button>
</form>
~~~

Đoạn HTML là **mẫu cấu trúc view**; giá trị hidden input phải được server render thành token thực của request, không hardcode chuỗi minh họa. Nếu dùng template integration của Spring Security, tận dụng hỗ trợ CSRF token của framework thay vì tạo token tự chế. Không đưa token vào URL, log hay analytics.

### 5.3. Khi nào GET /logout có ích?

GET có thể hiển thị **trang xác nhận** với form POST. Trên trang đó, người dùng click nút logout, gửi POST với CSRF token. Đây là cách phân chia rõ: GET đọc giao diện; POST thay đổi session. Nếu chỉ muốn nút giống link, dùng một form POST được style như link, không đổi method của logout thành GET.

## 6. Chọn handler dọn dẹp và response cho API

Khi logout khỏi ứng dụng session-based, một cấu hình rõ ràng là:

~~~java
var cleanup = new DelegatingServerLogoutHandler(
    new SecurityContextServerLogoutHandler(),
    new WebSessionServerLogoutHandler());

http.logout(logout -> logout
    .logoutUrl("/account/logout")
    .logoutHandler(cleanup)
    .logoutSuccessHandler(
        new HttpStatusReturningServerLogoutSuccessHandler(
            HttpStatus.NO_CONTENT)));
~~~

Đây là mảnh code trong class cấu hình; import các class reactive và `HttpStatus`. Nó cho thấy ba quyết định độc lập:

1. **Khi nào logout:** POST tới `/account/logout`.
2. **Xóa gì:** SecurityContext đã lưu và WebSession đang hoạt động.
3. **Phản hồi thế nào:** trả HTTP **204 No Content**, không redirect.

Trong ứng dụng web điều hướng, thay success handler bằng `RedirectServerLogoutSuccessHandler` và đặt URL đích nếu muốn. Đừng nhầm logout success URL (đường dẫn sau khi logout) với logout request URL.

Đừng tự ghi cookie session bị xóa rồi xem đó là toàn bộ security. Invalidate WebSession phía server mới đảm bảo session ID cũ không còn sử dụng được để nạp context. Khi một ứng dụng có cả dữ liệu session phi xác thực, cân nhắc ảnh hưởng của invalidate đối với các phần còn lại.

## 7. Bài thực hành Java 17 chạy độc lập

Ví dụ dùng **Java 17**, **Spring Boot 3.5.16**, Spring WebFlux và Spring Security theo dependency management của Boot. Boot 3.5.16 đã được phát hành; production nên dùng dòng framework còn được hỗ trợ và đã cập nhật bảo mật thay vì coi demo là cấu hình triển khai lâu dài.

**Mục tiêu của demo:**

- Đăng nhập qua form mặc định bằng user `learner`.
- `GET /csrf` hiển thị token CSRF để thử request cục bộ.
- `GET /api/me` trả username từ principal nếu đã đăng nhập.
- `GET /account/logout` chỉ hiển thị thông tin, không logout.
- `POST /account/logout` mới trigger LogoutWebFilter; token sai thì 403, token hợp lệ thì 204.
- Sau POST logout thành công, session ID cũ không được tiếp tục truy cập `/api/me`.

### 7.1. Cấu trúc project và Gradle

~~~text
webflux-logout-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/WebfluxLogoutDemo.java
    └── test/java/example/LogoutMethodTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-logout-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Dùng Gradle tương thích với Spring Boot 3.5 và JDK 17+. Nếu đã có Gradle Wrapper, ưu tiên chạy wrapper để người học có kết quả nhất quán.

### 7.2. Ứng dụng hoàn chỉnh

Tệp `src/main/java/example/WebfluxLogoutDemo.java`:

~~~java
package example;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.logout.DelegatingServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.HttpStatusReturningServerLogoutSuccessHandler;
import org.springframework.security.web.server.authentication.logout.SecurityContextServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.WebSessionServerLogoutHandler;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class WebfluxLogoutDemo {

    public static void main(String[] args) {
        SpringApplication.run(WebfluxLogoutDemo.class, args);
    }

    @Bean
    MapReactiveUserDetailsService users() {
        // Chỉ dùng local demo, không dùng password {noop} ở production.
        UserDetails user = User.withUsername("learner")
            .password("{noop}demo-pass")
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(user);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        var cleanup = new DelegatingServerLogoutHandler(
            new SecurityContextServerLogoutHandler(),
            new WebSessionServerLogoutHandler());

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/login", "/csrf").permitAll()
                .anyExchange().authenticated())
            .formLogin(Customizer.withDefaults())
            // Không tắt CSRF: giữ bảo vệ mặc định.
            .logout(logout -> logout
                .logoutUrl("/account/logout")
                .logoutHandler(cleanup)
                .logoutSuccessHandler(
                    new HttpStatusReturningServerLogoutSuccessHandler(
                        HttpStatus.NO_CONTENT)))
            .build();
    }

    @RestController
    static class ApiController {

        @GetMapping("/csrf")
        Mono<Map<String, String>> csrf(ServerWebExchange exchange) {
            // CsrfWebFilter đặt Mono<CsrfToken> vào exchange attribute.
            Mono<CsrfToken> source =
                exchange.getAttribute(CsrfToken.class.getName());

            if (source == null) {
                return Mono.error(new IllegalStateException(
                    "CSRF attribute unavailable"));
            }

            return source.map(token -> Map.of(
                "headerName", token.getHeaderName(),
                "parameterName", token.getParameterName(),
                "token", token.getToken()));
        }

        @GetMapping("/api/me")
        Mono<Map<String, String>> me(ServerWebExchange exchange) {
            return exchange.getPrincipal()
                .map(principal -> Map.of(
                    "username", principal.getName()));
        }

        // GET này KHÔNG logout. POST cùng URL do LogoutWebFilter bắt.
        @GetMapping("/account/logout")
        Mono<Map<String, String>> logoutInfo(
            ServerWebExchange exchange) {

            return exchange.getPrincipal()
                .map(principal -> Map.of(
                    "message", "GET does not log out",
                    "username", principal.getName()));
        }
    }
}
~~~

**Giải thích:**

- `@EnableWebFluxSecurity` và bean `SecurityWebFilterChain` cấu hình security reactive.
- `formLogin(Customizer.withDefaults())` dùng trang/handler login mặc định và lưu Authentication qua cơ chế session của form login.
- `logoutUrl("/account/logout")` tạo POST logout match. GET cùng path không bị LogoutWebFilter nhận làm logout, vì vậy controller GET ở ví dụ vẫn đọc principal.
- CSRF vẫn bật; request POST có session cookie nhưng thiếu CSRF token bị từ chối trước khi dọn context.
- Cleanup có `SecurityContextServerLogoutHandler` và `WebSessionServerLogoutHandler` để tránh giữ lại Authentication/session không cần thiết.
- `HttpStatusReturningServerLogoutSuccessHandler(HttpStatus.NO_CONTENT)` trả 204 sau khi handler hoàn tất; không gửi redirect.
- Endpoint `/csrf` chỉ để người học quan sát token được WebFlux tạo. Ứng dụng thật có thể cấp CSRF cho view/template hoặc frontend theo cơ chế khác; không log token hay expose qua CORS cho nguồn lạ.
- `/api/me` kiểm tra principal từ Spring Security, không tin header do client tự khai báo.

### 7.3. Chạy và thử bằng curl

Trong thư mục `webflux-logout-demo`:

~~~bash
gradle bootRun
~~~

Nếu có Gradle Wrapper: `./gradlew bootRun` trên Linux/macOS, `gradlew.bat bootRun` trên Windows. Trong terminal Bash khác, cần `curl` và `jq` để lấy token từ JSON:

~~~bash
# A. Lấy CSRF token và giữ cookie session.
TOKEN=$(curl -sS -c cookies.txt -b cookies.txt \
  http://localhost:8080/csrf | jq -r '.token')

# B. Form login: username/password + CSRF token.
curl -i -b cookies.txt -c cookies.txt \
  --data-urlencode 'username=learner' \
  --data-urlencode 'password=demo-pass' \
  --data-urlencode "_csrf=$TOKEN" \
  http://localhost:8080/login

# C. Đã login: lấy username từ session.
curl -i -b cookies.txt http://localhost:8080/api/me

# D. GET logout URL: trả thông tin, KHÔNG logout.
curl -i -b cookies.txt http://localhost:8080/account/logout

# E. POST logout không có token: kỳ vọng 403.
curl -i -b cookies.txt -X POST http://localhost:8080/account/logout

# F. Sau login lấy CSRF token còn hiệu lực.
TOKEN=$(curl -sS -b cookies.txt -c cookies.txt \
  http://localhost:8080/csrf | jq -r '.token')

# G. POST logout với CSRF: kỳ vọng 204 No Content.
curl -i -b cookies.txt -c cookies.txt \
  --data-urlencode "_csrf=$TOKEN" \
  http://localhost:8080/account/logout

# H. Cookie cũ không còn là Authentication.
curl -i -b cookies.txt http://localhost:8080/api/me
~~~

`-c` ghi cookie jar; `-b` gửi cookie jar; `--data-urlencode` mặc định tạo POST form-urlencoded; `-i` in status/header. Không thêm `-L` khi đang kiểm tra redirect vì nó có thể làm mất thông tin status 302 ban đầu. Shell ví dụ sử dụng mật khẩu giả local; không lưu password thật trong shell history hay command line công cộng.

**HTTP response kỳ vọng trong demo:**

| Bước | Status | Ý nghĩa |
|---|---|---|
| GET /csrf | 200 | Token và tên header/parameter được cấp cho lần thử local. |
| POST /login đúng user/password + CSRF | Thường 302 | Form login thành công và redirect; kiểm tra tiếp GET /api/me để chắc chắn. |
| GET /api/me khi đã login | 200 | JSON có `"username":"learner"`. |
| GET /account/logout | 200 | JSON có `"message":"GET does not log out"`. |
| POST /account/logout thiếu CSRF | **403** | CsrfWebFilter chặn, chưa logout. |
| POST /account/logout đủ CSRF | **204** | Logout handlers chạy, response không có body. |
| GET /api/me với cookie cũ sau logout | Thường 302 tới /login | Form-login entry point yêu cầu đăng nhập lại. |

Một request không authenticated **không phải lúc nào trả 401**: với form login, Spring Security thường redirect 302 tới trang login, còn HTTP Basic hay một API entry point có thể trả 401. Những session IDs, CSRF tokens, ngày/giờ và Location header có thể thay đổi theo runtime.

### 7.4. Nếu muốn chạy thử trên Windows PowerShell

Bash dùng `TOKEN=$(...)`, không phải cú pháp biến PowerShell. Có thể dùng WSL/Git Bash hoặc chạy `curl.exe` và lưu token bằng thao tác phân tích JSON phù hợp. Cần giữ nguyên cùng cookie jar giữa lấy token, login, logout và request kế tiếp. Không chép raw token thành hằng số trong source code.

## 8. Kiểm thử bằng WebTestClient

Bài kiểm thử này mô phỏng request ngay trong ApplicationContext. Nó tập trung xác minh method và CSRF; để chắc chắn **WebSession ngoài đời thực bị hủy qua nhiều request**, vẫn cần kiểm thử cookie jar trong mục 7 hoặc test tích hợp với session store tương ứng.

Tệp `src/test/java/example/LogoutMethodTest.java`:

~~~java
package example;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class LogoutMethodTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void getDoesNotLogOut() {
        client.mutateWith(mockUser("learner"))
            .get().uri("/account/logout")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("GET does not log out")
            .jsonPath("$.username").isEqualTo("learner");
    }

    @Test
    void postWithoutCsrfFails() {
        client.mutateWith(mockUser("learner"))
            .post().uri("/account/logout")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void postWithCsrfLogsOut() {
        client.mutateWith(mockUser("learner"))
            .mutateWith(csrf())
            .post().uri("/account/logout")
            .exchange()
            .expectStatus().isNoContent();
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

Với wrapper dùng `./gradlew test` hoặc `gradlew.bat test`. Các kiểm thử ở đây dùng mock Authentication cho từng request; chúng xác minh HTTP status, không thay thế thử nghiệm session persistence thật. Khi bạn viết thêm custom `ServerLogoutHandler`, nên test gọi handler và kết quả kho session/database cụ thể.

## 9. Khi thật sự muốn GET logout

Spring Security cho phép `requiresLogout(...)` nhận matcher chỉ kiểm tra URL:

~~~java
// Có thể khớp mọi HTTP method, gồm GET: không khuyến nghị.
http.logout(logout -> logout.requiresLogout(
    new PathPatternParserServerWebExchangeMatcher("/account/logout")));
~~~

Đó là một **ngoại lệ cần review bảo mật**. Nếu app có browser tự gửi session cookie, một link hoặc navigation từ bên ngoài có thể logout user mà không có thao tác chủ động trên UI hợp lệ. Đừng bật GET logout chỉ để nút “Đăng xuất” dễ viết. Thay vì thế, dùng GET để hiện confirmation và form POST có CSRF.

Nếu requirement nghiệp vụ buộc client dùng một HTTP method khác (ví dụ DELETE), phải cấu hình matcher method tường minh, giữ các biện pháp CSRF/authorization phù hợp, cập nhật frontend và test mọi đường vào. Không mặc định DELETE an toàn hơn POST khi browser tự gửi cookie.

## 10. Một số ranh giới khác cần nhớ

### 10.1. Session-based logout không giống HTTP Basic logout

Với HTTP Basic, client có thể gửi `Authorization: Basic ...` ở **từng request**. Dù logout handler dọn SecurityContext, request sau gửi lại Basic đúng vẫn có thể được xác thực. Một phản hồi 204 không thể buộc mọi browser quên password Basic đã cache. Nếu UX yêu cầu logout thực sự, cân nhắc session-based login hoặc cơ chế token/revocation phù hợp.

### 10.2. Logout WebSession không tự revoke JWT

Một bearer JWT được ký và còn hạn có thể tiếp tục xác thực API sau khi bạn invalidate WebSession. Cần revoke refresh token, token introspection, danh sách thu hồi hoặc access-token lifetime phù hợp threat model. Không quảng bá endpoint POST logout như “vô hiệu hóa mọi token” nếu implementation chỉ dọn session.

### 10.3. OIDC/SSO có hai phiên

Logout session ứng dụng và logout ở Identity Provider có thể là hai bước riêng. Spring Security có OIDC logout support chuyên biệt; nếu ứng dụng cần single logout, hãy dùng luồng phù hợp với provider và kiểm thử callback/post-logout redirect, thay vì chỉ redirect browser tới trang login local.

### 10.4. Nhiều SecurityWebFilterChain

Nếu website session và API bearer dùng hai `SecurityWebFilterChain`, mỗi chuỗi có matcher `securityMatcher(...)` riêng. Logout URL phải khớp chuỗi có chính sách/logout handler cần dùng. Một request không khớp chuỗi nào có thể không gặp `LogoutWebFilter`. Đặt chain cụ thể trước, chuỗi catch-all bảo vệ mặc định sau và kiểm thử toàn bộ đường dẫn.

### 10.5. Reverse proxy và cookie

Nếu URL ngoài Internet nằm dưới `/service` nhưng app nhận path đã rewrite, kiểm tra cách proxy xử lý path prefix và forwarded headers. Form action, matcher, cookie Path/Domain/Secure/SameSite và redirect Location phải tương thích với domain/prefix thực. Tránh trường hợp người dùng logout một origin nhưng browser vẫn giữ session cookie của origin khác.

## 11. Lỗi phổ biến và cách sửa

**1. POST logout 403 nên tắt CSRF.** Sai với ứng dụng cookie/session. Hãy gửi token hợp lệ. Dùng `CsrfWebFilter` như ranh giới trước thao tác thay đổi trạng thái.

**2. Cấu hình `logoutUrl("/signout")` rồi dùng link GET.** `logoutUrl` mặc định match **POST**. Dùng form POST, không kết luận GET đã xóa phiên.

**3. Dùng `requiresLogout` không có HttpMethod.** Matcher path-only có thể nhận GET và tạo logout CSRF. Chỉ dùng nếu hiểu và chấp nhận rủi ro.

**4. Chỉ redirect tới /login trong controller.** Điều hướng không thay thế xóa context hoặc WebSession. Dùng logout filter và handler đúng.

**5. Chỉ xóa cookie mà không hủy session.** ID cũ có thể vẫn dùng được ở server nếu bị lộ. Invalidate session server-side khi policy đòi.

**6. Chỉ xóa SecurityContext trong request hiện tại.** Repository có thể vẫn lưu context cho request sau. Xóa đúng repository.

**7. Nghĩ WebSession luôn bị invalidate mặc định.** Spring Security reactive cung cấp handler riêng `WebSessionServerLogoutHandler`. Cấu hình minh thị khi cần.

**8. Nghĩ logout local thu hồi JWT.** Token độc lập có thể tiếp tục hoạt động; phải có revoke/expiry policy.

**9. Tự gọi `subscribe()` trong logout handler.** Có thể khiến dọn dữ liệu chạy ngoài pipeline, mất lỗi hoặc trả response trước khi xóa xong. Trả `Mono<Void>` cho Spring.

**10. Thấy 302 sau logout rồi cho là lỗi.** Website form login thường redirect; API có thể chọn 204. Cần phân biệt success handler và authentication entry point.

**11. Test mỗi status 204 nhưng không thử session cũ.** Chưa chứng minh authentication bị thu hồi. Test login → logout → protected request với cookie cũ.

**12. Đặt logout URL ngoài securityMatcher.** Chain không match thì logout filter không thực thi như mong đợi. Test qua gateway thực.

**13. Nhầm `logoutSuccessHandler` với `logoutHandler`.** Handler đầu định dạng phản hồi; handler sau thực hiện dọn state.

**14. Nhầm API Servlet và WebFlux.** Reactive dùng `WebSessionServerLogoutHandler`/`ServerLogoutHandler` và `ServerWebExchange`.

**15. Để lộ CSRF/session cookie trong log.** Token, cookie và credential cần bảo vệ; audit chỉ ghi thông tin cần thiết và được scrub.

## 12. Checklist triển khai

1. Logout URL có thuộc `SecurityWebFilterChain` đúng?
2. Matcher có chỉ chấp nhận HTTP POST theo policy?
3. Client có dùng form POST hoặc AJAX POST được bảo vệ bằng CSRF?
4. GET logout có chỉ hiển thị confirmation/thông tin, không xóa state?
5. CSRF thiếu/sai có bị 403 và không chạy cleanup?
6. Authentication đã được lưu trong repository nào và logout xóa đúng repository đó?
7. Có yêu cầu invalidate cả WebSession không, và handler đã có?
8. HTTP response thành công dùng redirect hay 200/204 theo client?
9. Request sau logout mang cookie cũ có bị yêu cầu xác thực lại?
10. Nếu có nhiều tab/browser/device, định nghĩa rõ logout phiên này hay tất cả phiên.
11. JWT/refresh token có kế hoạch thu hồi/expiry độc lập với session?
12. OIDC có cần logout IdP hay chỉ ứng dụng local?
13. Cookie và redirect có đúng Path/Domain/SameSite/Secure/TLS qua proxy?
14. Không log password, session ID, CSRF token hoặc Authorization header?
15. Có regression test cho GET, POST thiếu CSRF, POST đủ CSRF và request protected sau logout?
16. Không dùng `block()`/`subscribe()` thủ công trong reactive logout handler?

## 13. Câu hỏi tự đánh giá

**1.** Đổi `logoutUrl("/account/logout")` có khiến GET /account/logout logout không?

**Đáp án:** Không. Mặc định matcher logout mới nhận POST tới URL đó; GET có thể do controller/view xử lý nhưng không tự logout.

**2.** POST logout trả 403 dù browser có session cookie. Có nên disable CSRF?

**Đáp án:** Không. Kiểm tra token được server tạo, form/header truyền token, session cookie và CSRF matcher.

**3.** Vì sao `WebSessionServerLogoutHandler` và `SecurityContextServerLogoutHandler` không giống nhau?

**Đáp án:** Một handler invalidate toàn bộ WebSession, handler kia xóa SecurityContext qua repository. Có thể cần cả hai.

**4.** POST logout trả 204 nhưng request sau dùng cookie cũ vẫn authenticated. Điều gì cần điều tra?

**Đáp án:** Logout handler, repository lưu/đọc security context, session store, cookie thực tế, một authentication mechanism khác có thể đang tự xác thực lại và việc có thực sự gửi token/password cũ ở request sau không.

**5.** Một API dùng bearer JWT gửi cùng token sau logout local. Có chắc bị 401?

**Đáp án:** Không. JWT chưa bị revoke và còn hiệu lực có thể vẫn xác thực. Cần thiết kế revoke hoặc expiry.

**6.** GET /logout có thể xuất hiện trong docs mặc định, vậy có nghĩa nên kích hoạt logout bằng GET?

**Đáp án:** Không. GET mặc định có thể hiển thị trang xác nhận, còn POST mới thay đổi trạng thái. Dùng GET logout trực tiếp tạo rủi ro CSRF.

**7.** `logoutSuccessHandler` có dọn session giúp mình không?

**Đáp án:** Không. Nó tạo HTTP response sau khi các logout handler hoàn tất.

**8.** Tại sao phải test cookie cũ sau logout?

**Đáp án:** Vì chỉ status/redirect không chứng minh state phía server đã được vô hiệu. Request tiếp theo là bằng chứng thực tế.

## Tài liệu chính thức

- Spring Security WebFlux — Logout: https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/logout.html
- Spring Security WebFlux — CSRF và POST logout: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
- `ServerHttpSecurity.LogoutSpec` (logoutUrl, requiresLogout): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.LogoutSpec.html
- `LogoutWebFilter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/logout/LogoutWebFilter.html
- `DelegatingServerLogoutHandler`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/logout/DelegatingServerLogoutHandler.html
- `WebSessionServerLogoutHandler`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/logout/WebSessionServerLogoutHandler.html
- `HttpStatusReturningServerLogoutSuccessHandler`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/logout/HttpStatusReturningServerLogoutSuccessHandler.html
- Spring Security WebFlux — Testing CSRF: https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html
- Spring Security WebFlux — WebTestClient Security Setup: https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html
