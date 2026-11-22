# Chuyển từ HttpSecurity và SecurityFilterChain sang ServerHttpSecurity và SecurityWebFilterChain

## 1. Mục tiêu và ranh giới của việc chuyển đổi

Trong Spring Security, cấu hình bảo mật của ứng dụng Spring MVC/Servlet và ứng dụng Spring WebFlux cùng xử lý những yêu cầu như xác thực người dùng, phân quyền đường dẫn, HTTP Basic, OAuth2 Resource Server, CSRF và xử lý truy cập bị từ chối. Tuy nhiên, chúng chạy trên **hai mô hình thực thi khác nhau**:

- **Servlet:** request đi qua `jakarta.servlet.Filter`; chuỗi bảo mật được khai báo bằng `HttpSecurity` và tạo ra `SecurityFilterChain`. Luồng xử lý thường gắn với Servlet request và mô hình đồng bộ.
- **Reactive WebFlux:** request đi qua `org.springframework.web.server.WebFilter`; cấu hình dùng `ServerHttpSecurity` và trả về `SecurityWebFilterChain`. Thông tin bảo mật gắn với Reactor Context, các thao tác xác thực/phân quyền bất đồng bộ có thể trả về `Mono`.

Chuyển đổi đúng nghĩa là chuyển **hợp đồng bảo mật và cách nối các component vào pipeline reactive**, không chỉ đổi tên lớp. Mục tiêu sau khi chuyển là: cùng endpoint được yêu cầu cùng mức quyền, người chưa đăng nhập không truy cập tài nguyên bảo vệ, người đã đăng nhập nhưng thiếu quyền bị từ chối, các bước I/O không chặn event loop, và trạng thái đăng nhập/CSRF/OAuth2 vẫn đáp ứng kiến trúc dự kiến.

Bài này dùng **Spring Boot 3.3, Spring Security 6.x và Java 17+** làm nền tảng minh họa. Một ứng dụng chỉ nên chạy đúng security stack tương ứng với loại web application thực tế. Việc import lớp reactive vào project còn chạy MVC không tự biến project thành WebFlux.

## 2. Bản đồ chuyển đổi API quan trọng

| Trách nhiệm | Servlet/MVC | Reactive/WebFlux | Điều cần giữ nguyên hoặc kiểm tra |
| --- | --- | --- | --- |
| Bật web security | `@EnableWebSecurity` | `@EnableWebFluxSecurity` | Đúng kiểu ứng dụng và context. |
| Đối tượng cấu hình HTTP | `HttpSecurity` | `ServerHttpSecurity` | Không cast/adapter trực tiếp giữa hai DSL. |
| Chain được công bố thành bean | `SecurityFilterChain` | `SecurityWebFilterChain` | Có một chain phù hợp cho mỗi request, xét thứ tự khi nhiều chain. |
| Bộ lọc security | `Filter` / `FilterChainProxy` | `WebFilter` / `WebFilterChainProxy` | Filter Servlet không chạy như WebFilter. |
| Đặt rule theo URL | `authorizeHttpRequests(...)`, `requestMatchers(...)` | `authorizeExchange(...)`, `pathMatchers(...)` | Bảo toàn thứ tự rule cụ thể → rule bao quát. |
| Chọn chain theo request | `securityMatcher(...)` | `securityMatcher(ServerWebExchangeMatcher)` | Khác với việc phân quyền bên trong chain. |
| Request matcher tùy biến | `RequestMatcher` | `ServerWebExchangeMatcher` | WebFlux dùng `ServerWebExchange` thay vì `HttpServletRequest`. |
| Trình quản lý xác thực | `AuthenticationManager` | `ReactiveAuthenticationManager` | Đường reactive trả về `Mono<Authentication>`. |
| Tra cứu người dùng | `UserDetailsService` | `ReactiveUserDetailsService` | Không đưa JDBC blocking vào event loop. |
| Quy tắc phân quyền tùy biến | `AuthorizationManager<RequestAuthorizationContext>` | `ReactiveAuthorizationManager<AuthorizationContext>` | Quyết định reactive là `Mono<AuthorizationDecision>`. |
| JWT Resource Server | `JwtDecoder` | `ReactiveJwtDecoder` | Bảo toàn issuer/audience/key, chuyển converter nếu tùy biến. |
| Lưu/đọc SecurityContext | `SecurityContextHolder`, `SecurityContextRepository` | `ReactiveSecurityContextHolder`, `ServerSecurityContextRepository` | Reactor Context khác thread-local. |
| Ngữ cảnh request | `HttpServletRequest`/`HttpServletResponse` | `ServerWebExchange`/`ServerHttpRequest`/`ServerHttpResponse` | Chuyển handler/filter dùng Servlet API. |
| Method security | `@EnableMethodSecurity` | `@EnableReactiveMethodSecurity` | Method được bảo vệ phải tuân hợp đồng reactive thích hợp. |
| Kiểm thử web security | `MockMvc` | `WebTestClient` | Kiểm thử cả success, unauthorized và forbidden. |

**Hai cặp không được nhầm:** `HttpSecurity.build()` tạo `SecurityFilterChain`; `ServerHttpSecurity.build()` tạo `SecurityWebFilterChain`. Tên phương thức thường tương tự (`httpBasic`, `csrf`, `oauth2ResourceServer`), nhưng kiểu đối số và các SPI khác nhau; code của MVC không thể được sao chép nguyên khối sang WebFlux.

## 3. Chuyển một cấu hình URL rule đơn giản: trước và sau

Giả sử cả hai phiên bản cần cùng chính sách:

- `GET /public/ping`: cho phép mọi người.
- `GET /api/hello`: phải xác thực.
- `GET /api/admin`: phải có authority `ROLE_ADMIN`.
- Mọi endpoint còn lại: phải xác thực.

### 3.1. Bản Servlet/MVC trước khi chuyển

Tệp minh họa `ServletSecurityConfig.java`, chỉ dùng trong dự án Spring MVC có `spring-boot-starter-web` và `spring-boot-starter-security`:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class ServletSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(rules -> rules
                        .requestMatchers("/public/**").permitAll()
                        .requestMatchers("/api/admin/**").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

`hasRole("ADMIN")` kiểm tra authority `ROLE_ADMIN` theo prefix mặc định; `hasAuthority("ADMIN")` là kiểm tra chuỗi `ADMIN` nguyên vẹn và không tương đương. Nếu hệ thống dùng JWT OAuth2 scope `SCOPE_admin` thì phải dùng rule phù hợp với scope thay vì mặc định thay `hasRole`.

### 3.2. Bản reactive WebFlux sau khi chuyển

Tệp minh họa `ReactiveSecurityConfig.java`, chỉ dùng trong dự án WebFlux có `spring-boot-starter-webflux` và `spring-boot-starter-security`:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(rules -> rules
                        .pathMatchers("/public/**").permitAll()
                        .pathMatchers("/api/admin/**").hasRole("ADMIN")
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

So sánh từng phần:

1. `@EnableWebSecurity` → `@EnableWebFluxSecurity`.
2. Bean tham số `HttpSecurity` → `ServerHttpSecurity`.
3. Kiểu trả về `SecurityFilterChain` → `SecurityWebFilterChain`.
4. `authorizeHttpRequests` → `authorizeExchange`.
5. `requestMatchers` → `pathMatchers`; `anyRequest` → `anyExchange`.
6. `httpBasic` vẫn có tên tương tự, nhưng được cấu hình trên DSL reactive.
7. Bean reactive trong ví dụ **không khai báo `throws Exception`**, vì `ServerHttpSecurity.build()` không có hợp đồng checked exception giống `HttpSecurity.build()`.

Không đặt đồng thời hai class ví dụ này trong cùng dự án để “thử xem class nào chạy”: chúng là **hai phương án thuộc hai stack riêng**. Chỉ mang các chính sách đã đối chiếu sang cấu hình WebFlux đích.

## 4. Ví dụ ứng dụng WebFlux chạy được và tự kiểm tra

Để thấy sự khác biệt có thể quan sát được, sau đây là ứng dụng WebFlux tối thiểu: công khai một route, bảo vệ một route và từ chối route yêu cầu role ADMIN. Ví dụ sử dụng HTTP Basic và user trong bộ nhớ **chỉ cho bài thực hành**; ứng dụng production phải thay bằng nguồn danh tính và bộ mã hóa mật khẩu an toàn.

### 4.1. Dependency trong dự án Spring Boot đã cấu hình plugin/BOM

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Trong module WebFlux đích, kiểm tra không còn dependency `spring-boot-starter-web` hoặc transitive MVC ngoài ý muốn. Khi có cả Spring MVC và WebFlux, Spring Boot thông thường chọn MVC. Có thể kiểm tra bằng dependency tree và log loại web application lúc khởi động; `spring.main.web-application-type=reactive` là công tắc ép kiểu khi có lý do rõ ràng, nhưng không thay thế việc xử lý các dependency/cấu hình không tương thích.

### 4.2. Tệp `src/main/java/demo/ReactiveSecurityDemoApplication.java`

Đây là **một tệp Java có thể biên dịch trong project Boot WebFlux ở trên**; hai class không public có thể nằm cùng tệp với class public chính.

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class ReactiveSecurityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveSecurityDemoApplication.class, args);
    }
}

@Configuration
@EnableWebFluxSecurity
class ReactiveSecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(rules -> rules
                        .pathMatchers("/public/**").permitAll()
                        .pathMatchers("/api/admin/**").hasRole("ADMIN")
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails learner = User.withUsername("learner")
                .password("{noop}demo-pass")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(learner);
    }
}

@RestController
class DemoController {

    @GetMapping("/public/ping")
    Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/api/hello")
    Mono<String> hello() {
        return ReactiveSecurityContextHolder.getContext()
                .map(ctx -> "hello " + ctx.getAuthentication().getName());
    }

    @GetMapping("/api/admin")
    Mono<String> admin() {
        return Mono.just("admin");
    }
}
```

Giải thích các quyết định trong mẫu:

- `MapReactiveUserDetailsService` là thành phần reactive tương ứng với nguồn user trong bộ nhớ. `{noop}` khiến mật khẩu được so khớp dạng plaintext, **chỉ dùng cho demo**; với người dùng thật hãy lưu hash phù hợp và sử dụng `PasswordEncoder`.
- `httpBasic` cung cấp authentication challenge kiểu Basic. Tắt `formLogin` ở ví dụ API này để tránh nhầm hành vi redirect đến trang đăng nhập; với ứng dụng browser có form login, phải giữ lại flow đăng nhập và CSRF thích hợp.
- `ReactiveSecurityContextHolder.getContext()` lấy thông tin xác thực từ **Reactor Context khi publisher được subscribe**. Tránh thay bằng `SecurityContextHolder.getContext()` rồi giả định thread-local luôn đúng trên mọi event loop.
- Các handler đều trả về `Mono<String>`, không gọi `block()` và không chạy I/O đồng bộ.

Chạy bằng wrapper của dự án (đã có plugin Boot, dependency management và Java toolchain tương thích):

```bash
./gradlew bootRun
```

Gửi request để quan sát (giả sử ứng dụng nghe tại localhost:8080):

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/hello
curl -i -u learner:demo-pass http://localhost:8080/api/hello
curl -i -u learner:demo-pass http://localhost:8080/api/admin
```

Kết quả mong đợi:

| Request | HTTP status | Body đáng chú ý | Lý do |
| --- | --- | --- | --- |
| `GET /public/ping` không credential | `200` | `pong` | `permitAll`. |
| `GET /api/hello` không credential | `401` | Tùy cơ chế xử lý lỗi | Thiếu authentication. |
| `GET /api/hello` với HTTP Basic `learner` | `200` | `hello learner` | Đã xác thực. |
| `GET /api/admin` với HTTP Basic `learner` | `403` | Tùy cơ chế xử lý lỗi | User có `ROLE_USER`, không có `ROLE_ADMIN`. |

Không khẳng định output HTTP headers là cố định giữa mọi bản runtime; status và body thành công là điều cần đối chiếu. HTTP Basic chỉ được truyền qua HTTPS trong môi trường thật.

### 4.3. Kiểm thử tích hợp bằng `WebTestClient`

Tệp `src/test/java/demo/ReactiveSecurityDemoApplicationTests.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveSecurityDemoApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicAndProtectedRoutesKeepTheirPolicies() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");

        client.get().uri("/api/hello")
                .exchange()
                .expectStatus().isUnauthorized();

        client.get().uri("/api/hello")
                .headers(headers ->
                        headers.setBasicAuth("learner", "demo-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("hello learner");

        client.get().uri("/api/admin")
                .headers(headers ->
                        headers.setBasicAuth("learner", "demo-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }
}
```

Chạy `./gradlew test`. Các request test kiểm tra **behavior từ HTTP vào tới controller**, giúp phát hiện chain sai, rule sai, thay đổi status hoặc context không được truyền. Khi dùng `@WebFluxTest` thay cho integration test, cần import security configuration liên quan và bảo đảm `WebTestClient` thực sự áp dụng cấu hình Spring Security trước khi diễn giải kết quả.

## 5. Chuyển nhiều chain: phân biệt chọn chain và quyết định quyền

Một ứng dụng Servlet thường có nhiều `SecurityFilterChain`, ví dụ một chain cho API và một chain cho giao diện. Sang WebFlux vẫn cần xác định **chain nào áp dụng cho request trước**, sau đó mới áp dụng rule bên trong chain.

- `http.securityMatcher(...)` giới hạn phạm vi của **cả chain**.
- `http.authorizeExchange(...).pathMatchers(...)` đưa ra **quyết định quyền trong chain đã được chọn**.
- Với nhiều `SecurityWebFilterChain`, framework xét theo thứ tự `@Order` và chọn **chain khớp đầu tiên**. Chain thấp ưu tiên hơn không được áp dụng tiếp để “bổ sung” rule cho chain đã chọn.
- Luôn có một chain catch-all với policy có chủ đích, tránh route nằm ngoài mọi chain.

Ví dụ minh họa hai chain WebFlux (đặt các bean trong class `@Configuration @EnableWebFluxSecurity`, dùng cho project đã có cơ chế authentication tương ứng):

```java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Bean
@Order(1)
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
            .securityMatcher(
                    new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(rules ->
                    rules.anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}

@Bean
@Order(2)
SecurityWebFilterChain otherChain(ServerHttpSecurity http) {
    return http
            .authorizeExchange(rules -> rules
                    .pathMatchers("/public/**").permitAll()
                    .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

Đoạn này là **hai phương thức bean để chèn vào class cấu hình**, không phải tệp Java chạy riêng. Khi request là `/api/orders`, chain `apiChain` khớp trước; với `/public/ping`, chain `otherChain` xử lý. Chuyển `@Order` hoặc đặt catch-all ở vị trí ưu tiên hơn có thể khiến chain API không bao giờ chạy. Nếu hệ thống dùng session/form login ở chain web và Bearer token ở chain API, giữ **phân tách các cơ chế** khi di chuyển, thay vì vô tình bật mọi phương thức login cho mọi route.

## 6. Xác thực: không chuyển nguyên các component đồng bộ

### 6.1. User/password, HTTP Basic và custom authentication

Đối với Servlet, security có thể dùng `AuthenticationManager` và `UserDetailsService` đồng bộ. Với WebFlux, các SPI tương ứng thường là `ReactiveAuthenticationManager` và `ReactiveUserDetailsService`. Đặc điểm khác biệt là authentication có thể bao gồm network/DB call reactive và trả về `Mono<Authentication>`.

Ví dụ hình dạng API:

```java
// Minh họa chữ ký SPI, không phải triển khai standalone.
Mono<Authentication> authenticate(Authentication input); // reactive
UserDetails loadUserByUsername(String username);        // servlet/blocking
Mono<UserDetails> findByUsername(String username);      // reactive
```

Phương thức chính xác của `ReactiveUserDetailsService` là `findByUsername(String username)`; phương thức của `UserDetailsService` là `loadUserByUsername(String username)`. Nếu project cũ có custom `AuthenticationProvider`, hãy rà soát việc chuyển thành reactive manager hoặc adapter được kiểm soát; không giữ nguyên DAO đồng bộ rồi gọi trực tiếp trong pipeline reactive. Nếu không thể đổi adapter đồng bộ ngay, phải cô lập công việc blocking trên scheduler phù hợp, hạn chế concurrency và đo khả năng chịu tải, đồng thời lập kế hoạch thay bằng driver/API nonblocking.

Với custom xác thực từ header, `OncePerRequestFilter` hoặc `javax.servlet.Filter`/`jakarta.servlet.Filter` là cấu trúc của Servlet. Trong WebFlux, đăng ký `WebFilter` hoặc các component của Spring Security reactive như `AuthenticationWebFilter`, đặt vào thứ tự `SecurityWebFiltersOrder` phù hợp. Một `WebFilter` tự tạo chỉ kiểm tra header rồi truyền `chain.filter(exchange)` **không tự tạo authentication**. Phải tích hợp `ReactiveAuthenticationManager` và `ServerSecurityContextRepository`/Reactor Context đúng cách, và bảo đảm filter không làm mất context, không phản hồi sớm sai mã lỗi.

### 6.2. JWT/opaque token và OAuth2

Khi chuyển **Resource Server JWT**, cấu hình khái quát chuyển từ:

```java
// Servlet:
http.oauth2ResourceServer(oauth2 ->
        oauth2.jwt(Customizer.withDefaults()));

// Reactive:
http.oauth2ResourceServer(oauth2 ->
        oauth2.jwt(Customizer.withDefaults()));
```

Dù DSL trông giống nhau, Servlet thường dùng `JwtDecoder` và WebFlux dùng `ReactiveJwtDecoder`. Nếu ứng dụng cũ đã tùy biến validator (`iss`, `aud`, `exp`), mapping claim thành authority, key rotation hoặc xử lý lỗi Bearer, những điều đó phải được chuyển và kiểm tra lại tương ứng. Không được dựa vào việc phương thức `jwt(...)` biên dịch để kết luận toàn bộ cơ chế tương đương.

Với Spring Boot Resource Server, cấu hình issuer có thể giữ cùng dạng thuộc tính:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/issuer
```

Giá trị URL trên chỉ là ví dụ, phải thay bằng issuer thật. JWT scopes thường được ánh xạ sang authority có prefix `SCOPE_`; nếu rule Servlet dùng `hasAuthority("SCOPE_reports.read")` thì hãy kiểm tra reactive giữ đúng tên authority. Với **opaque token**, SPI cần xem là `ReactiveOpaqueTokenIntrospector`, không dùng `OpaqueTokenIntrospector` Servlet làm bean thay thế một cách máy móc. OAuth2 Login/OIDC, refresh token và authorized client cũng có các client, repository và service reactive riêng; không giả định Resource Server JWT bao phủ luôn flow OAuth2 Login.

### 6.3. SecurityContext và principal

Trong Servlet, mẫu này thường thấy:

```java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
String username = authentication.getName();
```

Trong WebFlux, thực hiện tương đương **bên trong pipeline reactive**:

```java
Mono<String> username =
        ReactiveSecurityContextHolder.getContext()
                .map(context -> context.getAuthentication().getName());
```

Reactor có thể đổi thread trên `publishOn`/`subscribeOn`, nên dựa vào `SecurityContextHolder` thread-local hoặc `ThreadLocal` tự viết sẽ gây lỗi principal biến mất hay rò ngữ cảnh. Trong controller có thể dùng cơ chế injection principal của Spring WebFlux khi phù hợp; với service reactive, nên truyền dữ liệu cần thiết rõ ràng hoặc dùng `ReactiveSecurityContextHolder`. Không cache `Authentication` theo biến static hoặc lưu toàn cục giữa request.

Nếu ứng dụng có đăng nhập lưu session, so sánh thiết kế cũ với `ServerSecurityContextRepository` và WebFlux `WebSession`; không bê nguyên `HttpSessionSecurityContextRepository` sang. Nếu API cố ý stateless, cân nhắc `NoOpServerSecurityContextRepository` khi đúng cơ chế xác thực và yêu cầu nghiệp vụ, không xóa session chỉ vì thấy chữ “reactive”.

## 7. Authorization nâng cao và method security

Với quyền truy cập dựa trên HTTP method, WebFlux có thể dùng `pathMatchers(HttpMethod.GET, "/api/reports/**")`, rồi đặt rule dành cho ghi bên dưới. Rule cụ thể cần đứng trước `anyExchange`. Với quyền theo dữ liệu sở hữu, servlet custom `AuthorizationManager` phải được chuyển thành `ReactiveAuthorizationManager<AuthorizationContext>`. Giá trị trả về là `Mono<AuthorizationDecision>`; truy vấn cơ sở dữ liệu/quyền theo người dùng nên là reactive hoặc được cô lập đúng cách.

Đoạn minh họa **được chèn trong lambda của `authorizeExchange`**, giả sử có service `accessService.canRead(username, id)` trả về `Mono<Boolean>`:

```java
.pathMatchers("/api/reports/{id}")
.access((authentication, context) ->
        authentication.flatMap(user ->
                accessService
                        .canRead(user.getName(),
                                context.getVariables().get("id"))
                        .map(AuthorizationDecision::new)))
```

Đây là đoạn minh họa ghép policy, **chưa phải class chạy độc lập**. Quyết định khi principal rỗng, service lỗi hoặc publisher rỗng phải được xét rõ ràng; không vô tình biến kết quả rỗng thành quyền truy cập mặc định. Đường này minh họa nơi áp dụng check; logic `canRead` cần kiểm tra quyền thật từ nguồn đáng tin, tránh chỉ so sánh ID tùy ý do client gửi.

Với `@PreAuthorize` ở service, WebFlux cần bật method security reactive:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
class ReactiveMethodSecurityConfig {
}
```

`@EnableMethodSecurity` Servlet không phải bản thay thế tương đương cho Reactor Context. Đối với luồng method security reactive, return type nên là `Mono`/`Flux` hoặc loại reactive được cấu hình hỗ trợ; kiểm tra tình huống method đồng bộ và self-invocation đi vòng qua proxy. Quy tắc ở HTTP layer và method layer đều có thể cần thiết; cấu hình lại chỉ layer HTTP không bảo đảm giữ mọi `@PreAuthorize` cũ.

## 8. CSRF, CORS, login, session và lỗi HTTP khi chuyển

### CSRF

Spring Security WebFlux có CSRF protection, không mặc nhiên bỏ CSRF chỉ vì server dùng WebFlux. Với browser dựa vào cookie/session, tiếp tục bảo vệ các thao tác thay đổi dữ liệu (`POST`, `PUT`, `DELETE`…) và cấp token theo cơ chế reactive. Với API chỉ chấp nhận Bearer token trong Authorization header và không dựa vào credential được browser tự gửi, có thể cân nhắc vô hiệu CSRF **cho phạm vi kiến trúc thực sự không bị CSRF**, sau khi đánh giá luồng xác thực và endpoint:

```java
// Chỉ đặt khi yêu cầu bảo mật của API cho phép.
http.csrf(csrf -> csrf.disable());
```

Không tự động thêm dòng này vào mọi bản migration. Với WebFlux, `ServerCsrfTokenRepository`/`CsrfWebFilter` và cách truyền CSRF token qua cookie/header khác một số API Servlet; nếu SPA dùng cookie, cần đối chiếu phần lưu token và xử lý bảo vệ BREACH.

### CORS

Preflight `OPTIONS` thường chưa có credential. Kiểm tra CORS theo cấu hình WebFlux (`CorsWebFilter`/CORS config reactive hoặc integration qua security DSL) và kiểm thử request từ origin thật. Không sao chép nguyên `CorsFilter` Servlet, `HttpServletRequest` hay `CorsConfigurationSource` của sai package sang pipeline reactive. CORS **không thay thế authorization**: origin được phép không có nghĩa user được phép truy cập API.

### Login, logout và session

Với browser, kiểm tra URL login/logout, trang redirect, cookies (`SameSite`, `Secure`, `HttpOnly`), session timeout, CSRF, saved request và success/failure handlers. Với HTTP Basic/Bearer, xác minh lựa chọn stateless hay session được cấu hình nhất quán. Không tự động bật form login cho API JSON nếu client đang mong `401`; cũng không tự tắt form login nếu sản phẩm vẫn cần browser session.

### 401, 403 và 302

- `401 Unauthorized`: request thiếu hoặc không có credential hợp lệ; HTTP Basic/Bearer thường phát challenge.
- `403 Forbidden`: authentication có hiệu lực nhưng không đủ quyền (có ngoại lệ theo entry point/anonymous configuration).
- `302 Found`: có thể là redirect tới form login trong browser flow; khác với ý nghĩa API client mong muốn.

Nếu phải tự xử lý lỗi, WebFlux dùng các giao diện reactive như `ServerAuthenticationEntryPoint` và `ServerAccessDeniedHandler` thay cho Servlet counterparts. Không trộn handler viết cho `HttpServletResponse` vào WebFlux. Đối chiếu body lỗi, content type và headers `WWW-Authenticate` trên cả các trường hợp không đăng nhập và thiếu quyền.

## 9. Checklist thực thi từng bước trong dự án thật

1. **Chốt policy hiện hành:** liệt kê route, HTTP method, quyền theo role/scope, route public, nhiều chain, form login, OAuth2, session, CSRF/CORS, method security và custom filters. Xác nhận hành vi từ bài test Servlet hiện có trước khi chuyển.
2. **Xác nhận runtime WebFlux:** chọn đúng `spring-boot-starter-webflux`; kiểm tra dependency tree để loại server MVC/Servlet ngoài ý muốn; kiểm tra app chạy dạng reactive.
3. **Tạo cấu hình mới:** thay `@EnableWebSecurity`/`HttpSecurity`/`SecurityFilterChain` bằng `@EnableWebFluxSecurity`/`ServerHttpSecurity`/`SecurityWebFilterChain`; migrate `authorizeHttpRequests` thành `authorizeExchange` với rule tương ứng.
4. **Giữ chọn chain và thứ tự:** chuyển `securityMatcher`, `@Order`, catch-all và các route public; kiểm tra “first matching chain” với các đường dẫn chồng nhau.
5. **Chuyển authentication component:** chọn `ReactiveAuthenticationManager`, `ReactiveUserDetailsService`, `ReactiveJwtDecoder`/opaque introspector, reactive OAuth2 components phù hợp; kiểm tra authorities và error mapping.
6. **Chuyển custom security filter/handlers:** thay Servlet Filter API bằng WebFilter/reactive SPI; kiểm tra vị trí filter, Reactor Context, cách trả lỗi và việc không chặn event loop.
7. **Rà soát bảo vệ browser:** giữ đúng CSRF, CORS, form login, logout, cookie/session, redirect; không đồng loạt tắt bảo vệ khi đổi stack.
8. **Chuyển method security:** dùng `@EnableReactiveMethodSecurity` và test `@PreAuthorize`/`@PostAuthorize` trên các method reactive.
9. **Viết test trước–sau theo ma trận:** public/anonymous, user có quyền, user thiếu quyền, token sai/hết hạn, CSRF thiếu/đúng, CORS preflight, browser login, nhiều chain, policy theo dữ liệu.
10. **Kiểm tra dưới tải:** quan sát latency xác thực, phản hồi 401/403, event-loop blocking, connection pool và context propagation; rollout theo phạm vi nhỏ khi có thể.

Một bảng kiểm thử đủ cụ thể cho mỗi route thường có các cột: request path, HTTP method, credential, authorities, security chain mong đợi, kết quả Servlet trước, kết quả WebFlux sau và nguyên nhân chênh lệch. So sánh cả **policy và đáp ứng HTTP**, không chỉ kiểm tra ứng dụng khởi động được.

## 10. Các lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách tìm và sửa |
| --- | --- | --- |
| `No qualifying bean of type ServerHttpSecurity` hoặc lỗi cấu hình class | App chưa bật WebFlux security, dependency/auto-config không đúng stack | Xác nhận `@EnableWebFluxSecurity`, Boot web application type và các starter. |
| Class `HttpSecurity`/`SecurityFilterChain` vẫn còn trong WebFlux config | Sao chép API Servlet | Tách hẳn cấu hình MVC và reactive; import đúng các class của `.web.server`. |
| Endpoint bị 404 hoặc security không hoạt động như dự kiến | Ứng dụng thực tế vẫn chạy MVC; route chưa được WebFlux đăng ký | Kiểm tra log, dependency tree và controller/router registration trước khi đổ lỗi cho security. |
| `401` với token trông hợp lệ | Reactive decoder/issuer/audience/keys/clock skew sai; thiếu bean/phần cấu hình Resource Server | Bật log có kiểm soát, kiểm tra validator và định dạng Bearer, không log raw token. |
| `403` khi role có vẻ đúng | Nhầm `ROLE_` với `SCOPE_`, nhầm `hasRole` và `hasAuthority` hoặc không chuyển authorities converter | In hoặc assert danh sách authorities **không nhạy cảm** trong test, rồi điều chỉnh rule/mapping. |
| API bị `302` thay vì `401` | Form login hoặc entry point browser đang bật ở chain đó | Phân tách API chain và web chain, chọn entry point phù hợp. |
| POST bị `403` nhưng GET được | Thiếu CSRF token ở flow dùng cookie/session | Xác nhận CSRF policy và gửi token hợp lệ; chỉ tắt khi đúng mô hình bảo mật. |
| Route public vẫn bị bảo vệ | Rule khớp sai thứ tự, chain cụ thể bị catch-all che mất | Kiểm tra `@Order`, `securityMatcher` và thứ tự `pathMatchers`. |
| Principal biến mất sau `flatMap`/`publishOn` | Dùng `SecurityContextHolder` thread-local hoặc dựng publisher sai ngữ cảnh | Dùng Reactor Context/`ReactiveSecurityContextHolder`, test ở pipeline thật. |
| Độ trễ tăng, event loop nghẽn | Custom authenticator/authorization gọi `block()`, JDBC sync hoặc HTTP client blocking | Dùng API reactive, tách blocking work hợp lý và kiểm tra tải. |
| Đang chạy nhưng method `@PreAuthorize` không còn chặn | Chưa bật reactive method security hoặc proxy không bao phủ lời gọi | Chuyển annotation/config, kiểm thử trực tiếp method reactive và self-invocation. |

Có thể bật `logging.level.org.springframework.security=DEBUG` **tạm thời trong môi trường thử nghiệm** để xem tiến trình security và matcher; không dùng TRACE/DEBUG đại trà trong production và không đưa Authorization header, cookie session, bearer token hoặc password vào log. Với lỗi chain không khớp, hãy bắt đầu từ **securityMatcher và thứ tự các bean**; với lỗi authn, đi từ auth mechanism/decoder/manager; với lỗi authz, so sánh authorities đã xác thực và rule đích.

## 11. Những nhầm lẫn cần tránh

- **Đổi tên DSL nhưng để nguyên Servlet filter.** `OncePerRequestFilter` không phải `WebFilter`; đặt sai stack có thể khiến mã không chạy, hoặc lỗi khởi động.
- **Tự thêm `block()` để gọi lại DAO/Auth manager cũ.** Việc này có thể khóa event loop và làm sụp throughput khi tăng concurrency.
- **Giả định principal nằm trong ThreadLocal.** Security context reactive đi theo subscriber context; phải test qua các async boundary.
- **Nhầm matcher của chain với rule phân quyền.** `securityMatcher` chọn chain; `pathMatchers` chọn chính sách trong chain, và rule cụ thể phải đến trước `anyExchange`.
- **Gộp mọi cấu hình vào một chain mà không kiểm tra UI/API.** Chính sách cho form login, Basic/Bearer, session và entry point có thể khác nhau đáng kể.
- **Dùng `permitAll` trên mọi đường dẫn để vượt lỗi migration.** Cách này che mất bug và tạo lỗ hổng phân quyền; hãy kiểm thử và sửa nguyên nhân.
- **Bỏ qua CSRF vì “reactive” hoặc “REST”.** Điều quyết định là client credential có tự được browser gửi hay không và kiến trúc xác thực thực tế.
- **Dựa vào compiler thay cho test security.** Code biên dịch được chưa chứng minh `401`/`403`, scope, role, chain ordering hay session flow còn đúng.

## 12. Tiêu chí hoàn thành migration

Bản chuyển đổi đạt yêu cầu khi: ứng dụng thực sự chạy với WebFlux; mọi request đi qua `SecurityWebFilterChain` dự kiến; rule URL và method security giữ nguyên ý nghĩa; auth manager, user details, JWT/OAuth2 và custom filters có component reactive đúng; không chặn event loop; CSRF/CORS và browser flow được xác nhận; các test `200`/`401`/`403`/`302` phù hợp với thiết kế; và log/metrics không rò credential. Khi một policy không có ánh xạ 1:1 giữa Servlet và WebFlux, phải ghi rõ yêu cầu nghiệp vụ và thiết kế lại component đó thay vì giả định cùng tên API là tương đương.

**Tài liệu tham khảo chính thức:** [WebFlux Security Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html), [Reactive HTTP Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html), [Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html), [Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html), [CSRF trong WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html), [Kiểm thử WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/test/web/).