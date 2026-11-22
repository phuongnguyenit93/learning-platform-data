# ReactiveSecurityContextHolder và danh tính trong Reactor Context

Trong **Spring Security OAuth 2.0/OIDC Resource Server** sử dụng **Spring WebFlux**, một HTTP request có thể được xử lý qua nhiều toán tử Reactor, đổi thread thực thi và gọi các dịch vụ bất đồng bộ. Điều đó làm thay đổi cách ứng dụng lưu và truy cập **danh tính người gọi** so với ứng dụng Servlet dùng `ThreadLocal`.

Ở WebFlux, Spring Security cung cấp **`ReactiveSecurityContextHolder`** để truy cập `SecurityContext` thông qua **Reactor Context gắn với subscriber**. Sau khi Resource Server xác thực Bearer access token, các thành phần phía sau có thể đọc `Authentication` trong reactive pipeline nhằm kiểm tra subject, scope và quyền truy cập tài nguyên. Tuy nhiên, danh tính không đơn giản được “gắn vào thread hiện tại”, và cũng không được phép tùy ý biến một chuỗi `sub` do client cung cấp thành Authentication đáng tin.

Bài học này tập trung vào:

- Sự khác biệt giữa **`SecurityContextHolder` kiểu ThreadLocal** và **`ReactiveSecurityContextHolder` trong Reactor Context**.
- Luồng Bearer JWT/opaque token qua **`SecurityWebFilterChain`**, reactive authentication và authorization.
- Cách dùng `ReactiveSecurityContextHolder.getContext()`, `withAuthentication(...)`, `withSecurityContext(...)`, `clearContext()` và `contextWrite(...)`.
- Quy tắc **Context đi theo subscriber, được đọc khi subscription** và tác động của `publishOn`, `subscribeOn`, `block()`, `subscribe()`, thread pool và callback ngoài Reactor.
- Đọc JWT/opaque principal trong controller và service, áp dụng **reactive method security**, bảo vệ tenant/ownership và kiểm thử bằng **StepVerifier/WebTestClient**.

Các ví dụ dùng Java, Reactor, Spring Security WebFlux và Spring Boot hiện đại. API cụ thể có thể khác theo dòng phiên bản, nhưng nguyên tắc bảo mật và mô hình subscriber context cần được giữ nhất quán.

## 1. Khung kiến trúc WebFlux Resource Server

Một client gọi:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <access-token>
~~~

Khác với Servlet `SecurityFilterChain`, WebFlux dùng **`SecurityWebFilterChain`** gồm các **`WebFilter`** làm việc với request/response bất đồng bộ. Với JWT, quá trình xác thực thường bao gồm lấy Bearer token, gọi `ReactiveAuthenticationManager` và `ReactiveJwtDecoder`, rồi đặt authentication vào reactive security context.

~~~mermaid
flowchart TD
    A["HTTP GET + Bearer access token"] --> B["WebFlux WebFilter chain"]
    B --> C["AuthenticationWebFilter / Bearer token converter"]
    C --> D{"Có Bearer token?"}
    D -- "Có" --> E["ReactiveAuthenticationManager"]
    E --> F["ReactiveJwtDecoder hoặc ReactiveOpaqueTokenIntrospector"]
    F --> G{"Token hợp lệ, đúng issuer/audience/time/profile?"}
    G -- "Không" --> H["ServerAuthenticationEntryPoint: thường 401"]
    G -- "Có" --> I["Authentication đã xác thực"]
    I --> J["SecurityContext trong Reactor Context"]
    D -- "Không" --> K["Tiếp tục WebFilter chain"]
    J --> K
    K --> L["AuthorizationWebFilter"]
    L --> M{"Đủ quyền endpoint?"}
    M -- "Không" --> N["401/403 theo trạng thái và handler"]
    M -- "Có" --> O["Handler / Controller / Service"]
    O --> P["ReactiveSecurityContextHolder.getContext()"]
    P --> Q["Kiểm tra quyền trên tài nguyên nghiệp vụ"]
~~~

Sơ đồ là khái quát luồng trách nhiệm, **không phải cam kết tên/thứ tự từng WebFilter ở mọi phiên bản**. Spring Security có các filter liên quan như `ReactorContextWebFilter` và `SecurityContextServerWebExchangeWebFilter` để phối hợp ngữ cảnh xác thực trong WebFlux. `AuthenticationWebFilter` có thể gắn kết quả authentication vào Reactor Context cho phần xử lý tiếp theo.

| Thành phần | Trách nhiệm |
| --- | --- |
| `SecurityWebFilterChain` | Cấu hình các WebFilter và quy tắc bảo mật cho WebFlux |
| `ServerHttpSecurity` | DSL cấu hình reactive HTTP security |
| `ReactiveAuthenticationManager` | Xác thực yêu cầu theo mô hình reactive |
| `ReactiveJwtDecoder` | Giải mã/xác minh JWT access token trong nhánh reactive JWT |
| `ReactiveOpaqueTokenIntrospector` | Xác minh opaque token qua introspection và trả principal theo mô hình reactive |
| `ReactiveSecurityContextHolder` | Truy cập `Mono<SecurityContext>` từ Reactor Context |
| `Authentication` | Danh tính và authorities đã được xác thực |
| `AuthorizationWebFilter` | Kiểm tra `permitAll`, `authenticated`, scope và các rule HTTP |
| Reactive method security | Phân quyền trên phương thức service trả `Mono`/`Flux` |

**Resource Server xác thực access token, không tự cấp access token mới.** Một OIDC **ID token** dùng cho client đăng nhập không tự trở thành access token dành cho API, ngay cả khi nó có `sub` và chữ ký hợp lệ.

## 2. Vì sao ThreadLocal không phù hợp để giữ danh tính trong reactive pipeline?

Trong mô hình Servlet đồng bộ, Spring Security thường cung cấp:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
~~~

Cách trên chủ yếu dựa vào một chiến lược `SecurityContextHolder` sử dụng **ThreadLocal** trong các ứng dụng Servlet thông dụng. Một request được xử lý trên thread hiện tại, và framework quản lý việc thiết lập/dọn ngữ cảnh trong phạm vi request.

Nhưng WebFlux có thể thực thi những giai đoạn của cùng một request trên **các thread khác nhau**:

~~~text
Request #A
  event-loop-1: đọc HTTP, nhận access token
      |
      v
  event-loop-1: bắt đầu reactive pipeline
      |
      +-- publishOn(boundedElastic)
      |
      v
  boundedElastic-2: truy vấn hoặc tính toán
      |
      v
  event-loop-3: ghi HTTP response
~~~

Nếu chỉ lưu danh tính trong một `ThreadLocal`, bước thực thi sau khi đổi thread có thể không đọc được dữ liệu cũ, hoặc đọc nhầm trạng thái nếu code quản lý thread-local sai. Đây là một lý do WebFlux dùng **Reactor Context theo subscription** để mang thông tin xuyên các giai đoạn asynchronous.

| Tiêu chí | `SecurityContextHolder` kiểu ThreadLocal | `ReactiveSecurityContextHolder` |
| --- | --- | --- |
| Phạm vi chính | Thread hiện tại | Reactor subscriber/subscription |
| Truy cập | Đồng bộ, giá trị hiện tại | `Mono<SecurityContext>`, đánh giá khi subscribe |
| Khi đổi thread | Không tự bảo đảm giữ nguyên ThreadLocal | Reactor Context tiếp tục đi cùng subscription qua các toán tử Reactor chuẩn |
| Cách ghi ngữ cảnh | Set/Clear SecurityContextHolder theo chiến lược | `contextWrite(...)` với context có security context |
| Kiểm thử | Gắn thread-local test context | `StepVerifier`/`WebTestClient` với reactive context |
| Rủi ro thường gặp | Rò ThreadLocal giữa request/thread | Mất context khi rời reactive chain hoặc tạo subscription độc lập |

**Không nên lấy `SecurityContextHolder.getContext()` làm nguồn danh tính mặc định trong WebFlux reactive service**. Ở đó, `ReactiveSecurityContextHolder.getContext()` mới là API phù hợp với ngữ cảnh subscriber do Spring Security quản lý.

## 3. Reactor Context là gì?

Trong Project Reactor, **`Context`** là cấu trúc key–value gắn với **Subscriber**. Nó khác với:

- **`ThreadLocal`:** dữ liệu nằm trên thread đang chạy.
- **Biến local Java:** dữ liệu nằm trong một lần gọi phương thức/scope cụ thể.
- **`ServerWebExchange.getAttributes()`:** dữ liệu request do framework hoặc code lưu trên exchange.
- **`Context` của một thread pool:** Reactor Context không phải một map toàn cục của scheduler.

Reactor Context được thiết kế như một cấu trúc **bất biến theo ngữ nghĩa**: thao tác `put` trả về ngữ cảnh mới thay vì sửa tại chỗ. Các lần subscribe có thể có context khác nhau, dù dùng chung một `Mono` hoặc `Flux`.

Ví dụ với một key ứng dụng không liên quan bảo mật:

~~~java
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

Mono<String> requestLabel = Mono.deferContextual(contextView ->
    Mono.just(contextView.getOrDefault("requestLabel", "anonymous-request"))
);

Mono<String> flow = requestLabel
    .contextWrite(Context.of("requestLabel", "request-42"));
~~~

Khi `flow` được subscribe, `requestLabel` sẽ đọc `request-42`. Đây là **metadata tùy chỉnh**; một string trong Reactor Context **không tự đáng tin để phân quyền**. Người dùng hoặc đoạn code trong ứng dụng có thể ghi tùy ý một key thường. Chỉ Authentication đã được xác minh theo quy trình Spring Security mới được dùng làm danh tính bảo mật.

### Context đi từ subscriber về phía upstream

Một đặc điểm dễ nhầm là toán tử **`contextWrite(...)` tác động đến phần upstream của nó** khi tạo subscription. Hãy hình dung:

~~~text
source (đọc Context)
     |
     v
map / flatMap
     |
     v
contextWrite(put key)
     |
     v
subscriber

Khi subscribe:
subscriber -> contextWrite -> upstream source thấy key
~~~

Vì thế vị trí của `contextWrite` trong pipeline **có ý nghĩa**; nó không đơn thuần giống lệnh gán một biến toàn cục cho mọi đoạn code phía sau.

## 4. API cốt lõi của ReactiveSecurityContextHolder

`ReactiveSecurityContextHolder` nằm trong:

~~~java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
~~~

Những API quan trọng:

| API | Kết quả/ý nghĩa |
| --- | --- |
| `ReactiveSecurityContextHolder.getContext()` | `Mono<SecurityContext>`, đọc context hiện có từ subscriber |
| `ReactiveSecurityContextHolder.withAuthentication(authentication)` | Tạo Reactor `Context` mang `SecurityContext` từ Authentication đã cho |
| `ReactiveSecurityContextHolder.withSecurityContext(Mono<SecurityContext>)` | Tạo Reactor `Context` mang publisher của SecurityContext |
| `ReactiveSecurityContextHolder.clearContext()` | Hàm biến đổi Reactor Context để bỏ security context khi áp dụng bằng `contextWrite(...)` |

Chữ ký generic chính xác của `withSecurityContext(...)` có thể dùng wildcard tùy phiên bản. Với Spring Security thông dụng, có thể truyền `Mono.just(securityContext)`.

### 4.1. Đọc SecurityContext

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;

Mono<Authentication> currentAuthentication =
    ReactiveSecurityContextHolder.getContext()
        .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()));
~~~

Đây là `Mono<Authentication>`, **không phải** một đối tượng Authentication sẵn có tại thời điểm khai báo biến. Nó chỉ tạo giá trị khi một subscriber chạy trong context tương ứng.

Nếu subscriber không có security context, `getContext()` có thể hoàn tất **rỗng**; nếu context có Authentication null, `Mono.justOrEmpty(...)` cũng cho rỗng. Trên một số chain có anonymous authentication, bạn có thể nhận `AnonymousAuthenticationToken` — không nên coi nó là user đã đăng nhập chỉ vì `isAuthenticated()` trả true.

### 4.2. Ghi Authentication vào context

~~~java
import java.util.List;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Authentication authenticated = new UsernamePasswordAuthenticationToken(
    "alice",
    "not-used",
    List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
);

Mono<String> currentName = ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName());

Mono<String> forTest = currentName.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(authenticated)
);
~~~

Nếu subscribe `forTest`, publisher upstream `currentName` nhận Authentication `alice` qua Reactor Context.

**Đây là ví dụ để hiểu API và tạo fixture kiểm thử**, không phải cách production tự xác thực người dùng từ một username/client header. Trong HTTP Resource Server, Spring Security filter phải xác minh Bearer access token **trước khi** thiết lập Authentication đáng tin.

### 4.3. Ghi một SecurityContext hoàn chỉnh

~~~java
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextImpl;
import reactor.core.publisher.Mono;

SecurityContext context = new SecurityContextImpl(authenticated);

Mono<String> name = currentName.contextWrite(
    ReactiveSecurityContextHolder.withSecurityContext(Mono.just(context))
);
~~~

`withAuthentication(...)` là cách ngắn gọn khi đã có Authentication. `withSecurityContext(...)` hữu ích khi framework hoặc fixture có sẵn một `Mono<SecurityContext>`. Cả hai chỉ tạo **context cho upstream tại subscription**, không biến `SecurityContext` thành biến static toàn ứng dụng.

### 4.4. Xóa context trong phạm vi subscriber

~~~java
Mono<String> withoutIdentity = currentName
    .contextWrite(ReactiveSecurityContextHolder.clearContext());
~~~

Đoạn này minh họa việc loại security context khỏi phần upstream của publisher; khi không có context, `currentName` ở ví dụ có thể hoàn tất rỗng. Trong test, `clearContext()` hữu ích để xác nhận service xử lý thiếu danh tính. **Không dùng nó trong production để tắt xác thực hoặc bỏ qua authorization của API**.

## 5. Subscription là thời điểm danh tính được đọc

Một nhầm lẫn thường gặp là mong lời gọi `getContext()` lập tức trả một context “của request hiện tại”:

~~~java
// Không phải cách lấy Authentication đồng bộ:
Mono<SecurityContext> contextMono =
    ReactiveSecurityContextHolder.getContext();
~~~

Biến `contextMono` chỉ là một **publisher**. Context được giải quyết khi nó được subscribe, trong phạm vi subscriber của pipeline thực tế. Spring WebFlux và Reactor sẽ subscribe vào publisher trả từ controller/service khi xử lý HTTP request.

### Đúng: trả publisher để framework subscribe

~~~java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

public Mono<String> currentName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());
}
~~~

### Sai: tự block trong reactive service

~~~java
// TRÁNH trong WebFlux reactive flow:
String name = ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName())
    .block();
~~~

`block()` tạo một subscription đồng bộ mới và có thể chặn event-loop; nó cũng không bảo đảm mang Reactor Context của request hiện tại sang subscription mới. Trên thread WebFlux không cho phép blocking, thao tác này có thể gây lỗi runtime.

### Sai: tự subscribe để chạy side effect rồi trả kết quả

~~~java
// TRÁNH: fire-and-forget, subscription độc lập.
ReactiveSecurityContextHolder.getContext()
    .doOnNext(ctx -> audit(ctx.getAuthentication().getName()))
    .subscribe();
~~~

Hành vi side effect có thể chạy ngoài lifecycle request, mất context, không được chờ hoàn thành và làm lỗi không được xử lý đúng. Thay vào đó, **ghép audit vào publisher được trả về**:

~~~java
public Mono<Void> auditCurrentUser() {
    return ReactiveSecurityContextHolder.getContext()
        .flatMap(ctx ->
            auditService.recordUserAction(
                ctx.getAuthentication().getName()));
}
~~~

Ví dụ giả định `auditService.recordUserAction(...)` trả `Mono<Void>`. Caller phải compose publisher trong chuỗi đang được WebFlux subscribe. Không ghi raw access token, refresh token hoặc dữ liệu cá nhân không cần thiết vào log/audit.

## 6. Vị trí contextWrite quyết định upstream nào nhìn thấy danh tính

Giả sử:

~~~java
Mono<String> readName = ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName());
~~~

Cách áp dụng đúng:

~~~java
Mono<String> result = Mono.just("work")
    .then(readName)
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(authenticated));
~~~

Với cấu trúc này, `contextWrite` nằm ở downstream của toàn bộ publisher `Mono.just(...).then(readName)`, nên upstream `readName` có thể đọc context.

Vị trí dễ gây sai:

~~~java
Mono<String> wrong = Mono.just("work")
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(authenticated))
    .then(readName);
~~~

Ở đây toán tử `contextWrite` chỉ bao quanh publisher `Mono.just("work")` ở upstream; `readName` là publisher được dùng ở phần `then(...)` downstream, nên **không được bảo đảm nhìn thấy context ấy**.

**Không dùng cách “thấy đoạn code ở bên dưới trong file nên chắc có context”.** Hãy xét graph của Reactor: subscriber, toán tử `contextWrite` và phần upstream mà nó tác động.

### Hai subscription khác nhau có thể có hai danh tính khác nhau

~~~java
Mono<String> source = ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName());

Mono<String> forAlice = source.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(aliceAuth));

Mono<String> forBob = source.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(bobAuth));
~~~

Dù hai publisher dùng chung `source`, mỗi lần subscribe có context riêng. Vì vậy **không đưa Authentication vào static field** hoặc shared singleton field rồi mong đồng bộ đúng theo từng request.

## 7. Cấu hình JWT Resource Server trong WebFlux

Dependency Spring Boot thông dụng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Giả sử Orders API nhận JWT access token từ issuer:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

Trong WebFlux, Spring Security sử dụng các thành phần **reactive** như `ReactiveJwtDecoder`. Một `JwtDecoder` Servlet tùy chỉnh **không tự thay thế** decoder reactive của WebFlux.

Ví dụ cấu hình `SecurityWebFilterChain`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class ReactiveApiSecurity {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public/**").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Ví dụ `csrf(...disable())` giả định ứng dụng là API **Bearer-only stateless**, không dựa vào cookie xác thực trình duyệt tự động gửi. Với các ứng dụng có cookie/session, cần đánh giá CSRF đầy đủ.

JWT Resource Server phải kiểm tra **chữ ký, issuer, thời hạn, audience và token profile theo hợp đồng**. Cấu hình `issuer-uri` không tự thay thế mọi validator dành riêng cho API. Một JWT còn hạn nhưng `aud` dành cho Payments API không nên được Orders API chấp nhận.

### Tại sao reactive context xuất hiện sau xác thực?

Trong nhánh JWT, provider/manager có thể tạo `JwtAuthenticationToken` với `Jwt` làm principal và authorities đã được chuyển từ `scope`/`scp`. Spring Security reactive web filters bảo đảm Authentication thành công có thể được đọc bởi các reactive publisher chạy **trong phần còn lại của request chain**.

Không cần tự đặt:

~~~java
// KHÔNG NÊN thêm thủ công vào controller production:
// SecurityContextHolder.getContext().setAuthentication(jwtAuth);
~~~

để WebFlux nhận diện người dùng. Framework đã tạo security context trong reactive pipeline sau khi xác thực access token.

## 8. Đọc danh tính JWT trong Controller

Với controller annotated WebFlux, có thể lấy principal đã xác thực bằng `@AuthenticationPrincipal`:

~~~java
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class ProfileController {

    @GetMapping("/api/me")
    Mono<Map<String, String>> me(@AuthenticationPrincipal Jwt jwt) {
        return Mono.just(Map.of(
            "subject", jwt.getSubject(),
            "issuer", jwt.getIssuer().toString()
        ));
    }
}
~~~

Ví dụ giả định endpoint chỉ chấp nhận JWT đã xác thực và có `sub`/`iss` phù hợp. Không nên trả toàn bộ claims hoặc token value cho client. Khi endpoint được `permitAll()`, principal có thể không hiện diện; không áp dụng cách này mà quên xử lý trường hợp anonymous.

### Đọc Authentication bằng Reactor Context tại service

Trong service không có tham số `Jwt` của controller, dùng:

~~~java
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class CurrentJwtProvider {

    public Mono<Jwt> currentJwt() {
        return ReactiveSecurityContextHolder.getContext()
            .flatMap(context ->
                Mono.justOrEmpty(context.getAuthentication()))
            .filter(Authentication::isAuthenticated)
            .ofType(JwtAuthenticationToken.class)
            .map(JwtAuthenticationToken::getToken)
            .switchIfEmpty(Mono.error(
                new AuthenticationCredentialsNotFoundException(
                    "JWT access token required")));
    }
}
~~~

Ưu điểm:

1. Đọc principal khi publisher **được subscribe**, đúng subscriber context.
2. Không coi `AnonymousAuthenticationToken` là JWT user.
3. Không ép kiểu tùy tiện từ Authentication sang Jwt.
4. Khi không có JWT authentication thích hợp, **báo lỗi** thay vì tự gán “system user”.
5. Không dùng `block()` hoặc lấy principal qua một static field.

Trong production, tầng web/entry point cần cấu hình phản hồi HTTP phù hợp cho lỗi authentication; nếu nghiệp vụ cố gọi provider trong một luồng không có request, hãy truyền identity theo hợp đồng rõ ràng thay vì ngầm phụ thuộc HTTP context.

## 9. Principal trong opaque token và những khác biệt

Với opaque access token, Resource Server gọi **reactive introspection** thay vì đọc JWS. Cấu hình minh họa:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: REPLACE_WITH_RUNTIME_SECRET
~~~

Và WebFlux DSL:

~~~java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults()))
~~~

Đây là **phương án opaque token riêng**, không nên thêm vào cùng cấu hình JWT chỉ để “thử cho chạy” mà chưa xác định cơ chế chọn cách xác thực theo request.

Với opaque token, Authentication thường là `BearerTokenAuthentication`, principal là `OAuth2AuthenticatedPrincipal`. Đọc thông tin theo kiểu:

~~~java
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;
import reactor.core.publisher.Mono;

public Mono<OAuth2AuthenticatedPrincipal> currentOpaquePrincipal() {
    return ReactiveSecurityContextHolder.getContext()
        .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
        .ofType(BearerTokenAuthentication.class)
        .map(BearerTokenAuthentication::getPrincipal)
        .switchIfEmpty(Mono.error(
            new AuthenticationCredentialsNotFoundException(
                "Opaque token authentication required")));
}
~~~

Không ép kiểu `authentication.getPrincipal()` sang `Jwt` khi ứng dụng đã chuyển sang opaque token. Nếu service hỗ trợ cả JWT và opaque token, nên chuyển cả hai sang một abstraction miền nghiệp vụ **đã xác minh**, ví dụ `AuthenticatedActor(issuer, subject, clientId, tenantId, authorities)`.

| Nhánh xác thực | Authentication thường gặp | Principal thường gặp | Nguồn danh tính |
| --- | --- | --- | --- |
| Reactive JWT | `JwtAuthenticationToken` | `Jwt` | Claims của JWT đã được `ReactiveJwtDecoder` xác minh |
| Reactive opaque token | `BearerTokenAuthentication` | `OAuth2AuthenticatedPrincipal` | Metadata được introspector của issuer chấp nhận |
| Anonymous | Có thể là `AnonymousAuthenticationToken` tùy chain | Anonymous principal | Không phải danh tính người dùng đã xác thực |

**`Authentication.getName()` không luôn bằng email hoặc internal user ID.** Với JWT thường dựa trên `sub`, còn opaque token phụ thuộc principal implementation. Hệ thống nhiều issuer nên ánh xạ **(issuer, subject)** sang identity nội bộ thay vì coi `sub` trùng nhau ở mọi issuer.

## 10. Reactive method security: quyền được kiểm tra trong subscription

Spring Security WebFlux có thể bật:

~~~java
@EnableReactiveMethodSecurity
~~~

để áp dụng biểu thức như `@PreAuthorize` lên service reactive. Trong mô hình này, các phương thức được bảo vệ thường cần trả **`Mono`/`Flux`** hoặc loại publisher được hỗ trợ, để framework đưa việc kiểm tra quyền vào chuỗi reactive thích hợp.

Ví dụ:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class OrderQueryService {

    private final CurrentActorService actors;
    private final ReactiveOrderRepository orders;

    public OrderQueryService(
            CurrentActorService actors,
            ReactiveOrderRepository orders) {
        this.actors = actors;
        this.orders = orders;
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public Mono<OrderDto> readOrder(String tenantId, String orderId) {
        return actors.currentActor()
            .flatMap(actor ->
                orders.findReadableOrder(
                    orderId, tenantId, actor.userId()))
            .map(OrderDto::from)
            .switchIfEmpty(Mono.error(new OrderNotFoundException()));
    }
}
~~~

Các kiểu `CurrentActorService`, `ReactiveOrderRepository`, `OrderDto`, `OrderNotFoundException` là **thành phần ứng dụng tự định nghĩa**. `findReadableOrder(...)` biểu thị một truy vấn đã kiểm tra tenant, owner hoặc quan hệ chia sẻ thích hợp; không phải API có sẵn của Spring Security.

**Scope chỉ là quyền chức năng.** Dù token có `SCOPE_orders.read`, người dùng không tự được xem order của người khác hoặc tenant khác. Policy nghiệp vụ có thể cần:

~~~text
Được đọc Order khi:
  JWT/introspection đã xác minh
  AND có SCOPE_orders.read
  AND là thành viên đang hoạt động của tenant chứa order
  AND (là owner OR manager hợp lệ OR có share READ còn hiệu lực)
~~~

Reactive Context giúp **truyền danh tính** đến service, nhưng **không tự thực thi** quyền ownership/tenant. Việc đọc DB phải được giới hạn theo policy, và membership/share có thể cần kiểm tra trạng thái hiện hành khi token còn hạn.

### Cẩn thận với self-invocation

Reactive method security thường đi qua proxy/interceptor. Khi method trên cùng object tự gọi một method khác có `@PreAuthorize`, lời gọi nội bộ có thể **không đi qua proxy**. Không được coi annotation trên một method là bảo vệ tuyệt đối mọi đường đi; đặt chính sách ở service ranh giới và repository phù hợp, đồng thời kiểm thử HTTP/batch/message consumer khi chúng cùng thao tác dữ liệu.

## 11. publishOn và subscribeOn có làm mất Reactor Context không?

Một đặc điểm quan trọng: **đổi scheduler bằng các toán tử Reactor chuẩn không đồng nghĩa mất Reactor Context**.

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

Mono<String> name = ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName())
    .publishOn(Schedulers.boundedElastic())
    .map(value -> value.toUpperCase());
~~~

Nếu publisher này được subscribe trong một security context phù hợp, ngữ cảnh gắn với subscription vẫn có thể được truy cập qua `ReactiveSecurityContextHolder`, dù xử lý đổi thread. Reactor đảm nhiệm việc mang Context qua các toán tử của nó.

Tuy nhiên, **`ThreadLocal` không tự đi cùng** theo cách tương tự. Trong lambda chạy trên thread khác:

~~~java
// Không đáng tin để đọc principal trong reactive pipeline:
// SecurityContextHolder.getContext().getAuthentication();
~~~

Đọc `ReactiveSecurityContextHolder.getContext()` từ **publisher nằm trong cùng reactive chain** mới là cách phù hợp.

### Điểm dễ mất context thực sự

- Gọi `.block()` trên một publisher khác và tạo subscription độc lập.
- Gọi `.subscribe()` để fire-and-forget rồi không compose với request chain.
- Chuyển sang `CompletableFuture`, executor hoặc callback ngoài Reactor mà không có cơ chế **context propagation** phù hợp.
- Tạo Publisher mới tại một boundary bên ngoài và subscribe nó mà không mang context.
- Dùng API imperative đọc `SecurityContextHolder` ThreadLocal trên thread khác.
- Dùng `contextWrite(...)` sai vị trí, khiến publisher cần đọc danh tính nằm ngoài phần upstream.

**Không đánh đồng `publishOn` với mất Reactor Context.** Rủi ro lớn thường ở **subscription bị tách** hoặc **bridge sang hệ thống không hiểu Reactor Context**.

## 12. Kết hợp với API blocking, executor và @Async

WebFlux không có nghĩa mọi thư viện dưới tầng service đều non-blocking. Khi phải gọi một API blocking trong hệ thống reactive, thường cần đưa thao tác blocking sang scheduler phù hợp:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public Mono<OrderRecord> loadFromBlockingRepository(String id) {
    return Mono.fromCallable(() -> blockingRepository.findById(id))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

Đây là ví dụ kỹ thuật về bảo vệ event loop khỏi blocking I/O; cần kiểm tra kiểu trả về thật của repository, lỗi/not found và số lượng thread. **Không gọi blocking repository ngay trên event-loop** rồi chỉ thêm `publishOn` ở cuối pipeline mà tưởng đã di chuyển công việc trước đó.

Nếu cần danh tính trong một blocking callback, hãy **lấy danh tính có kiểm soát từ Reactive Context rồi truyền như tham số**:

~~~java
public Mono<OrderRecord> loadOrderForCurrentUser(String id) {
    return actors.currentActor()
        .flatMap(actor ->
            Mono.fromCallable(() ->
                    blockingRepository.findVisibleOrder(
                        id, actor.userId(), actor.tenantId()))
                .subscribeOn(Schedulers.boundedElastic()));
}
~~~

Ở đây `actors.currentActor()` phải lấy danh tính **đã xác thực** từ request; `actor.userId()` và `tenantId()` phải được xác định từ identity/policy đáng tin. Truyền actor tường minh vào callback giúp tránh phụ thuộc ThreadLocal ở thread mới.

### @Async và CompletableFuture

Một method `@Async` chạy trong executor hoặc một `CompletableFuture.supplyAsync(...)` không tự nhiên nhận cùng Reactor subscriber context. Nếu cần ghi audit hoặc xử lý một công việc nền có chủ thể liên quan, nên truyền **identity/authorization context được rút gọn và cho phép** thành dữ liệu tác vụ, hoặc dùng cơ chế context propagation chính thức được thiết kế cho boundary đó.

Không sao chép nguyên Bearer token sang background job để tái sử dụng vô thời hạn. Một tác vụ nền nên có **định danh tác vụ, phạm vi quyền, thời hạn và cách xác thực riêng** phù hợp.

## 13. Reactor Context không phải một nguồn quyền tự thân

Ứng dụng có thể đặt custom values vào Reactor Context:

~~~java
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

Mono<String> requestedTenant = Mono.deferContextual(view ->
    Mono.justOrEmpty(view.<String>getOrEmpty("requestedTenant"))
);

Mono<String> withTenant = requestedTenant
    .contextWrite(Context.of("requestedTenant", "t-7"));
~~~

Nhưng `"requestedTenant"` ở đây chỉ là **ngữ cảnh do code truyền vào**. Nếu nó bắt nguồn từ URL, request header, cookie hoặc body thì nó vẫn là **input có thể do client kiểm soát**. Không được dùng:

~~~java
// KHÔNG AN TOÀN:
// if (contextTenant.equals(order.getTenantId())) allow();
~~~

mà không xác minh user thực sự thuộc tenant và có quyền trên order.

Phân biệt:

| Dữ liệu | Ai xác lập? | Có thể dùng làm chứng cứ phân quyền? |
| --- | --- | --- |
| Authentication từ Resource Server sau token validation | Spring Security và các components được cấu hình đáng tin | Là đầu vào danh tính/quyền chức năng |
| `scope`/`aud`/`iss` từ token được xác minh | Issuer theo contract | Dùng theo chính sách xác thực và phân quyền |
| `requestedTenant` từ request/header/Context tùy chỉnh | Client hoặc application code | Chỉ là ngữ cảnh yêu cầu, **không chứng minh membership** |
| Owner/tenant/share trong DB | Dữ liệu nghiệp vụ được kiểm soát | Nguồn quyết định quan hệ hiện hành |
| Trace ID/correlation ID | Gateway hoặc tracing | Phục vụ quan sát, **không phải authority** |

Đừng coi việc “dữ liệu nằm trong Reactor Context” là đã được framework ký, xác thực hoặc chống sửa đổi. **Nguồn tin cậy nằm ở quy trình xác minh và chính sách**, không nằm ở loại container lưu dữ liệu.

## 14. Đừng lẫn Reactor Context với MDC/logging context

Các hệ thống logging Java thường dùng **MDC** thông qua ThreadLocal. Một pipeline đổi scheduler có thể giữ Reactor Context nhưng **không tự bảo đảm MDC ở thread mới có đủ thông tin** nếu thiếu context-propagation bridge phù hợp.

Ví dụ không nên tin:

~~~java
Mono<String> publisher = currentJwtProvider.currentJwt()
    .publishOn(Schedulers.boundedElastic())
    .map(jwt -> {
        // Một MDC ThreadLocal đặt ở thread khác có thể không có giá trị cũ.
        return jwt.getSubject();
    });
~~~

Để gắn correlation ID vào log, có thể dùng Reactor Context và một cơ chế tích hợp với logging/tracing được **phiên bản Reactor/Spring/Micrometer hỗ trợ**. Nếu chọn dùng automatic context propagation hoặc `ContextSnapshot` ở một số boundary imperative, phải kiểm tra cấu hình và lifecycle của bridge; đừng tự bật mọi cơ chế mà chưa hiểu tác động hiệu năng hoặc rò dữ liệu.

**Không đưa raw access token, refresh token, private claim nhạy cảm hoặc credentials vào MDC.** Trace ID và user ID nội bộ được phép ghi theo chính sách là những dữ liệu khác hẳn với Bearer token.

## 15. Kiểm thử ReactiveSecurityContextHolder với StepVerifier

`StepVerifier` của `reactor-test` cho phép subscribe publisher với reactive context được chuẩn bị, xác nhận kết quả và lỗi mà không cần chạy HTTP server.

Ví dụ một service nhỏ:

~~~java
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

public class CurrentActorService {

    public Mono<String> currentName() {
        return ReactiveSecurityContextHolder.getContext()
            .flatMap(ctx ->
                Mono.justOrEmpty(ctx.getAuthentication()))
            .map(auth -> auth.getName())
            .switchIfEmpty(Mono.error(
                new AuthenticationCredentialsNotFoundException(
                    "Authentication required")));
    }
}
~~~

Test với Authentication được gắn vào **subscriber Context**:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.test.StepVerifier;

class ReactiveCurrentActorTest {

    private final CurrentActorService service =
        new CurrentActorService();

    @Test
    void readsNameFromSubscriberSecurityContext() {
        Authentication alice = new UsernamePasswordAuthenticationToken(
            "alice",
            "unused",
            List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
        );

        StepVerifier.create(
                service.currentName()
                    .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(
                            alice)))
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void rejectsMissingSecurityContext() {
        StepVerifier.create(service.currentName()
                .contextWrite(
                    ReactiveSecurityContextHolder.clearContext()))
            .expectError(AuthenticationCredentialsNotFoundException.class)
            .verify();
    }
}
~~~

Test này xác nhận **cơ chế đọc context trong publisher**, không chứng minh token JWT/opaque đã được xác minh. `UsernamePasswordAuthenticationToken` được dựng trực tiếp là fixture test. Trong production, không tạo token tương tự từ một username trong request rồi đặt vào Reactive Context.

### Test với JWT principal

Nếu service dùng `CurrentJwtProvider.currentJwt()` ở mục 8, có thể tạo Authentication thử nghiệm:

~~~java
import java.time.Instant;
import java.util.List;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import reactor.test.StepVerifier;

Jwt jwt = Jwt.withTokenValue("unit-test-only")
    .header("alg", "RS256")
    .issuer("https://auth.example.com/realms/shop")
    .subject("user-42")
    .issuedAt(Instant.parse("2026-01-01T00:00:00Z"))
    .expiresAt(Instant.parse("2031-01-01T00:00:00Z"))
    .claim("scope", "orders.read")
    .build();

JwtAuthenticationToken auth = new JwtAuthenticationToken(
    jwt, List.of(new SimpleGrantedAuthority("SCOPE_orders.read")));

StepVerifier.create(new CurrentJwtProvider().currentJwt()
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(auth)))
    .expectNext(jwt)
    .verifyComplete();
~~~

Chuỗi `"unit-test-only"` **không phải JWS được ký hợp lệ**. Việc dựng Authentication trực tiếp chỉ thích hợp để kiểm tra service/context; nó không xác minh signature, issuer, audience, `exp` hay token profile.

## 16. WebTestClient: kiểm tra SecurityWebFilterChain thực tế

Trong WebFlux, công cụ tích hợp là **`WebTestClient`**. Có hai kiểu kiểm thử cần phân biệt.

### 16.1. Mock authentication để test authorization

Spring Security Test hỗ trợ `mockJwt()` với WebTestClient trong phiên bản phù hợp:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

webTestClient
    .mutateWith(mockJwt().authorities(
        new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get()
    .uri("/api/orders/123")
    .exchange()
    .expectStatus().isOk();
~~~

Đoạn test này giả định endpoint/fixture trả 200 khi đủ quyền. `mockJwt()` giúp tạo Authentication để **kiểm tra authorization**, nhưng thường **không gửi Bearer token qua decoder thật**. Một test pass không chứng minh JWT expired, sai chữ ký hay sai issuer sẽ bị từ chối.

### 16.2. Gửi Bearer header thật, mock ReactiveJwtDecoder

Để kiểm tra **WebFilter xử lý token và phản hồi HTTP**, nên gửi header `Authorization: Bearer ...` thật rồi mock **`ReactiveJwtDecoder`**, giữ security chain.

Ví dụ dùng Spring Boot, WebTestClient và các phiên bản Spring Test hỗ trợ `@MockitoBean`:

~~~java
import static org.mockito.Mockito.when;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

@SpringBootTest
@AutoConfigureWebTestClient
class WebFluxBearerResponseTest {

    @Autowired WebTestClient client;

    @MockitoBean
    ReactiveJwtDecoder jwtDecoder;

    @Test
    void missingTokenOnProtectedRouteReturns401() {
        client.get().uri("/api/orders/123")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueMatches(
                HttpHeaders.WWW_AUTHENTICATE, "Bearer.*");
    }

    @Test
    void invalidBearerReturns401() {
        when(jwtDecoder.decode("invalid-token"))
            .thenReturn(Mono.error(new BadJwtException("Bad JWT")));

        client.get().uri("/api/orders/123")
            .headers(h -> h.setBearerAuth("invalid-token"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void validTokenWithoutReadScopeReturns403() {
        when(jwtDecoder.decode("valid-without-scope"))
            .thenReturn(Mono.just(jwt(
                "valid-without-scope", "profile.read")));

        client.get().uri("/api/orders/123")
            .headers(h -> h.setBearerAuth("valid-without-scope"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void validTokenWithReadScopeReachesController() {
        when(jwtDecoder.decode("valid-with-scope"))
            .thenReturn(Mono.just(jwt(
                "valid-with-scope", "orders.read")));

        client.get().uri("/api/orders/123")
            .headers(h -> h.setBearerAuth("valid-with-scope"))
            .exchange()
            .expectStatus().isOk();
    }

    private static Jwt jwt(String value, String scope) {
        return Jwt.withTokenValue(value)
            .header("alg", "RS256")
            .issuer("https://auth.example.com/realms/shop")
            .subject("user-42")
            .issuedAt(Instant.parse("2026-01-01T00:00:00Z"))
            .expiresAt(Instant.parse("2031-01-01T00:00:00Z"))
            .claim("aud", List.of("orders-api"))
            .claim("scope", scope)
            .build();
    }
}
~~~

Điều kiện để ví dụ chạy:

- App test thực sự dùng **WebFlux** và cấu hình JWT Resource Server như mục 7.
- Có `GET /api/orders/123` tương ứng; nếu controller còn yêu cầu membership/owner thì phải chuẩn bị fixture phù hợp.
- `@MockitoBean` có trong Spring Test phiên bản sử dụng; với phiên bản Boot cũ hơn có thể dùng `@MockBean` nếu hỗ trợ.
- `ReactiveJwtDecoder` mock chỉ điều khiển outcome; **không xác minh chữ ký thật**.

Muốn kiểm tra JWS signature, `iss`, `aud`, `exp` và JWKS, cần integration test khác dùng **decoder thật**, JWT ký bằng test key, issuer/JWKS test server và validators tương ứng.

### Có thể kiểm tra cả Reactive Context qua HTTP

Một endpoint test được bảo vệ có thể trả `authentication.getName()` đọc từ `ReactiveSecurityContextHolder`. Nếu WebTestClient gửi token được mock decoder chấp nhận và endpoint nhận đúng subject, test chứng minh WebFilter đã **chuyển Authentication sang Reactor Context** để downstream đọc được. Khi gửi token hỏng, endpoint phải không được thực thi.

Đó là kiểm thử giàu ý nghĩa hơn việc chỉ dựng `Authentication` trong unit test, nhưng vẫn chưa thay thế kiểm tra decoder cryptography thật.

## 17. Public endpoint, permitAll và Reactor Context

Nếu WebFlux SecurityWebFilterChain có:

~~~java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/public/**").permitAll()
    .anyExchange().authenticated())
.oauth2ResourceServer(oauth2 ->
    oauth2.jwt(Customizer.withDefaults()))
~~~

thì `permitAll` chỉ nói **authorization không yêu cầu quyền** trên `/public/**`. Nó **không mặc định tắt Bearer authentication** khi client tự gửi token đến endpoint công khai.

| Request public | Hành vi thường gặp |
| --- | --- |
| Không token | Có thể vào handler mà không có JWT Authentication |
| Bearer JWT hợp lệ | Filter xác thực token và handler có thể thấy JWT Authentication trong Reactor Context |
| Bearer JWT sai/hết hạn | Filter có thể trả **401 trước khi permitAll cho đi tiếp** |

Nếu app muốn public route **bỏ qua mọi Bearer token được gửi đến**, cần thiết kế **SecurityWebFilterChain riêng** hoặc cơ chế token converter phù hợp, thay vì gọi `clearContext()` trong controller. Với nhiều chain, phải kiểm tra matcher, thứ tự lựa chọn chain và fallback bảo vệ các đường dẫn còn lại.

### Không tạo dữ liệu fallback làm người dùng thật

Ví dụ:

~~~java
ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName())
    .defaultIfEmpty("guest");
~~~

Cách này có thể phù hợp cho **nhãn hiển thị ở endpoint công khai**, nhưng **không** được coi `guest` là danh tính có quyền. Một endpoint yêu cầu quyền phải được bảo vệ ở filter/method policy và service, không dựa vào string fallback để quyết định truy cập bản ghi.

## 18. Cách nhận biết lỗi từ context và từ quyền nghiệp vụ

Khi một service không đọc được danh tính:

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `getContext()` hoàn tất rỗng | Không có authenticated request; subscriber không mang context; test chưa gắn fixture | Kiểm tra SecurityWebFilterChain và subscription boundary |
| `SecurityContextHolder.getContext()` trả null/anonymous trong WebFlux | Đọc ThreadLocal thay vì Reactor Context | Dùng `ReactiveSecurityContextHolder` |
| Context có Authentication nhưng không phải JWT | Endpoint đang dùng opaque token, anonymous hoặc mechanism khác | Chuyển theo đúng principal type/policy |
| Authenticated, có scope nhưng 403 | Thiếu authority khác, method security, tenant/owner policy | Kiểm tra đúng authorization layer |
| Có danh tính khi ở controller, mất ở background callback | Tạo subscription/future ngoài Reactor hoặc không truyền actor | Compose trong chain hoặc truyền identity đã chuẩn hóa |
| Context đúng sau `publishOn` nhưng MDC rỗng | Reactor Context khác ThreadLocal MDC | Cấu hình tracing/context bridge phù hợp |
| Dùng `.with(mockJwt())` test pass nhưng token thật 401 | Mock bỏ qua decoder/issuer/JWKS | Test với Bearer header và decoder thật hoặc mock boundary rõ ràng |

Khi debug, không ghi nguyên Bearer access token, client secret hoặc toàn bộ JWT claims vào log. Dùng request ID, loại Authentication, issuer/subject được phép ghi, authorities cần thiết và kết quả policy ở mức phù hợp.

## 19. Những hiểu nhầm thường gặp

**“ReactiveSecurityContextHolder là ThreadLocal phiên bản mới.”**  
Không. Nó cung cấp truy cập SecurityContext thông qua **Reactor subscriber Context**. Thread hiện tại có thể thay đổi mà context subscription vẫn được giữ.

**“Gọi getContext() sẽ trả SecurityContext ngay.”**  
Không. Nó trả `Mono<SecurityContext>` được đánh giá trong subscription.

**“publishOn hoặc subscribeOn luôn làm mất identity.”**  
Không. Các toán tử Reactor chuẩn giữ Reactor Context trong cùng subscription. Rủi ro lớn là subscription độc lập và callback ngoài Reactor.

**“Có thể gọi block() để lấy Authentication cho tiện.”**  
Không nên trong WebFlux request flow: nó blocking, có thể tạo subscription riêng và không bảo đảm context đúng.

**“Tạo Authentication từ header username rồi withAuthentication là đủ bảo mật.”**  
Không. `withAuthentication` chỉ đặt đối tượng vào context; nó **không xác thực token**. Production phải đi qua cơ chế authentication được tin cậy.

**“JWT và opaque token có cùng kiểu principal.”**  
Không mặc định. JWT thường có `JwtAuthenticationToken`/`Jwt`, opaque thường có `BearerTokenAuthentication`/`OAuth2AuthenticatedPrincipal`.

**“Có SCOPE_orders.read nghĩa là được đọc mọi order.”**  
Không. Tenant, owner, sharing và business policy vẫn phải kiểm tra.

**“Reactor Context có tenant ID nghĩa là user chắc chắn thuộc tenant.”**  
Không. Một custom context key không phải bằng chứng membership hay ownership.

**“@PreAuthorize luôn chạy dù method tự gọi bên trong cùng bean.”**  
Không chắc. Proxy self-invocation có thể bỏ qua interceptor; cần cấu trúc service/policy đúng.

**“Test mockJwt() đủ chứng minh signature/expiry được kiểm tra.”**  
Không. Nó thường tạo Authentication trực tiếp; muốn kiểm tra decoder phải dùng JWT/JWKS/validators thật hoặc test riêng.

**“permitAll làm filter JWT không xử lý token sai.”**  
Không. Bearer token được gửi vẫn có thể bị xác thực và từ chối trước authorization.

## 20. Checklist áp dụng trong WebFlux Resource Server

1. **Chọn đúng stack:** `SecurityWebFilterChain` + `ServerHttpSecurity` cho WebFlux, không sao chép nguyên `HttpSecurity` Servlet.
2. **Giữ đúng nguồn xác thực:** `ReactiveJwtDecoder` hoặc `ReactiveOpaqueTokenIntrospector` với issuer/audience/time/profile đã được định nghĩa.
3. **Đọc principal qua Reactor:** dùng `ReactiveSecurityContextHolder.getContext()` trong `Mono`/`Flux`, hoặc `@AuthenticationPrincipal` ở WebFlux controller khi phù hợp.
4. **Không phụ thuộc ThreadLocal:** `SecurityContextHolder.getContext()` không phải cách lấy user mặc định trong pipeline reactive.
5. **Không tự subscribe/block:** trả hoặc compose publisher để Spring WebFlux quản lý subscription.
6. **Đặt contextWrite đúng vị trí:** hiểu nó tác động đến upstream tại subscription.
7. **Không coi Reactor Context tự đáng tin:** identity phải đến từ authentication và các token validators, custom key chỉ là dữ liệu.
8. **Bảo vệ nghiệp vụ:** scope/authority không thay tenant membership, ownership, sharing và kiểm tra bản ghi.
9. **Kiểm thử theo hai lớp:** `StepVerifier` kiểm tra context propagation; `WebTestClient` kiểm tra SecurityWebFilterChain, 401/403 và phản hồi HTTP.
10. **Nhận biết boundary async:** khi chuyển sang executor, callback hoặc background task, truyền actor đã được chuẩn hóa hoặc dùng context-propagation mechanism được thiết kế rõ ràng.

**Điểm cần nhớ:** Trong Spring Security WebFlux, danh tính đã xác thực **đi cùng reactive subscription**, không mặc nhiên đi cùng thread. `ReactiveSecurityContextHolder` là cầu nối giữa kết quả Bearer authentication và các publisher downstream. Dùng nó đúng cách nghĩa là **đọc SecurityContext khi subscribe, giữ pipeline thống nhất, hiểu phạm vi `contextWrite` và không vượt qua bước xác minh access token**. Sau khi đã có principal đáng tin, Resource Server vẫn phải kiểm tra quyền đối với **đúng endpoint, tenant và tài nguyên nghiệp vụ**.
