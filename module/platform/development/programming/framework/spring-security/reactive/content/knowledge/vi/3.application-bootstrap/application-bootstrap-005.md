# Tạo `SecurityWebFilterChain` đầu tiên với `ServerHttpSecurity`

## Mục tiêu bài học

Sau bài này, bạn có thể tạo một cấu hình bảo mật **Spring WebFlux** bằng Java, hiểu luồng `ServerHttpSecurity → SecurityWebFilterChain → WebFilter`, cho phép một endpoint công khai, yêu cầu xác thực cho endpoint cá nhân, giới hạn endpoint quản trị theo role, chạy ứng dụng và kiểm chứng kết quả bằng HTTP/test tự động.

**Phạm vi:** cấu hình **một** `SecurityWebFilterChain` đầu tiên cho WebFlux, dùng HTTP Basic và tài khoản in-memory để học. Đây chưa phải bài triển khai OAuth2, JWT, đăng nhập qua database hay nhiều security chain; các chủ đề đó chỉ được chỉ ra ở những vị trí cần nhận biết ranh giới. Các ví dụ Java sau hướng tới Spring Boot 3.x, Spring Security 6.x, Java 17 trở lên và Gradle. Với phiên bản mới hơn, kiểm tra tài liệu tương ứng nếu API có thay đổi.

## 1. Ba khái niệm cần nắm trước khi viết code

- **`ServerHttpSecurity`:** builder/DSL cấu hình bảo mật HTTP của **Spring WebFlux**. Bạn khai báo những đường dẫn có thể truy cập, cách xác thực, HTTP security headers, CSRF, login, v.v. Đây là đối tượng giúp *xây dựng* chain, không phải filter tự xử lý từng request.
- **`SecurityWebFilterChain`:** kết quả từ `http.build()`. Nó mô tả tập các `WebFilter` bảo mật và matcher áp dụng cho request. Spring Security đưa chain này vào `WebFilterChainProxy`, để request WebFlux thực tế được bảo vệ.
- **`@EnableWebFluxSecurity`:** bật cơ chế tích hợp Spring Security với WebFlux thông qua Java configuration. Khi Spring Boot auto-configuration đã bật WebFlux Security, annotation này đôi khi không cần khai báo thủ công; ở bài đầu tiên ta dùng tường minh để nhận biết vai trò.

Đường đi giản lược:

```text
HTTP client
    |
    v
Spring WebFlux (ServerWebExchange)
    |
    v
Spring Security WebFilterChainProxy
    |
    +--> SecurityWebFilterChain được chọn
    |       |
    |       +--> WebFilter xác thực người gọi
    |       +--> WebFilter kiểm tra quyền
    |       +--> các cơ chế khác (headers, CSRF, ...)
    |
    v
@RestController / RouterFunction
    |
    v
Mono / Flux -> HTTP response
```

Điểm phân biệt quan trọng: ở ứng dụng **Servlet/MVC** người ta thường dùng `HttpSecurity` và `SecurityFilterChain`. Ở **WebFlux**, dùng `ServerHttpSecurity` và `SecurityWebFilterChain`. Đừng ghép lẫn hai cặp API vì chúng tích hợp vào hai pipeline khác nhau.

## 2. Chuẩn bị project đúng WebFlux

Tạo một project qua [Spring Initializr](https://start.spring.io/) với Java 17+ (hoặc Java 21), Gradle, Spring Boot 3.x và các dependency:

- **Spring Reactive Web** (`spring-boot-starter-webflux`): cung cấp server, router/controller và Reactor.
- **Spring Security** (`spring-boot-starter-security`): cung cấp Spring Security cùng các thành phần bảo mật web.
- **Spring Boot Starter Test** (`spring-boot-starter-test`): để viết JUnit và WebTestClient test.
- **Spring Security Test** (`spring-security-test`): hỗ trợ bảo mật khi viết test.

Trong `build.gradle` do Initializr sinh, phần dependency tương ứng có thể viết:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

Đây là **mảnh cấu hình Gradle**, không phải toàn bộ `build.gradle` độc lập. Giữ plugin Spring Boot, dependency management, repositories và toolchain Java mà Initializr đã tạo. Không thêm `spring-boot-starter-web` vào demo: khi cả starter MVC và WebFlux cùng hiện diện, Spring Boot 3.x thường chọn **Servlet/MVC** làm loại server mặc định, mặc dù project có thư viện Reactor hoặc `WebClient`. Mục tiêu demo là inbound request chạy trên WebFlux.

Dùng package chung `demo.security.webflux` và bố trí:

```text
src/
  main/
    java/demo/security/webflux/
      DemoApplication.java
      SecurityConfig.java
      DemoController.java
  test/
    java/demo/security/webflux/
      SecurityFlowTests.java
```

## 3. Định nghĩa chính sách bảo mật trước khi cấu hình

Trong ví dụ này, ta có ba API chỉ hỗ trợ HTTP GET:

| HTTP endpoint | Ai được phép? | Mong muốn |
|---|---|---|
| `GET /public` | Tất cả, kể cả khách chưa đăng nhập | Trả `public` |
| `GET /profile` | Người dùng đã xác thực | Trả `hello <username>` |
| `GET /admin` | Người có role `ADMIN` | Trả `admin` |
| Mọi request khác | Không cho phép bởi chính sách demo | Từ chối ngay ở tầng security |

Hai tài khoản học tập được khai báo trong bộ nhớ:

| Username | Password *chỉ cho demo* | Role |
|---|---|---|
| `reader` | `reader-pass` | `USER` |
| `admin` | `admin-pass` | `ADMIN` |

Spring Security thường chuyển `.roles("ADMIN")` thành granted authority `ROLE_ADMIN`. Vì vậy `hasRole("ADMIN")` yêu cầu authority đó; **không** viết `hasRole("ROLE_ADMIN")` khi dùng convention mặc định. Authentication trả lời “ai đang gọi?”, authorization trả lời “người đó được làm gì?”; hai bước không được đánh đồng.

Đặt luật cụ thể **trước** luật mặc định cho mọi request. Ta dùng `anyExchange().denyAll()` để không vô tình mở endpoint khi thêm controller mới. Trong ứng dụng thực, sẽ cần xét thêm preflight CORS, health-check, static assets và các HTTP method cần hoạt động; không tự cho chúng quyền truy cập ngoài ý muốn.

## 4. Viết ứng dụng Java đầy đủ

### 4.1. Điểm khởi chạy

Tạo `src/main/java/demo/security/webflux/DemoApplication.java`:

```java
package demo.security.webflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Annotation `@SpringBootApplication` kích hoạt component scan trong package và các package con. Vì ba class nằm chung package, Spring tìm thấy `SecurityConfig` và `DemoController` khi khởi động.

### 4.2. Tạo `SecurityWebFilterChain` từ `ServerHttpSecurity`

Tạo `src/main/java/demo/security/webflux/SecurityConfig.java`:

```java
package demo.security.webflux;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    public SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/profile").authenticated()
                .pathMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    public MapReactiveUserDetailsService userDetailsService() {
        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }
}
```

Đây là class Java **độc lập trong project Spring Boot đã có dependencies như mục 2**. Ý nghĩa các dòng quyết định:

1. **`@Configuration`**: đánh dấu class khai báo bean.
2. **`@EnableWebFluxSecurity`**: bật hạ tầng bảo mật WebFlux.
3. **`@Bean SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http)`**: Spring cung cấp builder `ServerHttpSecurity`; method cấu hình chính sách và trả về bean chứa chain.
4. **`authorizeExchange(...)`**: vào DSL phân quyền HTTP trên `ServerWebExchange`. Đây là DSL của WebFlux, khác `authorizeHttpRequests(...)` của Servlet.
5. **`pathMatchers(HttpMethod.GET, "/public").permitAll()`**: cho phép đúng phương thức GET và đường dẫn `/public` đi qua kiểm tra quyền. Nó vẫn đi qua security chain, gồm các filter liên quan.
6. **`pathMatchers(... "/profile").authenticated()`**: yêu cầu một `Authentication` đã xác thực.
7. **`pathMatchers(... "/admin").hasRole("ADMIN")`**: yêu cầu `ROLE_ADMIN`.
8. **`anyExchange().denyAll()`**: request chưa khớp luật nào bị từ chối. Đây là fallback hữu hạn của chính sách.
9. **`httpBasic(Customizer.withDefaults())`**: bật xác thực HTTP Basic, để client gửi header `Authorization: Basic ...`. Tài khoản/mật khẩu thực phải truyền qua HTTPS; Base64 trong HTTP Basic **không mã hóa bí mật**.
10. **`formLogin(form -> form.disable())`**: tắt login HTML form vì bài demo dùng Basic với JSON/text API; mặc định form login không cần thiết ở đây.
11. **`build()`**: kết thúc DSL và tạo `SecurityWebFilterChain`. Không cần tự khởi tạo `WebFilterChainProxy` hay `Servlet Filter`.
12. **`MapReactiveUserDetailsService`**: nơi tra cứu tài khoản theo mô hình reactive cho bài tập. `PasswordEncoderFactories.createDelegatingPasswordEncoder()` lưu chuỗi hash có prefix nhận dạng encoder (ví dụ `{bcrypt}`); nó không lưu plain password trực tiếp trong `UserDetails`.

Lưu ý: mật khẩu demo vẫn xuất hiện ở source để có thể chạy bài thực hành, dù giá trị được hash khi dựng `UserDetails`. Không mang tài khoản/mật khẩu này vào môi trường thật. Production cần nguồn identity và quản lý credential phù hợp.

### 4.3. Tạo ba endpoint để quan sát chính sách

Tạo `src/main/java/demo/security/webflux/DemoController.java`:

```java
package demo.security.webflux;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping("/public")
    public Mono<String> publicEndpoint() {
        return Mono.just("public");
    }

    @GetMapping("/profile")
    public Mono<String> profile() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName())
            .map(name -> "hello " + name);
    }

    @GetMapping("/admin")
    public Mono<String> adminEndpoint() {
        return Mono.just("admin");
    }
}
```

Đây là **ba handler reactive**, trả `Mono` để WebFlux quản lý subscription và hoàn thành response. Trong `/profile`, `ReactiveSecurityContextHolder` truy cập `SecurityContext` từ **Reactor Context** của subscription. Không dùng `SecurityContextHolder.getContext()` vốn mặc định dựa vào `ThreadLocal` để đoán principal trong reactive pipeline. Nếu dùng hàm lấy context ở nơi không có security context, `Mono` có thể hoàn thành rỗng; ví dụ này yêu cầu authentication tại security chain trước khi vào handler.

Ba lớp `DemoApplication`, `SecurityConfig`, `DemoController`, kết hợp project Initializr và dependencies ở trên, cấu thành ứng dụng mẫu đầy đủ.

## 5. Chạy và tự kiểm chứng bằng HTTP

Từ thư mục gốc project đã được Initializr tạo:

```bash
./gradlew bootRun
```

Trong Windows PowerShell/cmd sử dụng:

```powershell
.\gradlew.bat bootRun
```

Khi ứng dụng lắng nghe mặc định trên cổng `8080`, mở một terminal khác và gửi các request dưới đây (trên Windows dùng `curl.exe` để tránh alias PowerShell):

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/profile
curl -i -u reader:reader-pass http://localhost:8080/profile
curl -i -u reader:reader-pass http://localhost:8080/admin
curl -i -u admin:admin-pass http://localhost:8080/admin
```

Kết quả HTTP **dự kiến** theo thứ tự:

| Request | HTTP status | Body khi thành công |
|---|---:|---|
| `GET /public` không credential | `200` | `public` |
| `GET /profile` không credential | `401` | Không yêu cầu body cụ thể |
| `GET /profile` với `reader` | `200` | `hello reader` |
| `GET /admin` với `reader` | `403` | Không yêu cầu body cụ thể |
| `GET /admin` với `admin` | `200` | `admin` |

Không dự đoán nguyên văn mọi dòng `curl -i`: header `WWW-Authenticate`, body lỗi và thời gian/metadata của response phụ thuộc phiên bản và cấu hình. `401 Unauthorized` có nghĩa client cần xác thực hợp lệ; `403 Forbidden` ở tình huống `reader` trên `/admin` nghĩa là **đã xác thực** nhưng thiếu quyền `ROLE_ADMIN`.

Một request GET `/does-not-exist` chưa có luật cho phép sẽ không được chuyển sang controller để trả 404 như route công khai. Nó bị luật `anyExchange().denyAll()` chặn; trạng thái cụ thể có thể khác tùy có authentication hay chưa và cơ chế xử lý lỗi. Khi xây dựng API, phải quyết định chủ động có muốn khách chưa xác thực nhìn thấy 404 hay bị chặn từ vòng security.

**Quan sát response lỗi đúng cách:** đừng kết luận `SecurityWebFilterChain` không chạy chỉ vì một request trả 401; đó thường là dấu hiệu Basic authentication đang hoạt động. Ngược lại, một response 200 của `/public` **không chứng minh** các route riêng tư được bảo vệ; cần thử đủ cả trường hợp chưa đăng nhập, đăng nhập sai quyền và đúng quyền.

## 6. Cách đọc `ServerHttpSecurity` như một chính sách

Cấu trúc cốt lõi có thể nhìn ngắn gọn như sau:

```java
@Bean
SecurityWebFilterChain chain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(spec -> spec
            .pathMatchers("/open/**").permitAll()
            .pathMatchers("/staff/**").hasRole("STAFF")
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

*Đoạn trên chỉ minh họa DSL bên trong một class `@Configuration`, không phải file chạy độc lập; không dùng đồng thời với bean `SecurityWebFilterChain` demo ở mục 4 nếu chưa thiết kế nhiều chain.* Các ý cần phân biệt:

### 6.1. Matcher và thứ tự rule

- `pathMatchers("/open/**")` xét path và phân quyền khi request đi vào chain. Pattern `/open/**` khác `/open` tùy matcher; không đoán pattern bao phủ tất cả đường dẫn biến thể mà không kiểm tra test.
- `pathMatchers(HttpMethod.GET, "/public")` trong demo giới hạn cả phương thức HTTP; POST cùng path **không tự được permit**.
- Các rule được xét theo **thứ tự khai báo**. Đặt luật cụ thể trước `anyExchange()`. Một `permitAll()` quá rộng ở đầu có thể làm các rule chặt hơn phía sau không được xét.
- `authenticated()` đòi identity đã xác thực; `permitAll()` công khai; `denyAll()` chặn; `hasRole("STAFF")` cần granted authority `ROLE_STAFF`; `hasAuthority("SCOPE_read")` kiểm tra chính xác authority đó.

### 6.2. Phạm vi của cả chain khác quyền trong chain

Ở bài một-chain này, không gọi `http.securityMatcher(...)` nên chain được áp dụng cho phạm vi request mặc định. Nếu ứng dụng có nhiều `SecurityWebFilterChain`, `securityMatcher(ServerWebExchangeMatcher)` chọn **request nào thuộc chain**, còn `authorizeExchange(...).pathMatchers(...)` áp dụng **luật quyền bên trong chain đã chọn**. Cần đặt thứ tự bean/`@Order` có chủ đích và một chiến lược cho request ngoài các matcher; không nghĩ hai chain tự gộp filter vào nhau.

Ví dụ ý tưởng (không phải code cần thêm vào bài demo):

```text
Chain A: chỉ khớp /api/** -> xác thực bearer token
Chain B: khớp request còn lại -> cấu hình cho giao diện web
        |
        v
Mỗi request chọn chain thích hợp; policy của chain A
không tự hợp nhất với policy chain B.
```

### 6.3. Có phải tạo `ServerHttpSecurity` bằng `new`?

Không. Method `@Bean` nhận builder qua tham số để framework cung cấp và quản lý cấu hình. Bạn dùng DSL và trả về bean đã `build()`. Không trả về chính `ServerHttpSecurity` thay cho `SecurityWebFilterChain`; không tạo `SecurityWebFilterChain` bằng cách nhồi trực tiếp một `Filter` của Servlet.

### 6.4. Vì sao cần tự khai báo bean khi Spring Security đã có mặc định?

Cấu hình WebFlux tối thiểu có thể tự bảo vệ các endpoint và bật các cơ chế xác thực mặc định khi chưa có custom chain. Nhưng để có policy riêng cho `/public`, `/profile` và `/admin`, bạn khai báo bean `SecurityWebFilterChain`. Khi đã cung cấp bean này, phải thể hiện rõ các luật cần thiết; đừng dựa vào giả định rằng các luật của chain tự động trước đó sẽ luôn được thêm vào bean của mình.

## 7. Phân biệt authentication, authorization và Reactor Context

Khi gửi `curl -u reader:reader-pass ...`, client tạo HTTP Basic Authorization header từ username/password. Security filter phân tích header, sử dụng cơ chế authentication và `ReactiveUserDetailsService` để tìm `UserDetails` của reader, kiểm tra password và đặt `Authentication` vào security context phù hợp với reactive request.

Với `/profile`, authorization cho qua vì người gọi đã xác thực. Controller nhận quyền truy cập vào Reactor Context để lấy tên. Với `/admin`, người đó đã xác thực nhưng chỉ có `ROLE_USER`; `hasRole("ADMIN")` không được thỏa mãn nên trả `403`.

```text
GET /admin + Basic reader
  -> xác thực: reader, authorities = [ROLE_USER]
  -> kiểm quyền: cần ROLE_ADMIN
  -> DENIED -> 403

GET /admin + Basic admin
  -> xác thực: admin, authorities = [ROLE_ADMIN]
  -> kiểm quyền: có ROLE_ADMIN
  -> ALLOWED -> controller -> "admin"
```

**Reactor Context** khác với một biến global hoặc `ThreadLocal`. Reactive publisher có thể di chuyển giữa các thread, nhưng context phải gắn với **subscription**. Do vậy bên trong ứng dụng WebFlux, muốn truy cập principal thường nên sử dụng `ReactiveSecurityContextHolder`, injection được Spring hỗ trợ hoặc đối tượng authentication/Principal đã được framework cung cấp. Không gọi `subscribe()` thủ công để tách công việc xử lý HTTP vì dễ làm đứt luồng quản lý context và lỗi. Tránh `.block()` trên event-loop.

## 8. Kiểm thử tự động security chain bằng `WebTestClient`

Thử thủ công giúp quan sát, nhưng test tự động bảo vệ policy khi sau này thêm endpoint. Dùng class dưới đây trong `src/test/java/demo/security/webflux/SecurityFlowTests.java`:

```java
package demo.security.webflux;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
@AutoConfigureWebTestClient
class SecurityFlowTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointWorksWithoutLogin() {
        client.get().uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void profileWithoutLoginReturns401() {
        client.get().uri("/profile")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void readerCanReadOwnProfile() {
        client.get().uri("/profile")
            .headers(headers -> headers.setBasicAuth("reader", "reader-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("hello reader");
    }

    @Test
    void readerCannotEnterAdminArea() {
        client.get().uri("/admin")
            .headers(headers -> headers.setBasicAuth("reader", "reader-pass"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminCanEnterAdminArea() {
        client.get().uri("/admin")
            .headers(headers -> headers.setBasicAuth("admin", "admin-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin");
    }
}
```

Chạy:

```bash
./gradlew test
```

Hoặc Windows:

```powershell
.\gradlew.bat test
```

Trong môi trường Spring Boot 3.x với dependency test ở mục 2, các kiểm thử trên khởi động ứng dụng tại cổng ngẫu nhiên, dùng WebTestClient gửi HTTP thật tới web server test và kiểm tra cả chain lẫn controller. **Kỳ vọng:** 5 test thành công. Không cam kết dòng stdout Gradle cố định vì Gradle/JUnit in tên task, thời gian và trạng thái khác nhau theo version. Khi test fail, kiểm tra log, bean security, role và web application type; không tự sửa expected HTTP status cho test xanh.

Khi chỉ cần kiểm chứng security ở cấp WebFlux test client giả lập (không mở server), có thể sử dụng `WebTestClient.bindToApplicationContext(context).apply(springSecurity())` với `spring-security-test`; các matcher và mock principal được quản lý bằng DSL test. Bài này chọn test qua cổng ngẫu nhiên để dễ xác minh HTTP thực và tránh nhầm rằng unit test controller đã đủ bảo vệ endpoint.

## 9. CSRF, session, CORS và các mặc định cần tôn trọng

### 9.1. CSRF không tự biến mất vì dùng WebFlux

Spring Security WebFlux **bật CSRF mặc định**. Các request state-changing như POST/PUT/PATCH/DELETE thường cần CSRF token theo chính sách hiện hành. Demo chỉ triển khai GET nên không gặp một form gửi dữ liệu. Nếu thêm browser form login, session/cookie, POST API, cần thiết kế token và test phù hợp. Đừng thêm `csrf(csrf -> csrf.disable())` một cách máy móc khi request dùng cookie/session tự động gửi. Một API bearer token không dùng cookie có thể có threat model khác, nhưng tắt CSRF cần dựa trên kiểm chứng thực tế của cơ chế authentication.

### 9.2. HTTP Basic không thay cho HTTPS và quản lý session

HTTP Basic đưa credential vào mỗi request qua header; chỉ chấp nhận qua HTTPS trong môi trường thật. Việc bật HTTP Basic **không tự khẳng định hệ thống stateless**. WebFlux vẫn có `WebSession` và `ServerSecurityContextRepository` cho những kịch bản cần lưu security context. Nếu thiết kế stateless REST API, hãy cấu hình rõ chiến lược token/context/session và kiểm tra nó, không suy luận từ mỗi chữ “reactive”.

### 9.3. CORS preflight khác quyền GET

Browser gửi `OPTIONS` preflight trong một số tình huống CORS. Vì demo dùng `anyExchange().denyAll()`, preflight chưa được cấp quyền hoặc xử lý riêng sẽ có thể bị chặn. Trong ứng dụng thật, CORS cần được cấu hình phù hợp với nguồn client tin cậy và xử lý trước bước yêu cầu authentication khi cần. Tránh `permitAll()` cho mọi method/URL chỉ để “CORS chạy”, vì sẽ mở rộng quyền quá mức.

### 9.4. Error status và login flow

Với HTTP Basic và form login đã tắt, request chưa đăng nhập vào route cần authentication thường nhận `401` cùng HTTP Basic challenge; người đăng nhập không đủ role nhận `403`. Nếu đổi sang `formLogin`, OAuth2 login hoặc custom authentication entry point, trải nghiệm có thể đổi thành redirect hoặc lỗi JSON. Khi test, cần gắn expected status với cấu hình thực tế.

## 10. Từ chain đầu tiên đến ứng dụng thật

Khi cần thêm tính năng, hãy mở rộng bằng từng quyết định riêng:

- **Thêm endpoint:** định nghĩa rule phù hợp trước `anyExchange()`; xác định HTTP method, role/authority và ca test 401/403/200. Đừng sửa `anyExchange()` thành `permitAll()` để “tạm cho chạy”.
- **Dùng role và permission khác nhau:** `hasRole("ADMIN")` kiểm `ROLE_ADMIN`, còn `hasAuthority("SCOPE_orders.read")` kiểm đúng chuỗi authority; cần mapping rõ từ danh tính/JWT sang granted authorities.
- **Dùng database:** thay `MapReactiveUserDetailsService` bằng nguồn tài khoản thật, quản lý hash và credential. `ReactiveUserDetailsService` phải không chặn event loop; không bọc JDBC blocking trong `Mono.just(...)` rồi coi là non-blocking.
- **Đổi sang JWT Resource Server:** thay HTTP Basic và user store demo bằng security config resource server phù hợp, khai báo issuer/JWK/audience/claims và các luật authority. Không cùng lúc để hai chain toàn cục cùng match tất cả request mà thiếu `securityMatcher`/`@Order`.
- **Bảo vệ method:** với WebFlux có `@EnableReactiveMethodSecurity` cho method trả reactive publisher và dùng Reactor Context; nó bổ sung, không thay thế hoàn toàn HTTP authorization.
- **Thêm health/static paths:** xác định những request thật sự cần public, tài nguyên nào chỉ dành nội bộ; xét cả firewall/proxy/API gateway để tránh dựa trên tên path có thể khác thực tế.

Tập trung vào việc bảo vệ **inbound request tới ứng dụng đang chạy**. Một ứng dụng Spring MVC có thể dùng `WebClient` để gọi hệ thống khác mà inbound security vẫn là Servlet. Khi chọn đúng starter/server stack, code cấu hình và test phải nhất quán với stack đó.

## 11. Lỗi thường gặp, nguyên nhân và cách kiểm tra

| Hiện tượng | Nguyên nhân cần nghĩ tới | Cách xác minh hoặc sửa |
|---|---|---|
| Import `HttpSecurity`/`SecurityFilterChain` mà API reactive không chịu cấu hình | Nhầm stack Servlet với WebFlux | Dùng `ServerHttpSecurity`, `SecurityWebFilterChain`, `@EnableWebFluxSecurity` |
| `/public` trả `401` | Chưa thêm `permitAll` hoặc matcher sai method/path | Kiểm tra path chính xác và thứ tự `authorizeExchange` |
| `/admin` trả `403` với `reader` | Role `USER`, thiếu `ROLE_ADMIN` | Kiểm tra authorities; đây là kết quả đúng của demo |
| `/admin` vẫn trả `403` với identity kỳ vọng có ADMIN | Authority thực không phải `ROLE_ADMIN`, mapper sai hoặc Basic credentials sai | In/log quyền ở vùng test an toàn; kiểm tra `roles` và `hasRole` |
| Mọi request bị redirect sang trang login | Form login hoặc entry point khác đang bật | Kiểm tra có đúng chain demo và `formLogin(form -> form.disable())` |
| POST thất bại dù GET được | Fallback `denyAll`, CSRF hoặc policy method | Xác định chính xác lỗi 403 và rule; không tắt CSRF vô điều kiện |
| Test 200 khi production 401 | Test không gắn Spring Security vào WebTestClient/mocks hoặc không test đúng server | Chạy test tích hợp với security chain và các ca 401/403 |
| Startup có thông báo hai security chain/matcher | Thêm nhiều bean hoặc framework config không như giả định | Rà lại bean `SecurityWebFilterChain` và ưu tiên chọn chain |
| Thấy `Mono` nhưng request vẫn treo | Code service gọi blocking hoặc `.block()` | Kiểm tra thread sử dụng, chọn adapter non-blocking hoặc cô lập blocking |
| Dữ liệu đăng nhập lộ trên HTTP | Dùng Basic trên kết nối không mã hóa | Dùng TLS/HTTPS và giải pháp credential production |

**Sai lầm tư duy hay gặp:** “Đã có `@Bean SecurityWebFilterChain` thì tất cả endpoint đã có quyền đúng.” Bean chỉ chứa các quy tắc bạn định nghĩa; lỗi đặt matcher/role/chain vẫn có thể làm lộ hoặc chặn nhầm API. Vì vậy phải test cả ba trạng thái: khách chưa xác thực, người dùng thiếu quyền, người dùng đủ quyền.

## 12. Bài tập tự thực hành

**Bài 1.** Thêm endpoint `GET /reports` chỉ dành cho `USER` và `ADMIN`. Trước khi code, quyết định dùng role nào và thêm test cho cả hai tài khoản. Nếu muốn hai role được phép, có thể dùng `hasAnyRole("USER", "ADMIN")`; đặt rule trước `anyExchange().denyAll()`.

**Bài 2.** Thay rule `/profile` bằng `hasRole("USER")` và thử gọi bằng `admin` của demo (chỉ có `ROLE_ADMIN`). Vì sao lại có `403`? Đó là vì `authenticated()` kiểm chứng danh tính, còn `hasRole("USER")` kiểm chính xác quyền; role ADMIN không tự bao gồm USER. Nếu muốn kế thừa quyền, phải thiết kế role hierarchy hoặc cấp authority phù hợp.

**Bài 3.** Gửi POST vào `/public` (chỉ có GET). Việc `GET /public` công khai **không làm POST được permit**. Xác định request bị chặn do matcher/fallback và/hoặc CSRF tùy cấu hình; không dự đoán route xử lý POST nếu chưa khai báo handler.

**Bài 4.** Vì sao `SecurityContextHolder.getContext()` không phải lựa chọn mặc định để lấy principal bên trong `Mono` ở WebFlux?

**Đáp án:** Reactive Security giữ context trong Reactor subscription, có thể tiếp tục trên thread khác. `SecurityContextHolder` mặc định dựa vào `ThreadLocal`, nên không phải cách đáng tin cậy để truy cập context của reactive request; dùng `ReactiveSecurityContextHolder` hoặc API injection phù hợp.

**Bài 5.** Điều gì thay đổi nếu gọi `.anyExchange().permitAll()` ở cuối?

**Đáp án:** Các endpoint ngoài ba rule cụ thể sẽ được phép truy cập; đây là thay đổi chính sách lớn và có thể vô tình mở API được thêm trong tương lai. Bài demo dùng `denyAll()` để yêu cầu khai báo rõ ràng.

## Tài liệu chính thức

- [Spring Security — WebFlux Security: minimal và explicit configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Spring Security — CSRF protection for WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Security — WebTestClient security setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html)
- [Spring Boot — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html)
