# Cấu hình HTTP Basic, realm và WWW-Authenticate trong Spring Security (Servlet)

## 1. Mục tiêu và phạm vi

Sau bài này, bạn có thể:

- Bật HTTP Basic trong `SecurityFilterChain` bằng `HttpSecurity.httpBasic(...)`.
- Hiểu đúng hai chiều của giao thức: client gửi `Authorization: Basic ...`; server dùng `WWW-Authenticate: Basic realm="..."` để yêu cầu thông tin đăng nhập.
- Đổi tên `realm`, hiểu vai trò của `BasicAuthenticationEntryPoint` và không nhầm realm với cơ chế phân quyền.
- Phân biệt tình huống trả `401 Unauthorized`, `403 Forbidden` và việc endpoint `permitAll()` không đòi đăng nhập.
- Chạy thử, kiểm thử tự động và nhận diện những rủi ro bảo mật đặc thù của Basic Authentication.

Ví dụ sử dụng **Spring Security cho ứng dụng Servlet/Spring MVC**, `SecurityFilterChain` kiểu hiện đại và **Java 17+ / Spring Boot 3.x**. Cấu hình reactive/WebFlux sử dụng `ServerHttpSecurity` và không dùng nguyên mã Servlet bên dưới.

## 2. HTTP Basic gồm những gì?

HTTP Basic (RFC 7617) là cơ chế xác thực ở tầng HTTP, dùng cặp **username/password**. Nó không tự cấp access token, không có quy trình đăng nhập qua trang form và không mã hóa mật khẩu. Với mỗi request cần xác thực, client gửi một HTTP header:

```http
GET /api/profile HTTP/1.1
Host: localhost:8080
Authorization: Basic <Base64(username:password)>
```

- Phần sau `Basic ` là Base64 của chuỗi `username:password` (dấu hai chấm đầu tiên tách username khỏi password). **Base64 chỉ là mã hóa biểu diễn, không phải encryption**: ai đọc được header có thể khôi phục thông tin đăng nhập.
- Client như `curl -u`, Postman hoặc browser có thể tự tạo header; không cần viết Base64 bằng tay.
- Server xác thực username/password qua `AuthenticationManager` và `AuthenticationProvider` tương ứng, rồi mới kiểm tra quyền truy cập.
- Basic phù hợp với các hệ thống nhỏ, tác vụ tích hợp có kiểm soát hoặc tình huống học tập; ở môi trường thật phải dùng HTTPS và cân nhắc cơ chế không gửi lại mật khẩu dài hạn cho mỗi request.

### Hai header hay bị nhầm

| Header | Bên gửi | Mục đích |
|---|---|---|
| `Authorization: Basic <credentials>` | Client → Server | Cung cấp username/password đã Base64-encode để xác thực request |
| `WWW-Authenticate: Basic realm="Learning API"` | Server → Client, thường cùng `401` | Thông báo scheme xác thực mà tài nguyên yêu cầu và vùng bảo vệ (`realm`) |

Một chu kỳ tối giản:

```http
GET /api/profile HTTP/1.1
Host: localhost:8080

HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Learning API"
```

Client có thể gửi lại request cùng `Authorization: Basic ...`. Khi thông tin hợp lệ, server tiếp tục xử lý endpoint; nếu mật khẩu sai, kết quả thường lại là `401`. Các đoạn HTTP trên là **minh họa các dòng liên quan**, không phải toàn bộ headers/body thực tế.

## 3. Realm có nghĩa gì?

`realm` là chuỗi mô tả **protection space** mà server công bố trong challenge, ví dụ `Learning API`, `Partner Portal` hoặc `Internal Reports`. Browser có thể dùng scheme, origin và realm để phân biệt/ngữ cảnh hóa lời nhắc đăng nhập hoặc tái sử dụng credentials.

Điều cần hiểu đúng:

- `realmName("Learning API")` quyết định chuỗi realm xuất hiện trong `WWW-Authenticate` khi Spring Security phát Basic challenge.
- Đổi realm **không tạo** cơ sở dữ liệu người dùng, `AuthenticationManager` riêng, role mới hoặc hàng rào tenant. Việc ai đăng nhập được vẫn do hệ thống xác thực quyết định; ai được truy cập vẫn do authorization rules quyết định.
- Realm không nằm trong `Authorization: Basic ...` mà client gửi lại; `BasicAuthenticationFilter` xác thực credentials, không dùng realm như một trường chứng minh danh tính.
- Nếu cần tách những vùng API có cách xác thực hoặc chính sách khác nhau, thiết kế các `SecurityFilterChain` có `securityMatcher` và độ ưu tiên phù hợp; không dựa vào tên realm.

Trong Spring Security, có thể dùng tên mặc định của Basic challenge, nhưng **nên đặt realm dễ hiểu** nếu client là browser hoặc công cụ tích hợp cần phân biệt môi trường.

## 4. Đường đi của một request qua Spring Security

1. Request đi vào `FilterChainProxy` rồi `SecurityFilterChain` áp dụng cho URL đó.
2. Nếu có `Authorization: Basic ...`, `BasicAuthenticationFilter` giải mã credentials, tạo `UsernamePasswordAuthenticationToken` chưa xác thực và chuyển cho `AuthenticationManager`.
3. Với ví dụ dùng `UserDetailsService`, nhà cung cấp xác thực có thể tải user, đối chiếu password bằng `PasswordEncoder` và trả về `Authentication` đã xác thực kèm authorities.
4. Khi thành công, `Authentication` được đặt trong `SecurityContextHolder` cho request đang xử lý; `AuthorizationFilter` đối chiếu các quy tắc như `authenticated()` hoặc `hasRole("ADMIN")`.
5. Khi endpoint yêu cầu đăng nhập nhưng request chưa xác thực, `ExceptionTranslationFilter` dùng `AuthenticationEntryPoint` được chọn để bắt đầu xác thực. Với HTTP Basic, `BasicAuthenticationEntryPoint` có thể trả `401` và `WWW-Authenticate`.
6. Khi Basic credentials sai, `BasicAuthenticationFilter` xử lý thất bại xác thực và gọi entry point; client nhận yêu cầu xác thực lại.
7. Khi credentials đúng nhưng quyền thiếu, authorization dẫn tới **`403 Forbidden`** theo cấu hình thông thường. Đổi realm không biến `403` thành `401`.

**Đừng nhầm:** `401` nói rằng request chưa có xác thực hợp lệ hoặc cần xác thực lại; `403` nói rằng request đã được nhận diện nhưng không được phép làm việc được yêu cầu (hoặc một lớp bảo vệ khác, chẳng hạn CSRF, chặn request). Một endpoint `permitAll()` có thể trả `200` ngay cả khi không gửi `Authorization`.

## 5. Cấu hình thực hành với Spring Boot 3.x

Giả sử bạn đã có ứng dụng Spring Boot Servlet với Java 17+ và plugin quản lý dependency của Spring Boot. Cần tối thiểu hai starter sau; test tích hợp dùng thêm hai dependency test:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Nếu dùng Maven, thêm các starter tương ứng vào `pom.xml`. Ví dụ gồm ba file Java trong cùng package `com.example.basicauth`.

### 5.1. Điểm khởi động

File `src/main/java/com/example/basicauth/BasicDemoApplication.java`:

```java
package com.example.basicauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BasicDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(BasicDemoApplication.class, args);
    }
}
```

### 5.2. Định nghĩa người dùng và bật HTTP Basic

File `src/main/java/com/example/basicauth/SecurityConfig.java`:

```java
package com.example.basicauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(basic -> basic.realmName("Learning API"))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            );

        return http.build();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice-secret"))
                .roles("USER")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("bob-secret"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}
```

Giải thích các quyết định:

- `.httpBasic(basic -> basic.realmName("Learning API"))` kích hoạt `BasicAuthenticationFilter` và cấu hình tên realm cho challenge. Nếu không cần realm riêng, cú pháp tối giản là `.httpBasic(Customizer.withDefaults())` (import `org.springframework.security.config.Customizer`).
- Khi đã tự khai báo `SecurityFilterChain`, nên cấu hình tường minh cơ chế xác thực muốn dùng; đừng dựa vào các default mà Spring Boot có thể cung cấp khi **chưa** có bean chain tự viết.
- `UserDetailsService` trong ví dụ lưu user trong bộ nhớ để học và test; ứng dụng thật dùng nguồn danh tính/phương thức xác thực có quản trị thích hợp.
- `BCryptPasswordEncoder` giúp so khớp password với hash; **không lưu password dạng plaintext** trong kho dữ liệu thật. Hai password mẫu chỉ dành cho môi trường local.
- `roles("ADMIN")` tạo authority `ROLE_ADMIN`; vì vậy `hasRole("ADMIN")` khớp với user `bob`. User `alice` chỉ có `ROLE_USER`.
- `SessionCreationPolicy.STATELESS` yêu cầu Spring Security không dùng `HttpSession` để lưu/lấy `SecurityContext`. Với Basic, client vẫn phải gửi credentials trên từng request cần xác thực. Cấu hình này không làm HTTP Basic an toàn trước CSRF khi browser tự gửi credentials.
- Ví dụ **giữ nguyên bảo vệ CSRF mặc định**. Các endpoint demo là GET (không thay đổi trạng thái). Khi thêm POST/PUT/DELETE, cần quyết định chính sách CSRF theo loại client thật sự; không tắt toàn cục chỉ vì đã dùng Basic hoặc `STATELESS`.

### 5.3. Endpoint để thấy hiệu ứng của realm, 401 và 403

File `src/main/java/com/example/basicauth/ApiController.java`:

```java
package com.example.basicauth;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public Map<String, String> publicEndpoint() {
        return Map.of("message", "public");
    }

    @GetMapping("/api/profile")
    public Map<String, String> profile(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }

    @GetMapping("/api/admin")
    public Map<String, String> admin(Authentication authentication) {
        return Map.of("admin", authentication.getName());
    }
}
```

Chạy bằng tác vụ bootRun của dự án Gradle có cấu hình Spring Boot plugin:

```bash
./gradlew bootRun
```

Trên Windows PowerShell sử dụng `.\gradlew.bat bootRun`. Nếu dự án không có wrapper hoặc plugin Spring Boot, phải hoàn thiện phần build trước khi chạy lệnh; ba file Java trên được thiết kế cho **ứng dụng Spring Boot 3.x đã có build**, không phải chương trình `javac` độc lập.

### 5.4. Thử bằng curl và đọc kết quả

```bash
# Không cần đăng nhập:
curl -i http://localhost:8080/api/public

# Chưa gửi credentials:
curl -i http://localhost:8080/api/profile

# Username/password đúng:
curl -i -u alice:alice-secret http://localhost:8080/api/profile

# Sai password:
curl -i -u alice:wrong http://localhost:8080/api/profile

# Đúng password nhưng thiếu ROLE_ADMIN:
curl -i -u alice:alice-secret http://localhost:8080/api/admin

# User có ROLE_ADMIN:
curl -i -u bob:bob-secret http://localhost:8080/api/admin
```

| Request | Kết quả mong đợi | Ý nghĩa |
|---|---|---|
| `GET /api/public`, không header | `200`, JSON `{"message":"public"}` | `permitAll()` |
| `GET /api/profile`, không header | `401` cùng `WWW-Authenticate: Basic realm="Learning API"` | Server gửi Basic challenge |
| `GET /api/profile`, alice đúng password | `200`, JSON `{"user":"alice"}` | Xác thực thành công |
| `GET /api/profile`, alice sai password | `401`, thông thường có Basic challenge | Chưa xác thực hợp lệ |
| `GET /api/admin`, alice đúng password | `403` | Đã xác thực nhưng thiếu role |
| `GET /api/admin`, bob đúng password | `200`, JSON `{"admin":"bob"}` | Đủ role |

Bảng chỉ nêu **status và những giá trị cần kiểm tra**; status line, thứ tự headers, error body và những header bổ sung phụ thuộc môi trường. `curl -u` có thể khiến password mẫu xuất hiện trong lịch sử shell/tiến trình; không sử dụng bí mật thật theo cách này trong môi trường dùng chung.

Muốn xem riêng challenge, có thể dùng:

```bash
curl -i http://localhost:8080/api/profile
```

Dòng quan trọng trong phản hồi là `WWW-Authenticate: Basic realm="Learning API"`. Với browser, challenge này có thể kích hoạt hộp thoại hỏi username/password. Một số client hoặc request mang `X-Requested-With: XMLHttpRequest` có thể được cấu hình mặc định trả `401` mà **không** kèm challenge nhằm tránh bật hộp thoại trình duyệt; do đó cần xem loại client và entry point đang thực sự áp dụng khi debug.

## 6. Tùy chỉnh realm và AuthenticationEntryPoint đúng cách

### Đổi tên realm đơn giản

Dùng trực tiếp DSL khi chỉ cần thay chuỗi:

```java
http.httpBasic(basic -> basic.realmName("Partner API"));
```

Đây là cách gọn nhất để giữ hành vi mặc định của HTTP Basic và đổi thông tin challenge. Chuỗi realm nên ngắn, dễ nhận diện. Không dùng realm để chứa bí mật hoặc mã phân quyền.

### Khi cần một entry point riêng

`BasicAuthenticationEntryPoint` là implementation của `AuthenticationEntryPoint` có nhiệm vụ gửi `401` và `WWW-Authenticate`. Có thể cung cấp một bean đã đặt realm:

```java
@Bean
BasicAuthenticationEntryPoint partnerEntryPoint() {
    BasicAuthenticationEntryPoint entryPoint =
        new BasicAuthenticationEntryPoint();
    entryPoint.setRealmName("Partner API");
    return entryPoint;
}
```

Các import cho đoạn trên là `org.springframework.context.annotation.Bean` và `org.springframework.security.web.authentication.www.BasicAuthenticationEntryPoint`. Vì là Spring bean, callback `afterPropertiesSet()` được container gọi khi khởi tạo; nếu tự tạo instance ngoài container, cần khởi tạo/kiểm tra lifecycle tương ứng.

Để dùng bean này, **thay** dòng `httpBasic(...)` trong `SecurityFilterChain`, ví dụ với tham số `BasicAuthenticationEntryPoint partnerEntryPoint` được inject vào method tạo chain:

```java
.httpBasic(basic -> basic.authenticationEntryPoint(partnerEntryPoint))
```

Đây là **đoạn thay thế trong cấu hình**, không phải một `SecurityFilterChain` hoàn chỉnh. Tránh kết hợp `realmName(...)` và `authenticationEntryPoint(...)` trong cùng configurer: entry point riêng tự quyết định challenge; theo API Spring Security, gọi realmName sau khi đã đặt entry point riêng có thể bị từ chối. Khi viết entry point tùy biến để trả JSON lỗi, nếu vẫn theo chuẩn Basic thì phải bảo toàn status `401` và header challenge phù hợp; chỉ trả body JSON không đủ cho client nhận biết scheme xác thực.

### Tại sao có lúc không thấy WWW-Authenticate?

Không phải mọi lỗi HTTP đều tạo Basic challenge:

- `200` của resource public: không cần yêu cầu đăng nhập.
- `403` của user đã xác thực nhưng thiếu role: thường do `AccessDeniedHandler` xử lý; không cần đòi lại credentials.
- `401` do một entry point tùy chỉnh chỉ trả status, hoặc request AJAX được xử lý khác: có thể thiếu header.
- Request khớp một `SecurityFilterChain` khác, hoặc Basic chưa được bật trong chain tương ứng: hành vi có thể khác hẳn.
- Proxy/gateway đứng trước ứng dụng có thể tạo hoặc thay đổi phản hồi; cần kiểm tra log và headers tại đúng lớp xử lý.

Nếu dùng nhiều chain, phải xác minh `securityMatcher(...)`, `@Order` và cơ chế xác thực trên từng chain. `requestMatchers(...)` bên trong `authorizeHttpRequests` chỉ quy định quyền đối với request đã đi vào chain; nó **không** thay thế `securityMatcher` để chọn chain.

## 7. Kiểm thử tự động hành vi quan trọng

Sau khi bổ sung `spring-boot-starter-test` và `spring-security-test`, tạo file `src/test/java/com/example/basicauth/BasicAuthenticationTest.java`:

```java
package com.example.basicauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class BasicAuthenticationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void missingCredentialsReturnBasicChallenge() throws Exception {
        mvc.perform(get("/api/profile"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                "Basic realm=\"Learning API\""
            ));
    }

    @Test
    void validCredentialsReturnProfile() throws Exception {
        mvc.perform(get("/api/profile")
                .with(httpBasic("alice", "alice-secret")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("alice"));
    }

    @Test
    void validUserWithoutAdminRoleIsForbidden() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("alice", "alice-secret")))
            .andExpect(status().isForbidden());
    }

    @Test
    void incorrectPasswordIsUnauthorized() throws Exception {
        mvc.perform(get("/api/profile")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void publicEndpointNeedsNoCredentials() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk());
    }
}
```

Chạy `./gradlew test` (Windows: `.\gradlew.bat test`). Các test này xác minh hành vi HTTP từ request tới filter chain, gồm chuỗi realm thực tế; chúng không thay thế kiểm tra HTTPS/secret management khi triển khai production. Khi thay entry point hoặc có nhiều filter chain, sửa kỳ vọng challenge cho chain cần kiểm tra.

## 8. Bảo mật và các lỗi thường gặp

### HTTPS là bắt buộc

Thông tin username/password được mã Base64 **có thể đảo ngược**. Không gửi HTTP Basic qua HTTP không mã hóa ở môi trường thật, dù đã dùng `BCryptPasswordEncoder` khi lưu hash: BCrypt bảo vệ **password lưu trên server**, còn TLS bảo vệ **credentials đang truyền** trên mạng. HTTPS phải có cấu hình xác minh certificate đúng và không ghi `Authorization` vào log, tracing, exception message hoặc URL.

### Stateless không tự loại bỏ CSRF

Browser có thể tự đính kèm Basic credentials đã nhớ khi gửi request đến cùng server. Vì vậy ứng dụng web có thao tác thay đổi trạng thái **vẫn có thể bị CSRF**, kể cả khi `SessionCreationPolicy.STATELESS`. Spring Security bật bảo vệ CSRF mặc định cho các HTTP method không an toàn. Nếu API chỉ cho client không phải browser và không dựa trên cơ chế credentials tự gửi, hãy đánh giá threat model rồi giới hạn ngoại lệ CSRF vào đúng endpoints cần thiết; không sao chép `csrf.disable()` toàn cục như một nghi thức của Basic.

### Basic không có cơ chế logout server-side như session login

Khi client/browser giữ và tiếp tục gửi `Authorization`, server vẫn có thể xác thực lại ở request sau. Xóa `SecurityContext` của một request không bảo đảm browser quên credentials. Muốn thu hồi quyền truy cập thực tế cần vô hiệu hóa/đổi credentials hoặc thiết kế cơ chế xác thực có khả năng thu hồi phù hợp.

### Checklist khắc phục sự cố

| Hiện tượng | Kiểm tra đầu tiên |
|---|---|
| `401` dù đã gửi username/password | Header phải có scheme `Basic`, cặp credentials đúng, user tồn tại, password hash khớp encoder, account không bị khóa |
| `401` nhưng không thấy `WWW-Authenticate` | Có dùng `X-Requested-With: XMLHttpRequest`, entry point riêng, gateway/proxy, hay chain khác không? |
| Realm hiển thị sai | `realmName(...)` được cấu hình trên đúng chain chưa? Có `authenticationEntryPoint(...)` thay thế không? |
| `403` sau khi đăng nhập đúng | So sánh `ROLE_ADMIN` với `hasRole("ADMIN")`; kiểm tra authorization khác hoặc CSRF đối với request thay đổi trạng thái |
| `POST` bị `403` còn `GET` thành công | Kiểm tra CSRF token và chính sách cho nhóm client; không tự suy luận password sai |
| Browser vẫn gửi tài khoản cũ | Kiểm tra cache HTTP Basic credentials của browser, origin/realm; dùng cửa sổ riêng hoặc client thử nghiệm độc lập |
| `.httpBasic(...)` không có hiệu lực | Xác minh đúng `SecurityFilterChain`, `securityMatcher` và thứ tự nhiều chain; bật log Spring Security khi cần |
| Không thể tách quyền giữa hai realm | Realm chỉ là tên challenge; phải cấu hình authentication và authorization theo vùng URL thật sự |

## 9. Ghi nhớ khi áp dụng

- **`httpBasic(...)` bật cơ chế xác thực**, còn **`realmName(...)` đổi thông tin vùng bảo vệ** gửi cho client khi có Basic challenge.
- Client gửi **`Authorization`**; server yêu cầu xác thực bằng **`401 + WWW-Authenticate`**. Header challenge không phải bằng chứng rằng user đã đăng nhập.
- Phân biệt **`401` (cần xác thực)** và **`403` (không đủ quyền hoặc bị chính sách khác chặn)** trước khi sửa cấu hình.
- Sử dụng HTTPS, PasswordEncoder, role/authority phù hợp, giới hạn scope filter chain và giữ chính sách CSRF đúng theo loại client.
- Test đủ các ca: public, thiếu credentials, sai password, đúng password, thiếu role và đúng realm.

**Tài liệu tra cứu:**

- [Spring Security — Basic Authentication (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html)
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [RFC 7617 — The Basic HTTP Authentication Scheme](https://www.rfc-editor.org/rfc/rfc7617)
