# Thay cấu hình mặc định bằng bean SecurityFilterChain trong Spring Security

> **Bối cảnh:** Spring Boot 3.x, Spring Security 6.x, Java 17+ và ứng dụng **Servlet/Spring MVC**. Chủ đề này là bước khởi tạo quan trọng: từ ứng dụng chỉ thêm dependency Spring Security, chuyển sang chủ động xác định endpoint nào công khai, endpoint nào cần đăng nhập, endpoint nào cần quyền cụ thể, và dùng cơ chế xác thực nào. Tên API/cách cấu hình của Spring Security WebFlux (reactive) khác với Servlet.

## 1. Vì sao phải thay cấu hình mặc định?

Khi thêm **spring-boot-starter-security** vào một ứng dụng Spring Boot Servlet mà chưa có cấu hình bảo mật tùy chỉnh, Spring Boot/Spring Security cung cấp cấu hình web bảo vệ mặc định. Trong trường hợp điển hình, mọi request cần xác thực; hai phương thức đăng nhập **form login** và **HTTP Basic** được bật, và Spring Boot có thể tạo một tài khoản trong bộ nhớ với password ngẫu nhiên được in lúc khởi động (nếu không có một cấu hình authentication khác làm auto-configuration này lùi bước).

Ví dụ một ứng dụng có ba endpoint:

- **GET /public**: trang thông tin công khai.
- **GET /me**: thông tin người đang đăng nhập.
- **GET /admin**: chức năng của quản trị viên.

Nếu không khai báo rule, mặc định ứng dụng không biết **/public** được phép mở, **/admin** phải yêu cầu ROLE_ADMIN hay API cần phản hồi bằng HTTP Basic thay cho redirect login. Các endpoint có thể đều đòi authentication chung. Để mô tả policy đúng nghiệp vụ, ta định nghĩa một bean **SecurityFilterChain**.

**Ý quan trọng:** khai báo bean **SecurityFilterChain** làm Spring Boot **không tạo cấu hình bảo vệ web mặc định của nó nữa**. Bean mới của bạn điều khiển filter chain tương ứng. Nhưng nó **không tự tắt hoàn toàn Spring Security**, **không tự tạo user/role**, **không tự tắt CSRF** và **không đồng nghĩa toàn bộ authentication auto-configuration biến mất**.

Tài liệu Spring Boot phân biệt hai việc:
1. Có bean **SecurityFilterChain**: Boot lùi bước khỏi **default web application security settings**.
2. Có bean **UserDetailsService**, **AuthenticationProvider** hoặc **AuthenticationManager** phù hợp: Boot lùi bước khỏi bean **InMemoryUserDetailsManager** mặc định của phần tài khoản.

Vì thế, nếu chỉ thêm SecurityFilterChain mà không khai báo nguồn user/authentication nào khác, trong một cấu hình Boot đơn giản **tài khoản generated mặc định vẫn có thể tồn tại**. Khi xây dựng ví dụ hoặc hệ thống thật, nên khai báo nguồn danh tính rõ ràng, rồi kiểm tra trạng thái bean và log khởi động.

## 2. SecurityFilterChain là gì và nằm ở đâu?

**SecurityFilterChain** là một chuỗi các servlet filters bảo vệ request được chọn. Ta thường khai báo nó như bean bằng cách cấu hình **HttpSecurity** rồi gọi **http.build()**. Spring Security dùng **FilterChainProxy** để chọn chain phù hợp và thực thi filter theo thứ tự đã định.

~~~text
HTTP client
    |
    v
Servlet container
    |
    v
DelegatingFilterProxy ("springSecurityFilterChain")
    |
    v
FilterChainProxy
    |
    +--> Chọn SecurityFilterChain đầu tiên khớp request
             |
             +--> Các filter bảo vệ: headers, CSRF, context...
             +--> Filter authentication: Basic/form/Bearer... nếu bật
             +--> ExceptionTranslationFilter
             +--> AuthorizationFilter
                         |
                         +--> ALLOW -> DispatcherServlet -> Controller
                         |
                         +--> DENY -> entry point / access denied handler
~~~

Không cần tự tạo **FilterChainProxy** hoặc đăng ký từng filter bằng Servlet API trong ứng dụng Spring Boot thông thường. Spring Security/Boot thực hiện phần tích hợp servlet. Việc ứng dụng làm là xây dựng những **SecurityFilterChain bean** phù hợp.

Một bean tối giản có dạng:

~~~java
@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Đây là đoạn trích**, cần import **Configuration**, **Bean**, **HttpSecurity**, **SecurityFilterChain**, **Customizer** và một project Spring Boot 3 đã có dependency Spring Security. Nó yêu cầu authentication cho mọi request và bật Basic. Chỉ copy một rule mà không hiểu authentication/filter nào được bật có thể làm client nhận response khác mong đợi.

Trong Java configuration của Spring Security 6, **SecurityFilterChain + HttpSecurity + authorizeHttpRequests** là cách khai báo phổ biến. Các hướng dẫn cũ sử dụng **WebSecurityConfigurerAdapter** đã lỗi thời cho Spring Security 6; nên viết bean SecurityFilterChain thay vì kế thừa adapter này.

## 3. Cấu hình trước và sau: thay đổi điều gì?

Xem hai trạng thái của cùng một dự án.

**Trước khi khai báo SecurityFilterChain:**

~~~text
Spring Boot + spring-boot-starter-security
  |
  +--> Boot cung cấp cấu hình web mặc định
  |      - yêu cầu authenticated cho các request thông thường
  |      - hỗ trợ form login và HTTP Basic
  |
  +--> nếu chưa có nguồn authentication tùy chỉnh phù hợp:
         tạo in-memory user mặc định và password ngẫu nhiên
~~~

**Sau khi khai báo SecurityFilterChain của ứng dụng:**

~~~text
Spring Boot + spring-boot-starter-security
  |
  +--> tìm thấy SecurityFilterChain bean của ứng dụng
  |      - Boot không tạo default web SecurityFilterChain
  |      - rule và cơ chế HTTP do ứng dụng định nghĩa
  |
  +--> authentication/user source là phần cấu hình khác
         - có thể vẫn xuất hiện generated user
         - hoặc dùng UserDetailsService / provider / OAuth2...
~~~

Ví dụ thay đổi hành vi:

| Request | Khi dùng cấu hình Boot mặc định điển hình | Sau khi thêm rule cho phép/giới hạn |
| --- | --- | --- |
| GET /public, chưa đăng nhập | Thường cần xác thực hoặc redirect/challenge | **200** khi permitAll và controller thành công |
| GET /me, chưa đăng nhập | Cần xác thực | **401** nếu ứng dụng chỉ bật HTTP Basic |
| GET /me, user hợp lệ | Có thể được đi tiếp | **200** theo rule authenticated |
| GET /admin, ROLE_USER | Nếu chỉ yêu cầu authenticated, có thể được đi tiếp | **403** khi hasRole("ADMIN") |
| GET /unknown, đã đăng nhập | Quyền tùy cấu hình | Bị từ chối nếu fallback anyRequest().denyAll() |

**Cần chú ý:** bảng chỉ so sánh **authorization policy**. Một endpoint không có controller còn có thể trả **404**, và lỗi authentication/CSRF/filter chain có thể thay đổi status. Không thể khẳng định mọi request với cấu hình mặc định luôn có cùng status vì Spring Security điều chỉnh entry point theo client và cấu hình.

## 4. Đọc cú pháp HttpSecurity đúng theo từng tầng

Cấu hình thường gặp:

~~~java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/public").permitAll()
        .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
        .requestMatchers(HttpMethod.GET, "/me").authenticated()
        .anyRequest().denyAll()
    )
    .httpBasic(Customizer.withDefaults());
~~~

Đây là một **snippet trong method @Bean**, không phải lớp Java độc lập.

### 4.1. authorizeHttpRequests

**authorizeHttpRequests(...)** định nghĩa các quy tắc authorization dựa trên request. **AuthorizationFilter** cùng **AuthorizationManager** dùng chúng để quyết định cho phép hoặc từ chối. Rule **đầu tiên khớp** có hiệu lực, nên thứ tự cần được thiết kế có chủ đích.

| Cấu hình | Ý nghĩa |
| --- | --- |
| **permitAll()** | Cho request đi tiếp mà không cần principal đăng nhập; vẫn qua chain và các filter còn lại |
| **authenticated()** | Cần danh tính được coi là đã xác thực, không chỉ là anonymous |
| **hasRole("ADMIN")** | Cần authority **ROLE_ADMIN** theo tiền tố mặc định |
| **hasAuthority("report:read")** | Cần đúng authority **report:read** |
| **denyAll()** | Từ chối request khớp quy tắc đó |
| **anyRequest()** | Match mọi request còn lại **trong SecurityFilterChain đang xét** |

Lệnh **hasRole("ADMIN")** không kiểm tra tên account “admin”; nó kiểm tra danh sách **GrantedAuthority** của principal. Nếu user có authority **ADMIN** nhưng thiếu **ROLE_ADMIN**, kiểm tra role mặc định không khớp.

### 4.2. requestMatchers có thể xét cả HTTP method

~~~java
.requestMatchers(HttpMethod.GET, "/api/items").permitAll()
.requestMatchers(HttpMethod.POST, "/api/items").hasRole("EDITOR")
~~~

GET được công khai không có nghĩa POST cũng được công khai. Đặt **anyRequest().denyAll()** ở cuối giúp endpoint hoặc HTTP method mới chưa được khai báo không tự mở quyền. Cần thiết kế thêm error dispatch, tài nguyên tĩnh, health check và các endpoint framework như login nếu ứng dụng sử dụng.

**Đường dẫn trong matcher** phải khớp cách Spring Security nhận request trong servlet app. Đừng đoán path khi có **context path**, servlet path tùy chỉnh hoặc reverse proxy. Hãy kiểm thử đường dẫn thực tế.

### 4.3. httpBasic, formLogin và cơ chế khác

~~~java
.httpBasic(Customizer.withDefaults())
~~~

bật HTTP Basic để client gửi **Authorization: Basic ...**. Tùy loại request, khi chưa có credential hợp lệ sẽ thường trả **401 + WWW-Authenticate**.

~~~java
.formLogin(Customizer.withDefaults())
~~~

bật form login, có thể dùng trang đăng nhập do Spring Security tạo và **POST /login**. Khi chưa đăng nhập, browser thường được **redirect** đến trang login.

**Không phải cứ khai báo SecurityFilterChain là tự động bật cả hai kiểu đăng nhập như Boot mặc định.** Khi viết một chain mới, cần nêu rõ phương thức xác thực dự kiến cho từng nhóm request. **oauth2ResourceServer(...)** là lựa chọn khác cho Bearer token, đòi cấu hình issuer/decoder/introspection phù hợp; JWT không được tự xác minh chỉ vì ứng dụng có một bean SecurityFilterChain.

### 4.4. Một bean là cấu hình HTTP, không phải nơi tạo user

Có ba tầng cấu hình:
1. **SecurityFilterChain:** request nào được bảo vệ, bằng những filter nào, URL nào có quyền gì.
2. **Authentication:** credential được xác minh ra sao, UserDetailsService/AuthenticationProvider/PasswordEncoder/JWT Decoder nào hoạt động.
3. **Session/CSRF/CORS và các chính sách khác:** cách context được lưu, credential được browser gửi và response bảo mật được xây dựng.

Đừng trộn trách nhiệm bằng cách tự gọi **loadUserByUsername** trong controller hoặc tự gán principal tùy ý để bỏ qua filter. Khi user đăng nhập đúng nhưng bị **403**, cần xem authorization; khi client chưa được xác thực và bị **401**, cần xem authentication và entry point.

## 5. Ví dụ chạy được với Spring Boot 3 + Java 17

Ví dụ đầy đủ sau đây **thay cấu hình bảo mật mặc định bằng bean SecurityFilterChain** và khai báo nguồn user để kết quả ổn định, không phụ thuộc generated password. Dùng HTTP Basic với các endpoint GET: công khai, cần đăng nhập, cần ADMIN và một endpoint có controller nhưng bị rule cuối chặn.

### 5.1. Chuẩn bị dự án

Tạo project **Spring Boot 3.x, Java 17+**, sử dụng **Spring Web**, **Spring Security**, **Spring Boot Test** và **Spring Security Test**. Với dự án Gradle hiện hữu, dependency block là:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Đoạn trên là **phần dependencies của build.gradle hiện hữu**; project phải có plugins/BOM và Gradle Wrapper phù hợp. Các file dưới đây nằm trong package **com.example.customchain**:

~~~text
src/main/java/com/example/customchain/
  CustomChainApplication.java
  SecurityConfig.java
  DemoController.java

src/test/java/com/example/customchain/
  SecurityChainTest.java
~~~

### 5.2. CustomChainApplication.java

~~~java
package com.example.customchain;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CustomChainApplication {
    public static void main(String[] args) {
        SpringApplication.run(CustomChainApplication.class, args);
    }
}
~~~

### 5.3. SecurityConfig.java — bean thay cấu hình mặc định

~~~java
package com.example.customchain;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
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
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
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

**Giải thích lần lượt:**

- **@Configuration** đăng ký lớp cấu hình, **@Bean SecurityFilterChain** đưa policy HTTP của ứng dụng vào Spring. Boot không tạo default web security chain nữa.
- **HttpSecurity** được truyền vào method bởi Spring Security. **http.build()** tạo chain đã cấu hình; đừng trả null.
- **GET /public → permitAll()** là ngoại lệ có chủ đích.
- **GET /me → authenticated()** yêu cầu principal đăng nhập.
- **GET /admin → hasRole("ADMIN")** yêu cầu authority **ROLE_ADMIN**. **roles("ADMIN")** trong builder thêm tiền tố ROLE_.
- **anyRequest().denyAll()** từ chối request chưa có allow rule; kể cả controller tồn tại nhưng chưa khai báo policy.
- **httpBasic(...)** là cơ chế xác thực API được chọn trong ví dụ. **formLogin(...)** không được bật trong chain này.
- **UserDetailsService** cùng **PasswordEncoder** thiết lập người dùng demo; việc tạo bean UserDetailsService cũng làm Boot không cung cấp generated in-memory user của nó trong trường hợp tương ứng.
- **BCryptPasswordEncoder** băm mật khẩu để so khớp; password minh họa chỉ dùng trong môi trường học. Không lưu password plaintext trong production.

**CSRF vẫn được Spring Security bảo vệ theo mặc định cho các HTTP method không an toàn** (như POST) nếu chưa thay cấu hình. Vì chỉ demo endpoint GET nên ta không tùy tiện tắt CSRF. Nếu bổ sung endpoint POST, hãy quyết định chính sách CSRF dựa trên kiểu client và cách browser có thể tự gắn credential, rồi thêm test tương ứng.

Một số hướng dẫn cũ thêm **.csrf(csrf -> csrf.disable())** ngay khi làm “REST API”. Điều đó không phải hệ quả bắt buộc của HTTP Basic hay SecurityFilterChain; bạn nên hiểu nguy cơ CSRF và cơ chế session/cookie/token thực tế trước khi điều chỉnh.

### 5.4. DemoController.java

~~~java
package com.example.customchain;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/me")
    public String me(Authentication authentication) {
        return "user:" + authentication.getName();
    }

    @GetMapping("/admin")
    public String adminPage() {
        return "admin-only";
    }

    @GetMapping("/unlisted")
    public String unlistedPage() {
        return "should-not-be-exposed";
    }
}
~~~

Endpoint **/unlisted** cố tình có controller để kiểm tra deny-by-default: có route **không đồng nghĩa được phép truy cập**. Controller **/me** nhận Authentication đã xác thực, không tự parse Basic header hoặc kiểm tra password lại.

### 5.5. Chạy ứng dụng và gửi request

Tại thư mục có Gradle Wrapper:

~~~bash
./gradlew bootRun
# Windows (PowerShell hoặc cmd):
gradlew.bat bootRun
~~~

Dùng terminal khác gửi các request trên **localhost**:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u alice:alice123 http://localhost:8080/me
curl -i -u alice:alice123 http://localhost:8080/admin
curl -i -u admin:admin123 http://localhost:8080/admin
curl -i -u admin:admin123 http://localhost:8080/unlisted
curl -i -u alice:wrong http://localhost:8080/me
~~~

Kỳ vọng với **đúng ví dụ trên**, không có cấu hình proxy/exception handler khác:

| Request | HTTP status | Kết quả |
| --- | --- | --- |
| GET /public, anonymous | **200** | Body **public** |
| GET /me, anonymous | **401** | HTTP Basic challenge, thường có WWW-Authenticate |
| GET /me, alice đúng password | **200** | Body **user:alice** |
| GET /admin, alice ROLE_USER | **403** | Đã xác thực nhưng thiếu ROLE_ADMIN |
| GET /admin, admin ROLE_ADMIN | **200** | Body **admin-only** |
| GET /unlisted, admin | **403** | Deny rule chặn, controller không chạy |
| GET /me, alice sai password | **401** | Xác thực thất bại |

Với HTTP Basic, Base64 chỉ là cách trình bày credential, **không mã hóa bảo mật**; luôn dùng **HTTPS** trên mạng, và tránh hard-code hoặc in credential thật. Lệnh **curl -u user:password** phù hợp thử demo trên localhost nhưng có thể lộ mật khẩu trong history/process list. Response body lỗi không được cố định trong ví dụ; hãy kiểm tra status và WWW-Authenticate.

### 5.6. SecurityChainTest.java — test hành vi qua filter

Tạo **src/test/java/com/example/customchain/SecurityChainTest.java**:

~~~java
package com.example.customchain;

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
class SecurityChainTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsAllowed() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void protectedEndpointRequiresAuthentication() throws Exception {
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedUserCanReadProfile() throws Exception {
        mvc.perform(get("/me")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(content().string("user:alice"));
    }

    @Test
    void roleRuleRejectsNonAdmin() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanEnterAdminEndpoint() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-only"));
    }

    @Test
    void unlistedControllerIsDeniedByFallbackRule() throws Exception {
        mvc.perform(get("/unlisted")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidPasswordIsUnauthorized() throws Exception {
        mvc.perform(get("/me")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Chạy:

~~~bash
./gradlew test
# Windows:
gradlew.bat test
~~~

Các test này đi qua filter của Spring Security qua MockMvc; **httpBasic(...)** từ Spring Security Test giúp tạo header Basic, không tự cấp principal bỏ qua xác thực. Chúng chứng minh rằng bean SecurityFilterChain đã mở đúng endpoint, từ chối anonymous, kiểm tra role và bảo vệ endpoint chưa có rule. Các kết quả được ghi là **dự kiến theo code**; cần chạy Gradle trong dự án đã khai báo đúng dependencies để xác nhận thực tế.

## 6. Vì sao chỉ thêm bean SecurityFilterChain có thể gây thay đổi lớn?

Khi Boot ngừng tạo default web SecurityFilterChain, ứng dụng chịu trách nhiệm xác định policy bảo vệ. Một số tác động quan trọng:

### 6.1. Thay thế khác với bổ sung mặc định

Spring Boot không tự giữ một “default security chain” rồi gắn vài rule của bạn vào sau. Nếu bạn đăng ký SecurityFilterChain, **bạn đang cung cấp chain do mình xây dựng**. Chỉ tạo bean không có đầy đủ rule/matcher có thể dẫn đến hành vi khác dự tính.

Ví dụ cấu hình không nên dùng khi endpoint nhạy cảm:

~~~java
@Bean
SecurityFilterChain unsafeExample(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .anyRequest().permitAll()
    );

    return http.build();
}
~~~

**Đây là snippet minh họa cấu hình quá rộng**, không phải gợi ý triển khai. Nó cho phép toàn bộ request đi qua authorization, kể cả controller tương lai có thể chứa dữ liệu nhạy cảm. Nếu có lý do cho public endpoint, chỉ cho phép đúng URL/method cần thiết. Một **anyRequest().denyAll()** ở cuối thường hữu ích cho allowlist chặt, nhưng phải tính các endpoint framework cần hoạt động.

### 6.2. Authentication và authorization là hai việc khác nhau

~~~java
.authorizeHttpRequests(auth -> auth
    .anyRequest().authenticated()
)
~~~

chỉ định chính sách “request cần authentication”. Nó **không quyết định cách lấy credential**, **không khai báo nguồn user**, không bảo đảm form login hoặc HTTP Basic đã bật.

Một request có thể không đủ điều kiện vì:
- Chưa có credential hoặc credential sai: cơ chế **AuthenticationEntryPoint** được gọi, ví dụ 401 Basic hoặc 302 login.
- Đã xác thực nhưng thiếu authority: thường là **403** từ **AccessDeniedHandler**.
- CSRF token thiếu/sai ở request thay đổi trạng thái, nếu bật CSRF: có thể bị chặn **403** trước khi controller chạy.
- Không khớp chain nào: request có thể **không được Spring Security bảo vệ**, một vấn đề độc lập với 401/403.

Cần xem đúng **chain**, **authentication filter** và **rule** trước khi sửa code.

### 6.3. Một SecurityFilterChain không tự có nghĩa stateless

Nếu API muốn không đọc HttpSession cho SecurityContext, có thể cấu hình thêm:

~~~java
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
~~~

Đoạn trên cần import **SessionCreationPolicy** và đặt bên trong HttpSecurity của chain phù hợp. **STATELESS** điều chỉnh việc Spring Security dùng HttpSession cho SecurityContext; nó không bật Bearer JWT và không bảo đảm mọi thứ ở server đều không có state. Với web app dùng form login, session có thể là lựa chọn phù hợp. Không áp dụng STATELESS cho mọi chain chỉ vì controller trả JSON.

### 6.4. Không tùy tiện bỏ security headers và CSRF

Các filter như **HeaderWriterFilter** và **CsrfFilter** thường vẫn được cấu hình theo các default phù hợp khi sử dụng HttpSecurity. Việc tự khai báo SecurityFilterChain không tự vô hiệu hóa các lớp bảo vệ này. Nếu muốn thay đổi, cần lý do cụ thể, test đường request có tác động và hiểu cookie/browser credential được gửi như thế nào.

**permitAll() không đồng nghĩa bỏ filter chain**. Một endpoint public đi qua chain vẫn có thể nhận security headers và chịu các cơ chế bảo vệ khác. Đừng tự động dùng **web.ignoring()** cho mọi static path khi một **permitAll()** trong chain đã đáp ứng yêu cầu.

## 7. Nhiều SecurityFilterChain: /api và giao diện web

Một ứng dụng có thể cần chính sách HTTP khác nhau cho API và browser:

- **/api/**: Basic hoặc Bearer authentication, response thích hợp cho HTTP client.
- **/**, **/web/**, **/login**: form login, session cookie và CSRF cho browser.

Khai báo nhiều bean **SecurityFilterChain** được phép, nhưng **FilterChainProxy chỉ chọn chain phù hợp đầu tiên** theo thứ tự xét. Các chain **không được cộng dồn tất cả filter** như nhiều lớp bảo vệ độc lập cho cùng request.

Ví dụ cấu hình riêng (đây là **snippet**, không đặt đồng thời với SecurityConfig đầy đủ phần 5 nếu chưa sửa code cho nhất quán):

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

Cần import **Bean**, **Order**, **HttpMethod**, **HttpSecurity**, **SecurityFilterChain**, **Customizer**. Trong ví dụ này:
1. **apiChain** có **securityMatcher("/api/**")**, nên chỉ được chọn cho request /api.
2. **webChain** không đặt securityMatcher, nên matcher mặc định bao quát các request khác.
3. **@Order(1)** để /api được xét trước chain chung.
4. API được cấu hình HTTP Basic, web dùng form login. CSRF/session/CORS cần điều chỉnh nếu architecture thực tế khác.
5. Một rule **anyRequest()** ở apiChain chỉ xét request **đã vào apiChain**, không quyết định request ngoài /api.

### 7.1. securityMatcher khác requestMatchers

| Thành phần | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **http.securityMatcher("/api/**")** | Request này có vào **chain API** không? | /api/items: có; /login: không |
| **requestMatchers(HttpMethod.GET, "/api/ping")** | Trong chain đã chọn, **rule quyền nào** áp dụng? | GET /api/ping: permitAll |
| **anyRequest()** | Những request còn lại **trong chain này** thì sao? | require auth hoặc denyAll |
| **@Order** | Chain nào được xét trước? | /api trước web |

Nếu chỉ đăng ký một chain **securityMatcher("/api/**")** và không có chain chung còn lại, request **/internal/debug** có thể không được Spring Security bảo vệ. Trong đa số ứng dụng cần một **fallback SecurityFilterChain** bao phủ các URL còn lại. Nếu muốn chặn URL chưa quy định, dùng **anyRequest().denyAll()** trong chain chung và mở ngoại lệ có chủ đích.

### 7.2. Filter tự tạo endpoint cũng phải khớp matcher

Form login có thể cung cấp **GET /login** và **POST /login** qua các filter tương ứng. Nếu bạn cấu hình **formLogin** bên trong chain chỉ match **/secured/**, thì **/login** không khớp chain đó; endpoint login do filter cung cấp có thể không tồn tại theo cách bạn mong đợi (thường thấy 404). Cần thiết kế URL đăng nhập nằm trong phạm vi chain hoặc có chain khác xử lý nó.

Tương tự, với **/logout**, OAuth2 login callback, SAML endpoint, CSRF token endpoint hoặc các endpoint khác do filter tạo, phải xét cùng lúc **securityMatcher, endpoint URL và thứ tự chain**. Không dựa vào đường dẫn từ ví dụ khác mà không kiểm tra.

### 7.3. Chọn form login hay Basic/Bearer theo client

Ứng dụng browser dùng session và form login có thể cần redirect và CSRF; API client thường muốn response 401 với WWW-Authenticate hoặc lỗi JSON có contract rõ. Một ứng dụng có thể có hai chain hợp lệ. **Không phải vì đặt tên controller là “REST API” mà Spring Security tự lựa chọn JWT hoặc SessionCreationPolicy.STATELESS**.

## 8. Static resources, error dispatch và Actuator

Khi đổi cấu hình mặc định, hãy kiểm tra cả những endpoint **không phải business controller**:

- **Static assets**: CSS, JS, favicon hoặc thư mục tài nguyên mà trang login cần; nếu rule cuối denyAll và không có allow rule, trang có thể hiển thị thiếu CSS/JS.
- **/error** và servlet dispatcher types: khi controller gặp lỗi, servlet có thể chuyển tới **ERROR/FORWARD** dispatch; nếu authorization áp dụng và chặn dispatch đó, phản hồi lỗi có thể khác kỳ vọng. Cần cân nhắc rule có chủ đích cho dispatcher types phù hợp.
- **Actuator**: health/info/metrics, có thể dùng port/path quản trị khác. Khi tự định nghĩa SecurityFilterChain, không giả định các policy mặc định của Boot cho actuator vẫn được áp dụng đúng như trước. Mở đúng health endpoint cần thiết; bảo vệ metrics/env/beans và endpoint nhạy cảm.
- **CORS preflight**: browser có thể gửi **OPTIONS** trước request có Authorization header khác origin. CORS được xử lý phù hợp trước bước authorization và backend cần cấu hình origin/header/method rõ ràng.
- **Login/logout endpoints**: nếu bật formLogin/logout, kiểm tra URL được xử lý và CSRF trên POST.
- **OpenAPI/Swagger UI**: cân nhắc cho phép tài liệu ở môi trường thích hợp; đừng mở tài liệu quản trị ra Internet theo phản xạ.

Một cấu hình production thường phải liệt kê endpoint vận hành, không chỉ ba endpoint trong ví dụ học. **Không mở mọi URL hoặc tắt CSRF chỉ để chữa một lỗi 403**; trước tiên xác định filter/rule nào từ chối request.

## 9. Tùy chỉnh AuthenticationEntryPoint và AccessDeniedHandler

Sau khi SecurityFilterChain hoạt động, đôi lúc client API cần định dạng lỗi cụ thể.

**AuthenticationEntryPoint** chịu trách nhiệm bắt đầu authentication khi chưa có danh tính hợp lệ; với Basic thường là **401** kèm challenge, còn form login thường là **302** đến login. **AccessDeniedHandler** xử lý thiếu quyền đối với danh tính đã xác thực, thường là **403**. **ExceptionTranslationFilter** là thành phần kết nối ngoại lệ bảo mật với những handler này.

Nếu API cần JSON như:

~~~json
{"error":"UNAUTHORIZED"}
~~~

thì phải tự định nghĩa handler/entry point và kiểm thử; đó **không phải response body mặc định bất biến** của mọi ứng dụng Spring Security. Khi tự triển khai, tránh lộ credential, token hay nội dung nội bộ trong body. Nếu API dùng HTTP Basic, cân nhắc giữ challenge header phù hợp cho client thực sự dựa vào HTTP authentication.

Đừng dùng controller **@ExceptionHandler** rồi giả định nó sẽ bắt mọi **AuthenticationException/AccessDeniedException** phát sinh trong servlet filters. Các lỗi có thể xảy ra **trước khi controller được gọi**, nên cấu hình exceptionHandling trong chain là nơi phù hợp cho nhiều use case.

## 10. Debug khi SecurityFilterChain không có hiệu lực như dự kiến

Khi thêm bean mà response vẫn “lạ”, hãy kiểm tra theo thứ tự:

| Quan sát | Điều cần kiểm tra |
| --- | --- |
| Vẫn thấy generated password | Bạn mới thay **web SecurityFilterChain**; có khai báo UserDetailsService/Provider/Manager để thay nguồn user mặc định chưa? |
| GET /public vẫn yêu cầu login | Request có vào đúng chain? Rule permitAll có khớp method/path? Có chain khác được xét trước? |
| POST trả 403 dù đã đăng nhập | Có thể là CSRF hoặc thiếu quyền; xem CSRF token và rule method |
| ROLE_USER vào /admin vẫn được | Có rule rộng permitAll/authenticated đứng trước hasRole không? |
| Login trả 404 | formLogin có được bật? URL GET/POST /login có thuộc matcher của chain không? |
| GET /unknown được truy cập | Có fallback anyRequest().permitAll hoặc request ngoài tất cả chain không? |
| Request API nhận 302 tới /login | Có phải chain web bắt request API trước? API có cấu hình entry point phù hợp không? |
| Gửi Bearer nhưng nhận 401 Basic | Chain chỉ bật httpBasic, chưa bật/cấu hình resource server Bearer token? |
| Nguyên tắc CORS không hoạt động | OPTIONS preflight có được xử lý đúng trước authorization không? |
| Đổi role nhưng session vẫn quyền cũ | Authentication đã lưu trong session/token; cần chiến lược refresh/revalidation/thu hồi |

Có thể bật log Spring Security ở môi trường phát triển:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Khi khởi động, log có thể cho biết những filter có trong chain; khi request đến, log giúp xác định chain/filter/decision. **Không log raw Authorization, cookie, password hoặc access token**. Nếu có nhiều chain, viết test bao phủ *đúng* matcher và các đường dẫn nằm ngoài matcher là rất quan trọng.

### 10.1. Những sai lầm về API và phiên bản

- **Dùng WebSecurityConfigurerAdapter** từ bài cũ cho Spring Security 6: API này đã bị loại bỏ; dùng SecurityFilterChain bean.
- **Nhầm Servlet với WebFlux**: WebFlux dùng **SecurityWebFilterChain** và **ServerHttpSecurity**, không dùng HttpSecurity/Servlet SecurityFilterChain.
- **Nhầm application bean với FilterChainProxy**: bean bạn tạo mô tả filter chain, còn framework quản lý cách chọn/chạy chain.
- **Nhầm requestMatchers với securityMatcher**: một cái xét authorization trong chain, một cái chọn chain.
- **Nhầm hasRole và hasAuthority**: tiền tố ROLE_ mặc định cần được hiểu thống nhất.
- **Nhầm permitAll với bypass filter**: request public vẫn đi qua filter chain và có thể nhận security headers.
- **Nhầm 401/403/302**: response phụ thuộc entry point và tình trạng authentication, không chỉ tên URL.
- **Tắt các lớp bảo vệ để test xanh**: trước hết xác định nguyên nhân 403/CSRF/CORS/session và lựa chọn theo threat model.

## 11. Quy trình đưa SecurityFilterChain vào dự án hiện hữu

Để thay đổi an toàn từ cấu hình mặc định:

1. **Liệt kê chính xác endpoint và HTTP method**: public, authenticated, admin, audit, actuator, login, logout, resources, callback.
2. **Chọn authentication mechanism**: form login/session, HTTP Basic, OAuth2/OIDC, JWT/opaque resource server, custom provider hoặc phối hợp nhiều chain.
3. **Định nghĩa SecurityFilterChain bean**: dùng HttpSecurity, đặt rule cụ thể trước, fallback deny phù hợp, cấu hình filter cần thiết.
4. **Khai báo nguồn danh tính**: UserDetailsService/AuthenticationProvider/AuthenticationManager hoặc JWT decoder/introspector; không mặc nhiên dựa vào generated user.
5. **Kiểm tra chain coverage**: nếu có nhiều chain, dùng securityMatcher và @Order, bảo đảm mọi URL cần bảo vệ đều khớp ít nhất một chain.
6. **Rà soát CSRF, CORS, session, headers và error dispatch**: dựa trên client và credential transport; không áp dụng một cấu hình cho mọi loại ứng dụng theo thói quen.
7. **Kiểm thử cả trường hợp được phép và bị từ chối**: anonymous, đúng/sai password, đúng/sai role, unlisted path, path với method khác, callback/login/logout.
8. **Quan sát log và HTTP response**: đọc 401/403/302, kiểm tra challenge, session cookie, các filter đang áp dụng.
9. **Triển khai với HTTPS và bảo vệ secrets**: passwords demo phải được thay, quyền tối thiểu và chính sách thu hồi credential phải được thiết kế.
10. **Duy trì policy khi thêm tính năng**: endpoint mới phải có allow rule rõ ràng; phương thức nghiệp vụ nhạy cảm nên được kiểm tra quyền theo resource/tenant, không chỉ role URL.

**Thay cấu hình mặc định là chuyển quyền quyết định chính sách bảo vệ sang ứng dụng.** Hãy bảo đảm policy mới bao phủ mọi đường đi quan trọng; một cấu hình “ít dòng” không tự đồng nghĩa cấu hình an toàn.

## 12. Bài tập tự kiểm tra

**Câu 1.** Chỉ thêm bean SecurityFilterChain có làm Spring Boot ngừng tạo generated user không?

**Đáp án:** Không nhất thiết. Bean SecurityFilterChain làm Boot lùi bước khỏi default web security configuration; nguồn user mặc định là phần auto-configuration khác. Cần UserDetailsService/AuthenticationProvider/AuthenticationManager phù hợp nếu muốn thay nguồn authentication đó.

**Câu 2.** Trong rule **requestMatchers("/public").permitAll()**, request có bỏ qua mọi filter Spring Security không?

**Đáp án:** Không. **permitAll()** là quyết định authorization, request vẫn đi qua SecurityFilterChain được chọn và các filter còn lại.

**Câu 3.** Nếu đặt **anyRequest().permitAll()** trước rule **/admin → hasRole("ADMIN")**, điều gì xảy ra?

**Đáp án:** Không nên viết cấu hình như vậy; rule cho tất cả request có thể che rule chi tiết, hoặc DSL báo lỗi vì không được thêm rule sau anyRequest, tùy cách diễn đạt và phiên bản. Hãy để rule cụ thể trước, fallback ở cuối.

**Câu 4.** Có một chain **securityMatcher("/api/**")** với **anyRequest().denyAll()**. /internal/debug có chắc bị Spring Security chặn không?

**Đáp án:** Không. Nếu không có chain khác khớp /internal/debug, request có thể nằm ngoài Spring Security. DenyAll bên trong API chain không áp dụng cho URL không khớp chain đó.

**Câu 5.** Tạo SecurityFilterChain nhưng chỉ gọi **authorizeHttpRequests(...).anyRequest().authenticated()**. HTTP Basic có tự được bật như cấu hình mặc định của Boot không?

**Đáp án:** Không nên giả định. Khi tự tạo chain, cần cấu hình mechanism dự kiến, ví dụ **httpBasic(Customizer.withDefaults())** hoặc **formLogin(Customizer.withDefaults())**.

**Câu 6.** HTTP Basic user alice có ROLE_USER gửi GET /admin đòi ROLE_ADMIN. Vì sao nhận 403?

**Đáp án:** Authentication có thể thành công nhưng authorities không thỏa policy. Đó là authorization denial.

**Câu 7.** API vừa thêm POST /orders, cùng path GET được permitAll. Có nghĩa POST cũng public?

**Đáp án:** Không nếu rule phân theo HTTP method. POST phải có rule phù hợp; CSRF có thể cũng áp dụng nếu đang bật.

**Câu 8.** Bật **formLogin** trong chain chỉ nhận **/secured/** nhưng dùng URL login mặc định **/login**. Vì sao có thể trả 404?

**Đáp án:** Filter chain xử lý login có thể không được chọn cho /login, khiến endpoint do filter cung cấp không tồn tại. Cần điều chỉnh login URL/matcher/chain cho nhất quán.

**Câu 9.** Tại sao một REST controller có thể trả 302 khi chưa đăng nhập?

**Đáp án:** Nếu request đi qua chain bật form login và entry point cho redirect, Spring Security có thể chuyển hướng đến login. REST controller không tự quyết định entry point.

**Câu 10.** Khi người dùng đổi role, SecurityFilterChain có tự cập nhật Authentication trong các session/JWT đang có không?

**Đáp án:** Không mặc định. Cần chiến lược session invalidation, token expiration/revocation hoặc revalidation và test vòng đời quyền phù hợp.

## Tài liệu tham khảo chính thức

- Spring Boot 3.x — Security auto-configuration: https://docs.spring.io/spring-boot/3.4/reference/web/spring-security.html
- Spring Boot — How-to Security: https://docs.spring.io/spring-boot/3.4/how-to/security.html
- Spring Security 6.5 — Java Configuration / Multiple HttpSecurity: https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html
- Spring Security — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security — Servlet Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html
- Spring Security — CSRF: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Spring Security — HTTP Basic: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html

**Ghi nhớ:** khai báo **@Bean SecurityFilterChain** giúp ứng dụng thay cấu hình web mặc định của Boot bằng chính sách HTTP rõ ràng. Sau đó vẫn phải quyết định **cách xác thực**, **nguồn người dùng/token**, **rule phân quyền**, **CSRF/CORS/session** và **độ bao phủ của các chain**. Một cấu hình tốt cho phép đúng nơi cần mở, yêu cầu đúng quyền ở nơi cần bảo vệ và từ chối những đường đi chưa được khai báo.
