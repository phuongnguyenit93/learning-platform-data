# Vì sao không dùng ThreadLocal để suy luận danh tính xuyên chuỗi reactive

> **Trọng tâm:** Trong Servlet truyền thống, `SecurityContextHolder` thường dựa trên `ThreadLocal` để code chạy trên một request thread truy cập `Authentication` hiện tại. Trong **WebFlux/Reactor**, một yêu cầu được biểu diễn bằng một **chuỗi Publisher/Subscriber bất đồng bộ**: các tín hiệu có thể chạy trên nhiều thread, một thread có thể phục vụ nhiều subscription, và chính chuỗi có thể được lắp ráp ở thời điểm khác với lúc xử lý. Vì vậy, **thread hiện tại không phải danh tính của request/subscription**. Dùng `ThreadLocal` hoặc `SecurityContextHolder.getContext()` làm nguồn suy luận user xuyên toàn bộ pipeline reactive có thể trả null, thấy giá trị không đúng phạm vi hoặc khiến code bỏ qua authorization. Spring Security reactive sử dụng **Reactor Context** và `ReactiveSecurityContextHolder` để mang `SecurityContext` theo **subscriber**, không phụ thuộc việc continuation chạy trên thread nào.

Bài thuộc nhóm **Ngữ cảnh bảo mật** của module **Spring Security – fundamentals**. Phần thực hành dùng Java 17+, Spring Boot **3.5.16**, Spring Security **6.5.x** và Spring WebFlux/Project Reactor. Bài đối chiếu với Servlet để giải thích bản chất, nhưng ứng dụng mẫu **chỉ dùng WebFlux**, `SecurityWebFilterChain`, `ReactiveSecurityContextHolder` và `WebTestClient`. Mật khẩu mẫu chỉ phục vụ môi trường localhost.

## 1. Sau bài học bạn làm được gì?

1. Phân biệt rõ **thread**, **request**, **publisher**, **subscriber**, **subscription**, **signal** và **Reactor Context**.
2. Giải thích tại sao `ThreadLocal.get()` không đại diện danh tính của toàn bộ reactive chain.
3. Biết `Mono.just(...)` có thể tính dữ liệu khi lắp ráp chuỗi, còn `Mono.defer(...)` tạo giá trị tại subscription nhưng **vẫn không sửa được vấn đề xác định identity bằng thread**.
4. Hiểu `Mono.deferContextual(...)`, `ContextView` và `contextWrite(...)`; biết phạm vi ảnh hưởng của `contextWrite` đến các operator **upstream**.
5. Dùng `ReactiveSecurityContextHolder.getContext()` để lấy authentication đáng tin từ pipeline reactive.
6. Nhận ra Spring Security WebFlux dùng `WebFilter`/`SecurityWebFilterChain`, `ReactiveAuthenticationManager` và `ServerSecurityContextRepository`, không phải cơ chế Servlet `ThreadLocal`/`HttpSecurity`.
7. Phân biệt tác động của `publishOn`, `subscribeOn`, `delayElement` và asynchronous boundaries đối với **scheduler** với tác động đối với **Reactor Context**.
8. Tránh tạo `subscribe()` lồng nhau, gọi `block()` trên event-loop, lưu principal trong field mutable/static hay dùng raw thread pool để tự suy luận user.
9. Chạy ứng dụng WebFlux có auth thật qua HTTP Basic + BCrypt, kiểm tra identity vẫn đúng sau khi chuyển scheduler, phân biệt Alice/Bob và kiểm tra role/method security.
10. Viết unit test `StepVerifier` cho hai subscriber độc lập và integration test `WebTestClient` để chứng minh context không bị truyền nhầm qua request.

## 2. Cần hiểu đúng: ThreadLocal thuộc về thread, còn Reactor Context thuộc về subscriber

### 2.1. Servlet cổ điển

Một luồng đồng bộ đơn giản:

```text
HTTP request của Alice
       |
       v
Tomcat/Servlet worker thread T1
       |
       v
Spring Security Servlet filter chain
       |
       v
SecurityContextHolder (mặc định MODE_THREADLOCAL)
       |
       v
Controller -> Service -> Repository trên T1
       |
       v
Filter dọn SecurityContext khỏi ThreadLocal
       |
       v
T1 được tái sử dụng cho request khác
```

Trong mô hình này, `SecurityContextHolder.getContext()` giúp code trên **cùng một thread request** biết authentication hiện tại. Spring Security Servlet filter chain phải dọn ThreadLocal khi kết thúc để tránh một thread đã xử lý Alice còn giữ danh tính khi phục vụ Bob.

Đây là một convenience có vòng đời rõ. Nó **không có nghĩa** một thread mãi thuộc về Alice hoặc rằng một authentication sẽ tự đi theo mọi `@Async`, `CompletableFuture` hay HTTP callback.

### 2.2. WebFlux/Reactor

Một request reactive không nhất thiết được xử lý bởi một thread cố định:

```text
HTTP request của Alice
       |
       v
WebFlux WebFilter chain thiết lập reactive security context
       |
       v
Subscriber/Subscription của pipeline Alice
       |
       +-- Tại một thời điểm: event-loop thread E1
       |      map/filter/flatMap...
       |
       +-- Khi có delay hoặc publishOn: worker thread W3
       |      tiếp tục operator...
       |
       +-- Async I/O callback: event-loop E2 hoặc thread khác
       |      hoàn tất Mono/Flux...
       |
       v
Response cho Alice

Đồng thời:
HTTP request của Bob -> subscriber riêng -> có thể dùng E1, W3, E2
```

Cùng một thread có thể chạy tín hiệu thuộc nhiều subscriptions **ở những thời điểm khác nhau**. Một chuỗi của Alice có thể đổi thread giữa các operator. Ngược lại, một thread phục vụ Bob sau Alice không hề cho biết current principal là ai chỉ bằng thread ID.

**Đơn vị hợp lý để gắn metadata theo reactive operation là subscriber/subscription context**, không phải worker thread.

### 2.3. Bảng so sánh

| Tiêu chí | Servlet đồng bộ | WebFlux/Reactor |
| --- | --- | --- |
| Mô hình thực thi | Thường là thread per request trong đoạn đồng bộ | Tín hiệu bất đồng bộ, thread switching, chia sẻ event-loop |
| Holder bảo mật chuẩn | `SecurityContextHolder` | `ReactiveSecurityContextHolder` |
| Cách mang context | `ThreadLocal` theo strategy Servlet mặc định | `Reactor Context` gắn với subscriber |
| Filter bảo mật | `SecurityFilterChain`/Servlet `Filter` | `SecurityWebFilterChain`/`WebFilter` |
| Cấu hình web | `HttpSecurity` | `ServerHttpSecurity` |
| Authentication manager | `AuthenticationManager` | `ReactiveAuthenticationManager` |
| Repository context | `SecurityContextRepository` | `ServerSecurityContextRepository` |
| Test HTTP | `MockMvc` | `WebTestClient` |
| Test async | Executor/thread tests | `StepVerifier` + test subscription/scheduler |
| Sai lầm điển hình | Quên dọn ThreadLocal khi reuse thread | Đọc ThreadLocal thay vì Reactor Context, nested subscribe hoặc mất context ở bridge |

**Lưu ý:** Trong hệ thống thật, Servlet cũng có async dispatch và Reactor có thể tích hợp restoration cho một số ThreadLocal. Bảng mô tả **mặc định và cơ chế nguồn của danh tính**, không tuyên bố mọi request Servlet chạy đúng một thread hoặc mọi reactive operator luôn đổi thread.

## 3. Lỗi nền tảng: lấy ThreadLocal như thể nó là identity của logical request

### 3.1. Vì sao việc đọc có thể sai?

```java
// PHẢN VÍ DỤ trong một reactive service WebFlux.
Mono<String> currentUserWrong() {
    return Mono.fromSupplier(() -> {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();

        return auth == null ? "unknown" : auth.getName();
    });
}
```

Đây là snippet, các import/class được lược bỏ có chủ đích. `Mono.fromSupplier(...)` hoãn thực thi cho đến subscription — điểm này tốt hơn đọc ngay khi tạo publisher — nhưng bên trong nó vẫn đọc `SecurityContextHolder` dựa trên **ThreadLocal**. Không có hợp đồng Spring Security WebFlux rằng ThreadLocal đó luôn chứa authentication của subscriber hiện tại.

Có thể gặp:

- Giá trị null/rỗng dù HTTP request đã được xác thực đúng trong WebFlux.
- Giá trị do một component tự gán cho worker thread ở một scope khác.
- Kết quả thay đổi khi thêm `publishOn` hoặc thay scheduler.
- Test chạy đơn thread có vẻ đúng nhưng production dưới tải đồng thời bị sai.
- Log/audit xác định sai actor hoặc code authorization tự viết cấp quyền sai.

**Không dự đoán tuyệt đối rằng kết quả lúc nào cũng null.** Một số hệ thống dùng Micrometer Context Propagation có thể khôi phục `ThreadLocal` trong một số đoạn operator. Sự tồn tại của cơ chế bridge đó vẫn **không biến ThreadLocal thành nguồn danh tính chủ đạo của WebFlux**; nguồn đúng là security context của subscription.

### 3.2. Đọc quá sớm ở assembly time

```java
// Cũng là PHẢN VÍ DỤ:
Authentication a =
    SecurityContextHolder.getContext().getAuthentication();

Mono<String> user =
    Mono.just(a == null ? "unknown" : a.getName());
```

Ở đây giá trị được đọc **khi tạo Mono**, không phải khi có subscription. Nếu `user` được tạo một lần trong một bean singleton, nó có thể giữ identity của thời điểm khởi tạo hoặc một request trước rồi dùng cho mọi subscriber. Kể cả tạo Mono trong controller, assembly và subscription vẫn là hai thời điểm khác nhau: dựa vào timing của thread là một giả định dễ hỏng.

### 3.3. defer không đồng nghĩa đúng identity

`Mono.defer(...)` trì hoãn việc gọi supplier tới lúc có subscriber. Điều này hữu ích khi cần lazy evaluation. Nhưng nếu supplier vẫn gọi `ThreadLocal.get()`, kết quả còn phụ thuộc thread lúc supplier chạy và bridge configuration. Muốn biết context của **chính subscriber**, dùng `Mono.deferContextual(...)` hoặc `ReactiveSecurityContextHolder.getContext()`.

### 3.4. Lỗi nghiêm trọng nhất không chỉ là NullPointerException

Nếu `auth` null, code có thể throw hoặc từ chối request — đây là lỗi chức năng. Nếu code tự fallback sang một system principal có nhiều quyền, bỏ qua kiểm tra vì “không thấy user”, hoặc dùng giá trị ThreadLocal cũ từ thread khác, hậu quả có thể là **IDOR/BOLA, lộ dữ liệu, ghi audit sai, cross-tenant access**.

Không sửa bằng `MODE_GLOBAL` hay `MODE_INHERITABLETHREADLOCAL` trong WebFlux. `MODE_GLOBAL` cho nhiều user chia một context; inherited thread local không mang identity đúng với từng subscription được schedule trên thread pool.

## 4. Reactor Context: cách truyền metadata đúng theo subscription

### 4.1. Context không phải một Map toàn cục

Reactor `Context` là cấu trúc key/value được cung cấp trong **Reactive Streams subscriber chain**. Khi context được cập nhật bằng `put`, Reactor tạo context mới theo semantic immutable, không làm thay đổi một Map static dùng chung cho mọi request.

```text
Mono<String> source
    |
    v
map/filter/flatMap...
    |
    v
Subscriber S_A với Context_A (actor=alice)
    
Cùng source publisher có thể có:
Subscriber S_B với Context_B (actor=bob)

Context_A và Context_B không cần cùng thread;
hai subscriber không tự động thấy key/value của nhau.
```

Không nên hiểu Context là “ThreadLocal cách viết khác”. Nó đi cùng **subscription**, cho phép downstream subscriber cung cấp dữ liệu để upstream operators đọc khi thực thi. Nó cũng không phải database/session: subscription kết thúc không làm dữ liệu tự lưu sang một HTTP request độc lập.

### 4.2. Ví dụ thuần Reactor: contextWrite và deferContextual

Một publisher:

```java
Mono<String> source =
    Mono.deferContextual(view ->
        Mono.just(view.getOrDefault("actorId", "missing"))
    );

Mono<String> alice =
    source.contextWrite(ctx -> ctx.put("actorId", "alice"));

Mono<String> bob =
    source.contextWrite(ctx -> ctx.put("actorId", "bob"));
```

**Ý nghĩa:** Hai subscription khác nhau có thể chạy cùng `source` nhưng nhận `actorId` khác nhau tùy context. Nếu không có key, code trả `missing`. Những chuỗi `alice`/`bob` là dữ liệu demo, **không phải bằng chứng người dùng đã đăng nhập**. Trong sản phẩm thật, không cho client tự điền `actorId` rồi coi nó là authority; security context phải do authentication mechanism đáng tin thiết lập.

### 4.3. Vì sao contextWrite đặt “bên dưới” lại có tác dụng “bên trên”?

Quy tắc Reactor: `contextWrite` nhận context từ **downstream subscriber** và bổ sung key để các operator **upstream** thấy. Ví dụ:

```java
Mono<String> visible =
    Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("traceId", "missing"))
    )
    .contextWrite(ctx -> ctx.put("traceId", "request-42"));
```

Khi có subscription, `deferContextual` trả `request-42`.

Nhưng:

```java
Mono<String> notAutomaticallyVisibleDownstream =
    Mono.just("start")
        .contextWrite(ctx -> ctx.put("traceId", "request-42"))
        .flatMap(ignored ->
            Mono.deferContextual(ctx ->
                Mono.just(ctx.getOrDefault("traceId", "missing"))
            )
        );
```

`flatMap` ở **downstream** của `contextWrite` không nhất thiết thấy key do một operator ở upstream thêm. Với sơ đồ trên, `deferContextual` ở dưới được thiết kế để trả `missing` vì key không lan ngược theo chiều dữ liệu. Đây là một khác biệt với tư duy “gọi set() thì mọi code phía sau đọc được”.

### 4.4. Mỗi subscribe là một subscription mới

Một `Mono` hay `Flux` có thể được **subscribe** nhiều lần. Với cold publisher, mỗi subscription thực thi lại source theo semantic của nó và có context riêng. Một `Flux` chia sẻ hot source vẫn có thể có nhiều subscribers với metadata riêng; cách propagation phải được kiểm chứng theo các operator/share boundaries cụ thể.

**Không nên lưu một `SecurityContext` mutable rồi mutate nó giữa hai subscribers**. Reactor Context bảo vệ phạm vi key/value, nhưng các object reference được gắn vào Context **có thể vẫn mutable**. Spring Security quản lý context theo request; code ứng dụng không nên mutate `Authentication`/authorities đã được công nhận trong một singleton.

## 5. SecurityContext trong Spring WebFlux

### 5.1. Các thành phần

```text
HTTP request
    |
    v
Spring WebFlux WebFilter chain
    |
    v
Spring Security SecurityWebFilterChain
    |
    +-- AuthenticationWebFilter (tùy mechanism)
    |       |
    |       v
    |   ReactiveAuthenticationManager
    |       |
    |       v
    |   Authentication đã kiểm chứng
    |
    +-- ReactorContextWebFilter / reactive context integration
    |       |
    |       v
    |   Mono<SecurityContext> trong Reactor Context
    |
    +-- Reactive authorization (URL/method)
    |
    v
Controller -> Service trả Mono/Flux
    |
    v
ReactiveSecurityContextHolder.getContext()
    |
    v
Mono<SecurityContext> -> Authentication -> principal/authorities
```

Đây là sơ đồ thành phần, không phải trình tự cố định của mọi WebFilter cho mọi cơ chế. `ReactorContextWebFilter` tích hợp `ServerSecurityContextRepository` để thiết lập reactive security context; authentication filters cũng tương tác với context theo thiết kế. `SecurityWebFilterChain` không tương đương một `SecurityFilterChain` Servlet chỉ đổi tên.

### 5.2. API đọc identity đúng

Trong WebFlux, dùng:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Mono<String> username =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .defaultIfEmpty("anonymous");
```

Đây là snippet. Method `getContext()` trả `Mono<SecurityContext>`; nó không yêu cầu code hiện tại phải biết tên thread. Khi không có context, có thể là empty Mono. `defaultIfEmpty(...)` ở đây chỉ dùng cho **thông báo minh họa**, tuyệt đối không chuyển anonymous thành actor có quyền. Trong API bảo vệ, nếu thiếu user đáng tin thì trả lỗi xác thực/phân quyền thích hợp, không tự cho phép truy cập.

### 5.3. Đọc current principal có hai kiểu hợp lệ

1. Trong reactive service, lấy bằng `ReactiveSecurityContextHolder.getContext()` và compose bằng `map`/`flatMap`.
2. Ở WebFlux controller, Spring có thể resolve `Principal` hoặc `Mono<Principal>` từ request thông qua method argument theo API; nếu cần business service độc lập HTTP framework, truyền actor ID đã được xác minh hoặc đọc reactive context tại nơi cần.

Nếu cần authorize theo object, đừng chỉ dùng `auth.getName()` là có quyền. Route `GET /orders/{id}` phải kiểm owner/tenant/permission trong service/repository. `Authentication` cho biết “ai”, không tự trả lời “được thao tác record này không”.

### 5.4. API ghi context trong unit test hoặc flow tin cậy

Spring Security cho phép thiết lập context vào **một subscription** trong test:

```java
Authentication testAlice =
    new TestingAuthenticationToken("alice", "unused", "ROLE_USER");

Mono<String> forAlice =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(testAlice)
        );
```

Đây là snippet dùng authentication **giả lập** trong test, không thực hiện password authentication. `withAuthentication(authentication)` tạo một Reactor `Context` để truyền authentication đã cung cấp; method này không tự xác minh credential. Trong ứng dụng thật, authentication context cần đến từ **WebFlux security filters/provider/verified token**; không lấy role từ body rồi tự gọi `withAuthentication(...)`.

API `ReactiveSecurityContextHolder.withSecurityContext(Mono<SecurityContext>)` có thể dùng khi đã có context đáng tin, và `ReactiveSecurityContextHolder.clearContext()` hỗ trợ thao tác context theo cơ chế Reactor; không áp dụng `ThreadLocal.remove()` cho các API này.

### 5.5. Session và Reactor Context là hai vấn đề khác nhau

`Reactor Context` chứa metadata để operator trong **subscription hiện tại** có thể truy cập; `ServerSecurityContextRepository` (ví dụ `WebSessionServerSecurityContextRepository` hoặc `NoOpServerSecurityContextRepository`) quyết định lưu/khôi phục authentication **qua những HTTP requests khác nhau**.

Với HTTP Basic stateless trong demo ở phần thực hành, mỗi request tự gửi credential. Nếu dùng WebSession/OIDC login, security filter có thể khôi phục authenticated identity từ session mới vào reactive context ở request sau.

Không đồng nhất:
- Reactor Context với HTTP Session.
- `contextWrite(...)` với lưu database.
- `clearContext()` reactive với logout/revoke refresh token.
- `SecurityContextHolder.clearContext()` Servlet với xóa security context của một subscription WebFlux.

## 6. publishOn, subscribeOn, delay và context

### 6.1. Scheduler là điều khiển thực thi, không phải nơi lưu identity

`publishOn(scheduler)` dịch chuyển việc chạy **các signal downstream** từ vị trí operator đó sang worker scheduler được chỉ định. `subscribeOn(scheduler)` ảnh hưởng việc **subscribe tới upstream** và một phần execution pipeline. Cả hai có thể thay đổi thread sử dụng, nhưng **không làm Reactor Context bị đổi owner sang user khác** khi pipeline dùng operator native và context được truyền đúng.

```text
Request Alice, subscription S_A, Context_A
       |
       v
map(...) trên event-loop E1
       |
       v
publishOn(boundedElastic)
       |
       v
flatMap(...) trên worker W2
       |
       v
ReactiveSecurityContextHolder.getContext()
       |
       v
Authentication(Alice) của subscription S_A
```

Không cần cố giữ mọi operator của Alice trên cùng E1. Đó là đi ngược mô hình reactive và làm giảm khả năng mở rộng.

### 6.2. Ví dụ đúng sau chuyển scheduler

```java
Mono<String> afterSchedulerHop() {
    return Mono.delay(Duration.ofMillis(10))
        .publishOn(Schedulers.boundedElastic())
        .then(ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName))
        .map(name -> "after-hop:" + name);
}
```

Snippet này giả định có import Reactor/Spring Security tương ứng. `Mono.delay` phát signal bất đồng bộ; `publishOn` làm execution downstream chuyển scheduler; source identity được đọc từ **Reactor Context** khi `Mono` được subscribe. Một test có thể chứng minh chuỗi vẫn nhận Alice, dù thread đã đổi. **Không assert exact thread name** trong test vì runtime/scheduler/pool có thể thay đổi.

### 6.3. Vì sao không dùng Thread.currentThread().getName() để xác thực?

`Thread.currentThread().getName()` chỉ hữu ích để quan sát concurrency và debug. Tên như `reactor-http-nio-3`, `parallel-2` hoặc `boundedElastic-1` không nói actor là ai. Cùng tên thread có thể chạy signals cho nhiều user; một user có thể xuất hiện trên nhiều thread. Không map thread name → user/tenant/role.

### 6.4. Không dùng thread-local request variable để chuyển tenant

Nếu một WebFlux service tự tạo `private static final ThreadLocal<String> TENANT` rồi dùng `TENANT.set(...)` ở filter và `TENANT.get()` trong một `map(...)` sâu, nó có nguy cơ thấy tenant sai hoặc null sau scheduler switch.

Để an toàn:
- Xác minh tenant thuộc authenticated principal.
- Truyền tenant ID rõ ràng theo method arguments tới domain/repository, hoặc đặt metadata có provenance rõ trong Reactor Context.
- Không coi key `tenantId` trong Reactor Context là authority nếu một filter không đáng tin có thể ghi vào.
- Database queries dùng owner/tenant predicate và domain authorization, không chỉ rely vào HTTP path.

## 7. Khi nào context có thể bị “mất” khỏi một chuỗi?

### 7.1. Tạo subscribe() lồng nhau

```java
// PHẢN VÍ DỤ: fire-and-forget bên trong một reactive operator.
Mono<String> broken() {
    return reactiveIdentity.currentName()
        .map(actor -> {
            sendNotification(actor).subscribe();
            return "accepted";
        });
}
```

Snippet này cố tình thiếu class/fields để chỉ ra lỗi. `subscribe()` tạo **subscription mới**, tách khỏi subscription HTTP của caller; context, error, cancellation, tracing và lifecycle không còn được compose tự nhiên. Việc giữ `actor` trong closure có thể khiến notification biết một chuỗi tên, nhưng không đồng nghĩa nó có security context/permission chính xác. Error trong notification có thể bị xử lý không như mong muốn; request có thể trả thành công trước khi notification hoàn tất.

**Đúng hơn:** compose cùng chuỗi:

```java
Mono<String> composed() {
    return reactiveIdentity.currentName()
        .flatMap(actor ->
            sendNotification(actor).thenReturn("accepted")
        );
}
```

Nếu notification thật sự phải chạy ngoài request, sử dụng queue/outbox với message đáng tin, actor/tenant/action metadata, transaction, retry và reauthorization theo chính sách; đừng tạo một nested subscription vô danh trong controller.

### 7.2. Gọi block() trên event-loop

```java
// PHẢN VÍ DỤ trong WebFlux controller:
String actor = reactiveIdentity.currentName().block();
return Mono.just("hello:" + actor);
```

`block()` là subscription/blocking boundary; trên non-blocking Reactor event-loop có thể bị từ chối hoặc gây thread starvation, timeouts và phá mô hình reactive. Nó cũng tạo một điểm khó reasoning về context vì bạn đã thoát chuỗi đang được WebFlux quản lý.

**Đúng:** giữ `Mono`:

```java
Mono<String> hello() {
    return reactiveIdentity.currentName()
        .map(actor -> "hello:" + actor);
}
```

### 7.3. Raw ExecutorService, CompletableFuture, callback SDK

Reactor Context có scope thuộc Reactor subscriber; một `Runnable` chạy trên `ExecutorService` hoặc callback SDK tự mở thread **không tự biến thành reactive operator có cùng context**.

Nếu cần gọi legacy blocking code:

```java
Mono<Order> loadOwnedOrder(String orderId) {
    return reactiveIdentity.currentName()
        .flatMap(actorId ->
            Mono.fromCallable(() ->
                    legacyOrderDao.findOwnedOrder(actorId, orderId))
                .subscribeOn(Schedulers.boundedElastic())
        );
}
```

Đoạn này là snippet định hướng; `Order`/`legacyOrderDao` và policy cần được dự án thực hiện. Quan trọng là **đọc actor đã được xác minh ở reactive boundary**, rồi truyền **giá trị actor ID rõ ràng** tới blocking DAO. Trong DAO vẫn cần kiểm owner/tenant và authorization thật; việc truyền một string không tự chứng minh quyền. Chạy blocking call qua `boundedElastic` để không chặn Netty event-loop.

### 7.4. Nested request hoặc messaging

Một HTTP client như `WebClient` có publisher riêng; context của chain sẽ được propagate qua các operator Reactor phù hợp, nhưng **security identity không tự được chia sẻ sang một service khác như một credential hợp lệ**. Nếu downstream cần xác thực, phải có OAuth2 token relay/propagation policy được xác minh, không tự lấy username rồi đặt header `X-User` và coi header đó là trusted authentication.

Với Kafka/RabbitMQ/SQS message, consumer là một scope mới: metadata actor phải được ký/kiểm soát phù hợp, kiểm token/authorization lại, không suy luận user từ ThreadLocal của listener.

### 7.5. cache, share, hot publisher và context

`Mono.cache()` có thể cache một giá trị và chia sẻ lại cho subscribers khác. Nếu cached value là **dữ liệu theo người dùng** hoặc principal, đặt cache ở singleton không có key actor/tenant có thể khiến Alice nhận kết quả của Bob (hoặc ngược lại), ngay cả khi Reactor Context ở mọi subscription vẫn đúng. Đừng cache publisher/result theo một key chung khi response phụ thuộc identity; cache key và scope phải bao gồm security-relevant dimensions và expiry.

Tương tự, `share()`/`publish().refCount(...)` và các publisher hot có cơ chế đăng ký nguồn riêng; đừng giả định context của từng downstream subscriber tự tạo lại identity cho một source upstream được dùng chung. Test các boundary này theo behavior của operator thực tế.

## 8. Micrometer Context Propagation: ngoại lệ phải hiểu đúng

### 8.1. Vì sao đôi khi ThreadLocal vẫn “có vẻ đúng” trong reactive code?

Reactor có hỗ trợ `io.micrometer:context-propagation` SPI. Khi ứng dụng cấu hình `ThreadLocalAccessor` và chế độ khôi phục thích hợp, một số giá trị từ Reactor Context có thể được **tạm đưa vào ThreadLocal** quanh callback:

- Default/limited mode: một số operators như `handle`/`tap` có cơ chế restoration phù hợp khi library hiện diện.
- Automatic mode: có thể bật bằng `Hooks.enableAutomaticContextPropagation()` trước các subscriptions cần áp dụng.
- `contextCapture()` có thể chụp các ThreadLocal đã đăng ký ở thời điểm subscription để đưa vào Reactor Context.
- Các cơ chế này có phạm vi, chi phí, thời điểm bật và quy tắc cleanup; không phải mọi ThreadLocal tự động được propagate.

Vì thế câu khẳng định “ThreadLocal luôn null trong WebFlux” là **không chính xác**. Tuy nhiên câu khẳng định “mọi reactive operator có thể dùng ThreadLocal làm nguồn bảo mật” cũng **không đúng**.

### 8.2. Nguồn sự thật vẫn là context của subscription

Khi bridge được bật, Reactor Context là **nguồn ngữ cảnh** mà các registered ThreadLocal accessors sử dụng để khôi phục state trong những scope được hỗ trợ. Điều đó có lợi khi tích hợp thư viện logging/MDC hoặc mã imperative cần tương thích, nhưng không nên viết mới authorization dựa trên `SecurityContextHolder.getContext()` trong WebFlux.

Đối với Spring Security WebFlux:
- Dùng `ReactiveSecurityContextHolder.getContext()` để đọc authentication trong pipeline.
- Dùng `@EnableReactiveMethodSecurity`/`@PreAuthorize`/`SecurityWebFilterChain` để bảo vệ điểm truy cập.
- Với blocking bridge, truyền trusted actor ID/permissions vào service hoặc thiết kế propagation có kiểm soát và test.
- Nếu bật automatic ThreadLocal propagation, test cả case **không có context** để chắc chắn các accessors xóa state đúng, tránh cross-subscriber leak.
- Benchmark overhead và contention; propagation không miễn phí.

### 8.3. Không bật global hook chỉ để “fix auth.getName()”

`Hooks.enableAutomaticContextPropagation()` ảnh hưởng behavior của Reactor trong toàn process đối với các subscription mới. Nó không tự kiểm chứng credentials hay biến một `ThreadLocal` tùy tiện thành authentication hợp lệ. Với hệ thống web multi-user, thay đổi global hook cần đánh giá timing, performance, library integration và cleanup; không bật một cách vô thức để một đoạn code legacy đọc được current user.

## 9. Ví dụ chạy được: Spring Boot WebFlux + Reactor Context + HTTP Basic

Demo minh họa ba điều:

1. `ReactiveSecurityContextHolder` đọc identity đúng ở một HTTP request đã đi qua WebFlux security.
2. Identity vẫn có thể đọc đúng **sau async delay và publishOn**, không dựa vào tên thread.
3. Alice/Bob trong **hai subscriptions khác nhau** không chia sẻ identity; reactive method security xét role trong context.

Đây là ứng dụng **Spring WebFlux**, không trộn `spring-boot-starter-web` (MVC) vào project. Có user in-memory chỉ dùng để học. Ứng dụng thật có thể xác thực bằng OIDC/JWT/IdP; cách lấy `Authentication` từ reactive context vẫn theo nguyên tắc tương tự nhưng principal type và token validation khác.

### 9.1. Phiên bản và cấu trúc

- Java 17+, Spring Boot **3.5.16**, Spring Security **6.5.x** từ Boot BOM, Project Reactor theo BOM.
- Maven 3.9+ hoặc Maven wrapper tương thích.
- Chạy ở localhost, HTTP Basic credential mẫu không dùng trên mạng thật; production cần HTTPS.
- Boot 3.5.16 phát hành ngày **25/06/2026** và là bản OSS cuối dòng 3.5; khi triển khai mới nên chọn dòng Boot còn được hỗ trợ (4.x) và migrate API/test tương ứng.

```text
reactive-security-context-demo/
├── pom.xml
└── src/
    ├── main/java/demo/reactive/ReactiveContextApplication.java
    └── test/java/demo/reactive/
        ├── ReactiveContextHttpTests.java
        └── ReactiveContextUnitTests.java
```

### 9.2. pom.xml đầy đủ

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>reactive-security-context-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 9.3. Java application đầy đủ

Tạo `src/main/java/demo/reactive/ReactiveContextApplication.java`:

```java
package demo.reactive;

import java.time.Duration;
import java.util.Objects;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@SpringBootApplication
public class ReactiveContextApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveContextApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
class ReactiveSecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService reactiveUsers(
            PasswordEncoder passwordEncoder) {

        UserDetails alice = User.withUsername("alice")
            .password(passwordEncoder.encode("lab-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(passwordEncoder.encode("lab-pass"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(alice, admin);
    }

    @Bean
    SecurityWebFilterChain webFluxSecurity(ServerHttpSecurity http) {
        return http
            // Demo API stateless: không khôi phục authentication từ WebSession.
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .pathMatchers(HttpMethod.GET,
                    "/me", "/after-hop", "/role-user")
                    .authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            // CSRF vẫn giữ cấu hình mặc định. Demo chỉ dùng GET.
            .csrf(Customizer.withDefaults())
            .build();
    }
}

@Service
class ReactiveIdentityService {

    Mono<String> currentUsername() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Objects::nonNull)
            .map(Authentication::getName)
            // Giá trị minh họa khi KHÔNG có context trong unit test.
            // Không biến anonymous thành authenticated.
            .defaultIfEmpty("anonymous");
    }

    Mono<String> afterSchedulerHop() {
        return Mono.delay(Duration.ofMillis(10))
            .publishOn(Schedulers.boundedElastic())
            // subscribe vào publisher đọc security context SAU boundary.
            .then(Mono.defer(this::currentUsername))
            .map(name -> "after-hop:" + name);
    }

    @PreAuthorize("hasRole('USER')")
    public Mono<String> onlyUserRole() {
        // Reactive method security đọc Authentication từ Reactor Context.
        return currentUsername().map(name -> "user-only:" + name);
    }
}

@RestController
class ReactiveIdentityController {

    private final ReactiveIdentityService identity;

    ReactiveIdentityController(ReactiveIdentityService identity) {
        this.identity = identity;
    }

    @GetMapping("/public")
    Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping("/me")
    Mono<String> currentUser() {
        return identity.currentUsername()
            .map(name -> "me:" + name);
    }

    @GetMapping("/after-hop")
    Mono<String> afterHop() {
        return identity.afterSchedulerHop();
    }

    @GetMapping("/role-user")
    Mono<String> onlyUserRole() {
        // Đi qua service bean proxy để @PreAuthorize được áp dụng.
        return identity.onlyUserRole();
    }

    @GetMapping("/admin")
    Mono<String> admin() {
        return Mono.just("admin-ok");
    }
}
```

**Đọc đúng ý nghĩa code:**

1. `spring-boot-starter-webflux` và `SecurityWebFilterChain` xác định app là **reactive web stack**. Không dùng `HttpSecurity`, `OncePerRequestFilter` hoặc Servlet `SecurityContextHolder` để quyết định actor trong controller.
2. `MapReactiveUserDetailsService` chỉ là nguồn user học tập, không có database; `BCryptPasswordEncoder` so password. HTTP Basic trên localhost dùng đúng credential do provider kiểm tra; demo không có endpoint tạo admin.
3. `NoOpServerSecurityContextRepository.getInstance()` làm rõ mục đích stateless: không dùng WebSession lưu authentication qua request. Nó **không liên quan** tới `NoOpPasswordEncoder`; một cái là repository không lưu context, cái kia là encoder plaintext nguy hiểm.
4. `ReactiveIdentityService.currentUsername()` trả **Mono**, dùng `ReactiveSecurityContextHolder.getContext()` để lấy authentication của subscriber. Không đọc static field hay `ThreadLocal`.
5. `afterSchedulerHop()` tạo một delay và dùng `publishOn(Schedulers.boundedElastic())` để chuyển execution trước khi đọc context. Vì context truyền theo subscription, identity vẫn đúng.
6. `@EnableReactiveMethodSecurity` và `@PreAuthorize("hasRole('USER')")` hoạt động trên method trả `Mono<String>`. Test sẽ phân biệt Alice (ROLE_USER) và admin (chỉ ROLE_ADMIN). Role không đồng nghĩa mọi quyền.
7. `.formLogin(form -> form.disable())` giúp app này chỉ minh họa HTTP Basic, không redirect form login. `csrf` giữ bật theo mặc định; vì các endpoint demo đều dùng **GET**, test không cần token CSRF. Endpoint ghi dữ liệu trong sản phẩm thật phải đánh giá CSRF threat model riêng.
8. `.anyExchange().denyAll()` chặn route không khai báo. Nếu có nhiều SecurityWebFilterChain cần matcher/order đúng để không rơi vào chain public.
9. `Mono<String>` được return trực tiếp; WebFlux subscribe và quản lý lifecycle. Không gọi `subscribe()`/`block()` trong controller.
10. Mật khẩu `lab-pass` được hard-code cho học tập và là dữ liệu **không bí mật**. Không dùng mã này làm cấu hình production: phải dùng IdP/user store được quản lý, rate limits, TLS, audit và quản lý token/session.

### 9.4. Integration test: WebTestClient xác minh identity qua HTTP

Tạo `src/test/java/demo/reactive/ReactiveContextHttpTests.java`:

```java
package demo.reactive;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment =
    SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveContextHttpTests {

    @Autowired
    WebTestClient client;

    @Test
    void basicAuthenticationUsesRealReactiveUserStore() {
        client.get().uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");

        client.get().uri("/me")
            .exchange()
            .expectStatus().isUnauthorized();

        client.get().uri("/me")
            .headers(h -> h.setBasicAuth("alice", "lab-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("me:alice");

        client.get().uri("/me")
            .headers(h -> h.setBasicAuth("alice", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void identitySurvivesReactorSchedulerSwitch() {
        client.get().uri("/after-hop")
            .headers(h -> h.setBasicAuth("alice", "lab-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("after-hop:alice");

        client.get().uri("/after-hop")
            .headers(h -> h.setBasicAuth("admin", "lab-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("after-hop:admin");
    }

    @Test
    void twoUsersAndAnonymousDoNotShareIdentity() {
        client.get().uri("/me")
            .headers(h -> h.setBasicAuth("alice", "lab-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("me:alice");

        client.get().uri("/me")
            .headers(h -> h.setBasicAuth("admin", "lab-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("me:admin");

        // Stateless request không mang Basic header không nhận user cũ.
        client.get().uri("/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void webAndReactiveMethodAuthorizationAreSeparate() {
        client.get().uri("/admin")
            .headers(h -> h.setBasicAuth("alice", "lab-pass"))
            .exchange()
            .expectStatus().isForbidden();

        client.get().uri("/admin")
            .headers(h -> h.setBasicAuth("admin", "lab-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin-ok");

        client.get().uri("/role-user")
            .headers(h -> h.setBasicAuth("alice", "lab-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("user-only:alice");

        client.get().uri("/role-user")
            .headers(h -> h.setBasicAuth("admin", "lab-pass"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void unlistedEndpointIsNotOpenedByAnAuthenticatedUser() {
        client.get().uri("/unlisted")
            .headers(h -> h.setBasicAuth("alice", "lab-pass"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

**Ý nghĩa test:**

- `WebTestClient` thay cho Servlet `MockMvc`, kiểm tra thật SecurityWebFilterChain của WebFlux trên HTTP port ngẫu nhiên.
- `setBasicAuth` gửi credential như client thực. Các test 200/401 cho biết authentication manager/user store/BCrypt hoạt động; khác với `mockUser()`/`@WithMockUser` chỉ giả lập principal.
- `/after-hop` kiểm tra **Reactor Context vẫn truy cập được sau scheduler hop**. Test không phụ thuộc tên thread nào.
- Alice và admin có authentication khác nhau; request mới không Basic header bị 401 trong demo stateless. Không hề có biến global “current user” nào được giữ lại.
- Test quyền role ở hai lớp: URL `/admin` cần ROLE_ADMIN, service `onlyUserRole` cần ROLE_USER qua `@PreAuthorize`.
- Đây là integration test của lab với username/password mẫu. Production cần thêm negative tests (token validation, tenant/object authorization, login rate limit, log redaction, TLS, cancellation).

### 9.5. Unit test với StepVerifier: hai subscriber dùng cùng source nhưng identity khác nhau

Tạo `src/test/java/demo/reactive/ReactiveContextUnitTests.java`:

```java
package demo.reactive;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class ReactiveContextUnitTests {

    private final ReactiveIdentityService identity =
        new ReactiveIdentityService();

    private static Authentication user(String name) {
        // Chỉ dùng trong unit test. Không phải password authentication thật.
        return new TestingAuthenticationToken(
            name, "unused-test-credential", "ROLE_USER");
    }

    @Test
    void contextIsChosenPerSubscriptionNotPerSourceMono() {
        Mono<String> source = identity.currentUsername();

        StepVerifier.create(source.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                    user("alice"))))
            .expectNext("alice")
            .verifyComplete();

        StepVerifier.create(source.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                    user("bob"))))
            .expectNext("bob")
            .verifyComplete();

        StepVerifier.create(source)
            .expectNext("anonymous")
            .verifyComplete();
    }

    @Test
    void schedulerSwitchDoesNotChangeReactivePrincipal() {
        StepVerifier.create(identity.afterSchedulerHop()
                .contextWrite(
                    ReactiveSecurityContextHolder.withAuthentication(
                        user("alice"))))
            .expectNext("after-hop:alice")
            .verifyComplete();
    }

    @Test
    void concurrentSubscriptionsHaveIndependentSecurityContexts() {
        Mono<String> alice = identity.afterSchedulerHop()
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                    user("alice")));

        Mono<String> bob = identity.afterSchedulerHop()
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                    user("bob")));

        StepVerifier.create(Mono.zip(alice, bob))
            .expectNextMatches(pair ->
                pair.getT1().equals("after-hop:alice")
                && pair.getT2().equals("after-hop:bob"))
            .verifyComplete();
    }

    @Test
    void deferContextualReadsContextAtSubscription() {
        Mono<String> source =
            Mono.deferContextual(ctx ->
                Mono.just(ctx.getOrDefault("lesson.actor", "missing"))
            );

        StepVerifier.create(source
                .contextWrite(ctx -> ctx.put("lesson.actor", "alice")))
            .expectNext("alice")
            .verifyComplete();

        StepVerifier.create(source
                .contextWrite(ctx -> ctx.put("lesson.actor", "bob")))
            .expectNext("bob")
            .verifyComplete();

        StepVerifier.create(source)
            .expectNext("missing")
            .verifyComplete();
    }

    @Test
    void contextWriteOnlyAffectsItsUpstreamPart() {
        Mono<String> source =
            Mono.deferContextual(ctx ->
                Mono.just(ctx.getOrDefault("lesson.trace", "missing"))
            );

        StepVerifier.create(source
                .contextWrite(ctx -> ctx.put("lesson.trace", "T1")))
            .expectNext("T1")
            .verifyComplete();

        Mono<String> downstream =
            Mono.just("start")
                .contextWrite(ctx -> ctx.put("lesson.trace", "T1"))
                .flatMap(x -> source);

        StepVerifier.create(downstream)
            .expectNext("missing")
            .verifyComplete();
    }
}
```

Lưu ý: Các import `Duration` và `Schedulers` được liệt kê có thể được IDE đánh dấu unused trong file test vì việc chuyển scheduler nằm trong `ReactiveIdentityService.afterSchedulerHop()`; xóa unused imports nếu dự án bật strict lint. Các method JUnit vẫn hợp lệ về mặt mô hình.

**Điều unit test chứng minh:**

1. **Cùng một Mono source** có thể được subscribe ba lần với context Alice/Bob/rỗng; nó không giữ “current user” trong một field singleton.
2. `ReactiveSecurityContextHolder.withAuthentication(...)` đặt **test authentication** vào subscription; đây là cách test identity propagation, không phải chứng minh password thật.
3. `StepVerifier` giúp assert Mono hoàn tất đúng; nó không cần tự `block()` trong code controller.
4. Hai subscriptions dùng `Mono.zip` được chạy đồng thời theo thiết kế scheduler của source; chúng có thể dùng chung worker pool nhưng phải giữ identity đúng **theo subscription**, không theo thread.
5. `contextWrite` bổ sung key cho **upstream**; test downstream thấy `missing` để ngăn hiểu sai thứ tự.
6. Không cần dựa vào `Thread.currentThread().getName()` hoặc giấc ngủ tùy ý để kết luận identity.

### 9.6. Chạy Maven và thử curl

Từ thư mục dự án:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

Kỳ vọng khi các dependency/JDK phù hợp:

- `mvn test` thực hiện WebTestClient HTTP tests và StepVerifier unit tests.
- `GET /public` không cần Basic authentication → HTTP 200, body `public`.
- `GET /me` không credential → 401.
- `GET /me` của Alice → 200, `me:alice`.
- `GET /after-hop` của Alice → 200, `after-hop:alice`.
- `GET /after-hop` của admin → 200, `after-hop:admin`.
- `GET /admin` của Alice → 403; của admin → 200.
- `GET /role-user` của Alice → 200, của admin chỉ có ROLE_ADMIN → 403.
- `GET /me` ngay sau request được xác thực nhưng không mang Basic header → 401.

Đây là **kết quả kỳ vọng của mã**, không phải tuyên bố đã chạy Maven trong môi trường biên soạn.

Ở terminal thứ hai, chỉ trên localhost:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u alice http://localhost:8080/me
curl -i -u alice http://localhost:8080/after-hop
curl -i -u admin http://localhost:8080/after-hop
curl -i -u alice http://localhost:8080/admin
curl -i -u admin http://localhost:8080/admin
```

`curl -u alice`/`-u admin` sẽ hỏi mật khẩu; nhập `lab-pass` trên máy học. Không đặt password trong command line, chia sẻ trong logs hoặc gửi HTTP Basic ngoài localhost không có HTTPS. Trên PowerShell cũ có thể cần dùng `curl.exe`.

## 10. Vì sao WebTestClient và StepVerifier bổ sung cho nhau?

| Câu hỏi cần chứng minh | WebTestClient | StepVerifier |
| --- | --- | --- |
| HTTP Basic password đúng/sai được provider xác minh | **Có** | Không nếu dùng test token |
| URL role policy có trả đúng 200/401/403 | **Có** | Có thể test method security riêng |
| WebFlux security filter thiết lập context đúng | **Có** | Chỉ test source/context do test cấp |
| Context theo từng subscription | Gián tiếp qua requests | **Trực tiếp** qua contextWrite |
| Đổi scheduler không làm đổi identity | **Có** với endpoint async | **Có** với Mono trong unit test |
| Hai subscriber có context riêng | Test nhiều request | **Có** với Mono.zip/contextWrite |
| Không có context phải không cấp quyền | **Có** qua 401/403 | Test empty/default behavior |
| CSRF/session/OIDC/JWT production policy | Cần test riêng | Không đủ |
| Không lộ tenant/object thuộc user khác | Cần app/domain tests | Có thể test service/repository reactive |

`@WithMockUser`/`mockUser()` trong Spring Security reactive testing cũng hữu ích để test role policy, nhưng nó **không chứng minh** password authentication thật. Trong bài này HTTP test cố tình gửi Basic credentials để kiểm tra trọn đường xác thực.

## 11. Các lỗi thiết kế dễ xảy ra

### 11.1. Lưu Authentication trong field của singleton service

```java
// PHẢN VÍ DỤ NGUY HIỂM.
@Service
class WrongIdentityService {
    private Authentication lastAuthentication;
}
```

Bean `@Service` mặc định là singleton; field có thể bị nhiều requests/subscriptions đọc/ghi cùng lúc. Đừng lưu “current user” như mutable global state. Dùng reactive context hoặc truyền actor ID được xác minh vào method.

### 11.2. Dựa vào ThreadLocal ở mọi map()

```java
// PHẢN VÍ DỤ:
flux.map(item -> {
    String actor = THREAD_LOCAL_CURRENT_USER.get();
    return loadFor(actor, item);
});
```

Nếu `THREAD_LOCAL_CURRENT_USER` là context tùy chỉnh không được propagate đúng, `actor` có thể null hoặc sai. Dù bridge Micrometer có mặt, phải có contract/registration/cleanup rõ. Với identity Spring Security WebFlux, nên dùng `ReactiveSecurityContextHolder.getContext()` trước rồi `flatMapMany`/`flatMap` với trusted actor.

### 11.3. Dùng Context key từ client làm role

```java
// PHẢN VÍ DỤ: roles từ request body không phải authentication đáng tin.
return service.run()
    .contextWrite(ctx -> ctx.put("role", request.getRole()));
```

Reactor Context không kiểm chữ ký của một role string. Chỉ đặt metadata được chứng thực từ filter/identity mechanism; authorization vẫn phải dùng trusted `Authentication` và domain policy.

### 11.4. Context biến mất sau nested subscribe()

Sửa bằng composition `flatMap`/`then`/`concatMap` thay vì `subscribe()` lồng nhau. Nếu fire-and-forget thật sự cần thiết, tạo job boundary rõ, message envelope và authorization/retry riêng.

### 11.5. Context có vẻ đúng trong test nhưng production mất

Một test unit có thể chạy mọi operator trên cùng thread, vô tình dựa vào `ThreadLocal`. Thêm tests với `delayElement`/`publishOn`, hai subscriber khác nhau và HTTP requests xen kẽ. Không assert thread name, assert **identity và authority**.

### 11.6. Đổi sang MODE_INHERITABLETHREADLOCAL

Một worker thread được tạo khi Alice đang authenticated có thể kế thừa context Alice, sau đó bị tái sử dụng cho Bob; đây không phải propagation theo subscription. Không đặt chiến lược toàn JVM chỉ để tránh dùng `ReactiveSecurityContextHolder`.

### 11.7. Chuyển blocking JDBC lên event-loop

`JdbcTemplate` là blocking; dùng trực tiếp trong `map` trên Netty event-loop dễ gây nghẽn. Sử dụng R2DBC hoặc bọc blocking operations qua `Schedulers.boundedElastic()` cùng resource limits; truyền actor/tenant ID rõ ràng và kiểm domain authorization ở nơi truy vấn.

### 11.8. Cho rằng Context giúp session persist

`ReactiveSecurityContextHolder` trả identity cho chain hiện tại. Đăng nhập tồn tại giữa các HTTP requests cần cơ chế repository/session/token phù hợp, không chỉ `contextWrite`. Trong demo Basic stateless, mỗi request cần Authorization header.

### 11.9. Cho rằng authenticated luôn đủ quyền

Login đúng chỉ cho biết ai; role/method policy và object authorization vẫn cần được áp dụng. Với anonymous authentication, một `Authentication` có thể tồn tại; đừng tự viết `auth.isAuthenticated()` như điều kiện duy nhất để cấp thao tác nhạy cảm.

### 11.10. Log cả SecurityContext để debug

`Authentication`/principal có thể chứa claims/metadata nhạy cảm; không log raw credentials, Basic header, bearer token, cookie, tenant secret. Audit nên ghi actor ID ổn định, action, outcome và correlation ID; không lấy tên thread làm actor.

### 11.11. Cache publisher theo một key global

Nếu publisher tạo ra response dựa vào current principal rồi `cache()` trong singleton, result của user đầu có thể được trả lại cho user sau. Không cache cross-user response theo một key không chứa actor/tenant/permission/expiry. Reactive context đúng không chữa sai lầm cache scope.

### 11.12. Cho rằng Reactor Context tự trao quyền cho remote service

Một downstream HTTP request cần chính nó được xác thực (ví dụ qua OAuth2 token relay có policy) và authorize theo resource. Reactor Context của upstream không tự vượt qua network boundary thành một identity được remote service tin cậy.

## 12. Reactive method security và danh tính ở service

Spring Security reactive hỗ trợ `@EnableReactiveMethodSecurity` và `@PreAuthorize` trên phương thức trả reactive publisher:

```java
@Service
class PurchaseService {
    @PreAuthorize("hasAuthority('PURCHASE_READ')")
    public Mono<Purchase> getPurchase(String purchaseId) {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .flatMap(authentication ->
                repository.findOwnedPurchase(
                    purchaseId,
                    stableActorId(authentication)
                )
            );
    }
}
```

Đây là **snippet thiết kế**, không phải chương trình độc lập: `Purchase`, `repository` và `stableActorId` là thành phần tùy ứng dụng. Ý nghĩa:

- Method security lấy trusted authentication từ reactive context, không dùng static ThreadLocal.
- Authority `PURCHASE_READ` được kiểm tra.
- Repository/Service kiểm ownership của purchase theo actor ID/tenant để tránh BOLA.
- Return type `Mono` giúp Spring Security gắn policy vào reactive pipeline.
- Không gọi `block()` rồi trả `Purchase` đồng bộ từ event-loop.
- Actor ID ổn định nên được lấy từ principal/claims **đã xác minh**, không từ query param để người gọi chọn thay người khác.

Nếu một method annotated bị gọi bằng **self-invocation** bên trong chính object thay vì qua Spring proxy, interception có thể không chạy. Vì vậy tách security-sensitive service và test integration của proxy/method, đừng dựa vào annotation chỉ vì nhìn thấy trong source.

## 13. Khi nào vẫn có chỗ cho ThreadLocal trong hệ thống reactive?

ThreadLocal không “bị cấm” tuyệt đối. Nó vẫn được dùng hợp lý trong nhiều thư viện imperative như logging MDC, metrics, JDBC transaction management hoặc legacy SDK. Nhưng cần định rõ:

1. Context nào thuộc subscriber, context nào thuộc thread?
2. Nếu phải bridge, có `ThreadLocalAccessor` và chế độ Reactor Context Propagation được thiết lập/test không?
3. Có **cleanup/reset** đúng khi scheduler worker tái sử dụng không?
4. Có logic nào coi ThreadLocal là bằng chứng quyền dù nó chỉ do logging framework thiết lập không?
5. Có scope nào chuyển sang raw thread/CompletableFuture/SDK callback nằm ngoài Reactor không?
6. Nếu propagation mất, application **fail closed** chứ không dùng identity mặc định nhiều quyền?
7. Có benchmark overhead và error/cancellation/concurrent subscriptions không?

**Quy tắc chọn:** Metadata chỉ phục vụ observability có thể bridge sang MDC có kiểm soát; quyết định ai được thao tác dữ liệu vẫn dựa vào trusted identity của cơ chế xác thực, Reactor Context/authorization policy và kiểm tra domain.

## 14. Ma trận kiểm thử thiết yếu

| Tình huống | Điều cần xác minh |
| --- | --- |
| Anonymous GET protected | 401 hoặc redirect theo authentication entry point |
| Alice password đúng | HTTP 200, name Alice |
| Alice password sai | HTTP 401 |
| Admin vào URL chỉ cho admin | 200 |
| Alice vào URL admin | 403 |
| Alice vào method cần ROLE_USER | 200 |
| Admin không có ROLE_USER vào method đó | 403 |
| Alice qua Mono.delay + publishOn | Vẫn đọc Alice bằng ReactiveSecurityContextHolder |
| Bob qua cùng endpoint/scheduler | Vẫn đọc Bob, không thấy Alice |
| Request sau không Basic header | Không nhận identity request trước |
| Cùng Mono source, subscribe dưới context Alice rồi Bob | Mỗi subscription thấy đúng user |
| Cùng Mono source, subscribe không context | Không thấy user của subscription khác |
| Concurrent Mono.zip Alice/Bob | Hai authentication độc lập |
| deferContextual và contextWrite | Key đúng upstream, đúng thời điểm subscribe |
| contextWrite đặt trước flatMap downstream | Downstream không mặc định nhận key của upstream |
| Nested subscribe() | Không được coi là propagation của HTTP request; test refactor |
| Blocking bridge to JDBC | Chạy boundedElastic hoặc dùng R2DBC, ownership vẫn được xét |
| Cache theo user | Không trả data từ actor khác |
| Micrometer automatic mode | Không rò giá trị khi context rỗng và callback khác |
| WebClient downstream | Không tự tin header caller, dùng token relay đúng protocol |
| JWT/OIDC principal | Không cast nhầm UserDetails, validate issuer/audience/signature |
| Cancellation/exception | Không lộ context và resource giữa subscriptions |

**Đừng chỉ test “có cùng thread thì đúng”.** Cần test **subscription A rồi B**, hai subscribers chạy đồng thời và đổi scheduler. Khi lỗi khó tái hiện, tăng độ phủ bằng stress/integration tests và đo các tín hiệu security audit có redaction; không thêm `Thread.sleep` ngẫu nhiên để “ép” race.

## 15. Câu hỏi tự đánh giá

**Câu 1.** `ThreadLocal` thuộc về thread hay HTTP request?

**Đáp án:** Thuộc về **thread**. Servlet filter có thể quản lý scope gần tương ứng request đồng bộ, còn reactive pipeline không ràng buộc một thread duy nhất cho một subscription.

**Câu 2.** Trong WebFlux, vì sao `SecurityContextHolder.getContext()` không phải lựa chọn mặc định để đọc user?

**Đáp án:** Spring Security WebFlux lưu/truyền security context theo **Reactor Context** và `ReactiveSecurityContextHolder`. ThreadLocal không có hợp đồng gắn với subscriber khi scheduler đổi hoặc thread bị tái sử dụng.

**Câu 3.** `Mono.defer(...)` có giải quyết sai lầm lấy user từ ThreadLocal không?

**Đáp án:** Không. Nó chỉ trì hoãn tính giá trị tới lúc subscription; không chuyển nguồn dữ liệu từ thread sang subscriber. Phải dùng `deferContextual`/`ReactiveSecurityContextHolder`.

**Câu 4.** `contextWrite` hoạt động theo hướng nào?

**Đáp án:** Nó bổ sung context cho operator **upstream** từ chỗ nó được đặt; context được chuyển dọc subscription, không đơn thuần truyền xuôi theo kết quả của `map`.

**Câu 5.** Nếu Alice đổi từ event-loop sang boundedElastic sau `publishOn`, có cần biến global currentUser không?

**Đáp án:** Không. Mono/Flux được compose đúng sẽ giữ Reactor Context trong subscription; `ReactiveSecurityContextHolder.getContext()` lấy đúng Alice.

**Câu 6.** Có một ThreadLocalAccessor/Micrometer tự động khôi phục giá trị, vậy có thể dùng ThreadLocal làm nguồn duy nhất cho authorization không?

**Đáp án:** Không nên. Bridge có điều kiện theo registration, scope và cleanup. Reactor Context/verified authentication mới là nguồn đúng của WebFlux; authorization vẫn phải theo policy.

**Câu 7.** Vì sao gọi `subscribe()` bên trong `flatMap`/`map` là đáng nghi?

**Đáp án:** Nó tạo một subscription độc lập, làm đứt composition của context, error, cancellation và lifecycle. Nên return/compose publisher; nếu cần background job thật, dùng task boundary riêng.

**Câu 8.** Cùng một `Mono` được hai subscriber Alice và Bob subscribe, có cần một Mono singleton chứa field currentUser không?

**Đáp án:** Không. Context nằm ở mỗi subscription, nên cùng source có thể phục vụ nhiều actor mà không dùng mutable global field.

**Câu 9.** Nếu `ReactiveSecurityContextHolder.getContext()` trả empty, nên tự tạo admin principal để service khỏi lỗi không?

**Đáp án:** Tuyệt đối không. Với endpoint được bảo vệ, thiếu authentication cần bị từ chối hoặc dẫn tới flow xác thực phù hợp; fail closed.

**Câu 10.** Dùng Reactor Context đúng có tự kiểm quyền sở hữu hóa đơn/đơn hàng không?

**Đáp án:** Không. Nó cung cấp danh tính, còn service/repository phải kiểm actor + action + resource/tenant và trạng thái nghiệp vụ.

**Câu 11.** `NoOpServerSecurityContextRepository` trong WebFlux demo có nghĩa password được so plaintext không?

**Đáp án:** Không. Đây là repository **không lưu security context qua request**, khác hoàn toàn `NoOpPasswordEncoder`; password trong demo vẫn được hash bằng BCrypt.

**Câu 12.** Nếu backend gọi WebClient sang service khác, service đó có tự nhận Reactor Context của upstream như credentials không?

**Đáp án:** Không. Mỗi service có trust boundary riêng; dùng OAuth2 token relay hoặc cơ chế machine-to-machine authentication thích hợp, không gửi username thuần và coi là xác thực.

## 16. Checklist khi review code WebFlux

- [ ] Dự án thật sự dùng WebFlux (`spring-boot-starter-webflux`), không nhầm MVC và reactive adapters?
- [ ] Dùng `SecurityWebFilterChain`/`ServerHttpSecurity` cho WebFlux, không dùng Servlet `SecurityFilterChain`?
- [ ] Authentication mechanism có xác minh credentials/JWT/OIDC đúng theo provider/decoder?
- [ ] Các reactive service đọc danh tính từ `ReactiveSecurityContextHolder` hoặc nhận actor ID đã xác minh?
- [ ] Không dùng `SecurityContextHolder.getContext()` ThreadLocal làm “current user” mặc định trong `map`/`flatMap`?
- [ ] Không lưu `Authentication`/tenant/role trong static field hoặc singleton mutable field?
- [ ] Không gọi `Mono.just(ThreadLocal.get())` rồi cache identity ở assembly time?
- [ ] Không tự gọi `subscribe()` lồng nhau, không `block()` trên event-loop?
- [ ] Biết `contextWrite` ảnh hưởng upstream, còn `Mono.deferContextual` đọc khi subscription?
- [ ] Có test scheduler hops (`publishOn`/delay) và ít nhất hai subscribers khác identity?
- [ ] HTTP tests dùng `WebTestClient` với password thật và 401/403/200, ngoài mock auth tests?
- [ ] Có `@EnableReactiveMethodSecurity` và các method quan trọng trả `Mono`/`Flux` phù hợp?
- [ ] Domain ownership/tenant check áp trên resource thực, không chỉ `authenticated()`?
- [ ] Khi gọi blocking SDK/DAO, dùng boundedElastic/resource limits hoặc chuyển sang reactive driver?
- [ ] Khi đẩy job sang queue, có trusted actor metadata + reauthorization, không giữ stale session?
- [ ] Nếu dùng Micrometer context-propagation, đã test registered accessors, cleanup và overhead?
- [ ] Không coi Reactor Context là session repository, và không coi `contextWrite` là token relay?
- [ ] Không chia sẻ cached user-specific Mono/Flux cho mọi account không có key/phạm vi?
- [ ] Không log raw Authentication, password, JWT, session cookie hoặc headers nhạy cảm?
- [ ] Có cập nhật Boot/Security/Reactor version được hỗ trợ, kiểm thử sau migration?

## 17. Tóm tắt ngắn để ghi nhớ

1. **ThreadLocal gắn với thread; Reactor Context gắn với subscriber/subscription.** Vì reactive chain có thể đổi thread và dùng lại pool, không thể dùng ThreadLocal để suy ra identity xuyên chain.
2. **ReactiveSecurityContextHolder.getContext()** là API chính để đọc Spring Security context trong WebFlux service, không phải Servlet `SecurityContextHolder.getContext()`.
3. **contextWrite bổ sung context cho upstream**, `deferContextual` đọc context tại subscription. Không hiểu nó như việc set một biến toàn cục.
4. **publishOn/subscribeOn đổi scheduling, không quyết định actor** nếu pipeline giữ đúng Reactor Context. Test identity chứ không test tên thread.
5. **Nested subscribe(), block(), raw Executor và global cache** có thể phá lifecycle/context hoặc làm rò dữ liệu; compose reactive operators và truyền actor rõ ràng qua bridge.
6. **Micrometer context propagation có thể tạm khôi phục ThreadLocal**, nhưng đây là cơ chế tương thích có cấu hình, không phải lý do để thay đổi trust model.
7. **Reactive method security và domain authorization vẫn bắt buộc**; authentication đúng không đồng nghĩa có quyền với mọi record.
8. **WebTestClient + StepVerifier** kiểm tra cả HTTP security thật và hai subscriptions khác identity, không chỉ một request chạy thành công.

## Tài liệu tham khảo chính thức

- [Spring Security 6.5 — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security 6.5 — EnableReactiveMethodSecurity](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [Spring Security 6.5 — Reactive Authentication](https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/index.html)
- [Spring Security 6.5 — Security Context in Reactive Applications](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [Spring Security 6.5 — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html)
- [Spring Security 6.5 — Testing Reactive Authentication](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html)
- [Spring Security 6.5 — Servlet Authentication Architecture (để so sánh ThreadLocal)](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Project Reactor 3 — Reactor Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [Project Reactor 3 — Context-Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html)
- [Reactor Mono Javadoc — contextWrite](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
- [Spring Boot 3.5.16 release, 25/06/2026](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)
