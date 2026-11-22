# Chọn chuyển hướng hoặc JSON theo loại điểm truy cập và nội dung yêu cầu

> **Ngữ cảnh:** Spring Security 6.x trên Spring WebFlux, Spring Boot 3.3.x và Java 17+. Bài này tập trung vào **phản hồi lỗi bảo mật**: lúc nào trình duyệt nên được chuyển đến trang đăng nhập, lúc nào API nên trả JSON kèm HTTP 401/403, và cách áp dụng chính sách theo **loại điểm truy cập (web/API)** cộng với header **Accept**. Ví dụ dùng Spring Boot 3.3.13 để nhất quán cú pháp; trước khi triển khai thật cần chọn phiên bản Spring đang được hỗ trợ và đã vá bảo mật.

## 1. Vấn đề: cùng một lỗi xác thực, client mong đợi khác nhau

Một ứng dụng có thể phục vụ đồng thời:

- **Trang web HTML:** người dùng mở `GET /web/me` trong tab trình duyệt. Nếu chưa đăng nhập, trải nghiệm thông thường là HTTP redirect đến `/login`.
- **API JSON:** frontend `fetch(...)`, ứng dụng mobile hoặc tích hợp server-to-server gọi `GET /api/me`. Nếu chưa đăng nhập, client cần HTTP **401** và một JSON ổn định để quyết định có hiển thị dialog đăng nhập, refresh token hay yêu cầu người dùng đăng nhập lại.
- **Trang web được gọi bằng AJAX:** đường dẫn `/web/me` nhưng request có `Accept: application/json`; redirect đến HTML login page sẽ khiến code đang đợi JSON nhận HTML hoặc bị trình duyệt tự follow 302. Có thể chọn **401 JSON**.
- **Người đã đăng nhập nhưng thiếu quyền:** không nên bị đưa về trang login như người chưa xác thực. Nên nhận **403 Forbidden** dưới representation phù hợp.

Sự khác biệt này thuộc về **cách trình bày phản hồi**, không phải thay đổi quyền truy cập. Một route đòi `ROLE_ADMIN` vẫn đòi role đó bất kể client yêu cầu HTML hay JSON.

### Mô hình quyết định

```text
HTTP request
    |
    v
Authentication (cookie/form, Basic, bearer token, ...)
    |
    v
Authorization (path, method, role, dữ liệu)
    |
    +--> Được phép ----------------------------------> Controller
    |
    +--> Thiếu authentication / cần bắt đầu login
    |            |
    |            +-- Trang web + navigation HTML -> 302 /login
    |            |
    |            +-- API hoặc request mong JSON    -> 401 problem+json
    |
    +--> Đã xác thực nhưng không đủ quyền
                 |
                 +-- Browser navigation HTML       -> 403 HTML
                 |
                 +-- API hoặc request mong JSON    -> 403 problem+json
```

Điều kiện quyết định *nội dung* phản hồi không bao giờ được phép tự nâng mức quyền. Với request mang credential sai, handler xác thực có thể thất bại **trước** lớp authorization; phải kiểm tra cả nhánh đó chứ không chỉ `exceptionHandling`.

## 2. Hiểu đúng 302, 401 và 403

| HTTP status | Ý nghĩa trong luồng này | Dạng phản hồi thường gặp | Không nên làm |
|---|---|---|---|
| `302 Found` hoặc cơ chế redirect phù hợp | Điều hướng client HTML chưa login đến `/login` | Header `Location: /login`, có thể không có JSON | Trả redirect login cho API rồi kỳ vọng client tự hiểu đó là lỗi auth |
| `401 Unauthorized` | Chưa có authentication hợp lệ hoặc thông tin xác thực không được chấp nhận | JSON chứa mã lỗi; với HTTP authentication cần `WWW-Authenticate` phù hợp | Đổi thành 403 cho mọi trường hợp chỉ vì muốn che khác biệt |
| `403 Forbidden` | Request bị chặn dù đã xác thực, hoặc một chính sách khác (ví dụ CSRF) từ chối | JSON/HTML 403 | Redirect user có role sai về trang login, gây vòng lặp |
| `400 Bad Request` | Payload/path/query không hợp lệ | Lỗi validation theo contract | Gọi lỗi input là “not authenticated” |
| `404 Not Found` | Endpoint/đối tượng không tồn tại hoặc API chủ ý che tính tồn tại của resource | JSON/HTML 404 | Tin rằng mọi 404 có nghĩa Spring Security đã kiểm quyền |
| `405 Method Not Allowed` | Handler không hỗ trợ method đó | Response framework | Mong nhận 405 nếu security denyAll chặn trước controller |
| `406 Not Acceptable` | Không thể tạo representation hợp lệ theo content negotiation của handler | HTTP 406 | Tự biến mọi Accept không quen thành 302 login |
| `429 Too Many Requests` | Rate limit vượt ngưỡng | JSON/headers về rate limit | Trộn với 401/403 khi áp dụng login throttling |

**401 không đồng nghĩa “mật khẩu sai”.** Nó cũng áp dụng khi **chưa gửi** thông tin xác thực cho resource được bảo vệ. Với HTTP Basic/Bearer, server nên trả challenge `WWW-Authenticate` theo giao thức; ví dụ API ở dưới dùng Basic nên chủ động trả `WWW-Authenticate: Basic realm="api"`.

**403 không luôn chỉ là “đã đăng nhập nhưng thiếu role”.** CSRF filter có thể từ chối POST/DELETE bằng 403, còn các filter/exception handler khác có thể định dạng response theo cách riêng. Phải kiểm thử thực tế nhánh CSRF thay vì mặc định mọi lỗi 403 đều đi qua đúng một `ServerAccessDeniedHandler` tùy chỉnh.

## 3. Ba câu hỏi trước khi chọn phản hồi

### 3.1 Đây là API hay trang web?

Phân loại theo **route contract** là điều ổn định hơn so với đoán client:

- `/api/**`: **luôn** trả response máy đọc được khi lỗi authentication/authorization, kể cả client gửi `Accept: text/html`.
- `/web/**`: có thể trả HTML/redirect cho **navigation**, hoặc JSON khi request chủ động yêu cầu JSON.
- `/login`: là UI flow cho đăng nhập bằng form; không thay thế một endpoint đăng nhập bằng token.
- Route không có contract rõ ràng: nên có quy tắc fallback an toàn, tránh redirect tới login cho cả webhook, health, API ngoài ý muốn.

**Path không phải bằng chứng danh tính.** Phân loại API hay web giúp chọn representation; xác thực/authorization vẫn phải dựa trên Authentication do Spring Security cung cấp.

### 3.2 Client muốn nhận gì? Header Accept

`Accept` mô tả các **kiểu nội dung response** mà client chấp nhận. Nó khác với `Content-Type`, vốn mô tả **nội dung request body** đang gửi.

```http
GET /web/me HTTP/1.1
Accept: text/html
```

Thể hiện navigation HTML. Trong khi:

```http
GET /web/me HTTP/1.1
Accept: application/json
```

Thể hiện request muốn JSON. Một số HTTP client gửi mặc định:

```http
Accept: */*
```

Nó **không** phải bằng chứng client là browser đang điều hướng trang. Trong chính sách của bài này, `*/*` **không kích hoạt redirect**; fallback là JSON.

Browser navigation hiện đại thường gửi `text/html` tường minh bên cạnh `application/xhtml+xml` và `*/*`. AJAX/fetch có thể gửi `*/*` nếu lập trình viên không đặt `Accept`. Không nên dựa vào `User-Agent` hoặc `X-Requested-With` làm nền tảng duy nhất: chúng có thể vắng mặt hoặc bị client tự đặt.

### 3.3 Đây có phải thao tác navigation an toàn?

Ví dụ chỉ redirect khi request web dùng **GET/HEAD** và khai báo **Accept HTML tường minh**. Đối với POST/PUT/PATCH/DELETE có thể bị từ chối trước bởi CSRF; redirect sau một thao tác không idempotent cũng dễ làm client khó hiểu. Luồng login success có redirect riêng do form-login handler quản lý, không bị quy tắc GET/HEAD này chi phối.

**Quy ước nếu Accept đồng thời ghi `text/html` và `application/json`:** demo ưu tiên JSON có chủ đích để client tích hợp không vô tình nhận HTML login. Đây là **quy ước sản phẩm** của ví dụ, không phải bộ content negotiation tổng quát có xét hết các tham số chất lượng `q`. Code có kiểm tra `q=0` để không coi media type bị từ chối là hợp lệ.

## 4. WebFlux security sử dụng những interface nào?

Trong Spring Security **reactive**, hai điểm mở rộng chính nằm dưới `ServerHttpSecurity.exceptionHandling(...)`.

### 4.1 ServerAuthenticationEntryPoint

`org.springframework.security.web.server.ServerAuthenticationEntryPoint` nhận một `ServerWebExchange` và một `AuthenticationException`, trả về `Mono<Void>`:

```java
Mono<Void> commence(
    ServerWebExchange exchange, AuthenticationException exception);
```

Đây là **signature giản lược**. Entry point quyết định hành vi khi một người gọi cần bắt đầu quá trình authentication: ví dụ redirect login, gửi status 401 hoặc tạo JSON. Một số implementation có sẵn:

- `RedirectServerAuthenticationEntryPoint`: chuyển đến URL được cấu hình.
- `HttpStatusServerEntryPoint`: ghi HTTP status, không tự tạo JSON body.
- `HttpBasicServerAuthenticationEntryPoint`: challenge HTTP Basic.

**Không nhầm** với `AuthenticationEntryPoint` của Servlet. WebFlux dùng `ServerAuthenticationEntryPoint` trả Publisher thay vì thao tác Servlet response đồng bộ.

### 4.2 ServerAccessDeniedHandler

`org.springframework.security.web.server.authorization.ServerAccessDeniedHandler` xử lý `AccessDeniedException`, trả `Mono<Void>`:

```java
Mono<Void> handle(
    ServerWebExchange exchange, AccessDeniedException exception);
```

Nó thường biểu diễn **403** khi caller đã được xác thực nhưng không đủ authority. `HttpStatusServerAccessDeniedHandler` có thể đặt mã status; nếu cần JSON/HTML body, có thể viết handler tùy chỉnh.

**Không đưa thông báo exception gốc** vào JSON phản hồi. Chi tiết nội bộ, tên bean, chính sách role, database query hoặc token metadata có thể lộ. Trả mã lỗi, status và thông điệp an toàn; phần debug nằm trong logs bảo vệ.

### 4.3 ExceptionTranslationWebFilter

Spring Security reactive có `ExceptionTranslationWebFilter`, kết nối các lỗi access denied của security với entry point hoặc denied handler. Nó đánh giá trạng thái authentication và dùng trust resolver khi quyết định nhánh. Một `AnonymousAuthenticationToken` có thể có raw `isAuthenticated()==true`, nhưng **không được coi là user đã đăng nhập thật** khi xử lý quyền.

### 4.4 Lỗi login và lỗi controller là các nhánh khác

| Lỗi xảy ra ở đâu? | Thành phần thường điều phối | Điều cần tùy chỉnh nếu muốn JSON/HTML nhất quán |
|---|---|---|
| Request protected thiếu login | `ExceptionTranslationWebFilter` → `ServerAuthenticationEntryPoint` | `exceptionHandling().authenticationEntryPoint(...)` |
| User đã login nhưng thiếu quyền | `ExceptionTranslationWebFilter` → `ServerAccessDeniedHandler` | `exceptionHandling().accessDeniedHandler(...)` |
| HTTP Basic có credential sai | Authentication WebFilter cho Basic | Cấu hình `httpBasic(...authenticationEntryPoint(...))`/failure handler tương thích |
| Form login POST sai mật khẩu | Authentication WebFilter cho form login | `formLogin(...authenticationFailureHandler(...))` |
| Form login POST thành công | Success handler của form login | `formLogin(...authenticationSuccessHandler(...))` |
| Controller ném `ResponseStatusException` | Cơ chế xử lý lỗi WebFlux | `@ControllerAdvice`/WebExceptionHandler/error handling của ứng dụng |
| CSRF token thiếu/sai | Security CSRF filter | Kiểm đường xử lý CSRF/denied và phản hồi thực tế |
| CORS preflight không được phép | CORS/security configuration | CORS policy, không biến thành login redirect |

Đây là lý do một `@RestControllerAdvice` **không đủ** để thay đổi tất cả phản hồi 401/403 của Spring Security: nhiều lỗi xảy ra trong WebFilter **trước** khi controller chạy.

## 5. Hai chiến lược cấu hình

### 5.1 Một SecurityWebFilterChain với entry point chọn response

Một cách là dùng cùng chain và kiểm route + Accept trong entry point. Phù hợp nếu ứng dụng có một tập chính sách authentication chung, và logic response khác nhau được gom đúng một nơi. Nhưng phải nhớ luồng Basic, form-login failure, OAuth2 login và CSRF có handler riêng, cần kiểm thử.

### 5.2 Nhiều SecurityWebFilterChain: API trước, web sau

Nếu API và web khác authentication scheme lẫn chính sách response, cách rõ ràng hơn là hai chain:

```text
@Order(0) API chain:
    securityMatcher("/api/**")
    HTTP Basic (demo)
    401/403 -> application/problem+json
    WWW-Authenticate: Basic ...

@Order(1) Web/fallback chain:
    match các request còn lại
    form login + cookie session
    /web/**: 302 login nếu navigation HTML, 401 JSON nếu không
    403: HTML hoặc problem+json
    /login: generated login page
    các URL khác: denyAll()
```

**Cảnh báo:** `ServerHttpSecurity.securityMatcher(...)` xác định **request đi vào chain nào**; `authorizeExchange().pathMatchers(...)` chỉ quyết định quyền **sau khi** chain đã được chọn. Chain API ở `@Order(0)` xử lý `/api/**` và chain thứ hai không nên ghi đè/chặn mất route API. Ngược lại, một URL không match chain nào có nguy cơ không qua security; cần fallback.

Ví dụ bên dưới sử dụng chiến lược thứ hai vì giúp phân tách hành vi API với browser và dễ viết kiểm thử. Các route đều minh họa **GET** để không biến demo content negotiation thành bài tắt CSRF. CSRF vẫn bật cho các thao tác không an toàn.

## 6. Hợp đồng lỗi JSON: Problem Details

Thay vì response tùy hứng theo HTML login page, API có thể thống nhất `application/problem+json`, gần với chuẩn RFC 9457. Một response lỗi 401:

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/problem+json;charset=UTF-8
Cache-Control: no-store
WWW-Authenticate: Basic realm="api"

{"type":"about:blank","title":"Unauthorized","status":401,"detail":"Authentication required"}
```

Một response lỗi 403:

```http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json;charset=UTF-8
Cache-Control: no-store

{"type":"about:blank","title":"Forbidden","status":403,"detail":"Access denied"}
```

Các trường `type`, `title`, `status`, `detail` mô tả lỗi. Với `type: about:blank`, `title` thông thường tương ứng reason phrase của HTTP status, như `Unauthorized` hoặc `Forbidden`. Không đưa username bị từ chối, quyền chính xác đang thiếu, mật khẩu, token, exception stack trace hay tên bảng dữ liệu vào response.

**Lưu ý HTTP Basic:** client cần biết cách gửi credential nên ví dụ API trả challenge `Basic realm="api"`. Với OAuth2 resource server bearer token, phải dùng challenge `Bearer` phù hợp tiêu chuẩn (bao gồm chi tiết lỗi hợp lệ khi cần), thay vì sao chép header Basic. Với API dùng session cookie hoặc custom token, thiết kế challenge/response theo giao thức thực; không bịa scheme trong `WWW-Authenticate`.

### Status khác representation

Ngay cả khi response muốn JSON, HTTP status phải là **401/403 thực**, không trả mọi lỗi `200 OK` với `{"success":false}` rồi làm hỏng semantics của client, caching và monitoring.

`Cache-Control: no-store` phù hợp để tránh cache response lỗi auth nhạy cảm. Những endpoint không bao giờ nên bị shared-cache tùy tiện. Với dữ liệu được phép cache, chính sách cache phải xét người dùng, session và authorization.

## 7. Demo Java 17+: API JSON và browser redirect

Demo dùng **Spring Boot 3.3.13** và Spring Security của BOM. Cung cấp hai user in-memory: `alice` có `ROLE_USER`, `admin` có `ROLE_ADMIN`. Web login có trang login mặc định do Spring Security tạo; API dùng HTTP Basic. Password chỉ dùng để thử trên localhost; trong production phải có TLS và nguồn danh tính được quản lý.

### 7.1 Cấu trúc

```text
webflux-negotiated-errors/
  settings.gradle
  build.gradle
  src/main/java/demo/errors/ErrorsApplication.java
  src/main/java/demo/errors/SecurityConfiguration.java
  src/main/java/demo/errors/ApiController.java
  src/test/java/demo/errors/ErrorResponseTest.java
```

**settings.gradle**

```groovy
rootProject.name = 'webflux-negotiated-errors'
```

**build.gradle**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo.errors'
version = '1.0.0'

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
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Không thêm `spring-boot-starter-web`**: đó là Spring MVC/Servlet. Các ví dụ dùng `ServerHttpSecurity` và `SecurityWebFilterChain` của WebFlux.

### 7.2 Main application

**src/main/java/demo/errors/ErrorsApplication.java**

```java
package demo.errors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ErrorsApplication {

    public static void main(String[] args) {
        SpringApplication.run(ErrorsApplication.class, args);
    }
}
```

### 7.3 SecurityConfiguration.java

File dưới đây là phần quan trọng nhất: hai chain, hai nhóm entry point và một hàm chọn representation cho request web.

```java
package demo.errors;

import java.nio.charset.StandardCharsets;
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authorization.ServerAccessDeniedHandler;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("dev-alice-only"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("dev-admin-only"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(alice, admin);
    }

    @Bean
    @Order(0)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        ServerAuthenticationEntryPoint apiEntry =
            (exchange, failure) -> writeError(
                exchange, HttpStatus.UNAUTHORIZED, false, true);

        ServerAccessDeniedHandler apiDenied =
            (exchange, denied) -> writeError(
                exchange, HttpStatus.FORBIDDEN, false, false);

        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .pathMatchers(HttpMethod.GET, "/api/me").authenticated()
                .anyExchange().denyAll())
            .httpBasic(basic -> basic.authenticationEntryPoint(apiEntry))
            .formLogin(form -> form.disable())
            .exceptionHandling(exceptions -> exceptions
                .authenticationEntryPoint(apiEntry)
                .accessDeniedHandler(apiDenied))
            .csrf(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain webChain(ServerHttpSecurity http) {
        ServerAuthenticationEntryPoint loginRedirect =
            new RedirectServerAuthenticationEntryPoint("/login");

        ServerAuthenticationEntryPoint webEntry = (exchange, error) -> {
            if (wantsHtmlNavigation(exchange)) {
                return loginRedirect.commence(exchange, error);
            }
            return writeError(
                exchange, HttpStatus.UNAUTHORIZED, false, false);
        };

        ServerAccessDeniedHandler webDenied = (exchange, error) ->
            writeError(exchange, HttpStatus.FORBIDDEN,
                wantsHtmlNavigation(exchange), false);

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/login", "/error").permitAll()
                .pathMatchers(HttpMethod.GET, "/web/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/web/admin")
                    .hasRole("ADMIN")
                .pathMatchers(HttpMethod.GET, "/web/me").authenticated()
                .anyExchange().denyAll())
            .formLogin(Customizer.withDefaults())
            .httpBasic(basic -> basic.disable())
            .exceptionHandling(exceptions -> exceptions
                .authenticationEntryPoint(webEntry)
                .accessDeniedHandler(webDenied))
            .csrf(Customizer.withDefaults())
            .build();
    }

    private static boolean wantsHtmlNavigation(
            ServerWebExchange exchange) {

        HttpMethod method = exchange.getRequest().getMethod();
        if (method != HttpMethod.GET && method != HttpMethod.HEAD) {
            return false;
        }

        List<MediaType> accepts =
            exchange.getRequest().getHeaders().getAccept();

        boolean explicitHtml = accepts.stream().anyMatch(type ->
            type.getQualityValue() > 0
                && "text".equalsIgnoreCase(type.getType())
                && "html".equalsIgnoreCase(type.getSubtype()));

        boolean explicitJson = accepts.stream().anyMatch(type -> {
            if (type.getQualityValue() <= 0) {
                return false;
            }
            String subtype = type.getSubtype().toLowerCase(
                java.util.Locale.ROOT);
            return "application".equalsIgnoreCase(type.getType())
                && ("json".equals(subtype)
                    || subtype.endsWith("+json"));
        });

        // JSON thắng khi client khai báo cả JSON và HTML.
        // Accept */* riêng lẻ không bật redirect.
        return explicitHtml && !explicitJson;
    }

    private static Mono<Void> writeError(
            ServerWebExchange exchange,
            HttpStatus status,
            boolean html,
            boolean basicChallenge) {

        ServerHttpResponse response = exchange.getResponse();
        response.setStatusCode(status);
        response.getHeaders().set(HttpHeaders.CACHE_CONTROL, "no-store");

        if (basicChallenge && status == HttpStatus.UNAUTHORIZED) {
            response.getHeaders().set(
                HttpHeaders.WWW_AUTHENTICATE,
                "Basic realm=\"api\"");
        }

        String body;
        if (html) {
            response.getHeaders().setContentType(
                new MediaType(MediaType.TEXT_HTML, StandardCharsets.UTF_8));
            body = "<!doctype html><html lang=\"vi\">"
                + "<meta charset=\"utf-8\">"
                + "<title>Forbidden</title><body>"
                + "<h1>403 Forbidden</h1>"
                + "<p>Ban khong co quyen truy cap.</p>"
                + "</body></html>";
        } else {
            response.getHeaders().setContentType(
                new MediaType(
                    MediaType.APPLICATION_PROBLEM_JSON,
                    StandardCharsets.UTF_8));

            body = (status == HttpStatus.UNAUTHORIZED)
                ? "{\"type\":\"about:blank\","
                    + "\"title\":\"Unauthorized\","
                    + "\"status\":401,"
                    + "\"detail\":\"Authentication required\"}"
                : "{\"type\":\"about:blank\","
                    + "\"title\":\"Forbidden\","
                    + "\"status\":403,"
                    + "\"detail\":\"Access denied\"}";
        }

        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        return response.writeWith(Mono.just(
            response.bufferFactory().wrap(bytes)));
    }
}
```

**Điểm cần đọc kỹ trong code:**

1. `@Order(0)` đưa API chain lên trước; `securityMatcher("/api/**")` chỉ nhận nhóm URL API. `@Order(1)` là catch-all chain cho các request còn lại, bao gồm `/login` và `/web/**`.
2. API chỉ bật HTTP Basic, **không bật form login**. Khi chưa/không xác thực, trả 401 với JSON và `WWW-Authenticate`, kể cả có `Accept: text/html`.
3. Web chỉ bật form login, **không bật Basic**. Request web navigation HTML chưa xác thực được redirect đến `/login`. Request web kiểu JSON nhận 401 JSON.
4. `httpBasic(basic -> basic.authenticationEntryPoint(apiEntry))` điều chỉnh cả nhánh authentication thất bại **bên trong filter Basic**, không chỉ unauthorized do `authorizeExchange`. Đây là điểm rất dễ bỏ sót nếu chỉ tùy chỉnh `exceptionHandling`.
5. `.exceptionHandling(...authenticationEntryPoint(...).accessDeniedHandler(...))` dùng lambda DSL của Spring Security 6, không dùng `.and()` cũ.
6. Khi role sai, nhánh `ServerAccessDeniedHandler` trả 403; web HTML nhận 403 HTML chứ **không** redirect về login.
7. `wantsHtmlNavigation` chỉ chọn redirect/HTML cho GET/HEAD có `Accept: text/html` **tường minh** và không yêu cầu JSON. `Accept: */*` hoặc JSON cho ra JSON. Đây là policy cụ thể của demo, không là heuristics mặc định của Spring Security.
8. HTML và JSON body là chuỗi cố định; code không đưa exception text/path/username từ client vào phản hồi, tránh injection và rò rỉ dữ liệu nội bộ.
9. `csrf(Customizer.withDefaults())` vẫn bật; demo chỉ expose GET. Nếu thêm write endpoints dùng cookie/form, phải triển khai CSRF token đúng chuẩn, không tắt nó để sửa lỗi 403.
10. `MapReactiveUserDetailsService` là ví dụ in-memory; mật khẩu được BCrypt hash. Trong môi trường thật, dùng identity store/IdP phù hợp, TLS và chính sách quản lý session/token.
11. Không có bean `SecurityWebFilterChain` thứ ba vì chain `webChain` không có `securityMatcher`, tạo **fallback bảo vệ toàn bộ** ngoài API. URL chưa liệt kê bị `denyAll()`.

**Vì sao dùng `@Order` trên hai bean?** Với nhiều security chain, Spring Security chọn chain đầu tiên có matcher phù hợp. Nếu một catch-all chain chạy trước API chain, API có thể bị áp dụng nhầm form login/redirect.

**Vì sao có cả `httpBasic(...authenticationEntryPoint(...))` và `exceptionHandling(...authenticationEntryPoint(...))` trên API chain?** Nhánh HTTP Basic **credential sai** có thể do chính authentication filter xử lý; nhánh **không có credential** rồi bị authorization yêu cầu đăng nhập sẽ dùng exception handling. Đặt cùng policy ở cả hai nơi giúp tránh trường hợp một nhánh trả JSON còn nhánh kia rơi về response mặc định.

### 7.4 Controller: trang HTML và API JSON

**src/main/java/demo/errors/ApiController.java**

```java
package demo.errors;

import java.security.Principal;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    public record Identity(String username) {}

    @GetMapping(value = "/api/public",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Identity> apiPublic() {
        return Mono.just(new Identity("public"));
    }

    @GetMapping(value = "/api/me",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Identity> apiMe(Principal principal) {
        return Mono.just(new Identity(principal.getName()));
    }

    @GetMapping(value = "/api/admin",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Identity> apiAdmin(Principal principal) {
        return Mono.just(new Identity(principal.getName()));
    }

    @GetMapping(value = "/web/public",
                produces = MediaType.TEXT_HTML_VALUE)
    public Mono<String> webPublic() {
        return Mono.just("<html><body><h1>Public</h1></body></html>");
    }

    @GetMapping(value = "/web/me",
                produces = MediaType.TEXT_HTML_VALUE)
    public Mono<String> webMe() {
        return Mono.just("<html><body><h1>Member</h1></body></html>");
    }

    @GetMapping(value = "/web/admin",
                produces = MediaType.TEXT_HTML_VALUE)
    public Mono<String> webAdmin() {
        return Mono.just("<html><body><h1>Admin</h1></body></html>");
    }
}
```

**Chú ý** `produces = ...` chỉ mô tả content type của **response thành công do controller tạo**. Nó **không** tự quyết định response lỗi 401/403 từ Spring Security WebFilter. Vì vậy API chưa xác thực có thể nhận `application/problem+json` trước khi handler được chọn, ngay cả khi client gửi `Accept: text/html`; ngược lại, **request API đã đăng nhập** nhưng chỉ chấp nhận text/html có thể nhận 406 từ controller vì nó chỉ tạo JSON. Đó là hai tầng content negotiation khác nhau.

Trong web controller, HTML dùng chuỗi cố định. Nếu có đưa username hoặc dữ liệu người dùng vào HTML, cần dùng cơ chế HTML escaping/template an toàn; không nối trực tiếp dữ liệu tùy ý vào HTML response.

### 7.5 Chạy với Gradle và curl

Từ thư mục dự án (JDK 17+ và Gradle tương thích với Spring Boot 3.3):

```bash
gradle bootRun
```

Nếu dự án có wrapper đúng phiên bản, có thể dùng `./gradlew bootRun`; Windows dùng `gradlew.bat bootRun`.

Các phép thử với curl CLI:

```bash
# API public: JSON 200
curl -i -H "Accept: application/json" \
  http://localhost:8080/api/public

# API protected, ngay cả khi Accept là HTML: phải là JSON 401
curl -i -H "Accept: text/html" \
  http://localhost:8080/api/me

# API protected: curl hỏi password khi -u chỉ có username
# Nhập dev-alice-only tại prompt
curl -i -u alice -H "Accept: application/json" \
  http://localhost:8080/api/me

# API Admin bằng Alice: thiếu ROLE_ADMIN -> 403 JSON
curl -i -u alice -H "Accept: application/json" \
  http://localhost:8080/api/admin

# Trang web: browser-like Accept HTML -> 302 đến /login
curl -i -H "Accept: text/html" \
  http://localhost:8080/web/me

# Cùng URL web nhưng client muốn JSON -> 401 JSON
curl -i -H "Accept: application/json" \
  http://localhost:8080/web/me

# Accept */* không đủ để suy luận đây là navigation
curl -i -H "Accept: */*" \
  http://localhost:8080/web/me

# Trang login mặc định của Spring Security
curl -i -H "Accept: text/html" \
  http://localhost:8080/login
```

**Không dùng `curl -L` khi đang muốn xem redirect 302**, vì `-L` tự follow đến trang login và kết quả cuối có thể 200 HTML, làm che mất status phản hồi ban đầu.

Với PowerShell, có thể phải dùng `curl.exe` do `curl` là alias của lệnh khác. Không gõ password thật trong URL hoặc script log; mật khẩu demo chỉ dùng local. Trình duyệt muốn thật sự đăng nhập qua form sẽ gửi POST đến `/login` với CSRF token; đây là **luồng form-login riêng**, không phải POST của một API dùng Basic.

### 7.6 Ma trận kết quả

| Route và tình huống | Status | Content type / Location | Ý nghĩa |
|---|---|---|---|
| `GET /api/public` anonymous | 200 | `application/json` | API công khai |
| `GET /api/me` anonymous, `Accept: text/html` | 401 | `application/problem+json` + Basic challenge | API contract ưu tiên JSON |
| `GET /api/me` Basic alice hợp lệ | 200 | `application/json` | API authentication thành công |
| `GET /api/admin` Basic alice hợp lệ | 403 | `application/problem+json` | Authenticated nhưng không có ADMIN |
| `GET /api/admin` Basic admin hợp lệ | 200 | `application/json` | Đúng role |
| `GET /web/me` anonymous, `Accept: text/html` | 302 | `Location: /login` | Navigation browser |
| `GET /web/me` anonymous, `Accept: application/json` | 401 | `application/problem+json` | Web endpoint gọi qua AJAX |
| `GET /web/me` anonymous, `Accept: */*` | 401 | `application/problem+json` | Không tự suy diễn browser |
| `GET /web/admin` user thiếu role, `Accept: text/html` | 403 | `text/html` | Không redirect lại login |
| `GET /web/admin` user thiếu role, `Accept: application/json` | 403 | `application/problem+json` | JSON access denied |
| `GET /login` chưa login | 200 | HTML login page | Form login chain |
| `POST /login` sai password | Phụ thuộc form-login failure handler (mặc định chuyển về login?error) | HTML/redirect của form flow | Không phải nhánh 401 của `exceptionHandling` |

Bảng mô tả **dự kiến của cấu hình demo**; nếu có additional filter, OAuth2/SAML handler, reverse proxy hoặc exception handler khác, response thực tế có thể khác. Luôn kiểm thử chính dependency và chain được triển khai.

## 8. Kiểm thử tự động bằng WebTestClient

Test sử dụng application context WebFlux **mock** và áp dụng Spring Security Test. Với API, dùng HTTP Basic thật để kiểm tra cả nhánh credential hợp lệ/sai. Với web, `mockUser` giả lập một authenticated user để tập trung xác minh **representation khi access denied**; không phải kiểm thử toàn bộ bước login bằng cookie.

**src/test/java/demo/errors/ErrorResponseTest.java**

```java
package demo.errors;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class ErrorResponseTest {

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
    void apiMissingCredentialIsJsonEvenWithHtmlAccept() {
        client.get().uri("/api/me")
            .accept(MediaType.TEXT_HTML)
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON)
            .expectHeader().valueMatches(
                HttpHeaders.WWW_AUTHENTICATE, "Basic .*")
            .expectBody()
            .jsonPath("$.status").isEqualTo(401);
    }

    @Test
    void apiBadBasicPasswordIsJson() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("alice", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON)
            .expectBody()
            .jsonPath("$.status").isEqualTo(401);
    }

    @Test
    void apiSuccessfulBasicRequestIsJson() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("alice", "dev-alice-only"))
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.username").isEqualTo("alice");
    }

    @Test
    void apiInsufficientRoleIsJson403() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth("alice", "dev-alice-only"))
            .exchange()
            .expectStatus().isForbidden()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON)
            .expectBody()
            .jsonPath("$.status").isEqualTo(403);
    }

    @Test
    void webNavigationWithoutLoginRedirects() {
        client.get().uri("/web/me")
            .accept(MediaType.TEXT_HTML)
            .exchange()
            .expectStatus().isFound()
            .expectHeader().valueMatches(
                HttpHeaders.LOCATION, ".*/login");
    }

    @Test
    void webAjaxWithoutLoginGetsJson401() {
        client.get().uri("/web/me")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON)
            .expectBody()
            .jsonPath("$.status").isEqualTo(401);
    }

    @Test
    void webWildcardAcceptDefaultsToJson401() {
        client.get().uri("/web/me")
            .accept(MediaType.ALL)
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON);
    }

    @Test
    void webHtmlAndJsonAcceptChoosesJson() {
        client.get().uri("/web/me")
            .accept(MediaType.TEXT_HTML, MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON);
    }

    @Test
    void webAuthenticatedUserWithoutAdminGetsHtml403() {
        client.mutateWith(mockUser("alice").roles("USER"))
            .get().uri("/web/admin")
            .accept(MediaType.TEXT_HTML)
            .exchange()
            .expectStatus().isForbidden()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.TEXT_HTML);
    }

    @Test
    void webAuthenticatedUserWithoutAdminGetsJson403() {
        client.mutateWith(mockUser("alice").roles("USER"))
            .get().uri("/web/admin")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isForbidden()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON)
            .expectBody()
            .jsonPath("$.status").isEqualTo(403);
    }

    @Test
    void adminCanReadWebAndApi() {
        client.mutateWith(mockUser("admin").roles("ADMIN"))
            .get().uri("/web/admin")
            .accept(MediaType.TEXT_HTML)
            .exchange()
            .expectStatus().isOk();

        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth("admin", "dev-admin-only"))
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.username").isEqualTo("admin");
    }

    @Test
    void unlistedWebPathIsDenied() {
        client.mutateWith(mockUser("admin").roles("ADMIN"))
            .get().uri("/web/unknown")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

Các static import được xuống dòng ở vị trí giữa token tên package để code dễ nhìn; **Java cho phép whitespace giữa các token qualified name**. Khi sao chép, có thể format lại thành **một dòng** cho quen quy ước:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
```

Dùng đúng **hai lệnh import** ở trên (thay cho các dòng import dài trong file mẫu) để rõ ràng khi build. `mockUser` gắn SecurityContext cho request ở lớp test, không đại diện việc kiểm password/form login thật; đó là lý do test API dùng Basic credential thật.

Chạy:

```bash
gradle test
```

Dự án có **12 test methods**. Kỳ vọng chúng PASS khi Spring Boot/Spring Security, Java/Gradle và classpath đúng như ví dụ. Chúng kiểm tra logic phân nhánh và JSON/HTML status, **chưa kiểm thử quy trình form login POST/CSRF/session cookie đầu-cuối**. Phải test thêm bằng browser hoặc integration client khi triển khai login thực. Không coi bản mô tả này là bằng chứng đã chạy build: tài liệu không chạy `gradle test` thay người đọc.

**Đặc biệt quan trọng:** các test anonymous không dùng `mockUser`, nên thực sự đi vào nhánh thiếu danh tính. Test role denied dùng `mockUser` để ép request có `Authentication` nhưng không đủ role; nếu mọi case đều dùng mock admin, không thể chứng minh 401/403 được tách đúng.

## 9. Những hành vi **không** được điều khiển hoàn toàn bằng exceptionHandling

### 9.1 Form login sai mật khẩu

`POST /login` với username/password sai có thể do `ServerAuthenticationFailureHandler` xử lý, ví dụ redirect về `/login?error` theo cấu hình form mặc định. Không nên kỳ vọng `exceptionHandling().authenticationEntryPoint(...)` tự biến lỗi này thành 401 JSON; nếu frontend SPA gửi login request bằng JSON/XHR, cần thiết kế một cơ chế login phù hợp (form endpoint + failure/success handler tùy chỉnh hoặc token endpoint). Đừng mở endpoint token “tự phát” bỏ qua CSRF/password protection.

### 9.2 Basic auth sai credential

HTTP Basic có cơ chế xác thực trong `AuthenticationWebFilter`. Nếu nhập sai mật khẩu, chính filter có thể gọi entry point/failure handler riêng. Ví dụ đã cấu hình `httpBasic(basic -> basic.authenticationEntryPoint(apiEntry))` để thống nhất định dạng 401 JSON. Khi đổi sang bearer token, phải cấu hình `oauth2ResourceServer(...)` và entry point phù hợp chuẩn OAuth2, không tái sử dụng Basic challenge sai scheme.

### 9.3 CSRF và CORS

- **CSRF:** nếu request bị chặn trước authorization do thiếu token, response có thể là 403 trước khi custom accessDenied handler định dạng theo mong muốn. Trên form/cookie web, CSRF protection vẫn cần thiết. Test POST có/không có CSRF token một cách riêng biệt.
- **CORS:** browser có thể không cho JavaScript đọc response nếu preflight hoặc Origin/headers không được chấp nhận. Đừng giải quyết bằng cách chuyển mọi `OPTIONS` đến `/login` hoặc `permitAll("/**")`. Cấu hình CORS đúng cho origin, method và credential.
- **Form action và cookies:** redirect sang login khi request dạng fetch có thể bị client follow, trả HTML không đúng JSON schema, hoặc không gửi cookie do SameSite/CORS. Hãy để client API/SPA nhận 401 JSON và chủ động điều hướng UI.

### 9.4 OAuth2/OIDC redirect có giao thức riêng

OAuth2 Login/OIDC có redirect đến authorization endpoint của Identity Provider, mang `state`, `nonce` và callback. Không viết một entry point chung đưa mọi OAuth2 login request thẳng `/login` nếu điều đó làm hỏng authorization request resolution, saved request hoặc callback. Cấu hình theo flow chính thức và test đủ cả success/failure.

### 9.5 Controller errors không phải authentication errors

Nếu controller ném lỗi validation 400 hoặc business 409, đừng dùng `ServerAuthenticationEntryPoint` để đổi chúng thành 401. Dùng `@ControllerAdvice`, WebFlux error handler hoặc `ErrorWebExceptionHandler` của ứng dụng theo loại exception phù hợp. Spring Security security exceptions phát sinh trong filter chain có thể không đi qua controller advice.

## 10. Nguy cơ khi redirect và content negotiation

### 10.1 Open redirect và query parameter

Không tạo redirect target bằng dữ liệu client chưa được kiểm chứng:

```java
// SAI về bảo mật: next do client gửi có thể trỏ tới domain lạ.
String next = exchange.getRequest().getQueryParams()
    .getFirst("next");
// response.getHeaders().setLocation(URI.create(next)); // đừng làm
```

Đây là mảnh code **cố ý không an toàn**, không dùng trong production. Redirect cố định đến `/login` ở demo tránh open redirect. Nếu phải hỗ trợ `returnUrl`, chỉ cho phép relative path nội bộ đã kiểm chuẩn hóa, loại protocol-relative `//evil.example`, validate host/scheme khi cần và xem chính sách saved request của Spring Security.

### 10.2 URL và header không định danh user

- `Accept` không phải credential; bất kỳ client nào cũng có thể gửi `text/html` hoặc `application/json`.
- `User-Agent`, `X-Requested-With`, `Referer` có thể bị giả mạo/thiếu.
- `Content-Type: application/json` không chứng minh caller là API client.
- `X-User-Id` hoặc claim chưa được xác thực không phải principal.
- `/api/admin` không được phép chỉ vì tên route có chữ admin; Security chain phải kiểm `ROLE_ADMIN`.

Chỉ dùng các yếu tố trên để chọn **response representation**/CORS policy khi thích hợp, không để chúng cấp quyền.

### 10.3 Tránh phản hồi lỗi khác biệt quá chi tiết

Một API không nên trả cho người chưa xác thực kiểu:

```json
{"error":"user alice exists but password is invalid"}
```

vì dễ hỗ trợ user enumeration. Trả thông điệp không tiết lộ thông tin riêng. Logs nội bộ có thể ghi mã lỗi, request ID, route và trạng thái; không ghi raw `Authorization`, cookie session, token hoặc password.

### 10.4 Vấn đề cache và proxy

- Response 401/403 thường nên có `Cache-Control: no-store`, nhất là có dữ liệu liên quan authentication.
- Reverse proxy/CDN phải không cache nhầm một response user A để phục vụ user B.
- Nếu có redirect, kiểm tra `Location` ở môi trường có context path, TLS termination, host forwarding để tránh redirect HTTP hoặc host sai.
- Nếu chọn HTML cho browser, giữ `Content-Type` đúng và escape dữ liệu; JSON cần UTF-8 hợp lệ.
- Kiểm thử browser thật khi có cookie `SameSite`, `Secure`, CORS và CSRF; WebTestClient mock không mô phỏng tất cả hành vi browser.

## 11. Kỹ thuật kiểm thử theo ma trận

| Trục | Test case quan trọng | Giá trị chứng minh |
|---|---|---|
| Loại route | `/api/**` và `/web/**` | Không dùng nhầm chain |
| Trạng thái auth | Missing, invalid, valid USER, valid ADMIN | Tách 401/403/200 |
| Accept | `text/html`, `application/json`, `*/*`, cả HTML + JSON | Quy tắc response deterministic |
| HTTP method | GET, POST, OPTIONS, HEAD | Navigation, CSRF, CORS không bị đoán sai |
| Xử lý login | GET /login, POST /login success/fail | Form handler không bị nhầm entry point |
| Nội dung | JSON schema, status, media type, Location | Client nhận đúng định dạng |
| Challenge | Basic `WWW-Authenticate`, bearer khi áp dụng | HTTP auth scheme đúng |
| Redirect | URL nội bộ; không dùng `next` không tin cậy | Không tạo open redirect |
| Cache | `Cache-Control: no-store` | Giảm nguy cơ cache phản hồi bảo mật |
| Nhiều chain | Match order, catch-all fallback | Không để URL lách khỏi security |
| Lỗi ngoài security | validation 400, business 409, handler 500 | Controller advice xử lý đúng phạm vi |
| CSRF/CORS | Same-origin/cross-origin, unsafe methods | Không cho redirect login giả vờ giải quyết CORS |

Trong kiểm thử thực tế, client HTTP tự follow redirect có thể che mất status 302; dùng WebTestClient hoặc curl không `-L` để xem response ban đầu. Một `401` đúng mã nhưng body HTML vẫn là lỗi contract của API; một JSON lỗi với status 200 cũng là lỗi.

## 12. Bài tập thực hành

1. Chạy project, gọi `GET /web/me` với `Accept: text/html`; giải thích vì sao có 302 và `Location: /login`.
2. Gọi **cùng URL** với `Accept: application/json` hoặc `Accept: */*`. Vì sao status trở thành 401 JSON chứ không là login redirect?
3. Gọi `GET /api/me` với `Accept: text/html`. Vì sao policy API vẫn chọn `application/problem+json`?
4. Đổi rule `/web/admin` cho `ROLE_USER`; viết test xác định Alice được vào nhưng role khác không được. Đảm bảo test không dùng header giả như `X-Role`.
5. Xóa `basic.authenticationEntryPoint(apiEntry)` rồi thử API Basic credential sai. So sánh body/status với nhánh không có credential để hiểu các failure handler khác nhau. Sau bài tập, khôi phục chính sách thống nhất.
6. Thử truy cập `/web/admin` bằng mock user thiếu ADMIN, một lần Accept HTML, một lần Accept JSON. Cả hai phải 403, không bị “bắt login lại”.
7. Đặt `Accept: text/html, application/json` và giải thích vì sao demo cố ý ưu tiên JSON; sau đó thay chính sách để xét trọng số `q` có kiểm thử.
8. Mở rộng ứng dụng với `POST /web/profile`; viết test CSRF token thiếu/hợp lệ và phân biệt phản hồi 403 do CSRF với 403 do thiếu role.
9. Thay Basic API bằng resource-server JWT, giữ contract lỗi JSON và thêm challenge Bearer đúng. Test token vắng, sai chữ ký, hết hạn và thiếu scope.
10. Thử một URL `/unexpected` nằm ngoài `/api/**`, xác minh fallback chain deny; không thêm chain catch-all cho phép mọi URL.
11. Viết `@ControllerAdvice` cho validation 400 và chứng minh nó không thay đổi 401/403 được tạo trước controller.
12. Thiết kế login redirect an toàn cho đường dẫn đã yêu cầu, không tin `next=https://...` và kiểm tránh protocol-relative redirect.
13. Kiểm tra trên browser thật rằng khi fetch nhận 401 JSON, frontend hiển thị lời nhắc login có chủ đích thay vì parse nhầm HTML.

## Tóm tắt

- Chọn response lỗi bằng **hai trục**: route contract (`/api/**` hay web page) và nội dung được yêu cầu qua `Accept`. Không dùng Accept/User-Agent để **cấp quyền**.
- `ServerAuthenticationEntryPoint` quyết định bước bắt đầu login khi authentication cần thiết. `ServerAccessDeniedHandler` điều khiển phản hồi khi đã xác thực nhưng bị deny. Form-login failure, HTTP Basic failure, CSRF, CORS và controller exception có thể đi qua **handler khác**, phải kiểm thử từng nhánh.
- Browser **GET/HEAD** yêu cầu HTML tường minh có thể nhận **302 /login**; API và web AJAX nên nhận **401 application/problem+json**. Người dùng đủ authentication nhưng thiếu role nhận **403**, không redirect login.
- Khi dùng Basic/Bearer, HTTP 401 cần scheme-specific `WWW-Authenticate` phù hợp. Không dùng header Basic cho OAuth2 token API.
- Trong WebFlux, dùng `ServerHttpSecurity.exceptionHandling(...)`, `SecurityWebFilterChain` và reactive handlers trả `Mono<Void>`; không nhầm API Servlet `HttpSecurity`/`AuthenticationEntryPoint`.
- Kiểm thử đủ các trục **route × Accept × authentication × HTTP method**, giữ CSRF/CORS và có fallback chain rõ ràng.

## Tài liệu chính thức

- Spring Security — WebFlux Security Configuration: https://docs.spring.io/spring-security/reference/6.3/reactive/configuration/webflux.html
- Spring Security 6.3 — `ServerHttpSecurity.ExceptionHandlingSpec`: https://docs.spring.io/spring-security/site/docs/6.3.3/api/org/springframework/security/config/web/server/ServerHttpSecurity.ExceptionHandlingSpec.html
- Spring Security 6.3 — `ServerHttpSecurity.HttpBasicSpec`: https://docs.spring.io/spring-security/site/docs/6.3.0-M3/api/org/springframework/security/config/web/server/ServerHttpSecurity.HttpBasicSpec.html
- Spring Security — `RedirectServerAuthenticationEntryPoint`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/RedirectServerAuthenticationEntryPoint.html
- Spring Security — `ServerAccessDeniedHandler`, `HttpStatusServerAccessDeniedHandler`: https://docs.spring.io/spring-security/site/docs/6.3.6/api/org/springframework/security/web/server/authorization/HttpStatusServerAccessDeniedHandler.html
- Spring Security — Reactive OAuth2 Login Advanced, tùy chỉnh login redirect: https://docs.spring.io/spring-security/reference/6.3/reactive/oauth2/login/advanced.html
- Spring Security — Reactive testing WebTestClient: https://docs.spring.io/spring-security/reference/6.3/reactive/test/index.html
- Spring Framework — WebFlux method arguments, Accept/response handling: https://docs.spring.io/spring-framework/reference/6.1/web/webflux/controller/ann-methods/arguments.html
- RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457
- RFC 9110 — HTTP Semantics, Accept và WWW-Authenticate: https://www.rfc-editor.org/rfc/rfc9110
