# Cấu hình bảo mật bằng Spring bean và Lambda DSL

> **Phạm vi:** Spring Security dành cho **Servlet/Spring MVC**, Java 17+, Spring Boot 3.x và Spring Security 6.x. Bài học giải thích cách tạo cấu hình bảo mật hiện đại bằng các **Spring bean**, đọc đúng **Lambda DSL** của **HttpSecurity**, kết hợp cơ chế xác thực với phân quyền, tách nhiều filter chain, kiểm thử thực tế và chuẩn bị cho Spring Security 7. Các ví dụ chạy đầy đủ tập trung vào một ứng dụng API dùng HTTP Basic để người học quan sát được kết quả 200/401/403.

## 1. Vì sao cấu hình bằng bean và Lambda DSL?

Trong các dự án Spring Security cũ, bạn có thể thấy lớp kế thừa **WebSecurityConfigurerAdapter**, ghi đè **configure(HttpSecurity)**, gọi **.and()** để quay về builder cha. Cách đó không còn phù hợp cho ứng dụng mới:

- **WebSecurityConfigurerAdapter** đã bị loại bỏ khỏi Spring Security 6.
- Từ Spring Security 5.2, framework hỗ trợ **Lambda DSL**. Đây là cách cấu hình được ưu tiên ở dòng 6.x.
- Từ Spring Security 7, cú pháp Lambda DSL trở thành phương thức bắt buộc cho việc cấu hình HTTP security; kiểu chain không dùng lambda với **.and()** từ tài liệu cũ không còn là hướng nâng cấp hợp lệ.
- Spring Boot quản lý các component qua **IoC container**; bạn công bố một **@Bean SecurityFilterChain** để mô tả chính sách bảo vệ HTTP của ứng dụng.

Mẫu hiện đại tối giản:

~~~java
@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Đây là **snippet cấu hình**, cần các import và dependency Spring Security để biên dịch; phần 5 cung cấp ứng dụng hoàn chỉnh. Từ mẫu này bạn đã thấy ba ý:

1. **@Configuration** cho biết Spring quản lý lớp chứa các khai báo bean.
2. **@Bean** công bố một **SecurityFilterChain** với chính sách cụ thể.
3. **authorizeHttpRequests(authorize -> ...)** và **httpBasic(Customizer.withDefaults())** là cú pháp Lambda DSL, không yêu cầu tự gọi **.and()**.

**Bean SecurityFilterChain không tự tạo người dùng.** Quy tắc “mọi request cần authenticated” nói về **authorization**, còn nguồn username/password, password hash hoặc token validation là **authentication**; chúng được cấu hình thêm qua bean/cơ chế riêng.

## 2. Hiểu vai trò của Spring bean

Một bean là đối tượng được **Spring ApplicationContext** khởi tạo, quản lý vòng đời và cung cấp cho thành phần cần dùng thông qua dependency injection.

Đối với ứng dụng Spring Boot/Spring Security, các bean liên quan có thể gồm:

| Bean/đối tượng | Tại sao cần | Thường khai báo ở đâu |
| --- | --- | --- |
| **SecurityFilterChain** | Chọn filter và rule bảo vệ HTTP request | Method **@Bean** nhận HttpSecurity |
| **PasswordEncoder** | Kiểm tra raw password với hash đã lưu; mã hóa trước khi lưu | Bean cấu hình hoặc component thích hợp |
| **UserDetailsService** | Tải user/authorities/flags khi xác thực username/password | Bean hoặc **@Service** |
| **AuthenticationProvider** | Thực hiện một loại xác thực cụ thể | Bean khi cần provider tùy biến |
| **AuthenticationManager** | Điều phối các provider | Thường do framework cấu hình; tự khai báo khi kiến trúc cần |
| **CorsConfigurationSource** | Cung cấp CORS policy cho security chain khi cần | Bean cấu hình riêng |
| **AuthorizationManager** | Thực hiện logic cấp phép theo request/method | API mặc định hoặc bean/policy tùy biến |
| **SecurityFilterChain nhiều instance** | Tách chính sách của API và web | Nhiều bean kèm matcher và thứ tự rõ |

Không phải ứng dụng nào cũng phải tự khai báo toàn bộ bảng trên. **Ưu tiên cơ chế/framework mặc định phù hợp**, chỉ tạo bean tùy biến khi cần thay hành vi. Định nghĩa quá nhiều provider hoặc manager cạnh tranh có thể khiến request đi qua thành phần khác dự kiến.

### 2.1. @Configuration, @Bean và dependency injection

Ví dụ:

~~~java
@Configuration
class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice123"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(alice);
    }
}
~~~

Đây là **snippet**, cần các import và project Spring Security. Spring inject **PasswordEncoder** vào method **users(...)**, nên ta không cần tạo một encoder thứ hai bằng **new BCryptPasswordEncoder()** trong method này. **BCryptPasswordEncoder** có salt; dùng **matches** để so khớp raw password với hash, không so sánh hai chuỗi hash bằng equals.

Có thể dùng **@Service** để Spring tự phát hiện class implements **UserDetailsService**, thay vì tạo bean trong cấu hình. Hãy chọn một cách khai báo có chủ đích, tránh vô tình cung cấp hai bean UserDetailsService cùng loại khiến authentication wiring không rõ ràng.

### 2.2. @EnableWebSecurity có bắt buộc trong Spring Boot?

Trong ứng dụng Spring Boot Servlet có starter-security và auto-configuration thông thường, **không cần thêm @EnableWebSecurity chỉ để một @Bean SecurityFilterChain có hiệu lực**. Nhiều ví dụ của thư viện Spring Security độc lập vẫn đặt @EnableWebSecurity một cách tường minh.

**@EnableMethodSecurity** là phần riêng: khi muốn dùng **@PreAuthorize**, **@PostAuthorize** và các annotation method security, cần bật cơ chế tương ứng. Chỉ có bean SecurityFilterChain không tự làm mọi annotation method-level được thực thi.

### 2.3. Khi bạn khai báo SecurityFilterChain, Spring Boot còn tự làm gì?

Spring Boot mặc định bảo vệ web khi có Spring Security trên classpath. **Khai báo bean SecurityFilterChain** làm cấu hình **web security mặc định của Boot lùi bước**; các matcher, authorization rule và cơ chế đăng nhập trong chain mới là do bạn thiết kế.

Điều đó **không tự tắt bean tài khoản in-memory mặc định**. Auto-configuration cho **UserDetailsService** là phần khác; một bean **UserDetailsService**, **AuthenticationProvider** hoặc **AuthenticationManager** phù hợp có thể làm cấu hình nguồn user mặc định của Boot lùi bước. Khi dùng OAuth2 module, các điều kiện auto-configuration cũng có thể khác; cần kiểm tra cấu hình thật.

Nếu ứng dụng vẫn in ra **Using generated security password**, điều đó không chứng minh SecurityFilterChain của bạn bị bỏ qua. Nó có thể cho biết bạn mới tùy chỉnh **web chain** mà chưa thay **nguồn user**. Ví dụ đầy đủ phía dưới chủ động khai báo cả hai.

## 3. Đọc Lambda DSL đúng cách

Lambda DSL có dạng:

~~~java
http
    .authorizeHttpRequests(authorize -> authorize
        .requestMatchers(HttpMethod.GET, "/public").permitAll()
        .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
        .anyRequest().authenticated()
    )
    .httpBasic(Customizer.withDefaults());
~~~

**Giải mã cú pháp:**

- **http** là **HttpSecurity**: builder tổng thể của servlet security.
- **authorizeHttpRequests(...)** nhận một **Customizer** (lambda) để cấu hình nhóm rule authorization.
- **authorize** là tham số lambda do framework cấp; tên biến chỉ để dễ đọc, có thể đặt **auth**, **rules** hoặc tên khác.
- **requestMatchers(...)** giới hạn request được rule xét theo path/method.
- **permitAll**, **authenticated**, **hasRole** và **hasAuthority** là quyết định quyền trong một rule.
- **Customizer.withDefaults()** là cách viết ngắn cho một lambda không thay đổi các option mặc định của feature đang bật, tương đương về ý định với **basic -> {}**.
- **http.build()** tạo **SecurityFilterChain** bean. Hãy gọi **build()** sau khi cấu hình xong.

**Không cần gọi .and()** để thoát khỏi từng nhánh. Khi lambda kết thúc, bạn tiếp tục cấu hình trên **HttpSecurity** trong chuỗi builder ngoài.

### 3.1. So sánh cách cũ và Lambda DSL

**Cách cũ, chỉ để nhận diện khi đọc legacy code:**

~~~java
// Phong cách cũ; không nên dùng cho Spring Security 7.
http
    .authorizeHttpRequests()
        .requestMatchers("/public").permitAll()
        .anyRequest().authenticated()
        .and()
    .httpBasic();
~~~

**Cách được ưu tiên:**

~~~java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/public").permitAll()
        .anyRequest().authenticated()
    )
    .httpBasic(Customizer.withDefaults());
~~~

Hai đoạn thể hiện cùng **ý định policy** khi đặt trong môi trường phiên bản tương ứng. Đoạn cũ không phải hướng viết mới hay cam kết chạy ở mọi version. Từ 7.x cần cú pháp Lambda DSL.

### 3.2. Lambda rỗng và Lambda có cấu hình

Muốn bật HTTP Basic theo mặc định:

~~~java
.httpBasic(Customizer.withDefaults())
~~~

Muốn cấu hình login page trong một ứng dụng web:

~~~java
.formLogin(form -> form
    .loginPage("/login")
    .permitAll()
)
~~~

Snippet form login đòi hỏi ứng dụng có **GET /login** để render trang do bạn thiết kế và có **POST /login** phù hợp để filter xử lý credential; nếu chỉ thay **loginPage** mà không cung cấp trang, người dùng có thể gặp **404**. Khi muốn dùng trang đăng nhập do Spring Security tạo, có thể dùng **formLogin(Customizer.withDefaults())** và để framework xử lý mặc định.

Khi tự thay AuthenticationEntryPoint, RequestCache, login success handler hoặc logout URL, hãy thiết kế cả hành vi browser và HTTP response; có thể cần thay đổi CSRF/session policy.

### 3.3. Lambda không tự đặt policy an toàn

Đây là cấu hình rất rộng:

~~~java
http.authorizeHttpRequests(auth -> auth
    .anyRequest().permitAll()
);
~~~

Nó cho phép mọi request trong chain đi tiếp qua bước authorization, kể cả controller mới thêm. Lambda DSL **không tự bảo đảm quyền tối thiểu**: bạn vẫn phải xét cẩn thận endpoint public, protected, admin, các method và quyền theo resource.

Thứ tự các **requestMatchers** cũng quan trọng: rule đầu tiên khớp sẽ được dùng. Một rule bao trùm như **/api/** đứng trước rule yêu cầu ADMIN ở **/api/admin/** có thể khiến logic chi tiết không bao giờ được dùng.

## 4. Authentication, authorization và filter chain là ba phần khác nhau

Với HTTP request:

~~~text
Browser / API client
       |
       v
Servlet container -> DelegatingFilterProxy
       |
       v
FilterChainProxy
       |
       +--> Chọn SecurityFilterChain đầu tiên khớp request
                  |
                  +--> Context / headers / CSRF / CORS filters (tùy cấu hình)
                  |
                  +--> Authentication filter (Basic, form login, bearer...)
                  |       |
                  |       +--> AuthenticationManager
                  |       +--> UserDetailsService + PasswordEncoder
                  |            hoặc JwtDecoder, introspector...
                  |
                  +--> AuthorizationFilter
                          |
                          +--> ALLOW -> Controller / Service
                          |
                          +--> DENY -> exception translation -> HTTP response
~~~

**Authentication** xác minh credential để tạo danh tính. **Authorization** đánh giá có quyền truy cập hay không. **SecurityFilterChain** kết nối các filter thực thi những hành vi đó.

Ví dụ, **requestMatchers("/admin").hasRole("ADMIN")** chỉ định điều kiện cấp quyền. Nếu không bật hoặc không cấu hình bất kỳ cơ chế authentication nào phù hợp, người dùng không tự có credential hợp lệ chỉ vì rule có chữ ADMIN. Ngược lại, bật Basic mà để **permitAll** quá rộng có thể làm lộ tài nguyên dù có bước xác thực.

### 4.1. HttpSecurity chỉ mô tả một chain

Mỗi bean **SecurityFilterChain** được xây dựng từ HttpSecurity; bean được tạo lúc khởi động, không phải tự chạy code **securityFilterChain(...)** mỗi request. Khi có request, **FilterChainProxy** chọn chain rồi chạy filters đã được tạo.

Một chain có thể bao phủ tất cả URL nếu không đặt giới hạn matcher, hoặc chỉ áp dụng cho phạm vi cụ thể qua **securityMatcher**.

- **securityMatcher(...)**: chọn request nào thuộc **chain**.
- **requestMatchers(...)** bên trong **authorizeHttpRequests(...)**: rule **trong chain đã được chọn**.
- **@Order**: thứ tự các chain khi có nhiều bean.
- **anyRequest()**: chỉ áp dụng với request còn lại trong chain hiện tại, không bảo vệ URL ngoài mọi chain.

## 5. Ứng dụng Spring Boot 3 chạy được: cấu hình bằng bean và Lambda DSL

Dự án dùng **Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring Web MVC**. Ví dụ dùng HTTP Basic để không phải xây dựng trang HTML login; có hai tài khoản demo. Chúng ta khai báo:

1. **SecurityFilterChain** để quy định URL và HTTP method.
2. **PasswordEncoder** dùng BCrypt.
3. **UserDetailsService** chứa hai user mẫu.
4. **Controller** công khai, cần authentication, cần ADMIN và endpoint cố tình không nằm trong allowlist.
5. **MockMvc test** để xác nhận toàn bộ đường đi qua filter.

### 5.1. Dependencies

Trong project Spring Boot 3.x đã có Gradle plugin, Java configuration và version management, đặt block sau vào **build.gradle** hiện hữu:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Đây là **đoạn dependencies**, không phải build.gradle độc lập; Gradle Wrapper và Spring Boot plugin cần được cấu hình từ trước. Cấu trúc file:

~~~text
src/main/java/com/example/lambdasecurity/
  LambdaSecurityApplication.java
  SecurityConfig.java
  DemoController.java

src/test/java/com/example/lambdasecurity/
  LambdaSecurityTest.java
~~~

### 5.2. LambdaSecurityApplication.java

~~~java
package com.example.lambdasecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LambdaSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(LambdaSecurityApplication.class, args);
    }
}
~~~

### 5.3. SecurityConfig.java

~~~java
package com.example.lambdasecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/profile").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            );

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice123"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }
}
~~~

**Đọc từng bean:**

- **apiSecurity(HttpSecurity http):** nhận builder do Spring Security cung cấp; cấu hình rule, HTTP Basic và session policy bằng lambda; trả **http.build()**.
- **passwordEncoder():** tạo một BCrypt encoder do Spring quản lý. Hash mỗi lần tạo user có thể khác vì salt, nhưng raw password đúng vẫn được xác minh bằng **matches**.
- **users(PasswordEncoder encoder):** Spring tự truyền bean PasswordEncoder vào; tạo **UserDetailsService** chứa alice và admin. **roles("USER")** gắn authority **ROLE_USER**, tương tự ROLE_ADMIN.
- **STATELESS:** Spring Security không dựa vào HttpSession để lấy SecurityContext ở request kế tiếp. Nó không có nghĩa HTTP Basic là cách duy nhất để làm API, và không tự động vô hiệu hóa CSRF.
- **anyRequest().denyAll():** endpoint và method chưa có rule được tuyên bố rõ ràng sẽ bị từ chối trong chain này.
- Ví dụ không gọi **csrf.disable()** vì các endpoint business đều là GET; chính sách CSRF cho POST/PUT/DELETE phải được thiết kế theo client/credential transport.

**Không khai báo formLogin** trong chain trên; khi client anonymous gọi **/profile**, Basic entry point thường phản hồi **401** và challenge, thay vì chuyển hướng tới trang đăng nhập của browser.

**Cấu hình này dành cho demo/localhost:** password đơn giản và in-memory không phù hợp sản xuất. Với hệ thống thật cần identity store, secret management và HTTPS/TLS.

### 5.4. DemoController.java

~~~java
package com.example.lambdasecurity;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/profile")
    public String profile(Authentication authentication) {
        return "profile:" + authentication.getName();
    }

    @GetMapping("/admin")
    public String adminEndpoint() {
        return "admin";
    }

    @GetMapping("/unlisted")
    public String unlisted() {
        return "this-must-not-be-exposed";
    }
}
~~~

Controller **/unlisted** tồn tại để minh họa rằng một endpoint có mapping vẫn không được truy cập nếu **SecurityFilterChain** có fallback deny. Controller **/profile** nhận **Authentication** đã được Spring Security xác minh; nó không tự parse Basic header.

### 5.5. Chạy thủ công và xem phản hồi

Từ thư mục project có Gradle Wrapper:

~~~bash
./gradlew bootRun
# Windows:
gradlew.bat bootRun
~~~

Từ terminal khác gửi HTTP request đến localhost:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/profile
curl -i -u alice:alice123 http://localhost:8080/profile
curl -i -u alice:alice123 http://localhost:8080/admin
curl -i -u admin:admin123 http://localhost:8080/admin
curl -i -u admin:admin123 http://localhost:8080/unlisted
curl -i -u alice:wrong http://localhost:8080/profile
~~~

Dự kiến với **đúng ứng dụng demo** và không có reverse proxy hoặc handler tùy chỉnh:

| HTTP request | Status | Kết quả |
| --- | --- | --- |
| GET /public, không credential | **200** | Body **public** |
| GET /profile, không credential | **401** | HTTP Basic challenge |
| GET /profile, alice đúng password | **200** | Body **profile:alice** |
| GET /admin, alice ROLE_USER | **403** | Thiếu ROLE_ADMIN |
| GET /admin, admin ROLE_ADMIN | **200** | Body **admin** |
| GET /unlisted, admin | **403** | Fallback deny, controller không chạy |
| GET /profile, sai password | **401** | Xác thực thất bại |

Đây là **HTTP status và body**, không phải stdout được in bởi ứng dụng Java. **curl -i** in header cùng body. Khi có 401 từ HTTP Basic, header **WWW-Authenticate** thường cho biết Basic challenge. Không phụ thuộc vào nội dung body lỗi vì cấu hình error handling có thể thay đổi.

Với HTTP Basic, chuỗi username/password chỉ được mã hóa Base64 trong header; **Base64 không phải mã hóa bảo mật**. Chỉ dùng credential thật qua HTTPS và không ghi password trong shell history/log. Các password trong ví dụ là dữ liệu học tập.

### 5.6. Kiểm thử MockMvc: xác nhận rule và cơ chế login

Đặt file **src/test/java/com/example/lambdasecurity/LambdaSecurityTest.java**:

~~~java
package com.example.lambdasecurity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LambdaSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsPublic() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void anonymousCannotAccessProfile() throws Exception {
        mvc.perform(get("/profile"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceCanReadHerProfile() throws Exception {
        mvc.perform(get("/profile")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(content().string("profile:alice"));
    }

    @Test
    void roleUserCannotAccessAdmin() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanAccessAdmin() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }

    @Test
    void unlistedControllerRemainsDenied() throws Exception {
        mvc.perform(get("/unlisted")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void wrongPasswordIsRejected() throws Exception {
        mvc.perform(get("/profile")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Chạy test trong project:

~~~bash
./gradlew test
# Windows:
gradlew.bat test
~~~

**httpBasic(...)** từ Spring Security Test giúp MockMvc tạo header Basic giống request thực. Test đi qua filter + provider + authorization; nó **không tự đánh dấu người dùng đã đăng nhập**. Chính các test 401/403 có giá trị vì chứng minh điều gì xảy ra khi thiếu credential hoặc thiếu authority, chứ không chỉ kiểm tra endpoint 200.

Bộ kiểm thử trên nhắm đến **Spring Boot 3.x**. Không sao chép nguyên import khi dự án dùng Spring Boot 4.x/Spring Security 7.x mà chưa kiểm tra dependency và thay đổi package kiểm thử tương ứng.

## 6. Chia cấu hình thành nhiều bean có trách nhiệm rõ

Đối với ứng dụng lớn, bạn thường tách:

- **WebSecurityConfig:** các bean SecurityFilterChain và URL policy.
- **IdentityConfig/AccountConfig:** PasswordEncoder, UserDetailsService hoặc AuthenticationProvider.
- **CORS policy:** CorsConfigurationSource nếu thực sự dùng browser cross-origin.
- **Service/domain policy:** các service và annotation method security khi cần.

Phân tách như vậy cho phép kiểm tra bean nào xác thực, bean nào phân quyền và bean nào xử lý session/CORS/CSRF. Tuy nhiên **không bắt buộc mỗi mối quan tâm phải nằm trong một class khác**: demo nhỏ có thể giữ các bean liên quan trong một lớp SecurityConfig như phần 5.

### 6.1. Tự viết UserDetailsService từ database

Ví dụ app dùng JPA:

~~~java
// Chỉ là đoạn trích: AccountEntity, AccountRepository và các import
// phải được định nghĩa trong dự án thật.
@Service
public class AccountUserDetailsService implements UserDetailsService {

    private final AccountRepository repository;

    public AccountUserDetailsService(AccountRepository repository) {
        this.repository = repository;
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        AccountEntity account = repository.findByUsername(username)
            .orElseThrow(() -> new UsernameNotFoundException(
                "Invalid credentials"
            ));

        return User.withUsername(account.getUsername())
            .password(account.getPasswordHash())
            .authorities(account.getAuthorities())
            .disabled(!account.isEnabled())
            .accountLocked(account.isLocked())
            .build();
    }
}
~~~

Đây là **snippet phụ thuộc code của dự án**, không phải file Java độc lập. **UserDetailsService** chỉ tải account; **DaoAuthenticationProvider** và **PasswordEncoder** xác minh credential. Trong đa tenant, username phải được định danh đúng tenant, tránh nhầm account cùng tên. Password nên lưu hash phù hợp, không plaintext.

### 6.2. @EnableMethodSecurity và @PreAuthorize

Nếu có nghiệp vụ đọc dữ liệu cần quyền **report:read**, ta có thể bật method security:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
~~~

Rồi bảo vệ một service được Spring quản lý:

~~~java
@Service
class ReportService {

    @PreAuthorize("hasAuthority('report:read')")
    public String readReport() {
        return "report";
    }
}
~~~

Đây là **hai snippet bổ sung**, cần import **Configuration**, **EnableMethodSecurity**, **Service**, **PreAuthorize**. Khi được gọi qua Spring proxy và cấu hình phù hợp, method được kiểm tra quyền; **self-invocation** trong cùng bean có thể không đi qua proxy. **@EnableMethodSecurity không tự chặn mọi method không có annotation**: cần xác định điểm kiểm soát theo nghiệp vụ và kiểm thử.

Rule theo URL và rule theo method có thể phối hợp. Tuy vậy, việc cho phép đọc một loại resource chưa chứng minh người dùng sở hữu **resource cụ thể**; cần kiểm tra owner, tenant và trạng thái dữ liệu khi policy yêu cầu.

### 6.3. Tự khai báo AuthenticationManager có cần không?

Thông thường **không cần** tự tạo ProviderManager để dùng HTTP Basic với **một UserDetailsService** và **PasswordEncoder** có sẵn. Spring Security có cơ chế cấu hình manager/provider cho trường hợp phổ biến. Khi sử dụng nhiều provider hoặc cần cơ chế xác thực đặc biệt, hãy khai báo có chủ đích; tránh thêm một **AuthenticationManager** tùy tiện chỉ để “đủ bean” và vô tình bỏ qua provider mặc định.

## 7. Nhiều SecurityFilterChain với @Order

Một ứng dụng có thể vừa có HTTP API vừa có giao diện web với form login. Khi đó tạo **nhiều SecurityFilterChain bean**, phân phạm vi bằng **securityMatcher(...)** và sắp thứ tự bằng **@Order**.

Ví dụ sau chỉ là **snippet của một cấu hình khác**, không ghép thêm nguyên xi vào SecurityConfig demo ở phần 5:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/ping").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());

    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/login").permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults());

    return http.build();
}
~~~

Cần import **Bean**, **Order**, **HttpMethod**, **HttpSecurity**, **SecurityFilterChain** và **Customizer**. Trong ví dụ:

1. Request thuộc **/api/** sẽ khớp chain API trước.
2. Request còn lại có thể vào chain web không khai báo giới hạn **securityMatcher**.
3. **FilterChainProxy chọn chain đầu tiên khớp**, không áp dụng đồng thời tất cả các chain vào cùng request.
4. Cơ chế xác thực/entry point khác nhau nên API có thể trả 401 Basic, trong khi browser vào web route có thể được redirect đến login.
5. Khi dùng form login, kiểm tra endpoint login được filter chain xử lý, và CSRF token phù hợp cho POST /login.

### 7.1. Đừng nhầm hai loại matcher

| API | Vai trò | Ví dụ |
| --- | --- | --- |
| **securityMatcher("/api/**")** | Quyết định request có thuộc **chain** | /api/orders có; /login không |
| **requestMatchers(HttpMethod.GET, "/api/ping")** | Quyết định rule authorization trong chain | GET /api/ping permitAll |
| **anyRequest().authenticated()** | Rule cuối cho request còn lại thuộc chain | /api/orders cần đăng nhập |
| **@Order(1)** | Chọn chain ưu tiên hơn | API trước web |

Nếu chỉ có **securityMatcher("/api/**")** và không tạo chain bao phủ phần còn lại, **/internal/debug** có thể nằm ngoài Spring Security. Đặt **anyRequest().denyAll()** trong chain API cũng không chặn được request **ngoài API chain**. Hãy có fallback chain và kiểm tra coverage trên toàn bộ servlet URL.

### 7.2. Form login URL phải nằm trong phạm vi chain

Nếu chain chỉ match **/secured/** nhưng form login để **/login** mặc định, request đến **/login** có thể không được chain đó xử lý, dẫn đến login endpoint không tồn tại như mong đợi. Khi dùng **loginPage("/secured/login")** hoặc **loginProcessingUrl(...)**, cần bảo đảm request GET/POST liên quan thuộc chain và ứng dụng có controller/view cho trang login tùy chỉnh.

### 7.3. @Order chỉ ảnh hưởng khi nhiều chain

Nếu ứng dụng chỉ có một chain không giới hạn securityMatcher, thường không cần đặt **@Order**. Khi có nhiều chain, hãy xếp các matcher **cụ thể trước**, chain **rộng nhất sau**, và test request khớp lẫn request nằm ngoài matcher.

## 8. Cách cấu hình CSRF, CORS và Session bằng lambda

Lambda DSL không chỉ dành cho authorizeHttpRequests. Các concern khác cũng có dạng lambda, nhưng phải hiểu ý nghĩa trước khi sao chép.

### 8.1. Session management

~~~java
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
)
~~~

**STATELESS** làm Spring Security không sử dụng HttpSession để lấy SecurityContext. Điều này hữu ích với API xác thực credential trên mỗi request, nhưng **không bật JWT** và không có nghĩa toàn bộ server không lưu state. Nếu web app dùng form login + session, chính sách session cần khác.

### 8.2. CSRF

Spring Security Servlet thường bật **CSRF protection** cho HTTP method không an toàn khi chưa thay cấu hình. Một web app dùng session cookie nên bảo vệ POST/PUT/DELETE bằng CSRF token đúng cách; **HttpOnly cookie không thay CSRF token**.

Có thể cấu hình CSRF qua:

~~~java
.csrf(csrf -> csrf
    // Chỉ thêm rule khi threat model và loại client đã rõ.
)
~~~

Đoạn trên **chỉ minh họa điểm mở rộng DSL**, không cần thêm vào ứng dụng nếu chỉ muốn giữ mặc định. Cấu hình **csrf -> csrf.disable()** không nên được áp dụng theo thói quen cho mọi API; browser có thể tự gửi cookie hoặc HTTP authentication credential và tạo rủi ro CSRF.

### 8.3. CORS

Trong ứng dụng có browser frontend khác origin, cross-origin request mang Authorization header thường có CORS preflight. Bạn có thể bật tích hợp CORS:

~~~java
.cors(Customizer.withDefaults())
~~~

Việc này **chưa tự định nghĩa danh sách origin/method/header được phép**. Cần **CorsConfigurationSource** hoặc cấu hình MVC CORS phù hợp, bảo đảm preflight được xử lý và credentialed CORS không dùng wildcard origin sai quy định.

**CORS không phải authorization.** Nó kiểm soát hành vi cross-origin của browser, không xác thực token hay quyết định user có quyền đọc tài liệu cụ thể hay không.

### 8.4. Exception handling

Một ứng dụng API có thể muốn response JSON thay cho trang HTML. **AuthenticationEntryPoint** bắt đầu authentication (thường là 401 Basic hoặc redirect login), còn **AccessDeniedHandler** xử lý danh tính đã xác thực nhưng thiếu quyền (thường 403).

Có thể cấu hình qua:

~~~java
.exceptionHandling(errors -> errors
    .authenticationEntryPoint(customEntryPoint)
    .accessDeniedHandler(customDeniedHandler)
)
~~~

Đây là **snippet**: cần khai báo/import hai handler thật, có contract HTTP cụ thể và test response. Nếu ghi đè entry point của HTTP Basic, cần cân nhắc giữ header **WWW-Authenticate** khi client dựa vào Basic challenge.

### 8.5. Headers và logout

Các cấu hình khác cũng sử dụng lambda:

~~~java
.headers(headers -> headers
    .frameOptions(frame -> frame
        .sameOrigin()
    )
)
.logout(logout -> logout
    .logoutUrl("/logout")
)
~~~

Đoạn này chỉ minh họa cú pháp; **không tự mở same-origin frame** nếu ứng dụng không thật sự cần, vì frame policy nên được lựa chọn theo nhu cầu chống clickjacking. Khi dùng logout với session/cookie hoặc JWT, semantics khác nhau; cấu hình endpoint logout chưa tự thu hồi mọi token đã phát.

## 9. Tách DSL theo module: lúc nào nên làm?

Trong dự án lớn, security policy có thể dài. Có ba cách tổ chức phổ biến:

1. Giữ method **@Bean SecurityFilterChain** đủ ngắn, gọi các method private để cấu hình nhóm rule trong cùng lớp (nếu API hỗ trợ và dễ đọc).
2. Đặt nhiều chain cho **vùng request có chính sách thực sự khác nhau**, có @Order và fallback rõ ràng.
3. Với các phiên bản Spring Security hỗ trợ, dùng **Customizer<HttpSecurity> bean** hoặc cơ chế **custom DSL** để chia phần thiết lập chung của các chain. Việc này cần kiểm tra lifecycle và thứ tự áp dụng customizer trên version mục tiêu; không mặc định mọi bean Customizer đều tự được áp dụng ở mọi version.

Một **custom DSL** nâng cao có thể được áp dụng bằng **http.with(...)** trong Spring Security 6.2+, thay cho **http.apply(...)** kiểu cũ để tương thích hướng Spring Security 7. Chỉ đưa abstraction này vào khi nhiều chain thực sự chia sẻ hành vi phức tạp; demo và app nhỏ không cần custom DSL.

**Không lạm dụng nhiều @Configuration class** nếu cùng một URL có nhiều rule mâu thuẫn khó phát hiện. Đặt điểm sở hữu policy rõ ràng, kèm test cho matcher và HTTP method.

## 10. Kiểm thử thay đổi cấu hình và chống lỗi bảo mật

Khi chuyển sang Lambda DSL, mục tiêu không chỉ là dự án **compile** mà là **giữ đúng behavior**. Một lần nâng cấp có thể khiến chain khác được chọn, login URL bị mất, 401 thành 302 hoặc endpoint mới vô tình được mở.

Bộ test nên có:

| Test case | Lý do |
| --- | --- |
| Anonymous gọi public GET | Chứng minh rule permitAll nằm đúng vị trí |
| Anonymous gọi protected GET | Chứng minh entry point yêu cầu authentication |
| User hợp lệ vào profile | Chứng minh authentication filter/provider hoạt động |
| User không đủ role vào admin | Chứng minh authorization tách biệt authentication |
| Admin vào admin | Chứng minh authority ROLE_ADMIN đúng |
| Endpoint không nằm trong allowlist | Chứng minh fallback deny |
| HTTP method khác trên cùng path | Chứng minh rule theo method và CSRF cần xem xét |
| Request ngoài securityMatcher của chain API | Chứng minh fallback chain vẫn bảo vệ |
| Form login GET/POST và CSRF | Chứng minh login endpoint thật sự được filter xử lý |
| OAuth2/Bearer token sai audience/scope (nếu dùng) | Chứng minh token validation và quyền |

Trong demo phần 5, các test MockMvc đã bao phủ bảy trường hợp HTTP cốt lõi. Khi cần kiểm tra filter chain chi tiết, có thể bật:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Ở môi trường phát triển, log có thể hiển thị các filter trong chain và những bước áp dụng authorization. Không log raw password, Basic Authorization header, bearer token, session cookie hoặc dữ liệu riêng tư.

### 10.1. Debug theo luồng từ ngoài vào

Khi response không đúng, lần lượt hỏi:

1. **Request thực sự tới đúng path và HTTP method chưa?** Có context path/reverse proxy/servlet mapping khác không?
2. **FilterChainProxy chọn chain nào?** Có securityMatcher, @Order hoặc fallback chain sai không?
3. **Rule requestMatchers nào khớp đầu tiên?** Có permitAll/authenticated quá rộng đứng trước hasRole không?
4. **Filter authentication nào đang bật?** Basic, form, OAuth2 Resource Server, OAuth2 Login hay một custom filter?
5. **Nguồn danh tính nào được sử dụng?** Generated default user, UserDetailsService, AuthenticationProvider, JwtDecoder?
6. **Principal và authorities có phù hợp không?** ROLE_ADMIN khác ADMIN, SCOPE_read khác read.
7. **CSRF/CORS/error dispatch có can thiệp không?** Phân biệt lỗi authentication, authorization và cơ chế bảo vệ khác.
8. **Controller/service có kiểm tra quyền theo resource không?** URL rule không tự kiểm tra quyền đọc bản ghi sở hữu bởi người khác.

## 11. Những lỗi phổ biến khi chuyển sang Spring bean và Lambda DSL

### 11.1. Vẫn kéo WebSecurityConfigurerAdapter vào project mới

**WebSecurityConfigurerAdapter** không còn có trong Spring Security 6. Hãy khai báo **@Bean SecurityFilterChain** và giữ logic xác thực trong bean/provider phù hợp. Đừng lấy nguyên class adapter từ hướng dẫn Spring Security 5 cũ rồi đổi vài import.

### 11.2. Tiếp tục .and() và cú pháp configurer không lambda

Cách gọi không lambda được thay bằng Lambda DSL. Điều đó giúp rõ đối tượng đang cấu hình và nhất quán hơn; đặc biệt **Spring Security 7 bắt buộc Lambda DSL** cho kiểu cấu hình HTTP này.

### 11.3. Nghĩ @Bean SecurityFilterChain tạo user/password

Bean chain kiểm soát **web security**, không xác định luôn **authentication provider**. Cần xem UserDetailsService/Provider/Manager và Spring Boot auto-configuration. Nếu vẫn có generated password, kiểm tra nguồn bean thực tế.

### 11.4. Đặt anyRequest().permitAll() quá rộng

Một rule mở hết có thể làm lộ endpoint mới. Dùng allowlist theo path/method với fallback deny nếu phù hợp. Đừng mở toàn ứng dụng chỉ vì trang login hoặc CSS đang bị 401.

### 11.5. Đặt requestMatchers sai thứ tự

Rule rộng có thể che rule hẹp; một số cách thêm matcher sau **anyRequest()** còn bị DSL từ chối. Đặt rule cụ thể trước, fallback cuối.

### 11.6. Quên authentication mechanism

**authenticated()** là một điều kiện, không tự bật **httpBasic** hoặc **formLogin**. Với API Bearer cần **oauth2ResourceServer(...)** và cấu hình token validation tương ứng; không tự coi một Authorization Bearer header là credential hợp lệ trong Basic chain.

### 11.7. securityMatcher khiến URL nằm ngoài mọi chain

**anyRequest().denyAll()** trong một chain chỉ chặn request đã thuộc chain. Nếu chỉ tạo chain cho **/api/**, endpoint **/internal/** có thể không được Spring Security bảo vệ. Hãy có fallback chain và test coverage.

### 11.8. @EnableMethodSecurity bị bỏ quên

Gắn **@PreAuthorize** vào service mà không bật method security đúng cách có thể khiến policy annotation không được thực thi. Cũng cần tránh self-invocation bỏ qua Spring AOP proxy.

### 11.9. Nhầm HTTP Basic với session/JWT

**SessionCreationPolicy.STATELESS** không tự bật JWT. HTTP Basic truyền username/password (Base64) và cần HTTPS; JWT Bearer có validation khác. Với browser session app, state management và CSRF có thể hoàn toàn hợp lý.

### 11.10. Vô hiệu hóa CSRF để mọi POST hết 403

403 có thể là thiếu CSRF token, thiếu quyền hoặc custom handler. Cần xác định client dùng cookie/session hay Bearer header, CSRF threat model và yêu cầu bảo vệ endpoint trước khi cấu hình exception hoặc disable.

### 11.11. Custom formLogin URL không được xử lý

Nếu chain không match **GET/POST /login** hoặc trang login tùy chỉnh không có controller/view, người dùng có thể gặp 404, redirect loop hoặc 403. Đặt matcher, loginProcessingUrl, csrf token và permitAll nhất quán.

### 11.12. Tự đăng ký security filter sai chỗ

Không tự tạo một **FilterRegistrationBean** khác cho filter của Spring Security nếu framework đã quản lý chain và bạn không có lý do đặc biệt. Việc đăng ký filter hai lần hoặc sai thứ tự có thể dẫn đến xử lý trùng hoặc bỏ qua các cơ chế bảo vệ.

### 11.13. Nghĩ permitAll đồng nghĩa bỏ qua Spring Security

**permitAll()** chỉ cho phép request ở bước authorization. Các security headers, CSRF/CORS và filter khác vẫn được áp dụng theo chain. Tránh lạm dụng **web.ignoring()** cho endpoint cần hưởng những lớp bảo vệ này.

### 11.14. Không kiểm tra phiên bản thư viện

Dự án Spring Boot 3/Spring Security 6 và Spring Boot 4/Spring Security 7 có khác biệt về package, auto-configuration và API. Tài liệu Lambda DSL hiện đại là hướng phù hợp, nhưng luôn kiểm tra phiên bản **được Gradle/Maven resolve thật**. Đặc biệt không sao chép import test hoặc custom DSL từ version mới sang version cũ khi chưa xác nhận.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Bean nào là điểm vào phổ biến để tự cấu hình HTTP security trong Spring Security Servlet hiện đại?

**Đáp án:** Một **@Bean SecurityFilterChain** nhận **HttpSecurity**, cấu hình bằng Lambda DSL rồi **return http.build()**.

**Câu 2.** Khai báo SecurityFilterChain có tự tắt UserDetailsService in-memory mặc định của Spring Boot không?

**Đáp án:** Không nhất thiết. Web chain và nguồn xác thực là hai phần auto-configuration khác. Cần khai báo bean authentication phù hợp nếu muốn thay nguồn user mặc định.

**Câu 3.** **Customizer.withDefaults()** có nghĩa gì?

**Đáp án:** Bật/configure một feature với các thiết lập mặc định của nó, thay vì viết lambda không tùy chỉnh các thuộc tính bên trong.

**Câu 4.** Vì sao Lambda DSL không cần **.and()**?

**Đáp án:** Framework tự quay về HttpSecurity sau khi xử lý lambda cấu hình, nên có thể tiếp tục cấu hình nhóm tiếp theo theo cách nhất quán.

**Câu 5.** **hasRole("ADMIN")** có kiểm tra username là “admin” không?

**Đáp án:** Không. Với role prefix mặc định, nó yêu cầu authority **ROLE_ADMIN**.

**Câu 6.** Chỉ tạo chain **securityMatcher("/api/**")** và đặt **anyRequest().denyAll()** trong chain đó. URL **/debug** có chắc được bảo vệ không?

**Đáp án:** Không. Nếu /debug không khớp chain khác, nó có thể nằm ngoài Spring Security. Cần một fallback chain bao trùm.

**Câu 7.** **.authorizeHttpRequests(auth -> auth.anyRequest().authenticated())** có tự bật HTTP Basic?

**Đáp án:** Không nên giả định. Rule yêu cầu authentication không tự mô tả cơ chế lấy credential. Hãy cấu hình **httpBasic**, **formLogin** hoặc cơ chế phù hợp theo client.

**Câu 8.** Tại sao một user đã đăng nhập có thể nhận **403** khi gọi endpoint?

**Đáp án:** Authentication đã xác minh danh tính, nhưng policy có thể yêu cầu role/authority hoặc quyền trên resource mà user thiếu. CSRF/filter khác cũng có thể tạo 403 ở một số request.

**Câu 9.** Có cần **@EnableMethodSecurity** cho **@PreAuthorize**?

**Đáp án:** Trong cấu hình ứng dụng thông thường, có. Bean SecurityFilterChain cho URL không tự bật method-security annotations.

**Câu 10.** Vì sao formLogin tùy chỉnh có thể nhận 404 với nhiều chain?

**Đáp án:** URL login có thể nằm ngoài **securityMatcher** của chain chứa login filter hoặc ứng dụng chưa cung cấp trang login tùy chỉnh.

**Câu 11.** Có thể dùng **http.csrf(csrf -> csrf.disable())** cho mọi ứng dụng trả JSON không?

**Đáp án:** Không suy ra từ JSON hay REST. Phải đánh giá browser có tự gắn credential không, session/cookie/HTTP auth và CSRF threat model trước khi thiết kế exception.

**Câu 12.** Vì sao test positive và negative đều cần khi đổi SecurityFilterChain?

**Đáp án:** Một endpoint trả 200 chưa chứng minh endpoint khác được chặn đúng. Test anonymous, sai password, thiếu role và URL chưa có rule giúp phát hiện lỗi mở quyền hoặc mất cơ chế xác thực.

## 13. Tài liệu tham khảo chính thức

- Spring Security — **Java Configuration**: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security 6.5 — **Use the Lambda DSL / Configuration Migrations**: https://docs.spring.io/spring-security/reference/6.5/migration-7/configuration.html
- Spring Security — **Authorize HttpServletRequests**: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — **Servlet Architecture**: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — **Method Security**: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — **Cross Site Request Forgery (CSRF)**: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Boot 3.5 — **Spring Security auto-configuration**: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html

**Ghi nhớ:** dùng **@Configuration + @Bean SecurityFilterChain + HttpSecurity Lambda DSL** để mô tả cách ứng dụng bảo vệ request. Cấu hình nguồn **Authentication** bằng bean thích hợp, áp dụng rule quyền đúng thứ tự, hiểu phạm vi mỗi chain và kiểm thử những request được phép lẫn bị từ chối. Cú pháp hiện đại giúp code rõ ràng; **policy đúng và độ bao phủ đủ** mới quyết định hệ thống có được bảo vệ như mong muốn.
