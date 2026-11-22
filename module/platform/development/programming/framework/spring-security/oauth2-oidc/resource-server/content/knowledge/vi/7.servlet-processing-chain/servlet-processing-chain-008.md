# SecurityContextHolder và phạm vi danh tính trong một yêu cầu

Trong **Spring Security OAuth 2.0/OIDC Resource Server** chạy trên **Servlet stack** (Spring MVC, `HttpServletRequest`), mỗi HTTP request đi qua một chuỗi bộ lọc bảo mật trước khi tới controller. Khi client gửi access token hợp lệ, Spring Security xác thực token, tạo một đối tượng biểu diễn chủ thể đã xác thực (`Authentication`) rồi đặt nó trong `SecurityContext`. Những phần mã xử lý cùng request có thể lấy thông tin này qua `SecurityContextHolder`.

Điểm mấu chốt: **danh tính “hiện tại” có phạm vi thực thi**, thường gắn với thread đang xử lý request và được dọn khỏi holder khi chuỗi xử lý kết thúc. Nó không phải một biến toàn cục chứa người dùng đăng nhập gần nhất. Nó cũng không mặc nhiên đi theo mọi thread, mọi tác vụ bất đồng bộ, mọi request kế tiếp hoặc mọi lời gọi tới dịch vụ phía sau.

Bài này giải thích cấu trúc của `SecurityContextHolder`, cách Spring Security thiết lập và xóa ngữ cảnh trong Servlet filter chain, phương pháp sử dụng principal của JWT/opaque token ở controller và service, và ranh giới danh tính với session, async, error dispatch, executor và microservice.

## 1. Ba thành phần khác nhau: Holder, Context và Authentication

### 1.1. SecurityContextHolder: điểm truy cập thông tin bảo mật hiện tại

`SecurityContextHolder` là API trung tâm giúp mã Java lấy `SecurityContext`:

```java
import org.springframework.security.core.context.SecurityContextHolder;

var securityContext = SecurityContextHolder.getContext();
```

Trong ứng dụng Servlet, mặc định `SecurityContextHolder` sử dụng một `SecurityContextHolderStrategy` dựa trên **`ThreadLocal`**. Vì vậy, khi request đã được xử lý qua các filter xác thực, code trong cùng thread có thể đọc thông tin bảo mật mà không cần chuyền trực tiếp một tham số `Authentication` qua mọi phương thức.

Các method của `SecurityContextHolder` là static, nhưng điều đó **không có nghĩa mọi request dùng chung một Authentication toàn JVM**. Static API chuyển tiếp việc truy cập đến một strategy; strategy mặc định giữ context theo thread.

### 1.2. SecurityContext: một ngữ cảnh có thể chứa Authentication

`SecurityContext` biểu diễn ngữ cảnh bảo mật, trong đó phần quan trọng nhất là:

```java
Authentication authentication = securityContext.getAuthentication();
```

Không phải mọi context đều đã có principal được xác thực. Ví dụ, lúc chưa có bearer token, trước khi filter xác thực, trong một thread nền chưa được truyền ngữ cảnh, `getAuthentication()` có thể trả về `null`.

### 1.3. Authentication: principal và các quyền đã được xác thực

`Authentication` có thể biểu diễn credential đầu vào chưa được xác thực hoặc kết quả xác thực thành công. Với **kết quả xác thực** trong Resource Server, các thành phần thường gặp:

| API | Ý nghĩa | Trong Resource Server |
|---|---|---|
| `getPrincipal()` | Chủ thể được biểu diễn | Thường là `Jwt` (JWT) hoặc `OAuth2AuthenticatedPrincipal` (opaque token) |
| `getName()` | Tên principal do authentication converter cung cấp | Với JWT mặc định thường dựa vào claim `sub`; có thể tùy biến |
| `getAuthorities()` | Các `GrantedAuthority` | Scope thường ánh xạ thành `SCOPE_orders.read`, `SCOPE_orders.write` |
| `isAuthenticated()` | Trạng thái của đối tượng Authentication | Không dùng boolean này một mình để khẳng định có end-user đã xác thực |
| `getCredentials()` | Credential liên quan | Có thể bị loại bỏ sau xác thực; không ghi vào log |
| `getDetails()` | Thông tin phụ thuộc cơ chế xác thực | Không tự coi metadata do client gửi là bằng chứng danh tính |

```mermaid
flowchart TB
  H["SecurityContextHolder<br/>API lấy context hiện tại"] --> C["SecurityContext"]
  C --> A["Authentication"]
  A --> P["principal<br/>Jwt / OAuth2AuthenticatedPrincipal"]
  A --> N["name"]
  A --> G["authorities<br/>SCOPE_..."]
  A --> D["details / credentials"]
```

**Chủ thể đã xác thực** (`authentication`) và **quyền trên tài nguyên cụ thể** (`authorization`) là hai câu hỏi độc lập. Người dùng có `SCOPE_orders.read` không tự động được xem đơn hàng của người dùng khác.

## 2. SecurityContext xuất hiện thế nào trong Servlet filter chain?

HTTP request đi từ Servlet container qua `DelegatingFilterProxy` đến `FilterChainProxy`. Spring Security chọn `SecurityFilterChain` phù hợp với request. Trong cấu hình Resource Server, các filter xử lý context, bearer credential, authentication và authorization trước khi request tới `DispatcherServlet`.

```mermaid
sequenceDiagram
    autonumber
    participant C as HTTP Client
    participant F as Servlet Security Filters
    participant H as SecurityContextHolder
    participant M as AuthenticationManager
    participant MVC as Controller / Service
    C->>F: GET /api/orders + Bearer token
    F->>H: Nạp hoặc chuẩn bị context cho request
    F->>M: Xác thực credential trích xuất từ request
    M-->>F: Authentication đã xác thực
    F->>H: Đặt Authentication vào context
    F->>MVC: Tiếp tục filter chain + authorization
    MVC->>H: Đọc principal, authorities
    H-->>MVC: Authentication của phạm vi hiện tại
    MVC-->>F: HTTP response
    F->>H: Dọn SecurityContextHolder
    F-->>C: HTTP response
```

Những thành phần cần nhận diện:

| Thành phần | Vai trò |
|---|---|
| `FilterChainProxy` | Chọn chuỗi filter khớp request và quản lý luồng filter |
| `SecurityContextHolderFilter` | Nạp/thiết lập context qua `SecurityContextRepository` cho phạm vi xử lý; dọn sau khi kết thúc |
| `BearerTokenAuthenticationFilter` | Lấy Bearer token, đưa tới `AuthenticationManager` và thiết lập Authentication khi thành công |
| `AnonymousAuthenticationFilter` | Có thể tạo anonymous Authentication nếu chưa có người gọi đã xác thực |
| `ExceptionTranslationFilter` | Dịch lỗi xác thực/phân quyền thành entry point hoặc phản hồi phù hợp |
| `AuthorizationFilter` | Đánh giá quy tắc bảo vệ URL theo Authentication hiện tại |
| `DispatcherServlet` | Gọi controller/service sau các bước filter cần thiết |

Bảng nói về vai trò, không phải thứ tự filter chính xác của mọi phiên bản và mọi cấu hình. Các filter tham gia và thứ tự có thể thay đổi theo `SecurityFilterChain` của ứng dụng.

### 2.1. Khi token là JWT

Ví dụ client gửi:

```http
GET /api/orders/ord-123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

Luồng điển hình:

1. `BearerTokenResolver` đọc bearer credential từ `HttpServletRequest`.
2. `BearerTokenAuthenticationFilter` tạo `BearerTokenAuthenticationToken`.
3. `AuthenticationManager` gọi provider JWT, thường là `JwtAuthenticationProvider` với `JwtDecoder`.
4. Decoder kiểm tra chữ ký, thuật toán/khóa phù hợp, thời hạn, issuer và audience theo những validator API cấu hình.
5. Kết quả thành công thường là `JwtAuthenticationToken`, principal là một `Jwt` đã xác thực.
6. Spring Security thiết lập context chứa Authentication, rồi HTTP authorization, controller và service đọc thông tin đã được kiểm chứng.
7. Context được dọn khỏi holder sau phạm vi xử lý thích hợp, tránh rò rỉ sang yêu cầu khác.

`SecurityContextHolder` **không giải mã hay xác minh chữ ký JWT**. Nó chỉ cung cấp context sau khi cơ chế xác thực đã đưa kết quả vào đó.

### 2.2. Khi token được kiểm tra bằng introspection

Với cấu hình opaque token:

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults()))
```

Provider gọi `OpaqueTokenIntrospector` để xác thực token. Authentication được lưu trong context thường là `BearerTokenAuthentication`, với principal kiểu `OAuth2AuthenticatedPrincipal` chứa thuộc tính được xác thực. Điều này có nghĩa ứng dụng dùng cả hai chế độ **không nên ép mọi `authentication.getPrincipal()` thành `Jwt`**.

### 2.3. Khi token không hợp lệ hoặc vắng mặt

Token hết hạn, sai chữ ký, sai issuer, sai audience (nếu có validator) hoặc không active qua introspection bị từ chối ở bước authentication; thông thường HTTP **401** và `WWW-Authenticate: Bearer` sẽ hướng dẫn client.

Nếu request không có bearer credential, filter có thể đi tiếp; route `permitAll()` vẫn chạy, còn route `authenticated()` cần một cơ chế xác thực phù hợp. Một context của request public có thể chứa `AnonymousAuthenticationToken`. Đó không phải người dùng đã được xác thực bằng access token.

## 3. Phạm vi theo thread và cách tránh lẫn danh tính giữa request

Trong Servlet đồng bộ thông thường, có thể hình dung:

```text
Servlet Thread A                         Servlet Thread B
  Request của user-842                    Request của user-901
  ThreadLocal context A                   ThreadLocal context B
  Authentication(user-842)                Authentication(user-901)
          |                                       |
  Controller A                              Controller B
  Service A                                 Service B
```

Hai request có thể xử lý đồng thời. Trong thread A:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
```

trả về Authentication tương ứng với context được thiết lập cho **thread A**. Thread B có context riêng. Đây là lý do các service đồng bộ có thể đọc danh tính hiện tại mà không phải truyền qua mọi tầng.

### 3.1. Vì sao cleanup là điều kiện bắt buộc?

Servlet container thường sử dụng **thread pool**. Cùng một thread có thể xử lý nhiều request theo thời gian:

```text
T1: Thread-17 -> request user-842 -> context user-842
    Kết thúc request -> xóa context khỏi Thread-17

T2: Thread-17 -> request user-901 -> context user-901
    Kết thúc request -> xóa context khỏi Thread-17
```

Nếu ai đó đặt Authentication vào một `ThreadLocal` riêng hoặc tự chỉnh context rồi không cleanup, request sau có thể **nhìn thấy danh tính/quyền của request trước**. Spring Security quản lý việc dọn `SecurityContextHolder` trong filter chain tiêu chuẩn. Tránh tự lắp thêm một vùng lưu principal theo thread rồi bỏ qua vòng đời đó.

### 3.2. Các strategy của SecurityContextHolder

| Strategy | Cách lưu | Đánh giá trong web server |
|---|---|---|
| `MODE_THREADLOCAL` | Mỗi thread có context riêng | Mặc định phù hợp cho Servlet filter chain |
| `MODE_INHERITABLETHREADLOCAL` | Thread con mới có thể kế thừa context của thread cha | Không nên bật rộng để “sửa” async; khó kiểm soát với thread pool |
| `MODE_GLOBAL` | Một context dùng chung trên JVM | Không phù hợp với nhiều request/người dùng |

`MODE_GLOBAL` có nguy cơ trộn danh tính của các request khác nhau. `MODE_INHERITABLETHREADLOCAL` không bảo đảm task chạy trên executor được truyền đúng principal: thread pool có thể được tạo trước request, hoặc tồn tại lâu và tái sử dụng. Khi cần truyền danh tính qua async, hãy dùng cơ chế rõ ràng.

### 3.3. “Một request = một thread” chỉ là mô hình đơn giản

Servlet có thể xử lý request qua các dispatch kiểu `REQUEST`, `ASYNC`, `ERROR`; thread thực thi có thể thay đổi. Một thread cũng có thể chạy mã không liên quan đến HTTP request. Do đó cần hiểu:

- **Trong thread đã được thiết lập context:** code có thể đọc Authentication hiện tại.
- **Trong thread mới/executor:** không mặc định có cùng context.
- **Trong nhiều Servlet dispatch:** có thể cần nạp lại context tùy repository và bộ lọc được áp dụng.
- **Sau response/request:** không được giả định context của request trước vẫn tồn tại trên thread.

## 4. Đọc Authentication đã xác thực trong Spring MVC

Spring Security và Spring MVC hỗ trợ lấy principal theo nhiều cách. Tùy nhu cầu, nên chọn phương pháp ít phụ thuộc nhất vào token format.

### 4.1. Nhận Authentication trực tiếp trong controller

```java
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {

    @GetMapping("/api/me")
    public Map<String, Object> me(Authentication authentication) {
        return Map.of(
            "principal", authentication.getName(),
            "authorities", authentication.getAuthorities().stream()
                .map(authority -> authority.getAuthority())
                .toList()
        );
    }
}
```

Ví dụ giả định `/api/me` đã được bảo vệ và có Authentication phù hợp. Trong sản phẩm thật, chỉ trả về các thông tin identity/authority thực sự cần cho client; **không trả token raw, credential hoặc mọi claim một cách tùy tiện**.

Nhận `Authentication` hữu ích khi controller chỉ cần tên/authorities, hoặc khi ứng dụng có thể chấp nhận cả JWT và opaque token.

### 4.2. Nhận JWT đã xác thực bằng @AuthenticationPrincipal

Ở một route dùng JWT Resource Server, principal của `JwtAuthenticationToken` thông thường là `Jwt`:

```java
import java.util.List;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/api/orders/mine")
    public List<OrderDto> myOrders(@AuthenticationPrincipal Jwt jwt) {
        String issuer = jwt.getIssuer().toString();
        String subject = jwt.getSubject();
        String tenantId = jwt.getClaimAsString("tenant_id");

        return orderService.findVisibleOrders(issuer, subject, tenantId);
    }
}
```

`OrderService` và `OrderDto` là các thành phần nghiệp vụ tự định nghĩa. JWT trong ví dụ đến từ **Spring Security sau khi đã xác thực**, không phải payload do controller tự Base64 decode. Nếu chấp nhận nhiều issuer, danh tính toàn hệ thống thường cần cặp `issuer + subject` hoặc một định danh nội bộ đã liên kết đúng.

Claim như `tenant_id` phải được IdP/API thống nhất về ý nghĩa. Sau khi xác thực token, ứng dụng vẫn cần đối chiếu tenant với bản ghi được truy cập.

### 4.3. Nhận principal của opaque token

```java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OpaqueIdentityController {

    @GetMapping("/api/opaque/me")
    public String me(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
        return principal.getName();
    }
}
```

Ví dụ này yêu cầu route đi qua opaque Resource Server chain và introspector tạo principal tương ứng. Không ép sang `Jwt` nếu ứng dụng đang dùng `BearerTokenAuthentication`.

### 4.4. Dùng @CurrentSecurityContext

```java
@GetMapping("/api/identity")
public String identity(
        @CurrentSecurityContext(expression = "authentication")
        Authentication authentication) {
    return authentication.getName();
}
```

Annotation `@CurrentSecurityContext` thuộc `org.springframework.security.core.annotation`; cho phép Spring MVC lấy context hoặc phần thuộc tính được chỉ định. Trong controller, cũng có thể lấy toàn bộ `Authentication` trực tiếp như ví dụ trước.

### 4.5. Đọc context trong service nếu thực sự cần

```java
import java.util.Optional;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

@Component
public class CurrentPrincipal {

    public Optional<Authentication> authenticated() {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();

        if (auth == null || auth instanceof AnonymousAuthenticationToken
                || !auth.isAuthenticated()) {
            return Optional.empty();
        }
        return Optional.of(auth);
    }
}
```

`AnonymousAuthenticationToken` có thể trả `isAuthenticated() == true`. Vì thế **chỉ kiểm tra boolean này chưa đủ để xác nhận request có bearer principal hợp lệ**. Khi dùng trực tiếp API, cần phân biệt anonymous hoặc sử dụng `AuthenticationTrustResolver` phù hợp. Ở tầng HTTP/method security, nên ưu tiên `authenticated()` và các authorization expression chuẩn.

Đọc holder sâu trong mọi repository/service khiến logic phụ thuộc ngầm vào thread. Một cách dễ kiểm thử và dễ dùng với async hơn là biến principal đã xác thực thành một **đối tượng actor nhỏ, bất biến**, rồi truyền qua tham số hàm nghiệp vụ.

## 5. Phạm vi danh tính trong tầng nghiệp vụ: CurrentActor

Giả sử bearer JWT đã được kiểm chứng:

```json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "tenant-a"
}
```

Cần phân biệt:

1. JWT hợp lệ về chữ ký/issuer/audience/thời gian và có authority cho thao tác **đọc đơn hàng**.
2. Chủ thể có quyền **đọc đúng đơn hàng ORD-123** hay không.

Mẫu dùng Java 17+:

```java
public record CurrentActor(
    String issuer,
    String subject,
    String tenantId
) {}
```

```java
@GetMapping("/api/orders/{orderId}")
public OrderDto readOrder(
        @PathVariable String orderId,
        @AuthenticationPrincipal Jwt jwt) {

    CurrentActor actor = new CurrentActor(
        jwt.getIssuer().toString(),
        jwt.getSubject(),
        jwt.getClaimAsString("tenant_id")
    );

    return orderService.readVisibleTo(actor, orderId);
}
```

Ví dụ kiểm tra policy ở tầng service:

```java
public OrderDto readVisibleTo(CurrentActor actor, String orderId) {
    Order order = repository.findById(orderId)
        .orElseThrow(OrderNotFoundException::new);

    boolean ownerMatches =
        order.getOwnerIssuer().equals(actor.issuer()) &&
        order.getOwnerSubject().equals(actor.subject());

    boolean tenantMatches =
        order.getTenantId().equals(actor.tenantId());

    if (!ownerMatches || !tenantMatches) {
        throw new AccessDeniedException("Order access denied");
    }
    return mapper.toDto(order);
}
```

Các class như `Order`, `OrderDto`, `OrderNotFoundException` và `repository` là ví dụ thuộc dự án riêng. Chính sách thật có thể cho phép người dùng quản trị truy cập trong tenant, cần kiểm tra trạng thái đơn và liên kết payment/customer. **Scope ở SecurityContext là đầu vào cho authorization, không phải giấy phép bỏ qua kiểm tra đối tượng.**

Truyền `CurrentActor` có lợi vì:

- Service biết rõ **ai đang yêu cầu** từ tham số, không phải đọc một trạng thái thread ngầm.
- Không cần giữ nguyên bearer token trong logic nghiệp vụ chỉ để biết `sub`.
- Có thể truyền dữ liệu actor tối thiểu vào tác vụ async theo chính sách rõ ràng.
- Unit test nghiệp vụ không cần giả lập cả filter chain hoặc SecurityContextHolder.

Actor chỉ là dữ liệu nội bộ đã được controller xây dựng từ Authentication tin cậy. Nếu client từ bên ngoài gửi JSON `{"subject":"user-842"}`, JSON đó **không tự trở thành chứng cứ xác thực**.

## 6. Cấu hình Resource Server stateless và SecurityContext

Một ví dụ Servlet REST API nhận bearer JWT từ header:

```yaml
# application.yml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          audiences:
            - orders-api
```

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ResourceServerSecurityConfig {

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            // Chỉ thích hợp cho API dùng Bearer header,
            // không dùng cookie/session làm credential cho thao tác ghi.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Trong cấu hình này:

- `oauth2ResourceServer().jwt()` bật filter/provider xác thực bearer JWT.
- `issuer-uri` khai báo nhà phát hành đáng tin; `audiences` yêu cầu token được phát hành cho API theo thuộc tính Boot phiên bản phù hợp.
- Scope JWT được ánh xạ thành authority, thường có tiền tố `SCOPE_`.
- `SessionCreationPolicy.STATELESS` yêu cầu Spring Security **không tạo hoặc sử dụng HttpSession để lấy SecurityContext cho các request**.
- `csrf().disable()` là lựa chọn cho API chỉ dùng credential do client gửi rõ ràng qua bearer header; nếu ứng dụng có xác thực dựa trên cookie, cần giữ biện pháp CSRF phù hợp.

Resource Server phải có validator audience phù hợp; chỉ cấu hình issuer không đồng nghĩa API tự kiểm tra đúng audience trong mọi phiên bản/cách tự tạo decoder.

### 6.1. Mỗi request vẫn cần credential trong mô hình stateless

```text
Request 1:
  GET /api/orders/123
  Authorization: Bearer TOKEN_USER_842
  -> Xác thực user-842
  -> SecurityContextHolder chứa user-842 trong phạm vi request
  -> Kết thúc, context được dọn

Request 2:
  GET /api/orders/124
  Không có Authorization
  -> Không tự kế thừa identity của Request 1
```

Đây là hành vi mong muốn. Spring Security có thể tạo/nạp một context mới ở request tiếp theo; bearer auth không yêu cầu giữ nguyên Java object SecurityContext qua nhiều HTTP request.

## 7. SecurityContextHolder, SecurityContextRepository và HttpSession khác nhau

Ba tầng thường bị nhầm:

| Thành phần | Câu hỏi trả lời | Phạm vi |
|---|---|---|
| `SecurityContextHolder` | Thread đang chạy lấy context từ đâu? | Thường thread hiện tại |
| `SecurityContextRepository` | Context được nạp và lưu từ nơi nào? | Tùy repository, theo request/dispatch hoặc session |
| `HttpSession` | Server lưu trạng thái HTTP nào qua nhiều request? | Có thể tồn tại qua nhiều request |

Các repository quan trọng:

- `RequestAttributeSecurityContextRepository` lưu context trong **request attribute** để xử lý nhiều Servlet dispatch của **cùng request**.
- `HttpSessionSecurityContextRepository` có thể duy trì context qua `HttpSession` khi ứng dụng sử dụng cơ chế stateful phù hợp.
- `NullSecurityContextRepository` không duy trì SecurityContext vào nơi lưu bền giữa request.
- `DelegatingSecurityContextRepository` phối hợp nhiều repository theo cấu hình.

### 7.1. SecurityContextHolderFilter trong Spring Security 6

Ở Spring Security 6, mô hình mặc định **explicit save** sử dụng `SecurityContextHolderFilter`. Filter này chuẩn bị context từ `SecurityContextRepository` cho quá trình xử lý và dọn context ở cuối. Khi muốn giữ context trong repository cho request khác, cơ chế xác thực hoặc mã quản lý phải **lưu một cách tường minh**.

Spring Security 5 trước đây thường sử dụng `SecurityContextPersistenceFilter` với mô hình tự lưu context thay đổi vào repository. Không lấy cách làm ở bản cũ rồi suy ra mọi thay đổi của context sẽ tự được lưu ở Spring Security 6.

`BearerTokenAuthenticationFilter` có thể dùng repository phục vụ phạm vi request/dispatch tùy cấu hình. Điều đó **không đồng nghĩa bearer authentication sẽ tự được lưu vào session đăng nhập lâu dài**.

### 7.2. Error dispatch trong cùng HTTP request

```text
REQUEST dispatch
    |
    +-- Xác thực user-842
    |
    +-- Controller phát sinh lỗi
    |
ERROR dispatch
    |
    +-- Render trang/xử lý lỗi của cùng request
```

Tùy Servlet container và filter setup, context trên thread của dispatch ban đầu có thể đã được dọn trước khi error dispatch bắt đầu. `RequestAttributeSecurityContextRepository` được thiết kế để có thể lấy lại context của **cùng request** trong các dispatch phù hợp. Nó **không phải** session chia sẻ identity giữa nhiều HTTP request.

Nếu error handler cần biết principal, phải xử lý trường hợp Authentication null/anonymous và giới hạn dữ liệu trả ra. Không hiển thị toàn bộ JWT hoặc claims nhạy cảm trong trang lỗi.

### 7.3. Vì sao không tự ghi context vào session?

Đừng tự tạo một phiên đăng nhập bằng:

```java
request.getSession().setAttribute(
    "SPRING_SECURITY_CONTEXT",
    SecurityContextHolder.getContext()
);
```

Trong API bearer stateless, cách này có thể thay đổi bất ngờ hợp đồng “mỗi request xác thực bằng token” và tạo trạng thái không cần thiết. Nếu sản phẩm cần đăng nhập bằng session/cookie, hãy thiết kế cơ chế session authentication và repository phù hợp, không tự nhét SecurityContext vào session.

## 8. Anonymous Authentication và câu hỏi “đã đăng nhập chưa?”

Ở route `permitAll()`, Spring Security có thể thiết lập `AnonymousAuthenticationToken`, hoặc có thể chưa có Authentication nếu không bật/filter tương ứng. `AnonymousAuthenticationToken` dùng để biểu diễn guest, **không phải** bearer principal đã được xác thực.

Đoạn sau chưa đủ an toàn:

```java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();

if (auth != null && auth.isAuthenticated()) {
    // Chưa thể kết luận đây là người dùng thực sự đã xác thực.
}
```

Vì AnonymousAuthenticationToken có thể trả `true` cho `isAuthenticated()`, hãy sử dụng các rule và resolver phân loại của Spring Security:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll())
```

Nếu cần phân quyền theo scope:

```java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public OrderDto readOrder(String orderId) {
    // ...
}
```

Cần bật method security (ví dụ `@EnableMethodSecurity`) để `@PreAuthorize` có hiệu lực.

Một điểm nữa: access token Client Credentials có thể biểu diễn **service principal**, không phải một người dùng tương tác. `authentication.getName()` không mặc định là email/username và có thể thay đổi theo converter, grant type và hợp đồng issuer. Không suy ra “đang đăng nhập bằng mật khẩu” chỉ từ sự hiện diện của Authentication.

## 9. Ranh giới async: thread khác không tự có context hiện tại

`SecurityContextHolder` mặc định dựa vào `ThreadLocal`. Một task được gửi tới executor có thể chạy trên thread khác với thread Servlet:

```mermaid
sequenceDiagram
    participant R as Servlet Thread
    participant H as SecurityContextHolder
    participant W as Worker Thread
    R->>H: Context(user-842) trong request
    R->>W: submit(task)
    Note over W: ThreadLocal riêng
    W->>H: getContext()
    H-->>W: Không mặc định có user-842
    R->>H: Context của request được dọn
```

Ví dụ dễ gặp:

```java
@GetMapping("/api/start")
public String start() {
    CompletableFuture.runAsync(() -> {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
        // Không thể giả định auth là principal của request gọi start().
        performTask(auth);
    });
    return "accepted";
}
```

`CompletableFuture.runAsync` thường chạy trên executor khác. Java không tự mang `ThreadLocal` của request sang thread đang thực thi task.

### 9.1. Cách đơn giản: truyền dữ liệu actor đã xác thực

Nếu task chỉ cần biết issuer/subject/tenant đã xác thực, truyền `CurrentActor`:

```java
@PostMapping("/api/reports")
public ResponseEntity<Void> createReport(
        @AuthenticationPrincipal Jwt jwt) {

    CurrentActor actor = new CurrentActor(
        jwt.getIssuer().toString(),
        jwt.getSubject(),
        jwt.getClaimAsString("tenant_id")
    );

    reportService.enqueueReport(actor);
    return ResponseEntity.accepted().build();
}
```

`enqueueReport` là API nghiệp vụ do ứng dụng tự định nghĩa. Tác vụ chạy sau cần đánh giá lại quyền hiện tại nếu nghiệp vụ yêu cầu, vì token và quyền có thể thay đổi sau khi request kết thúc. Actor đã chụp không phải quyền sử dụng vô thời hạn.

Khi gửi job vào queue/message broker, tránh lưu bearer token của người dùng trong message dài hạn. Dùng thông tin actor tối thiểu và một mô hình credential/ủy quyền của worker theo hợp đồng.

### 9.2. Khi thực sự cần SecurityContext trong thread khác

Spring Security cung cấp các wrapper concurrency:

- `DelegatingSecurityContextRunnable`
- `DelegatingSecurityContextCallable`
- `DelegatingSecurityContextExecutor`
- `DelegatingSecurityContextAsyncTaskExecutor`

Các wrapper đưa context tới thread thực thi rồi khôi phục/dọn context theo vòng đời task. Ví dụ:

```java
import java.util.concurrent.Executor;
import org.springframework.security.concurrent.DelegatingSecurityContextExecutor;

// delegate là một Executor được quản lý vòng đời bởi ứng dụng.
Executor securedExecutor =
    new DelegatingSecurityContextExecutor(delegate);

// Gửi task khi request đang có Authentication đã được xác thực.
securedExecutor.execute(() -> {
    Authentication current =
        SecurityContextHolder.getContext().getAuthentication();
    processInCurrentContext(current);
});
```

`delegate` và `processInCurrentContext` là thành phần do ứng dụng định nghĩa. Với constructor nhận một executor, wrapper dùng context hiện có tại thời điểm submit task. Có biến thể nhận context cụ thể khi thực sự muốn chạy với system identity được quản trị.

Kể cả khi đã truyền context cần cân nhắc:

1. Task có thể thực hiện sau khi token gốc hết hạn hoặc quyền đã thay đổi.
2. SecurityContext có thể chứa dữ liệu credential/token nhạy cảm; không serialize vào queue/log.
3. Tránh sửa context được chia sẻ giữa nhiều task vì race condition.
4. DelegatingSecurityContext chỉ quản lý context **trong process**, không cấp OAuth token cho dịch vụ phía sau.

Với `@Async`, có thể dùng `DelegatingSecurityContextAsyncTaskExecutor` bọc executor được quản lý để truyền context tại thời điểm gọi. Không nên bật `MODE_INHERITABLETHREADLOCAL` toàn cục để giải quyết lỗi trên thread pool.

### 9.3. Spring MVC Callable và DeferredResult khác nhau

Spring Security tích hợp với Spring MVC async. Với controller trả về `Callable<T>`, framework có thể dùng `WebAsyncManagerIntegrationFilter` để đặt context phù hợp khi chạy Callable:

```java
@GetMapping("/api/slow")
public Callable<String> slow() {
    return () -> {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
        return "processed for " + auth.getName();
    };
}
```

Ví dụ giả định route được bảo vệ và dùng Spring MVC Callable chuẩn. Không suy rộng điều đó sang mọi coroutine, `CompletableFuture` hoặc thread tự tạo.

Với `DeferredResult`, phần xử lý kết quả do ứng dụng/executor điều khiển; Spring Security **không tự động có một cơ chế lan truyền SecurityContext cho tất cả task DeferredResult**. Nếu cần danh tính trong thread hoàn thành response, truyền actor hoặc dùng wrapper concurrency.

### 9.4. Scheduled job không có HTTP principal

Một `@Scheduled` job không đi qua Servlet filter chain của user:

```java
@Scheduled(fixedDelayString = "PT5M")
public void reconcile() {
    Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();
    // Không mặc định có Authentication của end-user nào.
}
```

Job nền thường nên có service identity và chính sách quyền riêng, ví dụ client credentials khi gọi API từ xa, thay vì giả lập một người dùng tùy ý trong holder.

## 10. Một HTTP request đi qua microservice khác: không chuyển context của JVM

`SecurityContextHolder` tồn tại **trong process Java của ứng dụng hiện tại**. Khi Orders API gọi Payments API:

```text
Browser
  |
  | Authorization: Bearer token-A (aud=orders-api)
  v
Orders API
  | SecurityContextHolder -> Authentication(user-842)
  |
  | HTTP call
  v
Payments API
    SecurityContextHolder -> context riêng từ credential đến Payments API
```

Payments API không thể đọc holder trong JVM của Orders API. Nó phải xác thực credential của request riêng:

| Phương án | Khi phù hợp | Identity ở API đích |
|---|---|---|
| Relay token | Token đầu vào **đã được cấp cho API đích** và policy hai bên cho phép | API đích xác thực lại token và tự tạo context |
| Token exchange/on-behalf-of | Cần token mới dành cho audience của API đích, gắn với delegation của người dùng | API đích xác thực token mới |
| Client credentials | Lời gọi theo danh tính service | Authentication của service principal, không mặc định là end-user |

Không relay token `aud=orders-api` sang `payments-api` nếu Payments API không thuộc audience hợp lệ. Không gửi nguyên Java `SecurityContext` hoặc `Authentication` qua HTTP và coi đó là credential. Header `X-User-Id` tự đặt cũng không chứng minh danh tính nếu bên nhận không có một hợp đồng trust được thực thi.

## 11. SecurityContextHolder khác RequestContextHolder, MDC và tracing

Các dạng dữ liệu “theo request” không thể thay nhau:

| Thành phần | Mục tiêu | Có mặc định chứng minh principal đã xác thực? |
|---|---|---|
| `SecurityContextHolder` | Truy cập Authentication được framework thiết lập | Có, nếu context được lập bởi cơ chế xác thực tin cậy và không bị can thiệp |
| `HttpServletRequest` attribute | Chia sẻ dữ liệu trong request hoặc dispatch | Không |
| `RequestContextHolder` | Truy cập request attributes theo thread | Không |
| MDC logging | Gắn request id/user id để quan sát | Không |
| Trace/span context | Theo dõi đường đi giữa dịch vụ | Không |
| `HttpSession` | Lưu dữ liệu phiên | Chỉ có giá trị bảo mật khi có hợp đồng/session authentication phù hợp |

Ví dụ MDC có `userId` phục vụ tìm log, nhưng giá trị đó không nên được dùng để cho phép rút tiền/đọc đơn hàng. MDC cũng có vòng đời/thread handling riêng; đặt nhầm giá trị và quên cleanup có thể gây trộn log giữa request.

## 12. Khi nào chủ động thiết lập SecurityContext bằng tay?

Với Resource Server chuẩn, filter của Spring Security thiết lập Authentication sau khi xác thực bearer token. Controller/service **không cần** tự xây context.

Trong integration test hoặc một authentication mechanism thật sự tùy biến, code có thể cần tạo context bằng tay:

```java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authenticationFromTrustedMechanism);
SecurityContextHolder.setContext(context);
```

Điều kiện quan trọng: `authenticationFromTrustedMechanism` là kết quả của một cơ chế xác thực thật sự hoặc system principal được quản trị. **Không** chuyển trực tiếp `X-User-Id` do client đặt thành một Authentication “đã xác thực”.

Spring Security khuyên **tạo context mới** khi thay đổi Authentication, thay vì sửa trực tiếp đối tượng có thể được chia sẻ:

```java
// Cẩn thận vì có thể sửa một context đã được chia sẻ.
SecurityContextHolder.getContext().setAuthentication(otherAuthentication);
```

Nếu một scope tự quản lý nằm **ngoài Servlet filter chain**, phải dọn lại:

```java
try {
    SecurityContext context = SecurityContextHolder.createEmptyContext();
    context.setAuthentication(authenticationFromTrustedMechanism);
    SecurityContextHolder.setContext(context);
    performTrustedWork();
} finally {
    SecurityContextHolder.clearContext();
}
```

Mẫu trên chỉ dành cho **phạm vi tự quản lý**; không copy vào controller đang được Spring Security xử lý. Nếu code được gọi từ một context đã có sẵn, gọi `clearContext()` có thể xóa Authentication của luồng gọi. Khi đó nên dùng wrapper quản lý scope hoặc lưu và khôi phục context cũ theo cơ chế được thiết kế cẩn thận.

Không đổi Authentication tạm sang một “admin” để qua được method security. Nếu tác vụ cần quyền service, phải thiết kế cơ chế service credential/authorization và audit riêng.

## 13. Những tình huống thường gặp

### Tình huống A: hai user gọi cùng endpoint đồng thời

```text
T1 Thread-21:
  Bearer token của user-A
  JwtAuthenticationToken(name=user-A)

T2 Thread-34:
  Bearer token của user-B
  JwtAuthenticationToken(name=user-B)
```

Mỗi request có context riêng theo thread. Sau khi xử lý xong, framework dọn context. Nếu một singleton service giữ Authentication trong field mutable, nó có thể phá vỡ ranh giới vốn có.

### Tình huống B: cùng người dùng gọi hai request liên tiếp

```text
GET /api/me + Bearer token-A -> context(user-A) trong request 1
GET /api/me + Bearer token-A -> context(user-A) trong request 2
```

Với API stateless, request 2 xác thực credential của chính nó; không cần dùng lại cùng Java object SecurityContext của request 1.

### Tình huống C: endpoint public không có token

```text
GET /public/health
Không có Authorization header
```

Endpoint vẫn có thể được cho phép với `permitAll()`. Context có thể chưa có Authentication hoặc có anonymous principal tùy cấu hình.

### Tình huống D: JWT hợp lệ nhưng thiếu quyền

```text
JWT: aud=orders-api; sub=user-A; scope=orders.read
POST /api/orders cần SCOPE_orders.write
```

JWT authentication có thể thành công, context chứa `JwtAuthenticationToken(user-A)`, nhưng authorization trả **403** vì thiếu authority. Authentication hợp lệ không đồng nghĩa mọi thao tác đều được phép.

### Tình huống E: Async trên executor mặc định

```text
HTTP Thread: context(user-A) -> submit task -> response 202
Worker Thread: getContext() -> không tự có user-A
```

Giải pháp là truyền actor tường minh hoặc dùng DelegatingSecurityContext có kiểm soát, đồng thời đánh giá quyền và vòng đời thực thi.

### Tình huống F: error dispatch

```text
REQUEST: user-A được xác thực -> controller phát sinh lỗi
ERROR dispatch: có thể cần repository để nạp lại context cùng request
```

Repository theo request attribute có thể hỗ trợ trường hợp này. Không suy ra context còn tồn tại sang một HTTP request khác.

## 14. Những lỗi thiết kế dễ gây rủi ro

| Sai lầm | Vì sao sai | Cách làm phù hợp |
|---|---|---|
| Coi holder là biến global lưu user cuối cùng | Mặc định là ThreadLocal | Để filter chain quản lý context từng request |
| Dùng `MODE_GLOBAL` cho web server | Danh tính có thể bị dùng chung | Giữ strategy mặc định |
| Dùng `MODE_INHERITABLETHREADLOCAL` để chữa mọi async | Pool có thể giữ/thiếu context | Truyền actor hoặc dùng concurrency wrapper |
| Lưu Authentication vào field singleton | Rủi ro race condition và lẫn user | Nhận actor từ tham số request |
| Tin mỗi `isAuthenticated()` | Anonymous token có thể trả true | Dùng authorization/trust resolver |
| Coi `getName()` luôn là email end-user | Có service token và converter tùy biến | Hiểu hợp đồng principal |
| Có JWT auth rồi bỏ qua owner/tenant | Scope không thay thế quyền bản ghi | Kiểm tra ở tầng nghiệp vụ |
| Gán Authentication từ header không tin cậy | Có thể giả mạo user/admin | Xác thực bearer credential theo hợp đồng |
| Tự lưu context vào session cho API bearer | Tạo trạng thái và hành vi sai mong đợi | Dùng stateless/request token theo thiết kế |
| Xóa context trong controller | Làm mất danh tính trước khi xử lý tiếp | Để filter dọn context |
| Log JWT/token value | Credential bị lộ có thể được sử dụng lại | Chỉ ghi metadata tối thiểu |
| Tưởng context tự truyền sang microservice | Context nằm trong JVM | API đích xác thực credential riêng |
| Dùng `@WithMockUser` và kết luận chữ ký JWT đúng | Test chỉ giả lập principal | Tách test authorization với JWT validation |

## 15. Quan sát và kiểm chứng hành vi mà không làm lộ token

Khi gỡ lỗi, tách ba câu hỏi:

1. **Authentication:** bearer token có được decoder/introspector xác minh không?
2. **Context:** holder đang chứa Authentication loại nào và authorities gì?
3. **Authorization:** policy endpoint và nghiệp vụ có cho phép thao tác không?

Một endpoint nội bộ chỉ trả metadata tối thiểu:

```java
@GetMapping("/internal/auth-info")
public Map<String, Object> authInfo(Authentication auth) {
    return Map.of(
        "authenticationType", auth.getClass().getSimpleName(),
        "principalName", auth.getName(),
        "authorities", auth.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .toList()
    );
}
```

`GrantedAuthority` thuộc `org.springframework.security.core.GrantedAuthority`. Endpoint chẩn đoán này phải được bảo vệ; không trả raw token/credentials hay mọi claim của người dùng.

Với Spring Security Test, `@WithMockUser` tạo một Authentication giả lập để kiểm tra authorization:

```java
@WithMockUser(username = "user-842", authorities = "SCOPE_orders.read")
@Test
void mayReadWithScope() {
    // Test nhánh phân quyền dựa trên Authentication giả lập.
}
```

Kiểm thử kiểu này **không chứng minh JWT decoder xác minh đúng chữ ký, issuer, audience hoặc thời hạn**. Tương tự, `SecurityMockMvcRequestPostProcessors.jwt()` thuận tiện khi kiểm tra controller/authorization với JWT principal giả lập, nhưng có thể không chạy qua toàn bộ nhánh Bearer HTTP header và JWT decoder thật.

Khi quan sát filter chain, có thể bật DEBUG log trong development:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
```

Không in nguyên `Jwt#getTokenValue()`, `Authorization` header hoặc Authentication object có credential vào log production. Nếu dùng nhiều `SecurityFilterChain`, Spring Security chọn chain phù hợp đầu tiên; request không match chain bearer có thể không được xác thực theo cách mong đợi, dù header có token.

## 16. Câu hỏi thường gặp

**Có thể đọc principal ở mọi class Java không?** Có thể ở code chạy trong thread mà Spring Security đã thiết lập context. Không tự giả định có context khi gọi từ constructor lúc startup, `@Scheduled`, executor thread, callback thư viện hoặc code chạy sau HTTP response.

**SecurityContextHolder có phải kho lưu token không?** Không. Holder cung cấp context chứa Authentication. Một số Authentication implementation tham chiếu JWT/token, nhưng mục tiêu là biểu diễn danh tính và authorities hiện tại, không lưu refresh token hay cache bearer token qua request.

**Có nên tự gọi `setAuthentication()` trong controller?** Với Resource Server chuẩn thì không; filter đã làm điều đó sau khi xác thực credential. Custom authentication mechanism cần tích hợp đúng filter/provider và lifecycle.

**Vì sao `getAuthentication()` null dù client gửi token?** Code có thể chạy trước filter, trong thread khác, ngoài matcher của SecurityFilterChain, sau khi request đã kết thúc, hoặc request không được xử lý bởi bearer filter. Token sai thường bị chặn trước controller. Cần xem đúng vị trí đọc context và chuỗi filter.

**Có thể đưa SecurityContext vào message queue?** Không nên serialize Java SecurityContext/Authentication thành credential cho process khác. Chuyển thông tin actor tối thiểu theo hợp đồng; bên nhận phải áp cơ chế xác thực/ủy quyền độc lập.

**Context có tồn tại sau request không?** Context trong holder của thread request được dọn. Trong mô hình stateful, một repository/session có thể lưu dữ liệu để nạp lại trong request tương lai, nhưng đó là một cơ chế khác với việc để nguyên Authentication trên thread.

## 17. Mô hình ghi nhớ

```text
HTTP request đến Resource Server
    |
    v
Bearer token -> xác thực JWT hoặc introspection
    |
    v
Authentication đã xác thực
    |
    v
SecurityContext chứa Authentication
    |
    v
SecurityContextHolder cho code trong phạm vi thread đọc context
    |
    +--> HTTP/method authorization: scope, authority
    +--> Business authorization: ownership, tenant, trạng thái
    +--> Async: truyền actor/context một cách rõ ràng
    +--> Microservice khác: cần credential hợp lệ cho API đích
    |
    v
Kết thúc xử lý -> dọn context khỏi holder
```

**`SecurityContextHolder` trả lời “trong phạm vi thực thi hiện tại, Spring Security đang sử dụng Authentication nào?”.** Nó không tự xác thực JWT, không tự ban quyền cho dữ liệu và không bảo đảm danh tính lan sang thread/request/process khác. Khi hiểu ranh giới này, ứng dụng Servlet có thể tránh lẫn người dùng giữa các request, mất danh tính ở tác vụ async và sử dụng sai credential khi gọi dịch vụ phía sau.

## Tài liệu tham khảo

- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): holder, context, authentication, ThreadLocal strategy.
- [Spring Security — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): Bearer filter, JWT và opaque token.
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JwtDecoder, JwtAuthenticationToken và validator.
- [Spring Security — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection và principal.
- [Spring Security — Authentication Persistence](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html): SecurityContextHolderFilter và SecurityContextRepository.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): explicit save và session policy.
- [Spring Security — Spring MVC Integration](https://docs.spring.io/spring-security/reference/servlet/integrations/mvc.html): AuthenticationPrincipal, CurrentSecurityContext và MVC Callable/DeferredResult.
- [Spring Security — Concurrency Support](https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html): DelegatingSecurityContext wrappers.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): cách dùng và bảo vệ bearer token.
