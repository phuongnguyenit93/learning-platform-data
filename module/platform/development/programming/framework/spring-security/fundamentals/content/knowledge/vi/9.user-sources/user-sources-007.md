# ReactiveUserDetailsService và MapReactiveUserDetailsService trong Spring WebFlux

Khi ứng dụng Spring Security chạy trên **Spring WebFlux**, việc tìm tài khoản cần phù hợp với luồng xử lý reactive. Thay vì hợp đồng đồng bộ **UserDetailsService.loadUserByUsername(String)**, Spring Security cung cấp **ReactiveUserDetailsService.findByUsername(String)** trả về **Mono<UserDetails>**. Để bắt đầu nhanh, framework có **MapReactiveUserDetailsService**, một implementation lưu các UserDetails trong Map, hữu ích cho bài học, demo và test. Với hệ thống thực, bạn có thể thay nó bằng một ReactiveUserDetailsService truy vấn dữ liệu qua nguồn I/O nonblocking như R2DBC.

Bài thuộc nhóm **Nguồn người dùng** của Spring Security fundamentals. Mục tiêu là hiểu hợp đồng, quan hệ với cơ chế xác thực, cách cấu hình WebFlux, tính chất của Reactor, các bẫy blocking và một ví dụ **Java 17+, Spring Boot 3.3.6, Spring Security 6.x** đầy đủ. Ví dụ dùng **HTTP Basic và tài khoản giả trên localhost** để tự kiểm bằng WebTestClient; production phải chọn nguồn danh tính, HTTPS, bí mật, giới hạn truy cập và bản vá bảo mật phù hợp.

## 1. Vì sao WebFlux có một hợp đồng tra cứu người dùng riêng?

Spring MVC thường xử lý request trong mô hình Servlet, với API UserDetailsService:

~~~java
// Chữ ký đồng bộ của Servlet-oriented UserDetailsService.
// Đây là mảnh mô tả, không phải file Java độc lập.
UserDetails loadUserByUsername(String username)
    throws UsernameNotFoundException;
~~~

Trong WebFlux, nhiều bước I/O được biểu diễn bằng publisher từ Project Reactor. Hợp đồng reactive:

~~~java
// Chữ ký của org.springframework.security.core.userdetails.ReactiveUserDetailsService.
// Đây là mảnh mô tả, không phải file Java độc lập.
Mono<UserDetails> findByUsername(String username);
~~~

Sự khác nhau không nằm ở đối tượng **UserDetails**: cả hai đều có username, password hash, GrantedAuthority và trạng thái account. Khác biệt là **cách biểu diễn quá trình lấy dữ liệu**:

| Tiêu chí | UserDetailsService | ReactiveUserDetailsService |
| --- | --- | --- |
| Phương thức | loadUserByUsername(String) | findByUsername(String) |
| Giá trị trả về | UserDetails trực tiếp | Mono<UserDetails> |
| I/O hợp lý | Đồng bộ; thường JDBC/JPA hoặc nguồn blocking | Nguồn nonblocking/R2DBC hoặc publisher có chiến lược lập lịch phù hợp |
| Bối cảnh điển hình | Spring MVC với DaoAuthenticationProvider | Spring WebFlux với UserDetailsRepositoryReactiveAuthenticationManager |
| Không tìm thấy user | Thường ném UsernameNotFoundException | Thể hiện qua tín hiệu của Mono theo implementation và lớp manager xử lý |
| Thông tin user | UserDetails gồm principal, hash, quyền, account flags | **Cùng interface UserDetails** |
| Kiểm password | PasswordEncoder ở provider/manager | PasswordEncoder ở reactive authentication manager |
| Bảo vệ HTTP | HttpSecurity + SecurityFilterChain | ServerHttpSecurity + SecurityWebFilterChain |

**Mono<UserDetails> không tự làm database nonblocking.** Nếu implementation gọi JDBC hoặc HTTP client đồng bộ trên event-loop rồi bọc Mono.just(...), event-loop vẫn bị chặn. Chuyển sang WebFlux cần xem toàn bộ đường gọi I/O, không chỉ đổi kiểu trả về của method.

Một ứng dụng Spring MVC có thể dùng **WebClient** để gọi dịch vụ khác mà vẫn là Servlet server. Trong trường hợp đó, cấu hình HTTP bảo mật vẫn dùng **HttpSecurity/SecurityFilterChain**, không tự đổi thành ServerHttpSecurity chỉ vì đã đưa dependency WebFlux vào classpath.

## 2. UserDetails vẫn là hợp đồng chung

Trong cả hai stack, **UserDetails** là interface của Spring Security Core, thường chứa:

~~~java
// Mảnh hợp đồng thu gọn, không dùng thay file thư viện.
String getUsername();
String getPassword();
Collection<? extends GrantedAuthority> getAuthorities();
boolean isEnabled();
boolean isAccountNonLocked();
boolean isAccountNonExpired();
boolean isCredentialsNonExpired();
~~~

Trong user store:

- **getUsername()** xác định tên dùng cho authentication lookup.
- **getPassword()** chứa thông tin password đã lưu, thông thường là **hash** phù hợp với PasswordEncoder. Không lưu plain text.
- **getAuthorities()** chứa các authority tin cậy như ROLE_USER, ROLE_ADMIN hoặc orders:read; không lấy quyền trực tiếp từ header client.
- **isEnabled()** báo tài khoản được kích hoạt.
- **isAccountNonLocked()**, **isAccountNonExpired()**, **isCredentialsNonExpired()** là ba cờ có ý nghĩa phủ định: trạng thái bình thường thường phải **true**.

Ví dụ một user đang hoạt động:

~~~text
UserDetails
  username                  = alice
  password                  = BCrypt hash (không đưa vào JSON)
  authorities               = [ROLE_USER, orders:read]
  isEnabled                 = true
  isAccountNonLocked        = true
  isAccountNonExpired       = true
  isCredentialsNonExpired   = true
~~~

**ReactiveUserDetailsService chỉ tìm UserDetails**. Nó không tự nhận HTTP request, không tự so sánh raw password, không tạo SecurityContext hay quyết định role có được phép gọi endpoint. Những nhiệm vụ đó thuộc authentication filter, authentication manager và authorization layer.

Cần lưu ý: **isAccountNonLocked=false** nghĩa là *đang bị khóa*; **isAccountNonExpired=false** nghĩa là *tài khoản đã hết hạn*. Khi ánh xạ từ entity có trường locked=true hoặc expired=true, phải đảo boolean cho đúng.

## 3. Mono<UserDetails>: hiểu kết quả, lỗi và vòng đời

Publisher Mono có thể:

1. **Phát ra một UserDetails** rồi hoàn tất khi tìm thấy.
2. **Hoàn tất không có phần tử** khi nguồn không cung cấp user, nếu implementation chọn cách thể hiện đó.
3. **Phát lỗi** khi có một điều kiện không thành công, ví dụ lỗi nguồn dữ liệu hoặc implementation báo username không tìm thấy bằng exception.

Hợp đồng findByUsername trả **Mono<UserDetails>**, tức bản thân giá trị trả về không được null. Không viết **return null** hoặc **return Mono.just(null)**: Mono không dùng null làm phần tử hợp lệ. Tình huống user không có cần được xử lý rõ bằng Reactor và theo contract của authentication manager.

Ví dụ tra cứu từ một repository reactive, chỉ để minh họa:

~~~java
// Mảnh minh họa. reactiveAccountRepository và phương thức tìm
// được định nghĩa riêng trong project dùng R2DBC hoặc nguồn reactive.
@Override
public Mono<UserDetails> findByUsername(String username) {
    return reactiveAccountRepository.findByUsername(username)
        .map(row -> User.withUsername(row.username())
            .password(row.passwordHash())
            .authorities(row.authorities())
            .disabled(!row.enabled())
            .accountLocked(row.locked())
            .build());
}
~~~

Ở đây **findByUsername(...)** của repository đã phải trả một publisher thực sự, không chạy JDBC blocking. **map(...)** chuyển AccountRow thành UserDetails; khi repository không phát user, map không chạy. Khi repository phát lỗi, lỗi được chuyển tiếp theo luồng trừ khi bạn cố ý xử lý.

**Không dùng onErrorResume để trả một tài khoản mặc định có quyền cao.** Lỗi database cần làm authentication thất bại có kiểm soát, không biến thành một danh tính giả được phép truy cập.

### 3.1. Lazy execution và subscription

Thông thường nhiều publisher Reactor là cold: dựng pipeline chưa bắt buộc thực thi truy vấn ngay; framework subscribe khi request cần kết quả. Tránh tự gọi **subscribe()** trong ReactiveUserDetailsService, vì khi đó bạn tách công việc xác thực ra khỏi lifecycle request và bỏ mất cơ chế propagation, error handling, timeout.

Trong controller/service, hãy trả Mono cho framework hoặc ghép bằng các toán tử như **map**, **flatMap**, **switchIfEmpty**. Không gọi **block()** trong WebFilter hoặc Controller chạy trên event-loop.

### 3.2. Sai lầm Mono.just với nguồn blocking

~~~java
// Anti-pattern: JDBC chạy ngay trên thread hiện tại.
return Mono.just(jdbcUserRepository.findUser(username));
~~~

Khi phương thức jdbcUserRepository.findUser(...) chạy, JDBC đã chặn thread **trước** khi Mono.just được tạo. Cách an toàn hơn về lâu dài là dùng database driver và repository reactive phù hợp; khi bắt buộc dùng API blocking, cần cô lập bằng scheduler và giới hạn tải:

~~~java
// Mảnh minh họa, dùng khi nguồn bắt buộc blocking.
// Có thể cần xử lý null, exception, timeout và giới hạn truy cập thêm.
return Mono.fromCallable(() -> jdbcUserRepository.findUser(username))
    .subscribeOn(Schedulers.boundedElastic());
~~~

Ví dụ này cần import **reactor.core.scheduler.Schedulers** và publisher **Mono**. BoundedElastic giúp tránh chặn event-loop khi đợi I/O blocking; nó không làm JDBC nonblocking, không tạo pool vô hạn và không bảo đảm hiệu năng tốt nếu tất cả truy vấn vẫn blocking. Với password hash CPU-intensive, cần quan sát scheduler/CPU và giới hạn đồng thời theo cơ chế manager thực sự sử dụng.

## 4. MapReactiveUserDetailsService là gì?

**org.springframework.security.core.userdetails.MapReactiveUserDetailsService** là implementation có sẵn của **ReactiveUserDetailsService**, dựa trên Map lưu UserDetails. Lớp này còn implement **ReactiveUserDetailsPasswordService**, có phương thức updatePassword(...) để cập nhật password theo contract của implementation.

Những cách tạo thường gặp:

~~~java
// Mảnh code dùng trong nơi đã import MapReactiveUserDetailsService
// và đã tạo trước các biến alice, bob là UserDetails.
MapReactiveUserDetailsService first =
    new MapReactiveUserDetailsService(alice, bob);

MapReactiveUserDetailsService second =
    new MapReactiveUserDetailsService(List.of(alice, bob));

MapReactiveUserDetailsService third =
    new MapReactiveUserDetailsService(
        Map.of(alice.getUsername(), alice, bob.getUsername(), bob)
    );
~~~

**Đặc điểm:**

- Nguồn user nằm trong bộ nhớ của tiến trình đang chạy.
- Phù hợp ví dụ nhỏ, test, prototype hoặc tài khoản thử nghiệm tạm thời.
- findByUsername(...) trả Mono<UserDetails>, cùng contract với service custom.
- Tính năng updatePassword(...) có thể thay đổi dữ liệu user đang lưu; cần dùng riêng trong test hoặc một flow quản lý password đã thiết kế.
- Không cung cấp sẵn database bền vững, replication, MFA, reset password, rotation, audit hay account provisioning production.
- Nếu ứng dụng có nhiều instance, Map của instance A **không tự đồng bộ** sang instance B.
- Cần kiểm rõ case sensitivity, uniqueness của username, thời gian sống dữ liệu và cách tái tạo account khi restart.

### 4.1. Đừng nhầm tên class hoặc package

~~~java
// Spring Security Core:
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.UserDetails;
~~~

Không có lý do viết một class mang tên **InMemoryReactiveUserDetailsManager** rồi mặc định đó là API có sẵn. Đối với Servlet, lớp quen thuộc là **InMemoryUserDetailsManager**; đối với reactive, dùng **MapReactiveUserDetailsService**.

### 4.2. Khi nào không nên dùng MapReactiveUserDetailsService?

Không dùng nó làm kho tài khoản chính của sản phẩm thật nếu hệ thống cần cập nhật account qua nhiều server, đồng bộ quyền, audit, password reset, account lockout hoặc nguồn danh tính tập trung. Dữ liệu nằm trong Map không thay thế identity service/DB, dù API tra cứu mang tên “reactive”.

Nó cũng không làm OAuth2/OIDC/JWT tự xuất hiện. Một Resource Server giải mã/kiểm access token theo cơ chế của chính nó; có thể không dùng ReactiveUserDetailsService cho mỗi request Bearer.

## 5. ReactiveUserDetailsService nằm ở đâu trong luồng xác thực?

Với HTTP Basic trong WebFlux:

~~~mermaid
flowchart TD
    A["Client GET /api/me + Authorization: Basic ..."] --> B["Spring Security WebFilter chain"]
    B --> C["HTTP Basic authentication filter"]
    C --> D["UsernamePasswordAuthenticationToken chưa xác thực"]
    D --> E["ReactiveAuthenticationManager"]
    E --> F["UserDetailsRepositoryReactiveAuthenticationManager"]
    F --> G["ReactiveUserDetailsService.findByUsername()"]
    G --> H["Mono<UserDetails>"]
    H --> I["PasswordEncoder.matches + account checks"]
    I --> J{"Đăng nhập hợp lệ?"}
    J -- "Có" --> K["Authentication được xác thực"]
    J -- "Không" --> L["401 / phản hồi theo entry point"]
    K --> M["Reactor SecurityContext"]
    M --> N["authorizeExchange và WebFlux Controller"]
~~~

Các bước được rút gọn để học; vị trí WebFilter và handler có thể phụ thuộc cấu hình. **UserDetailsRepositoryReactiveAuthenticationManager** là implementation ReactiveAuthenticationManager dùng ReactiveUserDetailsService để lấy account và kiểm username/password.

Phân chia trách nhiệm:

| Thành phần | Công việc |
| --- | --- |
| Authentication WebFilter cho HTTP Basic | Đọc HTTP Authorization, tạo authentication request, gọi manager phù hợp. |
| ReactiveAuthenticationManager | Nhận Authentication, trả Mono<Authentication> hoặc tín hiệu lỗi/không xác định theo hợp đồng. |
| UserDetailsRepositoryReactiveAuthenticationManager | Dùng ReactiveUserDetailsService, PasswordEncoder và các account checks cho xác thực username/password. |
| ReactiveUserDetailsService | Tìm UserDetails theo username; không trực tiếp xác thực password. |
| MapReactiveUserDetailsService | Một implementation tra user trong Map; hữu ích demo và test. |
| PasswordEncoder | Hash/so khớp password; vẫn là interface đồng bộ, cần tính chi phí CPU. |
| SecurityWebFilterChain + ServerHttpSecurity | Áp dụng cơ chế authn/authz WebFlux, CSRF, headers và các filter liên quan. |
| ReactiveSecurityContextHolder | Truy cập SecurityContext trong Reactor Context ở các đoạn reactive thích hợp. |

**Đừng dùng DaoAuthenticationProvider + HttpSecurity làm cấu hình chính cho WebFlux server.** Chúng thuộc stack Servlet. Trong WebFlux, bộ tương ứng cho username/password gồm ReactiveAuthenticationManager và ServerHttpSecurity.

### 5.1. Username/password và Bearer token là hai cơ chế khác nhau

Đối với OAuth2 Resource Server, một access token có thể được kiểm bằng **ReactiveJwtDecoder** hoặc introspection phù hợp. Trong đường đó, framework không mặc định gọi MapReactiveUserDetailsService để tải user và kiểm password. Đừng kết luận rằng UserDetails bị disable trong Map sẽ tự thu hồi mọi JWT còn hiệu lực; token validation/revocation là chủ đề riêng.

## 6. Dự án thực hành: Spring Boot WebFlux + MapReactiveUserDetailsService

Ứng dụng mẫu có bốn endpoint:

- **GET /api/public**: không cần xác thực.
- **GET /api/me**: phải xác thực, trả username từ principal.
- **GET /api/orders**: phải có authority **orders:read**.
- **GET /api/admin**: phải có role **ADMIN** (authority ROLE_ADMIN).

Để thấy cả account states, tạo các user:

| Username | Password thử | Authorities | Trạng thái |
| --- | --- | --- | --- |
| alice | demo-password | ROLE_USER, orders:read | Hoạt động. |
| viewer | demo-password | ROLE_USER | Hoạt động; không có orders:read. |
| admin | demo-password | ROLE_ADMIN, orders:read | Hoạt động; được gọi /api/admin. |
| locked | demo-password | ROLE_USER | Đã khóa, không được đăng nhập. |
| disabled | demo-password | ROLE_USER | Đã vô hiệu hóa, không được đăng nhập. |
| expired | demo-password | ROLE_USER | Account hết hạn. |
| credentials-expired | demo-password | ROLE_USER | Credential hết hạn. |

Mật khẩu trên là dữ liệu giả cho localhost. Không đưa account hoặc password demo vào production. **PasswordEncoder** sẽ hash mật khẩu ngay khi tạo user ở startup.

### 6.1. Yêu cầu và cấu trúc file

- **JDK 17+**, Maven 3.9+ hoặc Maven Wrapper.
- Port **8080** còn trống.
- **curl.exe** trên PowerShell, hoặc curl trên Linux/macOS.

~~~text
webflux-users-demo/
├── pom.xml
└── src
    ├── main/java/com/example/reactiveusers
    │   ├── ReactiveUsersApplication.java
    │   ├── ApiController.java
    │   └── SecurityConfig.java
    └── test/java/com/example/reactiveusers
        └── ReactiveUsersTests.java
~~~

Tất cả file Java dùng package **com.example.reactiveusers**. Không có spring-boot-starter-web vì project phải chạy **WebFlux server**, không chuyển ngầm về Spring MVC.

### 6.2. pom.xml

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
    <artifactId>webflux-users-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

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
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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

**Vai trò dependency:**

- spring-boot-starter-webflux: Spring WebFlux, Reactor và server HTTP reactive.
- spring-boot-starter-security: các hợp đồng UserDetails, reactive authentication và security WebFilter.
- spring-boot-starter-test: JUnit 5, Spring Boot Test, WebTestClient và tiện ích test.
- spring-security-test: hỗ trợ mock authentication và tích hợp Security WebTestClient khi cần.
- reactor-test: StepVerifier để kiểm Mono/Flux trực tiếp.

### 6.3. ReactiveUsersApplication.java

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

Class main ở package gốc để Spring Boot quét Controller và Configuration cùng package. Không hard-code một profile “dev mở hết quyền” trong hàm main.

### 6.4. SecurityConfig.java — tạo MapReactiveUserDetailsService

~~~java
package com.example.reactiveusers;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
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
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-password"))
            .authorities("ROLE_USER", "orders:read")
            .build();

        UserDetails viewer = User.withUsername("viewer")
            .password(encoder.encode("demo-password"))
            .authorities("ROLE_USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("demo-password"))
            .authorities("ROLE_ADMIN", "orders:read")
            .build();

        UserDetails locked = User.withUsername("locked")
            .password(encoder.encode("demo-password"))
            .authorities("ROLE_USER")
            .accountLocked(true)
            .build();

        UserDetails disabled = User.withUsername("disabled")
            .password(encoder.encode("demo-password"))
            .authorities("ROLE_USER")
            .disabled(true)
            .build();

        UserDetails expired = User.withUsername("expired")
            .password(encoder.encode("demo-password"))
            .authorities("ROLE_USER")
            .accountExpired(true)
            .build();

        UserDetails credentialsExpired =
            User.withUsername("credentials-expired")
                .password(encoder.encode("demo-password"))
                .authorities("ROLE_USER")
                .credentialsExpired(true)
                .build();

        return new MapReactiveUserDetailsService(
            alice, viewer, admin, locked, disabled, expired,
            credentialsExpired
        );
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            MapReactiveUserDetailsService users,
            PasswordEncoder encoder) {

        UserDetailsRepositoryReactiveAuthenticationManager manager =
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
                .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/admin").hasRole("ADMIN")
                .pathMatchers(HttpMethod.GET, "/api/orders")
                    .hasAuthority("orders:read")
                .pathMatchers(HttpMethod.GET, "/api/me").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

**Giải thích cấu hình:**

1. **MapReactiveUserDetailsService** quản lý UserDetails demo và cung cấp phương thức **findByUsername(...)** theo ReactiveUserDetailsService.
2. **BCryptPasswordEncoder** tạo hash từ mật khẩu mẫu. Không lưu raw password trong UserDetails.
3. **UserDetailsRepositoryReactiveAuthenticationManager** tra user qua service, so khớp password với encoder và áp dụng các kiểm tra trạng thái tài khoản.
4. **http.authenticationManager(manager)** đưa manager vào WebFlux security DSL. Cấu hình tường minh tránh phụ thuộc suy đoán việc Spring Boot tự chọn manager nào nếu hệ thống có nhiều provider.
5. **ServerHttpSecurity** và **SecurityWebFilterChain** thuộc stack reactive. Đừng thay bằng HttpSecurity/SecurityFilterChain của Servlet.
6. **authorizeExchange** kiểm quyền theo path và HTTP method. /api/public có chủ đích là public; /api/me cần authenticated; /api/orders cần authority orders:read; /api/admin cần ROLE_ADMIN.
7. **anyExchange().denyAll()** từ chối các request chưa khớp quy tắc. Điều này bao gồm các method mới trên path cũ.
8. **httpBasic** cho phép curl gửi credential. Mẫu này chỉ dùng GET; **không tắt CSRF mặc định**.
9. **User.withUsername().accountLocked(true)** tạo UserDetails với isAccountNonLocked=false; disabled(true), accountExpired(true), credentialsExpired(true) cũng đảo sang giá trị không hợp lệ tương ứng.
10. HTTP Basic **không mã hóa** username/password khi truyền trên mạng: Base64 có thể bị giải mã; kết nối thật phải dùng HTTPS. Không dùng tài khoản demo ngoài localhost.

Với các dòng Spring Security khác 6.3.x, cần xem API constructor và setPasswordEncoder tương ứng trong dependency đang dùng. Không mix nhiều version Spring Security rời nhau chỉ để compile một đoạn code.

### 6.5. ApiController.java

~~~java
package com.example.reactiveusers;

import java.security.Principal;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public Mono<Map<String, String>> publicEndpoint() {
        return Mono.just(Map.of("message", "public"));
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(Mono<Principal> principal) {
        return principal.map(
            p -> Map.of("username", p.getName())
        );
    }

    @GetMapping("/api/orders")
    public Mono<Map<String, String>> orders() {
        return Mono.just(Map.of("message", "orders-read"));
    }

    @GetMapping("/api/admin")
    public Mono<Map<String, String>> admin() {
        return Mono.just(Map.of("message", "admin"));
    }
}
~~~

Các method trả **Mono** cho WebFlux. Ở /api/me, tham số **Mono<Principal>** được WebFlux hỗ trợ; Principal đại diện danh tính đã được security thiết lập. Không tự lấy username từ query parameter rồi coi đó là người gọi.

**Controller không kiểm mật khẩu hoặc role bằng if**: SecurityWebFilterChain đã làm kiểm soát URL trước khi handler được gọi. Một ứng dụng thật vẫn cần Service/domain kiểm **quyền trên object**, ví dụ tenant/owner của từng đơn, vì orders:read chỉ là authority theo loại thao tác.

### 6.6. Khởi chạy

Tại thư mục chứa pom.xml:

~~~bash
mvn spring-boot:run
~~~

Nếu port mặc định còn trống, ứng dụng lắng nghe tại:

~~~text
http://localhost:8080
~~~

Trên PowerShell dùng **curl.exe**, Linux/macOS dùng **curl**.

~~~powershell
curl.exe -i http://localhost:8080/api/public
curl.exe -i http://localhost:8080/api/me
curl.exe -i -u alice:demo-password http://localhost:8080/api/me
curl.exe -i -u alice:demo-password http://localhost:8080/api/orders
curl.exe -i -u viewer:demo-password http://localhost:8080/api/orders
curl.exe -i -u alice:demo-password http://localhost:8080/api/admin
curl.exe -i -u admin:demo-password http://localhost:8080/api/admin
curl.exe -i -u locked:demo-password http://localhost:8080/api/me
~~~

**Kết quả HTTP dự kiến:**

| Request | Status | Lý do |
| --- | --- | --- |
| GET /api/public, không credential | 200 | Có rule permitAll(). |
| GET /api/me, không credential | 401 | Cần xác thực qua HTTP Basic. |
| GET /api/me, alice đúng password | 200 | Account hoạt động, manager xác thực thành công. |
| GET /api/orders, alice | 200 | Có orders:read. |
| GET /api/orders, viewer | 403 | Có ROLE_USER nhưng thiếu orders:read. |
| GET /api/admin, alice | 403 | Thiếu ROLE_ADMIN. |
| GET /api/admin, admin | 200 | Có ROLE_ADMIN. |
| GET /api/me, locked | 401 | Account bị khóa dù password đúng. |
| GET /api/me, password sai | 401 | Credential không hợp lệ. |

Body JSON khi thành công:

~~~json
{"username":"alice"}
~~~

và:

~~~json
{"message":"orders-read"}
~~~

Header như WWW-Authenticate hoặc các security headers phụ thuộc cấu hình; không cố định toàn bộ response byte-for-byte. Nếu bạn thử public URL **với Authorization header sai**, filter xác thực có thể trả lỗi ngay cả khi authorization rule là permitAll; hãy dùng request không credential để kiểm public đúng nghĩa.

### 6.7. MapReactiveUserDetailsService có tự tạo HTTP session không?

**Không.** Service chỉ biết tìm UserDetails từ Map. HTTP Basic, form login, Bearer token và security context persistence là công việc của filter chain và cơ chế authn khác. Với HTTP Basic, client thường gửi credential ở mỗi request. Không xem Mono hoặc MapReactiveUserDetailsService là bằng chứng hệ thống tự động stateless; WebFlux vẫn có WebSession và các repository context tương ứng khi cấu hình.

## 7. Kiểm thử ReactiveUserDetailsService bằng StepVerifier

**StepVerifier** trong reactor-test cho phép kiểm thử publisher mà không cần gọi block() trong code nghiệp vụ. Ví dụ kiểm trực tiếp:

~~~java
StepVerifier.create(users.findByUsername("alice"))
    .assertNext(user -> {
        assertThat(user.getUsername()).isEqualTo("alice");
        assertThat(user.isEnabled()).isTrue();
        assertThat(user.isAccountNonLocked()).isTrue();
        assertThat(user.getAuthorities())
            .extracting(GrantedAuthority::getAuthority)
            .contains("ROLE_USER", "orders:read");
    })
    .verifyComplete();
~~~

Đây là một mảnh test hợp lệ khi đặt trong class JUnit, có Bean users và import StepVerifier, AssertJ, GrantedAuthority. Nó chứng minh contract **Mono<UserDetails>** và dữ liệu cơ bản được nạp. Nó chưa chứng minh password đúng, vì findByUsername không có tham số password và không thực hiện authentication.

Đối với tài khoản bị khóa, test dữ liệu có thể thấy **isAccountNonLocked=false**; muốn chứng minh manager từ chối password đúng, phải test **ReactiveAuthenticationManager** hoặc HTTP Basic ở tầng WebTestClient.

## 8. Bộ test hoàn chỉnh: service, manager và WebTestClient

Tạo **src/test/java/com/example/reactiveusers/ReactiveUsersTests.java**:

~~~java
package com.example.reactiveusers;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveUsersTests {

    @Autowired
    MapReactiveUserDetailsService users;

    @Autowired
    ReactiveAuthenticationManager manager;

    @Autowired
    PasswordEncoder encoder;

    @Autowired
    WebTestClient client;

    @Test
    void findUserReturnsReactiveUserDetails() {
        StepVerifier.create(users.findByUsername("alice"))
            .assertNext(user -> {
                assertThat(user.getUsername()).isEqualTo("alice");
                assertThat(user.getAuthorities())
                    .extracting(GrantedAuthority::getAuthority)
                    .contains("ROLE_USER", "orders:read");
                assertThat(user.isEnabled()).isTrue();
                assertThat(user.isAccountNonLocked()).isTrue();
                assertThat(user.isAccountNonExpired()).isTrue();
                assertThat(user.isCredentialsNonExpired()).isTrue();
            })
            .verifyComplete();
    }

    @Test
    void passwordIsEncodedAndMatchesOnlyCorrectRawPassword() {
        StepVerifier.create(users.findByUsername("alice"))
            .assertNext(user -> {
                assertThat(user.getPassword())
                    .isNotEqualTo("demo-password");
                assertThat(encoder.matches(
                    "demo-password", user.getPassword())).isTrue();
                assertThat(encoder.matches(
                    "wrong-password", user.getPassword())).isFalse();
            })
            .verifyComplete();
    }

    @Test
    void lockedFlagIsReflectedInUserDetails() {
        StepVerifier.create(users.findByUsername("locked"))
            .assertNext(user -> {
                assertThat(user.isEnabled()).isTrue();
                assertThat(user.isAccountNonLocked()).isFalse();
            })
            .verifyComplete();
    }

    @Test
    void disabledFlagIsReflectedInUserDetails() {
        StepVerifier.create(users.findByUsername("disabled"))
            .assertNext(user ->
                assertThat(user.isEnabled()).isFalse())
            .verifyComplete();
    }

    @Test
    void expiredFlagIsReflectedInUserDetails() {
        StepVerifier.create(users.findByUsername("expired"))
            .assertNext(user ->
                assertThat(user.isAccountNonExpired()).isFalse())
            .verifyComplete();
    }

    @Test
    void credentialsExpiredFlagIsReflectedInUserDetails() {
        StepVerifier.create(users.findByUsername("credentials-expired"))
            .assertNext(user ->
                assertThat(user.isCredentialsNonExpired()).isFalse())
            .verifyComplete();
    }

    @Test
    void authenticationManagerAcceptsValidCredentials() {
        var request = UsernamePasswordAuthenticationToken
            .unauthenticated("alice", "demo-password");

        StepVerifier.create(manager.authenticate(request))
            .assertNext(authentication -> {
                assertThat(authentication.isAuthenticated()).isTrue();
                assertThat(authentication.getName()).isEqualTo("alice");
                assertThat(authentication.getAuthorities())
                    .extracting(GrantedAuthority::getAuthority)
                    .contains("ROLE_USER", "orders:read");
            })
            .verifyComplete();
    }

    @Test
    void publicEndpointAllowsAnonymous() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("public");
    }

    @Test
    void privateEndpointRejectsAnonymous() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void privateEndpointAcceptsActiveUser() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth(
                "alice", "demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.username").isEqualTo("alice");
    }

    @Test
    void wrongPasswordIsRejected() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth(
                "alice", "wrong-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void lockedUserIsRejectedOverHttpBasic() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth(
                "locked", "demo-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void disabledUserIsRejectedOverHttpBasic() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth(
                "disabled", "demo-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void expiredUserIsRejectedOverHttpBasic() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth(
                "expired", "demo-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void expiredCredentialsAreRejectedOverHttpBasic() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth(
                "credentials-expired", "demo-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void userWithReadAuthorityCanReadOrdersEndpoint() {
        client.get().uri("/api/orders")
            .headers(h -> h.setBasicAuth(
                "alice", "demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("orders-read");
    }

    @Test
    void roleUserWithoutPermissionCannotReadOrdersEndpoint() {
        client.get().uri("/api/orders")
            .headers(h -> h.setBasicAuth(
                "viewer", "demo-password"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void normalUserCannotCallAdminEndpoint() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth(
                "alice", "demo-password"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminRoleCanCallAdminEndpoint() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth(
                "admin", "demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("admin");
    }

    @Test
    void unknownRouteIsDeniedEvenForAuthenticatedUser() {
        client.get().uri("/api/unknown")
            .headers(h -> h.setBasicAuth(
                "alice", "demo-password"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void spoofedRoleHeaderDoesNotAuthenticate() {
        client.get().uri("/api/admin")
            .header("X-Role", "ADMIN")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

**21 test** trên bao phủ dữ liệu UserDetails, BCrypt hash, bốn account flags, xác thực trực tiếp qua ReactiveAuthenticationManager và kết quả HTTP WebFlux (200/401/403). Các test cần được chạy trong project với dependency đã khai báo; phần mã ở tài liệu là mẫu để người học thực thi, không phải báo cáo rằng Maven đã được chạy.

### 8.1. Test nào chứng minh được điều gì?

| Nhóm | Chứng minh được | Chưa chứng minh |
| --- | --- | --- |
| StepVerifier trên MapReactiveUserDetailsService | Publisher phát UserDetails và các field/flags/authorities đúng. | Đường HTTP đã xác thực, mật khẩu được kiểm trong filter. |
| StepVerifier trên manager.authenticate | Password và account được xử lý thành Authentication hợp lệ trong reactive pipeline. | HTTP status, CORS, CSRF, TLS hoặc proxy. |
| WebTestClient | WebFlux/Spring Security áp dụng rule và trả status/body đúng trong test context. | Ingress production, thực tế OAuth2 IdP, database thật, tenant ownership. |
| curl trên server chạy thật | Hành vi HTTP của tiến trình local và Basic challenge. | Bảo mật hạ tầng/HTTPS khi deploy và secret rotation. |

Không dùng MockMvc làm công cụ chính để kiểm filter chain WebFlux. **WebTestClient** là API phù hợp, có thể bind vào application context hoặc kết nối tới server HTTP thật, tùy cấu hình.

### 8.2. Vì sao không test luôn updatePassword?

MapReactiveUserDetailsService có updatePassword(...), nhưng nó **thay đổi dữ liệu trong Map**. Nếu các test cùng dùng Spring ApplicationContext và một test thay password của alice, các test đăng nhập sau có thể trở nên phụ thuộc thứ tự hoặc thất bại ngẫu nhiên. Để test cập nhật, hãy tạo **một instance MapReactiveUserDetailsService riêng trong test đó**, dùng mật khẩu demo và verify cả giá trị hash lẫn hành vi tìm user sau update. Không làm thay đổi bean người dùng chung của các integration test.

## 9. ReactiveUserDetailsService tự viết với database reactive

Khi ứng dụng cần nguồn account thật, thay Map bằng repository phù hợp. Một luồng R2DBC có thể được thiết kế:

~~~text
HTTP Basic / form login
        |
        v
ReactiveAuthenticationManager
        |
        v
ReactiveUserDetailsService.findByUsername(username)
        |
        v
R2DBC repository / driver nonblocking
        |
        v
Mono<AccountRow> --> map AccountRow -> UserDetails
        |
        v
Manager kiểm trạng thái + PasswordEncoder.matches
        |
        v
Authentication hoặc lỗi
~~~

Một mảnh service minh họa; **cần có AccountRepository, AccountRow và cấu hình R2DBC riêng**, nên không phải file độc lập chạy trong demo:

~~~java
@Service
public class DatabaseReactiveUserDetailsService
        implements ReactiveUserDetailsService {

    private final AccountRepository accounts;

    public DatabaseReactiveUserDetailsService(
            AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    public Mono<UserDetails> findByUsername(String username) {
        return accounts.findByUsername(username)
            .map(row -> User.withUsername(row.username())
                .password(row.passwordHash())
                .authorities(row.authorities())
                .disabled(!row.enabled())
                .accountLocked(row.locked())
                .accountExpired(row.expired())
                .credentialsExpired(row.credentialsExpired())
                .build());
    }
}
~~~

**AccountRepository.findByUsername(...)** trong đoạn minh họa được giả định trả **Mono<AccountRow>**. Phải đảm bảo hàng dữ liệu có đúng hash và authorities đã được cấp từ nguồn tin cậy. Nếu repository trả lỗi do DB mất kết nối, manager không nên tự cho đăng nhập dưới một account mặc định.

Khi thay bean Map bằng database service:

- Chỉ giữ **một nguồn ReactiveUserDetailsService thích hợp** cho cơ chế đăng nhập này hoặc cấu hình manager/chain để lựa chọn tường minh.
- Không đưa cả Map demo account vào production; tài khoản demo có thể trở thành cửa hậu nếu bị quên.
- Đảm bảo username unique trong phạm vi cần thiết và không trộn dữ liệu giữa tenant.
- Hash password trong database phải phù hợp encoder. Không gọi encoder.encode(storedHash) lần nữa.
- Đọc authorities/roles từ mối quan hệ đáng tin; không lấy từ header X-Role do client tùy ý đặt.
- Mapping boolean phải chính xác: entity.locked=true → builder.accountLocked(true), nghĩa là UserDetails.isAccountNonLocked() false.
- Dùng index/query tối ưu, timeout, giới hạn connection pool và health check; tránh trả toàn bộ profile dữ liệu nhạy cảm chỉ để xác thực.
- Nếu cache user hoặc authorities, phải có TTL/invalidation khi đổi role, password hoặc khóa account.
- Đặt quy trình password reset, MFA, audit, rate limit và cảnh báo gian lận ở những thành phần phù hợp.

### 9.1. R2DBC có bắt buộc không?

Không. WebFlux có thể tích hợp nguồn HTTP reactive hoặc một loại lưu trữ có driver nonblocking tương thích. Cũng có ứng dụng WebFlux phải gọi một dependency blocking; lúc đó cần cô lập và đo tải. Điều quan trọng là hiểu **thực tế lời gọi**, khả năng backpressure, timeout và mức tiêu thụ thread, không coi tên method bắt đầu bằng Mono là bằng chứng.

## 10. PasswordEncoder, scheduler và hiệu năng

**PasswordEncoder** có chữ ký đồng bộ, chẳng hạn:

~~~java
// Mảnh API, không phải method độc lập ngoài interface.
String encode(CharSequence rawPassword);
boolean matches(CharSequence rawPassword, String encodedPassword);
~~~

BCrypt thực hiện công việc CPU có chủ đích để làm chậm tấn công thử mật khẩu. Một ReactiveAuthenticationManager có thể lập lịch các bước xử lý password trên scheduler phù hợp; không có nghĩa phép hash đã trở thành thao tác I/O nonblocking.

Khi có nhiều request login cùng lúc, cần quan sát:

- CPU dùng để so khớp BCrypt/Argon2/PBKDF2 theo chính sách.
- Timeout và concurrency cho việc tra user từ database/identity store.
- Rate limit theo IP/tài khoản/thiết bị và phòng chống credential stuffing.
- Độ trễ p95/p99 của authentication và số lượng thread ở event-loop/scheduler.
- Điều kiện trả lỗi khi account không tồn tại, DB lỗi hoặc credential sai.
- Không ghi thông tin password hash, raw password, Authorization header, cookie và token vào log.

**Không khuyên bỏ BCrypt hoặc dùng NoOpPasswordEncoder để tăng tốc production.** Cần tối ưu cấu hình, cost và khả năng chịu tải đúng cách. Với dòng Spring Security khác, behavior scheduling có thể thay đổi; hãy đọc Javadoc/implementation của manager trong version đang dùng.

## 11. Reactor Context và SecurityContext: hai việc khác với user lookup

Trong WebFlux, Spring Security truyền ngữ cảnh bảo mật qua **Reactor Context** theo luồng reactive. Sau khi authentication thành công, code có thể lấy principal từ WebFlux method argument hoặc qua **ReactiveSecurityContextHolder**.

Ví dụ fragment trong một service reactive:

~~~java
// Mảnh code cần import ReactiveSecurityContextHolder,
// SecurityContext và Mono từ Spring Security/Reactor.
Mono<String> currentUsername =
    ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName());
~~~

**Điều này không phải là ReactiveUserDetailsService.findByUsername(...)**. Một service dùng ReactiveSecurityContextHolder đang đọc **người dùng hiện tại đã xác thực**, còn ReactiveUserDetailsService là nơi **tìm account theo username** trong quá trình xác thực.

Khi không có security context, publisher có thể không phát username; khi principal là JWT/OIDC/service identity, type của principal có thể khác UserDetails. Đừng cast mọi Authentication.getPrincipal() sang UserDetails mà không kiểm cơ chế authentication.

Không lưu Authentication trong một biến static rồi để nhiều request cùng dùng: làm vậy có thể trộn danh tính giữa người dùng. Cũng không tự subscribe bên ngoài request và cho rằng security context sẽ luôn tự theo sang scheduled job hoặc message consumer.

### 11.1. WebSession và MapReactiveUserDetailsService

Một account được tìm thấy trong Map không tự tạo HTTP session hoặc auto-login. Phải phân biệt:

- **User lookup**: MapReactiveUserDetailsService.
- **Authentication**: ReactiveAuthenticationManager + filter.
- **Request context**: SecurityContext trong Reactor Context.
- **Persistence giữa request**: ServerSecurityContextRepository/WebSession hoặc cơ chế token/credential theo cấu hình.
- **Authorization**: quyền trên URL, method và object.

WebFlux vẫn hỗ trợ session. Mono không tự mang ý nghĩa “stateless”; thiết kế stateless hay stateful là một quyết định kiến trúc riêng.

## 12. Phân biệt mã 401, 403 và lỗi tra user

Khi test REST API WebFlux, các kết quả điển hình:

| Tình huống | Kết quả HTTP thường thấy | Lý do |
| --- | --- | --- |
| GET /api/me không Authorization | 401 | Endpoint cần Authentication; HTTP Basic challenge. |
| Alice gửi password đúng | 200 | Account hợp lệ, provider cho Authentication. |
| Alice gửi password sai | 401 | Credential không khớp. |
| Username không có trong store | 401 | Không tạo được Authentication, không công bố user tồn tại. |
| User locked/disabled/expired/password-expired | 401 | Account checks của manager từ chối dù password đúng. |
| Viewer vào /api/orders | 403 | Đã xác thực nhưng thiếu orders:read. |
| Alice vào /api/admin | 403 | Thiếu ROLE_ADMIN. |
| POST tới một path chỉ mở GET, thiếu CSRF token | Thường 403 | Có thể bị CsrfWebFilter từ chối trước authorization. |
| Một endpoint chưa được khai báo | 403 với denyAll và user đã xác thực | Fallback từ chối ở tầng authorization. |

**401 không luôn nghĩa “mật khẩu sai”.** Có thể chưa gửi credential, sai username, account locked hoặc service lookup lỗi. **403 không luôn nghĩa “thiếu role”**; còn có permission, CSRF, CORS trong browser, tenant/owner policy hoặc WebFilter khác. Xác định chính xác layer từ chối trước khi sửa.

Trên production, tránh trả cho người dùng chưa xác thực chi tiết “account Alice đang bị khóa” hoặc “tài khoản tồn tại” vì có thể làm lộ thông tin. Giữ lý do đầy đủ trong audit/log nội bộ được bảo vệ và che secret.

### 12.1. Có cần luôn trả Mono.error khi user không tồn tại?

Không áp dụng một lời khuyên máy móc cho mọi implementation. Hợp đồng quan trọng là **không trả null thay vì publisher**, và cơ chế authentication phải biến kết quả “không có user” thành thất bại. Với service custom, bạn có thể phát **Mono.empty()** hoặc tín hiệu lỗi thích hợp theo contract/cấu hình được sử dụng; khi đưa vào manager thật, test trường hợp username không tồn tại để xác nhận response 401 và không tạo fallback danh tính.

Đừng dùng switchIfEmpty(Mono.just(adminUser)) vì đó là fail-open. Đối với lỗi nguồn dữ liệu, xử lý error có chủ đích và không giả làm user hợp lệ.

## 13. updatePassword() của MapReactiveUserDetailsService

Ngoài findByUsername, MapReactiveUserDetailsService còn hỗ trợ hợp đồng **ReactiveUserDetailsPasswordService** với phương thức **updatePassword(UserDetails, String)** trả Mono<UserDetails>.

Ý nghĩa tổng quát:

- Dùng để cập nhật password đã lưu theo implementation.
- Chuỗi password mới được truyền theo contract của hệ thống lưu trữ; đừng tùy tiện truyền raw password vào một API mong encoded hash.
- Cần xác thực/ủy quyền và quy trình thay đổi password riêng (xác minh password cũ hoặc kênh recovery/MFA theo policy).
- Thay đổi trong Map của demo chỉ ảnh hưởng tiến trình đang chạy; không tự ghi database hoặc đồng bộ nhiều instance.

Ví dụ minh họa trong một test có instance **tạo riêng**, không sửa bean demo dùng chung:

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder();

UserDetails account = User.withUsername("test-user")
    .password(encoder.encode("old-demo"))
    .roles("USER")
    .build();

MapReactiveUserDetailsService isolated =
    new MapReactiveUserDetailsService(account);

// Mảnh reactive test: updatePassword nhận encoded password mới.
Mono<UserDetails> updated = isolated.updatePassword(
    account, encoder.encode("new-demo")
);
~~~

Sau đó cần subscribe/verify updated và tìm lại test-user để xác nhận password mới được áp dụng. Đoạn này **không phải một endpoint đổi mật khẩu**: nó bỏ qua rất nhiều bước production như xác minh chủ tài khoản, rate limit, MFA, invalidation session/token và audit.

## 14. Tình huống lỗi thường gặp khi chuyển từ MVC sang WebFlux

### 14.1. Import UserDetailsService đồng bộ trong WebFlux

Bạn viết một bean UserDetailsService và mong reactive authentication manager tự gọi loadUserByUsername. Hợp đồng username/password reactive sử dụng **ReactiveUserDetailsService**. Hãy kiểm stack server và manager thực sự trong cấu hình; đừng đoán theo tên interface gần giống.

### 14.2. Đổi kiểu trả về thành Mono nhưng vẫn gọi JDBC blocking

Mono.just(jdbcRepository.findUser(...)) vẫn block thread hiện tại. Dùng R2DBC hoặc chiến lược cô lập blocking đúng cách, đo concurrency và timeout.

### 14.3. Quên PasswordEncoder tương ứng

UserDetails.getPassword() chứa BCrypt hash nhưng manager dùng encoder không tương thích, có thể dẫn đến 401 hoặc lỗi xử lý encoded password. Demo dùng **setPasswordEncoder(BCryptPasswordEncoder)** tường minh và test match/mismatch.

### 14.4. Đảo trạng thái account

builder.accountLocked(true) làm isAccountNonLocked=false. Nếu bạn gán ngược từ DB, user bị khóa có thể tiếp tục đăng nhập. Test trực tiếp UserDetails flags và đường xác thực.

### 14.5. Coi ROLE_USER tự có orders:read

**hasRole("USER")** kiểm ROLE_USER; **hasAuthority("orders:read")** kiểm chính xác quyền thao tác. Một user chỉ có role không tự có permission. Không cấp quyền đọc dữ liệu nhạy cảm vì username có tên “admin”.

### 14.6. Map chứa tài khoản demo xuất hiện ở production

Không vận hành với password demo hard-code, tài khoản admin dùng chung, dữ liệu chỉ nằm trong RAM hoặc thiếu audit/rotation. Thay bằng nguồn danh tính và deployment controls thích hợp.

### 14.7. Dùng MockMvc thay cho WebTestClient

MockMvc là công cụ dành cho Spring MVC/Servlet. WebFlux nên kiểm bằng **WebTestClient**, và dùng reactor-test/StepVerifier cho publisher trực tiếp.

### 14.8. Tắt CSRF để POST chạy được

CSRF phụ thuộc loại credential và threat model của browser; không tắt theo phản xạ khi một request POST nhận 403. Demo chỉ dùng GET; khi bổ sung thao tác ghi, thiết kế CSRF rõ và dùng test thích hợp.

### 14.9. Đăng nhập thành công nhưng API vẫn 403

Manager đã có Authentication đúng, nhưng policy authorization đòi role/permission khác. Xem rule **authorizeExchange** và authorities trước khi thay logic user lookup.

### 14.10. Xóa/đổi account nhưng session hoặc JWT vẫn có quyền cũ

Một UserDetails snapshot được nạp lúc đăng nhập không tự đồng bộ với mọi session hoặc JWT. Phải thiết kế revocation/TTL/dynamic checks khi khóa user hoặc thu hồi permission.

### 14.11. Tra username không theo tenant

Nếu nhiều tenant có cùng username, chỉ tìm theo username không đủ xác định đúng account. Tenant routing phải dựa trên nguồn đáng tin và cơ chế xác thực được thiết kế, không gán tùy ý từ header.

### 14.12. Trả UserDetails trực tiếp ra REST

UserDetails có thể chứa password hash và trạng thái account. Đừng serialize nguyên object; trả DTO cần thiết, thường chỉ username và trường public phù hợp.

### 14.13. Quên tính chất lazy/cancel của publisher

Tự subscribe rồi trả Mono.empty() có thể khiến xử lý authentication chạy ngoài thời điểm request và không truyền lỗi đúng. Trả publisher cho manager/framework subscribe, định nghĩa timeout và error propagation.

### 14.14. Tin rằng JWT Resource Server luôn dùng MapReactiveUserDetailsService

Bearer token validation thường dựa vào decoder/introspection, không mặc định lấy account từ Map để so password. Khi chuyển cơ chế, cần thiết kế lại cách kiểm trạng thái tài khoản và authority mapping.

## 15. Từ demo sang production: những bước cần làm

Một quy trình hợp lý:

1. **Xác định server stack**: Spring MVC hay WebFlux. Nếu là WebFlux, dùng ServerHttpSecurity và ReactiveUserDetailsService cho username/password.
2. **Chọn nguồn dữ liệu**: R2DBC database, HTTP client reactive, LDAP/IdP có integration phù hợp. Đừng đặt JDBC blocking vô tình trên event-loop.
3. **Thiết kế account schema**: username/ID/tenant unique, password hash, authorities, enabled/locked/expiry và nguồn thời gian đáng tin.
4. **Cấu hình PasswordEncoder**: hash chuẩn, migration và kiểm thử đúng thuật toán/version.
5. **Thiết kế lifecycle user**: registration, verification, password reset, lockout/rate limit, MFA, disable và audit.
6. **Chọn credential transport**: form login/session, Basic chỉ với HTTPS hoặc OAuth2/OIDC/Bearer theo nhu cầu thực tế.
7. **Bảo vệ URL và method**: permitAll có chủ đích, hasRole/hasAuthority đúng kiểu, fallback denyAll và CSRF/CORS được kiểm theo client.
8. **Bảo vệ object-level**: user chỉ đọc/sửa dữ liệu mình có quyền; tenant/admin không mặc nhiên bỏ qua policy domain.
9. **Kiểm reactivity**: test timeout/cancel/error, connection pool, CPU password hash và tải đồng thời.
10. **Kiểm sự thu hồi**: khi account bị khóa/đổi quyền, session/token có còn hợp lệ không, trong bao lâu?
11. **Viết test âm tính**: username không tồn tại, wrong password, locked/disabled/expired, missing authority, cross-tenant, lỗi DB.
12. **Đối chiếu deployment thực**: HTTPS, gateway, headers, secret management, update Spring Security và giám sát.

Một tài khoản demo với MapReactiveUserDetailsService là đủ để hiểu API; khi đưa vào production, cần cả chính sách vận hành và data integrity chứ không chỉ một implementation finder khác.

## 16. Bài tập tự luyện

**Bài tập 1 — So sánh contract.** Viết hai chữ ký **UserDetailsService.loadUserByUsername(String)** và **ReactiveUserDetailsService.findByUsername(String)**. Giải thích vì sao loại kết quả khác nhau nhưng UserDetails vẫn dùng chung.

**Bài tập 2 — Tạo MapReactiveUserDetailsService.** Tạo hai UserDetails alice và admin bằng User builder, sử dụng BCryptPasswordEncoder để lưu hash, rồi truyền vào constructor nhận varargs. Viết StepVerifier kiểm username và ROLE_ADMIN.

**Bài tập 3 — Trạng thái khóa.** Tạo UserDetails locked bằng .accountLocked(true). isAccountNonLocked() trả gì? Vì sao password đúng không đủ để đăng nhập?

**Bài tập 4 — Permission.** Viewer có ROLE_USER nhưng không có orders:read. GET /api/orders trả gì với rule hasAuthority("orders:read")? Vì sao không thể coi role và permission là đồng nghĩa?

**Bài tập 5 — Kiểm hash.** Tại sao getPassword() phải là hash và PasswordEncoder.matches(raw, hash) khác với so raw.equals(hash)? Viết test sai password.

**Bài tập 6 — Blocking.** Phân tích vì sao Mono.just(jdbcRepository.loadUser(username)) không đưa JDBC sang nonblocking. Đề xuất phương án có R2DBC và phương án giới hạn dùng boundedElastic khi buộc gọi blocking.

**Bài tập 7 — Test WebFlux.** Viết WebTestClient test public 200, anonymous /api/me 401, viewer /api/orders 403 và admin /api/admin 200.

**Bài tập 8 — User không tồn tại.** Một ReactiveUserDetailsService trả null khi username không tìm thấy. Sửa theo Reactor contract; test authentication manager từ chối user không tồn tại.

**Bài tập 9 — Password update.** Tạo instance MapReactiveUserDetailsService riêng, cập nhật encoded password trong test và xác nhận password cũ không còn hợp lệ. Tại sao không nên thay đổi account chung giữa các integration tests?

**Bài tập 10 — Token và session.** User vừa bị disable trong database nhưng access token còn hiệu lực. Vì sao cập nhật UserDetails chưa chắc thu hồi được token? Đề xuất một chiến lược phù hợp.

**Bài tập 11 — SecurityContext.** Phân biệt ReactiveSecurityContextHolder.getContext() với ReactiveUserDetailsService.findByUsername(...). Cái nào cho biết principal của request hiện tại, cái nào tra thông tin user từ store?

**Bài tập 12 — Multi-tenant.** Hai tenant đều có username alice. Thiết kế một cách tìm user an toàn có tính tới tenant đã xác minh, rồi test cross-tenant access denied.

### Checklist ghi nhớ

- **ReactiveUserDetailsService** là interface tìm UserDetails bằng **Mono<UserDetails>**.
- **MapReactiveUserDetailsService** là implementation dùng Map, phù hợp demo/test; không phải cơ sở dữ liệu production.
- **UserDetails** vẫn chứa username, password hash, authorities và bốn account flags.
- **UserDetailsRepositoryReactiveAuthenticationManager** dùng service reactive + PasswordEncoder để kiểm username/password.
- **ServerHttpSecurity và SecurityWebFilterChain** bảo vệ WebFlux server; HttpSecurity/SecurityFilterChain là API của Servlet.
- **Mono không tự biến I/O blocking thành nonblocking**. Không gọi block() trong WebFilter/Controller.
- **ReactiveSecurityContextHolder** phục vụ current security context; nó không phải user repository.
- **ROLE_USER khác orders:read**; xác thực thành công không tự cho phép mọi endpoint hay object.
- **Account disabled/locked/expired** có thể bị từ chối ngay cả khi password đúng.
- **StepVerifier kiểm publisher, WebTestClient kiểm HTTP WebFlux**. Không dùng MockMvc để kết luận WebFlux chain đúng.
- **WebFlux không tự bảo đảm stateless**. Session, JWT revocation và quyền dữ liệu cần thiết kế riêng.
- **Không dùng dữ liệu demo hoặc HTTP Basic qua mạng không có HTTPS** trong sản phẩm thật.

## Tài liệu tham khảo

- [Spring Security — ReactiveUserDetailsService JavaDoc](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/core/userdetails/ReactiveUserDetailsService.html): contract findByUsername trả Mono<UserDetails>.
- [Spring Security — MapReactiveUserDetailsService JavaDoc](https://docs.spring.io/spring-security/site/docs/6.3.0/api/org/springframework/security/core/userdetails/MapReactiveUserDetailsService.html): constructors, findByUsername và updatePassword.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): EnableWebFluxSecurity, ServerHttpSecurity và SecurityWebFilterChain.
- [Spring Security — UserDetailsRepositoryReactiveAuthenticationManager JavaDoc](https://docs.spring.io/spring-security/site/docs/6.3.0/api/org/springframework/security/authentication/UserDetailsRepositoryReactiveAuthenticationManager.html): ReactiveAuthenticationManager dùng ReactiveUserDetailsService.
- [Spring Security — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html): kiểm thử WebFlux security.
- [Spring Framework — Testing WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux-test.html): WebTestClient và mock reactive request/response.

**Phiên bản:** Bài thực hành cố định Spring Boot 3.3.6, Spring Security 6.3.x để giữ mã và API đồng nhất. Khi tạo dự án mới, chọn nhánh Spring Boot/Spring Security đang được hỗ trợ và áp dụng bản vá tương ứng; kiểm tra package, constructor, password encoder và test theo dependency được quản lý thực tế.

## Kết luận

**ReactiveUserDetailsService** cung cấp cách tra tài khoản bằng Mono<UserDetails> phù hợp với pipeline WebFlux, trong khi **MapReactiveUserDetailsService** là implementation đơn giản dùng Map để thử nhanh hoặc kiểm thử. Hai loại cùng trả UserDetails chứa username, password hash, authorities và trạng thái account; nhưng **việc xác thực** vẫn thuộc ReactiveAuthenticationManager và PasswordEncoder, còn **việc cho phép truy cập** thuộc security policy và domain. Hiểu rõ vai trò của từng lớp, kiểm tra nguồn I/O thực sự nonblocking, bảo vệ credentials và dùng WebTestClient/StepVerifier để kiểm cả trường hợp thành công lẫn bị từ chối sẽ giúp triển khai nguồn người dùng reactive chính xác và an toàn.
