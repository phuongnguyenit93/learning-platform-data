# ServerAuthenticationEntryPoint cho yêu cầu chưa được xác thực trong Spring Security reactive

## 1. Mục tiêu

Một REST API dùng Spring WebFlux có endpoint `GET /api/me` chỉ dành cho người đã đăng nhập. Khi request không có credentials, server cần yêu cầu xác thực, thường bằng HTTP **401 Unauthorized** cùng challenge phù hợp. Nếu website dùng form login, thay vì 401 JSON, browser có thể được **redirect** đến `/login`. Thành phần Spring Security reactive quyết định **cách khởi tạo phản hồi yêu cầu xác thực** chính là `ServerAuthenticationEntryPoint`.

Bài này giúp bạn:

1. Hiểu chức năng, vị trí và chữ ký reactive `commence(...)` của `ServerAuthenticationEntryPoint`.
2. Phân biệt request **chưa xác thực**, **đăng nhập sai**, **đã đăng nhập nhưng thiếu quyền** và **CSRF bị từ chối**.
3. Cấu hình `ServerHttpSecurity.exceptionHandling(...).authenticationEntryPoint(...)` đúng trên `SecurityWebFilterChain`.
4. Viết entry point JSON 401 an toàn nhưng vẫn giữ `WWW-Authenticate` theo HTTP Basic/Bearer protocol.
5. Phân biệt `ServerAuthenticationEntryPoint` với `ServerAuthenticationFailureHandler`, `ServerAccessDeniedHandler`, `AuthenticationWebFilter` và `ExceptionTranslationWebFilter`.
6. Chạy ví dụ Java 17+ và xác nhận kết quả qua `curl`, bao gồm public, anonymous, sai password và thiếu role.
7. Chọn cách phản hồi cho API JSON, trình duyệt form login và OAuth2 Resource Server.

**Điểm cốt lõi:** entry point **không thực hiện kiểm tra mật khẩu, không cấp role, không phát hành token và không xác thực principal**. Nó hoàn tất phản hồi để client biết cần làm gì để xác thực.

## 2. Vị trí trong chuỗi WebFilter

~~~text
HTTP request
    |
    v
SecurityWebFilterChain
    |
    v
AuthenticationWebFilter / filter xác thực phù hợp
    |
    +-- Không có credentials thuộc cơ chế này
    |       -> converter có thể trả Mono.empty()
    |       -> filter không thử xác thực; tiếp tục chain
    |
    +-- Có credentials nhưng sai
    |       -> ReactiveAuthenticationManager phát lỗi
    |       -> ServerAuthenticationFailureHandler
    |
    +-- Credentials đúng
    |       -> Authentication được xác thực trong Reactor Context
    |
    v
AuthorizationWebFilter (và có thể method security downstream)
    |
    +-- permitAll() --------------------> Controller / handler
    |
    +-- chưa được xác thực mà URL cần authenticated()
    |       -> AccessDeniedException
    |       -> ExceptionTranslationWebFilter
    |       -> ServerAuthenticationEntryPoint.commence(...)
    |
    +-- đã xác thực nhưng thiếu role/authority
            -> AccessDeniedException
            -> ExceptionTranslationWebFilter
            -> ServerAccessDeniedHandler
~~~

Đây là **sơ đồ trách nhiệm**, không mô phỏng chính xác mọi operator nội bộ. Một số lỗi từ filter authentication đi qua failure handler trước khi tới authorization; lỗi method security ngoài HTTP cũng không tự nhiên có HTTP response.

Theo contract Spring Security WebFlux, `ExceptionTranslationWebFilter` xử lý truy cập bị từ chối ở downstream. Khi principal không được coi là đã xác thực, nó khởi động quy trình yêu cầu xác thực qua entry point; khi principal hợp lệ nhưng thiếu quyền, nó dùng access-denied handler.

### 2.1. Chữ ký API

~~~java
// Chữ ký rút gọn từ Spring Security reactive:
@FunctionalInterface
public interface ServerAuthenticationEntryPoint {
    Mono<Void> commence(
            ServerWebExchange exchange,
            AuthenticationException exception);
}
~~~

Đây là **trích đoạn API để học**, không phải source thay thế thư viện Spring. Import thực tế:

~~~java
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.security.core.AuthenticationException;
import reactor.core.publisher.Mono;
~~~

- `ServerWebExchange` cung cấp HTTP request/response cho reactive chain.
- `AuthenticationException` mô tả nguyên nhân phải bắt đầu cơ chế xác thực. Đừng suy ra từ nó rằng username/password đã sai; request có thể chưa gửi gì.
- `Mono<Void>` thông báo việc xử lý response hoàn tất; không trả `Authentication` hoặc `boolean`.
- Interface là functional interface nên có thể cài bằng lambda, method reference hoặc class riêng.

**Không dùng** Servlet `AuthenticationEntryPoint` (package `org.springframework.security.web`), với `HttpServletRequest` và `HttpServletResponse`. WebFlux cần `ServerAuthenticationEntryPoint` thuộc `org.springframework.security.web.server`.

### 2.2. Reactive và Reactor Context

Khi xác thực thành công, `Authentication` được đưa vào `SecurityContext` của Reactor Context, thay vì dựa vào `ThreadLocal` servlet thông thường. Entry point được kích hoạt ở điểm phù hợp khi request chưa có danh tính đủ tin cậy. Một `AnonymousAuthenticationToken` có thể tồn tại, nhưng điều đó **không đồng nghĩa** được coi là user đã đăng nhập cho rule `authenticated()`.

## 3. 401, 403, redirect và login thất bại khác nhau

| Trường hợp | Ai thường xử lý? | Đầu ra ví dụ |
| --- | --- | --- |
| Anonymous gọi `/api/me` cần authenticated | `ExceptionTranslationWebFilter` → `ServerAuthenticationEntryPoint` | HTTP **401**, `WWW-Authenticate`, JSON |
| Client gửi HTTP Basic password sai | `AuthenticationWebFilter` → `ServerAuthenticationFailureHandler` | HTTP **401**, có thể cùng JSON và challenge |
| Đã login nhưng gọi URL đòi `ROLE_ADMIN` | `ServerAccessDeniedHandler` | HTTP **403 Forbidden** |
| Browser anonymous gọi `/web/home` | Redirect entry point | HTTP **302** sang `/login` |
| Browser gửi form sai password | Form-login failure handler | Redirect `/login?error` hoặc trang báo lỗi |
| POST thiếu CSRF token | `CsrfWebFilter` và CSRF access-denied handling | Thường HTTP **403** |
| Database hoặc IdP ngừng hoạt động | Error handling của xác thực/hệ thống | Theo chính sách lỗi, **không** mặc nhiên thành “sai mật khẩu” |

**Cùng 401 không chứng minh cùng nguồn lỗi.** Với request thiếu Authorization header, Basic converter có thể trả `Mono.empty()`; filter không thử đăng nhập và authorization sau đó đòi login. Với request có header Basic nhưng password sai, manager phát `BadCredentialsException` và failure handler xử lý.

### 3.1. Vì sao phải phân biệt entry point với failure handler?

`ServerAuthenticationEntryPoint` mang ý nghĩa **“phương thức nào sẽ yêu cầu client xác thực?”** còn `ServerAuthenticationFailureHandler` mang ý nghĩa **“làm gì khi một authentication attempt thất bại?”**.

Một ứng dụng có thể cấu hình entry point JSON cho anonymous route, nhưng password sai vẫn nhận body/status từ failure handler mặc định của HTTP Basic. Muốn bảo đảm JSON nhất quán, phải test **cả hai nhánh** và, nếu cần, nối failure handler đến cùng entry point bằng `ServerAuthenticationEntryPointFailureHandler`.

### 3.2. Vì sao 403 không nên đổi thành 401?

User đã đăng nhập có `ROLE_USER` nhưng thiếu `ROLE_ADMIN` thường phải nhận 403. Nếu cố trả 401, frontend có thể liên tục yêu cầu login lại dù password đúng; đó là sai nguyên nhân. Chỉ dùng entry point nếu cần authentication, còn authorization denial của principal hợp lệ nên qua `ServerAccessDeniedHandler`.

### 3.3. “Chưa có Authorization header” không phải lỗi ở endpoint public

`GET /public` gắn `permitAll()` phải có thể hoạt động không cần header. Entry point **không tự động chạy trên mọi request không có credentials**. Chỉ khi một bước bảo vệ yêu cầu authentication phù hợp mà request chưa đủ thì entry point mới cần bắt đầu phản hồi yêu cầu xác thực.

## 4. Các implementation có sẵn

Spring Security reactive cung cấp nhiều entry point:

| Class | Khi nào phù hợp | Kết quả điển hình |
| --- | --- | --- |
| `HttpBasicServerAuthenticationEntryPoint` | HTTP Basic | 401 + `WWW-Authenticate: Basic ...` |
| `BearerTokenServerAuthenticationEntryPoint` | OAuth2 Resource Server Bearer | 401 + `WWW-Authenticate: Bearer ...` theo RFC 6750 |
| `RedirectServerAuthenticationEntryPoint` | Browser và form login | Redirect tới URL đăng nhập, thường 302 |
| `HttpStatusServerEntryPoint` | Muốn trả riêng status | Status đã chọn; **không tự bảo đảm challenge cho Basic/Bearer** |
| `DelegatingServerAuthenticationEntryPoint` | Chọn entry point theo `ServerWebExchangeMatcher` | Chuyển tới delegate phù hợp |
| Custom lambda/class | API muốn body JSON, error envelope, header riêng | Tự định nghĩa trong `Mono<Void>` |

### 4.1. HTTP Basic

Ví dụ response khi server muốn Basic authentication:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="my-api"
Cache-Control: no-store
Content-Type: application/json

{"error":"unauthorized"}
~~~

Đây là **minh họa của custom JSON entry point**, không phải toàn bộ output mặc định của Spring Security. `WWW-Authenticate` là **authentication challenge**. HTTP 401 theo semantics giao thức cần ít nhất một challenge phù hợp; body JSON không thay thế header.

Spring Security có sẵn:

~~~java
HttpBasicServerAuthenticationEntryPoint basicEntryPoint =
        new HttpBasicServerAuthenticationEntryPoint();
basicEntryPoint.setRealm("my-api");
~~~

Đây là snippet trong class cấu hình. Import class từ `org.springframework.security.web.server.authentication`. Cách này hữu ích khi chỉ cần Basic challenge/realm mà không cần body JSON tùy chỉnh. `realm` không phải user/role và không chứng minh authentication thành công.

### 4.2. Bearer/OAuth2 Resource Server

API JWT/OAuth2 Bearer nên dùng `BearerTokenServerAuthenticationEntryPoint` thuộc `org.springframework.security.oauth2.server.resource.web.server`. Khi request thiếu token, header có thể là:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

Khi token đã được parser/decoder nhận diện nhưng không hợp lệ, Bearer entry point sử dụng `BearerTokenError` để gắn status/challenge/error theo **RFC 6750**. Không giả định mọi request thiếu token đều cần `invalid_token`.

Nếu code custom viết JSON cho Bearer API, phải bảo toàn challenge đúng cơ chế. Không trả `WWW-Authenticate: Basic` cho Bearer-only resource server; cũng không tự tuyên bố đã xác thực JWT nếu không có validator kiểm tra issuer, audience, signature và expiration theo thiết kế.

### 4.3. Trình duyệt và form login

Browser thường mong đợi:

~~~http
HTTP/1.1 302 Found
Location: /login
~~~

`RedirectServerAuthenticationEntryPoint` phù hợp form login, trong khi form authentication failure handler có thể redirect `/login?error`. Cần giữ CSRF cho form login và thao tác thay đổi trạng thái dùng cookie session.

Nếu client JavaScript `fetch` gọi API mà bị redirect sang HTML login, nó có thể tự theo redirect, nhận 200 HTML và lỗi khi gọi `response.json()`. Với API JSON, phản hồi 401 JSON trực tiếp dễ xử lý hơn. Tách security chain theo `/api/**` và `/web/**` nếu cần hai cơ chế authentication khác nhau.

### 4.4. Status-only entry point

`HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED)` có thể đặt status 401. Nhưng nếu dùng Basic/Bearer, chỉ đặt status mà không có challenge có thể sai chuẩn HTTP authentication. Chỉ chọn status-only khi threat model và giao thức client cho phép hoặc khi đã có phần khác đảm bảo header cần thiết.

## 5. Cách cấu hình trong ServerHttpSecurity

### 5.1. Entry point từ authorization

~~~java
http.exceptionHandling(errors ->
        errors.authenticationEntryPoint(myEntryPoint));
~~~

`myEntryPoint` là một biến/bean `ServerAuthenticationEntryPoint`; đây là snippet DSL, không phải ứng dụng độc lập. Method `ServerHttpSecurity.ExceptionHandlingSpec.authenticationEntryPoint(...)` quyết định cách yêu cầu authentication khi authorization cần điều đó.

### 5.2. Gắn cả failure handler cho HTTP Basic

~~~java
http.httpBasic(basic -> basic
        .authenticationEntryPoint(myEntryPoint)
        .authenticationFailureHandler(
                new ServerAuthenticationEntryPointFailureHandler(
                        myEntryPoint)));

http.exceptionHandling(errors ->
        errors.authenticationEntryPoint(myEntryPoint));
~~~

Snippet này cần một `myEntryPoint` đã định nghĩa. Ý nghĩa:

1. `httpBasic.authenticationEntryPoint` thay Basic entry point.
2. `ServerAuthenticationEntryPointFailureHandler` **chuyển lời gọi** từ một failure handler vào entry point, để credentials Basic sai có cùng mẫu phản hồi.
3. `exceptionHandling.authenticationEntryPoint` xử lý trường hợp authorization cần login.
4. Lỗi `AuthenticationServiceException` của nguồn xác thực có thể được adapter ném lại theo mặc định; không nên ép lỗi hạ tầng thành 401 “mật khẩu sai” và che sự cố.

**Một cấu hình chỉ có mục 3 chưa chứng minh mọi password sai đều có body giống anonymous 401.** Luôn test trực tiếp cả thiếu header và sai password.

### 5.3. Access denied handler xử lý 403 độc lập

~~~java
ServerAccessDeniedHandler forbidden = (exchange, denied) -> {
    exchange.getResponse().setStatusCode(HttpStatus.FORBIDDEN);
    return exchange.getResponse().setComplete();
};

http.exceptionHandling(errors -> errors
        .authenticationEntryPoint(myEntryPoint)
        .accessDeniedHandler(forbidden));
~~~

Đây là snippet, cần imports và biến `myEntryPoint`. Với API JSON, handler 403 có thể dùng cùng utility ghi JSON nhưng status và error code khác. Đừng dùng entry point 401 để xử lý người đã xác thực mà thiếu role.

## 6. Viết custom JSON ServerAuthenticationEntryPoint

Vì là functional interface, bạn có thể dùng lambda:

~~~java
ServerAuthenticationEntryPoint json401 = (exchange, ex) -> {
    ServerHttpResponse response = exchange.getResponse();
    response.setStatusCode(HttpStatus.UNAUTHORIZED);
    response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
    response.getHeaders().setCacheControl("no-store");
    response.getHeaders().set(
            HttpHeaders.WWW_AUTHENTICATE,
            "Basic realm=\"my-api\", charset=\"UTF-8\"");

    byte[] bytes = "{\"error\":\"unauthorized\"}"
            .getBytes(StandardCharsets.UTF_8);

    return response.writeWith(
            Mono.just(response.bufferFactory().wrap(bytes)));
};
~~~

Snippet này thuộc một class cấu hình, cần imports `ServerHttpResponse`, `HttpStatus`, `MediaType`, `HttpHeaders`, `StandardCharsets`, `Mono` và `ServerAuthenticationEntryPoint`. Chúng ta dùng body JSON **cố định**, không phản chiếu exception message.

### 6.1. Những chi tiết bắt buộc

- `Mono<Void>` được **return** để WebFlux subscribe theo vòng đời request. Không gọi `.subscribe()` hoặc `.block()` thủ công trong entry point.
- `Content-Type` khớp body JSON, status là `401`, `Cache-Control: no-store` giảm nguy cơ cache lỗi có thông tin nhạy cảm.
- `WWW-Authenticate: Basic ...` cần đúng scheme của API demo. Nếu dùng Bearer thì phải đổi challenge và xử lý đúng chuẩn RFC 6750.
- Nếu cần dynamic body (timestamp, request ID, mã lỗi), dùng JSON serializer và escape đúng; không nối thẳng dữ liệu do user gửi vào JSON.
- Không gửi raw `ex.getMessage()`, stack trace, user ID nội bộ, token gốc hoặc password.
- Không ghi response hai lần sau khi đã commit, không tiếp tục controller sau khi entry point hoàn tất một response từ chối.

### 6.2. Error envelope chuẩn hóa

Có thể dùng `Problem Details` theo RFC 9457 nếu sản phẩm chọn chuẩn đó:

~~~json
{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Authentication is required"
}
~~~

Đây chỉ là **mẫu JSON theo cách trình bày Problem Details**, không phải output của code demo ở phần 7. Với Problem Details thực sự, dùng `Content-Type: application/problem+json` và schema chuẩn. Chỉ thêm correlation ID/trace ID do server cấp, không phơi credentials trong `detail`.

## 7. Ví dụ hoàn chỉnh với Java 17+ và Spring WebFlux

Ta xây dựng một ứng dụng Boot dùng HTTP Basic, tự trả JSON cho 401/403, không redirect sang form-login HTML.

Endpoints:

- `GET /public`: công khai, trả JSON.
- `GET /api/me`: yêu cầu đã xác thực.
- `GET /api/admin`: yêu cầu `ROLE_ADMIN`.

Người dùng local:

- `reader` / `reader123!` có `ROLE_USER`.
- `admin` / `admin123!` có `ROLE_USER` và `ROLE_ADMIN`.

Credentials mẫu chỉ dành cho máy học tập; HTTP Basic **bắt buộc dùng HTTPS** trong môi trường triển khai thực sự vì Base64 không mã hóa bí mật.

### 7.1. pom.xml

Dùng Maven, Java 17+, Spring Boot **4.1.2**, dependencies **Spring Reactive Web** và **Spring Security**. File `pom.xml`:

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
    <artifactId>reactive-entrypoint-demo</artifactId>
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

Boot BOM quản lý phiên bản Security/Framework/Reactor. Không thêm `spring-boot-starter-web` để tránh trộn Spring MVC/Servlet với WebFlux.

### 7.2. Java source đầy đủ

Tạo file `src/main/java/com/example/entrypoint/ReactiveEntryPointDemoApplication.java`:

~~~java
package com.example.entrypoint;

import java.nio.charset.StandardCharsets;
import java.security.Principal;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
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
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveEntryPointDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveEntryPointDemoApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("reader123!"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin123!"))
                .roles("USER", "ADMIN")
                .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        ServerAuthenticationEntryPoint requireAuthentication =
                (exchange, error) -> sendJson(exchange,
                        HttpStatus.UNAUTHORIZED, "unauthorized", true);

        ServerAccessDeniedHandler forbidden =
                (exchange, error) -> sendJson(exchange,
                        HttpStatus.FORBIDDEN, "forbidden", false);

        return http
                .authorizeExchange(rules -> rules
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/api/admin").hasRole("ADMIN")
                        .pathMatchers("/api/me").authenticated()
                        .anyExchange().denyAll())
                .httpBasic(basic -> basic
                        .authenticationEntryPoint(requireAuthentication)
                        .authenticationFailureHandler(
                                new ServerAuthenticationEntryPointFailureHandler(
                                        requireAuthentication)))
                .formLogin(form -> form.disable())
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint(requireAuthentication)
                        .accessDeniedHandler(forbidden))
                .build();
    }

    private static Mono<Void> sendJson(ServerWebExchange exchange,
            HttpStatus status, String errorCode, boolean basicChallenge) {

        ServerHttpResponse response = exchange.getResponse();
        response.setStatusCode(status);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
        response.getHeaders().setCacheControl("no-store");

        if (basicChallenge) {
            response.getHeaders().set(HttpHeaders.WWW_AUTHENTICATE,
                    "Basic realm=\"entrypoint-demo\", charset=\"UTF-8\"");
        }

        // errorCode chỉ là literal nội bộ, không chứa input từ client.
        String body = "{\"error\":\"" + errorCode + "\"}";
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);

        return response.writeWith(
                Mono.just(response.bufferFactory().wrap(bytes)));
    }

    @RestController
    static class Api {

        @GetMapping("/public")
        Mono<Map<String, String>> publicEndpoint() {
            return Mono.just(Map.of("message", "PUBLIC_OK"));
        }

        @GetMapping("/api/me")
        Mono<Map<String, String>> me(Principal principal) {
            return Mono.just(Map.of("user", principal.getName()));
        }

        @GetMapping("/api/admin")
        Mono<Map<String, String>> admin() {
            return Mono.just(Map.of("message", "ADMIN_OK"));
        }
    }
}
~~~

**Vì sao mã đúng mục tiêu?**

1. `@EnableWebFluxSecurity` cùng `SecurityWebFilterChain` sử dụng API WebFlux reactive; không import Servlet `HttpSecurity`.
2. `MapReactiveUserDetailsService` cung cấp user in-memory và `PasswordEncoder` thật (delegating encoder, mặc định chọn thuật toán thích hợp); không sử dụng `{noop}` cho password.
3. `/public` dùng `permitAll()`, nên anonymous có thể nhận dữ liệu công khai.
4. `/api/me` yêu cầu authentication và kích hoạt entry point khi anonymous.
5. `/api/admin` yêu cầu role; `reader` đã authenticated nhưng thiếu quyền, nên access-denied handler trả 403.
6. `httpBasic(...).authenticationFailureHandler(...)` xử lý **password sai** bằng cùng logic JSON 401.
7. `formLogin(...disable())` bảo đảm không có redirect HTML từ form login của chain demo.
8. `sendJson(...)` tạo `Mono<Void>` ghi response, có `WWW-Authenticate` chỉ trên 401 và tránh echo exception text.
9. Ví dụ chỉ có GET; **không cần tắt CSRF**. Nếu thêm API POST dùng cookie hoặc browser-cached credentials, phải phân tích CSRF riêng.
10. Các password hard-coded chỉ dùng local. Production cần kho danh tính thích hợp, HTTPS, MFA/rate limit và audit an toàn.

### 7.3. Chạy

Ở thư mục chứa `pom.xml`:

~~~bash
./mvnw clean package
./mvnw spring-boot:run
~~~

Trên Windows dùng `.\mvnw.cmd clean package` và `.\mvnw.cmd spring-boot:run`. Nếu không có wrapper, dùng `mvn clean package` rồi `mvn spring-boot:run` với Maven đã cài. Server mặc định dùng `http://localhost:8080`.

### 7.4. Kiểm tra bằng curl

Mở terminal thứ hai:

~~~bash
# Public, không gửi Authorization
curl -i http://localhost:8080/public

# Anonymous gọi endpoint cần authentication
curl -i http://localhost:8080/api/me

# Có Basic credentials nhưng password sai
curl -i -u 'reader:wrong' http://localhost:8080/api/me

# Đúng credentials
curl -i -u 'reader:reader123!' http://localhost:8080/api/me

# Đã login nhưng thiếu role
curl -i -u 'reader:reader123!' http://localhost:8080/api/admin

# Đủ role
curl -i -u 'admin:admin123!' http://localhost:8080/api/admin

# API-only policy không dựa vào Accept
curl -i -H 'Accept: text/html' http://localhost:8080/api/me
~~~

Trên Windows PowerShell, nên dùng `curl.exe` nếu `curl` là alias. Không bật `-L` nếu cần kiểm tra redirect; ví dụ không sử dụng form login nên không mong đợi 302.

| Request | Status | Body mong đợi | Ý nghĩa |
| --- | --- | --- | --- |
| Anonymous `/public` | **200** | `{"message":"PUBLIC_OK"}` | Không cần entry point |
| Anonymous `/api/me` | **401** | `{"error":"unauthorized"}` | Authorization đòi authentication |
| Reader password sai `/api/me` | **401** | `{"error":"unauthorized"}` | Basic authentication failure |
| Reader đúng `/api/me` | **200** | `{"user":"reader"}` | Authentication thành công |
| Reader `/api/admin` | **403** | `{"error":"forbidden"}` | Đã xác thực nhưng thiếu `ROLE_ADMIN` |
| Admin `/api/admin` | **200** | `{"message":"ADMIN_OK"}` | Có `ROLE_ADMIN` |
| Anonymous `/api/me`, `Accept: text/html` | **401** | `{"error":"unauthorized"}` | Không tự redirect sang HTML |

Ở hai nhánh 401, kiểm tra `Content-Type: application/json`, `Cache-Control: no-store` và `WWW-Authenticate: Basic realm="entrypoint-demo", charset="UTF-8"`. Ở nhánh 403, code **không gắn Basic challenge**. Output bổ sung do server/framework tạo có thể khác phiên bản, nhưng body custom và mã status ở các nhánh này là xác định.

Nếu sau này trả object `Map` có nhiều field, thứ tự key JSON không được `Map.of` cam kết; unit/integration test nên so **giá trị JSON field**, không cố định toàn bộ chuỗi theo thứ tự.

## 8. Khi ứng dụng có cả browser và REST API

Một ứng dụng có thể có cùng user store nhưng hai hợp đồng UX:

- Browser `/web/**`: form login, cookie WebSession, redirect `/login`, HTML lỗi.
- API `/api/**`: JSON 401/403, Basic/Bearer hoặc token khác, không dùng form redirect.

Có thể dùng hai chain theo thứ tự:

~~~java
@Bean
@Order(1)
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
            .securityMatcher(
                    new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(rules ->
                    rules.anyExchange().authenticated())
            .httpBasic(basic -> basic
                    .authenticationEntryPoint(json401EntryPoint)
                    .authenticationFailureHandler(
                            new ServerAuthenticationEntryPointFailureHandler(
                                    json401EntryPoint)))
            .formLogin(form -> form.disable())
            .exceptionHandling(errors ->
                    errors.authenticationEntryPoint(json401EntryPoint))
            .build();
}

@Bean
@Order(2)
SecurityWebFilterChain browserChain(ServerHttpSecurity http) {
    return http
            .authorizeExchange(rules -> rules
                    .pathMatchers("/", "/login").permitAll()
                    .anyExchange().authenticated())
            .httpBasic(basic -> basic.disable())
            .formLogin(Customizer.withDefaults())
            .build();
}
~~~

**Snippet kiến trúc, không phải project độc lập:** `json401EntryPoint` là bean/parameter cần định nghĩa; phải có imports `@Bean`, `@Order`, `PathPatternParserServerWebExchangeMatcher`, `Customizer`, các interface đã nói. Khi áp dụng vào project demo, **thay thế** bean security cũ, không khai báo chồng chain match-all mà không hiểu thứ tự.

`@Order` quyết định xem chain nào trước; `securityMatcher(...)` quyết định request thuộc chain nào. `authorizeExchange(...).pathMatchers(...)` quyết định quyền **bên trong chain**. Không nhầm ba thứ này.

**Quan trọng:** nếu SPA dùng cookie session gọi JSON API, đừng tùy tiện cấu hình API là stateless hay tắt CSRF. Cơ chế response JSON không quyết định rằng browser không gửi cookie tự động. Phải tách authentication model, session repository, CORS, CSRF và cookie policy theo threat model.

### DelegatingServerAuthenticationEntryPoint

`DelegatingServerAuthenticationEntryPoint` là lựa chọn khác nếu chỉ cần một entry point quyết định giữa JSON/redirect dựa trên `ServerWebExchangeMatcher`. Tuy nhiên nó **chỉ định tuyến hành vi yêu cầu xác thực**, không tự vô hiệu hóa form login, thay password converter hoặc tách session/token. Khi các cơ chế thực sự khác nhau, nhiều `SecurityWebFilterChain` thường rõ ràng hơn.

## 9. Những tình huống biên

### 9.1. Missing vs invalid vs unsupported credential

Request không có Authorization header có thể được Basic converter bỏ qua. Request có `Authorization: Bearer ...` nhưng chỉ cấu hình Basic cũng có thể bị bỏ qua ở Basic converter; nó **không chứng minh Bearer token sai** vì chưa có Bearer decoder. Request có Basic đúng định dạng nhưng password sai sẽ đi theo authentication failure path.

Dù các trường hợp cuối cùng đều có thể trả 401, **không nên log/cảnh báo như cùng một loại sự cố**. Số lần password sai quan trọng cho rate limiting; request thiếu header tới API công khai có thể bình thường.

### 9.2. Lỗi hạ tầng xác thực

Database hoặc identity provider timeout không phải lúc nào cũng là “BadCredentials”. Adapter `ServerAuthenticationEntryPointFailureHandler` có tùy chọn mặc định rethrow `AuthenticationServiceException`. Giữ sự phân biệt để hệ thống giám sát báo đúng lỗi, không tự chuyển mọi exception thành 401 và làm client tưởng chỉ cần nhập lại mật khẩu.

### 9.3. Form login failure khác với yêu cầu login

Trong form login, request chưa đăng nhập vào trang riêng tư thường dẫn tới **redirect login page**. Nhưng người dùng nhập sai password thường kích hoạt **form failure handler**, có thể redirect `/login?error`. Dùng entry point của anonymous route để thay thế một failure handler sai chỗ dễ tạo vòng lặp redirect.

### 9.4. CSRF có handler riêng

`POST` không có CSRF token hợp lệ có thể nhận 403 từ `CsrfWebFilter`. Việc chỉ thiết lập `exceptionHandling.accessDeniedHandler(...)` không bảo đảm mọi CSRF response cũng đi qua nó. Cần test và cấu hình CSRF handler nếu ứng dụng muốn JSON format thống nhất, thay vì thay lỗi CSRF bằng 401.

### 9.5. Đã viết response thì không viết tiếp

Trong `commence(...)`, return publisher ghi dữ liệu rồi hoàn tất. Không tiếp tục xử lý controller sau khi đã gửi challenge, không tự gọi `response.setComplete()` rồi cố ghi body thêm lần nữa. Khi response đã committed, thiết lập lại status/header có thể không có hiệu lực; đây không phải vấn đề có thể “chữa” bằng `block()`.

### 9.6. HTTP 401 và WWW-Authenticate

Theo HTTP authentication semantics, phản hồi 401 cần một challenge thích hợp. Với Basic, `Basic realm="..."`; với Bearer resource server, `Bearer` và các tham số theo RFC 6750. Dùng JSON body không bỏ qua yêu cầu giao thức. Nếu muốn browser không bật native Basic dialog, hãy chọn một authentication mechanism/UX khác phù hợp thay vì cắt header challenge rồi hy vọng mọi client Basic vẫn chuẩn.

## 10. Kiểm thử ở cấp entry point

Khi viết unit test cho entry point, có thể dùng `MockServerWebExchange` từ Spring Test và `StepVerifier` của Reactor Test. Quy trình:

1. Tạo exchange mock cho `GET /api/me`.
2. Tạo `AuthenticationException` mô tả cần login, ví dụ `AuthenticationCredentialsNotFoundException`.
3. Gọi `entryPoint.commence(exchange, exception)`.
4. Subscribe với `StepVerifier`; xác nhận publisher hoàn tất.
5. Assert status 401, content type, `WWW-Authenticate` và body.
6. Đảm bảo không ghi raw exception text trong response.

Snippet cho một test method:

~~~java
MockServerWebExchange exchange = MockServerWebExchange.from(
        MockServerHttpRequest.get("/api/me"));

AuthenticationException reason =
        new AuthenticationCredentialsNotFoundException(
                "Authentication required");

StepVerifier.create(entryPoint.commence(exchange, reason))
        .verifyComplete();

assertEquals(HttpStatus.UNAUTHORIZED,
        exchange.getResponse().getStatusCode());
assertEquals(MediaType.APPLICATION_JSON,
        exchange.getResponse().getHeaders().getContentType());
~~~

Đây là **test snippet**, không phải class JUnit chạy độc lập: `entryPoint` phải được inject hoặc tạo từ cấu hình, các imports `MockServerWebExchange`, `MockServerHttpRequest`, `StepVerifier`, `assertEquals` cần có trong test class, cùng dependencies Spring Test, Reactor Test và JUnit tương thích. Muốn kiểm tra body, decode các `DataBuffer` của mock response bằng API Spring Test tương ứng phiên bản.

### 10.1. Test matrix thực tế

| Case | Cần assert |
| --- | --- |
| Public anonymous | 200, không gọi entry point |
| Private anonymous | 401 JSON + Basic challenge, không redirect |
| Private sai Basic password | 401 JSON + challenge qua failure handler |
| Private đúng credentials | 200, controller chạy |
| User thiếu role admin | 403 JSON, không Basic challenge |
| Admin đủ quyền | 200 |
| `Accept: text/html` tới API | Vẫn đúng policy API, không tự trả HTML login |
| Browser chưa login tới browser chain | Redirect theo form login |
| Bearer token thiếu/sai trong resource server | Bearer challenge phù hợp, không Basic challenge |
| CSRF token sai | Kết quả theo `CsrfWebFilter`, không ép thành 401 |
| Auth database/IdP lỗi | Tín hiệu lỗi hạ tầng phù hợp, không lộ stack trace |

Kiểm tra cả **status, Content-Type, WWW-Authenticate, Location, Cache-Control** và body, không chỉ một số HTTP duy nhất. Với HTTP-level test của WebFlux, `WebTestClient` và Spring Security test support có thể mô phỏng user/headers; với entry point thuần, test publisher giúp bắt lỗi `Mono<Void>` không hoàn tất.

### 10.2. Debug an toàn

Trong môi trường dev, có thể dùng:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Log nên phân biệt `credentials_absent`, `authentication_failed`, `authorization_denied`, `csrf_denied`, `authentication_service_unavailable`. Không ghi token/Basic header/password/session cookie vào log; nếu có request ID thì chỉ ghi ID phù hợp chính sách quan sát. Đừng dùng `exception.getMessage()` nguyên văn làm HTTP response.

## 11. Những lỗi thường gặp

**Lỗi 1 — Dùng Servlet AuthenticationEntryPoint cho WebFlux.** Servlet API dùng `HttpServletRequest`/`HttpServletResponse`; reactive API dùng `ServerWebExchange` và `Mono<Void>`. Kiểm tra package import, không copy code `HttpSecurity` vào `ServerHttpSecurity`.

**Lỗi 2 — Đổi entry point trong exceptionHandling nhưng password sai vẫn khác format.** Basic authentication failure đi qua failure handler. Thiết lập `ServerAuthenticationEntryPointFailureHandler` khi muốn dùng cùng JSON entry point cho nhánh sai credentials.

**Lỗi 3 — Trả 401 cho user đã authenticated nhưng thiếu role.** Trường hợp đó cần `ServerAccessDeniedHandler` trả 403; trả 401 làm frontend yêu cầu login lại không cần thiết.

**Lỗi 4 — Bỏ WWW-Authenticate trên Basic/Bearer 401.** Body JSON không thay thế challenge. Client đúng protocol có thể yêu cầu header đó.

**Lỗi 5 — Basic entry point trong API chỉ dùng Bearer.** Gửi sai scheme challenge; cần đúng `BearerTokenServerAuthenticationEntryPoint` và chính sách RFC 6750.

**Lỗi 6 — Cứ trả JSON là khỏi CSRF.** API dùng cookie/browser cached credentials vẫn có nguy cơ CSRF; định dạng response không thay đổi threat model.

**Lỗi 7 — Dùng ControllerAdvice để xử lý toàn bộ lỗi security.** Security WebFilters chạy trước controller; entry point, authentication failure và access-denied handler phải được cấu hình trong security layer.

**Lỗi 8 — Viết body sau response commit.** Reactive publisher ghi response phải được return, không tự subscribe, không double-write và không block event loop.

**Lỗi 9 — Chỉ test thiếu header, không test sai password.** Hai request có đường xử lý khác nhau; cùng status chưa chắc body/header nhất quán.

**Lỗi 10 — API bị redirect sang /login.** Kiểm tra `SecurityWebFilterChain` matcher, thứ tự `@Order`, formLogin và browser fallback; `Accept` không tự bảo đảm JSON.

**Lỗi 11 — Thông báo lỗi tiết lộ thông tin tài khoản.** Không đưa password, tên user không tồn tại, provider secret, stack trace vào JSON; dùng message/mã lỗi chung.

**Lỗi 12 — Biến mọi lỗi hạ tầng thành “bad credentials”.** Cần giám sát và xử lý đúng sự cố kho user/JWK/IdP, không âm thầm đánh đổi độ chính xác/độ an toàn.

## 12. Checklist production

1. Xác định rõ route nào sử dụng Basic, Bearer, browser form login hoặc session.
2. Dùng đúng reactive `ServerAuthenticationEntryPoint`, không nhầm Servlet.
3. Entry point 401 có challenge/status/body thích hợp với authentication scheme.
4. Cấu hình Basic/Bearer authentication failure handler đúng nếu muốn JSON thống nhất.
5. Access-denied handler phân biệt 403 cho user đã xác thực nhưng thiếu quyền.
6. CSRF có chính sách riêng cho cookie/browsers; không tắt để “sửa” status code.
7. Nếu nhiều chain, kiểm tra `securityMatcher`, `@Order` và fallback để không có URL bỏ sót.
8. Không tiết lộ exception detail, credential, token, session ID hoặc thông tin nội bộ.
9. Không dùng I/O blocking, `block()` hoặc tự subscribe trong `commence(...)`.
10. Test anonymous, wrong credentials, authenticated, wrong role, malformed token, Bearer challenge, browser redirect và lỗi service.
11. Có error envelope và logging nhất quán với các mã lỗi nghiệp vụ khác.
12. Với Basic chỉ chạy HTTPS; với Bearer kiểm tra JWT đầy đủ bằng thư viện/server được hỗ trợ.
13. Kiểm tra version Spring Security từ Boot BOM trước khi sao chép API hoặc import.
14. Xem `curl -i` cả header lẫn body; không để redirect-following che nguyên nhân.

## 13. Tự đánh giá

**Câu 1.** Khi `GET /api/me` chưa có credentials và cần `authenticated()`, `ServerAuthenticationEntryPoint` làm gì?

**Đáp án:** Khởi tạo phản hồi yêu cầu xác thực, ví dụ 401 + Basic challenge hoặc redirect login theo cơ chế. Nó không kiểm tra password.

**Câu 2.** Basic password sai có chắc đi qua entry point trong `exceptionHandling` không?

**Đáp án:** Không. Một authentication attempt thất bại thường chạy `ServerAuthenticationFailureHandler` của `AuthenticationWebFilter`; có thể dùng `ServerAuthenticationEntryPointFailureHandler` để nối vào entry point.

**Câu 3.** User `reader` đã xác thực nhưng gọi `/api/admin`, nên trả 401 hay 403?

**Đáp án:** 403 nếu chỉ thiếu `ROLE_ADMIN`; dùng `ServerAccessDeniedHandler`.

**Câu 4.** Tại sao custom JSON 401 cho HTTP Basic còn cần `WWW-Authenticate`?

**Đáp án:** 401 theo HTTP semantics phải có authentication challenge; client dùng Basic cần biết scheme/realm. JSON body chỉ bổ sung thông tin.

**Câu 5.** Có được sử dụng `HttpBasicServerAuthenticationEntryPoint` trong Bearer-only API không?

**Đáp án:** Không. Bearer resource server cần challenge theo Bearer/RFC 6750, thường dùng `BearerTokenServerAuthenticationEntryPoint`.

**Câu 6.** Một API `permitAll` không gửi Authorization header có bị gọi entry point không?

**Đáp án:** Không bắt buộc; nếu không có yêu cầu xác thực và không có authentication attempt thất bại, request public có thể xử lý bình thường.

**Câu 7.** Vì sao POST thiếu CSRF token có thể bị 403 dù user chưa login?

**Đáp án:** CSRF filter có quyết định lỗi riêng cho request thay đổi trạng thái; đừng dùng entry point 401 để che tình huống CSRF.

**Câu 8.** Có thể dùng `@RestControllerAdvice` thay cho entry point không?

**Đáp án:** Không tin cậy để xử lý mọi lỗi security trước controller. Nên cấu hình đúng entry point/failure/denied handlers ở WebFlux Security layer.

## 14. Tham khảo chính thức

- [Spring Security — ServerAuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/ServerAuthenticationEntryPoint.html)
- [Spring Security — ExceptionTranslationWebFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/ExceptionTranslationWebFilter.html)
- [Spring Security — ServerHttpSecurity.ExceptionHandlingSpec API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.ExceptionHandlingSpec.html)
- [Spring Security — ServerHttpSecurity.HttpBasicSpec API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.HttpBasicSpec.html)
- [Spring Security — ServerAuthenticationEntryPointFailureHandler API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationEntryPointFailureHandler.html)
- [Spring Security — AuthenticationWebFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html)
- [Spring Security — HttpBasicServerAuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/HttpBasicServerAuthenticationEntryPoint.html)
- [Spring Security — BearerTokenServerAuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/server/BearerTokenServerAuthenticationEntryPoint.html)
- [Spring Security — Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Spring Security — WebFlux Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — HTTP Basic in WebFlux](https://docs.spring.io/spring-security/reference/reactive/authentication/basic.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Security — OAuth2 Reactive Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html)
- [Spring Boot 4.1.2 release](https://spring.io/blog/2026/10/23/spring-boot-4-1-2-available-now/)
