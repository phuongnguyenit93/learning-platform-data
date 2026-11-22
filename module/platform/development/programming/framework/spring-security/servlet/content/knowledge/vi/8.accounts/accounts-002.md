# InMemoryUserDetailsManager cho ví dụ và kiểm thử trong Spring Security Servlet

## 1. Tổng quan và mục tiêu

Khi mới học **Spring Security Servlet**, bạn thường muốn tạo một vài tài khoản cố định để kiểm chứng **đăng nhập**, **phân quyền theo role**, **mật khẩu đã băm** và các phản hồi HTTP mà không phải thiết lập PostgreSQL, MySQL hay một dịch vụ nhận dạng bên ngoài. **InMemoryUserDetailsManager** đáp ứng nhu cầu này: nó lưu các đối tượng **UserDetails trong bộ nhớ tiến trình Java** và cung cấp cả thao tác tra cứu lẫn quản lý user.

Bài học này giúp bạn:

1. Hiểu vai trò của **UserDetailsService**, **UserDetailsManager**, **UserDetails**, **GrantedAuthority** và **InMemoryUserDetailsManager**.
2. Tạo user mẫu bằng **User.withUsername(...)**, **PasswordEncoder** và **roles(...)**.
3. Kết nối InMemoryUserDetailsManager với **SecurityFilterChain**, **DaoAuthenticationProvider** theo cơ chế tích hợp và HTTP Basic.
4. Thử các kết quả **200/401/403**, phân biệt xác thực sai với thiếu quyền.
5. Sử dụng **createUser**, **loadUserByUsername**, **userExists**, **updateUser** và **deleteUser** để chuẩn bị hoặc dọn dữ liệu test.
6. Viết **MockMvc integration tests** đi qua Spring Security filter chain, thay vì chỉ giả lập một người dùng đã xác thực.
7. Nhận ra giới hạn của giải pháp in-memory: **không bền vững qua restart, không chia sẻ giữa các node, không thay database production**, và cần xử lý bảo mật ngay cả với tài khoản test.

Ví dụ hoàn chỉnh sử dụng **Java 17+**, **Spring Boot 3.3.13**, **Spring Security 6**, Maven và **spring-security-test**. Chúng ta chỉ sử dụng **GET** cho API minh họa; nếu thêm request làm thay đổi trạng thái, cần xem xét CSRF và quyền truy cập riêng.

## 2. InMemoryUserDetailsManager là gì?

**org.springframework.security.provisioning.InMemoryUserDetailsManager** là một implementation cung cấp kho user trực tiếp trong bộ nhớ JVM. Nó thực hiện các thao tác của **UserDetailsManager**, qua đó cũng đáp ứng hợp đồng **UserDetailsService**.

Tách rõ các vai trò:

| Thành phần | Trách nhiệm | Có trực tiếp xác thực HTTP request không? |
| --- | --- | --- |
| **UserDetails** | Mô tả username, encoded password, trạng thái account, authorities | Không |
| **UserDetailsService** | Trả UserDetails theo username bằng loadUserByUsername | Không |
| **UserDetailsManager** | Mở rộng UserDetailsService với thao tác quản lý user | Không |
| **InMemoryUserDetailsManager** | Lưu/truy vấn/quản lý user trong bộ nhớ JVM | Không |
| **PasswordEncoder** | encode mật khẩu trước khi lưu, matches mật khẩu lúc xác thực | Không tự đọc request |
| **DaoAuthenticationProvider** | So raw password với hash từ UserDetailsService và kiểm tra trạng thái account | Được AuthenticationManager gọi |
| **AuthenticationManager / ProviderManager** | Điều phối AuthenticationProvider | Có trong luồng xác thực |
| **SecurityFilterChain** | Gắn các filter và luật bảo mật cho Servlet request | Xử lý request |
| **AuthorizationFilter** | Quyết định đã đủ quyền cho URL hay chưa | Kiểm tra quyền |

**InMemoryUserDetailsManager không phải là một AuthenticationManager.** Nó chỉ cung cấp dữ liệu user. Xác thực thực tế vẫn cần AuthenticationProvider phù hợp và PasswordEncoder khớp với password hash đã lưu.

### Hợp đồng quản lý user

Interface **UserDetailsManager** công bố các method thường dùng:

~~~java
void createUser(UserDetails user);
void updateUser(UserDetails user);
void deleteUser(String username);
void changePassword(String oldPassword, String newPassword);
boolean userExists(String username);
~~~

Ngoài ra, từ UserDetailsService có:

~~~java
UserDetails loadUserByUsername(String username)
    throws UsernameNotFoundException;
~~~

Đây là các **chữ ký minh họa từ interface**, không phải một chương trình Java độc lập. Để sử dụng trong ứng dụng, hãy inject InMemoryUserDetailsManager hoặc UserDetailsManager vào code test/dịch vụ có thẩm quyền.

**Phân biệt quan trọng:** updateUser nhận một UserDetails biểu diễn trạng thái tài khoản được cập nhật; **changePassword** có ngữ nghĩa thay mật khẩu người dùng hiện đang xác thực, phụ thuộc cấu hình security context/encoder thích hợp. Bài thực hành sử dụng updateUser một cách tường minh để kiểm thử kho dữ liệu; không gọi changePassword trong một request anonymous rồi giả định nó hoạt động.

## 3. UserDetails thực sự chứa những gì?

UserDetails là contract cần thiết cho xác thực bằng tên người dùng/mật khẩu. Những thuộc tính thường gặp:

- **getUsername()**: tên đăng nhập.
- **getPassword()**: mật khẩu **đã được encode/hash**, không phải raw password.
- **getAuthorities()**: tập quyền, ví dụ **ROLE_USER**, **ROLE_ADMIN**.
- **isEnabled()**: tài khoản có được bật hay không.
- **isAccountNonLocked()**: tài khoản có đang bị khóa hay không.
- **isAccountNonExpired()**: tài khoản có còn hạn hay không.
- **isCredentialsNonExpired()**: credentials có còn hạn hay không.

Spring Security cung cấp lớp xây sẵn **org.springframework.security.core.userdetails.User** và **User.UserBuilder**. Ví dụ:

~~~java
UserDetails learner = User.withUsername("learner")
    .password(encoder.encode("learn-pass"))
    .roles("USER")
    .build();
~~~

Các ý cần nhớ:

1. **roles("USER")** thường tạo authority **ROLE_USER**; chỉ truyền tên role **USER**, không thêm ROLE_ trước khi gọi roles.
2. **hasRole("USER")** trong cấu hình authorization mặc định đối chiếu authority **ROLE_USER**.
3. **authorities("document:read")** cho phép mô tả quyền cụ thể hơn; hasAuthority dùng tên quyền đúng chuỗi.
4. **password(encoder.encode(...))** lưu hash theo encoder được cấu hình, không đưa raw password vào object UserDetails dùng lâu dài.
5. Những password mẫu trong bài chỉ dành cho môi trường localhost/test. Không sử dụng trong sản phẩm thật.

**InMemoryUserDetailsManager lưu dữ liệu trong RAM**, không đồng nghĩa việc hệ thống có thể lấy lại mật khẩu gốc từ hash. Hash password phù hợp là một chiều; server xác nhận mật khẩu bằng **PasswordEncoder.matches(raw, encoded)**.

### UserDetails và principal sau xác thực

Sau khi provider xác thực, đối tượng Authentication có thể mang một **UserDetails** làm principal. Trong Spring Security, **ProviderManager** thường bật cơ chế xóa credentials khỏi kết quả xác thực. Vì thế không viết business logic hoặc test đòi principal.getPassword() phải còn hash sau login. Khi cần kiểm tra hash ban đầu, hãy kiểm tra qua nguồn test/user store **trước xác thực**, trong một phạm vi test an toàn, không trả hash ra HTTP response.

Đặc biệt, nếu tự xây UserDetailsService/cache khác và trả cùng mutable UserDetails instance cho cả cache lẫn principal, việc xóa credentials có thể ảnh hưởng password trong cache. InMemoryUserDetailsManager là một implementation cụ thể; không suy ra mọi repository/cache đều có chính sách defensive copy giống nhau. Với cache tùy biến hãy kiểm tra reference sharing và có test xác thực lặp lại.

## 4. Vòng đời của user in-memory

~~~text
Khởi động Spring Boot
        |
        v
SecurityConfig khai báo InMemoryUserDetailsManager bean
        |
        +--> tạo UserDetails learner (ROLE_USER)
        |         mật khẩu BCrypt hash
        |
        +--> tạo UserDetails admin (ROLE_ADMIN)
                  mật khẩu BCrypt hash
        |
        v
HTTP request tới endpoint có bảo vệ
        |
        v
SecurityFilterChain -> BasicAuthenticationFilter
        |
        v
AuthenticationManager -> DaoAuthenticationProvider
        |
        +--> loadUserByUsername(username)
        +--> PasswordEncoder.matches(raw, hash)
        +--> kiểm tra enabled/locked/expired
        |
        v
Authentication thành công?
   /            \
  Không          Có
   |             |
 401      Authentication trong SecurityContext
                 |
                 v
            AuthorizationFilter
                 |
           Có đủ quyền?
            /       \
           Có       Không
           |          |
       Controller     403
           |
          200
~~~

Không phải mọi request đều phải gọi UserDetailsService nếu một kiến trúc khác có session, remember-me hoặc cache riêng. Demo sẽ dùng **HTTP Basic + SessionCreationPolicy.STATELESS** để mỗi request có Basic credentials đi qua xác thực thích hợp; như vậy dễ quan sát tác động thay đổi user ngay trong JVM.

**In-memory storage không tự đồng bộ nhiều máy.** Nếu có hai JVM, mỗi JVM có map user riêng. createUser tại JVM A không làm JVM B tự nhận tài khoản ấy. Khi process dừng hoặc restart, những thay đổi phát sinh trong runtime mất đi; chỉ dữ liệu seed lại lúc khởi động được tạo lại.

## 5. Tạo bean và PasswordEncoder đúng cách

Một cấu hình cơ bản:

~~~java
@Bean
PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder();
}

@Bean
InMemoryUserDetailsManager userDetailsService(
        PasswordEncoder encoder) {

    UserDetails learner = User.withUsername("learner")
        .password(encoder.encode("learn-pass"))
        .roles("USER")
        .build();

    return new InMemoryUserDetailsManager(learner);
}
~~~

Đây là **fragment**, toàn bộ SecurityConfig runnable có ở mục 7.

**Tại sao cần PasswordEncoder?** Khi user gửi raw password qua HTTP Basic, provider cần so nó với hash lưu. BCryptPasswordEncoder có thuật toán matches phù hợp với các BCrypt hash được tạo bằng encode. Nếu user được tạo bằng encoder khác, ví dụ DelegatingPasswordEncoder có prefix **{bcrypt}**, bạn phải chọn cách xác minh tương thích với định dạng đang lưu.

**Không nên dùng chuỗi raw password trực tiếp** trong .password(...) rồi gắn BCryptPasswordEncoder. Điều đó không phải mật khẩu đã mã hóa, và matches có thể từ chối vì dữ liệu không phải BCrypt hash. Cũng không dùng **NoOpPasswordEncoder** trong production để che lỗi hash. Các ví dụ tài liệu đôi khi dùng **{noop}** cho mục tiêu trình diễn, nhưng bài này chủ động sử dụng BCrypt nhất quán.

**BCrypt dùng salt ngẫu nhiên**: khởi động ứng dụng hai lần có thể sinh các chuỗi hash khác nhau cho cùng mật khẩu demo, nhưng HTTP Basic vẫn xác thực được khi raw password đúng. Không hardcode giá trị hash cụ thể làm stdout/test expected.

## 6. Phân biệt UserDetailsService và UserDetailsManager khi test

Với code chỉ cần tải thông tin tài khoản để xác thực, inject **UserDetailsService** là đủ:

~~~java
UserDetails details = users.loadUserByUsername("learner");
~~~

Với code cần chuẩn bị/dọn dữ liệu test, dùng **UserDetailsManager** hoặc **InMemoryUserDetailsManager**:

~~~java
manager.createUser(newUser);
boolean exists = manager.userExists("new-user");
manager.updateUser(updatedUser);
manager.deleteUser("new-user");
~~~

**Các fragment này không phải chương trình độc lập**: newUser, manager và updatedUser cần được khai báo, đồng thời phải kiểm soát đúng quyền và thứ tự thao tác. Project ở mục 7 và test ở mục 9 cho ví dụ hoàn chỉnh.

### Không có API liệt kê tất cả user trong UserDetailsManager

UserDetailsManager không công bố phương thức chuẩn **getAllUsers()**. Một test muốn kiểm tra user cụ thể nên dùng **userExists(username)** hoặc **loadUserByUsername(username)**. Nếu ứng dụng thật cần tìm kiếm, phân trang hoặc lọc người dùng, hãy thiết kế repository/service thích hợp thay vì tự suy đoán InMemoryUserDetailsManager là database/query engine.

### Cẩn thận với bean dùng chung giữa các test

SpringBootTest thường tái sử dụng application context; một InMemoryUserDetailsManager bean được mutate ở test A có thể ảnh hưởng test B. Vì vậy:

- Seed các tài khoản cố định không đổi trong các test thông thường.
- Dùng username riêng cho mỗi test quản lý dữ liệu.
- Có **try/finally** hoặc @AfterEach để xóa user tạm ngay cả khi assertion thất bại.
- Tránh chạy test song song trên cùng user hoặc dùng chung mutable state không được kiểm soát.
- Khi cần isolation chặt, tạo manager mới trong unit test, hoặc dùng test context/test fixture phù hợp thay vì phụ thuộc thứ tự test.
- Không cho test chỉnh/xóa tài khoản thực tế của hệ thống.

Trong demo, test quản lý sẽ tạo user tên **temporary-user** và dọn trong finally. Những test khác dùng learner/admin nhưng không sửa chúng nên thứ tự chạy không có ý nghĩa.

## 7. Project Spring Boot hoàn chỉnh

### 7.1. Cấu trúc tệp

~~~text
inmemory-users-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/inmemory/
    │       ├── InMemoryDemoApplication.java
    │       ├── SecurityConfig.java
    │       └── AccountController.java
    └── test/
        └── java/com/example/inmemory/
            └── InMemoryUsersIntegrationTest.java
~~~

Demo có ba endpoint:

- **GET /public**: công khai.
- **GET /me**: đòi xác thực; trả username và authorities, không có password.
- **GET /admin**: đòi ROLE_ADMIN.

Hai user ban đầu:

| Username | Mật khẩu demo | Roles | /me | /admin |
| --- | --- | --- | --- | --- |
| learner | learn-pass | USER | 200 | 403 |
| admin | admin-pass | ADMIN | 200 | 200 |
| Không credentials | — | Không | 401 | 401 |

Tất cả mật khẩu chỉ để chạy local và test. InMemoryUserDetailsManager không cấp user-admin API công khai; các thao tác CRUD được làm trong integration test dưới quyền kiểm soát code test.

### 7.2. pom.xml — Maven đầy đủ và hợp lệ

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
    <artifactId>inmemory-users-demo</artifactId>
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

Spring Boot parent quản lý phiên bản phụ thuộc phù hợp cho ví dụ. Đặt nguyên nội dung trên vào **một file pom.xml**, không cần thêm Maven profile nào khác. Nếu hệ thống production đang chạy Spring Boot khác, dùng dependency management/version của chính dự án đó.

### 7.3. InMemoryDemoApplication.java

~~~java
package com.example.inmemory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InMemoryDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(InMemoryDemoApplication.class, args);
    }
}
~~~

Entry point Spring Boot. Các class còn lại cùng package **com.example.inmemory**, nên Spring Boot quét được configuration và controller mà không cần component-scan đặc biệt.

### 7.4. SecurityConfig.java

~~~java
package com.example.inmemory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
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
    InMemoryUserDetailsManager userDetailsService(
            PasswordEncoder encoder) {

        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("learn-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(learner, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);

        return http.build();
    }
}
~~~

**Tại sao cấu hình này có thể xác thực?**

1. Có một bean **InMemoryUserDetailsManager**, đáp ứng interface **UserDetailsService**.
2. Có một bean **PasswordEncoder**, trùng thuật toán encode đã dùng khi seed user.
3. Spring Security dùng thông tin UserDetailsService/PasswordEncoder trong cơ chế **username/password authentication** chuẩn; ứng dụng không cần tự tạo controller so sánh password hay viết BasicAuthenticationFilter.
4. **httpBasic** bật HTTP Basic và challenge cho endpoint bảo vệ.
5. **STATELESS** yêu cầu mỗi request mang credentials riêng trong demo; không dựa vào HttpSession để nhớ login.
6. **formLogin disabled** tránh redirect tới trang login HTML khi học API Basic.
7. **hasRole("ADMIN")** đối chiếu ROLE_ADMIN do roles("ADMIN") sinh ra.
8. **anyRequest().denyAll()** tránh công khai các endpoint khác ngoài danh sách đã kiểm tra.

Nếu dự án đồng thời khai một **AuthenticationProvider/AuthenticationManager tùy biến** hoặc nhiều SecurityFilterChain, bạn phải xác định rõ request đi qua provider/chain nào; không mặc định mọi bean sẽ được sử dụng theo cùng thứ tự.

**Không tắt CSRF trong cấu hình này.** Demo chỉ dùng GET để đọc dữ liệu; GET không yêu cầu CSRF token. Nếu bạn thêm POST/PUT/DELETE, cần phân tích CSRF theo client/browser: HTTP Basic có thể được browser nhớ và gửi tự động. STATELESS không mặc nhiên vô hiệu rủi ro CSRF.

### 7.5. AccountController.java

~~~java
package com.example.inmemory;

import java.util.List;
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @GetMapping("/public")
    public Map<String, String> publicEndpoint() {
        return Map.of("message", "public");
    }

    @GetMapping("/me")
    public Map<String, Object> currentUser(
            Authentication authentication) {

        List<String> roles = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return Map.of(
            "username", authentication.getName(),
            "authorities", roles
        );
    }

    @GetMapping("/admin")
    public Map<String, String> adminEndpoint() {
        return Map.of("message", "admin-only");
    }
}
~~~

Controller chỉ dùng **Authentication** đã được Spring Security kiểm tra. Không truy cập trực tiếp password, không gọi loadUserByUsername để tự xác thực lại, không để client quyết định roles qua request param hoặc JSON.

### 7.6. Chạy ứng dụng

Từ thư mục **inmemory-users-demo** chứa pom.xml:

~~~bash
mvn spring-boot:run
~~~

Trên máy có JDK 17+ và Maven, ứng dụng chạy cổng 8080 theo cấu hình mặc định nếu cổng đó rảnh. Khi dependency chưa có trong cache Maven, cần truy cập repository để tải chúng.

Dùng terminal khác gọi:

~~~bash
curl -i http://localhost:8080/public
~~~

Kỳ vọng status **200** và JSON có message = "public".

Không gửi credentials:

~~~bash
curl -i http://localhost:8080/me
~~~

Kỳ vọng **401 Unauthorized** cùng challenge WWW-Authenticate: Basic (realm cụ thể phụ thuộc cấu hình).

Dùng user thường:

~~~bash
curl -i -u learner:learn-pass http://localhost:8080/me
~~~

Kỳ vọng **200 OK** với JSON:

~~~json
{
  "username": "learner",
  "authorities": ["ROLE_USER"]
}
~~~

Gọi endpoint admin bằng user thường:

~~~bash
curl -i -u learner:learn-pass http://localhost:8080/admin
~~~

Kỳ vọng **403 Forbidden**, vì đã xác thực nhưng không có ROLE_ADMIN.

Dùng admin:

~~~bash
curl -i -u admin:admin-pass http://localhost:8080/admin
~~~

Kỳ vọng **200 OK** với JSON có message = "admin-only".

Sai password:

~~~bash
curl -i -u learner:wrong-pass http://localhost:8080/me
~~~

Kỳ vọng **401 Unauthorized**.

**Lưu ý về curl -u:** dùng thông tin mẫu trong bài để chạy local. Với secrets thật, password trong câu lệnh có thể bị lưu ở shell history hoặc xuất hiện ở process information. Chọn cơ chế cấp secrets an toàn thích hợp; production luôn dùng **HTTPS** vì HTTP Basic chỉ Base64-encode username/password, không tự mã hóa bí mật.

## 8. Tại sao 401 khác 403?

Đây là một phần rất quan trọng khi kiểm thử user in-memory:

| Tình huống | UserDetailsService / provider | Authorization | Kết quả |
| --- | --- | --- | --- |
| GET /public không credentials | Không cần xác thực để cho phép | permitAll | 200 |
| GET /me không credentials | Chưa có danh tính hợp lệ | authenticated() không đạt | 401 |
| GET /me sai password | matches(raw, encoded) thất bại | Không đi tới tài nguyên bảo vệ | 401 |
| GET /me learner đúng | Có Authentication của learner | authenticated() đạt | 200 |
| GET /admin learner đúng | Có ROLE_USER, không có ROLE_ADMIN | hasRole("ADMIN") từ chối | 403 |
| GET /admin admin đúng | Có ROLE_ADMIN | hasRole("ADMIN") đạt | 200 |

**401 Unauthorized** trong HTTP Basic thường có **WWW-Authenticate** để client biết cần gửi credentials. **403 Forbidden** trong trường hợp user đã xác thực nhưng thiếu role là lỗi authorization, không có nghĩa password sai.

Có những nguyên nhân khác cũng có thể tạo 403, ví dụ CSRF khi POST; không suy luận rằng cứ thấy 403 là credentials đúng mà không kiểm tra request và filter chain.

**Role và authority:** roles("ADMIN") tạo ROLE_ADMIN. hasRole("ADMIN") kiểm tra ROLE_ADMIN theo mặc định. Nếu bạn dùng authorities("ADMIN") không có tiền tố ROLE_, rule hasRole("ADMIN") sẽ không khớp; khi đó nên dùng hasAuthority("ADMIN") hoặc thống nhất mô hình quyền.

## 9. MockMvc integration tests hoàn chỉnh

Mục tiêu test không chỉ là chứng minh UserDetailsManager có lưu user; chúng ta cần kiểm tra **luồng HTTP thật của ứng dụng**: Spring Security filters, HTTP Basic, PasswordEncoder, phân quyền, rồi thao tác create/update/delete in-memory.

Tạo file **src/test/java/com/example/inmemory/InMemoryUsersIntegrationTest.java**:

~~~java
package com.example.inmemory;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class InMemoryUsersIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    InMemoryUserDetailsManager users;

    @Autowired
    PasswordEncoder encoder;

    @Test
    void publicEndpointWorksWithoutLogin() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public"));
    }

    @Test
    void protectedEndpointWithoutCredentialsReturns401()
            throws Exception {

        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongPasswordReturns401() throws Exception {
        mvc.perform(get("/me").with(
                httpBasic("learner", "wrong-pass")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void learnerCanReadOwnIdentity() throws Exception {
        mvc.perform(get("/me").with(
                httpBasic("learner", "learn-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("learner"))
            .andExpect(jsonPath("$.authorities[0]")
                .value("ROLE_USER"));
    }

    @Test
    void learnerCannotReadAdminEndpoint() throws Exception {
        mvc.perform(get("/admin").with(
                httpBasic("learner", "learn-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void administratorCanReadAdminEndpoint() throws Exception {
        mvc.perform(get("/admin").with(
                httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("admin-only"));
    }

    @Test
    void seedUserPasswordIsEncoded() {
        UserDetails learner = users.loadUserByUsername("learner");

        assertTrue(users.userExists("learner"));
        assertNotEquals("learn-pass", learner.getPassword());
        assertTrue(encoder.matches("learn-pass", learner.getPassword()));
        assertFalse(encoder.matches(
            "wrong-pass", learner.getPassword()));
    }

    @Test
    void canCreateUpdateAndDeleteTemporaryAccount() throws Exception {
        String username = "temporary-user";

        assertFalse(users.userExists(username));

        UserDetails initial = User.withUsername(username)
            .password(encoder.encode("initial-pass"))
            .roles("USER")
            .build();

        try {
            // Create: user mới xác thực được nhưng chưa có quyền admin.
            users.createUser(initial);
            assertTrue(users.userExists(username));

            mvc.perform(get("/me").with(
                    httpBasic(username, "initial-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value(username));

            mvc.perform(get("/admin").with(
                    httpBasic(username, "initial-pass")))
                .andExpect(status().isForbidden());

            // Update: đổi password hash và quyền của chính user tạm.
            UserDetails updated = User.withUsername(username)
                .password(encoder.encode("changed-pass"))
                .roles("ADMIN")
                .build();

            users.updateUser(updated);

            mvc.perform(get("/me").with(
                    httpBasic(username, "initial-pass")))
                .andExpect(status().isUnauthorized());

            mvc.perform(get("/admin").with(
                    httpBasic(username, "changed-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("admin-only"));

            // Delete: credentials mới cũng không còn xác thực được.
            users.deleteUser(username);
            assertFalse(users.userExists(username));

            mvc.perform(get("/me").with(
                    httpBasic(username, "changed-pass")))
                .andExpect(status().isUnauthorized());

        } finally {
            if (users.userExists(username)) {
                users.deleteUser(username);
            }
        }
    }

    @Test
    void disabledUserCannotAuthenticate() throws Exception {
        String username = "disabled-test";
        UserDetails disabled = User.withUsername(username)
            .password(encoder.encode("disabled-pass"))
            .roles("USER")
            .disabled(true)
            .build();

        try {
            users.createUser(disabled);

            mvc.perform(get("/me").with(
                    httpBasic(username, "disabled-pass")))
                .andExpect(status().isUnauthorized());

        } finally {
            if (users.userExists(username)) {
                users.deleteUser(username);
            }
        }
    }
}
~~~

Chạy test:

~~~bash
mvn test
~~~

### 9.1. Giải thích từng nhóm kiểm thử

**Nhóm HTTP cơ bản:** các test GET /public, GET /me không credentials, sai password, learner đúng, learner thiếu role và admin đúng đi qua **MockMvc + Spring Security filter chain**. Như vậy bạn đang xác nhận password và authorities thực tế của kho in-memory, không chỉ giả lập một authenticated user.

**Nhóm password encoding:** test **seedUserPasswordIsEncoded** đọc UserDetails từ manager, xác nhận password đã lưu khác raw string và dùng **PasswordEncoder.matches** để kiểm chứng. Test không in password hash ra console hoặc HTTP response.

**Nhóm CRUD:** test **canCreateUpdateAndDeleteTemporaryAccount** làm đủ vòng đời:

1. Kiểm tra user chưa tồn tại.
2. **createUser** thêm user với BCrypt hash và ROLE_USER.
3. Xác thực bằng HTTP Basic thành công; truy cập /admin bị 403.
4. **updateUser** cập nhật hash và role thành ADMIN.
5. Mật khẩu cũ bị 401; mật khẩu mới có thể truy cập /admin.
6. **deleteUser** xóa account khỏi manager.
7. Basic credentials sau xóa bị 401.
8. **finally** đảm bảo dọn user nếu assertion giữa chừng ném exception.

**Nhóm trạng thái tài khoản:** test **disabledUserCannotAuthenticate** tạo UserDetails có disabled(true). Dù raw password khớp hash, DaoAuthenticationProvider vẫn không chấp nhận một account disabled trong flow username/password chuẩn.

### 9.2. Vì sao không chỉ dùng @WithMockUser?

**@WithMockUser** rất có ích để test **authorization** nhanh mà không cần đi qua xác thực password thật. Ví dụ một controller test có thể giả lập ROLE_ADMIN để kiểm tra controller/service.

Tuy nhiên, nếu bài học muốn chứng minh InMemoryUserDetailsManager, BCrypt hash và DaoAuthenticationProvider thực sự kết nối đúng, **@WithMockUser không đủ**: nó đặt Authentication test có sẵn vào SecurityContext, không cần tra username/password từ manager. Vì thế ví dụ này chủ động dùng **httpBasic(username, password)** từ spring-security-test.

Bạn có thể dùng cả hai loại test trong dự án thật:

| Loại test | Mục tiêu | Có kiểm tra user store/password thật trong flow? |
| --- | --- | --- |
| Unit test trực tiếp manager | createUser, updateUser, deleteUser, loadUserByUsername | Không kiểm tra HTTP filter |
| MockMvc + @WithMockUser | Quyền của một principal giả lập, logic controller | Thường không |
| MockMvc + httpBasic | HTTP Basic, UserDetailsService, PasswordEncoder, authorization | Có, theo cấu hình ứng dụng |
| Test integration với DB thật | Query user, hash/roles, transaction, cache | Có, nếu setup đúng |

### 9.3. Test isolation và chạy song song

Ví dụ dùng **temporary-user** và **disabled-test** chỉ để test; không có test nào khác sửa hai user ấy. Dù vậy, nếu Maven/JUnit được cấu hình chạy cùng test class trên nhiều process hoặc nhiều test context chia sẻ dữ liệu ngoài, cần sinh tên user riêng cho từng test hoặc tạo manager riêng.

**Không dùng @DirtiesContext cho mọi test như phản xạ.** Việc tải lại toàn bộ Spring context có thể làm suite chậm. Dọn state trong finally thường đủ với những test tuần tự, còn trường hợp isolation đặc biệt cần thiết kế test fixture riêng.

### 9.4. Vì sao không hardcode BCrypt hash trong test?

BCrypt dùng salt ngẫu nhiên, nên một raw password thường tạo hash string khác nhau mỗi lần encode. Test nên dùng **encoder.matches** và chức năng của hệ thống, không mong một chuỗi hash bằng literal nào đó. Nếu test yêu cầu thay password, tạo encoded hash mới bằng cùng PasswordEncoder.

## 10. CRUD của UserDetailsManager có những giới hạn nào?

**createUser(UserDetails):** thêm một user vào manager. Nó không tự phát email xác minh, áp chính sách password, cấp MFA hay kiểm tra điều kiện pháp lý. Trong ví dụ, test đã encode password trước khi truyền UserDetails vào createUser.

**loadUserByUsername(String):** tra user theo username. Khi user không tồn tại, hợp đồng UserDetailsService thường ném **UsernameNotFoundException**; không giả định null là giá trị trả về chuẩn. Một số provider có thể chuyển lỗi username not found thành thông báo BadCredentials chung để tránh lộ sự tồn tại của tài khoản.

**userExists(String):** kiểm tra user đã được lưu trong manager. Đây là API nội bộ phục vụ quản lý và test; không nên công khai một endpoint có thể giúp attacker dò username.

**updateUser(UserDetails):** cập nhật dữ liệu user được cung cấp, gồm hash/roles/trạng thái. Không mặc nhiên có transaction trên DB, audit trail, invalidation của session/token hay optimistic locking như một repository production. Trong demo, updateUser dùng để chứng minh hiệu ứng khi HTTP Basic reauthenticate.

**deleteUser(String):** xóa user khỏi store hiện tại. Nếu ứng dụng dùng session đã xác thực ở request trước, việc xóa user khỏi store không tự xóa Authentication đã nằm trong session. Ví dụ dùng HTTP Basic stateless để mỗi request kiểm tra user store, nên sau delete credentials sẽ không được chấp nhận ở request mới.

**changePassword(String oldPassword, String newPassword):** có ngữ nghĩa dành cho user đang authenticated, và implementation có thể yêu cầu AuthenticationManager/PasswordEncoder được cấu hình thích hợp. Không nên dùng như shortcut tạo password mới cho tài khoản bất kỳ từ một request vô danh. Đối với nghiệp vụ reset/change thật, tạo service có kiểm tra quyền, so mật khẩu cũ nếu cần, encode mật khẩu mới và cập nhật một cách an toàn.

### Không đưa manager CRUD trực tiếp ra REST API công khai

Đây là một lỗi bảo mật phổ biến trong demo được copy sang production. Nếu viết:

~~~java
// Ví dụ phản diện: KHÔNG triển khai.
@PostMapping("/users")
public void create(@RequestBody UserDto user) {
    manager.createUser(...);
}
~~~

Đoạn trên chỉ là **fragment minh họa chống mẫu sai**, không phải code chạy độc lập: UserDto, manager và object truyền vào cần định nghĩa riêng. Vấn đề không chỉ ở cú pháp mà ở thiết kế: một request ngoài Internet không nên được phép tự chọn role/encoded password rồi tạo user mà không có authorization, validation, rate limiting, CSRF và audit thích hợp.

Trong project thực hành, CRUD chỉ xảy ra ở **test code**, không có HTTP endpoint tạo/xóa user.

## 11. Dữ liệu in-memory có được giữ sau restart không?

**Không.** Hãy phân biệt rõ bốn tình huống:

1. **Khởi động lần đầu:** bean userDetailsService tạo user learner và admin.
2. **Trong cùng JVM:** bạn gọi createUser("temporary-user"), user đó tồn tại cho những request dùng cùng bean.
3. **Restart JVM:** Spring tạo lại bean từ SecurityConfig; các user tạo tạm ở runtime không còn, còn user seed được tạo lại theo cấu hình.
4. **Chạy hai instance:** user tạo trong instance A không tự xuất hiện tại instance B.

| Đặc điểm | InMemoryUserDetailsManager | Repository/database production |
| --- | --- | --- |
| Setup ban đầu | Rất nhanh | Cần database/migration/schema |
| Dữ liệu qua restart | Không, trừ user seed được tạo lại | Có khi DB bền vững và vận hành đúng |
| Chia sẻ nhiều app instance | Không tự động | Có thể, tùy database/cache |
| Tìm kiếm, phân trang, giao dịch | Hạn chế, không phải query engine | Thiết kế được |
| Dùng trong tutorial/test | Rất phù hợp | Thường không cần |
| Lưu account thật lâu dài | Không nên | Phù hợp khi có security controls |
| Bảo vệ password/role | Vẫn cần | Vẫn cần, cộng transaction, audit, backup |

**Đừng suy ra rằng dùng in-memory nghĩa là bảo mật kém ở mọi trường hợp.** Với ứng dụng demo, prototype cô lập hoặc các test, đó là lựa chọn hợp lý. Điểm hạn chế chính là **persistence, quản trị dữ liệu và vận hành**, chứ không phải bản thân thuật toán password hash nếu đã dùng BCrypt đúng.

Ngược lại, một hệ thống production dùng database cũng không tự an toàn nếu lưu raw password, cấu hình thiếu authorization, để lộ token trong log hoặc không có bảo vệ brute force.

## 12. Lưu ý về user cache và credentials erasure

Trong một flow điển hình:

~~~text
InMemoryUserDetailsManager / UserDetailsService
          |
          v
DaoAuthenticationProvider lấy UserDetails
          |
          v
PasswordEncoder.matches(rawPassword, storedHash)
          |
          v
ProviderManager tạo Authentication thành công
          |
          v
Có thể erase credentials khỏi Authentication/principal
          |
          v
Controller sử dụng username + authorities
~~~

Tại controller, **authentication.getCredentials() có thể là null** và UserDetails principal có thể không còn password. Đây thường là hành vi mong muốn: sau login, ứng dụng giữ danh tính/quyền nhưng không cần lưu raw password trong Authentication.

Nếu một **cache tùy biến** trả cùng mutable instance UserDetails được dùng như principal, cơ chế eraseCredentials có thể làm hash trên object dùng chung bị xóa. Hãy giữ nguồn dữ liệu cache độc lập với object principal có thể bị erase; test ít nhất hai request login liên tiếp. InMemoryUserDetailsManager của framework có hành vi triển khai cụ thể; khi xây hệ thống khác, đừng giả định cơ chế xóa/cache luôn giống nhau.

Không dùng việc tắt ProviderManager.eraseCredentialsAfterAuthentication mặc định làm giải pháp đầu tiên cho lỗi cache vì có thể tăng thời gian giữ dữ liệu nhạy cảm trong RAM.

## 13. Sử dụng InMemoryUserDetailsManager trong unit test không cần Spring Boot

Khi chỉ cần kiểm tra **CRUD của user manager**, bạn có thể tạo manager trực tiếp thay vì tải Spring application context. Phần sau là một **JUnit 5 test class độc lập trong cùng Maven project**; nó không dùng HTTP, không cần Spring Boot chạy.

Tạo file thêm: **src/test/java/com/example/inmemory/InMemoryManagerUnitTest.java**:

~~~java
package com.example.inmemory;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

class InMemoryManagerUnitTest {

    @Test
    void createsReadsAndDeletesUserWithoutApplicationContext() {
        PasswordEncoder encoder = new BCryptPasswordEncoder();
        InMemoryUserDetailsManager manager =
            new InMemoryUserDetailsManager();

        UserDetails user = User.withUsername("unit-user")
            .password(encoder.encode("unit-pass"))
            .roles("USER")
            .build();

        assertFalse(manager.userExists("unit-user"));

        manager.createUser(user);
        assertTrue(manager.userExists("unit-user"));

        UserDetails loaded =
            manager.loadUserByUsername("unit-user");

        assertTrue(encoder.matches(
            "unit-pass", loaded.getPassword()));

        manager.deleteUser("unit-user");
        assertFalse(manager.userExists("unit-user"));

        assertThrows(UsernameNotFoundException.class,
            () -> manager.loadUserByUsername("unit-user"));
    }
}
~~~

Chạy **mvn test** để thực thi cả hai test class. Đây là lựa chọn tốt khi mục tiêu chỉ là kiểm tra manager; test chạy nhanh và không phụ thuộc container HTTP. Tuy nhiên nó **không** xác minh SecurityFilterChain hoặc tính đúng của requestMatchers. Vì thế phải kết hợp unit test và integration test theo nhu cầu.

**Điểm đáng nhớ:** InMemoryUserDetailsManager có constructor không đối số cho một store ban đầu trống; bạn có thể thêm user bằng createUser. Trong ví dụ Spring Boot, ta dùng constructor nhận varargs UserDetails để seed những user mẫu.

## 14. Nhầm lẫn với một số thành phần khác

### 14.1. InMemoryUserDetailsManager và InMemoryAuthentication

Một số ví dụ Spring Security cũ dùng cấu hình **inMemoryAuthentication()** trong WebSecurityConfigurerAdapter. Với Spring Security 6, bạn nên ưu tiên **SecurityFilterChain bean** và **UserDetailsService/InMemoryUserDetailsManager bean**, tránh sao chép cấu hình deprecated/removed từ phiên bản cũ.

### 14.2. InMemoryUserDetailsManager và InMemoryUserDetailsService

Tên implementation đúng trong module Servlet/username-password phổ biến là **InMemoryUserDetailsManager**. Nó có thể được inject qua interface **UserDetailsService** hoặc **UserDetailsManager**. Không tạo class tự phát minh tên gần giống rồi dựa vào giả định API.

### 14.3. InMemoryUserDetailsManager và MapReactiveUserDetailsService

**MapReactiveUserDetailsService** phục vụ hệ sinh thái **Reactive/WebFlux**, còn bài này dùng **Servlet**. Hai stack có kiểu filter chain và API khác, không đặt bean reactive vào một ứng dụng Servlet rồi kỳ vọng mọi thứ tự liên kết.

### 14.4. InMemoryUserDetailsManager và database

Một ứng dụng production có thể dùng **JdbcUserDetailsManager** hoặc implementation UserDetailsService/Repository tùy biến liên kết database. Phần quản lý user, password hashing, kiểm tra trạng thái account, role mapping vẫn là các khái niệm cần giữ khi chuyển từ in-memory sang persistent storage.

### 14.5. HTTP Basic và form login

Cả HTTP Basic và form login có thể sử dụng **cùng UserDetailsService** để tải user và PasswordEncoder để kiểm tra raw password. Khác biệt chủ yếu ở cách nhận credentials và cách duy trì Authentication. HTTP Basic client gửi Authorization header, còn form login dùng form parameters và thường có session. Không cần thay InMemoryUserDetailsManager chỉ vì chuyển UI từ Basic sang form.

### 14.6. Role và authority

**roles("ADMIN")** tạo ROLE_ADMIN trong builder chuẩn. **authorities("ADMIN")** tạo quyền đúng chuỗi ADMIN, không có prefix. hasRole("ADMIN") và hasAuthority("ADMIN") không tự tương đương. Một lỗi prefix có thể tạo 403 dù password đúng.

## 15. Vận hành và an toàn bảo mật

**Không dùng mật khẩu mẫu ngoài localhost.** Dữ liệu seed của bài phục vụ học tập, không phải tài khoản vận hành. Khi triển khai thật, đưa secrets ra khỏi source code và chọn kho user có chính sách password, reset/rotation, khóa account và kiểm toán.

**Không lưu raw password.** UserDetails password field nên là encoded hash từ encoder phù hợp. Dùng BCrypt/Argon2/PBKDF2/scrypt theo chính sách và benchmark của hệ thống, không dùng hashing nhanh không salt dành cho integrity check thay password hashing.

**Không công khai CRUD user.** Việc gọi createUser/updateUser/deleteUser phải được giới hạn trong code có thẩm quyền; với API quản trị cần kiểm tra authorization, validation đầu vào, CSRF, rate limiting và audit.

**Không lấy authorities từ client làm nguồn tin cậy.** Nếu user gửi JSON "roles":["ADMIN"], đừng tự động biến chúng thành quyền được cấp; chỉ kho user và nghiệp vụ quản trị được phê duyệt mới quyết định authorities.

**Giữ CSRF policy phù hợp.** Với HTTP Basic qua browser, trình duyệt có thể nhớ credentials. Nếu thêm endpoint POST, hãy đánh giá CSRF thay vì tắt do nhầm STATELESS đồng nghĩa an toàn.

**Không log mật khẩu/hash/header.** Không ghi Authorization, raw password, BCrypt hash, session cookie hoặc toàn bộ Authentication vào logger/telemetry. Đối với test, có thể assert bằng boolean hoặc các thuộc tính không nhạy cảm.

**Đừng dùng hash cố định trong test output.** BCrypt tạo salt ngẫu nhiên. Test nên xác minh encoder.matches và các trạng thái đúng, không snapshot string hash.

**Không xem việc xóa user là thu hồi mọi phiên đã cấp.** Với session-based app, Authentication đã lưu trong HttpSession có thể tiếp tục tồn tại. Cần session invalidation/revocation và kiểm tra account state theo yêu cầu.

**Tài khoản trong một JVM không phải identity store phân tán.** Khi scale thành nhiều pod/instance, chuyển sang persistent store hoặc một identity provider, đồng thời thiết kế cache consistency và session/token policy.

**Rate limiting và chống brute force:** password hashing cost cao có thể tiêu tốn CPU khi bị credential stuffing. Áp dụng rate limit, monitoring và policy khóa/khôi phục tài khoản phù hợp khi triển khai login thật.

## 16. Chẩn đoán các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| GET /me trả 401 dù raw password đúng | Stored password chưa được encode, hoặc encoder không khớp | PasswordEncoder.matches trên stored hash |
| UserDetailsService báo không có user | Username không được seed, sai tên, hoặc JVM khác | userExists, source bean và environment |
| GET /admin trả 403 với learner | Chỉ có ROLE_USER | hasRole("ADMIN") so với authorities |
| Admin đúng vẫn 403 | Đã dùng authorities("ADMIN") thay roles("ADMIN") | Kiểm tra ROLE_ prefix |
| Test createUser chạy được, test khác bị ảnh hưởng | Shared ApplicationContext chứa manager mutable | Dùng user riêng và cleanup |
| Sau restart mất user tạm | In-memory không persistent | Chuyển sang database/identity provider |
| Thay password nhưng request cũ vẫn truy cập | Ứng dụng dùng session chứa Authentication đã xác thực | Session revocation, security context policy |
| Mật khẩu bị lộ trên log/curl history | In header/shell/trace có raw credentials | Redact và cấp secrets an toàn |
| Form login redirect 302 thay vì Basic challenge | Bật formLogin đồng thời hoặc chain khác | SecurityFilterChain, httpBasic, exception entry point |
| Thay role rồi request vẫn thấy role cũ | Session/cache/principal cũ | Reauthentication, cache/session invalidation |
| Test với @WithMockUser pass nhưng HTTP Basic fail | Mock bypass store/password provider | Dùng MockMvc httpBasic integration test |
| createUser trong production không có ở node khác | Store là RAM trong JVM hiện tại | DB/identity service chia sẻ |
| POST mới bị 403 | CSRF hoặc authorization policy | CSRF token, HTTP method, security rules |
| Có nhiều bean UserDetailsService | Provider tự cấu hình có thể không rõ nguồn | Xác minh AuthenticationManager/provider wiring |

### Các bước debug nhanh

1. Kiểm tra đúng URL, HTTP method, SecurityFilterChain và port của app.
2. Xác nhận bean InMemoryUserDetailsManager được tạo và userExists(username) đúng trong môi trường test.
3. Xác nhận password được encode theo PasswordEncoder mà provider sử dụng.
4. Xác nhận request có Authorization header Basic hợp lệ hoặc dùng MockMvc httpBasic.
5. Nếu 401, xem username, trạng thái account, password matches và authentication entry point; tránh ghi credentials.
6. Nếu 403, kiểm tra authorities, ROLE_ prefix, CSRF và rule authorizeHttpRequests.
7. Nếu test ảnh hưởng lẫn nhau, kiểm tra shared manager state, user test cleanup và việc chạy song song.
8. Nếu lỗi sau restart hoặc nhiều node, nhớ rằng manager không persistent/phân tán.
9. Với tích hợp phức tạp, kiểm tra có AuthenticationProvider custom và nhiều chain cùng matcher không.
10. Ghi thêm integration tests tái hiện lỗi thay vì tắt authentication hoặc CSRF để được status 200.

## 17. Bài tập tự luyện có đáp án

### Bài A — UserDetailsService hay UserDetailsManager?

Bạn chỉ cần tải user để kiểm tra password; interface nào là đủ? Khi cần tạo/xóa một user test, interface nào phù hợp?

**Đáp án:** chỉ tra user thì UserDetailsService đủ; cần create/update/delete/userExists thì UserDetailsManager phù hợp.

### Bài B — Tại sao phải encode?

Dùng .password("secret") trong builder nhưng provider có BCryptPasswordEncoder. Login có bảo đảm thành công không?

**Đáp án:** Không. Stored password phải ở định dạng BCrypt hash mà encoder.matches hiểu. Dùng encoder.encode("secret") khi tạo UserDetails; không lưu plaintext.

### Bài C — Role nào được tạo?

~~~java
User.withUsername("reader")
    .password(encoder.encode("pass"))
    .roles("ADMIN")
    .build();
~~~

Fragment trên tạo authority gì, và hasRole("ADMIN") kiểm tra gì?

**Đáp án:** quyền ROLE_ADMIN. hasRole("ADMIN") đối chiếu ROLE_ADMIN theo prefix mặc định.

### Bài D — 401 hay 403?

Một user có mật khẩu đúng và ROLE_USER gọi GET /admin cần ROLE_ADMIN. Status nào hợp lý trong demo?

**Đáp án:** 403 vì xác thực thành công nhưng không đủ quyền. 401 phù hợp khi chưa xác thực hoặc password sai.

### Bài E — Data persistence

Tạo temporary-user qua createUser, sau đó restart Spring Boot. User tạm có còn trong manager mới không?

**Đáp án:** Không, trừ khi được seed lại trong startup configuration. In-memory manager không persist thay đổi runtime.

### Bài F — Unit test hay integration test?

Test chỉ gọi manager.createUser/loadUserByUsername mà không qua SecurityFilterChain. Có đủ chứng minh /admin chặn ROLE_USER không?

**Đáp án:** Không. Cần test HTTP qua filter chain, ví dụ MockMvc với httpBasic đúng password và rule hasRole.

### Bài G — Thay password

Test tạo temporary-user mật khẩu cũ, sau đó updateUser với hash mới. Vì sao password cũ phải bị từ chối ở request HTTP Basic tiếp theo trong demo?

**Đáp án:** STATELESS yêu cầu xác thực lại mỗi request; PasswordEncoder.matches với hash mới không còn khớp raw password cũ.

### Bài H — Tại sao không dùng @WithMockUser để test BCrypt?

@WithMockUser có kiểm tra raw password bằng hash trong InMemoryUserDetailsManager hay không?

**Đáp án:** Không. @WithMockUser cung cấp Authentication giả lập cho test, hữu ích khi kiểm tra authorization nhưng không chứng minh user store/password provider tích hợp. Dùng MockMvc httpBasic nếu cần kiểm tra thực.

### Bài I — Cleanup

Nếu một assertion trong test tạo user tạm thất bại trước deleteUser, làm sao tránh ảnh hưởng test khác?

**Đáp án:** Dùng try/finally hoặc fixture teardown được thiết kế an toàn để xóa user nếu còn tồn tại, và dùng username riêng cho từng test.

### Bài K — Đa node

Bạn có hai app instance cùng cấu hình InMemoryUserDetailsManager. Test thêm user ở instance A, rồi gửi request vào B. B có biết user mới không?

**Đáp án:** Không có đồng bộ tự động giữa JVM. Cần persistent store hoặc identity service chung nếu đó là yêu cầu của kiến trúc.

## 18. Checklist trước khi áp dụng

- [ ] Hiểu InMemoryUserDetailsManager là **kho UserDetails trong RAM**, không phải AuthenticationManager.
- [ ] Tạo user với PasswordEncoder và hash phù hợp, không lưu plaintext.
- [ ] Dùng User.withUsername(...).roles(...) đúng quy ước ROLE_.
- [ ] Cấu hình SecurityFilterChain, httpBasic/formLogin và requestMatchers rõ ràng.
- [ ] Kiểm tra request không credentials, sai password, đúng password và thiếu role.
- [ ] Có ít nhất một test đi qua HTTP Basic + provider + store, không chỉ @WithMockUser.
- [ ] Với create/update/delete test, dùng user tạm và cleanup trong finally/teardown.
- [ ] Không chạy test mutable shared context song song mà không có isolation.
- [ ] Không xuất user passwords/hashes/Authorization header ra API hoặc log.
- [ ] Đã phân biệt 401 authentication failure và 403 authorization/CSRF denial.
- [ ] Đã hiểu restart/multi-node sẽ không giữ/chia sẻ các user thêm ở runtime.
- [ ] Không công khai API CRUD dựa trực tiếp trên manager mà thiếu kiểm soát quyền và audit.
- [ ] Không trông chờ deleteUser/updateUser tự thu hồi session đã phát.
- [ ] Sử dụng HTTPS với HTTP Basic thật và rate limiting cho endpoint login.
- [ ] Khi chuyển production, dùng UserDetailsService/identity store persistent phù hợp, transaction và security policies.

**Kết luận:** **InMemoryUserDetailsManager** là lựa chọn gọn nhẹ và hữu ích để xây ví dụ hoặc kiểm thử **Spring Security Servlet**. Nó cung cấp UserDetailsService để xác thực username/password và UserDetailsManager để tạo, sửa, xóa tài khoản test. Khi phối hợp với **BCryptPasswordEncoder**, **SecurityFilterChain**, HTTP Basic và **MockMvc**, bạn có thể kiểm tra trọn luồng 200/401/403 và dữ liệu user biến đổi trong cùng JVM. Hãy nhớ đây là **kho tạm trong RAM**, không phải hệ thống quản lý tài khoản bền vững hoặc phân tán cho production.
