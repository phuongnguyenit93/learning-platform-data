# Đặt bộ lọc tùy chỉnh bằng addFilterAt, addFilterBefore và addFilterAfter

**Module: Spring Security Reactive · Xác thực mở rộng · Java 17+ / Spring WebFlux**

## 1. Mục tiêu và tình huống

Ứng dụng Spring WebFlux đã có Spring Security kiểm tra HTTP Basic, JWT hay form login. Khi cần gắn correlation ID, quan sát danh tính, xử lý authentication mới hoặc đo request latency, nhà phát triển có thể muốn bổ sung một WebFilter. Vấn đề là **vị trí đặt filter ảnh hưởng khả năng nhìn thấy Authentication, 401/403 và response lifecycle**. Nếu đặt sai, custom filter có thể chạy trước khi credential được xác minh, bị bỏ qua khi một filter trước đó từ chối request hoặc vô tình chạy hai lần.

Spring Security Reactive cung cấp ba phương thức cấu hình trên ServerHttpSecurity:

- **addFilterBefore(WebFilter, SecurityWebFiltersOrder)**: chèn filter trước một mốc.
- **addFilterAt(WebFilter, SecurityWebFiltersOrder)**: chèn filter tại chính mốc đó.
- **addFilterAfter(WebFilter, SecurityWebFiltersOrder)**: chèn filter sau một mốc.

Sau bài này, bạn sẽ giải thích chính xác sự khác nhau của ba phương thức, chọn mốc theo cơ chế authentication đang bật, viết ví dụ **Java 17+ có thể biên dịch**, kiểm thử bằng WebTestClient và tránh các sai lầm đặc biệt nguy hiểm: nhầm API Servlet, nhầm vị trí với thay thế, tin X-User chưa xác minh, làm mất Reactor SecurityContext, double-registration, tự subscribe/block và xử lý response sau commit.

**Nguyên tắc quan trọng:** addFilterAt **không tự thay thế WebFilter có sẵn**. Thêm filter đúng thứ tự cũng **không** làm credential chưa được kiểm tra trở thành một danh tính đáng tin.

## 2. Phân biệt WebFilter, SecurityWebFilterChain và Filter của Servlet

Spring WebFlux dùng:

~~~java
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;
~~~

Hợp đồng:

~~~java
public interface WebFilter {
    Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain);
}
~~~

Đây là chữ ký minh họa của thư viện, không phải một interface bạn cần tự tạo trong project. WebFilter dùng **ServerWebExchange**, đọc request, response và attributes rồi trả một **Mono<Void>** biểu diễn công việc bất đồng bộ.

| Điểm khác | Servlet / Spring MVC | Reactive / WebFlux |
| --- | --- | --- |
| Filter | jakarta.servlet.Filter | org.springframework.web.server.WebFilter |
| Request | HttpServletRequest | ServerWebExchange |
| Security config | HttpSecurity | ServerHttpSecurity |
| Chain | SecurityFilterChain | SecurityWebFilterChain |
| Anchor addFilter | Filter class | SecurityWebFiltersOrder enum |
| Security context | Thường ThreadLocal | Reactor Context qua ReactiveSecurityContextHolder |
| Mô hình xử lý | Servlet pipeline | Publisher, nonblocking, cancellation |

**Đoạn sau sai trong WebFlux:**

~~~java
// API servlet, không phải ServerHttpSecurity reactive.
http.addFilterBefore(myFilter,
        UsernamePasswordAuthenticationFilter.class);
~~~

Đúng trong WebFlux:

~~~java
http.addFilterBefore(
        myWebFilter,
        SecurityWebFiltersOrder.AUTHENTICATION);
~~~

Các đoạn này minh họa API, file cấu hình đầy đủ nằm ở mục 7.

### 2.1. Filter được chạy ở đâu?

~~~text
HTTP request (Reactor Netty)
        |
        v
Global WebFlux WebFilters (nếu có)
        |
        v
Spring Security WebFilterChainProxy
        |
        +-- chọn một SecurityWebFilterChain theo securityMatcher/@Order
        |
        v
Security chain nội bộ
        |
        +-- HTTP_HEADERS_WRITER
        +-- CORS / CSRF
        +-- REACTOR_CONTEXT
        +-- HTTP_BASIC / FORM_LOGIN / AUTHENTICATION
        +-- ANONYMOUS_AUTHENTICATION
        +-- EXCEPTION_TRANSLATION / AUTHORIZATION
        +-- các custom WebFilters đã add
        |
        v
Controller / RouterFunction
~~~

Sơ đồ là khái niệm; **thứ tự chi tiết phải đối chiếu SecurityWebFiltersOrder của phiên bản đang dùng**, và một số mốc chỉ xuất hiện khi cấu hình tương ứng. Global WebFilter của Spring WebFlux là một tầng **khác** so với filter nằm trong SecurityWebFilterChain. Một filter đặt trong chain không tự động chạy trên các request bị chặn trước chain bởi proxy/gateway hoặc bởi một chain khác.

## 3. Ý nghĩa ba phương thức trong Spring Security 6.5

Các chữ ký:

~~~java
ServerHttpSecurity addFilterBefore(
        WebFilter webFilter,
        SecurityWebFiltersOrder order);

ServerHttpSecurity addFilterAt(
        WebFilter webFilter,
        SecurityWebFiltersOrder order);

ServerHttpSecurity addFilterAfter(
        WebFilter webFilter,
        SecurityWebFiltersOrder order);
~~~

Implementation hiện tại đặt custom filter dựa trên giá trị thứ tự của enum:

~~~text
addFilterBefore(f, X): position(X) - 1
addFilterAt(f, X):     position(X)
addFilterAfter(f, X):  position(X) + 1
~~~

Đây là cách đọc hành vi implementation, **không khuyến khích hard-code số thứ tự**. Dùng enum do Spring Security cung cấp.

| Phương thức | Ý định | Điều không được suy ra |
| --- | --- | --- |
| addFilterBefore | Đặt WebFilter trước một slot | Chạy trước tất cả filter khác |
| addFilterAt | Đặt WebFilter cùng slot | Thay thế, disable hoặc override built-in filter |
| addFilterAfter | Đặt WebFilter sau một slot | Luôn chạy, kể cả khi request bị chặn trước đó |

### 3.1. addFilterAt không phải replace

Ví dụ:

~~~java
http.httpBasic(Customizer.withDefaults());
http.addFilterAt(
        customFilter, SecurityWebFiltersOrder.HTTP_BASIC);
~~~

Spring Security **không tự xóa HTTP Basic AuthenticationWebFilter**. Một custom WebFilter ở cùng thứ tự có thể cùng tồn tại với built-in filter, và **không có bảo đảm thứ tự** giữa các filter ở cùng vị trí. Nếu một filter phụ thuộc vào việc filter còn lại đã chạy, dùng cách đặt before/after tại các mốc **khác nhau phù hợp**, hoặc thiết kế một authentication mechanism chuyên biệt với matcher rõ ràng.

Nếu thật sự thay cơ chế authentication, phải cấu hình **tắt built-in mechanism có chủ đích**, đồng thời thay thế bằng AuthenticationWebFilter/ReactiveAuthenticationManager đúng chuẩn, xử lý success/failure, context và 401/403. Không dùng addFilterAt như một công tắc tắt bảo mật.

### 3.2. addFilterBefore chỉ tương đối so với mốc chỉ định

addFilterBefore(custom, HTTP_BASIC) nghĩa là custom được gọi trước **slot HTTP_BASIC**, không bảo đảm chạy trước CORS, CSRF, headers hay mọi cơ chế OAuth2 khác. Request bị CORS/CSRF chặn sớm có thể chưa từng đi tới custom filter.

### 3.3. addFilterAfter không đồng nghĩa doFinally

addFilterAfter đặt **vị trí invocation** trong chain. Còn doOnSuccess/doFinally của Publisher nói về **hoàn thành** chuỗi reactive. Đó là hai khái niệm khác nhau.

~~~java
// Đây là snippet minh họa reactive lifecycle.
// Việc ghi metric nằm ở hàm riêng của ứng dụng.
return chain.filter(exchange)
        .doFinally(signal -> metrics.record(signal.name()));
~~~

Không dùng doFinally để ghi response headers: response có thể đã commit. Với header, ưu tiên DSL headers.writer hoặc ServerHttpResponse.beforeCommit được đăng ký từ sớm. Không tự subscribe() hay block() trong WebFilter.

## 4. SecurityWebFiltersOrder và lựa chọn mốc

Enum SecurityWebFiltersOrder thuộc **org.springframework.security.config.web.server.SecurityWebFiltersOrder**.

| Mốc | Ý nghĩa | Gợi ý |
| --- | --- | --- |
| FIRST | Vị trí sớm trong security chain | Observer sớm nhưng không thay global ingress |
| HTTP_HEADERS_WRITER | Header bảo mật | Thường nên dùng HeaderSpec writer |
| HTTPS_REDIRECT | Hỗ trợ chuyển sang HTTPS | Không tự viết redirect tùy tiện |
| CORS | Xử lý CORS/preflight | Dùng CorsConfigurationSource |
| CSRF | Bảo vệ request dùng browser credentials | Giữ cơ chế chuẩn |
| REACTOR_CONTEXT | Nạp SecurityContext trong Reactor | Đọc Context theo pipeline |
| HTTP_BASIC | Basic AuthenticationWebFilter | Trước Basic để gắn trace, sau khi xác thực để quan sát |
| FORM_LOGIN | Form AuthenticationWebFilter | Phù hợp login page/cookie |
| AUTHENTICATION | Mốc cho authentication extensions | Có thể chèn AuthenticationWebFilter mới |
| ANONYMOUS_AUTHENTICATION | Hỗ trợ anonymous | Không nhầm anonymous là user đã login |
| EXCEPTION_TRANSLATION | Chuyển security exceptions thành HTTP responses | Đừng bypass 401/403 |
| AUTHORIZATION | Access decision theo authorizeExchange | Filter sau mốc này có thể không thấy request bị chặn |
| LAST | Mốc cuối trong security chain | Không bảo đảm thấy lỗi ở gateway |

Các tên mốc khác liên quan logout, OAuth2 authorization code, request cache và security context. Không cần chọn mốc dựa vào hình dung số thứ tự; **chọn theo cơ chế thực mà app bật**.

### 4.1. Chọn order theo ranh giới tin cậy

- Cần trace trước Basic authentication: **before HTTP_BASIC**.
- Cần chạy một cơ chế auth mới: **at AUTHENTICATION**, nhưng dùng AuthenticationWebFilter có manager xác minh thật.
- Cần đọc principal sau Basic và trước authorizeExchange: **after AUTHENTICATION** có thể phù hợp vì trong demo HTTP_BASIC xảy ra trước mốc AUTHENTICATION.
- Cần quan sát mọi request bị chặn: một WebFilter sau AUTHORIZATION **không đủ**, vì phần authorization có thể trả 403 và không gọi downstream.
- Cần header response: HeaderSpec hoặc beforeCommit, không sửa header sau commit.
- Cần rate limit theo user: chỉ dùng principal đã verify, không dùng X-User do client khai.

## 5. Flow trong bài thực hành

Bài demo có một SecurityWebFilterChain:

~~~text
GET /api/me
     |
     v
Spring defaults: headers, CSRF, context...
     |
     v
TraceMarkerFilter("before-basic")
  addFilterBefore(..., HTTP_BASIC)
     |
     v
HTTP Basic AuthenticationWebFilter
  credential đúng -> Authentication trong Reactor Context
  credential sai  -> có thể trả 401, không đi tiếp
     |
     v
TraceMarkerFilter("at-authentication")
  addFilterAt(..., AUTHENTICATION)
     |
     v
VerifiedPrincipalObserverFilter
  addFilterAfter(..., AUTHENTICATION)
  đọc ReactiveSecurityContextHolder, không đọc X-User
     |
     v
Spring authorization filter
     |
     +-- 401 nếu chưa xác thực, 403 nếu thiếu quyền
     |
     v
Controller nếu được phép
~~~

**Lưu ý:** Trong một số kiến trúc khác, AuthenticationWebFilter chạy ở một mốc khác, ví dụ OAuth2, form login hoặc token bearer. Không suy ra observer sau AUTHENTICATION nhìn thấy **mọi** cơ chế đã xác thực nếu cơ chế đó có vị trí khác. Test thực tế phải khớp mô hình cấu hình.

### 5.1. Ma trận endpoint

| Method/URL | Ai được gọi | Kết quả |
| --- | --- | --- |
| GET /public/ping | Bất kỳ | 200 |
| GET /api/me | Đã xác thực | 200 hoặc 401 |
| GET /api/admin | ROLE_ADMIN | 200 hoặc 401/403 |
| GET /unknown | denyAll | 403 với authenticated user |

Fixture local:
- alice / alice-pass → ROLE_USER
- admin / admin-pass → ROLE_USER, ROLE_ADMIN

Mục tiêu có thể quan sát bằng header lab:

~~~http
X-Lab-Filter-Trace: before-basic > at-authentication > after-authentication
~~~

Dòng trace chỉ tồn tại ở **các request đi qua cả ba filter**. Khi Basic password sai hoặc CSRF chặn sớm, các filter sau có thể không chạy. Header lab **không** phải production security header; dùng để dạy và test, nên loại bỏ ở production.

## 6. Project hoàn chỉnh Java 17+ Spring Boot WebFlux

Cấu trúc:

~~~text
webflux-filter-placement/
├── settings.gradle
├── build.gradle
├── src/main/java/example/filterorder/FilterPlacementApplication.java
├── src/main/java/example/filterorder/TraceMarkerFilter.java
├── src/main/java/example/filterorder/VerifiedPrincipalObserverFilter.java
├── src/main/java/example/filterorder/SecurityConfig.java
├── src/main/java/example/filterorder/DemoController.java
└── src/test/java/example/filterorder/FilterPlacementTest.java
~~~

Dùng **Spring Boot 3.5.16**, Java 17+ và Gradle 8.x tương thích. Spring Boot BOM quản lý Spring Security/Reactor. Đây là project WebFlux, **không thêm spring-boot-starter-web** MVC.

### 6.1. settings.gradle

~~~groovy
rootProject.name = 'webflux-filter-placement'
~~~

### 6.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
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
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 6.3. FilterPlacementApplication.java

~~~java
package example.filterorder;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterPlacementApplication {

    public static void main(String[] args) {
        SpringApplication.run(FilterPlacementApplication.class, args);
    }
}
~~~

### 6.4. TraceMarkerFilter.java

~~~java
package example.filterorder;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

public final class TraceMarkerFilter implements WebFilter {

    public static final String TRACE_HEADER =
            "X-Lab-Filter-Trace";

    private static final String TRACE_ATTRIBUTE =
            TraceMarkerFilter.class.getName() + ".steps";

    private final String marker;

    public TraceMarkerFilter(String marker) {
        this.marker = Objects.requireNonNull(marker);
    }

    static void record(
            ServerWebExchange exchange,
            String marker) {

        @SuppressWarnings("unchecked")
        List<String> steps =
                (List<String>) exchange.getAttribute(TRACE_ATTRIBUTE);

        if (steps == null) {
            steps = new ArrayList<>();
            exchange.getAttributes().put(TRACE_ATTRIBUTE, steps);

            List<String> stepsRef = steps;
            exchange.getResponse().beforeCommit(() -> {
                exchange.getResponse().getHeaders().set(
                        TRACE_HEADER, String.join(" > ", stepsRef));
                return Mono.empty();
            });
        }

        steps.add(marker);
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        record(exchange, marker);
        return chain.filter(exchange);
    }
}
~~~

**Giải thích:**

- Dấu trace nằm trong **ServerWebExchange attributes riêng từng request**. Không dùng static List chung giữa tất cả requests.
- Hai instance TraceMarkerFilter được tạo từ SecurityConfig, không phải Spring WebFilter beans global.
- Response header được ghi ở response.beforeCommit; lúc doFinally chạy, response có thể đã commit.
- Filter không tự lấy credentials/không tự tạo Authentication và luôn chuyển tiếp đúng một lần.
- ArrayList đủ cho demo tuyến tính; nếu hệ thống có branches concurrent cùng ghi một collection, phải xử lý concurrency rõ.
- X-Lab-Filter-Trace chỉ phục vụ học tập; không tiết lộ chi tiết chain ở public production.

### 6.5. VerifiedPrincipalObserverFilter.java

~~~java
package example.filterorder;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

public final class VerifiedPrincipalObserverFilter
        implements WebFilter {

    public static final String PRINCIPAL_ATTRIBUTE =
            VerifiedPrincipalObserverFilter.class.getName()
                    + ".verifiedPrincipal";

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .filter(auth -> auth != null
                        && auth.isAuthenticated()
                        && !(auth instanceof AnonymousAuthenticationToken))
                .map(Authentication::getName)
                .defaultIfEmpty("guest")
                .flatMap(name -> {
                    exchange.getAttributes().put(
                            PRINCIPAL_ATTRIBUTE, name);
                    TraceMarkerFilter.record(
                            exchange, "after-authentication");
                    return chain.filter(exchange);
                });
    }
}
~~~

Ở đây **ReactiveSecurityContextHolder** lấy Authentication từ Reactor subscriber Context. Không dùng SecurityContextHolder thread-local của Servlet làm nguồn danh tính mặc định. Khi HTTP Basic đã xác minh alice, observer nhìn thấy alice. Nếu không có Authentication, demo dùng guest; anonymous không bị coi là logged-in user.

Nếu cần audit chính xác login success/failure, hãy cân nhắc ServerAuthenticationSuccessHandler/FailureHandler thay vì giả định observer phải chạy trên mọi nhánh. Không log password, Authorization token, cookie/session ID.

### 6.6. SecurityConfig.java

~~~java
package example.filterorder;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService demoUsers(
            PasswordEncoder encoder) {

        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build();

        return new MapReactiveUserDetailsService(alice, admin);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers(HttpMethod.GET,
                                "/public/ping").permitAll()
                        .pathMatchers(HttpMethod.GET,
                                "/api/admin").hasRole("ADMIN")
                        .pathMatchers(HttpMethod.GET,
                                "/api/me").authenticated()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)

                // Trước HTTP Basic; Basic vẫn do Spring thực hiện.
                .addFilterBefore(
                        new TraceMarkerFilter("before-basic"),
                        SecurityWebFiltersOrder.HTTP_BASIC)

                // Cùng slot AUTHENTICATION, không thay filter cũ.
                .addFilterAt(
                        new TraceMarkerFilter("at-authentication"),
                        SecurityWebFiltersOrder.AUTHENTICATION)

                // Quan sát Principal sau slot AUTHENTICATION.
                .addFilterAfter(
                        new VerifiedPrincipalObserverFilter(),
                        SecurityWebFiltersOrder.AUTHENTICATION)
                .build();
    }
}
~~~

**Chốt về cấu hình:**

1. Các filter được tạo bằng new **chỉ trong SecurityWebFilterChain**, tránh double-registration với global WebFilter.
2. HTTP Basic là built-in auth mechanism, không bị addFilterAt(AUTHENTICATION) thay thế.
3. Rule admin đứng trước các rule chung; role đến từ UserDetailsService được kiểm chứng qua password encoder.
4. formLogin được disable có chủ đích vì đây là bài test HTTP Basic; **không disable CSRF** hoặc security headers mặc định.
5. Khi request 401 bị chặn tại HTTP Basic, các WebFilter phía sau không nhất thiết chạy.
6. Cơ chế có cùng order slot AUTHENTICATION **không bảo đảm relative ordering**; demo không viết logic phụ thuộc thứ tự với một built-in filter tại slot đó.
7. Không dùng filter này để thay authorizeExchange hoặc cấp authorities từ client headers.

### 6.7. DemoController.java

~~~java
package example.filterorder;

import java.security.Principal;
import java.util.Map;
import java.util.Objects;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping("/public/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(
            Mono<Principal> principal,
            ServerWebExchange exchange) {

        Object observed = exchange.getAttribute(
                VerifiedPrincipalObserverFilter.PRINCIPAL_ATTRIBUTE);

        return principal.map(actor -> Map.of(
                "principal", actor.getName(),
                "observer",
                Objects.toString(observed, "missing")));
    }

    @GetMapping("/api/admin")
    public Mono<Map<String, String>> admin() {
        return Mono.just(Map.of("result", "admin-ok"));
    }
}
~~~

DemoController nhận **Principal đã được Spring Security xác thực** từ reactive argument resolver; không tin X-User/X-Role do client tự đặt. Field observer chỉ chứng minh vị trí filter trong bài học, nên loại ra ở endpoint production nếu không có nhu cầu nghiệp vụ.

### 6.8. Chạy ứng dụng

~~~bash
gradle bootRun
~~~

Nếu dùng Java 17+ và Gradle tương thích, Spring Boot mở http://localhost:8080 theo mặc định. Tài khoản:

~~~text
alice : alice-pass  → ROLE_USER
admin : admin-pass  → ROLE_USER, ROLE_ADMIN
~~~

Dữ liệu là fixtures local. HTTP Basic chỉ Base64-encode credentials, **không mã hóa đường truyền**. Production bắt buộc HTTPS và identity store thực; không dùng mật khẩu mẫu.

## 7. Kiểm tra qua curl và status

### 7.1. Public endpoint

~~~bash
curl -i http://localhost:8080/public/ping
~~~

Kỳ vọng status 200 và header trace:

~~~http
HTTP/1.1 200 OK
X-Lab-Filter-Trace: before-basic > at-authentication > after-authentication
X-Content-Type-Options: nosniff

{"status":"ok"}
~~~

Các header bổ sung và thứ tự có thể khác, đây là các dấu chính cần kiểm tra.

### 7.2. Authentication thành công

~~~bash
curl -i -u alice:alice-pass \
  http://localhost:8080/api/me
~~~

Kỳ vọng status 200 và body chứa hai trường:

~~~json
{"principal":"alice","observer":"alice"}
~~~

Thứ tự key JSON không được cam kết; WebTestClient sẽ dùng JSONPath. Đây là chứng cứ observer đọc **authenticated principal** trong Reactor Context.

### 7.3. Giả mạo header không làm tăng quyền

~~~bash
curl -i -u alice:alice-pass \
  -H 'X-User: admin' -H 'X-Role: ADMIN' \
  http://localhost:8080/api/me
~~~

Kỳ vọng vẫn là principal=alice, observer=alice. Client không thể trở thành admin bằng các header tự khai.

### 7.4. Không có credential → 401

~~~bash
curl -i http://localhost:8080/api/me
~~~

Kỳ vọng HTTP 401 và WWW-Authenticate Basic. Trace filter không cấp quyền đăng nhập.

### 7.5. Password sai → 401

~~~bash
curl -i -u alice:wrong \
  http://localhost:8080/api/me
~~~

Kỳ vọng 401. Basic filter có thể kết thúc luồng trước các custom filters sau HTTP_BASIC; không assert rằng mọi dấu trace phải có trên request lỗi.

### 7.6. User không có ROLE_ADMIN → 403

~~~bash
curl -i -u alice:alice-pass \
  http://localhost:8080/api/admin
~~~

Kỳ vọng 403, không phải 200. Custom filters không thay quyền của authorizeExchange.

### 7.7. Admin hợp lệ → 200

~~~bash
curl -i -u admin:admin-pass \
  http://localhost:8080/api/admin
~~~

Kỳ vọng:

~~~json
{"result":"admin-ok"}
~~~

Khi chỉ muốn headers của **GET**, dùng curl -sS -D - -o /dev/null, không dùng curl -I rồi xem đó là GET: curl -I gửi HEAD. Tránh log Authorization/Cookie. Trên Windows PowerShell dùng curl.exe; ví dụ nối dòng trên theo Bash.

## 8. Kiểm thử bằng WebTestClient

File **src/test/java/example/filterorder/FilterPlacementTest.java**:

~~~java
package example.filterorder;

import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class FilterPlacementTest {

    @Autowired
    WebTestClient client;

    private static final String FULL_TRACE =
            "before-basic > at-authentication > after-authentication";

    @Test
    void publicEndpointHasThreeMarkersInOrder() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        TraceMarkerFilter.TRACE_HEADER, FULL_TRACE)
                .expectBody()
                .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    void basicUserIsVisibleInReactiveSecurityContext() {
        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        TraceMarkerFilter.TRACE_HEADER, FULL_TRACE)
                .expectBody()
                .jsonPath("$.principal").isEqualTo("alice")
                .jsonPath("$.observer").isEqualTo("alice");
    }

    @Test
    void forgedUserHeaderCannotOverridePrincipal() {
        client.get().uri("/api/me")
                .headers(h -> {
                    h.setBasicAuth("alice", "alice-pass");
                    h.set("X-User", "admin");
                    h.set("X-Role", "ADMIN");
                })
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.principal").isEqualTo("alice")
                .jsonPath("$.observer").isEqualTo("alice");
    }

    @Test
    void anonymousPrivateRequestGets401() {
        client.get().uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().exists(
                        HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void spoofedHeadersWithoutCredentialGet401() {
        client.get().uri("/api/me")
                .header("X-User", "admin")
                .header("X-Role", "ADMIN")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void wrongPasswordDoesNotAuthenticate() {
        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth("alice", "wrong"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void ordinaryUserGets403ForAdmin() {
        client.get().uri("/api/admin")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminHasAccess() {
        client.get().uri("/api/admin")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        TraceMarkerFilter.TRACE_HEADER, FULL_TRACE)
                .expectBody()
                .jsonPath("$.result").isEqualTo("admin-ok");
    }

    @Test
    void unknownUrlRemainsDenied() {
        client.get().uri("/unknown")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void builtInSecurityHeadersRemainPresent() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "X-Content-Type-Options", "nosniff")
                .expectHeader().value(
                        HttpHeaders.CACHE_CONTROL,
                        value -> assertTrue(
                                value.contains("no-store")));
    }

    @Test
    void traceContainsOneOccurrenceOfEachMarker() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        TraceMarkerFilter.TRACE_HEADER, FULL_TRACE);
    }
}
~~~

Chạy tests:

~~~bash
gradle test
~~~

**Kết quả kỳ vọng** là **11 JUnit tests PASS** nếu code, JDK và dependencies phù hợp. Đây là kết quả dự kiến từ thiết kế; **không phải khẳng định đã thực thi Gradle trong lúc tạo nội dung**.

Test cases được chọn vì:

- Public 200 xác minh dấu của ba filters và thứ tự khi đi qua chain.
- HTTP Basic thành công xác minh observer thấy Principal đã được xác thực.
- Spoofed X-User/X-Role không thay Authentication.
- Không credential/wrong password vẫn trả 401.
- Alice thiếu ROLE_ADMIN vẫn nhận 403; admin hợp lệ vẫn có 200.
- Unknown URL không bị custom filter biến thành public.
- Security headers mặc định no-sniff/no-store vẫn còn.
- Không có dấu trace lặp do vô tình đăng ký filter hai lần.

**Không assert đủ ba dấu trên mọi 401/403**: một authentication/authorization/CSRF/CORS filter có thể short-circuit trước một số custom filters. Status và security semantics phải là bằng chứng chính.

### 8.1. Kiểm thử khác với proof production

WebTestClient chạy ứng dụng và Spring Security chain, nhưng production có proxy, nhiều chains, TLS termination, lỗi event loop và tracing setup khác. Cần quan sát thêm metrics, latency, response headers và tình huống concurrent requests; tuyệt đối không log raw credentials để debug.

## 9. Chọn cách đặt filter theo nhu cầu

| Mục đích | Vị trí hoặc API đề xuất | Lý do |
| --- | --- | --- |
| Gắn request correlation ID trước HTTP Basic | addFilterBefore(..., HTTP_BASIC) | Có ID trước Basic challenge/failure |
| Cơ chế credential riêng của partner | AuthenticationWebFilter tại AUTHENTICATION | AuthManager phải xác minh credential |
| Quan sát authenticated principal | addFilterAfter theo anchor auth phù hợp | Reactor context có thể chứa Authentication |
| HTTP security headers | ServerHttpSecurity.headers / writer | Không làm việc sau response commit |
| CORS preflight | ServerHttpSecurity.cors / CorsConfigurationSource | Áp dụng chuẩn CORS |
| CSRF | ServerHttpSecurity.csrf | Không tự disable vì filter custom |
| Owner/tenant authorization | Service/domain checks và method security | Scope/role không đủ cho từng object |
| Log mọi request kể cả trước security | Global observation/gateway | Không phụ thuộc security chain được chọn |
| Phân quyền URL | authorizeExchange | Không thay bằng if trên raw headers |
| Audit login success/failure | Authentication success/failure handlers | Event semantics chính xác hơn filter bất kỳ |

### 9.1. Khi cần xác thực mở rộng thật sự

Một custom authentication scheme nên sử dụng **AuthenticationWebFilter**:

~~~java
// Snippet tích hợp, không phải chương trình Java độc lập.
AuthenticationWebFilter filter =
        new AuthenticationWebFilter(trustedManager);

filter.setRequiresAuthenticationMatcher(
        ServerWebExchangeMatchers.pathMatchers("/partner/**"));
filter.setServerAuthenticationConverter(
        partnerCredentialConverter);
filter.setSecurityContextRepository(
        NoOpServerSecurityContextRepository.getInstance());

http.addFilterAt(
        filter, SecurityWebFiltersOrder.AUTHENTICATION);
~~~

Trong snippet, **trustedManager** phải là ReactiveAuthenticationManager thật sự kiểm chứng credential; **partnerCredentialConverter** là ServerAuthenticationConverter chỉ tạo một Authentication **chưa xác thực** từ request, không tự gắn ROLE_ADMIN. Cần thêm imports, registration, success/failure handling, credential lookup/key rotation, replay protection, rate limit và tests phù hợp. NoOpServerSecurityContextRepository chỉ phù hợp khi thật sự muốn stateless per-request credentials.

Đừng đặt một UsernamePasswordAuthenticationToken có authorities từ header X-User/X-Role chưa xác minh rồi tự ghi vào SecurityContext. Đó là authentication bypass dù filter được đặt ở AUTHENTICATION.

### 9.2. Có nhiều authentication mechanisms

Nếu ứng dụng vừa Basic, vừa OAuth2 Bearer vừa form login, mốc AUTHENTICATION đơn lẻ không đảm bảo mọi loại authentication đã xảy ra trước observer. Phải đánh giá vị trí và matcher của từng mechanism rồi kiểm tra 200/401/403 cho mỗi loại. Mục tiêu debug/audit có thể nên dùng authentication success/failure handlers thay vì phụ thuộc vị trí một filter.

## 10. Bẫy double-registration và global WebFilter

Sai lầm phổ biến:

~~~java
@Component
public class AuditFilter implements WebFilter {
    // ...
}
~~~

và còn:

~~~java
http.addFilterBefore(auditFilter,
        SecurityWebFiltersOrder.AUTHENTICATION);
~~~

Nếu WebFlux tự phát hiện @Component/@Bean WebFilter làm **global WebFilter**, sau đó bạn còn thêm cùng filter vào SecurityWebFilterChain, request có thể chạy qua nó **hai lần**: một ở ngoài và một ở trong security chain. Hậu quả gồm duplicate audit, rate limit đếm đôi, response headers trùng, mất ngữ cảnh principal hoặc thứ tự không đúng kỳ vọng.

Demo chủ động dùng **new** ngay trong SecurityConfig, không đánh dấu filter với @Component hoặc @Bean WebFilter. Với production DI, có thể dùng factory/config object thay vì đăng ký global WebFilter, hoặc thiết kế rõ nơi duy nhất nó được đăng ký.

### 10.1. Hai hệ order khác nhau

- @Order / Ordered trên **global WebFilters** ảnh hưởng thứ tự ở WebFlux-level.
- **SecurityWebFiltersOrder** ảnh hưởng WebFilters **bên trong SecurityWebFilterChain**.

Annotation @Order(1) ở một WebFilter toàn cục không tương đương AUTHENTICATION hay AUTHORIZATION. Không chuyển đổi cơ học giữa hai hệ.

### 10.2. Test phát hiện chạy hai lần

Nếu trace xuất hiện:

~~~http
X-Lab-Filter-Trace: before-basic > before-basic > at-authentication > after-authentication
~~~

hãy kiểm tra global registration, nhiều filters cùng label, filter gọi chain.filter(exchange) nhiều lần, retried request và middleware trùng. Không sửa bằng static AtomicBoolean dùng toàn server: nó trộn requests concurrent. Sửa ở cấu hình đăng ký và dùng per-exchange attributes khi cần.

## 11. Short-circuit, exceptions và response commit

Một WebFilter chỉ forward khi gọi chain.filter(exchange). Nếu trả Mono.empty() hoặc ghi response rồi kết thúc, downstream không chạy. Việc intentionally deny nên được xử lý theo security rules/handlers để status và WWW-Authenticate/403 đúng; đừng tự dừng request ngẫu nhiên.

Các trường hợp:

| Request | Filter nào có thể kết thúc trước? |
| --- | --- |
| GET public, không credential | Thường đi qua tới Controller |
| GET private, không credential | Authorization/entry point có thể trả 401 |
| HTTP Basic sai password | HTTP Basic filter trả 401, filters sau có thể không chạy |
| Authenticated USER vào admin | Authorization trả 403 |
| POST thiếu CSRF | CSRF có thể chặn trước HTTP Basic |
| Preflight CORS không phù hợp | CORS có thể xử lý và không vào auth |
| Request do gateway chặn | Không chạy SecurityWebFilterChain |
| URL vào chain khác | Filter chỉ đăng ký ở chain cũ không chạy |

**Đi vào filter** theo order và **completion/response** khác nhau. Nếu muốn thêm header, dùng beforeCommit từ sớm, hoặc Security HeaderSpec. Không set header trong doFinally; response có thể đã commit. Với Reactor cancellation, doFinally có thể nhận CANCEL dù không có HTTP 200/401/403 thông thường.

## 12. Multiple SecurityWebFilterChain

Spring Security Reactive cho phép nhiều SecurityWebFilterChain với @Order và securityMatcher, ví dụ chain đầu cho /api/** dùng bearer, chain tiếp theo cho browser form login. **Request chỉ được chọn vào chain phù hợp**, không lần lượt qua toàn bộ security chains. Vì vậy:

- Custom WebFilter trong browser chain không tự áp dụng cho API chain.
- Mỗi chain cần authentication/authorization/headers/CSRF/CORS thích hợp.
- Đặt chain matcher rộng sai thứ tự có thể làm API nhạy cảm đi vào chain permissive.
- Chọn anchor theo auth mechanism thực tế của chain đó.
- Test từng URL/method/credential và 401/403, không chỉ kiểm tra bean tồn tại.
- Không trông đợi addFilterAt ở chain A thay một filter trong chain B.

Nếu một yêu cầu là telemetry trên **mọi** request kể cả lỗi do gateway, cần một observation layer ngoài chain hoặc edge. Nếu một yêu cầu là bảo vệ URL, đặt trong authorizeExchange/service method security đúng chỗ thay vì dùng filter định tuyến tự chế.

## 13. Các lỗi thường gặp

| Lỗi | Tác hại | Biện pháp |
| --- | --- | --- |
| Copy servlet Filter vào WebFlux | Sai API/không compile | Dùng WebFilter, ServerWebExchange |
| Dùng Filter class làm anchor | Sai kiểu trong addFilterBefore | SecurityWebFiltersOrder |
| Tưởng addFilterAt thay Basic/CSRF | Bỏ sót hoặc nhầm cơ chế cũ | addFilterAt chỉ gắn cùng vị trí |
| Phụ thuộc same-order tie | Thứ tự không bảo đảm | Chọn anchors before/after khác nhau |
| Đọc ThreadLocal SecurityContextHolder | Không thấy principal đúng trong Reactor | ReactiveSecurityContextHolder |
| Tin X-User/X-Role | Authentication bypass | AuthManager kiểm chứng credential |
| Đặt observer sau AUTHORIZATION để ghi mọi 403 | Không chạy trên 403 short-circuit | Auth/denied handlers hoặc earlier observer |
| Không gọi chain.filter | Controller không chạy | Forward đúng khi request được phép |
| Gọi chain.filter hai lần | Duplicate handler effects | Forward/subscription đúng một lần |
| subscribe() tự phát | Detached reactive operation | Compose Mono |
| block() trên Netty event loop | Starvation/latency cao | Nonblocking IO |
| Set headers trong doFinally | Response đã commit | beforeCommit hoặc headers.writer |
| WebFilter vừa @Component vừa addFilter | Chạy đôi | Một nơi đăng ký |
| Nghĩ @Order global tương đương Security order | Sai tầng | Phân biệt hai chain levels |
| Quên securityMatcher nhiều chains | Custom filter bỏ sót URL | Test chain selection |
| Filter sau auth nhưng auth mechanism ở mốc khác | Context không như mong đợi | Đối chiếu order/matcher |
| Chỉ kiểm thử status 200 | Bỏ qua bypass/error paths | Test 200,401,403 |
| Disable CSRF vì lỗi POST | Mất bảo vệ browser credential | Dùng CSRF config đúng |
| Log Authorization/cookie | Secret leak | Redact và least privilege |
| Hard-code numeric order | Dễ hỏng khi nâng version | Dùng enum và integration tests |

## 14. Checklist review và QA

1. Code đang chạy WebFlux, không trộn Servlet types.
2. Custom filter implements WebFilter và trả Mono<Void>.
3. Trước khi chọn Before/At/After đã xác định **mục tiêu nào cần quan sát**.
4. Không coi addFilterAt là replace.
5. Không tạo relative dependency với same-order filters.
6. Nắm các authentication mechanisms được bật và vị trí từng loại.
7. SecurityContext được đọc qua ReactiveSecurityContextHolder đúng reactor subscriber.
8. Dữ liệu raw headers không trở thành Authentication.
9. Cơ chế auth mới dùng AuthenticationWebFilter + ReactiveAuthenticationManager thật.
10. Không tự subscribe()/block(), không gọi chain hai lần.
11. Response headers được set trước commit.
12. Không double-register global và internal WebFilters.
13. SecurityWebFilterChain matcher/@Order đúng nếu có nhiều chains.
14. Không vô hiệu hóa CSRF, CORS hoặc security headers do một custom observer.
15. Không log secret, sessionId, Bearer token, password.
16. Test public 200, private 401, denied 403, spoofed header.
17. Test wrong credential short-circuit và không giả định trace luôn đầy đủ.
18. Test no-sniff/no-store defaults còn hiện diện.
19. Quan sát latency/error/cancellation và concurrency trong staging.
20. Loại bỏ demo-only header/credential và observer response trước production.

## 15. Bài tập tự đánh giá

1. WebFlux dùng WebFilter hay jakarta.servlet.Filter? **WebFilter.**
2. addFilterAt có tự thay filter cũ không? **Không.**
3. Khi hai filters cùng order, có nên dựa vào relative order không? **Không.**
4. addFilterBefore(HTTP_BASIC) có chắc trước CSRF không? **Không.**
5. Giá trị Authentication đáng tin nên lấy từ đâu? **SecurityContext đã xác thực.**
6. Vì sao không dùng SecurityContextHolder thread-local trong Reactor? **Execution không cố định một thread.**
7. Header X-Role: ADMIN có cho ROLE_ADMIN không? **Không.**
8. Vì sao Basic wrong password có thể không chạy observer sau? **Short-circuit 401.**
9. Vì sao filter sau AUTHORIZATION có thể không thấy 403? **Authorization không forward.**
10. Khác nhau giữa addFilterAfter và doFinally? **Position vs reactive completion.**
11. Tại sao set header trong doFinally nguy hiểm? **Response đã commit.**
12. @Component WebFilter và addFilterAt cùng instance có thể gây gì? **Double invocation.**
13. @Order global có cùng nghĩa SecurityWebFiltersOrder không? **Không.**
14. Chain A có filter, URL match chain B thì sao? **Filter A không chạy.**
15. Custom API-key nên xác thực bằng gì? **AuthenticationWebFilter + trusted ReactiveAuthenticationManager.**
16. Không gọi chain.filter(exchange) thì điều gì xảy ra? **Downstream/controller không chạy.**
17. Nếu Alice gửi X-User=admin nhưng Basic của Alice đúng, principal là ai? **Alice.**
18. CSRF filter chặn trước HTTP Basic thì marker before-basic có luôn xuất hiện không? **Không.**
19. Vì sao sample tests kiểm tra 401 và 403? **Đảm bảo custom filter không bypass security.**
20. Có được sử dụng static ArrayList cho tất cả requests làm trace không? **Không, dễ trộn request và có race.**

## 16. Tài liệu tham khảo

- Spring Security 6.5 — ServerHttpSecurity Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security 6.5 — SecurityWebFiltersOrder: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/config/web/server/SecurityWebFiltersOrder.html
- Spring Security 6.5 — WebFlux Security Configuration: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security 6.5 — AuthenticationWebFilter Javadoc: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html
- Spring Security — Reactive Authentication: https://docs.spring.io/spring-security/reference/reactive/authentication/index.html
- Spring Security — Reactive Authorization: https://docs.spring.io/spring-security/reference/reactive/authorization/index.html
- Spring Framework — WebFilter Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/server/WebFilter.html
- Reactor — Context: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- OWASP — Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html

**Kết luận:** Trong Spring Security Reactive, dùng addFilterBefore/At/After với **WebFilter + SecurityWebFiltersOrder** để đặt logic quan sát hoặc authentication mở rộng đúng ranh giới. addFilterAt **không thay thế** built-in WebFilter. Khi cần danh tính, đọc Reactor SecurityContext sau khi credential đã verify; khi cần xác thực mới, dùng AuthenticationWebFilter cùng ReactiveAuthenticationManager. Kiểm thử WebTestClient cả 200/401/403, short-circuit và double-registration thay vì chỉ nhìn vào cấu hình.