# WebFilter và cơ chế xác thực tùy biến trong Reactive

## 1. Bài toán: thêm cơ chế xác thực mà vẫn kiểm thử được toàn bộ đường đi

Một ứng dụng Spring WebFlux có API dành cho đối tác: `GET /api/secure/report`. Đối tác phải gửi khóa thử nghiệm qua header `X-API-Key`, sau đó Spring Security tạo danh tính `partner-service` và cấp authority `REPORT_READ`. Một endpoint khác, `GET /api/secure/admin`, yêu cầu role `ADMIN` nên khóa đối tác không được phép truy cập.

Khi viết test, có hai con đường rất khác nhau:

- Dùng `mockUser()` hoặc `@WithMockUser` để đưa sẵn một `Authentication` vào ngữ cảnh. Cách này kiểm tra **phân quyền** nhưng có thể bỏ qua cơ chế đọc và kiểm tra API key.
- Gửi header `X-API-Key` qua `WebTestClient` mà **không gắn mock authentication**. Khi đó request phải đi qua `ServerAuthenticationConverter`, `ReactiveAuthenticationManager`, `AuthenticationWebFilter` và cuối cùng mới đến authorization rule.

Trong module `SPRING_SECURITY_TESTING`, người học kiểm chứng xác thực, phân quyền và bảo vệ HTTP với `spring-security-test` trên Servlet và Reactive, bao gồm MockMvc, WebTestClient, SecurityContext, JWT/OAuth2/OIDC giả lập. Bài học này tập trung vào chương **Filter và cơ chế tùy biến** ở WebFlux: cách xây dựng một cơ chế xác thực Reactive có thể kiểm thử, không nhầm `WebFilter` thông thường với cơ chế authentication của Spring Security.

Sau bài này, bạn có thể:

1. Giải thích vai trò của `WebFilter`, `SecurityWebFilterChain` và `AuthenticationWebFilter`.
2. Tách bước **đọc credential** (converter) khỏi bước **xác minh credential** (manager).
3. Đặt filter ở vị trí phù hợp với `SecurityWebFiltersOrder` và sử dụng `ReactiveSecurityContextHolder` đúng cách.
4. Kiểm tra các nhánh `200`, `401`, `403`, header bị thiếu, API key sai và quyền không đủ bằng `WebTestClient`.
5. Phân biệt test dùng mock principal với test thực sự chạy cơ chế xác thực tùy biến.
6. Nhận diện rủi ro khi dùng `subscribe()` thủ công, tắt CSRF tùy tiện, đăng ký filter hai lần hoặc tự triển khai xác thực JWT/OIDC thay cho thành phần chuẩn.

## 2. `WebFilter` khác gì `AuthenticationWebFilter`?

### 2.1. `WebFilter` là điểm chặn chung của WebFlux

Trong Spring WebFlux, một `WebFilter` có thể quan sát hoặc thay đổi request/response trước hoặc sau các thành phần downstream. Phương thức chính là:

~~~java
Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain);
~~~

Ví dụ một filter thêm header chẩn đoán:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
class DiagnosticHeaderWebFilter implements WebFilter {
    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        exchange.getResponse()
                .getHeaders()
                .add("X-Diagnostic-Filter", "applied");

        return chain.filter(exchange);
    }
}
~~~

Đoạn trên chỉ minh họa một `WebFilter` thông thường. Header này **không phải bằng chứng danh tính đã được xác minh**. Filter cũng không nên đọc hoặc ghi log credentials chỉ để phục vụ chẩn đoán.

### 2.2. Authentication là một quy trình có cấu trúc

Spring Security WebFlux cung cấp `AuthenticationWebFilter` để phối hợp nhiều thành phần:

| Thành phần | Công việc |
| --- | --- |
| `ServerWebExchangeMatcher` | Quyết định request nào cần thử cơ chế xác thực |
| `ServerAuthenticationConverter` | Đọc HTTP request và chuyển credential thành `Authentication` **chưa được xác thực** |
| `ReactiveAuthenticationManager` | Xác minh credential và trả `Authentication` đã được xác thực, hoặc phát lỗi xác thực |
| `ServerSecurityContextRepository` | Quyết định cách đọc/lưu security context khi cần persistence |
| `ServerAuthenticationSuccessHandler` | Xử lý sau xác thực thành công; mặc định có thể tiếp tục filter chain |
| `ServerAuthenticationFailureHandler` | Xử lý lỗi xác thực; trả phản hồi phù hợp thay vì cho request tiếp tục |
| `SecurityWebFilterChain` | Định vị filter và áp dụng CSRF, authentication, authorization, xử lý exception |

Luồng tổng quát:

~~~mermaid
flowchart TD
    A["GET /api/secure/report"] --> B["SecurityWebFilterChain"]
    B --> C{"AuthenticationWebFilter matcher khớp?"}
    C -- "Không" --> G["Bộ lọc downstream"]
    C -- "Có" --> D["ServerAuthenticationConverter đọc X-API-Key"]
    D --> E{"Có credential?"}
    E -- "Không" --> G
    E -- "Có" --> F["ReactiveAuthenticationManager"]
    F -- "Sai" --> H["Authentication failure handler: 401"]
    F -- "Đúng" --> I["Authentication ghi vào Reactor SecurityContext"]
    I --> G
    G --> J{"Authorization rule"}
    J -- "Chưa xác thực" --> K["Authentication entry point: 401"]
    J -- "Thiếu quyền" --> L["Access denied: 403"]
    J -- "Đủ quyền" --> M["Controller: 200"]
~~~

**Quy tắc thiết kế:** bước converter chưa được coi credential là đáng tin; bước manager mới quyết định có xác thực hay không. Không chỉ đọc `X-API-Key` rồi gắn trực tiếp principal `authenticated=true` trong một `WebFilter` tùy ý.

## 3. Reactive SecurityContext được truyền như thế nào?

Spring Security trong WebFlux sử dụng `ReactiveSecurityContextHolder` để lưu/truy xuất `SecurityContext` qua **Reactor Context**, không dựa vào một `ThreadLocal` cố định cho toàn bộ vòng đời request.

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Mono<String> currentClientName() {
    return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication())
            .map(Authentication::getName);
}
~~~

Một `AuthenticationWebFilter` được cấu hình đúng sẽ đưa authentication đã xác minh vào ngữ cảnh phù hợp để authorization và downstream controller/service nhìn thấy principal.

Không gọi `SecurityContextHolder.getContext().setAuthentication(...)` từ một WebFlux filter rồi mặc định các publisher ở thread khác sẽ nhìn thấy identity đó. Cũng không tự `subscribe()` trong filter để tạo một luồng độc lập: hãy **trả về** `Mono<Void>` từ `chain.filter(exchange)` hoặc pipeline tương ứng, để Spring điều phối subscription, lỗi và context.

Khi dùng `NoOpServerSecurityContextRepository`, authentication được áp dụng trong request hiện tại nhưng **không được lưu thành session authentication** cho request tiếp theo. “Không lưu security context” không đồng nghĩa hệ thống tự chặn mọi hình thức session/cookie ở các thành phần khác.

## 4. Thiết kế API key demo và hợp đồng HTTP

Chúng ta dùng hai endpoint bảo vệ và một endpoint công khai:

| Request | Quy tắc | Kết quả |
| --- | --- | --- |
| `GET /api/public` | `permitAll()` | `200` khi không gửi khóa |
| `GET /api/secure/report` | `hasAuthority('REPORT_READ')` | `200` với API key đúng |
| `GET /api/secure/admin` | `hasRole('ADMIN')` | `403` với khóa đối tác chỉ có `REPORT_READ` |
| `GET /api/secure/report` thiếu `X-API-Key` | Yêu cầu đã xác thực | `401` |
| `GET /api/secure/report` với khóa sai | Manager từ chối credential | `401` |

API key là một **bearer secret**: ai sở hữu giá trị đúng có thể chứng minh mình là đối tác theo chính sách hiện tại. Không sử dụng header `X-User` hoặc tên đối tác do client tự khai để quyết định authentication. Trong ứng dụng sản xuất, khóa phải đủ entropy, được lưu an toàn (ưu tiên hash có chính sách phù hợp), xoay vòng/thu hồi được và chỉ truyền qua HTTPS. Ví dụ dùng một khóa hardcode **duy nhất cho bài kiểm thử**, tuyệt đối không được dùng trong sản phẩm.

Ví dụ controller WebFlux:

~~~java
import java.security.Principal;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class PartnerApiController {

    @GetMapping("/api/public")
    Mono<String> publicInfo() {
        return Mono.just("public");
    }

    @GetMapping("/api/secure/report")
    Mono<Map<String, String>> report(Mono<Principal> principal) {
        return principal.map(p -> Map.of(
                "client", p.getName(),
                "report", "summary"));
    }

    @GetMapping("/api/secure/admin")
    Mono<String> admin() {
        return Mono.just("administration");
    }
}
~~~

Các dependencies Gradle thường cần:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Ví dụ sử dụng Spring Boot WebFlux và Spring Security có hỗ trợ `AuthenticationWebFilter`, `ServerAuthenticationConverter` và `SecurityWebFiltersOrder`. Một dự án có cả starter Servlet và WebFlux phải kiểm tra loại application đã được khởi tạo; nếu Spring MVC đang được chọn, không thể giả định Reactive filter chain chạy.

## 5. Bước 1: `ServerAuthenticationConverter` đọc header

Converter nhận `ServerWebExchange` và trả một `Mono<Authentication>` chưa được xác thực, hoặc `Mono.empty()` khi request không cung cấp credential.

~~~java
import org.springframework.security.authentication
        .UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.server.authentication
        .ServerAuthenticationConverter;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

final class ApiKeyHeaderConverter
        implements ServerAuthenticationConverter {

    static final String HEADER = "X-API-Key";

    @Override
    public Mono<Authentication> convert(ServerWebExchange exchange) {
        String rawKey = exchange.getRequest()
                .getHeaders()
                .getFirst(HEADER);

        if (rawKey == null) {
            // Không có credential để thử xác thực.
            return Mono.empty();
        }

        // CHƯA công nhận caller là authenticated tại bước này.
        return Mono.just(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "api-key-candidate", rawKey));
    }
}
~~~

Ở đây `UsernamePasswordAuthenticationToken` chỉ được mượn làm vật mang credential cho demo. Trong hệ thống lớn, có thể định nghĩa một loại `Authentication` riêng, chẳng hạn `ApiKeyAuthenticationToken`, để tránh nhầm API key với password và giảm nguy cơ một manager khác xử lý nhầm.

**Phân biệt ba kết quả:**

- **Không có header** → `Mono.empty()`: filter không thử xác thực, request đi tiếp và authorization layer quyết định có cần identity không.
- **Có header nhưng giá trị trống/sai** → tạo authentication **chưa xác thực**; manager phải từ chối.
- **Có header hợp lệ** → converter vẫn chỉ tạo authentication chưa xác thực; manager phải kiểm tra rồi mới trả authentication đã xác thực.

Production nên từ chối headers trùng lặp, giá trị không đúng định dạng, quá dài và các dạng nhập mơ hồ. Ví dụ dùng `getFirst()` để giữ logic giảng dạy ngắn gọn; đây **không phải** parser hoàn chỉnh cho API key ở môi trường mở.

## 6. Bước 2: `ReactiveAuthenticationManager` xác thực credential

Manager chịu trách nhiệm kiểm tra key và chỉ trả principal đã xác thực khi giá trị hợp lệ. Ví dụ dưới dùng một secret fixture cố định trong code test:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication
        .UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
class ApiKeyAuthenticationConfiguration {

    static final String DEMO_KEY = "test-only-partner-key-123456";

    @Bean
    ReactiveAuthenticationManager apiKeyAuthenticationManager() {
        return candidate -> {
            if (!(candidate instanceof UsernamePasswordAuthenticationToken)) {
                return Mono.empty();
            }

            Object credentials = candidate.getCredentials();
            if (!(credentials instanceof String suppliedKey)
                    || !MessageDigest.isEqual(
                        suppliedKey.getBytes(StandardCharsets.UTF_8),
                        DEMO_KEY.getBytes(StandardCharsets.UTF_8))) {
                return Mono.error(
                    new BadCredentialsException("Invalid API key"));
            }

            return Mono.just(new UsernamePasswordAuthenticationToken(
                    "partner-service",
                    null,
                    List.of(new SimpleGrantedAuthority("REPORT_READ"))));
        };
    }
}
~~~

Giải thích:

1. `candidate` đến từ converter; ban đầu nó chưa được xác thực.
2. Manager kiểm tra nội dung credential. `MessageDigest.isEqual(...)` tránh so sánh chuỗi bằng vòng lặp dừng ở ký tự sai đầu tiên; trong production vẫn cần lưu secret an toàn, kiểm tra chiều dài, áp dụng chính sách tạo key và xoay vòng.
3. Với khóa sai, manager phát `BadCredentialsException`. Filter sẽ chuyển lỗi này qua authentication failure handler.
4. Với khóa đúng, constructor `UsernamePasswordAuthenticationToken(principal, credentials, authorities)` tạo authentication đã xác thực. Credentials được đặt `null` để tránh giữ bản sao key trên principal lưu hành trong request.
5. Authority của đối tác chỉ là `REPORT_READ`; **không** mặc định có `ROLE_ADMIN`.

Đừng viết manager kiểu `return Mono.just(new UsernamePasswordAuthenticationToken(rawKey, rawKey, allRoles))` trước khi kiểm tra key: thao tác đó vô tình cấp quyền cho credential do client tự cung cấp.

### 6.1. Lỗi xác thực khác với thiếu quyền

- Sai key: **authentication thất bại** → phản hồi `401 Unauthorized` theo failure handler.
- Đúng key nhưng thiếu `ROLE_ADMIN`: authentication thành công, **authorization thất bại** → `403 Forbidden`.
- Không có key ở endpoint `permitAll()`: không cần authentication → `200 OK`.

Trong hệ thống thật, cách trả mã lỗi/body phải thống nhất với hợp đồng bảo mật. Không trả lại key đã nhận, hash của key hoặc mô tả chi tiết giúp suy đoán khóa trong response.

## 7. Bước 3: lắp `AuthenticationWebFilter` vào `SecurityWebFilterChain`

Thay vì tự quản lý `SecurityContext` trong một `WebFilter` thường, ta cấu hình `AuthenticationWebFilter` của Spring Security rồi đặt nó tại vị trí `SecurityWebFiltersOrder.AUTHENTICATION`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.annotation.web.reactive
        .EnableWebFluxSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication
        .AuthenticationWebFilter;
import org.springframework.security.web.server.authentication
        .HttpStatusServerEntryPoint;
import org.springframework.security.web.server.authentication
        .ServerAuthenticationEntryPointFailureHandler;
import org.springframework.security.web.server.authorization
        .HttpStatusServerAccessDeniedHandler;
import org.springframework.security.web.server.context
        .NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher
        .PathPatternParserServerWebExchangeMatcher;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class PartnerApiSecurityConfiguration {

    @Bean
    SecurityWebFilterChain partnerApiSecurity(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager apiKeyAuthenticationManager) {

        AuthenticationWebFilter apiKeyFilter =
                new AuthenticationWebFilter(apiKeyAuthenticationManager);

        apiKeyFilter.setServerAuthenticationConverter(
                new ApiKeyHeaderConverter());
        apiKeyFilter.setRequiresAuthenticationMatcher(
                new PathPatternParserServerWebExchangeMatcher(
                        "/api/secure/**"));
        apiKeyFilter.setSecurityContextRepository(
                NoOpServerSecurityContextRepository.getInstance());
        apiKeyFilter.setAuthenticationFailureHandler(
                new ServerAuthenticationEntryPointFailureHandler(
                        new HttpStatusServerEntryPoint(
                                HttpStatus.UNAUTHORIZED)));

        return http
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                .addFilterAt(
                        apiKeyFilter, SecurityWebFiltersOrder.AUTHENTICATION)
                .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/api/public").permitAll()
                    .pathMatchers(HttpMethod.GET, "/api/secure/report")
                        .hasAuthority("REPORT_READ")
                    .pathMatchers(HttpMethod.GET, "/api/secure/admin")
                        .hasRole("ADMIN")
                    .anyExchange().denyAll())
                .exceptionHandling(errors -> errors
                    .authenticationEntryPoint(
                        new HttpStatusServerEntryPoint(
                                HttpStatus.UNAUTHORIZED))
                    .accessDeniedHandler(
                        new HttpStatusServerAccessDeniedHandler(
                                HttpStatus.FORBIDDEN)))
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .build();
    }
}
~~~

**Giải thích những quyết định cấu hình:**

- `setRequiresAuthenticationMatcher("/api/secure/**")`: chỉ yêu cầu filter API key thử xác thực trên nhóm endpoint được chọn. Với `/api/public`, converter không cần chạy.
- `addFilterAt(..., SecurityWebFiltersOrder.AUTHENTICATION)`: đưa filter vào **bên trong** Spring Security filter chain tại vị trí dành cho authentication; không chỉ đăng ký một WebFilter tùy ý có thứ tự mơ hồ.
- `NoOpServerSecurityContextRepository`: ứng dụng không lưu authentication API key cho request tiếp theo; mỗi request bảo vệ phải tự mang credential.
- `authenticationEntryPoint(401)` và `accessDeniedHandler(403)`: tạo hợp đồng phản hồi rõ ràng cho client HTTP.
- `anyExchange().denyAll()`: những đường HTTP chưa được liệt kê không vô tình được phép truy cập.
- `httpBasic` và `formLogin` bị tắt trong **demo API key độc lập**, tránh trộn thêm một cơ chế xác thực không nằm trong phạm vi ví dụ.
- `csrf` bị tắt **chỉ với giả định demo là API stateless không dựa vào cookie/session của trình duyệt để chứng thực**. Nếu ứng dụng hỗ trợ form/session/browser credentials, phải đánh giá CSRF và thường giữ bảo vệ phù hợp; không lấy ví dụ này làm quy tắc tắt CSRF cho mọi ứng dụng.

### 7.1. Vì sao không khai báo `AuthenticationWebFilter` như một WebFilter bean toàn cục?

Trong WebFlux, các bean `WebFilter` có thể được áp dụng như **global web filters**. Nếu bạn vừa đăng ký `AuthenticationWebFilter` làm bean `WebFilter` toàn cục, vừa chèn cùng instance vào `SecurityWebFilterChain`, có nguy cơ nó chạy **hai lần** hoặc sai vị trí.

Ví dụ trên **khởi tạo filter bên trong factory method của `SecurityWebFilterChain`**, không xuất bản nó thành một bean `WebFilter` riêng. Chỉ `ReactiveAuthenticationManager` được quản lý bằng bean. Cách này giúp filter thuộc đúng security chain và giữ thứ tự có chủ đích.

### 7.2. Khi có nhiều security chains

Ứng dụng có thể cần:

- Một chain riêng cho `/api/**` dùng API key/Bearer token.
- Một chain khác cho trình duyệt dùng form/OIDC login với CSRF và session.
- Một fallback chain từ chối các path không được công bố.

Khi đó dùng `securityMatcher(...)` và `@Order` để chọn chain phù hợp, bảo đảm **mọi request** thuộc một chain mong muốn. Không tạo chain chỉ match `/api/**` rồi mặc định các path còn lại cũng được bảo vệ; nếu không có fallback chain thì những path không match có thể không được áp dụng security chain đó.

## 8. Kiểm thử bằng `WebTestClient`, không giả lập authentication

Để xác minh chính cơ chế API key, request phải gửi **header thực** tới filter trong application context. Đừng dùng `mockUser()` cho các ca dưới đây, bởi mock principal có thể vượt qua phần converter/manager cần kiểm tra.

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class ApiKeyWebFluxSecurityTests {

    @Autowired
    ApplicationContext context;

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
    void publicEndpointNeedsNoKey() {
        client.get()
              .uri("/api/public")
              .exchange()
              .expectStatus().isOk()
              .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void missingKeyIsUnauthorized() {
        client.get()
              .uri("/api/secure/report")
              .exchange()
              .expectStatus().isUnauthorized();
    }

    @Test
    void invalidKeyIsUnauthorized() {
        client.get()
              .uri("/api/secure/report")
              .header("X-API-Key", "incorrect-key")
              .exchange()
              .expectStatus().isUnauthorized();
    }

    @Test
    void blankKeyIsUnauthorized() {
        client.get()
              .uri("/api/secure/report")
              .header("X-API-Key", "")
              .exchange()
              .expectStatus().isUnauthorized();
    }

    @Test
    void validKeyCreatesPrincipalAndAllowsReport() {
        client.get()
              .uri("/api/secure/report")
              .header(
                  "X-API-Key",
                  ApiKeyAuthenticationConfiguration.DEMO_KEY)
              .exchange()
              .expectStatus().isOk()
              .expectBody()
              .jsonPath("$.client").isEqualTo("partner-service")
              .jsonPath("$.report").isEqualTo("summary");
    }

    @Test
    void validKeyWithoutAdminAuthorityIsForbidden() {
        client.get()
              .uri("/api/secure/admin")
              .header(
                  "X-API-Key",
                  ApiKeyAuthenticationConfiguration.DEMO_KEY)
              .exchange()
              .expectStatus().isForbidden();
    }

    @Test
    void userControlledIdentityHeaderCannotBypassAuthentication() {
        client.get()
              .uri("/api/secure/report")
              .header("X-User", "admin")
              .exchange()
              .expectStatus().isUnauthorized();
    }
}
~~~

Test context giả định đang nạp các lớp `PartnerApiController`, `ApiKeyAuthenticationConfiguration`, `PartnerApiSecurityConfiguration` của mục 4–7. Cách bind ở đây chạy toàn bộ WebFlux handler/filter trong Spring application context, nhưng **không mở TCP port**. Nếu project có controller/service khác hoặc nhiều security chains, cần kiểm soát test context để request đi qua đúng chain.

### 8.1. Ý nghĩa của từng ca

| Test | Converter | Manager | Authorization | Dự kiến |
| --- | --- | --- | --- | --- |
| Public không key | Không match / không cần | Không chạy | `permitAll` | `200` |
| Report không key | `Mono.empty()` | Không chạy | Cần authentication | `401` |
| Report key sai | Tạo candidate | `BadCredentialsException` | Không cấp principal | `401` |
| Report key rỗng | Tạo candidate rỗng | Từ chối | Không cấp principal | `401` |
| Report key đúng | Tạo candidate | Trả principal `partner-service` | Có `REPORT_READ` | `200` |
| Admin key đúng | Tạo candidate | Trả principal `partner-service` | Thiếu `ROLE_ADMIN` | `403` |
| Giả mạo `X-User` | Không có API key | Không chạy | Không xác thực | `401` |

Đặc biệt, ca **key sai `401`** và ca **key đúng `200`** phải cùng tồn tại. Nếu mọi request đều bị `401` do filter bị cấu hình sai, chỉ có test âm sẽ không chứng minh cơ chế xác thực hoạt động đúng.

### 8.2. Một lỗi khó phát hiện: mock principal che lỗi filter

Một test kiểu sau vẫn có thể xanh ngay cả khi manager API key bị hỏng:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;

client.mutateWith(mockUser("pretend-admin").roles("ADMIN"))
      .get()
      .uri("/api/secure/admin")
      .exchange()
      .expectStatus().isOk();
~~~

Vì mock principal đã có `ROLE_ADMIN`, bộ lọc API key không cần có credential để endpoint nhận đủ quyền. Kết quả đó chỉ chứng minh **authorization chấp nhận một principal giả có vai trò ADMIN**; nó **không chứng minh** key đã được đọc, đối chiếu hay bị từ chối khi sai.

Với mục tiêu kiểm thử **custom authentication**, luôn có các ca request thật chứa credential hợp lệ và không hợp lệ **mà không gắn mock principal**. Với mục tiêu kiểm thử policy thuần túy, `mockUser()` vẫn hữu ích và tiết kiệm chi phí tạo fixture.

## 9. Unit test cho converter và manager

HTTP integration test là bằng chứng mạnh nhất cho đường filter, nhưng các thành phần nhỏ vẫn nên có unit tests để xác định lỗi nhanh.

### 9.1. Converter không có header phải trả `Mono.empty()`

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive
        .MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import reactor.test.StepVerifier;

@Test
void converterIgnoresRequestWithoutApiKey() {
    var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/api/secure/report"));

    StepVerifier.create(
            new ApiKeyHeaderConverter().convert(exchange))
        .verifyComplete();
}
~~~

Đây là test chỉ dành cho converter: không có key không tự tạo authentication, chưa kết luận HTTP sẽ trả `401` vì authorization layer không tham gia.

### 9.2. Converter phải giữ authentication ở trạng thái chưa xác thực

~~~java
@Test
void converterProducesUnauthenticatedCandidate() {
    var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/api/secure/report")
                .header("X-API-Key", "any-value"));

    StepVerifier.create(
            new ApiKeyHeaderConverter().convert(exchange))
        .assertNext(auth -> {
            assertFalse(auth.isAuthenticated());
            assertEquals("any-value", auth.getCredentials());
        })
        .verifyComplete();
}
~~~

Test này cần `org.junit.jupiter.api.Assertions.assertFalse` và `assertEquals`. Nó chứng minh converter **không tự công nhận credential**, giúp bắt lỗi nếu converter vô tình tạo token 3 tham số đã authenticated.

### 9.3. Unit test cho manager

~~~java
@Test
void managerRejectsWrongKey() {
    ReactiveAuthenticationManager manager =
            new ApiKeyAuthenticationConfiguration()
                    .apiKeyAuthenticationManager();

    var candidate =
            UsernamePasswordAuthenticationToken.unauthenticated(
                    "api-key-candidate", "wrong");

    StepVerifier.create(manager.authenticate(candidate))
            .expectError(BadCredentialsException.class)
            .verify();
}

@Test
void managerGrantsOnlyReportRead() {
    ReactiveAuthenticationManager manager =
            new ApiKeyAuthenticationConfiguration()
                    .apiKeyAuthenticationManager();

    var candidate =
            UsernamePasswordAuthenticationToken.unauthenticated(
                    "api-key-candidate",
                    ApiKeyAuthenticationConfiguration.DEMO_KEY);

    StepVerifier.create(manager.authenticate(candidate))
            .assertNext(auth -> {
                assertTrue(auth.isAuthenticated());
                assertEquals("partner-service", auth.getName());
                assertTrue(auth.getAuthorities().stream()
                    .anyMatch(a -> a.getAuthority().equals("REPORT_READ")));
                assertFalse(auth.getAuthorities().stream()
                    .anyMatch(a -> a.getAuthority().equals("ROLE_ADMIN")));
            })
            .verifyComplete();
}
~~~

Thêm imports cho `ReactiveAuthenticationManager`, `UsernamePasswordAuthenticationToken`, `BadCredentialsException`, `StepVerifier` và JUnit assertions. Unit tests chỉ xác nhận converter/manager riêng lẻ; hãy giữ các WebTestClient tests ở mục 8 để bảo đảm chúng **được nối đúng vào security chain**.

## 10. Kiểm thử qua HTTP server thật

`WebTestClient.bindToApplicationContext(...)` kiểm tra được web filter và authentication manager thực trong **một tiến trình mock server**. Nếu cần xác nhận HTTP headers/cookies đi qua socket, dùng server thật với cổng động:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ApiKeyRealHttpTests {

    @LocalServerPort
    int port;

    @Test
    void apiKeyIsAuthenticatedAcrossRealHttp() {
        WebTestClient http = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .build();

        http.get()
            .uri("/api/secure/report")
            .header(
                "X-API-Key",
                ApiKeyAuthenticationConfiguration.DEMO_KEY)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.client").isEqualTo("partner-service");

        http.get()
            .uri("/api/secure/report")
            .header("X-API-Key", "wrong")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

Kiểu test này không dùng `@WithMockUser` và không truyền một `SecurityContext` giả từ JUnit qua socket; request thực tự mang key. Kết quả chứng minh thêm HTTP binding và đường request đi vào WebFlux server đang chạy.

Nó **chưa** xác nhận reverse proxy, TLS, load balancer hoặc kho API key của production. Các thành phần đó cần integration/end-to-end test ở môi trường phù hợp, với secret thử nghiệm riêng và chính sách không ghi log credentials.

## 11. Lỗi thường gặp trong filter Reactive

### 11.1. Gọi `subscribe()` hoặc `block()` bên trong filter

Sai:

~~~java
@Override
public Mono<Void> filter(
        ServerWebExchange exchange, WebFilterChain chain) {
    chain.filter(exchange).subscribe(); // Sai: tách khỏi pipeline
    return Mono.empty();
}
~~~

Lời gọi tự `subscribe()` có thể làm mất khả năng điều phối lỗi, context và vòng đời request, thậm chí tạo xử lý chồng chéo. Cũng không nên `block()` trong event-loop để truy vấn dữ liệu xác thực. Đúng là **trả về pipeline**:

~~~java
@Override
public Mono<Void> filter(
        ServerWebExchange exchange, WebFilterChain chain) {
    return chain.filter(exchange);
}
~~~

Với kiểm tra key từ database hoặc cache, dùng repository/client Reactive (trả `Mono`) bên trong `ReactiveAuthenticationManager`, bảo đảm lỗi và cancellation được xử lý theo chuỗi hiện tại.

### 11.2. Đặt authentication tùy tiện vào `SecurityContextHolder`

Một custom `WebFilter` tự gọi:

~~~java
SecurityContextHolder.getContext()
        .setAuthentication(authentication);
~~~

không đảm bảo WebFlux downstream ở thread khác đọc được identity đó. Dùng `AuthenticationWebFilter` và cơ chế Reactor Context của Spring Security. Chỉ khi có lý do đặc biệt mới tự xây authentication propagation, và phải kiểm thử cả subscriber context lẫn HTTP authorization.

### 11.3. Dùng sai vị trí hoặc đăng ký filter hai lần

- Một `@Component WebFilter` thông thường được đăng ký trên global chain; `@Order` cho global filter **không** đồng nhất với `SecurityWebFiltersOrder` bên trong Spring Security.
- `AuthenticationWebFilter` cần được chèn với `addFilterAt`/`addFilterBefore`/`addFilterAfter` theo nhu cầu, không gắn ngẫu nhiên.
- Tránh xuất bản cùng authentication filter vừa thành global `WebFilter` bean vừa thành thành phần bên trong `SecurityWebFilterChain`.

### 11.4. Converter trả `Mono.empty()` cho mọi key sai

Nếu converter coi cả key sai là “không có credential” và filter cho request tiếp tục, việc phản hồi có thể phụ thuộc vào anonymous authorization rule. Hãy phân biệt **không có credential** với **credential đã cung cấp nhưng sai**: trường hợp thứ hai phải được xử lý như authentication failure, không âm thầm rơi về một cơ chế danh tính khác.

### 11.5. Xử lý lỗi không nhất quán

Không tự trả `200` và ghi body “invalid key” trong authentication failure handler. Hãy dùng status phù hợp (`401` cho key sai/chưa xác thực, `403` cho đã xác thực nhưng thiếu quyền), response body không tiết lộ secret và xử lý exception không làm lộ stack trace.

### 11.6. Vô tình cấp quyền cho tất cả API keys

Ví dụ demo chỉ có một đối tác và một authority. Trong hệ thống thực, manager nên lấy thông tin principal và authorities từ dữ liệu tin cậy tương ứng với key đã xác thực. **Không** ánh xạ tất cả khóa hợp lệ thành `ROLE_ADMIN` hay dùng claim/header do request tự khai để cấp quyền.

## 12. Trường hợp cần OAuth2, OIDC hoặc JWT thay vì API key tự viết

API key là ví dụ dễ thấy cách kết nối converter/manager; không phải khuyến nghị thay thế những giao thức đã có.

| Nhu cầu | Cơ chế thường nên dùng | Kiểm thử phù hợp |
| --- | --- | --- |
| HTTP Basic với username/password | `httpBasic()` và authentication manager/provider phù hợp | Gửi Basic credentials đúng/sai qua WebTestClient |
| Bearer JWT access token | `oauth2ResourceServer().jwt()` và `ReactiveJwtDecoder` | JWS thật ký đúng/sai, `exp`/`iss`/`aud` và scopes |
| OAuth2 Login | `oauth2Login()` với client registrations | Mock login cho controller, integration test callback/token exchange |
| OpenID Connect Login | `oauth2Login()` với OIDC provider | `mockOidcLogin()` cho mapping; integration test ID token validation |
| Khóa API nội bộ độc lập | Converter + `ReactiveAuthenticationManager` tùy biến | Test header thiếu/sai/đúng, 401/403/200 và rotation/revocation |
| Đa cơ chế trên nhiều đường HTTP | Nhiều security chains có matcher/ordering rõ ràng | Test từng chain và fallback, cả trường hợp cơ chế bị trộn |

Nếu một ứng dụng dùng `mockJwt()` hoặc `mockOidcLogin()` trong WebTestClient, nó đang cấp một principal **giả** cho test. Điều đó không chứng minh JWT đã được decoder kiểm tra chữ ký, OIDC ID token được xác minh hay authorization code được đổi tại token endpoint. Tương tự, `mockUser()` không chứng minh converter API key đã nhận header.

Đối với JWT/OIDC, đừng tự viết một `WebFilter` chỉ Base64-decode payload rồi cấp quyền từ `scope` hoặc `role`: payload chưa được xác minh có thể do bất kỳ client nào tạo. Hãy sử dụng các authentication mechanisms chuẩn và thêm validator/authorization converter khi cần.

## 13. Checklist về an toàn và khả năng quan sát

Trước khi kết luận custom reactive authentication đã sẵn sàng, kiểm tra:

1. **Phạm vi filter:** Matcher đúng paths/methods; không bỏ sót endpoint mới và không gây ảnh hưởng ngoài ý muốn cho endpoint công khai.
2. **Đầu vào:** Header credential thiếu, rỗng, trùng lặp, quá dài hoặc sai định dạng được xử lý theo chính sách rõ ràng.
3. **Xác thực:** Chỉ manager sau khi kiểm tra key với nguồn tin cậy mới trả `Authentication` có `isAuthenticated=true`.
4. **Phân quyền:** Principal chỉ có authorities cần thiết; test cả ca đủ quyền và ca thiếu từng quyền.
5. **Context:** Danh tính đúng trong Reactor Context, không rò rỉ sang request khác, không phụ thuộc ThreadLocal Servlet.
6. **Thứ tự:** Filter nằm đúng `SecurityWebFiltersOrder`, không bị chạy hai lần do global registration.
7. **Bảo mật transport:** HTTPS khi truyền secret thật; không ghi access token/API key vào log, metrics tags hoặc trace.
8. **Lưu trữ credential:** Khóa được sinh đủ mạnh, lưu an toàn, hỗ trợ xoay vòng, hết hạn và thu hồi.
9. **Lỗi:** Credential sai → `401`; key đúng nhưng thiếu quyền → `403`; ca key đúng và đủ quyền → `200`.
10. **CSRF/session:** Chỉ tắt CSRF khi kiến trúc thực sự phù hợp; không đánh đồng no-op security context repository với việc mọi hình thức session đều biến mất.
11. **Thử nghiệm âm:** Không chỉ có test `200`, phải có test thiếu key, key sai, thiếu quyền, đường dẫn không được công bố.
12. **Tích hợp ngoài tiến trình:** Nếu cần xác minh HTTP server, proxy, TLS hoặc secret store thực, thêm integration tests phù hợp môi trường.

## 14. Bài tập thực hành

### Bài tập 1: Phân biệt lỗi xác thực và thiếu quyền

Giữ cấu hình ở mục 7. Viết ba ca WebTestClient đối với `GET /api/secure/report`: không có key, key sai, key đúng. Khẳng định `401`, `401`, `200`. Sau đó gọi `GET /api/secure/admin` bằng key đúng và chứng minh `403` xuất hiện **sau khi** key được chấp nhận.

### Bài tập 2: Bắt lỗi converter công nhận credential quá sớm

Thay `UsernamePasswordAuthenticationToken.unauthenticated(...)` bằng một token đã authenticated ngay trong converter ở nhánh thực hành riêng. Viết unit test khẳng định converter phải trả `isAuthenticated=false`. Giải thích nguy cơ nếu converter gán authorities từ header do client kiểm soát.

### Bài tập 3: Xác thực từ Reactive repository

Thay hằng `DEMO_KEY` bằng `ReactiveApiKeyRepository.findByKeyId(...)` và một bộ kiểm tra secret/hash đáng tin. Viết test khi key không tồn tại, bị thu hồi, hết hạn và hợp lệ có `REPORT_READ`; bảo đảm không dùng `block()` hoặc gọi `subscribe()` thủ công.

### Bài tập 4: Nhiều cơ chế xác thực

Một ứng dụng có `/api/partner/**` dùng API key và `/web/**` dùng form login. Thiết kế các `SecurityWebFilterChain` có matcher, thứ tự và fallback rõ ràng. Giải thích chain nào có CSRF, chain nào stateless và cách ngăn API key được dùng cho trang admin.

### Bài tập 5: Đối chứng với mock principal

Viết test `mockUser("admin").roles("ADMIN")` cho endpoint `/api/secure/admin`. Test có thể trả `200` dù không gửi API key. Giải thích vì sao nó chỉ phù hợp cho **authorization test**, và dùng test header thực để kiểm tra custom authentication.

### Bài tập 6: So sánh mock WebFlux và HTTP server thật

Chạy cùng hai ca key đúng/sai bằng `bindToApplicationContext(...).apply(springSecurity())` và bằng `bindToServer()` với `RANDOM_PORT`. Nêu thành phần đã được kiểm chứng trong mỗi cách, và những thứ cả hai vẫn chưa chứng minh về cơ sở dữ liệu key hoặc hạ tầng sản xuất.

## 15. Tổng kết

**`WebFilter` là điểm chặn Reactive tổng quát; `AuthenticationWebFilter` là thành phần Spring Security dành cho quy trình xác thực.** Một cơ chế tùy biến nên tách rõ việc trích credential (`ServerAuthenticationConverter`), xác minh credential (`ReactiveAuthenticationManager`), quản lý security context, xử lý lỗi và phân quyền.

Trong kiểm thử, `mockUser()`, `mockJwt()` hay OAuth2/OIDC principal giả rất hữu ích để đánh giá policy nhưng **không thay thế** request mang credential thật. Muốn chứng minh cơ chế API key hoạt động, phải có các ca thiếu key, key sai, key hợp lệ và key hợp lệ nhưng thiếu quyền, chạy qua đúng filter chain bằng `WebTestClient`. Cách kết hợp này giúp phát hiện cả lỗi xây dựng danh tính lẫn lỗi phân quyền.

## 16. Tài liệu tham khảo

- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): cấu hình `ServerHttpSecurity` và `SecurityWebFilterChain`.
- [Spring Security — AuthenticationWebFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html): matcher, converter, manager và handlers.
- [Spring Security — ServerAuthenticationConverter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationConverter.html): chuyển `ServerWebExchange` thành authentication candidate.
- [Spring Security — ReactiveAuthenticationManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ReactiveAuthenticationManager.html): xác minh authentication trong Reactive.
- [Spring Security — Reactive Authentication Architecture](https://docs.spring.io/spring-security/reference/reactive/authentication/architecture.html): Reactor Context và bảo mật Reactive.
- [Spring Security — Reactive Test Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html): `WebTestClient` và `springSecurity()`.
- [Spring Security — Testing Authentication](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html): `mockUser()` và giới hạn của principal giả.
- [Spring Framework — Web Filters](https://docs.spring.io/spring-framework/reference/web/webflux/filters.html): `WebFilter`, `WebFilterChain` và phản hồi Reactive.
