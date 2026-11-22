# Tạo bean SecurityFilterChain và UserDetailsService đầu tiên

## Mục tiêu

Trong ứng dụng Spring Boot chạy **Servlet stack** (thường dùng Spring MVC), hai bean đầu tiên cần nắm khi tự cấu hình Spring Security là **SecurityFilterChain** và **UserDetailsService**.

Sau bài này, bạn có thể:

1. Tạo một bean SecurityFilterChain để xác định HTTP request nào được truy cập công khai, request nào phải đăng nhập và request nào chỉ dành cho quản trị viên.
2. Tạo bean UserDetailsService cung cấp người dùng thử nghiệm trong bộ nhớ, kết hợp PasswordEncoder để kiểm tra mật khẩu.
3. Chạy ví dụ Spring Boot hoàn chỉnh và tự kiểm chứng các phản hồi **200 OK**, **401 Unauthorized**, **403 Forbidden**.
4. Giải thích được đường đi của một HTTP Basic request: SecurityFilterChain → xác thực danh tính → kiểm tra quyền → controller.
5. Biết những giới hạn của cấu hình đầu tiên trước khi triển khai thực tế.

Bài học tập trung vào **cách dựng hai bean đầu tiên và kiểm chứng hoạt động**. Những hệ thống đăng nhập phức tạp như database user store, OAuth2/OIDC, JWT, nhiều security chain, method-level security và phân quyền dữ liệu sẽ cần thêm cấu hình và kiến thức riêng.

## 1. Vì sao cần hai bean khác nhau?

Mỗi bean giải một câu hỏi:

| Bean | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **SecurityFilterChain** | Thiết lập các bộ lọc bảo mật và chính sách áp dụng cho HTTP request | GET /public công khai; GET /profile yêu cầu đăng nhập; GET /admin yêu cầu role ADMIN |
| **UserDetailsService** | Tìm và trả về thông tin người dùng theo username để cơ chế xác thực sử dụng | Tra username student, trả về mật khẩu đã băm và ROLE_USER |

Hãy tưởng tượng một tòa nhà:

- **SecurityFilterChain** giống hệ thống cửa ra vào: quy định cửa nào mở công khai, cửa nào phải xuất trình thẻ, cửa nào yêu cầu quyền quản trị.
- **UserDetailsService** giống nơi tra cứu nhân viên: tìm hồ sơ danh tính từ username. Bản thân nó **không quyết định** người đó được vào cửa nào.
- **PasswordEncoder** kiểm tra mật khẩu ở dạng đã lưu an toàn; cơ chế xác thực sẽ sử dụng nó cùng dữ liệu UserDetailsService.
- **AuthenticationManager/AuthenticationProvider** phối hợp các thành phần để xác thực credentials. Không nên hiểu UserDetailsService tự so mật khẩu hoặc tự cấp quyền HTTP.

**Điểm mấu chốt:** SecurityFilterChain giữ các quy tắc bảo vệ request; UserDetailsService cung cấp dữ liệu để hệ thống xác thực user. Cần cấu hình đúng cả hai để quan sát được đăng nhập và phân quyền.

## 2. Điều kiện chạy và cấu trúc dự án

Ví dụ sử dụng:

- JDK **17 hoặc mới hơn** (tương thích cả JDK 21).
- Spring Boot **3.3.13**, thuộc nhánh dùng Spring Security **6**.
- Maven, ứng dụng Spring MVC/Servlet.
- Hai dependency chính: **spring-boot-starter-web** và **spring-boot-starter-security**.
- Người dùng được lưu **trong bộ nhớ** để tập trung vào hai bean đầu tiên.

Cây thư mục:

~~~text
security-first-beans/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── securitydemo/
                        ├── SecurityDemoApplication.java
                        ├── SecurityConfig.java
                        └── DemoController.java
~~~

Đặt ba lớp Java trong cùng package com.example.securitydemo để @SpringBootApplication tìm thấy @Configuration và @RestController bằng component scan.

### pom.xml

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
    <artifactId>security-first-beans</artifactId>
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

Không phải khai báo trực tiếp version của Spring Security: Spring Boot parent quản lý các phiên bản dependency tương thích. Tránh pha trộn tùy tiện các phiên bản Spring Framework và Spring Security.

### SecurityDemoApplication.java

~~~java
package com.example.securitydemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityDemoApplication.class, args);
    }
}
~~~

Lớp này là điểm khởi động. Khi chạy, Spring tạo ApplicationContext, phát hiện các phương thức @Bean trong SecurityConfig và đăng ký các bean tương ứng.

## 3. Tạo bean SecurityFilterChain đầu tiên

Tạo tệp **src/main/java/com/example/securitydemo/SecurityConfig.java** với nội dung sau:

~~~java
package com.example.securitydemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
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
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
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
    UserDetailsService userDetailsService(PasswordEncoder passwordEncoder) {
        UserDetails student = User.withUsername("student")
            .password(passwordEncoder.encode("student123"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(passwordEncoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(student, admin);
    }
}
~~~

**Đây là cấu hình runnable cho môi trường học tập.** Tài khoản và mật khẩu viết trực tiếp trong source chỉ để mô phỏng; không đưa các mật khẩu ví dụ này vào hệ thống thật.

### Giải thích từng phần SecurityFilterChain

**1. @Configuration và @Bean**

@Configuration đánh dấu lớp chứa định nghĩa bean. Phương thức có @Bean trả về SecurityFilterChain; Spring quản lý kết quả như một bean trong ApplicationContext. Tên phương thức có thể đổi; **kiểu bean** SecurityFilterChain mới là điều quan trọng.

**2. HttpSecurity được Spring cung cấp**

Đối số HttpSecurity là builder để khai báo cấu hình bảo mật cho một filter chain. Câu lệnh **return http.build()** dựng SecurityFilterChain thật từ cấu hình đó. Nếu bỏ @Bean hoặc không gọi build(), Spring sẽ không đăng ký chain theo ý bạn.

**3. authorizeHttpRequests quyết định quyền đối với URL**

- **requestMatchers(HttpMethod.GET, "/public").permitAll():** chỉ GET /public được phép đi qua lớp phân quyền request dù không đăng nhập.
- **requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN"):** GET /admin phải có authority ROLE_ADMIN.
- **anyRequest().authenticated():** mọi request còn lại phải được xác thực; đây là quy tắc cuối để không vô tình mở endpoint mới.

Các rule được xét theo thứ tự khai báo. Đặt điều kiện cụ thể trước điều kiện bao quát. Chẳng hạn, nếu viết anyRequest().authenticated() trước rule /admin, rule sau sẽ không có cơ hội quyết định quyền như dự kiến.

**4. HTTP Basic cho ví dụ đơn giản**

**httpBasic(Customizer.withDefaults())** bật cơ chế HTTP Basic; curl có thể gửi username/password trong Authorization header. HTTP Basic chỉ mã hóa cặp username/password bằng Base64, **không mã hóa bí mật**. Khi triển khai thực tế phải dùng HTTPS. Ví dụ local qua http://localhost:8080 chỉ dùng để học.

**5. Tắt form login để hành vi bài học rõ ràng**

**formLogin(AbstractHttpConfigurer::disable)** chỉ tắt cơ chế form login trong chain này; nó **không tắt xác thực** và cũng không tắt HTTP Basic. Nhờ đó request thiếu credentials tới endpoint bảo vệ nhận phản hồi thách thức HTTP Basic thay vì bị điều hướng đến trang đăng nhập HTML.

**6. Những gì cấu hình không làm**

Cấu hình này chưa bật method-level authorization, chưa hỗ trợ user từ database, chưa xây dựng login JSON/JWT, và chưa định nghĩa policy sở hữu tài nguyên. Nó vẫn có các cơ chế bảo mật mặc định do Spring Security áp dụng, bao gồm CSRF protection cho những request phù hợp; việc bật HTTP Basic không có nghĩa CSRF tự động bị tắt.

### Vì sao tự tạo SecurityFilterChain?

Khi thêm spring-boot-starter-security mà chưa tự khai báo chain, Spring Boot cung cấp cấu hình web security mặc định. Khi bạn đăng ký **SecurityFilterChain bean** của chính mình, cấu hình security chain mặc định của Boot sẽ lùi lại để bạn tự quyết định chính sách HTTP. Spring Security vẫn là bên cung cấp và thực thi các filter cần thiết.

Không cần kế thừa WebSecurityConfigurerAdapter: cách này đã bị loại bỏ khỏi Spring Security 6. Đối với cấu hình hiện đại, dùng bean SecurityFilterChain cùng lambda DSL.

## 4. Tạo UserDetailsService và PasswordEncoder đầu tiên

Cả hai bean đã có trong SecurityConfig, nhưng cần hiểu chính xác lý do.

### UserDetailsService làm gì?

Giao diện UserDetailsService có một phương thức trọng tâm:

~~~java
UserDetails loadUserByUsername(String username)
    throws UsernameNotFoundException;
~~~

Một implementation nhận username, tìm thông tin user và trả về **UserDetails** chứa username, password hash, authorities, trạng thái account. Ví dụ dùng **InMemoryUserDetailsManager** đã có sẵn; không cần tự viết lớp implements UserDetailsService.

Khi có yêu cầu HTTP Basic:

1. Filter trích username và password từ Authorization header.
2. Cơ chế xác thực được cấu hình sử dụng AuthenticationManager/AuthenticationProvider.
3. Với xác thực username/password qua UserDetailsService, provider lấy UserDetails theo username.
4. PasswordEncoder so sánh mật khẩu được cung cấp với password hash đã lưu.
5. Thành công thì Authentication có danh tính và authorities để rule trong SecurityFilterChain kiểm tra.

UserDetailsService **không** tự đọc HTTP request, **không** quyết định URL nào được truy cập và **không** trả trực tiếp HTTP 200/401/403.

### Vì sao thêm PasswordEncoder?

Mật khẩu trong UserDetails phải được lưu theo dạng mà cơ chế xác thực có thể kiểm tra an toàn. Trong ví dụ:

~~~java
@Bean
PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder();
}
~~~

BCryptPasswordEncoder dùng thuật toán băm mật khẩu thích hợp cho ví dụ. Trong userDetailsService, **passwordEncoder.encode("student123")** tạo chuỗi hash cho mật khẩu mẫu. Khi đăng nhập, Spring Security kiểm tra bằng cách so khớp mật khẩu gửi lên với hash, không so chuỗi plaintext với hash bằng phép equals.

BCrypt thường tạo giá trị hash khác nhau cho cùng mật khẩu do có salt; đây là hành vi bình thường. Vì InMemoryUserDetailsManager được tạo khi ứng dụng khởi động, user mẫu sẽ được thiết lập lại khi restart.

**Không dùng {noop} hoặc lưu plaintext trong production.** Với ứng dụng thật, mật khẩu được đăng ký và lưu dưới dạng hash tại thời điểm tạo tài khoản; lúc đọc từ database, UserDetailsService phải trả về đúng hash đã lưu.

### role và GrantedAuthority

~~~java
User.withUsername("admin")
    .password(passwordEncoder.encode("admin123"))
    .roles("ADMIN")
    .build();
~~~

Trong cách cấu hình mặc định, **roles("ADMIN")** tạo authority **ROLE_ADMIN**. Vì vậy **hasRole("ADMIN")** tương ứng với authority ROLE_ADMIN. Nếu dùng **hasAuthority("ADMIN")**, Spring Security sẽ tìm đúng authority có tên ADMIN, không tự thêm ROLE_; hai cách này không thể thay thế tùy tiện.

Trong ví dụ, student có ROLE_USER và admin có ROLE_ADMIN. Admin không có ROLE_USER mặc định; hãy cấp đủ các authority cần thiết khi thiết kế role thực tế.

### Khác biệt giữa bean và đối tượng user

Có **một** bean UserDetailsService ở đây, nhưng nó quản lý **hai** UserDetails. Số lượng user không phải số lượng bean. Spring không tự tạo một UserDetailsService riêng cho từng user.

Việc tự định nghĩa UserDetailsService cũng khiến cấu hình in-memory user mặc định với mật khẩu sinh tự động của Spring Boot lùi lại. Vì vậy khi chạy ví dụ, hãy dùng đúng student/student123 hoặc admin/admin123, không tìm mật khẩu ngẫu nhiên trong log.

## 5. Tạo controller để kiểm tra

Tạo tệp **src/main/java/com/example/securitydemo/DemoController.java**:

~~~java
package com.example.securitydemo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicEndpoint() {
        return "Hello, everyone!";
    }

    @GetMapping("/profile")
    public String profile(Authentication authentication) {
        return "Hello, " + authentication.getName() + "!";
    }

    @GetMapping("/admin")
    public String adminEndpoint() {
        return "Admin dashboard";
    }
}
~~~

Ở /profile, tham số Authentication do Spring Security/Spring MVC cung cấp thể hiện danh tính đã qua bước xác thực. Khi gửi credentials của student, **authentication.getName()** trả **student**. Cách sử dụng tham số này không đồng nghĩa controller tự xác thực mật khẩu; request đã đi qua filter chain trước khi controller được gọi.

Chỉ ba GET endpoint là đủ để kiểm chứng:

- /public: ai cũng xem được.
- /profile: người đăng nhập hợp lệ xem được.
- /admin: chỉ người có ROLE_ADMIN xem được.

## 6. Chạy ứng dụng và thử từng tình huống

Tại thư mục **security-first-beans/** có pom.xml:

~~~bash
mvn spring-boot:run
~~~

Đợi ứng dụng khởi động thành công trên cổng 8080. Lệnh sau dùng cú pháp curl; trên Windows PowerShell nên dùng **curl.exe** để tránh alias của PowerShell cũ. Có thể thay curl bằng curl.exe mà không đổi các đối số.

### Thử request công khai

~~~bash
curl -i http://localhost:8080/public
~~~

Kết quả chính dự kiến:

~~~http
HTTP/1.1 200
Content-Type: text/plain;charset=UTF-8

Hello, everyone!
~~~

Các header khác có thể xuất hiện do security headers mặc định hoặc do web server. Mục tiêu là kiểm chứng status 200 và nội dung **Hello, everyone!**.

### Thử request bảo vệ nhưng chưa đăng nhập

~~~bash
curl -i http://localhost:8080/profile
~~~

Kết quả chính dự kiến:

~~~http
HTTP/1.1 401
WWW-Authenticate: Basic realm="Realm"
~~~

Thông tin WWW-Authenticate có thể thay đổi theo cấu hình; status **401** là điều cần quan sát. Request chưa có credentials hợp lệ nên chưa được phép vào /profile.

### Đăng nhập bằng tài khoản student

~~~bash
curl -i -u student:student123 http://localhost:8080/profile
~~~

Kết quả chính dự kiến:

~~~http
HTTP/1.1 200

Hello, student!
~~~

Tham số **-u student:student123** khiến curl tạo Authorization header dạng Basic; endpoint đọc tên của Authentication đã xác thực.

### Student thử truy cập /admin

~~~bash
curl -i -u student:student123 http://localhost:8080/admin
~~~

Kết quả chính dự kiến:

~~~http
HTTP/1.1 403
~~~

User student đã được xác thực, nhưng thiếu ROLE_ADMIN, nên bị từ chối bởi quy tắc authorization.

### Admin truy cập /admin

~~~bash
curl -i -u admin:admin123 http://localhost:8080/admin
~~~

Kết quả chính dự kiến:

~~~http
HTTP/1.1 200

Admin dashboard
~~~

### Thử mật khẩu sai

~~~bash
curl -i -u student:wrong-password http://localhost:8080/profile
~~~

Kết quả chính dự kiến là **401**, vì credentials không hợp lệ. Tài khoản đúng nhưng mật khẩu sai không được coi là user đã xác thực.

| Request | Credentials | Kết quả chính | Lý do |
| --- | --- | --- | --- |
| GET /public | Không có | 200 + Hello, everyone! | permitAll |
| GET /profile | Không có | 401 | Cần xác thực |
| GET /profile | student/student123 | 200 + Hello, student! | Xác thực thành công |
| GET /admin | student/student123 | 403 | Thiếu ROLE_ADMIN |
| GET /admin | admin/admin123 | 200 + Admin dashboard | Có ROLE_ADMIN |
| GET /profile | student/wrong-password | 401 | Mật khẩu sai |

**401 và 403 khác nhau:** 401 thường thể hiện cần credentials hợp lệ; 403 thường thể hiện request không có quyền hoặc bị từ chối bởi một cơ chế bảo vệ khác. Không nên suy ra mọi 403 đều do role sai, vì chẳng hạn CSRF cũng có thể trả về 403.

## 7. Theo dấu một request từ đầu đến cuối

Xét lệnh:

~~~bash
curl -i -u student:student123 http://localhost:8080/profile
~~~

Dòng xử lý khái niệm:

~~~text
Client
  |
  | GET /profile
  | Authorization: Basic ...
  v
Servlet container
  |
  v
DelegatingFilterProxy -> springSecurityFilterChain
  |
  v
FilterChainProxy -> SecurityFilterChain đã cấu hình
  |
  +-- HTTP Basic filter đọc credentials
  |       |
  |       +-- Provider xác thực username/password
  |               |
  |               +-- UserDetailsService.loadUserByUsername("student")
  |               +-- PasswordEncoder so mật khẩu với hash
  |               +-- Authentication(student, ROLE_USER)
  |
  +-- Authorization kiểm tra /profile -> authenticated()
  |
  v
DemoController.profile(authentication)
  |
  v
HTTP 200, body: Hello, student!
~~~

Sơ đồ tập trung vào hai bean trong bài; đây **không phải** danh sách đầy đủ hoặc thứ tự tuyệt đối của tất cả filter. Spring Security còn có các filter/ngữ cảnh bảo mật, xử lý ngoại lệ, CSRF, headers và những thành phần tùy theo cấu hình.

Với GET /admin của student, xác thực vẫn thành công nhưng rule **hasRole("ADMIN")** từ chối quyền. Controller.adminEndpoint() không chạy. Với mật khẩu sai, bước xác thực thất bại trước khi controller chạy.

## 8. Những điểm quan trọng khi tự thay đổi cấu hình

### Phạm vi khớp URL và thứ tự rule

Rule sau:

~~~java
.requestMatchers(HttpMethod.GET, "/public").permitAll()
~~~

chỉ khớp **GET** /public, không có nghĩa POST /public công khai. Đường dẫn và HTTP method đều có thể ảnh hưởng đến quyết định quyền. Khi thêm API, hãy xác định rõ method, path và quyền cần thiết.

Trong một SecurityFilterChain, rule cụ thể đặt trước **anyRequest()**. Với ứng dụng có nhiều SecurityFilterChain, cần hiểu thêm securityMatcher và thứ tự chain; bài này chỉ tạo một chain để tránh phức tạp ban đầu.

### Xác thực không đồng nghĩa phân quyền tài nguyên

Đoạn **anyRequest().authenticated()** chỉ kiểm tra người dùng đã xác thực. Nó không kiểm tra người dùng có sở hữu tài liệu, hóa đơn hoặc dữ liệu của một tenant hay không. Nếu thêm endpoint như GET /orders/{id}, service phải xác minh chủ sở hữu hoặc quyền truy cập dữ liệu cụ thể để tránh lỗ hổng truy cập chéo tài nguyên.

### Đừng vô tình tắt CSRF khi học cấu hình cơ bản

Trong ví dụ không hề gọi csrf().disable(). Spring Security thường bật bảo vệ CSRF mặc định cho những HTTP method có khả năng thay đổi trạng thái. Nếu bổ sung endpoint POST/PUT/DELETE và gọi bằng curl mà không gửi CSRF token, bạn có thể nhận **403** dù username/password đúng.

Phải phân tích cơ chế client gửi credentials trước khi quyết định thay đổi CSRF: website dùng cookie session thường cần bảo vệ CSRF; API chỉ dùng bearer token chủ động gửi qua Authorization header có thể có cấu hình khác. Không tắt CSRF chỉ để “làm hết lỗi 403”.

### Vì sao không dùng formLogin cùng HTTP Basic ở ví dụ này?

Hai cơ chế phục vụ cách giao tiếp khác nhau. HTTP Basic thuận tiện cho curl; formLogin thích hợp với luồng login qua biểu mẫu và thường gắn với session. Bài học chủ động chỉ sử dụng Basic để nhìn rõ SecurityFilterChain và UserDetailsService. Khi bật formLogin, cần thiết kế lại trang/form login, lưu session, redirect và CSRF cho phù hợp.

### Bean nào được khởi tạo lúc startup, thao tác nào xảy ra mỗi request?

- **SecurityFilterChain bean** được Spring tạo khi xây dựng ApplicationContext; filter chain này sẽ xử lý các request phù hợp.
- **InMemoryUserDetailsManager bean** được tạo khi startup, chứa các UserDetails mẫu.
- **BCryptPasswordEncoder bean** được dùng để băm mật khẩu mẫu lúc tạo users và để kiểm tra mật khẩu ở quá trình xác thực.
- Mỗi request HTTP Basic sẽ đi qua cơ chế bảo mật và có bước xác thực theo cách cơ chế đó quản lý request/ngữ cảnh; controller chỉ xử lý request được phép.

Không nên mô tả @Bean như thể Spring gọi lại phương thức tạo bean cho từng request: mặc định các bean này có scope singleton.

## 9. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Kiểm tra |
| --- | --- | --- |
| Tất cả endpoint đều trả 401 | Chưa khai báo permitAll đúng path/method; cấu hình SecurityConfig không được nhận | Kiểm tra package scan, @Configuration, @Bean và các requestMatchers |
| Student đăng nhập được nhưng /admin trả 403 | **Đúng hành vi thiết kế**: student có ROLE_USER | Dùng admin hoặc thay rule/quyền khi có yêu cầu rõ ràng |
| Username đúng, mật khẩu đúng nhưng vẫn 401 | PasswordEncoder không khớp hash; UserDetailsService trả sai user; gọi sai credentials | Xem bean UserDetailsService, hash, username; không log plaintext password |
| GET trả 200 nhưng POST trả 403 | Có thể thiếu CSRF token trên method thay đổi trạng thái | Xem CSRF policy và loại client; không tắt toàn cục theo phản xạ |
| Startup lỗi khi có nhiều bean tương tự | Nhiều bean user store/password encoder hoặc wiring không rõ ràng | Kiểm tra bean types, qualifier/primary nếu thực sự cần nhiều implementation |
| Bean không được tạo | SecurityConfig nằm ngoài package scan hoặc thiếu @Configuration/@Bean | Đặt dưới base package của @SpringBootApplication hoặc cấu hình scan rõ ràng |
| hasRole("ADMIN") không khớp quyền | Dữ liệu user đang chứa chuỗi authority khác ROLE_ADMIN | Phân biệt roles("ADMIN"), hasRole("ADMIN") và hasAuthority(...) |
| Endpoint mới vô tình cho phép truy cập | Rule quá rộng, đặt permitAll không phù hợp hoặc thiếu fallback | Dùng matcher hẹp, kiểm tra thứ tự rule, có quy tắc cuối rõ ràng |

Khi cần chẩn đoán, có thể tạm bật log Spring Security ở mức DEBUG trong môi trường phát triển để biết request khớp filter chain và rule nào. Tuyệt đối không in ra mật khẩu, Authorization header hoặc token bí mật. Tránh giải quyết 401/403 bằng cách xóa toàn bộ cấu hình bảo mật.

## 10. Bài tập thực hành

### Bài tập A — Endpoint bắt buộc đăng nhập

Thêm controller GET /private trả chuỗi “Private area”. Giữ **anyRequest().authenticated()** như ví dụ. Dự đoán và thử kết quả trước/sau khi gửi credentials của student. Giải thích tại sao không cần khai báo một rule riêng cho /private.

**Đáp án gợi ý:** GET /private không nằm trong rule /public hay /admin nên khớp anyRequest().authenticated(). Không có credentials → 401; student hợp lệ → 200 nếu controller tồn tại.

### Bài tập B — Thêm role REVIEWER

Thêm user reviewer/reviewer123 với roles("REVIEWER") trong InMemoryUserDetailsManager và endpoint GET /review dành cho role REVIEWER. Thêm rule requestMatchers GET /review **trước** anyRequest().authenticated().

**Đáp án gợi ý:** hasRole("REVIEWER") kiểm tra ROLE_REVIEWER. Reviewer vào /review được; student/admin chỉ vào khi thực sự được cấp ROLE_REVIEWER, chứ không tự được phép nhờ đã đăng nhập.

### Bài tập C — Quan sát 401 và 403

Thử lần lượt /admin không credentials, /admin với student, và /admin với admin. Ghi lại HTTP status và xác định request bị từ chối ở bước xác thực hay phân quyền.

**Đáp án:** Thiếu credentials → thường 401 với Basic; student hợp lệ → 403 do thiếu role; admin hợp lệ → 200.

### Bài tập D — Thêm API thay đổi trạng thái

Nếu thêm POST /profile với yêu cầu đã đăng nhập, hãy dự đoán kết quả của một POST bằng HTTP Basic nhưng thiếu CSRF token, rồi tìm cách cấu hình và kiểm thử bảo vệ CSRF phù hợp cho một client thực tế. Đừng tắt CSRF toàn cục để lấy status 200.

**Mục tiêu:** phân biệt xác thực người dùng, phân quyền endpoint và chống request giả mạo; hiểu lý do 403 có thể đến từ cơ chế khác ngoài role.

## 11. Checklist trước khi mở rộng dự án

1. Lớp SecurityConfig được Spring scan và trả về đúng **SecurityFilterChain bean**.
2. Rule công khai được khai báo cụ thể; rule cần login/role rõ ràng; có fallback cho các request còn lại.
3. UserDetailsService trả về username, password hash và authorities đúng ý định.
4. PasswordEncoder được cấu hình tương thích với cách password được lưu.
5. Có kiểm thử thực tế ít nhất 200/401/403 và xác minh body/side effects.
6. HTTP Basic chỉ dùng qua HTTPS trong môi trường thật.
7. Không dùng tài khoản/mật khẩu hardcoded hoặc lưu user trong bộ nhớ như cơ chế production.
8. Khi thêm database, JWT, OAuth2, method security hoặc object-level authorization, xác định ranh giới trách nhiệm của từng thành phần và bổ sung kiểm thử.
9. Khi thêm các method thay đổi dữ liệu, kiểm tra CSRF, xử lý input, authorization theo object và logging an toàn.

## 12. Tự kiểm tra kiến thức

**Hỏi:** SecurityFilterChain có lưu danh sách user không?  
**Đáp:** Không. Nó mô tả filter chain và chính sách bảo mật đối với request; user store là trách nhiệm của UserDetailsService hoặc thành phần xác thực tương ứng.

**Hỏi:** UserDetailsService có quyết định /admin cần ROLE_ADMIN không?  
**Đáp:** Không. Quy tắc URL nằm trong SecurityFilterChain; UserDetailsService chỉ cung cấp thông tin user, bao gồm authorities.

**Hỏi:** Tại sao cần PasswordEncoder khi dùng InMemoryUserDetailsManager?  
**Đáp:** Vì xác thực mật khẩu phải so với hash lưu trong UserDetails. In-memory không đồng nghĩa được lưu plaintext.

**Hỏi:** Khi student vào /admin, lỗi 403 có nghĩa password sai?  
**Đáp:** Không. Với mật khẩu đúng, student đã xác thực nhưng thiếu ROLE_ADMIN. Mật khẩu sai thường dẫn đến 401.

**Hỏi:** Một ứng dụng chỉ cần hai bean này là đã bảo mật hoàn toàn?  
**Đáp:** Chưa. Đây là nền tảng ban đầu; production còn cần user store bền vững, quản lý credentials, HTTPS, kiểm tra dữ liệu/tài nguyên, CSRF theo client, các security headers và kiểm thử phù hợp.

**Ghi nhớ:** Hãy bắt đầu bằng một SecurityFilterChain mô tả *request nào được phép*, một UserDetailsService cung cấp *user là ai và có authorities gì*, cùng PasswordEncoder để *xác minh mật khẩu an toàn*. Kiểm chứng hai bean bằng request HTTP thật trước khi thêm những cơ chế phức tạp hơn.
