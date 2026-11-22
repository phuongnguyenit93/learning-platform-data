# ReactiveAuthorizationManager với AuthorizationContext trong Spring Security WebFlux

## 1. Bài toán và kết quả cần đạt

Khi bảo vệ một HTTP API reactive, quy tắc “đã đăng nhập mới được gọi” thường không đủ. Hãy xét endpoint:

```http
GET /api/tenants/TENANT_A/documents/42
DELETE /api/tenants/TENANT_A/documents/42
```

Để quyết định cho phép hay từ chối, ứng dụng cần đồng thời biết **ai đang gọi**, **HTTP method**, **tenant trên đường dẫn**, **document ID**, **quyền chức năng** và **thông tin nghiệp vụ của tài liệu**. Trong Spring Security cho WebFlux, một cách viết chính sách có kiểu rõ ràng là dùng `ReactiveAuthorizationManager<AuthorizationContext>` trong cấu hình `ServerHttpSecurity.authorizeExchange(...).access(...)`.

Bài thuộc nhóm **HTTP trên WebFlux** của module Spring Security Authorization. Sau khi học, bạn sẽ:

1. Phân biệt `ReactiveAuthorizationManager<AuthorizationContext>` (phân quyền HTTP trong WebFlux) với `AuthorizationManager<RequestAuthorizationContext>` (Servlet) và reactive method-security authorization.
2. Hiểu `Mono<Authentication>` và `AuthorizationContext` chứa những gì; vì sao **không dùng `block()`** hoặc `SecurityContextHolder` kiểu imperative trong authorization path.
3. Truy cập `context.getExchange()`, `context.getVariables()`, đọc path variables đúng cách và xử lý malformed ID.
4. Cấu hình manager tùy chỉnh bằng `.pathMatchers(HttpMethod.GET, ...).access(manager)`, phối hợp `permitAll`, `hasAuthority`, `denyAll` và thứ tự matcher.
5. Kết hợp quyền READ/DELETE với tenant membership, owner, trạng thái tài liệu và một policy source trả về `Mono<Boolean>`.
6. Xử lý **anonymous**, thiếu authentication, lỗi nguồn quyền, thiếu biến đường dẫn và không có bản ghi theo hướng **deny by default**.
7. Test bằng `WebTestClient` và `spring-security-test`, có kiểm tra status 200/204/401/403, CSRF và **method body không chạy khi quyền bị từ chối**.
8. Biết các giới hạn production: HTTP authorization khác object authorization ở service, biến tenant trong path không phải danh tính tin cậy, race condition, reactive data access, caching, multi-tenant và hiệu ứng phụ.

**Phiên bản minh họa:** Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x, Spring WebFlux và Reactor. Các ví dụ dùng convention của nhánh 6.5. Từ Spring Security 6.4, `ReactiveAuthorizationManager.check(...)` đã được đánh dấu deprecated để hướng tới `authorize(...)`; bài sẽ nói rõ để tránh áp dụng máy móc API sang 7.x.

## 2. Kiến trúc: request, manager, Mono quyết định và handler

```text
HTTP GET /api/tenants/TENANT_A/documents/42
  |
  v
SecurityWebFilterChain
  |
  v
WebFlux exchange matcher
  pathMatchers(GET, "/api/tenants/{tenantId}/documents/{docId}")
  |
  v
ReactiveAuthorizationManager<AuthorizationContext>
  |  Mono<Authentication>             -> actor/authorities
  |  AuthorizationContext.variables  -> tenantId, docId
  |  AuthorizationContext.exchange   -> HTTP method/request
  |
  +-- thiếu auth/quyền/tenant/doc/state --> AuthorizationDecision(false)
  |
  +-- policy source (Mono<Boolean>)
        |
        +-- true  --> AuthorizationDecision(true)
        +-- false --> AuthorizationDecision(false)
        +-- error --> deny/fail closed theo chính sách
  |
  v
AuthorizationWebFilter / ExceptionTranslation
  |  401 khi cần authentication
  |  403 khi authenticated nhưng không được phép
  |
  +-- ALLOW -> WebFlux handler/controller -> Mono<ResponseEntity<...>>
  +-- DENY  -> handler body không được gọi
```

Spring Security tự cung cấp thông tin authentication dưới dạng publisher. Manager **không cần tự xây một `SecurityContext` mới** và không nên dựa vào `ThreadLocal` của request thread: trong Reactor, một pipeline có thể đổi thread mà vẫn giữ Reactor Context.

### 2.1. Các interface và class quan trọng

| Thành phần | Package chính | Trách nhiệm |
| --- | --- | --- |
| `ReactiveAuthorizationManager<T>` | `org.springframework.security.authorization` | Đưa ra quyết định reactive đối với đối tượng `T` |
| `AuthorizationContext` | `org.springframework.security.web.server.authorization` | Chứa `ServerWebExchange` và các URI template variables |
| `AuthorizationDecision` | `org.springframework.security.authorization` | Kết quả được/không được cấp quyền |
| `ServerHttpSecurity` | `org.springframework.security.config.web.server` | Cấu hình WebFlux HTTP security |
| `SecurityWebFilterChain` | `org.springframework.security.web.server` | Chuỗi WebFilter bảo mật |
| `Authentication` | `org.springframework.security.core` | Danh tính và authorities đã được framework xác thực |
| `ReactiveSecurityContextHolder` | `org.springframework.security.core.context` | Truy cập SecurityContext theo Reactor Context |
| `WebTestClient` | `org.springframework.test.web.reactive.server` | Kiểm thử HTTP WebFlux |
| `SecurityMockServerConfigurers` | `org.springframework.security.test.web.reactive.server` | Giả lập authentication/CSRF trong reactive tests |

**Không lẫn với Servlet:** Servlet dùng `HttpSecurity.authorizeHttpRequests` và `AuthorizationManager<RequestAuthorizationContext>`; WebFlux dùng `ServerHttpSecurity.authorizeExchange` và `ReactiveAuthorizationManager<AuthorizationContext>`. Không import nhầm `HttpServletRequest` hay `RequestAuthorizationContext` trong project WebFlux.

## 3. Cấu trúc `ReactiveAuthorizationManager<AuthorizationContext>`

### 3.1. Chữ ký trong Spring Security 6.5

```java
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.server.authorization.AuthorizationContext;
import reactor.core.publisher.Mono;

public class SampleManager
        implements ReactiveAuthorizationManager<AuthorizationContext> {

    @Override
    @SuppressWarnings("deprecation")
    public Mono<AuthorizationDecision> check(
            Mono<Authentication> authentication,
            AuthorizationContext context) {
        return authentication
            .map(auth -> new AuthorizationDecision(
                auth.isAuthenticated()
                    && auth.getAuthorities().stream()
                       .anyMatch(a -> "DOC_READ".equals(a.getAuthority()))))
            .defaultIfEmpty(new AuthorizationDecision(false));
    }
}
```

Đây là một **class Java độc lập về cú pháp** nếu các dependency Spring Security và Reactor có sẵn, nhưng mới kiểm tra authority, chưa kiểm tra tenant/resource/owner, và `auth.isAuthenticated()` **không đủ để loại trừ anonymous token**. Mẫu đầy đủ ở mục 8 bổ sung các điều kiện đó.

**Chi tiết tương thích version:**

- Ở Spring Security 6.5, `check(Mono<Authentication>, T)` trả `Mono<AuthorizationDecision>` vẫn là cách implement phổ biến của interface; nó đã được gắn deprecated.
- Interface còn có `authorize(Mono<Authentication>, T)`, trả `Mono<AuthorizationResult>` và được khuyến nghị cho API mới. `AuthorizationDecision` thực thi mô hình kết quả authorization tương ứng.
- Vì signature/khả năng override có thể thay đổi giữa dòng 6.5 và 7.x, hãy đối chiếu Javadoc version thực tế. Mẫu ở đây nhắm chính xác **6.5.x**; không coi annotation `@SuppressWarnings("deprecation")` là giải pháp migration cho tất cả version.
- `Mono.empty()` có thể biểu thị abstain/không có quyết định trong một số manager; việc hệ thống xử lý abstain tùy composition. Với policy nhạy cảm, ví dụ **trả explicit deny** cho mọi trường hợp không đủ điều kiện để tránh suy diễn.

### 3.2. `Mono<Authentication>` không phải `Authentication`

Trong WebFlux, đối số thứ nhất là **publisher**, không phải đối tượng authentication đồng bộ:

```java
return authentication
    .filter(auth -> auth.isAuthenticated())
    .flatMap(auth -> reactivePolicy.canRead(auth)
        .map(AuthorizationDecision::new))
    .defaultIfEmpty(new AuthorizationDecision(false));
```

`reactivePolicy.canRead(auth)` được giả định trả `Mono<Boolean>`. Đây chỉ là **fragment**. Không gọi:

```java
// PHẢN VÍ DỤ: có thể block Netty event-loop.
Authentication auth = authentication.block();

// PHẢN VÍ DỤ: ThreadLocal không phải nguồn chính của reactive context.
Authentication auth2 = SecurityContextHolder
    .getContext().getAuthentication();
```

`block()` trong WebFlux có thể gây chặn event-loop, giảm throughput hoặc ném lỗi trong môi trường non-blocking. Nếu data source hiện tại dùng JDBC/JPA blocking, chuyển sang R2DBC/reactive service hoặc offload có kiểm soát lên scheduler phù hợp; không giấu blocking call trong `Mono.just(repository.findById(...))` rồi coi là reactive.

### 3.3. `AuthorizationContext`: exchange và variables

```java
ServerWebExchange exchange = context.getExchange();
HttpMethod method = exchange.getRequest().getMethod();

Object tenantValue = context.getVariables().get("tenantId");
Object documentValue = context.getVariables().get("docId");
```

Các biến nhận từ `pathMatchers("/api/tenants/{tenantId}/documents/{docId}")`. Trong API 6.5, `getVariables()` là `Map<String,Object>`; không ép mọi trường hợp là `String` trước khi kiểm tra. `getExchange()` cho phép đọc HTTP method, request headers, path, query params, attributes, remote address... nhưng **dữ liệu từ HTTP request không tự trở thành thông tin được tin cậy**.

Ví dụ: client có thể tự viết `/api/tenants/TENANT_B/documents/42`, nên manager phải xác minh người gọi thực sự được truy cập TENANT_B. Đừng đọc `X-Tenant-Id` rồi mặc nhiên coi nó là tenant của principal. Tương tự, `docId="hello"` hoặc ID tràn giới hạn `long` nên bị deny hoặc trả lỗi được kiểm soát, không gây 500 vô tình.

### 3.4. `AuthorizationDecision(true/false)`, thiếu auth và error

Các loại kết quả thường gặp:

| Trường hợp | Chính sách ví dụ | Kết quả HTTP phổ biến |
| --- | --- | --- |
| Authenticated, có authority + đúng tenant + đúng resource | Allow | Handler được gọi, 2xx hoặc 404 theo dữ liệu |
| Authenticated nhưng thiếu authority | Deny | 403 Forbidden |
| Authenticated nhưng tenant khác | Deny | 403 (hoặc 404 nếu API che giấu tồn tại tài nguyên) |
| Authenticated, resource không tồn tại | Deny | 403 trong ví dụ |
| Anonymous/chưa đăng nhập | Deny/need authentication | 401 khi HTTP Basic entry point được cấu hình |
| Path variable không hợp lệ | Explicit deny | 403 trong ví dụ |
| Policy backend bị lỗi | Fail closed | 403 trong ví dụ; production có thể dùng 503 khi an toàn và không tiết lộ dữ liệu |

**Không đồng nhất 401/403 với ẩn thông tin:** muốn trả 404 để tránh tiết lộ ID thuộc tenant khác, cần thiết kế response/exception handling nhất quán. Manager chỉ cung cấp quyết định; HTTP status cuối cùng còn phụ thuộc authentication entry point, access-denied handler, CSRF filter và WebFlux exception mapping.

## 4. Cấu hình `ServerHttpSecurity.authorizeExchange(...)`

### 4.1. Lắp custom manager

```java
@Bean
SecurityWebFilterChain filterChain(
        ServerHttpSecurity http,
        DocumentAuthorizationManager manager) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/public/ping").permitAll()
            .pathMatchers(HttpMethod.GET,
                "/api/tenants/{tenantId}/documents/{docId}")
                .access(manager)
            .pathMatchers(HttpMethod.DELETE,
                "/api/tenants/{tenantId}/documents/{docId}")
                .access(manager)
            .anyExchange().denyAll()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Đây là **fragment bean**; class `DocumentAuthorizationManager` và imports nằm trong project hoàn chỉnh ở mục 8. Thứ tự matcher quan trọng: đặt route cụ thể trước `anyExchange`; nếu `anyExchange().permitAll()` xuất hiện sai vị trí, các route phía sau có thể không được bảo vệ như dự định.

### 4.2. Khi nào dùng `.hasAuthority(...)` thay `.access(manager)`?

Dùng cú pháp có sẵn khi rule đơn giản:

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/public/**").permitAll()
    .pathMatchers(HttpMethod.GET, "/api/reports/**")
        .hasAuthority("REPORT_READ")
    .anyExchange().authenticated()
)
```

Dùng `.access(manager)` nếu cần logic riêng theo path variables, tenant membership, owner, document state, lookup reactive hoặc quyết định từ PDP. **Không phức tạp hóa mọi route:** những route chỉ cần authenticated/role có thể dùng manager tích hợp để dễ đọc và kiểm thử.

### 4.3. CSRF và HTTP method

Trong WebFlux, CSRF protection thường được bật mặc định. Khi dùng `DELETE`, `POST`, `PUT`, `PATCH` với session/cookie authentication, request phải có CSRF token hợp lệ. Vì thế test DELETE trong bài dùng:

```java
webTestClient
    .mutateWith(mockUser("alice").authorities(
        new SimpleGrantedAuthority("DOC_DELETE")))
    .mutateWith(csrf())
    .delete()
    .uri("/api/tenants/TENANT_A/documents/42")
    .exchange()
    .expectStatus().isNoContent();
```

Đây là **fragment test**. Nếu không có CSRF token, một request được phép theo custom manager vẫn có thể nhận **403 từ CsrfWebFilter**, không chứng minh manager deny. Đừng tắt CSRF trên toàn bộ ứng dụng chỉ để test dễ đi; với stateless bearer-token API, quyết định bật/tắt CSRF phải dựa trên threat model authentication và những nguồn browser tự gửi credentials.

### 4.4. Router functions và `pathMatchers`

WebFlux có cả annotation controllers và functional `RouterFunction`. HTTP authorization chạy ở WebFilter, có thể bảo vệ cả hai. Tuy nhiên, template variables từ `AuthorizationContext` phải khớp với **security matcher** đã chọn; không dựa vào tên biến của một controller hoặc RouterFunction khác nếu security matcher không trích xuất chúng. Nếu URI path matching trở nên phức tạp, kiểm thử trực tiếp `context.getVariables()` cùng các HTTP routes thực tế.

## 5. Ví dụ chính sách: tenant + document + method

Giả sử database có:

| Tenant | ID | Owner | State | Body |
| --- | ---: | --- | --- | --- |
| TENANT_A | 42 | alice | DRAFT | A private 42 |
| TENANT_B | 42 | bob | DRAFT | B private 42 |
| TENANT_A | 43 | bob | PUBLISHED | A public 43 |
| TENANT_B | 44 | bob | PUBLISHED | B public 44 |

**Server-side membership**:

- `alice` thuộc TENANT_A, có thể được cấp `DOC_READ` và `DOC_DELETE`.
- `bob` thuộc TENANT_B, có thể được cấp `DOC_READ` và `DOC_DELETE`.
- `reviewer` thuộc cả TENANT_A và TENANT_B, nhưng trong demo chỉ dùng `DOC_READ`.
- User lạ không có membership sẽ bị từ chối dù họ truyền đúng tenant trên URL.

**Business rule**:

```text
canRead(actor, tenant, document)
  = authenticated
    AND hasAuthority("DOC_READ")
    AND actor được phép dùng tenant
    AND document.tenant = tenant
    AND (document.state = PUBLISHED OR document.owner = actor.username)

canDelete(actor, tenant, document)
  = authenticated
    AND hasAuthority("DOC_DELETE")
    AND actor được phép dùng tenant
    AND document.tenant = tenant
    AND document.state = DRAFT
    AND document.owner = actor.username
```

Ở đây username dùng cho owner **chỉ để đơn giản hóa test**. Trong hệ thống nhiều identity provider, phải dùng ổn định `issuer + subject` hoặc internal user ID; cùng username ở hai tenant không được coi là một danh tính. Manager vẫn kiểm tra tenant của actor, tenant trên path và tenant của resource qua repository.

### 5.1. Ma trận cho phép/từ chối

| Request | Auth/authority | Kỳ vọng | Tại sao? |
| --- | --- | --- | --- |
| GET A/42 | alice + DOC_READ | 200, A private 42 | Owner và member A |
| GET B/42 | bob + DOC_READ | 200, B private 42 | Owner và member B |
| GET B/42 | alice + DOC_READ | 403 | Alice không thuộc B |
| GET A/42 | bob + DOC_READ | 403 | Bob không thuộc A |
| GET A/43 | reviewer + DOC_READ | 200 | PUBLISHED, member A |
| GET A/42 | reviewer + DOC_READ | 403 | DRAFT của Alice |
| GET A/42 | alice chỉ DOC_DELETE | 403 | Quyền DELETE không cấp READ |
| DELETE A/42 | alice + DOC_DELETE + CSRF | 204 | Owner, DRAFT |
| DELETE B/42 | bob + DOC_DELETE + CSRF | 204 | Owner, DRAFT |
| DELETE A/43 | alice + DOC_DELETE + CSRF | 403 | PUBLISHED và không phải owner |
| DELETE A/42 | reviewer chỉ DOC_READ + CSRF | 403 | Thiếu DELETE |
| DELETE A/42 | alice + DOC_DELETE, thiếu CSRF | 403 | CSRF filter chặn |
| GET A/999 | alice + DOC_READ | 403 | Không có document |
| GET A/not-a-number | alice + DOC_READ | 403 | Invalid path variable |
| GET A/42 | chưa xác thực | 401 | Cần authentication |
| GET /public/ping | chưa xác thực | 200 | Public route |
| POST A/42 | authenticated | 403 | Route không được cấu hình |

**Phân biệt:** 403 do custom manager và 403 do CSRF có nguồn khác nhau. Test phải có trường hợp DELETE **kèm** CSRF token để thật sự đi đến authorization manager.

## 6. Reactive pipeline: làm đúng thay vì chỉ “dùng Mono”

### 6.1. Trả publisher, không gọi subscribe thủ công

Manager nên trả về `Mono<AuthorizationDecision>`, để Spring Security quản lý subscription. Không tự gọi `.subscribe()` trong `check()`, vì quyết định sẽ thoát khỏi request pipeline và exception/context có thể bị xử lý sai.

```java
return authentication
    .flatMap(auth ->
        policy.canRead(auth, tenant, id)
            .map(AuthorizationDecision::new))
    .defaultIfEmpty(new AuthorizationDecision(false));
```

`policy.canRead(...)` là fragment reactive method do ứng dụng định nghĩa. Kết quả chỉ được tạo khi pipeline được subscription. Tránh side effect không kiểm soát ở thời điểm **assembly** và tránh blocking remote calls trên Netty event-loop.

### 6.2. Fail closed khi lookup lỗi

```java
return policy.isAllowed(user, tenant, id, action)
    .map(AuthorizationDecision::new)
    .onErrorReturn(new AuthorizationDecision(false))
    .defaultIfEmpty(new AuthorizationDecision(false));
```

Mẫu này cố ý biến lỗi policy backend thành deny. Production có thể muốn phân biệt `AccessDenied` với `ServiceUnavailable` để trả 503 và alert, nhưng **không tự fallback ALLOW**. Theo dõi lỗi để sự cố PDP không bị che kín bởi hàng loạt 403 khó chẩn đoán.

Nếu policy trả `Mono.empty()` vì không có document, `defaultIfEmpty(false)` nên tạo explicit deny; tránh trộn nghĩa `empty = không có dữ liệu` với `empty = abstain` của framework.

### 6.3. Không lấy actor từ request headers

```java
// PHẢN VÍ DỤ: client kiểm soát được giá trị.
String actor = context.getExchange().getRequest()
    .getHeaders().getFirst("X-User");

// PHẢN VÍ DỤ: tenant client truyền không tự chứng minh membership.
String tenant = context.getExchange().getRequest()
    .getHeaders().getFirst("X-Tenant");
```

Manager phải lấy identity từ `Mono<Authentication>` mà security filter tạo sau xác thực, và membership từ directory/claims **đã xác minh**. Nếu actor có quyền chuyển tenant, server phải xác thực quyền membership trước khi dùng tenant được chọn trên path.

### 6.4. Không dùng servlet API

Các kiểu sau thuộc Servlet và không dùng cho `AuthorizationContext` reactive:

```java
// Sai ngữ cảnh WebFlux:
// HttpServletRequest
// RequestAuthorizationContext
// HttpSecurity.authorizeHttpRequests(...)
```

Dùng `ServerWebExchange`, `AuthorizationContext`, `ServerHttpSecurity.authorizeExchange(...)`. Nếu Spring Boot có cả `spring-boot-starter-web` và `spring-boot-starter-webflux` trong classpath, Boot thường ưu tiên MVC; cần kiểm tra `spring.main.web-application-type=reactive` và dependencies khi chạy test WebFlux.

## 7. Quan hệ HTTP security, reactive method security và RLS

### 7.1. HTTP WebFilter là lớp đầu tiên, không phải toàn bộ authorization

HTTP `ReactiveAuthorizationManager<AuthorizationContext>` chỉ kiểm tra những request đi qua WebFlux security chain. Một method nghiệp vụ có thể được gọi từ scheduled job, message consumer, reactive listener hoặc service khác **không đi qua HTTP security**. Với dữ liệu quan trọng, nên kiểm tra ở service hoặc repository nữa.

Nếu bật method security reactive:

```java
@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodSecurityConfig {
    // Các phương thức Mono/Flux có thể dùng @PreAuthorize.
}
```

Đây là fragment cấu hình, không bắt buộc trong demo HTTP ở mục 8. `@EnableReactiveMethodSecurity` dành cho **reactive method security** và dùng Reactor Context. Không đánh đồng nó với `@EnableMethodSecurity` của Servlet/immediate-method proxy.

### 7.2. AuthorizationContext là HTTP context, không phải domain ACL

`AuthorizationContext` nắm exchange và path variables, không tự chứa các ACE, owner hay trạng thái tài liệu. Việc đọc document phải do reactive policy/data source thực hiện. Nếu policy phức tạp và dùng `Spring Security ACL` JDBC blocking, phải xem xét I/O và scheduler hoặc thiết kế lại data access, không chèn query JDBC blocking trực tiếp vào authorization manager.

### 7.3. TOCTOU

Một `DELETE` có thể được cho phép vì tại thời điểm kiểm tra, document là DRAFT của Alice. Trước khi câu DELETE thực thi, transaction khác có thể chuyển trạng thái thành APPROVED. Vì vậy, trong body/service **phải kiểm tra lại owner và state ở thời điểm xóa** bằng conditional update/delete hoặc optimistic locking, thay vì cho rằng preauthorization đã đóng băng dữ liệu.

Với database reactive, ví dụ tư duy SQL:

```sql
DELETE FROM documents
WHERE tenant_id = :tenant
  AND document_id = :id
  AND owner_id = :authenticatedSubject
  AND status = 'DRAFT';
```

Kiểm tra affected rows là 1 mới coi là xóa thành công. `@PreAuthorize` không tự thay thế transaction/locking. Bài demo in-memory thực hiện điều kiện owner/state trong `ConcurrentHashMap.computeIfPresent` nhằm nhấn mạnh nguyên tắc; nó **không mô phỏng transaction database**.

## 8. Project Java 17+ với WebTestClient và Spring Security thực

Project dưới đây dùng WebFlux HTTP Security thật, một store **in-memory non-blocking** để dễ tập trung vào manager và 22 JUnit tests. Nó không yêu cầu Docker/database; không phải service production sẵn sàng chạy trên nhiều node. Spring Boot test context tạo WebFlux routes và security chain; `WebTestClient` gắn vào ApplicationContext và áp dụng `springSecurity()` của `spring-security-test`.

### 8.1. File layout

```text
reactive-authz-context-demo/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/ReactiveAuthorizationContextTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'reactive-authz-context-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.0'
    )
    testImplementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Project đặt tất cả Java dưới `src/test/java`, nên chỉ cần `testImplementation`. Nếu đưa vào ứng dụng, chuyển WebFlux/Security starters sang `implementation`. Vì chỉ có WebFlux starter, demo không phụ thuộc Servlet `MockMvc`.

### 8.2. Một file Java test hoàn chỉnh

Tạo `src/test/java/demo/ReactiveAuthorizationContextTest.java`:

```java
package demo;

import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authorization.AuthorizationContext;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(
    classes = ReactiveAuthorizationContextTest.Config.class,
    webEnvironment = SpringBootTest.WebEnvironment.MOCK,
    properties = "spring.main.web-application-type=reactive"
)
public class ReactiveAuthorizationContextTest {

    public record Key(String tenant, long id) {}

    public record Document(
        String tenant, long id, String owner,
        String state, String body
    ) {}

    public record DocumentView(
        String tenant, long id, String body
    ) {}

    public static class TenantDirectory {
        private final Map<String, Set<String>> memberships = Map.of(
            "alice", Set.of("TENANT_A"),
            "bob", Set.of("TENANT_B"),
            "reviewer", Set.of("TENANT_A", "TENANT_B")
        );

        public boolean belongs(String actor, String tenant) {
            return memberships.getOrDefault(actor, Set.of())
                .contains(tenant);
        }
    }

    public static class ReactiveDocumentStore {
        private final Map<Key, Document> rows =
            new ConcurrentHashMap<>();
        private final AtomicInteger lookups = new AtomicInteger();
        private final AtomicBoolean available =
            new AtomicBoolean(true);

        public void reset() {
            rows.clear();
            rows.put(new Key("TENANT_A", 42L),
                new Document("TENANT_A", 42L,
                    "alice", "DRAFT", "A private 42"));
            rows.put(new Key("TENANT_B", 42L),
                new Document("TENANT_B", 42L,
                    "bob", "DRAFT", "B private 42"));
            rows.put(new Key("TENANT_A", 43L),
                new Document("TENANT_A", 43L,
                    "bob", "PUBLISHED", "A public 43"));
            rows.put(new Key("TENANT_B", 44L),
                new Document("TENANT_B", 44L,
                    "bob", "PUBLISHED", "B public 44"));
            lookups.set(0);
            available.set(true);
        }

        public Mono<Document> find(String tenant, long id) {
            return Mono.defer(() -> {
                lookups.incrementAndGet();
                if (!available.get()) {
                    return Mono.error(new IllegalStateException(
                        "Simulated policy source outage"));
                }
                return Mono.justOrEmpty(
                    rows.get(new Key(tenant, id)));
            });
        }

        // Domain re-check: không tin một precheck đã qua.
        public Mono<Boolean> deleteDraftOwnedBy(
                String tenant, long id, String actor) {
            return Mono.fromSupplier(() -> {
                Key key = new Key(tenant, id);
                AtomicBoolean deleted = new AtomicBoolean();
                rows.computeIfPresent(key, (k, doc) -> {
                    if ("DRAFT".equals(doc.state())
                            && actor.equals(doc.owner())) {
                        deleted.set(true);
                        return null;
                    }
                    return doc;
                });
                return deleted.get();
            });
        }

        public String rawBody(String tenant, long id) {
            Document d = rows.get(new Key(tenant, id));
            return d == null ? null : d.body();
        }

        public boolean exists(String tenant, long id) {
            return rows.containsKey(new Key(tenant, id));
        }

        public int lookups() {
            return lookups.get();
        }

        public void setAvailable(boolean state) {
            available.set(state);
        }
    }

    public static class DocumentPolicy {
        private final ReactiveDocumentStore store;

        public DocumentPolicy(ReactiveDocumentStore store) {
            this.store = store;
        }

        public Mono<Boolean> isAllowed(
                String actor, String tenant,
                long id, String action) {
            return store.find(tenant, id)
                .map(doc -> {
                    if ("READ".equals(action)) {
                        return "PUBLISHED".equals(doc.state())
                            || actor.equals(doc.owner());
                    }
                    if ("DELETE".equals(action)) {
                        return "DRAFT".equals(doc.state())
                            && actor.equals(doc.owner());
                    }
                    return false;
                })
                .defaultIfEmpty(false);
        }
    }

    public static class DocumentAuthorizationManager
            implements ReactiveAuthorizationManager<AuthorizationContext> {

        private final TenantDirectory directory;
        private final DocumentPolicy policy;
        private final AtomicInteger checks = new AtomicInteger();

        public DocumentAuthorizationManager(
                TenantDirectory directory, DocumentPolicy policy) {
            this.directory = directory;
            this.policy = policy;
        }

        @Override
        @SuppressWarnings("deprecation")
        public Mono<AuthorizationDecision> check(
                Mono<Authentication> authentication,
                AuthorizationContext context) {

            return Mono.defer(() -> {
                checks.incrementAndGet();

                Object rawTenant =
                    context.getVariables().get("tenantId");
                Object rawId =
                    context.getVariables().get("docId");

                if (!(rawTenant instanceof String tenant)
                        || tenant.isBlank()
                        || !(rawId instanceof String idText)) {
                    return Mono.just(new AuthorizationDecision(false));
                }

                final long id;
                try {
                    id = Long.parseLong(idText);
                    if (id <= 0L) {
                        return Mono.just(new AuthorizationDecision(false));
                    }
                } catch (NumberFormatException invalidId) {
                    return Mono.just(new AuthorizationDecision(false));
                }

                HttpMethod method =
                    context.getExchange().getRequest().getMethod();

                String action = HttpMethod.GET.equals(method)
                    ? "READ"
                    : HttpMethod.DELETE.equals(method)
                        ? "DELETE" : null;

                if (action == null) {
                    return Mono.just(new AuthorizationDecision(false));
                }

                String authority = "DOC_" + action;

                return authentication
                    .filter(auth -> auth.isAuthenticated()
                        && !(auth instanceof AnonymousAuthenticationToken))
                    .flatMap(auth -> {
                        boolean hasAuthority = auth.getAuthorities()
                            .stream()
                            .anyMatch(granted -> authority.equals(
                                granted.getAuthority()));

                        if (!hasAuthority
                                || !directory.belongs(
                                    auth.getName(), tenant)) {
                            return Mono.just(
                                new AuthorizationDecision(false));
                        }

                        return policy.isAllowed(
                                auth.getName(), tenant, id, action)
                            .map(AuthorizationDecision::new)
                            .defaultIfEmpty(
                                new AuthorizationDecision(false))
                            .onErrorReturn(
                                new AuthorizationDecision(false));
                    })
                    .defaultIfEmpty(new AuthorizationDecision(false));
            });
        }

        public int checks() {
            return checks.get();
        }

        public void reset() {
            checks.set(0);
        }
    }

    public static class Probe {
        private final AtomicInteger reads = new AtomicInteger();
        private final AtomicInteger deletes = new AtomicInteger();

        public void read() {
            reads.incrementAndGet();
        }

        public void delete() {
            deletes.incrementAndGet();
        }

        public int reads() {
            return reads.get();
        }

        public int deletes() {
            return deletes.get();
        }

        public void reset() {
            reads.set(0);
            deletes.set(0);
        }
    }

    @RestController
    @RequestMapping("/api/tenants/{tenantId}/documents")
    public static class DocumentController {
        private final ReactiveDocumentStore store;
        private final Probe probe;

        public DocumentController(
                ReactiveDocumentStore store, Probe probe) {
            this.store = store;
            this.probe = probe;
        }

        @GetMapping("/{docId}")
        public Mono<ResponseEntity<DocumentView>> get(
                @PathVariable("tenantId") String tenant,
                @PathVariable("docId") long id) {
            probe.read();

            return store.find(tenant, id)
                .map(doc -> ResponseEntity.ok(new DocumentView(
                    doc.tenant(), doc.id(), doc.body())))
                .defaultIfEmpty(
                    ResponseEntity.notFound().build());
        }

        @DeleteMapping("/{docId}")
        public Mono<ResponseEntity<Void>> delete(
                @PathVariable("tenantId") String tenant,
                @PathVariable("docId") long id) {
            probe.delete();

            return ReactiveSecurityContextHolder.getContext()
                .map(ctx -> ctx.getAuthentication().getName())
                .flatMap(actor ->
                    store.deleteDraftOwnedBy(tenant, id, actor))
                .map(deleted -> deleted
                    ? ResponseEntity.noContent().<Void>build()
                    : ResponseEntity.status(
                        HttpStatus.CONFLICT).<Void>build());
        }
    }

    @RestController
    public static class PublicController {
        @GetMapping("/public/ping")
        public Mono<String> ping() {
            return Mono.just("pong");
        }
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableWebFluxSecurity
    public static class Config {

        @Bean TenantDirectory tenantDirectory() {
            return new TenantDirectory();
        }

        @Bean ReactiveDocumentStore documentStore() {
            return new ReactiveDocumentStore();
        }

        @Bean DocumentPolicy documentPolicy(
                ReactiveDocumentStore store) {
            return new DocumentPolicy(store);
        }

        @Bean DocumentAuthorizationManager documentManager(
                TenantDirectory directory, DocumentPolicy policy) {
            return new DocumentAuthorizationManager(directory, policy);
        }

        @Bean Probe probe() {
            return new Probe();
        }

        @Bean DocumentController documentController(
                ReactiveDocumentStore store, Probe probe) {
            return new DocumentController(store, probe);
        }

        @Bean PublicController publicController() {
            return new PublicController();
        }

        @Bean MapReactiveUserDetailsService testUsers() {
            // Demo only. HTTP tests inject mockUser; không dùng
            // mật khẩu {noop} trong production.
            UserDetails user = User.withUsername("test-login")
                .password("{noop}test-only")
                .authorities("DOC_READ")
                .build();
            return new MapReactiveUserDetailsService(user);
        }

        @Bean SecurityWebFilterChain securityWebFilterChain(
                ServerHttpSecurity http,
                DocumentAuthorizationManager manager) {
            return http
                .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/public/ping").permitAll()
                    .pathMatchers(HttpMethod.GET,
                        "/api/tenants/{tenantId}/documents/{docId}")
                        .access(manager)
                    .pathMatchers(HttpMethod.DELETE,
                        "/api/tenants/{tenantId}/documents/{docId}")
                        .access(manager)
                    .anyExchange().denyAll()
                )
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                // CSRF giữ mặc định: DELETE phải kèm token.
                .build();
        }
    }

    @Autowired ApplicationContext applicationContext;
    @Autowired ReactiveDocumentStore store;
    @Autowired DocumentAuthorizationManager manager;
    @Autowired Probe probe;

    private WebTestClient web;

    @BeforeEach
    void setUp() {
        store.reset();
        manager.reset();
        probe.reset();

        web = WebTestClient
            .bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private WebTestClient actor(
            String username, String authority) {
        return web.mutateWith(
            mockUser(username).authorities(
                new SimpleGrantedAuthority(authority)));
    }

    @Test
    void publicPingWorksWithoutAuthentication() {
        web.get().uri("/public/ping").exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void anonymousDocumentReadIsUnauthorized() {
        web.get()
            .uri("/api/tenants/TENANT_A/documents/42")
            .exchange()
            .expectStatus().isUnauthorized();

        assertThat(probe.reads()).isZero();
    }

    @Test
    void aliceReadsHerTenantADraft() {
        actor("alice", "DOC_READ")
            .get().uri("/api/tenants/TENANT_A/documents/42")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.body").isEqualTo("A private 42")
            .jsonPath("$.tenant").isEqualTo("TENANT_A");

        assertThat(probe.reads()).isEqualTo(1);
    }

    @Test
    void bobReadsSameIdInTenantBWithoutSeeingA() {
        actor("bob", "DOC_READ")
            .get().uri("/api/tenants/TENANT_B/documents/42")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.body").isEqualTo("B private 42")
            .jsonPath("$.tenant").isEqualTo("TENANT_B");
    }

    @Test
    void aliceCannotReadTenantBLocalId42() {
        actor("alice", "DOC_READ")
            .get().uri("/api/tenants/TENANT_B/documents/42")
            .exchange()
            .expectStatus().isForbidden();

        assertThat(probe.reads()).isZero();
    }

    @Test
    void bobCannotReadTenantALocalId42() {
        actor("bob", "DOC_READ")
            .get().uri("/api/tenants/TENANT_A/documents/42")
            .exchange()
            .expectStatus().isForbidden();

        assertThat(probe.reads()).isZero();
    }

    @Test
    void reviewerReadsPublishedDocumentInTenantA() {
        actor("reviewer", "DOC_READ")
            .get().uri("/api/tenants/TENANT_A/documents/43")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.body").isEqualTo("A public 43");
    }

    @Test
    void reviewerReadsPublishedDocumentInTenantB() {
        actor("reviewer", "DOC_READ")
            .get().uri("/api/tenants/TENANT_B/documents/44")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.body").isEqualTo("B public 44");
    }

    @Test
    void reviewerCannotReadOtherPersonsDraft() {
        actor("reviewer", "DOC_READ")
            .get().uri("/api/tenants/TENANT_A/documents/42")
            .exchange()
            .expectStatus().isForbidden();

        assertThat(probe.reads()).isZero();
    }

    @Test
    void deleteAuthorityDoesNotImplyReadAuthority() {
        actor("alice", "DOC_DELETE")
            .get().uri("/api/tenants/TENANT_A/documents/42")
            .exchange()
            .expectStatus().isForbidden();

        assertThat(probe.reads()).isZero();
    }

    @Test
    void genericRoleDoesNotImplyDocRead() {
        actor("alice", "ROLE_ADMIN")
            .get().uri("/api/tenants/TENANT_A/documents/42")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void unknownUsernameIsNotMemberOfPathTenant() {
        actor("unknown", "DOC_READ")
            .get().uri("/api/tenants/TENANT_A/documents/43")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void missingDocumentIsDeniedBeforeHandler() {
        actor("alice", "DOC_READ")
            .get().uri("/api/tenants/TENANT_A/documents/999")
            .exchange()
            .expectStatus().isForbidden();

        assertThat(probe.reads()).isZero();
    }

    @Test
    void malformedDocIdIsDeniedInAuthorizationManager() {
        actor("alice", "DOC_READ")
            .get().uri("/api/tenants/TENANT_A/documents/not-a-number")
            .exchange()
            .expectStatus().isForbidden();

        assertThat(probe.reads()).isZero();
    }

    @Test
    void overflowingDocIdIsDeniedInAuthorizationManager() {
        actor("alice", "DOC_READ")
            .get().uri(
                "/api/tenants/TENANT_A/documents/999999999999999999999")
            .exchange()
            .expectStatus().isForbidden();

        assertThat(probe.reads()).isZero();
    }

    @Test
    void aliceCanDeleteHerOwnDraftWithCsrf() {
        actor("alice", "DOC_DELETE")
            .mutateWith(csrf())
            .delete().uri("/api/tenants/TENANT_A/documents/42")
            .exchange()
            .expectStatus().isNoContent();

        assertThat(store.exists("TENANT_A", 42L)).isFalse();
        assertThat(store.rawBody("TENANT_B", 42L))
            .isEqualTo("B private 42");
        assertThat(probe.deletes()).isEqualTo(1);
    }

    @Test
    void bobCanDeleteHisOwnDraftWithoutDeletingTenantA() {
        actor("bob", "DOC_DELETE")
            .mutateWith(csrf())
            .delete().uri("/api/tenants/TENANT_B/documents/42")
            .exchange()
            .expectStatus().isNoContent();

        assertThat(store.exists("TENANT_B", 42L)).isFalse();
        assertThat(store.rawBody("TENANT_A", 42L))
            .isEqualTo("A private 42");
    }

    @Test
    void aliceCannotDeletePublishedDocument() {
        actor("alice", "DOC_DELETE")
            .mutateWith(csrf())
            .delete().uri("/api/tenants/TENANT_A/documents/43")
            .exchange()
            .expectStatus().isForbidden();

        assertThat(probe.deletes()).isZero();
        assertThat(store.exists("TENANT_A", 43L)).isTrue();
    }

    @Test
    void readAuthorityDoesNotImplyDelete() {
        actor("reviewer", "DOC_READ")
            .mutateWith(csrf())
            .delete().uri("/api/tenants/TENANT_A/documents/42")
            .exchange()
            .expectStatus().isForbidden();

        assertThat(probe.deletes()).isZero();
        assertThat(store.exists("TENANT_A", 42L)).isTrue();
    }

    @Test
    void missingCsrfTokenBlocksEvenAuthorizedDelete() {
        actor("alice", "DOC_DELETE")
            .delete().uri("/api/tenants/TENANT_A/documents/42")
            .exchange()
            .expectStatus().isForbidden();

        assertThat(probe.deletes()).isZero();
        assertThat(store.exists("TENANT_A", 42L)).isTrue();
    }

    @Test
    void policySourceErrorFailsClosed() {
        store.setAvailable(false);

        actor("alice", "DOC_READ")
            .get().uri("/api/tenants/TENANT_A/documents/42")
            .exchange()
            .expectStatus().isForbidden();

        assertThat(probe.reads()).isZero();
    }

    @Test
    void unknownRouteIsDeniedByAnyExchange() {
        actor("alice", "DOC_READ")
            .get().uri("/internal/debug")
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

### 8.3. Vì sao example này test đúng HTTP manager?

**`DocumentAuthorizationManager`** được đăng ký trong `SecurityWebFilterChain` bằng `.access(manager)` với hai HTTP method. Nó nhận một `Mono<Authentication>` từ framework, lấy `tenantId` và `docId` từ `AuthorizationContext.getVariables()`, kiểm tra method từ `getExchange()`, sau đó gọi `DocumentPolicy.isAllowed(...)` trả `Mono<Boolean>` và `map` sang `AuthorizationDecision`.

**`WebTestClient` gắn ApplicationContext** bằng `bindToApplicationContext(...).apply(springSecurity())`, nên `mockUser(...)` và `csrf()` tham gia đúng reactive security filter chain mà không cần khởi động HTTP server thật. Đây là kiểm thử HTTP ở mức context-bound, **khác** một unit test chỉ gọi trực tiếp `manager.check(...)`.

**`Probe`** chỉ tăng counter trong handler/controller. Khi 403 do manager hoặc CSRF, counter không tăng; nhờ vậy test negative không chỉ kiểm tra status code mà còn chứng minh protected method body chưa chạy.

**`ReactiveDocumentStore`** dùng `ConcurrentHashMap` để minh họa non-blocking source qua `Mono.defer`. Nó không có DB hoặc network I/O, vì vậy không thay thế test R2DBC/database production. `deleteDraftOwnedBy` vẫn kiểm tra owner/state tại điểm mutation để minh họa chống TOCTOU, nhưng không có transaction phân tán.

**`TenantDirectory`** chứa membership phía server trong ví dụ. Production cần xác thực issuer/subject, role/tenant scope, token revocation và tenant switching. Không cho user tự quyết định membership chỉ bằng URL hoặc HTTP header.

### 8.4. Chạy và kết quả kỳ vọng

Ở thư mục `reactive-authz-context-demo`:

```bash
gradle test --tests demo.ReactiveAuthorizationContextTest
```

Nếu project đã có Gradle Wrapper, dùng `./gradlew test --tests demo.ReactiveAuthorizationContextTest` trên Linux/macOS hoặc `gradlew.bat test --tests demo.ReactiveAuthorizationContextTest` trên Windows.

**Kỳ vọng:** có **22 test JUnit** đạt và Gradle kết thúc `BUILD SUCCESSFUL`, nếu môi trường Java/Gradle/dependency phù hợp. Đây là **kết quả dự kiến**, không phải log một lần chạy thực tế. Báo cáo HTML: `build/reports/tests/test/index.html`.

| Cụm test | Điều cần xác nhận |
| --- | --- |
| Public, anonymous | Route `permitAll` chạy; protected route yêu cầu authentication |
| Alice/Bob cùng local ID 42 | Trả đúng body của tenant tương ứng |
| Cross-tenant | `AuthorizationContext` path variables + membership chặn truy cập |
| Reviewer | Được xem PUBLISHED trong tenant hợp lệ, không xem DRAFT của người khác |
| Function-level permissions | `DOC_DELETE` không trở thành `DOC_READ`; generic role không tự cấp tài liệu |
| Missing/malformed IDs | Deny rõ ràng và không vào controller |
| DELETE có CSRF | Xóa đúng DRAFT/owner, tenant còn lại không bị ảnh hưởng |
| DELETE không CSRF | 403 do CSRF, dù custom manager có thể cho phép |
| Policy source outage | Không fallback ALLOW |
| Unmatched URL | `anyExchange().denyAll()` có hiệu lực |
| Probe | Request bị deny không gọi method body |

### 8.5. Khi test không đạt: kiểm tra theo thứ tự

1. **401 thay vì 403:** đã inject `mockUser` vào WebTestClient bảo vệ Spring Security chưa? Authentication entry point có hoạt động không?
2. **DELETE đều 403:** có gửi `csrf()` trong test DELETE được phép chưa? Nếu không, CSRF có thể chặn trước khi đánh manager.
3. **403 ở cả GET hợp lệ:** kiểm tra `getVariables()` nhận `tenantId`/`docId` theo đúng tên template. Nếu map trống, kiểm tra security matcher và version.
4. **404 thay vì 200:** xác minh controller `@Bean` được đăng ký, `@RestController` và mapping đúng đường dẫn.
5. **Deny nhưng handler vẫn chạy:** có gọi test qua WebTestClient/WebFilterChain thật hay chỉ tạo controller bằng `new` không?
6. **Method Security không chạy:** đây là HTTP security demo; để bật method annotation riêng cần `@EnableReactiveMethodSecurity` và service Publisher.
7. **Hành vi khác khi thêm MVC starter:** Boot có thể khởi tạo Servlet app; kiểm tra loại web application và classpath.
8. **Blocking lỗi:** tìm `.block()`, JDBC/JPA blocking trong manager; dùng reactive data source hoặc chuyển I/O sang bounded scheduler nếu không thể thay thế ngay.

## 9. Áp dụng với service và dữ liệu production

### 9.1. Tham số URI không thay thế kiểm tra object

Manager được gọi vì path matcher phù hợp, nhưng `AuthorizationContext` không tự chứng minh ID thuộc tenant. **Tải object bằng tenant + ID từ data source**:

```java
// Fragment reactive repository do ứng dụng cung cấp:
Mono<Document> findByTenantAndId(String tenant, long id);

// Fragment policy:
return repository.findByTenantAndId(tenant, id)
    .map(doc -> documentOwnerPolicyAllows(actor, doc, action))
    .defaultIfEmpty(false);
```

Không viết `repository.findById(id)` rồi giả định URL tenant đủ an toàn. Với JPA/JDBC blocking, không chạy trực tiếp trên Netty event-loop. Với R2DBC, áp dụng `DatabaseClient`/reactive repository và transaction phù hợp.

### 9.2. Domain authorization phải bao trùm cả đường không-HTTP

Một message consumer hoặc scheduler không qua `SecurityWebFilterChain`. Nếu dữ liệu là nhạy cảm, nên đặt rule quan trọng ở **service/repository** cùng với HTTP manager; tránh chỉ một lớp HTTP bị bypass bởi internal call. Đừng giả định HTTP manager dùng cho reactive method security; hai cơ chế có context/target khác nhau.

### 9.3. Cache quyết định và latency

Nếu policy truy vấn DB/PDP mỗi request, có thể cân nhắc cache `ALLOW`/`DENY` ngắn hạn theo **tenant + actor identity + action + resource + policy revision**. Cần invalidation khi ACL/role/tenant/resource đổi, theo dõi stale grants và không cache một quyết định READ để dùng cho DELETE. Với các mutation nhạy cảm, preauthorization cache chỉ là lớp hỗ trợ; recheck ở transaction vẫn cần thiết.

### 9.4. Nhiều nguồn identity

`Authentication.getName()` không chắc là unique toàn hệ thống. Hai người ở tenant A/B có thể cùng username hoặc đến từ IdP khác nhau. Sử dụng stable `issuer + subject` hoặc user ID nội bộ và xác minh tenant membership, không tin user-supplied headers. Demo dùng username cho owner chỉ để code nhỏ; cần đổi trước khi đưa vào multi-tenant production.

### 9.5. Trường hợp nhiều authentication mechanisms

Nếu ứng dụng dùng OAuth2 Resource Server JWT, HTTP Basic, session, mTLS hoặc một gateway đã xác thực, **đừng** tự coi header `X-User` là Authentication. Cấu hình đúng authentication filter và entry point tương ứng. Có thể dùng `ReactiveAuthenticationManager` hoặc JWT converter để đưa authorities vào `Authentication`; manager chỉ quyết định sau khi authentication đã được xác thực.

### 9.6. Tương tác với WebSockets, SSE và streaming

HTTP authorization kiểm tra handshake/request, nhưng với long-lived stream hoặc WebSocket, quyền có thể bị thu hồi trong khi luồng đang phát dữ liệu. Nếu đó là dữ liệu nhạy cảm, cần chính sách recheck/termination phù hợp theo TTL/revocation SLA và loại protocol. Không hiểu một lần `ALLOW` khi mở stream là giấy phép vô hạn.

## 10. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách phát hiện/sửa |
| --- | --- | --- |
| Dùng `AuthorizationManager<RequestAuthorizationContext>` trong WebFlux | Nhầm Servlet API | Dùng `ReactiveAuthorizationManager<AuthorizationContext>` |
| Dùng `SecurityContextHolder.getContext()` trong reactive pipeline | Context sai khi đổi thread | Sử dụng `Mono<Authentication>` / `ReactiveSecurityContextHolder` |
| Gọi `block()` khi kiểm tra quyền | Chặn event-loop, giảm throughput | Return `Mono<AuthorizationDecision>` |
| Bỏ qua `getVariables()` và chỉ đọc body/query param | Không ràng buộc đúng resource | Test security path matcher với URI template |
| Đổi tenant trên URL để tự được truy cập | IDOR/cross-tenant access | Xác minh membership và resource tenant từ server |
| Có READ là được DELETE | Thiếu action separation | Test `GET` vs `DELETE` và authority khác nhau |
| `@PreAuthorize` của Servlet dùng cho WebFlux HTTP | Nhầm security layer | `authorizeExchange` bảo vệ HTTP; `@EnableReactiveMethodSecurity` bảo vệ method |
| `Mono.empty()` được coi là ALLOW | Semantics abstain không rõ | Explicit `AuthorizationDecision(false)` khi thiếu dữ liệu |
| Lỗi PDP rồi fallback `true` | Fail-open | `onErrorReturn(deny)` + alert |
| DELETE 403 rồi kết luận custom manager deny | Có thể do CSRF | Test DELETE kèm `csrf()` |
| Dùng `anyExchange().permitAll()` quá rộng | Mở route ngoài dự định | Đặt cụ thể trước, `denyAll` mặc định |
| Chỉ kiểm tra owner trước khi gọi DELETE | Race condition/TOCTOU | Conditional DELETE theo owner/state/version |
| Cache quyền bằng `id` đơn lẻ | Trùng ID giữa tenant/action | Key theo tenant, actor, action, resource, revision |
| Test manager bằng `new` nhưng không test filter chain | Bỏ sót integration | WebTestClient + springSecurity |
| Chính sách trả 403 nhưng endpoint nội bộ vẫn đọc data | HTTP manager không chạy với job | Bảo vệ cả service/repository |
| Dùng JdbcTemplate ngay trong `flatMap` | Blocking I/O trên reactive thread | R2DBC/reactive API hoặc scheduler được kiểm soát |

## 11. Checklist nghiệm thu

- [ ] Project WebFlux dùng đúng `ServerHttpSecurity.authorizeExchange(...)`, không lẫn Servlet `HttpSecurity`.
- [ ] `ReactiveAuthorizationManager<AuthorizationContext>` dùng `Mono<Authentication>`, không gọi `block()`/`subscribe()`.
- [ ] Lấy `getExchange()`/`getVariables()` đúng tên biến security matcher; kiểm tra malformed/missing ID.
- [ ] Auth anonymous, không có authority hoặc tenant membership sai được explicit deny.
- [ ] Quyền `READ/DELETE` tách biệt; record owner/state/tenant do policy source đáng tin kiểm tra.
- [ ] Query ở data layer vẫn có tenant/ID scope, không chỉ dựa vào path.
- [ ] HTTP routes được cấu hình đúng thứ tự; unknown path/method bị deny theo chính sách.
- [ ] Test WebTestClient dùng security support thật và phân biệt 401/403/200/204.
- [ ] Test CSRF đúng cho DELETE/POST trong cơ chế browser credentials.
- [ ] Có negative tests cho ID không tồn tại, malformed, tràn số, tenant sai, source outage, missing auth/authority.
- [ ] Có kiểm tra method body không chạy khi bị deny; side effect được conditional recheck.
- [ ] Không dùng username hiển thị làm owner identity toàn cục khi nhiều tenant/issuer.
- [ ] Với I/O blocking, không đặt trên event-loop; kiểm tra reactive transaction và error handling.
- [ ] Với version mới, xác minh `check` deprecated vs `authorize` signature và test migration.

## 12. Bài tập mở rộng

**Bài tập A — POST và CSRF:** Thêm `POST /api/tenants/{tenantId}/documents` với `DOC_CREATE`, cho server gán tenant/owner từ identity tin cậy. Viết test có/không có `csrf()` và kiểm tra không thể tạo trong tenant lạ.

**Bài tập B — nhiều authorities:** Cho reviewer quyền đọc tài liệu PUBLISHED trong hai tenant nhưng chỉ có `DOC_DELETE` đối với tài liệu do mình tạo; đừng coi `ROLE_REVIEWER` là quyền xóa mọi object.

**Bài tập C — policy dữ liệu:** Thay map bằng R2DBC repository có `tenant_id` và `doc_id`, test bằng Testcontainers PostgreSQL. Nếu dùng RLS, đảm bảo DB role không bypass và tenant context trong transaction.

**Bài tập D — invalid URI:** Thử `/documents/0`, `/documents/-1`, ID lớn hơn `Long.MAX_VALUE` và path chứa encoding đặc biệt. Phải không có 500/side effect vì parsing.

**Bài tập E — biến URI:** Thay security path matcher thành `/workspaces/{workspaceId}/documents/{docId}` nhưng không cập nhật manager. Quan sát missing `tenantId` dẫn đến deny; sửa contract hoặc manager.

**Bài tập F — kiểm thử direct manager:** Dùng `MockServerWebExchange`, `AuthorizationContext` với biến giả lập, `StepVerifier` và `Mono<Authentication>` để test branch authorization độc lập; sau đó giữ WebTestClient integration tests.

**Bài tập G — outage:** Cho reactive PDP trả `Mono.error`; đo 403/503 theo policy nhưng không được fallback allow, thêm metrics và trace ID.

**Bài tập H — tự duyệt/tự xóa:** Thêm policy `APPROVE` với quy tắc maker-checker; test method action + owner/state, và conditional write bảo vệ TOCTOU.

## 13. Kết luận

`ReactiveAuthorizationManager<AuthorizationContext>` là điểm mở rộng cho **HTTP authorization trong Spring Security WebFlux**. Nó kết hợp **Authentication reactive** với **ServerWebExchange và URI template variables**, cho phép kiểm tra authority, HTTP method, tenant, resource và policy nghiệp vụ mà không chặn Reactor event-loop.

Cấu trúc cốt lõi:

```java
// WebFlux HTTP:
.pathMatchers(HttpMethod.GET, "/api/tenants/{tenantId}/documents/{docId}")
    .access(documentAuthorizationManager)

// Manager Spring Security 6.5:
Mono<AuthorizationDecision> check(
    Mono<Authentication> authentication,
    AuthorizationContext context)
```

Quy tắc an toàn: **deny rõ ràng khi thiếu điều kiện**, phân biệt 401/403 với CSRF, không coi path tenant là identity tin cậy, tách HTTP gate khỏi transaction/domain authorization, kiểm thử cả thành công và từ chối qua `WebTestClient`. Nhớ kiểm tra Javadoc khi nâng cấp từ 6.5 lên 7.x vì `check(...)` đã deprecated trong 6.5.

## Tài liệu tham khảo chính thức

- Spring Security 6.5 — WebFlux HTTP Authorization: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html
- Spring Security 6.5 API — `ReactiveAuthorizationManager`, `check` và `authorize`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html
- Spring Security 6.5 API — `AuthorizationContext`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authorization/AuthorizationContext.html
- Spring Security 6.5 API — `ServerHttpSecurity.AuthorizeExchangeSpec.Access.access`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.AuthorizeExchangeSpec.Access.html
- Spring Security 6.5 — Reactive Method Security (khác HTTP manager): https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
- Spring Security 6.5 — Reactive WebTestClient authentication test: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html
- Spring Security 6.5 — Reactive testing CSRF: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html
- Spring Boot 3.5 — Testing Spring Boot Applications và WebTestClient: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
