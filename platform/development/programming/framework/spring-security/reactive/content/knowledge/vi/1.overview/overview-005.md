# Ranh giới giữa bảo mật Reactive và bảo mật Servlet trong Spring Security

## 1. Hiểu đúng ranh giới

Spring Security có cùng mục tiêu trên cả hai nền tảng: xác thực (authentication) người gọi, kiểm tra quyền (authorization), bảo vệ request và cung cấp danh tính cho mã nghiệp vụ. Tuy nhiên, **Servlet Security và Reactive Security là hai cách tích hợp khác nhau vào vòng đời xử lý HTTP**. Việc controller cùng dùng `@GetMapping`, cùng trả JSON hoặc cùng chấp nhận JWT không làm cho hai security pipeline có thể hoán đổi.

- **Servlet/MVC**: request đi qua Servlet container, `jakarta.servlet.Filter`, `HttpServletRequest`/`HttpServletResponse`, rồi `DispatcherServlet`. Spring Security dùng `FilterChainProxy` và các `SecurityFilterChain`.
- **Reactive/WebFlux**: request đi qua hạ tầng WebFlux với `ServerWebExchange`, `WebFilter` và reactive publisher (`Mono`/`Flux`). Spring Security dùng `WebFilterChainProxy` và các `SecurityWebFilterChain`. WebFlux thường chạy trên Reactor Netty, nhưng cũng có adapter cho container Servlet hỗ trợ non-blocking I/O.
- **Giống nhau ở mô hình bảo mật**: `Authentication`, `GrantedAuthority`, nguyên tắc least privilege, HTTP Basic, OAuth2/OIDC, JWT, kiểm soát truy cập và chống CSRF. **Khác nhau ở cách gắn chúng vào request, cách truyền context và API cấu hình**.

Một dấu hiệu rất dễ nhầm: dự án Spring MVC thêm `spring-boot-starter-webflux` chỉ để sử dụng `WebClient` vẫn có thể là ứng dụng **Servlet**. Theo mặc định của Spring Boot 3.x, nếu cả `spring-boot-starter-web` và `spring-boot-starter-webflux` đều có mặt, MVC được chọn làm web application type; thêm WebClient không tự chuyển security của server sang reactive. Phải xác định **web stack đang phục vụ inbound request**, thay vì suy đoán từ sự hiện diện của Reactor trên classpath.

## 2. Hai pipeline request hoạt động như thế nào?

### Servlet

```text
HTTP request
  -> Servlet container
  -> DelegatingFilterProxy
  -> FilterChainProxy
  -> SecurityFilterChain phù hợp (các Servlet Filter)
  -> DispatcherServlet / Spring MVC controller
  -> service / dữ liệu
  -> HTTP response
```

Mỗi `SecurityFilterChain` chọn các Servlet Filter cần chạy, ví dụ xử lý authentication, CSRF và authorization. `FilterChainProxy` chọn **chain khớp đầu tiên** theo thứ tự; bên trong chain, các filter chạy theo thứ tự bảo mật được định nghĩa. Filter của Servlet tương tác với request/response thuộc Servlet API, và context người dùng thông thường gắn với luồng xử lý hiện tại.

### Reactive

```text
HTTP request
  -> WebFlux HttpHandler
  -> WebFilterChainProxy
  -> SecurityWebFilterChain phù hợp (các WebFilter)
  -> WebFlux handler / @RestController / RouterFunction
  -> Mono/Flux của service và dữ liệu
  -> HTTP response bất đồng bộ
```

`SecurityWebFilterChain` dùng `ServerWebExchangeMatcher` để chọn chain; các `WebFilter` tham gia dòng xử lý không đồng bộ. Kết quả của mỗi bước có thể hoàn thành sau, trên một thread khác, nên danh tính không thể dựa vào giả định “một request = một thread cố định”. Ở cả hai stack, nếu có nhiều chain thì cần kiểm tra phạm vi matcher và thứ tự ưu tiên; đặt chain quá hẹp có thể khiến một endpoint không đi qua cấu hình dự kiến.

## 3. Bản đồ API: lớp nào thuộc stack nào?

| Mối quan tâm | Servlet Security | Reactive Security |
|---|---|---|
| HTTP abstraction | `HttpServletRequest`, `HttpServletResponse` | `ServerWebExchange` |
| Điểm móc security | Servlet `Filter`, `FilterChainProxy` | `WebFilter`, `WebFilterChainProxy` |
| Chain bảo mật | `SecurityFilterChain` | `SecurityWebFilterChain` |
| DSL cấu hình | `HttpSecurity` | `ServerHttpSecurity` |
| Luật truy cập URL | `authorizeHttpRequests`, `requestMatchers`, `anyRequest` | `authorizeExchange`, `pathMatchers`, `anyExchange` |
| Chọn chain | `RequestMatcher` / `securityMatcher` | `ServerWebExchangeMatcher` / `securityMatcher` |
| Xác thực tùy biến | `AuthenticationManager`, `AuthenticationProvider` | `ReactiveAuthenticationManager` trả `Mono<Authentication>` |
| Tra cứu người dùng | `UserDetailsService` | `ReactiveUserDetailsService` trả `Mono<UserDetails>` |
| Context khi chạy | `SecurityContextHolder` (mặc định `ThreadLocal`) | `ReactiveSecurityContextHolder` (Reactor `Context`) |
| Lưu security context trên web | `SecurityContextRepository`, thường liên quan `HttpSession` | `ServerSecurityContextRepository`, có thể dùng `WebSession` |
| Method security | `@EnableMethodSecurity` | `@EnableReactiveMethodSecurity` |
| Test HTTP thường gặp | `MockMvc` + `spring-security-test` | `WebTestClient` + `spring-security-test` |

Bảng này mô tả **vai trò tương ứng**, không khẳng định hai interface là subtype hoặc có thể ép kiểu qua lại. Chẳng hạn, inject `SecurityFilterChain` vào cấu hình WebFlux không tạo ra `WebFilter` bảo vệ request WebFlux.

## 4. Khác biệt cốt lõi: SecurityContext và luồng thực thi

### Servlet: context gắn với thread

Trong cấu hình Servlet thông thường, Spring Security quản lý `SecurityContext` qua `SecurityContextHolder` với chiến lược mặc định `ThreadLocal`. Bên trong đoạn mã đang chạy trên thread đã được filter bảo mật thiết lập, có thể đọc:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

String username = authentication.getName();
```

*Đây là mảnh mã Servlet minh họa, không phải chương trình Java độc lập.* Cần đảm bảo người gọi đã xác thực và `authentication` khác `null`. Khi công việc chuyển sang `Executor`, `@Async` hoặc thread tự tạo, không được mặc định context sẽ tự đi theo; các cơ chế như `DelegatingSecurityContextExecutor` hỗ trợ truyền context với vòng đời phù hợp. Thao tác thiết lập và dọn context phải do cơ chế bảo mật quản lý, tránh rò rỉ danh tính giữa các request dùng lại thread.

### Reactive: context gắn với subscriber, không cố định ở thread

Reactive Security đặt `SecurityContext` trong **Reactor Context** của chuỗi publisher. Lấy danh tính bên trong pipeline bằng:

```java
// Phương thức thuộc một bean/handler WebFlux; không phải file Java độc lập.
public Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
}
```

Các import cần thiết: `reactor.core.publisher.Mono`, `org.springframework.security.core.context.SecurityContext`, `org.springframework.security.core.Authentication` và `org.springframework.security.core.context.ReactiveSecurityContextHolder`. Nếu không có security context trong subscription, publisher có thể hoàn thành rỗng; API nên đặt chính sách cho trường hợp chưa xác thực ở security chain hoặc xử lý `switchIfEmpty` theo yêu cầu nghiệp vụ.

`Mono`/`Flux` là mô tả công việc; code bên trong được thực thi khi **subscribe**. `publishOn`/`subscribeOn` có thể đổi thread nhưng các operator Reactor vẫn truyền Reactor Context đúng cách trong cùng subscription. Nguy cơ phát sinh khi tự gọi `subscribe()` tách dòng, nhảy sang `CompletableFuture`/callback không được nối với context, hoặc dùng trực tiếp `SecurityContextHolder` trong WebFlux rồi mong gặp đúng identity.

Có thể minh họa việc gắn context cho **test hoặc publisher nội bộ** như sau:

```java
Authentication demo = new TestingAuthenticationToken(
    "alice", "unused", "ROLE_USER"
);

Mono<String> name = ReactiveSecurityContextHolder.getContext()
    .map(context -> context.getAuthentication().getName())
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(demo));

// Nếu subscribe bằng block() trong một chương trình kiểm thử độc lập:
// name.block() -> "alice"
```

*Đây là đoạn minh họa cần Reactor và Spring Security trên classpath; `block()` chỉ được nhắc trong môi trường kiểm thử hoặc chương trình không thuộc event loop.* Không tự tạo `Authentication` từ header tự khai hay input chưa được xác thực để gắn context như cách trên trong production.

## 5. So sánh cấu hình security theo cùng một chính sách

Yêu cầu chung: `/public` mở, `/admin` đòi role `ADMIN`, tất cả endpoint khác cần đăng nhập. Hai đoạn sau **dùng trong hai ứng dụng khác nhau**, chỉ minh họa config class; import và dependency phải khớp stack.

**Servlet / Spring MVC:**

```java
@Configuration
@EnableWebSecurity
class ServletSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

**Reactive / Spring WebFlux:**

```java
@Configuration
@EnableWebFluxSecurity
class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain filterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/public").permitAll()
                .pathMatchers("/admin").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Trong ví dụ: `@Configuration` và `@Bean` thuộc `org.springframework.context.annotation`; `Customizer` thuộc `org.springframework.security.config`. Với Servlet dùng `org.springframework.security.config.annotation.web.builders.HttpSecurity`, `org.springframework.security.web.SecurityFilterChain`, `@EnableWebSecurity`. Với Reactive dùng `org.springframework.security.config.web.server.ServerHttpSecurity`, `org.springframework.security.web.server.SecurityWebFilterChain`, `@EnableWebFluxSecurity`.

- `hasRole("ADMIN")` kiểm tra authority `ROLE_ADMIN` trong cách đặt tên mặc định. Nó không kiểm tra chuỗi `ADMIN` thuần; nếu identity có authorities kiểu OAuth scope, cần `hasAuthority("SCOPE_...")` hoặc chính sách chuyển đổi phù hợp.
- Các rule trong `authorizeHttpRequests`/`authorizeExchange` được xét theo thứ tự. Luật cụ thể đặt trước luật bao quát, và thường nên có `anyRequest`/`anyExchange` quyết định rõ với phần còn lại.
- `securityMatcher` ở cấp chain quyết định request **có vào chain đó không**, còn `requestMatchers` hoặc `pathMatchers` quyết định quyền **sau khi chain đã được chọn**. Khi cần nhiều chain, đặt `@Order` phù hợp và có chain bao phủ các endpoint còn lại.
- Đổi `SecurityFilterChain` thành `SecurityWebFilterChain` là thay cấu trúc tích hợp, kéo theo thay cả matcher, filter, authentication manager, context repository, test fixture và phụ thuộc I/O.

## 6. Ví dụ thực hành WebFlux + Security (Java 17+)

Ví dụ dành cho **một project Spring Boot 3.x/ Spring Security 6.x đã cấu hình plugin Spring Boot và Java 17+**. Thêm hai dependency vào `build.gradle` (Groovy DSL):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Không đưa `spring-boot-starter-web` vào project demo này để tránh Spring Boot ưu tiên MVC. Tạo file `src/main/java/example/security/ReactiveSecurityDemoApplication.java`:

```java
package example.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveSecurityDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveSecurityDemoApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/public").permitAll()
                .pathMatchers("/admin").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-demo"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-demo"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }
}
```

Tạo file `src/main/java/example/security/StatusController.java`:

```java
package example.security;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class StatusController {

    @GetMapping("/public")
    public Mono<String> publicStatus() {
        return Mono.just("public");
    }

    @GetMapping("/private")
    public Mono<String> privateStatus() {
        return Mono.just("private");
    }

    @GetMapping("/admin")
    public Mono<String> adminStatus() {
        return Mono.just("admin");
    }
}
```

Chạy bằng `./gradlew bootRun` (Windows: `gradlew.bat bootRun`) trong project có Gradle wrapper và plugin Spring Boot tương thích. Kiểm tra qua `curl.exe` trên Windows hoặc `curl` trên macOS/Linux:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/private
curl -i -u reader:reader-demo http://localhost:8080/private
curl -i -u reader:reader-demo http://localhost:8080/admin
curl -i -u admin:admin-demo http://localhost:8080/admin
```

Kỳ vọng **mã HTTP** lần lượt `200`, `401`, `200`, `403`, `200`; body thành công lần lượt là `public`, `private` và `admin` tương ứng. Không cam kết toàn bộ header/stdout của `curl -i` giống nhau giữa các phiên bản/server. `401` nghĩa là chưa xác thực; `403` ở đây nghĩa là đã xác thực với role không đủ quyền. Các username/password trên chỉ dùng trong môi trường học tập: production dùng nguồn danh tính thực, lưu hash an toàn, không nhúng mật khẩu vào source và bật HTTPS.

Vì controller trả `Mono<String>` trên hạ tầng WebFlux, response được hoàn thành theo subscription reactive. Tuy nhiên, **trả `Mono` một mình chưa chứng minh hệ thống non-blocking**: một gọi JDBC/JPA đồng bộ hoặc `Thread.sleep` bên trong pipeline vẫn có thể chặn event-loop.

## 7. Authentication, session và CSRF: cùng mục tiêu, khác adapter

**Authentication.** Ở Servlet, xử lý đăng nhập thường đi qua `AuthenticationManager` và các `AuthenticationProvider` đồng bộ; ở WebFlux, API tương ứng dùng `ReactiveAuthenticationManager` với kết quả `Mono<Authentication>`. Truy vấn account theo username sử dụng `UserDetailsService` (Servlet) hoặc `ReactiveUserDetailsService` (Reactive). Khi backend danh tính chỉ hỗ trợ I/O blocking, không biến nó thành non-blocking bằng cách bọc kết quả vào `Mono.just(...)`; cần đánh giá driver/client reactive hoặc cách cô lập blocking có giới hạn.

**Phiên đăng nhập.** Servlet thường gắn session với `HttpSession` và một `SecurityContextRepository` phù hợp. WebFlux có `WebSession` và `ServerSecurityContextRepository` (ví dụ `WebSessionServerSecurityContextRepository`). Hai kiểu context repository/session không thể tùy tiện tráo đổi; stateful login qua cookie khác stateless bearer token về cách lưu trạng thái và vòng đời logout. Không đồng nhất “reactive” với “bắt buộc stateless”: WebFlux vẫn có thể dùng session và form login.

**CSRF.** Spring Security bật CSRF mặc định trên cả Servlet và WebFlux đối với các HTTP method thay đổi trạng thái. Trong WebFlux, `CsrfWebFilter` và cơ chế token của WebFlux được sử dụng; token có thể được lưu trong `WebSession`. Nếu ứng dụng dựa vào cookie/session mà trình duyệt tự gửi, bảo vệ CSRF vẫn cần thiết. Chỉ cân nhắc vô hiệu hóa cho endpoint API khi đã xác nhận mô hình xác thực thực sự không bị trình duyệt tự gắn credential theo kiểu dễ bị CSRF, và đã kiểm tra các flow thực tế; không tắt chỉ vì thấy từ “REST” hoặc “WebFlux”.

**OAuth2 Resource Server / JWT.** Cùng một access token có thể được chấp nhận ở hai loại service nếu **mỗi service** cấu hình xác minh chữ ký, issuer, thời hạn và audience/quyền thích hợp. Servlet resource server dùng builder trên `HttpSecurity` và `JwtDecoder`; WebFlux dùng builder trên `ServerHttpSecurity` và `ReactiveJwtDecoder`. Nếu provider phát scope `read`, Spring Security thường ánh xạ thành authority `SCOPE_read`; đó không phải `ROLE_read`. Gateway xác thực phía ngoài không có nghĩa downstream được tin mọi header tự khai: mỗi trust boundary cần xác minh hoặc có giao thức truyền danh tính đáng tin cậy.

Ví dụ cấu hình **Reactive resource server** (đoạn cấu hình bổ sung, thay cho cơ chế Basic của demo khi dùng JWT thực):

```java
@Bean
SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
    return http
        .authorizeExchange(auth -> auth
            .pathMatchers("/public").permitAll()
            .pathMatchers("/reports/**").hasAuthority("SCOPE_reports.read")
            .anyExchange().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
        .build();
}
```

Điều kiện: có dependency OAuth2 Resource Server/Jose do Spring Boot quản lý, cấu hình issuer đáng tin cậy như `spring.security.oauth2.resourceserver.jwt.issuer-uri` và chính sách claim/audience phù hợp. Đoạn này không thể chạy riêng nếu thiếu các điều kiện trên; không đặt cùng demo Basic như hai `SecurityWebFilterChain` phủ toàn bộ URL mà không định nghĩa thứ tự và matcher rõ ràng.

## 8. Method security và ranh giới bất đồng bộ

Servlet method security thông thường dùng `@EnableMethodSecurity`. Trong ứng dụng WebFlux, dùng `@EnableReactiveMethodSecurity`; cơ chế authorization lấy principal qua Reactor Context. Với phương thức Java theo mô hình reactive, kiểu trả về cần là `Publisher` như `Mono<T>` hoặc `Flux<T>` để method security tích hợp đúng với subscription:

```java
// Trích đoạn thuộc một @Service bean trong ứng dụng đã bật
// @EnableReactiveMethodSecurity; không phải class chạy độc lập.
@PreAuthorize("hasRole('ADMIN')")
public Mono<String> readSensitiveReport() {
    return Mono.just("sensitive");
}
```

Phải import `org.springframework.security.access.prepost.PreAuthorize`, `reactor.core.publisher.Mono` và bật `@EnableReactiveMethodSecurity` trong cấu hình. Việc kiểm soát tại URL và method nên bổ sung nhau: rule URL chặn từ ngoài, rule method bảo vệ logic nghiệp vụ khi có nhiều điểm gọi khác nhau. Không suy diễn rằng annotation `@PreAuthorize` của Servlet sẽ tự động có lifecycle tương đương trong một bean reactive trả giá trị đồng bộ thông thường.

**Ranh giới blocking.** Trên Servlet/MVC, I/O đồng bộ thường tiêu thụ thread của request. Trên WebFlux, một lệnh blocking kéo dài trên Netty event loop có thể ảnh hưởng hàng loạt request. `Schedulers.boundedElastic()` có thể cô lập một số adapter blocking chuyển tiếp, nhưng vẫn dùng thread và tài nguyên; đây là giải pháp tương thích có giới hạn, không thay thế việc đánh giá client/driver và tải hệ thống. Không dùng `.block()` trong web handler/reactive filter để lấy danh tính hoặc gọi service rồi tưởng đã làm Reactive Security đúng.

**Không tách subscription tùy tiện.** Thay vì tự gọi `subscribe()` trong controller và trả về ngay (dễ làm mất mạch lỗi/context và kết quả), hãy **trả lại `Mono`/`Flux`** cho framework, và dùng các operator `flatMap`, `map`, `onErrorResume` trên cùng pipeline. Khi bắt buộc giao việc sang hệ thống ngoài Reactor, cần thiết kế rõ cách truyền identity, thời điểm hết quyền và hủy tác vụ.

## 9. Chọn đúng stack và chuyển đổi cấu hình

Trước khi thêm/chuyển security, hãy trả lời theo thứ tự:

1. **Inbound server là gì?** Spring MVC/`DispatcherServlet` hay WebFlux handler? Kiểm tra dependencies và web application type thực tế; không suy ra chỉ từ `WebClient` hoặc kiểu trả về controller.
2. **Security chain đang xử lý request nào?** Servlet chọn `SecurityFilterChain` và `HttpSecurity`; WebFlux chọn `SecurityWebFilterChain` và `ServerHttpSecurity`. Kiểm tra matcher, `@Order` và fallback chain.
3. **Danh tính đi theo luồng nào?** Servlet thread context và cơ chế async riêng; WebFlux Reactor Context trong subscription. Không dùng `ThreadLocal` để suy luận principal xuyên reactive operators.
4. **Nguồn tài khoản/token có non-blocking không?** Chọn `UserDetailsService`/`ReactiveUserDetailsService` và `AuthenticationManager`/`ReactiveAuthenticationManager` tương ứng; không giấu JDBC blocking sau một `Mono.just`.
5. **Dữ liệu phiên và CSRF là gì?** Cookie/session hay bearer token; xác định rule cho request thay đổi trạng thái, login/logout và lưu context trên đúng stack.
6. **Có quyền bảo vệ ở cả HTTP và method không?** Rà soát `hasRole`, `hasAuthority`, role prefix, mapping JWT scope, anonymous/401/403 và các route fallback.
7. **Test bằng công cụ nào?** Servlet thường `MockMvc` với `spring-security-test`; WebFlux dùng `WebTestClient` gắn Spring Security. Kiểm tra cả unauthenticated, authenticated sai quyền và đúng quyền.

### Tình huống áp dụng

- **Ứng dụng MVC chỉ gọi dịch vụ khác bằng WebClient:** server vẫn Servlet; giữ `SecurityFilterChain`. Cân nhắc Reactor context chỉ trong dòng WebClient riêng, không cấu hình nhầm `SecurityWebFilterChain` cho inbound MVC.
- **Ứng dụng gateway WebFlux chuyển request đến API MVC:** gateway cấu hình reactive security, API phía sau cấu hình servlet security. Token/session không tự “chảy” qua ranh giới HTTP; truyền credential theo giao thức được thiết kế và kiểm tra quyền tại từng service.
- **Di chuyển service MVC sang WebFlux:** thay security chain/DSL, authentication adapter, session/context repository, method-security mode và test; đánh giá tất cả persistence/network clients để xác định đoạn blocking. Chuyển annotation controller mà giữ hạ tầng cũ không phải một đợt chuyển đổi hoàn chỉnh.
- **Nhiều chain cho API và trang web:** một chain bearer-token API và một chain form login chỉ an toàn khi matcher/tính ưu tiên tách bạch, và có chính sách rõ cho route ngoài phạm vi. Không suy luận “chain sau tự bổ sung filter cho chain trước”.

## 10. Kiểm chứng hành vi và các lỗi hay gặp

Một ma trận kiểm thử tối thiểu cho demo ở mục 6:

| Tình huống | Kỳ vọng |
|---|---|
| `GET /public` không credential | `200` |
| `GET /private` không credential | `401` trong cấu hình HTTP Basic của demo |
| `GET /private` với `reader` | `200` |
| `GET /admin` với `reader` | `403` |
| `GET /admin` với `admin` | `200` |
| POST có cookie xác thực nhưng thiếu CSRF token | Bị CSRF protection từ chối khi áp dụng và method là unsafe |
| JWT sai chữ ký, issuer hoặc hết hạn (khi dùng resource server) | Bị từ chối xác thực; không cấp quyền dựa trên claim chưa xác minh |

Trong WebFlux, `WebTestClient` kết hợp `spring-security-test` có thể mô phỏng principal bằng `mockUser()`; khi bind thủ công vào ApplicationContext, cần áp dụng bộ cấu hình `springSecurity()` vào client. Dùng kiểm thử HTTP thật hoặc cấu hình test tích hợp để xác thực filter chain và phản hồi, không chỉ unit-test method trả `Mono`. Với Servlet, `MockMvc` có integration tương ứng.

Những lỗi phổ biến và cách nhận diện:

- **Đặt bean sai stack:** đã cấu hình `SecurityFilterChain` nhưng request WebFlux không được bảo vệ như mong đợi; kiểm tra đúng loại server và dùng `SecurityWebFilterChain` cho WebFlux.
- **Dùng `SecurityContextHolder` bên trong reactive operator:** user đôi khi null hoặc sai khi đổi thread/transaction; lấy context từ `ReactiveSecurityContextHolder` trong cùng subscription.
- **Gọi `.block()`/blocking driver trên event loop:** latency tăng, có thể báo lỗi về blocking call hoặc suy giảm throughput; đánh giá API bất đồng bộ thực sự.
- **Nhầm matcher cấp chain với matcher cấp rule:** một URL rơi ngoài chain khiến policy không được thi hành; có fallback chain và test route biên.
- **Nhầm `ROLE_ADMIN` với `SCOPE_admin`:** authenticated vẫn `403` dù token hợp lệ; xem authorities thực tế và chính sách mapping.
- **Tắt CSRF hàng loạt:** request dùng session/cookie trở nên có nguy cơ bị giả mạo; phân tích mô hình credential trước khi điều chỉnh.
- **Tin header danh tính từ ngoài:** client tự gửi `X-User` không có chữ ký mà backend coi là authenticated; chỉ tin dữ liệu danh tính qua cơ chế đã xác minh.
- **Test sai harness:** test WebFlux không gắn security WebFilter hoặc mock principal chỉ trong một method, khiến test xanh nhưng đường HTTP thực chạy khác; kiểm tra 401/403/200 qua đúng web stack.

## 11. Tự kiểm tra

**Câu 1.** Một ứng dụng có `spring-boot-starter-web` và `spring-boot-starter-webflux` để gọi `WebClient`. Khi chưa ép application type, cần cấu hình loại security chain nào cho endpoint server?

**Đáp án:** Theo lựa chọn mặc định của Spring Boot 3.x, server là MVC/Servlet, dùng `SecurityFilterChain` và `HttpSecurity`.

**Câu 2.** Vì sao `SecurityContextHolder.getContext()` không phải cách chuẩn lấy principal trong WebFlux?

**Đáp án:** `SecurityContextHolder` mặc định dùng `ThreadLocal`, còn Reactive Security giữ context trong Reactor subscription. Cần `ReactiveSecurityContextHolder.getContext()` hoặc cơ chế injection chính thống của WebFlux.

**Câu 3.** WebFlux dùng `Mono` có bảo đảm không còn blocking không?

**Đáp án:** Không. Một hàm JDBC đồng bộ hay `block()` bên trong operator vẫn chặn thread thực thi.

**Câu 4.** Một bearer token JWT có scope `reports.read` nhưng route đòi `hasRole("reports.read")`. Vì sao có thể bị 403?

**Đáp án:** Resource Server thường tạo authority `SCOPE_reports.read`, còn `hasRole` kiểm tra role với tiền tố `ROLE_`. Cần chính sách authority hoặc converter khớp claim đã xác minh.

## Tài liệu chính thức để đào sâu

- [Spring Security – Servlet Security Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security – WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security – Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security – Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Security – Reactive Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Boot – Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- [Spring Security – WebTestClient Authentication Tests](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html)
