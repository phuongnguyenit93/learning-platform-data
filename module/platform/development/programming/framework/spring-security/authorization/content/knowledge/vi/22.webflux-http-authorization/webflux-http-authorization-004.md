# SecurityWebExchangeMatcher và lựa chọn filter chain trong Spring Security WebFlux

## 1. Bối cảnh: một ứng dụng WebFlux có nhiều vùng bảo mật

Trong ứng dụng dùng **Spring WebFlux**, cùng một server có thể phục vụ nhiều loại HTTP endpoint:

- `/api/**`: REST API nhận Bearer JWT.
- `/api/admin/**`: API quản trị cần authority đặc biệt.
- `/ui/**`: giao diện nội bộ hoặc API dành cho client xác thực HTTP Basic.
- `/actuator/**`: health/metrics có quy tắc truy cập riêng.
- Những đường dẫn còn lại: cần chặn mặc định thay vì vô tình mở công khai.

Vấn đề không chỉ là endpoint có quyền READ hay WRITE. Có thể mỗi vùng cần **một chuỗi WebFilter khác nhau**, dùng cơ chế xác thực, session, CSRF, exception handling và header policy khác nhau.

Spring Security Reactive cho phép đăng ký nhiều bean `SecurityWebFilterChain`; một bộ chọn sẽ duyệt chúng theo thứ tự, chọn **chain khớp đầu tiên** với `ServerWebExchange` đang xử lý. Trong mỗi chain đã được chọn, các rule authorization mới quyết định request cụ thể cần `permitAll`, `authenticated`, `hasRole`, `hasAuthority` hay bị `denyAll`.

**Tên API cần phân biệt:** đề bài có cụm "SecurityWebExchangeMatcher". Trong mã nguồn Spring Security WebFlux, interface matcher chính thức là **`ServerWebExchangeMatcher`**, không phải một interface riêng tên `SecurityWebExchangeMatcher`. Loại chain là **`SecurityWebFilterChain`**. Nên tìm kiếm/import đúng các tên này khi làm việc với Java API.

Mục tiêu sau bài học:

1. Hiểu vai trò `ServerWebExchangeMatcher` và `SecurityWebFilterChain`.
2. Phân biệt **chọn chain** với **chọn authorization rule bên trong chain**.
3. Nắm nguyên tắc **first matching chain wins**, `@Order` và fallback.
4. Cấu hình nhiều chain dùng JWT/HTTP Basic mà không làm lộ route.
5. Dùng `PathPatternParserServerWebExchangeMatcher`, `ServerWebExchangeMatchers` và matcher ghép.
6. Biết cách kiểm thử bằng `WebTestClient` và phát hiện chain bị shadow/bỏ sót.
7. Tránh nhầm kiến trúc WebFlux với Servlet, cũng như tránh matcher blocking trong reactive stack.

## 2. WebFlux khác Servlet ở những API nào?

| Mục đích | Servlet stack | Reactive WebFlux |
| --- | --- | --- |
| Request context | `HttpServletRequest` | `ServerWebExchange` |
| API cấu hình HTTP | `HttpSecurity` | `ServerHttpSecurity` |
| Filter bảo mật | Servlet `Filter` | WebFlux `WebFilter` |
| Chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Matcher | `RequestMatcher` | **`ServerWebExchangeMatcher`** |
| Bộ điều phối chain | `FilterChainProxy` | `WebFilterChainProxy` |
| DSL authorization | `authorizeHttpRequests(...)` | `authorizeExchange(...)` |
| Match đường dẫn ở cấp rule | `requestMatchers(...)` | `pathMatchers(...)`/`matchers(...)` |
| Bộ kiểm thử HTTP | `MockMvc` | `WebTestClient` |
| Principal trong reactive pipeline | Servlet context/thread strategy | Reactive SecurityContext gắn Reactor Context |

Không copy trực tiếp `AntPathRequestMatcher`, `RequestAuthorizationContext` hoặc Servlet `SecurityFilterChain` vào một ứng dụng WebFlux và kỳ vọng nó hoạt động như `ServerWebExchangeMatcher`. Một project có cả dependency MVC lẫn WebFlux cần xác định **loại web application thực sự đang chạy**, vì Spring Boot có quy tắc chọn web application type; import đúng tên chưa bảo đảm đang chạy reactive server.

Trong WebFlux, các thao tác matching và xác thực có thể dựa trên **`Mono`**, vì pipeline không đồng bộ. Tránh chặn event loop bằng `block()`, JDBC blocking, I/O file đồng bộ hoặc gọi HTTP blocking trong custom matcher.

## 3. SecurityWebFilterChain hoạt động như thế nào?

`SecurityWebFilterChain` là một contract với hai khái niệm quan trọng:

```java
Mono<Boolean> matches(ServerWebExchange exchange);
Flux<WebFilter> getWebFilters();
```

Đây là chữ ký **minh họa từ interface** (cần imports Reactor/Spring và tùy version); Spring Security xây chain thông qua `ServerHttpSecurity`, nên đa số ứng dụng không tự implement interface này.

`WebFilterChainProxy` nhận các `SecurityWebFilterChain` đã đăng ký theo thứ tự và thực hiện logic khái niệm:

```text
HTTP request: GET /api/documents/42
           |
           v
WebFilterChainProxy
           |
           +--> Chain 1 matcher ?  NO
           |
           +--> Chain 2 matcher ?  YES
           |              |
           |              +--> chọn CHAIN 2
           |              +--> chạy WebFilter của CHAIN 2
           |              +--> trong chain, xét authorization rules
           |
           +--> Chain 3? KHÔNG xét tiếp
```

**First match wins:** Một request không chạy nối tiếp qua *tất cả* `SecurityWebFilterChain`. Chọn chain khác với việc gọi nhiều lớp authorization manager trong cùng chain.

Khi một chain đã khớp nhưng rule bên trong trả DENY hoặc authentication thất bại, Spring Security **không chuyển sang chain tiếp theo để tìm rule dễ hơn**. Điều này giúp các chain hoạt động có thứ tự và cũng khiến cấu hình chain quá rộng ở ưu tiên cao dễ "nuốt" toàn bộ những chain phía sau.

Trong cấu hình nhiều chain, **`@Order`** của bean quyết định thứ tự xét: thứ tự số thấp hơn thường được xét trước. Đặt chain chuyên biệt trước, chain tổng quát sau.

## 4. ServerWebExchangeMatcher là gì?

Interface `org.springframework.security.web.server.util.matcher.ServerWebExchangeMatcher` có phương thức:

```java
Mono<ServerWebExchangeMatcher.MatchResult> matches(
    ServerWebExchange exchange
);
```

**Khác biệt cần nhớ:**

- `ServerWebExchangeMatcher.matches(...)` trả `Mono<MatchResult>`.
- `SecurityWebFilterChain.matches(...)` trả `Mono<Boolean>`.
- `MatchResult` có `isMatch()` và `getVariables()`, có thể chứa những biến path được trích xuất.
- Một matcher là **phép xác định request có khớp điều kiện không**, không phải một cơ chế xác minh user được phép truy cập resource.
- Matcher có thể xét HTTP method, path, content type và các thuộc tính khác theo implementation.

Các factory/implementation thường gặp:

| Loại | Công dụng |
| --- | --- |
| `PathPatternParserServerWebExchangeMatcher` | Khớp path pattern dựa trên Spring PathPattern |
| `ServerWebExchangeMatchers.pathMatchers(...)` | Factory khớp một hoặc nhiều path, có overload theo HTTP method |
| `ServerWebExchangeMatchers.anyExchange()` | Match mọi request |
| `ServerWebExchangeMatchers.matchers(...)` | Kết hợp theo OR, khớp nếu có một matcher con khớp |
| `AndServerWebExchangeMatcher` | Kết hợp AND: mọi matcher con phải khớp |
| `OrServerWebExchangeMatcher` | Kết hợp OR: chỉ một matcher con cần khớp |
| `NegatedServerWebExchangeMatcher` | Phủ định một matcher |
| `MediaTypeServerWebExchangeMatcher` | Khớp theo media type theo API/configuration cụ thể |
| `IpAddressServerWebExchangeMatcher` | Khớp theo địa chỉ IP/subnet, phải xét proxy trust |

Các matcher chỉ là công cụ **route selection**. Nếu một chain riêng dành cho `/api/admin/**`, trong chain đó vẫn phải cấu hình authentication và authority thích hợp. Không có cơ chế tự suy ra role ADMIN từ tên đường dẫn.

### Factory khớp path

```java
import org.springframework.http.HttpMethod;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatcher;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

ServerWebExchangeMatcher allApi =
    ServerWebExchangeMatchers.pathMatchers("/api/**");

ServerWebExchangeMatcher onlyApiPost =
    ServerWebExchangeMatchers.pathMatchers(
        HttpMethod.POST, "/api/**");
```

Đây là **fragment** trong ứng dụng Spring Security Reactive, không chạy độc lập bằng `javac` thuần. Matcher đầu không hạn chế method; matcher thứ hai chỉ match POST trong phạm vi path. Khi gắn matcher thứ hai cho **toàn bộ chain**, GET và OPTIONS sẽ không vào chain đó.

### PathPatternParserServerWebExchangeMatcher

```java
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

var apiMatcher =
    new PathPatternParserServerWebExchangeMatcher("/api/**");
```

Spring WebFlux dùng hệ thống `PathPattern`; không áp mọi giả định về `AntPathMatcher` từ mã Servlet cũ. Nên kiểm thử các biến thể đường dẫn thật, context path, dấu slash ở cuối, encoding, case và đường dẫn qua reverse proxy. Chỉ nhìn một chuỗi `"/api/**"` mà chưa test thì chưa chứng minh bao phủ toàn bộ endpoint.

## 5. Hai tầng matcher: chain-level và authorization rule-level

Đây là sự phân biệt quan trọng nhất của bài:

| Tầng | API | Câu hỏi |
| --- | --- | --- |
| **Chọn chain** | `http.securityMatcher(matcher)` | Chain cấu hình này có áp dụng cho request hay không? |
| **Quy tắc trong chain** | `http.authorizeExchange(ex -> ex.pathMatchers(...))` | Request đã vào chain này cần quyền gì? |

Ví dụ:

```java
http
    .securityMatcher(
        new PathPatternParserServerWebExchangeMatcher("/api/**")
    )
    .authorizeExchange(exchanges -> exchanges
        .pathMatchers("/api/public/**").permitAll()
        .pathMatchers("/api/admin/**").hasAuthority("SCOPE_admin")
        .anyExchange().authenticated()
    );
```

Ý nghĩa:

1. Chain này **chỉ được xét thành công** với request khớp `/api/**`.
2. Trong chain ấy, `/api/public/**` được permit nếu các cơ chế khác không chặn.
3. `/api/admin/**` yêu cầu authority `SCOPE_admin`.
4. Các path API còn lại yêu cầu authenticated.
5. `/dashboard` **không chịu tác động** bởi `anyExchange().authenticated()` ở chain này, vì không được chain-level matcher chọn.

Một lỗi nghiêm trọng:

```java
http
    .securityMatcher(
        new PathPatternParserServerWebExchangeMatcher("/api/**")
    )
    .authorizeExchange(ex -> ex
        .anyExchange().authenticated()
    );
```

Nếu đây là chain duy nhất và ứng dụng có `/admin` nằm ngoài `/api/**`, request `/admin` **có thể không đi qua Spring Security WebFilter của bất kỳ chain nào**. Nó không tự động bị `authenticated()` chặn. Vì vậy cần một **fallback chain** match mọi request hoặc thiết kế bao phủ hết tất cả route được bảo vệ.

### PermitAll ở tầng rule không giống bỏ security filter

`permitAll()` nghĩa là authorization rule cho phép request ở tầng đó. Nó **không tự bỏ chain**, không tự tắt CSRF, authentication filters, CORS, security headers hoặc exception handling.

Ví dụ `GET /api/public/info` được permitAll trong một chain bật JWT: một request không có Authorization header có thể đi qua; nhưng request gửi **Bearer token sai** vẫn có thể bị authentication filter từ chối theo cách resource server hoạt động. Đừng suy ra permitAll nghĩa là bỏ qua tất cả filter.

Ngược lại, **chain không match** nghĩa là bộ lọc bảo mật của chain đó không tham gia request. Đây là lý do phải đặc biệt kiểm tra các "lỗ hổng bao phủ" của matcher.

## 6. @Order: chain chuyên biệt phải đứng trước chain tổng quát

Xét hai chain:

- `admin`: `/api/admin/**`, yêu cầu chính sách admin riêng.
- `api`: `/api/**`, yêu cầu JWT authenticated cho các API thông thường.

Nếu `api` đứng trước, request `GET /api/admin/users` đã match `/api/**` và dừng ở chain API. Chain admin **không được xét nữa**, bất kể admin đặt role yêu cầu chặt hơn.

**Sai:**

```text
@Order(1) apiChain   -> /api/**       authenticated()
@Order(2) adminChain -> /api/admin/** hasRole("ADMIN")
GET /api/admin/users -> vào apiChain, adminChain bị shadow
```

**Đúng hướng:**

```text
@Order(1) adminChain -> /api/admin/** admin policy
@Order(2) apiChain   -> /api/**       normal API policy
@Order(99) fallback  -> mọi request   denyAll()
```

Không nhất thiết phải tách chain admin nếu nó dùng **cùng cơ chế authentication** với API còn lại. Khi đó một chain API với rule `pathMatchers("/api/admin/**").hasRole("ADMIN")` trước `anyExchange().authenticated()` thường đơn giản hơn. Dùng nhiều chain khi cần tách **bộ WebFilter/cơ chế authentication** hoặc cấu hình HTTP khác nhau thật sự, không phải chỉ để mỗi URL có một bean.

### @Order không phải SecurityWebFiltersOrder

`@Order` trên `SecurityWebFilterChain` điều khiển **chain nào được xét trước**.

`SecurityWebFiltersOrder` dùng cho `http.addFilterAt/addFilterBefore/addFilterAfter`, điều khiển vị trí **WebFilter bên trong chain đã chọn**.

Đó là hai trục thứ tự độc lập. Chèn custom WebFilter vào một vị trí "sớm" không khiến chain chứa nó được chọn trước những chain khác.

## 7. Cấu hình thực tế: API JWT, UI HTTP Basic và fallback DENY

Ví dụ sau được viết cho **ứng dụng Spring Boot WebFlux + Spring Security** dùng Java 17+. Nó là **một class cấu hình ứng dụng**, có thể biên dịch khi các dependency tương thích được khai báo; muốn chạy một server thật còn cần endpoints, cấu hình JWT decoder/issuer, nguồn user Basic và các hạ tầng liên quan.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityChainsConfig {

    // Các request /api/** dùng Bearer JWT.
    @Bean
    @Order(1)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**")
            )
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(
                    HttpMethod.GET, "/api/public/info"
                ).permitAll()
                .pathMatchers("/api/admin/**")
                    .hasAuthority("SCOPE_admin")
                .anyExchange().authenticated()
            )
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            // Chỉ phù hợp API thực sự dùng Bearer token không dùng
            // cookie/session browser làm nguồn authentication.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }

    // UI nội bộ dùng HTTP Basic cho mục đích minh họa.
    @Bean
    @Order(2)
    SecurityWebFilterChain uiChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/ui/**")
            )
            .authorizeExchange(exchanges -> exchanges
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    // Không để bất kỳ URL nào rơi ra ngoài Spring Security.
    @Bean
    @Order(99)
    SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .anyExchange().denyAll()
            )
            .build();
    }
}
```

**Lưu ý thiết yếu khi dùng ví dụ:**

1. `@EnableWebFluxSecurity` áp dụng cho stack WebFlux. Nếu ứng dụng dùng Spring MVC, đây không phải cấu hình thay cho `@EnableWebSecurity`.
2. `@Order(1)`, `@Order(2)`, `@Order(99)` được dùng để xác định thứ tự rõ ràng, không phụ thuộc bean registration order.
3. `securityMatcher` của chain API khớp tất cả HTTP methods bên trong `/api/**`. `authorizeExchange` mới áp các quyền cụ thể.
4. `hasAuthority("SCOPE_admin")` giả định bộ chuyển đổi JWT authority map scope `admin` thành `SCOPE_admin` theo cấu hình. Nếu converter khác, phải đổi authority cho khớp, không tự cấp role.
5. `httpBasic(...)` ở UI cần một `ReactiveUserDetailsService` hoặc một `ReactiveAuthenticationManager` phù hợp. Không tự hardcode password plaintext vào production.
6. `oauth2ResourceServer(...jwt(...))` yêu cầu decoder và cấu hình issuer/audience/token verification đáng tin. Nếu thiếu, ứng dụng có thể không khởi tạo được hoặc JWT không được xác thực như mong đợi.
7. `csrf(disable)` ở chain API chỉ hợp lý khi endpoint **không dựa vào credential tự gửi qua cookie của browser**; nếu dùng cookie/session hoặc có luồng mixed-mode, phải đánh giá CSRF thay vì copy nguyên cấu hình này.
8. Chain fallback với `denyAll()` là cách **chặn những request chưa thuộc API/UI**. Nếu cần endpoint public như health, tạo rule hẹp có chủ đích trong fallback hoặc chain chuyên biệt đã kiểm thử, không xóa fallback.
9. Một request vào `/api/admin/users` sẽ dùng **apiChain**, và được kiểm tra `SCOPE_admin`. Trong ví dụ không có chain admin riêng vì JWT authentication giống toàn API.
10. Nếu Spring Boot Management/Actuator chạy ở **management port/management context riêng**, phải kiểm tra cấu hình bảo mật của context đó; không suy luận chỉ từ những chain của application context chính.

### Bảng đường đi theo cấu hình trên

| Request | Chain được chọn | Quy tắc authorization |
| --- | --- | --- |
| `GET /api/public/info` | apiChain | permitAll |
| `POST /api/public/info` | apiChain | authenticated (GET-only public rule không match) |
| `GET /api/documents/42` | apiChain | authenticated |
| `POST /api/admin/users` | apiChain | `SCOPE_admin` |
| `GET /ui/home` | uiChain | authenticated bằng cơ chế Basic được cấu hình |
| `GET /random` | fallbackChain | denyAll |
| `OPTIONS /api/documents` | apiChain | Được chọn theo path, CORS/preflight còn tùy cấu hình |
| `GET /actuator/health` | fallbackChain nếu trong cùng app context | denyAll nếu chưa có ngoại lệ rõ |

Bảng mô tả chain selection và rule, **không phải cam kết status code duy nhất**: authentication entry point, CORS, CSRF, resource tồn tại hay không, exception handling và request headers còn ảnh hưởng kết quả HTTP. Nếu một endpoint không có controller, sau khi được authorize nó vẫn có thể trả 404.

## 8. Nếu cần chain admin riêng

Chỉ tách chain `/api/admin/**` khi nó thật sự cần security mechanisms/header policy riêng. Ví dụ rule tổng quát về thứ tự:

```java
@Bean
@Order(1)
SecurityWebFilterChain adminChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher(
                "/api/admin/**"
            )
        )
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().hasAuthority("SCOPE_admin")
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        )
        .build();
}

@Bean
@Order(2)
SecurityWebFilterChain ordinaryApiChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**")
        )
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        )
        .build();
}
```

Đây là **hai bean mẫu thay thế cách cấu hình apiChain ở mục trước**, không phải đoạn được thêm nguyên xi cùng lúc với bean `apiChain` đã có. Nếu copy cả ba sẽ có chain chồng nhau và behavior có thể gây hiểu nhầm. Cần bổ sung imports/config JWT và fallback.

**Ranh giới quan trọng:** mỗi chain phải tự cấu hình những thành phần security mình cần. Chain admin không tự "kế thừa" cơ chế JWT, CSRF hoặc exception handling của chain API thấp hơn chỉ vì path trùng nhau. Một chain match trước **chiếm toàn bộ request**.

## 9. Khi nào nên dùng một chain thay vì nhiều chain?

Một chain duy nhất thường dễ audit hơn khi toàn bộ ứng dụng dùng **cùng authentication mechanism** và chỉ khác permissions:

```java
@Bean
SecurityWebFilterChain oneChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/public/**").permitAll()
            .pathMatchers("/api/admin/**").hasRole("ADMIN")
            .pathMatchers(HttpMethod.GET, "/api/**")
                .hasAuthority("SCOPE_read")
            .pathMatchers(HttpMethod.POST, "/api/**")
                .hasAuthority("SCOPE_write")
            .anyExchange().denyAll()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        )
        .build();
}
```

Đây là một **alternative** (cần imports, JWT decoder và endpoints), không phải đoạn cấu hình bổ sung cho ví dụ ba chain ở trên.

**Phân biệt phạm vi:**

- `anyExchange().denyAll()` trong một chain match-all bảo vệ mọi request chưa match rule.
- `anyExchange().denyAll()` trong chain chỉ match `/api/**` chỉ bảo vệ **phần chưa có rule của API**. Các URL khác cần chain khác.
- `pathMatchers(...).permitAll()` chỉ mở đúng match, không làm toàn chain public.
- Không cần tách chain theo mỗi role: rule authorization trong cùng chain đã được xét **theo thứ tự khai báo**.

Nhiều chain hợp lý khi:

- API Bearer-only cần CSRF strategy khác UI cookie-based.
- Một vùng dùng form login, vùng khác dùng OAuth2 Resource Server.
- Một vùng cần exception handling hoặc security headers khác.
- Management endpoints có cơ chế bảo mật độc lập.
- Một số route cần security context repository khác (cẩn trọng với stateless/stateful).
- Có yêu cầu giảm độ phức tạp của matcher conditions bên trong một chain quá lớn.

Nếu tất cả chỉ khác `READ/WRITE/ADMIN`, một chain với rules được sắp xếp cẩn thận thường ít rủi ro hơn.

## 10. Thứ tự các rule bên trong authorizeExchange

Có **hai kiểu thứ tự**:

**Tầng 1 – giữa các SecurityWebFilterChain:** quyết định bằng `@Order` và `securityMatcher(...)`.

**Tầng 2 – trong chain đã chọn:** `authorizeExchange` có các matcher/rule được xét theo thứ tự đăng ký.

Ví dụ:

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/**").authenticated()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().denyAll()
)
```

Rule `/api/**` rộng nằm trước nên request `/api/admin/**` sẽ match rule đầu; rule ADMIN chuyên biệt về sau **không được áp dụng** như bạn dự tính.

Đúng:

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .pathMatchers("/api/**").authenticated()
    .anyExchange().denyAll()
)
```

Thứ tự **specific before general** cần áp dụng cả hai tầng nhưng đây là **hai cấu hình khác nhau**, không nên nhầm chúng làm một.

### Một response 403 không có nghĩa chain sau được thử

Giả sử chain đầu khớp `/api/admin/**` và chặn vì user thiếu role. Spring Security không tiếp tục thử chain thứ hai match `/api/**` để cho user đi qua với `authenticated()`. Nếu có hành vi như vậy, cấu hình chính sách sẽ cực kỳ dễ bypass. First-match chain ngăn fallback nới quyền sau khi một chain đã được chọn.

## 11. Path, HTTP method, context path và reverse proxy

Nhiều lỗi chỉ xuất hiện khi chạy sau API gateway hoặc reverse proxy:

```text
Client:   https://example.test/service-a/api/documents/42
Proxy:    strip prefix /service-a
Backend:  /api/documents/42
```

Matcher `/api/**` của WebFlux có thể phù hợp ở backend nếu proxy đã strip prefix. Nhưng nếu proxy giữ prefix và ứng dụng nhận path khác, chain có thể không khớp như kỳ vọng.

Cần kiểm thử **đường dẫn mà WebFlux thực sự thấy**, không chỉ URL hiển thị ở browser. Nếu ứng dụng cấu hình context path/base-path riêng, kết quả path pattern cần được xác minh bằng test.

### Những tình huống cần test

| Tình huống | Rủi ro |
| --- | --- |
| `/api` và `/api/` | Pattern `/api/**` có thể không hoạt động giống mong đợi ở mọi điều kiện; test |
| `/api/admin` và `/api/admin/` | Không dựa vào trực giác về trailing slash |
| Encoded slash / percent encoding | Proxy/backend normalize khác nhau |
| Case variation | `/API` so với `/api` |
| Double slash và dot-segments | Khác biệt chuẩn hóa path giữa nhiều tầng |
| HTTP `HEAD` | Quy tắc GET có được áp dụng? Test độc lập |
| `OPTIONS` preflight | Chọn chain nào, có bị authentication/CSRF chặn trước CORS? |
| WebSocket upgrade | Handshake HTTP có được bảo vệ, frames có policy riêng? |
| URL rewrite phía gateway | Public route vô tình thành protected hoặc ngược lại |
| Management port riêng | Chain app không tự bao phủ management context |

Tránh tự ghép string `path.startsWith("/api")` cho security route khi cần nhận diện segment. Chuỗi này còn match `/apix`, `/api-admin` nếu không kiểm tra segment boundary. Dùng Spring `PathPattern` hoặc matcher đã được kiểm chứng.

### Path variable không phải authorization

Matcher `"/api/users/{userId}"` có thể trích ra `userId`, nhưng việc nhận ra path **không chứng minh** người đang đăng nhập chính là user ID đó. Policy vẫn phải kiểm tra subject/resource/tenant và các quyền nghiệp vụ từ nguồn tin cậy.

## 12. Matcher theo HTTP method: lợi ích và bẫy

`ServerWebExchangeMatchers.pathMatchers(HttpMethod.POST, "/api/**")` có thể dùng nếu thật sự muốn một chain riêng chỉ cho POST. Nhưng điều này làm GET/PUT/PATCH/DELETE/HEAD/OPTIONS nằm ngoài chain đó.

Ví dụ **nguy hiểm nếu thiếu fallback**:

```java
@Bean
SecurityWebFilterChain postOnly(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            ServerWebExchangeMatchers.pathMatchers(
                HttpMethod.POST, "/api/**"
            )
        )
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated()
        )
        .build();
}
```

Nếu đây là chain duy nhất, `GET /api/private` không match. Nó không được chain này bảo vệ. Trong đa số trường hợp, tốt hơn là match `/api/**` ở **chain-level** và phân biệt method **bên trong authorizeExchange**.

Ví dụ:

```java
http
    .securityMatcher(
        ServerWebExchangeMatchers.pathMatchers("/api/**")
    )
    .authorizeExchange(exchanges -> exchanges
        .pathMatchers(HttpMethod.GET, "/api/public/**").permitAll()
        .pathMatchers(HttpMethod.POST, "/api/**")
            .hasAuthority("SCOPE_write")
        .pathMatchers(HttpMethod.GET, "/api/**")
            .hasAuthority("SCOPE_read")
        .anyExchange().denyAll()
    );
```

Request PUT hoặc DELETE không được vô tình coi như GET/POST. `anyExchange().denyAll()` làm rõ hành vi phương thức chưa được cấu hình.

## 13. CORS, CSRF và xác thực không phải là cùng một vấn đề

### 13.1. CORS preflight thường là OPTIONS

Một browser gửi:

```http
OPTIONS /api/documents/42
Origin: https://app.example.test
Access-Control-Request-Method: PUT
Access-Control-Request-Headers: authorization,content-type
```

Preflight có thể **không chứa Bearer token**. Nếu chain API match theo **chỉ POST/GET** ở cấp chain hoặc rule mặc định yêu cầu authenticated cho mọi OPTIONS, CORS có thể hỏng dù request PUT có quyền khi chạy từ một HTTP client không phải browser.

Đúng hướng:

- Chain-level path matcher nên đủ rộng bao phủ `OPTIONS` của vùng API.
- Cấu hình CORS với **allowed origins, methods, headers** rõ ràng tại server/WebFlux/Spring Security.
- Xem xét thứ tự xử lý preflight, không giải quyết bằng cách `permitAll()` mọi route hoặc mọi origin.
- Test preflight cả thành công lẫn origin trái phép, headers không được phép.
- Không tin rằng browser CORS là bảo vệ authorization: client không phải browser không bị CORS ràng buộc như browser.

### 13.2. CSRF không được tắt bừa

Với API stateless chỉ nhận Bearer token trong `Authorization` và không dùng cookie tự gửi tự động, có thể cân nhắc disable CSRF cho **chain API cụ thể**. Nhưng nếu WebFlux UI dùng cookie/session hoặc Browser credential tự động, CSRF vẫn là lớp phòng vệ quan trọng cho các thay đổi state.

Không chỉ vì `/api/**` là API nên tắt CSRF cho toàn bộ server. Khi đổi chain, CSRF filters có thể khác; nếu một đường dẫn vào nhầm chain, bạn vừa thay đổi authentication vừa thay đổi CSRF behavior.

### 13.3. 401, 403, 404 không chọn lại chain

- **401** thường là chưa authenticated/credential không hợp lệ theo entry point.
- **403** thường là đã authenticated nhưng thiếu quyền (hoặc một số CSRF failures).
- **404** có thể đơn thuần là không có handler/resource; không chứng minh một chain có bảo vệ đúng hay không.

Không thấy 401 từ một test không đủ để kết luận authentication đã bị tắt: cần xét endpoint tồn tại, chain đã chọn và status do error handler trả.

## 14. Dùng matcher ghép AND, OR, NOT

Nếu một chain áp dụng cho nhiều vùng tương đương:

```java
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatcher;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

ServerWebExchangeMatcher protectedAreas =
    ServerWebExchangeMatchers.matchers(
        ServerWebExchangeMatchers.pathMatchers("/api/**"),
        ServerWebExchangeMatchers.pathMatchers("/internal/**")
    );
```

`matchers(...)` factory trong tài liệu tạo matcher **OR**: chỉ cần một vùng khớp.

Tương đương dùng class:

```java
import org.springframework.security.web.server.util.matcher.OrServerWebExchangeMatcher;

ServerWebExchangeMatcher protectedAreas =
    new OrServerWebExchangeMatcher(
        ServerWebExchangeMatchers.pathMatchers("/api/**"),
        ServerWebExchangeMatchers.pathMatchers("/internal/**")
    );
```

Đây là **fragment riêng thay thế** fragment trên, không nên khai báo hai biến `protectedAreas` cùng một scope. Dùng `OrServerWebExchangeMatcher` cho nhiều path được **quản trị và kiểm thử**.

Ghép AND:

```java
import org.springframework.http.HttpMethod;
import org.springframework.security.web.server.util.matcher.AndServerWebExchangeMatcher;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatcher;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

ServerWebExchangeMatcher onlyPostApi =
    new AndServerWebExchangeMatcher(
        ServerWebExchangeMatchers.pathMatchers("/api/**"),
        ServerWebExchangeMatchers.pathMatchers(
            HttpMethod.POST, "/api/**"
        )
    );
```

Ở đây AND hơi dư thừa (matcher thứ hai đã giới hạn cả method lẫn path), chỉ nhằm minh họa **mọi** điều kiện đều phải match. Trong code thực tế, dùng một matcher method+path cho yêu cầu đơn giản.

Phủ định:

```java
import org.springframework.security.web.server.util.matcher.NegatedServerWebExchangeMatcher;

ServerWebExchangeMatcher notApi =
    new NegatedServerWebExchangeMatcher(
        ServerWebExchangeMatchers.pathMatchers("/api/**")
    );
```

**Cảnh báo:** matcher phủ định một vùng có thể tạo phạm vi **rất rộng**, gồm cả những endpoint mới chưa biết. Nếu dùng `notApi` làm chain cho khu vực public, bạn có thể vô tình mở route nhạy cảm. Mọi matcher NOT/OR rộng nên được đi kèm `denyAll`/guardrails và test negative.

## 15. Custom ServerWebExchangeMatcher: khi nào và viết thế nào?

Bạn có thể implement `ServerWebExchangeMatcher` khi cần một điều kiện chọn chain chưa có factory phù hợp.

Ví dụ matcher chỉ áp dụng cho **GET tới `/reports/**`**:

```java
import org.springframework.http.HttpMethod;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatcher;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;
import reactor.core.publisher.Mono;

ServerWebExchangeMatcher reportsGet =
    ServerWebExchangeMatchers.pathMatchers(
        HttpMethod.GET, "/reports/**");
```

Trường hợp này **không cần custom matcher**. Dùng factory có sẵn thường dễ review hơn.

Khi cần logic mới, interface yêu cầu trả `Mono<MatchResult>`:

```java
import org.springframework.http.HttpMethod;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatcher;

ServerWebExchangeMatcher healthGet = exchange -> {
    boolean allowedPath =
        "/health".equals(
            exchange.getRequest().getPath().pathWithinApplication().value());
    boolean isGet =
        HttpMethod.GET.equals(exchange.getRequest().getMethod());

    return allowedPath && isGet
        ? ServerWebExchangeMatcher.MatchResult.match()
        : ServerWebExchangeMatcher.MatchResult.notMatch();
};
```

Đây là **fragment WebFlux**, cần ứng dụng/context và các imports tương ứng. Nó dùng dữ liệu request đồng bộ đơn giản và trả một `Mono` đã biết, không gọi `block()`. Với đường dẫn phức tạp, nên dùng `PathPatternParserServerWebExchangeMatcher` thay cho so sánh chuỗi.

### Đừng dùng request header do client tự đặt làm căn cứ tin cậy

Ví dụ một matcher coi `X-Internal-Request: true` là bằng chứng request đến từ hệ thống nội bộ có thể làm một chain ít bảo vệ được chọn bởi attacker chỉ cần tự gửi header.

Nếu cần phân biệt internal/public traffic, hãy dùng trust boundary đáng tin: gateway cấu hình mTLS/service identity, mạng, token audience, certificate verification hoặc cơ chế kiểm tra kết hợp; lưu ý **chain selection xảy ra trước một số bước authentication** nên không được mặc định có authenticated principal tại đó.

**Nguyên tắc:** matcher chọn **cách xử lý một request**, không thể tự thay thế authentication và authorization đối với resource thật.

### Tránh blocking trong matcher

Không viết:

```java
ServerWebExchangeMatcher badMatcher = exchange -> {
    // Anti-pattern: blocking database query ngay trên event loop.
    boolean enabled = jdbcRepository.checkSomePolicy();
    return enabled
        ? ServerWebExchangeMatcher.MatchResult.match()
        : ServerWebExchangeMatcher.MatchResult.notMatch();
};
```

Đây là **anti-pattern** minh họa, không phải code nên dùng. Matcher còn cần nhẹ, không gây side effect, không đọc/consume request body tùy tiện. Nếu thật sự phải tra dữ liệu I/O để chọn chain, hãy xem có thể tránh tách chain và đưa quyết định sang `ReactiveAuthorizationManager` trong chain hay không; nếu bắt buộc thì dùng non-blocking reactive data access với timeout và failure behavior rõ, không cố `block()`.

## 16. Không nhầm matcher với ReactiveAuthorizationManager

Trong WebFlux, rule tùy biến của `authorizeExchange(...).access(...)` sử dụng cơ chế reactive authorization. Ví dụ một truy vấn quyền object theo principal:

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/documents/{documentId}")
        .access((authenticationMono, context) ->
            authenticationMono
                .flatMap(auth -> documentPolicy
                    .canRead(auth,
                        context.getVariables().get("documentId"))
                )
                .map(
                    org.springframework.security.authorization.AuthorizationDecision::new
                )
                .defaultIfEmpty(
                    new org.springframework.security.authorization.AuthorizationDecision(false)
                )
        )
    .anyExchange().denyAll()
)
```

Đây là **pseudocode cấu hình ở mức fragment**, giả định `documentPolicy.canRead(auth, id)` trả `Mono<Boolean>` và tự đọc resource/tenant/owner từ nguồn tin cậy. Không phải method chuẩn có sẵn tên `documentPolicy`. Với phiên bản Spring Security mới, interface/kiểu trả về của reactive authorization có thể phát triển; phải đối chiếu Javadoc và compile dự án thật.

Điều khác nhau:

- `ServerWebExchangeMatcher`: “Đường dẫn/method này có match không?”
- `ReactiveAuthorizationManager`: “Authentication này có được phép làm việc này trong context này không?”
- `SecurityWebFilterChain`: “Những WebFilter nào sẽ bảo vệ request đã match chain?”

**Không** đặt quyền sở hữu Document 42 vào chain matcher rồi cho rằng tất cả endpoint trong chain có quyền. Object-level policy vẫn phải xác minh đúng object ID, action, tenant và trạng thái nghiệp vụ ở cấp service/data.

## 17. Spring Boot Actuator, health và management endpoints

Một hệ thống thường có endpoint `/actuator/health` để readiness/liveness, nhưng quy tắc public khác với metrics, env hoặc heapdump.

Một cấu hình sai:

```java
.authorizeExchange(ex -> ex
    .pathMatchers("/actuator/**").permitAll()
    .anyExchange().authenticated()
)
```

Điều này có thể công khai **mọi** endpoint actuator đang được exposure, nếu không có lớp bảo vệ khác.

Thiết kế tốt hơn: chỉ cho public những health endpoints thật sự được phép, bảo vệ metrics/prometheus/admin endpoints bằng authority và network policy riêng, chặn phần còn lại.

```java
.authorizeExchange(ex -> ex
    .pathMatchers(HttpMethod.GET, "/actuator/health")
        .permitAll()
    .pathMatchers("/actuator/**")
        .hasAuthority("ACTUATOR_ADMIN")
    .anyExchange().denyAll()
)
```

**Đây là fragment** chỉ mô tả rule. Nếu management endpoints nằm trên port/context khác, matcher của application chain có thể **không được áp dụng**. Các matcher chuyên dụng cho Actuator trong Spring Boot có thể phù hợp hơn hardcode path khi base-path được cấu hình; cần kiểm tra auto-configuration, management server và tests thực tế.

Cũng phải kiểm tra `/health` custom path không bị route qua một chain cho phép tất cả phương thức; một endpoint GET health public không có nghĩa POST/DELETE cùng path được phép.

## 18. WebSocket, SSE, functional routing và GraphQL

**Cùng WebFlux application không đồng nghĩa mọi loại traffic đều là một GET REST thông thường.**

- **SSE/streaming:** request mở một stream; chain selection diễn ra khi HTTP request vào, nhưng quyền có thể bị revoke trong lúc stream chạy. Nếu cần ngắt stream theo thời gian thực, thiết kế authorization enforcement trong service/streaming layer.
- **WebSocket:** handshake dùng HTTP nên matcher/chain có thể tham gia, nhưng từng message sau khi nâng cấp protocol cần policy riêng theo ứng dụng.
- **Functional routes (`RouterFunction`):** endpoint không nhất thiết có controller annotation nhưng vẫn đi qua WebFlux WebFilter chain ở lớp HTTP; test đúng URL/method.
- **GraphQL:** có thể tập trung tại `POST /graphql`; chain path matcher không biết query đang yêu cầu resource ID nào. Resolver/data fetcher/service phải kiểm tra object-level authorization.
- **Gateway:** nếu backend nhận các path đã rewrite, matcher phải được cấu hình dựa trên path mà backend thấy, không chỉ route gốc ở gateway.

Không coi `anyExchange().authenticated()` là đủ cho tất cả hành động chứa object IDs, tenant selection hoặc field-level permissions.

## 19. Kiểm thử bằng WebTestClient: chứng minh chain nào đang bảo vệ

### 19.1. Vì sao không chỉ test controller?

Khi dùng `WebTestClient.bindToController(new Controller())` mà không đưa Spring Security WebFilter vào, bạn có thể test business response **nhưng không test chain selection thật**. Muốn kiểm tra matcher, hãy dùng integration test với application context và security support; hoặc test matcher trực tiếp bằng `MockServerWebExchange` cho các path/method đặc biệt.

Ví dụ setup tiêu biểu:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

public class ReactiveSecurityTests {
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

Đây là **test class fragment**, cần test runner/config load application context, controller thật, `spring-security-test` và security dependencies. Có thể dùng `@SpringBootTest` + `@AutoConfigureWebTestClient` để khởi tạo bối cảnh tương ứng nếu dự án Spring Boot cung cấp.

### 19.2. Test API bearer JWT

Với Spring Security Test, `mockJwt()` giúp mô phỏng JWT Authentication để tập trung vào authorization:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

client
    .mutateWith(mockJwt())
    .get()
    .uri("/api/documents/42")
    .exchange()
    .expectStatus().isOk();
```

Chỉ kỳ vọng 200 nếu controller tồn tại và object-level policy cho fixture ấy phép đọc; `mockJwt()` **không tự đảm bảo quyền trên Document 42**. Nó cũng không kiểm thử signature/issuer/audience validation của token thật. Để xác minh những phần đó, cần thêm integration test Resource Server với JWT/decoder thực.

Test scope riêng:

```java
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

client
    .mutateWith(mockJwt().authorities(
        new SimpleGrantedAuthority("SCOPE_admin")
    ))
    .post()
    .uri("/api/admin/ping")
    .exchange()
    .expectStatus().is2xxSuccessful();
```

Đây là **fragment**, cần endpoint `POST /api/admin/ping` thật và fixture đúng; nếu endpoint chưa tồn tại, status sẽ không là 2xx dù authorization được cấp. Test đối chứng với JWT thiếu `SCOPE_admin` phải bị deny, đồng thời kiểm tra không có side effect.

### 19.3. Test một số tình huống chain quan trọng

| Request | Authentication | Kết quả bảo mật cần kiểm tra |
| --- | --- | --- |
| `GET /api/documents` | Không có JWT | Bị yêu cầu authentication (thường 401) |
| `GET /api/documents` | JWT hợp lệ | Đi vào API chain; authorization/object policy tiếp tục |
| `GET /api/admin/users` | JWT không có admin authority | 403/deny theo contract |
| `GET /api/admin/users` | JWT có admin authority | Không bị deny bởi rule admin |
| `GET /api/public/info` | Không có token | Rule public không yêu cầu authentication |
| `POST /api/public/info` | Không có token | Không được coi là public vì rule chỉ GET |
| `GET /ui/home` | Không có credentials Basic | Bị yêu cầu authentication phù hợp UI chain |
| `GET /random` | Có token hợp lệ | Vẫn DENY bởi fallback |
| `OPTIONS /api/documents` | Browser preflight | Đúng CORS strategy; không nhầm route |
| `/api/admin/**` | API chain đặt trước chain admin | Test phát hiện chain admin bị shadow |
| `GET /apix/documents` | Không authentication | Không lọt vào chain API do prefix nhầm; fallback DENY |
| `GET /api/admin` | JWT thường | Kiểm thử biến thể path không khớp `/api/admin/**` như dự tính |
| `GET /actuator/env` | User thường | Không lộ dữ liệu quản trị |

**Quan trọng:** assert chỉ HTTP status là chưa đủ nếu cùng một status có thể đến từ controller, CORS, CSRF hoặc matcher. Nên thêm test đường authentication đặc trưng, logging/audit theo chain (không log secrets), hoặc kiểm tra matcher riêng để biết chain nào đã được chọn.

### 19.4. Test trực tiếp ServerWebExchangeMatcher

Dùng `MockServerWebExchange` và `MockServerHttpRequest` để kiểm tra matcher đơn lẻ:

```java
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import reactor.test.StepVerifier;

var matcher =
    new PathPatternParserServerWebExchangeMatcher("/api/**");

var exchange = MockServerWebExchange.from(
    MockServerHttpRequest.get("/api/documents/42")
);

StepVerifier.create(matcher.matches(exchange))
    .expectNextMatches(result -> result.isMatch())
    .verifyComplete();
```

Đây là một **JUnit/reactor-test fragment**, cần test class/method, Spring Test và Reactor Test dependencies. Khi matcher trả `Mono<MatchResult>`, test thẳng kết quả `isMatch()` và các path variables nếu có. Test cả negative paths, methods và những đường dẫn biên; chỉ test `/api/documents/42` không đủ.

## 20. Java 17 độc lập: mô phỏng first-match chain selection

Chương trình sau **không chạy Spring Security**, mà mô phỏng thuật toán xét danh sách chain theo thứ tự bằng Java 17. Nó giúp thấy rằng **chain chọn đầu tiên quyết định**, rule của chain sau không được dùng, và fallback cần match mọi request.

Tạo file `WebFluxChainSelectionDemo.java`:

```java
import java.util.Comparator;
import java.util.List;
import java.util.function.Function;
import java.util.function.Predicate;

public class WebFluxChainSelectionDemo {

    record Request(String method, String path) {}

    record Chain(
        int order,
        String name,
        Predicate<Request> matches,
        Function<Request, String> rule
    ) {}

    static boolean under(String path, String prefix) {
        return path.equals(prefix) || path.startsWith(prefix + "/");
    }

    static String select(List<Chain> chains, Request request) {
        return chains.stream()
            .sorted(Comparator.comparingInt(Chain::order))
            .filter(chain -> chain.matches().test(request))
            .findFirst()
            .map(chain -> chain.name() + " -> "
                + chain.rule().apply(request))
            .orElse("NO_CHAIN -> UNPROTECTED_BY_THIS_MODEL");
    }

    public static void main(String[] args) {
        Chain admin = new Chain(
            1, "admin",
            r -> under(r.path(), "/api/admin"),
            r -> "ADMIN_JWT_REQUIRED"
        );

        Chain api = new Chain(
            2, "api",
            r -> under(r.path(), "/api"),
            r -> r.method().equals("GET")
                    && r.path().equals("/api/public/info")
                ? "PUBLIC_PERMIT"
                : "JWT_REQUIRED"
        );

        Chain ui = new Chain(
            3, "ui",
            r -> under(r.path(), "/ui"),
            r -> "BASIC_REQUIRED"
        );

        Chain fallback = new Chain(
            99, "fallback",
            r -> true,
            r -> "DENY_ALL"
        );

        List<Chain> safe = List.of(api, fallback, admin, ui);

        System.out.println("Admin: "
            + select(safe, new Request("GET", "/api/admin/users")));
        System.out.println("Public GET: "
            + select(safe, new Request("GET", "/api/public/info")));
        System.out.println("Public POST: "
            + select(safe, new Request("POST", "/api/public/info")));
        System.out.println("UI: "
            + select(safe, new Request("GET", "/ui/home")));
        System.out.println("Unknown: "
            + select(safe, new Request("GET", "/unknown")));
        System.out.println("Near-prefix: "
            + select(safe, new Request("GET", "/api-admin/data")));

        // Sai thứ tự: API rộng đứng trước admin.
        Chain apiFirst = new Chain(
            1, "api",
            api.matches(),
            api.rule()
        );
        Chain adminSecond = new Chain(
            2, "admin",
            admin.matches(),
            admin.rule()
        );
        System.out.println("Wrong order: "
            + select(List.of(apiFirst, adminSecond, fallback),
                new Request("GET", "/api/admin/users")));

        // Không có fallback: những URL ngoài phạm vi không được chain bảo vệ.
        System.out.println("No fallback: "
            + select(List.of(admin, api, ui),
                new Request("GET", "/unknown")));
    }
}
```

Chạy với Java 17 trở lên:

```bash
javac WebFluxChainSelectionDemo.java
java WebFluxChainSelectionDemo
```

Stdout chính xác:

```text
Admin: admin -> ADMIN_JWT_REQUIRED
Public GET: api -> PUBLIC_PERMIT
Public POST: api -> JWT_REQUIRED
UI: ui -> BASIC_REQUIRED
Unknown: fallback -> DENY_ALL
Near-prefix: fallback -> DENY_ALL
Wrong order: api -> JWT_REQUIRED
No fallback: NO_CHAIN -> UNPROTECTED_BY_THIS_MODEL
```

Giải thích:

1. Mặc dù `safe` được khai báo theo thứ tự `api, fallback, admin, ui`, hàm `select` **sắp theo order** nên admin được xét trước API.
2. `GET /api/public/info` là public trong API chain, nhưng POST cùng URL cần JWT.
3. `/api-admin/data` không được xem là `/api/**` do hàm `under` kiểm tra ranh giới segment.
4. Fallback match mọi request chưa được chain trước chọn và quyết định DENY.
5. Đảo thứ tự làm `/api/admin/users` đi vào API chain rộng, mất rule chặt hơn của admin.
6. Bỏ fallback khiến `/unknown` không có chain trong mô hình; đó là một lỗ hổng cần tránh khi ứng dụng có các route ngoài matcher.
7. Mã chỉ mô phỏng **chain selection + tên rule**; nó **không thực hiện JWT/Basic authentication, CSRF, Reactor Context hoặc Spring PathPattern parsing**. Trong ứng dụng thật phải test bằng `WebTestClient`.

## 21. Debug và quan sát chain selection trong production

Khi một endpoint trả 401/403 bất ngờ, không nên đổi `permitAll()` ngay. Hãy điều tra có hệ thống:

1. Xác định application thực chạy WebFlux hay MVC.
2. Liệt kê bean `SecurityWebFilterChain` và `@Order`.
3. Kiểm tra chain-level `securityMatcher` của từng bean.
4. Kiểm tra path/method mà server thấy **sau proxy rewrites**.
5. Xác định chain đầu tiên match.
6. Trong chain đó, xét authorization rules theo thứ tự.
7. Kiểm tra authentication mechanism đã bật, token/Basic credentials và authority mapping.
8. Kiểm tra CSRF/CORS, exception handling và status của controller/handler.
9. Kiểm tra object-level authorization ở service/domain.
10. Bổ sung regression test cho request gây lỗi.

Có thể bật logging Spring Security ở mức DEBUG trong môi trường phát triển với chính sách redaction:

```properties
logging.level.org.springframework.security=DEBUG
```

**Không** bật TRACE hoặc ghi toàn bộ Authorization headers, JWT, cookies và thông tin nhạy cảm trong production nếu chưa có kế hoạch bảo vệ log. Log quyết định nên ghi path template, chain name/revision nếu có, action, outcome và correlation ID, không lộ token hoặc nội dung tài nguyên.

### Vì sao chain bị “mất” sau khi cấu hình thêm bean?

Spring Boot/Spring Security auto-configuration có các cơ chế điều kiện khi ứng dụng khai báo `SecurityWebFilterChain` tự quản. Đừng đoán default chain nào còn tồn tại: kiểm tra **bean thực sự được đăng ký** trong application context và test mọi endpoint. Việc thêm một bean custom có thể làm cấu hình mặc định trước đó không còn được tạo theo cách bạn tưởng.

Nếu nhiều bean có cùng `@Order`, kết quả thứ tự có thể khó kiểm soát. Hãy dùng order duy nhất cho những matcher chồng nhau và có test xác minh hành vi cụ thể.

## 22. Bảo mật khi dùng nhiều chain: những điều dễ bỏ sót

### Chain selection không thay thế resource authorization

Một request `GET /api/documents/42` chọn đúng API chain và có JWT hợp lệ. Nhưng nếu Document 42 thuộc Bob hoặc tenant khác, authentication thành công vẫn không chứng minh được quyền READ trên object.

Cần thêm:

```text
JWT hợp lệ
AND role/authority hành động phù hợp
AND tenant được xác minh
AND object thật nằm trong tenant
AND (owner hoặc ACL/share grant hợp lệ)
AND resource status cho phép
```

Đặt chính sách ở service/domain và data-scoped repository query. Các luồng GraphQL, export, stream và message đều cần kiểm tra đúng tài nguyên.

### Đừng cố dùng matcher chọn chain theo quyền đã xác thực

`ServerWebExchangeMatcher` chủ yếu phân loại request **trước các cơ chế authentication bên trong chain**. Nếu đặt điều kiện “user có ROLE_ADMIN” vào matcher tùy chỉnh, tại thời điểm đó chưa chắc đã có Authentication được xác minh. Hãy để các role/claims trong `ReactiveAuthorizationManager` hoặc service policy của chain được chọn.

### Không dùng chain fallback permitAll

Một fallback:

```java
@Bean
SecurityWebFilterChain fallback(ServerHttpSecurity http) {
    return http.authorizeExchange(ex -> ex
        .anyExchange().permitAll()
    ).build();
}
```

có thể khiến route mới được thêm ngoài `/api/**` mở công khai mà không ai nhận ra. Nếu không có yêu cầu public thật rõ, chọn `denyAll`, rồi thêm whitelist hẹp khi cần.

### Mọi chain cần kiểm tra security features liên quan

Khi tách JWT/Basic hoặc UI/API, rà lại:

- CSRF behavior.
- CORS behavior.
- OAuth2 resource server/login support.
- HTTP Basic/form login.
- Session/security context repository.
- Exception handling/entry point.
- Security headers, HSTS và redirect HTTPS (tùy deployment).
- Logout endpoints.
- Filter ordering và custom WebFilters.
- Test account-lock, token expiry, issuer/audience và revoked permissions.

Tách chain không có nghĩa các cấu hình của chain khác được kế thừa tự động. Một rule `denyAll` có thể chặn truy cập nhưng chưa chắc những header/security filters của chain khác được chạy.

## 23. Ma trận kiểm thử bắt buộc trước khi release

### 23.1. Chain selection

| Kịch bản | Kỳ vọng |
| --- | --- |
| `/api/admin/**` và `/api/**` chồng nhau | Chain ưu tiên cao đúng được chọn |
| Matcher rộng đứng trước matcher hẹp | Test bắt lỗi shadow chain |
| `/api/**` và `/apix/**` | Không nhận nhầm prefix |
| `/api`, `/api/`, `/api/admin` | Đúng contract path thực |
| GET vs POST vs PUT | Không rơi khỏi chain vì matcher method hẹp |
| OPTIONS preflight | Chain và CORS chính xác |
| Không match chain chuyên biệt | Fallback denyAll |
| Không có fallback | Test phát hiện route không được bảo vệ |
| Endpoint mới ngoài `/api/**` | Không tự public |
| Route viết hoa/URL encoding/double slash | Được xử lý nhất quán với proxy và router |

### 23.2. Authentication và authorization

| Kịch bản | Kỳ vọng |
| --- | --- |
| API bearer-only, token không có | Không truy cập protected API |
| API token sai chữ ký/issuer/audience | Không được xác thực |
| JWT hợp lệ thiếu scope | 403/deny action phù hợp |
| JWT có admin scope | Không bị chặn bởi rule admin, object policy vẫn áp dụng |
| UI Basic credentials đúng/sai | Chỉ UI chain xử lý tương ứng |
| Request công khai không token | Public path hoạt động theo hợp đồng |
| Public path gửi token sai | Test hành vi authentication filter, không giả định permitAll thắng |
| Admin URL vào nhầm chain API rộng | Regression test bắt được |
| Tài liệu thuộc tenant khác | Bị object-level policy chặn |
| Cookie-based mutation không CSRF token | Bị từ chối theo chính sách CSRF |
| Request không tồn tại | Không coi 404 là bằng chứng bảo mật |

### 23.3. Hạ tầng và non-REST

- CORS origins và preflight.
- Actuator ở cùng port và management port riêng.
- Proxy strip-prefix, context path, trailing slash.
- RouterFunction, GraphQL, SSE và WebSocket handshake.
- Reactive method security nếu có `@EnableReactiveMethodSecurity`.
- Async/background work không dựa vào HTTP chain để kiểm tra quyền domain.
- Đường truy cập cache/search/file downloads.
- Nhiều phiên bản Spring Security/Boot khi nâng cấp, tên API/matcher và Java 17 requirements.
- Test dependency `spring-security-test`, thiết lập `WebTestClient.apply(springSecurity())` và JWT mocking.
- Startup tests xác nhận bean chain được tạo theo thứ tự, không trùng order ngoài dự kiến.

## 24. Các lỗi phổ biến và cách khắc phục

| Lỗi | Hậu quả | Khắc phục |
| --- | --- | --- |
| Tìm class `SecurityWebExchangeMatcher` | Không tồn tại interface như kỳ vọng | Dùng `ServerWebExchangeMatcher` |
| Mang `RequestMatcher` Servlet sang WebFlux | Sai loại API/stack | Dùng reactive matchers/`ServerWebExchange` |
| Nghĩ `authorizeExchange().anyExchange()` áp toàn ứng dụng | URL ngoài chain không được bảo vệ | Kiểm tra chain-level matcher và fallback |
| Đặt `/api/**` chain trước `/api/admin/**` | Chain hẹp bị shadow | Thứ tự bean rõ `@Order` |
| Nghĩ DENY sẽ thử chain sau | Sai logic first match | Rule DENY là kết quả trong chain đã chọn |
| Dùng matcher theo POST ở chain nhưng quên GET/OPTIONS | Các method ngoài chain | Match path rộng, xét method ở rule layer |
| Dùng `@Order` để đổi vị trí filter trong chain | Không đổi đúng thứ tự nội bộ | Dùng `SecurityWebFiltersOrder` khi cần |
| Dùng `addFilterAt` để đổi thứ tự chain | Không ảnh hưởng chain selection | Sắp xếp `@Order` và `securityMatcher` |
| Fallback `permitAll` | Route mới vô tình public | Fallback `denyAll` |
| Không có fallback | URL không match chain có thể không qua security | Đăng ký chain match-all cuối |
| Tự so khớp `startsWith("/api")` | Nhầm `/apix`, `/api-admin` | Dùng PathPattern matcher |
| Tin `X-Internal` như identity | User giả mạo header để chọn chain dễ dãi | Authentication/service trust boundary |
| Gọi `block()` trong matcher | Chặn event loop, lỗi latency/deadlock | Reactive non-blocking APIs |
| Dùng chain matcher làm object authorization | IDOR/BOLA | Service policy subject-resource-action |
| Cấu hình CSRF disabled mọi chain | Cookie-based UI dễ bị CSRF | Đánh giá theo auth mechanism từng chain |
| Mở `/actuator/**` bằng permitAll | Lộ management endpoints | Whitelist health hẹp và khóa endpoints nhạy cảm |
| Chỉ test controller bằng WebTestClient không security | Không test WebFilterChainProxy | Apply springSecurity hoặc test server |
| Test mỗi GET happy path | Bỏ lỗi method/URL overlap | Matrix path × method × authentication |
| Dùng JWT mock để khẳng định token signature an toàn | Mock không kiểm thử decoder thật | Bổ sung Resource Server integration tests |
| Quên WebFlux vs MVC auto-selection | Config không dùng trong runtime | Xác minh application type, beans và imports |
| Dùng nhiều chain cùng order | Behavior khó dự đoán | Order nhất quán và test thực |
| Dùng Servlet `SecurityFilterChain` làm fallback | Không bảo vệ WebFlux | Reactive `SecurityWebFilterChain` |

## 25. Checklist cuối cùng

1. Ứng dụng đang chạy **WebFlux** hay **Servlet MVC**?
2. Đã import đúng `ServerWebExchangeMatcher` và `SecurityWebFilterChain` chưa?
3. Có bao nhiêu bean chain, `@Order` mỗi chain là gì?
4. Matcher nào có phạm vi rộng và có khả năng che matcher hẹp?
5. Mỗi chain có cấu hình authentication/CSRF/CORS/headers của riêng nó không?
6. Tất cả path/method cần bảo vệ có match một chain không?
7. Có một fallback **match-all + denyAll** cho các route còn lại không?
8. `securityMatcher` đang chọn chain hay `pathMatchers` đang chọn rule? Team có phân biệt hai tầng không?
9. Rule hẹp có đứng trước `anyExchange` hoặc rule `/api/**` rộng không?
10. Đã test `/api`, `/api/`, HEAD/OPTIONS và proxy rewriting chưa?
11. API dùng Bearer-only có CSRF policy rõ và JWT issuer/audience hợp lệ không?
12. UI cookie/Basic/form login có CSRF và session policy phù hợp không?
13. Management/actuator paths có được bảo vệ cả khi chạy port riêng không?
14. API public `permitAll` có còn đi qua authentication/security filters như mong đợi không?
15. Custom matcher có non-blocking, side-effect-free và không dựa vào header giả mạo không?
16. Có object-level authorization sau JWT/Basic authentication không?
17. Đã dùng `WebTestClient` có Spring Security WebFilter chain thật chưa?
18. Có negative test cho chain overlap, scope thiếu, IDOR và CORS preflight chưa?
19. Có log/audit an toàn để phân biệt matcher fail, authentication fail và authorization deny chưa?
20. Mỗi thay đổi route hoặc bean chain có regression tests cho toàn bộ ma trận quan trọng không?

**Tóm tắt:** Trong Spring Security WebFlux, **`ServerWebExchangeMatcher` xác định một request có thuộc `SecurityWebFilterChain` hay không**. Bộ điều phối xét chain theo `@Order` và **chọn chain khớp đầu tiên**; các rule `authorizeExchange().pathMatchers(...)` chỉ được xét **bên trong chain đó**. Hãy đặt matcher cụ thể trước matcher tổng quát, dùng fallback match-all với `denyAll`, kiểm thử cả path và HTTP method, đồng thời vẫn bảo vệ quyền trên tài nguyên thật ở service/data layer. Đó là chìa khóa để tách JWT/UI/management an toàn mà không vô tình để một request nằm ngoài bảo vệ.

## Tài liệu tham khảo chính thức

- [Spring Security — WebFlux Security, Multiple Chains Support](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): ví dụ nhiều `SecurityWebFilterChain` với `@Order` và `securityMatcher`.
- [Spring Security — Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): `authorizeExchange`, thứ tự rule, `pathMatchers`, custom reactive authorization.
- [Spring Security Javadoc — ServerWebExchangeMatcher](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/util/matcher/ServerWebExchangeMatcher.html): `matches(ServerWebExchange)` và `Mono<MatchResult>`.
- [Spring Security Javadoc — ServerWebExchangeMatchers](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/util/matcher/ServerWebExchangeMatchers.html): factory matcher theo path/method, OR và match-all.
- [Spring Security Javadoc — SecurityWebFilterChain](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/SecurityWebFilterChain.html): `matches` và `getWebFilters`.
- [Spring Security Javadoc — ServerHttpSecurity](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html): `securityMatcher`, `authorizeExchange`, CSRF, filters và cơ chế xác thực.
- [Spring Security — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html): `apply(springSecurity())`.
- [Spring Security — Reactive Testing OAuth2/JWT](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockJwt` và phạm vi test authentication/authorization.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): cách setup test client cho WebFlux.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): kiểm tra quyền ở service bằng Reactor Context và method-security.
