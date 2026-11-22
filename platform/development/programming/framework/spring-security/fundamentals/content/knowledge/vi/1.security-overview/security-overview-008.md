# Hai mô hình thực thi Servlet và reactive trong hệ sinh thái Spring Security

## 1. Cùng mục tiêu bảo mật, khác cách xử lý HTTP

Spring Security là bộ công cụ xác thực (authentication), phân quyền (authorization) và bảo vệ ứng dụng Java. Trong hệ sinh thái Spring, một ứng dụng web có thể chạy theo **Servlet stack** (thường là Spring MVC) hoặc **reactive stack** (Spring WebFlux). Cả hai cùng dùng những khái niệm như `Authentication`, `GrantedAuthority`, `SecurityContext`, `PasswordEncoder`, nguyên tắc chặn truy cập trước khi tới nghiệp vụ và các cơ chế như HTTP Basic, OAuth2 Resource Server, bảo vệ CSRF. Nhưng **bộ lọc, cấu hình, cách lấy danh tính và hợp đồng bất đồng bộ là khác nhau**.

- **Servlet/MVC:** mô hình xử lý dựa trên Servlet API, dùng `HttpServletRequest`, `HttpServletResponse` và các `Filter`. Request thường được xử lý trên một luồng của container trong phần lớn vòng đời đồng bộ, dù Spring MVC vẫn hỗ trợ xử lý bất đồng bộ.
- **Reactive/WebFlux:** dựa trên `Publisher`, `Mono`, `Flux`, `ServerWebExchange` và `WebFilter`. Luồng xử lý là một pipeline có thể bất đồng bộ, không chặn, dùng ít luồng để phục vụ nhiều kết nối *khi các thành phần I/O cũng không chặn*. WebFlux có thể chạy trên Reactor Netty hoặc các server được hỗ trợ khác.

**Ý chính:** “Servlet” và “reactive” ở đây là hai mô hình thực thi HTTP của *cùng hệ sinh thái bảo mật*, không phải hai cơ chế cấp quyền độc lập hoặc hai cách mã hóa mật khẩu. Reactive cũng không đồng nghĩa với tự động nhanh hơn hay an toàn hơn.

## 2. Luồng request và nơi Spring Security tham gia

### 2.1. Servlet stack

~~~text
Client
  -> Servlet container (Tomcat/Jetty...)
  -> DelegatingFilterProxy
  -> FilterChainProxy (Spring Security)
  -> SecurityFilterChain phù hợp, gồm các Servlet Filter theo thứ tự
  -> DispatcherServlet -> Spring MVC Controller -> Service
  -> HTTP response
~~~

`DelegatingFilterProxy` nối thế giới Servlet container với Spring bean. `FilterChainProxy` chọn **`SecurityFilterChain` đầu tiên khớp request**; các filter trong chain làm những việc như nạp/lưu ngữ cảnh bảo mật theo cấu hình, xác thực thông tin, xử lý lỗi và kiểm tra quyền trước khi đi vào controller. Với nhiều chain, thứ tự và `securityMatcher` quyết định chain nào bảo vệ từng URL. Không được coi `requestMatchers` trong quy tắc phân quyền là cách thay thế việc chọn chain.

API cấu hình điển hình là **`HttpSecurity` → `SecurityFilterChain`**, với `authorizeHttpRequests`, `requestMatchers`, `httpBasic`, `formLogin`, `csrf`, `oauth2ResourceServer`. Với request đồng bộ, mã hiện tại thường truy cập `SecurityContextHolder`; chiến lược mặc định dùng `ThreadLocal` và Spring Security quản lý việc dọn ngữ cảnh sau request. Không mặc định suy ra ngữ cảnh này tự truyền sang mọi luồng do ứng dụng tự tạo.

### 2.2. Reactive stack

~~~text
Client
  -> HTTP server (ví dụ Reactor Netty)
  -> WebFilterChainProxy (Spring Security)
  -> SecurityWebFilterChain phù hợp, gồm các WebFilter
  -> DispatcherHandler / WebFlux handler
  -> Mono/Flux và các tác vụ I/O bất đồng bộ
  -> HTTP response khi publisher hoàn tất
~~~

Spring Security WebFlux đặt các `WebFilter` vào `SecurityWebFilterChain`; đây **không phải** `jakarta.servlet.Filter`. Cấu hình điển hình là **`ServerHttpSecurity` → `SecurityWebFilterChain`**, với `authorizeExchange`, `pathMatchers`, `httpBasic`, `csrf` và các API dành cho reactive.

Danh tính đã xác thực được đưa vào **Reactor Context** của luồng xử lý, truy cập bằng `ReactiveSecurityContextHolder`. Điều này phù hợp với việc các bước `Mono`/`Flux` có thể chạy trên những luồng khác nhau; phụ thuộc vào `ThreadLocal` trong mã reactive có thể dẫn tới mất hoặc nhầm ngữ cảnh. Reactive Security xử lý chuỗi publisher khi có subscription; tạo `Mono` không có nghĩa logic bên trong đã chạy.

### 2.3. So sánh nhanh

| Khía cạnh | Servlet / Spring MVC | Reactive / Spring WebFlux |
| --- | --- | --- |
| Abstraction HTTP | `HttpServletRequest` / `HttpServletResponse` | `ServerWebExchange` |
| Cơ chế filter bảo mật | `FilterChainProxy`, `SecurityFilterChain`, Servlet `Filter` | `WebFilterChainProxy`, `SecurityWebFilterChain`, `WebFilter` |
| DSL cấu hình | `HttpSecurity`, `authorizeHttpRequests` | `ServerHttpSecurity`, `authorizeExchange` |
| Ghép điều kiện đường dẫn | `requestMatchers("/api/**")` | `pathMatchers("/api/**")` |
| Lấy danh tính | `SecurityContextHolder` (mặc định `ThreadLocal`) | `ReactiveSecurityContextHolder` (Reactor Context) |
| Dịch vụ tra cứu user | `UserDetailsService` | `ReactiveUserDetailsService` |
| Quản lý xác thực | `AuthenticationManager` / `AuthenticationProvider` | `ReactiveAuthenticationManager` |
| Quyền ở method | `@EnableMethodSecurity`, `@PreAuthorize` | `@EnableReactiveMethodSecurity`, `@PreAuthorize` trên publisher |
| Kiểm thử web thường gặp | `MockMvc` | `WebTestClient` |
| Phù hợp I/O | JDBC/JPA, API và SDK blocking truyền thống | I/O reactive xuyên suốt như `WebClient`, R2DBC, reactive driver |

Bảng mô tả các API điển hình. Servlet cũng có cơ chế async; WebFlux không bảo đảm non-blocking nếu bên trong vẫn gọi JDBC, `Thread.sleep` hoặc `block()`.

## 3. Phần dùng chung: xác thực, phân quyền và ngữ cảnh

1. **Authentication** mô tả chủ thể và các quyền (authorities) sau khi xác thực; ví dụ người dùng “alice” có quyền `ROLE_USER`. `hasRole("ADMIN")` theo mặc định tìm authority `ROLE_ADMIN`.
2. **Authentication** trả lời “Ai đang gọi?”. **Authorization** trả lời “Người đó có quyền thực hiện thao tác này không?”. Có thể xác thực thành công và vẫn nhận HTTP 403.
3. **SecurityContext** chứa `Authentication` hiện hành; cơ chế *lưu và truyền* context khác nhau theo stack. Không dùng `SecurityContextHolder.getContext()` làm cách chung để đọc danh tính bên trong reactive pipeline.
4. **401 Unauthorized** thường có nghĩa client chưa có thông tin xác thực hợp lệ; **403 Forbidden** nghĩa truy cập bị từ chối dù đã xác thực hoặc do một biện pháp bảo vệ khác như CSRF. Header thách thức và response body thay đổi theo cơ chế cấu hình.
5. Cả hai đều có session và có thể triển khai API stateless bằng token. Servlet thường tích hợp `HttpSession`, WebFlux có `WebSession`; **chọn stateless/session là quyết định kiến trúc riêng**, không mặc định do tên stack quyết định.

Ví dụ đọc danh tính trong dịch vụ Servlet đã nằm trong security context:

~~~java
String username = SecurityContextHolder.getContext()
    .getAuthentication()
    .getName();
~~~

Đây là đoạn trích đặt trong phương thức đã xác thực; để biên dịch cần import `org.springframework.security.core.context.SecurityContextHolder`. Trong WebFlux, biểu diễn tương ứng là một publisher:

~~~java
Mono<String> username = ReactiveSecurityContextHolder.getContext()
    .map(context -> context.getAuthentication().getName());
~~~

Đây cũng là đoạn trích, cần import `reactor.core.publisher.Mono` và `org.springframework.security.core.context.ReactiveSecurityContextHolder`; publisher phải được trả về/gắn vào pipeline có security context. Dùng `subscribe()` thủ công để lấy giá trị rồi gán biến ngoài pipeline là một lỗi thiết kế phổ biến.

## 4. Thực hành: cùng một chính sách bảo mật trên hai runtime

Ta dựng **hai dự án Spring Boot riêng** cùng có ba endpoint: `GET /public` không yêu cầu đăng nhập, `GET /me` yêu cầu đăng nhập, `GET /admin` yêu cầu vai trò ADMIN. Để tập trung vào runtime, hai dự án dùng HTTP Basic và tài khoản in-memory. Chỉ dùng những mật khẩu ví dụ dưới đây khi chạy trên máy học tập; triển khai thật phải lưu hash an toàn, bảo vệ HTTPS và chọn nguồn user phù hợp.

Yêu cầu: **JDK 17+**, **Maven 3.9+**. Ví dụ dùng Spring Boot **3.3.5**, thuộc dòng Spring Security 6.x. Tạo hai thư mục độc lập `servlet-demo` và `reactive-demo`. Mỗi thư mục có một `pom.xml` và một tệp Java như hướng dẫn.

### 4.1. Maven cho Servlet

Tạo `servlet-demo/pom.xml`:

~~~xml
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
    <groupId>demo</groupId>
    <artifactId>security-runtime-demo</artifactId>
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

Tạo `servlet-demo/src/main/java/demo/servlet/ServletApp.java`:

~~~java
package demo.servlet;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ServletApp {
    public static void main(String[] args) {
        SpringApplication.run(ServletApp.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
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
                .password(encoder.encode("secret"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-secret"))
                .roles("ADMIN")
                .build()
        );
    }
}

@RestController
class ServletEndpoints {
    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/me")
    String me() {
        return SecurityContextHolder.getContext()
            .getAuthentication().getName();
    }

    @GetMapping("/admin")
    String adminPage() {
        return "admin";
    }
}
~~~

Trong `servlet-demo`, chạy `mvn spring-boot:run`. `SecurityFilterChain` là bean cấu hình bảo mật được Spring Boot sử dụng cho Servlet runtime. Ở đây `/public` được phép truy cập vô danh; `/admin` kiểm tra vai trò; các đường dẫn còn lại yêu cầu người dùng hợp lệ. `httpBasic` đọc thông tin xác thực ở request; `formLogin` được tắt có chủ đích để các câu trả lời API dễ quan sát. CSRF vẫn theo mặc định của Spring Security và demo chỉ sử dụng GET.

### 4.2. Maven cho WebFlux

Tạo `reactive-demo/pom.xml` bằng **toàn bộ** nội dung Maven ở mục 4.1 rồi thay **duy nhất** artifact `spring-boot-starter-web` bằng `spring-boot-starter-webflux`. Giữ `spring-boot-starter-security`. Bằng cách đó ta có dự án WebFlux riêng, không trộn cả hai web starter trong cùng ứng dụng.

Tạo `reactive-demo/src/main/java/demo/reactive/ReactiveApp.java`:

~~~java
package demo.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class ReactiveApp {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveApp.class, args);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/public").permitAll()
                .pathMatchers("/admin").hasRole("ADMIN")
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
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
                .password(encoder.encode("secret"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-secret"))
                .roles("ADMIN")
                .build()
        );
    }
}

@RestController
class ReactiveEndpoints {
    @GetMapping("/public")
    Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping("/me")
    Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName());
    }

    @GetMapping("/admin")
    Mono<String> adminPage() {
        return Mono.just("admin");
    }
}
~~~

Trong `reactive-demo`, chạy `mvn spring-boot:run` khi ứng dụng Servlet đã dừng (cả hai cùng dùng cổng mặc định 8080). Chính sách quyền tương đương Servlet, nhưng cấu hình đi qua `ServerHttpSecurity`, `SecurityWebFilterChain` và danh tính lấy từ Reactor Context. `MapReactiveUserDetailsService` phục vụ ví dụ học tập bằng lookup reactive từ bộ nhớ; dùng database reactive thực tế thì repository, kết nối và các thư viện tham gia cũng phải hỗ trợ non-blocking.

### 4.3. Gọi thử và đối chiếu kết quả

Chạy cùng bộ lệnh sau cho **mỗi** ứng dụng tại cổng 8080:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u alice:secret http://localhost:8080/me
curl -i -u alice:secret http://localhost:8080/admin
curl -i -u admin:admin-secret http://localhost:8080/admin
~~~

| Request | HTTP status dự kiến | Nội dung response khi thành công |
| --- | --- | --- |
| `GET /public`, không credentials | 200 | `public` |
| `GET /me`, không credentials | 401 | Có thể không có body hoặc body lỗi do cấu hình |
| `GET /me`, Alice | 200 | `alice` |
| `GET /admin`, Alice chỉ có USER | 403 | Body lỗi tùy cấu hình |
| `GET /admin`, Admin có ADMIN | 200 | `admin` |

Header do server sinh ra (ngày, content type, thách thức `WWW-Authenticate`...) có thể khác nhau; **điều cần kiểm chứng là status và body nêu trong bảng**. Kết quả hành vi bảo mật tương đồng, mặc dù Servlet xử lý trên Servlet Filter chain còn WebFlux dùng reactive WebFilter chain.

## 5. Khi nào dùng API và pattern nào?

**Phân quyền theo đường dẫn.** Dùng `authorizeHttpRequests`/`requestMatchers` với Servlet, và `authorizeExchange`/`pathMatchers` với WebFlux. Với nhiều chain, khai báo matcher chọn chain và thứ tự rõ ràng; luôn kiểm tra có chain bao phủ những endpoint còn lại để không tạo khoảng trống bảo mật.

**Phân quyền ở service.** Spring Security hỗ trợ annotation như `@PreAuthorize("hasAuthority('SCOPE_read')")` trong cả hai hệ, nhưng phải bật đúng cơ chế: `@EnableMethodSecurity` cho Servlet/imperative và `@EnableReactiveMethodSecurity` cho reactive. Với reactive, áp dụng kiểm tra trên service trả `Mono`/`Flux` và sử dụng reactive context. Không nhầm method security với việc tự động bảo vệ mọi URL; nên phối hợp với HTTP security.

**Tích hợp xác thực.** Phần Servlet thường sử dụng `UserDetailsService` và `AuthenticationManager`; phần reactive sử dụng `ReactiveUserDetailsService` và `ReactiveAuthenticationManager`. Những chức năng OAuth2/OIDC/JWT có thể tồn tại ở cả hai stack nhưng lớp, chữ ký và cách ghép chuỗi cần đúng stack. Dùng một thư viện xác thực blocking trực tiếp trên event loop sẽ làm mất lợi ích reactive.

**CSRF và trạng thái.** CSRF là vấn đề riêng của request dùng thông tin xác thực tự được trình duyệt gắn vào (ví dụ cookie/session). HTTP Basic trong trình duyệt cũng có thể được gửi tự động, nên **không tắt CSRF chỉ vì endpoint trả JSON hoặc dùng HTTP Basic**. Với API thực sự dùng bearer token được client đặt trong Authorization header và không dựa vào credential tự gửi, có thể đánh giá chính sách CSRF theo threat model. Cả Servlet và WebFlux đều hỗ trợ cấu hình này; ứng dụng học tập phía trên để CSRF mặc định và chỉ có GET.

**CORS, HTTPS, session, exception handling.** Cả hai stack cần quyết định riêng về nguồn gọi chéo miền, TLS, session/token, xử lý 401/403 và log an toàn. CORS không thay thế xác thực hay phân quyền. Nếu dùng bearer JWT, định nghĩa rõ issuer, audience, thuật toán, vòng đời token và xử lý quyền ở phía server; đổi stack không giải quyết các quyết định đó.

## 6. Chọn stack theo luồng I/O của hệ thống

- Chọn **Servlet/MVC** khi hệ thống dùng nhiều thư viện blocking (điển hình JPA/JDBC), có sẵn MVC controller/filter và đội ngũ quen xử lý imperative. Đây là lựa chọn phù hợp cho nhiều ứng dụng CRUD; không cần reactive chỉ để hỗ trợ nhiều người dùng.
- Chọn **WebFlux** khi luồng từ HTTP vào tới các API, database, message client chủ yếu là non-blocking, phải phục vụ nhiều kết nối đồng thời và muốn kiểm soát pipeline bất đồng bộ. Cần đo latency/throughput với workload thực tế, kể cả nhu cầu CPU và backpressure.
- Nếu bắt buộc gọi thư viện blocking trong WebFlux, việc chuyển sang scheduler chuyên dụng có thể tránh khóa event loop trong một số tình huống, nhưng **không biến thư viện blocking thành non-blocking**; phải đo tài nguyên và tránh lạm dụng.
- Thêm dependency `spring-boot-starter-webflux` vào ứng dụng có sẵn `spring-boot-starter-web` **thường khiến Spring Boot vẫn auto-configure Spring MVC**, vì WebFlux starter cũng có thể chỉ để dùng `WebClient`. Muốn ứng dụng HTTP reactive thực sự, xác định web application type và dependencies có chủ đích.
- Controller trả `Mono` trong MVC, hoặc gọi `WebClient` từ một service MVC, **không tự đổi Servlet security chain thành reactive chain**.

## 7. Lỗi phổ biến và cách kiểm tra

1. **Dùng sai DSL/filter cho runtime:** Bean `SecurityFilterChain(HttpSecurity)` không thay thế `SecurityWebFilterChain(ServerHttpSecurity)`. Khi không thấy rule chạy, kiểm tra starter đang dùng và Boot khởi tạo MVC hay WebFlux.
2. **Lấy user qua ThreadLocal ở WebFlux:** `SecurityContextHolder` có thể rỗng hoặc sai ngữ cảnh sau các bước bất đồng bộ. Dùng `ReactiveSecurityContextHolder` trong pipeline, hoặc tiêm principal theo cơ chế WebFlux thích hợp.
3. **Chặn event loop:** `block()`, `Thread.sleep()` và JDBC blocking bên trong WebFlux có thể gây nghẽn dù controller trả `Mono`. Kiểm tra call stack I/O, thread và thời gian chờ thực tế.
4. **Nhầm 401 với 403:** không credentials hoặc sai mật khẩu thường là 401; credentials hợp lệ nhưng thiếu role thường là 403. Kiểm tra cả đường xác thực lẫn rule quyền trước khi thay config.
5. **Vô hiệu hóa CSRF tràn lan:** giữ biện pháp bảo vệ phù hợp với cách trình duyệt/client gửi credentials, nhất là khi dùng cookie/session.
6. **Cấu hình nhiều chain nhưng bỏ lọt URL:** matcher và thứ tự quyết định chain được chọn. Viết kiểm thử cho URL public, URL protected, URL admin và URL không khớp rule riêng.
7. **Chỉ dựa vào @PreAuthorize mà không bật method security:** annotation có thể không có tác dụng nếu thiếu `@EnableMethodSecurity` / `@EnableReactiveMethodSecurity` tương ứng.
8. **So sánh hiệu năng theo khẩu hiệu:** WebFlux có chi phí xây dựng, quan sát và debug pipeline; hiệu quả phải được kiểm chứng qua tải, I/O, bộ nhớ và nhu cầu triển khai cụ thể.

## 8. Tự kiểm tra sau bài học

- Mô tả đường đi của một request trước khi tới controller trên Servlet và trên WebFlux; nêu tên hai kiểu chain bảo mật.
- Giải thích vì sao Reactor Context thích hợp để lưu danh tính trong pipeline thay vì dùng riêng `ThreadLocal`.
- Từ bảng thử nghiệm, nêu sự khác biệt giữa request chưa xác thực và request đã xác thực nhưng thiếu vai trò ADMIN.
- Nếu một ứng dụng dùng Spring MVC, JPA và `WebClient`, hãy giải thích tại sao ứng dụng ấy chưa trở thành reactive web server.
- Khi chuyển từ MVC sang WebFlux, hãy liệt kê những API cấu hình, truy cập security context, user service và kiểu I/O phải rà soát lại.

## 9. Tài liệu chính thức

- Spring Security — Servlet architecture: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — Servlet authentication architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — WebFlux security configuration: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — Reactive method security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Boot — Reactive Web Applications: https://docs.spring.io/spring-boot/reference/web/reactive.html
