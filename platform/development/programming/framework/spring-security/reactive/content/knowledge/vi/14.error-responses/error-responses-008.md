# Ranh giới giữa lỗi WebFilter, @ControllerAdvice và WebExceptionHandler trong Spring Security WebFlux

## Mục tiêu bài học

Trong **Spring Security - reactive**, một request có thể bị từ chối ở nhiều giai đoạn trước khi controller chạy: WebFlux `WebFilter`, Spring Security `AuthenticationWebFilter`/`AuthorizationWebFilter`, CSRF, router/handler mapping, logic nghiệp vụ reactive, hoặc khi ghi response. Khi trả lỗi, cần chọn **đúng lớp xử lý**: `@ControllerAdvice`, `WebExceptionHandler` hoặc **security exception handlers**.

Bài thuộc nhóm **Phản hồi lỗi**, tập trung vào *ranh giới trách nhiệm* chứ không chỉ viết một class để trả JSON đẹp.

Sau bài học, bạn có thể:

1. Vẽ đúng đường đi từ Reactor Netty → `WebExceptionHandler` → `WebFilter` → `DispatcherHandler` → controller/handler.
2. Giải thích tại sao `@RestControllerAdvice` thường xử lý lỗi do controller và kết quả handler phát sinh, nhưng **không phải bộ xử lý lỗi tổng quát cho mọi WebFilter**.
3. Biết `WebExceptionHandler` có thể xử lý lỗi chưa được xử lý từ chuỗi WebFilter/`WebHandler` và cách `@Order` tương tác với error handler mặc định của Spring Boot.
4. Tách lỗi Spring Security **401 authentication** và **403 authorization/CSRF** khỏi lỗi business 4xx, lỗi filter 5xx, và lỗi ứng dụng 500.
5. Viết một `WebFilter` cố tình trả `Mono.error(...)`, một `@RestControllerAdvice` riêng và một `WebExceptionHandler` chỉ bắt loại lỗi được phép.
6. Xây dựng ví dụ **Java 17+, Spring Boot 3.3.13, Spring WebFlux, Spring Security** chạy được, kiểm thử bằng `WebTestClient`.
7. Xử lý đúng trường hợp response đã `isCommitted()`: không hứa sẽ đổi status/body sau khi response đã gửi.
8. Tránh các lỗi nguy hiểm: catch-all che lỗi authentication, nuốt exception thành `Mono.empty()`, ghi body hai lần, lộ stack trace/token và can thiệp sai thứ tự filter.
9. Dùng bảng quyết định để chọn nơi trả lỗi cho annotated controller, functional endpoint, authentication, authorization, filter, connection và lỗi sau commit.

**Phạm vi kỹ thuật:** `org.springframework.web.server.WebFilter` và `WebExceptionHandler` thuộc **WebFlux reactive**; `@ControllerAdvice` dùng mô hình annotated controller của WebFlux. Không nhầm với Servlet `Filter`, `OncePerRequestFilter`, `HandlerExceptionResolver` hoặc `ExceptionTranslationFilter` phía Servlet.

## 1. Bản đồ xử lý request và lỗi

Một sơ đồ khái quát (chi tiết mỗi phiên bản/config có thể khác) là:

```text
                 Reactor Netty / HTTP request
                            |
                            v
                 HttpWebHandlerAdapter
                            |
                            v
            WebExceptionHandler chain (lỗi chưa xử lý)
                            |
                            v
                   WebFilter chain
                            |
        +-------------------+--------------------+
        |                   |                    |
        v                   v                    v
  WebFilter tùy biến  Spring Security        Filter khác
                       WebFilterChainProxy
                        /             \
               authentication      authorization
                  |                    |
                401/redirect         403/401
                  |                    |
           handled inside Spring Security
                            |
                            v
                    DispatcherHandler
                            |
                    HandlerMapping
                            |
                    HandlerAdapter
                            |
                  @RestController method
                            |
              +-------------+---------------+
              |                             |
              v                             v
           Mono.value                   Mono.error(e)
              |                             |
              v                             v
         ResultHandler            @ExceptionHandler (local)
                                            |
                                            v
                                   @ControllerAdvice
                                            |
                              handled -> HTTP response
                              unhandled -> propagate
                                            |
                                            v
                         WebExceptionHandler chain / Boot fallback
```

Sơ đồ nhằm phân biệt **lớp trong/ngoài**. Trên thực tế, `DispatcherHandler` và `HandlerAdapter` hỗ trợ nhiều cơ chế xử lý lỗi bất đồng bộ; một số lỗi được sinh trong handler mapping hoặc result handling, không chỉ bên trong thân controller.

**Quy tắc học nhanh:**

- **Lỗi phát sinh từ `WebFilter` trước khi controller được chọn:** không trông chờ `@ControllerAdvice` là nơi bắt; dùng filter xử lý có chủ đích hoặc `WebExceptionHandler`.
- **Lỗi nghiệp vụ từ annotated controller/handler result:** `@ExceptionHandler` tại controller, rồi `@ControllerAdvice`, hoặc fallback global nếu không được xử lý.
- **Lỗi chưa được nơi nào xử lý:** `WebExceptionHandler` theo `@Order`; Spring Boot có error handler mặc định.
- **Lỗi xác thực/phân quyền:** ưu tiên `ServerAuthenticationEntryPoint`, `ServerAccessDeniedHandler` và các bộ lọc Spring Security, không dùng generic exception mapping để thay thế.
- **Response đã gửi:** status/headers/body không thể tùy tiện viết lại. Có thể cần kết thúc connection hoặc chỉ ghi log/metric thay vì sinh JSON lỗi mới.

## 2. Ba abstraction và sự khác biệt

### 2.1. WebFilter

`WebFilter` là hook chạy quanh chuỗi xử lý request:

```java
public interface WebFilter {
    Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain);
}
```

Một filter có thể:

- Kiểm tra request path/header trước khi vào handler.
- Đặt correlation ID, đo thời gian, kiểm tra precondition, thiết lập thuộc tính `ServerWebExchange`.
- Ngăn request đi tiếp bằng response phù hợp.
- Phát lỗi bằng `Mono.error(...)`.
- Đăng ký operator `doOnError`/`doFinally` quanh `chain.filter(exchange)` để quan sát kết quả downstream.

Ví dụ tối giản:

```java
return chain.filter(exchange)
        .doOnError(error -> {
            // Chỉ ghi metric hoặc log thông tin đã ẩn dữ liệu nhạy cảm.
            // doOnError không "nuốt" exception.
        });
```

**Sai lầm:** Mọi `WebFilter` có `onErrorResume` đều là “error handler cho cả hệ thống”. Một filter có thể nhìn lỗi downstream **chưa được xử lý** nhưng không nhất thiết thấy lỗi đã được `@ControllerAdvice`/Spring Security xử lý. Nó cũng không thể viết lại response sau commit một cách an toàn.

### 2.2. @ControllerAdvice / @RestControllerAdvice

`@ControllerAdvice` là cơ chế thuộc **annotated controller model**. Phương thức `@ExceptionHandler` có thể xử lý lỗi của controller hoặc result processing trong phạm vi handler được hỗ trợ.

`@RestControllerAdvice` ghép `@ControllerAdvice` với `@ResponseBody`, thích hợp trả JSON:

```java
@RestControllerAdvice
class ApiAdvice {
    @ExceptionHandler(DomainFailureException.class)
    ResponseEntity<ApiError> onDomainFailure(
            DomainFailureException ex) {

        return ResponseEntity.status(HttpStatus.UNPROCESSABLE_ENTITY)
                .body(new ApiError(
                        "BUSINESS_RULE", "Yêu cầu không hợp lệ theo nghiệp vụ"));
    }
}
```

Nó **không tự động trở thành global WebFilter exception interceptor**. Lỗi được phát ra bởi filter chạy trước `DispatcherHandler` có thể không có controller nào để áp dụng `@ExceptionHandler`. Spring Framework 6.x có cơ chế dispatch exception handling chi tiết hơn ở `HandlerAdapter`, nhưng không nên viết policy dựa trên suy luận rằng một `@ControllerAdvice` chắc chắn bắt mọi ngoại lệ trước handler.

**Không nên viết `@ExceptionHandler(Exception.class)` rồi đổi tất cả thành 200 hoặc 500** nếu chưa có chiến lược phân biệt `AccessDeniedException`, `AuthenticationException`, `ResponseStatusException`, binding errors và lỗi giao thức. Một catch-all có thể vô tình chiếm lỗi security của controller/method security trước khi `ExceptionTranslationWebFilter` xử lý.

### 2.3. WebExceptionHandler

`WebExceptionHandler` là abstraction của **WebFlux WebHandler API**:

```java
public interface WebExceptionHandler {
    Mono<Void> handle(ServerWebExchange exchange, Throwable ex);
}
```

Nó được dùng cho exception chưa được xử lý từ WebFilter chain và target WebHandler. Đăng ký một Spring bean và có thể dùng `@Order` để chỉ định ưu tiên.

- Trả `Mono<Void>` hoàn tất bình thường khi handler **đã xử lý được** lỗi và hoàn tất response.
- Trả `Mono.error(ex)` khi handler **không xử lý loại lỗi này** để handler tiếp theo có cơ hội.
- Kiểm tra `exchange.getResponse().isCommitted()` trước khi đặt status, header hoặc ghi body.
- Không nuốt mọi Throwable bằng `Mono.empty()`; như vậy có thể biến lỗi thành một response chưa nhất quán hoặc che lỗi bảo mật.
- Không giả định có một controller đã được chọn.
- Không log raw Authorization, session cookie, access token, password hay stack trace ra response.

Spring Boot 3.3 tự cung cấp `DefaultErrorWebExceptionHandler` cho các lỗi chưa được xử lý. Nó có thể trả HTML khi client muốn HTML và JSON cho machine client; nội dung phụ thuộc cấu hình `server.error.*` và content negotiation. Không đoán body cố định cho mọi phiên bản.

### 2.4. Bảng so sánh trách nhiệm

| Tiêu chí | `WebFilter` | `@RestControllerAdvice` | `WebExceptionHandler` |
| --- | --- | --- | --- |
| Có chạy trước router? | Có thể | Không phải tầng filter độc lập | Nằm trong global error processing |
| Nhận `ServerWebExchange` | Có | Có thể dùng trong handler method | Có |
| Xử lý lỗi controller reactive | Chỉ lỗi downstream chưa được nơi khác xử lý | Là nhiệm vụ chính | Nếu lỗi chưa được advice/handler giải quyết |
| Xử lý lỗi do filter trước controller | Tự xử lý hoặc phát lên | Không nên trông chờ | Có thể xử lý |
| Ký hợp đồng reactive | `Mono<Void> filter(...)` | `@ExceptionHandler` trả response body/`Mono`/`ResponseEntity` | `Mono<Void> handle(...)` |
| Ưu tiên | `@Order` của WebFilter | Local handler trước global advice, thứ tự advice riêng | `@Order` trong chuỗi WebExceptionHandler |
| Lỗi security 401/403 | Filter Spring Security thường tự xử lý | Không phải nơi mặc định để sửa status security | Chỉ lỗi security còn propagating, không phải đường chuẩn |
| Có thể viết HTTP body | Có, nếu chưa commit | Có qua message writer | Có trực tiếp hoặc qua cơ chế fallback |
| Phù hợp nhất | Cross-cutting, precondition, metrics | Business/API error từ controller | Fallback hoặc lỗi ở tầng WebHandler/filter |

**Hai thứ tự `@Order` độc lập:** `@Order(-200)` trên `WebFilter` không “đứng trước” `@Order(-2)` trên `WebExceptionHandler` trong **cùng danh sách**. Chúng thuộc hai chuỗi khác nhau, tạo ở các tầng khác nhau. Thứ tự nội bộ Spring Security filter lại là lớp khác.

## 3. Spring Security xử lý 401/403 ở đâu?

### 3.1. Lỗi xác thực

Một request cần đăng nhập nhưng không có credentials hoặc credentials sai có thể kết thúc bằng **401**, redirect đến form login hoặc phản hồi khác theo cơ chế xác thực.

Các thành phần liên quan:

- `ServerAuthenticationEntryPoint`: bắt đầu authentication khi request chưa có danh tính phù hợp; ví dụ Basic challenge/redirect.
- `AuthenticationWebFilter` và các authentication failure handler: giải quyết thất bại credentials của cơ chế cụ thể.
- `ExceptionTranslationWebFilter`: trong reactive security chain, chuyển `AccessDeniedException` của downstream thành entry point hoặc access denied handler tùy authentication state và policy.

Với HTTP Basic, client thường nhận **401** cùng `WWW-Authenticate`. Nếu bạn viết một catch-all `WebExceptionHandler` trả 500 cho `AuthenticationException` trước khi cơ chế Spring Security phản hồi, cấu trúc response có thể sai giao thức và gây rò rỉ thông tin.

### 3.2. Lỗi phân quyền

Khi user đã được xác thực nhưng thiếu role/scope, `AuthorizationWebFilter` hoặc method security có thể phát `AccessDeniedException`. Spring Security reactive thường dùng `ServerAccessDeniedHandler` để trả **403**.

**Chú ý:** Khi người dùng chưa xác thực, một authorization deny có thể được chuyển thành **401/redirect** thay vì 403. Do đó không suy mã HTTP chỉ từ tên exception; phải xét principal và entry point/handler đã cấu hình.

### 3.3. CSRF không phải lỗi business controller

Với browser POST dựa trên cookie/session, `CsrfWebFilter` có thể chặn request thiếu token **trước controller** và trả 403. `@RestControllerAdvice` bắt `IllegalArgumentException` không giải quyết được vấn đề này. Muốn sửa, kiểm tra request CSRF token, cookie, method và cấu hình chain; không tùy tiện `csrf.disable()`.

### 3.4. Tùy biến phản hồi bảo mật

Trong WebFlux, DSL của `ServerHttpSecurity` cho phép:

```java
http.exceptionHandling(spec -> spec
        .authenticationEntryPoint(entryPoint)
        .accessDeniedHandler(deniedHandler));
```

Đây là **mảnh cấu hình**, cần cung cấp các bean `ServerAuthenticationEntryPoint` và `ServerAccessDeniedHandler` thật, viết response đúng hợp đồng. Không dùng `HttpSecurity.exceptionHandling(...)` của Servlet trong dự án này.

**Điều quan trọng:** Tùy biến entry point cho HTTP Basic có thể vô tình làm mất header `WWW-Authenticate` nếu bạn chỉ đổi status sang 401 mà không giữ challenge. Với Resource Server Bearer, phải giữ các semantics liên quan `WWW-Authenticate: Bearer` và OAuth error codes theo chuẩn; không trả HTML form hay body tùy tiện cho mọi API. Vì vậy ví dụ chạy được ở mục sau **giữ cơ chế Basic mặc định**.

## 4. Mô hình luồng lỗi: "đã xử lý" và "chưa xử lý"

### 4.1. Lỗi trong filter sớm

```text
Request /api/filter-fail
  |
  v
PreRoutingFailureFilter (WebFilter, chạy trước security/router)
  |
  +--> Mono.error(FilterPhaseException)
            |
            +--> không có controller nào được chọn
            |
            v
  Custom WebExceptionHandler @Order(-2)
            |
            +--> nhận đúng loại FilterPhaseException
            +--> response chưa committed
            +--> HTTP 503 + JSON cố định
            |
            v
  Response hoàn tất
```

Trong tình huống này, `@RestControllerAdvice` không xử lý. Controller nếu có mapping trùng URL cũng **chưa được gọi**.

### 4.2. Lỗi từ controller Mono

```text
Request /api/business-fail
  |
  v
WebFilters -> Security permitAll -> DispatcherHandler
  |
  v
@RestController method -> Mono.error(DomainFailureException)
  |
  v
@RestControllerAdvice @ExceptionHandler(DomainFailureException.class)
  |
  +--> HTTP 422 + JSON code BUSINESS_RULE
  |
  v
Response hoàn tất, WebExceptionHandler không phải fallback cần dùng
```

Trả `Mono.error(...)` từ controller khác với việc tạo `Mono.just(...)` rồi ném exception ở nơi không thuộc publisher; cả hai có thể được framework xử lý trong nhiều tình huống, nhưng publisher error phải được subscribe trong flow của DispatcherHandler để advice có thể nhận.

### 4.3. Lỗi controller chưa có handler cụ thể

```text
Request /api/unhandled
  |
  v
@RestController -> Mono.error(IllegalStateException)
  |
  v
Không có @ExceptionHandler dành cho IllegalStateException
  |
  v
Error signal đi tới WebExceptionHandler chain
  |
  v
Spring Boot DefaultErrorWebExceptionHandler
  |
  +--> HTTP 500 + body tùy Accept/config (JSON/HTML)
```

Không coi Boot error JSON là một schema API công khai ổn định nếu chưa kiểm soát contract bằng tests. Mục tiêu của fallback là phản hồi an toàn; business API cần định nghĩa lỗi dự kiến riêng.

### 4.4. Lỗi 401/403

```text
GET /api/private (không credentials)
  -> Spring Security yêu cầu authentication
  -> HTTP Basic 401 + WWW-Authenticate
  -> không gọi controller

GET /api/admin (Basic user không có ROLE_ADMIN)
  -> authentication thành công
  -> authorization DENY
  -> Spring Security access denied handler
  -> HTTP 403, controller không chạy
```

Không có lý do ép hai luồng này qua một custom `@ControllerAdvice` trả 500.

## 5. Ví dụ hoàn chỉnh: WebFlux, filter, advice và global error handler

Ví dụ dùng **Java 17+, Spring Boot 3.3.13**, Gradle, Spring Security WebFlux. Mục tiêu không phải mô phỏng sản phẩm thật với DB; nó cố tình tạo ra các loại lỗi ở đúng giai đoạn để có thể **đối chiếu status/body/header bằng test**.

Các endpoint:

| Endpoint | Cơ chế | Expected |
| --- | --- | --- |
| `GET /api/public/ok` | Không cần login | 200 `OK` |
| `GET /api/business-fail` | Controller `Mono.error(DomainFailureException)` | 422 + code `BUSINESS_RULE` |
| `GET /api/filter-fail` | WebFilter sớm `Mono.error(FilterPhaseException)` | 503 + code `FILTER_FAILURE` |
| `GET /api/unhandled` | Controller `Mono.error(IllegalStateException)` | 500 từ Boot fallback |
| `GET /api/private` | Cần authenticated | Không credentials: 401 |
| `GET /api/admin` | Cần ROLE_ADMIN | User chỉ có ROLE_USER: 403 |

### 5.1. Cấu trúc dự án

```text
webflux-error-boundaries/
  settings.gradle
  build.gradle
  src/main/java/example/
    ErrorBoundaryApplication.java
    ApiController.java
    ApiError.java
    DomainFailureException.java
    FilterPhaseException.java
    PreRoutingFailureFilter.java
    ApiAdvice.java
    FilterFailureHandler.java
  src/test/java/example/
    ErrorBoundaryApplicationTests.java
```

### 5.2. Gradle

Tạo `settings.gradle`:

```groovy
rootProject.name = 'webflux-error-boundaries'
```

Tạo `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Boot BOM quản lý phiên bản Framework/Security/Reactor tương thích. Không thêm `spring-boot-starter-web` (MVC/Servlet) vào dự án WebFlux này.

### 5.3. ErrorBoundaryApplication.java

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.reactive
        .EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails
        .MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
@EnableWebFluxSecurity
public class ErrorBoundaryApplication {

    public static void main(String[] args) {
        SpringApplication.run(ErrorBoundaryApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(
                                "/api/public/**",
                                "/api/business-fail",
                                "/api/filter-fail",
                                "/api/unhandled")
                        .permitAll()
                        .pathMatchers("/api/admin")
                        .hasRole("ADMIN")
                        .anyExchange().authenticated())
                .httpBasic(withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails user = User.withUsername("alice")
                .password("{noop}learn")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(user);
    }
}
```

**Giải thích:**

- `@EnableWebFluxSecurity` kích hoạt reactive security chain.
- `/api/public/**` và ba URL lỗi có mục đích demo được phép truy cập không credentials để chỉ kiểm tra **nguồn phát lỗi**.
- `/api/admin` cần role ADMIN; `alice` chỉ có ROLE_USER nên bị 403 khi đã đăng nhập.
- `/api/private` không nằm trong permitAll, được `anyExchange().authenticated()` bảo vệ.
- `httpBasic(withDefaults())` đảm bảo 401 là Basic challenge hợp lệ.
- `formLogin(...disable())` tránh redirect form làm kết quả test 401 khó phân biệt.
- `{noop}learn` **chỉ dành cho môi trường học cục bộ**; production cần password encoder phù hợp, HTTPS, rate limiting và credential storage tốt.

### 5.4. Hai exception riêng

Tạo `src/main/java/example/DomainFailureException.java`:

```java
package example;

public class DomainFailureException extends RuntimeException {
    public DomainFailureException() {
        super("Demo business rule failed");
    }
}
```

Tạo `src/main/java/example/FilterPhaseException.java`:

```java
package example;

public class FilterPhaseException extends RuntimeException {
    public FilterPhaseException() {
        super("Demo pre-routing filter failure");
    }
}
```

Hai class giúp kiểm tra **đúng tầng** xử lý, không dựa vào text của một `IllegalStateException` chung chung. Trong sản phẩm thật, nên dùng exception type riêng cho domain, validation, access policy và lỗi hạ tầng, nhưng tránh tạo hàng chục class không có contract rõ ràng.

### 5.5. ApiError.java — response DTO

Tạo `src/main/java/example/ApiError.java`:

```java
package example;

public record ApiError(String code, String message) {
}
```

DTO tách mã lỗi ổn định (`code`) khỏi text hiển thị (`message`). Không đưa stack trace, chi tiết SQL, hash hoặc dữ liệu session vào response. Với API lớn, cân nhắc chuẩn `ProblemDetail`/RFC 9457 và đồng bộ request trace ID.

### 5.6. ApiController.java — lỗi từ controller

Tạo `src/main/java/example/ApiController.java`:

```java
package example;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/api/public/ok")
    public Mono<String> ok() {
        return Mono.just("OK");
    }

    @GetMapping("/api/business-fail")
    public Mono<String> businessFailure() {
        return Mono.error(new DomainFailureException());
    }

    @GetMapping("/api/unhandled")
    public Mono<String> unexpectedFailure() {
        return Mono.error(
                new IllegalStateException("demo unhandled exception"));
    }

    @GetMapping("/api/filter-fail")
    public Mono<String> shouldNotReachController() {
        return Mono.just("CONTROLLER_WAS_CALLED");
    }

    @GetMapping("/api/private")
    public Mono<String> privateEndpoint() {
        return Mono.just("PRIVATE_OK");
    }

    @GetMapping("/api/admin")
    public Mono<String> adminEndpoint() {
        return Mono.just("ADMIN_OK");
    }
}
```

Một controller mapping dành cho `/api/filter-fail` được cố ý thêm vào để chứng minh **filter chặn trước controller**. Nếu response thực là 503 với mã FILTER_FAILURE, handler này không chạy để trả `CONTROLLER_WAS_CALLED`.

`Mono.error(...)` chuyển lỗi vào reactive chain. `Mono.empty()` không phải lỗi; nếu trả empty ở controller, framework có thể hoàn tất response mà không sinh error JSON. Đừng sửa lỗi bằng cách nuốt exception thành empty khi client cần biết đã thất bại.

### 5.7. ApiAdvice.java — bắt đúng lỗi business

Tạo `src/main/java/example/ApiAdvice.java`:

```java
package example;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiAdvice {

    @ExceptionHandler(DomainFailureException.class)
    public ResponseEntity<ApiError> handleDomainFailure(
            DomainFailureException error) {

        return ResponseEntity
                .status(HttpStatus.UNPROCESSABLE_ENTITY)
                .header("X-Error-Handled-By", "controller-advice")
                .body(new ApiError(
                        "BUSINESS_RULE",
                        "Yeu cau khong thoa quy tac nghiep vu"));
    }
}
```

**Vì sao cố ý chỉ bắt `DomainFailureException`?**

- `@RestControllerAdvice` dùng annotated-controller error handling của DispatcherHandler.
- Nó không giành quyền xử lý `FilterPhaseException` đã phát trước khi controller được chọn.
- Nó không nuốt `AccessDeniedException`/`AuthenticationException` rồi biến sai status bảo mật.
- Nó không giành fallback `IllegalStateException` ngoài dự kiến; Boot có thể xử lý 500.
- Body chứa thông điệp an toàn được kiểm soát, không sao chép exception message hoặc stack trace trực tiếp.

Trong ứng dụng thật có thể cần `@ExceptionHandler(ResponseStatusException.class)`, validation exception handler hoặc subclass `ResponseEntityExceptionHandler` để tùy biến `ProblemDetail`. Mỗi handler nên có mục đích và thứ tự rõ ràng; không thêm blanket catch-all thiếu kiểm soát.

### 5.8. PreRoutingFailureFilter.java — phát lỗi trước controller

Tạo `src/main/java/example/PreRoutingFailureFilter.java`:

```java
package example;

import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
@Order(-200)
public class PreRoutingFailureFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String path = exchange.getRequest()
                .getPath().pathWithinApplication().value();

        if (exchange.getRequest().getMethod() == HttpMethod.GET
                && "/api/filter-fail".equals(path)) {
            return Mono.error(new FilterPhaseException());
        }

        return chain.filter(exchange);
    }
}
```

**Thứ tự:** Spring Boot 3.3 thường gắn WebFilterChainProxy của Spring Security ở order `-100`; `@Order(-200)` của filter demo đứng trước. Số này dùng để làm rõ lỗi phát sinh **trước Spring Security và DispatcherHandler**, không phải khuyến nghị luôn đặt mọi custom filter trước security.

**Không nên làm trong production:**

- Đọc/ghi security principal trước khi authentication filter tạo context rồi dùng nó như kết quả đã xác thực.
- Đặt filter có side effect hoặc check quyền tùy biến trước chain chuẩn mà không đánh giá các bypass.
- Tự viết status/body cho mọi exception chỉ bằng `onErrorResume(Exception.class, ...)`.
- Gọi `block()` hoặc dùng I/O blocking trên Netty event loop.
- Thực thi việc ghi HTTP response rồi tiếp tục `chain.filter(exchange)`; dễ ghi body hai lần.

Ví dụ này chỉ phát ra một exception type riêng cho đường test.

### 5.9. FilterFailureHandler.java — WebExceptionHandler có thứ tự

Tạo `src/main/java/example/FilterFailureHandler.java`:

```java
package example;

import java.nio.charset.StandardCharsets;

import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebExceptionHandler;
import reactor.core.publisher.Mono;

@Component
@Order(-2)
public class FilterFailureHandler implements WebExceptionHandler {

    @Override
    public Mono<Void> handle(ServerWebExchange exchange, Throwable error) {

        if (!(error instanceof FilterPhaseException)) {
            // Chuyển lỗi chưa thuộc trách nhiệm của handler này
            // sang WebExceptionHandler tiếp theo.
            return Mono.error(error);
        }

        if (exchange.getResponse().isCommitted()) {
            // Không thể đổi status/body sau khi response đã committed.
            return Mono.error(error);
        }

        var response = exchange.getResponse();
        response.setStatusCode(HttpStatus.SERVICE_UNAVAILABLE);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
        response.getHeaders().set("X-Error-Handled-By",
                "web-exception-handler");

        String payload = """
                {"code":"FILTER_FAILURE","message":"Filter rejected request"}
                """.trim();

        byte[] bytes = payload.getBytes(StandardCharsets.UTF_8);

        return response.writeWith(Mono.just(
                response.bufferFactory().wrap(bytes)));
    }
}
```

**Giải thích contract:**

1. Chỉ `FilterPhaseException` được xử lý; exception khác được trả `Mono.error(error)` cho handler kế tiếp.
2. Nếu response đã `isCommitted()` thì không viết lại. Không có "rollback response" tổng quát.
3. Đặt `503 Service Unavailable`, content type JSON và header chứng minh nơi xử lý.
4. Payload cố định nên không lấy dữ liệu input nhạy cảm hoặc message tùy ý đưa vào JSON thủ công. Khi cần body động, nên dùng serializer được kiểm soát để escape đúng thay vì ghép chuỗi JSON từ client input.
5. `writeWith(Mono.just(buffer))` tạo một publisher ghi body và hoàn tất theo contract `Mono<Void>`. Không gọi `subscribe()` rời rạc.
6. `@Order(-2)` đưa handler này **đứng trước error handler mặc định của Boot** vốn thường order `-1` trong cấu hình Boot 3.3; không thay thế handler mặc định của Boot cho exception khác.
7. Dùng một loại exception chuyên biệt giúp giảm rủi ro bắt nhầm lỗi authentication/authorization.

**Cảnh báo về `@Order`:** Chỉ so sánh order với **các WebExceptionHandler khác**. Đừng so `@Order(-2)` ở đây với `@Order(-200)` của WebFilter như thể chúng nằm chung một chuỗi.

Trong ứng dụng lớn, nếu muốn format JSON lỗi thống nhất, có thể thay mảnh code viết JSON cố định bằng một utility dùng `ObjectMapper`/`ServerCodecConfigurer` phù hợp, nhưng phải xử lý lifecycle của DataBuffer và tránh write sau commit. Đây là trách nhiệm cấp framework chứ không đơn giản gọi controller advice từ filter.

## 6. Chạy thử bằng HTTP và đối chiếu

Yêu cầu **JDK 17+**, Gradle tương thích với Spring Boot 3.3.13.

```bash
gradle bootRun
```

Nếu dự án đã có Gradle Wrapper, dùng `./gradlew bootRun` (Linux/macOS) hoặc `gradlew.bat bootRun` (Windows).

Terminal khác:

```bash
curl -i http://localhost:8080/api/public/ok
curl -i http://localhost:8080/api/business-fail
curl -i http://localhost:8080/api/filter-fail
curl -i http://localhost:8080/api/unhandled
curl -i http://localhost:8080/api/private
curl -i -u alice:learn http://localhost:8080/api/private
curl -i -u alice:learn http://localhost:8080/api/admin
```

Kết quả kỳ vọng của ứng dụng demo:

| Request | Status | Handler | Dấu hiệu |
| --- | --- | --- | --- |
| Public OK | 200 | Controller | Body `OK` |
| Business fail | 422 | `ApiAdvice` | Header `X-Error-Handled-By: controller-advice`, code `BUSINESS_RULE` |
| Filter fail | 503 | `FilterFailureHandler` | Header `X-Error-Handled-By: web-exception-handler`, code `FILTER_FAILURE` |
| Unhandled | 500 | Boot fallback `DefaultErrorWebExceptionHandler` | Body phụ thuộc `Accept`/`server.error.*` |
| Private không credentials | 401 | Spring Security | Basic challenge |
| Private với Basic alice | 200 | Controller | Body `PRIVATE_OK` |
| Admin với Basic alice | 403 | Spring Security | Thiếu `ROLE_ADMIN` |

Mục tiêu là **phân biệt đường đi**. Không lấy header `X-Error-Handled-By` làm tiêu chuẩn production hay yêu cầu an ninh; đây là công cụ quan sát của bài demo. Kết quả body Boot fallback không phải chuỗi cố định giữa các bản Spring Boot, nên test chủ yếu status 500.

Nếu gửi `Accept: text/html`, Boot fallback có thể render HTML error view, còn custom `FilterFailureHandler` ở ví dụ luôn trả JSON. Đây là lựa chọn của handler, không có content negotiation tự động cho body tự viết. API sản xuất cần hợp đồng media type rõ ràng.

## 7. Kiểm thử đầy đủ bằng WebTestClient

Tạo `src/test/java/example/ErrorBoundaryApplicationTests.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive
        .AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.boot.test.context.SpringBootTest
        .WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
@AutoConfigureWebTestClient
class ErrorBoundaryApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicRouteIsOk() {
        client.get().uri("/api/public/ok")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("OK");
    }

    @Test
    void controllerErrorIsHandledByAdvice() {
        client.get().uri("/api/business-fail")
                .exchange()
                .expectStatus().isEqualTo(422)
                .expectHeader()
                .valueEquals("X-Error-Handled-By",
                        "controller-advice")
                .expectBody()
                .jsonPath("$.code").isEqualTo("BUSINESS_RULE");
    }

    @Test
    void filterErrorIsHandledByWebExceptionHandler() {
        client.get().uri("/api/filter-fail")
                .exchange()
                .expectStatus().isEqualTo(503)
                .expectHeader()
                .valueEquals("X-Error-Handled-By",
                        "web-exception-handler")
                .expectBody()
                .jsonPath("$.code").isEqualTo("FILTER_FAILURE");
    }

    @Test
    void unexpectedControllerErrorFallsBackToBoot() {
        client.get().uri("/api/unhandled")
                .header(HttpHeaders.ACCEPT, "application/json")
                .exchange()
                .expectStatus().is5xxServerError();
    }

    @Test
    void unauthenticatedPrivateRequestGetsBasicChallenge() {
        client.get().uri("/api/private")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().exists(
                        HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void authenticatedUserCanAccessPrivateEndpoint() {
        client.get().uri("/api/private")
                .headers(h -> h.setBasicAuth("alice", "learn"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("PRIVATE_OK");
    }

    @Test
    void authenticatedNonAdminGetsForbidden() {
        client.get().uri("/api/admin")
                .headers(h -> h.setBasicAuth("alice", "learn"))
                .exchange()
                .expectStatus().isForbidden();
    }
}
```

Chạy:

```bash
gradle test
```

### Các test này xác minh điều gì?

- **200:** request đi qua filters tới controller bình thường.
- **422:** `@RestControllerAdvice` xử lý exception type từ annotated controller.
- **503:** WebFilter phát lỗi trước controller, một `WebExceptionHandler` riêng xử lý; không bị advice nuốt.
- **500:** lỗi controller không được advice xử lý, đi tới fallback global.
- **401:** Spring Security entry point phản hồi challenge; không có business controller response.
- **403:** user có Authentication nhưng thiếu quyền; không có handler body `ADMIN_OK`.

Đây là test tích hợp trên ứng dụng Spring Boot thật qua WebTestClient. Các test không chứng minh mọi lỗi streaming/commit, không kiểm tra Netty load, và không bảo đảm production đã có policy cho 404/validation; cần thêm test theo runtime/route thực.

## 8. Ranh giới response đã committed

Đây là ca thường gây lỗi khó hiểu nhất khi xử lý reactive streams.

### 8.1. Khi response chưa committed

Nếu lỗi phát sinh trước khi status/headers/body được gửi, handler có thể:

- Đặt status thích hợp;
- Đặt `Content-Type`, cache control và header an toàn;
- Serialize một body JSON nhỏ;
- Hoàn tất response hoặc cho handler khác xử lý.

### 8.2. Khi response đã committed

Giả sử handler bắt đầu ghi một `Flux`:

```text
HTTP/1.1 200 OK
Content-Type: application/json

[{"id":1},
 ... lỗi phát sinh sau khi một phần body đã gửi ...
```

Không thể thay response đang truyền thành:

```text
HTTP/1.1 500 Internal Server Error
{"error":"failed"}
```

vì status line và một phần body **đã gửi cho client**. `ServerHttpResponse.isCommitted()` thể hiện việc đó. Cách xử lý thường là ghi nhận lỗi và chấm dứt stream/connection theo hành vi hạ tầng, hoặc dùng định dạng streaming (SSE/gRPC protocol-level errors) có semantics lỗi riêng. Không viết thêm một object JSON lỗi vào giữa một JSON array chưa hoàn tất rồi coi là response hợp lệ.

### 8.3. Ví dụ minh họa lỗi giữa stream

```java
// MẢNH MINH HỌA, không ghép vào demo hoàn chỉnh.
@GetMapping(value = "/api/stream",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<String> stream() {
    return Flux.concat(
            Flux.just("first", "second"),
            Flux.error(new IllegalStateException(
                    "downstream stream failure")));
}
```

Đối với SSE, một phần sự kiện có thể đã được ghi. `@ControllerAdvice`/`WebExceptionHandler` không được bảo đảm còn khả năng viết lại HTTP 200 thành 500. Muốn truyền lỗi **ở cấp giao thức ứng dụng** khi stream đã mở, có thể thiết kế event SSE `event: error` có schema phù hợp (không tiết lộ nội bộ) và xử lý trực tiếp trong stream; khác với việc đổi HTTP status.

**Quan trọng:** `onErrorResume` trong stream có thể phục hồi bằng một event hợp lệ **nếu protocol cho phép**. Nhưng không được đổi lỗi database hay phân quyền thành dữ liệu thành công giả tạo; phải có contract rõ ràng cho client phân biệt partial success và failure.

## 9. @ControllerAdvice với functional endpoints và handler mapping

Spring WebFlux có hai mô hình lập route:

1. **Annotated controllers:** `@RestController`, `@RequestMapping`, `@ExceptionHandler` và `@ControllerAdvice`.
2. **Functional endpoints:** `RouterFunction<ServerResponse>` và `HandlerFunction<ServerResponse>`.

`@ControllerAdvice` không phải cơ chế mặc định áp dụng trực tiếp lên mọi functional `HandlerFunction`. Với functional routing, có thể xử lý error trong publisher, tại router/handler filter hoặc để `WebExceptionHandler`/Boot fallback xử lý.

Ví dụ xử lý lỗi ngay trong functional handler (mảnh code minh họa):

```java
Mono<ServerResponse> response =
        businessService.execute()
            .flatMap(value ->
                    ServerResponse.ok().bodyValue(value))
            .onErrorResume(DomainFailureException.class,
                ex -> ServerResponse.status(422)
                        .bodyValue(new ApiError(
                                "BUSINESS_RULE",
                                "Yeu cau khong thoa quy tac")));
```

Đoạn này cần `businessService` và các imports của RouterFunction API để dùng, không phải file tự chạy. Điểm quan trọng: **functional handler quyết định cách biến domain exception thành ServerResponse** nếu không muốn nhờ global error handler.

Lỗi handler mapping trước khi controller tồn tại có thể được framework map thành HTTP 404/405/400 qua các cơ chế tích hợp; không được kết luận mọi lỗi đó đều chạy qua `@ControllerAdvice` do ta viết. Với WebFlux 6.x, `DispatchExceptionHandler` của `HandlerAdapter` có thể hỗ trợ một số lỗi trước/ngoài handler invocation, nhưng nó **không biến advice thành một filter tổng quát**.

### 9.1. @ExceptionHandler tại controller và global advice

Nếu controller có:

```java
@RestController
class LocalController {

    @GetMapping("/api/local-error")
    public Mono<String> fail() {
        return Mono.error(new DomainFailureException());
    }

    @ExceptionHandler(DomainFailureException.class)
    public ResponseEntity<ApiError> localHandler(
            DomainFailureException ex) {
        return ResponseEntity.status(409)
                .body(new ApiError(
                        "LOCAL_FAILURE", "Handled locally"));
    }
}
```

và đồng thời có global `@RestControllerAdvice` bắt `DomainFailureException`, **local @ExceptionHandler** của controller được áp dụng trước global advice cho controller đó. Nếu nhiều advice có `@Order` khác nhau hoặc scope selectors, việc lựa chọn handler có quy tắc riêng. Không so thứ tự advice với `@Order` của WebFilter/WebExceptionHandler.

## 10. Spring Boot ErrorWebExceptionHandler và ProblemDetail

Spring Boot tự cấu hình `DefaultErrorWebExceptionHandler` (implementation của `ErrorWebExceptionHandler`/`WebExceptionHandler`) để xử lý lỗi còn lại. Nó sử dụng `ErrorAttributes` và có thể render JSON hoặc HTML error view tùy `Accept`/đường template.

Với REST API, nên chọn một contract lỗi nhất quán. Spring Framework hỗ trợ **RFC 9457 Problem Details** qua `ProblemDetail`, `ErrorResponse` và `ResponseEntityExceptionHandler`.

Ví dụ cho business exception trong annotated controller:

```java
// Mảnh minh họa thay cho handler @ExceptionHandler
// trong ApiAdvice khi chọn RFC 9457.
@ExceptionHandler(DomainFailureException.class)
public ResponseEntity<ProblemDetail> problem(
        DomainFailureException ex) {

    ProblemDetail body = ProblemDetail.forStatus(422);
    body.setTitle("Business rule denied");
    body.setDetail("Request violates a business rule");
    body.setProperty("code", "BUSINESS_RULE");

    return ResponseEntity.status(422).body(body);
}
```

Đây là mảnh code, yêu cầu import `ProblemDetail` và các annotation/ResponseEntity tương ứng, không phải một class riêng hoàn chỉnh. `ProblemDetail` giúp có các trường `type/title/status/detail/instance` theo chuẩn; response có thể sử dụng `application/problem+json` qua message converters khi content negotiation phù hợp.

**Không cố ép mọi mã lỗi Spring Security thành ProblemDetail bằng catch-all ở advice.** 401/403 có semantics authentication/authorization (WWW-Authenticate, redirect, credentials/session) và nên được điều khiển ở Spring Security chain. Bạn có thể xây chung một formatter giúp `ServerAuthenticationEntryPoint`, `ServerAccessDeniedHandler` và application handlers sử dụng cùng schema, nhưng cần triển khai **đúng từng interface**.

### Một lựa chọn của Spring Boot 3.x

Property `spring.webflux.problemdetails.enabled` có thể kích hoạt hỗ trợ Problem Details cho các lỗi WebFlux chuẩn do Boot quản lý. Cơ chế này không thay thế hoàn toàn custom domain mapping hoặc entry point/denied handler của Spring Security. Nếu bật property, hãy kiểm tra thứ tự `@ControllerAdvice` với framework advice và chạy lại test 400/404/405/415, thay vì đoán thứ tự mặc định.

**Không gửi exception message tùy ý** tới client nếu message có thể chứa SQL, file path, user ID nhạy cảm hoặc thông tin implementation. Với lỗi 500, phản hồi nên dùng thông điệp trung tính và correlation ID; log nội bộ chứa error đầy đủ dưới quyền truy cập phù hợp.

## 11. Debug: tại sao lỗi không được handler mình mong đợi bắt?

### 11.1. Lỗi phát sinh trước controller

Triệu chứng: `@ExceptionHandler(Exception.class)` chưa từng được gọi dù request trả 500.

Kiểm tra:

- Exception đến từ `WebFilter`, CORS, Spring Security, codec đọc request hay handler mapping?
- Request đã chọn annotated handler chưa?
- Có `WebExceptionHandler`/Boot fallback đang nhận error không?
- Filter có trả `Mono.error` hay tự ghi response rồi kết thúc?

Hướng xử lý: xác định **tầng phát lỗi**, không đơn giản thêm catch-all advice. Với lỗi filter đặc thù, dùng custom `WebExceptionHandler` theo loại exception hoặc xử lý đúng tại filter nếu contract rõ.

### 11.2. 401/403 bị đổi thành 500

Nếu controller/method security phát `AccessDeniedException`, một `@ExceptionHandler(Exception.class)` có thể nhận trước bộ lọc Security tùy đường propagation và trả 500. Hoặc custom `WebExceptionHandler` bắt generic Throwable rồi ghi body 500.

Kiểm tra và thu hẹp handler; để `AuthenticationException`/`AccessDeniedException` đi qua security handlers nếu chúng là lỗi bảo mật, hoặc định nghĩa handler bảo mật bằng DSL reactive `exceptionHandling(...)`. Tuyệt đối không đổi lỗi 403 thành 200 chỉ để client không gặp error.

### 11.3. WebExceptionHandler không bắt exception

Nguyên nhân có thể là:

- Loại exception không khớp với điều kiện `instanceof` của handler.
- Một handler có order cao hơn đã xử lý trước.
- `@ControllerAdvice`/Spring Security xử lý và hoàn tất response, nên error không còn propagate.
- Response đã committed, không thể viết lại.
- Lỗi xảy ra ngoài Reactor pipeline của request do code gọi `subscribe()` riêng, scheduler/background task không quản lý, hay I/O được xử lý không đúng subscription.

Không khắc phục bằng cách cho handler nhận mọi `Throwable` rồi trả 200. Hãy dùng `doOnError`, correlation ID và test đúng lớp.

### 11.4. HTTP status đúng nhưng body khác

- Basic 401 có `WWW-Authenticate`, body có thể không theo schema business.
- Boot error handler dùng content negotiation; `Accept: text/html` có thể nhận HTML.
- Default 404/405/415 thường do framework, không phải `DomainFailureException`.
- Nếu app bật ProblemDetail, content type có thể là `application/problem+json`.
- Nếu response đã committed, client có thể nhận body dở dang hoặc connection reset.
- Proxy/gateway có thể thay error page. Test trực tiếp app và qua ingress cần tách riêng.

### 11.5. Exception bị nuốt bởi onErrorResume

```java
// SAI: biến lỗi thành hoàn tất bình thường, có thể để client
// hiểu request thành công hoặc response đang dở dang.
return chain.filter(exchange)
        .onErrorResume(error -> Mono.empty());
```

Thay bằng xử lý **đúng loại** nếu filter thật sự chịu trách nhiệm:

```java
// Mảnh minh họa: chỉ log rồi truyền lỗi đến global handlers.
return chain.filter(exchange)
        .doOnError(error -> recordFailureType(error));
```

`recordFailureType` ở đây là helper của ứng dụng, chỉ ghi thông tin an toàn; mảnh code không biên dịch độc lập. Không dùng `doOnError` để ghi response hoặc thay status, vì operator này không chuyển signal lỗi thành response.

## 12. Kiểm soát thứ tự và không tạo handler toàn năng

### 12.1. Ba phạm vi thứ tự

| Cấp | Thành phần | Thứ tự |
| --- | --- | --- |
| Global WebFilter | `@Order` hoặc `Ordered` trên filter bean | Tác động vị trí filter trong chuỗi request |
| Spring Security chain | `@Order` trên `SecurityWebFilterChain` + `securityMatcher`; `SecurityWebFiltersOrder` ở bên trong | Chọn chain và trình tự filter security |
| Global WebExceptionHandler | `@Order` hoặc `Ordered` trên handler bean | Xác định handler nào được thử trước khi fallback |

`@ControllerAdvice` có hệ thống lựa chọn handler riêng: local controller `@ExceptionHandler` thường ưu tiên hơn global; giữa nhiều advice, `@Order`/scope selectors có tác dụng theo mô hình handler resolution. Không gộp các thứ tự vào một danh sách số duy nhất.

### 12.2. Vì sao không tạo một WebExceptionHandler "bắt hết"?

Ví dụ nguy hiểm:

```java
// SAI VỀ CHIẾN LƯỢC: nuốt mọi lỗi và giả lập thành công.
@Override
public Mono<Void> handle(ServerWebExchange exchange, Throwable ex) {
    exchange.getResponse().setStatusCode(HttpStatus.OK);
    return exchange.getResponse().setComplete();
}
```

Lỗi database, JSON parse, authentication, authorization và response commit có thể bị che khuất. Client nhận 200 dù thao tác thất bại; monitoring thiếu tín hiệu; lỗi an ninh không còn status đúng.

Bộ xử lý global tốt nên:

1. Chỉ nhận **loại exception do nó được giao**.
2. Kiểm tra response chưa committed.
3. Ghi status và body đúng protocol, không lộ dữ liệu nhạy cảm.
4. Khi không thuộc trách nhiệm, **truyền error** cho handler tiếp theo.
5. Giữ `onError` khi xử lý bản thân handler thất bại, tránh vòng lặp/đệ quy.
6. Có test 401/403 trước và sau khi thêm handler.
7. Ghi metric lỗi theo code/giai đoạn, không theo raw message có thể chứa PII.
8. Giữ fallback Boot để không bỏ sót exception ngoài danh sách dự kiến.

### 12.3. Trường hợp filter phải từ chối có chủ đích

Nếu filter thực thi một precondition rõ ràng và muốn trả 429/503, đôi khi việc **trực tiếp trả response từ filter** đơn giản hơn phát exception rồi dùng global handler. Ví dụ, rate limiter có thể viết status 429 và `Retry-After` theo contract của nó.

Nhưng nếu đã viết status/body trong filter, **không tiếp tục `chain.filter(exchange)`** và không đồng thời phát exception để handler global viết lại. Chọn một chủ sở hữu response cho mỗi đường đi.

Đối với **quyền truy cập**, ưu tiên Spring Security `ReactiveAuthorizationManager` và exception handling của security; đừng tạo custom filter kiểm tra `X-Role` rồi tự trả 403 chỉ vì dễ hơn. Tách trách nhiệm business/security/network để giảm bypass.

## 13. Lỗi sau commit, logging và vận hành

### 13.1. Log ở nơi nào?

- **WebFilter đo lường:** `doOnError` để log kết quả của downstream chưa xử lý, `doFinally` để đo thời gian.
- **Controller advice:** log business code, HTTP status và correlation ID; không log stack trace liên tục cho lỗi 4xx dự kiến.
- **WebExceptionHandler:** log lỗi bất thường ở tầng filter/handler mà nó chịu trách nhiệm; phân biệt lỗi đã committed.
- **Security:** dùng audit/events/metrics cho authentication fail, access denied, CSRF failure, không log credentials.
- **Boot fallback:** giữ observability cho lỗi 500 không có handler riêng.

Tránh **log trùng**: một lỗi có thể đi qua filter, custom handler và global fallback. Dùng một correlation ID/request ID và event-type thống nhất để không đếm cùng exception ba lần như ba sự cố.

### 13.2. Mã lỗi API ổn định

Nên có:

```json
{
  "code": "BUSINESS_RULE",
  "message": "Request violates a business rule"
}
```

hoặc chuẩn `ProblemDetail`/RFC 9457. Không dùng `Throwable.getMessage()` làm field `code`, vì message có thể đổi theo phiên bản, chứa dữ liệu riêng hoặc khó dịch. Nếu cần thêm request ID, lấy từ nguồn có độ tin cậy phù hợp và sanitize trước khi echo.

### 13.3. Chống lộ thông tin qua lỗi

Không trả cho client:

- Stack trace Java hoặc package/class nội bộ.
- SQL query, database hostname/password, secret, session ID.
- Authorization/Bearer token hoặc cookie `SESSION`.
- Thông tin “tài khoản này tồn tại”, “tài khoản bị khóa” quá chi tiết tại login nếu giúp enumeration.
- Raw URL/query từ request chứa dữ liệu nhạy cảm khi chưa được redacted.
- Thông tin chính sách ACL/tenant nội bộ không cần công khai.

Ứng dụng Spring Boot có `server.error.include-message`, `server.error.include-stacktrace` và lựa chọn lỗi khác. Không bật kiểu luôn đưa stacktrace/message thô vào phản hồi production.

### 13.4. Phân biệt lỗi application và lỗi giao thức

Một số lỗi có chủ sở hữu khác:

| Lỗi | Chủ sở hữu phù hợp |
| --- | --- |
| Body JSON sai cấu trúc | WebFlux binding/codec handling, built-in error response hoặc advice có chủ đích |
| Không có handler 404 | DispatcherHandler/Boot fallback/status handler theo version |
| HTTP method không hỗ trợ 405 | WebFlux mapping & error response |
| Business state invalid 422 | Domain `@ExceptionHandler`/`@RestControllerAdvice` |
| Filter dependency outage 503 | Filter xử lý có chủ đích hoặc custom `WebExceptionHandler` |
| Uncaught IllegalStateException 500 | Global fallback `WebExceptionHandler`/Boot |
| Chưa xác thực 401 | Spring Security `ServerAuthenticationEntryPoint` |
| Xác thực sai credential | Authentication failure handler/entry point tùy mechanism |
| Đã xác thực, thiếu quyền 403 | Spring Security `ServerAccessDeniedHandler` |
| CSRF token sai 403 | Spring Security `CsrfWebFilter` |
| Stream lỗi sau commit | Protocol streaming/connection termination, không thể đổi HTTP status |

Một endpoint dùng functional `RouterFunction` nên xem cơ chế xử lý lỗi của functional endpoint/global handler thay vì giả định annotated `@RestControllerAdvice` luôn được gọi.

## 14. Checklist kiểm tra trước production

1. **Lỗi thuộc giai đoạn nào?** Before filter, security, handler mapping, annotated controller, functional handler, DB hay streaming response.
2. **Có handler cụ thể không?** Domain exception map tại advice; filter type riêng map tại WebExceptionHandler; Boot fallback cho unexpected.
3. **Auth status chuẩn chưa?** 401 vẫn có challenge/redirect đúng, 403 không biến thành 200/500.
4. **Mỗi response một chủ sở hữu:** Không ghi body hai lần, không tiếp tục chain sau khi filter đã kết thúc response.
5. **Kiểm tra isCommitted:** Không viết status/body mới sau commit.
6. **Thứ tự rõ ràng:** Global WebFilter, SecurityWebFilterChain và WebExceptionHandler có priority riêng.
7. **Mã lỗi ổn định:** Dùng code/schema hoặc ProblemDetail; không trả raw exception text.
8. **Không nuốt Mono.error:** Không `onErrorResume(e -> Mono.empty())` rộng, không `onErrorReturn(success)`.
9. **Không block event loop:** Không `block()`, JDBC/HTTP client sync trong error handler; ghi response phải compose `Mono<Void>`.
10. **Đã test negative:** Business 422, filter 503, unexpected 500, Basic 401, role 403, CSRF 403 khi phù hợp.
11. **Kiểm thử sau commit:** Streaming/SSE, partial body, connection close, client timeout và proxy behavior.
12. **Không leak dữ liệu:** Log an toàn, mask headers/PII, không expose stack trace.
13. **Không đổi mặc định mù quáng:** Bật ProblemDetail hoặc custom error handler phải kiểm tra 404/405/415/validation/CSRF regression.
14. **Quan sát:** Metrics theo route/status/error code/correlation ID và kiểm tra handler nào đã xử lý.

## 15. Câu hỏi tự kiểm tra

**1. Lỗi từ WebFilter chạy trước DispatcherHandler có tự rơi vào @ControllerAdvice không?**  
Không nên kỳ vọng. `@ControllerAdvice` gắn với annotated controller error handling; lỗi filter trước routing thường cần được giải quyết tại filter hoặc `WebExceptionHandler`.

**2. @RestControllerAdvice khác WebExceptionHandler ở đâu?**  
Advice dùng `@ExceptionHandler` trong mô hình annotated controller; WebExceptionHandler là component global WebFlux handler cho lỗi chưa được giải quyết từ WebFilter/WebHandler.

**3. Nếu @ControllerAdvice đã xử lý DomainFailureException thì WebExceptionHandler còn thấy lỗi đó không?**  
Thông thường không, vì error đã được chuyển thành response thành công ở tầng advice. WebExceptionHandler dành cho signal lỗi chưa xử lý.

**4. Vì sao Basic request chưa đăng nhập nên trả 401 chứ không chuyển tất cả thành 500?**  
Đó là yêu cầu xác thực, phải đi qua `ServerAuthenticationEntryPoint`/security mechanism. 500 biểu thị lỗi server, không phải client thiếu credentials.

**5. User có ROLE_USER gửi GET /api/admin trong demo, nơi nào phản hồi?**  
Spring Security authorization/access denied handler trả 403; controller không chạy.

**6. Trong WebExceptionHandler, không nhận loại lỗi thì làm gì?**  
Trả `Mono.error(error)` để handler tiếp theo xử lý. Không dùng `Mono.empty()` để coi là đã xử lý.

**7. isCommitted() == true có thể đổi status từ 200 sang 500 không?**  
Không. Headers/status đã gửi, không thể viết lại nguyên response. Phải xử lý theo semantics streaming/connection và quan sát lỗi.

**8. Hai annotation @Order(-200) trên WebFilter và @Order(-2) trên WebExceptionHandler so sánh trực tiếp được không?**  
Không. Chúng thuộc hai chain riêng với các vai trò khác nhau.

**9. Vì sao không viết @ExceptionHandler(Exception.class) trả 200 "OK"?**  
Nó che lỗi business/security/framework và làm client hiểu sai trạng thái; có thể dẫn tới bypass hoặc mất giám sát.

**10. Khi Boot fallback trả HTML thay vì JSON có phải @ControllerAdvice bị lỗi không?**  
Không nhất thiết. Boot error handler có content negotiation; hãy kiểm tra `Accept` và `server.error.*`, cùng xem exception có thuộc phạm vi advice không.

**11. Lỗi từ functional RouterFunction có được @RestControllerAdvice của annotated controller bắt tự động không?**  
Không nên giả định. Dùng error handling của functional pipeline hoặc global `WebExceptionHandler` khi cần.

**12. Vì sao phải test cả 401 và 403 sau khi thêm custom WebExceptionHandler?**  
Để đảm bảo handler mới không nuốt lỗi security, phá challenge/redirect hoặc đổi deny thành 500/200.

**13. Mono.empty từ WebFilter là lỗi hay thành công?**  
`Mono.empty()`/`Mono<Void>` hoàn tất bình thường chỉ là completion; không phải error signal. Nếu filter trả complete sớm mà chưa thiết lập response thích hợp, client có thể nhận response không như mong đợi.

**14. CSRF 403 có nên đưa vào @RestControllerAdvice để trả status khác không?**  
Không mặc định. Cần sửa token/session/method hoặc tùy biến security handler đúng chỗ, không dùng business advice để bypass CSRF.

**15. Làm sao chứng minh controller chưa chạy ở /api/filter-fail?**  
Nó có handler sẽ trả `CONTROLLER_WAS_CALLED`, nhưng test nhận 503 với code `FILTER_FAILURE` từ WebExceptionHandler; filter đã chặn luồng trước controller.

**Tóm lại:** Muốn phản hồi lỗi đúng trong Spring Security WebFlux, phải biết **lỗi sinh ra tại đâu, tín hiệu nào chưa được xử lý và response đã committed chưa**. Business exception từ annotated controller thuộc `@ControllerAdvice`; lỗi pre-routing/filter chưa xử lý thuộc `WebExceptionHandler` hoặc filter có chủ đích; 401/403 thuộc Spring Security entry point/denied handlers; lỗi bất ngờ còn lại do Spring Boot fallback. Thiết kế đúng ranh giới giúp giữ HTTP semantics, an toàn thông tin và khả năng điều tra lỗi.

## Tài liệu tham khảo

- [Spring Framework — WebFlux Reactive Core / Exceptions](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html): `WebFilter`, `WebExceptionHandler`, WebHandler chain và `@Order`.
- [Spring Framework — WebFlux @ControllerAdvice](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-advice.html): phạm vi annotated controller, `@ExceptionHandler` local/global, `@RestControllerAdvice`.
- [Spring Framework — DispatcherHandler Exceptions](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/dispatcher-handler.html): xử lý exception trong handler adapter, result handling và dispatch pipeline.
- [Spring Framework — WebFlux Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html): `ProblemDetail`, `ErrorResponse`, `ResponseEntityExceptionHandler`, RFC 9457.
- [Spring Boot 3.3.13 — DefaultErrorWebExceptionHandler API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/reactive/error/DefaultErrorWebExceptionHandler.html): lỗi fallback, JSON và HTML.
- [Spring Boot — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): vị trí WebExceptionHandler của Boot, WebFilter order và error handling.
- [Spring Security 6.3 — ServerHttpSecurity.ExceptionHandlingSpec API](https://docs.spring.io/spring-security/site/docs/6.3.3/api/org/springframework/security/config/web/server/ServerHttpSecurity.ExceptionHandlingSpec.html): `authenticationEntryPoint` và `accessDeniedHandler`.
- [Spring Security — ExceptionTranslationWebFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/ExceptionTranslationWebFilter.html): chuyển authorization deny sang HTTP security response.
- [Spring Security — WebFlux HTTP Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): security chain, access rules và denial.
- [Spring Security — Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): lỗi CSRF trước controller.
- [Spring Framework — WebExceptionHandler API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/server/WebExceptionHandler.html): hợp đồng `Mono<Void> handle(exchange, ex)`.
