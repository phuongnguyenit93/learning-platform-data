# Tích hợp spring-security-test với WebTestClient

> **Chương:** Kiểm thử Reactive  
> **Module:** `SPRING_SECURITY_HTTP_PROTECTION`  
> **Phạm vi:** Viết kiểm thử tích hợp cho **Spring Security WebFlux** bằng `spring-security-test` và `WebTestClient`, bảo vệ API/trình duyệt qua authentication, authorization, CSRF, CORS, security headers, CSP/HSTS, HTTP firewall, session và nhiều `SecurityWebFilterChain`.  
> **Định hướng phiên bản:** Các API được minh họa trên Spring Security **6.5/7.x**, Spring Framework Test và Spring Boot 3.5/4.x. Package của một số **Spring Boot test annotations** thay đổi từ Boot 3 sang Boot 4; kiểm tra dependency/BOM thực tế thay vì kết hợp các import từ nhiều dòng.

## 1. Vì sao cần `spring-security-test` khi kiểm thử WebFlux?

Một controller Reactive có thể trả `Mono<ResponseEntity<?>>` đúng và các unit test của service đều xanh, nhưng application vẫn có lỗ hổng HTTP:

- `GET /admin/reports` được xử lý dù người dùng không có `ROLE_ADMIN`.
- `POST /orders` dùng session cookie được chấp nhận khi thiếu CSRF token.
- OPTIONS CORS preflight bị 401 trước khi browser gửi POST thực.
- API JWT map scope `orders:write` thành authority sai.
- Response HTML thiếu CSP/HSTS, hoặc frontend bị chặn vì CSP/CORS xung đột.
- URL lạ như `/admin;v=1/reports` đi qua router và matcher khác nhau.
- `SecurityWebFilterChain` của API chọn nhầm request browser, khiến session và CSRF bị áp sai.

Để bắt những lỗi này, test không chỉ gọi handler mà phải chạy **đúng chuỗi security WebFilters** trên `ServerWebExchange`. `spring-security-test` cung cấp công cụ mô phỏng user, JWT, OAuth2, CSRF... bên trong mock server test, giúp tập trung vào **chính sách** mà chưa cần một identity provider thật cho mọi test.

### Bạn sẽ đạt được gì?

1. Thêm dependency `spring-security-test` đúng test scope và quản lý version bằng Spring Boot BOM.
2. Hiểu khác biệt `WebTestClient.bindToApplicationContext`, `@WebFluxTest`, `@SpringBootTest` và `bindToServer`.
3. Gắn `springSecurity()` để `SecurityWebFilterChain` thực sự tham gia vào mock integration tests.
4. Dùng `mockUser()`, `@WithMockUser`, `mockJwt()`, `mockOpaqueToken()`, `mockOAuth2Login()` và `csrf()` đúng phạm vi.
5. Phân biệt test 401/403, session login, CSRF token, CORS preflight, CSP/HSTS và HTTP firewall.
6. Viết regression suite cho Servlet-vs-Reactive khác biệt và cho multi-chain selection.
7. Biết điều **mocks không chứng minh**: chữ ký JWT thật, cookie cross-origin của browser, TLS/proxy, login flow và vòng đời WebSession.

## 2. Sơ đồ ba thành phần: WebTestClient, mock server và security filters

```text
JUnit 5 test method
       |
       v
WebTestClient
  - GET/POST/OPTIONS, headers, cookies, body
  - springSecurity() test configurer
  - mutateWith(mockUser/mockJwt/csrf...)
       |
       v
Mock WebFlux application context
       |
       v
WebFilterChainProxy
       |
       +-- ServerWebExchangeFirewall (từ Security 6.4+)
       |
       +-- Chọn SecurityWebFilterChain theo matcher/@Order
       |
       +-- CORS -> CSRF -> Authentication -> Authorization
       |           -> Exception handling -> Security headers
       v
Controller/RouterFunction
       |
       v
WebTestClient assertions:
  expectStatus, expectHeader, expectBody, JSONPath...
```

**Hai câu hỏi độc lập** khi đọc kết quả:

1. `WebTestClient` có thực sự gửi request qua application context chứa security WebFilters không?
2. Request đã chọn **đúng chain** và trải qua đúng authorization/CSRF/CORS/headers chưa?

Nếu câu 1 sai, test có thể trả 200 vì **không chạy Security**. Nếu câu 1 đúng nhưng chain selection sai, test cũng có thể bỏ qua chính sách dự kiến. Vì vậy, kiểm tra user thiếu quyền, POST thiếu CSRF và headers là bắt buộc; không chỉ test request được phép.

### 2.1. Các gói API không được nhầm với Servlet

| Mục tiêu | WebFlux/Reactive | Servlet/Spring MVC |
| --- | --- | --- |
| HTTP security builder | `ServerHttpSecurity` | `HttpSecurity` |
| Chain bean | `SecurityWebFilterChain` | `SecurityFilterChain` |
| Chain proxy | `WebFilterChainProxy` | `FilterChainProxy` |
| Authorization DSL | `authorizeExchange(...pathMatchers)` | `authorizeHttpRequests(...requestMatchers)` |
| Principal/context | Reactor Context và `ServerSecurityContextRepository` | `SecurityContextHolder`/Servlet request/context repository |
| CSRF | `CsrfWebFilter` / `ServerCsrfTokenRepository` | `CsrfFilter` / `CsrfTokenRepository` |
| CORS source | `org.springframework.web.cors.reactive.CorsConfigurationSource` | `org.springframework.web.cors.CorsConfigurationSource` |
| HTTP firewall | `StrictServerWebExchangeFirewall` (6.4+) | `StrictHttpFirewall` |
| Test HTTP | `WebTestClient` | `MockMvc` |
| Security test helpers | `SecurityMockServerConfigurers` | `SecurityMockMvcRequestPostProcessors` |

Không copy `SecurityMockMvcRequestPostProcessors.user()`/`csrf()` vào `WebTestClient`. Tên công cụ có thể giống nhau nhưng **kiểu request và pipeline khác**. Ngay cả khi ứng dụng dùng Reactor types ở service, nếu HTTP layer là Spring MVC thì đó vẫn là bài toán Servlet test.

## 3. Chuẩn bị dependency và phiên bản

`WebTestClient` thuộc Spring Test; các helper `springSecurity()`, `mockUser()`, `csrf()`, `mockJwt()` nằm trong artifact `org.springframework.security:spring-security-test`. Không nên tự đặt version khác BOM nếu dự án sử dụng Spring Boot dependency management.

### 3.1. Gradle (Groovy DSL)

```groovy
dependencies {
    // Ứng dụng thực tế đã có Spring WebFlux + Security starter phù hợp.
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'

    // Nếu viết StepVerifier tests và starter-test chưa cung cấp:
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Khi nâng lên Boot 4, có thể sử dụng các starter kiểm thử chia nhỏ (như `spring-boot-starter-webflux-test`) theo tài liệu và dependency graph của dòng tương ứng. Không trộn nhiều test starter/phiên bản để “sửa thiếu class” trước khi xác minh `spring-test`, `spring-security-test`, Reactor Test và JUnit đang được resolve.

### 3.2. Maven

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

Điều kiện cần là project có **`spring-webflux`, `spring-test` và Spring Security WebFlux runtime** tương thích, còn OAuth2 Resource Server tests thêm hỗ trợ JWT/opaque token theo dependency dự án. Với Spring Boot app, các test starters quản lý phần lớn phụ thuộc này.

### 3.3. Kiểm tra resolved versions

```bash
# Chạy trong repo của người học khi cần chẩn đoán version.
./gradlew dependencyInsight --dependency spring-security-test --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-security-web --configuration runtimeClasspath

# Hoặc Maven:
./mvnw dependency:tree -Dincludes=org.springframework.security
```

Ở Windows có `gradlew.bat`/`mvnw.cmd`. Những lệnh này **chỉ là hướng dẫn**, không phải kết quả đã chạy trong bài học. Nếu import `SecurityMockServerConfigurers` không tìm thấy, kiểm tra artifact test/runtime đã resolve trước khi sửa code.

### 3.4. Những import sử dụng xuyên suốt

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
```

Các import này thuộc `spring-security-test` của **Reactive WebTestClient**, không phải `org.springframework.security.test.web.servlet...`. Một số ví dụ tiếp theo là các đoạn **trong test class** có `client`/endpoint fixtures tương ứng, không phải tất cả cùng chạy trong một file Java duy nhất.

## 4. Thiết lập `WebTestClient` đúng cách

### 4.1. Cách tiêu chuẩn: `bindToApplicationContext` + `springSecurity()`

Spring Security Reference Guide sử dụng cấu hình sau:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ReactiveSecurityIntegrationTest {

    @Autowired ApplicationContext applicationContext;
    WebTestClient client;

    @BeforeEach
    void setUp() {
        this.client = WebTestClient
            .bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void publicEndpointResponds() {
        client.get().uri("/public/ping")
            .exchange()
            .expectStatus().isOk();
    }
}
```

Ví dụ giả định app có controller `GET /public/ping` và đang được cấu hình là một **Reactive** Spring Boot application. `@SpringBootTest` kiểu mặc định không mở HTTP server cổng thật; `WebTestClient` bind vào application context để thực thi WebFlux filters/handler mapping in-memory.

**Mấu chốt là `.apply(springSecurity())`** khi tự xây `WebTestClient` với context. Nó thêm phần hỗ trợ test Security vào mock server, giúp mutators và Spring Security WebFilters làm việc cùng nhau. Nếu test chỉ `bindToController(...)` mà không có security filters, nó không thể xác nhận role/CSRF/CORS do Security quản lý.

### 4.2. Cách Spring Boot auto-configure client

Spring Boot cũng hỗ trợ:

```java
@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveBootManagedClientTest {
    @Autowired WebTestClient client;
    // Các test GET/POST và assertions...
}
```

**Package phụ thuộc phiên bản:**

| Dòng Spring Boot | `@AutoConfigureWebTestClient` | `@WebFluxTest` |
| --- | --- | --- |
| 3.5 | `org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient` | `org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest` |
| 4.x | `org.springframework.boot.webtestclient.autoconfigure.AutoConfigureWebTestClient` | `org.springframework.boot.webflux.test.autoconfigure.WebFluxTest` |

Nếu muốn dùng `mockUser()` hoặc `csrf()` với client tự được Boot tạo, hãy xác nhận client đó đã áp dụng Spring Security mock-server test support trong cấu hình test đang chạy, hoặc **tạo một client tường minh bằng `bindToApplicationContext(...).apply(springSecurity())`** để tránh phỏng đoán. `@AutoConfigureWebTestClient` tự cấu hình client nhưng không thay thế việc include đúng custom security chain trong test context.

### 4.3. Khi nào chọn loại test nào?

| Loại setup | Có network server? | Security test support | Dùng để |
| --- | --- | --- | --- |
| `bindToController` | Không | Không có toàn app security chain theo mặc định | Controller behavior đơn giản |
| `bindToRouterFunction` | Không | Không có toàn app security chain theo mặc định | Functional route unit tests |
| `bindToApplicationContext` + `springSecurity()` | Không | Có WebFlux Security filters trong context và mutators | **Kiểm thử security integration chính** |
| `@WebFluxTest` + `@Import(SecurityConfig.class)` | Không | Có khi import đúng config, apply test support phù hợp | Test slice tập trung web layer |
| `@SpringBootTest` + `@AutoConfigureWebTestClient` | Không nếu MOCK | Có Security beans thuộc app context; kiểm tra mock support | Test toàn context, không TCP |
| `@SpringBootTest(RANDOM_PORT)` / `bindToServer` | **Có** | Chỉ có auth thật được gửi qua HTTP | Cookie, headers, login, JWT, server/proxy behavior |

Mỗi loại có giới hạn riêng. Không coi test slice, mock context và live TCP là các từ đồng nghĩa. Để xác minh reverse proxy/CDN và TLS termination, cần thêm staging/E2E qua đường public.

## 5. Xây fixture WebFlux có chính sách bảo mật thực để test

Đừng bắt đầu từ `@WebFluxTest` trống rồi giả định các custom security chains của ứng dụng tự xuất hiện. Dưới đây là một cấu hình **kiểm thử độc lập** minh họa cách để lớp bảo vệ thật chạy, trong khi principal được mô phỏng có kiểm soát.

### 5.1. Controller Reactive mẫu

```java
package com.example.protection;

import reactor.core.publisher.Mono;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SampleController {

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/admin/report")
    public Mono<String> report() {
        return Mono.just("private-report");
    }

    @PostMapping("/orders")
    public Mono<String> placeOrder() {
        return Mono.just("created");
    }
}
```

Đoạn controller đơn giản cố ý không chứa nghiệp vụ thật. Nó cho phép test tập trung vào authorization, CSRF, CORS, headers và đường đi qua filter chain. Trong ứng dụng production, controller gọi service và kiểm tra quyền truy cập ở cả domain/method layer khi cần.

### 5.2. Cấu hình Security WebFlux

```java
package com.example.protection;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.reactive.CorsConfigurationSource;

@Configuration
@EnableWebFluxSecurity
public class ReactiveProtectionConfig {

    @Bean
    SecurityWebFilterChain browser(
            ServerHttpSecurity http,
            CorsConfigurationSource allowedCors) {

        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/public/**").permitAll()
                .pathMatchers("/admin/**").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .cors(cors -> cors.configurationSource(allowedCors))
            .csrf(Customizer.withDefaults())
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives(
                        "default-src 'self'; object-src 'none'; frame-ancestors 'none'"
                    )
                )
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Đây là ví dụ **WebFlux**, nên `SecurityWebFilterChain` và `ServerHttpSecurity` đúng stack. `httpBasic` trong fixture giúp phân biệt 401 anonymous với 403 thiếu quyền, và có thể dùng khi minh họa HTTP integration với test credential. Vì browser có thể tự gửi Basic credential hoặc session cookie, **giữ CSRF cho unsafe methods**; không mặc định coi Basic là “API stateless nên tắt CSRF”.

### 5.3. CORS source Reactive mẫu

```java
package com.example.protection;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
public class ReactiveCorsConfig {

    @Bean
    CorsConfigurationSource allowedCors() {
        CorsConfiguration c = new CorsConfiguration();
        c.setAllowedOrigins(List.of("https://app.example.com"));
        c.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        c.setAllowedHeaders(
            List.of("Content-Type", "X-CSRF-TOKEN", "X-XSRF-TOKEN"));
        c.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", c);
        return source;
    }
}
```

`CorsConfigurationSource` thuộc `org.springframework.web.cors.reactive`, **không** phải Servlet package. Host `example.com` chỉ là minh họa; trong thực tế lấy origin từ cấu hình có validation theo môi trường, không trả allow-origin `*` cho credentialed request.

### 5.4. Test users: dùng duy nhất ở test profile

Khi test theo HTTP Basic với server thật, cần một `ReactiveUserDetailsService` hợp lệ. Chỉ ở test profile có thể dựng test user store:

```java
package com.example.protection;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;

@TestConfiguration
public class TestUserStore {

    @Bean
    MapReactiveUserDetailsService testUsers() {
        UserDetails viewer = User.withUsername("viewer")
            .password("{noop}test-only-password")
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password("{noop}test-only-admin-password")
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(viewer, admin);
    }
}
```

**Chỉ dùng `{noop}`/mật khẩu giả trong môi trường thử nghiệm.** Production phải cấu hình user/identity provider thật, password encoder mạnh và secrets an toàn. Nếu production application đã có một `ReactiveUserDetailsService` bean, cần tránh tạo thêm bean ngoài ý định; dùng `@Import(TestUserStore.class)` ở đúng test class hoặc test profile với sự cô lập rõ ràng.

## 6. Test authentication/authorization bằng `mockUser()`

### 6.1. Authentication mock được gắn theo một request

Giả sử `client` được tạo bởi `bindToApplicationContext(...).apply(springSecurity())` và đã có controller ở mục 5:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

@Test
void anonymousCannotReadAdmin() {
    client.get().uri("/admin/report")
        .exchange()
        .expectStatus().isUnauthorized();
}

@Test
void ordinaryUserCannotReadAdmin() {
    client.mutateWith(mockUser("viewer").roles("USER"))
        .get().uri("/admin/report")
        .exchange()
        .expectStatus().isForbidden();
}

@Test
void adminCanReadAdmin() {
    client.mutateWith(mockUser("admin").roles("ADMIN"))
        .get().uri("/admin/report")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("private-report");
}
```

`mockUser("admin").roles("ADMIN")` tạo principal có `ROLE_ADMIN`, đúng với `hasRole("ADMIN")`. Nếu ứng dụng dùng `hasAuthority("SCOPE_admin")`, đừng gửi role rồi kết luận authorization sai; **ROLE và SCOPE là hai authority khác nhau**.

### 6.2. Phân biệt `roles` và `authorities`

```java
// hasRole("ADMIN") kỳ vọng ROLE_ADMIN
client.mutateWith(mockUser("alice").roles("ADMIN"))
    .get().uri("/admin/report")
    .exchange()
    .expectStatus().isOk();

// hasAuthority("SCOPE_orders:read") kỳ vọng chuỗi authority chính xác.
client.mutateWith(mockUser("bob")
        .authorities(new SimpleGrantedAuthority("SCOPE_orders:read")))
    .get().uri("/orders/view")
    .exchange();
```

Đoạn thứ hai là mẫu mutator; status cuối phụ thuộc route `/orders/view` và rule thực sự được cấu hình, nên không mặc định assert `isOk()` khi chưa có fixture. Nhập sai prefix `ROLE_`/`SCOPE_` là lỗi thường gặp sau khi đổi JWT converter hay method security.

### 6.3. `@WithMockUser` so với `mutateWith(mockUser())`

Spring Security hỗ trợ cả annotation:

```java
import org.springframework.security.test.context.support.WithMockUser;

@Test
@WithMockUser(username = "admin", roles = "ADMIN")
void adminAnnotationCanAccessAdmin() {
    client.get().uri("/admin/report")
        .exchange()
        .expectStatus().isOk();
}
```

**Cách chọn:**

| `@WithMockUser` | `mutateWith(mockUser())` |
| --- | --- |
| Tiện cho toàn test method | Tiện cho từng request trong cùng method |
| Phù hợp test method security + HTTP tests in-memory | Rõ principal/roles sát request |
| Phụ thuộc Spring Test context listeners phù hợp Reactive | Cần `springSecurity()` mock-server support |
| Không tự mang auth qua HTTP tới server thật | Cũng không mang auth qua TCP tới server thật |

Reactive method security dựa trên Reactor Context. Nếu test trực tiếp service method có `@PreAuthorize` và dùng `@WithMockUser`, bảo đảm Spring Test Security listeners cho Reactor được đăng ký phù hợp; riêng request mutator có thể tiện hơn khi test WebFilterChain.

### 6.4. `mockAuthentication` cho principal tùy chỉnh

Khi controller/service phụ thuộc một `Authentication` cụ thể, có thể mock chính object này:

```java
import java.util.List;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

var authentication = new UsernamePasswordAuthenticationToken(
    "alice",
    "not-used",
    List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
);

client.mutateWith(mockAuthentication(authentication))
    .get().uri("/admin/report")
    .exchange()
    .expectStatus().isOk();
```

Đây là test-mutator, **không gọi authentication provider** hay xác thực password. Đừng dùng `mockAuthentication` để chứng minh login flow thật hay password hashing đúng.

## 7. Kiểm thử CSRF trong WebFlux bằng `csrf()`

Với `CsrfWebFilter` mặc định, các request HTTP unsafe như POST/PUT/PATCH/DELETE cần CSRF token khi bảo vệ phù hợp được bật. `permitAll()` của authorization không tự vô hiệu CSRF. Test quan trọng nhất là **có user nhưng không có token** vẫn bị từ chối.

### 7.1. Bộ test âm/dương cơ bản

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

@Test
void postWithoutCsrfIsRejected() {
    client.mutateWith(mockUser("viewer").roles("USER"))
        .post().uri("/orders")
        .exchange()
        .expectStatus().isForbidden();
}

@Test
void postWithCsrfIsAccepted() {
    client.mutateWith(mockUser("viewer").roles("USER"))
        .mutateWith(csrf())
        .post().uri("/orders")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("created");
}
```

Trong fixture mục 5, `POST /orders` không đòi role đặc biệt nhưng yêu cầu authenticated user; ví dụ đúng. `csrf()` của `SecurityMockServerConfigurers` cung cấp token hợp lệ cho mock exchange, giúp kiểm thử **cơ chế từ chối/chấp nhận ở tầng CSRF**. Nó không tự chứng minh browser đã nhận cookie `XSRF-TOKEN` hoặc gửi lại header đúng.

### 7.2. Vì sao không nên suy CSRF từ status 403 duy nhất?

`403` có thể do:

- CSRF token thiếu/không hợp lệ.
- Authenticated user thiếu quyền.
- CORS policy từ chối origin.
- Custom `ServerAccessDeniedHandler`.

Do đó phải có **positive control**: test cùng user và URL với `csrf()`. Nếu có token mà vẫn 403, xem authorization role, selected chain hoặc handler khác, không sửa bằng cách tắt CSRF.

### 7.3. Test token sai và flow SPA/session thực

Ở WebFlux, `SecurityMockServerConfigurers.csrf()` là helper cho **valid token**. Không giả định nó có API `useInvalidToken()` giống `MockMvc` Servlet. Để kiểm tra token sai/stale một cách chắc chắn, dùng **cookie-aware client** hoặc `GET /csrf` endpoint phù hợp repository/handler của ứng dụng:

```text
1. GET /csrf -> nhận token T, duy trì WebSession cookie.
2. POST /orders cùng session, KHÔNG đính token -> 403.
3. POST /orders cùng session, header CSRF = "wrong" -> 403.
4. POST /orders cùng session, header CSRF = T -> vượt CSRF.
5. Login/logout làm token cũ bị xóa -> lấy token mới trước POST tiếp.
```

Khi dùng `WebSessionServerCsrfTokenRepository` mặc định và handler có XOR/BREACH masking, **gửi lại đúng token mà request handler expose**, không tự lấy raw cookie token theo mẫu Servlet 7 `csrf.spa()`. Trong Spring Security 7, `ServerHttpSecurity.CsrfSpec` không có cùng method `spa()` của Servlet `HttpSecurity`; cấu hình token endpoint và request handler cho WebFlux phải được chọn riêng.

### 7.4. Form login và CSRF

`POST /login` dùng form login/session cũng là state-changing request; trong các ứng dụng bật CSRF, token cần được gửi đúng. Khi test mock user bằng `mockUser()`, bạn **bỏ qua** authentication flow; muốn kiểm tra form login thật và session fixation, cần test POST login với credentials và CSRF thực trên HTTP test client có cookie jar.

## 8. Reactive Resource Server: kiểm thử JWT, opaque token và OAuth2

Khi một API Reactive sử dụng Bearer token, `@WithMockUser` thường không đủ nếu controller/method security đọc claim `sub`, scope, audience hoặc cần principal là `JwtAuthenticationToken`. `spring-security-test` cung cấp các mutators chuyên biệt.

### 8.1. Fixture API chain giả định

Ví dụ bảo vệ `/api/**` bằng OAuth2 Resource Server JWT. Đây là một **cấu hình ứng dụng độc lập** với fixture form/basic ở mục 5; nếu muốn kết hợp trong một ứng dụng, phải thiết kế multi-chain ở mục 12.

```java
@Bean
@Order(1)
SecurityWebFilterChain api(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            ServerWebExchangeMatchers.pathMatchers("/api/**"))
        .authorizeExchange(auth -> auth
            .pathMatchers(HttpMethod.GET, "/api/public/**").permitAll()
            .pathMatchers("/api/orders/**").hasAuthority("SCOPE_orders:read")
            .anyExchange().authenticated()
        )
        // Chỉ miễn CSRF khi API THUẦN bearer, không nhận session cookie
        // hay credential mà browser tự động đính kèm.
        .csrf(csrf -> csrf.disable())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults()))
        .build();
}
```

Để chạy Resource Server thực, ứng dụng cần cấu hình decoder/issuer/JWK và dependency tương ứng. Với test `mockJwt()`, bạn tập trung vào **authorization và claim mapping** chứ không tạo token ký thật. Không dùng đoạn `csrf.disable()` cho API dùng cookie session.

### 8.2. `mockJwt()`: cấp đúng authority

```java
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

@Test
void jwtWithoutScopeCannotReadOrders() {
    client.mutateWith(mockJwt()
            .authorities(new SimpleGrantedAuthority("SCOPE_profile:read")))
        .get().uri("/api/orders/42")
        .exchange()
        .expectStatus().isForbidden();
}

@Test
void jwtWithScopeCanReadOrders() {
    client.mutateWith(mockJwt()
            .authorities(new SimpleGrantedAuthority("SCOPE_orders:read")))
        .get().uri("/api/orders/42")
        .exchange()
        .expectStatus().isOk();
}
```

Giả định một handler `GET /api/orders/42` có tồn tại và trả 200 khi được phép. `hasAuthority("SCOPE_orders:read")` đòi authority chính xác, nên `ROLE_ADMIN` không tự thay thế được.

### 8.3. Tạo JWT mock có claim cụ thể

```java
import org.springframework.security.oauth2.jwt.Jwt;

Jwt jwt = Jwt.withTokenValue("test-token")
    .header("alg", "none")      // Chỉ có ý nghĩa trong mock test!
    .subject("user-42")
    .claim("tenant", "tenant-a")
    .claim("scope", "orders:read")
    .build();

client.mutateWith(mockJwt()
        .jwt(jwt)
        .authorities(new SimpleGrantedAuthority("SCOPE_orders:read")))
    .get().uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk();
```

Trong ví dụ, `.authorities(...)` **định nghĩa trực tiếp** authorities; không chứng minh production `JwtGrantedAuthoritiesConverter` đã biến claim `scope` thành đúng authorities. Muốn kiểm thử mapping thật, test converter riêng và/hoặc cấu hình `ReactiveJwtDecoder` với một token ký bằng key thử nghiệm, gửi nó qua request HTTP thực.

**Không chấp nhận `alg=none` trên production decoder.** Nó chỉ xuất hiện trong object mock do `spring-security-test` dựng để không cần chữ ký thật khi test authorization. Đừng gửi chuỗi `test-token` tới identity provider hay trông chờ API production xác thực.

### 8.4. Opaque token, OAuth2 login và OIDC

Những mutators thường dùng:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOpaqueToken;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOAuth2Login;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOidcLogin;

// Resource Server introspection/opaque token: lập principal và authorities giả.
client.mutateWith(mockOpaqueToken()
        .authorities(new SimpleGrantedAuthority("SCOPE_orders:read")))
    .get().uri("/api/orders/42")
    .exchange();

// Ứng dụng có OAuth2 login:
client.mutateWith(mockOAuth2Login())
    .get().uri("/account")
    .exchange();

// Controller đòi OidcUser:
client.mutateWith(mockOidcLogin())
    .get().uri("/profile")
    .exchange();
```

Status của các snippet này phụ thuộc config/handler app, nên chưa assert kết quả. Các helpers **mô phỏng authenticated principal**; chúng không chứng minh OAuth authorization-code redirect flow, OIDC discovery, token introspection, revocation hay JWKS networking thực sự hoạt động.

Khi test controller dùng `@AuthenticationPrincipal OidcUser`, `mockOidcLogin()` giúp kiểm tra claim/identity handling mà không cần chạy provider thật. Với integration cần bảo đảm đúng login session hoặc consent flow, dùng môi trường identity provider thử nghiệm và HTTP client/browser thực.

### 8.5. Khi nào cần mock decoder thay vì `mockJwt()`?

| Mục tiêu test | Nên dùng |
| --- | --- |
| User với `SCOPE_orders:read` có được gọi URL không? | `mockJwt().authorities(...)` |
| Controller đọc `tenant` claim và trả dữ liệu đúng? | `mockJwt().jwt(customJwt)` |
| Token thiếu scope dẫn tới 403? | `mockJwt()` với authority không đủ |
| Token thật sai chữ ký/issuer/audience có bị 401? | HTTP integration với `ReactiveJwtDecoder`/test key hoặc provider giả |
| Introspection endpoint timeout/failure? | Mock `ReactiveOpaqueTokenIntrospector` hoặc integration server có kiểm soát |
| Login redirect/cookie sau OAuth2 callback? | Full integration hoặc browser E2E |

Test mutator giỏi nhất khi **isolate authorization**. Đừng dùng mock để khẳng định crypto, remote identity service hay session-cookie behavior.

## 9. Kiểm thử CORS preflight bằng WebTestClient

CORS là cơ chế do browser áp dụng, nhưng server phải trả đúng các response headers. Khi SPA khác origin gửi JSON hoặc custom CSRF header, browser có thể gửi OPTIONS trước POST; preflight thường **không mang session cookie**.

### 9.1. Test allowlisted origin

Với CORS fixture mục 5, `https://app.example.com` là origin hợp lệ:

```java
@Test
void allowedPreflightHasExpectedCorsHeaders() {
    client.options().uri("/orders")
        .header("Origin", "https://app.example.com")
        .header("Access-Control-Request-Method", "POST")
        .header("Access-Control-Request-Headers", "content-type,x-csrf-token")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals(
            "Access-Control-Allow-Origin", "https://app.example.com")
        .expectHeader().valueEquals(
            "Access-Control-Allow-Credentials", "true");
}
```

Spring CORS filter thường trả 200 cho preflight hợp lệ; một gateway có thể trả 204 hoặc thêm headers riêng. Khi test API contract thực tế, pin status đúng thành phần xử lý và luôn kiểm tra headers chính.

### 9.2. Test origin lạ

```java
@Test
void untrustedOriginIsNeverGrantedCorsPermission() {
    client.options().uri("/orders")
        .header("Origin", "https://evil.example")
        .header("Access-Control-Request-Method", "POST")
        .exchange()
        .expectHeader()
        .doesNotExist("Access-Control-Allow-Origin");
}
```

Negative test không nhất thiết yêu cầu status đúng 403 nếu proxy/custom handlers khác. Hợp đồng quan trọng là **origin lạ không được cấp quyền CORS**, và browser không thể đọc credentialed response từ origin đó. CORS **không thay CSRF hoặc authorization**: một request side-effect hợp lệ về HTTP vẫn cần user/quyền và token CSRF nếu dùng cookie.

### 9.3. Test preflight không rơi vào authentication

Nếu OPTIONS bị 401 khi thiếu cookie, cần kiểm tra CORS filter đã được xử lý **trước authentication** và chain matcher có bao phủ OPTIONS hay không. Một chain chỉ match method POST có thể khiến preflight OPTIONS rơi sang chain khác.

```text
OPTIONS /orders
  Origin: https://app.example.com
  Access-Control-Request-Method: POST
      |
      +--> CORS filter/source đúng: response preflight, chưa cần login
      |
      +--> CORS thiếu/sai: preflight có thể bị 401/403
                                  -> browser không gửi POST
```

Nếu dùng nhiều `CorsConfigurationSource` hoặc CORS được cấu hình thêm tại gateway/handler, chỉ định source đúng **security chain** và xem response public để tránh duplicate `Access-Control-Allow-Origin`. Response thay đổi theo `Origin` cần cache/Vary xử lý đúng.

### 9.4. Browser/E2E mới kiểm tra được cookie thực

`WebTestClient` giúp quan sát headers, nhưng **không áp dụng đầy đủ chính sách trình duyệt** như SameSite, third-party cookie blocking, Fetch credentials mode hay CSP. Một preflight test xanh không chứng minh `fetch(..., { credentials: "include" })` sẽ mang cookie tới backend. Hãy chạy thêm browser E2E với origin staging thực.

## 10. Kiểm thử CSP, HSTS và các security headers

Security headers được cấu hình trên `SecurityWebFilterChain`. Chúng vẫn cần xuất hiện trên response public nếu `permitAll()` cho phép truy cập; `permitAll()` không có nghĩa bỏ qua các WebFilters.

### 10.1. CSP và `X-Content-Type-Options`

```java
@Test
void publicEndpointStillGetsSecurityHeaders() {
    client.get().uri("/public/ping")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals(
            "Content-Security-Policy",
            "default-src 'self'; object-src 'none'; frame-ancestors 'none'")
        .expectHeader().valueEquals(
            "X-Content-Type-Options", "nosniff");
}
```

`Content-Security-Policy` **không được Spring Security thêm mặc định**. Test trên chỉ pass vì cấu hình mục 5 đã chủ động khai báo `contentSecurityPolicy`. `X-Content-Type-Options` thường có default `nosniff` theo Spring Security config, nhưng vẫn nên regression test sau khi đổi chains/headers.

### 10.2. CSP của frontend HTML có thể không thuộc backend API

Giả sử frontend HTML ở `https://app.example.com` do CDN phục vụ, API ở `https://api.example.com` do Spring WebFlux phục vụ. CSP `connect-src` của frontend phải cho phép API origin, nhưng CSP Spring gắn trên **JSON API response** không thay thế CSP HTML do CDN trả.

Vì vậy cần hai nhóm test:

- `WebTestClient` xác nhận headers do **Spring WebFlux** ghi vào response của app.
- Browser/public HTTP test xác nhận **HTML frontend thực** có CSP đúng cho script/style/font/connect và không gây vi phạm.

Đừng “sửa CORS” để xử lý CSP `connect-src` chặn fetch; chúng là hai policy khác nhau.

### 10.3. HSTS cần HTTPS request thực tế

HSTS chỉ có ý nghĩa khi trình duyệt nhận `Strict-Transport-Security` trên HTTPS public. Các mock clients bind-to-context thường không mô phỏng trọn vẹn TLS termination và forwarded headers.

```bash
curl -i "https://api.staging.example.com/public/ping"
```

Trong staging thực, kiểm tra `Strict-Transport-Security: max-age=...`, `includeSubDomains` và tình trạng TLS/ingress, không suy HSTS thiếu chỉ vì mock HTTP URI là `http://localhost`. Khi cùng hostname có nhiều chains, HSTS có tác động **mức host**, nên nên giữ policy thống nhất.

### 10.4. Public URL, 401/403 và headers

Hãy test headers trên **ít nhất** một URL public và một URL cần auth (đăng nhập hoặc có mock principal). Một số headers được ghi ở trước/sau filter chain và có thể khác trên response lỗi. Nếu một URL hoàn toàn không đi qua Spring Security hoặc do gateway/CDN phục vụ, test của Spring không chứng minh response đó có đúng headers.

## 11. Kiểm thử HTTP firewall Reactive (Spring Security 6.4+)

Từ Spring Security 6.4, WebFlux có `ServerWebExchangeFirewall` và triển khai mặc định `StrictServerWebExchangeFirewall`. Firewall bảo vệ tầng **diễn giải request URI/method/header** trước khi authorization cho phép/không cho phép một endpoint.

### 11.1. Vì sao phải test firewall riêng?

```text
GET /admin/report       -> URL chuẩn; USER thiếu role -> 403
GET /admin;v=1/report   -> URL semicolon đáng ngờ -> thường bị firewall reject
GET /admin//report      -> URL chưa normalize -> reject ở server/proxy/firewall
TRACE /public/ping      -> method ngoài allowlist -> reject
POST /orders thiếu CSRF -> URL chuẩn, nhưng CSRF filter -> 403
```

Hai request cùng trả 400/403 có thể đến từ **những tầng khác nhau**. `StrictServerWebExchangeFirewall` không tự thay đổi quyền `ROLE_ADMIN`, không cấp CSRF token và không đặt CORS allow-origin.

### 11.2. Unit test trực tiếp bằng StepVerifier

Với `spring-security-web` 6.4+, `spring-test` và `reactor-test`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.web.server.firewall.StrictServerWebExchangeFirewall;
import org.springframework.security.web.server.firewall.ServerExchangeRejectedException;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@Test
void strictFirewallRejectsSemicolonPath() {
    var firewall = new StrictServerWebExchangeFirewall();
    var exchange = MockServerWebExchange.from(
        MockServerHttpRequest.get("/admin;v=1/report")
    );

    StepVerifier.create(
        Mono.defer(() -> firewall.getFirewalledExchange(exchange))
    )
        .expectError(ServerExchangeRejectedException.class)
        .verify();
}

@Test
void strictFirewallAllowsCanonicalPath() {
    var firewall = new StrictServerWebExchangeFirewall();
    var exchange = MockServerWebExchange.from(
        MockServerHttpRequest.get("/public/ping")
    );

    StepVerifier.create(
        Mono.defer(() -> firewall.getFirewalledExchange(exchange))
    )
        .expectNextCount(1)
        .verifyComplete();
}
```

`Mono.defer` bao cả kiểm tra đồng bộ lẫn reactive subscription vào phạm vi assertion. Test này chứng minh **instance Strict firewall** xử lý input như kỳ vọng; **chưa** chứng minh một server thực có `WebFilterChainProxy` đang sử dụng đúng instance đó.

### 11.3. Kiểm thử tích hợp qua WebTestClient

```java
@Test
void semicolonPathIsRejectedByDefaultFirewall() {
    client.get().uri("/admin;v=1/report")
        .exchange()
        .expectStatus().isBadRequest();
}
```

Kỳ vọng HTTP 400 áp dụng cho fixture Security WebFlux với default `HttpStatusExchangeRejectedHandler` và mock request còn nguyên semicolon đến firewall. Ở server/proxy thực, URI có thể bị reject hoặc normalize trước, hoặc custom rejection handler trả status khác. Đừng chỉnh test bằng `setAllowSemicolon(true)` để làm request qua; thay vì vậy, xác định **vì sao URI bất thường phát sinh**.

### 11.4. Không nới security defaults để “sửa bài kiểm thử”

Những công tắc như `setAllowSemicolon(true)`, `setAllowUrlEncodedSlash(true)` hoặc `setUnsafeAllowAnyHttpMethod(true)` phải được coi là **thay đổi chính sách bảo mật**, không phải tiện ích test. Khi cần URL đặc biệt, ưu tiên thay đổi định dạng identifier/route để các tầng ingress, WebFlux matcher và controller hiểu thống nhất.

**Lưu ý mốc version:** một project WebFlux Security 6.3 không import được `StrictServerWebExchangeFirewall`. Đừng viết test class mới này rồi kết luận ứng dụng cũ thiếu dependency test; nó là API xuất hiện từ 6.4.

## 12. Nhiều security chains: test chọn đúng chain

Khi có một API Bearer và một browser form/session trong cùng WebFlux application:

```text
@Order(1): /api/**, Bearer JWT, CORS dành cho SPA API,
           CSRF chỉ miễn nếu không nhận browser credential tự gửi

@Order(2): fallback, form/session, CSRF bật,
           CSP/HSTS theo chính sách browser
```

Một test chỉ kiểm tra `/api/orders` trả 200 **không chứng minh** `/admin/report` hay `/login` được bảo vệ. Bảo vệ phải bao phủ URL ngoài matcher API và không có chain ưu tiên cao match quá rộng.

### 12.1. Ví dụ khung multi-chain Reactive

```java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Bean
@Order(1)
SecurityWebFilterChain api(ServerHttpSecurity http) {
    return http
        .securityMatcher(ServerWebExchangeMatchers.pathMatchers("/api/**"))
        .authorizeExchange(auth -> auth
            .pathMatchers("/api/admin/**").hasAuthority("SCOPE_admin")
            .anyExchange().authenticated()
        )
        // Chỉ dành cho Bearer-only API đã được duyệt threat model.
        .csrf(csrf -> csrf.disable())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults()))
        .build();
}

@Bean
@Order(2)
SecurityWebFilterChain browser(ServerHttpSecurity http) {
    return http
        .authorizeExchange(auth -> auth
            .pathMatchers("/public/**", "/login", "/error").permitAll()
            .pathMatchers("/admin/**").hasRole("ADMIN")
            .anyExchange().authenticated()
        )
        .csrf(Customizer.withDefaults())
        .formLogin(Customizer.withDefaults())
        .build();
}
```

Đây là **khung ví dụ thay cho security chain fixture duy nhất ở mục 5**, không được khai báo thêm bên cạnh fixture ấy mà không xử lý matcher/order. Cần cấu hình CORS/headers cho từng chain và JWT decoder để vận hành thực tế.

### 12.2. Test phân biệt API và browser

```java
@Test
void apiAndBrowserChainsEnforceDifferentContracts() {
    client.mutateWith(mockJwt()
            .authorities(new SimpleGrantedAuthority("SCOPE_read")))
        .get().uri("/api/admin/report")
        .exchange()
        .expectStatus().isForbidden();

    client.mutateWith(mockJwt()
            .authorities(new SimpleGrantedAuthority("SCOPE_admin")))
        .get().uri("/api/admin/report")
        .exchange()
        .expectStatus().isOk();

    client.mutateWith(mockUser("viewer").roles("USER"))
        .get().uri("/admin/report")
        .exchange()
        .expectStatus().isForbidden();

    client.mutateWith(mockUser("viewer").roles("USER"))
        .post().uri("/orders")
        .exchange()
        .expectStatus().isForbidden();

    client.mutateWith(mockUser("viewer").roles("USER"))
        .mutateWith(csrf())
        .post().uri("/orders")
        .exchange()
        .expectStatus().isOk();
}
```

Đoạn test giả định handlers `/api/admin/report`, `/admin/report` và `/orders` tồn tại. Nếu API response cuối là 204, điều chỉnh expectation theo hợp đồng. Mục tiêu là chứng minh:

- `securityMatcher` chọn chain trước.
- `pathMatchers` chỉ chọn authorization rule bên trong chain.
- `csrf.disable()` trong API **không tắt** CSRF ở browser fallback.
- `ROLE_ADMIN` của browser không tương đương `SCOPE_admin` của JWT.

Test thêm `GET /api`, `/api/`, `/api-v2/**`, `/admin/**` và `/unknown` để phát hiện URL lọt khỏi mọi chain, nhất là khi có ingress rewrite prefix.

### 12.3. Đừng coi fallback mặc định của Boot là hiển nhiên

Khi ứng dụng tự tạo `SecurityWebFilterChain`, các default Security auto-configurations của Boot có thể rút lại theo điều kiện. Nếu chỉ có một chain `/api/**` mà không có fallback, một URL browser khác có thể không qua Spring Security. Test **một URL nằm ngoài tất cả matcher hẹp** phải là một test bắt buộc của migration.

## 13. `@WebFluxTest`: test slice cần import security config của ứng dụng

`@WebFluxTest` của Spring Boot tự thiết lập WebFlux slice và `WebTestClient`, nhưng **không tự quét toàn bộ custom `SecurityWebFilterChain` beans**. Nếu test slice thiếu security config, endpoint có thể bị xử lý bởi default chain hoặc bỏ qua các rule của ứng dụng, dẫn tới kết quả sai lệch.

### 13.1. Ví dụ test slice với Boot 3.5

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@WebFluxTest(SampleController.class)
@Import({ReactiveProtectionConfig.class, ReactiveCorsConfig.class})
class SampleControllerSecuritySliceTest {

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
    void publicRouteIsAvailable() {
        client.get().uri("/public/ping")
            .exchange()
            .expectStatus().isOk();
    }
}
```

Nếu security config phụ thuộc service, repository hay authentication beans không có trong slice, cần đưa vào test bằng `@Import`, `@MockitoBean` hoặc test configuration có chủ đích. **Không tắt toàn Security** để tránh lỗi thiếu bean. Một test slice “đã import security” vẫn cần kiểm tra chính sách âm: user thường không truy cập `/admin/**`, POST thiếu token bị chặn.

### 13.2. Spring Boot 4 thay đổi package

Trên Boot 4:

```java
// Boot 4: dùng package mới thay vì package Boot 3.5:
import org.springframework.boot.webflux.test.autoconfigure.WebFluxTest;
import org.springframework.boot.webtestclient.autoconfigure.AutoConfigureWebTestClient;
```

Spring Framework hiện đại dùng `@MockitoBean` ở `org.springframework.test.context.bean.override.mockito.MockitoBean`. Boot 3 cũ có thể dùng `@MockBean`; hãy đọc migration guide theo version đích, không copy cùng lúc cả hai. Khi kiểm thử API có security chain phụ thuộc CORS, custom filters hoặc authentication manager, nhập **đúng các beans cần thiết** thay vì phụ thuộc ngoài ý định vào scan của test slice.

### 13.3. Functional routes cần thêm cấu hình

`@WebFluxTest` không tự phát hiện mọi `RouterFunction` từ functional routing nếu bean nằm ngoài component scan slice. Với functional route phải `@Import` router config, hoặc dùng `@SpringBootTest` cho toàn application context.

### 13.4. Test slice và full context không thay thế nhau

Một test slice có thể giúp debug nhanh một controller, nhưng không nhất thiết chứa Gateway filters, tất cả `SecurityWebFilterChain`, method-security services và session store production. Duy trì một số tests `@SpringBootTest` để chứng minh integration, và thêm HTTPS/public smoke tests ở release pipeline.

## 14. Kiểm thử server thực: tại sao `mutateWith(mockUser())` không còn đủ?

`@SpringBootTest(webEnvironment = RANDOM_PORT)` mở web server trên một cổng TCP ngẫu nhiên. Khi đó `WebTestClient` là một HTTP client thật, request được xử lý **trong server process**. Context mutators của Spring Security mock server **không tự chuyển qua network**.

### 14.1. Ví dụ HTTP Basic với server thực

```java
// Import dành cho Spring Boot 3.5; trên Boot 4 xem bảng package ở mục 4.
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
@Import(TestUserStore.class)
class ReactiveRealHttpSecurityTest {

    @Autowired WebTestClient client;

    @Test
    void requestWithoutCredentialsIsUnauthorized() {
        client.get().uri("/admin/report")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void httpBasicWithValidCredentialsIsAllowed() {
        client.get().uri("/admin/report")
            .headers(h -> h.setBasicAuth(
                "admin", "test-only-admin-password"))
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void httpBasicUserWithoutAdminRoleIsForbidden() {
        client.get().uri("/admin/report")
            .headers(h -> h.setBasicAuth(
                "viewer", "test-only-password"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

Ví dụ giả định `SampleController` và `ReactiveProtectionConfig` trong application context; `TestUserStore` không được xung đột với user store có sẵn. Test credential là dữ liệu giả chỉ được dùng trong môi trường test; không sử dụng password `{noop}` trong production.

**Khác biệt bản chất:**

```text
Mock context:
  client.mutateWith(mockUser("admin")) -> ServerWebExchange mock
  -> Security filters nhìn thấy principal giả

Server RANDOM_PORT:
  client.get().headers(setBasicAuth("admin", "..."))
  -> HTTP request thực qua TCP
  -> server gọi authentication provider/user store
  -> SecurityContext được tạo nếu credential hợp lệ
```

`@WithMockUser` ở test thread cũng không tự làm server process xác thực user: request được xử lý trong thread/request context khác. Nếu bạn muốn thử Bearer token thật, gửi `Authorization: Bearer ...` và dùng key/issuer test phù hợp thay vì `mockJwt()`.

### 14.2. Khi nào dùng `bindToServer`?

```java
WebTestClient live = WebTestClient
    .bindToServer()
    .baseUrl("http://localhost:8080")
    .build();

live.get().uri("/public/ping")
    .exchange()
    .expectStatus().isOk();
```

Đây là mẫu cho một server đang chạy độc lập; khi test tích hợp Boot với `RANDOM_PORT`, ưu tiên inject `WebTestClient` đã được Boot cấu hình đúng port. Tránh hard-code 8080 nếu cổng là ngẫu nhiên. `bindToServer` không tự mang những request mutators của mock security context qua TCP.

### 14.3. Cookie/session phải được giữ qua nhiều request

`WebTestClient` không nên được giả định tự duy trì một browser cookie jar đầy đủ như Chrome. Khi test login/logout/WebSession:

1. GET endpoint phát session cookie và/hoặc CSRF token.
2. Lấy giá trị `Set-Cookie`/`ResponseCookie` từ response test.
3. Đưa cookie phù hợp vào request tiếp theo bằng `.cookie(name, value)` hoặc cơ chế cookie-aware client đã thiết kế.
4. POST login có CSRF token hợp lệ, nhận session mới nếu server rotate session.
5. GET private URL với cookie mới; xác nhận authenticated.
6. POST logout có token hợp lệ; kiểm tra session/token cũ không còn tác dụng.

Đừng chỉ gửi một cookie CSRF mà bỏ WebSession cookie; repository mặc định có thể lưu token trong WebSession. Ở môi trường nhiều replica, cần test request đổi pod nhưng vẫn nhận đúng security context qua shared session store.

### 14.4. Các thứ test qua network nhưng chưa qua CDN/proxy

RANDOM_PORT kiểm tra HTTP server và authentication thật của ứng dụng, nhưng **không nhất thiết** tái hiện:

- TLS termination ở ingress, `Forwarded`/`X-Forwarded-Proto`.
- CDN serving HTML/static assets, CSP của frontend.
- Cookie SameSite hoặc third-party cookie restrictions của browser.
- Gateway route rewrite, WAF và firewall normalization ngoài ứng dụng.
- Rolling deploy với shared Redis session trên nhiều phiên bản.

Vì vậy cần một lớp smoke test qua **public staging HTTPS** trước khi promote.

## 15. Chẩn đoán khi test WebFlux Security không như kỳ vọng

### Lỗi A — `mockUser()` có nhưng endpoint vẫn 401

**Kiểm tra:** client có `.apply(springSecurity())` ở mock context không? Có đúng `SecurityWebFilterChain`/`WebFilterChainProxy` trong context không? Test đang gọi `bindToServer`/RANDOM_PORT thay vì in-memory hay không?

**Cách xử lý:** với mock context, bind đúng application context và test mutator; với live HTTP, gửi Basic/Bearer credentials thật. Đừng đặt `@WithMockUser` lên test TCP rồi kỳ vọng server tự biết user.

### Lỗi B — `@WebFluxTest` trả 200 cho URL ADMIN dù production chặn

**Khả năng:** slice không import custom security config; controller được test riêng hoặc test client không qua Security WebFilter.

**Cách xử lý:** `@Import` chain config và các dependency tối thiểu, dùng `springSecurity()`, thêm negative test USER/anonymous. Dùng `@SpringBootTest` khi muốn bao phủ toàn security stack.

### Lỗi C — WebFlux test gửi `csrf()` vẫn bị 403

**Khả năng:** request đi sai chain, user thiếu quyền, CSRF repository/handler tùy chỉnh, request không có đúng session, hoặc token không hợp lệ.

**Cách xử lý:** thêm positive/negative controls, xem `CsrfWebFilter`, `ServerCsrfTokenRepository` và exception logs an toàn. Không tắt `csrf` để làm pass.

### Lỗi D — POST thiếu token trả 200

**Đây là tín hiệu cần kiểm tra ngay.** Có thể:

- Request không được gắn security filters.
- Chain được chọn có `csrf.disable()`.
- CSRF request matcher/ignore rules miễn endpoint.
- HTTP method thuộc safe method chứ không phải POST.
- Test helper hoặc filter tự cấp token ngoài ý định.

Kiểm tra đúng URL, method, chain và WebFilters; đừng coi test 200 như một dấu hiệu chức năng tốt.

### Lỗi E — JWT mock có scope nhưng vẫn 403

**Khả năng:** authority string sai (`ROLE_ADMIN` vs `SCOPE_admin`), rule `hasAuthority` khác, custom converter/config hoặc request đi vào browser chain.

**Cách xử lý:** test `mockJwt().authorities(...)` với authority chính xác, kiểm tra matcher `/api/**` và callback authorization. Một claim `scope` trong JWT mock không tự chứng minh converter đã chạy nếu bạn đặt authorities thủ công.

### Lỗi F — Test `mockJwt()` pass, server JWT thực trả 401

**Nguyên nhân:** mutator bỏ qua việc ký/parse token, còn server thật cần decoder/issuer/audience và JWKS hợp lệ.

**Cách xử lý:** thêm integration test với `ReactiveJwtDecoder` thực và token ký từ test issuer/key; tách test 401 sai chữ ký/expired token khỏi test 403 thiếu quyền.

### Lỗi G — OPTIONS preflight bị 401/403

**Kiểm tra:** Reactive CORS source đúng package, origin/method/headers, chain match OPTIONS, ingress chặn OPTIONS, credentials policy.

**Cách xử lý:** cấu hình CORS trước authentication trong security pipeline. `permitAll()` OPTIONS không đủ nếu thiếu `Access-Control-Allow-Origin`. Browser vẫn cần CSRF token cho POST cookie.

### Lỗi H — CSP/HSTS thiếu trên test

**Kiểm tra:** CSP đã được cấu hình chưa (không tự có mặc định)? Response có đi qua chain viết headers không? Đang thử HSTS trên HTTP in-memory hay HTTPS public? HTML có được CDN phát thay backend không?

**Cách xử lý:** giữ CSP trên đúng HTML response/chain, kiểm tra public HTTPS/HSTS và trusted forwarded headers. Đừng tắt toàn bộ headers vì một directive phá giao diện.

### Lỗi I — Firewall test 400 nhưng qua ingress lại trả 404/200

**Nguyên nhân:** URL bị proxy/parser normalize trước `StrictServerWebExchangeFirewall` hoặc custom rejected handler đổi status.

**Cách xử lý:** kết hợp direct firewall unit test, WebTestClient context test và `curl --path-as-is` qua ingress được ủy quyền. Kiểm tra canonical path; không nới encoded slash/semicolon tùy tiện.

### Lỗi J — `No qualifying bean of type SecurityWebFilterChain`

**Khả năng:** test slice không import `@Configuration` chứa security chain, dùng sai stack Servlet vs Reactive, hoặc bean phụ thuộc authentication/CORS source chưa được tạo.

**Cách xử lý:** xác minh `WebApplicationType`, import đúng chain config và các dependencies, xem Boot's auto-configuration conditions. Không giải quyết bằng cách disable Security toàn bộ.

### Lỗi K — `mockUser()` của test trước ảnh hưởng test sau

**Điều tra:** có đang dùng static/shared test client với mutator permanent/defaultHeaders? Có dùng `@WithMockUser` ở cấp class hoặc đang dùng custom Reactor context không được cô lập?

**Cách xử lý:** tạo test client mới trong `@BeforeEach`, apply mutator theo request, không chia sẻ session/cookies ngoài chủ đích. Tránh lạm dụng `@DirtiesContext` để che state leakage nếu có thể sửa fixture.

### Lỗi L — `@WebFluxTest` không phát hiện functional routes

**Nguyên nhân:** test slice thường chỉ scan controller và một nhóm web components; `RouterFunction` bean không tự được đưa vào như full context.

**Cách xử lý:** `@Import` đúng router configuration và security config, hoặc chuyển test sang `@SpringBootTest`. Không kết luận 404 của functional route là do authorization.

## 16. Ma trận hồi quy trước khi nâng hoặc thay cấu hình

| Mục tiêu | Request/test | Expected contract |
| --- | --- | --- |
| Public | GET `/public/ping` | 200, có headers |
| Anonymous private | GET `/admin/report` không auth | 401 hoặc login redirect tùy entry point |
| User role | `mockUser().roles("USER")` GET admin | 403 |
| Admin role | `mockUser().roles("ADMIN")` GET admin | 200, có headers |
| CSRF âm | User + POST `/orders` không token | 403 |
| CSRF dương | User + `csrf()` POST `/orders` | Qua CSRF, handler response đúng |
| CSRF stale | Cookie/WebSession token cũ sau logout | Bị từ chối, refresh trước POST |
| API JWT thiếu scope | `mockJwt(SCOPE_read)` GET admin API | 403 |
| API JWT đúng scope | `mockJwt(SCOPE_admin)` GET admin API | Qua authorization |
| JWT thật không hợp lệ | Bearer token ký sai/expired qua TCP | 401 |
| CORS positive | OPTIONS origin allowlisted | Allow-origin đúng, preflight không cần auth |
| CORS negative | OPTIONS origin lạ | Không được cấp CORS permission |
| CSP | GET HTML/backend response | CSP đúng chain và trang thực |
| HSTS | HTTPS public GET | HSTS đúng hostname |
| Firewall | Semicolon/duplicate slash, TRACE | Không bypass security/routing |
| Session | Login, cookie rotation, logout | Phiên cũ mất hiệu lực |
| Multi-chain | `/api/**` và `/admin/**` | Chain đúng, fallback bảo vệ URL còn lại |
| Proxy path | Public URL sau rewrite | Matcher và handler nhìn cùng canonical path |
| Management endpoints | Actuator đúng cổng | Exposure/auth theo chính sách |

Thử cả **âm lẫn dương**. Một 403 có thể vì CSRF, authorization, CORS hoặc custom filter; tránh dùng một assertion đơn lẻ để kết luận chính xác lớp bảo vệ.

## 17. Quy trình thực hiện một bộ WebFlux Security Test có thể duy trì

1. **Ghi version đã resolve**: Boot, Framework, Security, `spring-security-test`, Reactor/Netty và test JUnit.
2. **Vẽ web stack**: xác định ứng dụng thật sự dùng Reactive `ServerHttpSecurity`, không chỉ có WebFlux dependency bên cạnh Spring MVC.
3. **Lập manifest chains**: `@Order`, `securityMatcher`, authorization rules, CSRF, CORS, CSP/HSTS, session, authentication.
4. **Tạo mock context client**: `bindToApplicationContext` + `apply(springSecurity())`.
5. **Tạo fixture nhỏ**: một public GET, một admin GET, một state-changing POST, một API JWT endpoint nếu có.
6. **Viết tests negative trước**: anonymous private, USER admin, POST thiếu CSRF, origin lạ, URL bất thường.
7. **Thêm tests positive**: ADMIN, valid CSRF, CORS allowlisted, CSP/nosniff, JWT scope hợp lệ.
8. **Dùng mutator hợp lý**: `mockUser` cho role-based, `mockJwt` cho Resource Server, `mockOAuth2Login` cho OAuth2, `csrf()` cho valid token.
9. **Thêm slice hoặc full-context tests**: `@WebFluxTest` phải import custom security, `@SpringBootTest` bao phủ các beans thực.
10. **Thêm live HTTP tests**: credentials thật, JWT decoder, WebSession cookie, login/logout trên `RANDOM_PORT`.
11. **Thử staging HTTPS**: browser cookie/CORS/CSP, TLS/HSTS, proxy rewrite và firewall semantics.
12. **Theo dõi regression**: khi nâng Spring Security, giữ test contracts thay vì chỉ sửa expected status để suite xanh.

## 18. Bài tập thực hành

### Bài 1 — Gắn đúng security test support

Tạo một ứng dụng WebFlux với `/public/ping` và `/admin/report`. Viết `WebTestClient.bindToApplicationContext(applicationContext).apply(springSecurity())`. Chứng minh:

- GET public không đăng nhập trả 200.
- GET admin không credential bị chặn.
- `mockUser("viewer").roles("USER")` bị 403.
- `mockUser("admin").roles("ADMIN")` được 200.

### Bài 2 — CSRF và authentication cùng tồn tại

Thêm `POST /orders` trong browser chain. Viết test một user đã authenticated nhưng thiếu token bị 403, và test `mutateWith(csrf())` thành công. Giải thích vì sao `permitAll()` không thay CSRF và vì sao 403 cần positive control.

### Bài 3 — JWT scope thay vì role

Tạo Bearer API chain `/api/**` với `/api/admin/**` yêu cầu `SCOPE_admin`. Viết tests cho `mockJwt()` thiếu scope và có scope. Sau đó thêm một HTTP integration test dùng token ký thật nhưng scope sai; so sánh 401 authentication failure và 403 authorization denial.

### Bài 4 — CORS preflight

Frontend `https://app.example.com` gọi `POST /orders` kèm `X-CSRF-TOKEN` và cookie. Viết hai OPTIONS tests cho origin đúng/sai; quan sát `Access-Control-Allow-Origin`/`Access-Control-Allow-Credentials`. Giải thích vì sao một preflight 200 không chứng minh cookie sẽ được browser gửi.

### Bài 5 — CSP, HSTS và HTML frontend

Đặt CSP baseline trên Reactive chain, test `Content-Security-Policy` và `X-Content-Type-Options` qua WebTestClient. Nếu HTML được CDN phát, thiết kế một smoke test riêng trên public HTML URL với CSP `connect-src` và HSTS qua HTTPS.

### Bài 6 — Firewall và URL bất thường

Dùng `StrictServerWebExchangeFirewall` 6.4+ và `StepVerifier` kiểm tra semicolon path bị reject. Dùng WebTestClient context test để kiểm tra HTTP 400, rồi qua ingress xem proxy có rewrite không. Không bật `setAllowSemicolon(true)` chỉ để làm test qua.

### Bài 7 — Test slice thiếu security config

Tạo `@WebFluxTest(SampleController.class)`. Quan sát kết quả khi custom `SecurityWebFilterChain` không được import, sau đó thêm `@Import(ReactiveProtectionConfig.class)` và CORS config. Thêm negative test để chứng minh đã kiểm tra **đúng security policy**, không chỉ controller.

### Bài 8 — Session login/logout qua RANDOM_PORT

Với `@SpringBootTest(RANDOM_PORT)`, dùng test user store riêng và `WebTestClient` gửi Basic hoặc flow form login thật. Duy trì cookie qua requests, kiểm tra session sau login/logout và CSRF token. Giải thích vì sao `mockUser()` của in-memory test không thay được bước xác thực HTTP thực.

## 19. Checklist kỹ thuật trước khi hoàn thành bài test hoặc merge PR

- [ ] Có `spring-security-test` đúng **test scope**, cùng dòng với `spring-security-web`/`spring-security-config` mà Boot BOM quản lý.
- [ ] Test thật sự chạy WebFlux, không vô tình chọn Spring MVC vì cả hai starter cùng xuất hiện.
- [ ] `WebTestClient` in-memory được `bindToApplicationContext` và `apply(springSecurity())`, hoặc một cấu hình tương đương đã được kiểm chứng.
- [ ] `@WebFluxTest` đã import đúng custom `SecurityWebFilterChain`, CORS, authentication/test configuration và functional routes nếu có.
- [ ] Không lẫn package test annotations Boot 3.5 với Boot 4.
- [ ] Có test anonymous private, USER thiếu quyền và ADMIN có quyền; không chỉ test 200.
- [ ] `mockUser()` và `@WithMockUser` được dùng ở mock context, không kỳ vọng chúng mang principal qua TCP.
- [ ] `mockJwt()`/`mockOpaqueToken()` có authorities/claims đúng; có test riêng cho JWT decoder, issuer, signature và audience thật khi cần.
- [ ] Browser POST thiếu CSRF token **bị chặn**; POST token hợp lệ đi tiếp; có test token sai/stale theo repository của ứng dụng.
- [ ] Không dùng helper `csrf()` để khẳng định browser thực đọc và gửi cookie/token; có cookie-aware hoặc browser E2E test.
- [ ] CORS OPTIONS được xử lý theo đúng Reactive source, origin hợp lệ được phép, origin lạ không được cấp allow-origin.
- [ ] CSP/nosniff đã được quan sát trên response của Spring; CSP của HTML frontend/CDN được kiểm chứng ở đúng host.
- [ ] HSTS kiểm tra trên HTTPS public (kể cả reverse proxy), không suy từ in-memory HTTP.
- [ ] HTTP firewall được test từ Spring Security 6.4+, URL semicolon/encoded/traversal không bypass authentication.
- [ ] Multi-chain có `@Order`, matcher cụ thể và fallback; CSRF không bị tắt cho browser bởi API Bearer chain.
- [ ] Login/logout/WebSession cookie và rotation có test qua `RANDOM_PORT` hoặc môi trường tương đương.
- [ ] HTTP tests dùng credentials/test tokens có phạm vi hạn chế; không đưa password, session cookie hoặc Bearer token thật vào logs/artifacts.
- [ ] Có regression suite ổn định khi nâng Spring Security/Boot, tránh thay expected status chỉ để che lỗi chính sách.

## 20. Tài liệu tham khảo chính thức

1. [Spring Security — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html) — `bindToApplicationContext`, `apply(springSecurity())` và cấu hình Reactive test client.
2. [Spring Security — Testing Authentication](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html) — `@WithMockUser` và `mockUser()` cho WebTestClient.
3. [Spring Security — Testing with CSRF](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html) — `SecurityMockServerConfigurers.csrf()`.
4. [Spring Security — Testing OAuth 2.0](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html) — `mockJwt()`, `mockOpaqueToken()`, `mockOAuth2Login()`, `mockOidcLogin()`, `mockOAuth2Client()`.
5. [Spring Security Javadoc — SecurityMockServerConfigurers](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.html) — signatures, mutators, `springSecurity` và `csrf`.
6. [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html) — `@SpringBootTest`, `RANDOM_PORT`, `@WebFluxTest` và `@AutoConfigureWebTestClient`; xem đúng version Boot đang dùng.
7. [Spring Boot 3.5 — Testing](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html) và [Spring Boot 4.x — Testing](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html) — đối chiếu khác biệt package annotation và cách tổ chức test starters.
8. [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html) — `ServerHttpSecurity` và `SecurityWebFilterChain`.
9. [Spring Security — Reactive HTTP Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html) — `pathMatchers`, `hasRole`, `hasAuthority` và `anyExchange`.
10. [Spring Security — Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html) — `CsrfWebFilter`, token repository, BREACH/deferred token và token lifecycle.
11. [Spring Security — Reactive CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html) — CORS source, preflight và origin allowlist.
12. [Spring Security — Reactive Security Headers](https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html) — CSP, HSTS, nosniff và security headers khác.
13. [Spring Security — Reactive ServerWebExchangeFirewall](https://docs.spring.io/spring-security/reference/reactive/exploits/firewall.html) — Strict firewall, path normalization, allowed methods và rejection.
14. [Spring Security — Reactive Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html) — overview của test support, method security và WebFlux test setup.

**Câu hỏi tự đánh giá:** Vì sao `bindToController` không đủ để xác nhận CSRF và authorization? `springSecurity()` thêm gì cho mock `WebTestClient`? Khi nào dùng `mockUser()`, `mockJwt()` và `csrf()`? Tại sao `@WithMockUser` không làm HTTP request trên `RANDOM_PORT` được xác thực? Vì sao phải có cả POST thiếu token lẫn POST có token? Một preflight CORS đúng có chứng minh browser gửi session cookie không? Và kiểm thử nào cho thấy firewall, CSP/HSTS cùng fallback chain vẫn hoạt động sau nâng phiên bản?
