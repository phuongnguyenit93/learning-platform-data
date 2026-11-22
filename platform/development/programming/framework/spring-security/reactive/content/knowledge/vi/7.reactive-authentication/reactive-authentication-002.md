# ReactiveAuthenticationManager và hợp đồng `Mono<Authentication>`

## 1. Mục tiêu của bài học

Trong Spring Security chạy trên **Spring WebFlux**, xử lý xác thực phải phối hợp với chuỗi Reactor thay vì giả định mọi thao tác luôn đồng bộ. `ReactiveAuthenticationManager` là giao diện chịu trách nhiệm **thử xác thực** một đối tượng `Authentication` và trả kết quả theo hợp đồng `Mono<Authentication>`.

Nắm được hợp đồng này giúp bạn hiểu vì sao một request đăng nhập có thể **thành công**, **bị từ chối** hoặc **không được manager hiện tại xử lý**; đồng thời tránh những lỗi nguy hiểm như coi mật khẩu sai là `Mono.empty()`, tự đánh dấu token đã xác thực hoặc gọi `block()` trên event loop.

Sau bài học, bạn cần:
1. Đọc đúng chữ ký `authenticate(Authentication)` và phân biệt ba loại tín hiệu của `Mono`.
2. Biết `Authentication` đầu vào khác với đối tượng đã xác thực đầu ra ở đâu.
3. Hiểu mối quan hệ giữa `ReactiveAuthenticationManager`, `ReactiveUserDetailsService`, `AuthenticationWebFilter`, `SecurityWebFilterChain` và Reactor `Context`.
4. Cấu hình một manager có sẵn để xác thực username/password trong Spring Security reactive.
5. Tự kiểm thử success/error/empty bằng `StepVerifier` và kiểm chứng HTTP Basic bằng `WebTestClient`.
6. Biết khi nào cần manager tùy chỉnh, cách kết hợp nhiều manager và nguyên tắc tránh blocking hoặc rò rỉ thông tin xác thực.

> Phạm vi: hợp đồng `ReactiveAuthenticationManager` trong Spring Security **reactive**, với ví dụ Java 17+, Spring WebFlux và HTTP Basic. Mã hóa mật khẩu, JWT/OAuth2 và quản trị danh tính được nhắc đến ở mức hỗ trợ hiểu giao diện; bài không xây dựng hệ thống authentication production.

## 2. Hợp đồng cốt lõi

Giao diện thuộc package `org.springframework.security.authentication`:

```java
@FunctionalInterface
public interface ReactiveAuthenticationManager {
    Mono<Authentication> authenticate(Authentication authentication);
}
```

Đây là **chữ ký khái niệm rút gọn từ API**, không phải file cần tạo lại trong dự án. Các kiểu liên quan:
- `Authentication` (`org.springframework.security.core.Authentication`) mô tả danh tính, credentials, authorities, trạng thái authentication và một số chi tiết bổ sung.
- `Mono<Authentication>` (`reactor.core.publisher.Mono`) là publisher phát tối đa **một** đối tượng `Authentication`, hoặc hoàn tất rỗng, hoặc phát lỗi.
- `ReactiveAuthenticationManager` là **functional interface** nên có thể được implement bằng class hoặc lambda, nhưng một implementation phải tuân thủ ý nghĩa ba tín hiệu.

### Ba kết quả phải phân biệt

| Tín hiệu từ `authenticate(...)` | Ý nghĩa trong hợp đồng | Ví dụ đúng |
| --- | --- | --- |
| `onNext(authenticated)` rồi `onComplete()` | Xác thực **thành công** | User/password hợp lệ; kết quả chứa principal và authorities đã xác minh |
| `onComplete()` **không có `onNext`** | Manager **không thể quyết định / không hỗ trợ** request này | Manager chỉ biết API key nhận một token username/password |
| `onError(authenticationException)` | Manager đã xử lý request nhưng **xác thực thất bại** | Sai mật khẩu, tài khoản bị khóa, token không hợp lệ |

Chìa khóa để đọc hợp đồng: **`Mono.empty()` không tương đương với mật khẩu sai.** Sai credentials là thất bại xác thực và cần được biểu đạt bằng error thích hợp; empty dành cho manager không thể xác định kết quả. Không dùng `null` làm thành phần phát ra của `Mono` vì Reactor không cho phép `onNext(null)`.

Ba nhánh trong pseudocode:

```java
ReactiveAuthenticationManager manager = request -> {
    if (!supportsThisTokenType(request)) {
        return Mono.empty(); // Không thể xác thực loại token này
    }
    if (!credentialsAreValid(request)) {
        return Mono.error(
                new BadCredentialsException("Invalid credentials"));
    }
    Authentication verified = createAuthenticatedResult(request);
    return Mono.just(verified);
};
```

Đây là **mã minh họa cấu trúc**, không biên dịch độc lập vì ba hàm `supportsThisTokenType`, `credentialsAreValid` và `createAuthenticatedResult` chỉ đại diện cho nghiệp vụ. Bên dưới có dự án chạy được với manager có sẵn và các test thật cho ba tín hiệu.

### `Mono` mang tính lazy

`authenticate(...)` trả về một publisher; quá trình truy cập dữ liệu và kiểm tra credentials trong một implementation reactive đúng nghĩa thường diễn ra khi publisher được subscribe. Không dựa vào thời điểm gọi phương thức để suy đoán mọi bước đã thực thi: thao tác đồng bộ nằm ngoài `Mono.defer(...)` hoặc `Mono.fromCallable(...)` vẫn có thể chạy sớm.

Điều quan trọng là **không tự subscribe hoặc block** trong bộ xử lý HTTP WebFlux. Framework và chuỗi bảo mật sẽ subscribe đúng vị trí và phối hợp tín hiệu.

## 3. `Authentication` đầu vào và đầu ra

Cùng là interface `Authentication` nhưng trước và sau xác thực có ý nghĩa khác nhau.

### Đầu vào chưa xác thực

Khi HTTP Basic nhận username/password, bộ chuyển đổi HTTP thường tạo một `Authentication` biểu diễn **yêu cầu xác thực**. Ví dụ:

```java
Authentication request =
        UsernamePasswordAuthenticationToken.unauthenticated(
                "reader", "reader-pass");
```

Với Spring Security 6.x, factory `unauthenticated(...)` tạo token chưa có quyền được cấp và `isAuthenticated()` là `false`. Lúc này username là thông tin client khai báo; mật khẩu **chưa được xác minh**. Không tin tưởng authorities do client tự gửi.

### Kết quả đã xác thực

Sau khi manager kiểm tra credentials, kết quả thành công thường chứa:
- Principal được xác thực (`UserDetails` hoặc principal khác).
- `GrantedAuthority`/roles được lấy từ nguồn tin cậy.
- `isAuthenticated() == true`.
- Credentials có thể đã được xóa/không còn cần giữ dưới dạng raw string.

Ví dụ minh họa factory trên một nguồn đã xác minh danh tính:

```java
Authentication verified =
        UsernamePasswordAuthenticationToken.authenticated(
                userDetails,
                null,
                userDetails.getAuthorities());
```

Đây là **đoạn trích**, biến `userDetails` phải là đối tượng `UserDetails` đã được truy xuất và kiểm tra đúng. Không gọi factory `authenticated(...)` chỉ vì đã đọc được một username từ request; làm vậy sẽ vượt qua bước xác minh credentials.

| Thuộc tính | Authentication request | Authentication result |
| --- | --- | --- |
| `getPrincipal()` | Thường là username do client gửi | Danh tính đã xác minh, có thể là `UserDetails` |
| `getCredentials()` | Password/token do client cung cấp | Nên được hạn chế lưu giữ, có thể bị xóa |
| `getAuthorities()` | Không được tin tưởng nếu đến từ client | Quyền từ nguồn tin cậy |
| `isAuthenticated()` | `false` trong token login ban đầu | `true` khi đã xác thực |
| Mục đích | Yêu cầu manager kiểm tra | Cung cấp danh tính để thực hiện authorization |

Cần tránh kết luận rằng mọi authentication mechanism đều là username/password: token bearer, certificate, OAuth2 và những cơ chế khác có kiểu `Authentication`/manager riêng.

## 4. Manager đứng ở đâu trong Spring Security reactive?

Sơ đồ ý tưởng cho **HTTP Basic trong WebFlux**:

```text
HTTP request
   |
   v
SecurityWebFilterChain (chọn chain bảo mật)
   |
   v
AuthenticationWebFilter (cho cơ chế authentication thích hợp)
   |
   +--> ServerAuthenticationConverter
   |         |
   |         +--> Mono<Authentication> request
   |
   +--> ReactiveAuthenticationManager.authenticate(request)
               |
               +--> onNext(verified Authentication): thành công
               |           |
               |           v
               |    SecurityContext / Reactor Context
               |           |
               |           v
               |    Authorization -> Controller
               |
               +--> onError(AuthenticationException): thất bại
               |           |
               |           v
               |    Authentication failure handler (HTTP Basic thường 401)
               |
               +--> empty: manager không có quyết định
                           (hành vi tiếp theo tùy filter/tổ hợp manager)
```

Sơ đồ diễn giải quan hệ thành phần, không cam kết thứ tự chính xác của mọi WebFilter nội bộ. `AuthenticationWebFilter` có trách nhiệm xác định khi nào thử authentication, biến request thành đối tượng `Authentication`, gọi manager và chuyển kết quả thành xử lý thành công/thất bại. `SecurityWebFilterChain` kết hợp các WebFilter; `ServerHttpSecurity` là DSL để cấu hình chain.

**`ReactiveAuthenticationManager` không phải authorization manager.** Nó trả lời “người dùng/tokens này có xác thực được không?”. `authorizeExchange(...)`/`hasRole(...)` trả lời “danh tính đã xác thực có được truy cập tài nguyên này không?”.

### Hợp đồng giữa những interface dễ nhầm

| Interface | Hàm chính | Trách nhiệm |
| --- | --- | --- |
| `ReactiveAuthenticationManager` | `authenticate(Authentication) -> Mono<Authentication>` | Xác minh thông tin xác thực và tạo kết quả đã xác thực |
| `ReactiveUserDetailsService` | `findByUsername(String) -> Mono<UserDetails>` | Tra thông tin user phục vụ xác thực username/password |
| `ServerAuthenticationConverter` | `convert(ServerWebExchange) -> Mono<Authentication>` | Biến HTTP request thành authentication request |
| `AuthenticationWebFilter` | WebFilter | Kết nối request, converter, manager và success/failure handlers |
| `SecurityWebFilterChain` | `matches(exchange)`, `getWebFilters()` | Quy định tập WebFilter áp dụng cho request |
| `ReactiveAuthorizationManager<T>` | `check(Mono<Authentication>, T)` trong API 6.x | Ra quyết định quyền truy cập trên danh tính đã xác thực |

Đừng đồng nhất `ReactiveUserDetailsService.findByUsername(...)` với `ReactiveAuthenticationManager.authenticate(...)`. Lấy ra được `UserDetails` **không có nghĩa** raw password của client đã đúng: còn phải kiểm tra password, account state và tạo authentication result đáng tin cậy.

### Reactor `Context`, không phải ThreadLocal kiểu Servlet

Trong WebFlux, Spring Security đặt thông tin `SecurityContext` vào **Reactor Context** để các đoạn downstream có thể truy cập theo cách reactive. Sau khi đổi thread qua scheduler, `ThreadLocal` thông thường không đủ để truyền security context. Nếu mã ứng dụng cần đọc thông tin bảo mật, hãy dùng API reactive như `ReactiveSecurityContextHolder.getContext()` trong pipeline; không dùng `SecurityContextHolder.getContext()` kiểu Servlet làm nguồn sự thật trong WebFlux.

## 5. Các implementation có sẵn

Không cần tự viết manager từ đầu cho mọi bài toán.

| Implementation / lựa chọn | Phạm vi phù hợp |
| --- | --- |
| `UserDetailsRepositoryReactiveAuthenticationManager` | Username/password với `ReactiveUserDetailsService` và `PasswordEncoder` |
| `DelegatingReactiveAuthenticationManager` | Kết hợp nhiều manager; cho manager kế tiếp khi nhánh trước trả empty |
| `JwtReactiveAuthenticationManager` | Xác thực JWT trong cấu hình resource server thích hợp |
| `OpaqueTokenReactiveAuthenticationManager` | Xác thực bearer token opaque qua introspection theo cấu hình thích hợp |
| `ReactiveAuthenticationManagerAdapter` | Cầu nối một `AuthenticationManager` đồng bộ, cần cân nhắc scheduler/khối lượng blocking |
| Manager tự viết | Cơ chế credentials riêng chưa được framework hỗ trợ; cần tuân thủ đầy đủ hợp đồng và chính sách bảo mật |

Trong bài thực hành, `UserDetailsRepositoryReactiveAuthenticationManager` là lựa chọn chính: nó sử dụng `ReactiveUserDetailsService` để tìm user và dùng `PasswordEncoder` để kiểm tra mật khẩu. Phần tùy chỉnh chỉ minh họa cách phân loại token không thuộc trách nhiệm của manager.

## 6. Dự án hoàn chỉnh: Spring Boot + Spring WebFlux + HTTP Basic

Ví dụ dưới đây hướng đến **Java 17+**, **Spring Boot 3.3.5** với Spring Security 6.x do Spring Boot quản lý và Gradle tương thích. Đây là ứng dụng **chạy được** theo cấu trúc tệp đầy đủ; các đoạn ở phần lý thuyết bên trên chỉ là minh họa.

### Cấu trúc tệp

```text
reactive-auth-manager-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/dev/example/authmanager/
    │   ├── ReactiveAuthManagerApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/dev/example/authmanager/
        └── AuthenticationManagerTests.java
```

`settings.gradle`:

```groovy
rootProject.name = 'reactive-auth-manager-demo'
```

`build.gradle`:

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
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Chỉ dùng `spring-boot-starter-webflux` cho web stack ở ví dụ này. Nếu đồng thời thêm `spring-boot-starter-web`, Spring Boot thường ưu tiên cấu hình Servlet, làm bài học WebFlux khó kiểm chứng chính xác.

### 6.1. Class khởi động

Tệp `src/main/java/dev/example/authmanager/ReactiveAuthManagerApplication.java`:

```java
package dev.example.authmanager;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveAuthManagerApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveAuthManagerApplication.class, args);
    }
}
```

### 6.2. Khai báo user store, encoder và authentication manager

Tệp `src/main/java/dev/example/authmanager/SecurityConfig.java`:

```java
package dev.example.authmanager;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("reader-pass"))
                .roles("READER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("READER", "ADMIN")
                .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            ReactiveUserDetailsService users,
            PasswordEncoder encoder) {
        UserDetailsRepositoryReactiveAuthenticationManager manager =
                new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager authenticationManager) {
        return http
                .authenticationManager(authenticationManager)
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/admin").hasRole("ADMIN")
                        .anyExchange().authenticated()
                )
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
```

**Giải thích theo đúng trách nhiệm:**

1. `MapReactiveUserDetailsService` lưu hai user mẫu trong RAM và triển khai `ReactiveUserDetailsService`. Bản ghi chứa username, hash BCrypt và roles.
2. `UserDetailsRepositoryReactiveAuthenticationManager` được cấp `ReactiveUserDetailsService` và `PasswordEncoder`. Nó chịu trách nhiệm kết hợp tra cứu user, xác minh credentials và kiểm tra trạng thái tài khoản theo implementation framework.
3. Bean trả về đúng interface `ReactiveAuthenticationManager`; điều này cho thấy code gọi chỉ cần hợp đồng, không phụ thuộc vào implementation cụ thể.
4. `ServerHttpSecurity.authenticationManager(...)` đặt manager mặc định cho security configuration. `httpBasic(...)` bật khả năng thử xác thực username/password lấy từ HTTP Basic.
5. `/public` không yêu cầu đăng nhập; `/admin` yêu cầu `ROLE_ADMIN`; URL còn lại yêu cầu đã xác thực. `formLogin(form -> form.disable())` tắt trang login form vì demo dùng HTTP Basic.
6. Mật khẩu `reader-pass` và `admin-pass` **chỉ dùng cho môi trường học/demo**. `encode(...)` trả hash BCrypt; password từ request phải được so bằng encoder phù hợp. Không ghi password hoặc hash ra log.

Với `.roles("ADMIN")`, Spring Security thêm prefix `ROLE_`; `hasRole("ADMIN")` kiểm tra authority `ROLE_ADMIN`. Trong bean `users`, admin có cả `ROLE_READER` và `ROLE_ADMIN`.

**Vì sao không tự viết kiểm tra `password.equals(storedPassword)`?** Vì stored password là hash; kiểm tra phải dùng `PasswordEncoder.matches(raw, encoded)`. Việc tự viết manager username/password rất dễ bỏ sót kiểm tra account locked/disabled/expired, thời gian xử lý hoặc xóa raw credentials. Ưu tiên implementation chính thức khi phù hợp.

### 6.3. Controller WebFlux

Tệp `src/main/java/dev/example/authmanager/DemoController.java`:

```java
package dev.example.authmanager;

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

    @GetMapping("/me")
    public Mono<String> me(Principal principal) {
        return Mono.just("user=" + principal.getName());
    }

    @GetMapping("/admin")
    public Mono<String> admin() {
        return Mono.just("admin-area");
    }
}
```

Tất cả handler trả `Mono<String>`, không `block()` và không `subscribe()`. Với request đã xác thực, `Principal` được Spring WebFlux giải quyết từ context phù hợp.

## 7. Chạy và quan sát HTTP Basic

Chạy từ thư mục `reactive-auth-manager-demo`, với Gradle tương thích và JDK 17+:

```bash
gradle bootRun
```

Nếu có Gradle Wrapper, dùng `./gradlew bootRun` trên Linux/macOS hoặc `gradlew.bat bootRun` trên Windows. Khi ứng dụng chạy ở `localhost:8080`, dùng terminal khác:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u reader:reader-pass http://localhost:8080/me
curl -i -u reader:wrong-pass http://localhost:8080/me
curl -i -u reader:reader-pass http://localhost:8080/admin
curl -i -u admin:admin-pass http://localhost:8080/admin
```

Dự kiến:

| Request | HTTP status / body đáng chú ý | Nguyên nhân |
| --- | --- | --- |
| `GET /public`, không có credential | `200 OK`, `public` | Rule `permitAll` |
| `GET /me`, không có credential | `401 Unauthorized` | Basic challenge, chưa xác thực |
| `GET /me`, reader đúng password | `200 OK`, `user=reader` | Manager phát authentication hợp lệ |
| `GET /me`, reader sai password | `401 Unauthorized` | Manager phát lỗi xác thực; filter trả challenge |
| `GET /admin`, reader đúng password | `403 Forbidden` | Đã xác thực nhưng thiếu `ROLE_ADMIN` |
| `GET /admin`, admin đúng password | `200 OK`, `admin-area` | Xác thực và phân quyền đều thành công |

Status/body trên là **kết quả dự kiến theo cấu hình mẫu**. Header và chi tiết response có thể khác theo phiên bản/cấu hình. Các lệnh đều dùng HTTP GET; đối với POST/PUT/DELETE, CSRF có thể ảnh hưởng status riêng biệt.

> HTTP Basic chỉ Base64-encode username/password trong header; **không mã hóa bảo mật** thông tin đăng nhập trên đường truyền. Chỉ dùng HTTP localhost cho demo và bắt buộc HTTPS/TLS cho luồng thực tế qua mạng.

## 8. Test hợp đồng `Mono<Authentication>` bằng `StepVerifier`

Đây là phần trọng tâm nhất: kiểm thử **signal** thay vì chỉ nhìn status HTTP. `reactor-test` cung cấp `StepVerifier`, cho phép xác nhận `onNext`, `onComplete`, `onError` mà không cần gọi `block()`.

Tệp `src/test/java/dev/example/authmanager/AuthenticationManagerTests.java`:

```java
package dev.example.authmanager;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class AuthenticationManagerTests {

    @Autowired
    ReactiveAuthenticationManager authenticationManager;

    @Autowired
    WebTestClient client;

    @Test
    void validCredentialsEmitAuthenticatedAuthenticationThenComplete() {
        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "reader", "reader-pass");

        assertFalse(request.isAuthenticated());

        StepVerifier.create(authenticationManager.authenticate(request))
                .assertNext(result -> {
                    assertTrue(result.isAuthenticated());
                    assertEquals("reader", result.getName());
                    assertTrue(result.getAuthorities().stream()
                            .anyMatch(a -> a.getAuthority()
                                    .equals("ROLE_READER")));
                })
                .verifyComplete();
    }

    @Test
    void badCredentialsProduceOnErrorNotEmpty() {
        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "reader", "wrong-pass");

        StepVerifier.create(authenticationManager.authenticate(request))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void unsupportedTokenCanProduceEmpty() {
        ReactiveAuthenticationManager usernamePasswordOnly = candidate -> {
            if (!(candidate instanceof UsernamePasswordAuthenticationToken)) {
                return Mono.empty();
            }
            return authenticationManager.authenticate(candidate);
        };

        Authentication unsupported =
                new TestingAuthenticationToken("robot", "opaque");

        StepVerifier.create(usernamePasswordOnly.authenticate(unsupported))
                .verifyComplete();
    }

    @Test
    void publicRequestNeedsNoCredentials() {
        client.get().uri("/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void missingCredentialsReturn401() {
        client.get().uri("/me")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void correctCredentialsReturnIdentity() {
        client.get().uri("/me")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("user=reader");
    }

    @Test
    void invalidCredentialsReturn401() {
        client.get().uri("/me")
                .headers(h -> h.setBasicAuth("reader", "wrong-pass"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedReaderLacksAdminRole() {
        client.get().uri("/admin")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminCanAccessAdminEndpoint() {
        client.get().uri("/admin")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin-area");
    }
}
```

Chạy test:

```bash
gradle test
```

**Kết quả kỳ vọng:** **9 test thành công** khi chạy bộ mã và dependency như trên. Đây là kết quả được suy ra từ cấu hình và hợp đồng API, **không phải tuyên bố test đã được chạy trong repository của bạn**. Gradle có thể in nhiều dòng logs, nên không giả định nguyên văn stdout.

### Điều gì được kiểm tra?

- Test 1: `Mono` phát đúng **một `Authentication` đã được xác thực**, có authority nguồn tin cậy, sau đó complete.
- Test 2: Mật khẩu sai phát `onError(BadCredentialsException)`; **không** biến thành empty.
- Test 3: **Một wrapper minh họa** chỉ xử lý username/password trả `Mono.empty()` khi gặp token loại khác. Nó minh họa “không hỗ trợ”, **không** giả định manager username/password sẵn có cũng trả empty cho mọi token lạ.
- Sáu test HTTP: xác thực và phân quyền được nối đúng với WebFlux HTTP Basic và controller.

Test empty dùng `TestingAuthenticationToken` **chỉ dành cho unit test**. Không đưa token này vào một flow đăng nhập production.

## 9. Khi nào `Mono.empty()` hữu ích?

Giả sử hệ thống có hai cơ chế authentication khác nhau:
1. Manager A biết kiểm tra token API key nội bộ.
2. Manager B biết kiểm tra username/password.

Nếu A nhận một token mà nó không hỗ trợ, A có thể trả `Mono.empty()` để nhường quyền quyết định cho thành phần khác. Khi A nhận đúng loại API key nhưng key **sai**, A phải trả `Mono.error(...)`; không được coi key sai là “không biết” để né chính sách thất bại.

Bảng quyết định:

| Tình huống ở một manager | Đúng | Không nên |
| --- | --- | --- |
| Token type nằm ngoài phạm vi được hỗ trợ | `Mono.empty()` | Báo “sai mật khẩu” khi chưa thử |
| Token type hỗ trợ, credentials đúng | `Mono.just(verifiedAuth)` | Tự đặt `isAuthenticated` khi chưa kiểm tra |
| Token type hỗ trợ, credentials sai | `Mono.error(BadCredentialsException)` | `Mono.empty()` |
| Lỗi hạ tầng, ví dụ DB/identity provider không phản hồi | Tín hiệu error phù hợp và handler có chính sách | `onErrorResume(ex -> Mono.empty())` cho mọi lỗi |
| Không tìm thấy user trong store username/password | Authentication failure theo chính sách | Trả thành công với principal mặc định |

### Kết hợp nhiều manager

`DelegatingReactiveAuthenticationManager` cho phép thử nhiều delegate:

```java
ReactiveAuthenticationManager combined =
        new DelegatingReactiveAuthenticationManager(
                apiKeyManager, usernamePasswordManager);
```

Đây là **đoạn minh họa**: hai biến `apiKeyManager` và `usernamePasswordManager` phải được định nghĩa theo cơ chế tương ứng; import `org.springframework.security.authentication.DelegatingReactiveAuthenticationManager`. Mặc định, khi delegate trước trả **empty**, việc đánh giá có thể tiếp tục với delegate kế tiếp. Khi delegate phát **error**, mặc định lỗi được chuyển tiếp thay vì âm thầm nuốt lỗi. Có tùy chọn `setContinueOnError(boolean)` cho các trường hợp đặc biệt nhưng không bật chỉ để “đăng nhập cho qua”.

Quan trọng: kết quả cuối của chuỗi manager phụ thuộc implementation của delegation, loại token, thứ tự delegate và chính sách khi không ai xác thực được. **Không giả định** empty cuối cùng tự biến thành `401` ở mọi thành phần; cần kiểm thử integration filter thật.

## 10. Custom manager: hình dạng hợp đồng và các ràng buộc

Nếu có cách xác thực đặc biệt, bạn có thể implement interface:

```java
// Đoạn minh họa: ví dụ ở ngoài chương trình chạy của phần 6.
final class DemoApiKeyAuthenticationManager
        implements ReactiveAuthenticationManager {

    private final ApiKeyVerifier verifier;

    DemoApiKeyAuthenticationManager(ApiKeyVerifier verifier) {
        this.verifier = verifier;
    }

    @Override
    public Mono<Authentication> authenticate(Authentication request) {
        if (!(request instanceof ApiKeyAuthenticationToken keyRequest)) {
            return Mono.empty();
        }

        return verifier.verify(keyRequest.getCredentials())
                .switchIfEmpty(Mono.error(
                        new BadCredentialsException("Invalid API key")))
                .map(verifiedIdentity ->
                        ApiKeyAuthenticationToken.authenticated(
                                verifiedIdentity));
    }
}
```

**Đây là pseudocode Java có kiểu minh họa, không biên dịch độc lập**: `ApiKeyVerifier`, `ApiKeyAuthenticationToken`, kiểu `verifiedIdentity` và các phương thức được viết để mô tả giao diện cần triển khai. Không sao chép thành file chạy mà chưa định nghĩa chúng. Cách làm đúng phải đảm bảo:
- Phân biệt **không hỗ trợ token type** và **credentials sai**.
- Verify thực sự, kiểm tra trạng thái tài khoản và áp dụng chính sách khóa/thu hồi token.
- Lấy authorities từ nguồn tin cậy; không copy thẳng từ request hay header client.
- Không để lộ API key, mật khẩu, access token trong exception, logs, `toString()` hoặc tracing.
- Không phát `null`; không trả `Mono.just(null)`.
- Không cấp `isAuthenticated=true` chỉ dựa trên dữ liệu tự khai báo.
- Kiểm tra tính thread-safe, timeout, cancellation, giới hạn tải và các cuộc gọi lặp.
- Chỉ chuyển kết quả đã xác minh sang `Authentication` và SecurityContext.

Nếu bạn muốn nhận `X-API-Key` từ request HTTP, **chỉ custom manager chưa đủ**. Bạn còn cần `ServerAuthenticationConverter` lấy header để tạo request token và `AuthenticationWebFilter` cấu hình converter/manager/điều kiện áp dụng, hoặc cấu hình xác thực phù hợp do Spring hỗ trợ. Không lấy `ServerWebExchange` làm input trực tiếp cho `ReactiveAuthenticationManager.authenticate(...)`; tham số của manager là `Authentication`.

## 11. Reactor: lỗi, scheduler, retry và an toàn

### 11.1. Khi nào dùng `Mono.defer` hoặc `fromCallable`?

Một manager có thể dựa vào repository reactive thực sự; khi đó method truy vấn có thể trả `Mono` từ driver mà không cần bọc lại. Nếu phải gọi SDK blocking, cần trì hoãn call và chuyển nó sang scheduler dành cho blocking:

```java
// Đoạn minh họa: legacyAuthClient là API blocking đã có.
Mono<LegacyResult> result = Mono
        .fromCallable(() -> legacyAuthClient.verify(rawCredential))
        .subscribeOn(Schedulers.boundedElastic());
```

Import `reactor.core.scheduler.Schedulers`. `LegacyResult` và `legacyAuthClient` là ký hiệu minh họa. `fromCallable` trì hoãn lời gọi đến subscription; `subscribeOn(boundedElastic())` cách ly blocking I/O khỏi event loop. **Lazy không tự động là non-blocking**. Nếu SDK thực sự non-blocking, ưu tiên dùng API Reactor của nó, thay vì offload mọi thứ sang scheduler.

Việc dùng `PasswordEncoder` có thể tiêu tốn CPU; implementation Spring Security có chiến lược scheduling phù hợp cho password verification. Đừng tự gọi `passwordEncoder.matches(...)` trên event loop trong custom manager mà không xét chi phí tính toán.

### 11.2. Error cần được biểu diễn rõ

```java
Mono<Authentication> rejected =
        Mono.error(new BadCredentialsException("Invalid credentials"));
```

Dùng `AuthenticationException` phù hợp giúp authentication filter/handler phân biệt thất bại xác thực với các lỗi khác. Không trả `Mono.empty()` khi password sai và không tự viết `onErrorResume(ex -> Mono.just(authenticatedAdmin))` vì điều đó tạo lỗ hổng.

`BadCredentialsException` có thể được chuyển thành HTTP `401` bởi HTTP Basic flow, nhưng `Mono.error(...)` **không tự nó là HTTP response**. HTTP status được quyết định bởi filter, failure handler, entry point và security configuration.

### 11.3. Retry có thể lặp công việc

`Mono` cold có thể chạy lại logic mỗi lần subscribe. `retry(...)` cũng có thể subscribe lại sau lỗi. Với xác thực:
- Không retry tự động **mật khẩu sai**: dễ gây nhiều lượt thử, tăng tải và làm sai chính sách rate limit.
- Có thể cân nhắc retry có giới hạn cho một số lỗi hạ tầng tạm thời, nhưng phải tách chúng khỏi `AuthenticationException`, có backoff và giới hạn rõ ràng.
- Nếu manager thực hiện side effects như audit, đếm lần nhập sai hoặc khóa tài khoản, phải tính đến idempotency và duplicate effects khi có retry.
- `timeout(...)` ở Reactor không bảo đảm hủy thực sự một lời gọi I/O blocking trong driver bên dưới.

### 11.4. Không dùng `block()` để lấy `Authentication` trong WebFlux handler

Sai:

```java
// Đoạn minh họa SAI, không sao chép vào handler:
Authentication result = manager.authenticate(request).block();
```

Đúng là trả publisher và kết hợp reactive:

```java
// Đoạn minh họa trong hàm trả Mono<String>:
return manager.authenticate(request)
        .map(Authentication::getName);
```

Với endpoint WebFlux thật, thường **không tự gọi** manager từ controller để làm lại authentication: hãy để WebFilter xác thực và đọc principal đã được xác thực. Mã đúng ở trên chỉ minh họa composition của Reactor, không thay cho Spring Security filter.

### 11.5. Các thông tin nhạy cảm trong `Authentication`

`Authentication.getCredentials()` có thể chứa password/token/raw secret trong giai đoạn trước xác thực. Không log nguyên `Authentication` vì `toString()`/diagnostic của implementation hoặc thư viện giám sát có thể làm lộ dữ liệu. Sau khi xác thực, hạn chế lưu credentials, không serialize đối tượng này ra response và không nhúng raw secret vào `details`.

## 12. Tách authentication khỏi authorization và HTTP status

Trong ví dụ:
- Đăng nhập `reader` đúng password -> manager trả `Authentication` hợp lệ có `ROLE_READER`.
- Request `GET /admin` vẫn nhận **403**, vì `hasRole("ADMIN")` không được đáp ứng.
- Đăng nhập `reader` sai password -> manager báo **authentication failure**; HTTP Basic thường phản hồi **401**.
- Request `GET /public` không có credentials vẫn **200** vì rule cho phép public. Điều này **không có nghĩa** manager đã xác thực một anonymous user thành công.

Điểm dễ nhầm: `Authentication.isAuthenticated()` biểu thị kết quả xác thực theo nghĩa của token, còn authorization dùng authorities và các rule. Không tự cấp `ROLE_ADMIN` vì request URI chứa `/admin`, cũng không coi `isAuthenticated()` luôn đủ cho mọi endpoint.

Với `AnonymousAuthenticationToken`, hệ thống có thể tạo một đối tượng authentication đại diện người truy cập vô danh trong security context; điều này **không** có nghĩa họ đã cung cấp credentials hợp lệ. `authenticated()` trong security authorization hiểu ngữ cảnh authentication hợp lệ theo semantics framework, không đơn thuần đọc Boolean một cách cơ học.

## 13. Lỗi thường gặp và cách gỡ

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Mật khẩu sai nhưng manager trả `Mono.empty()` | Nhầm “không hỗ trợ loại token” với “xác thực thất bại” | Trả `Mono.error(BadCredentialsException)` |
| `401` dù credentials đúng | `PasswordEncoder` không hợp hash đã lưu, username sai, manager không được dùng trong chain | Kiểm tra encoder, `ReactiveUserDetailsService` và `http.authenticationManager(...)` |
| `403` trên `/admin` dù đăng nhập thành công | Kết quả thiếu authority `ROLE_ADMIN` | Phân biệt xác thực với phân quyền và kiểm tra roles |
| `ClassCastException` khi custom manager nhận token lạ | Ép kiểu mà không kiểm tra loại | Kiểm tra `instanceof`, trả empty nếu unsupported |
| Controller WebFlux gọi `block()` | Dùng lối tư duy Servlet, có thể block event loop | Trả `Mono`/`Flux`, để framework subscribe |
| `Mono.just(null)` ném lỗi | Reactor không cho `null` làm item | Dùng `Mono.empty()` đúng nghĩa hoặc `Mono.justOrEmpty` khi là dữ liệu tùy chọn (không dùng để che auth failure) |
| Tự tạo token đã authenticated từ username trong header | Không xác minh secret; có thể cấp quyền giả | Xác minh bằng manager đáng tin và authorities từ backend |
| Token/hard-coded secret xuất hiện trong logs | Log đối tượng `Authentication`/exception/raw header | Loại bỏ credentials khỏi logs, redaction và secrets management |
| Custom manager gọi JDBC blocking trong event loop | Mất khả năng xử lý đồng thời của WebFlux | Dùng driver reactive hoặc `fromCallable` + `boundedElastic` cho nguồn blocking |
| Chỉ có `ReactiveUserDetailsService` nhưng chưa hiểu việc verify password | Nhầm tra user với chứng thực | Dùng `UserDetailsRepositoryReactiveAuthenticationManager` + `PasswordEncoder` |
| Kết quả test rỗng cho “sai password” | Dùng `onErrorResume(... -> Mono.empty())` hoặc fake manager sai logic | Viết test `expectError(BadCredentialsException.class)` |
| Trộn `AuthenticationManager` (Servlet) và `ReactiveAuthenticationManager` | API sync/reactive khác nhau | Ưu tiên manager reactive; adapter chỉ cho trường hợp cầu nối có kiểm soát |

### Checklist cho một implementation tùy chỉnh

1. Chỉ xử lý đúng loại `Authentication` mà manager hỗ trợ.
2. Xác minh credentials trên nguồn đáng tin, kiểm tra tài khoản/khóa/thu hồi.
3. Đúng credentials -> phát **một** Authentication đã xác thực; unsupported -> empty; invalid -> error.
4. Không phát auth đã xác thực nếu logic verify chưa chạy.
5. Không tin authorities do client tự đặt.
6. Không để I/O blocking chạy trên event loop.
7. Hạn chế raw secret tồn tại trong memory/log/response.
8. Test đủ success/error/empty và HTTP integration thực.
9. Kiểm soát retry, timeout, cancellation, audit, rate limits.
10. Tránh viết lại password authentication khi implementation Spring Security sẵn có đã đáp ứng.

## 14. Câu hỏi tự kiểm tra

**1.** `ReactiveAuthenticationManager.authenticate(...)` trả kiểu gì?  
**Đáp án:** `Mono<Authentication>`.

**2.** `Mono.empty()` có được dùng cho password sai không?  
**Đáp án:** Không. Nó biểu thị manager hiện tại không thể quyết định/không hỗ trợ; sai password phải đi nhánh lỗi xác thực.

**3.** Sau khi user store trả `UserDetails`, có thể coi đã xác thực chưa?  
**Đáp án:** Chưa; cần kiểm tra credentials, trạng thái user và tạo result hợp lệ.

**4.** Sự khác biệt giữa `BadCredentialsException` và `403 Forbidden` là gì?  
**Đáp án:** `BadCredentialsException` biểu thị authentication failure (HTTP Basic thường 401); `403` thường là đã xác thực nhưng không đủ quyền hoặc do cơ chế khác như CSRF.

**5.** Tại sao không tạo `UsernamePasswordAuthenticationToken.authenticated(...)` ngay từ request?  
**Đáp án:** Vì như vậy gán trạng thái đã xác thực khi chưa verify.

**6.** Vì sao test bằng `StepVerifier` có giá trị hơn chỉ gọi `.block()`?  
**Đáp án:** Nó kiểm tra chính xác chuỗi tín hiệu success/complete/error, rất phù hợp với hợp đồng Reactor.

**7.** Nếu một manager chỉ hỗ trợ API key nhận `UsernamePasswordAuthenticationToken` thì nên phát gì?  
**Đáp án:** `Mono.empty()` để thể hiện không xử lý loại token đó, nếu đúng theo chiến lược delegation.

**8.** Manager trả authentication đã xác thực rồi, tại sao `GET /admin` còn bị từ chối?  
**Đáp án:** Authentication và authorization là hai bước khác nhau; phải có authority cho quy tắc `hasRole("ADMIN")`.

**9.** Đặt `.retry(3)` cho mọi lỗi login có phù hợp không?  
**Đáp án:** Không; retry password sai là hành vi không mong muốn và có thể gây lặp side effects/rate limits.

**10.** `ReactiveSecurityContextHolder` giải quyết vấn đề gì?  
**Đáp án:** Cho phép truy cập security context theo Reactor Context xuyên qua reactive pipeline mà không phụ thuộc vào một request thread cố định.

### Bài tập thực hành

1. Trong test success, kiểm tra thêm `result.getAuthorities()` có `ROLE_READER` và `result.isAuthenticated() == true`.
2. Thêm test cho username không tồn tại. Quan sát loại `AuthenticationException` mà implementation cụ thể trả về; không yêu cầu exception phải phân biệt được user chưa tồn tại trên response công khai.
3. Tạo `ReactiveAuthenticationManager` đơn giản chỉ nhận `TestingAuthenticationToken` và trả `Mono.empty()` cho `UsernamePasswordAuthenticationToken`. Test bằng `StepVerifier.verifyComplete()`.
4. Tạo manager cố ý sai: trả `Mono.empty()` khi password sai. Viết test `expectError(...)` để chứng minh hợp đồng bị phá vỡ; sau đó sửa lại.
5. Bảo vệ endpoint `GET /reader` bằng `hasRole("READER")`, kiểm chứng reader và admin đều vào được nhưng request không có credential bị 401.
6. Trong bài nâng cao, dùng `DelegatingReactiveAuthenticationManager` kết hợp manager username/password và một manager chỉ hỗ trợ token riêng. Viết ba test phân biệt token hợp lệ, sai và không hỗ trợ mà không tiết lộ secret.

## 15. Tài liệu chính thức

- [Spring Security API — ReactiveAuthenticationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ReactiveAuthenticationManager.html): hợp đồng trả thành công/empty/error.
- [Spring Security API — UserDetailsRepositoryReactiveAuthenticationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/UserDetailsRepositoryReactiveAuthenticationManager.html): manager username/password.
- [Spring Security API — DelegatingReactiveAuthenticationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/DelegatingReactiveAuthenticationManager.html): ghép nhiều manager.
- [Spring Security API — AuthenticationWebFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html): chuyển HTTP request thành `Authentication` và xử lý kết quả.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): cấu hình `@EnableWebFluxSecurity` và `SecurityWebFilterChain`.
- [Spring Security — Reactive Security Context](https://docs.spring.io/spring-security/reference/reactive/authentication.html): nguyên tắc authentication và context reactive.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): dùng `StepVerifier` kiểm tra tín hiệu.

**Ghi nhớ:** `ReactiveAuthenticationManager` trả về **một kết quả đã xác thực** khi thành công, **empty** khi manager không có quyết định, và **error** khi xác thực thất bại. Đọc đúng ba tín hiệu này là nền tảng để tích hợp authentication trong Spring Security reactive mà vẫn giữ chính sách bảo mật chính xác.