# AuthenticationEntryPoint yêu cầu client cung cấp thông tin xác thực

> **Phạm vi:** Spring Security trên Servlet stack (`HttpSecurity`, `SecurityFilterChain`, `jakarta.servlet`), với cách cấu hình tương thích Spring Security 6.x / Spring Boot 3.x. Trong WebFlux, khái niệm tương ứng là `ServerAuthenticationEntryPoint` nhưng API và filter khác nhau.

## 1. Vấn đề cần giải quyết

Giả sử client gọi `GET /api/hello`, nhưng tài nguyên chỉ dành cho người dùng đã đăng nhập. Nếu request chưa mang thông tin xác thực hợp lệ, server cần **chỉ cho client cách bắt đầu xác thực**: trả HTTP `401 Unauthorized` kèm lời mời dùng HTTP Basic/Bearer, hoặc chuyển trình duyệt đến trang đăng nhập.

Trong Spring Security, **`AuthenticationEntryPoint` quyết định phản hồi mở đầu quá trình xác thực**. Tên “EntryPoint” dễ gây nhầm lẫn: nó không phải điểm bắt đầu toàn bộ security filter chain và **không tự kiểm tra mật khẩu, giải mã JWT hay cấp quyền truy cập**. Nó được gọi khi một request cần xác thực hoặc việc xác thực thất bại tại một luồng có sử dụng entry point.

Phân biệt ba trách nhiệm:

- **Authentication (xác thực):** người gọi là ai, chứng thực có hợp lệ không? Thường do authentication filter, `AuthenticationManager` và `AuthenticationProvider` đảm nhiệm.
- **Authorization (phân quyền):** danh tính đã xác thực có được truy cập tài nguyên không? Do các quy tắc `authorizeHttpRequests`, `AuthorizationManager`, method security… quyết định.
- **AuthenticationEntryPoint (khởi phát xác thực):** khi cần xác thực, phản hồi HTTP gì để client biết cần cung cấp hoặc bổ sung thông tin xác thực?

Ví dụ: API yêu cầu đăng nhập có thể đáp `401`; website dùng form login có thể đáp `302 Location: /login`. Một `AuthenticationEntryPoint` khác nhau có thể được chọn cho từng loại ứng dụng hoặc request.

## 2. Cơ chế với ExceptionTranslationFilter

`ExceptionTranslationFilter` nằm trong chuỗi security filter của Servlet, làm cầu nối giữa **ngoại lệ bảo mật** và **phản hồi HTTP**. Bộ lọc này không thực hiện chính sách phân quyền; nó xử lý `AuthenticationException` hoặc `AccessDeniedException` phát sinh trong phần còn lại của chain mà nó bao quanh.

Dòng xử lý điển hình khi truy cập một endpoint bảo vệ mà chưa đăng nhập:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant F as Security filters
    participant A as AuthorizationFilter
    participant E as ExceptionTranslationFilter
    participant P as AuthenticationEntryPoint
    C->>F: GET /api/hello (không credentials)
    F->>E: Tiếp tục filter chain
    E->>A: Kiểm tra quyền cho request
    A-->>E: AccessDeniedException (anonymous)
    E->>P: commence(request, response, exception)
    P-->>C: 401 + WWW-Authenticate (hoặc 302 login)
~~~

**Điểm quyết định của `ExceptionTranslationFilter`:**

1. Khi gặp `AuthenticationException`, nó bắt đầu quá trình xác thực qua `AuthenticationEntryPoint`.
2. Khi gặp `AccessDeniedException` và caller là anonymous (hoặc trường hợp mức xác thực hiện tại không đủ theo trust resolver), nó cũng có thể dùng `AuthenticationEntryPoint`: phải xác thực trước khi kiểm tra quyền tiếp.
3. Khi gặp `AccessDeniedException` từ người dùng đã xác thực đầy đủ nhưng thiếu quyền, nó chuyển sang `AccessDeniedHandler`, thông thường trả `403 Forbidden`.

Trước khi gọi entry point ở nhánh trên, filter xử lý bối cảnh bảo mật và có thể lưu request gốc qua `RequestCache` để quay lại sau khi đăng nhập. Việc lưu request **phụ thuộc cấu hình**; API stateless thường không cần lưu trong session.

**Giới hạn quan trọng:** `ExceptionTranslationFilter` chỉ bắt được ngoại lệ đi qua phạm vi `doFilter` của nó. Một filter xác thực đứng trước nó, chẳng hạn `BasicAuthenticationFilter`, có thể tự gọi entry point của filter đó khi credentials sai. Vì vậy, cấu hình lỗi xác thực của HTTP Basic đôi khi phải đặt ngay trong `httpBasic(...)`, thay vì giả định mọi lỗi đều đến từ `exceptionHandling(...)`.

## 3. Giao diện AuthenticationEntryPoint

Phương thức cốt lõi trên Servlet:

~~~java
void commence(HttpServletRequest request,
              HttpServletResponse response,
              AuthenticationException authException)
        throws IOException, ServletException;
~~~

Ý nghĩa từng tham số:

- `request`: request đang cố truy cập tài nguyên; có thể xem URI/method để chọn phản hồi phù hợp.
- `response`: nơi thiết lập status, header, content type và body hoặc chuyển hướng.
- `authException`: nguyên nhân khiến quá trình xác thực cần được khởi phát; **không nên trả nguyên văn** thông điệp nội bộ của ngoại lệ ra client.

Entry point được kỳ vọng viết phản hồi thích hợp để client có thể đăng nhập hoặc gửi thông tin xác thực. Nó **không gọi lại endpoint bảo vệ**, không sinh principal, không coi request là đã xác thực và không quyết định quyền của principal.

### Các cách triển khai thường gặp

| Cách xác thực | Entry point tiêu biểu | Phản hồi cho request chưa xác thực |
|---|---|---|
| HTTP Basic | `BasicAuthenticationEntryPoint` | `401`, thường có `WWW-Authenticate: Basic realm="..."` |
| Trang đăng nhập | `LoginUrlAuthenticationEntryPoint` | Redirect đến URL login, thường HTTP `302` |
| OAuth2 Resource Server/Bearer | `BearerTokenAuthenticationEntryPoint` | `401`, thử thách `WWW-Authenticate: Bearer` theo chuẩn Bearer |
| API cần status cố định | `HttpStatusEntryPoint` | Gửi status được cấu hình (ví dụ `401`), không tự thiết kế challenge |
| API có JSON lỗi riêng | Lambda/class triển khai `AuthenticationEntryPoint` | Tự thiết lập status, header và JSON theo hợp đồng API |

**Chọn theo giao thức xác thực thực tế.** Với HTTP Basic, `WWW-Authenticate` báo client sử dụng scheme Basic. Với Bearer, nên dùng entry point được Spring Security cung cấp sẵn để giữ đúng các header tham số lỗi theo chuẩn OAuth2; không trả “Basic” cho API chỉ chấp nhận Bearer.

## 4. 401 và 403: khác nhau ở đâu?

| Tình huống | Xử lý thường gặp | Ý nghĩa |
|---|---|---|
| Anonymous gọi tài nguyên `authenticated()` | Entry point: `401` hoặc redirect login | Cần bắt đầu xác thực |
| HTTP Basic có username/mật khẩu sai | Entry point cho HTTP Basic: `401` | Credentials không hợp lệ, phải xác thực lại |
| Bearer token hết hạn/không hợp lệ | Bearer entry point: thông thường `401` | Phải cung cấp token hợp lệ |
| Đã đăng nhập nhưng thiếu `ROLE_ADMIN` | `AccessDeniedHandler`: `403` | Đã biết danh tính, nhưng không có quyền |
| Endpoint `permitAll()` | Trả phản hồi từ ứng dụng | Không cần challenge |
| Request bị CSRF protection từ chối | Thường `403` | Là lỗi bảo vệ CSRF; không đồng nghĩa với mật khẩu sai |

**Chú ý:** `401 Unauthorized` trên HTTP về bản chất thường có nghĩa là “chưa được xác thực hợp lệ”, còn `403 Forbidden` là từ chối truy cập. Không suy từ tên status `Unauthorized` rằng đây là lỗi thiếu role. Một số scheme hoặc entry point chuyên biệt có cách phản hồi khác; cần đọc cấu hình thực tế.

Với trang web, `302 /login` có thể đúng cho anonymous request. Với API REST, redirect HTML login thường làm client khó xử lý và có thể che giấu nguyên nhân lỗi. Hãy xác định API client mong `401`/challenge hay trình duyệt mong login page.

## 5. Ví dụ chạy được: API trả 401 JSON + HTTP Basic

Ví dụ này dùng **Java 17, Spring Boot 3.5.16 (Spring Security 6.x), Maven**. Mục đích là quan sát `AuthenticationEntryPoint`; đây là demo tối giản, không phải mẫu quản lý tài khoản production.

Cấu trúc file:

~~~text
security-entrypoint-demo/
├── pom.xml
└── src/main/java/com/example/securitydemo/
    ├── SecurityDemoApplication.java
    ├── SecurityConfig.java
    └── DemoController.java
~~~

### 5.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>security-entrypoint-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

### 5.2. SecurityDemoApplication.java

~~~java
package com.example.securitydemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityDemoApplication.class, args);
    }
}
~~~

### 5.3. SecurityConfig.java

~~~java
package com.example.securitydemo;

import java.nio.charset.StandardCharsets;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    AuthenticationEntryPoint apiEntryPoint() {
        return (request, response, authException) -> {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setHeader(
                    HttpHeaders.WWW_AUTHENTICATE, "Basic realm=\"demo\"");
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            response.getWriter().write(
                    "{\"error\":\"unauthorized\","
                    + "\"message\":\"Authentication is required\"}");
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AuthenticationEntryPoint apiEntryPoint)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().permitAll()
            )
            .httpBasic(basic ->
                basic.authenticationEntryPoint(apiEntryPoint)
            )
            .exceptionHandling(ex ->
                ex.authenticationEntryPoint(apiEntryPoint)
            )
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            );

        return http.build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                    .password("{noop}pass123")
                    .roles("USER")
                    .build()
        );
    }
}
~~~

**Giải thích cấu hình:**

- `/public` là URL không cần login, `/api/hello` cần `Authentication` hợp lệ, `/api/admin` cần `ROLE_ADMIN`.
- `apiEntryPoint()` đưa ra HTTP `401`, header challenge Basic và body JSON ổn định. Nó **không** xử lý kiểm tra mật khẩu.
- `.exceptionHandling(...authenticationEntryPoint(...))` xử lý trường hợp request chưa đăng nhập bị bộ lọc phân quyền từ chối.
- `.httpBasic(...authenticationEntryPoint(...))` sử dụng **cùng entry point** cho lỗi phát sinh ngay khi HTTP Basic authentication filter kiểm tra credentials; nếu không cấu hình, đường lỗi này có thể dùng handler riêng.
- `SessionCreationPolicy.STATELESS` để request xác thực độc lập và không dùng session làm kho lưu `SecurityContext`; HTTP Basic gửi credentials cho mỗi request.
- `{noop}` và password `pass123` chỉ để demo có thể chạy; hệ thống thật phải dùng password encoder phù hợp, bảo vệ secret và **HTTPS**.
- Ví dụ **giữ CSRF protection mặc định**. Các request kiểm tra đều là `GET`; nếu bổ sung endpoint thay đổi trạng thái (`POST`, `PUT`, `DELETE`), cần cấu hình CSRF cho mô hình client tương ứng. Không tắt CSRF chỉ vì API dùng HTTP Basic: trình duyệt có thể tự gửi Basic credentials.

### 5.4. DemoController.java

~~~java
package com.example.securitydemo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/hello")
    public String hello(Authentication authentication) {
        return "hello " + authentication.getName();
    }

    @GetMapping("/api/admin")
    public String admin() {
        return "admin";
    }
}
~~~

### 5.5. Chạy và kiểm chứng

Trong thư mục có `pom.xml`, dùng JDK 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

Mở terminal khác để thử:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/hello
curl -i -u alice:wrong http://localhost:8080/api/hello
curl -i -u alice:pass123 http://localhost:8080/api/hello
curl -i -u alice:pass123 http://localhost:8080/api/admin
~~~

Kết quả cần kiểm tra (rút gọn các header phụ thuộc môi trường):

| Request | HTTP status | Body / dấu hiệu chính |
|---|---|---|
| `GET /public` | `200` | `public` |
| `GET /api/hello` không credentials | `401` | `WWW-Authenticate: Basic realm="demo"` và JSON `unauthorized` |
| `GET /api/hello` với `alice:wrong` | `401` | Cũng qua entry point đã gắn cho HTTP Basic |
| `GET /api/hello` với `alice:pass123` | `200` | Chính xác `hello alice` |
| `GET /api/admin` với `alice:pass123` | `403` | Đã xác thực nhưng thiếu `ROLE_ADMIN`; không phải 401 |

**Body JSON của hai trường hợp 401** do `apiEntryPoint()` tạo:

~~~json
{"error":"unauthorized","message":"Authentication is required"}
~~~

Header `Content-Type` có thể thêm charset; thứ tự header, `Date`, `Content-Length`… tùy servlet container. Với `403`, chỉ khẳng định status; không phụ thuộc body lỗi mặc định của Spring Boot.

Điều quan trọng trong thí nghiệm này là hai lỗi `401` có **đường vào khác nhau**: request không credentials được phân quyền phát hiện và kích hoạt `ExceptionTranslationFilter`; credentials Basic sai được `BasicAuthenticationFilter` phát hiện rồi gọi entry point được cấu hình cho Basic. Cả hai có phản hồi thống nhất nhờ cùng sử dụng một bean.

## 6. Cùng mục tiêu, các kiểu challenge khác nhau

### HTTP Basic — yêu cầu client gửi username/password

Một response mẫu:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="demo"
Content-Type: application/json;charset=UTF-8

{"error":"unauthorized","message":"Authentication is required"}
~~~

Sau challenge, client có thể gọi lại với:

~~~http
GET /api/hello HTTP/1.1
Authorization: Basic <base64(username:password)>
~~~

Base64 **chỉ là biểu diễn**, không phải mã hóa bảo mật. Giao thức phải chạy qua HTTPS để tránh lộ credentials trên đường truyền. Không ghi giá trị header này vào log.

### Form login — đưa browser tới trang đăng nhập

`LoginUrlAuthenticationEntryPoint` thường phản hồi với redirect `302` tới trang đăng nhập đã cấu hình, ví dụ `Location: /login`. Người dùng nhập credentials trong form; các filter xử lý login mới xác thực. Entry point chỉ đưa họ đến chỗ nhập credentials. Sau khi xác thực thành công, saved request có thể giúp quay lại URL cũ nếu có cấu hình `RequestCache` tương ứng.

### OAuth2 Resource Server — yêu cầu Bearer token

Với API dùng OAuth2 access token, HTTP challenge là scheme `Bearer`, không phải `Basic`. Request thường mang header `Authorization: Bearer <token>`. Spring Security cung cấp `BearerTokenAuthenticationEntryPoint` để trả `WWW-Authenticate: Bearer` và mô tả lỗi phù hợp khi token không hợp lệ.

Ví dụ minh họa một lỗi token:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Các tham số challenge thực tế phụ thuộc nguyên nhân và cấu hình. Không tự đưa toàn bộ exception hoặc token vào response. Với OAuth2, lỗi **token hợp lệ nhưng thiếu scope** có thể là `403` và được xử lý theo đường từ chối quyền; đừng mặc định mọi lỗi Bearer là 401.

## 7. Khi nào cần cấu hình AuthenticationEntryPoint riêng?

Một entry point tùy biến hữu ích khi API có hợp đồng lỗi nhất quán, chẳng hạn JSON gồm `error`, `message` và trace ID, trong khi vẫn giữ status/header theo giao thức xác thực. Có thể dùng lambda `AuthenticationEntryPoint` như ví dụ, hoặc tạo class riêng nếu cần tái sử dụng.

Khi ứng dụng có cả website và API, hãy phân biệt các request: browser thường cần redirect login, API client thường cần `401` rõ ràng. Có thể cấu hình các `SecurityFilterChain` riêng bằng `securityMatcher` và thứ tự phù hợp, hoặc chọn entry point bằng `defaultAuthenticationEntryPointFor` / `DelegatingAuthenticationEntryPoint` với `RequestMatcher`. Không vô tình đưa API vào cơ chế redirect chỉ vì app cũng có form login.

**Phân biệt các hook gần tên:**

- `AuthenticationEntryPoint`: bắt đầu xác thực cho một request vào tài nguyên cần bảo vệ.
- `AuthenticationFailureHandler`: xử lý thất bại của một lần đăng nhập do filter đăng nhập (ví dụ POST form login) chủ động thực hiện.
- `AccessDeniedHandler`: xử lý từ chối quyền khi caller đã xác thực nhưng không được phép truy cập.
- `AuthenticationProvider`: kiểm tra credentials và trả kết quả xác thực; không chịu trách nhiệm thiết kế HTTP error body.

## 8. Lỗi thường gặp và cách chẩn đoán

1. **Trả 403 cho mọi request anonymous:** kiểm tra có dùng nhầm `AccessDeniedHandler` hoặc entry point chuyên trả 403 không; xem điều kiện anonymous, request matcher và authentication scheme.
2. **Trả 401 cho người dùng đã đăng nhập nhưng thiếu role:** xem `hasRole("ADMIN")` tương ứng authority `ROLE_ADMIN`; đường từ chối quyền thông thường dùng `AccessDeniedHandler`.
3. **API nhận HTML trang login thay vì JSON:** ứng dụng đang dùng form login hoặc entry point áp dụng sai phạm vi; tách cấu hình API/browser.
4. **Có Basic credentials sai nhưng body 401 không theo mẫu JSON:** `BasicAuthenticationFilter` có thể dùng entry point được cấu hình riêng. Kiểm tra cả `httpBasic(...)` lẫn `exceptionHandling(...)`.
5. **Không thấy entry point chạy:** ngoại lệ có thể bị xử lý ở filter khác, request được `permitAll`, hay response đã được commit; xem security filter chain và bật log DEBUG có chọn lọc.
6. **POST bị 403 dù không đăng nhập:** có thể do CSRF filter chặn trước logic authorization. Kiểm tra CSRF token/mô hình credentials trước khi quy cho entry point.
7. **Chỉ trả `401` mà quên challenge:** nếu dùng Basic/Bearer, cần bảo toàn yêu cầu `WWW-Authenticate` của scheme; handler mặc định thường an toàn hơn việc tự viết thiếu header.
8. **Rò rỉ dữ liệu nhạy cảm qua lỗi:** tránh nhúng `authException.getMessage()`, stack trace, mật khẩu, token hoặc chi tiết cấu hình vào response. Log server có kiểm soát và dùng thông điệp client ổn định.
9. **Dùng Servlet API cho WebFlux:** WebFlux dùng `ServerAuthenticationEntryPoint`, `ServerHttpSecurity` và reactive security filters; không thể thay trực tiếp `HttpServletResponse` vào luồng reactive.

Để quan sát dòng thực thi, có thể bật `logging.level.org.springframework.security=DEBUG` trong môi trường phát triển và xem filter chain/rule bị chặn. Không bật logging nhạy cảm bừa bãi trên production; không log header `Authorization`.

## 9. Tự kiểm tra kiến thức

- Anonymous gọi `GET /api/admin`: vì sao request thường đến `AuthenticationEntryPoint` trước khi đánh giá một principal thật sự có `ROLE_ADMIN`?
- `alice` đăng nhập thành công nhưng chỉ có `ROLE_USER`: vì sao kết quả là `403` thay vì challenge Basic?
- Trong ví dụ, nếu chỉ cấu hình `exceptionHandling().authenticationEntryPoint(...)` mà bỏ cấu hình ở `httpBasic()`, đường xử lý nào có thể cho response khác?
- Vì sao entry point của Bearer token không nên trả `WWW-Authenticate: Basic`?
- Vì sao việc thay entry point không thể biến mật khẩu sai thành đúng hoặc cấp thêm quyền cho người dùng?

**Tiêu chí nắm vững:** giải thích được **ai phát hiện lỗi xác thực/phân quyền**, **ai chuyển lỗi thành phản hồi HTTP**, **entry point yêu cầu client làm gì tiếp**, và chứng minh bằng bốn request `200`, `401`, `401`, `403` ở ví dụ trên.

## Tài liệu chính thức

- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Handling Security Exceptions / ExceptionTranslationFilter](https://docs.spring.io/spring-security/reference/servlet/architecture.html#servlet-exceptiontranslationfilter)
- [Spring Security — AuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/AuthenticationEntryPoint.html)
- [Spring Security — OAuth2 Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html)
- [Spring Security — CSRF on Servlet](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
