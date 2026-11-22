# Tạo endpoint công khai và endpoint cần xác thực với Spring Security

Một ứng dụng thường có **API công khai**, chẳng hạn trang giới thiệu hoặc danh mục sản phẩm, và **API chỉ dành cho người đã đăng nhập**, chẳng hạn thông tin hồ sơ. Trong Spring Boot, tạo hai phương thức Controller là bước đầu; phần quyết định ai được gọi từng endpoint nên đặt tại **Spring SecurityFilterChain** để áp dụng chính sách nhất quán trước khi request đi tới Controller.

Bài thực hành này tạo đúng hai endpoint:

- **GET /api/public**: mọi người, kể cả người chưa đăng nhập, được gọi.
- **GET /api/me**: người gọi phải có danh tính đã được xác thực.

Ví dụ sử dụng **Java 17+, Spring Boot 3.3.6, Spring Security 6.x, Maven, Spring MVC và HTTP Basic** để dễ quan sát sự khác nhau. Tài khoản nằm trong bộ nhớ và chỉ dùng cho thực hành trên localhost. Khi làm hệ thống thật, cơ chế đăng nhập, lưu credential và quản lý phiên/token phải được thiết kế riêng.

## 1. Mục tiêu của bài

Sau khi hoàn thành, bạn có thể:

1. Tạo một REST Controller với hai endpoint GET.
2. Thêm dependency Spring Security và viết bean **SecurityFilterChain**.
3. Dùng **permitAll()** để cho phép truy cập công khai và **authenticated()** để yêu cầu đăng nhập.
4. Cấu hình một tài khoản demo với **UserDetailsService** và **PasswordEncoder**.
5. Quan sát kết quả **200 OK** và **401 Unauthorized** bằng curl.
6. Viết kiểm thử MockMvc bao phủ truy cập ẩn danh, đúng/sai credential và phương thức HTTP khác.
7. Giải thích vì sao “đăng nhập hợp lệ” vẫn khác với “được phép thực hiện mọi hành động”.

Bài tập không yêu cầu hệ thống cơ sở dữ liệu, frontend, OAuth2 hay JWT. Hai endpoint đủ để thấy cơ chế bảo vệ hoạt động và làm nền cho các bước học phân quyền tiếp theo.

## 2. Hiểu luồng request trước khi viết code

Với một request GET từ browser hoặc curl, Spring Boot xử lý khái quát như sau:

~~~text
HTTP client
    |
    v
Servlet container (ví dụ Tomcat)
    |
    v
DelegatingFilterProxy
    |
    v
Spring Security FilterChainProxy
    |
    v
SecurityFilterChain phù hợp request
    |-- xử lý SecurityContext / authentication khi cần
    |-- kiểm tra authorization rule
    |
    +-- Không được phép --> AuthenticationEntryPoint / denied handling
    |                         --> HTTP 401, 403 hoặc phản hồi theo cấu hình
    |
    +-- Được phép ------> DispatcherServlet
                              |
                              v
                         REST Controller
                              |
                              v
                         HTTP response
~~~

**Authentication (xác thực)** trả lời “người gọi là ai và bằng chứng có hợp lệ không?”. **Authorization (phân quyền)** trả lời “người gọi đã xác thực này có quyền thực hiện request không?”.

Trong bài:

- GET /api/public dùng **permitAll()** nên được phép mà không phải cung cấp danh tính.
- GET /api/me dùng **authenticated()**, nên chỉ đi vào Controller sau khi có Authentication hợp lệ theo cơ chế đã cấu hình.
- Với API HTTP Basic, một request tới /api/me **không có hoặc có credential sai** thường nhận **401** kèm **WWW-Authenticate** để báo cần xác thực.
- Một người **đã xác thực nhưng thiếu role hoặc quyền** thường nhận **403** khi chính sách yêu cầu quyền cao hơn. Bài này mới yêu cầu “đã đăng nhập”, chưa có endpoint dành riêng cho ADMIN.

Spring Security có thể chặn request **trước Controller**. Vì vậy việc thiếu một câu lệnh if kiểm tra mật khẩu trong Controller là có chủ đích: Controller xử lý nghiệp vụ, còn filter chain thi hành chính sách truy cập.

## 3. Chuẩn bị môi trường và cấu trúc dự án

Yêu cầu:

- **JDK 17 trở lên**, đã có lệnh java và javac.
- **Maven 3.9+** hoặc Maven Wrapper phù hợp.
- Port 8080 trên máy local chưa bị chiếm.
- Công cụ HTTP như curl; trên Windows PowerShell có thể dùng **curl.exe** để tránh trùng alias trên một số phiên bản.

Tạo thư mục dự án:

~~~text
public-private-api/
├── pom.xml
└── src
    ├── main
    │   └── java
    │       └── com
    │           └── example
    │               └── accessdemo
    │                   ├── AccessDemoApplication.java
    │                   ├── ApiController.java
    │                   └── SecurityConfig.java
    └── test
        └── java
            └── com
                └── example
                    └── accessdemo
                        └── ApiAccessTests.java
~~~

Tất cả các file Java dùng package **com.example.accessdemo**, khớp với đường dẫn thư mục. Lớp có **@SpringBootApplication** nằm ở package gốc để Spring Boot tự quét Controller và Configuration cùng package.

Nếu cần kiểm tra phiên bản công cụ:

~~~bash
java -version
javac -version
mvn -version
~~~

## 4. Khai báo Maven dependencies

Tạo **pom.xml** ở thư mục gốc dự án:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.6</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>public-private-api</artifactId>
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

Vai trò từng dependency:

| Dependency | Dùng để làm gì? |
| --- | --- |
| spring-boot-starter-web | Tạo REST API bằng Spring MVC, chạy embedded Servlet container và xuất JSON qua Jackson. |
| spring-boot-starter-security | Cung cấp security filter chain, authentication, authorization và PasswordEncoder. |
| spring-boot-starter-test | JUnit 5, Spring Boot Test, MockMvc và các công cụ kiểm thử liên quan. |
| spring-security-test | Các request post-processor cho MockMvc như **httpBasic()**, **csrf()**, và tiện ích kiểm thử bảo mật. |

Khi có Spring Security starter nhưng chưa cấu hình riêng, ứng dụng Spring Boot thường có cấu hình bảo vệ mặc định. Nếu muốn **một endpoint công khai và một endpoint cần xác thực theo chính sách cụ thể**, bạn nên khai báo SecurityFilterChain rõ ràng, thay vì chờ framework đoán nhu cầu của ứng dụng.

Phiên bản 3.3.6 trong ví dụ được dùng để giữ mã nguồn bài thực hành nhất quán. Khi triển khai sản phẩm thật, dùng dòng Spring Boot/Spring Security còn được hỗ trợ và cập nhật bản vá phù hợp.

## 5. Tạo lớp khởi chạy Spring Boot

Tạo **src/main/java/com/example/accessdemo/AccessDemoApplication.java**:

~~~java
package com.example.accessdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AccessDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(AccessDemoApplication.class, args);
    }
}
~~~

Chức năng:

- **@SpringBootApplication** kích hoạt auto-configuration và component scanning thông thường của Spring Boot.
- **SpringApplication.run(...)** khởi động ứng dụng và embedded server.
- Không cần viết Servlet Filter thủ công trong lớp main.

Đến đây ứng dụng có thể khởi động khi các dependency hợp lệ, nhưng chưa có endpoint nghiệp vụ.

## 6. Tạo hai endpoint trong một REST Controller

Tạo **src/main/java/com/example/accessdemo/ApiController.java**:

~~~java
package com.example.accessdemo;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class ApiController {

    @GetMapping("/public")
    public Map<String, String> publicInfo() {
        return Map.of("message", "public");
    }

    @GetMapping("/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }
}
~~~

**Điều gì xảy ra ở mỗi method?**

- **@RestController** cho Spring MVC biết đây là controller trả response body. Với kiểu **Map**, Jackson tạo JSON.
- **@RequestMapping("/api")** đặt tiền tố cho cả hai method.
- **@GetMapping("/public")** tương ứng GET /api/public.
- **@GetMapping("/me")** tương ứng GET /api/me.
- Tham số **Authentication authentication** được Spring MVC hỗ trợ lấy từ ngữ cảnh bảo mật của request khi một người dùng đã được xác thực. Trong luồng này, cấu hình bảo vệ /api/me đảm bảo handler chỉ chạy sau kiểm tra authenticated() thành công.
- **authentication.getName()** trả tên principal từ danh tính đã được xác thực, không đọc tùy tiện userId/role do client gửi lên.

Dữ liệu mẫu:

~~~json
{"message":"public"}
~~~

và:

~~~json
{"username":"learner"}
~~~

Đừng thêm logic kiểu **if (request.getHeader("X-Role").equals("USER"))** để tự quyết định danh tính: client có thể tạo header tùy ý. Chúng ta sẽ để Spring Security kiểm chứng credential và thi hành chính sách.

## 7. Khai báo SecurityFilterChain: permitAll và authenticated

Tạo **src/main/java/com/example/accessdemo/SecurityConfig.java**:

~~~java
package com.example.accessdemo;

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
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .anyRequest()
                    .denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(
            PasswordEncoder encoder) {

        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("demo-password"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(learner);
    }
}
~~~

Đây là **cấu hình đầy đủ** cho bài lab. Bạn không cần tạo WebSecurityConfigurerAdapter; cách cấu hình hiện đại dùng bean **SecurityFilterChain**.

### 7.1. Từng quy tắc có ý nghĩa gì?

~~~java
.requestMatchers(HttpMethod.GET, "/api/public").permitAll()
~~~

Cho phép **GET /api/public** kể cả khi người gọi không có tài khoản. **permitAll() là quy tắc authorization**: nó không tạo một SecurityFilterChain riêng, không bỏ qua mọi filter và không có nghĩa server sẽ bỏ qua các kiểm soát khác. Chẳng hạn, nếu client gửi một header Authorization chứa HTTP Basic credential sai, bộ lọc xác thực có thể từ chối request trước bước quyết định permitAll. Vì vậy khi thử “public”, nên gọi **không gửi credential**.

~~~java
.requestMatchers(HttpMethod.GET, "/api/me").authenticated()
~~~

Yêu cầu GET /api/me có **Authentication phù hợp**. Spring Security kiểm tra danh tính theo HTTP Basic đã cấu hình. Một tài khoản có role USER cũng đủ vì **authenticated() không yêu cầu một role cụ thể**.

~~~java
.anyRequest().denyAll()
~~~

Từ chối mọi request chưa khớp các quy tắc phía trên. Điều này giúp endpoint mới không tự công khai ngoài ý muốn. Tuy nhiên, nó cũng có nghĩa **các đường khác** (ví dụ GET /hello, POST /api/public, /actuator/** nếu có) không tự được cho phép. Khi bổ sung tính năng, phải thêm chính sách cụ thể và kiểm thử.

**Thứ tự matcher quan trọng**: Spring Security đánh giá các rule theo thứ tự và dùng rule khớp phù hợp đầu tiên. Đặt rule cụ thể trước rule tổng quát. Nếu đặt **anyRequest().denyAll()** lên trước, các rule sau sẽ không có cơ hội được xét.

**HttpMethod.GET** giúp phân biệt GET /api/public với POST /api/public. Chỉ định path công khai mà không ràng buộc method đôi khi mở rộng quyền sang các thao tác không mong muốn.

### 7.2. Vì sao dùng HTTP Basic ở bài đầu tiên?

~~~java
.httpBasic(Customizer.withDefaults())
~~~

Bật cơ chế xử lý **Authorization: Basic ...**. Khi nhận request có credential, Spring Security đưa thông tin cho thành phần xác thực, đối chiếu user và mật khẩu qua **UserDetailsService**/**PasswordEncoder**, xây dựng Authentication, rồi thực hiện kiểm tra quyền.

HTTP Basic dễ gọi bằng curl và không cần trang login. Nó có giới hạn:

- Credential được mã hóa **Base64**, không phải mã hóa bí mật; chỉ dùng qua **HTTPS** trên mạng thật.
- Client thường gửi Authorization với từng request; phải bảo vệ credential, log và cấu hình cache/trình duyệt.
- Nó không thay thế cơ chế khóa tài khoản, MFA, vòng đời mật khẩu, token hoặc kiểm soát người dùng ngoài phạm vi ví dụ.
- HTTP Basic không tự chứng minh ứng dụng “stateless” theo mọi nghĩa; session/request cache hay các filter khác còn phụ thuộc cấu hình.
- Nếu trình duyệt tự động gửi credential đã lưu, vẫn phải xét nguy cơ CSRF đối với request thay đổi dữ liệu.

Bài này **chỉ dùng GET** nên không cần thao tác gửi CSRF token. Chúng ta không tắt CSRF mặc định của Spring Security. Khi thêm POST/PUT/PATCH/DELETE, phải thiết kế xác thực và CSRF cho đúng loại client.

### 7.3. Tài khoản demo, mật khẩu và vai trò

~~~java
UserDetails learner = User.withUsername("learner")
    .password(encoder.encode("demo-password"))
    .roles("USER")
    .build();
~~~

- Username **learner**, mật khẩu demo **demo-password**.
- **BCryptPasswordEncoder** tạo hash để lưu và so khớp mật khẩu trong UserDetails; không lưu mật khẩu nguyên văn vào thuộc tính password của user.
- **InMemoryUserDetailsManager** giữ tài khoản trong bộ nhớ. Khởi động lại ứng dụng sẽ tạo user demo mới.
- **roles("USER")** tạo authority theo quy ước **ROLE_USER**. Nhưng /api/me chỉ cần authenticated(), nên role không phải điều kiện bắt buộc trong bài này.

Mật khẩu demo đang có sẵn trong mã nguồn để người học thử. **Không đưa tài khoản/mật khẩu này lên môi trường công khai hoặc dùng cho dữ liệu thật.** Production cần secret management và kho danh tính phù hợp.

### 7.4. Những gì cấu hình này chưa giải quyết

Tạo một endpoint có yêu cầu đăng nhập **chưa phải là hoàn thành toàn bộ bảo mật**:

- Chưa có quản lý người dùng thật, đổi mật khẩu, reset password hay MFA.
- Chưa có quyền theo role/permission phức tạp.
- Chưa có quyền theo tài nguyên, ownerId hoặc tenant.
- Chưa có OAuth2, OpenID Connect hoặc JWT Resource Server.
- Chưa có rate limit, audit, secret rotation, kiểm soát vận hành và giám sát.
- Chưa có cấu hình HTTPS/gateway cho môi trường triển khai.

Đây là nền tảng để hiểu các quyết định xác thực và phân quyền trên hai endpoint, không phải mẫu cấu hình đầy đủ cho production.

## 8. Chạy ứng dụng và xem kết quả

Mở terminal tại thư mục chứa pom.xml:

~~~bash
mvn spring-boot:run
~~~

Nếu khởi động thành công, embedded server thường lắng nghe tại:

~~~text
http://localhost:8080
~~~

**Các lệnh dưới đây sử dụng curl.exe trên Windows**. Trên Linux/macOS, có thể thay **curl.exe** bằng **curl**.

### 8.1. GET endpoint công khai khi chưa đăng nhập

~~~powershell
curl.exe -i http://localhost:8080/api/public
~~~

Kết quả mong đợi:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"message":"public"}
~~~

Các header khác có thể xuất hiện và thứ tự header không cố định. Quan trọng là **status 200** cùng JSON chứa message public.

**Vì sao được 200?** Rule **permitAll()** áp dụng cho GET /api/public. Không yêu cầu Authorization hoặc cookie đăng nhập.

### 8.2. GET endpoint bảo vệ khi chưa đăng nhập

~~~powershell
curl.exe -i http://localhost:8080/api/me
~~~

Kết quả mong đợi: **401 Unauthorized** và một HTTP Basic challenge.

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"

~~~

Giá trị realm, các security header và response body lỗi có thể khác theo cấu hình. Không cố định toàn bộ response. Với cơ chế HTTP Basic, **401** báo request cần credential hợp lệ; GET /api/me không đi vào phương thức me() của Controller trong trường hợp này.

### 8.3. GET endpoint bảo vệ với đúng tài khoản

~~~powershell
curl.exe -i -u learner:demo-password http://localhost:8080/api/me
~~~

Kết quả mong đợi:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"username":"learner"}
~~~

Tham số **-u** khiến curl tạo HTTP Basic Authorization từ cặp user/password. Spring Security xác minh mật khẩu thông qua UserDetailsService và PasswordEncoder, sau đó kiểm tra authenticated() và cho phép Controller chạy.

**Không dùng -u với mật khẩu thật trong ví dụ chia sẻ/public**: secret có thể bị lộ trong shell history hoặc process arguments. Chỉ sử dụng tài khoản giả trên localhost.

### 8.4. GET endpoint bảo vệ với mật khẩu sai

~~~powershell
curl.exe -i -u learner:wrong-password http://localhost:8080/api/me
~~~

Kết quả mong đợi: **401 Unauthorized**. User name tồn tại nhưng password sai không tạo Authentication hợp lệ; server không cấp quyền gọi /api/me.

Trong API thật, thông điệp lỗi xác thực cần tránh làm lộ thông tin về việc một tài khoản có tồn tại hay không.

### 8.5. GET endpoint công khai dù người dùng chưa có role

Bạn có thể mở http://localhost:8080/api/public trên trình duyệt bình thường. Ở mức ứng dụng web, browser có thể hiển thị JSON hoặc tải response về tùy cách sử dụng. Nếu mở http://localhost:8080/api/me, trình duyệt có thể hiển thị hộp thoại HTTP Basic tùy hành vi browser và cách server phát challenge. Đó là hành vi client, không phải Spring Boot tự tạo form login HTML.

Trong bài này, **curl đáng tin cậy hơn để kiểm tra chính xác status**, vì không tự xử lý giao diện đăng nhập hay che response theo trải nghiệm browser.

### 8.6. Bảng đối chiếu nhanh

| Method và endpoint | Credential | Dự kiến | Nguyên nhân |
| --- | --- | --- | --- |
| GET /api/public | Không có | **200** | Được permitAll(). |
| GET /api/me | Không có | **401** | Chưa xác thực; HTTP Basic challenge. |
| GET /api/me | learner / demo-password | **200** | Credential hợp lệ, đáp ứng authenticated(). |
| GET /api/me | learner / wrong-password | **401** | Mật khẩu sai, xác thực thất bại. |
| POST /api/public | learner / demo-password, có CSRF token hợp lệ | **403** | Không có rule cho phép POST; fallback denyAll(). |

Với một request POST từ curl **không có CSRF token**, Spring Security có thể trả 403 từ **CsrfFilter** trước khi đến authorization. Vì thế chỉ nhìn “POST /api/public trả 403” không đủ để chứng minh nguyên nhân là denyAll(). Khi muốn kiểm đúng matcher GET, cần test có CSRF token hợp lệ để loại trừ tác động của CSRF filter như ở mục kiểm thử.

## 9. Viết test với MockMvc và Spring Security Test

Bài tập thực hành nên có test để tránh vô tình biến endpoint bảo vệ thành public khi người khác thay cấu hình. Tạo file:

**src/test/java/com/example/accessdemo/ApiAccessTests.java**

~~~java
package com.example.accessdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ApiAccessTests {

    @Autowired
    private MockMvc mvc;

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public"));
    }

    @Test
    void privateEndpointRejectsAnonymous() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void privateEndpointAllowsValidBasicCredentials() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("learner", "demo-password")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("learner"));
    }

    @Test
    void privateEndpointRejectsWrongPassword() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("learner", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void publicGetRuleDoesNotPermitPost() throws Exception {
        mvc.perform(post("/api/public")
                .with(httpBasic("learner", "demo-password"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void otherRouteIsDeniedForAuthenticatedUser() throws Exception {
        mvc.perform(get("/api/unknown")
                .with(httpBasic("learner", "demo-password")))
            .andExpect(status().isForbidden());
    }
}
~~~

Chạy test bằng Maven:

~~~bash
mvn test
~~~

**Kết quả kỳ vọng:** sáu test chạy thành công nếu code/configuration đúng và môi trường đầy đủ. Không cố định dòng “Tests run: ...” của một phiên bản Maven vì output plugin, thời gian chạy và log khác nhau.

### 9.1. Vì sao test từng trường hợp này?

- **publicEndpointAllowsAnonymous**: chứng minh public endpoint không đòi xác thực.
- **privateEndpointRejectsAnonymous**: xác nhận đường riêng tư được chặn trước Controller.
- **privateEndpointAllowsValidBasicCredentials**: chứng minh đường hợp lệ đi đến Controller, và Authentication chứa principal learner.
- **privateEndpointRejectsWrongPassword**: chứng minh không thể qua kiểm soát chỉ bằng cách gửi bất kỳ Authorization.
- **publicGetRuleDoesNotPermitPost**: xác nhận rule chỉ cho phép GET. Test gắn **csrf()** để tránh CSRF che mất kiểm tra authorization; gắn user hợp lệ để fallback denyAll() trả 403 thay vì nhánh chưa xác thực.
- **otherRouteIsDeniedForAuthenticatedUser**: xác nhận fail-closed: cả user đã đăng nhập cũng không mặc nhiên được gọi đường chưa có chính sách.

Khi test endpoint khác có side effects, ngoài status cần xác minh DB hoặc message không bị thay đổi nếu bị từ chối. Một request trả 403 nhưng vẫn ghi dữ liệu trái phép là lỗi nghiêm trọng.

### 9.2. Test có khác curl thật không?

MockMvc gọi stack Spring MVC và các filter trong ứng dụng test mà không mở cổng HTTP thực sự, vì vậy nó rất tốt để kiểm tra route và chính sách Spring Security. Nhưng nó không chứng minh TLS, reverse proxy, mạng hay cấu hình deployment đã đúng.

Dùng cả hai:

- **MockMvc:** test lặp lại nhanh, phát hiện lỗi rule/auth/handler.
- **curl/HTTP integration:** kiểm ứng dụng thật đang chạy, status/headers, basic challenge và đường đi server.
- **Kiểm thử deploy:** xác minh proxy, HTTPS, các environment-specific properties và đường quản trị nếu có.

## 10. Những lỗi thường gặp khi tạo public và protected endpoint

### 10.1. Thêm Spring Security và mọi URL bỗng cần đăng nhập

Khi bạn thêm spring-boot-starter-security, Spring Boot có thể bật cấu hình bảo mật mặc định. Nếu chưa khai báo SecurityFilterChain, endpoint mà trước đây công khai có thể bị yêu cầu xác thực. Giải pháp là **định nghĩa chính sách cụ thể**; đừng xóa dependency chỉ để tránh màn hình đăng nhập.

### 10.2. permitAll() bị hiểu là bỏ qua toàn bộ bảo mật

**permitAll()** cho phép authorization với matcher đó, nhưng không bỏ qua các filter đã áp dụng. Những filter xác thực, CSRF, security headers và kiểm soát khác vẫn tồn tại theo cấu hình. Không tùy tiện thay bằng **web.ignoring()** cho REST endpoint thông thường vì bỏ qua toàn bộ Spring Security filter chain còn có thể bỏ mất các cơ chế bảo vệ mong muốn.

### 10.3. URL trong Controller và matcher không khớp

Ví dụ Controller có @RequestMapping("/api") và @GetMapping("/me"), nhưng SecurityFilterChain lại cấu hình "/me" thay vì "/api/me". Kết quả route thật không khớp rule, có thể rơi vào denyAll().

Luôn đọc **path cuối cùng** sau khi cộng tiền tố Controller, context path, gateway rewrite và các HTTP method thực sự. Không tự đoán matcher theo tên method Java.

### 10.4. Tự đặt endpoint /api/public nhưng quên giới hạn GET

Nếu dùng:

~~~java
.requestMatchers("/api/public").permitAll()
~~~

matcher không ràng buộc HTTP method. Nếu sau này có POST /api/public, request đó có thể được cho phép ở tầng authorization dù đáng lẽ cần một chính sách riêng. Dùng matcher theo method khi ngữ nghĩa nghiệp vụ yêu cầu.

### 10.5. Đặt anyRequest().permitAll() quá rộng

~~~java
.anyRequest().permitAll()
~~~

Đây là cấu hình có thể làm endpoint mới mở công khai, trừ các quy tắc đặt trước đó. Bài này dùng **anyRequest().denyAll()** để buộc mọi route chưa được liệt kê cần một quyết định rõ ràng.

Khi thêm actuator, file static, error page hoặc login UI sau này, bạn phải cập nhật rule phù hợp với loại endpoint; không mặc nhiên mở tất cả.

### 10.6. Tin rằng role USER là điều kiện của authenticated()

**authenticated()** chỉ yêu cầu danh tính đã được xác thực theo chính sách. Nó không phải viết tắt của **hasRole("USER")**. Khi cần role cụ thể, thêm hasRole/hasAuthority theo đúng mô hình quyền và kiểm tra với từng endpoint hoặc method.

### 10.7. Gọi URL đúng nhưng nhận 403 thay vì 401

Các nguyên nhân có thể khác nhau:

- Principal hợp lệ nhưng policy từ chối.
- Request POST/PUT/DELETE thiếu CSRF token khi CSRF protection áp dụng.
- Một route không khớp matcher và rơi vào denyAll().
- Gateway hoặc filter khác chủ động từ chối.
- Custom authentication/authorization handlers đã thay HTTP status.

Vì vậy debug phải xem **method, path, credential, CSRF, chain match và log liên quan**, không suy luận chỉ từ status.

### 10.8. Dùng HTTP Basic trong hệ thống thật qua HTTP thuần

HTTP Basic gửi credential dưới dạng Base64 trong Authorization. Đây **không phải mã hóa**. Dùng **HTTPS**, quản lý mật khẩu/secret, thời hạn và audit phù hợp; không in Authorization hoặc Cookie vào log và không dùng thông tin demo.

### 10.9. Cho rằng mọi lỗi 401 đều là do Controller

Với GET /api/me ẩn danh, Spring Security có thể từ chối request **trước khi ApiController.me() chạy**, thông qua Basic authentication entry point. Thêm try/catch trong Controller không giúp xử lý các trường hợp bị chặn từ filter phía trước. Tùy chỉnh phản hồi 401/403 cần cấu hình đúng security handler khi thật sự cần.

### 10.10. Lẫn lộn CORS và authentication

Nếu frontend JavaScript chạy ở một origin khác API, browser còn áp dụng **CORS**, đôi khi có OPTIONS preflight. Curl không bị chính sách CORS của browser chặn đọc response. CORS không cho phép một user bỏ qua Spring Security; request GET /api/me vẫn cần credential hợp lệ dù Access-Control-Allow-Origin đã cho phép browser đọc response.

## 11. Mở rộng sau khi hoàn thành bài cơ bản

Sau khi đã phân biệt public và authenticated, các bài tiếp theo thường nâng dần độ phức tạp:

### 11.1. Phân quyền theo vai trò

Có thể yêu cầu vai trò ADMIN cho một URL riêng:

~~~java
.requestMatchers(HttpMethod.GET, "/api/admin")
    .hasRole("ADMIN")
~~~

Đây chỉ là **mảnh cấu hình minh họa**, chưa có method Controller hay role ADMIN trong dự án hai endpoint ở trên. Khi mở rộng, cần bổ sung endpoint và principal phù hợp rồi kiểm thử 403/200.

### 11.2. Phân quyền theo đối tượng dữ liệu

Ví dụ GET /api/orders/42 có thể chỉ yêu cầu authenticated() ở URL, nhưng người dùng A không được phép đọc đơn 42 của người dùng B. Service phải kiểm quyền **owner/tenant** trước khi trả dữ liệu. Một SecurityFilterChain áp dụng role ở URL không tự hiểu mọi quy tắc nghiệp vụ.

### 11.3. Chuyển từ HTTP Basic sang Bearer/JWT

Với API sử dụng OAuth2 Resource Server, client gửi Authorization: Bearer token, server cần **xác minh chữ ký hoặc introspection, issuer, expiry, audience khi chính sách yêu cầu và scope/authority**. Chỉ giải mã JWT và tin role từ payload không đủ. Chính sách permitAll()/authenticated() vẫn có cùng mục tiêu khái niệm nhưng cơ chế xác thực khác.

### 11.4. Khi thêm thao tác ghi dữ liệu

POST /api/orders hoặc PUT /api/profile cần **authorization theo hành động và dữ liệu**, input validation, kiểm concurrency và cân nhắc CSRF theo cách client gửi credential. Không tắt CSRF chỉ để curl POST dễ thành công.

Với browser gửi cookie/session tự động, CSRF protection thường là cơ chế trọng yếu. Với API stateless chỉ chấp nhận Bearer token chủ động gắn vào Authorization, threat model và cấu hình CSRF có thể khác; vẫn phải bảo vệ token trước XSS/leak.

### 11.5. Dùng nhiều SecurityFilterChain

Ứng dụng lớn có thể cần chain riêng cho /api/** và web form login với thứ tự riêng. Khi đó cần kiểm tra **securityMatcher**, @Order và fallback. Đừng cấu hình chain hẹp rồi để route ngoài mọi chain vô tình mất kiểm soát. Bài này dùng **một chain** để tập trung vào phân biệt public với authenticated.

## 12. Checklist triển khai và tự kiểm tra

Trước khi hoàn thành bài, xác minh:

- **GET /api/public** hoạt động với request không Authorization.
- **GET /api/me** không có credential nhận 401 theo HTTP Basic.
- **GET /api/me** với learner/demo-password nhận JSON username learner.
- **Credential sai** không truy cập được /api/me.
- **POST /api/public** không được công khai chỉ vì GET /api/public công khai.
- **Endpoint mới** bị chặn nếu chưa có rule và cấu hình fail-closed.
- Cấu hình có **SecurityFilterChain** và **UserDetailsService** rõ ràng.
- Mật khẩu lưu trong UserDetails dạng hash tạo bởi **PasswordEncoder**.
- Không lưu hoặc ghi log password/token thật; không dùng Basic qua HTTP ngoài môi trường học tập cô lập.
- Kiểm tra **mvn test** và thử HTTP thực tế trên localhost.

**Câu hỏi tự luyện:**

1. Tại sao @GetMapping("/api/public") không đủ để khai báo endpoint công khai khi Spring Security đang bật?  
   **Gợi ý:** Controller mapping xử lý routing; SecurityFilterChain quyết định authorization trước Controller.
2. Điểm khác nhau giữa permitAll() và authenticated() là gì?  
   **Gợi ý:** một rule cho phép ẩn danh, rule kia cần danh tính hợp lệ.
3. Vì sao GET /api/me ẩn danh thường nhận 401, còn user đã xác thực nhưng thiếu role thường nhận 403?  
   **Gợi ý:** phân biệt authentication với authorization.
4. Vì sao nên ràng buộc HttpMethod.GET khi chỉ muốn mở công khai endpoint đọc?  
   **Gợi ý:** tránh mở ngoài ý muốn các method thay đổi dữ liệu trên cùng path.
5. POST /api/public bị 403 thì làm sao biết do CSRF hay denyAll()?  
   **Gợi ý:** loại trừ CSRF bằng MockMvc csrf() và cung cấp danh tính hợp lệ để kiểm riêng rule authorization.
6. Tại sao InMemoryUserDetailsManager và mật khẩu demo không phù hợp cho production?  
   **Gợi ý:** quản lý tài khoản, vòng đời secret, bảo vệ credential và khả năng vận hành.
7. Nếu có thêm GET /api/orders/42, điều kiện authenticated() đã đủ đảm bảo user A không đọc đơn của B chưa?  
   **Gợi ý:** chưa; cần kiểm quyền cấp đối tượng ở Service/domain.

## Kết luận

Để tạo một endpoint công khai và một endpoint cần xác thực trong Spring Security, hãy định nghĩa **Controller route**, khai báo **SecurityFilterChain** với **permitAll()** cho đường công khai và **authenticated()** cho đường riêng tư, rồi chọn cơ chế xác thực và tài khoản phù hợp. Kiểm thử cả anonymous, credential đúng/sai, HTTP method và route chưa được liệt kê. Cơ chế này giúp Controller tập trung vào nghiệp vụ, đồng thời ngăn request thiếu quyền trước khi truy cập dữ liệu; khi mở rộng ứng dụng, vẫn phải bổ sung phân quyền theo vai trò và theo tài nguyên cụ thể.
