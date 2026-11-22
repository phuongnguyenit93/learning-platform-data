# Thêm `spring-security-test` và nạp đúng cấu hình bảo mật khi kiểm thử Spring Security

> **Phạm vi:** Kiểm thử ứng dụng **Spring MVC (Servlet stack)** với Java 17+, Spring Boot 3.x, Spring Security 6.x, JUnit 5 và MockMvc. Trọng tâm là khai báo `spring-security-test` và bảo đảm mỗi test sử dụng đúng `SecurityFilterChain`, authentication provider, user/role, CSRF và các bean bảo mật liên quan. Với WebFlux, cần bộ công cụ và cấu hình reactive tương ứng.

## 1. Tại sao thêm dependency thôi chưa đủ?

Một test controller có thể “xanh” trong khi ứng dụng thật trả 401 hoặc 403, hoặc ngược lại. Nguyên nhân thường là **context kiểm thử không nạp đúng cấu hình bảo mật**: filter bảo mật bị bỏ qua, test slice chỉ lấy một phần bean, mock user thay thế quá trình đăng nhập thật, hoặc một default `SecurityFilterChain` khác đang áp dụng.

Ví dụ: production yêu cầu `ROLE_ADMIN` cho `/api/admin`, nhưng test dùng `@AutoConfigureMockMvc(addFilters = false)` và chỉ kiểm controller trả 200. Test này **không chứng minh** endpoint đã được bảo vệ. Trái lại, nếu `@WebMvcTest` nạp một chain mặc định yêu cầu login cho mọi URL thay vì chain ứng dụng cho phép `/api/public`, một test 401 cũng **không chứng minh** cấu hình production đúng.

Mục tiêu của bài học:

1. Khai báo `spring-security-test` trong **test scope**, cùng `spring-boot-starter-test`.
2. Chọn đúng giữa **`@SpringBootTest` + `@AutoConfigureMockMvc`** và **`@WebMvcTest` + `@Import`**.
3. Đảm bảo security filters thực sự chạy trong `MockMvc`.
4. Phân biệt `@WithMockUser`, `@WithUserDetails`, `user(...)`, `httpBasic(...)` và `csrf()`.
5. Test đủ trường hợp anonymous, sai credentials, đúng credentials, thiếu quyền và CSRF.
6. Biết cách chẩn đoán lỗi do test context thay vì sửa bừa SecurityConfig.

## 2. Thêm dependency kiểm thử đúng cách

Trong dự án Gradle dùng Spring Boot plugin và dependency management, khai báo:

```groovy
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

- `spring-boot-starter-test` cung cấp cơ sở kiểm thử Spring Boot, Spring Test, JUnit Jupiter, MockMvc và các công cụ assertion/mock thường dùng.
- `spring-security-test` cung cấp các thành phần chuyên biệt như `@WithMockUser`, `@WithUserDetails`, `SecurityMockMvcRequestPostProcessors.httpBasic(...)`, `csrf()`, `user(...)`, `springSecurity()` và các request/result matchers bảo mật.
- `spring-boot-starter-security` thuộc **runtime/application dependency**; `spring-security-test` thuộc **test dependency**. Thêm test dependency **không tự tạo user, không kích hoạt SecurityFilterChain mới và không sửa chính sách runtime**.
- Khi dùng Spring Boot BOM/dependency management, **không cần tự ghim version riêng** cho `spring-security-test`: chọn phiên bản tương thích mà Spring Boot quản lý. Tránh trộn một bản Spring Security Test tùy ý với các artifact security runtime phiên bản khác.

Với Maven, dependency quan trọng là:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
```

Ứng dụng Maven cũng cần `spring-boot-starter-test` trong `test` scope và `spring-boot-starter-security` là dependency ứng dụng.

### 2.1. Những import thường dùng

```java
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.test.context.support.WithUserDetails;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;

import static org.springframework.security.test.web.servlet.setup
    .SecurityMockMvcConfigurers.springSecurity;
```

Đây là **danh sách import minh họa**; không phải mọi class cần tất cả chúng. Sau khi thêm dependency, chạy `./gradlew test` để Gradle tải và kiểm tra test classpath.

## 3. Phải nạp những gì để kiểm thử bảo mật đúng?

Luồng test HTTP dùng MockMvc cần hai điều:

1. **Các bean cấu hình bảo mật đúng:** `SecurityFilterChain` thật sự áp dụng cho URL/method đang kiểm, cùng `UserDetailsService`, `AuthenticationProvider`, `PasswordEncoder`, filter tùy chỉnh hoặc các dependency bảo mật cần thiết.
2. **Tích hợp security filter với MockMvc:** request phải đi qua `FilterChainProxy` để authentication/authorization/CSRF xử lý giống đường Servlet thông thường.

Mô hình:

```text
MockMvc.perform(request)
        |
        v
Spring Security FilterChainProxy (nếu đã đăng ký đúng)
        |
        +--> Authentication filter (HTTP Basic/form/Bearer...)
        |
        +--> SecurityContext / AuthorizationFilter / CsrfFilter
        |
        +--> Controller / Service / Method Security
        |
        v
MockHttpServletResponse -> status / headers / body / redirect
```

Nếu thiếu (1), test có thể chạy qua **default security chain** khác với ứng dụng. Nếu thiếu (2), controller có thể được gọi mà **không qua bất kỳ filter kiểm quyền nào**. Hai lỗi này độc lập: có bean `SecurityFilterChain` trong context **chưa đủ chứng minh** MockMvc đã đăng ký filter; và có filter trong MockMvc **chưa đủ chứng minh** đó là chính sách mong muốn.

### 3.1. Hai lựa chọn chính trong Spring Boot

| Mục tiêu | Kiểu test | Những gì được nạp |
| --- | --- | --- |
| Kiểm tra HTTP security với cấu hình ứng dụng đầy đủ: login thật, encoder, filter, role, CSRF | `@SpringBootTest` + `@AutoConfigureMockMvc` | ApplicationContext của ứng dụng cùng auto-configuration/bean thực theo test profile. |
| Kiểm tra riêng MVC/controller và rules HTTP, tránh nạp toàn hệ thống | `@WebMvcTest(Controller.class)` + `@Import(SecurityConfig.class)` khi cần | MVC slice, MockMvc và cấu hình bảo mật **được import rõ ràng**; các service/repository khác thường phải mock hoặc import. |
| Tự dựng MockMvc từ `WebApplicationContext` | `MockMvcBuilders.webAppContextSetup(context).apply(springSecurity())` | Web context do test đã tạo và tích hợp đúng Spring Security. |
| Unit test service không cần Servlet | JUnit/Spring method-security test thích hợp | Không tự chứng minh HTTP `SecurityFilterChain`; muốn test `@PreAuthorize` phải nạp method security và bean được proxy. |

**Mặc định** `@AutoConfigureMockMvc` có `addFilters = true`. `@WebMvcTest` cũng tự cấu hình MockMvc và cơ sở Spring Security cho MVC slice, nhưng slice không bảo đảm tự lấy **toàn bộ custom security beans** có dependency ngoài slice; vì thế cần chủ động xem và import cấu hình thực dùng. Khi muốn kiểm cả hệ thống từ HTTP đến database, chọn full context thay vì vô tình biến một slice test thành giả lập.

## 4. Ví dụ ứng dụng Java 17+ để kiểm thử

Ví dụ bên dưới dùng Spring Boot **3.3.5** (phiên bản ghim minh họa, không phải tuyên bố mới nhất), HTTP Basic, hai user trong bộ nhớ, rule role và CSRF mặc định. Tất cả test dùng **chính cấu hình** của ứng dụng. Để chạy, tạo dự án Gradle có cấu trúc thư mục đúng như hướng dẫn.

### 4.1. Cấu hình Gradle hoàn chỉnh

`settings.gradle`:

```groovy
rootProject.name = 'security-test-demo'
```

`build.gradle`:

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

### 4.2. Application, controller và SecurityFilterChain

Tạo `src/main/java/demo/securitytest/SecurityTestDemoApplication.java`:

```java
package demo.securitytest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityTestDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityTestDemoApplication.class, args);
    }
}

@RestController
class DemoController {
    @GetMapping("/api/public")
    String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/me")
    String me(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/api/admin")
    String adminEndpoint() {
        return "admin";
    }

    @PostMapping("/api/messages")
    ResponseEntity<String> createMessage() {
        return ResponseEntity
            .status(HttpStatus.CREATED)
            .body("created");
    }
}

@Configuration
class DemoSecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("reader123"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin123"))
                .roles("USER", "ADMIN")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/api/messages")
                    .hasRole("USER")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);

        return http.build();
    }
}
```

Chủ ý của cấu hình:

- `/api/public` cho phép anonymous.
- `/api/me` yêu cầu có user xác thực; trả tên principal.
- `/api/admin` yêu cầu authority `ROLE_ADMIN`.
- `POST /api/messages` yêu cầu `ROLE_USER` **và** CSRF token hợp lệ theo cấu hình CSRF Servlet mặc định.
- User `reader` chỉ có `ROLE_USER`; user `admin` có cả `ROLE_USER` và `ROLE_ADMIN`.
- `httpBasic` cho phép kiểm tra credentials thật bằng `httpBasic(...)` trong MockMvc. `formLogin(...disable)` tránh redirect trang login làm nhiễu kết quả API.
- **Không tắt CSRF** trong ví dụ để có thể kiểm thử trường hợp request ghi thiếu/đủ CSRF token.
- Password được hash BCrypt khi tạo user. Credentials trong ví dụ chỉ dùng học tập và phải được thay bằng nguồn an toàn khi triển khai thật.

`DemoController` và `DemoSecurityConfig` là **package-private classes** trong cùng tệp với public class ứng dụng, hợp lệ theo Java. Test đặt trong cùng package `demo.securitytest` sẽ tham chiếu được chúng.

### 4.3. Bảng hành vi kỳ vọng

| Request | Credentials / CSRF | Kết quả mong đợi |
| --- | --- | --- |
| `GET /api/public` | Không gửi | **200**, nội dung `public`. |
| `GET /api/me` | Không gửi | **401**, yêu cầu xác thực HTTP Basic. |
| `GET /api/me` | `reader` / mật khẩu sai | **401**, xác thực thất bại. |
| `GET /api/me` | `reader:reader123` | **200**, nội dung `reader`. |
| `GET /api/admin` | Reader hợp lệ | **403**, thiếu `ROLE_ADMIN`. |
| `GET /api/admin` | Admin hợp lệ | **200**, nội dung `admin`. |
| `POST /api/messages` | Reader hợp lệ, thiếu CSRF | **403**, bị `CsrfFilter` từ chối. |
| `POST /api/messages` | Reader hợp lệ, có CSRF hợp lệ | **201**, nội dung `created`. |

**Không dựa vào việc app khởi động thành công để kết luận test đúng**: cần các test âm tính cho 401/403 và test dương tính cho 200/201. Cũng không coi 403 thiếu CSRF là thiếu role; phải phân biệt theo điều kiện request.

## 5. Kiểm thử với toàn bộ cấu hình: `@SpringBootTest`

Tạo `src/test/java/demo/securitytest/SecurityFullContextTest.java`:

```java
package demo.securitytest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityFullContextTest {
    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointDoesNotRequireLogin() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void anonymousUserReceives401ForProtectedEndpoint() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void invalidPasswordIsRejectedByRealAuthentication() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("reader", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validPasswordAuthenticatesThroughHttpBasic() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("reader", "reader123")))
            .andExpect(status().isOk())
            .andExpect(content().string("reader"));
    }

    @Test
    void readerIsForbiddenFromAdminEndpoint() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("reader", "reader123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminIsAllowed() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }

    @Test
    void postWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/messages")
                .with(httpBasic("reader", "reader123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithCsrfIsCreated() throws Exception {
        mvc.perform(post("/api/messages")
                .with(httpBasic("reader", "reader123"))
                .with(csrf()))
            .andExpect(status().isCreated())
            .andExpect(content().string("created"));
    }
}
```

**Vì sao test này kiểm tra đúng đường HTTP?**

- `@SpringBootTest` khởi tạo application context đầy đủ dựa trên `@SpringBootApplication`, bao gồm bean `DemoSecurityConfig`, user service và password encoder.
- `@AutoConfigureMockMvc` tạo `MockMvc` và mặc định đăng ký các filter từ context. Không cần tự gọi `.apply(springSecurity())` cho `MockMvc` được auto-configure theo cách này.
- `httpBasic("reader", "...")` thêm Authorization header HTTP Basic; credentials đi qua filter và provider để kiểm tra mật khẩu thật.
- Các test âm tính phân biệt chưa login, sai password, thiếu role và thiếu CSRF.
- `csrf()` đặt token hợp lệ theo support của Spring Security Test; nếu chỉ kiểm POST với `@WithMockUser` mà quên token, vẫn có thể bị 403 **do CSRF**, bất kể role đúng.
- Không cần mở cổng TCP: `MockMvc` thực thi pipeline Spring MVC trong tiến trình test bằng mock request/response.

`@SpringBootTest` có giá thành chạy lớn hơn slice test vì nạp nhiều bean. Đó là lựa chọn phù hợp khi mục tiêu là **xác nhận chính xác cấu hình bảo mật của ứng dụng**, đặc biệt khi provider/service/filter có phụ thuộc giữa các module.

### 5.1. Chạy các test

Ở thư mục dự án có Gradle Wrapper:

```bash
./gradlew test
```

Windows PowerShell/CMD:

```bat
gradlew.bat test
```

Để chỉ chạy suite vừa tạo:

```bash
./gradlew test --tests demo.securitytest.SecurityFullContextTest
```

Nếu tất cả assertion khớp, Gradle báo task `test` thành công; **đừng dự đoán cứng stdout** vì log phụ thuộc Gradle/IDE. Test failure sẽ chỉ ra ca khác kỳ vọng (ví dụ `Expected: 403`, `Actual: 401`), đây là tín hiệu để kiểm tra filter/context/credentials trước khi thay chính sách.

## 6. Kiểm thử controller slice: `@WebMvcTest` và `@Import`

`@WebMvcTest` chỉ nạp các thành phần có liên quan tới Spring MVC và những auto-configuration thích hợp. Nó **thường auto-configure security**, nhưng các bean bảo mật tùy chỉnh hoặc các dependency bên ngoài MVC slice có thể bị loại khỏi context. Vì thế khi cần kiểm đúng rule HTTP của ứng dụng, hãy **import cấu hình bảo mật thực** và cung cấp dependencies cần thiết.

Tạo `src/test/java/demo/securitytest/SecurityMvcSliceTest.java`:

```java
package demo.securitytest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@WebMvcTest(DemoController.class)
@Import(DemoSecurityConfig.class)
class SecurityMvcSliceTest {
    @Autowired
    MockMvc mvc;

    @Test
    void publicRuleFromImportedSecurityConfigIsActive() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk());
    }

    @Test
    void anonymousCannotAccessProfile() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void basicAuthenticationUsesImportedUserService() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("reader", "reader123")))
            .andExpect(status().isOk())
            .andExpect(content().string("reader"));
    }

    @Test
    void readerCannotAccessAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("reader", "reader123")))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "reader", roles = "USER")
    void mockUserCanTestAuthorizationWithoutPassword() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isOk())
            .andExpect(content().string("reader"));
    }
}
```

**Tại sao `@Import(DemoSecurityConfig.class)` quan trọng?** Nó cho slice biết phải nạp `SecurityFilterChain` mà ta muốn kiểm, cùng `UserDetailsService` và `PasswordEncoder` được khai báo trong cùng config. Nếu không import, test có thể dùng default security behavior hoặc thiếu beans phục vụ cơ chế riêng. Trong dự án thực có nhiều chain/profile/bean phụ thuộc, nên import đúng class cần thiết và xác nhận request dùng đúng chain.

**Đừng biến test slice thành test “giả toàn bộ” mà vẫn khẳng định đã tích hợp:** nếu controller inject `OrderService`, `AccountRepository` hoặc chính sách ngoài MVC, `@WebMvcTest` thường không load chúng. Khi kiểm controller riêng, mock collaborator phù hợp (ví dụ `@MockBean` trong Spring Boot 3.3) hoặc `@Import` adapter thật nếu có lý do. Nếu mục tiêu là kiểm DB, provider và những filter tương tác đầy đủ, ưu tiên test full context.

### 6.1. Khi có nhiều `SecurityFilterChain`

Một ứng dụng có thể có chain cho `/api/**`, `/admin/**` và web form. Một test chỉ xác nhận “có bean security” vẫn có thể rơi vào chain sai.

- Kiểm `securityMatcher(...)` của từng chain, thứ tự `@Order` và `requestMatchers(...)` trong chain.
- Nạp các chain đúng với mục tiêu test; nếu slice chỉ import một chain, cần ghi rõ nó **không đại diện cho toàn bộ ứng dụng**.
- Test ít nhất một URL thuộc mỗi chain, cộng một URL ngoài matcher để xác nhận fallback/default.
- `@ActiveProfiles("test")` có thể làm cấu hình thay đổi, nhưng **không tự bảo đảm** chain production vẫn như cũ. Phải xem các bean `@Profile`, `@ConditionalOnProperty`, `@TestConfiguration` và overrides.
- Không tạo một `permitAll()` chain “dành cho test” nếu nhiệm vụ đang kiểm tra rằng endpoint production có kiểm quyền.

### 6.2. Lúc nào nên mock service?

Nếu controller cần collaborator:

```java
@RestController
class ReportController {
    private final ReportService service;

    ReportController(ReportService service) {
        this.service = service;
    }
}
```

Một `@WebMvcTest(ReportController.class)` chỉ nên mock `ReportService` để kiểm request mapping, validation, status, authorization HTTP của controller. **Đoạn trên chỉ minh họa dependency**, chưa phải tệp độc lập. Muốn kiểm method security trên service thật, mock service sẽ bỏ qua lời gọi proxy thực; phải viết integration test có bean/proxy method security.

## 7. `@WithMockUser`, `@WithUserDetails`, `user(...)` và `httpBasic(...)` khác nhau thế nào?

| Công cụ | Thực hiện gì? | Có xác thực password thật? | Nên dùng khi |
| --- | --- | --- | --- |
| `@WithMockUser(username="...", roles="...")` | Spring Security Test đưa authentication giả vào `SecurityContext` cho test. | **Không** | Kiểm role/authorization với danh tính kiểm thử. |
| `.with(user("reader").roles("USER"))` | Gắn principal giả trên **request MockMvc cụ thể**. | **Không** | Một test có nhiều request dùng danh tính khác nhau. |
| `@WithUserDetails(value="reader")` | Tải `UserDetails` qua bean `UserDetailsService` để lập security context test. | **Không**; có lookup user nhưng không so khớp password thô | Kiểm quy tắc dùng principal/authorities thật của user fixture. |
| `.with(httpBasic("reader","reader123"))` | Thêm HTTP Basic header vào request. Filter/provider xử lý credentials nếu security filters đúng. | **Có, trong luồng Basic được cấu hình** | Kiểm xác thực, encoder, provider và filter bằng request HTTP. |
| `.with(csrf())` | Thêm CSRF token hợp lệ vào request; `.with(csrf().useInvalidToken())` tạo trường hợp sai. | Không liên quan password | Kiểm POST/PUT/PATCH/DELETE khi bật CSRF. |

**Ví dụ kiểm quyền mà không đụng password:**

```java
@Test
@WithMockUser(username = "admin", roles = {"USER", "ADMIN"})
void adminIsAuthorizedWithSimulatedPrincipal() throws Exception {
    mvc.perform(get("/api/admin"))
        .andExpect(status().isOk());
}
```

Đoạn này có thể được thêm như method của một trong các test class đã cấu hình MockMvc bên trên. Nó **không chứng minh** account `admin` tồn tại, password hợp lệ hay provider đã hoạt động. `@WithMockUser` dùng annotations ở test method/class; Spring Test listener tạo và dọn `SecurityContext` trong vòng đời test.

**Ví dụ muốn nạp user fixture qua service:**

```java
@Test
@WithUserDetails(
    value = "reader",
    userDetailsServiceBeanName = "userDetailsService"
)
void userDetailsFixtureCanReadProfile() throws Exception {
    mvc.perform(get("/api/me"))
        .andExpect(status().isOk())
        .andExpect(content().string("reader"));
}
```

Đoạn này cũng thuộc test class có `MockMvc`; nó cần bean `userDetailsService` và user `reader` thực sự tồn tại trong nguồn test. Không đưa `@WithUserDetails` vào test để xác nhận **mật khẩu sai bị từ chối**: annotation đã nạp principal qua service, không gửi password sai cho provider.

**Ví dụ request-scoped principal giả:**

```java
mvc.perform(get("/api/admin").with(user("reader").roles("USER")))
    .andExpect(status().isForbidden());
```

Để `user(...)` và `@WithMockUser` tương tác với MVC security context đúng, `MockMvc` phải được tích hợp Spring Security như ở các ví dụ trên.

### 7.1. Role prefix

`roles = "ADMIN"` trong `@WithMockUser` tạo authority `ROLE_ADMIN`. Tương tự, `.with(user("reader").roles("USER"))` tạo `ROLE_USER`. Nếu rule là `hasAuthority("SCOPE_read")`, hãy dùng `authorities = "SCOPE_read"` thay vì tự mặc định mọi quyền là role. Kiểm chính xác tập authorities mà production principal nhận được.

### 7.2. CSRF đúng ngữ cảnh

Với Spring Security Servlet bật CSRF mặc định, request đổi trạng thái như POST thường cần token:

```java
mvc.perform(post("/api/messages")
        .with(httpBasic("reader", "reader123"))
        .with(csrf()))
    .andExpect(status().isCreated());

mvc.perform(post("/api/messages")
        .with(httpBasic("reader", "reader123"))
        .with(csrf().useInvalidToken()))
    .andExpect(status().isForbidden());
```

Token trong test là **giả lập theo API kiểm thử Spring Security**, không phải bằng chứng client production đã lấy/gửi token đúng quy trình UI. Với ứng dụng stateless chỉ dùng Bearer token header, CSRF có thể được cấu hình khác; test phải **theo chính sách CSRF thực tế** của ứng dụng thay vì vô điều kiện gắn `csrf()` hoặc tắt CSRF để được 200.

## 8. Khi tự tạo `MockMvc`, phải tích hợp `springSecurity()`

Có hai cách khởi tạo MockMvc thường gặp:

**Cách A — Spring Boot tự cấu hình:** `@SpringBootTest` + `@AutoConfigureMockMvc` hoặc `@WebMvcTest` đã có MockMvc. Không cần tự gọi builder để đăng ký filter.

**Cách B — tự dựng từ `WebApplicationContext`:** tạo `MockMvc` và gọi `.apply(springSecurity())`. Ví dụ test class độc lập, dùng lại application code ở mục 4:

```java
package demo.securitytest;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.context.WebApplicationContext;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.security.test.web.servlet.setup
    .SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
class ManualSecurityMockMvcTest {
    @Autowired
    WebApplicationContext context;

    MockMvc mvc;

    @BeforeEach
    void setUp() {
        mvc = MockMvcBuilders
            .webAppContextSetup(context)
            .apply(springSecurity())
            .build();
    }

    @Test
    void anonymousCannotReadProfile() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }
}
```

`springSecurity()` gắn `FilterChainProxy` cùng các test post-processor cần thiết cho Spring Security. Nếu dùng `MockMvcBuilders.standaloneSetup(controller)` thuần túy, MVC xử lý controller **không có nghĩa đã nạp SecurityFilterChain thật**. Có thể cấu hình filters thủ công trong standalone setup, nhưng nếu mục tiêu là kiểm tích hợp bảo mật, dùng web application context dễ kiểm đúng hơn.

**Không vừa inject MockMvc auto-configure vừa tự add filter trùng lặp**: việc chạy filter hai lần có thể làm sai session, CSRF, exception translation và khiến kết quả khó hiểu.

## 9. Kiểm thử method security và giới hạn của MVC test

`SecurityFilterChain` bảo vệ HTTP path. Annotation như `@PreAuthorize`/`@PostAuthorize` bảo vệ **phương thức**, thường yêu cầu `@EnableMethodSecurity` và Spring proxy đúng cách. Một test MVC chỉ kiểm controller có thể chưa kiểm tra method security trên service nếu service bị mock.

Ví dụ mã **minh họa**, cần đặt trong bean service đã đăng ký và cấu hình `@EnableMethodSecurity`:

```java
@Service
class ApprovalService {
    @PreAuthorize("hasAuthority('approve:request')")
    public String approve() {
        return "approved";
    }
}
```

Để kiểm một method như vậy:

1. Load context có `@EnableMethodSecurity` và bean `ApprovalService` thực được Spring quản lý.
2. Gọi **qua Spring proxy**, không gọi trực tiếp `new ApprovalService()` hoặc self-invocation rồi kỳ vọng annotation được áp dụng.
3. Dùng `@WithMockUser(authorities = "approve:request")` cho ca được phép, `@WithMockUser(authorities = "read:request")` cho ca thiếu quyền.
4. Nếu kết quả quan trọng ở API, viết thêm HTTP integration test nạp service thật. Method security proxy bị bỏ qua khi controller gọi một mock service.

Đừng ngộ nhận `@EnableMethodSecurity` tự bật do `spring-security-test`. Dependency test cung cấp công cụ tạo SecurityContext; **chính ứng dụng** phải cấu hình method security theo yêu cầu.

## 10. Những lỗi thường gặp khi nạp cấu hình bảo mật

### Lỗi 1. `@AutoConfigureMockMvc(addFilters = false)` khi đang test Security

```java
// Sai nếu mục tiêu là kiểm thử authentication/authorization qua HTTP.
@SpringBootTest
@AutoConfigureMockMvc(addFilters = false)
class InsecureTestSetup {
}
```

Cấu hình này loại filters khỏi MockMvc; nhiều endpoint có thể được gọi trực tiếp. Đối với test bảo mật, giữ mặc định `addFilters = true`, sau đó xác nhận 401/403 thực sự xuất hiện khi thiếu quyền.

### Lỗi 2. `@WebMvcTest` chỉ test controller nhưng quên custom SecurityConfig

Nếu slice dùng default chain thay vì chain ứng dụng, endpoint công khai có thể nhận 401 không mong muốn. Import đúng cấu hình thực bằng `@Import(DemoSecurityConfig.class)` và mọi bean cần thiết. Với ứng dụng lớn, nếu phụ thuộc quá nhiều, dùng full context để kiểm chính sách thật.

### Lỗi 3. Chỉ dùng `@WithMockUser` rồi kết luận password/provider đúng

`@WithMockUser` cấp principal giả, không bắt buộc chạy `UserDetailsService.loadUserByUsername()` hay `PasswordEncoder.matches(...)`. Muốn kiểm authentication thật, dùng request Basic/form login hoặc test provider phù hợp và đúng chain.

### Lỗi 4. POST 403, lập tức gán thêm ROLE_ADMIN

CSRF có thể từ chối POST **trước khi** business authorization. Test thêm `.with(csrf())` cho case hợp lệ và test thiếu/sai token riêng. Nếu thực tế yêu cầu login role USER thì gán ADMIN là mở rộng quyền không cần thiết.

### Lỗi 5. Dùng `@WithMockUser` nhưng request không có SecurityContext

Nếu tự dựng MockMvc không gắn Spring Security, test listener có thể tạo context nhưng HTTP request không mang security context như kỳ vọng. Dùng `@AutoConfigureMockMvc` hoặc `.apply(springSecurity())` với web application context.

### Lỗi 6. Test profile thay thế security chain production

`@ActiveProfiles("test")` là cơ chế kích hoạt profile, có thể thay datasource, password encoder hoặc SecurityConfig. Kiểm thử cần biết đang kiểm **chính sách nào**, và có integration test xác nhận chain của ứng dụng sẽ triển khai. Không dùng `permitAll()` chỉ để mọi test đều xanh nếu test đang khẳng định tính an toàn.

### Lỗi 7. Sai thứ tự matcher hoặc nhiều filter chain

Trong `authorizeHttpRequests`, rule được đánh giá theo thứ tự; một rule rộng như `"/api/**"` đặt trước rule admin đặc biệt có thể làm rule sau không bao giờ được áp dụng. Với nhiều `SecurityFilterChain`, xem cả `securityMatcher` và `@Order` để biết request chạy qua chain nào.

### Lỗi 8. Ghi đè authentication bean hoặc thiếu dependency trong slice

Nếu service xác thực dùng repository thì `@WebMvcTest` có thể thiếu repository và fail startup. Đừng vô tình mock `AuthenticationManager` luôn trả authenticated rồi kết luận luồng password đã đúng. Chỉ mock collaborator khi mục tiêu kiểm một boundary rõ ràng; authentication integration test nên có provider và nguồn user thực/fixture phù hợp.

### Lỗi 9. `401` và `403` bị hiểu nhầm

API HTTP Basic chưa có credentials hoặc credentials sai thường trả **401**. Đã login nhưng thiếu authority thường **403**. Tuy vậy, 403 còn do CSRF; với form login, chưa đăng nhập có thể redirect thay vì 401. Viết assertion theo **cơ chế xác thực thực tế**, không máy móc lấy một status cho mọi ứng dụng.

### Lỗi 10. Test không bị ảnh hưởng khi xóa cấu hình bảo mật

Một kiểm thử bảo mật đáng tin nên **thất bại nếu bỏ rule bảo vệ**. Ví dụ, nếu xóa `.requestMatchers("/api/admin").hasRole("ADMIN")` mà test vẫn xanh, rất có thể test không chạy filter, chỉ kiểm controller, hoặc không có ca reader bị từ chối. Cần test âm tính để bắt hồi quy về quyền.

## 11. Trình tự chẩn đoán khi test 401/403 bất ngờ

Khi một test trả 401/403 trái mong đợi, làm tuần tự:

1. Kiểm dependencies: `spring-security-test` có trong `testImplementation`/`test` scope và test imports đúng.
2. Xác định loại test: full context, MVC slice, hay MockMvc standalone; **security config nào thực sự được load**?
3. Xem `MockMvc` có chạy `FilterChainProxy` không; bảo đảm không có `addFilters=false`.
4. Xác định URL, HTTP method khớp chain/matcher nào. Với nhiều chains, kiểm `@Order` và `securityMatcher`.
5. Kiểm test principal: `@WithMockUser`/`user(...)` là fake auth, còn `httpBasic(...)` đưa credentials vào provider; `@WithUserDetails` lấy user fixture nhưng không kiểm mật khẩu.
6. Kiểm authority chính xác (`ROLE_ADMIN` khác `ADMIN`), account flags, encoder/provider nếu dùng credentials thật.
7. Với POST/PUT/PATCH/DELETE, kiểm CSRF token theo chính sách của ứng dụng.
8. Với method security, kiểm `@EnableMethodSecurity`, bean proxy và lời gọi service không bị mock/self-invocation bỏ qua.
9. So sánh với một full-context HTTP integration test để phát hiện slice configuration lệch production.
10. Đọc assertion/log có kiểm soát: không log password thô, Bearer token hoặc session secrets.

### Một ma trận test tối thiểu

| Test | Điều phải chứng minh |
| --- | --- |
| Anonymous gọi protected API | Không truy cập được; thường 401 với HTTP Basic/Bearer. |
| Password sai | Provider thực sự từ chối; không dùng `@WithMockUser`. |
| Password đúng | Principal và SecurityContext được thiết lập. |
| Role USER gọi endpoint ADMIN | 403 vì thiếu authority. |
| Role ADMIN gọi endpoint ADMIN | Được phép. |
| POST thiếu/CSRF sai | 403 khi ứng dụng yêu cầu CSRF. |
| POST có CSRF hợp lệ và đủ quyền | Thành công. |
| Public API không credentials | Truy cập được theo chính sách `permitAll`. |
| Phân quyền ở service | `@PreAuthorize` thực sự được áp dụng qua Spring bean proxy nếu dùng method security. |

Chạy cả test **dương tính và âm tính** giúp phân biệt một policy được thực thi đúng với một suite chỉ có các request được phép.

## 12. Bài tập tự kiểm tra

**Tình huống A:** Bạn đã thêm `spring-security-test` nhưng `/api/admin` vẫn trả 200 cho user thường trong test.  
**Phân tích:** dependency không bật rule. Kiểm `@AutoConfigureMockMvc(addFilters=false)`, chain được load, matcher order và liệu test dùng authentication giả không đúng authority.

**Tình huống B:** `@WebMvcTest(ReportController.class)` không khởi động do thiếu bean `PermissionService`.  
**Phân tích:** Slice chỉ nạp MVC layer, còn một collaborator nằm ngoài slice. Mock service để kiểm controller/HTTP boundary, hoặc dùng `@SpringBootTest` nếu mục tiêu là kiểm thực security/service cùng nhau; đừng tự thay rule bằng `permitAll()`.

**Tình huống C:** Một test dùng `@WithMockUser(username="alice", roles="ADMIN")` pass, nhưng gọi HTTP Basic `alice:wrong` vẫn 401.  
**Phân tích:** đúng kỳ vọng: annotation đã giả lập principal, không kiểm password; Basic buộc provider kiểm mật khẩu thật.

**Tình huống D:** POST bằng admin đã xác thực trả 403, GET cùng URL trả 200.  
**Phân tích:** trước hết kiểm CSRF token và method-specific authorization, không tự động kết luận thiếu ADMIN role.

**Tình huống E:** Test dùng `MockMvcBuilders.standaloneSetup(controller).build()` và không hề nhận 401.  
**Phân tích:** chưa tích hợp FilterChainProxy. Chọn WebApplicationContext và `.apply(springSecurity())` hoặc dùng MockMvc do Boot auto-configure.

**Tình huống F:** `@WithUserDetails("reader")` pass nhưng mật khẩu của reader trong database đã đổi mà test không phát hiện.  
**Phân tích:** annotation có tra user nhưng không chạy password comparison; cần test authentication thực bằng credentials để kiểm encoder/provider.

## 13. Checklist trước khi coi kiểm thử bảo mật đạt yêu cầu

- [ ] Đã khai báo `testImplementation 'org.springframework.security:spring-security-test'`, dùng version do Spring Boot quản lý.
- [ ] Đã chọn full-context hay MVC slice đúng mục tiêu.
- [ ] `SecurityFilterChain`/provider/user service đúng với ứng dụng đang được load; không vô tình dùng default chain.
- [ ] `MockMvc` đã tích hợp `FilterChainProxy`; không tắt filters trong test bảo mật.
- [ ] Có ca 401 khi anonymous/password sai và 403 khi thiếu quyền.
- [ ] Có ca dương tính với principal/authority hợp lệ.
- [ ] Test POST kiểm rõ CSRF theo chính sách thực.
- [ ] Test login/provider không chỉ dựa vào `@WithMockUser` hoặc `@WithUserDetails`.
- [ ] Nếu dùng method security, có `@EnableMethodSecurity` và test gọi qua bean proxy thật.
- [ ] Test profile, mocks và các chain không làm thay đổi chính sách cần bảo vệ.
- [ ] Một thay đổi phá rule sẽ khiến ít nhất một test âm tính thất bại.

## 14. Ghi nhớ và tài liệu chính thức

**Hai việc tách biệt nhưng cùng bắt buộc:** (1) `spring-security-test` cung cấp những công cụ giả lập principal/credentials/CSRF và assertion; (2) đúng **Spring test context + filter integration** mới xác nhận ứng dụng thật đang thi hành chính sách. `@SpringBootTest` + `@AutoConfigureMockMvc` thích hợp để kiểm luồng thực; `@WebMvcTest` phù hợp kiểm MVC boundary khi import chính xác SecurityConfig và dependencies cần thiết. Dùng `httpBasic(...)` để thử password/provider; dùng `@WithMockUser` khi chủ ý chỉ thử quyền.

Nguồn đối chiếu:

- [Spring Security — Testing (Servlet)](https://docs.spring.io/spring-security/reference/6.5/servlet/test/index.html)
- [Spring Security — Tích hợp MockMvc](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/)
- [Spring Security — Thiết lập `MockMvc` với `springSecurity()`](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html)
- [Spring Security — CSRF trong MockMvc tests](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [Spring Security — Testing with Mock Users](https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html)
- [Spring Boot — `@WebMvcTest` và MVC test slices](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/web/servlet/WebMvcTest.html)
- [Spring Boot — `@AutoConfigureMockMvc`, `addFilters` mặc định](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/web/servlet/AutoConfigureMockMvc.html)
- [Spring Framework — MockMvc setup options](https://docs.spring.io/spring-framework/reference/testing/mockmvc/setup-options.html)
