# Cấu hình người dùng mẫu bằng `MapReactiveUserDetailsService`

## 1. Mục tiêu và bối cảnh

Trong giai đoạn **khởi tạo ứng dụng Spring Security reactive**, ta thường cần một vài tài khoản mẫu để thử đăng nhập, kiểm tra phân quyền và xác nhận pipeline bảo mật của Spring WebFlux hoạt động trước khi tích hợp cơ sở dữ liệu hoặc hệ thống danh tính thực tế.

`MapReactiveUserDetailsService` là cách thiết lập đơn giản cho tình huống này. Nó lưu các bản ghi `UserDetails` trong một `Map` ở bộ nhớ ứng dụng và cung cấp API tìm người dùng theo username dưới dạng Reactor `Mono<UserDetails>`. Bạn không cần JDBC, R2DBC hay máy chủ danh tính bên ngoài để bắt đầu kiểm thử quy tắc bảo mật cơ bản.

Sau bài học, bạn sẽ có thể:

1. Phân biệt `ReactiveUserDetailsService` với `UserDetailsService` của Servlet/MVC.
2. Khai báo nhiều tài khoản mẫu bằng `User.withUsername(...)` và `MapReactiveUserDetailsService`.
3. Mã hóa mật khẩu bằng `PasswordEncoder` và cấp quyền bằng roles.
4. Kết nối kho user mẫu với `SecurityWebFilterChain`, HTTP Basic và các endpoint WebFlux.
5. Chạy, kiểm thử các kết quả 200/401/403 và chẩn đoán lỗi cấu hình thường gặp.
6. Giải thích vì sao giải pháp in-memory chỉ thích hợp cho học tập, demo và test có kiểm soát.

**Phạm vi:** cấu hình người dùng mẫu trong ứng dụng Spring Boot + Spring WebFlux + Spring Security. Việc triển khai kho người dùng production, OAuth2/OIDC, JWT hay đăng nhập liên kết là những chủ đề tiếp theo.

## 2. `MapReactiveUserDetailsService` là gì?

Các thành phần chính:

| Thành phần | Vai trò |
| --- | --- |
| `UserDetails` | Biểu diễn username, password đã mã hóa, authorities/roles và các trạng thái tài khoản cần cho authentication |
| `User.withUsername(...)` | Builder tạo `UserDetails` mẫu |
| `ReactiveUserDetailsService` | Giao diện reactive có `Mono<UserDetails> findByUsername(String username)` |
| `MapReactiveUserDetailsService` | Cài đặt `ReactiveUserDetailsService` bằng kho `Map` trong bộ nhớ |
| `PasswordEncoder` | Kiểm tra mật khẩu người dùng cung cấp với giá trị đã mã hóa trong `UserDetails` |
| `SecurityWebFilterChain` | Định nghĩa quy tắc bảo vệ HTTP request trong WebFlux |
| `ServerHttpSecurity` | DSL tạo `SecurityWebFilterChain` trong ứng dụng reactive |

Sơ đồ ý tưởng với HTTP Basic:

```text
HTTP request có Authorization: Basic ...
                 |
                 v
       Spring Security WebFilter
                 |
                 v
     Giải mã username/password
                 |
                 v
  Reactive authentication infrastructure
                 |
                 v
ReactiveUserDetailsService.findByUsername(...)
                 |
                 v
    MapReactiveUserDetailsService
      (tra trong bộ nhớ ứng dụng)
                 |
                 v
    Kiểm tra mật khẩu + trạng thái user
                 |
                 v
    Tạo Authentication nếu hợp lệ
                 |
                 v
    Kiểm tra quyền trong SecurityWebFilterChain
                 |
             200 / 401 / 403
```

Đây là **luồng khái niệm**, không phải danh sách class nội bộ cố định của mọi phiên bản Spring Security. `MapReactiveUserDetailsService` chỉ thực hiện phần tìm dữ liệu user; nó không tự tạo endpoint đăng nhập và không tự định nghĩa quyền truy cập URL. Spring Security kết hợp nó với các thành phần authentication/authorization khi cấu hình thích hợp.

### Reactive khác gì cách Servlet?

- **WebFlux/reactive:** dùng `org.springframework.security.core.userdetails.ReactiveUserDetailsService` và `MapReactiveUserDetailsService`; phương thức tra cứu trả `Mono<UserDetails>`. Web security dùng `SecurityWebFilterChain` và `ServerHttpSecurity`.
- **Servlet/Spring MVC:** thường dùng `UserDetailsService`, `InMemoryUserDetailsManager`, `SecurityFilterChain` và `HttpSecurity`. Phương thức `loadUserByUsername(...)` trả `UserDetails` trực tiếp.

Không trộn `InMemoryUserDetailsManager` và cấu hình `HttpSecurity` vào ví dụ WebFlux thuần. Nếu dự án thêm cả `spring-boot-starter-web` lẫn `spring-boot-starter-webflux`, Spring Boot thường chọn chế độ Servlet/MVC; để học reactive WebFlux đúng nghĩa, hãy chỉ sử dụng starter WebFlux.

## 3. Điều kiện đầu vào và phiên bản ví dụ

Ví dụ hoàn chỉnh dưới đây dành cho **Java 17+**, Spring Boot **3.3.5**, Spring Security 6.x được Spring Boot quản lý dependency, và Gradle tương thích với Spring Boot 3.3 (chẳng hạn Gradle 8.5). Các API chính cũng tồn tại ở các nhánh Spring Security mới hơn, nhưng muốn sao chép toàn bộ dự án và chạy nguyên trạng thì nên dùng bộ phiên bản nêu ở đây.

Cần có:
- JDK 17 trở lên.
- Gradle hoặc Gradle Wrapper tương thích (nếu đã có wrapper thì ưu tiên `./gradlew` trên Linux/macOS hoặc `gradlew.bat` trên Windows).
- Cổng 8080 còn trống, hoặc điều chỉnh `server.port` và các lệnh kiểm tra.

Cấu trúc tệp:

```text
reactive-users-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   └── java/dev/example/reactiveusers/
    │       ├── ReactiveUsersApplication.java
    │       ├── SecurityConfig.java
    │       └── DemoController.java
    └── test/
        └── java/dev/example/reactiveusers/
            └── SecurityIntegrationTest.java
```

Tệp `settings.gradle`:

```groovy
rootProject.name = 'reactive-users-demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
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
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-webflux` cung cấp WebFlux và Reactor; `spring-boot-starter-security` cung cấp Spring Security. Để thử authentication bằng HTTP Basic trong bài này, **không cần tự thêm database**. Spring Boot quản lý phiên bản dependency xuyên suốt thông qua BOM; không tự ghép các bản Spring Security không tương thích với bản Boot.

## 4. Tạo lớp khởi động ứng dụng

Tệp `src/main/java/dev/example/reactiveusers/ReactiveUsersApplication.java`:

```java
package dev.example.reactiveusers;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveUsersApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveUsersApplication.class, args);
    }
}
```

`@SpringBootApplication` kích hoạt auto-configuration và component scan của package `dev.example.reactiveusers`. Đặt các class cấu hình, controller và test cùng package hoặc dưới package này để Spring phát hiện được chúng.

## 5. Khai báo hai người dùng mẫu và bảo vệ URL

Tệp `src/main/java/dev/example/reactiveusers/SecurityConfig.java`:

```java
package dev.example.reactiveusers;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    public MapReactiveUserDetailsService userDetailsService(
            PasswordEncoder passwordEncoder) {

        UserDetails reader = User.withUsername("reader")
                .password(passwordEncoder.encode("reader-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(passwordEncoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    public SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/admin").hasRole("ADMIN")
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
```

**Giải thích lần lượt:**

1. `@Configuration` khai báo cấu hình Spring; `@EnableWebFluxSecurity` bật hỗ trợ Spring Security cho WebFlux.
2. Bean `PasswordEncoder` dùng BCrypt để băm mật khẩu. Chuỗi `reader-pass` và `admin-pass` là mật khẩu rõ **chỉ trong chương trình demo**; hai đối tượng `UserDetails` lưu *hash*, không lưu chuỗi rõ. BCrypt dùng salt nên hash có thể khác sau mỗi lần khởi động dù mật khẩu demo giữ nguyên.
3. `User.withUsername(...).password(...).roles(...)` tạo ra bản ghi `UserDetails` có thông tin đăng nhập và quyền. `roles("USER")` tạo authority `ROLE_USER`, còn `roles("USER", "ADMIN")` tạo `ROLE_USER` và `ROLE_ADMIN`.
4. `new MapReactiveUserDetailsService(reader, admin)` khởi tạo kho in-memory từ hai `UserDetails`. Constructor này nhận `UserDetails...` (varargs); còn có constructor nhận `Collection<UserDetails>` hoặc `Map<String, UserDetails>` phù hợp cho các trường hợp khác. Với constructor nhận map, map phải truy cập không blocking.
5. Bean `MapReactiveUserDetailsService` đồng thời là một bean loại `ReactiveUserDetailsService`; hạ tầng Spring Security reactive có thể dùng nó để tra username. Spring Boot cũng sẽ không tạo tài khoản mặc định tự sinh khi bạn đã cung cấp dịch vụ xác thực phù hợp.
6. `authorizeExchange` phân quyền: `/public` cho phép mọi người, `/admin` yêu cầu role ADMIN; mọi URL còn lại yêu cầu đăng nhập. Thứ tự matcher cụ thể trước `anyExchange()` rất quan trọng.
7. `httpBasic(Customizer.withDefaults())` bật HTTP Basic để kiểm thử bằng `curl -u`. `formLogin(form -> form.disable())` tắt form login cho ví dụ API, tránh chuyển hướng trang login khi đang muốn quan sát phản hồi Basic 401.
8. `build()` trả về `SecurityWebFilterChain` gắn với pipeline WebFlux. Cấu hình này không dùng `HttpSecurity` của Servlet.

**Điểm mấu chốt:** `MapReactiveUserDetailsService` định nghĩa “ai là user và có quyền gì”; `SecurityWebFilterChain` định nghĩa “URL nào yêu cầu đăng nhập hoặc role nào”. Hai phần phối hợp với nhau nhưng giải quyết hai việc khác nhau.

### Tại sao lại cần `PasswordEncoder`?

Đầu vào HTTP Basic chứa username và password do client gửi tới. Spring Security xác minh password bằng `PasswordEncoder.matches(rawPassword, encodedPassword)` theo phương thức xác thực phù hợp. Bởi vậy dữ liệu `UserDetails.password` phải có định dạng tương thích với encoder đang dùng.

Trong ví dụ này:

```text
raw password từ client: reader-pass
PasswordEncoder bean:    BCryptPasswordEncoder
stored password của user: hash BCrypt, dạng $2a$... / $2b$...
comparison:              passwordEncoder.matches(raw, storedHash)
```

Không cần tự gọi `matches` bên trong controller hoặc `SecurityWebFilterChain`. Cơ chế authentication thực hiện việc xác minh mật khẩu.

Một mẫu thay thế phổ biến khi cần hỗ trợ nhiều định dạng hash là `PasswordEncoderFactories.createDelegatingPasswordEncoder()`. Encoder này lưu hash theo dạng `{id}encodedPassword` (ví dụ `{bcrypt}$2a$...`). **Không trộn** hash BCrypt không có tiền tố từ ví dụ hiện tại với `DelegatingPasswordEncoder` mà không điều chỉnh định dạng; nếu không có mapping cho id, bạn có thể nhận lỗi kiểu “There is no PasswordEncoder mapped for the id null”. Hai mô hình đều hợp lệ khi cấu hình đồng nhất.

## 6. Tạo ba endpoint WebFlux để thử bảo mật

Tệp `src/main/java/dev/example/reactiveusers/DemoController.java`:

```java
package dev.example.reactiveusers;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping("/public")
    public Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping("/profile")
    public Mono<String> profile(Principal principal) {
        return Mono.just("profile:" + principal.getName());
    }

    @GetMapping("/admin")
    public Mono<String> admin(Principal principal) {
        return Mono.just("admin:" + principal.getName());
    }
}
```

Spring WebFlux hỗ trợ tham số `Principal` trong phương thức xử lý request. Đối với `/profile` và `/admin`, security chain yêu cầu đã xác thực nên khi handler chạy, principal phản ánh danh tính đang đăng nhập.

Giá trị trả về của handler là `Mono<String>`, đúng mô hình xử lý reactive; ví dụ không gọi `block()` hoặc `subscribe()` trong controller.

## 7. Chạy ứng dụng và tự kiểm tra bằng HTTP

Chạy từ thư mục `reactive-users-demo`:

```bash
gradle bootRun
```

Nếu dự án đã có Gradle Wrapper, dùng `./gradlew bootRun` (Linux/macOS) hoặc `gradlew.bat bootRun` (Windows). Cần build được các dependency từ repository phù hợp, và ứng dụng được khởi động thành công trên cổng 8080.

Mở một terminal khác, dùng `curl -i` để quan sát status line, header và body:

```bash
# Không cần tài khoản
curl -i http://localhost:8080/public

# Chưa đăng nhập
curl -i http://localhost:8080/profile

# Đúng user/password mẫu
curl -i -u reader:reader-pass http://localhost:8080/profile

# Sai password
curl -i -u reader:wrong-pass http://localhost:8080/profile

# USER không phải ADMIN
curl -i -u reader:reader-pass http://localhost:8080/admin

# ADMIN có quyền truy cập
curl -i -u admin:admin-pass http://localhost:8080/admin
```

Kết quả dự kiến về **HTTP status và body**:

| Request | Kết quả dự kiến | Vì sao? |
| --- | --- | --- |
| `GET /public`, không có credential | `200 OK`, body `public` | `permitAll()` |
| `GET /profile`, không có credential | `401 Unauthorized` | `authenticated()` và HTTP Basic |
| `GET /profile`, `reader:reader-pass` | `200 OK`, body `profile:reader` | Credential đúng, đã xác thực |
| `GET /profile`, `reader:wrong-pass` | `401 Unauthorized` | Xác thực không thành công |
| `GET /admin`, `reader:reader-pass` | `403 Forbidden` | Đăng nhập hợp lệ nhưng thiếu `ROLE_ADMIN` |
| `GET /admin`, `admin:admin-pass` | `200 OK`, body `admin:admin` | Có `ROLE_ADMIN` |

Không cam kết nguyên văn tất cả HTTP headers do version và cấu hình có thể thay đổi, nhưng các status/body trên phải ổn định với cấu hình demo này.

### Phân biệt `401` và `403`

- `401 Unauthorized` thường biểu thị client chưa cung cấp credential hợp lệ hoặc authentication thất bại. Với HTTP Basic, server có thể gửi header `WWW-Authenticate` để client biết cách đăng nhập.
- `403 Forbidden` trong ví dụ xuất hiện khi user **đã được xác thực** nhưng không thỏa điều kiện `hasRole("ADMIN")`.

Không đánh đồng “đăng nhập thành công” với “có mọi quyền”.

### Vì sao ví dụ chỉ kiểm tra GET?

Cấu hình vẫn có bảo vệ CSRF mặc định của Spring Security cho các phương thức phù hợp. Một `POST`/`PUT`/`DELETE` với HTTP Basic có thể trả `403` nếu thiếu CSRF token dù user/password đúng. Đây là **mối quan tâm khác** với việc tìm user bằng `MapReactiveUserDetailsService`. Không tùy tiện tắt CSRF cho ứng dụng dùng cookie/session hoặc trình duyệt; hãy quyết định dựa trên mô hình client, xác thực và nguy cơ CSRF thực tế.

## 8. Kiểm thử tích hợp tự động bằng `WebTestClient`

Tệp `src/test/java/dev/example/reactiveusers/SecurityIntegrationTest.java`:

```java
package dev.example.reactiveusers;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class SecurityIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointIsOpen() {
        client.get().uri("/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void missingCredentialsAreUnauthorized() {
        client.get().uri("/profile")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void readerCanReadProfile() {
        client.get().uri("/profile")
                .headers(headers ->
                        headers.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("profile:reader");
    }

    @Test
    void readerCannotOpenAdminEndpoint() {
        client.get().uri("/admin")
                .headers(headers ->
                        headers.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminCanOpenAdminEndpoint() {
        client.get().uri("/admin")
                .headers(headers ->
                        headers.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin:admin");
    }

    @Test
    void invalidPasswordIsUnauthorized() {
        client.get().uri("/profile")
                .headers(headers ->
                        headers.setBasicAuth("reader", "wrong-pass"))
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
```

Chạy:

```bash
gradle test
```

Dự kiến: **6 test passes**, khi ứng dụng và dependencies tương thích như cấu hình mẫu. Đây là kết quả **dự kiến theo logic cấu hình**, không phải báo cáo đã thực thi Gradle trong môi trường của bạn. `RANDOM_PORT` cho phép test khởi chạy HTTP server thật trên cổng ngẫu nhiên; `WebTestClient` gửi request và kiểm tra phản hồi thay vì chỉ kiểm thử `PasswordEncoder` riêng lẻ.

Với test authentication nội bộ, có thể kiểm tra trực tiếp `ReactiveUserDetailsService.findByUsername("reader")` bằng `StepVerifier` nếu bổ sung `reactor-test`. Tuy nhiên, các integration test trên có giá trị hơn cho mục tiêu bài học vì chúng cùng xác nhận user store, mật khẩu và authorization chain.

## 9. Hiểu các phần tử chi tiết trong cấu hình

### 9.1. `UserDetails` chứa những gì?

Một đối tượng `UserDetails` có các thông tin điển hình: `username`, `password` đã mã hóa, `authorities` và trạng thái như enabled/account non-expired/account non-locked/credentials non-expired. Builder `User.withUsername` phù hợp cho bài demo nhỏ vì tạo được đối tượng đầy đủ với ít mã.

`.roles("USER")` là cách tiện lợi để xây role; nó thêm tiền tố `ROLE_`. Nếu chủ động cấu hình `.authorities("report:read")`, đó là authority nguyên văn, **không** tự sinh role `ROLE_report:read`. Quy tắc `hasRole("ADMIN")` tìm authority `ROLE_ADMIN` (theo role prefix mặc định), còn `hasAuthority("report:read")` tìm đúng chuỗi authority đó.

Ví dụ độc lập về ý nghĩa:

```java
UserDetails sample = User.withUsername("analyst")
        .password(passwordEncoder.encode("example-pass"))
        .authorities("report:read")
        .build();
```

Đoạn trên **minh họa**, cần biến `passwordEncoder` trong scope; nó không tự bổ sung user vào `MapReactiveUserDetailsService`. Muốn dùng user này, phải chuyển nó vào constructor của service.

### 9.2. `findByUsername` có phải là truy vấn database?

Không. Với class này, nó tra cứu trong bộ nhớ và trả về `Mono<UserDetails>` để tương thích với API reactive. Phương thức có thể dùng ở những nơi Spring Security cần tra dữ liệu user, hoặc dùng trực tiếp trong một test/service có lý do rõ ràng.

```java
// Demo đoạn mã trong class đã có service:
Mono<UserDetails> userMono = userDetailsService.findByUsername("reader");
```

Câu lệnh tạo `Mono` để tiêu thụ theo phong cách Reactor. Không gọi `userMono.block()` trong request handler WebFlux. Tìm một user không tồn tại không tạo được danh tính hợp lệ để xác thực; hãy để tầng authentication xử lý thất bại theo giao ước của framework thay vì tự lấy `null` làm user.

`MapReactiveUserDetailsService` cung cấp implementation của `ReactiveUserDetailsService` và `ReactiveUserDetailsPasswordService`; tài liệu API mô tả các constructor nhận `Map`, `Collection`, hoặc danh sách `UserDetails`, cùng phương thức `findByUsername` và `updatePassword`. Đây **không phải** một hệ quản lý tài khoản có CRUD, transaction, audit hay lưu trữ bền vững.

### 9.3. Có nên tự tạo `ReactiveAuthenticationManager`?

Không cần trong bài này. Với một kho user mẫu hợp lệ, một `PasswordEncoder` phù hợp và cấu hình WebFlux Security thông thường, Spring Security có thể thiết lập việc xác thực username/password. Viết custom authentication manager chỉ hữu ích khi logic xác thực thực sự đặc biệt, và dễ làm phức tạp bài học khởi tạo.

### 9.4. Có cần gọi `subscribeOn(Schedulers.boundedElastic())`?

Không cần cho phép tra cứu in-memory đơn giản này. API `Mono` không tự bảo đảm mọi việc đều non-blocking; tuy nhiên lookup trong `Map` là thao tác bộ nhớ, không phải I/O blocking. Khi chuyển sang DAO đồng bộ thật sự, phải có chiến lược cô lập blocking hoặc ưu tiên driver reactive. Không gắn scheduler một cách máy móc vào mọi phương thức trả `Mono`.

## 10. Những lỗi phổ biến khi bắt đầu

| Dấu hiệu | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Ứng dụng khởi động nhưng chỉ có user tự sinh trong log | Bean user mẫu không được component scan, chưa đăng ký `@Bean`, hoặc không vào cấu hình mong muốn | Kiểm tra package, `@Configuration`, `@EnableWebFluxSecurity` và bean `ReactiveUserDetailsService` |
| `401` ngay cả khi gửi đúng mật khẩu demo | Hash và `PasswordEncoder` không đồng nhất; username/password khác dữ liệu bean; ứng dụng đang chạy config khác | Kiểm tra `encode(...)`, bean encoder và tên user; không log mật khẩu thật |
| `403` ở `/admin` dù đăng nhập được | User thiếu `ROLE_ADMIN` hoặc matcher quá rộng chặn trước | Kiểm tra `roles("ADMIN")` và thứ tự `pathMatchers` |
| Gửi Basic nhưng bị redirect sang form login | Form login còn bật hoặc ứng dụng không áp dụng security chain dự kiến | Kiểm tra `formLogin(form -> form.disable())`, `httpBasic(...)` và chain |
| Controller reactive nhưng mã bảo mật dùng `HttpSecurity` | Lẫn cấu hình MVC/Servlet với WebFlux | Dùng `ServerHttpSecurity`/`SecurityWebFilterChain`; kiểm tra dependencies |
| `There is no PasswordEncoder mapped for the id "null"` | Dùng `DelegatingPasswordEncoder` nhưng hash không có tiền tố `{id}` | Đồng bộ định dạng hash với encoder đang dùng |
| Dùng `password("reader-pass")` không encode | Password trong `UserDetails` không đúng định dạng mà provider chờ | `password(passwordEncoder.encode("reader-pass"))` |
| Chạy lại ứng dụng rồi thấy thay đổi user/password biến mất | Kho nằm trong RAM | Chuyển sang cơ sở dữ liệu hoặc identity provider khi có yêu cầu lưu bền |
| POST có credential đúng vẫn `403` | CSRF protection có thể đang có hiệu lực | Kiểm tra cơ chế CSRF thay vì kết luận ngay user store sai |
| Dùng `User.withDefaultPasswordEncoder()` từ snippet demo mà không hiểu cảnh báo | API tiện học nhưng không phù hợp để thiết kế lưu mật khẩu production | Định nghĩa `PasswordEncoder` rõ ràng như ví dụ |

### Ba tình huống cần tránh

**1. Không lưu password rõ trong `UserDetails`.**

```java
// Không phù hợp với BCryptPasswordEncoder:
UserDetails wrong = User.withUsername("reader")
        .password("reader-pass")
        .roles("USER")
        .build();

// Phù hợp:
UserDetails right = User.withUsername("reader")
        .password(passwordEncoder.encode("reader-pass"))
        .roles("USER")
        .build();
```

Cả hai là đoạn minh họa trong scope có `passwordEncoder`. Mặc dù đây là demo có mật khẩu rõ trong source để người học thử curl, mã thực tế lưu vào đối tượng `UserDetails` cần là **giá trị đã mã hóa**.

**2. Không dùng mã hình thức Servlet trong bài WebFlux.**

```java
// Servlet stack, KHÔNG dùng cho cấu hình reactive WebFlux:
SecurityFilterChain filterChain(HttpSecurity http) { /* ... */ }

// WebFlux stack:
SecurityWebFilterChain filterChain(ServerHttpSecurity http) { /* ... */ }
```

Hai dòng trên là **minh họa chữ ký**, không phải các phương thức hoàn chỉnh có thể biên dịch; chương trình đầy đủ đã nằm ở phần 5.

**3. Không coi user mẫu là hệ thống quản lý danh tính thực.** Password demo trong source, vai trò cố định và dữ liệu RAM đều có mục đích sư phạm. Đừng bật chúng ngoài môi trường học/demo có kiểm soát, đặc biệt trên server công khai. Với môi trường production, dùng kho credential và cơ chế vòng đời tài khoản được bảo vệ, giám sát và quản trị phù hợp.

## 11. Khi nào thay thế `MapReactiveUserDetailsService`?

Giải pháp hiện tại có ưu điểm **nhanh, ít cấu hình, không I/O bên ngoài, dễ kiểm thử**. Nó phù hợp cho:
- Bài hướng dẫn mở đầu Spring Security reactive.
- Local demo và integration test có tài khoản cố định.
- Prototype tạm thời kiểm tra matcher và phân quyền URL.

Nên chuyển sang cơ chế khác khi bạn cần:
- Tài khoản được thêm/sửa/khóa/xóa trong quá trình chạy và giữ bền sau restart.
- Đồng bộ danh tính giữa nhiều instance/container.
- Thay đổi password an toàn, reset mật khẩu, rotation, audit, rate limiting hoặc MFA.
- Tích hợp database, LDAP, hệ thống doanh nghiệp, OIDC/OAuth2 hoặc identity provider bên ngoài.

Khi nguồn danh tính chuyển sang backend reactive khác, vẫn có thể giữ hợp đồng `ReactiveUserDetailsService` (nếu xác thực username/password thích hợp) nhưng thay implementation của nó. Không biến một `Map` được chia sẻ thủ công thành database; cách đó không tự có persistence, transaction hoặc consistency giữa các node.

**Về bảo mật vận hành:** bật HTTPS khi gửi Basic credentials qua mạng; chỉ dùng password demo trong môi trường thử nghiệm. Basic chuyển thông tin xác thực được mã hóa Base64, **không phải** một dạng mã hóa mật khẩu bảo vệ khỏi nghe lén nếu thiếu TLS. Cần kiểm soát lưu log, giới hạn thử mật khẩu, secret management và chính sách mật khẩu khi chuyển sang hệ thống thật.

## 12. Câu hỏi tự kiểm tra và bài tập

**Câu 1.** `MapReactiveUserDetailsService` lưu dữ liệu ở đâu?  
**Đáp án:** trong bộ nhớ ứng dụng, thông qua cấu trúc `Map`; không tự ghi database hay tồn tại bền qua restart.

**Câu 2.** Vì sao dùng `ReactiveUserDetailsService` trong WebFlux?  
**Đáp án:** API tra cứu trả `Mono<UserDetails>` để kết hợp với pipeline reactive, thay vì `UserDetails` trả trực tiếp như giao diện Servlet.

**Câu 3.** `roles("ADMIN")` cung cấp authority gì trong cấu hình mặc định?  
**Đáp án:** `ROLE_ADMIN`. Bởi vậy `hasRole("ADMIN")` hoạt động với user này.

**Câu 4.** Reader gửi đúng mật khẩu truy cập `/admin` sẽ nhận gì?  
**Đáp án:** `403 Forbidden`: authentication thành công nhưng authorization từ chối.

**Câu 5.** Người dùng chưa đăng nhập truy cập `/profile` qua HTTP Basic nhận gì?  
**Đáp án:** `401 Unauthorized` với cấu hình form login bị tắt của ví dụ.

**Câu 6.** Có thể dùng `MapReactiveUserDetailsService` để lưu user lâu dài không?  
**Đáp án:** không nên: không có persistence, quản trị user production hay khả năng chia sẻ dữ liệu giữa nhiều instance.

**Câu 7.** Vì sao gọi `passwordEncoder.encode(...)`?  
**Đáp án:** vì Spring Security cần kiểm tra raw password với mật khẩu đã mã hóa; việc lưu chuỗi thô làm sai cấu hình và kém an toàn.

### Bài tập thực hành

1. Thêm user `auditor` với mật khẩu demo `auditor-pass` và role `AUDITOR` vào bean `userDetailsService`. Bổ sung endpoint `GET /audit` và matcher `hasRole("AUDITOR")`.
2. Xác nhận `auditor` có thể truy cập `/audit`; `reader` bị `403`; request không credential bị `401`.
3. Viết integration test `WebTestClient` cho cả ba trường hợp.
4. Thử thay `hasRole("AUDITOR")` bằng `hasAuthority("AUDITOR")` và giải thích vì sao user có `roles("AUDITOR")` không thỏa điều kiện mới.
5. Chuyển user `reader` từ `.roles("USER")` sang `.authorities("report:read")`, tạo endpoint mới yêu cầu `hasAuthority("report:read")` và kiểm thử.

Mẫu cho câu 1:

```java
UserDetails auditor = User.withUsername("auditor")
        .password(passwordEncoder.encode("auditor-pass"))
        .roles("AUDITOR")
        .build();

// Đưa vào constructor cùng reader/admin:
return new MapReactiveUserDetailsService(reader, admin, auditor);
```

Đây là **đoạn trích thay thế trong phương thức `userDetailsService`**, không phải class Java độc lập; cần thêm endpoint và matcher để hoàn thiện bài tập.

## 13. Tài liệu tham khảo chính thức

- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): cách bật và cấu hình `@EnableWebFluxSecurity`, `MapReactiveUserDetailsService` và `SecurityWebFilterChain`.
- [Spring Security API — MapReactiveUserDetailsService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/MapReactiveUserDetailsService.html): constructor và phương thức của lớp.
- [Spring Security API — ReactiveUserDetailsService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/ReactiveUserDetailsService.html): hợp đồng tra cứu user reactive.
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): `PasswordEncoder`, BCrypt và `DelegatingPasswordEncoder`.
- [Spring Boot — Gradle Plugin](https://docs.spring.io/spring-boot/docs/3.3.5/gradle-plugin/reference/htmlsingle/): cách sử dụng plugin Boot với Gradle.

**Ghi nhớ:** `MapReactiveUserDetailsService` cung cấp **user mẫu ở RAM theo API reactive**; `PasswordEncoder` xác minh mật khẩu đúng định dạng; `SecurityWebFilterChain` kiểm soát URL và role. Kết hợp đủ ba phần là bạn đã có một ứng dụng Spring Security WebFlux nhỏ có thể chạy và kiểm thử.