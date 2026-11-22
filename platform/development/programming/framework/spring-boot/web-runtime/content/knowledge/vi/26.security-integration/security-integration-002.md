# SecurityFilterChain của Servlet và SecurityWebFilterChain của reactive trong Spring Boot

> **Module:** Spring Boot - web-runtime · **Nhóm:** Tích hợp bảo mật. Bài giải thích cách Spring Security ghép lớp bảo mật vào hai web runtime: **Spring MVC trên Servlet** và **Spring WebFlux reactive**. Trọng tâm là phân biệt `SecurityFilterChain` và `SecurityWebFilterChain`, đường thực thi, điều kiện chọn chain, cách viết authorization rules, lưu security context, CSRF, CORS, lỗi thường gặp và kiểm thử. Ví dụ sử dụng **Java 17+**, Maven, **Spring Boot 4.1.2** và Spring Security cùng dependency do Boot quản lý. Hai ứng dụng MVC/WebFlux được đặt ở **hai project độc lập**.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả hai pipeline xử lý HTTP và giải thích vì sao không thể hoán đổi `SecurityFilterChain` với `SecurityWebFilterChain`.
2. Xác định trách nhiệm của `DelegatingFilterProxy`, `FilterChainProxy`, `jakarta.servlet.Filter` ở Servlet, đối chiếu với `WebFilterChainProxy` và `org.springframework.web.server.WebFilter` ở WebFlux.
3. Phân biệt **authentication** (xác thực người gọi) và **authorization** (quyết định quyền với tài nguyên), cũng như vai trò của `SecurityContext`.
4. Viết chain dùng `HttpSecurity.authorizeHttpRequests(...)` trên MVC và `ServerHttpSecurity.authorizeExchange(...)` trên WebFlux, sử dụng `permitAll`, `authenticated`, `hasRole`.
5. Hiểu **first matching security chain**, thứ tự `@Order` và sự khác nhau giữa **chain-level matcher** với **authorization rule matcher**.
6. Tạo và chạy hai REST demo độc lập cho cùng endpoint, quan sát 200/401/403 qua cURL.
7. Giải thích CSRF, stateless APIs, session, Reactive Context, filter ordering, CORS và những cạm bẫy khi tích hợp JWT, OAuth2, method security hoặc custom filter.
8. Chọn đúng cách thiết kế và kiểm thử bảo mật khi chuyển MVC ↔ WebFlux.

## 1. Vấn đề chung: request cần đi qua bảo mật trước controller

Một endpoint như `GET /admin` có thể được khai báo bằng `@GetMapping`. Spring MVC hoặc WebFlux quyết định **controller/handler** xử lý URL. Spring Security xử lý **ai được phép đến handler ấy** và các cơ chế như request authorization, authentication, CSRF, headers, session hoặc exception translation.

Quy trình khái niệm:

~~~text
HTTP request
  -> web server nhận request
  -> Spring Security web chain
       1. kiểm tra/thực thi cơ chế xác thực nếu cần
       2. truy cập/duy trì security context
       3. quyết định quyền truy cập
       4. CSRF/CORS/security headers/exception handling tùy cấu hình
  -> MVC controller hoặc WebFlux handler
  -> HTTP response
~~~

Lưu ý thứ tự trong sơ đồ là **mức khái niệm**: các filter thật có thứ tự cụ thể, nhiều filter có thể chạy trước/sau bước authentication, và preflight CORS hoặc CSRF có thể khiến request bị xử lý trước khi authorization. Không dựa vào sơ đồ này để lập trình thứ tự filter bằng tay.

**Authentication** xác nhận danh tính/chứng thực, ví dụ HTTP Basic, session cookie, bearer JWT, OAuth2 login hoặc mTLS. **Authorization** quyết định quyền với URL/method/tài nguyên. Có một Authentication hợp lệ không đồng nghĩa được truy cập mọi endpoint.

Ví dụ:

| Request | Người gọi | Quy tắc | Kết quả thường gặp |
| --- | --- | --- | --- |
| `GET /public` | Ẩn danh | `permitAll()` | 200 |
| `GET /me` | Ẩn danh | `authenticated()` | 401 với HTTP Basic API |
| `GET /me` | Xác thực USER | `authenticated()` | 200 |
| `GET /admin` | Xác thực USER, không có ADMIN | `hasRole("ADMIN")` | 403 |
| `GET /admin` | Xác thực ADMIN | `hasRole("ADMIN")` | 200 |

**401** thường nghĩa là chưa cung cấp/không có xác thực phù hợp và có thể đi kèm `WWW-Authenticate`. **403** thường nghĩa là đã xác thực nhưng không có quyền, hoặc request bị policy khác (chẳng hạn CSRF) từ chối. Với form login hay OAuth2 redirect, người chưa đăng nhập **có thể nhận 302** thay vì 401. Status phụ thuộc entry point và thiết lập thực tế, không chỉ sự có mặt của một `SecurityFilterChain`.

## 2. Hai web stack xử lý request khác nhau

### 2.1. Servlet / Spring MVC

~~~text
Browser / API client
  |
  v
Servlet container (Tomcat/Jetty)
  |
  v
Servlet Filter chain
  |
  +-- DelegatingFilterProxy("springSecurityFilterChain")
  |      |
  |      v
  |   FilterChainProxy
  |      |
  |      +-- chọn SecurityFilterChain đầu tiên có RequestMatcher khớp
  |      |
  |      +-- chạy các jakarta.servlet.Filter bên trong chain
  |             CSRF, Authentication, Authorization, ...
  |
  v
DispatcherServlet
  |
  v
@Controller / @RestController
  |
  v
HTTP response qua Servlet container
~~~

- `DelegatingFilterProxy` là cầu nối giữa **Servlet container Filter** và bean do Spring quản lý. Trong cấu hình Boot, việc đăng ký thường được auto-config, không cần viết `web.xml`.
- `FilterChainProxy` là cơ chế Spring Security quản lý và chọn một trong các `SecurityFilterChain`.
- Một `SecurityFilterChain` gồm **RequestMatcher** và danh sách **Servlet Filter** áp dụng khi request khớp.
- Các bộ lọc thao tác với `HttpServletRequest`/`HttpServletResponse`, điều khiển tiếp tục qua `FilterChain.doFilter(...)`.
- `HttpSecurity` là builder cấu hình filter chain, không phải một filter được gọi trực tiếp trong từng request.

### 2.2. Reactive / Spring WebFlux

~~~text
Browser / API client
  |
  v
Reactor Netty (phổ biến) hoặc runtime tương thích WebFlux
  |
  v
HTTP exchange -> WebFilter chain
  |
  +-- Spring Security WebFilterChainProxy
  |      |
  |      +-- chọn SecurityWebFilterChain đầu tiên khớp ServerWebExchange
  |      |
  |      +-- chạy các WebFilter trong reactive pipeline
  |             CSRF, Authentication, Authorization, ...
  |
  v
DispatcherHandler
  |
  v
Handler / @RestController (Mono/Flux)
  |
  v
Non-blocking HTTP response
~~~

- `SecurityWebFilterChain` chứa **ServerWebExchangeMatcher** và chuỗi **WebFilter** dùng reactive API.
- `ServerHttpSecurity` cấu hình security behavior cho **WebFlux**, khác `HttpSecurity` ở Servlet.
- `WebFilter.filter(ServerWebExchange, WebFilterChain)` trả `Mono<Void>`, có thể phát thành công/lỗi hoặc hoàn tất bất đồng bộ.
- Reactive authentication context thường truyền trong **Reactor Context**, không bảo đảm nằm trong cùng một ThreadLocal qua nhiều scheduler.
- `SecurityWebFilterChain` **không** phải `jakarta.servlet.Filter` và không được đăng ký qua Servlet `FilterRegistrationBean`.

Nếu một ứng dụng có cả `spring-boot-starter-webmvc` lẫn `spring-boot-starter-webflux`, Spring Boot thông thường chọn **Servlet/MVC web application type**, trừ khi cấu hình rõ để đổi. Chỉ thêm WebFlux starter để dùng `WebClient` **không** có nghĩa request server chuyển sang reactive. Hãy kiểm loại runtime trước khi chọn API security.

## 3. Bảng so sánh lớp, API và vòng đời

| Chủ đề | Servlet / MVC | Reactive / WebFlux |
| --- | --- | --- |
| Web runtime | Servlet container, `DispatcherServlet` | WebFlux runtime, `DispatcherHandler` |
| Kiểu chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Builder | `HttpSecurity` | `ServerHttpSecurity` |
| Container/proxy security | `FilterChainProxy` qua `DelegatingFilterProxy` | `WebFilterChainProxy` trong WebFlux filter chain |
| Filter interface | `jakarta.servlet.Filter` | `org.springframework.web.server.WebFilter` |
| Đầu vào matcher | `HttpServletRequest` + `RequestMatcher` | `ServerWebExchange` + `ServerWebExchangeMatcher` |
| Authorization DSL | `authorizeHttpRequests(...)` | `authorizeExchange(...)` |
| URL rule | `requestMatchers(...)` | `pathMatchers(...)` / `matchers(...)` |
| Fallback rule | `anyRequest()` | `anyExchange()` |
| Basic auth | `httpBasic(...)` | `httpBasic(...)` |
| User lookup | `UserDetailsService` hoặc authentication provider | `ReactiveUserDetailsService` / reactive authentication manager |
| Security context | `SecurityContextHolder`, thường thread-bound | `ReactiveSecurityContextHolder`, Reactor Context |
| Session infrastructure | `HttpSession`, `SecurityContextRepository` | `WebSession`, `ServerSecurityContextRepository` |
| Method security | `@EnableMethodSecurity` | `@EnableReactiveMethodSecurity` |
| HTTP result | Servlet response, async theo API phù hợp | Publisher (`Mono`/`Flux`) |
| Custom filter ordering | Spring Security filter order, `addFilterBefore/After`... | `SecurityWebFiltersOrder` / `addFilterAt` và reactive semantics |

Điểm chung: cả hai cho phép nhiều chains, authentication mechanisms, authorization rules, CSRF, CORS và headers. **Nhưng lớp Java/điểm mở rộng khác nhau**, không thể chỉ đổi tên từ Servlet sang reactive rồi giữ nguyên cách triển khai.

## 4. Chọn chain: first match, không phải “gộp tất cả”

Một ứng dụng có thể khai báo nhiều chain, ví dụ một chain đặc biệt cho `/api/**` và một chain fallback cho những URL khác. Cả Servlet và reactive đều chọn **chain đầu tiên khớp** theo thứ tự ưu tiên (thường gắn `@Order`).

~~~text
Request GET /api/orders
  |
  +-- Chain A @Order(1), securityMatcher /api/**  -> MATCH -> DÙNG A
  |
  +-- Chain B @Order(2), matcher /admin/**        -> không xét tiếp
  |
  +-- Chain fallback                              -> không xét tiếp
~~~

Tất cả authorization rule và filter của A quyết định request. Nếu A **từ chối quyền** và trả 403, framework **không** thử chain B chỉ vì B có thể cho phép request. Chọn security chain và quyết định quyền **không phải** hai vòng fallback giống nhau.

Nếu request không khớp bất kỳ chain nào, request có thể **đi qua mà không được Spring Security bảo vệ**. Vì vậy nên có một **fallback chain** khớp mọi request và dùng `authenticated()` hoặc `denyAll()` theo chính sách.

### 4.1. `@Order`

- `@Order(1)` được xét trước `@Order(2)`.
- Số order thấp có ưu tiên cao; không dùng bean name hoặc thứ tự khai báo file làm cơ sở bảo mật.
- Chain đặc biệt nên có order rõ, fallback đặt sau.
- Đừng cấp quyền qua một matcher quá rộng ở chain ưu tiên cao rồi kỳ vọng chain thấp hơn sẽ hạn chế lại.
- Giữa các matcher chồng nhau, cần kiểm thử cả URL khớp nhiều chain để thấy chain **thực sự được chọn**.

### 4.2. Chain matcher khác authorization matcher

**Servlet:**

~~~java
// Fragment minh họa một SecurityFilterChain cho /api/**.
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public").permitAll()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated());
~~~

`securityMatcher("/api/**")` quyết định **chain này có được dùng hay không**. Sau khi đã chọn chain, `requestMatchers("/api/admin/**")` quyết định **quyền** cho một request trong chain. `anyRequest()` chỉ là fallback **bên trong chain** đã được chọn; không bảo vệ URLs bên ngoài `/api/**`.

**Reactive:**

~~~java
// Fragment minh họa: chain cho /api/** trong WebFlux.
http.securityMatcher(
        new PathPatternParserServerWebExchangeMatcher("/api/**"))
    .authorizeExchange(ex -> ex
        .pathMatchers("/api/public").permitAll()
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .anyExchange().authenticated());
~~~

Matcher cho chain dùng `ServerWebExchangeMatcher`; authorization matcher chọn rule trong một chain và có thể so phương thức HTTP.

**Không nhầm** `requestMatchers(...)` của MVC với `pathMatchers(...)` của WebFlux. Cũng đừng dùng matcher servlet để bảo vệ WebFlux hoặc ngược lại.

### 4.3. Thứ tự rule bên trong một chain cũng quan trọng

Ví dụ:

~~~java
// SAI về ý định: rule rộng được xét trước.
auth.requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated();
~~~

Một request `/api/admin/stats` có thể đã được rule rộng permitAll xử lý, nên rule admin cụ thể không được dùng. Đặt các rule **cụ thể trước**, broad/fallback ở cuối:

~~~java
auth.requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/public/**").permitAll()
    .anyRequest().authenticated();
~~~

Với WebFlux, áp dụng cùng nguyên tắc nhưng dùng `pathMatchers(...)`. Luôn test request đang nằm ở ranh giới các pattern.

## 5. Một chain Servlet cơ bản trong Spring MVC

Mẫu cấu hình theo Spring Security hiện đại:

~~~java
// Fragment của Spring MVC, chưa phải class độc lập.
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public").permitAll()
            .requestMatchers("/admin").hasRole("ADMIN")
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults());
    return http.build();
}
~~~

- `@Bean` xuất một `SecurityFilterChain`.
- `HttpSecurity` tạo danh sách servlet security filters và request matcher; `build()` kết thúc cấu hình.
- `permitAll()` cho phép endpoint public nhưng **không loại bỏ toàn bộ security filters**.
- `hasRole("ADMIN")` kiểm authority **`ROLE_ADMIN`** theo convention, không phải một chuỗi bất kỳ `ADMIN` (nếu muốn kiểm authority nguyên văn thì dùng `hasAuthority(...)`).
- `anyRequest().authenticated()` không tự yêu cầu role admin: mọi user đã xác thực có thể vào những URL còn lại.
- `httpBasic(...)` thêm cơ chế HTTP Basic. Mặc dù tiện cho demo, production phải dùng HTTPS và cơ chế auth phù hợp; không coi Base64 của Basic là mã hóa bí mật.

**CSRF mặc định vẫn được bật** vì mẫu không vô hiệu hóa nó. Demo bên dưới chỉ đọc qua GET. Nếu thêm POST/PUT/DELETE sử dụng credential từ browser, cần xử lý CSRF token hoặc phân tích đúng tình huống stateless bearer token; không tắt toàn bộ chỉ để test thành công.

## 6. Một chain Reactive cơ bản trong Spring WebFlux

~~~java
// Fragment của Spring WebFlux, chưa phải class độc lập.
@Bean
SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(ex -> ex
            .pathMatchers("/public").permitAll()
            .pathMatchers("/admin").hasRole("ADMIN")
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

- `ServerHttpSecurity` là builder của **WebFlux**, không nhận `HttpServletRequest`.
- `SecurityWebFilterChain` được tạo từ builder và chạy trong web filter chain của reactive stack.
- `authorizeExchange(...)` chọn quyền trên `ServerWebExchange`; `anyExchange()` là fallback.
- `httpBasic(...)` dùng reactive authentication stack; user lookup có thể là `ReactiveUserDetailsService`.
- Dòng `build()` không subscribe vào `Mono`; đây là cấu hình chain ở thời điểm startup, không phải xử lý request tự viết.

Nếu đọc authentication trong một pipeline, dùng `ReactiveSecurityContextHolder.getContext()` hoặc principal từ `ServerWebExchange.getPrincipal()`; không dựa vào `SecurityContextHolder.getContext()` trong một reactive `flatMap` tùy thread. Reactor có thể chuyển scheduler và thread trong vòng đời request.

## 7. Hai dự án chạy độc lập: cùng quy tắc, khác runtime

Để đối chiếu, ta xây hai dự án **cùng endpoint và users**:

| Endpoint | Public | learner / USER | admin / ADMIN |
| --- | --- | --- | --- |
| `GET /public` | 200 | 200 | 200 |
| `GET /me` | 401 | 200 | 200 |
| `GET /admin` | 401 | 403 | 200 |

Kết quả 401/403 giả định request dùng HTTP Basic, client không có cookie/session hợp lệ và không có entry point khác. Trong demo, password được hardcode **chỉ cho localhost**, không đặt làm secret production và không dùng cho hệ thống internet thật. Cả hai dùng BCrypt cho hash của in-memory users. Không bao giờ lưu mật khẩu thật dưới dạng plaintext trong project.

### 7.1. Dự án A — Servlet MVC SecurityFilterChain

**Cấu trúc:**

~~~text
security-servlet-demo/
  pom.xml
  src/main/java/com/example/servletsecurity/
    ServletSecurityApplication.java
    ServletSecurityConfig.java
    ApiController.java
  src/main/resources/
    application.properties
~~~

**`pom.xml`**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>security-servlet-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
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
~~~

Đây là Maven project **Servlet stack** với embedded Tomcat. Spring Boot quản lý các phiên bản Spring Security tương thích. Không thêm `spring-boot-starter-webflux` cho project A.

**`ServletSecurityApplication.java`**

~~~java
package com.example.servletsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ServletSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(ServletSecurityApplication.class, args);
    }
}
~~~

**`ServletSecurityConfig.java`**

~~~java
package com.example.servletsecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
public class ServletSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public", "/error").permitAll()
                        .requestMatchers("/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        // Demo credentials, chỉ cho môi trường local không public.
        UserDetails learner = User.withUsername("learner")
                .password(encoder.encode("learner-demo-123"))
                .roles("USER")
                .build();
        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-demo-123"))
                .roles("USER", "ADMIN")
                .build();
        return new InMemoryUserDetailsManager(learner, admin);
    }
}
~~~

**Giải thích:**

- `@EnableWebSecurity` làm intent của ví dụ rõ ràng; với Spring Boot auto-configuration thông thường, việc tích hợp Spring Security cũng có thể tự được kích hoạt khi starter ở classpath.
- `SecurityFilterChain` là bean bảo vệ mọi request vì không đặt `securityMatcher(...)` giới hạn riêng. HTTP Basic được bật và auth type do `UserDetailsService` cung cấp.
- `PasswordEncoder` dùng BCrypt, không lưu plaintext password trong đối tượng user. Literal password chỉ phục vụ demo để người học cURL dễ thử; trong thực tế lấy từ identity provider, secret storage/credential provisioning.
- `ROLE_USER` và `ROLE_ADMIN` được gắn bởi builder `.roles(...)`; do đó `hasRole("ADMIN")` hợp với user admin.
- `/error` được permitAll để tránh lặp 401 khi framework cần render lỗi; không dùng điều này như quyền truy cập tới dữ liệu thật.

**`ApiController.java`**

~~~java
package com.example.servletsecurity;

import java.security.Principal;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/public")
    public Map<String, String> publicInfo() {
        return Map.of("message", "public");
    }

    @GetMapping("/me")
    public Map<String, String> me(Principal principal) {
        return Map.of("user", principal.getName());
    }

    @GetMapping("/admin")
    public Map<String, String> admin() {
        return Map.of("message", "admin only");
    }
}
~~~

`Principal` của MVC được cung cấp từ security request context. Method `me()` chỉ chạy sau khi authorization cho phép authenticated user. Không dựa vào giá trị query string `user=admin` để tự tạo Principal.

**`application.properties`**

~~~properties
server.port=8080
logging.level.org.springframework.security=INFO
~~~

Dùng `INFO` tránh xuất quá nhiều thông tin trong demo. Khi debug, có thể tăng DEBUG ở môi trường kiểm thử có kiểm soát; không in mật khẩu, Basic header, bearer token hoặc dữ liệu cá nhân vào log.

### 7.2. Dự án B — WebFlux SecurityWebFilterChain

**Cấu trúc:**

~~~text
security-reactive-demo/
  pom.xml
  src/main/java/com/example/reactivesecurity/
    ReactiveSecurityApplication.java
    ReactiveSecurityConfig.java
    ApiController.java
  src/main/resources/
    application.properties
~~~

**`pom.xml`**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>security-reactive-demo</artifactId>
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
~~~

`spring-boot-starter-webflux` dùng WebFlux với Reactor Netty phổ biến, **không** dùng servlet MVC starter. Tránh trộn cả hai starter trong project B nếu muốn quan sát security pipeline reactive thật sự.

**`ReactiveSecurityApplication.java`**

~~~java
package com.example.reactivesecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveSecurityApplication.class, args);
    }
}
~~~

**`ReactiveSecurityConfig.java`**

~~~java
package com.example.reactivesecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers("/public", "/error").permitAll()
                        .pathMatchers("/admin").hasRole("ADMIN")
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    ReactiveUserDetailsService userDetailsService(PasswordEncoder encoder) {
        // Credentials demo, không dùng trong production.
        UserDetails learner = User.withUsername("learner")
                .password(encoder.encode("learner-demo-123"))
                .roles("USER")
                .build();
        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-demo-123"))
                .roles("USER", "ADMIN")
                .build();
        return new MapReactiveUserDetailsService(learner, admin);
    }
}
~~~

**Giải thích:**

- Không có `HttpSecurity` hoặc `SecurityFilterChain` kiểu Servlet; bean đúng là `SecurityWebFilterChain` dựng từ `ServerHttpSecurity`.
- `MapReactiveUserDetailsService` là implementation demo của `ReactiveUserDetailsService`; user data nằm trong memory, không phải database/repository production.
- BCrypt là phép tính CPU-bound; với workload lớn cần cân nhắc tài nguyên authentication. Không đưa blocking JDBC authentication tự viết vào Reactor Netty event loop; nếu nguồn chỉ có API blocking, cô lập vào scheduler thích hợp hoặc chuyển sang reactive repository/auth manager.
- `authorizeExchange(...)` bảo vệ các WebFlux exchanges; `anyExchange().authenticated()` là fallback cho tất cả routes khác.

**`ApiController.java`**

~~~java
package com.example.reactivesecurity;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/public")
    public Mono<Map<String, String>> publicInfo() {
        return Mono.just(Map.of("message", "public"));
    }

    @GetMapping("/me")
    public Mono<Map<String, String>> me(ServerWebExchange exchange) {
        return exchange.getPrincipal()
                .map(principal -> Map.of("user", principal.getName()));
    }

    @GetMapping("/admin")
    public Mono<Map<String, String>> admin() {
        return Mono.just(Map.of("message", "admin only"));
    }
}
~~~

`ServerWebExchange.getPrincipal()` trả `Mono<Principal>` trong WebFlux; controller tiếp tục xử lý bằng Reactor operators. Bên dưới, Spring Security quản lý context trong reactive execution, không cần tự gọi `subscribe()` hoặc `block()`.

**`application.properties`**

~~~properties
server.port=8080
logging.level.org.springframework.security=INFO
~~~

### 7.3. Chạy và kiểm thử bằng cURL

Chạy **từng project một** vì cả hai cùng sử dụng port 8080:

~~~bash
# Trong security-servlet-demo/ hoặc security-reactive-demo/:
mvn spring-boot:run
~~~

Trong terminal khác:

~~~bash
# 1. Route public:
curl -i http://localhost:8080/public

# 2. Route cần xác thực, chưa gửi Authorization:
curl -i http://localhost:8080/me

# 3. Xác thực USER:
curl -i -u learner:learner-demo-123 http://localhost:8080/me

# 4. USER thử admin:
curl -i -u learner:learner-demo-123 http://localhost:8080/admin

# 5. ADMIN truy cập admin:
curl -i -u admin:admin-demo-123 http://localhost:8080/admin
~~~

Bảng kỳ vọng trong cấu hình HTTP Basic của hai ví dụ:

| Lệnh | Status | Body tiêu biểu |
| --- | --- | --- |
| GET `/public` ẩn danh | 200 | `{"message":"public"}` |
| GET `/me` ẩn danh | 401 | Có thể là error body/không body; kèm challenge HTTP Basic |
| GET `/me` bằng learner | 200 | `{"user":"learner"}` |
| GET `/admin` bằng learner | 403 | Tùy error representation, không phải response của controller |
| GET `/admin` bằng admin | 200 | `{"message":"admin only"}` |

Body JSON có thể khác thứ tự thuộc tính, error body có thể khác theo stack/Boot error configuration. **Chỉ khẳng định những response đã biết từ controller**; không cố định chi tiết error body khi chưa chạy thực tế.

Trên PowerShell, dùng `curl.exe -i -u learner:learner-demo-123 http://localhost:8080/me`. Trên Windows nên biết `curl` có thể là alias của `Invoke-WebRequest` tùy phiên bản.

Đóng gói:

~~~bash
mvn package
java -jar target/security-servlet-demo-0.0.1-SNAPSHOT.jar
~~~

Với project reactive, đổi tên JAR tương ứng:

~~~bash
java -jar target/security-reactive-demo-0.0.1-SNAPSHOT.jar
~~~

Chạy trong đúng thư mục dự án sau khi `mvn package`, không chạy đồng thời hai JAR trên cùng port trừ khi đổi port.

**Cảnh báo bảo mật:** HTTP Basic gửi credential dưới dạng mã hóa Base64, **không** phải encryption. Ví dụ `http://localhost:8080` chỉ phù hợp môi trường local test. Production cần HTTPS (kể cả qua reverse proxy đúng trust boundary) và identity store/credential management thay vì hardcoded demo users.

## 8. Nhiều chain trong Servlet: ví dụ cấu hình và thứ tự

Một ứng dụng có thể muốn:

- `/api/**` dùng HTTP Basic hoặc bearer JWT.
- Các URL còn lại chỉ chấp nhận người đã đăng nhập bằng form/session hoặc bị từ chối.
- Không có đường đi “lọt” ngoài Spring Security.

Fragment minh họa đặt trong một class `@Configuration` (không thêm trực tiếp cùng chain của ví dụ trên mà không chỉnh cấu hình):

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(a -> a
            .requestMatchers("/api/status").permitAll()
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(a -> a.anyRequest().denyAll())
        .build();
}
~~~

Ý nghĩa:

- `@Order(1)` ưu tiên cho `/api/**`. Mọi endpoint ngoài prefix đó sẽ không đi qua chain API.
- `fallbackChain` khớp mọi URL còn lại và từ chối; đây là **deny-by-default**. Trong ứng dụng thật, bạn có thể thay bằng formLogin/permission phù hợp, nhưng đừng bỏ fallback khi chưa chủ động có tầng khác bảo vệ.
- Khi `/api/admin/x` không đủ quyền, kết quả 403 không làm Spring Security “thử fallback chain” tiếp.
- Nếu Servlet được mount dưới `spring.mvc.servlet.path` riêng, matcher semantics có thể phức tạp hơn. Spring Security 7 từng có lỗ hổng liên quan `securityMatchers(String)` kết hợp Servlet path và matcher builder ở một số phiên bản trước khi được vá. Luôn cập nhật bản Spring Security đã khắc phục và **test path thực**, không chỉ chạy unit test matcher.

**Về CSRF:** Nếu chain API chỉ dùng bearer token trong `Authorization` mà browser không tự đính credential, có thể cân nhắc tắt CSRF **chỉ cho chain/paths đó** sau khi đánh giá threat model. Nếu dùng cookie/session hoặc HTTP Basic được browser tự gửi, không mặc định CSRF không còn cần. Mặc định nên giữ bật khi không có lý do rõ.

## 9. Nhiều chain trong Reactive: ví dụ tương ứng

Fragment WebFlux khác API matcher:

~~~java
@Bean
@Order(1)
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**"))
        .authorizeExchange(ex -> ex
            .pathMatchers("/api/status").permitAll()
            .pathMatchers("/api/admin/**").hasRole("ADMIN")
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(ex -> ex.anyExchange().denyAll())
        .build();
}
~~~

Ở đây `PathPatternParserServerWebExchangeMatcher` thuộc package `org.springframework.security.web.server.util.matcher`. Fragment cần các import `Bean`, `Order`, `Customizer`, `SecurityWebFilterChain`, `ServerHttpSecurity` trong class reactive configuration, không phải class Servlet.

**Điểm giống:** first match và thứ tự `@Order`. **Điểm khác:** matcher nhận `ServerWebExchange`, filter là reactive `WebFilter`. Không copy `HttpSecurity.securityMatcher(...)` với `RequestMatcher` sang WebFlux.

### Một chain per request, không phải một filter per URL

Các security filter nằm bên trong chain được chọn; dù có nhiều chain beans, một request không thường chạy tất cả các chain đó lần lượt. Muốn chặn một request theo permission, đặt rule/authorization trong **chain khớp thực sự**. Nếu cần áp chính sách cross-cutting cho tất cả URLs, cấu hình ở mọi chain phù hợp hoặc một shared customizer/bean chính sách, chứ đừng giả định chain fallback chạy sau chain chuyên biệt.

## 10. Servlet SecurityContextHolder và Reactor Context

### Servlet: thường gắn với thread hiện hành

Trong luồng Servlet đồng bộ, nhiều thành phần Spring Security dùng `SecurityContextHolder` (chiến lược thông thường dựa trên `ThreadLocal`) để truy cập `Authentication` của request hiện tại.

~~~java
// Fragment trong mã Servlet sau khi Spring Security đã xác thực:
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
String username = authentication.getName();
~~~

Đây là ví dụ **không độc lập**; cần import Spring Security context. Khi dùng async executors, `@Async`, `CompletableFuture` hoặc thread do ứng dụng tự tạo, **đừng mặc định** security context tự đi theo thread. Có thể sử dụng `DelegatingSecurityContextExecutor` hoặc cơ chế propagation được hỗ trợ. Tách request context lifecycle, không chia sẻ Authentication mutable giữa users.

### Reactive: subscriber context, không mặc định thread-local

Trong WebFlux, asynchronous operators có thể tiếp tục trên nhiều threads/schedulers. Spring Security sử dụng **Reactor Context** để truyền reactive `SecurityContext`:

~~~java
// Fragment WebFlux; gọi bên trong pipeline Reactor (không tự block).
Mono<String> username = ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName());
~~~

Hoặc trong HTTP handler dùng `ServerWebExchange.getPrincipal()`, như demo. Không dùng `SecurityContextHolder.getContext()` ở một reactive `flatMap` rồi cho rằng luôn thấy user tương ứng. Nếu tự tạo Publisher ngoài subscription chain, tự `subscribe()`, đưa task sang scheduler hoặc thực hiện bridge blocking, cần hiểu **context propagation**.

Method security reactive cũng có yêu cầu: policy dựa trên `@EnableReactiveMethodSecurity` và return type phù hợp (thường `Mono`/`Flux`), bảo đảm security context có mặt trong subscriber context. Cùng một service method có thể có semantics khác khi trả plain value hoặc tự `block()`; không biến mọi method thành reactive chỉ bằng annotation.

### Dữ liệu lưu trong session

- Servlet thường dùng `HttpSession` và `SecurityContextRepository` để lưu/khôi phục context giữa requests, khi sử dụng session-based auth.
- WebFlux dùng `WebSession` và `ServerSecurityContextRepository`; cơ chế reactive không phải wrapper trực tiếp của `HttpSession`.
- Với bearer JWT stateless, có thể không cần lưu server-side login session; tuy nhiên **stateless** không đồng nghĩa “không có CSRF/CORS/permission problem”.
- Khi sử dụng Spring Session/Redis, phải chọn integration tương ứng Servlet hay reactive và đánh giá session fixation, expiry, invalidation, logout.

## 11. CSRF: default và lý do không tắt vô điều kiện

**CSRF** (Cross-Site Request Forgery) là khả năng một site khác kích hoạt request thay đổi trạng thái dùng credential mà browser tự đính kèm (ví dụ cookie phiên đăng nhập). Spring Security thường bật CSRF protection mặc định cho các **unsafe methods** như POST/PUT/PATCH/DELETE, cả ở Servlet và WebFlux.

### Servlet

~~~java
// Minh họa khi cần custom, KHÔNG phải lời khuyên tắt CSRF global.
http.csrf(csrf -> csrf
    .ignoringRequestMatchers("/api/token/**"));
~~~

Fragment này chỉ phù hợp khi endpoint thật sự không dựa vào browser auto-sent credentials và đã được đánh giá; việc ignore CSRF không đồng nghĩa authentication/authorization tự hoạt động.

### WebFlux

~~~java
// Minh họa khái niệm; kiểu matcher ở WebFlux khác Servlet.
http.csrf(csrf -> csrf
    .requireCsrfProtectionMatcher(customServerWebExchangeMatcher));
~~~

`customServerWebExchangeMatcher` là một `ServerWebExchangeMatcher` do ứng dụng định nghĩa theo rủi ro; fragment **không độc lập** và không nên copy nếu chưa rõ policy. Với form HTML/session, cần truyền CSRF token đến client theo cơ chế được hỗ trợ. Đừng tắt CSRF chỉ vì một request POST trong Postman bị 403.

**HTTP Basic cũng có thể được browser lưu/tự gửi**, nên không tự khẳng định Basic-only API là miễn CSRF trong mọi trường hợp. Với OAuth2 bearer header do script chủ động thêm và không dùng cookie, mô hình đe dọa khác nhưng phải đánh giá XSS, CORS, token storage và quyền request.

CSRF khác CORS: CORS quy định browser được đọc/gửi một số cross-origin requests theo chính sách, nhưng **không phải** biện pháp chống CSRF thay thế.

## 12. CORS, security headers và thứ tự xử lý

Browser có thể gửi preflight `OPTIONS` mà **chưa chứa cookie/Authorization** giống request thật. Nếu một security chain đòi authentication trước khi xử lý CORS đúng cách, preflight có thể bị từ chối.

- Servlet sử dụng cấu hình CORS qua Spring MVC và Spring Security (ví dụ `http.cors(Customizer.withDefaults())` khi có cấu hình CORS phù hợp) hoặc `CorsConfigurationSource`.
- WebFlux dùng cấu hình CORS tương thích WebFlux hoặc `CorsWebFilter`/Spring Security chain; phải tránh cấu hình chồng hai nơi phát headers mâu thuẫn.
- Chỉ cho phép `Access-Control-Allow-Origin` phù hợp. Không kết hợp wildcard origin với credentials tùy tiện.
- Không dùng `permitAll("/**")` chỉ để chữa preflight 401/403.
- Header như `Content-Security-Policy`, `X-Content-Type-Options`, HSTS, Referrer-Policy có thể được Spring Security cấu hình theo web stack; không coi CSP/HSTS là một cơ chế tự có chỉ vì thêm starter mà không kiểm.

Nếu ứng dụng nằm sau reverse proxy, cần cấu hình trusted forwarded headers và TLS termination đúng; tránh trường hợp server tin header `X-Forwarded-*` do client internet tự đặt. Redirect URL sai hoặc HTTP ↔ HTTPS loop không được giải quyết bằng cách vô hiệu hóa security chain.

## 13. JWT, OAuth2 và bảo mật API: chọn provider theo stack

Các ví dụ HTTP Basic ở trên chỉ dạy **cấu trúc chain**. Production REST APIs thường dùng OAuth2 resource server, OpenID Connect hoặc session-based login, tùy sản phẩm.

**Servlet JWT resource server (fragment):**

~~~java
// Minh họa sau khi đã có dependency OAuth2 Resource Server và issuer/JWK config.
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/public").permitAll()
        .anyRequest().authenticated())
    .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));
~~~

**WebFlux JWT resource server (fragment):**

~~~java
// Minh họa; phải có reactive JWT decoder và resource server dependency.
http.authorizeExchange(ex -> ex
        .pathMatchers("/public").permitAll()
        .anyExchange().authenticated())
    .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));
~~~

Cấu hình thật còn cần issuer URI/JWK Set URI, kiểm chữ ký, `exp`, `nbf`, issuer, audience, thuật toán, scope/authority mapping, caching JWK và xử lý lỗi. **Đừng tin JWT chỉ vì decode Base64 thành công.** Không tự viết một JWT parser xác thực chữ ký theo regex.

Một số khác biệt:

| Mục | Servlet | Reactive |
| --- | --- | --- |
| Web security builder | `HttpSecurity` | `ServerHttpSecurity` |
| Token authentication runtime | Servlet filters/authentication manager | Reactive WebFilters/reactive auth manager |
| Method security | `@EnableMethodSecurity` | `@EnableReactiveMethodSecurity` |
| JWT decoder | `JwtDecoder` | `ReactiveJwtDecoder` |
| User details | `UserDetailsService` | `ReactiveUserDetailsService` |
| Bối cảnh auth | SecurityContextHolder/Servlet request | ReactiveSecurityContextHolder/Reactor Context |
| Request matcher | `RequestMatcher` | `ServerWebExchangeMatcher` |

Các bean OAuth2 thực tế có thể được Boot auto-config khi đúng starter/properties; không cần thêm bừa cả servlet và reactive provider vào cùng context.

## 14. Custom filter: đúng interface, đúng vị trí, không chặn event loop

### Servlet custom filter

Một Servlet filter bình thường implement `jakarta.servlet.Filter` hoặc kế thừa `OncePerRequestFilter`. Khi tích hợp Spring Security chain, có thể dùng `http.addFilterBefore(filter, BasicAuthenticationFilter.class)` hoặc vị trí chính xác khác tùy nhiệm vụ.

~~~java
// Fragment minh họa trong Servlet chain, customFilter phải là Filter phù hợp.
http.addFilterBefore(customFilter, BasicAuthenticationFilter.class);
~~~

Đừng đăng ký cùng filter **hai lần**: vừa `@Component` khiến container tự đăng ký như một Servlet filter, vừa `addFilterBefore` thêm vào Spring Security chain. Điều này có thể làm filter chạy hai lần hoặc khác thứ tự. Nếu cần, tạo bean và disable servlet auto registration tương ứng.

### Reactive custom WebFilter

WebFlux custom filter implement `org.springframework.web.server.WebFilter` và trả `Mono<Void>`; khi thêm vào Spring Security chain cần vị trí thuộc `SecurityWebFiltersOrder`:

~~~java
// Fragment minh họa trong cấu hình WebFlux.
http.addFilterAt(customWebFilter, SecurityWebFiltersOrder.AUTHENTICATION);
~~~

Vị trí `AUTHENTICATION` chỉ nên dùng khi customWebFilter thực hiện đúng vai trò auth và quản lý `SecurityContext`/errors; không đặt tùy ý mọi logging filter ở đó. WebFlux filter không được gọi `block()`, chạy JDBC chặn trực tiếp trên Netty event loop hoặc thao tác blocking I/O mà chưa cô lập phù hợp.

Custom auth/filter dễ có lỗi bỏ qua CSRF, rò token, exception translation, context propagation và thứ tự giữa các filter. Nên ưu tiên authentication provider, OAuth2 resource server, authorization manager hoặc giải pháp Spring Security có sẵn hơn tự viết token filter nếu không cần.

## 15. `permitAll` khác `web.ignoring()` và “không có chain”

Trong Servlet, khi URL có rule `permitAll()`, request thường **vẫn qua Spring Security chain**, bao gồm security headers và những cơ chế filter có liên quan. Còn cấu hình bỏ qua hoàn toàn `web.ignoring()` có thể làm request không qua Spring Security filters.

Với assets công khai như `/css/**`, ưu tiên permitAll khi có thể, để vẫn nhận security headers và firewall semantics. Không bỏ chain cho `/actuator/**`, `/error`, `/api/**` hoặc một prefix rộng chỉ vì muốn giảm log; điều này có thể làm lộ endpoint.

Reactive tương tự về mục tiêu: một authorization rule `permitAll` **không** có nghĩa bỏ toàn bộ `WebFilterChainProxy`. Nhưng API cấu hình bỏ qua khác MVC; không sao chép `WebSecurityCustomizer.ignoring()` từ Servlet sang WebFlux.

Nhớ rằng `requestMatchers("/public").permitAll()` chỉ quyết định quyền. Các policy khác như CSRF trên unsafe request, CORS, custom filters hoặc firewall vẫn có thể ảnh hưởng kết quả. Nếu muốn một POST public thật sự, cần thiết kế đúng các filter, không chỉ gắn permitAll.

## 16. Method security là lớp bảo vệ bổ sung

URL rule chỉ bảo vệ HTTP path ở web layer. Một service có thể được gọi từ scheduler, message listener, internal method hoặc endpoint khác. Method security giúp kiểm quyền tại boundary nghiệp vụ.

**Servlet/MVC:**

~~~java
// Fragment minh họa; class cần @Configuration bật method security.
@EnableMethodSecurity

// Trong Spring-managed service:
@PreAuthorize("hasRole('ADMIN')")
public Report getPrivateReport() {
    return loadReport();
}
~~~

**Reactive/WebFlux:**

~~~java
// Fragment minh họa; class cần @EnableReactiveMethodSecurity.
@EnableReactiveMethodSecurity

@PreAuthorize("hasRole('ADMIN')")
public Mono<Report> getPrivateReport() {
    return reportRepository.findReport();
}
~~~

Đây là các đoạn **không độc lập**: `Report` và `reportRepository` là types giả định. Với reactive method security, method trả Publisher và context phải được truyền đúng vào subscription. Không dùng plain `Report` và mong Reactive Context tự được áp giống `Mono<Report>`. Ở cả hai stack, proxy self-invocation có thể làm annotation không được áp dụng trong một số cấu hình; cần kiểm method security ở boundary thật.

Cần kiểm cả role-based authorization và **object-level access control**: USER có thể được GET `/orders/{id}` nhưng chỉ được đọc order của chính họ hoặc tenant. `authenticated()` không xác nhận quyền sở hữu record.

## 17. Kiểm thử bảo mật: không chỉ assert trang trả 200

Một ma trận test tối thiểu:

| Test | Vì sao cần | Kỳ vọng |
| --- | --- | --- |
| Anonymous GET public | Rule permitAll | 200 |
| Anonymous GET private | Auth entry point hoạt động | 401 hoặc redirect theo config |
| USER GET own endpoint | Authentication + authorization | 200 |
| USER GET admin | RBAC | 403 |
| ADMIN GET admin | Role mapping | 200 |
| Anonymous GET route mới chưa khai rule | Fallback deny/authenticated | Không tự 200 public |
| POST không có CSRF token ở cookie/session web | CSRF policy | 403 khi CSRF áp dụng |
| CORS preflight | Browser integration | Không bị auth chặn sai |
| Path /admin/x và /admin-evil | Matcher boundaries | Không mở rộng quyền nhầm |
| API path có trailing slash/case/encoding | Path semantics | Policy đúng theo mapping |
| Multiple chains, path khớp 2 matcher | Chain priority | Chỉ chain ưu tiên đầu tiên được chọn |
| OAuth2/JWT hết hạn/sai issuer | Token validation | 401 hoặc error theo contract |
| Resource owner khác user | Object-level auth | 403/404 theo chính sách không lộ dữ liệu |

### Servlet tests

Dùng Spring Security Test + MockMvc:

~~~java
// Fragment JUnit/MockMvc, chỉ dùng trong project có test starters.
mockMvc.perform(get("/public"))
    .andExpect(status().isOk());

mockMvc.perform(get("/admin").with(httpBasic("learner", "learner-demo-123")))
    .andExpect(status().isForbidden());

mockMvc.perform(get("/admin").with(httpBasic("admin", "admin-demo-123")))
    .andExpect(status().isOk());
~~~

Các import và test dependency không nằm trong project tối giản ở mục 7. Với Boot 4.x, dùng test starters tương thích WebMVC/Security Test, không copy dependency Boot 3.x cũ một cách mù quáng. Với unit test cấu hình, phải áp Spring Security filter chain vào MockMvc, không dùng standaloneSetup thiếu filters rồi kết luận endpoint an toàn.

### Reactive tests

Với WebFlux dùng `WebTestClient` và `spring-security-test`/reactor-test tùy test:

~~~java
// Fragment minh họa, yêu cầu WebTestClient đã được bind vào app security.
webTestClient.get().uri("/public")
    .exchange()
    .expectStatus().isOk();

webTestClient.get().uri("/admin")
    .headers(h -> h.setBasicAuth("learner", "learner-demo-123"))
    .exchange()
    .expectStatus().isForbidden();

webTestClient.get().uri("/admin")
    .headers(h -> h.setBasicAuth("admin", "admin-demo-123"))
    .exchange()
    .expectStatus().isOk();
~~~

Nếu bind trực tiếp controller mà không tích hợp security WebFilters, kết quả có thể **false positive**. Test ít nhất một suite thực sự chạy với security auto-configuration hoặc chain beans, kiểm route và custom filter/claims.

## 18. Gỡ lỗi: thấy 401, 403, 404 hay bean không tạo?

### Quy trình chẩn đoán

1. **WebApplicationType** của app là Servlet hay Reactive? Kiểm dependencies, logs embedded server và có `DispatcherServlet` hay `DispatcherHandler`.
2. Bean security đúng type đã được tạo chưa? `SecurityFilterChain` dùng HttpSecurity, `SecurityWebFilterChain` dùng ServerHttpSecurity.
3. Request có khớp **chain matcher** hay không? Khi nhiều chains, kiểm `@Order`, prefixes và fallback.
4. Nếu chain khớp, rule authorization nào được chọn? `requestMatchers`/`pathMatchers` có ưu tiên đúng chưa?
5. HTTP authentication mechanism nào đang bật? Basic, form login, bearer, OAuth2; có credential/issuer/decoder đúng?
6. CSRF có chặn unsafe HTTP method trước khi controller chạy không?
7. CORS preflight có bị yêu cầu auth do cấu hình thứ tự sai không?
8. Request đã qua controller chưa? 404 có thể do không có route, không phải do security.
9. Có method security, owner/tenant rule hoặc exception handler thêm 403 không?
10. Reverse proxy, gateway, TLS, forwarded headers, multiple contexts có thay URL/path/Authorization không?

### Bảng lỗi thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Bean `SecurityFilterChain` không dùng trong WebFlux | Sai loại stack | Dùng `SecurityWebFilterChain`/`ServerHttpSecurity` |
| Bean `SecurityWebFilterChain` không xử lý MVC | Đang chạy Servlet | Dùng `SecurityFilterChain`/`HttpSecurity` |
| App thêm WebFlux dependency nhưng vẫn Servlet | MVC starter hiện diện, Boot ưu tiên MVC | Chọn rõ web application type và starters |
| `/admin` được public ngoài ý muốn | Rule permitAll rộng đứng trước | Đặt rule cụ thể trước; test matcher |
| Một URL không qua Spring Security | Không có chain match và thiếu fallback | Thêm fallback auth/denyAll |
| Có `@Order(1)` chain API mà fallback không chạy | First-match behavior là đúng | Đặt policy trong API chain đang được chọn |
| 401 dù gửi Basic | Password sai, encoder mismatch, không bật httpBasic | Kiểm encoder, AuthenticationProvider, HTTPS |
| 403 với POST dù GET thành công | CSRF token thiếu hoặc authorization từ chối | Kiểm CSRF config/token và quyền |
| 302 thay vì 401 cho anonymous | Form login entry point đang bật | Chọn auth mechanism phù hợp API |
| USER có `ADMIN` string nhưng `hasRole("ADMIN")` fail | Thiếu `ROLE_` prefix trong authorities | Dùng `roles("ADMIN")` hoặc hasAuthority đúng |
| Browser báo CORS mặc dù cURL được | Preflight/cors/headers không khớp | Cấu hình CORS đúng và kiểm OPTIONS |
| Reactive principal rỗng trong custom thread | Mất Reactor Context hoặc dùng ThreadLocal sai | Dùng ReactiveSecurityContextHolder/ServerWebExchange |
| Custom filter chạy hai lần trong MVC | Đăng ký vừa Servlet vừa Security | Chỉ đăng ký một nơi hoặc disable auto registration |
| Đổi matcher nhưng Actuator vẫn public | Một management context/chain khác | Kiểm actuator exposure/security riêng |
| Unit test 200 nhưng prod 403 | Test không attach security filters | Dùng security-aware MockMvc/WebTestClient |
| Bỏ CSRF toàn site để sửa Postman | Đánh đổi bảo mật không cần thiết | Chỉ chỉnh khi threat model xác nhận |
| Lộ dữ liệu tenant dù authenticated | Thiếu object-level authorization | Kiểm owner/tenant ở service/repository |
| Custom filter WebFlux block JDBC | Chặn event loop và tăng latency | Dùng non-blocking I/O hoặc offload đúng cách |

### Logging khi debug

~~~properties
# Chỉ bật trong môi trường test/debug kiểm soát.
logging.level.org.springframework.security=DEBUG
~~~

DEBUG có thể in danh sách filter trong Servlet và thông tin decisions ở một số tầng. Khi debug sâu, TRACE có thể tốn tài nguyên và rò metadata; không bật thường xuyên ở production. Không bao giờ log Basic Authorization, JWT, password, session cookie hay OAuth2 refresh token.

Có thể kiểm tra Actuator bean/conditions khi được cấp quyền phù hợp, nhưng các endpoint quản trị có thể lộ cấu hình nếu expose công khai. Không bật `/actuator/beans` trên internet chỉ để xem chain.

## 19. Khi chuyển MVC sang WebFlux: checklist migration

Không coi migration là đổi `SecurityFilterChain` thành `SecurityWebFilterChain` bằng tìm/thay chuỗi. Ít nhất cần kiểm:

1. **Web stack thật:** không mang `jakarta.servlet.Filter` sang server Reactive Netty.
2. **URL/matcher:** Servlet RequestMatcher khác ServerWebExchangeMatcher; cấu hình chain priority và rule phải được viết lại.
3. **Authentication:** `UserDetailsService`/provider synchronous vs `ReactiveUserDetailsService`/reactive manager; không chạy JDBC/blocking auth trên event loop.
4. **Session:** Servlet HttpSession/SecurityContextRepository khác WebSession/ServerSecurityContextRepository.
5. **Security context:** ThreadLocal không phải Reactor Context; dùng reactive method security và principal API phù hợp.
6. **CSRF/CORS:** cấu hình DSL và request matchers khác nhau; không tắt mặc định.
7. **Filters:** filter order, interface, exception handling và request body access khác; custom servlet filter cần thiết kế lại.
8. **JWT/OAuth2:** chọn reactive decoder/authorization manager; xác minh issuer, audience, clock skew, keys.
9. **Methods:** với WebFlux, service gọi blocking repositories phải offload; custom auth code cần tránh `.block()`.
10. **Tests:** thay MockMvc bằng WebTestClient khi thích hợp, bảo đảm bind security filters thật.
11. **Error contract:** so sánh 401/403/302, headers, WWW-Authenticate, CSRF errors, CORS preflight.
12. **Object-level rules:** ownership/tenant checks phải giữ nguyên, bất kể stack.

Nếu ứng dụng chủ yếu dùng blocking JDBC/JPA và Servlet MVC đáp ứng yêu cầu, **không cần chuyển sang WebFlux chỉ để có SecurityWebFilterChain**. SecurityFilterChain của Servlet là lựa chọn đúng cho MVC, không “cũ” hay kém an toàn hơn chỉ vì API sync.

## 20. Những câu hỏi tự kiểm tra có đáp án

**A.** Có thể khai `@Bean SecurityFilterChain` trong một WebFlux chạy Reactor Netty rồi kỳ vọng Spring Security bảo vệ WebFilter pipeline không?

**Đáp án:** Không. Servlet SecurityFilterChain dùng HttpSecurity/jakarta.servlet.Filter; WebFlux dùng SecurityWebFilterChain/ServerHttpSecurity và WebFilter.

**B.** Ứng dụng có chain A `securityMatcher("/api/**")` order=1, chain B fallback order=2. User gọi `/api/admin` nhưng thiếu quyền. B có được thử không?

**Đáp án:** Không. A đã match; authorization trong A từ chối và không fallback sang B. Điều chỉnh rule của A chứ không trông vào B.

**C.** `requestMatchers("/api/**").permitAll()` có được đặt trước `requestMatchers("/api/admin/**").hasRole("ADMIN")` không?

**Đáp án:** Không nếu muốn bảo vệ admin; rule rộng có thể match trước. Đặt rule admin cụ thể trước, cuối cùng mới là fallback.

**D.** Vai trò `hasRole("ADMIN")` mong đợi authority nào?

**Đáp án:** Theo convention là `ROLE_ADMIN`. `roles("ADMIN")` tạo authority tương ứng; nếu muốn kiểm một chuỗi khác, dùng hasAuthority với chuỗi chính xác.

**E.** Vì sao HTTP POST có Basic username/password hợp lệ vẫn có thể bị 403?

**Đáp án:** CSRF protection mặc định có thể yêu cầu token cho unsafe methods; 403 không nhất thiết là sai password/role. Kiểm CSRF và quy tắc auth trước khi tắt bất kỳ protection nào.

**F.** Controller reactive có nên gọi `SecurityContextHolder.getContext()` trong `flatMap` để đọc user không?

**Đáp án:** Không coi ThreadLocal là nguồn đúng trong reactive context. Sử dụng `ReactiveSecurityContextHolder.getContext()` hoặc `ServerWebExchange.getPrincipal()`.

**G.** Khi thêm cả MVC và WebFlux starter vào Spring Boot, có chắc app sẽ dùng SecurityWebFilterChain?

**Đáp án:** Không. Boot thường ưu tiên Servlet MVC application type khi cả hai cùng có; phải kiểm runtime/dependencies, không suy từ sự tồn tại của WebClient.

**H.** Có thể dùng `permitAll()` cho asset công khai thay cho bỏ qua hoàn toàn security filter chain không?

**Đáp án:** Thường nên. PermitAll giữ những filter/headers phù hợp, còn bypass hoàn toàn có thể bỏ cả những lớp bảo vệ khác.

**I.** Vì sao GET `/orders/123` authenticated chưa đủ chắc chắn được xem dữ liệu?

**Đáp án:** Authentication chỉ xác thực người gọi; authorization cần kiểm quyền với object/tenant. User A không tự có quyền đọc order của user B.

**J.** CORS và CSRF có thay thế nhau không?

**Đáp án:** Không. CORS điều khiển quyền browser đọc/gửi request cross-origin theo chính sách; CSRF bảo vệ các thao tác dùng credential tự động gửi. Cần phân tích cả hai.

## 21. Tài liệu chính thức

- [Spring Security — Servlet Security Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html) — DelegatingFilterProxy, FilterChainProxy, SecurityFilterChain và thứ tự filters.
- [Spring Security — Servlet Java Configuration](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html) — HttpSecurity, nhiều chain, securityMatcher và requestMatchers.
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html) — authorization rules, permitAll, hasRole.
- [Spring Security — WebFlux Security Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html) — ServerHttpSecurity, SecurityWebFilterChain, multiple chains.
- [Spring Security — Reactive Authorization and Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html) — ReactiveSecurityContextHolder và @EnableReactiveMethodSecurity.
- [Spring Security — CSRF in Servlet Applications](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html).
- [Spring Security — CSRF in WebFlux Applications](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html).
- [Spring Security — CORS for Servlet](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html).
- [Spring Security — CORS for Reactive](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html).
- [Spring Boot — Spring Security for Servlet and WebFlux](https://docs.spring.io/spring-boot/reference/web/spring-security.html).
- [Spring Boot — Starter and Build Systems](https://docs.spring.io/spring-boot/reference/using/build-systems.html).
- [Spring Security — Servlet Path Matching CVE-2026-22753](https://spring.io/security/cve-2026-22753/) — lưu ý các phiên bản Spring Security 7.0.0–7.0.4 bị ảnh hưởng trong điều kiện đặc thù; dùng phiên bản đã vá.

**Kết luận:** `SecurityFilterChain` là cơ chế của **Servlet MVC** và `SecurityWebFilterChain` là cơ chế của **WebFlux reactive**. Hai stack cùng có khái niệm chain ưu tiên, authentication và authorization, nhưng filter, matcher, context và builder khác nhau. Hãy có **fallback bảo vệ mọi route**, đặt rule cụ thể trước rule rộng, giữ CSRF/CORS đúng mô hình, kiểm object-level permissions và dùng integration tests với security filters thật.