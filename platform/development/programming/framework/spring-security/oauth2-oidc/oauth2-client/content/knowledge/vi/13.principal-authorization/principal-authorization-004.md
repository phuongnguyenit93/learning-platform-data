# 13.4. Truy cập principal trong controller và chuỗi Reactive

## Mục tiêu bài học

Sau khi Spring Security hoàn tất **OAuth 2.0 Login / OpenID Connect (OIDC) Login**, ứng dụng có một đối tượng **principal** đại diện cho người dùng đã xác thực. Ở một controller, chúng ta thường muốn biết người dùng là ai để hiển thị hồ sơ hoặc truy vấn dữ liệu thuộc quyền sở hữu của họ. Trong một chuỗi xử lý **Reactive WebFlux**, cùng nhu cầu đó phải được giải quyết theo mô hình **Reactor Context**, thay vì giả định principal luôn nằm trong `ThreadLocal`.

Bài học tập trung vào hai thế giới của Spring Security:

- **Servlet / Spring MVC**: truy cập principal bằng `@AuthenticationPrincipal`, tham số `Authentication` / `Principal` hoặc `SecurityContextHolder`.
- **Reactive / Spring WebFlux**: sử dụng `@AuthenticationPrincipal` ở controller, `ServerWebExchange.getPrincipal()` và `ReactiveSecurityContextHolder` trong pipeline `Mono` / `Flux`.

Sau bài học, bạn có thể:

1. Phân biệt `Principal`, `Authentication`, `SecurityContext`, `OidcUser` và `OAuth2User`.
2. Lấy thông tin OIDC đã xác thực trong Spring MVC controller.
3. Xây endpoint WebFlux trả về `Mono` và lấy Authentication bên trong một chuỗi reactive.
4. Hiểu vì sao `SecurityContextHolder.getContext()` không phải phương án mặc định đáng tin cậy để truy cập principal ở mọi operator reactive.
5. Truyền danh tính người dùng đúng cách từ controller tới service, tránh nhầm tài khoản giữa các request.
6. Áp phân quyền từ authorities và dữ liệu nghiệp vụ, không dùng email/ID token làm quyền truy cập.
7. Biết cách lấy **access token** đã được cấp để gọi API thay vì dùng ID token làm bearer token.
8. Xử lý principal thiếu, sai loại, đổi tài khoản hoặc request chạy dưới nhiều cơ chế authentication.

## 1. Bối cảnh: principal xuất hiện sau OIDC Login như thế nào?

Giả sử có ứng dụng **Customer Portal**, được viết với Spring Boot và Spring Security OAuth 2.0 Client. Người dùng đăng nhập qua một OpenID Provider (OP) doanh nghiệp.

Luồng thường gặp:

~~~mermaid
sequenceDiagram
    autonumber
    actor User as Người dùng
    participant Browser as Trình duyệt
    participant Portal as Customer Portal
    participant OP as OpenID Provider
    User->>Browser: Truy cập /me
    Browser->>Portal: HTTP request
    Portal-->>Browser: Redirect OIDC Authorization Request
    Browser->>OP: Đăng nhập / consent khi cần
    OP-->>Browser: Redirect authorization code
    Browser->>Portal: Callback code + state
    Portal->>OP: Đổi code lấy token
    OP-->>Portal: ID token, access token nếu được cấp
    Note over Portal: Kiểm tra OIDC, tạo OidcUser và Authentication
    Portal-->>Browser: Session / response theo cấu hình
    Browser->>Portal: Request tiếp theo đến /me
    Note over Portal: Khôi phục Authentication và principal
    Portal-->>Browser: Thông tin của người dùng
~~~

Sau callback OIDC thành công, Spring Security tạo đối tượng `Authentication`. Đối tượng này chứa principal và các quyền/authority mà ứng dụng đã ánh xạ.

Đối với OIDC Login Servlet hoặc WebFlux thông thường, principal thường triển khai interface `OidcUser`.

**Điểm mấu chốt:** principal không phải authorization code, không phải session ID và cũng không phải một access token. Principal là đối tượng mô tả danh tính đã được framework chấp nhận trong ngữ cảnh xác thực.

### 1.1. Ví dụ một principal OIDC

Một ID token đã được xác minh có thể chứa các claim:

~~~json
{
  "iss": "https://id.example.com/realms/customers",
  "sub": "customer-4872",
  "aud": "portal-web",
  "iat": 1800000000,
  "exp": 1800003600,
  "email": "alice@example.com",
  "name": "Alice Nguyen",
  "email_verified": true
}
~~~

Đây chỉ là payload minh họa. Một ID token thật phải được OP phát hành và được RP kiểm tra theo quy tắc OIDC, gồm chữ ký hoặc cơ chế bảo vệ phù hợp, issuer, audience, thời hạn và nonce nếu được yêu cầu.

Spring Security có thể biểu diễn kết quả đó bằng một `OidcUser`, cho phép ứng dụng đọc issuer, subject, email hoặc tên nếu các claim tương ứng được cung cấp.

## 2. Mô hình đối tượng: Principal, Authentication và SecurityContext

Ba khái niệm thường được nhắc cùng nhau nhưng có trách nhiệm khác nhau.

| Thành phần | Vai trò | Có thể đọc gì? |
|---|---|---|
| `Principal` | Abstraction xác định chủ thể của request | Thường có `getName()` |
| `Authentication` | Kết quả authentication, có principal và authorities | `getPrincipal()`, `getAuthorities()`, `isAuthenticated()` |
| `SecurityContext` | Ngữ cảnh chứa Authentication hiện tại | `getAuthentication()` |
| `OidcUser` | Principal đã được xử lý theo OIDC Login | `getIdToken()`, `getClaims()`, `getSubject()`, `getEmail()` |
| `OAuth2User` | Principal của OAuth2 Login nói chung | `getAttributes()`, `getAuthorities()` |
| `OAuth2AuthenticationToken` | Một kiểu Authentication phổ biến sau OAuth2/OIDC Login | Principal, authorities, `getAuthorizedClientRegistrationId()` |

Một mô hình đơn giản:

~~~text
SecurityContext
└── Authentication
    ├── principal
    │   └── OidcUser
    │       ├── OidcIdToken
    │       ├── OidcUserInfo (nếu có)
    │       └── claims / attributes
    ├── GrantedAuthorities
    └── authenticated
~~~

Sơ đồ chỉ mô tả quan hệ khái niệm; không khẳng định toàn bộ các đối tượng luôn được lưu trong một cấu trúc session cụ thể.

### 2.1. `Principal.getName()` không nhất thiết là email

Một kiểu nhầm lẫn thường thấy:

~~~java
String username = principal.getName();
// Sai nếu mặc định username luôn là email.
~~~

Với OIDC, tên principal có thể được xác định từ `sub` hoặc một thuộc tính do ứng dụng/provider cấu hình. Email có thể thay đổi, bị thiếu hoặc không được xác minh.

Để liên kết một tài khoản bên ngoài với bản ghi nội bộ, lựa chọn thường an toàn hơn là cặp:

~~~text
issuer  = https://id.example.com/realms/customers
subject = customer-4872

Khóa định danh phía ứng dụng = issuer + subject
~~~

`sub` chỉ được bảo đảm mang ý nghĩa định danh trong phạm vi issuer tương ứng. Hai provider khác nhau có thể dùng cùng chuỗi `sub` cho hai người khác nhau.

### 2.2. `isAuthenticated()` không đồng nghĩa có quyền nghiệp vụ

`Authentication.isAuthenticated()` mô tả trạng thái xác thực của object. Nó không quyết định liệu người dùng có được xem đơn hàng của người khác hay không.

Ví dụ:

- Alice có thể đăng nhập hợp lệ nhưng chỉ xem được đơn hàng của chính Alice.
- Bob có thể có authority quản trị nhất định nhưng vẫn bị giới hạn bởi tenant.
- Một tài khoản đã được xác thực tại OP chưa chắc đã được kích hoạt trong Customer Portal.

Phân quyền cần xem xét **authorities**, ownership, tenant, trạng thái tài khoản và chính sách nghiệp vụ.

### 2.3. OIDC principal khác JWT Resource Server principal

Nếu một request đi qua **OIDC Login** bằng browser, principal thường là `OidcUser`.

Nếu cùng hệ thống có API nhận bearer JWT theo cấu hình **Resource Server**, Authentication thường là `JwtAuthenticationToken` và principal có thể là `Jwt`. Một controller nhận `@AuthenticationPrincipal OidcUser` sẽ **không tự đúng** với request được xác thực bằng bearer JWT.

Cần thiết kế filter chain, endpoint và kiểu principal theo phương thức authentication thực sự.

## 3. Truy cập principal trong Spring MVC / Servlet

Trong Servlet stack, Spring Security thông thường gắn `SecurityContext` với luồng xử lý request qua `SecurityContextHolder`. Framework có thể lưu và khôi phục context giữa các request nhờ `SecurityContextRepository`, thường có liên hệ với `HttpSession` khi dùng login dựa trên session.

Có ba cách đọc principal phổ biến.

### 3.1. `@AuthenticationPrincipal`: lấy trực tiếp `OidcUser`

Ví dụ controller:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/me")
    UserProfile me(@AuthenticationPrincipal OidcUser user) {
        return new UserProfile(
                user.getIdToken().getIssuer().toString(),
                user.getIdToken().getSubject(),
                user.getFullName(),
                user.getEmail());
    }

    record UserProfile(
            String issuer,
            String subject,
            String fullName,
            String email) {}
}
~~~

Giải thích:

1. `@AuthenticationPrincipal` lấy principal từ Authentication đang có.
2. `OidcUser` cho phép truy cập các claim OIDC đã được framework xử lý.
3. `getIdToken().getIssuer()` và `getIdToken().getSubject()` giúp xác định tài khoản bên ngoài.
4. Các claim `name` hoặc `email` có thể không tồn tại.

**Giả định của ví dụ:** `/me` được bảo vệ bằng OIDC Login. Nếu request chưa xác thực hoặc sử dụng một kiểu authentication khác, tham số có thể không có `OidcUser` như mong đợi. Endpoint thực tế phải xử lý điều kiện đó thay vì dereference một giá trị `null`.

### 3.2. Nhận `Authentication` như method parameter

Nếu cần cả principal lẫn authorities:

~~~java
import java.util.List;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LoginDetailsController {

    @GetMapping("/login-details")
    LoginDetails details(Authentication authentication) {
        String registrationId = null;

        if (authentication instanceof OAuth2AuthenticationToken oauth) {
            registrationId = oauth.getAuthorizedClientRegistrationId();
        }

        List<String> authorities = authentication.getAuthorities()
                .stream()
                .map(GrantedAuthority::getAuthority)
                .toList();

        String subject = authentication.getPrincipal() instanceof OidcUser oidc
                ? oidc.getIdToken().getSubject()
                : null;

        return new LoginDetails(authentication.getName(),
                registrationId, subject, authorities);
    }

    record LoginDetails(
            String principalName,
            String registrationId,
            String subject,
            List<String> authorities) {}
}
~~~

Ví dụ trên nhận Authentication đã được Spring Security thiết lập. Nó có thể cho biết registration ID đã dùng khi request là OAuth2/OIDC Login.

Khi ứng dụng có nhiều kiểu authentication, dùng kiểm tra kiểu như `instanceof` hoặc xây một abstraction principal nội bộ thống nhất; **không cast mù** sang `OidcUser`.

### 3.3. Nhận interface `Principal`

Đối với trường hợp chỉ cần tên định danh:

~~~java
import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    @GetMapping("/hello")
    String hello(Principal principal) {
        return "Hello, " + principal.getName();
    }
}
~~~

Cách này ít phụ thuộc Spring Security hơn, nhưng **không tự cho biết issuer, subject và các claim OIDC**. Hãy dùng `OidcUser` khi cần định danh OIDC đầy đủ.

Đừng dùng `getName()` như bằng chứng email hoặc quyền truy cập.

### 3.4. `SecurityContextHolder` trong Servlet service

Một service chạy cùng luồng xử lý request có thể truy cập:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

public class CurrentAuthenticationLookup {

    public Authentication current() {
        return SecurityContextHolder.getContext().getAuthentication();
    }
}
~~~

Cách này hữu ích trong tầng không nhận được principal qua method parameter, nhưng tạo phụ thuộc vào trạng thái bảo mật đang hoạt động.

Trong mã nghiệp vụ dễ kiểm thử, thường tốt hơn khi controller chuyển **issuer + subject** hoặc một đối tượng user identity đã được xác minh vào service. Nhờ đó service không cần phải biết request đến từ Servlet hay Reactive.

### 3.5. Không lưu principal hiện tại vào biến static

Ví dụ sai:

~~~java
public final class BadCurrentUser {
    static OidcUser lastLoggedInUser;
}
~~~

`static` được chia sẻ giữa các request và người dùng. Nếu cập nhật biến này trong login handler, request của người khác có thể đọc nhầm danh tính cũ.

Tương tự, không cache `Authentication` theo một khóa chung không gắn principal/session hoặc lưu trực tiếp object người dùng ở singleton service như trạng thái mutable.

## 4. Chuỗi Reactive khác Servlet ở điểm nào?

Với **Spring WebFlux**, request được xử lý qua **reactive pipeline** gồm các publisher như `Mono` và `Flux`. Một chuỗi xử lý có thể chuyển giữa các thread tùy scheduler/operator; không có bảo đảm rằng toàn bộ xử lý nằm trên một thread Servlet gắn với một `ThreadLocal` cố định.

Trong Spring Security Reactive, SecurityContext được đưa vào **Reactor Context** và có thể được truy cập bằng:

~~~java
ReactiveSecurityContextHolder.getContext()
~~~

Đây là khác biệt trung tâm.

| Tiêu chí | Servlet / Spring MVC | Reactive / Spring WebFlux |
|---|---|---|
| Mô hình xử lý | Request thường được xử lý theo luồng Servlet | Publisher được subscribe và thực thi qua pipeline reactive |
| Truy cập context ở service | `SecurityContextHolder.getContext()` | `ReactiveSecurityContextHolder.getContext()` |
| Kiểu dữ liệu context API | `SecurityContext` | `Mono<SecurityContext>` |
| Gắn context | Thường ThreadLocal trong request | Reactor subscriber context |
| Session mặc định khi dùng web login | `HttpSession` | `WebSession` / ServerSecurityContextRepository phù hợp |
| Filter bảo mật | `SecurityFilterChain` và Servlet filters | `SecurityWebFilterChain` và WebFilters |
| HTTP client hỗ trợ non-blocking | Có thể dùng `RestClient` hoặc WebClient theo mục đích | Thường dùng `WebClient` |
| Lưu ý khi chuyển thread | ThreadLocal không tự đi theo custom thread | Reactor Context có cơ chế lan truyền theo chuỗi reactive, không phải mọi manual subscribe |

**Không trộn hai cách truy cập context một cách cơ học.** Đặt `SecurityContextHolder.getContext()` trong một `flatMap` của WebFlux có thể cho kết quả rỗng hoặc không đúng ngữ cảnh tùy cách chạy.

## 5. Cấu hình OIDC Login cho Spring WebFlux

### 5.1. Dependency

Với dự án Spring Boot dùng WebFlux:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

Ví dụ sử dụng **Reactive stack**. Trong dự án có cả Spring MVC và WebFlux starters, Spring Boot có quy tắc lựa chọn web application type; không nên giả định thêm `webflux` là mọi controller đã tự động chạy trong WebFlux.

### 5.2. Cấu hình registration OIDC

Nhóm property của client tương tự Servlet:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: company-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company-oidc:
            issuer-uri: https://id.example.com/realms/customers
~~~

Ý nghĩa:

- `corporate` là `registrationId` nội bộ.
- `client-id` là định danh ứng dụng đã đăng ký tại OP.
- `client-secret` ở backend cần được quản lý như bí mật.
- `scope=openid` yêu cầu OpenID Connect.
- `issuer-uri` xác định OP đáng tin cậy.
- Callback phải được OP chấp nhận và khớp URL public thực tế.

### 5.3. Cấu hình `SecurityWebFilterChain`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/", "/error", "/assets/**").permitAll()
                        .anyExchange().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .oauth2Client(Customizer.withDefaults())
                .build();
    }
}
~~~

Trong WebFlux, chain là `SecurityWebFilterChain` thay vì `SecurityFilterChain` của Servlet.

Spring Security Reactive sử dụng các WebFilter và các repository Reactive tương ứng để xử lý login, Authentication và ngữ cảnh bảo mật. Không tự tạo một Servlet filter để bảo vệ những request đang chạy hoàn toàn trong WebFlux stack.

## 6. Truy cập principal trong WebFlux controller

### 6.1. `@AuthenticationPrincipal OidcUser`

Spring Security hỗ trợ đọc principal đã xác thực bằng annotation trong handler/controller. Ví dụ:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReactiveProfileController {

    @GetMapping("/api/me")
    Mono<Profile> me(@AuthenticationPrincipal OidcUser user) {
        Profile response = new Profile(
                user.getIdToken().getIssuer().toString(),
                user.getIdToken().getSubject(),
                user.getFullName());

        return Mono.just(response);
    }

    record Profile(String issuer, String subject, String name) {}
}
~~~

**Lưu ý:** Handler trả `Mono` nhưng `OidcUser` được Spring Security resolve ở điểm nhập controller từ Authentication hiện tại. Điều đó phù hợp khi principal đã được xác thực và endpoint yêu cầu OIDC Login.

Nếu toàn bộ logic phải diễn ra trong một chuỗi Reactive hoặc service bên dưới cần lấy Authentication, có thể truy cập context theo Reactor như phần sau.

### 6.2. Dùng `ServerWebExchange.getPrincipal()`

WebFlux cung cấp một cách khác để lấy principal từ exchange:

~~~java
import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class ExchangePrincipalController {

    @GetMapping("/api/principal-name")
    Mono<String> principalName(ServerWebExchange exchange) {
        return exchange.getPrincipal()
                .map(Principal::getName)
                .defaultIfEmpty("anonymous");
    }
}
~~~

`ServerWebExchange.getPrincipal()` trả về `Mono<Principal>`. Giá trị `getName()` chỉ là tên theo Authentication implementation; không mặc định là email.

Endpoint minh họa có thể trả `anonymous` khi không có principal. Với API cần xác thực, hãy yêu cầu authentication ở `SecurityWebFilterChain` thay vì dùng chuỗi `anonymous` làm định danh nghiệp vụ.

### 6.3. Controller reactive trả về Authentication chi tiết

Nếu muốn lấy issuer, subject và authorities một cách rõ ràng trong pipeline:

~~~java
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
public class ReactiveIdentityController {

    @GetMapping("/api/identity")
    Mono<IdentityResponse> identity() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .filter(Authentication::isAuthenticated)
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(HttpStatus.UNAUTHORIZED)))
                .flatMap(authentication -> {
                    if (!(authentication.getPrincipal() instanceof OidcUser user)) {
                        return Mono.error(
                                new ResponseStatusException(
                                        HttpStatus.FORBIDDEN,
                                        "OIDC login is required"));
                    }

                    List<String> authorities =
                            authentication.getAuthorities().stream()
                                    .map(GrantedAuthority::getAuthority)
                                    .toList();

                    return Mono.just(new IdentityResponse(
                            user.getIdToken().getIssuer().toString(),
                            user.getIdToken().getSubject(),
                            user.getEmail(),
                            authorities));
                });
    }

    record IdentityResponse(
            String issuer,
            String subject,
            String email,
            List<String> authorities) {}
}
~~~

Ở đây, `ReactiveSecurityContextHolder.getContext()` trả về `Mono<SecurityContext>`. Toàn bộ logic lấy Authentication và xử lý principal được thực hiện trong chuỗi reactive.

Các nhánh lỗi được minh họa để tránh `NullPointerException` khi principal vắng mặt hoặc sai kiểu. Trong hệ thống thật, policy truy cập có thể được đặt ở filter chain và method security để không cần lặp lại các điều kiện này trong mọi controller.

## 7. `ReactiveSecurityContextHolder` hoạt động ra sao?

### 7.1. Reactor Context, không phải biến toàn cục

Reactor Context là tập dữ liệu gắn với **subscriber và chuỗi thực thi reactive**, không phải một map global chia sẻ mọi người dùng.

Spring Security có thể đưa một `Mono<SecurityContext>` vào Reactor Context cho request đã xác thực. Trong code service:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Mono<Authentication> authentication() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication);
}
~~~

Khi publisher này được subscribe **trong chuỗi request có security context**, nó có thể đọc Authentication tương ứng.

Đừng hiểu lời gọi `getContext()` như phép đọc đồng bộ ở thời điểm tạo object. Reactive pipeline có tính lazy: các operator thực thi theo subscription, nên **ngữ cảnh lúc subscription** mới quan trọng.

### 7.2. Tại sao `SecurityContextHolder` không phải lựa chọn chính trong WebFlux?

Một đoạn sai theo mô hình Reactive:

~~~java
return Mono.fromCallable(() ->
        SecurityContextHolder.getContext().getAuthentication()
).map(authentication -> authentication.getName());
~~~

`SecurityContextHolder` thường dựa trên ThreadLocal của Servlet. Trong WebFlux, pipeline có thể chuyển scheduler/thread và không được bảo đảm giữ đúng ThreadLocal Authentication của request.

Việc thử nghiệm trên máy local có thể đôi khi trả kết quả mong muốn, nhưng không nên dựa vào điều đó như một hợp đồng bảo mật. **Dùng `ReactiveSecurityContextHolder` hoặc nhận principal qua WebFlux request abstractions.**

### 7.3. `map` và `flatMap` trong chuỗi principal

Khi chuyển từ Authentication thành giá trị đồng bộ:

~~~java
Mono<String> name =
        ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName);
~~~

Khi cần gọi repository/reactive service:

~~~java
Mono<CustomerProfile> profile =
        ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .flatMap(authentication ->
                        customerProfiles.findByExternalName(
                                authentication.getName()));
~~~

Ở ví dụ thứ hai, `customerProfiles.findByExternalName(...)` là API repository minh họa trả về `Mono<CustomerProfile>`.

**Lưu ý:** ngoài mục tiêu minh họa `flatMap`, trong hệ thống thật không nên dùng `getName()` làm khóa liên kết định danh OIDC khi chưa xác định ngữ nghĩa. Một thiết kế tốt hơn lấy `iss` + `sub` và dùng repository theo cặp đó.

### 7.4. Context theo subscriber và các thay đổi scheduler

Một pipeline Reactor có thể có:

~~~java
return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .publishOn(Schedulers.boundedElastic())
        .map(name -> "Hello, " + name);
~~~

Cần import `reactor.core.scheduler.Schedulers` khi dùng ví dụ trên.

Trong một chuỗi Reactor được xây dựng đúng, Reactor Context được truyền theo quy tắc của publisher/subscriber; đổi scheduler bằng `publishOn` không đồng nghĩa phải chuyển principal sang một static map.

Nhưng khi tự tạo subscription ngoài luồng request, chuyển sang một callback thư viện không tham gia pipeline Reactor, hoặc phá vỡ chuỗi bằng các API ngoài Reactor, **không mặc định context vẫn tồn tại**.

### 7.5. Vì sao tránh gọi `subscribe()` thủ công trong service?

Một mẫu dễ gây lỗi:

~~~java
public void updateSomething() {
    ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .subscribe(auth -> updateDatabase(auth.getName()));
}
~~~

Vấn đề:

- Tạo subscription riêng, làm mất khả năng điều phối kết quả với request gốc.
- Exception có thể không được xử lý cùng flow.
- Context có thể không được truyền như kỳ vọng nếu subscription nằm ngoài chuỗi được Spring Security quản lý.
- Side effect chạy bất đồng bộ, khó theo dõi transactional boundary và authorization.

Nên **trả lại `Mono` hoặc `Flux`** để framework subscribe tại đúng biên xử lý.

Ví dụ thiết kế đúng hơn:

~~~java
public Mono<Void> updateSomething() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .flatMap(auth -> updateDatabaseReactive(auth.getName()));
}
~~~

Trong đó `updateDatabaseReactive(...)` là một phương thức minh họa trả về `Mono<Void>`. Phần logic nghiệp vụ vẫn phải dùng định danh đáng tin cậy và kiểm tra quyền phù hợp.

### 7.6. Không dùng `block()` trong WebFlux request path

Mẫu cần tránh:

~~~java
Authentication auth =
        ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .block();
~~~

`block()` đồng bộ chờ kết quả, có thể cản trở event loop và mất/không có ngữ cảnh subscription như thiết kế. Khi nằm trong request WebFlux non-blocking, hãy **compose pipeline** bằng `map` / `flatMap` / `switchIfEmpty` thay vì ép kết quả đồng bộ.

Nếu thật sự phải gọi thư viện blocking, cần cô lập thao tác theo scheduler phù hợp và đánh giá tác động, nhưng **không biến việc đọc principal thành một lời gọi blocking**.

## 8. Dùng principal trong reactive service để kiểm tra ownership

### 8.1. Bài toán xem đơn hàng của chính người dùng

Giả sử Customer Portal có endpoint:

~~~text
GET /api/orders/{orderId}
~~~

Một người dùng đăng nhập hợp lệ vẫn không được tự xem đơn hàng của người khác bằng cách thay `orderId`.

Tầng service cần biết:

- Issuer của user.
- Subject của user.
- Đơn hàng thuộc chủ thể đó không.
- User có authority/ngữ cảnh nghiệp vụ cần thiết không.

### 8.2. Thiết kế service theo issuer và subject

Ví dụ các abstraction minh họa:

~~~java
public record ExternalIdentity(String issuer, String subject) {}

public record OrderView(String id, String description) {}

public interface OrderLookup {
    Mono<OrderView> findOwnedOrder(
            String orderId, String issuer, String subject);
}
~~~

Ở đây `OrderLookup` là interface ứng dụng giả định, implementation của nó phải kiểm tra ownership tại database hoặc service có thẩm quyền.

Service dùng ReactiveSecurityContextHolder:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@Service
public class OrderService {

    private final OrderLookup orders;

    public OrderService(OrderLookup orders) {
        this.orders = orders;
    }

    public Mono<OrderView> getOwnedOrder(String orderId) {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(HttpStatus.UNAUTHORIZED)))
                .flatMap(authentication -> {
                    if (!(authentication.getPrincipal() instanceof OidcUser user)) {
                        return Mono.error(
                                new ResponseStatusException(HttpStatus.FORBIDDEN));
                    }

                    String issuer = user.getIdToken()
                            .getIssuer().toString();
                    String subject = user.getIdToken().getSubject();

                    return orders.findOwnedOrder(orderId, issuer, subject)
                            .switchIfEmpty(Mono.error(
                                    new ResponseStatusException(
                                            HttpStatus.NOT_FOUND)));
                });
    }
}
~~~

Ý nghĩa:

1. Danh tính được đọc từ Reactive SecurityContext.
2. Service không tin user ID do browser tự gửi như bằng chứng danh tính.
3. Truy vấn ownership dựa trên issuer và subject đáng tin cậy.
4. Nếu không tìm thấy đơn hàng thuộc chủ thể hiện tại, service không trả dữ liệu.
5. Logic này hoạt động trong chuỗi `Mono`, không gọi `block()` hay tạo `subscribe()` riêng.

Trong dự án thật, mapping từ `iss` + `sub` sang account nội bộ có thể được thực hiện ở một lớp identity service chuyên trách. Cần quan tâm đến tenant và quyền thay mặt nếu sản phẩm hỗ trợ đại diện.

### 8.3. Controller trả về publisher của service

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class OrderController {

    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @GetMapping("/api/orders/{orderId}")
    Mono<OrderView> order(@PathVariable String orderId) {
        return service.getOwnedOrder(orderId);
    }
}
~~~

Controller **không tự lấy userId từ query parameter** để thay principal. Nó trả lại pipeline của service cho WebFlux xử lý.

### 8.4. Phương án truyền định danh tường minh

Không phải service nào cũng cần phụ thuộc `ReactiveSecurityContextHolder`. Một lựa chọn khác là controller nhận `OidcUser` và chuyển một DTO bất biến:

~~~java
public record ExternalIdentity(String issuer, String subject) {
    public static ExternalIdentity from(OidcUser user) {
        return new ExternalIdentity(
                user.getIdToken().getIssuer().toString(),
                user.getIdToken().getSubject());
    }
}
~~~

Controller:

~~~java
@GetMapping("/api/orders/{orderId}")
Mono<OrderView> order(
        @PathVariable String orderId,
        @AuthenticationPrincipal OidcUser user) {

    ExternalIdentity identity = ExternalIdentity.from(user);
    return orderService.getOwnedOrder(orderId, identity);
}
~~~

Ở ví dụ này, `getOwnedOrder(String, ExternalIdentity)` là overload hoặc API service khác theo thiết kế ứng dụng. Ưu điểm là danh tính được chuyển vào service rõ ràng, dễ kiểm thử và không buộc domain service phải đọc trực tiếp Reactive SecurityContext.

Tuy nhiên, caller phải là một thành phần tin cậy; service nhạy cảm không nên chấp nhận `ExternalIdentity` tùy ý từ body do người dùng gửi.

## 9. Những khác biệt giữa đọc claims và phân quyền

### 9.1. Claim hồ sơ không phải authority

OIDC ID token có thể có:

~~~json
{
  "sub": "customer-4872",
  "email": "alice@example.com",
  "name": "Alice Nguyen",
  "email_verified": true
}
~~~

Các claim này chủ yếu phục vụ định danh và hồ sơ. Chúng không tự nghĩa là Alice có authority `ROLE_ADMIN` hoặc scope `orders.write`.

Spring Security sử dụng `GrantedAuthority` để biểu diễn authority, nhưng cách ánh xạ claim từ OP sang authority phải được thiết kế cẩn thận.

### 9.2. Xem authorities ở controller

Ví dụ trong reactive pipeline:

~~~java
Mono<List<String>> authorities() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(authentication -> authentication.getAuthorities()
                    .stream()
                    .map(GrantedAuthority::getAuthority)
                    .toList());
}
~~~

Trong Spring Security, tên `SCOPE_orders.read` hoặc `ROLE_ADMIN` chỉ có ý nghĩa khi có cơ chế ánh xạ và chính sách đã được xác định.

OIDC Login không tự đảm bảo mọi role do provider đưa trong claim tùy biến được chuyển thành `ROLE_*` của ứng dụng. Đôi khi cần một authorities mapper hoặc custom OIDC user service phù hợp.

### 9.3. Reactive method security

Spring Security Reactive hỗ trợ bảo vệ method bằng annotation khi được bật.

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
public class ReactiveMethodSecurityConfig {
}
~~~

Ví dụ một service reactive:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import reactor.core.publisher.Mono;

public class ReportsService {

    @PreAuthorize("hasAuthority('SCOPE_reports.read')")
    public Mono<String> report() {
        return Mono.just("Report content");
    }
}
~~~

Ví dụ minh họa cú pháp; để hoạt động thực tế, service phải là Spring-managed bean và authority đó phải được cấp/ánh xạ đúng cho Authentication của request.

Với ứng dụng OIDC Login, cần xác minh cách provider và Spring Security tạo authorities. Không suy luận rằng vì OAuth client yêu cầu scope `reports.read` nên principal chắc chắn có `SCOPE_reports.read` trong mọi cấu hình.

**Phân quyền theo ownership vẫn cần thiết**, kể cả khi user có quyền tổng quát để gọi endpoint.

### 9.4. Khi có nhiều issuer hoặc nhiều tenant

Giả sử hai OP:

~~~text
https://id.example.com/realms/customer
https://id.example.com/realms/partner
~~~

Cả hai có thể phát hành `sub=12345` cho hai chủ thể khác nhau. Nếu service chỉ tra dữ liệu theo `sub`, có nguy cơ truy cập nhầm giữa tenant.

Khóa định danh nghiệp vụ nên ràng buộc issuer/tenant đúng cách. Không coi email, tên hiển thị hay `getName()` là duy nhất toàn hệ thống nếu mô hình định danh không đảm bảo điều đó.

## 10. Truy cập access token để gọi API không đồng nghĩa truy cập principal

Sau OIDC Login, client có thể được cấp access token để truy cập Resource Server. Token này không nằm ở `OidcUser` theo nghĩa “gọi `getIdToken()` để lấy token API”.

Phân biệt:

| Đối tượng | Mục đích |
|---|---|
| `OidcUser` | Chủ thể đã được xác thực theo OIDC |
| `OidcIdToken` | Kết quả xác thực mà RP sử dụng |
| `OAuth2AuthorizedClient` | Trạng thái client đã được cấp access token và có thể refresh token |
| `ReactiveOAuth2AuthorizedClientManager` | Quản lý việc lấy/refresh token theo cơ chế reactive |
| `ServerOAuth2AuthorizedClientExchangeFilterFunction` | Tích hợp OAuth2 access token vào `WebClient` theo ngữ cảnh |

**ID token không phải access token**. Không gửi `OidcUser.getIdToken().getTokenValue()` vào header Bearer của API nghiệp vụ theo thói quen.

### 10.1. `WebClient` có hỗ trợ OAuth2 Client

Ví dụ cấu hình Reactive `WebClient` với các bean do Spring Boot/Spring Security cung cấp:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class OrdersWebClientConfig {

    @Bean
    WebClient ordersWebClient(
            ReactiveClientRegistrationRepository registrations,
            ServerOAuth2AuthorizedClientRepository authorizedClients) {

        ServerOAuth2AuthorizedClientExchangeFilterFunction oauth =
                new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                        registrations, authorizedClients);

        return WebClient.builder()
                .baseUrl("https://orders-api.example.com")
                .apply(oauth.oauth2Configuration())
                .build();
    }
}
~~~

Khi gọi API trong ngữ cảnh request đã xác thực:

~~~java
import static org.springframework.security.oauth2.client.web
        .reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction
        .clientRegistrationId;

public Mono<String> fetchOrders() {
    return ordersWebClient.get()
            .uri("/api/orders")
            .attributes(clientRegistrationId("corporate"))
            .retrieve()
            .bodyToMono(String.class);
}
~~~

`ordersWebClient` là instance `WebClient` được inject vào service. Phần `clientRegistrationId("corporate")` cho biết cấu hình OAuth client cần dùng, còn filter giải quyết authorized client và token theo cơ chế được cấu hình.

Các đoạn code dùng Spring Security Reactive APIs và chỉ minh họa hướng tích hợp. Để dùng trong production, cần xác nhận scope/audience của access token, quản lý refresh/reauthorize, lỗi thiếu authorized client và chính sách sử dụng token của user đang đăng nhập.

Không bật chế độ gắn token mặc định vào **mọi request** tới mọi domain nếu không thực sự cần. Việc gửi access token đến server không đáng tin cậy có thể làm lộ credential.

### 10.2. Principal và authorized client có vòng đời khác nhau

Một user có thể:

- Còn `Authentication` trong WebSession.
- Có ID token của lần OIDC Login trước.
- Có access token đã hết hạn.
- Có refresh token được phép dùng để lấy access token mới.
- Có quyền API vừa bị thay đổi.

Vì vậy, **principal hiện diện không bảo đảm access token hợp lệ cho mọi API**. Token management và API authorization là trách nhiệm riêng.

## 11. Reactive Context khi dùng `flatMap`, `publishOn` và thư viện ngoài

### 11.1. Context lan truyền theo chuỗi Reactor

Một pipeline điển hình:

~~~java
return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .flatMap(authentication ->
                orderService.loadFor(authentication.getName()))
        .map(this::toResponse);
~~~

Trong chuỗi này, dữ liệu security được lấy từ Reactor Context của subscriber. Nếu service trả publisher đúng cách, request pipeline có thể giữ context khi compose các operator.

### 11.2. Đổi scheduler không tự tạo một principal mới

Ví dụ:

~~~java
return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .publishOn(Schedulers.boundedElastic())
        .map(name -> "Current user: " + name);
~~~

Việc dùng `publishOn` ở đây là minh họa. Không cần chuyển toàn bộ ứng dụng WebFlux sang `boundedElastic` chỉ để đọc principal; đọc context không phải thao tác blocking.

Reactor Context có cơ chế lan truyền theo subscriber, không phụ thuộc việc tất cả operator chạy cùng một Java Thread.

### 11.3. Tác vụ được tách khỏi request có thể mất context

Trường hợp thường gây nhầm:

~~~text
HTTP request đã xác thực
  -> Controller tạo Mono
  -> Service tự subscribe bên trong
  -> Task chuyển sang scheduler riêng
  -> Đọc principal không như mong đợi
~~~

Nguyên nhân có thể là subscription mới không được gắn vào subscriber/context của request gốc.

Cách thiết kế thích hợp:

- **Trả publisher** cho upstream subscribe/compose.
- Nếu tạo background job, truyền một DTO định danh đã được xác minh cùng dữ liệu nghiệp vụ cần thiết theo kênh tin cậy.
- Đối với tác vụ độc lập không còn request user, sử dụng service identity hoặc cơ chế ủy quyền phù hợp.
- Không giữ `OidcUser` hoặc `Authentication` trong biến static để “chuyển context”.

### 11.4. Khi dùng CompletableFuture hoặc thư viện callback ngoài Reactor

Không thể mặc định Reactor Context được tự động truyền qua mọi `CompletableFuture`, thread tự tạo hoặc callback không có bridge về Reactor.

Nếu cần tích hợp, bạn phải xác định rõ ranh giới dữ liệu nào đi qua và sử dụng cơ chế context propagation được các thư viện/version hỗ trợ hoặc chuyển **identity bất biến** theo tham số tin cậy.

Một giải pháp dễ kiểm soát cho nghiệp vụ là lấy `ExternalIdentity(issuer, subject)` ở biên request rồi truyền giá trị đó tới các tầng xử lý liên quan.

## 12. WebSession không phải HttpSession

Khi dùng Spring MVC Servlet OIDC Login, session thông dụng là `HttpSession` và `SecurityContextHolder` thường dựa trên ThreadLocal.

Trong WebFlux, request không dùng Servlet API làm abstraction chính. Hệ thống có:

- `WebSession` cho dữ liệu phiên WebFlux khi được sử dụng.
- `ServerSecurityContextRepository` để lưu/khôi phục SecurityContext theo mô hình Reactive.
- `ReactiveSecurityContextHolder` để truy cập context qua Reactor.
- `SecurityWebFilterChain` làm chuỗi bảo vệ request.

Một cấu hình Reactive Login dựa trên session có thể lưu trạng thái đăng nhập theo WebSession, nhưng **không nên dùng `HttpServletRequest.getSession()` trong một handler WebFlux**.

Ngoài ra, session của ứng dụng **khác** với phiên SSO tại OP. Người dùng có thể mất WebSession tại Portal nhưng vẫn được OP xác thực âm thầm khi bắt đầu OIDC Login mới vì browser còn phiên SSO.

## 13. Kiểu principal khác nhau trong ứng dụng hỗn hợp

Một hệ thống có thể hỗ trợ:

1. **WebFlux UI/OIDC Login**: principal thường là `OidcUser`.
2. **Reactive Resource Server với bearer JWT**: Authentication thường là `JwtAuthenticationToken`, principal có thể là `Jwt`.
3. **HTTP Basic hoặc custom authentication**: principal có kiểu khác.
4. **Anonymous request**: không có principal đã được xác thực hoặc dùng anonymous authentication theo cấu hình.

Vì vậy, không nên đưa một controller bắt buộc `OidcUser` lên endpoint có thể được truy cập từ nhiều kiểu đăng nhập mà không định nghĩa cách xử lý.

### 13.1. Đọc subject theo cơ chế xác thực thực tế

Một ví dụ minh họa về nhánh xử lý:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

String subject(Authentication authentication) {
    Object principal = authentication.getPrincipal();

    if (principal instanceof OidcUser oidc) {
        return oidc.getIdToken().getSubject();
    }
    if (authentication instanceof JwtAuthenticationToken jwt) {
        return jwt.getToken().getSubject();
    }
    throw new IllegalArgumentException("Unsupported authentication type");
}
~~~

Đoạn code minh họa cách phân biệt kiểu, **không phải toàn bộ chính sách tin cậy**. Với JWT Resource Server, `sub` phải được xem cùng issuer/audience, loại token và tenant theo token validation đã cấu hình.

Nếu ứng dụng hỗ trợ các nguồn Authentication khác nhau, có thể thiết kế một `CurrentIdentity` nội bộ gồm issuer, subject, tenant và nguồn xác thực. Việc chuyển đổi từ Authentication sang identity phải nằm trong một thành phần được kiểm soát tập trung.

### 13.2. Đăng nhập OIDC và gọi API stateless

Một WebFlux application có thể vừa có UI đăng nhập bằng session, vừa có API nhận bearer token. Nếu tách các chain phù hợp:

- UI OIDC Login xử lý redirect, WebSession và principal `OidcUser`.
- API Resource Server kiểm tra JWT/access token và không nhất thiết dùng WebSession.
- Controller cần được đặt sau chain đúng với phương thức authentication dự kiến.

Không dùng nguyên logic `OidcUser` của UI để chấp nhận ID token như bearer token ở API.

## 14. Lỗi thường gặp khi lấy principal

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| `@AuthenticationPrincipal OidcUser` trả `null` | Request chưa login hoặc principal khác kiểu | Xem filter chain, authentication thực tế và matcher |
| `getName()` không phải email | Principal name attribute khác email | Dùng issuer + subject khi liên kết user |
| Trong WebFlux service đọc `SecurityContextHolder` trống | Context nằm trong Reactor, không phải ThreadLocal hiện tại | Dùng `ReactiveSecurityContextHolder` |
| Trong callback `subscribe()` riêng không thấy context | Tách subscription khỏi request | Compose và trả publisher, không subscribe thủ công |
| `block()` gây lỗi hoặc giảm hiệu năng | Blocking trong WebFlux event loop | Dùng `map`/`flatMap` |
| Có OIDC Login nhưng API trả 401 | API cần access token đúng audience, không chỉ principal | Kiểm tra authorized client và Resource Server |
| Claim email không có | Scope/OP không trả email | Xử lý optional claim; không coi thiếu email là thiếu subject |
| Role trong ID token không trở thành `ROLE_ADMIN` | Không có authority mapping tương ứng | Thiết kế mapper và policy theo provider |
| Hai provider có cùng `sub` dẫn tới nhầm user | Lưu mỗi subject không kèm issuer | Dùng issuer + subject, tenant binding |
| Sau logout vẫn thấy principal ở tab khác | Phiên ứng dụng/SSO có lifecycle khác, browser có request cũ | Xem logout, session và yêu cầu đăng nhập mới |
| Service singleton giữ user của request trước | Lưu Authentication trong field dùng chung | Không giữ principal mutable giữa các request |
| Bắt đầu background job xong principal biến mất | Reactor Context không theo job độc lập | Truyền identity đáng tin cậy hoặc dùng service identity |

Những trường hợp này cần được phân biệt theo request, chain, nguồn Authentication và cách ứng dụng quản lý phiên; không nên “sửa” bằng cách gán principal mặc định cho mọi request.

## 15. Bảo mật và quyền riêng tư khi dùng principal

### 15.1. Trả DTO tối thiểu, không serialize nguyên `OidcUser`

Một OIDC principal có thể chứa ID token, UserInfo, claims và authorities. Không nên trả nguyên object này qua HTTP:

~~~java
// Tránh trả nguyên principal từ API:
@GetMapping("/unsafe-me")
OidcUser unsafeMe(@AuthenticationPrincipal OidcUser user) {
    return user;
}
~~~

Điều này có thể làm lộ dữ liệu hồ sơ hoặc token/metadata không cần thiết.

Tốt hơn là trả DTO chứa những trường màn hình thực sự cần. Ví dụ tên hiển thị, email đã được phép công bố hoặc ID nội bộ không nhạy cảm.

### 15.2. Không ghi ID token và access token vào log

`OidcUser.getIdToken().getTokenValue()` chứa ID token thô. `OAuth2AuthorizedClient.getAccessToken().getTokenValue()` chứa access token.

Đừng ghi các token này vào log, exception message, tracing hoặc response. Nếu cần điều tra, log registration ID, loại Authentication, kết quả kiểm tra và correlation ID không mang giá trị credential.

### 15.3. Không cho frontend tự khai báo principal

Ví dụ request:

~~~http
GET /api/orders
X-User-Id: customer-4872
~~~

Không được coi `X-User-Id` từ browser là bằng chứng xác thực hoặc ownership. Nếu một gateway đáng tin cậy truyền identity qua header, đó là một thiết kế xác thực đặc biệt cần ràng buộc mạng, nguồn gọi, chữ ký hoặc cơ chế xác minh phù hợp; không phải mặc định Spring Security.

Trong hệ thống OAuth/OIDC thông thường, identity đến từ Authentication đã được framework xác lập, không phải một query parameter hoặc header do client tùy ý cung cấp.

### 15.4. Không tự nâng authority từ claim chưa được định nghĩa

Một ID token có thể chứa danh sách nhóm hoặc vai trò theo schema riêng của OP. Chỉ sử dụng các claim đó khi:

- OP/issuer được tin cậy.
- Token đã được kiểm tra đúng mục đích.
- Có mapping được xác định rõ sang quyền của ứng dụng.
- Quyền được giới hạn theo tenant/resource và policy riêng.
- Không cho phép user tự thay đổi claim để tăng quyền.

Authentication và authorization luôn là hai quyết định khác nhau.

### 15.5. Context propagation cũng là vấn đề cách ly người dùng

Nếu một tác vụ nền hoặc static variable vô tình dùng principal của request trước, dữ liệu của người dùng khác có thể bị đọc hoặc sửa.

Vì vậy, khi truyền identity qua chuỗi reactive:

- Giữ context trong phạm vi subscription phù hợp.
- Không lưu context toàn cục.
- Không tự gắn một context không liên quan cho nhiều user.
- Không dùng `contextWrite` để gán một Authentication bất kỳ mà không có nguồn tin cậy.
- Khi kiểm tra ownership, kết hợp issuer/subject với quyền nghiệp vụ.

## 16. Tình huống thực hành

### Tình huống A: trang hồ sơ MVC

**Yêu cầu:** sau OIDC Login, controller Servlet hiển thị tên và subject của người dùng.

**Cách làm:** dùng `@AuthenticationPrincipal OidcUser`, đọc `getFullName()` và `getIdToken().getSubject()`, xử lý trường hợp tên không có.

**Tránh:** dựa vào `principal.getName()` và giả định đó là email.

### Tình huống B: WebFlux lấy đơn hàng thuộc người dùng

**Yêu cầu:** một Reactive service trả đơn hàng theo ID, chỉ khi người gọi là chủ sở hữu.

**Cách làm:** dùng `ReactiveSecurityContextHolder.getContext()` trong `Mono`, lấy issuer/subject từ `OidcUser`, truy vấn repository theo ownership và trả `Mono<OrderView>`.

**Tránh:** gọi `block()` hoặc tin `userId` từ query parameter.

### Tình huống C: chuyển thread khi chạy Reactor

**Yêu cầu:** một flow dùng `publishOn` để chuyển scheduler và vẫn cần biết principal.

**Cách làm:** sử dụng Reactor Context theo pipeline, tránh trông chờ ThreadLocal của Servlet.

**Tránh:** lưu Authentication vào static field để “giữ” principal.

### Tình huống D: service cần gọi API ngoài

**Yêu cầu:** Portal gọi Orders API thay mặt user.

**Cách làm:** dùng `OAuth2AuthorizedClient` / reactive client manager và `WebClient` tích hợp OAuth2 để gửi **access token** đúng audience/scope.

**Tránh:** gửi ID token trong `Authorization: Bearer` đến API.

### Tình huống E: cùng URL hỗ trợ OIDC Login và bearer JWT

**Yêu cầu:** endpoint có thể được truy cập từ browser đã login hoặc service gửi bearer token.

**Cách làm:** thiết kế rõ filter chain, principal conversion và policy. Nếu cần thống nhất identity, tạo abstraction sau khi kiểm tra issuer/audience và kiểu Authentication.

**Tránh:** cast mọi principal sang `OidcUser` hoặc chấp nhận một ID token của RP như bearer access token của API.

### Tình huống F: background job chạy sau request

**Yêu cầu:** user bấm nút yêu cầu tạo báo cáo nền.

**Cách làm:** xác thực/quyền khi nhận yêu cầu, lưu job với issuer/subject hoặc user ID nội bộ đã xác minh và thực hiện job với cơ chế ủy quyền phù hợp.

**Tránh:** giữ `ReactiveSecurityContextHolder` hoặc Authentication trong một job sẽ chạy sau khi request kết thúc mà không có ngữ cảnh bảo mật rõ ràng.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Trong Spring MVC, cách đơn giản để lấy người dùng OIDC ở controller là gì?

**Trả lời:** Dùng `@AuthenticationPrincipal OidcUser` nếu endpoint chỉ dành cho OIDC Login, hoặc nhận `Authentication` để kiểm tra kiểu principal.

**Câu 2.** Vì sao ở WebFlux không nên mặc định dùng `SecurityContextHolder.getContext()` trong mọi `flatMap`?

**Trả lời:** Reactive pipeline không bảo đảm cùng một ThreadLocal trong suốt vòng đời. Spring Security Reactive truyền context qua Reactor subscriber context; dùng `ReactiveSecurityContextHolder`.

**Câu 3.** `ReactiveSecurityContextHolder.getContext()` trả kiểu gì?

**Trả lời:** `Mono<SecurityContext>`. Cần compose nó bằng operator reactive, không ép `block()` trong request path.

**Câu 4.** Nếu `OidcUser.getEmail()` trả null, có nghĩa người dùng chưa đăng nhập không?

**Trả lời:** Không. Claim email có thể không được OP phát hành. Danh tính OIDC nên dựa trên issuer/subject của token đã được xác minh.

**Câu 5.** `Authentication.isAuthenticated()` có đủ cho phép xem đơn hàng bất kỳ không?

**Trả lời:** Không. Phải kiểm tra ownership, tenant và quyền nghiệp vụ.

**Câu 6.** Trong một reactive service, tại sao `subscribe()` thủ công dễ tạo lỗi?

**Trả lời:** Nó tách subscription khỏi flow request, có thể ảnh hưởng context propagation, exception handling và điều phối kết quả. Nên trả `Mono`/`Flux` để upstream compose.

**Câu 7.** Sau OIDC Login, token nào được dùng gọi API nghiệp vụ?

**Trả lời:** Access token dành cho Resource Server, thường được quản lý qua `OAuth2AuthorizedClient`, không phải ID token.

**Câu 8.** Có thể lấy principal từ `ServerWebExchange` không?

**Trả lời:** Có. `exchange.getPrincipal()` trả về `Mono<Principal>`, phù hợp với handler WebFlux.

**Câu 9.** Hai OP phát hành cùng `sub`. Có thể coi đó là cùng tài khoản không?

**Trả lời:** Không. Cần xét issuer và chính sách liên kết tài khoản; thường dùng `iss` + `sub`.

**Câu 10.** Nếu một background job không có request active, có thể tin rằng Reactor SecurityContext của user vẫn có sẵn không?

**Trả lời:** Không. Job phải nhận identity/ủy quyền đã được xác định một cách tin cậy hoặc sử dụng service identity theo yêu cầu.

## Ghi nhớ

- **Principal** mô tả chủ thể đã xác thực; `Authentication` chứa principal và authorities; `SecurityContext` chứa Authentication của ngữ cảnh hiện tại.
- Trong **Spring MVC Servlet**, dùng `@AuthenticationPrincipal`, `Authentication` hoặc `SecurityContextHolder` khi phù hợp.
- Trong **Spring WebFlux**, dùng `@AuthenticationPrincipal` ở controller, `ServerWebExchange.getPrincipal()` hoặc **`ReactiveSecurityContextHolder`** trong `Mono`/`Flux`. SecurityContext thuộc **Reactor Context**, không phải một biến global/thread-local bảo đảm đi theo mọi operator.
- Khi định danh người dùng OIDC, ưu tiên **`iss` + `sub`**; không mặc định tên/email là khóa bền vững hoặc nguồn cấp quyền.
- **Không dùng ID token làm access token** khi gọi API. Sử dụng authorized client và OAuth2-aware WebClient theo scope/audience phù hợp.
- **Không tự subscribe hoặc block trong request reactive**, không chia sẻ principal qua singleton/static và không bỏ kiểm tra ownership/authority chỉ vì người dùng đã đăng nhập.
