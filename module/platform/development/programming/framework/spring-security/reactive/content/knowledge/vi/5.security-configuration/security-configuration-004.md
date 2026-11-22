# Nhiều SecurityWebFilterChain với @Order và nguyên tắc chọn chuỗi phù hợp đầu tiên

> **Module:** Spring Security - reactive · **Chủ đề cha:** Cấu hình bảo mật  
> **Mục tiêu:** Biết khi nào tách cấu hình bảo mật thành nhiều `SecurityWebFilterChain` trong Spring WebFlux, hiểu chính xác thứ tự `@Order`, phạm vi `securityMatcher` và hậu quả khi hai chain cùng khớp một request. Bài có ví dụ Java 17+ sử dụng Spring Security Reactive, HTTP Basic, kiểm thử WebTestClient và tình huống cấu hình sai dẫn đến mở quyền quá rộng.

## 1. Bài toán: một ứng dụng, nhiều vùng bảo mật

Một ứng dụng WebFlux có thể có những khu vực yêu cầu chính sách khác nhau:

- `GET /api/status`: kiểm tra API công khai, không cần đăng nhập.
- `GET /api/profile`: API thông thường, cần tài khoản đã xác thực.
- `GET /api/admin/report`: API quản trị, cần role `ADMIN`.
- `GET /health`: điểm kiểm tra sức khỏe công khai.
- Những đường dẫn khác: không tự động cho phép truy cập.

Có thể biểu diễn tất cả bằng **một chain** với nhiều rule. Tuy nhiên, khi khu vực cần cách đăng nhập, filter, xử lý lỗi, CSRF hoặc phạm vi khác nhau, Spring Security Reactive cho phép khai báo **nhiều bean `SecurityWebFilterChain`**. Mỗi bean mô tả một security chain độc lập.

Câu hỏi then chốt: nếu `GET /api/admin/report` đồng thời khớp `/api/admin/**` và `/api/**`, Spring Security sẽ áp dụng cả hai chain, gộp quyền của chúng, hay chọn một chain?

**Trả lời:** Spring Security xét các chain theo thứ tự ưu tiên và **chọn chain đầu tiên có `securityMatcher` khớp request**. Chỉ chain được chọn xử lý request; nó không chạy tiếp các chain có ưu tiên thấp hơn để “cộng thêm” hoặc “kiểm tra lại” quyền. Vì vậy, `@Order` ảnh hưởng trực tiếp đến bảo mật.

## 2. Tách hai giai đoạn: chọn chain và cấp quyền bên trong chain

Phải phân biệt rõ hai câu hỏi.

| Giai đoạn | API liên quan | Câu hỏi | Kết quả |
| --- | --- | --- | --- |
| **Chọn chain** | `ServerHttpSecurity.securityMatcher(ServerWebExchangeMatcher)` | Security chain nào chịu trách nhiệm request này? | Lấy chain **đầu tiên** khớp theo `@Order` |
| **Cấp quyền trong chain** | `authorizeExchange(...).pathMatchers(...)/anyExchange()` | Request trong chain đã chọn có đủ quyền không? | Cho phép, yêu cầu xác thực hoặc từ chối |
| **Thực thi endpoint** | Router/controller, service, repository | Nếu được phép, endpoint nào và dữ liệu nào được xử lý? | Response/logic nghiệp vụ |

**`securityMatcher` quyết định phạm vi của toàn chain.** Các `pathMatchers` trong `authorizeExchange` chỉ quyết định **quyền trong chain đã được chọn**. Đặt `pathMatchers("/api/admin/**")` trong chain API chung không tự làm chain đó có ưu tiên cao hơn.

Hình dung:

~~~mermaid
flowchart TD
    R["HTTP request"] --> A{"Chain @Order(1): /api/admin/** ?"}
    A -->|"Khớp"| AA["Chọn chain ADMIN → kiểm tra ROLE_ADMIN"]
    A -->|"Không"| B{"Chain @Order(2): /api/** ?"}
    B -->|"Khớp"| BB["Chọn chain API → rule công khai / xác thực"]
    B -->|"Không"| C{"Chain @Order(3): mọi request?"}
    C -->|"Khớp"| CC["Chọn chain FALLBACK → /health public; còn lại denyAll"]
    C -->|"Không"| D["Không chain nào chọn: nguy cơ thiếu bảo vệ"]
    AA --> E["Quyết định cho phép / từ chối; KHÔNG chạy chain tiếp"]
    BB --> E
    CC --> E
~~~

Trong ví dụ sắp xây dựng, chain cuối **không** gọi `securityMatcher`, do đó dùng matcher mặc định khớp mọi request còn lại. Nhờ thế tất cả request có một chain chịu trách nhiệm. Một cấu hình chỉ có các chain giới hạn đường dẫn mà thiếu catch-all có thể để request không khớp chain nào, tức không được bảo vệ bởi những security chain đó. Không coi đây là cách tạo endpoint công khai: dùng `permitAll()` trong chain phù hợp để chính sách vẫn rõ ràng.

## 3. Ý nghĩa chính xác của @Order

Spring xét các bean `SecurityWebFilterChain` theo thứ tự được Spring quản lý:

- Giá trị `@Order` **nhỏ hơn được xét trước**: `@Order(1)` đứng trước `@Order(2)`, rồi `@Order(3)`.
- `Ordered.HIGHEST_PRECEDENCE` là hằng số thể hiện mức ưu tiên cao nhất; không cần dùng nó nếu các giá trị 1, 2, 3 đã rõ và duy nhất.
- `@Order` đặt trên method `@Bean` khai báo chain. Không dựa vào thứ tự method xuất hiện trong file Java hoặc thứ tự bean được viết ra.
- Nên chọn các giá trị thứ tự **khác nhau và được ghi rõ** cho các chain có matcher chồng lấp. Nếu hai chain có cùng độ ưu tiên, đừng dựa vào thứ tự tình cờ để bảo đảm an ninh.
- `@Order` không nói rằng chain đó “có quyền mạnh hơn”; nó chỉ quyết định **thứ tự được thử**. Quyền thật sự nằm ở rule authorization của chain được chọn.

**Nguyên tắc an toàn với đường dẫn chồng lấp:** matcher cụ thể hơn phải được xét **trước** matcher rộng hơn, ví dụ:

| Chain | `@Order` | `securityMatcher` | Chính sách |
| --- | --- | --- | --- |
| Admin | 1 | `/api/admin/**` | `hasRole("ADMIN")` |
| API chung | 2 | `/api/**` | `/api/status` public, API khác cần đăng nhập |
| Fallback | 3 | Match-all mặc định | `/health` public, còn lại từ chối |

Một request `GET /api/admin/report` khớp cả ba phạm vi, nhưng **chỉ chain Admin** được chọn do ưu tiên cao nhất.

## 4. Dựng ví dụ Spring Boot WebFlux

Ví dụ dùng Java 17+ và Spring Security 6.x qua Spring Boot 3.3.x để tập trung vào API chain selection. Nếu triển khai dự án mới, chọn phiên bản Spring Boot/Spring Security còn được hỗ trợ; không dùng phiên bản demo làm mặc định an ninh production. Mã mẫu này đặt trong dự án Maven độc lập; code không dùng API Servlet MVC.

Cấu trúc:

~~~text
multi-reactive-chains/
├── pom.xml
└── src/
    ├── main/java/demo/multichain/
    │   ├── MultiChainApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/demo/multichain/
        └── MultiChainSecurityTest.java
~~~

### 4.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>multi-reactive-chains</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
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

`spring-boot-starter-webflux` đưa vào WebFlux và Reactor; `spring-boot-starter-security` đưa vào Spring Security; `spring-boot-starter-test` hỗ trợ Spring Test/JUnit 5/WebTestClient. Không thêm `spring-boot-starter-web` vào ví dụ để tránh chuyển ứng dụng sang Servlet MVC do Spring Boot ưu tiên MVC khi cả hai starter web cùng hiện diện.

### 4.2. Entry point

File `src/main/java/demo/multichain/MultiChainApplication.java`:

~~~java
package demo.multichain;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MultiChainApplication {
    public static void main(String[] args) {
        SpringApplication.run(MultiChainApplication.class, args);
    }
}
~~~

### 4.3. Cấu hình ba SecurityWebFilterChain

File `src/main/java/demo/multichain/SecurityConfig.java`:

~~~java
package demo.multichain;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    // Chain cụ thể nhất: chỉ xử lý /api/admin/**
    @Bean
    @Order(1)
    SecurityWebFilterChain adminChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/admin/**")
            )
            .authorizeExchange(exchanges -> exchanges
                .anyExchange().hasRole("ADMIN")
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }

    // Chain rộng hơn: chỉ được thử khi adminChain không khớp.
    @Bean
    @Order(2)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**")
            )
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/status").permitAll()
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }

    // Catch-all: bảo vệ mọi request ngoài hai vùng trên.
    @Bean
    @Order(3)
    SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/health").permitAll()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder passwordEncoder) {
        UserDetails member = User.withUsername("member")
            .password(passwordEncoder.encode("member-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(passwordEncoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(member, admin);
    }
}
~~~

**Cách đọc đúng đoạn mã:**

1. `@EnableWebFluxSecurity` bật WebFlux security. Mỗi method `@Bean` trả về **một chain riêng** với matcher, authorization và HTTP Basic riêng. `ServerHttpSecurity` được cấu hình cho từng bean rồi gọi `build()`.
2. `adminChain` có matcher `/api/admin/**` và ưu tiên 1. Một khi request khớp, `anyExchange().hasRole("ADMIN")` có nghĩa là **mọi request bên trong phạm vi chain Admin** phải mang authority `ROLE_ADMIN`. Không phải mọi đường dẫn của toàn ứng dụng cần ADMIN.
3. `apiChain` có matcher `/api/**` và ưu tiên 2. Nó được xét khi chain Admin không khớp. `GET /api/status` được mở bằng `permitAll()`; phần API còn lại yêu cầu `authenticated()`.
4. `fallbackChain` không gắn `securityMatcher` cụ thể, vì thế nhận các request còn lại; `GET /health` public, mọi request khác bị `denyAll()`. Đây là lựa chọn deny-by-default để không bỏ lọt URL do thiếu cấu hình security.
5. `httpBasic(Customizer.withDefaults())` bật HTTP Basic trong từng chain để demo cùng một user store. `formLogin(...disable)` tránh điều hướng tới HTML login page thay vì thử thách HTTP Basic cho API.
6. Tài khoản `member` có `ROLE_USER`; `admin` có `ROLE_ADMIN`. Chúng chỉ dùng để học tại localhost; mật khẩu demo được mã hóa qua `PasswordEncoder` khi tạo user in-memory. Không đưa credential cố định vào source production.
7. Ví dụ **giữ nguyên CSRF** mặc định: các API GET trong bài là thao tác đọc. Khi mở thêm POST/PUT/DELETE, CSRF có thể ảnh hưởng status; cần quyết định theo cách client mang credentials, không tắt toàn bộ CSRF chỉ để test pass.
8. Thứ tự quyết định **chọn chain** nằm ở `@Order` và `securityMatcher`. Thứ tự quyết định **quyền trong từng chain** nằm ở các rule `authorizeExchange`. Đây là hai tầng độc lập.

Đừng coi hai khai báo `.anyExchange()` ở hai chain khác nhau là đè nhau. Mỗi rule chỉ tồn tại trong chain riêng được chọn. Ngược lại, đặt `.anyExchange()` sớm bên trong cùng một chuỗi rule có thể che các rule cụ thể đi sau.

## 5. Controller để kiểm chứng chain nào được chọn

File `src/main/java/demo/multichain/DemoController.java`:

~~~java
package demo.multichain;

import java.util.Map;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping("/api/status")
    public Mono<Map<String, String>> apiStatus() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping("/api/profile")
    public Mono<Map<String, String>> profile() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> Map.of(
                "username", context.getAuthentication().getName()
            ));
    }

    @GetMapping("/api/admin/report")
    public Mono<Map<String, String>> adminReport() {
        return Mono.just(Map.of("report", "admin-only"));
    }

    @GetMapping("/health")
    public Mono<Map<String, String>> health() {
        return Mono.just(Map.of("status", "UP"));
    }

    @GetMapping("/internal/ping")
    public Mono<Map<String, String>> internalPing() {
        return Mono.just(Map.of("status", "hidden"));
    }
}
~~~

`internalPing()` cố ý tồn tại để chứng minh **có handler không có nghĩa request được phép tới handler**. Request `/internal/ping` sẽ thuộc fallback chain; `anyExchange().denyAll()` ngăn endpoint hoạt động ngay cả khi client gửi credentials hợp lệ.

Dữ liệu trả về dùng `Map<String,String>` cố định, nên không cần database. Với profile, lấy principal qua `ReactiveSecurityContextHolder` trong pipeline reactive. Không dùng `ThreadLocal` như giả định thường gặp khi làm Servlet MVC.

## 6. Theo dõi chi tiết từng request

### Trường hợp A: GET /api/admin/report bằng member

1. Admin matcher `/api/admin/**` khớp.
2. Chain Admin được **chọn ngay**, không xét API chain và fallback.
3. HTTP Basic xác thực người dùng `member` thành công, nhưng user chỉ có `ROLE_USER`.
4. Rule `hasRole("ADMIN")` từ chối → kỳ vọng **403 Forbidden**.
5. Spring Security **không thử tiếp** apiChain, dù apiChain có `anyExchange().authenticated()` và member đã đăng nhập.

Đây là bằng chứng quan trọng nhất: nếu security chạy chuỗi chain theo kiểu “thử tới khi được cấp quyền”, member sẽ lọt vào admin. Spring Security không hoạt động như vậy.

### Trường hợp B: GET /api/profile bằng member

1. Chain Admin không khớp.
2. Chain API khớp `/api/**`, được chọn.
3. Không khớp đường dẫn public `GET /api/status` nên tới `anyExchange().authenticated()`.
4. HTTP Basic hợp lệ tạo Authentication cho `member` → controller trả username, kỳ vọng **200 OK**.

### Trường hợp C: GET /api/status không có credentials

1. Admin không khớp, API khớp.
2. Rule `permitAll()` cho phép anonymous → **200 OK**.
3. Endpoint không cần tự kiểm tra/đọc `SecurityContext`.

`permitAll()` không hứa bỏ qua mọi authentication filter. Nếu client cố ý gửi header Basic **sai**, filter có thể trả 401 trước khi tới kết quả public; test nghĩa “public” phải thực hiện với request **không mang credentials**.

### Trường hợp D: GET /health không có credentials

Hai matcher cụ thể đều không khớp. Fallback nhận request; rule `GET /health` cho phép anonymous → **200 OK**.

### Trường hợp E: GET /internal/ping bằng member

Admin và API không khớp. Fallback nhận request; `denyAll()` từ chối dù user đã đăng nhập → kỳ vọng **403 Forbidden**. Không có “fallback tiếp theo” vì đây là chain cuối.

## 7. Ma trận route, matcher, chain và kết quả

| Request | Chain đầu tiên khớp | Điều kiện authorization | Kết quả kỳ vọng |
| --- | --- | --- | --- |
| `GET /api/status`, anonymous | API (2) | `permitAll()` | 200 |
| `GET /api/profile`, anonymous | API (2) | `authenticated()` | 401 |
| `GET /api/profile`, member | API (2) | Đã xác thực | 200 |
| `GET /api/admin/report`, anonymous | Admin (1) | Chưa xác thực cho rule ADMIN | 401 |
| `GET /api/admin/report`, member | Admin (1) | Thiếu `ROLE_ADMIN` | 403 |
| `GET /api/admin/report`, admin | Admin (1) | Có `ROLE_ADMIN` | 200 |
| `GET /health`, anonymous | Fallback (3) | `permitAll()` | 200 |
| `GET /internal/ping`, member | Fallback (3) | `denyAll()` | 403 |

Kết quả dự kiến áp dụng cho **cấu hình HTTP Basic của ví dụ**. Nếu dự án thay HTTP Basic bằng form login/OAuth2/JWT, entry point và response có thể khác. Không dựa duy nhất vào status để suy ngược chain nào được chọn nếu chưa kiểm tra matcher và cấu hình xác thực.

## 8. Kiểm thử tự động bằng WebTestClient

File `src/test/java/demo/multichain/MultiChainSecurityTest.java`:

~~~java
package demo.multichain;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class MultiChainSecurityTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicApiWorksWithoutCredentials() {
        client.get().uri("/api/status")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    void apiProfileRejectsAnonymous() {
        client.get().uri("/api/profile")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void normalUserCanViewProfile() {
        client.get().uri("/api/profile")
            .headers(h -> h.setBasicAuth("member", "member-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.username").isEqualTo("member");
    }

    @Test
    void normalUserCannotEnterAdminChain() {
        client.get().uri("/api/admin/report")
            .headers(h -> h.setBasicAuth("member", "member-pass"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminCanEnterAdminChain() {
        client.get().uri("/api/admin/report")
            .headers(h -> h.setBasicAuth("admin", "admin-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.report").isEqualTo("admin-only");
    }

    @Test
    void healthIsHandledByFallback() {
        client.get().uri("/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.status").isEqualTo("UP");
    }

    @Test
    void fallbackDeniesInternalRouteEvenWhenAuthenticated() {
        client.get().uri("/internal/ping")
            .headers(h -> h.setBasicAuth("member", "member-pass"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminRouteRejectsAnonymous() {
        client.get().uri("/api/admin/report")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

Chạy trong thư mục chứa `pom.xml`:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Các bài test gọi ứng dụng thực ở cổng ngẫu nhiên và đi qua security filters. Chúng kiểm tra hiệu ứng của chain selection kết hợp authentication/authorization. Không tự gọi controller bằng `new DemoController()` để “test SecurityWebFilterChain” vì lời gọi trực tiếp bỏ qua HTTP security.

**Bài test có giá trị nhất là** `normalUserCannotEnterAdminChain()`: nó chống hồi quy khi ai đó vô tình đổi thứ tự chain hoặc nới `securityMatcher`. Dù member hợp lệ với API chung, họ vẫn bị từ chối ở vùng admin.

Ví dụ dùng user in-memory để dễ thử. Một dự án có database/identity provider riêng phải cấu hình phương thức xác thực, quyền và test fixture tương ứng; không được hiểu rằng dữ liệu user ở ví dụ là cơ chế cấp quyền cho hệ thống thực.

## 9. Thử tay bằng curl

Chạy ứng dụng rồi thử từ terminal khác. Với PowerShell 5.1, dùng `curl.exe` để tránh alias `curl`.

**API công khai:**

~~~bash
curl -i http://localhost:8080/api/status
~~~

Kỳ vọng HTTP 200 và body:

~~~json
{"status":"ok"}
~~~

**API yêu cầu đăng nhập, gọi ẩn danh:**

~~~bash
curl -i http://localhost:8080/api/profile
~~~

Kỳ vọng HTTP 401 (thường có `WWW-Authenticate: Basic ...`).

**Member truy cập profile:**

~~~bash
curl -i -u member http://localhost:8080/api/profile
~~~

curl hỏi mật khẩu, nhập `member-pass`. Kỳ vọng HTTP 200 và:

~~~json
{"username":"member"}
~~~

**Member truy cập admin, bị chặn:**

~~~bash
curl -i -u member http://localhost:8080/api/admin/report
~~~

Nhập `member-pass`, kỳ vọng HTTP 403 vì request dừng tại **adminChain**; không được chuyển sang apiChain để thử rule dễ hơn.

**Admin truy cập admin:**

~~~bash
curl -i -u admin http://localhost:8080/api/admin/report
~~~

Nhập `admin-pass`, kỳ vọng HTTP 200:

~~~json
{"report":"admin-only"}
~~~

**Fallback:**

~~~bash
curl -i http://localhost:8080/health
curl -i -u member http://localhost:8080/internal/ping
~~~

Lệnh đầu kỳ vọng 200, lệnh sau nhập `member-pass` và kỳ vọng 403.

Trên môi trường thực, HTTP Basic phải đi qua **HTTPS**: chuỗi Base64 không phải mã hóa bảo mật. Tránh đưa mật khẩu thực trực tiếp vào command history. Các user/password trên chỉ dành cho localhost.

## 10. Trường hợp sai nguy hiểm: đảo thứ tự chain

Giả sử người lập trình vô tình đổi thứ tự như sau (chỉ là **minh họa lỗi**, không áp dụng):

~~~java
@Bean
@Order(1)
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**")
        )
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityWebFilterChain adminChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/admin/**")
        )
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().hasRole("ADMIN")
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

`GET /api/admin/report` khớp cả hai matcher. Chain API có `@Order(1)` nên được chọn **trước**, áp dụng `authenticated()`. Người dùng `member` có tài khoản hợp lệ, vì thế **qua được kiểm tra ở tầng security** và có thể tới admin controller nếu không có biện pháp khác. Chain Admin với role chặt hơn **không bao giờ được dùng** cho request đó.

Đây là lỗi **shadowing chain**: matcher rộng hơn “che” matcher cụ thể. Nó có thể dẫn đến lộ chức năng quản trị, dù khi đọc riêng từng chain dường như cả hai đều đúng.

**Sửa đúng:** đặt `adminChain` với thứ tự ưu tiên cao hơn `apiChain`, hoặc thiết kế các matcher **không chồng lấp** và kiểm tra rõ đường dẫn loại trừ. Đừng kỳ vọng rule `hasRole("ADMIN")` trong một chain ít ưu tiên hơn sẽ bổ sung vào chain đã chọn.

## 11. Trường hợp sai khác: chain đầu không có securityMatcher

Sai lầm khác:

~~~java
@Bean
@Order(1)
SecurityWebFilterChain broadChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Nếu method này được đặt trước các chain Admin/API và **không có `securityMatcher` cụ thể**, nó sẽ khớp mọi request. Các chain sau không còn cơ hội xử lý đường dẫn nào. Một số endpoint sẽ yêu cầu đăng nhập sai mong muốn; nghiêm trọng hơn, những endpoint cần role đặc biệt có thể chỉ còn rule `authenticated()` quá rộng.

**Kinh nghiệm:** dùng catch-all ở cuối; viết kiểm thử cho các đường dẫn chồng lấp; ghi rõ matcher của từng chain trong code review.

## 12. Thiếu fallback: có thể tạo khoảng trống bảo vệ

Nếu chỉ khai báo:

~~~java
.securityMatcher(
    new PathPatternParserServerWebExchangeMatcher("/api/**")
)
~~~

và không còn chain nào khác nhận `/internal/**`, request ngoài `/api/**` có thể **không được xử lý bởi bất kỳ SecurityWebFilterChain nào**. Nếu handler vẫn tồn tại, bạn có thể vô tình để lộ endpoint do không có bảo vệ ở lớp HTTP security. Đừng cho rằng “không khớp chain” tức tự động `denyAll()`.

Có hai cách bảo vệ thiết kế:

1. Dùng một fallback chain khớp mọi request còn lại, đặt cuối cùng; cấu hình rõ `permitAll()` cho endpoint công khai và `denyAll()` hoặc `authenticated()` cho phần còn lại.
2. Nếu chỉ muốn security áp dụng cho một phạm vi rất hẹp, hãy coi đó là quyết định kiến trúc có chủ đích; phải đánh giá toàn bộ URL khác và có test xác nhận phạm vi ngoài security.

**Không nhầm `anyExchange().denyAll()` với catch-all matcher.** `anyExchange()` chỉ chặn những request **đã được đưa vào chain đó**. Một chain có `securityMatcher("/api/**")` và `anyExchange().denyAll()` không thể chặn `/internal/ping` nếu request đó chưa hề khớp matcher của chain.

## 13. Phân biệt hai loại thứ tự thường bị nhầm

### 13.1. Thứ tự các chain

~~~text
Request
  ├─ adminChain @Order(1), matcher /api/admin/**
  ├─ apiChain   @Order(2), matcher /api/**
  └─ fallback   @Order(3), matcher mặc định match-all
                 → DỪNG ở chain đầu tiên khớp
~~~

### 13.2. Thứ tự các rule trong một chain

~~~java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers(HttpMethod.GET, "/api/status").permitAll()
    .anyExchange().authenticated()
)
~~~

Trong chain API, rule cụ thể `/api/status` cần được khai báo trước rule rộng `anyExchange()`. Nếu rule tổng quát chiếm mọi request trước, rule cụ thể phía sau có thể không có tác dụng (hoặc cấu hình bị Spring Security từ chối).

Hai tầng ordering vận hành riêng biệt:

- `@Order` sắp **bean chain**.
- Thứ tự `pathMatchers` sắp **rule authorization trong một chain**.
- `securityMatcher` gắn phạm vi cho chain.
- `anyExchange` gắn fallback rule cho **request trong chain**.

Học được cách phân biệt hai tầng này giúp tránh sửa nhầm: khi `/api/admin/report` lọt qua, cần kiểm tra chain được chọn **trước** khi sửa các rule bên trong một chain có thể chưa từng được gọi.

## 14. Dùng nhiều chain để tách cơ chế xác thực

Ví dụ vừa rồi dùng HTTP Basic cho cả ba chain để tập trung vào việc chọn chain. Trong thực tế, mỗi chain có thể dùng cơ chế riêng:

| Vùng ứng dụng | Matcher ví dụ | Cơ chế thường gặp | Kiểm tra cần bổ sung |
| --- | --- | --- | --- |
| Resource Server API | `/api/**` | OAuth2 Bearer JWT | Chữ ký, thời hạn, issuer, audience, scope |
| Web quản trị | `/admin/**` | Session + form login/OIDC | Role, MFA, session/CSRF |
| Dịch vụ nội bộ | `/internal/**` | Token nội bộ hoặc mTLS ở gateway | Chính sách mạng, service identity |
| Fallback | Match-all | Theo chính sách | Không để đường dẫn ngoài phạm vi được mở |

Trong Spring Security WebFlux, cấu hình xác thực được thiết lập **trên từng chain**. Cấu hình `oauth2ResourceServer(...jwt(...))` cho chain API không có nghĩa một chain khác tự kế thừa cơ chế đó. Khi áp dụng JWT, cần có bộ giải mã/issuer thật và kiểm thử token hợp lệ/không hợp lệ riêng. **Đừng chỉ decode payload và tin claim.**

Nếu ứng dụng dùng cookie/session cho một vùng, phải đánh giá CSRF phù hợp ở vùng đó. Nếu API stateless dùng Bearer header do client chủ động gắn và không dựa vào cookie để xác thực, có thể đánh giá tắt CSRF tại API chain theo threat model. Không nên tắt toàn bộ bảo vệ chỉ vì một chain khác dùng token.

CORS cũng có thể cấu hình khác theo vùng, nhưng **CORS không thay thế authentication/authorization**. Nhiều chain tạo ra nhiều điểm cấu hình; cần kiểm thử tính nhất quán của headers, login/logout, CSRF, exception handling và CORS theo đường dẫn thật.

## 15. Quy trình chẩn đoán khi route bị cho phép hoặc từ chối sai

Khi một đường dẫn trả 200, 401, 403 hoặc 404 ngoài mong đợi, đi theo đúng chuỗi:

1. Xác định **HTTP method + path** thực tế, kể cả prefix tại proxy/gateway và đường dẫn sau reverse proxy. Query string không phải yếu tố thay thế matcher path.
2. Liệt kê các `SecurityWebFilterChain` và giá trị `@Order`; xác định chain nào được xét đầu tiên.
3. Kiểm tra **`securityMatcher` của từng chain**; chỉ ra chain **đầu tiên khớp**. Nếu không chain nào khớp, đó là một nhánh điều tra riêng.
4. Trong chain đã chọn, kiểm tra cơ chế authentication: HTTP Basic, session, Bearer, hoặc cơ chế khác. 401 có thể xảy ra vì thiếu/sai credentials.
5. Đọc rule `authorizeExchange` theo thứ tự; 403 có thể do đã xác thực nhưng thiếu role/scope hoặc `denyAll()`.
6. Nếu authorization pass, kiểm tra controller mapping, method security và data/business authorization. 404 có thể đến từ handler hoặc chính sách che giấu tài nguyên.
7. Xác minh bằng test cho **cả trường hợp được phép và bị chặn**; tránh suy luận dựa trên một response đơn lẻ.

Trong môi trường test, có thể sử dụng logging của Spring Security ở mức phù hợp để quan sát matcher/filter. Không ghi plaintext password, toàn bộ Authorization header, access token hoặc dữ liệu cá nhân vào log. Nếu debug một hệ thống có gateway, cần phân biệt status đến từ gateway với status do chính ứng dụng trả.

### Mẫu bảng điều tra

| Triệu chứng | Nguyên nhân có thể | Bước xác minh |
| --- | --- | --- |
| USER vào được `/api/admin/report` | API chain rộng ưu tiên hơn Admin chain | So lại `@Order` và matcher chồng lấp |
| `/api/status` 401 dù public | Admin/fallback chain bắt trước hoặc client gửi credentials sai | Xác định chain; thử request không có Authorization |
| `/health` 401 hoặc 403 | Fallback rule không có `permitAll()`, hoặc chain khác bắt request | Kiểm tra matcher từng chain và HTTP method |
| `/internal/ping` trả 200 | Thiếu fallback/catch-all hoặc cấu hình mở quá rộng | Test authenticated và anonymous cho đường dẫn ngoài API |
| Admin hợp lệ vẫn 403 | Role được ánh xạ sai, ví dụ thiếu `ROLE_ADMIN` | Kiểm tra authorities thực của Authentication và `hasRole` |
| Các chain sau không bao giờ chạy | Chain ưu tiên cao có matcher match-all | Thêm matcher hẹp cho chain đầu và đưa catch-all xuống cuối |
| POST nhận 403 nhưng GET được phép | CSRF hoặc rule HTTP method | Đối chiếu chính sách CSRF, HTTP method và việc mang credentials |

## 16. Những lỗi thiết kế cần tránh

- **Cho rằng các chain được cộng dồn.** Thực tế chọn **một** chain đầu tiên khớp; authorization fail không khiến Spring thử chain tiếp theo.
- **Dùng `@Order` nhưng bỏ `securityMatcher` ở chain ưu tiên cao.** Chain đó có thể bắt mọi request, làm các chain sau vô dụng.
- **Đưa matcher rộng lên trước matcher cụ thể.** `/api/**` có thể che `/api/admin/**`, bỏ qua quyền ADMIN.
- **Chỉ có chain chuyên biệt mà thiếu catch-all.** Những URL khác có thể không được security chain nào bảo vệ.
- **Xem `pathMatchers` là cách chọn chain.** Đây là rule cấp quyền của chain đã chọn; chọn chain bằng `securityMatcher`.
- **Tin một lần test 200.** Cần test 401, 403, quyền theo role và đường dẫn ngoài matcher, đặc biệt khi cấu hình thay đổi.
- **Sao chép API Servlet vào WebFlux.** Dùng `SecurityWebFilterChain`, `ServerHttpSecurity` và `ServerWebExchangeMatcher`, không dùng `SecurityFilterChain` + `HttpSecurity` dành cho Servlet.
- **Tắt CSRF/CORS hoặc mở mọi route để “sửa” test.** Phải xác định chain được chọn và lớp đang từ chối request trước; chính sách đăng nhập và threat model là cơ sở của quyết định bảo mật.
- **Đồng nhất role với quyền dữ liệu nghiệp vụ.** `ROLE_ADMIN` ở route chưa thay thế kiểm soát tenant, owner, trạng thái giao dịch hoặc giới hạn dữ liệu đầu ra.

## 17. Bài tập vận dụng

### Bài 1 — Dự đoán chain trước khi chạy

Với ba chain trong mục 4, hãy lập bảng chain được chọn cho:

- `GET /api/admin/report`
- `GET /api/profile`
- `GET /api/status`
- `GET /health`
- `GET /internal/ping`

Sau đó viết test so sánh dự đoán với status. Cần trình bày **tên chain trước**, rồi mới giải thích quyền. Không chỉ đoán status.

### Bài 2 — Chủ động tái hiện lỗi thứ tự

Đổi riêng `@Order` của Admin từ 1 thành 2, API từ 2 thành 1 trong bản sao bài lab. Chạy lại test `normalUserCannotEnterAdminChain`. Dự đoán sự thay đổi và giải thích vì sao request bị xử lý bởi chain API. Sau đó phục hồi thứ tự an toàn.

Lưu ý: thay đổi trên chỉ dùng cho lab cục bộ và cần có test phát hiện lỗi; không dùng cấu hình sai ở hệ thống có dữ liệu thật.

### Bài 3 — Thêm vùng riêng

Thêm endpoint `GET /api/reports/summary` cần `ROLE_ANALYST`. Có thể lựa chọn một trong hai thiết kế:

1. Thêm rule riêng `pathMatchers(...).hasRole("ANALYST")` trong API chain hiện tại khi chỉ khác quyền; hoặc
2. Tạo chain riêng `/api/reports/**` với `@Order` nằm giữa Admin và API nếu vùng này thực sự cần cơ chế filter/xác thực khác.

Giải thích vì sao không bắt buộc tạo một chain mới cho mỗi role và phải bổ sung test chống shadowing khi tạo chain có matcher chồng lấp.

### Bài 4 — Chứng minh fallback

Thêm `GET /unknown` trong controller nhưng không khai báo rule mở. Kiểm tra authenticated user bị từ chối do fallback. Sau đó thêm `GET /public-news` bằng `permitAll()` trong fallback, nhưng vẫn giữ `denyAll()` cho đường dẫn còn lại.

### Tiêu chí hoàn thành

- [ ] Vẽ đúng hai tầng: `securityMatcher` chọn chain; `authorizeExchange` quyết định quyền.
- [ ] Giải thích được: **`@Order(1)` đứng trước `@Order(2)`** và chọn chain đầu tiên khớp.
- [ ] Chứng minh `/api/admin/**` phải được xét trước `/api/**` khi matcher chồng lấp.
- [ ] Chạy được các endpoint và test trong ví dụ WebFlux.
- [ ] Có ít nhất một negative test cho MEMBER truy cập ADMIN và một test cho URL fallback.
- [ ] Giải thích được vì sao `anyExchange().denyAll()` trong chain API không tự bảo vệ URL ngoài `/api/**`.
- [ ] Phân biệt HTTP 401, 403 và lỗi routing 404 mà không suy đoán chain từ status đơn lẻ.
- [ ] Nêu được khi nào nên tách nhiều chain và khi nào một chain với nhiều rule là đủ.

## 18. Câu hỏi tự kiểm tra

1. Một request khớp hai `securityMatcher`: Spring Security chạy cả hai hay chỉ chain đầu tiên? Nếu chain đầu trả 403, chain thứ hai có được thử không?
2. `@Order(1)` và `@Order(2)` có bảo đảm thứ tự khi đặt trên hai method bean bất kỳ trong cùng cấu hình không?
3. Khác biệt giữa `http.securityMatcher("/api/**")` theo ý nghĩa cấu hình và `authorizeExchange().pathMatchers("/api/**")` là gì? (Trong WebFlux, `securityMatcher` thường nhận một `ServerWebExchangeMatcher` cụ thể như ví dụ.)
4. Nếu chain đầu không gọi `securityMatcher` thì điều gì xảy ra với các chain đặt sau?
5. Nếu không có catch-all và request không thuộc matcher chain nào, ứng dụng có mặc định từ chối không?
6. Vì sao test “member truy cập `/api/admin/report` phải bị 403” giúp phát hiện lỗi thứ tự mà test “admin vào được 200” có thể không phát hiện?
7. Khi cần vừa JWT API vừa session web, cấu hình authentication, exception handler và CSRF ở chain nào?
8. Nếu route trả 403, cách kiểm tra nào chứng minh đó là lỗi phân quyền ở chain được chọn, chứ không phải CSRF hay một cơ chế khác?

## 19. Tài liệu tham khảo

- [Spring Security — WebFlux Security, Multiple Chains Support](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): ví dụ chính thức về `@Order`, `securityMatcher` và chain đầu tiên khớp.
- [Spring Security — Authorize HTTP Exchanges](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): rule truy cập trong reactive chain.
- [Spring Security — HTTP Basic trong WebFlux](https://docs.spring.io/spring-security/reference/reactive/authentication/basic.html): thử thách/đăng nhập Basic của WebFlux.
- [Spring Security — CSRF trong WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): tác động với request thay đổi trạng thái.
- [Spring Framework — WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): reactive web stack và controller.

**Nguyên tắc cần ghi nhớ:** **Chain selection là quyết định “ai chịu trách nhiệm bảo vệ request”, không phải một phép cộng nhiều chính sách.** Đặt matcher cụ thể trước matcher tổng quát, ưu tiên bằng `@Order` rõ ràng và luôn có fallback được kiểm thử.