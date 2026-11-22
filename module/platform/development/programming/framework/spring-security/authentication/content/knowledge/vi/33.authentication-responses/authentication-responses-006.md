# DelegatingAuthenticationEntryPoint: chọn phản hồi xác thực theo nhóm yêu cầu trong Spring Security

## 1. Mục tiêu bài học

Một ứng dụng Spring Boot có thể vừa phục vụ **trang HTML dùng form login**, vừa cung cấp **REST API cho JavaScript/mobile**. Khi người dùng chưa được xác thực, hai loại request này thường cần phản hồi khác nhau:

- Người truy cập trang `/web/private` bằng browser mong được **chuyển tới trang đăng nhập** (thường HTTP 302 tới `/login`).
- Client gọi `/api/orders` thường mong **HTTP 401 Unauthorized** và body lỗi có cấu trúc; một redirect HTML tới `/login` sẽ làm hỏng contract API.
- Client OAuth 2.0 Bearer còn cần **`WWW-Authenticate: Bearer`** theo RFC 6750, không đơn giản là một HTML redirect.
- Người dùng **đã xác thực nhưng thiếu quyền** thường phải nhận **403 Forbidden**, không phải bị đưa đi login lại.

Trong Spring Security Servlet, **`DelegatingAuthenticationEntryPoint`** giải quyết phần **chọn `AuthenticationEntryPoint` dựa trên `RequestMatcher` của request gây lỗi**. Bản thân nó không xác minh mật khẩu, không phân quyền và không thay thế filter chain; nó chỉ chọn **cách bắt đầu quá trình authentication hoặc cách trả lỗi chưa xác thực**.

Sau bài này, bạn cần:

1. Hiểu đường đi `ExceptionTranslationFilter` → `AuthenticationEntryPoint.commence(...)` và thời điểm nó thực sự được gọi.
2. Phân biệt `AuthenticationEntryPoint`, `AccessDeniedHandler` và `AuthenticationFailureHandler`; gán đúng HTTP 401, 302, 403 và các challenge headers.
3. Sử dụng `LinkedHashMap<RequestMatcher, AuthenticationEntryPoint>` cùng `setDefaultEntryPoint(...)` trên baseline Spring Security 6.5.x.
4. Thiết kế rule **ưu tiên cụ thể trước**, tránh overlap, phân loại API bằng path và kiểm tra `Accept` khi phù hợp; không dựa một header dễ giả mạo để cấp quyền.
5. Cấu hình một `SecurityFilterChain` dùng `HttpSecurity.exceptionHandling(...)`, có ví dụ Java 17+ và phép thử thực tế.
6. Biết khi nào `ExceptionHandlingConfigurer.defaultAuthenticationEntryPointFor(...)` là cách viết gọn hơn, và khi nào nên dùng **nhiều filter chains**.
7. Giữ đúng semantics của **Bearer/Basic/form login**, xử lý request cache, CSRF, saved request, CORS, JSON/Problem Details và cơ chế lỗi trong WebFlux.
8. Viết test chứng minh nhóm nào đi tới entry point nào, cả trường hợp không khớp, thứ tự rule, 401 và 403.

**Phạm vi kỹ thuật:** Java 17+, Spring Boot 3.x, Spring Security 6.5.x **Servlet** cho ví dụ đầy đủ; WebFlux có lớp tương tự nhưng API khác. Các đường dẫn và response trong bài chỉ là ví dụ; phải kiểm chứng bằng version thực tế nếu nâng cấp Spring Security 7.x.

## 2. Nhóm request và hợp đồng phản hồi: chốt yêu cầu trước khi viết code

Ví dụ ứng dụng phục vụ ba nhóm:

| Nhóm request | Ví dụ | Không có authentication hợp lệ | Đã xác thực nhưng thiếu quyền |
| --- | --- | --- | --- |
| Trang HTML cần đăng nhập | `GET /web/private`, `Accept: text/html` | HTTP 302/303 điều hướng tới `/login` theo flow | HTTP 403 hoặc trang “không có quyền”; **không** login lại mặc định |
| REST API | `GET /api/items`, có hoặc không có `Accept` | HTTP 401; JSON Problem Details nếu API contract yêu cầu | HTTP 403 với body an toàn |
| AJAX/fetch không nằm dưới `/api` | `GET /web/private`, `Accept: application/json` | HTTP 401 JSON để JS tự quyết định UI | HTTP 403 hoặc body lỗi tương ứng |
| Bearer-protected resource server | `GET /v1/data`, `Authorization: Bearer ...` | 401 kèm Bearer challenge khi phù hợp RFC 6750 | 403/`insufficient_scope` khi thiếu scope |
| HTTP Basic-only machine client | `GET /internal/resource` | 401 kèm `WWW-Authenticate: Basic realm=...` | 403 khi credential hợp lệ nhưng thiếu quyền |

Bảng là **hợp đồng mong muốn**, không phải defaults luôn được Spring Security tự suy ra. Kết quả thực tế còn tùy filter chain, exception handler, authentication mechanism, request matcher và request cache.

### Hai quyết định tách biệt

1. **Có được truy cập không?** — do authentication và authorization logic quyết định, ví dụ `authorizeHttpRequests(...).authenticated()` hoặc `hasAuthority(...)`.
2. **Khi chưa đủ điều kiện, trả lời thế nào?** — khi lỗi thuộc trường hợp có thể sử dụng authentication entry point, `DelegatingAuthenticationEntryPoint` chọn nhánh thích hợp.

Chọn 401/302 theo path **không thay đổi quyền** của path đó. Nếu một request đã được `permitAll()`, nó không tự đi qua entry point chỉ vì `Accept` hoặc path trùng quy tắc.

## 3. AuthenticationEntryPoint và ExceptionTranslationFilter

### 3.1. AuthenticationEntryPoint là gì?

Trong Servlet, interface nằm tại:

```java
org.springframework.security.web.AuthenticationEntryPoint
```

Method chính:

```java
void commence(
    HttpServletRequest request,
    HttpServletResponse response,
    AuthenticationException authException
) throws IOException, ServletException;
```

Một `AuthenticationEntryPoint` có thể:

- Trả `401` để client biết cần credentials.
- Đặt `WWW-Authenticate` cho HTTP Basic hoặc OAuth Bearer.
- Redirect tới `/login` để bắt đầu form-login flow.
- Trả JSON lỗi theo API contract.
- Có hành vi khác phù hợp cơ chế authentication đang sử dụng.

Nó **không** nhận password để kiểm tra, không tự cấp `Authentication` hoặc chạy authorization. Nó quyết định phản hồi tại **ranh giới lỗi authentication/chưa xác thực**.

### 3.2. ExceptionTranslationFilter điều phối thế nào?

Trong `SecurityFilterChain` Servlet, `ExceptionTranslationFilter` xử lý các exception bảo mật phát sinh **trong phần downstream của filter chain**. Khái quát:

```text
Incoming HTTP request
        |
        v
Security filters -> Authentication filters -> AuthorizationFilter
                                            |
                                            +-- protected + no valid auth
                                            |      |
                                            |      v
                                            |   ExceptionTranslationFilter
                                            |      |
                                            |      v
                                            |   AuthenticationEntryPoint
                                            |      |
                                            |      +-- browser -> 302 /login
                                            |      +-- API     -> 401 JSON
                                            |
                                            +-- valid auth, insufficient authority
                                                   |
                                                   v
                                                AccessDeniedHandler
                                                   |
                                                   +-- 403
```

Cần hiểu hai nhánh khi filter bắt được lỗi:

- **`AuthenticationException`:** gọi `AuthenticationEntryPoint`.
- **`AccessDeniedException`:** nếu request chưa xác thực đủ theo trust resolver (ví dụ anonymous), Spring Security có thể khởi động authentication qua entry point; nếu principal đã xác thực nhưng thiếu quyền, chuyển tới `AccessDeniedHandler`.

Không kết luận 100% mọi lỗi 401 đều do `ExceptionTranslationFilter` xử lý. Chẳng hạn `UsernamePasswordAuthenticationFilter` có `AuthenticationFailureHandler` khi submit form login sai; `BearerTokenAuthenticationFilter` cũng có luồng xử lý authentication failure riêng. Điều này quan trọng khi debug tại sao JSON entry point không được gọi cho một request chứa Bearer token sai.

### 3.3. RequestCache và SavedRequest

Với form login, Spring có thể lưu request bị chặn vào `RequestCache` để sau khi đăng nhập chuyển người dùng quay lại URL ban đầu. Khi entry point nhận 302 tới `/login`, saved request thường có ý nghĩa.

Với REST API, lưu hàng nghìn saved requests trong HTTP sessions chỉ để trả 401 thường **không có ích** và có thể tạo session không mong muốn. Thiết kế API stateless cần quyết định riêng về request cache; đừng đánh đồng việc đổi entry point sang 401 với việc đã tắt mọi cơ chế session creation.

## 4. DelegatingAuthenticationEntryPoint chọn nhánh theo quy tắc nào?

Lớp Servlet:

```java
org.springframework.security.web.authentication
    .DelegatingAuthenticationEntryPoint
```

Trong Spring Security 6.5, constructor phổ biến là:

```java
DelegatingAuthenticationEntryPoint(
    LinkedHashMap<RequestMatcher, AuthenticationEntryPoint> mappings)
```

Sau khi tạo, gọi:

```java
delegating.setDefaultEntryPoint(fallbackEntryPoint);
```

`LinkedHashMap` giữ **thứ tự khai báo**. Khi `commence(request, response, ex)` chạy, delegating entry point:

1. Duyệt các `RequestMatcher` theo thứ tự.
2. Gặp matcher đầu tiên trả `true` → gọi `AuthenticationEntryPoint.commence(...)` tương ứng rồi dừng.
3. Không matcher nào đúng → gọi `defaultEntryPoint` đã cấu hình.

```text
                        DelegatingAuthenticationEntryPoint
                                       |
                        Matcher 1: /api/** ?
                         /           \
                       yes            no
                       /               \
             JSON 401 / Bearer?     Matcher 2: Accept JSON?
                                     /              \
                                   yes               no
                                   /                  \
                              JSON 401            default entry point
                                                       |
                                                       v
                                                  Redirect /login
```

Đây là **first-match-wins**; không có cơ chế “chọn matcher cụ thể nhất” tự động nếu bạn đưa một matcher rộng lên trước. Một matcher kiểu `AnyRequestMatcher.INSTANCE` đặt đầu danh sách có thể khiến mọi matcher sau đó không bao giờ chạy.

### 4.1. Quy tắc fallback

Đối với constructor trên, **default entry point cần khác null**. Nếu không cấu hình hoặc map rỗng, Spring có thể báo lỗi cấu hình khi khởi tạo/đối chiếu `afterPropertiesSet()`. Không cố “bỏ trống để Spring tự biết”.

Với `HttpSecurity.exceptionHandling().defaultAuthenticationEntryPointFor(...)`, DSL có thể dùng entry point đăng ký đầu tiên làm fallback nếu không có match, tùy cấu hình; vì vậy **thứ tự đăng ký cũng mang ý nghĩa chính sách**. Đặt một fallback rõ ràng trong demo giúp quyết định dễ kiểm chứng.

### 4.2. Khác biệt Spring Security 7.x

Trong 6.5.x, constructor `LinkedHashMap` và `setDefaultEntryPoint(...)` vẫn là API được javadoc mô tả. Ở các nhánh 7.x mới, constructor kiểu map và setter được đánh dấu deprecated for removal; API đề nghị dùng constructor mới với `RequestMatcherEntry` hoặc builder `DelegatingAuthenticationEntryPoint.builder()`. Vì vậy ví dụ của bài cố ý dùng **6.5.x**; khi nâng version, không “copy y nguyên rồi bỏ qua deprecated” mà hãy chuyển theo API của dòng đó.

## 5. Chọn RequestMatcher: URL trước, Accept sau

### 5.1. Path là ranh giới hợp đồng rõ nhất

Nếu tổ chức định nghĩa **mọi route dưới `/api/**` là JSON API**, chọn matcher path trước. Đừng dựa vào `Accept: text/html` do attacker gửi để chuyển một API endpoint thành HTML login flow.

Nhưng path matching phải tương thích cấu hình servlet mapping, context path, reverse proxy và normalization. Trong ví dụ Boot Servlet mặc định, `request.getServletPath()` dùng để minh họa. Với hệ thống phức tạp, dùng `PathPatternRequestMatcher`/matcher do Spring Security version khuyến nghị thay vì phép so chuỗi trên `getRequestURI()` có thể bị lỗi context path hoặc URL encoding.

### 5.2. Accept có thể hỗ trợ AJAX nằm ngoài nhóm API

Một request nhận `Accept: application/json` có thể mong lỗi JSON ngay cả khi path không nằm trong `/api/**`. Spring Security có `MediaTypeRequestMatcher` kết hợp với content negotiation strategy:

```java
MediaTypeRequestMatcher jsonMatcher = new MediaTypeRequestMatcher(
        new HeaderContentNegotiationStrategy(),
        MediaType.APPLICATION_JSON
);
jsonMatcher.setIgnoredMediaTypes(Set.of(MediaType.ALL));
```

Ý nghĩa: request `Accept: */*` không tự bị coi là JSON trong ví dụ. Tuy nhiên:

- `Accept` **được client điều khiển**; nó chỉ là tín hiệu để định dạng response, không phải bằng chứng user được tin cậy hoặc có quyền.
- Browser thường gửi nhiều media types; cần test content negotiation cụ thể.
- `application/problem+json` hoặc vendor `+json` có thể cần matcher/rule bổ sung, không mặc định mọi suffix `+json` đều được nhận diện đúng bởi một `MediaType.APPLICATION_JSON`.
- Nếu một API nằm ở path cố định, nên bảo đảm API được chọn bởi **path matcher** ngay cả khi client gửi `Accept: text/html`.
- `Content-Type` của request nói về **body mà client gửi**, khác `Accept` nói về **response client muốn nhận**; đừng dùng Content-Type thay Accept cho quyết định này.

### 5.3. Header tùy ý không nên ảnh hưởng authorization

Ví dụ một HTTP header `X-Requested-With: XMLHttpRequest` đôi khi được dùng để đoán request AJAX. Header đó dễ được client giả và không đáng tin để bảo vệ endpoint. Có thể dùng cho presentation trong môi trường đã kiểm soát, nhưng không dùng để cấp quyền, bỏ qua authentication, CSRF hoặc đổi trust boundary.

## 6. Hai entry point thường dùng: status 401 và login redirect

### 6.1. HttpStatusEntryPoint

`HttpStatusEntryPoint` có constructor nhận `HttpStatus`:

```java
AuthenticationEntryPoint api401 =
        new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED);
```

Nó trả một HTTP status, phù hợp với client không muốn browser tự mở hộp thoại Basic hoặc redirect tới HTML. Nếu API contract yêu cầu JSON body, hãy dùng custom `AuthenticationEntryPoint` để ghi body an toàn.

### 6.2. LoginUrlAuthenticationEntryPoint

`LoginUrlAuthenticationEntryPoint` khởi động form login bằng redirect đến URL đã cấu hình:

```java
AuthenticationEntryPoint browserLogin =
        new LoginUrlAuthenticationEntryPoint("/login");
```

Điều kiện: `/login` phải là endpoint trang login có thể truy cập, do Spring Security formLogin tạo hoặc do bạn cung cấp. Nếu redirect tới một route cũng yêu cầu login mà không có cơ chế tạo page, ứng dụng có thể rơi vào redirect loop.

### 6.3. Basic và Bearer có challenge semantics riêng

`BasicAuthenticationEntryPoint` tạo `WWW-Authenticate: Basic realm=...`. `BearerTokenAuthenticationEntryPoint` tạo challenge Bearer phù hợp OAuth resource server khi được cấu hình đúng. Việc thay một entry point Bearer bằng `HttpStatusEntryPoint(401)` có thể làm mất challenge header mà API contract/RFC yêu cầu.

**Đừng chọn 401 chỉ vì nó “trông giống API”.** Hãy xác định API đó dùng cookie-based auth, HTTP Basic, OAuth Bearer hay nhiều mechanism; response phải cho client biết cách xử lý theo đúng giao thức.

## 7. Ví dụ hoàn chỉnh: Spring Boot Servlet trả 401 JSON cho API và 302 cho trang web

Ví dụ dùng **Java 17+, Spring Boot 3.x + Spring Security 6.5.x** trong Servlet stack, một filter chain, tài khoản demo `alice`. Đăng nhập form bình thường ở `/login`. Khi chưa đăng nhập:

- `/api/**` trả **401 Problem JSON**, bất kể `Accept`.
- Một trang ngoài API với `Accept: application/json` trả **401 Problem JSON**.
- Trang còn lại mặc định redirect **302 tới `/login`**.

Lỗi **đã đăng nhập nhưng thiếu role** vẫn do nhánh `AccessDeniedHandler` xử lý (thường 403).

### 7.1. Gradle dependencies

Trong project Spring Boot đã tạo với Java 17:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Dùng một Servlet web application; không thêm WebFlux chỉ để copy cấu hình ở mục sau. Nếu dependency management từ Spring Boot chọn Spring Security version khác 6.5.x, kiểm tra API trước khi chạy.

### 7.2. File Java đầy đủ

Lưu ở `src/main/java/demo/entrypoint/EntryPointDemoApplication.java`:

```java
package demo.entrypoint;

import java.util.LinkedHashMap;
import java.util.Set;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.DelegatingAuthenticationEntryPoint;
import org.springframework.security.web.authentication.LoginUrlAuthenticationEntryPoint;
import org.springframework.security.web.util.matcher.MediaTypeRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;
import org.springframework.web.accept.HeaderContentNegotiationStrategy;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import jakarta.servlet.http.HttpServletResponse;

@SpringBootApplication
public class EntryPointDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(EntryPointDemoApplication.class, args);
    }

    @Bean
    UserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
                .password("{noop}local-demo-only")
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        // Demo sử dụng DispatcherServlet mapping mặc định "/".
        // Production: ưu tiên framework RequestMatcher theo version.
        RequestMatcher apiPath = request -> {
            String path = request.getServletPath();
            return path.equals("/api") || path.startsWith("/api/");
        };

        MediaTypeRequestMatcher acceptsJson = new MediaTypeRequestMatcher(
                new HeaderContentNegotiationStrategy(),
                MediaType.APPLICATION_JSON);
        acceptsJson.setIgnoredMediaTypes(Set.of(MediaType.ALL));

        // RFC 9457 / Problem Details style, không tiết lộ exception.
        AuthenticationEntryPoint apiProblem = (request, response, ex) -> {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setContentType("application/problem+json");
            response.setCharacterEncoding("UTF-8");
            response.setHeader("Cache-Control", "no-store");
            response.getWriter().write(
                    "{\"type\":\"about:blank\","
                    + "\"title\":\"Unauthorized\","
                    + "\"status\":401}");
        };

        AuthenticationEntryPoint browserLogin =
                new LoginUrlAuthenticationEntryPoint("/login");

        LinkedHashMap<RequestMatcher, AuthenticationEntryPoint> mappings =
                new LinkedHashMap<>();
        // Đặt path trước Accept để /api không bị redirect HTML.
        mappings.put(apiPath, apiProblem);
        mappings.put(acceptsJson, apiProblem);

        DelegatingAuthenticationEntryPoint delegating =
                new DelegatingAuthenticationEntryPoint(mappings);
        delegating.setDefaultEntryPoint(browserLogin);

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .requestMatchers("/api/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .exceptionHandling(ex -> ex
                        .authenticationEntryPoint(delegating))
                .build();
    }

    @RestController
    static class Pages {
        @GetMapping("/")
        String index() {
            return "Public home";
        }

        @GetMapping("/web/private")
        String privatePage() {
            return "Private HTML-like page";
        }

        @GetMapping("/api/items")
        String apiItems() {
            return "Items for signed-in user";
        }

        @GetMapping("/api/admin")
        String apiAdmin() {
            return "Admins only";
        }
    }
}
```

### 7.3. Giải thích từng nhóm

- `apiPath`: mọi request ở `/api` hoặc `/api/...` chọn JSON 401 khi **chưa xác thực**, bất kể user agent/Accept header.
- `acceptsJson`: các route khác nếu client yêu cầu JSON rõ ràng thì cũng nhận JSON 401.
- `LinkedHashMap`: **rule đầu tiên khớp thắng**; hai rule có thể cùng dẫn tới `apiProblem`, nhưng thứ tự thể hiện ưu tiên URL contract trước content negotiation.
- `browserLogin`: default redirect tới `/login` khi không match rule nào; chỉ được gọi khi cần bắt đầu authentication.
- `.formLogin(...)`: kích hoạt Spring Security form login và login page mặc định; đây là demo Servlet dùng session.
- `.authorizeHttpRequests(...)`: quyền truy cập được quyết định **trước khi** chọn kiểu response. `/api/admin` yêu cầu `ROLE_ADMIN`, tài khoản Alice chỉ có `ROLE_USER`.
- `apiProblem`: dùng body tĩnh để tránh tiết lộ `AuthenticationException.getMessage()`, username, password, token hoặc stack trace.
- `.exceptionHandling(ex -> ex.authenticationEntryPoint(delegating))`: đặt explicit entry point cho `ExceptionTranslationFilter`.
- `{noop}` chỉ là **mật khẩu local demo**. Production phải dùng password encoder phù hợp, HTTPS, secret management và account policy. Không lưu password plaintext trong repo thật.

Phần “HTML-like page” trả text để demo dễ nhìn. Trong ứng dụng MVC thực tế, controller `/web/private` có thể render template Thymeleaf; cách chọn entry point vẫn giống nhau.

### 7.4. Chạy ứng dụng

Trong project có Spring Boot Gradle plugin:

```bash
./gradlew bootRun
```

Trên Windows dùng `gradlew.bat bootRun`. Ứng dụng mặc định nghe `http://localhost:8080` nếu chưa đổi `server.port`.

Dùng `curl -i` để xem status/header; request không cần username/password mới thấy sự khác biệt:

```bash
# 1. API: 401 JSON, không redirect dù client muốn HTML.
curl -i -H 'Accept: text/html' \
  http://localhost:8080/api/items

# 2. Browser: redirect tới login.
curl -i -H 'Accept: text/html' \
  http://localhost:8080/web/private

# 3. AJAX yêu cầu JSON trên route ngoài API: 401 JSON.
curl -i -H 'Accept: application/json' \
  http://localhost:8080/web/private

# 4. Route public: 200 và không gọi entry point.
curl -i http://localhost:8080/

# 5. API admin khi chưa xác thực: 401 JSON.
curl -i -H 'Accept: application/json' \
  http://localhost:8080/api/admin
```

Kết quả kỳ vọng:

| Request | Status | Header/body đặc trưng |
| --- | --- | --- |
| `GET /api/items`, `Accept: text/html`, anonymous | 401 | `Content-Type: application/problem+json`, `{"status":401}` trong body |
| `GET /web/private`, `Accept: text/html`, anonymous | 302 | `Location` trỏ tới `/login` (có thể là URL tuyệt đối/tương đối) |
| `GET /web/private`, `Accept: application/json`, anonymous | 401 | Problem JSON |
| `GET /`, anonymous | 200 | `Public home` |
| `GET /api/admin`, anonymous | 401 | Problem JSON |
| `GET /api/admin`, Alice đã xác thực bằng form | 403 | Thiếu `ROLE_ADMIN`, không phải lỗi “chưa login” |

**Không dùng `curl -L` ở bước quan sát redirect**, vì `-L` sẽ tự theo `302` tới trang `/login` rồi hiển thị response cuối, khiến bạn khó nhận ra redirect đầu tiên.

Mã demo không bật HTTP Basic; để test tài khoản Alice, dùng browser tới `/login` hoặc MockMvc ở mục 8. **Không** coi `curl -u alice:...` là cách login được cấu hình, vì chỉ có form login. Nếu cần Basic song song, hãy bật cơ chế đó và kiểm tra lại entry point behavior/realm.

## 8. Tự động kiểm thử với MockMvc

Unit/integration test cần khẳng định cả **status**, **Location/Content-Type**, **thứ tự matcher** và ranh giới giữa authentication/authorization. Dự án ở mục 7 đã thêm `spring-security-test`.

File `src/test/java/demo/entrypoint/EntryPointDemoApplicationTests.java`:

```java
package demo.entrypoint;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class EntryPointDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void apiGets401JsonEvenWithHtmlAccept() throws Exception {
        mvc.perform(get("/api/items").accept(MediaType.TEXT_HTML))
                .andExpect(status().isUnauthorized())
                .andExpect(content().contentTypeCompatibleWith(
                        "application/problem+json"))
                .andExpect(jsonPath("$.status").value(401));
    }

    @Test
    void browserGetsLoginRedirect() throws Exception {
        mvc.perform(get("/web/private").accept(MediaType.TEXT_HTML))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().exists("Location"));
    }

    @Test
    void jsonClientOutsideApiGets401() throws Exception {
        mvc.perform(get("/web/private").accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.title").value("Unauthorized"));
    }

    @Test
    void publicRouteNeverRequiresAuthentication() throws Exception {
        mvc.perform(get("/"))
                .andExpect(status().isOk())
                .andExpect(content().string("Public home"));
    }

    @Test
    void authenticatedButMissingAdminRoleGets403() throws Exception {
        mvc.perform(get("/api/admin").with(user("alice").roles("USER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedUserCanCallApi() throws Exception {
        mvc.perform(get("/api/items").with(user("alice").roles("USER")))
                .andExpect(status().isOk())
                .andExpect(content().string("Items for signed-in user"));
    }
}
```

Test command:

```bash
./gradlew test --tests demo.entrypoint.EntryPointDemoApplicationTests
```

Kỳ vọng **6 tests PASS** khi project/Java/Spring Security đúng phiên bản và code được đặt ở đúng tên/package. `with(user("alice").roles("USER"))` là **fixture Spring Security Test**, không thực hiện network form login hoặc tự kiểm tra password. Bài test 403 kiểm tra authorization branch, không chứng minh quá trình password authentication của Alice.

### 8.1. Cần thêm những test nào ở production?

- `Accept: */*` trên browser route → fallback nào? Trong ví dụ, ignored media type khiến nó về redirect.
- JSON accept có `q` weights và nhiều media types; vendor media type/`application/problem+json` có được map đúng không?
- API route có/không có trailing slash, context path, servlet prefix, forwarded headers.
- Request gửi Bearer token không hợp lệ hoặc Basic credential sai: do failure handler nào xử lý?
- User đã login nhưng thiếu role → 403, không 302/login.
- Browser đã login: `/web/private` trả nội dung page, không bị entry point can thiệp.
- AuthenticationException phát sinh trong service/method security khi chưa login; có được Security filter translation đúng không?
- Test multiple `SecurityFilterChain` beans và `@Order` nếu ứng dụng có nhiều chains.
- Body lỗi không chứa path/credential/stack trace ngoài chính sách.
- Sau request API 401, không có session lưu saved request không mong muốn theo cấu hình stateless của hệ thống.

## 9. Cách cấu hình gọn bằng defaultAuthenticationEntryPointFor

Không nhất thiết tự tạo `DelegatingAuthenticationEntryPoint`. Trong Spring Security 6.5, `ExceptionHandlingConfigurer` có method:

```java
defaultAuthenticationEntryPointFor(
    AuthenticationEntryPoint entryPoint,
    RequestMatcher preferredMatcher)
```

Với nhiều matcher/entry point, DSL có thể tự tạo delegating entry point. Đoạn dưới chỉ minh họa **thay thế** khối `.exceptionHandling(...)` ở mục 7, khi `apiPath`, `acceptsJson`, `apiProblem` và `browserLogin` đã có:

```java
.exceptionHandling(ex -> ex
    .defaultAuthenticationEntryPointFor(apiProblem, apiPath)
    .defaultAuthenticationEntryPointFor(apiProblem, acceptsJson)
    .defaultAuthenticationEntryPointFor(
            browserLogin, AnyRequestMatcher.INSTANCE))
```

`AnyRequestMatcher.INSTANCE` đặt **cuối cùng** để làm fallback trên mọi request chưa match; trong bản demo explicit delegating, `setDefaultEntryPoint(browserLogin)` giúp thể hiện điều này rõ ràng hơn.

Các điểm cần nhớ:

- `defaultAuthenticationEntryPointFor` đưa một candidate vào danh sách; nếu chỉ có **một** candidate, nó có thể trở thành default trực tiếp.
- Nếu nhiều candidate, có cơ chế delegation như `DelegatingAuthenticationEntryPoint`.
- `authenticationEntryPoint(entryPoint)` chỉ định một entry point explicit và có thể **ghi đè cách chọn từ default candidates** của exception handling; đừng vừa register nhiều defaults vừa gọi một explicit entry point khác rồi mong rule vẫn hoạt động.
- Một configurer khác như `formLogin`, `httpBasic` hoặc `oauth2ResourceServer` cũng có thể đăng ký preferred entry points. Cấu hình explicit như mục 7 thường dễ audit khi ứng dụng hỗn hợp phức tạp.
- Luôn test end-to-end vì defaults và thứ tự configurer có thể thay đổi theo version hoặc khi nâng cấp security setup.

## 10. AuthenticationEntryPoint, AccessDeniedHandler, AuthenticationFailureHandler: ba vai trò khác nhau

| Thành phần | Được dùng khi nào? | Input/đối tượng | Ví dụ |
| --- | --- | --- | --- |
| `AuthenticationEntryPoint` | Bắt đầu auth cho request chưa xác thực/không đủ authentication | `AuthenticationException` | 302 login, 401 Basic/Bearer, 401 JSON |
| `AccessDeniedHandler` | Đã xác thực nhưng thiếu authorization cho resource | `AccessDeniedException` | 403/Problem JSON, trang 403 |
| `AuthenticationFailureHandler` | Một filter xác thực cụ thể xử lý credentials sai, ví dụ form submit | Failure từ authentication filter | Redirect `/login?error` hoặc trả 401 login API |
| `AuthenticationSuccessHandler` | Authentication filter xác thực thành công | `Authentication` sau kiểm tra | Redirect saved request, trả JSON hoặc setup session theo flow |

Một HTTP request **không nhất thiết** đi qua `AuthenticationEntryPoint` khi authentication thất bại trong filter login:

```text
POST /login
   -> UsernamePasswordAuthenticationFilter
   -> AuthenticationManager rejects wrong password
   -> AuthenticationFailureHandler (typically login?error)
   -> NOT necessarily DelegatingAuthenticationEntryPoint
```

Tương tự với Bearer token sai:

```text
Authorization: Bearer invalid
  -> BearerTokenAuthenticationFilter
  -> AuthenticationManager rejects token
  -> configured AuthenticationFailureHandler / Bearer response
  -> NOT necessarily ExceptionTranslationFilter branch
```

Vì vậy, nếu product yêu cầu **đồng nhất định dạng lỗi cho mọi authentication mechanism**, cấu hình **cả failure handler của mechanism**, không chỉ `ExceptionTranslationFilter`.

### 10.1. Vì sao 403 không nên bị đổi thành 401 cho người đã login?

Một người dùng đã được xác thực bằng account `ROLE_USER` nhưng gọi `/api/admin`: authentication đã thành công, chỉ thiếu quyền. Trả 401 có thể khiến UI logout hoặc lặp login vô hạn. Trả **403** cho phép client phân biệt: cần chọn tài khoản/role khác hoặc liên hệ admin, không phải cung cấp lại password.

### 10.2. Khi anonymous gặp AccessDeniedException

Một authorization rule `hasRole("ADMIN")` sẽ từ chối cả anonymous. `ExceptionTranslationFilter` phát hiện người dùng chưa đăng nhập đủ và gọi authentication entry point; vì vậy **anonymous trên /api/admin thường 401**, còn Alice `ROLE_USER` sẽ 403. Đây là hành vi đúng, không mâu thuẫn.

## 11. Chọn JSON error format mà không làm rò rỉ thông tin

Khi API trả 401, response có thể dùng [RFC 9457 Problem Details](https://www.rfc-editor.org/rfc/rfc9457):

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/problem+json
Cache-Control: no-store

{"type":"about:blank","title":"Unauthorized","status":401}
```

Đây là một cấu trúc minh họa đủ tối thiểu. Ứng dụng thực có thể thêm `instance` hoặc correlation ID **không chứa credential**. Không trả raw exception stack trace, password, Bearer token, session ID, username không được xác minh hoặc lý do nội bộ như “user john@example.org is disabled”.

### 11.1. Header cần giữ đúng theo cơ chế

- OAuth Bearer: nếu resource server chặn request không có/không hợp lệ token, trả `WWW-Authenticate: Bearer` và các error parameters khi phù hợp RFC 6750.
- HTTP Basic: cần `WWW-Authenticate: Basic realm="..."` để client hiểu challenge.
- Cookie/session browser: 302 tới login thường hợp lý cho navigation; JSON 401 cho XHR/fetch có thể hợp lý hơn.
- CORS: preflight `OPTIONS` phải được CORS layer xử lý đúng khi được phép; đừng để browser xem preflight lỗi rồi nghĩ lỗi credentials.
- No-store: JSON lỗi nhạy cảm nên đặt cache policy phù hợp, nhất là khi có thông tin xác thực hoặc định danh.

`HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)` chỉ gửi status; muốn body JSON hoặc headers đặc thù, cần wrapper/custom entry point, hoặc sử dụng implementation có sẵn của giao thức như Bearer.

### 11.2. Status 302 có thể bị fetch theo tự động

Một SPA gọi `fetch("/web/private")` có thể theo redirect 302 trong request nền và nhận HTML login page (đôi lúc status cuối 200). JavaScript mong JSON lại parse lỗi. Vì vậy route/API contract nên ưu tiên 401 và để frontend điều hướng top-level đến login theo ý muốn, thay vì tự redirect mọi request không có session.

## 12. Với Bearer Resource Server, dùng đúng entry point của giao thức

Nếu API thật sự là OAuth2 Resource Server:

```java
http.oauth2ResourceServer(oauth2 ->
        oauth2.jwt(Customizer.withDefaults()));
```

Cấu hình này cần `JwtDecoder`/issuer/JWKS đầy đủ; snippet chỉ là DSL minh họa, **không phải file runnable**. Nếu sử dụng introspection/opaque token, cấu hình `oauth2.opaqueToken(...)` tương ứng.

Đối với Bearer protected endpoint, có `BearerTokenAuthenticationEntryPoint`:

```java
AuthenticationEntryPoint bearer =
        new BearerTokenAuthenticationEntryPoint();
```

Entry point này biết chuẩn Bearer challenge thay vì chỉ gửi JSON 401 không header. Ví dụ nếu đồng thời có nhóm browser, có thể đặt path `/api/**` → `bearer`, default → `LoginUrlAuthenticationEntryPoint`; body JSON tùy chỉnh phải duy trì challenge semantics.

**Lưu ý ranh giới cấu hình:** `BearerTokenAuthenticationFilter` có cơ chế failure handler riêng cho Bearer token **đã được đưa vào request nhưng sai**. Để bảo đảm mọi Bearer lỗi trả đúng contract, kiểm tra cả resource server configuration, không chỉ mapping của `ExceptionTranslationFilter`.

### 12.1. Multiple credentials trên một request

Khi client gửi cả session cookie và `Authorization: Bearer`, phải quyết định rõ thứ tự và phạm vi credential theo security chain. Không cho phép một token không hợp lệ “rơi về” session browser một cách vô tình nếu API đòi Bearer bắt buộc. Dùng separate filter chains hoặc explicit request rules khi độ an toàn yêu cầu tách biệt.

### 12.2. Basic Authentication

`BasicAuthenticationEntryPoint` có realm/challenge semantics và có thể khiến browser hiện hộp thoại username/password. Nếu frontend là JavaScript ứng dụng, `HttpStatusEntryPoint`/JSON có thể cho UX hợp lý hơn — **nhưng** đó không phải tương đương giao thức HTTP Basic. Định nghĩa client contract và test `WWW-Authenticate` trước khi thay.

## 13. Nhiều SecurityFilterChain hay một DelegatingAuthenticationEntryPoint?

Có hai kiến trúc chính.

### 13.1. Một chain, nhiều loại phản hồi

Dùng một `SecurityFilterChain` và một delegating entry point như mục 7 nếu:

- Các nhóm chia sẻ session/authentication logic cơ bản.
- Chỉ khác cách **trả lời khi chưa xác thực**.
- Authentication/authorization rules có thể mô tả an toàn trong cùng chain.
- Không cần thay đổi khác biệt lớn về CSRF, request cache, session creation, CORS, Basic/Bearer filter.

### 13.2. Nhiều chains khi security model thực sự khác

Ví dụ /api dùng Bearer JWT stateless, còn /web dùng form login session. Khi đó **nhiều `SecurityFilterChain` với `securityMatcher(...)` và `@Order`** thường rõ hơn:

```java
// Trích đoạn Spring Security Servlet; cần JwtDecoder/issuer config.
// @Order(1) bảo đảm chain API được xét trước chain catch-all.
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(a -> a
                    .anyRequest().authenticated())
            .sessionManagement(s -> s
                    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .oauth2ResourceServer(o -> o
                    .jwt(Customizer.withDefaults()))
            .build();
}

@Bean
@Order(2)
SecurityFilterChain browserChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(a -> a
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
}
```

Đoạn trên là **minh họa cấu hình**, thiếu import và JwtDecoder/issuer config nên không phải project chạy độc lập; API chain còn cần CORS/CSRF/request cache theo requirements. Nó minh họa **scope của filter chain**, không phải trực tiếp sử dụng delegating entry point.

**Khác biệt quan trọng:**

| Cơ chế | Câu hỏi | Thời điểm |
| --- | --- | --- |
| `SecurityFilterChain.securityMatcher(...)` | “Filter chain nào áp dụng cho request?” | Trước khi thực thi filters của chain được chọn |
| `RequestMatcher` trong `DelegatingAuthenticationEntryPoint` | “Khi cần authentication entry point, trả phản hồi nào?” | **Sau** khi có lỗi authentication/chưa đủ authentication |
| `authorizeHttpRequests.requestMatchers(...)` | “Path nào đòi quyền gì?” | Tại bước authorization |
| `AuthenticationManagerResolver` | “Dùng authentication manager/provider nào?” | Khi xử lý credentials theo cấu hình |

Đừng dùng delegating entry point để “giả lập” isolation của Bearer và cookie-based session. Nó **không loại bỏ** các filter/session/authentication mechanisms của chain hiện hành.

## 14. RequestMatcher order, overlap và fallback: các bug thường gặp

### 14.1. Matcher rộng đặt trước matcher hẹp

```java
// SAI: sẽ match mọi request, các rule sau không được xét.
mappings.put(AnyRequestMatcher.INSTANCE, browserLogin);
mappings.put(apiPath, apiProblem);
```

Ở `DelegatingAuthenticationEntryPoint` constructor map, rule được duyệt theo thứ tự; generic matcher đi đầu có thể khiến API redirect về HTML login. Dùng matcher chuyên biệt trước, fallback bằng `setDefaultEntryPoint(...)` hoặc cuối danh sách.

### 14.2. Phân loại chỉ bằng Accept

```text
GET /api/orders
Accept: text/html
```

Nếu bạn có rule `acceptsJson -> JSON 401` và fallback login redirect, client trên có thể nhận 302 dù là API. Chọn path-first để giữ hợp đồng: **API vẫn 401**.

### 14.3. Bỏ quên đường dẫn có slash/context path

`/api`, `/api/`, `/api/items`, `/context/api/items` có quan hệ khác nhau tùy servlet path/context root. Hãy test route dưới `server.servlet.context-path`, dispatcher mapping, reverse proxy prefixes và URL normalization. Không lấy request URI không normalize rồi kiểm tra `startsWith("/api")` (vì sẽ match cả `/apiary`).

### 14.4. Fallback thiếu hoặc sai

Không match rule nào → default entry point. Nếu fallback là 401 JSON cho toàn bộ trang web, browser navigation cũng mất redirect. Nếu fallback là 302 login cho mọi request, XHR không match nhận HTML. Chọn dựa vào **request inventory** và test default path, không để hành vi vô tình phụ thuộc một matcher đầu tiên.

### 14.5. Vòng lặp redirect tới login

Nếu `/login` cũng bị yêu cầu authenticated và không có form-login page filter đáp ứng, request tới login có thể bị redirect về chính nó. Đảm bảo login route được phép truy cập và đúng path. Với custom login page, thường cần explicit `permitAll()`/form login configuration phù hợp.

## 15. RequestCache và session side effects

Một request API anonymous:

```http
GET /api/items
Authorization: (absent)
Accept: application/json
```

Bạn mong 401. Nhưng do `ExceptionTranslationFilter` có thể lưu request trước khi gọi entry point, API có thể vô tình tạo session/cookie hoặc thay saved request dùng cho browser login. Khi yêu cầu API stateless, hãy cấu hình **request cache** và session policy phù hợp cho API:

```java
// Trích đoạn minh họa cho chain API stateless, không phải toàn bộ app:
http
    .requestCache(cache -> cache
            .requestCache(new NullRequestCache()))
    .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
```

Ở một chain hỗn hợp, áp `NullRequestCache` cho **toàn bộ chain** có thể làm hỏng tính năng quay lại trang HTML ban đầu sau login. Khi đó ưu tiên separate chains hoặc `HttpSessionRequestCache` với matcher lưu chỉ browser navigations. Không chỉnh request cache chỉ để “đạt test 401” mà quên UX browser.

**Cần test thật:** không có session mới không mong muốn sau loạt API 401, không có saved request nhạy cảm, và browser login success vẫn trở về đúng trang theo policy. Một redirect được chọn đúng không chứng minh request caching đã đúng.

## 16. JSON và nội dung lỗi: bảo mật, tính nhất quán, quan sát

### 16.1. Không rò rỉ lý do authentication nội bộ

Trong custom entry point:

```java
// KHÔNG NÊN: có thể đưa nội dung exception ra Internet.
response.getWriter().write(
        "{\"error\":\"" + authException.getMessage() + "\"}");
```

Lý do: message có thể chứa thông tin nội bộ, tài khoản, provider, token/claims hoặc ký tự cần escaping JSON. Việc nối trực tiếp user input vào JSON dễ tạo body sai hoặc bị injection. Dùng một body tĩnh/generic, còn details audit ở log có kiểm soát. Với production, framework `ProblemDetail`/JSON serializer có thể giúp chuẩn hóa nếu được tích hợp đúng tại filter level.

### 16.2. CORS, cookie, CSP và caching

- Browser preflight `OPTIONS` không mang cookie/credentials như request thực; nếu CORS không xử lý trước, preflight có thể bị 401/302 làm hỏng API. Cấu hình `CorsFilter`/`http.cors(...)` với allowed origins/headers/methods cụ thể.
- Một frontend cross-origin với session cookie cần `SameSite`, `Secure` và CORS credentials policy phù hợp; không đặt `Access-Control-Allow-Origin: *` cùng credentialed requests.
- API 401/403 có thể không được JS đọc nếu CORS headers thiếu, ngay cả khi server thật sự trả status đúng.
- Đừng đặt `Cache-Control: public` cho body lỗi có identity/authorization metadata; cân nhắc `no-store`.
- Với HTML login redirect, chỉ cho phép redirect target đã cấu hình/kiểm soát; tránh dùng `returnUrl` từ query để tạo **open redirect**.
- `Accept` là request header dễ giả; thay response type theo Accept được phép nhưng không được thay security policy.

### 16.3. Observability

Log/metrics tối thiểu: request correlation ID, nhóm matcher (api/json/browser), type của authentication failure đã chuẩn hóa, status 401/302/403, latency. Không log toàn bộ `Authorization`, cookie, session ID hoặc raw exception chứa secret. Nếu cần biết matcher nào thắng, có thể bật debug log Spring Security trong môi trường test, nhưng **tắt log nhạy cảm** ở production.

## 17. WebFlux: lớp tương ứng không mang tên giống Servlet

Trong WebFlux/reactive security, **không dùng** Servlet `DelegatingAuthenticationEntryPoint`, `HttpSecurity` hoặc `jakarta.servlet.http.HttpServletResponse`.

Các kiểu tương ứng:

| Servlet | WebFlux |
| --- | --- |
| `AuthenticationEntryPoint` | `ServerAuthenticationEntryPoint` |
| `DelegatingAuthenticationEntryPoint` | `DelegatingServerAuthenticationEntryPoint` |
| `RequestMatcher` | `ServerWebExchangeMatcher` |
| `ExceptionTranslationFilter` | `ExceptionTranslationWebFilter` |
| `HttpSecurity.exceptionHandling(...)` | `ServerHttpSecurity.exceptionHandling(...)` |
| `LoginUrlAuthenticationEntryPoint` | `RedirectServerAuthenticationEntryPoint` |
| `HttpStatusEntryPoint` | `HttpStatusServerEntryPoint` |

Với WebFlux, `commence(ServerWebExchange, AuthenticationException)` trả về **`Mono<Void>`** và phải không block event loop. Đoạn cấu hình **minh họa trong @Configuration class**, không phải project runnable độc lập:

```java
ServerAuthenticationEntryPoint api401 =
        new HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED);

ServerAuthenticationEntryPoint browserLogin =
        new RedirectServerAuthenticationEntryPoint("/login");

var api = new DelegatingServerAuthenticationEntryPoint.DelegateEntry(
        ServerWebExchangeMatchers.pathMatchers("/api/**"), api401);

DelegatingServerAuthenticationEntryPoint delegating =
        new DelegatingServerAuthenticationEntryPoint(api);

delegating.setDefaultEntryPoint(browserLogin);

return http
        .authorizeExchange(exchanges -> exchanges
                .anyExchange().authenticated())
        .formLogin(Customizer.withDefaults())
        .exceptionHandling(ex -> ex
                .authenticationEntryPoint(delegating))
        .build();
```

Đặt trong method trả `SecurityWebFilterChain` với `ServerHttpSecurity http` đã inject và import các lớp tương ứng Spring Security WebFlux 6.5. WebFlux có mô hình khác về session/request cache/CSRF/failure handlers; không chuyển code Servlet sang WebFlux bằng cách đổi `HttpSecurity` thành `ServerHttpSecurity` rồi giữ nguyên `RequestMatcher`.

Nếu WebFlux API dùng Bearer, `BearerTokenServerAuthenticationEntryPoint` hỗ trợ challenge semantics tương ứng; muốn body Problem JSON cần một `ServerAuthenticationEntryPoint` reactive ghi response không-blocking và giữ headers hợp lệ.

## 18. Test matrix theo nhóm request và trạng thái bảo mật

| # | Nhóm | Auth state | Kỳ vọng |
| --- | --- | --- | --- |
| 1 | `/api/items`, `Accept: application/json` | Anonymous | 401 JSON |
| 2 | `/api/items`, `Accept: text/html` | Anonymous | 401 JSON, vì path API ưu tiên |
| 3 | `/api/items`, không có Accept | Anonymous | 401 JSON |
| 4 | `/api/admin` | Anonymous | 401 JSON, không phải 403 |
| 5 | `/api/admin` | Alice có ROLE_USER | 403 |
| 6 | `/api/admin` | Admin có ROLE_ADMIN | 200 theo controller nếu xác thực hợp lệ |
| 7 | `/web/private`, `Accept: text/html` | Anonymous | 302/Location login |
| 8 | `/web/private`, `Accept: application/json` | Anonymous | 401 JSON |
| 9 | `/web/private`, `Accept: */*` | Anonymous | Fallback redirect theo rule của ví dụ |
| 10 | `/web/private` | Authenticated | 200 |
| 11 | `/login` | Anonymous | Login page/flow hoạt động, không redirect loop |
| 12 | `/` public | Anonymous | 200, không gọi entry point |
| 13 | `/apiary` | Anonymous | Không được nhầm với `/api/**` |
| 14 | Application context path `/app` | Anonymous | Match route theo servlet mapping thực, không sai prefix |
| 15 | API gửi Bearer invalid | Invalid credential | RFC 6750 challenge/401 theo resource server config |
| 16 | Basic protected endpoint | Không có Basic | 401/`WWW-Authenticate: Basic` nếu chọn Basic |
| 17 | Login POST sai password | Auth failure | Failure handler, không giả định delegating xử lý |
| 18 | Cross-origin `OPTIONS` | Không credentials | CORS preflight theo policy, không bị redirect HTML không mong muốn |
| 19 | API 401 lặp nhiều lần | Anonymous | Không tạo/lưu session/saved request ngoài chính sách |
| 20 | Browser login rồi quay lại page | Authenticated | Saved request/redirect hợp lệ nếu tính năng bật |
| 21 | Overlapping matchers | Anonymous | Rule đầu tiên thắng, test order cố định |
| 22 | Không matcher nào đúng | Anonymous | Explicit fallback chạy |
| 23 | Failure response | Anonymous | Không log/return token, password, stack trace |
| 24 | Multi-chain mapping | Anonymous | API path chạy đúng chain, không rơi qua browser chain |

**Kiểm thử cả bằng browser, MockMvc/WebTestClient và HTTP client**: browser có thể tự follow redirect; MockMvc cho thấy status ban đầu; curl có thể bị thay đổi behavior khi dùng `-L`. Với 403, dùng authenticated test principal đã có role thiếu để chứng minh nhánh authorization.

## 19. Troubleshooting: triệu chứng → hướng kiểm tra

### API nhận HTML login page thay vì 401

Thử `curl -i` không theo redirect. Xem response ban đầu là `302 Location: /login` hay status 200 của login page do client đã follow. Kiểm tra `apiPath` có match đúng servlet path/context path, matcher order có `AnyRequestMatcher` quá sớm, chain nào đang xử lý, và explicit `authenticationEntryPoint` có bị thay bởi configurer khác.

### Browser nhận 401 JSON, không được redirect login

Kiểm tra `Accept` thực tế (có thể frontend đặt `application/json` trên mọi request), path có bị match nhầm `/api/**`, và fallback entry point có đúng `LoginUrlAuthenticationEntryPoint` không. Thay đổi matcher chỉ cho presentation; không cho phép browser path bỏ auth để “tránh 401”.

### API nhận 403 dù chưa đăng nhập

Kiểm tra request có thực sự anonymous/remember-me/full authenticated theo Spring Security trust resolver, có một custom `AccessDeniedHandler` đang ép status, có nhiều chains, hoặc error handler ở tầng khác. Đừng tùy tiện đổi authorization rule thành `permitAll()`; truy vết filters và authentication state.

### Người có quyền thấp nhận login redirect thay vì 403

Nếu đã authenticated mà bị redirect, kiểm tra application có khởi động authentication mới không, user principal có bị coi anonymous/remember-me không, hoặc custom entry point gọi sai. Phân biệt request GET resource và POST login failure. Đối với role thiếu, mặc định là AccessDeniedHandler chứ không phải login redirect.

### Đã khai báo map nhưng app không khởi động

Đọc exception khởi tạo `DelegatingAuthenticationEntryPoint`: map có ít nhất một matcher? Có `defaultEntryPoint` không? Có null entry point hoặc vòng đời bean không đúng? Spring Security 6.5 class implements `InitializingBean` và đối chiếu invariants khi khởi tạo.

### Matcher thứ hai không bao giờ được gọi

Rule trước match tất cả, hoặc MediaTypeMatcher quá rộng. Dùng `LinkedHashMap`, đặt path cụ thể trước, test priority. Đừng dùng `HashMap` khi thứ tự chọn entry point phải ổn định.

### Bearer invalid trả khác với Bearer missing

Đây có thể là do `BearerTokenAuthenticationFilter` xử lý invalid credential qua failure handler, còn missing credential để authorization phát `AccessDeniedException` rồi qua exception translation. Kiểm tra **cả hai đường đi**, status/header/body và JWT/opaque validation.

### Browser báo CORS dù backend có trả JSON 401

Kiểm tra response/preflight có CORS headers cần thiết không. Với credentialed fetch, server phải cho phép origin cụ thể và credentials policy tương ứng; một JSON 401 đúng nội dung nhưng thiếu CORS headers vẫn bị browser chặn cho JavaScript đọc.

### Không thể quay lại URL đã yêu cầu trước login

Nếu cấu hình `NullRequestCache` toàn chain hoặc session policy stateless cho cả browser, request cũ không được lưu. Thiết kế chain browser và API tách biệt khi yêu cầu khác nhau; không sửa bằng cách lưu mọi API request trong session.

### Đang dùng Spring Security 7 nhưng constructor báo deprecated

Chuyển sang `DelegatingAuthenticationEntryPoint.builder()` hoặc constructor mới với `RequestMatcherEntry` theo javadoc dòng 7.x. Không tự suy diễn tên method; kiểm tra artifact chính xác ở classpath.

## 20. Bài tập Java 17 độc lập: minh họa first-match-wins

Để thấy cơ chế ưu tiên mà không cần chạy cả Spring Boot, chương trình sau mô phỏng **logic lựa chọn matcher** bằng Java thuần. Nó không tạo `AuthenticationEntryPoint` thật và không thực hiện authentication.

Lưu `EntryPointRoutingModel.java`:

```java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.function.Predicate;

public class EntryPointRoutingModel {
    record Request(String path, String accept) {}

    static String select(
            Request req,
            LinkedHashMap<Predicate<Request>, String> rules,
            String fallback) {
        for (Map.Entry<Predicate<Request>, String> entry
                : rules.entrySet()) {
            if (entry.getKey().test(req)) {
                return entry.getValue();
            }
        }
        return fallback;
    }

    public static void main(String[] args) {
        var rules = new LinkedHashMap<Predicate<Request>, String>();

        rules.put(
                r -> r.path().equals("/api")
                        || r.path().startsWith("/api/"),
                "401 JSON");

        rules.put(
                r -> "application/json".equals(r.accept()),
                "401 JSON");

        System.out.println(select(
                new Request("/api/items", "text/html"),
                rules, "302 /login"));
        System.out.println(select(
                new Request("/web/private", "text/html"),
                rules, "302 /login"));
        System.out.println(select(
                new Request("/web/private", "application/json"),
                rules, "302 /login"));
        System.out.println(select(
                new Request("/reports", "*/*"),
                rules, "302 /login"));
    }
}
```

Biên dịch và chạy:

```bash
javac EntryPointRoutingModel.java
java EntryPointRoutingModel
```

Stdout **chính xác**:

```text
401 JSON
302 /login
401 JSON
302 /login
```

Bài tập chỉ biểu diễn **thứ tự matcher**. So sánh ở đây cố ý dùng `String.equals("application/json")` cho dễ hiểu, không thay thế `MediaTypeRequestMatcher` và content negotiation thực tế. Không dùng code mô phỏng để xử lý quyền truy cập hoặc Bearer tokens.

Thử đổi thứ tự rule, cho rule “match mọi request” lên đầu rồi quan sát mọi request đều nhận kết quả của rule đầu. Sau đó khôi phục thứ tự **specific before general**.

## 21. Checklist production

1. **Inventory:** liệt kê toàn bộ nhóm yêu cầu (browser navigation, API, SPA fetch, Basic/Bearer, health, static assets, OAuth callbacks) và contract 401/302/403 của từng nhóm.
2. **Authentication vs authorization:** kiểm tra entry point chỉ xử lý request chưa xác thực; authenticated thiếu quyền dùng AccessDeniedHandler.
3. **Match strategy:** path-first với API contract; Accept là tín hiệu format, không phải security proof; matcher ổn định theo context/servlet mapping.
4. **Order:** LinkedHashMap và rule cụ thể trước; explicit default, không AnyRequestMatcher làm rule đầu.
5. **Protocol correctness:** Bearer challenge theo RFC 6750; Basic realm; form login redirect; kiểm tra failure handlers của từng authentication filter.
6. **Error body:** Problem Details/JSON chuẩn hóa, không lộ exception details, token hoặc PII; status và headers đúng.
7. **Single vs multi-chain:** nếu chỉ khác response có thể delegation; nếu khác mechanism/session/CSRF/cache nên cân nhắc separate chains.
8. **Sessions:** xác minh request cache và session creation; API stateless không giữ saved request ngoài chủ đích, browser navigation vẫn có UX hợp lý.
9. **CSRF/CORS:** giữ CSRF ở cookie-based writes, xử lý preflight và cookie/allowed-origin đúng trust boundary.
10. **Safety:** không dùng `Accept`/`User-Agent`/header tùy ý để nâng quyền, bỏ xác thực hoặc đưa client sang endpoint ít an toàn hơn.
11. **Tests:** MockMvc/WebTestClient, redirect vs JSON, 401 vs 403, overlapping matchers, default, Basic/Bearer, context path, multi-chain, CORS và failure handlers.
12. **Version:** ghi nhận baseline Spring Security; khi nâng lên 7.x, đánh giá constructor/builder deprecations và regression tests.
13. **Observability:** metrics theo request group/status; audit lỗi nhưng không log Authorization/cookies/credentials; theo dõi redirect loops và 401/403 spikes.
14. **Documentation:** frontend/mobile biết khi nhận 401 phải làm gì; không mặc định fetch follow redirect nghĩa là login đã hoàn thành.

**Kết luận:** `DelegatingAuthenticationEntryPoint` **không** quyết định “ai có quyền” mà quyết định **“khi Spring Security yêu cầu bắt đầu authentication, client này nên nhận phản hồi gì?”**. Dùng `RequestMatcher` theo thứ tự có chủ đích, trả 401 đúng protocol cho API, 302 cho browser form login và để 403 thuộc authorization branch. Đây là cách tránh API nhận HTML login page mà vẫn giữ UX đăng nhập thân thiện cho người dùng web.

## 22. Tài liệu chính thức

- [Spring Security 6.5.11 — DelegatingAuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/DelegatingAuthenticationEntryPoint.html): constructor `LinkedHashMap`, `commence` và `setDefaultEntryPoint`.
- [Spring Security 6.5.11 — ExceptionHandlingConfigurer API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/ExceptionHandlingConfigurer.html): `authenticationEntryPoint`, `defaultAuthenticationEntryPointFor` và `accessDeniedHandler`.
- [Spring Security — AuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/AuthenticationEntryPoint.html): giao diện `commence` và tác động đến HTTP response.
- [Spring Security — ExceptionTranslationFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/access/ExceptionTranslationFilter.html): AuthenticationException/AccessDeniedException, request cache.
- [Spring Security — Servlet Exception Handling](https://docs.spring.io/spring-security/reference/servlet/architecture.html): kiến trúc web filters, exception handling và authorization.
- [Spring Security — HttpStatusEntryPoint API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/HttpStatusEntryPoint.html): generic 401 status.
- [Spring Security — LoginUrlAuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/LoginUrlAuthenticationEntryPoint.html): form login redirect.
- [Spring Security — MediaTypeRequestMatcher API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/util/matcher/MediaTypeRequestMatcher.html): content negotiation và ignored media types.
- [Spring Security — BearerTokenAuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/web/BearerTokenAuthenticationEntryPoint.html): Bearer challenge.
- [Spring Security — DelegatingServerAuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/DelegatingServerAuthenticationEntryPoint.html): lựa chọn entry point trong WebFlux.
- [Spring Security — Servlet Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): sessions, saved request và logout.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): `WWW-Authenticate`, 401/403 và `insufficient_scope`.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): JSON Problem Details.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): generic errors và tránh rò rỉ thông tin.
