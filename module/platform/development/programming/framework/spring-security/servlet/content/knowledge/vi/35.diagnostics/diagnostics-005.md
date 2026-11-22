# `ProviderNotFoundException`, `BadCredentialsException` và lỗi trạng thái tài khoản

## 1. Mục tiêu học tập và bối cảnh Spring Security Servlet

Khi bảo vệ API hoặc web application bằng **Spring Security trên Servlet stack**, những lỗi liên quan đến đăng nhập thường xuất hiện dưới dạng `AuthenticationException`. Hai lỗi dễ nhầm là:

- **`ProviderNotFoundException`**: `AuthenticationManager` không tìm được `AuthenticationProvider` xử lý thành công **loại `Authentication` đầu vào**; thường là sai hoặc thiếu provider, không phải kết luận rằng user nhập sai mật khẩu.
- **`BadCredentialsException`**: một provider đã tiếp nhận việc xác thực nhưng coi thông tin xác thực là không hợp lệ. Với `DaoAuthenticationProvider`, điều này thường là mật khẩu sai; mặc định một số trường hợp username không tồn tại cũng được che giấu bằng lỗi này.
- **Lỗi trạng thái tài khoản**: chẳng hạn `LockedException`, `DisabledException`, `AccountExpiredException`, `CredentialsExpiredException`. Tài khoản có thể có username/password đúng nhưng vẫn bị từ chối do chính sách quản trị tài khoản.

Bài này phân tích nguyên nhân, vòng đời `AuthenticationManager`/`AuthenticationProvider`, cách đọc kết quả HTTP `401`/`403`, cách chẩn đoán an toàn trong log và cách kiểm thử bằng Java 17+ với Spring Boot 3.3.x / Spring Security 6.x. Những cách kiểm lỗi trong bài nhằm **phân tích hệ thống**, không nhằm tiết lộ user tồn tại hay trạng thái chi tiết của họ cho người ngoài.

## 2. Luồng xác thực HTTP Basic trong một ứng dụng Servlet

Luồng đơn giản:

```text
HTTP request
  Authorization: Basic ...
           |
           v
SecurityFilterChain
           |
           v
BasicAuthenticationFilter
  tạo UsernamePasswordAuthenticationToken chưa xác thực
           |
           v
AuthenticationManager (thường là ProviderManager)
           |
           +-- Provider A: supports(token type)?
           |       không -> bỏ qua
           |
           +-- Provider B (ví dụ DaoAuthenticationProvider)
           |       hỗ trợ UsernamePasswordAuthenticationToken
           |       |
           |       +-- tải UserDetails
           |       +-- kiểm trạng thái tài khoản
           |       +-- đối chiếu password bằng PasswordEncoder
           |       +-- kiểm trạng thái credentials
           |       |
           |       +-- thành công -> Authentication authenticated
           |       +-- thất bại -> AuthenticationException
           |
           v
SecurityContext (nếu xác thực thành công)
           |
           v
AuthorizationFilter / @PreAuthorize
  đủ quyền -> Controller
  thiếu quyền -> AccessDeniedException -> 403 thông thường
```

Đây là luồng khái niệm cho **HTTP Basic với provider username/password**. Form login dùng `UsernamePasswordAuthenticationFilter`; JWT Resource Server có `BearerTokenAuthenticationFilter` và `JwtAuthenticationProvider`; các kiểu token khác có provider/manager khác. Không lấy một exception của Basic auth rồi suy ra tất cả cơ chế xác thực đều dùng `DaoAuthenticationProvider`.

Phân biệt các ranh giới:

1. **Authentication input**: token object do filter hoặc caller tạo, chẳng hạn `UsernamePasswordAuthenticationToken`.
2. **Authentication routing**: `ProviderManager` tìm provider phù hợp.
3. **Credential/identity validation**: provider và nguồn dữ liệu user hoặc identity provider đánh giá thông tin xác thực.
4. **Account policy**: kiểm tra locked/disabled/expired theo loại provider.
5. **Authorization**: kiểm tra quyền trên endpoint/object sau khi đã xác thực.

Lỗi tại tầng 2 khác bản chất với lỗi ở tầng 3, 4 hoặc 5.

## 3. `Authentication`, `AuthenticationManager` và `AuthenticationProvider`

Ba hợp đồng quan trọng:

```java
public interface AuthenticationManager {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;
}
```

```java
public interface AuthenticationProvider {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;

    boolean supports(Class<?> authentication);
}
```

Đây là **trích yếu chữ ký API để giải thích**, không phải hai interface nên định nghĩa lại trong project.

`AuthenticationManager` là điểm tiếp nhận yêu cầu xác thực. `ProviderManager` là implementation thường gặp: lặp qua các `AuthenticationProvider`, kiểm tra `supports(...)`, gọi `authenticate(...)`, có thể dùng manager cha nếu đã cấu hình.

Một provider có thể:

- Trả `Authentication` đã xác thực: thành công.
- Trả `null`: không quyết định được và để provider khác có cơ hội xử lý.
- Ném `AuthenticationException`: đã xử lý nhưng xác thực thất bại hoặc có vấn đề nội bộ.

Một số exception như `AccountStatusException` và `InternalAuthenticationServiceException` được `ProviderManager` coi là trường hợp dừng sớm; các exception khác có thể được lưu rồi tiếp tục thử provider tiếp theo. Vì vậy đừng rút ra quy luật “một provider ném lỗi luôn là kết quả cuối cùng” khi một application có nhiều providers.

`supports(Class<?>)` chỉ nói provider **có thể nhận diện loại token**, không bảo đảm nó có thể xác thực mọi instance của loại token ấy. Đúng kiểu token nhưng sai credential có thể dẫn tới `BadCredentialsException`; sai kiểu token hoặc không provider nào xử lý sẽ hướng đến `ProviderNotFoundException`.

## 4. `ProviderNotFoundException`: không có provider nhận việc

Ví dụ tình huống:

```text
Input token: UsernamePasswordAuthenticationToken
Configured provider: AnonymousAuthenticationProvider only

AnonymousAuthenticationProvider.supports(
    UsernamePasswordAuthenticationToken.class) == false
       |
       v
ProviderManager không có provider phù hợp
       |
       v
ProviderNotFoundException
```

Trong thực tế, thông điệp thường cho biết loại `Authentication` mà manager không xử lý, như `UsernamePasswordAuthenticationToken`. Không dùng nguyên văn thông điệp exception làm contract của HTTP API, vì tên class và cấu hình thay đổi giữa môi trường/phiên bản.

Các nguyên nhân phổ biến:

1. **Thiếu provider đúng loại**: filter tạo token username/password nhưng manager chỉ được gắn provider kiểu khác.
2. **Custom `AuthenticationManager` che cấu hình mặc định**: sau khi tạo bean hoặc cấu hình manager riêng, `DaoAuthenticationProvider`/provider từng có không còn nằm trong manager đang dùng.
3. **Sai token class**: custom filter tạo một implementation `Authentication` chưa được provider tương ứng hỗ trợ.
4. **Sai `SecurityFilterChain` hoặc thứ tự matcher**: request vào một chain khác với chain được mong đợi, sử dụng manager có danh sách provider khác.
5. **Provider trả `null`** cho toàn bộ trường hợp, không có manager cha xử lý thành công.
6. **Tích hợp tự viết bị sai `supports(...)`**, ví dụ nhận một subclass không mong đợi hoặc so sánh class bằng `==` không phù hợp với thiết kế.
7. **Spring context/wiring sai**: bean tồn tại nhưng không được thêm vào `ProviderManager` thực sự phục vụ filter.

Không nên xử lý bằng cách đổi mọi lỗi thành `BadCredentialsException`, hoặc thêm một provider “luôn authenticated” để test pass. Điều cần sửa là **authentication graph**: filter tạo loại token nào, manager nào nhận token, provider nào hỗ trợ loại token đó, chain nào sở hữu manager.

### Khi nào không phải `ProviderNotFoundException`?

Nếu `DaoAuthenticationProvider` hỗ trợ `UsernamePasswordAuthenticationToken` và kiểm mật khẩu nhưng thấy sai, nó thường ném `BadCredentialsException`, **không** ném `ProviderNotFoundException`. Còn nếu credentials đúng nhưng user đã khóa, kết quả có thể là `LockedException`.

Điều tra đúng bản chất sẽ tránh việc cấu hình thêm provider khi lỗi thực chất là credential hoặc account policy.

## 5. `BadCredentialsException`: credentials không được chấp nhận

Với username/password authentication, `BadCredentialsException` thường xuất hiện khi password không khớp `PasswordEncoder.matches(...)`. Tuy nhiên cần nhớ:

- Tên user không tồn tại thường cũng có thể tạo **cùng loại lỗi** để tránh tiết lộ danh sách tài khoản.
- Password encoding `{bcrypt}`, `{noop}` hoặc id khác phải khớp encoder. Lỗi thiếu password encoder/prefix có thể gây exception khác hoặc lỗi cấu hình, không phải lúc nào cũng là một `BadCredentialsException` rõ ràng.
- Nếu user đã bị khóa/vô hiệu hóa, provider có thể ném status exception **trước khi so khớp password**.
- Authentication từ token, API key, LDAP, OAuth2/JWT có semantics credential khác; cùng exception class không đảm bảo cùng nguyên nhân.

`AbstractUserDetailsAuthenticationProvider` có cơ chế `hideUserNotFoundExceptions` (mặc định bật ở các cấu hình phổ biến), chuyển `UsernameNotFoundException` thành `BadCredentialsException` đối với caller. Không tắt chế độ này ở production chỉ để người dùng thấy “email không tồn tại”.

Thông báo công khai an toàn thường là:

```json
{
  "error": "invalid_credentials",
  "message": "Không thể đăng nhập bằng thông tin đã cung cấp."
}
```

Cùng một thông báo nên áp dụng cho user không tồn tại và password sai nếu hệ thống cần chống account enumeration. Với HTTP Basic, `BasicAuthenticationEntryPoint` mặc định có thể trả `401` và header `WWW-Authenticate`, không tự phát JSON trên. Để dùng JSON, cần một entry point/failure handler phù hợp mà vẫn giữ HTTP semantics.

**Không ghi** password người dùng, Basic `Authorization` header hoặc credentials của `Authentication` vào log để “tìm sai ở đâu”.

## 6. Lỗi trạng thái tài khoản và vị trí kiểm tra

Trong `UserDetails`, các cờ phổ biến gồm:

| Thuộc tính `UserDetails` | Kết quả tốt | Trường hợp lỗi | Exception điển hình |
| --- | --- | --- | --- |
| `isAccountNonLocked()` | `true` | Tài khoản bị khóa | `LockedException` |
| `isEnabled()` | `true` | Tài khoản bị vô hiệu hóa | `DisabledException` |
| `isAccountNonExpired()` | `true` | Hết hạn tài khoản | `AccountExpiredException` |
| `isCredentialsNonExpired()` | `true` | Mật khẩu/credentials hết hạn | `CredentialsExpiredException` |

Với `DaoAuthenticationProvider`, các kiểm tra trạng thái tài khoản trước authentication thường kiểm locked, enabled, account non-expired; kiểm credentials non-expired diễn ra sau bước kiểm password trong checker mặc định. Đây là **hành vi của provider/checker cụ thể**, không phải lời hứa rằng mọi custom provider sẽ có cùng thứ tự.

Các exception trạng thái thường thuộc họ `AccountStatusException` trong Spring Security. Chúng **không đồng nghĩa user thiếu quyền truy cập một endpoint**. Một user đã authenticated nhưng thiếu `ROLE_ADMIN` được chặn ở authorization, thường là `AccessDeniedException` dẫn tới HTTP 403, chứ không phải `DisabledException`.

### Thiết kế vận hành

- **Locked:** cần biết lock được kích hoạt do policy nào; không tự mở khóa tài khoản bằng cách cho client retry vô hạn.
- **Disabled:** có thể liên quan tới quyết định của admin, lifecycle nhân sự hoặc vi phạm chính sách; client chỉ nên thấy thông báo chung.
- **Account expired:** trạng thái hiệu lực danh tính hết hạn; có thể yêu cầu quy trình renew hoặc cập nhật thông tin.
- **Credentials expired:** user cần thay/khôi phục credentials qua flow được bảo vệ; không đổi trạng thái trong controller bằng đầu vào chưa xác thực.
- **Multiple providers:** LDAP/IdP/Dao có thể trả exception khác nhau cho cùng tình huống; cần map diagnostic mà không lộ chi tiết nội bộ.

Không biến một account-status exception thành “mật khẩu sai” trong log vận hành nội bộ, vì sẽ khiến đội hỗ trợ yêu cầu user nhập lại mật khẩu không có tác dụng. Nhưng cũng không tiết lộ `user exists, locked until ...` cho unauthenticated caller nếu điều đó tạo account enumeration.

## 7. So sánh nhanh các lỗi hay nhầm

| Exception / sự kiện | Tầng phát sinh | Ý nghĩa | Phản hồi HTTP thường gặp |
| --- | --- | --- | --- |
| `ProviderNotFoundException` | `ProviderManager` | Không provider nào xác thực loại token được đưa vào | Có thể bị authentication entry point ánh xạ thành 401; cần xem lỗi cấu hình nội bộ |
| `BadCredentialsException` | Provider xác thực | Credentials sai hoặc che giấu user không tồn tại | 401 với HTTP Basic; form login có thể redirect |
| `UsernameNotFoundException` | `UserDetailsService` | Không tìm thấy user | Thường bị che thành BadCredentials khi đi qua Dao provider mặc định |
| `LockedException` | Kiểm tra trạng thái account | Account bị khóa | Thường 401 hoặc failure handler |
| `DisabledException` | Kiểm tra trạng thái account | Account bị disabled | Thường 401 hoặc failure handler |
| `AccountExpiredException` | Kiểm tra trạng thái account | Account hết hạn | Thường 401 hoặc failure handler |
| `CredentialsExpiredException` | Kiểm tra credentials | Password/credential hết hạn | Thường 401 hoặc flow đổi password |
| `InternalAuthenticationServiceException` | Provider/UserDetailsService | Bất thường từ hệ thống xác thực phía sau | Tùy handler; cần báo động backend, không diễn giải thành nhập sai |
| `AccessDeniedException` | Authorization | Đã xác thực nhưng thiếu quyền | 403 thông thường |
| Không có authentication | AuthenticationEntryPoint | Route yêu cầu caller đã xác thực | 401 hoặc redirect login tùy flow |

**HTTP status không duy nhất quyết định loại Java exception**. Basic, form login, custom failure handler, API gateway, method security và error handler có thể thay đổi status và body. Cần phân tích request, loại filter, exception root cause an toàn và `SecurityFilterChain` áp dụng.

## 8. Dự án chạy được: Spring Boot 3.3.5 + Java 17 + Servlet Security

Ta xây dựng một ứng dụng nhỏ có:

1. `GET /public/ping` công khai.
2. `GET /api/profile` yêu cầu `ROLE_READER`.
3. In-memory users có trạng thái active, locked, disabled, expired account và expired credentials.
4. HTTP Basic cho bài thực hành; **chỉ dành cho loopback**, password demo dạng `{noop}`.
5. Test MockMvc cho status và test trực tiếp `ProviderManager`/DAO provider để nhận biết **đúng loại exception**.

### 8.1. Cấu trúc project

```text
auth-exception-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/authdiag/
    │   │   ├── AuthDiagApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── ProfileController.java
    │   └── resources/application.yml
    └── test/
        └── java/demo/authdiag/
            ├── AuthenticationHttpTest.java
            └── AuthenticationExceptionTest.java
```

Tạo `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Tạo `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080
```

Ứng dụng chỉ lắng nghe loopback; không đưa tài khoản thử nghiệm hoặc HTTP Basic không TLS ra Internet. Cần một Gradle wrapper tương thích Java 17 trong thư mục project; nếu có `./gradlew` thì dùng wrapper, còn không phải cài Gradle và tạo wrapper trước.

### 8.2. Java main class

Tạo `src/main/java/demo/authdiag/AuthDiagApplication.java`:

```java
package demo.authdiag;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthDiagApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthDiagApplication.class, args);
    }
}
```

### 8.3. UserDetailsService và SecurityFilterChain

Tạo `src/main/java/demo/authdiag/SecurityConfig.java`:

```java
package demo.authdiag;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    UserDetailsService demoUsers() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password("{noop}demo-only")
                        .roles("READER")
                        .build(),
                User.withUsername("locked")
                        .password("{noop}demo-only")
                        .roles("READER")
                        .accountLocked(true)
                        .build(),
                User.withUsername("disabled")
                        .password("{noop}demo-only")
                        .roles("READER")
                        .disabled(true)
                        .build(),
                User.withUsername("expired")
                        .password("{noop}demo-only")
                        .roles("READER")
                        .accountExpired(true)
                        .build(),
                User.withUsername("old-password")
                        .password("{noop}demo-only")
                        .roles("READER")
                        .credentialsExpired(true)
                        .build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/ping").permitAll()
                        .requestMatchers("/api/profile").hasRole("READER")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

`UserDetails` trong demo cho phép tái hiện bốn trạng thái tài khoản. `.roles("READER")` tạo authority `ROLE_READER`; đây là **authorization**, tách biệt với credential và account status.

`{noop}` cho phép so sánh plaintext trong bài học, **không lưu plaintext password ở production**. Ứng dụng thực phải dùng password hash như BCrypt/Argon2 cùng `PasswordEncoder` được quản lý, credential rotation, rate limiting, audit và các chính sách user lifecycle phù hợp.

Nếu Spring Boot có nhiều `SecurityFilterChain`, một request có thể đi vào chain khác dự kiến. Chỉ nhìn thấy bean `UserDetailsService` không đủ để kết luận mọi chain đều dùng provider đó; cần kiểm tra `AuthenticationManager` trong chain thực tế.

### 8.4. Controller

Tạo `src/main/java/demo/authdiag/ProfileController.java`:

```java
package demo.authdiag;

import java.security.Principal;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/public/ping")
    public Map<String, String> ping() {
        return Map.of("status", "ok");
    }

    @GetMapping("/api/profile")
    public Map<String, String> profile(Principal principal) {
        return Map.of("name", principal.getName());
    }
}
```

Không trả password, authorities chi tiết hoặc raw authentication token. Khi Basic auth không thành công, request không được vào `/api/profile`; filter/entry point phản hồi theo chính sách HTTP.

## 9. Chạy thử HTTP và đọc status

Khởi chạy project:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Gọi public endpoint:

```bash
curl -i http://127.0.0.1:8080/public/ping
```

Với server chạy đúng, body JSON tương đương:

```json
{"status":"ok"}
```

User active đăng nhập thành công:

```bash
curl -i -u alice:demo-only \
  http://127.0.0.1:8080/api/profile
```

Body JSON thành công:

```json
{"name":"alice"}
```

Sai password:

```bash
curl -i -u alice:wrong \
  http://127.0.0.1:8080/api/profile
```

HTTP Basic thông thường trả `401 Unauthorized` với `WWW-Authenticate: Basic ...`. Tài khoản không tồn tại, disabled/locked/expired trong ví dụ cũng thường nhận 401 ở HTTP boundary. **Không trông chờ mỗi account-status có một HTTP code khác nhau** — đó có thể là lỗ hổng account enumeration.

Kiểm thử user đã disabled:

```bash
curl -i -u disabled:demo-only \
  http://127.0.0.1:8080/api/profile
```

Trong demo user không được vào controller. Để xác định lỗi Java cụ thể là `DisabledException` thay vì `BadCredentialsException`, cần **test trực tiếp `AuthenticationManager`/provider** ở phần tiếp theo.

Các lệnh `curl -u` có thể làm lộ credential trong lịch sử shell/process listing ở một số môi trường. Chúng chỉ là ví dụ local; trong CI hoặc production dùng secret management và phương pháp gửi credential an toàn, không ghi ra transcript công khai.

## 10. MockMvc: xác nhận authentication failure ở HTTP boundary

Tạo `src/test/java/demo/authdiag/AuthenticationHttpTest.java`:

```java
package demo.authdiag;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthenticationHttpTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointNeedsNoCredentials() throws Exception {
        mvc.perform(get("/public/ping"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void validCredentialsReachController() throws Exception {
        mvc.perform(get("/api/profile")
                        .with(httpBasic("alice", "demo-only")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("alice"));
    }

    @Test
    void wrongPasswordIsUnauthorized() throws Exception {
        mvc.perform(get("/api/profile")
                        .with(httpBasic("alice", "wrong")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void unknownUserIsUnauthorized() throws Exception {
        mvc.perform(get("/api/profile")
                        .with(httpBasic("ghost", "demo-only")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void disabledUserIsUnauthorized() throws Exception {
        mvc.perform(get("/api/profile")
                        .with(httpBasic("disabled", "demo-only")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void lockedUserIsUnauthorized() throws Exception {
        mvc.perform(get("/api/profile")
                        .with(httpBasic("locked", "demo-only")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void expiredAccountIsUnauthorized() throws Exception {
        mvc.perform(get("/api/profile")
                        .with(httpBasic("expired", "demo-only")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void expiredCredentialsAreUnauthorized() throws Exception {
        mvc.perform(get("/api/profile")
                        .with(httpBasic("old-password", "demo-only")))
                .andExpect(status().isUnauthorized());
    }
}
```

Chạy:

```bash
./gradlew test
```

Bộ test xác nhận **hợp đồng HTTP**, không khẳng định exception Java bên trong. `@AutoConfigureMockMvc` dùng Spring application context để chạy Spring Security filter chain; `httpBasic(...)` tạo header Basic thật cho filter, **khác** `.with(user("alice"))` vốn gắn sẵn danh tính và không kiểm password.

Nếu thay `httpBasic(...)` bằng `user(...)`, test sẽ không còn bảo đảm đã đi qua password check, nên có thể sai mục tiêu chẩn đoán.

## 11. Unit test trực tiếp: phân biệt chính xác từng exception

Test HTTP trả 401 thường không cho biết cause. Để kiểm tra đúng Java class, dựng `DaoAuthenticationProvider` với `UserDetailsService` fixture và gọi `ProviderManager.authenticate(...)` trực tiếp.

Tạo `src/test/java/demo/authdiag/AuthenticationExceptionTest.java`:

```java
package demo.authdiag;

import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.AnonymousAuthenticationProvider;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.ProviderNotFoundException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.authentication.AccountExpiredException;
import org.springframework.security.authentication.CredentialsExpiredException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest
class AuthenticationExceptionTest {

    @Autowired
    UserDetailsService userDetailsService;

    private AuthenticationManager daoManager;

    @BeforeEach
    void setup() {
        DaoAuthenticationProvider dao = new DaoAuthenticationProvider();
        dao.setUserDetailsService(userDetailsService);
        dao.setPasswordEncoder(
                PasswordEncoderFactories.createDelegatingPasswordEncoder());
        daoManager = new ProviderManager(List.of(dao));
    }

    private static UsernamePasswordAuthenticationToken credentials(
            String user, String password) {
        return UsernamePasswordAuthenticationToken.unauthenticated(
                user, password);
    }

    @Test
    void wrongPasswordYieldsBadCredentials() {
        assertThatThrownBy(() ->
                daoManager.authenticate(credentials("alice", "wrong")))
                .isInstanceOf(BadCredentialsException.class);
    }

    @Test
    void missingUserIsMaskedAsBadCredentialsByDefault() {
        assertThatThrownBy(() ->
                daoManager.authenticate(credentials("ghost", "demo-only")))
                .isInstanceOf(BadCredentialsException.class);
    }

    @Test
    void lockedAccountYieldsLockedException() {
        assertThatThrownBy(() ->
                daoManager.authenticate(credentials("locked", "demo-only")))
                .isInstanceOf(LockedException.class);
    }

    @Test
    void disabledAccountYieldsDisabledException() {
        assertThatThrownBy(() ->
                daoManager.authenticate(credentials("disabled", "demo-only")))
                .isInstanceOf(DisabledException.class);
    }

    @Test
    void expiredAccountYieldsAccountExpiredException() {
        assertThatThrownBy(() ->
                daoManager.authenticate(credentials("expired", "demo-only")))
                .isInstanceOf(AccountExpiredException.class);
    }

    @Test
    void expiredPasswordYieldsCredentialsExpiredException() {
        assertThatThrownBy(() ->
                daoManager.authenticate(credentials(
                        "old-password", "demo-only")))
                .isInstanceOf(CredentialsExpiredException.class);
    }

    @Test
    void managerWithoutProviderForUsernamePasswordYieldsProviderNotFound() {
        AuthenticationManager wrongManager =
                new ProviderManager(List.of(
                        new AnonymousAuthenticationProvider("test-key")));

        assertThatThrownBy(() ->
                wrongManager.authenticate(credentials("alice", "demo-only")))
                .isInstanceOf(ProviderNotFoundException.class);
    }
}
```

**Điểm QA đáng lưu ý:**

- `AnonymousAuthenticationProvider` không được thiết kế để hỗ trợ `UsernamePasswordAuthenticationToken`. Vì vậy test `wrongManager` cố ý minh họa **provider mismatch**, không ảnh hưởng SecurityFilterChain của app.
- `DaoAuthenticationProvider` được tạo **riêng trong test** để xác định chính xác exception; test không giả định HTTP response phải chứa tên exception.
- `createDelegatingPasswordEncoder()` hỗ trợ prefix như `{noop}` trong dữ liệu demo. Trong production phải dùng hashing có sức chống tấn công phù hợp; giữ `{noop}` chỉ cho project học tập.
- Một password không đúng với user **còn active** mới là trường hợp điển hình của `BadCredentialsException`; với user locked/disabled, provider có thể dừng trước khi kiểm password.
- Test `ghost` kiểm tra default **ẩn `UsernameNotFoundException`**; việc bật tùy chọn không ẩn user thường không phù hợp cho hệ thống công khai.

**Lưu ý phiên bản:** đoạn `new DaoAuthenticationProvider()` và setter `setUserDetailsService(...)` áp dụng cho dòng Spring Security 6.x tương ứng với Spring Boot 3.3.5; một số API có thể deprecated trong phiên bản mới hơn. Khi nâng cấp Spring Security, dùng constructor/kiểu config được phiên bản đó hỗ trợ và chạy lại test; không ép code deprecated sang framework mới nếu không còn tương thích.

Bộ test này có thể chứng minh nguyên nhân logic ở **DAO provider**, nhưng không kiểm chứng LDAP/OIDC/JWT hay database thật. Khi kiểm tra provider custom, phải test đúng `supports(...)` và exception contract của provider đó.

## 12. `ProviderManager` có nhiều provider và parent manager

Một cấu hình có thể có nhiều providers:

```text
ProviderManager
  |
  +-- Provider A (supports UsernamePasswordAuthenticationToken)
  |     -> trả null hoặc ném AuthenticationException
  |
  +-- Provider B (supports UsernamePasswordAuthenticationToken)
  |     -> thành công hoặc lỗi
  |
  +-- Parent AuthenticationManager (nếu có)
        -> thử xác thực theo policy riêng
```

Một số nguyên tắc:

1. Provider A trả `null` thì Provider B có thể xử lý tiếp.
2. Provider A ném `BadCredentialsException` có thể chưa phải kết quả cuối nếu Provider B hoặc parent manager xử lý thành công theo hợp đồng.
3. `AccountStatusException` và `InternalAuthenticationServiceException` thường làm ProviderManager dừng sớm vì không nên thử provider khác để bỏ qua account policy hoặc lỗi auth backend.
4. Nếu không provider nào xử lý và parent không giải quyết, manager có thể ném `ProviderNotFoundException`. Nếu có một exception xác thực khác được lưu lại, manager có thể ném exception đó.
5. Provider `supports(...)` rộng quá mức có thể lấy nhầm token không thuộc trách nhiệm của nó; `supports(...)` quá hẹp khiến token đúng loại bị bỏ qua.
6. Nếu nhiều `SecurityFilterChain`, mỗi chain có thể tham chiếu manager riêng. Thêm provider ở một bean không bảo đảm filter ở chain khác dùng nó.

**Không** chữa provider mismatch bằng cách thêm một `AuthenticationProvider` luôn trả token `authenticated=true` cho mọi request. Đó là lỗ hổng nghiêm trọng, nhất là khi provider nằm trước nơi kiểm mật khẩu.

## 13. Exception translation: 401, 403 và form login

Trong Spring Security Servlet, exception có thể được xử lý tại filter authentication (ví dụ Basic filter hoặc form-login filter) hoặc ở `ExceptionTranslationFilter` trong đường authorization.

### Authentication failure

Khi credentials không đúng, tài khoản bị disabled/locked hoặc provider không nhận token, request thường không được đến controller. `AuthenticationEntryPoint` hoặc authentication failure handler quyết định response.

**HTTP Basic**:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
```

Header và realm thực tế tùy cấu hình. Body có thể rỗng hoặc là thông báo mặc định; không coi response body đó là nơi phải ghi loại Java exception.

**Form login**: thất bại có thể redirect về trang login với error indicator. Một `302` trong flow này **không** đồng nghĩa auth thành công; phải kiểm tra session, destination và event.

### Authorization failure

Nếu user đã được xác thực nhưng thiếu quyền:

```java
.requestMatchers("/api/admin/**").hasRole("ADMIN")
```

một `alice` có `ROLE_READER` truy cập `/api/admin/report` sẽ thường nhận **403 Forbidden**. Đây không phải lỗi mật khẩu.

Một số cấu hình biểu diễn anonymous token như một authentication object đã được đánh dấu authenticated ở cấp implementation, nhưng authorization vẫn phải nhận diện anonymous qua trust resolver. Vì vậy không tự suy ra caller đã login chỉ từ `Authentication.isAuthenticated()`.

### Một quy tắc giao diện đáng dùng

HTTP response công khai nên cho thông tin vừa đủ để client biết nên đăng nhập lại, đổi mật khẩu qua flow phù hợp, hay báo hỗ trợ. **Chi tiết khóa tài khoản, user tồn tại, provider name hoặc stack trace nên ở kênh audit/monitor nội bộ** với quyền truy cập hạn chế, không phải response tự do.

## 14. Chẩn đoán `ProviderNotFoundException` có phương pháp

Khi log phát sinh `ProviderNotFoundException`, kiểm theo thứ tự:

1. **Loại token đầu vào**: ví dụ `UsernamePasswordAuthenticationToken`, `BearerTokenAuthenticationToken`, `PreAuthenticatedAuthenticationToken`, OAuth2 login token; không dùng giá trị `credentials`.
2. **Bộ lọc tạo token**: Basic, form login, bearer, custom filter… Chắc chắn request đi qua filter mong đợi.
3. **`SecurityFilterChain` áp dụng**: kiểm `securityMatcher(...)` và thứ tự chains. Một request có thể match chain đầu tiên rồi bỏ qua chain bạn đang xem.
4. **AuthenticationManager mà filter gọi**: phân biệt manager bean global, manager từ `HttpSecurity`, manager resolver theo request và parent manager.
5. **Danh sách provider trong manager đó**: loại provider nào, class token nào được `supports(...)` xử lý.
6. **Custom provider implementation**: `supports` có nhận subclasses đúng yêu cầu; `authenticate` trả `null` hợp lý hay ném exception?
7. **Wiring context**: bean có được Spring quản lý và đăng ký vào đúng manager chưa?
8. **Negative tests**: tạo token type không hỗ trợ để xác minh lỗi, rồi thêm provider đúng loại và test thành công.

Trong production, log nội bộ có thể ghi **token class name**, tên filter/chain đã chuẩn hóa, correlation ID và nhóm lỗi; không log `Authentication#getCredentials()` hoặc nguyên bearer token/Authorization header.

Nếu dùng `@Bean AuthenticationManager`, hãy xem lại liệu nó có thay thế con đường tự cấu hình của Spring Boot/Security không. Khi tự tạo `ProviderManager`, trách nhiệm lắp provider hỗ trợ đúng token thuộc về bạn.

## 15. Chẩn đoán `BadCredentialsException` và password encoder

Khi user báo "mật khẩu đúng nhưng API vẫn 401", không vội đổi encoder. Cần:

1. Kiểm tra request gửi qua endpoint/chain nào, Basic hay form login, và client có thực sự gửi credential không.
2. Kiểm tra `UsernamePasswordAuthenticationToken` mang username như mong đợi (trim/case normalization theo contract, không tự thay đổi secret).
3. Kiểm tra `UserDetailsService` kết nối đúng nguồn user và trạng thái user.
4. Kiểm tra password hash storage, prefix (`{bcrypt}`, `{noop}` trong test), algorithm và `PasswordEncoder` đã cấu hình.
5. Kiểm tra provider thực hiện password compare bằng `matches(raw, encoded)`; không so hash bằng so sánh chuỗi hoặc tự hash thêm nhiều lần.
6. Kiểm tra dữ liệu đã migrate từ thuật toán cũ hoặc prefix bị thiếu; lên kế hoạch migration an toàn.
7. Kiểm tra chính sách account lock/disabled/expired và rate limiting có thể gây các lỗi khác.
8. Kiểm tra reverse proxy/gateway có bỏ/ghi đè Authorization header hoặc đổi route không.

**Không đưa password thô vào exception message hoặc log.** Cần xử lý sai credential ở kênh xác thực, không ghi lại như một phần audit payload. Nếu debug một dòng dữ liệu hash, chỉ dùng metadata không nhạy cảm như encoder ID hoặc hash format (đã cân nhắc), tránh copy full hash vào ticket công khai.

### Lỗi `There is no PasswordEncoder mapped for the id "null"`

Khi dùng `DelegatingPasswordEncoder` mà password stored không có prefix ID hợp lệ, bạn có thể gặp lỗi encoder mapping (thường biểu thị hash/encoder config không thống nhất). Đây là **lỗi cấu hình hoặc migration**, không nên phản hồi "sai mật khẩu" rồi bỏ qua việc sửa dữ liệu/encoder.

Mật khẩu `"demo-only"` chỉ dùng cho test vì có `{noop}` trong project demo. Với production phải tạo hash và lưu phù hợp, không “sửa nhanh” bằng cách gắn `{noop}` cho toàn bộ cơ sở dữ liệu.

## 16. Lỗi nguồn dữ liệu user và độ tin cậy của provider

`UserDetailsService.loadUserByUsername(...)` có thể lỗi vì:

- Database timeout hoặc không thể kết nối.
- LDAP/IdP không khả dụng.
- Mapping user record thành `UserDetails` bị sai.
- User store trả nhiều bản ghi không nhất quán.
- Transaction/connection pool quá tải.
- Cache user stale khiến trạng thái bị khóa/vô hiệu hóa chưa cập nhật.

`InternalAuthenticationServiceException` có thể được provider sử dụng để thể hiện sự cố nội bộ khi truy vấn user service. Đây **không phải** bằng chứng user nhập sai. Hệ thống vận hành nên phân biệt "credential mismatch" với "authentication backend unavailable" để cảnh báo đúng mức và không tự khóa thêm tài khoản vì outage.

Một số hệ thống có cơ chế retry ngắn hoặc failover cho backend, nhưng không retry vô hạn cùng một password/lockout attempt. Không bỏ qua account disabled/locked khi LDAP/DB tạm lỗi. Đặc biệt không mặc định cho phép đăng nhập khi provider chính mất kết nối (*fail-open*) nếu không có policy khôi phục được phê duyệt.

## 17. Mapping thông báo lỗi và chống account enumeration

### Public API / browser

Nên trả thông báo **không tiết lộ sự tồn tại của tài khoản**. Ví dụ:

```json
{
  "code": "AUTHENTICATION_FAILED",
  "message": "Không thể xác thực thông tin đăng nhập."
}
```

Với tài khoản cần reset mật khẩu, hãy điều hướng đến flow an toàn không yêu cầu API công khai xác nhận user có tồn tại. Ví dụ flow "Nếu tài khoản hợp lệ, hướng dẫn khôi phục sẽ được gửi" giúp giảm enumeration.

### Internal diagnostics

Có thể ghi:

```text
event=authentication_failed
correlation_id=req-7f3
mechanism=http_basic
category=account_locked
principal_hash=<pseudonymized-id>
```

Giá trị `principal_hash` ở đây chỉ là **nhãn minh họa**, không phải giá trị thật và không nên dùng hash username không salt với khả năng brute force cao. Có thể dùng internal user ID được quản trị hoặc pseudonymous ID có secret/key, theo chính sách bảo mật dữ liệu.

Nội bộ có thể phân biệt `bad_credentials`, `account_disabled`, `provider_unavailable`, `provider_mismatch` để đo vận hành, nhưng log phải có retention/access control và tránh credential leak. Nên kiểm soát cả exception stack trace vì custom code đôi khi đặt raw credentials vào exception message.

### Quan hệ với HTTP status

Không nên định nghĩa `423 Locked` cho mọi trường hợp tài khoản bị khóa nếu điều đó công khai account state. Nếu một sản phẩm có yêu cầu UX riêng cho user đã xác minh bằng yếu tố khác, cần thiết kế flow bảo mật riêng. Với HTTP Basic demo, trả generic 401 là dễ hiểu và hạn chế lộ thông tin.

## 18. Cách kiểm thử trong hệ thống thực

Ngoài những test chạy trên demo, một application thật nên có:

| Kịch bản | Tầng test | Kết quả cần chứng minh |
| --- | --- | --- |
| Token class không có provider | Unit `ProviderManager` | Ném `ProviderNotFoundException`, không authenticated |
| Password sai | Provider/manager unit | `BadCredentialsException` |
| Username không tồn tại | Provider unit | Không tiết lộ sự tồn tại trong exception public |
| Locked/disabled/expired | Provider unit | Đúng exception trạng thái |
| Basic auth sai | MockMvc filter integration | 401, không vào controller |
| User có quyền phù hợp | MockMvc | 200 và principal đúng |
| User authenticated thiếu role | MockMvc | 403 (nếu endpoint có role khác) |
| Sai JWT signature/issuer | Resource Server integration | Bị từ chối theo policy; không dùng Dao provider để kết luận |
| LDAP/DB down | Integration fault injection | Fail closed, metric/alert đúng loại |
| Nhiều SecurityFilterChains | Spring integration | Request match đúng chain/manager, không bypass |
| Account state thay đổi giữa các request | Integration | Quyền và authentication không bị stale quá policy |
| Header/credential rò trong log | Security test | Không log password, Authorization, bearer token |

### Sự khác biệt giữa ba loại test

**Authorization test** có thể dùng `.with(user("alice").roles("READER"))` để gắn sẵn `Authentication` và kiểm quy tắc quyền. Test này không xác minh password.

**Authentication test** nên gửi credentials qua filter thật, như `.with(httpBasic("alice", "wrong"))`, hoặc gọi trực tiếp `AuthenticationManager`/provider.

**End-to-end test** kiểm HTTP server/gateway, TLS, DB/LDAP/IdP và session/cookie thật. MockMvc không tự mô phỏng tất cả những thành phần ngoài JVM.

Tách những tầng này giúp một test “xanh” không che giấu lỗi wiring provider hoặc nguy cơ account enumeration.

## 19. Checklist xử lý sự cố

- Nhận diện route, HTTP method, filter chain và authentication mechanism của request.
- Xác nhận có hoặc không có `Authentication` đầu vào; token class gì, không in credentials.
- Tìm đúng `AuthenticationManager` mà filter/endpoint gọi, không tự suy từ bean gần tên.
- Xác minh ít nhất một provider tương thích với token; kiểm `supports()` và manager cha.
- Nếu đã có provider, phân biệt password mismatch, username hidden, locked/disabled/expired và backend outage.
- Xác minh `PasswordEncoder` và định dạng hash storage khớp; không bật `{noop}` để sửa nhanh production.
- Kiểm tra `401` là authentication failure; `403` thường là authorization/CSRF tùy flow.
- Không dùng `ProviderNotFoundException` làm tín hiệu user sai mật khẩu hoặc tự thêm provider luôn authenticated.
- HTTP response công khai không lộ user existence, trạng thái lock, provider details hoặc stack trace.
- Có negative tests cho user không tồn tại, password sai, bốn trạng thái account, provider mismatch và backend outage.
- Theo dõi metrics/log audit có phân loại nội bộ, correlation ID, không chứa password/token.
- Khi đổi hoặc nâng cấp Spring Security, chạy lại test wiring AuthenticationManager/Provider và matcher của nhiều filter chain.

## Ghi nhớ

`ProviderNotFoundException` nói rằng **chuỗi `AuthenticationManager`/`AuthenticationProvider` không xử lý được token đúng cách**; đây chủ yếu là vấn đề lựa chọn/wiring provider. `BadCredentialsException` nói rằng **credential không được chấp nhận**, có thể bao gồm việc che giấu user không tồn tại. `LockedException`, `DisabledException`, `AccountExpiredException` và `CredentialsExpiredException` là **chính sách trạng thái tài khoản**. Tất cả phải được phân biệt với **authorization denied** sau khi đã xác thực. Hãy chẩn đoán nguyên nhân nội bộ bằng test/provider/log an toàn, đồng thời giữ HTTP error messages đủ chung để không tiết lộ danh tính hoặc trạng thái tài khoản cho attacker.