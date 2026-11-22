# SessionCreationPolicy trong Servlet và quản lý WebSession của WebFlux

## 1. Mục tiêu và phạm vi

Sau bài này, bạn có thể giải thích vì sao HTTP vốn không lưu trạng thái nhưng ứng dụng vẫn duy trì phiên đăng nhập; phân biệt chính sách tạo `HttpSession` trong Spring Security Servlet với việc quản lý `WebSession` trong Spring WebFlux; chọn cấu hình phù hợp cho form login và API; đọc đúng vai trò của `SecurityContextRepository`; và kiểm tra một ứng dụng có thật sự dùng session để nhớ người dùng qua nhiều request hay không.

**Phạm vi:** Spring Security trên Servlet và WebFlux, Java 17+, cấu hình `SecurityFilterChain` / `SecurityWebFilterChain` kiểu lambda (Spring Security 6/7). Các ví dụ Servlet và WebFlux là **hai ứng dụng Spring Boot riêng**, không ghép chung hai web starter vào một ứng dụng mẫu.

## 2. Ba thứ dễ bị nhầm: session, cookie và SecurityContext

- **HTTP session** là trạng thái gắn với một người dùng hoặc một client qua nhiều HTTP request, thường giữ ở phía máy chủ. Trình duyệt thường chỉ lưu **session ID** trong cookie rồi gửi ID đó ở request tiếp theo. Cookie chứa ID không có nghĩa là toàn bộ thông tin đăng nhập nằm trong cookie.
- **`SecurityContext`** chứa `Authentication` (principal, authorities, trạng thái xác thực). Spring Security cần quyết định có lưu và khôi phục context đó qua các request hay không.
- **Session ứng dụng** có thể còn lưu giỏ hàng, lựa chọn giao diện hoặc trạng thái workflow. Tắt việc lưu `SecurityContext` vào session không tự động cấm các thành phần ứng dụng sử dụng session.

Trong Servlet, đối tượng phiên chuẩn là `jakarta.servlet.http.HttpSession`, cookie thường mang tên `JSESSIONID` (tùy container và cấu hình). Trong WebFlux, hợp đồng tương đương là `org.springframework.web.server.WebSession`, cookie mặc định của `CookieWebSessionIdResolver` mang tên `SESSION`. **Hai loại session này không phải cùng một API**.

Luồng phiên điển hình:

1. Client truy cập trang cần đăng nhập; security chain xác định chưa được xác thực.
2. Người dùng đăng nhập thành công; ứng dụng lưu `SecurityContext` theo cơ chế đã cấu hình.
3. Phản hồi gửi một session ID cho client (thường qua `Set-Cookie`).
4. Client gửi cookie ở request sau; security chain nạp lại `SecurityContext`.
5. Đăng xuất hoặc hết hạn phiên làm context cũ không còn sử dụng được.

Với API xác thực **mỗi request** bằng một bearer token trong header `Authorization`, bước 2–4 có thể không cần diễn ra. Lúc đó tính hợp lệ của token được kiểm tra lại ở mỗi request.

## 3. Servlet: bốn giá trị của SessionCreationPolicy

`org.springframework.security.config.http.SessionCreationPolicy` quy định cách **Spring Security Servlet** tạo hoặc sử dụng `HttpSession`.

| Giá trị | Spring Security có tạo HttpSession không? | Có dùng session sẵn có cho SecurityContext không? | Cách hiểu |
| --- | --- | --- | --- |
| `ALWAYS` | Có, chủ động bảo đảm có session | Có | Dành cho trường hợp yêu cầu tạo phiên sớm |
| `IF_REQUIRED` | Chỉ khi cần | Có | Phù hợp luồng đăng nhập web có phiên; thường là lựa chọn mặc định |
| `NEVER` | Không chủ động tạo theo chính sách này | Có, nếu đã tồn tại | Không đồng nghĩa với stateless |
| `STATELESS` | Không tạo để lưu xác thực | Không đọc `SecurityContext` từ `HttpSession` | Phù hợp xác thực độc lập từng request |

Các giá trị này mô tả **phạm vi Spring Security**. Controller gọi `request.getSession()`, JSP, CSRF repository, request cache, session-scoped bean hay thư viện khác vẫn có thể tạo `HttpSession` tùy cấu hình. Vì vậy, **thấy `Set-Cookie: JSESSIONID` chưa đủ để kết luận `STATELESS` bị Spring Security bỏ qua**: cần xác định bộ phận nào tạo session và session có được dùng để khôi phục danh tính hay không.

### 3.1. ALWAYS và IF_REQUIRED

`ALWAYS` sử dụng cơ chế tạo session sớm (ví dụ `ForceEagerSessionCreationFilter`). `IF_REQUIRED` chỉ phát sinh session khi một nhu cầu thực sự xuất hiện, ví dụ cần giữ đăng nhập sau form login. Ngay cả `IF_REQUIRED`, một request công khai đơn giản có thể không tạo session.

`IF_REQUIRED` phù hợp với website đăng nhập bằng form, cần nhận ra người dùng ở lần tải trang tiếp theo mà không nhập lại mật khẩu. Không nên đổi sang `ALWAYS` chỉ để khắc phục lỗi mất đăng nhập: trước tiên kiểm tra cookie, SecurityContext repository và thao tác lưu context.

### 3.2. NEVER và STATELESS khác nhau ở đâu?

Giả sử client gửi `JSESSIONID=abc` đã tồn tại và session phía server lưu một `SecurityContext` hợp lệ:

- Với `NEVER`, Spring Security có thể sử dụng session đó và khôi phục danh tính.
- Với `STATELESS`, Spring Security không sử dụng `HttpSession` để lấy `SecurityContext`; request phải được xác thực bằng cơ chế đang cấu hình (chẳng hạn bearer token hoặc HTTP Basic).

`NEVER` cũng **không bảo đảm toàn bộ ứng dụng không tạo session**. Tài liệu Spring Security nêu tình huống request cache lưu request cần đăng nhập vào session. Nếu muốn tránh, kiểm tra `HttpSessionRequestCache` và cân nhắc `NullRequestCache` / tắt request cache ở security chain thích hợp.

### 3.3. SecurityContextRepository mới là điểm nối giữa các request

Các thành phần chính ở Servlet:

- `SecurityContextHolder`: giữ context phục vụ xử lý request đang chạy (thường gắn với thread theo chiến lược mặc định).
- `HttpSessionSecurityContextRepository`: lưu/đọc context thông qua `HttpSession`.
- `RequestAttributeSecurityContextRepository`: giữ context trong cùng request, hữu ích khi có dispatch như ERROR.
- `DelegatingSecurityContextRepository`: ủy quyền cho nhiều repository; trong Spring Security 6, cấu hình mặc định kết hợp request attribute và HTTP session.
- `NullSecurityContextRepository`: không lưu/đọc context giữa các request. Cấu hình `SessionCreationPolicy.STATELESS` làm Spring Security chọn repository phù hợp kiểu này và không lưu request vào session.

Ở cấu hình Spring Security 6 trở lên, `SecurityContextHolderFilter` mặc định **đọc** context; nó không tự lưu mọi thay đổi. Các cơ chế đăng nhập do Spring Security cung cấp xử lý việc lưu theo luồng của chúng. Nếu **tự viết** filter/controller để gán `Authentication`, bạn phải lưu context tường minh qua `SecurityContextRepository.saveContext(...)` nếu muốn duy trì qua request sau. Chỉ gọi `SecurityContextHolder.setContext(...)` không đủ cho custom login.

## 4. Ví dụ Servlet: một website có phiên và một API stateless

Tạo ứng dụng Spring Boot với Java 17+, dependencies `spring-boot-starter-web` và `spring-boot-starter-security`. Ba file sau cùng package `example.servlet`; sử dụng in-memory user và `{noop}` **chỉ để học**, không dùng mật khẩu lưu dạng rõ trong sản phẩm.

**`ServletSessionsApplication.java`**

~~~java
package example.servlet;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ServletSessionsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ServletSessionsApplication.class, args);
    }
}
~~~

**`ServletSecurityConfig.java`**

~~~java
package example.servlet;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class ServletSecurityConfig {
    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(a -> a.anyRequest().authenticated())
            .sessionManagement(s -> s
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .requestCache(c -> c.disable())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain pages(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(a -> a
                .requestMatchers("/", "/public").permitAll()
                .anyRequest().authenticated())
            .sessionManagement(s -> s
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .formLogin(Customizer.withDefaults())
            .build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("demo")
                .password("{noop}demo123")
                .roles("USER")
                .build()
        );
    }
}
~~~

**`ServletEndpoints.java`**

~~~java
package example.servlet;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ServletEndpoints {
    @GetMapping({"/", "/public"})
    String publicPage() {
        return "public";
    }

    @GetMapping("/private")
    String privatePage(Authentication auth) {
        return "web user=" + auth.getName();
    }

    @GetMapping("/api/me")
    String apiMe(Authentication auth) {
        return "api user=" + auth.getName();
    }
}
~~~

**Kiểm tra theo thứ tự:**

~~~bash
# API thiếu Authorization: bị từ chối (thường là HTTP 401).
curl -i http://localhost:8080/api/me

# API có HTTP Basic: được xác thực trong chính request này.
curl -i -u demo:demo123 http://localhost:8080/api/me

# Trang web chưa login: chuyển hướng tới trang đăng nhập.
curl -i http://localhost:8080/private
~~~

Ở lệnh thứ hai, phần thân phản hồi là `api user=demo`. Không gửi `Authorization` ở request API tiếp theo thì không được nhớ đăng nhập từ request trước. Luồng `/private` sử dụng form login (mở `http://localhost:8080/login` trong trình duyệt); sau đăng nhập thành công, trình duyệt thường nhận `JSESSIONID` và tiếp tục truy cập `/private` bằng cookie đó.

**Về CSRF:** ví dụ giữ bảo vệ CSRF mặc định. `STATELESS` **không đồng nghĩa** với vô hiệu hóa CSRF. Đặc biệt nếu trình duyệt tự gửi HTTP Basic hoặc cookie, CSRF vẫn là điều cần xem xét cho thao tác thay đổi dữ liệu. Chỉ bỏ qua/tắt CSRF trên API khi đã đánh giá cơ chế credential, client và bề mặt tấn công cụ thể; API chỉ dùng bearer token trong header do client chủ động gắn là trường hợp thường gặp.

### 4.1. Khi nào chọn giá trị nào?

- Website form login sử dụng cookie: thường `IF_REQUIRED`; lưu đăng nhập bằng session.
- API được thiết kế xác thực từng request: `STATELESS`, cùng cơ chế xác thực phù hợp (ví dụ resource server kiểm tra bearer token).
- Tích hợp cần tận dụng session do hệ thống khác tạo nhưng Spring Security không được chủ động tạo: cân nhắc `NEVER` và kiểm tra request cache.
- Nghiệp vụ yêu cầu mở session ngay từ request đầu: `ALWAYS`, nhưng phải có lý do cụ thể.

`SessionCreationPolicy` **không tự cấu hình** timeout, giới hạn số phiên đăng nhập đồng thời, cookie flags, chống session fixation hoặc cơ chế chia sẻ session giữa nhiều máy chủ. Đó là các cấu hình riêng. Đối với Servlet hiện đại, Spring Security thường đổi session ID khi xác thực thành công (`changeSessionId`) để giảm rủi ro session fixation.

## 5. WebFlux: WebSession hoạt động theo cơ chế khác

Spring WebFlux sử dụng non-blocking API: lấy session qua `ServerWebExchange.getSession()` (trả về `Mono<WebSession>`), không thao tác trực tiếp với Servlet `HttpSession`. `WebSession` có các khả năng:

| API | Ý nghĩa |
| --- | --- |
| `getAttributes()`, `getAttribute(name)` | Đọc/ghi dữ liệu phiên theo key |
| `start()`, `isStarted()` | Chủ động bắt đầu phiên và kiểm tra trạng thái |
| `getMaxIdleTime()`, `setMaxIdleTime(Duration)` | Xem/đổi thời gian nhàn rỗi tối đa |
| `changeSessionId()` | Đổi ID phiên (trả về `Mono<Void>`) |
| `invalidate()` | Vô hiệu hóa phiên và xóa dữ liệu (trả về `Mono<Void>`) |
| `save()` | Lưu vào store; framework thường tự gọi trước khi commit response |

**Điểm then chốt:** chỉ gọi `exchange.getSession()` không nhất thiết tạo phiên đã được lưu hay gửi cookie. `WebSession` được **start** khi gọi `start()` hoặc khi thêm thuộc tính vào session; chỉ phiên đã start mới được lưu như phiên mới và gửi session ID. `WebSession.save()` thường do framework thực hiện ở cuối request; ứng dụng thông thường không cần gọi thủ công.

Các thành phần phía dưới:

1. `WebSessionManager` điều phối việc tìm/tạo session; triển khai thông dụng là `DefaultWebSessionManager`.
2. `WebSessionIdResolver` đọc/ghi session ID, mặc định `CookieWebSessionIdResolver` với cookie `SESSION`.
3. `WebSessionStore` giữ dữ liệu phiên; `DefaultWebSessionManager` mặc định dùng `InMemoryWebSessionStore`, phù hợp ứng dụng một instance hơn là cluster nhiều node.
4. Spring Session có thể tích hợp `WebSessionManager` với `ReactiveSessionRepository` (ví dụ Redis) để chia sẻ phiên giữa các instance.

Cookie timeout (`Max-Age`) và thời gian hết hạn phía server (`maxIdleTime`) là hai khái niệm khác nhau. Cookie còn tồn tại không bảo đảm server chưa xóa/cho hết hạn phiên.

### 5.1. WebFlux không dùng SessionCreationPolicy

`SessionCreationPolicy` nằm trong cấu hình Servlet `HttpSecurity`; **không đem enum này áp vào `ServerHttpSecurity` của WebFlux**. Thay vào đó, quản lý việc lưu `SecurityContext` qua:

- `ServerSecurityContextRepository`: hợp đồng đọc/lưu `SecurityContext` giữa các request (`Mono<SecurityContext> load(exchange)` và `Mono<Void> save(exchange, context)`).
- `WebSessionServerSecurityContextRepository`: lưu `SecurityContext` trong `WebSession`; khi lưu context có đổi session ID để chống session fixation.
- `NoOpServerSecurityContextRepository`: không lưu/khôi phục context qua request. Thích hợp xác thực stateless.
- `ReactiveSecurityContextHolder`: cung cấp context trong **Reactor Context** cho chuỗi reactive của request; đây **không phải** nơi lưu phiên qua nhiều request.
- `ReactorContextWebFilter`: lấy `SecurityContext` từ repository để khởi tạo Reactor Context.

**Một tinh tế cấu hình:** `ServerHttpSecurity.securityContextRepository(repo)` thiết lập repository để `ReactorContextWebFilter` **đọc** context. Các `AuthenticationWebFilter` (ví dụ form login hoặc HTTP Basic) có repository **riêng** để **lưu** authentication khi xác thực thành công. Vì thế khi chuyển một luồng đăng nhập từ stateful sang stateless, cần xem cả nơi đọc **và** nơi lưu:

- Form login trên WebFlux mặc định dùng `WebSessionServerSecurityContextRepository` để lưu authentication.
- HTTP Basic WebFlux mặc định dùng `NoOpServerSecurityContextRepository` để lưu authentication.
- Nếu custom authentication filter, cấu hình repository của filter đó cho đúng. Chỉ đổi global reader chưa chắc đủ để bảo đảm không có chỗ vẫn ghi context vào session.

Đối với OAuth2/OIDC login, session còn có thể phục vụ luồng redirect, authorization request và tương quan callback. Không áp dụng máy móc NoOp cho toàn bộ luồng đăng nhập tương tác mà không kiểm tra các thành phần liên quan.

## 6. Ví dụ WebFlux: API HTTP Basic không nhớ SecurityContext

Tạo **ứng dụng Spring Boot riêng** với Java 17+, `spring-boot-starter-webflux` và `spring-boot-starter-security` (không thêm `spring-boot-starter-web` vào mẫu này). Các file sau cùng package `example.reactive`.

**`ReactiveSessionsApplication.java`**

~~~java
package example.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveSessionsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveSessionsApplication.class, args);
    }
}
~~~

**`ReactiveSecurityConfig.java`**

~~~java
package example.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {
    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        var noSessionContext = NoOpServerSecurityContextRepository.getInstance();

        return http
            .authorizeExchange(a -> a
                .pathMatchers("/public").permitAll()
                .anyExchange().authenticated())
            .securityContextRepository(noSessionContext)
            .httpBasic(b -> b.securityContextRepository(noSessionContext))
            .formLogin(f -> f.disable())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails user = User.withUsername("demo")
            .password("{noop}demo123")
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(user);
    }
}
~~~

Ở đây `securityContextRepository(noSessionContext)` kiểm soát khôi phục context, còn `httpBasic(b -> b.securityContextRepository(noSessionContext))` kiểm soát lưu context của cơ chế HTTP Basic. Dòng thứ hai là minh họa chủ động; HTTP Basic của WebFlux đã mặc định dùng NoOp. Form login được tắt để tránh một luồng đăng nhập lưu context vào WebSession. Các request sử dụng Basic vẫn được xác thực riêng lẻ.

**`ReactiveEndpoints.java`**

~~~java
package example.reactive;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class ReactiveEndpoints {
    @GetMapping("/public")
    Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping("/me")
    Mono<String> me(Authentication auth) {
        return Mono.just("reactive user=" + auth.getName());
    }

    @GetMapping("/visits")
    Mono<String> visits(ServerWebExchange exchange) {
        return exchange.getSession().map(session -> {
            Integer previous = session.getAttribute("visits");
            int next = previous == null ? 1 : previous + 1;
            session.getAttributes().put("visits", next);
            return "visits=" + next;
        });
    }
}
~~~

Lưu ý: endpoint `/visits` **cố ý tạo dữ liệu WebSession của ứng dụng** bằng `getAttributes().put(...)`. Điều này cho thấy **NoOp SecurityContext repository chỉ ngăn lưu danh tính vào WebSession; nó không cấm controller tự dùng WebSession**.

Thử nghiệm:

~~~bash
# Thiếu credentials: 401.
curl -i http://localhost:8080/me

# Credentials đúng: body "reactive user=demo".
curl -i -u demo:demo123 http://localhost:8080/me

# Cùng tài khoản, nhưng không gửi Authorization: vẫn 401.
curl -i http://localhost:8080/me

# Controller dùng WebSession: response thường cấp cookie SESSION.
curl -i -u demo:demo123 -c cookies.txt http://localhost:8080/visits
curl -i -u demo:demo123 -b cookies.txt http://localhost:8080/visits
~~~

Kết quả hai request `/visits` khi giữ cookie lần lượt là `visits=1` và `visits=2` (nếu server còn giữ phiên). Đây là state của **ứng dụng**, không phải trạng thái đăng nhập được giữ lại: nếu request thứ hai bỏ `Authorization`, security chain vẫn từ chối do `/visits` yêu cầu xác thực.

**CSRF:** cấu hình mẫu không tắt CSRF; các thao tác ghi (POST/PUT/DELETE) qua client tương thích cookie/HTTP Basic cần chiến lược CSRF phù hợp. Chỉ dùng endpoint GET để thử nghiệm.

### 6.1. Nếu muốn form login WebFlux có phiên

Thay cấu hình `SecurityWebFilterChain` ở ví dụ trước bằng biến thể dưới đây trong **ứng dụng WebFlux dùng trang đăng nhập**:

~~~java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    var repo = new WebSessionServerSecurityContextRepository();

    return http
        .authorizeExchange(a -> a
            .pathMatchers("/public").permitAll()
            .anyExchange().authenticated())
        .securityContextRepository(repo)  // đọc SecurityContext ở request sau
        .formLogin(f -> f.securityContextRepository(repo))  // lưu sau login
        .httpBasic(b -> b.disable())
        .build();
}
~~~

Thêm import `org.springframework.security.web.server.context.WebSessionServerSecurityContextRepository`. Cùng một repository được đặt cho reader và form-login filter. Khi đăng nhập thành công, repository lưu `SecurityContext` vào `WebSession`; trình duyệt gửi lại cookie `SESSION` để được xác thực ở request tiếp theo. Luồng WebFlux form login thông thường đã sử dụng kiểu repository này; cấu hình tường minh giúp nhận rõ nơi lưu và đọc.

### 6.2. Tùy biến cookie và thời gian sống của WebSession

Ví dụ đổi tên cookie và đặt flags của cookie WebFlux (thêm vào một lớp `@Configuration`):

~~~java
@Bean
WebSessionIdResolver webSessionIdResolver() {
    CookieWebSessionIdResolver resolver = new CookieWebSessionIdResolver();
    resolver.setCookieName("APPSESSION");
    resolver.addCookieInitializer(cookie -> cookie
        .httpOnly(true)
        .secure(true)
        .sameSite("Lax"));
    return resolver;
}
~~~

Imports: `org.springframework.web.server.session.WebSessionIdResolver` và `org.springframework.web.server.session.CookieWebSessionIdResolver`. Với `secure(true)`, cookie chỉ được gửi qua HTTPS: triển khai cần TLS/HTTPS thật, không suy luận từ request HTTP local. `SameSite=Lax` giúp giảm một số tình huống cross-site, **không thay thế** việc đánh giá CSRF. `setCookieMaxAge(...)` điều khiển thời gian sống của cookie phía browser; `WebSession.setMaxIdleTime(Duration)` và cấu hình session store điều khiển hết hạn phiên ở server.

Khi dùng nhiều instance, `InMemoryWebSessionStore` cục bộ có thể khiến client “mất phiên” nếu request đi sang node khác. Xem xét Spring Session với `ReactiveSessionRepository` (như Redis), phù hợp với yêu cầu vận hành, TTL và serialization của hệ thống.

## 7. So sánh trực tiếp Servlet và WebFlux

| Câu hỏi | Servlet | WebFlux |
| --- | --- | --- |
| Đối tượng phiên | `HttpSession` | `WebSession` |
| Lấy phiên từ request | `request.getSession(false)` / `getSession()` | `exchange.getSession(): Mono<WebSession>` |
| Cookie mặc định thường gặp | `JSESSIONID` | `SESSION` |
| Chính sách tạo session của Spring Security | `SessionCreationPolicy` | Không dùng enum Servlet này |
| Repository giữ đăng nhập có phiên | `HttpSessionSecurityContextRepository` | `WebSessionServerSecurityContextRepository` |
| Repository không giữ đăng nhập | `NullSecurityContextRepository` | `NoOpServerSecurityContextRepository` |
| Nơi đọc SecurityContext trong request | `SecurityContextHolder` / filter | `ReactiveSecurityContextHolder` / `ReactorContextWebFilter` |
| Dữ liệu session có thể nằm ở đâu? | Servlet container hoặc Spring Session | `WebSessionStore` hoặc Spring Session reactive |
| Mô hình API xác thực từng request | `STATELESS` + cơ chế xác thực thích hợp | NoOp reader + NoOp của từng authentication filter cần thiết |

Hai stack đều có thể xây dựng ứng dụng **stateful** hoặc **stateless về đăng nhập**. Việc WebFlux “reactive” không tự mang nghĩa không có session.

## 8. Tình huống lỗi thường gặp và cách chẩn đoán

**Lỗi 1 — “Đã đặt NEVER nhưng vẫn thấy JSESSIONID”.** `NEVER` vẫn dùng session có sẵn, còn request cache/JSP/controller có thể tạo session. Kiểm tra request cache, nơi gọi `getSession()` và luồng redirect sang login. Nếu mục tiêu là API không lưu xác thực, xem `STATELESS` thay vì chỉ đổi `NEVER`.

**Lỗi 2 — “STATELESS mà response có Set-Cookie”.** Không suy ra SecurityContext đang được lưu trong HttpSession. Xác định cookie do đâu phát sinh (session ứng dụng, CSRF, reverse proxy, thành phần khác); sau đó thử request kế tiếp **chỉ có cookie nhưng không có credential**. Nếu vẫn được nhận diện là người dùng đã đăng nhập, điều tra lại security chain, repository và các cơ chế xác thực khác.

**Lỗi 3 — “Custom login thành công nhưng request sau mất đăng nhập”.** Trong Servlet Spring Security 6/7, việc chỉ `SecurityContextHolder.setContext(context)` có thể không lưu context. Gọi `securityContextRepository.saveContext(context, request, response)` tại nơi xác thực thành công theo đúng luồng tùy biến. Với WebFlux, phải cấu hình repository lưu của `AuthenticationWebFilter` và repository đọc cho `ReactorContextWebFilter`.

**Lỗi 4 — “WebFlux đã đặt NoOp nhưng vẫn có SESSION”.** NoOp chỉ liên quan `SecurityContext`. Tìm code gọi `getSession()` rồi `start()`/`getAttributes().put(...)`, các cơ chế CSRF/form login và framework khác có thể tạo `WebSession`.

**Lỗi 5 — “Mất phiên ngẫu nhiên khi chạy nhiều node”.** Kiểm tra session store có chia sẻ hay không, cookie có được chuyển tiếp không, thuộc tính `Secure`/`SameSite`/domain/path, TTL ở server, đồng hồ và quy tắc sticky session. Với WebFlux, cân nhắc Spring Session reactive thay vì memory store cục bộ nếu cần session dùng chung.

**Lỗi 6 — “Tắt CSRF vì STATELESS”.** Stateless chỉ nói về lưu trạng thái xác thực phía server. Trình duyệt có thể tự gắn HTTP Basic, cookie hoặc credentials khác vào request. Quyết định bảo vệ CSRF dựa trên cách client mang credentials, không dựa duy nhất vào tên policy.

**Lỗi 7 — “WebSession được trả về tức là cookie đã tạo”.** `exchange.getSession()` có thể cho một đối tượng chưa start. Kiểm tra `isStarted()`, tác động của việc thêm attributes và `Set-Cookie` của response. Không gọi `save().block()` trong WebFlux; framework xử lý lưu bất đồng bộ trước khi commit.

## 9. Checklist kiểm tra hành vi thực tế

1. **Xác định stack:** ứng dụng chạy Servlet hay WebFlux? Phải đọc đúng `SecurityFilterChain` hoặc `SecurityWebFilterChain`.
2. **Kiểm tra cơ chế authentication:** form login, Basic, bearer token, OAuth2 login hay custom filter? Mỗi cơ chế có thể lưu/khôi phục khác nhau.
3. **Kiểm tra repository:** Servlet là `SecurityContextRepository`; WebFlux là `ServerSecurityContextRepository`, kể cả repo của từng authentication filter.
4. **Quan sát HTTP:** chụp status, `Set-Cookie`, `Cookie` và `Authorization` ở request kế tiếp; phân biệt “có session ứng dụng” với “đăng nhập được nhớ”.
5. **Thử lại không có credentials:** chỉ gửi session cookie cũ; với API stateless về xác thực, request không được nhận danh tính từ cookie session.
6. **Đăng xuất, hết hạn và scale:** kiểm tra hiệu lực invalidation, TTL phía server, bảo vệ session fixation, Secure/HttpOnly/SameSite và bộ nhớ phiên khi có nhiều instance.
7. **Giữ test độc lập:** kiểm tra stateful web login bằng browser/MockMvc/WebTestClient phù hợp và stateless API bằng requests có/không có header xác thực.

## 10. Câu hỏi tự kiểm tra

**Q1.** `NEVER` có ngăn Spring Security sử dụng `SecurityContext` nằm trong `HttpSession` đã tồn tại không? **Không.** Nó có thể dùng session đã có; `STATELESS` mới tránh dùng session để lấy context.

**Q2.** Vì sao hai request có cùng HTTP Basic credentials vẫn không cần session? **Vì mỗi request được xác thực lại từ header `Authorization`.**

**Q3.** Trong WebFlux, gọi `exchange.getSession()` có luôn phát `SESSION` cookie không? **Không.** Session mới chỉ được bắt đầu khi gọi `start()` hoặc thêm thuộc tính.

**Q4.** Vì sao `.securityContextRepository(NoOp...)` có thể chưa đủ nếu ứng dụng vẫn bật form login WebFlux? **Vì repository của authentication filter dùng để lưu context có thể cấu hình riêng**; form login mặc định lưu vào WebSession.

**Q5.** Bật Spring Session Redis có tự biến ứng dụng thành stateless không? **Không.** Nó thay cách lưu trữ session, vẫn là session phía server nếu ứng dụng sử dụng.

## Tài liệu tham khảo chính thức

- [Spring Security — Authentication Persistence and Session Management (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — Persisting Authentication (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html)
- [Spring Security — SessionCreationPolicy API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/http/SessionCreationPolicy.html)
- [Spring Security — ServerHttpSecurity API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Security — WebSessionServerSecurityContextRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/WebSessionServerSecurityContextRepository.html)
- [Spring Framework — WebSession API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebSession.html)
- [Spring Framework — DefaultWebSessionManager API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/session/DefaultWebSessionManager.html)
- [Spring Session — WebSession Integration](https://docs.spring.io/spring-session/reference/web-session.html)
