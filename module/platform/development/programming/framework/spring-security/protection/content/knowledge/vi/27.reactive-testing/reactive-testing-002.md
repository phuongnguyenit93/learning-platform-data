# Cấu hình security web filters trong bài kiểm thử

> **Chương:** Kiểm thử Reactive  
> **Module:** `SPRING_SECURITY_HTTP_PROTECTION`  
> **Mục tiêu:** Lắp ghép, quan sát và kiểm thử các **WebFilter bảo mật** trong Spring Security WebFlux: lựa chọn `SecurityWebFilterChain`, authentication, authorization, CSRF, CORS, security headers/CSP/HSTS, HTTP firewall, session và custom WebFilter.  
> **Phạm vi phiên bản:** Spring Security 6.5/7.x, Spring Framework WebFlux và Spring Boot 3.5/4.x; khi dùng API có khác biệt phiên bản phải kiểm tra Javadoc và dependency đã resolve. Nội dung Java minh họa chủ yếu dùng Lambda DSL và JUnit 5.

## 1. Tại sao cấu hình WebFilters là phần cốt lõi của kiểm thử bảo mật Reactive?

Một test controller `GET /admin/report` có thể trả 200 dù application thực tế yêu cầu quyền ADMIN. Lý do có thể rất đơn giản: test dùng `WebTestClient.bindToController(...)`, chỉ dựng mock handler và **không đưa các security WebFilters của ứng dụng vào đường xử lý**.

Ngược lại, một test có `SecurityWebFilterChain` nhưng thiếu CORS filter có thể khiến OPTIONS preflight trả 401 thay vì response CORS hợp lệ. Một test chèn custom WebFilter ở sai thứ tự có thể quan sát rằng request bị từ chối mà không biết đó là CSRF, authorization hay HTTP firewall. Khi sửa test bằng cách tắt Security, ta vô tình loại bỏ chính hành vi cần chứng minh.

**Mục tiêu đúng:** tạo một hệ thống kiểm thử mà request đi qua **cùng loại WebFilter pipeline và cùng chính sách bảo vệ** với ứng dụng; dùng mock principal hoặc token chỉ để cô lập phần xác thực cần thiết.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt `WebFilter` toàn cục, `WebFilterChainProxy`, `SecurityWebFilterChain`, `ServerHttpSecurity.addFilterBefore/After/At` và filter client của `WebTestClient`.
2. Gắn Spring Security vào mock server với `bindToApplicationContext(...).apply(springSecurity())` và nhận biết test chưa chạy Security.
3. Cấu hình security filter tùy chỉnh **trong một chain** bằng `SecurityWebFiltersOrder` mà không đăng ký lặp.
4. Cấu hình global `WebFilter` với `@Order`, hiểu quan hệ với proxy và khi nào filter được chạy trên mọi route.
5. Test nhiều chain với `@Order`/`securityMatcher` và fallback mà không hiểu nhầm `pathMatchers` thành chain matcher.
6. Test negative/positive cho authentication, CSRF, CORS, CSP/HSTS, session và Reactive firewall.
7. Chọn đúng `@WebFluxTest`, `@SpringBootTest`/mock context hoặc live HTTP để không dựa quá mức vào test doubles.

## 2. Ba cấp filter tuyệt đối không được đánh đồng

```text
Client WebTestClient
  |
  +-- ExchangeFilterFunction của client (logging, auth header...)
  |       Chạy ở phía CLIENT, không thay server security
  |
  v
Mock HTTP request / real HTTP request
  |
  v
WebHttpHandlerBuilder / WebFlux WebHandler
  |
  +-- Global WebFilter A @Order(...)
  |
  +-- WebFilterChainProxy (Spring Security)
  |       |
  |       +--> ServerWebExchangeFirewall (Security 6.4+)
  |       |
  |       +--> chọn SecurityWebFilterChain ĐẦU TIÊN phù hợp
  |               |
  |               +--> CORS / CSRF / authentication...
  |               +--> custom security WebFilter được addFilterBefore(...)
  |               +--> authorization / headers...
  |
  +-- Global WebFilter B @Order(...)
  |
  v
Controller / RouterFunction / WebHandler
```

| Cấp | API và nơi cấu hình | Phạm vi | Kiểm thử thế nào? |
| --- | --- | --- | --- |
| **Client filter** | `WebTestClient.configureClient().filter(ExchangeFilterFunction)` | Chỉ phía client: biến đổi request/response client | Quan sát HTTP request được gửi; không suy server an toàn |
| **Global server filter** | Bean `org.springframework.web.server.WebFilter`, `@Order`/`Ordered` | Mọi exchange đi qua WebFlux WebHandler do context quản lý | Bind application context, test trước/sau Security |
| **Security chain filter** | `ServerHttpSecurity.addFilterBefore/After/At(WebFilter, SecurityWebFiltersOrder)` | Chỉ exchange đã match **security chain đó** | Đưa chain vào context, chọn URL/role để chứng minh |
| **Security infrastructure** | `WebFilterChainProxy`, `ServerWebExchangeFirewall` | Chọn chain và ngăn HTTP input nguy hiểm | Integration test + unit firewall |
| **Authentication test mutator** | `SecurityMockServerConfigurers.mockUser()/mockJwt()/csrf()` | Mock `ServerWebExchange` trong test | Test policy, không thay login/JWT decoder thật |

Một Java class implement `WebFilter` có thể được đưa vào global chain **hoặc** vào security chain, nhưng **vị trí đăng ký quyết định scope và order**, không phải tên class. Đăng ký chính nó ở cả hai vị trí có thể khiến nó chạy hai lần.

### 2.1. `SecurityWebFilterChain` không phải `WebFilterChain`

- `SecurityWebFilterChain`: bean Spring Security chứa matcher và danh sách WebFilters **cho một phạm vi request**.
- `WebFilterChain`: interface runtime của WebFlux, cho `WebFilter` gọi `chain.filter(exchange)` để tiếp tục.
- `WebFilterChainProxy`: WebFilter của Spring Security điều phối tập `SecurityWebFilterChain` và tích hợp firewall.

Tên gần giống nhưng vai trò khác. Một test tạo `SecurityWebFilterChain` không có nghĩa controller `/admin/**` tự được bảo vệ: chain đó còn phải được **WebFilterChainProxy** sử dụng trong WebHandler pipeline.

### 2.2. `SecurityWebFiltersOrder` so với `@Order`

`SecurityWebFiltersOrder.CSRF`/`AUTHENTICATION`/`AUTHORIZATION`/... là **mốc thứ tự trong một SecurityWebFilterChain**. `@Order(1)` trên bean `SecurityWebFilterChain` điều khiển **thứ tự xét các chain**. `@Order` trên bean global `WebFilter` điều khiển **vị trí của nó trong WebFlux WebFilter pipeline**. Đây là **ba hệ thứ tự khác nhau**.

Không sửa một lỗi “API chain được chọn trước browser chain” bằng cách đổi `SecurityWebFiltersOrder` của CSRF filter: phải sửa `@Order`/`securityMatcher` của **security chains**.

## 3. Dependency và test setup tối thiểu

### 3.1. Cần `spring-security-test` trong test scope

Ví dụ Gradle Groovy DSL khi Spring Boot quản lý versions:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Trên Boot 4, tổ chức test starters có thể thay đổi; dùng starter tương ứng với phiên bản Boot đã resolve. Điều quan trọng là có `spring-webflux`, `spring-test`, `spring-security-web`/`spring-security-config` và `spring-security-test` cùng dòng tương thích. Đừng ép riêng một phiên bản Spring Security 7 vào BOM Boot 3.x chỉ để import một class.

Maven (test dependencies, các runtime starters do ứng dụng khai báo riêng):

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Kiểm tra resolved versions trong dự án thật bằng `./gradlew dependencyInsight --dependency spring-security-test --configuration testRuntimeClasspath` hoặc `./mvnw dependency:tree -Dincludes=org.springframework.security`. Các dòng lệnh là hướng dẫn, không phải lệnh được chạy trong quá trình viết bài.

### 3.2. Import chính

```java
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import org.springframework.web.server.ServerWebExchange;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
```

`WebFilter` là interface của Spring WebFlux. Nó **không phải** `jakarta.servlet.Filter`; `ServerHttpSecurity` cũng không phải `HttpSecurity` Servlet.

## 4. Cách chính thức gắn Spring Security WebFilters vào WebTestClient

### 4.1. Dựng client từ `ApplicationContext`

```java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

class SecurityFilterIntegrationTest {
    @Autowired ApplicationContext context;
    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }
}
```

Trong một test class thực, cần thêm `@SpringJUnitConfig(...)` hoặc `@SpringBootTest` để `ApplicationContext` có WebFlux infrastructure, controller và Security beans. Đây là cách được hướng dẫn trong **Spring Security WebTestClient Security Setup**: dùng application context với `.apply(springSecurity())` để kích hoạt hỗ trợ test Security.

`bindToApplicationContext` sử dụng Spring WebFlux `WebHttpHandlerBuilder` trên context để dựng pipeline giả lập, gồm các WebFilters mà context quản lý. `springSecurity()` tích hợp phần hỗ trợ mock principal/token với pipeline đó. **Hai điều kiện đều quan trọng**: context phải chứa **đúng security config**, và client phải có **test support đúng** để mutators hoạt động.

### 4.2. `bindToController` và `bindToRouterFunction` không tự mang cả Security của app

```java
// Không dùng làm bằng chứng auth/CSRF của toàn ứng dụng:
WebTestClient controllerOnly = WebTestClient
    .bindToController(new DemoController())
    .build();
```

`bindToController` có ích để test JSON/form binding và business handler, nhưng không tự nạp các bean `SecurityWebFilterChain` từ Spring ApplicationContext. Tương tự, `bindToRouterFunction(route)` chủ yếu dựng functional routing. Muốn kiểm tra Security trong toàn pipeline, ưu tiên `bindToApplicationContext` hoặc cung cấp các WebFilters một cách **tường minh và có kiểm chứng**, không suy từ việc HTTP 200 trả về.

### 4.3. Đưa `WebFilter` thủ công vào mock server (nhưng không thay cả security stack)

`WebTestClient.MockServerSpec` có `webFilter(WebFilter...)`:

```java
WebFilter addTestHeader = (exchange, chain) -> {
    exchange.getResponse().getHeaders().set("X-Test-Filter", "installed");
    return chain.filter(exchange);
};

WebTestClient testOnly = WebTestClient
    .bindToController(new DemoController())
    .webFilter(addTestHeader)
    .build();
```

Code này chứng minh **bạn có thể gắn một WebFilter lên mock handler**. Nó không tự tạo authentication, CSRF, CORS, exception translation, authorization hoặc security headers. Nếu `webFilter(...)` nhận một `WebFilterChainProxy` được dựng đúng cách thì có thể test pipeline ấy, nhưng tự lắp ghép thủ công dễ bỏ sót filter/bean; nên ưu tiên context để kiểm thử chính sách application.

### 4.4. `configureClient().filter(...)` là client-side filter, không phải server filter

```java
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;

ExchangeFilterFunction clientTrace =
    (request, next) -> next.exchange(request);

WebTestClient c = WebTestClient
    .bindToApplicationContext(context)
    .apply(springSecurity())
    .configureClient()
    .filter(clientTrace)  // phía WebClient, KHÔNG phải WebFilter server
    .build();
```

Client filter có thể gắn Basic header, correlation ID hoặc thu thập metadata khi gửi request. Nó không thay `ServerHttpSecurity.addFilterBefore(...)` và không xác nhận phía server thực thi quyền. Đừng log `Authorization` hoặc `Cookie` trong client filter mà không loại bỏ thông tin nhạy cảm.

## 5. Fixture ứng dụng dùng xuyên suốt bài

Để có bài test tái lập, cần một controller và Security config rõ ràng. Ví dụ dùng **HTTP Basic** để dễ phân biệt 401 anonymous với 403 thiếu quyền, đồng thời **giữ CSRF bật** cho unsafe methods. Basic credential có thể được browser tự gửi trong một số tình huống; không lấy HTTP Basic làm lý do tắt CSRF.

### 5.1. Controller thử nghiệm

```java
package com.example.securitytest;

import reactor.core.publisher.Mono;
import org.springframework.web.bind.annotation.*;

@RestController
public class DemoController {

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/admin/report")
    public Mono<String> report() {
        return Mono.just("report");
    }

    @PostMapping("/orders")
    public Mono<String> createOrder() {
        return Mono.just("created");
    }
}
```

### 5.2. Security config có một custom filter **chỉ thuộc security chain**

```java
package com.example.securitytest;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.server.WebFilter;

@Configuration
@EnableWebFluxSecurity
public class DemoSecurityConfig {

    @Bean
    SecurityWebFilterChain web(
            ServerHttpSecurity http,
            CorsConfigurationSource demoCorsSource) {
        // Test-only: marker chỉ được ghi sau khi request vào chain này.
        // KHÔNG khai báo marker thành WebFilter @Bean/@Component toàn cục.
        WebFilter marker = (exchange, chain) -> {
            exchange.getResponse().getHeaders()
                .set("X-Test-Security-Chain", "web");
            return chain.filter(exchange);
        };

        http
            .authorizeExchange(auth -> auth
                .pathMatchers("/public/**").permitAll()
                .pathMatchers("/admin/**").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .cors(cors -> cors.configurationSource(demoCorsSource))
            .csrf(Customizer.withDefaults())
            .httpBasic(Customizer.withDefaults())
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives(
                        "default-src 'self'; object-src 'none'; frame-ancestors 'none'"
                    )
                )
            )
            // Tạo marker trong chain, chạy trước bước authorization.
            .addFilterBefore(marker, SecurityWebFiltersOrder.AUTHORIZATION);

        return http.build();
    }
}
```

`SecurityWebFiltersOrder.AUTHORIZATION` có thật trong enum của Spring Security. Method `ServerHttpSecurity.addFilterBefore` chèn `WebFilter` trước một mốc Security, **không thay thế** chính WebFilter ở mốc đó. Cùng lớp có thể được thêm trước/sau/đúng mốc qua `addFilterBefore`, `addFilterAfter`, `addFilterAt` khi có lý do kiểm soát thứ tự.

Header `X-Test-Security-Chain` là **probe cho test**, không phải header production. Không gửi tên chain, quyền nội bộ hoặc chi tiết nhạy cảm vào response public của hệ thống thật. Nên đặt cấu hình probe trong test profile hoặc test configuration, còn bản production chỉ chứa các filters thực sự cần thiết.

### 5.3. WebFlux infrastructure và test user store

Để test chạy không phụ thuộc Boot auto-config user ngẫu nhiên, có thể tạo một `@SpringJUnitConfig` với `@EnableWebFlux` cùng hai bean controller/user store ở fixture:

```java
package com.example.securitytest;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.web.reactive.config.EnableWebFlux;

@Configuration
@EnableWebFlux
public class DemoWebConfig {

    @Bean DemoController demoController() {
        return new DemoController();
    }

    @Bean
    MapReactiveUserDetailsService testUsers() {
        UserDetails alice = User.withUsername("alice")
            .password("{noop}test-password-only")
            .roles("USER")
            .build();
        UserDetails admin = User.withUsername("admin")
            .password("{noop}test-admin-only")
            .roles("ADMIN")
            .build();
        return new MapReactiveUserDetailsService(alice, admin);
    }
}
```

`@EnableWebFlux` cung cấp WebFlux infrastructure cho context thuần Spring Test; `@EnableWebFluxSecurity` ở config trước đó cung cấp security setup. Mật khẩu `{noop}` chỉ dùng trong fixture test, **không bao giờ dùng production**. Nếu ứng dụng thật có user store bean rồi, đừng vô tình thêm một bean loại này vào context production.

### 5.4. Reactive CORS source dành cho test

Để không lẫn CORS vào quyền truy cập hoặc CSRF, fixture có một source tường minh, chỉ cho phép một origin:

```java
package com.example.securitytest;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
public class DemoCorsConfig {

    @Bean
    CorsConfigurationSource demoCorsSource() {
        CorsConfiguration cfg = new CorsConfiguration();
        cfg.setAllowedOrigins(List.of("https://app.example.com"));
        cfg.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        cfg.setAllowedHeaders(
            List.of("Content-Type", "X-CSRF-TOKEN", "X-XSRF-TOKEN")
        );
        cfg.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", cfg);
        return source;
    }
}
```

`org.springframework.web.cors.reactive.CorsConfigurationSource` là interface WebFlux; Servlet có một interface khác cùng tên. `DemoSecurityConfig` ở mục 5.2 **nhận source này qua dependency injection** và gắn bằng `.cors(cors -> cors.configurationSource(...))`. CORS xử lý preflight phía server, nhưng browser vẫn phải thực thi kiểm soát credential/cookie, CSRF và SOP.

## 6. Test fixture hoàn chỉnh: chứng minh Security WebFilters đã được gắn

Với bốn class ở mục 5 (controller, security, WebFlux infrastructure, CORS), có thể tạo một test **không cần Boot**:

```java
package com.example.securitytest;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

@SpringJUnitConfig(classes = {
    DemoWebConfig.class,
    DemoSecurityConfig.class,
    DemoCorsConfig.class
})
class SecurityPipelineIntegrationTest {

    @Autowired ApplicationContext context;
    WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void publicRequestTraversesSecurityChain() {
        client.get().uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals("X-Test-Security-Chain", "web")
            .expectHeader().valueEquals("X-Content-Type-Options", "nosniff")
            .expectHeader().valueEquals(
                "Content-Security-Policy",
                "default-src 'self'; object-src 'none'; frame-ancestors 'none'")
            .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void adminRequiresCorrectRole() {
        client.mutateWith(mockUser("alice").roles("USER"))
            .get().uri("/admin/report")
            .exchange()
            .expectStatus().isForbidden();

        client.mutateWith(mockUser("admin").roles("ADMIN"))
            .get().uri("/admin/report")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals("X-Test-Security-Chain", "web");
    }

    @Test
    void csrfCannotBeBypassedByAuthentication() {
        client.mutateWith(mockUser("alice").roles("USER"))
            .post().uri("/orders")
            .exchange()
            .expectStatus().isForbidden();

        client.mutateWith(mockUser("alice").roles("USER"))
            .mutateWith(csrf())
            .post().uri("/orders")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("created");
    }
}
```

**Những gì các assertions chứng minh:**

- Có controller/handler và WebFlux WebFilters trong một mock application context.
- Header marker test-only được ghi **trong security chain**, do đó request public đã chạy tới custom filter.
- URL admin bị phân quyền đúng (đòi `ROLE_ADMIN`), trong khi `mockUser()` chỉ thay phần mock authentication.
- `POST /orders` có user hợp lệ nhưng thiếu CSRF vẫn bị 403; có `csrf()` vượt CSRF và được xử lý.

**Những gì chúng chưa chứng minh:** password từ `MapReactiveUserDetailsService` được kiểm tra thực, frontend đọc cookie, CORS được browser thực thi, hoặc HSTS/TLS hoạt động qua proxy. Cần test bổ sung ở các mục sau.

### 6.1. Test âm để phát hiện client chưa gắn Security

Thử nghiệm nhằm minh họa lỗi sai setup (chạy riêng, **không** giữ trong production regression suite):

```java
WebTestClient controllerOnly =
    WebTestClient.bindToController(new DemoController()).build();

// Có thể trả 200 dù không có mock principal:
controllerOnly.get().uri("/admin/report")
    .exchange()
    .expectStatus().isOk();
```

Kết quả 200 ở đây **không cho thấy policy thiếu an toàn**: nó cho thấy test này đang **không áp policy**. Một test có giá trị cần dùng context phù hợp, kiểm tra anonymous/USER bị từ chối và ADMIN được phép. Nếu test trả 404, hãy xác nhận controller mapping trước khi suy về Security.

### 6.2. Vì sao dùng marker header có giới hạn?

Marker hữu ích để kiểm tra custom filter được cài và chạy. Tuy nhiên:

- Marker không chứng minh tất cả security filters đã chạy: response có header test nhưng authorization có thể vẫn bị disable.
- Header chỉ xuất hiện nếu request đi tới vị trí custom filter; CSRF hoặc CORS có thể short-circuit **trước** đó.
- Proxy/CDN cũng có thể thêm headers trùng tên trong test HTTP public.
- Marker test-only không nên xuất hiện trong production; không để lộ nội dung internal chain.

Để đo policy, vẫn cần **negative tests** cho CSRF, authorization và CORS, bên cạnh marker và response headers.

## 7. Đặt custom WebFilter đúng thứ tự trong `ServerHttpSecurity`

### 7.1. Ba API và vai trò

Javadoc của `ServerHttpSecurity` cung cấp:

```java
http.addFilterBefore(customFilter, SecurityWebFiltersOrder.AUTHORIZATION);
http.addFilterAt(customFilter, SecurityWebFiltersOrder.AUTHORIZATION);
http.addFilterAfter(customFilter, SecurityWebFiltersOrder.AUTHORIZATION);
```

`addFilterBefore`/`After`/`At` quy định vị trí tương đối với mốc **nội bộ security chain**. Đây là các cách chọn vị trí độc lập: **không** áp dụng cả ba lần cho cùng một filter như ví dụ liệt kê, trừ khi bạn thật sự muốn chạy nhiều lần. `addFilterAt` không mang nghĩa thay thế WebFilter mặc định ở vị trí đó; khi nhiều filters ở cùng mốc, thứ tự tương đối có thể không rõ ràng, nên ưu tiên `Before/After` với ý đồ cụ thể.

### 7.2. Những vị trí hay gặp

| Mốc | Thành phần/chức năng thường liên quan | Khi nào cần test? |
| --- | --- | --- |
| `HTTP_HEADERS_WRITER` | Header writer | CSP/HSTS/nosniff còn hoạt động trên public/private response |
| `CORS` | Xử lý CORS | Preflight OPTIONS trước authentication |
| `CSRF` | `CsrfWebFilter` | POST thiếu token bị chặn trước xử lý handler |
| `REACTOR_CONTEXT` | `ReactorContextWebFilter` | SecurityContext có được load/propagate |
| `AUTHENTICATION` / `HTTP_BASIC` | Authentication WebFilter | Credential hợp lệ/sai, principal được tạo |
| `ANONYMOUS_AUTHENTICATION` | Anonymous principal | Unauthorized vs anonymous semantics |
| `EXCEPTION_TRANSLATION` | Chuyển exception thành 401/403/redirect | Response và entry point chính xác |
| `AUTHORIZATION` | Quyết định quyền URL | Thiếu quyền không vào handler |

Không suy rằng đây là **mọi filter** hoặc thứ tự tuyệt đối trong mọi phiên bản: xem `SecurityWebFiltersOrder` của jar đang dùng, các custom filters và DSL configurers thực sự được enable. Một filter có thể không được tạo ở chain không bật feature tương ứng.

### 7.3. Probe trước và sau authorization: hành vi trên 403 khác nhau

Giả sử chỉ muốn quan sát request nào đến bước authorization và request nào đã được authorization cho qua. Có thể tạo hai filters độc lập:

```java
WebFilter beforeAuthorization = (exchange, chain) -> {
    exchange.getResponse().getHeaders()
        .set("X-Test-Before-Authorization", "yes");
    return chain.filter(exchange);
};

WebFilter afterAuthorization = (exchange, chain) -> {
    exchange.getResponse().getHeaders()
        .set("X-Test-After-Authorization", "yes");
    return chain.filter(exchange);
};

http.addFilterBefore(
    beforeAuthorization, SecurityWebFiltersOrder.AUTHORIZATION);
http.addFilterAfter(
    afterAuthorization, SecurityWebFiltersOrder.AUTHORIZATION);
```

Nếu request có user nhưng **thiếu ROLE_ADMIN**, authorization thường từ chối mà không gọi phần chain phía sau: marker “before” có thể có, “after” thường không. Với ADMIN hợp lệ, cả hai có thể xuất hiện. Tuy nhiên, **một lỗi CSRF hoặc CORS xảy ra sớm hơn** có thể làm cả hai không chạy. Đây là ví dụ tại sao cần biết **vị trí trong chain** trước khi suy từ header hoặc counter.

Không nên thay `AuthorizationWebFilter`, `CsrfWebFilter` hoặc `AuthenticationWebFilter` bằng một mock `WebFilter` trả `Mono.empty()` để “isolate test”, rồi tuyên bố đã kiểm tra Security của ứng dụng. Muốn isolate một dependency như user store hoặc JWT decoder, hãy mock **dependency** chứ không cắt các filters bảo vệ.

### 7.4. Thao tác trước/sau một reactive chain phải giữ đúng hợp đồng `Mono<Void>`

Một `WebFilter` đúng thường gọi `chain.filter(exchange)`:

```java
import reactor.core.publisher.Mono;
import org.springframework.web.server.WebFilter;

WebFilter tracing = (exchange, chain) -> {
    long start = System.nanoTime();
    return chain.filter(exchange)
        .doFinally(signal -> {
            long elapsed = System.nanoTime() - start;
            // Chỉ ghi số liệu tổng quát, không log token/headers nhạy cảm.
            recordLatency(elapsed);
        });
};
```

`recordLatency` là hàm đo đạc minh họa, không phải API có sẵn của Spring; test code phải cung cấp implementation. **Không gọi `block()` trong WebFilter**, không quên return publisher, không tự subscribe và không thay `return chain.filter(exchange)` bằng `Mono.empty()` nếu request cần đi tới handler.

### 7.5. Test custom filter nên độc lập với việc response đã commit

Nếu muốn ghi một HTTP header, đặt header **trước** khi downstream có thể commit response hoặc đăng ký `response.beforeCommit(...)`. Không cố sửa header trong `doFinally` khi response đã được gửi. Nếu mục tiêu chỉ là test thứ tự invocation, dùng một danh sách events/counter **chỉ thuộc một test instance** và kiểm tra sau khi publisher hoàn tất; tránh shared mutable state giữa các test chạy song song.

## 8. Global `WebFilter`: khác security-chain filter thế nào?

Spring WebFlux đăng ký bean `WebFilter` toàn cục vào `WebHttpHandlerBuilder`. Có thể điều khiển thứ tự bằng `@Order` hoặc `Ordered`. Đây là tầng bên ngoài/bao quanh `WebFilterChainProxy` theo thứ tự toàn cục, không bị giới hạn bởi `securityMatcher("/api/**")`.

### 8.1. Bean WebFilter toàn cục chỉ dùng cho test

```java
package com.example.securitytest;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.web.server.WebFilter;

@Configuration
public class GlobalProbeConfig {

    @Bean
    @Order(Ordered.HIGHEST_PRECEDENCE)
    WebFilter globalProbe() {
        return (exchange, chain) -> {
            exchange.getResponse().getHeaders()
                .set("X-Test-Global-Filter", "yes");
            return chain.filter(exchange);
        };
    }
}
```

Để thử `globalProbe`, nạp `GlobalProbeConfig.class` vào `@SpringJUnitConfig(classes={...})` của một test riêng, sau đó assert header `X-Test-Global-Filter` trên GET public. Global filter không tự kiểm soát role, CSRF hoặc JWT; nó chỉ chứng minh toàn ứng dụng có một WebFilter được WebFlux đăng ký.

### 8.2. Vấn đề đăng ký đôi

Ví dụ **không nên làm**:

```java
// CẢNH BÁO: cùng một WebFilter vừa là bean global...
@Bean
WebFilter customFilter() { return new MyWebFilter(); }

// ...vừa được thêm vào một SecurityWebFilterChain:
http.addFilterBefore(customFilter, SecurityWebFiltersOrder.AUTHORIZATION);
```

Khi WebFlux tự tìm WebFilter beans, filter này có thể chạy **ngoài** Spring Security proxy và **lại chạy thêm** ở trong chain. Nó có thể ghi header lặp, chạy side effect hai lần, mất context hoặc khiến test order khó dự đoán. Nếu muốn filter chỉ thuộc security chain, **tạo nó bên trong config chain hoặc đưa vào một đối tượng không bị auto-register làm global bean**. Nếu muốn global, chỉ khai báo bean và kiểm soát `@Order`, không add thêm vào chain.

`MyWebFilter` ở đây chỉ là tên minh họa; không có class này trong Spring Security.

### 8.3. Global filter chạy “trước Security” không phải lúc nào cũng có authentication

Một global filter có `@Order(Ordered.HIGHEST_PRECEDENCE)` có thể chạy **trước khi Security thiết lập `SecurityContext`**. Đọc `exchange.getPrincipal()` hoặc `ReactiveSecurityContextHolder.getContext()` ở đó có thể chưa cho kết quả như kỳ vọng. Nếu filter cần security context **đã được nạp**, cân nhắc đặt nó trong chain ở vị trí sau `REACTOR_CONTEXT`/authentication phù hợp và dùng reactive context propagation đúng chuẩn; không dùng thread-local Servlet `SecurityContextHolder` như nguồn chân lý trong WebFlux.

### 8.4. Filter toàn cục có thể tiếp tục chạy dù không chain nào match

Một request nằm ngoài mọi `SecurityWebFilterChain` có thể vẫn đi qua **global WebFilters**. Nếu header global xuất hiện, **đừng coi đó là bằng chứng Spring Security đã bảo vệ URL**. Test một URL ngoài matcher hẹp với anonymous/user thiếu quyền và kiểm tra fallback chain hoặc deny-by-default.

## 9. Cấu hình nhiều `SecurityWebFilterChain` và chứng minh chọn đúng chain

Trong ứng dụng thực, một chain dành cho `/api/**` có thể dùng OAuth2 Resource Server/Bearer JWT, còn browser chain dùng form login/session. Bài test cần chứng minh **chọn đúng chain đầu tiên**, không chỉ rằng endpoint cuối cùng trả 200.

### 9.1. Ba bước chọn chính sách

```text
GET /api/admin/report
   |
   v
WebFilterChainProxy
   |
   +-- @Order(1): securityMatcher("/api/**") ?
   |      Có -> chạy chỉ các WebFilters của API chain
   |             -> authorization SCOPE_admin
   |
   +-- Nếu không match:
          @Order(2): browser fallback
             -> authorization ROLE_ADMIN
             -> CSRF, form login, WebSession

Global WebFilters có thể vẫn chạy ngoài cả hai chain.
```

`authorizeExchange(...pathMatchers(...))` không chọn chain; nó chỉ quyết định quyền sau khi chain được chọn. `anyExchange().authenticated()` trong API chain không bảo vệ `/admin/report` **ngoài** `/api/**`. Nếu không có fallback, route ngoài các chain có thể lọt khỏi Spring Security.

### 9.2. Hai chain có marker khác nhau, chỉ dùng trong test

Ví dụ dưới đây là **cấu hình thay thế cho `DemoSecurityConfig` của mục 5.2**, không đăng ký chúng đồng thời trong cùng một context. Để tránh yêu cầu JWT decoder chỉ cho bài test về chain selection, fixture dùng HTTP Basic trên cả hai chain, nhưng **authority policy và marker khác nhau**. Trong app production Bearer, hãy bật Resource Server và test bằng `mockJwt()` cùng decoder ở test tích hợp chuyên biệt.

```java
package com.example.securitytest;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;
import org.springframework.web.server.WebFilter;
import org.springframework.web.cors.reactive.CorsConfigurationSource;

@Configuration
@EnableWebFluxSecurity
public class MultiChainTestSecurity {

    private static WebFilter tag(String value) {
        return (exchange, chain) -> {
            exchange.getResponse().getHeaders()
                .set("X-Test-Security-Chain", value);
            return chain.filter(exchange);
        };
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain api(
            ServerHttpSecurity http, CorsConfigurationSource demoCorsSource) {

        return http
            .securityMatcher(
                ServerWebExchangeMatchers.pathMatchers("/api/**"))
            .authorizeExchange(auth -> auth
                .pathMatchers("/api/admin/**").hasAuthority("SCOPE_admin")
                .anyExchange().authenticated()
            )
            .cors(cors -> cors.configurationSource(demoCorsSource))
            .csrf(Customizer.withDefaults())
            .httpBasic(Customizer.withDefaults())
            .addFilterBefore(tag("api"), SecurityWebFiltersOrder.AUTHORIZATION)
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain browser(
            ServerHttpSecurity http, CorsConfigurationSource demoCorsSource) {

        return http
            // Không có securityMatcher: fallback cho mọi URL còn lại.
            .authorizeExchange(auth -> auth
                .pathMatchers("/public/**", "/error").permitAll()
                .pathMatchers("/admin/**").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .cors(cors -> cors.configurationSource(demoCorsSource))
            .csrf(Customizer.withDefaults())
            .httpBasic(Customizer.withDefaults())
            .addFilterBefore(tag("browser"), SecurityWebFiltersOrder.AUTHORIZATION)
            .build();
    }
}
```

Mặc dù API path tên `/api/**`, ví dụ vẫn bật CSRF: HTTP Basic là credential mà browser có thể tự gửi, nên **không đủ điều kiện** để mặc nhiên tắt CSRF. Với API Bearer-only thực sự không nhận credential tự động, có thể đánh giá việc miễn CSRF cho đúng chain, nhưng không áp dụng quyết định đó cho browser fallback.

### 9.3. Controller thêm cho API test

```java
package com.example.securitytest;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DemoApiController {

    @GetMapping("/api/admin/report")
    public Mono<String> apiAdminReport() {
        return Mono.just("api-report");
    }
}
```

Trong `DemoWebConfig` của fixture multi-chain, thêm một bean:

```java
@Bean DemoApiController demoApiController() {
    return new DemoApiController();
}
```

### 9.4. Kiểm thử mỗi URL thuộc chain nào

```java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

@Test
void apiChainUsesScopeAndNotBrowserRole() {
    client.mutateWith(mockUser("viewer")
            .authorities(new SimpleGrantedAuthority("SCOPE_read")))
        .get().uri("/api/admin/report")
        .exchange()
        .expectStatus().isForbidden()
        .expectHeader().valueEquals("X-Test-Security-Chain", "api");

    client.mutateWith(mockUser("api-admin")
            .authorities(new SimpleGrantedAuthority("SCOPE_admin")))
        .get().uri("/api/admin/report")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals("X-Test-Security-Chain", "api");
}

@Test
void browserChainHasIndependentAuthorization() {
    client.mutateWith(mockUser("viewer").roles("USER"))
        .get().uri("/admin/report")
        .exchange()
        .expectStatus().isForbidden()
        .expectHeader().valueEquals("X-Test-Security-Chain", "browser");

    client.mutateWith(mockUser("admin").roles("ADMIN"))
        .get().uri("/admin/report")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals("X-Test-Security-Chain", "browser");
}
```

Những test này dùng context đã nạp `DemoWebConfig`, `DemoCorsConfig` và **`MultiChainTestSecurity`**, không nạp `DemoSecurityConfig`. Nếu marker nằm **trước** `AUTHORIZATION`, request thiếu quyền vẫn có thể nhận marker. Không suy rằng 403 với marker nghĩa tất cả filters chạy xong; downstream đã bị authorization từ chối.

### 9.5. Test URL ngoài matcher hẹp và method boundary

Với fallback thật:

| Request | Chain kỳ vọng | Kiểm tra |
| --- | --- | --- |
| GET `/api/admin/report` | API | `SCOPE_admin` |
| GET `/admin/report` | Browser | `ROLE_ADMIN` |
| POST `/orders` không token | Browser | CSRF 403 |
| GET `/public/ping` | Browser | `permitAll` nhưng có headers |
| GET `/unknown` không auth | Browser | Thường 401 với HTTP Basic, không bypass |
| GET `/api-v2/orders` không auth | Browser | Không tự nhận API chain |
| OPTIONS `/api/orders` | API | CORS source của API khi được cấu hình |

Thử thêm `/api`, `/api/`, dấu slash kép, trailing slash, encoded slash và public URL sau ingress rewrite. Đừng suy từ một test 404 của controller rằng security matcher đã bảo vệ URL: request có thể không có handler **và** không chain.

## 10. `@WebFluxTest` và full application context: nạp đúng Security WebFilters

Spring Boot web slice test chỉ nạp một phần web infrastructure. Theo tài liệu Boot, `@WebFluxTest` **không tự phát hiện custom bean `SecurityWebFilterChain` của ứng dụng**. Phải `@Import` cấu hình liên quan hoặc dùng `@SpringBootTest`.

### 10.1. Test slice (minh họa package Spring Boot 3.5)

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@WebFluxTest(DemoController.class)
@Import({DemoSecurityConfig.class, DemoCorsConfig.class})
class SecuritySliceTest {
    @Autowired ApplicationContext context;
    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void adminRequiresAuthentication() {
        client.get().uri("/admin/report")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @TestConfiguration
    static class Users {
        @Bean
        MapReactiveUserDetailsService users() {
            return new MapReactiveUserDetailsService(
                User.withUsername("admin")
                    .password("{noop}test-only")
                    .roles("ADMIN")
                    .build()
            );
        }
    }
}
```

Slice config ở trên có WebFlux runtime và controller do `@WebFluxTest` cung cấp, custom Security chain/CORS do `@Import` cung cấp, user store test ở nested `@TestConfiguration`. Nếu ứng dụng còn custom reactive authentication provider, exception handler hoặc WebFilters phụ thuộc bean khác, nạp đúng những bean đó bằng `@Import`/`@MockitoBean` với purpose rõ ràng. Đừng xử lý lỗi thiếu bean bằng `csrf.disable()` hay bỏ Security.

### 10.2. Package thay đổi từ Boot 3.5 sang Boot 4

Đối với Boot 4, ví dụ import:

```java
import org.springframework.boot.webflux.test.autoconfigure.WebFluxTest;
import org.springframework.boot.webtestclient.autoconfigure.AutoConfigureWebTestClient;
```

Với Boot 3.5:

```java
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
```

Không copy hai bộ import vào cùng một class. `@MockitoBean` thuộc Spring Test context (đặc biệt trong các dòng mới), còn `@MockBean` của Boot đời cũ có vòng đời deprecation riêng. Kiểm tra tài liệu **của Boot version đang chạy**, không suy từ tên annotation.

### 10.3. Full context với `@SpringBootTest`

Khi muốn test đúng tất cả Security beans của application:

```java
@SpringBootTest
class FullSecurityContextTest {
    @Autowired ApplicationContext context;
    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }
}
```

`@SpringBootTest` kiểu mặc định không mở network server nếu không chỉ định webEnvironment; `WebTestClient` ở đây vẫn chạy **in-memory**. Ưu điểm: Security config, WebFilters và custom beans của ứng dụng gần hơn thực tế. Nhược điểm: context lớn, test chậm, phụ thuộc databases/identity services, cần thiết lập test fixtures phù hợp.

### 10.4. Khi test functional routing

`@WebFluxTest` không tự tìm thấy mọi functional `RouterFunction` beans. Để test một functional handler với Security, có thể `@Import` đúng router configuration vào slice và dùng `bindToApplicationContext`. Nếu chỉ `bindToRouterFunction(route)` mà không có Security WebFilters, bạn đang kiểm thử router, **không phải** security filter pipeline.

## 11. Kiểm thử CSRF: phải chứng minh filter không bị bỏ qua

Khi có session hoặc credential tự động gửi bởi browser, CSRF là một lớp quan trọng sau khi request đi qua Security chain. Với WebFlux, `CsrfWebFilter` và `ServerCsrfTokenRepository` xử lý token; `csrf()` từ `spring-security-test` cấp một token **hợp lệ trong mock test**.

### 11.1. So sánh request có/không có token

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

@Test
void authenticatedPostWithoutCsrfIsForbidden() {
    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        .exchange()
        .expectStatus().isForbidden();
}

@Test
void authenticatedPostWithCsrfReachesHandler() {
    client.mutateWith(mockUser("alice").roles("USER"))
        .mutateWith(csrf())
        .post().uri("/orders")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("created");
}
```

Khi request thiếu CSRF token, nó có thể bị chặn **trước marker đặt ở `AUTHORIZATION`**; không lấy marker thiếu làm bằng chứng filter chưa được cài. **Positive control** cùng user, cùng endpoint nhưng có `csrf()` giúp phân biệt thiếu CSRF với thiếu quyền.

### 11.2. `permitAll()` không tự tắt CSRF

Một endpoint `POST /public/feedback` được authorization `permitAll` vẫn có thể cần token CSRF nếu thuộc browser chain bật CSRF. Test nên dùng đúng HTTP method: GET thường không cần CSRF, POST/PUT/PATCH/DELETE thường cần. Không suy rằng URL public nghĩa là bỏ qua toàn Security.

Đặc biệt:

```java
// Minh họa hai cấp rule khác nhau:
http.authorizeExchange(a -> a
    .pathMatchers("/public/**").permitAll()
    .anyExchange().authenticated()
);

http.csrf(Customizer.withDefaults());
```

`permitAll` chỉ ảnh hưởng authorization. Nếu cần miễn CSRF một webhook đã xác thực bằng chữ ký độc lập, sử dụng API ignore matcher phù hợp WebFlux **có threat model**, không tắt CSRF ở toàn browser chain chỉ để làm test xanh.

### 11.3. Token sai và token cũ là bài kiểm thử khác với `csrf()`

Đừng giả định WebFlux `csrf()` có cùng helper `useInvalidToken()` như Servlet `MockMvc`. Để test invalid/stale token trong WebFlux:

1. Dùng endpoint bootstrap `GET /csrf` trả token mà Reactive request handler expose, đồng thời giữ WebSession cookie.
2. POST cùng session không header token → phải bị chặn.
3. POST cùng session với token sai → phải bị chặn.
4. POST cùng session với token hợp lệ → qua CSRF, tiếp tục authorization.
5. Đăng nhập/logout thực và kiểm tra token cũ không còn hợp lệ theo token lifecycle của ứng dụng.

`mockUser()` không tự tái hiện `CsrfAuthenticationStrategy` hay session fixation/login handler thành công. Nếu cần kiểm tra thay token sau login/logout, test **luồng authentication thực** bằng HTTP client có cookie jar hoặc WebTestClient RANDOM_PORT.

### 11.4. Không nhầm Servlet SPA `csrf.spa()` với WebFlux

Spring Security 7 Servlet có `HttpSecurity.csrf(csrf -> csrf.spa())` cho SPA cookie/raw header; `ServerHttpSecurity.CsrfSpec` của WebFlux 7.0 không có API `spa()` cùng tên. WebFlux dùng `ServerCsrfTokenRepository`, `ServerCsrfTokenRequestHandler` và `CsrfWebFilter`; khi mặc định dùng XOR masking, token từ request attribute có thể khác token thô trong cookie. Test token lifecycle theo **đúng stack**, không copy handler Servlet sang WebFlux.

## 12. CORS filter: một OPTIONS request có thể dừng trước auth/authorization

Browser SPA khác origin gửi custom header hoặc JSON content type thường gây preflight `OPTIONS`. Preflight thường không có session cookie, nên CORS cần xử lý đúng ở vị trí trước authentication. Spring Security hỗ trợ `ServerHttpSecurity.cors(...)` với `CorsConfigurationSource` Reactive.

### 12.1. Positive CORS preflight trong fixture

```java
@Test
void preflightForAllowedOriginSucceeds() {
    client.options().uri("/orders")
        .header("Origin", "https://app.example.com")
        .header("Access-Control-Request-Method", "POST")
        .header(
            "Access-Control-Request-Headers",
            "content-type,x-csrf-token")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals(
            "Access-Control-Allow-Origin", "https://app.example.com")
        .expectHeader().valueEquals(
            "Access-Control-Allow-Credentials", "true");
}
```

Với CORS source mục 5.4, `OPTIONS` đi qua xử lý CORS mà không cần user; đây **không phải** request nghiệp vụ POST và không chứng minh POST được authorization/CSRF cho qua.

### 12.2. Negative test: origin lạ không được cấp quyền

```java
@Test
void preflightFromOtherOriginIsNotGranted() {
    client.options().uri("/orders")
        .header("Origin", "https://untrusted.example")
        .header("Access-Control-Request-Method", "POST")
        .exchange()
        .expectHeader()
        .doesNotExist("Access-Control-Allow-Origin");
}
```

Origin bị từ chối có thể trả 403 hoặc status khác tùy exception handler/proxy; quy tắc quan trọng là **không cấp `Access-Control-Allow-Origin` cho origin lạ** và không phản chiếu origin tùy ý. Nếu CORS response thay đổi theo Origin, kiểm tra `Vary` phù hợp để CDN/cache không chia sẻ policy sai.

### 12.3. Khi marker nằm sau CORS, header marker có thể không xuất hiện

`CorsWebFilter` có thể hoàn thành preflight ngay và không tiếp tục gọi filters phía sau. Vì marker của fixture được thêm **trước AUTHORIZATION nhưng sau CORS**, đừng buộc OPTIONS response phải có `X-Test-Security-Chain`. Một preflight không có marker vẫn có thể được CORS xử lý **đúng**. Hãy kiểm tra CORS headers và status riêng.

### 12.4. Đừng “sửa” preflight bằng cách tắt CSRF/authorization

Nếu OPTIONS trả 401:

- Có đang dùng đúng `CorsConfigurationSource` của **Reactive** không?
- CORS đã được kích hoạt trong **chain match OPTIONS** chưa?
- Có một global CORS filter hoặc proxy xử lý cùng header gây xung đột không?
- CORS allowedOrigins/Methods/Headers/AllowCredentials có chính xác không?
- Ingress có chặn OPTIONS trước backend không?

`pathMatchers(HttpMethod.OPTIONS, "/**").permitAll()` không thay việc phải trả các `Access-Control-Allow-*` headers đúng. CORS cũng không thay CSRF: browser POST cookie/session vẫn phải có CSRF token hợp lệ.

## 13. Security headers, CSP và HSTS trong WebFilter pipeline

`ServerHttpSecurity.headers(...)` cài các header-writing WebFilters theo policy. `Content-Security-Policy` **không tự được thêm mặc định**; đã có trong fixture vì chúng ta bật explicit. `X-Content-Type-Options: nosniff` thường là header mặc định. HSTS có điều kiện HTTPS và còn phụ thuộc reverse proxy.

### 13.1. Test public response vẫn đi qua headers writer

```java
@Test
void publicEndpointKeepsSecurityHeaders() {
    client.get().uri("/public/ping")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals(
            "Content-Security-Policy",
            "default-src 'self'; object-src 'none'; frame-ancestors 'none'")
        .expectHeader().valueEquals("X-Content-Type-Options", "nosniff");
}
```

Một public GET `permitAll` không nên mất headers nếu nó vẫn đi qua Security chain. Ngược lại, một request bỏ qua tất cả security chains hoặc response từ CDN ngoài ứng dụng **không** được đảm bảo nhận Spring Security headers.

### 13.2. HSTS ở HTTPS public, không chỉ mock HTTP

`Strict-Transport-Security` dành cho HTTPS. WebTestClient in-memory ở `http://localhost` có thể không phát HSTS vì exchange không được nhận là secure, ngay cả khi production public HTTPS có header đúng. Kiểm tra ở đúng HTTPS endpoint:

```bash
curl -i "https://app.staging.example.com/public/ping"
```

Quan sát `Strict-Transport-Security`, `Content-Security-Policy` và `X-Content-Type-Options`. Nếu TLS terminate tại reverse proxy, xác định **ai sở hữu HSTS**, proxy truyền trusted forwarded headers thế nào, và browser nhận policy trên hostname nào. HSTS được browser ghi nhớ theo host, không chỉ theo một security chain URL.

### 13.3. CSP trên JSON API không thay CSP của trang SPA

Nếu HTML của frontend được CDN phát từ `app.example.com`, nhưng WebFlux chỉ trả JSON ở `api.example.com`, CSP `connect-src`/`script-src` cần được áp trên **HTML document** mà browser đang chạy. Spring Security gắn CSP trên response API JSON không thể tự thay CSP của trang HTML do CDN phát. Vì vậy test phải chỉ rõ **response owner**.

### 13.4. Tắt hoặc ghi đè headers là một thay đổi cần regression test

Không dùng `headers(h -> h.disable())` chỉ để làm một iframe hoặc CDN asset chạy. Hãy sửa đúng CSP directive, frame-options policy hoặc tài nguyên được cấp quyền, đồng thời test một URL public và một URL private. Một marker custom filter vẫn xuất hiện khi headers writer bị tắt: **marker không thay thế header assertions**.

## 14. HTTP firewall Reactive: kiểm tra bên ngoài authorization

Từ Spring Security 6.4, `WebFilterChainProxy` hỗ trợ `ServerWebExchangeFirewall`, mặc định `StrictServerWebExchangeFirewall` trong cấu hình có hỗ trợ. Firewall giúp chặn URI/method/headers đáng ngờ trước hoặc trong khi xác định Security chain. Các request như semicolon path hoặc HTTP TRACE có thể bị reject trước khi đến `AuthorizationWebFilter`.

### 14.1. Test trực tiếp firewall bằng `StepVerifier`

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
        MockServerHttpRequest.get("/admin;mode=1/report")
    );

    StepVerifier.create(
        Mono.defer(() -> firewall.getFirewalledExchange(exchange))
    )
        .expectError(ServerExchangeRejectedException.class)
        .verify();
}
```

Test này kiểm tra **instance firewall** độc lập, không tự chứng minh app context đã sử dụng instance ấy. Với một Spring Security version **trước 6.4**, class này chưa có; không bắt buộc thêm import khi dự án còn trên dòng cũ. Javadoc `Since: 6.4` là căn cứ mốc.

### 14.2. Test qua WebTestClient

```java
@Test
void suspiciousPathIsRejectedInDefaultPipeline() {
    client.get().uri("/admin;mode=1/report")
        .exchange()
        .expectStatus().isBadRequest();
}
```

Expected HTTP 400 phụ thuộc default `HttpStatusExchangeRejectedHandler` và việc mock request giữ nguyên semicolon cho firewall. Một proxy hoặc server có thể reject/normalize URI trước Spring, hoặc app có custom handler trả 404. **Status 400 không chứng minh chỉ có firewall chặn**, nên cần unit test lẫn HTTP end-to-end.

### 14.3. Không nới firewall chỉ vì integration test fail

`setAllowSemicolon(true)`, `setAllowUrlEncodedSlash(true)` hoặc `setUnsafeAllowAnyHttpMethod(true)` là các thay đổi chính sách đáng kể. Nếu client gửi encoded slash/matrix variables, ưu tiên thay đổi URL design hoặc thống nhất parser/proxy/route và có security review. Đừng bật các lựa chọn đó chỉ để sửa test status.

### 14.4. Firewall và global filter có quan hệ khác với per-chain filters

Một global `WebFilter` có order trước `WebFilterChainProxy` có thể ghi header trace trước khi firewall reject, trong khi marker **inside security chain** chưa chạy. Điều đó phản ánh vị trí xử lý, không phải mất quyền. Test nên ghi nguyên nhân rejection/exception một cách an toàn, không log raw `Authorization`/cookie/JWT.

## 15. Authentication, Reactor Context và WebSession trong kiểm thử filter chain

### 15.1. Mock authentication khác đăng nhập thật

Trong mock context, `spring-security-test` có các mutators:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
```

`mockUser("admin").roles("ADMIN")` thiết lập principal cho request giả; nó **không** gọi `ReactiveAuthenticationManager`, password encoder hoặc OAuth2 authorization server. `mockJwt()` cũng không tự chứng minh chữ ký JWT/issuer/audience được kiểm tra; test chỉ chứng minh authority/claim mapping theo dữ liệu mock bạn tạo.

Trong chain Resource Server thật có rule `hasAuthority("SCOPE_admin")`, một test có thể dùng:

```java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

client.mutateWith(mockJwt()
        .authorities(new SimpleGrantedAuthority("SCOPE_admin")))
    .get().uri("/api/admin/report")
    .exchange()
    .expectStatus().isOk();
```

Snippet này **không dùng chung với fixture HTTP Basic ở mục 5**, vì fixture ấy không cấu hình JWT. Khi test JWT bằng mock, ứng dụng vẫn cần `oauth2ResourceServer(...jwt(...))` và route tương ứng trong một fixture riêng; để kiểm tra chữ ký/token lifetime cần integration test với `ReactiveJwtDecoder` thật hoặc test issuer.

### 15.2. `ReactorContextWebFilter` và security context

Spring Security Reactive dựa trên Reactor Context để mang `SecurityContext` qua các publisher. Một custom WebFilter cần user identity nên tương tác với `exchange.getPrincipal()` hoặc `ReactiveSecurityContextHolder` bằng API reactive, **không** giả định một ThreadLocal Servlet lưu identity xuyên suốt mọi signal.

Ví dụ custom security filter **chỉ đọc principal**:

```java
import org.springframework.security.core.Authentication;
import org.springframework.web.server.WebFilter;

WebFilter identityProbe = (exchange, chain) ->
    exchange.getPrincipal()
        .cast(Authentication.class)
        .map(auth -> auth.getName())
        .defaultIfEmpty("anonymous")
        .flatMap(name -> {
            // Chỉ là demo: không gửi identity này trong production header.
            exchange.getResponse().getHeaders().set("X-Test-User", name);
            return chain.filter(exchange);
        });
```

Vị trí filter rất quan trọng: nếu đặt **trước** giai đoạn SecurityContext được khôi phục/authentication, principal có thể chưa được thiết lập. Nếu mục tiêu là test identity sau authentication, đặt filter ở vị trí có chủ đích và kiểm tra cả anonymous/authenticated request. Đoạn minh họa không nên dùng như log identity production; tránh dữ liệu nhạy cảm trong headers.

### 15.3. WebSession là một thành phần riêng của mock server

`WebTestClient.MockServerSpec.webSessionManager(...)` cho phép thay `WebSessionManager` của mock server. Mặc định mock server dùng `DefaultWebSessionManager`. Chỉ thay session manager khi test cần mô hình session đặc biệt; không sử dụng một manager mới vô tình cho mỗi request rồi kết luận login/logout không hoạt động.

Nếu app lưu CSRF token trong `WebSessionServerCsrfTokenRepository`, test token round-trip phải:

- Duy trì cookie session giữa GET bootstrap và POST.
- Dùng token **đúng dạng** mà `ServerCsrfTokenRequestHandler` expose.
- Test session hết hạn/logout và token cũ bị invalidated.
- Phân biệt principal do `mockUser()` tạo với security context thực được lưu trong WebSession.

`MockServerSpec.webSessionManager` không thay thế một Redis/cluster session store thật. Test ở nhiều replicas và rolling deploy phải chạy qua HTTP server/session infrastructure phù hợp.

## 16. Từ mock WebFilter pipeline đến HTTP server thật

### 16.1. `RANDOM_PORT`: test authentication bằng HTTP credential

Với Spring Boot application đã có controller và Security config, có thể kiểm tra qua TCP:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class LiveSecurityHttpTest {

    @Autowired WebTestClient http;

    @Test
    void anonymousAdminIsRejected() {
        http.get().uri("/admin/report")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void basicAdminAccessesReport() {
        http.get().uri("/admin/report")
            .headers(headers -> headers.setBasicAuth(
                "admin", "test-admin-only"))
            .exchange()
            .expectStatus().isOk();
    }
}
```

Import `@AutoConfigureWebTestClient` trên thuộc **Boot 3.5**; Boot 4 dùng package `org.springframework.boot.webtestclient.autoconfigure`. Positive test giả định test profile cung cấp user `admin` với password `test-admin-only` và HTTP Basic được bật; **không dùng password này cho production**.

Ở `RANDOM_PORT`, `mockUser()` và `@WithMockUser` chạy trong JVM test không tự mang authentication qua HTTP sang server request. Cần gửi Basic/Bearer token thật qua HTTP, hoặc viết integration test với identity provider/test keys theo phạm vi được phép.

### 16.2. Vì sao vẫn cần `bindToServer` hoặc staging HTTPS?

`WebTestClient.bindToServer()` dùng HTTP client thật:

```java
WebTestClient live = WebTestClient.bindToServer()
    .baseUrl("http://localhost:8080")
    .build();

live.get().uri("/public/ping")
    .exchange()
    .expectStatus().isOk();
```

Ví dụ trên chỉ hợp lệ khi server thật đang chạy ở cổng 8080; với `RANDOM_PORT`, inject client do Spring Boot cấu hình để tránh hard-code port. Client-side `filter(ExchangeFilterFunction)` có thể thêm `Authorization` hoặc metadata, nhưng **không** chạy thay các server-side Security WebFilters.

### 16.3. Các lớp mà mock in-memory chưa mô phỏng đầy đủ

| Thành phần | Mock application context | Live HTTP / staging HTTPS |
| --- | --- | --- |
| SecurityWebFilterChain, CSRF, authorization | Có khi context được cấu hình đúng | Có, theo runtime application |
| WebFlux controller/RouterFunction | Có nếu được nạp | Có theo deployment |
| Authentication provider thật | Không nhất thiết nếu dùng `mockUser` | Có khi gửi credential thật |
| JWT decode/signature/issuer | Không được `mockJwt()` kiểm chứng | Có thể kiểm tra với decoder/provider thử nghiệm |
| HTTP parser, Reactor Netty URI handling | Mock objects | Có HTTP server thực |
| HTTPS/HSTS và trusted forwarding | Thường chỉ mô phỏng | Test qua public ingress |
| Browser CORS/SameSite/CSP | Không có browser engine | Cần browser E2E |
| CDN/cache/rewrite và WAF | Không có | Cần staging tương đồng production |
| Session store đa pod | Không có nếu dùng mock manager | Test theo cụm thực tế |

Không cố đặt mọi test vào `@SpringBootTest(RANDOM_PORT)`: nhiều policy tests có thể chạy nhanh trong mock context. Dùng **tầng test phù hợp** và giữ một nhóm E2E nhỏ, đáng tin cậy cho đường HTTP public.

## 17. Chẩn đoán lỗi cấu hình security WebFilters trong tests

### Lỗi 1 — Controller trả 200 khi anonymous gọi `/admin/**`

**Khả năng:** dùng `bindToController` không có Security, thiếu `springSecurity()`/security config, chain hẹp không match URL hoặc không có fallback.

**Cách xử lý:** kiểm tra test client binding, `WebFilterChainProxy` bean, chain matcher và negative test USER/anonymous. Đừng coi HTTP 200 là thành công nếu contract yêu cầu từ chối.

### Lỗi 2 — `@WebFluxTest` không dùng đúng Security chain

**Khả năng:** slice không import custom `SecurityWebFilterChain`; Spring Boot dựng default security khác hoặc thiếu bean.

**Cách xử lý:** `@Import` config tạo chain, CORS, auth dependencies và router nếu cần. Dùng full `@SpringBootTest` cho phần infrastructure phức tạp. Không disable toàn bộ Security chỉ để nạp slice.

### Lỗi 3 — Custom WebFilter chạy hai lần

**Khả năng:** cùng filter được đăng ký là `@Bean WebFilter` global và `http.addFilterBefore(...)` trong security chain, hoặc mock server `webFilter(...)` còn add thêm một lần.

**Cách xử lý:** chọn **một vị trí sở hữu**: global hoặc selected security chain. Test event count trong một request; không che bằng flag static/global mutable state.

### Lỗi 4 — Marker “sau Authorization” không xuất hiện ở response 403

**Nguyên nhân thường gặp:** authorization từ chối trước khi gọi filter phía sau, hoặc CSRF/CORS short-circuit trước cả authorization.

**Cách xử lý:** phân biệt mốc `AUTHORIZATION` và chuỗi filters; dùng marker trước authz nếu chỉ muốn quan sát request chạm đến bước ấy, và dùng negative/positive policy assertions riêng.

### Lỗi 5 — Test filter đọc principal trước khi auth dẫn tới anonymous

**Khả năng:** global WebFilter có `@Order` chạy trước Security hoặc custom filter trước `REACTOR_CONTEXT`/authentication.

**Cách xử lý:** cân nhắc vị trí trong security chain, đọc `exchange.getPrincipal()` theo reactive contract, và kiểm tra Reactor Context; không dùng `SecurityContextHolder` kiểu ThreadLocal của Servlet.

### Lỗi 6 — POST có user nhưng không token lại được chấp nhận

**Đây là regression bảo mật cần kiểm tra.** `CsrfWebFilter` có bị disable/ignore không? Request đi vào chain nào? Test có vô tình `mutateWith(csrf())` ở client dùng chung? Có đúng HTTP method POST không?

**Cách xử lý:** tạo request mới không kèm token, test đúng URL, xác nhận selected chain và CSRF matcher. Không tắt CSRF để làm “fix”.

### Lỗi 7 — `csrf()` có mặt nhưng POST vẫn 403

**Khả năng:** thiếu quyền, handler token tùy chỉnh, test dùng sai client, CSRF token được lưu ở session khác hoặc request đi vào chain khác.

**Cách xử lý:** so sánh request có/không có token với **cùng principal**, xem loại exception, repository và matcher; đừng kết luận mọi 403 đều do CSRF.

### Lỗi 8 — OPTIONS preflight thiếu marker hoặc trả 401

**Phân biệt:** thiếu marker sau CORS là bình thường nếu CORS hoàn thành preflight; còn 401 khi origin hợp lệ có thể do CORS source sai, OPTIONS rơi vào chain khác hoặc ingress chặn.

**Cách xử lý:** test đầy đủ `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers`; check allow-origin/credentials, security matcher và thứ tự xử lý CORS.

### Lỗi 9 — CSP không xuất hiện dù user đã authenticated

**Khả năng:** `contentSecurityPolicy(...)` chưa được bật (không mặc định), request vào chain khác, response do CDN phục vụ, hoặc headers bị disable.

**Cách xử lý:** test URL public/private cùng owner; xác minh `SecurityWebFilterChain` và header writer. Đừng dùng marker custom làm bằng chứng CSP đã bật.

### Lỗi 10 — HSTS không xuất hiện trong in-memory test

**Khả năng:** request HTTP không được xem là secure; HSTS chỉ cho HTTPS; TLS terminate tại proxy ở production.

**Cách xử lý:** test HTTPS public/trusted forwarded headers/edge HSTS; không đơn giản đổi expected header sang rỗng nếu policy production yêu cầu.

### Lỗi 11 — Firewall trả 400 trên mock, nhưng 404/200 qua gateway

**Khả năng:** ingress/Reactor Netty đã reject/normalize path khác, custom rejected handler đổi status, hoặc proxy rewrite khác với test.

**Cách xử lý:** direct firewall test + mock context + HTTP public staging, kiểm tra request canonical. Không nới encoded slash/semicolon vô điều kiện.

### Lỗi 12 — `mockUser()` pass nhưng Basic login/JWT thật thất bại

**Nguyên nhân:** mock bypass xác thực credential/crypto và mô phỏng principal trong mock exchange.

**Cách xử lý:** test HTTP thật với user store hoặc test issuer; kiểm tra password encoder, decoder, authority mapping và session persistence riêng. `mockJwt().authorities(...)` không tự kiểm thử JWT claim converter thực.

### Lỗi 13 — Test có WebFilter nhưng không có fallback chain

**Khả năng:** chỉ khai báo `@Order(1)` chain `/api/**`, Boot rút auto-config fallback. Global WebFilters vẫn chạy ở `/admin/**` nhưng Spring Security authorization không áp dụng.

**Cách xử lý:** thêm fallback `SecurityWebFilterChain` với `anyExchange` policy rõ, kiểm thử URL ngoài matcher cụ thể.

### Lỗi 14 — Test suite bị rò user/session giữa các testcase

**Khả năng:** shared mutated `WebTestClient`/cookie jar, static mutable markers hoặc test instance lưu `Authentication` ngoài phạm vi request.

**Cách xử lý:** tạo client mới trong `@BeforeEach`, dùng `mutateWith(...)` theo request, reset state test-only, không chia sẻ WebSession/cookies ngoài chủ đích. Test song song cần cô lập thông tin định danh và counters.

### Lỗi 15 — HTTP Basic request được chấp nhận dù credential sai

**Khả năng:** request bị xử lý bởi mock `mockUser()` hoặc test fixture user store không như production; test chỉ kiểm tra status mà không test authentication provider.

**Cách xử lý:** test lại trên `RANDOM_PORT` với HTTP `Authorization: Basic ...` thật và password sai/đúng; không sử dụng mock principal khi mục tiêu là kiểm tra Basic authentication thực.

## 18. Ma trận kiểm thử và quy trình review một thay đổi WebFilter

### 18.1. Ma trận theo lớp bảo vệ

| Request / điều kiện | Filter hoặc tầng chính | Expected result và bằng chứng |
| --- | --- | --- |
| GET `/public/ping` anonymous | Fallback Security chain + authorization | 200 và Security headers; test marker trước authz có thể xuất hiện |
| GET `/admin/report` anonymous | Authentication entry point | 401 hoặc redirect theo chain, không vào handler |
| GET admin với `ROLE_USER` | Authorization | 403; không nhầm thiếu CSRF |
| GET admin với `ROLE_ADMIN` | Authentication mock + authorization | 200, đúng body và headers |
| POST `/orders` user hợp lệ, thiếu CSRF | `CsrfWebFilter` | 403 trước xử lý nghiệp vụ |
| POST `/orders` user + `csrf()` | CSRF + authorization | Qua Security và handler trả kết quả mong đợi |
| OPTIONS `/orders` origin được phép | `CorsWebFilter` | Response CORS đúng; không cần user |
| OPTIONS `/orders` origin lạ | `CorsWebFilter` | Không cấp `Access-Control-Allow-Origin` |
| GET `/admin;v=1/report` | HTTP firewall (6.4+) hoặc parser | Request bất thường bị chặn, xác định nguồn |
| GET API admin scope thiếu | Security chain API + authorization | 403, marker API nếu tới vị trí probe |
| GET `/unknown` anonymous | Browser fallback chain | Bị authentication/authorization chặn, không bypass |
| GET HTML frontend qua HTTPS | Header writer hoặc CDN/edge | CSP, HSTS, nosniff theo response owner |
| Login/logout với WebSession | Authentication/CSRF/session | Token/session thay đổi đúng lifecycle |
| HTTP Basic password sai qua TCP | AuthenticationManager/provider thật | 401, không dùng `mockUser()` |
| JWT ký sai/expired qua TCP | `ReactiveJwtDecoder` thật | 401; khác 403 do thiếu scope |
| HTTP request có custom client filter | `ExchangeFilterFunction` phía client | Header/request client được biến đổi, không chứng minh server filters |

Một request có thể bị chặn **trước** một filter bạn đang quan sát. Đừng biến việc “marker phải xuất hiện trên mọi response” thành policy: hành vi đó có thể sai về order. Hãy xác định **filter nào được phép short-circuit** và test từng quyết định bảo mật bằng expected status/header/body riêng.

### 18.2. Quy trình sáu bước để thay một custom WebFilter

1. **Xác định scope:** filter là global `WebFilter` hay thuộc API/browser `SecurityWebFilterChain`? Ghi rõ URL/method được ảnh hưởng.
2. **Chọn vị trí:** chỉ định mốc `SecurityWebFiltersOrder` hoặc global `@Order`. Tránh đặt trước authentication nếu cần identity đã xác thực.
3. **Đặt dữ liệu test:** dùng fixture có controller public, protected GET, state-changing POST, CORS source, user store và fallback chain.
4. **Đo trước/sau:** test user thường/ADMIN, CSRF thiếu/đúng, CORS allowed/denied, security headers và negative URL.
5. **Kiểm tra không đăng ký đôi:** filter không cùng lúc là global bean và per-chain filter trừ khi đó là một quyết định có chủ đích được chứng minh.
6. **Xác minh qua HTTP thật:** nếu filter động tới session, forwarding, raw URI, cookie hoặc authentication credential, dùng `RANDOM_PORT`/HTTPS staging bên cạnh mock context.

### 18.3. Các cấp kiểm thử phù hợp với chi phí

```text
Unit Test WebFilter
  - gọi filter.filter(exchange, chain) trực tiếp
  - kiểm tra marker, publisher completes, chain được gọi
      |
      v
Mock WebFlux integration
  - bindToApplicationContext + apply(springSecurity)
  - authentication/authorization/CSRF/CORS/headers, chain selection
      |
      v
SpringBootTest RANDOM_PORT
  - HTTP server parser, Basic/JWT decoder, cookies, session thật
      |
      v
Staging HTTPS / Browser E2E
  - TLS proxy, CDN, HSTS, CSP, CORS browser, SameSite/cookie
```

Giữ phần lớn policy tests ở mock integration để chạy nhanh, nhưng **không** bỏ các test HTTP public có giá trị cao; hai cấp kiểm thử giải quyết những rủi ro khác nhau.

## 19. Bài tập thực hành

### Bài 1 — Chứng minh test đang chạy Security

Viết một `DemoController` có `GET /admin/report`. So sánh `WebTestClient.bindToController(...)` và `bindToApplicationContext(...).apply(springSecurity())`. Tại sao client đầu có thể trả 200 cho anonymous còn client sau phải chặn? Giải thích vì sao lỗi không nằm ở business handler.

### Bài 2 — Filter bên trong chain

Thêm một `WebFilter` test-only vào `ServerHttpSecurity.addFilterBefore(..., SecurityWebFiltersOrder.AUTHORIZATION)`, ghi `X-Test-Security-Chain`. Viết tests GET public, GET admin với USER, GET admin với ADMIN, POST thiếu CSRF. Ở request nào marker có thể không xuất hiện dù Security hoạt động đúng?

### Bài 3 — Global filter vs per-chain filter

Khai báo một global `WebFilter` với `@Order(Ordered.HIGHEST_PRECEDENCE)` và một filter riêng của API chain. Viết test cho `/api/admin/**`, `/admin/**` và `/unknown`. Chứng minh global filter có thể chạy trong mọi URL còn API marker chỉ xuất hiện ở API chain. Không dùng marker làm bằng chứng authorization.

### Bài 4 — Đăng ký đôi

Đặt cùng một `WebFilter` vào global context và `addFilterAfter(...)` trong chain; dùng counter chỉ thuộc test để đo số lần chạy. Sửa config để filter chỉ được đăng ký một lần, giải thích vì sao cấu hình ban đầu nguy hiểm khi filter có side effect.

### Bài 5 — Thứ tự trước/sau authorization

Thêm hai probes trước và sau `SecurityWebFiltersOrder.AUTHORIZATION`. Gọi `GET /admin/report` với USER và ADMIN. Vì sao request 403 có thể chỉ chạy probe “before”? Thử lại với `POST /orders` thiếu CSRF và phân tích lý do cả hai probes có thể không chạy.

### Bài 6 — CSRF và CORS độc lập

Giữ CSRF cho browser session. Test `POST /orders` với và không với `csrf()`. Đồng thời test OPTIONS origin allowlisted và origin không được phép. Tại sao CORS OPTIONS không bắt buộc chạy tới `AuthorizationWebFilter`, nhưng POST cookie vẫn cần CSRF?

### Bài 7 — Test slice thiếu cấu hình

Tạo `@WebFluxTest(DemoController.class)`. Quan sát nếu không import `DemoSecurityConfig`/`DemoCorsConfig`. Bổ sung `@Import` và test user store. Thêm hai negative tests (admin USER 403, POST thiếu CSRF 403) để chứng minh slice đang chạy đúng Security.

### Bài 8 — Multi-chain và fallback

Tạo API chain `@Order(1)` với matcher `/api/**`, browser chain `@Order(2)` fallback. Dùng hai test-only markers khác nhau. Kiểm tra `/api/admin/report` cần `SCOPE_admin`, `/admin/report` cần `ROLE_ADMIN`, `/unknown` anonymous vẫn bị chặn. Sau đó cố ý đặt fallback `@Order(0)` rồi giải thích vì sao API chain không còn được chọn.

### Bài 9 — Reactive firewall

Trên Spring Security 6.4+, kiểm thử `StrictServerWebExchangeFirewall` với `StepVerifier` cho `/admin;mode=1/report`. Sau đó kiểm tra qua `WebTestClient` và staging ingress. Giải thích vì sao HTTP 400 có thể xuất phát từ proxy/parser chứ không nhất thiết Spring firewall.

### Bài 10 — Chuyển mock test sang HTTP real

Một test `mockUser("admin")` cho phép `GET /admin/report`. Viết test `RANDOM_PORT` gửi Basic credentials thật và test password sai. Nếu ứng dụng dùng Resource Server, thay bằng token JWT ký từ test issuer. Liệt kê những rủi ro mock test chưa kiểm tra: password encoder, JWT decoder, session cookie, HSTS và forward headers.

## 20. Checklist trước khi merge test/security configuration

- [ ] Web stack là **Reactive WebFlux**; không nhập nhằng Servlet `FilterChainProxy`/`SecurityFilterChain` với Reactive `WebFilterChainProxy`/`SecurityWebFilterChain`.
- [ ] Test đã gắn đúng `WebTestClient.bindToApplicationContext(...).apply(springSecurity())` hoặc cơ chế tương đương được kiểm chứng.
- [ ] `ApplicationContext` của test chứa đúng controller/router, các custom `SecurityWebFilterChain`, CORS source và dependencies.
- [ ] `@WebFluxTest` có `@Import` security config cần thiết; không bật cấu hình lỏng chỉ để vượt lỗi thiếu bean.
- [ ] Đã phân biệt client `ExchangeFilterFunction`, global `WebFilter` và security chain `WebFilter`.
- [ ] Một filter không bị đăng ký lặp ở global bean, mock `webFilter(...)` và `addFilterBefore(...)`.
- [ ] Custom security filter có vị trí `SecurityWebFiltersOrder` đúng và không `block()` hoặc subscribe thủ công.
- [ ] Test quan sát principal sau khi SecurityContext được thiết lập, có kiểm tra Reactor Context theo reactive contract.
- [ ] Có test anonymous/USER/ADMIN và fallback URL; không chỉ test 200.
- [ ] Browser POST với user nhưng thiếu CSRF bị chặn; token hợp lệ đi tiếp; có test token cũ/sai khi repository được tùy chỉnh.
- [ ] CORS preflight origin được phép thành công, origin lạ không được cấp allow-origin; OPTIONS không bị auth chặn nhầm.
- [ ] CSP được kiểm tra trên đúng response HTML, nosniff trên app response, HSTS qua HTTPS public.
- [ ] Reactive firewall từ Security 6.4+ được test cho URL bất thường; không nới semicolon/encoded slash tùy tiện.
- [ ] Multi-chain `@Order` và `securityMatcher` được kiểm tra; có fallback chain bao phủ URL ngoài matcher cụ thể.
- [ ] `mockUser()`/`mockJwt()` không bị nhầm với kiểm thử password/JWT signature thực; có live HTTP tests cho credential.
- [ ] Login/logout/session cookie được kiểm tra trong HTTP client có duy trì cookie; không lưu credentials trong log.
- [ ] Test data/probe headers/counters chỉ tồn tại ở test profile, không lộ nội bộ ứng dụng ra production.
- [ ] Có các negative tests rõ nguyên nhân 400/401/403/404 và HTTP staging tests khi proxy/ingress ảnh hưởng đường dẫn.

## 21. Nguồn tham khảo chính thức

1. [Spring Security — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html) — `bindToApplicationContext` và `apply(springSecurity())`.
2. [Spring Security — WebFlux Security Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html) — `ServerHttpSecurity`, `SecurityWebFilterChain`, multi-chain, `@Order` và fallback.
3. [Spring Security API — ServerHttpSecurity](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html) — `securityMatcher`, `addFilterAt`, `addFilterBefore`, `addFilterAfter`.
4. [Spring Security API — SecurityWebFiltersOrder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/SecurityWebFiltersOrder.html) — mốc thứ tự CSRF, CORS, authentication, authorization và headers.
5. [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html) — mock controller, router, application context, live server và client configuration.
6. [Spring Framework API — WebTestClient.MockServerSpec](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/web/reactive/server/WebTestClient.MockServerSpec.html) — `webFilter(WebFilter...)`, `webSessionManager(...)` và `apply(MockServerConfigurer)`.
7. [Spring Framework — WebFlux Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html) — `WebFilter`, `WebExceptionHandler`, `@Order` và WebHandler pipeline.
8. [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html) — `@WebFluxTest`/`@SpringBootTest`, import custom Security chain và test slices.
9. [Spring Security — Reactive Test Authentication](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html), [Testing with CSRF](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html), [OAuth 2.0 Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html) — `mockUser()`, `csrf()`, `mockJwt()` và các mutators.
10. [Spring Security — Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html), [Reactive CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html) và [Reactive Security Headers](https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html) — các lớp phòng vệ cụ thể.
11. [Spring Security — Reactive HTTP Firewall](https://docs.spring.io/spring-security/reference/reactive/exploits/firewall.html) — `StrictServerWebExchangeFirewall` và rejection handler.
12. [Spring Boot — Reactive Web Filters](https://docs.spring.io/spring-boot/reference/web/reactive.html) — tự động đăng ký global `WebFilter` beans và thứ tự với Spring Security proxy.

**Tự đánh giá:** `WebTestClient.configureClient().filter(...)` khác `ServerHttpSecurity.addFilterBefore(...)` ở đâu? `@Order` của `SecurityWebFilterChain` có cùng ý nghĩa với `SecurityWebFiltersOrder` không? Vì sao `bindToController` có thể trả 200 cho anonymous ngay cả khi production bảo vệ `/admin/**`? Tại sao không nên đăng ký cùng một WebFilter thành global bean và per-chain filter? Một OPTIONS preflight không có marker trước authorization có thể là hành vi đúng không? Làm thế nào chứng minh CSRF, CORS, CSP/HSTS, HTTP firewall, fallback chain và session vẫn được bảo vệ sau khi thay filter order?
