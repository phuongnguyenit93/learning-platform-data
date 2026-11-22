# ExceptionTranslationWebFilter: chuyển lỗi bảo mật thành phản hồi HTTP

> **Chủ đề:** Spring Security – reactive  
> **Ngữ cảnh:** Kiến trúc WebFilter trong Spring WebFlux  
> **Trọng tâm:** Cách một quyết định **từ chối truy cập** của Spring Security được biểu diễn bằng `AccessDeniedException`, sau đó được `ExceptionTranslationWebFilter` chuyển thành nhánh yêu cầu xác thực hoặc phản hồi từ chối quyền. Bài này tập trung vào ứng dụng **reactive**, không dùng cấu hình Servlet.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích trách nhiệm của `ExceptionTranslationWebFilter` trong `SecurityWebFilterChain`, phân biệt nó với filter xác thực và filter ra quyết định phân quyền.
2. Diễn giải chính xác vì sao cùng một lần kiểm tra quyền thất bại có thể dẫn tới **401 Unauthorized** hoặc **403 Forbidden**.
3. Phân biệt `ServerAuthenticationEntryPoint` với `ServerAccessDeniedHandler`, kể cả nguồn phát sinh của HTTP 401 khi mật khẩu Basic sai.
4. Sử dụng `ServerHttpSecurity.exceptionHandling(...)` để tùy biến phản hồi lỗi theo cách reactive, không chặn thread.
5. Viết test `WebTestClient` kiểm tra thiếu credentials, credentials sai, đã đăng nhập nhưng thiếu quyền, đủ quyền và lỗi server không thuộc security.
6. Chẩn đoán các tình huống dễ nhầm: anonymous principal, lỗi CSRF, nhiều security chain, response đã commit và generic exception handler.

## 2. Tại sao cần một filter "dịch" lỗi?

Tầng **authorization** trả lời câu hỏi: “Yêu cầu này có được phép thực hiện không?” Tầng **HTTP response** lại cần biểu đạt kết quả theo giao thức: status, header, body hoặc chuyển hướng trang đăng nhập. Hai tầng không nên trộn lẫn.

Ví dụ endpoint `GET /api/reports` đòi role `READER`. Khi kiểm tra quyền thất bại, một thành phần bên dưới có thể phát ra `AccessDeniedException`. Nếu người gọi **chưa xác thực**, API thường cần phản hồi **401** để client biết phải cung cấp credentials. Nếu người gọi **đã xác thực** nhưng thiếu `ROLE_READER`, API thường trả **403** để thông báo không đủ quyền.

`ExceptionTranslationWebFilter` là cầu nối giữa **tín hiệu lỗi phân quyền** và **cách biểu diễn lỗi bằng HTTP**. Nó không có nhiệm vụ so khớp mật khẩu, giải mã JWT hay quyết định user có `ROLE_READER` hay không. Các thành phần khác thực hiện những việc đó.

| Thành phần | Trách nhiệm chính | Điều không nên gán cho nó |
| --- | --- | --- |
| `AuthenticationWebFilter` (chẳng hạn HTTP Basic) | Trích xuất credentials, yêu cầu xác thực và xử lý thành công/thất bại xác thực | Không tự quyết định mọi rule phân quyền tài nguyên |
| `SecurityContext` và Reactor `Context` | Mang danh tính/`Authentication` qua reactive pipeline | Không tự động cho phép mọi request |
| `AuthorizationWebFilter` | Kiểm tra chính sách truy cập và phát tín hiệu từ chối khi quyền không đủ | Không tự xây dựng mọi response lỗi HTTP |
| **`ExceptionTranslationWebFilter`** | Nhận một `AccessDeniedException` từ phần downstream, chọn entry point hoặc access-denied handler | Không thực hiện xác thực hay cấp quyền |
| `ServerAuthenticationEntryPoint` | Bắt đầu quá trình yêu cầu xác thực, ví dụ phản hồi 401 + `WWW-Authenticate` | Không có nhiệm vụ xác minh password |
| `ServerAccessDeniedHandler` | Xử lý trường hợp bị từ chối quyền, điển hình trả 403 | Không phải password authentication failure handler |
| `WebExceptionHandler` / `@ControllerAdvice` | Xử lý các lỗi ứng dụng theo phạm vi của cơ chế đó | Không thay thế chính sách bảo mật và security exception handling |

**Tên lớp cần dùng đúng:** Trong WebFlux là `org.springframework.security.web.server.authorization.ExceptionTranslationWebFilter`. Phía Servlet là `org.springframework.security.web.access.ExceptionTranslationFilter`. Hai lớp gần nhau về mục tiêu nhưng **khác API, khác cơ chế và khác phạm vi bắt lỗi**.

## 3. Vị trí trong reactive filter chain

Một `SecurityWebFilterChain` là tập hợp các `WebFilter` Spring Security áp dụng cho request. Mô hình giản lược:

```text
                  HTTP REQUEST
                       |
                       v
             WebFlux WebFilter chain
                       |
        [Authentication WebFilter, nếu có]
                 credentials / token
                       |
         SecurityContext trong Reactor Context
                       |
                       v
          ExceptionTranslationWebFilter
                       |
                 chain.filter(exchange)
                       |
                       v
              AuthorizationWebFilter
                       |
                +------+-------+
                |              |
             Cho phép      AccessDeniedException
                |              |
         Handler/Service        +--> ExceptionTranslationWebFilter
                |                         |
             Response            +--------+--------+
                                 |                 |
                         Chưa xác thực         Đã xác thực
                                 |                 |
                      AuthenticationEntryPoint  AccessDeniedHandler
                                 |                 |
                            thường 401         thường 403
```

**Lưu ý:** Đây là sơ đồ các mắt xích liên quan, không phải danh sách đầy đủ của filter chain. Spring Security còn có các filter về context, header, CSRF, CORS, logout, request cache... Thứ tự chuẩn trong `SecurityWebFiltersOrder` đặt `EXCEPTION_TRANSLATION` trước `AUTHORIZATION`, để phần xử lý exception bao quanh các bước cấp quyền ở phía sau.

Khi xây dựng Spring Security WebFlux thông thường bằng `ServerHttpSecurity`, framework tự cấu hình `ExceptionTranslationWebFilter`. **Không cần** tự `new ExceptionTranslationWebFilter()` hoặc chèn thêm một filter tương tự chỉ để nhận 401/403. Việc tự thêm filter có thể gây hai tầng xử lý lỗi, response không nhất quán và khó truy vết.

### 3.1. Cơ chế reactive: `onErrorResume`

Ý tưởng cốt lõi của implementation có thể mô tả bằng **mã giả**, không phải đoạn API thay thế source Spring Security:

```java
// Pseudocode minh họa, không phải chương trình biên dịch độc lập:
return chain.filter(exchange)
    .onErrorResume(AccessDeniedException.class, denied -> {
        // Đọc principal, xem đây là anonymous/chưa xác thực
        // hay chủ thể được tin là đã xác thực.
        // Chưa xác thực: authenticationEntryPoint.commence(...)
        // Đã xác thực: accessDeniedHandler.handle(...)
        return handleAccordingToAuthentication(exchange, denied);
    });
```

Ý nghĩa:

- `chain.filter(exchange)` trả về `Mono<Void>` đại diện cho phần downstream.
- Nếu downstream hoàn thành bình thường, filter không cần tạo một response lỗi.
- Khi downstream phát `AccessDeniedException` vào chính reactive error signal, `onErrorResume` có thể xử lý và hoàn tất một response HTTP.
- Nếu downstream phát `IllegalStateException` hoặc lỗi ứng dụng khác, nhánh `onErrorResume(AccessDeniedException.class, ...)` **không** tự biến nó thành 401/403.
- Bộ lọc đánh giá trạng thái authentication bằng cơ chế trust resolver của Spring Security. Không nên thay toàn bộ logic bằng điều kiện giản lược `authentication.isAuthenticated()`, vì anonymous authentication có thể mang cờ `isAuthenticated() == true` nhưng vẫn là người dùng ẩn danh.

Không kết luận rằng "mọi lỗi bảo mật đều do `ExceptionTranslationWebFilter` trực tiếp bắt": điều đó đặc biệt dễ sai khi so sánh với **Servlet `ExceptionTranslationFilter`**. Implementation reactive nhắm tới `AccessDeniedException` từ phần downstream; một lần HTTP Basic authentication thất bại còn có đường xử lý riêng bên trong `AuthenticationWebFilter`.

### 3.2. Những lớp liên quan

| Tên lớp/giao diện | Package tiêu biểu | Dùng để |
| --- | --- | --- |
| `ExceptionTranslationWebFilter` | `org.springframework.security.web.server.authorization` | Dịch lỗi từ chối quyền downstream |
| `AccessDeniedException` | `org.springframework.security.access` | Biểu đạt không đủ quyền |
| `AuthenticationException` | `org.springframework.security.core` | Biểu đạt lỗi trong quá trình xác thực |
| `ServerAuthenticationEntryPoint` | `org.springframework.security.web.server` | Sinh phản hồi/yêu cầu bắt đầu authentication |
| `ServerAccessDeniedHandler` | `org.springframework.security.web.server.authorization` | Phản hồi khi truy cập bị từ chối |
| `AuthenticationWebFilter` | `org.springframework.security.web.server.authentication` | Xác thực reactive request |
| `AuthorizationWebFilter` | `org.springframework.security.web.server.authorization` | Kiểm tra quyền ở HTTP layer |
| `ServerHttpSecurity` | `org.springframework.security.config.web.server` | Cấu hình `SecurityWebFilterChain` |
| `ReactiveSecurityContextHolder` | `org.springframework.security.core.context` | Truy cập context bảo mật trong Reactor |

## 4. Cách phân biệt 401, 403 và lỗi ứng dụng

Đừng hiểu "401 = luôn do `ExceptionTranslationWebFilter`" hoặc "403 = chỉ khi thiếu role". HTTP status còn phụ thuộc authentication mechanism và nơi phát sinh lỗi.

| Tình huống | Luồng xử lý chủ yếu | Kết quả thường gặp trong REST API |
| --- | --- | --- |
| Không có credentials, truy cập endpoint yêu cầu quyền | Authorization từ chối → `AccessDeniedException` → entry point của exception translation | **401** và có thể có `WWW-Authenticate` |
| Credentials hợp lệ, user không có quyền | Authorization từ chối → `AccessDeniedException` → access-denied handler | **403** |
| HTTP Basic gửi sai mật khẩu | `AuthenticationWebFilter` phát hiện lỗi authentication và gọi **authentication failure handler** | **401**, có thể không dùng JSON body của exception-translation entry point |
| User có quyền | Request đi qua authorization, handler xử lý bình thường | **200**, **201**, ... theo nghiệp vụ |
| Handler ném `IllegalStateException` | Không thuộc lỗi truy cập từ `AccessDeniedException` | Thường **500** do ứng dụng xử lý |
| Controller gọi tài nguyên không tồn tại | Lỗi nghiệp vụ/`ResponseStatusException` thích hợp | Có thể **404**, độc lập với chuyện đã xác thực |
| POST bị CSRF protection từ chối | Nhánh CSRF riêng; có thể dùng `ServerAccessDeniedHandler` được gắn với cấu hình CSRF | Thường **403**, không tự suy rằng role sai |
| JWT hết hạn/không hợp lệ | Luồng bearer-token authentication/resource-server thất bại | Thường **401** kèm quy tắc `WWW-Authenticate: Bearer ...` |

### 4.1. Vì sao một `AccessDeniedException` có thể thành 401?

Quy tắc bảo vệ endpoint không chỉ phát biểu "thiếu quyền"; trong nhiều trường hợp hệ thống chưa biết người gọi là ai. Khi gặp tín hiệu từ chối quyền nhưng principal chưa được coi là đã xác thực, filter chuyển sang `ServerAuthenticationEntryPoint` để yêu cầu xác thực. HTTP Basic entry point thường đáp 401, đôi khi kèm header `WWW-Authenticate: Basic ...`. Với form login, entry point có thể redirect; OAuth2 resource server có thể áp dụng Bearer semantics.

Vì vậy **401/403 là lựa chọn của handler phù hợp với trạng thái bảo mật và cơ chế xác thực**. Đây không phải hai exception Java bắt buộc tương ứng một-một với hai status.

### 4.2. Đừng nhầm một anonymous token với người dùng đã đăng nhập

Spring Security có thể tạo `AnonymousAuthenticationToken` cho request chưa đăng nhập. Token này có thể trả `isAuthenticated() == true` theo hợp đồng object, nhưng `AuthenticationTrustResolver` nhận diện anonymous là chưa được xác thực theo nghĩa dùng để bảo vệ tài nguyên. Với request bị từ chối, entry point thường vẫn được dùng. Hãy dựa vào chính sách `authenticated()` và hệ thống trust resolver, không tự viết `if (authentication.isAuthenticated()) return 403`.

## 5. Cấu hình mặc định và tùy biến handler

Spring Security WebFlux đã có thành phần để nhận lỗi. Trong cấu hình thường gặp:

- `ServerAuthenticationEntryPoint` mặc định cho Basic có thể dùng `HttpBasicServerAuthenticationEntryPoint` để tạo authentication challenge.
- `ServerAccessDeniedHandler` tiêu biểu là `HttpStatusServerAccessDeniedHandler(HttpStatus.FORBIDDEN)`, trả 403.
- `ServerHttpSecurity.exceptionHandling(customizer)` cho phép gắn entry point và access-denied handler theo nhu cầu REST API.

**Hợp đồng phương thức:**

```java
// Các chữ ký giao diện liên quan (minh họa, không phải file Java độc lập):
Mono<Void> commence(ServerWebExchange exchange,
                     AuthenticationException exception);

Mono<Void> handle(ServerWebExchange exchange,
                  AccessDeniedException denied);
```

`Mono<Void>` nghĩa là handler phải trả về tín hiệu cho biết việc viết response đã được xử lý bất đồng bộ. Không dùng `block()` hoặc gọi `subscribe()` thủ công trong handler. Với một body HTTP, có thể dùng `ServerHttpResponse.writeWith(Publisher<DataBuffer>)`.

Các quy tắc thiết kế phản hồi nên giữ rõ:

1. 401 cho client biết có vấn đề xác thực; nếu dùng HTTP Basic, nên giữ `WWW-Authenticate` tương thích.
2. 403 cho biết quyền không đủ, **không** tiết lộ chi tiết tài nguyên nhạy cảm, chính sách nội bộ hoặc stack trace.
3. Nội dung response có thể theo chuẩn thống nhất như `{"code":"ACCESS_DENIED"}`, nhưng mã lỗi phải có ý nghĩa ổn định cho client.
4. Không đưa nguyên văn exception message, mật khẩu, raw token hay thông tin người dùng khác vào body.
5. Nếu dùng form login hoặc OAuth2/JWT, entry point và headers cần phản ánh cơ chế đó; tránh ép HTTP Basic challenge lên mọi client.

## 6. Ví dụ Java 17+ chạy được: một WebFlux API trả JSON khi bị chặn

Phần này là một project Maven nhỏ dùng **Spring Boot 3.5.16**, tương ứng Spring Security 6.x qua dependency management. Phiên bản được cố định để mẫu dễ tái lập; hãy chọn bản đang được dự án thực tế hỗ trợ khi dùng production. Demo chỉ chứa GET và user trong bộ nhớ để tập trung vào exception translation.

Cấu trúc:

```text
reactive-exception-translation-demo/
├── pom.xml
└── src/
    ├── main/java/demo/webfilter/
    │   ├── Application.java
    │   ├── SecurityConfiguration.java
    │   └── DemoController.java
    └── test/java/demo/webfilter/
        └── ExceptionTranslationTests.java
```

### 6.1. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <groupId>demo</groupId>
    <artifactId>reactive-exception-translation-demo</artifactId>
    <version>1.0.0</version>
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

Với Spring Boot parent, không tự chèn version của `spring-security-test`, `spring-boot-starter-security` hay Reactor. `spring-security-test` chỉ dùng trong test; runtime WebFlux/Security không yêu cầu artifact này.

### 6.2. `src/main/java/demo/webfilter/Application.java`

```java
package demo.webfilter;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

### 6.3. `src/main/java/demo/webfilter/SecurityConfiguration.java`

```java
package demo.webfilter;

import java.nio.charset.StandardCharsets;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public").permitAll()
                .pathMatchers("/api/reports").hasRole("READER")
                .anyExchange().authenticated()
            )
            .httpBasic(withDefaults())
            .formLogin(form -> form.disable())
            .exceptionHandling(exceptions -> exceptions
                .authenticationEntryPoint((exchange, error) ->
                    respondJson(exchange, HttpStatus.UNAUTHORIZED, """
                        {"code":"AUTHENTICATION_REQUIRED"}
                        """))
                .accessDeniedHandler((exchange, error) ->
                    respondJson(exchange, HttpStatus.FORBIDDEN, """
                        {"code":"ACCESS_DENIED"}
                        """))
            )
            .build();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService() {
        UserDetails reader = User.withUsername("reader")
            .password("{noop}reader123")
            .roles("READER")
            .build();
        UserDetails guest = User.withUsername("guest")
            .password("{noop}guest123")
            .roles("GUEST")
            .build();
        return new MapReactiveUserDetailsService(reader, guest);
    }

    private static Mono<Void> respondJson(
            ServerWebExchange exchange,
            HttpStatus status,
            String json) {

        ServerHttpResponse response = exchange.getResponse();
        response.setStatusCode(status);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);

        if (status == HttpStatus.UNAUTHORIZED) {
            response.getHeaders().set(
                HttpHeaders.WWW_AUTHENTICATE, "Basic realm=\"demo\"");
        }

        byte[] body = json.getBytes(StandardCharsets.UTF_8);
        return response.writeWith(Mono.just(
            response.bufferFactory().wrap(body)));
    }
}
```

Đọc theo đúng dòng xử lý:

- `authorizeExchange(...)` định nghĩa **khi nào từ chối quyền**; `ExceptionTranslationWebFilter` không tự tạo ra chính sách.
- `httpBasic(withDefaults())` tạo đường xác thực HTTP Basic. `formLogin(...disable())` tránh trả redirect HTML trong demo API này.
- `exceptionHandling(...)` cấu hình hai hướng xử lý lỗi cho filter translation. **Không** cần khai báo một `@Bean ExceptionTranslationWebFilter` riêng.
- `authenticationEntryPoint(...)` trả JSON có code `AUTHENTICATION_REQUIRED` và HTTP 401 nếu một request thiếu authentication hợp lệ để vượt qua authorization.
- `accessDeniedHandler(...)` trả JSON `ACCESS_DENIED` và HTTP 403 khi principal đã xác thực nhưng không có đủ quyền.
- `WWW-Authenticate: Basic realm="demo"` là challenge phù hợp với cơ chế Basic đang sử dụng. Nếu chuyển sang bearer token, đừng giữ nguyên header Basic.
- `respondJson(...)` ghi UTF-8 bằng `Mono` mà không `block()`/`subscribe()`. Text block Java 17 chứa một JSON object và ký tự xuống dòng cuối; điều đó vẫn là JSON hợp lệ.
- `{noop}` và mật khẩu trong source **chỉ dùng cho bài thực hành cục bộ**. Production phải dùng password hash mạnh, nguồn user phù hợp và HTTPS.

**Phạm vi cực kỳ quan trọng:** handler ở `exceptionHandling` định nghĩa nhánh dịch `AccessDeniedException`. Khi user gửi **Basic password sai**, lỗi có thể được xử lý trước đó bởi `AuthenticationWebFilter` và `ServerAuthenticationFailureHandler`. Vì thế đừng bắt buộc JSON body của trường hợp mật khẩu sai phải giống JSON của entry point trên; test bên dưới chỉ khẳng định status 401.

### 6.4. `src/main/java/demo/webfilter/DemoController.java`

```java
package demo.webfilter;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class DemoController {

    @GetMapping("/public")
    public Mono<String> publicData() {
        return Mono.just("public OK");
    }

    @GetMapping("/reports")
    public Mono<String> reports() {
        return Mono.just("reports OK");
    }

    @GetMapping("/failure")
    public Mono<String> unexpectedFailure() {
        return Mono.error(new IllegalStateException("unexpected failure"));
    }
}
```

`/api/failure` cố ý phát **lỗi ứng dụng không thuộc security** để chứng minh exception translation không phải bộ chuyển đổi mọi exception thành 403. Dùng `Mono.error(...)` khiến lỗi đi qua reactive error signal. Endpoint này cần authentication bởi `anyExchange().authenticated()`, nhưng dù user hợp lệ thì controller vẫn trả lỗi server.

## 7. Test đúng vai trò của ExceptionTranslationWebFilter

Các test dùng `WebTestClient.bindToApplicationContext(...).apply(springSecurity())` để cấu hình Spring Security test support, không cần mở cổng TCP. Test với Basic user thật và test với mocked principal phục vụ những mục đích khác nhau.

### 7.1. `src/test/java/demo/webfilter/ExceptionTranslationTests.java`

```java
package demo.webfilter;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ExceptionTranslationTests {

    @Autowired
    ApplicationContext applicationContext;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
            .bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void publicRouteDoesNotNeedAuthentication() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public OK");
    }

    @Test
    void unauthenticatedRequestStartsAuthentication() {
        client.get().uri("/api/reports")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE)
            .expectBody()
            .jsonPath("$.code").isEqualTo("AUTHENTICATION_REQUIRED");
    }

    @Test
    void authenticatedUserWithoutRoleGetsForbidden() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBasicAuth("guest", "guest123"))
            .exchange()
            .expectStatus().isForbidden()
            .expectBody()
            .jsonPath("$.code").isEqualTo("ACCESS_DENIED");
    }

    @Test
    void readerWithCorrectRolePassesAuthorization() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBasicAuth("reader", "reader123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("reports OK");
    }

    @Test
    void invalidBasicPasswordFailsAuthentication() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBasicAuth("reader", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void mockedGuestIsDeniedByAuthorization() {
        client.mutateWith(mockUser("someone").roles("GUEST"))
            .get().uri("/api/reports")
            .exchange()
            .expectStatus().isForbidden()
            .expectBody()
            .jsonPath("$.code").isEqualTo("ACCESS_DENIED");
    }

    @Test
    void unrelatedApplicationErrorRemainsServerError() {
        client.get().uri("/api/failure")
            .headers(h -> h.setBasicAuth("reader", "reader123"))
            .exchange()
            .expectStatus().is5xxServerError();
    }
}
```

**Lưu ý về câu lệnh `import static`:** Java cho phép xuống dòng sau `server` trong một import như trên vì token `.` thuộc đường dẫn import; nếu muốn sao chép nguyên dòng theo style IDE, có thể viết:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
```

Hai cách đều nhắm đúng API trong `spring-security-test`; không dùng `org.springframework.security.test.web.servlet...` của Servlet.

### 7.2. Ma trận kiểm thử

| Bối cảnh | Cơ chế được chứng minh | Status | JSON body cần kiểm tra? |
| --- | --- | --- | --- |
| `/api/public` không credentials | Rule `permitAll()` | 200 | Không, body là `public OK` |
| `/api/reports` không credentials | Access denied → entry point | **401** | `AUTHENTICATION_REQUIRED` |
| `/api/reports`, Basic guest đúng mật khẩu | Access denied → denied handler | **403** | `ACCESS_DENIED` |
| `/api/reports`, Basic reader đúng mật khẩu | Authorization cho phép | 200 | Không, body là `reports OK` |
| `/api/reports`, Basic reader sai mật khẩu | Authentication failure path | **401** | Không áp body của exception translation |
| `/api/reports`, mock GUEST | Đánh giá rule với principal giả | **403** | `ACCESS_DENIED` |
| `/api/failure`, Basic reader hợp lệ | Lỗi ứng dụng khác `AccessDeniedException` | **5xx** (thường 500) | Không áp body của exception translation |

Trong `mockUser(...)` Spring Security Test tạo principal đã xác thực cho request đó. Test này kiểm tra **authorization**, không chứng minh mật khẩu thật đã được xác minh. Test Basic dùng `MapReactiveUserDetailsService` mới kiểm tra luôn cơ chế xác thực mẫu.

### 7.3. Chạy test và khởi động ứng dụng

Trong thư mục project chứa `pom.xml`:

```bash
mvn clean test
mvn spring-boot:run
```

Với JDK 17+ và Maven/dependencies tương thích, kỳ vọng Surefire ghi nhận **7 tests, 0 failures, 0 errors**. Tên test và thời gian có thể khác tùy môi trường. Phần hướng dẫn này xác định kết quả dự kiến từ mã; không xem đó là bằng chứng test đã được chạy trên mọi máy.

Ở terminal khác:

```bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/reports
curl -i -u guest:guest123 http://localhost:8080/api/reports
curl -i -u reader:reader123 http://localhost:8080/api/reports
curl -i -u reader:wrong http://localhost:8080/api/reports
curl -i -u reader:reader123 http://localhost:8080/api/failure
```

Trên Windows PowerShell, chọn `curl.exe` nếu `curl` được ánh xạ sang cmdlet khác.

**Response mẫu cho request không credentials** (không cố định thứ tự các HTTP headers):

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json
WWW-Authenticate: Basic realm="demo"

{"code":"AUTHENTICATION_REQUIRED"}
```

**Response mẫu cho Basic guest đúng mật khẩu nhưng thiếu role**:

```http
HTTP/1.1 403 Forbidden
Content-Type: application/json

{"code":"ACCESS_DENIED"}
```

**Response mẫu cho Basic reader đúng quyền**:

```http
HTTP/1.1 200 OK
Content-Type: text/plain;charset=UTF-8

reports OK
```

Các status và JSON code trên bám theo cấu hình mẫu; version/transport có thể thay đổi biểu diễn header khác nhau. Lỗi application 500 và Basic password sai không có body JSON cố định từ `respondJson` trong demo.

## 8. Phân tích sâu ba đường đi thường bị nhầm

### 8.1. Request không cung cấp credentials

1. Client gọi `GET /api/reports` mà không có `Authorization`.
2. HTTP Basic authentication không chứng minh được danh tính. Security context của request có thể chứa anonymous principal.
3. `AuthorizationWebFilter` đánh giá `hasRole("READER")` và từ chối bằng `AccessDeniedException`.
4. `ExceptionTranslationWebFilter` bắt error signal ở phần downstream.
5. Filter sử dụng trust resolver để xác định người gọi chưa được xác thực theo nghĩa bảo mật.
6. `ServerAuthenticationEntryPoint` được gọi; cấu hình ví dụ trả 401 + `WWW-Authenticate: Basic` + JSON `AUTHENTICATION_REQUIRED`.

**Điểm mấu chốt:** 401 này đến từ yêu cầu **cần xác thực để tiếp tục** sau khi đã bị từ chối ở authorization.

### 8.2. Request xác thực thành công nhưng thiếu quyền

1. Client gọi endpoint và cung cấp Basic credentials hợp lệ của `guest`.
2. `AuthenticationWebFilter` xác thực user, tạo `Authentication` với `ROLE_GUEST`.
3. `AuthorizationWebFilter` cần `ROLE_READER`, nên phát `AccessDeniedException`.
4. Filter translation thấy principal được tin là đã xác thực.
5. `ServerAccessDeniedHandler` trả 403 + `ACCESS_DENIED`.

**Điểm mấu chốt:** Không dùng authentication entry point để "đăng nhập lại" một người đã chứng minh danh tính nhưng không có quyền; giải pháp là cấp đúng role hoặc sửa policy dựa trên yêu cầu thực tế.

### 8.3. Request có Basic password sai

1. Client gửi Basic `reader:wrong`.
2. `AuthenticationWebFilter` cố xác thực và nhận lỗi authentication.
3. `ServerAuthenticationFailureHandler` xử lý lỗi của bộ lọc xác thực. Với Basic mặc định, kết quả thường là 401 và authentication challenge.
4. Vì luồng thất bại ngay trong authentication filter, **không thể mặc nhiên quy kết** JSON của `ExceptionTranslationWebFilter` sẽ được gọi.

**Điểm mấu chốt:** Tùy biến `exceptionHandling(...)` **không bảo đảm mọi authentication failure** trong toàn hệ thống dùng chung JSON. Muốn thống nhất phản hồi cho Basic password sai, cần thiết kế cả failure handling tại cơ chế Basic (hoặc cấu hình entry point tương ứng theo phiên bản) và kiểm thử riêng.

## 9. Cách mở rộng cho ứng dụng thực tế

### 9.1. Khi API dùng Bearer/JWT

Với resource server sử dụng OAuth2 JWT, request thường chứa `Authorization: Bearer <access-token>`. Cấu hình `oauth2ResourceServer(...)` có cơ chế authentication entry point và access-denied handler riêng, có thể tạo `WWW-Authenticate: Bearer ...` theo HTTP Bearer token. Khi đó:

- **Không** giữ `Basic realm="demo"` từ ví dụ.
- Phân biệt token thiếu/sai/hết hạn (authentication) với token hợp lệ nhưng thiếu scope/authority (authorization).
- Kiểm tra phiên bản và cách cấu hình resource server; rule `hasAuthority("SCOPE_report.read")` khác `hasRole("READER")`.
- Khi tùy biến JSON, giữ các header hợp chuẩn của cơ chế xác thực đã chọn; test cả status/header/body thay vì chỉ test body.

### 9.2. Khi ứng dụng dùng form login/session

Authentication entry point có thể redirect tới trang login (thường là 302), không buộc mọi request chưa xác thực phải là 401. Với browser-based session, CSRF protection và cách redirect sau khi đăng nhập cần được thiết kế nhất quán. Không áp đặt logic của REST Basic cho mọi request HTML.

### 9.3. Khi security chain có nhiều cấu hình

Một ứng dụng có thể có `SecurityWebFilterChain` riêng cho `/api/**` và `/admin/**`. Spring Security chọn security chain phù hợp cho từng request theo thứ tự và matcher. Mỗi chain có thể có authentication entry point/denied handler khác nhau. Nếu JSON 401 xuất hiện ở endpoint này nhưng endpoint khác lại redirect, hãy kiểm tra **chain nào đã match** trước khi kết luận filter hoạt động sai.

### 9.4. Method security và phân quyền theo đối tượng

Reactive method security (ví dụ `@PreAuthorize` với `@EnableReactiveMethodSecurity`) có thể phát `AccessDeniedException` khi quyền không đủ. Nếu lỗi đi qua downstream reactive pipeline được filter translation bao quanh, handler tương ứng có thể biến nó thành response HTTP. Tuy nhiên không nên giả định mọi lỗi nằm ngoài pipeline hoặc mọi lần gọi service nội bộ đều đi qua WebFilter.

Đặc biệt, `hasRole("READER")` tại URL không chứng minh rằng user có quyền đọc **báo cáo số 42** hay báo cáo của tenant khác. Kiểm tra quyền sở hữu, tenant và trạng thái tài nguyên nên đặt trong service/repository. Có thể trả 403 hoặc 404 theo chính sách, nhưng không tiết lộ dữ liệu trước khi kiểm tra.

### 9.5. Khi response đã được commit

Nếu handler đã ghi headers/body hoặc bắt đầu stream dữ liệu, rồi mới phát lỗi security, framework có thể không còn thay đổi status/body thành phản hồi JSON 401/403 như mong muốn. Ví dụ phát `Flux` dài và chỉ kiểm tra quyền sau phần tử đầu tiên là quá muộn. **Hãy xác thực và kiểm tra quyền trước khi phát dữ liệu nhạy cảm**. Không thiết kế exception translation như cơ chế thu hồi dữ liệu đã gửi tới client.

### 9.6. CORS, CSRF và generic exception handler

- **CORS:** Một request preflight `OPTIONS` không đi kèm credentials như GET/POST thực tế; cần cấu hình CORS đúng cho API và policy. 401 trên preflight không nhất thiết là do thiếu role.
- **CSRF:** Lỗi CSRF trên POST/PUT/DELETE có thể được xử lý ở filter CSRF, với handler riêng. Một 403 vì CSRF không được giải bằng cách cấp thêm `ROLE_ADMIN`. Hãy kiểm tra cơ chế auth (cookie/session vs bearer) trước khi quyết định CSRF policy.
- **Global error handler:** `@RestControllerAdvice`, `WebExceptionHandler` hoặc cơ chế Boot WebFlux error handling không phải nơi thay thế tất cả phản hồi của Spring Security. Các security filter có thể trả response trước khi controller chạy.

## 10. Debug và kiểm thử an toàn

Khi kết quả thực tế không như mong đợi, hãy xác định lần lượt:

1. **Endpoint nào, method nào, security chain nào?** URL pattern có đúng không? Có rule rộng đặt trước rule cụ thể không?
2. **Lỗi xảy ra khi authentication hay authorization?** Không credentials, sai credentials, đã đăng nhập thiếu authority là ba tình huống khác nhau.
3. **Có principal loại nào?** Anonymous, HTTP Basic user, JWT authentication, remember-me hay cơ chế khác.
4. **Authority thực tế là gì?** `hasRole("READER")` cần `ROLE_READER` theo tiền tố mặc định; `hasAuthority("report:read")` đòi đúng chuỗi.
5. **Điểm nào chọn response?** Basic failure handler, exception translation entry point, denied handler, CSRF handler hay generic WebFlux error handler.
6. **Status/header/body có nhất quán?** Với Basic/Bearer, `WWW-Authenticate` có thể là một phần của hợp đồng API.
7. **Response đã commit chưa?** Với streaming, bảo vệ trước khi gửi dữ liệu.

Có thể tăng log phù hợp trong môi trường phát triển, ví dụ cấu hình tạm:

```properties
logging.level.org.springframework.security=DEBUG
```

Không bật logging nhạy cảm vô hạn ở production và không log raw `Authorization` header, mật khẩu, cookie phiên hay JWT đầy đủ. Nếu cần truy vết, dùng request/correlation ID và mã lỗi chung đã được kiểm soát.

### Một số lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Không credentials nhưng lại 403 | Policy/entry point tùy biến, ngữ cảnh principal hoặc authentication chain khác kỳ vọng | Kiểm tra anonymous/trust resolver, chain và entry point |
| Đã đăng nhập nhưng lại 401 | Authentication thất bại/hết hạn, security context không được mang qua pipeline, hoặc custom entry point | Kiểm tra credentials, context reactive, cơ chế xác thực |
| Basic password sai trả 401 nhưng không có JSON custom | Lỗi được xử lý bởi authentication failure handler | Kiểm tra `AuthenticationWebFilter` và Basic failure handling riêng |
| Role đúng mà bị 403 | Nhầm `ROLE_` prefix; user authorities khác với rule | In/kiểm tra authorities an toàn và đối chiếu `hasRole` vs `hasAuthority` |
| POST trả 403 dù đã đủ role | CSRF hoặc rule theo HTTP method | Xác định nguồn 403 và kiểm tra CSRF configuration |
| Tùy biến `@ControllerAdvice` nhưng 401 vẫn theo Spring Security | Lỗi phát sinh trong security filters trước controller | Cấu hình `exceptionHandling`, entry point/failure handler của auth |
| Xử lý lỗi bằng `block()` rồi request treo | Blocking trên reactive event-loop | Trả `Mono<Void>`, dùng `writeWith` |
| Response đang stream không sửa được thành 403 | Headers/body đã commit trước khi quyền bị từ chối | Kiểm tra quyền trước khi stream |
| Lỗi nghiệp vụ bất ngờ lại hiện 500 | `ExceptionTranslationWebFilter` không phải generic error handler | Dùng xử lý lỗi ứng dụng phù hợp; không bọc mọi exception thành `AccessDeniedException` |
| API Bearer lại trả challenge Basic | Dùng sai authentication entry point cho chain | Cấu hình Bearer entry point/headers phù hợp |
| Không biết filter chạy trước/sau authorization | Chèn filter tùy chỉnh sai thứ tự | Kiểm tra `SecurityWebFiltersOrder.EXCEPTION_TRANSLATION` và `AUTHORIZATION` |

## 11. Bài tự kiểm tra

**Câu 1.** User chưa gửi Basic credentials và gọi endpoint yêu cầu `ROLE_READER`. Quyết định "từ chối quyền" có bắt buộc luôn thành 403?  
**Đáp án:** Không. Khi thiếu authentication hợp lệ, `ExceptionTranslationWebFilter` có thể gọi `ServerAuthenticationEntryPoint`; API Basic thường trả 401.

**Câu 2.** User `guest` đăng nhập hợp lệ, nhưng chỉ có `ROLE_GUEST`. Truy cập endpoint cần `ROLE_READER` thì thành phần nào thường sinh response?  
**Đáp án:** `ServerAccessDeniedHandler` được filter translation gọi sau khi authorization phát `AccessDeniedException`; demo trả 403 và JSON `ACCESS_DENIED`.

**Câu 3.** Nếu Basic password sai, có thể khẳng định `ExceptionTranslationWebFilter` luôn tạo 401 không?  
**Đáp án:** Không. Xác thực thất bại thường được `AuthenticationWebFilter` cùng failure handler của nó xử lý. Phân biệt điều này với `AccessDeniedException` từ authorization downstream.

**Câu 4.** Tại sao không dùng `if (authentication.isAuthenticated())` để phân biệt 401/403 trong code tự viết?  
**Đáp án:** Vì anonymous authentication có thể mang cờ `isAuthenticated() == true`. Spring Security dùng logic tin cậy riêng để phân biệt anonymous/unauthenticated với principal đã xác thực.

**Câu 5.** Nếu controller phát `Mono.error(new IllegalStateException("oops"))`, `ExceptionTranslationWebFilter` có tự chuyển thành 403 không?  
**Đáp án:** Không. Nhánh translation tập trung vào `AccessDeniedException`; lỗi ứng dụng thông thường được xử lý theo error handling của WebFlux/Spring Boot.

**Câu 6.** Muốn mọi API trả cùng một JSON khi thiếu authentication, chỉ tùy biến `exceptionHandling().authenticationEntryPoint(...)` đã đủ chưa?  
**Đáp án:** Chưa chắc. Phải kiểm tra cả authentication failure handlers của Basic, Bearer, form login và các security chain liên quan; cấu hình đúng theo API stack và test từng tình huống.

**Câu 7.** Một `Flux` đã gửi 10 bản ghi cho client rồi mới phát `AccessDeniedException`. Có thể coi dữ liệu được bảo vệ nhờ exception translation không?  
**Đáp án:** Không. Thông tin đã gửi không thể lấy lại; response đã commit có thể không đổi được status/body. Phải kiểm tra quyền trước khi stream dữ liệu.

## 12. Ghi nhớ và tài liệu tham khảo

- `ExceptionTranslationWebFilter` là **bridge từ lỗi từ chối quyền downstream sang hành vi HTTP** trong Spring WebFlux.
- Nó xử lý `AccessDeniedException` qua Reactor `onErrorResume` và chọn **`ServerAuthenticationEntryPoint`** hoặc **`ServerAccessDeniedHandler`** bằng thông tin authentication đáng tin.
- **401** thường là yêu cầu cung cấp authentication; **403** thường là authentication hợp lệ nhưng không đủ quyền. Status thực tế còn tùy cơ chế Basic, Bearer, form login và cấu hình handler.
- **Basic password sai** thường thuộc `AuthenticationWebFilter` failure handling, không được giả định sẽ đi qua JSON của exception translation.
- Trong WebFlux dùng `SecurityWebFilterChain`/`ServerHttpSecurity`, không dùng `ExceptionTranslationFilter` của Servlet.
- Thiết kế security phải kiểm tra quyền **trước khi** stream dữ liệu, thử cả happy path và failure path, giữ status/header/body nhất quán.

**Tài liệu chính thức:**

- Spring Security, WebFlux Security: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security, `ServerHttpSecurity.exceptionHandling` và `ExceptionHandlingSpec`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.ExceptionHandlingSpec.html
- Spring Security, `AuthenticationWebFilter`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html
- Spring Security, `SecurityWebFiltersOrder`: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/config/web/server/SecurityWebFiltersOrder.html
- Spring Security, WebFlux authentication testing: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html
- Spring Security, implementation `ExceptionTranslationWebFilter`: https://github.com/spring-projects/spring-security/blob/main/web/src/main/java/org/springframework/security/web/server/authorization/ExceptionTranslationWebFilter.java
