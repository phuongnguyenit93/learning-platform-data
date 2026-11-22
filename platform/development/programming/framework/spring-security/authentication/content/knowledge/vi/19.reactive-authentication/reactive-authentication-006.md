# AuthenticationWebFilter và ServerAuthenticationConverter — xác thực Reactive trong Spring Security

> **Module:** Spring Security - authentication. **Nhánh:** Xác thực reactive. Bài học giải thích cách `AuthenticationWebFilter` phối hợp với `ServerAuthenticationConverter`, `ReactiveAuthenticationManager`, Reactor Context và các rule phân quyền trong **Spring WebFlux**. Có ví dụ độc lập chạy bằng **Java 17, Spring Boot 3.3.5, Spring Security 6.x, Maven** và các bài kiểm thử `WebTestClient`. Cơ chế xác thực mẫu là API key qua header để thấy rõ ranh giới trách nhiệm; production nên ưu tiên cơ chế chuẩn OAuth2/JWT khi phù hợp.

## 1. Spring Security Reactive có gì khác Spring MVC?

Spring MVC chạy trên Servlet stack; Spring WebFlux cung cấp mô hình xử lý bất đồng bộ với Reactor `Mono`/`Flux`. Nếu chỉ quen `OncePerRequestFilter`, `HttpServletRequest` và `SecurityContextHolder` dạng ThreadLocal, bạn dễ cấu hình sai khi chuyển sang reactive.

| Thành phần Servlet | Thành phần WebFlux tương ứng |
| --- | --- |
| `jakarta.servlet.Filter` | `org.springframework.web.server.WebFilter` |
| `HttpServletRequest` và `HttpServletResponse` | `ServerWebExchange`, reactive request/response |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `HttpSecurity` | `ServerHttpSecurity` |
| `AuthenticationManager` trả `Authentication` trực tiếp | `ReactiveAuthenticationManager` trả `Mono<Authentication>` |
| `AuthenticationFilter` hoặc filter xác thực khác | `AuthenticationWebFilter` |
| `AuthenticationConverter` với servlet request | `ServerAuthenticationConverter` với `ServerWebExchange` |
| `SecurityContextHolder` thường dựa vào ThreadLocal | `ReactiveSecurityContextHolder` dựa vào Reactor Context |
| `HttpSession` | `WebSession` khi cần session-based security |
| `MockMvc` trong Servlet | `WebTestClient` cho Spring WebFlux |

**Quan trọng:** WebFlux không tự biến tất cả Java I/O thành non-blocking. Một converter gọi `.block()` hoặc một manager chạy JDBC blocking trên Netty event loop có thể làm giảm throughput nghiêm trọng. Reactive stack đòi hỏi cả API và các dependency chính được sử dụng đúng cách.

**Tình huống của bài:** API có `GET /api/data` cho client được cấp quyền đọc và `GET /api/admin` cho client quản trị. Client đưa header `X-API-Key`; server phải kiểm chứng key trước khi cấp principal và role. Header `X-Role: ROLE_ADMIN` do client tự gửi **không** được xem là authority.

## 2. Vai trò chính xác của AuthenticationWebFilter

`AuthenticationWebFilter` thuộc package `org.springframework.security.web.server.authentication` và implements `WebFilter`. Nó điều phối **một lần thử xác thực** với các bước:

```text
HTTP request -> SecurityWebFilterChain
    |
    v
AuthenticationWebFilter
    |
    +-- ServerWebExchangeMatcher:
    |      không khớp? -> bỏ qua xác thực, chain tiếp tục
    |      khớp?       -> gọi converter
    |
    +-- ServerAuthenticationConverter.convert(exchange)
    |      Mono.empty() -> không có credential, chain tiếp tục
    |      Mono.error(AuthenticationException) -> authentication failure
    |      Mono<Authentication> -> candidate cần xác minh
    |
    +-- ReactiveAuthenticationManager.authenticate(candidate)
    |      Mono<Authentication> đã xác minh -> thành công
    |      Mono.error(AuthenticationException) -> thất bại
    |      Mono.empty() -> manager không cung cấp kết quả
    |
    +-- Thành công:
    |      đưa Authentication tin cậy vào Reactor SecurityContext
    |      lưu context bằng ServerSecurityContextRepository nếu cấu hình
    |      gọi ServerAuthenticationSuccessHandler
    |
    +-- Thất bại:
           gọi ServerAuthenticationFailureHandler
           trả 401, challenge, redirect... theo cấu hình
    |
    v
AuthorizationWebFilter / authorizeExchange
    |
    +-- không có credential hợp lệ -> entry point xử lý
    +-- đã xác thực nhưng thiếu quyền -> 403
    +-- đủ quyền -> controller/handler
```

Filter không tự chứng minh key/password đúng, và converter không được tự cấp role. **Filter điều phối, converter trích xuất, manager xác minh, authorization quyết định quyền truy cập.** Đó là bốn ranh giới cần giữ độc lập.

### 2.1. API quan trọng

```java
// Chữ ký minh họa; không phải một tệp Java biên dịch độc lập.
new AuthenticationWebFilter(ReactiveAuthenticationManager manager);

new AuthenticationWebFilter(
    ReactiveAuthenticationManagerResolver<ServerWebExchange> resolver);

filter.setRequiresAuthenticationMatcher(matcher);
filter.setServerAuthenticationConverter(converter);
filter.setSecurityContextRepository(repository);
filter.setAuthenticationSuccessHandler(successHandler);
filter.setAuthenticationFailureHandler(failureHandler);
```

| API | Khi nào dùng |
| --- | --- |
| `setRequiresAuthenticationMatcher` | Giới hạn loại path/request mà filter sẽ thử xác thực |
| `setServerAuthenticationConverter` | Cách đọc request và dựng `Authentication` candidate |
| Constructor với `ReactiveAuthenticationManager` | Dùng một manager cố định cho cơ chế xác thực |
| Constructor với `ReactiveAuthenticationManagerResolver<ServerWebExchange>` | Chọn manager theo context với trust boundary rõ ràng (tenant/issuer đã allowlist) |
| `setSecurityContextRepository` | Lưu security context sau thành công; mặc định ở filter là `NoOpServerSecurityContextRepository` |
| `setAuthenticationSuccessHandler` | Phản hồi hoặc tiếp tục chain sau khi xác thực thành công |
| `setAuthenticationFailureHandler` | Chuyển exception xác thực thành HTTP response |

API cũ `setAuthenticationConverter(Function<ServerWebExchange, Mono<Authentication>>)` đã deprecated; với Spring Security 6 nên gọi **`setServerAuthenticationConverter`**.

Mặc định `ServerHttpBasicAuthenticationConverter` được dùng nếu không đặt converter riêng. Nếu ứng dụng đang dùng HTTP Basic, form login hoặc OAuth2 resource server tiêu chuẩn, **ưu tiên DSL có sẵn** thay vì tự thêm một filter trùng chức năng.

### 2.2. Matcher không thay cho authorization

Nếu filter chỉ match `/api/**` thì ngoài path đó filter không kiểm tra API key. Điều đó không tự khiến mọi URL bên ngoài `/api/**` trở thành private. Cần cấu hình `authorizeExchange` độc lập với rule:
- Public route được `permitAll()`.
- Route cần role dùng `hasRole(...)`/`hasAuthority(...)`.
- Các route khác bị `denyAll()` nếu không có nhu cầu public.

Lỗi nghiêm trọng là chỉ bật filter xác thực nhưng để `anyExchange().permitAll()` rồi tưởng endpoint đã được bảo vệ.

## 3. ServerAuthenticationConverter: chuyển request thành bằng chứng, không xác minh

`ServerAuthenticationConverter` là functional interface:

```java
// Hợp đồng API minh họa.
Mono<Authentication> convert(ServerWebExchange exchange);
```

Converter có thể đọc header, form body hoặc các thành phần của `ServerWebExchange`. Nó nên làm công việc nhỏ, không blocking và dễ kiểm tra:

1. Chọn đúng vị trí credential. Ví dụ chỉ đọc header `X-API-Key`.
2. Kiểm tra **cú pháp**: header có tồn tại không; rỗng/độ dài/trùng lặp có được chấp nhận không.
3. Nếu thiếu credential, trả `Mono.empty()`.
4. Nếu có credential nhưng sai cú pháp, trả `Mono.error(new BadCredentialsException(...))`.
5. Nếu hợp lệ về cú pháp, tạo một `Authentication` **chưa xác thực** chứa credential để manager kiểm chứng.

```java
// Trích đoạn minh họa, cần imports.
ServerAuthenticationConverter converter = exchange -> {
    String key = exchange.getRequest().getHeaders().getFirst("X-API-Key");
    if (key == null) {
        return Mono.empty();
    }
    if (key.isBlank()) {
        return Mono.error(new BadCredentialsException("Invalid API key"));
    }
    return Mono.just(
        UsernamePasswordAuthenticationToken.unauthenticated("api-key", key)
    );
};
```

Đây là cách mượn `UsernamePasswordAuthenticationToken` để minh họa candidate. Ở production có thể tạo `ApiKeyAuthenticationToken` chuyên biệt cho loại credential. Tên token không đổi nguyên lý: **principal và authorities tin cậy chỉ đến sau khi provider/manager xác minh**.

### 3.1. Ý nghĩa chính xác của các signal

| Signal | Ý nghĩa | Đường xử lý |
| --- | --- | --- |
| `Mono.empty()` | Converter không tìm thấy credential | Filter bỏ qua authentication, authorization quyết định có cần 401 |
| `Mono.just(candidate)` | Có bằng chứng theo cú pháp hợp lệ | Giao candidate cho manager |
| `Mono.error(BadCredentialsException)` | Đã gặp credential không chấp nhận được | Failure handler xử lý, trong demo trả 401 |
| `Mono.just(null)` | **Sai contract Reactor** | Reactor không chấp nhận phát null |
| Candidate gắn `ROLE_ADMIN` từ `X-Role` | **Sai trust boundary** | Có nguy cơ leo thang quyền |

Không biến `Mono.empty()` thành `anonymous authenticated`; thiếu credential chỉ là **không có một lần thử xác thực**. Một resource `permitAll` có thể trả 200, trong khi resource yêu cầu `authenticated()` sẽ từ chối.

### 3.2. Converter đọc request body cần đặc biệt cẩn trọng

Reactive request body thường là luồng có giới hạn tiêu thụ. Đọc body trong một filter rồi tiếp tục để controller đọc lại mà không cache/điều phối đúng có thể gây lỗi hoặc mất dữ liệu. Khi parse JSON/form login:
- Kiểm tra `Content-Type`, body size, charset và schema.
- Dùng WebFlux reactive API; không gọi `.block()` trên event loop.
- Tránh log raw password/token.
- Dùng converter sẵn có của Spring Security (ví dụ `ServerFormLoginAuthenticationConverter`) nếu phù hợp.
- Giữ CSRF protection khi credential được browser tự gửi.

Header-only converter của bài không cần đụng đến body.

## 4. ReactiveAuthenticationManager mới là nơi xác minh credential

`ReactiveAuthenticationManager` có phương thức:

```java
Mono<Authentication> authenticate(Authentication authentication);
```

Đây là thành phần được phép đối chiếu bằng chứng với nguồn tin cậy phía server (secret manager, reactive user store, issuer/decoder được cấu hình, IdP...). Trong demo:

```text
Input từ converter:
  UsernamePasswordAuthenticationToken.unauthenticated(
      "api-key", "demo-reader-key-123")

ReactiveAuthenticationManager:
  tìm key đã provision phía server
  kiểm tra key
  nếu đúng: tạo principal/role theo registry server
  nếu sai: Mono.error(new BadCredentialsException(...))

Output thành công:
  UsernamePasswordAuthenticationToken.authenticated(
      "reader-service", null, [ROLE_READER])
```

Manager phải **không tin** các trường `authenticated`, `role`, `scope` hay `tenant` do client tự cung cấp. Không viết code như sau:

```json
{
  "apiKey": "wrong",
  "authenticated": true,
  "authorities": ["ROLE_ADMIN"]
}
```

rồi dùng JSON đó để tạo một `Authentication` đã authenticated. Điều đó biến dữ liệu không tin cậy thành quyền server.

### 4.1. Mono.empty của manager khác bad credentials

`Mono.empty()` từ manager phù hợp với tình huống **manager không hỗ trợ loại token đó** và có cơ chế delegation rõ. Nếu token là loại được hỗ trợ nhưng key sai, trả một `AuthenticationException` (ví dụ `BadCredentialsException`) thay vì bỏ qua như không có request. Cách này giúp failure handler trả response đúng và dễ theo dõi.

### 4.2. Reactive thật sự không được block

Trong production, nếu cần query database qua mạng để kiểm tra key, ưu tiên reactive repository/driver như R2DBC hoặc reactive Redis; dùng `flatMap` và timeout hợp lý. Không gọi JDBC blocking trực tiếp trong converter/manager trên Netty event loop. Nếu buộc bridge library blocking, cần scheduler phù hợp, giới hạn concurrency, timeout và quan sát tải; không coi `Mono.just(blockingCall())` là non-blocking.

## 5. Authentication thành công sống trong Reactor Context thế nào?

Ở Servlet stack, code thường đọc `SecurityContextHolder.getContext()` từ thread-local. Trong WebFlux, execution có thể đổi thread qua scheduler hoặc callback. `ReactiveSecurityContextHolder` dùng Reactor `Context` để liên kết `SecurityContext` với reactive subscription.

Sau khi filter xác thực thành công, Spring Security thiết lập context cho những thành phần downstream. Controller có thể nhận `Mono<Principal>`:

```java
// Đoạn dùng trong reactive service khi cần lấy tên user tin cậy.
Mono<String> currentName =
    ReactiveSecurityContextHolder.getContext()
        .map(security -> security.getAuthentication().getName());
```

Không lấy tên user từ `X-User` hoặc JSON client rồi gọi đó là authenticated principal. Cũng không dùng một `ThreadLocal` tự đặt tên `currentUser` trong reactive pipeline nếu chưa thiết kế truyền context đúng.

### 5.1. Stateless và session-based

- **`NoOpServerSecurityContextRepository`**: không lưu security context vào `WebSession`. Request kế tiếp thiếu API key lại phải xác thực; phù hợp header API key/Bearer stateless trong demo.
- **`WebSessionServerSecurityContextRepository`**: có thể lưu context vào `WebSession` với cơ chế login tương tác; phải có chính sách session, CSRF, session fixation, logout và cookie.
- `ServerHttpSecurity.securityContextRepository(...)` điều khiển cách context được lấy vào reactor chain; `AuthenticationWebFilter.setSecurityContextRepository(...)` điều khiển nơi filter **lưu** context sau auth thành công. Hai chỗ nên nhất quán.

**Tránh nhầm package:** `ServerSecurityContextRepository` của WebFlux khác `SecurityContextRepository` của Servlet. Việc inject repository Servlet vào reactive filter là sai kiểu.

## 6. Dự án Spring Boot WebFlux hoàn chỉnh

Chúng ta sẽ viết API key riêng để dễ quan sát converter và manager. Hệ thống có:
- `GET /health`: public, trả `ok`.
- `GET /api/data`: cần `ROLE_READER` hoặc `ROLE_ADMIN`.
- `GET /api/admin`: cần `ROLE_ADMIN`.

Demo có hai key trong cấu hình **local-only**, không phải secret production. Không thêm `spring-boot-starter-web` vì mục tiêu là WebFlux (khi cả MVC và WebFlux cùng nằm trên classpath, Spring Boot thường ưu tiên MVC trừ khi có chỉ định rõ).

### 6.1. Cấu trúc tệp

```text
reactive-filter-demo/
├── pom.xml
├── src/main/resources/application.properties
├── src/main/java/com/example/reactiveauth/ReactiveAuthApplication.java
└── src/test/java/com/example/reactiveauth/ReactiveAuthApplicationTests.java
```

### 6.2. Maven: `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>reactive-filter-demo</artifactId>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
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

### 6.3. Cấu hình local `application.properties`

```properties
# Chỉ để chạy bài thực hành trên máy cá nhân. Không dùng trên production.
demo.auth.reader-key=demo-reader-key-123
demo.auth.admin-key=demo-admin-key-456
```

Các giá trị này là **key minh họa dễ đoán**. Trong hệ thống thật, key phải được sinh ngẫu nhiên đủ entropy, lưu/kiểm tra theo key ID và secret manager hoặc hash/HMAC phù hợp, hỗ trợ rotation và revocation. Không commit hoặc in key thực vào logs.

### 6.4. Java: `ReactiveAuthApplication.java`

```java
package com.example.reactiveauth;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.Principal;
import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.AuthenticationWebFilter;
import org.springframework.security.web.server.authentication.HttpStatusServerEntryPoint;
import org.springframework.security.web.server.authentication.ServerAuthenticationConverter;
import org.springframework.security.web.server.authentication.ServerAuthenticationEntryPointFailureHandler;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveAuthApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveAuthApplication.class, args);
    }

    @Bean
    ServerAuthenticationConverter apiKeyConverter() {
        return exchange -> {
            List<String> headers =
                    exchange.getRequest().getHeaders().get("X-API-Key");

            // Không có header -> không thử xác thực.
            if (headers == null) {
                return Mono.empty();
            }

            // Header có mặt nhưng sai cú pháp -> lỗi xác thực.
            if (headers.size() != 1 || headers.get(0).isBlank()
                    || headers.get(0).length() > 128) {
                return Mono.error(
                        new BadCredentialsException("Invalid API key"));
            }

            // Authentication candidate chưa được xác thực.
            return Mono.just(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "api-key", headers.get(0))
            );
        };
    }

    @Bean
    ReactiveAuthenticationManager apiKeyAuthenticationManager(
            @Value("${demo.auth.reader-key}") String readerKey,
            @Value("${demo.auth.admin-key}") String adminKey) {

        return authentication -> {
            if (!(authentication instanceof UsernamePasswordAuthenticationToken)) {
                return Mono.empty();
            }

            Object credentials = authentication.getCredentials();
            if (!(credentials instanceof String supplied)) {
                return Mono.error(
                        new BadCredentialsException("Invalid API key"));
            }

            // Quyền được quyết định từ key phía server, không từ X-Role.
            if (sameSecret(supplied, readerKey)) {
                return Mono.just(
                    UsernamePasswordAuthenticationToken.authenticated(
                        "reader-service",
                        null,
                        List.of(new SimpleGrantedAuthority("ROLE_READER"))
                    )
                );
            }

            if (sameSecret(supplied, adminKey)) {
                return Mono.just(
                    UsernamePasswordAuthenticationToken.authenticated(
                        "admin-service",
                        null,
                        List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
                    )
                );
            }

            return Mono.error(
                    new BadCredentialsException("Invalid API key"));
        };
    }

    // So sánh byte có cân nhắc timing; production cần quản lý hash/key chặt hơn.
    private static boolean sameSecret(String supplied, String expected) {
        return MessageDigest.isEqual(
                supplied.getBytes(StandardCharsets.UTF_8),
                expected.getBytes(StandardCharsets.UTF_8)
        );
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager apiKeyAuthenticationManager,
            ServerAuthenticationConverter apiKeyConverter) {

        AuthenticationWebFilter apiKeyFilter =
                new AuthenticationWebFilter(apiKeyAuthenticationManager);

        apiKeyFilter.setRequiresAuthenticationMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**")
        );
        apiKeyFilter.setServerAuthenticationConverter(apiKeyConverter);
        apiKeyFilter.setSecurityContextRepository(
                NoOpServerSecurityContextRepository.getInstance()
        );
        apiKeyFilter.setAuthenticationFailureHandler(
            new ServerAuthenticationEntryPointFailureHandler(
                new HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED)
            )
        );

        return http
            // Không tải security context từ WebSession.
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance()
            )
            // Chỉ trong demo API key stateless; không dùng cookie browser.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .logout(ServerHttpSecurity.LogoutSpec::disable)
            .exceptionHandling(ex -> ex.authenticationEntryPoint(
                new HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED)
            ))
            .authorizeExchange(ex -> ex
                .pathMatchers("/health").permitAll()
                .pathMatchers("/api/admin").hasRole("ADMIN")
                .pathMatchers("/api/data").hasAnyRole("READER", "ADMIN")
                .anyExchange().denyAll()
            )
            .addFilterAt(apiKeyFilter, SecurityWebFiltersOrder.AUTHENTICATION)
            .build();
    }

    public record Identity(String username, List<String> authorities) {}

    @RestController
    static class ApiController {
        @GetMapping("/health")
        Mono<String> health() {
            return Mono.just("ok");
        }

        @GetMapping("/api/data")
        Mono<Identity> data(Mono<Principal> principal) {
            return principal.map(p -> {
                Authentication auth = (Authentication) p;
                List<String> roles = auth.getAuthorities().stream()
                        .map(GrantedAuthority::getAuthority)
                        .sorted()
                        .toList();
                return new Identity(auth.getName(), roles);
            });
        }

        @GetMapping("/api/admin")
        Mono<String> admin() {
            return Mono.just("admin-only");
        }
    }
}
```

### 6.5. Giải thích từng quyết định trong ví dụ

1. **Converter chỉ trích credential.** Một header `X-API-Key` được kiểm tra cú pháp; trùng header, rỗng hoặc dài quá giới hạn tạo lỗi. Candidate được tạo bằng `UsernamePasswordAuthenticationToken.unauthenticated`, không có authorities.
2. **Manager quyết định danh tính.** Nó so key với giá trị server được provision và trả `UsernamePasswordAuthenticationToken.authenticated` kèm principal/authority chính thức. User không được tự chọn quyền qua header.
3. **Không chặn event loop.** So sánh key demo là phép tính ngắn trong bộ nhớ. Khi thay bằng DB/IdP cần dùng reactive driver/client; không gọi `block()` để "giữ cú pháp cũ".
4. **Matcher của filter:** `/api/**` được kiểm tra API key. `/health` không buộc converter xử lý header không liên quan.
5. **Response 401 rõ ràng:** filter có failure handler trả status 401 cho credential sai; entry point cùng status được dùng khi authorization yêu cầu authenticated principal mà request thiếu key.
6. **Tách authn và authz:** role READER không đủ cho route admin → 403; role ADMIN đủ cho route admin → 200.
7. **Stateless nhất quán:** `NoOpServerSecurityContextRepository` cấu hình ở cả filter và `ServerHttpSecurity`; request mới không gửi key không thể dùng lại identity.
8. **Principal reactive:** controller nhận `Mono<Principal>` từ exchange đã qua security filter; ở route này principal là một `Authentication` do manager tạo. Không đọc username từ request query.
9. **CSRF disabled có phạm vi hẹp:** đây là demo GET-only với key gắn thủ công vào header, không dùng cookie session/browser credentials tự gửi. Khi thêm browser login hoặc các POST dùng cookie cần xem lại CSRF.
10. **Không dùng Servlet SecurityFilterChain.** Code chỉ khai báo `SecurityWebFilterChain`, `ServerHttpSecurity`, `AuthenticationWebFilter`; không thêm một `OncePerRequestFilter`.

## 7. Chạy và tự kiểm chứng bằng curl

Từ thư mục dự án:

```bash
mvn spring-boot:run
```

Thử các request sau:

```bash
# Public endpoint: 200, body ok
curl -i http://localhost:8080/health

# Không có key: 401
curl -i http://localhost:8080/api/data

# Key sai: 401
curl -i -H 'X-API-Key: invalid' \
  http://localhost:8080/api/data

# Reader key: 200, ROLE_READER từ server
curl -i -H 'X-API-Key: demo-reader-key-123' \
  http://localhost:8080/api/data

# Không tăng quyền bằng header client: 403
curl -i -H 'X-API-Key: demo-reader-key-123' \
  -H 'X-Role: ROLE_ADMIN' \
  -H 'X-Authenticated: true' \
  http://localhost:8080/api/admin

# Admin key: 200
curl -i -H 'X-API-Key: demo-admin-key-456' \
  http://localhost:8080/api/admin

# Chứng minh stateless: sau 200, request mới không header vẫn 401
curl -i -H 'X-API-Key: demo-reader-key-123' \
  http://localhost:8080/api/data
curl -i http://localhost:8080/api/data
```

Response JSON minh họa ở `/api/data`:

```json
{"username":"reader-service","authorities":["ROLE_READER"]}
```

Body của `/api/admin` với admin key:

```text
admin-only
```

| Request | Trạng thái dự kiến | Lý do |
| --- | --- | --- |
| `/health` không key | 200 | Public |
| `/api/data` không key | 401 | Converter `Mono.empty()`, authorization thiếu auth |
| `/api/data` key không đúng | 401 | Manager phát `BadCredentialsException` |
| `/api/data` reader key | 200 | Manager cấp `ROLE_READER` |
| `/api/admin` reader key + `X-Role: ROLE_ADMIN` | 403 | Role client không được tin |
| `/api/admin` admin key | 200 | Manager cấp `ROLE_ADMIN` |
| Request mới không gửi key | 401 | Không có session để khôi phục identity |

Bảng mô tả status và body nghiệp vụ. HTTP headers bổ sung phụ thuộc server/framework; không nên hard-code toàn bộ response khi không cần. Với credential thật, **không đặt API key trong query string**, log hoặc tài liệu công khai.

## 8. Kiểm thử bằng WebTestClient, không bỏ qua filter

Tạo `src/test/java/com/example/reactiveauth/ReactiveAuthApplicationTests.java`:

```java
package com.example.reactiveauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveAuthApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void healthWorksWithoutKey() {
        client.get().uri("/health")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("ok");
    }

    @Test
    void missingAndWrongKeyAreRejected() {
        client.get().uri("/api/data")
                .exchange()
                .expectStatus().isUnauthorized();

        client.get().uri("/api/data")
                .header("X-API-Key", "invalid")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void readerKeyIsAuthenticatedWithServerSideAuthority() {
        client.get().uri("/api/data")
                .header("X-API-Key", "demo-reader-key-123")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.username").isEqualTo("reader-service")
                .jsonPath("$.authorities[0]").isEqualTo("ROLE_READER");
    }

    @Test
    void clientCannotForgedAdminRole() {
        client.get().uri("/api/admin")
                .header("X-API-Key", "demo-reader-key-123")
                .header("X-Role", "ROLE_ADMIN")
                .header("X-Authenticated", "true")
                .exchange()
                .expectStatus().isForbidden();

        client.get().uri("/api/admin")
                .header("X-API-Key", "demo-admin-key-456")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin-only");
    }

    @Test
    void secondRequestNeedsOwnKey() {
        client.get().uri("/api/data")
                .header("X-API-Key", "demo-reader-key-123")
                .exchange()
                .expectStatus().isOk();

        client.get().uri("/api/data")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void malformedAndRepeatedKeyHeadersAreRejected() {
        client.get().uri("/api/data")
                .header("X-API-Key", " ")
                .exchange()
                .expectStatus().isUnauthorized();

        client.get().uri("/api/data")
                .header("X-API-Key",
                        "demo-reader-key-123", "demo-admin-key-456")
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
```

Chạy:

```bash
mvn test
```

**Tại sao những test này có giá trị?** Chúng gửi request với header thật qua `SecurityWebFilterChain`, không inject sẵn authenticated principal. Vì vậy chúng có thể phát hiện lỗi ở matcher, converter, manager, context và authorization. Nếu chỉ dùng `mockUser()`, các test authority có thể pass dù converter/manager hỏng. `mockUser()` vẫn hữu ích khi muốn **cố ý** test mỗi authorization rule mà bỏ qua phần xác thực.

`@SpringBootTest` + `@AutoConfigureWebTestClient` kiểm thử ở tầng WebFlux application, nhưng chưa thay thế E2E test TLS, reverse proxy, secret store, rate limits và deployment đa node. Mã kiểm thử được cung cấp để người học chạy; **không khẳng định đã chạy Maven ở đây**.

## 9. Biến thể converter và authentication mechanism

### 9.1. HTTP Basic

Spring Security có `ServerHttpBasicAuthenticationConverter` để đọc `Authorization: Basic ...`. Thường dùng `http.httpBasic(...)` thay vì viết một converter Base64 riêng. Base64 không mã hóa password; HTTPS và password hashing phía server vẫn bắt buộc.

### 9.2. Form login

WebFlux có `ServerFormLoginAuthenticationConverter` xử lý dữ liệu form. Với browser login, authentication thành công có thể được lưu vào `WebSession`. Khi đó cần CSRF protection, session fixation, logout và cookie policy tương thích; không dùng NoOp session repository một cách máy móc.

### 9.3. JWT Bearer

Với API xác thực JWT, `http.oauth2ResourceServer(...jwt...)` cùng `ReactiveJwtDecoder` và các converter/manager được Spring Security cung cấp là con đường ưu tiên. Không tự decode Base64 phần payload rồi tin các trường `iss`, `scope` hay `role` trước khi kiểm tra chữ ký, `aud`, thời hạn, issuer và các constraints khác.

### 9.4. Multi-tenant manager resolver

`AuthenticationWebFilter` có constructor nhận `ReactiveAuthenticationManagerResolver<ServerWebExchange>` để chọn manager theo request. Một tenant/issuer hint có thể do client ảnh hưởng; server phải chuẩn hóa, tra registry/allowlist tin cậy, chọn manager/decoder đã provision, rồi **xác minh credential với manager đó**.

Không nhận JDBC URL, LDAP host hay JWK URL tùy ý từ client để tạo manager. Nếu tenant không tồn tại, fail closed; không fallback sang manager toàn cục với authority rộng.

### 9.5. Custom API key token

Thay `UsernamePasswordAuthenticationToken` bằng custom token sẽ rõ nghĩa hơn ở hệ thống lớn. Nhưng việc tạo token ở converter vẫn phải **unauthenticated**; factory method/constructor đánh dấu authenticated chỉ được dùng sau khi nguồn server xác minh. Tránh class token có setter công khai cho phép gán `ROLE_ADMIN` từ request JSON.

## 10. Lỗi thực tế và cách chẩn đoán

| Biểu hiện/lỗi | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| WebFlux app dùng `OncePerRequestFilter` | Nhầm Servlet với reactive | Dùng `AuthenticationWebFilter`, `ServerWebExchange` |
| Authn filter chạy nhưng route vẫn public | Chưa có `authorizeExchange` phù hợp | Test protected endpoint không key phải 401 |
| Converter luôn trả `Mono.empty()` | Đọc sai header/path hoặc matcher không khớp | Kiểm tra request header/matcher, không log secret |
| Key sai nhưng response 200 | Manager trả authenticated token sai logic | Kiểm tra server-side verification, không tin client |
| Key đúng nhưng 403 | Authority từ manager không thỏa rule | Kiểm tra `ROLE_READER` vs `ROLE_ADMIN` |
| Không đọc được principal trong reactive service | Dùng ThreadLocal thay Reactor Context | `ReactiveSecurityContextHolder`/reactive principal |
| Request có 2 API keys mà vẫn thành công | Converter chọn first header không kiểm tra duplicates | Reject sai cú pháp/trùng lặp |
| Giảm throughput khi gọi login | Blocking database/`block()` trên event loop | Reactive driver, timeout, bounded resources |
| Request sau tự authenticated dù không gửi key | Cấu hình session repository ngoài ý định | NoOp đồng bộ ở filter và chain |
| Sai key trả 500 | Không map authentication failure | `ServerAuthenticationFailureHandler` với entry point thích hợp |
| Missing key trả 403 thay vì 401 | Rule/entry point/anonymous handling khác | Cấu hình và test exception handling |
| Tắt CSRF cho mọi route | Browser cookie vẫn tự gửi | Đánh giá credential transport và bảo vệ state-changing actions |

**Phân biệt status:** 401 thường là không có/không hợp lệ credential; 403 là đã xác thực nhưng thiếu quyền. Response chính xác phụ thuộc các entry point/failure/access-denied handlers được cấu hình. Demo khai báo rõ 401 cho hai trường hợp authentication missing và invalid.

### 10.1. Không đồng nhất authentication với authorization

Đường `/api/data` và `/api/admin` đều dùng cùng filter API key. Việc manager xác minh key chỉ trả lời "đây là ai"; bước authorization mới trả lời "được phép làm gì". Header `X-Role` là dữ liệu client nên không thay đổi role đã được manager cấp.

### 10.2. Lỗi đọc body khi thêm JSON login

WebFlux request body có thể bị tiêu thụ. Converter custom nhận `ServerWebExchange` rồi đọc body và tiếp tục chain cần xử lý body caching/validation đúng cách; không coi nó như `HttpServletRequest.getInputStream()` có thể đọc lại vô hạn. Cần giới hạn payload, parse reactive và tránh gọi `block()`.

### 10.3. Không sử dụng request-scope ThreadLocal

Chuyển scheduler hoặc dùng async callback có thể thay đổi thread. Nếu audit/authorization phụ thuộc user hiện tại, lấy từ `ReactiveSecurityContextHolder` hoặc truyền principal được xác thực qua reactive pipeline đúng contract, không dùng biến tĩnh/ThreadLocal do ứng dụng tự tạo.

## 11. Chuẩn hóa trước production

1. **Secrets:** API key ngẫu nhiên entropy cao, key ID, secret manager, hashing/HMAC, scopes, expiry và rotation. Không dùng literal demo keys ngoài môi trường local.
2. **Vận chuyển:** HTTPS/TLS, không gửi credential qua URL/query; không log raw authorization headers hoặc body credentials.
3. **Phân quyền:** kiểm chứng authorities theo nguồn tin cậy; mặc định quyền tối thiểu; kiểm soát tenant/object ownership ở service/data layer.
4. **Reactive I/O:** reactive DB/client cho xác thực, timeout/circuit breaker/rate limit; không chuyển sự cố IdP thành user sai mật khẩu một cách vô điều kiện.
5. **Observability:** chỉ ghi key ID và outcome sau khi redact; không lưu raw key trong trace, exception hay metric labels.
6. **Consistency:** khi nhiều node dùng registry, config/rotation/revocation phải đồng bộ; fail closed khi không thể xác minh.
7. **CSRF:** chỉ vô hiệu hóa ở các route header-token stateless đã phân tích. Nếu browser tự gửi cookie, cần CSRF policy đúng.
8. **Tests:** thiếu key, key sai, định dạng hỏng, fake role, đúng key nhưng thiếu role, context stateless và key revoked.
9. **Tối ưu:** lựa chọn API chuẩn của Spring Security khi phù hợp; custom filter chỉ khi có lý do rõ.
10. **Ranh giới:** token hết hạn/thu hồi và credential lifecycle là cơ chế riêng, không tự xảy ra vì một request reactive kết thúc.

## 12. Câu hỏi tự kiểm tra

1. `AuthenticationWebFilter` khác `ServerAuthenticationConverter` ở bước nào?
2. Vì sao converter nên trả `UsernamePasswordAuthenticationToken.unauthenticated(...)`?
3. `Mono.empty()` từ converter khác `Mono.error(BadCredentialsException)` như thế nào?
4. Trong demo, ai cấp `ROLE_READER` và `ROLE_ADMIN`?
5. `setRequiresAuthenticationMatcher` có thay thế `authorizeExchange` được không?
6. Vì sao một HTTP request thiếu key vẫn có thể thành công ở `/health`?
7. Vì sao reader key đúng vẫn bị 403 ở `/api/admin`?
8. `ReactiveAuthenticationManager` khác `AuthenticationManager` Servlet ở contract nào?
9. Vì sao `SecurityContextHolder` ThreadLocal không phải lựa chọn mặc định cho WebFlux?
10. Tại sao phải đặt `NoOpServerSecurityContextRepository` cả ở filter và chain?
11. Khi nào nên dùng `ReactiveAuthenticationManagerResolver`, và vì sao cần registry tin cậy?
12. Khi nào `mockUser()` hữu ích, và khi nào nó che bug converter?
13. Vì sao không nên parse JWT payload rồi tự gán quyền?
14. Tại sao tắt CSRF không phải hệ quả bắt buộc của dùng WebFlux?
15. Điều gì xảy ra khi manager gọi JDBC blocking trên Netty event loop?

**Đáp án cốt lõi:** (1) filter điều phối, converter trích credential; (2) credential client chưa được tin; (3) thiếu bằng chứng so với cố thử bằng chứng sai; (4) server-side manager; (5) không, authn khác authz; (6) permitAll; (7) thiếu authority; (8) `Mono<Authentication>`; (9) Reactor execution có thể đổi thread; (10) thống nhất stateless; (11) chọn manager đã allowlist và kiểm chứng credential; (12) tốt để test authorization riêng, không chứng minh converter; (13) cần chữ ký/issuer/audience validation; (14) phụ thuộc cơ chế browser credential; (15) chặn event loop, giảm khả năng phục vụ.

## 13. Tài liệu chính thức

- Spring Security 6.5 — AuthenticationWebFilter API: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html
- Spring Security 6.5 — ServerAuthenticationConverter API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationConverter.html
- Spring Security 6.5 — ReactiveAuthenticationManager API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ReactiveAuthenticationManager.html
- Spring Security 6.5 — ReactiveAuthentication: https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/index.html
- Spring Security 6.5 — WebFlux Security: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security 6.5 — Reactive authorization: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html
- Spring Security 6.5 — WebTestClient Security Setup: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html
- Spring Security 6.5 — Reactive Testing Authentication: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html
- Spring Security 6.5 — CSRF WebFlux: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
