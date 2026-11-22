# SecurityFilterChain và SecurityWebFilterChain tại biên của ứng dụng web

> **Trọng tâm:** Spring Security can thiệp vào luồng xử lý **trước khi request đi đến controller/handler**. Trong ứng dụng **Servlet/Spring MVC**, đơn vị cấu hình là `SecurityFilterChain` gồm các Servlet `Filter`, được chọn bởi `FilterChainProxy`. Trong **Spring WebFlux**, đơn vị tương ứng là `SecurityWebFilterChain` gồm các reactive `WebFilter`, được chọn bởi `WebFilterChainProxy`. Hai kiểu chain phục vụ hai mô hình web khác nhau; đừng mang cấu hình hay giả định về thread của một mô hình sang mô hình kia.

Bài học này giới hạn ở **ranh giới HTTP của ứng dụng web**: chain được gắn vào đâu, request được chọn và xử lý thế nào, cách cấu hình nhiều chain, điểm khác nhau giữa Servlet và WebFlux, và cách kiểm tra thật. Không đồng nhất những quy tắc bảo vệ request với phân quyền trên từng tài liệu/nghiệp vụ bên trong service.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Vẽ đúng đường đi của request qua `DelegatingFilterProxy` → `FilterChainProxy` → `SecurityFilterChain` trong Servlet và qua `WebFilterChainProxy` → `SecurityWebFilterChain` trong WebFlux.
2. Phân biệt `HttpSecurity`/**`ServerHttpSecurity`** (builder cấu hình) với chain được tạo ra bởi `build()` (cấu hình thực thi).
3. Phân biệt **chọn chain** (`securityMatcher`) với **chọn rule phân quyền bên trong chain** (`requestMatchers` hoặc `pathMatchers`).
4. Sắp xếp nhiều chain bằng `@Order`, bảo đảm chỉ **chain đầu tiên khớp** được sử dụng, có fallback bảo vệ phần còn lại.
5. Giải thích các nhóm filter xác thực, phân quyền, CSRF, security headers, SecurityContext và sự khác nhau giữa `ThreadLocal`/Reactor Context.
6. Tạo hai ví dụ độc lập Spring MVC và WebFlux bằng Java 17+, có thể kiểm thử `200`, `401`, `403`, rule theo HTTP method và CSRF.
7. Nhận diện lỗi khi cấu hình matcher sai, để request lọt ngoài mọi chain, nhầm authorization filter với nghiệp vụ, hoặc gắn custom filter không đúng vị trí.

## 2. Một khung khái niệm chung

Cả hai mô hình đều tuân theo một trật tự:

```text
HTTP request
    |
    v
Web framework nhận request
    |
    v
Spring Security chọn security chain phù hợp
    |
    +--> Các filter bảo vệ: context, authentication,
    |    exploit protection, authorization, ...
    |
    +--> Nếu thiếu credential hoặc thiếu quyền:
    |        trả challenge/error; handler có thể không chạy
    |
    v
Controller / handler / router function
    |
    v
Service / domain / repository (kiểm tra quyền resource và nghiệp vụ)
    |
    v
HTTP response đi ngược qua chuỗi xử lý
```

**Đây là “biên” an ninh của web request**, vì filter có thể chặn request trước khi code controller được thực thi. Không phải tất cả request đều đi qua mọi filter giống nhau: chain phụ thuộc loại ứng dụng, cấu hình bean, matcher và authentication mechanism.

Bảng đối chiếu nhanh:

| Khía cạnh | Servlet / Spring MVC | Reactive / Spring WebFlux |
| --- | --- | --- |
| HTTP abstraction | `HttpServletRequest`, `HttpServletResponse` | `ServerWebExchange` |
| Đơn vị filter của web framework | Servlet `Filter` + `FilterChain` | Reactive `WebFilter` + `WebFilterChain` |
| Cổng vào Spring Security | `DelegatingFilterProxy` chuyển đến `FilterChainProxy` | `WebFilterChainProxy` trong chuỗi WebFilter |
| Chain được chọn | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Builder | `HttpSecurity` | `ServerHttpSecurity` |
| Rule request | `authorizeHttpRequests` + `requestMatchers` | `authorizeExchange` + `pathMatchers` |
| Chọn chain | `http.securityMatcher(...)` | `http.securityMatcher(ServerWebExchangeMatcher)` |
| Matching | `RequestMatcher` trên Servlet request | `ServerWebExchangeMatcher` trên exchange |
| Authentication | Servlet authentication filters/manager | Reactive authentication web filters/manager |
| Authorization | Ví dụ `AuthorizationFilter` | Ví dụ `AuthorizationWebFilter` |
| Context hiện tại | `SecurityContextHolder` (thường ThreadLocal) | `ReactiveSecurityContextHolder` (Reactor Context) |
| Sản phẩm từ `build()` | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Kiểm thử HTTP | `MockMvc` + Spring Security Test | `WebTestClient` + Spring Security Test |

**Tên gần giống không có nghĩa hai interface thay thế trực tiếp được.** Servlet `Filter` có kiểu `doFilter(request, response, chain)` và mô hình servlet dispatch/thread. Reactive `WebFilter` có kiểu `Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain)`, biểu diễn một chuỗi bất đồng bộ không chặn. Hai loại này không thể dùng lẫn như một class filter Java thông thường.

## 3. SecurityFilterChain trong Servlet: request đi qua đâu?

### 3.1. Sơ đồ thực tế

```text
Servlet container (ví dụ Tomcat)
  |
  +-- Servlet FilterChain
        |
        +-- DelegatingFilterProxy
              | tìm Spring Bean tên springSecurityFilterChain
              v
           FilterChainProxy
              |
              +-- chọn SecurityFilterChain đầu tiên whose matcher matches
              |      (A) /api/**  -> filters cho API
              |      (B) /**      -> filters fallback
              |
              +-- Filter 1: security context / exploit protections ...
              +-- Filter 2: authentication, ...
              +-- Filter 3: authorization, ...
              |
              +-- Cho phép đi tiếp
                    |
                    v
               DispatcherServlet
                    |
                    v
               HandlerMapping -> Controller
```

`DelegatingFilterProxy` là cầu nối giữa lifecycle filter do Servlet container quản lý và bean trong Spring `ApplicationContext`. Bean `springSecurityFilterChain` thực tế thường là `FilterChainProxy`, bản thân nó là một Servlet `Filter`. Nó chọn đúng một `SecurityFilterChain` cho request rồi gọi các filter của chain đó theo thứ tự đã được framework thiết lập.

Điểm cần nhớ:

- `FilterChainProxy` là bộ **điều phối các chain**; `SecurityFilterChain` là **tập filter cụ thể** gắn với một matcher. `SecurityFilterChain` không phải một HTTP endpoint hay một controller.
- Một `FilterChainProxy` có thể quản lý nhiều `SecurityFilterChain`; chỉ **chain đầu tiên khớp request** được sử dụng. Các chain phía sau **không cộng dồn** bảo vệ lên chain trước.
- Nếu **không chain nào khớp**, request không chịu Spring Security theo các chain đó (dù Servlet filter khác có thể tồn tại). Không nên chỉ định `securityMatcher("/api/**")` cho chain duy nhất rồi nghĩ mọi URL khác tự bị chặn.
- `FilterChainProxy` có các công việc nền như áp dụng `HttpFirewall` và dọn `SecurityContext` trong luồng Servlet. Không bỏ qua cơ chế này bằng việc tự đăng ký security filter theo cách tùy tiện.
- `HttpSecurity` là **builder** dùng khi khởi tạo bean; `http.build()` tạo cấu hình filter chain. Không nhầm nó với handler thực thi mỗi request.

### 3.2. Authentication và authorization trong chuỗi

Một flow điển hình có các nhóm filter ở các vị trí thích hợp:

```text
HTTP request
    |
    +-- SecurityContextHolderFilter (đọc context / thiết lập cách truy xuất)
    +-- CsrfFilter (kiểm tra token trên request cần CSRF)
    +-- cơ chế xác thực (ví dụ BasicAuthenticationFilter)
    +-- AnonymousAuthenticationFilter (nếu không có authentication)
    +-- ExceptionTranslationFilter (xử lý lỗi security)
    +-- AuthorizationFilter (áp dụng request authorization)
    v
DispatcherServlet
```

Đây là **minh họa trách nhiệm**, không phải danh sách đầy đủ hoặc thứ tự bất biến của mọi phiên bản/cấu hình. Một chain có thể có thêm hoặc bỏ bớt filter (login, session, bearer token, remember-me, logout, OAuth2, headers...). Filter order quan trọng, đặc biệt khi thêm custom filter.

Nếu anonymous đi vào endpoint yêu cầu authenticated, thường nhận `401` hoặc redirect đến login tùy `AuthenticationEntryPoint`. Nếu user đã xác thực nhưng không đủ authority, thường nhận `403`. Cần kiểm tra thực tế vì entry point, request cache và cấu hình khác có thể làm response thay đổi.

### 3.3. Ba vùng matching dễ nhầm

```java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**") // 1. Chain này áp dụng cho request nào?
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/report")
                .hasAuthority("REPORT_READ") // 2. Rule bên trong chain
            .anyRequest().denyAll()           // 3. Các request còn lại CỦA chain
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

- `securityMatcher("/api/**")` chọn **phạm vi cả chain**, không phải rule cho một endpoint.
- `requestMatchers(HttpMethod.GET, "/api/report")` chọn rule khi request **đã vào đúng chain**.
- `anyRequest().denyAll()` chỉ “phủ” các request đã chọn chain này; nó không có tác dụng với `GET /other` nếu `/other` không được chain nào nhận.
- Rule cụ thể nên xếp trước rule tổng quát. Một rule `/api/**.permitAll()` đặt đầu có thể làm các rule hạn chế đặt sau không bao giờ được xét.
- `securityMatcher` và `requestMatchers` có thể hỗ trợ matcher khác nhau tùy môi trường MVC, nhiều servlet hoặc configuration. Kiểm tra semantics đường dẫn, method, servlet path, URL encoding, trailing slash và framework version thay vì đoán từ tên method.

## 4. SecurityWebFilterChain trong WebFlux: tương đương về mục đích, khác cơ chế

### 4.1. Sơ đồ WebFlux

```text
Reactive server (ví dụ Reactor Netty)
   |
   v
Spring WebFlux HTTP handler + chuỗi WebFilter
   |
   v
WebFilterChainProxy
   |
   +-- Chọn SecurityWebFilterChain đầu tiên whose matcher matches
   |      (A) /api/** -> reactive filters API
   |      (B) mọi request còn lại -> fallback
   |
   +-- ReactorContextWebFilter / context integration
   +-- AuthenticationWebFilter (tùy cơ chế)
   +-- CsrfWebFilter (nếu dùng)
   +-- AuthorizationWebFilter
   |
   v
DispatcherHandler -> annotated controller / RouterFunction
   |
   v
Mono / Flux, reactive service
```

Một `SecurityWebFilterChain` gồm reactive `WebFilter`. `ServerHttpSecurity` cấu hình các rule, rồi `build()` tạo chain; `WebFilterChainProxy` chọn **một** chain theo `ServerWebExchangeMatcher`. Các filter reactive tham gia vào pipeline mà request/response được xử lý không đồng bộ.

Sự khác biệt trọng yếu: không dùng `SecurityContextHolder` dựa trên `ThreadLocal` như một nguồn danh tính đáng tin cho logic reactive. Một request WebFlux có thể chuyển thread trong quá trình xử lý. Spring Security dùng `ReactiveSecurityContextHolder` trong **Reactor Context**, và các publisher của luồng xử lý có thể truy xuất context đó. Tính reactive không tự tạo ra phân quyền theo đối tượng; service vẫn cần policy owner/tenant/ACL riêng.

Một ví dụ nhỏ về truy xuất danh tính trong publisher:

```java
// Snippet minh họa trong reactive service có Spring Security;
// các import: reactor.core.publisher.Mono,
// org.springframework.security.core.context.ReactiveSecurityContextHolder,
// org.springframework.security.core.context.SecurityContext.
Mono<String> currentName = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(authentication -> authentication.getName());
```

Nếu không có security context, publisher có thể không phát giá trị. Muốn endpoint yêu cầu đăng nhập thì đặt rule `authenticated()` tại boundary; đừng tự coi một `Mono.empty()` là user mặc định. Truyền context qua scheduler và custom publisher phải giữ đúng Reactor Context; không viết code dùng `block()` trong event loop chỉ để “đọc principal”.

### 4.2. Cấu hình WebFlux tương ứng

```java
@Bean
@Order(1)
SecurityWebFilterChain api(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**"))
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers(HttpMethod.GET, "/api/report")
                .hasAuthority("REPORT_READ")
            .anyExchange().denyAll())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Trong WebFlux:

- `securityMatcher(...)` nhận `ServerWebExchangeMatcher` để chọn **chain**.
- `authorizeExchange(...)` đặt rule cho các request đã vào chain; `pathMatchers(...)` match path/HTTP method trong phạm vi đó.
- `anyExchange().denyAll()` đóng các đường còn lại của **chain đang xét**, không bảo vệ các request lọt ngoài mọi chain.
- Nhiều `SecurityWebFilterChain` cũng cần `@Order` và fallback đủ rộng.
- `@EnableWebFluxSecurity` bật hỗ trợ WebFlux Security trong cấu hình Java khi bạn định nghĩa các chain tường minh.

## 5. Tại sao chain ưu tiên đầu tiên và fallback quan trọng?

Giả sử có ba request:

```text
GET  /api/hello
GET  /profile
POST /api/tasks
```

Và cấu hình:

```text
@Order(1) Chain API:
    match /api/**
    GET /api/hello -> API_READ
    POST /api/tasks -> API_WRITE
    other /api/** -> denyAll

Chain FALLBACK:
    match mọi URL
    GET /public -> permitAll
    GET /profile -> authenticated
    other -> denyAll
```

| Request | Chain được chọn | Quy tắc bên trong |
| --- | --- | --- |
| `GET /api/hello` | API | Cần `API_READ` |
| `POST /api/tasks` | API | Cần `API_WRITE` và các bảo vệ HTTP khác như CSRF khi áp dụng |
| `DELETE /api/hello` | API | `denyAll`, vì method khác không được cấp quyền |
| `GET /profile` | FALLBACK | Cần authenticated |
| `GET /public` | FALLBACK | Công khai |
| `GET /unknown` | FALLBACK | `denyAll` |

**Bẫy 1: Chain API không khớp, fallback của nó cũng không?** Nếu chỉ tạo chain API với `securityMatcher("/api/**")` mà không có chain fallback, những đường ngoài `/api/**` có thể không được Spring Security bảo vệ. Lời gọi `anyRequest().denyAll()` nằm trong chain API không đóng được lỗ hổng đó.

**Bẫy 2: Chain nào có role mạnh hơn sẽ thắng?** Không đúng. Chain được chọn theo **thứ tự bean và matcher**, rồi mới xét policy của chain được chọn. Role/authority không dùng để chọn một chain “thích hợp hơn” về mức bảo vệ.

**Bẫy 3: Fallback có tự áp các filter lên API không?** Không. Khi API chain đã match, fallback không chạy. Nếu muốn các HTTP security headers, cơ chế session hoặc CSRF nhất quán, cần cấu hình từng chain phù hợp hoặc chia sẻ cấu hình chung có kiểm soát.

**Bẫy 4: `permitAll` tương đương “bypass tất cả Spring Security”?** Không. `permitAll` chỉ cho phép request ở bước phân quyền của chain; những filter khác trong chain vẫn có thể chạy. Việc bỏ qua hoàn toàn filter chain là hành động khác, kéo theo mất các lớp bảo vệ như security headers/CSRF theo trường hợp.

## 6. Demo A: Spring MVC / Servlet với hai SecurityFilterChain

Bản demo sau cố định Spring Boot **3.5.16** (Java 17+, Spring Security 6.5.x thuộc BOM của Spring Boot) để mã có thể được tái hiện. **3.5.16 là bản cuối của nhánh 3.5 được phát hành theo hỗ trợ OSS**; khi bắt đầu dự án sản xuất mới năm 2026, cần chọn Spring Boot 4.x/nhánh còn được hỗ trợ và kiểm tra lại API cùng bản vá hiện hành. Chỉ dùng account và mật khẩu ví dụ trong local/test.

### 6.1. Cấu trúc

```text
servlet-chain-demo/
├── pom.xml
└── src/
    ├── main/java/demo/servlet/ServletChainApplication.java
    └── test/java/demo/servlet/ServletChainTests.java
```

**`pom.xml`:**

```xml
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
    <artifactId>servlet-chain-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

### 6.2. Java đầy đủ

Tạo `src/main/java/demo/servlet/ServletChainApplication.java`:

```java
package demo.servlet;

import jakarta.servlet.DispatcherType;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableWebSecurity
public class ServletChainApplication {
    public static void main(String[] args) {
        SpringApplication.run(ServletChainApplication.class, args);
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/hello")
                    .hasAuthority("API_READ")
                .requestMatchers(HttpMethod.POST, "/api/tasks")
                    .hasAuthority("API_WRITE")
                .requestMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            // CSRF được giữ bật; POST cần token nếu thuộc phạm vi CSRF.
            .build();
    }

    @Bean
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                // Chỉ cho phép container dispatch lỗi; không mở endpoint client.
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/profile").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-pass"))
                .authorities("API_READ", "ROLE_USER").build(),
            User.withUsername("writer")
                .password(encoder.encode("demo-pass"))
                .authorities("API_READ", "API_WRITE").build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-pass"))
                .roles("ADMIN").build()
        );
    }
}

@RestController
class ServletRoutes {
    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/profile")
    String profile(Authentication authentication) {
        return "profile:" + authentication.getName();
    }

    @GetMapping("/api/hello")
    String hello(Authentication authentication) {
        return "api:" + authentication.getName();
    }

    @PostMapping("/api/tasks")
    String createTask(Authentication authentication) {
        // Minh họa quyền gọi thao tác. Không ghi database trong demo.
        return "created-by-" + authentication.getName();
    }

    @GetMapping("/api/admin")
    String apiAdmin() {
        return "admin";
    }
}
```

**Phân tích hành vi:**

- `apiChain` có `@Order(1)` và `securityMatcher("/api/**")` nên mọi request API vào đây trước; `fallbackChain` match tất cả đường còn lại. Chỉ một chain được chọn.
- Trong API, `GET /api/hello` yêu cầu `API_READ`, `POST /api/tasks` yêu cầu `API_WRITE`, `GET /api/admin` yêu cầu `ROLE_ADMIN` theo `hasRole("ADMIN")`; method/path chưa liệt kê bị từ chối.
- Ở fallback, `GET /public` công khai nhưng vẫn đi qua filter chain; `GET /profile` cần authentication. Những URL không có rule rõ ràng bị deny.
- Dùng `PasswordEncoder` và in-memory users có credential **chỉ để test**; không dùng mật khẩu mẫu hoặc cấu hình này cho production. `httpBasic` cần HTTPS trên môi trường có lưu lượng thực.
- Cả hai chain giữ CSRF protection theo mặc định Spring Security Servlet. `POST /api/tasks` yêu cầu token CSRF hợp lệ và `API_WRITE` trong ví dụ. CSRF được kiểm tra ở filter trước khi handler chạy, vì vậy mã lỗi có thể là `403` ngay cả khi user đã có quyền API_WRITE.

### 6.3. Kiểm thử với MockMvc

Tạo `src/test/java/demo/servlet/ServletChainTests.java`:

```java
package demo.servlet;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ServletChainTests {
    @Autowired
    MockMvc mvc;

    @Test
    void chainSelectionAndAuthorization() throws Exception {
        // Fallback public: không cần credential.
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));

        // API: anonymous bị challenge HTTP Basic.
        mvc.perform(get("/api/hello"))
            .andExpect(status().isUnauthorized());

        // API_READ cho Alice.
        mvc.perform(get("/api/hello").with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("api:alice"));

        // Admin có ROLE_ADMIN nhưng không có API_READ.
        mvc.perform(get("/api/hello").with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isForbidden());

        // Đường admin API dùng role, không phải permission API_READ.
        mvc.perform(get("/api/admin").with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));

        mvc.perform(get("/api/admin").with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());

        // Fallback cũng bảo vệ /profile.
        mvc.perform(get("/profile"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/profile").with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("profile:alice"));

        // Đúng permission nhưng POST thiếu CSRF token vẫn bị chặn.
        mvc.perform(post("/api/tasks").with(httpBasic("writer", "demo-pass")))
            .andExpect(status().isForbidden());

        // Có CSRF, nhưng Alice không có API_WRITE.
        mvc.perform(post("/api/tasks")
                .with(httpBasic("alice", "demo-pass")).with(csrf()))
            .andExpect(status().isForbidden());

        // Đúng credential + đúng authority + đúng CSRF -> thành công.
        mvc.perform(post("/api/tasks")
                .with(httpBasic("writer", "demo-pass")).with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("created-by-writer"));

        // /api/hello không cho POST dù cùng đường dẫn được phép GET.
        mvc.perform(post("/api/hello")
                .with(httpBasic("writer", "demo-pass")).with(csrf()))
            .andExpect(status().isForbidden());

        // Đường API chưa khai báo và đường ngoài API đều deny.
        mvc.perform(get("/api/unknown")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());
        mvc.perform(get("/unknown")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());
    }
}
```

Đây là integration test chạy qua Spring MVC và filter chain được gắn với `MockMvc`. `httpBasic("alice", "demo-pass")` tạo header Basic, để framework xác minh qua `UserDetailsService` thật trong context test; `csrf()` cung cấp token test hợp lệ. Những bài test chỉ tạo principal bằng `user(...)`/`@WithMockUser` sẽ kiểm tra rule, không xác minh password thật.

### 6.4. Chạy và kiểm tra thủ công

Cần JDK 17+ và Maven tương thích với Spring Boot 3.5; tại thư mục dự án:

```bash
mvn test
mvn spring-boot:run
```

Ở terminal khác (Windows PowerShell 5.1 dùng `curl.exe`):

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/hello
curl -i -u alice:demo-pass http://localhost:8080/api/hello
curl -i -u admin:demo-pass http://localhost:8080/api/admin
curl -i -u alice:demo-pass http://localhost:8080/profile
```

Kỳ vọng lần lượt `200`, `401`, `200` với body `api:alice`, `200` với body `admin`, và `200` với body `profile:alice`. Lệnh curl trên dùng HTTP thuần **chỉ dành cho máy local**: HTTP Basic không mã hóa password; ở môi trường thật phải cấu hình HTTPS. Nếu gửi `POST` bằng curl, cần lấy/gửi token CSRF tương ứng theo session/configuration, nên ví dụ chọn `MockMvc + csrf()` để chứng minh cả hai điều kiện trong test.

## 7. Demo B: Spring WebFlux với SecurityWebFilterChain

Demo này là **dự án Maven độc lập**, không ghép `spring-boot-starter-web` từ Demo A vào cùng ứng dụng. Với cả hai starter web và webflux, Spring Boot có thể chọn Servlet làm loại ứng dụng mặc định; để học `SecurityWebFilterChain` đúng cách, dùng riêng `spring-boot-starter-webflux`. Java 17, Boot 3.5.16 và Spring Security 6.5.x như Demo A.

### 7.1. Cấu trúc

```text
reactive-chain-demo/
├── pom.xml
└── src/
    ├── main/java/demo/reactive/ReactiveChainApplication.java
    └── test/java/demo/reactive/ReactiveChainTests.java
```

**`pom.xml`:**

```xml
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
    <artifactId>reactive-chain-demo</artifactId>
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

### 7.2. Mã Java đầy đủ

Tạo `src/main/java/demo/reactive/ReactiveChainApplication.java`:

```java
package demo.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveChainApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveChainApplication.class, args);
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/hello")
                    .hasAuthority("API_READ")
                .pathMatchers(HttpMethod.POST, "/api/tasks")
                    .hasAuthority("API_WRITE")
                .pathMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            // Không vô hiệu CSRF: request POST cần token hợp lệ.
            .build();
    }

    @Bean
    SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/profile").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        return new MapReactiveUserDetailsService(
            User.withUsername("alice")
                .password(encoder.encode("demo-pass"))
                .authorities("API_READ", "ROLE_USER").build(),
            User.withUsername("writer")
                .password(encoder.encode("demo-pass"))
                .authorities("API_READ", "API_WRITE").build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-pass"))
                .roles("ADMIN").build()
        );
    }
}

@RestController
class ReactiveRoutes {
    @GetMapping("/public")
    Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping("/profile")
    Mono<String> profile() {
        return Mono.just("profile");
    }

    @GetMapping("/api/hello")
    Mono<String> apiHello() {
        return Mono.just("api-hello");
    }

    @PostMapping("/api/tasks")
    Mono<String> createTask() {
        // Chỉ mô phỏng action; không có ghi database.
        return Mono.just("created");
    }

    @GetMapping("/api/admin")
    Mono<String> apiAdmin() {
        return Mono.just("admin");
    }
}
```

**Các mảnh ghép của demo:**

- `ServerHttpSecurity` là DSL reactive, còn `SecurityWebFilterChain` là bean được `WebFilterChainProxy` xem xét khi request đến.
- `PathPatternParserServerWebExchangeMatcher("/api/**")` chọn API chain; chain fallback không có matcher thu hẹp nên tiếp nhận những request không thuộc API.
- `@Order(1)` ưu tiên API trước fallback. `anyExchange().denyAll()` đóng các đường khác nằm **bên trong chain**.
- `MapReactiveUserDetailsService` cung cấp danh tính in-memory qua API reactive của Spring Security. Không dùng `InMemoryUserDetailsManager`/`UserDetailsService` đồng bộ rồi coi đó là cách tích hợp reactive mặc định.
- Các handler trả `Mono<String>` để minh họa kiểu xử lý bất đồng bộ. Trong service thật, xử lý không chặn và truy cập principal qua Reactor Context là điều quan trọng hơn việc controller trả `Mono.just(...)`.
- Spring Security WebFlux vẫn hỗ trợ CSRF và security headers theo cấu hình. Những rule `API_READ/API_WRITE` chỉ là ví dụ; ứng dụng thật còn phải kiểm tra quyền trên từng entity, tenant và hành động nhạy cảm.

### 7.3. WebTestClient với Spring Security Test

Tạo `src/test/java/demo/reactive/ReactiveChainTests.java`:

```java
package demo.reactive;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ReactiveChainTests {
    @Autowired
    ApplicationContext applicationContext;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void matchesApiFirstAndFallsBackForOtherPaths() {
        client.get().uri("/public").exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");

        client.get().uri("/api/hello").exchange()
            .expectStatus().isUnauthorized();

        client.get().uri("/api/hello")
            .headers(h -> h.setBasicAuth("alice", "demo-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("api-hello");

        client.get().uri("/api/hello")
            .headers(h -> h.setBasicAuth("admin", "demo-pass"))
            .exchange()
            .expectStatus().isForbidden();

        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth("admin", "demo-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin");

        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth("alice", "demo-pass"))
            .exchange()
            .expectStatus().isForbidden();

        client.get().uri("/profile").exchange()
            .expectStatus().isUnauthorized();

        client.get().uri("/profile")
            .headers(h -> h.setBasicAuth("alice", "demo-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("profile");

        // POST cần CSRF token dù writer có API_WRITE.
        client.post().uri("/api/tasks")
            .headers(h -> h.setBasicAuth("writer", "demo-pass"))
            .exchange()
            .expectStatus().isForbidden();

        // Đủ CSRF nhưng thiếu API_WRITE vẫn bị từ chối.
        client.mutateWith(csrf()).post().uri("/api/tasks")
            .headers(h -> h.setBasicAuth("alice", "demo-pass"))
            .exchange()
            .expectStatus().isForbidden();

        // Cả CSRF và API_WRITE hợp lệ.
        client.mutateWith(csrf()).post().uri("/api/tasks")
            .headers(h -> h.setBasicAuth("writer", "demo-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("created");

        client.get().uri("/api/unknown")
            .headers(h -> h.setBasicAuth("alice", "demo-pass"))
            .exchange()
            .expectStatus().isForbidden();

        client.get().uri("/unknown")
            .headers(h -> h.setBasicAuth("alice", "demo-pass"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

`WebTestClient.bindToApplicationContext(...)` dùng Spring WebFlux handler chain được khởi tạo từ context; `apply(springSecurity())` đưa Spring Security test support vào, còn `mutateWith(csrf())` tạo CSRF token hợp lệ cho request test. `setBasicAuth(...)` thử đường xác thực credential HTTP Basic. Không cần khởi động server thật cho test này. Test đơn vị của một `WebFilter` không thay thế kiểm thử **tích hợp toàn bộ chain** khi có nhiều matcher.

### 7.4. Lệnh chạy

Trong thư mục `reactive-chain-demo`:

```bash
mvn test
mvn spring-boot:run
```

Thử các GET bằng curl khi ứng dụng đã khởi động:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/hello
curl -i -u alice:demo-pass http://localhost:8080/api/hello
curl -i -u admin:demo-pass http://localhost:8080/api/admin
curl -i -u alice:demo-pass http://localhost:8080/profile
```

Kỳ vọng tương ứng: `200 public`; `401`; `200 api-hello`; `200 admin`; `200 profile`. POST trong mô hình có CSRF cần token phù hợp, nên kiểm tra đường cho phép và từ chối qua `WebTestClient` như trên. Không dùng HTTP Basic qua kết nối HTTP trên mạng không đáng tin; mẫu `localhost` chỉ dùng cho bài học.

## 8. Những khác biệt thực tế khi chuyển từ Servlet sang WebFlux

| Vấn đề | Điều cần kiểm tra |
| --- | --- |
| Filter type | Servlet filter không thể đặt thẳng vào `SecurityWebFilterChain`; reactive web filter không phải Servlet `Filter` |
| Context | Servlet thường dùng `SecurityContextHolder` trên ThreadLocal; WebFlux dùng `ReactiveSecurityContextHolder` qua Reactor Context |
| API phân quyền | `authorizeHttpRequests`/`requestMatchers` khác `authorizeExchange`/`pathMatchers` |
| Custom authentication | Servlet authentication filter + `AuthenticationManager` khác reactive `AuthenticationWebFilter` + `ReactiveAuthenticationManager` |
| Request object | `HttpServletRequest` khác `ServerWebExchange` |
| Session | Servlet `HttpSession` khác WebFlux `WebSession`; cách lưu context/session phải theo loại stack |
| Blocking I/O | WebFlux handler dùng JDBC/blocking SDK trên event loop có thể nghẽn dù đã dùng `Mono`; cần reactive driver hoặc offload phù hợp |
| Error handling | Servlet dispatch/error semantics khác WebFlux error pipeline; phải test status/error route thực tế |
| CSRF | Cả hai đều có cơ chế CSRF; repository/token request handler/configuration và test utilities khác nhau |
| Testing | Spring MVC `MockMvc` khác WebFlux `WebTestClient`; không dùng sai công cụ vì hai starter có tên tương tự |
| Method security | Servlet thường dùng `@EnableMethodSecurity` và method interceptor; WebFlux cần reactive method security và kiểu publisher phù hợp |
| Matcher | `RequestMatcher` và `ServerWebExchangeMatcher` là API riêng; đặc biệt chú ý HTTP method/path khi chuyển code |
| Startup | Có `spring-boot-starter-web` lẫn `spring-boot-starter-webflux` không bảo đảm app chạy WebFlux; kiểm tra `WebApplicationType`, classpath và auto configuration |

### 8.1. Chuyển custom filter

Ví dụ **minh họa Servlet** (không phải class hoàn chỉnh):

```java
// Dùng Filter/OncePerRequestFilter trong stack Servlet.
http.addFilterBefore(myServletFilter, UsernamePasswordAuthenticationFilter.class);
```

Ví dụ **minh họa WebFlux** (không phải class hoàn chỉnh):

```java
// Dùng WebFilter với vị trí xác định bởi SecurityWebFiltersOrder.
http.addFilterAt(myReactiveWebFilter, SecurityWebFiltersOrder.AUTHENTICATION);
```

Với custom authentication filter, đặt vào vị trí authentication, không tùy ý đặt sau authorization. Đối với filter ghi log, tracing, CORS hoặc security headers, phải chọn vị trí với trách nhiệm phù hợp. Nếu filter là Spring bean kiểu Servlet `Filter`, trong Boot nó có thể bị tự đăng ký thêm với container và chạy hai lần nếu đồng thời đưa vào Spring Security chain; cần quản lý việc đăng ký rõ ràng.

### 8.2. Áp quyền sau khi ra khỏi filter boundary

Một rule `.authenticated()` nghĩa là “actor đã được Spring Security xem là authenticated theo cơ chế tương ứng”. Nó **không có nghĩa** actor được đọc mọi record. Với endpoint `GET /api/orders/{id}`, service vẫn phải kiểm tra tenant/owner/ACL. Với `POST /api/payments`, ngoài API_WRITE còn phải kiểm soát hạn mức, idempotency, state transition và quyền với nguồn tiền. Điều này đúng ở cả Servlet lẫn WebFlux.

Đối với dữ liệu theo tenant, có thể định nghĩa query có điều kiện `findByIdAndTenantId` hoặc kiểm tra policy trong service theo **tenant từ identity đáng tin**. URL matcher không tự đọc database để biết đối tượng thuộc ai. Nếu dữ liệu đã bị trả ra response mà mới kiểm tra quyền thì quá muộn.

## 9. Các lỗi cấu hình hay gặp

### 9.1. Chỉ định chain API, quên fallback

**Triệu chứng:** `/api/**` yêu cầu login nhưng `/admin` ngoài API lại không đi qua Spring Security.

**Nguyên nhân:** chỉ một chain có `securityMatcher("/api/**")`, không chain nào match `/admin`.

**Sửa:** thêm chain fallback không thu hẹp matcher, với `anyRequest().denyAll()` hoặc chính sách rõ ràng; test cả endpoint có và không có prefix.

### 9.2. Đặt matcher quá rộng ở chain ưu tiên cao

**Triệu chứng:** chain API ưu tiên không bao giờ chạy; mọi request vào chain catch-all ở trên và bỏ qua rule cần thiết.

**Nguyên nhân:** chain match tất cả được ưu tiên trước chain hẹp.

**Sửa:** đặt chain hẹp trước và catch-all sau; có test chứng minh ai được chọn. Không dựa vào tên method bean hay thứ tự khai báo trong source.

### 9.3. Nghĩ các chain chồng lớp bảo mật

**Triệu chứng:** chain API không thiết lập header/CSRF như fallback nhưng đội phát triển tin fallback sẽ chạy sau.

**Nguyên nhân:** chỉ chain match đầu tiên được dùng.

**Sửa:** thống nhất rule cần lặp lại giữa chain qua helper/config phù hợp, hoặc giảm số chain khi không có lý do tách; kiểm tra filter list thực tế.

### 9.4. `permitAll()` và `ignoring()` bị nhầm

**Triệu chứng:** static resource hoặc endpoint public bị loại khỏi mọi security filter, mất một số header bảo vệ.

**Nguyên nhân:** sử dụng bỏ qua security filter chain thay cho rule cấp quyền.

**Sửa:** cho phép request trong chain bằng `permitAll` khi phù hợp và có chủ đích, vẫn giữ security filter trách nhiệm chung.

### 9.5. Đổi GET thành POST nhưng quên CSRF và method-specific authorization

**Triệu chứng:** thao tác POST 403 mặc dù user có role; hoặc tắt CSRF toàn bộ để “sửa”, làm endpoint cookie-based có thể bị CSRF.

**Nguyên nhân:** lẫn lộn phân quyền endpoint và CSRF protection. Hai kiểm tra này độc lập.

**Sửa:** phân quyền theo action/HTTP method, gửi token CSRF hợp lệ khi cơ chế đăng nhập có thể bị trình duyệt tự đính kèm; chỉ loại trừ CSRF nếu threat model xác nhận an toàn. Test cả các đường denied.

### 9.6. Thêm filter sai framework hoặc sai vị trí

**Triệu chứng:** Java class `OncePerRequestFilter` không hoạt động trong reactive chain; hoặc bearer authentication bị bỏ qua vì filter đặt sau authorization.

**Sửa:** chọn đúng API (`Filter` vs `WebFilter`), đúng chain, đúng thứ tự; kiểm tra loại ứng dụng thật tại runtime và test end-to-end.

### 9.7. Dùng ThreadLocal trong WebFlux

**Triệu chứng:** principal lúc có, lúc mất khi reactive pipeline đổi scheduler, hoặc rò rỉ dữ liệu người dùng nếu tự giữ context toàn cục.

**Sửa:** dùng `ReactiveSecurityContextHolder` và truyền identity có kiểm chứng qua publisher/Context; không dùng `block()` trên event loop.

### 9.8. Đặt tất cả endpoint admin dưới `/api/**` rồi chỉ viết rule ở fallback

**Triệu chứng:** fallback có `/api/admin/**.hasRole("ADMIN")`, nhưng request đã được chain API nhận, nên rule fallback không bao giờ được xét.

**Sửa:** quyền phải đặt trong **chain khớp thực tế**. Review “chain matcher → rule trong chain”, không chỉ tìm text `/api/admin` trong code.

### 9.9. Nhầm 404 và 403 ở đường chưa có handler

Một request đến URL chưa có controller có thể nhận `403` vì `denyAll` được thực thi **trước khi handler mapping quyết định 404**. Đây không nhất thiết là lỗi routing. Nếu muốn API trả 404 cho một số URL, vẫn cần giữ policy bảo mật rõ và thống nhất; đừng cho phép toàn bộ URL chỉ để đổi mã lỗi.

## 10. Cách kiểm tra filter chain đang chạy

### 10.1. Bật log ở local/staging

Với Spring Boot 3.x, đặt cấu hình logging trong `application.properties` của môi trường kiểm thử:

```properties
logging.level.org.springframework.security=DEBUG
```

Khi cần phân tích sâu hơn có thể tăng TRACE tạm thời cho package phù hợp, nhưng **không** giữ log chi tiết chứa credential/request nhạy cảm ở production. Log lúc startup thường giúp nhận diện filter được gắn; log lúc request giúp xác định request nào được bảo vệ. Mức và nội dung log cụ thể phụ thuộc phiên bản.

### 10.2. Checklist debug một request 401/403

1. **Stack thực tế:** Spring MVC Servlet hay WebFlux? Request đi qua server nào/proxy nào?
2. **Chain nào match?** Có `securityMatcher` phù hợp chưa, thứ tự `@Order` thế nào? Có fallback không?
3. **Rule nào match?** Path/HTTP method/servlet path/dispatcher type đã đúng chưa? `anyRequest`/`anyExchange` có chặn không?
4. **Authentication:** credential đã được decode và kiểm chứng chưa? `Authentication` là anonymous hay authenticated? Có authority đúng tên không? `hasRole` cần prefix `ROLE_` mặc định.
5. **Exploit protection:** POST có thiếu CSRF token không? CORS/preflight có được cấu hình đúng không? Headers/redirect có chịu proxy ảnh hưởng không?
6. **Handler:** request có đến controller không, hay bị security filter chặn trước? Nếu đến controller, policy owner/tenant còn phải kiểm tra ở service.
7. **Test:** có kiểm tra anonymous, user thường, admin, sai role, sai method, URL mới và đường lọt ngoài mọi chain?

Không log password, bearer token, session cookie, private key hoặc nguyên Authentication object ra file log công khai. Đối với WebFlux, kiểm tra cả pipeline scheduling và Reactor Context khi authentication được truyền qua các component reactive.

## 11. Bài tập tự đánh giá

**Bài 1.** API chain có `securityMatcher("/api/**")` và `authorizeHttpRequests(anyRequest -> denyAll())`. Không có chain khác. `GET /internal/health` có được Spring Security bảo vệ không?

**Đáp án:** Không, nếu không còn chain khác match `/internal/health`. `anyRequest` của API chain chỉ xét request đã match `/api/**`. Đây là lỗi cấu hình khi không có fallback.

**Bài 2.** Hai chain cùng match `GET /api/admin`. Chain `@Order(1)` yêu cầu `API_READ`, chain sau yêu cầu `ROLE_ADMIN`. Request chỉ có `ROLE_ADMIN` sẽ được chain nào bảo vệ?

**Đáp án:** Chỉ chain `@Order(1)` được dùng; nếu không có `API_READ`, request bị từ chối. Framework không tìm chain sau để thử cho phép.

**Bài 3.** Một request POST có role đúng nhưng thiếu CSRF token trong ứng dụng dùng cookie/session và CSRF đang bật. Có thể vào controller không?

**Đáp án:** Thông thường không; CSRF protection chặn request cần token trước khi xử lý action. Không nên tắt CSRF vì đã có role check.

**Bài 4.** Một reactive service dùng `SecurityContextHolder.getContext()` và nhận null khi đổi thread. Lỗi nên sửa ở đâu?

**Đáp án:** Dùng API reactive `ReactiveSecurityContextHolder`/Reactor Context hoặc truyền actor đã kiểm chứng rõ ràng qua pipeline. Không đổi sang `MODE_GLOBAL` để làm mọi thread nhìn thấy cùng identity.

**Bài 5.** Đã bảo vệ `GET /api/orders/123` bằng `authenticated()`. Alice có xem được hóa đơn của Bob không?

**Đáp án:** Chain chỉ đòi authenticated; để Alice không xem của Bob, service/repository phải kiểm tra ownership/tenant/permission cho order 123. Endpoint authenticated chưa đủ bảo vệ dữ liệu từng đối tượng.

## 12. Ghi nhớ

1. **Servlet:** `DelegatingFilterProxy → FilterChainProxy → SecurityFilterChain → Servlet Filter → DispatcherServlet`.
2. **WebFlux:** `WebFilterChainProxy → SecurityWebFilterChain → WebFilter → DispatcherHandler`, kết hợp Reactor Context.
3. **Chain selection xảy ra trước rule authorization.** `securityMatcher` chọn chain; `requestMatchers`/`pathMatchers` chọn quyền trong chain.
4. **Chain đầu tiên khớp là chain duy nhất chạy**; xếp chain đặc thù trước và có fallback để không lọt request.
5. **`HttpSecurity` và `ServerHttpSecurity` là builder**, được dùng để cấu hình, không phải các filter chạy trực tiếp mỗi request.
6. **Bảo vệ ở biên web chưa thay thế chính sách domain.** Cần quyền trên actor/action/resource/tenant/state và test denied paths.

## Tài liệu tham khảo chính thức

- [Spring Security 6.5 — Servlet Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security 6.5 — Java Configuration và nhiều SecurityFilterChain](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — WebFlux Security Configuration](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security 6.5 — WebFlux CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html)
- [Spring Security — MockMvc HTTP Basic Test](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html)
- [Spring Security — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html)
- [Spring Security — WebFlux Testing CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html)
- [Spring Boot 3.5.16 — End of OSS Support for 3.5.x](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)
