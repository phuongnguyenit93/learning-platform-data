# Đánh giá việc miễn CSRF cho API dùng Bearer token theo cách trình duyệt gửi thông tin xác thực

**Module:** Spring Security – reactive (WebFlux)  
**Chủ đề cha:** Bảo vệ CSRF  
**Đối tượng:** Lập trình viên Java 17+ triển khai API, SPA, browser session hoặc BFF với Spring Security.

**Kết luận cần nhớ trước khi cấu hình:** Một API có thể cân nhắc **miễn kiểm tra CSRF** trên request thay đổi trạng thái khi **credential duy nhất được API chấp nhận** là Bearer access token được client chủ động thêm vào header `Authorization`; browser **không tự lấy token từ origin đáng tin rồi gửi kèm các request do website khác kích hoạt**. Ngược lại, nếu API chấp nhận **cookie session, JWT/opaque token trong cookie, browser HTTP Basic đã lưu, BFF cookie hoặc bất kỳ fallback xác thực nào được browser tự gửi**, rủi ro CSRF **vẫn còn**. Việc endpoint trả JSON, tên token là JWT/Bearer hay backend được gọi là “stateless” đều **không đủ** để quyết định tắt CSRF.

Bài này đi từ cơ chế trình duyệt, ma trận rủi ro, thiết kế chain WebFlux, đến ứng dụng Spring Boot Java có **hai `SecurityWebFilterChain`** và **14 bài kiểm thử HTTP**. Các ví dụ sử dụng token test có chữ ký HMAC trên localhost để học, **không phải cấu hình quản lý khóa production**.

## 1. Bản chất của CSRF: quyền được browser tự mang sang request

CSRF (*Cross-Site Request Forgery*) là việc một trang tấn công lợi dụng trình duyệt của người dùng đã xác thực để yêu cầu website mục tiêu thực hiện hành động mà người dùng không chủ động chọn. Điều kiện cốt lõi là request đến máy chủ mục tiêu **tự mang credential được máy chủ chấp nhận**, ví dụ `SESSION` cookie. Attacker không cần đọc được cookie; chỉ cần browser gửi nó khi xử lý một form/navigation/request theo các quy tắc áp dụng.

```text
Người dùng đã đăng nhập tại https://bank.example.test
   |
   | Browser giữ Cookie: SESSION=...
   |
   v
Truy cập trang https://evil.example.test
   |
   | Trang lạ tạo form POST đến bank
   | Browser có thể tự thêm SESSION theo SameSite/cookie policy
   |
   v
Bank nhận POST + SESSION hợp lệ
   |
   +--> Nếu thiếu CSRF protection: nguy cơ xử lý hành động giả mạo
   +--> Nếu yêu cầu CSRF token không tự gửi: từ chối request giả
```

Bằng chứng đăng nhập trong cookie có thể là session ID hoặc một JWT tự chứa. **Không cần server-side session** vẫn có nguy cơ CSRF nếu JWT được trình duyệt gửi tự động qua cookie. Đây là lý do “stateless” không đồng nghĩa “CSRF-safe”.

### 1.1. Đối chiếu với Bearer header do JavaScript chủ động gắn

```http
POST /api/transfer HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token-hop-le>
Content-Type: application/json

{"destination":"demo","amount":1}
```

Nếu access token chỉ tồn tại trong ngữ cảnh client được phép và JavaScript của ứng dụng chủ động đặt `Authorization: Bearer ...`, một website lạ **không tự có được token** để đặt vào header. Browser không tự đính Bearer token từ vùng quản lý riêng của ứng dụng cho cross-site form. Đây là căn cứ **có điều kiện** để miễn CSRF trên API bearer-only.

Điều đó **không loại bỏ** XSS, token theft, rủi ro third-party scripts, cấu hình CORS quá rộng, access token bị log, hoặc việc resource server xác thực không đúng signature/issuer/expiry. CSRF exemption và token security là hai vấn đề khác nhau.

### 1.2. Năm câu hỏi trước khi miễn

1. **Server thực sự chấp nhận credential nào?** Chỉ header `Authorization: Bearer`, hay cũng chấp nhận `SESSION`/`access_token` cookie/HTTP Basic?
2. **Browser có tự mang credential đó sang request không?** Xét cookie scope, SameSite, `credentials` mode, Basic cache và gateway.
3. **Nếu không có Bearer header nhưng có cookie session hợp lệ, endpoint có bị 401 không?** Đây là negative test rất quan trọng.
4. **Có BFF/gateway nhận cookie rồi thêm Bearer header cho backend không?** Khi đó browser-facing boundary vẫn nhận ambient cookie.
5. **Đường nào là browser session và đường nào là Bearer-only?** Có thể giới hạn `csrf.disable()` vào đúng `SecurityWebFilterChain` không?

Nếu bất kỳ điểm nào còn mơ hồ, đừng tắt CSRF chỉ để làm test POST trở thành 200.

## 2. Ma trận quyết định theo credential transport

| Server xác thực request nhờ | Browser tự gửi trong request do trang khác kích hoạt? | Đánh giá CSRF với lệnh thay đổi trạng thái |
| --- | --- | --- |
| Bearer header **do JavaScript đáng tin tự thêm**, API **không nhận cookie fallback** | Không tự gắn Bearer token của origin khác | **Có thể xem xét miễn**, giữ nguyên authentication/authorization |
| JWT Bearer lưu trong cookie và API đọc cookie đó | Có thể, theo SameSite/cookie policy | **Phải bảo vệ CSRF** hoặc có phòng vệ tương đương đã chứng minh |
| `WebSession`/`SESSION` cookie cho form login | Có thể | **Bật CSRF**, nhất là POST/PUT/PATCH/DELETE |
| BFF giữ token phía server, browser dùng `SESSION` cookie | Có thể | **Bật CSRF ở BFF/browser-facing endpoints** |
| HTTP Basic mà browser đã ghi nhớ | Có thể tự gửi `Authorization: Basic` | **Đánh giá như ambient credential; giữ CSRF** |
| Bearer-only API có cookie xuất hiện nhưng **bỏ qua hoàn toàn cookie trong xác thực** | Cookie có thể xuất hiện; **không được cấp quyền từ đó** | **Có thể miễn** sau test cookie-only luôn 401 |
| Một endpoint chấp nhận **cả Bearer và cookie session** | Có đường ambient cookie | **Giữ CSRF**, hoặc thay đổi kiến trúc để loại cookie fallback |
| Resource server chỉ nhận mTLS/service-to-service token và không có browser | Không có browser credential ambient theo mô hình này | CSRF thường không phải cơ chế cần thiết; authn/authz vẫn bắt buộc |
| Proxy đọc cookie rồi đổi thành `Authorization: Bearer` gửi tới backend | Có ở ingress | **Bảo vệ CSRF tại ingress/BFF**; backend bearer-only không xóa rủi ro browser |
| `GET` có side effect hoặc token dùng trong URL | Link/navigation có thể bị kích hoạt; URL dễ rò | **Sửa HTTP semantics**, không dùng miễn CSRF để “chữa” |

**Không đánh đồng:** JWT là **định dạng** token; Bearer là **kiểu credential**; header hay cookie là **cách browser gửi**; CSRF phụ thuộc **credential ambient được server chấp nhận**.

### 2.1. Header Authorization không luôn giống nhau

`Authorization: Bearer <token>` được client code chủ động đặt khác `Authorization: Basic <base64>` mà browser có thể tự gửi sau khi user đăng nhập HTTP Basic. Không thể suy ra “có header Authorization nên không sợ CSRF”. Cũng không thể chỉ nhìn một HTTP header của backend vì gateway có thể đã bổ sung header dựa trên cookie.

### 2.2. Cookie hiện diện chưa đủ khẳng định nguy hiểm

Một browser cùng domain có thể tự thêm `SESSION` khi gửi request Bearer tới API. Nếu API **không bao giờ dùng** session cookie đó để xác thực, cookie không trao quyền cho request. Negative test gửi **chỉ cookie mà không Bearer** phải 401. Nếu một refactor sau này đọc cookie token và tạo Authentication thì kết luận miễn CSRF **phải được xem lại**.

## 3. Ba tình huống browser thực tế

### 3.1. SPA đính Bearer rõ ràng

```javascript
// accessToken phải đến từ cơ chế cấp token đúng và được giữ an toàn.
const result = await fetch("/api/transfer", {
  method: "POST",
  credentials: "omit",
  headers: {
    Authorization: "Bearer " + accessToken,
    "Content-Type": "application/json"
  },
  body: JSON.stringify({ destination: "demo", amount: 1 })
});

if (!result.ok) {
  throw new Error("Request rejected: " + result.status);
}
```

`credentials: "omit"` ngăn browser đính kèm cookie/credential ambient theo mode này; `Authorization` vẫn được mã ứng dụng đặt một cách chủ động. **Đừng coi việc đặt Bearer bằng JavaScript là bảo vệ chống XSS**: nếu origin bị XSS hoặc script độc hại có quyền chạy trên origin đó, attacker có thể dùng token/điều khiển request. Lưu token ở memory, storage hay BFF đều có đánh đổi; không tự cho rằng `localStorage` là lựa chọn an toàn mặc định.

### 3.2. JWT trong HttpOnly cookie

```http
POST /api/transfer HTTP/1.1
Cookie: access_token=<jwt>
Content-Type: application/x-www-form-urlencoded

destination=attacker&amount=1
```

`HttpOnly` ngăn JavaScript trực tiếp đọc cookie, **không** ngăn browser tự gửi cookie. Nếu Spring filter/gateway dùng cookie này để cấp Authentication, nguy cơ CSRF tồn tại. Cần token CSRF hoặc phòng vệ tương đương, kết hợp SameSite/Secure/Origin policy. Đặt một JWT vào cookie **không tự giữ được ưu điểm miễn CSRF** của Bearer header do JS đặt.

### 3.3. BFF lấy session cookie và gọi resource server bằng Bearer

```text
Browser --Cookie: SESSION=...--> BFF (WebFlux)
                                 |
                                 | Authorization: Bearer ...
                                 v
                              Resource Server
```

Resource Server có thể miễn CSRF nếu chỉ nhận Bearer và không có browser trực tiếp, **nhưng BFF nhận cookie vẫn phải chống CSRF** cho `POST /web/**`. Xác định đúng trust boundary người dùng tiếp xúc; không lấy cấu hình của backend để hợp thức hóa việc tắt CSRF ở frontend.

## 4. Java 17 độc lập: bài tập phân loại nguồn credential

Mã dưới đây chỉ là **mô hình tư duy** có stdout cố định. Nó không thể tự phân tích browser policy, không được dùng như bộ middleware quyết định bảo mật production.

Lưu `CsrfDecisionDemo.java`:

```java
import java.util.List;

public class CsrfDecisionDemo {

    record Channel(String name, boolean acceptedByServer,
                   boolean ambientFromBrowser) {}

    static String policy(Channel c) {
        if (!c.acceptedByServer()) {
            return "NOT_AUTHENTICATION";
        }
        if (c.ambientFromBrowser()) {
            return "CSRF_REQUIRED";
        }
        return "EXEMPTION_CAN_BE_REVIEWED";
    }

    public static void main(String[] args) {
        var cases = List.of(
            new Channel("JS Bearer header", true, false),
            new Channel("JWT in cookie", true, true),
            new Channel("WebSession cookie", true, true),
            new Channel("Cached HTTP Basic", true, true),
            new Channel("Ignored cookie", false, true)
        );

        for (Channel c : cases) {
            System.out.println(c.name() + " -> " + policy(c));
        }
    }
}
```

Chạy:

```bash
javac CsrfDecisionDemo.java
java CsrfDecisionDemo
```

**Stdout chính xác:**

```text
JS Bearer header -> EXEMPTION_CAN_BE_REVIEWED
JWT in cookie -> CSRF_REQUIRED
WebSession cookie -> CSRF_REQUIRED
Cached HTTP Basic -> CSRF_REQUIRED
Ignored cookie -> NOT_AUTHENTICATION
```

Từ `ambientFromBrowser` phải được **đánh giá bằng hành vi thực tế**, chứ không chỉ gán boolean theo cảm giác. Cần xét domain/path cookie, SameSite, browser version, gateway/BFF và cách server xác thực.

## 5. CSRF mặc định trong Spring Security Reactive

Trong WebFlux, `@EnableWebFluxSecurity` và `SecurityWebFilterChain` thường bật CSRF protection mặc định. `CsrfWebFilter` bảo vệ các request thay đổi trạng thái theo `ServerWebExchangeMatcher`, thông thường yêu cầu CSRF cho POST/PUT/PATCH/DELETE và không yêu cầu cho GET/HEAD/OPTIONS/TRACE.

Điều này **khác** authentication và authorization:

- **CSRF:** request browser có thêm bằng chứng không thể tự đính kèm từ trang tấn công không?
- **Authentication:** credential (session, Bearer, Basic) có thực sự hợp lệ không?
- **Authorization:** Authentication có được phép thao tác đối với route/record/tenant không?

Vì vậy trong API Bearer-only được miễn CSRF, POST **không Bearer** vẫn phải 401; Bearer **đúng nhưng thiếu scope** phải 403; Bearer **đúng và đủ scope** có thể 200 mà không có CSRF token. Ở browser session chain, POST thiếu CSRF token có thể bị 403 **trước khi** logic quyền chạy.

### 5.1. Cần giới hạn đúng chain

`ServerHttpSecurity.securityMatcher(...)` chọn **SecurityWebFilterChain** được áp dụng cho URL. `authorizeExchange().pathMatchers(...)` chỉ chọn **authorization rule bên trong chain**; nó **không giới hạn tác động** của `csrf.disable()` vào một path nếu chain đó đang match tất cả.

Một cấu hình dễ review:

```text
@Order(1): /api/**
    OAuth2 Resource Server Bearer header
    API không chấp nhận WebSession hoặc HTTP Basic để auth
    csrf.disable() chỉ tại chain này
    authorization scope/role/object-level vẫn bật

@Order(2): catch-all browser
    formLogin + WebSession cookie
    CSRF bật mặc định (bao gồm POST login/logout)
    authorization rõ ràng, default deny
```

Nếu trộn hai loại authentication trong một chain mà không thể loại cookie fallback, **đừng** dùng matcher kiểu “request nào có `Authorization` thì bỏ CSRF”. Header do client khai không phải bằng chứng rằng route hoàn toàn không dùng cookie.

## 6. Project Spring Boot WebFlux Java 17+ với hai chain

Project sau thiết kế rõ hai bề mặt:

- `POST /api/transfer`: mô phỏng lệnh ghi, chỉ chấp nhận JWT Bearer header có scope `transfer:write`. **Không cần CSRF token**, nhưng vẫn kiểm chữ ký và quyền.
- `GET /api/public`: public.
- `GET /web/private`: user form login qua WebSession.
- `POST /web/save`: **cần CSRF token hợp lệ** dù có cookie session.
- `GET /web/csrf`: endpoint demo cùng-origin để lấy token bảo vệ `POST /web/save`; cần session authenticated.

JWT test được ký bằng HS256 với khóa **hard-code dành riêng cho demo localhost**. Trong sản phẩm, tuyệt đối không để client biết secret, không hard-code signing key và không cho frontend tự mint JWT. Thay bằng IdP/JWKS đã xác thực, kiểm `iss`, `aud`, `exp`, `nbf`, scope và token type, cấu hình bảo vệ khóa/quay vòng khóa.

### 6.1. Tệp dự án và dependency

```text
csrf-bearer-webflux/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/csrf/
    │   │   ├── CsrfBearerApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── DemoController.java
    │   └── resources/application.properties
    └── test/java/demo/csrf/
        └── CsrfBearerTests.java
```

Dùng Java 17+ và Spring Boot `3.5.7` làm mốc dependency giáo trình. Khi vận hành thực, nâng lên phiên bản còn hỗ trợ và bản vá theo policy dự án. Không thêm `spring-boot-starter-web` làm app chọn Servlet stack.

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
    <artifactId>csrf-bearer-webflux</artifactId>
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
            <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
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
```

`src/main/resources/application.properties`:

```properties
spring.application.name=csrf-bearer-webflux
server.port=8080
```

`src/main/java/demo/csrf/CsrfBearerApplication.java`:

```java
package demo.csrf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfBearerApplication {
    public static void main(String[] args) {
        SpringApplication.run(CsrfBearerApplication.class, args);
    }
}
```

### 6.2. SecurityConfig: chỉ /api/** miễn CSRF

`src/main/java/demo/csrf/SecurityConfig.java`:

```java
package demo.csrf;

import java.nio.charset.StandardCharsets;
import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;

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
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    static final String DEMO_ISSUER = "https://issuer.example.invalid";

    // Chỉ để tạo JWT đã ký trong test; KHÔNG dùng production.
    static SecretKey demoSecret() {
        String raw = "only-for-local-csrf-demo-secret-key-32bytes";
        return new SecretKeySpec(
            raw.getBytes(StandardCharsets.UTF_8), "HmacSHA256");
    }

    @Bean
    ReactiveJwtDecoder jwtDecoder() {
        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withSecretKey(demoSecret())
                .macAlgorithm(MacAlgorithm.HS256)
                .build();
        decoder.setJwtValidator(
            JwtValidators.createDefaultWithIssuer(DEMO_ISSUER));
        return decoder;
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService browserUsers(PasswordEncoder encoder) {
        UserDetails viewer = User.withUsername("viewer")
            .password(encoder.encode("viewer123"))
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(viewer);
    }

    // Bearer-only API: không dùng session/Basic làm nguồn xác thực.
    @Bean
    @Order(1)
    SecurityWebFilterChain bearerApi(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
                .pathMatchers(HttpMethod.POST, "/api/transfer")
                    .hasAuthority("SCOPE_transfer:write")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            .csrf(csrf -> csrf.disable())
            .build();
    }

    // Browser-facing WebSession: CSRF vẫn bật.
    @Bean
    @Order(2)
    SecurityWebFilterChain browser(ServerHttpSecurity http) {
        return http
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/web/public").permitAll()
                .pathMatchers("/login").permitAll()
                .pathMatchers("/web/**").authenticated()
                .anyExchange().denyAll())
            .formLogin(Customizer.withDefaults())
            .httpBasic(basic -> basic.disable())
            .csrf(Customizer.withDefaults())
            .build();
    }
}
```

**Giải thích:**

1. `@Order(1)` và `securityMatcher` giới hạn chain JWT vào `/api/**`. Nếu bỏ `securityMatcher`, chính sách tắt CSRF có thể áp vào các route browser.
2. `oauth2ResourceServer().jwt()` tìm Bearer header và kiểm JWT. Với JWT test hợp lệ, scope `transfer:write` được Spring Security chuyển thành authority `SCOPE_transfer:write`.
3. `NoOpServerSecurityContextRepository` không lưu/nạp Authentication bằng WebSession trên API. Cùng với việc không bật form/Basic ở chain API, điều này giúp tránh fallback cookie-auth. Nhưng **đừng coi NoOp một mình là đủ** nếu bạn có custom filter/proxy lấy identity từ cookie.
4. `csrf.disable()` chỉ dành cho chain API đang có threat model phù hợp; `authorizeExchange` và JWT validation vẫn hoạt động.
5. Chain browser có form login/session cookie; `csrf(Customizer.withDefaults())` giữ bảo vệ mặc định. Khi thêm browser POST khác, CSRF vẫn áp theo matcher.

**Production:** thay `DEMO_ISSUER` và HS256 demo bằng issuer/JWK Set URI từ IdP, xác minh JWT signature, `iss`, audience, `exp`, `nbf`, thuật toán, scope/tenant và loại token; bảo vệ token ở client. `spring-boot-starter-oauth2-resource-server` đã hỗ trợ xác minh JWT chuẩn, không tự decode payload và tin claims.

### 6.3. DemoController: API Bearer và browser cookie tách biệt

`src/main/java/demo/csrf/DemoController.java`:

```java
package demo.csrf;

import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    public record TransferRequest(String destination, int amount) {}

    @GetMapping(value = "/api/public", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> apiPublic() {
        return Mono.just("api-public");
    }

    @PostMapping(value = "/api/transfer",
                 consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> transfer(@RequestBody Mono<TransferRequest> request) {
        // Chỉ mô phỏng; không thực hiện chuyển tiền.
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName())
            .zipWith(request)
            .map(t -> "queued:" + t.getT1() + ":"
                + t.getT2().destination() + ":"
                + t.getT2().amount());
    }

    @GetMapping(value = "/web/public", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> webPublic() {
        return Mono.just("web-public");
    }

    @GetMapping(value = "/web/private", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> webPrivate() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName())
            .map(name -> "browser:" + name);
    }

    // Chỉ dành cho giao diện cùng origin; không bật CORS rộng.
    @GetMapping(value = "/web/csrf", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<ResponseEntity<String>> webCsrf(ServerWebExchange exchange) {
        Mono<CsrfToken> token =
            exchange.getAttribute(CsrfToken.class.getName());
        if (token == null) {
            return Mono.error(new IllegalStateException(
                "CSRF is unavailable for browser chain"));
        }
        return token.map(value -> ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .contentType(MediaType.TEXT_PLAIN)
            .body(value.getToken()));
    }

    @PostMapping(value = "/web/save", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> webSave() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName())
            .map(name -> "saved:" + name);
    }
}
```

`/web/csrf` là endpoint demo để test cấp CSRF token cho đúng session đã login. Token được lấy từ exchange attribute theo tên `CsrfToken.class.getName()`. Spring Security Reactive 6.x dùng `XorServerCsrfTokenRequestAttributeHandler` mặc định (bảo vệ BREACH), nên token gửi từ trang hợp lệ phải đi qua request handler đúng. Không đưa CSRF token vào log/query, không cho origin không tin cậy đọc endpoint này.

Phương thức `/api/transfer` không đọc cookie `SESSION`; tên Alice đến từ `Authentication` do resource server xác minh JWT, và hành vi là trả kết quả mô phỏng. Trong nghiệp vụ thật còn phải validate dữ liệu, phân quyền owner/tenant, idempotency và transaction.

## 7. Kiểm thử WebTestClient: bằng chứng thay vì giả định

Bộ test dùng server WebFlux thật với `@SpringBootTest(RANDOM_PORT)`, không chỉ test service hoặc giả HTTP principal. Nó tạo JWT **HS256 thật** bằng `NimbusJwtEncoder` trong **test** và gửi qua header `Authorization: Bearer`. Decoder của resource server kiểm chữ ký, issuer và thời hạn. Browser tests gửi cookie session sau form login có CSRF, rồi thử POST không/có CSRF.

`src/test/java/demo/csrf/CsrfBearerTests.java`:

```java
package demo.csrf;

import java.time.Instant;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import com.nimbusds.jose.jwk.source.ImmutableSecret;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CsrfBearerTests {

    @Autowired
    WebTestClient client;

    private static String token(String scope, boolean expired) {
        JwtEncoder encoder = new NimbusJwtEncoder(
            new ImmutableSecret<>(SecurityConfig.demoSecret()));

        Instant now = Instant.now();
        JwtClaimsSet claims = JwtClaimsSet.builder()
            .issuer(SecurityConfig.DEMO_ISSUER)
            .subject("alice")
            .issuedAt(expired ? now.minusSeconds(3600) : now)
            .notBefore(expired ? now.minusSeconds(3500) : now.minusSeconds(5))
            .expiresAt(expired ? now.minusSeconds(600) : now.plusSeconds(900))
            .claim("scope", scope)
            .build();

        return encoder.encode(JwtEncoderParameters.from(
            JwsHeader.with(MacAlgorithm.HS256).build(), claims))
            .getTokenValue();
    }

    private static String session(
            EntityExchangeResult<?> result, String earlier) {
        ResponseCookie value = result.getResponseCookies()
            .getFirst("SESSION");
        return value == null ? earlier : value.getValue();
    }

    private static String csrfFromHtml(String html) {
        assertNotNull(html);
        Matcher tag = Pattern.compile(
            "(?is)<input\\b(?=[^>]*\\bname\\s*=\\s*['\\\"]_csrf['\\\"])[^>]*>")
            .matcher(html);
        assertTrue(tag.find(), "No _csrf hidden field");

        Matcher value = Pattern.compile(
            "(?i)\\bvalue\\s*=\\s*['\\\"]([^'\\\"]+)['\\\"]")
            .matcher(tag.group());
        assertTrue(value.find(), "No CSRF value");
        return value.group(1);
    }

    private String loginBrowser() {
        EntityExchangeResult<String> page =
            client.get().uri("/login")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).returnResult();

        String cookie = session(page, null);
        assertNotNull(cookie, "Missing SESSION cookie");
        String csrf = csrfFromHtml(page.getResponseBody());

        EntityExchangeResult<byte[]> login =
            client.post().uri("/login")
                .cookie("SESSION", cookie)
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("username", "viewer")
                    .with("password", "viewer123")
                    .with("_csrf", csrf))
                .exchange()
                .expectStatus().is3xxRedirection()
                .expectBody().returnResult();

        String location = login.getResponseHeaders()
            .getFirst(HttpHeaders.LOCATION);
        assertNotNull(location);
        assertFalse(location.contains("error"));
        return session(login, cookie);
    }

    @Test
    void publicApiDoesNotRequireAuth() {
        client.get().uri("/api/public")
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("api-public");
    }

    @Test
    void apiPostWithoutBearerIs401NotCsrf403() {
        client.post().uri("/api/transfer")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"destination\":\"demo\",\"amount\":1}")
            .exchange().expectStatus().isUnauthorized()
            .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void validBearerPostWithoutCsrfSucceeds() {
        client.post().uri("/api/transfer")
            .headers(h -> h.setBearerAuth(token("transfer:write", false)))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"destination\":\"demo\",\"amount\":1}")
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("queued:alice:demo:1");
    }

    @Test
    void validJwtWithoutRequiredScopeIs403() {
        client.post().uri("/api/transfer")
            .headers(h -> h.setBearerAuth(token("profile:read", false)))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"destination\":\"demo\",\"amount\":1}")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void expiredJwtIs401() {
        client.post().uri("/api/transfer")
            .headers(h -> h.setBearerAuth(token("transfer:write", true)))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"destination\":\"demo\",\"amount\":1}")
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void httpBasicCannotReplaceBearer() {
        client.post().uri("/api/transfer")
            .headers(h -> h.setBasicAuth("viewer", "viewer123"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"destination\":\"demo\",\"amount\":1}")
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void tokenCookieIsNotAcceptedAsBearerHeader() {
        client.post().uri("/api/transfer")
            .cookie("access_token", token("transfer:write", false))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"destination\":\"demo\",\"amount\":1}")
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void browserSessionCookieCannotAuthorizeBearerApi() {
        String cookie = loginBrowser();
        client.post().uri("/api/transfer")
            .cookie("SESSION", cookie)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"destination\":\"demo\",\"amount\":1}")
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void bearerStillAuthorizesWhenUnrelatedSessionCookieExists() {
        String cookie = loginBrowser();
        client.post().uri("/api/transfer")
            .cookie("SESSION", cookie)
            .headers(h -> h.setBearerAuth(token("transfer:write", false)))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"destination\":\"demo\",\"amount\":1}")
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("queued:alice:demo:1");
    }

    @Test
    void anonymousBrowserRouteRedirectsToLogin() {
        client.get().uri("/web/private")
            .exchange().expectStatus().is3xxRedirection()
            .expectHeader().value(HttpHeaders.LOCATION,
                location -> assertTrue(location.contains("/login")));
    }

    @Test
    void bearerDoesNotAutomaticallyLogIntoBrowserChain() {
        client.get().uri("/web/private")
            .headers(h -> h.setBearerAuth(token("transfer:write", false)))
            .exchange().expectStatus().is3xxRedirection();
    }

    @Test
    void browserLoginPostWithoutCsrfIsRejected() {
        client.post().uri("/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData("username", "viewer")
                .with("password", "viewer123"))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void authenticatedBrowserPostWithoutCsrfIsRejected() {
        String cookie = loginBrowser();

        client.post().uri("/web/save")
            .cookie("SESSION", cookie)
            .exchange().expectStatus().isForbidden();

        client.get().uri("/web/private")
            .cookie("SESSION", cookie)
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("browser:viewer");
    }

    @Test
    void browserPostWithValidCsrfIsAccepted() {
        String cookie = loginBrowser();

        EntityExchangeResult<String> csrfResponse =
            client.get().uri("/web/csrf")
                .cookie("SESSION", cookie)
                .exchange().expectStatus().isOk()
                .expectBody(String.class).returnResult();

        String csrf = csrfResponse.getResponseBody();
        assertNotNull(csrf);
        assertFalse(csrf.isBlank());

        client.post().uri("/web/save")
            .cookie("SESSION", cookie)
            .header("X-CSRF-TOKEN", csrf)
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("saved:viewer");
    }
}
```

Chạy:

```bash
mvn test
```

Với đúng class ở trên, mục tiêu là **14 bài test**. Đây là giáo trình cho người đọc chạy trong môi trường phù hợp; **không tuyên bố các test đã thực thi** tại dự án của bạn. Helper ký JWT chỉ phục vụ local test: không đưa secret vào frontend hoặc production; không biến demo thành Authorization Server.

### 7.1. Vì sao các negative tests có ý nghĩa?

- **Không Bearer → 401**, không phải 403 do CSRF: chứng minh CSRF đã được miễn **nhưng authentication vẫn chạy**.
- **Bearer đúng, không CSRF → 200:** chứng minh trường hợp được miễn hoạt động đúng như mong đợi.
- **Bearer đúng, thiếu scope → 403:** chứng minh `hasAuthority("SCOPE_transfer:write")` còn nguyên.
- **JWT hết hạn → 401:** chứng minh việc disable CSRF không bỏ JWT validation.
- **HTTP Basic → 401** và **JWT trong cookie → 401:** API không có đường credential ambient thay thế.
- **WebSession cookie browser thật nhưng không Bearer → 401:** chứng minh không dùng WebSession để cấp Authentication trên API.
- **WebSession cookie + Bearer đúng → 200:** browser có thể đính cookie không liên quan; API vẫn xác thực bằng Bearer.
- **Browser POST không CSRF → 403**, nhưng POST cùng session và token đúng → 200: CSRF còn hoạt động ở chain cookie-auth.
- **Bearer header đến route browser không tự đăng nhập:** hai chain tách auth schemes.

`WebTestClient` là HTTP client có thể đặt header/cookie tùy ý: nó chứng minh cấu hình **server**, không tự chứng minh trình duyệt thật có gửi cookie theo SameSite hay có tạo preflight. Để xác minh đầy đủ, cần thêm browser tests từ origin khác và kiểm tra proxy/gateway.

## 8. Chạy thủ công bằng curl

Dùng `mvn spring-boot:run` rồi mở terminal khác:

```bash
curl -i http://localhost:8080/api/public

curl -i -X POST http://localhost:8080/api/transfer \
  -H 'Content-Type: application/json' \
  -d '{"destination":"demo","amount":1}'

curl -i -X POST http://localhost:8080/api/transfer \
  -H 'Cookie: access_token=not-a-token' \
  -H 'Content-Type: application/json' \
  -d '{"destination":"demo","amount":1}'

curl -i --user viewer:viewer123 -X POST \
  http://localhost:8080/api/transfer \
  -H 'Content-Type: application/json' \
  -d '{"destination":"demo","amount":1}'

curl -i http://localhost:8080/web/private
curl -i -X POST http://localhost:8080/web/save
```

Kỳ vọng: API public 200; ba lệnh API POST thiếu Bearer hợp lệ là **401**; `GET /web/private` chưa login được redirect `/login`; `POST /web/save` không CSRF token trả **403**. Trên Windows PowerShell, nếu `curl` là alias của lệnh khác, dùng `curl.exe`.

Để gửi Bearer **hợp lệ**:

```bash
# Thay placeholder bằng JWT được cấp hợp lệ, KHÔNG dán nguyên chuỗi này.
curl -i -X POST http://localhost:8080/api/transfer \
  -H 'Authorization: Bearer <VALID_SIGNED_TEST_JWT>' \
  -H 'Content-Type: application/json' \
  -d '{"destination":"demo","amount":1}'
```

Đây là lệnh **có placeholder**. Mã test ở phần 7 tự tạo token HS256 có chữ ký đúng và gửi request thực, nên `mvn test` là đường kiểm chứng happy path **không cần IdP ngoài**. Không có API phát token tùy tiện trong demo; với hệ thống thật cần token từ Authorization Server. Không đưa token/password thật vào shell history/log; dùng HTTPS ngoài localhost.

## 9. CORS, SameSite, Origin và Fetch Metadata là những lớp khác nhau

### 9.1. CORS không phải chứng minh CSRF đã được giải quyết

CORS quản lý browser có thể thực hiện một số cross-origin fetch và đọc response hay không. Header `Authorization` do JavaScript thêm thường gây preflight vì không phải safelisted header. Tuy nhiên:

- HTML `form` POST hoặc top-level navigation có cơ chế khác với `fetch` custom-header.
- Một cuộc tấn công CSRF có thể chỉ cần **gửi được request**, không cần đọc response.
- CORS không xác minh username, JWT, quyền hay CSRF token.
- Nếu API dùng session cookie, đừng tắt CSRF chỉ vì CORS bị hạn chế.
- Không bật `Access-Control-Allow-Origin: *` kết hợp credentials như một cách “sửa” request từ SPA; dùng allowlist origin hẹp theo chính sách.

### 9.2. SameSite không thay thế toàn bộ CSRF protection

Cookie `SameSite=Lax`/`Strict` có thể giảm một số request cross-site mang cookie, nhưng **site khác origin**. Subdomain khác có thể là *same-site* nhưng *cross-origin*, và attacker có thể kiểm soát một subdomain khác trong một số hệ thống. Browser/client cũ, domain/path cookie, exception điều hướng và các flow SSO cần `SameSite=None; Secure` có thể làm thay đổi kết luận. Với cookie được server dùng làm authentication, **tiếp tục bảo vệ CSRF**.

### 9.3. Origin/Referer/Fetch Metadata

`Origin`, `Referer` và `Sec-Fetch-Site` có thể giúp chặn cross-site requests như lớp bổ sung. Cần xử lý request thiếu header, proxy trusted origins, same-site subdomains, browser không hỗ trợ và CLI/mobile. Không suy ra một header vắng mặt có nghĩa request an toàn, cũng không cho rằng mọi CLI request có `Origin`. Nếu triển khai, đặt policy rõ và test đầy đủ.

### 9.4. GET phải thực sự an toàn

CSRF matcher mặc định không yêu cầu token cho GET/HEAD. Vì vậy **đừng** viết `GET /delete`, `GET /logout-all` hoặc một GET làm chuyển tiền. Dù API bearer-only, việc sử dụng GET có side effect có thể tạo rủi ro qua link/navigation/cache/retry khác. Dùng method có semantics đúng, chống lặp khi cần và kiểm soát quyền.

## 10. Tình huống nâng cấp kiến trúc và bẫy phổ biến

**Bẫy 1 – “API stateless nên tắt CSRF toàn bộ”.** Một cookie JWT tự chứa không cần session server vẫn được browser tự gửi. Tên stateless không thay đổi mô hình CSRF.

**Bẫy 2 – “JWT là Bearer, bỏ CSRF được dù JWT ở cookie”.** Sai. Nếu server lấy JWT từ cookie để tạo principal, phải đánh giá như ambient credential.

**Bẫy 3 – “Chỉ thêm `authorizeExchange.pathMatchers("/api/**")` rồi gọi `csrf.disable()`”.** Không đủ phạm vi. Disable áp vào cả chain; dùng `securityMatcher`/chain tách biệt.

**Bẫy 4 – “Header Authorization có mặt nên được miễn”.** HTTP Basic có thể được browser cache; gateway có thể sinh Bearer từ cookie. Cần kiểm source of trust và fallback.

**Bẫy 5 – “CORS đã chặn cross-site”.** CORS không chặn mọi HTML form hoặc cách request được kích hoạt, và không thay CSRF validation khi cookie ambient.

**Bẫy 6 – “SameSite=Strict giải quyết tuyệt đối”.** Same-site subdomain và thay đổi browser/cookie policy có thể khác mô hình dự tính. Giữ CSRF khi authentication dựa vào cookie.

**Bẫy 7 – “Không dùng CSRF thì có thể bỏ authentication/authorization”.** Ba cơ chế khác nhau. Bearer vẫn cần signature, issuer/audience/expiry, scope và object-level checks.

**Bẫy 8 – “BFF dùng Bearer gọi downstream nên bỏ CSRF ở BFF”.** Browser-facing BFF vẫn nhận `SESSION` cookie, cần CSRF cho mutations.

**Bẫy 9 – “Chỉ test Bearer đúng nhận 200”.** Phải có cookie-only 401, Basic-only 401, expired token 401, wrong scope 403 và browser CSRF 403.

**Bẫy 10 – “Không có CSRF nguy cơ thì app không còn rủi ro nào”.** XSS có thể chiếm Bearer, token có thể bị lộ qua log/URL, JWT validator có thể sai, CORS/proxy có thể bị cấu hình mở. Cần threat model riêng.

### 10.1. Nếu không thể tách chain

`ServerHttpSecurity.CsrfSpec.requireCsrfProtectionMatcher(ServerWebExchangeMatcher)` cho phép chọn request cần CSRF theo matcher, nhưng **đừng** viết matcher bỏ CSRF chỉ khi thấy một header `Authorization` bất kỳ. Một endpoint vừa dùng cookie vừa dùng bearer vẫn có đường credential ambient; nếu không thể loại bỏ fallback cookie, cách đơn giản và an toàn hơn là **giữ CSRF cho request thay đổi trạng thái**.

Fragment minh họa, **không phải cấu hình đầy đủ**:

```java
// browserMutatingMatcher phải phản ánh ROUTE + authentication policy thật,
// không chỉ header do client tự khai.
http.csrf(csrf -> csrf
    .requireCsrfProtectionMatcher(browserMutatingMatcher));
```

Cấu hình chain được giới hạn bởi `securityMatcher("/api/**")` dễ audit và test hơn một matcher phức tạp nhìn header. Khi API đổi phương thức xác thực, cập nhật test/policy cùng lúc.

### 10.2. Proxy có thể thay đổi toàn bộ kết luận

Nếu browser gửi cookie đến API gateway và gateway biến nó thành Bearer header cho resource server, backend chỉ thấy Bearer **nhưng ingress vẫn dễ bị CSRF nếu không có protection**. Đánh giá theo **đường user-agent → dịch vụ đầu tiên chấp nhận ambient credential**, không chỉ log ở service cuối.

## 11. Checklist review trước khi miễn CSRF

1. **Kiểm inventory auth:** Header Bearer, cookie token, WebSession, Basic, custom proxy principal, OAuth2 login; chứng minh route không có fallback ambient.
2. **Kiểm chain:** `@Order`, `securityMatcher`, default deny, URL rewrite, gateway path và route matching.
3. **Test cookie-only → 401** trên mọi state-changing bearer-only API, kể cả một `SESSION` cookie thực đã login thành công ở website.
4. **Test Basic-only → 401**, token-cookie-only → 401, expired/invalid JWT → 401.
5. **Test đúng Bearer không CSRF → 2xx** và sai scope → 403; không mở quyền cho credential không hợp lệ.
6. **Giữ CSRF ở browser chain**, gồm POST login/logout/session mutations; test thiếu token → 403 và đủ token + session → 2xx.
7. **Kiểm JWT/opaque validation:** signature hoặc introspection, issuer, audience, exp, nbf, type, key rotation và scope/tenant.
8. **Kiểm browser credential policy:** SameSite, Secure, HttpOnly, fetch credentials mode, Basic cache, multiple subdomains, SSO/BFF.
9. **Kiểm CORS và Origin:** allowed origins hẹp, preflight, Fetch Metadata/Origin/Referer bổ trợ nhưng không phải lý do duy nhất miễn CSRF.
10. **Kiểm XSS/token storage:** CSP, output escaping, scripts, refresh token lifecycle, không đưa token vào URL/log.
11. **Kiểm method safety:** GET không side effect, mutation có validation và idempotency/transaction khi phù hợp.
12. **CI hồi quy:** Bất kỳ thay đổi auth transport, proxy, login hoặc cookie handling phải chạy lại negative tests.
13. **Test ngoài localhost:** Browser thật với origin khác, reverse proxy/ingress thật, cookie policy đa trình duyệt.
14. **Ghi lại quyết định:** Chính xác đường nào được miễn, căn cứ credential không ambient, và điều kiện khiến phải bật CSRF lại.

## 12. Câu hỏi tự đánh giá

**1.** API chỉ nhận Bearer header do JavaScript đáng tin tự đặt; website tấn công không có token. Có thể miễn CSRF không?  
**Có thể cân nhắc** trong đúng phạm vi API, sau khi chứng minh không có cookie/Basic/session fallback và vẫn kiểm authentication/authorization.

**2.** Chuyển JWT sang cookie `HttpOnly`. Có giữ được kết luận cũ không?  
**Không.** Cookie có thể được browser gửi tự động; CSRF phải được đánh giá lại và thường cần bảo vệ.

**3.** BFF nhận `SESSION` rồi gọi downstream bằng Bearer. Browser POST đến BFF có cần CSRF?  
**Có.** Ranh giới browser-facing dựa vào ambient cookie.

**4.** Browser gửi cookie không liên quan kèm Bearer; API luôn bỏ qua cookie. Cookie đó có tự cấp quyền không?  
**Không.** Cần test cookie-only 401 để chứng minh.

**5.** Vì sao API bearer-only POST thiếu token phải trả 401, không phải 403 do CSRF?  
Bởi CSRF đã được miễn ở API chain, **nhưng vẫn cần authentication**.

**6.** Bearer đúng chữ ký nhưng thiếu scope khi gọi POST nhận gì?  
**403 Forbidden** theo authorization policy.

**7.** Có thể thay CSRF bằng CORS cho endpoint session cookie không?  
**Không.** CORS không ngăn mọi request kiểu form/navigation và không thay synchronizer CSRF token.

**8.** HTTP Basic là header Authorization, có miễn CSRF như Bearer do JS đặt không?  
**Không được suy ra vậy.** Browser có thể tự gửi Basic đã cache.

**9.** Chỉ dùng `authorizeExchange.pathMatchers("/api/**")` có làm `csrf.disable()` tác động riêng `/api/**` không?  
**Không.** Cần `securityMatcher` hoặc matcher CSRF đúng.

**10.** Nếu xuất hiện XSS đánh cắp Bearer token, có phải CSRF exemption là nguyên nhân duy nhất?  
**Không.** Token theft/XSS là threat model khác; cần bảo vệ frontend/token và backend authorization.

### Tài liệu tham khảo chính thức

- Spring Security 6.5, *CSRF for WebFlux*: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
- Spring Security, *CSRF Considerations* (stateless/cookie/HTTP Basic): https://docs.spring.io/spring-security/reference/features/exploits/csrf.html
- Spring Security, *WebFlux Security*: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security 6.5, `ServerHttpSecurity.CsrfSpec` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.CsrfSpec.html
- Spring Security 6.5, *Reactive OAuth2 Resource Server JWT*: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
- OWASP, *Cross-Site Request Forgery Prevention Cheat Sheet*: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- MDN, *Request.credentials*: https://developer.mozilla.org/en-US/docs/Web/API/Request/credentials
- MDN, *Set-Cookie SameSite*: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie

**Tóm lại:** Quyết định miễn CSRF phải dựa trên **cách trình duyệt có thể tự đính kèm credential được server chấp nhận**. Bearer header do client tin cậy chủ động đặt trên API bearer-only có thể là trường hợp miễn phù hợp; JWT/session cookie, browser Basic hoặc BFF cookie thì không. Hãy tách `SecurityWebFilterChain`, giữ CSRF cho browser, và kiểm chứng bằng cả request thành công lẫn negative tests trước khi triển khai.