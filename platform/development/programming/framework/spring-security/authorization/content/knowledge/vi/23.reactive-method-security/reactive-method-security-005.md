# Đưa danh tính vào Reactor Context và tránh phụ thuộc ThreadLocal trong Reactive Method Security

## 1. Bài toán: cùng một luồng xử lý, nhiều thread và nhiều người dùng

Trong Spring MVC/Servlet truyền thống, code thường lấy người dùng hiện tại như sau:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
String username = authentication.getName();
```

Cách đó quen thuộc vì mỗi request thường được xử lý trong một chuỗi gọi gắn với thread; `SecurityContextHolder` mặc định có chiến lược lưu ngữ cảnh bằng `ThreadLocal`. Nhưng Spring WebFlux và Reactor không đảm bảo toàn bộ một request chỉ chạy trên một thread. Một `Mono`/`Flux` có thể:

- được lắp ráp (*assembly*) trên thread A;
- bắt đầu thực thi khi một subscriber đăng ký (*subscribe*) trên thread B;
- gọi API I/O không đồng bộ rồi tiếp tục trên thread C;
- đổi scheduler qua `publishOn` hoặc `subscribeOn`;
- xử lý nhiều subscriptions khác nhau từ cùng một publisher.

Nếu một service reactive dùng `SecurityContextHolder.getContext()` trong callback, nó có thể gặp context **rỗng** hoặc context **không tương ứng với subscriber**, tùy pipeline và cấu hình context propagation. Rủi ro nghiêm trọng hơn phát sinh khi một ứng dụng tự viết `static ThreadLocal<String> CURRENT_USER`, quên `remove()` hoặc dùng thread pool; một request có thể vô tình nhận user/tenant của request khác.

Trong Reactive Method Security, cách chuẩn là dùng **Reactor `Context`** và **`ReactiveSecurityContextHolder`**. Đối tượng `Authentication` được truy cập từ context của **lượt subscription**, thay vì giả định identity gắn cố định với thread đang chạy.

Bài Knowledge thuộc nhóm **Method security Reactive** của module **Spring Security – authorization**. Trọng tâm là **đưa danh tính vào Reactor Context và tránh phụ thuộc ThreadLocal**: cách đặt/lấy identity, luồng truyền context, quan hệ với `@PreAuthorize`, kiểm thử và các rủi ro thực tế khi đi qua async boundaries.

Kết thúc bài, bạn sẽ biết:

1. Vì sao `ThreadLocal` không phải nguồn identity đáng tin trong reactive chain.
2. `Context`, `ContextView`, `contextWrite` và `deferContextual` hoạt động theo subscription và direction nào.
3. Cách lấy `SecurityContext` qua `ReactiveSecurityContextHolder.getContext()`.
4. Cách đặt identity trong **test hoặc boundary nội bộ tin cậy** bằng `withAuthentication`/`withSecurityContext`.
5. Cách WebFlux Security tự thiết lập Reactor security context sau khi xác thực request.
6. Cách dùng `@EnableReactiveMethodSecurity` và `@PreAuthorize` với `Mono`/`Flux`.
7. Cách bảo vệ tenant/owner/ACL bằng principal và dữ liệu authoritative.
8. Cách tránh mất context trong `publishOn`, `subscribeOn`, `@Async`, `CompletableFuture`, detached `subscribe()` và background jobs.
9. Cách viết project Java 17 + Spring Boot 3.5.8 chạy được, gồm CLI minh họa, `StepVerifier` và HTTP `WebTestClient`.
10. Cách kiểm thử **cùng một publisher dưới hai danh tính**, không lộ dữ liệu giữa tenants, không chạy nguồn khi bị từ chối.
11. Vì sao `Mono.cache()`, hot publishers, retry và thời điểm thu hồi quyền cần thiết kế riêng.
12. Cách phân biệt ngữ cảnh **identity** với một quyết định **authorization** đã có thể lỗi thời.

**Nguyên tắc:** Identity phải được tạo từ authentication đã xác minh và được mang theo **đúng subscription**, còn quyền trên dữ liệu phải tiếp tục được kiểm tra tại repository/service/transaction. Reactor Context **không** tự cấp quyền.

---

## 2. So sánh ThreadLocal và Reactor Context

| Tiêu chí | `ThreadLocal` | Reactor `Context` |
| --- | --- | --- |
| Gắn với | Một Java thread | Một subscriber/subscription và chuỗi operator |
| Truy cập | `threadLocal.get()` | `deferContextual`, `contextWrite` và API dựa Context |
| Qua `publishOn` / `subscribeOn` | Không được đảm bảo tự mang sang thread mới | Reactor Context tiếp tục theo reactive chain |
| Nhiều request chung thread | Có thể bị lẫn nếu quản lý sai | Context tách theo subscription |
| Quyền sở hữu/lifecycle | Set/remove đúng ở mọi path/thread | Được liên kết với subscriber, bất biến theo cập nhật |
| Lấy Spring Security auth | `SecurityContextHolder` (mặc định imperative) | `ReactiveSecurityContextHolder` |
| Khi nào phù hợp | Imperative Servlet hoặc adapter đã được thiết kế | WebFlux/Reactor reactive chain |
| Điều không giải quyết | Không kiểm tra tenant/ACL | Cũng không tự kiểm tra tenant/ACL |

### 2.1. Một callback trên thread pool không mang theo ThreadLocal gốc

Mảnh code minh họa vấn đề:

```java
ThreadLocal<String> current = new ThreadLocal<>();

current.set("alice");
CompletableFuture<String> result =
    CompletableFuture.supplyAsync(current::get);

// Không được dựa vào kết quả là "alice".
System.out.println(result.join());
current.remove();
```

Đoạn trên **chỉ để giải thích**, không nằm trong project runnable ở phần sau. Với `CompletableFuture.supplyAsync`, callback chạy trên executor khác; giá trị ThreadLocal thường không được copy sang đó. Một số công cụ propagation có thể thay đổi hành vi quan sát được, vì vậy không nên lấy output cụ thể của đoạn này làm contract bảo mật.

**Cũng không nên sửa bằng `InheritableThreadLocal`** cho mọi use case: thread pool tái sử dụng worker threads và thời điểm tạo thread không tương đương thời điểm bắt đầu request. Copy một principal từ thread cũ cũng không bảo đảm người đó còn quyền ở thời điểm dùng.

### 2.2. Trong Reactor, subscription mới là ranh giới quan trọng

```text
Publisher definition / assembly
            |
            | không phải identity cố định cho mọi subscriber
            v
       Mono / Flux
        /       \
       /         \
Subscribe A    Subscribe B
Context A      Context B
alice / T1     bob / T2
       \         /
        v       v
  Operators đọc Context
  theo từng subscription
```

Cùng một publisher **cold** có thể được subscribe bởi Alice và Bob với hai context khác nhau. Mỗi subscriber nhận kết quả dựa trên identity của chính mình nếu publisher được xây đúng: không capture user vào field singleton, không cache kết quả đã authorize dùng chung và không tạo side effect eager ngoài publisher.

### 2.3. Reactor Context không phải Java `Map` chia sẻ

`reactor.util.context.Context` là một cấu trúc key-value, bất biến theo hướng tạo bản mới mỗi lần đặt/ghi. Một operator nhận `ContextView` chỉ đọc được các giá trị có hiệu lực đối với subscription và nhánh pipeline đó.

Điều này **không** đồng nghĩa Context là kho bí mật hoặc security boundary bất khả giả mạo. Code chạy trong cùng ứng dụng có thể chủ động đặt Context; vì thế chỉ boundary **đáng tin cậy** được phép tạo `Authentication` từ identity đã xác minh. Không xây `Authentication` từ JSON, cookie tùy ý hoặc header tự khai rồi đặt bằng `withAuthentication`.

---

## 3. Những API Reactor cần biết

### 3.1. `contextWrite(...)`: đưa dữ liệu vào Context

Một ví dụ Reactor thuần không có Spring:

```java
Mono<String> greeting =
    Mono.deferContextual(ctx ->
        Mono.just("Hello " + ctx.getOrDefault(
            "requestUser", "anonymous"
        ))
    );

String result = greeting
    .contextWrite(ctx -> ctx.put("requestUser", "alice"))
    .block();

System.out.println(result);
```

Output trong CLI/test:

```text
Hello alice
```

Ở đây:

- `Mono.deferContextual(...)` chỉ chạy lambda khi có **subscription**, và cung cấp `ContextView`.
- `contextWrite(...)` tạo Context mới chứa `requestUser=alice`.
- `.block()` tạo subscription, dùng được cho CLI/test; trong WebFlux request pipeline, **không gọi `block()`** để chờ công việc reactive.

**`requestUser` là key minh họa nghiệp vụ, không phải key nội bộ Spring Security.** Đừng tự tạo một Context key `"username"` rồi nghĩ Spring Security tự nhận nó làm principal.

### 3.2. `contextWrite(ContextView)` và `contextWrite(Function)`

Hai dạng phổ biến:

```java
Mono<String> first = greeting.contextWrite(
    reactor.util.context.Context.of("requestUser", "alice")
);

Mono<String> second = greeting.contextWrite(
    ctx -> ctx.put("requestUser", "bob")
);
```

Cả hai đặt context cho những operators **ở upstream** tương ứng khi có subscribe. Dạng function nhận Context từ downstream và trả về Context mới; không nên xóa/sửa những key do framework đặt trừ khi đó là hành động cố ý và được kiểm soát.

### 3.3. Context truyền từ downstream ngược lên upstream

Về cú pháp, nhiều người viết:

```java
Mono<String> result = Mono.deferContextual(ctx ->
        Mono.just(ctx.get("tag"))
    )
    .contextWrite(ctx -> ctx.put("tag", "NEAR"))
    .contextWrite(ctx -> ctx.put("tag", "FAR"));
```

Khi subscribe, operator `contextWrite` ở cuối đặt `FAR`, sau đó operator nằm gần source đặt `NEAR`. `deferContextual` nhìn thấy giá trị gần nó nhất:

```text
NEAR
```

**Quy tắc nhớ:** `contextWrite` ảnh hưởng **upstream** trong chain, không tự khiến mọi code nằm *sau* nó trong source Java nhìn thấy giá trị.

Ví dụ không thấy context:

```java
Mono<String> result = Mono.just("value")
    .contextWrite(ctx -> ctx.put("tag", "INNER"))
    .flatMap(x -> Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("tag", "MISSING"))
    ));
```

`flatMap` đứng **downstream** của `contextWrite("INNER")`, nên context trong inner subscriber ở đây không tự nhận key từ operator nằm trước nó. Với cách viết minh họa, kết quả kỳ vọng là:

```text
MISSING
```

Đây là lý do vị trí `contextWrite` cần được **test trên publisher cuối cùng**, không đoán từ thứ tự nhìn thấy khi đọc code từ trên xuống dưới.

### 3.4. `deferContextual` dùng khi cần identity trong nguồn

Nếu một repository/service cần thông tin có sẵn trong Context ngay lúc subscriber bắt đầu:

```java
Mono<String> actorName = Mono.deferContextual(ctx ->
    Mono.just(ctx.getOrDefault("actorName", "anonymous"))
);
```

Tuy nhiên, với **Spring Security**, cách chuẩn để đọc identity là:

```java
ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName);
```

Không sao chép security identity qua một key tự nghĩ ra nếu không có yêu cầu tích hợp rõ ràng; hai nguồn identity sẽ dễ không nhất quán.

---

## 4. Spring Security đặt `Authentication` vào Reactor Context thế nào?

`ReactiveSecurityContextHolder` thuộc package:

```java
org.springframework.security.core.context
```

Các API cần nắm:

| API | Mục đích |
| --- | --- |
| `getContext()` | Trả `Mono<SecurityContext>` từ Reactor Context hiện tại |
| `withAuthentication(Authentication)` | Tạo Reactor Context có `SecurityContext` chứa Authentication |
| `withSecurityContext(Mono<? extends SecurityContext>)` | Đưa một `Mono<SecurityContext>` vào Context |
| `clearContext()` | Function dùng với `contextWrite` để xóa security context khỏi Context |

### 4.1. Lấy user hiện tại

```java
Mono<String> username =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
```

Cách này đọc identity theo **subscriber**, không yêu cầu thread đang chạy có `SecurityContextHolder` imperative.

Khi không có context, `getContext()` có thể hoàn thành rỗng. Đối với endpoint bảo mật, đừng dùng một default như `"admin"` hay tenant `"public"` để tiếp tục truy vấn; hãy **fail closed**:

```java
Mono<Authentication> requiredAuthentication =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .switchIfEmpty(Mono.error(
            new AccessDeniedException("Authentication required")
        ));
```

Trong production phải xét thêm `authentication.isAuthenticated()` và phân biệt anonymous bằng `AuthenticationTrustResolver` hoặc Spring Security expression phù hợp. Có thể có anonymous token báo `isAuthenticated() == true`; kiểm tra boolean thô không đủ.

### 4.2. Đưa Authentication vào pipeline trong test/CLI

```java
Authentication alice = new UsernamePasswordAuthenticationToken(
    "alice",
    "demo-only",
    List.of(new SimpleGrantedAuthority("memo:read"))
);

Mono<String> example =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(alice)
        );

String answer = example.block();
System.out.println(answer);
```

Output dự kiến:

```text
alice
```

`withAuthentication(alice)` tạo một Reactor `Context` mang security context để upstream đọc được. Đây là **mô phỏng test/CLI**. Không tạo `UsernamePasswordAuthenticationToken` đặc quyền từ username/role do HTTP client gửi rồi coi là người dùng đã xác thực.

### 4.3. `withSecurityContext(Mono<SecurityContext>)`

Nếu ứng dụng có `Mono<SecurityContext>` đã được xây dựng từ một **trusted authentication boundary**, có thể dùng:

```java
Mono<SecurityContext> securityContext = Mono.fromSupplier(() -> {
    SecurityContext ctx = new SecurityContextImpl();
    ctx.setAuthentication(alice);
    return ctx;
});

Mono<String> pipeline = username.contextWrite(
    ReactiveSecurityContextHolder.withSecurityContext(
        securityContext
    )
);
```

Mảnh code cần import `SecurityContextImpl` và biến `alice` đã được định nghĩa. `Mono.fromSupplier` khiến việc tạo context lazy; giá trị authentication vẫn phải được xác minh từ nguồn đúng, không từ user input tùy ý.

**Không dùng một `SecurityContext` mutable toàn cục cho nhiều users.** Nếu ai đó thay `setAuthentication` trên object shared, các subscribers có thể bị ảnh hưởng. Dùng context mới theo request/actor.

### 4.4. `clearContext()` dùng có chủ đích

```java
Mono<String> anonymousRead = username
    .contextWrite(ReactiveSecurityContextHolder.clearContext())
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(alice)
    );
```

Operator `clearContext` nằm **gần source hơn** nên nó xóa security context của subscription ở phía upstream. `username` không nhận được identity từ `withAuthentication` phía ngoài.

Trong một phép thử nhạy cảm, đừng để `switchIfEmpty(Mono.just("admin"))` biến mất context thành đặc quyền. Mặc định của authorization phải là từ chối.

### 4.5. Spring WebFlux tự làm gì?

Khi HTTP request đi qua Spring Security WebFlux:

1. Security WebFilters áp authentication từ HTTP Basic, session, JWT/Bearer hoặc một cơ chế được cấu hình.
2. Với request đã xác thực, `ReactorContextWebFilter` hỗ trợ đặt `SecurityContext` vào Reactor Context theo security context repository và pipeline.
3. Controller/Service reactive dùng `ReactiveSecurityContextHolder.getContext()` để lấy identity theo request subscription.
4. `@PreAuthorize` từ **Reactive Method Security** có thể dùng identity của Reactor Context để quyết định quyền.

**Không cần tự gọi `withAuthentication` ở mọi controller** khi request đã đi qua Spring Security đúng cách. Nếu tự tạo authentication bên trong controller từ request body, bạn có thể vô tình bypass toàn bộ provider authentication.

---

## 5. `@PreAuthorize` và Reactive Method Security

### 5.1. Bật đúng cấu hình

```java
@Configuration
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class MethodSecurityConfig {
}
```

Với Spring Security 6.5, `@EnableReactiveMethodSecurity(useAuthorizationManager=true)` là lựa chọn dùng cơ chế reactive AuthorizationManager. Một method được bảo vệ điển hình:

```java
@PreAuthorize("hasAuthority('memo:read')")
public Flux<MemoView> list() {
    return actorResolver.require()
        .flatMapMany(actor ->
            repository.findByTenantId(actor.tenantId())
        );
}
```

Mảnh code trên cần `MemoView`, `ActorResolver`, repository. Ví dụ project đầy đủ ở mục 8.

**Không nhầm** `@EnableWebFluxSecurity` với `@EnableReactiveMethodSecurity`: cái đầu bảo vệ HTTP WebFilter chain, cái sau bật authorization cho lời gọi Spring-managed methods qua proxy.

### 5.2. Publisher từ method không phải một quyết định đã thực thi

```java
Flux<MemoView> pending = memoService.list();
```

Việc có biến `pending` chưa chứng minh người gọi được đọc dữ liệu. Reactive method-security interceptor phối hợp với publisher/subscription. Khi `pending` được subscribe, nó sử dụng Reactor Context của lượt đó để đánh giá `@PreAuthorize`.

Test đúng phải subscribe:

```java
StepVerifier.create(
    pending.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(alice)
    )
).expectNextCount(2).verifyComplete();
```

Nếu bạn chỉ gọi method rồi assert không có Java exception, có thể bỏ sót lỗi authorization vốn xuất hiện dưới dạng **reactive onError signal**.

### 5.3. Cùng publisher, hai subscribers

```text
memoService.list() -> Flux<MemoView> secured
    |
    +-- subscribe Alice / memo:read / T1
    |      -> @PreAuthorize allow
    |      -> ActorResolver thấy Alice/T1
    |      -> chỉ query tenant T1
    |
    +-- subscribe Bob / memo:read / T2
           -> @PreAuthorize allow
           -> ActorResolver thấy Bob/T2
           -> chỉ query tenant T2
```

Nếu dùng đúng reactive Context, publisher cold không “nhớ” Alice chỉ vì Alice subscribe trước. Với policy thực, mỗi lần subscription có thể đánh giá quyền mới. Dữ liệu từ repository cũng phải được **tenant-scoped theo actor được xác minh trong subscription**.

### 5.4. Không phụ thuộc vào caller-supplied principal

Cách nguy hiểm:

```java
// SAI về thiết kế: client tự chọn username và tenant.
@GetMapping("/api/memos")
Flux<MemoView> all(
        @RequestHeader("X-User") String username,
        @RequestHeader("X-Tenant") String tenant) {
    return repository.findByTenantId(tenant);
}
```

Dù URL đã yêu cầu `.authenticated()`, code trên vẫn tin tenant chưa được xác minh. Phải suy tenant từ stable `issuer + subject`/membership server hoặc verify lựa chọn active tenant. Chính sách chức năng `memo:read` và tenant isolation là **hai ràng buộc độc lập**.

### 5.5. Đừng dùng `SecurityContextHolder` trong callback reactive

```java
// SAI trong reactive pipeline nếu giả định ThreadLocal luôn đúng.
return Mono.fromSupplier(() ->
    SecurityContextHolder.getContext()
        .getAuthentication().getName()
);
```

Nó có thể chạy trên thread không có context imperative, hoặc context đã được propagation bridge theo cách khác. Cách khuyến nghị:

```java
return ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName());
```

Tuy một số Reactor/Micrometer context-propagation bridges có thể khôi phục một số ThreadLocal trong operator callbacks, đó **không phải** lý do thiết kế Reactive Method Security dựa vào ThreadLocal ngầm định. Nếu cần tích hợp thư viện imperative, dùng adapter được kiểm chứng và không cho phép silent fallback.

---

## 6. `publishOn`, `subscribeOn`, `flatMap` và vòng đời ngữ cảnh

### 6.1. Reactor Context vẫn đi theo reactive chain khi đổi scheduler

```java
Mono<String> result =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .publishOn(Schedulers.parallel())
        .map(name -> "Hello " + name)
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(alice)
        );
```

Đây là mảnh code (cần import `Schedulers` và biến `alice`). Dù có `publishOn`, dữ liệu identity đến từ Context của subscription. Trong CLI/test output dự kiến `"Hello alice"`.

`subscribeOn` điều khiển nơi subscription/source được bắt đầu; `publishOn` ảnh hưởng nơi các tín hiệu downstream được xử lý. **Cả hai không tự biến ThreadLocal thường thành context an toàn**.

### 6.2. `flatMap` và inner publishers

Một pipeline:

```java
return actorResolver.require()
    .flatMap(actor -> remotePolicyClient.check(actor))
    .flatMap(result -> repository.findAllowed(result));
```

Đây là mảnh code minh họa. `flatMap` sẽ subscribe inner publisher theo contract của Reactor và truyền subscriber context theo đúng cấu trúc chain. Nếu bạn **tự tách** `remotePolicyClient.check(actor).subscribe()` bên trong lambda, bạn tạo một subscription phụ khó quản lý, dễ mất completion/error/identity của HTTP request.

Nên compose/return publisher của tác vụ con. Nếu cần truyền identity tường minh sang remote service, dùng **stable verified user ID + tenant scope** theo hợp đồng, không tự serialize toàn bộ `SecurityContext` hay token bí mật vào message.

### 6.3. Vì sao Context không phải biến toàn cục?

```text
HTTP request A -> Reactor Context A -> alice / T1
HTTP request B -> Reactor Context B -> bob / T2

Có thể:
  A và B chạy cùng event loop worker ở các thời điểm khác nhau.
  A có operator chuyển sang parallel scheduler.
  B tạo inner publishers riêng.

Không được có:
  static CURRENT_USER = "alice"
  ThreadLocal giữ tenant T1 rồi vô tình dùng ở request B.
```

Context gắn với subscriber giúp tách danh tính trong các luồng đó, với điều kiện không capture user vào singleton field hoặc dùng cache dữ liệu đã authorize chung cho mọi user.

### 6.4. Mất context khi rời khỏi Reactor

Ranh giới dễ sai:

- `CompletableFuture.supplyAsync(...)` được tạo ngoài reactive chain.
- `new Thread(...)`, `ExecutorService.submit(...)` tự quản lý.
- `@Async` imperative method.
- `queue.publish(...)` rồi job chạy nhiều giờ sau.
- Fire-and-forget `.subscribe()` không gắn lifecycle với request.
- Callback từ SDK bên ngoài tự chạy trên thread do SDK sở hữu.

Reactor Context **không tự chứng minh** identity đã được chuyển an toàn qua các boundary đó. Khi chuyển sang queue/background job, nên đưa vào message những facts tối thiểu, xác minh integrity/source, và **re-authorize khi job thực thi** theo SLA về quyền thu hồi.

---

## 7. Định nghĩa security contract cho ví dụ

Ta xây một dịch vụ memos đa tenant với dữ liệu in-memory để tập trung vào danh tính và Context.

| Memo ID | Tenant | Title |
| ---: | --- | --- |
| 11 | T1 | Alpha |
| 12 | T1 | Beta |
| 21 | T2 | Gamma |

Identity demo:

| Username | Tenant từ server directory | Authority |
| --- | --- | --- |
| alice | T1 | `memo:read` |
| bob | T2 | `memo:read` |
| mallory | T1 | `memo:other` |

Quy tắc:

```text
canListOrViewMemo(actor, memo) =
    validAuthenticated(actor)
    AND hasAuthority(actor, "memo:read")
    AND actor.tenant == memo.tenant
```

Một user có authority đọc nhưng thuộc T1 **không** đọc memo #21 của T2. Một user ở T1 nhưng thiếu `memo:read` cũng không được đọc memos T1. Code service phải dùng directory trên server, không nhận tenant từ HTTP header/body.

Ứng dụng đầy đủ sẽ có:

- HTTP GET `/public` không yêu cầu auth.
- GET `/api/me` yêu cầu người dùng đã đăng nhập, trả identity từ Reactor Context và directory.
- GET `/api/memos` yêu cầu `memo:read` qua **Reactive Method Security**, chỉ trả dữ liệu tenant hiện tại.
- GET `/api/memos/{id}` yêu cầu `memo:read`, ID tenant khác trả 404 theo scope.
- Lệnh CLI demo dùng `withAuthentication` để gắn hai identity vào cùng một `Mono`.
- `StepVerifier` và `WebTestClient` xác nhận chính sách thật qua Spring proxy/WebFilter.

**Giới hạn rõ ràng:** Directory và store in-memory chỉ là mô phỏng; không phải hệ thống đăng nhập production. Trong DB thật, tenant filtering phải được đặt trực tiếp trong SQL/R2DBC repository, ví dụ `WHERE tenant_id = :trustedTenant` hoặc `WHERE id=:id AND tenant_id=:trustedTenant`. Không fetch dữ liệu mọi tenant rồi lọc sau trong Java.

---

## 8. Dự án Java 17 + Spring Boot 3.5.8 hoàn chỉnh

### 8.1. Cây thư mục

```text
reactor-context-identity-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   └── java/demo/
    │       ├── IdentityApplication.java
    │       ├── ReactiveSecurityConfig.java
    │       ├── CurrentActor.java
    │       ├── Memo.java
    │       ├── MemoView.java
    │       ├── MemoStore.java
    │       ├── MemoService.java
    │       └── MemoController.java
    └── test/
        └── java/demo/
            ├── ReactorIdentityTest.java
            └── MemoHttpSecurityTest.java
```

Các class đều nằm trong package `demo`. Mục này là source project chạy dạng Gradle, không phải chỉ pseudo-code; các đoạn sau có thể đặt vào đúng file.

### 8.2. `settings.gradle`

```groovy
rootProject.name = 'reactor-context-identity-demo'
```

### 8.3. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

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
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot quản lý versions Spring Security, Reactor và Netty tương thích theo BOM. Không thêm `spring-boot-starter-web` (Servlet) vào project học WebFlux này, để không thay web application type theo quy tắc auto-config.

### 8.4. Identity application và CLI: `IdentityApplication.java`

```java
package demo;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class IdentityApplication {

    public static void main(String[] args) {
        SpringApplication.run(IdentityApplication.class, args);
    }

    @Bean
    @Profile("!test")
    CommandLineRunner demonstrate(
            MemoService memos,
            MemoStore store) {

        return args -> {
            Authentication alice = actor("alice", "memo:read");
            Authentication bob = actor("bob", "memo:read");

            // Cùng một Mono cold, được tạo trước khi có
            // Reactor Security Context của subscriber.
            Mono<String> identity = memos.whoAmI();

            System.out.println("READS_BEFORE: "
                + store.readSubscriptions());

            System.out.println("ALICE_IDENTITY: "
                + identity.contextWrite(
                    ReactiveSecurityContextHolder
                        .withAuthentication(alice)
                ).block());

            System.out.println("BOB_IDENTITY: "
                + identity.contextWrite(
                    ReactiveSecurityContextHolder
                        .withAuthentication(bob)
                ).block());

            System.out.println("ALICE_MEMO_IDS: "
                + memos.list().map(MemoView::id)
                    .collectList()
                    .contextWrite(
                        ReactiveSecurityContextHolder
                            .withAuthentication(alice)
                    ).block());

            System.out.println("BOB_MEMO_IDS: "
                + memos.list().map(MemoView::id)
                    .collectList()
                    .contextWrite(
                        ReactiveSecurityContextHolder
                            .withAuthentication(bob)
                    ).block());

            System.out.println("READS_AFTER: "
                + store.readSubscriptions());
        };
    }

    static Authentication actor(
            String username, String authority) {
        return new UsernamePasswordAuthenticationToken(
            username,
            "demo-only",
            List.of(new SimpleGrantedAuthority(authority))
        );
    }
}
```

**Chú ý:** `.block()` ở đây dùng trong `CommandLineRunner` trên thread chạy CLI demo, không phải trong WebFlux controller/event-loop. Nếu chuyển logic vào controller, hãy **return `Mono`/`Flux`**, đừng block.

`UsernamePasswordAuthenticationToken` được dựng thủ công **chỉ cho CLI/test**. Trong HTTP thật, credentials do Spring Security xác thực; client không được tự chọn principal hoặc authorities bằng JSON.

### 8.5. Reactive Web + Method Security: `ReactiveSecurityConfig.java`

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/**")
                    .authenticated()
                .anyExchange()
                    .denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
            .password("{noop}demo-pass")
            .authorities("memo:read")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password("{noop}demo-pass")
            .authorities("memo:read")
            .build();

        UserDetails mallory = User.withUsername("mallory")
            .password("{noop}demo-pass")
            .authorities("memo:other")
            .build();

        return new MapReactiveUserDetailsService(
            alice, bob, mallory
        );
    }
}
```

HTTP rule `/api/**` yêu cầu authentication, **không tự yêu cầu** `memo:read`. Quyền chức năng sẽ được kiểm tra ở `@PreAuthorize` trong service. Việc cố ý chia thành hai tầng cho phép test phát hiện khi Method Security bị thiếu: Mallory đăng nhập được nhưng vẫn phải nhận 403 khi gọi `/api/memos`.

Mật khẩu `"{noop}demo-pass"` chỉ dành cho học/test. Trong production dùng password hashing và identity provider/OIDC/OAuth2 phù hợp.

### 8.6. Actor resolver tin cậy: `CurrentActor.java`

```java
package demo;

import java.util.Map;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

record Actor(String username, String tenantId) {
}

@Component
public class CurrentActor {

    private final AuthenticationTrustResolver trustResolver =
        new AuthenticationTrustResolverImpl();

    private final Map<String, Actor> directory = Map.of(
        "alice", new Actor("alice", "T1"),
        "bob", new Actor("bob", "T2"),
        "mallory", new Actor("mallory", "T1")
    );

    public Mono<Actor> require() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(this::isTrusted)
            .flatMap(authentication ->
                Mono.justOrEmpty(
                    directory.get(authentication.getName())
                )
            )
            .switchIfEmpty(Mono.error(
                new AccessDeniedException(
                    "Authenticated tenant mapping required"
                )
            ));
    }

    private boolean isTrusted(Authentication authentication) {
        return authentication != null
            && authentication.isAuthenticated()
            && !trustResolver.isAnonymous(authentication);
    }
}
```

`CurrentActor.require()` trả `Mono<Actor>` để resolve **khi subscriber thực thi**, không ghi tên user vào singleton field. Khi thiếu Reactor Security Context, anonymous hoặc user không có mapping, method **fail closed** bằng `AccessDeniedException`.

Directory trên server là nguồn tenant đáng tin trong **demo**. Trong production, từ identity provider hãy ánh xạ stable `issuer + subject` tới membership và tenant hiện hành; nếu user có nhiều tenant, active tenant do request đề xuất phải được **kiểm tra membership** trước khi dùng. Tên user `getName()` không phải luôn unique toàn hệ thống, nên không dùng làm khóa bảo mật nếu hệ thống cho phép username trùng.

**Không trả raw `Authentication`, credentials hay token** ra HTTP response để “debug tenant”. Chỉ trả những trường identity đã được chấp thuận.

### 8.7. Model: `Memo.java`

```java
package demo;

public record Memo(
        Long id,
        String tenantId,
        String title) {
}
```

`Memo` đại diện hàng domain server-side, gồm `tenantId`. Trong ứng dụng thật, row này lấy từ R2DBC/DB; không tin `tenantId` do người dùng tự gửi.

### 8.8. DTO: `MemoView.java`

```java
package demo;

public record MemoView(Long id, String title) {

    public static MemoView from(Memo memo) {
        return new MemoView(
            memo.id(), memo.title()
        );
    }
}
```

`MemoView` chỉ chứa ID/title; không serialize toàn bộ tenant, owner, policy/ACL hay object graph nếu endpoint không cần.

### 8.9. Store lazy, tenant-scoped: `MemoStore.java`

```java
package demo;

import java.util.Comparator;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Repository;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Repository
public class MemoStore {

    private final List<Memo> rows = List.of(
        new Memo(11L, "T1", "Alpha"),
        new Memo(12L, "T1", "Beta"),
        new Memo(21L, "T2", "Gamma")
    );

    private final AtomicInteger reads = new AtomicInteger();

    public Flux<Memo> findAllInTenant(String trustedTenant) {
        return Flux.defer(() -> {
            reads.incrementAndGet();

            return Flux.fromIterable(rows)
                .filter(m -> m.tenantId().equals(trustedTenant))
                .sort(Comparator.comparing(Memo::id));
        });
    }

    public Mono<Memo> findInTenant(
            String trustedTenant, Long id) {

        return Flux.defer(() -> {
            reads.incrementAndGet();

            return Flux.fromIterable(rows)
                .filter(m ->
                    m.tenantId().equals(trustedTenant)
                    && m.id().equals(id)
                );
        }).next();
    }

    public int readSubscriptions() {
        return reads.get();
    }
}
```

Hai hàm truy cập dữ liệu nhận **trusted tenant** do service cung cấp. `Flux.defer` khiến bộ đếm chỉ tăng **khi subscription thực sự đến store**, giúp kiểm chứng lỗi deny không vô tình đọc dữ liệu rồi mới chặn ở tầng sau.

**Đừng copy cách filter in-memory sang production đa tenant.** Đối với DB thật, **tenant predicate phải nằm trong SQL/repository query** trước khi fetch, pagination, count hoặc JOIN. Demo dùng list nhỏ chỉ để mô tả identity flow.

### 8.10. Service với `@PreAuthorize`: `MemoService.java`

```java
package demo;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class MemoService {

    private final CurrentActor actors;
    private final MemoStore store;

    public MemoService(
            CurrentActor actors,
            MemoStore store) {
        this.actors = actors;
        this.store = store;
    }

    @PreAuthorize("isAuthenticated()")
    public Mono<String> whoAmI() {
        return actors.require().map(actor ->
            actor.username() + "@" + actor.tenantId()
        );
    }

    @PreAuthorize("hasAuthority('memo:read')")
    public Flux<MemoView> list() {
        return actors.require()
            .flatMapMany(actor ->
                store.findAllInTenant(actor.tenantId())
                    .map(MemoView::from)
            );
    }

    @PreAuthorize("hasAuthority('memo:read')")
    public Mono<MemoView> one(Long id) {
        return actors.require()
            .flatMap(actor ->
                store.findInTenant(actor.tenantId(), id)
            )
            .map(MemoView::from)
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.NOT_FOUND,
                    "Memo unavailable"
                )
            ));
    }
}
```

Luồng đọc danh sách:

```text
HTTP authentication
    |
    v
MemoController.list()
    |
    v
Spring proxy + reactive @PreAuthorize memo:read
    |
    v
MemoService.list() publisher
    |
    v
CurrentActor.require()
    |
    v
ReactiveSecurityContextHolder.getContext()
    |
    v
Trusted actor directory -> T1 hoặc T2
    |
    v
MemoStore.findAllInTenant(trustedTenant)
    |
    v
Flux<MemoView> chỉ chứa cùng tenant
```

`@PreAuthorize` không thay thế tenant scope. Trong method `one`, lookup luôn dùng `id + tenant`; nếu Alice đoán ID 21 của T2, service trả 404 để không tiết lộ thông tin của tenant khác.

**`isAuthenticated()` không giống authorization dữ liệu.** `whoAmI` cho phép mọi user đã đăng nhập có mapping; `list` và `one` cần thêm authority `memo:read` do Method Security xét.

### 8.11. WebFlux controller: `MemoController.java`

```java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class MemoController {

    private final MemoService service;

    public MemoController(MemoService service) {
        this.service = service;
    }

    @GetMapping("/public")
    public Mono<String> publicStatus() {
        return Mono.just("PUBLIC");
    }

    @GetMapping("/api/me")
    public Mono<String> me() {
        return service.whoAmI();
    }

    @GetMapping("/api/memos")
    public Flux<MemoView> list() {
        return service.list();
    }

    @GetMapping("/api/memos/{id}")
    public Mono<MemoView> one(
            @PathVariable Long id) {
        return service.one(id);
    }
}
```

Controller **return publishers**; nó không gọi `.block()`, `.subscribe()` hay xây Authentication từ request body. Framework WebFlux quản lý subscription và Reactor security context.

Nếu một controller cần truyền tenant/user đến nhiều service không thuộc cùng reactive chain, thay vì copy ThreadLocal, có thể resolve `Actor` một lần từ `CurrentActor.require()` và **truyền explicit `Actor`/trusted IDs** như input của application service. Nhưng không nhận một `Actor` tự khai từ HTTP client.

---

## 9. Lệnh chạy và stdout CLI dự kiến

Với Gradle Wrapper:

```bash
./gradlew bootRun
```

Trên PowerShell:

```powershell
.\gradlew.bat bootRun
```

Nếu không có Gradle Wrapper, cài Gradle tương thích hoặc tạo wrapper rồi chạy lại. Trong project này, Spring Boot startup logs vẫn hiện; các dòng **do `CommandLineRunner` tự in** được dự kiến như sau:

```text
READS_BEFORE: 0
ALICE_IDENTITY: alice@T1
BOB_IDENTITY: bob@T2
ALICE_MEMO_IDS: [11, 12]
BOB_MEMO_IDS: [21]
READS_AFTER: 2
```

**Phân tích chính xác:**

1. `MemoStore` mới khởi tạo, `reads = 0`.
2. `Mono<String> identity = memos.whoAmI()` chưa tạo query store và chưa có subscriber.
3. Lượt `.contextWrite(withAuthentication(alice)).block()` subscribe với Alice, `CurrentActor.require()` nhìn thấy Alice/T1.
4. Dùng **cùng `identity` publisher** để subscribe dưới Bob, nhận Bob/T2, không bị giữ lại tên Alice.
5. Lượt `memos.list()` thứ nhất subscribe dưới Alice, store chạy một lần và trả `[11, 12]`.
6. Lượt `memos.list()` thứ hai subscribe dưới Bob, store chạy lần hai và trả `[21]`.
7. `READS_AFTER = 2`, vì hai lần `whoAmI` không cần query memo store.

**Những dòng trên là kết quả kỳ vọng theo source code**, không phải tuyên bố đã biên dịch hoặc chạy thực tế trong môi trường soạn bài. `block()` chỉ được dùng trong CLI/test, không dùng trong reactive HTTP handlers.

### 9.1. Thử HTTP bằng Basic demo

```bash
curl -i http://localhost:8080/public
curl -i -u alice:demo-pass http://localhost:8080/api/me
curl -i -u alice:demo-pass http://localhost:8080/api/memos
curl -i -u bob:demo-pass http://localhost:8080/api/memos
```

Kỳ vọng:

- `/public` trả `PUBLIC` khi anonymous.
- Alice `/api/me` trả `alice@T1`, list chỉ có Alpha/Beta.
- Bob `/api/me` trả `bob@T2`, list chỉ có Gamma.
- User không xác thực gọi `/api/memos` phải bị chặn.
- Mallory đăng nhập thành công nhưng gọi `/api/memos` bị chặn bởi method authority.
- Alice gọi `/api/memos/21` không được đọc memo của Bob/T2.

Basic demo với `{noop}` chỉ dùng để học; khi triển khai thật cần secret management, TLS và credential verification thích hợp.

---

## 10. Integration test trực tiếp bằng `StepVerifier`

`StepVerifier` tạo **subscription thật** để kiểm chứng identity flow và authorization. Đây là công cụ đặc biệt quan trọng: một test chỉ gọi `service.list()` mà không subscribe **không chứng minh được** reactive policy đã được thực thi.

**`src/test/java/demo/ReactorIdentityTest.java`:**

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.test.context.ActiveProfiles;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

@SpringBootTest
@ActiveProfiles("test")
class ReactorIdentityTest {

    @Autowired
    MemoService memos;

    @Autowired
    MemoStore store;

    private static Authentication alice() {
        return IdentityApplication.actor(
            "alice", "memo:read");
    }

    private static Authentication bob() {
        return IdentityApplication.actor(
            "bob", "memo:read");
    }

    private static Authentication mallory() {
        return IdentityApplication.actor(
            "mallory", "memo:other");
    }

    private static <T> Mono<T> as(
            Mono<T> publisher, Authentication actor) {
        return publisher.contextWrite(
            ReactiveSecurityContextHolder
                .withAuthentication(actor)
        );
    }

    private static <T> Flux<T> as(
            Flux<T> publisher, Authentication actor) {
        return publisher.contextWrite(
            ReactiveSecurityContextHolder
                .withAuthentication(actor)
        );
    }

    @Test
    void sameMonoUsesDifferentSubscriberIdentities() {
        Mono<String> identity = memos.whoAmI();

        StepVerifier.create(as(identity, alice()))
            .expectNext("alice@T1")
            .verifyComplete();

        StepVerifier.create(as(identity, bob()))
            .expectNext("bob@T2")
            .verifyComplete();
    }

    @Test
    void sameColdFluxUsesTrustedTenantOfEachSubscriber() {
        Flux<MemoView> publisher = memos.list();

        int readsBefore = store.readSubscriptions();

        StepVerifier.create(as(publisher, alice()))
            .expectNext(
                new MemoView(11L, "Alpha"),
                new MemoView(12L, "Beta")
            )
            .verifyComplete();

        StepVerifier.create(as(publisher, bob()))
            .expectNext(
                new MemoView(21L, "Gamma")
            )
            .verifyComplete();

        assertEquals(
            readsBefore + 2,
            store.readSubscriptions()
        );
    }

    @Test
    void missingReadAuthorityDoesNotReachStore() {
        int before = store.readSubscriptions();

        StepVerifier.create(as(memos.list(), mallory()))
            .expectError(AccessDeniedException.class)
            .verify();

        assertEquals(before, store.readSubscriptions());
    }

    @Test
    void crossTenantLookupIsNotVisible() {
        StepVerifier.create(as(memos.one(21L), alice()))
            .expectError(
                org.springframework.web.server
                    .ResponseStatusException.class
            )
            .verify();

        StepVerifier.create(as(memos.one(21L), bob()))
            .expectNext(new MemoView(21L, "Gamma"))
            .verifyComplete();
    }

    @Test
    void identitySurvivesReactorSchedulerHop() {
        Mono<String> shifted = memos.whoAmI()
            .publishOn(Schedulers.parallel());

        StepVerifier.create(as(shifted, alice()))
            .expectNext("alice@T1")
            .verifyComplete();
    }

    @Test
    void missingReactorSecurityContextFailsClosed() {
        StepVerifier.create(memos.whoAmI())
            .expectError()
            .verify();
    }

    @Test
    void contextWriteClosestToSourceWins() {
        Mono<String> source = Mono.deferContextual(ctx ->
            Mono.just(ctx.get("tag"))
        );

        Mono<String> result = source
            .contextWrite(ctx -> ctx.put("tag", "NEAR"))
            .contextWrite(ctx -> ctx.put("tag", "FAR"));

        StepVerifier.create(result)
            .expectNext("NEAR")
            .verifyComplete();
    }
}
```

**Điểm kiểm chứng quan trọng:**

- `sameMonoUsesDifferentSubscriberIdentities` dùng **cùng một Mono**, hai contexts; không capture user ở assembly.
- `sameColdFluxUsesTrustedTenantOfEachSubscriber` dùng **cùng một Flux**, assert T1/T2 và nguồn store chạy lại khi subscribe.
- `missingReadAuthorityDoesNotReachStore` chứng minh denial không chỉ thay kết quả cuối bằng lỗi sau khi đã đọc dữ liệu.
- `crossTenantLookupIsNotVisible` khẳng định biết ID tenant khác không đủ để đọc object.
- `identitySurvivesReactorSchedulerHop` chứng minh code đọc Reactor Context không phụ thuộc thread-local request identity.
- `missingReactorSecurityContextFailsClosed` không chấp nhận thiếu identity như admin.
- `contextWriteClosestToSourceWins` làm rõ phạm vi/direction của Context.

**Lưu ý:** Test dựa vào Spring-managed beans, Method Security AOP và subscriber thật; không dùng `new MemoService(...)` rồi trông chờ annotation hoạt động. Các tests này không chỉnh state của store, nên test được thiết kế độc lập với thứ tự thực thi JUnit (counters chỉ kiểm tra độ tăng tương đối).

### 10.1. Vì sao không set `SecurityContextHolder` trực tiếp trong test?

Viết:

```java
SecurityContextHolder.getContext()
    .setAuthentication(alice);
```

không bảo đảm publisher được subscribe dưới **Reactive Security Context** mong muốn. Trong test trực tiếp của Reactor, dùng:

```java
publisher.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(alice)
);
```

Cách này kiểm chứng đúng API mà reactive method security sử dụng, thay vì phụ thuộc thread-local của thread chạy JUnit.

`@WithMockUser` vẫn có giá trị khi kết hợp Spring Security Test, nhất là WebFlux integration test, nhưng với bài có hai users subscribe **cùng một publisher**, `contextWrite` tường minh giúp phân biệt chính xác từng subscription.

---

## 11. HTTP integration tests bằng `WebTestClient`

Các test trước không đi qua WebFilter HTTP. Để chứng minh rằng **Spring Security thật sự đặt Authentication vào Reactor Context** sau khi xử lý HTTP request, ta dùng WebTestClient.

**`src/test/java/demo/MemoHttpSecurityTest.java`:**

```java
package demo;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@ActiveProfiles("test")
class MemoHttpSecurityTest {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void configure() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private WebTestClient alice() {
        return client.mutateWith(
            mockUser("alice").authorities(
                new SimpleGrantedAuthority("memo:read")
            )
        );
    }

    private WebTestClient bob() {
        return client.mutateWith(
            mockUser("bob").authorities(
                new SimpleGrantedAuthority("memo:read")
            )
        );
    }

    private WebTestClient mallory() {
        return client.mutateWith(
            mockUser("mallory").authorities(
                new SimpleGrantedAuthority("memo:other")
            )
        );
    }

    @Test
    void publicRouteDoesNotNeedAuthentication() {
        client.get().uri("/public").exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("PUBLIC");
    }

    @Test
    void meReadsSubscriberIdentityFromWebFluxContext() {
        alice().get().uri("/api/me").exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("alice@T1");

        bob().get().uri("/api/me").exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("bob@T2");
    }

    @Test
    void listIsTenantScopedEvenWithSameAuthority() {
        alice().get().uri("/api/memos").exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$[0].id").isEqualTo(11)
            .jsonPath("$[1].id").isEqualTo(12)
            .jsonPath("$[2]").doesNotExist();

        bob().get().uri("/api/memos").exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$[0].id").isEqualTo(21)
            .jsonPath("$[1]").doesNotExist();
    }

    @Test
    void authenticatedButMissingAuthorityIsForbidden() {
        mallory().get().uri("/api/memos").exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void knownOtherTenantIdDoesNotRevealMemo() {
        alice().get().uri("/api/memos/21").exchange()
            .expectStatus().isNotFound();

        bob().get().uri("/api/memos/21").exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo(21)
            .jsonPath("$.title").isEqualTo("Gamma");
    }

    @Test
    void anonymousCannotCallProtectedApi() {
        client.get().uri("/api/me").exchange()
            .expectStatus().isUnauthorized();
    }
}
```

`WebTestClient` gọi vào WebFlux application context có gắn `.apply(springSecurity())`; `mockUser(...)` cung cấp principal/authorities cho **request test**, sau đó Spring Security đưa context phù hợp vào reactive pipeline. Không cần tự set `SecurityContextHolder` hay thêm `X-User` trong controller.

Các expectations là HTTP status **dự kiến cho cấu hình HTTP Basic**. Nếu ứng dụng thực dùng Bearer, form login hoặc custom authentication entry point, cách biểu diễn lỗi có thể khác nhưng policy allow/deny phải được giữ.

### 11.1. Chạy tất cả tests

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

Lệnh này chạy tests về React Context trực tiếp và tests HTTP security. Khi debug failure, phân biệt ba tầng:

1. HTTP authorization: WebFilter có yêu cầu login không?
2. Method authorization: `@PreAuthorize` có hoạt động qua Spring proxy không?
3. Data authorization: trusted tenant có nằm trong query/lookup không?

Nếu chỉ kiểm tra HTTP 401/403 mà không assert dữ liệu trả ra, test có thể bỏ sót cross-tenant leak.

---

## 12. Cách tránh cache identity sai và giữ context ngoài vòng đời request

### 12.1. Không giữ current user trong field singleton

Sai:

```java
@Service
class UnsafeMemoService {
    private String currentUsername;

    Mono<String> read() {
        return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> {
                currentUsername =
                    ctx.getAuthentication().getName();
                return currentUsername;
            });
    }
}
```

Đây là mảnh code **cố tình sai về thiết kế**, không thuộc project runnable. `@Service` mặc định singleton; hai subscriptions của Alice/Bob có thể ghi đè field nhau. Sử dụng biến local trong lambda hoặc truyền `Actor` xuống service/repository, không lưu nó thành state chung.

### 12.2. Đừng capture identity ở assembly rồi phát cho subscriber sau

```java
// MẢNH CODE sai trong app reactive nếu capturedUsername
// lấy từ một ThreadLocal ở thời điểm lắp ráp.
String capturedUsername = currentThreadUser();
Mono<String> result = Mono.just(capturedUsername);
```

`Mono.just` tính argument trước lúc tạo Mono; người dùng có thể đã đổi trước subscribe nhưng value bị cố định. Cách đúng trong Reactive Spring Security là lấy user từ context khi subscribe:

```java
Mono<String> result =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());
```

### 12.3. `Mono.cache()` có thể replay một quyết định/response đã authorize

Mảnh code nguy hiểm:

```java
// Shared ở nhiều người dùng: rủi ro nếu đã cache response.
Mono<String> shared = memoService.whoAmI().cache();
```

Nếu Alice subscribe đầu, cache có thể ghi `"alice@T1"`. Bob subscribe **cùng shared cached publisher** sau đó có thể nhận lại `"alice@T1"` mà không subscribe mới tới protected publisher gốc. Đó là rò identity; với `MemoView` là rò dữ liệu.

```text
Alice -> cached mono -> authorized source -> alice@T1
                              |
                              v
                            cache

Bob   -> cached mono -> replay alice@T1
                      (không nhất thiết recheck)
```

Giải pháp: không cache **publisher đã được personalize/authorize** rồi share cross-user; nếu cache raw data, key phải tenant/resource/version/visibility-aware và vẫn check quyền cho mỗi subscriber. Với long-lived hot streams hoặc Server-Sent Events/WebSocket, cần policy per subscriber/session và cơ chế revoke/cancel phù hợp.

### 12.4. Retry/repeat tạo subscriptions mới

```java
Mono<MemoView> publisher = memoService.one(11L);
Mono<MemoView> retried = publisher.retry(1);
```

`retry` có thể subscribe lại và do đó lặp lại việc đọc/quyết định; với write, có thể gây side effect hai lần. Đừng retry authorization denial để “chờ đủ quyền”; deny không phải lỗi mạng tạm thời. Với thao tác mutate, cần idempotency key/transaction/version và retry policy rõ ràng.

### 12.5. Không fire-and-forget `.subscribe()`

Sai trong controller:

```java
@GetMapping("/start")
public Mono<String> start() {
    memoService.one(11L).subscribe();
    return Mono.just("DONE");
}
```

Đây là code mô phỏng **sai**, không thuộc project chạy. Nó mở một subscription phụ có lifecycle/error/context không còn gắn với HTTP response theo ý định, và trả “DONE” dù tác vụ có thể bị deny hoặc chưa xong.

Nên compose:

```java
@GetMapping("/start")
public Mono<MemoView> start() {
    return memoService.one(11L);
}
```

Với background task thực sự, phải tạo job có ownership, identity/policy scope, correlation ID và giao thức kiểm tra quyền **lúc chạy job**, không mượn vô hạn security context của request ban đầu.

---

## 13. Context propagation bridges không thay thế Reactive Security Context

Các hệ thống có thể dùng Micrometer Context Propagation, Reactor `Hooks.enableAutomaticContextPropagation()`, `contextCapture()` hay adapters để đưa một số ThreadLocal qua Reactor operators. Những cơ chế đó giải quyết **interoperability** với tracing/logging/legacy libraries.

Phân biệt:

- **Reactor `Context`:** mô hình gốc theo subscriber, dùng cho Spring Security reactive identity.
- **`SecurityContextHolder` ThreadLocal:** cơ chế imperative với storage strategy, thường được Servlet sử dụng.
- **Micrometer/Reactor context-propagation bridge:** có thể capture/restore những ThreadLocal **đã đăng ký accessor** theo phạm vi và version cụ thể.
- **MDC logging:** thường là ThreadLocal của logging framework, cần bridge nếu muốn trace IDs đi qua scheduler.
- **`ReactiveSecurityContextHolder`:** API được Spring Security cung cấp để lưu/lấy `SecurityContext` trong Reactor pipeline.

Không tuyên bố rằng **mọi** ThreadLocal đều tự được propagate khi bật hook, hoặc code security dùng ThreadLocal luôn đúng nếu tác vụ dùng scheduler. Behavior phụ thuộc Reactor version, thư viện context-propagation, accessor, subscription lifecycle và nơi boundary được đặt.

### 13.1. Khi cần gọi một thư viện imperative

Ví dụ hệ thống còn một SDK cần user ID như argument:

```java
return currentActor.require()
    .flatMap(actor -> legacyAdapter.callFor(
        actor.username(),
        actor.tenantId()
    ));
```

Đây là mảnh code; `legacyAdapter` phải trả Publisher thích hợp và chịu trách nhiệm adapter blocking. Truyền **explicit trusted identity** là cách dễ kiểm chứng hơn việc hy vọng thư viện tự đọc ThreadLocal của Spring.

Nếu SDK chỉ nhận ThreadLocal, cần một adapter có phạm vi thiết lập/khôi phục/clear rất chặt, chạy ở scheduler phù hợp, kiểm thử concurrency, timeout, cancellation và error. Với reactive request processing, **không dùng blocking JDBC/SDK trực tiếp trên event-loop**; `boundedElastic` là một lựa chọn offload có giới hạn, nhưng không tự cấp DB transaction/reactive authorization.

### 13.2. Ngữ cảnh logging và identity không phải một

Có thể đưa `traceId` và `requestId` vào Context cho observability, nhưng không được coi chúng là bằng chứng authentication. Một client có thể gửi correlation ID; nó hữu ích cho log nhưng **không được phép quyết định role/tenant**.

Nếu đưa stable user ID/tenant ID vào audit logs, giới hạn PII, retention và masking. Không log raw bearer tokens, passwords hoặc toàn bộ `Authentication` object.

---

## 14. Security Context không tự bảo đảm quyền vẫn còn hiệu lực

Ngay cả khi `Authentication` được truyền đúng bằng Reactor Context, một quyết định quyền có thể đã lỗi thời:

```text
t1: Subscriber có Authentication Alice / memo:write
t2: @PreAuthorize ALLOW
t3: Admin thu hồi grant hoặc chuyển ownership
t4: Service UPDATE theo dữ liệu cũ
t5: DB COMMIT
```

Reactor Context giải quyết **identity thuộc về ai**; nó không tự đồng bộ **ACL/owner/tenant/role vừa thay đổi**.

Đối với thao tác ghi:

1. Dùng `@PreAuthorize` để kiểm tra authority chức năng.
2. Lấy user/tenant đáng tin từ subscriber security context.
3. Đọc resource/policy từ nguồn authoritative.
4. Guard `tenant_id`, `owner_id`, trạng thái và version ngay trong `UPDATE` hoặc khóa/recheck trong transaction.
5. Khi quyền phụ thuộc grant table/remote PDP, xác định snapshot/revocation semantics và transaction protocol.
6. Không coi `Authentication` trong một long-lived stream là bản sao quyền bất biến mãi mãi.

Ví dụ SQL điều kiện:

```sql
UPDATE memos
SET title = :newTitle,
    version = version + 1
WHERE id = :memoId
  AND tenant_id = :trustedTenant
  AND owner_id = :trustedSubject
  AND version = :expectedVersion;
```

Đây là **SQL minh họa**, không chạy trong store in-memory của project demo. Affected rows `0` nghĩa là không còn khớp một hoặc nhiều điều kiện; không tự bỏ tenant/version để thử lại. Nếu cần quyền cập nhật từ bảng grant khác, điều kiện/lock phải bao phủ chính nguồn quyền đó.

### 14.1. Reactive database transactions

Một ứng dụng R2DBC có thể dùng `ReactiveTransactionManager`/`TransactionalOperator` trong reactive chain:

```java
// MẢNH CODE: cần TransactionalOperator và repository thực.
return transactionalOperator.transactional(
    repository.findByIdAndTenantId(memoId, trustedTenant)
        .flatMap(memo -> verifyAndUpdate(memo, trustedActor))
);
```

Reactive transaction context không đồng nghĩa transaction thread-bound của JDBC. Với R2DBC, transaction được phối hợp theo Reactor Context; đừng gọi `@Transactional` rồi `block()`/tự subscribe để tùy ý tách tác vụ ra ngoài boundary.

**Một Reactor Context có authentication hợp lệ vẫn không làm `UPDATE` unscoped trở thành an toàn.** Identity propagation và data authorization là hai điều kiện khác nhau.

### 14.2. Long-lived stream và revoke

`Flux` có thể phát dữ liệu trong nhiều giờ. Một lần `@PreAuthorize` khi subscription bắt đầu không tự kiểm tra lại mỗi `onNext` hay hủy stream khi user mất quyền. Với dữ liệu nhạy cảm:

- recheck authorization per item/batch hoặc theo policy freshness window;
- cancel active subscribers khi revoke bằng signaling phù hợp;
- dùng query tenant-scoped tại nguồn, tránh prefetch dữ liệu không được phép;
- kiểm tra sự thay đổi tenant/role/ACL version;
- đảm bảo hot/multicast streams không broadcast data tenant A cho subscriber tenant B;
- test việc revoke giữa các signals và sau khi cache warm.

Tất cả điều đó là yêu cầu policy, không phải một tính năng tự động do `contextWrite` mang lại.

---

## 15. Checklist kiểm thử lỗi Context và security bypass

| Ca kiểm thử | Điều cần xác minh |
| --- | --- |
| Tạo `Mono` nhưng chưa subscribe | Không coi là đã thực thi authorization hay data access |
| Subscribe cùng Mono với Alice và Bob | Identity lấy theo từng subscription |
| `publishOn` chuyển scheduler | Identity vẫn lấy từ ReactiveSecurityContextHolder |
| Không có Reactor Security Context | Fail closed, không dùng default admin |
| Anonymous authentication | Không được coi là verified user chỉ bằng `isAuthenticated()` |
| Unknown user/tenant mapping | Từ chối, không query toàn bộ bảng |
| User có auth nhưng thiếu authority | `@PreAuthorize` chặn trước data access |
| User T1 biết ID của T2 | Repository dùng `id + tenant`, không trả nội dung T2 |
| `Mono.cache` shared qua hai users | Không replay response đã personalize trái quyền |
| Dùng `this.securedMethod()` | Phát hiện Spring AOP self-invocation bypass |
| Tạo detached `.subscribe()` | Xử lý lifecycle/error/identity rõ ràng |
| `retry` của action ghi | Không duplicate side effects |
| `flatMap` với inner publisher | Context không mất, không tự subscribe phụ |
| `CompletableFuture`/`@Async` | Identity không phụ thuộc implicit ThreadLocal |
| Thay owner/grant giữa check và write | Transaction/conditional mutation recheck |
| Reactor Context dùng sai vị trí | `contextWrite` phải ảnh hưởng đúng upstream |
| HTTP app dùng `mockUser` | Security WebFilters + method proxy đều hoạt động |
| Nâng Spring Security/Reactor | Kiểm thử context-propagation behavior trên version mới |

### 15.1. Một số lỗi phổ biến

| Sai lầm | Tác động | Cách xử lý |
| --- | --- | --- |
| `SecurityContextHolder.getContext()` trong callback | Context có thể rỗng/stale | Dùng `ReactiveSecurityContextHolder.getContext()` |
| `ThreadLocal` singleton cho user/tenant | Dễ lẫn request | Context per subscriber hoặc explicit trusted actor |
| `InheritableThreadLocal` với thread pool | Không tương ứng request lifecycle | Không dùng làm auth propagation mặc định |
| `Mono.just(expensiveWrite())` | Side effect xảy ra ở assembly | `Mono.defer`/`fromSupplier` và transaction |
| Tin `X-User`, `X-Tenant` | Caller có thể giả danh/chọn tenant nạn nhân | Verify auth + membership server-side |
| Set `withAuthentication` từ JSON input | Bypass authentication provider | Chỉ trusted boundary/test dùng |
| Không có `@EnableReactiveMethodSecurity` | `@PreAuthorize` có thể không bảo vệ method | Bật và test proxy |
| Gọi `new MemoService(...)` | Không qua AOP interceptor | Inject Spring-managed bean |
| Gọi `this.secured()` từ cùng bean | Self-invocation bypass proxy | Tách bean, giữ domain guard |
| Test không subscribe | Không quan sát reactive authorization | StepVerifier hoặc WebTestClient |
| Cache Mono đã authorize cross-user | Replay dữ liệu của user khác | Cache scope và reauthorize per subscriber |
| Fire-and-forget `.subscribe()` | Mất lifecycle, lỗi không được xử lý | Return/compose publisher |
| Gọi `.block()` trên WebFlux event-loop | Nghẽn thread, giảm throughput | Reactive composition |
| `publishOn` rồi đọc raw ThreadLocal | Giá trị không được đảm bảo | Reactor Context, adapter kiểm soát |
| Lưu `Authentication` trong singleton field | Race và identity bleed | Resolver lazy theo subscriber |
| Nhầm traceId với principal | Không có authentication guarantee | SecurityContext authoritative |
| Dựa vào role cũ cho write sau revoke | TOCTOU | Recheck/conditional DB update |
| Dữ liệu thuộc tenant khác vẫn xuất hiện | Repository unscoped | `WHERE tenant_id = trustedTenant` |
| Bắt AccessDenied rồi return secret | Fail-open | Deny và không phát dữ liệu nhạy cảm |
| WebTestClient không gắn `springSecurity()` | Test không phản ánh WebFilter bảo mật | Apply test security setup |

---

## 16. Bài tập và câu hỏi tự kiểm tra

### Câu 1: vì sao `ThreadLocal` không đủ?

Trong một WebFlux request, source được subscribe trên event-loop thread, sau đó `publishOn(Schedulers.parallel())`. Có bảo đảm `SecurityContextHolder.getContext()` bằng ThreadLocal trả đúng identity ở cả hai thread không?

**Đáp:** Không. Cần `ReactiveSecurityContextHolder`/Reactor Context hoặc một adapter propagation được cấu hình và kiểm thử có chủ đích.

### Câu 2: `contextWrite` ảnh hưởng hướng nào?

```java
Mono<String> result = Mono.deferContextual(ctx ->
    Mono.just(ctx.get("tag"))
)
.contextWrite(ctx -> ctx.put("tag", "ONE"))
.contextWrite(ctx -> ctx.put("tag", "TWO"));
```

**Đáp:** Source thấy `"ONE"` (operator ghi gần source hơn), không phải `"TWO"`.

### Câu 3: tại sao `withAuthentication` không được dùng trực tiếp từ body?

**Đáp:** Vì nó chỉ mang Authentication vào Context, không tự xác minh credential hoặc membership. Lấy username/role từ JSON rồi đặt sẽ tạo principal giả mạo.

### Câu 4: một Mono được subscribe hai lần dưới hai users

`Mono<String> p = memoService.whoAmI()` được subscribe bởi Alice T1 và Bob T2. Với cold publisher và Context đúng, có nên trả cùng một username không?

**Đáp:** Không. Mỗi subscriber mang identity riêng; test dùng `StepVerifier` xác nhận hai kết quả.

### Câu 5: thiếu authentication

`ReactiveSecurityContextHolder.getContext()` không phát giá trị. Service nên fallback sang admin hay đọc mọi tenant?

**Đáp:** Không. Fail closed, không có identity hợp lệ thì không dùng unscoped repository.

### Câu 6: sự khác nhau giữa HTTP auth và method auth

`@EnableWebFluxSecurity` bảo vệ URL, còn `@PreAuthorize` reactive service cần gì?

**Đáp:** Bật `@EnableReactiveMethodSecurity` và gọi method qua Spring proxy, kiểm thử bằng subscription thật.

### Câu 7: `Mono.cache()` có thể rò user không?

**Đáp:** Có nếu cache bao ngoài một publisher đã được personalize/authorize cho Alice rồi cùng instance được share cho Bob. Cần cache scope và recheck per subscriber.

### Câu 8: `Mono.just(performWrite())` có lazy không?

**Đáp:** Không nếu `performWrite()` được Java gọi ngay để tính argument. Dùng `Mono.defer`/`fromSupplier` cho nguồn lazy và đặt mutation trong transaction/policy boundary.

### Câu 9: một `Flux` chạy lâu, user bị revoke

**Đáp:** Context tiếp tục mang identity; nó không tự chặn mọi item sau revoke. Cần per-item/batch check hoặc cancel theo security contract.

### Câu 10: khi đi sang background queue

Có nên copy toàn bộ Reactor Context của request, gồm token, và replay vài ngày sau?

**Đáp:** Không. Chuyển tối thiểu identity/scope theo hợp đồng integrity, rồi reauthorize khi job thực thi; không lưu raw access token lâu dài.

### Câu 11: tại sao `@PreAuthorize` có thể chưa bảo vệ được object của T2?

**Đáp:** Role `memo:read` là functional authority. Repository vẫn cần tenant scope và object policy, không chỉ authentication.

### Câu 12: cách kiểm chứng không có side effect sau denial?

**Đáp:** Đặt counter/log tại nguồn lazy hoặc đọc lại DB. Sau `StepVerifier.expectError(AccessDeniedException.class)`, assert source chưa chạy và dữ liệu chưa thay đổi.

### Câu 13: tại sao dùng `AuthenticationTrustResolver`?

**Đáp:** Để không nhầm anonymous token có `isAuthenticated()==true` với user đã được xác minh; kết hợp directory và trust checks.

### Câu 14: Reactor `Context` có phải security boundary chống code nội bộ giả mạo không?

**Đáp:** Không. Bất kỳ trusted code có quyền xây publisher và tạo Authentication đều có thể đặt Context. Security boundary nằm ở authentication provider, principal validation, method/data authorization và cấu hình hệ thống.

### Câu 15: test sau khi đổi scheduler phải assert gì?

**Đáp:** `ReactiveSecurityContextHolder.getContext()` vẫn trả identity của subscriber dù `publishOn`/`subscribeOn` thay scheduler; không giả định thread name hay ThreadLocal value cụ thể.

---

## 17. Tham khảo và tài liệu chính thức

1. [Spring Security 6.5 — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html): `@EnableReactiveMethodSecurity`, Reactor Context, `@PreAuthorize` trên `Mono`/`Flux`.
2. [Spring Security 6.5 API — ReactiveSecurityContextHolder](https://docs.spring.io/spring-security/site/docs/6.5.2/api/org/springframework/security/core/context/ReactiveSecurityContextHolder.html): `getContext`, `withAuthentication`, `withSecurityContext`, `clearContext`.
3. [Spring Security — Reactive Authentication](https://docs.spring.io/spring-security/reference/reactive/authentication/index.html): authentication in WebFlux.
4. [Spring Security — Reactive WebFlux Security Configuration](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html): `SecurityWebFilterChain`, WebFilter và authentication.
5. [Spring Security — Testing WebFlux Applications](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/index.html): WebTestClient và test support.
6. [Spring Security — WebFlux Test Authentication](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html): `mockUser`, `springSecurity()`.
7. [Project Reactor — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): subscriber Context, `contextWrite`, `deferContextual`, hướng propagation.
8. [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): `publishOn`, `subscribeOn`, scheduler semantics.
9. [Project Reactor — Context Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html): interoperability giữa Reactor Context và ThreadLocal.
10. [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): StepVerifier và subscriber-driven tests.
11. [Spring Framework — Reactive Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): transaction propagation với Reactor, `TransactionalOperator`.
12. [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): Spring AOP/self-invocation limitations.

**Kết luận:** Trong WebFlux, identity nên được lấy **theo subscriber qua `ReactiveSecurityContextHolder`**, không dựa vào `ThreadLocal` của một Java thread. `contextWrite` giúp đưa context vào pipeline trong test/boundary tin cậy; Spring Security WebFlux tự thiết lập context cho HTTP request đã xác thực. `@EnableReactiveMethodSecurity` + `@PreAuthorize` bảo vệ các publishers khi chúng được thực thi qua Spring proxy. Tuy nhiên, Context không tự xác minh input, không bảo vệ dữ liệu cross-tenant nếu query thiếu scope, không ngăn cache phát lại dữ liệu của user khác và không giải quyết revoke/TOCTOU sau khi đã cho phép. Hãy test bằng `StepVerifier`/`WebTestClient` với nhiều users và scheduler hops, đồng thời guard tenant/ACL/transaction ở tầng dữ liệu.