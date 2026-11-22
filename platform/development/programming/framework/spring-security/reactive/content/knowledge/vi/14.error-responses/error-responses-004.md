# ServerAccessDeniedHandler cho yêu cầu thiếu quyền

## Mục tiêu học tập

Bài này thuộc phần **Phản hồi lỗi** trong **Spring Security reactive / Spring WebFlux**. Sau bài học, bạn có thể:

- Giải thích `ServerAccessDeniedHandler` xử lý một yêu cầu **đã xác thực nhưng không đủ quyền** như thế nào, và vì sao status thường là **HTTP 403 Forbidden**.
- Phân biệt `AccessDeniedException` với `AuthenticationException`; phân biệt `ServerAccessDeniedHandler` với `ServerAuthenticationEntryPoint` dùng cho **HTTP 401 Unauthorized**.
- Xác định vai trò của `AuthorizationWebFilter` và `ExceptionTranslationWebFilter` trong chuỗi bảo mật WebFlux, bao gồm trường hợp lỗi do `@PreAuthorize` phát ra.
- Sử dụng `HttpStatusServerAccessDeniedHandler` khi chỉ cần status, hoặc tự triển khai `ServerAccessDeniedHandler` khi API cần phản hồi **JSON thống nhất**.
- Gắn handler bằng `ServerHttpSecurity.exceptionHandling(exceptions -> exceptions.accessDeniedHandler(...))` và kiểm thử bằng `WebTestClient`.
- Nhận ra các trường hợp **CSRF 403**, **OAuth2 Bearer insufficient_scope** và nhiều `SecurityWebFilterChain` cần xử lý cẩn trọng thay vì ghi đè một handler chung.
- Thiết kế thông báo lỗi không làm lộ cấu trúc quyền, dữ liệu tài nguyên, credential hoặc thông tin nhạy cảm; giữ mã lỗi ổn định cho frontend.

> **Phạm vi:** Spring Security **reactive**, dùng `ServerWebExchange` và trả `Mono<Void>`. Không dùng nhầm `AccessDeniedHandler`/`HttpServletRequest`/`HttpSecurity` của **Servlet MVC**; ở WebFlux là `ServerAccessDeniedHandler`, `ServerHttpSecurity` và `SecurityWebFilterChain`.

## 1. Vì sao cần phản hồi “thiếu quyền”?

Một API thường có hai câu hỏi bảo mật tách biệt:

1. **Bạn là ai?** (authentication): Có principal/Authentication đã xác minh chưa?
2. **Bạn có được làm việc này không?** (authorization): Principal có authority/role/scope/ownership phù hợp không?

Ví dụ người dùng `reader` đăng nhập đúng mật khẩu, có `ROLE_READER` nhưng gửi:

~~~http
GET /api/admin/summary HTTP/1.1
Authorization: Basic <credentials-of-reader>
~~~

Server có thể **xác thực thành công** user `reader` nhưng từ chối `hasRole("ADMIN")`. Đây là tình huống **access denied**. Spring Security WebFlux có thể dùng `ServerAccessDeniedHandler` để biến từ chối đó thành HTTP response, thường là:

~~~http
HTTP/1.1 403 Forbidden
~~~

Nếu **không có credential** hoặc credential sai, một HTTP Basic API thường trả **401 Unauthorized** và header `WWW-Authenticate`. Không nên ép cả hai loại lỗi thành một thông báo rằng “mật khẩu sai”, vì user đã authenticated có thể không giải quyết được 403 bằng cách thử lại mật khẩu.

### 1.1. Bảng quyết định nhanh

| Tình huống | Trạng thái xác thực | HTTP thường gặp | Thành phần xử lý đáng chú ý |
|---|---|---|---|
| Không gửi credential tới endpoint `authenticated()` | Chưa authenticated | **401** với Basic challenge | `ServerAuthenticationEntryPoint` |
| Gửi username/password Basic sai | Authentication thất bại | **401** | Basic authentication failure/entry point |
| Gửi Basic đúng nhưng thiếu `ROLE_ADMIN` | Authenticated nhưng thiếu quyền | **403** | `ServerAccessDeniedHandler` |
| User có role cần thiết | Authenticated và được phép | **200** ví dụ | Controller/service |
| User authenticated bị `@PreAuthorize` từ chối | Authenticated nhưng thiếu quyền method | **403** trong HTTP chain thông thường | Reactive method security + exception translation |
| POST thiếu CSRF token | Có thể có hoặc không có Authentication | Thường **403** | `CsrfWebFilter` và CSRF-specific denied handler |
| Bearer token hợp lệ nhưng thiếu scope | Authenticated nhưng không đủ scope | **403** theo RFC 6750 | Bearer-specific denied handler/challenge |
| URL không tồn tại nhưng request vượt policy HTTP | Tùy | **404** | WebFlux handler/router, không phải bằng chứng của access denied |

Đây là các tình huống điển hình, không phải một quy tắc “mọi 401/403 đều có đúng một nguyên nhân”. Với custom exception handling, nhiều chain, form login hay gateway, response có thể khác. Xác định cơ chế thực tế bằng trace, log được scrub và integration test.

## 2. ServerAccessDeniedHandler là gì?

Interface trong Spring Security reactive:

~~~java
package org.springframework.security.web.server.authorization;

public interface ServerAccessDeniedHandler {
    Mono<Void> handle(
        ServerWebExchange exchange,
        AccessDeniedException denied);
}
~~~

Đây là **chữ ký API rút gọn để học**, không phải toàn bộ file nguồn framework. Các type cần quan tâm:

- `ServerWebExchange`: cặp request/response WebFlux hiện tại, dùng để đặt HTTP status, headers và body.
- `AccessDeniedException`: exception cho quyết định authorization từ chối.
- `Mono<Void>`: publisher đại diện cho thao tác xử lý response; Spring subscribe theo reactive pipeline, không được tự gọi `subscribe()` rồi trả về quá sớm.

Handler **không cấp quyền**, **không xác thực mật khẩu**, **không tự đổi role**. Nó nhận lỗi từ chối và quyết định HTTP client sẽ nhìn thấy gì sau khi authorization thất bại.

Các implementation đáng biết:

| Loại | Cách dùng | Hành vi |
|---|---|---|
| `HttpStatusServerAccessDeniedHandler` | Muốn trả status HTTP đơn giản. | Đặt mã status được cấu hình, ví dụ `HttpStatus.FORBIDDEN`. |
| Custom lambda/bean triển khai `ServerAccessDeniedHandler` | API cần JSON error code, content type, cache policy. | Đặt status, headers, viết reactive body, tránh lộ dữ liệu nhạy cảm. |
| `ServerWebExchangeDelegatingServerAccessDeniedHandler` | Muốn lựa chọn handler theo request matcher. | Duyệt matcher theo thứ tự, dùng handler đầu tiên phù hợp, có handler mặc định dự phòng. |
| `BearerTokenServerAccessDeniedHandler` | OAuth2 Resource Server cần response phù hợp RFC 6750. | Có thể gửi challenge Bearer với lỗi `insufficient_scope` khi điều kiện cho phép. |

Đừng nhầm với `org.springframework.security.web.access.AccessDeniedHandler` của Servlet; interface Servlet có chữ ký `handle(HttpServletRequest,HttpServletResponse,AccessDeniedException)` và return `void`.

### 2.1. Khi chỉ cần status

Ví dụ **mảnh cấu hình** với handler có sẵn:

~~~java
ServerAccessDeniedHandler deniedHandler =
    new HttpStatusServerAccessDeniedHandler(HttpStatus.FORBIDDEN);

http.exceptionHandling(exceptions ->
    exceptions.accessDeniedHandler(deniedHandler));
~~~

Đặt trong class cấu hình Spring có bean `SecurityWebFilterChain` và import các type tương ứng. Nếu chưa có yêu cầu JSON body cụ thể, cách này đơn giản, tránh phải tự quản lý bytes/charset/response commit.

### 2.2. Khi cần JSON cho frontend

Một API có thể định nghĩa hợp đồng ổn định:

~~~json
{
  "code": "ACCESS_DENIED",
  "message": "Không có quyền truy cập."
}
~~~

`code` giúp frontend hiển thị trạng thái/lựa chọn liên hệ hỗ trợ; `message` là thông điệp an toàn, không chứa tên role nội bộ, IDs tài nguyên được bảo vệ, thông tin tài khoản, stack trace hoặc payload gốc.

**Không dùng raw `denied.getMessage()` làm JSON công khai**. Exception nội bộ có thể chứa tên expression/route/authority; những thông tin đó nên nằm trong audit có giới hạn, không xuất hiện trong response cho người không đủ quyền.

## 3. Nó đứng ở đâu trong WebFilter chain?

Luồng khái niệm trong Spring Security WebFlux:

~~~text
HTTP request
    |
    v
WebFilterChainProxy
    |
    v
SecurityWebFilterChain đầu tiên khớp securityMatcher
    |
    +--> Authentication filters (HTTP Basic / Bearer / form...)
    |       |
    |       +-- credential không hợp lệ
    |               -> authentication failure handling / 401
    |
    +--> ExceptionTranslationWebFilter (bao quanh downstream)
    |       |
    |       +-- AuthorizationWebFilter
    |                 |
    |                 +-- policy cho phép -> Controller/Service
    |                 |
    |                 +-- AccessDeniedException
    |                            |
    |                            +-- chưa authenticated?
    |                            |       -> ServerAuthenticationEntryPoint
    |                            |       -> 401/challenge hoặc login redirect
    |                            |
    |                            +-- authenticated nhưng thiếu quyền?
    |                                    -> ServerAccessDeniedHandler
    |                                    -> 403 (thường)
    |
    +--> Có thể có AccessDeniedException ở method security
            -> exception translation nếu lỗi truyền qua chain phù hợp
~~~

Sơ đồ chỉ mô tả trách nhiệm, không khóa chặt thứ tự của mọi WebFilter; thứ tự phụ thuộc `SecurityWebFiltersOrder` và cấu hình cụ thể. Một lời gọi ngoài HTTP pipeline (ví dụ test trực tiếp service reactive) có thể phát `AccessDeniedException` dưới dạng `Mono.error(...)` **mà không có HTTP response để handler xử lý**.

### 3.1. AuthorizationWebFilter

`AuthorizationWebFilter` đọc security context hiện tại và kiểm tra các matcher/rule từ `authorizeExchange(...)`. Ví dụ:

~~~java
http.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/public").permitAll()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().authenticated());
~~~

Request `/api/admin/summary` từ user có `ROLE_READER` sẽ bị từ chối vì thiếu `ROLE_ADMIN`. Đừng tưởng `ServerAccessDeniedHandler` là nơi tự làm `hasRole`; quyền đã được quyết định ở authorization layer, handler chỉ biến lỗi thành phản hồi.

### 3.2. ExceptionTranslationWebFilter

`ExceptionTranslationWebFilter` xử lý các `AccessDeniedException` phát sinh từ downstream trong WebFlux security pipeline và lựa chọn phản ứng thích hợp tùy Authentication/context. Khái niệm chính:

- **Authentication chưa đủ:** cần bắt đầu xác thực -> `ServerAuthenticationEntryPoint` (thường 401 hoặc redirect login).
- **Đã xác thực nhưng bị từ chối:** `ServerAccessDeniedHandler` (thường 403).

Không viết code theo giả định rằng mọi `AccessDeniedException` đều được gửi thẳng vào handler 403, bất kể anonymous/authentication state. Đó chính là lý do câu hỏi “401 hay 403?” phải được đặt trước khi tùy biến response.

### 3.3. ServerAuthenticationEntryPoint khác gì?

Interface reactive cho **bắt đầu authentication**:

~~~java
Mono<Void> commence(
    ServerWebExchange exchange,
    AuthenticationException exception);
~~~

Nó dùng khi cần yêu cầu client xác thực; ví dụ HTTP Basic trả `401` kèm `WWW-Authenticate: Basic realm="Realm"` theo cấu hình. Trong khi đó:

~~~java
Mono<Void> handle(
    ServerWebExchange exchange,
    AccessDeniedException denied);
~~~

là chữ ký denied handler. Tên method, loại exception và ngữ nghĩa **không giống nhau**. Nếu chỉ gắn `accessDeniedHandler(...)`, bạn không tự thay thế toàn bộ response cho username/password sai hoặc route anonymous. Muốn custom 401, dùng entry point/failure handler phù hợp và vẫn giữ challenge theo HTTP authentication scheme.

## 4. Cấu hình tại ServerHttpSecurity.exceptionHandling

WebFlux dùng DSL:

~~~java
@Bean
SecurityWebFilterChain springSecurityFilterChain(
    ServerHttpSecurity http,
    ServerAccessDeniedHandler accessDeniedHandler) {

    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/admin/**").hasRole("ADMIN")
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .exceptionHandling(exceptions ->
            exceptions.accessDeniedHandler(accessDeniedHandler))
        .build();
}
~~~

Đây là một **method cấu hình minh họa**, cần bean `ServerAccessDeniedHandler` và các import `@Bean`, `ServerHttpSecurity`, `SecurityWebFilterChain`, `Customizer`; phần thực hành ở dưới có chương trình hoàn chỉnh.

### 4.1. Hai nhánh độc lập trong ExceptionHandlingSpec

| Method | Nhận tham số | Trách nhiệm |
|---|---|---|
| `exceptionHandling(ex -> ex.authenticationEntryPoint(entryPoint))` | `ServerAuthenticationEntryPoint` | Chọn phản hồi khi cần authentication, ví dụ 401 challenge. |
| `exceptionHandling(ex -> ex.accessDeniedHandler(handler))` | `ServerAccessDeniedHandler` | Chọn phản hồi cho người đã xác thực nhưng thiếu quyền. |

Có thể cấu hình cả hai:

~~~java
http.exceptionHandling(exceptions -> exceptions
    .authenticationEntryPoint(customEntryPoint)
    .accessDeniedHandler(customDeniedHandler));
~~~

Đây là **mảnh code không độc lập**; cả hai bean cần được khai báo đúng nơi. Khi API hỗ trợ nhiều auth scheme (Bearer, Basic, form login), tránh dùng một entry point kiểu Basic cho mọi request nếu điều đó sẽ làm sai RFC/auth challenge.

### 4.2. Đặt handler cho mỗi SecurityWebFilterChain

Khi có nhiều bean `SecurityWebFilterChain`, Spring Security chọn chain đầu tiên khớp request theo `securityMatcher(...)` và `@Order`. Vì vậy `accessDeniedHandler(...)` gắn trên **chain được cấu hình**, không phải tự động áp dụng cho mọi chain hoặc mọi URL của ứng dụng.

Ví dụ: chain `/api/**` trả JSON 403, chain dành cho browser `/web/**` redirect tới trang lỗi hoặc trả HTML theo UI design. Thiết lập matcher và fallback nhất quán; nếu một URL nằm ngoài mọi chain, denied handler của Spring Security **không thể bảo vệ** URL đó.

## 5. Tạo JSON ServerAccessDeniedHandler đúng reactive

Mẫu lambda ngắn:

~~~java
ServerAccessDeniedHandler jsonDeniedHandler = (exchange, denied) -> {
    ServerHttpResponse response = exchange.getResponse();

    response.setStatusCode(HttpStatus.FORBIDDEN);
    response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
    response.getHeaders().setCacheControl(CacheControl.noStore());

    byte[] body = (
        "{\"code\":\"ACCESS_DENIED\","
        + "\"message\":\"Không có quyền truy cập.\"}")
        .getBytes(StandardCharsets.UTF_8);

    return response.writeWith(
        Mono.just(response.bufferFactory().wrap(body)));
};
~~~

Đây là đoạn Java trong class Spring có import `ServerAccessDeniedHandler`, `ServerHttpResponse`, `HttpStatus`, `MediaType`, `CacheControl`, `StandardCharsets` và `Mono`. Phần thực hành dùng cùng ý tưởng ở dạng bean để có thể chạy.

**Các điểm đúng:**

1. Sử dụng `ServerWebExchange.getResponse()`, không dùng `HttpServletResponse`.
2. Đặt `403 Forbidden` trước khi ghi body.
3. Đặt `Content-Type: application/json`.
4. Dùng UTF-8 để encode tiếng Việt trong JSON.
5. Đặt `Cache-Control: no-store` để giảm nguy cơ cache nội dung lỗi/tài nguyên nhạy cảm.
6. Viết bytes qua `DataBufferFactory` của chính response.
7. Trả `Mono<Void>` từ `response.writeWith(...)` và để WebFlux subscribe; **không** gọi `block()` hoặc `subscribe()` thủ công.

**Những điều không nên làm:**

~~~java
// SAI: trả response thành công, không mô tả access denied.
return Mono.empty(); // khi chưa set status, headers hoặc body

// SAI: cố ghi response hai lần hoặc ghi sau khi đã commit.
response.setStatusCode(HttpStatus.FORBIDDEN);
response.setComplete().subscribe();
return response.writeWith(...); // ... chỉ là placeholder minh họa lỗi
~~~

Hai snippet trên **chỉ mô tả lỗi cần tránh**, không phải code chạy độc lập. Khi response đã committed, việc đổi status/header thường không còn hiệu lực và có thể sinh lỗi; hãy tổ chức filter/handler sao cho response chỉ được ghi một lần.

### 5.1. Không viết exception message cho client

Không thực hiện:

~~~java
// KHÔNG đưa exception.getMessage() vào JSON client.
String unsafe = denied.getMessage();
~~~

Một `AccessDeniedException` có thể tiết lộ tên policy, role thiếu, method expression, dữ liệu tài nguyên hoặc stack trace. Nếu cần audit, ghi error category/sanitized data vào hệ thống log có quyền truy cập thích hợp; không log Basic credential, bearer token, session cookie, PII hoặc raw sensitive resource.

### 5.2. Chú ý JSON escaping

Ví dụ trên dùng hai string **hằng số do server sở hữu**, nên JSON literal là hợp lệ. Nếu cần đưa giá trị động vào body, **không nối chuỗi** từ header/path/exception raw; dùng JSON serializer được framework hỗ trợ (Jackson `ObjectMapper`) với DTO lỗi rõ ràng. Giá trị `traceId` có thể lấy từ correlation ID được server cấp nhưng cần validate/truncate để tránh phản chiếu dữ liệu không đáng tin.

### 5.3. Có nên thêm Content-Length?

Không bắt buộc tự set Content-Length khi dùng `writeWith`; server có thể chọn streaming/chunked encoding. Điều quan trọng cho client là status, Content-Type và payload có schema ổn định. Nếu tự set Content-Length, phải tính theo **số byte UTF-8**, không phải `String.length()`, vì tiếng Việt có nhiều code point mã hóa bằng nhiều byte.

## 6. Bài thực hành Java 17: cùng một JSON handler cho URL và phương thức nghiệp vụ

Ví dụ chạy với **Java 17**, **Spring Boot 3.5.16**, WebFlux và Spring Security do Spring Boot dependency management quản lý. Tài khoản demo hardcode và `{noop}` chỉ dành cho localhost, không dùng trên môi trường mạng thật.

Mục tiêu:

- `GET /public` được phép không credential.
- `GET /api/me` cần authenticated.
- `GET /api/admin/summary` cần `ROLE_ADMIN` **ngay ở HTTP URL rule**.
- `GET /api/internal/report` chỉ cần authenticated tại HTTP, nhưng có `@PreAuthorize("hasRole('ADMIN')")` **ở service**.
- Hai user `reader` (chỉ ROLE_READER) và `admin` (ROLE_ADMIN).
- Cả hai đường bị từ chối khi user `reader` đã xác thực đều trả status **403** và JSON `{"code":"ACCESS_DENIED","message":"Không có quyền truy cập."}`.
- Request không authenticated/credential sai trả **401** theo Basic entry point, không bị custom 403 handler giả mạo thành “thiếu role”.

### 6.1. Cấu trúc dự án

~~~text
webflux-access-denied-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/AccessDeniedWebFluxDemo.java
    └── test/java/example/AccessDeniedIntegrationTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-access-denied-demo'
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
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Cần JDK 17+ và Gradle/Gradle Wrapper tương thích Spring Boot 3.5. Không cần tự gắn phiên bản Spring Security khác với Spring Boot BOM cho bài demo. Trong dự án thật, dùng release còn hỗ trợ và nhận bản vá bảo mật tương ứng.

### 6.2. Ứng dụng hoàn chỉnh

`src/main/java/example/AccessDeniedWebFluxDemo.java`:

~~~java
package example;

import java.nio.charset.StandardCharsets;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authorization.ServerAccessDeniedHandler;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class AccessDeniedWebFluxDemo {

    public static void main(String[] args) {
        SpringApplication.run(AccessDeniedWebFluxDemo.class, args);
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
            .password("{noop}demo-pass")
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password("{noop}admin-pass")
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    ServerAccessDeniedHandler jsonDeniedHandler() {
        return (exchange, denied) -> {
            ServerHttpResponse response = exchange.getResponse();
            response.setStatusCode(HttpStatus.FORBIDDEN);
            response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
            response.getHeaders().setCacheControl(CacheControl.noStore());

            // Chỉ dùng nội dung lỗi hằng số an toàn, không lộ exception.
            String json = "{\"code\":\"ACCESS_DENIED\","
                + "\"message\":\"Không có quyền truy cập.\"}";

            byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
            return response.writeWith(
                Mono.just(response.bufferFactory().wrap(bytes)));
        };
    }

    @Bean
    SecurityWebFilterChain security(
        ServerHttpSecurity http,
        ServerAccessDeniedHandler jsonDeniedHandler) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .pathMatchers("/api/admin/**").hasRole("ADMIN")
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .exceptionHandling(exceptions ->
                exceptions.accessDeniedHandler(jsonDeniedHandler))
            .build();
    }

    @Service
    public static class ReportService {

        @PreAuthorize("hasRole('ADMIN')")
        public Mono<Map<String, String>> internalReport() {
            return Mono.just(Map.of("report", "internal-only"));
        }
    }

    @RestController
    static class ApiController {

        private final ReportService reportService;

        ApiController(ReportService reportService) {
            this.reportService = reportService;
        }

        @GetMapping("/public")
        Mono<Map<String, String>> publicRoute() {
            return Mono.just(Map.of("access", "public"));
        }

        @GetMapping("/api/me")
        Mono<Map<String, String>> me(ServerWebExchange exchange) {
            return exchange.getPrincipal()
                .map(principal -> Map.of(
                    "username", principal.getName()));
        }

        @GetMapping("/api/admin/summary")
        Mono<Map<String, String>> adminSummary() {
            return Mono.just(Map.of("access", "admin"));
        }

        @GetMapping("/api/internal/report")
        Mono<Map<String, String>> report() {
            return reportService.internalReport();
        }
    }
}
~~~

**Từng thành phần:**

1. `@EnableWebFluxSecurity` bật web security reactive. `@EnableReactiveMethodSecurity(useAuthorizationManager=true)` kích hoạt `@PreAuthorize` tại service.
2. Bean `jsonDeniedHandler` là một `ServerAccessDeniedHandler` lambda với chữ ký `(ServerWebExchange, AccessDeniedException) -> Mono<Void>`.
3. `exceptionHandling(...accessDeniedHandler(...))` gắn handler vào xử lý access denied của HTTP security chain.
4. `/api/admin/**` bị `AuthorizationWebFilter` chặn nếu user không có `ROLE_ADMIN`.
5. `/api/internal/report` vượt qua HTTP policy với một user authenticated, nhưng `ReportService.internalReport()` đòi ADMIN qua method security. Reactive error từ downstream được security chain xử lý thành response 403 trong cấu hình demo.
6. `/api/me` trả principal đã được Spring Security xác thực, không tin header tùy ý do client gửi.
7. JSON handler giữ `code`/`message` ổn định, không trả nội dung `denied.getMessage()` cho caller.
8. Form login được tắt để các test unauthenticated thấy Basic 401 rõ ràng.
9. Demo **chỉ dùng GET**, để không trộn lỗi 403 do CSRF của POST vào bài thử authorization denial.
10. `{noop}` và password hardcode chỉ phục vụ chạy local; production phải dùng `PasswordEncoder` phù hợp, HTTPS, quản lý secret và rate limiting.

### 6.3. Chạy bằng Gradle và curl

Trong thư mục `webflux-access-denied-demo`:

~~~bash
gradle bootRun
~~~

Nếu dự án đã tạo Gradle Wrapper, Linux/macOS dùng `./gradlew bootRun`; Windows dùng `gradlew.bat bootRun`. Khi ứng dụng chạy ở `localhost:8080`, thử:

~~~bash
# 1. Anonymous tới route công khai.
curl -i http://localhost:8080/public

# 2. Anonymous tới route admin: mong đợi Basic 401.
curl -i http://localhost:8080/api/admin/summary

# 3. Basic sai: authentication thất bại, cũng là 401.
curl -i -u reader:wrong-pass http://localhost:8080/api/admin/summary

# 4. Reader đã xác thực nhưng thiếu role ở HTTP rule: 403 JSON.
curl -i -u reader:demo-pass http://localhost:8080/api/admin/summary

# 5. Reader bị @PreAuthorize ở service từ chối: 403 JSON.
curl -i -u reader:demo-pass http://localhost:8080/api/internal/report

# 6. Admin truy cập cả URL rule lẫn service rule.
curl -i -u admin:admin-pass http://localhost:8080/api/admin/summary
curl -i -u admin:admin-pass http://localhost:8080/api/internal/report

# 7. Reader được truy cập route chỉ cần authenticated.
curl -i -u reader:demo-pass http://localhost:8080/api/me
~~~

Trên PowerShell, dùng `curl.exe` khi `curl` trỏ tới alias khác. `-i` hiển thị response headers; `-u` tạo HTTP Basic Authorization header. Tránh đưa mật khẩu thật vào command line/shell history; ở đây chỉ có credential giả cho localhost.

**Kết quả kỳ vọng:**

| Request | Status | Body/header có ý nghĩa |
|---|---|---|
| `GET /public` anonymous | **200** | `{"access":"public"}` |
| `GET /api/admin/summary` anonymous | **401** | `WWW-Authenticate: Basic ...`; **không** dùng JSON 403 của denied handler |
| `GET /api/admin/summary` Basic sai | **401** | Authentication failure; không phải thiếu role |
| `GET /api/admin/summary` reader đúng | **403** | JSON `code=ACCESS_DENIED` |
| `GET /api/internal/report` reader đúng | **403** | Cùng JSON vì service method security từ chối |
| `GET /api/admin/summary` admin đúng | **200** | `{"access":"admin"}` |
| `GET /api/internal/report` admin đúng | **200** | `{"report":"internal-only"}` |
| `GET /api/me` reader đúng | **200** | `{"username":"reader"}` |

Ví dụ đoạn **HTTP response** khi reader bị deny:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/json
Cache-Control: no-store

{"code":"ACCESS_DENIED","message":"Không có quyền truy cập."}
~~~

Đây là output mô tả phần cần quan sát, không phải toàn bộ response byte-for-byte. HTTP version, thứ tự header, Content-Length/Transfer-Encoding, Date và các security headers khác có thể thay đổi. Client nên parse JSON theo field, không so sánh nguyên response dump.

### 6.4. Đọc kết quả theo security flow

- `curl -u reader:demo-pass` cung cấp credential đúng cho user có `ROLE_READER`. Với route admin, authorization rule từ chối và `ExceptionTranslationWebFilter` dùng denied handler -> 403 JSON.
- Với route `/api/internal/report`, HTTP rule chỉ yêu cầu authenticated, nên reader đi qua HTTP filter. Sau đó service `@PreAuthorize` từ chối -> reactive access denied đi qua exception translation -> 403 JSON.
- `curl` không credential không tạo Authentication hợp lệ; Basic entry point nhận yêu cầu authentication -> 401 challenge. Không dùng denied handler làm login page.
- Với admin, cả hai policy đều cho phép, controller/service trả JSON nghiệp vụ.

Không tự làm cho `@PreAuthorize` hoạt động bằng cách gọi protected service qua `new` hoặc self-invocation trong cùng bean; demo sử dụng Spring `@Service` và constructor injection vào controller, bảo đảm lời gọi qua Spring bean proxy.

## 7. Integration tests bằng WebTestClient

Để xác nhận đúng HTTP status và JSON body theo API contract, dùng Spring Boot test và `WebTestClient`. Những test sau kiểm tra cả 401, 403 và 200.

Tệp `src/test/java/example/AccessDeniedIntegrationTest.java`:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class AccessDeniedIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void anonymousMustAuthenticateInsteadOfReceiving403Json() {
        client.get().uri("/api/admin/summary")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void wrongPasswordIs401() {
        client.get().uri("/api/admin/summary")
            .headers(h -> h.setBasicAuth("reader", "wrong-pass"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void validReaderMissingUrlRoleGets403Json() {
        client.get().uri("/api/admin/summary")
            .headers(h -> h.setBasicAuth("reader", "demo-pass"))
            .exchange()
            .expectStatus().isForbidden()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.code").isEqualTo("ACCESS_DENIED")
            .jsonPath("$.message").isEqualTo(
                "Không có quyền truy cập.");
    }

    @Test
    void methodSecurityDenialGetsSame403Json() {
        client.get().uri("/api/internal/report")
            .headers(h -> h.setBasicAuth("reader", "demo-pass"))
            .exchange()
            .expectStatus().isForbidden()
            .expectBody()
            .jsonPath("$.code").isEqualTo("ACCESS_DENIED");
    }

    @Test
    void adminPassesBothAuthorizationLayers() {
        client.get().uri("/api/admin/summary")
            .headers(h -> h.setBasicAuth("admin", "admin-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.access").isEqualTo("admin");

        client.get().uri("/api/internal/report")
            .headers(h -> h.setBasicAuth("admin", "admin-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.report").isEqualTo("internal-only");
    }

    @Test
    void readerCanAccessOwnIdentity() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("reader", "demo-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.username").isEqualTo("reader");
    }

    @Test
    void publicRequestDoesNotNeedCredential() {
        client.get().uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.access").isEqualTo("public");
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

Nếu có Gradle Wrapper: `./gradlew test` hoặc `gradlew.bat test`. Kỳ vọng bảy test pass với code/dependencies đúng. Chưa cần đo exact log/status line byte-for-byte; mã lỗi, status và header thiết yếu mới là contract.

**Giới hạn của test:** Chỉ có GET, nên chưa kiểm tra CSRF của POST; cũng không kiểm tra auth token Bearer. Đó là các cơ chế riêng được bàn ở phần 8. Code là ví dụ đầy đủ để học, nhưng phải chạy build/test trên môi trường thực để xác minh kết quả, không nên xem một status kỳ vọng là chứng cứ đã thực thi.

## 8. CSRF 403 không nhất thiết dùng exceptionHandling.accessDeniedHandler

Một lỗi rất dễ nhầm: gửi `POST /api/update` thiếu CSRF token, nhận 403 và kết luận rằng handler JSON ở mục 6 hỏng vì response không phải JSON. Thực tế `CsrfWebFilter` có **handler cấu hình riêng**.

Trong Spring Security WebFlux, `ServerHttpSecurity.CsrfSpec` cung cấp:

~~~java
http.csrf(csrf ->
    csrf.accessDeniedHandler(jsonDeniedHandler));
~~~

Đây là **mảnh cấu hình** trong một bean `SecurityWebFilterChain` đã có `jsonDeniedHandler`. Nó chỉ định xử lý khi CSRF token không hợp lệ. Còn:

~~~java
http.exceptionHandling(exceptions ->
    exceptions.accessDeniedHandler(jsonDeniedHandler));
~~~

được dùng cho access denied từ authorization/exception translation. **Hai điểm cấu hình khác nhau**, không nên suy đoán chỉ gắn một nơi sẽ bao phủ tất cả 403.

### 8.1. Nên dùng cùng JSON body cho CSRF không?

Có thể nếu frontend cần schema chung, nhưng cần phân biệt nội bộ:

- `CSRF_TOKEN_INVALID`: thiếu/sai token, có thể hướng client làm mới token/session khi policy cho phép.
- `ACCESS_DENIED`: đã authenticated nhưng không có quyền với tài nguyên.
- `AUTHENTICATION_REQUIRED`: chưa xác thực hợp lệ, cần entry point 401.

Nếu công khai cả ba với thông điệp quá chi tiết, có thể làm lộ thông tin về trạng thái phiên/tài khoản. Nên có mã lỗi công khai tối thiểu, còn audit nội bộ phân biệt nguyên nhân đủ dùng.

### 8.2. Không tắt CSRF chỉ vì thiếu JSON

Nếu ứng dụng dùng cookie/session mà browser tự gửi credential, tắt CSRF để làm POST trả status bạn muốn có thể tạo lỗ hổng. Cấu hình CSRF token và handler đúng; test bằng `WebTestClient` với `csrf()` hoặc luồng token thật để tránh nhầm authorization 403 với CSRF 403.

Với API bearer stateless không dựa vào cookie tự động gửi, CSRF threat model có thể khác, nhưng phải đánh giá cơ sở trước khi tắt CSRF toàn cục.

## 9. OAuth2 Resource Server: đừng làm mất Bearer challenge

Với OAuth2 Resource Server, một access token **hợp lệ** nhưng thiếu scope có thể cần HTTP response theo **RFC 6750**; `BearerTokenServerAccessDeniedHandler` được Spring Security thiết kế cho tình huống này.

Ví dụ ý nghĩa protocol:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Đây là trích đoạn minh họa; handler thực tế có thể thêm `realm`, `scope` hoặc tham số khác theo cấu hình và mức thông tin phù hợp. Không coi toàn bộ các request 403 đều phải có header như trên.

**Rủi ro khi thay bằng JSON handler duy nhất:** Nếu override Bearer handler một cách thiếu cân nhắc, bạn có thể đánh mất `WWW-Authenticate` hoặc `error="insufficient_scope"` mà OAuth2 client dựa vào.

### 9.1. Các hướng triển khai an toàn

1. Nếu Resource Server không cần JSON body riêng, giữ Bearer-specific handler mặc định cho chain đó.
2. Nếu cần body JSON, cân nhắc **ủy quyền cho BearerTokenServerAccessDeniedHandler** thiết lập status/header trước, rồi mới kết hợp body theo quy tắc response commit; phải thiết kế và test cẩn thận để không ghi response hai lần.
3. Nếu ứng dụng có cả HTTP Basic và Bearer, tách chúng bằng `SecurityWebFilterChain`/matcher đúng, hoặc chọn handler theo request bằng `ServerWebExchangeDelegatingServerAccessDeniedHandler`.
4. Kiểm thử `401` với token thiếu/hết hạn, `403` với token đúng nhưng thiếu scope, giá trị `WWW-Authenticate` và error schema.
5. Không đưa access token hoặc chi tiết nội bộ về policy vào JSON/WWW-Authenticate.

**Đừng** đổi mọi 403 thành 401 để client “đăng nhập lại”; token hợp lệ nhưng thiếu quyền thường cần phân biệt với token thiếu/hết hạn.

## 10. Tùy biến theo request bằng ServerWebExchangeDelegatingServerAccessDeniedHandler

Một ứng dụng có thể muốn lỗi HTML cho `/web/**` và JSON cho `/api/**`, hoặc trả lỗi theo API version. Spring Security cung cấp `ServerWebExchangeDelegatingServerAccessDeniedHandler` để chọn delegate theo `ServerWebExchangeMatcher`.

Tư duy cấu hình:

~~~text
403 access denied trong security chain
   |
   v
ServerWebExchangeDelegatingServerAccessDeniedHandler
   |
   +-- match /api/** -> JSON ServerAccessDeniedHandler
   |
   +-- match /web/** -> handler cho browser
   |
   +-- không match -> default denied handler
~~~

Matcher được xét theo thứ tự, handler đầu tiên phù hợp được dùng. Phải có fallback rõ ràng, nhất là khi thêm route mới. Nếu các route thuộc **hai security chain riêng**, việc cấu hình handler trên từng chain có thể đơn giản hơn. Đừng tạo nhiều cách phân nhánh chồng chéo khiến không biết policy nào có hiệu lực.

### 10.1. Trả HTML error cho browser

Với browser giao diện server-rendered, có thể muốn redirect tới trang access-denied hoặc render HTML. Hãy nhớ response **403** có ý nghĩa khác redirect login: người dùng đã đăng nhập nhưng không có quyền. Nếu redirect, cân nhắc mã status và UX để không khiến client tưởng được xác thực lại sẽ giải quyết mọi thiếu quyền.

Cẩn thận tránh vòng lặp: trang `/access-denied` tự bị bảo vệ bằng role vừa không thỏa thì lại tạo access denied. Nếu cần trang lỗi công khai, cấu hình authorize rule và controller riêng theo policy.

### 10.2. Khi dùng custom WebExceptionHandler/@ControllerAdvice

Global exception handling của ứng dụng có thể can thiệp vào `AccessDeniedException` theo vị trí trong pipeline. Không bắt mọi exception rồi chuyển thành 500/200. Với security exception, ưu tiên để Spring Security translation xử lý khi nằm trong security chain, trừ khi có yêu cầu tích hợp được test rõ ràng. Đừng trả raw stack trace hoặc principal details trong response.

## 11. Thiết kế error schema cho production

Một error response dùng nhất quán cho API nên cân nhắc:

~~~json
{
  "code": "ACCESS_DENIED",
  "message": "Không có quyền truy cập.",
  "requestId": "opaque-server-generated-id"
}
~~~

Đây là **schema minh họa**, không phải output bắt buộc của code demo. Không copy string `opaque-server-generated-id` thành ID cố định. Các nguyên tắc:

- `code` ổn định theo API contract; frontend không parse lời văn tiếng Việt để quyết định hành vi.
- `message` an toàn, có thể nội địa hóa nhưng không tiết lộ role/authority cụ thể, quyền của người khác, ID tài nguyên nhạy cảm.
- `requestId` phải do server/gateway tạo hoặc validate an toàn; dùng để tra audit có giới hạn, không đưa thông tin cá nhân vào ID.
- `timestamp` tùy chọn, nhưng không nên phụ thuộc format chuỗi/timezone khi không có yêu cầu; nếu dùng, thống nhất ISO 8601/UTC.
- `details` có thể có nhưng không chứa `denied.getMessage()` hoặc stack trace cho client.
- `Content-Type` phải đúng, status HTTP không được thay bằng một JSON field trong khi status luôn 200.
- `Cache-Control: no-store` hữu ích để hạn chế cache nội dung lỗi, nhất là tài nguyên nhạy cảm.
- CORS headers nếu cần được cấu hình ở cơ chế CORS; 403 không tự thiết lập Access-Control-Allow-Origin.
- Không trả nhiều body fragment, không ghi response sau khi committed.

### 11.1. Logging và observability

Để debug access denied, nên có log/audit gồm:

- request ID/correlation ID, thời gian, route/method đã chuẩn hóa;
- user ID/subject **theo chính sách privacy** hoặc ID đã pseudonymize;
- nguồn denial: HTTP authorization, method security, CSRF, Bearer insufficient_scope;
- policy key/authority category ở **audit nội bộ**, không leak qua response;
- security chain/matcher đã chọn khi cần, không log raw Authorization header.

Rate-limit và cảnh báo khi nhiều 403 bất thường có thể hỗ trợ phát hiện privilege probing. Tuy nhiên 403 có thể do frontend stale permissions hoặc session state cũ; đừng coi mọi 403 là tấn công.

### 11.2. 403 hay 404 để che sự tồn tại tài nguyên?

RFC HTTP cho phép server trả 404 trong một số tình huống muốn ẩn tài nguyên bị cấm, nhưng không phải quy tắc mặc định của `ServerAccessDeniedHandler`. Nếu policy yêu cầu che resource existence, phải thiết kế rõ ở authorization/data access layer, bảo đảm không tạo khác biệt thời gian/body rò rỉ, test theo identity/tenant. Đừng tự chuyển mọi 403 thành 404 một cách mù quáng: có thể làm client hiểu sai và che lỗi permission config.

## 12. Các sai lầm thường gặp

**Sai lầm 1 — Dùng handler 403 để xử lý login sai.** Login sai là authentication failure, dùng entry point/handler của authentication. Access denied cho user đã xác thực là một vấn đề khác.

**Sai lầm 2 — Coi mọi 403 là thiếu role.** CSRF, scope token, method policy và gateway có thể sinh 403. Phải phân biệt nguồn.

**Sai lầm 3 — Trả status 200 kèm `{"error":"forbidden"}`.** HTTP client/proxy/monitoring có thể hiểu thành công. Trả 403 thật và schema rõ ràng.

**Sai lầm 4 — Nuốt exception rồi gọi `Mono.empty()`.** Nếu chưa set status/body, response có thể bị hiểu thành thành công. Handler cần hoàn tất response đúng semantics.

**Sai lầm 5 — Tự `subscribe()` rồi trả Mono.empty.** Response có thể chưa được ghi khi framework hoàn tất, dẫn đến lỗi race/committed response. Trả publisher.

**Sai lầm 6 — Dùng `AccessDeniedHandler` Servlet trên WebFlux.** Sai API stack. Dùng `ServerAccessDeniedHandler` và `ServerWebExchange`.

**Sai lầm 7 — Chỉ gắn `exceptionHandling.accessDeniedHandler(...)` mà mong CSRF 403 thành JSON.** CSRF có `csrf.accessDeniedHandler(...)` riêng. Cấu hình đúng điểm.

**Sai lầm 8 — Ghi raw `AccessDeniedException.getMessage()` ra body.** Nó có thể lộ thông tin nội bộ. Dùng mã lỗi và thông điệp chung.

**Sai lầm 9 — Hardcode quyền trong denied handler.** Handler không phải nơi cấp role hoặc quyết định ownership. Kiểm tra quyền ở AuthorizationManager/method service.

**Sai lầm 10 — Coi `permitAll()` bảo đảm không có security denial.** Authentication filter, CSRF, method security vẫn có thể từ chối; permitAll chỉ nói về rule HTTP authorization tương ứng.

**Sai lầm 11 — Ghi response sau khi committed.** Nếu một filter/controller đã gửi body, thay status/header quá muộn có thể lỗi. Thiết kế exception boundary rõ ràng.

**Sai lầm 12 — Dùng JSON denied handler của Basic để thay Bearer-specific handler.** Có thể đánh mất `WWW-Authenticate: Bearer`/`insufficient_scope` theo RFC 6750. Chọn theo chain/scheme.

**Sai lầm 13 — Gắn handler cho chain không khớp URL.** Nhiều `SecurityWebFilterChain` chọn chain đầu tiên theo matcher/order; handler của chain khác không chạy.

**Sai lầm 14 — So sánh nguyên HTTP response byte-for-byte.** Header, content length, thứ tự JSON field có thể thay đổi; test status/content type/error code.

**Sai lầm 15 — Dùng ThreadLocal để lấy principal trong reactive handler.** Không bảo đảm truyền qua asynchronous operators; tận dụng `ServerWebExchange` và Reactor security context, không dựa vào `SecurityContextHolder` kiểu Servlet.

**Sai lầm 16 — Bỏ qua custom error handler khác của ứng dụng.** Một `@ControllerAdvice` hoặc Gateway/WebExceptionHandler có thể thay response; test theo đường request thật.

**Sai lầm 17 — Muốn uniform JSON nên tắt CSRF hoặc bỏ authentication.** Uniformity là vấn đề handler/schema, không phải lý do bỏ lớp bảo vệ. Giữ security policy và cấu hình response riêng.

## 13. Checklist QA trước khi triển khai

1. **Đúng stack:** Có dùng `ServerHttpSecurity`/`ServerAccessDeniedHandler`, không phải Servlet API?
2. **Đúng chain:** URL khớp chain với `exceptionHandling.accessDeniedHandler(...)` đã cấu hình?
3. **Chưa authenticated:** Request thiếu credential nhận 401/challenge hoặc login redirect theo mechanism, không thành 403 JSON tùy tiện?
4. **Sai credential:** Authentication failure không bị chuyển sai thành access denied?
5. **Đã authenticated nhưng thiếu role:** 403 thật với JSON code theo contract?
6. **Đủ role:** Request được phép, handler denied không chạy và business response chính xác?
7. **Method security:** Nếu dùng `@PreAuthorize`, denied từ service có được chuyển thành response mong muốn?
8. **CSRF:** Test riêng POST thiếu/sai token; có cần `csrf.accessDeniedHandler(...)` không?
9. **Bearer:** Token đủ/thiếu scope/hết hạn có `WWW-Authenticate` và error code theo RFC 6750?
10. **Error privacy:** Không lộ username, role thiếu, resource secret, stack trace, token hay cookie?
11. **Reactive response:** Handler trả `Mono<Void>`, không tự `block()`/`subscribe()`, không ghi sau commit?
12. **JSON schema:** `Content-Type` đúng, UTF-8, fields ổn định, không dựng JSON động bằng nối input raw?
13. **Cache:** Response lỗi được cache theo policy thích hợp; cân nhắc `no-store`?
14. **Frontend:** UI phân biệt 401 (cần login) và 403 (không đủ quyền), không retry token/password vô hạn?
15. **Multi-chain:** Nếu có web HTML và API JSON, matcher/order và fallback rõ ràng?
16. **Observability:** Log đủ trace/sanitized cause nhưng không log raw credentials hay secrets?
17. **Regression:** Có test HTTP status/body cho 401, 403 (HTTP + method), 200 và public?
18. **Deployment:** TLS, CORS, gateway/proxy, error mapping và version Spring Security đã được kiểm tra theo runtime thật?

## 14. Tự đánh giá có đáp án

**1.** User không gửi credentials tới `/api/admin/summary`. Có phải custom `ServerAccessDeniedHandler` JSON 403 chắc chắn được dùng không?

**Đáp án:** Không. Khi chưa authenticated, Spring Security thường bắt đầu authentication qua `ServerAuthenticationEntryPoint`, ví dụ HTTP Basic 401 và challenge.

**2.** User `reader` đã authenticated nhưng không có `ROLE_ADMIN`, handler nào chịu trách nhiệm?

**Đáp án:** Sau authorization denial trong WebFlux chain, `ServerAccessDeniedHandler` thường tạo 403, có thể là JSON custom.

**3.** `ServerAccessDeniedHandler` có thể tự cấp `ROLE_ADMIN` để cho phép request không?

**Đáp án:** Không nên và không phải trách nhiệm của nó. Quyền được quyết định bởi authentication và authorization; handler chỉ tạo error response.

**4.** Tại sao `POST /update` không CSRF token trả 403 mà body không giống JSON denied handler?

**Đáp án:** `CsrfWebFilter` có handler xử lý riêng, cấu hình qua `csrf.accessDeniedHandler(...)`; `exceptionHandling.accessDeniedHandler(...)` không phải lúc nào cũng xử lý lỗi CSRF.

**5.** Nếu resource server Bearer nhận token hợp lệ thiếu scope, việc thay denied handler bằng JSON-only có rủi ro gì?

**Đáp án:** Có thể làm mất Bearer `WWW-Authenticate`/`insufficient_scope` theo RFC 6750; cần giữ/chọn scheme-specific response.

**6.** Vì sao phản hồi 403 không nên chứa `denied.getMessage()`?

**Đáp án:** Message có thể chứa policy, authority, tên method, resource hoặc thông tin nội bộ. Dùng error code an toàn; ghi audit chi tiết có kiểm soát.

**7.** Gọi `jsonDeniedHandler.handle(...).subscribe()` rồi return `Mono.empty()` có đúng reactive không?

**Đáp án:** Không. Nó tách response write khỏi pipeline; có thể trả sớm, bỏ lỗi hoặc gây double commit. Trả Mono từ `writeWith`.

**8.** Phân biệt `ServerAuthenticationEntryPoint` và `ServerAccessDeniedHandler`?

**Đáp án:** Entry point bắt đầu authentication, thường 401/login redirect; denied handler xử lý user đã authenticated nhưng không đủ quyền, thường 403.

**9.** Có thể dùng `HttpStatusServerAccessDeniedHandler(HttpStatus.FORBIDDEN)` thay JSON handler không?

**Đáp án:** Có, nếu client không cần JSON body. Đây là implementation ngắn gọn để đặt HTTP status.

**10.** Khi nhiều `SecurityWebFilterChain`, handler của chain A có tự nhận denial từ chain B không?

**Đáp án:** Không mặc nhiên. Chỉ chain khớp đầu tiên được dùng cho request; cấu hình exception handling trên chain được chọn mới quyết định response.

## Tài liệu chính thức

- Spring Security 6.5 — `ServerAccessDeniedHandler` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authorization/ServerAccessDeniedHandler.html
- Spring Security 6.5 — `HttpStatusServerAccessDeniedHandler` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authorization/HttpStatusServerAccessDeniedHandler.html
- Spring Security 6.5 — `ServerHttpSecurity.ExceptionHandlingSpec`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.ExceptionHandlingSpec.html
- Spring Security 6.5 — `ServerHttpSecurity.CsrfSpec` (CSRF-specific denied handler): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.CsrfSpec.html
- Spring Security — `ExceptionTranslationWebFilter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/ExceptionTranslationWebFilter.html
- Spring Security — `ServerWebExchangeDelegatingServerAccessDeniedHandler`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/ServerWebExchangeDelegatingServerAccessDeniedHandler.html
- Spring Security — `BearerTokenServerAccessDeniedHandler`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/access/server/BearerTokenServerAccessDeniedHandler.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- RFC 6750 — OAuth2 Bearer token usage/errors: https://www.rfc-editor.org/rfc/rfc6750.html
