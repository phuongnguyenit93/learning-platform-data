# Phối hợp CORS với cookie phiên, CSRF và Bearer token trong Spring Security Reactive

> **Module:** Spring Security - reactive  
> **Nhóm kiến thức:** Cấu hình CORS  
> **Đích học tập:** Phân biệt CORS, authentication, cookie/session và CSRF; cấu hình đúng preflight, origin, credentials và headers cho hai kiểu client; kiểm chứng bằng Spring WebFlux, Spring Security, WebTestClient và các tình huống lỗi thực tế.

## 1. Tại sao bài toán này dễ cấu hình sai?

Giả sử có một frontend tại `http://localhost:5173` và Spring WebFlux API tại `http://localhost:8080`. Hai địa chỉ khác **origin** vì khác cổng, dù cùng host. Frontend có hai kiểu thao tác:

1. **Web app đăng nhập bằng session cookie:** browser giữ cookie `SESSION` và tự đính kèm khi gọi API, ví dụ `POST /session/notes`. Request thay đổi dữ liệu phải mang **CSRF token** hợp lệ, không chỉ cookie.
2. **Client API gắn Bearer access token:** JavaScript chủ động gửi `Authorization: Bearer ...` ở từng request, ví dụ `POST /token/notes`. Trình duyệt thường gửi **CORS preflight** vì header Authorization không phải simple request header. JWT Resource Server phải tự xác minh token.

Lỗi phổ biến:

- Bật `Access-Control-Allow-Origin: *` và `Access-Control-Allow-Credentials: true` cho cookie session, khiến browser không chấp nhận response.
- Nhầm CORS với cơ chế xác thực, nghĩ rằng chỉ cần chặn origin lạ là API đã an toàn với `curl`/server khác.
- Tắt CSRF chỉ vì đã bật CORS; request độc hại có thể vẫn **gây tác dụng phụ** dù attacker không được đọc response.
- Để authentication filter chặn `OPTIONS` preflight vì preflight không mang session cookie hoặc Bearer token.
- Cho phép cookie session ở chính API đã tắt CSRF vì “API có JWT”.
- Quên cho phép header `Authorization` hoặc `X-CSRF-TOKEN` trong `Access-Control-Allow-Headers`, khiến browser chặn request trước khi đến controller.
- Gửi Bearer token trong response URL/log hoặc lưu dài hạn ở vùng JavaScript dễ bị XSS đánh cắp.

**Nguyên tắc:** CORS là chính sách *browser có được đọc cross-origin response và gửi request dưới điều kiện nào*. Authentication chứng minh danh tính, authorization cấp quyền, còn CSRF bảo vệ các thao tác dùng credentials mà browser có thể tự đính kèm. Không một thành phần nào thay được thành phần còn lại.

## 2. Origin khác Site; cookie phụ thuộc cả hai

Một **origin** là bộ ba `scheme + hostname + port`. `https://app.example.com` và `https://api.example.com` khác origin do hostname, nhưng có thể **same-site** trong cách đánh giá cookie (phụ thuộc scheme và registrable domain). `http://localhost:5173` và `http://localhost:8080` khác origin do port nhưng thường được xem là same-site.

| Frontend | API | Same origin? | Điểm cần lưu ý |
| --- | --- | --- | --- |
| `http://localhost:5173` | `http://localhost:8080` | Không | CORS do khác port; local cookies có thể same-site |
| `https://app.example.com` | `https://api.example.com` | Không | CORS; cookie domain/path và site cần xét riêng |
| `https://app.example.net` | `https://api.example.com` | Không | Cross-site; cookie `SameSite=None; Secure` có thể cần nếu thiết kế dựa vào third-party cookie |
| `https://api.example.com` | `https://api.example.com` | Có | Không cần CORS, nhưng CSRF vẫn có thể cần khi dùng auto-sent credential |

**SameSite không phải CORS.** Một cookie có thể được trình duyệt gửi hoặc không dựa trên `SameSite`, `Secure`, `Path`, `Domain` và browser privacy controls; việc frontend đọc response lại chịu Same-Origin Policy/CORS. CORS không thể ép browser gửi cookie bị chặn bởi SameSite hoặc chính sách third-party cookies.

Với website và API có thể đưa về cùng origin, một **Backend-for-Frontend (BFF)** hoặc reverse proxy same-origin thường làm đơn giản hóa cookie và CSRF. Dùng cross-site cookie không chỉ là thêm hai HTTP headers: phải cân nhắc bảo vệ browser, HTTPS, privacy restrictions và client compatibility.

## 3. CORS và CSRF chống hai nguy cơ khác nhau

**CORS:** browser kiểm tra response headers như `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers` và `Access-Control-Allow-Credentials` để quyết định script ở origin khác có được truy cập response và gửi request cần preflight hay không.

**CSRF:** một trang độc hại có thể khiến browser của nạn nhân gửi request tới website nơi nạn nhân đã đăng nhập, lợi dụng cookie hoặc credential **tự động được gửi**. Server cần chứng minh thao tác không chỉ được browser thực hiện hộ attacker: CSRF token trong form/header, `Origin`/`Referer` checks thích hợp, SameSite và thiết kế HTTP verbs đúng.

Một form cross-site đơn giản có thể gây **POST** ngay cả khi server không bật CORS cho attacker. Browser không cho script attacker đọc response, nhưng tác dụng phụ ở server **có thể đã xảy ra**. Do đó cấu hình CORS hẹp **không thay thế CSRF protection**.

~~~mermaid
flowchart TD
    A["Browser gửi cross-origin request"] --> B{"Request có preflight?"}
    B -->|"Có"| C["OPTIONS + Origin + Access-Control-Request-*"]
    C --> D{"Server CORS cho phép?"}
    D -->|"Không"| E["Browser chặn actual request"]
    D -->|"Có"| F["Actual request"]
    B -->|"Không"| F
    F --> G["Authentication: session cookie hoặc Bearer"]
    G --> H["CSRF nếu dựa vào auto-sent credentials"]
    H --> I["Authorization theo role/scope/object"]
    I --> J["Controller / service"]
    J --> K["Response + CORS response headers"]
    K --> L["Browser quyết định script có được đọc response"]
~~~

**CORS không phải firewall cho API.** Client không phải browser như `curl`, backend service hay bot có thể tự gửi HTTP request bất kể CORS. `Origin` header cũng không phải bằng chứng đăng nhập: nhiều HTTP clients có thể tự đặt giá trị này.

## 4. Preflight OPTIONS chứa gì và thiếu gì?

Một request JSON kèm Authorization hoặc một header CSRF tùy chỉnh thường cần preflight:

~~~http
OPTIONS /token/notes HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

Server được phép có thể phản hồi:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: Authorization,Content-Type
Vary: Origin,Access-Control-Request-Method,Access-Control-Request-Headers
~~~

Status 200 là minh họa, một handler phù hợp có thể dùng 204. **Quan trọng là đúng CORS headers**, không phải buộc preflight 200 trong mọi triển khai.

Preflight **không gửi session cookie hoặc Bearer access token như request bình thường**. Nếu security filter đòi Authentication trước khi CORS xử lý, OPTIONS dễ bị 401 hoặc redirect tới `/login`, làm trình duyệt báo lỗi. Spring Security tài liệu yêu cầu CORS được xử lý trước security authentication; WebFlux có thể dùng `CorsWebFilter` hoặc tích hợp CORS vào `ServerHttpSecurity.cors(...)` với `CorsConfigurationSource`.

**Không sửa bằng cách `OPTIONS /** permitAll` rồi bỏ qua CORS policy.** Bạn vẫn phải kiểm soát allowed origin/method/header; ưu tiên CORS filter/integration đúng thứ tự, sau đó test preflight mà **không** gửi credentials.

## 5. CORS headers thiết yếu

| Header | Bên gửi | Tác dụng |
| --- | --- | --- |
| `Origin` | Browser request | Origin đang yêu cầu truy cập |
| `Access-Control-Request-Method` | Browser preflight | Method của actual request sắp tới |
| `Access-Control-Request-Headers` | Browser preflight | Headers không safelisted, như authorization |
| `Access-Control-Allow-Origin` | Server response | Origin nào được phép đọc response |
| `Access-Control-Allow-Credentials` | Server response | Cho browser dùng credentialed cross-origin response khi là true |
| `Access-Control-Allow-Methods` | Server preflight response | Các method được phép |
| `Access-Control-Allow-Headers` | Server preflight response | Các request headers được phép |
| `Access-Control-Expose-Headers` | Server response | Response headers bổ sung được JS đọc; không liên quan cho phép gửi request header |
| `Access-Control-Max-Age` | Server preflight response | TTL browser có thể cache preflight |
| `Vary` | Server/proxy response | Tránh dùng nhầm cached response giữa các Origin/method/header khác nhau |

Khi dùng cookie credentials, phải trả **origin cụ thể** thay vì `*` trong `Access-Control-Allow-Origin`, cùng `Access-Control-Allow-Credentials: true`. Trong Spring, `setAllowedOrigins(List.of("http://localhost:5173"))` và `setAllowCredentials(true)` phản ánh ý định. Đừng dùng `allowedOriginPatterns("*")` như một cách lách hạn chế; nếu phản chiếu mọi origin, mọi website có thể đọc credentialed response khi browser gửi cookie.

**Header Authorization không phải expose header.** `Access-Control-Allow-Headers: Authorization` cho phép frontend *gửi* Authorization. `Access-Control-Expose-Headers` chỉ kiểm soát *đọc response headers*, không cho phép request headers.

## 6. Mô hình A — cookie phiên và CSRF

~~~mermaid
sequenceDiagram
    participant F as Frontend origin :5173
    participant B as Browser
    participant API as WebFlux :8080
    F->>B: Yêu cầu frontend gọi API
    B->>API: OPTIONS /session/notes (nếu JSON/CSRF header)
    API-->>B: CORS response cho Origin được phép
    B->>API: GET /session/csrf + cookie (nếu có)
    API-->>B: CSRF token + session cookie (nếu cần)
    B->>API: POST /login + CSRF + credentials
    API-->>B: Thiết lập session đã xác thực
    B->>API: POST /session/notes + SESSION + X-CSRF-TOKEN
    API->>API: Xác thực session + kiểm CSRF + phân quyền
    API-->>B: 200 và Access-Control-Allow-Origin
~~~

Ở WebFlux, session ID thường nằm trong cookie `SESSION` (không mặc định gọi là `JSESSIONID` như Servlet). `WebSessionServerSecurityContextRepository` lưu SecurityContext trong WebSession. Request tiếp theo có cookie hợp lệ sẽ tải Authentication từ session; cookie là **tham chiếu**, không phải password hoặc JWT.

CSRF cần thiết với **POST/PUT/PATCH/DELETE** được browser gửi với cookie auto-attached. Spring Security WebFlux **bật CSRF protection mặc định**. Theo mặc định, expected token thường lưu trong `WebSession` thông qua `WebSessionServerCsrfTokenRepository` và token được đưa vào exchange attributes. Spring Security 6 mặc định dùng `XorServerCsrfTokenRequestAttributeHandler` để hỗ trợ chống BREACH.

Trong lab, endpoint `GET /session/csrf` trả token đã được request handler cung cấp, rồi frontend gửi lại trong header `X-CSRF-TOKEN`. Cách này tránh nhầm giữa raw `XSRF-TOKEN` cookie và token đã được XOR mask.

**Sau login/logout**, CSRF token có thể bị thay đổi/loại bỏ theo cấu hình. SPA nên lấy token mới khi phiên thay đổi; không lưu mãi token cũ trong localStorage hoặc cache chung.

## 7. Mô hình B — Authorization Bearer header

~~~mermaid
sequenceDiagram
    participant JS as SPA :5173
    participant B as Browser
    participant API as Resource Server :8080
    JS->>B: fetch với Authorization: Bearer
    B->>API: OPTIONS /token/notes (không Bearer)
    API-->>B: Cho origin + Authorization,Content-Type
    B->>API: POST /token/notes + Bearer access token
    API->>API: Xác minh JWT + scope (mỗi request)
    API-->>B: 200 + Access-Control-Allow-Origin
~~~

Với **header-only Bearer API** không chấp nhận session cookie, HTTP Basic hay cơ chế browser tự đính kèm khác để xác thực, thường có thể tắt CSRF cho security chain **của API này** sau khi đánh giá threat model. Phải **không** dùng kết luận này cho một application dùng JWT đặt trong cookie: khi browser tự gửi JWT cookie, CSRF risk vẫn tồn tại.

JWT Resource Server không dựa vào CORS để xác thực token. Nó phải xác minh chữ ký, issuer, expiry/nbf, audience phù hợp và scope. Spring Security JWT thường biến scope thành authority có prefix `SCOPE_`. Default issuer validation không đảm bảo audience đúng với mọi API; bổ sung audience validator theo hợp đồng.

Một access token hợp lệ chưa chắc có quyền đọc/ghi mọi tài nguyên. Sau route-level scope check phải có object/tenant ownership checks ở service.

## 8. Thiết kế lab: hai Spring profiles thay thế nhau

Ta tạo **một Maven project** với hai profiles, mỗi lần chạy **chỉ bật một**:

- `session`: CORS cho origin `http://localhost:5173` + credentials, form login, WebSession và CSRF mặc định; GET token, GET user, POST notes.
- `bearer`: CORS chỉ origin và các headers cho Bearer, không cần credentialed CORS; resource server JWT xác thực từng request, không lưu WebSession security context; tắt CSRF **chỉ** trên Bearer-only chain.
- Hai security chains có cùng phạm vi mặc định nhưng được gắn hai profile khác nhau; không bật cả hai cùng lúc. Điều đó tránh việc vô ý dùng session để xác thực endpoint đã tắt CSRF.
- Controller chỉ trả echo dữ liệu để quan sát bảo mật. Không có repository ghi DB trong lab; **CSRF được kiểm thử bằng việc request đến hay không đến controller**, không phải chứng minh giao dịch dữ liệu thật.

Yêu cầu Java 17+, Maven và Spring Boot `3.3.13` làm phiên bản lab tương thích Spring Security 6.x. Nhánh Boot 3.3 đã hết hỗ trợ OSS, nên dự án production mới phải dùng phiên bản còn được hỗ trợ. Config JWT ở profile bearer cần issuer/OIDC thật cho request token thật; test dùng `mockJwt()` **không** kiểm chứng chữ ký hay issuer.

~~~text
cors-security-reactive/
├── pom.xml
└── src/
    ├── main/java/example/cors/
    │   ├── CorsApplication.java
    │   ├── SecurityConfiguration.java
    │   └── ApiController.java
    ├── main/resources/
    │   └── application.yml
    └── test/java/example/cors/
        ├── SessionCorsTest.java
        └── BearerCorsTest.java
~~~

### 8.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>cors-security-reactive</artifactId>
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
            <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
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

Không thêm `spring-boot-starter-web`. `spring-security-test` có WebTestClient mutators như `csrf()`, `mockUser()` và `mockJwt()`. Các mock security test giúp kiểm tra behavior của filter/authorization, **không** tự chứng minh JWT decoder xác minh chữ ký.

### 8.2. CorsApplication.java

~~~java
package example.cors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsApplication.class, args);
    }
}
~~~

### 8.3. application.yml

~~~yaml
server:
  port: 8080
~~~

Để chạy profile `bearer` với token thật, phải cấu hình thêm một issuer hoạt động bằng environment variable chuẩn của Spring Boot:

~~~bash
export SPRING_SECURITY_OAUTH2_RESOURCESERVER_JWT_ISSUER_URI=https://issuer.example.com/issuer
~~~

Lệnh trên chỉ là cấu hình mẫu; `issuer.example.com` phải thay bằng issuer thật và issuer phải cung cấp metadata/JWK Set hợp lệ. Khi chạy Windows PowerShell, set env variable theo cú pháp PowerShell của phiên terminal đó. Không tự ký token bằng secret cố định trong source code hoặc dùng token không kiểm chứng.

## 9. SecurityConfiguration: hai chính sách CORS và hai chain tách profile

File `src/main/java/example/cors/SecurityConfiguration.java`:

~~~java
package example.cors;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
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
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.context.WebSessionServerSecurityContextRepository;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {

    private static final String FRONTEND = "http://localhost:5173";

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        // Cookie session: chỉ cho origin cụ thể và credentials.
        CorsConfiguration session = new CorsConfiguration();
        session.setAllowedOrigins(List.of(FRONTEND));
        session.setAllowCredentials(true);
        session.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        session.setAllowedHeaders(
            List.of("Content-Type", "X-CSRF-TOKEN", "X-XSRF-TOKEN"));
        session.setMaxAge(1800L);

        // Header-only Bearer: không dùng cookie credentials.
        CorsConfiguration bearer = new CorsConfiguration();
        bearer.setAllowedOrigins(List.of(FRONTEND));
        bearer.setAllowCredentials(false);
        bearer.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        bearer.setAllowedHeaders(
            List.of("Authorization", "Content-Type"));
        bearer.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/session/**", session);
        source.registerCorsConfiguration("/login", session);
        source.registerCorsConfiguration("/logout", session);
        source.registerCorsConfiguration("/token/**", bearer);
        return source;
    }

    @Bean
    @Profile("session")
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    @Profile("session")
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails student = User.withUsername("student")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(student);
    }

    @Bean
    @Profile("session")
    SecurityWebFilterChain sessionChain(
            ServerHttpSecurity http,
            CorsConfigurationSource corsSource) {

        var repo = new WebSessionServerSecurityContextRepository();

        return http
            .cors(cors -> cors.configurationSource(corsSource))
            .securityContextRepository(repo)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/session/csrf").permitAll()
                .pathMatchers("/login", "/logout").permitAll()
                .pathMatchers("/session/**").authenticated()
                .anyExchange().denyAll()
            )
            .formLogin(form -> form.securityContextRepository(repo))
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .csrf(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Profile("bearer")
    SecurityWebFilterChain bearerChain(
            ServerHttpSecurity http,
            CorsConfigurationSource corsSource) {

        var noOp = NoOpServerSecurityContextRepository.getInstance();

        return http
            .cors(cors -> cors.configurationSource(corsSource))
            .securityContextRepository(noOp)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/token/me")
                    .authenticated()
                .pathMatchers(HttpMethod.POST, "/token/notes")
                    .hasAuthority("SCOPE_notes.write")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .requestCache(ServerHttpSecurity.RequestCacheSpec::disable)
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .build();
    }
}
~~~

**Đọc kỹ từng quyết định:**

1. `CorsConfigurationSource` có *cấu hình theo path*, không phải cho mọi origin/method. Session và bearer đều cho frontend cụ thể; chỉ session có `allowCredentials(true)`.
2. `sessionChain` bật CORS đúng vị trí thông qua `ServerHttpSecurity.cors(...configurationSource...)`, để preflight không bị coi là anonymous request rồi chặn trước CORS.
3. Session dùng `WebSessionServerSecurityContextRepository` và form login; CSRF vẫn bật bằng mặc định. Cookie/session được server quản lý; muốn bảo vệ HTTPS/cookie flags trong production phải cấu hình WebSession cookie policy tương ứng.
4. Bearer chain dùng Resource Server JWT, không dùng form login/Basic/session authentication và `NoOpServerSecurityContextRepository`. **Chỉ vì chain này hoàn toàn header-only** nên CSRF được tắt trong lab.
5. Để tạo token thật, Resource Server cần issuer/JWKS đáng tin, JWT signature/timestamp/issuer validation và audience phù hợp với API. Nó **không cấp token**; token đến từ Authorization Server/IdP.
6. `hasAuthority("SCOPE_notes.write")` chỉ bảo vệ route; method service thao tác dữ liệu thật vẫn phải kiểm tra owner/tenant/other business rules.
7. `anyExchange().denyAll()` chặn các URL chưa khai báo. Khi chạy session profile, /token không trở thành endpoint mở; khi chạy bearer profile, /session và /login không được bật.
8. Nếu cần cả session UI và Bearer API trong một deployment, không sao chép nguyên hai chain profile rồi bật cùng lúc. Hãy cấu hình **các securityMatcher tách URL, @Order rõ ràng, repository/auth mechanism/CSRF riêng từng chain** và test rằng không chain nào chấp nhận credential không mong muốn.

### Vì sao không dùng CORS wildcard cho session?

Khi `allowCredentials(true)`, browser không chấp nhận `Access-Control-Allow-Origin: *`. Spring cũng có các kiểm tra cấu hình đối với wildcard allowed origins + credentials. Dùng `allowedOriginPatterns("*")` để phản chiếu mọi Origin không giải quyết rủi ro: attacker origin có thể được phản hồi như trusted origin. Chỉ allowlist các frontend origins thật sự cần, tính cả scheme và port, và quản lý qua configuration theo môi trường.

### Dùng CorsWebFilter độc lập hay tích hợp security?

Spring Security WebFlux có thể tích hợp CORS từ `CorsConfigurationSource` như code trên; tài liệu cũng mô tả `CorsWebFilter` để xử lý preflight trước security. Không cài **hai CORS filters có cấu hình cạnh tranh** rồi hy vọng header được ghép đúng. Chọn một chiến lược, test toàn bộ preflight/actual response, xem cả API gateway hoặc reverse proxy có tự thêm CORS headers không.

## 10. ApiController: CSRF token và hai API bảo vệ

File `src/main/java/example/cors/ApiController.java`:

~~~java
package example.cors;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

record NoteInput(String value) {}

@RestController
public class ApiController {

    @GetMapping("/session/csrf")
    public Mono<Map<String, String>> csrf(ServerWebExchange exchange) {
        Mono<CsrfToken> supplied =
            exchange.getAttribute(CsrfToken.class.getName());

        if (supplied == null) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.INTERNAL_SERVER_ERROR,
                "CSRF protection not configured"));
        }

        return supplied.map(token -> Map.of(
            "headerName", token.getHeaderName(),
            "token", token.getToken()
        ));
    }

    @GetMapping("/session/me")
    public Mono<Map<String, String>> sessionMe() {
        return me();
    }

    @GetMapping("/token/me")
    public Mono<Map<String, String>> tokenMe() {
        return me();
    }

    private Mono<Map<String, String>> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> Map.of(
                "user", ctx.getAuthentication().getName()));
    }

    @PostMapping("/session/notes")
    public Mono<Map<String, String>> sessionWrite(
            @RequestBody Mono<NoteInput> body) {
        return body.map(input -> Map.of("accepted", input.value()));
    }

    @PostMapping("/token/notes")
    public Mono<Map<String, String>> tokenWrite(
            @RequestBody Mono<NoteInput> body) {
        return body.map(input -> Map.of("accepted", input.value()));
    }
}
~~~

**Lưu ý mã này cố tình echo input, không ghi DB.** Mục đích là phân biệt request nào qua được CORS, authentication, CSRF và authorization. Khi chuyển thành cập nhật thực, phải kiểm tra ràng buộc và quyền trên dữ liệu ở service.

Endpoint `GET /session/csrf` đọc `Mono<CsrfToken>` từ exchange attribute do `CsrfWebFilter` cung cấp. Trong Spring Security 6, mặc định có XOR handler để bảo vệ token được render trong response; frontend phải gửi lại chính giá trị token nhận từ endpoint, qua header name trả về (thường `X-CSRF-TOKEN`).

Không công khai endpoint này cho mọi origin: mặc dù token không thay thế authentication, một CORS allowlist sai kết hợp credentialed response có thể làm lộ thông tin không cần thiết. Dùng `Cache-Control: no-store` cho response token hoặc cấu hình header cache thích hợp khi đưa vào production; đừng để proxy public cache token của user.

## 11. Browser: gọi session API đúng cách

**Bước 1 — đăng nhập:** ở bản lab đơn giản, mở `http://localhost:8080/login` trong browser và đăng nhập với `student` / `demo-pass`. Trang form login mặc định của Spring Security tự mang CSRF token. Browser lưu cookie phiên, nếu chính sách cookie cho phép.

**Bước 2 — SPA lấy token sau khi login rồi POST:** code JavaScript trong frontend `http://localhost:5173`:

~~~javascript
const API = "http://localhost:8080";

// Đã login ở browser, cho phép cookie đi cùng cross-origin fetch.
const csrfResponse = await fetch(API + "/session/csrf", {
  credentials: "include",
  cache: "no-store"
});

if (!csrfResponse.ok) {
  throw new Error("Cannot obtain CSRF token");
}

const csrf = await csrfResponse.json();

const result = await fetch(API + "/session/notes", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    [csrf.headerName]: csrf.token
  },
  body: JSON.stringify({value: "hello-session"})
});

if (!result.ok) {
  throw new Error("Session request rejected");
}

console.log(await result.json());
~~~

Output JSON của endpoint sau khi xác thực và CSRF hợp lệ:

~~~json
{"accepted":"hello-session"}
~~~

**Quan trọng:** `credentials: "include"` yêu cầu fetch gửi/nhận cookie theo browser policy, nhưng không vượt qua `SameSite`, `Secure` hay third-party cookie restrictions. Server phải trả `Access-Control-Allow-Credentials: true` và `Access-Control-Allow-Origin` bằng đúng frontend origin (không phải `*`).

Lúc chưa đăng nhập, GET `/session/csrf` có thể cấp token cho phiên anonymous, **không cấp Authentication**. Nếu login làm đổi phiên/token, phải lấy lại CSRF token sau login. Với form login/redirect thực tế, thao tác AJAX login cross-origin cần xử lý redirect, cookie và CSRF cẩn thận; BFF/same-origin login thường dễ vận hành hơn.

**Nếu frontend không thể đọc cookie CSRF do khác host**, cách trả token qua JSON như trên đơn giản hơn double-submit raw cookie. Nếu chọn `CookieServerCsrfTokenRepository.withHttpOnlyFalse()` để JavaScript tự đọc `XSRF-TOKEN`, Spring Security 6 mặc định dùng XOR request handler, nên phải kiểm tra cơ chế resolve token khi gửi raw cookie token qua `X-XSRF-TOKEN`; không mặc định rằng ví dụ Servlet SPA handler áp dụng y hệt trong WebFlux. Chỉ bỏ HttpOnly ở cookie CSRF khi thực sự cần JavaScript đọc cookie, không bỏ HttpOnly cho session cookie.

## 12. Browser: gọi Bearer API đúng cách

Frontend có access token đã nhận từ luồng OAuth2/OIDC phù hợp (Authorization Code + PKCE cho public client hoặc BFF quản lý token server-side). Gắn token trực tiếp vào Authorization header:

~~~javascript
const API = "http://localhost:8080";

// accessToken là biến đã được cấp qua luồng OAuth2 hợp lệ.
const result = await fetch(API + "/token/notes", {
  method: "POST",
  credentials: "omit",
  headers: {
    "Authorization": "Bearer " + accessToken,
    "Content-Type": "application/json"
  },
  body: JSON.stringify({value: "hello-bearer"})
});

if (!result.ok) {
  throw new Error("Bearer request rejected");
}

console.log(await result.json());
~~~

Output JSON nếu token hợp lệ và có scope `notes.write`:

~~~json
{"accepted":"hello-bearer"}
~~~

Browser sẽ preflight vì có Authorization/JSON Content-Type. CORS config phải cho phép `Authorization` và `Content-Type`, nhưng **preflight không mang Bearer token**. Actual request mới mang token và Resource Server xác minh nó. Không gắn Authorization vào URL query string hoặc log, không đưa refresh token vào API không cần nó.

**Tại sao `credentials: "omit"`?** Trong ví dụ bearer chain chỉ nhận token từ header, không cần browser gửi cookie. Đây là cách giảm phụ thuộc vào auto-sent credentials. Không biến nó thành tuyên bố mọi Bearer token an toàn khỏi XSS: script độc hại trên origin frontend có thể dùng/đánh cắp token nếu token đang ở JS-accessible storage. CSP, escaping, token lifetime và cách lưu token vẫn phải được thiết kế.

## 13. Kiểm thử session: CORS preflight + CSRF + cookie

File `src/test/java/example/cors/SessionCorsTest.java`:

~~~java
package example.cors;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@SpringBootTest
@ActiveProfiles("session")
@AutoConfigureWebTestClient
class SessionCorsTest {

    private static final String FRONTEND = "http://localhost:5173";

    @Autowired
    WebTestClient client;

    @Test
    void anonymousPreflightIsAcceptedBeforeAuthentication() {
        client.options()
            .uri("/session/notes")
            .header(HttpHeaders.ORIGIN, FRONTEND)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "content-type,x-csrf-token")
            .exchange()
            .expectStatus().is2xxSuccessful()
            .expectHeader()
            .valueEquals(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, FRONTEND)
            .expectHeader()
            .valueEquals(HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true");
    }

    @Test
    void untrustedOriginIsNotAllowed() {
        client.options()
            .uri("/session/notes")
            .header(HttpHeaders.ORIGIN, "https://evil.invalid")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .exchange()
            .expectHeader()
            .doesNotExist(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }

    @Test
    void csrfBlocksAuthenticatedPostWithoutToken() {
        client.mutateWith(mockUser("student"))
            .post()
            .uri("/session/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("value", "test"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void csrfAllowsAuthenticatedPostWithValidToken() {
        client.mutateWith(mockUser("student"))
            .mutateWith(csrf())
            .post()
            .uri("/session/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("value", "test"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.accepted").isEqualTo("test");
    }

    @Test
    void formLoginCreatesReusableSessionCookie() {
        EntityExchangeResult<byte[]> login = client.mutateWith(csrf())
            .post()
            .uri("/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData(
                "username", "student").with("password", "demo-pass"))
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectBody()
            .returnResult();

        ResponseCookie session =
            login.getResponseCookies().getFirst("SESSION");
        assertNotNull(session);

        client.get()
            .uri("/session/me")
            .cookie("SESSION", session.getValue())
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.user").isEqualTo("student");
    }
}
~~~

**Ý nghĩa và giới hạn:**

- Preflight `OPTIONS` **không có cookie** vẫn nhận CORS success; đây là phép thử xác thực thứ tự CORS trước security.
- Origin lạ không được nhận `Access-Control-Allow-Origin` cho origin đó. Trong bộ lọc Spring mặc định, request CORS không hợp lệ thường nhận 403; test không phụ thuộc nội dung lỗi body.
- `mockUser()` chỉ giả lập Authentication để cô lập kiểm tra CSRF; chưa chứng minh login thật.
- `csrf()` cung cấp CSRF token test hợp lệ; nó không thay việc browser production tự lấy token từ server.
- Test login riêng kiểm tra server tạo `SESSION` và request GET sau đó dùng cookie. Tên cookie tương ứng WebFlux session resolver mặc định của bài lab; thay resolver thì sửa test.
- Khi test production, kiểm tra thêm cookie `Secure`, `HttpOnly`, `SameSite`, HTTPS, expiry và server-side logout invalidation.

## 14. Kiểm thử Bearer: preflight và scope không phụ thuộc CSRF

File `src/test/java/example/cors/BearerCorsTest.java`:

~~~java
package example.cors;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@ActiveProfiles("bearer")
@AutoConfigureWebTestClient
class BearerCorsTest {

    private static final String FRONTEND = "http://localhost:5173";

    @Autowired
    WebTestClient client;

    @MockBean
    ReactiveJwtDecoder decoder;

    @Test
    void preflightWithAuthorizationHeaderNeedsNoBearerToken() {
        client.options()
            .uri("/token/notes")
            .header(HttpHeaders.ORIGIN, FRONTEND)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "authorization,content-type")
            .exchange()
            .expectStatus().is2xxSuccessful()
            .expectHeader()
            .valueEquals(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, FRONTEND)
            .expectHeader()
            .doesNotExist(HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS);
    }

    @Test
    void missingBearerCannotReadPrivateEndpoint() {
        client.get().uri("/token/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void mockJwtWithWriteScopeMayPostWithoutCsrfToken() {
        client.mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_notes.write")))
            .post()
            .uri("/token/notes")
            .header(HttpHeaders.ORIGIN, FRONTEND)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("value", "test-token"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.accepted").isEqualTo("test-token");
    }

    @Test
    void authenticatedJwtWithoutWriteScopeIsForbidden() {
        client.mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_notes.read")))
            .post()
            .uri("/token/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("value", "denied"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void untrustedOriginDoesNotGetCorsPermission() {
        client.options()
            .uri("/token/notes")
            .header(HttpHeaders.ORIGIN, "https://evil.invalid")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .exchange()
            .expectHeader()
            .doesNotExist(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }
}
~~~

**Điểm cần hiểu:** `mockJwt()` tạo Authentication cho WebTestClient; nó **bỏ qua công đoạn lấy JWKS và kiểm chứng chữ ký/issuer của JWT thật**. Nó thích hợp để kiểm tra route/scope/CORS/CSRF behavior, nhưng phải bổ sung integration tests với issuer/decoder thật hoặc test riêng token validator để chứng minh cryptographic authentication và audience validation.

Ở profile bearer, `@MockBean ReactiveJwtDecoder` cung cấp decoder mock cho Spring context test; **không đưa bean này vào production**. Ở test scope, header Authorization không cần chứa một JWT có chữ ký thật vì Security Test đã thiết lập authentication context.

## 15. Chạy test và khởi động riêng từng profile

Tại thư mục Maven project:

~~~bash
mvn clean test
~~~

Kỳ vọng các bài test của `SessionCorsTest` và `BearerCorsTest` chạy thành công. Assertion tập trung vào **cặp origin/credentials**, quyền scope, CSRF và session persistence. Test không chứng minh CORS được browser thực thi ngoài thực tế; nên thử bằng Chrome DevTools/Network trên frontend thật khi triển khai.

Chạy session mode:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=session
~~~

Mở `http://localhost:8080/login`; dùng account demo `student`/`demo-pass`. Sau login, gọi `/session/me` trong browser để thấy principal. Dùng trang frontend tại localhost:5173 thực hiện fetch trong mục 11.

Dừng process trước khi chuyển mode. Chạy bearer mode **sau khi cung cấp issuer hợp lệ**:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=bearer
~~~

Cấu hình Resource Server sẽ dùng issuer/JWKS từ môi trường. Không có IdP/token thật, hãy chỉ chạy các bài kiểm thử `mockJwt()`; đừng dùng `example.com` làm issuer thực hay tạo token không ký để “bỏ qua” xác thực.

### 15.1. Kiểm tra preflight bằng curl

Lệnh sau gửi header tương đương một preflight; `curl` **không thực thi chính sách CORS của browser**, chỉ giúp quan sát response:

~~~bash
curl -i -X OPTIONS "http://localhost:8080/session/notes" \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

Khi chạy session mode, response preflight phải chứa `Access-Control-Allow-Origin: http://localhost:5173` và `Access-Control-Allow-Credentials: true`. Không bắt buộc cookie cho OPTIONS.

Chuyển bearer mode rồi thử:

~~~bash
curl -i -X OPTIONS "http://localhost:8080/token/notes" \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: authorization,content-type"
~~~

Preflight Bearer không có Authorization token mà vẫn cần được CORS handler chấp nhận. Một request `POST /token/notes` thực không Bearer token phải bị chặn bởi resource server dù preflight thành công.

### 15.2. Quan sát lỗi browser

Trong Chrome/Firefox DevTools → Network, xem **hai request**: preflight OPTIONS và actual request. Ghi nhận Origin/Access-Control-Request-Headers, response CORS headers, cookie policy, X-CSRF-TOKEN, HTTP status và console error. Đừng in token/cookie bí mật vào report hoặc screen recording công khai.

## 16. Ma trận expected behavior

| Tình huống | Session + CSRF | Bearer header-only |
| --- | --- | --- |
| Preflight từ origin được allowlist, không auth | **CORS success** | **CORS success** |
| Preflight origin lạ | Không cấp CORS permission | Không cấp CORS permission |
| Actual GET không cookie/token | Được yêu cầu đăng nhập (thường redirect) | **401** |
| Actual GET cookie session hợp lệ | Có Authentication | Cookie không được dùng làm phương thức auth |
| Actual GET Bearer token hợp lệ | Không có Resource Server trong profile session | Authenticated theo JWT |
| POST có cookie session, thiếu CSRF | **403** nếu auth đã có và route được cho phép | Không nhận session làm auth |
| POST cookie + CSRF hợp lệ | Có thể xử lý khi có quyền | Không áp dụng |
| POST Bearer hợp lệ, có write scope, không CSRF | Không dùng Bearer auth trong session profile | Có thể xử lý |
| POST Bearer hợp lệ nhưng thiếu write scope | Không dùng Bearer auth | **403** |
| JWT đặt trong cookie | Cần CSRF vì auto-sent credential | **Không thuộc bảo đảm của Bearer-only chain** |
| `Access-Control-Allow-Origin: *` với credentials | Sai cấu hình | Chỉ hợp lý ở public API không credentials nếu được đánh giá |
| CORS từ origin lạ nhưng token hợp lệ qua curl | curl không bị browser CORS chặn | Authentication/authorization vẫn quyết định |

**Lưu ý 401/403/302:** form login cho request anonymous thường redirect, API Bearer thường trả 401. 403 cũng có thể từ CSRF hoặc thiếu quyền tùy request. Phân biệt HTTP entry point, authentication, CSRF và authorization trước khi sửa rule.

## 17. Cookie flags, SameSite và môi trường triển khai

Với session-based browser app:

- **`Secure`:** chỉ gửi cookie qua HTTPS (ngoại trừ đặc thù localhost/test do browser cho phép). Triển khai production phải dùng HTTPS và forward headers/trust proxy đúng.
- **`HttpOnly`:** ngăn JavaScript trực tiếp đọc session cookie, giảm nguy cơ lộ ID từ XSS; không ngăn XSS thực hiện request hộ user.
- **`SameSite=Lax`/`Strict`:** giảm một số bối cảnh cross-site auto-send; không thay CSRF token cho mọi rủi ro.
- **`SameSite=None; Secure`:** khi kiến trúc thực sự yêu cầu cookie cross-site, nhưng có thể bị browser chặn như third-party cookies. Cần test trên browser/ITP thực tế và cân nhắc BFF.
- **Domain/Path:** hạn chế phạm vi cookie, tránh dùng parent domain quá rộng vô tình chia sẻ session cho subdomain không tin cậy.
- **Session timeout và logout:** phải invalidate server-side WebSession; chỉ xóa cookie client không thu hồi bản sao ID bị đánh cắp.
- **CSRF token lifecycle:** token có thể cần refresh sau login/logout hoặc session rotation; không lưu response CSRF qua shared proxy/public cache.

Cấu hình cookie của WebFlux `WebSession` khác CookieCsrfTokenRepository; không nhầm hai cookie. Nếu dùng `CookieServerCsrfTokenRepository.withHttpOnlyFalse()`, đó là quyết định để JS đọc **CSRF cookie**, **không** có nghĩa tắt HttpOnly của SESSION cookie.

## 18. XSS, CORS và OAuth2: ranh giới tin cậy

CORS không bảo vệ khỏi XSS chạy ngay trong origin frontend đã được phép; script độc hại trên frontend đó có thể gọi API như code hợp lệ và đọc response. Vì vậy bảo vệ XSS, Content Security Policy, quản lý dependency, escape output, code review và tránh lưu access token trong nơi JavaScript dễ bị đọc dài hạn đều quan trọng.

Với Bearer token, frontend origin được allowlist **không có nghĩa** token đến từ frontend đó. Resource Server phải xác thực token, đúng audience, issuer và scope. Một access token có thể bị relay tới API sai audience nếu API không kiểm chứng aud; CORS không nhận diện và sửa lỗi này.

Nếu dùng **BFF**, OAuth2 token có thể được giữ server-side và browser chỉ mang session cookie tới BFF. Khi đó dù backend cuối dùng Bearer tới downstream, browser–BFF lại là **cookie/session + CSRF**. Đừng “tắt CSRF vì BFF gọi downstream bằng Bearer”; hãy xét credential tại **đúng HTTP boundary**.

### Khác biệt giữa credential modes của fetch

- `credentials: "include"`: browser xét gửi cookie cross-origin và chỉ cho JS đọc credentialed CORS response nếu server đồng ý; không ghi đè được cookie restrictions.
- `credentials: "omit"`: không dựa vào browser auto-send cookie; một Authorization header do JavaScript **chủ động đặt** vẫn là request header và sẽ cần CORS cho phép.
- `mode: "no-cors"` không phải mẹo vượt CORS: response sẽ opaque, custom headers/methods bị hạn chế, không giải quyết Authentication/CSRF và không cho script đọc API JSON.

## 19. Những sai lầm thường gặp

1. **Cho `*` với `allowCredentials=true`:** browser không chấp nhận credentialed response; dùng origin allowlist.
2. **Phản chiếu mọi Origin bằng allowedOriginPatterns wildcard:** có thể cho website độc hại đọc response của người đang đăng nhập.
3. **Chặn OPTIONS bằng login filter:** preflight không mang credentials, phải xử lý CORS trước auth.
4. **Cho OPTIONS permitAll nhưng không có CorsConfigurationSource:** browser vẫn thiếu CORS response headers.
5. **Tắt CSRF toàn app khi có JWT:** session/cookie endpoints có thể thành CSRF vulnerable.
6. **Nghĩ JWT trong cookie không cần CSRF:** browser tự đính kèm cookie bất kể JWT bên trong.
7. **Gọi POST bằng cookie mà thiếu X-CSRF-TOKEN:** Spring Security trả 403 khi CSRF bật.
8. **Dùng `Access-Control-Expose-Headers` thay vì Allow-Headers:** không làm Authorization request header hợp lệ.
9. **Quên Origin đúng scheme/port:** `localhost:3000` khác `localhost:5173`; HTTP khác HTTPS.
10. **Tin curl chứng minh CORS bảo vệ API:** curl không có browser SOP; CORS không phải authentication.
11. **Không phân biệt 401/403/302:** có thể do login redirect, CSRF hoặc scope, không chỉ CORS.
12. **Để reverse proxy và Spring cùng ghi CORS headers xung đột:** browser có thể thấy nhiều Access-Control-Allow-Origin và từ chối.
13. **Không thêm Vary khi response phụ thuộc Origin:** shared cache có thể phân phối sai CORS response.
14. **Cho Origin lạ truy cập CSRF endpoint với credentials:** rò response không cần thiết.
15. **Đặt Bearer ở query string/URL hoặc log:** rủi ro lộ qua history, proxy logs và referer.
16. **Bỏ audience validator cho JWT:** token hợp lệ cho service A chưa chắc dùng được cho B.
17. **Không đánh giá third-party cookie block:** CORS đúng nhưng browser vẫn bỏ SESSION cookie.
18. **Giữ CSRF token qua logout/rotation:** token cũ có thể bị từ chối; refresh sau thay đổi authentication state.
19. **Nhầm CORS với authorization dữ liệu:** user đăng nhập vẫn phải bị kiểm tra owner/tenant.
20. **Gộp session và Bearer vào một chain tắt CSRF:** request được xác thực bằng cookie có thể đi qua endpoint không được CSRF bảo vệ.

## 20. Hướng chẩn đoán theo thứ tự

Khi frontend báo “CORS error”, làm theo luồng:

1. Xác định chính xác URL frontend và API: **scheme, host, port**.
2. DevTools → Network → có **OPTIONS** hay không? OPTIONS gửi Origin/Access-Control-Request-* gì? Có cookie/token không? (Preflight chuẩn không mang credential của actual request.)
3. Response preflight có `Access-Control-Allow-Origin` đúng origin, allow methods, allow headers và status phù hợp không?
4. Với session credentialed fetch, có `Access-Control-Allow-Credentials: true` không? Browser có gửi cookie thật không? Có bị `SameSite`, `Secure` hoặc third-party policy chặn không?
5. Nếu actual request được gửi, server trả status gì? 302 login redirect, 401 JWT missing, 403 CSRF/role, 404 route, 5xx app error? Đọc server logs an toàn (không log cookie/token).
6. Nếu POST session thất bại, CSRF token được lấy đúng **phiên hiện hành** chưa? Có gửi đúng header name/token vừa được trả không?
7. Nếu POST Bearer thất bại, Authorization header có thật trên actual request không? Token được ký/validate bằng đúng issuer/audience/scope không?
8. Kiểm tra proxy/WAF có rewrite Origin, Location, Set-Cookie, Vary hoặc CORS headers không; test browser production thật, không chỉ curl.
9. Sau khi xác định tầng lỗi, sửa nhỏ nhất đúng tầng; đừng tắt security/CSRF hoặc mở toàn bộ origins như workaround.

**Quan trọng:** Browser có thể hiển thị “CORS error” khi một response thực là 401/403/500 nhưng thiếu CORS headers. Sửa nguyên nhân authentication/CSRF/authorization và bảo đảm response error vẫn đi qua CORS integration phù hợp, không chỉ thêm ACAO vào success responses.

## 21. Bài tập vận dụng

**Bài A — preflight không auth:** thử OPTIONS `/session/notes` không cookie và OPTIONS `/token/notes` không Bearer. Cả hai phải được trả CORS success ở origin trusted; thử origin lạ không được allow.

**Bài B — CSRF dưới session:** dùng `mockUser()` POST JSON không token, kỳ vọng 403; thêm `csrf()`, kỳ vọng 200. Giải thích vì sao body GET hoặc preflight không thay CSRF token.

**Bài C — Bearer scope:** dùng `mockJwt()` với `SCOPE_notes.read` gọi POST, kỳ vọng 403; đổi sang `SCOPE_notes.write`, kỳ vọng 200. Nêu rõ mock này không kiểm tra chữ ký/audience.

**Bài D — cookie trong JWT:** sửa hệ thống giả định để token được browser tự gửi bằng cookie; phân tích vì sao phải bật CSRF thay vì copy `csrf.disable()` của profile bearer.

**Bài E — allowCredentials wildcard:** thử đổi session origin sang `*` với `allowCredentials(true)`; quan sát lỗi cấu hình/browser và khôi phục allowlist. Giải thích vì sao `allowedOriginPatterns("*")` không phải biện pháp an toàn.

**Bài F — Frontend khác site:** chuyển giả định frontend sang `https://app.example.net`, API sang `https://api.example.com`. Lập bảng cookie SameSite/Secure/Domain/Path, CORS allowlist, CSRF token lifecycle và third-party browser policies. Đề xuất BFF same-origin nếu cookie khó vận hành.

**Bài G — reverse proxy:** giả sử CDN thêm ACAO trong khi Spring cũng thêm. Viết test/inspection để phát hiện duplicate headers, thiếu Vary, Set-Cookie bị đổi thuộc tính và preflight cache khác giữa origins.

**Bài H — authorization đối tượng:** thay API echo bằng POST cập nhật một bản ghi thật; thêm test cho user đúng cookie/token nhưng thiếu quyền tenant/owner. Chứng minh CORS + CSRF + authentication vẫn không tự cấp quyền vào dữ liệu.

### Tiêu chí hoàn thành

- [ ] Phân biệt origin, site, cookie policy và CORS.
- [ ] Giải thích được CORS không thay authentication/authorization/CSRF.
- [ ] Preflight không có cookie/Bearer được xử lý trước security.
- [ ] Session credentialed CORS dùng allowlist origin cụ thể và allowCredentials true.
- [ ] Session POST cần CSRF token; test 403 thiếu token và 200 đủ token.
- [ ] Bearer header được cho phép ở CORS và JWT được xác thực mỗi request.
- [ ] CSRF chỉ disable với header-only API không chấp nhận auto-sent credentials sau threat modeling.
- [ ] JWT trong cookie vẫn được đánh giá CSRF như cookie credentials khác.
- [ ] Biết mockJwt không chứng minh cryptographic JWT validation.
- [ ] Biết cookie Secure/HttpOnly/SameSite, browser privacy và BFF alternatives.
- [ ] Kiểm tra origin/headers/status/redirect/caching và không làm lộ token trong logs.
- [ ] Có negative tests cho forbidden origin, thiếu scope, thiếu CSRF và request anonymous.

## 22. Câu hỏi tự kiểm tra

1. `localhost:5173` và `localhost:8080` là same-origin không? Có nhất thiết cross-site không?
2. Nếu CORS chặn origin lạ đọc response, request POST đơn giản có thể vẫn gây tác dụng phụ không?
3. Vì sao preflight OPTIONS không nên yêu cầu session cookie hoặc Bearer token?
4. Khi dùng cookie session, vì sao `Access-Control-Allow-Origin: *` không phù hợp với credentials?
5. Header nào cho phép frontend gửi `Authorization`? Header nào cho phép đọc response header bổ sung?
6. `credentials: include` có vượt qua SameSite và chính sách third-party cookie của browser không?
7. Khi form login xong, vì sao SPA có thể cần lấy CSRF token mới?
8. Nếu JWT được đặt trong cookie HttpOnly, có thể bỏ CSRF chỉ vì JWT đã ký không?
9. `mockJwt()` kiểm tra những gì và **không** kiểm tra những gì?
10. Vì sao Resource Server cần kiểm tra issuer, expiry, audience và scope ngoài CORS allowlist?
11. Nếu browser báo CORS error, vì sao phải đọc cả 401/403/302 từ Network/server?
12. Vì sao CORS không bảo vệ một API trước curl hoặc script chạy trên origin được tin nhưng đã bị XSS?

## 23. Tài liệu tham khảo

- [Spring Security — CORS for WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/cors.html): CORS before security, CorsWebFilter và CorsConfigurationSource.
- [Spring Security — CSRF for WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html): WebSessionServerCsrfTokenRepository, CookieServerCsrfTokenRepository và XOR handler.
- [Spring Security — Testing CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html): WebTestClient `csrf()`.
- [Spring Security — Testing OAuth2](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html): `mockJwt()` và authority testing.
- [Spring Security — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html): signature, issuer, exp/nbf, scope và audience validation.
- [Spring Framework — CORS in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html): origin, headers, preflight và response behavior.
- [MDN — CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): preflight và credentialed requests.
- [MDN — Fetch Request.credentials](https://developer.mozilla.org/en-US/docs/Web/API/Request/credentials): include, omit, same-origin.
- [OWASP — CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): synchronizer token, double-submit, SameSite, Origin validation.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): cookie flags, session fixation, logout.

**Kết luận:** CORS quyết định **browser có thể tương tác cross-origin và đọc response theo chính sách nào**; session cookie và Bearer header quyết định **bằng chứng xác thực được gửi như thế nào**; CSRF quyết định **request dùng credential tự động của browser có được phép tạo tác dụng phụ hay không**. Trong Spring Security Reactive, xử lý CORS trước authentication, allowlist origin/headers cụ thể, giữ CSRF khi dùng cookie session và chỉ tắt CSRF trong chain Bearer header-only đã được tách ranh giới rõ. Cuối cùng, vẫn phải kiểm tra token, scope và quyền đối tượng — CORS không phải authorization.