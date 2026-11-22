# UserDetailsRepositoryReactiveAuthenticationManager và PasswordEncoder

**Chủ đề:** Spring Security – reactive (Spring WebFlux)  
**Ngữ cảnh:** Người dùng và mật khẩu  
**Yêu cầu nền tảng:** Java 17+, hiểu `Mono`, HTTP Basic và bean `@Configuration` trong Spring Boot.

Hai thành phần này giải quyết **hai trách nhiệm khác nhau nhưng liên kết chặt chẽ** khi xác thực username/password trong ứng dụng WebFlux:

- `UserDetailsRepositoryReactiveAuthenticationManager` là một `ReactiveAuthenticationManager`: nhận yêu cầu xác thực, truy xuất tài khoản qua `ReactiveUserDetailsService`, thực hiện kiểm tra liên quan đến người dùng và mật khẩu, rồi trả về `Mono<Authentication>` khi hợp lệ hoặc phát lỗi xác thực khi thất bại.
- `PasswordEncoder` quyết định **mật khẩu được biến đổi để lưu trữ thế nào** (`encode`) và **mật khẩu người dùng nhập có khớp hash lưu trữ không** (`matches`). Nó **không** tải user, cấp role, cấp session hay kiểm tra quyền truy cập endpoint.

**Kết luận thực hành:** Lưu **hash một chiều**, dùng cùng một chính sách `PasswordEncoder` khi tạo tài khoản và khi xác thực, truyền `ReactiveUserDetailsService` vào manager, rồi đưa manager vào đúng `SecurityWebFilterChain`. Sau khi xác thực, Spring Security dùng `Authentication` trong ngữ cảnh bảo mật reactive để áp dụng các quy tắc `authorizeExchange` và phục vụ mã nghiệp vụ.

## 1. Ba interface/lớp tham gia trong xác thực bằng mật khẩu

| Thành phần | Đầu vào | Đầu ra / vai trò | Điều nó không làm |
| --- | --- | --- | --- |
| `ReactiveUserDetailsService` | Username, qua `findByUsername(String)` | `Mono<UserDetails>` chứa username, **hash mật khẩu**, authorities và trạng thái tài khoản; hoặc empty nếu không có user | Không xác minh mật khẩu người dùng vừa nhập |
| `PasswordEncoder` | `encode(rawPassword)`, `matches(raw, encoded)` | Tạo hash khi đăng ký/đổi mật khẩu; kiểm tra mật khẩu khi login | Không biết user đang thuộc tenant nào hay có quyền đọc tài nguyên không |
| `UserDetailsRepositoryReactiveAuthenticationManager` | `Authentication` chưa xác thực (thường là `UsernamePasswordAuthenticationToken`) | `Mono<Authentication>` đã xác thực hoặc lỗi `AuthenticationException` | Không tự tạo HTTP response, cookie hay mapping endpoint |
| `SecurityWebFilterChain` / authentication web filter | HTTP request + credential | Chuyển credential thành token, gọi manager, thiết lập security context, xử lý lỗi và authorization | Không trực tiếp lưu mật khẩu vào database cho bạn |

Tránh nhầm những kiểu có tên gần giống:

- **Reactive/WebFlux:** `ReactiveUserDetailsService`, `ReactiveAuthenticationManager`, `UserDetailsRepositoryReactiveAuthenticationManager`, `ServerHttpSecurity`, `SecurityWebFilterChain`, `ReactiveSecurityContextHolder`.
- **Servlet/MVC:** `UserDetailsService`, `AuthenticationManager`, `DaoAuthenticationProvider`, `HttpSecurity`, `SecurityFilterChain`, `SecurityContextHolder` kiểu thread-local. Ví dụ Servlet không thể sao chép nguyên dạng sang WebFlux.

`MapReactiveUserDetailsService` là triển khai in-memory thích hợp để học hoặc test. Khi dùng database thật, triển khai `ReactiveUserDetailsService` riêng, trả kết quả từ repository **reactive**; không chuyển các lời gọi JDBC blocking thành “reactive” chỉ bằng cách bao chúng trong `Mono.just(...)`.

## 2. Luồng xác thực HTTP Basic từ đầu đến cuối

Trong ứng dụng WebFlux cấu hình HTTP Basic:

```text
Client GET /api/me
Authorization: Basic <encoded-user-and-password>
       |
       v
Spring Security AuthenticationWebFilter cho HTTP Basic
       | trích username/password từ header
       v
UsernamePasswordAuthenticationToken chưa xác thực
       |
       v
ReactiveAuthenticationManager.authenticate(token)
       |
       v
UserDetailsRepositoryReactiveAuthenticationManager
       |-- ReactiveUserDetailsService.findByUsername(username)
       |       └── UserDetails: username, passwordHash, authorities, trạng thái
       |-- PasswordEncoder.matches(rawPassword, passwordHash)
       |-- kiểm tra trạng thái user / chính sách bổ sung
       |
       +-- SAI: Mono phát AuthenticationException
       |         └── HTTP Basic thường trả 401 + WWW-Authenticate
       |
       +-- ĐÚNG: Mono<Authentication> đã xác thực
                 └── SecurityContext của request/subscriber
                           |
                           v
                 authorizeExchange: kiểm tra quyền
                           |
                  +--------+---------+
                  |                  |
             cho phép            thiếu quyền
                  |                  |
                  v                  v
             controller             403 (thường gặp)
                  |
                  v
         Mono/Flux -> HTTP response
```

Các bước xử lý diễn ra trong cơ chế reactive: tạo `Mono` và thực sự subscribe là hai việc khác nhau. `findByUsername` phải đưa dữ liệu của **đúng username** vào luồng; manager sẽ đối chiếu mật khẩu theo encoder đã chọn. Spring Security lo việc chọn filter, kết hợp authentication và authorization; service nghiệp vụ **không nên tự gọi** `manager.authenticate(...).subscribe()` chỉ để “ép đăng nhập”.

**Một điểm thường bị bỏ qua:** `Authentication.getAuthorities()` biểu thị quyền đã xác thực; `hasRole("ADMIN")` thường tra authority `ROLE_ADMIN` (prefix mặc định). Đăng nhập thành công không đồng nghĩa có quyền với mọi endpoint, còn `PasswordEncoder.matches(...) == true` tự nó chưa chứng minh tài khoản đang enabled hoặc đủ role.

## 3. Cách PasswordEncoder hoạt động

Interface cốt lõi (mô tả chữ ký):

```java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);
    boolean matches(CharSequence rawPassword, String encodedPassword);
    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
```

Ý nghĩa:

1. **Đăng ký hoặc đổi mật khẩu:** lấy mật khẩu gốc từ request qua đường an toàn, xác thực/chặn chính sách phù hợp, gọi `passwordEncoder.encode(raw)` **một lần** trước khi lưu; database lưu `encodedPassword` chứ không lưu `rawPassword`.
2. **Đăng nhập:** lấy **mật khẩu gốc** mà client gửi (chỉ dùng tạm trong quá trình xác thực), tải `encodedPassword` từ user store, gọi `passwordEncoder.matches(raw, encoded)`. Không giải mã hash; không “so lại hai chuỗi encode mới”.
3. **Nâng cấp hash:** `upgradeEncoding(encoded)` có thể báo hash đã cũ/yếu so với cấu hình mới. Để tự nâng cấp và lưu lại khi login hợp lệ cần tích hợp dịch vụ cập nhật mật khẩu; không phải mọi manager/repository tự sửa database chỉ vì bạn thay encoder.

Ví dụ hành vi đúng (đoạn Java minh họa, không phải chương trình độc lập):

```java
PasswordEncoder encoder =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();

String hash = encoder.encode("correct horse battery staple");

boolean ok = encoder.matches("correct horse battery staple", hash);
boolean wrong = encoder.matches("incorrect", hash);

System.out.println(ok);
System.out.println(wrong);
```

Stdout chính xác của **hai lệnh println**:

```text
true
false
```

Giá trị `hash` không được in vì BCrypt sử dụng salt ngẫu nhiên, nên chạy hai lần cho cùng một mật khẩu thường nhận **hai hash khác nhau**. Đó là hành vi đúng. Không so sánh `encoder.encode(input).equals(hashFromDatabase)`; hãy dùng `matches`.

### 3.1. Vì sao dùng hash chậm có salt?

Mật khẩu là bí mật dễ đoán và có thể bị lộ khi database bị sao chép. Hash mật khẩu chuyên dụng làm tăng chi phí tấn công ngoại tuyến. BCrypt là lựa chọn có sẵn và thực tế trong Spring Security; Argon2 hoặc PBKDF2 cũng là những thuật toán mật khẩu có chủ đích khi được cấu hình và hỗ trợ đúng cách.

- **Salt:** giá trị ngẫu nhiên gắn với mỗi mật khẩu/hashing, ngăn hai user có cùng mật khẩu sinh cùng hash cố định và làm khó tra bảng có sẵn. BCrypt lưu thông tin salt và work factor trong chuỗi hash.
- **Work factor / cost:** hash cố ý tốn công tính hơn SHA-256 thông thường, làm chậm việc thử hàng loạt mật khẩu. Cần benchmark trên hạ tầng thật để chọn mức phù hợp giữa bảo mật và độ trễ đăng nhập.
- **Không mã hóa có thể giải mã:** hash một chiều dùng để so khớp, không thể “decrypt” để trả lại mật khẩu cũ. Quên mật khẩu phải qua quy trình **reset** với token dùng một lần, thời hạn và xác minh phù hợp.

Dùng `MessageDigest` SHA-256 thuần, MD5, Base64 hoặc mã hóa đảo ngược làm cơ chế lưu mật khẩu là không phù hợp. Mật khẩu băm cũng không thay thế TLS; mật khẩu vẫn đi từ client đến server trong quá trình login và cần HTTPS ở ngoài localhost.

## 4. DelegatingPasswordEncoder và tiền tố {id}

`PasswordEncoderFactories.createDelegatingPasswordEncoder()` tạo `DelegatingPasswordEncoder`. Khi mã hóa mật khẩu mới, cấu hình mặc định thường chọn BCrypt và tạo dạng:

```text
{bcrypt}$2a$10$...phần-salt-và-hash...
```

**Đây là định dạng minh họa**, không phải hash hợp lệ để copy vào database. Thành phần:

- `{bcrypt}` là **id thuật toán** để `DelegatingPasswordEncoder` chọn implementation lúc `matches`.
- Phần `$2a$10$...` là chuỗi BCrypt chứa phiên bản, cost, salt và kết quả hash.
- Với các mật khẩu cũ, có thể tồn tại prefix khác như `{pbkdf2}` hoặc `{noop}` nếu hệ thống từng dùng chúng. Việc encoder biết đọc một định dạng **không có nghĩa** định dạng đó nên được tiếp tục dùng cho dữ liệu mới.

Khi gọi `matches(raw, "{bcrypt}...")`, delegating encoder đọc id `bcrypt` rồi chuyển phần còn lại cho `BCryptPasswordEncoder`. Nếu hash lưu **không có prefix** hoặc có id không được hỗ trợ, cấu hình mặc định có thể phát `IllegalArgumentException` như “There is no PasswordEncoder mapped for the id ...”. Không coi đó là sai mật khẩu thông thường hoặc tự chữa bằng cách tắt hashing.

**Sai lầm phổ biến:**

```java
// Tạo hash BCrypt thuần, thường KHÔNG có {bcrypt}:
String withoutId = new BCryptPasswordEncoder().encode("secret");

// Nhưng lại so khớp bằng DelegatingPasswordEncoder:
PasswordEncoder delegating =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();

// Có thể gặp lỗi vì thiếu id, dù phần BCrypt bên trong hợp lệ.
delegating.matches("secret", withoutId);
```

Đây là fragment có chủ ý để minh họa lỗi cấu hình, không nên copy vào luồng đăng nhập thật. Có thể lựa chọn nhất quán một `BCryptPasswordEncoder` cho cả encode/matches của hệ thống cũ hoặc **di trú dữ liệu** sang định dạng có `{id}`. Không tự động thêm `{bcrypt}` vào mọi bản ghi nếu chưa xác minh toàn bộ dữ liệu thực sự là BCrypt hợp lệ. Đừng đặt `setDefaultPasswordEncoderForMatches(NoOpPasswordEncoder.getInstance())` như cách vá lỗi tổng quát: nó có thể âm thầm chấp nhận mật khẩu dạng plaintext ngoài ý định.

### 4.1. Prefix {noop}: học được, nhưng đừng dùng cho production

Ví dụ trên mạng đôi khi dùng:

```java
User.withUsername("demo")
    .password("{noop}password")
    .roles("USER")
    .build();
```

`{noop}` nghĩa là **không hash mật khẩu**, phù hợp tối đa cho bài minh họa ngắn hạn nhưng không thích hợp để lưu user thực. Trong bài chạy được dưới đây, chúng ta dùng `PasswordEncoderFactories.createDelegatingPasswordEncoder()` để mã hóa bằng BCrypt ngay từ lúc tạo user in-memory.

### 4.2. Có nên đổi work factor và thuật toán không?

- Nếu dùng BCrypt trực tiếp: `new BCryptPasswordEncoder(strength)` (cost trong khoảng được API hỗ trợ). Cần cấu hình việc lưu hash tương ứng với encoder này.
- Nếu dùng Delegating: định nghĩa tập thuật toán/id và `idForEncode` rõ ràng khi cần đổi thuật toán cho mật khẩu mới, vẫn cho phép đọc các hash đã tồn tại trong giai đoạn migration. Không thay prefix bằng thao tác chuỗi tùy ý.
- Việc đổi cost không làm hash cũ biến mất; `matches` vẫn dựa trên dữ liệu được lưu, còn cơ chế rehash tùy theo tích hợp.
- Đánh giá giới hạn CPU/độ trễ, tốc độ login hợp lệ, khả năng chống brute force, memory requirements và cost theo thời gian. Không hạ work factor chỉ vì test bị chậm mà không đo.

## 5. Ví dụ ứng dụng WebFlux đầy đủ bằng Java 17+

Ta sẽ triển khai ba endpoint:

- `GET /public/ping`: công khai, trả `pong`.
- `GET /api/me`: yêu cầu đăng nhập; đọc username của Authentication trong Reactor Context.
- `GET /api/admin`: yêu cầu `ROLE_ADMIN`; reader không được truy cập.

Có hai tài khoản demo: `alice / alice123` với role `USER`, và `admin / admin123` với role `ADMIN`. Mật khẩu được encode **trước khi đưa vào in-memory user store**; manager dùng cùng encoder để xác minh. Mật khẩu ví dụ chỉ được sử dụng trên **localhost**, không tái sử dụng trên hệ thống thật.

### 5.1. Tệp dự án và dependency

```text
reactive-password-auth/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/password/
    │   │   ├── PasswordAuthApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── ProbeController.java
    │   └── resources/application.properties
    └── test/java/demo/password/
        └── PasswordAuthTests.java
```

Ví dụ dùng Spring Boot `3.5.7`, đã phát hành và có trên Maven Central, để có dependency nhất quán. Khi đưa vào sản phẩm, nâng lên phiên bản còn được hỗ trợ/bản vá mới phù hợp với chính sách dự án; không coi con số của ví dụ là khuyến nghị dùng cố định lâu dài.

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>reactive-password-auth</artifactId>
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
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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

`src/main/resources/application.properties`:

```properties
spring.application.name=reactive-password-auth
server.port=8080
```

Không thêm `spring-boot-starter-web` cho bài WebFlux: nếu cả MVC và WebFlux cùng có mặt, Spring Boot có thể chọn Servlet/MVC theo ưu tiên mặc định, làm sai kỳ vọng về filter reactive.

### 5.2. Entry point

`src/main/java/demo/password/PasswordAuthApplication.java`:

```java
package demo.password;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PasswordAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(PasswordAuthApplication.class, args);
    }
}
```

Ba lớp Java chính nằm cùng package `demo.password` và được component scan tìm thấy.

### 5.3. Cấu hình PasswordEncoder, ReactiveUserDetailsService và manager

`src/main/java/demo/password/SecurityConfig.java`:

```java
package demo.password;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    ReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice123"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(alice, admin);
    }

    @Bean
    UserDetailsRepositoryReactiveAuthenticationManager passwordManager(
            ReactiveUserDetailsService users,
            PasswordEncoder encoder) {

        UserDetailsRepositoryReactiveAuthenticationManager manager =
            new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    SecurityWebFilterChain security(
            ServerHttpSecurity http,
            UserDetailsRepositoryReactiveAuthenticationManager passwordManager) {

        return http
            .authenticationManager(passwordManager)
            .authorizeExchange(ex -> ex
                .pathMatchers("/public/ping").permitAll()
                .pathMatchers("/api/admin").hasRole("ADMIN")
                .pathMatchers("/api/me").authenticated()
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }
}
```

Điểm cần hiểu **theo từng bean**:

1. `passwordEncoder()` trả một policy encoder duy nhất được dùng xuyên suốt. Với factory mặc định của Spring Security phiên bản ví dụ, mật khẩu mới có prefix `{bcrypt}`.
2. `users(encoder)` tạo `UserDetails` mang **hash**. Mỗi lần ứng dụng khởi động, hash được tạo lại với salt mới, nhưng cùng mật khẩu gốc vẫn đăng nhập được. Đây là demo in-memory, không phải database tồn tại lâu dài.
3. `passwordManager(users, encoder)` tạo chính xác đối tượng `UserDetailsRepositoryReactiveAuthenticationManager` được học; constructor nhận `ReactiveUserDetailsService`, `setPasswordEncoder` cấu hình phép kiểm tra hash. Mặc định manager cũng có delegating encoder, nhưng khai báo tường minh tránh lệch policy giữa tạo mật khẩu và xác thực.
4. `security(..., passwordManager)` truyền manager vào `ServerHttpSecurity.authenticationManager`, cấu hình filter HTTP Basic nhận credential; chỉ các endpoint cần thiết được cho phép. `formLogin` tắt để bài test không bị redirect login form.
5. `hasRole("ADMIN")` là **authorization** sau khi authentication thành công. Alice hợp lệ mà không có role ADMIN vẫn nhận 403. Đăng nhập bằng admin không mở mọi route vì `anyExchange().denyAll()` chặn các đường chưa khai báo.

**Cẩn thận vòng đời Spring bean:** Hàm `users` phụ thuộc vào bean `PasswordEncoder` được Spring inject; không tạo một encoder khác trong controller hoặc một encoder khác khi so mật khẩu. Với database thật, user không được encode lại mỗi khi `findByUsername`: repository phải trả **hash đã lưu nguyên trạng**.

### 5.4. Controller đọc principal trong Reactor Context

`src/main/java/demo/password/ProbeController.java`:

```java
package demo.password;

import org.springframework.http.MediaType;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ProbeController {

    @GetMapping(value = "/public/ping",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping(value = "/api/me",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
    }

    @GetMapping(value = "/api/admin",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> admin() {
        return Mono.just("admin-ok");
    }
}
```

Khi Spring Security xác thực HTTP Basic thành công, controller `/api/me` đọc `Authentication` của subscription hiện tại qua `ReactiveSecurityContextHolder`, không lấy tên user từ query parameter hoặc HTTP header `X-User` không được tin cậy. Controller trả `Mono` cho framework subscribe; không gọi `subscribe()` thủ công.

## 6. Chạy ứng dụng và đối chiếu HTTP status

Trong thư mục `reactive-password-auth`:

```bash
java -version
mvn -version
mvn spring-boot:run
```

Dùng JDK 17+, Maven 3.9+ và cổng 8080 còn trống. Khi server Reactor Netty khởi động thành công, ở terminal khác:

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/me
curl -i --user alice:alice123 http://localhost:8080/api/me
curl -i --user alice:wrong http://localhost:8080/api/me
curl -i --user unknown:whatever http://localhost:8080/api/me
curl -i --user alice:alice123 http://localhost:8080/api/admin
curl -i --user admin:admin123 http://localhost:8080/api/admin
```

Dự kiến theo thứ tự:

| Request | Status | Body/ý nghĩa |
| --- | --- | --- |
| `/public/ping` không credential | 200 | `pong`; URL public |
| `/api/me` không credential | 401 | HTTP Basic challenge, thường có `WWW-Authenticate: Basic ...` |
| `/api/me` với Alice đúng mật khẩu | 200 | `alice` |
| `/api/me` với Alice sai mật khẩu | 401 | `matches` thất bại; không được cấp danh tính |
| `/api/me` với user không tồn tại | 401 | Không tiết lộ user có tồn tại hay không qua phản hồi công khai |
| `/api/admin` với Alice đúng mật khẩu | 403 | Đã xác thực nhưng thiếu `ROLE_ADMIN` |
| `/api/admin` với admin đúng mật khẩu | 200 | `admin-ok` |

`401` và `403` là kỳ vọng của mẫu dùng HTTP Basic và cấu hình lỗi mặc định thường gặp; app có form login, OAuth2, custom entry point hoặc access-denied handler có thể khác. Một response `401` **không xác định** chính xác là user không tồn tại, hash sai định dạng hay password sai: cần kiểm tra hệ thống ở phía server, đồng thời giữ thông báo cho client đủ chung để tránh username enumeration.

Trên Windows PowerShell, nếu `curl` là alias của `Invoke-WebRequest`, dùng `curl.exe`. Basic gửi credential qua header Base64, **không mã hóa đường truyền**; chỉ dùng localhost trong ví dụ và HTTPS trong hệ thống thật. Tránh đưa credential thật vào script, shell history hoặc log.

## 7. Kiểm thử bằng WebTestClient và StepVerifier

Bộ test sau kiểm tra hai tầng riêng biệt:

- **Tầng encoder/manager:** hash có prefix, mật khẩu đúng/sai, manager tạo `Authentication` và authorities, không đối chiếu hai hash mới bằng phép so sánh chuỗi.
- **Tầng HTTP:** filter sử dụng manager, endpoint cần xác thực và phân quyền phản hồi 200/401/403 đúng như mong đợi.

`@SpringBootTest(webEnvironment = RANDOM_PORT)` tạo server thật trên cổng ngẫu nhiên. Spring Boot 3.5 hỗ trợ inject `WebTestClient` cho ứng dụng WebFlux với cấu hình này; test không cần chạy `mvn spring-boot:run` ở một terminal khác. `StepVerifier` dùng để kiểm tra tín hiệu của các `Mono` độc lập.

`src/test/java/demo/password/PasswordAuthTests.java`:

```java
package demo.password;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class PasswordAuthTests {

    @Autowired
    WebTestClient client;

    @Autowired
    PasswordEncoder passwordEncoder;

    @Autowired
    ReactiveUserDetailsService users;

    @Autowired
    UserDetailsRepositoryReactiveAuthenticationManager manager;

    @Test
    void storedPasswordIsEncodedAndMatchesOnlyCorrectRawPassword() {
        StepVerifier.create(users.findByUsername("alice"))
            .assertNext(user -> {
                assertTrue(user.getPassword().startsWith("{bcrypt}"));
                assertFalse(user.getPassword().equals("alice123"));
                assertTrue(passwordEncoder.matches(
                    "alice123", user.getPassword()));
                assertFalse(passwordEncoder.matches(
                    "wrong", user.getPassword()));
            })
            .verifyComplete();
    }

    @Test
    void saltedHashesOfSameRawPasswordCanDiffer() {
        String first = passwordEncoder.encode("somePassword");
        String second = passwordEncoder.encode("somePassword");

        assertNotEquals(first, second);
        assertTrue(passwordEncoder.matches("somePassword", first));
        assertTrue(passwordEncoder.matches("somePassword", second));
    }

    @Test
    void managerAuthenticatesAndSuppliesAuthorities() {
        var request = UsernamePasswordAuthenticationToken.unauthenticated(
            "alice", "alice123");

        StepVerifier.create(manager.authenticate(request))
            .assertNext(auth -> {
                assertTrue(auth.isAuthenticated());
                assertEquals("alice", auth.getName());
                assertTrue(auth.getAuthorities().stream().anyMatch(
                    authority -> authority.getAuthority().equals("ROLE_USER")));
            })
            .verifyComplete();
    }

    @Test
    void managerRejectsIncorrectPassword() {
        var request = UsernamePasswordAuthenticationToken.unauthenticated(
            "alice", "incorrect");

        StepVerifier.create(manager.authenticate(request))
            .expectError(BadCredentialsException.class)
            .verify();
    }

    @Test
    void publicEndpointDoesNotRequirePassword() {
        client.get().uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void anonymousUserGetsHttpBasicChallenge() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void correctCredentialsReachProtectedEndpoint() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("alice", "alice123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("alice");
    }

    @Test
    void wrongPasswordReturns401() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("alice", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void unknownUserReturns401() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("unknown", "guess"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedUserWithoutAdminRoleGets403() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth("alice", "alice123"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminWithCorrectPasswordCanAccessAdminEndpoint() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth("admin", "admin123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin-ok");
    }
}
```

Chạy:

```bash
mvn test
```

Nếu chỉ có class `PasswordAuthTests`, kỳ vọng có **11 test pass**. Không cố đoán log Maven, thời gian hash BCrypt hay thứ tự test vì chúng thay đổi theo môi trường. Đây là mã mẫu để người đọc tạo project và thực thi; trước khi coi là kết quả kiểm thử thực tế, cần chạy bằng JDK/Maven đúng phiên bản.

### 7.1. Cách đọc kết quả và giới hạn test

- `storedPasswordIsEncodedAndMatchesOnlyCorrectRawPassword` xác nhận in-memory user store chứa hash, không chứa raw. Hash được tạo trong startup, không định trước chuỗi bytes.
- `saltedHashesOfSameRawPasswordCanDiffer` chứng minh không được so sánh hai hash bằng equality; nếu muốn test ổn định lâu dài khi đổi encoder, tập trung vào `matches` và policy thuật toán đã chọn. Với BCrypt, hai salt ngẫu nhiên khiến xác suất hai hash bằng nhau cực nhỏ.
- `managerAuthenticatesAndSuppliesAuthorities` chứng minh gọi **manager thật** có thể tạo `Authentication` và tải authorities của Alice.
- `managerRejectsIncorrectPassword` kiểm tra lỗi `BadCredentialsException` ở cấp manager cho **username có tồn tại, mật khẩu sai**; không khẳng định mọi kiểu lỗi xác thực đều dùng class này.
- Các test HTTP xác nhận filter nhận Basic header, gọi manager và áp dụng authorization; direct manager test một mình không chứng minh WebFilter đã được wiring đúng.
- Test `admin` được phép và Alice bị từ chối cùng URL làm rõ **authentication vs authorization**: mật khẩu đúng không có nghĩa đủ role.

Không biến test thành kiểm tra nội bộ hash bằng một chuỗi BCrypt hard-code; hash có salt ngẫu nhiên. Nếu muốn test chính sách nâng cấp, tự xây fixture hash legacy hợp lệ, cấu hình password service và khẳng định cập nhật được lưu thật sau xác thực thành công.

## 8. Thời điểm thực thi, hiệu năng và scheduler trong reactive

`ReactiveUserDetailsService.findByUsername` trả `Mono<UserDetails>`, thường được subscribe trong pipeline authentication. Các lưu ý:

1. Nếu nguồn user từ R2DBC/reactive driver, việc gọi repository trả Publisher thường chưa thực hiện I/O ngay; I/O chạy khi subscribe. **Không bao** lời gọi blocking vào `Mono.just(blockingRepository.findUser(...))` vì Java đánh giá đối số trước.
2. Kiểm tra mật khẩu BCrypt có chủ đích **tốn CPU**. Spring Security's `AbstractUserDetailsReactiveAuthenticationManager` có khả năng xử lý kiểm tra mật khẩu qua scheduler, tránh giả định mọi đoạn callback phải ở Netty event-loop. Đừng tự dựng `Schedulers.parallel()` bừa bãi cho mỗi request.
3. Kết hợp user lookup reactive, hash verification và authorization cần giữ **Reactor Context** của request. Không lưu principal trong biến static/singleton cho các request chạy đồng thời.
4. Đừng gọi `block()` trong event-loop WebFlux để truy vấn user hoặc chờ manager. Với nguồn dữ liệu bắt buộc blocking tạm thời, việc cô lập thành `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` có thể là cầu nối, nhưng vẫn cần kế hoạch chuyển sang driver reactive, giới hạn tải và đo latency.
5. Cần cân nhắc rate limiting, backoff, chống credential stuffing và giới hạn concurrency để endpoint login không bị dùng làm công cụ đốt CPU qua BCrypt. Không giảm cost hoặc disable hash để “sửa” timeout mà chưa đo chính xác.

Manager có `setScheduler(...)` cho tình huống tối ưu chuyên sâu; hãy giữ mặc định trước khi benchmark trừ khi có lý do đo được. Scheduler không thay thế việc bảo vệ database/CPU pool dưới tải cao.

## 9. Đưa ReactiveUserDetailsService từ in-memory sang database

In-memory dùng cho demo, test hoặc cấu hình nhỏ. Trong ứng dụng thực, cần bảng user và hash bền vững. Có thể dùng R2DBC và query theo username đã chuẩn hóa, duy nhất.

**Sơ đồ dữ liệu gợi ý:**

| Trường | Ý nghĩa |
| --- | --- |
| `id` | ID nội bộ, không nhất thiết trùng username |
| `username` | Giá trị duy nhất theo policy; chuẩn hóa input cẩn thận |
| `password_hash` | Chuỗi encode đầy đủ, bao gồm prefix `{id}` nếu dùng delegating |
| `enabled`, `locked` | Trạng thái tài khoản; manager kiểm tra qua `UserDetails` |
| `authorities` hoặc bảng role riêng | Quyền hiện tại, có thể cần resolve reactive |
| `password_changed_at`, `updated_at` | Phục vụ vòng đời/cảnh báo/cập nhật, không lưu raw |

Ví dụ **fragment thiết kế**, không phải file Java độc lập:

```java
@Service
class DatabaseUserDetailsService implements ReactiveUserDetailsService {
    private final AccountRepository accounts;

    DatabaseUserDetailsService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    public Mono<UserDetails> findByUsername(String username) {
        return accounts.findByUsername(username)
            .map(account -> User.withUsername(account.username())
                .password(account.passwordHash()) // KHÔNG encode lại
                .authorities(account.authorities().toArray(String[]::new))
                .disabled(!account.enabled())
                .accountLocked(account.locked())
                .build());
    }
}
```

Đoạn này giả định có `AccountRepository` với `Mono<Account> findByUsername(String)` và record/account model có các accessor tương ứng; cần import `@Service`, `Mono`, `User`, `ReactiveUserDetailsService`, `UserDetails` và kiểu domain. Nếu user không tồn tại, repository nên trả `Mono.empty()` theo hợp đồng dịch vụ. Đừng tự biến “không thấy user” thành user mặc định hay dùng mật khẩu rỗng.

Khi **tạo tài khoản** bằng API riêng, mã phục vụ lưu trữ có thể dùng:

```java
Mono<Account> register(RegisterRequest request) {
    return Mono.fromSupplier(() ->
            passwordEncoder.encode(request.password()))
        .flatMap(hash -> accounts.insert(
            request.username(), hash, /* fields đã xác minh khác */));
}
```

Đây là **pseudocode/fragment** để minh họa vị trí mã hóa; `Account`, `RegisterRequest` và `accounts.insert` do dự án định nghĩa. Lưu ý hash là việc tốn CPU; `Mono.fromSupplier` ở đây giúp trì hoãn nhưng **không tự chuyển thread**. Trong hệ thống thực cần đặt encode ở scheduler thích hợp hoặc dùng cơ chế quản lý tài khoản với resource control rõ ràng, rồi xử lý trùng username, xác minh email, rate limit và yêu cầu mật khẩu riêng. Không copy fragment này như mã controller đã hoàn chỉnh.

## 10. Nâng cấp hash mà không buộc mọi người đổi mật khẩu

Một tổ chức có thể nâng thuật toán/cost theo thời gian, ví dụ từ `{bcrypt}` với work factor cũ sang chính sách mới. Một kế hoạch phù hợp:

1. Dùng `DelegatingPasswordEncoder` để **vẫn đối chiếu được** các hash legacy đã được chấp nhận qua id đáng tin cậy. Chỉ cho phép những thuật toán cần thiết trong giai đoạn migration.
2. Khi user đăng nhập thành công, nếu `passwordEncoder.upgradeEncoding(storedHash)` báo cần nâng cấp, tạo hash mới bằng encoder hiện hành và lưu lại thông qua `ReactiveUserDetailsPasswordService`.
3. `UserDetailsRepositoryReactiveAuthenticationManager` kế thừa cơ chế `setUserDetailsPasswordService(...)`; muốn upgrade tự động phải cấu hình một implementation thực sự cập nhật storage và kiểm thử đường này.
4. Đảm bảo cập nhật password hash không ghi đè thay đổi đồng thời của người dùng, tuân thủ transaction/concurrency của datastore, và không làm hỏng quyền/flags của tài khoản.
5. Theo dõi tỷ lệ hash còn cũ, tài khoản ít đăng nhập, và có quy trình đổi mật khẩu/reset riêng cho trường hợp không thể di trú bằng login.

**Ví dụ interface cần triển khai**:

```java
public interface ReactiveUserDetailsPasswordService {
    Mono<UserDetails> updatePassword(UserDetails user, String newPassword);
}
```

Đây là chữ ký rút gọn để học; method thật dùng các kiểu tương ứng của Spring Security. Tham số `newPassword` trong cơ chế upgrade là **chuỗi hash mới** cần lưu, không phải yêu cầu lấy plaintext của user và đặt lại password ngoài luồng. Implementation phải cập nhật database và trả lại `UserDetails` đã cập nhật theo hợp đồng. Tránh logging chuỗi hash hoặc raw credential trong quá trình migration.

**Không làm như sau:** khi chuyển sang delegating, thay mọi password hash cũ bằng `encoder.encode(oldHash)`. Việc này sẽ hash **chuỗi hash**, làm người dùng không thể đăng nhập bằng mật khẩu gốc. Chỉ encode raw password lúc đăng ký/đổi mật khẩu hoặc sau **một lần đăng nhập đã xác thực thành công** có raw password trong phạm vi cần thiết.

## 11. Kiểm tra trạng thái user và xử lý lỗi an toàn

`UserDetails` còn mang các cờ như `enabled`, `accountNonLocked`, `accountNonExpired` và `credentialsNonExpired`. Manager và các check strategy liên quan dùng chúng để kiểm soát việc đăng nhập. Một account disabled/locked không nên được cấp `Authentication` hợp lệ chỉ vì mật khẩu khớp. Với chính sách riêng, cấu hình đúng check strategy thay vì bỏ qua trạng thái.

Các lỗi cần phân biệt **nội bộ** nhưng không tiết lộ quá nhiều **ra bên ngoài**:

| Tình huống | Điểm điều tra | Phản hồi công khai thường hợp lý |
| --- | --- | --- |
| Không có user | `findByUsername` không có kết quả / chiến lược manager | HTTP Basic 401, thông điệp chung |
| Sai mật khẩu | `PasswordEncoder.matches` false | 401, không tiết lộ user tồn tại |
| Hash không có prefix hoặc id không hợp lệ | Dữ liệu legacy lệch `DelegatingPasswordEncoder` | Điều tra cấu hình và migration; không tự bỏ hash |
| User disabled/locked/expired | `UserDetails` và check strategy | Từ chối đăng nhập theo policy; thông điệp công khai an toàn |
| Đúng mật khẩu nhưng thiếu quyền | `authorizeExchange`, role/authority, policy domain | Thường 403 |
| User store chậm/lỗi kết nối | Database reactive, timeout, retry, circuit breaker | Lỗi hệ thống, không fallback cho phép truy cập |
| BCrypt quá tốn thời gian trong tải cao | CPU capacity, scheduler, cost, rate limiting | Tối ưu có đo đạc, giữ cơ chế mật khẩu an toàn |

**Không log mật khẩu, Basic header, bearer token hoặc password hash đầy đủ.** Log event đăng nhập với request ID/user ID được phép, loại lỗi ở mức phù hợp, chống rò rỉ thông tin và tuân thủ kiểm soát dữ liệu. Không gửi stack trace hoặc password hash về client. Tránh khác biệt phản hồi công khai giữa “username chưa tồn tại” và “mật khẩu sai” khiến kẻ tấn công liệt kê tài khoản; với nguy cơ timing, cần đánh giá riêng thay vì tự giả định một thông báo giống nhau đã đủ chống phân biệt.

## 12. Lỗi cấu hình thường gặp và cách sửa

### 12.1. Lưu plaintext với encoder mạnh

`PasswordEncoder` chỉ giúp nếu **thực sự gọi `encode` trước khi lưu**. Lưu `"alice123"` trong database rồi dùng delegating encoder để `matches` là không đúng; đừng gắn `{noop}` hàng loạt để làm test xanh. Tạo migration có kiểm soát hoặc reset password theo chính sách.

### 12.2. Double encode lúc đọc user

`findByUsername` tuyệt đối không làm:

```java
return repository.findByUsername(username)
    .map(user -> User.withUsername(user.username())
        .password(passwordEncoder.encode(user.passwordHash())) // SAI!
        .roles("USER")
        .build());
```

Đây là fragment cố ý sai (các kiểu repo/model do ứng dụng định nghĩa). Lỗi này biến chuỗi hash từ database thành **input của lần hash mới**, khiến mật khẩu đúng không bao giờ khớp. Trả hash gốc từ database.

### 12.3. Dùng BCryptPasswordEncoder một bên và DelegatingPasswordEncoder bên kia

BCrypt thuần thường trả `$2a$...` không có prefix; delegating mặc định cần `{id}`. Chọn cấu hình lưu/đọc đồng nhất, hoặc di trú định dạng đúng. Không tự mặc định thêm `{bcrypt}` cho giá trị chưa kiểm chứng.

### 12.4. Chọn nhầm API Servlet

`DaoAuthenticationProvider`, `UserDetailsService`, `HttpSecurity` và `SecurityFilterChain` thuộc stack Servlet. Với WebFlux, dùng `UserDetailsRepositoryReactiveAuthenticationManager`, `ReactiveUserDetailsService`, `ServerHttpSecurity`, `SecurityWebFilterChain`. Đừng mong `@EnableWebSecurity` tự cài filter reactive đúng cho dự án.

### 12.5. Tự chặn event loop bằng bcrypt/SQL

Gọi trực tiếp JDBC blocking bên trong controller hoặc ở bước assembly làm WebFlux nghẽn dù method trả `Mono`. Với database, dùng R2DBC hoặc cô lập blocking trên scheduler thích hợp. Với password hashing, dùng cơ chế scheduler của manager/cấu hình được đo đạc; không tạo executor mới cho mỗi request.

### 12.6. Đặt default permitAll khi debug login

Khi thấy 401, nhiều người đổi `anyExchange().permitAll()` rồi tưởng đã “sửa” authentication. Điều đó làm endpoint bị công khai. Hãy kiểm tra Basic header, user store, password hash id và encoder, sau đó mới xét authorization. Đừng sửa policy bằng cách bỏ bảo mật.

### 12.7. Phân quyền theo username trong URL

`/api/users/alice` không tự an toàn với user Alice nếu endpoint chỉ `authenticated()`; cần so resource owner với `Authentication` hoặc kiểm tra quyền ở service. Password manager giải quyết **xác thực danh tính**, không giải quyết quyền sở hữu từng bản ghi.

### 12.8. Giữ Authentication trong singleton hay ThreadLocal

Một lần đăng nhập thành công không phải lý do lưu `Authentication` vào `static currentUser` hoặc cache toàn cục. Request reactive chạy xen kẽ và context nằm trong subscription; dùng `ReactiveSecurityContextHolder`, không dùng dữ liệu còn sót từ request trước. Mật khẩu/hash không nên được giữ trong shared mutable state.

## 13. Áp dụng vào môi trường production

**Quản lý tài khoản:** Username có uniqueness và chuẩn hóa được xét rõ ràng, không tự ép lowercase hoặc normalize Unicode tùy tiện sau khi tài khoản đã được tạo. Mật khẩu mạnh, xử lý reset/verify email/thay đổi mật khẩu theo chính sách. Lưu hash toàn vẹn (không cắt cột database vì prefix hoặc độ dài thuật toán), không log secrets.

**Bảo vệ endpoint login:** HTTPS, rate limiting theo nhiều chiều (IP/tài khoản/risk), giám sát credential stuffing, khóa/chậm có điều kiện phù hợp, và MFA khi cần. Hash chậm là lớp bảo vệ sau khi lộ database, không thay thế chống tấn công trực tuyến.

**Quyền và trạng thái user:** Lấy authorities đáng tin cậy, xem xét thay đổi quyền, account lock/disable và dữ liệu trên từng tài nguyên. Không đưa raw password hoặc object `UserDetails` nguyên vẹn vào JSON response.

**Hiệu năng:** Benchmark encoder theo CPU/cost hiện tại. Không thực hiện hash trong vòng lặp hoặc tạo mới encoder liên tục để “thử” từng đăng nhập. Phân tách việc tra user (I/O) và so mật khẩu (CPU); quan sát latency, queue và tải login, kiểm soát concurrency.

**Khả năng mở rộng:** Khi có nhiều `SecurityWebFilterChain`, manager phải được nối vào đúng chuỗi thực sự nhận request; hai chain có cơ chế xác thực khác nhau có thể cần manager khác nhau. Nếu dùng OAuth2/JWT, bearer token không được xác minh bằng `PasswordEncoder` và không nên áp cơ chế username/password nhầm vào resource server.

**Di trú hash:** Dùng id thuật toán và dịch vụ nâng cấp, có kế hoạch xử lý legacy/noop và chính sách reset. Không đảo ngược hash, không tự động fallback sang so sánh plaintext khi lỗi id.

**Testing:** Ngoài test login đúng/sai còn kiểm tra user locked/disabled, thiếu quyền, giá trị hash thiếu prefix, password change, nâng cấp hash và thời gian xử lý trên tải thật. Tất cả test phải giữ nguyên security filter thay vì gọi controller trực tiếp rồi kết luận login an toàn.

## 14. Câu hỏi tự đánh giá

**Câu 1.** Cùng mật khẩu gốc mà `encode` hai lần ra hai chuỗi khác nhau. Có lỗi không?  
**Không.** Với BCrypt có salt ngẫu nhiên, đây là hành vi dự kiến; dùng `matches(raw, storedHash)`.

**Câu 2.** `ReactiveUserDetailsService.findByUsername` nên trả mật khẩu gốc hay hash?  
**Hash đã lưu** trong `UserDetails.getPassword()`. Manager dùng `PasswordEncoder` để so với raw credential của lần đăng nhập hiện tại.

**Câu 3.** Vì sao một user nhập đúng mật khẩu nhưng nhận 403 ở `/api/admin`?  
Xác thực thành công, nhưng tài khoản không có `ROLE_ADMIN`; đây là **authorization**, không phải lỗi encoder.

**Câu 4.** Một hash BCrypt từ thư viện khác không có `{bcrypt}`. DelegatingPasswordEncoder mặc định có luôn đọc được không?  
**Không đảm bảo.** Nó cần id được hỗ trợ; phải chọn/di trú cấu hình đúng, không tự bật `noop`.

**Câu 5.** Có thể dùng `Mono.just(jdbcRepository.findByUsername(...))` để làm nguồn reactive?  
**Không đúng.** Lời gọi JDBC đã chạy trước khi tạo `Mono` và có thể block thread; cần R2DBC hoặc cách cô lập blocking phù hợp.

**Câu 6.** Chỉ cần tạo bean `PasswordEncoder` có tự nâng cấp mọi hash trong database không?  
**Không.** Cần logic/`ReactiveUserDetailsPasswordService` được cấu hình để lưu hash mới, điều kiện nâng cấp và test bảo toàn dữ liệu.

**Câu 7.** Khác biệt chính giữa `UserDetailsRepositoryReactiveAuthenticationManager` và `DaoAuthenticationProvider` là gì?  
Cả hai phục vụ username/password, nhưng manager được hỏi ở đây thuộc **reactive/WebFlux** và dùng `ReactiveUserDetailsService`, còn provider kia là thành phần **Servlet** thường dùng với `UserDetailsService` và `AuthenticationManager` đồng bộ.

**Câu 8.** Nếu client gửi header `X-Role: ADMIN` cùng mật khẩu đúng của Alice, role có tự đổi thành ADMIN không?  
**Không.** Authorities đến từ `UserDetails`/hệ thống tin cậy. Header tự khai không phải nguồn cấp quyền.

**Câu 9.** Có cần gọi `subscribe()` trong controller để kích hoạt xác thực không?  
**Không.** Spring Security/WebFlux điều phối pipeline request và subscription. Gọi `subscribe()` thủ công có thể tách công việc khỏi lifecycle và context.

### Tài liệu chính thức

- Spring Security, `UserDetailsRepositoryReactiveAuthenticationManager` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/UserDetailsRepositoryReactiveAuthenticationManager.html
- Spring Security, `AbstractUserDetailsReactiveAuthenticationManager` (encoder, scheduler, password upgrade): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AbstractUserDetailsReactiveAuthenticationManager.html
- Spring Security, *Password Storage / DelegatingPasswordEncoder*: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Security, *Spring Security Crypto Module*: https://docs.spring.io/spring-security/reference/features/integrations/cryptography.html
- Spring Security, `ServerHttpSecurity` API (ReactiveAuthenticationManager): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Boot 3.5, *Testing Spring Boot Applications*: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html

**Ghi nhớ:** `ReactiveUserDetailsService` **tìm đúng người dùng và hash**, `PasswordEncoder` **mã hóa và so khớp mật khẩu một chiều**, `UserDetailsRepositoryReactiveAuthenticationManager` **kết hợp hai thành phần để xác thực**, còn `SecurityWebFilterChain` **kết nối xác thực vào HTTP và kiểm tra quyền**. Cấu hình nhất quán cả bốn phần, lưu hash đúng định dạng, và test đường thành công lẫn từ chối để tránh nhầm lẫn hoặc vô tình nới quyền.