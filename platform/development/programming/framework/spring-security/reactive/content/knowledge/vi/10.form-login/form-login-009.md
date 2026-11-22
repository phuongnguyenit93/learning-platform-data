# Tách hành vi đăng nhập của trình duyệt khỏi phản hồi JSON cho API trong Spring Security reactive

## 1. Mục tiêu

Một hệ thống Spring WebFlux có thể đồng thời phục vụ **trang web cho người dùng trên trình duyệt** và **REST API cho ứng dụng di động, SPA hoặc dịch vụ khác**. Tuy cùng yêu cầu xác thực, hai nhóm client thường cần hành vi hoàn toàn khác:

- **Trình duyệt truy cập trang HTML:** khi chưa đăng nhập, điều hướng sang trang `/login`; người dùng gửi biểu mẫu, có thể được chuyển về trang đã yêu cầu; khi sai mật khẩu, hiển thị trang đăng nhập với thông báo; dùng cookie/WebSession và CSRF protection.
- **API trả JSON:** khi chưa có credentials trả **401** với nội dung JSON; khi đã xác thực nhưng thiếu quyền trả **403** với JSON; không redirect sang HTML, không bất ngờ phát form login page trong response; API client xử lý status và dữ liệu theo hợp đồng đã công bố.

Bài học giải thích cách **tách chính sách và cơ chế**, không chỉ đổi `Content-Type` cho một trang login. Bạn sẽ hiểu `SecurityWebFilterChain`, `ServerHttpSecurity`, `securityMatcher`, `ServerAuthenticationEntryPoint`, `ServerAccessDeniedHandler` và khác biệt giữa authentication failure với authorization denial; sau đó tạo project Java 17+ có hai nhóm endpoint với hành vi có thể kiểm chứng.

**Thông điệp quan trọng:** muốn response đúng loại client, hãy định nghĩa **ranh giới security chain và authentication mechanism** rõ ràng. Không dùng việc có header `Accept: application/json` như một cơ chế quyết định quyền truy cập.

## 2. Bốn tình huống phải tách biệt

| Sự kiện | Browser HTML | REST API JSON |
| --- | --- | --- |
| Request **chưa đăng nhập** vào tài nguyên riêng tư | Thường **302** và `Location: /login`; browser hiển thị trang login | **401 Unauthorized** với JSON mã lỗi, không tự chuyển về HTML |
| **Gửi credentials sai** | Form login failure thường redirect `/login?error` | Nếu có API login riêng thì trả 401/400 có mã lỗi JSON thích hợp; API Basic/Bearer lỗi thường 401 |
| **Đã đăng nhập nhưng thiếu role/quyền** | Thường **403** hoặc trang lỗi HTML thân thiện, không đẩy về login như anonymous | **403 Forbidden** với JSON, không biến thành HTML login |
| **Đăng nhập thành công** | Với form login, thường redirect đến saved request hoặc landing page; giữ context ở WebSession nếu dùng session | API trả JSON/token hoặc response theo hợp đồng; không redirect. Với Bearer resource server, mỗi request kiểm tra token |

Có một sai lầm phổ biến: dùng `.formLogin()` trên toàn bộ ứng dụng, khiến `GET /api/orders` không có credentials trả redirect tới `/login` thay vì JSON 401. Frontend `fetch()` có thể tự theo redirect và nhận HTML status 200, rồi lỗi khi parse `response.json()`. Tệ hơn, client không phát hiện đúng sự kiện session hết hạn và có thể nhầm lỗi xác thực với lỗi JSON.

Cũng không nên trả 401 cho mọi access denied: **401** là tình huống cần xác thực hợp lệ; **403** là tình huống có danh tính nhưng không đủ quyền theo rule. Một số trường hợp CSRF invalid cũng là 403 nhưng là lớp bảo vệ request, không phải vì thiếu role.

## 3. Vị trí của sự khác biệt trong kiến trúc WebFlux

~~~text
                   Incoming HTTP request
                              |
                              v
                     WebFilterChainProxy
                              |
                chọn SecurityWebFilterChain theo
                securityMatcher và @Order
                              |
              +---------------+----------------+
              |                                |
              v                                v
        /api/** chain                    Browser chain
        @Order(1)                        @Order(2), fallback
              |                                |
      HTTP Basic/Bearer (demo: Basic)    formLogin
      formLogin disabled                 httpBasic disabled
      JSON entry point                   Redirect entry point
      JSON accessDeniedHandler           WebSession context
      no request-cache redirect          CSRF cho login/logout/form
              |                                |
        /api/public: 200                  /: HTML công khai
        /api/me: 401/200                  /web/home: 302 -> /login
        /api/admin: 403/200              POST /login -> redirect
~~~

Hai cấp matcher không giống nhau:

1. **`http.securityMatcher(...)`:** quyết định **toàn bộ chain** có chạy cho request hay không. Với `/api/**` ở chain ưu tiên cao, các filter browser form login **không cần** xử lý request API.
2. **`authorizeExchange(...).pathMatchers(...)`:** quyết định **quyền truy cập** trong chain đã chọn. Đây không phải cách ngăn `formLogin` hoặc các filter khác trong chain được kích hoạt.

Spring Security reactive hỗ trợ nhiều `SecurityWebFilterChain`; đây là cấu hình bình thường, không phải bean trùng lỗi. `@Order` điều khiển chain nào được xét trước. Một chain fallback không đặt matcher chuyên biệt có thể bảo vệ những URL còn lại. Nếu **không có chain nào match**, URL có thể nằm ngoài vùng bảo vệ Spring Security — rủi ro lớn khi tách API và browser.

### Vì sao không chỉ dùng Accept header?

`Accept` thể hiện loại biểu diễn client mong muốn, nhưng:

- Browser có thể gửi `Accept: application/json` trong `fetch()`, dù vẫn sử dụng cookie session.
- Script hoặc bot có thể gửi `Accept: text/html`, dù gọi API.
- Một request có `Accept: */*` không cho bạn biết chính xác đó là app, browser hay backend.
- `Accept` không phải bằng chứng danh tính, không phải tiêu chí để cấp quyền hay bật/tắt CSRF.

Có thể dùng negotiation để **định dạng** response sau khi chính sách đã được xác định, nhưng quyết định scheme, session/cookie, CSRF, OAuth2/JWT và security chain phải dựa trên **route/hợp đồng truy cập được thiết kế rõ ràng**.

## 4. Những thành phần reactive cần hiểu

| Thành phần | Vai trò | Dùng ở đâu? |
| --- | --- | --- |
| `SecurityWebFilterChain` | Mô tả filter cho một vùng request | Một bean cho API, một bean cho HTML |
| `ServerHttpSecurity` | DSL cấu hình WebFlux Security | Tạo từng chain |
| `PathPatternParserServerWebExchangeMatcher` | Match URL ở cấp chain | Ví dụ `/api/**` |
| `ServerAuthenticationEntryPoint` | Bắt đầu xác thực khi request cần danh tính | HTML: redirect; API: 401 JSON |
| `ServerAccessDeniedHandler` | Xử lý người dùng đã xác thực nhưng thiếu quyền | API: 403 JSON |
| `ServerAuthenticationFailureHandler` | Xử lý **một authentication attempt thất bại** | API Basic sai password: JSON; form login sai: redirect |
| `ServerAuthenticationSuccessHandler` | Xử lý authentication thành công | Form: redirect; JSON login: response JSON |
| `ServerSecurityContextRepository` | Lưu/đọc `SecurityContext` giữa các request, nếu có | Browser thường WebSession; API Basic stateless có thể NoOp |
| `ServerRequestCache` | Nhớ URL ban đầu để redirect lại sau login | Hữu ích với browser; API không cần |
| `CsrfWebFilter` | Bảo vệ request thay đổi trạng thái trong bối cảnh có CSRF risk | Đặc biệt cần cho form/cookie |

Phân biệt cụ thể ba loại handler:

- `authenticationEntryPoint` nhận request **chưa có authentication được chấp nhận** tại bước cần login (ví dụ request API không có credentials, hoặc browser cần điều hướng đến trang login).
- `authenticationFailureHandler` xử lý việc **thử xác thực đã thất bại** (password sai, token không hợp lệ...). Đừng chỉ đặt entry point ở `exceptionHandling` rồi giả định mọi filter authentication tự sử dụng nó.
- `accessDeniedHandler` xử lý **access denied** sau khi có danh tính phù hợp nhưng không đủ authority. Một request bị CSRF filter từ chối có thể sử dụng cơ chế error handler riêng; cần cấu hình nếu muốn toàn bộ API lỗi CSRF cũng ra JSON.

## 5. Cấu hình tách hai chain có thể chạy được

Ta sẽ tạo một project duy nhất nhưng có hai vùng URL:

- Browser: `/` công khai; `/web/home` yêu cầu login; `/web/admin` yêu cầu `ROLE_ADMIN`; Spring Security tạo trang `GET /login` và xử lý `POST /login`.
- API: `GET /api/public` công khai; `GET /api/me` yêu cầu login; `GET /api/admin` cần `ROLE_ADMIN`. Response thành công là JSON. Response 401/403 có body JSON cố định, **không redirect sang `/login`**.

Để không cần hạ tầng OAuth2/JWT trong bài thực hành, API minh họa bằng **HTTP Basic** với hai user local. HTTP Basic **không phải** lựa chọn mặc định tốt cho mọi SPA; nó chỉ giúp dễ quan sát ranh giới authentication và response. Trong production nên chọn Bearer/OAuth2 hoặc cơ chế API phù hợp, đánh giá token expiry, CORS/CSRF và đặc tính trình duyệt. Phần `11` phân tích cách chuyển sang API token hoặc JSON login.

### 5.1. Project Maven, Java 17+

Tạo project Spring Initializr với Maven, Java **17+**, Spring Boot **4.1.2**, group `com.example`, artifact `browser-api-security`. Chọn dependencies **Spring Reactive Web** và **Spring Security**.

File `pom.xml` đầy đủ tối giản:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>browser-api-security</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring Boot BOM tự quản lý Spring Framework, Spring Security và Reactor; **không** thêm version riêng cho từng Spring module. Với nhánh Boot 3.5, phải sử dụng parent/BOM cùng nhánh và xác nhận API tương ứng.

### 5.2. Một file Java đầy đủ

Tạo file `src/main/java/com/example/browserapi/BrowserApiSecurityApplication.java` với nội dung:

~~~java
package com.example.browserapi;

import java.nio.charset.StandardCharsets;
import java.security.Principal;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authentication.ServerAuthenticationEntryPointFailureHandler;
import org.springframework.security.web.server.authorization.ServerAccessDeniedHandler;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.savedrequest.NoOpServerRequestCache;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class BrowserApiSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(BrowserApiSecurityApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails viewer = User.withUsername("viewer")
                .password(encoder.encode("viewer123!"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin123!"))
                .roles("ADMIN")
                .build();

        return new MapReactiveUserDetailsService(viewer, admin);
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        ServerAuthenticationEntryPoint unauthorized = (exchange, error) ->
                writeJson(exchange, HttpStatus.UNAUTHORIZED, "unauthorized");

        ServerAccessDeniedHandler denied = (exchange, error) ->
                writeJson(exchange, HttpStatus.FORBIDDEN, "forbidden");

        return http
                .securityMatcher(
                        new PathPatternParserServerWebExchangeMatcher("/api/**"))
                .authorizeExchange(rules -> rules
                        .pathMatchers("/api/public").permitAll()
                        .pathMatchers("/api/admin").hasRole("ADMIN")
                        .anyExchange().authenticated())
                .httpBasic(basic -> basic
                        .authenticationEntryPoint(unauthorized)
                        .authenticationFailureHandler(
                                new ServerAuthenticationEntryPointFailureHandler(
                                        unauthorized)))
                .formLogin(form -> form.disable())
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint(unauthorized)
                        .accessDeniedHandler(denied))
                .csrf(csrf -> csrf.accessDeniedHandler(denied))
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                .requestCache(cache -> cache
                        .requestCache(NoOpServerRequestCache.getInstance()))
                .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain browserChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(rules -> rules
                        .pathMatchers("/", "/web/public").permitAll()
                        .pathMatchers("/web/admin").hasRole("ADMIN")
                        .anyExchange().authenticated())
                .httpBasic(basic -> basic.disable())
                .formLogin(Customizer.withDefaults())
                .build();
    }

    private static Mono<Void> writeJson(
            ServerWebExchange exchange, HttpStatus status, String error) {
        ServerHttpResponse response = exchange.getResponse();
        response.setStatusCode(status);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
        String json = "{\"error\":\"" + error + "\"}";
        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        return response.writeWith(
                Mono.just(response.bufferFactory().wrap(bytes)));
    }

    @RestController
    static class DemoController {

        @GetMapping(value = "/", produces = MediaType.TEXT_HTML_VALUE)
        Mono<String> index() {
            return Mono.just("""
                    <!doctype html>
                    <html lang="vi"><head><meta charset="UTF-8">
                    <title>Browser Demo</title></head>
                    <body>
                      <h1>Trang web công khai</h1>
                      <a href="/web/home">Vào trang riêng tư</a>
                    </body></html>
                    """);
        }

        @GetMapping(value = "/web/public",
                produces = MediaType.TEXT_HTML_VALUE)
        Mono<String> webPublic() {
            return Mono.just("<h1>PUBLIC_HTML</h1>");
        }

        @GetMapping(value = "/web/home",
                produces = MediaType.TEXT_HTML_VALUE)
        Mono<String> webHome() {
            return Mono.just("<h1>WEB_HOME</h1>");
        }

        @GetMapping(value = "/web/admin",
                produces = MediaType.TEXT_HTML_VALUE)
        Mono<String> webAdmin() {
            return Mono.just("<h1>WEB_ADMIN</h1>");
        }

        @GetMapping(value = "/api/public",
                produces = MediaType.APPLICATION_JSON_VALUE)
        Mono<Map<String, String>> apiPublic() {
            return Mono.just(Map.of(
                    "message", "PUBLIC_JSON"));
        }

        @GetMapping(value = "/api/me",
                produces = MediaType.APPLICATION_JSON_VALUE)
        Mono<Map<String, String>> apiMe(Principal principal) {
            return Mono.just(Map.of(
                    "user", principal.getName(),
                    "mode", "http-basic"));
        }

        @GetMapping(value = "/api/admin",
                produces = MediaType.APPLICATION_JSON_VALUE)
        Mono<Map<String, String>> apiAdmin() {
            return Mono.just(Map.of(
                    "message", "ADMIN_JSON"));
        }
    }
}
~~~

**Đây là project demo đầy đủ trong một class**, tận dụng Java text block của Java 17. File, package và public class khớp nhau. Spring Boot starter WebFlux cung cấp server và JSON codec phù hợp; không cần controller tự viết HTTP response cho từng API thành công.

### 5.3. Giải thích từng quyết định trong cấu hình

**Chain API:**

- `@Order(1)` và `securityMatcher("/api/**")`: mọi URL API của ví dụ đi vào chain ưu tiên cao.
- `formLogin(...disable())`: API không tạo redirect hay trang đăng nhập form; không có form login filter trong chain này.
- `httpBasic(...)`: Basic parser/manager xử lý username/password để demo. `authenticationEntryPoint` được đặt riêng để đổi phản hồi “chưa đăng nhập” thành JSON; `authenticationFailureHandler` giúp credentials Basic sai cũng nhận JSON.
- `exceptionHandling(...)`: khi authorization đòi authentication hoặc deny role, dùng **JSON entry point / access denied handler** tương ứng.
- `csrf(csrf -> csrf.accessDeniedHandler(denied))`: **vẫn giữ CSRF protection**; khi có request unsafe thiếu token, handler CSRF của chain này trả JSON 403 thay vì nội dung HTML. Ví dụ chỉ có GET để tránh giả định API Basic trong browser là miễn nhiễm CSRF.
- `NoOpServerSecurityContextRepository`: không lưu authentication của API Basic vào WebSession. Basic credentials được kiểm tra ở request có header; request không header không được “kế thừa” browser login chỉ vì cùng host.
- `NoOpServerRequestCache`: API không lưu request nhằm redirect lại sau form login.

**Chain browser:**

- `@Order(2)` và không có `securityMatcher` chuyên biệt: bảo vệ những URL **không thuộc `/api/**`** nhờ fallback.
- `httpBasic(...disable())`: giảm nguy cơ browser bật native Basic login dialog thay vì hiển thị form.
- `formLogin(withDefaults())`: Spring Security tạo `GET /login` mặc định và xử lý `POST /login` từ HTML form; success thường redirect đến saved request hoặc trang gốc; failure chuyển tới `/login?error`.
- Giữ CSRF protection mặc định. Trình duyệt gửi login form chứa CSRF token và lưu cookie phiên theo cơ chế Spring Security.
- `authorizeExchange` bảo vệ `/web/home` và yêu cầu role trên `/web/admin`. Với `/web/public`, rule `permitAll` cho phép HTML công khai.

**Nguồn người dùng:** `MapReactiveUserDetailsService` chứa hai user minh họa, được mã hóa bằng `PasswordEncoder`. User `viewer` có `ROLE_USER`, user `admin` có `ROLE_ADMIN`. Mật khẩu demo có trong source chỉ cho local; tuyệt đối không dùng tài khoản mẫu hoặc secret hard-code cho production.

### 5.4. Một lưu ý về HTTP Basic và WWW-Authenticate

Ví dụ API cố ý trả JSON 401 và **không gửi Basic challenge** để trình duyệt không bật hộp thoại HTTP Basic. Đây là cách minh họa phân tách UX, **không phải mẫu HTTP Basic chuẩn cho mọi client**: theo HTTP semantics, phản hồi 401 cho cơ chế HTTP authentication cần challenge `WWW-Authenticate` phù hợp; một số client chuẩn cần header này. Vì thế với API production, nên chọn cơ chế được thiết kế cho API (thường OAuth2 Bearer) và trả `WWW-Authenticate: Bearer ...` theo chuẩn thích hợp cùng response JSON khi chính sách cho phép, hoặc thiết kế endpoint JSON login/session minh bạch. Đừng xóa challenge mà không đánh giá tương thích protocol/client.

Các JSON handler trên là mẫu giáo dục. Trong ứng dụng thật, không chỉ riêng 401/403 mà còn lỗi validation, 404, 405, 415, 500... cần có hợp đồng JSON chuẩn hóa và tập trung.

## 6. Chạy và kiểm chứng hai đường đi

Tại thư mục chứa `pom.xml`, sử dụng Maven wrapper từ Spring Initializr:

~~~bash
./mvnw clean package
./mvnw spring-boot:run
~~~

Windows: `.\mvnw.cmd clean package` và `.\mvnw.cmd spring-boot:run`; nếu không có wrapper thì dùng Maven cài sẵn. Cổng mặc định là `http://localhost:8080` trừ khi cấu hình khác.

### 6.1. Trình duyệt: trang công khai và redirect

Mở `http://localhost:8080/`: nhận HTML trang công khai, có liên kết tới `/web/home`.

Mở `http://localhost:8080/web/home` khi chưa đăng nhập: trình duyệt được điều hướng sang trang `/login`; đây là trang HTML mặc định do Spring Security tạo (không phải JSON).

Đăng nhập bằng `viewer` / `viewer123!` trên form. Khi thành công, Spring Security có thể đưa về trang đã yêu cầu; vào `/web/home` sẽ thấy `WEB_HOME`. Mở `/web/admin` bằng viewer bị **403** vì thiếu `ROLE_ADMIN`. Đăng xuất bằng tính năng logout được Spring Security cung cấp hoặc dùng phiên trình duyệt riêng rồi đăng nhập bằng `admin` / `admin123!`; admin vào `/web/admin` sẽ nhận HTML có `WEB_ADMIN`.

Khi chưa đăng nhập, lệnh sau thường cho thấy **302 Found** với `Location` trỏ tới trang login:

~~~bash
curl -i -H "Accept: text/html" http://localhost:8080/web/home
~~~

Dùng `curl -i` chứ không bật `-L` nếu muốn quan sát redirect gốc: `-L` theo chuyển hướng và có thể khiến bạn chỉ nhìn thấy HTTP 200 của trang HTML login.

### 6.2. REST API: JSON không redirect

Những lệnh sau dùng `curl` và API JSON. Thay `curl` bằng `curl.exe` trong Windows PowerShell nếu tên `curl` bị alias sang lệnh khác:

~~~bash
# Public API, không có credentials
curl -i -H "Accept: application/json" \
  http://localhost:8080/api/public

# Private API, không có credentials
curl -i -H "Accept: application/json" \
  http://localhost:8080/api/me

# Private API, sai mật khẩu Basic
curl -i -u viewer:wrong \
  -H "Accept: application/json" \
  http://localhost:8080/api/me

# Private API, viewer hợp lệ
curl -i -u 'viewer:viewer123!' \
  -H "Accept: application/json" \
  http://localhost:8080/api/me

# Viewer thiếu ROLE_ADMIN
curl -i -u 'viewer:viewer123!' \
  http://localhost:8080/api/admin

# Admin có ROLE_ADMIN
curl -i -u 'admin:admin123!' \
  http://localhost:8080/api/admin
~~~

Trong shell không hỗ trợ dấu `\` để xuống dòng, đặt mỗi command thành một dòng. Kết quả mong đợi:

| Request | HTTP status | Body JSON điển hình |
| --- | --- | --- |
| `GET /api/public` (anonymous) | **200** | `{"message":"PUBLIC_JSON"}` |
| `GET /api/me` (anonymous) | **401** | `{"error":"unauthorized"}` |
| `GET /api/me` (Basic sai password) | **401** | `{"error":"unauthorized"}` |
| `GET /api/me` (viewer) | **200** | `{"user":"viewer","mode":"http-basic"}` |
| `GET /api/admin` (viewer) | **403** | `{"error":"forbidden"}` |
| `GET /api/admin` (admin) | **200** | `{"message":"ADMIN_JSON"}` |

Body JSON thành công có thể đổi **thứ tự các key** vì `Map.of` không cam kết thứ tự serialization. Khi test, **parse JSON rồi so giá trị các field**, không so text serialization cứng như một chuỗi duy nhất. Các error body JSON 401/403 là do method `writeJson(...)` tạo ra với một field `error`.

Để xác nhận không có redirect, kiểm tra **không có status 3xx và không có `Location: /login`** ở các API được kiểm thử. Cũng kiểm tra `Content-Type: application/json`. Đừng kết luận chỉ từ một 200 sau khi `curl -L` hoặc browser `fetch` tự follow redirect.

### 6.3. Trường hợp cùng một browser đã login rồi gọi API

Vì hai chain dùng cơ chế riêng, API demo dùng `NoOpServerSecurityContextRepository`; việc browser có WebSession đã đăng nhập không tự khiến `GET /api/me` được xác thực **nếu không gửi Basic header**. Đây là minh họa cho **phân tách session browser với credentials API**.

Nếu sản phẩm của bạn thực sự muốn một SPA dùng cookie session để gọi `/api/**`, **đừng áp dụng máy móc `NoOpServerSecurityContextRepository` hoặc quy tắc “API không cần CSRF”**. Trong trường hợp đó API dùng cookie làm authentication, cần dùng security context repository phù hợp, CSRF header, SameSite/cookie attributes, CORS với credentials và các rule phù hợp. Phân tách HTML/JSON response vẫn thực hiện được, nhưng **cơ chế xác thực đã khác**.

## 7. CSRF, CORS và cookie: JSON không làm API tự an toàn

### 7.1. Browser form login phải xử lý CSRF

Spring Security WebFlux bật CSRF protection theo mặc định cho phương thức HTTP không an toàn. Form đăng nhập cũng là thao tác có rủi ro login CSRF. Trang login mặc định do Spring Security tạo đã tích hợp CSRF token; khi tự làm trang login bằng Thymeleaf/HTML, phải đưa token hợp lệ vào form:

~~~html
<form method="post" action="/login">
  <label>Username <input name="username" autocomplete="username"></label>
  <label>Password <input name="password" type="password"
                         autocomplete="current-password"></label>
  <input type="hidden" name="_csrf" value="TOKEN_FROM_SERVER">
  <button type="submit">Sign in</button>
</form>
~~~

Đây là **HTML mẫu để giải thích**, không dùng nguyên `TOKEN_FROM_SERVER`. Khi sử dụng Spring Security và Thymeleaf tích hợp đúng, framework có thể tự đưa token vào form; còn HTML tự render phải lấy `CsrfToken` từ `ServerWebExchange` hoặc cơ chế tương đương. Không vô hiệu hóa CSRF toàn hệ thống chỉ để form login chạy được.

### 7.2. API JSON dùng cookie session vẫn có CSRF risk

JSON body không loại bỏ CSRF khi browser gửi session cookie tự động. Ví dụ SPA gọi `POST /api/profile` với `credentials: "include"` cần được thiết kế chống CSRF bằng token/header hoặc các biện pháp phòng vệ được phân tích đầy đủ. Việc chọn `Content-Type: application/json` không phải tấm khiên chống mọi CSRF, vì có nhiều hình thức side-effect khác và rủi ro cấu hình CORS.

Ngược lại, một server-to-server API chỉ nhận Bearer token từ `Authorization` header do client chủ động đặt, không dùng cookie hay browser authentication tự động, có thể có mô hình CSRF khác. Chỉ tắt CSRF ở chain API sau khi chứng minh giả định đó đúng, chứ không sao chép `csrf.disable()` cho mọi REST API.

### 7.3. CORS và credential

CORS xác định origin browser nào có thể đọc HTTP response. Một cấu hình CORS quá rộng đi kèm cookie credentials có thể gây lộ dữ liệu. Không dùng `Access-Control-Allow-Origin: *` chung với credentials. Với API có cookie, đặt origin allowlist cụ thể, xác định `Access-Control-Allow-Credentials` cần hay không, và phối hợp chính sách cookie `Secure`, `HttpOnly`, `SameSite` với luồng xác thực.

CORS không thay thế authentication/authorization; một request từ script ngoài origin chưa được phép đọc response vẫn có thể gây side effect nếu backend không bảo vệ đủ các POST/PUT/DELETE.

## 8. Nếu cần form login HTML tùy chỉnh

Trong browser chain, có thể thay:

~~~java
.formLogin(Customizer.withDefaults())
~~~

bằng:

~~~java
.formLogin(form -> form
        .loginPage("/signin"))
~~~

Đây là **snippet thay thế ở browser chain**, không phải lớp Java độc lập. Khi dùng `loginPage("/signin")`, Spring Security không tự tạo trang HTML mặc định như trước. Ứng dụng phải phục vụ **GET /signin**, trang lỗi ở `/signin?error`, form submit **POST /signin** và CSRF token phù hợp. Phải khai báo `/signin` được truy cập công khai:

~~~java
.authorizeExchange(rules -> rules
        .pathMatchers("/", "/signin", "/web/public").permitAll()
        .pathMatchers("/web/admin").hasRole("ADMIN")
        .anyExchange().authenticated())
~~~

Đừng chỉ đổi `loginPage` rồi quên tạo handler HTML: browser có thể mắc vòng lặp redirect hoặc gặp 404 thay vì form. Đừng dùng chung `/api/login` cho form HTML nếu hợp đồng JSON API đòi body và status khác.

Form login thành công mặc định sử dụng `RedirectServerAuthenticationSuccessHandler`, có thể redirect đến saved request hoặc `/`; failure dùng handler tương ứng và redirect `/signin?error`. Nếu muốn đổi đích:

~~~java
.formLogin(form -> form
        .authenticationSuccessHandler(
                new RedirectServerAuthenticationSuccessHandler("/web/home"))
        .authenticationFailureHandler(
                new RedirectServerAuthenticationFailureHandler("/signin?error"))
        .loginPage("/signin"))
~~~

Đây là **snippet cấu hình**, cần import các handler từ `org.springframework.security.web.server.authentication`. Lưu ý: đặt success handler redirect cố định sẽ làm thay đổi hành vi phục hồi saved request; hãy cân nhắc UX của ứng dụng trước khi dùng. Không trả password hoặc authentication exception chi tiết trong URL/query string.

## 9. Nếu cần đăng nhập JSON cho API, đừng dùng formLogin mặc định

Có hai cách kiến trúc khác nhau mà người học dễ trộn:

**Cách A — API xác thực từng request bằng Bearer/OAuth2:** client lấy access token từ identity provider/authorization server, gọi `/api/**` với header `Authorization: Bearer ...`, server kiểm tra token. Không có HTML form login trong API chain. Khi token thiếu/sai thường trả 401 kèm `WWW-Authenticate: Bearer` theo cơ chế resource server; khi token hợp lệ nhưng thiếu scope/role trả 403. Đây thường là kiến trúc phù hợp cho mobile và máy–máy.

**Cách B — API có JSON login endpoint:** ứng dụng định nghĩa `POST /api/auth/login` nhận JSON credentials, gọi `ReactiveAuthenticationManager`, rồi trả JSON success/failure và tạo session/token theo mô hình đã chọn. Không chỉ thêm một controller trả `{"ok":true}` sau khi kiểm tra password; cần thiết kế cả:

- `ServerAuthenticationConverter` đọc JSON body đúng cách, validate schema và xử lý malformed input.
- `AuthenticationWebFilter` hoặc cơ chế xác thực tương ứng có matcher chỉ áp dụng `POST /api/auth/login`.
- `ServerAuthenticationSuccessHandler` và `ServerAuthenticationFailureHandler` không redirect, trả JSON có mã lỗi ổn định, không tiết lộ user có tồn tại hay không.
- Lưu và tái sử dụng SecurityContext bằng `ServerSecurityContextRepository` **nếu** dùng session; hoặc phát token và xác thực token ở mọi request nếu dùng stateless.
- CSRF protection khi dùng cookie session; rate limiting, brute-force protection, HTTPS, session fixation, cookie policy, logout/revocation, test login failure và bảo mật token.
- Nếu dùng Bearer JWT, đánh giá nơi phát token và nơi resource server verify issuer/signature/audience/expiration; không tự triển khai JWT ký bằng secret đơn giản chưa có threat model.

**Chỉ thay authentication success handler không tự biến form-urlencoded credentials thành JSON input**. Converter mặc định của form login nhận các trường form như `username` và `password`; còn JSON payload cần converter hoặc endpoint chuyên biệt. Cũng không nên ép form login chain trả 200 JSON mà vẫn giữ redirect entry point ở các URL khác, vì frontend sẽ nhìn thấy hành vi bất nhất.

### Mẫu phần phản hồi lỗi JSON có thể tái sử dụng

Ở lớp Java mẫu phần 5, `writeJson(...)` minh họa một hàm để ghi mã lỗi chuẩn hóa. Nếu dùng `Problem Details` theo RFC 9457 trong sản phẩm thật, bạn có thể xuất response:

~~~json
{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Authentication is required"
}
~~~

Và một phản hồi tương tự với `status: 403` và `title: "Forbidden"`. Đây là **mẫu schema**, chưa phải output từ code demo (demo chỉ xuất `{"error":"..."}`). Đặt `Content-Type: application/problem+json` khi thật sự tuân theo chuẩn Problem Details; đừng gọi mọi JSON object là Problem Details.

### Phân biệt HTTP error và thông tin nghiệp vụ

401/403 trong WebFlux security là lỗi security layer. Lỗi 400 do JSON sai cấu trúc, 422 do dữ liệu không hợp lệ, 404 do route không tồn tại và 500 do lỗi hệ thống thường được xử lý ở handler/controller advice hoặc exception mapper phù hợp. Không bắt mọi `Throwable` rồi trả 401 JSON; làm vậy che giấu lỗi hạ tầng và gây chẩn đoán sai.

## 10. Những bẫy thường gặp

### Bẫy 1 — Đặt formLogin ở chain bao phủ API

~~~java
// Cấu hình thiếu ranh giới; có thể redirect API về /login.
http.authorizeExchange(r -> r.anyExchange().authenticated())
    .formLogin(Customizer.withDefaults());
~~~

Đây là **snippet để nhận diện vấn đề**, không phải project độc lập. Nếu chain này bao phủ `/api/**`, request API anonymous có thể bị redirect sang login HTML. Tách chain với `securityMatcher` hoặc thiết kế entry point theo matcher rõ ràng.

### Bẫy 2 — Chỉ đặt accessDeniedHandler JSON

Nếu chỉ sửa 403, request API **chưa xác thực** vẫn có thể redirect sang `/login`. Phải xử lý cả **entry point 401**, **authentication failure**, và **access denied**. Nếu có CSRF unsafe request, xem thêm CSRF handler.

### Bẫy 3 — Chỉ tắt formLogin nhưng không có cơ chế xác thực

Sau `formLogin(disable)`, ứng dụng vẫn cần Basic/Bearer/hoặc authentication filter tùy thiết kế. Nếu không, API private có thể liên tục trả 401 dù client gửi token chưa được một filter nào xử lý. JSON handler không thực hiện xác thực.

### Bẫy 4 — Dùng @Primary để chọn chain

`@Primary` là cách chọn bean khi injection theo type; không phải router HTTP. Spring Security chọn `SecurityWebFilterChain` theo `@Order` và `securityMatcher`. Hai bean chain với tên khác nhau là hợp lệ; matcher và thứ tự mới quyết định hành vi.

### Bẫy 5 — Đặt fallback chain trước API chain

Nếu một chain match-all có ưu tiên cao hơn chain API, nó có thể nhận `/api/**` trước. Kết quả là JSON API lại bị chuyển hướng hoặc áp sai policy browser. Test trực tiếp `GET /api/me` anonymous, wrong password và user không đủ role để phát hiện lỗi này.

### Bẫy 6 — Dựa hoàn toàn vào Accept hoặc X-Requested-With

Những header này có thể bị thay đổi. Sử dụng chúng cho định dạng nội dung có thể hợp lý, nhưng **không** dựa vào chúng để tin request đã qua xác thực hoặc để quyết định tắt CSRF. Route API và browser, cookie/token, origin, request method và policy phải được thiết kế độc lập.

### Bẫy 7 — Vô hiệu hóa CSRF toàn bộ chỉ vì API JSON

Form login và cookie-based session cần CSRF protection. Cấu hình `csrf.disable()` trên một chain rộng có thể khiến login/logout và POST form bị tấn công. Hãy xác định chain nào thực sự stateless, không có browser-sent credentials và chỉ cân nhắc disable khi threat model cho phép.

### Bẫy 8 — Dùng response 200 HTML để che giấu 401

`fetch` có thể tự follow redirect và chỉ hiển thị HTTP 200 của `/login`. Khi frontend gọi `response.json()` sẽ lỗi parse. Đảm bảo API trả status trực tiếp 401/403, `Content-Type` tương ứng và body JSON như hợp đồng, rồi viết frontend kiểm tra `response.ok`/`response.status`.

### Bẫy 9 — JSON exception handler làm lộ stack trace

Không xuất `AuthenticationException.getMessage()` thẳng ra body cho client. Message có thể tiết lộ user có tồn tại, trạng thái tài khoản hoặc thông tin nội bộ. Dùng mã lỗi chung; log có cấu trúc nội bộ và không chứa password/token.

### Bẫy 10 — Nhầm SecurityFilterChain với SecurityWebFilterChain

`HttpSecurity`, `SecurityFilterChain`, `AuthenticationEntryPoint` Servlet và `OncePerRequestFilter` không phải API cần dùng cho Spring WebFlux. Với reactive, dùng `ServerHttpSecurity`, `SecurityWebFilterChain`, `ServerAuthenticationEntryPoint`, `WebFilter` và handler reactive trả `Mono<Void>`.

## 11. Test matrix trước khi triển khai

| Test | Input | Kết quả yêu cầu |
| --- | --- | --- |
| HTML public | `GET /` anonymous | 200, `text/html` |
| Browser private anonymous | `GET /web/home` | Redirect trang `/login`, không JSON |
| Browser login page | `GET /login` | HTML chứa form và CSRF token |
| Browser login failure | `POST /login` credentials sai, CSRF hợp lệ | Redirect hoặc trang lỗi HTML theo cấu hình |
| Browser login success | `POST /login` credentials đúng, CSRF hợp lệ | Redirect đích đúng; cookie session phù hợp |
| Browser role mismatch | Viewer vào `/web/admin` | 403, không coi là login failure |
| API public | `GET /api/public` anonymous | 200, `application/json` |
| API private anonymous | `GET /api/me` | **401 JSON**, không redirect |
| API wrong credentials | Basic password sai | **401 JSON**, không redirect |
| API user authenticated | Viewer vào `/api/me` | 200 JSON có username |
| API insufficient role | Viewer vào `/api/admin` | **403 JSON**, không redirect |
| API admin | Admin vào `/api/admin` | 200 JSON |
| API spoof Accept | `GET /api/me` với `Accept: text/html` | Vẫn chọn API chain, không trả form login |
| Browser spoof Accept | `GET /web/home` với `Accept: application/json` | Vẫn chọn browser chain; không đổi chính sách |
| API unsafe request | POST không token CSRF (nếu có cookie/CSRF) | 403 JSON hoặc theo chính sách cụ thể, không âm thầm bỏ qua |
| Unknown route | `GET /api/unknown` | Cần hợp đồng xử lý 401/404 rõ ràng; không redirect sang HTML |

**Điểm kiểm thử quan trọng:** không dựa vào status duy nhất. Xác nhận cả `Location`, `Content-Type`, JSON schema, sự hiện diện/vắng mặt của cookie, và hành vi sau khi browser đã đăng nhập. Với Spring WebFlux có thể dùng `WebTestClient` và Spring Security test utilities để test login, CSRF và authorities; so JSON theo field chứ không so thứ tự key.

Một trình tự tốt: test chain routing trước (`/api/**` vs browser), test entry point 401, tiếp đến failure handler 401, access denied 403, cuối cùng test form login success và CSRF với cookie jar riêng.

## 12. Checklist vận hành và bảo mật

1. Ranh giới URL rõ ràng: `/api/**` không lọt sang form login chain; browser có fallback bao phủ mọi URL cần bảo vệ.
2. Xác thực API theo cơ chế được công bố: Basic minh họa, Bearer/IdP thường phù hợp hơn trong production; không chấp nhận JWT mà không có validator.
3. API 401 và 403 thống nhất JSON; không trả redirect/html trong các lỗi security đã định nghĩa.
4. Browser vẫn có login page, success/failure redirect phù hợp, không có vòng lặp redirect.
5. CSRF được giữ cho form/cookie request; CORS và cookie policy được đánh giá riêng.
6. Có chiến lược xử lý access token expiry, revocation, logout và session timeout rõ ràng.
7. Không log credentials, session cookie, access token, refresh token; audit thành công/thất bại an toàn.
8. Khác biệt giữa 401/403/CSRF 403 được xác định trong telemetry và test.
9. Các lỗi ứng dụng ngoài security (validation, 404, 500) có JSON error contract riêng.
10. Test browser, API client, SPA dùng cookie và client ngoài browser **đúng với từng mô hình**; không áp dụng một chuỗi test cho tất cả.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `.formLogin()` trên mọi URL dễ làm `fetch("/api/me")` báo lỗi JSON?

**Đáp án:** request anonymous có thể redirect tới trang login HTML; fetch theo redirect rồi parse HTML như JSON sẽ lỗi. API nên trả 401 JSON trực tiếp theo hợp đồng.

**Câu 2.** Đặt `@Order(1)` cho chain API có đủ chưa?

**Đáp án:** Chưa. Chain phải có `securityMatcher` chỉ đúng `/api/**`; browser fallback đặt sau, và authorization rule đúng trong từng chain. Nếu matcher sai, request có thể vào chain khác hoặc không được bảo vệ.

**Câu 3.** Vì sao phải cấu hình cả entry point và authentication failure handler cho API Basic?

**Đáp án:** “Chưa có credentials nhưng resource yêu cầu login” và “đã gửi Basic credentials sai” là hai đường xử lý khác nhau. Muốn cả hai ra JSON, phải bảo đảm cấu hình của cả entry point và filter authentication failure.

**Câu 4.** Viewer đã xác thực nhưng gọi `/api/admin`. Vì sao 403 mà không phải 401?

**Đáp án:** Viewer có danh tính hợp lệ nhưng thiếu `ROLE_ADMIN`; đây là quyết định authorization denied.

**Câu 5.** API trả JSON thì có thể tắt CSRF tự động không?

**Đáp án:** Không. Phải biết browser có tự gửi cookie/session hoặc cached credentials không. CSRF threat model độc lập với định dạng JSON.

**Câu 6.** Thay `Content-Type` của trang `/login` thành JSON có giải quyết được vấn đề không?

**Đáp án:** Không. Flow redirect, request cache, form-urlencoded login, session repository và failure/success handler vẫn có thể theo hành vi HTML; muốn JSON login phải thiết kế đúng converter/filter/handlers và cơ chế cấp quyền.

**Câu 7.** Có thể dùng một API token stateless và browser session trong cùng ứng dụng không?

**Đáp án:** Có. Hai `SecurityWebFilterChain` có matcher và thứ tự rõ ràng là một cách tiêu biểu; API dùng cơ chế token, browser dùng form login/session, và từng chain có entry point, authorization, CSRF/context policy phù hợp.

## 14. Tài liệu chính thức

- [Spring Security — WebFlux Security và Multiple Chains](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — Getting Started with WebFlux](https://docs.spring.io/spring-security/reference/reactive/getting-started.html)
- [Spring Security — ServerHttpSecurity API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Security — ServerHttpSecurity.FormLoginSpec API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.FormLoginSpec.html)
- [Spring Security — ServerHttpSecurity.HttpBasicSpec API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.HttpBasicSpec.html)
- [Spring Security — ServerHttpSecurity.ExceptionHandlingSpec API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.ExceptionHandlingSpec.html)
- [Spring Security — ServerAuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/ServerAuthenticationEntryPoint.html)
- [Spring Security — ServerAccessDeniedHandler API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/ServerAccessDeniedHandler.html)
- [Spring Security — ServerAuthenticationEntryPointFailureHandler API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationEntryPointFailureHandler.html)
- [Spring Security — Cross Site Request Forgery for WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Security — Reactive OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html)
- [Spring Boot — Security in Web Applications](https://docs.spring.io/spring-boot/reference/web/spring-security.html)
