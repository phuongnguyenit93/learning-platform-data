# Kiểm tra CORS preflight qua `CorsWebFilter`

> **Chương:** Kiểm thử Reactive  
> **Module:** `SPRING_SECURITY_HTTP_PROTECTION`  
> **Trọng tâm:** Thiết kế và kiểm thử cơ chế xử lý **CORS preflight** ở Spring WebFlux thông qua `org.springframework.web.cors.reactive.CorsWebFilter`, đặc biệt khi ứng dụng còn dùng Spring Security `SecurityWebFilterChain`, CSRF, session cookie và frontend khác origin.  
> **Phạm vi phiên bản:** Spring Framework 6.2/7.x, Spring Security 6.5/7.x và Spring Boot 3.5/4.x; code minh họa dùng Java 17+, JUnit Jupiter và `WebTestClient`. Dùng BOM cùng dòng; đối chiếu package của Boot test annotations khi nâng cấp.

## 1. Bối cảnh: browser gửi OPTIONS nhưng backend trả 401

Giả sử một SPA được phục vụ tại `https://app.example.com`, còn API Spring WebFlux chạy tại `https://api.example.com`. Người dùng bấm “Tạo đơn hàng”; SPA định gửi:

```http
POST /api/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Content-Type: application/json
X-CSRF-TOKEN: token-from-server
Cookie: SESSION=opaque-session-id

{"sku":"BOOK-01","quantity":1}
```

Vì đây là một request **khác origin** và có `Content-Type: application/json` cùng custom header `X-CSRF-TOKEN`, browser thường gửi một **CORS preflight** trước actual POST:

```http
OPTIONS /api/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
```

Preflight là câu hỏi của browser: “Nếu tôi gửi POST từ origin này và mang những header này, server có cho phép không?”. Nó **không thực hiện tạo đơn**, thường không mang cookie phiên đăng nhập, và không được dùng làm bằng chứng user đã authenticated.

Nếu `SecurityWebFilterChain` yêu cầu authentication xử lý OPTIONS **trước khi CORS có cơ hội phản hồi**, server có thể trả 401. Browser sẽ không gửi actual POST. Developer thấy “CORS error” nhưng vội thêm `permitAll("/api/**")` hoặc `csrf.disable()` có thể vô tình nới bảo mật sai chỗ.

### 1.1. Mục tiêu học tập

Sau bài, người học có thể:

1. Phân biệt **Origin**, CORS, preflight, simple/actual requests, cookie policy và CSRF.
2. Nhận diện chính xác preflight bằng `CorsUtils.isPreFlightRequest` và giải thích vì sao OPTIONS không có các header cần thiết chưa phải preflight.
3. Tạo `CorsWebFilter` dùng `org.springframework.web.cors.reactive.CorsConfigurationSource` và `UrlBasedCorsConfigurationSource`, đúng stack WebFlux.
4. Sắp xếp `CorsWebFilter` **trước Spring Security**, không đăng ký CORS filter hai lần thiếu kiểm soát.
5. Dùng `WebTestClient` kiểm tra allowed/denied origins, methods, requested headers, credentials, max-age và `Vary`.
6. Chứng minh allowed preflight không chạy controller, không tạo đơn, không bắt buộc có session cookie hoặc CSRF token.
7. Viết negative tests cho URL không có CORS configuration, malformed Origin, header bị cấm, OPTIONS không phải preflight và actual POST.
8. So sánh standalone `CorsWebFilter` với `ServerHttpSecurity.cors(...)` và `@CrossOrigin`/`WebFluxConfigurer`.
9. Chẩn đoán lỗi qua proxy, CDN, nhiều security chains, JWT/cookie/CSRF, và kiểm tra bằng HTTP server thật cùng browser.

## 2. CORS là chính sách của browser, không phải authentication

**Origin** được xác định bởi bộ ba **scheme + host + port**. Hai URL có thể cùng *site* nhưng vẫn khác *origin*:

| Trang frontend | Backend API | Cùng origin? | Diễn giải |
| --- | --- | --- | --- |
| `https://app.example.com` | `https://app.example.com/api` | Có | Chỉ khác path, không cần CORS |
| `https://app.example.com` | `https://api.example.com` | Không | Khác host |
| `https://app.example.com` | `http://app.example.com` | Không | Khác scheme |
| `http://localhost:3000` | `http://localhost:8080` | Không | Khác port |
| `https://app.example.com` | `https://app.example.com:8443` | Không | Port không phải cổng HTTPS mặc định |

Header `Origin` chỉ mang scheme/host/port, **không mang path**. Khi cấu hình allowlist `allowedOrigins`, viết `https://app.example.com`, không viết `https://app.example.com/some/page`.

CORS chủ yếu điều khiển JavaScript **có được đọc response cross-origin** và browser **có được tiếp tục gửi một actual request sau preflight** hay không. Nó không thay:

- **Authentication:** ai đang gọi API (cookie, HTTP Basic, OAuth2/JWT).
- **Authorization:** user có quyền tạo đơn không.
- **CSRF:** state-changing request dùng browser credential tự đính kèm có mang token phù hợp không.
- **Cookie policy:** `SameSite`, `Secure`, `HttpOnly`, `Domain`, `Path`.
- **CSP, HSTS, firewall:** những lớp HTTP/trình duyệt khác trong module.

Một tool như `curl` hoặc server-side client có thể tự đặt `Origin` bất kỳ và bỏ qua cơ chế browser bảo vệ response. **Không dùng CORS allowlist như cơ chế xác thực nguồn gọi đáng tin cậy thay cho authentication**.

### 2.1. Ba loại request thường bị nhầm

| Loại | Dấu hiệu | CORS filter làm gì? |
| --- | --- | --- |
| Same-origin request | Không có `Origin` hoặc Origin khớp đúng origin request | Không cần CORS authorization như cross-origin |
| Actual/simple CORS request | Có `Origin` khác origin nhưng **không phải** preflight OPTIONS | Kiểm tra CORS, thêm allow-origin/credentials trên response phù hợp; request có thể tiếp tục security/handler |
| Preflight request | **OPTIONS + Origin + Access-Control-Request-Method** | Kiểm tra policy, trả CORS headers hoặc từ chối; **không chạy handler nghiệp vụ** |

“Simple request” không đồng nghĩa an toàn về nghiệp vụ. Ví dụ form POST `application/x-www-form-urlencoded` có thể không cần preflight nhưng vẫn thay đổi dữ liệu. Vì thế **CORS không thể thay CSRF**.

### 2.2. Điều kiện kỹ thuật của preflight

Theo `org.springframework.web.cors.reactive.CorsUtils.isPreFlightRequest(ServerHttpRequest)`, ba yếu tố cần có là:

```text
HTTP method = OPTIONS
Origin: <cross-origin value>
Access-Control-Request-Method: <actual method>

Access-Control-Request-Headers: ...
  -> xuất hiện khi actual request mang headers cần browser hỏi trước
  -> KHÔNG bắt buộc để CorsUtils nhận diện preflight
```

Tương ứng, một `OPTIONS /api/orders` **không có** `Origin` hoặc **không có** `Access-Control-Request-Method` không phải preflight hợp lệ theo định nghĩa đó. Nó có thể đi tiếp vào security chain và bị 401/403/404/405 tùy endpoint, nhưng không được coi là lỗi xử lý preflight.

### 2.3. Diễn biến request qua WebFlux filters

```text
Browser SPA               WebFlux app                       Endpoint
   |                         |                                |
   |-- OPTIONS + Origin ---->|                                |
   | Access-Control-Request-Method: POST                      |
   | Access-Control-Request-Headers: content-type,x-csrf-token|
   |                         v                                |
   |                    CorsWebFilter                          |
   |                      +-- allowed?                         |
   |                      |    yes -> reply headers           |
   |                      |    no  -> deny                    |
   |<--- preflight result --+                                |
   |                         X (không vào controller)          |
   |                                                          |
   |-- POST + cookie + CSRF header --------------------------->|
   |                         |                                |
   |                    CorsWebFilter                          |
   |                         |                                |
   |                SecurityWebFilterChain                     |
   |                   CSRF + auth + authz                     |
   |                         |                                |
   |                         +------------------------------->|
   |<-------------------- response CORS + HTTP ----------------|
```

Chỉ sau allowed preflight, browser mới có thể tiếp tục actual request theo cơ chế Fetch/CORS. **Preflight 200 không tự chứng minh actual POST 200**.

## 3. `CorsWebFilter` thuộc API nào?

WebFlux cần đúng class:

```java
org.springframework.web.cors.reactive.CorsWebFilter
org.springframework.web.cors.reactive.CorsConfigurationSource
org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource
org.springframework.web.cors.reactive.CorsUtils
org.springframework.web.cors.CorsConfiguration
```

`CorsWebFilter` là `WebFilter`, được Spring Framework cung cấp từ 5.0. Nó lấy CORS policy theo `ServerWebExchange`, dùng `CorsProcessor` (mặc định `DefaultCorsProcessor`), xử lý preflight trực tiếp và thêm các response headers cho actual CORS requests.

### 3.1. Reactive khác Servlet

| Servlet stack | Reactive WebFlux |
| --- | --- |
| `org.springframework.web.filter.CorsFilter` | `org.springframework.web.cors.reactive.CorsWebFilter` |
| `org.springframework.web.cors.UrlBasedCorsConfigurationSource` | `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource` |
| `HttpServletRequest`, Servlet `FilterChain` | `ServerWebExchange`, `WebFilterChain` |
| `HttpSecurity` / Servlet `SecurityFilterChain` | `ServerHttpSecurity` / `SecurityWebFilterChain` |
| `MockMvc` | `WebTestClient` |

`CorsConfiguration` bản thân nằm trong package chung `org.springframework.web.cors`, nhưng `CorsConfigurationSource` và `UrlBasedCorsConfigurationSource` dành cho WebFlux phải lấy từ package **`.reactive`**.

### 3.2. `CorsWebFilter`, `@CrossOrigin` và `ServerHttpSecurity.cors`

Spring WebFlux có nhiều cách cấu hình CORS:

| Cách | Đặt CORS ở đâu? | Phù hợp khi nào? |
| --- | --- | --- |
| `CorsWebFilter` bean | Global WebFilter, trước handler | Cần xử lý sớm, dùng functional routes hoặc Security |
| `ServerHttpSecurity.cors(...)` | Filter bên trong Security integration | Cần policy CORS tích hợp cho Security chain |
| `WebFluxConfigurer.addCorsMappings(...)` | `HandlerMapping` | Ứng dụng annotation controllers, CORS ở web routing layer |
| `@CrossOrigin` | Controller hoặc handler method | Rule cục bộ cho một handler |

**Không trộn tất cả phương án không có lý do rõ ràng.** Hai nơi cùng sinh `Access-Control-Allow-Origin` hoặc hai rule khác nhau có thể gây header trùng, bị browser từ chối và khó xác định rule thật sự có hiệu lực.

Trong bài này, phương án **chính** là một `CorsWebFilter` được đăng ký và đặt order **trước Spring Security**; phương án dùng Security DSL sẽ được trình bày riêng, **thay thế**, không đăng ký thêm filter ngoài.

### 3.3. Thế nào là “preflight được chặn tại filter”?

Với `CorsWebFilter`, request preflight được xử lý bởi `CorsProcessor`. Khi đó filter **không gọi `chain.filter(exchange)`** cho preflight, bất kể policy chấp nhận hay từ chối. Vì vậy:

- Controller `@RequestMapping(method=OPTIONS)` không cần tồn tại để preflight hợp lệ nhận CORS headers.
- Security authentication không cần nhận session cookie từ preflight; filter đứng trước Security.
- Một request OPTIONS **không phải preflight** vẫn có thể được chuyển tiếp và bị authentication/handler xử lý.
- Negative test phải assert cả status/CORS headers **và** controller không chạy; chỉ assert 200 dễ bỏ sót cấu hình không có CORS headers.

## 4. CORS response headers phải kiểm tra

### 4.1. Một preflight hợp lệ

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: content-type,x-csrf-token
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 3600
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
```

Đây là **mẫu hình**, không phải từng byte response bất biến. Trong Spring, danh sách methods/headers có thể được nối bằng dấu phẩy hoặc nhiều header values tùy version/HTTP adapter. `Vary` có thể được gộp vào một dòng hoặc xuất nhiều dòng; test nên kiểm tra **semantics** chứ không dựa vào thứ tự hoặc cách gộp.

| Header | Ý nghĩa | Khi kiểm thử |
| --- | --- | --- |
| `Access-Control-Allow-Origin` | Origin được chấp thuận; dùng origin chính xác khi có credentials | Assert exact allowed origin, không được cấp cho origin lạ |
| `Access-Control-Allow-Methods` | Actual methods được phép | Chứa method mà browser đề nghị |
| `Access-Control-Allow-Headers` | Request headers được phép trên actual request | Bao gồm `content-type`, `x-csrf-token` theo policy |
| `Access-Control-Allow-Credentials` | Browser có thể đưa credentials theo Fetch config | `true` khi SPA dùng session cookie và policy cho phép |
| `Access-Control-Max-Age` | Cache policy preflight tính bằng **giây** | Giá trị do server cấu hình; browser có giới hạn riêng |
| `Vary` | Yêu cầu caches phân biệt Origin, requested method/headers | Tránh cache trả nhầm CORS response |
| `Access-Control-Expose-Headers` | Response headers JS được đọc từ actual response | **Không** thay `Allow-Headers` trong preflight |

### 4.2. Credentials không tự có chỉ vì allow-origin

Với SPA dùng session cookie, server cần allowlist origin và `allowCredentials(true)` theo threat model, còn frontend fetch phải đặt `credentials: "include"` nếu cross-origin. Cookie vẫn phải thỏa `SameSite/Secure/Domain/Path` và browser third-party restrictions. `Access-Control-Allow-Credentials: true` **không bắt browser gửi cookie bị chặn**.

### 4.3. Không dùng `allowedOrigins("*")` khi có credentials

Spring Framework `CorsConfiguration.validateAllowCredentials()` từ chối kết hợp wildcard `*` trong `allowedOrigins` với `allowCredentials(true)`. Nếu cần pattern, dùng `allowedOriginPatterns` với phạm vi hostname/port được review; Spring phản hồi **origin cụ thể phù hợp**, không phản hồi wildcard.

Tránh pattern quá rộng như `https://*.example.com` nếu có subdomain do khách hàng quản lý. CORS origin allowlist là **quyết định chia sẻ dữ liệu nhạy cảm cho mã JavaScript ở origin đó**.

## 5. Dependencies và nguyên tắc tách test environment

### 5.1. Gradle với Spring Boot BOM

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

### 5.2. Maven test dependencies

```xml
<dependencies>
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
```

Đối với Boot 4, đối chiếu các **test starter modules chia theo stack** (ví dụ WebFlux test starter) và vị trí `@WebFluxTest`/`AutoConfigureWebTestClient`. Đừng tự pin Spring Security version khác BOM để có method mà IDE chưa nhận. Khi cần kiểm tra dependency thực trong dự án của người học:

```bash
./gradlew dependencyInsight --dependency spring-security-web --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-test --configuration testRuntimeClasspath
./mvnw dependency:tree -Dincludes=org.springframework.security
```

Ví dụ trong bài giả định Spring Test/JUnit có sẵn; **không phải kết quả đã chạy build**. Trên Windows, wrapper có thể là `gradlew.bat` hoặc `mvnw.cmd`.

### 5.3. Chọn lớp test đúng

| Lớp test | Có kiểm tra `CorsWebFilter`? | Giới hạn |
| --- | --- | --- |
| Unit `CorsUtils` / `CorsConfiguration` | Chỉ rule matching/validation | Không kiểm tra filter ordering |
| Mock `WebTestClient.bindToApplicationContext` | Có nếu context chứa filter bean | Không mô phỏng browser cookie rules |
| Standalone `CorsWebFilter` + `MockServerWebExchange` | Có, cô lập processor | Không tự xác minh Spring Security wiring |
| `@WebFluxTest` slice | Có **nếu import đúng CORS/Security config** | Có thể thiếu custom bean/filter |
| `@SpringBootTest` full mock context | Thường có full bean wiring | Không qua TCP/gateway |
| `@SpringBootTest(RANDOM_PORT)` | HTTP thật tới app | Không phải browser engine hoặc HTTPS edge |
| Browser E2E qua HTTPS staging | Browser preflight, credentials, cookies | Đòi môi trường policy tương ứng production |

Để trả lời câu hỏi “CORS preflight có bị authentication chặn không?”, chọn **mock application context có cả `CorsWebFilter` lẫn `SecurityWebFilterChain`**, không chỉ test controller.

## 6. Cấu hình một `CorsWebFilter` tường minh

Ta dùng allowlist chính xác cho frontend `https://app.example.com`, API tại `/api/**`, các methods GET/POST/OPTIONS, headers `Content-Type` và `X-CSRF-TOKEN`; `Authorization` được thêm khi muốn test Bearer API. Để tránh wildcard gây hiểu lầm, mọi giá trị được khai báo tường minh.

### 6.1. Reactive CORS source

```java
package com.example.protection.cors;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
public class ReactiveCorsPolicyConfig {

    @Bean
    CorsConfigurationSource browserCorsSource() {
        CorsConfiguration policy = new CorsConfiguration();
        policy.setAllowedOrigins(List.of(
            "https://app.example.com"
        ));
        policy.setAllowedMethods(List.of(
            "GET", "POST", "OPTIONS"
        ));
        policy.setAllowedHeaders(List.of(
            "Content-Type", "X-CSRF-TOKEN", "Authorization"
        ));
        policy.setAllowCredentials(true);
        policy.setMaxAge(3600L);
        policy.setExposedHeaders(List.of("X-Request-Id"));

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", policy);
        return source;
    }
}
```

**Lưu ý URL scope:** source trên chỉ gắn CORS policy cho `/api/**`. `GET /public/ping` không có CORS policy theo source này; browser cross-origin không tự được phép đọc response đó. Đây là chủ đích test `no matching config` sau này, không phải endpoint bị hỏng.

### 6.2. Đăng ký filter với thứ tự trước Security

```java
package com.example.protection.cors;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.CorsWebFilter;

@Configuration
public class ReactiveCorsWebFilterConfig {

    @Bean
    @Order(Ordered.HIGHEST_PRECEDENCE)
    CorsWebFilter corsWebFilter(CorsConfigurationSource browserCorsSource) {
        return new CorsWebFilter(browserCorsSource);
    }
}
```

Spring WebFlux nhận các `WebFilter` beans từ application context và có thể sắp xếp bằng `@Order` hoặc interface `Ordered`. `Ordered.HIGHEST_PRECEDENCE` ở đây đặt CORS filter trước Spring Security's `WebFilterChainProxy` để **preflight không cần cookie/authentication** được xử lý trước.

**Không dùng `SecurityWebFiltersOrder` để xếp một standalone `CorsWebFilter` global:** `SecurityWebFiltersOrder` chỉ áp cho filters bên trong `SecurityWebFilterChain`. `@Order` trên bean `CorsWebFilter` là thứ tự ở **global WebFlux WebFilter chain**; hai cơ chế order khác nhau.

### 6.3. Tránh xử lý CORS trùng với Security DSL

Nếu đã chọn global `CorsWebFilter` ở mục 6.2, ta chủ động **không thêm filter CORS thứ hai trong Security chain**. Trong fixture dưới đây:

```java
.cors(cors -> cors.disable())
```

được hiểu là **tắt lớp CORS integration của riêng Spring Security**, **không tắt global `CorsWebFilter`** đã đăng ký/đặt trước Security. Chỉ dùng cách này khi chắc chắn global filter có mặt và đã kiểm thử end-to-end. Nếu **không** có global filter, tắt CORS trong Security rất dễ khiến frontend cross-origin không thể dùng API.

Phương án thay thế an toàn khác là **không đăng ký `CorsWebFilter` riêng**, chỉ truyền `CorsConfigurationSource` cho `ServerHttpSecurity.cors(cors -> cors.configurationSource(...))`; phần này ở mục 13. **Chọn một chiến lược nhất quán**, không coi việc có nhiều filter là defense in depth.

### 6.4. Vì sao không dùng `config.applyPermitDefaultValues()` vô điều kiện?

`applyPermitDefaultValues()` có thể cấu hình wildcard origins, wildcard headers, methods đơn giản và max age mặc định nếu chưa được chỉ định. Trong ứng dụng có credentialed browser session, việc vô tình cho mọi origin hoặc method là một thay đổi security policy quan trọng.

Mẫu ở mục 6.1 đặt allowlist explicit để người học thấy rõ **origin + method + header**. Nếu dùng helper defaults trong local demos, phải review lại trước staging/production.

## 7. Fixture WebFlux + Security để chứng minh filter ordering

### 7.1. Handler có side-effect counter

```java
package com.example.protection.cors;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

final class OrderCounter {
    private final AtomicInteger accepted = new AtomicInteger();
    int count() { return accepted.get(); }
    void reset() { accepted.set(0); }
    void increment() { accepted.incrementAndGet(); }
}

@RestController
public class OrdersController {
    private final OrderCounter counter;

    public OrdersController(OrderCounter counter) {
        this.counter = counter;
    }

    @GetMapping("/api/orders")
    public Mono<String> listOrders() {
        return Mono.just("orders-list");
    }

    @PostMapping("/api/orders")
    public Mono<ResponseEntity<String>> createOrder() {
        return Mono.fromSupplier(() -> {
            counter.increment();
            return ResponseEntity.ok()
                .header("X-Request-Id", "demo-correlation-id")
                .body("created");
        });
    }

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }
}
```

Counter chứng minh preflight không chạm tới handler tạo order. Không cần `@RequestMapping(method = OPTIONS)` trên controller; `CorsWebFilter` xử lý trước router. Với application thật, side-effect assertion nên ở service/repository (không ghi record/event khi preflight).

### 7.2. Spring Security chain yêu cầu authentication và giữ CSRF

```java
package com.example.protection.cors;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/public/**").permitAll()
                .anyExchange().authenticated()
            )
            .csrf(Customizer.withDefaults())
            // Global CorsWebFilter xử lý CORS trước chain này.
            .cors(cors -> cors.disable())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService testUserStore() {
        return new MapReactiveUserDetailsService(
            User.withUsername("alice")
                .password("{noop}for-tests-only")
                .roles("USER")
                .build()
        );
    }
}
```

Trong fixture, `GET /api/orders` cần user, `POST /api/orders` cần **user và CSRF token**. `OPTIONS` preflight không mang credential nhưng **nếu allowed** sẽ được `CorsWebFilter` xử lý trước authentication.

`{noop}` chỉ dùng ở test fixture, không được dùng production. `csrf(Customizer.withDefaults())` giữ CSRF cho browser/session; CORS không thay CSRF.

### 7.3. WebFlux infrastructure thuần Spring Test

```java
package com.example.protection.cors;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.EnableWebFlux;

@Configuration
@EnableWebFlux
public class ReactiveWebConfig {

    @Bean OrderCounter orderCounter() {
        return new OrderCounter();
    }

    @Bean
    OrdersController ordersController(OrderCounter counter) {
        return new OrdersController(counter);
    }
}
```

`@EnableWebFlux` phù hợp Spring Test context độc lập; **không tự ý thêm** vào Spring Boot app đã có WebFlux auto-configuration nếu không hiểu ảnh hưởng đối với Boot-specific codecs/configurers.

### 7.4. Tạo WebTestClient chứa tất cả filters

```java
package com.example.protection.cors;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

@SpringJUnitConfig(classes = {
    ReactiveWebConfig.class,
    ReactiveCorsPolicyConfig.class,
    ReactiveCorsWebFilterConfig.class,
    ReactiveSecurityConfig.class
})
class CorsPreflightIntegrationTest {

    @Autowired ApplicationContext context;
    @Autowired OrderCounter counter;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        counter.reset();
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    // Các @Test ở các mục sau nằm trong class này.
}
```

`bindToApplicationContext` lấy **global `CorsWebFilter` bean và Security WebFilters từ đúng context**. `apply(springSecurity())` dùng cho Security test support; `mutateWith(csrf())` chỉ được dùng khi muốn thử actual POST trong mock context, **không dùng để làm preflight OPTIONS “hợp lệ”**.

Nếu chỉ dùng:

```java
WebTestClient notIntegration =
    WebTestClient.bindToController(
        new OrdersController(new OrderCounter())
    ).build();
```

thì client có thể không có `CorsWebFilter` hoặc `SecurityWebFilterChain` từ app thật. Một response 200/401 ở client đó không trả lời câu hỏi filter ordering production. 

## 8. Test dương: preflight hợp lệ không cần đăng nhập

Ta gửi đúng ba header xác định preflight và các requested headers phù hợp allowlist:

```java
@Test
void approvedPreflightReturnsCorsHeadersWithoutCookie() {
    client.options().uri("/api/orders")
        .header("Origin", "https://app.example.com")
        .header("Access-Control-Request-Method", "POST")
        .header(
            "Access-Control-Request-Headers",
            "content-type,x-csrf-token")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals(
            "Access-Control-Allow-Origin",
            "https://app.example.com")
        .expectHeader().valueMatches(
            "Access-Control-Allow-Methods", "(?i).*POST.*")
        .expectHeader().valueMatches(
            "Access-Control-Allow-Headers", "(?i).*x-csrf-token.*")
        .expectHeader().valueEquals(
            "Access-Control-Allow-Credentials", "true")
        .expectHeader().valueEquals(
            "Access-Control-Max-Age", "3600")
        .expectBody().isEmpty();

    assertEquals(0, counter.count());
}
```

**Điều test chứng minh:**

- Preflight được xử lý thành công mặc dù **không có `SESSION` cookie, Basic authentication hay CSRF token**.
- CORS response phản hồi origin chính xác và cho phép POST/các requested headers.
- `CorsWebFilter` short-circuit trước controller, không tạo order.
- Test kiểm tra headers chứ không chỉ status 200.

**Điều test không chứng minh:** user đã đăng nhập, CSRF token thật khớp, POST sẽ được authorize, hoặc browser đã gửi cookie theo SameSite policy. Những câu hỏi đó cần test riêng.

### 8.1. Thêm assertion cho `Vary`

`DefaultCorsProcessor` đặt `Vary` cho Origin, requested method và requested headers để intermediaries không dùng nhầm CORS response giữa các request khác nhau. Vì server có thể gộp hoặc tách các header values, hãy kiểm tra semantic:

```java
import java.util.Locale;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Test
void preflightHasVaryDimensionsForCaches() {
    client.options().uri("/api/orders")
        .header("Origin", "https://app.example.com")
        .header("Access-Control-Request-Method", "POST")
        .header("Access-Control-Request-Headers", "x-csrf-token")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().values("Vary", values -> {
            String combined = String.join(",", values)
                .toLowerCase(Locale.ROOT);
            assertTrue(combined.contains("origin"));
            assertTrue(combined.contains("access-control-request-method"));
            assertTrue(combined.contains("access-control-request-headers"));
        });
}
```

Không assert `Vary` là **một** chuỗi cố định theo đúng thứ tự, vì HTTP cho phép trình bày nhiều field lines hoặc gộp comma-separated values. Với CDN/ingress, `Vary` còn có thể được bổ sung bởi các lớp trung gian.

### 8.2. Preflight không mang cookie — test không cần mock principal

Không thêm:

```java
// Không cần cho OPTIONS CORS preflight:
client.mutateWith(mockUser("alice"))
    .mutateWith(csrf())
    .options().uri("/api/orders");
```

Preflight phải được policy CORS xử lý đúng **khi không có user/session credential**. Nếu chỉ chạy pass sau khi gắn `mockUser()`, có thể `CorsWebFilter` đang không đứng trước authentication.

### 8.3. Không bắt buộc `Access-Control-Request-Headers`

Một preflight chỉ yêu cầu một method, không liệt kê request headers:

```java
@Test
void approvedPreflightWithoutRequestedHeadersStillPasses() {
    client.options().uri("/api/orders")
        .header("Origin", "https://app.example.com")
        .header("Access-Control-Request-Method", "POST")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals(
            "Access-Control-Allow-Origin", "https://app.example.com");
}
```

Đây vẫn là preflight vì có **OPTIONS + Origin + Access-Control-Request-Method**. Không viết matcher custom đòi `Access-Control-Request-Headers` mới cho phép; điều đó vô tình chặn các preflight hợp lệ.

## 9. Test âm: origin, method và header bị từ chối

Các tests nên thay **một tham số mỗi lần**, giữ URI/HTTP method và cấu hình filter ổn định. `DefaultCorsProcessor` của Spring WebFlux thường trả 403 khi origin, actual method hoặc requested header không được policy cho phép.

### 9.1. Origin không nằm trong allowlist

```java
@Test
void preflightFromUntrustedOriginIsRejected() {
    client.options().uri("/api/orders")
        .header("Origin", "https://attacker.example")
        .header("Access-Control-Request-Method", "POST")
        .header("Access-Control-Request-Headers", "content-type")
        .exchange()
        .expectStatus().isForbidden()
        .expectHeader()
        .doesNotExist("Access-Control-Allow-Origin");

    assertEquals(0, counter.count());
}
```

Một origin lạ có thể được attacker tự điền vào `curl`; CORS reject chỉ có ý nghĩa trong threat model browser. **Không** dùng test này thay kiểm thử authentication/JWT validation hoặc CSRF.

### 9.2. Origin có scheme hoặc port khác

```java
@Test
void httpOriginIsNotEquivalentToHttpsOrigin() {
    client.options().uri("/api/orders")
        .header("Origin", "http://app.example.com")
        .header("Access-Control-Request-Method", "POST")
        .exchange()
        .expectStatus().isForbidden();
}

@Test
void nonDefaultPortIsASeparateOrigin() {
    client.options().uri("/api/orders")
        .header("Origin", "https://app.example.com:8443")
        .header("Access-Control-Request-Method", "POST")
        .exchange()
        .expectStatus().isForbidden();
}
```

Đừng ghi origin trong config thiếu scheme rồi tưởng “mọi scheme đều được”. Với local development, `http://localhost:3000` và `http://localhost:5173` là hai origins khác nhau; cấu hình từng origin cần thiết và tách khỏi production.

### 9.3. Requested method không được phép

```java
@Test
void preflightForDeleteIsRejectedByAllowedMethods() {
    client.options().uri("/api/orders")
        .header("Origin", "https://app.example.com")
        .header("Access-Control-Request-Method", "DELETE")
        .exchange()
        .expectStatus().isForbidden()
        .expectHeader()
        .doesNotExist("Access-Control-Allow-Origin");

    assertEquals(0, counter.count());
}
```

`Access-Control-Request-Method` nói về **actual request sau này**, không phải method của preflight: preflight luôn dùng OPTIONS. Allowed methods chứa POST/GET/OPTIONS trong fixture; DELETE không được chấp thuận.

### 9.4. Header không được phép

```java
@Test
void preflightWithUnknownRequestedHeaderIsRejected() {
    client.options().uri("/api/orders")
        .header("Origin", "https://app.example.com")
        .header("Access-Control-Request-Method", "POST")
        .header(
            "Access-Control-Request-Headers",
            "content-type,x-internal-admin")
        .exchange()
        .expectStatus().isForbidden()
        .expectHeader()
        .doesNotExist("Access-Control-Allow-Origin");

    assertEquals(0, counter.count());
}
```

Tên header HTTP **không phân biệt chữ hoa/chữ thường**; test policy nên kiểm tra bất kể client gửi `X-CSRF-TOKEN` hay `x-csrf-token`. Đừng hard-code việc Spring trả tên header đúng hoa/thường như request, chỉ assert tập header cho phép.

### 9.5. `Origin: null` có thể xuất hiện từ opaque origin

Các trang sandboxed, `file:` hoặc một số ngữ cảnh privacy có thể sinh origin literal `null`. Không thêm `"null"` vào allowlist credentials chỉ vì test local file bị CORS reject.

```java
@Test
void opaqueNullOriginIsNotAllowedByDefault() {
    client.options().uri("/api/orders")
        .header("Origin", "null")
        .header("Access-Control-Request-Method", "POST")
        .exchange()
        .expectStatus().isForbidden();
}
```

Nếu ứng dụng thực sự cần hỗ trợ opaque origin, đó là một quyết định threat model riêng với phạm vi rất hẹp, không nên nới `allowedOrigins` mặc định.

### 9.6. Vì sao status 403 không đủ?

Một test origin bị cấm nhận 403 có thể “xanh” vì:

- Authentication/authorization chặn từ trước, CORS filter chưa được gọi.
- HTTP firewall từ chối URL bất thường.
- Custom CORS error handler trả 403 không phản ánh rule bạn định test.

Vì vậy cần **positive preflight không có credential nhận CORS headers** song song với các negative tests, và kiểm tra filter order. Đối với fixture các mục 6–7, positive preflight ở mục 8 chính là đối chứng đó.

## 10. OPTIONS không đủ header chưa chắc là preflight

### 10.1. Thiếu `Origin`

```java
@Test
void bareOptionsIsNotCorsPreflight() {
    client.options().uri("/api/orders")
        .exchange()
        // Security yêu cầu authentication; đây KHÔNG phải preflight.
        .expectStatus().isUnauthorized()
        .expectHeader()
        .doesNotExist("Access-Control-Allow-Origin");
}
```

Ở fixture HTTP Basic, bare OPTIONS không thuộc `/public/**` và không có credential, nên Security có thể trả 401. Trạng thái có thể khác nếu ứng dụng `permitAll` OPTIONS, có handler OPTIONS hoặc custom authentication entry point; test phải phản ánh security config cụ thể.

### 10.2. Có `Origin` nhưng thiếu `Access-Control-Request-Method`

```java
@Test
void optionsWithOriginButNoRequestedMethodIsNotPreflight() {
    client.options().uri("/api/orders")
        .header("Origin", "https://app.example.com")
        .exchange()
        .expectStatus().isUnauthorized();
}
```

Request này có thể được nhận diện là một **actual CORS request bằng method OPTIONS**, nhưng không phải preflight. `CorsWebFilter` có thể gắn `Access-Control-Allow-Origin` nếu OPTIONS là allowed method, rồi **cho request tiếp tục Security**. Không assert thiếu allow-origin trong trường hợp này; chỉ nên assert nó **không** được short-circuit như preflight.

### 10.3. Phân biệt với một OPTIONS route thật

Nếu ứng dụng thật có endpoint `OPTIONS /health` được cho phép và xử lý bằng router, OPTIONS không có preflight headers có thể trả 200 hoặc 204 theo handler. Điều đó **không phải** bằng chứng CORS preflight đã được xử lý. Dùng headers preflight đúng và assert `Access-Control-Allow-*` như mục 8.

### 10.4. Không sửa 401 preflight bằng `permitAll("/api/**")`

Nếu một OPTIONS **đúng preflight** nhận 401, cần kiểm tra:

1. `CorsWebFilter` bean có được đăng ký không?
2. Có `@Order(Ordered.HIGHEST_PRECEDENCE)` hoặc cơ chế order tương đương không?
3. `CorsConfigurationSource` có policy khớp path/origin/method/headers không?
4. Có filter custom trước CORS yêu cầu token/authentication không?
5. Gateway có chặn OPTIONS trước khi tới WebFlux không?

Không phải giải pháp: bỏ authentication cho actual POST hoặc tắt CSRF của browser chain. Preflight được kiểm tra theo CORS policy, không dựa vào việc user có session.

## 11. URL không có CORS configuration: 200 chưa chắc là allowed

Một trong những lỗi đánh giá nguy hiểm nhất là coi status 200 của OPTIONS đồng nghĩa browser sẽ chấp nhận cross-origin call. Trong Spring WebFlux, khi `CorsConfigurationSource` trả `null` cho request, `DefaultCorsProcessor` có thể **không thêm CORS headers**, còn `CorsWebFilter` vẫn short-circuit preflight.

Với source `registerCorsConfiguration("/api/**", policy)`, URL `/public/ping` **không** có policy:

```java
@Test
void unmatchedCorsPathHasNoAllowOriginEvenIfOptionsIsSuccessful() {
    client.options().uri("/public/ping")
        .header("Origin", "https://app.example.com")
        .header("Access-Control-Request-Method", "GET")
        .exchange()
        // Filter có thể trả 200 nhưng KHÔNG cấp quyền CORS:
        .expectStatus().isOk()
        .expectHeader()
        .doesNotExist("Access-Control-Allow-Origin");
}
```

**Cách kết luận đúng:** preflight **chỉ được browser chấp nhận** khi response có CORS headers đáp ứng `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers` theo yêu cầu. Status 2xx đơn lẻ chưa đủ.

### 11.1. Phân biệt “config null” và “config có nhưng reject”

| Trạng thái của source | `DefaultCorsProcessor` thường làm gì? | Kết quả browser |
| --- | --- | --- |
| Có policy match, Origin hợp lệ | Thêm allow-origin/method/header/credentials | Có thể cho phép |
| Có policy match, Origin không được phép | Trả 403 | Không cho phép |
| Có policy match, requested method không được phép | Trả 403 | Không cho phép |
| Có policy match, requested header không được phép | Trả 403 | Không cho phép |
| **Không có policy match** (`null`) | Không thêm allow-origin, preflight có thể 200 | **Không cho phép** |

Vì vậy negative test cho URL không có mapping nên assert **absence of allow-origin**, không khăng khăng assert 403 trong mọi biến thể source/processor.

### 11.2. Kiểm thử prefix/path case

`/api/**` không đồng nghĩa với `/apis/**`, `/API/**` hoặc URL public đã bị gateway strip prefix. Viết tests cho những route thực tế để tránh:

```text
Public:    https://api.example.com/gateway/api/orders
Ingress:   /gateway/api/orders -> /api/orders
Spring:    CorsConfigurationSource matches /api/**
```

Nếu test chỉ dùng internal path `/api/orders` nhưng public gateway không rewrite như dự kiến, browser có thể nhận preflight 200 **không có CORS headers** hoặc 404/401 ở edge. Cần HTTP staging test qua public URL.

## 12. Kiểm thử actual CORS requests: preflight chưa phải toàn bộ luồng

Sau khi CORS đã cho phép preflight, browser mới gửi actual request. Tại đây Spring Security **vẫn** phải thực thi authentication, authorization, CSRF, firewall và business logic.

### 12.1. GET thực từ origin được phép nhưng chưa xác thực

```java
@Test
void allowedOriginDoesNotBypassAuthenticationOnActualGet() {
    client.get().uri("/api/orders")
        .header("Origin", "https://app.example.com")
        .exchange()
        .expectStatus().isUnauthorized()
        .expectHeader().valueEquals(
            "Access-Control-Allow-Origin",
            "https://app.example.com");
}
```

Đây là minh họa rõ **CORS permit ≠ auth permit**: global `CorsWebFilter` gắn response CORS headers hợp lệ, rồi Security HTTP Basic vẫn trả 401 vì không có credential. Header allow-origin không biến response 401 thành dữ liệu đã được cấp quyền.

### 12.2. GET với principal hợp lệ

```java
@Test
void authenticatedCorsGetIsAccepted() {
    client.mutateWith(mockUser("alice").roles("USER"))
        .get().uri("/api/orders")
        .header("Origin", "https://app.example.com")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals(
            "Access-Control-Allow-Origin",
            "https://app.example.com")
        .expectHeader().valueEquals(
            "Access-Control-Allow-Credentials", "true")
        .expectBody(String.class).isEqualTo("orders-list");
}
```

`mockUser` chỉ cấp principal cho **mock WebTestClient**, không thực hiện login thật hoặc lưu authentication vào session. Test live HTTP cần Basic/JWT/session credentials thực.

### 12.3. Origin không được phép trên actual request

```java
@Test
void untrustedOriginActualGetIsRejectedByCorsBeforeSecurity() {
    client.mutateWith(mockUser("alice").roles("USER"))
        .get().uri("/api/orders")
        .header("Origin", "https://attacker.example")
        .exchange()
        .expectStatus().isForbidden()
        .expectHeader()
        .doesNotExist("Access-Control-Allow-Origin");
}
```

Một CORS reject có thể xảy ra **trước** authentication/authorization trong fixture global filter. Không suy “403 = user thiếu role” nếu request có Origin lạ.

### 12.4. POST được CORS cho phép nhưng thiếu CSRF

```java
@Test
void corsPermissionDoesNotReplaceCsrfForPost() {
    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/api/orders")
        .header("Origin", "https://app.example.com")
        .contentType(org.springframework.http.MediaType.APPLICATION_JSON)
        .bodyValue("{}")
        .exchange()
        .expectStatus().isForbidden();

    assertEquals(0, counter.count());
}
```

Trong fixture, CSRF vẫn bật trong `SecurityWebFilterChain`. Actual POST authenticated nhưng thiếu token bị 403. Với browser thật, cookie `SESSION` có thể tự đi kèm; cần token CSRF mà ứng dụng cung cấp, không chỉ CORS.

### 12.5. POST mock có điều kiện CSRF hợp lệ

```java
@Test
void authenticatedPostWithCsrfTestSupportReachesHandler() {
    client.mutateWith(mockUser("alice").roles("USER"))
        .mutateWith(csrf())
        .post().uri("/api/orders")
        .header("Origin", "https://app.example.com")
        .contentType(org.springframework.http.MediaType.APPLICATION_JSON)
        .bodyValue("{}")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals(
            "Access-Control-Allow-Origin",
            "https://app.example.com")
        .expectHeader().valueEquals(
            "Access-Control-Expose-Headers", "X-Request-Id")
        .expectHeader().valueEquals(
            "X-Request-Id", "demo-correlation-id")
        .expectBody(String.class).isEqualTo("created");

    assertEquals(1, counter.count());
}
```

`csrf()` hỗ trợ **mock** test khi điều kiện CSRF đã được đáp ứng, không chứng minh session/token thật. Nếu muốn kiểm tra CSRF repository, cần GET token bootstrap, cookie session và POST actual token **không gọi `csrf()`** như các bài trong chương Reactive Testing.

### 12.6. `Access-Control-Expose-Headers` khác `Allow-Headers`

Trong config:

```java
policy.setAllowedHeaders(List.of(
    "Content-Type", "X-CSRF-TOKEN", "Authorization"));
policy.setExposedHeaders(List.of("X-Request-Id"));
```

- `Access-Control-Allow-Headers`: browser **được gửi** những request headers nào sau preflight.
- `Access-Control-Expose-Headers`: JavaScript **được đọc** những response headers nào trên actual response (ngoài các safelisted response headers).

Không thêm `Authorization` vào `exposedHeaders` với hy vọng browser sẽ được gửi Bearer token; đó là sai chiều dữ liệu. Và không expose session ID, raw CSRF token hoặc internal infrastructure headers cho JS nếu không có yêu cầu rõ ràng.

### 12.7. WebTestClient có thể gửi actual POST trực tiếp dù browser sẽ preflight

Mock `WebTestClient` **không tự phát sinh OPTIONS** trước POST có JSON/custom header như browser. Vì thế:

```text
WebTestClient POST -> test HTTP server xử lý POST được hay không.
Browser fetch POST -> có thể OPTIONS trước, kiểm tra CORS,
                     sau đó mới gửi POST nếu preflight thành công.
```

Đừng kết luận “đã test preflight” chỉ vì một POST kèm `Origin` trả 200. Cần test OPTIONS **riêng** và browser E2E khi chuyển sang môi trường public.

## 13. Phương án thay thế: CORS tích hợp trong Spring Security

Nếu không muốn đăng ký một `CorsWebFilter` bean global, Spring Security WebFlux hỗ trợ CORS tích hợp. Dùng cùng `CorsConfigurationSource` **Reactive** nhưng cấu hình bên trong `ServerHttpSecurity`.

### 13.1. Cấu hình thay thế — không có global CorsWebFilter bean

```java
package com.example.protection.cors;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.reactive.CorsConfigurationSource;

@Configuration
@EnableWebFluxSecurity
public class SecurityManagedCorsConfig {

    @Bean
    SecurityWebFilterChain securityChain(
            ServerHttpSecurity http,
            CorsConfigurationSource browserCorsSource) {

        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/public/**").permitAll()
                .anyExchange().authenticated()
            )
            .cors(cors -> cors
                .configurationSource(browserCorsSource))
            .csrf(Customizer.withDefaults())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Đây là **biến thể thay thế** `ReactiveSecurityConfig` và `ReactiveCorsWebFilterConfig` ở mục 6–7. Trong test context cho biến thể này:

- **Giữ** `ReactiveCorsPolicyConfig` và `ReactiveWebConfig`.
- **Không đăng ký** `ReactiveCorsWebFilterConfig` (tránh hai CORS processors).
- **Không đăng ký** `ReactiveSecurityConfig` fallback khác.
- **Đăng ký** `SecurityManagedCorsConfig`.

Preflight vẫn phải được CORS handling xử lý **trước yêu cầu authentication** bên trong integration, và WebTestClient test response headers như mục 8–10.

### 13.2. So sánh hai chiến lược

| Tiêu chí | Standalone `CorsWebFilter` | `ServerHttpSecurity.cors(...)` |
| --- | --- | --- |
| Vị trí | Global WebFilter trước Security proxy | CORS integration trong Security pipeline |
| CORS scope | Theo `CorsConfigurationSource`, có thể áp dụng trước nhiều chains | Theo Security integration và source |
| Ordering | `@Order` trên WebFilter bean | Framework quyết định vị trí trong Security chain |
| Functional endpoints | Rất phù hợp | Cũng phù hợp nếu routes thuộc security chains |
| Rủi ro phổ biến | Không đăng ký filter/đặt order sai, trùng với Security CORS | Quên source hoặc config, chain không match |
| Test bắt buộc | Preflight không auth + CORS headers + no side effects | Tương tự, và kiểm tra chain isolation |

Chọn một kiến trúc, tài liệu hóa nơi policy được khai báo, và dùng tests làm bằng chứng. Đừng đưa `.cors(cors -> cors.disable())` từ fixture standalone sang biến thể Security-managed rồi không tạo filter khác; lúc đó CORS có thể không được xử lý đúng.

### 13.3. `@CrossOrigin`/`WebFluxConfigurer` không luôn xử lý được preflight trước Security

`HandlerMapping` xử lý CORS ở tầng routing/handler. Nếu Security yêu cầu authentication **trước** khi tới HandlerMapping, một preflight không credential có thể bị chặn. Khi dùng WebFlux Security, tài liệu Spring khuyến nghị CORS processing **trước Security** qua `CorsWebFilter` hoặc integration tương đương.

Tương tự, `@CrossOrigin` trên controller POST không nhất thiết giải quyết tình huống một global Security filter đã trả 401 cho preflight trước khi controller mapping chạy. Test phản hồi trên URL thực, không chỉ nhìn annotation.

## 14. Test unit `CorsUtils`: preflight matcher hoạt động ra sao?

Trước khi debug Security, có thể xác minh input HTTP thực sự được coi là CORS preflight. `CorsUtils.isPreFlightRequest` là công cụ nhỏ nhưng hữu ích để phân biệt OPTIONS thông thường với preflight.

### 14.1. Unit test ba header cần thiết

```java
import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.web.cors.reactive.CorsUtils;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CorsUtilsPreflightTest {

    @Test
    void optionsWithOriginAndRequestedMethodIsPreflight() {
        var request = MockServerHttpRequest.options("/api/orders")
            .header("Origin", "https://app.example.com")
            .header("Access-Control-Request-Method", "POST")
            .build();

        assertTrue(CorsUtils.isPreFlightRequest(request));
    }

    @Test
    void optionsWithoutOriginIsNotPreflight() {
        var request = MockServerHttpRequest.options("/api/orders")
            .header("Access-Control-Request-Method", "POST")
            .build();

        assertFalse(CorsUtils.isPreFlightRequest(request));
    }

    @Test
    void optionsWithoutRequestedMethodIsNotPreflight() {
        var request = MockServerHttpRequest.options("/api/orders")
            .header("Origin", "https://app.example.com")
            .build();

        assertFalse(CorsUtils.isPreFlightRequest(request));
    }

    @Test
    void postWithPreflightHeadersStillIsNotPreflight() {
        var request = MockServerHttpRequest.post("/api/orders")
            .header("Origin", "https://app.example.com")
            .header("Access-Control-Request-Method", "POST")
            .build();

        assertFalse(CorsUtils.isPreFlightRequest(request));
    }
}
```

Tests này xác minh **hình dạng request**, không xác minh origin/method/header có được **policy** cho phép. Một request có thể đúng dạng preflight nhưng vẫn bị `CorsWebFilter` từ chối do allowed origins/methods/headers.

### 14.2. Không tự viết CORS matcher quá chặt

Sai lầm thường gặp: code tự kiểm tra `Origin`, `Access-Control-Request-Method` **và** bắt buộc `Access-Control-Request-Headers`. Browser có thể gửi preflight cho một actual method không có custom headers; matcher ấy sẽ bỏ sót request hợp lệ.

Ưu tiên `CorsUtils` và `CorsWebFilter` đã được Framework duy trì. Khi bắt buộc có custom `CorsProcessor`, viết tests bao phủ các trường hợp hợp lệ/thiếu header/malformed origin theo phiên bản.

## 15. Test `CorsWebFilter` cô lập bằng `MockServerWebExchange`

Đôi khi cần xác minh logic của **chính filter**, không có Spring Security hoặc router. Dùng `MockServerWebExchange` và một `WebFilterChain` test đếm số lần được gọi.

### 15.1. Preflight được filter xử lý, chain sau không chạy

```java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsWebFilter;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Test
void corsFilterShortCircuitsApprovedPreflight() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of("https://app.example.com"));
    config.setAllowedMethods(List.of("POST"));
    config.setAllowedHeaders(List.of("X-CSRF-TOKEN"));

    var source = new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", config);
    var filter = new CorsWebFilter(source);

    var exchange = MockServerWebExchange.from(
        MockServerHttpRequest.options("/api/orders")
            .header("Origin", "https://app.example.com")
            .header("Access-Control-Request-Method", "POST")
            .header("Access-Control-Request-Headers", "x-csrf-token")
    );

    AtomicInteger forwarded = new AtomicInteger();
    WebFilterChain next = ignored -> Mono.fromRunnable(
        forwarded::incrementAndGet);

    StepVerifier.create(filter.filter(exchange, next))
        .verifyComplete();

    assertEquals(0, forwarded.get());
    assertEquals(
        "https://app.example.com",
        exchange.getResponse().getHeaders()
            .getFirst("Access-Control-Allow-Origin"));
}
```

Test khẳng định filter nhận một preflight hợp lệ và **không gọi next WebFilterChain**. Nó không chứng minh bean filter này thực sự được đăng ký/đặt trước Security trong ứng dụng; phần đó được kiểm tra bằng integration test `bindToApplicationContext`.

### 15.2. Actual request được chuyển tiếp vào chain

```java
@Test
void corsFilterAllowsValidActualGetToReachNextFilter() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of("https://app.example.com"));
    config.setAllowedMethods(List.of("GET"));

    var source = new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", config);
    var filter = new CorsWebFilter(source);

    var exchange = MockServerWebExchange.from(
        MockServerHttpRequest.get("/api/orders")
            .header("Origin", "https://app.example.com")
    );

    AtomicInteger forwarded = new AtomicInteger();
    WebFilterChain next = ignored -> Mono.fromRunnable(
        forwarded::incrementAndGet);

    StepVerifier.create(filter.filter(exchange, next))
        .verifyComplete();

    assertEquals(1, forwarded.get());
    assertEquals(
        "https://app.example.com",
        exchange.getResponse().getHeaders()
            .getFirst("Access-Control-Allow-Origin"));
}
```

Giữ nguyên source/processor concept nhưng đổi method. Một actual CORS request hợp lệ được gắn CORS headers và chuyển tới Security/controller; đây là hành vi **khác** preflight.

### 15.3. Origin bị từ chối không được gọi handler

```java
@Test
void corsFilterRejectsUnknownOriginWithoutCallingNext() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of("https://app.example.com"));
    config.setAllowedMethods(List.of("POST"));

    var source = new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", config);
    var filter = new CorsWebFilter(source);

    var exchange = MockServerWebExchange.from(
        MockServerHttpRequest.options("/api/orders")
            .header("Origin", "https://attacker.example")
            .header("Access-Control-Request-Method", "POST")
    );

    AtomicInteger forwarded = new AtomicInteger();
    WebFilterChain next = ignored -> Mono.fromRunnable(
        forwarded::incrementAndGet);

    StepVerifier.create(filter.filter(exchange, next))
        .verifyComplete();

    assertEquals(0, forwarded.get());
    assertEquals(
        org.springframework.http.HttpStatus.FORBIDDEN,
        exchange.getResponse().getStatusCode());
}
```

Nhớ đây là unit test của `CorsWebFilter` + `DefaultCorsProcessor`. Với một custom processor, semantics status/body có thể khác; hãy test hợp đồng của processor đó.

## 16. CORS có credentials và cookie: preflight ≠ session validation

### 16.1. Các browser origins khác nhau có thể cùng site

`https://app.example.com` và `https://api.example.com` là **khác origin**, nhưng thường **cùng site** theo mô hình schemeful same-site nếu cùng scheme và registrable domain. Một cookie host-only của `api.example.com` có thể được gửi về API khi browser policy cho phép, nhưng JavaScript tại `app.example.com` **không thể đọc** cookie host-only đó bằng `document.cookie`.

Với frontend cross-origin:

```javascript
const response = await fetch(
  "https://api.example.com/api/orders",
  {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-TOKEN": csrfTokenFromApi
    },
    body: JSON.stringify({sku: "BOOK-01", quantity: 1})
  }
);
```

`csrfTokenFromApi` là giá trị phải được frontend lấy từ endpoint/view tin cậy theo CSRF repository/handler của API, **không phải string hard-code**. Browser có thể gửi OPTIONS trước POST, sau đó gửi cookie nếu `credentials`, `SameSite`, `Secure` và origin policy phù hợp.

### 16.2. Khác origin khác với cross-site

Nếu SPA chạy tại `https://shop-another-site.example` và API ở một registrable domain khác, browser có thể coi request là **cross-site**, khiến cookie `SameSite=Lax/Strict` không được gửi trong `fetch`. `SameSite=None; Secure` có thể cần thiết cho một số flow, nhưng third-party cookie restrictions vẫn có thể chặn.

Không tăng `allowCredentials` hay mở `allowedOrigins` tùy tiện để chữa cookie bị browser loại. Phải kiểm tra request cookie trong browser Network panel và policy ở server.

### 16.3. `Access-Control-Allow-Credentials` không thay CSRF

Một preflight được phép với `Access-Control-Allow-Credentials: true` **không có nghĩa**:

- Browser gửi session cookie ở preflight.
- Browser có authenticated session cho actual POST.
- Client có CSRF token hợp lệ.
- API đã authorize quyền tạo đơn.
- Cookie được cấp phép đọc bởi JavaScript.

Test những trách nhiệm này thành các bước độc lập. Với WebFlux CSRF, default `WebSessionServerCsrfTokenRepository` lưu expected token trong WebSession; SPA thường lấy exposed token qua `GET /csrf` và gửi header tương ứng cùng cookie `SESSION`.

### 16.4. Bearer-only API và CORS

Khi API thực sự dùng Bearer token được JavaScript gửi chủ động, browser có thể phải preflight vì header `Authorization`:

```http
OPTIONS /api/orders HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
```

Với token Bearer được người gọi tự gắn (không tự dùng cookie browser), quyết định miễn CSRF ở **một chain hẹp** cần threat-model review; nhưng **CORS vẫn cần cấu hình**. Đừng để `SecurityWebFilterChain` của API chặn OPTIONS preflight thiếu Bearer token.

Nếu app có **cả** Bearer API và browser session routes, đừng miễn CSRF cho toàn ứng dụng vì một API path. Một `/api/**` matcher rộng sẽ được review khác với một browser fallback chain.

## 17. Nhiều `SecurityWebFilterChain`: preflight thuộc chain nào?

Spring Security WebFlux có thể chọn một `SecurityWebFilterChain` trong nhiều chains theo `@Order` và `securityMatcher`. Một global `CorsWebFilter` đứng trước Security có thể xử lý preflight **độc lập với việc chain nào sẽ được chọn sau đó**, miễn CORS source có policy khớp URI.

### 17.1. Ví dụ chain API và browser fallback

```java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Bean
@Order(1)
SecurityWebFilterChain apiBearer(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            ServerWebExchangeMatchers.pathMatchers("/api/**"))
        .authorizeExchange(auth -> auth
            .anyExchange().authenticated())
        .cors(cors -> cors.disable()) // Global CorsWebFilter xử lý trước.
        // Chỉ nếu API thực sự Bearer-only, không dùng cookie credentials:
        .csrf(csrf -> csrf.disable())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults()))
        .build();
}

@Bean
@Order(2)
SecurityWebFilterChain browserFallback(ServerHttpSecurity http) {
    return http
        .authorizeExchange(auth -> auth
            .pathMatchers("/public/**").permitAll()
            .anyExchange().authenticated())
        .cors(cors -> cors.disable())
        .csrf(Customizer.withDefaults())
        .formLogin(Customizer.withDefaults())
        .build();
}
```

Ví dụ này **thay thế** fixture một chain `ReactiveSecurityConfig`, không dùng cùng lúc. Resource Server cần dependencies/JWT decoder phù hợp; minh họa không phải một ứng dụng đầy đủ đã cấu hình issuer. `csrf.disable()` chỉ chấp nhận cho API thực sự không dựa vào browser auto-attached credentials, sau threat-model review.

### 17.2. Filter ordering có hai lớp

```text
Global WebFlux WebFilters:
  @Order(HIGHEST_PRECEDENCE) CorsWebFilter
              |
              v
  Spring Security WebFilterChainProxy
              |
              +-- @Order(1): /api/** -> Bearer/JWT chain
              |
              +-- @Order(2): fallback -> browser session/CSRF chain
              |
              v
     HandlerMappings / controllers
```

`@Order` trên **global WebFilter bean** khác `@Order` trên **SecurityWebFilterChain bean**. Thêm `@Order(1)` cho API chain không tự đảm bảo CORS được chạy trước Security; đó là trách nhiệm của global filter order hoặc Security CORS integration.

### 17.3. Regression test theo route type

| Request | CORS policy | Security policy sau preflight |
| --- | --- | --- |
| OPTIONS `/api/orders` from allowed SPA | Preflight 200 + headers, không JWT | Actual API cần Bearer |
| GET `/api/orders` no Bearer | CORS headers nếu Origin allowed | 401 |
| GET `/api/orders` Bearer invalid | CORS vẫn xử lý | 401 theo decoder |
| POST `/api/orders` Bearer scope thiếu | CORS không quyết định scope | 403 authorization |
| OPTIONS `/public/ping` from SPA | Source `/api/**` không match: có thể 200 không ACAO | Browser không cho script đọc cross-origin |
| POST `/orders` dùng browser session | Source `/api/**` không match | Fallback CSRF phải bảo vệ |

Nếu thêm API chain với matcher `/**`, nó có thể bắt nhầm browser routes và thay đổi CSRF policy. CORS preflight có thể vẫn pass do global filter, trong khi actual POST vào **sai chain**. Vì vậy cần test toàn bộ hai giai đoạn và fallback, không chỉ OPTIONS.

### 17.4. Preflight được cấp quyền cho URL chưa có handler?

CORS filter hoạt động **trước routing**. Nếu `UrlBasedCorsConfigurationSource` đăng ký `/api/**`, `OPTIONS /api/not-yet-implemented` vẫn có thể trả allowed CORS headers dù **không có controller** xử lý actual POST. Browser sau đó gửi actual request và server có thể trả 404. Do vậy:

- Preflight 200 chứng minh **CORS policy cho path/method/header**.
- Nó không chứng minh endpoint tồn tại.
- Cần actual GET/POST test tới handler cụ thể, cùng authorization/CSRF controls.

## 18. Test slice `@WebFluxTest` và full-context `@SpringBootTest`

### 18.1. Test slice cần import `CorsWebFilter` và security config

`@WebFluxTest` của Spring Boot có phạm vi web slice; nó không bảo đảm **mọi custom global `WebFilter`, `SecurityWebFilterChain` hoặc `CorsConfigurationSource`** của app được nạp giống full runtime.

Ví dụ **Spring Boot 3.5 imports**:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@WebFluxTest(OrdersController.class)
@Import({
    ReactiveCorsPolicyConfig.class,
    ReactiveCorsWebFilterConfig.class,
    ReactiveSecurityConfig.class,
    CorsSliceTest.CounterBeans.class
})
class CorsSliceTest {

    @TestConfiguration
    static class CounterBeans {
        @Bean OrderCounter counter() {
            return new OrderCounter();
        }
    }

    @Autowired ApplicationContext context;
    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void preflightStillBypassesAuthenticationInSlice() {
        client.options().uri("/api/orders")
            .header("Origin", "https://app.example.com")
            .header("Access-Control-Request-Method", "POST")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                "Access-Control-Allow-Origin",
                "https://app.example.com");
    }
}
```

Trong slice, import đúng Security và CORS configs của application. Nếu một filter/bean chỉ được tạo trong Boot auto-config mà không có trong slice, test có thể sai lệch production. Trường hợp không khôi phục được wiring trong slice, dùng full-context test để kiểm tra integration.

### 18.2. Boot 4 thay đổi package test annotations

```java
// Boot 4.x:
import org.springframework.boot.webflux.test.autoconfigure.WebFluxTest;
import org.springframework.boot.webtestclient.autoconfigure.AutoConfigureWebTestClient;

// Boot 3.5:
// org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest
// org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient
```

Không copy cả hai nhóm imports vào cùng class. Kiểm tra đúng Spring Boot migration reference/test starters của bản đã chọn.

### 18.3. Full context nhưng chưa chắc có TCP server

```java
@SpringBootTest
class CorsFullContextTest {
    @Autowired ApplicationContext context;

    @Test
    void preflightIsHandledBeforeAuthentication() {
        WebTestClient client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();

        client.options().uri("/api/orders")
            .header("Origin", "https://app.example.com")
            .header("Access-Control-Request-Method", "POST")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                "Access-Control-Allow-Origin",
                "https://app.example.com");
    }
}
```

`@SpringBootTest` mặc định không có nghĩa đã mở một cổng HTTP. `bindToApplicationContext` vẫn là mock server adapter; nó kiểm tra full wiring tốt nhưng chưa thử Reactor Netty/TLS termination/gateway.

## 19. HTTP server thật: thử OPTIONS bằng WebTestClient hoặc curl

### 19.1. `RANDOM_PORT` cho WebFlux

Với một Spring Boot WebFlux app/test profile khai báo các beans ở mục 6–7:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class CorsLiveHttpTest {

    @Autowired WebTestClient http;

    @Test
    void preflightOverRealHttpDoesNotNeedCredentials() {
        http.options().uri("/api/orders")
            .header("Origin", "https://app.example.com")
            .header("Access-Control-Request-Method", "POST")
            .header(
                "Access-Control-Request-Headers",
                "content-type,x-csrf-token")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                "Access-Control-Allow-Origin",
                "https://app.example.com")
            .expectHeader().valueEquals(
                "Access-Control-Allow-Credentials", "true");
    }
}
```

Boot 4 dùng `org.springframework.boot.webtestclient.autoconfigure.AutoConfigureWebTestClient`. Test `RANDOM_PORT` đi qua HTTP adapter thật nhưng không tự đi qua public gateway, CDN hoặc browser engine. `@WithMockUser`/`mockUser()` không tự đưa credential qua TCP; điều đó **không cần thiết cho preflight** và với actual requests phải dùng HTTP credentials/session thực.

### 19.2. Dùng curl quan sát response (không thay browser test)

```bash
curl -i -X OPTIONS 'https://api.example.com/api/orders' \
  -H 'Origin: https://app.example.com' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,x-csrf-token'
```

Kỳ vọng: status 2xx, `Access-Control-Allow-Origin` chính xác, allow-methods chứa POST, allow-headers cho phép content-type/x-csrf-token, allow-credentials nếu policy cần, `Vary` và `Max-Age` theo config.

Thử đổi origin:

```bash
curl -i -X OPTIONS 'https://api.example.com/api/orders' \
  -H 'Origin: https://attacker.example' \
  -H 'Access-Control-Request-Method: POST'
```

Kỳ vọng: bị từ chối **hoặc không có allow-origin** theo policy/processor/edge, tuyệt đối không cấp header chia sẻ credentials cho origin đó.

**Giới hạn:** curl không áp dụng SOP, không tự preflight theo Fetch và không thực thi browser SameSite/CSP/HSTS behavior. Một response 200 qua curl nhưng thiếu allow-origin vẫn bị browser chặn.

### 19.3. Kiểm tra actual request sau preflight

Đối với HTTP Basic test fixture, actual GET cần gửi credential thật:

```bash
curl -i 'https://api.example.com/api/orders' \
  -H 'Origin: https://app.example.com' \
  -u 'alice:for-tests-only'
```

Chỉ dùng **test credentials trên môi trường test**, không dùng password thật trong lệnh shell hoặc CI logs. Trong production nên dùng một token test được quản lý an toàn hoặc browser session. Thử actual POST cần CSRF token hợp lệ của đúng repository/WebSession; thêm `Origin` chỉ cấp phép CORS chứ không giải quyết CSRF.

### 19.4. Browser E2E mới xác nhận thực tế Fetch/CORS

Trên staging HTTPS có SPA và API đúng origins, dùng browser automation hoặc DevTools Network:

1. Mở SPA từ origin dự kiến.
2. Gửi fetch POST JSON có custom CSRF header (và credentials khi cần).
3. Kiểm tra Network có OPTIONS preflight thật.
4. Quan sát preflight headers được browser chấp thuận.
5. Kiểm tra actual POST có được gửi, cookie/header có đến đúng đích không.
6. Thử origin không có trong allowlist ở test environment được kiểm soát.
7. Kiểm tra CSP của trang HTML và HSTS trên HTTPS hostname độc lập.

Không để devtools screenshots/logs chứa raw CSRF tokens, JWTs, session cookies hoặc password nếu đưa vào tài liệu/CI reports.

## 20. Cache, `Vary`, max-age và reverse proxy

### 20.1. Browser có thể cache kết quả preflight

`CorsConfiguration.setMaxAge(3600L)` khai báo:

```http
Access-Control-Max-Age: 3600
```

Giá trị tính bằng **giây**, cho phép browser cache kết quả preflight trong giới hạn do browser áp đặt. Nó **không** cache authentication token, session cookie, actual POST response hoặc CSRF token; không đồng nghĩa policy đã được browser công nhận vĩnh viễn.

Nếu vừa đổi CORS allowlist nhưng browser đã cache kết quả preflight, hành vi quan sát có thể khác giữa tab/profile; vì thế khi debug cần kiểm tra browser cache, dùng session mới hoặc thay URL có kiểm soát. Không nới toàn bộ policy chỉ để chữa cache của một client.

### 20.2. `Vary` bảo vệ shared caches khỏi trả nhầm response

Response có thể khác theo:

- `Origin`.
- `Access-Control-Request-Method`.
- `Access-Control-Request-Headers`.

`DefaultCorsProcessor` thêm `Vary` tương ứng trong nhiều dòng Spring Framework. Proxy/CDN có thể gộp hoặc lọc headers; nếu vô tình bỏ `Vary`, edge có thể cache một preflight response của origin A rồi phục vụ origin B, làm browser từ chối hoặc tạo kết quả không nhất quán.

Test cả CORS headers của **hai origins** (allowlisted và denied) qua gateway và kiểm tra `Vary` trên đường public, không chỉ mock context.

### 20.3. CORS headers do gateway và app cùng sinh

```text
Browser OPTIONS
    |
    v
CDN/WAF/Ingress
  có thể tự xử lý OPTIONS hoặc thêm ACAO
    |
    v
Spring CorsWebFilter
  cũng thêm ACAO/Vary nếu request tới app
    |
    v
SecurityWebFilterChain
```

Hai lớp cùng phát `Access-Control-Allow-Origin` với giá trị trùng hoặc khác nhau có thể khiến browser reject vì response không hợp lệ. Trên staging hãy xác định **một CORS policy owner**; nếu gateway xử lý hoàn toàn preflight, app CORS tests vẫn hữu ích cho internal entrypoint nhưng **không đủ** cho public behavior.

**Không dựa vào `curl` trực tiếp gọi pod để kết luận cấu hình public edge**. Test public URL, giữ `Origin`/requested headers và kiểm tra toàn response.

### 20.4. Forwarded headers và origin comparison

Sau TLS termination, Spring app có thể thấy:

```text
Public URL:  https://api.example.com/api/orders
Backend:    http://service:8080/api/orders
Origin:     https://app.example.com
```

Với origin khác host, CORS policy cần khớp `https://app.example.com`; nếu app có redirects, same-origin checks hoặc xây URLs từ request, **trusted forwarded headers** có thể ảnh hưởng scheme/host/port mà Spring quan sát. Cấu hình `server.forward-headers-strategy` theo Boot version và chỉ tin headers từ proxy được kiểm soát; không tin `X-Forwarded-*` tùy ý từ Internet.

Nếu security chain dùng `securityMatcher("/api/**")` nhưng proxy strip prefix thành `/orders`, CORS source cũng có thể không match `/api/**`. Thử URL public và URL nội bộ đúng thứ tự.

### 20.5. `Access-Control-Request-Private-Network` là trường hợp mở rộng

Một số trình duyệt/tiêu chuẩn mới có yêu cầu preflight khi website public truy cập tài nguyên private network. Spring Framework một số phiên bản hỗ trợ `allowPrivateNetwork`/`Access-Control-Allow-Private-Network`, nhưng behavior phụ thuộc Framework/browser và policy.

Đừng bật tính năng này theo wildcard vì một preflight local bị chặn. Nếu hệ thống thực sự cần truy cập private network từ browser, kiểm tra version và threat model, cấu hình origin cụ thể và viết tests riêng cho PNA. Nó không thay CORS/CSRF/authentication thông thường của ứng dụng.

## 21. Chẩn đoán 400/401/403/404/405 quanh OPTIONS và CORS

Một HTTP status đơn lẻ **không cho biết** request bị chặn ở CorsWebFilter, Security, firewall, handler hay gateway. Cách chẩn đoán là giữ nguyên URL/headers và thay một yếu tố mỗi lần.

### Lỗi A — Preflight hợp lệ nhận 401

**Nguyên nhân phổ biến:** `CorsWebFilter` chưa đăng ký, thứ tự chạy sau `WebFilterChainProxy`, Security CORS integration chưa được bật, hoặc gateway yêu cầu authentication trước khi chuyển request.

**Chẩn đoán:** gửi OPTIONS gồm `Origin` và `Access-Control-Request-Method`, không cookie. Nếu 401, kiểm tra global WebFilter beans/order và public ingress. Đừng sửa bằng `csrf.disable()` hoặc `permitAll("/api/**")` cho actual POST.

### Lỗi B — Preflight nhận 200 nhưng browser vẫn báo CORS

**Khả năng:** thiếu `Access-Control-Allow-Origin`, allow-methods không chứa actual method, allow-headers thiếu custom header, hoặc credentials policy không phù hợp. Trường hợp `CorsConfigurationSource` trả `null` có thể tạo 200 **mà không có CORS headers**.

**Khắc phục:** assert response headers đầy đủ, không chỉ HTTP status. Kiểm tra source path và Origin chính xác.

### Lỗi C — Preflight nhận 403 khi origin có vẻ “giống” nhau

**Khả năng:** khác scheme (`http`/`https`), port, host/subdomain, origin `null`, typo hoặc policy không match. Header `Origin` không chứa URL path; không cấu hình path trong `allowedOrigins`.

**Khắc phục:** so Origin hiện có trong browser Network với allowlist, kiểm tra case/port và public URL. Không mở wildcard origins cho credentialed session.

### Lỗi D — GET được nhưng POST bị 403 CORS

**Khả năng:** CORS source chỉ cho phép GET, không cho phép POST, hoặc actual POST yêu cầu header `X-CSRF-TOKEN`/`Content-Type` chưa nằm trong `allowedHeaders`. Cần xem 403 xảy ra ở **OPTIONS preflight** hay **actual POST**.

**Khắc phục:** kiểm tra từng request trong Network, allowed methods/requested headers và POST CSRF/authorization. Một POST 403 sau preflight 200 có thể đến từ CSRF, không còn là lỗi CORS.

### Lỗi E — Thêm `permitAll()` cho OPTIONS vẫn không có ACAO

**Giải thích:** authorization `permitAll()` chỉ quyết định Spring Security có chặn hay không. Nó **không** tự tạo `Access-Control-Allow-Origin`/allow-headers/credentials cho browser.

**Khắc phục:** cấu hình đúng `CorsWebFilter` hoặc Security CORS integration và test response headers.

### Lỗi F — OPTIONS thiếu `Access-Control-Request-Method` trả 401

**Giải thích:** request đó **không được `CorsUtils` nhận diện là preflight**. Nếu path protected, Security xử lý actual OPTIONS như request bình thường và có thể trả 401.

**Khắc phục:** test harness/curl phải gửi đủ preflight headers; đừng gán tất cả OPTIONS 401 cho filter order.

### Lỗi G — Browser gửi `authorization` nhưng preflight header không được phép

**Nguyên nhân:** `allowedHeaders` thiếu `Authorization`. Browser thường preflight khi actual request dùng Bearer header cross-origin.

**Khắc phục:** thêm `Authorization` vào allowlist ở đúng API path; vẫn giữ JWT issuer/audience/signature/scope validation ở Security. Allowed header **không phải cấp quyền** dùng Bearer token tùy ý.

### Lỗi H — `Access-Control-Allow-Credentials` có nhưng cookie không đến API

**Nguyên nhân:** frontend thiếu `credentials: "include"`, cookie `SameSite/Domain/Path/Secure` không hợp, third-party cookie restrictions, session hết hạn hoặc HTTPS scheme mismatch.

**Khắc phục:** kiểm tra browser Request Cookies/Set-Cookie và public origin. Đừng sửa bằng wildcard origin hoặc tắt CSRF.

### Lỗi I — Response chứa hai `Access-Control-Allow-Origin`

**Nguyên nhân:** gateway/CDN và Spring cùng thêm headers, hoặc standalone `CorsWebFilter` và Security CORS integration/`@CrossOrigin` cùng xử lý không được kiểm soát.

**Khắc phục:** xác định CORS owner, loại đăng ký trùng, test public response với một giá trị allow-origin hợp lệ. Không coi hai lớp CORS như hai lớp phòng thủ luôn an toàn hơn.

### Lỗi J — `@CrossOrigin` trên controller mà preflight vẫn 401

**Nguyên nhân:** Security chặn request **trước HandlerMapping** nơi annotation xử lý. Với functional routes hoặc global security, rule handler-level có thể không giải quyết ordering.

**Khắc phục:** chuyển CORS processing trước Spring Security qua `CorsWebFilter` hoặc `ServerHttpSecurity.cors(...)`, rồi kiểm tra preflight không auth.

### Lỗi K — GET cùng origin hoạt động, cross-origin không có ACAO

**Giải thích:** same-origin request không cần CORS response headers. Cross-origin cần policy khớp. Việc GET cùng host không có ACAO không mặc nhiên là bug.

**Khắc phục:** test với `Origin` đúng khác origin và so allowed/unallowed origins; tránh phát ACAO cho mọi request vô điều kiện.

### Lỗi L — OPTIONS bị 404 hoặc 405

**Nguyên nhân có thể:** request chưa tới `CorsWebFilter` hoặc bị gateway/router xử lý, CORS source không active, hoặc request không phải preflight. Một preflight hợp lệ qua active `CorsWebFilter` thường được filter short-circuit **không cần OPTIONS controller**.

**Khắc phục:** kiểm tra Origin/ACRM headers, global filter registration và ingress OPTIONS handling.

### Lỗi M — OPTIONS có header lạ và bị 403

`Access-Control-Request-Headers` liệt kê headers browser dự kiến gửi; nếu một header không được `allowedHeaders` chấp thuận, `DefaultCorsProcessor` sẽ từ chối preflight.

**Khắc phục:** kiểm tra frontend có thật sự cần header đó không; chỉ cho phép danh sách tối thiểu thay vì dùng `"*"` khi không cần thiết.

### Lỗi N — OPTIONS từ origin không có config trả 200 nhưng không có ACAO

**Giải thích:** source không tìm được policy có thể trả `null`. Filter vẫn short-circuit preflight trong khi processor không thêm allow-origin.

**Khắc phục:** xác nhận `registerCorsConfiguration` đúng path; **không kỳ vọng mọi deny đều 403**.

### Lỗi O — Preflight pass nhưng actual POST không xuất hiện

**Khả năng:** browser đánh giá một CORS header không hợp lệ, credentials mismatch, redirect preflight, mixed-content policy, fetch bị cancel, CSP `connect-src` không cho gọi API hoặc network block.

**Khắc phục:** xem browser Console + Network, CSP trên HTML, redirect/HTTPS, và đối chiếu headers. Một curl preflight 200 không đủ để suy browser sẽ gửi POST.

### Lỗi P — Preflight pass nhưng actual POST trả 403

**Khả năng:** CSRF token thiếu/sai, session cookie không được gửi, user thiếu role, JWT scope không đủ, HTTP firewall hoặc custom access-denied handler.

**Khắc phục:** làm positive/negative controls cho authentication và CSRF sau khi CORS đã pass. Không gộp “CORS 403” với “CSRF 403”.

### Lỗi Q — HSTS/CSP mất sau chỉnh CORS

**Giải thích:** CORS filter không tự tạo CSP/HSTS. HSTS phải được browser nhận qua HTTPS public; CSP chủ yếu phải đặt trên HTML document owner. Nếu preflight được xử lý trước Security, không suy mọi default Security headers sẽ xuất hiện trên preflight response.

**Khắc phục:** test CSP/HSTS/nosniff trên các response thích hợp riêng, không bắt buộc OPTIONS preflight phải mang toàn bộ Security headers của actual response.

### Lỗi R — Chạy trên staging tốt, production origin khác

**Khả năng:** environment allowlist sai, public domain/port thay đổi, TLS termination, forwarded headers không được tin đúng, path prefix rewrite hoặc CDN cache.

**Khắc phục:** source allowlist theo deployment env được validate fail-closed; smoke test public URL và origins cụ thể trước canary.

### Lỗi S — Test `@WebFluxTest` xanh, `RANDOM_PORT` đỏ

**Khả năng:** test slice chưa nạp custom global filter hoặc nạp một source khác, Boot full runtime có filter order khác, gateway chưa được test, hoặc test-only profile khác production.

**Khắc phục:** xác minh application context/bean selection, chạy full-context test và real HTTP test cho cùng policy; không tự thêm mock principal vào preflight để chữa.

### Lỗi T — Vary/max-age bất nhất khi qua CDN

**Khả năng:** CDN cache preflight không tôn trọng `Vary` hoặc tự override `Access-Control-Max-Age`, response ACAO của origin khác bị phục vụ nhầm.

**Khắc phục:** test hai Origin/requested methods với cùng URL qua edge, xác nhận Vary/cache-key, không log raw credentials.

## 22. Ma trận kiểm thử hồi quy CORS preflight

| ID | Request/điều kiện | Kết quả cần xác minh |
| --- | --- | --- |
| C01 | OPTIONS `/api/orders`, Origin allowlisted, ACRM POST | 2xx, ACAO đúng |
| C02 | C01 + ACRH `content-type,x-csrf-token` | ACA-Headers cho phép cả hai |
| C03 | C01 không cookie/auth/CSRF | Vẫn thành công |
| C04 | C01 + `Access-Control-Max-Age` đã cấu hình | Header max-age đúng |
| C05 | C01, kiểm tra `Vary` | Origin, requested method, requested headers |
| C06 | Origin `https://attacker.example` | 403 hoặc không ACAO theo policy |
| C07 | Origin `http://app.example.com` | Bị từ chối |
| C08 | Origin `https://app.example.com:8443` | Bị từ chối |
| C09 | Origin literal `null` | Bị từ chối theo allowlist |
| C10 | ACRM DELETE không được phép | 403 |
| C11 | ACRH `x-internal-admin` không được phép | 403 |
| C12 | OPTIONS có Origin nhưng không ACRM | **Không là preflight**, Security/routing quyết định |
| C13 | OPTIONS có ACRM nhưng không Origin | **Không là preflight** |
| C14 | POST mang Origin/ACRM headers | Không là preflight vì không phải OPTIONS |
| C15 | Preflight `/public/ping` không match CORS source | Không ACAO dù có thể 200 |
| C16 | OPTIONS allowed, count controller side effect | Không chạy controller |
| C17 | Actual GET allowed Origin nhưng anonymous | Auth 401, có thể có ACAO |
| C18 | Actual GET allowed Origin + valid mock user | 200 + ACAO |
| C19 | Actual GET Origin không được phép | CORS reject, không ACAO |
| C20 | Actual POST allowed Origin + user thiếu CSRF | 403, không side effect |
| C21 | Actual POST allowed Origin + user/CSRF test valid | Handler chạy, headers đúng |
| C22 | CORS processor unit: preflight allowed | Không gọi next chain |
| C23 | CORS processor unit: actual GET allowed | Gọi next chain |
| C24 | CORS processor unit: untrusted Origin | 403, không gọi next |
| C25 | API Bearer header `Authorization` | Preflight cho requested header, actual auth riêng |
| C26 | Browser session frontend cross-origin | Credential/include và cookie policy đúng |
| C27 | Hai security chains: API và fallback | CORS xử lý trước, actual chain đúng |
| C28 | `@WebFluxTest` với CORS filter import | Có cùng policy như full app |
| C29 | `RANDOM_PORT` / curl qua HTTP thật | Response CORS headers phù hợp |
| C30 | Browser HTTPS qua CDN/ingress | Preflight/actual requests, redirects và `Vary` đúng |

### 22.1. Bộ test tối thiểu cần có trong CI

Một bộ tối thiểu để phát hiện regression khi thay Spring Security, CORS policy hoặc route:

1. **Positive preflight no-cookie:** OPTIONS + Origin/ACRM/ACRH allowed nhận 2xx cùng headers.
2. **Negative origin:** origin lạ **không được cấp ACAO**.
3. **Negative method/header:** actual method hoặc requested header bị cấm nhận deny.
4. **Missing mapping:** URL không có CORS source không vô tình được phép.
5. **Actual authentication:** allowed Origin không bỏ qua 401.
6. **Actual CSRF:** allowed Origin không bỏ qua POST CSRF.
7. **No side effects:** preflight và denied POST không tạo order.
8. **Staging browser:** xác nhận cookie, CSP/HTTPS, gateway và Vary theo deployment.

### 22.2. Khi nào dừng release?

Nếu một origin không tin cậy được cấp `Access-Control-Allow-Origin` **cùng `Access-Control-Allow-Credentials: true`** trên tài nguyên nhạy cảm, cần điều tra trước release. Tương tự, nếu một protected business endpoint trở nên publicly accessible vì đội phát triển “sửa preflight” bằng cách nới authentication/CSRF thay vì xử lý CORS ordering, đó là regression bảo mật cần dừng triển khai.

## 23. Bài tập thực hành

### Bài 1 — Viết `CorsWebFilter` đúng package

Tạo một Spring WebFlux app với `CorsWebFilter` bean, `UrlBasedCorsConfigurationSource` reactive và `SecurityWebFilterChain`. Chỉ allow origin `https://app.example.com`, GET/POST/OPTIONS và `Content-Type`/`X-CSRF-TOKEN`. Dùng `@Order(Ordered.HIGHEST_PRECEDENCE)` trên filter. Viết test preflight OPTIONS không cookie nhận ACAO đúng trong khi actual GET anonymous vẫn 401.

**Câu hỏi:** Vì sao `@Order` trên `SecurityWebFilterChain` không thay `@Order` trên global CORS WebFilter?

### Bài 2 — Định nghĩa và kiểm tra preflight

Viết bốn `CorsUtils.isPreFlightRequest` tests: OPTIONS đủ Origin+ACRM, OPTIONS thiếu Origin, OPTIONS thiếu ACRM, POST có cả hai headers. Không thêm `Access-Control-Request-Headers` vào điều kiện bắt buộc. Giải thích vì sao `OPTIONS /api/orders` chỉ có `Origin` có thể đi tiếp tới Security.

### Bài 3 — Cho phép POST nhưng từ chối DELETE

Với CORS source chỉ cho GET/POST/OPTIONS, thử OPTIONS ACRM POST và OPTIONS ACRM DELETE. Assert ACAO/methods được cấp cho POST; DELETE không được cấp. Sau đó tạo actual DELETE endpoint trong một fixture riêng và giải thích vì sao CORS không phải cơ chế authorization ngăn non-browser clients gọi DELETE.

### Bài 4 — Requested headers

Từ SPA, dùng POST JSON với `X-CSRF-TOKEN`. Viết preflight test khi `allowedHeaders` có cả `Content-Type`/`X-CSRF-TOKEN` rồi bỏ một header khỏi allowlist. Quan sát status/ACA-Headers và cách browser không gửi actual request khi preflight fail.

### Bài 5 — 200 nhưng không có ACAO

Đăng ký policy chỉ cho `/api/**`. Gửi OPTIONS `/public/ping` có Origin và ACRM. Kiểm tra response có thể 200 nhưng thiếu `Access-Control-Allow-Origin`. Viết assertion đúng về CORS permission thay vì chỉ assert status.

### Bài 6 — Filter short-circuit

Dùng `MockServerWebExchange`, `CorsWebFilter`, `WebFilterChain` có `AtomicInteger`. Cho allowed preflight đi qua và assert counter bằng 0; cho actual GET với Origin hợp lệ đi qua và assert counter bằng 1. Làm tiếp với origin bị cấm và xác nhận không gọi next chain.

### Bài 7 — CORS không thay authentication

Giữ `/api/orders` cần authentication HTTP Basic. Test preflight no-cookie pass, actual GET không auth 401, actual GET với `mockUser` 200 trong mock client. Với server thật, thay `mockUser` bằng Basic credentials ở HTTP layer. Vì sao preflight 200 không nên được xem như user đã đăng nhập?

### Bài 8 — CORS không thay CSRF

Giữ browser session `POST /api/orders` có CSRF enabled. Viết test actual POST authenticated nhưng thiếu CSRF token -> 403 và counter không tăng. Sau đó dùng `mutateWith(csrf())` cho mock positive control. Viết test token thật riêng khi dùng WebSession repo. Phân biệt CORS, authentication và CSRF.

### Bài 9 — Hai CORS strategies

Chạy fixture A với standalone `CorsWebFilter` global đứng trước Security, fixture B với `ServerHttpSecurity.cors(cors -> cors.configurationSource(...))` và **không có global filter bean**. Giữ cùng policy và chạy bộ test C01–C10. Trường hợp nào filter order hoặc bean wiring dễ bị hiểu nhầm hơn?

### Bài 10 — Nhiều security chains

Tạo `/api/**` Bearer-only chain và browser fallback. Giữ global `CorsWebFilter` xử lý OPTIONS trước Security, test API preflight không Bearer token pass, actual API GET thiếu Bearer nhận 401, browser POST vẫn yêu cầu CSRF. Đánh giá rủi ro nếu API chain matcher bị đổi thành `/**`.

### Bài 11 — Credentialed cross-origin SPA

SPA chạy `https://app.example.com`, API `https://api.example.com`. Viết `fetch` với `credentials: "include"` và token CSRF. Quan sát Network: OPTIONS thường không có cookie, actual POST có thể có cookie theo browser policy. So sánh trường hợp cookie host-only, `SameSite=Lax`, `Secure` và khác-site origin.

### Bài 12 — Vary, max-age và cache

Đặt `setMaxAge(3600L)`. Viết tests cho `Access-Control-Max-Age` và `Vary` semantic. Qua CDN staging, gửi hai preflight với origins/requested headers khác nhau nhưng cùng path; xác minh không có CORS headers của origin A lẫn vào origin B. Tại sao một chuỗi `Vary` cố định không nên là assertion duy nhất?

### Bài 13 — Gateway path rewrite

Public URL là `/gateway/api/orders`, app nhìn thấy `/api/orders`. Test preflight qua internal app và public ingress. Cấu hình một rewrite sai rồi xác định vì sao source `/api/**` không match và browser thấy OPTIONS 200 không ACAO hoặc 404 ở gateway.

### Bài 14 — Browser CSP và CORS

Trên staging, cố tình đặt CSP `connect-src 'self'` cho SPA rồi thử gọi API ở origin khác. Mặc dù CORS allowlist của API đúng, browser có thể không thực hiện fetch do CSP. Sửa CSP theo yêu cầu origin (giữ các directives còn lại chặt chẽ) và giải thích tại sao test `CorsWebFilter` không phát hiện lỗi ở HTML frontend.

## 24. Checklist review trước khi merge cấu hình CORS WebFlux

- [ ] Đã xác định **Reactive WebFlux**, không dùng Servlet `CorsFilter`/`CorsConfigurationSource` nhầm package.
- [ ] `CorsWebFilter`, `CorsUtils`, `UrlBasedCorsConfigurationSource` lấy từ `org.springframework.web.cors.reactive`.
- [ ] `CorsConfiguration` và các allowed lists được khai báo tường minh, version/framework dependencies tương thích BOM.
- [ ] Source `registerCorsConfiguration` match public/internal route sau proxy rewrite.
- [ ] Allowed origins là **scheme + host + port** chính xác; không đưa path vào origin.
- [ ] `allowCredentials(true)` chỉ dành cho các origins đáng tin và cần credentials.
- [ ] Không dùng `allowedOrigins("*")` với credentials; review kỹ `allowedOriginPatterns` và trusted subdomains.
- [ ] Allowed methods đủ cho API thực, không tự mở DELETE/PATCH nếu không dùng.
- [ ] Allowed request headers bao gồm đúng `Content-Type`, CSRF header, `Authorization` khi cần; tránh `*` vô tội vạ.
- [ ] `Access-Control-Expose-Headers` không bị nhầm với `Access-Control-Allow-Headers`.
- [ ] `Access-Control-Max-Age` và `Vary` được xét theo browser/proxy cache behavior.
- [ ] Preflight được xác định bằng OPTIONS + `Origin` + `Access-Control-Request-Method`; không bắt buộc ACRH.
- [ ] OPTIONS preflight hợp lệ không cần cookie, Basic, JWT, `mockUser` hoặc `csrf()`.
- [ ] `CorsWebFilter` đã đăng ký trước Spring Security nếu dùng standalone strategy.
- [ ] `@Order` trên global WebFilter được phân biệt với `@Order` trên SecurityWebFilterChain.
- [ ] Đã chọn **một** CORS owner: global filter **hoặc** Security DSL/handler-level strategy phù hợp.
- [ ] Nếu `ServerHttpSecurity.cors(...).disable()`, chắc chắn global CORS filter vẫn đang hoạt động.
- [ ] Có test positive preflight kiểm tra **CORS headers**, không chỉ 200.
- [ ] Có test origin lạ, scheme/port khác, method không cho phép, requested header lạ.
- [ ] Có test URL không match source: không ACAO dù OPTIONS có thể trả 200.
- [ ] Có test bare OPTIONS/Origin-only OPTIONS không bị nhận nhầm là preflight.
- [ ] Có test `Vary` tương thích nhiều header lines/comma-separated representation.
- [ ] Có assertion preflight không chạy controller/không tạo dữ liệu/không phát event.
- [ ] Actual GET từ allowed Origin vẫn yêu cầu authentication và authorization.
- [ ] Actual POST từ allowed Origin vẫn yêu cầu CSRF (khi dùng cookie/browser session).
- [ ] Test mock dùng `bindToApplicationContext(...).apply(springSecurity())` nếu cần cả Security pipeline.
- [ ] `@WebFluxTest` slice đã import CORS source/filter, Security config và dependencies của controller.
- [ ] Test full context hoặc `RANDOM_PORT` bổ sung cho nguy cơ khác biệt Boot auto-configuration.
- [ ] Browser/E2E chứng minh preflight do browser gửi và actual request chỉ xảy ra khi hợp lệ.
- [ ] Cookie `Secure`/`HttpOnly`/`SameSite`/`Domain`/`Path`, `fetch(credentials)` được kiểm tra độc lập.
- [ ] CSP `connect-src` trên HTML, HSTS/HTTPS và HTTP firewall có tests riêng.
- [ ] CDN/Ingress không thêm ACAO trùng, không làm mất `Vary` hoặc rewrite sai path.
- [ ] Không sử dụng CORS thay authentication, CSRF, role/scope checks hoặc endpoint allowlist.
- [ ] Logs/test artifacts không chứa session cookies, CSRF tokens, JWT, password hoặc dữ liệu nhạy cảm.

## 25. Tài liệu tham khảo chính thức

1. [Spring Framework — WebFlux CORS](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html) — xử lý CORS qua HandlerMapping, `CorsWebFilter`, credentials, origins, configuration và `@CrossOrigin`.
2. [Spring Framework 6.2 — WebFlux CORS (pinned)](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-cors.html) — đối chiếu thay đổi giữa các dòng Framework.
3. [Spring Security — Reactive CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html) — yêu cầu CORS chạy trước Security, `CorsConfigurationSource`, Security CORS integration.
4. [Spring Security 7.0 — Reactive CORS (pinned)](https://docs.spring.io/spring-security/reference/7.0/reactive/integrations/cors.html) — ví dụ cấu hình tương ứng Spring Security 7.
5. [Spring Framework API — CorsWebFilter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/cors/reactive/CorsWebFilter.html) — reactive WebFilter xử lý preflight và actual CORS requests.
6. [Spring Framework API — CorsUtils](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/cors/reactive/CorsUtils.html) — `isCorsRequest` và `isPreFlightRequest`.
7. [Spring Framework API — CorsConfiguration](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/cors/CorsConfiguration.html) — allowed origins/patterns, methods, headers, credentials, max-age, validations.
8. [Spring Framework API — Reactive UrlBasedCorsConfigurationSource](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/cors/reactive/UrlBasedCorsConfigurationSource.html) — CORS policy lookup theo URL patterns.
9. [Spring Framework API — Reactive DefaultCorsProcessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/cors/reactive/DefaultCorsProcessor.html) — xử lý/deny/response headers, cấu hình `null` và `Vary`.
10. [Spring Framework — WebFlux WebFilter ordering](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html) — filter beans, `@Order` và request pipeline.
11. [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html) — mock bind-to-controller/context, HTTP server binding và header assertions.
12. [Spring Security — WebFlux Security Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html) — `SecurityWebFilterChain`, multi-chain `securityMatcher` và `@Order`.
13. [Spring Security — Reactive Testing Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html) và [Reactive Testing with CSRF](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html) — `apply(springSecurity())`, mock principals và CSRF test mutator.
14. [Spring Security — Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html) — CSRF token khi dùng browser cookie/session.
15. [Spring Security — Reactive Security Headers](https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html) và [Reactive HTTP Firewall](https://docs.spring.io/spring-security/reference/reactive/exploits/firewall.html) — lớp phòng vệ khác CORS.
16. [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html) — `@WebFluxTest`, `@SpringBootTest`/`RANDOM_PORT` và test tooling theo version.
17. [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS) — browser CORS/preflight behavior, credentials, caching và hạn chế.
18. [Fetch Standard — CORS protocol](https://fetch.spec.whatwg.org/) — tiêu chuẩn diễn giải CORS protocol/preflight/cache và credentials mode.
19. [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html) — tại sao CORS không thay CSRF, token, SameSite và defense in depth.

**Tự đánh giá:** Vì sao preflight OPTIONS của browser thường không có cookie và không nên bị chặn bởi authentication? Ba thành phần bắt buộc để `CorsUtils.isPreFlightRequest` trả true là gì? `CorsWebFilter` xử lý preflight khác actual CORS request ra sao? Vì sao preflight status 200 vẫn có thể bị browser từ chối? Khi nào Origin khác scheme hoặc port phải bị xem là khác origin? `Access-Control-Allow-Headers` khác `Access-Control-Expose-Headers` thế nào? Nếu CORS allowed nhưng actual POST trả 403, làm sao phân biệt CSRF, authorization và CORS? Tại sao `@Order` của global CORS filter khác `@Order` của SecurityWebFilterChain? Khi gateway/cache trả ACAO sai, bạn sẽ kiểm tra `Vary`, path rewrite và chính sách nào? Và ngoài WebTestClient mock, cần những test HTTP/browser nào để xác nhận CORS cùng cookie, CSP/HSTS, TLS và session hoạt động đúng?
