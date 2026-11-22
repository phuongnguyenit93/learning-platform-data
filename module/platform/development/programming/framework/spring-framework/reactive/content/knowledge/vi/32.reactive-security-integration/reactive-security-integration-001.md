# `SecurityWebFilterChain` và các điểm tích hợp Spring Security trong Spring WebFlux

## 1. Mục tiêu và phạm vi

Spring WebFlux vận hành trên mô hình reactive, còn Spring Security cung cấp xác thực (authentication), phân quyền (authorization), phòng vệ CSRF, bảo vệ HTTP headers, xử lý lỗi truy cập và tích hợp OAuth2. Trong WebFlux, phần bảo mật HTTP chạy qua `WebFilter` và được cấu hình chủ yếu bằng `ServerHttpSecurity` tạo ra một hoặc nhiều bean `SecurityWebFilterChain`.

Bài học tập trung vào cách đưa Spring Security vào một ứng dụng Spring WebFlux mà **không nhầm với Spring MVC/Servlet**.

Sau bài này, bạn có thể:

1. Giải thích request đi qua chuỗi `WebFilter` bảo mật trước khi tới controller hoặc functional handler.
2. Tạo `SecurityWebFilterChain` với `ServerHttpSecurity`, quy tắc URL và các cơ chế xác thực.
3. Phân biệt `securityMatcher(...)` chọn **chuỗi filter** và `authorizeExchange(...)` đặt **quy tắc truy cập trong chuỗi đó**.
4. Dùng nhiều security chains có `@Order` và một chain dự phòng để không bỏ sót endpoint.
5. Biết nơi tích hợp `ReactiveAuthenticationManager`, `AuthenticationWebFilter`, `ServerSecurityContextRepository`, `SecurityWebFiltersOrder` và custom `WebFilter`.
6. Lấy người dùng hiện tại từ Reactor Context bằng `ReactiveSecurityContextHolder`.
7. Kết hợp HTTP authorization với `@EnableReactiveMethodSecurity` và `@PreAuthorize`.
8. Hiểu sự khác biệt giữa 401 và 403, CSRF, CORS, sessions, HTTP Basic và JWT Resource Server.
9. Viết và kiểm thử ứng dụng Java 17+ Spring Boot bằng `WebTestClient` và Spring Security Test.
10. Tránh các lỗi bảo mật thường gặp như mở nhầm endpoint, tắt CSRF tùy tiện hoặc dùng `ThreadLocal` để lưu identity.

Ví dụ có thể chạy được được xây dựng cho **Java 17, Spring Boot 3.3.5, Spring WebFlux và Spring Security 6.3.x**. Những đoạn code thuộc dự án mẫu sẽ được trình bày theo đúng tên file; các đoạn code riêng trong phần giải thích chỉ minh họa API và có thể cần thêm imports/beans khi dùng độc lập.

## 2. WebFlux Security khác Spring MVC Security

Spring Security có hai cách tích hợp web chính:

| Nội dung | Spring MVC / Servlet | Spring WebFlux / Reactive |
|---|---|---|
| Entry point HTTP | Servlet `Filter` | Spring `WebFilter` |
| Chuỗi bảo mật | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Cấu hình | `HttpSecurity` | `ServerHttpSecurity` |
| Match request | `RequestMatcher` | `ServerWebExchangeMatcher` |
| Authentication manager | `AuthenticationManager` | `ReactiveAuthenticationManager` |
| Authentication filter | Servlet authentication filters | `AuthenticationWebFilter` |
| Context propagation | Thường dựa vào `SecurityContextHolder`/ThreadLocal | Reactor Context qua `ReactiveSecurityContextHolder` |
| HTTP request abstraction | `HttpServletRequest` | `ServerWebExchange` |
| Method security | `@EnableMethodSecurity` | `@EnableReactiveMethodSecurity` |
| HTTP testing | `MockMvc` | `WebTestClient` |

Không thay thế tên class bằng cách đổi tiền tố một cách máy móc. Một ứng dụng dùng `spring-boot-starter-webflux` cần cấu hình security cho reactive stack.

Ví dụ sau **không** phải cấu hình WebFlux:

```java
SecurityFilterChain servletChain(HttpSecurity http) {
    // Servlet stack; không dùng cho WebFlux Security.
    return http.build();
}
```

Cấu hình WebFlux tương ứng dùng:

```java
@Bean
SecurityWebFilterChain reactiveChain(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchange -> exchange
                    .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

`Customizer` đến từ `org.springframework.security.config.Customizer`. Class `SecurityWebFilterChain` đến từ `org.springframework.security.web.server`.

Một ứng dụng có thể chứa cả dependency Servlet và Reactive do dependency tree. Hãy xác định ứng dụng thật sự đang chạy trên web application type nào trước khi áp dụng hướng dẫn bảo mật.

## 3. Một request đi qua bảo mật ở đâu?

WebFlux có `WebHttpHandlerBuilder`, `WebHandler`, `WebFilter` và `WebExceptionHandler`. Spring Security tham gia bằng một `WebFilterChainProxy` mang một tập các `SecurityWebFilterChain`.

Luồng tổng quát:

```text
HTTP request
    |
    v
HTTP server / Reactor Netty
    |
    v
WebFlux HttpHandler
    |
    v
WebFilterChainProxy của Spring Security
    |
    +-- Chọn SecurityWebFilterChain khớp request
    |
    +-- CORS/CSRF/HTTP headers (theo cấu hình)
    |
    +-- Load SecurityContext
    |
    +-- Authentication (Basic, Bearer, form login, ...)
    |
    +-- Exception translation
    |
    +-- Authorization
    |
    v
WebFlux HandlerMapping / HandlerAdapter
    |
    v
@RestController hoặc RouterFunction
    |
    v
Service với reactive method security
    |
    v
Mono/Flux response
```

Thứ tự filter cụ thể do cấu hình và `SecurityWebFiltersOrder` quyết định; sơ đồ là cách nhìn chức năng chứ không phải cam kết toàn bộ filters có mặt trong mọi chain.

### Ba lớp bảo vệ cần phân biệt

- **Authentication**: request này gắn với danh tính nào, credential có được chấp nhận không?
- **Authorization tại HTTP boundary**: danh tính đó có được gọi URL + method này không?
- **Authorization tại service/domain**: danh tính đó có được phép tác động vào đối tượng nghiệp vụ cụ thể không?

`SecurityWebFilterChain` giúp thực hiện hai bước đầu; reactive method security và domain service giữ vai trò phòng vệ sâu hơn. URL rule không thể thay thế hoàn toàn quy tắc ownership như “người dùng chỉ được đọc tài liệu của mình”.

## 4. `SecurityWebFilterChain` và `ServerHttpSecurity`

`SecurityWebFilterChain` xác định matcher để xem chuỗi có áp dụng cho request không, đồng thời chứa các `WebFilter` được cấu hình cho chuỗi.

`ServerHttpSecurity` là DSL/builder của Spring Security dùng cho WebFlux. Gọi `.build()` để tạo `SecurityWebFilterChain`.

Ví dụ cấu hình tối thiểu:

```java
@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchange -> exchange
                        .pathMatchers("/public/**").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

Đọc từ trên xuống:

1. `/public/**` có thể truy cập không cần đăng nhập.
2. Mọi request còn lại cần Authentication đã được xác thực.
3. Bật HTTP Basic làm một phương thức xác thực.
4. `.build()` tạo chuỗi `WebFilter` có thể được WebFlux sử dụng.

### 4.1. Thứ tự rule trong `authorizeExchange`

Các matcher/rule được áp dụng theo thứ tự khai báo. Rule cụ thể nên đứng trước `anyExchange()`.

```java
.authorizeExchange(exchange -> exchange
        .pathMatchers(HttpMethod.GET, "/api/catalog").permitAll()
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .pathMatchers("/api/**").authenticated()
        .anyExchange().denyAll())
```

Nếu đặt `anyExchange().permitAll()` quá sớm, các rule phía sau không còn giúp bảo vệ endpoint như dự kiến. Viết quy tắc từ cụ thể tới tổng quát.

### 4.2. `permitAll`, `authenticated`, `hasRole` và `hasAuthority`

| Rule | Ý nghĩa |
|---|---|
| `permitAll()` | Cho phép truy cập không phụ thuộc identity |
| `authenticated()` | Yêu cầu user/request đã được xác thực |
| `hasRole("ADMIN")` | Kiểm tra quyền `ROLE_ADMIN` theo quy ước role prefix |
| `hasAuthority("invoice:write")` | Kiểm tra chính xác authority `invoice:write` |
| `denyAll()` | Từ chối tất cả |

`hasRole("ADMIN")` không tìm authority `"ADMIN"` trực tiếp; theo mặc định Spring Security kiểm tra `"ROLE_ADMIN"`. Khi Resource Server map OAuth2 scopes thành `SCOPE_read`, thường dùng `hasAuthority("SCOPE_read")` chứ không dùng `hasRole("read")`.

### 4.3. Không đồng nhất `permitAll` với bỏ qua filter

`permitAll()` là quyết định phân quyền. Request vẫn đi qua security chain đã chọn, bao gồm những filter phù hợp như security headers, CORS hoặc CSRF.

Ví dụ một POST `permitAll` vẫn có thể bị CSRF từ chối nếu CSRF được bật và request thuộc nhóm cần CSRF token. “Cho phép truy cập” không có nghĩa tắt toàn bộ bảo vệ cho request.

## 5. `securityMatcher` chọn chain; `authorizeExchange` đặt quyền

Đây là điểm dễ nhầm nhất khi có nhiều chuỗi.

### 5.1. `securityMatcher(...)`

Định nghĩa **toàn bộ chuỗi SecurityWebFilterChain có tham gia xử lý request hay không**.

```java
http.securityMatcher(
        new PathPatternParserServerWebExchangeMatcher("/api/**"));
```

Nếu request không khớp `/api/**`, cả chuỗi filter này không áp dụng.

### 5.2. `pathMatchers(...)` bên trong `authorizeExchange`

Định nghĩa **chính sách authorization khi chuỗi đã được chọn**.

```java
http.authorizeExchange(exchange -> exchange
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .pathMatchers("/api/**").authenticated());
```

Nếu request không khớp một rule cụ thể, logic tiếp tục xét các rule còn lại của chain đó. Vì vậy nên kết thúc bằng `anyExchange().authenticated()` hoặc `denyAll()`.

### 5.3. Sự khác biệt bằng ví dụ

```text
GET /api/admin/report
    |
    v
securityMatcher("/api/**") -> MATCH
    |
    v
authorizeExchange("/api/admin/**") -> ROLE_ADMIN
    |
    +-- không đủ role -> 403
    +-- đủ role -> controller

GET /health
    |
    v
securityMatcher("/api/**") -> NOT MATCH
    |
    v
Xét chain có thứ tự thấp hơn (fallback)
```

**Cảnh báo nghiêm trọng:** nếu không có `SecurityWebFilterChain` nào match request, request đó không được bảo vệ bởi Spring Security web chain. Đừng tạo duy nhất chain `/api/**` rồi nghĩ các path khác mặc định bị chặn.

## 6. Nhiều chuỗi với `@Order` và một fallback an toàn

Một ứng dụng có thể yêu cầu cơ chế bảo mật khác nhau cho:

- `/api/**`: Bearer JWT.
- `/console/**`: Form Login + CSRF/session.
- `/health`: endpoint công khai theo chính sách.
- Phần còn lại: từ chối.

Spring Security xét các `SecurityWebFilterChain` theo thứ tự. **Chuỗi khớp đầu tiên được chọn**, không phải chạy cộng dồn mọi chuỗi.

Ví dụ:

```java
@Bean
@Order(1)
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
            .securityMatcher(
                    new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(exchange -> exchange
                    .pathMatchers("/api/public").permitAll()
                    .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}

@Bean
@Order(2)
SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchange -> exchange
                    .pathMatchers("/health").permitAll()
                    .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

Chain thứ hai không khai báo `securityMatcher`, nên dùng matcher mặc định áp dụng cho tất cả request chưa được chain ưu tiên cao chọn.

### 6.1. Checklist khi dùng nhiều chains

- Đặt chain cụ thể trước chain tổng quát.
- Dùng `@Order` thay vì trông chờ thứ tự đăng ký bean.
- Chain fallback phải thực sự match các URL còn lại.
- Kiểm thử cả URL thuộc API, URL công khai, URL không nằm trong bất kỳ path dự kiến.
- Không mặc định cấu hình authentication của chain A tự động áp dụng cho chain B.
- Không để rule `/actuator/**` hoặc `/admin/**` không được bảo vệ do matcher thiếu.
- Nếu có WebSocket handshake, test path handshake có đi qua chain thích hợp không.

### 6.2. Một chain có thể dùng nhiều phương thức authentication

Không phải mọi hệ thống đều cần nhiều chains. Nếu nhiều cơ chế được phép dùng cho cùng một tập endpoint, có thể cấu hình các spec phù hợp trong một chain. Tuy nhiên, nếu cần CSRF/session/cookie cho browser và Bearer-only stateless cho API, việc tách chain thường dễ review hơn.

## 7. Authentication được tích hợp tại đâu?

Authentication là bước kiểm tra credential và tạo `Authentication` chứa principal cùng authorities.

Các component reactive quan trọng:

| Thành phần | Vai trò |
|---|---|
| `AuthenticationWebFilter` | Nhận request, trích credential, gọi authentication manager |
| `ServerAuthenticationConverter` | Chuyển `ServerWebExchange` thành authentication token |
| `ReactiveAuthenticationManager` | Xác minh token và trả `Mono<Authentication>` |
| `ReactiveUserDetailsService` | Truy xuất người dùng theo username bằng API reactive |
| `PasswordEncoder` | Hash/verify password |
| `ServerSecurityContextRepository` | Load/save `SecurityContext` theo chiến lược |
| `ReactiveSecurityContextHolder` | Truy cập `SecurityContext` trong Reactor Context |
| `ServerAuthenticationEntryPoint` | Xử lý khi cần xác thực, thường tạo 401 |
| `ServerAccessDeniedHandler` | Xử lý khi đã được xác thực nhưng bị từ chối quyền, thường 403 |

### 7.1. HTTP Basic

Một chain có thể bật Basic:

```java
.httpBasic(Customizer.withDefaults())
```

Với username/password, Spring dùng cơ chế authentication phù hợp, ví dụ `ReactiveUserDetailsService` và password encoder.

Ví dụ đăng ký user in-memory (chỉ cho demo/test):

```java
@Bean
PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder();
}

@Bean
MapReactiveUserDetailsService demoUsers(PasswordEncoder encoder) {
    UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("read-pass"))
            .roles("READER")
            .build();

    return new MapReactiveUserDetailsService(reader);
}
```

Với production, dùng identity provider/directory hoặc repository reactive tương ứng. Không hardcode credential, không dùng `{noop}` cho password production, và không log header `Authorization`.

### 7.2. `AuthenticationWebFilter`: nơi mở rộng authentication

Nếu cần cơ chế credential riêng (ví dụ token truyền trong header có contract đặc biệt), một `AuthenticationWebFilter` có thể dùng:

1. `setRequiresAuthenticationMatcher(...)` để giới hạn request.
2. `setServerAuthenticationConverter(...)` để parse credential.
3. `ReactiveAuthenticationManager` để validate.
4. Success/failure handlers và context repository phù hợp.

Trong trường hợp chuẩn, ưu tiên các module Spring Security đã có: HTTP Basic, OAuth2 Login, Resource Server Bearer token. Không tự viết filter parse JWT mà bỏ qua verify signature/issuer/audience/expiry.

### 7.3. `ReactiveAuthenticationManager` phải reactive đúng nghĩa

Manager trả `Mono<Authentication>`. Tránh gọi JPA/JDBC blocking hoặc HTTP synchronous trực tiếp trên Netty event loop trong authentication pipeline. Nếu identity store chỉ hỗ trợ blocking I/O, ưu tiên lựa chọn reactive hoặc cô lập blocking work theo scheduler phù hợp và có giới hạn.

Không đưa credential người dùng vào một global singleton field để các request khác vô tình dùng chung.

## 8. `SecurityContext` trong Reactor Context, không phải ThreadLocal

Trong Servlet, nhiều ví dụ dùng:

```java
SecurityContextHolder.getContext().getAuthentication();
```

Trong WebFlux reactive, execution có thể nhảy qua nhiều thread do scheduling và bất đồng bộ. ThreadLocal không phải nơi đáng tin để chuyển authentication giữa các reactive operators.

Spring Security đặt `SecurityContext` trong **Reactor Context** của publisher. Dùng:

```java
Mono<String> currentUsername =
        ReactiveSecurityContextHolder.getContext()
                .map(context -> context.getAuthentication().getName());
```

Với controller:

```java
@GetMapping("/api/me")
public Mono<String> me() {
    return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName());
}
```

Khi request được xác thực, context đi theo subscription. Nếu code tự tạo thread/task rồi gọi `subscribe()` tách rời, không thể giả định context và cancellation tự lan tới task đó.

### 8.1. Sử dụng identity khi có async boundary

Ví dụ:

```java
public Mono<Profile> profile() {
    return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication().getName())
            .flatMap(profileRepository::findByUsername);
}
```

Publisher trả về từ service vẫn thuộc pipeline request. Nếu `profileRepository` là reactive repository, không cần block.

### 8.2. Khi nào dùng `contextWrite(...)`?

Spring Security tạo context khi xác thực request; phần lớn controller/service **không cần tự gắn authentication**. `contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))` có giá trị trong code infrastructure/test hoặc boundary đặc biệt đã được thiết kế, không phải cách cho user tự nhận quyền.

Không nhận một username từ header rồi tự tạo `Authentication` được xác thực để vượt qua Spring Security.

## 9. Authorization ở HTTP và service

HTTP authorization bảo vệ bề mặt API. Method security bảo vệ thao tác nghiệp vụ sau khi request đã qua security chain.

### 9.1. Bật reactive method security

```java
@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
class SecurityConfig {
}
```

Service:

```java
@Service
public class BillingService {

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> readFinanceSummary() {
        return Mono.just("finance-summary");
    }
}
```

`@PreAuthorize` chặn method dựa trên authentication/authorities trong reactive context. Method phải được gọi qua Spring bean proxy; một self-invocation trong cùng instance có thể bỏ qua advice.

### 9.2. Vì sao vẫn cần URL rules?

Không phải mọi request đều vào một method có annotation; controller, functional route, static resources và fallback đều cần chính sách mặc định.

Ví dụ defense in depth:

```java
.authorizeExchange(exchange -> exchange
        .pathMatchers("/api/reports/**").authenticated()
        .anyExchange().denyAll())
```

Trong service:

```java
@PreAuthorize("hasRole('ADMIN')")
public Mono<Report> confidentialReport() {
    return repository.loadConfidentialReport();
}
```

URL cần đã đăng nhập; service yêu cầu ADMIN. Nếu sau này route hoặc caller thay đổi, method vẫn giữ một lớp kiểm tra.

### 9.3. Kiểm tra ownership của resource

Role chỉ đủ cho rule chung. Nếu cần “user A chỉ được xem hóa đơn của user A”, domain service phải kiểm tra quan hệ giữa principal và resource ID, không chỉ dựa vào `/api/invoices/{id}`.

Có thể dùng custom reactive authorization logic hoặc kiểm tra trong service sau khi load metadata. Tránh đưa các thông tin ownership nhạy cảm vào error message.

## 10. `SecurityWebFiltersOrder` và custom `WebFilter`

Spring Security định nghĩa các vị trí tương đối qua enum `SecurityWebFiltersOrder`, như `AUTHENTICATION`, `EXCEPTION_TRANSLATION`, `AUTHORIZATION`, `CSRF`, `HTTP_BASIC`, `REACTOR_CONTEXT` và các điểm khác.

Có thể thêm custom filter vào **một security chain** bằng:

```java
http.addFilterBefore(customFilter, SecurityWebFiltersOrder.AUTHORIZATION);
http.addFilterAfter(customFilter, SecurityWebFiltersOrder.AUTHENTICATION);
http.addFilterAt(customFilter, SecurityWebFiltersOrder.AUTHENTICATION);
```

Đoạn trên minh họa ba API lựa chọn vị trí; **không gọi cả ba** cho cùng filter nếu không có lý do, vì sẽ thêm filter nhiều lần.

### 10.1. Ví dụ filter ghi nhận thời gian xử lý

```java
WebFilter timingFilter = (exchange, chain) -> {
    long started = System.nanoTime();

    return chain.filter(exchange)
            .doFinally(signal -> {
                long millis = java.util.concurrent.TimeUnit.NANOSECONDS
                        .toMillis(System.nanoTime() - started);

                metrics.record("api.response", millis);
            });
};

http.addFilterAfter(timingFilter, SecurityWebFiltersOrder.AUTHORIZATION);
```

`metrics.record(...)` là API minh họa của một metrics adapter trong ứng dụng. Dùng Micrometer Observation/Tracing khi hệ thống đã có bộ quan sát chuẩn, thay vì tự tạo tags chứa URL đầy đủ hoặc thông tin cá nhân.

### 10.2. Dùng đúng vị trí khi cần authentication

- Filter đọc credential nên được tích hợp bằng authentication pipeline, không tùy tiện đặt sau Authorization.
- Filter cần đọc principal đã xác thực phải đặt ở vị trí phù hợp và đọc từ Reactor Context, không dùng ThreadLocal.
- Filter thay đổi request metadata phải tránh sửa `Authorization` hoặc bypass matcher.
- Filter custom nên có test chứng minh route nào sẽ chạy qua nó.

Một `@Component WebFilter` nằm ở global WebFlux filter chain có phạm vi khác với filter được thêm bằng `ServerHttpSecurity.addFilter...` trong một security chain. Hiểu rõ phạm vi trước khi chọn cách đăng ký.

## 11. Spring Security WebFlux và HTTP 401/403

Hai response quan trọng:

- **401 Unauthorized**: không có credential hợp lệ hoặc cần yêu cầu xác thực; với HTTP Basic thường kèm `WWW-Authenticate`.
- **403 Forbidden**: request đã được xác thực nhưng không có quyền phù hợp, hoặc bị một policy như CSRF từ chối.

Ví dụ:

| Request | Rule | Kết quả thường gặp |
|---|---|---|
| Không credential → `GET /api/me` | `authenticated()` | 401 |
| Basic sai password → `GET /api/me` | `authenticated()` | 401 |
| User ROLE_READER → `GET /api/admin` | `hasRole("ADMIN")` | 403 |
| User ROLE_ADMIN → `GET /api/admin` | `hasRole("ADMIN")` | 200 |
| User ROLE_EDITOR → POST có CSRF protection nhưng thiếu token | `hasRole("EDITOR")` | 403 |
| Request vào path không nằm trong chain nào | Không có filter chain khớp | Có nguy cơ không được Spring Security bảo vệ |

Spring Security sử dụng exception translation để gọi authentication entry point hoặc access denied handler tùy lỗi và trạng thái authentication.

### 11.1. Tùy biến entry point/denied handler

Có thể cấu hình:

```java
.exceptionHandling(spec -> spec
        .authenticationEntryPoint((exchange, error) -> {
            exchange.getResponse()
                    .setStatusCode(HttpStatus.UNAUTHORIZED);
            return exchange.getResponse().setComplete();
        })
        .accessDeniedHandler((exchange, error) -> {
            exchange.getResponse()
                    .setStatusCode(HttpStatus.FORBIDDEN);
            return exchange.getResponse().setComplete();
        }))
```

Các lambda ví dụ chỉ trả status, không body. Khi thay entry point của HTTP Basic, hãy cân nhắc giữ semantics `WWW-Authenticate` cho client tương thích. Nếu viết JSON `ProblemDetail`, dùng response writer reactive, đặt Content-Type và tránh tiết lộ nguyên nhân xác thực/secret.

Không trả `200 OK` kèm `"not authorized"` thay cho 401/403, vì client, gateway và observability cần status chính xác.

## 12. CSRF trong WebFlux: đừng tắt tùy tiện

CSRF xảy ra khi trình duyệt của nạn nhân tự gửi credential đã lưu (ví dụ session cookie hoặc Basic credentials) tới một website, còn attacker khiến browser gửi request thay đổi trạng thái.

Spring Security WebFlux bật CSRF protection theo mặc định. Request an toàn như GET/HEAD/OPTIONS/TRACE thường không yêu cầu CSRF token, còn POST/PUT/PATCH/DELETE thường cần token khi policy mặc định áp dụng.

Ví dụ một request:

```http
POST /api/items HTTP/1.1
Authorization: Basic ...
Content-Type: application/json
```

Dù authentication hợp lệ và user có ROLE_EDITOR, POST vẫn có thể bị trả **403** khi thiếu CSRF token.

### 12.1. CSRF có liên quan đến HTTP Basic không?

Có. Browser có thể tự đính kèm credential Basic đã lưu. Vì vậy, không đúng khi nói “API dùng Basic nên chắc chắn không cần CSRF”.

Một API chỉ nhận Bearer token gắn thủ công trong header `Authorization`, không sử dụng cookie hoặc ambient browser credentials, thường có threat model CSRF khác. Chỉ cân nhắc tắt CSRF **trong đúng chain stateless đó** sau khi xác minh mọi đường đi credential, CORS, frontend và logout/login flows.

### 12.2. Không nhầm CSRF với CORS

- **CORS** giới hạn website origin nào được phép truy cập response cross-origin trong browser.
- **CSRF** bảo vệ khỏi hành vi browser tự gửi request mang credential mà người dùng không chủ ý.

Bật CORS không tự thay thế CSRF. CORS cũng không phải authentication/authorization; curl hoặc server-to-server client không chịu cùng quy tắc CORS của browser.

### 12.3. Test CSRF bằng Spring Security Test

```java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;

client.mutateWith(csrf())
        .post()
        .uri("/api/items")
        .bodyValue(new ItemRequest("Notebook"))
        .exchange()
        .expectStatus().isOk();
```

Trong ứng dụng thực tế, browser/form cần cơ chế nhận và gửi CSRF token phù hợp với `ServerCsrfTokenRepository` đang dùng. Helper test không phải hướng dẫn client production tạo token tùy ý.

## 13. CORS và request từ trình duyệt

Một request từ `https://app.example.com` tới `https://api.example.com` có thể bị CORS preflight trước khi gửi request thật, nhất là khi dùng custom Authorization header.

Spring WebFlux cung cấp cấu hình CORS qua `CorsConfiguration` và `CorsWebFilter`/WebFlux mapping. Spring Security có `.cors(Customizer.withDefaults())` để phối hợp xử lý CORS khi đã cung cấp configuration source thích hợp.

Ví dụ mô tả cấu hình origin cụ thể:

```java
CorsConfiguration config = new CorsConfiguration();
config.setAllowedOrigins(List.of("https://app.example.com"));
config.setAllowedMethods(List.of("GET", "POST"));
config.setAllowedHeaders(List.of("Authorization", "Content-Type",
        "X-CSRF-TOKEN"));
config.setAllowCredentials(true);
```

Đoạn trên chỉ tạo đối tượng config; cần đăng ký nó qua `CorsConfigurationSource` hoặc WebFlux configuration để có hiệu lực.

Nếu `allowCredentials=true`, không dùng wildcard `*` cho `allowedOrigins` theo cách gây vi phạm policy. Chỉ cho phép origin thực sự tin cậy.

OPTIONS preflight không nên bị yêu cầu credential mà browser không gửi trong preflight. Hãy kiểm tra CORS được xử lý đủ sớm trong filter chain, đồng thời không mở rộng danh sách origins chỉ để vượt qua lỗi frontend.

## 14. Session, context repository và stateless API

`ServerSecurityContextRepository` cho phép Spring Security load/save `SecurityContext` qua một chiến lược lưu trữ.

Các implementation phổ biến:

- `WebSessionServerSecurityContextRepository`: lưu thông tin context trong WebSession khi cấu hình sử dụng session.
- `NoOpServerSecurityContextRepository`: không lưu context giữa các request.
- Repository tùy chỉnh: dùng cho một thiết kế cụ thể đã đánh giá threat model.

Đừng suy ra rằng `.httpBasic()` tự động biến toàn ứng dụng thành stateless theo mọi cấu hình. Một chain có thể dùng repository mặc định hoặc được tùy chỉnh; hãy kiểm tra policy thực tế.

Với API Bearer JWT, mỗi request có thể được xác thực độc lập bằng token. Nếu API không sử dụng session/cookie, `NoOpServerSecurityContextRepository` phù hợp với mục tiêu không lưu security context theo HTTP session.

Ví dụ API-only (độc lập với dự án Basic phía sau):

```java
SecurityWebFilterChain jwtChain(ServerHttpSecurity http) {
    return http
            .securityMatcher(
                    new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .securityContextRepository(
                    NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(exchange -> exchange
                    .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                    .jwt(Customizer.withDefaults()))
            .build();
}
```

Cần cấu hình `ReactiveJwtDecoder` hoặc issuer/JWK Set URI phù hợp; chỉ bật DSL trên không đủ để tin JWT đúng cách. Việc tắt CSRF nếu có phải là quyết định riêng, có điều kiện, sau khi kiểm tra mọi cookie/credential flow.

## 15. Tích hợp OAuth2 Resource Server JWT

Khi WebFlux API nhận token Bearer do authorization server phát hành, ưu tiên Spring Security OAuth2 Resource Server thay vì tự parse JWT:

Maven dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
```

Cấu hình issuer:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/issuer
```

Resource Server thường lấy metadata/JWK Set thông qua issuer discovery và kiểm tra chữ ký, issuer, exp, nbf theo khả năng decoder được cấu hình. Với ứng dụng production còn cần xác minh audience (`aud`) đúng với API, scope/authority mapping và key rotation strategy.

Ví dụ chain JWT:

```java
@Bean
SecurityWebFilterChain resourceServerChain(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchange -> exchange
                    .pathMatchers("/api/public").permitAll()
                    .pathMatchers("/api/admin/**")
                        .hasAuthority("SCOPE_catalog.admin")
                    .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                    .jwt(Customizer.withDefaults()))
            .build();
}
```

Đoạn trên là một lựa chọn cấu hình riêng thay cho chain HTTP Basic trong dự án mẫu. Không đăng ký cả hai bean catch-all không có `@Order` và matcher rõ ràng.

### JWT authentication không giống OAuth2 Client

- **Resource Server** xác thực Bearer token gửi tới ứng dụng.
- **OAuth2 Client** giúp ứng dụng đăng nhập qua Identity Provider hoặc lấy access token để gọi API khác.
- **Authorization Server** là bên cấp token.

Một ứng dụng có thể có nhiều vai trò, nhưng cấu hình cần rõ boundaries, trust và nguồn credential.

### JWT authorities và scopes

Spring Security có thể ánh xạ scope trong token thành authority `SCOPE_<scope>`. Ví dụ scope `"catalog.read"` trở thành `"SCOPE_catalog.read"` theo mapping mặc định. Nếu token dùng claim roles riêng, cần `ReactiveJwtAuthenticationConverter` hoặc converter khác được kiểm thử để tạo authorities phù hợp.

Không dùng `.hasRole("ADMIN")` rồi giả định JWT scope `admin` tự trở thành `ROLE_ADMIN`.

## 16. Điểm tích hợp khác trong Spring WebFlux

### 16.1. `@RestController` và functional routes

Vì security nằm ở `WebFilter` trước handler, cùng một `SecurityWebFilterChain` có thể bảo vệ cả annotated controller và `RouterFunction`.

Một functional route:

```java
RouterFunction<ServerResponse> routes(Handler handler) {
    return RouterFunctions.route()
            .GET("/api/items/{id}", handler::findById)
            .build();
}
```

Nếu path khớp chain `/api/**`, route vẫn chịu chính sách authentication/authorization của chain đó. Không cần viết một security interceptor riêng chỉ vì ứng dụng dùng functional endpoints.

### 16.2. `WebClient` gọi downstream

Spring Security bảo vệ **inbound** server requests. Khi service dùng WebClient gọi downstream, token forwarding hoặc OAuth2 Client token acquisition là một chủ đề riêng.

Không tự động chuyển nguyên `Authorization` của request inbound sang mọi host downstream. Chỉ forward token tới audience/host được phép, hoặc dùng `ServerOAuth2AuthorizedClientExchangeFilterFunction` trong client có scope phù hợp.

### 16.3. WebSocket handshake

WebSocket bắt đầu bằng một HTTP upgrade request, nên URL handshake vẫn có thể được bảo vệ bởi WebFlux `SecurityWebFilterChain`. Sau khi upgrade, WebSocket messages không phải HTTP requests mới; business authorization cho từng message/command cần cơ chế riêng.

### 16.4. RSocket

Spring Security có hỗ trợ RSocket authentication/authorization riêng ở tầng RSocket. `SecurityWebFilterChain` không tự bảo vệ từng RSocket message chỉ vì ứng dụng cũng chạy WebFlux HTTP. RSocket over WebSocket có handshake HTTP, nhưng RSocket message security vẫn phải được thiết kế theo giao thức.

### 16.5. Reverse proxy và forwarded headers

Nếu TLS kết thúc ở ingress, WebFlux có thể thấy kết nối HTTP từ proxy. Bất kỳ rule redirect-to-HTTPS nào dựa vào scheme đều cần forwarded headers đáng tin. Proxy ở trust boundary phải xóa `Forwarded`/`X-Forwarded-*` giả mạo rồi set lại metadata. `ForwardedHeaderTransformer` không tự xác minh rằng header đến từ proxy tin cậy.

## 17. Spring Boot tự cấu hình và các bẫy cấu hình

Thêm dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
```

Nếu Spring Security nằm trên classpath, Spring Boot có default security cho web application, bao gồm WebFlux. Trong môi trường phát triển có thể có một user mặc định tên `user` và password sinh tự động; đây **không** phải production identity store.

Khi cung cấp bean `SecurityWebFilterChain`, bạn có thể thay đổi rules và authentication modes. Khi cung cấp `ReactiveUserDetailsService` hoặc `ReactiveAuthenticationManager`, bạn có thể thay authentication user setup. Boot auto-configuration có quy tắc backoff riêng và có thể thay đổi khi thêm OAuth2 modules; đừng suy diễn mọi default bean đều biến mất chỉ vì tạo một chain.

### Những cách kiểm tra

- Có đang dùng `spring-boot-starter-web` khiến ứng dụng chạy Servlet thay vì WebFlux không?
- Có nhiều `SecurityWebFilterChain` nhưng không có `@Order` hoặc catch-all không?
- Có một bean `WebFilterChainProxy` do framework/app tự tạo không?
- Có module OAuth2 Resource Server/JWT nhưng chưa cấu hình issuer/JWK không?
- `@EnableReactiveMethodSecurity` có được bật nếu dùng `@PreAuthorize` không?
- Có annotation `@EnableWebSecurity` (Servlet) dùng nhầm trong WebFlux không?
- Có account demo hoặc password chưa được thay cho production không?

## 18. Dự án Java 17+ chạy được: nhiều chains, Basic, CSRF và method security

Dự án nhỏ sau minh họa:

1. Một security chain riêng cho `/api/**`, một fallback chain cho phần còn lại.
2. `GET /api/public` không yêu cầu credential.
3. `GET /api/me` yêu cầu authentication.
4. `GET /api/admin` yêu cầu `ROLE_ADMIN`.
5. `POST /api/items` yêu cầu `ROLE_EDITOR` và CSRF token.
6. `GET /api/reports/secret` dùng `@PreAuthorize("hasRole('ADMIN')")`.
7. `GET /health` được phép công khai.
8. URL khác bị fallback chain từ chối.
9. `WebTestClient` xác minh status 200/401/403 và body.
10. Demo credential được BCrypt hash; không sử dụng mật khẩu thực.

### 18.1. Cấu trúc thư mục

```text
webflux-security-chain/
├── pom.xml
└── src/
    ├── main/java/edu/demo/security/
    │   ├── SecurityApplication.java
    │   ├── SecurityConfig.java
    │   ├── ApiController.java
    │   └── ReportService.java
    └── test/java/edu/demo/security/
        └── SecurityIntegrationTests.java
```

### 18.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.demo</groupId>
    <artifactId>webflux-security-chain</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

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

### 18.3. `SecurityApplication.java`

```java
package edu.demo.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityApplication.class, args);
    }
}
```

### 18.4. `SecurityConfig.java`

```java
package edu.demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration
        .EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive
        .EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher
        .PathPatternParserServerWebExchangeMatcher;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("read-pass"))
                .roles("READER")
                .build();

        UserDetails editor = User.withUsername("editor")
                .password(encoder.encode("editor-pass"))
                .roles("EDITOR")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build();

        return new MapReactiveUserDetailsService(
                reader, editor, admin);
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
                .securityMatcher(
                        new PathPatternParserServerWebExchangeMatcher(
                                "/api/**"))
                .authorizeExchange(exchange -> exchange
                        .pathMatchers(HttpMethod.GET, "/api/public")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/admin")
                            .hasRole("ADMIN")
                        .pathMatchers(HttpMethod.POST, "/api/items")
                            .hasRole("EDITOR")
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain fallbackSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchange -> exchange
                        .pathMatchers(HttpMethod.GET, "/health")
                            .permitAll()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
```

Hai chains có matcher/order rõ ràng. Các POST request vẫn chịu CSRF protection mặc định; code không tắt CSRF.

Tên user/password này chỉ dùng cho demo/test. Trong production, quản lý credential qua identity provider hoặc storage an toàn, áp dụng hashing policy phù hợp và không đặt password trong code.

### 18.5. `ReportService.java`

```java
package edu.demo.security;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class ReportService {

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> secretReport() {
        return Mono.just("finance-report");
    }
}
```

Chính sách của service được thực thi khi method được gọi qua Spring proxy, sau khi authenticated security context đã được truyền vào Reactor pipeline.

### 18.6. `ApiController.java`

```java
package edu.demo.security;

import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.security.core.context
        .ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    private final ReportService reportService;

    public ApiController(ReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping("/api/public")
    public Mono<String> publicInfo() {
        return Mono.just("public");
    }

    @GetMapping("/api/me")
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
                .map(context ->
                        context.getAuthentication().getName());
    }

    @GetMapping("/api/admin")
    public Mono<String> admin() {
        return Mono.just("admin-only");
    }

    @GetMapping("/api/reports/secret")
    public Mono<String> secretReport() {
        return reportService.secretReport();
    }

    @PostMapping(
            path = "/api/items",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Map<String, String>> createItem(
            @RequestBody Mono<ItemRequest> incoming) {

        return incoming.map(item ->
                Map.of("name", item.name(), "state", "created"));
    }

    @GetMapping("/health")
    public Mono<String> health() {
        return Mono.just("healthy");
    }

    @GetMapping("/unexpected")
    public Mono<String> unexpected() {
        return Mono.just("should-not-be-visible");
    }

    public record ItemRequest(String name) {
    }
}
```

`/api/me` cho thấy cách đọc identity từ Reactor Context. Endpoint `/api/reports/secret` chỉ cần authenticated ở URL rule, nhưng bị `ReportService` kiểm tra `ROLE_ADMIN`.

Trong ví dụ đơn giản, service trả chuỗi cố định; production phải thực thi quyền trên resource/domain cụ thể và validate request body.

### 18.7. `SecurityIntegrationTests.java`

```java
package edu.demo.security;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class SecurityIntegrationTests {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void publicApiDoesNotRequireAuthentication() {
        client.get()
                .uri("/api/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void healthIsPublicThroughFallbackChain() {
        client.get()
                .uri("/health")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("healthy");
    }

    @Test
    void protectedApiWithoutCredentialsReturns401() {
        client.get()
                .uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void wrongBasicCredentialsReturn401() {
        client.get()
                .uri("/api/me")
                .headers(headers ->
                        headers.setBasicAuth("reader", "wrong"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void validBasicCredentialsExposeUsername() {
        client.get()
                .uri("/api/me")
                .headers(headers ->
                        headers.setBasicAuth("reader", "read-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("reader");
    }

    @Test
    void readerCannotEnterAdminEndpoint() {
        client.get()
                .uri("/api/admin")
                .headers(headers ->
                        headers.setBasicAuth("reader", "read-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminCanEnterAdminEndpoint() {
        client.get()
                .uri("/api/admin")
                .headers(headers ->
                        headers.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin-only");
    }

    @Test
    void serviceMethodSecurityDeniesReader() {
        client.get()
                .uri("/api/reports/secret")
                .headers(headers ->
                        headers.setBasicAuth("reader", "read-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void serviceMethodSecurityAllowsAdmin() {
        client.get()
                .uri("/api/reports/secret")
                .headers(headers ->
                        headers.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("finance-report");
    }

    @Test
    void editorPostWithoutCsrfIsForbidden() {
        client.post()
                .uri("/api/items")
                .headers(headers ->
                        headers.setBasicAuth("editor", "editor-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new ApiController.ItemRequest("Notebook"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void editorPostWithValidCsrfSucceeds() {
        client.mutateWith(csrf())
                .post()
                .uri("/api/items")
                .headers(headers ->
                        headers.setBasicAuth("editor", "editor-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new ApiController.ItemRequest("Notebook"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.name").isEqualTo("Notebook")
                .jsonPath("$.state").isEqualTo("created");
    }

    @Test
    void readerWithCsrfStillCannotCreateItem() {
        client.mutateWith(csrf())
                .post()
                .uri("/api/items")
                .headers(headers ->
                        headers.setBasicAuth("reader", "read-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new ApiController.ItemRequest("Notebook"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void fallbackChainDeniesOtherPathsEvenWhenLoggedIn() {
        client.get()
                .uri("/unexpected")
                .headers(headers ->
                        headers.setBasicAuth("reader", "read-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void mockUserCanTestAuthorizationWithoutPassword() {
        client.mutateWith(mockUser().roles("ADMIN"))
                .get()
                .uri("/api/admin")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin-only");
    }
}
```

`WebTestClient.bindToApplicationContext` dùng WebFlux mock server pipeline, không cần mở HTTP port thực. `.apply(springSecurity())` kết nối Spring Security Test với `WebTestClient`, giúp các mutator như `mockUser()` và `csrf()` hoạt động theo request. Các test dùng HTTP Basic trực tiếp còn kiểm tra credential thật trong demo in-memory user store.

Các mục tiêu assertion:

| Nhóm | Kết quả |
|---|---|
| Public API/health | 200 |
| Thiếu Basic hoặc sai password | 401 |
| ROLE_READER truy cập admin | 403 |
| ROLE_ADMIN truy cập admin | 200 |
| `@PreAuthorize` từ chối reader | 403 |
| `@PreAuthorize` chấp nhận admin | 200 |
| POST có editor nhưng thiếu CSRF | 403 |
| POST có editor và CSRF hợp lệ | 200 + JSON |
| POST reader dù có CSRF | 403 |
| Fallback path | 403 |
| Mock principal cho admin | 200 |

Đây là các expected outcomes, không phải kết quả kiểm thử đã được ghi nhận từ một lần chạy Maven trong môi trường biên soạn.

### 18.8. Chạy dự án

Trong thư mục chứa `pom.xml`:

```bash
mvn test
```

Chạy server:

```bash
mvn spring-boot:run
```

GET công khai:

```bash
curl -i http://localhost:8080/api/public
```

GET với Basic credentials demo:

```bash
curl -i -u reader:read-pass http://localhost:8080/api/me
```

GET admin:

```bash
curl -i -u admin:admin-pass http://localhost:8080/api/admin
```

Không sử dụng demo password hoặc HTTP cleartext trong production. Trong hệ thống thật, HTTPS/TLS là yêu cầu tối thiểu khi truyền Basic credentials. POST từ browser/client cần tuân thủ CSRF token flow của ứng dụng; không chỉ thêm Basic header rồi nghĩ có thể ghi dữ liệu.

### 18.9. Những gì test mẫu chưa bao phủ

Để sử dụng trong production, cần thêm test:

- CSRF token không hợp lệ hoặc hết hạn.
- Role thay đổi trong session.
- Authentication backend chậm hoặc tạm lỗi.
- CORS preflight từ origin cho phép/không cho phép.
- OAuth2 JWT issuer/audience/scope.
- Authentication/authorization ở WebSocket handshake.
- Method security khi `Mono.error`, `Flux` và cancellation.
- Reverse proxy forwarded headers và HTTPS redirect.
- Path encoding/trailing slash/URL normalization.
- Security HTTP response headers và caching policy.
- Nhiều chains khi có Actuator endpoints.

## 19. Testing: mock identity và test credential thật

Có hai lớp test khác nhau.

### 19.1. Mock user

```java
client.mutateWith(mockUser().roles("ADMIN"))
        .get()
        .uri("/api/admin")
        .exchange()
        .expectStatus().isOk();
```

Dễ dùng để test rule authorization, nhưng **không** chứng minh Basic password encoder, JWT signature validation hoặc connection tới identity provider hoạt động thật.

### 19.2. Gửi credential thật trong test

```java
client.get()
        .uri("/api/me")
        .headers(headers ->
                headers.setBasicAuth("reader", "read-pass"))
        .exchange()
        .expectStatus().isOk();
```

Cách này kiểm tra Basic authentication pipeline và configured user service trong application context của test.

Với JWT, Spring Security Test có `mockJwt()` để kiểm tra authorization với authorities/claims mô phỏng; dùng integration tests riêng để kiểm tra signature, expiry, audience, issuer và JWK rotation.

### 19.3. Kiểm thử không chỉ happy path

Ít nhất cần có trường hợp:

- Unauthenticated → 401.
- Authenticated nhưng thiếu quyền → 403.
- Authenticated và đủ quyền → 200/201.
- Endpoint `permitAll`.
- CSRF protection với unsafe HTTP method.
- URL không thuộc chain dự định.
- URL thuộc nhiều matcher: xác nhận chain precedence.
- Method security ngoài HTTP handler nếu service có caller khác.

## 20. Phân quyền theo request và kiểm tra idempotency

Security chỉ quyết định ai có quyền gọi operation. Nó không tự bảo đảm operation có thể retry an toàn hoặc không gây side effect trùng.

Ví dụ một endpoint tạo đơn hàng:

```text
POST /api/orders
```

Ngay cả khi `ROLE_EDITOR` được phép POST và CSRF token đúng, client retry do timeout vẫn có thể gửi lại một giao dịch đã được server xử lý. Phải thiết kế idempotency key, transaction boundaries và authorization kiểm tra ownership tại domain layer.

Đừng trộn logic xác thực/phân quyền với xử lý retry, database transaction hoặc outbound network call trong một custom `WebFilter` phức tạp. Filter nên làm trách nhiệm bảo mật/quan sát phù hợp, còn use case xử lý nghiệp vụ ở service.

## 21. Những lỗi phổ biến và cách sửa

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Dùng `HttpSecurity`/`SecurityFilterChain` trong WebFlux | Cấu hình sai stack | Dùng `ServerHttpSecurity`/`SecurityWebFilterChain` |
| Chỉ định chain `/api/**` nhưng không có fallback | Path khác có thể không được bảo vệ | Tạo catch-all chain với `anyExchange().denyAll()` |
| Nhầm `securityMatcher` với `pathMatchers` | Tưởng đang bảo vệ path nhưng chain không áp dụng | Phân biệt chọn chain và phân quyền trong chain |
| Đặt `anyExchange().permitAll()` sớm | Quy tắc chặt phía sau không áp dụng | Xếp từ cụ thể tới tổng quát |
| Nhiều chain không đặt `@Order` | Khó dự đoán chain nào match trước | Khai báo order rõ |
| Tưởng `permitAll` bỏ qua mọi filter | POST công khai vẫn bị CSRF từ chối | Hiểu security pipeline và token policy |
| Dùng `hasRole("ADMIN")` với authority `"ADMIN"` | Role check thất bại | Dùng `ROLE_ADMIN` hoặc `hasAuthority` đúng contract |
| Chuyển JWT scope `admin` thành role ADMIN không qua converter | Phân quyền sai | Cấu hình mapping được test |
| Gọi `SecurityContextHolder` như Servlet | Mất context khi đổi thread | Dùng `ReactiveSecurityContextHolder` |
| Tự `subscribe()` trong service | Tách context, error và cancellation | Return/compose Mono/Flux |
| Tắt CSRF cho mọi chain | Browser session/Basic có thể bị CSRF | Chỉ tắt với stateless Bearer-only threat model đã xác minh |
| Dùng CORS để thay authentication | Client ngoài browser vẫn gọi được API | Bảo vệ bằng authentication/authorization thực |
| Cho phép mọi origin với credentials | Tăng rủi ro dữ liệu bị website không tin cậy đọc | Allowlist origins cụ thể |
| Tự decode JWT nhưng không verify signature/issuer/expiry | Token giả có thể được chấp nhận | Dùng OAuth2 Resource Server và validators |
| Lưu bearer token trong global field | Rò rỉ giữa nhiều users | Token theo request/authorized client |
| Không bật method security nhưng đã gắn `@PreAuthorize` | Annotation không được thực thi | Bật `@EnableReactiveMethodSecurity` và test |
| Self-invocation method có annotation | Bỏ qua Spring proxy/interceptor | Gọi qua bean boundary hoặc thiết kế service khác |
| Chặn event loop trong auth manager | Tăng latency của mọi request | Dùng reactive I/O hoặc bounded scheduler có giới hạn |
| Ghi nguyên Authorization/cookie vào log | Lộ credential | Mask secret và log metadata an toàn |
| Gọi 403 cho mọi authentication failure | Client không biết khi nào cần đăng nhập | Phân biệt entry point 401 và access denied 403 |
| Đưa role tùy ý từ request header vào context | Privilege escalation | Xác minh credential qua authentication manager |
| Tưởng security chain bảo vệ mọi WebSocket/RSocket message | Thiếu per-message authorization | Thiết kế security cho giao thức/message riêng |
| Không test route không thuộc chain | Lộ endpoint khi thêm controller mới | Fallback denyAll + regression tests |

## 22. Checklist production

### Kiến trúc

- Ứng dụng đang chạy reactive WebFlux chứ không phải Servlet?
- Có bean `SecurityWebFilterChain` đúng loại?
- Mỗi chain có `securityMatcher` và `@Order` phù hợp?
- Có chain catch-all hoặc deny policy cho URL không được khai báo?
- Có các rule cụ thể trước `anyExchange()`?
- Có kiểm thử các endpoint error, actuator và WebSocket handshake?

### Authentication

- Dùng cơ chế chuẩn HTTP Basic/OAuth2 Resource Server/OAuth2 Client?
- `ReactiveAuthenticationManager` và identity store không block event loop?
- Password encoder an toàn, không lưu plain text?
- Credential/token có TTL, rotation và revoke policy thích hợp?
- JWT có verify signature, issuer, audience, exp/nbf và authorities?
- Token không xuất hiện trong URL, logs hoặc metrics tags?

### Authorization

- Role và authority được map đúng quy ước?
- `@EnableReactiveMethodSecurity` bật nếu dùng `@PreAuthorize`?
- Service được gọi qua Spring proxy để advice chạy?
- Có kiểm tra resource ownership/domain policy?
- 401 và 403 được phân biệt trong response contract?
- Có test authenticated thiếu quyền và đủ quyền?

### Web security

- CSRF bật nơi có browser ambient credentials?
- CORS allowlist hợp lý và preflight hoạt động?
- HTTPS/TLS và proxy forwarded headers được xử lý an toàn?
- Cookie/session Secure, HttpOnly, SameSite phù hợp?
- Security response headers được giữ theo chính sách?
- Không expose endpoint quản trị/diagnostics không chủ ý?

### Reactive và vận hành

- Không dùng ThreadLocal để truyền security context giữa operators?
- Không tự subscribe/block trong authentication/authorization pipeline?
- Có metrics cho authentication failures, access denials và latency?
- Có rate limiting/abuse protection nếu cần?
- Log được correlation ID nhưng không ghi raw credentials?
- Có kiểm thử integration bằng WebTestClient và negative scenarios?

## 23. Câu hỏi tự kiểm tra

**1.** `SecurityWebFilterChain` khác `SecurityFilterChain` ở đâu?

**Đáp án:** `SecurityWebFilterChain` là loại reactive cho WebFlux (`WebFilter`); `SecurityFilterChain` thuộc Servlet (`Filter`).

**2.** `securityMatcher("/api/**")` và `pathMatchers("/api/admin")` có cùng trách nhiệm không?

**Đáp án:** Không. `securityMatcher` quyết định chain có áp dụng; `pathMatchers` trong `authorizeExchange` chọn rule authorization khi chain đó đã được chọn.

**3.** Nếu không chain nào match `/debug`, endpoint có tự động bị từ chối không?

**Đáp án:** Không thể dựa vào điều đó. Request không có security chain khớp có nguy cơ không được Spring Security bảo vệ. Cần catch-all chain.

**4.** `hasRole("ADMIN")` mặc định yêu cầu authority nào?

**Đáp án:** `ROLE_ADMIN`.

**5.** User đã xác thực nhưng thiếu role cần thiết thì thường nhận status nào?

**Đáp án:** 403 Forbidden. Khi thiếu credential hợp lệ thường nhận 401 Unauthorized với entry point phù hợp.

**6.** Trong WebFlux service, lấy authentication từ đâu?

**Đáp án:** `ReactiveSecurityContextHolder.getContext()` trong Reactor Context, không dùng ThreadLocal Servlet như nguồn chính.

**7.** Có nên tắt CSRF chỉ vì API dùng HTTP Basic không?

**Đáp án:** Không. Browser có thể tự gửi Basic credentials. CSRF cần được đánh giá theo loại credential và cách browser thực sự gửi request.

**8.** Bật `@PreAuthorize` trên service cần annotation nào trong ứng dụng WebFlux?

**Đáp án:** `@EnableReactiveMethodSecurity` và method được gọi qua Spring-managed proxy với reactive context.

**9.** JWT scope `catalog.read` thường thành authority nào theo mapping mặc định?

**Đáp án:** `SCOPE_catalog.read`.

**10.** `mockUser()` test được những gì và không test được gì?

**Đáp án:** Test authorization rules với principal mô phỏng. Nó không chứng minh password hashing, JWT signature/issuer/audience validation hoặc kết nối tới identity provider thật.

## 24. Ghi nhớ

- WebFlux Security dựa vào `WebFilter`, `SecurityWebFilterChain` và `ServerHttpSecurity`.
- `WebFilterChainProxy` chọn một chain khớp request; chain có order cao hơn được xét trước.
- `securityMatcher` chọn chuỗi; `authorizeExchange` định nghĩa quyền truy cập trong chuỗi.
- Nên có một chain fallback để tránh URL không được bảo vệ.
- Authentication qua `AuthenticationWebFilter`/`ReactiveAuthenticationManager`; authorization qua các WebFilters tương ứng.
- Identity đi theo Reactor Context: dùng `ReactiveSecurityContextHolder`.
- HTTP authorization và reactive method security bảo vệ các lớp khác nhau; dùng cả hai khi hợp lý.
- CSRF và CORS có mục tiêu khác nhau, không thay thế nhau.
- `permitAll()` không tự tắt security filters, còn `denyAll()` giúp bảo vệ default.
- HTTP Basic và browser cookies có thể liên quan đến CSRF; chỉ tắt theo threat model thật.
- Với Bearer JWT, ưu tiên OAuth2 Resource Server và validate token đúng issuer/audience/scope.
- `SecurityWebFiltersOrder` cho phép chèn filter đúng vị trí nhưng không nên tự viết authentication khi framework đã hỗ trợ.
- Test 200/401/403, CSRF, chain order, method security, fallback và credentials bằng `WebTestClient`.

**Quy tắc kiểm tra nhanh:** **Request khớp chain nào? Chain đó xác thực bằng gì? Rule authorization nào quyết định quyền? Service còn kiểm tra domain/method security không?** Trả lời đủ bốn câu hỏi sẽ giúp cấu hình Spring Security cho WebFlux đúng và an toàn hơn.

## 25. Tài liệu chính thức

- Spring Security — WebFlux Security và multiple chains: https://docs.spring.io/spring-security/reference/6.3/reactive/configuration/webflux.html
- Spring Boot 3.3 — WebFlux Security auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/6.3/reactive/authorization/method.html
- Spring Security — Reactive OAuth2 Resource Server/JWT: https://docs.spring.io/spring-security/reference/6.3/reactive/oauth2/resource-server/jwt.html
- Spring Security — Reactive CSRF: https://docs.spring.io/spring-security/reference/6.3/reactive/exploits/csrf.html
- Spring Security — Reactive Web Security Test: https://docs.spring.io/spring-security/reference/6.3/reactive/test/web/
- Spring Security — `ServerHttpSecurity` API: https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security — `AuthenticationWebFilter` API: https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html
- Spring Framework — WebFlux and WebFilter infrastructure: https://docs.spring.io/spring-framework/reference/6.1/web/webflux/reactive-spring.html
- Spring Framework — WebTestClient: https://docs.spring.io/spring-framework/reference/6.1/testing/webtestclient.html