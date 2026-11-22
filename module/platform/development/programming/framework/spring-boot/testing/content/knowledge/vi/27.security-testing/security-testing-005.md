# Form login, HTTP Basic, session và logout khi ứng dụng có sử dụng

Trong **Spring Boot - testing**, nhóm **Bảo mật**, cần kiểm thử những cơ chế đăng nhập và duy trì danh tính mà **ứng dụng thực sự bật**: form login trên trình duyệt, HTTP Basic cho client thích hợp, HTTP session, CSRF và logout. Một bài test chỉ đặt **@WithMockUser** rồi GET endpoint thành công **chưa chứng minh** password được kiểm tra, session được tạo/lưu, login failure dẫn đến URL đúng, session fixation được phòng ngừa hoặc logout đã vô hiệu hóa session cũ.

Bài học tập trung **Spring Security servlet stack** trên **Java 17, Spring Boot 3.4.5 và Spring Security 6.4.x**. Ví dụ đầy đủ dùng **spring-boot-starter-security, spring-security-test, JUnit Jupiter, MockMvc** và một test HTTP thực với **RANDOM_PORT**. Bộ test sẽ kiểm tra **anonymous vs authenticated**, **form login đúng/sai mật khẩu**, **HTTP Basic 200/401**, **403 do thiếu role hoặc CSRF**, **session qua nhiều requests**, **đổi session ID khi login**, **POST logout có CSRF**, **session invalidated và không còn quyền truy cập**.

**Điều kiện áp dụng:** Không phải mọi ứng dụng đều cần form login, HTTP Basic hay server-side session. Một REST API hoàn toàn stateless dùng bearer token/OAuth2 Resource Server có hợp đồng khác. Chỉ bật và kiểm thử cơ chế có trong threat model/thực tế; **không thêm HTTP Basic hoặc form login chỉ để vượt qua một bài test**. Các kết quả nêu bên dưới là **kỳ vọng từ code**, không phải stdout Gradle đã được quan sát khi biên soạn.

## 1. Phân biệt authentication, authorization, session và logout

- **Authentication (xác thực):** chứng minh user là ai. Ví dụ form POST username/password hoặc HTTP header Authorization: Basic.
- **Authorization (phân quyền):** sau xác thực, user được vào đường dẫn nào. **ROLE_USER** có thể vào /private nhưng không được vào /admin.
- **SecurityContext:** chứa Authentication hiện tại; Spring Security dùng nó trong filter chain khi xử lý request.
- **HTTP session:** server-side state được nhận diện qua session cookie/id. Với form login kiểu stateful, kết quả authentication thường được lưu trong session để request sau vẫn biết user.
- **Session fixation protection:** đổi session ID khi xác thực thành công, tránh tái sử dụng ID bị kẻ tấn công kiểm soát từ trước.
- **CSRF protection:** chặn request thay đổi state được gửi bằng credentials của browser mà không có token hợp lệ; áp dụng cho form login, logout và POST/PUT/PATCH/DELETE theo cấu hình.
- **Logout:** chấm dứt server-side login state, thường invalidate session, clear SecurityContext và đưa client đến logout-success URL.
- **HTTP Basic:** client gửi username/password (Base64, **không phải mã hóa bảo mật**) theo từng request; không phải login form/session protocol. Phải dùng HTTPS; logout server-side **không thu hồi** username/password mà client vẫn có thể gửi lại.

Bốn câu hỏi cần được test độc lập: **ai đăng nhập được**, **đăng nhập xong được làm gì**, **danh tính còn qua request mới không**, và **logout có thực sự thu hồi session không**.

### Ma trận hành vi mục tiêu

| Tình huống | Cơ chế | Kết quả dự kiến trong project |
| --- | --- | --- |
| Anonymous GET /public | permitAll | **200** |
| Anonymous GET /private, Accept text/html | Form entry point | **302** đến /login |
| Anonymous GET /private, Accept application/json | Basic entry point | **401**, có WWW-Authenticate Basic |
| Alice login đúng password + CSRF | Form | **302** đến /private và authenticated |
| Alice login sai password | Form | **302** đến /login?error |
| Alice POST /login không CSRF | CSRF | **403**, chưa xác thực |
| Alice GET /private kèm authenticated session | Session | **200**, user=alice |
| Alice GET /admin | Authorization | **403** |
| Admin GET /admin | Authorization | **200** |
| Alice GET /private kèm đúng Basic header | HTTP Basic | **200** |
| Alice GET /private kèm sai Basic password | HTTP Basic | **401** |
| Alice POST /private/action không CSRF | CSRF | **403** |
| Alice POST /private/action có CSRF | CSRF | **200** |
| Logged-in POST /logout không CSRF | CSRF | **403**, session vẫn active |
| Logged-in POST /logout có CSRF | Logout | **302** đến /login?logout, session invalid |
| Request mới không mang session sau logout | Anonymous | **401** với Accept application/json |

**302/401 phụ thuộc entry point và Accept header** khi ứng dụng bật cả form login và Basic. Trong project này định nghĩa rõ header ở mỗi test để assertions không phụ thuộc content negotiation ngầm.

## 2. Spring Security request đi qua những gì?

~~~text
HTTP request
    |
    v
DelegatingFilterProxy
    |
    v
FilterChainProxy / SecurityFilterChain
    |
    +--> SecurityContextHolderFilter đọc SecurityContextRepository
    |
    +--> CsrfFilter kiểm tra token trên non-safe methods
    |
    +--> UsernamePasswordAuthenticationFilter (POST /login)
    |      hoặc BasicAuthenticationFilter (Authorization: Basic ...)
    |
    +--> AuthorizationFilter áp rule permitAll/authenticated/hasRole
    |
    v
Spring MVC controller
    |
    v
HTTP response
~~~

Đây là **sơ đồ khái niệm**, không phải thứ tự liệt kê chính xác tất cả filter: thứ tự filter thực tế có thể khác và còn tùy configuration. Spring Security 6 dùng **SecurityContextHolderFilter** và **SecurityContextRepository** theo mô hình lưu SecurityContext tường minh; các filter authentication chuẩn xử lý việc lưu thành công. Một **custom login endpoint** tự set SecurityContextHolder không nhất thiết được persist qua request tiếp theo nếu không gọi SecurityContextRepository.saveContext(...) phù hợp.

### Vì sao kiểm thử filter chain quan trọng?

Một controller test thuần:

~~~java
MockMvcBuilders.standaloneSetup(controller).build()
~~~

là **trích đoạn phản ví dụ**, có thể chạy mà không có Spring Security filter chain. Nếu nó gọi controller rồi trả 200, điều đó **không chứng minh** anonymous thật cũng được bảo vệ bởi security. Tương tự:

~~~java
@AutoConfigureMockMvc(addFilters = false)
~~~

là cấu hình **tắt filter khi chạy MockMvc**, nên có nguy cơ cho security tests xanh giả. Muốn kiểm chứng login/Basic/session/logout thực, dùng **@SpringBootTest + @AutoConfigureMockMvc** để MockMvc chạy filter chain đã cấu hình. Với MockMvc tự dựng từ WebApplicationContext, cần tích hợp **SecurityMockMvcConfigurers.springSecurity()** đúng cách.

## 3. Khi nào Spring Boot tự bật form login/Basic?

Khi spring-boot-starter-security có trên classpath và không có SecurityFilterChain custom thay thế, Spring Boot bảo vệ web app mặc định. Cơ chế challenge có thể chọn **form login** hoặc **HTTP Basic** theo request/Accept header. Spring Boot có thể tạo user mặc định với mật khẩu ngẫu nhiên để phát triển; **không dùng account/mật khẩu generated như production policy**.

Khi bạn định nghĩa **SecurityFilterChain bean** riêng, cần chủ động cấu hình **authorizeHttpRequests**, **formLogin**, **httpBasic**, **logout**, **csrf** và **sessionManagement** theo yêu cầu. Không coi việc import starter-security là bảo đảm các feature vẫn bật đúng khi một custom chain đã ghi đè default.

Trong project mẫu:
- GET /public: anonymous được phép.
- GET /private: mọi authenticated user.
- GET /admin: chỉ ROLE_ADMIN.
- POST /private/action: authenticated và CSRF hợp lệ.
- /login: Spring Security cung cấp **generated login page** và xử lý POST form login.
- /logout: Spring Security cung cấp logout endpoint, cần **POST + CSRF**.
- Cho phép **formLogin + httpBasic** đồng thời **chỉ để học cả hai flow**. Production nên thu hẹp attack surface và chọn phương án phù hợp từng client.

### Thứ tự match rule có ý nghĩa

Ví dụ:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public").permitAll()
    .requestMatchers("/admin").hasRole("ADMIN")
    .anyRequest().authenticated()
)
~~~

Rule cụ thể phải đặt **trước** anyRequest. **hasRole("ADMIN")** tương ứng với authority **ROLE_ADMIN** theo mặc định; **hasAuthority("ADMIN")** không phải cách viết đồng nghĩa. Test nên có user thường và admin để bắt lỗi security rule bị mở rộng.

## 4. Dự án runnable Java 17 + Spring Boot 3.4.5

Dự án intentionally dùng **hai account trong memory chỉ khi bật Spring profile demo**, để test không phụ thuộc database, external IdP hoặc password của người dùng thật. Đây là **fixture bảo mật phục vụ học tập**, không phải cấu hình triển khai sản phẩm.

### 4.1. Cấu trúc tệp

~~~text
settings.gradle
build.gradle
src/main/java/com/example/securityqa/SecurityQaApplication.java
src/main/java/com/example/securityqa/DemoSecurityConfig.java
src/main/java/com/example/securityqa/DemoController.java
src/test/java/com/example/securityqa/FormLoginFlowTest.java
src/test/java/com/example/securityqa/HttpBasicFlowTest.java
src/test/java/com/example/securityqa/SessionFixationTest.java
src/test/java/com/example/securityqa/LogoutFlowTest.java
src/test/java/com/example/securityqa/CsrfAndRoleTest.java
src/test/java/com/example/securityqa/RealHttpBasicTest.java
~~~

### 4.2. Gradle và test dependencies

**settings.gradle**

~~~groovy
rootProject.name = 'spring-security-authentication-testing'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
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
~~~

**spring-boot-starter-security** cung cấp Spring Security servlet filters, authentication và password encoding. **spring-security-test** cung cấp **formLogin()**, **httpBasic()**, **csrf()**, **@WithMockUser** cùng authenticated()/unauthenticated() matchers. **spring-boot-starter-test** cung cấp JUnit Jupiter, MockMvc và assertions.

Không thêm servlet container thủ công vì starter-web đã có embedded servlet server cho real HTTP test. Spring Boot 3.4 BOM quản lý Spring Security 6.4.x; không trộn phiên bản Spring Security 5.x hoặc Spring Boot 2.x snippets với Java 17/Jakarta Servlet APIs.

### 4.3. Main application

**src/main/java/com/example/securityqa/SecurityQaApplication.java**

~~~java
package com.example.securityqa;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityQaApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityQaApplication.class, args);
    }
}
~~~

### 4.4. SecurityFilterChain và in-memory demo users

**src/main/java/com/example/securityqa/DemoSecurityConfig.java**

~~~java
package com.example.securityqa;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
@Profile("demo")
public class DemoSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUsers(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN", "USER")
                .build()
        );
    }

    @Bean
    SecurityFilterChain demoSecurity(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(form -> form
                .defaultSuccessUrl("/private", true)
                .permitAll()
            )
            .httpBasic(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutSuccessUrl("/login?logout")
                .permitAll()
            )
            .sessionManagement(session -> session
                .sessionFixation(fixation ->
                    fixation.changeSessionId())
            );

        return http.build();
    }
}
~~~

**@Profile("demo")** giữ test credentials và cấu hình demonstration không được bật mặc định khi ứng dụng chạy với profile khác. **Tuyệt đối không kích hoạt profile demo trên môi trường internet/public**, không đưa alice-pass/admin-pass vào secrets thực, không dùng những credentials này trong production.

- **BCryptPasswordEncoder** hash mật khẩu fixture; login vẫn gửi cleartext password tới form/Basic transport nên phải dùng HTTPS khi triển khai.
- **roles("USER")** tạo authority ROLE_USER; admin có ROLE_ADMIN và ROLE_USER.
- **formLogin.defaultSuccessUrl("/private", true)** dùng redirect cố định sau successful form login, làm contract dễ assert. Nếu bỏ **true**, Spring Security có thể đưa user về SavedRequest trước login.
- **httpBasic** được bật để test HTTP Authorization header; Basic **không nên được bật nếu ứng dụng không cần**.
- **csrf** giữ mặc định, không disable chỉ để form login/logout test xanh.
- **sessionFixation.changeSessionId()** là chiến lược phù hợp với Servlet 3.1+, thay session ID khi auth success.
- **logout** sử dụng default logout filter, success redirect về /login?logout; mặc định invalidate session/clear SecurityContext khi logout thành công.

Khi viết custom loginPage("/sign-in"), bạn phải tự cung cấp GET trang đó, thiết lập loginProcessingUrl, username/password parameter names và permitAll phù hợp. Không copy đoạn test formLogin() mặc định nếu endpoint đã được đổi.

### 4.5. Controller cho public, private, admin và POST có CSRF

**src/main/java/com/example/securityqa/DemoController.java**

~~~java
package com.example.securityqa;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public Map<String, String> publicPage() {
        return Map.of("status", "public");
    }

    @GetMapping("/private")
    public Map<String, String> privatePage(
            Authentication authentication) {
        return Map.of(
            "user", authentication.getName(),
            "scope", "private");
    }

    @GetMapping("/admin")
    public Map<String, String> adminPage(
            Authentication authentication) {
        return Map.of(
            "user", authentication.getName(),
            "scope", "admin");
    }

    @PostMapping("/private/action")
    public Map<String, String> submitAction(
            Authentication authentication) {
        return Map.of(
            "status", "accepted",
            "user", authentication.getName());
    }
}
~~~

POST /private/action là **điểm kiểm tra bảo vệ request non-safe**, không sửa dữ liệu thật. Trong production, ví dụ này có thể là đổi password hoặc tạo đơn hàng; test CSRF phải xác minh request **không đến business side effect** khi thiếu token. Ở demo, HTTP status cho biết CsrfFilter xử lý request trước controller.

## 5. Test Form Login: credentials, redirect và session qua requests

**src/test/java/com/example/securityqa/FormLoginFlowTest.java**

~~~java
package com.example.securityqa;

import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("demo")
class FormLoginFlowTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void anonymousBrowserIsRedirectedToLogin() throws Exception {
        mvc.perform(get("/private")
                .accept(MediaType.TEXT_HTML))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login"));
    }

    @Test
    void successfulFormLoginPersistsAuthenticationInSession()
            throws Exception {
        MvcResult result = mvc.perform(
                formLogin()
                    .user("alice")
                    .password("alice-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/private"))
            .andExpect(authenticated().withUsername("alice"))
            .andReturn();

        HttpSession session =
                result.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/private")
                .session((MockHttpSession) session)
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("alice"))
            .andExpect(jsonPath("$.scope").value("private"));
    }

    @Test
    void wrongPasswordIsRejected() throws Exception {
        mvc.perform(formLogin()
                .user("alice")
                .password("wrong-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"))
            .andExpect(unauthenticated());
    }

    @Test
    void loginWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/login")
                .param("username", "alice")
                .param("password", "alice-pass"))
            .andExpect(status().isForbidden());
    }
}
~~~

**formLogin()** là helper từ **spring-security-test**: nó tạo request **POST /login**, điền credentials và **CSRF token hợp lệ**. Vì thế test formLogin() thành công **không tự chứng minh endpoint cũng chấp nhận POST thiếu CSRF**; test riêng loginWithoutCsrfIsForbidden phải gửi raw post để verify 403.

**authenticated().withUsername("alice")** xác nhận SecurityContext sau login match đúng principal. Test tiếp theo truyền **MockHttpSession** từ request login vào **GET /private mới** để chứng minh **authentication persistence qua request**, không chỉ trạng thái của một request đang được xử lý.

**Sai password** phải fail và redirect /login?error theo default failure handler. Chỉ assert status302 là yếu vì **cả thành công và thất bại đều thường là redirect**; phải assert đúng Location và authenticated()/unauthenticated().

### Trường hợp saved request

Nếu browser GET /private trước, Spring Security có thể lưu **SavedRequest** trong session và sau successful form login redirect về URL ban đầu. Trong demo đã cố ý dùng **defaultSuccessUrl("/private", true)** để luôn redirect /private; khi test một ứng dụng thực **không bật alwaysUse=true**, expected redirect phải phản ánh SavedRequest contract thay vì ép URL của demo.

### Khi custom login form

Ví dụ app tự định nghĩa loginProcessingUrl("/auth/login"), usernameParameter("email"), passwordParameter("secret"), thì test dùng:

~~~java
mvc.perform(
    formLogin("/auth/login")
        .user("email", "alice@example.com")
        .password("secret", "password"))
    .andExpect(authenticated());
~~~

Đây là **trích đoạn minh họa**, không thuộc runnable tree. Nó chỉ chạy nếu SecurityFilterChain thật đã cấu hình endpoint/parameter names đó và có user tương ứng. Không trộn helper mặc định POST /login với custom loginPage khi URL/field đã thay.

## 6. Test HTTP Basic: header thật, 401/403 đúng

HTTP Basic truyền:

~~~http
Authorization: Basic YWxpY2U6YWxpY2UtcGFzcw==
~~~

Đây là Base64 của **alice:alice-pass** trong demo. **Base64 có thể decode**, không mã hóa hay bảo vệ bí mật; Basic **chỉ an toàn khi được gửi qua TLS/HTTPS**. Không log Authorization headers, không đặt Basic credentials trong URL và không dùng test credential production.

**src/test/java/com/example/securityqa/HttpBasicFlowTest.java**

~~~java
package com.example.securityqa;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.startsWith;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("demo")
class HttpBasicFlowTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void validBasicCredentialsReachProtectedEndpoint()
            throws Exception {
        mvc.perform(get("/private")
                .with(httpBasic("alice", "alice-pass"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("alice"));
    }

    @Test
    void anonymousJsonRequestGetsBasicChallenge()
            throws Exception {
        mvc.perform(get("/private")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "WWW-Authenticate", startsWith("Basic")));
    }

    @Test
    void wrongBasicPasswordGetsUnauthorized()
            throws Exception {
        mvc.perform(get("/private")
                .with(httpBasic("alice", "invalid"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void userRoleCannotEnterAdminArea() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("alice", "alice-pass"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminRoleMayEnterAdminArea() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("admin", "admin-pass"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("admin"))
            .andExpect(jsonPath("$.scope").value("admin"));
    }
}
~~~

**httpBasic("alice","alice-pass")** là **RequestPostProcessor**, tạo Authorization header thực ở mức MockHttpServletRequest. Khác với **with(user("alice"))** hoặc **@WithMockUser**, nó đi qua cơ chế HTTP Basic authentication và kiểm tra mật khẩu dựa trên UserDetailsService/PasswordEncoder.

Cùng một route, anonymous request có thể:
- **302 redirect /login** nếu client chấp nhận HTML và chain chọn form entry point.
- **401 WWW-Authenticate: Basic** nếu request chọn Basic entry point, ví dụ **Accept application/json** trong cấu hình demo.
- **403** nếu đã authenticated nhưng không đủ authority, hoặc request unsafe thiếu CSRF.

**Không viết một test chung rằng mọi anonymous request phải 401** khi hệ thống đang hỗ trợ browser form login và API HTTP Basic. Xác định Accept headers, SecurityFilterChain matcher, entry point và response thực.

### Basic auth không tự đồng nghĩa STATELESS

Basic thường được dùng theo request; nhưng một app vẫn có thể có session behavior tùy SecurityFilterChain và SessionCreationPolicy. **Không suy ra tự động** rằng mọi request Basic không có JSESSIONID hoặc server state. Nếu ứng dụng là REST API stateless, hãy chủ động cấu hình SessionCreationPolicy.STATELESS trên đúng filter chain, chọn CSRF policy theo nguy cơ cookies/browser credentials, rồi viết tests không phụ thuộc session.

## 7. Test session: login thật, session fixation và state persistence

Một session fixation attack có thể xảy ra nếu attacker biết hoặc ép browser dùng một session ID trước khi victim login, và ID ấy vẫn được chấp nhận sau login. Spring Security trên Servlet 3.1+ dùng **changeSessionId** mặc định; trong demo cấu hình tường minh.

Kiểm thử phải tạo **session cũ**, gắn một attribute không nhạy cảm, login rồi so sánh **old ID vs authenticated session ID** và verify user có thể dùng session đó vào protected endpoint.

**src/test/java/com/example/securityqa/SessionFixationTest.java**

~~~java
package com.example.securityqa;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("demo")
class SessionFixationTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void successfulLoginChangesExistingSessionId()
            throws Exception {

        MockHttpSession preLoginSession = new MockHttpSession();
        preLoginSession.setAttribute("cart", "cart-42");
        String oldSessionId = preLoginSession.getId();

        MvcResult login = mvc.perform(post("/login")
                .session(preLoginSession)
                .param("username", "alice")
                .param("password", "alice-pass")
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(authenticated().withUsername("alice"))
            .andReturn();

        MockHttpSession afterLogin =
                (MockHttpSession) login.getRequest().getSession(false);

        assertNotNull(afterLogin);
        assertNotEquals(oldSessionId, afterLogin.getId());
        assertEquals("cart-42", afterLogin.getAttribute("cart"));

        mvc.perform(get("/private")
                .session(afterLogin)
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("alice"));
    }
}
~~~

**Sự khác nhau giữa ID và object:** **changeSessionId()** có thể đổi ID trên **cùng** HttpSession object; đừng assert session object mới được cấp. Bài chỉ assert **ID đổi** và session vẫn mang attribute **cart** (trong changeSessionId strategy), rồi kiểm chứng request tiếp theo có authentication.

Spring Security còn có **newSession**, **migrateSession** và **none** trong session fixation policy:
- **changeSessionId**: dùng API Servlet container, mặc định Servlet 3.1+, ID đổi.
- **newSession**: tạo session mới và chỉ giữ một số security-related attributes cần thiết.
- **migrateSession**: copy attributes sang session mới, thường dành cho các container/compatibility modes khác.
- **none**: tắt bảo vệ session fixation, thường **không nên dùng**.

**Nếu app cấu hình SessionCreationPolicy.STATELESS**, test chờ SecurityContext được lưu qua session sẽ sai contract: người dùng phải gửi lại bearer/basic credentials hoặc token khác. Không tự thêm session vào REST API chỉ để một test xanh.

### Không đồng nhất SecurityContext của thread và session

**SecurityContextHolder** thường gắn với thread trong request. Khi request kết thúc, context có thể được clear khỏi thread; auth cần được **restore từ SecurityContextRepository** ở request mới. Đừng kết luận “đã login thành công” chỉ vì SecurityContextHolder trong cùng đoạn code chứa Authentication mà không kiểm tra request kế tiếp.

Nếu tự viết JSON login controller/custom authentication filter ở Spring Security 6, việc tự set SecurityContextHolder có thể **không persist** nếu không save vào SecurityContextRepository. Với form login filter chuẩn, persistence đã được xử lý; test session ở phần trên giúp bắt những regression do custom login persistence bị bỏ sót.

## 8. Test logout: POST + CSRF, invalidate session và không còn truy cập

Khi **CSRF bật**, Spring Security mặc định **POST /logout có CSRF** sẽ thực hiện logout; **GET /logout** thường hiển thị trang xác nhận (có token) chứ **không logout ngay**. Việc cho GET làm logout nếu tắt CSRF là một rủi ro logout-CSRF; không sửa test bằng cách vô hiệu hóa CSRF trên toàn app.

Logout thành công thường làm:
1. Invalidate HttpSession hiện tại.
2. Clear SecurityContextHolder.
3. Clear SecurityContextRepository.
4. Clear remember-me state nếu có.
5. Clear CSRF token và publish logout event tùy handler.
6. Redirect tới logout-success URL.

**src/test/java/com/example/securityqa/LogoutFlowTest.java**

~~~java
package com.example.securityqa;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("demo")
class LogoutFlowTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void postLogoutRequiresCsrfAndInvalidatesSession()
            throws Exception {

        MvcResult login = mvc.perform(formLogin()
                .user("alice")
                .password("alice-pass"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/private")
                .session(session)
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("alice"));

        mvc.perform(post("/logout")
                .session(session))
            .andExpect(status().isForbidden());

        assertFalse(session.isInvalid());

        mvc.perform(post("/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?logout"));

        assertTrue(session.isInvalid());

        // Sau logout, gửi request mới không có session/cookie.
        mvc.perform(get("/private")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Test này **không** cố truyền lại MockHttpSession đã invalid vào MockMvc request khác: một session bị invalidate không nên được tái sử dụng. Thay vào đó, nó assert **session.isInvalid()** và rằng request mới không mang session bị challenge. Hai assertions cùng nhau bảo vệ logout lifecycle.

**Quan trọng:** Nếu dùng helper **SecurityMockMvcRequestBuilders.logout()**, helper sẽ **tự kèm CSRF hợp lệ** theo mặc định. Nó rất tiện test success path; nhưng test muốn chứng minh **thiếu CSRF bị 403** phải tự gửi raw post("/logout") không có csrf().

### Logout rồi HTTP Basic vẫn có thể xác thực lại

Logout form session **không vô hiệu hóa mật khẩu**. Nếu client tiếp tục gửi:

~~~http
Authorization: Basic YWxpY2U6YWxpY2UtcGFzcw==
~~~

thì HTTP Basic filter có thể authenticate một request mới và cấp lại quyền, miễn credentials vẫn hợp lệ. Vì vậy câu **“logout cắt quyền Basic vĩnh viễn”** là sai. Để revoke credentials/tokens cần password change, token revocation, account disable hoặc cơ chế phù hợp. Với browser Basic auth, browser có thể cache credentials; ứng dụng không có một logout server-session chuẩn giống form login.

### Cookie xóa trên browser khác session invalidation

Invalidate HttpSession là hành động server-side. Xóa cookie trên client có thể được cấu hình thêm bằng logout handler/cookie settings nhưng **xóa cookie đơn độc** không nhất thiết invalidated server session đang còn. Ngược lại, invalidate session server-side không bảo đảm browser tự xóa cookie cũ nếu không có Set-Cookie/Clear-Site-Data policy; cookie cũ sẽ không còn đại diện session hợp lệ. Test MockMvc chứng minh server behavior, còn Set-Cookie/HttpOnly/Secure/SameSite cần test HTTP/browser phù hợp.

## 9. Test CSRF và authorization riêng, không nhập làm một

**CSRF** có thể trả **403 ngay cả khi user đã authenticated**. **Access denied do role** cũng trả **403**. Vì vậy một test chỉ assert HTTP 403 chưa cho biết nguyên nhân nếu không kiểm soát đầy đủ credentials, token và route.

**src/test/java/com/example/securityqa/CsrfAndRoleTest.java**

~~~java
package com.example.securityqa;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("demo")
class CsrfAndRoleTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void authenticatedPostWithoutCsrfIsForbidden()
            throws Exception {
        mvc.perform(post("/private/action")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedPostWithValidCsrfIsAccepted()
            throws Exception {
        mvc.perform(post("/private/action")
                .with(httpBasic("alice", "alice-pass"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("accepted"))
            .andExpect(jsonPath("$.user").value("alice"));
    }

    @Test
    void invalidCsrfTokenIsRejected() throws Exception {
        mvc.perform(post("/private/action")
                .with(httpBasic("alice", "alice-pass"))
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());
    }

    @Test
    void roleUserCannotAccessAdminEvenWithValidPassword()
            throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("alice", "alice-pass"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isForbidden());
    }

    @Test
    void roleAdminCanAccessAdmin() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("admin", "admin-pass"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.scope").value("admin"));
    }

    @Test
    void publicEndpointDoesNotNeedLogin() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("public"));
    }
}
~~~

**CSRF test** dùng actual Basic credentials nhưng thiếu/invalid token để kiểm chứng CsrfFilter. **Role test** dùng GET (safe method) để tránh CSRF can thiệp, giúp 403 có thể quy về thiếu ROLE_ADMIN. Hai loại 403 có cùng status nhưng khác nguyên nhân và cách khắc phục.

**csrf().useInvalidToken()** là helper chuyên để kiểm thử token invalid. **csrf().asHeader()** kiểm tra trường hợp client gửi token qua header; vẫn phải phù hợp CSRF repository/request handler của ứng dụng. Không thay bằng csrf().disable() trong test chỉ để POST được 200.

### Có phải mọi REST API phải bật CSRF?

CSRF threat chủ yếu khi browser tự động gửi credentials (session cookie, browser HTTP Basic cache...). Một API dùng bearer Authorization token mà browser không tự động đính kèm có thể có threat model khác và cho phép disable CSRF **chọn lọc**. Nhưng một ứng dụng có form login/cookie-based sessions cần bảo vệ POST login/logout và state-changing endpoints. Quyết định dựa trên **cách trình duyệt gửi credentials**, không dựa vào URL bắt đầu bằng /api hay nhãn “REST”.

## 10. Test HTTP Basic qua HTTP server thật (RANDOM_PORT)

MockMvc có chạy Spring Security filter chain nhưng **không mở socket hoặc browser thật**. Khi cần một bằng chứng bổ sung rằng Basic header được xử lý qua servlet server, ta dùng JDK HttpClient và random port. Test này **không kiểm tra session cookie**; nó kiểm tra actual HTTP challenge và valid Basic credentials.

**src/test/java/com/example/securityqa/RealHttpBasicTest.java**

~~~java
package com.example.securityqa;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Base64;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
@ActiveProfiles("demo")
class RealHttpBasicTest {

    @LocalServerPort
    private int port;

    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();

    @Test
    void basicCredentialsAreCheckedOverRealHttp()
            throws Exception {
        URI url = URI.create(
                "http://127.0.0.1:" + port + "/private");

        HttpRequest withoutCredentials = HttpRequest
                .newBuilder(url)
                .header("Accept", "application/json")
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        HttpResponse<String> denied = client.send(
                withoutCredentials,
                HttpResponse.BodyHandlers.ofString());

        assertEquals(401, denied.statusCode());
        assertTrue(denied.headers()
                .firstValue("WWW-Authenticate")
                .orElse("")
                .startsWith("Basic"));

        String base64 = Base64.getEncoder()
                .encodeToString(
                    "alice:alice-pass".getBytes(
                        StandardCharsets.UTF_8));

        HttpRequest withCredentials = HttpRequest
                .newBuilder(url)
                .header("Accept", "application/json")
                .header("Authorization", "Basic " + base64)
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        HttpResponse<String> allowed = client.send(
                withCredentials,
                HttpResponse.BodyHandlers.ofString());

        assertEquals(200, allowed.statusCode());
        assertTrue(allowed.body().contains(
                "\"user\":\"alice\""));
    }
}
~~~

**Kết quả dự kiến:** anonymous JSON request nhận **401** và **WWW-Authenticate: Basic**; request gửi Basic credentials hợp lệ nhận **200** và body JSON có user alice. Đây là test trên **HTTP loopback không mã hóa** với **credentials demo**; production Basic credentials phải đi qua HTTPS. Không đưa account thật vào test hoặc log HTTP Authorization headers.

### MockMvc vs RANDOM_PORT vs browser

| Cấp test | Chứng minh được | Chưa chứng minh |
| --- | --- | --- |
| Unit SecurityFilterChain matcher | Một số rule/config theo class | Authentication flow, Servlet/cookie runtime |
| MockMvc với Spring Security filters | Form POST, Basic header, CSRF, SecurityContext, role/session logic | TLS, reverse proxy, browser cookies, network |
| RANDOM_PORT + HttpClient | HTTP server/filter behavior, header, status/cookie response | Full browser navigation, SameSite policies thực |
| Playwright/Selenium browser E2E | Form HTML, cookies, redirect, CSRF hidden field, navigation | Backend internals/concurrency trừ khi có backend assertions |
| Production-like integration | Proxy/TLS/session store/distributed context | Không thay thế unit coverage |

**Không chọn một công cụ để chứng minh tất cả.** MockMvc thường là mức tốt nhất cho kiểm thử Spring Security filter chain nhanh và ổn định. RANDOM_PORT hữu ích để kiểm tra cấu hình HTTP thực; browser test cần khi UI/login form/cookies là contract quan trọng.

## 11. @WithMockUser và with(user()) tiện nhưng không phải login test

Ví dụ:

~~~java
@Test
@WithMockUser(username = "alice", roles = "USER")
void userRoleMayEnterPrivate() throws Exception {
    mvc.perform(get("/private"))
        .andExpect(status().isOk());
}
~~~

Đây là **trích đoạn** chưa có imports/class, không thuộc runnable tree. **@WithMockUser** tạo SecurityContext thử nghiệm, không xác thực mật khẩu qua UserDetailsService/PasswordEncoder và **không tạo form POST login/session persistence** như một browser thật.

Tương tự:

~~~java
mvc.perform(get("/private")
        .with(user("alice").roles("USER")))
    .andExpect(status().isOk());
~~~

Đây là request post processor cho authorization-focused tests, không chứng minh actual Basic header hay form credentials. Dùng những helpers này khi chỉ quan tâm **hasRole/hasAuthority/method security**; dùng **formLogin()** để kiểm tra form flow, **httpBasic()** để kiểm tra Basic flow, và session được lấy từ **real login request** để test persistence.

### Không tạo test context giả security policy

Với **@WebMvcTest**, phải biết slice có load filter chain và UserDetailsService/security config mong muốn không. Nếu @Import một test SecurityFilterChain dễ dãi hoặc disable filters, controller test có thể cho 200 dù production rule đòi ROLE_ADMIN. Khi requirement là security filter chain hoàn chỉnh, dùng **@SpringBootTest + @AutoConfigureMockMvc** hoặc slice có cấu hình SecurityFilterChain tương ứng và assert cả negative cases.

## 12. Session cookie, expiration và nhiều application instances

Một HTTP session thường được nhận diện bằng **JSESSIONID** hoặc tên cookie do app/container/Spring Session cấu hình. Cần phân biệt:

- **Session ID trên server** là token nhận diện state.
- **Cookie** là phương thức browser mang session ID sang request tiếp theo.
- **SecurityContextRepository** phục hồi authentication từ nguồn lưu SecurityContext.
- **HttpSession timeout** khiến session hết hạn, request sau phải đăng nhập lại theo rule.
- **Session fixation** đổi ID khi login; **logout** invalidate session.
- **Concurrent session management** có thể giới hạn số phiên mỗi user nhưng cần SessionRegistry/session event handling và test riêng.
- **Distributed deployments** có thể dùng **Spring Session** với Redis/JDBC thay HttpSession local; test phải xác minh session store và logout propagation qua nodes.

### Flags của cookie

Production browser app nên xem xét:
- **HttpOnly**: JavaScript không đọc cookie, giảm một phần nguy cơ lộ session cookie qua XSS nhưng không xóa mọi XSS rủi ro.
- **Secure**: browser chỉ gửi cookie qua HTTPS; không mặc định bật Secure trên HTTP local rồi không hiểu tại sao browser không lưu cookie.
- **SameSite**: ảnh hưởng cross-site cookie submission; cần chọn Lax/Strict/None theo flow thực và CSRF threat model. **SameSite không thay thế CSRF token trong mọi tình huống**.
- **Path/Domain**: giới hạn nơi browser gửi cookie; cần xét reverse proxy/base path.
- **Max-Age/Expires**: kiểm soát lifetime của persistent cookie, khác thời gian server-side session.

Một cấu hình minh họa chỉ dành cho profile **production HTTPS**:

~~~properties
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.timeout=15m
~~~

Đây là **trích đoạn config**, không thuộc runnable project; chọn các giá trị theo requirement thực, HTTPS/proxy và Spring Boot version. Đặc biệt, khi test RANDOM_PORT qua HTTP loopback, không áp Secure cookie config production rồi suy ra browser cookie lifecycle giống môi trường HTTPS.

### MockMvc không phải browser cookie jar

MockMvc có MockHttpSession, có thể truyền bằng .session(...) để mô phỏng state. Nó không tự vận hành cùng cơ chế browser gửi cookie, follow redirects, enforce SameSite/Secure và TLS. Nếu app có custom login page, reverse proxy, OAuth redirect hoặc session-cookie settings phức tạp, cần thêm browser/HTTP integration test. Một MockMvc test xanh **không chứng minh Chrome đã gửi cookie đúng trong mọi cross-site flow**.

## 13. Logout nâng cao: remember-me, Clear-Site-Data và token revocation

Default logout thường invalidate session và clear SecurityContext, nhưng các feature khác có lifecycle riêng:

**Remember-me cookies:** nếu app bật remember-me, cần verify remember-me cookie/token được xóa hoặc revoke, đặc biệt persistent token repository. Một logout session thành công không tự chứng minh remember-me state được dọn nếu custom logout handler sai.

**Custom authentication:** nếu app tự tạo token/passwordless/OAuth login, phải xác định token/session store cần revoke. Đặt SecurityContextHolder.clearContext() là không đủ nếu credentials/token vẫn có thể dùng lại.

**Clear-Site-Data**: HTTP response header có thể yêu cầu browser xóa cache/cookies/storage trong phạm vi được hỗ trợ; đây là client-side browser behavior và cần kiểm thử trên môi trường phù hợp. Không gọi nó là session invalidation server-side.

**Cookies:** Delete-Cookie hoặc Set-Cookie Max-Age=0 chỉ tác động phía client. Nên test cả **session server invalid** và **cookie response** khi đó là requirement.

**Logout success URL:** /login?logout trong demo là một redirect đơn giản. Khi custom logoutSuccessUrl khác, test phải assert URL mới và quyền anonymous truy cập endpoint success page. Nếu endpoint success bị SecurityFilterChain bảo vệ, browser có thể bị redirect loop.

**GET /logout:** với CSRF bật, thường là confirmation page, không phải một state-changing GET. Không viết custom GET endpoint để xóa session nếu không có thiết kế chống logout CSRF rõ.

## 14. Session timeout, concurrent login và security testing

### Session expiration

Muốn test timeout, đừng dùng Thread.sleep(900000) chờ 15 phút. Có thể dùng test session giả đánh dấu expire/invalidate trong unit/integration test, hoặc cấu hình TTL ngắn trên test profile và dùng timing có bounded wait. Kiểm tra:
1. Request đang authenticated.
2. Session hết hạn theo cơ chế được test.
3. Request mới không có authentication.
4. Server trả 401 hoặc redirect /login theo entry point.
5. Không rò SecurityContext từ thread/request trước.

Với Spring Session distributed store, cần chạy integration test store/TTL và replication nếu timeout là yêu cầu hệ thống.

### Concurrency và SessionRegistry

Nếu app giới hạn tối đa 1 session/user, cần cấu hình **maximumSessions**, xử lý expired sessions, SessionRegistry/HttpSessionEventPublisher theo runtime. Kiểm thử hai login sessions thực, xác nhận phiên cũ hoặc mới bị reject theo policy; không chỉ dùng một @WithMockUser rồi tuyên bố đã kiểm concurrency.

**Không bật session concurrency control mặc định** trong demo vì yêu cầu B335 tập trung form login, Basic, session và logout khi app sử dụng. Chỉ thêm advanced checks khi hệ thống thật có feature đó.

### Session fixation và custom login

Một custom success handler có thể quên save SecurityContext, bỏ session fixation strategy hoặc bỏ CSRF. Tests cần tạo pre-login session, login, assert ID change, kiểm tra next request, logout rồi assert invalid. Bộ test phần 5–8 bắt các regression phổ biến mà pure controller test không thấy.

## 15. Một vài khác biệt quan trọng: stateless API, OAuth2 và MFA

**Stateless bearer token API**: request cần Authorization: Bearer; thường không có form login hoặc HttpSession authentication. Logout server session không làm JWT đã ký biến mất; cần token revocation, short-lived access token và refresh-token rotation. Test bằng JWT/security-specific helpers và actual Authorization headers, không copy formLogin test.

**OAuth2/OIDC login**: redirect đến identity provider, state/nonce, callback, ID token và authentication principal khác; @WithMockOAuth2User có thể giúp controller test nhưng không thay integration login flow.

**MFA/2FA**: username/password đúng chưa đồng nghĩa fully authenticated theo application policy; test phải kiểm challenge và second factor, không cho protected URL trước MFA completion.

**Machine-to-machine Basic**: nếu vẫn dùng, credentials cần TLS, rotation, secret store, rate limiting và audit. Form login browser không phải phương án thích hợp cho machine client. Security test phải thể hiện ứng dụng đã chọn cơ chế phù hợp.

Bài ví dụ **không tự triển khai OAuth2/MFA/JWT** vì chúng có contract riêng. Điều quan trọng là **không mở những mechanisms ứng dụng không sử dụng**.

## 16. Test negative cases: không chỉ đo 200

Một security test có giá trị vì kiểm tra cả trường hợp **bị từ chối đúng cách**.

| Tình huống | Response kỳ vọng | Phải chứng minh thêm |
| --- | --- | --- |
| Anonymous vào trang cần auth bằng browser Accept | 302 -> /login | Đúng target redirect, không lộ dữ liệu |
| Anonymous API Accept JSON | 401 | Basic challenge nếu HTTP Basic được bật |
| Sai mật khẩu form | 302 -> /login?error | Unauthenticated, không tạo privileged session |
| Sai Basic credentials | 401 | Không vô tình dùng previous request auth |
| User thường vào /admin | 403 | Admin 200 để chứng minh rule không chặn tất cả |
| POST thiếu CSRF | 403 | Side effect không xảy ra |
| POST token CSRF sai | 403 | Không lộ dữ liệu |
| POST login hợp lệ | 302 + authenticated | New session request hoạt động |
| POST logout thiếu CSRF | 403 | Session vẫn hợp lệ |
| POST logout hợp lệ | 302 + invalidated session | Request mới không authenticated |
| User request sau session timeout | 401/302 | SecurityContext không còn |
| Basic request sau logout form vẫn có Basic header đúng | 200 có thể xảy ra | Logout không revoke password |
| Custom login success handler | Theo policy | Save SecurityContext đúng, session policy áp dụng |

**Phân biệt 401 và 403:** 401 thường nghĩa cần xác thực/challenge, 403 nghĩa đã bị từ chối do quyền hoặc CSRF. Khi form login chọn entry point, unauthenticated request có thể **302** thay vì 401. Đọc đúng context của request và security chain mới đánh giá được test.

## 17. Chạy Gradle và kết quả kỳ vọng

Cần Java 17+, Gradle Wrapper tương thích và dependencies từ Maven Central. Lệnh:

~~~bash
./gradlew clean test
./gradlew test --tests com.example.securityqa.FormLoginFlowTest
./gradlew test --tests com.example.securityqa.HttpBasicFlowTest
./gradlew test --tests com.example.securityqa.SessionFixationTest
./gradlew test --tests com.example.securityqa.LogoutFlowTest
./gradlew test --tests com.example.securityqa.CsrfAndRoleTest
./gradlew test --tests com.example.securityqa.RealHttpBasicTest
~~~

Trên Windows dùng **gradlew.bat** với cùng arguments. Các test được **thiết kế PASS nếu file/code/dependencies/config được tạo đúng như bài**, nhưng chưa có lần chạy Gradle nào được quan sát trong quá trình biên soạn. Khi dùng port 0/RANDOM_PORT, không assert port cụ thể.

### Bảng kết quả dự kiến

| Test | Điểm kiểm chứng |
| --- | --- |
| anonymousBrowserIsRedirectedToLogin | 302 -> /login |
| successfulFormLoginPersistsAuthenticationInSession | 302 -> /private, alice authenticated, session GET 200 |
| wrongPasswordIsRejected | 302 -> /login?error, unauthenticated |
| loginWithoutCsrfIsForbidden | 403 |
| validBasicCredentialsReachProtectedEndpoint | 200, user alice |
| anonymousJsonRequestGetsBasicChallenge | 401, WWW-Authenticate Basic |
| wrongBasicPasswordGetsUnauthorized | 401 |
| userRoleCannotEnterAdminArea | 403 |
| adminRoleMayEnterAdminArea | 200 |
| successfulLoginChangesExistingSessionId | oldId khác newId, authenticated session usable |
| postLogoutRequiresCsrfAndInvalidatesSession | 403 thiếu CSRF; POST có CSRF 302, session invalid |
| authenticatedPostWithoutCsrfIsForbidden | 403 |
| authenticatedPostWithValidCsrfIsAccepted | 200 |
| invalidCsrfTokenIsRejected | 403 |
| roleUserCannotAccessAdminEvenWithValidPassword | 403 |
| roleAdminCanAccessAdmin | 200 |
| publicEndpointDoesNotNeedLogin | 200 |
| basicCredentialsAreCheckedOverRealHttp | HTTP thật: 401 không header, 200 với Basic hợp lệ |

**Không khẳng định stdout BUILD SUCCESSFUL đã được quan sát.** Nếu test trên máy thật fail do version mismatch, nhiều filter chains hoặc CSRF repository custom, phải đọc stacktrace/security debug logs và đối chiếu chính xác configuration đang dùng.

## 18. Troubleshooting thực tế

| Triệu chứng | Nguyên nhân khả dĩ | Cách giải quyết |
| --- | --- | --- |
| MockMvc GET /private trả 200 cho anonymous | Security filters bị tắt, permitAll quá rộng | Dùng @AutoConfigureMockMvc với filters; inspect SecurityFilterChain |
| Form login luôn 403 | Thiếu CSRF token | Dùng formLogin() hoặc post(...).with(csrf()) trong test |
| POST /logout trả 403 | Thiếu CSRF | Gửi POST với csrf(), không disable global |
| Form login sai password lại redirect như success | Credentials/encoder fixture sai hoặc test chỉ assert 302 | Assert redirect URL và authenticated()/unauthenticated() |
| Browser GET /private trả 302 còn test mong 401 | Form entry point dựa Accept header | Đặt Accept và assert đúng entry point |
| API GET private trả 401 dù @WithMockUser trên test khác | Authentication chỉ cho test/request hiện tại | Không dùng state từ test khác |
| User USER vào admin trả 200 | hasRole/hasAuthority matcher sai | Assert both user forbidden and admin allowed |
| POST thiếu CSRF vẫn 200 | csrf disabled, matcher ignore quá rộng, filters bị bỏ | Kiểm tra CsrfFilter và matcher |
| Session login test GET sau lại redirect | Không truyền session, SecurityContext không lưu | Truyền MockHttpSession và kiểm tra SecurityContextRepository |
| Session ID không đổi khi login | Session fixation disabled/custom filter | Đặt đúng strategy, test session cũ và ID mới |
| Logout redirect đúng nhưng user vẫn authenticated | Custom logout quên invalidate/clear context | Assert session invalid + subsequent request |
| Dùng @WithMockUser rồi tin password đã được test | Helper bypass password login | Dùng formLogin/httpBasic với credentials thật |
| HTTP Basic logout rồi client vẫn login được | Credentials vẫn được gửi lại | Basic logout không revoke password |
| Browser cookie không được lưu trên HTTP localhost | Secure flag hoặc SameSite/cookie config | Test HTTPS profile hoặc đổi test cookie config |
| @WebMvcTest không chạy đúng role policy | Slice có security config khác production | @Import đúng config hoặc @SpringBootTest |
| Spring Boot có custom SecurityFilterChain mà login không hoạt động | FormLogin/Basic không được bật rõ | Kiểm tra DSL |
| Test phụ thuộc user/roles từ class trước | Shared state hoặc account fixture không rõ | Fixture riêng/isolated profile |
| Session timeout test flaky | Dùng Thread.sleep và wall-clock timing | Mock session timeout hoặc test TTL với bounded wait |
| RANDOM_PORT test fail khi đoán 8080 | Port được cấp ngẫu nhiên | @LocalServerPort |
| Login E2E qua reverse proxy sai redirect/cookie | Forwarded headers/base path/TLS | Test production-like proxy/browser |

### Logging và an toàn thông tin

Có thể bật **org.springframework.security=DEBUG** cục bộ để chẩn đoán matcher, filter chain và authentication flow. **Không log plaintext password, Basic Authorization header, session ID, CSRF token, authentication cookie** trong CI artifacts công khai. Không lấy các giá trị security secrets từ log/screenshot để tạo fixtures lâu dài.

Với app có nhiều SecurityFilterChain (browser + API), kiểm tra **securityMatcher** và **@Order** của mỗi chain; một API path vô tình match browser chain có thể trả 302 thay vì 401. Test riêng từng URL với Accept/Authorization tương ứng.

## 19. Khi muốn rút gọn test mà vẫn có bằng chứng

Có thể thiết kế một ma trận tối thiểu cho mỗi feature:

**Form login:** đúng mật khẩu + sai mật khẩu + thiếu CSRF + redirect target + session request kế tiếp.

**HTTP Basic:** đúng, sai, không có header, insufficient role; xác minh WWW-Authenticate và đảm bảo HTTPS ở deployment.

**Session:** login tạo/lưu authentication, session ID đổi, request sau có identity; nếu app có timeout/concurrency control, thêm tests riêng.

**Logout:** POST có/thiếu CSRF, invalidate session, clear authentication, access challenge sau logout. Nếu app dùng remember-me/custom tokens, thêm revoke/clear tests.

**Authorization/CSRF:** anonymous, USER, ADMIN và safe/non-safe method để phân biệt 401/403. Test một path public nhằm phát hiện cấu hình quá restrictive.

**Integration:** ít nhất một HTTP-level test nếu redirect/cookie/TLS/reverse-proxy là contract quan trọng; không bắt mọi unit test phải khởi server.

Bộ mẫu trình bày đầy đủ hơn ma trận tối thiểu để tách nguyên nhân lỗi khi học. Khi áp dụng project thật, giữ những cases bảo vệ rủi ro và yêu cầu thực, không sao chép tất cả tests cho mọi endpoint.

## 20. Bài tập tự kiểm tra

**1.** @WithMockUser(username="alice") có kiểm chứng mật khẩu alice không? **Không**, nó inject SecurityContext test, không chạy form/basic authentication.

**2.** Form login POST /login không CSRF mặc định ra sao? **403** khi CsrfFilter bật và token thiếu.

**3.** formLogin() trong spring-security-test có tự tạo CSRF token không? **Có**, helper thiết kế cho successful form request.

**4.** Tại sao chỉ assert 302 cho login chưa đủ? Vì cả success và failure đều có thể 302; assert **Location + authentication state**.

**5.** GET /private anonymous có luôn là 401 không? **Không** khi form login entry point có thể redirect 302 theo Accept/content negotiation.

**6.** HTTP Basic header dùng Base64 có mã hóa dữ liệu an toàn không? **Không**; bắt buộc HTTPS.

**7.** USER thiếu ROLE_ADMIN nhưng đã authenticated vào /admin trả gì? **403**.

**8.** 403 từ POST chắc chắn nghĩa thiếu role không? **Không**; có thể do thiếu/invalid CSRF token.

**9.** Muốn kiểm tra session persistence cần gì? Login thật, lấy session sau login và gửi một **request mới** với session đó.

**10.** Tại sao login cần đổi session ID? Để chống **session fixation**.

**11.** changeSessionId có nhất thiết tạo HttpSession object mới không? **Không**, có thể đổi ID trên cùng session object.

**12.** Spring Security 6 custom login tự set SecurityContextHolder có đủ cho request sau không? **Không chắc**; cần lưu vào **SecurityContextRepository**.

**13.** GET /logout có nên lập tức invalidate session khi CSRF bật không? **Không**, default thường là confirmation page; POST logout có CSRF là flow thay đổi state.

**14.** POST /logout thiếu CSRF có thể giữ session sống không? **Có**, token bị reject và logout filter không hoàn tất; test cần chứng minh.

**15.** Logout thành công cần kiểm tra gì ngoài redirect? **Session invalid**, SecurityContext không còn và request mới bị challenge.

**16.** Basic request với cùng credentials sau form logout có thể 200 không? **Có**, logout không thu hồi mật khẩu.

**17.** @AutoConfigureMockMvc(addFilters=false) có thích hợp để xác minh bảo mật không? **Không**, nó bỏ filter chain được test.

**18.** @WebMvcTest đơn giản có tự chứng minh production SecurityFilterChain đúng không? **Không** nếu config/filter khác; dùng đúng chain hoặc full context.

**19.** SessionCreationPolicy.STATELESS có phù hợp để test saved HttpSession authentication không? **Không**, đó là contract khác.

**20.** Khi app dùng bearer JWT thay form/session thì làm gì? Test bearer token/resource server và token lifecycle, **không** ép formLogin()/logout session.

**21.** Cookie Secure=true trong local HTTP browser có thể gây điều gì? Browser có thể không gửi/lưu cookie theo chính sách HTTPS, dẫn đến login loop trong browser test.

**22.** SameSite có thay thế toàn bộ CSRF protection không? **Không**, cần threat model và CSRF token phù hợp.

**23.** Tại sao MockMvc không chứng minh cookie SameSite trên browser thật? Vì MockMvc không chạy browser cookie jar/network/TLS.

**24.** Dùng @LocalServerPort để làm gì? Lấy đúng random port khi Spring Boot real server khởi động.

**25.** Khi chỉ cần test quyền ROLE_ADMIN, có bắt buộc test form login lại không? **Không**; @WithMockUser có thể thích hợp cho authorization-only test, nhưng cần ít nhất một integration test riêng cho authentication flow thực.

### Checklist QA cuối bài

- Có xác định app **thực sự dùng** form login/Basic/session/logout hay stateless bearer auth?
- Test có Spring Security filter chain thật, không addFilters=false?
- SecurityFilterChain custom có cấu hình rõ formLogin/httpBasic/logout/csrf theo policy?
- Có public URL, protected URL và role-limited URL để kiểm tra cả allow/deny?
- Form login test có đúng password, sai password, missing CSRF, redirect URL và authenticated assertion?
- Có GET protected trong request mới kèm **session từ login thật**?
- HTTP Basic test có actual Authorization header, wrong credentials, 401 challenge và role 403?
- CSRF tests có missing/invalid/valid token cho unsafe HTTP method?
- Không tắt CSRF toàn app chỉ để test xanh?
- Session fixation có assert **old ID khác new ID**, không nhầm session object identity?
- Logout test có POST + CSRF, invalidation, request mới không authenticated?
- Không giả định HTTP Basic logout đã revoke password?
- Có phân biệt 302, 401, 403 theo Accept headers/entry point?
- @WithMockUser chỉ dùng cho authorization-focused tests, không làm bằng chứng password/session?
- Cookie HttpOnly/Secure/SameSite, timeout và reverse proxy được test khi app có yêu cầu?
- Test data/accounts là fixture của profile an toàn, không lộ credentials thật?
- Không phụ thuộc thứ tự test hoặc session từ method trước?
- Đã xem xét remember-me, custom authentication, concurrency limit nếu app bật?
- Đã bổ sung RANDOM_PORT/browser integration cho phần network/cookie UI thật sự cần?
- Không tuyên bố build/run output đã quan sát khi chưa chạy Gradle?

**Kết luận:** Test Spring Security đúng cần **tái hiện cơ chế mà người dùng/client thật sử dụng**. Dùng **formLogin() + session request kế tiếp** để kiểm tra login và persistence; dùng **httpBasic()** để kiểm tra Authorization header và credentials; dùng **csrf()** để bảo vệ POST login/logout/action; dùng **role assertions** để phân biệt 401 và 403; dùng **session ID rotation + logout invalidation** để bảo vệ lifecycle. **@WithMockUser** là công cụ tốt cho authorization unit tests, nhưng không thay bằng chứng authentication flow thật. Với browser/cookie/TLS/reverse proxy, bổ sung HTTP/browser integration test khi cần.

## Tài liệu tham khảo chính thức

- Spring Boot 3.4 — Spring Security auto-configuration: https://docs.spring.io/spring-boot/3.4/reference/web/spring-security.html
- Spring Security — Testing form-based authentication with MockMvc: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/form-login.html
- Spring Security — Testing HTTP Basic: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/http-basic.html
- Spring Security — Testing CSRF: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
- Spring Security — Testing logout: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/logout.html
- Spring Security — Session management and fixation protection: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — Logout architecture and default handlers: https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html
- Spring Security — MockMvc setup with springSecurity(): https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html
- Spring Security — Form login architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html
