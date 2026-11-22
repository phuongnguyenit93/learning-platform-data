# Vai trò của `@EnableWebFluxSecurity` và cấu hình tự động trong Spring Security reactive

## 1. Bức tranh tổng quan

Trong ứng dụng **Spring WebFlux**, Spring Security bảo vệ HTTP request bằng các `WebFilter` hoạt động với Reactor (`Mono`/`Flux`). Hai khái niệm thường gặp khi khởi tạo ứng dụng là:

- **`@EnableWebFluxSecurity`**: annotation thuộc **Spring Security**, bật cơ chế cấu hình bảo mật cho WebFlux trong Spring application context.
- **Spring Boot auto-configuration**: dựa vào loại ứng dụng, dependency và các bean sẵn có để tự đăng ký phần cấu hình mặc định. Nếu ứng dụng Boot đã có `spring-boot-starter-webflux` và `spring-boot-starter-security`, thông thường **không cần tự gắn `@EnableWebFluxSecurity`** để có bảo mật HTTP.

Điểm cần phân biệt: *bật hạ tầng bảo mật*, *định nghĩa chính sách HTTP* và *cấp dữ liệu xác thực* là ba trách nhiệm khác nhau. Annotation không tự biến một endpoint thành public; thêm một `SecurityWebFilterChain` không tự tạo kho người dùng; thêm một `ReactiveUserDetailsService` cũng không tự quyết định URL nào được truy cập.

Mục tiêu sau bài học:
1. Giải thích vai trò của `@EnableWebFluxSecurity` và phần tự động do Spring Boot đảm nhiệm.
2. Nhận biết các thành phần `WebFilterChainProxy`, `SecurityWebFilterChain`, `ServerHttpSecurity` và `ReactiveUserDetailsService`.
3. Biết khi nào cần khai báo cấu hình tường minh và điều gì thay đổi khi thêm từng loại bean.
4. Tự chạy ứng dụng Java 17+ và kiểm tra HTTP 200/401/403 tương ứng.

## 2. `@EnableWebFluxSecurity` thực sự làm gì?

`@EnableWebFluxSecurity` thường đặt trên một lớp `@Configuration`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;

@Configuration
@EnableWebFluxSecurity
class SecurityConfig {
}
~~~

Annotation nhập các lớp cấu hình Spring Security cho WebFlux, từ đó thiết lập hạ tầng lọc request, quản lý ngữ cảnh bảo mật và hỗ trợ các bean cấu hình HTTP. Nếu không có `SecurityWebFilterChain` tùy biến, Spring Security cung cấp chính sách mặc định điển hình: yêu cầu xác thực cho mọi request, hỗ trợ form login và HTTP Basic, tạo trang đăng nhập/đăng xuất mặc định khi thích hợp, bật bảo vệ CSRF và các security headers.

Điều **không** được suy ra chỉ từ annotation:
- Nó không phải là công tắc “cho phép tất cả request”.
- Nó không đồng nghĩa với cấu hình người dùng/mật khẩu; trong Spring Boot, phần này thường do `ReactiveUserDetailsServiceAutoConfiguration` cung cấp.
- Nó không thay thế `spring-boot-starter-security` hoặc các thư viện cần có trong classpath.
- Nó không bật phân quyền ở mức phương thức `@PreAuthorize`; việc này cần cấu hình **reactive method security** riêng, thường bằng `@EnableReactiveMethodSecurity`.
- Nó không phải `@EnableWebSecurity`, vốn dành cho mô hình **Servlet/Spring MVC**.

Trong một ứng dụng **không dùng Spring Boot**, việc khai báo `@EnableWebFluxSecurity` là cách tường minh để bật web security (với các dependency và bean tương ứng). Trong ứng dụng **Spring Boot WebFlux**, auto-configuration thường đã làm việc tương đương khi điều kiện phù hợp.

## 3. Các đối tượng nằm ở tầng nào?

~~~text
HTTP request
    │
    ▼
Spring WebFlux WebFilter infrastructure
    │
    ▼
Spring Security WebFilterChainProxy
    │  chọn chuỗi bảo mật khớp request
    ▼
SecurityWebFilterChain
    ├─ các WebFilter xác thực (nếu cơ chế được cấu hình)
    ├─ ngữ cảnh bảo mật / xử lý ngoại lệ
    └─ quy tắc phân quyền URL (AuthorizationWebFilter)
    │
    ▼
Controller / RouterFunction / Handler
~~~

- `WebFilterChainProxy` là thành phần của hạ tầng **reactive web filter**; nó kết nối Spring Security vào chuỗi xử lý WebFlux.
- `SecurityWebFilterChain` là tập các filter và chính sách áp dụng cho một nhóm request. Có thể có nhiều chain; Spring Security lựa chọn chain khớp theo thứ tự.
- `ServerHttpSecurity` là **builder** để khai báo `authorizeExchange`, `httpBasic`, `formLogin`, `csrf`, `oauth2ResourceServer`, v.v. Gọi `http.build()` để tạo `SecurityWebFilterChain`.
- `ReactiveAuthenticationManager` xác minh thông tin đăng nhập theo giao diện reactive; `ReactiveUserDetailsService` cung cấp người dùng cho các cơ chế xác thực phù hợp. `ReactiveUserDetailsService` là nguồn dữ liệu, không phải toàn bộ quy trình xác thực.
- Spring Security reactive truyền `SecurityContext` qua **Reactor Context**; không nên dùng giả định ThreadLocal của Servlet để đọc danh tính trên mọi luồng.

Phân biệt kiểu với Spring MVC:

| WebFlux (reactive) | Servlet/MVC | Vai trò |
| --- | --- | --- |
| `@EnableWebFluxSecurity` | `@EnableWebSecurity` | Bật cấu hình bảo mật của web stack tương ứng |
| `ServerHttpSecurity` | `HttpSecurity` | Builder chính sách HTTP |
| `SecurityWebFilterChain` | `SecurityFilterChain` | Chuỗi filter cho HTTP request |
| `WebFilterChainProxy` | `FilterChainProxy` | Bộ điều phối filter bảo mật |
| `ReactiveUserDetailsService` | `UserDetailsService` | Nguồn người dùng |
| `ReactiveAuthenticationManager` | `AuthenticationManager` | Xử lý xác thực |

Các API ở hai cột không thể tùy tiện thay thế nhau. Một ứng dụng WebFlux có cấu hình `SecurityFilterChain(HttpSecurity)` của Servlet sẽ không có cùng tác dụng với `SecurityWebFilterChain(ServerHttpSecurity)` của reactive.

## 4. Spring Boot tự cấu hình những gì?

Phần này dùng tên lớp ở **Spring Boot 3.3.x** (tên hoặc điều kiện chi tiết có thể thay đổi ở dòng Boot khác).

Khi classpath có các thư viện tương ứng và Spring Boot phát hiện **reactive web application**, các cấu hình quan trọng gồm:

- `ReactiveSecurityAutoConfiguration`: bật hạ tầng Spring Security dành cho WebFlux nếu chưa có cách cấu hình tương đương; phụ thuộc các điều kiện về classpath/web application và có thể nhường chỗ cho `WebFilterChainProxy` đã được định nghĩa.
- `ReactiveUserDetailsServiceAutoConfiguration`: nếu chưa có cơ chế xác thực thay thế phù hợp, tạo `ReactiveUserDetailsService` dựa trên cấu hình `spring.security.user.*`, thông thường là một người dùng trong bộ nhớ.
- Cấu hình mặc định của Spring Security WebFlux: bảo vệ các request theo mặc định, hỗ trợ form login/HTTP Basic và các cơ chế bảo vệ khác theo cấu hình framework.

Ở ứng dụng mới có starter security, user mặc định thường mang tên **`user`** và mật khẩu sinh ngẫu nhiên được thông báo khi khởi động (dành cho development). Giá trị có thể thay qua `spring.security.user.name`, `spring.security.user.password` khi dùng cơ chế user tự động. Đây không phải cấu hình đăng nhập dành cho production.

### 4.1. Điều gì xảy ra khi ta tạo bean riêng?

| Thay đổi trong ứng dụng Boot WebFlux | Kết quả cần hiểu |
| --- | --- |
| Chỉ thêm hai starter WebFlux và Security | Boot cấu hình bảo mật mặc định, bảo vệ endpoint, có user thử nghiệm nếu đủ điều kiện |
| Tự thêm `@EnableWebFluxSecurity`, chưa định nghĩa chain | Bật cấu hình tường minh; **không làm endpoint tự mở** |
| Tạo `@Bean SecurityWebFilterChain` | Dùng chính sách URL do bean đó định nghĩa thay cho chain HTTP mặc định; phần xác thực người dùng có thể vẫn do Boot tạo |
| Tạo `@Bean ReactiveUserDetailsService` | Dùng kho người dùng riêng, Boot không cần tạo user mặc định; quy tắc truy cập HTTP không tự đổi |
| Tạo `@Bean ReactiveAuthenticationManager` | Dùng cơ chế xác thực được cung cấp; cấu hình user mặc định của Boot có thể lùi lại theo điều kiện |
| Tạo `@EnableReactiveMethodSecurity` | Bật bảo mật mức phương thức, bổ sung cho quy tắc filter HTTP |

**Hai kiểu back-off khác nhau:** Spring Boot 3.3 mô tả việc bỏ phần đăng ký hạ tầng web mặc định khi đã có `WebFilterChainProxy`; còn một `SecurityWebFilterChain` tùy biến sẽ thay chính sách HTTP mặc định được chọn. Đây là hai cấp bean khác nhau. Tạo custom chain **không có nghĩa** tự tắt mọi auto-configuration, đặc biệt là phần user mặc định.

Bên cạnh các bean, sự hiện diện của dependency OAuth2 Client/Resource Server có thể làm thay đổi điều kiện auto-configure user mặc định. Vì vậy khi thêm security starter/token provider, hãy quan sát **beans thực tế** và điều kiện auto-configuration, đừng mặc định lúc nào cũng có user `user`.

### 4.2. Lỗi xác định sai web stack

Nếu đồng thời thêm `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot thường ưu tiên **Servlet/MVC**. Việc ứng dụng có dùng `WebClient` không chứng minh nó chạy WebFlux server. Để xây server reactive, ưu tiên dùng `spring-boot-starter-webflux` và tránh vô tình kéo starter MVC. Chỉ ép `spring.main.web-application-type=reactive` khi thực sự chủ động chọn reactive và hiểu các dependency đi kèm.

## 5. Ví dụ đầy đủ Java 17+ với Spring Boot WebFlux

Ví dụ dùng **Spring Boot 3.3.13**, Java 17+, Gradle 8.x; chỉ dùng endpoint GET để tập trung vào WebFlux security. Mục tiêu: cho phép `/public`, buộc đăng nhập ở `/private` và yêu cầu quyền ADMIN tại `/admin`.

### 5.1. Khởi tạo dự án

Cấu trúc tệp:

~~~text
webflux-security-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── ReactiveSecurityDemoApplication.java
    │   ├── DemoController.java
    │   └── SecurityConfig.java
    └── test/java/demo/
        └── ReactiveSecurityDemoApplicationTests.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-security-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

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
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/java/demo/ReactiveSecurityDemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveSecurityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveSecurityDemoApplication.class, args);
    }
}
~~~

`src/main/java/demo/DemoController.java`:

~~~java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class DemoController {

    @GetMapping("/public")
    Mono<String> publicEndpoint() {
        return Mono.just("public");
    }

    @GetMapping("/private")
    Mono<String> privateEndpoint() {
        return Mono.just("private");
    }

    @GetMapping("/admin")
    Mono<String> adminEndpoint() {
        return Mono.just("admin");
    }
}
~~~

**Quan sát auto-configuration trước khi tự viết cấu hình:** tạm thời **chưa tạo `SecurityConfig.java`**. Chạy từ thư mục dự án:

~~~bash
gradle bootRun
~~~

Nếu đã có Gradle Wrapper, dùng `./gradlew bootRun` trên Unix/macOS hoặc `gradlew.bat bootRun` trên Windows. Khi ứng dụng khởi động, Spring Boot có thể in dòng `Using generated security password: ...` (giá trị thay đổi theo lần chạy). Lúc này **`/public` vẫn bị bảo vệ** vì chưa có luật `permitAll`. Request API chưa đăng nhập thường trả HTTP 401 với HTTP Basic; yêu cầu browser chấp nhận HTML có thể được chuyển đến trang đăng nhập (302) do content negotiation. Không nên hard-code một stdout/mật khẩu ngẫu nhiên cho bước này.

### 5.2. Tự định nghĩa chain và kho người dùng

Thêm `src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class SecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .pathMatchers("/admin").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService(
            PasswordEncoder passwordEncoder) {
        UserDetails demo = User.withUsername("demo")
            .password(passwordEncoder.encode("demo-pass"))
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(demo);
    }
}
~~~

Đọc kỹ từng thành phần:
1. `@EnableWebFluxSecurity` khởi tạo cấu hình Spring Security WebFlux một cách tường minh. Trong ứng dụng Boot đã có auto-configuration, annotation này thường **không bắt buộc** nhưng hữu ích để thấy rõ điểm bật hạ tầng. Có thể bỏ nó trong ví dụ Boot này khi điều kiện auto-configuration vẫn thỏa mãn.
2. `@Bean SecurityWebFilterChain` **thay đổi chính sách truy cập**. `/public` cho phép khách chưa đăng nhập; `/admin` cần authority `ROLE_ADMIN` (`hasRole("ADMIN")` tự ghép tiền tố `ROLE_`); các đường dẫn còn lại yêu cầu xác thực.
3. `httpBasic(Customizer.withDefaults())` bật HTTP Basic; `formLogin(form -> form.disable())` loại bỏ form login để kết quả API chưa đăng nhập dễ quan sát là **401**. Đây là lựa chọn **riêng của demo**, không phải hành vi bắt buộc của annotation.
4. `MapReactiveUserDetailsService` thay user tự sinh của Boot bằng user demo. `BCryptPasswordEncoder` mã hóa mật khẩu; trong thực tế user/mật khẩu phải lấy từ cấu hình bí mật hoặc kho danh tính an toàn, không hard-code.
5. Không disable CSRF trong ví dụ vì chỉ dùng HTTP GET. Với POST/PUT/DELETE dựa vào cookie/session, CSRF là cơ chế quan trọng; nếu thiết kế API stateless và cần thay đổi CSRF, phải đánh giá chính sách riêng, không sao chép một lệnh disable vô điều kiện.

Sau khi thêm class, dừng và chạy lại `gradle bootRun`.

### 5.3. Kiểm tra bằng HTTP

Các lệnh sau dành cho bash/Git Bash, dùng trên máy chạy server ở `localhost:8080`:

~~~bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/public
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/private
curl -s -u demo:demo-pass -o /dev/null -w '%{http_code}\n' http://localhost:8080/private
curl -s -u demo:demo-pass -o /dev/null -w '%{http_code}\n' http://localhost:8080/admin
~~~

Khi chạy đúng cấu hình và không có filter khác can thiệp, stdout theo thứ tự:

~~~text
200
401
200
403
~~~

- **200**: `/public` được `permitAll`, không yêu cầu danh tính.
- **401**: `/private` chưa có credentials; HTTP Basic trả yêu cầu xác thực.
- **200**: `demo` có mật khẩu đúng, đủ điều kiện `authenticated()`.
- **403**: `demo` đã đăng nhập nhưng chỉ có `ROLE_USER`, không có `ROLE_ADMIN`.

Đối với Windows PowerShell, có thể dùng `curl.exe` và tùy môi trường đổi đích bỏ body từ `/dev/null` thành `NUL`. Nếu một trình duyệt chuyển hướng về `/login` trong bước mặc định, đó là do form login/content negotiation; sau cấu hình demo ở trên, form login đã tắt.

### 5.4. Kiểm thử tự động với `WebTestClient`

`src/test/java/demo/ReactiveSecurityDemoApplicationTests.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class ReactiveSecurityDemoApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicRouteIsOpen() {
        client.get().uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void privateRouteRequiresLogin() {
        client.get().uri("/private")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void loggedInUserCanAccessPrivateRoute() {
        client.get().uri("/private")
            .headers(headers -> headers.setBasicAuth("demo", "demo-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("private");
    }

    @Test
    void ordinaryUserCannotAccessAdminRoute() {
        client.get().uri("/admin")
            .headers(headers -> headers.setBasicAuth("demo", "demo-pass"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

Chạy `gradle test`; Gradle Wrapper có thể dùng như trên. Khi tất cả kiểm tra thành công, lệnh kết thúc với exit code 0; không nên dự đoán nguyên văn log Gradle vì tùy môi trường. `@SpringBootTest` kiểm tra context và security configuration cùng nhau; `@WebFluxTest` chỉ tải một phần bean và thường cần `@Import` cấu hình security tùy biến nếu muốn kiểm tra cùng các rule đã khai báo.

## 6. So sánh ba cách cấu hình thường gặp

### Cách A — Để Spring Boot làm toàn bộ phần mặc định

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

Không cần `@EnableWebFluxSecurity` hoặc `SecurityWebFilterChain` tự viết khi mục đích chỉ là khởi chạy và quan sát cơ chế mặc định. Tất cả route thường được bảo vệ. Phù hợp để học hoặc khởi tạo nhanh, **không phải thiết kế xác thực production**.

### Cách B — Định nghĩa policy HTTP, để Boot giữ auth mặc định

~~~java
@Configuration
class HttpRules {
    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(ex -> ex
                .pathMatchers("/healthz").permitAll()
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Đây là **đoạn minh họa**, cần các import tương ứng trong dự án. Nó tạo chain tùy biến nhưng **không tự khai báo `ReactiveUserDetailsService`**, vì vậy user mặc định vẫn có thể được Boot cấu hình nếu thỏa điều kiện. Điều này giải thích vì sao sau khi “đã viết security config”, ứng dụng vẫn in mật khẩu ngẫu nhiên.

### Cách C — Định nghĩa cả policy và cơ chế xác thực

Cấu hình đầy đủ ở mục 5 thực hiện cả hai phần: `SecurityWebFilterChain` + `MapReactiveUserDetailsService`. Với ứng dụng nghiệp vụ, thay `MapReactiveUserDetailsService` bằng nguồn dữ liệu reactive hoặc Spring Security OAuth2 Resource Server để kiểm tra JWT/opaque token theo chuẩn đã chọn.

Không nên tự viết parser JWT/password verification thiếu kiểm soát hoặc biến một “không tìm thấy user” thành principal đã đăng nhập. Mọi bước xác thực thực tế cần truyền lỗi và kết quả qua API reactive đúng hợp đồng.

## 7. Khi có nhiều `SecurityWebFilterChain`

Một ứng dụng có thể cần chính sách riêng cho `/api/**` và các trang web còn lại. Khi đó tạo các bean chain với `@Order` và `securityMatcher(...)` để xác định **chuỗi nào được chọn** trước khi áp dụng các luật `authorizeExchange` bên trong.

Ví dụ minh họa **đoạn cấu hình, không phải chương trình Java độc lập**:

~~~java
@Bean
@Order(1)
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**"))
        .authorizeExchange(ex -> ex.anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityWebFilterChain otherChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(ex -> ex.anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Các import cần có gồm `org.springframework.core.annotation.Order`, `org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher` và những loại đã dùng ở mục 5. Trong ví dụ này, `otherChain` là catch-all. Nếu bạn chỉ tạo chain khớp `/api/**` mà bỏ catch-all, request ngoài phạm vi có thể không được bảo vệ bởi chain của ứng dụng theo cách bạn nghĩ. `pathMatchers` là luật truy cập **bên trong chain**, còn `securityMatcher` là điều kiện **chọn chain**; hai khái niệm khác nhau.

Với nhu cầu đơn giản, chỉ một chain có `anyExchange().authenticated()` là dễ kiểm tra hơn.

## 8. Các hiểu nhầm và cách chẩn đoán

| Triệu chứng / hiểu nhầm | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| “Đã thêm `@EnableWebFluxSecurity` mà mọi URL vẫn cần login” | Annotation bật bảo mật, không cấp quyền public | Tạo `SecurityWebFilterChain` với `permitAll` cho route cần mở |
| “Đã tạo chain nhưng vẫn có generated password” | Chuỗi HTTP và nguồn user là hai auto-config khác nhau | Cung cấp `ReactiveUserDetailsService` hoặc `ReactiveAuthenticationManager` phù hợp |
| “Đã cấu hình `SecurityFilterChain(HttpSecurity)` mà WebFlux không hoạt động như kỳ vọng” | Dùng API Servlet thay vì reactive | Dùng `SecurityWebFilterChain(ServerHttpSecurity)` |
| “Endpoint GET hoạt động, POST lại 403” | CSRF cho request thay đổi trạng thái hoặc thiếu quyền | Kiểm tra CSRF token/cách xác thực và các access rules |
| “Test `@WebFluxTest` không dùng rule của ứng dụng” | Test slice không tải đủ custom security bean | Dùng `@Import` đúng config hoặc `@SpringBootTest` |
| “Bất ngờ chạy Spring MVC” | Có cả Web MVC và WebFlux starter | Kiểm tra dependency và `WebApplicationType` |
| “User có ROLE_USER nhưng bị 403 ở admin” | `hasRole("ADMIN")` cần authority `ROLE_ADMIN` | Kiểm tra mapping authorities và access policy |
| “Thêm custom chain làm Actuator mở ngoài ý muốn” | Chưa quy định matcher/rule cho actuator endpoint | Kiểm tra và test riêng các endpoint Actuator |
| “Phương thức `@PreAuthorize` không được kiểm tra” | Chưa bật reactive method security phù hợp | Bật `@EnableReactiveMethodSecurity` và kiểm thử điều kiện |

### 8.1. Dùng condition report để hiểu Boot quyết định gì

Spring Boot có báo cáo điều kiện auto-configuration. Khi cần chẩn đoán bean nào được tạo hoặc bị bỏ qua, chạy:

~~~bash
gradle bootRun --args='--debug'
~~~

Đọc phần **CONDITIONS EVALUATION REPORT** và tìm các lớp reactive security, lý do điều kiện được đáp ứng/chưa đáp ứng. Cờ `--debug` làm log dài hơn; chỉ bật trong môi trường phát triển. Ngoài ra, dùng danh sách bean hoặc công cụ quan sát được kiểm soát để xác định `SecurityWebFilterChain`, `WebFilterChainProxy` và `ReactiveUserDetailsService` có mặt hay không. Không mở công khai endpoint quản trị/chẩn đoán chỉ để debug.

### 8.2. Một số nguyên tắc an toàn

- **Mặc định từ chối** với tài nguyên không khai báo public; giữ rule catch-all được kiểm thử.
- Với Basic auth, bắt buộc dùng HTTPS trong thực tế; ví dụ local chỉ để học.
- Không đặt mật khẩu demo, generated password hoặc token vào source production và log.
- Phân biệt **401** (chưa hoặc không xác thực hợp lệ) với **403** (đã xác thực nhưng thiếu quyền); HTTP status cụ thể còn chịu tác động của entry point, các filter và cơ chế xác thực đã cấu hình.
- Nếu cấu hình Resource Server/JWT, xác minh issuer, audience, chữ ký/hạn dùng và các quy định liên quan bằng thành phần thư viện phù hợp trước khi chấp nhận danh tính.
- Với nhiều chain, kiểm thử cả route thuộc và **ngoài** matcher, bao gồm actuator, error path và static resources nếu ứng dụng có chúng.

## 9. Câu hỏi tự kiểm tra

1. **Dùng Spring Boot WebFlux có starter security thì có bắt buộc thêm `@EnableWebFluxSecurity` không?** Thường không; auto-configuration đã bật WebFlux security khi điều kiện thỏa mãn.
2. **`@EnableWebFluxSecurity` có tự cho `/public` truy cập tự do không?** Không. Cần rule `permitAll` trong chain.
3. **Tạo `SecurityWebFilterChain` tùy biến có tự loại user `user` mặc định không?** Không nhất thiết; phần cấu hình user có điều kiện riêng.
4. **Đối tượng nào dùng để khai báo `pathMatchers`, `httpBasic` và `formLogin`?** `ServerHttpSecurity`.
5. **`SecurityWebFilterChain` có giống `WebFilterChainProxy` không?** Không. Chain là tập chính sách/filter; proxy chọn và thực thi chain phù hợp cho request.
6. **`hasRole("ADMIN")` thực tế so khớp authority nào theo quy ước thông thường?** `ROLE_ADMIN`.
7. **Dùng `@EnableWebSecurity` để bảo vệ handler WebFlux có đúng không?** Không; đó là cấu hình Servlet.
8. **Cần annotation gì để bật `@PreAuthorize` trong reactive method security?** `@EnableReactiveMethodSecurity` (với cấu hình phù hợp).
9. **Vì sao test đầy đủ security nên ưu tiên `@SpringBootTest` hoặc import custom config vào slice?** Vì test slice có thể không tự tải chuỗi security tự khai báo.
10. **Vì sao `/admin` trả 403 khi gọi bằng user demo?** User đã được xác thực nhưng thiếu `ROLE_ADMIN`.

## 10. Tài liệu chính thức

- Spring Boot 3.3 — Spring Security và WebFlux Security: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
- Spring Boot 3.3 — `ReactiveSecurityAutoConfiguration`: https://docs.spring.io/spring-boot/3.3.13/api/java/org/springframework/boot/autoconfigure/security/reactive/ReactiveSecurityAutoConfiguration.html
- Spring Security — WebFlux Security Configuration: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — API `@EnableWebFluxSecurity`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/reactive/EnableWebFluxSecurity.html
- Spring Boot 3.3 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html

**Ghi nhớ:** `@EnableWebFluxSecurity` phụ trách kích hoạt cấu hình WebFlux security của Spring Security; Spring Boot thường đăng ký hạ tầng và user mặc định nếu đủ điều kiện; `SecurityWebFilterChain` do ứng dụng định nghĩa là nơi thể hiện chính sách HTTP thực tế. Hãy kiểm thử policy **và** nguồn xác thực như hai phần riêng biệt.
