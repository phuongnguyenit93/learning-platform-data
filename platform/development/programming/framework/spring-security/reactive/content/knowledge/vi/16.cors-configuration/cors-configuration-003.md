# Thứ tự xử lý CORS trước các bước xác thực và phân quyền trong Spring Security WebFlux

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao browser gửi **CORS preflight** bằng HTTP `OPTIONS` **trước actual request**, và tại sao preflight không mang session cookie hay `Authorization` của actual request.
2. Phân biệt **CORS**, **authentication**, **authorization** và **CSRF**: đây là các cơ chế khác nhau, không thay thế cho nhau.
3. Mô tả thứ tự đúng trong Spring Security WebFlux: CORS được xét sớm, preflight hợp lệ kết thúc ở bước CORS, còn actual request tiếp tục đi qua xác thực/phân quyền.
4. Sử dụng `ServerHttpSecurity.cors(...)` cùng `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource`, cấu hình origin/method/header/credentials một cách tối thiểu.
5. Phân biệt cách dùng `CorsWebFilter`, `CorsConfigurationSource`, `WebFluxConfigurer.addCorsMappings(...)` và `@CrossOrigin`, tránh đăng ký CORS hai lần hoặc đặt filter sai thứ tự.
6. Xây dựng ứng dụng Java 17+ / Spring Boot 3.x và kiểm thử bằng `WebTestClient`: OPTIONS không cần login, actual GET chưa login nhận 401, có login nhưng thiếu role nhận 403, origin không được phép nhận CORS reject.
7. Phân tích các vấn đề multi-chain, gateway/proxy, `Access-Control-Allow-Credentials`, `Vary`, cookie SameSite, lỗi CORS bị hiểu nhầm là lỗi quyền và kiểm soát CSRF với unsafe methods.

> Phạm vi: **Spring Security reactive/WebFlux**, Spring Security 6.5.x và Spring Framework 6.2.x trên Spring Boot 3.5.x, Java 17+. Các tên `CorsFilter` (Servlet), `HttpSecurity`, `SecurityFilterChain` và `HttpServletRequest` thuộc ngăn xếp MVC/Servlet, không sử dụng cho ví dụ WebFlux này. Trong WebFlux cần `CorsWebFilter`, `ServerHttpSecurity`, `SecurityWebFilterChain` và `ServerWebExchange`.

## 1. CORS được xử lý trước authentication nghĩa là gì?

Giả sử giao diện ở `http://localhost:3000` cần gọi API bảo vệ tại `http://localhost:8080/api/private`. Hai địa chỉ này khác **origin** vì khác cổng, dù đều là `localhost`.

Một lời gọi JavaScript dùng header `Authorization` (không phải header safelisted) sẽ thường làm browser gửi hai HTTP request:

1. **Preflight**: `OPTIONS /api/private` có `Origin`, `Access-Control-Request-Method: GET` và `Access-Control-Request-Headers: authorization`. Browser hỏi server: "Origin này có thể dùng method/header đó không?"
2. **Actual request**: chỉ khi preflight được chấp thuận, browser mới thực hiện `GET /api/private` với credential thích hợp, rồi xử lý CORS response của actual request.

**Preflight không phải một yêu cầu đăng nhập của user.** Theo cơ chế CORS, request preflight không được gửi credentials như cookies hoặc HTTP authentication. Nếu Spring Security áp yêu cầu `authenticated()` lên preflight **trước khi CORS có cơ hội nhận diện**, server có thể trả 401 hoặc redirect login; browser coi việc kiểm tra CORS không thành công và **không gửi actual GET**.

Vì vậy:

- **CORS trước authentication**: cho phép preflight hợp lệ được đánh giá theo origin/method/header mà không cần user login.
- **Authentication sau CORS**: chỉ actual request mới kiểm chứng cookie, HTTP Basic, Bearer token hoặc cơ chế xác thực khác.
- **Authorization sau authentication**: actual request phải đủ quyền cho tài nguyên.
- **CSRF**: vẫn phải bảo vệ những unsafe requests có browser tự gửi credentials, bất kể CORS đã cho phép origin hay chưa.

Quan trọng: CORS được xử lý trước **không có nghĩa mọi request OPTIONS được phép hoặc endpoint được mở public**. Preflight có `Origin` và `Access-Control-Request-Method` được kiểm tra bằng chính sách CORS; OPTIONS thông thường không có các dấu hiệu đó không tự được quyền đi qua authorization.

### Bảng phân biệt

| Bước | Mục đích | Dựa vào thông tin nào? | Có chứng minh user được quyền không? |
| --- | --- | --- | --- |
| CORS | Browser có được phép gọi/đọc response cross-origin theo policy? | Origin, request method, request headers, credentialed mode | **Không** |
| Authentication | Ai đang gọi API? | Session, Basic, Bearer, mTLS hoặc identity source | Chỉ xác lập danh tính |
| Authorization | Người đó được thực hiện gì? | Role, permission, owner, tenant, resource state | **Có**, theo rule |
| CSRF | Request thay đổi trạng thái có token/nguồn hợp lệ không? | CSRF token/repository và cơ chế chống giả mạo | Không thay thế authorization |

## 2. Preflight là một request độc lập, không phải actual OPTIONS "đăng nhập"

Một preflight hợp lệ có hình dạng ví dụ:

```http
OPTIONS /api/private HTTP/1.1
Host: localhost:8080
Origin: http://localhost:3000
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

Không có cookie phiên và cũng không có `Authorization: Basic ...` trong request này. Browser không thử login bằng preflight. Nếu chính sách cho phép, server có thể phản hồi:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:3000
Access-Control-Allow-Methods: GET
Access-Control-Allow-Headers: authorization
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 1800
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
```

Đây là **ví dụ response headers**, cách viết hoa, thứ tự header, mã 200/204 và cách gộp nhiều giá trị `Vary` tùy implementation. Browser kiểm tra **origin**, method và header đã hỏi; nếu response không hợp lệ, actual request bị chặn ở browser. Browser có thể cache kết quả preflight một thời gian theo policy, nhưng `maxAge=1800` không bắt buộc mọi browser cache đủ 1800 giây.

Actual request khác:

```http
GET /api/private HTTP/1.1
Host: localhost:8080
Origin: http://localhost:3000
Authorization: Basic ...
```

Actual request này vẫn phải trải qua Spring Security authentication và authorization. Nếu thiếu credential, ví dụ HTTP Basic thường trả `401 Unauthorized`; nếu đã authenticated nhưng thiếu role, thường là `403 Forbidden`. Nếu được phép, response chứa data cùng CORS headers hợp lệ để browser cho frontend đọc.

**CORS preflight pass không cấp một "vé thông hành" bỏ qua security cho actual request.** Nó chỉ xác nhận browser có thể tiến tới bước HTTP thực tiếp theo.

### Khi nào browser tạo preflight?

Browser thường preflight khi cross-origin request dùng method/header/content type không nằm trong các loại CORS-safelisted. Ví dụ: `Authorization`, `X-Request-ID`, `Content-Type: application/json` hoặc method `PUT`. Một cross-origin GET đơn giản không có custom header thường **không** preflight; browser gửi actual GET trực tiếp, nhưng CORS vẫn phải được kiểm tra trên response của actual GET.

Preflight thường có request method thực tế nằm trong `Access-Control-Request-Method`, chứ không phải chỉ hỏi server có cho phép `OPTIONS` hay không. Trong ví dụ trên, method cần được cho phép là **GET**.

## 3. Sơ đồ thứ tự xử lý đúng và sai

### Đúng: CORS filter ở trước security authentication

```text
Frontend http://localhost:3000
          |
          | OPTIONS /api/private
          | Origin: http://localhost:3000
          | Access-Control-Request-Method: GET
          v
Spring WebFlux filter chain
          |
          +--> CORS processing (CorsWebFilter / CorsSpec)
          |        |
          |        +--> Origin/method/header hợp lệ?
          |        |      |
          |        |      +--> Có -> preflight response (200/204)
          |        |      +--> Không -> reject CORS (thường 403)
          |        |
          |        +--> Không cần user identity cho preflight
          |
          +--> Không vào AuthenticationWebFilter / AuthorizationWebFilter
               nếu preflight đã được xử lý và kết thúc ở CORS

Browser nhận preflight thành công
          |
          | GET /api/private + credential thực (nếu có)
          v
CORS kiểm tra origin trên actual request
          |
          +--> HTTP Basic/session/JWT authentication
          |
          +--> Authorization (authenticated/role/ACL)
          |
          +--> Controller/HandlerFunction
          |
          +--> Response + Access-Control-Allow-Origin cho browser
```

### Sai: security chặn preflight trước CORS

```text
OPTIONS /api/private không cookie / Authorization
          |
          v
Authentication / authorization chạy trước CORS
          |
          +--> Không có principal -> 401 hoặc redirect login
          |
          v
Browser: CORS preflight thất bại
          |
          +--> Actual GET không được gửi
          +--> DevTools có thể báo "CORS error"
```

Điều nguy hiểm về mặt vận hành: backend có thể trả 401, nhưng frontend JavaScript chỉ thấy một thông báo CORS không chi tiết và cho rằng API "không cho phép origin". Cần kiểm tra **Network tab** riêng request OPTIONS và actual request, không chỉ nhìn exception của `fetch()`.

### Vậy `OPTIONS /** permitAll()` có giải quyết không?

Cấu hình sau là cách chữa cháy không hoàn chỉnh:

```java
// Anti-pattern nếu dùng như giải pháp CORS duy nhất.
.authorizeExchange(exchanges -> exchanges
        .pathMatchers(HttpMethod.OPTIONS, "/**").permitAll()
        .anyExchange().authenticated())
```

Cho phép OPTIONS tại authorization **không tự sinh** các header `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`. Nếu CORS không được xử lý đúng, browser vẫn bác preflight. Nó còn cho phép cả những OPTIONS không phải CORS preflight, trong khi mục tiêu thực sự là chỉ xử lý yêu cầu CORS phù hợp origin/method/header policy.

Chính sách đúng: **gắn CORS configuration source vào tầng CORS đặt sớm**, giữ authorization chặt chẽ cho actual request.

## 4. Thứ tự trong SecurityWebFilterChain của WebFlux

Trong Spring Security 6.5, `SecurityWebFiltersOrder` có các mốc theo thứ tự tương đối:

```text
... HTTP_HEADERS_WRITER
... HTTPS_REDIRECT
    CORS
    CSRF
    REACTOR_CONTEXT
    HTTP_BASIC / FORM_LOGIN / AUTHENTICATION
    ...
    ANONYMOUS_AUTHENTICATION
    ...
    EXCEPTION_TRANSLATION
    AUTHORIZATION
```

Danh sách này **chỉ mô tả tương quan các stage chính**, không phải bản sao đầy đủ của enum hoặc thứ tự bắt buộc từng filter trong mọi cấu hình. Một filter có thể không có mặt nếu cơ chế tương ứng bị tắt; ứng dụng có thể chèn filter khác ở vị trí có chủ đích.

`ServerHttpSecurity.CorsSpec` của Spring Security WebFlux đảm bảo `CorsWebFilter` được đặt ở đúng vị trí CORS trong security chain. Trong phiên bản 6.5, API:

```java
// Đoạn cấu hình bên trong bean SecurityWebFilterChain:
http.cors(cors -> cors.configurationSource(corsConfigurationSource));
```

sẽ sử dụng `org.springframework.web.cors.reactive.CorsConfigurationSource` đã cung cấp. Nếu bạn cấu hình `.cors(Customizer.withDefaults())`, Spring Security có thể tìm bean `CorsConfigurationSource` để tích hợp; **không có source nào phù hợp thì không nên kỳ vọng CORS headers được tự sinh**.

Lưu ý: `.cors(cors -> cors.disable())` nghĩa là vô hiệu hóa **CORS integration trong Spring Security**, không có nghĩa browser tắt same-origin policy. Khi disable nhầm, frontend cross-origin vẫn có thể gặp lỗi CORS; đừng dùng disable làm cách sửa lỗi.

## 5. Những API CORS thường bị nhầm giữa WebFlux và Servlet

| Vai trò | **WebFlux reactive** | **Servlet/MVC — không dùng trong bài** |
| --- | --- | --- |
| Security DSL | `ServerHttpSecurity` | `HttpSecurity` |
| Filter chain | `SecurityWebFilterChain` | `SecurityFilterChain` |
| CORS filter | `org.springframework.web.cors.reactive.CorsWebFilter` | `org.springframework.web.filter.CorsFilter` |
| Source interface | `org.springframework.web.cors.reactive.CorsConfigurationSource` | `org.springframework.web.cors.CorsConfigurationSource` |
| URL mapping source | `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource` | `org.springframework.web.cors.UrlBasedCorsConfigurationSource` |
| Exchange/request | `ServerWebExchange` | `HttpServletRequest` |
| Controller mapping | WebFlux HandlerMapping | MVC HandlerMapping |
| Authentication | Reactive security WebFilters | Servlet filters |

Tên class `CorsConfiguration` (không có chữ reactive) lại là **dùng chung**: `org.springframework.web.cors.CorsConfiguration`. Vì vậy import đúng source/filter rất quan trọng khi IDE tự gợi ý.

### Ba cách cấu hình CORS trong WebFlux

**Cách A — Ưu tiên trong bài này:** cung cấp `UrlBasedCorsConfigurationSource` và đặt trực tiếp qua `ServerHttpSecurity.cors(cors -> cors.configurationSource(source))`. Ưu điểm: security configuration thể hiện rõ CORS source được dùng và vị trí do Security quản lý.

**Cách B — Bean `CorsWebFilter` độc lập:** Spring WebFlux có thể dùng `CorsWebFilter` bean được đặt trước security WebFilter bằng `@Order` phù hợp. Phù hợp khi dùng functional endpoints hoặc muốn CORS cho nhiều route ngoài security chain. Nếu chọn cách này, **không vô ý cài thêm CORS handling thứ hai trong Security** với policy khác.

**Cách C — `WebFluxConfigurer.addCorsMappings(...)` / `@CrossOrigin`:** đây là cơ chế CORS ở `HandlerMapping`, hữu ích để mô tả URL/handler nhưng có thể nằm **sau** security WebFilters. Nếu security từ chối preflight ở trước, annotation trên controller chưa có cơ hội chạy. Phải xác minh CORS integration trước security khi endpoint được bảo vệ.

Mỗi cách có giá trị; cần chọn một nơi cấu hình policy chủ đạo và test đường đi thực. Đừng sao chép hướng dẫn Servlet `CorsFilter` hoặc `FilterRegistrationBean` rồi kỳ vọng hoạt động trong WebFlux.

## 6. Ví dụ Java 17+ chạy được: CORS trước HTTP Basic và authorization

Ví dụ sẽ có:

- Frontend dev origin được cho phép: **`http://localhost:3000`**.
- API: **`http://localhost:8080`**, dùng Spring WebFlux.
- Authentication: HTTP Basic để test rõ ràng; chỉ sử dụng tài khoản demo trên máy local. Khi deploy thật, phải dùng HTTPS và identity provider phù hợp.
- Endpoint `GET /api/public` không cần đăng nhập, `GET /api/private` cần authenticated, `GET /api/admin` cần role ADMIN.
- CORS được cấu hình cho `/api/**`; chỉ nhận origin dev đã chỉ định, chỉ method GET và header Authorization, Content-Type.
- `Access-Control-Allow-Credentials: true` để minh họa credentialed browser requests; trong production chỉ bật khi thực sự cần cookies/HTTP authentication và phải sử dụng allowlist origin cụ thể.

### 6.1. Cấu trúc project

```text
cors-order-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/example/corsorder/
        CorsOrderApplication.java
        SecurityConfiguration.java
        ApiController.java
      resources/
        application.yml
    test/
      java/example/corsorder/
        CorsOrderIntegrationTest.java
```

Không thêm `spring-boot-starter-web`; nếu Spring MVC và WebFlux cùng có trên classpath, Spring Boot thường ưu tiên ứng dụng Servlet.

### 6.2. Gradle đầy đủ

**`settings.gradle`**:

```groovy
rootProject.name = 'cors-order-demo'
```

**`build.gradle`**:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Hai version plugin trên là các bản đã được phát hành; chúng tạo ví dụ có baseline Spring Boot 3.5 / Spring Security 6.5. Để chạy, bạn cần Gradle Wrapper tương thích (hoặc Gradle đã cài). Trong dự án thực nên dùng phiên bản patch được hỗ trợ và cập nhật security fixes; không pin bản cũ nếu chính sách vận hành yêu cầu nâng cấp.

**`src/main/resources/application.yml`**:

```yaml
server:
  port: 8080

spring:
  application:
    name: cors-order-demo
```

### 6.3. Main class

**`src/main/java/example/corsorder/CorsOrderApplication.java`**:

```java
package example.corsorder;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsOrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsOrderApplication.class, args);
    }
}
```

### 6.4. Cấu hình CORS và Spring Security WebFlux

**`src/main/java/example/corsorder/SecurityConfiguration.java`**:

```java
package example.corsorder;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
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
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();

        config.setAllowedOrigins(List.of("http://localhost:3000"));
        config.setAllowedMethods(List.of("GET"));
        config.setAllowedHeaders(List.of(
                "Authorization", "Content-Type"));
        config.setAllowCredentials(true);
        config.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("local-test-password"))
                .roles("READER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("local-test-password"))
                .roles("ADMIN")
                .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            UrlBasedCorsConfigurationSource corsConfigurationSource) {
        return http
                .cors(cors -> cors.configurationSource(
                        corsConfigurationSource))
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/api/public")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/admin")
                            .hasRole("ADMIN")
                        .pathMatchers(HttpMethod.GET, "/api/private")
                            .authenticated()
                        .anyExchange().denyAll()
                )
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
```

**Vì sao đoạn này đúng thứ tự?**

1. `UrlBasedCorsConfigurationSource` thuộc package `org.springframework.web.cors.reactive`. Một URL `/api/private` sẽ khớp pattern `/api/**`.
2. `config.setAllowedOrigins(...)` so khớp **origin chính xác** gồm scheme/host/port. `http://localhost:3000` khác `http://127.0.0.1:3000` và khác `https://localhost:3000`.
3. `setAllowedMethods(List.of("GET"))` cho phép **actual method GET**. Browser preflight dùng HTTP OPTIONS nhưng header `Access-Control-Request-Method: GET`, vì thế không cần thêm OPTIONS vào allowed methods chỉ để preflight GET hợp lệ.
4. `setAllowedHeaders(List.of("Authorization","Content-Type"))` chấp nhận những header mà browser yêu cầu cho actual call. Nếu frontend muốn dùng `X-Correlation-ID`, phải đưa nó vào allowlist theo nhu cầu.
5. `setAllowCredentials(true)` chỉ bật credentialed CORS cho origin đã whitelist; tuyệt đối không kết hợp `allowCredentials(true)` với `allowedOrigins("*")`.
6. `setMaxAge(1800L)` cho phép browser cache kết quả preflight tối đa theo policy; không phải thời hạn session hay access token.
7. `http.cors(cors -> cors.configurationSource(...))` tích hợp CORS trong security chain **ở vị trí trước** CSRF/authentication/authorization. Thứ tự dòng gọi DSL không phải thứ tự chạy WebFilter; framework xác định order từ `SecurityWebFiltersOrder`.
8. `anyExchange().denyAll()` vẫn là default; preflight hợp lệ được filter CORS xử lý trước, actual request chưa xác thực vẫn bị từ chối.
9. `httpBasic(...)` cho demo quan sát header Authorization; `formLogin(...)` tắt để client API không bị redirect HTML login. CSRF vẫn giữ mặc định; demo chỉ cho GET nên không gặp yêu cầu CSRF token ở endpoint nghiệp vụ.
10. `PasswordEncoder` băm password cho người dùng demo. Không dùng `{noop}` hoặc tài khoản local hardcode trong môi trường production.

**Quan trọng:** bean source không phải một `CorsWebFilter` độc lập. Trong ví dụ này ta để **Spring Security tạo/integrate CorsWebFilter**, tránh bị xử lý trùng ở hai nơi. Đây là cấu hình của **một** `SecurityWebFilterChain` cho mọi request.

### 6.5. Controller để quan sát preflight không được đi vào business code

**`src/main/java/example/corsorder/ApiController.java`**:

```java
package example.corsorder;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    private final AtomicInteger privateReads = new AtomicInteger();

    @GetMapping("/api/public")
    public Mono<String> publicInfo() {
        return Mono.just("public");
    }

    @GetMapping("/api/private")
    public Mono<String> privateInfo() {
        return Mono.fromSupplier(() -> {
            privateReads.incrementAndGet();
            return "private-data";
        });
    }

    @GetMapping("/api/admin")
    public Mono<String> adminInfo() {
        return Mono.just("admin-data");
    }

    // Chỉ dùng từ test trong cùng package, không phải endpoint public.
    int privateVisits() {
        return privateReads.get();
    }

    void resetForTests() {
        privateReads.set(0);
    }
}
```

Vì filter CORS hoàn tất preflight trước khi gọi controller, một preflight hợp lệ tới `/api/private` **không làm tăng counter**. Chỉ actual GET đã được authenticated mới thực thi handler và tăng counter. `AtomicInteger` ở đây chỉ là công cụ test, không phải state người dùng thực.

### 6.6. Khởi động

Tại thư mục dự án có Gradle Wrapper:

```bash
./gradlew bootRun
```

PowerShell trên Windows:

```powershell
.\gradlew.bat bootRun
```

Hoặc dùng Gradle đã cài tương thích:

```bash
gradle bootRun
```

Giả định API chạy tại `http://localhost:8080`. Dùng HTTP trên localhost để học; **production phải sử dụng HTTPS** khi có Basic auth, session cookie hoặc Bearer token.

## 7. Thử preflight bằng curl: có CORS nhưng không có identity

**Preflight đúng origin, GET, Authorization header:**

```bash
curl -i -X OPTIONS "http://localhost:8080/api/private" \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization"
```

Kỳ vọng: HTTP thành công (trong demo thường **200**), có `Access-Control-Allow-Origin: http://localhost:3000`, `Access-Control-Allow-Methods: GET`, `Access-Control-Allow-Headers: authorization` và `Access-Control-Allow-Credentials: true`. **Không cần `-u reader:...` hay cookie** trong preflight. Curl không tự thực thi CORS và không mô phỏng toàn bộ browser; ta dùng nó để quan sát response.

**Origin không nằm trong allowlist:**

```bash
curl -i -X OPTIONS "http://localhost:8080/api/private" \
  -H "Origin: https://untrusted.example.invalid" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization"
```

Kỳ vọng: thường **403** từ CORS processor, không có `Access-Control-Allow-Origin` hợp lệ cho origin đó. Nếu request không có header `Origin` và `Access-Control-Request-Method`, đó **không** còn là preflight; response có thể đến từ đường security/handler khác.

**Method không được phép:**

```bash
curl -i -X OPTIONS "http://localhost:8080/api/private" \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: DELETE"
```

Kỳ vọng: CORS từ chối vì policy chỉ cho actual method GET. Chỉ thêm `OPTIONS` vào `allowedMethods` không làm cho DELETE hợp lệ.

**Header không được phép:**

```bash
curl -i -X OPTIONS "http://localhost:8080/api/private" \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: x-unlisted-header"
```

Kỳ vọng: CORS từ chối vì `X-Unlisted-Header` không nằm trong `allowedHeaders`. Không giải quyết bằng `allowedHeaders("*")` cho mọi origin nếu app không có yêu cầu thực tế.

### Windows PowerShell lưu ý

Trên Windows PowerShell 5.1, `curl` có thể là alias của `Invoke-WebRequest`. Khi muốn dùng cú pháp cURL như trên, gọi **`curl.exe`** và dùng một dòng/PowerShell backtick ở vị trí phù hợp; ký tự `\` nối dòng là cú pháp shell Unix, không phải PowerShell. Ví dụ:

```powershell
curl.exe -i -X OPTIONS "http://localhost:8080/api/private" -H "Origin: http://localhost:3000" -H "Access-Control-Request-Method: GET" -H "Access-Control-Request-Headers: authorization"
```

## 8. Actual request: CORS pass vẫn cần authentication/authorization

Gọi endpoint với origin được phép nhưng **không có credential**:

```bash
curl -i "http://localhost:8080/api/private" \
  -H "Origin: http://localhost:3000"
```

Kỳ vọng: **401 Unauthorized** theo HTTP Basic, thường có `WWW-Authenticate` và vẫn có `Access-Control-Allow-Origin: http://localhost:3000` vì CORS xử lý actual request sớm. Điều này tốt: browser có thể phân biệt lỗi đăng nhập (401) với lỗi CORS về origin.

Gọi bằng user hợp lệ:

```bash
curl -i -u reader:local-test-password \
  "http://localhost:8080/api/private" \
  -H "Origin: http://localhost:3000"
```

Kỳ vọng: **200 OK**, body:

```text
private-data
```

Tài khoản reader vào trang admin:

```bash
curl -i -u reader:local-test-password \
  "http://localhost:8080/api/admin" \
  -H "Origin: http://localhost:3000"
```

Kỳ vọng: **403 Forbidden** vì đã authenticated nhưng thiếu `ROLE_ADMIN`, dù CORS của origin này hợp lệ.

Tài khoản admin:

```bash
curl -i -u admin:local-test-password \
  "http://localhost:8080/api/admin" \
  -H "Origin: http://localhost:3000"
```

Kỳ vọng: **200 OK**, body:

```text
admin-data
```

**Quan sát bảo mật:** CORS không quyết định ai là admin. Một script ở origin được phép không tự có quyền vào `/api/admin`; nó vẫn cần credential và authority hợp lệ. Ngược lại, cURL có thể truy cập API **không cần gửi Origin** nếu có credential đúng: CORS là policy browser, không phải một phương thức thay thế backend authentication/authorization.

### Tổng hợp trạng thái

| Request | CORS | Security/HTTP | HTTP status kỳ vọng |
| --- | --- | --- | --- |
| OPTIONS preflight allowed origin + GET + Authorization | Pass, kết thúc sớm | Chưa đòi login | 200 |
| OPTIONS preflight disallowed origin | Reject | Không cần authz | 403 |
| OPTIONS preflight requested DELETE | Reject | Không cần authz | 403 |
| GET /api/private, allowed origin, no credentials | Pass | HTTP Basic challenge | 401 |
| GET /api/private, allowed origin, reader | Pass | authenticated | 200 |
| GET /api/admin, allowed origin, reader | Pass | thiếu ADMIN | 403 |
| GET /api/admin, allowed origin, admin | Pass | có ADMIN | 200 |
| GET /api/private, không Origin, reader | Không phải CORS | authenticated | 200 |
| GET /api/private, disallowed Origin | CORS reject trước auth | Không đọc body | Thường 403 |

Ở actual request, browser cũng phải kiểm tra CORS response; chỉ nhìn thấy HTTP 200 trong cURL **không chứng minh** browser sẽ cho phép JavaScript của một origin không được whitelist đọc body.

## 9. Kiểm thử tự động bằng WebTestClient: không chỉ nhìn status

Mục tiêu: xác minh thứ tự thực tế bằng các request HTTP kiểm tra response headers, authn/authz và side effect của controller. Mã bên dưới dùng `WebTestClient.bindToApplicationContext(...).apply(springSecurity())` để chạy security WebFilters trong mock server.

**`src/test/java/example/corsorder/CorsOrderIntegrationTest.java`**:

```java
package example.corsorder;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class CorsOrderIntegrationTest {

    private static final String UI = "http://localhost:3000";

    @Autowired
    ApplicationContext context;

    @Autowired
    ApiController api;

    private WebTestClient client;

    @BeforeEach
    void prepare() {
        api.resetForTests();
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void validPreflightNeedsNoAuthenticationAndSkipsController() {
        client.options().uri("/api/private")
                .header("Origin", UI)
                .header("Access-Control-Request-Method", "GET")
                .header("Access-Control-Request-Headers", "authorization")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .valueEquals("Access-Control-Allow-Origin", UI)
                .expectHeader()
                    .valueEquals("Access-Control-Allow-Credentials", "true");

        assertEquals(0, api.privateVisits());
    }

    @Test
    void preflightFromUnknownOriginIsRejected() {
        client.options().uri("/api/private")
                .header("Origin", "https://untrusted.example.invalid")
                .header("Access-Control-Request-Method", "GET")
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().doesNotExist("Access-Control-Allow-Origin");

        assertEquals(0, api.privateVisits());
    }

    @Test
    void preflightWithUnapprovedMethodIsRejected() {
        client.options().uri("/api/private")
                .header("Origin", UI)
                .header("Access-Control-Request-Method", "DELETE")
                .exchange()
                .expectStatus().isForbidden();

        assertEquals(0, api.privateVisits());
    }

    @Test
    void preflightWithUnapprovedHeaderIsRejected() {
        client.options().uri("/api/private")
                .header("Origin", UI)
                .header("Access-Control-Request-Method", "GET")
                .header("Access-Control-Request-Headers", "x-unlisted")
                .exchange()
                .expectStatus().isForbidden();

        assertEquals(0, api.privateVisits());
    }

    @Test
    void actualRequestWithoutCredentialsStillNeedsLogin() {
        client.get().uri("/api/private")
                .header("Origin", UI)
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader()
                    .valueEquals("Access-Control-Allow-Origin", UI);

        assertEquals(0, api.privateVisits());
    }

    @Test
    void validReaderCanAccessPrivateApi() {
        client.get().uri("/api/private")
                .header("Origin", UI)
                .headers(h -> h.setBasicAuth(
                        "reader", "local-test-password"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .valueEquals("Access-Control-Allow-Origin", UI)
                .expectBody(String.class).isEqualTo("private-data");

        assertEquals(1, api.privateVisits());
    }

    @Test
    void readerCannotAccessAdminEvenFromAllowedOrigin() {
        client.get().uri("/api/admin")
                .header("Origin", UI)
                .headers(h -> h.setBasicAuth(
                        "reader", "local-test-password"))
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader()
                    .valueEquals("Access-Control-Allow-Origin", UI);
    }

    @Test
    void adminCanAccessAdmin() {
        client.get().uri("/api/admin")
                .header("Origin", UI)
                .headers(h -> h.setBasicAuth(
                        "admin", "local-test-password"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin-data");
    }

    @Test
    void requestWithoutOriginIsNotAWebCorsCheck() {
        client.get().uri("/api/private")
                .headers(h -> h.setBasicAuth(
                        "reader", "local-test-password"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("private-data");
    }

    @Test
    void publicEndpointDoesNotRequireAuthentication() {
        client.get().uri("/api/public")
                .header("Origin", UI)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .valueEquals("Access-Control-Allow-Origin", UI)
                .expectBody(String.class).isEqualTo("public");
    }
}
```

Lệnh chạy:

```bash
./gradlew test --tests example.corsorder.CorsOrderIntegrationTest
```

PowerShell:

```powershell
.\gradlew.bat test --tests example.corsorder.CorsOrderIntegrationTest
```

**Kết quả kỳ vọng:** 10 test PASS với các file và dependency đúng baseline. Đây là **kết quả dự kiến theo mã**, không phải log biên dịch/chạy test đã thực hiện trong một project thực tế. Mã test dùng cùng instance controller và reset counter tại `@BeforeEach`; nếu cấu hình test chạy song song, phải cô lập state hoặc loại bỏ bộ đếm dùng chung để tránh race giữa tests.

### Vì sao test này chứng minh đúng thứ tự?

- OPTIONS preflight **không mang Authentication**, vẫn thành công và có CORS response headers.
- Bộ đếm controller vẫn bằng 0: preflight kết thúc trong tầng CORS, không đi vào handler nghiệp vụ.
- Actual GET không có credential vẫn bị **401**, chứng minh preflight pass không bypass authentication.
- Actual GET từ origin được phép nhưng thiếu role vẫn **403**, chứng minh CORS pass không bypass authorization.
- Disallowed origin/method/header bị CORS từ chối.
- Không có header Origin vẫn có thể truy cập được với Basic đúng, cho thấy CORS không phải auth guard cho non-browser client.

Một test chỉ assert `OPTIONS=200` **chưa đủ**: có thể server bật `permitAll OPTIONS` nhưng không trả CORS headers, browser vẫn chặn actual request. Phải kiểm tra các `Access-Control-Allow-*` headers và actual security riêng.

## 10. Giao diện browser: credentials, cookie và Authorization

### 10.1. Origin khác vì port khác

Một frontend đang chạy ở `http://localhost:3000` gọi `http://localhost:8080` là **cross-origin**, dù cùng máy. Browser áp dụng CORS cho JavaScript. Trường hợp production thường là `https://ui.example.test` gọi `https://api.example.test`; hai origin khác nhau vì hostname khác nhau.

### 10.2. Fetch API không tự gửi mọi credential

`fetch()` mặc định dùng `credentials: "same-origin"`. Với cross-origin call, browser thông thường **không gửi cookie** trừ khi code đặt `credentials: "include"` và cookie policy cho phép. Với Basic authentication:

- Một header `Authorization` do frontend tự thêm thường kích hoạt preflight.
- Nếu browser đã cache Basic credentials, hành vi có thể phụ thuộc browser và vùng auth; không nên thiết kế production dựa trên demo Basic.
- Không đưa raw username/password cố định vào JavaScript frontend production; Basic phải dùng HTTPS và ưu tiên cơ chế auth phù hợp SPA/SSO.

Ví dụ minh họa client được cấp credential thông qua kiến trúc đã thiết kế (không có token thật trong bài):

```javascript
// Minh họa, authorizationHeader phải được cung cấp an toàn bởi ứng dụng.
// Không hardcode password/token trong mã frontend.
async function loadPrivate(authorizationHeader) {
  const response = await fetch("http://localhost:8080/api/private", {
    method: "GET",
    credentials: "include",
    headers: { Authorization: authorizationHeader }
  });

  if (response.status === 401) {
    throw new Error("Cần xác thực lại");
  }
  if (response.status === 403) {
    throw new Error("Không đủ quyền");
  }
  if (!response.ok) {
    throw new Error("Lỗi HTTP " + response.status);
  }
  return response.text();
}
```

Đây là **đoạn JS minh họa**, chưa có phần cấp `authorizationHeader` và chưa phải ứng dụng độc lập. Browser sẽ preflight do header Authorization và thực hiện GET sau khi được phép. Nếu server trả preflight 401, JavaScript thường nhận network/CORS failure, **không** đi vào nhánh `response.status === 401`, vì actual GET chưa được gửi.

### 10.3. SameSite có thể chặn cookie dù CORS cho phép

CORS allowlist và cookie policy là hai điều kiện độc lập:

- `Access-Control-Allow-Credentials: true` không ép browser gửi cookie.
- Cookie cần `Domain`, `Path`, `Secure`, `SameSite` phù hợp và không bị browser third-party cookie policy chặn.
- CORS so sánh **origin** (scheme + host + port). Cookie SameSite dựa trên **site**, không xét port như origin. Hai địa chỉ localhost khác cổng là cross-origin nhưng thường same-site.
- Ở sản phẩm cross-site khác registrable domain, cookie `SameSite=Lax`/`Strict` có thể không đi trên cross-site fetch, dù CORS preflight hoàn hảo.
- Khi cần cookies thực sự cross-site, `SameSite=None; Secure` và chính sách browser phù hợp thường cần thiết. Đây là quyết định security có thêm rủi ro CSRF và third-party cookie restrictions.

**Không kết luận "CORS đúng nên cookie phải có".** Network tab cho biết preflight, actual request và cookie gửi đi theo từng bước; không chia sẻ cookie/session ID thực.

## 11. CORS với cookie không thay thế CSRF

Một sai lầm nguy hiểm là coi origin allowlist đồng nghĩa request thay đổi trạng thái đã được phép.

CORS chủ yếu điều khiển quyền JavaScript của origin khác gửi/đọc request theo luật browser. Nhưng HTML form đơn giản có thể gửi cross-origin POST mà không cần đọc response. Nếu browser tự gắn cookie session, server vẫn cần bảo vệ **CSRF** cho POST/PUT/PATCH/DELETE theo thiết kế.

Trong Spring Security WebFlux, `CsrfWebFilter` được bật theo mặc định. Khi bổ sung endpoint ghi dữ liệu:

- Giữ CSRF nếu authentication dùng browser session/cookie hoặc cơ chế ambient credentials.
- Cấp token cho frontend qua một kênh cùng origin/được bảo vệ đúng.
- Gửi token trong field/header mà CSRF repository và request handler của backend hỗ trợ.
- Không dùng `.csrf(csrf -> csrf.disable())` chỉ vì preflight OPTIONS nhận 403: preflight được xử lý bằng **CORS order**, không bằng tắt bảo vệ state-changing requests.
- Một request có Origin được phép vẫn có thể bị **403 CSRF** nếu thiếu token; đó là vấn đề khác với CORS 403 hay authorization 403.

Bài demo trên **chỉ có GET** nên việc giữ mặc định CSRF không làm gián đoạn endpoint chính. Nếu mở POST, phải thiết kế test riêng: preflight thành công, actual POST có authentication và token hợp lệ mới được phép. Khi actual POST thiếu token, CORS pass nhưng CSRF deny.

### So sánh ba lỗi 403

| Nguyên nhân | Request nào bị chặn? | Cách xác minh |
| --- | --- | --- |
| CORS policy không cho origin/method/header | Preflight hoặc actual CORS request | OPTIONS status, `Access-Control-Allow-Origin`, CORS logs |
| CSRF token không hợp lệ | Unsafe actual request | CSRF logs, token/repository, giữ cookie phù hợp |
| Authorization thiếu role/permission | Actual request sau authentication | Principal, authority, matcher/ACL |

Một response `403` **không tự nói rõ** là CSRF, CORS hay thiếu quyền. Tránh trả chi tiết security nhạy cảm cho client; dùng correlation ID và structured logs an toàn để phân biệt nội bộ.

## 12. Khi nào dùng CorsWebFilter độc lập thay vì ServerHttpSecurity.cors?

Spring Framework cung cấp `org.springframework.web.cors.reactive.CorsWebFilter`, có thể đăng ký làm bean và sắp xếp order ở **WebFilter chain ngoài**.

Nếu chọn **cách thay thế**, ví dụ minh họa:

```java
// Fragment dùng như phương án THAY THẾ, không đặt song song với
// cùng một CORS policy đang được .cors(...) quản lý.
@Bean
@Order(Ordered.HIGHEST_PRECEDENCE)
CorsWebFilter corsWebFilter(UrlBasedCorsConfigurationSource source) {
    return new CorsWebFilter(source);
}
```

Các import cần có là `org.springframework.web.cors.reactive.CorsWebFilter`, `org.springframework.core.Ordered`, `org.springframework.core.annotation.Order`. Đây chỉ là **fragment** trong một `@Configuration`; ở project demo chính đã dùng CORS trong `ServerHttpSecurity`, vì vậy **không thêm bean này**.

Cần chú ý:

1. Filter độc lập phải có order **trước WebFilter proxy của Spring Security**, không chỉ trước controller.
2. Nếu cũng bật `.cors(...)` với source khác, có thể gặp response header trùng, chính sách mâu thuẫn và behavior khó giải thích.
3. Nếu có các functional routes hoặc API gateway, chọn vị trí sớm phù hợp toàn bộ routing, không chỉ một controller.
4. Dù filter được sắp đúng, **actual request** vẫn phải qua authentication và authorization.
5. Không dùng `FilterRegistrationBean` hoặc Servlet `CorsFilter` cho WebFlux thuần.

**Ưu tiên của bài:** CORS integration qua `ServerHttpSecurity.cors(cors -> cors.configurationSource(source))` vì Spring Security tự đặt `CorsWebFilter` ở đúng `SecurityWebFiltersOrder.CORS`, dễ test và tránh đoán thứ tự WebFilters thủ công.

## 13. @CrossOrigin và WebFluxConfigurer có thể chưa đủ khi security đến trước

Spring WebFlux có CORS support ở `HandlerMapping` và annotations:

```java
// Ví dụ chỉ minh họa phạm vi annotation, không thêm vào demo chính.
@CrossOrigin(origins = "http://localhost:3000")
@GetMapping("/api/report")
public Mono<String> report() {
    return Mono.just("report");
}
```

Nhưng `@CrossOrigin` thuộc CORS mapping ở controller/HandlerMapping. Nếu security WebFilter đã chặn OPTIONS do thiếu authentication **trước lúc xác định handler**, annotation này không cứu được preflight.

Tương tự:

```java
// Fragment dành cho Spring WebFluxConfigurer nếu chọn cách này.
@Override
public void addCorsMappings(CorsRegistry registry) {
    registry.addMapping("/api/**")
            .allowedOrigins("http://localhost:3000")
            .allowedMethods("GET")
            .allowedHeaders("Authorization", "Content-Type")
            .allowCredentials(true);
}
```

Đây là config của **WebFlux layer**, không phải bằng chứng preflight được security cho qua. Nếu sử dụng kết hợp, phải đảm bảo Spring Security có CORS integration đúng và policy không xung đột. Khi ứng dụng chỉ có một policy API, **tránh trộn ba chỗ cấu hình một cách vô tội vạ**.

### Đặc biệt: OPTIONS không khớp controller GET matcher

Một preflight `OPTIONS /api/private` hỏi ý định GET. CORS filter theo URL pattern `/api/**` có thể xử lý nó dù controller chỉ định `@GetMapping`. Nếu bạn giới hạn security chain bằng một matcher **có method GET**, preflight method OPTIONS có thể không khớp chain đó và rơi vào chain khác. Đây là một nguyên nhân khó phát hiện ở ứng dụng có nhiều `SecurityWebFilterChain`.

## 14. Nhiều SecurityWebFilterChain, API Gateway và reverse proxy

### 14.1. Nhiều chain theo đường dẫn

Khi tách API và web UI:

```text
SecurityWebFilterChain @Order(1): /api/**
  - CorsSpec: API CORS policy
  - HTTP Basic / Bearer authentication
  - API authorization

SecurityWebFilterChain @Order(2): catch-all
  - Browser form login hoặc public/static
  - Web UI policy
```

Điểm dễ lỗi là chain matcher thứ nhất chỉ nhận `GET /api/**`, làm preflight OPTIONS rơi vào chain catch-all vốn yêu cầu login. Hãy match API chain **bằng path**, không giới hạn chỉ method GET, rồi xác định allowed methods trong **CorsConfiguration**. Nếu cần nhiều chain với cấu hình CORS khác nhau, phải xác nhận OPTIONS được xử lý ở chain nào. Một independent CORS filter trước security cũng có thể là chiến lược hợp lệ khi phải chia sẻ policy chung.

**Không** viết hai chain cùng catch-all rồi hy vọng request sẽ đi qua cả hai; Spring Security chọn chain phù hợp đầu tiên theo matcher/order.

### 14.2. Reverse proxy xử lý OPTIONS

Một Nginx/gateway/CDN có thể trả response preflight trước ứng dụng, hoặc chặn OPTIONS trước khi request tới Spring. Nếu chọn để proxy xử lý CORS:

- Dùng **một nguồn policy thống nhất** giữa gateway và backend.
- Không phản chiếu Origin tùy ý cùng `Access-Control-Allow-Credentials: true`.
- Cho phép đúng path/method/header; bảo vệ response cache theo `Vary`.
- Đảm bảo proxy không tự loại bỏ `Access-Control-Allow-*` headers khỏi response 401/403/500 do backend gửi.
- Không cho proxy "OPTIONS=200" bừa bãi khi backend không cho phép method/header thực.
- Xác định trusted proxy/forwarded headers, đặc biệt scheme/host/port vì origin khác nhau theo scheme.

Nếu request chưa vào app, chỉnh `SecurityWebFilterChain` cũng không cứu được preflight. Dùng log gateway, access logs và tracing để xác định thành phần nào trả response.

### 14.3. Spring Cloud Gateway và route predicate

Một route gateway chỉ match HTTP method GET có thể **không match preflight OPTIONS**. Một số phiên bản Spring Cloud Gateway WebFlux cung cấp tùy chọn global CORS cho simple URL handler mapping như `add-to-simple-url-handler-mapping`; kiểm tra đúng namespace property theo phiên bản gateway. Không copy configuration YAML từ release khác mà chưa đối chiếu. CORS route metadata cũng phải có path/method hợp lý để preflight không rơi vào 404/401.

## 15. Chính sách CORS an toàn: không mở hơn nhu cầu

| Thuộc tính | Ý nghĩa | Nguyên tắc |
| --- | --- | --- |
| `allowedOrigins` | Origin được phép | Danh sách cụ thể, gồm scheme/host/port |
| `allowedOriginPatterns` | Match origin theo mẫu | Chỉ dùng khi cần, review wildcard kỹ |
| `allowedMethods` | Actual HTTP methods được phép | Chỉ GET/POST/PUT/... thực sự cần |
| `allowedHeaders` | Headers JS được phép gửi | Authorization/Content-Type và custom headers cần thiết |
| `exposedHeaders` | Response headers JS được phép đọc thêm | Chỉ những header nghiệp vụ cần |
| `allowCredentials` | Browser có thể đưa credential và đọc response credentialed | Chỉ bật với origin tin cậy, không wildcard `*` |
| `maxAge` | Thời gian browser cache preflight | Không liên quan thời hạn token/session |
| `Vary` | Cách response cache phân biệt Origin/method/headers | Cần đúng khi CDN/proxy cache |

### Wildcard và credentialed requests

Theo Spring Framework, không dùng `allowedOrigins("*")` khi `allowCredentials(true)`. Nếu được cấu hình sai, framework có thể từ chối cấu hình/request do không thể xác định giá trị `Access-Control-Allow-Origin` phù hợp cho credentialed response.

Nếu thật sự cần nhiều subdomain, dùng danh sách origin xác định hoặc `allowedOriginPatterns` với phạm vi rất hẹp. Không phản chiếu mọi giá trị `Origin` do client cung cấp rồi trả `Access-Control-Allow-Credentials: true` — đó có thể cho một website không tin cậy đọc response dưới danh tính của user.

### Origin khác domain-name "giống nhau"

- `http://localhost:3000` khác `http://localhost:8080`.
- `https://ui.example.test` khác `http://ui.example.test`.
- `https://ui.example.test` khác `https://api.example.test`.
- Browser thường không gửi header Origin cho request cùng origin GET thông thường; thiếu Origin **không đồng nghĩa** request độc hại, và server không nên dùng CORS để xác thực non-browser clients.

**CORS không phải access-control list của backend.** CORS được áp dụng chủ yếu bởi browser; kẻ gọi bằng cURL/máy chủ khác có thể bỏ header Origin. Bất cứ API nhạy cảm nào cũng phải có authentication và authorization thực sự.

## 16. Bảng gỡ lỗi theo triệu chứng

| Hiện tượng | Chẩn đoán khả dĩ | Cách khắc phục |
| --- | --- | --- |
| Preflight OPTIONS 401 | Security yêu cầu login trước CORS hoặc gateway chặn | Đặt CORS trước authentication; xác minh chain/proxy |
| Preflight OPTIONS 302 tới /login | Form login entry point bắt OPTIONS | Tích hợp `CorsWebFilter` sớm, không redirect preflight |
| OPTIONS 200 nhưng browser vẫn báo CORS | Thiếu/sai ACA-Origin, Methods hoặc Headers | Kiểm tra response headers, origin/method/header thực |
| OPTIONS 403 | Origin, requested method hoặc requested header bị CORS deny | So khớp allowlist; đừng tắt authentication |
| OPTIONS 404 | Route/gateway/HandlerMapping không khớp OPTIONS | Tạo CORS handling sớm, xem route predicate |
| OPTIONS 405 | Controller/gateway xử lý OPTIONS thay vì CORS preflight | Xác minh filter và requested method |
| OPTIONS hợp lệ nhưng actual GET 401 | Thiếu/expired credential hoặc auth scheme sai | Sửa auth, không nới CORS |
| OPTIONS hợp lệ nhưng actual GET 403 | Thiếu role hoặc policy authorization | Kiểm tra authorities, rule và principal |
| Actual POST 403 sau preflight pass | Có thể là CSRF, authorization hoặc nghiệp vụ | Phân biệt CSRF token và role, xem logs |
| CORS được phép nhưng không gửi cookie | Fetch credentials mode, cookie SameSite/Path/Domain/Secure | Kiểm tra Network/Application cookies |
| Header Authorization bị preflight reject | Chưa có trong `allowedHeaders` | Thêm header cụ thể, đúng scope |
| Sửa `@CrossOrigin` nhưng OPTIONS vẫn 401 | Security chặn trước HandlerMapping | Dùng `ServerHttpSecurity.cors(...)` hoặc early CorsWebFilter |
| CORS config trên MVC `CorsFilter` trong app WebFlux | Wrong stack/bean không được dùng | Import `org.springframework.web.cors.reactive` |
| Hai CorsWebFilter/bean CORS trùng policy | Header trùng, behavior khó đoán | Chọn một tích hợp rõ ràng |
| 401/403 không có ACAO | CORS quá trễ hoặc proxy xóa headers | Đảm bảo CORS trước auth, kiểm tra gateway |
| `allowCredentials=true` + wildcard `*` | Chính sách không hợp lệ/không an toàn | Whitelist origin cụ thể |
| Chỉ whitelist `https://...` nhưng local dùng `http://...` | Origin lệch scheme | Điều chỉnh dev origin chính xác, production HTTPS |
| Test chỉ assert HTTP 200 | Không kiểm tra browser policy thực | Assert các ACA headers và actual auth |
| CORS pass nhưng bị lộ dữ liệu qua API client | Authz thiếu ở backend | Bổ sung role/ACL/tenant validation |
| Preflight cache che thay đổi config | Browser tái dùng preflight cache | Test với browser profile/URL mới, maxAge hợp lý |
| Cache/CDN trả ACAO nhầm origin | Thiếu Vary hoặc cache key sai | Đảm bảo `Vary: Origin` và kiểm tra CDN |

### Thứ tự điều tra đề xuất

1. Mở DevTools → **Network**, lọc `OPTIONS` và URL API; xác minh có preflight hay không.
2. Kiểm tra preflight **Request Headers**: `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers`.
3. Kiểm tra preflight **Status, Response Headers**: ACA-Origin, ACA-Methods, ACA-Headers, ACA-Credentials, Vary.
4. Nếu preflight pass, tìm **actual GET/POST** và kiểm tra credential có được gửi hay không, actual status và CORS headers.
5. Kiểm tra application logs có CORS reject, authentication challenge, access denied hay CSRF reject — không log password/token/cookie.
6. Xác định request đang bị chặn ở browser, gateway, Spring CorsWebFilter, Security WebFilter hay controller.
7. Chỉ sau khi biết tầng lỗi mới sửa cấu hình; không tắt toàn bộ security hoặc mở wildcard để "cho request chạy".

## 17. Checklist review trước production

1. CORS được xử lý **trước authentication và authorization** cho request preflight của các API cần cross-origin.
2. `OPTIONS` hợp lệ không cần login/cookie/Basic header và không đi vào controller.
3. Origin, actual method và requested headers được kiểm tra bằng allowlist đúng môi trường.
4. Actual request vẫn cần authentication, authorization và CSRF khi phù hợp.
5. Response 401/403 của actual request có CORS headers phù hợp để frontend tin cậy đọc status mà không cần nới policy.
6. `allowedOrigins("*")` không kết hợp `allowCredentials(true)`; không phản chiếu mọi Origin bừa bãi.
7. Cookie SameSite/Secure/HttpOnly/Domain/Path đúng với topology frontend-backend; CORS không ép cookie đi qua.
8. Không lạm dụng `OPTIONS permitAll` thay cho CORS config; không để preflight redirect login.
9. Một nơi chịu trách nhiệm chính cho CORS policy; không vô tình vừa CorsWebFilter độc lập vừa security CorsSpec với policy mâu thuẫn.
10. Khi có nhiều `SecurityWebFilterChain`, preflight OPTIONS phải match chain/path CORS được cấu hình.
11. Gateway/proxy/CDN không chặn OPTIONS, không tự thêm ACA headers tùy tiện và tôn trọng `Vary`.
12. Test preflight hợp lệ, origin/method/header không hợp lệ, actual 401, actual 403, actual 200 và tác dụng controller.
13. Với client non-browser, backend authorization vẫn hoạt động dù không có Origin.
14. Mọi thay đổi chính sách được review/test/giám sát theo origin và endpoint, tránh mở quá phạm vi.
15. Không lưu raw password, cookie session, Authorization header hoặc CSRF token vào error logs.

## 18. Bài tập tự luyện

1. Xóa `.cors(...)` ở Security chain, giữ nguyên `.authorizeExchange(...)`. Thử gửi preflight OPTIONS và quan sát status/headers. Giải thích lỗi từ filter/handler.
2. Thêm `.pathMatchers(HttpMethod.OPTIONS, "/**").permitAll()` mà vẫn không có CORS source; chứng minh OPTIONS pass (nếu có handler) **không đủ** để browser đọc actual request khi ACA headers thiếu.
3. Thay frontend origin sang `http://127.0.0.1:3000`, giữ allowlist `http://localhost:3000`. Xác nhận browser coi chúng là khác origin và CORS từ chối.
4. Thêm `X-Trace-Id` vào request; thử trước và sau khi thêm vào `allowedHeaders`. Không dùng wildcard nếu có thể liệt kê cụ thể.
5. Cho phép `POST /api/actions`; cấu hình CORS method POST, giữ CSRF nếu dùng session cookie và viết test tách riêng preflight pass với actual POST thiếu/đủ token.
6. Thêm chain `/api/**` và chain browser. Viết matcher chain API chỉ dựa trên path, rồi chứng minh preflight OPTIONS cũng chọn đúng chain.
7. Chuyển HTTP Basic demo sang Bearer JWT; kiểm thử preflight vẫn **không có Authorization**, actual request gửi Bearer nhưng phải đủ scope/authority.
8. Đặt ứng dụng sau một gateway; xác định gateway hay backend trả OPTIONS bằng response header và tracing. Tránh hai policy CORS khác nhau.
9. Dùng DevTools so sánh một GET đơn giản không preflight với một GET có header Authorization phải preflight.
10. Thử thay `allowCredentials(true)` bằng `false`; mô tả tác động với JavaScript `credentials:"include"` và trường hợp chỉ dùng Authorization header được client chủ động gắn.
11. Xây dựng ma trận QA cho origin, requested method, requested headers, authentication status và resource permissions; không chỉ test happy path.
12. Xác định vì sao server không nên dùng header Origin làm chứng cứ rằng request đến từ người dùng đáng tin cậy, đặc biệt với script server-to-server.

## Tổng kết

**Thứ tự đúng cho ứng dụng WebFlux phục vụ frontend cross-origin là: CORS được đánh giá trước → preflight hợp lệ kết thúc mà không cần identity → actual request mới đi qua authentication, authorization và CSRF khi phù hợp.**

Spring Security 6.5 hỗ trợ cách này bằng `ServerHttpSecurity.cors(cors -> cors.configurationSource(...))`, đặt `CorsWebFilter` tại thứ tự `SecurityWebFiltersOrder.CORS`. Một preflight 200 kèm headers đúng chưa nói gì về quyền truy cập dữ liệu; actual GET/POST vẫn phải vượt qua chính sách security. Ngược lại, một preflight 401 hoặc redirect login báo hiệu CORS integration/filter ordering có thể đang sai. Đặt allowlist chặt, kiểm tra cả browser và WebTestClient, phân biệt CORS với CSRF và không bao giờ dùng CORS để thay authentication/authorization.

## Tài liệu tham khảo chính thức

- [Spring Security 6.5 — CORS trong WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/cors.html)
- [Spring Security 6.5 — ServerHttpSecurity.CorsSpec Javadoc](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/config/web/server/ServerHttpSecurity.CorsSpec.html)
- [Spring Security 6.5 — SecurityWebFiltersOrder](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/config/web/server/SecurityWebFiltersOrder.html)
- [Spring Security 6.5 — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security 6.5 — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html)
- [Spring Framework 6.2 — WebFlux CORS](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-cors.html)
- [Spring Framework 6.2 — CorsWebFilter API](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/web/cors/reactive/CorsWebFilter.html)
- [MDN — CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
- [MDN — Fetch credentials mode](https://developer.mozilla.org/en-US/docs/Web/API/Request/credentials)
- [Spring Cloud Gateway — CORS Configuration](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/cors-configuration.html)
