# ServerAuthenticationSuccessHandler và ServerAuthenticationFailureHandler

> **Chủ đề:** Spring Security – reactive  
> **Nhóm:** Xác thực reactive  
> **Nhiệm vụ học tập:** Hiểu hai callback xử lý **kết quả của một lần thử xác thực** trong `AuthenticationWebFilter`, cách tiếp tục hoặc kết thúc HTTP exchange, cách dùng cấu hình WebFlux để tùy biến chúng, và cách kiểm thử bằng credentials thật. Mọi ví dụ dưới đây dành cho **Spring WebFlux**, không phải Spring MVC/Servlet.

## 1. Mục tiêu

Sau bài này bạn có thể:

1. Phân biệt *authentication* (kiểm tra danh tính) với *authorization* (kiểm tra quyền), từ đó biết khi nào success/failure handler được gọi.
2. Đọc đúng chữ ký `ServerAuthenticationSuccessHandler` và `ServerAuthenticationFailureHandler`, đặc biệt kiểu trả về `Mono<Void>` và `WebFilterExchange`.
3. Mô tả luồng `ServerAuthenticationConverter` → `ReactiveAuthenticationManager` → success/failure handler trong `AuthenticationWebFilter`.
4. Giải thích tại sao **đăng nhập thành công không có nghĩa là được phép truy cập tài nguyên**, và vì sao request không gửi thông tin xác thực không nhất thiết làm failure handler chạy.
5. Cấu hình handler cho HTTP Basic bằng `ServerHttpSecurity.httpBasic(...)` trong Spring Security 6.5; hiểu cách áp dụng tương tự cho form login và bộ lọc tự tạo.
6. Viết handler không `block()`, không `subscribe()` thủ công, không làm lộ mật khẩu, token hay nội dung exception.
7. Chạy ứng dụng WebFlux Java 17+ và các test kiểm tra success, failure, 401, 403 và sự tiếp tục của filter chain.

## 2. Phân biệt bốn kết quả bảo mật

Giả sử một API có tài khoản `reader` (vai trò `READER`) và `admin` (vai trò `ADMIN`). API `/api/admin` yêu cầu `ROLE_ADMIN`. Khi gửi request, có ít nhất bốn tình huống khác nhau:

| Trường hợp | Authentication đã được **thử** chưa? | Kết quả authentication | Hành vi tiếp theo |
| --- | --- | --- | --- |
| Không có HTTP Basic header | Converter thường trả `Mono.empty()`, không thử | Không có kết quả thành công/thất bại từ lần thử Basic | Request tiếp tục; nếu endpoint yêu cầu đăng nhập, authorization/entry point có thể trả **401** |
| Basic header có username/password sai | Có | `AuthenticationException` | **`ServerAuthenticationFailureHandler`** xử lý, với API Basic thường là **401** |
| Basic header đúng, gọi tài nguyên được phép | Có | `Authentication` đã xác thực | **`ServerAuthenticationSuccessHandler`** chạy; nếu cho chain đi tiếp thì controller có thể trả **200** |
| Basic header đúng nhưng user thiếu role `ADMIN` | Có | Authentication **thành công** | Success handler đã được gọi; ở bước authorization phía sau, truy cập bị từ chối, thường **403** |

**Nguyên tắc:** `ServerAuthenticationSuccessHandler` **không phải** “handler trả 200 mỗi khi truy cập được phép”. Nó phản ứng với kết quả xác thực. `ServerAuthenticationFailureHandler` **không phải** “handler trả 403 mỗi khi thiếu quyền”. Lỗi phân quyền được xử lý ở nhánh riêng, điển hình qua `ExceptionTranslationWebFilter` và `ServerAccessDeniedHandler`.

```text
HTTP request
  |
  v
AuthenticationWebFilter
  |
  +--> Có match URL/method cần xác thực không?
  |       |
  |       +-- Không --> tiếp tục WebFilter chain
  |       |
  |       v
  |    ServerAuthenticationConverter
  |       |
  |       +-- Mono.empty() --> không thử authentication; tiếp tục chain
  |       |
  |       v
  |    ReactiveAuthenticationManager
  |       |
  |       +-- Xác thực lỗi (AuthenticationException)
  |       |       |
  |       |       v
  |       |  ServerAuthenticationFailureHandler
  |       |       |
  |       |       +--> Basic: thường 401/challenge
  |       |       +--> Form: có thể redirect /login?error
  |       |
  |       +-- Xác thực thành công (Authentication)
  |               |
  |               v
  |          SecurityContext / Reactor Context
  |               |
  |               v
  |          ServerAuthenticationSuccessHandler
  |               |
  |               +--> tiếp tục chain --> authorization --> controller
  |               +--> hoặc chủ động hoàn tất response/redirect
  |
  v
AuthorizationWebFilter (khi chain còn tiếp tục)
  |
  +--> đủ quyền --> nghiệp vụ
  +--> thiếu quyền --> AccessDeniedException
                          |
                          v
                 ExceptionTranslationWebFilter
                 (entry point / access-denied handler)
```

Sơ đồ lược bỏ các filter không liên quan như CSRF, headers và request cache. Các vị trí thực tế trong security chain phụ thuộc cơ chế và cấu hình. Điều cần nhớ là **handler thuộc bước xác thực**, còn kiểm tra role/permission là một quyết định tiếp theo.

## 3. Hai interface và hợp đồng reactive

### 3.1. `ServerAuthenticationSuccessHandler`

Giao diện của Spring Security WebFlux nằm trong package `org.springframework.security.web.server.authentication`:

```java
// Chữ ký API minh họa; không phải một file Java độc lập.
Mono<Void> onAuthenticationSuccess(
    WebFilterExchange webFilterExchange,
    Authentication authentication);
```

Đối số:

- `WebFilterExchange`: đối tượng gộp `ServerWebExchange` (request/response HTTP) và `WebFilterChain` (chuỗi WebFilter cần tiếp tục nếu phù hợp).
- `Authentication`: kết quả **đã xác thực** từ manager, có thể đọc `getName()`, principal và authorities. Không suy rằng `getCredentials()` luôn còn hoặc nên ghi log.
- `Mono<Void>`: tín hiệu hoàn tất xử lý bất đồng bộ; handler có thể tiếp tục chain, redirect hoặc ghi phản hồi rồi hoàn tất.

Hai kiểu triển khai success hợp lệ nhưng **mang ý nghĩa khác nhau**:

**A. Tiếp tục lọc và xử lý nghiệp vụ** (thường đúng cho HTTP Basic/bearer API):

```java
ServerAuthenticationSuccessHandler success =
    (webFilterExchange, authentication) ->
        webFilterExchange.getChain()
            .filter(webFilterExchange.getExchange());
```

Đây là đoạn định nghĩa biến trong cấu hình có import cần thiết. Nó tương đương về mục tiêu với `WebFilterChainServerAuthenticationSuccessHandler`: thành công rồi để các filter ở phía sau kiểm tra quyền và controller thực thi. Một API có thể trả 403 **sau** khi callback success chạy nếu chủ thể chưa có quyền.

**B. Kết thúc response tại bước xác thực** (ví dụ một endpoint xử lý login riêng):

```java
ServerAuthenticationSuccessHandler success =
    (webFilterExchange, authentication) -> {
        ServerHttpResponse response =
            webFilterExchange.getExchange().getResponse();
        response.setStatusCode(HttpStatus.NO_CONTENT);
        return response.setComplete();
    };
```

Đây cũng chỉ là đoạn minh họa trong cấu hình. Nó gửi 204 và **không gọi** chuỗi filter phía sau. **Không đặt dạng B cho mọi HTTP Basic request trên resource API** nếu vẫn muốn controller xử lý request; làm vậy sẽ khiến response dừng ngay tại success handler.

### 3.2. `ServerAuthenticationFailureHandler`

Cùng package, chữ ký:

```java
// Chữ ký API minh họa; không phải một file Java độc lập.
Mono<Void> onAuthenticationFailure(
    WebFilterExchange webFilterExchange,
    AuthenticationException exception);
```

- `AuthenticationException` diễn tả lần thử xác thực không thành công; điển hình sai credentials, tài khoản không hợp lệ hoặc cơ chế identity provider từ chối.
- Failure handler **không có đối số `Authentication` đã xác thực**. Đừng dựng một principal được tin cậy từ dữ liệu client ở nhánh thất bại.
- Với HTTP Basic, thường trả 401 và header `WWW-Authenticate: Basic ...`. Với form login, thường redirect về trang login kèm trạng thái lỗi.
- Không trả thông tin chi tiết “user không tồn tại” hay “password sai” khác nhau cho client nếu điều đó khiến client dò tài khoản; không đưa raw exception, password hay access token vào response.

Ví dụ một failure handler rất ngắn:

```java
ServerAuthenticationFailureHandler failure =
    (webFilterExchange, exception) -> {
        ServerHttpResponse response =
            webFilterExchange.getExchange().getResponse();
        response.setStatusCode(HttpStatus.UNAUTHORIZED);
        return response.setComplete();
    };
```

Đoạn này **chưa** đặt `WWW-Authenticate`. Khi dùng thật với HTTP Basic nên trả challenge thích hợp; ví dụ runnable phía dưới có cả header này.

### 3.3. Tại sao cần `WebFilterExchange` thay vì chỉ `ServerWebExchange`?

`ServerWebExchange` cho bạn request, response, attributes và principal của exchange. `WebFilterExchange` **bọc thêm `WebFilterChain`**. Cần chuỗi filter để success handler có quyền lựa chọn “cho request đi tiếp”:

```java
WebFilterChain chain = webFilterExchange.getChain();
ServerWebExchange exchange = webFilterExchange.getExchange();
return chain.filter(exchange);
```

Đoạn này là mã minh họa đặt trong method handler với các import `WebFilterChain` và `ServerWebExchange`. Cả hai method `getChain()` và `getExchange()` là API của `WebFilterExchange`. Không tìm `getChain()` trực tiếp trên `ServerWebExchange`.

## 4. `AuthenticationWebFilter` triệu gọi các handler thế nào?

Trong WebFlux, `AuthenticationWebFilter` thuộc `org.springframework.security.web.server.authentication`. Có thể dùng nó gián tiếp qua `ServerHttpSecurity.httpBasic(...)`/`formLogin(...)` hoặc trực tiếp trong một cơ chế xác thực riêng.

Luồng tổng quát:

1. **Matcher:** `setRequiresAuthenticationMatcher(...)` quyết định request nào kích hoạt thử authentication. Nếu không match thì filter tiếp tục chain, không gọi success/failure handler.
2. **Converter:** `ServerAuthenticationConverter` biến `ServerWebExchange` thành `Mono<Authentication>` chưa được xác thực. HTTP Basic dùng `ServerHttpBasicAuthenticationConverter` để lấy username/password từ `Authorization`. Nếu converter phát `Mono.empty()`, không có lần thử xác thực để kết luận success hay failure.
3. **Authentication manager:** `ReactiveAuthenticationManager.authenticate(authentication)` kiểm tra chứng cứ và trả kết quả xác thực theo kiểu reactive hoặc tín hiệu lỗi.
4. **Kết quả thành công:** Spring Security xây dựng/lưu `SecurityContext` theo `ServerSecurityContextRepository` đã cấu hình, đưa authentication vào reactive context cho nhánh thích hợp và gọi success handler.
5. **Kết quả thất bại:** nhánh `AuthenticationException` được chuyển tới failure handler tương ứng, nếu chưa được biến thành một loại lỗi khác.
6. **Downstream:** chỉ được thực thi nếu handler thích hợp cho chain đi tiếp. Khi downstream yêu cầu thêm quyền, authorization vẫn có thể trả 403.

Đừng gắn nhầm `AuthenticationException` với `AccessDeniedException`:

| Khái niệm | Tín hiệu | Bước thường xử lý |
| --- | --- | --- |
| Authentication bị từ chối | `AuthenticationException` | Failure handler của authentication filter hoặc cơ chế xác thực |
| Authorization bị từ chối sau khi đã xác thực | `AccessDeniedException` | Exception translation và access-denied handler |
| Chưa xác thực nhưng gọi endpoint được bảo vệ | Thường là kết quả authorization từ chối vì thiếu danh tính | Authentication entry point để yêu cầu credentials |
| Nghiệp vụ tự phát lỗi khác, ví dụ `IllegalStateException` | Exception ứng dụng | WebFlux application error handling, không mặc nhiên là security failure |

**Trường hợp quan trọng:** Người dùng không gửi HTTP Basic header nhưng truy cập endpoint protected có thể nhận 401 **mà `ServerAuthenticationFailureHandler` tùy biến không chạy**. Bởi converter trả rỗng, không có authentication attempt sai; bước authorization/entry point mới yêu cầu xác thực.

### 4.1. Default behavior theo cơ chế

| Cơ chế | Success thường gặp | Failure thường gặp |
| --- | --- | --- |
| HTTP Basic | `WebFilterChainServerAuthenticationSuccessHandler`: tiếp tục chain | `ServerAuthenticationEntryPointFailureHandler`: chuyển sang entry point tạo HTTP Basic challenge/401 |
| Form login | `RedirectServerAuthenticationSuccessHandler`: redirect về URL lưu trước đó hoặc trang mặc định | `RedirectServerAuthenticationFailureHandler`: redirect về trang login với dấu hiệu lỗi |
| Custom `AuthenticationWebFilter` | Mặc định success tiếp tục chain | Mặc định failure yêu cầu Basic authentication; nên cấu hình rõ cho cơ chế riêng |
| OAuth2/JWT | Tùy thành phần/cơ chế; có thể là handler redirect hoặc bearer failure/entry point | Phụ thuộc flow và cơ chế, không được mặc định áp dụng handler Basic cho token |

Mặc định của Spring Security có thể được thay đổi bằng cấu hình. Khi làm việc với hệ thống thực, cần kiểm tra **filter và security chain được chọn**, cùng phương thức authentication đang hoạt động.

### 4.2. `ServerSecurityContextRepository` là việc riêng

Success handler quyết định phản hồi/tiếp tục request. `ServerSecurityContextRepository` quyết định **cách lưu và tải SecurityContext**, chẳng hạn qua session hay không lưu trạng thái. Một success handler gửi 200/204 **không tự động phát hành JWT, tạo session lâu dài hoặc cấp refresh token**. HTTP Basic gửi credentials trên mỗi request; lưu session cho form login có cơ chế riêng. Cần cấu hình kho lưu context theo đúng thiết kế, không làm `authenticationSuccessHandler` chịu trách nhiệm thay toàn bộ hệ thống identity/session.

## 5. Ví dụ Java 17+ chạy được: tùy biến success/failure của HTTP Basic

Ví dụ cố định phiên bản **Spring Boot 3.5.16** để dễ lặp lại trong quá trình học, tương ứng Spring Security 6.5.x qua dependency management. Đây là nhánh lịch sử đã kết thúc hỗ trợ OSS; khi dùng cho hệ thống triển khai thật cần chọn nhánh Spring Boot đang được hỗ trợ và kiểm tra tương thích API. Mục tiêu ở đây là học cách handler được gọi, vì vậy mã nguồn đặt sẵn user demo và chỉ dùng GET.

**Các quy tắc của ví dụ:**

- Không có credentials, `GET /api/public` → 200, không kích hoạt success/failure.
- User `reader` với password đúng gọi `/api/private` → success handler thêm header `X-Auth-Result: SUCCESS` rồi cho chain đi tiếp → controller trả 200.
- Password sai → failure handler trả 401, header HTTP Basic challenge, JSON `AUTHENTICATION_FAILED`.
- `reader` đã xác thực gọi `/api/admin` → success handler đã chạy, nhưng authorization thiếu `ROLE_ADMIN` → 403.
- `admin` đúng password gọi `/api/admin` → 200.

Header `X-Auth-Result` chỉ là **dấu quan sát cho bài học**, không phải cơ chế chứng minh danh tính với client hay phương thức cấp quyền. Production nên dùng metrics/log được kiểm soát thay vì làm lộ trạng thái nội bộ không cần thiết.

### 5.1. Cấu trúc file

```text
reactive-auth-handlers/
├── pom.xml
└── src/
    ├── main/java/demo/handlers/
    │   ├── Application.java
    │   ├── SecurityConfiguration.java
    │   └── DemoController.java
    └── test/java/demo/handlers/
        └── AuthenticationHandlersTests.java
```

### 5.2. `pom.xml`

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
    <artifactId>reactive-auth-handlers</artifactId>
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

`starter-webflux` cung cấp WebFlux và Reactor; `starter-security` cung cấp security; `starter-test` và `spring-security-test` chỉ tham gia khi chạy test. Không tự ghi version riêng cho Spring Security khi dùng Boot BOM.

### 5.3. `src/main/java/demo/handlers/Application.java`

```java
package demo.handlers;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

### 5.4. `src/main/java/demo/handlers/SecurityConfiguration.java`

```java
package demo.handlers;

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
import org.springframework.security.web.server.authentication.ServerAuthenticationSuccessHandler;
import org.springframework.security.web.server.authentication.ServerAuthenticationFailureHandler;
import reactor.core.publisher.Mono;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        ServerAuthenticationSuccessHandler success =
            (webFilterExchange, authentication) -> {
                // Dấu quan sát dành riêng cho bài học.
                webFilterExchange.getExchange()
                    .getResponse()
                    .getHeaders()
                    .set("X-Auth-Result", "SUCCESS");

                // Giữ nguyên request pipeline: authorization vẫn chạy sau đó.
                return webFilterExchange.getChain()
                    .filter(webFilterExchange.getExchange());
            };

        ServerAuthenticationFailureHandler failure =
            (webFilterExchange, exception) -> {
                ServerHttpResponse response =
                    webFilterExchange.getExchange().getResponse();

                response.setStatusCode(HttpStatus.UNAUTHORIZED);
                response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
                response.getHeaders().set(
                    HttpHeaders.WWW_AUTHENTICATE,
                    "Basic realm=\"reactive-demo\"");

                // Không trả exception.getMessage(), username hoặc password.
                byte[] bytes = "{\"code\":\"AUTHENTICATION_FAILED\"}"
                    .getBytes(StandardCharsets.UTF_8);

                return response.writeWith(Mono.just(
                    response.bufferFactory().wrap(bytes)));
            };

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public").permitAll()
                .pathMatchers("/api/admin").hasRole("ADMIN")
                .pathMatchers("/api/private", "/api/me").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(basic -> basic
                .authenticationSuccessHandler(success)
                .authenticationFailureHandler(failure)
            )
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
            .password("{noop}reader123")
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password("{noop}admin123")
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }
}
```

**Đọc mã theo ý nghĩa của handler:**

- `httpBasic(...)` cấu hình HTTP Basic authentication filter; trên Spring Security 6.5, `HttpBasicSpec` có setter `authenticationSuccessHandler` và `authenticationFailureHandler`.
- Success handler **không cố định** status 200, cũng không tự `setComplete()`. Nó ghi một header quan sát rồi gọi `webFilterExchange.getChain().filter(...)`. Đó là điều kiện để `AuthorizationWebFilter` và controller được thực thi ở downstream.
- Failure handler nhận `AuthenticationException`, tạo **401** và JSON body. Với HTTP Basic, `WWW-Authenticate: Basic realm="reactive-demo"` báo loại challenge phù hợp.
- `formLogin(...disable())` tránh cơ chế form login/redirect mặc định, giúp bài học tập trung vào Basic.
- `roles("ADMIN")` tạo authority `ROLE_ADMIN`. `hasRole("ADMIN")` kiểm tra authority này theo prefix mặc định, không tự xác thực người dùng.
- `MapReactiveUserDetailsService` lưu tài khoản trong RAM. `{noop}` **không mã hóa mật khẩu**, chỉ hợp lệ như demo; production phải dùng password hash mạnh, secret management và HTTPS.
- Tất cả endpoint demo là GET. Không tắt CSRF bừa bãi; nếu chuyển sang form login và request thay đổi trạng thái, cần CSRF token/chiến lược thích hợp.

**Giới hạn của callback custom:** Một custom failure handler đơn giản đổi mọi `AuthenticationException` thành 401 có thể che giấu lỗi hạ tầng như identity provider/database bị lỗi. Production cần phân biệt `AuthenticationServiceException` với sai credentials và chọn cách ghi nhận/xử lý riêng theo chính sách. `ServerAuthenticationEntryPointFailureHandler` có cơ chế có thể rethrow `AuthenticationServiceException` mặc định; khi thay nó bằng handler custom, hãy kiểm tra hành vi đó.

### 5.5. `src/main/java/demo/handlers/DemoController.java`

```java
package demo.handlers;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class DemoController {

    @GetMapping("/public")
    public Mono<String> publicInfo() {
        return Mono.just("public OK");
    }

    @GetMapping("/private")
    public Mono<String> privateInfo() {
        return Mono.just("private OK");
    }

    @GetMapping("/admin")
    public Mono<String> adminInfo() {
        return Mono.just("admin OK");
    }

    @GetMapping("/me")
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
    }
}
```

`/api/me` cho thấy authentication đã được đưa vào Reactor security context và đọc được bởi handler phía sau. `ReactiveSecurityContextHolder` là cơ chế reactive, khác sử dụng `ThreadLocal` kiểu Servlet để truy cập thông tin principal.

## 6. Test bằng `WebTestClient`: phải dùng credentials thật

Nếu chỉ dùng `mockUser()` hoặc `@WithMockUser`, test tạo sẵn principal đã xác thực và có thể bỏ qua đường xử lý credentials thật, nên **không chứng minh success/failure callback trong `AuthenticationWebFilter` chạy**. Để kiểm tra bài này, các request liên quan phải thật sự gửi `Authorization: Basic ...`.

Dùng `WebTestClient.bindToApplicationContext(...).apply(springSecurity())` để kiểm tra toàn bộ WebFlux security chain trong bộ test mà không cần mở cổng TCP.

### 6.1. `src/test/java/demo/handlers/AuthenticationHandlersTests.java`

```java
package demo.handlers;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class AuthenticationHandlersTests {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void publicRequestDoesNotRequireAuthenticationAttempt() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().doesNotExist("X-Auth-Result")
            .expectBody(String.class).isEqualTo("public OK");
    }

    @Test
    void missingBasicHeaderUsesAuthenticationEntryPoint() {
        client.get().uri("/api/private")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE)
            .expectHeader().doesNotExist("X-Auth-Result");
    }

    @Test
    void invalidPasswordInvokesFailureHandler() {
        client.get().uri("/api/private")
            .headers(headers -> headers.setBasicAuth("reader", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueEquals(
                HttpHeaders.WWW_AUTHENTICATE,
                "Basic realm=\"reactive-demo\"")
            .expectHeader().contentTypeCompatibleWith(
                org.springframework.http.MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.code").isEqualTo("AUTHENTICATION_FAILED");
    }

    @Test
    void unknownUsernameInvokesFailureHandler() {
        client.get().uri("/api/private")
            .headers(headers -> headers.setBasicAuth("unknown", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized()
            .expectBody()
            .jsonPath("$.code").isEqualTo("AUTHENTICATION_FAILED");
    }

    @Test
    void successHandlerContinuesToController() {
        client.get().uri("/api/private")
            .headers(headers -> headers.setBasicAuth("reader", "reader123"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals("X-Auth-Result", "SUCCESS")
            .expectBody(String.class).isEqualTo("private OK");
    }

    @Test
    void successfulAuthenticationCanStillBeForbidden() {
        client.get().uri("/api/admin")
            .headers(headers -> headers.setBasicAuth("reader", "reader123"))
            .exchange()
            .expectStatus().isForbidden()
            .expectHeader().valueEquals("X-Auth-Result", "SUCCESS");
    }

    @Test
    void adminWithCorrectCredentialsMayAccessAdminEndpoint() {
        client.get().uri("/api/admin")
            .headers(headers -> headers.setBasicAuth("admin", "admin123"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals("X-Auth-Result", "SUCCESS")
            .expectBody(String.class).isEqualTo("admin OK");
    }

    @Test
    void authenticatedPrincipalIsAvailableDownstream() {
        client.get().uri("/api/me")
            .headers(headers -> headers.setBasicAuth("reader", "reader123"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals("X-Auth-Result", "SUCCESS")
            .expectBody(String.class).isEqualTo("reader");
    }

    @Test
    void invalidCredentialsOnPublicRouteStillFailAuthentication() {
        client.get().uri("/api/public")
            .headers(headers -> headers.setBasicAuth("reader", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized()
            .expectBody()
            .jsonPath("$.code").isEqualTo("AUTHENTICATION_FAILED");
    }
}
```

**Vì sao test cuối đáng chú ý?** Rule `permitAll()` nghĩa là endpoint không cần authentication để truy cập; nó **không** có nghĩa Spring Security bắt buộc bỏ qua mọi credentials được client gửi. Basic filter có thể vẫn cố xác thực header được cung cấp và phát failure trước khi request tới authorization.

### 6.2. Ma trận kết quả

| Request | Success handler | Failure handler | Status mong đợi | Giải thích |
| --- | --- | --- | --- | --- |
| `GET /api/public`, không header | Không | Không | **200** | Public, converter không tạo authentication attempt |
| `GET /api/private`, không header | Không | Không | **401** | Authentication entry point yêu cầu chứng cứ hợp lệ |
| `GET /api/private`, `reader:wrong` | Không | **Có** | **401** + JSON code | Credentials sai |
| `GET /api/private`, `unknown:wrong` | Không | **Có** | **401** + JSON code | User không tồn tại, không tiết lộ chi tiết cho client |
| `GET /api/private`, `reader:reader123` | **Có** | Không | **200** + success header | Authentication thành công, controller chạy |
| `GET /api/admin`, `reader:reader123` | **Có** | Không | **403** | Authentication đúng, authorization thiếu `ROLE_ADMIN` |
| `GET /api/admin`, `admin:admin123` | **Có** | Không | **200** | Có quyền `ROLE_ADMIN` |
| `GET /api/me`, `reader:reader123` | **Có** | Không | **200**, body `reader` | Reactive context cho phép đọc principal |
| `GET /api/public`, `reader:wrong` | Không | **Có** | **401** | Request công khai vẫn có thể thất bại khi client chủ động gửi credentials sai |

Một `AuthenticationException` phát sinh do hệ thống authentication bên ngoài bị ngắt kết nối không nhất thiết nên được chuyển về lỗi sai mật khẩu. Bài test trên chỉ kiểm tra username/password trong memory; production nên thêm test ứng với lỗi hạ tầng, rate limit và timeout phù hợp.

## 7. Chạy và quan sát bằng terminal

Tại thư mục chứa `pom.xml`:

```bash
java -version
mvn -version
mvn clean test
```

JDK 17+ và Maven tương thích phải hiện diện. Với mã đã liệt kê, dự kiến có **9 phương thức `@Test`** chạy. Xem báo cáo Maven Surefire tại `target/surefire-reports`. Thông báo build và thời gian test không cố định theo từng máy; xác minh status thực tế qua kết quả chạy.

Khởi chạy:

```bash
mvn spring-boot:run
```

Gọi bằng `curl` trong terminal khác:

```bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/private
curl -i -u reader:wrong http://localhost:8080/api/private
curl -i -u reader:reader123 http://localhost:8080/api/private
curl -i -u reader:reader123 http://localhost:8080/api/admin
curl -i -u admin:admin123 http://localhost:8080/api/admin
curl -i -u reader:reader123 http://localhost:8080/api/me
```

Trên Windows PowerShell, chọn `curl.exe` nếu `curl` được ánh xạ sang cmdlet. Các lệnh trên dùng user demo và HTTP localhost, không mang password mẫu sang môi trường thực.

Với password sai, response mẫu:

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json
WWW-Authenticate: Basic realm="reactive-demo"

{"code":"AUTHENTICATION_FAILED"}
```

Với `reader` hợp lệ, gọi `/api/private`:

```http
HTTP/1.1 200 OK
X-Auth-Result: SUCCESS
Content-Type: text/plain;charset=UTF-8

private OK
```

Với `reader` hợp lệ nhưng gọi `/api/admin`:

```http
HTTP/1.1 403 Forbidden
X-Auth-Result: SUCCESS
```

Ý nghĩa dòng cuối: header `X-Auth-Result: SUCCESS` chỉ xác nhận **bước xác thực** thành công; response vẫn là 403 vì bước **kiểm tra quyền** từ chối. HTTP header như `Content-Length`, `Date` hay nội dung body lỗi 403 tùy server/cấu hình nên không cố định trong ví dụ.

## 8. Khi nào dùng handler có sẵn thay vì lambda?

Spring Security đã cung cấp nhiều implementation:

| Implementation | Công việc |
| --- | --- |
| `WebFilterChainServerAuthenticationSuccessHandler` | Sau authentication success, tiếp tục `WebFilterChain`. Phù hợp kiểu Basic API |
| `RedirectServerAuthenticationSuccessHandler` | Redirect sau login, có thể xét saved request và URL mặc định; thường gặp ở form login |
| `RedirectServerAuthenticationFailureHandler` | Redirect tới URL lỗi đăng nhập |
| `ServerAuthenticationEntryPointFailureHandler` | Biến entry point thành failure handler, thường dùng trả challenge khi xác thực thất bại |
| `DelegatingServerAuthenticationSuccessHandler` | Phối hợp nhiều success handler theo thiết kế cụ thể |
| `ConcurrentSessionControlServerAuthenticationSuccessHandler` | Bổ trợ kiểm soát phiên đồng thời khi chính sách/session registry được cấu hình |

Đừng thay default success của HTTP Basic bằng handler redirect hoặc `setComplete` tùy tiện; Basic authentication được thực hiện trên các request tài nguyên, và controller thường cần tiếp tục xử lý. Ngược lại, một endpoint form login có thể **cố ý kết thúc response** bằng redirect hoặc 204.

### 8.1. Cấu hình form login (đoạn bổ sung)

Đoạn dưới **không thuộc project Basic ở mục 5**; dùng khi bạn có ứng dụng WebFlux form-based login, nơi request login thường là `POST /login`. Đặt trong phần cấu hình của `ServerHttpSecurity`:

```java
.formLogin(form -> form
    .authenticationSuccessHandler(
        new RedirectServerAuthenticationSuccessHandler("/dashboard"))
    .authenticationFailureHandler(
        new RedirectServerAuthenticationFailureHandler("/login?error")))
```

Cần import hai implementation `RedirectServerAuthenticationSuccessHandler` và `RedirectServerAuthenticationFailureHandler` trong package `org.springframework.security.web.server.authentication`.

Form login mặc định xử lý username/password ở form data, thường gắn với session. Với ứng dụng trình duyệt, phải bảo vệ CSRF khi cần và xử lý cookie/session, session fixation, giới hạn phiên, logout. Không dùng mô hình stateless Basic để suy ra form login có cùng chính sách, và không bảo đảm chỉ đổi handler là đã thiết kế đầy đủ login.

### 8.2. Custom `AuthenticationWebFilter`: chỗ lắp handler

Khi phát triển authentication flow riêng, có thể dựng một `AuthenticationWebFilter` với `ReactiveAuthenticationManager` và cấu hình:

```java
// Khung minh họa; chưa phải chương trình độc lập.
AuthenticationWebFilter filter = new AuthenticationWebFilter(manager);
filter.setRequiresAuthenticationMatcher(matcher);
filter.setServerAuthenticationConverter(converter);
filter.setAuthenticationSuccessHandler(successHandler);
filter.setAuthenticationFailureHandler(failureHandler);
filter.setSecurityContextRepository(repository);
```

Ở đây `manager`, `matcher`, `converter`, `repository` và handlers là những thành phần **phải được ứng dụng cung cấp**, không phải biến Java được định nghĩa sẵn. Phải gắn filter vào security chain ở vị trí thích hợp và kiểm tra thứ tự filter. Đặc biệt, nếu converter trả `Mono.empty()` thì không có lần thử xác thực để một success/failure handler xử lý.

Trong luồng nhiều cơ chế (Basic, bearer, form, mTLS...), mỗi authentication filter có thể có handler riêng. Không cho một bộ handler Basic “bắt tất cả lỗi xác thực” nếu request thực tế được bộ lọc OAuth2/Bearer xử lý.

## 9. Sử dụng `Mono<Void>` đúng cách trong handler

### 9.1. Không dùng `block()` hoặc gọi `subscribe()` thủ công

Một handler reactive cần **trả về publisher** biểu diễn việc cần làm. Nếu phải ghi sự kiện audit bất đồng bộ, mô hình khái niệm là:

```java
// Minh họa, phụ thuộc auditService do ứng dụng cung cấp.
ServerAuthenticationSuccessHandler success = (exchange, auth) ->
    auditService.recordLoginSuccess(auth.getName())
        .then(exchange.getChain().filter(exchange.getExchange()));
```

Trong đoạn này `auditService.recordLoginSuccess(...)` phải trả `Mono<Void>` (hoặc publisher tương thích). **Đây là mã minh họa chưa độc lập**, không sử dụng nếu chưa định nghĩa audit service và chính sách xử lý lỗi audit. Nếu audit không được phép làm hỏng login, cần xử lý lỗi của audit riêng và minh bạch. Không dùng `auditService.record(...).subscribe()` rồi trả `Mono.empty()` vì tạo subscription tách rời, khó kiểm soát lỗi/cancellation và mất ngữ cảnh.

### 9.2. Trả response xong phải kết thúc đúng

Khi tự ghi body, dùng `ServerHttpResponse.writeWith(...)` và trả `Mono<Void>`. Nếu chỉ muốn status, `response.setComplete()` thích hợp. Đừng `response.setStatusCode(UNAUTHORIZED)` rồi tiếp tục filter chain khi đã quyết định từ chối; downstream có thể ghi thêm dữ liệu hoặc khiến response committed không thể đổi.

Tương tự, đừng vừa `response.writeWith(...)` vừa `chain.filter(...)` sau đó nếu không có lý do và kiểm soát rõ: có thể ghi response hai lần hoặc làm lẫn ý nghĩa authentication failure.

### 9.3. Dữ liệu nào an toàn cho log/response?

- Có thể ghi sự kiện dạng “authentication success/failure”, request/correlation ID, thời điểm và loại authentication ở mức cần thiết.
- Không ghi mật khẩu, token, nội dung `Authorization` header, session secret, `authentication.getCredentials()` hay nguyên văn exception.
- Không phân biệt “user tồn tại” và “password sai” bằng phản hồi có thể quan sát được. Dùng chung `AUTHENTICATION_FAILED` khi thích hợp.
- Cân nhắc timeouts, backpressure, retry, rate limiting và ghi audit bất đồng bộ theo chính sách vận hành; không biến handler thành thao tác I/O chặn event-loop.
- Với OAuth2/OIDC, failure/success redirect hoặc token response phải tuân theo giao thức, không thay bằng JSON tùy tiện nếu phá hỏng state/nonce/PKCE và flow đang dùng.

## 10. Debug: phân biệt callback với exception translation và authorization

Khi chỉ nhìn một response 401 hoặc 403, **không đủ để kết luận** callback nào đã chạy. Cần đi theo thứ tự:

1. Request có match `SecurityWebFilterChain` và filter authentication đang xem xét không?
2. Converter có tạo `Authentication` hay trả `Mono.empty()`?
3. Manager xác thực thành công, từ chối, hay lỗi hạ tầng?
4. Success/failure handler nào đã được cấu hình tại authentication filter đó?
5. Nếu success handler tiếp tục chain, `AuthorizationWebFilter` có yêu cầu authority nào?
6. Nếu authorization phát `AccessDeniedException`, response do `ExceptionTranslationWebFilter` gọi entry point hay denied handler?
7. Có CSRF/CORS filter, multiple security chains, response đã commit, hoặc handler tầng ứng dụng can thiệp không?

| Hiện tượng | Cách hiểu thường đúng | Cần kiểm tra |
| --- | --- | --- |
| Không có header Basic → 401 nhưng custom failure JSON không xuất hiện | Không có authentication attempt; entry point yêu cầu đăng nhập | `ServerAuthenticationConverter`, `ServerAuthenticationEntryPoint` |
| Basic password sai → JSON failure 401 | `AuthenticationWebFilter` gọi failure handler | Password encoder, user store, failure handler |
| Basic đúng nhưng 403 | Xác thực thành công, phân quyền thất bại | `ROLE_`, authorities, policy và denied handler |
| Basic đúng mà controller không chạy | Success handler đã `setComplete`/redirect thay vì continue chain | `WebFilterChainServerAuthenticationSuccessHandler` hoặc `getChain().filter` |
| `mockUser` test xanh nhưng JSON failure không được test | Test mock bỏ qua xác thực bằng credentials | Dùng HTTP Basic thật hoặc authentication flow thật trong `WebTestClient` |
| Một API trả redirect login, API khác trả 401 | Có thể đang dùng form login hoặc chain/entry point khác nhau | `formLogin`, `httpBasic`, request matcher và Accept |
| Thiếu quyền nhưng custom failure handler không chạy | `AccessDeniedException` thuộc authorization | `ExceptionTranslationWebFilter`, `ServerAccessDeniedHandler` |
| POST bị 403 dù user đúng | Có thể là CSRF, không phải sai password | CSRF config/token, HTTP method, cookie/session |
| Success handler ghi `200` cho mọi request rồi trả `setComplete` | Controller và rule downstream không thực thi | Thiết kế lại success handler theo loại authentication |
| Có 401 thay vì lỗi dịch vụ identity provider | Handler custom đổi mọi `AuthenticationException` thành BAD_CREDENTIALS | Phân biệt `AuthenticationServiceException`, metrics và chính sách lỗi |
| Mất danh tính sau thao tác async | Tách subscription hoặc đọc ThreadLocal ngoài Reactor | `ReactiveSecurityContextHolder`, Reactor pipeline |
| Body lỗi chứa raw exception/token | Rò rỉ dữ liệu nhạy cảm | Dùng mã lỗi chung, bỏ thông tin bí mật |

## 11. Câu hỏi tự kiểm tra

**Câu 1.** User gửi HTTP Basic username/password đúng rồi gọi endpoint cần role mà user không có. Success hay failure handler sẽ chạy? HTTP status cuối có thể là gì?

**Đáp án:** Authentication thành công nên **success handler chạy**. Nếu success cho chain đi tiếp, bước authorization sau đó có thể từ chối và trả **403**. Không gọi authentication failure chỉ vì thiếu quyền.

**Câu 2.** Không có HTTP Basic header, gọi endpoint yêu cầu đăng nhập và nhận 401. Có chắc `ServerAuthenticationFailureHandler` đã chạy?

**Đáp án:** Không. Converter có thể trả `Mono.empty()`, filter bỏ qua authentication attempt, rồi entry point ở nhánh authorization tạo 401.

**Câu 3.** Vì sao success handler của Basic thường cần tiếp tục chain?

**Đáp án:** Basic credentials gắn với request tài nguyên hiện tại. Xác thực xong, request còn phải qua authorization và handler/controller; `setComplete()` sớm làm ngừng toàn bộ xử lý.

**Câu 4.** `ServerAuthenticationFailureHandler` nhận `AuthenticationException` hay `AccessDeniedException`?

**Đáp án:** `AuthenticationException`. `AccessDeniedException` thường thuộc bước kiểm tra quyền và exception translation.

**Câu 5.** Cùng HTTP 401, thiếu credentials và credentials sai có thể đi qua hai chỗ xử lý khác nhau không?

**Đáp án:** Có. Thiếu credentials thường do authorization/entry point yêu cầu xác thực; credentials sai thường do authentication failure handler. Response có thể khác nhau nếu các handler được tùy biến không đồng bộ.

**Câu 6.** Vì sao `@WithMockUser` không đủ để chứng minh password failure handler đã được gọi?

**Đáp án:** Vì `@WithMockUser` thiết lập principal giả đã xác thực, không thực hiện kiểm tra username/password thật qua `ReactiveAuthenticationManager`.

**Câu 7.** Nếu một custom failure handler `response.writeWith(...)` xong lại gọi `chain.filter(exchange)`, điều gì có thể xảy ra?

**Đáp án:** Request bị từ chối vẫn đi xuống downstream và có thể phát sinh ghi response lần hai hoặc xử lý dữ liệu khi không nên; cần trả publisher hoàn tất phản hồi và dừng chain.

**Câu 8.** Một handler trả `Mono<Void>` nhưng trong đó gọi API chặn bằng `block()`. Điều này có phù hợp WebFlux không?

**Đáp án:** Không. `Mono<Void>` không tự làm thao tác blocking thành non-blocking. Cần compose publisher bất đồng bộ bằng `flatMap`, `then`, `writeWith` hoặc thiết kế integration thích hợp.

**Câu 9.** Khi chuyển từ form login sang Bearer JWT, có thể dùng nguyên `WWW-Authenticate: Basic ...` trong failure handler không?

**Đáp án:** Không. Phản hồi phải tuân cơ chế Bearer và cấu hình resource server đang dùng. Success/failure handler có thể thuộc filter khác, không mặc định áp dụng cùng callback Basic.

## 12. Ghi nhớ và tài liệu tham khảo

- `ServerAuthenticationSuccessHandler` nhận **`Authentication` hợp lệ** cùng `WebFilterExchange`, trả `Mono<Void>`; nó có thể **tiếp tục chain** hoặc **kết thúc response**, tùy flow.
- `ServerAuthenticationFailureHandler` nhận **`AuthenticationException`** và thường tạo HTTP challenge, response lỗi hoặc redirect, không có principal đã được xác thực.
- **Authentication success ≠ authorization success**. HTTP Basic đúng mà thiếu `ROLE_ADMIN` vẫn có thể trả 403 phía sau.
- **Không credentials ≠ failed authentication attempt**. Converter trả rỗng khiến failure handler không được gọi; một entry point khác có thể trả 401.
- Với WebFlux, dùng `ServerHttpSecurity`, `AuthenticationWebFilter`, `WebFilterExchange`, `ReactiveSecurityContextHolder`; đừng trộn các interface Servlet như `AuthenticationSuccessHandler` hoặc `AuthenticationFailureHandler`.
- Viết response theo mô hình reactive, không log credentials, không chạy subscription thủ công trong handler và kiểm tra cả status/header/body với `WebTestClient`.

**Tài liệu chính thức:**

- Spring Security 6.5 – `ServerAuthenticationSuccessHandler`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationSuccessHandler.html
- Spring Security 6.5 – `ServerAuthenticationFailureHandler`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationFailureHandler.html
- Spring Security 6.5 – `AuthenticationWebFilter`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html
- Spring Security 6.5 – `ServerHttpSecurity.HttpBasicSpec`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.HttpBasicSpec.html
- Spring Security 6.5 – `ServerHttpSecurity.FormLoginSpec`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.FormLoginSpec.html
- Spring Security – Reactive authentication testing: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html
- Spring Security – WebTestClient security setup: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html
