# ReactiveUserDetailsService và MapReactiveUserDetailsService trong Spring Security WebFlux

> **Mục tiêu:** Hiểu vai trò của **ReactiveUserDetailsService** khi xác thực username/password trong Spring Security **reactive**, biết sử dụng **MapReactiveUserDetailsService** để xây dựng một ứng dụng WebFlux có thể chạy/kiểm thử, và biết khi nào phải thay kho user trong bộ nhớ bằng truy vấn **thực sự non-blocking**. Trọng tâm: Java 17+, Spring Boot 3.x, Spring Security 6.x và Reactor.

## 1. Vì sao xác thực WebFlux cần một kiểu UserDetailsService khác?

Trong Spring MVC/Servlet, nhiều cơ chế đăng nhập với username/password sử dụng **UserDetailsService** đồng bộ:

~~~java
// Hợp đồng của hệ Servlet, không phải WebFlux reactive:
UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException;
~~~

Lời gọi trên trả về **UserDetails** ngay hoặc ném exception. Nếu truy vấn database chặn thread, một request có thể giữ thread cho tới khi I/O kết thúc.

Trong Spring WebFlux, authentication pipeline làm việc với **Publisher** của Project Reactor. Giao diện tương ứng là **ReactiveUserDetailsService**:

~~~java
package org.springframework.security.core.userdetails;

import reactor.core.publisher.Mono;

public interface ReactiveUserDetailsService {
    Mono<UserDetails> findByUsername(String username);
}
~~~

**Mono<UserDetails>** biểu diễn tối đa một user được phát ra bất đồng bộ; nó không có nghĩa password đã được xác minh. Đây là hợp đồng **truy xuất dữ liệu người dùng**, không phải toàn bộ quá trình login. **ReactiveAuthenticationManager** mới có trách nhiệm đối chiếu credential và tạo **Authentication** khi thành công.

**MapReactiveUserDetailsService** là một implementation có sẵn của ReactiveUserDetailsService, giữ user trong một Map ở memory và trả **Mono<UserDetails>**. Nó tiện cho ví dụ, test, proof of concept và một số dịch vụ rất nhỏ có user cố định, nhưng không thay một hệ quản lý user thực.

### So sánh Servlet và reactive

| Vấn đề | Spring Security Servlet | Spring Security WebFlux |
| --- | --- | --- |
| Thành phần tìm user | **UserDetailsService** | **ReactiveUserDetailsService** |
| Phương thức | **loadUserByUsername(String)** | **findByUsername(String)** |
| Giá trị trả về | **UserDetails** đồng bộ | **Mono<UserDetails>** |
| Kho user in-memory mẫu | **InMemoryUserDetailsManager** | **MapReactiveUserDetailsService** |
| Thành phần xác thực username/password phổ biến | **DaoAuthenticationProvider** trong AuthenticationManager/ProviderManager | **UserDetailsRepositoryReactiveAuthenticationManager** trong ReactiveAuthenticationManager |
| Chain bảo mật HTTP | **SecurityFilterChain**, HttpSecurity, Servlet Filter | **SecurityWebFilterChain**, ServerHttpSecurity, WebFilter |
| Ngữ cảnh xác thực | SecurityContextHolder/ThreadLocal theo mô hình Servlet | **ReactiveSecurityContextHolder** trong Reactor Context |
| Kiểm thử web | MockMvc | **WebTestClient** |
| Data access phù hợp | JDBC/JPA hoặc dịch vụ đồng bộ | R2DBC, reactive driver hoặc client non-blocking |
| Lỗi thường gặp | Thread bị chặn bởi DB chậm | Gọi **block()**, JDBC/JPA trên event-loop Netty |

**Lưu ý:** có chữ *Reactive* trong tên interface không tự làm driver JDBC trở nên non-blocking. Phải thiết kế chuỗi I/O phù hợp. Ngược lại, MapReactiveUserDetailsService là lookup trong memory rất nhanh; không có network I/O để chờ.

## 2. Hợp đồng của ReactiveUserDetailsService

Chỉ một phương thức:

~~~java
Mono<UserDetails> findByUsername(String username);
~~~

Đầu vào là username mà bộ lọc/manager lấy từ yêu cầu đăng nhập. Đầu ra là một publisher. Trong thiết kế chuẩn:

- **Mono.just(user)** hoặc publisher tương đương: có bản ghi UserDetails; phần còn lại của pipeline sẽ kiểm tra trạng thái tài khoản, password, authorities.
- **Mono.empty()**: không tìm thấy user. Manager sẽ biến tình trạng không có user thành thất bại xác thực phù hợp; không nên phát ra UserDetails giả được gán quyền.
- **Mono.error(exception)**: lỗi thực như DB timeout, mất kết nối, lỗi xử lý dữ liệu. Cần fail closed; không chuyển lỗi thành một user có mật khẩu mặc định.
- **Không bao giờ trả Java null** thay vì Mono. Null không biểu diễn “không có user” trong Reactor.
- **Không làm các việc nặng/chặn thread** ngay bên trong phương thức trước khi trả publisher.

**UserDetails** mô tả dữ liệu user dùng cho xác thực: username, password hash, danh sách **GrantedAuthority**, trạng thái enabled, accountNonLocked, accountNonExpired, credentialsNonExpired. Nó không phải đối tượng HTTP response và thường **không nên serialize ra client**, đặc biệt là password hash.

Một ví dụ đơn giản thể hiện ý nghĩa:

~~~java
ReactiveUserDetailsService users = username -> {
    if ("alice".equals(username)) {
        UserDetails user = User.withUsername("alice")
                .password("{noop}training-only")
                .roles("READER")
                .build();
        return Mono.just(user);
    }
    return Mono.empty();
};
~~~

Đây là **đoạn minh họa hợp đồng**, không phải cấu hình sản phẩm: **{noop}** không băm mật khẩu, chỉ phù hợp để giải thích semantics; trong phần ví dụ chạy thật bên dưới sẽ dùng **BCryptPasswordEncoder**. Hai import **UserDetails**/**User** nằm ở package **org.springframework.security.core.userdetails** và Mono ở **reactor.core.publisher**.

### UserDetailsService không tự kiểm tra password

Hình dung một request:

~~~text
GET /api/me
Authorization: Basic <base64(username:password)>
                  |
                  v
       SecurityWebFilterChain
                  |
                  v
       AuthenticationWebFilter
             (HTTP Basic)
                  |
                  v
       ReactiveAuthenticationManager
                  |
                  v
UserDetailsRepositoryReactiveAuthenticationManager
                  |
                  +--> ReactiveUserDetailsService.findByUsername("alice")
                  |       |
                  |       +--> Mono<UserDetails>
                  |
                  +--> PasswordEncoder.matches(raw, storedHash)
                  +--> kiểm tra account flags
                  +--> dựng Authentication đáng tin
                  |
                  v
      ReactiveSecurityContextHolder / Reactor Context
                  |
                  v
          AuthorizationWebFilter
                  |
                  v
              Controller
~~~

**Không được gán isAuthenticated=true chỉ vì tìm thấy user.** Nếu client tự khai username và manager chưa so mật khẩu thì danh tính chưa được chứng minh. Authority phải đến từ nguồn do server quản lý, không từ trường **role** trong request.

## 3. MapReactiveUserDetailsService là gì và làm được gì?

Spring Security cung cấp:

~~~java
package org.springframework.security.core.userdetails;

public class MapReactiveUserDetailsService
        implements ReactiveUserDetailsService,
                   ReactiveUserDetailsPasswordService {
    // Triển khai của thư viện Spring Security.
}
~~~

Constructor hữu ích:

~~~java
new MapReactiveUserDetailsService(user1, user2);
new MapReactiveUserDetailsService(collectionOfUsers);
new MapReactiveUserDetailsService(mapOfUsernameToUserDetails);
~~~

Map có thể sử dụng trong ví dụ, nhưng với constructor nhận Map, Javadoc yêu cầu **Map không chặn**. Nên dùng cấu trúc memory thông thường hoặc loại map đồng thời phù hợp, không truyền adapter mà mỗi lần **get** lại truy cập database chặn thread.

| Điều mong đợi | Hành vi / lưu ý |
| --- | --- |
| Tìm user đã nạp vào Map | Trả Mono phát ra UserDetails tương ứng |
| Tìm username không tồn tại | Kết thúc không có phần tử |
| Tạo role | Dùng **User.withUsername(...).roles("READER")**, role trở thành **ROLE_READER** |
| Dùng authority chính xác | Dùng **authorities("SCOPE_read")**, không tự hiểu mọi string đều là role |
| Password | Lưu giá trị encoded hash do PasswordEncoder sinh; raw password không nên lưu trong Map |
| Thay đổi user | Map không phải database quản trị, không tự đồng bộ giữa node/restart |
| Đổi password | Lớp hỗ trợ interface **ReactiveUserDetailsPasswordService.updatePassword(...)**, nhưng đây không phải nghiệp vụ đổi mật khẩu hoàn chỉnh |
| Khởi động lại | Dữ liệu từ cấu hình/bean được tạo lại; thay đổi runtime không tự persisted |
| Phân tán nhiều instance | Mỗi instance có Map riêng; cần quản lý cùng cấu hình hoặc nguồn dữ liệu chung |

**ReactiveUserDetailsPasswordService** tách khỏi ReactiveUserDetailsService. Nó mô tả việc **cập nhật password hash đã mã hóa** trong kho user, có thể dùng trong cơ chế nâng cấp hash khi đăng nhập. Nó không tự có quy trình xác minh mật khẩu cũ, xác nhận người dùng, audit, MFA hoặc gửi email. Nếu tự viết thao tác đổi password, phải thiết kế riêng.

### Khi nào dùng MapReactiveUserDetailsService?

Phù hợp cho:

- Ví dụ học Spring Security WebFlux cần login thật bằng HTTP Basic/form.
- Automated tests với vài user và vai trò tĩnh.
- PoC, ứng dụng nội bộ rất nhỏ có danh sách user được quản lý bằng cấu hình/secret manager (vẫn cần xử lý rotation và deployment).
- So sánh trực tiếp contract **findByUsername** với UserDetailsService Servlet.

Không phù hợp khi cần user đăng ký/đổi password qua API, lockout, quản lý tenant, revoke theo thiết bị, audit dài hạn, hàng triệu accounts hoặc database làm nguồn sự thật. Khi ấy tạo **ReactiveUserDetailsService tùy chỉnh** truy vấn qua reactive repository và kiểm soát trạng thái user.

## 4. Ví dụ chạy được: Spring Boot WebFlux + MapReactiveUserDetailsService

Ta tạo ứng dụng Java 17+, Spring Boot 3.x và Spring Security 6.x, có **hai tài khoản**: **alice** được ROLE_READER, **admin** được ROLE_READER + ROLE_ADMIN. Client đăng nhập bằng HTTP Basic và thử endpoint public/reader/admin.

### 4.1. Chọn đúng dependencies

Tạo dự án Maven bằng **Spring Initializr**: Java 17+, Spring Boot 3.x, dependencies **Spring Reactive Web (spring-boot-starter-webflux)**, **Spring Security (spring-boot-starter-security)** và **Spring Boot Starter Test**. Với WebTestClient cần các thư viện test do starter-test/webflux cung cấp; nếu dự án đã tùy chỉnh dependencies, bảo đảm có **spring-test**, **reactor-test** và test HTTP client phù hợp.

Phần dependencies trong **pom.xml** của một dự án có Spring Boot parent/BOM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
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
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Đây là **trích đoạn**, không phải toàn bộ pom.xml. Dùng Spring Boot dependency management để giữ các version tương thích. **Không** thêm **spring-boot-starter-web** vào dự án này chỉ để có controller: nếu cùng có Spring MVC và WebFlux starter, Spring Boot có thể tự chọn ứng dụng Servlet; điều đó làm demo không còn minh họa pipeline reactive. Nếu dự án thật cố ý chạy hỗn hợp, phải cấu hình rõ **spring.main.web-application-type** và hiểu lý do.

Đặt các file Java trong **src/main/java/com/example/reactiveusers/**. Spring Boot main class cũng ở package này để component scan bao phủ các class còn lại.

### 4.2. Class khởi động

Tệp **ReactiveUsersApplication.java**:

~~~java
package com.example.reactiveusers;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveUsersApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveUsersApplication.class, args);
    }
}
~~~

### 4.3. Cấu hình Spring Security reactive

Tệp **SecurityConfig.java**:

~~~java
package com.example.reactiveusers;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService reactiveUsers(
            PasswordEncoder encoder,
            @Value("${demo.alice.password}") String alicePassword,
            @Value("${demo.admin.password}") String adminPassword) {

        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode(alicePassword))
                .roles("READER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode(adminPassword))
                .roles("READER", "ADMIN")
                .build();

        return new MapReactiveUserDetailsService(alice, admin);
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            MapReactiveUserDetailsService users,
            PasswordEncoder encoder) {

        var manager =
                new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager manager) {

        return http
                .authenticationManager(manager)
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/api/admin").hasRole("ADMIN")
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
~~~

**Từng phần có vai trò riêng:**

1. **@EnableWebFluxSecurity** kích hoạt cấu hình bảo mật WebFlux. Đối tượng cần tạo là **SecurityWebFilterChain**, không phải **SecurityFilterChain** của Servlet.
2. **PasswordEncoder** mã hóa raw password thành BCrypt hash khi tạo UserDetails. **roles("READER")** sinh **ROLE_READER**, tương tự ADMIN → ROLE_ADMIN.
3. **MapReactiveUserDetailsService** giữ hai user server quản lý. Password đến từ biến môi trường cho demo; trong production tài khoản/credential cần nguồn dữ liệu được bảo vệ và quy trình rotation.
4. **UserDetailsRepositoryReactiveAuthenticationManager** nhận ReactiveUserDetailsService và PasswordEncoder; nó xử lý credential username/password. **findByUsername** không tự verify password.
5. **http.authenticationManager(manager)** dùng manager đã cấu hình, tránh phụ thuộc vào việc đoán bean nào được auto-config.
6. **authorizeExchange** đặt rule cho request reactive. Endpoint **/api/admin** yêu cầu ROLE_ADMIN; các request còn lại phải xác thực, trừ **/public**.
7. **httpBasic(...)** nhận username/password từ header HTTP Authorization. **formLogin(...disable())** tắt login form, nên client không bị redirect HTML bất ngờ khi thử API; chưa có REST endpoint tự tạo token.
8. **Không tắt CSRF** vì demo chỉ dùng GET. Với POST/PUT/PATCH/DELETE có sử dụng cookie/session hoặc HTTP Basic từ browser, phải đánh giá và cấu hình CSRF theo mô hình client; đừng tắt chỉ để test xanh.

**Trọng điểm học tập:** bean MapReactiveUserDetailsService và UserDetailsRepositoryReactiveAuthenticationManager hoàn toàn là thành phần **reactive**. Đừng tạo **DaoAuthenticationProvider** của Servlet cho SecurityWebFilterChain này.

### 4.4. Controller nhận Authentication từ Reactor Context

Tệp **ApiController.java**:

~~~java
package com.example.reactiveusers;

import reactor.core.publisher.Mono;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/public")
    public Mono<String> publicEndpoint() {
        return Mono.just("public");
    }

    @GetMapping("/api/me")
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
                .map(context ->
                        "me " + context.getAuthentication().getName());
    }

    @GetMapping("/api/admin")
    public Mono<String> admin() {
        return Mono.just("admin");
    }
}
~~~

**ReactiveSecurityContextHolder** sử dụng **Reactor Context** để truy cập SecurityContext đã được xác minh. Khác **SecurityContextHolder** ThreadLocal trong nhiều ví dụ Servlet, Reactor Context đi cùng một chuỗi publisher và không phụ thuộc vào việc request luôn chạy một thread cố định.

Đừng truyền Authentication vào một **static ThreadLocal** tùy tiện khi xử lý reactive. Việc pipeline đổi scheduler/thread có thể khiến dữ liệu ThreadLocal không đi cùng request. Để truy cập context, dùng thành phần bảo mật reactive hoặc các argument được Spring WebFlux hỗ trợ.

### 4.5. Cấu hình mật khẩu demo

Tệp **src/main/resources/application.properties**:

~~~properties
server.port=8080
demo.alice.password=${DEMO_ALICE_PASSWORD}
demo.admin.password=${DEMO_ADMIN_PASSWORD}
~~~

Ở Linux/macOS:

~~~bash
export DEMO_ALICE_PASSWORD=alice-demo-pass
export DEMO_ADMIN_PASSWORD=admin-demo-pass
./mvnw spring-boot:run
~~~

Ở Windows PowerShell:

~~~powershell
$env:DEMO_ALICE_PASSWORD = "alice-demo-pass"
$env:DEMO_ADMIN_PASSWORD = "admin-demo-pass"
.\mvnw.cmd spring-boot:run
~~~

Các mật khẩu này chỉ là **dữ liệu luyện tập trên localhost**. Không dùng HTTP Basic trên Internet không có TLS: Base64 không bảo vệ mật khẩu khỏi bên quan sát. Production phải dùng HTTPS, bảo vệ secrets và xem xét giới hạn thử sai/rate limiting.

### 4.6. Gửi request bằng curl

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/me
curl -i -u alice:alice-demo-pass http://localhost:8080/api/me
curl -i -u alice:wrong http://localhost:8080/api/me
curl -i -u alice:alice-demo-pass http://localhost:8080/api/admin
curl -i -u admin:admin-demo-pass http://localhost:8080/api/admin
~~~

Kỳ vọng:

| Request | HTTP status | Body / ý nghĩa |
| --- | --- | --- |
| GET /public | **200** | **public** |
| GET /api/me không credential | **401** | Cần xác thực; có thể kèm WWW-Authenticate |
| Alice + đúng password → /api/me | **200** | **me alice** |
| Alice + sai password → /api/me | **401** | Password bị từ chối |
| Alice + đúng password → /api/admin | **403** | Đã xác thực nhưng không có ROLE_ADMIN |
| Admin + đúng password → /api/admin | **200** | **admin** |

Không kết luận request chỉ cần gửi username và role là đăng nhập được. Nguồn quyền nằm trong UserDetails phía server và PasswordEncoder phải so khớp password. Nếu browser/client có header Authorization cũ, hãy kiểm tra header thực tế khi thử tình huống không credential.

### 4.7. Cây thư mục mẫu

~~~text
reactive-users-demo/
  pom.xml
  src/
    main/
      java/com/example/reactiveusers/
        ReactiveUsersApplication.java
        SecurityConfig.java
        ApiController.java
      resources/
        application.properties
    test/
      java/com/example/reactiveusers/
        MapReactiveUsersTest.java
        WebFluxAuthenticationTest.java
~~~

Các file Java mang **package com.example.reactiveusers**. Không đặt nhiều public classes vào một file. Dự án Maven wrapper **mvnw/mvnw.cmd** thường do Spring Initializr tạo.

## 5. Kiểm thử ReactiveUserDetailsService và WebFlux authentication

Ta cần hai cấp test: **lookup trực tiếp Mono<UserDetails>** và **request HTTP qua WebFilter chain**. Nếu chỉ mock SecurityContext, bài kiểm thử có thể bỏ qua việc so mật khẩu thật.

### 5.1. Unit/context test với StepVerifier

Tệp **src/test/java/com/example/reactiveusers/MapReactiveUsersTest.java**:

~~~java
package com.example.reactiveusers;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(properties = {
        "demo.alice.password=alice-test-pass",
        "demo.admin.password=admin-test-pass"
})
class MapReactiveUsersTest {

    @Autowired
    MapReactiveUserDetailsService users;

    @Autowired
    PasswordEncoder encoder;

    @Test
    void knownUserHasServerControlledDetails() {
        StepVerifier.create(users.findByUsername("alice"))
                .assertNext(user -> {
                    assertEquals("alice", user.getUsername());
                    assertTrue(user.isEnabled());
                    assertTrue(encoder.matches(
                            "alice-test-pass", user.getPassword()));
                    assertTrue(user.getAuthorities().stream()
                            .anyMatch(a ->
                                    a.getAuthority().equals("ROLE_READER")));
                    assertFalse(user.getAuthorities().stream()
                            .anyMatch(a ->
                                    a.getAuthority().equals("ROLE_ADMIN")));
                })
                .verifyComplete();
    }

    @Test
    void missingUserYieldsNoDetails() {
        StepVerifier.create(users.findByUsername("nobody"))
                .verifyComplete();
    }
}
~~~

**StepVerifier** đăng ký subscription và kiểm tra tín hiệu emitted, complete/error của Mono. **Không** gọi **users.findByUsername("alice")** rồi lập tức đọc dữ liệu như thể Mono đã thực thi đồng bộ; publisher có thể lazy và chỉ chạy khi được subscribe.

Test không cần kiểm tra giá trị hash BCrypt chính xác bằng string equality, vì BCrypt dùng salt và hai lần encode cùng raw password không nhất thiết cho cùng chuỗi. Kiểm tra bằng **PasswordEncoder.matches(raw, encoded)**.

### 5.2. Integration test bằng WebTestClient

Tệp **src/test/java/com/example/reactiveusers/WebFluxAuthenticationTest.java**:

~~~java
package com.example.reactiveusers;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
                "demo.alice.password=alice-test-pass",
                "demo.admin.password=admin-test-pass"
        })
@AutoConfigureWebTestClient
class WebFluxAuthenticationTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicRouteNeedsNoAuthentication() {
        client.get().uri("/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void missingCredentialsReturn401() {
        client.get().uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void validPasswordAuthenticatesAlice() {
        client.get().uri("/api/me")
                .headers(h ->
                        h.setBasicAuth("alice", "alice-test-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("me alice");
    }

    @Test
    void incorrectPasswordIsRejected() {
        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth("alice", "wrong"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void unknownUserIsRejected() {
        client.get().uri("/api/me")
                .headers(h ->
                        h.setBasicAuth("unknown", "alice-test-pass"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void readerCannotAccessAdmin() {
        client.get().uri("/api/admin")
                .headers(h ->
                        h.setBasicAuth("alice", "alice-test-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminCanAccessAdmin() {
        client.get().uri("/api/admin")
                .headers(h ->
                        h.setBasicAuth("admin", "admin-test-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin");
    }
}
~~~

Đây là test request HTTP với server ngẫu nhiên (**RANDOM_PORT**) và **WebTestClient**, đi qua WebFlux/Spring Security chain thật của ứng dụng. Nếu test dùng credential sai mà vẫn 200, hãy kiểm tra manager wiring, encoder, matcher và việc endpoint có bị permitAll ngoài ý muốn hay không.

Chạy:

~~~bash
./mvnw test
./mvnw -Dtest=WebFluxAuthenticationTest test
~~~

PowerShell:

~~~powershell
.\mvnw.cmd test
.\mvnw.cmd '-Dtest=WebFluxAuthenticationTest' test
~~~

Khi test không chạy được, trước tiên kiểm tra JDK 17+, Maven wrapper, Boot 3.x, WebFlux starter và biến mật khẩu trong test. Các câu lệnh là hướng dẫn thực hành, **không phải báo cáo rằng bộ kiểm thử đã được chạy**.

### 5.3. Test dùng mock security context có giới hạn

Spring Security Test cho phép gắn một user giả vào reactive test client hoặc dùng annotation **@WithMockUser**. Điều đó hữu ích khi test **authorization** hoặc logic controller, nhưng **không kiểm tra dữ liệu** trong MapReactiveUserDetailsService và **không kiểm tra password**. Để xác minh đường login, cần gửi Basic credentials thật như integration test trên.

Một test unit gọi thẳng **ReactiveAuthenticationManager.authenticate(...)** cũng có giá trị: kiểm tra BadCredentialsException, disabled account và quyền trả về; nhưng nó không thay cho kiểm tra WebFilter HTTP.

## 6. Từ MapReactiveUserDetailsService sang nguồn user reactive thực

Khi user nằm trong PostgreSQL, MySQL, MongoDB hay dịch vụ nội bộ, **không** duy trì một Map vô hạn hoặc tự dùng JDBC chặn event-loop. Hãy thiết kế **ReactiveUserDetailsService** với repo non-blocking.

### 6.1. Tách hợp đồng bản ghi khỏi Spring Security

Ví dụ tiếp theo là **mẫu tích hợp thay thế**, không đặt cùng lúc với MapReactiveUserDetailsService trong demo mục 4 vì sẽ có **hai bean** ReactiveUserDetailsService. Mẫu này giả định bạn đã có reactive repository lưu dữ liệu account từ nguồn tin cậy. Nó tách trách nhiệm DB và chuyển bản ghi sang UserDetails:

Tệp **AccountRecord.java**:

~~~java
package com.example.reactiveusers;

import java.util.List;

public record AccountRecord(
        String username,
        String passwordHash,
        boolean active,
        List<String> grantedAuthorities) {
}
~~~

Tệp **AccountStore.java**:

~~~java
package com.example.reactiveusers;

import reactor.core.publisher.Mono;

public interface AccountStore {
    Mono<AccountRecord> findByUsername(String username);
}
~~~

**AccountStore** là một contract do ứng dụng đặt ra, không phải một repository Spring đã tự sinh. Một adapter **R2DBC**, **ReactiveMongoRepository** hoặc **WebClient** non-blocking cần cung cấp implementation phù hợp.

Tệp **DatabaseReactiveUserDetailsService.java**:

~~~java
package com.example.reactiveusers;

import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import reactor.core.publisher.Mono;

public final class DatabaseReactiveUserDetailsService
        implements ReactiveUserDetailsService {

    private final AccountStore accounts;

    public DatabaseReactiveUserDetailsService(AccountStore accounts) {
        this.accounts = accounts;
    }

    @Override
    public Mono<UserDetails> findByUsername(String username) {
        if (username == null || username.isBlank()
                || username.length() > 128) {
            return Mono.empty();
        }

        return accounts.findByUsername(username)
                .map(account -> User.withUsername(account.username())
                        .password(account.passwordHash())
                        .authorities(
                                account.grantedAuthorities().toArray(
                                        String[]::new))
                        .disabled(!account.active())
                        .build());
    }
}
~~~

**Giải thích:**

- Service **không thực thi truy vấn DB trực tiếp**. Nó yêu cầu AccountStore trả Mono, rồi dùng **map** chuyển sang UserDetails.
- **account.passwordHash()** phải là password hash do server lưu và tương thích với PasswordEncoder trong authentication manager. Không nhập raw password trong SQL rồi so chuỗi trong service.
- **grantedAuthorities** phải đến từ nguồn có thẩm quyền. Ví dụ dữ liệu có thể chứa **ROLE_USER**, **ROLE_ADMIN**, **SCOPE_read** theo thiết kế; không lấy role do client gửi trong body/header.
- **disabled(!account.active())** để manager biết account không được phép đăng nhập. Một ứng dụng thực có thể còn lock/expired flags, tenancy, MFA, ban status và các kiểm tra riêng.
- Khi AccountStore trả Mono.empty(), service cũng hoàn tất rỗng. Khi DB trả Mono.error, lỗi được truyền lên theo Reactor, không biến thành một UserDetails mặc định.
- Hạn chế độ dài username trước khi lookup giúp loại đầu vào không hợp lý; phải đồng nhất với chính sách username của app. Nếu username cần chuẩn hóa, dùng một phép chuẩn hóa nhất quán, tránh thay đổi danh tính bất ngờ vì hoa/thường.

Trong project thật, đăng ký **một** bean:

~~~java
@Bean
ReactiveUserDetailsService userDetailsService(AccountStore accountStore) {
    return new DatabaseReactiveUserDetailsService(accountStore);
}
~~~

Đây là **đoạn cấu hình bổ sung**, không độc lập. Cần sửa bean manager ở mục 4 từ nhận **MapReactiveUserDetailsService** sang **ReactiveUserDetailsService**, hoặc dùng một cấu hình khác chỉ có implementation DB. Nếu giữ đồng thời hai service bean mà không có @Qualifier, dependency injection có thể bị ambiguous.

### 6.2. Kết nối với R2DBC — bản đồ kiến trúc

~~~text
WebFlux Basic Authentication
        |
        v
UserDetailsRepositoryReactiveAuthenticationManager
        |
        v
DatabaseReactiveUserDetailsService
        |
        v
AccountStore (reactive adapter)
        |
        +--> DatabaseClient / R2dbcEntityTemplate / R2dbcRepository
        |
        v
R2DBC Driver (non-blocking)
        |
        v
User table: username UNIQUE, password_hash, active, authorities
~~~

Một ví dụ repository Spring Data R2DBC khi dùng entity riêng:

~~~java
// Trích đoạn cho module có Spring Data R2DBC:
// AccountEntity phải có mapping @Table/@Id phù hợp DB schema.
// Đây không phải toàn bộ file/entity chạy độc lập.
public interface AccountRepository
        extends ReactiveCrudRepository<AccountEntity, Long> {

    Mono<AccountEntity> findByUsername(String username);
}
~~~

Bạn cần thêm dependency **spring-boot-starter-data-r2dbc**, driver R2DBC thích hợp, schema và migrations. **ReactiveCrudRepository** thuộc Spring Data, không phải ReactiveUserDetailsService của Spring Security; hai lớp có mục đích khác nhau.

Nếu lưu roles trong nhiều bảng, thiết kế truy vấn không tạo **N+1 blocking calls**, có index phù hợp và mapping authority tin cậy. Khi cần một truy vấn account + authorities, xem xét join/aggregate hoặc pipeline reactive được xác định rõ.

### 6.3. Không gọi block() trong pipeline HTTP

**Cách sai:**

~~~java
@Override
public Mono<UserDetails> findByUsername(String username) {
    AccountRecord record = jdbcRepository.findByUsername(username);
    // JDBC này chặn thread, dù bọc kết quả bằng Mono.just.
    return Mono.just(mapToUserDetails(record));
}
~~~

**Cách cũng sai:**

~~~java
@Override
public Mono<UserDetails> findByUsername(String username) {
    return Mono.just(
            reactiveRepository.findByUsername(username).block());
}
~~~

Lời gọi **block()** đợi kết quả bằng cách chặn thread, phá vỡ ưu điểm của mô hình reactive và có thể bị Reactor chặn trên non-blocking scheduler. Việc dùng **Mono.just** sau khi gọi blocking operation không thay đổi điều đó: I/O đã xảy ra trước khi publisher được trả về.

**Cách đúng với repo reactive:**

~~~java
@Override
public Mono<UserDetails> findByUsername(String username) {
    return reactiveRepository.findByUsername(username)
            .map(this::mapToUserDetails);
}
~~~

Những biến **reactiveRepository** và phương thức **mapToUserDetails** là các thành phần do bạn tự cung cấp; snippet chỉ giải thích pipeline và không phải class hoàn chỉnh. Không thêm **subscribe()** tùy tiện trong service: Spring Security là subscriber của publisher và sẽ quản lý lifecycle. Tự subscribe dễ làm lệch error handling, context, timeout và tạo fire-and-forget không được kiểm soát.

### 6.4. Nếu bắt buộc tích hợp JDBC/LDAP blocking

Trong giai đoạn di trú, có thể cô lập lời gọi chặn thread khỏi event-loop bằng **Schedulers.boundedElastic()**:

~~~java
Mono<UserDetails> lookup =
        Mono.fromCallable(() -> blockingUserDetailsService
                .loadUserByUsername(username))
            .subscribeOn(Schedulers.boundedElastic());
~~~

Đây là **mẫu ranh giới tạm thời** với biến **blockingUserDetailsService** đã có và imports Mono/Schedulers. Nó không biến JDBC thành driver reactive thực, cũng không bảo đảm scale vô hạn: boundedElastic có pool/queue giới hạn. Cần timeout, concurrency bound, connection pool, monitoring và kế hoạch chuyển sang non-blocking driver nếu tải lớn. Không gọi **block()** ngược lại trên request thread.

Nếu dùng hệ LDAP/AD hoặc một identity provider khác, cân nhắc provider/adapter chính thức hỗ trợ giao thức phù hợp. Không tự giả định một API **Mono** đã bảo đảm toàn bộ việc xác thực qua LDAP là non-blocking.

## 7. PasswordEncoder trong reactive authentication

**UserDetailsService chỉ tải hash; manager dùng PasswordEncoder để so sánh.** Với ứng dụng thực:

- Dùng BCrypt, Argon2id, PBKDF2 hoặc encoder phù hợp chính sách và hệ thống hiện tại.
- Không lưu password rõ trong UserDetails/database.
- Không dùng **NoOpPasswordEncoder** cho production; **User.withDefaultPasswordEncoder()** trong một số trang hướng dẫn Spring Security là cách học nhanh, không phải lựa chọn triển khai sản phẩm.
- Khớp encoder lúc tạo hash và lúc verify. Nếu dùng **DelegatingPasswordEncoder**, hash có prefix như **{bcrypt}**; nếu dùng **BCryptPasswordEncoder** trực tiếp, hash BCrypt không cần prefix kiểu Delegating.
- Không băm lại raw password với salt mới rồi so sánh hai hash bằng String.equals: BCrypt có salt. Sử dụng **encoder.matches(raw, storedHash)**.
- Nếu hỗ trợ nâng cấp password hash, dùng cơ chế nâng cấp tương thích **ReactiveUserDetailsPasswordService** và cập nhật DB an toàn, không để password cũ lộ trong log.

Để kiểm tra trực tiếp encoder:

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder();
String hash = encoder.encode("alice-demo-pass");
boolean valid = encoder.matches("alice-demo-pass", hash);
boolean invalid = encoder.matches("wrong", hash);

System.out.println(valid);
System.out.println(invalid);
~~~

Đoạn Java trên được đặt trong method/class có imports phù hợp; **stdout chính xác** cho hai dòng là:

~~~text
true
false
~~~

Không in hash hoặc password thật vào log trong ứng dụng.

**Chi phí BCrypt là CPU-bound.** Dù tra user là non-blocking, so khớp password vẫn tốn CPU và cần giới hạn số request song song. **AbstractUserDetailsReactiveAuthenticationManager** có cơ chế scheduler cho bước kiểm tra password; không nên tự chặn event-loop hoặc tự tạo unbounded scheduler. Áp dụng rate limiting, quan sát độ trễ và chống credential stuffing.

## 8. Tình huống thất bại, bảo mật và độ tin cậy

### 8.1. Không tìm thấy user

**findByUsername** có thể trả Mono.empty(). Trong luồng authentication username/password thông thường, manager sẽ từ chối, ví dụ HTTP Basic trả **401**. Không phản hồi công khai “username không tồn tại” khác với “password sai” nếu điều đó tạo khả năng dò tài khoản.

Cần kiểm tra **timing differences**: tra user không tồn tại có thể nhanh hơn so password BCrypt của user tồn tại. Cân nhắc mitigations theo tải/rủi ro, kết hợp rate limiting và monitoring.

### 8.2. Tài khoản khóa, vô hiệu hoặc hết hạn

**UserDetails** có các cờ accountNonExpired, accountNonLocked, credentialsNonExpired, enabled. Nếu implement custom service, map đầy đủ trạng thái từ nguồn server tin cậy. Không bỏ qua trạng thái chỉ vì password khớp. Kiểm tra các policy như revoke, tenant suspension và không tự tạo quyền khi DB source không hoạt động.

### 8.3. Data source lỗi

Nếu remote DB timeout, không được biến lỗi thành UserDetails mới hoặc trả một Authentication thành công. Để **Mono.error** lan lên tầng xử lý phù hợp, tạo telemetry phân biệt “invalid credentials” và “identity service unavailable”, và quyết định response 401/503 theo API contract. Tránh log raw password và dữ liệu token. Không ghi lại chuỗi SQL chứa credential.

Cẩn trọng với:

~~~java
return accounts.findByUsername(username)
        .onErrorResume(error -> Mono.empty());
~~~

Mẫu trên **che lỗi hệ thống thành tình trạng không có user**, làm khó vận hành và có thể kích hoạt lockout sai cho người dùng. Dù không phải tự động cho phép, nó phá phân biệt sự cố identity source và credential không đúng; chỉ dùng nếu có một chính sách lỗi được phân tích rõ.

### 8.4. Quyền đến từ đâu?

Khi client gửi **role=ADMIN** trong JSON/header, điều đó không phải bằng chứng cấp quyền. **UserDetails.getAuthorities()** phải được dựng từ nguồn có thẩm quyền. Với MapReactiveUserDetailsService, dữ liệu được khởi tạo trong bean phía server. Với DB-backed service, chỉ đọc role/scope đã gắn với subject được xác minh.

Phân biệt: **roles("ADMIN")** tạo **ROLE_ADMIN**; **authorities("SCOPE_read")** giữ nguyên chuỗi. Kiểm tra **hasRole("ADMIN")** so với authority prefix thực để tránh 403 do cấu hình không khớp.

### 8.5. Mật khẩu từ environment của demo vẫn cần quản lý

Biến môi trường tiện cho thực hành nhưng production nên dùng secret manager hoặc hệ thống quản lý credential. Không log biến môi trường, không hard-code password demo vào artifact phát hành, không để H2/test user trở thành tài khoản mặc định truy cập production. Các tài khoản trong Map được tạo lại mỗi khi service restart; nếu mã hóa hash mới mỗi lần chạy, đó là hành vi bình thường với BCrypt, không phải lý do bỏ password encoding.

## 9. Phân biệt với các hệ xác thực reactive khác

| Yêu cầu sản phẩm | Có dùng ReactiveUserDetailsService không? | Thành phần phù hợp |
| --- | --- | --- |
| HTTP Basic username/password với user DB | Thường **có** | UserDetailsRepositoryReactiveAuthenticationManager + custom ReactiveUserDetailsService |
| Form login reactive với username/password | Thường **có** | SecurityWebFilterChain formLogin + reactive manager/service |
| User tĩnh trong test | **Có** | MapReactiveUserDetailsService |
| JWT Bearer token từ IdP | **Không bắt buộc** | oauth2ResourceServer().jwt(), ReactiveJwtDecoder, JWT authority converter |
| Opaque bearer token | **Không bắt buộc** | ReactiveOpaqueTokenIntrospector |
| OAuth2/OIDC login qua nhà cung cấp bên ngoài | **Không nhất thiết** | OAuth2Login authentication components, client registration |
| API key custom | **Không tự động** | Custom AuthenticationWebFilter + ReactiveAuthenticationManager hoặc resolver |
| Lưu credential password cho user | Không trực tiếp | Database account repository + PasswordEncoder + kiểm soát đổi mật khẩu |
| Phân quyền method | Có thể kết hợp | @EnableReactiveMethodSecurity + @PreAuthorize, Reactor Context |

**ReactiveUserDetailsService không phải API chung để xác minh mọi loại token.** Dùng JWT/opaque token với resource server thường không tra user bằng username/password mỗi request, mà xác thực token theo issuer/decoder/introspection. Đừng cưỡng ép JWT vào MapReactiveUserDetailsService hoặc tự tạo user theo JWT claims chưa verify.

## 10. Lỗi thường gặp khi triển khai

**Lỗi 1 — Dùng UserDetailsService của Servlet trong WebFlux rồi mong non-blocking.** Interface Servlet trả UserDetails trực tiếp. **Sửa:** dùng ReactiveUserDetailsService và driver/adapter phù hợp.

**Lỗi 2 — Chỉ tạo MapReactiveUserDetailsService mà không cấu hình filter hoặc manager đúng.** Map giữ dữ liệu user nhưng không tự mở endpoint login. **Sửa:** HTTP Basic/form login trong SecurityWebFilterChain và ReactiveAuthenticationManager phù hợp.

**Lỗi 3 — Tưởng findByUsername kiểm tra password.** Nó chỉ lookup user. **Sửa:** để manager + PasswordEncoder thực hiện xác minh và kiểm tra account flags.

**Lỗi 4 — Trả null khi user không tồn tại.** Reactor không dùng null làm kết quả từ publisher. **Sửa:** Mono.empty() hoặc contract lỗi phù hợp.

**Lỗi 5 — Đặt block() trong findByUsername.** Event-loop bị chặn. **Sửa:** dùng reactive data access hoặc cô lập blocking adapter rõ ràng.

**Lỗi 6 — Dùng Mono.just(blockingDatabaseCall()).** Lời gọi blocking đã chạy trước khi Mono được tạo. **Sửa:** loại bỏ I/O blocking; nếu di trú phải dùng Mono.fromCallable + boundedElastic với giới hạn.

**Lỗi 7 — Dùng password dạng {noop} trong môi trường thật.** Raw password không được băm. **Sửa:** BCrypt/Argon2id/DelegatingPasswordEncoder theo chính sách.

**Lỗi 8 — Mặc định roles("ADMIN") giống authorities("ADMIN").** Thực tế **roles** thêm prefix ROLE_. **Sửa:** thống nhất cấu hình GrantedAuthority với hasRole/hasAuthority.

**Lỗi 9 — Serialize toàn bộ UserDetails thành JSON.** UserDetails thường chứa password hash, account metadata và authorities. **Sửa:** expose DTO tối thiểu sau xác thực.

**Lỗi 10 — Kết hợp starter-web và starter-webflux không kiểm tra application type.** Ứng dụng có thể chạy MVC/Servlet thay vì WebFlux, làm chain reactive không áp dụng. **Sửa:** chọn đúng starter và kiểm tra ứng dụng chạy trên stack nào.

**Lỗi 11 — Kiểm thử chỉ với @WithMockUser.** Bỏ qua bước so credential. **Sửa:** WebTestClient gửi Basic auth thật, test 401/403/200.

**Lỗi 12 — Dựa vào Map như database production.** User state không bền vững/không đồng bộ cluster. **Sửa:** reactive repository có uniqueness, account flags, caching/TTL và revoke được thiết kế.

## 11. Checklist khi chuyển ứng dụng reactive sang production

- [ ] Ứng dụng thực sự dùng **Spring WebFlux** và **SecurityWebFilterChain**, không vô tình là Servlet.
- [ ] ReactiveUserDetailsService là **một implementation rõ ràng** được manager sử dụng, không có bean ambiguous.
- [ ] findByUsername luôn trả **Mono<UserDetails>**, Mono.empty hoặc Mono.error; không trả null.
- [ ] Data access thực sự non-blocking; không block()/JDBC/JPA trực tiếp trên event-loop.
- [ ] UserDetails chứa encoded password và trạng thái account hợp lệ, không chứa raw secret.
- [ ] PasswordEncoder tương thích hash hiện có, có kế hoạch upgrade/migration.
- [ ] Roles/authorities lấy từ nguồn server tin cậy, không tin dữ liệu role ở request.
- [ ] Không phát UserDetails chứa password hash qua controller hoặc logs.
- [ ] Có giới hạn thử sai/rate limiting, telemetry timeout, credential stuffing và user enumeration.
- [ ] Mất DB/identity source → fail closed, không có fallback tạo user tự động.
- [ ] WebTestClient test credential đúng, sai, thiếu, account locked/disabled và role không đủ.
- [ ] StepVerifier test Mono phát user đúng, Mono.empty và Mono.error ở service/adapter.
- [ ] Dùng HTTPS/TLS thật khi truyền Basic credentials, không nhầm Base64 thành mã hóa.
- [ ] Khi dùng OAuth2/JWT, chọn thành phần reactive resource-server riêng thay vì nhồi vào user lookup.
- [ ] Có chính sách session/CSRF phù hợp với browser/cookie; không tắt bảo vệ không lý do.
- [ ] Với cluster, datasource và account state nhất quán; Map-only chỉ dùng nếu chấp nhận giới hạn.

## 12. Câu hỏi tự kiểm tra

**1. ReactiveUserDetailsService trả dữ liệu gì?** Một **Mono<UserDetails>**. Nó không tự trả Authentication đã xác thực và không tự xác minh mật khẩu.

**2. Khi nào dùng MapReactiveUserDetailsService?** Khi cần kho user trong memory cho demo, test hoặc cấu hình tĩnh được quản trị rõ; không nên mặc định dùng cho hệ user sản phẩm có thay đổi và cần đồng bộ/persistence.

**3. Nếu username không tồn tại, trả Mono.just(null) được không?** Không. Reactor không cho null item; dùng Mono.empty() hoặc hợp đồng lỗi phù hợp.

**4. Tại sao Mono.just(jdbcRepository.findByUsername(name)) không phải reactive?** JDBC call chạy đồng bộ trước khi Mono được tạo; nó vẫn chặn thread.

**5. User đã được tìm thấy, nhưng password sai, có được đăng nhập không?** Không. Manager phải dùng PasswordEncoder.matches, kiểm tra account state và chỉ phát Authentication thành công khi đạt yêu cầu.

**6. Tại sao endpoint /api/admin trả 403 cho alice dù /api/me trả 200?** Alice đã xác thực bằng password đúng nhưng chỉ có ROLE_READER, không có ROLE_ADMIN.

**7. Trong WebFlux, SecurityContext được truy cập như thế nào?** Qua **ReactiveSecurityContextHolder/Reactor Context** hoặc các tiện ích reactive của Spring Security; không giả định một ThreadLocal tồn tại đúng xuyên các scheduler.

**8. MapReactiveUserDetailsService có thể tự hoạt động với JWT bearer token không?** Không. JWT cần bộ giải mã/xác minh token và authentication manager/filter tương ứng; user lookup bằng username/password là cơ chế khác.

## 13. Tài liệu chính thức

- [Spring Security 6.5 — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html): @EnableWebFluxSecurity, SecurityWebFilterChain, MapReactiveUserDetailsService và DSL.
- [ReactiveUserDetailsService Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/ReactiveUserDetailsService.html): hợp đồng findByUsername và Mono<UserDetails>.
- [MapReactiveUserDetailsService Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/MapReactiveUserDetailsService.html): constructor nhận Map/Collection/varargs, findByUsername và updatePassword.
- [UserDetailsRepositoryReactiveAuthenticationManager Javadoc](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/authentication/UserDetailsRepositoryReactiveAuthenticationManager.html): reactive password authentication manager.
- [AbstractUserDetailsReactiveAuthenticationManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AbstractUserDetailsReactiveAuthenticationManager.html): PasswordEncoder, scheduler, account checks và password upgrade.
- [Spring Security 6.5 — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html): @EnableReactiveMethodSecurity, Reactor Context và ví dụ MapReactiveUserDetailsService.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): @SpringBootTest(RANDOM_PORT), WebTestClient.
- [Project Reactor — Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): Mono.just, Mono.empty, Mono.error, map và subscribeOn.
