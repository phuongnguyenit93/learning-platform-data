# RequestPostProcessor: `user`, `anonymous`, `authentication` và `securityContext`

## 1. Tại sao cần `RequestPostProcessor` khi kiểm thử HTTP?

Trong **Spring Security Servlet**, một HTTP request đến controller thường phải đi qua `SecurityFilterChain`: bộ lọc khôi phục hoặc xây dựng `SecurityContext`, xác thực người gọi, rồi kiểm tra quyền trước khi cho request vào `DispatcherServlet`. Khi viết test bằng **Spring MVC MockMvc**, chúng ta muốn mô phỏng chính xác nhiều tình huống: người dùng có vai trò nhất định, người dùng ẩn danh, một `Authentication` tùy biến hoặc một `SecurityContext` đã chuẩn bị sẵn.

Spring Security Test cung cấp các **`RequestPostProcessor`** để thay đổi `MockHttpServletRequest` trước khi MockMvc thực thi, đặc biệt các method tĩnh của `SecurityMockMvcRequestPostProcessors`:

```java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.anonymous;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.securityContext;
```

Các lệnh import ở đây nằm trong Java test. Chúng không phải controller hoặc chương trình có `main` độc lập.

Ví dụ ngắn:

```java
mockMvc.perform(get("/api/reports")
        .with(user("alice").roles("READER")))
    .andExpect(status().isOk());
```

**Điểm quan trọng:** `user(...)` và `authentication(...)` thường **đặt sẵn trạng thái đã xác thực cho request kiểm thử**. Chúng **không** gọi `AuthenticationManager` để kiểm mật khẩu, không truy vấn database user và không xác minh chữ ký JWT. Muốn test một cơ chế đăng nhập/xác thực thật, phải thực hiện luồng HTTP tương ứng (ví dụ `httpBasic`, login form hoặc bearer token đi qua `JwtDecoder`) và cấu hình filter chain thực tế.

## 2. `RequestPostProcessor` là cơ chế gì?

`RequestPostProcessor` thuộc Spring Test, có contract khái niệm:

```java
MockHttpServletRequest postProcessRequest(MockHttpServletRequest request);
```

Nó nhận request giả lập do MockMvc tạo, điều chỉnh request và trả request để pipeline test tiếp tục. Spring Security Test cung cấp các processor chuyên dụng cho danh tính, header, credential, CSRF và nhiều tình huống khác.

Có ba tầng cần phân biệt:

1. **Tạo request:** `MockMvcRequestBuilders.get("/...")`, `post("/...")` và dữ liệu body/header.
2. **Tiền xử lý request:** `.with(user(...))`, `.with(anonymous())`, `.with(authentication(...))`, `.with(securityContext(...))`.
3. **Chạy pipeline:** filter chain được tích hợp với MockMvc, sau đó handler/controller và result matchers kiểm tra status/body/redirect.

Luồng mô phỏng:

```text
MockMvc.perform(...)
    |
    +-- MockHttpServletRequest
    |      |
    |      +-- RequestPostProcessor
    |             user / anonymous /
    |             authentication / securityContext
    |
    v
Spring Security FilterChain
    |
    +-- SecurityContext được dùng cho request
    +-- AuthorizationFilter kiểm tra quyền
    |
    v
DispatcherServlet / Controller
    |
    v
MockMvc ResultMatchers: 200 / 401 / 403 / body / ...
```

Nếu MockMvc **không** được tích hợp Spring Security đúng cách, processor có thể không tạo ra kết quả như mong đợi: test controller có thể đi qua mà không thực sự kiểm tra URL authorization. Với Boot, `@SpringBootTest` + `@AutoConfigureMockMvc` thường auto-configure security filters; với MockMvc tự tạo, dùng `springSecurity()` configurer như phần sau.

## 3. `user(...)`: gắn principal và authorities giả lập

Dùng `user(String username)` khi bạn cần một request được xem như đến từ user đã xác thực. Ví dụ:

```java
mockMvc.perform(get("/api/reports")
        .with(user("alice").roles("READER")))
    .andExpect(status().isOk());
```

Với `.roles("READER")`, Spring Security Test tạo authority **`ROLE_READER`**. Vì thế cấu hình sau có thể cho phép:

```java
.requestMatchers("/api/reports").hasRole("READER")
```

`hasRole("READER")` thông thường tìm authority `ROLE_READER`, không phải chuỗi `READER`.

Một số biến thể:

```java
// Mặc định nếu chỉ truyền username, user được gắn ROLE_USER.
.with(user("alice"))

// Gắn một hay nhiều role; prefix ROLE_ do roles(...) thêm.
.with(user("alice").roles("READER", "EDITOR"))

// Tự gắn authorities với tên chính xác, không tự thêm ROLE_.
.with(user("alice").authorities(
        new SimpleGrantedAuthority("REPORT_EXPORT")))

// Sử dụng một UserDetails do test tự tạo.
.with(user(testUserDetails))
```

Các dòng trên là **các biểu thức fragment**, đặt bên trong `mockMvc.perform(...)` với import `SimpleGrantedAuthority` và biến `testUserDetails` đã được tạo. Không kết hợp `.roles(...)` rồi `.authorities(...)` mà không xét thao tác cuối cùng làm thay đổi danh sách quyền ra sao; thông thường chọn một contract authority rõ ràng.

**Không hiểu `user("alice")` là “tìm alice trong `UserDetailsService`”**. Nếu `alice` không tồn tại trong database/in-memory store, processor này vẫn có thể dựng principal cho test. Đây là ưu điểm cho **authorization unit/integration tests**, nhưng không chứng minh password, account lock, MFA hoặc provider xác thực đang hoạt động.

## 4. `anonymous()`: kiểm thử người gọi chưa đăng nhập

`anonymous()` tạo tình huống anonymous authentication trong request MockMvc:

```java
mockMvc.perform(get("/api/reports")
        .with(anonymous()))
    .andExpect(status().isUnauthorized());
```

Trong cấu hình mẫu sử dụng HTTP Basic và endpoint cần authentication, `401 Unauthorized` là kỳ vọng phù hợp. Tuy nhiên **status phụ thuộc `AuthenticationEntryPoint`**: ứng dụng form login có thể redirect đến trang đăng nhập thay vì trả 401; một error handler tự viết có thể phản hồi khác.

Anonymous authentication thường có principal như `"anonymousUser"` và authority như `ROLE_ANONYMOUS`. Đừng nhìn duy nhất `Authentication#isAuthenticated()` để suy ra người gọi là user đăng nhập: một `AnonymousAuthenticationToken` có thể báo true theo contract token, nhưng `AuthenticationTrustResolver` và các rule như `.authenticated()` vẫn xem anonymous là chưa xác thực đối với authorization.

`anonymous()` đặc biệt hữu ích để:

- Bảo đảm route riêng tư không lộ nội dung cho người chưa đăng nhập.
- Tạo override cho test đang dùng mặc định `@WithMockUser` hoặc `defaultRequest(user(...))`.
- Kiểm tra public endpoint thật sự cho anonymous truy cập được.
- Kiểm tra controller không nhận `Authentication` của một request trước đó trong cùng test suite.

Phân biệt **anonymous** với **không gửi Authorization header**: hai tình huống thường dẫn tới cùng việc từ chối, nhưng không nhất thiết hoàn toàn đồng nhất khi ứng dụng có custom filters, session, cookie hoặc security context.

## 5. `authentication(...)`: đưa một `Authentication` đã dựng sẵn vào request

`authentication(Authentication)` dùng khi muốn kiểm thử đối tượng xác thực tùy biến, chi tiết principal/credentials, loại token hoặc danh sách authority mà DSL `user(...)` không biểu diễn hết.

Ví dụ dùng `UsernamePasswordAuthenticationToken` đã được đánh dấu authenticated:

```java
Authentication auth = UsernamePasswordAuthenticationToken.authenticated(
        "carol",
        "not-used-in-this-test",
        List.of(new SimpleGrantedAuthority("AUDIT_READ")));

mockMvc.perform(get("/api/audit")
        .with(authentication(auth)))
    .andExpect(status().isOk());
```

Đoạn code này giả định import:

```java
import java.util.List;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
```

`authentication(auth)` không đưa `"not-used-in-this-test"` đến user store để xác thực. Nó **sử dụng chính `Authentication` mà test truyền vào**. Hãy chủ động chọn trạng thái `isAuthenticated`, principal và authorities để không vô tình khiến test “xanh” bằng một token giả có quyền quá lớn.

Tình huống nên dùng:

1. `Authentication` không phải username/password, ví dụ loại authentication có extra details.
2. Principal là đối tượng domain hoặc `UserDetails` tùy chỉnh.
3. Cần kiểm tra service/controller xử lý `Authentication#getName()` và authorities theo contract cụ thể.
4. Kiểm thử authorization cho một tập `GrantedAuthority` không theo convention `ROLE_`.

Nếu mục tiêu là **kiểm thử Resource Server JWT thực sự**, việc gắn sẵn `JwtAuthenticationToken` bằng `authentication(...)` **bỏ qua decode và verify chữ ký**; phải có test khác đi qua `BearerTokenAuthenticationFilter`/`JwtDecoder`.

## 6. `securityContext(...)`: kiểm thử với cả `SecurityContext`

`securityContext(SecurityContext)` nhận một context được tạo sẵn, thường là:

```java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(
        UsernamePasswordAuthenticationToken.authenticated(
                "dave",
                "unused",
                List.of(new SimpleGrantedAuthority("ROLE_READER"))));

mockMvc.perform(get("/api/reports")
        .with(securityContext(context)))
    .andExpect(status().isOk());
```

Các import tương ứng:

```java
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
```

Sự khác biệt thực tế:

- `authentication(...)`: gắn **một đối tượng `Authentication`** để Spring Security Test tạo/dùng context cần thiết.
- `securityContext(...)`: truyền **cả `SecurityContext`**, phù hợp khi muốn tự chuẩn bị context có authentication cụ thể hoặc dùng một implementation context riêng.
- `user(...)`: cách thuận tiện nhất khi chỉ cần user, roles, authorities, username.
- `anonymous()`: cách thuận tiện nhất để chỉ định request anonymous một cách rõ ràng.

**Không dùng** `SecurityContextHolder.getContext().setAuthentication(...)` ngay trong test thread rồi mặc định kết quả sẽ đi vào mọi MockMvc request. Hãy dùng request processor hoặc test annotations phù hợp để scope đúng request. Việc Spring Security Test cài đặt context cần filter chain/test context integration; tự set `ThreadLocal` sai chỗ dễ tạo test phụ thuộc thứ tự chạy.

## 7. Bảng lựa chọn nhanh

| Mục đích | Processor | Điều đang được giả lập |
| --- | --- | --- |
| User đã xác thực với role đơn giản | `user("alice").roles("READER")` | UserDetails + `ROLE_READER` |
| User có authority không theo `ROLE_` | `user("alice").authorities(...)` | Chính xác các `GrantedAuthority` |
| Request được xem là anonymous | `anonymous()` | Anonymous authentication |
| Authentication tùy biến | `authentication(auth)` | Chính đối tượng `Authentication` đã tạo |
| Context tùy chỉnh | `securityContext(ctx)` | `SecurityContext` do test cung cấp |
| Test HTTP Basic thật | `httpBasic("alice", "password")` | HTTP Authorization header để Basic filter xử lý |
| Test session/form login thật | `formLogin()` hoặc request login hợp lệ | Luồng authentication đi qua filter/provider |
| Test CSRF | `csrf()` | CSRF token cho request có thể thay đổi trạng thái |

**Cảnh báo:** `user`, `authentication` và `securityContext` chủ yếu hữu ích để test **authorization** và **cách controller/service sử dụng danh tính**. Chúng không thay thế test của `AuthenticationProvider`, JWT decoder, password encoder, MFA, cookie/session fixation hoặc OIDC login.

## 8. Spring Boot 3.3.x + Java 17: ứng dụng demo chạy được

Ví dụ dưới dùng **Spring MVC Servlet** và `spring-security-test`. Ta tạo một API nhỏ với ba endpoint:

- `GET /public/ping`: công khai.
- `GET /api/reports`: yêu cầu role `READER`.
- `GET /api/audit`: yêu cầu authority `AUDIT_READ`.

Các processor được kiểm tra bằng MockMvc, còn `httpBasic(...)` được dùng đối chiếu để thấy khác biệt giữa **gắn principal giả lập** và **xác thực thật qua HTTP filter**.

### 8.1. Cấu trúc project

```text
mockmvc-security-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/mocksec/
    │   │   ├── DemoApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── ExampleController.java
    │   └── resources/application.yml
    └── test/java/demo/mocksec/RequestPostProcessorTest.java
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

Dùng loopback để demo HTTP Basic trên máy cá nhân. Trong mạng thật, HTTP Basic truyền credential dạng Base64, **không phải mã hóa**; phải dùng HTTPS và các cơ chế authentication phù hợp với sản phẩm.

### 8.2. Lớp khởi động

Tạo `src/main/java/demo/mocksec/DemoApplication.java`:

```java
package demo.mocksec;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 8.3. SecurityFilterChain và user store

Tạo `src/main/java/demo/mocksec/SecurityConfig.java`:

```java
package demo.mocksec;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
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
                        .build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/ping").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/reports")
                                .hasRole("READER")
                        .requestMatchers(HttpMethod.GET, "/api/audit")
                                .hasAuthority("AUDIT_READ")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

Quy tắc:

- `/public/ping` không cần đăng nhập.
- `/api/reports` cần `ROLE_READER`.
- `/api/audit` cần authority chính xác `AUDIT_READ`.
- Route khác mặc định từ chối.
- User `alice` có trong in-memory user store với mật khẩu demo; không có user `phantom`, `carol` hoặc `dave`.

`{noop}` là định dạng minh họa cho mật khẩu không hash, **không dùng ở production**. Đây là cấu hình demo để thấy HTTP Basic thực sự kiểm user store; không phải thiết kế lưu mật khẩu thực tế.

### 8.4. Controller trả kết quả tối giản

Tạo `src/main/java/demo/mocksec/ExampleController.java`:

```java
package demo.mocksec;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ExampleController {

    @GetMapping("/public/ping")
    public Map<String, String> ping() {
        return Map.of("message", "pong");
    }

    @GetMapping("/api/reports")
    public Map<String, Object> reports(Authentication authentication) {
        return Map.of(
                "name", authentication.getName(),
                "canReadReports", true);
    }

    @GetMapping("/api/audit")
    public Map<String, Object> audit(Authentication authentication) {
        return Map.of(
                "name", authentication.getName(),
                "canReadAudit", true);
    }
}
```

Controller chỉ chạy sau các rule trong SecurityFilterChain. Trong test, khi một processor cung cấp principal hợp lệ theo rule, response phản ánh `Authentication#getName()` mà Spring MVC nhận được. Không trả credential hoặc toàn bộ security context về client.

## 9. Bộ test chạy được: cả bốn RequestPostProcessor

Tạo `src/test/java/demo/mocksec/RequestPostProcessorTest.java`:

```java
package demo.mocksec;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.anonymous;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.securityContext;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RequestPostProcessorTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void userWithReaderRoleCanReadReport() throws Exception {
        mvc.perform(get("/api/reports")
                        .with(user("alice").roles("READER")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("alice"))
                .andExpect(jsonPath("$.canReadReports").value(true));
    }

    @Test
    void fakeUserCanReadViaPostProcessorEvenWhenAbsentFromStore()
            throws Exception {
        mvc.perform(get("/api/reports")
                        .with(user("phantom").roles("READER")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("phantom"));
    }

    @Test
    void anonymousCallerCannotReadPrivateReport() throws Exception {
        mvc.perform(get("/api/reports").with(anonymous()))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void userWithoutReaderRoleIsForbidden() throws Exception {
        mvc.perform(get("/api/reports")
                        .with(user("mallory").roles("VIEWER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void customAuthenticationCanCarrySpecificAuthority()
            throws Exception {
        Authentication auth =
                UsernamePasswordAuthenticationToken.authenticated(
                        "carol",
                        "unused",
                        List.of(new SimpleGrantedAuthority("AUDIT_READ")));

        mvc.perform(get("/api/audit").with(authentication(auth)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("carol"))
                .andExpect(jsonPath("$.canReadAudit").value(true));
    }

    @Test
    void fullSecurityContextCanBeSuppliedForOneRequest()
            throws Exception {
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(
                UsernamePasswordAuthenticationToken.authenticated(
                        "dave",
                        "unused",
                        List.of(
                                new SimpleGrantedAuthority("ROLE_READER"))));

        mvc.perform(get("/api/reports").with(securityContext(context)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("dave"));
    }

    @Test
    void realHttpBasicChecksPasswordAndConfiguredUserStore()
            throws Exception {
        mvc.perform(get("/api/reports")
                        .with(httpBasic("alice", "demo-only")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("alice"));

        mvc.perform(get("/api/reports")
                        .with(httpBasic("alice", "wrong")))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/reports")
                        .with(httpBasic("phantom", "anything")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void publicEndpointWorksForAnonymous() throws Exception {
        mvc.perform(get("/public/ping").with(anonymous()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("pong"));
    }
}
```

Chạy bộ test:

```bash
./gradlew test
```

Trên Windows:

```powershell
.\gradlew.bat test
```

Kỳ vọng các test thành công khi Gradle wrapper, JDK 17 và dependencies tương thích được cài. Dòng log của Gradle tùy phiên bản/môi trường, nên không khẳng định một stdout cụ thể. Kết quả đáng kiểm tra là **trạng thái test pass**; nếu có failure, xem stack trace của test và cấu hình security integration, không “chữa” bằng cách tắt filter chain.

**Điều mà bộ test chứng minh:**

1. `user("alice").roles("READER")` tạo identity có authority đúng cho rule.
2. `user("phantom")` vẫn đi qua vì processor **không truy vấn** in-memory user store.
3. `anonymous()` bị từ chối ở route riêng tư nhưng được phép ở route public.
4. `user("mallory").roles("VIEWER")` đã có user giả lập nhưng thiếu role nên nhận 403.
5. `authentication(auth)` cho phép quyền `AUDIT_READ` tùy chỉnh.
6. `securityContext(context)` truyền cả context để route đọc role READER.
7. `httpBasic(...)` thực sự đưa credential qua Basic filter và user store, nên sai password/user không tồn tại nhận 401.

Nhờ vậy một test không chỉ kiểm tra “200 khi có role” mà còn chứng minh **khác biệt giữa mock authentication và authentication thật**.

## 10. Đọc chính xác status 401 và 403

Với API sử dụng HTTP Basic như ví dụ:

| Trạng thái request | Kết quả thông thường | Vì sao |
| --- | --- | --- |
| Không có authentication, route protected | `401 Unauthorized` | Cần đăng nhập/xác thực |
| `anonymous()` với route protected | `401 Unauthorized` | Anonymous không đáp ứng `.hasRole` hoặc `.authenticated()` |
| User giả lập đã authenticated nhưng thiếu `ROLE_READER` | `403 Forbidden` | Authentication có rồi, authorization không đủ |
| `user("alice").roles("READER")` | `200 OK` | Đúng authority |
| Header HTTP Basic sai password | `401 Unauthorized` | AuthenticationProvider không chấp nhận credential |
| `user("phantom").roles("READER")` | `200 OK` trong test | Được gắn mock principal, không truy vấn user store |

Những status trên thuộc **cấu hình demo cụ thể**. Với form login, SSO/OIDC, custom entry point, API gateway hoặc `AccessDeniedHandler`, có thể nhận `302`, `401`, `403` hoặc response format khác. Vì vậy test phải xác nhận **contract của ứng dụng**, không ép mọi hệ thống theo cùng status.

Một lỗi chẩn đoán phổ biến: test dùng `.with(user(...))` rồi tin rằng nó đã kiểm tra password encoder hay tài khoản bị disable. Không; token giả lập đã có authorities trước khi filter chain kiểm tra authorization.

## 11. Test quyền theo `roles` và `authorities`

Spring Security phân biệt hai lối kiểm tra:

```java
.hasRole("READER")
.hasAuthority("REPORT_EXPORT")
```

`hasRole("READER")` theo convention sẽ tìm `"ROLE_READER"`. `hasAuthority("REPORT_EXPORT")` tìm đúng chuỗi `"REPORT_EXPORT"`.

Trong test:

```java
.with(user("alice").roles("READER"))
```

khác với:

```java
.with(user("alice").authorities(
        new SimpleGrantedAuthority("REPORT_EXPORT")))
```

Nếu bạn viết:

```java
.with(user("alice").authorities(
        new SimpleGrantedAuthority("READER")))
```

thì kết quả **không** thỏa `hasRole("READER")` vì thiếu tiền tố `ROLE_`. Đây là lỗi test rất thường gặp khi ứng dụng trộn scope JWT (`SCOPE_orders.read`), role (`ROLE_ADMIN`) và permission nghiệp vụ (`REPORT_EXPORT`).

Không nên tự thêm tiền tố lần hai: `.roles("ROLE_READER")` không phải cách chuẩn để đưa role `READER` vào DSL. Thay vào đó, dùng `.roles("READER")` hoặc `.authorities(new SimpleGrantedAuthority("ROLE_READER"))`.

## 12. `@WithMockUser` và RequestPostProcessor khác nhau thế nào?

Spring Security Test cũng có annotation:

```java
@WithMockUser(username = "alice", roles = "READER")
@Test
void example() throws Exception {
    mockMvc.perform(get("/api/reports"))
            .andExpect(status().isOk());
}
```

Đây là **đoạn trong một JUnit test class**, cần import `org.springframework.security.test.context.support.WithMockUser`, `@Test`, `MockMvc` và `MockMvcRequestBuilders` tương ứng.

So sánh:

- `@WithMockUser` chuẩn bị security context theo scope method/class test; tiện khi nhiều request trong test dùng cùng identity.
- `.with(user(...))` đặt identity cho **một request MockMvc cụ thể**, tiện kiểm tra nhiều user/authority khác nhau trong một test.
- `.with(anonymous())` có thể ghi đè trạng thái user giả lập để kiểm tra một request không đăng nhập.
- `@WithUserDetails` tải `UserDetails` từ service để mô phỏng user có thật; nhưng vẫn là hỗ trợ test và không đồng nghĩa đã kiểm password qua authentication filter.
- Với nhiều request trong một test, hãy scope rõ identity của từng request để tránh test phụ thuộc trạng thái còn lại.

Đừng coi annotation và processor là hai tầng xác thực được cộng dồn. Chúng là **những cách chuẩn bị test security context**, có thứ tự ưu tiên theo scope và request.

## 13. Tích hợp MockMvc với `SecurityFilterChain` thực tế

**Spring Boot full integration test** thường cấu hình:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ApiTest {
    @Autowired MockMvc mockMvc;
}
```

`@AutoConfigureMockMvc` sử dụng Spring application context và các filter bean phù hợp; ví dụ trong phần 9 dựa vào cơ chế này để chạy authorization rules thật.

Nếu **tự xây MockMvc** từ WebApplicationContext, cần tích hợp Spring Security:

```java
MockMvc mvc = MockMvcBuilders.webAppContextSetup(context)
        .apply(springSecurity())
        .build();
```

Đây là **đoạn trong test method/setup** với biến `context` kiểu `WebApplicationContext`, import `MockMvcBuilders` và `SecurityMockMvcConfigurers.springSecurity`. Nó đảm bảo security filter chain và Spring Security Test support tham gia vào request.

Nếu dùng `MockMvcBuilders.standaloneSetup(controller)`, chỉ có controller được đăng ký theo cách tối giản; Spring Security filter chain **không tự xuất hiện**. Trường hợp này phù hợp unit test thuần MVC nhưng **không đủ** để kết luận `hasRole`/`hasAuthority` đang hoạt động. Muốn test security, ưu tiên context-based MockMvc hoặc tự gắn security filter chain đúng cách với đầy đủ dependencies.

Một bài test có request processor nhưng không có security filters vẫn có thể sai ý nghĩa: controller trả dữ liệu không có nghĩa endpoint được bảo vệ.

## 14. Dùng `defaultRequest(...)` và override theo request

Khi nhiều request trong suite dùng chung một user, bạn có thể đặt request mặc định:

```java
MockMvc mvc = MockMvcBuilders.webAppContextSetup(context)
        .defaultRequest(get("/").with(user("alice").roles("READER")))
        .apply(springSecurity())
        .build();
```

Đây là **đoạn setup**, không phải một file độc lập; cần các import MockMvc Builders, HTTP builder, `user` và `springSecurity`. Với mỗi request, vẫn có thể ghi đè identity:

```java
mvc.perform(get("/api/reports").with(anonymous()))
        .andExpect(status().isUnauthorized());
```

Trọng tâm là **request-specific override** để kiểm tra negative scenario. Nếu test mong anonymous nhưng nhận 200 vì default user vẫn còn hiệu lực, xem thứ tự kết hợp các request processor, phương thức setup, cookie/session và annotation context.

Đừng tái sử dụng cùng một đối tượng `SecurityContext` có thể bị mutate qua nhiều test song song. Tạo context mới cho từng tình huống, không lưu một context có quyền ADMIN trong field static để rồi các test chia sẻ trạng thái ngoài ý muốn.

## 15. CSRF, method security và các cơ chế khác

Một request có principal giả lập không đồng nghĩa request POST đã qua CSRF. Với Spring Security Servlet có CSRF protection:

```java
mockMvc.perform(post("/api/items")
        .with(user("alice").roles("EDITOR"))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"name\":\"demo\"}"));
```

Đây là **đoạn minh họa**, giả định endpoint `/api/items` và quyền tương ứng được cấu hình; import `csrf`, `MediaType` và `post` là cần thiết. Nếu bỏ `.with(csrf())`, request POST dùng cookie/session có thể bị chặn 403 **vì CSRF**, dù user có role đúng. Không tắt CSRF để làm test xanh khi ứng dụng web vẫn dùng credential gắn tự động.

Tương tự:

- Method security qua `@PreAuthorize` cần cấu hình `@EnableMethodSecurity` và gọi service qua Spring proxy. `.with(user(...))` chuẩn bị identity, không tự kích hoạt method interception.
- Nếu kiểm tra quyền sở hữu object/tenant, role `READER` chỉ là một phần; service phải kiểm tra `ownerId`/tenant cụ thể.
- Với JWT Resource Server, test converter/decoder riêng thay vì luôn dựng `Authentication` sẵn rồi kết luận JWT bảo mật đúng.
- Nếu app dùng session, test nhiều request và cookie cần mô phỏng persistence có chủ đích; RequestPostProcessor không tự chứng minh session store an toàn.
- Nếu app dùng async Servlet, cần `asyncDispatch` khi kiểm tra response cuối, và hiểu `SecurityContext` có thể cần context propagation sang worker thread.

## 16. Không dùng mock principal để chứng minh login thật

Có ba mức kiểm thử cần tách rõ:

### A. Authorization-focused test

```java
mvc.perform(get("/api/reports")
        .with(user("alice").roles("READER")))
    .andExpect(status().isOk());
```

Mục tiêu: rule `hasRole("READER")` có cho phép người có authority tương ứng truy cập hay không.

### B. Authentication-focused test

```java
mvc.perform(get("/api/reports")
        .with(httpBasic("alice", "demo-only")))
    .andExpect(status().isOk());
```

Mục tiêu: Basic filter, AuthenticationManager, UserDetailsService và PasswordEncoder configuration phối hợp đúng, ít nhất ở mức context test này. Cần thêm negative cases password sai/user khóa.

### C. End-to-end production-like test

Kiểm thử qua HTTP server/gateway thật, TLS, session/OIDC/JWT provider thực hoặc fixture có chữ ký, proxy headers và database đã cấu hình. MockMvc không mô phỏng toàn bộ container networking hoặc external identity provider.

Nếu bài test chỉ dùng `.with(authentication(jwtAuth))`, nó không chứng minh chữ ký JWT hoặc issuer/audience được validate. Nếu chỉ dùng `.with(user(...))`, nó không chứng minh authentication provider chấp nhận tài khoản. Nếu chỉ dùng `httpBasic`, nó không chứng minh OAuth2 login hay quyền dữ liệu nhiều tenant.

## 17. Những lỗi phổ biến

| Triệu chứng | Nguyên nhân thường gặp | Cách khắc phục |
| --- | --- | --- |
| `.with(user("alice"))` cho 200 dù DB không có alice | Processor không truy vấn user store | Dùng luồng auth thực để test credential, dùng mock cho authorization |
| `.with(user(...).roles("ADMIN"))` nhưng 403 | Rule cần authority khác hoặc object/tenant check | Đọc đúng SecurityFilterChain và `GrantedAuthority` |
| `.with(user(...).authorities("ADMIN"))` không thỏa `hasRole("ADMIN")` | Thiếu `ROLE_` prefix | Dùng `.roles("ADMIN")` hoặc `SimpleGrantedAuthority("ROLE_ADMIN")` |
| `anonymous()` nhận redirect thay vì 401 | App dùng form login | Kiểm tra entry point và contract route |
| Người không đủ quyền nhận 401 thay vì 403 | Authentication context chưa được cài hoặc filter chain chưa đúng | Kiểm tra MockMvc security integration |
| Test luôn 200 cả khi thiếu role | Test dùng `standaloneSetup` không gắn filter | Dùng WebApplicationContext + `springSecurity()` |
| `securityContext(ctx)` không ảnh hưởng controller | Security filters/test support không được tích hợp | Kiểm tra setup và cách tạo context |
| Test PASS nhưng login production FAIL | Toàn test dùng `.with(user(...))` | Thêm authentication-focused và E2E tests |
| POST nhận 403 dù user có role | Thiếu CSRF token hoặc custom access policy | Kiểm tra CSRF, method và headers |
| Test kiểm JWT pass nhưng token giả ngoài đời bị từ chối | Đã mock JWT Authentication, bỏ qua decoder | Test decode/validation hoặc request qua bearer filter |
| Hai test dùng lẫn user | SecurityContext/session/test fixture bị chia sẻ | Dùng request-specific processor và isolation |
| Authority sai khi đổi OIDC provider | Roles/scopes mapping chưa được test | Test converter, issuer/audience/claims với fixture phù hợp |

### Debug theo thứ tự

1. Xác nhận đang test **đúng endpoint, HTTP method và SecurityFilterChain**.
2. Xác nhận MockMvc đã tích hợp Spring Security (`@AutoConfigureMockMvc` hoặc `springSecurity()`).
3. Xác nhận request dùng mock identity hay credential thật; đừng nhầm hai thứ.
4. Xem `Authentication#getName`, `isAuthenticated`, `getAuthorities` **trong test/log nội bộ**, không log mật khẩu/token.
5. Xác định 401 do thiếu authentication hay 403 do authorization/CSRF.
6. Với custom `Authentication`, kiểm tra `authenticated` flag và authority prefix.
7. Với method security, kiểm tra proxy/interception và điều kiện resource ownership.
8. Thêm test negative trước khi nới Security config.

## 18. Bảo vệ chất lượng test và tính độc lập

Các nguyên tắc hữu ích:

- Mỗi test nên nói rõ **identity đang giả lập** và **quy tắc cần kiểm tra**.
- Tách test authorization, test authentication mechanism và test E2E; không để một nhóm thay thế nhóm khác.
- Dùng `.with(anonymous())` để kiểm tra denial path, không chỉ kiểm tra happy path.
- Kiểm tra `ROLE_`/`SCOPE_`/custom authority chính xác, không chỉ so sánh một username.
- Dùng `securityContext(...)` khi cần thiết; với case đơn giản, `user(...)` giúp test ngắn và ít sai.
- Tạo `Authentication` giả với authorities tối thiểu, không tự gán ADMIN cho mọi request.
- Không lấy username từ request header của client rồi dựng `Authentication` đáng tin nếu chưa có xác thực/ranh giới proxy.
- Không in password, token hoặc `SecurityContext` đầy đủ ra log.
- Nếu test dùng fixed time/random ID, kiểm soát đồng hồ/test data để kết quả lặp lại được.
- Nếu chạy test song song, tránh chia sẻ `SecurityContextHolder`, session hoặc static mocks giữa tests.
- Xác minh cả mã HTTP, body, quyền trên object và nội dung error contract khi có giá trị.

## 19. Bài tập áp dụng

### Bài 1: Role và permission

Thêm route `GET /api/export` yêu cầu `hasAuthority("REPORT_EXPORT")`. Viết một test cho:

- User có `ROLE_READER` nhưng thiếu `REPORT_EXPORT` → bị từ chối.
- User có đúng `REPORT_EXPORT` qua `.with(user("alice").authorities(...))` → đi qua.
- User anonymous → không được truy cập.

Mục tiêu: phân biệt `roles()` và `authorities()`.

### Bài 2: Context và principal tùy chỉnh

Tạo một `Authentication` có principal là `UserDetails` chứa `tenantId`. Dùng `authentication(...)` và `securityContext(...)` ở hai test riêng để xác nhận controller/service đọc đúng tenant từ principal. Sau đó test tenant khác không được xem dữ liệu của tenant hiện tại.

Mục tiêu: tránh chỉ dựa vào `getName()` khi quyền đối tượng thuộc tenant.

### Bài 3: Authentication thật vs mock

Cho in-memory store chỉ có `alice`. Dùng `user("phantom")` để xác nhận rule authorization sẽ cho phantom có `ROLE_READER` đi qua trong test; sau đó dùng `httpBasic("phantom","anything")` để xác nhận provider **không** đăng nhập phantom. Viết chú thích giải thích tại sao cả hai kỳ vọng cùng đúng.

Mục tiêu: phân biệt việc inject security context và xác thực credential.

## Ghi nhớ

`RequestPostProcessor` trong Spring Security Test giúp MockMvc dựng **một HTTP request có trạng thái bảo mật được kiểm soát**. `user(...)` thuận tiện cho user/role giả lập; `anonymous()` kiểm tra caller chưa đăng nhập; `authentication(...)` gắn một `Authentication` tùy chỉnh; `securityContext(...)` gắn cả `SecurityContext`. Các processor này đặc biệt hữu ích cho **authorization tests**, nhưng **không chứng minh** mật khẩu, JWT, OIDC hay account policy đã được xác thực thật. Muốn test đúng, hãy tích hợp SecurityFilterChain vào MockMvc, phân biệt 401 với 403, thêm negative tests và kiểm thử riêng luồng authentication thực.