# Kiểm thử preflight CORS, origin không được phép và thông tin xác thực

**Module:** Spring Security – reactive (Spring WebFlux)  
**Nhóm:** Kiểm thử HTTP  
**Đề bài:** Kiểm thử `OPTIONS` CORS preflight, origin không được phép và request có thông tin xác thực bằng `WebTestClient`, `curl` và trình duyệt; phân biệt phản hồi CORS với authentication, authorization, CSRF và cơ chế cookie.

## 1. Kết luận chính

**CORS không cấp quyền truy cập API.** CORS là quy tắc do **trình duyệt** thực thi để quyết định JavaScript từ origin nào được đọc response cross-origin. Server vẫn phải xác thực và phân quyền từng request, kể cả request không có `Origin` hoặc request do công cụ như `curl` gửi.

**Preflight không phải actual request:** Với một GET có header `Authorization`, trình duyệt thường gửi một `OPTIONS` trước, gồm `Origin`, `Access-Control-Request-Method: GET` và `Access-Control-Request-Headers: authorization`. Preflight này **không mang cookie hoặc Authorization credentials của user**. Khi CORS được chấp nhận, browser mới gửi actual GET có credential (nếu có). Vì vậy Spring Security WebFlux cần xử lý CORS **trước** authentication; không được chặn OPTIONS chỉ vì chưa có user session.

**Credentialed CORS đòi hỏi allowlist chính xác:** Nếu server dùng `Access-Control-Allow-Credentials: true` thì `Access-Control-Allow-Origin` phải trả **một origin cụ thể được phép**, không được là wildcard `*`. `credentials:"include"` không tự xác thực user, cũng không buộc browser gửi cookie nếu SameSite/third-party policy đang chặn.

**HTTP tests không phải browser tests:** `WebTestClient` và `curl` cho phép chủ động đặt `Origin`, đọc HTTP status/header/body ngay cả khi origin bị cấm. Chúng **không áp dụng** browser CORS enforcement. Hãy test HTTP integration và browser behavior **riêng**, tránh diễn giải nhầm một response `200` là JavaScript đã có quyền đọc body.

## 2. Bốn lớp của một CORS request

| Lớp | Câu hỏi | Kết quả có thể thấy |
| --- | --- | --- |
| CORS preflight | Origin, method và request headers có được phép? | `200` + ACAO/ACAM/ACAH/ACAC nếu pass; trong Spring DefaultCorsProcessor thường `403` nếu CORS invalid |
| Browser enforcement | Response có ACAO/ACAC phù hợp credential mode? | JavaScript nhận `Response` hoặc lỗi CORS/`TypeError`; đôi khi HTTP network vẫn đã trả 200 |
| Authentication | Actual request có Basic/Bearer/session credential hợp lệ không? | `401` nếu thiếu/invalid, đôi khi form login redirect `302` |
| Authorization và CSRF | Principal được phép thao tác không; mutation có CSRF token hợp lệ không? | `403` khi thiếu quyền/CSRF |

**Không gộp** `403` do CORS processor với `403` do authorization hoặc CSRF. Cách debug là kiểm `Origin`, `Access-Control-Request-Method`, ACAO/ACAC, status, authentication context và filter order. Trong multi-tenant, xác thực tenant không thể chỉ dựa vào Origin.

### 2.1. Origin chính xác là gì?

Origin là bộ ba `scheme + host + port`. So sánh:

```text
https://app.example.test         ALLOWED trong bài
http://app.example.test          DENIED: khác scheme
https://app.example.test:8443    DENIED: khác port
https://evil.example.test        DENIED: khác host
null                             DENIED: không phải domain đã cấp phép
https://app.example.test.evil    DENIED: domain khác
```

Không dùng `String.endsWith("example.test")` để kiểm origin: nó có thể nhận các domain không thuộc quyền sở hữu. `Origin: null` thường xuất hiện ở ngữ cảnh sandbox/file/data; không tự mặc định tin cậy. Browser tự gửi Origin trong fetch, còn công cụ non-browser có thể tự chọn bất kỳ giá trị nào, vì vậy Origin **không phải identity**.

### 2.2. Những HTTP headers phải đọc

| Header | Chiều | Mục đích |
| --- | --- | --- |
| `Origin` | Request | Origin của JavaScript/browser |
| `Access-Control-Request-Method` | **Preflight request** | Actual method dự kiến |
| `Access-Control-Request-Headers` | **Preflight request** | Tên request headers dự kiến, không chứa raw token values |
| `Access-Control-Allow-Origin` | Response | Origin được phép, hoặc `*` cho trường hợp không credentialed phù hợp |
| `Access-Control-Allow-Methods` | Preflight response | Allowed actual methods |
| `Access-Control-Allow-Headers` | Preflight response | Allowed request headers |
| `Access-Control-Allow-Credentials` | Response | Cho phép browser expose credentialed CORS response |
| `Access-Control-Expose-Headers` | Actual response | Extra response headers có thể đọc bằng JavaScript |
| `Access-Control-Max-Age` | Preflight response | Thời hạn browser có thể cache preflight result |
| `Vary` | Response | Phân biệt cache theo Origin và request method/headers khi liên quan |
| `Authorization` | **Actual request** | Basic/Bearer credential, không có trong chuẩn preflight của browser |
| `Cookie` | **Actual request** | Session/CSRF cookies nếu được browser cho gửi; không có trên chuẩn preflight |

Không gửi `Access-Control-Allow-Credentials` ở **request** và nghĩ server sẽ bật credentialed mode. Nó là response header server trả về. Đừng đòi `Set-Cookie` phải đọc được từ JavaScript thông qua exposed headers; đây là forbidden response header trong Fetch.

## 3. Điểm khác nhau giữa preflight và actual GET

JavaScript từ `https://app.example.test`:

```javascript
// accessToken là token được lấy qua cơ chế bảo mật của app;
// không hard-code, không đưa real token vào URL/log.
fetch("https://api.example.test/api/me", {
  method: "GET",
  headers: {
    Authorization: "Bearer " + accessToken
  }
});
```

Vì có header Authorization, browser gửi preflight trước:

```http
OPTIONS /api/me HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

**Không có** `Authorization: Bearer ...` hoặc `Cookie: SESSION=...` trong OPTIONS. CORS processor có thể trả:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: authorization
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
```

Ví dụ minh họa; header order và cách ghi vary có thể khác. Browser sau đó gửi actual GET với Bearer. Actual request có thể:

- `200` nếu token hợp lệ và có quyền.
- `401` nếu không có hoặc sai token.
- `403` nếu principal đã xác thực nhưng không đủ authority.
- `403` từ CORS processor nếu Origin không hợp lệ trong cấu hình Spring của bài.

**Preflight 200 không đồng nghĩa actual 200.** Ngoài ra, một simple GET không header đặc biệt có thể **không preflight** nhưng actual response vẫn cần ACAO chính xác để JavaScript đọc body.

### 3.1. OPTIONS phải đi trước Spring Security authentication

Spring Security WebFlux reference yêu cầu CORS được xử lý trước Security vì preflight không mang cookie đăng nhập. Nếu server yêu cầu authentication trước khi nhận OPTIONS, bạn thường thấy OPTIONS bị `401` hoặc `302 /login`. Browser vì thế không gửi actual request. Không sửa lỗi này bằng cách `permitAll("/api/**")`: như vậy sẽ mở luôn endpoint cần được bảo vệ.

Trong WebFlux, dùng `CorsConfiguration` kết hợp `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource` và `ServerHttpSecurity.cors`, hoặc một `CorsWebFilter` được đặt đúng thứ tự. **Không copy imports của Servlet** (ví dụ `org.springframework.web.cors.UrlBasedCorsConfigurationSource`) vào chương trình WebFlux.

Cấp phép OPTIONS bằng `.pathMatchers(HttpMethod.OPTIONS, "/**").permitAll()` đơn độc **không thay** CORS processor: nó không tạo ACAO, ACAM, ACAH và không kiểm allowed origin. Hãy test cả status lẫn headers.

### 3.2. Actual request không có Origin

`curl -u viewer:viewer-pass http://localhost:8080/api/me` có thể nhận HTTP 200 vì Basic credential đúng, **không có ACAO**, và điều đó hoàn toàn bình thường. CORS không phải firewall chặn HTTP clients; non-browser clients có thể bỏ Origin hoặc forge Origin. Authentication/authorization phải đúng ngay cả khi Origin vắng mặt.

## 4. Credentials, cookies và CSRF

### 4.1. Fetch credential modes

| JavaScript fetch | Cookie cross-origin tự gửi? | Server và browser cần gì? |
| --- | --- | --- |
| `credentials:"omit"` | Không theo credential mode | Response cần ACAO thích hợp nếu JS muốn đọc |
| `credentials:"same-origin"` (mặc định) | Không tự gửi cookie tới origin khác | Cross-origin API có thể 401 dù cookie tồn tại |
| `credentials:"include"` | Có thể, **nếu** policy cookie cho phép | ACAO exact + ACAC true; còn phụ thuộc SameSite/Secure/domain/path/third-party-cookie policy |
| `Authorization: Bearer ...` được JS đặt tường minh | Không cần cookie để có Authorization | Preflight thường khai request header `authorization`; token vẫn cần validate |
| Cookie `HttpOnly` | JavaScript không đọc được cookie value | Browser có thể tự gửi cookie nếu policy phù hợp; server phải kiểm CSRF |
| Cookie `SameSite=None; Secure` | Có thể dùng cho cross-site HTTPS khi browser cho phép | Không vượt được third-party cookie blocking hoặc partitioning policy |

`credentials:"include"` **không chứng minh** cookie đã được gửi. DevTools Network/Application mới cho thấy lý do cookie bị chặn, ví dụ SameSite, Secure, Domain, Path, expiry hoặc user privacy settings.

### 4.2. Cấu hình wildcard không hợp lệ với credentials

```java
CorsConfiguration invalid = new CorsConfiguration();
invalid.setAllowedOrigins(List.of("*"));
invalid.setAllowCredentials(true);
// checkOrigin / validation có thể ném IllegalArgumentException.
```

Với credentialed responses, browser không cho JavaScript đọc nếu ACAO là `*`. Cách sửa là allowlist cụ thể:

```java
config.setAllowedOrigins(
    List.of("https://app.example.test"));
config.setAllowCredentials(true);
```

`allowedOriginPatterns` hỗ trợ các tập origin động, nhưng không có nghĩa pattern `*` an toàn: với cookie auth, chấp nhận bất kỳ origin có thể cấp quyền đọc response nhạy cảm cho attacker khi browser có session hợp lệ. Thiết kế registry tenant-origin có ownership verification, HTTPS và danh sách domains rõ ràng.

### 4.3. CORS không thay CSRF

Ngay cả khi site độc hại không thể **đọc** response, nó có thể **kích hoạt** một số loại request gửi credential tự động (nhất là form/cookie) nếu server không có biện pháp bảo vệ. POST/PUT/DELETE cần CSRF phù hợp khi dùng session-cookie/Basic cached credentials. `SameSite` là defense-in-depth, không thay mọi CSRF controls.

Trong bài thực hành, ta dùng HTTP Basic demo nhưng **giữ Spring Security CSRF mặc định**, để có hai phép thử khác nhau:

- Preflight `OPTIONS` POST được chấp nhận dù chưa có CSRF token, vì nó không phải business mutation.
- Actual `POST /api/action` có Basic đúng nhưng **không CSRF** bị `403`.
- Actual POST Basic đúng và `csrf()` hợp lệ trong security test được `200`.

Test `csrf()` từ `spring-security-test` chỉ kiểm Spring Security filter behavior, **không** chứng minh cookie CSRF thật hoạt động ở Chrome/Safari. Muốn hoàn tất QA trình duyệt, test session cookie, token retrieval và header forwarding theo mô hình của app thật.

## 5. Thiết kế một test matrix không bị lẫn ý nghĩa

Ví dụ cấu hình:

```text
Allowed Origin:  https://app.example.test
Allowed Methods: GET, POST
Allowed Headers: Authorization, Content-Type, X-CSRF-TOKEN
Allow Credentials: true
CORS Paths: /api/**
GET /public: public, không bật CORS cho route này
GET /api/me: Basic authentication
POST /api/action: Basic authentication + CSRF
```

| Tình huống | Request cần test | Kỳ vọng với Spring CORS processor |
| --- | --- | --- |
| Preflight hợp lệ GET | OPTIONS, allowed Origin, ACRM GET, ACRH authorization, **không auth** | 200, ACAO exact, ACAC true, ACAM/ACAH đúng |
| Preflight hợp lệ POST | OPTIONS /api/action, ACRM POST, ACRH content-type,x-csrf-token | 200, không cần CSRF credential |
| Preflight Evil | OPTIONS, Origin evil | 403, không ACAO |
| Preflight null origin | OPTIONS, Origin null | 403, không ACAO |
| Sai scheme/port | OPTIONS, http thay https hoặc :8443 | 403 |
| Method không phép | OPTIONS, ACRM DELETE | 403 |
| Header không phép | OPTIONS, ACRH x-admin | 403 |
| Actual GET no Basic | Allowed Origin, GET | 401, ACAO vẫn đúng |
| Actual GET Basic đúng | Allowed Origin, GET | 200, ACAO/ACAC, DTO body |
| Actual GET Basic sai | Allowed Origin, GET | 401 |
| Actual GET evil origin + Basic | Evil Origin, GET | 403 do CORS, không ACAO |
| Actual GET không Origin + Basic | No Origin, GET | 200, không ACAO |
| Actual GET cookie giả, no Basic | Allowed Origin, GET | 401 |
| Actual POST Basic, no CSRF | Allowed Origin, POST | 403 |
| Actual POST Basic + test CSRF | Allowed Origin, POST | 200 |
| Actual POST evil + test CSRF | Evil Origin, POST | 403 do CORS, không ACAO |

**Status không nói hết câu chuyện:** với một framework khác, CORS processor có thể trả status khác cho origin invalid; điều cốt lõi là browser không được đọc response nếu ACAO không cho phép. Nhưng khi test **chính implementation Spring WebFlux đã chọn**, 403 từ `DefaultCorsProcessor` là kỳ vọng hợp lý.

## 6. Project Spring Boot WebFlux Java 17+ để chạy test

**Mốc phiên bản trong ví dụ:** Java 17+, Maven 3.9+, Spring Boot 3.5.7, Spring Security 6.5.x qua Boot BOM. Mục đích là demo có thể tự dựng, không phải chỉ định bản production vĩnh viễn. Hãy cập nhật các bản vá/còn hỗ trợ khi triển khai thực tế.

Cây thư mục:

```text
cors-webflux-tests/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/cors/
    │   │   ├── CorsApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── DemoController.java
    │   └── resources/application.properties
    └── test/java/demo/cors/
        ├── CorsHttpTests.java
        └── CorsPolicyUnitTests.java
```

Không dùng `spring-boot-starter-web` vì bài cần reactive CORS `CorsWebFilter`/`ServerHttpSecurity`, không phải Servlet MVC.

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.7</version>
    <relativePath/>
  </parent>
  <groupId>demo</groupId>
  <artifactId>cors-webflux-tests</artifactId>
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
```

`src/main/resources/application.properties`:

```properties
spring.application.name=cors-webflux-tests
server.port=8080
```

`src/main/java/demo/cors/CorsApplication.java`:

```java
package demo.cors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsApplication.class, args);
    }
}
```

### 6.1. SecurityConfig.java: allowlist CORS với credentials

`src/main/java/demo/cors/SecurityConfig.java`:

```java
package demo.cors;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    static final String ALLOWED_ORIGIN =
        "https://app.example.test";

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of(ALLOWED_ORIGIN));
        config.setAllowedMethods(List.of("GET", "POST"));
        config.setAllowedHeaders(
            List.of("Authorization", "Content-Type", "X-CSRF-TOKEN"));
        config.setExposedHeaders(List.of("X-Request-Id"));
        config.setAllowCredentials(true);
        config.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails viewer = User.withUsername("viewer")
            .password("{noop}viewer-pass")
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(viewer);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/public")
                    .permitAll()
                .pathMatchers("/api/**")
                    .authenticated()
                .anyExchange().denyAll())
            .cors(Customizer.withDefaults())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            // Không disable CSRF; giữ mặc định.
            .build();
    }
}
```

**Giải thích:**

1. `UrlBasedCorsConfigurationSource` có package `reactive`, đúng kiểu cho Spring Security WebFlux. Đây là một bean source duy nhất, được kết nối qua `.cors(withDefaults())`; **không tạo đồng thời một CorsWebFilter bean khác** hoặc `@CrossOrigin` rộng không rõ nguồn.
2. Origin duy nhất là `https://app.example.test`, không dùng wildcard với `allowCredentials(true)`.
3. Allowed methods chỉ gồm GET, POST; `OPTIONS` là method preflight hỏi về actual method, không cần nằm trong list để kiểm GET/POST.
4. `Authorization`, `Content-Type` và `X-CSRF-TOKEN` là các request headers được phép cho preflight; không bật `allowedHeaders("*")` vì dễ che thiếu sót policy.
5. `X-Request-Id` được phép đọc bằng JavaScript sau actual response; không tự expose toàn bộ cookie/token headers.
6. `maxAge=600` cho phép browser cache kết quả preflight, nhưng browser có thể áp cap riêng. Khi đổi policy production, cần test/quan sát preflight cache.
7. `httpBasic` là fixture, không đại diện OAuth2 Login; `NoOpServerSecurityContextRepository` không giữ security context trong session. CSRF vẫn bật mặc định cho POST, kể cả khi Basic đúng.
8. `anyExchange().denyAll()` từ chối route ngoài scope. Không tự permitAll API để làm preflight pass.
9. Password `{noop}viewer-pass` chỉ để demo, không dùng cho production. Với browser và HTTP Basic, phải dùng HTTPS; Basic credentials có thể được browser nhớ và là lý do **không bỏ CSRF** tùy tình huống.

### 6.2. DemoController.java: quan sát response thật

`src/main/java/demo/cors/DemoController.java`:

```java
package demo.cors;

import java.security.Principal;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {
    public record Me(String username) {}
    public record Action(String status) {}

    @GetMapping(value = "/public",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> publicRoute() {
        return Mono.just("public");
    }

    @GetMapping(value = "/api/me",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<Me>> me(Principal principal) {
        return Mono.just(ResponseEntity.ok()
            .header("X-Request-Id", "demo-123")
            .body(new Me(principal.getName())));
    }

    @PostMapping(value = "/api/action",
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Action> action() {
        // Không ghi DB thật. Dùng để test Security/CSRF.
        return Mono.just(new Action("accepted"));
    }
}
```

Không có code kiểm `Origin` bên trong controller: Spring CORS processor xử lý trước. `Principal` của `GET /api/me` do Spring Security Basic authentication cung cấp; không đọc username từ query hoặc Origin. POST là unsafe method nên test CSRF vẫn có nghĩa dù bản demo không ghi database.

## 7. Java 17 CLI độc lập: origin exact match

Trước khi test Spring, có thể chạy một program thuần JDK 17 để nhắc mình rằng match origin **không phải** match một phần domain. Chương trình này chỉ là mô phỏng allowlist, **không** tái hiện toàn bộ Fetch/CORS processor.

Lưu `OriginPolicyDemo.java`:

```java
import java.util.Set;

public class OriginPolicyDemo {
    static final Set<String> ALLOWED =
        Set.of("https://app.example.test");

    static boolean allowed(String origin) {
        return ALLOWED.contains(origin);
    }

    public static void main(String[] args) {
        System.out.println("allowed=" +
            allowed("https://app.example.test"));
        System.out.println("wrongScheme=" +
            allowed("http://app.example.test"));
        System.out.println("wrongPort=" +
            allowed("https://app.example.test:8443"));
        System.out.println("evil=" +
            allowed("https://evil.example.test"));
    }
}
```

Chạy:

```bash
javac OriginPolicyDemo.java
java OriginPolicyDemo
```

**Stdout chính xác:**

```text
allowed=true
wrongScheme=false
wrongPort=false
evil=false
```

Trong Spring, dùng `CorsConfiguration.checkOrigin` để kiểm chính sách đã cấu hình; ở browser, Origin còn có chuẩn hóa cổng mặc định và quy tắc URL. Không thay implementation CORS của framework bằng một `Set.contains` thiếu bối cảnh nếu app có origins động.

## 8. HTTP tests với WebTestClient và Spring Security reactive

Ta dùng `@SpringBootTest(webEnvironment = MOCK)` + `WebTestClient.bindToApplicationContext(context).apply(springSecurity())` để chạy full WebFlux filter chain **không cần mở port**. `spring-security-test` có `csrf()` cho request mutation trong test. Không dùng Servlet `MockMvc` hay Servlet `SecurityMockMvcRequestPostProcessors.csrf` cho ứng dụng WebFlux.

**Quan trọng:** `WebTestClient` không tự động phát OPTIONS khi bạn gọi GET có Origin/Authorization. Browser có thể tự preflight; trong test phải **tự viết OPTIONS** rồi test actual GET riêng.

`src/test/java/demo/cors/CorsHttpTests.java`:

```java
package demo.cors;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class CorsHttpTests {

    private static final String ALLOWED =
        "https://app.example.test";
    private static final String EVIL =
        "https://evil.example.test";

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private WebTestClient.ResponseSpec preflight(
            String origin, String method, String headers) {
        return client.options().uri("/api/me")
            .header(HttpHeaders.ORIGIN, origin)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                method)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                headers)
            .exchange();
    }

    @Test
    void validPreflightNeedsNoAuthentication() {
        preflight(ALLOWED, "GET", "authorization")
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                ALLOWED)
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS,
                "true")
            .expectHeader().value(
                HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS,
                v -> assertTrue(v.contains("GET")))
            .expectHeader().value(
                HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS,
                v -> assertTrue(
                    v.toLowerCase().contains("authorization")));
    }

    @Test
    void preflightHasCacheAgeAndVary() {
        preflight(ALLOWED, "GET", "authorization")
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_MAX_AGE, "600")
            .expectHeader().value(
                HttpHeaders.VARY,
                v -> assertTrue(v.contains("Origin")));
    }

    @Test
    void postAndCsrfHeaderPreflightPassesWithoutCsrf() {
        client.options().uri("/api/action")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                "POST")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "content-type,x-csrf-token")
            .exchange().expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                ALLOWED);
    }

    @Test
    void unknownOriginPreflightIsRejected() {
        preflight(EVIL, "GET", "authorization")
            .expectStatus().isForbidden()
            .expectHeader().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }

    @Test
    void nullOriginPreflightIsRejected() {
        preflight("null", "GET", "authorization")
            .expectStatus().isForbidden()
            .expectHeader().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }

    @Test
    void wrongSchemeIsNotTheSameOrigin() {
        preflight("http://app.example.test", "GET",
            "authorization").expectStatus().isForbidden();
    }

    @Test
    void wrongPortIsNotTheSameOrigin() {
        preflight("https://app.example.test:8443", "GET",
            "authorization").expectStatus().isForbidden();
    }

    @Test
    void disallowedDeleteMethodIsRejected() {
        preflight(ALLOWED, "DELETE", "authorization")
            .expectStatus().isForbidden()
            .expectHeader().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }

    @Test
    void disallowedCustomHeaderIsRejected() {
        preflight(ALLOWED, "GET", "x-admin")
            .expectStatus().isForbidden()
            .expectHeader().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }

    @Test
    void allowedCorsDoesNotAuthenticateActualGet() {
        client.get().uri("/api/me")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .exchange().expectStatus().isUnauthorized()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED)
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS,
                "true");
    }

    @Test
    void correctBasicActualRequestReturns200AndCorsHeaders() {
        client.get().uri("/api/me")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .headers(h -> h.setBasicAuth(
                "viewer", "viewer-pass"))
            .exchange().expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                ALLOWED)
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS,
                "true")
            .expectHeader().value(
                HttpHeaders.ACCESS_CONTROL_EXPOSE_HEADERS,
                v -> assertTrue(v.contains("X-Request-Id")))
            .expectBody()
            .jsonPath("$.username").isEqualTo("viewer");
    }

    @Test
    void invalidBasicPasswordStillReturns401() {
        client.get().uri("/api/me")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .headers(h -> h.setBasicAuth(
                "viewer", "incorrect"))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void evilActualOriginDeniedEvenIfBasicCorrect() {
        client.get().uri("/api/me")
            .header(HttpHeaders.ORIGIN, EVIL)
            .headers(h -> h.setBasicAuth(
                "viewer", "viewer-pass"))
            .exchange().expectStatus().isForbidden()
            .expectHeader().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }

    @Test
    void noOriginWithCorrectBasicStillWorks() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth(
                "viewer", "viewer-pass"))
            .exchange().expectStatus().isOk()
            .expectHeader().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN)
            .expectBody()
            .jsonPath("$.username").isEqualTo("viewer");
    }

    @Test
    void publicRouteDoesNotNeedAuthentication() {
        client.get().uri("/public")
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void FakeCookieCannotReplaceBasicAuthentication() {
        client.get().uri("/api/me")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .cookie("SESSION", "fake")
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void postWithBasicButNoCsrfIsForbidden() {
        client.post().uri("/api/action")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .headers(h -> h.setBasicAuth(
                "viewer", "viewer-pass"))
            .exchange().expectStatus().isForbidden()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                ALLOWED);
    }

    @Test
    void postWithBasicAndValidTestCsrfSucceeds() {
        client.mutateWith(csrf())
            .post().uri("/api/action")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .headers(h -> h.setBasicAuth(
                "viewer", "viewer-pass"))
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.status").isEqualTo("accepted");
    }

    @Test
    void evilOriginPostStillDeniedWithCsrf() {
        client.mutateWith(csrf())
            .post().uri("/api/action")
            .header(HttpHeaders.ORIGIN, EVIL)
            .headers(h -> h.setBasicAuth(
                "viewer", "viewer-pass"))
            .exchange().expectStatus().isForbidden()
            .expectHeader().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }
}
```

**19 HTTP tests** kiểm CORS filter integration, Origin matching, ACAO/ACAC, preflight method/header, Basic authentication và CSRF. Code được thiết kế để người học **tự chạy**; bài này **không khẳng định đã thực thi Maven tests trong workspace của bạn**. `csrf()` chỉ giúp test security filter trong memory, không xác minh cookie cross-site trên Chrome/Safari.

### 8.1. Unit tests riêng cho CorsConfiguration

`src/test/java/demo/cors/CorsPolicyUnitTests.java`:

```java
package demo.cors;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.web.cors.CorsConfiguration;

import static org.junit.jupiter.api.Assertions.*;

class CorsPolicyUnitTests {

    @Test
    void wildcardCannotBeCredentialed() {
        CorsConfiguration c = new CorsConfiguration();
        c.setAllowedOrigins(List.of("*"));
        c.setAllowCredentials(true);
        assertThrows(IllegalArgumentException.class,
            () -> c.checkOrigin("https://app.example.test"));
    }

    @Test
    void exactAllowedOriginButNotEvil() {
        CorsConfiguration c = new CorsConfiguration();
        c.setAllowedOrigins(List.of(
            "https://app.example.test"));
        c.setAllowCredentials(true);

        assertEquals("https://app.example.test",
            c.checkOrigin("https://app.example.test"));
        assertNull(c.checkOrigin(
            "https://evil.example.test"));
    }

    @Test
    void onlyDeclaredMethodsPass() {
        CorsConfiguration c = new CorsConfiguration();
        c.setAllowedMethods(List.of("GET", "POST"));
        assertNotNull(c.checkHttpMethod(HttpMethod.GET));
        assertNull(c.checkHttpMethod(HttpMethod.DELETE));
    }

    @Test
    void unlistedHeadersDoNotPass() {
        CorsConfiguration c = new CorsConfiguration();
        c.setAllowedHeaders(List.of(
            "Authorization", "Content-Type"));
        assertNotNull(c.checkHeaders(
            List.of("authorization")));
        assertNull(c.checkHeaders(
            List.of("X-Admin")));
    }
}
```

**Tổng cộng 23 bài test mẫu:** 19 `CorsHttpTests` và 4 `CorsPolicyUnitTests`. Unit tests gọi `CorsConfiguration.checkOrigin`/`checkHttpMethod`/`checkHeaders`, không chạy Security chain. Integration tests dùng WebTestClient chứ không chạy trình duyệt. Hai tầng kiểm thử là bổ sung cho nhau.

### 8.2. Chạy Maven

```bash
mvn test
mvn spring-boot:run
```

Có thể thêm `mvn -Dtest=CorsHttpTests test` để chỉ chạy HTTP integration tests hoặc `mvn -Dtest=CorsPolicyUnitTests test` để chỉ chạy policy tests. Đừng thay test expected 403 bằng 200 thông qua `permitAll()` hoặc `allowedOrigins("*")`; phải sửa cấu hình CORS đúng với sản phẩm.

## 9. Curl recipes để đối chiếu response

Các lệnh gọi `http://localhost:8080`; `https://app.example.test` là **Origin giả lập cho HTTP test**, không cần frontend DNS thật khi dùng curl. `curl` không enforce CORS nên status/body chỉ chứng minh hành vi server.

### 9.1. OPTIONS allowed origin, no Authorization

```bash
curl -i -X OPTIONS http://localhost:8080/api/me \
  -H 'Origin: https://app.example.test' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'
```

Kỳ vọng `200`, ACAO chính xác, ACAC true, ACAM chứa GET, ACAH chứa authorization. **Không thêm `-u` vào OPTIONS**: browser preflight không chứa Basic/Bearer credentials.

### 9.2. OPTIONS disallowed origin

```bash
curl -i -X OPTIONS http://localhost:8080/api/me \
  -H 'Origin: https://evil.example.test' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'
```

Kỳ vọng Spring CORS processor `403` và thiếu ACAO. Nếu server bất ngờ trả ACAO bằng origin evil, kiểm allowlist, `@CrossOrigin` và bất kỳ gateway/proxy nào ghi đè CORS headers.

### 9.3. OPTIONS method DELETE không được phép

```bash
curl -i -X OPTIONS http://localhost:8080/api/me \
  -H 'Origin: https://app.example.test' \
  -H 'Access-Control-Request-Method: DELETE' \
  -H 'Access-Control-Request-Headers: authorization'
```

Kỳ vọng `403` vì DELETE chưa được allow. Thêm `OPTIONS` vào allowedMethods không có nghĩa DELETE được phép — CORS kiểm giá trị header `Access-Control-Request-Method`.

### 9.4. OPTIONS header X-Admin không được phép

```bash
curl -i -X OPTIONS http://localhost:8080/api/me \
  -H 'Origin: https://app.example.test' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: x-admin'
```

Kỳ vọng `403`. Trong sản phẩm thật chỉ whitelist những custom headers thực sự cần; không nên cho client tự gửi internal admin/tenant assertions rồi tin giá trị đó.

### 9.5. GET allowed origin không credentials

```bash
curl -i http://localhost:8080/api/me \
  -H 'Origin: https://app.example.test'
```

Kỳ vọng `401` do Basic thiếu, đồng thời có ACAO/ACAC cho allowed Origin. Đây là chứng cứ **CORS pass ≠ auth pass**.

### 9.6. GET allowed origin với Basic fixture

```bash
curl -i -u viewer:viewer-pass \
  http://localhost:8080/api/me \
  -H 'Origin: https://app.example.test'
```

Kỳ vọng `200` với JSON `{"username":"viewer"}`, ACAO exact, ACAC true và `X-Request-Id` được exposed. Chỉ dùng password fixture này trên localhost. Trong production dùng HTTPS và không để mật khẩu/token thật trong shell history.

### 9.7. GET evil origin với Basic đúng

```bash
curl -i -u viewer:viewer-pass \
  http://localhost:8080/api/me \
  -H 'Origin: https://evil.example.test'
```

Kỳ vọng `403` từ Spring CORS processor, không có ACAO. **CORS không phải authentication**: nếu non-browser client bỏ Origin và gửi credential đúng, nó vẫn được xử lý theo API auth policy.

### 9.8. POST allowed origin nhưng thiếu CSRF

```bash
curl -i -u viewer:viewer-pass -X POST \
  http://localhost:8080/api/action \
  -H 'Origin: https://app.example.test'
```

Kỳ vọng `403` do CSRF; preflight POST trước đó có thể pass. Với browser/session thật, cần cơ chế phát CSRF token, gửi form/header theo Spring Security repository/handler và giữ cookie protections. Không mở CSRF chỉ vì Origin được allowlisted.

### 9.9. PowerShell và tài khoản thật

PowerShell 5.1 có thể gán `curl` cho `Invoke-WebRequest`, nên dùng `curl.exe` khi cần cú pháp curl chuẩn. Không copy Base64 Basic headers từ DevTools vào ticket hoặc log; Base64 không mã hóa bí mật. Không đưa Bearer/session credentials vào URL query hay ảnh chụp màn hình.

## 10. Browser QA khác WebTestClient ra sao?

### 10.1. Từ frontend allowed origin

Mở ứng dụng HTTPS thực tại `https://app.example.test` và thử:

```javascript
const response = await fetch("https://api.example.test/api/me", {
  method: "GET",
  credentials: "include"
});
console.log(response.status);
```

Nếu session-cookie hợp lệ ở môi trường thật, browser có thể gửi cookie cross-origin nếu SameSite/Secure/domain/path và browser privacy policies cho phép. Trong project HTTP Basic demo, `credentials:"include"` **không tự đăng nhập**; nếu chưa có Basic credential hợp lệ, nhận 401. Browser DevTools Network cho thấy request OPTIONS (nếu có), actual GET, response ACAO/ACAC và cookie sending decisions.

### 10.2. Từ frontend disallowed origin

Nếu tương tự chạy từ `https://evil.example.test`, browser sẽ chặn preflight hoặc không expose response. Với **simple GET không preflight**, request có thể đã đến server, nhưng JavaScript ở evil origin **không được đọc** body khi ACAO không cho phép. Fetch có thể **reject bằng TypeError**; JavaScript có thể không đọc được `response.status` của một CORS-blocked response. Vì vậy **không** viết test browser “đợi response.status=403” như đang dùng WebTestClient; hai tầng có observation khác nhau.

### 10.3. Kiểm cookies một cách có hệ thống

1. Trong DevTools Application/Storage, cookie có được lưu không?
2. Cookie có `Secure` khi API dùng HTTPS; `Domain`, `Path` và `Expires/Max-Age` chính xác không?
3. `SameSite=Lax/Strict/None` có hợp use case? Cross-site cookies bị browser block/partition không?
4. Fetch đã có `credentials:"include"` chưa?
5. OPTIONS đúng Origin/ACRM/ACRH đã pass chưa; actual response có ACAO exact và ACAC true không?
6. Nếu cookie được gửi nhưng actual 401, kiểm session validity/authentication, không quy hết cho CORS.
7. Nếu POST 403, kiểm CSRF token và authorization; không tắt CSRF để “chữa lỗi”.
8. Đừng thêm `Access-Control-Allow-Origin: *` khi credentialed; browser không chấp nhận wildcard với credentials.

**Không có cách nào** dùng ACAC để cưỡng ép Chrome/Safari gửi cookie đã bị third-party blocking. Nếu app BFF cần cross-site session, hãy xem thiết kế domain/site, privacy policies, CSRF và cookie attributes, không chỉ server header.

## 11. Những lỗi test dễ tạo kết luận sai

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| WebTestClient GET tự preflight | WebTestClient không phải browser | Gửi OPTIONS tường minh |
| OPTIONS có Authorization để “test credentials” | Browser preflight chuẩn không mang credentials | Kiểm OPTIONS anonymous pass, actual authenticated riêng |
| Chỉ assert OPTIONS status 200 | Có thể thiếu ACAO/ACAM/ACAH | Assert headers và allowed origin exact |
| Chỉ test allowed origin | Wildcard/reflect-all có thể lọt | Negative test evil/null/scheme/port |
| Dùng `allowedOrigins("*")` với ACAC | Invalid credentialed CORS | Whitelist origin cụ thể |
| Mở `allowedOriginPatterns("*")` để “fix” | Có thể phản chiếu mọi origin và rò response | Pattern chặt từ registry trusted |
| OPTIONS 200 coi là endpoint authenticated | Preflight không cấp principal | Actual 401/403/200 tests |
| Browser không có preflight coi là không cần CORS | Simple request vẫn cần ACAO | Test actual CORS response |
| Đọc `curl` body từ evil origin coi browser cũng đọc được | curl không enforce CORS | Browser DevTools/automation riêng |
| `GET` có side-effect và dựa CORS để chống CSRF | Browser có thể gửi request dù không đọc được response | Safe GET, CSRF/Origin checks/authorization |
| Dùng `permitAll("/api/**")` để OPTIONS pass | Mở API thực | Tích hợp CORS filter trước auth |
| Tắt CSRF vì POST đã preflight | CORS không CSRF | Giữ CSRF cho cookie/Basic mutation |
| Coi ACAC true là cookie chắc chắn gửi | SameSite, Secure, third-party policies vẫn áp | Browser cookie test |
| Coi 403 của evil Origin là user thiếu role | 403 có thể từ CORS processor | Phân loại filter/source |
| Tin Origin như user/tenant identity | Non-browser có thể giả Origin | AuthN/AuthZ từ token/session thật |
| Thêm Servlet UrlBasedCorsConfigurationSource vào WebFlux | Sai type/integration | Dùng reactive package |
| Tạo nhiều CorsWebFilter/CORS sources chồng nhau | Policy khó theo dõi/trùng headers | Một source rõ, test per chain/path |
| Quên Vary khi CDN cache ACAO | Cross-origin cache poisoning | Vary Origin/ACRM/ACRH, private caching |
| Đòi CSRF test helper chứng minh browser cookie | Test helper chỉ mô phỏng Security context | E2E browser cookie flow |
| CORS wildcard expose all headers | Có thể lộ metadata/token trong JS | Explicit exposedHeaders |
| API chỉ kiểm CORS không auth | curl/non-browser vẫn truy cập | Authentication + authorization |

### 11.1. Nếu OPTIONS trả 401 hoặc 302

Kiểm filter ordering: `CorsConfigurationSource` có được Spring Security tích hợp không? Endpoint matcher có đúng `/api/**` không? Có một SecurityWebFilterChain khác đang bắt request và chặn trước không? Proxy/ingress có redirect OPTIONS từ HTTP sang HTTPS hay `/login` không? Nếu app là WebFlux, bảo đảm bạn không vô tình bật Servlet stack bằng `spring-boot-starter-web`.

### 11.2. Nếu OPTIONS trả 403 với allowed Origin

Kiểm request có đủ `Origin` và `Access-Control-Request-Method` chưa. Header `Access-Control-Request-Headers` có chứa request header **ngoài** allowedHeaders không. Method `DELETE/PUT` có trong allowedMethods không. Scheme/port có khớp exact allowlist không. CORS configuration có áp đúng path không, ví dụ `/api/**` nhưng request đang ở `/auth/**`.

### 11.3. Nếu actual GET 200 nhưng browser vẫn báo lỗi CORS

Kiểm ACAO **trên actual response**, không chỉ OPTIONS; kiểm ACAC true khi fetch credentials include, header `Vary`/CDN cache, redirects, cookie policies và browser console. Một status 200 của HTTP server không bảo đảm JS đã đọc được body.

### 11.4. Nếu POST 403

Nếu ACAO đúng, request có thể đã vượt CORS nhưng bị `CsrfWebFilter` hoặc authorization chặn. Kiểm CSRF token repository/handler: mặc định WebFlux có `WebSessionServerCsrfTokenRepository` và ở Spring Security 6.x có cơ chế XOR mask token. Nếu dùng CookieServerCsrfTokenRepository cho SPA, phải có token flow phù hợp, không tự disable CSRF hoặc tin Origin thay token ở mọi tình huống.

## 12. CDN, reverse proxy và nhiều origin

**Origin response có thể khác nhau theo request Origin**. Khi server whitelist nhiều frontends, `Access-Control-Allow-Origin` phải ứng với origin được phép. Vì thế `Vary: Origin` (và khi cần `Access-Control-Request-Method`/`Access-Control-Request-Headers`) rất quan trọng để cache/CDN không phát nhầm ACAO của origin A sang B.

Đối với private responses, cần quản lý `Cache-Control` và key theo identity/authorization hoặc tắt shared caching. Đừng để response JSON user A xuất hiện trong shared CDN vì nhầm CORS là auth. Reverse proxy có thể ghi đè CORS headers hoặc xử lý OPTIONS riêng; integration tests với app trong memory không chứng minh ingress/CDN production, nên cần staging tests qua URL thật.

### 12.1. Proxy forwarded headers và scheme

`Forwarded`, `X-Forwarded-Proto`, `X-Forwarded-Host` có thể khiến server nhìn thấy request origin/target khác giá trị ngoài Internet nếu reverse proxy cấu hình sai. Chỉ tin forwarded headers từ trusted proxies đã strip/rewrite. Nếu không, attacker có thể khai headers sai và tác động origin comparison, redirect URI hoặc logs.

### 12.2. Tenant-specific frontend origins

Nếu tenant có frontend `https://acme.portal.example` và `https://globex.portal.example`, muốn cấp CORS riêng phải kiểm ownership domain trong trusted tenant registry và auth của backend. Không dùng một dynamic `Origin` echo-all để “đỡ quản lý danh sách”. Ngay cả khi browser cho tenant A gọi API, backend vẫn cần kiểm token `tenant_id` và quyền trên resource: CORS policy chỉ quản lý **đọc response cross-origin**, không thay tenant authorization.

## 13. Checklist review trước khi sản xuất

1. Xác định chính xác frontend origins theo `scheme://host:port`, không chỉ substring domain.
2. Ghi lại origin/method/header/credentials matrix theo từng path.
3. Tích hợp CORS trước Spring Security WebFlux authentication; test preflight **không có Cookie/Authorization**.
4. Dùng `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource` hoặc CorsWebFilter reactive đúng thứ tự; không nhầm Servlet imports.
5. Với `allowCredentials(true)`, chỉ whitelist exact origins/pattern chặt, không ACAO wildcard.
6. Test allowed/evil/null/scheme/port, methods DELETE, headers x-admin, preflight maxAge/Vary.
7. Test actual GET anonymous 401 và authenticated 200, sai credential 401, missing Origin non-browser.
8. Test POST đúng Basic/session nhưng thiếu CSRF 403, có CSRF token phù hợp mới thành công.
9. Không chuyển API `authenticated()` thành `permitAll()` chỉ để CORS test xanh.
10. Test browser enforcement riêng: CORS-blocked fetch không lộ response object cho JS.
11. Kiểm cookie `SameSite`/`Secure`/`HttpOnly`/domain/path và third-party policies trên browsers đích.
12. Không dùng Origin làm cơ chế user/tenant authentication; kiểm scopes/roles/owner tại backend.
13. Kiểm Vary, CDN/authenticated response caching, reverse proxy OPTIONS/redirects.
14. Không log Authorization header/session/CSRF token trong test artifacts, tracing hoặc screenshots.
15. Khi nâng Spring Security/Spring Framework/ingress, chạy lại CORS HTTP và browser regression tests.

## 14. Câu hỏi tự đánh giá

**1.** Một preflight cần những header gì?  
`OPTIONS` với `Origin` và `Access-Control-Request-Method`; `Access-Control-Request-Headers` có thể chứa names của các headers dự kiến.

**2.** Preflight có gửi cookie hoặc Bearer credentials của user không?  
Theo CORS browser chuẩn, **không**. Đó là lý do CORS phải xử lý trước authentication.

**3.** Preflight 200 nhưng GET 401 có phải CORS sai không?  
Không. Origin được phép, nhưng actual request thiếu/invalid credential.

**4.** ACAO `*` và ACAC true có dùng được cho credentialed browser fetch không?  
Không. Cần explicit origin.

**5.** `credentials:"include"` có đảm bảo session cookie cross-site được gửi không?  
Không; SameSite/Secure/domain/third-party policies vẫn áp.

**6.** Vì sao WebTestClient phải gửi OPTIONS tường minh?  
Vì WebTestClient không tự áp browser preflight logic.

**7.** CORS có thay CSRF cho POST cookie-auth không?  
Không. Browser có thể gửi request dù JavaScript không đọc response, nên cần CSRF/Origin/authorization protections.

**8.** Vì sao HTTP và HTTPS cùng host là origin khác?  
Origin gồm scheme, host, port, không chỉ domain.

**9.** HTTP client không có Origin có thể gọi API không?  
Có, nếu authentication/authorization cho phép; CORS không phải firewall.

**10.** Vì sao test evil Origin trên curl chưa chứng minh browser sẽ bị block?  
Curl không enforce CORS; cần kiểm actual browser enforcement.

**11.** Nếu actual POST 403, cần kiểm gì?  
Phân biệt CORS processor, CSRF token, authorization rule và security filter order.

**12.** `Access-Control-Expose-Headers` có làm JS đọc được Set-Cookie không?  
Không. Set-Cookie bị browser quản lý, không phải response header tùy ý JS có thể đọc.

**13.** Vì sao cần Vary: Origin?  
Để cache không dùng ACAO của origin A cho origin B và tránh cross-origin cache poisoning.

**14.** Một `@CrossOrigin` rộng trên controller có làm chính sách Spring Security thống nhất không?  
Không chắc; cấu hình chồng lấn có thể tạo kết quả khó dự đoán. Dùng một source rõ ràng, test mọi chain/path.

**15.** `csrf()` của test đã chứng minh cookie SameSite production chưa?  
Chưa. Đó là request test mutator; browser cookie flow cần E2E.

### Nguồn tham khảo chính thức

- Spring Security – Reactive CORS: https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/cors.html
- Spring Framework – CORS WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux-cors.html
- Spring Security – Testing Reactive Web Security: https://docs.spring.io/spring-security/reference/reactive/test/web/
- Spring Security – Testing with CSRF: https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html
- Spring Security – CSRF WebFlux: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
- Spring Framework API – CorsConfiguration: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/web/cors/CorsConfiguration.html
- MDN – CORS: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS
- MDN – Credentials + ACAO wildcard error: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS/Errors/CORSNotSupportingCredentials
- Fetch Standard – CORS: https://fetch.spec.whatwg.org/

**Tóm tắt:** Kiểm thử preflight, origin không được phép và credentials trong WebFlux cần tách `OPTIONS` **không credential** khỏi actual GET/POST **có/không auth**, kiểm ACAO/ACAC/ACAM/ACAH chính xác, và giữ CSRF/authorization riêng. WebTestClient/curl giúp xác minh response server; browser test xác minh thực sự JavaScript có đọc được response và cookie có được gửi hay không.