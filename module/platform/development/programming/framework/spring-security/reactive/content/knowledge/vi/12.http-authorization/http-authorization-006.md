# ReactiveAuthorizationManager<AuthorizationContext> và AuthorizationDecision

## 1. Bài học giải quyết vấn đề gì?

Trong **Spring Security Reactive (Spring WebFlux)**, xác thực trả lời câu hỏi *ai đang gọi API?*; phân quyền HTTP trả lời câu hỏi *người đó có được truy cập request này không?*. Những điều kiện phổ biến như `authenticated()`, `hasRole("ADMIN")` hay `hasAuthority("orders:read")` thường đủ. Nhưng chính sách thực tế có thể cần xét **người dùng hiện tại + đường dẫn HTTP + biến path + trạng thái tài nguyên hoặc tenant**. Khi đó, Spring Security cung cấp contract `ReactiveAuthorizationManager<T>` để trả một quyết định bất đồng bộ.

Bài này tập trung vào chính xác hai khái niệm:

- **`ReactiveAuthorizationManager<AuthorizationContext>`**: thành phần quyết định cho một request HTTP WebFlux, nhận `Mono<Authentication>` và `AuthorizationContext`, được gắn với `ServerHttpSecurity.authorizeExchange(...).access(...)`.
- **`AuthorizationDecision`**: một kết quả có `isGranted()`, cho biết cho phép hay từ chối; ở Spring Security 6.4+ nó implements `AuthorizationResult`.

Kết thúc bài, bạn có thể:

1. Giải thích chuỗi **authentication → authorization → tiếp tục WebFilterChain hoặc từ chối**.
2. Phân biệt `AuthorizationContext.getExchange()` với `getVariables()` và cách biến path được matcher trích ra.
3. Phân biệt `Mono.just(new AuthorizationDecision(true))`, `false`, `Mono.empty()` và `Mono.error(...)`.
4. Hiểu sự khác nhau giữa phương thức `check(...)` ở Spring Security **6.5.x** và `authorize(...)` ở **7.x**, tránh trộn những chữ ký không tương thích.
5. Cấu hình một policy tùy biến qua `pathMatchers(...).access(manager)`, kết hợp route thông thường và chính sách mặc định từ chối.
6. Viết manager kiểm tra owner hoặc admin, không nhầm `isAuthenticated()` của anonymous token với đăng nhập thực sự.
7. Tạo ứng dụng Spring Boot 3.x/Spring Security 6.5.x Java 17+ chạy được, test 401/403/200 và policy bằng `WebTestClient`/`StepVerifier`.
8. Tránh lỗ hổng về **client-controlled path**, truy vấn blocking trên event-loop, request authorization thay cho object authorization, quyền tenant và lỗi fail-open.

**Ngữ cảnh cấp cha:** Phân quyền HTTP. Bài chỉ nói về **inbound WebFlux**, không sao chép `AuthorizationManager<RequestAuthorizationContext>` hoặc `HttpSecurity.authorizeHttpRequests` của Servlet. Phần demo được viết có chủ đích cho Spring Security **6.5.x** chạy trên Spring Boot **3.x**; mục 4.4 chỉ rõ cách chuyển contract sang Security 7.x.

## 2. Bức tranh tổng thể: xác thực trước, phân quyền sau

Luồng khái niệm:

```text
Client -> GET /projects/alice
             |
             v
       Spring WebFlux WebFilters
             |
             v
       Spring Security WebFilterChainProxy
             |
             +-- Authentication filter
             |     Basic / Bearer / session / login ...
             |     -> Authentication (principal + authorities)
             |
             +-- Reactor Context / ReactiveSecurityContextHolder
             |
             +-- AuthorizationWebFilter
                   -> chọn rule trong authorizeExchange(...)
                   -> ReactiveAuthorizationManager<AuthorizationContext>
                         Authentication + AuthorizationContext
                         -> Mono<AuthorizationDecision>
                   -> GRANTED ? tiếp tục request : access denied
             |
             +-- controller / service / repository nếu được phép
```

Sơ đồ nói về vai trò logic, **không phải mô tả thứ tự triển khai đầy đủ của mọi filter**. `AuthorizationWebFilter` xử lý authorization cho inbound exchange theo cấu hình; `ExceptionTranslationWebFilter` giúp chuyển những lỗi truy cập phù hợp thành HTTP response.

Điểm cần giữ rõ:

- **Authentication**: một `Authentication` đã được framework xác minh; ví dụ principal `alice` với `ROLE_USER`.
- **Authorization**: kết quả của chính sách xét request. Cùng principal `alice` có thể truy cập `/projects/alice` nhưng không truy cập `/projects/bob`.
- **Role/authority**: `hasRole("ADMIN")` theo convention kiểm tra `ROLE_ADMIN`; `hasAuthority("ROLE_ADMIN")` kiểm tra chuỗi chính xác.
- **Response**: `AuthorizationDecision(false)` tự nó **không** phải `HTTP 403`. Filter và entry point/denied handler quyết định HTTP status tùy trạng thái authentication và cấu hình.

Trong bài thực hành, HTTP Basic được bật để dễ test. Với client **chưa có credential**, request cần xác thực thường nhận **401 Unauthorized**. Với user đã login nhưng policy từ chối, thường nhận **403 Forbidden**. Cấu hình form login có thể redirect **302** thay vì 401 cho người chưa xác thực. Không hardcode status trong manager bằng cách `setStatusCode`; hãy để security pipeline thực hiện.

## 3. Contract của ReactiveAuthorizationManager

### 3.1. Tổng quan generic type T

`ReactiveAuthorizationManager<T>` là một strategy có thể dùng cho nhiều đối tượng được kiểm soát quyền. `T` thể hiện **đối tượng muốn phân quyền**:

- Với **HTTP WebFlux rule `.access(...)`**, `T` thường là `AuthorizationContext`.
- Với các cơ chế authorization khác, kiểu `T` có thể khác, chẳng hạn method invocation; không tự thay `AuthorizationContext` bằng một object tùy ý trong `authorizeExchange`.
- `ReactiveAuthorizationManager` khác contract đồng bộ `AuthorizationManager<T>` của Servlet/một số method security paths.

Ở Spring Security 6.5, chữ ký đáng lưu ý:

```java
// API rút gọn từ Spring Security 6.5.x để giải thích.
// Đừng tự khai báo lại interface này trong project.
public interface ReactiveAuthorizationManager<T> {

    @Deprecated
    Mono<AuthorizationDecision> check(
        Mono<Authentication> authentication,
        T object
    );

    default Mono<AuthorizationResult> authorize(
        Mono<Authentication> authentication,
        T object
    ) {
        // Implementation mặc định 6.5 ủy quyền cho check(...)
        // và trả AuthorizationResult.
        throw new UnsupportedOperationException("diagram only");
    }

    default Mono<Void> verify(
        Mono<Authentication> authentication,
        T object
    ) {
        throw new UnsupportedOperationException("diagram only");
    }
}
```

**Quan trọng:** Đây là *pseudocode mô tả chữ ký*; `throw` và method bodies chỉ là dấu hiệu không dùng để biên dịch/triển khai; **không copy vào source**. Spring Security cung cấp các implementation thật. Trong **6.5.x**, `check(...)` còn là phương thức cần implement khi viết một class implement interface, dù đã `@Deprecated` từ **6.4**, và `authorize(...)` là method mặc định được khuyên sử dụng khi **gọi** manager. Điều này khác với 7.x.

`check` trả `Mono<AuthorizationDecision>`. `authorize` trả `Mono<AuthorizationResult>`: kiểu interface giúp thêm dạng kết quả authorization mà không bắt người dùng phụ thuộc một concrete class. `AuthorizationDecision` vẫn là một implementation hợp lệ của `AuthorizationResult`. `verify` thể hiện contract xác minh/quản lý từ chối, trả `Mono<Void>` khi thành công hoặc signal lỗi nếu quyền không được cấp theo policy.

### 3.2. Hai tham số trong HTTP

```java
Mono<Authentication> authentication
AuthorizationContext context
```

`authentication` là **publisher** chứa thông tin xác thực cho reactive request, không phải một `Authentication` đồng bộ. Không gọi `authentication.block()` trong request; điều đó có thể block Netty event loop, cắt mất ngữ cảnh hoặc gây lỗi chạy.

`context` cung cấp:

- `context.getExchange()`: `ServerWebExchange`, cho phép đọc method, URL, headers và các thuộc tính request theo đúng contract.
- `context.getVariables()`: `Map<String,Object>` chứa **URI template variables được matcher trích xuất**, ví dụ pattern `/projects/{owner}` và request `/projects/alice` cho `owner = "alice"`.

`AuthorizationContext.getVariables()` không phải một map chứa mọi request parameter; nó chứa biến của rule matcher. Khi policy cần giá trị từ query/header/body, phải tự xác định cách lấy dữ liệu an toàn và đánh giá rủi ro. Với request có body streaming, **không tự đọc và consume body trong authorization manager** rồi kỳ vọng controller còn đọc được như cũ.

### 3.3. AuthorizationDecision và isGranted

```java
AuthorizationDecision allow = new AuthorizationDecision(true);
AuthorizationDecision deny  = new AuthorizationDecision(false);

boolean a = allow.isGranted(); // true
boolean b = deny.isGranted();  // false
```

`AuthorizationDecision` là **kết quả phân quyền**, không phải object chứa role mới, session mới hoặc response HTTP. Nếu manager trả allow, nó chỉ cho phép request đi tiếp theo security filter; service/repository vẫn phải bảo vệ resource thật. Nếu manager trả deny, nó từ chối truy cập theo cơ chế chung, chứ không trả về một body "false" cho client.

Ở 6.4+/7.x, `AuthorizationResult` là abstraction có method `isGranted()`; `AuthorizationDecision` implements interface này. Vì vậy code đọc kết quả từ `authorize(...)` nên ưu tiên `AuthorizationResult` thay vì ép kiểu ngược về `AuthorizationDecision`.

### 3.4. Bốn kết quả reactive có ý nghĩa khác nhau

| Giá trị publisher | Ý nghĩa | Điều cần nhớ |
|---|---|---|
| `Mono.just(new AuthorizationDecision(true))` | Quyết định **allow** | Security filter có thể tiếp tục chuỗi |
| `Mono.just(new AuthorizationDecision(false))` | Quyết định **deny** | Security pipeline sẽ từ chối theo entry point/denied handler phù hợp |
| `Mono.empty()` | Manager **không đưa ra quyết định** / abstain | Không sử dụng làm “deny mặc định”; cách phối hợp quyết định phụ thuộc consumer/implementation |
| `Mono.error(error)` | Kiểm tra xảy ra **lỗi** | Không có Boolean decision; lỗi được lan truyền/được xử lý theo pipeline |

**Không** dùng `Mono.empty()` để biểu diễn user không được phép. Nó biểu diễn **không có decision**, và khi kết hợp nhiều manager, `switchIfEmpty`/`filter` có semantics riêng; luôn chọn cách fail-closed rõ ràng cho resource nhạy cảm.

**Không** biến mọi exception khi gọi policy service thành `new AuthorizationDecision(true)`. Lỗi database/permission backend phải fail closed hoặc được chuyển thành lỗi ứng dụng phù hợp; nếu che giấu lỗi thành allow sẽ là lỗ hổng phân quyền.

### 3.5. Mono được thực thi khi subscription, không phải khi khai báo

Một manager nên trả publisher, ví dụ:

```java
return authentication.map(auth ->
    new AuthorizationDecision(hasRequiredAuthority(auth)));
```

`hasRequiredAuthority` ở đây là helper do bạn tự định nghĩa; snippet chưa chạy độc lập. Đừng `subscribe()` bên trong manager rồi trả `Mono.just(true)`: subscription riêng bị tách lỗi, cancellation và Reactor Context. Nếu cần đọc repository reactive, compose bằng `flatMap`/`map`/`switchIfEmpty`/`onErrorMap` theo policy cụ thể.

## 4. Khác biệt phiên bản 6.5 và 7.x: tránh copy nhầm chữ ký

Đây là điểm **rất quan trọng** khi học từ nhiều bài viết có tuổi đời khác nhau.

| Spring Security | Method implement trong class manager | Return type | Ghi chú |
|---|---|---|---|
| 5.x–6.3 | `check(Mono<Authentication>, T)` | `Mono<AuthorizationDecision>` | API trước cải tiến 6.4 |
| 6.4–6.5 | `check(...)` (đã deprecated nhưng còn abstract) | `Mono<AuthorizationDecision>` | `authorize(...)` mặc định mới có, trả `Mono<AuthorizationResult>` |
| 7.x | `authorize(Mono<Authentication>, T)` | `Mono<AuthorizationResult>` | Dùng contract mới; không giữ override `check(...)` cũ |

Với Spring Boot 3.x/Java 17 trong demo dưới đây, ta viết **đúng API 6.5**:

```java
@Override
@SuppressWarnings("deprecation")
public Mono<AuthorizationDecision> check(
        Mono<Authentication> authentication,
        AuthorizationContext context) {
    return authentication
        .map(auth -> new AuthorizationDecision(auth.isAuthenticated()))
        .defaultIfEmpty(new AuthorizationDecision(false));
}
```

Đây là snippet giải thích chữ ký; **logic policy thực tế phải xử lý anonymous token**, không thể chỉ dùng `auth.isAuthenticated()`. Class hoàn chỉnh ở mục 7 đã làm việc đó.

Khi chuyển sang **Spring Security 7.x**, class cần triển khai chữ ký mới, ví dụ mảnh method:

```java
@Override
public Mono<AuthorizationResult> authorize(
        Mono<Authentication> authentication,
        AuthorizationContext context) {
    return authentication
        .map(auth -> (AuthorizationResult)
            new AuthorizationDecision(isAllowed(auth, context)))
        .defaultIfEmpty(new AuthorizationDecision(false));
}
```

Trong đoạn trên, `isAllowed` là helper policy phải tự viết và mã chỉ minh họa **API 7.x**; không thể dùng nguyên bản làm class 6.5. Phân biệt `@Override` với chỉ thêm một method có tên đúng nhưng **không còn interface contract**. Khi nâng version, compiler phải là bước kiểm tra đầu tiên, sau đó test lại behavior của manager và các integration filter.

**Quy tắc thực hành:** đọc Javadoc của **phiên bản đang có trong dependency tree**, không chỉ trang “current”. Một ví dụ trên web dùng `authorize(...)` cho 7.x có thể không biên dịch khi bạn implement một class 6.5 chỉ có method đó. Mục tiêu bài này là nắm contract và migration đúng, không pha trộn hai dòng API.

## 5. AuthorizationContext: thông tin gì được chuyển vào policy?

### 5.1. Exchange và biến URI

Khi cấu hình:

```java
.pathMatchers(HttpMethod.GET, "/projects/{owner}")
.access(ownerAuthorizationManager)
```

Spring Security sử dụng matcher tương ứng, và `AuthorizationContext` có thể chứa biến `owner` được trích từ path. Trong manager:

```java
String owner = context.getVariables().get("owner") instanceof String s
    ? s
    : null;

String method = context.getExchange()
    .getRequest().getMethod().name();

String path = context.getExchange()
    .getRequest().getPath().value();
```

Đây là mảnh code Java 17+, phụ thuộc một `AuthorizationContext` thật. Nếu owner không có vì matcher/route khác, **từ chối** thay vì giả định `owner` luôn tồn tại. Đừng lấy `owner` từ query string do client tùy ý gửi rồi coi đó là bằng chứng quyền sở hữu.

### 5.2. Phân biệt path variable và dữ liệu đáng tin

`/projects/alice` chứa một chuỗi mà **client chọn**. Nó không chứng minh request thực sự thuộc tài nguyên của Alice. Một policy `auth.getName().equals(owner)` có thể có ích cho demo user-namespaced routes, nhưng trong sản phẩm thật:

- Project có thể có owner lưu trong database không trùng username trên path.
- Admin, member, tenant và resource-level ACL có thể cần điều kiện khác.
- URL có thể bị đổi tên, ID có thể bị đoán và query/body có thể khai báo thông tin không đáng tin.
- Authorization ở HTTP layer phải được củng cố trong service/repository, nhất là khi cùng service được gọi bởi job, message consumer hoặc endpoint khác.

Ví dụ policy đáng tin hơn là dùng `projectId` trích từ URL rồi **tra owner/tenant/ACL trong repository** bằng một truy vấn reactive; trả deny nếu không có resource hoặc không đủ quyền. Với trường hợp nhạy cảm, cần tách 403 và 404 theo chính sách chống enumeration, nhưng không cho phép chỉ vì path có username trùng người gọi.

### 5.3. Quan sát header không phải tin header

`context.getExchange().getRequest().getHeaders()` cho phép xem header. Tuy nhiên `X-User`, `X-Role`, `X-Tenant` do client gửi **không tự trở thành principal/authority đáng tin**. Nếu kiến trúc dùng reverse proxy đặt trusted identity headers, chỉ chấp nhận qua mạng và cơ chế xác thực proxy được xác minh, không tin header công khai từ internet. Mặc định, policy nên dựa vào `Authentication` đã xác thực bởi Spring Security và dữ liệu resource từ nguồn tin cậy.

## 6. Gắn custom manager vào authorizeExchange

Ví dụ một phần cấu hình:

```java
return http
    .authorizeExchange(exchanges -> exchanges
        .pathMatchers(HttpMethod.GET, "/public").permitAll()
        .pathMatchers(HttpMethod.GET, "/projects/{owner}")
            .access(ownerAuthorizationManager)
        .anyExchange().denyAll())
    .httpBasic(Customizer.withDefaults())
    .formLogin(form -> form.disable())
    .build();
```

Đây là **snippet** trong method `@Bean SecurityWebFilterChain`; code đầy đủ có import và bean ở mục 7.

Quy tắc quan trọng:

1. `authorizeExchange` xét các rule theo **thứ tự khai báo**; một request dùng rule khớp đầu tiên. Hãy đặt pattern cụ thể trước catch-all.
2. `permitAll()` cho nội dung public; `authenticated()` chỉ yêu cầu đã xác thực; `hasRole(...)`/`hasAuthority(...)` xử lý quyền đơn giản; `access(...)` là điểm gắn policy tùy biến.
3. `anyExchange().denyAll()` làm default **fail closed**, không mở URL mới một cách vô tình.
4. Khi đã khai báo `.pathMatchers("/projects/{owner}").access(manager)`, đừng kỳ vọng một `.pathMatchers("/projects/{owner}").authenticated()` đặt sau nó sẽ “AND” vào policy: rule đầu đã khớp. Manager tự phải xử lý trường hợp chưa xác thực/anonymous phù hợp.
5. Một request **không khớp** path pattern sẽ không tới custom manager ở rule đó; rule tiếp theo quyết định.
6. Nếu có nhiều `SecurityWebFilterChain` dùng `securityMatcher` khác nhau, phải kiểm tra chain nào thực sự áp dụng trước khi phân tích các rule trong chain.

### 6.1. Built-in managers có thể dùng làm thành phần policy

Spring Security có `AuthorityReactiveAuthorizationManager.hasAuthority("...")`, `hasRole("...")` và các built-in policy khác. Với nhiều điều kiện, có thể compose publisher thay vì viết lại logic kiểm tra tất cả loại authentication.

Mảnh minh họa yêu cầu **cả** role ADMIN và DBA theo API 6.5:

```java
ReactiveAuthorizationManager<AuthorizationContext> admin =
    AuthorityReactiveAuthorizationManager.hasRole("ADMIN");
ReactiveAuthorizationManager<AuthorizationContext> dba =
    AuthorityReactiveAuthorizationManager.hasRole("DBA");

return admin.check(authentication, context)
    .flatMap(first -> {
        if (!first.isGranted()) {
            return Mono.just(new AuthorizationDecision(false));
        }
        return dba.check(authentication, context);
    })
    .defaultIfEmpty(new AuthorizationDecision(false));
```

Đây là snippet trong custom policy method, không phải class độc lập. Ở 6.5 `check` deprecated nhưng vẫn có; trong code mới gọi `authorize` thường phù hợp hơn và return type là `AuthorizationResult`. Chú ý: nếu cùng cold `Mono<Authentication>` bị subscribe nhiều lần, cần xem semantics và tối ưu theo workflow; đoạn demo hoàn chỉnh ở mục 7 chỉ đọc `Authentication` **một lần**.

Không dùng `Mono.when(...)` để AND hai Boolean decisions: `Mono.when` chờ completion, bỏ qua giá trị true/false của các source, có thể vô tình cho phép request sai.

### 6.2. AND/OR và “abstain” không phải dễ ghép tùy tiện

Ví dụ logic mong muốn:

- **AND:** cho phép nếu người gọi là user thực và vừa có scope `orders:read` vừa có quyền với resource.
- **OR:** cho phép nếu người gọi là admin **hoặc** là owner thực sự.
- **Deny:** nếu không có identity, thiếu dữ liệu owner/ACL, không có quyền hoặc điều kiện không rõ.
- **Error:** nếu backend phân quyền gặp sự cố, không tự chuyển thành allow; quyết định fail closed/response 5xx tùy thiết kế.

`filter(AuthorizationResult::isGranted).switchIfEmpty(...)` dễ gây hiểu nhầm bởi `filter` biến kết quả deny thành **empty**, sau đó `switchIfEmpty` xem như không có quyết định. Điều đó có thể đúng trong một pipeline OR được thiết kế chặt, nhưng nguy hiểm nếu nhầm một deny thành “hãy thử allow default”. Viết test cho từng tổ hợp và chọn default deny rõ.

## 7. Project Spring Boot 3.x + Security 6.5.x + Java 17+ chạy được

Ta xây dựng policy:

> `GET /projects/{owner}` chỉ được phép nếu request do **owner được xác thực** gọi, hoặc một user có authority `ROLE_ADMIN` gọi. Chưa xác thực, không có biến owner hoặc user khác không phải admin thì từ chối.

Đây là ví dụ đủ nhỏ để chạy và thấy rõ `ReactiveAuthorizationManager<AuthorizationContext>` / `AuthorizationDecision`; **không** đại diện toàn bộ chính sách sở hữu tài nguyên ở production.

### 7.1. Khởi tạo project

Dùng [Spring Initializr](https://start.spring.io/) tạo Gradle Groovy project với **Spring Boot 3.5.x**, **Java 17+**, dependencies **Spring Reactive Web**, **Spring Security**, **Spring Boot Starter Test**, **Spring Security Test** và **Reactor Test**. Spring Boot 3.5.x thường quản lý Spring Security 6.5.x; hãy kiểm tra kết quả `./gradlew dependencies` để khẳng định đúng minor version trước khi chạy.

Trong `build.gradle` được Initializr sinh, phần dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

Đây là **block dependencies**, chưa phải toàn bộ file Gradle. Giữ plugins Spring Boot, Java toolchain, repositories và Gradle wrapper do Initializr tạo. Không thêm `spring-boot-starter-web` vào demo: khi starter Servlet và WebFlux cùng có mặt, Boot 3 thường chọn inbound MVC/Servlet.

Cấu trúc:

```text
src/main/java/demo/reactiveauthz/
  ReactiveAuthzApplication.java
  SecurityConfig.java
  OwnerAuthorizationManager.java
  ProjectController.java
src/test/java/demo/reactiveauthz/
  OwnerAuthorizationIntegrationTests.java
  OwnerAuthorizationManagerTests.java
```

### 7.2. `ReactiveAuthzApplication.java`

```java
package demo.reactiveauthz;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveAuthzApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveAuthzApplication.class, args);
    }
}
```

### 7.3. `OwnerAuthorizationManager.java`: policy cốt lõi

```java
package demo.reactiveauthz;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.server.authorization.AuthorizationContext;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public final class OwnerAuthorizationManager
        implements ReactiveAuthorizationManager<AuthorizationContext> {

    @Override
    @SuppressWarnings("deprecation")
    public Mono<AuthorizationDecision> check(
            Mono<Authentication> authentication,
            AuthorizationContext context) {

        Object variable = context.getVariables().get("owner");
        String owner = variable instanceof String value ? value : null;

        if (owner == null || owner.isBlank()) {
            return Mono.just(new AuthorizationDecision(false));
        }

        return authentication
            .map(auth -> new AuthorizationDecision(
                isRealUser(auth) &&
                (hasAuthority(auth, "ROLE_ADMIN")
                    || owner.equals(auth.getName()))
            ))
            .defaultIfEmpty(new AuthorizationDecision(false));
    }

    private boolean isRealUser(Authentication authentication) {
        return authentication != null
            && authentication.isAuthenticated()
            && !(authentication instanceof AnonymousAuthenticationToken);
    }

    private boolean hasAuthority(
            Authentication authentication,
            String authority) {
        return authentication.getAuthorities().stream()
            .anyMatch(granted ->
                authority.equals(granted.getAuthority()));
    }
}
```

Đây là **class hoàn chỉnh Spring Security 6.5.x** với import đủ. Phân tích:

- `ReactiveAuthorizationManager<AuthorizationContext>` nhận ngữ cảnh của HTTP rule đang xét.
- `context.getVariables().get("owner")` lấy biến của pattern; thiếu/không phải String sẽ **deny**. Không ép kiểu bừa dẫn tới ClassCastException.
- `Mono<Authentication>` được xử lý bằng `map`, **không block**.
- `isRealUser` loại token anonymous. Không tin riêng `Authentication.isAuthenticated()`: trong một số configuration, `AnonymousAuthenticationToken.isAuthenticated()` có thể `true` dù đó không phải user đăng nhập.
- Nếu user là admin hoặc principal trùng owner, trả `new AuthorizationDecision(true)`; trường hợp khác trả false.
- `defaultIfEmpty(false)` là **deny rõ ràng** nếu publisher không phát `Authentication`.
- Không lấy role từ HTTP header `X-Role`; authorities đến từ cơ chế xác thực đã được Spring Security tin cậy.
- `@SuppressWarnings("deprecation")` dành riêng vì 6.5 đòi implement `check(...)` nhưng method này đã deprecated. Khi dùng Security 7.x phải migrate như mục 4.

**Giới hạn của demo:** so sánh owner path với `Authentication.getName()` hợp lý khi route được thiết kế theo username. Với resource IDs thực, phải lấy owner/tenant/ACL từ cơ sở dữ liệu tin cậy; người dùng có thể tự sửa path, không có bằng chứng URL tương ứng resource owner.

### 7.4. `SecurityConfig.java`: đặt manager vào HTTP policy

```java
package demo.reactiveauthz;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    public SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            OwnerAuthorizationManager ownerManager) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/projects/{owner}")
                    .access(ownerManager)
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    public MapReactiveUserDetailsService users() {
        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice-pass"))
            .roles("USER")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("bob-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(alice, bob, admin);
    }
}
```

Chú thích:

1. Rule `GET /public` được phép cho tất cả.
2. Rule `GET /projects/{owner}` gọi đúng `OwnerAuthorizationManager`. Pattern chứa biến `{owner}` trích xuất thành `AuthorizationContext.getVariables()`.
3. `anyExchange().denyAll()` từ chối URL/method không được khai báo.
4. HTTP Basic là hình thức gửi credential mỗi request để dễ test bằng curl, **không mã hóa mật khẩu**: HTTP Basic phải sử dụng trên HTTPS ở production. `formLogin` bị tắt để client API không nhận HTML redirect thay cho 401.
5. Password ví dụ được băm thông qua `PasswordEncoderFactories`; không lưu credential mẫu trong dự án thật.
6. Alice và Bob có `ROLE_USER`, admin có `ROLE_ADMIN`. Policy cho admin hoặc owner, không yêu cầu mọi owner đều phải có ROLE_USER (nhưng họ vẫn phải là real authenticated user); đây là thiết kế cụ thể của bài tập.
7. CSRF protection mặc định không bị tắt; các endpoint demo chỉ dùng GET, nên không phát sinh POST cần token.

Nếu một request không mang credential, `AuthorizationWebFilter` sẽ không tự cấp role; policy trả deny. Với `httpBasic` được bật, security entry point thông thường là 401. Nếu Alice gửi credential nhưng mở `/projects/bob`, decision false dẫn đến 403. Không cần controller viết `if (user.equals(...))` để giả lập việc bị chặn ở HTTP layer.

### 7.5. `ProjectController.java`

```java
package demo.reactiveauthz;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ProjectController {

    @GetMapping("/public")
    public Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping("/projects/{owner}")
    public Mono<String> project(@PathVariable String owner) {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName())
            .map(principal ->
                "projectOwner=" + owner + ";principal=" + principal);
    }
}
```

Controller chỉ trả nội dung minh họa. Với user Alice gọi `/projects/alice`: body là `projectOwner=alice;principal=alice`. Với admin gọi `/projects/bob`: body là `projectOwner=bob;principal=admin`. Điều này giúp nhìn thấy **owner trong URL** và **identity thực đã xác thực** là hai giá trị khác nhau.

Không dùng controller này để bảo vệ dữ liệu dự án thật: dữ liệu thật phải được query theo tenant/ACL đã kiểm tra tại service/repository; HTTP rule là **một lớp** bảo vệ, không đủ cho tác vụ nội bộ không đi qua HTTP.

### 7.6. Chạy ứng dụng, kiểm chứng response

Từ root của project Initializr:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Gọi API:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/projects/alice
curl -i -u alice:alice-pass http://localhost:8080/projects/alice
curl -i -u alice:alice-pass http://localhost:8080/projects/bob
curl -i -u bob:bob-pass http://localhost:8080/projects/bob
curl -i -u admin:admin-pass http://localhost:8080/projects/bob
curl -i -u alice:alice-pass http://localhost:8080/not-configured
```

Nếu PowerShell có alias `curl`, dùng `curl.exe`. Không dùng password thật trực tiếp trong shell command vì có thể lưu trong shell history/process list; ở đây là credential demo.

Dự kiến:

| Request | HTTP status | Body ở trường hợp 200 |
|---|---:|---|
| Không auth: `GET /public` | 200 | `public` |
| Không auth: `GET /projects/alice` | 401 | Không cố định |
| Alice: `GET /projects/alice` | 200 | `projectOwner=alice;principal=alice` |
| Alice: `GET /projects/bob` | 403 | Không cố định |
| Bob: `GET /projects/bob` | 200 | `projectOwner=bob;principal=bob` |
| Admin: `GET /projects/bob` | 200 | `projectOwner=bob;principal=admin` |
| Alice: `GET /not-configured` | 403 | Không cố định |

HTTP status và challenge header chịu ảnh hưởng cấu hình entry point/denied handler; những giá trị này là **kỳ vọng cho cấu hình demo**. Không assert response body mặc định của 401/403 vì format có thể thay đổi theo phiên bản.

## 8. Kiểm thử end-to-end với WebTestClient

Bài học phân quyền cần test **kết quả HTTP**: policy có thể trả đúng Boolean nhưng security chain/route matcher không gọi nó do thứ tự config sai. `WebTestClient` chạy qua WebFlux security chain và kiểm tra status/body như client thật.

Tạo `src/test/java/demo/reactiveauthz/OwnerAuthorizationIntegrationTests.java`:

```java
package demo.reactiveauthz;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class OwnerAuthorizationIntegrationTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointIsAvailable() {
        client.get().uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void unauthenticatedUserCannotAccessProject() {
        client.get().uri("/projects/alice")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void ownerCanReadOwnProject() {
        client.get().uri("/projects/alice")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("projectOwner=alice;principal=alice");
    }

    @Test
    void ordinaryUserCannotReadAnotherProject() {
        client.get().uri("/projects/bob")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void secondOwnerCanReadOwnProject() {
        client.get().uri("/projects/bob")
            .headers(h -> h.setBasicAuth("bob", "bob-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("projectOwner=bob;principal=bob");
    }

    @Test
    void adminCanReadAnotherUsersProject() {
        client.get().uri("/projects/bob")
            .headers(h -> h.setBasicAuth("admin", "admin-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("projectOwner=bob;principal=admin");
    }

    @Test
    void denyAllCatchesUnlistedRoute() {
        client.get().uri("/not-configured")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

Các test này kiểm tra 7 tình huống: public, anonymous, owner, người khác, owner thứ hai, admin và route nằm ngoài policy. Các phép kiểm tra **không dùng `mockUser`**, mà gửi HTTP Basic thật tới in-memory user store, nên tích hợp được cả authentication và authorization. Test trả 401/403 ở security layer trước controller.

### 8.1. Unit test cho chính manager bằng StepVerifier

Integration test quan trọng, nhưng để bắt lỗi logic chi tiết (ví dụ thiếu biến `owner`, authentication publisher empty), ta unit test trực tiếp manager. Tạo `src/test/java/demo/reactiveauthz/OwnerAuthorizationManagerTests.java`:

```java
package demo.reactiveauthz;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.web.server.authorization.AuthorizationContext;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OwnerAuthorizationManagerTests {

    private final OwnerAuthorizationManager manager =
        new OwnerAuthorizationManager();

    private Authentication alice() {
        return UsernamePasswordAuthenticationToken.authenticated(
            "alice", "unused",
            List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    private Authentication admin() {
        return UsernamePasswordAuthenticationToken.authenticated(
            "admin", "unused",
            List.of(new SimpleGrantedAuthority("ROLE_ADMIN")));
    }

    private AuthorizationContext contextWithOwner(String owner) {
        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/projects/" + owner).build());
        return new AuthorizationContext(
            exchange, Map.of("owner", owner));
    }

    @Test
    void ownerIsGranted() {
        StepVerifier.create(manager.check(
                Mono.just(alice()), contextWithOwner("alice")))
            .assertNext(decision ->
                assertTrue(decision.isGranted()))
            .verifyComplete();
    }

    @Test
    void anotherOwnerIsDenied() {
        StepVerifier.create(manager.check(
                Mono.just(alice()), contextWithOwner("bob")))
            .assertNext(decision ->
                assertFalse(decision.isGranted()))
            .verifyComplete();
    }

    @Test
    void administratorIsGranted() {
        StepVerifier.create(manager.check(
                Mono.just(admin()), contextWithOwner("alice")))
            .assertNext(decision ->
                assertTrue(decision.isGranted()))
            .verifyComplete();
    }

    @Test
    void emptyAuthenticationIsDenied() {
        StepVerifier.create(manager.check(
                Mono.empty(), contextWithOwner("alice")))
            .assertNext(decision ->
                assertFalse(decision.isGranted()))
            .verifyComplete();
    }

    @Test
    void missingOwnerVariableIsDenied() {
        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/projects/alice").build());
        var context = new AuthorizationContext(exchange, Map.of());

        StepVerifier.create(manager.check(Mono.just(alice()), context))
            .assertNext(decision ->
                assertFalse(decision.isGranted()))
            .verifyComplete();
    }
}
```

Đây là class JUnit5, cần `spring-boot-starter-test`, `reactor-test` và `spring-security-test` theo dependencies ở mục 7. Kiểm tra kỹ: constructor `AuthorizationContext(exchange, variables)` có ở WebFlux Security API, và `MockServerWebExchange` ở test library của Spring Framework.

Unit tests chỉ gọi `manager.check` với `Authentication` giả lập đáng tin *trong phạm vi test*; chúng **không** chứng minh password thật được xác minh. Integration tests làm phần đó. Đối với bản Spring Security 7.x, test trực tiếp method `authorize` với `AuthorizationResult` tương ứng thay vì `check`.

Chạy:

```bash
./gradlew test
```

Trên Windows:

```powershell
.\gradlew.bat test
```

Dự kiến **12 test pass** (7 integration và 5 unit) với cấu hình được trình bày, nếu project sử dụng đúng Spring Boot 3.5/Spring Security 6.5, Java17 và dependencies. Đây là **kết quả kỳ vọng từ mã nguồn**, không phải lời tuyên bố test đã được chạy. Không cố assert thread name hoặc nội dung body mặc định của 401/403. Nếu khác kết quả, kiểm tra version, actual HTTP status/header, rule matcher và classpath.

## 9. AuthorizationDecision không thay thế việc bảo vệ resource thật

### 9.1. Chống IDOR/BOLA

Đường dẫn `/projects/{owner}` là minh họa. Trong ứng dụng quản lý dự án thật, URL thường là `/projects/{id}`. User có thể đoán hoặc đổi `id`; nếu policy chỉ kiểm tra `auth.isAuthenticated()`, request có nguy cơ thành **IDOR/BOLA (Broken Object Level Authorization)**.

Một thiết kế tốt hơn:

```text
GET /projects/853
  -> Authentication principal + tenant membership
  -> AuthorizationContext có projectId="853"
  -> ProjectPermissionRepository.existsAllowed(user, tenant, projectId)
       trả Mono<Boolean> từ R2DBC/reactive store
  -> AuthorizationDecision(allowed)
  -> service/repository vẫn query với cùng tenant/ACL constraint
  -> response chỉ chứa record được phép
```

Bảo vệ ở **hai tầng** khi cần: route policy bảo vệ HTTP boundary, còn service/repository đảm bảo không có code path phụ (message consumer, batch job, internal call) truy cập dữ liệu ngoài quyền.

### 9.2. Mẫu truy vấn bất đồng bộ, không block

Ví dụ **mảnh code trong manager tùy biến** với repository reactive do dự án định nghĩa:

```java
return authentication
    .filter(auth -> auth.isAuthenticated()
        && !(auth instanceof AnonymousAuthenticationToken))
    .flatMap(auth ->
        permissionRepository.canRead(
            auth.getName(), tenantId, projectId))
    .map(AuthorizationDecision::new)
    .defaultIfEmpty(new AuthorizationDecision(false));
```

Giả định `permissionRepository.canRead(...)` trả `Mono<Boolean>`, và `tenantId`/`projectId` đã được trích, validate theo thiết kế. Đây không phải class độc lập; test 401/403, record không tồn tại, permission store lỗi, tenant mismatch và race condition.

Nếu permission repository trả `Mono.empty()` cho “không tìm thấy”, `defaultIfEmpty(false)` đảm bảo deny. Nếu backend lỗi `Mono.error`, lỗi được lan truyền; tuyệt đối không dùng `onErrorReturn(new AuthorizationDecision(true))`. Đối với hệ thống dữ liệu nhạy cảm, chọn fail-closed và quan sát lỗi vận hành; không che 500 thành 200.

### 9.3. Nguy cơ TOCTOU và cache quyền

Quyền có thể thay đổi **sau khi authorization ở HTTP layer kiểm tra** nhưng trước khi service đọc/ghi resource (time-of-check vs time-of-use). Với thao tác nhạy cảm, nên đưa điều kiện tenant/owner/ACL vào truy vấn dữ liệu hoặc transaction thích hợp. Cache kết quả quyền phải có TTL/invalidation rõ ràng, key bao gồm identity, tenant, resource, action và policy version; không cache Boolean `true` theo URL chung cho mọi user.

### 9.4. Đừng nhầm authentication với authorization

Khi gọi `Authentication.isAuthenticated()`, một anonymous token có thể `true` theo ý nghĩa nội bộ framework. Dùng các built-in managers `authenticated()`/`fullyAuthenticated()` khi policy chỉ cần authentication level, hoặc một `AuthenticationTrustResolver`/type check thích hợp trong custom logic. Bài demo loại `AnonymousAuthenticationToken` để tránh cho phép `anonymousUser` như một user bình thường.

Không tự tạo `Authentication` từ query string, body, header mà chưa xác thực rồi gọi `withAuthentication` để khiến custom manager trả allow. Điều đó là **bypass authentication**, không phải phân quyền động.

## 10. Quy tắc cho ReactiveAuthorizationManager chất lượng production

### 10.1. Fail closed, nhưng không biến mọi lỗi thành 403

- Không có Authentication hợp lệ → không cho phép.
- Không có path/resource variable, tenant không hợp lệ → deny hoặc trả 400 theo validation layer; không allow.
- User có Authentication nhưng thiếu quyền → deny.
- Permission backend gặp lỗi → truyền lỗi và xử lý ở tầng phù hợp (thường 5xx), đồng thời bảo đảm không trả dữ liệu. Không biến lỗi backend thành “user được phép”.
- Nếu cần 404 để không tiết lộ resource existence, đó là **chính sách ứng dụng**, cần thiết kế nhất quán, không vô tình che sai quyền thành resource not found.
- Nếu manager định dùng `Mono.empty()` để abstain trong tổ hợp nhiều manager, phải có policy fallback **tường minh** và test; không coi empty là deny hoặc allow theo cảm tính.

### 10.2. Không thực thi blocking logic trên event-loop

Sai:

```java
return authentication.map(auth -> {
    boolean allowed = jdbcRepository.checkPermission(auth.getName());
    return new AuthorizationDecision(allowed);
});
```

Snippet này **sai trong WebFlux** nếu `jdbcRepository.checkPermission` là JDBC blocking và đang chạy trên Netty event loop: request có thể bị nghẽn. Dùng repository reactive như R2DBC khi thích hợp.

Nếu phải bắc cầu legacy service đồng bộ, bọc đúng phần blocking:

```java
return authentication.flatMap(auth ->
    Mono.fromCallable(() ->
            legacyService.hasPermission(auth.getName(), resourceId))
        .subscribeOn(Schedulers.boundedElastic())
        .map(AuthorizationDecision::new)
).defaultIfEmpty(new AuthorizationDecision(false));
```

Đây là **mảnh code** cần import `Schedulers`, `Mono`, kiểu `legacyService` và `resourceId` theo dự án. `boundedElastic` tránh block event loop nhưng không biến tác vụ thành non-blocking; giới hạn concurrency/connection pool, timeout và capacity phù hợp. Không gọi `block()` trong manager.

### 10.3. Hạn chế network call cho mọi request khi không cần

Một policy gọi service phân quyền từ xa cho **mọi** URL có thể làm hệ thống phụ thuộc availability của service đó, tăng latency và tải. Dùng built-in `permitAll`/`authenticated`/`hasAuthority` cho rule đơn giản; chỉ gọi remote policy khi cần và cache có kiểm soát. Đặt timeout, circuit breaker, fallback fail-closed, correlation IDs và metrics đo p95/p99; không log token/password hay toàn bộ security context.

### 10.4. Tách policy khỏi controller và kiểm thử độc lập

Manager nên chứa **quy tắc phân quyền**, không chứa nghiệp vụ trả response hoặc UI redirect. Service tài nguyên có thể cung cấp truy vấn ACL reactive cho manager, nhưng không nên để manager tự encode JSON response hay set cookie. Đặt unit test cho mọi nhánh (allow, deny, no auth, missing variable, backend error) và integration test cho toàn HTTP chain.

### 10.5. Thận trọng với method và path

- `GET /projects/{owner}` không tự bảo vệ `POST /projects/{owner}` hoặc những endpoint khác; dùng rule rõ theo từng method, còn `anyExchange().denyAll()` làm safety net.
- Nếu cùng resource có endpoints alias, webhook, GraphQL resolver hoặc message consumer, HTTP rule ở một URL không bảo vệ các code path khác.
- Path matcher chuẩn hóa URI theo framework; không tự so chuỗi `getPath().value().startsWith(...)` với dữ liệu chưa canonicalized để quyết định nhạy cảm nếu matcher có sẵn.
- Không cho client tự định role/tenant bằng query parameter rồi so với input đó mà bỏ qua authoritative membership.
- Không dùng `permitAll()` cho toàn `/projects/**` rồi kỳ vọng một `access(...)` phía sau vẫn chạy. Rule có thứ tự ưu tiên.

## 11. Bảng lỗi phổ biến

| Triệu chứng | Nguyên nhân | Cách sửa |
|---|---|---|
| `@Override check` không biên dịch ở Spring Security 7 | Interface đã chuyển sang `authorize` | Implement `authorize(Mono<Authentication>, T) -> Mono<AuthorizationResult>` |
| Class 6.5 implement mỗi `authorize` nhưng compiler vẫn đòi `check` | `check` vẫn là abstract trong 6.5 | Implement `check` cho 6.5 hoặc nâng version đồng bộ |
| `getVariables().get("owner")` là `null` | Matcher không có biến hoặc rule khác match trước | Kiểm tra `pathMatchers` và thứ tự, deny khi thiếu biến |
| Anonymous truy cập được endpoint có owner `anonymousUser` | Chỉ kiểm tra `isAuthenticated()` | Dùng trust resolver/built-in policy hoặc loại anonymous token |
| User thường xem dữ liệu người khác | Tin path/query do client chọn như chứng cứ ACL | Tra permission/ownership từ nguồn tin cậy, bảo vệ service/repo |
| Policy trả `Mono.empty()` khi sai quyền | Nhầm abstain với deny | Trả `AuthorizationDecision(false)` và có fallback deny |
| Manager tự `subscribe()` | Tạo subscription tách rời, mất lifecycle/error | Compose publisher và return |
| Manager gọi `block()` hoặc JDBC trực tiếp | Block event loop | Dùng reactive repository hoặc offload bounded blocking có giới hạn |
| 401 khi chưa có credential | HTTP Basic entry point, yêu cầu authentication | Hành vi đúng cho API, đừng đổi thành 403 bằng tay |
| 403 khi đã đăng nhập nhưng thiếu role | Authorization deny | Kiểm tra role/authority thực và policy |
| Redirect tới login thay vì 401 | Có form login/entry point tương tác | Thiết kế security chain phù hợp loại client |
| `/projects/{owner}` trả 404 dù manager đúng | Controller mapping không khớp URL | Phân biệt security authorization và WebFlux routing |
| Policy backend lỗi nhưng app vẫn trả 200 | Dùng `onErrorReturn(true)`/fail-open | Fail closed, theo dõi lỗi và kiểm tra kết quả |
| `.authenticated()` đặt sau `.access(...)` không có hiệu lực | Rule đầu khớp đã được dùng | Gộp điều kiện trong một policy hoặc sắp xếp lại rule |
| Test unit manager pass nhưng HTTP route mở | Chưa gắn manager/chain không match | Viết WebTestClient integration tests qua security filter |
| Sai loại `AuthorizationContext` | Dùng `RequestAuthorizationContext` Servlet | Dùng `org.springframework.security.web.server.authorization.AuthorizationContext` |

## 12. Bài tập và đáp án

**Bài 1 — AuthorizationDecision(true) nghĩa là gì?** Một manager trả `Mono.just(new AuthorizationDecision(true))`. Spring Security đã xác thực user chưa, và controller có tự động nhận role ADMIN không?

**Đáp án:** Đây là quyết định cho phép theo policy đang xét. Nó không xác thực credential, không gán role mới, không đổi principal và không bảo vệ các service ngoài luồng HTTP. Authentication vẫn phải đến từ cơ chế tin cậy trước khi manager quyết định.

**Bài 2 — Empty khác false thế nào?** Một manager trả `Mono.empty()` khi user không sở hữu resource. Tại sao không nên?

**Đáp án:** `Mono.empty()` có nghĩa chưa có quyết định (abstain), còn `AuthorizationDecision(false)` là từ chối tường minh. Consumer/composition có thể xử lý empty khác deny; với resource nhạy cảm, trả false và cấu hình fallback deny rõ ràng.

**Bài 3 — Owner ở URL có đủ không?** Client gọi `/projects/alice` và đăng nhập bằng Alice. Có chắc mọi dữ liệu database trả về đều thuộc Alice?

**Đáp án:** Không. Path là input do client chọn, không bảo đảm owner/tenant của record thật. Phải kiểm tra quyền theo dữ liệu authoritative trong repository/service, đặc biệt để chống BOLA/IDOR.

**Bài 4 — 401 hay 403?** API bật HTTP Basic. Không gửi credential vào `/projects/alice` thì thường nhận gì? Đăng nhập Alice rồi gọi `/projects/bob` thì thường nhận gì?

**Đáp án:** Không credential: 401 từ authentication entry point; đã xác thực nhưng deny: 403 từ access-denied handling. Các status chính xác tùy security entry point và cấu hình cụ thể, không được hardcode trong `AuthorizationDecision`.

**Bài 5 — Vì sao method policy nhận Mono<Authentication>?** Có thể gọi `authentication.block()` rồi dùng như Java đồng bộ trong WebFlux không?

**Đáp án:** Không. Reactor dùng lazy publisher/Context để thực hiện asynchronous request pipeline. `block()` có thể block event-loop và phá reactive contract. Compose bằng `map`/`flatMap` rồi trả publisher.

**Bài 6 — Một admin thiếu ROLE_USER có được phép không?** Theo manager ở mục 7, user admin có `ROLE_ADMIN` nhưng không có `ROLE_USER`. Có vào `/projects/bob` được không?

**Đáp án:** Có, vì policy là “real authenticated user AND (ROLE_ADMIN OR username bằng owner)”; không có điều kiện bắt buộc ROLE_USER. Nếu sản phẩm đòi cả hai role thì phải đổi policy và test.

**Bài 7 — Thay manager sang Security 7.x ra sao?** Mã 6.5 đang `@Override check(Mono<Authentication>, AuthorizationContext) -> Mono<AuthorizationDecision>`.

**Đáp án:** Trong 7.x implement `authorize(Mono<Authentication>, AuthorizationContext) -> Mono<AuthorizationResult>`, có thể trả `AuthorizationDecision` vì nó implements `AuthorizationResult`. Sửa chữ ký theo dependency đang dùng và test lại.

**Bài 8 — Test nào quan trọng nhất?** Vì sao một unit test gọi `manager.check(Mono.just(alice),context)` chưa đủ chứng minh route được bảo vệ?

**Đáp án:** Unit test chỉ thử logic manager. Integration test qua `SecurityWebFilterChain` xác minh đúng matcher, order, authentication, entry point và response HTTP. Cần cả hai.

**Bài 9 — Permission service trả lỗi?** Nếu repository không kết nối được, manager nên trả `new AuthorizationDecision(true)` cho user đã login để “giữ trải nghiệm” không?

**Đáp án:** Không. Đó là fail-open, có thể lộ dữ liệu. Propagate error/fail-closed và trả lỗi vận hành phù hợp; không tiết lộ dữ liệu nhạy cảm.

**Bài 10 — Vì sao không đặt mọi route vào một manager tùy biến?**

**Đáp án:** `permitAll`, `authenticated`, `hasAuthority` cho rule đơn giản nhanh, dễ kiểm tra và thường tránh call policy backend không cần thiết. Chỉ dùng custom manager khi điều kiện thực sự cần dữ liệu/context phức tạp; vẫn giữ `anyExchange().denyAll()`.

## 13. Checklist dùng trong dự án

- [ ] Dùng `ServerHttpSecurity`/`SecurityWebFilterChain` cho WebFlux, không nhầm Servlet APIs.
- [ ] Ghi rõ Spring Security version; nếu 6.5, implement `check`; nếu 7.x, implement `authorize`.
- [ ] Gắn `ReactiveAuthorizationManager<AuthorizationContext>` vào đúng `pathMatchers(...).access(...)`.
- [ ] Rule cụ thể trước `anyExchange().denyAll()`; xác minh ordering của nhiều chain.
- [ ] Với custom policy, không tin `isAuthenticated()` một mình cho anonymous token.
- [ ] Thiếu principal/biến path/ACL rõ ràng -> explicit deny.
- [ ] Không dùng `Mono.empty()` để thay thế deny hoặc bỏ qua error signal.
- [ ] Không gọi `block()`/`subscribe()` trong manager; dùng reactive composition.
- [ ] Path/header/query do client kiểm soát không thay thế resource ownership/tenant ACL đã được xác minh.
- [ ] Tránh backend authorization fail-open; quản lý timeout và fallback an toàn.
- [ ] Manager không set HTTP response trực tiếp; để framework xử lý 401/403.
- [ ] Kiểm tra 401 chưa xác thực, 403 thiếu quyền, 200 đủ quyền bằng WebTestClient.
- [ ] Kiểm thử quyền dữ liệu ở service/repository và các đường đi ngoài HTTP.
- [ ] Theo dõi latency/deny/error của policy mà không log token/password/PII quá mức.
- [ ] Bảo vệ tenant boundaries, resource ownership và thay đổi quyền đồng thời.

## 14. Tóm tắt nhanh

```text
Reactive HTTP request
    |
    v
Authentication đã được xác minh
    |
    v
AuthorizationWebFilter
    |
    v
ReactiveAuthorizationManager<AuthorizationContext>
    |-- Mono<Authentication>             : ai đang gọi?
    |-- AuthorizationContext.getExchange : HTTP request/exchange?
    |-- AuthorizationContext.getVariables: path variables?
    |
    +-- AuthorizationDecision(true)  -> cho qua rule
    +-- AuthorizationDecision(false) -> từ chối
    +-- Mono.empty()                 -> không quyết định
    +-- Mono.error(e)                -> lỗi pipeline

Spring Security 6.5: check(...) deprecated, authorize(...) default
Spring Security 7.x: implement authorize(...) -> Mono<AuthorizationResult>

HTTP Basic chưa xác thực -> thường 401
Đã xác thực, thiếu quyền -> thường 403
Form login chưa xác thực -> có thể redirect /login
```

Điểm mấu chốt: **`ReactiveAuthorizationManager` quyết định quyền dựa trên identity đáng tin và context request; `AuthorizationDecision` là kết quả**, không phải cách tạo authentication hoặc ghi HTTP response. Với dữ liệu thật, luôn bảo vệ quyền ở resource/service/repository, chứ không chỉ ở tên URL.

## 15. Tài liệu chính thức

- [Spring Security 6.5 — ReactiveAuthorizationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html)
- [Spring Security 7.x — ReactiveAuthorizationManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html)
- [Spring Security — AuthorizationDecision API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationDecision.html)
- [Spring Security — AuthorizationResult API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationResult.html)
- [Spring Security — AuthorizationContext API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/AuthorizationContext.html)
- [Spring Security — Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — Testing WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/test/web/)
- [Spring Security — AuthorityReactiveAuthorizationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorityReactiveAuthorizationManager.html)
- [Spring Security — AuthorizationWebFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/AuthorizationWebFilter.html)
