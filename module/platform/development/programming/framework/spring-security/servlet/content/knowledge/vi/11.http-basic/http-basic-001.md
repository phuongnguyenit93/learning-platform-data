# Luồng HTTP Basic và header Authorization trong Spring Security Servlet

## 1. Mục tiêu bài học

**HTTP Basic Authentication** là một cơ chế xác thực HTTP đơn giản: client gửi tên người dùng và mật khẩu dưới dạng một giá trị trong header **Authorization**. Server giải mã cách biểu diễn, kiểm tra credentials bằng cơ chế xác thực, rồi cho phép hoặc từ chối truy cập theo chính sách bảo mật. Spring Security Servlet hỗ trợ luồng này thông qua các filter và AuthenticationManager, không đòi hỏi chúng ta tự giải mã header tại controller.

Sau bài này, bạn có thể:

1. Đọc đúng cú pháp **Authorization: Basic ...** và biết nội dung Base64 thực sự chứa gì.
2. Phân biệt **Authorization** của request với **WWW-Authenticate** của response.
3. Theo dõi đường đi từ **BasicAuthenticationFilter** tới **AuthenticationManager**, **AuthenticationProvider**, **SecurityContext** rồi **AuthorizationFilter**.
4. Giải thích các status **200, 401, 403** trong HTTP Basic và vì sao sai credentials khác với không đủ quyền.
5. Viết một ứng dụng Spring Boot Java 17+ sử dụng **SecurityFilterChain**, **httpBasic**, **UserDetailsService**, **PasswordEncoder** và các quy tắc URL.
6. Thực hành với **curl**, đọc header thật và kiểm chứng bằng **MockMvc**.
7. Nhận diện các rủi ro: **Base64 không mã hóa bí mật**, phải dùng HTTPS, trình duyệt có thể gửi credentials lại, tránh log header, xử lý proxy/charset/CSRF đúng nhu cầu.

**Phạm vi:** Spring Security trên **Servlet stack**, ví dụ Spring MVC. Đây là bài về cách hoạt động của HTTP Basic và header Authorization, không phải hướng dẫn tự xây OAuth2, JWT hay một giao thức đăng nhập mới.

## 2. Bức tranh tổng thể: client, HTTP header, Servlet filters

Khi client gọi endpoint bảo vệ bằng HTTP Basic, luồng khái niệm là:

~~~text
Client                                   Server (Spring Security Servlet)
  |                                                |
  |  GET /me HTTP/1.1                              |
  |  Authorization: Basic <base64-user-colon-pass>  |
  |----------------------------------------------->|
  |                                                |
  |                  DelegatingFilterProxy         |
  |                         |                      |
  |                  FilterChainProxy              |
  |                         |                      |
  |                 SecurityFilterChain            |
  |                         |                      |
  |              BasicAuthenticationFilter         |
  |                đọc Authorization               |
  |                         |                      |
  |                  AuthenticationManager         |
  |                         |                      |
  |                  AuthenticationProvider        |
  |                         |                      |
  |           UserDetailsService + PasswordEncoder |
  |                         |                      |
  |              Authentication thành công?        |
  |                   /              \             |
  |                 Có               Không         |
  |                 |                  |           |
  |        đặt SecurityContext       401           |
  |                 |                              |
  |          AuthorizationFilter                   |
  |                 |                              |
  |          đúng quyền URL?                       |
  |           /          \                         |
  |         Có           Không                     |
  |         |               |                      |
  |      Controller        403                     |
  |         |                                      |
  |<--------+---- HTTP 200 / response -------------|
~~~

Sơ đồ thể hiện các vai trò, không phải danh sách đầy đủ từng filter trong mọi SecurityFilterChain. Những filter xử lý SecurityContext, CSRF, exception, anonymous và authorization có thể tham gia ở các giai đoạn khác nhau.

**Authentication** hỏi: “Người gửi request là ai, đã chứng minh danh tính chưa?”. **Authorization** hỏi: “Danh tính đã xác thực đó có được phép dùng tài nguyên này không?”. HTTP Basic chủ yếu là cách **đưa credentials cho bước authentication**, không thay thế cấu hình authorization.

## 3. Cú pháp của header Authorization

Theo HTTP Basic (RFC 7617), client gửi:

~~~http
GET /me HTTP/1.1
Host: example.test
Authorization: Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ==
~~~

Giá trị sau chữ **Basic** là Base64 của chuỗi:

~~~text
Aladdin:open sesame
~~~

Đây là cặp credentials mẫu để giải thích định dạng. Chúng **không** thuộc những user được cấu hình trong dự án Spring Boot ở phần thực hành.

Cấu trúc tổng quát:

~~~text
Authorization: Basic <base64(username:password)>
               |     |
               |     +-- chuỗi Base64 của user-id + dấu : + password
               +-------- authentication scheme
~~~

**Những điểm chính:**

- Tên header đúng là **Authorization**, không phải Authentication và cũng không phải Proxy-Authorization.
- Scheme là **Basic**; theo quy tắc HTTP, tên scheme không phân biệt hoa/thường, dù thường viết đúng dạng Basic.
- **Dấu hai chấm đầu tiên** phân tách user-id và password trước khi Base64. Vì vậy user-id trong định dạng này không chứa dấu hai chấm; password có thể có dấu hai chấm.
- Có dấu cách giữa **Basic** và chuỗi credentials đã biểu diễn.
- Base64 chỉ là **encoding**, có thể đảo ngược về byte ban đầu; không có thuật toán mã hóa bí mật hay chữ ký bảo vệ chuỗi này.
- Header được gửi trong mỗi request mà client muốn xác thực theo Basic; có thể gửi chủ động hoặc sau khi server trả challenge.
- Với ký tự ngoài ASCII, charset giữa client và server phải thống nhất. RFC 7617 có tham số **charset="UTF-8"** trên challenge trong các trường hợp hỗ trợ; không giả định mọi client/server lịch sử đều diễn giải byte giống nhau.

**Base64 tuyệt đối không thay cho TLS.** Nếu request chạy qua HTTP không mã hóa, kẻ quan sát đường truyền có thể lấy và giải mã credentials. Dùng **HTTPS** và bảo đảm TLS bao phủ cả đường đi qua proxy/load balancer tới thành phần tin cậy thích hợp.

### Base64 có “mã hóa password” không?

Không. Ví dụ nếu một người xem được:

~~~text
Authorization: Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ==
~~~

thì họ có thể giải Base64 để nhận lại chính **Aladdin:open sesame**. Do đó:

- Không chụp hoặc ghi nguyên header Authorization vào log, trace, analytics và exception.
- Không gửi header sang dịch vụ phụ không cần thiết.
- Không coi cặp Basic credentials giống một access token có scope/expiry độc lập.
- Không đưa raw credentials vào URL query string vì URL có thể bị lưu ở lịch sử, log hoặc Referer.
- Nếu buộc phải dùng Basic với thông tin đăng nhập thực, nên có cơ chế thay đổi/thu hồi credential, rate limiting và phát hiện brute force.

## 4. Authorization của request khác WWW-Authenticate của response

Hai header phục vụ hai hướng giao tiếp khác nhau.

| Header | Bên gửi | Mục đích |
| --- | --- | --- |
| **Authorization: Basic ...** | Client → server | Gửi credentials để thử xác thực cho request |
| **WWW-Authenticate: Basic realm="..."** | Server → client | Thông báo cơ chế xác thực được hỗ trợ/yêu cầu trong một challenge |
| **Proxy-Authorization** | Client → proxy | Credentials dành cho proxy; không thay thế Authorization tới origin server |
| **Proxy-Authenticate** | Proxy → client | Challenge từ proxy, thường liên quan HTTP 407 |

Ví dụ, khi chưa có credentials và endpoint yêu cầu đăng nhập:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
~~~

**Realm** là nhãn của vùng bảo vệ để user agent biết khu vực xác thực; realm không phải password hash, JWT scope hoặc session ID. Trong Spring Security, giá trị realm có thể tùy cấu hình. Đừng cố dựa vào đúng chuỗi "Realm" trong mọi ứng dụng.

Client có thể:

1. Gửi GET /me mà không có Authorization.
2. Nhận 401 cùng challenge WWW-Authenticate: Basic.
3. Yêu cầu người dùng nhập username/password hoặc dùng thông tin đã lưu.
4. Gửi lại GET /me với Authorization: Basic ...
5. Nhận 200 nếu credentials hợp lệ **và** user đủ quyền.

Nhiều HTTP client, bao gồm curl khi dùng tùy chọn **-u**, có thể **gửi Basic ngay trong request đầu** mà không cần chờ 401. Đó là lý do bạn thường thấy header Authorization xuất hiện ngay khi gọi API lần đầu.

**401 Unauthorized** theo tên trạng thái HTTP không chỉ nghĩa “thiếu quyền”; trong ngữ cảnh này nó chủ yếu thông báo cần hoặc chưa hoàn thành xác thực. **403 Forbidden** nghĩa là server đã hiểu request nhưng **từ chối quyền thực hiện**, điển hình khi user đã xác thực nhưng thiếu authority.

## 5. Spring Security xử lý Authorization: Basic ở đâu?

Các thành phần chính của luồng Servlet:

| Thành phần | Trách nhiệm |
| --- | --- |
| **FilterChainProxy** | Chọn SecurityFilterChain đầu tiên có matcher phù hợp với request |
| **BasicAuthenticationFilter** | Nhận dạng HTTP Basic, chuyển credentials thành yêu cầu xác thực |
| **BasicAuthenticationConverter** | Parse/giải biểu diễn của Basic credentials khi filter sử dụng converter |
| **AuthenticationManager** | Điều phối quá trình xác thực, thường do ProviderManager triển khai |
| **DaoAuthenticationProvider** | Xác thực username/password với UserDetailsService và PasswordEncoder |
| **UserDetailsService** | Tải username, hash mật khẩu, trạng thái tài khoản, authorities |
| **PasswordEncoder** | So sánh raw password với hash lưu bằng matches(...) |
| **SecurityContextHolder** | Cung cấp Authentication của quá trình xử lý hiện tại |
| **AuthorizationFilter** | Kiểm tra request có đủ quyền theo các rule authorizeHttpRequests hay không |
| **BasicAuthenticationEntryPoint** | Trả HTTP 401 và WWW-Authenticate: Basic khi cần challenge |
| **ExceptionTranslationFilter** | Chuyển một số lỗi authentication/authorization phía sau thành phản hồi phù hợp qua entry point/access denied handler |

**BasicAuthenticationFilter** không nên được nhầm với việc định nghĩa người dùng. Filter chỉ xử lý cơ chế HTTP Basic; nó không tự tạo tài khoản, không tự truy vấn database nếu không có AuthenticationProvider/UserDetailsService phù hợp.

### 5.1. Request có Basic credentials hợp lệ

~~~text
Authorization: Basic <credentials>
           |
BasicAuthenticationFilter
           |
BasicAuthenticationConverter -> username + raw password
           |
UsernamePasswordAuthenticationToken (chưa authenticated)
           |
AuthenticationManager.authenticate(...)
           |
DaoAuthenticationProvider
           |
UserDetailsService.loadUserByUsername(...)
           |
PasswordEncoder.matches(raw, storedHash)
           |
Authentication thành công
           |
SecurityContextHolder chứa Authentication
           |
AuthorizationFilter kiểm tra role/authority
           |
Controller
~~~

Trong luồng thông thường, credentials của kết quả Authentication có thể bị **erase** sau xác thực, để giảm thời gian tồn tại của mật khẩu thô trong object kết quả. Không dùng Authentication.getCredentials() ở controller để lấy lại password vì giá trị này có thể đã là null.

### 5.2. Request có Basic credentials sai

~~~text
Authorization: Basic <invalid-password>
           |
BasicAuthenticationFilter
           |
AuthenticationManager -> xác thực thất bại
           |
Xóa/dọn ngữ cảnh phù hợp, gọi entry point
           |
HTTP 401 + challenge WWW-Authenticate (theo cấu hình)
~~~

Nếu filter xử lý lỗi và kết thúc response, các filter phía sau có thể **không** chạy và controller không được gọi.

### 5.3. Không có Authorization trên URL cần xác thực

Khi request không có Basic credentials, BasicAuthenticationFilter thường không thể xác thực user và chuyển tiếp chain. Đến bước authorization, URL bảo vệ không được phép cho anonymous, nên exception handling sẽ trả một challenge xác thực, thường là **401** trong cấu hình chỉ dùng HTTP Basic.

Điểm khác với mật khẩu sai: request thiếu header **không phải** là lỗi parse Basic credentials; nó chỉ chưa có danh tính thỏa rule. Cả hai có thể nhận 401 ở endpoint được bảo vệ nhưng xuất phát từ những nhánh xử lý khác nhau.

### 5.4. Đã đăng nhập nhưng không có role

Một user có **ROLE_USER**, trong khi /admin đòi **ROLE_ADMIN**:

~~~text
Authorization: Basic <valid-user-credentials>
            |
Authentication thành công -> user có ROLE_USER
            |
AuthorizationFilter kiểm tra hasRole("ADMIN")
            |
Không đủ role -> 403 Forbidden
~~~

**hasRole("ADMIN")** theo cấu hình mặc định tìm authority **ROLE_ADMIN**; không dùng hasRole("ROLE_ADMIN") để thêm tiền tố hai lần. Tên role được gán ở UserDetailsService bởi roles("ADMIN") trong ví dụ.

## 6. HTTP Basic có tạo session không?

**HTTP Basic là scheme gửi username/password trong request**, không phải định nghĩa rằng server luôn stateless. Cơ chế này có thể chạy cùng session nếu ứng dụng cấu hình session; không được kết luận rằng chỉ cần gọi httpBasic() là mọi thứ tự động stateless.

Trong demo ta đặt:

~~~java
http.sessionManagement(session ->
    session.sessionCreationPolicy(SessionCreationPolicy.STATELESS));
~~~

Điều đó yêu cầu Spring Security không dùng HttpSession để nạp SecurityContext qua request. Mỗi request bảo vệ cần cung cấp chứng cứ xác thực thích hợp, ví dụ Basic credentials. Spring Security có thể tạo Authentication mới cho request sau, nhưng không hồi sinh login chỉ vì HTTP Basic đã thành công ở request trước.

**Về mặt client**, trình duyệt có thể ghi nhớ credentials Basic và tự gửi Authorization header ở request tiếp theo. Vì vậy người dùng có cảm giác “vẫn đăng nhập” dù server không dùng session. Đây là việc **client gửi lại credentials**, khác với việc server khôi phục Authentication từ một session cookie.

**Logout cho HTTP Basic không giống form login.** Server có thể trả 401 hoặc từ chối credentials, nhưng không luôn có cách tiêu chuẩn buộc mọi browser xóa credentials Basic đã nhớ. Nếu cần trải nghiệm logout/session rõ ràng, cân nhắc cơ chế đăng nhập khác phù hợp hơn.

## 7. Ví dụ Spring Boot hoàn chỉnh: HTTP Basic và Authorization header

Ứng dụng sẽ có:

- GET **/public** không cần xác thực.
- GET **/me** yêu cầu bất kỳ user đã xác thực.
- GET **/admin** yêu cầu ROLE_ADMIN.
- User **learner / learner-pass** có ROLE_USER.
- User **admin / admin-pass** có ROLE_ADMIN.

Các mật khẩu và tài khoản này chỉ phục vụ thử nghiệm local. Không triển khai mật khẩu hardcoded ra production và **không** thử credential demo trên hệ thống thật.

### 7.1. Công nghệ và cấu trúc dự án

Sử dụng **Java 17+**, **Maven**, **Spring Boot 3.3.13**, **Spring Security 6**.

~~~text
basic-auth-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/basicdemo/
    │   ├── BasicDemoApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/com/example/basicdemo/
        └── BasicAuthenticationFlowTest.java
~~~

Không cần viết BasicAuthenticationFilter tùy biến để chạy demo: **httpBasic(Customizer.withDefaults())** sử dụng cơ chế chuẩn của Spring Security.

### 7.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>basic-auth-demo</artifactId>
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

Spring Boot starter parent quản lý phiên bản tương thích của Spring Framework và Spring Security. Không cần gắn phiên bản Spring Security bằng tay cho các starter.

### 7.3. BasicDemoApplication.java

~~~java
package com.example.basicdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BasicDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(BasicDemoApplication.class, args);
    }
}
~~~

File là entry point Spring Boot. Vì các lớp cùng package **com.example.basicdemo**, cấu hình bean và controller được component scan tự nhận.

### 7.4. SecurityConfig.java

~~~java
package com.example.basicdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
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
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("learner-pass"))
            .roles("USER")
            .build();

        UserDetails administrator = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(learner, administrator);
    }
}
~~~

**Giải thích từng khối:**

1. **SecurityFilterChain** thay cho cách cấu hình cũ bằng WebSecurityConfigurerAdapter trong Spring Security 6.
2. **sessionCreationPolicy(STATELESS)** làm demo độc lập từng request; không dùng session để lưu Authentication qua nhiều lần GET.
3. **requestMatchers(HttpMethod.GET, ...)** chỉ ra đúng method và path. Các request không nằm trong những route này bị denyAll; không mặc nhiên cho phép mọi POST/PUT.
4. **authenticated()** yêu cầu danh tính hợp lệ. **hasRole("ADMIN")** yêu cầu authority ROLE_ADMIN.
5. **httpBasic(Customizer.withDefaults())** bật cơ chế Basic và entry point chuẩn; ứng dụng không phải tự đọc header Authorization.
6. **formLogin(AbstractHttpConfigurer::disable)** tắt redirect tới trang login dạng HTML để các lời gọi curl thiếu thông tin đăng nhập nhận challenge Basic.
7. **PasswordEncoder** tạo hash BCrypt cho user mẫu; mỗi lần khởi động có thể tạo chuỗi hash khác nhau do salt.
8. **InMemoryUserDetailsManager** phục vụ demo cục bộ, không phải hệ thống quản lý người dùng production.

**CSRF không bị tắt.** Ví dụ chỉ sử dụng GET nên không cần CSRF token. Nếu thêm endpoint thay đổi dữ liệu, hãy đánh giá CSRF theo cách browser/client gửi credentials: browser có thể nhớ và gửi HTTP Basic tự động. Không kết luận STATELESS hoặc HTTP Basic tự động loại bỏ rủi ro CSRF.

### 7.5. DemoController.java

~~~java
package com.example.basicdemo;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public Map<String, String> publicEndpoint() {
        return Map.of("message", "public-ok");
    }

    @GetMapping("/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @GetMapping("/admin")
    public Map<String, String> admin() {
        return Map.of("message", "admin-ok");
    }
}
~~~

Tham số **Authentication** trong /me do Spring Security cung cấp khi request đã xác thực. Controller không nhận raw password, không đọc Authorization header và không thực hiện lại PasswordEncoder.matches. Đây là tách biệt trách nhiệm: filter/provider xác thực trước, controller chỉ xử lý request được phép.

## 8. Chạy ứng dụng và gọi curl

Từ thư mục chứa pom.xml:

~~~bash
mvn spring-boot:run
~~~

Maven cần có JDK 17+ và kết nối để tải dependency khi chưa có cache. Khi application khởi động thành công, ứng dụng lắng nghe mặc định trên **http://localhost:8080** trong cấu hình local.

**Lưu ý về mật khẩu trong dòng lệnh:** cú pháp curl -u trong ví dụ chứa thông tin mẫu công khai. Với secrets thật, tránh đưa trực tiếp mật khẩu vào command history, process listings hay script được lưu; chọn cách cung cấp bí mật an toàn phù hợp hệ điều hành và công cụ.

### 8.1. Endpoint công khai, không header Authorization

~~~bash
curl -i http://localhost:8080/public
~~~

Các thành phần phản hồi cần quan sát:

~~~http
HTTP/1.1 200
Content-Type: application/json

{"message":"public-ok"}
~~~

Các header khác và thứ tự header có thể do server/framework tự thêm. Điều quan trọng là status **200** và nội dung JSON công khai.

### 8.2. Endpoint /me thiếu Authorization

~~~bash
curl -i http://localhost:8080/me
~~~

Kết quả trọng tâm:

~~~http
HTTP/1.1 401
WWW-Authenticate: Basic realm="Realm"
~~~

Vì không có thông tin xác thực và /me yêu cầu authenticated(), server gửi challenge Basic. Tên realm phụ thuộc cấu hình; với cấu hình mặc định này thường là Realm.

### 8.3. Endpoint /me với Basic credentials hợp lệ

~~~bash
curl -i -u learner:learner-pass http://localhost:8080/me
~~~

Kết quả trọng tâm:

~~~http
HTTP/1.1 200
Content-Type: application/json

{"username":"learner"}
~~~

Tùy chọn **-u username:password** khiến curl tạo Authorization: Basic với chuỗi Base64 tương ứng. Spring Security kiểm tra mật khẩu bằng BCrypt hash trong UserDetailsService. Sau đó /me được phép gọi.

### 8.4. Mật khẩu sai

~~~bash
curl -i -u learner:wrong-pass http://localhost:8080/me
~~~

Dự kiến **401 Unauthorized**, không chạy controller /me. Trường hợp này khác request không có credentials về đường đi bên trong filter, nhưng cùng thất bại ở bước đạt điều kiện authentication.

### 8.5. Đã xác thực nhưng thiếu quyền ADMIN

~~~bash
curl -i -u learner:learner-pass http://localhost:8080/admin
~~~

Dự kiến **403 Forbidden**: learner có ROLE_USER và mật khẩu đúng nhưng không có ROLE_ADMIN. Đừng báo “đăng nhập sai” cho tình huống này; vấn đề là **authorization**, không phải credential validity.

### 8.6. Admin truy cập đúng quyền

~~~bash
curl -i -u admin:admin-pass http://localhost:8080/admin
~~~

Kết quả trọng tâm:

~~~http
HTTP/1.1 200
Content-Type: application/json

{"message":"admin-ok"}
~~~

### 8.7. Trường hợp Authorization header thuộc scheme khác

Nếu client gửi **Authorization: Bearer ...** trong cấu hình demo chỉ bật HTTP Basic, bearer token không được filter Basic xác thực như username/password. Trên URL /me, nếu không có cơ chế khác xác thực request, kết quả vẫn không đạt authenticated() và sẽ bị challenge.

Đừng đổi một scheme sang scheme khác bằng cách thay tên prefix rồi kỳ vọng server tự hiểu: **Basic** và **Bearer** là hai giao thức có ngữ nghĩa, credentials và cách kiểm tra khác nhau.

Bảng kiểm chứng:

| Request | Credentials/role | Status dự kiến | Ý nghĩa |
| --- | --- | --- | --- |
| GET /public | Không Authorization | 200 | URL public |
| GET /me | Không Authorization | 401 | Chưa xác thực, có Basic challenge |
| GET /me | learner đúng mật khẩu | 200 | Xác thực hợp lệ |
| GET /me | learner sai mật khẩu | 401 | Sai credentials |
| GET /admin | learner đúng mật khẩu, ROLE_USER | 403 | Đã xác thực nhưng thiếu role |
| GET /admin | admin đúng mật khẩu, ROLE_ADMIN | 200 | Đủ quyền |

**Không dựa vào body hoặc bộ header cụ thể của trang lỗi** như một hợp đồng bất biến, trừ khi bạn đã cấu hình và kiểm thử handler riêng. Status và nội dung WWW-Authenticate của challenge là điểm cốt lõi cho bài này.

## 9. Kiểm thử MockMvc: chứng minh luồng Basic và challenge

Tạo **src/test/java/com/example/basicdemo/BasicAuthenticationFlowTest.java**:

~~~java
package com.example.basicdemo;

import static org.hamcrest.Matchers.startsWith;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class BasicAuthenticationFlowTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointNeedsNoAuthorizationHeader() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public-ok"));
    }

    @Test
    void protectedEndpointReturnsBasicChallengeWhenMissingCredentials()
            throws Exception {

        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "WWW-Authenticate", startsWith("Basic")));
    }

    @Test
    void validBasicCredentialsAuthenticateRequest() throws Exception {
        mvc.perform(get("/me").with(
                httpBasic("learner", "learner-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("learner"));
    }

    @Test
    void invalidBasicCredentialsAreRejected() throws Exception {
        mvc.perform(get("/me").with(
                httpBasic("learner", "wrong-pass")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedUserWithoutRequiredRoleReceivesForbidden()
            throws Exception {

        mvc.perform(get("/admin").with(
                httpBasic("learner", "learner-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void administratorWithCorrectRoleCanAccessAdmin() throws Exception {
        mvc.perform(get("/admin").with(
                httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("admin-ok"));
    }
}
~~~

Chạy từ thư mục gốc:

~~~bash
mvn test
~~~

**Kiểm tra chính:**

- Endpoint công khai trả 200 không cần header.
- Endpoint bảo vệ thiếu credentials trả 401 với **WWW-Authenticate** bắt đầu bằng **Basic**.
- Basic username/password hợp lệ giúp /me trả danh tính.
- Password sai trả 401.
- Đăng nhập đúng nhưng thiếu role trả 403.
- Đủ role trả 200.

MockMvc không cần một server HTTP thực đang chạy ở cổng 8080; nó mô phỏng request đi qua Spring MVC và filter chain được tích hợp trong ngữ cảnh test. **httpBasic(...)** từ spring-security-test giúp tạo header Authorization theo định dạng Basic, không cần tự tính Base64. Các kiểm thử không giả định mật khẩu đã được giữ trong session.

## 10. Tự tạo header Authorization để hiểu định dạng

**Không cần** tự viết logic Base64 trong controller. Tuy nhiên, để hiểu giao thức, bạn có thể sử dụng đoạn Java độc lập sau.

Tạo tệp **BasicHeaderDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class BasicHeaderDemo {

    public static void main(String[] args) {
        String username = "Aladdin";
        String password = "open sesame";

        String userPass = username + ":" + password;
        String token = Base64.getEncoder().encodeToString(
            userPass.getBytes(StandardCharsets.UTF_8));

        System.out.println("Authorization: Basic " + token);

        String decoded = new String(
            Base64.getDecoder().decode(token),
            StandardCharsets.UTF_8);

        System.out.println("Decoded example: " + decoded);
    }
}
~~~

Lệnh biên dịch và chạy độc lập với Spring Boot:

~~~bash
javac BasicHeaderDemo.java
java BasicHeaderDemo
~~~

Stdout chính xác:

~~~text
Authorization: Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ==
Decoded example: Aladdin:open sesame
~~~

Ví dụ này **cố ý in credentials mẫu** để chứng minh Base64 đảo ngược được. Không dùng lệnh in decoded credentials này với tài khoản thật. Nếu hệ thống có ký tự non-ASCII, phải thống nhất charset; chương trình minh họa cố ý dùng ASCII nên kết quả Base64 là xác định.

**Điểm mấu chốt:** bất kỳ ai lấy được header cũng có thể thực hiện phép decode tương tự; Base64 **không** bảo mật thông tin đăng nhập.

## 11. Khi nào BasicAuthenticationFilter chạy và không chạy?

**Có header Authorization với scheme Basic hợp lệ về định dạng:** filter parse username/password và yêu cầu AuthenticationManager kiểm tra. Nếu thành công, nó thiết lập Authentication trong SecurityContext phù hợp. Nếu thất bại, quá trình trả challenge có thể kết thúc chain.

**Không có header Authorization:** Basic filter thường chuyển tiếp, không tự tạo Authentication từ không khí. Một filter khác hoặc session policy có thể cung cấp context nếu ứng dụng cấu hình như vậy; trong demo stateless và chỉ bật Basic, /me thiếu header bị 401.

**Authorization có scheme khác Basic:** BasicAuthenticationFilter không biến bearer token thành password. Phải cấu hình cơ chế xác thực khác nếu muốn chấp nhận scheme đó.

**Header bị hỏng (không phải Base64 hợp lệ, thiếu dấu phân cách, định dạng lạ):** converter/filter có thể từ chối yêu cầu xác thực; status và body cuối cùng phụ thuộc cấu hình exception/entry point. Không tự cho header “có chữ Basic” là đủ.

**Đường dẫn public vẫn có header sai:** dù /public có permitAll, nếu client chủ động gửi Basic credentials không hợp lệ, filter xác thực có thể từ chối trước khi đến controller. Vì vậy **permitAll không có nghĩa filter trước đó bỏ qua mọi lỗi header Basic**. Khi thử endpoint công khai, hãy gửi request không có Authorization để không nhầm kết quả.

**Nhiều SecurityFilterChain:** mỗi request chỉ được xử lý bởi chain đầu tiên khớp matcher. Nếu một chain cho /api/** không bật httpBasic còn một chain khác có bật, hành vi challenge có thể khác tùy URL. Không suy ra mọi URL của server đều có chung authentication scheme.

## 12. Các mã lỗi và cách hiểu trong ứng dụng thật

| HTTP code | Tình huống thường thấy | Người phát triển nên kiểm tra |
| --- | --- | --- |
| **200 OK** | Request thành công, đủ quyền | Controller đã được gọi; không có nghĩa dữ liệu trong body tự động an toàn |
| **401 Unauthorized** | Thiếu credentials, sai password, credentials không hợp lệ hoặc chưa được xác thực | WWW-Authenticate, cấu hình authentication/entry point, thông tin client gửi |
| **403 Forbidden** | Authentication hợp lệ nhưng thiếu role, hoặc yêu cầu bị chính sách khác từ chối | Authorities, authorizeHttpRequests, CSRF, method security |
| **407 Proxy Authentication Required** | Proxy yêu cầu xác thực riêng | Proxy-Authenticate/Proxy-Authorization, không nhầm với Basic của origin |
| **302 Found** | Có thể xuất hiện khi ứng dụng bật form login/redirect thay vì chỉ Basic | Kiểm tra các entry point và Accept header |

**403 không luôn chứng minh username/password đúng.** Ví dụ, một POST thiếu CSRF token có thể trả 403 dù chưa qua xác thực thành công; handler tùy biến cũng có thể trả 403. Muốn phân tích lỗi thực tế, cần đọc cấu hình filter và request cụ thể.

Với HTTP Basic API, một thiết kế rõ ràng là: **401** khi chưa xác thực và có challenge; **403** khi xác thực hợp lệ nhưng rule từ chối. Tuy nhiên chính sách của nhiều security chain hoặc cơ chế lỗi tùy biến có thể thay đổi hành vi.

**Không trả thông báo lỗi quá chi tiết** phân biệt username tồn tại hay không, hoặc cho biết tài khoản nào hợp lệ để hỗ trợ attacker dò tài khoản. Audit nội bộ có thể lưu loại lỗi ở mức phù hợp và được bảo vệ.

## 13. HTTPS, trình duyệt, CSRF và proxy

### 13.1. HTTPS là yêu cầu căn bản

Authorization: Basic chứa username/password ở dạng Base64 có thể giải mã. Nếu dùng HTTP plaintext, thông tin có thể bị đọc, sao chép hoặc thay đổi trên đường truyền. Production cần HTTPS với cấu hình TLS phù hợp, quản lý chứng chỉ và xử lý reverse proxy đúng cách.

Dùng **http://localhost:8080** trong ví dụ chỉ để thử cục bộ. Không mở cổng HTTP Basic chứa tài khoản thật ra Internet.

### 13.2. Browser có thể tự gửi lại credentials

Một số browser cache Basic credentials theo vùng bảo vệ và tự động gửi lại trên các request sau. Do đó, ngay cả khi server stateless, credentials vẫn có thể được trình duyệt gửi mỗi lần. Điều này ảnh hưởng UX/logout và bề mặt CSRF.

Đừng xem Basic là lựa chọn mặc định cho ứng dụng web tương tác có yêu cầu đăng nhập/đăng xuất tinh vi. Form login/session hoặc cơ chế federated auth có thể phù hợp hơn tùy hệ thống.

### 13.3. CSRF vẫn có thể liên quan

Một browser có thể tự gửi credentials Basic đã nhớ trong hoàn cảnh thích hợp, tương tự cách nó tự đính kèm cookie. Khi xây endpoint đổi trạng thái, không tự động bỏ CSRF protection chỉ vì đang dùng HTTP Basic hoặc SessionCreationPolicy.STATELESS.

Phân tích CSRF phải xét threat model: loại client, credentials có tự được gửi không, chính sách cookie/origin/CORS và các method HTTP. Với API chỉ có machine-to-machine client kiểm soát header rõ ràng, thiết kế có thể khác browser app; phải có lý do và test tương ứng.

### 13.4. Reverse proxy/load balancer

Đôi khi browser gửi Authorization đúng nhưng đến ứng dụng lại thiếu. Nguyên nhân có thể là gateway không forward header hoặc biến đổi request. Cần cấu hình proxy truyền header cần thiết qua các trust boundary phù hợp và bảo đảm không ghi raw credentials vào access log.

**Đừng log toàn bộ request headers** để debug 401 trong production. Nếu cần quan sát, ghi trạng thái khái quát như “Authorization header present / scheme Basic”, thời điểm, request ID và outcome; che hoàn toàn giá trị header.

### 13.5. CORS và request tiền kiểm

CORS của browser là chính sách khác với HTTP Basic. Một preflight OPTIONS có thể bị rule bảo mật từ chối nếu không cấu hình CORS phù hợp. Khi dùng frontend khác origin, hãy cấu hình CORS theo origin/method/header được phép và kiểm chứng OPTIONS; **không** giải quyết bằng cách cho phép tất cả origin cùng credentials bừa bãi.

### 13.6. Credential charset và dấu hai chấm

RFC 7617 dùng định dạng user-id + ":" + password trước khi tạo Base64. Username chứa dấu hai chấm không biểu diễn rõ ràng theo Basic; còn password có thể chứa dấu hai chấm. Với username/password Unicode, client và server cần đồng nhất charset; ưu tiên quy tắc/khai báo rõ ràng, không tự đoán từ kết quả thử ASCII.

## 14. Lỗi thường gặp khi tích hợp HTTP Basic

### Lỗi 1 — Nghĩ Basic đã mã hóa password

Sai. Basic chuyển raw username/password thành Base64, không phải encryption. Dùng HTTPS và bảo vệ Authorization header ở log/proxy.

### Lỗi 2 — Gửi sai tên header

Sai: Authentication: Basic ... hoặc Token: Basic ... rồi chờ Spring Security tự hiểu. Đúng là **Authorization: Basic ...**.

### Lỗi 3 — Header không có tiền tố Basic

Gửi một chuỗi Base64 đơn lẻ trong Authorization không giống đúng scheme Basic. Phải có scheme và dấu cách, đồng thời nội dung Base64 phải decode được thành username:password.

### Lỗi 4 — Lấy Authorization: Bearer làm Basic

Bearer token không phải Base64 của username:password theo Basic. Nếu muốn Bearer, phải bật cơ chế resource server/token authentication riêng; không sửa tiền tố bằng cách nối chuỗi.

### Lỗi 5 — So sánh password trực tiếp với BCrypt hash

Sai. UserDetails chứa hash, không chứa raw password. PasswordEncoder.matches(raw, storedHash) là cách kiểm chứng; đừng dùng equals giữa raw và hash.

### Lỗi 6 — Hiểu nhầm 401 và 403

401 thường là thiếu/sai authentication; 403 có thể là đủ danh tính nhưng thiếu role hoặc bị policy như CSRF từ chối. Kiểm tra SecurityContext, rule và exception handling thay vì đổi status thủ công để che lỗi.

### Lỗi 7 — Bật cả formLogin và httpBasic mà không biết entry point nào đáp ứng

Khi cả hai cơ chế được bật, ứng dụng có thể redirect HTML client và challenge API client theo matcher/Accept header. Nếu mục tiêu là API Basic thuần, cấu hình rõ và test status/WWW-Authenticate.

### Lỗi 8 — Tin rằng STATELESS làm client quên credentials

STATELESS chủ yếu nói về cách Spring Security dùng session. Browser hoặc client vẫn có thể lưu và gửi lại Authorization. Logout Basic không đơn giản là invalidate HttpSession.

### Lỗi 9 — Mọi request public đều luôn trả 200 dù có Basic header sai

Filter xác thực có thể xử lý Authorization sai trước khi đến rule permitAll. Thử public endpoint không có header khi muốn xác minh permitAll.

### Lỗi 10 — Quên chain.doFilter khi viết filter bổ sung

Một custom Servlet/Security filter nếu chặn chain không đúng sẽ làm BasicAuthenticationFilter hoặc AuthorizationFilter không chạy như dự kiến. Trước khi tự viết filter, ưu tiên các extension point chuẩn của Spring Security và định nghĩa thứ tự rõ ràng.

### Lỗi 11 — Log/capture request có password thật

Raw Authorization header là một bí mật. Dùng dữ liệu test và công cụ redaction; giới hạn người có quyền đọc trace/heap dump và session recordings. Không gửi bản chụp request có credentials thật vào issue tracker.

### Lỗi 12 — Kỳ vọng HTTP Basic tự quản lý tài khoản và phân quyền

HTTP Basic chỉ là scheme chuyển credentials. UserDetailsService, PasswordEncoder, AuthenticationProvider, authorities và các rule authorizeHttpRequests mới quyết định xác thực và quyền truy cập.

## 15. Chẩn đoán lỗi theo từng bước

Nếu client nhận 401/403 không như mong đợi, kiểm tra theo thứ tự:

1. **URL, method, scheme:** request đi đến đúng HTTP path, HTTPS/TLS và đúng method?
2. **SecurityFilterChain:** có nhiều chain? Chain đầu tiên khớp có bật httpBasic không?
3. **Authorization header:** có mặt ở request tới server không? Scheme có phải Basic không? Proxy có forward không? Kiểm tra sự hiện diện, không log giá trị raw.
4. **Encoding:** giá trị Basic có được tạo từ username + ":" + password trước Base64? Có sai charset hoặc ký tự dấu hai chấm trong username?
5. **UserDetailsService:** username có tồn tại không? Account có enabled/locked/expired phù hợp không?
6. **PasswordEncoder:** hash lưu thuộc đúng định dạng encoder hay không? Password có đúng không?
7. **AuthenticationManager:** provider có được cấu hình và có thể xác thực UsernamePasswordAuthenticationToken không?
8. **SecurityContext:** filter có tạo Authentication thành công cho request này không? Có custom filter nào xóa/thay context sai thời điểm?
9. **Authorization rules:** endpoint dùng authenticated(), hasRole(), hasAuthority() nào? ROLE_ prefix có khớp không?
10. **Exception/entry point:** 401 có WWW-Authenticate đúng không? Có login form/handler khác can thiệp?
11. **CSRF/CORS:** với POST/OPTIONS có bị chính sách độc lập từ chối không?
12. **Client:** browser có cache Basic credentials sai hoặc gửi header cũ không? Dùng curl/new client độc lập để loại trừ.
13. **Quan sát an toàn:** log filter chain ở mức phù hợp, metrics 401/403 và request ID; không log passwords, encoded Authorization hay token.

**Khi debug, đừng tắt authentication/authorization toàn bộ để “cho request chạy”**. Thay vào đó, tái hiện request bằng dữ liệu test, tìm bước chuyển trạng thái chính xác và sửa cấu hình cần thiết.

## 16. Bài tập thực hành

### Bài A — Decode đúng header

Header Authorization: Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ== tương ứng với cặp username/password nào? Có được coi là “mật khẩu đã được mã hóa an toàn” không?

**Đáp án:** Aladdin và open sesame; Base64 có thể đảo ngược và không phải encryption bảo vệ bí mật.

### Bài B — Phân biệt 401 và 403

Client gửi learner/learner-pass tới GET /admin và nhận 403. Tại sao không phải 401?

**Đáp án:** credentials đúng, Authentication thành công, nhưng learner có ROLE_USER và rule cần ROLE_ADMIN. Đây là từ chối quyền, không phải sai mật khẩu.

### Bài C — Không có Authorization

Gọi GET /me mà không gửi header. BasicAuthenticationFilter có tự tạo user mặc định để cấp quyền không? Vì sao trả 401?

**Đáp án:** filter không tự tạo user đã xác thực từ request thiếu credentials; rule authenticated() không được thỏa. Entry point Basic tạo challenge.

### Bài D — Stateless và trình duyệt

Server được cấu hình STATELESS. Một browser vẫn gọi /me thành công ở request thứ hai mà người dùng không nhập lại mật khẩu. Điều đó chứng minh session server đã được dùng chưa?

**Đáp án:** Chưa. Browser có thể tự gửi lại Authorization Basic đã cache. Cần xem request/header và chính sách SecurityContext, không suy từ UI.

### Bài E — Tự sửa config

Đổi rule GET /admin từ hasRole("ADMIN") thành hasAuthority("ROLE_ADMIN"). Hai cách có tương đương với UserDetailsService mẫu không? Nếu đổi thành hasAuthority("ADMIN") thì sao?

**Đáp án:** hasRole("ADMIN") thường kiểm tra ROLE_ADMIN, tương đương hasAuthority("ROLE_ADMIN") với cấu hình default. hasAuthority("ADMIN") kiểm tra authority đúng chuỗi ADMIN nên không khớp user có ROLE_ADMIN.

### Bài F — Tạo Basic header bằng Java

Chạy BasicHeaderDemo.java và đối chiếu output với ví dụ trong phần 3. Thay password bằng một chuỗi có dấu hai chấm, rồi giải Base64 để xem quy tắc tách tại dấu hai chấm **đầu tiên**.

**Gợi ý:** thêm dấu hai chấm trong password vẫn có thể biểu diễn; thêm vào username thì cấu trúc Basic không thể phân định username đúng như mong muốn.

### Bài G — Thử request sai trên URL public

Gọi GET /public không Authorization rồi gọi lại có Basic credentials sai. Giải thích vì sao phản hồi thứ hai có thể khác 200 dù /public được cấu hình permitAll.

**Đáp án:** BasicAuthenticationFilter có thể xử lý lỗi credentials và trả 401 trước khi đến AuthorizationFilter kiểm tra permitAll.

### Bài H — Soạn một ma trận kiểm thử

Đối với /public, /me, /admin và hai tài khoản demo, lập test cho không credentials, sai credentials, learner hợp lệ, admin hợp lệ. Xác nhận 200/401/403 và WWW-Authenticate tương ứng; không suy đoán body lỗi bất biến khi chưa cấu hình handler.

## 17. Checklist trước khi đưa HTTP Basic vào ứng dụng thực

- [ ] Hiểu **Authorization: Basic Base64(username:password)** là cách biểu diễn, không phải mã hóa bảo mật.
- [ ] Đã bật **HTTPS** trên mọi đường truyền chứa credentials; kiểm soát reverse proxy và TLS termination.
- [ ] Không log, ghi trace hoặc trả về raw Authorization header, password hoặc decoded credentials.
- [ ] SecurityFilterChain xác định đúng matcher và bật httpBasic cho những endpoint cần dùng.
- [ ] Đã cấu hình UserDetailsService hoặc AuthenticationProvider phù hợp, sử dụng PasswordEncoder an toàn.
- [ ] Các rule **authenticated/hasRole/hasAuthority** áp đúng method/path, có default deny phù hợp.
- [ ] Phân biệt **401 challenge** với **403 thiếu quyền**, kiểm thử cả trường hợp header không có/sai/hợp lệ.
- [ ] Đã kiểm tra **WWW-Authenticate** và realm được cấu hình đúng.
- [ ] Không suy ra HTTP Basic luôn stateless; nếu cần, cấu hình SessionCreationPolicy rõ ràng.
- [ ] Đã tính đến việc browser nhớ credentials, logout Basic và CSRF đối với endpoint thay đổi trạng thái.
- [ ] CORS/OPTIONS, gateway/proxy forwarding và charset đã được kiểm thử khi có nhu cầu.
- [ ] Có cơ chế rate limiting, audit an toàn và theo dõi brute force/credential stuffing.
- [ ] Không dùng tài khoản/mật khẩu mẫu trong production; quản lý secrets và password rotation/reset an toàn.
- [ ] Trước khi tùy biến filter, đã ưu tiên cơ chế Spring Security tích hợp và kiểm tra đúng filter chain.

**Kết luận:** HTTP Basic dùng header **Authorization: Basic ...** để truyền username/password theo Base64. Trong Spring Security Servlet, **BasicAuthenticationFilter** chuyển credentials thành yêu cầu xác thực, **AuthenticationManager/Provider** kiểm tra mật khẩu, **SecurityContext** giữ kết quả cho request và **AuthorizationFilter** quyết định quyền. **401** thường biểu thị cần xác thực và có **WWW-Authenticate**, còn **403** thường biểu thị không đủ quyền sau xác thực. Vì Base64 không bảo vệ bí mật, **HTTPS, bảo vệ header và cấu hình quyền đúng** là yêu cầu bắt buộc.
