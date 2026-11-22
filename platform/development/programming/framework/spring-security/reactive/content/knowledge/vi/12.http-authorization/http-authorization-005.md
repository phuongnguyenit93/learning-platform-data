# Kết hợp quyền với thông tin ServerWebExchange trong Spring Security WebFlux

## Mục tiêu và bối cảnh

Bài học thuộc nhóm **Phân quyền HTTP** của **Spring Security - reactive**. Trong ứng dụng thực tế, quyết định cho phép một request thường không chỉ phụ thuộc vào việc người dùng có `ROLE_USER` hay `ROLE_ADMIN`. Cùng một người dùng có thể xem báo cáo của mình nhưng không được xem báo cáo của người khác; một số biểu diễn dữ liệu cần vai trò cao hơn; HTTP method, URL, tham số truy vấn và dữ liệu đã xác minh trong request cũng có thể ảnh hưởng đến quyền truy cập.

Spring Security WebFlux hỗ trợ kết hợp **Authentication** với **ServerWebExchange** thông qua `ReactiveAuthorizationManager<AuthorizationContext>`, thường được nối vào DSL `ServerHttpSecurity.authorizeExchange(...).access(...)`.

Sau bài học, bạn sẽ:

1. Phân biệt **authentication**, **authorization**, **request matching**, **business ownership** và dữ liệu trong HTTP exchange.
2. Truy cập `AuthorizationContext.getExchange()`, `getVariables()` và các thuộc tính request hữu ích.
3. Viết `ReactiveAuthorizationManager<AuthorizationContext>` để kết hợp role, người sở hữu tài nguyên, HTTP method, query parameters và headers.
4. Xác định thông tin nào **do client kiểm soát**, không được xem là bằng chứng nhận dạng hoặc quyền; biết khi nào phải tra cứu dữ liệu đáng tin cậy từ server/database.
5. Trả quyết định **ALLOW/DENY** đúng hợp đồng `Mono<AuthorizationDecision>`, xử lý `Mono.empty()` và lỗi bất đồng bộ mà không bypass bảo mật.
6. Tạo ví dụ chạy được với **Java 17+ và Spring Boot 3.3.13 WebFlux**, kiểm thử các ca 200/401/403 bằng `WebTestClient`.
7. Nhận ra lỗ hổng cross-tenant/IDOR, client header spoofing, query parameter pollution và lỗi khi đọc biến đường dẫn.
8. Biết nơi áp dụng HTTP authorization và khi nào cần thêm bảo vệ ở tầng service bằng **reactive method security**.

**Phạm vi:** Spring Security **reactive** dùng `SecurityWebFilterChain` và `ServerHttpSecurity`. Không tráo với Servlet `HttpSecurity.authorizeHttpRequests(...)` hoặc `RequestAuthorizationContext`: tên API và hợp đồng request khác nhau.

## 1. Từ RBAC thuần đến điều kiện dựa vào request

RBAC (role-based access control) thường được biểu đạt bằng:

```java
http.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/admin/**").hasRole("ADMIN")
        .anyExchange().authenticated());
```

Cách này đủ khi yêu cầu chỉ là “ai có role nào được vào nhóm URL nào”. Nhưng giả sử có endpoint:

```text
GET /api/reports/alice
GET /api/reports/bob
GET /api/reports/alice?view=full
```

Cùng là request HTTP GET đến nhóm `/api/reports/**`, nhưng:

- Alice được xem báo cáo của **alice** theo dạng tóm tắt.
- Alice **không** được xem báo cáo của bob dù có role đọc báo cáo.
- Auditor có thể được xem dữ liệu của người khác theo chính sách.
- Chế độ `view=full` hoặc header `X-Report-Format: raw` yêu cầu quyền AUDITOR bổ sung.
- Request với giá trị mode lạ, tham số lặp bất thường hoặc thiếu thông tin cần thiết phải bị từ chối có kiểm soát.

Chúng ta cần quyết định đồng thời theo:

```text
ALLOW =
  authenticated principal
  AND matcher đúng nhóm request
  AND dữ liệu HTTP hợp lệ
  AND (
        (đúng người sở hữu AND có ROLE_REPORT_READER)
        OR có ROLE_AUDITOR
      )
  AND (
        chỉ yêu cầu biểu diễn thông thường
        OR có ROLE_AUDITOR
      )
```

Đây là ví dụ **kết hợp RBAC với điều kiện ngữ cảnh (contextual/ABAC)**. Quan trọng: role và principal phải đến từ Authentication đã được framework xác thực; path/query/header chỉ mô tả request và **có thể bị client thay đổi**.

## 2. Đường đi của quyết định HTTP

```text
HTTP client
   |
   v
Spring WebFlux WebFilter pipeline
   |
   v
Spring Security WebFilterChainProxy
   |
   +--> chọn SecurityWebFilterChain đầu tiên khớp
             |
             +--> các Authentication WebFilter
             |       xác thực Basic/Bearer/Form theo cấu hình
             |
             +--> AuthorizationWebFilter
                       |
                       +--> so khớp HTTP method/path
                       +--> tạo AuthorizationContext
                       |      + ServerWebExchange
                       |      + URI variables do matcher trích xuất
                       |
                       +--> ReactiveAuthorizationManager.check(
                       |       Mono<Authentication>,
                       |       AuthorizationContext)
                       |       |
                       |       +--> Mono<AuthorizationDecision>(true/false)
                       |
                       +--> ALLOW: chain tiếp tục -> handler
                       +--> DENY: chặn handler, xử lý exception
                       +--> ERROR: truyền lỗi theo error pipeline
```

Ở tầng DSL:

```java
http.authorizeExchange(exchanges -> exchanges
    .pathMatchers(HttpMethod.GET, "/api/reports/{owner}")
        .access(customReportManager)
    .anyExchange().denyAll());
```

- `pathMatchers(...)` chọn **quy tắc authorization** được áp dụng cho request trong chain.
- `.access(customReportManager)` yêu cầu manager quyết định dựa trên **Authentication + AuthorizationContext**.
- `.anyExchange().denyAll()` bảo đảm những URL chưa định nghĩa trong chain không tự động mở.
- `securityMatcher(...)` của `ServerHttpSecurity`, nếu có, quyết định **chain nào** được chọn ở tầng trước. Đừng hiểu `pathMatchers` hoặc `access` có thể thay thế việc chọn security chain.

Nếu có nhiều `SecurityWebFilterChain`, proxy chỉ áp dụng chain đầu tiên khớp request; custom manager trong chain khác sẽ **không** được gọi.

## 3. Những API quan trọng

### 3.1. AuthorizationContext

`AuthorizationContext` là lớp trong package `org.springframework.security.web.server.authorization`. Nó cho phép đọc:

```java
ServerWebExchange exchange = context.getExchange();
Map<String, Object> variables = context.getVariables();
```

Hai dữ liệu này phục vụ những nhu cầu khác nhau:

| API | Thông tin | Cách sử dụng |
| --- | --- | --- |
| `context.getExchange()` | HTTP request, response, attributes, principal và session APIs | Lấy method/path/headers/query; dữ liệu ứng dụng đã đặt vào exchange nếu tin cậy |
| `context.getVariables()` | Biến URI được **authorization matcher** trích xuất | Đọc `owner` từ matcher `/api/reports/{owner}` |
| `exchange.getRequest().getMethod()` | HTTP method | Kiểm tra GET/POST/PUT/DELETE nếu chính sách cần |
| `exchange.getRequest().getPath()` | Request path của WebFlux | Quan sát path, không thay thế chuẩn matcher |
| `exchange.getRequest().getQueryParams()` | MultiValueMap query parameters | Kiểm tra mode/filter do client chọn; từ chối giá trị lặp không mong muốn |
| `exchange.getRequest().getHeaders()` | HTTP headers | Đọc representation/client intent; không dùng custom header như role đã xác minh |
| `exchange.getRequest().getCookies()` | Cookies do client gửi | Thông tin đầu vào, không phải bằng chứng quyền nếu chưa có cơ chế xác thực kiểm chứng |
| `exchange.getRequest().getRemoteAddress()` | Địa chỉ kết nối phía server nhìn thấy | Không nhất thiết là IP cuối cùng của người dùng sau proxy |
| `exchange.getAttributes()` | Attributes do WebFilter/handler lưu trên exchange | Chỉ tin dữ liệu được thành phần **đáng tin cậy** thiết lập và quản lý |
| `Authentication.getAuthorities()` | Quyền đã được hệ thống xác thực/ánh xạ | Nguồn quyền tin cậy của policy |

**Cảnh báo:** `context.getVariables()` đến từ **matcher trong cấu hình authorization**, không phải lúc nào cũng giống attributes của WebFlux controller. Authorization chạy **trước** khi route handler thực thi, nên không nên dựa vào `HandlerMapping.URI_TEMPLATE_VARIABLES_ATTRIBUTE` như nguồn mặc định của biến URL tại thời điểm này. Dùng biến được `pathMatchers` cung cấp khi cấu hình rule tương ứng.

### 3.2. ReactiveAuthorizationManager và AuthorizationDecision

Với các phiên bản Spring Security 6.x được Boot 3.3 quản lý, kiểu thường dùng là:

```java
ReactiveAuthorizationManager<AuthorizationContext> manager =
        (authenticationMono, context) -> {
            // Đọc request từ context.getExchange()
            // Đọc role/principal từ authenticationMono
            return authenticationMono
                    .map(authentication ->
                            new AuthorizationDecision(
                                    /* điều kiện cho phép */ true))
                    .defaultIfEmpty(new AuthorizationDecision(false));
        };
```

Trong Java, hai tham số ở lambda có kiểu:

- `authenticationMono`: `Mono<Authentication>`, vì người dùng có thể chưa xác thực và thông tin security context được cung cấp theo mô hình reactive.
- `context`: `AuthorizationContext` chứa exchange và URI variables.

`AuthorizationDecision(true)` biểu thị cho phép; `AuthorizationDecision(false)` biểu thị không cho phép. Thực tế còn phân biệt lỗi khi đánh giá policy và quyết định từ chối: **không dùng lỗi hạ tầng làm tín hiệu ALLOW**.

Ở một số phiên bản API mới có phương thức `authorize(...)` trả `AuthorizationResult`; bản WebFlux 6.x sử dụng `check(...)`/`AuthorizationDecision` trong DSL là hợp đồng phù hợp cho ví dụ Java 17+ bên dưới. Khi nâng cấp major version, kiểm tra lại Javadoc và migration guide.

### 3.3. Khi thiếu Authentication

Cẩn trọng với code:

```java
return authenticationMono.map(authentication ->
        new AuthorizationDecision(authentication.getName().equals(owner)));
```

Nếu `authenticationMono` rỗng, publisher có thể hoàn tất **không phát quyết định**; Spring Security có những đường xử lý abstain/empty tùy cơ chế. Trong business policy nơi thiếu identity phải bị từ chối, nên viết:

```java
return authenticationMono
        .map(authentication ->
                new AuthorizationDecision(
                        authentication.isAuthenticated()
                        && !(authentication instanceof AnonymousAuthenticationToken)
                        && authentication.getName().equals(owner)))
        .defaultIfEmpty(new AuthorizationDecision(false));
```

Code trên là **mảnh minh họa**; cần import `AnonymousAuthenticationToken` và cung cấp `owner`. Lưu ý anonymous token có thể có `isAuthenticated() == true` theo kiểu object, nên chỉ kiểm tra flag này là không đủ để coi token là principal của người dùng thật. Khi đã có authority policy rõ ràng, các authority đáng tin cậy cũng giúp ngăn anonymous bị coi là người dùng hợp lệ.

**Không sử dụng `block()` để lấy Authentication** từ `Mono` trong WebFlux. Hãy kết hợp qua `map`/`flatMap` hoặc manager sẵn có.

## 4. Dữ liệu nào được phép ảnh hưởng đến quyền?

| Dữ liệu | Ai có thể điều khiển? | Vai trò an toàn trong policy |
| --- | --- | --- |
| `Authentication.getName()` | Identity đã được cơ chế auth xác minh | Có thể dùng làm actor ID trong demo; production ưu tiên stable user ID |
| `Authentication.getAuthorities()` | Mã hóa/ánh xạ từ identity provider hoặc user store | Role/scope đã xác minh cho authorization |
| `/reports/{owner}` | Client chọn URL | **Đối tượng cần truy cập**, không tự chứng minh quyền sở hữu |
| Query `view=full` | Client tự gửi | Yêu cầu biểu diễn nhạy cảm; đòi quyền mạnh hơn |
| Header `X-Report-Format: raw` | Client tự gửi | Yêu cầu mode nhạy cảm; đòi quyền mạnh hơn |
| Header `X-Tenant-ID` | Client tự gửi, có thể giả | Chỉ là yêu cầu chọn tenant; **không** tin làm bằng chứng tenant membership |
| Cookie tự đặt | Client gửi | Chỉ có giá trị xác thực sau khi framework kiểm chứng session/token |
| `X-Forwarded-For` | Có thể giả nếu proxy không lọc/ghi đè | Không dùng như IP tin cậy nếu chưa xác minh chain proxy và forwarded-header policy |
| Tenant/ownership đọc từ DB | Server xác minh theo principal & resource | Nguồn mạnh hơn để quyết định quyền theo tài nguyên |
| Attributes từ trusted security filter | Server đặt trong filter đã kiểm chứng, sau khi xác minh dữ liệu | Có thể dùng nếu có hợp đồng rõ ràng, không dễ bị ghi đè |

**Ví dụ không an toàn:**

```java
// SAI: Client tự gửi X-User-Role: ADMIN là được vào admin.
String requestedRole =
        context.getExchange().getRequest().getHeaders()
                .getFirst("X-User-Role");

boolean allow = "ADMIN".equals(requestedRole);
```

Kẻ tấn công chỉ cần gửi header. **Sửa:** kiểm tra `Authentication.getAuthorities()` đã được cơ chế xác thực phát và, nếu cần, kiểm tra thêm tổ chức/tài nguyên từ nguồn phía server. Header có thể dùng để *yêu cầu chế độ* khiến policy nghiêm ngặt hơn, không nên tự cấp thêm quyền.

### Phân biệt authorization và validation

- Validation xác nhận format/path/query hợp lệ, số lượng tham số, độ dài dữ liệu.
- Authentication xác nhận danh tính/credentials.
- Authorization quyết định principal ấy có quyền truy cập tài nguyên/chế độ hay không.
- Business logic xác minh trạng thái thực của tài nguyên, tenant membership, ownership, workflow status và các invariant sâu hơn.

Có thể từ chối giá trị request không hợp lệ ngay trong manager để **fail-closed**, nhưng ở API production thường cũng có tầng validation riêng trả 400 thay vì trộn mọi lỗi input thành 403. Dù phản hồi là 400 hay 403, **không được chạy handler với quyền cao hơn** khi dữ liệu input chưa được kiểm tra.

## 5. Thiết kế policy mẫu

Ứng dụng demo cung cấp endpoint:

```text
GET /api/reports/{owner}?view=summary
GET /api/reports/{owner}?view=full
X-Report-Format: json | raw  (header tùy chọn)
```

Quy tắc:

1. Request phải là **GET**; các method khác không có rule cho phép và bị deny ở fallback.
2. `owner` phải là tên hợp lệ do matcher trích xuất, không rỗng; không dùng path để tự xác nhận quyền.
3. `view` không có thì mặc định `summary`; nếu có phải là **đúng một giá trị**, chỉ `summary` hoặc `full`.
4. `X-Report-Format` không có thì mặc định `json`; nếu có phải là **đúng một giá trị**, chỉ `json` hoặc `raw`.
5. Request đã xác thực được xem summary/json nếu **owner trùng Authentication name và có ROLE_REPORT_READER**, hoặc nếu có `ROLE_AUDITOR`.
6. Nếu `view=full` hoặc `X-Report-Format: raw` thì **bắt buộc có ROLE_AUDITOR**, ngay cả khi chủ sở hữu đang đọc báo cáo của mình.
7. Thiếu Authentication, query/header trùng lặp, mode không nhận diện được hoặc path owner không hợp lệ: **DENY**.
8. Dữ liệu response trong demo chỉ là placeholder; policy minh họa quyền đọc. Trong production, controller/service phải truy vấn resource bằng identity/tài nguyên đúng cách, tránh IDOR.

### Ma trận quyết định

| Caller | Request | Kết quả |
| --- | --- | --- |
| Alice, `ROLE_REPORT_READER` | `GET /api/reports/alice` | ALLOW |
| Alice | `GET /api/reports/bob` | DENY (khác owner) |
| Bob, `ROLE_REPORT_READER` | `GET /api/reports/bob?view=summary` | ALLOW |
| Alice | `GET /api/reports/alice?view=full` | DENY (thiếu AUDITOR) |
| Auditor, `ROLE_AUDITOR` | `GET /api/reports/bob?view=full` | ALLOW |
| Auditor | `GET /api/reports/bob` + `X-Report-Format: raw` | ALLOW |
| Alice | `GET /api/reports/alice` + `X-Report-Format: raw` | DENY |
| Alice | `GET /api/reports/alice?view=garbage` | DENY |
| Alice | `GET /api/reports/alice?view=summary&view=full` | DENY (tham số lặp) |
| Chưa đăng nhập | `GET /api/reports/alice` | DENY; với HTTP Basic có thể trả 401 |
| Alice | `POST /api/reports/alice` | Không có rule cho phép; CSRF có thể chặn trước |

**Điểm khác biệt quan trọng:** Header hay query chỉ *yêu cầu chế độ dữ liệu*. Client không thể gửi một giá trị để được thêm quyền. Khi client yêu cầu biểu diễn nhạy cảm hơn, policy mới yêu cầu quyền AUDITOR.

## 6. Ví dụ đầy đủ chạy được với Java 17+ và Spring Boot WebFlux

Ứng dụng sử dụng Spring Boot **3.3.13**, Java 17, WebFlux, Spring Security và HTTP Basic. HTTP Basic giúp thử từng request bằng `curl` mà không cần dựng OAuth Authorization Server. Dữ liệu người dùng đặt trong bộ nhớ và mật khẩu `{noop}` **chỉ dùng để học**, không phù hợp production.

### 6.1. Cấu trúc dự án

```text
exchange-authorization-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/example/ExchangeAuthorizationApplication.java
    test/
      java/example/ExchangeAuthorizationApplicationTests.java
```

Tạo `settings.gradle`:

```groovy
rootProject.name = 'exchange-authorization-demo'
```

Tạo `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
```

Boot BOM quản lý Spring Security, WebFlux, Reactor tương thích. Không bổ sung `spring-boot-starter-web` (Servlet MVC) vào demo và không sử dụng `HttpSecurity`/`SecurityFilterChain` của Servlet.

### 6.2. Main class, HTTP endpoint và custom authorization

Tạo `src/main/java/example/ExchangeAuthorizationApplication.java`:

```java
package example;

import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authorization.AuthorizationContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
@EnableWebFluxSecurity
@RestController
public class ExchangeAuthorizationApplication {

    public static void main(String[] args) {
        SpringApplication.run(ExchangeAuthorizationApplication.class, args);
    }

    @GetMapping("/health")
    public String health() {
        return "OK";
    }

    @GetMapping("/api/reports/{owner}")
    public Mono<Map<String, String>> getReport(
            @PathVariable String owner,
            @RequestParam(name = "view", defaultValue = "summary")
                    String view,
            @RequestHeader(name = "X-Report-Format",
                    defaultValue = "json") String format) {

        // Chỉ trả dữ liệu mô phỏng. Ứng dụng thật phải load
        // đúng resource và kiểm tra quyền ở service.
        return Mono.just(Map.of(
                "owner", owner,
                "view", view,
                "format", format,
                "data", "demo-only"));
    }

    @Bean
    SecurityWebFilterChain securityChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/health").permitAll()
                        .pathMatchers(
                                HttpMethod.GET, "/api/reports/{owner}")
                        .access(reportAccess())
                        .anyExchange().denyAll())
                .httpBasic(withDefaults())
                .formLogin(form -> form.disable())
                // CSRF giữ mặc định: ví dụ chỉ cấp quyền GET.
                .build();
    }

    private static ReactiveAuthorizationManager<AuthorizationContext>
            reportAccess() {

        return (authenticationMono, context) -> {
            ServerHttpRequest request =
                    context.getExchange().getRequest();

            Object ownerVariable =
                    context.getVariables().get("owner");

            String owner = ownerVariable instanceof String
                    ? (String) ownerVariable
                    : "";

            // Cùng một biến phải đến từ authorization pathMatcher.
            boolean validOwner =
                    owner.matches("[A-Za-z0-9_-]{1,64}");

            // Không coi hai lần ?view=... là một giá trị hợp lệ.
            List<String> views =
                    request.getQueryParams().get("view");

            boolean validView = views == null
                    || (views.size() == 1
                        && ("summary".equals(views.get(0))
                            || "full".equals(views.get(0))));

            String view = views == null
                    ? "summary"
                    : validView ? views.get(0) : "";

            // Header này do client chọn để yêu cầu format,
            // không bao giờ là bằng chứng cấp quyền.
            List<String> formats =
                    request.getHeaders().get("X-Report-Format");

            boolean validFormat = formats == null
                    || (formats.size() == 1
                        && ("json".equals(formats.get(0))
                            || "raw".equals(formats.get(0))));

            String format = formats == null
                    ? "json"
                    : validFormat ? formats.get(0) : "";

            boolean isGet =
                    request.getMethod() == HttpMethod.GET;

            boolean sensitiveView = "full".equals(view)
                    || "raw".equals(format);

            boolean requestValid =
                    isGet && validOwner && validView && validFormat;

            return authenticationMono
                    .map(auth -> {
                        boolean loggedIn =
                                auth.isAuthenticated()
                                && !(auth instanceof
                                        AnonymousAuthenticationToken);

                        boolean isReader = hasAuthority(
                                auth, "ROLE_REPORT_READER");
                        boolean isAuditor = hasAuthority(
                                auth, "ROLE_AUDITOR");

                        boolean isOwner =
                                owner.equals(auth.getName());

                        boolean canRead = isAuditor
                                || (isReader && isOwner);

                        boolean canSeeRequestedView =
                                !sensitiveView || isAuditor;

                        boolean allow =
                                requestValid && loggedIn
                                && canRead && canSeeRequestedView;

                        return new AuthorizationDecision(allow);
                    })
                    .defaultIfEmpty(new AuthorizationDecision(false));
        };
    }

    private static boolean hasAuthority(
            Authentication auth, String required) {

        for (GrantedAuthority granted : auth.getAuthorities()) {
            if (required.equals(granted.getAuthority())) {
                return true;
            }
        }
        return false;
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
                .password("{noop}learn")
                .roles("REPORT_READER")
                .build();

        UserDetails bob = User.withUsername("bob")
                .password("{noop}read")
                .roles("REPORT_READER")
                .build();

        UserDetails auditor = User.withUsername("auditor")
                .password("{noop}audit")
                .roles("AUDITOR")
                .build();

        return new MapReactiveUserDetailsService(
                alice, bob, auditor);
    }
}
```

### 6.3. Tại sao từng quyết định được viết như vậy?

**Đường dẫn:** `pathMatchers(HttpMethod.GET, "/api/reports/{owner}")` match request và đưa `owner` vào `AuthorizationContext.getVariables()`. Giá trị owner đến từ URL và **không tự nói người gọi là owner**. Chúng ta so sánh nó với `auth.getName()` lấy từ Authentication đã được HTTP Basic xác minh.

**Method:** `pathMatchers(HttpMethod.GET, ...)` đã lọc method từ tầng DSL. Kiểm tra `request.getMethod() == HttpMethod.GET` trong custom manager là cách minh họa việc đọc `ServerWebExchange`; với rule này nó hơi dư nhưng giúp chính sách tự mô tả. Các method khác tới fallback deny. Với request POST, CSRF filter có thể chặn trước authorization, nên không gán mọi phản hồi 403 cho custom manager.

**Query:** `view=summary` là chế độ cơ bản; `view=full` cần auditor. Nếu người dùng gửi `view=full&view=summary` thì `getFirst` đơn thuần có thể tạo hành vi khó đoán. Policy dùng `List<String>` và từ chối trường hợp nhiều giá trị. Đồng thời từ chối mode không nằm trong danh sách cho phép.

**Header:** `X-Report-Format: raw` chỉ là yêu cầu xem biểu diễn nhạy cảm, **không cấp quyền**. Chính role AUDITOR mới cho phép raw. Header do client kiểm soát nên có thể spoof và phải được xử lý như đầu vào dữ liệu. Lặp header hoặc giá trị ngoài `json/raw` bị từ chối.

**Role:** `User.withUsername(...).roles("REPORT_READER")` tạo `ROLE_REPORT_READER`, tương tự `ROLE_AUDITOR`. Không so sánh username literal `"auditor"` để quyết định chức năng audit; role thật mới là nguồn của quyền.

**Missing authentication:** manager luôn trả `new AuthorizationDecision(false)` khi publisher rỗng, tránh “không có kết quả” bị hiểu sai thành quyền. `AnonymousAuthenticationToken` cũng được loại khỏi người dùng đăng nhập thật.

**Reactive:** `authenticationMono.map(...)` kết hợp identity bất đồng bộ mà không `block()`. Vì policy trong ví dụ là in-memory Boolean computation, nó không cần `Schedulers.boundedElastic()` hay chuyển thread. Nếu cần DB lookup, dùng repository reactive và `flatMap`.

**Dữ liệu handler:** HTTP response chỉ chứa chuỗi `demo-only`; một ứng dụng thật cần tải resource theo ID với tenant/user scope thích hợp và có authorization ở tầng service. Không coi rule HTTP là bảo vệ duy nhất cho mọi cách gọi service.

**Mật khẩu:** `{noop}` chỉ cho demo chạy độc lập; production cần password encoder một chiều có work factor phù hợp và HTTPS. HTTP Basic gửi credentials trên từng request, nên bảo vệ kênh truyền, rate limiting và tài nguyên hashing cũng rất quan trọng.

## 7. Chạy ví dụ và dự đoán đầu ra

Yêu cầu JDK 17+ và Gradle tương thích với Spring Boot 3.3.13. Chạy trong thư mục dự án:

```bash
gradle bootRun
```

Nếu dự án có Gradle Wrapper, dùng `./gradlew bootRun` trên Linux/macOS hoặc `gradlew.bat bootRun` trên Windows. Mở terminal khác và thử:

```bash
curl -i http://localhost:8080/health
curl -i http://localhost:8080/api/reports/alice

curl -i -u alice:learn \
  "http://localhost:8080/api/reports/alice"

curl -i -u alice:learn \
  "http://localhost:8080/api/reports/bob"

curl -i -u alice:learn \
  "http://localhost:8080/api/reports/alice?view=full"

curl -i -u auditor:audit \
  "http://localhost:8080/api/reports/bob?view=full"

curl -i -u alice:learn -H "X-Report-Format: raw" \
  "http://localhost:8080/api/reports/alice"

curl -i -u auditor:audit -H "X-Report-Format: raw" \
  "http://localhost:8080/api/reports/bob"

curl -i -u alice:learn \
  "http://localhost:8080/api/reports/alice?view=summary&view=full"

curl -i -u alice:learn \
  "http://localhost:8080/api/reports/alice?view=unknown"
```

### Kết quả mong đợi

| Request | HTTP dự kiến | Ý nghĩa |
| --- | --- | --- |
| `GET /health` | 200, `OK` | Public |
| `GET /api/reports/alice` không credentials | 401 Basic challenge | Chưa xác thực |
| Alice → `/api/reports/alice` | 200 | Owner + reader |
| Alice → `/api/reports/bob` | 403 | Không phải owner, không phải auditor |
| Alice → `/api/reports/alice?view=full` | 403 | Full yêu cầu AUDITOR |
| Auditor → `/api/reports/bob?view=full` | 200 | AUDITOR có quyền đặc biệt |
| Alice + header `X-Report-Format: raw` | 403 | Client không thể tự xin raw nếu thiếu AUDITOR |
| Auditor + `X-Report-Format: raw` | 200 | Đủ AUDITOR |
| Alice + hai giá trị `view` | 403 | Chính sách từ chối input mơ hồ |
| Alice + `view=unknown` | 403 | Không hợp lệ |
| POST vào report GET endpoint | Bị chặn | CSRF hoặc fallback deny; không kết luận chỉ từ status |

Khi HTTP 200, endpoint trả JSON có các thuộc tính như `owner`, `view`, `format` và `data`. Ví dụ khi Alice xem summary:

```json
{
  "owner": "alice",
  "view": "summary",
  "format": "json",
  "data": "demo-only"
}
```

Đây là **hình dạng nội dung dự kiến**, không phải lời hứa thứ tự field/whitespace giống hệt: serializer JSON có thể sắp field khác thứ tự. Thông tin quan trọng là HTTP status và giá trị field. Với 403/401, handler `getReport` không được chạy để tạo JSON trên.

## 8. Kiểm thử Spring Boot/WebTestClient

Tạo `src/test/java/example/ExchangeAuthorizationApplicationTests.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
@AutoConfigureWebTestClient
class ExchangeAuthorizationApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicHealthIsAllowed() {
        client.get().uri("/health")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("OK");
    }

    @Test
    void unauthenticatedRequestRequiresBasicAuth() {
        client.get().uri("/api/reports/alice")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void readerCanAccessOwnSummary() {
        client.get().uri("/api/reports/alice")
                .headers(h -> h.setBasicAuth("alice", "learn"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.owner").isEqualTo("alice")
                .jsonPath("$.view").isEqualTo("summary");
    }

    @Test
    void readerCannotAccessAnotherOwner() {
        client.get().uri("/api/reports/bob")
                .headers(h -> h.setBasicAuth("alice", "learn"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void readerCannotRequestFullView() {
        client.get().uri("/api/reports/alice?view=full")
                .headers(h -> h.setBasicAuth("alice", "learn"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void auditorCanRequestOtherUsersFullView() {
        client.get().uri("/api/reports/bob?view=full")
                .headers(h -> h.setBasicAuth("auditor", "audit"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.owner").isEqualTo("bob")
                .jsonPath("$.view").isEqualTo("full");
    }

    @Test
    void clientHeaderCannotGrantRawView() {
        client.get().uri("/api/reports/alice")
                .headers(h -> h.setBasicAuth("alice", "learn"))
                .header("X-Report-Format", "raw")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void auditorCanRequestRawView() {
        client.get().uri("/api/reports/bob")
                .headers(h -> h.setBasicAuth("auditor", "audit"))
                .header("X-Report-Format", "raw")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.format").isEqualTo("raw");
    }

    @Test
    void duplicateViewIsDenied() {
        client.get()
                .uri("/api/reports/alice?view=summary&view=full")
                .headers(h -> h.setBasicAuth("alice", "learn"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void unknownViewIsDenied() {
        client.get().uri("/api/reports/alice?view=unknown")
                .headers(h -> h.setBasicAuth("alice", "learn"))
                .exchange()
                .expectStatus().isForbidden();
    }
}
```

Chạy:

```bash
gradle test
```

Các test kiểm tra **quy tắc thực trong security filter chain**, không đơn thuần test controller. Mục tiêu của bài là chứng minh **actor + resource owner + mode từ exchange** tạo ra kết quả đúng. `WebTestClient` cho phép gửi path, query, header và Basic credentials để làm rõ từng điều kiện.

**Cần test thêm khi đưa vào production:** GET vs HEAD/OPTIONS, encoded path, route không khớp matcher, query lặp, header lặp, tên Unicode/tenant ID, token hết hạn, authority mapping, user bị khóa và lỗi database. Không dựa vào một test HTTP 200 duy nhất để kết luận policy an toàn.

## 9. Nếu quyền phụ thuộc dữ liệu trong database

Trong demo, owner được gắn với username trên URL chỉ để dễ hiểu. Với dữ liệu thật, người dùng có thể đổi username, báo cáo có resource ID riêng và quyền có thể phụ thuộc **ACL/tenant membership**. Không nên cho phép truy cập dựa vào việc client khai báo `owner=alice` mà chưa đối chiếu báo cáo thuộc ai trong database.

Giả sử request `GET /api/reports/{reportId}` và `reportId` là mã báo cáo. Authorization cần:

```text
Authentication (userId/tenantId đã xác minh)
   + URL reportId (đối tượng client muốn xem)
   + Server-side lookup: report.ownerId, report.tenantId,
                          report.state, sharing grants
   -> quyết định ALLOW/DENY
```

Mảnh code sau minh họa ý tưởng dùng repository **reactive** (không phải ứng dụng độc lập):

```java
ReactiveAuthorizationManager<AuthorizationContext> policy =
        (authenticationMono, context) -> {

            Object rawId = context.getVariables().get("reportId");

            if (!(rawId instanceof String reportId)
                    || reportId.isBlank()) {
                return Mono.just(new AuthorizationDecision(false));
            }

            return authenticationMono
                    .flatMap(authentication -> {
                        if (!authentication.isAuthenticated()
                                || authentication instanceof
                                        AnonymousAuthenticationToken) {
                            return Mono.just(
                                    new AuthorizationDecision(false));
                        }

                        return reportRepository.findById(reportId)
                                .map(report -> {
                                    boolean sameTenant =
                                            report.tenantId().equals(
                                                trustedTenantOf(authentication));

                                    boolean canRead =
                                            report.ownerId().equals(
                                                trustedUserIdOf(authentication))
                                            || hasReadGrant(
                                                authentication, report);

                                    return new AuthorizationDecision(
                                            sameTenant && canRead);
                                })
                                .defaultIfEmpty(
                                    new AuthorizationDecision(false));
                    })
                    .defaultIfEmpty(new AuthorizationDecision(false));
        };
```

**Giới hạn của mảnh minh họa:** `reportRepository`, `trustedTenantOf`, `trustedUserIdOf` và `hasReadGrant` là abstraction phải được ứng dụng cung cấp; `report` phải có record/domain model tương ứng. Mảnh này không thể biên dịch độc lập; chương trình Gradle hoàn chỉnh nằm ở mục 6.

**Các nguyên tắc khi đưa logic DB vào manager:**

- `reportRepository.findById(...)` nên là repository **reactive** trả publisher, không gọi `block()` trên event loop.
- Nếu không tìm thấy report hoặc user không có quyền, `Mono.empty()` phải trở thành DENY (hoặc xử lý 404 có chủ đích ở tầng API); không tự cho phép.
- Nếu DB gặp lỗi, để lỗi đi qua đường giám sát xử lý hạ tầng; **không** chuyển thành `AuthorizationDecision(true)` hoặc nuốt lỗi để tiếp tục handler.
- Nếu quyền thay đổi nhanh, kiểm tra lại tại thời điểm thực thi nghiệp vụ; tránh TOCTOU (time-of-check to time-of-use) giữa authorization và thao tác thay đổi dữ liệu.
- Không dùng user ID/tenant ID tự do trong request header thay cho thông tin đã xác minh ở Authentication/DB.
- Trong hệ thống multi-tenant, repository nên **scope truy vấn theo tenant của principal** thay vì tải mọi record toàn cục rồi mới lọc nếu có khả năng rò rỉ dữ liệu qua các đường khác.

### Authorization ở tầng service để phòng thủ nhiều lớp

HTTP manager bảo vệ route ngoài Internet. Nhưng nếu cùng service được gọi từ scheduler, message listener, RSocket hoặc job nội bộ, không có đảm bảo nó đã đi qua `AuthorizationWebFilter`. Đối với nghiệp vụ nhạy cảm, thêm kiểm tra ở service, ví dụ reactive method security `@EnableReactiveMethodSecurity` và `@PreAuthorize` khi phù hợp. Method security phải được cấu hình đúng với Reactor context và đường gọi không phải HTTP.

**Không trùng lặp logic một cách thiếu nhất quán**: nên đưa policy nghiệp vụ/ACL vào service chia sẻ, còn HTTP manager quyết định routing và quyền sơ bộ. Kiểm thử cả API và service trong các bối cảnh khác nhau.

## 10. Thông tin IP, proxy, header và nguồn tin cậy

`ServerWebExchange` cho phép đọc `getRemoteAddress()` và HTTP headers. Nhưng phía sau reverse proxy/load balancer:

```text
Client -> CDN -> Ingress -> App WebFlux

request.getRemoteAddress() có thể là IP của ingress.
X-Forwarded-For có thể chứa giá trị do upstream chuyển tiếp.
```

**Không tin `X-Forwarded-For`, `Forwarded` hoặc `X-Real-IP` vô điều kiện**. Nếu app kết nối trực tiếp tới Internet, kẻ tấn công có thể tự gửi các header đó. Muốn dùng IP trong policy:

1. Chỉ cho phép traffic đến app từ các reverse proxy **đáng tin cậy**.
2. Cấu hình edge/gateway ghi đè hoặc lọc forwarded headers do client gửi.
3. Thiết lập forward-header handling tại ứng dụng theo deployment thực tế (ví dụ `server.forward-headers-strategy` trong Spring Boot).
4. Xác định địa chỉ nào được coi là IP client cuối cùng sau chuỗi proxy, tránh tin giá trị đầu chuỗi do client tự khai.
5. Không dùng IP một mình để cấp quyền nhạy cảm: dùng authentication, role, network policy, MFA và kiểm soát thiết bị khi phù hợp.
6. Viết integration test mô phỏng kẻ tấn công gửi header giả.

Cần phân biệt **network access control** (được kết nối từ mạng nào) với **business authorization** (được xem báo cáo nào). Kiểm tra HTTP header do client chọn chế độ biểu diễn là hợp lệ nếu nó chỉ khiến policy chặt hơn; dùng header làm principal/role là sai.

### Cookie và query parameter cũng không tự đáng tin

Một session cookie chỉ có ý nghĩa sau khi Spring Security/Spring Session xác minh nó, tìm ra session và nạp Authentication hợp lệ. Tự đọc `Cookie: role=ADMIN` trong custom manager để cấp ADMIN là lỗ hổng.

Query `?tenant=abc` có thể dùng làm yêu cầu lựa chọn tenant, nhưng phải so sánh với **membership đã xác minh** trong token/database. Tự tin `tenant=abc` nghĩa user thuộc tenant abc có thể gây IDOR/cross-tenant data leak.

## 11. Ưu tiên rule, thứ tự và fail-closed

### 11.1. Thứ tự các rule trong một chain

```java
// Sai: rule đầu tiên quá rộng có thể nuốt rule chặt hơn bên dưới.
http.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/api/**").authenticated()
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .anyExchange().denyAll());
```

Request `/api/admin/...` khớp rule `/api/**` trước, nên rule ADMIN phía sau không được áp dụng. Hãy đặt **rule cụ thể trước rule tổng quát**:

```java
http.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .pathMatchers("/api/**").authenticated()
        .anyExchange().denyAll());
```

Tương tự, nếu một custom manager áp dụng cho `/api/reports/{owner}`, nó cần được đặt trước rule quá rộng `/api/**`. `anyExchange().denyAll()` nên là đường dự phòng cuối.

### 11.2. Thứ tự các SecurityWebFilterChain

Nếu nhiều `SecurityWebFilterChain` tồn tại, `@Order` của từng chain và `securityMatcher` chọn chain **trước** khi nội bộ gọi `authorizeExchange`. `@Order` trên bean toàn cục `WebFilter` và `SecurityWebFiltersOrder` bên trong chain là hai lớp thứ tự khác nữa.

Không cho rằng custom manager sẽ được gọi nếu request rơi vào một chain khác. Phải kiểm thử URL giao nhau, chain fallback và trường hợp không có chain nào khớp. **Không có chain match không tự động là DENY**; bảo đảm phạm vi bảo vệ đầy đủ.

### 11.3. Mono.empty, DENY và ERROR

| Tín hiệu từ custom manager | Cách hiểu cần lưu ý | Hướng xử lý |
| --- | --- | --- |
| `Mono.just(new AuthorizationDecision(true))` | Cho phép theo policy đã đánh giá | Chỉ phát khi đủ bằng chứng |
| `Mono.just(new AuthorizationDecision(false))` | Từ chối | Dùng khi thiếu quyền, input không hợp lệ |
| `Mono.empty()` | Không phát quyết định | Tránh để thiếu identity/lookup biến thành abstain ngoài ý định |
| `Mono.error(...)` | Lỗi đánh giá, không phải role DENY | Truyền lỗi hoặc xử lý fail-closed có metric; không biến thành ALLOW |

Đối với một chính sách rõ ràng, nên dùng `defaultIfEmpty(new AuthorizationDecision(false))` để thiếu context không thành “cho phép”. Nếu backend quyền/ACL hỏng, **không** dùng:

```java
// SAI: lỗi database làm người dùng được phép.
return policy.check(authentication, context)
        .onErrorReturn(new AuthorizationDecision(true));
```

Lỗi hạ tầng có thể trả 5xx, ghi metric/alert và để API không thực hiện nghiệp vụ. Tránh `onErrorComplete()` làm biến mất lỗi rồi downstream tiếp tục với ngữ cảnh mơ hồ.

### 11.4. HTTP 401 và 403

- **401 Unauthorized:** request chưa có authentication phù hợp, HTTP Basic/Bearer entry point có thể gửi challenge.
- **403 Forbidden:** người dùng đã xác thực nhưng không đủ quyền, hoặc một filter khác như CSRF từ chối request.
- **400 Bad Request:** validation xử lý input lỗi khi pipeline được phép đến tầng validation; manager cũng có thể deny sớm theo policy.
- **5xx:** lỗi hệ thống khi load permission từ DB, network, serializer v.v. theo error handling.

Không suy luận “403 chắc chắn do custom ReactiveAuthorizationManager” nếu còn CSRF, CORS, matcher hoặc authentication filter. Kiểm thử phải xác định đúng **lớp từ chối**.

## 12. Hiệu năng và khả năng quan sát

Custom manager có thể chạy ở **mỗi request** khớp rule. Vì vậy:

- Không gọi DB blocking, HTTP client blocking hoặc `Thread.sleep(...)` trên Netty event loop.
- Dùng `ReactiveCrudRepository`/`WebClient` và các toán tử `flatMap` khi cần I/O; nếu bắt buộc dùng thư viện đồng bộ, offload có giới hạn theo thiết kế và đo tải.
- Tránh lookup dữ liệu nặng nhiều lần trong cùng request; cân nhắc request-scoped cache có vòng đời ngắn hoặc kết hợp query hiệu quả.
- Caching quyết định ALLOW liên request phải có invalidation rõ ràng khi role/tenant membership/resource owner thay đổi; cache cẩu thả dễ gây quyền cũ còn hiệu lực.
- Policy nên không có side effect (không trừ quota, không chuyển trạng thái đơn hàng) vì framework có thể đánh giá lại hoặc request bị hủy.
- Không đưa password/token/cookie/session ID, raw query nhạy cảm hoặc toàn bộ SecurityContext vào log.
- Đo latency authorization và backend entitlement/ACL, tỷ lệ allow/deny/error, 401/403/5xx, cùng độ trễ p95/p99 ở tải cao.
- Với dữ liệu tenant nhạy cảm, audit log nên lưu **actor ID, resource ID, policy version và kết quả** ở dạng được phép, tránh leak dữ liệu riêng.

### Ma trận điều tra một sự cố

| Triệu chứng | Khả năng | Cần kiểm tra |
| --- | --- | --- |
| User có role nhưng bị 403 | Owner/path không khớp hoặc mode yêu cầu AUDITOR | `context.getVariables()`, authority thực, query/header |
| User khác tenant vẫn được phép | Tin header hoặc path thay cho DB/claim | Nguồn tenant đáng tin và lookup ownership |
| Không thấy custom manager được gọi | Rule/chain trước khớp trước | Thứ tự `securityMatcher`, `@Order`, `pathMatchers` |
| Cùng URL lúc 200 lúc 403 | Query/header khác, role thay đổi hoặc cache | Request context, JWT/session, dữ liệu ACL |
| 403 khi POST dù đủ role | CSRF chặn trước | Token CSRF, cookie và phương thức |
| 401 dù gửi Basic | Credentials sai/hết hạn hoặc manager không nhận | Authentication mechanism và header thực |
| 5xx khi Redis/DB lỗi | Policy dependency không sẵn sàng | Error logs có kiểm soát, timeout, circuit breaking |
| Event loop chậm | Có blocking trong custom manager | Thread dump/profiling, reactive driver, latency |
| Query lặp gây quyền bất thường | Parameter pollution | Kiểm tra số lượng giá trị, không chỉ `getFirst` |

## 13. Checklist áp dụng an toàn

1. **Tách đầu vào:** actor/authorities lấy từ `Authentication`, resource từ URL và dữ liệu server-side; không lấy role từ header tự gửi.
2. **Đúng matcher:** `pathMatchers` bao phủ đúng HTTP method, URL và capture variables; các rule cụ thể được xét trước.
3. **Đúng chain:** `securityMatcher` và `@Order` không loại request khỏi chain mong muốn; có fallback an toàn.
4. **Kiểm tra ownership:** đối chiếu stable user/tenant IDs; không mặc định path variable là bằng chứng quyền.
5. **Query/header hợp lệ:** xử lý mode không hợp lệ, giá trị lặp, thiếu trường, giá trị không được hỗ trợ.
6. **Fail-closed:** thiếu authentication hoặc không tìm thấy ACL -> DENY; hạ tầng lỗi -> không được ALLOW.
7. **Không blocking:** kết hợp identity/entitlement qua Reactor operators; không `block()` trên event loop.
8. **HTTP status:** phân biệt thiếu auth, thiếu quyền, CSRF failure và lỗi hệ thống.
9. **Defense in depth:** tài nguyên nhạy cảm có authorization bổ sung trong service/domain, không chỉ route.
10. **Kiểm thử negative:** user khác owner, role thiếu, mode cao hơn, header giả, query lặp và path ngoài matcher.
11. **Không rò rỉ:** hạn chế log headers/tokens; nếu dùng IP thật, xác minh proxy trust.
12. **Quan sát production:** authorization latency, deny/error metrics, audit và thử nghiệm sau mỗi thay đổi policy.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `AuthorizationContext.getExchange()` khác `getVariables()` như thế nào?  
**Đáp:** `getExchange()` cung cấp ServerWebExchange với HTTP request/response/attributes; `getVariables()` cung cấp URI variables do authorization matcher trích xuất.

**Câu 2.** Vì sao không dùng `X-User-Role: ADMIN` để cho vào admin?  
**Đáp:** Header HTTP do client tự giả mạo được. Role phải đến từ Authentication/identity provider đã được xác minh.

**Câu 3.** Alice có `ROLE_REPORT_READER`, truy cập `/api/reports/bob` thì có được không?  
**Đáp:** Không theo policy mẫu, vì role đọc chưa đủ: Alice không phải owner và không có AUDITOR.

**Câu 4.** Alice gửi `X-Report-Format: raw`, quyền có tự tăng không?  
**Đáp:** Không. Header chỉ yêu cầu biểu diễn raw; policy bắt buộc role AUDITOR cho dạng raw.

**Câu 5.** `pathMatchers(HttpMethod.GET, "/api/reports/{owner}")` có thể truyền `owner` cho custom manager bằng đâu?  
**Đáp:** `AuthorizationContext.getVariables().get("owner")`. Không cần đợi controller chạy để đọc biến đường dẫn.

**Câu 6.** `Mono.empty()` từ custom authorization có đồng nghĩa DENY chắc chắn không?  
**Đáp:** Không nên dựa vào implicit empty semantics. Với policy cần từ chối khi thiếu dữ liệu, trả tường minh `AuthorizationDecision(false)`, chẳng hạn bằng `defaultIfEmpty(...)`.

**Câu 7.** Có nên dùng `block()` để đọc role hoặc ownership từ database reactive trong manager không?  
**Đáp:** Không. Dùng `flatMap`/`map` và repository reactive; blocking có thể làm nghẽn event loop.

**Câu 8.** Vì sao `POST /api/reports/alice` có thể nhận 403 ngay cả khi chưa vào report manager?  
**Đáp:** CSRF filter có thể chặn method thay đổi trạng thái trước authorization. Ngoài ra report manager được gắn với GET matcher, nên POST không áp dụng manager đó.

**Câu 9.** Nếu thêm một rule `/api/**.authenticated()` trước rule báo cáo, custom manager có chạy không?  
**Đáp:** Có thể không. Rule đầu khớp trước và quyết định, vì vậy phải đặt rule cụ thể trước rule rộng.

**Câu 10.** Một request đã qua HTTP authorization thì service có nhất thiết an toàn khi được gọi từ message listener không?  
**Đáp:** Không. Message listener có thể không đi qua `AuthorizationWebFilter`; quyền nghiệp vụ cần được bảo vệ ở service/domain khi có nhiều đường gọi.

**Câu 11.** Địa chỉ từ `X-Forwarded-For` có luôn là IP client đáng tin không?  
**Đáp:** Không. Phải có reverse proxy tin cậy, cấu hình lọc/ghi đè forwarded headers và network boundary phù hợp.

**Câu 12.** Nếu entitlement database bị lỗi, có thể trả ALLOW vì “không biết chắc bị cấm” không?  
**Đáp:** Không. Lỗi hạ tầng không phải bằng chứng cấp quyền; phải fail-closed hoặc trả lỗi phù hợp.

**Ghi nhớ:** Trong Spring Security WebFlux, `ReactiveAuthorizationManager<AuthorizationContext>` cho phép kết hợp **Authentication/authorities đã xác minh** với **ServerWebExchange và URI variables** để xây dựng HTTP authorization có điều kiện. Điều kiện request có thể làm policy chặt hơn, nhưng **không thể thay thế nguồn quyền đáng tin cậy**. Dùng matcher cụ thể, quyết định rõ ALLOW/DENY, kết hợp reactive I/O đúng cách và test cả các trường hợp bị từ chối.

## Tài liệu tham khảo

- [Spring Security — Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): `authorizeExchange`, `pathMatchers`, `access` và cách kết hợp custom ReactiveAuthorizationManager.
- [Spring Security — ServerHttpSecurity API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html): DSL reactive authorization và authentication.
- [Spring Security — AuthorizationContext API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/AuthorizationContext.html): `getExchange()` và `getVariables()`.
- [Spring Security — ReactiveAuthorizationManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html): reactive check/verify contract.
- [Spring Security — AuthorizationDecision API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationDecision.html): cách biểu đạt granted/denied.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): bảo vệ phương thức service trong reactive pipelines.
- [Spring Framework — ServerWebExchange](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/ServerWebExchange.html): request/response/attributes/session API.
- [Spring Security — CSRF in WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): vì sao request POST có thể bị từ chối trước authorization.
