# authorizeExchange và nguyên tắc áp dụng quy tắc theo thứ tự

> **Chủ đề:** Phân quyền HTTP trong Spring Security **reactive / Spring WebFlux**, dùng Spring Boot 3.x, Spring Security 6.x và Java 17+. Trọng tâm là `ServerHttpSecurity.authorizeExchange(...)`, quy tắc **đầu tiên khớp request quyết định policy**, cách đặt matcher đặc thù trước matcher tổng quát, và phân biệt thứ tự rule với thứ tự chọn `SecurityWebFilterChain`.

## Mục tiêu

Sau bài này, bạn có thể:

1. Mô tả cách Spring Security áp dụng authentication rồi authorization cho HTTP request trong WebFlux.
2. Khai báo `authorizeExchange(exchanges -> exchanges...)` với `pathMatchers`, `permitAll`, `authenticated`, `hasRole`, `hasAuthority`, `denyAll`, `anyExchange`.
3. Dự đoán **rule nào sẽ được chọn** khi cùng một URL khớp nhiều path patterns.
4. Phát hiện lỗ hổng do `/api/**` hoặc `/**` đứng trước `/api/admin/**`.
5. Bảo vệ riêng endpoint theo HTTP method, role và scope.
6. Chạy một ứng dụng Spring Boot/WebFlux với Java 17+ và kiểm thử `WebTestClient` cho kết quả 200/401/403.
7. Phân biệt `http.securityMatcher(...)` chọn chain với `authorizeExchange().pathMatchers(...)` chọn rule trong chain.
8. Biết khi nào CORS, CSRF, path variables và quyền sở hữu tài nguyên cần được xem xét riêng.

## 1. Phân quyền HTTP diễn ra ở đâu?

Trong Spring WebFlux, request đi qua các `WebFilter`. Spring Security đăng ký `WebFilterChainProxy` để chọn `SecurityWebFilterChain` phù hợp. Chain được chọn chứa các filter liên quan đến security context, xác thực, phân quyền, CSRF và xử lý lỗi. Nếu request không được cho phép, request có thể kết thúc trước khi `DispatcherHandler` gọi controller hoặc functional handler.

```text
HTTP request (method, path, Authorization header)
       |
       v
WebFlux WebFilter pipeline
       |
       v
Spring Security WebFilterChainProxy
       |
       +-- Chọn SecurityWebFilterChain theo securityMatcher / @Order
       |
       +-- Authentication: xác minh credential, tạo Authentication
       |
       +-- Authorization: chọn rule trong authorizeExchange
       |     |
       |     +-- rule #1 có khớp?
       |     |     +-- Có -> đánh giá quyền và dừng chọn rule
       |     |     +-- Không -> rule #2
       |     +-- rule #2 ...
       |     +-- fallback anyExchange()
       |
       +-- Không đủ quyền: chặn (thường 401/403 tùy tình huống)
       |
       v
DispatcherHandler
       |
       +-- @RestController / annotated handler
       +-- RouterFunction / functional handler
       |
       v
HTTP response
```

Sơ đồ chỉ mô tả các **bước quyết định logic**, không phải thứ tự vật lý của toàn bộ filter. Spring Security HTTP authorization áp dụng theo `ServerWebExchange`, không phụ thuộc handler được viết bằng `@RestController` hay `RouterFunction`.

### Authentication khác Authorization

| Khái niệm | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| Authentication | Người gọi **là ai**? | HTTP Basic kiểm password, tạo principal `reader` |
| Authorization | Người gọi **được làm gì**? | `/api/admin/**` đòi `ROLE_ADMIN` |
| Rule matcher | Quy tắc nào áp dụng cho request này? | `GET /api/reports/**` |
| Authentication entry point | Người chưa xác thực được xử lý thế nào? | Basic trả 401/challenge; form login có thể redirect |
| Access denied handling | Người đã xác thực nhưng thiếu quyền nhận gì? | Thường 403 |
| Security chain matcher | Bộ `WebFilter` nào xử lý request? | `securityMatcher("/api/**")` với matcher thích hợp |

**Đừng nhầm:** “Đã đăng nhập” không đồng nghĩa “được phép gọi mọi API”. `authenticated()` chỉ yêu cầu principal đã xác thực; `hasRole("ADMIN")`, `hasAuthority("SCOPE_reports.read")` hoặc business authorization mới giới hạn quyền cụ thể.

## 2. Nguyên tắc cốt lõi: thứ tự khai báo quyết định

Trong Spring Security reactive, các rule được xét theo **thứ tự đăng ký**. Rule **đầu tiên khớp** request chọn một authorization policy. Nếu policy từ chối request, Spring Security không tiếp tục thử rule phía dưới để tìm một rule “dễ hơn”.

Ví dụ:

```java
http.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/public/**").permitAll()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .pathMatchers("/api/**").authenticated()
    .anyExchange().denyAll()
);
```

Đây là một **đoạn trong method cấu hình**, không phải class độc lập. Nó có kết quả:

- `GET /public/ping` → khớp `/public/**` → public.
- `GET /api/admin/stats` → không khớp public, **khớp admin** → cần `ROLE_ADMIN`. Người dùng chỉ có `ROLE_READER` bị từ chối.
- `GET /api/profile` → khớp `/api/**` → chỉ cần đã xác thực.
- `GET /unlisted` → khớp fallback `anyExchange()` → từ chối mọi người.

**Spring Security không tự sắp xếp path dài hơn trước path ngắn hơn.** Thứ tự trong DSL thể hiện ý định chính sách của bạn.

### 2.1 Phản ví dụ: rule rộng đứng trước rule hẹp

```java
// SAI nếu /api/admin/** chỉ dành cho ADMIN:
http.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/**").authenticated()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().denyAll()
);
```

Request `GET /api/admin/stats` khớp ngay `/api/**`. Một user `reader` đã đăng nhập được `authenticated()` chấp thuận **trước khi** Spring Security có cơ hội xét `hasRole("ADMIN")`. Rule admin bị **che** (rule shadowing); chính sách có lỗ hổng dù không có lỗi biên dịch.

Sửa:

```java
http.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .pathMatchers("/api/**").authenticated()
    .anyExchange().denyAll()
);
```

Tóm tắt: **Đặt URL cụ thể, nhạy cảm và ngoại lệ có chủ đích trước URL bao quát**. `anyExchange()` nên đặt cuối, không phải đầu.

### 2.2 Không tự cộng dồn nhiều rule

Hai rule này **không** có nghĩa “phải có cả FINANCE và SCOPE_approved”:

```java
.pathMatchers("/api/finance/**").hasRole("FINANCE")
.pathMatchers("/api/finance/**").hasAuthority("SCOPE_approved")
```

Rule thứ nhất đã match path; rule thứ hai không được đánh giá cho cùng request. Khi cần phối hợp nhiều điều kiện AND/OR, hãy sử dụng **một** custom `ReactiveAuthorizationManager` được đăng ký qua `.access(...)`, hoặc đặt logic nghiệp vụ trong service/method security và kiểm thử riêng.

### 2.3 “Matcher khớp” khác với “policy cho phép”

Giả sử rule đầu tiên khớp `/api/admin/stats` với `hasRole("ADMIN")` và principal là reader. Đây không phải “rule không khớp vì user thiếu role”; **matcher đã khớp**, nhưng **authorization decision là denied**. Spring Security không chuyển sang `/api/**.authenticated()`.

Đây là lý do một policy “thử lần lượt đến khi có rule cho phép” sẽ nguy hiểm; thực tế Spring Security chọn **rule đầu tiên có matcher khớp request** và quyết định theo rule đó.

## 3. Các phép phân quyền thông dụng

| DSL | Điều kiện | Trường hợp phù hợp |
| --- | --- | --- |
| `permitAll()` | Không yêu cầu principal đã đăng nhập | Endpoint công khai có chủ đích |
| `authenticated()` | Yêu cầu `Authentication` hợp lệ theo Spring Security | Profile riêng của người dùng đã đăng nhập, nhưng vẫn cần kiểm tra ownership khi cần |
| `hasRole("ADMIN")` | Cần authority `ROLE_ADMIN` | Admin UI/API |
| `hasAuthority("SCOPE_reports.read")` | Cần authority đúng chuỗi `SCOPE_reports.read` | Scope hoặc granular permission |
| `denyAll()` | Từ chối mọi request khớp rule | Fallback deny by default |
| `anyExchange()` | Matcher bắt mọi exchange trong **chain** còn lại | Rule cuối hoặc baseline rõ ràng |
| `access(customManager)` | Ủy quyền cho policy tùy chỉnh | Tenant, ownership, kết hợp nhiều điều kiện |

### 3.1 `hasRole` vs `hasAuthority`

`hasRole("ADMIN")` dùng tiền tố role mặc định `ROLE_` và kiểm tra authority `ROLE_ADMIN`. Khi tạo user bằng `User.roles("ADMIN")`, builder tự tạo `ROLE_ADMIN`. Không đưa `"ROLE_ADMIN"` vào `hasRole(...)` trừ khi biết rõ API và prefix đã được thay đổi.

`hasAuthority("SCOPE_reports.read")` so khớp **đúng tên authority**. Một JWT có scope cần được decoder/provider kiểm chứng và mapper cấp authorities phù hợp trước khi rule kiểm tra. Chỉ viết `hasAuthority` không xác minh chữ ký token.

### 3.2 `permitAll` không đồng nghĩa bỏ qua WebFilter

Dù `/public/**` được `permitAll`, request vẫn đi qua security chain nếu chain match. Authentication filter có thể xử lý Basic credential người gọi đã gửi và thất bại, CSRF filter có thể chặn method không an toàn, CORS có thể ảnh hưởng browser. Public rule chỉ nói authorization không yêu cầu quyền, **không phải** “mọi security filter được tắt”.

### 3.3 `authenticated` không thay thế kiểm tra quyền theo dữ liệu

Giả sử `GET /api/orders/{orderId}` chỉ cần `authenticated()`; người dùng A có thể thử orderId của người dùng B. HTTP rule cần phối hợp service-layer kiểm tra owner/tenant. Phân quyền theo URL chỉ là lớp kiểm soát truy cập **ở cửa vào**, không đảm bảo data-level access một cách tự động.

### 3.4 `denyAll` vs `authenticated` cho fallback

`anyExchange().denyAll()` có nghĩa endpoint không được khai báo chính sách cụ thể sẽ **không vô tình được phép**. Đây là lựa chọn tốt cho API có allowlist. `anyExchange().authenticated()` có thể phù hợp với ứng dụng mà hầu hết URL đều dành cho user đã đăng nhập, nhưng phải chú ý endpoint admin chưa có rule đặc thù có thể bị mở cho mọi user authenticated.

## 4. HTTP method cũng là một phần của matcher

WebFlux hỗ trợ:

```java
.pathMatchers(HttpMethod.GET, "/api/orders/**").hasRole("READER")
.pathMatchers(HttpMethod.POST, "/api/orders").hasAuthority("SCOPE_orders.write")
```

Đây là các dòng DSL cần đặt trong `authorizeExchange` với `HttpMethod` từ `org.springframework.http.HttpMethod`. Phải kiểm tra path và method **thực tế được server nhận**.

Ví dụ cấu hình method-specific có thứ tự:

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers(HttpMethod.POST, "/api/orders")
        .hasAuthority("SCOPE_orders.write")
    .pathMatchers(HttpMethod.GET, "/api/orders/**")
        .hasRole("READER")
    .pathMatchers("/api/**")
        .authenticated()
    .anyExchange().denyAll()
)
```

Nếu đặt `/api/**.authenticated()` trước hai dòng cụ thể, cả POST lẫn GET có thể chỉ còn cần đăng nhập và bỏ qua scope/role của từng hành động.

**Lưu ý CSRF:** Spring Security WebFlux thường bật CSRF protection mặc định. Một POST có password/role đúng vẫn có thể nhận 403 **vì thiếu CSRF token** trước khi authorization rule thể hiện kết quả. Khi test request thay đổi dữ liệu, gửi CSRF token hợp lệ với browser/cookie clients hoặc thiết kế CSRF policy đúng threat model cho API, không tắt toàn app để chữa test.

### 4.1 GET, HEAD và OPTIONS

Khi rule chỉ ghi `HttpMethod.GET`, đừng mặc định nó đã cho phép mọi `HEAD` hoặc `OPTIONS` trong mọi cấu hình. Browser có thể gửi `OPTIONS` preflight khi API dùng Authorization header và cross-origin request. Preflight cần xử lý bằng CORS configuration phù hợp với security, không chữa bằng `anyExchange().permitAll()`.

### 4.2 Path prefix, base path và proxy

Matcher xét request path mà WebFlux nhìn thấy. Những khác biệt như `spring.webflux.base-path`, route rewrite ở gateway, dấu slash cuối đường dẫn, encoded path variables và tên path khác giữa controller với security có thể khiến rule mong muốn không khớp. Nếu thấy `403` từ fallback dù user đủ quyền, kiểm tra **path/method được nhận**, không chỉ nhìn URL ở frontend.

## 5. Ứng dụng thực hành hoàn chỉnh

Ta tạo một ứng dụng Spring Boot 3.x / Java 17+ chỉ có **một `SecurityWebFilterChain`**, in-memory user store reactive và nhiều GET routes được phân quyền khác nhau. Ví dụ dùng **HTTP Basic** để test credential/role đơn giản; các quy tắc `authorizeExchange` vẫn áp dụng với cơ chế xác thực khác như OAuth2 Bearer JWT hoặc session.

### 5.1 Dependencies

Trong `build.gradle` của Spring Boot project đã có plugin/dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Dùng WebFlux server thực sự. Không đồng thời thêm `spring-boot-starter-web` (MVC) vào bài thực hành; khi có cả MVC và WebFlux, Spring Boot thường chọn MVC/Servlet mặc định. `SecurityWebFilterChain`/`ServerHttpSecurity` dành cho **reactive HTTP stack**, khác `SecurityFilterChain`/`HttpSecurity` của Servlet.

Cấu trúc file:

```text
src/main/java/com/example/orderrules/
  RuleOrderApplication.java
  AccessRulesConfig.java
  DemoController.java
src/test/java/com/example/orderrules/
  AuthorizationOrderTest.java
```

Mỗi class Java `public` phải là file riêng đúng tên. Các đoạn dưới cần Spring Boot dependencies và Gradle wrapper, không phải chương trình Java SE chạy bằng `javac` trần.

### 5.2 RuleOrderApplication.java

`src/main/java/com/example/orderrules/RuleOrderApplication.java`:

```java
package com.example.orderrules;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RuleOrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(RuleOrderApplication.class, args);
    }
}
```

### 5.3 AccessRulesConfig.java: các rule theo thứ tự

`src/main/java/com/example/orderrules/AccessRulesConfig.java`:

```java
package com.example.orderrules;

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

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class AccessRulesConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                // 1. Ngoại lệ công khai đúng path và GET
                .pathMatchers(HttpMethod.GET, "/public/**").permitAll()

                // 2. Chính sách cụ thể trước /api/**
                .pathMatchers(HttpMethod.GET, "/api/admin/**")
                    .hasRole("ADMIN")
                .pathMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("SCOPE_reports.read")
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasRole("READER")

                // 3. GET API còn lại chỉ cần được xác thực
                .pathMatchers(HttpMethod.GET, "/api/**")
                    .authenticated()

                // 4. Từ chối mọi request chưa khớp
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
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-demo-password"))
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-demo-password"))
            .roles("ADMIN", "READER")
            .build();

        UserDetails analyst = User.withUsername("analyst")
            .password(encoder.encode("analyst-demo-password"))
            .authorities("ROLE_READER", "SCOPE_reports.read")
            .build();

        UserDetails viewer = User.withUsername("viewer")
            .password(encoder.encode("viewer-demo-password"))
            .roles("VIEWER")
            .build();

        return new MapReactiveUserDetailsService(
            reader, admin, analyst, viewer
        );
    }
}
```

**Từng rule hoạt động như thế nào?**

- `GET /public/ping` → rule public, không yêu cầu đăng nhập.
- `GET /api/admin/stats` → rule admin, yêu cầu `ROLE_ADMIN`. Reader đã đăng nhập vẫn không được phép.
- `GET /api/reports/monthly` → rule reports, yêu cầu chính xác `SCOPE_reports.read`. Analyst được phép, reader không.
- `GET /api/orders/42` → rule orders, yêu cầu `ROLE_READER`. Reader/admin/analyst có role này; viewer không.
- `GET /api/profile` → matcher tổng quát `GET /api/**`, chỉ cần authentication.
- `GET /private/unlisted` → `anyExchange().denyAll()` từ chối kể cả admin.

**Bảo mật password:** `createDelegatingPasswordEncoder()` băm password demo trước khi tạo user. Trong sản phẩm thật, không hardcode username/password, không log HTTP Basic credential, dùng TLS/HTTPS và kho danh tính đáng tin cậy. `User.roles` tự thêm prefix `ROLE_`, còn `User.authorities` nhận đúng chuỗi authority.

### 5.4 DemoController.java

`src/main/java/com/example/orderrules/DemoController.java`:

```java
package com.example.orderrules;

import org.springframework.http.MediaType;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping(
        value = "/public/ping",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping(
        value = "/api/profile",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> profile() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(auth -> "Profile " + auth.getName());
    }

    @GetMapping(
        value = "/api/admin/stats",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> adminStats() {
        return Mono.just("admin-stats");
    }

    @GetMapping(
        value = "/api/reports/monthly",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> report() {
        return Mono.just("monthly-report");
    }

    @GetMapping(
        value = "/api/orders/{id}",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> order(@PathVariable String id) {
        return Mono.just("order-" + id);
    }

    @GetMapping(
        value = "/private/unlisted",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> unlisted() {
        return Mono.just("must-not-be-visible");
    }
}
```

Controller không tự kiểm password/role. WebFilter bảo vệ request **trước** khi method được gọi. `ReactiveSecurityContextHolder` đọc username từ Reactor Context của request đã được xác thực.

**Route tồn tại không đồng nghĩa được phép truy cập.** `/private/unlisted` có method hợp lệ nhưng bị policy denyAll chặn. Và nếu request đủ quyền đi qua security mà WebFlux không tìm thấy route, vẫn có thể trả 404.

## 6. Ma trận expected behavior

| Request | Credential | Rule đầu tiên khớp | Kết quả kỳ vọng |
| --- | --- | --- | --- |
| GET `/public/ping` | Không có | Public → permitAll | 200, `pong` |
| GET `/api/profile` | Không có | API chung → authenticated | 401 với HTTP Basic |
| GET `/api/profile` | reader | API chung → authenticated | 200, `Profile reader` |
| GET `/api/admin/stats` | reader | Admin → hasRole(ADMIN) | 403 |
| GET `/api/admin/stats` | admin | Admin → hasRole(ADMIN) | 200, `admin-stats` |
| GET `/api/orders/42` | reader | Orders → hasRole(READER) | 200, `order-42` |
| GET `/api/orders/42` | viewer | Orders → hasRole(READER) | 403 |
| GET `/api/reports/monthly` | reader | Reports → hasAuthority(scope) | 403 |
| GET `/api/reports/monthly` | analyst | Reports → hasAuthority(scope) | 200, `monthly-report` |
| GET `/private/unlisted` | admin | Fallback denyAll | 403 |
| GET `/api/does-not-exist` | reader | API chung → authenticated | Sau security, 404 nếu không có handler |
| POST `/api/profile` | reader | Fallback denyAll | Có thể bị 403 do CSRF hoặc policy; GET handler không nhận POST |

**Điều quan trọng:** Khi `GET /api/admin/stats` khớp rule admin nhưng reader thiếu `ROLE_ADMIN`, request bị từ chối **ngay ở policy admin**, không chuyển tiếp xuống rule `GET /api/**.authenticated()`.

## 7. Kiểm thử bằng WebTestClient

Integration test giúp phát hiện **rule shadowing**: nếu chỉ thử admin nhận 200, bạn không biết reader có được phép truy cập admin trái ý muốn hay không. Hãy luôn test ít nhất một user **đủ quyền** và một user **thiếu quyền**.

Tạo file `src/test/java/com/example/orderrules/AuthorizationOrderTest.java`:

```java
package com.example.orderrules;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class AuthorizationOrderTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicPingDoesNotNeedAuthentication() {
        client.get().uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void anonymousCannotReadProfile() {
        client.get().uri("/api/profile")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedReaderCanReadProfile() {
        client.get().uri("/api/profile")
            .headers(h -> h.setBasicAuth(
                "reader", "reader-demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("Profile reader");
    }

    @Test
    void readerCannotReadAdminRoute() {
        client.get().uri("/api/admin/stats")
            .headers(h -> h.setBasicAuth(
                "reader", "reader-demo-password"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminCanReadAdminRoute() {
        client.get().uri("/api/admin/stats")
            .headers(h -> h.setBasicAuth(
                "admin", "admin-demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin-stats");
    }

    @Test
    void readerCanReadOrdersButViewerCannot() {
        client.get().uri("/api/orders/42")
            .headers(h -> h.setBasicAuth(
                "reader", "reader-demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("order-42");

        client.get().uri("/api/orders/42")
            .headers(h -> h.setBasicAuth(
                "viewer", "viewer-demo-password"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void reportScopeIsMoreSpecificThanAuthenticated() {
        client.get().uri("/api/reports/monthly")
            .headers(h -> h.setBasicAuth(
                "reader", "reader-demo-password"))
            .exchange()
            .expectStatus().isForbidden();

        client.get().uri("/api/reports/monthly")
            .headers(h -> h.setBasicAuth(
                "analyst", "analyst-demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("monthly-report");
    }

    @Test
    void denyAllRejectsAuthenticatedAdminOnUnlistedPath() {
        client.get().uri("/private/unlisted")
            .headers(h -> h.setBasicAuth(
                "admin", "admin-demo-password"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

Chạy từ thư mục Gradle project:

```bash
./gradlew test --tests '*AuthorizationOrderTest'
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests '*AuthorizationOrderTest'
```

Những điều kiện 200/401/403 trong test là **kỳ vọng theo source code**; cần chạy build trong project để xác minh thực tế. Test dùng Spring Boot web server random port và gửi Basic header thật, nhờ vậy xác minh cả authentication, authority mapping và authorization. Không dùng `@WithMockUser` làm **bằng chứng duy nhất** rằng HTTP Basic parser/password validator chạy đúng, dù mock-user test hữu ích khi chỉ muốn kiểm tra policy.

### 7.1 Kiểm thử hồi quy khi cố ý đảo thứ tự

Trong `AccessRulesConfig`, thử đổi:

```java
.pathMatchers(HttpMethod.GET, "/api/**").authenticated()
.pathMatchers(HttpMethod.GET, "/api/admin/**").hasRole("ADMIN")
```

Đây là **một thay đổi cố ý sai** để học; giữ lại các rule khác nhưng đưa API chung lên trước admin. Chạy lại `AuthorizationOrderTest`. Test `readerCannotReadAdminRoute` có thể bắt đầu nhận 200 thay vì 403, vì reader đã authenticated. Phục hồi thứ tự đúng ngay sau bài thử.

Một test chỉ có “admin vào admin endpoint nhận 200” **không phát hiện lỗ hổng này**, vì admin vẫn được phép trong cả hai cấu hình. Kiểm thử **người không đủ quyền** có giá trị đặc biệt cao khi rà soát rule order.

### 7.2 401, 403, 404 và 302 cần được hiểu đúng

- **401 Unauthorized:** thường xảy ra với unauthenticated request khi dùng HTTP Basic entry point.
- **403 Forbidden:** authenticated user thiếu role/scope hoặc request bị CSRF chặn.
- **404 Not Found:** request đã vượt qua security nhưng WebFlux không có handler.
- **302 redirect:** có thể xảy ra nếu dùng form login entry point, không phải dấu hiệu policy đang permit.

Status còn phụ thuộc active security chain, exception handler và cách xác thực. Khi test POST, **403 do CSRF** không chứng minh rule authorization đã được xét.

## 8. Hai tầng lựa chọn: securityMatcher và authorizeExchange

Ứng dụng lớn có thể có nhiều `SecurityWebFilterChain` cho API, browser UI hoặc Actuator. Khi ấy, có **hai cơ chế chọn thứ tự khác nhau**:

1. **Chọn chain:** `WebFilterChainProxy` xem các bean `SecurityWebFilterChain` theo `@Order` và `securityMatcher`; một request sử dụng **chain đầu tiên phù hợp**.
2. **Chọn rule bên trong chain đã chọn:** `authorizeExchange` xét rule theo thứ tự khai báo; rule đầu tiên khớp chọn policy.

```text
GET /api/admin/stats
    |
    +-- @Order(1) apiChain: matcher /api/** -> MATCH -> chain được chọn
    |      |
    |      +-- admin rule /api/admin/** -> MATCH -> require ROLE_ADMIN
    |      +-- /api/** authenticated    -> không thử nữa
    |
    +-- @Order(2) webChain: match all   -> không được chọn
```

**Cảnh báo:** `anyExchange().denyAll()` trong một chain chỉ match `/api/**` **không bảo vệ** `/private/**` ngoài matcher đó. Nếu không có fallback chain, request có thể không đi qua Spring Security, kể cả bạn nghĩ đã có denyAll.

### 8.1 Cấu hình nhiều chain: đoạn ví dụ thay thế

Class sau là **ví dụ thay thế `AccessRulesConfig` ở mục 5**, không khai báo cùng lúc với bean single-chain nếu không chủ đích. Để chạy như ứng dụng riêng, vẫn cần ReactiveUserDetailsService/user store, ví dụ bean `users` và `passwordEncoder` đã nêu.

```java
package com.example.orderrules;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class MultipleChainsExample {

    @Bean
    @Order(1)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**")
            )
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/admin/**").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public/**").permitAll()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }
}
```

Giải thích:

- `apiChain` chỉ nhận `/api/**` vì `securityMatcher`. Trong nó, rule admin phải đứng trước `anyExchange().authenticated()`.
- `fallbackChain` không định nghĩa `securityMatcher`, nên mặc định có thể khớp mọi URL **chưa được chain trước chọn**.
- Nếu đưa catch-all chain lên `@Order(1)`, nó có thể “nuốt” mọi request, khiến apiChain không được chọn.
- Nếu bỏ fallbackChain, các path ngoài `/api/**` không được bảo vệ chỉ bởi `denyAll()` nằm bên trong apiChain.
- Nếu muốn cơ chế Bearer cho API và form login cho browser, mỗi chain cần authentication mechanism riêng và tests tương ứng; việc này không thay đổi quy tắc first-match ở cả hai tầng.

## 9. Kết hợp nhiều quyền trong một policy

Vì các rule không tự nối với toán tử AND, muốn yêu cầu đồng thời `ROLE_FINANCE` **và** `SCOPE_approved`, có thể dùng custom `ReactiveAuthorizationManager` qua `.access(...)`:

```java
.pathMatchers("/api/finance/**")
    .access((authentication, context) ->
        authentication.map(auth -> {
            boolean finance = auth.getAuthorities().stream()
                .anyMatch(a -> "ROLE_FINANCE".equals(a.getAuthority()));

            boolean approved = auth.getAuthorities().stream()
                .anyMatch(a -> "SCOPE_approved".equals(a.getAuthority()));

            return new org.springframework.security.authorization
                .AuthorizationDecision(finance && approved);
        })
    )
```

Đây là **snippet bên trong `authorizeExchange`**, không phải class hoàn chỉnh. Nó trả `Mono<AuthorizationDecision>` từ authentication đã có. Cả hai authority phải đến từ authentication provider/IdP được kiểm chứng, không được lấy từ query/header tùy ý rồi tự gán.

Nếu chính sách đòi hỏi truy cập tài nguyên theo owner hoặc tenant, thường cần kiểm tra thêm trong service. Authorization theo URL và method chỉ chặn ở **cấp HTTP route**.

### 9.1 Path variables và phân quyền theo username

Matcher có thể hỗ trợ variables, ví dụ:

```java
.pathMatchers("/api/users/{username}")
    .access((authentication, context) ->
        authentication
            .map(auth -> auth.getName().equals(
                context.getVariables().get("username")
            ))
            .map(org.springframework.security.authorization.AuthorizationDecision::new)
    )
```

Snippet yêu cầu route `/api/users/{username}` tương ứng và Spring Security đã xác minh principal. Nó minh họa “chỉ cho user xem URL của chính mình”, nhưng **chưa đủ** để bảo vệ mọi tài nguyên có quan hệ ownership phức tạp. Nếu service nhận objectId khác với username, phải xác minh ownership/tenant trên dữ liệu thật.

### 9.2 Hệ quả khi có nhiều điều kiện

Cần AND/OR? Đặt logic đó **trong một policy**, ví dụ `access(...)`, method security `@PreAuthorize` hoặc một service authorization. Đừng viết hai dòng `pathMatchers("/same/**")` rồi kỳ vọng Spring Security tổng hợp quyết định.

## 10. Những lỗi cần phát hiện khi review

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| `/api/**.authenticated()` trước `/api/admin/**.hasRole("ADMIN")` | Reader có thể vào admin API | Đặt admin rule trước API rule |
| `/**.permitAll()` trước `/private/**.denyAll()` | Private endpoint bị mở | Không dùng matcher public bao trùm cả app |
| `/api/**.denyAll()` trước `/api/public/**.permitAll()` | Tài nguyên public bị chặn | Đặt public exception trước |
| `anyExchange().denyAll()` trước rules đặc thù | Mọi rule phía sau không có hiệu lực | Đặt fallback ở cuối |
| Hai rule cùng pattern, mỗi rule kiểm một quyền | Tưởng có AND nhưng chỉ rule đầu có tác dụng | Dùng `access(...)` / method security |
| `hasRole("ROLE_ADMIN")` | Prefix role sai với API mặc định | Dùng `hasRole("ADMIN")` |
| Dùng `authenticated()` cho route cần tenant/ownership | User khác có thể đọc dữ liệu | Bổ sung quyền resource-level |
| Chỉ dùng success test của admin | Bỏ sót reader cũng được truy cập admin | Test denied case với reader |
| Dựa vào HTTP 403 của POST để chứng minh rule | CSRF có thể là nguyên nhân | Test riêng CSRF và authorization |
| Dùng `securityMatcher("/api/**")` nhưng không có fallback | Path ngoài /api có thể không được bảo vệ | Thêm catch-all SecurityWebFilterChain |
| Catch-all chain đứng trước API chain | Chain API không được chọn | `@Order` và matcher cụ thể đúng |
| Kiểm tra route qua URL frontend thay vì server | Proxy/base path khiến mismatch | Đo path/method thực tại WebFlux server |
| Đặt `/actuator/**.permitAll()` vô điều kiện | Lộ management endpoints | Allowlist endpoint thật sự public |
| Nghĩ `permitAll` bỏ qua mọi security filters | Request mang credential lỗi/CSRF vẫn có thể bị chặn | Hiểu phạm vi chỉ là authorization |
| Mặc định GET pattern bao gồm mọi method | POST/HEAD/OPTIONS có thể có policy khác | Dùng method matcher và test đầy đủ |
| Dùng Servlet DSL trong WebFlux | Security không bảo vệ runtime dự kiến | Chọn `ServerHttpSecurity` / `SecurityWebFilterChain` |

**Dấu hiệu quan trọng khi review:** Nếu một rule cụ thể nằm dưới một rule bao quát hơn và không có request nào có thể chạm tới rule cụ thể, đó là **rule shadowing**. Lỗ hổng dễ bị bỏ qua vì Java vẫn compile và test positive của user đủ quyền vẫn pass.

## 11. Bài tập tự kiểm tra

**Câu 1.** Với cấu hình:

```java
.pathMatchers("/api/**").authenticated()
.pathMatchers("/api/admin/**").hasRole("ADMIN")
```

Reader đã đăng nhập truy cập `/api/admin/stats` có thể được phép không?

**Trả lời:** Có thể. Rule `/api/**` đã match trước, nên policy authenticated cho qua. Đưa admin rule lên trước.

**Câu 2.** Tại sao viết `.pathMatchers("/api/reports/**").hasAuthority("SCOPE_reports.read")` ngay **sau** `/api/**.authenticated()` chưa bảo vệ report theo scope?

**Trả lời:** Matcher API chung match trước, che rule reports. Phải đặt scope-specific rule trước rule chung.

**Câu 3.** Hai rule cùng pattern `/api/finance/**`, một `hasRole(FINANCE)` và một `hasAuthority(SCOPE_approved)` có buộc cả hai không?

**Trả lời:** Không. Chỉ policy của rule match đầu tiên được xét. Dùng `access(...)` cho điều kiện kết hợp.

**Câu 4.** `hasRole("ADMIN")` kiểm authority nào với mặc định?

**Trả lời:** `ROLE_ADMIN`. Trong `User.withUsername(...).roles("ADMIN")`, builder tạo authority tương ứng.

**Câu 5.** `anyExchange().denyAll()` ở một chain chỉ khớp `/api/**` có từ chối `/private/home` không?

**Trả lời:** Không; request phải match **chain** trước, rồi `anyExchange` của chain mới chạy. Cần fallback chain.

**Câu 6.** POST đã xác thực và đủ role nhưng nhận 403 có chứng minh rule deny không?

**Trả lời:** Chưa. CSRF filter có thể chặn POST thiếu token. Cần test CSRF và policy riêng.

**Câu 7.** Tại sao test `adminCanReadAdminRoute` pass chưa chứng minh rule order an toàn?

**Trả lời:** Khi rule authenticated che rule admin, admin vẫn pass **và reader cũng có thể pass**. Test reader nhận 403 mới chứng minh admin restriction hoạt động.

**Câu 8.** GET URL chưa có handler nhưng rơi vào `anyExchange().denyAll()` sẽ nhất thiết 404?

**Trả lời:** Không. Security có thể từ chối 401/403 trước khi routing xác định không có handler.

## 12. Checklist triển khai

- [ ] Đang dùng WebFlux reactive thật sự, không nhầm Spring MVC/Servlet DSL.
- [ ] `authorizeExchange` xác định policy theo path và HTTP method rõ ràng.
- [ ] Rule public thật sự cần thiết được khai báo cụ thể, không dùng `/**.permitAll()`.
- [ ] Rule nhạy cảm (admin, report, dữ liệu nội bộ) đứng trước `/api/**` hoặc matcher tổng quát.
- [ ] `anyExchange().denyAll()` hoặc fallback an toàn được đặt cuối chain.
- [ ] Hiểu matcher khớp đầu tiên là policy được đánh giá, không phải tổng hợp nhiều policies.
- [ ] `hasRole`, `hasAuthority` và role/scope mapping khớp mô hình identity.
- [ ] Nếu nhiều chains, đã kiểm tra `@Order` và `securityMatcher` cùng catch-all.
- [ ] Có test **anonymous**, **user đủ quyền**, **user thiếu quyền** trên endpoint nhạy cảm.
- [ ] Test 403 với POST/DELETE đã loại trừ nhầm lẫn CSRF.
- [ ] Browser OPTIONS/CORS, actuator, reverse proxy và base path được xem xét đúng.
- [ ] Resource ownership/tenant authorization được kiểm tra ở nơi có dữ liệu thực.
- [ ] Không dùng credential demo hoặc HTTP Basic không TLS trong production.
- [ ] Hệ thống có log và monitoring phát hiện unauthorized access mà không lộ password/token.

**Kết luận:** `ServerHttpSecurity.authorizeExchange` là DSL phân quyền HTTP trong Spring Security reactive. **Thứ tự rule chính là một phần của security policy**: matcher đầu tiên khớp request quyết định điều kiện truy cập. Đặt rule đặc thù/nhạy cảm trước matcher rộng, kết thúc bằng fallback an toàn, và kiểm thử cả **user thiếu quyền**. Khi có nhiều `SecurityWebFilterChain`, còn phải kiểm tra tầng chọn chain bằng `securityMatcher` và `@Order`; `anyExchange` chỉ xét các request đã vào chain đó.

### Tài liệu chính thức

- [Spring Security — Authorize ServerHttpRequest (reactive)](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Spring Security — WebFlux Security và nhiều SecurityWebFilterChain](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security 6.5 — ServerHttpSecurity Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Security — Reactive method security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security — CSRF trong WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Security — Reactive test support](https://docs.spring.io/spring-security/reference/reactive/test/index.html)
- [Spring Framework — WebFlux DispatcherHandler](https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html)
