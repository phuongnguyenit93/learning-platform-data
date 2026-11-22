# Tích hợp spring-security-test với MockMvc hoặc WebTestClient

## 1. Mục tiêu: kiểm thử đăng nhập và ranh giới bảo mật, không chỉ HTTP status

Trong ứng dụng Java/Spring Boot, kiểm thử endpoint trả về `200 OK` chưa chứng minh xác thực hay phân quyền đang đúng. Một controller có thể trả nội dung hợp lệ trong test vì security filters đã bị bỏ qua; một request có principal giả lập có thể được cho phép dù password encoder, authentication provider hoặc token decoder bị cấu hình sai.

**`spring-security-test`** cung cấp công cụ gắn Spring Security vào các bài test HTTP và tạo ngữ cảnh bảo mật theo cách có kiểm soát. Hai nhánh phổ biến:

- **`MockMvc`**: dành cho Spring MVC/Servlet stack; tích hợp Spring Security filter chain qua `springSecurity()` hoặc `@AutoConfigureMockMvc` có bật filters.
- **`WebTestClient`**: có thể kiểm thử HTTP theo phong cách reactive; trong ứng dụng **Spring WebFlux**, áp `SecurityMockServerConfigurers.springSecurity()` và các `mockUser()`, `mockJwt()`, `csrf()` reactive. Spring Framework cũng có adapter WebTestClient để kiểm thử MVC; **không được nhầm adapter MVC với security mutator của WebFlux**.

Bài học tập trung vào **đăng nhập thật, người dùng giả lập, anonymous/forbidden, CSRF, role/authority, JWT/OIDC testing và lựa chọn đúng test layer**.

Mục tiêu sau bài học: bạn tự viết được test chứng minh `formLogin()` thực sự gọi authentication provider, trong khi `user()` hoặc `@WithMockUser` chỉ tạo sẵn authentication để kiểm tra **authorization**, và biết khi nào cần test JWT signature/issuer/audience bằng decoder thật thay vì `jwt()` mock.

## 2. Tách các lớp kiểm thử để biết test đang chứng minh điều gì

| Lớp test | Công cụ | Điều được xác nhận | Điều KHÔNG tự được chứng minh |
|---|---|---|---|
| Unit test logic nhỏ | JUnit 5, Mockito | Một hàm/validator/service với dependency giả. | SecurityFilterChain, request parsing, session/CSRF. |
| Controller + security slice | `@WebMvcTest`, `MockMvc`, `spring-security-test` | Mapping MVC, filter chain được import, role/CSRF theo config test. | Mọi DB/provider/IdP production nếu chúng được mock. |
| Servlet security integration | `@SpringBootTest` + `@AutoConfigureMockMvc` | Nhiều bean ứng dụng cùng security chain, form login và handlers thật trong test context. | Hạ tầng bên ngoài hoặc production reverse proxy. |
| Reactive web security integration | `WebTestClient.bindToApplicationContext` + `springSecurity()` | `SecurityWebFilterChain` WebFlux, reactive principal, CSRF và route policy. | MVC servlet filter hoặc production gateway. |
| Live-server HTTP integration | `WebTestClient.bindToServer` / TestRestTemplate | HTTP behavior qua cổng thật, cookie, redirects, headers theo môi trường test. | Giao thức bên thứ ba nếu vẫn mock. |
| Real OAuth/JWT integration | decoder/introspection/IdP test fixture | Chữ ký, issuer, audience, expiry, mapping claims và failure path. | Không thể đạt bằng `jwt()` mock một mình. |

**Nguyên tắc đặt tên test:** `withMockUserCanRead` không phải `passwordLoginWorks`. Tên test nên nói chính xác đường nào được thực thi.

### Sơ đồ ranh giới

~~~text
MockMvc (Servlet)
   |
   +-- MockHttpServletRequest
   +-- FilterChainProxy / SecurityFilterChain
   +-- UsernamePasswordAuthenticationFilter
   +-- AuthenticationManager / UserDetailsService / PasswordEncoder
   +-- Spring MVC Controller
   +-- MockHttpServletResponse

WebTestClient (WebFlux security)
   |
   +-- MockServerWebExchange
   +-- SecurityWebFilterChain
   +-- ReactiveAuthenticationManager / reactive auth providers
   +-- WebFlux Handler / Controller
   +-- Flux/Mono response verification
~~~

`MockMvc` không tạo TCP socket; nó đưa mock servlet request qua Spring MVC infrastructure. `WebTestClient` có thể bind trực tiếp context/controller mà không cần socket hoặc bind vào server thật; **kiểu binding quyết định những phần hạ tầng được chạy**.

## 3. Dependency: những thư viện cần có

Với Spring Boot 3.x / Spring Security 6.x và Java 17+, sử dụng Spring Boot dependency management để không lệch phiên bản Spring/Security giữa runtime và test.

Maven dependencies cho dự án **Servlet Spring MVC**:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
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
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

**`spring-boot-starter-test` không nên được coi là thay cho `spring-security-test`**. Starter test bổ sung JUnit, AssertJ, Mockito, Spring Test; security-test mang các request post-processors, result matchers, annotations và reactive test configurers.

Tương đương Gradle Groovy:

~~~groovy
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

Với **WebFlux** thay starter web bằng `spring-boot-starter-webflux`, vẫn thêm starter security, starter test và `spring-security-test`. Không đặt servlet và reactive starters cùng nhau chỉ vì muốn dùng hai test APIs; mặc định Spring Boot có thể chọn MVC nếu cả hai có mặt. Hãy xác định **ứng dụng thật là MVC hay WebFlux** trước.

Nếu dự án dùng Spring Security 7/Spring Boot 4, kiểm tra tài liệu đúng phiên bản, package/API và module mới; các ví dụ ở đây bám đường API quen thuộc của Spring Boot 3.x/Security 6.x.

## 4. Chọn MockMvc hay WebTestClient theo runtime thật

| Câu hỏi | Nên chọn |
|---|---|
| App dùng `spring-boot-starter-web`, servlet filters, Spring MVC controllers? | **MockMvc** + servlet `springSecurity()`. |
| App dùng `spring-boot-starter-webflux`, `SecurityWebFilterChain`? | **WebTestClient** + reactive `springSecurity()`. |
| Muốn gọi API qua HTTP thật, cookie/redirect/network boundary? | `WebTestClient.bindToServer()` hoặc client HTTP test khác. |
| Muốn test controller MVC nhưng thích API fluent của WebTestClient? | Spring Framework hỗ trợ `MockMvcWebTestClient` adapter; **security vẫn là servlet**. |
| Muốn kiểm tra username/password thực sự qua provider? | Gửi HTTP form login/basic auth thật, không dùng `user()`/`mockUser()`. |
| Muốn tập trung vào quyền endpoint với principal/scope đã có? | `user()`, `@WithMockUser`, `jwt()` / `mockJwt()` thích hợp. |
| Muốn kiểm tra chữ ký JWT, `aud`, `iss`, `exp`? | Test `JwtDecoder`/resource server với token ký thật hoặc fake server có chủ đích. |

`MockMvc` và reactive `WebTestClient` đều có thể kiểm thử bảo mật tốt, nhưng **API test helper không biến Servlet runtime thành Reactor/WebFlux hoặc ngược lại**.

## 5. Setup MockMvc để chạy Spring Security filters thật

Tài liệu Spring Security hướng dẫn:

~~~java
import static org.springframework.security.test.web.servlet.setup
        .SecurityMockMvcConfigurers.springSecurity;

@BeforeEach
void setUp() {
    mvc = MockMvcBuilders
            .webAppContextSetup(webApplicationContext)
            .apply(springSecurity())
            .build();
}
~~~

Các imports bổ sung: `org.springframework.test.web.servlet.setup.MockMvcBuilders`, `org.springframework.web.context.WebApplicationContext` và JUnit `@BeforeEach`. Code là snippet trong test class có field `webApplicationContext`.

`springSecurity()` tích hợp `FilterChainProxy` và post-processor của test context để các `RequestPostProcessor`, `@WithMockUser` được áp đúng khi dùng MockMvc. Trong Spring Boot, `@AutoConfigureMockMvc` với mặc định **có filters** thường tự cung cấp `MockMvc` phù hợp.

**Anti-pattern:**

~~~java
// Dễ tạo false positive nếu bạn tưởng đã test security filters:
MockMvc mvc = MockMvcBuilders
        .standaloneSetup(new DemoController())
        .build();
~~~

Cách trên chủ yếu dựng controller đơn lẻ; nếu không add filter chain/security test support, `/admin` có thể trả `200` dù production yêu cầu admin. Tương tự, `@AutoConfigureMockMvc(addFilters = false)` vô hiệu việc đăng ký servlet filters vào MockMvc test, nên không thể dùng kết quả để tuyên bố SecurityFilterChain đã được bảo vệ.

Dùng `@WebMvcTest` khi muốn slice nhỏ và import cấu hình security cần kiểm thử; dùng `@SpringBootTest` nếu muốn kiểm chứng nhiều bean/provider liên quan và tránh việc test slice bị khác production.

## 6. Một dự án Maven Spring Boot 3 + Java 17 có thể chạy thử

Để tránh ví dụ chỉ là pseudocode, phần này cung cấp **một ứng dụng Servlet nhỏ hoàn chỉnh**: form login, hai role và endpoint yêu cầu CSRF. Dùng Spring Boot `3.5.16` (mốc phiên bản được chỉ định cho ví dụ, không phải khẳng định là release mới nhất) với Security 6.x được Boot quản lý.

Cây thư mục:

~~~text
security-mockmvc-demo/
├── pom.xml
└── src/
    ├── main/java/demo/security/
    │   ├── DemoApplication.java
    │   ├── SecurityConfiguration.java
    │   └── DemoController.java
    └── test/java/demo/security/
        └── DemoSecurityTests.java
~~~

### 6.1. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>security-mockmvc-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
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
~~~

### 6.2. `src/main/java/demo/security/DemoApplication.java`

~~~java
package demo.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 6.3. `src/main/java/demo/security/SecurityConfiguration.java`

~~~java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .requestMatchers("/me", "/settings").authenticated()
                .anyRequest().denyAll())
            .formLogin(Customizer.withDefaults());
        // CSRF là mặc định cho Servlet web app; không disable.
        return http.build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        UserDetails alice = User.withUsername("alice")
                .password("{noop}demo-pass")
                .roles("USER")
                .build();
        UserDetails admin = User.withUsername("admin")
                .password("{noop}admin-pass")
                .roles("ADMIN")
                .build();
        return new InMemoryUserDetailsManager(alice, admin);
    }
}
~~~

**`{noop}` chỉ dành cho demo/test với credential giả**, không dùng để lưu password production. Hệ thống thật dùng `PasswordEncoder` an toàn như BCrypt/Argon2 theo policy, không hard-code password. `hasRole("ADMIN")` so với authority `ROLE_ADMIN`; `roles("ADMIN")` tự thêm tiền tố `ROLE_`. Các endpoint `/login` do `formLogin()` xử lý; `CSRF` giữ mặc định.

### 6.4. `src/main/java/demo/security/DemoController.java`

~~~java
package demo.security;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/me")
    public String me(Principal principal) {
        return principal.getName();
    }

    @GetMapping("/admin")
    public String admin() {
        return "admin";
    }

    @PostMapping("/settings")
    public String settings() {
        return "updated";
    }
}
~~~

### 6.5. `src/test/java/demo/security/DemoSecurityTests.java`

~~~java
package demo.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.unauthenticated;
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
class DemoSecurityTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicPageAllowsAnonymous() throws Exception {
        mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"));
    }

    @Test
    void protectedPageRequiresLogin() throws Exception {
        mvc.perform(get("/me"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void loginWithCorrectPasswordSucceeds() throws Exception {
        mvc.perform(formLogin()
                    .user("alice")
                    .password("demo-pass"))
                .andExpect(authenticated().withUsername("alice"));
    }

    @Test
    void loginWithWrongPasswordFails() throws Exception {
        mvc.perform(formLogin()
                    .user("alice")
                    .password("wrong"))
                .andExpect(unauthenticated());
    }

    @Test
    void mockedUserCanReadOwnName() throws Exception {
        mvc.perform(get("/me")
                    .with(user("alice").roles("USER")))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));
    }

    @Test
    void nonAdminCannotReadAdminRoute() throws Exception {
        mvc.perform(get("/admin")
                    .with(user("alice").roles("USER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCanReadAdminRoute() throws Exception {
        mvc.perform(get("/admin")
                    .with(user("admin").roles("ADMIN")))
                .andExpect(status().isOk())
                .andExpect(content().string("admin"));
    }

    @Test
    void postWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/settings")
                    .with(user("alice").roles("USER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void postWithCsrfIsAllowed() throws Exception {
        mvc.perform(post("/settings")
                    .with(user("alice").roles("USER"))
                    .with(csrf()))
                .andExpect(status().isOk())
                .andExpect(content().string("updated"));
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void annotationCanSetTestSecurityContext() throws Exception {
        mvc.perform(get("/me"))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));
    }
}
~~~

Chạy từ thư mục chứa `pom.xml` (Maven + JDK 17 đã cài, máy có khả năng tải dependencies):

~~~bash
mvn test
~~~

**Kỳ vọng:** 10 bài test thành công, không có failed/error tests; output Maven cụ thể (thời gian chạy, tên reporter, số lần cache) tùy môi trường. Các điều kiện được kiểm tra là:

| Test | Điều khẳng định |
|---|---|
| Public GET | Anonymous nhận `200` với body `public`. |
| Protected GET | Anonymous được chuyển hướng sang login flow (3xx). |
| Correct form login | Kết quả `Authentication` có username `alice`. |
| Wrong form login | Không có authenticated result. |
| `user()` GET /me | Mock principal xuất hiện ở controller. |
| `user()` GET /admin | `ROLE_USER` bị từ chối `403`. |
| Admin GET | `ROLE_ADMIN` nhận `200`. |
| POST thiếu CSRF | `403` mặc dù đã mô phỏng principal. |
| POST có CSRF | `200` và body `updated`. |
| `@WithMockUser` | Test SecurityContext được đưa vào request. |

**Hai loại test khác nhau trong cùng file:** `formLogin()` thật sự gửi một request vào authentication filter và kiểm tra password với `UserDetailsService`; các test `user()`/`@WithMockUser` **bỏ qua bước kiểm chứng password** và có mục đích kiểm tra ranh giới access policy.

Chú ý servlet form login mặc định khi client yêu cầu HTML thường redirect; nếu ứng dụng thực là REST API dùng custom entry point trả JSON `401` thì kỳ vọng phải điều chỉnh theo security chain thật, không sao chép `3xx` máy móc.

## 7. Vì sao `formLogin()` và `user()` không thể thay thế nhau?

### `formLogin()`

~~~java
mvc.perform(formLogin()
        .user("alice")
        .password("demo-pass"))
    .andExpect(authenticated());
~~~

`SecurityMockMvcRequestBuilders.formLogin()` tạo request phù hợp form-login mặc định và cung cấp CSRF token test theo thiết kế. Đường test đi qua `UsernamePasswordAuthenticationFilter` và `AuthenticationManager` khi filter chain được áp. Dùng để kiểm tra password đúng/sai, disabled/locked flags, login failure handlers và session authentication behavior.

Có thể đổi endpoint và parameter tên field:

~~~java
// Nếu ứng dụng cấu hình loginProcessingUrl("/signin")
// và usernameParameter("email"), passwordParameter("secret"):
mvc.perform(formLogin("/signin")
        .userParameter("email")
        .passwordParam("secret")
        .user("alice@example.test")
        .password("wrong"))
    .andExpect(unauthenticated());
~~~

Các method tên parameter có thể khác theo phiên bản; đối với API Spring Security 6.x, nên xác nhận chữ ký builder từ `SecurityMockMvcRequestBuilders` tương ứng khi copy đoạn này. Đây là snippet minh họa custom form configuration, **không áp dụng trực tiếp** vào app demo ở phần 6.

### `user()`

~~~java
mvc.perform(get("/admin")
        .with(user("alice").roles("ADMIN")))
    .andExpect(status().isOk());
~~~

`SecurityMockMvcRequestPostProcessors.user()` tạo authentication đã được coi là hợp lệ trong mock request. Dùng để hỏi "nếu principal X có `ROLE_ADMIN` thì rule hoạt động thế nào?" Nó **không kiểm chứng** account "alice" có tồn tại trong DB, password có đúng, trạng thái disabled có được chặn trong login hay không.

Đừng gọi test trên là chứng minh `AuthenticationProvider` đã chạy. Trong đời thật, attacker không được tự cấp `ROLE_ADMIN`; chỉ test fixture mới có quyền làm vậy.

## 8. `@WithMockUser`, `@WithUserDetails` và custom principal

### `@WithMockUser`

~~~java
@Test
@WithMockUser(username = "alice", roles = "USER")
void userPage() throws Exception {
    mvc.perform(get("/me"))
            .andExpect(status().isOk());
}
~~~

Annotation `org.springframework.security.test.context.support.WithMockUser` thiết lập test security context trước test method. Nó tiện cho nhiều test có cùng role. `roles={"ADMIN"}` tạo authority `ROLE_ADMIN`; `authorities={"SCOPE_orders.read"}` dùng chính xác tên authority, không tự thêm tiền tố role.

**Không kết hợp `roles` và `authorities` một cách tùy tiện:** hãy quyết định policy đang dùng `hasRole` hay `hasAuthority`.

### `@WithUserDetails`

Khi controller/service phụ thuộc `UserDetails` thật hơn là username giả, có thể dùng:

~~~java
@Test
@WithUserDetails("alice")
void loadedPrincipal() throws Exception {
    mvc.perform(get("/me"))
            .andExpect(status().isOk());
}
~~~

Cần `UserDetailsService` có user `alice` trong test context. Annotation nạp principal từ service, nhưng **không thử password được submit qua form**. Dùng khi custom `UserDetails` có tenant/ID/authorities, còn test login credential vẫn dùng `formLogin()`.

### Custom principal và `@WithSecurityContext`

Nếu ứng dụng sử dụng `InternalPrincipal` với tenant, user ID, factor proof hoặc policy version, `@WithMockUser` có thể tạo sai loại principal. Hãy dùng `authentication()` request post-processor với authentication instance phù hợp, hoặc tạo annotation `@WithSecurityContext(factory=...)` để xây test context có đúng principal.

Quan trọng: build custom principal từ **test fixture tin cậy**, không để controller/authorization layer lấy role từ JSON request body. Dù dùng mock, test phải phản ánh ranh giới do framework quản lý.

## 9. Kiểm tra anonymous, quyền và kết quả login

Các result matchers tiện dụng:

~~~java
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.unauthenticated;

mvc.perform(formLogin().user("alice").password("demo-pass"))
    .andExpect(authenticated().withUsername("alice"));

mvc.perform(formLogin().user("alice").password("bad"))
    .andExpect(unauthenticated());
~~~

Có thể kiểm tra `authenticated().withRoles("USER")`, username hoặc predicate trên `Authentication` để xác nhận authorities/principal. Tuy nhiên nếu chỉ đưa `user("admin").roles("ADMIN")` từ fixture rồi kiểm tra `authenticated()`, bạn đang xác nhận trạng thái giả lập của fixture, **không phải** quá trình verifier xác thực credential.

Đối với anonymous request:

- Web form login thường redirect tới `/login`; có thể kiểm tra `3xx` và `Location` phù hợp.
- API dùng bearer token thường trả `401 Unauthorized` khi thiếu/invalid token.
- Authenticated principal thiếu quyền thường `403 Forbidden`.
- POST có cookie-based session nhưng không có CSRF token có thể `403` ngay cả khi principal hợp lệ.

**HTTP behavior phụ thuộc entry point, exception handling, CSRF matcher và authentication mechanism đang được cấu hình.** Không ép mọi endpoint thiếu user đều `401` nếu ứng dụng cố ý dùng web redirect.

## 10. Kiểm thử CSRF, lỗi input và handler

Spring Security CSRF mặc định bảo vệ những phương thức thay đổi trạng thái trong nhiều Servlet web apps. Với `MockMvc`:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;

mvc.perform(post("/settings")
        .with(user("alice"))
        .with(csrf()))
    .andExpect(status().isOk());

mvc.perform(post("/settings")
        .with(user("alice"))
        .with(csrf().useInvalidToken()))
    .andExpect(status().isForbidden());
~~~

`csrf()` cung cấp token phù hợp cho test; `csrf().asHeader()` có thể dùng để gửi qua header. **Không tắt CSRF chỉ vì bài test thiếu token** nếu ứng dụng thực đang dùng cookie/session web. Điều này có thể tạo lỗi CSRF thật ở production.

Để test **failure handler**, thử password sai qua `formLogin()`, kiểm tra redirect hoặc JSON error tùy cấu hình, và xác minh không lộ trạng thái account. Nếu handler đã dùng generic error message, test cả user không tồn tại với sai password để chống account enumeration.

Test cookies và session khi có logic login/logout cụ thể. Một request đã authenticate trong `MockMvc` không có nghĩa HTTP session của các request sau tự được giữ: cần lấy và tái sử dụng `MockHttpSession` hoặc cookie theo đúng test scenario, thay vì kỳ vọng mỗi `mvc.perform` là một browser duy trì session.

## 11. Test OAuth2 Resource Server JWT: `jwt()` là mock authentication

Spring Security test Servlet có `jwt()`:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;

mvc.perform(get("/api/orders")
        .with(jwt().jwt(token -> token
                .subject("usr-1042")
                .claim("scope", "orders:read"))))
    .andExpect(status().isOk());
~~~

Đoạn trên **chỉ đúng khi security/endpoint trong ứng dụng cho phép authority/claims tương ứng**; không nằm trong mini app form-login ở phần 6. `jwt()` dựng `JwtAuthenticationToken` giả để đi qua test authorization context, không yêu cầu token được mã hóa/ký bởi IdP thật.

Có thể chỉ định authorities trực tiếp:

~~~java
mvc.perform(get("/api/orders")
        .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders:read"))))
    .andExpect(status().isOk());
~~~

Import `org.springframework.security.core.authority.SimpleGrantedAuthority` trong Java snippet.

**Điểm rất quan trọng:** `jwt()` **bỏ qua việc kiểm chứng chữ ký, `iss`, `aud` và `exp` của JWT thực**. Một test thành công với `jwt()` không chứng minh `JwtDecoder` được cấu hình an toàn. Để kiểm chứng token validation, gửi bearer token đã ký và dùng decoder phù hợp hoặc stub riêng `JwtDecoder` trả/throw theo trường hợp, kiểm tra negative cases cho signature/issuer/audience/expiry. Trong Spring Security Resource Server, `JwtAuthenticationToken.getPrincipal()` thường là một `Jwt`, không mặc nhiên là custom UserDetails.

### JWT role/scopes mapping

Mặc định Spring resource server thường map scopes vào authorities dạng `SCOPE_x`. Nếu hệ thống có converter riêng từ `roles`/groups/tenant sang authorities nội bộ, test phải bảo đảm **converter thực sự chạy**. Truyền thẳng `jwt().authorities(...)` có thể bỏ qua converter, nên test cả converter và integration path với claims để phát hiện mapping sai.

## 12. OAuth2 Login, OIDC, opaque token: helper dùng để làm gì?

Servlet security-test hỗ trợ:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.oauth2Login;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.opaqueToken;

mvc.perform(get("/profile")
        .with(oauth2Login()));

mvc.perform(get("/profile")
        .with(oidcLogin()
                .idToken(token -> token.claim("user_id", "usr-1042"))));

mvc.perform(get("/api/data")
        .with(opaqueToken()
                .authorities(
                    new SimpleGrantedAuthority("SCOPE_data:read"))));
~~~

Mỗi helper này **đặt đúng loại mock authentication/principal** cho controller cần `OAuth2User`, `OidcUser` hoặc opaque `BearerTokenAuthentication`, tránh phải chạy authorization code flow với IdP thật trong mọi test đơn vị.

Chúng **không chứng minh**:

- OAuth2 authorization redirect/callback, `state`, `nonce`, PKCE đã được kiểm tra end-to-end.
- ID Token đã được xác thực bằng issuer/audience/signature đúng.
- Opaque-token introspection thực sự trả `active=false` khi token revoked.
- Principal mapping từ external `(iss,sub)` sang internal account được đúng trong mọi path.

Test helper dùng để kiểm tra controller/authorization logic **khi giả định authentication đã hợp lệ**. Muốn test federation thực, thêm tests cho OAuth2LoginAuthenticationFilter/OIDC client/IdP simulator hoặc wire mock server ở boundary có chủ đích.

## 13. WebFlux: dùng WebTestClient và SecurityWebFilterChain

Với ứng dụng WebFlux, runtime có `SecurityWebFilterChain`, `ServerWebExchange` và `ReactiveAuthenticationManager`. Không dùng Servlet `HttpSecurity` hoặc `SecurityFilterChain` của MVC để thay cho cấu hình reactive.

Ví dụ WebFlux security config trong ứng dụng riêng có `spring-boot-starter-webflux`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/public").permitAll()
                .pathMatchers("/admin").hasRole("ADMIN")
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Đây là **mã tích hợp**: cần thêm controllers/reactive user store và application context. Nó không chạy cùng mini app MVC của phần 6 như một security chain khác. Để JWT reactive resource server, sẽ cần `oauth2ResourceServer(jwt -> jwt.jwt(...))` hoặc cấu hình tương ứng và dependency resource server.

### Cấu hình WebTestClient security

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

@BeforeEach
void setup() {
    client = WebTestClient
            .bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
}
~~~

`applicationContext` là Spring `ApplicationContext` của **WebFlux app**, và `client` là `org.springframework.test.web.reactive.server.WebTestClient`. `springSecurity()` ở đây thuộc `SecurityMockServerConfigurers`, **khác package với Servlet `SecurityMockMvcConfigurers.springSecurity()`**.

Nếu dùng Spring Boot `@AutoConfigureWebTestClient`, kiểm tra client đã được cấu hình security phù hợp với WebFlux application. Với client bound-to-server thật, không thể tùy ý dùng mutator tạo mock server exchange phía server như khi bind-to-application-context.

## 14. Reactive test với `mockUser()`, `mockJwt()`, `csrf()`

Một test class trong **dự án WebFlux riêng** có thể viết:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;

@SpringBootTest
class ReactiveSecurityTests {

    @Autowired
    ApplicationContext applicationContext;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
                .bindToApplicationContext(applicationContext)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void anonymousCannotAccessAdmin() {
        client.get().uri("/admin")
                .exchange()
                .expectStatus().isUnauthorized();
        // Giả định app sử dụng HTTP Basic entry point.
    }

    @Test
    void userWithoutAdminRoleIsForbidden() {
        client.mutateWith(mockUser("alice").roles("USER"))
                .get().uri("/admin")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminCanAccessAdminRoute() {
        client.mutateWith(mockUser("admin").roles("ADMIN"))
                .get().uri("/admin")
                .exchange()
                .expectStatus().isOk();
    }

    @Test
    void csrfCanBeAddedToStateChangingRequest() {
        client.mutateWith(mockUser("alice").roles("USER"))
                .mutateWith(csrf())
                .post().uri("/settings")
                .exchange()
                .expectStatus().isOk();
        // Giả định có POST /settings và security rule cho phép USER.
    }
}
~~~

Đây là **integration snippet** vì app reactive/controller và user store phải tồn tại với routes phù hợp. Phải bảo đảm method `/settings` có controller handler và không có business validation làm thay đổi kết quả. Thay `@SpringBootTest` bằng test context phù hợp khi dự án dùng functional routes, router functions hoặc custom security chain.

Reactive mock JWT:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockJwt;

client.mutateWith(mockJwt()
        .authorities(new SimpleGrantedAuthority("SCOPE_orders:read")))
    .get().uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
~~~

Cần import `SimpleGrantedAuthority` và một endpoint tương ứng. `mockJwt()` tạo `JwtAuthenticationToken` trong server exchange, **không gửi JWT đã ký để test decoder**. Reactive WebTestClient cũng có annotations `@WithMockUser` khi security test setup hỗ trợ, nhưng phải kiểm tra test context và lifecycle.

Nếu ứng dụng WebFlux dùng `httpBasic` và muốn kiểm tra password thật, hãy gửi Basic Authorization header/client filter tương ứng để gọi reactive authentication manager/user store, **không dùng `mockUser()`** vì nó bypasses credential verification.

## 15. WebTestClient không đồng nghĩa chỉ có WebFlux

Spring Framework có thể dùng `WebTestClient` để kiểm thử:

- **WebFlux bind-to-controller/context** không cần server.
- **Spring MVC thông qua `MockMvcWebTestClient` adapter**.
- **HTTP server thật bằng `bindToServer()`**.

Tuy nhiên, `SecurityMockServerConfigurers.mockUser()`, `mockJwt()`, `csrf()` thao tác trên **reactive `ServerWebExchange`**. Đừng copy chúng nguyên xi vào test MVC dùng `MockMvcWebTestClient` rồi kỳ vọng nó cấu hình servlet SecurityContext theo cùng cách. Với MVC, dùng Servlet request post-processors của `SecurityMockMvcRequestPostProcessors` hoặc test qua actual HTTP login/token.

**Chọn adapter theo application under test, không chỉ theo kiểu return value của client.** Một assertion WebTestClient có thể kiểm chứng HTTP result nhưng vẫn không chạy bảo mật nếu binding thiếu filter chain/web filter chain.

## 16. Kiểm thử method security và custom principal

Có hai ranh giới: HTTP authorization và method-level authorization. Ví dụ:

~~~java
@EnableMethodSecurity
@Configuration
class MethodSecurityConfig {}

@Service
class PayrollService {
    @PreAuthorize("hasAuthority('PAYROLL_APPROVE')")
    void approve(String paymentId) {
        // business operation
    }
}
~~~

Nếu bạn chỉ test `GET /public`, bạn chưa chứng minh `@PreAuthorize` hoạt động. Có thể dùng:

- `@WithMockUser(authorities="PAYROLL_APPROVE")` để test method/service được chấp nhận.
- `@WithMockUser(roles="USER")` để test thiếu authority và bị từ chối.
- `MockMvc` request đi vào controller thật để xác nhận proxy/method-security interception và mapped HTTP status.
- Unit/service integration cho role-tenant/resource constraints, cùng negative tests để ngăn bypass.

**Cẩn thận self-invocation:** gọi method có `@PreAuthorize` từ chính bean chứa nó có thể bỏ qua Spring proxy. Một test chỉ gọi method trực tiếp bằng `new PayrollService()` cũng không kích hoạt method security. Test phải lấy bean từ Spring context hoặc qua HTTP request có security chain thật.

Nếu principal nội bộ có tenant/owner/factor proof, `@WithMockUser` có thể thiếu metadata; dùng `@WithSecurityContext` hoặc `authentication()` với đúng internal principal, rồi test trường hợp cross-tenant, disabled-account và step-up freshness. Không chấp nhận role/tenant tự khai trong request body để thay dữ liệu xác thực.

## 17. Test stateful session, logout và không rò quyền

Nhiều test nhập vai user bằng `with(user("alice"))` trên **một request độc lập**, nên không chứng minh session được persist giữa hai request.

Với form login stateful, kiểm thử:

1. Gửi `POST /login` với CSRF hợp lệ và credential đúng.
2. Lấy `MockHttpSession` hoặc cookie từ response theo cấu hình.
3. Gửi request tiếp theo sử dụng đúng session/cookie.
4. Xác minh endpoint bảo vệ cho phép.
5. Gửi logout qua helper `logout()` hoặc request logout thực với CSRF.
6. Gửi lại session/cookie cũ, bảo đảm không còn được chấp nhận.

Spring Security test có `SecurityMockMvcRequestBuilders.logout()`; mặc định logout URI và CSRF của helper phụ thuộc setup. Cẩn thận không chỉ kiểm tra redirect `/login?logout` mà quên xác minh server-side session invalidation.

Nếu app dùng Spring Session Redis/JDBC, bài test với MockMvc context đơn lẻ có thể chưa chứng minh revoke all across nodes. Cần integration tests với store thực và nhiều app instances hoặc xác minh repository semantics.

## 18. Test negative cases trước khi tin vào green build

Một suite login nên bao gồm ít nhất:

| Tình huống | Kỳ vọng |
|---|---|
| Anonymous GET public | Cho phép khi policy là public. |
| Anonymous GET protected web page | Redirect login; hoặc 401 nếu API entry point. |
| Anonymous POST protected | Bị chặn bởi CSRF/authentication như policy, không có side effect. |
| Đúng username/password | Authenticated result, correct principal và session behavior. |
| Sai password | Không authenticated, generic failure response. |
| Username không tồn tại | Không lộ account existence qua status/body/timing rõ rệt. |
| Account disabled/locked | Không cho login; recovery policy phù hợp. |
| `@WithMockUser` role USER gọi admin route | 403. |
| User ADMIN gọi admin route | 200/expected behavior. |
| Thiếu CSRF trên session-backed POST | 403 nếu CSRF required. |
| CSRF token invalid | 403. |
| CSRF token valid | Có thể xử lý theo đúng authorization. |
| JWT mock scope thiếu | 403, khi endpoint yêu cầu authority. |
| JWT thật sai chữ ký/issuer/audience/expired | Token decoder từ chối; không thể chứng minh chỉ bằng `jwt()`. |
| OIDC mock principal thiếu claim cần thiết | Deny theo mapping/policy. |
| Valid token nhưng owner disabled | Deny nếu online account-state policy yêu cầu. |
| Cross-tenant principal | Không truy cập resource tenant khác. |
| MFA chưa hoàn tất | Không được nâng thành fully authenticated action quyền cao. |
| Logout | Session/cookie cũ không còn quyền. |
| CSRF/headers bị disable trong test | Suite phải phát hiện khác biệt thay vì “tự xanh”. |
| Authentication backend down | Fail closed, không mặc định login thành công. |

**Không chỉ kiểm tra 200/401/403**: assert principal/role, response body, cookie, header, side-effect service/repository, session handling và event/audit (nếu yêu cầu). Một request bị 403 do CSRF không chứng minh rule role đã chặn — cần cung cấp CSRF token hợp lệ khi đang muốn test authorization trên POST.

## 19. Bẫy thường gặp và nguyên nhân

### Bẫy 1: quên tích hợp security filter chain

`MockMvcBuilders.standaloneSetup(...)` hoặc `@AutoConfigureMockMvc(addFilters=false)` có thể làm endpoint trả 200 khi production trả 403. **Cách sửa:** cấu hình `springSecurity()`/`@AutoConfigureMockMvc` đúng và có negative test cho anonymous/role.

### Bẫy 2: dùng `@WithMockUser` để tuyên bố password login đã đúng

Mock user tạo sẵn authentication, không kiểm tra password encoder/user repo/provider. **Cách sửa:** test cả `formLogin()` hoặc actual HTTP Basic/bearer credential path.

### Bẫy 3: thiếu `csrf()` rồi tưởng thiếu role

POST không có CSRF bị 403 trước khi test được authorization rule. **Cách sửa:** khi test quyền POST, cung cấp valid CSRF; khi test CSRF, kiểm tra thiếu/invalid token riêng.

### Bẫy 4: `roles("ROLE_ADMIN")`

`roles("ADMIN")` tự sinh `ROLE_ADMIN`. Dùng `roles("ROLE_ADMIN")` có thể tạo sai authority hoặc bị từ chối vì prefix đã có. **Cách sửa:** với role, truyền `"ADMIN"`; với authority nguyên văn, dùng `authorities("ROLE_ADMIN")` khi API hỗ trợ.

### Bẫy 5: `jwt()` test green nhưng production JWT verifier sai

Mock JWT không kiểm signature/issuer/audience/expiry. **Cách sửa:** test converter và decoder riêng, có integration test với JWT đã ký hoặc decoder mocked theo kịch bản negative.

### Bẫy 6: test Servlet helper trong reactive context

`SecurityMockMvcRequestPostProcessors.user()` và `SecurityMockServerConfigurers.mockUser()` khác runtime. **Cách sửa:** phân nhánh test theo Spring MVC hay WebFlux, đúng package.

### Bẫy 7: chỉ test role thành công

Không có negative test cho anonymous, USER gọi ADMIN, wrong password, expired token, CSRF. **Cách sửa:** test ma trận cho phép/từ chối, chú trọng fail-closed.

### Bẫy 8: mock hết security configuration

Nếu `@WebMvcTest` mock luôn filter/proxy, test không chứng minh policy production. **Cách sửa:** import/filter chain thật khi đó là đối tượng cần kiểm thử; dùng `@SpringBootTest` khi nhiều integration beans liên quan.

### Bẫy 9: test context vô tình trỏ production

Không dùng tài khoản production, IdP thật hoặc signing keys thật cho integration tests. Cần profile/test datasource/local IdP fixtures, không log credentials test nếu có nguy cơ lẫn với production.

### Bẫy 10: kết quả chỉ khác vì request matching

Security matcher `/api/**` có thể không bao phủ endpoint mới; `permitAll`/`anyRequest`/multiple filter chains có thứ tự khác. **Cách sửa:** test trực tiếp mọi route nhạy cảm và match chain thực, không chỉ service method.

## 20. Cấu trúc test suite có thể duy trì lâu dài

Một codebase thường nên phân lớp test rõ:

~~~text
src/test/java/
  security/
    PasswordLoginMockMvcTests.java
    RoleAuthorizationMockMvcTests.java
    CsrfMockMvcTests.java
    SessionAndLogoutTests.java
    JwtClaimMappingTests.java
    JwtDecoderIntegrationTests.java
    OidcPrincipalMappingTests.java
    SecurityEventTests.java
  reactive/
    ReactiveSecurityWebTestClientTests.java (chỉ nếu dự án WebFlux)
~~~

Có thể dùng custom fixtures `aliceUser()`, `adminJwt()`, `oidcTenantUser()`, nhưng phải đặt tên nhắc rằng chúng là **mocked security context**. Không tạo default request luôn là admin cho cả suite: nó có thể che lấp một endpoint đáng lẽ anonymous bị chặn.

Khuyến nghị:

- Chọn test names theo behavior, ví dụ `anonymousShouldNotApprovePayment`, `validPasswordShouldAuthenticate`.
- Dùng JUnit parameterized tests khi thử ma trận nhiều role/scope/tenant.
- Giữ fixtures tối thiểu, không phụ thuộc thứ tự chạy test; reset session/state giữa tests.
- Dùng thời gian kiểm soát được cho JWT expiry/MFA freshness, không `Thread.sleep()`.
- Giữ negative tests qua mỗi thay đổi SecurityFilterChain, request matcher, JWT converter hoặc resource permission.
- Test bảo mật ở mức controller/service và tích hợp hệ thống khi có Redis/IdP/LDAP/KMS, không để mock che mất ranh giới tin cậy.
- Trong CI, thất bại của security tests phải làm build fail; không tắt filters, CSRF hoặc assertions để “cho xanh”.

## 21. Checklist trước khi đánh dấu hoàn thành

- [ ] Dự án xác định là Servlet MVC hay reactive WebFlux; dùng đúng test tool.
- [ ] Đã thêm `spring-security-test` trong test scope, phiên bản tương thích với Spring Security runtime.
- [ ] `MockMvc` có Spring Security filters qua `springSecurity()` hoặc Boot auto-config; không dùng `addFilters=false` khi test policy.
- [ ] `WebTestClient` WebFlux được `apply(springSecurity())` và setup đúng server context.
- [ ] Test có actual login credential path (`formLogin()`/HTTP Basic/OIDC callback integration) và test mocked principal path tách biệt.
- [ ] Test anonymous, wrong password, disabled/locked user, role/authority allow/deny.
- [ ] Test POST với valid/invalid/missing CSRF theo ứng dụng thực.
- [ ] Test JWT/OIDC/OAuth2 principal bằng helper và validation thật bằng integration tests bổ sung.
- [ ] Test quyền theo tenant/resource thay vì chỉ role.
- [ ] Test session/logout và không tự suy session continuity từ test user mock.
- [ ] Test method security qua Spring-managed proxy, tránh self-invocation false positive.
- [ ] Không đưa secret, token, user PII vào logs/test artifacts.
- [ ] Negative/security regression tests chạy tự động trong CI.
- [ ] Test suite dùng mock rõ ràng, không khẳng định một mock vượt qua decoder/provider là kiểm chứng production auth.

## 22. Tổng kết

`spring-security-test` giúp kiểm thử **đúng ranh giới** của Spring Security khi kết hợp với HTTP test infrastructure:

- Với **Spring MVC/Servlet**, dùng `MockMvc` và `springSecurity()` hoặc `@AutoConfigureMockMvc` có filters. `formLogin()` đi qua authentication mechanism; `user()`/`@WithMockUser` giả lập authentication để tập trung kiểm tra authorization.
- Với **Spring WebFlux**, dùng `WebTestClient` + reactive `springSecurity()` cùng `mockUser()`, `mockJwt()` và `csrf()`; các helper reactive không thể dùng thay servlet helpers một cách tùy tiện.
- Với **JWT/OIDC**, mock principal/claims thuận tiện nhưng **không thay** test chữ ký, issuer, audience, expiry, callback, nonce, state, PKCE và account mapping tại biên hệ thống.

Một bộ test đáng tin cần cả **positive và negative cases**, kiểm tra security chain thực, hiểu helper nào bypass credential verification và không để CSRF/role/session trở thành false positives.

## Tài liệu tham khảo

- [Spring Security 6.5 — MockMvc Setup](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html): `springSecurity()`, security filter chain và test context.
- [Spring Security — MockMvc Authentication](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html): `user()` và `@WithMockUser`.
- [Spring Security — MockMvc CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): `csrf()`, invalid token và header token.
- [Spring Security — MockMvc Result Matchers](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/result-matchers.html): `authenticated()` và `unauthenticated()`.
- [Spring Security — OAuth2/OIDC/JWT MockMvc Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): `oauth2Login()`, `oidcLogin()`, `jwt()` và `opaqueToken()`.
- [Spring Security 6.5 — Reactive WebTestClient Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html): `WebTestClient.apply(springSecurity())`.
- [Spring Security 6.5 — Reactive Authentication Testing](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html): `mockUser()` và reactive `@WithMockUser`.
- [Spring Security — Reactive CSRF Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html): reactive `csrf()`.
- [Spring Security — Reactive OAuth2/JWT Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockJwt()` và related helpers.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): bind-to-context, controllers, MockMvc adapter và HTTP server.
- [Spring Boot 3.5.16 Release](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/): phiên bản demo Maven.
