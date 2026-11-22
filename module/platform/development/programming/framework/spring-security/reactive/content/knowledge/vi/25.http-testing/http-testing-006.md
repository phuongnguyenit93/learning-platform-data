# Kiểm thử HTTP Basic với thông tin hợp lệ và không hợp lệ trong Spring Security Reactive

> **Module:** Spring Security - reactive  
> **Nhóm kiến thức:** Kiểm thử HTTP  
> **Bài học:** Kiểm thử HTTP Basic với thông tin hợp lệ và không hợp lệ  
> **Mục tiêu:** Viết và hiểu các kiểm thử WebFlux chứng minh HTTP Basic xác thực **username/password thật**, phân biệt lỗi 401 và 403, kiểm tra `WWW-Authenticate`, chống bỏ qua filter bảo mật khi dùng mock, bảo vệ đường ghi dữ liệu bằng CSRF và xây một bộ JUnit 5 + `WebTestClient` đủ tình huống thành công/thất bại.

## 1. Bài toán: kiểm thử đúng đường xác thực, không chỉ giả lập login

Ứng dụng cung cấp các endpoints:

- `GET /public/ping`: công khai.
- `GET /api/me`: yêu cầu người dùng đã xác thực.
- `GET /api/reports`: cho vai trò ANALYST hoặc ADMIN.
- `GET /api/admin`: chỉ vai trò ADMIN.
- `POST /api/reports`: chỉ ANALYST và phải tuân thủ CSRF khi bảo vệ endpoint này bằng Basic cho browser.

Ứng dụng không có form login, không nhận JWT trong ví dụ, không dựa trên HTTP session để lưu Authentication. Mỗi request tới endpoint riêng tư cần có thông tin HTTP Basic hợp lệ, trừ những policy khác được khai báo một cách chủ đích.

Bộ test phải chứng minh **ba điều khác nhau**:

1. **Authentication:** password thực sự được so với BCrypt hash từ một `ReactiveUserDetailsService`. Username đúng + password đúng → qua. Username đúng + password sai → 401.
2. **Authorization:** tài khoản được xác thực nhưng thiếu quyền truy cập route → 403, không phải lỗi password.
3. **Protocol security:** thiếu hoặc sai `Authorization` header → 401; password có được Base64 encode **không phải** mã hóa bảo mật; có Basic challenge khi cần và CSRF cho request đổi dữ liệu nếu browser có thể tự gửi credentials.

Quan trọng: `mockUser()` hoặc `@WithMockUser` **không chứng minh** HTTP Basic password verification đã chạy. Chúng cài sẵn Authentication vào test context, hữu ích để test authorization nhưng không thay thế kiểm thử header Basic thật.

## 2. HTTP Basic hoạt động như thế nào?

Theo RFC 7617, client gửi credential dưới dạng:

~~~http
GET /api/me HTTP/1.1
Host: api.example.com
Authorization: Basic YW5hbHlzdDpsYWItcGFzcy0xMjM=
Accept: application/json
~~~

Chuỗi Base64 ở ví dụ là encoding của `analyst:lab-pass-123`. Đây là password dummy công khai chỉ dùng trong lab.

Quy trình:

~~~mermaid
sequenceDiagram
    participant C as HTTP Client
    participant W as WebFlux SecurityWebFilterChain
    participant B as HTTP Basic authentication converter
    participant M as ReactiveAuthenticationManager
    participant U as ReactiveUserDetailsService
    participant H as Controller
    C->>W: GET /api/me + Authorization Basic ...
    W->>B: Parse scheme + Base64(username:password)
    B->>M: UsernamePasswordAuthenticationToken (unauthenticated)
    M->>U: findByUsername(username)
    U-->>M: UserDetails + BCrypt password hash
    M->>M: PasswordEncoder.matches(raw, storedHash)
    alt Incorrect or missing credential
        M-->>C: 401 + Basic challenge (theo entry point)
    else Credential valid
        M->>W: Authenticated principal + authorities
        W->>W: authorizeExchange route rule
        alt Missing required authority
            W-->>C: 403 Forbidden
        else Authorized
            W->>H: Invoke endpoint
            H-->>C: 200 JSON
        end
    end
~~~

**Base64 ≠ Encryption:** ai đọc được traffic plaintext có thể decode Base64 lấy username/password. Cấm dùng Basic qua HTTP internet; chỉ dùng HTTPS với chứng chỉ được kiểm tra. Không nhúng credential trong URL hay repository, không log Authorization header. HTTP/2, TLS termination và reverse proxy vẫn phải bảo vệ đường đi tới server.

**Colon delimiter:** Basic hình thành từ chuỗi `username:password`, phân tách tại dấu `:` đầu tiên. Username không được chứa dấu `:`; password **có thể** chứa dấu `:`. Charset của Basic có yếu tố interoperability; để các ví dụ test dễ dự đoán, dùng username/password ASCII và xác nhận policy UTF-8/charset của server nếu cần tiếng Việt hay ký tự quốc tế.

## 3. Phân biệt 401 Unauthorized và 403 Forbidden

| Kịch bản | Authentication | Authorization | Kết quả kỳ vọng |
| --- | --- | --- | --- |
| `GET /public/ping` không credential | Không bắt buộc | Public route | **200** |
| `GET /api/me` không header | Chưa xác thực | Bắt buộc auth | **401** |
| Username đúng, password sai | Thất bại | Không xét đến quyền | **401** |
| Username không tồn tại | Thất bại | Không xét quyền | **401** |
| Base64 malformed / scheme sai | Không có Basic credential hợp lệ | Bắt buộc auth | **401** |
| analyst + password đúng vào `/api/me` | Thành công | Chỉ cần auth | **200** |
| analyst + password đúng vào `/api/admin` | Thành công | Thiếu ADMIN | **403** |
| admin + password đúng vào `/api/admin` | Thành công | Có ADMIN | **200** |
| analyst + password đúng + POST không CSRF | Thành công | CSRF không hợp lệ | **403** |
| analyst + password đúng + POST có CSRF hợp lệ | Thành công | Có ANALYST + CSRF | **201** |

**Một response 401 không cho biết chính xác lý do tài khoản bị từ chối.** Tránh body trả “username không có” nhưng password sai thì “password incorrect”; lỗi cần chung để không hỗ trợ account enumeration. Có thể ghi mã lỗi an toàn trong logs nội bộ, nhưng không ghi raw credential.

**403 không phải “đăng nhập thất bại”:** nếu người dùng đã authenticated mà thiếu authority, việc gửi lại password cũ thường không giúp. Đây là vấn đề quyền ở route hoặc domain layer.

## 4. Header WWW-Authenticate và cách đọc kết quả test

Khi request private chưa authenticated, HTTP Basic entry point thường gửi:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
~~~

Đây là **dạng minh họa**; tên realm và các response headers cụ thể phụ thuộc cấu hình Spring Security/version và proxy. Bộ test nên kiểm tra header bắt đầu bằng `Basic` khi route yêu cầu challenge, thay vì hardcode mọi byte của realm.

Theo chính sách entry point, các yêu cầu đặc biệt như XHR hoặc API gateway có thể biến đổi challenge, vì vậy đừng buộc mọi response 401 phải có cùng body/header nếu ứng dụng đã cấu hình custom exception handling.

Header không nên chứa username/password, BCrypt hash hoặc lý do “tài khoản này tồn tại”. Basic challenge có thể khiến browser bật hộp thoại đăng nhập; với SPA/API-first, một số nhóm chủ động customize entry point để kiểm soát UX, nhưng phải test quyết định đó riêng.

## 5. Chọn cách kiểm thử nào?

| Cách | Dữ liệu gửi | Chứng minh được gì? | Giới hạn |
| --- | --- | --- | --- |
| `WebTestClient.headers(h -> h.setBasicAuth(...))` | Basic HTTP header thật | Basic converter + manager + BCrypt + route | Khi bind in-memory chưa test TCP/TLS/proxy |
| `WebTestClient.bindToApplicationContext(...).apply(springSecurity())` | HTTP request mock, filter chain thật | WebFlux security end-to-end trong ApplicationContext | Không mở Netty socket |
| `@SpringBootTest(RANDOM_PORT)` + WebTestClient | HTTP request tới Netty server thật | Network HTTP + filter + password lookup | Chậm hơn, vẫn không chứng minh internet TLS |
| `mockUser("alice")` | Gắn Authentication giả | Role/authority route logic | **Không verify Basic password** |
| `@WithMockUser` | Tạo mock SecurityContext | Annotation method security và authorization | **Không verify header Base64** |
| `@WebFluxTest` | Web slice | Controller/security khi import đúng chain | Có thể bỏ custom SecurityWebFilterChain nếu quên import |
| `curl --user ...` | Basic header qua mạng | Smoke test môi trường chạy thật | Dễ lộ password qua terminal/log nếu thao tác sai |

**Chọn tối thiểu hai lớp cho bài này:** in-memory WebTestClient với Spring Security filter chain thật để test đầy đủ trường hợp, và vài smoke tests với `RANDOM_PORT` để xác minh Netty HTTP thực tế.

Không dùng `MockMvc` làm công cụ chính cho Spring WebFlux. Nó phục vụ Servlet MVC; nếu dự án chứa đồng thời `spring-boot-starter-web` và WebFlux thì Boot thường ưu tiên MVC trừ khi cấu hình chọn reactive rõ ràng.

## 6. Kiến trúc Spring Security Reactive cho Basic

Server side gồm:

- `SecurityWebFilterChain`: tập hợp security WebFilters dành cho HTTP WebFlux.
- `ServerHttpSecurity`: DSL khai báo `httpBasic`, authorization và CSRF.
- `ServerHttpBasicAuthenticationConverter`: chuyển Basic header thành `UsernamePasswordAuthenticationToken` chưa authenticated.
- `ReactiveAuthenticationManager`: xác minh credential; có thể dùng `UserDetailsRepositoryReactiveAuthenticationManager` hoặc custom provider.
- `ReactiveUserDetailsService`: tải user/password hash/roles; demo dùng `MapReactiveUserDetailsService`.
- `PasswordEncoder`: so sánh raw password với hash, demo dùng `BCryptPasswordEncoder`.
- `ServerAuthenticationEntryPoint`: khởi động cơ chế phản hồi 401/challenge.
- `ReactiveAuthorizationManager`: kiểm tra rule `authenticated`/`hasRole`/`hasAuthority`.
- `ReactiveSecurityContextHolder`: security context theo Reactor, không phải ThreadLocal luôn cố định một thread.

Trong lab, dùng `NoOpServerSecurityContextRepository` để không **persist Authentication** qua HTTP session. Điều này không có nghĩa toàn bộ WebFlux không thể dùng WebSession: CSRF token repository hoặc các thành phần khác vẫn có thể dùng session nếu được cấu hình.

HTTP Basic là **credential mỗi request**. Không nhầm với Basic xác thực user một lần rồi tạo session login cookie. Khi dùng browser, browser có thể tự cache Basic credentials và gửi lại, nên việc không persist SecurityContext **không** tự loại bỏ nguy cơ CSRF.

## 7. Security requirements cho bộ lab

1. **Secure by default:** các routes ngoài danh sách bị deny.
2. Chỉ `GET /public/ping` không cần auth.
3. `GET /api/me` yêu cầu authenticated principal.
4. `GET /api/reports` yêu cầu role ANALYST **hoặc** ADMIN.
5. `GET /api/admin` yêu cầu role ADMIN.
6. `POST /api/reports` yêu cầu role ANALYST và CSRF token hợp lệ (để minh họa browser Basic).
7. Không có formLogin, không có requestCache, không persist SecurityContext trong WebSession.
8. Passwords của ba users lab được cấp qua cấu hình, hash bằng BCrypt khi khởi động.
9. Không khai báo tài khoản mặc định/password mặc định dùng ngoài test.
10. Tests gửi Basic headers **thật**, không dùng `mockUser` để qua password check.
11. Với Spring Security default entry point, missing/wrong Basic trả 401; authenticated nhưng thiếu scope/role trả 403.
12. Đối với production, thay in-memory users bằng backing store và có chính sách chống brute force, MFA/vault/monitoring tùy môi trường.

## 8. Dự án Java 17+ / Maven

Ví dụ cố định parent `Spring Boot 3.5.16`, thuộc dòng 3.x dùng Spring Security 6.x. Đây là **phiên bản mốc để đọc mã**, không khẳng định là bản patch mới nhất tại thời điểm bạn học; production phải kiểm tra phiên bản còn hỗ trợ, CVEs và cập nhật patch thích hợp.

~~~text
webflux-http-basic-tests/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/basic/
    │   │   ├── BasicApplication.java
    │   │   ├── BasicSecurityConfig.java
    │   │   └── AccountController.java
    │   └── resources/application.yml
    └── test/java/demo/basic/
        ├── BasicFilterTest.java
        └── BasicNetworkTest.java
~~~

**Vì sao cần hai tests classes?** `BasicFilterTest` dùng WebTestClient bind trực tiếp WebFlux context, giúp xét nhiều trường hợp nhanh. `BasicNetworkTest` mở Netty trên random TCP port để chứng minh luồng HTTP thực tế chạy qua Basic filter; không sử dụng mockUser trong cả hai.

### 8.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>webflux-http-basic-tests</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
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

Không cần `spring-boot-starter-web`, Spring Session hoặc JWT starter; đề bài tập trung Basic và WebFlux. `spring-security-test` dùng cho `springSecurity()` và `csrf()` trong WebTestClient. `reactor-test` không bắt buộc cho các tests HTTP response; nếu thêm tests trực tiếp với Mono/Flux có thể khai báo riêng.

### 8.2. BasicApplication.java

~~~java
package demo.basic;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BasicApplication {
    public static void main(String[] args) {
        SpringApplication.run(BasicApplication.class, args);
    }
}
~~~

### 8.3. application.yml

~~~yaml
server:
  port: 8080

lab:
  users:
    analyst-password: "${LAB_ANALYST_PASSWORD:}"
    admin-password: "${LAB_ADMIN_PASSWORD:}"
    colon-password: "${LAB_COLON_PASSWORD:}"
~~~

Không có password cấu hình thì app phải **fail fast**. Mã không tạo user/password mặc định ngoài test, tránh bất ngờ chạy public server với credential đã công khai trong bài học.

Trong production, dùng secret store/vault và IAM, không đặt cleartext password trong Git, build logs hoặc CI config không mã hóa. Nếu cần nhiều users, dùng DB hoặc identity provider thay vì MapReactiveUserDetailsService in-memory.

## 9. BasicSecurityConfig.java — HTTP Basic + BCrypt + roles + CSRF

File `src/main/java/demo/basic/BasicSecurityConfig.java`:

~~~java
package demo.basic;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class BasicSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(12);
    }

    @Bean
    MapReactiveUserDetailsService users(
            PasswordEncoder encoder,
            @Value("${lab.users.analyst-password:}") String analystPassword,
            @Value("${lab.users.admin-password:}") String adminPassword,
            @Value("${lab.users.colon-password:}") String colonPassword) {

        if (analystPassword.isBlank()
                || adminPassword.isBlank()
                || colonPassword.isBlank()) {
            throw new IllegalStateException(
                "Configure all LAB_*_PASSWORD secrets");
        }

        UserDetails analyst = User.withUsername("analyst")
            .password(encoder.encode(analystPassword))
            .roles("ANALYST")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode(adminPassword))
            .roles("ADMIN")
            .build();

        UserDetails colon = User.withUsername("colon")
            .password(encoder.encode(colonPassword))
            .roles("ANALYST")
            .build();

        return new MapReactiveUserDetailsService(
            analyst, admin, colon);
    }

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http) {

        return http
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/public/ping")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .pathMatchers(HttpMethod.GET, "/api/reports")
                    .hasAnyRole("ANALYST", "ADMIN")
                .pathMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .pathMatchers(HttpMethod.POST, "/api/reports")
                    .hasRole("ANALYST")
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .requestCache(ServerHttpSecurity.RequestCacheSpec::disable)
            // Không vô hiệu hóa CSRF: Basic có thể được browser gửi tự động.
            .csrf(Customizer.withDefaults())
            .build();
    }
}
~~~

**Giải thích chi tiết:**

- `@EnableWebFluxSecurity` kích hoạt reactive security, `SecurityWebFilterChain` áp các rules HTTP.
- `MapReactiveUserDetailsService` là user store **demo**; `BCryptPasswordEncoder(12)` lưu bcrypt hash, không so raw string với raw string.
- Ba users có credentials từ secrets/config; test sẽ gán password dummy qua `@SpringBootTest(properties=...)`.
- `roles("ADMIN")` tạo `ROLE_ADMIN`; `hasRole("ADMIN")` kiểm đúng authority prefix. `hasAnyRole("ANALYST","ADMIN")` cho phép hai vai trò; POST chỉ cho ANALYST để có test 403 độc lập.
- `httpBasic(Customizer.withDefaults())` đăng ký Basic authentication converter/manager và entry point.
- `formLogin(...disable)` không mở trang login theo form; API này dựa vào Basic.
- `NoOpServerSecurityContextRepository` không lưu Authentication qua WebSession; mỗi Basic request cần credential, không dựa vào login state cũ.
- `requestCache(...disable)` tránh giữ request cache của login flow.
- `csrf(Customizer.withDefaults())` giữ CSRF protection với request thay đổi trạng thái: POST hợp lệ về password nhưng thiếu CSRF vẫn có thể 403. CSRF token repository vẫn có thể tạo WebSession, không mâu thuẫn NoOp SecurityContextRepository.
- `anyExchange().denyAll()` ngăn route mới vô tình thành public.

**Chú ý:** Username/password đôi khi được xác thực qua một `ReactiveAuthenticationManager` tùy chỉnh hoặc nhiều providers; nếu app thực dùng LDAP/DB/IdP, hãy test chính provider của production thay vì thay bằng MapReactiveUserDetailsService rồi cho rằng đã kiểm tra đúng password policy. Spring Security WebFlux không tự bảo vệ dữ liệu tenant/object chỉ nhờ role.

## 10. AccountController.java — endpoint đơn giản, không trả password

File `src/main/java/demo/basic/AccountController.java`:

~~~java
package demo.basic;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class AccountController {

    @GetMapping("/public/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "up"));
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(
            @AuthenticationPrincipal UserDetails principal) {
        return Mono.just(Map.of(
            "username", principal.getUsername()));
    }

    @GetMapping("/api/reports")
    public Mono<Map<String, String>> reports() {
        return Mono.just(Map.of("report", "readable"));
    }

    @GetMapping("/api/admin")
    public Mono<Map<String, String>> admin() {
        return Mono.just(Map.of("section", "admin"));
    }

    @PostMapping("/api/reports")
    @ResponseStatus(HttpStatus.CREATED)
    public Mono<Map<String, String>> createReport() {
        return Mono.just(Map.of("status", "created"));
    }
}
~~~

**Vì sao controller không tự parse header?** Authentication phải được Spring Security xử lý trước: controller chỉ đọc `@AuthenticationPrincipal UserDetails` đã xác thực. Nếu code tự `Base64.decode`, so password rồi cấp quyền trong controller, dễ bỏ quên bảo vệ route khác và mất centralized security semantics.

Các bodies JSON chỉ minh họa; production không trả password, BCrypt hash, `Authorization` hay secret. Controller `createReport` không thực sự lưu report; status 201 giúp kiểm tra route/CSRF mà không tạo side effect.

## 11. Chỉ dẫn dựng WebTestClient bảo vệ thật

Bài test thứ nhất sẽ bind `WebTestClient` vào `ApplicationContext`:

~~~java
client = WebTestClient.bindToApplicationContext(context)
    .apply(springSecurity())
    .configureClient()
    .build();
~~~

**Vì sao không dùng mỗi `bindToController(new AccountController())`?** Khi bind chỉ controller mà không cung cấp security filter chain, tests có thể gọi protected endpoint và nhận 200, nhưng đó **không** phải security test. `bindToApplicationContext(...)` lấy WebFlux infrastructure và `springSecurity()` áp SecurityWebFilterChain, cho phép credential converter/authentication manager/authorization hoạt động.

Để gửi Basic thật:

~~~java
client.get().uri("/api/me")
    .headers(headers ->
        headers.setBasicAuth("analyst", "lab-pass-123"))
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.username").isEqualTo("analyst");
~~~

`headers.setBasicAuth(username,password)` của Spring dựng `Authorization: Basic ...` đúng format, không cần tự Base64 bằng tay cho positive cases. Chỉ tự tạo malformed headers trong các negative tests.

Không dùng `.mutateWith(mockUser("analyst"))` trong **test xác thực mật khẩu**, vì request ấy không đi qua Basic converter/BCrypt authentication flow; đấy là mock Authentication đã được tin cậy trong test.

## 12. BasicFilterTest.java — positive và negative authentication

File `src/test/java/demo/basic/BasicFilterTest.java`. Trong các test properties, tất cả passwords đều là **dummy test credentials** và sẽ không được dùng khi chạy production.

~~~java
package demo.basic;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(properties = {
    "lab.users.analyst-password=lab-pass-123",
    "lab.users.admin-password=admin-pass-456",
    "lab.users.colon-password=pa:ss"
})
class BasicFilterTest {

    private static final String ANALYST = "analyst";
    private static final String GOOD = "lab-pass-123";

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private String rawBasic(String decoded) {
        return "Basic " + Base64.getEncoder().encodeToString(
            decoded.getBytes(StandardCharsets.ISO_8859_1));
    }

    @Test
    void publicEndpointWorksWithoutCredentials() {
        client.get().uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.status").isEqualTo("up");
    }

    @Test
    void missingCredentialsAreUnauthorized() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void correctAnalystCredentialsAreAccepted() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth(ANALYST, GOOD))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.username").isEqualTo("analyst")
            .jsonPath("$.password").doesNotExist();
    }

    @Test
    void correctAdminCredentialsAreAccepted() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth(
                "admin", "admin-pass-456"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.username").isEqualTo("admin");
    }

    @Test
    void wrongPasswordIsUnauthorized() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth(
                ANALYST, "incorrect-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void unknownUsernameIsUnauthorized() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth(
                "not-a-user", GOOD))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void emptyPasswordIsUnauthorized() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth(
                ANALYST, ""))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void malformedBase64IsUnauthorized() {
        client.get().uri("/api/me")
            .header(HttpHeaders.AUTHORIZATION,
                "Basic !!!not-base64!!!")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void decodedBasicWithoutColonIsUnauthorized() {
        client.get().uri("/api/me")
            .header(HttpHeaders.AUTHORIZATION,
                rawBasic("analyst"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void bearerSchemeIsNotAcceptedAsBasic() {
        client.get().uri("/api/me")
            .header(HttpHeaders.AUTHORIZATION,
                "Bearer not-an-access-token")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void emptyAuthorizationHeaderIsUnauthorized() {
        client.get().uri("/api/me")
            .header(HttpHeaders.AUTHORIZATION, "")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void colonInsidePasswordIsSupported() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("colon", "pa:ss"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.username").isEqualTo("colon");
    }

    @Test
    void analystCanReadReports() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBasicAuth(ANALYST, GOOD))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.report").isEqualTo("readable");
    }

    @Test
    void adminCanReadReports() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBasicAuth(
                "admin", "admin-pass-456"))
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void analystCannotAccessAdmin() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth(ANALYST, GOOD))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminMayAccessAdmin() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth(
                "admin", "admin-pass-456"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.section").isEqualTo("admin");
    }

    @Test
    void anonymousAdminRequestIsUnauthorized() {
        client.get().uri("/api/admin")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void basicChallengeIsOfferedWhenMissing() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueMatches(
                HttpHeaders.WWW_AUTHENTICATE, "^Basic.*");
    }

    @Test
    void validBasicWithoutCsrfStillCannotPost() {
        client.post().uri("/api/reports")
            .headers(h -> h.setBasicAuth(ANALYST, GOOD))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void validBasicAndCsrfCanPost() {
        client.mutateWith(csrf())
            .post().uri("/api/reports")
            .headers(h -> h.setBasicAuth(ANALYST, GOOD))
            .exchange()
            .expectStatus().isCreated()
            .expectBody()
            .jsonPath("$.status").isEqualTo("created");
    }

    @Test
    void wrongBasicStillFailsEvenWithCsrf() {
        client.mutateWith(csrf())
            .post().uri("/api/reports")
            .headers(h -> h.setBasicAuth(
                ANALYST, "incorrect-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void nextRequestDoesNotInheritPriorBasicIdentity() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth(ANALYST, GOOD))
            .exchange()
            .expectStatus().isOk();

        // Request thứ hai không có Authorization header.
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

**22 bài test** trên cùng một Spring ApplicationContext dùng WebTestClient kết hợp **Basic header thật** để chạy authentication chain. Cấu trúc này kiểm chứng code WebFlux filters và BCrypt, nhưng không mở socket TCP/kiểm tra proxy TLS.

**Vì sao negative tests có nhiều dạng?** Nếu chỉ kiểm tra một case “password sai”, app có thể vẫn chấp nhận Bearer nhầm, malformed Base64, route thiếu role hoặc dùng mockUser làm tất cả xanh. Mỗi test bảo vệ một quyết định cụ thể của pipeline.

**Đầu ra kỳ vọng:** các methods test không có stdout nghiệp vụ cố định; Maven Surefire/JUnit hiển thị số tests và PASS/FAIL tùy môi trường. Không cần so byte-for-byte nội dung lỗi 401 vì Spring Boot có thể cấu hình error handler khác nhau.

## 13. Tại sao dùng Basic header thật chứ không mockUser?

Đoạn test sau **không kiểm tra password**:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;

client.mutateWith(mockUser("analyst").roles("ANALYST"))
    .get().uri("/api/reports")
    .exchange().expectStatus().isOk();
~~~

Dù database không có user `analyst` hoặc mật khẩu đã bị đổi, mock vẫn có thể được cấp Authentication theo roles được test tự cung cấp. Đây là **authorization test**. Nó có giá trị để kiểm tra route/method-level rules nhưng không thay bộ test của bài này.

Ngược lại, với:

~~~java
client.get().uri("/api/me")
    .headers(h -> h.setBasicAuth("analyst", "incorrect-password"))
    .exchange().expectStatus().isUnauthorized();
~~~

Spring Security phải parse Base64, tìm user, so BCrypt hash và từ chối password sai. Nếu một test tự dựng Authentication authenticated trước rồi lại gửi Basic header, kết quả có thể bị ảnh hưởng bởi mock principal và không chứng minh Basic.

**Anti-pattern:** chèn `@WithMockUser` ở class level của chính các tests “invalid password”, khiến mọi request đã authenticated trước khi header được xét. Tách class tests về Basic credentials khỏi class tests thuần authorization mocks.

## 14. BasicNetworkTest.java — kiểm chứng HTTP qua Netty thật

Ngoài tests in-memory, thêm một nhóm nhỏ chạy server trên random port:

File `src/test/java/demo/basic/BasicNetworkTest.java`:

~~~java
package demo.basic;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "lab.users.analyst-password=lab-pass-123",
        "lab.users.admin-password=admin-pass-456",
        "lab.users.colon-password=pa:ss"
    }
)
@AutoConfigureWebTestClient
class BasicNetworkTest {

    @Autowired
    WebTestClient web;

    @Test
    void genuineHttpBasicWorksAcrossNetworkBoundary() {
        web.get().uri("/api/me")
            .headers(h -> h.setBasicAuth(
                "analyst", "lab-pass-123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.username").isEqualTo("analyst");
    }

    @Test
    void wrongPasswordReturns401OnRealHttpServer() {
        web.get().uri("/api/me")
            .headers(h -> h.setBasicAuth(
                "analyst", "bad-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void missingBasicHeaderReturns401OnRealHttpServer() {
        web.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void validButUnauthorizedRoleReturns403OnNetwork() {
        web.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth(
                "analyst", "lab-pass-123"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

**Bốn bài network tests** xác nhận HTTP Basic header thực sự chạy trên Netty + Spring WebFlux. Đây vẫn là loopback HTTP trong tests; không chứng minh TLS certificate, reverse proxy, WAF, ingress, sticky sessions hoặc multi-node deployment.

`RANDOM_PORT` tránh tranh chấp port giữa CI jobs. `@AutoConfigureWebTestClient` tự gắn base URL đến server đã chạy với random port; không hardcode localhost:8080 trong integration test.

**Tổng bộ ví dụ:** 22 filter tests + 4 network tests = **26 JUnit test methods**. Việc số đếm và PASS là kỳ vọng sau khi bạn chạy Maven trên workspace có dependencies, không phải kết quả đã được thực thi ở đây.

## 15. Checklist coverage tối thiểu, trước khi phát hành

| Test ID | Input | Route | Assert chính | Vai trò của test |
| --- | --- | --- | --- | --- |
| AUTH-01 | Header thiếu | `/api/me` | 401 | Private yêu cầu Basic |
| AUTH-02 | analyst / đúng password | `/api/me` | 200, username đúng | Basic + BCrypt |
| AUTH-03 | admin / đúng password | `/api/me` | 200 | Nhiều users |
| AUTH-04 | analyst / password sai | `/api/me` | 401 | Phải verify password |
| AUTH-05 | Unknown user | `/api/me` | 401 | Không auto-provision user |
| AUTH-06 | Password rỗng | `/api/me` | 401 | Không có fallback credential |
| AUTH-07 | Malformed Base64 | `/api/me` | 401 | Parsing không bypass auth |
| AUTH-08 | Basic không có delimiter | `/api/me` | 401 | Header không chuẩn |
| AUTH-09 | Bearer scheme | `/api/me` | 401 | Không tự bật cơ chế khác |
| AUTH-10 | Colon trong password | `/api/me` | 200 | Parse đúng first colon |
| AUTH-11 | Không auth | `/public/ping` | 200 | Không chặn public |
| AUTHZ-01 | analyst đúng | `/api/reports` | 200 | Role ANALYST |
| AUTHZ-02 | admin đúng | `/api/reports` | 200 | Role ADMIN |
| AUTHZ-03 | analyst đúng | `/api/admin` | 403 | Authn ≠ authz |
| AUTHZ-04 | admin đúng | `/api/admin` | 200 | ADMIN |
| AUTHZ-05 | Không auth | `/api/admin` | 401 | Anonymous không có ADMIN |
| CSRF-01 | analyst Basic, thiếu CSRF | POST reports | 403 | Basic có thể được browser cache |
| CSRF-02 | analyst Basic + csrf() | POST reports | 201 | CSRF + role đủ |
| CSRF-03 | Password sai + csrf() | POST reports | 401 | CSRF không thay password |
| STATE-01 | Request sau bỏ header | `/api/me` | 401 | Không persist Basic identity |
| HTTP-01 | 401 challenge | `/api/me` | WWW-Authenticate Basic | Hợp đồng protocol |
| NET-01 | Basic thật trên TCP | `/api/me` | 200 | Network integration |

Bạn có thể sử dụng bảng làm test plan cho automation/QA nhưng không thay actual JUnit code. Một số nhóm muốn thêm case unauthorized POST body/Content-Type, user disabled/locked, password rotation, backend exceptions và rate limit; các mục này cần cấu hình provider và policy thêm, không thể suy ra từ lab mặc định.

## 16. Kiểm tra HTTP Basic bằng curl

Khởi động Spring Boot sau khi đặt secrets **local**. Với Bash:

~~~bash
export LAB_ANALYST_PASSWORD="lab-pass-123"
export LAB_ADMIN_PASSWORD="admin-pass-456"
export LAB_COLON_PASSWORD="pa:ss"
mvn spring-boot:run
~~~

Các giá trị trên là **demo password công khai**, tuyệt đối không dùng trong môi trường public. Với PowerShell:

~~~powershell
$env:LAB_ANALYST_PASSWORD = "lab-pass-123"
$env:LAB_ADMIN_PASSWORD = "admin-pass-456"
$env:LAB_COLON_PASSWORD = "pa:ss"
mvn spring-boot:run
~~~

Không có mật khẩu phù hợp, app fail fast trước khi mở service.

Gọi public endpoint:

~~~bash
curl -i "http://localhost:8080/public/ping"
~~~

Body dự kiến:

~~~json
{"status":"up"}
~~~

Gọi private endpoint thiếu Basic header:

~~~bash
curl -i "http://localhost:8080/api/me"
~~~

Status mong đợi: `HTTP/1.1 401` và một Basic challenge header theo entry point. Dùng curl cho phép nhập password sau prompt để không phải để password nguyên văn trong command-line arguments:

~~~bash
curl -i --user analyst "http://localhost:8080/api/me"
~~~

Nhập `lab-pass-123` khi công cụ hỏi. JSON dự kiến:

~~~json
{"username":"analyst"}
~~~

Với `GET /api/admin` dùng analyst Basic đúng, response mong đợi 403. Với admin Basic đúng, mong đợi 200 với:

~~~json
{"section":"admin"}
~~~

**Giới hạn môi trường:** URL localhost HTTP plaintext là lab. Ở production phải dùng HTTPS, bảo vệ password khi nhập, không copy Basic header vào issue/log/screenshot/CI. Lệnh curl với `--user username:password` trực tiếp có thể để lộ password trong process list và shell history; sử dụng prompt hoặc phương thức vault-aware.

## 17. Tình huống đặc biệt: Basic credentials trong browser và CSRF

Một nhầm lẫn phổ biến: “HTTP Basic là header-based và không dùng session, nên có thể tắt CSRF hoàn toàn.” Điều này **không đúng trong mọi trường hợp**.

Sau khi user xác thực Basic, một số browser có thể tự ghi nhớ và gửi lại `Authorization: Basic ...` đến cùng protected origin. Kẻ tấn công có thể lợi dụng browser thực hiện cross-site state-changing requests, nên Basic **cũng có thể là ambient credential**. Khi ứng dụng được browser truy cập và có `POST`, `PUT`, `PATCH` hoặc `DELETE`, cần đánh giá CSRF.

Trong lab, CSRF được giữ bật và test `POST /api/reports`:

~~~java
// Password đúng nhưng thiếu CSRF token:
client.post().uri("/api/reports")
    .headers(h -> h.setBasicAuth(
        "analyst", "lab-pass-123"))
    .exchange().expectStatus().isForbidden();

// Password đúng + CSRF mock token hợp lệ:
client.mutateWith(csrf())
    .post().uri("/api/reports")
    .headers(h -> h.setBasicAuth(
        "analyst", "lab-pass-123"))
    .exchange().expectStatus().isCreated();
~~~

`csrf()` trong `spring-security-test` cài token **hợp lệ cho security test context**; nó không có nghĩa client production có thể tự tạo token tương tự. Trong ứng dụng thật cần thiết kế cách browser nhận/gửi token, same-site cookies, Origin/Referer checks hoặc kiến trúc BFF/session tùy tình huống.

Nếu API thực sự chỉ nhận machine-to-machine clients, không có browser/cookie/auto-sent credentials và CSRF threat không tồn tại theo thiết kế, có thể **quyết định tắt CSRF cho chain phù hợp** sau khi threat model rõ ràng. Không lấy “Basic” làm lý do duy nhất và không tắt CSRF trên các chains có session/form login.

## 18. Vì sao một bài test 401 có thể cho kết quả khác mong đợi?

Nếu thiếu Basic mà test trả `302` redirect:
- Có thể formLogin vẫn bật, browser-oriented entry point được chọn.
- Test dùng Servlet `MockMvc`/MVC config thay vì WebFlux.
- Custom authentication entry point đã đổi behavior.
- Route private không thuộc security matcher bạn nghĩ.

Nếu password sai mà test lại trả `200`:
- Có `mockUser()`/`@WithMockUser` cài identity trước.
- Custom filter/matcher `permitAll()` quá rộng.
- Security test không apply `springSecurity()` hoặc bỏ qua security WebFilters.
- ReactiveAuthenticationManager custom trả Authentication authenticated mà không verify password.
- Một HTTP session/Basic cache khác làm request được authenticated, cần kiểm tra test client state.

Nếu correct Basic trả `401`:
- Password hash không khớp encoder, tài khoản bị disabled/locked.
- Username case-sensitivity hoặc password chứa ký tự mã hóa khác giữa client/server.
- `MapReactiveUserDetailsService` không chứa user test hoặc test properties chưa nạp.
- Có nhiều SecurityWebFilterChains và request đi vào chain khác.
- Security context bị lấy sai với reactive ThreadLocal code; dùng Reactor Context/AuthenticationPrincipal.

Nếu correct Basic trả `403`:
- Authentication đã thành công nhưng thiếu role/authority.
- Basic user có `ROLE_ANALYST` nhưng route yêu cầu `ROLE_ADMIN`.
- CSRF token thiếu cho request thay đổi dữ liệu.
- Business authorization cấm tenant/object hoặc `anyExchange().denyAll()` là rule match trước.
- Route/method matcher không khớp (ví dụ `POST` và `GET` khác nhau).

**Không sửa test bằng cách chuyển mọi expectation thành isOk hoặc disable security.** Đối chiếu route, header, manager, saved BCrypt hash, security chain ordering và error response.

## 19. Tình huống header nhiều giá trị, whitespace và encoding

RFC 7617 Basic credential cần cú pháp nhất quán. Những trường hợp đáng viết thêm negative tests:

- `Authorization: Basic` thiếu credentials.
- `Authorization: Basic !!!` chứa Base64 không hợp lệ.
- Base64 hợp lệ nhưng decoded text không có `:`.
- Username rỗng hoặc không tồn tại; password rỗng.
- Prefix scheme khác `Bearer` hoặc custom API key.
- Nhiều `Authorization` header values; cách server/proxy merge header không được mơ hồ.
- Dấu cách, tab, newline/control characters trong credential.
- Username Unicode/charset chưa thống nhất.
- Chuỗi decoded có dấu `:` trong **password**, không phải username.

**Không khẳng định mọi implementation đều trả 401 cho duplicated Authorization headers**: connector/proxy có thể join, server có thể chọn một hoặc từ chối. Quan trọng hơn là **không có bypass**; test trên phiên bản, reverse proxy và connector thực để định nghĩa đúng contract. Nếu policy cần bắt buộc đúng một Authorization value, tạo converter/filter chặn duplicates trước authentication và test mạng.

Một decoder tùy biến nên giới hạn header length để tránh huge Base64 khiến server tiêu thụ quá nhiều CPU/memory. Không log toàn bộ header để debug malformed requests.

### 19.1. Mã Java tạo Basic header phục vụ negative test

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

String encoded = Base64.getEncoder().encodeToString(
    "analyst:wrong-password".getBytes(
        StandardCharsets.ISO_8859_1));
String header = "Basic " + encoded;
~~~

Với positive tests, **ưu tiên** `HttpHeaders.setBasicAuth(username,password)` vì framework xây encoding đúng, test ngắn và dễ đọc. Chỉ tự Base64 khi cố ý thử malformed/edge conditions.

## 20. Những ranh giới ngoài phạm vi lab

**Password policy:** Lab dùng bcrypt hash và hardcoded dummy test users. Production cần password rotation, account lock/disable, credential stuffing protection, MFA cho human identities, breach checks và audit. Nếu API machine-to-machine, cân nhắc OAuth2 Client Credentials, mTLS, workload identity thay vì Basic dài hạn.

**User enumeration:** Dù status chung 401, thời gian xử lý unknown username so với wrong password có thể khác vì DB lookup/BCrypt. Muốn hạn chế timing leak có thể cần dummy BCrypt check, rate limit và thống kê phù hợp; đừng tuyên bố HTTP request constant-time chỉ vì message giống nhau.

**Database/outage:** Nếu ReactiveUserDetailsService trả lỗi vì DB unavailable, không được tự chuyển lỗi thành user authenticated hay cấp quyền anonymous. Fail closed; ánh xạ status phụ thuộc security exception handling. Alert dependency outages riêng thay vì thông báo password sai hàng loạt.

**Ratelimits và monitoring:** Nhận diện nhiều failed logins theo IP/account/workload, nhưng không log raw Authorization. Thêm quotas, backoff và CAPTCHA/MFA nếu phù hợp browser flow; tránh làm DoS bằng lockout không kiểm soát.

**Basic challenge UX:** Trình duyệt có thể cache credential và hiển thị login dialog. Có thể khác kỳ vọng SPA/mobile; response 401 và WWW-Authenticate có thể cần tùy biến, nhưng Basic protocol semantics vẫn phải rõ ràng.

**Domain auth:** Role ANALYST đủ GET reports trong lab, không có nghĩa có quyền đọc mọi báo cáo của tenant khác. Service/DB phải kiểm tra owner/tenant/resource ownership khi xử lý dữ liệu thật.

## 21. Tổ chức các test cho CI đáng tin

Một cấu trúc CI phù hợp:

~~~text
mvn clean test
  -> BasicFilterTest:
       Basic header parsing + BCrypt + 401/403/200 + CSRF
  -> BasicNetworkTest:
       Netty HTTP real server + valid/invalid credentials
  -> surefire-reports:
       XML/JUnit logs đã redact và summary
~~~

Gợi ý:
- Chạy tests trong Spring Boot version pin rõ, JDK 17+.
- Không dùng live production passwords/accounts.
- Mỗi test tự gửi credential, không giữ state từ test khác.
- Không phụ thuộc cổng 8080 cho network tests; dùng random port.
- Không để security disabled trong `test` profile chỉ để tests nhanh hơn.
- Theo dõi flakiness từ database/network/clock; lab không có external DB.
- Khi nâng Spring Security, chạy lại negative cases và header challenge semantics.
- Tránh bật wiretap HTTP headers trong CI logs.
- Có test riêng cho TLS/proxy và disabled users nếu production phụ thuộc chúng.

**Test chạy thành công không đủ bảo đảm security hoàn hảo.** Nhưng một negative test thất bại (ví dụ wrong password nhận 200) là tín hiệu nghiêm trọng cần sửa trước deploy.

## 22. Những sai lầm phổ biến trong bài kiểm thử HTTP Basic

1. Dùng `mockUser()` để chứng minh username/password đúng.
2. Chỉ test 200 với correct credentials mà quên invalid.
3. Hardcode real password vào source/test fixtures.
4. Dùng `@WebFluxTest` nhưng quên import custom SecurityWebFilterChain.
5. Test controller riêng không cài `springSecurity()` rồi tưởng auth pass.
6. Khởi động `MockMvc` trên WebFlux application.
7. Gửi `Bearer` khi server chỉ cấu hình Basic.
8. Truyền plaintext password qua HTTP internet vì “đã Base64”.
9. Log `Authorization` header để debug 401.
10. Nhầm password sai 401 với role thiếu 403.
11. Nhầm CSRF 403 với password sai.
12. Không test `WWW-Authenticate`/client challenge contract.
13. Bật formLogin và Basic đồng thời không chủ ý, làm 302 thay cho 401.
14. Không cấu hình `NoOpServerSecurityContextRepository` khi muốn per-request Basic semantics.
15. Cho phép mọi route vì `anyExchange().permitAll()`.
16. Dùng một tài khoản admin trong tất cả tests nên không thấy lỗi role.
17. Tự tạo Base64 sai charset/colon delimiter rồi coi là bug server.
18. Chỉ kiểm HTTP status mà không kiểm JSON không lộ password.
19. Tắt CSRF vô điều kiện vì “Basic không có cookie”.
20. Không test missing header sau successful request, bỏ sót session persistence.
21. Không test qua Netty khi phụ thuộc proxy/header forwarding.
22. Không có rate limits hoặc alert cho brute-force attempts trong production.
23. Đồng nhất unknown user và DB outage trong vận hành.
24. Đưa password vào curl command-line, shell history và screenshots.
25. Thay acceptance criteria bằng expectation tùy ý khi security test fail.

## 23. Bài tập thực hành

**A — Authentication matrix:** Thêm 401 tests cho unknown username, wrong password, empty password, malformed Base64, Basic thiếu dấu `:`, Bearer scheme. Chứng minh không có private response 200.

**B — Authorization:** Đăng nhập analyst bằng Basic thật, gọi `/api/admin` và nhận 403. Đổi thành admin đúng password và nhận 200. Giải thích tại sao hai kết quả không giống authentication failure.

**C — Browser CSRF:** POST bằng Basic hợp lệ nhưng thiếu CSRF → 403; thêm `csrf()` trong WebTestClient → 201. Nêu vì sao bản production cần cơ chế phát CSRF token, không chỉ dùng mock.

**D — Colon delimiter:** Tài khoản colon có password `pa:ss`, xác minh header Basic vẫn được parse đúng khi phân tách dấu hai chấm **đầu tiên**.

**E — WWW-Authenticate:** Kiểm tra challenge Basic trên request chưa auth; custom realm rồi cập nhật assertion, không leak info tài khoản.

**F — Network integration:** Chạy `BasicNetworkTest` trên random port, đảm bảo Basic header đến đúng Netty/WebFlux. Thử reverse proxy test ở staging.

**G — Mock pitfalls:** Viết một test `mockUser` đọc reports dù password trong DB sai, sau đó giải thích vì sao đây không phải bug của mock mà là test sai mục tiêu.

**H — No persistence:** Gửi một Basic request đúng, request tiếp theo bỏ header; xác minh 401 và kiểm tra cookies/WebSession nếu ứng dụng thay config.

**I — Error sanitization:** Log 401/403 status và safe correlation ID, không ghi Authorization/password/BCrypt hash. Viết test hoặc integration assertion cho logging filter.

**J — Production provider:** Thay MapReactiveUserDetailsService bằng R2DBC/LDAP/custom manager trong staging, giữ nguyên credential tests và thêm disabled/locked user cases.

**K — Brute force:** Tạo nhiều login failures ở môi trường controlled, áp rate limit theo IP/account, đo không lộ tài khoản tồn tại qua body/status.

**L — HTTPS:** Dùng TLS test certificate ở staging, xác minh không có Basic credentials trên đường truyền không mã hóa hoặc proxy logs.

## 24. Checklist trước khi gọi bộ test hoàn chỉnh

- [ ] Private endpoints không nhận anonymous requests.
- [ ] Correct username/password Basic trả 200 và principal đúng.
- [ ] Incorrect password/unknown username trả 401 chung.
- [ ] Malformed/missing header và wrong scheme không bypass auth.
- [ ] `WWW-Authenticate` được kiểm tra theo hợp đồng client.
- [ ] Account roles từ UserDetails được kiểm đúng ở routes.
- [ ] Authenticated user thiếu role nhận 403, khác 401.
- [ ] Không có mockUser trong tests muốn chứng minh BCrypt credential verification.
- [ ] WebTestClient bind ApplicationContext có `springSecurity()`.
- [ ] Ít nhất vài tests qua Netty HTTP thực, random port.
- [ ] Không lưu Authentication trong session nếu yêu cầu per-request Basic.
- [ ] CSRF được đánh giá cho browser Basic và các state-changing routes.
- [ ] Không có secrets/hash trong JSON response, logs, exceptions hoặc screenshots.
- [ ] JDK/Maven/Spring Boot versions rõ ràng, không giả định test đã được chạy.
- [ ] Có cách debug khác nhau cho 401 authn, 403 authz, 403 CSRF.
- [ ] TLS và secret management/rate limits có kế hoạch production.
- [ ] Dữ liệu tenant/owner vẫn được kiểm ở service/DB, không chỉ HTTP roles.

## 25. Câu hỏi tự kiểm tra

1. HTTP Basic gửi header nào và Base64 có mã hóa thông tin mật khẩu hay không?
2. Vì sao Basic phải chạy trên HTTPS?
3. `HttpHeaders.setBasicAuth` giúp tests tốt hơn việc tự ghép header thế nào?
4. Vì sao cần WebTestClient `springSecurity()` khi bind ApplicationContext?
5. `mockUser` có kiểm tra BCrypt password không?
6. Correct credential nhưng thiếu ADMIN phải trả 401 hay 403?
7. Tại sao 403 từ CSRF không có nghĩa password sai?
8. Browser có thể tự gửi Basic credential đã cache không?
9. `NoOpServerSecurityContextRepository` có loại bỏ mọi WebSession do CSRF tạo không?
10. Vì sao password có dấu hai chấm vẫn có thể hợp lệ trong Basic?
11. Token `Bearer` có được chấp nhận khi security chỉ bật Basic không?
12. Kết quả gì nên thấy khi request sau không còn Authorization header?
13. Cách kiểm tra challenge Basic mà không hardcode realm là gì?
14. Khi user không tồn tại và khi password sai, API nên tiết lộ lý do khác nhau không?
15. Khi có nhiều SecurityWebFilterChains, test cần xác nhận điều gì?
16. Khi cần dùng WebFlux test slice `@WebFluxTest`, làm sao không bỏ security config?
17. Vì sao Basic header hợp lệ không đồng nghĩa có quyền dữ liệu tenant khác?
18. Nếu BasicNetworkTest pass ở localhost, TLS/proxy đã được chứng minh chưa?
19. Vì sao phải có negative tests cho header parse chứ không chỉ 200?
20. Khi dependency account store down, server có nên coi authentication thành công không?

## 26. Nguồn tham khảo

- [Spring Security — WebFlux Security Configuration](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html): `ServerHttpSecurity`, reactive user details và SecurityWebFilterChain.
- [Spring Security — Testing Authentication (Reactive)](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html): `mockUser`/`@WithMockUser` và test security context.
- [Spring Security — Testing with CSRF (Reactive)](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html): `SecurityMockServerConfigurers.csrf()`.
- [Spring Security — WebFlux HTTP Authorization](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html): route authorization rules.
- [Spring Security — WebFlux HTTP Basic](https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/passwords/http-basic.html): Basic authentication trong WebFlux.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, WebTestClient, random port và test slices.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): bindToApplicationContext, server response assertions và testing HTTP.
- [RFC 7617 — The Basic HTTP Authentication Scheme](https://www.rfc-editor.org/rfc/rfc7617): header, Base64, challenge/realm, delimiter/charset.
- [RFC 7235 — HTTP Authentication](https://www.rfc-editor.org/rfc/rfc7235): WWW-Authenticate challenge semantics (đã được thay thế bởi RFC 9110).
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): 401/403 và HTTP authentication.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): password/credential errors và chống enumeration.
- [OWASP — Cross-Site Request Forgery Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): CSRF khi browser auto-sends credentials.
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): BCrypt và password hashing.
- [OWASP — Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): HTTPS/TLS và credential confidentiality.

**Kết luận:** Với Spring Security Reactive, **kiểm thử HTTP Basic đúng** là gửi `Authorization: Basic ...` thực sự bằng `WebTestClient.headers(h -> h.setBasicAuth(...))` và quan sát phản hồi từ SecurityWebFilterChain + ReactiveAuthenticationManager + PasswordEncoder. Correct username/password trên route đủ quyền → 200; thiếu/sai credential → 401; authenticated nhưng thiếu role → 403. Đừng dùng `mockUser()` để chứng minh password verification, đừng coi Base64 là encryption và đừng vô hiệu hóa CSRF chỉ vì Basic không dùng session. Kết hợp tests in-memory và Netty network, negative cases về header, role và CSRF để tránh false confidence.