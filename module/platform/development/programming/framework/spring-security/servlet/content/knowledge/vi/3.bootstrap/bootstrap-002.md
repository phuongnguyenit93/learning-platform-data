# Các thành phần core, web, config, crypto và spring-security-test trong Spring Security Servlet

Một ứng dụng Spring Security chạy trên Servlet stack không được bảo vệ bởi một thư viện duy nhất theo nghĩa “thêm dependency là hiểu hết mọi thứ”. Spring Security chia trách nhiệm thành nhiều module: **core** mô tả danh tính và quyền; **web** đưa cơ chế bảo mật vào HTTP/Servlet; **config** lắp ghép các cơ chế thành cấu hình; **crypto** cung cấp công cụ bảo vệ mật khẩu và dữ liệu; **spring-security-test** giúp kiểm chứng hành vi. Hiểu ranh giới này giúp chọn đúng dependency, đọc đúng class và chẩn đoán lỗi cấu hình thay vì thử thay đổi ngẫu nhiên.

Bài học đặt trong phạm vi **Spring Security Servlet, Java 17+ và Spring Boot 3.x/Spring Security 6.x**. Những ví dụ bên dưới dùng Spring Boot 3.3.5; khi sử dụng nhánh Boot khác, hãy để BOM của Boot quản lý các phiên bản Spring Security tương thích, và kiểm tra thay đổi API theo phiên bản đó.

## 1. Bản đồ năm module

| Maven/Gradle artifact | Trách nhiệm chính | Các API/class tiêu biểu | Có mặt ở đâu? |
| --- | --- | --- | --- |
| `org.springframework.security:spring-security-core` | Mô hình xác thực, người dùng, quyền, ngữ cảnh bảo mật và các contract dùng chung | `Authentication`, `GrantedAuthority`, `SecurityContext`, `SecurityContextHolder`, `AuthenticationManager`, `UserDetails`, `UserDetailsService` | Runtime |
| `org.springframework.security:spring-security-web` | Tích hợp **HTTP Servlet**, chuỗi filter, bảo vệ request, session, CSRF và xử lý nhánh lỗi HTTP | `FilterChainProxy`, `SecurityFilterChain`, `BasicAuthenticationFilter`, `CsrfFilter`, `AuthorizationFilter`, `ExceptionTranslationFilter` | Runtime của ứng dụng Servlet |
| `org.springframework.security:spring-security-config` | Cấu hình Java/DSL, xây dựng filter chain và tích hợp các thành phần authentication/authorization | `HttpSecurity`, `@EnableWebSecurity`, `@EnableMethodSecurity`, `Customizer` | Runtime nếu cấu hình qua các API này |
| `org.springframework.security:spring-security-crypto` | API mã hóa, hash và kiểm tra mật khẩu; các tiện ích crypto riêng biệt | `PasswordEncoder`, `BCryptPasswordEncoder`, `DelegatingPasswordEncoder`, `PasswordEncoderFactories` | Runtime khi xác thực mật khẩu hoặc dùng crypto |
| `org.springframework.security:spring-security-test` | Hỗ trợ giả lập người dùng, thêm credentials/CSRF cho request test, tích hợp Spring Test/MockMvc | `@WithMockUser`, `@WithUserDetails`, `SecurityMockMvcRequestPostProcessors.user`, `httpBasic`, `csrf`, `springSecurity()` | **Chỉ test** (Gradle `testImplementation`/Maven `test`) |

Đây là **artifact/module**, không phải năm tầng request độc lập. Một module có nhiều package; tên package thường gợi ý trách nhiệm, nhưng cần kiểm tra dependency thực tế thay vì đoán class nằm trong JAR nào.

Sơ đồ ý nghĩa khi dùng Spring Boot Servlet:

~~~text
spring-boot-starter-web                 spring-boot-starter-security
  -> Spring MVC + Servlet container       -> các thư viện Spring Security runtime
                                             core / web / config / crypto
                  |                                    |
                  +-------------- ứng dụng ------------+
                                      |
                         SecurityFilterChain bean
                                      |
                     Servlet security filters + controller

testImplementation spring-boot-starter-test
testImplementation spring-security-test
                 -> JUnit + MockMvc + công cụ security test
~~~

Hai starter của Boot và artifact riêng có vai trò khác nhau:

- `spring-boot-starter-web` tạo nền Servlet/Spring MVC. Nó **không tự cấp khả năng bảo vệ HTTP bằng Spring Security**.
- `spring-boot-starter-security` đưa các module runtime cần thiết vào classpath và kích hoạt auto-configuration bảo mật của Boot. Trong ứng dụng Boot thông thường, không cần tự kê riêng bốn artifact `core/web/config/crypto`; hãy xem dependency graph để biết phiên bản đã được chọn.
- `spring-security-test` **không tự được thêm** chỉ vì có starter security. Cần khai báo riêng cho test.
- Các thành phần OAuth2 login, OAuth2 resource server, SAML2… thuộc những artifact chuyên biệt khác. Không suy luận “có core/web/config là tự có mọi cơ chế xác thực”.

Điểm cần nhớ: **module** trả lời “thư viện chịu trách nhiệm gì?”, còn **bean/filter** trả lời “tại runtime request chạy qua thành phần nào?”. Hai câu hỏi này bổ sung cho nhau.

## 2. `spring-security-core`: danh tính, quyền và ngữ cảnh

### 2.1. Các contract cơ bản

`Authentication` đại diện thông tin xác thực trong Spring Security. Nó có thể chứa principal, credentials, authorities, details và trạng thái `isAuthenticated()`. Trong quá trình xác thực, một `Authentication` ban đầu có thể chứa credentials chưa được kiểm chứng; sau khi thành công, `AuthenticationManager` trả về kết quả đã xác thực. Vì vậy **không coi chỉ cần có đối tượng Authentication là chắc chắn đã đăng nhập thành công**.

`GrantedAuthority` biểu diễn quyền dưới dạng giá trị mà chính sách bảo mật hiểu được, thường là chuỗi như `ROLE_READER` hoặc `REPORT_VIEW`. “Role” là một quy ước phổ biến trên authority: `hasRole("ADMIN")` thường kiểm tra `ROLE_ADMIN`, còn `hasAuthority("ADMIN")` kiểm tra đúng chuỗi `ADMIN`. Quy ước tiền tố có thể được tùy chỉnh; bài này dùng mặc định.

`SecurityContext` chứa Authentication hiện tại; `SecurityContextHolder` là điểm truy cập thông dụng tới context trong luồng xử lý hiện tại. Trong ứng dụng Servlet, các filter quản lý việc thiết lập và dọn context ở các ranh giới request phù hợp. Không nên dựa vào giả định “ThreadLocal tự đi theo tất cả thread”, nhất là khi dùng `@Async`, executor hoặc background task.

`AuthenticationManager` nhận yêu cầu xác thực và trả kết quả hoặc ném lỗi; `AuthenticationProvider` là chiến lược có thể xác thực một loại token. Với username/password, `UserDetailsService` cung cấp dữ liệu người dùng cho luồng xác thực phù hợp, còn `PasswordEncoder` kiểm tra mật khẩu đã nhập với chuỗi hash được lưu.

### 2.2. Core **không đồng nghĩa** tự chặn HTTP

Chỉ có interface `Authentication` hoặc `UserDetailsService` trong classpath chưa đủ để bảo vệ `GET /admin`. Việc nối authentication với Servlet request nằm ở **web**, còn quy tắc truy cập URL thường được khai báo qua **config**.

Một cách định vị lớp khi đọc code:

| Khi cần biết... | Bắt đầu từ |
| --- | --- |
| Người gọi được biểu diễn bởi object nào? | `Authentication`, `getPrincipal()` |
| Người gọi có quyền nào? | `getAuthorities()`, `GrantedAuthority` |
| Context hiện tại ở đâu? | `SecurityContextHolder` |
| Credentials được kiểm chứng ra sao? | `AuthenticationManager`, `AuthenticationProvider` |
| User được nạp từ đâu? | `UserDetailsService` và nguồn dữ liệu do ứng dụng triển khai |
| URL bị chặn ở bước nào? | Sang module `web` và cấu hình `SecurityFilterChain` |

**Lưu ý:** `UserDetailsService.loadUserByUsername()` không phải một HTTP controller và không tự ra quyết định truy cập URL; nó là nguồn dữ liệu cho một cơ chế authentication.

## 3. `spring-security-web`: điểm chặn request Servlet

Spring MVC request đi qua Servlet filter chain trước khi tới `DispatcherServlet`. Spring Security sử dụng `DelegatingFilterProxy` để kết nối filter chain của Servlet container với bean Spring thường mang tên `springSecurityFilterChain`, do `FilterChainProxy` quản lý.

`FilterChainProxy` chọn `SecurityFilterChain` phù hợp request. Một ứng dụng có thể khai báo nhiều chain cho `/api/**` và trang web khác; **chain được chọn** phụ thuộc matcher và thứ tự chain. Filter cụ thể tùy cơ chế bảo mật được bật, không có một thứ tự cố định áp dụng cho mọi dự án.

~~~text
HTTP request
    |
Servlet filter chain
    |
DelegatingFilterProxy
    |
FilterChainProxy
    |
SecurityFilterChain khớp request
    |-- xử lý SecurityContext
    |-- filter xác thực (nếu cơ chế tương ứng được bật)
    |-- kiểm tra CSRF khi áp dụng
    |-- đánh giá authorization
    |-- exception translation / entry point / access denied handler
    |
    +--> cho qua -> DispatcherServlet -> controller
    |
    +--> từ chối -> 401 / 403 / redirect ... tùy tình huống
~~~

Ví dụ các nhiệm vụ thuộc web:

- `BasicAuthenticationFilter` có thể đọc header `Authorization: Basic ...`, tạo authentication request và gọi tầng xác thực. Không phải mọi ứng dụng đều dùng HTTP Basic.
- `AuthorizationFilter` áp dụng authorization rule đã cấu hình.
- `CsrfFilter` xử lý bảo vệ CSRF khi enabled và request thuộc phạm vi kiểm tra.
- `ExceptionTranslationFilter` liên kết một số lỗi authentication/authorization với entry point hoặc access-denied handler. Một số filter xác thực cũng có thể gọi entry point trực tiếp.
- Các thành phần xử lý session và SecurityContext phụ thuộc cấu hình; không coi header HTTP Basic là bằng chứng ứng dụng đã tắt session.

**401 khác 403:** request chưa xác thực có thể nhận challenge 401 khi dùng Basic; request đã xác thực nhưng thiếu quyền thường nhận 403. Request POST thiếu CSRF token cũng có thể bị 403. Với form login, entry point có thể trả 302. Luôn đối chiếu cơ chế đang bật.

## 4. `spring-security-config`: khai báo chính sách và lắp ghép module

Thay vì tự tạo và sắp xếp tất cả Servlet filter, ứng dụng thường khai báo một bean `SecurityFilterChain` và cấu hình qua `HttpSecurity`. Đây là API thuộc `spring-security-config`; bean được tạo sẽ sử dụng các component trong `web` và `core`.

Ví dụ cấu hình tối thiểu sau minh họa **hình dạng** DSL, chưa phải ứng dụng chạy độc lập:

~~~java
@Bean
SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public").permitAll()
            .requestMatchers("/admin").hasRole("ADMIN")
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Cần phân biệt:

- `requestMatchers("/public")` chỉ chọn request để áp dụng **rule authorization**, không phải chọn security chain nào. Khi có nhiều chain, `securityMatcher(...)` ở cấp `HttpSecurity` và thứ tự `@Order` là vấn đề riêng.
- `permitAll()` cho phép một URL theo chính sách này; nó không bỏ qua toàn bộ security filters.
- `hasRole("ADMIN")` đòi authority `ROLE_ADMIN` theo quy ước mặc định.
- `anyRequest().authenticated()` đặt cuối như fallback; thứ tự rule có ý nghĩa.
- `httpBasic(...)` bật HTTP Basic. Nếu không bật form login thì không nên giả định trình duyệt luôn được redirect tới login page.
- `http.build()` xây dựng filter chain. Nó không phải lệnh xử lý một request ngay lập tức.

Trong ứng dụng Spring Boot 3.x Servlet, định nghĩa `SecurityFilterChain` dạng `@Bean` là cách phổ biến để thay thế chính sách web security mặc định của Boot. `@EnableWebSecurity` hữu ích trong cấu hình Spring Security thuần, nhưng không cần thêm như một nghi thức bắt buộc vào mọi ứng dụng Boot. `@EnableMethodSecurity` bật khả năng dùng annotation như `@PreAuthorize` ở tầng method; đó là cơ chế bổ sung, không phải điều kiện để `authorizeHttpRequests` hoạt động.

## 5. `spring-security-crypto`: xử lý mật khẩu có chủ đích

`PasswordEncoder` cung cấp hai thao tác quan trọng: `encode(rawPassword)` để tạo giá trị lưu và `matches(rawPassword, encodedPassword)` để đối chiếu. Đừng so sánh chuỗi mật khẩu đã mã hóa bằng cách tự `equals(encode(raw))`: các thuật toán có salt như BCrypt thường cho hash khác nhau mỗi lần encode cùng mật khẩu.

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder();

String stored = encoder.encode("example-password");
boolean accepted = encoder.matches("example-password", stored);
boolean rejected = encoder.matches("wrong-password", stored);

System.out.println(accepted);
System.out.println(rejected);
~~~

Đoạn trên là **mảnh code minh họa** cần import `org.springframework.security.crypto.password.PasswordEncoder` và `org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder`, đặt trong một phương thức. Hai dòng kết quả luôn là:

~~~text
true
false
~~~

`stored` là chuỗi hash có salt, **không cố định giữa các lần chạy** nên không đưa một hash mẫu vào kiểm tra bằng `assertEquals`. `BCryptPasswordEncoder` là lựa chọn minh họa có sẵn; thuật toán và work factor trong sản phẩm thực phải được chọn theo chính sách bảo mật và năng lực máy chủ.

`DelegatingPasswordEncoder` hỗ trợ phân biệt nhiều thuật toán bằng tiền tố có định dạng như `{bcrypt}...`, tùy encoder id được cấu hình. `PasswordEncoderFactories.createDelegatingPasswordEncoder()` cung cấp một tập encoder được đăng ký sẵn. Khi đổi encoder, không nên chỉ đổi bean rồi giả định toàn bộ hash cũ lập tức tương thích: cần xem định dạng lưu, migration và cách xác nhận mật khẩu.

**Không dùng** mật khẩu plaintext, `NoOpPasswordEncoder` hoặc credential cố định trong cấu hình triển khai thực tế. Ví dụ user trong bộ nhớ ở phần sau chỉ dành cho máy học/tự kiểm thử.

## 6. `spring-security-test`: kiểm thử quy tắc, danh tính và cơ chế xác thực

Test không chỉ kiểm tra controller trả nội dung đúng; với endpoint được bảo vệ, cần chứng minh cả **request bị từ chối đúng lúc** và **request hợp lệ đi qua đúng chính sách**. `spring-security-test` hỗ trợ hai nhóm test khác mục tiêu:

1. **Giả lập SecurityContext:** `@WithMockUser` hoặc `.with(user(...))` tạo danh tính test với authorities mong muốn. Cách này kiểm tra authorization và hành vi controller, **không chứng minh password thật đã được kiểm tra**.
2. **Gửi credentials theo giao thức:** `.with(httpBasic("reader","reader-pass"))` đặt header HTTP Basic để bộ lọc và AuthenticationProvider của ứng dụng xử lý. Cách này có thể kiểm chứng luồng xác thực thật trong ngữ cảnh MockMvc.
3. **Mô phỏng CSRF:** `.with(csrf())` cung cấp CSRF token hợp lệ cho request test; kiểm chứng cả trường hợp không có token để tránh vô tình bỏ bảo vệ.
4. **Tích hợp filter chain:** dùng Spring Test/MockMvc có cấu hình Spring Security, ví dụ Boot `@SpringBootTest` + `@AutoConfigureMockMvc`, hoặc cấu hình `springSecurity()` với MockMvc tự dựng. Nếu quên áp dụng security filters, test có thể trả 200 giả dù runtime trả 401/403.

`@WithMockUser` không yêu cầu username tồn tại trong database/in-memory store. Đó là lợi ích để test authorization độc lập, đồng thời là giới hạn khi bạn cần test password encoder hoặc authentication provider.

## 7. Ví dụ chạy được bằng Java 17, Spring Boot 3.x và MockMvc

Ví dụ dưới đây tách class theo đúng trách nhiệm: application khởi động; config tạo SecurityFilterChain/user/encoder; controller phục vụ HTTP; test thực thi request bằng MockMvc. Nó giúp kiểm tra **cả năm module** trong một ứng dụng nhỏ.

### 7.1. Cấu trúc dự án

~~~text
security-modules-demo/
├── build.gradle
├── settings.gradle
└── src/
    ├── main/java/demo/security/
    │   ├── SecurityModulesApplication.java
    │   ├── SecurityConfiguration.java
    │   └── DemoController.java
    └── test/java/demo/security/
        └── SecurityModulesApplicationTests.java
~~~

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'security-modules-demo'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

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
~~~

**Tại sao không khai báo phiên bản cho từng artifact Spring Security?** Plugin dependency-management nhập BOM phù hợp với phiên bản Boot, nên Boot chọn các phiên bản security tương thích. Ép riêng version cho `spring-security-core` trong khi `web/config/crypto` vẫn theo BOM có thể tạo classpath không nhất quán. Khi dùng dự án có version catalog hoặc Gradle platform khác, giữ nguyên nguyên tắc đồng bộ phiên bản.

Tệp `src/main/java/demo/security/SecurityModulesApplication.java`:

~~~java
package demo.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityModulesApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityModulesApplication.class, args);
    }
}
~~~

Tệp `src/main/java/demo/security/SecurityConfiguration.java`:

~~~java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }
}
~~~

Tệp `src/main/java/demo/security/DemoController.java`:

~~~java
package demo.security;

import java.security.Principal;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicMessage() {
        return "public";
    }

    @GetMapping("/me")
    public String currentUser(Principal principal) {
        return "hello " + principal.getName();
    }

    @GetMapping("/admin")
    public String adminArea() {
        return "admin area";
    }

    @PostMapping("/notes")
    public String createNote() {
        return "created";
    }
}
~~~

Giải thích đường đi:

- `/public`: `permitAll`, không cần credentials.
- `/me`: theo `anyRequest().authenticated()`, cần đăng nhập; khi hợp lệ controller đọc `Principal`.
- `/admin`: cần authority `ROLE_ADMIN`; `reader` chỉ có `ROLE_READER`.
- `POST /notes`: cần xác thực **và** mặc định chịu CSRF protection. Đăng nhập đúng qua Basic nhưng không gửi CSRF token vẫn có thể nhận 403; đừng vội quy lỗi cho `hasRole`.
- Mật khẩu được hash bằng `BCryptPasswordEncoder` khi bean user store được tạo. Bài này không sử dụng database, OAuth2 hoặc API token; chúng là những lựa chọn khác cho bài nâng cao.

### 7.2. Kiểm thử đủ cả nhánh cho phép và từ chối

Tệp `src/test/java/demo/security/SecurityModulesApplicationTests.java`:

~~~java
package demo.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.security.test.context.support.WithMockUser;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityModulesApplicationTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publicEndpointDoesNotRequireCredentials() throws Exception {
        mockMvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void privateEndpointRequiresAuthentication() throws Exception {
        mockMvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validBasicCredentialsAreAuthenticated() throws Exception {
        mockMvc.perform(get("/me").with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello reader"));
    }

    @Test
    void wrongPasswordIsRejected() throws Exception {
        mockMvc.perform(get("/me").with(httpBasic("reader", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedReaderCannotAccessAdmin() throws Exception {
        mockMvc.perform(get("/admin").with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void syntheticAdminIdentityCanPassAuthorization() throws Exception {
        mockMvc.perform(get("/admin").with(user("mock-admin").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin area"));
    }

    @Test
    @WithMockUser(username = "simulated-reader", roles = "READER")
    void annotationInjectsTestIdentity() throws Exception {
        mockMvc.perform(get("/me"))
            .andExpect(status().isOk())
            .andExpect(content().string("hello simulated-reader"));
    }

    @Test
    void csrfProtectionAppliesToStateChangingRequests() throws Exception {
        mockMvc.perform(post("/notes").with(user("reader")))
            .andExpect(status().isForbidden());

        mockMvc.perform(post("/notes").with(user("reader")).with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("created"));
    }
}
~~~

Mỗi test kiểm tra một contract cụ thể:

| Test | Thành phần được quan sát | Điều chứng minh được |
| --- | --- | --- |
| `publicEndpointDoesNotRequireCredentials` | Config + web | URL public qua policy đúng. |
| `privateEndpointRequiresAuthentication` | Web/filter entry point | Khách chưa đăng nhập không vào endpoint riêng. |
| `validBasicCredentialsAreAuthenticated` | Web + core + crypto | Header Basic đi qua authentication thật, mật khẩu đúng được chấp nhận. |
| `wrongPasswordIsRejected` | Core + crypto + web | Sai mật khẩu bị từ chối. |
| `authenticatedReaderCannotAccessAdmin` | Core authority + config + web | Authentication đúng chưa đồng nghĩa có đủ quyền. |
| `syntheticAdminIdentityCanPassAuthorization` | Security test + config | Identity giả lập đủ `ROLE_ADMIN` đi qua rule, **không test password**. |
| `annotationInjectsTestIdentity` | `@WithMockUser` + security test | Có thể test controller với principal test mà không dùng database. |
| `csrfProtectionAppliesToStateChangingRequests` | Web CSRF + security test | POST không token bị chặn, có token hợp lệ được phép. |

Trong test dùng `@AutoConfigureMockMvc`, Spring Boot tích hợp security filters vào MockMvc theo cấu hình mặc định. Nếu tự `MockMvcBuilders.webAppContextSetup(context).build()`, cần đảm bảo thêm `.apply(springSecurity())`; thiếu bước này có thể khiến test không phản ánh hành vi bảo vệ HTTP thật.

Test trong `spring-security-test` là công cụ **tạo điều kiện kiểm thử và assertion**, không được phụ thuộc vào artifact này ở `implementation` của ứng dụng production.

### 7.3. Cách chạy và kết quả mong đợi

Với dự án đã có Gradle wrapper, chạy:

~~~bash
./gradlew test
./gradlew bootRun
~~~

Trên Windows sử dụng `gradlew.bat test` và `gradlew.bat bootRun`. Nếu mới tạo các tệp theo ví dụ mà chưa có wrapper, có thể chạy `gradle test` / `gradle bootRun` với Gradle tương thích đã cài, hoặc tạo wrapper trước. Đây là ví dụ dùng thư viện Spring, nên `javac`/`java` trực tiếp không đủ nếu chưa thiết lập classpath.

Khi ứng dụng khởi động thành công (cổng mặc định 8080), mở terminal khác:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u reader:reader-pass http://localhost:8080/me
curl -i -u reader:reader-pass http://localhost:8080/admin
curl -i -u admin:admin-pass http://localhost:8080/admin
curl -i -u reader:reader-pass -X POST http://localhost:8080/notes
~~~

Kết quả kiểm tra chính; thứ tự/giá trị header có thể khác theo môi trường:

| Request | Status dự kiến | Body khi thành công |
| --- | --- | --- |
| GET `/public` không auth | 200 | `public` |
| GET `/me` không auth | 401 | Không yêu cầu body cụ thể |
| GET `/me` với `reader` đúng mật khẩu | 200 | `hello reader` |
| GET `/admin` với `reader` | 403 | Không yêu cầu body cụ thể |
| GET `/admin` với `admin` đúng mật khẩu | 200 | `admin area` |
| POST `/notes` với Basic hợp lệ, **không có CSRF token** | 403 | Không yêu cầu body cụ thể |

Lệnh POST cuối cố ý mô tả **CSRF được giữ bật mặc định**; ví dụ không cung cấp HTTP endpoint lấy CSRF token, nên dùng test MockMvc `.with(csrf())` để kiểm chứng nhánh thành công. Không tự tắt CSRF chỉ để lệnh POST thử nghiệm trả 200. Với ứng dụng API thuần token không dùng cookie/session, quyết định bật/tắt CSRF cần dựa trên mô hình xác thực và threat model thực tế.

## 8. Quan sát dependency graph: kiểm tra module nào thật sự đã nạp

Không nhất thiết phải mở từng JAR. Gradle trả lời trực tiếp module có xuất hiện trên classpath không:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-security-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-test --configuration testRuntimeClasspath
~~~

Tại `runtimeClasspath`, tìm `spring-security-core`, `spring-security-web`, `spring-security-config` và `spring-security-crypto`; tại `testRuntimeClasspath` tìm thêm `spring-security-test`. Dùng `dependencyInsight` để biết **vì sao** một module được chọn và phiên bản nào thực tế được resolve.

Lệnh `dependencies` cho bạn **graph**, không trực tiếp chứng minh Spring đã đăng ký đúng bean hay request đã đi qua filter nào. Muốn trả lời runtime, hãy tiếp tục kiểm tra bean `SecurityFilterChain` và dùng test HTTP.

Một cách truy vết khi lỗi:

1. Lỗi `ClassNotFoundException`/`NoClassDefFoundError` ở `org.springframework.security...`: xác định module chứa class, classpath compile/runtime và version skew.
2. Lỗi khi khởi tạo `SecurityFilterChain`: kiểm tra bean/config và policy khai báo qua `HttpSecurity`; không vội bổ sung `spring-security-test` vào runtime.
3. Password luôn bị từ chối: kiểm tra `PasswordEncoder.matches`, dạng hash lưu và encoder được inject. Không so sánh hash BCrypt bằng chuỗi cố định.
4. Test `@WithMockUser` chạy nhưng Basic thật trả 401: kiểm tra user store, provider và password; test giả lập identity không xác minh đường đi credentials.
5. `/admin` trả 403 dù user đã đăng nhập: đọc authorities và rule. `ROLE_ADMIN` khác `ROLE_READER`; 403 cũng có thể do CSRF trên request thay đổi trạng thái.
6. Test trả 200 trong khi chạy thật bị 401: kiểm tra MockMvc đã áp dụng security filter chain chưa.
7. Nhiều `SecurityFilterChain`: kiểm tra `securityMatcher`, `@Order` và request nào khớp chain đầu tiên. `requestMatchers` nội bộ không quyết định chain nào được chọn.

## 9. Khi nào cần thêm hoặc thay module?

| Nhu cầu | Module/cấu hình cần xem |
| --- | --- |
| Chỉ cần dùng các type như `Authentication` trong một thư viện chung | `core` phù hợp về API; chưa phải HTTP security |
| Muốn bảo vệ Spring MVC endpoint chạy trên Servlet container | `web` + `config` + các thành phần authentication/crypto cần thiết |
| Muốn viết bean policy bằng `HttpSecurity` | `config` |
| Muốn hash và kiểm tra mật khẩu | `crypto` |
| Muốn test Spring Security bằng MockMvc/annotations | `spring-security-test` ở test scope |
| Muốn nhận bearer JWT như resource server | Tìm artifact chuyên biệt như `spring-boot-starter-oauth2-resource-server`, ngoài phạm vi năm module cơ bản |
| Dự án Spring WebFlux reactive | Dùng các API/filter dành cho reactive (ví dụ `SecurityWebFilterChain`); không đem Servlet `HttpSecurity` và `FilterChainProxy` áp dụng nguyên xi |

Ở **Spring Boot Servlet**, bắt đầu từ starter Web + Security + test là đơn giản và ổn định. Ở Spring Framework thuần không dùng Boot, bạn cần tự khai báo dependencies phù hợp và cấu hình việc đăng ký `DelegatingFilterProxy`/Spring Security với Servlet context. Việc có các JAR trong classpath một mình không thay thế bước tích hợp request filter vào container.

Để cập nhật version, ưu tiên quản lý version tập trung qua Spring Boot BOM hoặc cơ chế tương đương, rồi chạy test bao gồm cả 401/403 và xác thực mật khẩu. Đừng nâng riêng một module runtime khi các module khác vẫn bị khóa tại version không tương thích.

## 10. Bài tập tự kiểm tra

1. Chỉ vào các import trong `SecurityConfiguration.java` và phân loại từng class thuộc `core`, `web`, `config` hoặc `crypto`. Giải thích tại sao một bean cấu hình có thể dùng type của nhiều artifact.
2. Bỏ khai báo `spring-security-test` khỏi `testImplementation` (chỉ trong bản thử nghiệm), chạy compile test và ghi lại import nào không thể resolve; sau đó phục hồi dependency. Vì sao runtime application vẫn có thể chạy bình thường?
3. Đổi role của `reader` từ `READER` thành `ADMIN`, chạy lại test phân quyền: test nào phải thay đổi kỳ vọng và vì sao? Không để test cũ giả định reader mãi thiếu quyền.
4. So sánh hai test `.with(user("reader"))` và `.with(httpBasic("reader","reader-pass"))`: test nào đi qua password authentication của ứng dụng, test nào chỉ tạo principal?
5. Với POST `/notes`, dự đoán response khi (a) không đăng nhập, (b) đăng nhập đúng nhưng thiếu CSRF token, (c) dùng mock user cùng CSRF token trong MockMvc. Xác minh thực tế, lưu ý một request có thể bị filter CSRF từ chối trước khi tới bước trả challenge đăng nhập.
6. Dùng `dependencyInsight` xác nhận phiên bản được chọn cho `spring-security-core` và nguồn dependency đã kéo module đó vào.
7. Giải thích vì sao classpath đã có `spring-security-web` chưa tự chứng minh `/admin` được bảo vệ: cần xem bean `SecurityFilterChain`, matcher và tích hợp Servlet filter.
8. Nếu sau này thêm OAuth2/JWT hoặc method security, cho biết phần module nào vẫn giữ vai trò cốt lõi và phần nào được mở rộng.

**Tóm lại về trách nhiệm kỹ thuật:** `core` định nghĩa *ai và có quyền gì*; `web` đưa xử lý vào *request Servlet*; `config` quyết định *lắp ghép và chính sách*; `crypto` hỗ trợ *kiểm chứng bí mật an toàn*; `spring-security-test` giúp *chứng minh hành vi bằng test*. Đọc đúng ranh giới này sẽ giúp bạn lựa chọn dependency có chủ đích, tránh nhầm lẫn giữa lỗi classpath, authentication, authorization và cấu hình test.
