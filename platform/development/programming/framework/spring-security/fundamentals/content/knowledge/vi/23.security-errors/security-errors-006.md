# Thành phần xử lý lỗi tương ứng trong ứng dụng reactive (Spring Security WebFlux)

## 1. Bối cảnh và mục tiêu

Trong ứng dụng Spring Security chạy trên **Spring WebFlux**, lỗi bảo mật được xử lý qua các `WebFilter` và `ServerWebExchange`, thay cho `Filter`, `HttpServletRequest` và `HttpServletResponse` của Servlet/MVC. Khi chuyển cấu hình từ MVC sang WebFlux, cần dùng đúng những **giao diện và bộ lọc reactive**; các lớp xử lý lỗi của Servlet không thể gắn trực tiếp vào `SecurityWebFilterChain`.

Sau bài này, bạn có thể: tìm thành phần reactive tương ứng với cơ chế xử lý lỗi bảo mật của Servlet; phân biệt lỗi cần xác thực (401) và lỗi thiếu quyền (403); cấu hình phản hồi trong `ServerHttpSecurity`; và nhận biết trường hợp lỗi xảy ra ngay trong bộ lọc xác thực.

## 2. Bảng đối chiếu Servlet ↔ Reactive

| Vai trò | Servlet/MVC | Spring Security WebFlux |
| --- | --- | --- |
| Chuỗi bảo mật | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Bộ lọc điều phối chuỗi | `FilterChainProxy` | `WebFilterChainProxy` |
| Dịch ngoại lệ bảo mật thành phản hồi HTTP | `ExceptionTranslationFilter` | `ExceptionTranslationWebFilter` |
| Khởi động yêu cầu xác thực khi chưa đăng nhập | `AuthenticationEntryPoint` | `ServerAuthenticationEntryPoint` |
| Xử lý người đã xác thực nhưng không đủ quyền | `AccessDeniedHandler` | `ServerAccessDeniedHandler` |
| Xử lý một lần đăng nhập thất bại tại bộ lọc xác thực | `AuthenticationFailureHandler` | `ServerAuthenticationFailureHandler` |
| Trả mã trạng thái khi cần xác thực | `HttpStatusEntryPoint` | `HttpStatusServerEntryPoint` |
| Trả mã trạng thái khi bị từ chối quyền | `HttpStatusAccessDeniedHandler` | `HttpStatusServerAccessDeniedHandler` |
| Xác thực HTTP Basic | `BasicAuthenticationFilter` | `AuthenticationWebFilter` được cấu hình cho HTTP Basic |
| Bộ lọc quyết định quyền truy cập HTTP | `AuthorizationFilter` / `FilterSecurityInterceptor` (tùy cấu hình) | `AuthorizationWebFilter` |

**Ba thành phần trung tâm của chủ đề:**

- `ExceptionTranslationWebFilter`: quan sát các lỗi bảo mật từ chuỗi xử lý phía sau và chọn cách trả lời phù hợp. Nó **không tự đưa ra quyết định phân quyền**; quyết định đó thuộc thành phần ủy quyền như `AuthorizationWebFilter`.
- `ServerAuthenticationEntryPoint`: giao diện hàm `Mono<Void> commence(ServerWebExchange exchange, AuthenticationException ex)`. Nó yêu cầu client xác thực, chẳng hạn trả 401, gửi `WWW-Authenticate` hoặc chuyển hướng đến trang đăng nhập, tùy cơ chế xác thực.
- `ServerAccessDeniedHandler`: giao diện hàm `Mono<Void> handle(ServerWebExchange exchange, AccessDeniedException ex)`. Trường hợp điển hình là người dùng đã đăng nhập nhưng thiếu quyền, trả 403.

Đây là các API reactive: kết quả `Mono<Void>` biểu thị việc ghi và hoàn tất phản hồi theo cơ chế bất đồng bộ. Không gọi `subscribe()` hoặc `block()` thủ công trong handler để “ép” phản hồi hoàn thành.

## 3. Khi nào 401, khi nào 403?

| Trạng thái request | Ý nghĩa | Hướng xử lý thông thường |
| --- | --- | --- |
| Chưa cung cấp thông tin xác thực, truy cập tài nguyên bắt buộc đăng nhập | Chưa được xác thực | `ServerAuthenticationEntryPoint` → thường **401** đối với API |
| Gửi thông tin xác thực sai/hết hạn | Xác thực thất bại | Bộ lọc xác thực có thể gọi `ServerAuthenticationFailureHandler` → thường **401** |
| Đã xác thực, nhưng thiếu vai trò/quyền truy cập | Bị từ chối ủy quyền | `ServerAccessDeniedHandler` → thường **403** |
| Anonymous truy cập tài nguyên yêu cầu vai trò cao hơn | Chưa được xác thực để kiểm tra quyền | Bộ dịch ngoại lệ thường gọi entry point, thường **401** thay vì trả 403 |
| Request thay đổi dữ liệu có CSRF token sai/thiếu (khi CSRF được bật) | Vi phạm quy tắc CSRF | Có thể tạo `AccessDeniedException` và **403**, dù người dùng có tài khoản hợp lệ |

**401 Unauthorized** ở HTTP thực chất báo rằng request cần thông tin xác thực hợp lệ; tên mã dễ gây hiểu nhầm. **403 Forbidden** báo rằng server hiểu request nhưng không cho phép thực hiện. Không phải mọi ứng dụng đều trả hai mã này nguyên dạng: cấu hình form login cho trình duyệt có thể chuyển hướng **302** đến trang đăng nhập; Bearer-token API còn có các yêu cầu về header `WWW-Authenticate`.

Ví dụ: `GET /admin` yêu cầu `ROLE_ADMIN`. Không gửi token/mật khẩu thì cần xác thực; đã đăng nhập bằng tài khoản chỉ có `ROLE_USER` thì bị từ chối quyền. `hasRole("ADMIN")` tự xét authority `ROLE_ADMIN`; không truyền chuỗi `ROLE_ADMIN` vào `hasRole`.

## 4. Luồng xử lý trong chuỗi reactive

`SecurityWebFilterChain` chứa các `WebFilter` đã được cấu hình từ `ServerHttpSecurity`. Khi request đi qua bước kiểm tra quyền:

1. `AuthorizationWebFilter` xét chính sách như `permitAll()`, `authenticated()`, `hasRole()`. Nếu từ chối, luồng reactive có thể phát `AccessDeniedException`.
2. `ExceptionTranslationWebFilter` bắt ngoại lệ bảo mật trong phần chuỗi mà nó bao quanh. Với người dùng chưa xác thực/anonymous, nó điều hướng sang `ServerAuthenticationEntryPoint`; với người đã xác thực nhưng thiếu quyền, nó gọi `ServerAccessDeniedHandler`.
3. Handler đặt status/header/body vào `exchange.getResponse()` rồi trả `Mono<Void>` biểu diễn thao tác hoàn tất phản hồi.

```text
Request
   │
   ▼
WebFilterChainProxy → SecurityWebFilterChain
   │
   ├─ Xác thực (nếu có credentials) ── thất bại
   │                                    └─ ServerAuthenticationFailureHandler
   ▼
Kiểm tra quyền (AuthorizationWebFilter)
   │
   ├─ Được phép ─────────────────────────► Controller / Handler
   │
   └─ AccessDeniedException
          │
          ▼
   ExceptionTranslationWebFilter
          ├─ Chưa xác thực ───────────────► ServerAuthenticationEntryPoint
          └─ Đã xác thực, thiếu quyền ────► ServerAccessDeniedHandler
```

**Phân biệt hai đường lỗi quan trọng:** `ExceptionTranslationWebFilter` xử lý ngoại lệ được lan truyền tới nó từ phần chuỗi bảo vệ; còn `AuthenticationWebFilter` có **đường xử lý thất bại riêng** khi nó chủ động kiểm tra credentials. `ServerAuthenticationFailureHandler#onAuthenticationFailure(WebFilterExchange, AuthenticationException)` không đồng nhất với `ServerAuthenticationEntryPoint#commence(ServerWebExchange, AuthenticationException)`. Có thể dùng `ServerAuthenticationEntryPointFailureHandler` để chuyển tiếp một lỗi đăng nhập sang entry point, nhưng hai hợp đồng API vẫn khác nhau.

## 5. Cấu hình một ví dụ chạy được với Java 17

Ví dụ dùng Spring Boot **3.5.7**, Spring WebFlux và Spring Security, cấu hình HTTP Basic để dễ quan sát mã 401/403. Chỉ dùng `spring-boot-starter-webflux` cho tầng web; tránh thêm `spring-boot-starter-web` vì sẽ làm thay đổi loại ứng dụng mà Boot chọn khi cả hai stack có mặt.

**Tập tin `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>reactive-error-demo</artifactId>
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
```

**Tập tin `src/main/java/demo/ReactiveErrorDemoApplication.java`:**

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.HttpStatusServerEntryPoint;
import org.springframework.security.web.server.authorization.HttpStatusServerAccessDeniedHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ReactiveErrorDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveErrorDemoApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/admin").hasRole("ADMIN")
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .exceptionHandling(ex -> ex
                        .authenticationEntryPoint(
                                new HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED))
                        .accessDeniedHandler(
                                new HttpStatusServerAccessDeniedHandler(HttpStatus.FORBIDDEN)))
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails demoUser = User.withUsername("demo")
                .password("{noop}demo123")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(demoUser);
    }

    @RestController
    static class DemoController {
        @GetMapping("/public")
        String publicEndpoint() {
            return "public";
        }

        @GetMapping("/private")
        String privateEndpoint() {
            return "private";
        }

        @GetMapping("/admin")
        String adminEndpoint() {
            return "admin";
        }
    }
}
```

Điểm cần hiểu trong cấu hình:

- `authorizeExchange` đặt luật theo thứ tự: public, admin, rồi các đường dẫn còn lại. Tài khoản `demo` có `ROLE_USER` nên truy cập được `/private`, nhưng không được `/admin`.
- `httpBasic(...)` bật xác thực HTTP Basic; `formLogin(...disable)` giúp ví dụ API không chuyển hướng sang trang login.
- `exceptionHandling(...)` đăng ký hai handler reactive. `HttpStatusServerEntryPoint` và `HttpStatusServerAccessDeniedHandler` là các triển khai có sẵn, phù hợp khi chỉ muốn trả status HTTP.
- `"{noop}demo123"` **chỉ để minh họa dễ chạy**; không lưu mật khẩu dạng rõ trong hệ thống thật. Hãy dùng bộ mã hóa mật khẩu phù hợp và kho người dùng an toàn.
- Ví dụ dùng GET nên không cần thay đổi mặc định CSRF. Với thao tác POST/PUT/DELETE từ trình duyệt dùng cookie hoặc Basic Auth, cần xem xét bảo vệ CSRF riêng; đừng vô hiệu hóa CSRF chỉ để một request thử nghiệm chạy được.

**Biên dịch và khởi động** (Java 17+, Maven, chạy tại thư mục có `pom.xml`):

```bash
mvn -q -DskipTests package
java -jar target/reactive-error-demo-0.0.1-SNAPSHOT.jar
```

**Thử HTTP ở một terminal khác:**

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/private
curl -i -u demo:demo123 http://localhost:8080/private
curl -i -u demo:demo123 http://localhost:8080/admin
curl -i -u demo:wrong http://localhost:8080/private
```

| Lệnh | Status mong đợi | Ý nghĩa |
| --- | --- | --- |
| `GET /public` không credentials | `200 OK`, body `public` | Endpoint công khai |
| `GET /private` không credentials | `401 Unauthorized` | Cần xác thực |
| `GET /private` với `demo:demo123` | `200 OK`, body `private` | Đã xác thực và đủ quyền |
| `GET /admin` với `demo:demo123` | `403 Forbidden` | Đã xác thực, thiếu `ROLE_ADMIN` |
| `GET /private` với mật khẩu sai | `401 Unauthorized` | Lỗi xác thực tại bộ lọc |

Chú ý: `curl -i` hiển thị cả header, status và body. Một số header có thể thay đổi theo cơ chế xác thực và phiên bản thư viện; hãy kiểm tra **mã trạng thái** và không giả định mọi response 401 đều có cùng body hoặc được tạo bởi cùng một handler.

## 6. Khi API cần trả JSON lỗi tùy chỉnh

Các lớp `HttpStatusServerEntryPoint` và `HttpStatusServerAccessDeniedHandler` chỉ giải quyết status. Để thống nhất response JSON cho API, có thể triển khai hai giao diện bằng lambda reactive. Ví dụ dưới đây là **một tập tin Java độc lập** cung cấp hai factory handler; dùng nó thay cho hai đối tượng `HttpStatus...` ở mục 5.

**`src/main/java/demo/SecurityErrorResponses.java`:**

```java
package demo;

import java.nio.charset.StandardCharsets;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authorization.ServerAccessDeniedHandler;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

public final class SecurityErrorResponses {
    private SecurityErrorResponses() {}

    public static ServerAuthenticationEntryPoint authenticationEntryPoint() {
        return (exchange, exception) ->
                send(exchange, HttpStatus.UNAUTHORIZED, "UNAUTHENTICATED");
    }

    public static ServerAccessDeniedHandler accessDeniedHandler() {
        return (exchange, exception) ->
                send(exchange, HttpStatus.FORBIDDEN, "ACCESS_DENIED");
    }

    private static Mono<Void> send(
            ServerWebExchange exchange, HttpStatus status, String code) {
        var response = exchange.getResponse();
        response.setStatusCode(status);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);

        byte[] bytes = ("{\"error\":\"" + code + "\"}")
                .getBytes(StandardCharsets.UTF_8);
        return response.writeWith(
                Mono.just(response.bufferFactory().wrap(bytes)));
    }
}
```

Thay riêng đoạn đăng ký handler trong `securityWebFilterChain(...)` bằng:

```java
.exceptionHandling(ex -> ex
        .authenticationEntryPoint(SecurityErrorResponses.authenticationEntryPoint())
        .accessDeniedHandler(SecurityErrorResponses.accessDeniedHandler()))
```

Khi nhánh entry point được dùng, JSON trả về là `{"error":"UNAUTHENTICATED"}` với status 401; khi nhánh access-denied được dùng, JSON trả về là `{"error":"ACCESS_DENIED"}` với status 403. **Không đảm bảo** rằng mọi lần nhập sai mật khẩu đều đi qua entry point này: `AuthenticationWebFilter` có `ServerAuthenticationFailureHandler` riêng. Muốn áp cùng format cho lỗi đăng nhập trực tiếp, phải cấu hình failure handler thích hợp cho cơ chế xác thực cụ thể.

Trong production, cân nhắc chuẩn phản hồi lỗi của API, mã lỗi ổn định và logging phía server. Không đưa stack trace, mật khẩu, token hoặc thông tin nội bộ vào JSON gửi cho client. Trước khi ghi body, response chưa được commit; handler không được cố ghi lần thứ hai sau khi response đã hoàn tất.

## 7. Các trường hợp cần xử lý đúng cơ chế

### Form login và HTTP Basic

Ứng dụng trình duyệt với `formLogin` có thể dùng `RedirectServerAuthenticationEntryPoint` để chuyển hướng đến trang đăng nhập, thay vì 401 JSON. HTTP Basic có `HttpBasicServerAuthenticationEntryPoint` và có thể cần header `WWW-Authenticate: Basic ...`. Ví dụ cấu hình JSON/status trong mục 5 dành cho API demo; đừng áp một status-only entry point cho mọi ứng dụng mà bỏ qua hợp đồng xác thực của client.

### OAuth2 Resource Server (Bearer token)

Với JWT hoặc opaque token, Spring Security có `BearerTokenServerAuthenticationEntryPoint` và `BearerTokenServerAccessDeniedHandler`. Các implementation này giúp sinh phản hồi Bearer phù hợp, bao gồm `WWW-Authenticate` khi cần. Đối với token không hợp lệ/hết hạn, thông tin lỗi có thể nằm trong header theo giao thức. Nếu thay bằng handler JSON tự viết, phải bảo toàn các yêu cầu tương ứng của RFC 6750; không tự ý loại bỏ challenge hoặc làm lộ chi tiết nhạy cảm.

### Method security và context reactive

Khi dùng `@EnableReactiveMethodSecurity` và `@PreAuthorize`, ngoại lệ từ việc kiểm tra quyền ở tầng phương thức cũng có thể lan ra chuỗi HTTP để xử lý. Nếu một tác vụ chạy ngoài HTTP request, không có `ServerWebExchange` để áp dụng các handler WebFlux này; hãy xử lý lỗi theo biên của tác vụ. Security context reactive được truyền trong Reactor `Context`, không dựa vào việc đọc `ThreadLocal` như trong luồng đồng bộ truyền thống.

### Lỗi ứng dụng không phải lỗi bảo mật

`ExceptionTranslationWebFilter` không phải bộ xử lý tổng quát cho mọi lỗi. Ví dụ, lỗi validate dữ liệu, `ResponseStatusException` do controller ném ra, 404 hoặc 500 thuộc tầng xử lý lỗi WebFlux (chẳng hạn `@RestControllerAdvice` / `@ExceptionHandler`, `WebExceptionHandler`, `ErrorWebExceptionHandler` theo ngữ cảnh). Không trộn tất cả thành 401/403; đừng dùng một `@ExceptionHandler(Exception.class)` để vô tình che lấp ngữ nghĩa lỗi bảo mật.

## 8. Những lỗi triển khai thường gặp

1. **Sao chép mã Servlet sang WebFlux:** import `AuthenticationEntryPoint` hoặc `AccessDeniedHandler` từ các package servlet, dùng `HttpSecurity` / `HttpServletResponse` trong bean WebFlux. Cách đúng là `ServerHttpSecurity` cùng các giao diện có tiền tố `Server...`.
2. **Coi mọi `AccessDeniedException` đều là 403:** request anonymous vào endpoint cần đăng nhập thường được chuyển sang entry point (401 hoặc redirect); phân biệt danh tính hiện tại.
3. **Nhầm thất bại đăng nhập với thiếu quyền:** mật khẩu sai ở `AuthenticationWebFilter` khác với người đã đăng nhập nhưng bị `AuthorizationWebFilter` từ chối. Cần kiểm tra handler đúng vị trí.
4. **Chặn luồng reactive:** dùng `block()`, `Thread.sleep()`, thao tác I/O đồng bộ nặng, hoặc tự `subscribe()` trong handler có thể gây vấn đề về tài nguyên và thứ tự xử lý. Hãy trả lại `Mono<Void>`.
5. **Vô hiệu hóa CSRF/CORS để “sửa” 403:** trước tiên xác định lỗi do phân quyền, CSRF hay preflight CORS; mỗi loại có cơ chế giải quyết riêng.
6. **Thay Bearer handler không giữ `WWW-Authenticate`:** có thể phá hành vi client theo chuẩn OAuth2. Kiểm thử header, status và token invalid/expired/insufficient scope.
7. **Quên giới hạn chuỗi bảo mật:** với nhiều `SecurityWebFilterChain`, request chỉ áp dụng chuỗi phù hợp theo matcher và thứ tự; đặt handler vào sai chuỗi sẽ không có tác dụng.
8. **Đọc mỗi status để đoán nguyên nhân:** 403 cũng có thể đến từ CSRF; 401 có thể đến từ failure handler của cơ chế authentication. Bật log phù hợp và tái hiện kịch bản có/không credentials.

## 9. Checklist kiểm tra và câu hỏi tự luyện

- Request anonymous tới đường dẫn bắt buộc xác thực có đi đến entry point và trả status/challenge đúng loại client không?
- Request đã xác thực nhưng thiếu vai trò có đi đến access-denied handler và trả 403 không?
- Credentials sai có được xử lý bởi failure handler của bộ lọc xác thực không?
- Với Bearer token, header `WWW-Authenticate` có đúng khi token thiếu, sai hoặc không đủ scope không?
- Có vô tình ảnh hưởng đến CSRF, form login hoặc một `SecurityWebFilterChain` khác không?
- Handler có trả `Mono<Void>` và không tiết lộ thông tin nhạy cảm không?

**Tự trả lời:** (1) Vì sao `/admin` có thể trả 401 với khách anonymous nhưng 403 với `demo`? (2) Khi nhập sai mật khẩu Basic, vì sao không thể mặc định kết luận `ExceptionTranslationWebFilter` sinh response? (3) Khi đổi cơ chế từ HTTP Basic sang Bearer token, vì sao cần chú ý header challenge dù status vẫn là 401?

## 10. Tài liệu chính thức để tra cứu

- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [API — ExceptionTranslationWebFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/ExceptionTranslationWebFilter.html)
- [API — ServerHttpSecurity.ExceptionHandlingSpec](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.ExceptionHandlingSpec.html)
- [API — AuthenticationWebFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html)
- [Spring Security — CSRF for WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Security — Reactive OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html)
