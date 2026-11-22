# AuthenticationWebFilter: chuyển đổi thông tin đầu vào và gọi bộ xác thực trong Spring Security Reactive

## 1. Mục tiêu và vị trí trong kiến trúc WebFilter

**AuthenticationWebFilter** là WebFilter chịu trách nhiệm thực hiện một lần thử **authentication (xác thực)** đối với request được chọn trong Spring Security WebFlux. Nhiệm vụ cốt lõi của nó là:

1. Xác định request có thuộc phạm vi cần thử xác thực hay không.
2. Đọc dữ liệu xác thực từ **ServerWebExchange** thông qua **ServerAuthenticationConverter**.
3. Chuyển dữ liệu đầu vào thành một **Authentication chưa được xác thực**, rồi gửi cho **ReactiveAuthenticationManager**.
4. Nếu xác thực thành công, đặt Authentication kết quả vào **Reactive SecurityContext** và chạy success handler; nếu xác thực thất bại, chạy failure handler.
5. Để các WebFilter phía sau, đặc biệt bộ kiểm tra quyền, sử dụng danh tính đã được xác thực.

Bài này tập trung vào luồng **chuyển đổi đầu vào → gọi bộ xác thực → xử lý kết quả**. AuthenticationWebFilter không tự biết mật khẩu có đúng, token có hợp lệ, user được xem đơn hàng nào hay request có nên vượt giới hạn tải: các quyết định đó thuộc manager, các bộ xử lý token, tầng authorization và những cơ chế bảo vệ khác.

| Thành phần | Trách nhiệm | KHÔNG nên làm |
| --- | --- | --- |
| **SecurityWebFilterChain** | Gom các WebFilter bảo mật theo quy tắc request | Trộn cấu hình servlet HttpSecurity với WebFlux ServerHttpSecurity |
| **ServerWebExchangeMatcher** | Chọn request cần đi qua nhánh thử authentication | Coi “không match” là quyền truy cập được cho phép |
| **ServerAuthenticationConverter** | Rút credential khỏi request và tạo Authentication đầu vào | Tự gán ROLE_ADMIN hoặc tự đánh dấu authenticated |
| **ReactiveAuthenticationManager** | Kiểm tra credential, tạo Authentication đáng tin cậy | Tin vào principal/authority mà client tự khai |
| **ReactiveAuthenticationManagerResolver** | Chọn manager theo exchange nếu cấu hình kiểu đa nguồn | Tin issuer/tenant từ input không xác thực mà không kiểm tra |
| **ServerAuthenticationSuccessHandler** | Xử lý sau khi manager xác thực thành công | Phát dữ liệu bí mật khi chưa qua authorization |
| **ServerAuthenticationFailureHandler** | Trả phản hồi/thực hiện xử lý thất bại xác thực | Ghi lộ password, API key hoặc bearer token |
| **ServerSecurityContextRepository** | Quy định cách lưu/khôi phục SecurityContext giữa các request | Mặc định dùng session cho API stateless mà không có chủ ý |
| **AuthorizationWebFilter / method security** | Kiểm tra quyền của principal đối với tài nguyên | Tin rằng “đã xác thực” nghĩa là đủ quyền |

Một cách nhớ: **converter hiểu giao thức đầu vào**, **manager chứng minh danh tính**, còn **authorization quyết định được làm gì**.

## 2. Sơ đồ luồng xử lý request

~~~text
HTTP request
    |
    v
SecurityWebFilterChain
    |
    v
AuthenticationWebFilter
    |
    +-- matcher KHÔNG khớp ----------------> chain.filter(exchange)
    |
    +-- matcher khớp
             |
             v
    ServerAuthenticationConverter.convert(exchange)
             |
             +-- Mono.empty() -------------> chain.filter(exchange)
             |
             +-- Mono.error(...) ----------> xử lý lỗi xác thực nếu là
             |                                AuthenticationException
             |
             +-- Mono<Authentication chưa xác thực>
                          |
                          v
                  ReactiveAuthenticationManager.authenticate(...)
                          |
                          +-- thành công -> Authentication đã xác thực
                          |                   |
                          |                   v
                          |           SecurityContext / success handler
                          |                   |
                          |                   v
                          |               chain tiếp tục
                          |
                          +-- AuthenticationException -> failure handler
                          |
                          +-- lỗi hệ thống -> xử lý lỗi phù hợp,
                                             không cấp quyền mặc định
~~~

Đây là sơ đồ khái niệm cho một filter được cấu hình đúng, không phải lời cam kết rằng tất cả exception thuộc mọi lớp đều biến thành 401. Trong Spring Security, tên exception, vị trí WebFilter và các handler được cấu hình quyết định phản hồi HTTP thực tế.

**Điểm phân biệt quan trọng:** request không tạo được Authentication trong converter sẽ **không thử xác thực tại filter này**. Request vẫn đi tới các tầng phía sau. Nếu endpoint yêu cầu đăng nhập, bước authorization sẽ từ chối người dùng ẩn danh theo cấu hình. **Bỏ qua việc thử xác thực không đồng nghĩa được quyền truy cập.**

### 2.1. ServerWebExchange là gì?

ServerWebExchange đại diện cho một HTTP exchange trong WebFlux, gồm request, response và các thuộc tính liên quan. Converter thường quan tâm:

- Request header: Authorization, X-API-Key, thông tin chứng chỉ phía proxy đáng tin cậy…
- Cookie/session nếu cơ chế xác thực thực sự sử dụng.
- Path, method và các thông tin cần chọn cơ chế xác thực.

Không đọc body tùy tiện trong converter: body của WebFlux là luồng có thể tiêu thụ một lần, có chi phí bộ nhớ và ảnh hưởng việc downstream đọc body. Nếu xác thực dựa trên login JSON/form, cần cơ chế đọc/caching body phù hợp với framework và giới hạn kích thước.

### 2.2. Thứ tự xử lý trong SecurityWebFilterChain

Spring Security Reactive dùng các vị trí trong **SecurityWebFiltersOrder**, trong đó **AUTHENTICATION** dành cho filter xác thực, và authorization được xử lý ở một giai đoạn sau. Khi bổ sung custom filter, nên chèn bằng **ServerHttpSecurity.addFilterAt(filter, SecurityWebFiltersOrder.AUTHENTICATION)** trong đúng SecurityWebFilterChain.

Phân biệt:

- **WebFilter** và **ServerHttpSecurity** thuộc WebFlux/reactive.
- **jakarta.servlet.Filter**, **OncePerRequestFilter**, **HttpSecurity** thuộc servlet stack; không thay thế trực tiếp cho AuthenticationWebFilter.
- Không tự tạo Spring bean WebFilter rồi đồng thời addFilterAt cùng instance mà không kiểm soát, vì có thể dẫn tới đăng ký/chạy filter ngoài ý muốn. Trong demo, filter được tạo cục bộ bên trong @Bean SecurityWebFilterChain.

## 3. Bước 1 — Chọn request bằng ServerWebExchangeMatcher

AuthenticationWebFilter có cấu hình **setRequiresAuthenticationMatcher(ServerWebExchangeMatcher)**. Nếu matcher trả về kết quả không khớp, filter chuyển tiếp request và **không gọi converter/manager**.

Ví dụ:

~~~java
filter.setRequiresAuthenticationMatcher(
        ServerWebExchangeMatchers.pathMatchers("/api/**"));
~~~

Chỉ các request có path phù hợp nhánh /api/** mới đi vào converter của filter này. Matchers có thể kết hợp điều kiện HTTP method/path khi ứng dụng yêu cầu; tránh matcher quá rộng khiến một cơ chế cố xử lý cả login callback, preflight CORS hoặc endpoint thuộc scheme khác.

**Mặc định theo Javadoc:** requiresAuthenticationMatcher khớp với mọi request. Khi xây dựng custom filter, hãy tự nêu rõ phạm vi để tránh đụng các phương thức authentication khác.

Matcher **không** ra quyết định allow/deny cuối cùng. Một request không match vẫn có thể bị một matcher hoặc authorization rule phía sau từ chối.

## 4. Bước 2 — ServerAuthenticationConverter chuyển request thành Authentication

**ServerAuthenticationConverter** là hợp đồng reactive:

~~~java
Mono<Authentication> convert(ServerWebExchange exchange);
~~~

Nhiệm vụ của converter là nhận diện credential trong request và xây dựng **đề nghị xác thực**; nó không tự tin credential đó là hợp lệ.

Ví dụ tối giản cho header X-API-Key:

~~~java
ServerAuthenticationConverter converter = exchange -> {
    String rawKey = exchange.getRequest()
            .getHeaders()
            .getFirst("X-API-Key");

    if (rawKey == null) {
        return Mono.empty();
    }

    Authentication attempt =
            UsernamePasswordAuthenticationToken.unauthenticated(
                    "api-client", rawKey);

    return Mono.just(attempt);
};

filter.setServerAuthenticationConverter(converter);
~~~

Các import cần thiết cho đoạn minh họa: **ServerAuthenticationConverter**, **Authentication**, **UsernamePasswordAuthenticationToken** và **Mono**. Phần code này dùng bên trong phương thức cấu hình filter, không phải Java class chạy độc lập.

Ý nghĩa:

- Không có header → **Mono.empty()** → filter không thử xác thực.
- Có header → **Mono<Authentication>** chứa credential gốc, nhưng token ở trạng thái **chưa xác thực**.
- Chỉ manager mới được kiểm tra giá trị và trả về token đã xác thực cùng authority do hệ thống tin cậy xác định.

Bảng tín hiệu converter:

| Kết quả converter | Filter hiểu | Ảnh hưởng tới request |
| --- | --- | --- |
| **Mono.empty()** | Chưa tìm thấy credential phù hợp / không có lần thử xác thực | Chuyển tiếp, sau đó các policy còn lại quyết định |
| **Mono.just(unauthenticated)** | Có một lần thử xác thực | Gọi ReactiveAuthenticationManager |
| **Mono.error(BadCredentialsException)** | Credential được nhận diện nhưng malformed/không dùng được | Đi theo xử lý thất bại xác thực |
| **Mono.error(lỗi không thuộc AuthenticationException)** | Lỗi kỹ thuật không mong đợi | Phải xử lý bằng error pipeline phù hợp, không giả định luôn là 401 |

Nếu header có nhưng rỗng hoặc sai định dạng, thường nên coi đây là **lần xác thực không hợp lệ** và phát AuthenticationException; đừng luôn trả Mono.empty() vì nó trộn “không có credential” với “đã gửi credential sai”. Đối với bearer token, phải kiểm tra scheme Bearer đúng cách, reject header nhập nhằng hoặc nhiều credential trái chính sách, và đặt giới hạn kích thước.

**API nên dùng:** setServerAuthenticationConverter(...). Phương thức cũ **setAuthenticationConverter(Function<ServerWebExchange, Mono<Authentication>>)** đã deprecated từ Spring Security 5.1. Converter mặc định của AuthenticationWebFilter là **ServerHttpBasicAuthenticationConverter**; vì thế, nếu muốn header tùy biến, cần set converter mới thay vì mong filter tự hiểu X-API-Key.

## 5. Bước 3 — ReactiveAuthenticationManager xác minh credential

Hợp đồng chính:

~~~java
public interface ReactiveAuthenticationManager {
    Mono<Authentication> authenticate(Authentication authentication);
}
~~~

Một manager có thể:

1. Kiểm tra loại Authentication mà nó hỗ trợ.
2. Lấy credential từ token chưa xác thực.
3. Thực hiện kiểm tra đáng tin cậy: password hash, API key trong kho bí mật, kiểm tra chữ ký/claim JWT, introspection… theo cơ chế tương ứng.
4. Khi hợp lệ, trả **Authentication đã xác thực** chứa principal và GrantedAuthority do hệ thống quyết định.
5. Khi credential sai, trả **Mono.error(AuthenticationException)** (ví dụ BadCredentialsException).
6. Khi không hỗ trợ loại token, tùy contract có thể trả **Mono.empty()** để cơ chế điều phối manager khác xử lý. Trong một manager chuyên trách, nên thiết kế rõ loại token được hỗ trợ và cách xử lý unsupported; tuyệt đối không dùng empty như sự chấp thuận.

**Không bao giờ** chấp nhận danh sách role, user ID hoặc boolean authenticated do converter lấy nguyên từ header/body client rồi đưa thẳng vào success token. Client có thể sửa những trường đó. Authority phải xuất phát từ policy/kho danh tính hoặc token đã được kiểm chứng.

### 5.1. Mono là lời hứa xử lý bất đồng bộ

Manager trả **Mono<Authentication>**, giúp WebFlux kết hợp I/O và xử lý theo Reactor. Đừng gọi block() bên trong authenticate hoặc converter, vì event loop có thể bị nghẽn. Với client I/O blocking bất khả kháng, phải cô lập công việc bằng scheduler phù hợp hoặc tốt hơn dùng reactive driver/client; vẫn cần timeout và giới hạn concurrency.

Không gọi subscribe() thủ công bên trong converter hoặc manager: trả Publisher để framework sở hữu vòng đời, truyền context và nhận lỗi. Không ghi credential vào log debug, exception message hay Reactor Context không cần thiết.

### 5.2. Tại sao chưa xác thực và đã xác thực phải khác nhau?

Một **UsernamePasswordAuthenticationToken.unauthenticated(principal, credentials)** dùng để mang dữ liệu cần kiểm tra. Khi manager kiểm tra thành công, nó mới có thể trả:

~~~java
Authentication success =
        UsernamePasswordAuthenticationToken.authenticated(
                "api-client",
                null,
                List.of(new SimpleGrantedAuthority("ROLE_READER")));
~~~

Credential ở kết quả có thể là null để hạn chế tồn tại trong bộ nhớ. ROLE_READER do server cấp; không lấy từ request. **isAuthenticated()** là trạng thái của Authentication; ở Spring Security cần kết hợp nó với cơ chế tạo/chứng thực token, không dùng trạng thái do client tự khai.

## 6. Bước 4 — Kết quả thành công, thất bại và SecurityContext

### 6.1. Xác thực thành công

Sau khi manager phát Authentication thành công, AuthenticationWebFilter:

- Tạo/đặt thông tin SecurityContext và thiết lập ngữ cảnh reactive cho phần xử lý tiếp theo.
- Gọi **ServerAuthenticationSuccessHandler**.
- Có thể lưu SecurityContext thông qua **ServerSecurityContextRepository** nếu repository được cấu hình cho việc lưu trạng thái.

**Mặc định theo Javadoc:** success handler là **WebFilterChainServerAuthenticationSuccessHandler** — cho pipeline đi tiếp. SecurityContextRepository mặc định của riêng AuthenticationWebFilter là **NoOpServerSecurityContextRepository**, tức không lưu trạng thái qua request. Đây là mặc định của lớp filter; các cấu hình SecurityWebFilterChain, đăng nhập bằng form/session hoặc cơ chế khác có thể chọn repository khác.

Sau thành công, có thể đọc Authentication bằng **ReactiveSecurityContextHolder.getContext()** trong pipeline reactive. Đừng dựa vào **SecurityContextHolder** ThreadLocal của servlet khi truy cập trong handler WebFlux.

**Success không tự đồng nghĩa với được phép xem dữ liệu:** giai đoạn authorizeExchange hoặc method security mới kiểm tra hasRole/hasAuthority/ownership.

### 6.2. Xác thực thất bại

Một lỗi **BadCredentialsException** từ manager báo credential không được chấp nhận. AuthenticationWebFilter gọi **ServerAuthenticationFailureHandler** phù hợp; có thể trả HTTP 401, redirect login, hoặc đáp ứng khác theo cấu hình.

Mặc định của lớp filter là failure handler dùng HTTP Basic challenge; nếu triển khai scheme X-API-Key, thường cần cấu hình failure handler trả 401 **không làm client hiểu nhầm phải gửi Basic**.

Ví dụ:

~~~java
filter.setAuthenticationFailureHandler((filterExchange, exception) -> {
    var response = filterExchange.getExchange().getResponse();
    response.setStatusCode(HttpStatus.UNAUTHORIZED);
    return response.setComplete();
});
~~~

**Phân biệt:** 

- **401 Unauthorized**: chưa có bằng chứng xác thực hợp lệ hoặc lần xác thực thất bại (tùy entry point).
- **403 Forbidden**: đã có danh tính tin cậy nhưng bị authorization từ chối.
- **500/503**: lỗi kỹ thuật ở kho danh tính hoặc dịch vụ xác thực có thể cần ánh xạ thành lỗi hệ thống, không cấp quyền, không phơi bày secret.

Các mã phản hồi phụ thuộc cấu hình và thời điểm response commit; không nên khẳng định mọi AuthenticationException hoặc lỗi nội bộ đều tự biến thành chính xác một mã HTTP.

### 6.3. SecurityContext là ngữ cảnh theo subscription

Trong Reactor, dữ liệu request có thể đổi thread và đi qua operator bất đồng bộ. Spring Security Reactive dùng **Reactor Context** để truyền SecurityContext. **ReactiveSecurityContextHolder** là API phù hợp; tự tạo subscription, gọi block(), dùng ThreadLocal tùy tiện hoặc tách một pipeline fire-and-forget đều có nguy cơ đánh mất ngữ cảnh hoặc làm lỗi khó quan sát.

**NoOpServerSecurityContextRepository** giúp filter không duy trì đăng nhập bằng session. Stateless không miễn trừ mọi vấn đề bảo mật: bảo vệ TLS, bảo vệ secret, cấu hình CORS/CSRF theo kiểu credential mà trình duyệt tự gửi, và rate limit vẫn là việc riêng.

## 7. Demo Java 17+: tự tạo AuthenticationWebFilter cho X-API-Key

Demo dùng **Spring Boot 3.3.5**, **Java 17+**, WebFlux và Spring Security. Ta tự cấu hình AuthenticationWebFilter để minh họa ba bước: đọc X-API-Key, manager xác minh, đưa danh tính vào Reactor Context. Chỉ có GET endpoint; key cố định **demo-only-key** là dữ liệu thử nghiệm, không phải phương pháp lưu bí mật cho production.

Cấu trúc:

~~~text
auth-webfilter-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/security/ApiKeyDemoApplication.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'auth-webfilter-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
}
~~~

**src/main/java/example/security/ApiKeyDemoApplication.java**

~~~java
package example.security;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.AuthenticationWebFilter;
import org.springframework.security.web.server.authentication.ServerAuthenticationConverter;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
@RestController
public class ApiKeyDemoApplication {

    private static final byte[] EXPECTED_KEY =
            "demo-only-key".getBytes(StandardCharsets.UTF_8);

    public static void main(String[] args) {
        SpringApplication.run(ApiKeyDemoApplication.class, args);
    }

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/api/me")
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
                .map(ctx -> "hello " + ctx.getAuthentication().getName());
    }

    @GetMapping("/api/admin/report")
    public Mono<String> report() {
        return Mono.just("admin-report");
    }

    @Bean
    ReactiveAuthenticationManager apiKeyManager() {
        return candidate -> Mono.defer(() -> {
            Object credential = candidate.getCredentials();

            if (!(credential instanceof String submittedKey)) {
                return Mono.error(
                        new BadCredentialsException("Unsupported credential"));
            }

            byte[] actual = submittedKey.getBytes(StandardCharsets.UTF_8);

            if (!MessageDigest.isEqual(EXPECTED_KEY, actual)) {
                return Mono.error(
                        new BadCredentialsException("Invalid API key"));
            }

            Authentication verified =
                    UsernamePasswordAuthenticationToken.authenticated(
                            "demo-client",
                            null,
                            List.of(new SimpleGrantedAuthority("ROLE_READER")));

            return Mono.just(verified);
        });
    }

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager apiKeyManager) {

        AuthenticationWebFilter apiKeyFilter =
                new AuthenticationWebFilter(apiKeyManager);

        // Filter chỉ thử xác thực ở những request /api/**.
        apiKeyFilter.setRequiresAuthenticationMatcher(
                ServerWebExchangeMatchers.pathMatchers("/api/**"));

        // Chuyển header thành Authentication CHƯA xác thực.
        ServerAuthenticationConverter converter = exchange -> {
            String rawKey = exchange.getRequest()
                    .getHeaders()
                    .getFirst("X-API-Key");

            if (rawKey == null) {
                return Mono.empty();
            }

            Authentication attempt =
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "api-client", rawKey);
            return Mono.just(attempt);
        };
        apiKeyFilter.setServerAuthenticationConverter(converter);

        // Mỗi request tự mang credential; filter không lưu session.
        apiKeyFilter.setSecurityContextRepository(
                NoOpServerSecurityContextRepository.getInstance());

        // Không quảng bá HTTP Basic challenge cho cơ chế API key.
        apiKeyFilter.setAuthenticationFailureHandler((filterExchange, ex) -> {
            var response = filterExchange.getExchange().getResponse();
            response.setStatusCode(HttpStatus.UNAUTHORIZED);
            return response.setComplete();
        });

        return http
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public/ping").permitAll()
                        .pathMatchers("/api/admin/**").hasRole("ADMIN")
                        .pathMatchers("/api/**").authenticated()
                        .anyExchange().denyAll())
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint((exchange, ex) -> {
                            exchange.getResponse()
                                    .setStatusCode(HttpStatus.UNAUTHORIZED);
                            return exchange.getResponse().setComplete();
                        })
                        .accessDeniedHandler((exchange, ex) -> {
                            exchange.getResponse()
                                    .setStatusCode(HttpStatus.FORBIDDEN);
                            return exchange.getResponse().setComplete();
                        }))
                .addFilterAt(
                        apiKeyFilter, SecurityWebFiltersOrder.AUTHENTICATION)
                .build();
    }
}
~~~

**Giải thích từng đoạn:**

1. **setRequiresAuthenticationMatcher** chỉ thử cơ chế này trên /api/**.
2. **converter**: không có X-API-Key → Mono.empty; có header → Authentication chưa xác thực.
3. **apiKeyManager**: so sánh giá trị thử nghiệm; sai → BadCredentialsException; đúng → Authentication mới có principal demo-client và ROLE_READER.
4. **success**: handler mặc định cho request đi tiếp; danh tính được đặt trong Reactor Context, dùng được ở /api/me.
5. **failure**: custom failure handler đặt 401 cho key sai. Khi không có key, authorization của /api/** yêu cầu authenticated và entry point trả 401.
6. **authorization**: /api/admin/** yêu cầu ROLE_ADMIN, nhưng token demo chỉ có ROLE_READER; vì thế dù xác thực thành công vẫn nhận 403.
7. **NoOpServerSecurityContextRepository**: không lưu danh tính sang request sau. Dùng lại một key đúng ở request tiếp theo phải xác thực lại.
8. Cấu hình không thay CSRF mặc định; demo chỉ dùng GET. Nếu bổ sung phương thức ghi hoặc client trình duyệt, hãy thiết kế CSRF/CORS theo đúng cách sử dụng cookie, token và origin.

**Chạy demo:** cài JDK 17+ và Gradle 8.x tương thích. Trong thư mục auth-webfilter-demo:

~~~bash
gradle bootRun
~~~

Trong một terminal khác:

~~~bash
curl -s http://localhost:8080/public/ping
# pong

curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/api/me
# 401

curl -s -o /dev/null -w '%{http_code}\n' \
  -H 'X-API-Key: wrong-key' http://localhost:8080/api/me
# 401

curl -s -H 'X-API-Key: demo-only-key' \
  http://localhost:8080/api/me
# hello demo-client

curl -s -o /dev/null -w '%{http_code}\n' \
  -H 'X-API-Key: demo-only-key' \
  http://localhost:8080/api/admin/report
# 403
~~~

**Lưu ý lệnh:** các lệnh nhiều dòng sử dụng dấu gạch chéo ngược theo shell kiểu Bash/macOS/Linux. Trên Windows PowerShell, dùng mỗi lệnh trên một dòng với **curl.exe**, vì bí danh curl có thể trỏ đến Invoke-WebRequest và quy tắc xuống dòng khác Bash.

### 7.1. Bảng kết quả mong đợi

| Request | Converter | Manager | Authorization | Kết quả |
| --- | --- | --- | --- | --- |
| GET /public/ping không key | Filter không match | Không gọi | permitAll | **200**, pong |
| GET /api/me không key | Mono.empty | Không gọi | authenticated yêu cầu danh tính | **401** |
| GET /api/me key sai | Tạo unauthenticated token | BadCredentialsException | Không tới bước allow | **401** |
| GET /api/me key đúng | Tạo unauthenticated token | Trả ROLE_READER | authenticated | **200**, hello demo-client |
| GET /api/admin/report key đúng | Tạo unauthenticated token | Trả ROLE_READER | Thiếu ROLE_ADMIN | **403** |

Như vậy bạn quan sát được sự khác biệt **không có lần thử xác thực**, **xác thực thất bại** và **xác thực thành công nhưng không đủ quyền**. Phần mã dùng key trong bộ nhớ để học API; với production cần chuyển bí mật sang kho cấu hình an toàn, luân chuyển/thu hồi key, quản lý phạm vi và theo dõi sử dụng.

## 8. Khi nào dùng AuthenticationWebFilter trực tiếp?

Phần lớn ứng dụng nên dùng các cấu hình sẵn có:

- **http.httpBasic(...)** cho HTTP Basic khi phù hợp.
- **http.formLogin(...)** khi thực sự dùng đăng nhập qua form/session.
- **http.oauth2ResourceServer(...)** cho API bearer token/JWT/opaque token, kèm validation issuer, audience, chữ ký, expiry, mapping quyền.
- **http.oauth2Login(...)** cho quy trình OAuth2/OIDC login trên ứng dụng web.

Custom AuthenticationWebFilter hữu ích khi cần giao thức xác thực riêng hoặc kết hợp hệ thống danh tính đặc thù. Đừng tự viết bộ xác minh JWT/token chỉ để thay một vài dòng cấu hình: cơ chế chuẩn có nhiều quy tắc về chữ ký, key rotation, clock skew và exception handling đã được hỗ trợ.

Khi một ứng dụng có nhiều cơ chế:

- Dùng **matcher** cho đúng API/đường dẫn thay vì để các filter tranh xử lý cùng một credential.
- Có thể dùng **ReactiveAuthenticationManagerResolver<ServerWebExchange>** để chọn manager theo request; nhưng dữ liệu chọn manager từ request là **chưa đáng tin** cho đến khi được xác minh. Với nhiều issuer/tenant, phải kiểm tra issuer và key ở nguồn tin cậy, không dùng một chuỗi issuer tùy ý để cấp quyền.
- Nếu sử dụng nhiều **SecurityWebFilterChain**, kiểm tra chính sách chọn chain và thứ tự của chúng. Một request thường được bảo vệ bởi chain đầu tiên phù hợp, nên đừng tưởng mọi chain đều cộng dồn.
- Kiểm tra lỗi missing/malformed/invalid credential riêng biệt, đặc biệt khi có CORS preflight và cơ chế anonymous.

## 9. Lỗi phổ biến và cách tránh

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Converter trả token **đã authenticated=true** | Bỏ qua/giả mạo kết quả kiểm chứng danh tính | Trả token chưa xác thực, để manager cấp token tin cậy |
| Lấy role từ header **X-Role: ADMIN** | Client tự nâng đặc quyền | Authority phải do nguồn xác minh đáng tin cấp |
| Coi **Mono.empty()** của converter là “mật khẩu đúng” | Nhầm bước không thử với bước thành công | Endpoint phải có policy authenticated/role phù hợp |
| Converter trả empty cho credential malformed | Khó phân biệt thiếu key với key sai | Dùng AuthenticationException đối với credential đã nhận diện nhưng không hợp lệ |
| Manager dùng **onErrorReturn(authenticatedToken)** | Dịch vụ danh tính lỗi lại được đăng nhập | Fail closed, để lỗi có đường xử lý và giám sát |
| Gọi **block()** để truy vấn user | Nghẽn event loop và giảm khả năng chịu tải | Dùng API reactive, timeout và giới hạn tài nguyên |
| Tự gọi **subscribe()** bên trong filter | Mất lifecycle, context và khó xử lý lỗi | Trả Mono/Flux để framework subscribe |
| Ghi API key/token vào log | Lộ bí mật qua log tập trung | Mask/không ghi credential, bảo vệ log |
| Không phân biệt 401/403 | Client và điều tra sự cố hiểu sai tình trạng | Định nghĩa rõ failure handler, entry point và access denied handler |
| Chỉ dùng **authenticated()** cho mọi tài nguyên | Người dùng A đọc được dữ liệu của B | Kiểm tra role/authority và quyền trên owner/tenant |
| Dùng default HTTP Basic failure handler cho scheme khác | Client hiểu nhầm WWW-Authenticate hoặc phương thức đăng nhập | Cấu hình failure handler phù hợp |
| Đăng ký cùng custom WebFilter nhiều lần | Xác thực lặp hoặc hành vi khó dự đoán | Đăng ký chính xác trong chain có chủ đích |

Một tình huống thường gặp: developer viết converter như sau:

~~~java
// Không an toàn: client tự khai quyền ADMIN.
Authentication spoofed =
        UsernamePasswordAuthenticationToken.authenticated(
                requestUser, null,
                List.of(new SimpleGrantedAuthority("ROLE_ADMIN")));
return Mono.just(spoofed);
~~~

Đây không phải "chuyển đổi thông tin đầu vào" đúng nghĩa; nó đã **cấp quyền** trước khi có xác minh danh tính. Converter chỉ nên trả giá trị chưa được xác thực, manager mới xác minh và tạo danh tính tin cậy.

## 10. Kiểm thử AuthenticationWebFilter thế nào?

Hãy kiểm thử ở cả **đơn vị** và **tích hợp**, đúng các ranh giới API.

**Unit test cho converter:**

1. Không có header → Mono.empty.
2. Header hợp lệ về định dạng → Authentication chưa xác thực, credentials lấy đúng, không có authority tự khai.
3. Header rỗng, quá dài, nhiều giá trị hoặc sai scheme → kết quả theo hợp đồng rõ ràng (thường AuthenticationException).
4. Không tiêu thụ request body ngoài ý muốn.

**Unit test cho manager:**

1. Credential đúng → Authentication đã xác thực, principal và authority server xác định.
2. Credential sai → AuthenticationException; không phát kết quả thành công.
3. Kho credential/policy unavailable → không fallback cấp quyền.
4. Không log key, password hoặc token; không giữ credential trong kết quả nếu không cần.
5. Truy vấn nguồn danh tính là reactive, có timeout và giới hạn tải.

**Integration test với WebTestClient:**

- Không có key: request vào API yêu cầu đăng nhập bị 401; endpoint public vẫn hoạt động.
- Key sai: failure handler phát 401.
- Key đúng: endpoint /api/me thấy đúng Authentication trong Reactor Context.
- Key đúng nhưng thiếu ROLE_ADMIN: /api/admin/report phát 403.
- Không có quyền với một bản ghi cụ thể: service/data layer chặn dù authentication thành công.
- Các request cạnh nhau dùng các credential khác nhau không bị lẫn SecurityContext.
- Nếu có session/CORS/multiple chains, test độc lập để phát hiện filter khác “ăn” credential hoặc preflight bị chặn.

Với **StepVerifier**, có thể xác minh converter/manager phát giá trị, empty hoặc error. Với **WebTestClient**, xác minh hành vi đầy đủ của SecurityWebFilterChain. Phân tách này giúp xác định lỗi nằm ở đọc credential, kiểm tra credential hay quyết định quyền.

## 11. Tình huống thực tế: API dùng bearer token

Giả sử request:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJ...
~~~

Trong cấu hình OAuth2 Resource Server, một lớp converter phù hợp sẽ nhận diện bearer credential; manager/bộ xác thực token xử lý chữ ký hoặc introspection và các điều kiện tin cậy; SecurityContext nhận danh tính; authorization tiếp tục kiểm tra scope/role rồi quyền sở hữu đơn hàng 42.

**Không suy luận rằng token giải mã được là hợp lệ.** Chỉ sau khi xác thực chữ ký và các điều kiện issuer, audience, exp, nbf, scope theo ứng dụng mới tin principal/authority. Cũng không suy luận rằng scope đọc đơn hàng cho phép xem tất cả đơn hàng: owner/tenant vẫn cần kiểm tra ở tầng nghiệp vụ.

Với bearer token tiêu chuẩn, nên cấu hình Resource Server chính thức; tự tạo AuthenticationWebFilter kiểu demo chỉ để hiểu cơ chế kiến trúc.

## 12. Câu hỏi tự kiểm tra

1. AuthenticationWebFilter dùng matcher và converter cho hai nhiệm vụ khác nhau thế nào?
2. Converter trả Mono.empty khi không thấy X-API-Key. Tại sao endpoint /api/me vẫn trả 401?
3. Converter tạo UsernamePasswordAuthenticationToken ở trạng thái unauthenticated để làm gì?
4. Sau khi manager trả Authentication đã xác thực, vai trò của success handler và ReactiveSecurityContextHolder là gì?
5. Vì sao API key sai và đã đăng nhập nhưng thiếu ROLE_ADMIN tạo ra hai kiểu thất bại khác nhau?
6. Tại sao không nên lấy ROLE_ADMIN trực tiếp từ header X-Role mà client gửi?
7. Mặc định của AuthenticationWebFilter về converter, matcher, success handler và context repository là gì?
8. Khi nào nên dùng OAuth2 Resource Server thay cho custom filter?
9. Khi nhiều authentication mechanism cùng tồn tại, matcher và SecurityWebFilterChain giúp tránh nhầm lẫn thế nào?
10. Vì sao block()/subscribe() thủ công trong reactive authentication dễ làm khó việc xử lý Context và lỗi?

**Đáp án gợi ý:** (1) matcher chọn request, converter trích credential và tạo đề nghị; (2) không thử auth không tự cấp quyền, authorization chặn anonymous; (3) tránh tự chấp nhận credential chưa kiểm tra; (4) tiếp tục luồng theo handler và mang danh tính qua Reactor Context; (5) 401 thiếu/sai bằng chứng, 403 thiếu quyền; (6) client tự chỉnh được header; (7) converter Basic, matcher any request, success tiếp tục chain, NoOp repository; (8) khi xử lý bearer token/JWT/opaque chuẩn; (9) chọn đúng chain/filter và credential, tránh xử lý lặp/nhầm; (10) gây blocking, tách subscription và mất context.

## 13. Tài liệu đối chiếu

- Spring Security Javadoc — AuthenticationWebFilter: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html
- Spring Security — Reactive Authentication: https://docs.spring.io/spring-security/reference/reactive/authentication/index.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — OAuth2 Resource Server Reactive JWT: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html

**Kết luận:** AuthenticationWebFilter là cầu nối từ **HTTP request** sang **Authentication đáng tin** trong WebFlux. Hãy hiểu chính xác sự khác nhau giữa **matcher không khớp**, **converter trả empty**, **manager trả authenticated**, và **manager báo AuthenticationException**. Chỉ manager mới xác minh credential; success đưa kết quả vào ngữ cảnh reactive; authorization tiếp tục kiểm tra quyền. Phân tách rõ các bước này giúp xây dựng bộ lọc đúng, an toàn và dễ kiểm thử.