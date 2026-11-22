# 20.11. ReactiveSecurityContextHolder, principal và propagation của Reactor Context

## 1. Vì sao bài toán SecurityContext thay đổi khi chuyển sang Reactive?

Trong ứng dụng **Spring Security OAuth 2.0/OIDC Client** chạy trên Spring WebFlux, người dùng có thể đăng nhập qua OAuth2 Login hoặc OpenID Connect (OIDC), sau đó gọi các endpoint mà ứng dụng bảo vệ. Ứng dụng cần biết:

- Request đang thuộc về **principal** nào?
- Authentication đã thành công hay người dùng vẫn **anonymous**?
- Authorities/roles/scopes nào đã được gắn với authentication?
- Khi request đi qua `Mono`, `Flux`, `flatMap`, `publishOn`, `WebClient` hoặc một asynchronous boundary, thông tin xác thực có còn được truy cập đúng không?
- Khi không còn HTTP request, ví dụ `@Scheduled` hoặc consumer xử lý message, có được giả định tồn tại principal từ lần login trước không?

Trong Servlet MVC, nhiều developer quen dùng:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
```

`SecurityContextHolder` theo chiến lược thông dụng lưu context bằng **`ThreadLocal`**. Mô hình request-per-thread khiến cách truy cập này có vẻ tự nhiên trong nhiều đoạn code Servlet đồng bộ.

Trong **Reactive**, một request không nhất thiết được xử lý bởi đúng một thread từ đầu đến cuối. Operators có thể đổi thread, đợi I/O không chặn, ghép nhiều publisher và chạy callback sau khi inbound method đã trả về. Nếu dùng một `ThreadLocal` như là “chủ nhân” của request, có thể **không tìm thấy context** hoặc, khi tự xử lý không an toàn, **lấy sai context của một tác vụ khác**.

Spring Security dùng:

```java
org.springframework.security.core.context.ReactiveSecurityContextHolder
```

để gắn `SecurityContext` với **Reactor Context của subscription**, thay vì mặc định lấy authentication bằng ThreadLocal.

> Ý chính của bài: **ReactiveSecurityContextHolder đọc/ghi SecurityContext qua Reactor Context; context đi theo subscription trong reactive chain, không đơn thuần đi theo thread.** Chính cách xây publisher, subscribe và chuyển qua những API không thuộc Reactor quyết định context có đi tới đúng nơi hay không.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `SecurityContextHolder` với `ReactiveSecurityContextHolder`.
2. Phân biệt `SecurityContext`, `Authentication`, `principal` và `OAuth2AuthorizedClient`.
3. Hiểu Reactor Context thuộc **subscriber/subscription**, khác `ThreadLocal`, method arguments và HTTP headers.
4. Dùng `ReactiveSecurityContextHolder.getContext()`, `withAuthentication(...)`, `withSecurityContext(...)` và `clearContext()` đúng phạm vi.
5. Lấy principal trong WebFlux controller hoặc reactive service một cách có kiểm soát.
6. Nhận biết `OidcUser`, `OAuth2User` và các claims cần kiểm tra.
7. Hiểu tác động của `flatMap`, `publishOn`, `subscribeOn`, `contextWrite`, `deferContextual`, `subscribe()` và `block()`.
8. Biết cách tránh làm mất hoặc rò rỉ authentication khi gọi WebClient, xử lý async, chia sẻ `Mono` hoặc dùng cache.
9. Viết test với `StepVerifier`, `WebTestClient` và Spring Security Test.
10. Chẩn đoán hiện tượng “controller thấy user nhưng service thấy anonymous” hoặc “callback không đọc được principal”.

Các domain, users và tokens trong ví dụ là dữ liệu minh họa. Các đoạn code tập trung vào **Spring WebFlux + Spring Security reactive stack**, với Java hiện đại (Java 17+ cho một số pattern matching).

---

## 2. Mô hình tư duy: ThreadLocal và Reactor Context

### 2.1. Cách hình dung của Servlet đồng bộ

```text
HTTP request của Alice
    |
    v
Servlet Thread T-17
    |
    +-- SecurityContextHolder / ThreadLocal
    |       Authentication(Alice)
    |
    +-- Controller
    +-- Service
    +-- Repository
    |
    v
HTTP response
```

Trong một chuỗi gọi đồng bộ trên cùng thread, code có thể đọc `SecurityContextHolder`. Nhưng ngay trong Servlet, nếu tự đưa công việc sang một executor hoặc task khác, `ThreadLocal` cũng không tự đi theo mọi thread.

### 2.2. Cách hình dung trong Reactor

```text
HTTP request của Alice
    |
    v
Reactor subscription S-A
    |
    +-- Reactor Context
    |       SecurityContext(Authentication(Alice))
    |
    +-- Operator 1   [thread reactor-http-1]
    |
    +-- flatMap(...) [I/O bất đồng bộ]
    |
    +-- publishOn(...) [thread parallel-3]
    |
    +-- Operator 2   [vẫn thuộc subscription/context thích hợp]
    |
    v
HTTP response
```

Một request khác:

```text
HTTP request của Bob
    |
    v
Reactor subscription S-B
    |
    +-- Reactor Context
            SecurityContext(Authentication(Bob))
```

Hai subscriptions có thể chia sẻ các threads trong pool, nhưng **không được chia sẻ SecurityContext của nhau** chỉ vì chạy trên cùng thread.

### 2.3. Bảng so sánh

| Vấn đề | `ThreadLocal` | Reactor `Context` |
|---|---|---|
| Gắn với | Thread cụ thể | Subscriber/subscription của reactive pipeline |
| Truy cập thường thấy | `ThreadLocal.get()` | `Mono.deferContextual(...)`, `ReactiveSecurityContextHolder.getContext()` |
| Đổi thread | Không tự chuyển giá trị sang thread mới | Các Reactor operators thông thường bảo toàn subscriber context |
| Bất biến | Giá trị của ThreadLocal có thể thay đổi | Reactor `Context` là cấu trúc immutable/copy-on-write |
| Thời điểm có ý nghĩa | Trong khi thread giữ giá trị | Khi publisher được **subscribe** với context tương ứng |
| Nguy cơ phổ biến | Thiếu hoặc lẫn giá trị giữa threads | Tách subscription, contextWrite sai vị trí, cache dữ liệu user dùng chung |
| Dùng cho Security của WebFlux | Không phải nguồn chính của reactive chain | Là cơ chế cơ bản Spring Security sử dụng |

**Không có quy tắc “đổi thread là mất Reactor Context”.** Một `publishOn`/`subscribeOn` bình thường không giống một `new Thread()` hoặc một `CompletableFuture` tự quản lý. Ranh giới quan trọng là **publisher/subscription và khả năng bridge context**, không chỉ tên thread.

## 3. Những đối tượng Spring Security cần phân biệt

### 3.1. SecurityContext

Interface:

```java
org.springframework.security.core.context.SecurityContext
```

Nó chứa `Authentication`:

```java
Authentication authentication = securityContext.getAuthentication();
```

Một `SecurityContext` có thể không có authentication (đặc biệt ngoài ngữ cảnh request đã xác thực).

### 3.2. Authentication

Interface:

```java
org.springframework.security.core.Authentication
```

Những phương thức cần hiểu:

| API | Ý nghĩa |
|---|---|
| `getPrincipal()` | Chủ thể được xác thực; kiểu cụ thể tùy cơ chế login |
| `getName()` | Tên định danh do authentication cung cấp |
| `getAuthorities()` | Các `GrantedAuthority` ứng dụng sử dụng |
| `isAuthenticated()` | Trạng thái của authentication object, **không đủ** để kết luận không phải anonymous |
| `getCredentials()` | Credentials nếu cơ chế sử dụng; không log |
| `getDetails()` | Metadata phụ trợ, phụ thuộc cơ chế authentication |

Với OAuth2 Login, một implementation thường gặp là:

```java
org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken
```

Với OIDC Login, `OAuth2AuthenticationToken.getPrincipal()` thường chứa một `OidcUser`. Với OAuth2 Login không phải OIDC, principal có thể là `OAuth2User`.

### 3.3. Principal

Khái niệm `Principal` là danh tính đã được mô tả bởi authentication, nhưng không phải lúc nào kiểu runtime cũng là `java.security.Principal` đơn thuần.

Ví dụ:

```java
Authentication authentication = ...;

String name = authentication.getName();
Object principal = authentication.getPrincipal();
```

`principal` có thể là một `OidcUser`, `OAuth2User`, `UserDetails`, một `String` hoặc object riêng theo cơ chế xác thực. Không cast trực tiếp sang `OidcUser` nếu endpoint cũng cho phép những cơ chế authentication khác.

### 3.4. OAuth2AuthorizedClient không phải Authentication

Một object:

```java
org.springframework.security.oauth2.client.OAuth2AuthorizedClient
```

chứa client registration, access token và có thể refresh token cho một authorization đã được cấp.

Phân biệt:

| Thành phần | Trả lời câu hỏi |
|---|---|
| `SecurityContext` | Authentication nào được gắn với reactive subscription hiện tại? |
| `Authentication` | Principal nào đã được xác thực? Có authorities nào? |
| `OidcUser` / `OAuth2User` | Những attributes/claims nào mô tả user? |
| `OAuth2AuthorizedClient` | OAuth2 client nào có access token nào để gọi API? |
| `ReactiveOAuth2AuthorizedClientManager` | Authorized client có cần cấp hoặc làm mới token không? |

**Có SecurityContext của Alice không đồng nghĩa đã có access token hợp lệ cho mọi API.** Và có một access token từ Client Credentials Grant cũng **không làm cho background job trở thành người dùng Alice**.

## 4. Reactor Context là gì?

Trong Reactor, `Context` là một tập dữ liệu bất biến theo cặp khóa–giá trị, gắn với subscriber.

Các API thường gặp:

```java
reactor.util.context.Context
reactor.util.context.ContextView
reactor.core.publisher.Mono
reactor.core.publisher.Flux
```

Ví dụ đơn giản chưa có security:

```java
import reactor.core.publisher.Mono;

Mono<String> greeting =
    Mono.deferContextual(contextView -> {
        String language =
            contextView.getOrDefault("language", "en");

        return Mono.just(
            "vi".equals(language) ? "Xin chào" : "Hello"
        );
    });

Mono<String> result =
    greeting.contextWrite(context ->
        context.put("language", "vi")
    );
```

Khi `result` được subscribe, `deferContextual` có thể đọc `"vi"` từ Reactor Context.

### 4.1. Context không phải một biến toàn cục

Sai cách hình dung:

```text
Application singleton Context
    -> Alice login
    -> toàn ứng dụng đổi thành principal Alice
```

Đúng:

```text
Subscription của Alice -> Context chứa Authentication Alice
Subscription của Bob   -> Context chứa Authentication Bob
```

Một `Context` chỉ có ý nghĩa khi nó được gắn vào subscription và operators tham gia đúng chain.

### 4.2. Context được quan sát vào thời điểm subscription

Một Reactor `Mono` thường là **cold publisher**: tạo publisher chưa chắc thực hiện công việc.

```java
Mono<String> mono = ReactiveSecurityContextHolder.getContext()
    .map(context -> context.getAuthentication().getName());
```

Tại thời điểm khai báo `mono`, user chưa chắc được đọc. Việc đọc diễn ra khi publisher được subscribe, trong context của subscription đó.

Điều này lý giải vì sao:

- Tạo publisher trong controller chưa có nghĩa đã lấy security context ngay lúc đó.
- Một publisher bị giữ lại rồi subscribe sau, dưới context khác, có thể đọc context khác hoặc không có context.
- Tự gọi `subscribe()` tạo một subscription riêng và có thể tách khỏi inbound request context.

### 4.3. Reactor Context không tự gửi dữ liệu qua mạng

Dữ liệu trong Context **không tự trở thành HTTP header**, JWT, SQL parameter hoặc message attribute.

Nếu dùng WebClient, cần cấu hình OAuth2 Client filter hoặc explicit headers để chọn token phù hợp. Không coi Reactor Context là một kênh tự động truyền credentials tới mọi API.

## 5. ReactiveSecurityContextHolder: API trọng tâm

Class:

```java
org.springframework.security.core.context.ReactiveSecurityContextHolder
```

Các phương thức chính:

| API | Chức năng |
|---|---|
| `getContext()` | Đọc `Mono<SecurityContext>` từ Reactor Context của subscription hiện tại |
| `withSecurityContext(Mono<? extends SecurityContext>)` | Tạo Reactor `Context` mang một publisher cung cấp SecurityContext |
| `withAuthentication(Authentication)` | Tạo Reactor `Context` mang Authentication bằng một SecurityContext phù hợp |
| `clearContext()` | Trả function loại bỏ SecurityContext khỏi Context theo semantics API |

Ở mức khái niệm:

```java
Mono<SecurityContext> current =
    ReactiveSecurityContextHolder.getContext();
```

Không phải:

```java
SecurityContext current =
    ReactiveSecurityContextHolder.getContext(); // Sai kiểu
```

Vì kết quả là **`Mono`**, không phải một object đồng bộ lấy trực tiếp từ thread.

### 5.1. Lấy Authentication an toàn

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;

public Mono<Authentication> currentAuthentication() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .filter(authentication -> authentication != null);
}
```

Nếu context không tồn tại hoặc không có authentication, publisher có thể kết thúc **không phát ra giá trị**.

Tránh:

```java
Authentication auth = ReactiveSecurityContextHolder
    .getContext()
    .block()
    .getAuthentication();
```

Đoạn trên sai mô hình trong reactive pipeline vì có thể chặn event loop, và `block()` tạo subscription riêng không nhất thiết có security context từ upstream.

### 5.2. Lấy tên principal

```java
public Mono<String> currentPrincipalName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .filter(authentication -> authentication != null)
        .map(Authentication::getName);
}
```

Ở endpoint đã được security chain bảo vệ, cách này hữu ích khi business service cần tên principal.

Tuy nhiên, ở endpoint anonymous, kết quả có thể empty hoặc có anonymous authentication, tùy cấu hình. **Không kiểm tra quyền chỉ bằng việc string name khác rỗng**. Business authorization phải dùng Authentication/authorities và request authorization policy đáng tin.

### 5.3. Khi cần thông báo lỗi nếu context thiếu

```java
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;

public Mono<String> requirePrincipalName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .filter(authentication -> authentication != null)
        .map(Authentication::getName)
        .switchIfEmpty(Mono.error(
            new AuthenticationCredentialsNotFoundException(
                "Reactive authentication is required"
            )
        ));
}
```

Lỗi này có thể được Spring Security exception translation xử lý theo vị trí code trong filter chain. Trong nghiệp vụ thực tế, thường bảo vệ endpoint ngay tại `authorizeExchange()` và tránh tự tạo logic authentication rải rác.

## 6. `withAuthentication(...)`: đưa context vào một publisher

Một ví dụ đơn giản để minh họa API trong test hoặc một luồng được kiểm soát:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Authentication alice =
    UsernamePasswordAuthenticationToken.authenticated(
        "alice",
        "N/A",
        AuthorityUtils.createAuthorityList("ROLE_USER")
    );

Mono<String> name =
    ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName())
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(alice)
        );
```

Khi publisher được subscribe với context trên, `getContext()` sẽ thấy authentication của Alice.

### 6.1. API trả Reactor Context, không phải thay đổi thread-local

`withAuthentication(alice)` **không giống**:

```java
SecurityContextHolder.getContext().setAuthentication(alice);
```

Nó trả một `reactor.util.context.Context` để kết hợp vào **một subscription** bằng `contextWrite(...)`.

Không nên làm:

```java
ReactiveSecurityContextHolder.withAuthentication(alice);

// Chỉ gọi hàm rồi bỏ kết quả; không gắn vào publisher nào.
```

Không có subscription được cấu hình thì không có gì buộc các operators khác đọc được context này.

### 6.2. Không cho browser tự cung cấp Authentication

Đoạn ví dụ tạo `UsernamePasswordAuthenticationToken.authenticated(...)` nhằm mô phỏng **test/trusted infrastructure**, không phải cách cho một endpoint public tự xác thực user từ request parameter.

Sai thiết kế:

```text
GET /api?user=admin
    -> new authenticated Authentication("admin")
    -> contextWrite(...)
    -> coi như user admin thật
```

Authentication phải đến từ **authentication manager/provider** đã xác minh credential hoặc token phù hợp và policy bảo mật của Spring Security. `contextWrite(...)` không tự kiểm chứng danh tính.

## 7. `withSecurityContext(...)`: cung cấp cả SecurityContext

Đôi khi application/test đã có `SecurityContext` hoặc muốn truyền một publisher cung cấp context.

```java
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextImpl;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

SecurityContext securityContext =
    new SecurityContextImpl(aliceAuthentication);

Mono<String> value =
    loadSomething()
        .contextWrite(
            ReactiveSecurityContextHolder.withSecurityContext(
                Mono.just(securityContext)
            )
        );
```

`aliceAuthentication` và `loadSomething()` là những objects/methods đã được cung cấp bởi code minh họa xung quanh.

Khác biệt:

- `withAuthentication(authentication)` tiện lợi khi đã có Authentication.
- `withSecurityContext(Mono<? extends SecurityContext>)` phù hợp khi đã có publisher cung cấp SecurityContext.

Spring Security có thể dùng dạng lazy publisher vì security context có thể được lấy bất đồng bộ từ `ServerSecurityContextRepository`.

### 7.1. Không tự đặt key nội bộ trong Reactor Context

Tránh cách viết:

```java
context.put("SECURITY_CONTEXT", authentication);
```

rồi nghĩ `ReactiveSecurityContextHolder.getContext()` sẽ tự đọc được.

Spring Security có contract và key nội bộ của chính nó. Hãy dùng **public API của `ReactiveSecurityContextHolder`**, không suy đoán key lưu trữ.

### 7.2. `clearContext()` thay đổi phạm vi thấy authentication

```java
Mono<String> withoutInheritedContext =
    somePublisher
        .contextWrite(
            ReactiveSecurityContextHolder.clearContext()
        );
```

Có thể dùng khi cần loại bỏ context được kế thừa trong một phạm vi Reactor nhất định. Không dùng `clearContext()` như một giải pháp logout hay revoke token hoàn chỉnh.

**Logout** có thể cần xóa/invalid session, cập nhật `ServerSecurityContextRepository`, xử lý OIDC logout, và quản lý OAuth2AuthorizedClient/token theo chính sách. Xóa context của một subscription **không xóa phiên đăng nhập toàn ứng dụng**.

---

## 8. Nguyên tắc quan trọng nhất của `contextWrite`

Reactor Context được truyền theo hướng **từ subscriber về phía upstream** trong quá trình subscription. Vì thế **vị trí** `contextWrite` trong chain quyết định operators nào thấy context.

Ví dụ:

```java
Mono<String> source =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());

Mono<String> result =
    source.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(alice)
    );
```

`source` ở upstream của `contextWrite` có thể thấy authentication Alice khi `result` được subscribe.

### 8.1. Ví dụ đặt `contextWrite` ở giữa

```java
Mono<String> pipeline =
    ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName())
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(alice)
        )
        .map(name -> "Hello " + name);
```

`getContext()` ở upstream thấy Alice. `map` phía cuối xử lý tên đã phát ra; nó không nhất thiết trực tiếp đọc Reactor Context.

Nếu phía downstream còn có operator khác chủ động gọi `ReactiveSecurityContextHolder.getContext()` trong một publisher riêng, nó cần context của subscription tại đúng vị trí. Không nghĩ “một lần contextWrite sẽ thay đổi toàn bộ chương trình mãi mãi”.

### 8.2. Ví dụ hai nhánh và hai contexts

```java
Mono<String> aliceName =
    currentPrincipalName().contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(alice)
    );

Mono<String> bobName =
    currentPrincipalName().contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(bob)
    );
```

Hai publishers có thể cùng dùng method `currentPrincipalName()` nhưng được subscribe với contexts khác nhau. Đó là hành vi đúng: **context thuộc subscription**, không thuộc method singleton.

### 8.3. `contextWrite` không mutate context gốc

`Context` của Reactor có semantics bất biến; `contextWrite` tạo **context view mới** cho các operators upstream phù hợp. Nó không thay đổi authentication cho những requests/users không thuộc subscription này.

## 9. `deferContextual(...)`: đọc context vào đúng thời điểm

Ngoài `ReactiveSecurityContextHolder`, Reactor cung cấp:

```java
Mono.deferContextual(...)
Flux.deferContextual(...)
```

để đọc dữ liệu context tại **subscription time**.

Ví dụ kết hợp một correlation ID với principal:

```java
import reactor.core.publisher.Mono;

Mono<String> tracedPrincipal =
    Mono.deferContextual(contextView -> {

        String requestId =
            contextView.getOrDefault("request-id", "unknown");

        return ReactiveSecurityContextHolder.getContext()
            .map(securityContext -> {
                Authentication authentication =
                    securityContext.getAuthentication();

                return requestId + ":" + authentication.getName();
            });
    })
    .contextWrite(context ->
        context.put("request-id", "req-001")
    );
```

Nếu publisher được subscribe dưới security context của Alice, kết quả có thể như:

```text
req-001:alice
```

Không nên đặt **access token, refresh token hoặc client secret** vào Reactor Context chỉ để tiện dùng trong log. Reactor Context không phải kho secrets hay authorized client store.

### 9.1. Dùng context khi cần, không snapshot context quá sớm

Một anti-pattern:

```java
// Không nên biến SecurityContext trong một subscription
// thành static/global state dùng cho các subscriptions khác.
static Authentication currentUser;
```

Reactive operators có thể chạy sau khi method tạo publisher trả về; global mutable state sẽ gây nhầm principal giữa requests.

Thay vào đó, đọc context trong publisher hoặc truyền một immutable value đã được xác minh như stable user ID **qua method arguments** khi business flow cần.

## 10. Principal trong Spring WebFlux controller

WebFlux có thể cung cấp principal từ ngữ cảnh request mà không bắt controller phải tự truy cập low-level context.

Ví dụ với:

```java
import java.security.Principal;
import org.springframework.web.server.ServerWebExchange;
```

Controller:

```java
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class PrincipalController {

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(
            ServerWebExchange exchange) {

        return exchange.getPrincipal()
            .map(principal -> Map.of(
                "name",
                principal.getName()
            ));
    }
}
```

`ServerWebExchange.getPrincipal()` cung cấp một `Mono<Principal>` đại diện principal của exchange khi có.

Để endpoint yêu cầu authentication, phải bảo vệ đường dẫn bằng Spring Security `authorizeExchange()`. Nếu request anonymous, `getPrincipal()` có thể empty hoặc có principal theo cấu hình authentication; không giả định luôn là người dùng thật.

### 10.1. Có thể inject Authentication hoặc Principal

WebFlux hỗ trợ nhận một số dạng principal/authentication qua method arguments và annotations khi resolver tương ứng được cấu hình.

Ví dụ dưới đây tránh phụ thuộc vào kiểu principal cụ thể:

```java
@GetMapping("/api/my-name")
public Mono<String> myName(ServerWebExchange exchange) {
    return exchange.getPrincipal()
        .map(Principal::getName);
}
```

Nếu muốn truy cập authorities, dùng `Authentication` thông qua `ReactiveSecurityContextHolder` hoặc một resolver phù hợp, vì `java.security.Principal` chỉ có `getName()`.

### 10.2. Đừng trả toàn bộ Authentication trực tiếp ra API

Không nên:

```java
@GetMapping("/api/debug-auth")
public Mono<Authentication> debugAuth() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication);
}
```

Một `Authentication` có thể chứa details/credentials hoặc nested principal attributes không dành cho frontend. Chỉ trả những trường được nghiệp vụ phê duyệt như stable user ID hoặc tên hiển thị.

---

## 11. Principal khi đăng nhập OAuth2 và OIDC

Với OAuth2 Login, authentication thường là:

```java
org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken
```

Principal:

```java
org.springframework.security.oauth2.core.user.OAuth2User
```

Với OIDC Login, principal thường là:

```java
org.springframework.security.oauth2.core.oidc.user.OidcUser
```

`OidcUser` có ID Token đã được xử lý/xác minh theo OIDC authentication flow, cùng claims thích hợp.

### 11.1. Ví dụ đọc principal theo loại

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.core.user.OAuth2User;

public String describe(Authentication authentication) {
    if (!(authentication instanceof OAuth2AuthenticationToken oauth2)) {
        return "Other authentication";
    }

    Object principal = oauth2.getPrincipal();

    if (principal instanceof OidcUser oidcUser) {
        String issuer =
            oidcUser.getIdToken().getIssuer().toString();

        String subject =
            oidcUser.getIdToken().getSubject();

        return "OIDC " + issuer + " | " + subject;
    }

    if (principal instanceof OAuth2User oauth2User) {
        return "OAuth2 " + oauth2User.getName();
    }

    return "Unsupported principal type";
}
```

Ở đây:

- `getAuthorizedClientRegistrationId()` của `OAuth2AuthenticationToken` có thể cho biết registration được dùng khi đăng nhập.
- `OidcUser` cho phép đọc ID Token và OIDC claims.
- `OAuth2User` của provider OAuth2 không OIDC có thể dùng schema attributes riêng.
- Không cast mọi `Authentication.getPrincipal()` thành OIDC user.

### 11.2. Phân biệt name với external identity

Với OIDC, một identity đáng tin thường dựa trên **`(iss, sub)`**. Không dùng email làm khóa duy nhất để ghép các tài khoản từ nhiều issuers.

Email:

- Có thể đổi.
- Có thể không được provider trả về.
- Có thể chưa verified.
- Có thể được tái sử dụng.
- Không đại diện namespace issuer.

`Authentication.getName()` có thể là subject hoặc một tên do mapping customization cung cấp; kiểm tra cơ chế đang sử dụng trước khi coi nó là stable identity cho storage.

### 11.3. Không suy access token từ principal

OIDC principal mang ID Token/claims để **xác thực danh tính**. Khi gọi Resource Server API, ứng dụng cần **OAuth2 access token** phù hợp audience/scope, thường nằm trong `OAuth2AuthorizedClient`.

Không lấy ID Token từ `OidcUser` rồi gửi:

```http
Authorization: Bearer ID_TOKEN_VALUE
```

chỉ vì API nhận JWT. ID Token không được dùng làm access token cho API tùy ý.

## 12. Cấu hình Spring Security Reactive OAuth2 Login

Ví dụ dependencies với Spring Boot 3.x:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
```

Một `application.yml` minh họa:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate-idp
            client-id: ${CORPORATE_CLIENT_ID}
            client-secret: ${CORPORATE_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          corporate-idp:
            issuer-uri: https://id.example.net
```

Các URL và credentials là ví dụ. Đối với deployment thật, cần dùng secret manager hoặc biến môi trường bảo vệ, và xác minh provider metadata, redirect URI, TLS, scopes và các yêu cầu PKCE tương ứng.

### 12.1. SecurityWebFilterChain

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfiguration {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/", "/public/**").permitAll()
                .anyExchange().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
```

Ý nghĩa:

1. Spring Security bảo vệ các exchanges theo policy.
2. Khi user đăng nhập qua OAuth2/OIDC, reactive security filters xử lý authentication.
3. `SecurityContext` được cung cấp trong reactive execution context phù hợp.
4. Controller/service có thể truy xuất context qua `ReactiveSecurityContextHolder`.

`oauth2Client()` hỗ trợ chức năng OAuth2 Client khi ứng dụng cần authorized clients gọi API; có ứng dụng chỉ cần `oauth2Login()` tùy kiến trúc.

**Không sử dụng `HttpSecurity`/`SecurityFilterChain` của Servlet cho WebFlux security server.** WebFlux sử dụng `ServerHttpSecurity`/`SecurityWebFilterChain`.

## 13. Spring Security đưa context vào Reactor ở đâu?

Trong WebFlux, request đi qua chuỗi **`WebFilter`** của Spring Security.

Về mặt kiến trúc:

```text
HTTP Request
    |
    v
WebFilterChainProxy
    |
    +-- Reactive security filters
    |     |
    |     +-- Authentication mechanism (OAuth2 Login / other)
    |     +-- SecurityContext repository
    |     +-- Reactor Context integration
    |     +-- Authorization checks
    |
    v
DispatcherHandler
    |
    v
Controller -> Mono/Flux -> Service
    |
    v
HTTP Response
```

Một số implementation như `ReactorContextWebFilter` có nhiệm vụ phối hợp `ServerSecurityContextRepository` và Reactor Context, trong khi các authentication filters xử lý việc xác thực và lưu trạng thái khi thích hợp.

### 13.1. Trách nhiệm của ServerSecurityContextRepository

WebFlux có abstraction:

```java
org.springframework.security.web.server.context.ServerSecurityContextRepository
```

Nó cung cấp thao tác đọc/lưu `SecurityContext` liên quan tới một `ServerWebExchange`, ví dụ trong session-based authentication hoặc cơ chế cấu hình khác.

Lưu ý quan trọng:

- **Reactor Context**: phạm vi context **trong một subscription**.
- **ServerSecurityContextRepository**: có thể lưu/khôi phục SecurityContext **giữa các HTTP requests** theo kiến trúc.

Một `contextWrite` trong publisher **không tự persist authentication sang request tiếp theo**.

### 13.2. Còn WebSession thì sao?

OIDC/OAuth2 Login của web application thường cần cơ chế quản lý session/state/authorization request. Sau login thành công, security context có thể được lưu theo cơ chế `ServerSecurityContextRepository` cấu hình.

Không thể thay nguyên hệ thống session management bằng:

```java
someMono.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(authentication)
);
```

Đoạn này chỉ gắn context cho một vùng subscription, không tự xây login session, không kiểm tra `state`/nonce/PKCE, không phát cookie và không xử lý logout.

### 13.3. Stateless Resource Server là bài toán khác

Một WebFlux API đóng vai trò OAuth2 **Resource Server** có thể xác thực Bearer token trên **mỗi request** và không cần session đăng nhập.

Khi request đến có Bearer token hợp lệ, Resource Server authentication được tạo theo config và Reactor Context chứa authentication phù hợp cho request đó.

Điều này khác với ứng dụng **OAuth2/OIDC Client** thực hiện login rồi gọi downstream APIs. Có thể một ứng dụng vừa là client vừa là resource server, nhưng mỗi cơ chế có security policy riêng.

---

## 14. Propagation qua `map`, `flatMap` và các publishers liên tiếp

Reactor Context đi theo subscription trong một reactive chain bình thường.

Ví dụ:

```java
public Mono<String> greetFromSecurityContext() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .flatMap(name -> Mono.just("Hello " + name));
}
```

Khi được thực thi trong WebFlux request đã có context, các operators trong chain có thể truy cập principal hợp lệ theo subscription.

### 14.1. Dùng flatMap để kết hợp với business logic

```java
public Mono<AccountSummary> myAccount() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .flatMap(accountService::findSummaryByPrincipalName);
}
```

`accountService.findSummaryByPrincipalName` là method minh họa trả `Mono<AccountSummary>`.

Ưu điểm: Authentication được đọc đúng trong reactive pipeline, rồi stable principal ID được truyền tường minh vào business service.

Tuy nhiên:

- `getName()` cần được mapping thành một identity ổn định theo cơ chế authentication.
- Nếu yêu cầu tenant isolation, identity phải chứa hoặc suy ra namespace đáng tin.
- Việc đọc được principal không tự cho phép user xem mọi account.
- Business service cần kiểm tra ownership/authorization theo dữ liệu hiện tại.

### 14.2. Không ném authorization check ra khỏi reactive chain

Sai:

```java
// Anti-pattern: mong có authentication đồng bộ ngoài subscription.
String currentUser =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .block();
```

Đúng:

```java
return ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName())
    .flatMap(accountService::findSummaryByPrincipalName);
```

Một pipeline rõ ràng giúp tránh tạo subscriptions mới và tránh chặn event loop.

## 15. `publishOn` và `subscribeOn`: đổi thread không tự làm mất Context

Reactor có operators:

```java
publishOn(Scheduler scheduler)
subscribeOn(Scheduler scheduler)
```

Ví dụ:

```java
import reactor.core.scheduler.Schedulers;

Mono<String> name =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .publishOn(Schedulers.parallel())
        .map(value -> value.toUpperCase())
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(alice)
        );
```

Khi mọi operators nằm trong cùng reactive subscription hợp lệ, `publishOn` thay thread thực thi phần downstream nhưng **không mặc định loại bỏ Reactor Context**.

### 15.1. Không đánh đồng Reactor Context với MDC

Dù Reactor Context vẫn có, logging framework **MDC** thường dùng ThreadLocal. Vì vậy log có thể mất request ID hoặc principal label sau khi đổi scheduler nếu không có cầu nối context được cấu hình.

Ví dụ:

```text
ReactiveSecurityContextHolder.getContext()
    -> vẫn thấy Alice

MDC.get("user")
    -> có thể null trên thread khác
```

Hai kết quả này **không mâu thuẫn** vì chúng đọc từ các cơ chế lưu trữ khác nhau.

### 15.2. Không dùng Schedulers.boundedElastic chỉ để “giữ SecurityContext”

`boundedElastic()` hữu ích khi phải cô lập một tác vụ blocking không thể tránh trong một phần thích hợp của reactive application, nhưng nó **không phải cơ chế bảo mật hoặc truyền authentication**.

Với WebFlux stack, ưu tiên driver/HTTP client non-blocking. Khi dùng blocking adapter, cần thiết kế ranh giới rõ ràng và không kỳ vọng ThreadLocal/security context sẽ tự được cập nhật.

## 16. Một ranh giới nguy hiểm: tự gọi `subscribe()`

Một anti-pattern phổ biến:

```java
@GetMapping("/api/start")
public Mono<String> start() {

    someService.doWork()
        .subscribe(); // Tạo một subscription độc lập.

    return Mono.just("started");
}
```

`subscribe()` thủ công:

- Tạo một **subscription mới**.
- Không tự kế thừa đầy đủ Reactor Context của inbound request theo cách bạn có thể mặc định dựa vào.
- Tách error handling khỏi HTTP response.
- Có thể chạy sau khi request/session lifecycle đã đổi.
- Khi user disconnect/logout, công việc detached vẫn có thể tiếp tục.
- Làm trace/test/backpressure/cancellation khó kiểm soát.

Nếu `doWork()` cần principal và gọi `ReactiveSecurityContextHolder.getContext()`, subscription mới có thể không thấy security context.

### 16.1. Giữ công việc trong một chain

Thay vì tự subscribe:

```java
@GetMapping("/api/start")
public Mono<String> start() {
    return someService.doWork()
        .thenReturn("completed");
}
```

Ở đây Spring WebFlux quản lý subscription phục vụ HTTP response; security context được cung cấp trong phạm vi request thích hợp.

### 16.2. Nếu thực sự phải chạy nền?

Không nên cố giữ một inbound request subscription sống vô hạn.

Thay vào đó:

1. Xác thực và kiểm tra quyền ngay tại HTTP boundary.
2. Tạo job command/record với **stable account ID** và thông tin nghiệp vụ tối thiểu cần thiết.
3. Đưa job vào scheduler/queue được quản lý.
4. Khi worker thực thi, xác thực quyền gọi external API bằng **cơ chế service authorization hoặc delegated authorization đã được cấp hợp lệ**, chứ không mặc định “Alice vẫn đang có ReactiveSecurityContext”.
5. Ghi audit theo chính sách, không sao chép raw access/refresh token vào message payload.

`ReactiveSecurityContextHolder` của một HTTP request không phải một cơ chế lưu danh tính để tái sử dụng cho background worker.

## 17. Khác biệt giữa một reactive chain và `CompletableFuture`

Reactor Context được thiết kế cho Reactor subscribers. Một call ra ngoài như:

```java
CompletableFuture.supplyAsync(() -> {
    // Chạy trên executor khác.
    return callBlockingApi();
});
```

không mặc nhiên mang Reactor Context vào callback được chạy bởi executor.

Ví dụ:

```java
Mono<String> result = Mono.fromFuture(
    CompletableFuture.supplyAsync(() -> {
        // Không nên dựa vào SecurityContextHolder.getContext()
        // để xác định user của request WebFlux ở đây.
        return "done";
    })
);
```

Publisher `Mono.fromFuture` có thể tiếp tục nằm trong một chain, nhưng **code được thực thi bên trong future supplier** thuộc execution model khác và không tự đọc được Reactor Context.

### 17.1. Cách an toàn hơn: lấy identity trong Reactor, truyền làm argument

```java
public Mono<String> runLegacyOperation() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .flatMap(stableName ->
            Mono.fromCallable(() ->
                    legacyService.callFor(stableName)
                )
                .subscribeOn(Schedulers.boundedElastic())
        );
}
```

`legacyService.callFor(stableName)` ở đây là hàm blocking minh họa. `stableName` đã được xác định từ authenticated chain trước khi chuyển sang adapter.

Quan trọng:

- `stableName` phải là identity phù hợp và đã được xác thực.
- Business authorization vẫn phải được kiểm tra.
- Không truyền nguyên access token/Authentication object sang một executor không được kiểm soát chỉ để “cho tiện”.
- Khi cần principal trong thư viện legacy, ưu tiên truyền stable ID làm parameter thay vì cố gắn ThreadLocal.

### 17.2. Nếu phải bridge ThreadLocal?

Các phiên bản Reactor/Micrometer hiện đại có **context-propagation** integrations có thể hỗ trợ truyền những ThreadLocal values đã đăng ký qua các ranh giới cụ thể.

Tuy nhiên, đây **không phải phép đảm bảo tự động cho mọi executor, callback, HTTP client và mọi object SecurityContext**. Cần:

- Kiểm tra phiên bản Reactor/Micrometer/context-propagation.
- Đăng ký accessor đúng.
- Hiểu khi nào có `contextCapture`, automatic propagation hooks hoặc `ContextSnapshot` tương ứng.
- Test thực tế tại từng async boundary.
- Không dùng cầu nối này để thay thế authorization check.

Đối với logic bảo mật, **explicit trusted identity argument** thường dễ kiểm soát hơn so với việc cố làm mọi thư viện tự đọc ThreadLocal.

---

## 18. Nguy cơ từ `cache()`, `share()` và hot publisher

Một lỗi nghiêm trọng không liên quan trực tiếp đổi thread là **chia sẻ publisher chứa dữ liệu của một principal giữa các users**.

### 18.1. Anti-pattern: cache dữ liệu current user trong singleton service

```java
@Service
public class BadCurrentUserCache {

    private final Mono<UserProfile> sharedProfile;

    public BadCurrentUserCache(ProfileService profiles) {
        this.sharedProfile = profiles.currentUserProfile()
            .cache();
    }

    public Mono<UserProfile> getProfile() {
        return sharedProfile;
    }
}
```

Nếu `currentUserProfile()` đọc principal từ Reactor Context, **subscription đầu tiên** có thể tính profile của Alice và `.cache()` giữ kết quả đó cho tất cả subscribers sau, kể cả Bob.

Không nên xem việc Reactor Context tách theo subscriber là đủ để sửa một publisher **đã cache dữ liệu user đầu tiên** và đang được chia sẻ global.

### 18.2. Cách làm tốt hơn

Trả một publisher mới theo request:

```java
@Service
public class CurrentUserProfileService {

    private final ProfileService profiles;

    public CurrentUserProfileService(ProfileService profiles) {
        this.profiles = profiles;
    }

    public Mono<UserProfile> getProfile() {
        return profiles.currentUserProfile();
    }
}
```

Nếu cần cache nghiệp vụ, phải thiết kế cache key dựa trên **stable user/tenant identity và quyền truy cập**, cùng TTL/invalidation phù hợp.

### 18.3. Một `Mono.cache()` bên trong request có luôn sai?

Không. Nếu publisher được tạo **riêng cho một authenticated request** và không thoát ra một singleton/shared global state, một dạng share/caching trong phạm vi request có thể hợp lý để tránh gọi I/O lặp lại.

Rủi ro nằm ở **phạm vi chia sẻ dữ liệu** và khả năng một publisher/cached result của Alice bị Bob subscribe lại.

## 19. Principal và Reactor Context trong WebClient

Một WebFlux OAuth2 Client thường dùng:

```java
org.springframework.security.oauth2.client.web.reactive.function.client
    .ServerOAuth2AuthorizedClientExchangeFilterFunction
```

Nó tích hợp OAuth2 authorized client resolution với `WebClient`, khi được cấu hình cùng reactive manager hoặc repository phù hợp.

Sơ đồ:

```text
Inbound WebFlux request
    |
    +-- Reactor Context: Authentication(Alice)
    |
    v
Controller / Service
    |
    v
WebClient + OAuth2 ExchangeFilterFunction
    |
    +-- Chọn OAuth2AuthorizedClient phù hợp
    +-- Dùng hoặc làm mới access token khi được phép
    +-- Gắn Authorization: Bearer access_token
    |
    v
Downstream Resource Server
```

### 19.1. SecurityContext không tự trở thành Bearer header

Sai giả định:

```text
ReactiveSecurityContextHolder có Alice
    -> mọi WebClient call tự có Bearer token Alice
```

Điều đó không đúng mặc định.

Bạn cần:

- Cấu hình OAuth2 Client cho WebClient.
- Chọn client registration hoặc authorized client đúng.
- Đảm bảo reactive manager/repository có thể truy xuất/authorize token.
- Đảm bảo outgoing API có quyền nhận token và scopes/audience hợp lệ.

### 19.2. Ví dụ cấu hình reactive WebClient

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class DownstreamWebClientConfiguration {

    @Bean("partnerWebClient")
    WebClient partnerWebClient(
            ReactiveOAuth2AuthorizedClientManager manager) {

        ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                manager
            );

        return WebClient.builder()
            .baseUrl("https://api.partner.example")
            .filter(oauth2)
            .build();
    }
}
```

Đoạn code là mẫu wiring **WebFlux reactive**; `manager` phải là reactive manager phù hợp với flow OAuth2 Login/Client và authorized client storage của application.

### 19.3. Chọn registration trên một request

```java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

public Mono<String> readPartnerData(WebClient partnerWebClient) {
    return partnerWebClient.get()
        .uri("/v1/me")
        .attributes(clientRegistrationId("corporate"))
        .retrieve()
        .bodyToMono(String.class);
}
```

Dù method đã gọi `clientRegistrationId("corporate")`, token vẫn phải phù hợp với **principal và registration** mà manager đang resolve. Không tự cho rằng một registration luôn chỉ có một token cho toàn bộ users.

### 19.4. Chọn authorized client object cụ thể

Khi đã có authorized client đúng người dùng:

```java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

Mono<String> response = partnerWebClient.get()
    .uri("/v1/me")
    .attributes(oauth2AuthorizedClient(authorizedClient))
    .retrieve()
    .bodyToMono(String.class);
```

`authorizedClient` là một `OAuth2AuthorizedClient` được lấy từ nguồn đáng tin và đúng principal/tenant.

Đây là request attribute của **WebClient**, không phải dữ liệu tự động được truyền qua Reactor Context. Hai cơ chế có quan hệ trong pipeline nhưng không đồng nhất.

### 19.5. Không bật default token vô điều kiện

Một cấu hình chọn default OAuth2 authorized client cho mọi WebClient request có thể làm token của user được gắn tới **host không được phép nhận token** nếu WebClient được dùng chung.

Ưu tiên lựa chọn tường minh theo request hoặc WebClient riêng cho từng Resource Server; kiểm soát absolute URI và redirects để tránh SSRF/token leakage.

## 20. Vì sao token của Alice không được gửi cho service B?

Một `OidcUser` có thể đã được xác thực thành công, nhưng token dành cho API A có thể không hợp lệ hoặc không được phép dùng tại API B.

Ví dụ:

```text
Alice authenticated via corporate OIDC

Authorized client corporate:
    access token audience = inventory-api
    scope = inventory.read

Outgoing call:
    GET https://billing.example/v1/invoices
```

Không gửi access token của inventory sang billing chỉ vì Reactor Context đang chứa Authentication của Alice.

Phải kiểm tra:

- Client registration và issuer.
- Token audience/resource.
- Scopes đã được AS cấp.
- Resource Server API có quyền nhận token không.
- Authorization policy ở tầng API và tầng nghiệp vụ.
- Có cần token exchange hoặc authorization flow riêng không.

**Reactive Context propagation truyền ngữ cảnh xác thực trong ứng dụng, không mở rộng phạm vi hiệu lực của OAuth2 token.**

## 21. Context propagation trong logic nhiều nhánh

Một service có thể cần gọi nhiều publishers:

```java
public Mono<Dashboard> dashboard() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .flatMap(name -> Mono.zip(
            profileService.findByStableName(name),
            projectService.findVisibleProjects(name)
        ))
        .map(tuple -> new Dashboard(
            tuple.getT1(),
            tuple.getT2()
        ));
}
```

`Dashboard`, `profileService` và `projectService` là các types/services minh họa.

Mẫu này có lợi:

1. Principal được đọc trong reactive chain.
2. Stable ID được truyền tường minh sang hai dịch vụ.
3. `Mono.zip` phối hợp I/O non-blocking.
4. Không dùng global mutable current user field.
5. Business services vẫn có trách nhiệm phân quyền đối với dữ liệu mà ID đang truy cập.

### 21.1. `flatMap` có đảm bảo không lẫn Context giữa users?

Các Reactor subscriptions bình thường mang context riêng. Nhưng nếu một service dùng singleton mutable fields để giữ `Authentication`, hoặc cache kết quả của một user global, thì vẫn có thể lộ dữ liệu.

Context propagation **không tự sửa sai lầm về shared mutable state**.

### 21.2. Trong `Flux`, mỗi item không phải một security principal mới

Một `Flux<Order>` được tạo trong request Alice thường xử lý nhiều items dưới **cùng ngữ cảnh authorization của subscription**. Nếu một stream xử lý events của nhiều users/tenants, không được suy rằng Reactor Context chung chứa đúng principal cho mỗi item.

Với multi-tenant streams, cần:

- Dữ liệu gắn tenant/user identity rõ ràng.
- Xác minh event source và authorization riêng.
- Không dựa vào một HTTP user context để xử lý mọi events dài hạn.
- Phân quyền truy cập từng resource khi cần.

## 22. Khi context biến mất: năm nguyên nhân thường gặp

### 22.1. Gọi `subscribe()` ở giữa service

```java
void sendAudit() {
    auditMono.subscribe();
}
```

Đây là subscription mới, không nhất thiết có context của caller. Thay bằng phương thức trả `Mono<Void>` và ghép nó vào chain được quản lý.

### 22.2. Dùng `block()` ở ranh giới sai

```java
String name =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .block();
```

Một subscription blocking riêng không bảo đảm mang context của WebFlux request và có thể bị Reactor chặn khi chạy trên non-blocking event loop.

### 22.3. Chạy task qua executor tự tạo

```java
executor.submit(() -> {
    // SecurityContextHolder.getContext() có thể không phải context
    // của WebFlux request mà từ đó task được submit.
});
```

Truyền stable identity đã xác minh như argument hoặc thiết kế bridge có kiểm thử, không đọc global ThreadLocal mù quáng.

### 22.4. Đặt `contextWrite` không đúng phạm vi

Nếu bạn chỉ gắn context cho một nhánh nhỏ, publisher ở nhánh khác có thể không thấy nó. Hãy hiểu operator nào nằm upstream của `contextWrite` và subscription nào đang thực thi.

### 22.5. Gọi một hot/shared publisher đã được tạo dưới user khác

Publisher được cache global có thể trả kết quả của Alice cho Bob bất kể subscription context của Bob. Sửa phạm vi caching, không chỉ thêm `contextWrite`.

## 23. `SecurityContextHolder.getContext()` trong WebFlux có gì nguy hiểm?

Một developer quen Spring MVC có thể viết:

```java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();
```

trong một handler WebFlux.

Điều đó không phải cách được thiết kế để đọc authentication của Reactor subscriber.

### 23.1. Các triệu chứng

- `auth == null` dù HTTP request đã đăng nhập.
- Chỉ hoạt động trong một test nhưng không hoạt động khi production có concurrency.
- Đổi scheduler khiến code mất user.
- Log thấy một username không khớp với request hiện tại.
- Callback từ thư viện ngoài không có authentication.

### 23.2. Cách sửa

Đưa việc đọc Authentication vào reactive chain:

```java
return ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .flatMap(authentication ->
        service.handleAuthenticatedUser(authentication)
    );
```

Hoặc nhận principal tại controller boundary bằng `ServerWebExchange.getPrincipal()`/`@AuthenticationPrincipal` và truyền **trusted identity** cho service.

Không tự chép Authentication sang `SecurityContextHolder` trong mọi Reactor operator để mô phỏng Servlet. Nếu cần tương tác thư viện legacy phụ thuộc ThreadLocal, sử dụng cơ chế context-propagation được cấu hình và kiểm thử, hoặc truyền tham số rõ ràng.

---

## 24. Test ReactiveSecurityContextHolder bằng StepVerifier

Đây là loại test đơn vị rất hữu ích: không cần HTTP server hoặc Authorization Server.

### 24.1. Test có authentication trong Context

Ví dụ JUnit 5 + Reactor Test:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveContextExampleTest {

    @Test
    void canReadAuthenticationFromReactorContext() {
        Authentication alice =
            UsernamePasswordAuthenticationToken.authenticated(
                "alice",
                "N/A",
                AuthorityUtils.createAuthorityList("ROLE_USER")
            );

        Mono<String> principalName =
            ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName)
                .contextWrite(
                    ReactiveSecurityContextHolder.withAuthentication(alice)
                );

        StepVerifier.create(principalName)
            .expectNext("alice")
            .verifyComplete();
    }
}
```

Test này xác nhận khi subscription được gắn authentication, `ReactiveSecurityContextHolder.getContext()` đọc đúng principal.

**Không test bằng cách gọi `SecurityContextHolder.setContext(...)` rồi kỳ vọng reactive holder tự đọc từ ThreadLocal.** Hai APIs phục vụ cơ chế khác nhau.

### 24.2. Test khi thiếu context

```java
@Test
void missingContextProducesNoUser() {
    Mono<String> principalName =
        ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);

    StepVerifier.create(principalName)
        .verifyComplete();
}
```

Ví dụ cho thấy publisher có thể empty khi không được cung cấp Reactor SecurityContext.

Nếu business method yêu cầu authentication, hãy dùng `.switchIfEmpty(Mono.error(...))` để diễn đạt behavior thay vì mặc nhiên `.block()` rồi nhận `NullPointerException`.

### 24.3. Test không lẫn Alice và Bob

```java
@Test
void separateSubscriptionsHaveSeparatePrincipals() {
    Mono<String> source =
        ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication().getName());

    Authentication alice =
        UsernamePasswordAuthenticationToken.authenticated(
            "alice", "N/A",
            AuthorityUtils.createAuthorityList("ROLE_USER")
        );

    Authentication bob =
        UsernamePasswordAuthenticationToken.authenticated(
            "bob", "N/A",
            AuthorityUtils.createAuthorityList("ROLE_USER")
        );

    StepVerifier.create(
        source.contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(alice)
        )
    )
        .expectNext("alice")
        .verifyComplete();

    StepVerifier.create(
        source.contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(bob)
        )
    )
        .expectNext("bob")
        .verifyComplete();
}
```

Bài test chứng minh cùng publisher source logic có thể chạy dưới hai contexts khác nhau.

### 24.4. Test đổi scheduler

```java
@Test
void reactorContextSurvivesPublishOn() {
    Authentication alice =
        UsernamePasswordAuthenticationToken.authenticated(
            "alice", "N/A",
            AuthorityUtils.createAuthorityList("ROLE_USER")
        );

    Mono<String> pipeline =
        ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication().getName())
            .publishOn(reactor.core.scheduler.Schedulers.parallel())
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(alice)
            );

    StepVerifier.create(pipeline)
        .expectNext("alice")
        .verifyComplete();
}
```

Mục tiêu là kiểm tra **normal Reactor propagation** sau `publishOn`, không kiểm tra ThreadLocal MDC.

## 25. Kiểm thử endpoint bằng WebTestClient

Spring Security Test có support để mô phỏng reactive authentication/OAuth2 Login.

Một test WebFlux có thể dùng:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOidcLogin;
```

Ví dụ khái niệm với `WebTestClient` đã bind với application:

```java
webTestClient
    .mutateWith(mockOidcLogin())
    .get()
    .uri("/api/me")
    .exchange()
    .expectStatus().isOk();
```

Điểm cần hiểu:

- `mockOidcLogin()` mô phỏng một principal OIDC được xác thực cho test.
- Nó **không** thực hiện browser redirect, code exchange hoặc xác minh ID Token thật với AS.
- Nếu endpoint cần một `OAuth2AuthorizedClient` hoặc gọi downstream API, phải cấu hình mock authorization/repository/HTTP server phù hợp.
- Nếu endpoint dựa trên Reactor Context, test cần chạy qua Spring Security WebFilterChain hoặc cấp context tương ứng.

### 25.1. MockOAuth2Login khác mockOidcLogin

Trong Spring Security Test, có các helpers tương ứng OAuth2 Login và OIDC Login.

- OAuth2 Login không OIDC: principal thường `OAuth2User`.
- OIDC Login: principal thường `OidcUser`, gồm ID Token claims minh họa.

Nếu code cast mọi principal thành `OidcUser`, một test `mockOAuth2Login()` có thể bộc lộ lỗi thiết kế và giúp bạn chọn đúng contract.

### 25.2. Kiểm thử security context propagation và authorization riêng

Một endpoint trả tên principal trong test chưa chứng minh:

- User có quyền đọc tài nguyên nghiệp vụ.
- WebClient gửi access token đúng audience/scope.
- Refresh token rotation không race.
- Context được propagate qua mọi external executors.
- User identity được tách đúng giữa multi-tenant subscriptions.

Cần test mỗi boundary theo chức năng thực tế.

---

## 26. Quan sát và logging: đừng log nguyên SecurityContext

Khi debug, developer có thể muốn:

```java
log.info("securityContext={}", securityContext);
```

Không nên làm ở production. Một `Authentication`/principal có thể chứa:

- Email, profile attributes và identifiers.
- Credentials/details.
- ID Token claims.
- Các metadata liên quan authentication.
- Nội dung mà hệ thống không nên đưa vào logs.

Hãy log những trường tối thiểu được phép, ví dụ:

```text
event=authorized_api_call
requestId=req-001
registrationId=corporate
principalRef=<pseudonymized>
result=success
```

Không log:

```text
access_token
refresh_token
id_token
client_secret
Authorization header
full Authentication object
full OidcUser attributes
```

### 26.1. Reactor Context và MDC

Với logging theo request, có thể dùng Reactor Context để giữ request ID rồi cấu hình cầu nối sang MDC theo phiên bản Reactor/Micrometer mà ứng dụng đang dùng.

Lưu ý:

- MDC không phải Reactor Context.
- ThreadLocal values không tự gắn với subscriber.
- Nếu logging bridge thiếu hoặc sai, có thể mất hoặc lẫn labels giữa requests.
- Đừng dùng MDC như nguồn quyết định business authorization.
- Không đưa raw principal/email vào metrics labels có cardinality cao.

### 26.2. Tracing không chứng minh authorization

Một span có `user.id` không có nghĩa user có quyền xem một order. Authorization phải được kiểm tra tại business/resource boundary, không dựa vào tracing tags.

## 27. Multi-tenant và Reactor Context

Trong ứng dụng multi-tenant, cùng một `sub` có thể có nghĩa khác nhau giữa các issuers.

Ví dụ:

```text
Issuer A:
    iss = https://id.tenant-a.example
    sub = 123

Issuer B:
    iss = https://id.tenant-b.example
    sub = 123
```

Nếu application dùng `sub` duy nhất làm cache key/account ID, hai chủ thể có thể bị ghép nhầm.

### 27.1. Stable key đáng tin

Với OIDC:

```text
(iss, sub)
```

là nền tảng xác định external identity, hoặc ánh xạ cặp đó sang một stable local account ID có quản trị.

Nếu ứng dụng dùng custom tenant ID trong Reactor Context:

```java
.contextWrite(context -> context.put("tenant-id", tenantId))
```

thì `tenantId` phải được xác minh từ một nguồn đáng tin và so khớp với quyền của principal. Không cho một HTTP query parameter tự đặt `tenant-id` rồi coi đó là chứng cứ authorization.

### 27.2. Context không làm thay việc kiểm tra ownership

Dù `ReactiveSecurityContextHolder` trả Alice, code vẫn phải kiểm tra tài nguyên có thuộc tenant hoặc scope Alice được phép truy cập hay không.

```text
Authentication(Alice)
    |
    +-- Được xác thực
    |
    +-- Chưa chắc có quyền xem invoice của Bob
```

Không dùng một check `authentication.isAuthenticated()` để cho phép truy cập mọi records.

## 28. Scheduled jobs không có WebFlux request principal

Một scheduled job:

```java
@Scheduled(fixedDelay = 60000)
public void synchronize() {
    // Không có lý do mặc định tồn tại HTTP user principal.
}
```

không được gọi trong subscription của một inbound WebFlux request đã đăng nhập. Vì vậy không nên viết:

```java
ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName())
```

và mặc định luôn có user.

### 28.1. Nếu job gọi API bằng quyền chính ứng dụng

Dùng OAuth2 Client Credentials Grant và reactive authorized client manager phù hợp, ví dụ:

```java
AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager
```

cùng:

```java
ReactiveOAuth2AuthorizedClientService
```

và một principal name ổn định làm **khóa lưu authorized client của service**. Tên này không biến access token thành token của một End-User.

### 28.2. Nếu job làm việc thay mặt một user

Job cần:

- Một authorization đã được cấp hợp lệ theo policy.
- Stable external/local identity.
- Authorized client lưu đúng user/tenant.
- Refresh token handling nếu AS cho phép.
- Quy tắc xóa/thu hồi khi user disconnect.
- Kiểm soát concurrency khi nhiều workers cùng refresh.
- Re-authorization flow khi refresh token không còn hợp lệ.

Không sao chép `ReactiveSecurityContextHolder` của request cũ sang job rồi coi đó là bằng chứng Alice vẫn đang online và đã cho phép mọi tác vụ.

## 29. Những lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Controller thấy principal, service reactive thấy empty | Service tạo subscription mới hoặc đọc sai scope | Giữ trong một reactive chain; tránh `.subscribe()` |
| `SecurityContextHolder.getContext()` trả null/anonymous | Dùng ThreadLocal API trong WebFlux | Đọc bằng `ReactiveSecurityContextHolder` |
| Sau `publishOn`, log MDC mất username | MDC dùng ThreadLocal | Cấu hình context-propagation/logging bridge, không thay SecurityContext |
| Sau `publishOn`, code đọc Reactor Context vẫn đúng | Normal Reactor propagation hoạt động | Không coi đổi thread là lỗi tự động |
| `.block()` không đọc được current user | Subscription riêng/khả năng block event loop | Compose bằng `flatMap`, không block |
| CompletableFuture không thấy principal | Executor không tự nhận Reactor Context | Truyền stable identity argument hoặc bridge có kiểm thử |
| User A nhận dữ liệu B | Shared mutable state hoặc cache publisher global | Cache theo authenticated identity/tenant, không cache `Mono` current-user global |
| Anonymous được coi là authenticated | Chỉ kiểm tra `isAuthenticated()` | Dùng security authorization policy và anonymous trust semantics |
| OIDC user cast thất bại | Authentication khác hoặc principal không phải `OidcUser` | Kiểm tra runtime type, hỗ trợ cơ chế login phù hợp |
| ID Token được dùng gọi API | Nhầm identity token với access token | Dùng authorized client access token |
| WebClient không có Bearer header | Chưa cấu hình OAuth2 filter hoặc chọn authorized client | Cấu hình reactive WebClient OAuth2 integration |
| WebClient gửi token đến host khác | Default token rộng hoặc URL không được giới hạn | Chọn token per-request, kiểm soát host/redirect |
| API trả 403 dù context có Alice | Authentication không đồng nghĩa authorization | Kiểm tra scopes/roles/business ownership |
| Job không có security context | Job không thuộc inbound request subscription | Dùng service identity/delegated authorization |
| Unit test chỉ pass với ThreadLocal | Test không phản ánh Reactor Context | Dùng StepVerifier với `contextWrite` |
| Request kế tiếp mất login | SecurityContext không được persist hoặc session sai | Kiểm tra ServerSecurityContextRepository, session/cookie/login |
| `contextWrite` không thấy trong operator | Đặt sai vị trí/subscription | Xem thứ tự operators và chiều truyền Context |
| Test dùng mockOidcLogin nhưng không gọi AS | Đây là mock auth | Test flow OAuth2/OIDC integration riêng |
| Token refresh fail nhiều requests | Concurrent refresh token rotation | Đồng bộ theo authorized client, không chỉ propagation |

### 29.1. Quy trình khoanh vùng lỗi context

Nếu code trả anonymous dù request đã login:

1. Xác minh endpoint đang dùng Spring WebFlux `SecurityWebFilterChain`.
2. Xác minh request thực sự đã xác thực; kiểm tra policy `authorizeExchange`.
3. Kiểm tra controller có nhận principal từ `ServerWebExchange.getPrincipal()` không.
4. Kiểm tra reactive service đọc `ReactiveSecurityContextHolder.getContext()` thay vì ThreadLocal.
5. Tìm `.subscribe()` thủ công hoặc `.block()` trong business code.
6. Tìm `CompletableFuture`, `new Thread`, raw `ExecutorService` hoặc callbacks ngoài Reactor.
7. Kiểm tra `contextWrite` có nằm trong đúng subscription scope không.
8. Kiểm tra có `cache()`, `share()` hoặc global mutable state giữa users không.
9. Nếu liên quan WebClient, kiểm tra authorized client selection/filter thay vì chỉ security context.
10. Test lại bằng `StepVerifier`/`WebTestClient` với authentication rõ ràng.

Mọi bước nên sử dụng metadata không nhạy cảm; không cần log token để xác định có đúng principal hay không.

## 30. Thực hành: service đọc đúng current principal

Giả sử application cần một API `/api/my-projects` để trả các projects mà user hiện tại có quyền xem.

### 30.1. DTO minh họa

```java
public record ProjectDto(
    String projectId,
    String displayName
) {}
```

### 30.2. Service dùng SecurityContext trong chain

```java
import java.util.List;

import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class MyProjectService {

    private final ProjectRepository repository;

    public MyProjectService(ProjectRepository repository) {
        this.repository = repository;
    }

    public Mono<List<ProjectDto>> myProjects() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(authentication -> authentication != null)
            .switchIfEmpty(Mono.error(
                new AuthenticationCredentialsNotFoundException(
                    "Authentication required"
                )
            ))
            .flatMap(authentication ->
                repository.findVisibleFor(
                    authentication.getName(),
                    authentication.getAuthorities()
                )
            );
    }
}
```

`ProjectRepository.findVisibleFor(...)` là method minh họa, cần implementation thực tế với **tenant/resource authorization đúng policy**.

Điểm mạnh:

- Không có static/global current user.
- Không block.
- Không tự tạo subscription.
- Identity/authorities được lấy trong context của request.
- Repository có cơ hội kiểm tra quyền theo policy.

### 30.3. Reactive controller

```java
import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class MyProjectsController {

    private final MyProjectService service;

    public MyProjectsController(MyProjectService service) {
        this.service = service;
    }

    @GetMapping("/api/my-projects")
    public Mono<List<ProjectDto>> myProjects() {
        return service.myProjects();
    }
}
```

Controller **trả publisher** cho Spring WebFlux quản lý. Không gọi `subscribe()` và không đọc `SecurityContextHolder` đồng bộ ở controller.

### 30.4. Security chain bảo vệ endpoint

```java
http.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/", "/public/**").permitAll()
    .pathMatchers("/api/**").authenticated()
    .anyExchange().denyAll()
);
```

Snippet là một phần của `ServerHttpSecurity` configuration. Policy có thể phức tạp hơn khi yêu cầu scopes/roles, nhưng việc **bảo vệ tại filter chain** và kiểm tra ownership ở service/repository là hai lớp bổ sung.

---

## 31. Phân biệt propagation và persistence của SecurityContext

Một câu hỏi thường gặp: “Đã có `withAuthentication()` rồi, tại sao request sau vẫn anonymous?”

Vì:

```text
Reactor Context:
    Mang SecurityContext trong subscription hiện tại.

ServerSecurityContextRepository:
    Có thể lưu SecurityContext phục vụ những request sau.
```

Ví dụ:

```java
publisher.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(authentication)
);
```

chỉ gắn context cho publisher. Không đồng nghĩa:

```text
Spring Security đã lưu login session
Browser đã nhận session cookie
Refresh token đã được lưu
Authorization Server đã duy trì SSO
```

Khi cần login thực sự, hãy dùng OAuth2/OIDC authentication flow và security infrastructure phù hợp.

## 32. Các tình huống vận dụng

### Tình huống A — Controller đọc đúng user, service không thấy

`ServerWebExchange.getPrincipal()` thấy Alice nhưng một service bên trong gọi `SecurityContextHolder.getContext()` và nhận null.

**Nguyên nhân:** service dùng API ThreadLocal của Servlet trong WebFlux.

**Cách xử lý:** đọc `ReactiveSecurityContextHolder` trong chain hoặc truyền stable user ID từ controller.

### Tình huống B — Sau `publishOn`, principal vẫn là Alice

Publisher đổi sang `Schedulers.parallel()` nhưng `ReactiveSecurityContextHolder.getContext()` vẫn thấy Alice.

**Lý giải:** Reactor Context đi cùng subscription; đổi thread bằng operator chuẩn không mặc định làm mất nó.

### Tình huống C — `CompletableFuture` không có user

Code dùng `CompletableFuture.supplyAsync()` rồi gọi `SecurityContextHolder` trong future.

**Nguyên nhân:** executor task không tự có Reactor Context.

**Cách xử lý:** resolve trusted ID trong reactive chain và truyền vào future/legacy service, hoặc dùng bridge đã kiểm chứng.

### Tình huống D — `subscribe()` chạy fire-and-forget

Controller trả `Mono.just("OK")` nhưng tự subscribe một workflow cần principal.

**Nguyên nhân:** workflow tách subscription, ngoài lifecycle của HTTP response.

**Cách xử lý:** compose publisher vào response hoặc lập background job có authentication/authorization model riêng.

### Tình huống E — Bob thấy dữ liệu Alice

Một singleton service giữ `Mono<UserProfile>.cache()` được tạo cho current user.

**Nguyên nhân:** publisher shared/cached dữ liệu của first subscriber.

**Cách xử lý:** tạo publisher per-request hoặc cache theo stable identity/tenant cùng authorization checks.

### Tình huống F — Có OIDC principal nhưng API 403

Alice có `OidcUser` và `SecurityContext` hợp lệ, nhưng WebClient gọi API có scope khác.

**Nguyên nhân:** user đã xác thực không đồng nghĩa access token đủ scope.

**Cách xử lý:** chọn authorized client đúng API, kiểm tra scope/audience/resource policy.

### Tình huống G — Dùng `contextWrite` để giả làm admin

Một endpoint nhận `?role=admin`, tạo `Authentication` đã authenticated, rồi gắn `contextWrite`.

**Nguyên nhân:** không kiểm chứng credential trước khi tạo authentication.

**Cách xử lý:** chỉ authentication infrastructure đã xác minh credential/token mới được tạo trusted Authentication.

### Tình huống H — Worker xử lý queue không thấy ReactiveSecurityContext

Một event consumer chạy độc lập với HTTP request của Alice.

**Lý giải:** không có inbound login subscription.

**Cách xử lý:** dùng service token hoặc delegated authorization được lưu/kiểm soát theo chính sách, không dựa vào session context cũ.

### Tình huống I — Multi-tenant `sub=123` bị trùng

Hai issuers cung cấp cùng subject `123`.

**Nguyên nhân:** dùng subject không có issuer namespace.

**Cách xử lý:** khóa identity theo `(iss, sub)` hoặc stable mapped local identity có kiểm soát.

### Tình huống J — Reactor Context có user, log MDC không có

Trên thread scheduler khác, `MDC.get("principal")` trả null.

**Lý giải:** MDC là ThreadLocal, không phải Reactor Context.

**Cách xử lý:** cấu hình logging bridge theo version Reactor/Micrometer; không dựa vào MDC để authorization.

### Tình huống K — User logout nhưng detached job vẫn chạy

Một manual subscription giữ quyền truy cập API lâu hơn HTTP session.

**Nguyên nhân:** subscription tự quản lý ngoài session lifecycle.

**Cách xử lý:** quản lý job cancellation/authorization/token lifecycle đúng yêu cầu, không coi logout chỉ là clear Reactor Context.

### Tình huống L — Test Reactivity qua `@WithMockUser`

Một test chỉ set `SecurityContextHolder` ở test thread, rồi kỳ vọng `ReactiveSecurityContextHolder.getContext()` nhận user.

**Nguyên nhân:** test setup chưa gắn authentication vào Reactor Context hoặc chưa đi qua WebFlux test integration.

**Cách xử lý:** dùng `StepVerifier` + `contextWrite` cho unit test hoặc WebTestClient + Spring Security Test cho web test.

## 33. Câu hỏi tự kiểm tra

**Câu 1.** `ReactiveSecurityContextHolder.getContext()` trả kiểu gì?

**Trả lời:** `Mono<SecurityContext>`; không trả `SecurityContext` đồng bộ.

**Câu 2.** Reactor Context gắn với thread hay subscription?

**Trả lời:** Gắn với subscriber/subscription; operators có thể đổi thread mà không làm mất context theo cơ chế Reactor bình thường.

**Câu 3.** `SecurityContextHolder.getContext()` có nên là cách đọc principal chính trong WebFlux không?

**Trả lời:** Không. Với reactive chain, dùng `ReactiveSecurityContextHolder` hoặc principal resolver tại request boundary.

**Câu 4.** `withAuthentication(authentication)` có tự persist login sang request sau không?

**Trả lời:** Không. Nó tạo Reactor Context cho subscription; persistence do security repository/session flow xử lý.

**Câu 5.** `contextWrite` có mutate context global không?

**Trả lời:** Không. Nó tạo context mới trong phạm vi subscription cho operators phù hợp.

**Câu 6.** Vì sao `.subscribe()` thủ công có thể làm mất principal?

**Trả lời:** Nó tạo subscription mới không mặc nhiên kế thừa Reactor Context của inbound request.

**Câu 7.** `publishOn()` có luôn làm mất security context không?

**Trả lời:** Không. Reactor Context thường được bảo toàn trong reactive chain qua operator đó.

**Câu 8.** Vì sao `CompletableFuture.supplyAsync()` khác `publishOn()`?

**Trả lời:** Future supplier do executor chạy không tự là operator trong Reactor subscription và không mặc nhiên có context subscriber.

**Câu 9.** Để lấy tên principal trong service reactive nên làm gì?

**Trả lời:** `ReactiveSecurityContextHolder.getContext().map(SecurityContext::getAuthentication).map(Authentication::getName)` trong chain phù hợp, kèm kiểm tra missing/anonymous theo policy.

**Câu 10.** `OidcUser` và `OAuth2AuthorizedClient` khác nhau thế nào?

**Trả lời:** `OidcUser` là principal/claims của OIDC authentication; authorized client mang OAuth2 access token/refresh token cho client/registration.

**Câu 11.** Vì sao `Mono.cache()` trong singleton có thể lộ dữ liệu?

**Trả lời:** Nó có thể giữ kết quả được tạo cho subscription đầu tiên của Alice rồi trả lại cho Bob.

**Câu 12.** Đã có Reactor Context của Alice thì WebClient có tự gắn Bearer token Alice không?

**Trả lời:** Không. Cần cấu hình OAuth2 WebClient integration và chọn authorized client phù hợp.

**Câu 13.** Một access token có thể dùng cho mọi API nếu user authenticated không?

**Trả lời:** Không. Phải đúng issuer/audience/scope và authorization policy của Resource Server.

**Câu 14.** `clearContext()` có đồng nghĩa OIDC logout hoặc revoke refresh token không?

**Trả lời:** Không. Nó thay đổi Reactor Context trong subscription; logout và token lifecycle là các quy trình riêng.

**Câu 15.** Với background job, có mặc định principal user trong Reactor Context không?

**Trả lời:** Không. Job cần service identity hoặc delegated authorization model riêng.

**Câu 16.** Test unit cho reactive security context dùng công cụ gì?

**Trả lời:** `StepVerifier` và `.contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))`.

**Câu 17.** Test HTTP endpoint mô phỏng OIDC user dùng gì?

**Trả lời:** `WebTestClient` với Spring Security Test, ví dụ `mockOidcLogin()`; đó là mock, không phải flow OIDC thật.

**Câu 18.** Trong multi-tenant OIDC, identity nên tách namespace ra sao?

**Trả lời:** Theo cặp `(iss, sub)` hoặc stable local ID được ánh xạ tin cậy, không chỉ email hoặc `sub` không có issuer.

**Câu 19.** Vì sao không dùng MDC làm nguồn authorization?

**Trả lời:** MDC là logging state dựa trên ThreadLocal và có thể không được propagate đúng; authorization phải dựa vào trusted SecurityContext/Authentication và policy.

**Câu 20.** Khi reactive service không đọc được context, cần kiểm tra những ranh giới nào?

**Trả lời:** Kiểm tra chain, manual subscriptions, `block`, external futures/executors, vị trí `contextWrite`, hot/cache publishers và web filter security configuration.

## 34. Ghi nhớ trọng tâm

| Thành phần | Ý nghĩa |
|---|---|
| **`ReactiveSecurityContextHolder`** | API truy cập SecurityContext qua Reactor Context. |
| **`getContext()`** | Trả `Mono<SecurityContext>` trong subscription hiện tại. |
| **`withAuthentication(Authentication)`** | Tạo Reactor Context chứa trusted Authentication cho một phạm vi subscription. |
| **`withSecurityContext(Mono<SecurityContext>)`** | Gắn publisher cung cấp SecurityContext. |
| **`clearContext()`** | Loại bỏ security context trong Reactor Context scope. |
| **Reactor `Context`** | Dữ liệu immutable theo subscriber, không phải global variable. |
| **`contextWrite(...)`** | Bổ sung/thay context mà operators upstream nhìn thấy khi subscribe. |
| **`deferContextual(...)`** | Đọc context tại subscription time. |
| **`publishOn`/`subscribeOn`** | Chuyển execution scheduling; không tự mặc định xóa Reactor Context. |
| **Manual `subscribe()`** | Tạo subscription khác, dễ tách khỏi inbound request/làm mất context. |
| **`block()`** | Blocking/subscription boundary; không phù hợp trong event loop WebFlux. |
| **`ServerWebExchange.getPrincipal()`** | Cách đọc principal qua exchange trong WebFlux. |
| **`OAuth2AuthenticationToken`** | Authentication gắn với OAuth2/OIDC Login. |
| **`OidcUser`** | Principal OIDC với ID Token/claims; nên phân biệt `iss` và `sub`. |
| **`OAuth2AuthorizedClient`** | Token authorization dùng gọi API, không phải SecurityContext. |
| **`ServerSecurityContextRepository`** | Lưu/khôi phục context giữa requests theo cơ chế cấu hình. |
| **`ServerOAuth2AuthorizedClientExchangeFilterFunction`** | Gắn OAuth2 access token cho WebClient theo client/registration phù hợp. |
| **`Mono.cache()` global** | Có thể làm lộ dữ liệu giữa users nếu cache publisher current-user dùng chung. |
| **WebTestClient / StepVerifier** | Công cụ test reactive web security và propagation. |

### Kết luận

Với **Spring Security OAuth 2.0/OIDC Client trong WebFlux**, authentication của user không nên được coi là một biến ThreadLocal cố định theo HTTP request. Spring Security cung cấp **`ReactiveSecurityContextHolder`** để đọc và gắn SecurityContext bằng **Reactor Context**, vốn thuộc về subscription.

Để code đúng:

1. Đọc principal trong reactive pipeline hoặc tại trusted controller boundary.
2. Giữ công việc trong chain, hạn chế `.subscribe()` thủ công và `.block()` trên event loop.
3. Hiểu rằng `publishOn`/`subscribeOn` không tự làm mất Reactor Context, nhưng external executors/futures cần cách truyền identity phù hợp.
4. Không cache global một publisher hoặc object chứa dữ liệu user hiện tại.
5. Không xem SecurityContext là access token; khi gọi API, chọn `OAuth2AuthorizedClient` đúng registration, principal, issuer, audience và scope.
6. Kiểm thử đúng context bằng StepVerifier/WebTestClient và không dùng logging ThreadLocal làm bằng chứng phân quyền.

**Propagation đúng giúp ứng dụng giữ đúng danh tính trong một reactive execution. Authorization đúng vẫn cần thêm kiểm tra tài nguyên, tenant, token và business policy.**

## Tài liệu tham khảo

- [Spring Security — Reactive Security Context Holder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html): `getContext`, `withAuthentication`, `withSecurityContext`, `clearContext`.
- [Spring Security — Reactive OAuth2 Login](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html): luồng OAuth2/OIDC Login trong WebFlux.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `SecurityWebFilterChain`, `ServerHttpSecurity`.
- [Spring Security — Reactive OAuth2 Client](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html): authorized clients, managers và WebClient integration.
- [Spring Security — Reactive Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html): `WebTestClient`, `mockOidcLogin`, `mockOAuth2Login` và test security.
- [Reactor — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): Reactor `Context`, `ContextView`, `contextWrite`, `deferContextual`.
- [Reactor — Context-Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html): tương tác giữa Reactor Context và ThreadLocal với Micrometer context-propagation.
