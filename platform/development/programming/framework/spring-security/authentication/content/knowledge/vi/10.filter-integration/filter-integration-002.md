# SecurityFilterChain, securityMatcher và phạm vi endpoint đăng nhập

> **Chủ đề:** Spring Security — authentication. **Nhóm:** Tích hợp bộ lọc. Bài học tập trung vào việc Spring Security chọn chuỗi bảo mật nào cho một HTTP request, ý nghĩa thực tế của `HttpSecurity.securityMatcher(...)`, sự khác biệt so với `authorizeHttpRequests().requestMatchers(...)`, và lý do `GET /login` hoặc `POST /login` có thể biến mất khi cấu hình phạm vi chuỗi sai. Mã minh họa dùng **Java 17**, **Spring Boot 3.5.16**, Spring Security 6.5.x và bài kiểm thử MockMvc.

## 1. Mục tiêu

Sau bài này, bạn sẽ có thể:

1. Mô tả `DelegatingFilterProxy`, `FilterChainProxy`, `SecurityFilterChain`, `HttpSecurity` và sự liên quan tới Servlet Filter.
2. Dự đoán chain được chọn cho một URL khi ứng dụng có nhiều `SecurityFilterChain` và `@Order`.
3. Phân biệt chain-level `securityMatcher` với authorization-level `requestMatchers`; hiểu tại sao `anyRequest()` chỉ bao trùm phần phạm vi đã được chain nhận.
4. Giải thích vì sao một cấu hình `formLogin()` vẫn không tạo endpoint khả dụng tại `/login` nếu `/login` nằm ngoài matcher.
5. Thiết kế đúng `loginPage`, `loginProcessingUrl`, logout, thành phần custom và trang mặc định.
6. Viết hai chain riêng cho REST API dùng HTTP Basic stateless và web dùng form login/session, có chain cuối an toàn.
7. Chạy integration test với GET/POST login, CSRF, Basic 401/200, role-based 403 và session crossover.
8. Chẩn đoán 404/401/403/302, redirect loop, matcher bị shadow, error dispatch và đường dẫn sau reverse proxy.
9. Tránh nhầm `permitAll` với bỏ qua filter chain và tránh endpoint được tạo mới không có bảo vệ.

## 2. Request đi vào Spring Security như thế nào?

Trong Servlet application, một request thường đi qua `DelegatingFilterProxy`, proxy này chuyển tiếp đến Spring bean tên `springSecurityFilterChain`. Bean đó là `FilterChainProxy`: nó có **danh sách các SecurityFilterChain** và kiểm `RequestMatcher` của từng chain theo thứ tự.

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["DelegatingFilterProxy"]
    B --> P["FilterChainProxy"]
    P --> M1{"Chain @Order(1) match?"}
    M1 -->|Có| F1["Chạy filters chain 1"]
    M1 -->|Không| M2{"Chain @Order(2) match?"}
    M2 -->|Có| F2["Chạy filters chain 2"]
    M2 -->|Không| M3{"Catch-all chain match?"}
    M3 -->|Có| F3["Chạy filters fallback"]
    M3 -->|Không| X["Không được Spring Security chain bảo vệ"]
    F1 --> END["Response hoặc chuyển sang Servlet"]
    F2 --> END
    F3 --> END
    X --> END
~~~

Quy tắc cốt lõi: **chain đầu tiên match sẽ được chọn, và các chain tiếp theo không được thực thi thêm**. Luật authorization, CSRF, authentication filters và session policy của một chain không tự động hợp nhất với chain khác.

Nếu **không chain nào khớp**, Spring Security không bảo vệ request bằng những security filters đã cấu hình. Điều đó **không đồng nghĩa luôn 403 hoặc 404**: nếu MVC có handler tương ứng, handler có thể được gọi; nếu không có handler thì kết quả phụ thuộc ứng dụng. Bỏ lọt URL ngoài mọi chain là nguy cơ đáng xem xét.

### Các thành phần trong pipeline

| Thành phần | Trách nhiệm | Không làm gì? |
| --- | --- | --- |
| `DelegatingFilterProxy` | Kết nối Servlet container với Spring-managed filter | Không tự chọn role |
| `FilterChainProxy` | Chọn SecurityFilterChain đầu tiên có matcher phù hợp | Không chạy tất cả chain |
| `SecurityFilterChain` | Định nghĩa matcher phạm vi và danh sách filters | Không tự sinh MVC controller |
| `HttpSecurity` | Builder tạo chain và cấu hình authentication, authorization, CSRF... | Không tự bảo vệ URL ngoài matcher |
| `UsernamePasswordAuthenticationFilter` | Xử lý POST form login tại processing URL đã cấu hình | Không render custom GET login page |
| `DefaultLoginPageGeneratingFilter` | Sinh GET login page mặc định khi cấu hình cho phép | Không sinh mọi custom page |
| `BasicAuthenticationFilter` | Kiểm header HTTP Basic nếu chain có cấu hình | Không tạo POST /api/login |
| `AuthorizationFilter` | Quyết định quyền đối với request đã vào chain | Không chọn chain đầu tiên |

## 3. securityMatcher khác requestMatchers như thế nào?

### securityMatcher — cổng vào toàn bộ chain

~~~java
http.securityMatcher("/api/**");
~~~

Chain chỉ được xem xét cho request khớp mẫu `/api/**`. Nếu request là `/login`, `/dashboard` hay một đường ngoài API, chain này không xử lý nó; `FilterChainProxy` thử chain tiếp theo.

`securityMatcher` không tự tạo endpoint, không tự thêm filter xác thực, không chỉ định ai được phép. Nó xác lập **phạm vi áp dụng** của các cơ chế cấu hình phía sau.

### requestMatchers — luật phân quyền bên trong chain

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .requestMatchers("/api/public/**").permitAll()
        .anyRequest().authenticated()
    );
~~~

Với đoạn trên, `requestMatchers("/api/admin/**")` chỉ được áp dụng **sau khi chain /api/** đã được chọn**. Phần `anyRequest()` cũng chỉ bao trùm các request khớp `securityMatcher` của chain. Nó **không** có nghĩa mọi URL của toàn ứng dụng đều đòi authentication.

| Câu hỏi | `securityMatcher(...)` | `authorizeHttpRequests().requestMatchers(...)` |
| --- | --- | --- |
| Cấp cấu hình | Toàn SecurityFilterChain | Luật authorization trong chain |
| Kết quả | Chain có được chọn không? | Request cần quyền gì? |
| Ảnh hưởng login/basic/bearer filter? | Có, vì filter chỉ chạy trong chain | Không tạo hoặc chuyển filter |
| Khi path không khớp | Thử chain sau | Thử luật authorization tiếp theo |
| `anyRequest()` liên quan | Không phải API này | Phần còn lại **trong chain** |
| Có tự tạo controller? | Không | Không |
| Có mở rộng phạm vi chain khi permitAll? | Không | Không |

**Hình dung:** `securityMatcher` là cổng vào tòa nhà. `requestMatchers` là quy tắc vào phòng sau khi đã qua cổng.

### Anti-pattern: permitAll một URL ngoài chain

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/login").permitAll()
        .anyRequest().authenticated()
    )
    .formLogin(Customizer.withDefaults());
~~~

Dù có `requestMatchers("/login").permitAll()`, `/login` vẫn **không thuộc `/api/**`**. GET/POST login không được chain này nhận. `permitAll` không thể sửa phạm vi của `securityMatcher`.

## 4. @Order và quy tắc first match wins

Giả sử có:

~~~text
@Order(1)  /api/admin/**  -> HTTP Basic + role ADMIN
@Order(2)  /api/**        -> HTTP Basic + authenticated
@Order(3)  không matcher  -> form login + catch-all
~~~

| Request | Chain chọn | Lý do |
| --- | --- | --- |
| GET `/api/admin/users` | 1 | Khớp admin ngay |
| GET `/api/orders` | 2 | Không admin, nhưng thuộc API |
| GET `/login` | 3 | Chỉ catch-all khớp |
| POST `/login` | 3 | Form login xử lý ở chain 3 |
| GET `/portal` | 3 | Catch-all bảo vệ |
| GET `/unmapped` | 3 | Vẫn qua security, sau đó MVC có thể 404 |

Nếu đặt catch-all ở `@Order(1)`, nó sẽ **nuốt mọi request**, khiến API chain sau không được chọn. Không tồn tại chuyện chain đầu sẽ dùng `httpBasic` của chain sau hoặc hai chain cộng gộp quyền.

### Cách kiểm một chain có bị shadow?

1. Liệt kê từng chain cùng matcher/`@Order`.
2. Viết request URL và HTTP method thật.
3. Đọc từ order nhỏ nhất đến lớn nhất.
4. Dừng ở matcher đầu tiên trả true.
5. Kiểm inventory các filters và luật authorization **của chính chain ấy**.

Với pattern trùng/bao nhau, đặt chain chuyên biệt trước, catch-all sau. Dùng integration test để tránh phụ thuộc thứ tự bean tình cờ.

### Tại sao nên có catch-all?

~~~java
@Bean
@Order(99)
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll())
        .build();
}
~~~

Đây là **snippet tích hợp** minh họa fallback đóng tất cả path còn lại. Khi fallback cần form login cho web, dùng `authenticated()` và `formLogin(...)` theo chính sách thay vì `denyAll()`. Điểm chính là **không đặt `securityMatcher`** nếu muốn nhận mọi URL chưa được chain trước xử lý.

Spring Security documentation khuyến nghị một chain không có matcher hẹp để tránh URL vô tình không được bảo vệ.

## 5. Endpoint đăng nhập có thể thuộc filter, không phải controller

Một cấu hình Servlet form login thường tự cung cấp:

- `GET /login`: trang HTML mặc định do `DefaultLoginPageGeneratingFilter` render, khi page mặc định được bật.
- `POST /login`: `UsernamePasswordAuthenticationFilter` xử lý username/password theo `loginProcessingUrl` mặc định.
- Redirect tới `/login` khi web page cần authenticated mà chưa có session.
- Xử lý success/failure theo configured handlers.
- Logout qua `LogoutFilter`, thường yêu cầu POST và CSRF token nếu CSRF bật.

**Điều kiện quan trọng:** filter sở hữu endpoint phải **nằm trong chain được chọn cho URL đó**. Cấu hình `formLogin()` không khiến URL tự được xử lý bên ngoài matcher của chain.

### 5.1. Form login mặc định

~~~java
@Bean
SecurityFilterChain web(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults());

    return http.build();
}
~~~

Không có `securityMatcher` hẹp nên `GET/POST /login` nằm trong chain. Trong cấu hình thông thường trang login được tạo tự động. Nếu custom `SecurityFilterChain` của mình không gọi `formLogin`, đừng mặc định rằng form login vẫn được bật như cấu hình auto mặc định trước đó.

### 5.2. URL GET và POST là hai công việc

| HTTP request | Tác nhân xử lý | Điều cần thiết |
| --- | --- | --- |
| `GET /login` mặc định | DefaultLoginPageGeneratingFilter | Form login mặc định và chain khớp |
| `POST /login` mặc định | UsernamePasswordAuthenticationFilter | Chain khớp, POST, `username`/`password`, CSRF |
| `GET /account/sign-in` custom | MVC controller + HTML template | Developer tự tạo trang GET |
| `POST /account/sign-in` custom | UsernamePasswordAuthenticationFilter nếu processing URL đặt tương ứng | Form action, method, fields, CSRF |
| `GET /api/report` Basic | BasicAuthenticationFilter kiểm Authorization header | Không cần route POST /api/login |
| `POST /logout` | LogoutFilter | Chain phù hợp, URL, CSRF/method, policy |

Không tạo controller `@PostMapping("/login")` khi muốn dùng filter form login mặc định: filter có thể nhận request **trước** controller, làm đường controller tưởng như “không bao giờ chạy”.

### 5.3. Lỗi phổ biến khi chain chỉ bảo vệ /secured/**

~~~java
@Bean
SecurityFilterChain restricted(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/secured/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

Giả sử chỉ có chain này:

1. `GET /secured/report` vào chain và được redirect tới `/login`.
2. Browser gọi `GET /login`.
3. `/login` **không match `/secured/**`**, nên filter sinh login page trong chain đó không chạy.
4. Nếu không có controller hoặc chain khác cung cấp `/login`, kết quả có thể là **404**.

Tài liệu Java Configuration của Spring Security minh họa chính xác điểm đáng ngạc nhiên này. Nếu có một chain khác khớp `/login`, response phụ thuộc chain ấy: có thể là 302, 401, 403 hoặc 404 theo cấu hình, chứ không phải “luôn 404”.

## 6. Ba cách sửa login endpoint bị lệch phạm vi

### 6.1. Cách A: chain chuyên biệt cho API, chain catch-all cho web

~~~java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain web(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

`GET/POST /login` vào web chain và có thể được xử lý bởi form login filters. API path vào API chain, không bị web form redirect nếu Basic entry point xử lý đúng. Đây là kiến trúc đơn giản để hiểu first-match.

### 6.2. Cách B: đưa login vào prefix được bảo vệ

~~~java
http
    .securityMatcher("/secured/**")
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated())
    .formLogin(form -> form
        .loginPage("/secured/login")
        .loginProcessingUrl("/secured/login")
        .permitAll()
    );
~~~

Lúc này URL `/secured/login` nằm trong matcher. Nhưng **đã dùng custom `loginPage`** nên developer **phải tự tạo GET /secured/login** bằng controller/template; Spring Security sẽ không tự sinh trang custom đó. POST cùng path do authentication filter xử lý, với form fields/CSRF phù hợp.

Logout cũng nên nằm đúng prefix nếu chain ấy là nơi quản lý logout:

~~~java
http.logout(logout -> logout
    .logoutUrl("/secured/logout")
    .logoutSuccessUrl("/secured/login?logout")
    .permitAll());
~~~

Không coi GET logout link là request logout thực trong cấu hình có CSRF; thường cần POST kèm token.

### 6.3. Cách C: matcher nhiều path có chủ đích

Có thể cho một chain nhận `/secured/**` **và** `/login`, `/logout` bằng overloads/RequestMatcher phù hợp. Nhưng khi dùng nhiều chain, cần rõ **chain nào sở hữu mỗi URL**. Không tùy tiện trộn custom login page thuộc chain A với POST processing filter thuộc chain B.

Với mọi cách, kiểm riêng **GET page, POST processing, success/failure redirect, logout và assets**; một URL xử lý thành công không chứng minh các URL khác đã được gắn đúng.

## 7. Ví dụ Spring Boot thực hành: API Basic và web form login

Ứng dụng gồm hai chain:

- Chain API `@Order(1)`: `securityMatcher("/api/**")`, `httpBasic`, `SessionCreationPolicy.STATELESS`, URL admin yêu cầu `ROLE_ADMIN`.
- Chain web `@Order(2)`: **không có securityMatcher** nên là catch-all, form login mặc định, session, logout và trang public.
- Người dùng demo `lan` có `ROLE_USER` và password BCrypt. Đây chỉ là account thử local.

Các request dự kiến:
- `GET /public/ping` trả 200.
- `GET /app/dashboard` chưa login redirect `/login`.
- `GET /login` trang generated form.
- `POST /login` không CSRF trả 403.
- `POST /login` đúng credential và CSRF tạo session.
- `GET /api/report` không Basic trả 401; với Basic đúng trả 200.
- `GET /api/admin/report` với lan đúng credential nhưng thiếu role trả 403.
- Session web không tự thay thế credential Basic khi gọi API stateless.

### 7.1. Cấu trúc project

~~~text
chain-scope-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/chainscope/
    │   ├── ChainScopeApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/example/chainscope/
        └── ChainScopeSecurityTests.java
~~~

### 7.2. settings.gradle

~~~groovy
rootProject.name = 'chain-scope-lab'
~~~

### 7.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot 3.5 thuộc dòng Spring Security 6.5 và hỗ trợ Java 17. Các version cố định phục vụ tái hiện bài lab; production phải theo BOM/các bản vá được hỗ trợ. Không trộn một Spring Security module mới với các module cũ không tương thích.

### 7.4. ChainScopeApplication.java

~~~java
package example.chainscope;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ChainScopeApplication {
    public static void main(String[] args) {
        SpringApplication.run(ChainScopeApplication.class, args);
    }
}
~~~

### 7.5. SecurityConfig.java

~~~java
package example.chainscope;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("lan")
                    .password(encoder.encode("demo123"))
                    .roles("USER")
                    .build());
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .httpBasic(Customizer.withDefaults());

        // API chỉ có GET trong demo, giữ CSRF mặc định.
        // Không tắt CSRF cho HTTP Basic một cách thiếu đánh giá.
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public/**", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults());

        // Không securityMatcher: chain này nhận mọi URL chưa vào API.
        return http.build();
    }
}
~~~

Vì web chain bắt mọi path còn lại, `GET /login` và `POST /login` đều thuộc chain có form login. `requestMatchers("/", "/public/**", "/error").permitAll()` chỉ đặt quyền cho public endpoints; `formLogin` mặc định cho phép login page/processing path tương ứng.

### 7.6. DemoController.java

~~~java
package example.chainscope;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    @GetMapping("/")
    public String index() {
        return "index";
    }

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/app/dashboard")
    public String dashboard(Authentication authentication) {
        return "dashboard:" + authentication.getName();
    }

    @GetMapping("/api/report")
    public String api(Authentication authentication) {
        return "api:" + authentication.getName();
    }

    @GetMapping("/api/admin/report")
    public String admin(Authentication authentication) {
        return "admin:" + authentication.getName();
    }
}
~~~

Không có controller `GET /login` hoặc `POST /login` trong ứng dụng: chúng được **Spring Security form login filters** cung cấp theo cấu hình mặc định.

### 7.7. ChainScopeSecurityTests.java

~~~java
package example.chainscope;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrlPattern;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ChainScopeSecurityTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointWorks() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void unauthenticatedWebRedirectsToLogin() throws Exception {
        mvc.perform(get("/app/dashboard"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void generatedLoginPageExists() throws Exception {
        mvc.perform(get("/login"))
            .andExpect(status().isOk())
            .andExpect(content().string(containsString("name=\"username\"")));
    }

    @Test
    void formLoginWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/login")
                .param("username", "lan")
                .param("password", "demo123"))
            .andExpect(status().isForbidden());
    }

    @Test
    void formLoginSessionDoesNotAuthenticateStatelessApi() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "lan")
                    .param("password", "demo123"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/app/dashboard").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("dashboard:lan"));

        mvc.perform(get("/api/report").session(session))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void apiWithoutBasicReturns401() throws Exception {
        mvc.perform(get("/api/report"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void apiWithBasicReturnsReport() throws Exception {
        mvc.perform(get("/api/report")
                .with(httpBasic("lan", "demo123")))
            .andExpect(status().isOk())
            .andExpect(content().string("api:lan"));
    }

    @Test
    void apiWithWrongBasicPasswordReturns401() throws Exception {
        mvc.perform(get("/api/report")
                .with(httpBasic("lan", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void apiAdminRoleCannotBeBypassed() throws Exception {
        mvc.perform(get("/api/admin/report")
                .with(httpBasic("lan", "demo123")))
            .andExpect(status().isForbidden());
    }
}
~~~

Đây là **test class đầy đủ** có 9 phương thức kiểm. Nó gửi request thật qua filters của Spring Security trong `MockMvc`, khác với `@WithMockUser` vốn có thể bỏ qua chính bước authentication cần kiểm.

### 7.8. Chạy và quan sát

Từ thư mục `chain-scope-lab`, dùng JDK 17+ và Gradle tương thích:

~~~bash
gradle test
gradle bootRun
~~~

Hoặc với Gradle Wrapper:

~~~bash
./gradlew test
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test
.\gradlew.bat bootRun
~~~

Các lệnh thử trên máy local:

~~~bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/login
curl -i http://localhost:8080/app/dashboard
curl -i http://localhost:8080/api/report
curl -i -u lan:demo123 http://localhost:8080/api/report
curl -i -u lan:demo123 http://localhost:8080/api/admin/report
~~~

Kết quả kỳ vọng theo cấu hình:

| Request | Kết quả | Vì sao |
| --- | --- | --- |
| GET `/public/ping` | 200, `pong` | Catch-all cho phép |
| GET `/login` | 200, HTML login | Catch-all có formLogin |
| GET `/app/dashboard` không session | 302 đến login | Web chain cần authenticated |
| GET `/api/report` không Basic | 401 | API chain Basic |
| GET `/api/report` Basic đúng | 200, `api:lan` | Provider xác thực hợp lệ |
| GET `/api/admin/report` Basic lan | 403 | ROLE_USER không đủ ROLE_ADMIN |
| POST `/login` không CSRF | 403 | CSRF được giữ ở web chain |
| POST `/login` đúng password+CSRF | Redirect + session | Form filter xử lý |
| GET API chỉ mang session web | 401 | API chain stateless không dùng session web |

**Không dùng demo credentials thật trong terminal:** `curl -u lan:demo123` chỉ là dữ liệu local giả. Trên hệ thống thật, dùng HTTPS và tránh lộ mật khẩu trong history/process list/logs. Đầu ra Gradle/Boot gồm nhiều log phụ thuộc runtime; không có một stdout cố định ngoài response API và assertions test.

### 7.9. Vì sao API được đặt STATELESS?

Session policy áp dụng **cho API chain**, nên một web session không trở thành bằng chứng được API chain Basic chấp nhận. `SecurityContext` vẫn tồn tại trong lúc xử lý một request Basic hợp lệ, nhưng không được lưu để request kế tiếp có thể dùng như login form.

`STATELESS` không có nghĩa mọi request trong JVM không có session: chain web có session riêng. Nó cũng không có nghĩa CSRF lúc nào cũng vô dụng; HTTP Basic trong browser có thể tạo điều kiện auto-send credentials, nên cần đánh giá với mutating methods.

## 8. Cấu hình custom login page trong một chain có prefix

Giả sử giao diện nghiệp vụ nằm trong `/portal/**`, muốn toàn bộ login/logout ở cùng prefix:

~~~java
@Bean
@Order(1)
SecurityFilterChain portal(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/portal/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/portal/login", "/portal/assets/**")
                .permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(form -> form
            .loginPage("/portal/login")
            .loginProcessingUrl("/portal/login")
            .failureUrl("/portal/login?error")
            .defaultSuccessUrl("/portal/home")
            .permitAll()
        )
        .logout(logout -> logout
            .logoutUrl("/portal/logout")
            .logoutSuccessUrl("/portal/login?logout")
            .permitAll()
        )
        .build();
}
~~~

Đây là **snippet tích hợp**, không phải ứng dụng thứ hai hoàn chỉnh. Cần có:
- MVC handler `GET /portal/login` và view/template hiển thị form;
- action `POST /portal/login`, fields `username`/`password`, CSRF token hợp lệ;
- handler `GET /portal/home` cho success redirect;
- chính sách cho các URL ngoài `/portal/**`, ví dụ fallback deny-all;
- logout method/CSRF theo cấu hình, assets và error routes.

Đã cấu hình `loginPage(...)` tùy biến nên **Spring Security không tự sinh GET page đó**. Nhưng `loginProcessingUrl(...)` khiến filter nhận POST đúng URL, miễn request vào chính chain.

### Sườn HTML minh họa cho custom page

~~~html
<form method="post" action="/portal/login">
  <label>User <input name="username" /></label>
  <label>Password <input type="password" name="password" /></label>
  <!-- Server/template engine phải render hidden CSRF field/token. -->
  <button type="submit">Sign in</button>
</form>
~~~

Đây là **sườn giải thích**, chưa có hidden CSRF field thực nên không đủ để hoạt động khi CSRF bật. Khi dùng Thymeleaf/JSP hoặc frontend riêng, phải truyền token theo contract của Spring Security. Không hardcode token hay tắt toàn bộ CSRF chỉ để form hoạt động.

## 9. So sánh tình huống lỗi và nguyên nhân

| Triệu chứng | Nhóm nguyên nhân cần kiểm | Hướng sửa |
| --- | --- | --- |
| GET `/login` trả 404 | Login page filter ở chain hẹp không match; custom GET không có | Kiểm chain match và controller GET |
| POST `/login` trả 404 | Không có UsernamePasswordAuthenticationFilter tại chain chọn; path sai | Kiểm loginProcessingUrl và chain |
| POST `/login` trả 403 | CSRF thiếu/sai, policy khác từ chối | Kiểm token, cookie/session, filter chain |
| POST login về `?error` | Sai credential/account status hoặc failure handler | Kiểm UserDetailsService/PasswordEncoder |
| API trả 302 /login | Request bị web chain nhận hoặc API chain bật form | Kiểm @Order/matcher/entry point |
| API trả 401 | Thiếu hoặc sai Basic/Bearer credential | Kiểm Authorization header |
| API trả 403 sau Basic đúng | Principal đủ bằng chứng nhưng thiếu authority | Kiểm role/permission |
| GET login redirect lặp | Page chưa được permit hoặc URL thành auth requirement | permitAll cho đúng chain |
| Public page vẫn 403 POST | CSRF filter hoạt động dù permitAll | Xác định CSRF policy |
| GET endpoint protected trả 200 không login | Ngoài mọi chain hoặc permitAll quá rộng | Catch-all và policy lại |
| Redirect success tới URL 404 | Endpoint đích không có MVC handler hoặc matcher sai | Kiểm successUrl và route |

**Không suy ra:** 404 nghĩa password sai hoặc Spring Security không có filter; 302 nghĩa authentication đã thành công; 401 nghĩa username không tồn tại. HTTP status là kết quả của nhiều lớp: matching, authentication, authorization, exception handling và MVC routing.

## 10. permitAll và web.ignoring khác nhau

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .anyRequest().authenticated());
~~~

`permitAll` chỉ bỏ yêu cầu xác thực/phân quyền đối với path phù hợp, trong khi security filters vẫn có cơ hội chạy: CSRF, security headers, context, custom filters.

Ngược lại, `web.ignoring().requestMatchers(...)` thuộc cấu hình bỏ qua cả Spring Security filter chain cho request. Với authentication endpoints, điều này **có thể vô hiệu filter cần xử lý POST login**, logout hoặc các headers/context quan trọng. Không dùng `ignoring("/login")` như bản sửa cho `securityMatcher` sai.

Nếu chỉ muốn asset công khai, thông thường có thể `permitAll` thay vì ignore để duy trì security headers. Trường hợp static resource đặc biệt cần ignore phải dựa trên đánh giá cụ thể và test.

## 11. CSRF, method và form login

Spring Security Servlet thường bật CSRF mặc định. Khi client POST form login, cần token hợp lệ. Trang default login do Spring Security tạo có cơ chế token tương ứng, còn trang custom do ứng dụng render phải thêm CSRF field/header đúng cách.

### Vì sao login đúng mật khẩu nhưng vẫn 403?

- POST vào chain có `CsrfFilter`.
- Request thiếu/CSRF token sai.
- `CsrfFilter` từ chối trước khi `UsernamePasswordAuthenticationFilter` xác thực.
- Login không thành công; không liên quan tới bcrypt, UserDetailsService hoặc password nhập đúng/sai.

Kiểm CSRF bằng integration test như ở trên. Không vội tắt CSRF ứng dụng để “sửa login”.

### HTTP Basic trong API có cần CSRF?

Đánh giá theo **cách credential tự được gửi**:
- HTTP Basic browser có thể cache và tự gửi credentials, nên request thay đổi trạng thái có khả năng chịu CSRF.
- Bearer token ở header được chủ động thêm bởi client có mô hình khác.
- JWT cất trong cookie vẫn có vấn đề CSRF dù JWT được ký.
- CSRF configuration là per-chain, không phải “/api/** thì chắc chắn disable”.

Trong demo API chỉ có GET, vì vậy giữ CSRF mặc định. Khi thêm POST/PUT/DELETE cho API, phải xác định mô hình client, credential và chính sách CSRF thực tế.

### GET và POST login khác nhau

Một URL `/login` được `securityMatcher` chọn chưa đủ: authentication filter còn có method matcher. `UsernamePasswordAuthenticationFilter` thông thường xử lý **POST**. GET dùng để render page. Nếu custom form gửi GET hoặc action URL sai, filter có thể không thực thi.

## 12. Context path, servlet path và reverse proxy

Matcher nhìn request theo môi trường Servlet/framework. Browser có thể truy cập `https://example.com/shop/api/report` nhưng ứng dụng chạy với context path hoặc proxy prefix, khiến đường mà Spring Security matcher so khớp khác đường bên ngoài.

Cần kiểm:
1. `server.servlet.context-path` và servlet mapping (`DispatcherServlet` có thể map dưới một base path).
2. Loại `RequestMatcher` đang dùng, MVC/PathPattern behavior và cấu hình Spring Security version.
3. Một số trường hợp cần matcher có servlet path/base path cụ thể.
4. HTTP method, trailing slash, URL encoding và chuẩn hóa path.
5. Reverse proxy forwarding headers được tin cậy; không lấy prefix từ header không kiểm soát làm policy.
6. Nhiều DispatcherServlet hoặc context Spring khác nhau.
7. GET login page, POST processing, redirects, OAuth callback, static assets sau proxy.

Không sửa matcher bằng cách thêm tiền tố mù quáng dựa trên URL trình duyệt; kiểm **request path thực đến server** trong test/log có kiểm soát.

## 13. Các cơ chế authentication khác cũng chịu phạm vi chain

| Cơ chế | Filter/URL cần chú ý | Hậu quả nếu URL ngoài chain |
| --- | --- | --- |
| Form login | Generated GET login, POST processing | Không có endpoint tương ứng |
| HTTP Basic | BasicAuthenticationFilter nhận header | API không được challenge Basic đúng ý |
| Bearer Resource Server | BearerTokenAuthenticationFilter | API có thể rơi vào form redirect hoặc không verify token |
| OAuth2/OIDC Login | Authorization redirect và callback URL | Login flow/callback không đến filter |
| SAML2 Login | Authentication request và response endpoints | SAML callback không được xử lý |
| Logout | LogoutFilter và success page | Logout không chạy hoặc URL success không hợp lệ |

Một config `httpBasic()` **không tự tạo** `POST /api/login` để lấy JWT. HTTP Basic xác thực credentials ngay trong HTTP request. Nếu ứng dụng tự xây token issuance endpoint, đó là thiết kế API authentication riêng, phải kiểm method/path/filter, credential, token signing, rate limit và policy bảo mật.

Các URL OAuth2/SAML phụ thuộc registration và configurer; luôn kiểm đúng **filter-owned endpoints** nằm trong `securityMatcher` của chain tương ứng.

## 14. Cách debug hiệu quả bằng FilterChainProxy

Trong môi trường development, bật log vừa đủ:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Sau đó với từng request, xác định:
1. HTTP method/path/servlet mapping thật.
2. Chain nào được `FilterChainProxy` chọn?
3. Chain có filter cần thiết (`UsernamePasswordAuthenticationFilter`, Basic, Bearer...) không?
4. GET và POST có vào cùng kiến trúc authentication đã thiết kế không?
5. `loginProcessingUrl`, form action, parameter names và CSRF có đúng?
6. Authorization là `permitAll`/authenticated/role nào trong chain?
7. Authentication success/failure redirect tới path nào?
8. URL fallback có được bảo vệ không?

**Không bật DEBUG bừa trong production:** giới hạn thời gian, quyền truy cập log và tránh lộ Authorization header, cookies, session ID, password, JWT, Principal hoặc full SecurityContext.

### Bảng URL owner nên viết trước khi triển khai

| URL | Method | Owner | Chain đúng | Policy |
| --- | --- | --- | --- | --- |
| `/login` | GET | DefaultLoginPageGeneratingFilter | web | public |
| `/login` | POST | UsernamePasswordAuthenticationFilter | web | public + CSRF |
| `/app/dashboard` | GET | MVC controller | web | authenticated |
| `/public/ping` | GET | MVC controller | web | permitAll |
| `/api/report` | GET | MVC controller | API | Basic authenticated |
| `/api/admin/report` | GET | MVC controller | API | Basic + ADMIN |
| `/logout` | POST | LogoutFilter | web | CSRF/logout policy |

Bảng này giúp xác định **đúng chain** trước khi sửa `requestMatchers`. Khi một URL được nhiều chain matcher khớp, chain ưu tiên cao hơn sẽ là owner thực tế.

## 15. Kiểm thử bảo vệ phạm vi: không chỉ happy path

Một checklist test nên có:

| Case | Điều cần khẳng định |
| --- | --- |
| API không credential | 401/challenge, không bị web redirect |
| API Basic sai password | 401, không cấp authenticated result |
| API Basic đúng | Đúng principal và endpoint body |
| API thiếu role | 403, không vượt ADMIN |
| Web chưa login | Redirect đến login page |
| GET default login | 200 và có form fields |
| POST login thiếu CSRF | 403 và không có session authenticated |
| POST login đúng + CSRF | Auth thành công, session web |
| Session web gọi API stateless | Không thay Basic credential |
| Catch-all security | Endpoint ngoài API không vô tình bypass |
| Custom login URL | GET page, POST processing, failure/success redirect hợp lệ |
| Shadowed chain | @Order không để chain generic nhận nhầm API |
| Logout | POST đúng method/CSRF/session |
| 404 after auth | MVC path không tồn tại, không nhầm là filter missing |
| Reverse proxy/context path | Matcher và redirects ở production khớp |
| New controller | Không vô tình public do không có chain |
| Error dispatch | Không redirect loop hoặc expose stack trace |

`@WithMockUser` hữu ích cho authorization test, nhưng **không thay** kiểm thử form processing URL hay HTTP Basic filters. Bài lab dùng MockMvc request với `httpBasic` và form POST thật vì đó là cách chứng minh matcher/filter hoạt động.

### Test một endpoint ngoài chain

Nếu ứng dụng chỉ có:

~~~java
http.securityMatcher("/api/**");
~~~

và có controller `GET /admin/secret` ngoài `/api/**`, Spring Security chain ấy không bảo vệ controller. Bài test đòi authenticated/deny phải phát hiện, không chỉ kiểm API. Thêm catch-all chain với luật an toàn để giảm rủi ro này.

## 16. Hai tầng lỗi: URL thuộc chain và URL thuộc route

Tình huống dễ nhầm:

~~~text
GET /some-page
 -> có SecurityFilterChain match
 -> user đã authenticate
 -> controller không có mapping /some-page
 -> DispatcherServlet 404
~~~

Đây **không phải** bằng chứng chain bị thiếu. Ngược lại:

~~~text
GET /login
 -> không chain nào match
 -> DefaultLoginPageGeneratingFilter không có cơ hội chạy
 -> không MVC controller /login
 -> 404
~~~

Hai kết quả HTTP giống nhau nhưng nguyên nhân khác. Trong debug, cần xác định chain selection **trước** khi xem handler mapping, sau đó mới xem authentication/authorization và MVC 404.

Với login custom, `loginPage("/portal/login")` **không tự tạo MVC GET**, còn `loginProcessingUrl("/portal/login")` cấu hình POST filter processing. Test hai path/method riêng.

## 17. Anti-pattern cần tránh

1. Đặt `requestMatchers("/login").permitAll()` nhưng `securityMatcher` không nhận `/login`.
2. Chỉ có một chain `/api/**` và giả định mọi endpoint khác cũng được bảo vệ.
3. Đặt catch-all `@Order(1)` che hết chain chuyên biệt.
4. Tưởng tất cả chains đều chạy cùng một request.
5. Dùng formLogin mặc định trong chain `/secured/**` mà quên endpoint `/login`.
6. Cấu hình custom loginPage nhưng không có GET controller.
7. Form action khác loginProcessingUrl hoặc dùng GET thay POST.
8. Bỏ CSRF để chữa 403 login mà không đánh giá bảo mật.
9. Dùng `web.ignoring("/login")` khiến processing filter không chạy.
10. Tưởng permitAll bỏ qua toàn bộ filters.
11. Tưởng Basic tạo POST endpoint cấp JWT.
12. Tưởng `anyRequest()` bảo vệ các URL nằm ngoài chain.
13. Nhầm MVC 404 với filter login bị mất.
14. Đọc HTTP 302 rồi coi đó là login success mà không kiểm đích redirect.
15. Dùng session web cho API đã cấu hình stateless.
16. Không kiểm logout URL/method/CSRF.
17. Đặt role ADMIN ở authorization của chain không được chọn.
18. Không có regression tests cho GET và POST login.
19. Dùng `@WithMockUser` làm bằng chứng password authentication hoạt động.
20. Không kiểm context path/servlet mapping khi deploy sau proxy.
21. Thiếu fallback chain và vô tình công khai controller mới.
22. Tạo API Basic nhưng để URL rơi vào form redirect.
23. Tắt security headers với các public pages bằng ignoring không cần thiết.
24. Không phân biệt lỗi 401 vì thiếu credential và 403 vì thiếu quyền.
25. Bật logging chứa tokens/password để debug matcher.
26. Đặt nhiều chains trùng pattern nhưng không định nghĩa order.
27. Giữ trang login trong chain A, processing filter ở chain B mà không kiểm security flow.
28. Không biết `/error` và dispatcher type có thể chịu authorization policy riêng.

## 18. Câu hỏi tự kiểm tra

**1. `securityMatcher("/api/**")` nghĩa là mọi URL khác trả 403?**  
Không. URL không khớp chain này sẽ thử chain tiếp; nếu không có chain nào match, Spring Security không bảo vệ URL đó bằng chain.

**2. `requestMatchers("/login").permitAll()` có mở rộng phạm vi chain /api/** không?**  
Không. Nó chỉ là một luật authorization trong chain đã chọn.

**3. Vì sao bật `formLogin` nhưng GET /login trả 404?**  
GET login page có thể ngoài `securityMatcher` hoặc custom page chưa có GET MVC handler; cần xác định chain nào nhận URL.

**4. Nếu catch-all có @Order(1), API chain @Order(2) thì GET /api/report vào đâu?**  
Catch-all được chọn trước; API chain không chạy.

**5. `anyRequest().authenticated()` trong chain /secured/** có bảo vệ /admin/** không?**  
Không, vì /admin/** không qua matcher của chain đó.

**6. Custom `loginPage("/portal/login")` có cần controller GET?**  
Có. Spring Security không sinh trang GET tùy biến; filter có thể xử lý POST nếu processing URL khớp.

**7. POST login trả 403 dù mật khẩu đúng: kiểm gì trước?**  
CSRF token, chain matching, form action/method và filters; không vội đổi PasswordEncoder.

**8. HTTP Basic có làm POST /api/login tự xuất hiện không?**  
Không. Nó xác thực header Basic trên request.

**9. API Basic đúng mật khẩu nhưng thiếu ROLE_ADMIN thường trả gì?**  
403 Forbidden, khác 401 chưa authenticated.

**10. `permitAll` có bỏ qua CsrfFilter không?**  
Không. Đây là quyết định authorization, không loại CSRF filter.

**11. Session form login web có tự hợp lệ tại API Basic stateless không?**  
Không theo cấu hình lab; API không dùng session để khôi phục SecurityContext.

**12. Tại sao nên có catch-all chain?**  
Để các URL mới/không thuộc chain chuyên biệt vẫn chịu chính sách bảo mật.

**13. `GET /login` 200 có chắc POST /login đã xử lý đúng không?**  
Không. Phải test POST với credential, CSRF và đúng processing matcher.

**14. Vì sao không xem `redirectedUrl` là một controller route được Spring Security tạo?**  
Redirect chỉ chỉ định URL đích; URL đó vẫn cần filter/handler phù hợp.

**15. Có thể tắt CSRF vì API stateless và JWT ở cookie không?**  
Không suy ra được; cookie có thể tự gửi và chịu CSRF. Đánh giá theo credential thực.

**16. Một request đã xác thực nhận 404: có nhất thiết do thiếu SecurityFilterChain không?**  
Không. MVC có thể không có handler dù request đã qua chain.

## 19. Checklist production

- [ ] Liệt kê toàn bộ SecurityFilterChain beans, matcher và @Order.
- [ ] Xác định request nào vào chain nào, kể cả error dispatch và URLs mới.
- [ ] Có chain catch-all an toàn.
- [ ] Mỗi chain chứa authentication mechanism phù hợp (form, basic, bearer, oauth2...).
- [ ] GET login page và POST processing URL đều nằm trong đúng chain.
- [ ] Custom login page có MVC GET, template, form action, fields và CSRF.
- [ ] Success/failure redirect và logout URLs có route/chain/policy hợp lệ.
- [ ] Không dùng permitAll để cố vượt securityMatcher.
- [ ] Không dùng web.ignoring cho login processing endpoint.
- [ ] API chain trả Basic/Bearer response phù hợp thay vì form redirect ngoài ý muốn.
- [ ] Phân biệt authentication (401/redirect) và authorization (403).
- [ ] Kiểm CSRF theo cơ chế cookie/Basic/Bearer và HTTP method.
- [ ] Session policy đúng cho API stateless và web session-based.
- [ ] Context path/servlet path/reverse proxy được test.
- [ ] Có test GET/POST login, CSRF fail, role 403, API 401/200, logout, catch-all.
- [ ] Không chỉ dùng @WithMockUser cho test auth filters.
- [ ] Không log secrets khi debug FilterChainProxy.
- [ ] Re-run integration tests sau mỗi lần đổi matcher/order/login URL.

**Thông điệp chính:** `SecurityFilterChain` là bộ filter áp dụng cho một request; `securityMatcher` là ranh giới **chọn chain**, còn `requestMatchers` đặt quyền **bên trong chain được chọn**. Các endpoint đăng nhập do security filters cung cấp chỉ hoạt động khi URL thực sự đi vào chain có các filters ấy. Đặt thứ tự và phạm vi đúng, giữ catch-all an toàn, kiểm cả GET và POST login và dùng request-based integration tests sẽ tránh được phần lớn lỗi đăng nhập “có cấu hình nhưng không tồn tại”.

### Tài liệu tham khảo chính thức

- Spring Security — Java Configuration / Multiple HttpSecurity / SecurityFilterChain Endpoints: https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html
- Spring Security — Authorize HttpServletRequests / Security Matchers: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security — Form Login: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html
- Spring Security — HTTP Basic: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html
- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security — CSRF: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Spring Security — SecurityFilterChain API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/SecurityFilterChain.html
- Spring Boot 3.5 — System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html
