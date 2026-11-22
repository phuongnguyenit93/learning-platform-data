# Truyền ngữ cảnh qua Reactor Context thay cho giả định về ThreadLocal trong Streaming WebFlux

## 1. Bài toán: một request đi qua nhiều thread nhưng phải giữ đúng ngữ cảnh

Trong Spring MVC đồng bộ, một request có thể được xử lý liên tục trên một Servlet worker thread. Vì vậy mã cũ thường lưu correlation ID, người dùng hiện tại, locale hoặc MDC vào `ThreadLocal` rồi đọc lại ở mọi phương thức trên cùng thread. **Spring WebFlux không cam kết một request chỉ chạy trên một Java thread**. HTTP callback của Reactor Netty, toán tử `publishOn`, `subscribeOn`, `flatMap` với nguồn bất đồng bộ, `Mono.delay`, WebClient và reactive data driver có thể chạy tiếp ở các execution contexts khác nhau.

Tình huống thực tế:

```text
Client GET /api/events X-Request-Id: req-A
    │
    ▼
reactor-http-nio-2           tiếp nhận HTTP, tạo chuỗi Mono/Flux
    │
    ├── WebClient gửi remote request không block
    └── Mono.delay(...)      đợi timer mà không chiếm worker thread
                 │
                 ▼
parallel-1                  dữ liệu đến, pipeline tiếp tục
                 │
                 ├── đọc ThreadLocal: không bảo đảm thấy req-A
                 └── đọc Reactor Context: có thể thấy req-A nếu
                      toàn chuỗi có contextWrite đúng vị trí
                 │
                 ▼
reactor-http-nio-3          ghi thêm HTTP/SSE body
```

Tên thread chỉ minh họa. Không dựa vào tên/số lượng event-loop threads để thiết kế chức năng. Với **Reactor Context**, request metadata đi cùng chuỗi tín hiệu thông qua **subscription**, không bị phụ thuộc một thread nhất định. Điều này đặc biệt quan trọng trong bài **Streaming WebFlux** khi một Flux có thể sống lâu, trải qua các scheduler, nhiều callback và bị client hủy.

### 1.1. Mục tiêu học tập

Sau bài này bạn có thể:

1. Phân biệt `ThreadLocal` gắn với Java thread và `Context` gắn với từng **Reactor Subscriber/subscription**.
2. Dùng `contextWrite`, `Mono.deferContextual`, `Flux.deferContextual`, `Context` và `ContextView` theo đúng hướng propagation.
3. Giải thích vì sao `contextWrite` đặt cuối source code thường được thực thi **trước khi upstream phát onNext**, và tại sao đổi thứ tự operators làm thay đổi giá trị đọc được.
4. Kiểm soát phạm vi ghi đè context trong `flatMap`, `concatMap` và nested publishers, tránh rò rỉ context giữa các requests/tenants.
5. Đưa correlation ID từ WebFlux `WebFilter` vào Reactor Context và đọc trong service, kể cả sau `Mono.delay` và `subscribeOn`.
6. Hiểu việc đọc Reactor Context trong SSE/Flux: context cần cho từng event, cancellation và cả error path.
7. Phân biệt native Reactor Context với Micrometer Context Propagation/MDC/ThreadLocal bridge ở chế độ default và automatic.
8. Không coi một header do client tự khai là authentication, không đưa secrets vào logs hoặc context dùng chung.
9. Tạo dự án Spring Boot 3/Java 17 chạy được, có WebFilter, service, controller, WebTestClient và StepVerifier tests.
10. Debug các trường hợp “context missing”, request ID lẫn nhau, callback chạy ngoài chuỗi và reactive security principal không tồn tại.

**Phạm vi:** Spring Framework 6.x, Project Reactor 3.6.x / Spring Boot 3.3.x, Java 17+. Bài học không khẳng định mọi ThreadLocal đều biến mất trong WebFlux: có các cơ chế tự động khôi phục được cấu hình, nhưng chúng **không thay đổi nguyên tắc lõi** rằng một reactive pipeline không sở hữu một thread cố định.

## 2. Tư duy đúng về ThreadLocal và Context

### 2.1. ThreadLocal: giá trị nằm trong ngữ cảnh của thread đang chạy

Ví dụ imperative:

```java
private static final ThreadLocal<String> REQUEST_ID =
        new ThreadLocal<>();

static void handleRequest() {
    REQUEST_ID.set("req-123");
    try {
        callBusinessFunction(); // nếu cùng thread, get() thấy req-123
    } finally {
        REQUEST_ID.remove(); // cực kỳ quan trọng với thread pool
    }
}
```

`ThreadLocal.get()` truy cập trạng thái của **current Java Thread**. Nó không đi cùng một logical request khi công việc được chuyển sang executor/scheduler khác. Với thread pool reused, quên `remove()` còn có thể làm dữ liệu cũ rò rỉ sang một request khác.

Trong MVC đồng bộ, pattern set→get→remove có thể hợp lý nếu code và framework quản lý scope rõ. Trong WebFlux, dù một callback được gọi lại “trên cùng thread” tình cờ, đó **không phải contract** mà business code được dựa vào.

### 2.2. Reactor Context: giá trị nằm theo Subscriber

`reactor.util.context.Context` là một key-value container **immutable (mỗi mutation tạo Context mới)** liên kết với một subscription. Operators upstream có thể truy cập ngữ cảnh được downstream `Subscriber` cung cấp.

Các đặc điểm:

- Key/value không được là `null`; context không phải Map mutable chung.
- Mỗi thao tác `put`/`delete` tạo một bản ngữ cảnh logic mới.
- Có thể dùng String key, class/object key hoặc key chuyên biệt; nên namespace để tránh collisions.
- `ContextView` chỉ cung cấp đọc: `get`, `getOrDefault`, `hasKey`, `stream`.
- `Context` cung cấp thao tác tạo bản mới: `put`, `delete`, `putAll`.
- Dữ liệu truy cập được tại **subscription time / trong reactive chain**, không phải ở mọi đoạn synchronous code chạy ngoài reactive chain.
- Không bảo đảm truyền vào bất kỳ `ExecutorService`, `CompletableFuture`, external callbacks hoặc library khác chỉ vì bạn return Mono ở tầng ngoài.

**Khác nhau về nơi gắn state:**

| Chủ đề | ThreadLocal | Reactor Context |
| --- | --- | --- |
| Thuộc về | Java Thread đang chạy | Subscriber/subscription |
| Cross-thread | Không tự chuyển | Có thể truy cập qua Reactor operators khi context propagate |
| Lifecycle | Thread và explicit cleanup | Subscription/reactive chain |
| Mutability | ThreadLocal.set thay giá trị | Context bất biến, trả bản mới |
| Isolation giữa requests | Phụ thuộc set/remove và thread reuse | Theo subscription/context boundary |
| Cách đọc | `THREAD_LOCAL.get()` | `Mono.deferContextual(ctx -> ...)` |
| Cách ghi | `THREAD_LOCAL.set(x)` | `publisher.contextWrite(ctx -> ctx.put(key,x))` |
| Khả năng dùng với non-Reactor callback | Trực tiếp nếu cùng thread | Cần bridge/contextSnapshot/explicit arguments |
| Rủi ro | Leak, stale value, lost propagation | Sai thứ tự operator, context bị mất ngoài chain, key collision |

Không coi Reactor Context như một “global map” để lấy ở bất kỳ function nào. Nó được định hướng **subscriber context**, nên đọc đúng thông qua Reactor APIs.

### 2.3. Phân biệt ba đối tượng

- `Context`: interface đọc/ghi *bất biến về mặt semantic*; các methods `put` tạo instance mới.
- `ContextView`: interface **read-only**; loại được `deferContextual` truyền cho lambda.
- `ContextSnapshot` của Micrometer: **khác** Reactor Context, dùng để capture/restore các context mechanisms như ThreadLocal từ/đến registered accessors.

Ví dụ:

```java
Context original = Context.of("traceId", "A");
Context updated = original.put("tenantHint", "tenant-1");

System.out.println(original.hasKey("tenantHint")); // false
System.out.println(updated.hasKey("tenantHint"));  // true
```

Đây là snippet với `reactor.util.context.Context` import; trong dự án Java có Reactor dependency thì stdout của hai dòng là `false` và `true`. Lưu ý `tenantHint` chỉ là dữ liệu minh họa, **không** dùng một tenant ID do client tự khai làm bằng chứng authorization.

## 3. Cách ghi context: contextWrite

`contextWrite` là API thường dùng để làm phong phú ngữ cảnh của các operators **upstream**.

```java
Mono<String> pipeline =
    Mono.deferContextual(ctx ->
        Mono.just("trace=" + ctx.get("traceId")))
        .contextWrite(Context.of("traceId", "req-A"));
```

Khi `pipeline` được subscribe, giá trị kết quả là:

```text
trace=req-A
```

`contextWrite(ContextView)` gộp context mới với downstream context; `contextWrite(Function<Context,Context>)` cho phép tạo context bằng logic merge/replace.

```java
Mono<String> result =
    Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("traceId", "absent")))
      .contextWrite(ctx -> ctx.put("traceId", "req-A"));
```

Nên giữ context value nhỏ, immutable hoặc thread-safe. Không nhét nguyên HTTP request body, large lists, EntityManager, mutable Servlet request, unbounded buffers hoặc token/secret thừa vào Context.

### 3.1. Vì sao contextWrite ở cuối mã nguồn lại có hiệu lực bên trên?

Một pipeline thường được đọc theo **assembly order** từ trên xuống, nhưng subscription đi ngược chiều:

```text
Source / Mono.deferContextual          ── tạo giá trị
       ↑ context nhìn thấy từ downstream
.map(...)                               ── xử lý item
       ↑
.contextWrite(key=value)                ── ghi context cho upstream
       ↑ subscription tiến từ dưới lên
Subscriber / WebFlux HTTP writer
```

Vì vậy code:

```java
Mono.deferContextual(ctx -> Mono.just(ctx.get("k")))
    .contextWrite(Context.of("k", "v"));
```

có thể đọc `v`. Nhưng chuyển `contextWrite` **lên trước** một `flatMap` đọc context phía dưới nó có thể làm flatMap đó không nhìn thấy giá trị.

### 3.2. Ví dụ sai vị trí operator

```java
Mono<String> wrong = Mono.just("value")
    .contextWrite(ctx -> ctx.put("k", "inside"))
    .flatMap(x -> Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("k", "missing"))));
```

Kết quả mong đợi: **missing**. Vì `flatMap` nằm downstream của `contextWrite`; context write đó chỉ tác động upstream.

Sửa:

```java
Mono<String> right = Mono.just("value")
    .flatMap(x -> Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("k", "missing"))))
    .contextWrite(ctx -> ctx.put("k", "inside"));
```

Kết quả: **inside**. Hai đoạn trên là mã có thể đặt trong method Java có Reactor imports, kết quả xác minh bằng StepVerifier (mục 14).

### 3.3. Ghi đè cùng key: vị trí quyết định giá trị

```java
Mono<String> result =
    Mono.deferContextual(ctx ->
        Mono.just(ctx.get("language")))
       .contextWrite(ctx -> ctx.put("language", "vi"))
       .contextWrite(ctx -> ctx.put("language", "en"));
```

Kết quả: **vi**. Hai operators ghi cùng key; đối với source, `contextWrite(vi)` gần source hơn và override `en`. Giá trị `en` có thể vẫn được thấy bởi operators ở giữa/downstream, tùy phạm vi.

Không thiết kế security bằng việc “ghi đè role/tenant” ở một inner publisher chưa được kiểm tra. Context không phải auth barrier; authoritative user/tenant phải đến từ Spring Security/context đáng tin.

### 3.4. Chỉ một subscriber có một context view cụ thể

Một publisher cold có thể được subscribe nhiều lần với contexts riêng:

```java
Mono<String> source =
    Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("requestId", "missing")));

Mono<String> a =
    source.contextWrite(Context.of("requestId", "req-A"));
Mono<String> b =
    source.contextWrite(Context.of("requestId", "req-B"));
```

`a` cho req-A, `b` cho req-B. Không cần lưu requestId trong static field hay mutate một shared Context.

## 4. Đọc context đúng cách: deferContextual và ContextView

`Mono.deferContextual` tạo inner Mono dựa trên `ContextView` của subscription hiện tại. `Flux.deferContextual` cũng có cơ chế tương tự cho Flux.

```java
Mono<String> currentRequestId() {
    return Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("requestId", "anonymous")));
}
```

Không gọi `Mono.just(Context.of(...).get(...))` để lấy context hiện tại; bạn vừa tự tạo map mới không liên quan subscriber. Cũng không có hàm static phổ quát `ReactorContext.current()` hoạt động tùy nơi như `ThreadLocal.get()`.

### 4.1. Đọc trong một operator asynchronous

```java
Mono<String> result =
    Mono.delay(Duration.ofMillis(10))
        .flatMap(tick ->
            Mono.deferContextual(ctx ->
                Mono.just("trace=" +
                    ctx.getOrDefault("traceId", "none"))))
        .contextWrite(Context.of("traceId", "req-42"));
```

Sau timer chạy, inner `Mono.deferContextual` vẫn nhận context của subscription. Kết quả là `trace=req-42`. Không test bằng tên thread như “parallel-1” vì scheduler pool size/name có thể thay đổi.

### 4.2. Khi nào get, getOrDefault, hasKey?

- `ctx.get(key)`: yêu cầu key phải tồn tại; nếu không, thường ném `NoSuchElementException`.
- `ctx.getOrDefault(key, fallback)`: phù hợp với metadata tùy chọn như correlation ID.
- `ctx.hasKey(key)`: kiểm tra sự hiện diện.
- `ctx.getOrEmpty(key)`: cách lấy optional value khi phù hợp API.
- `ctx.stream()`: chỉ dành cho diagnostics cực kỳ kiểm soát; không dump toàn context ra logs vì có thể chứa auth/tracing values.

Với bắt buộc security principal, **không dùng fallback “admin”** khi thiếu key. Context missing có thể là lỗi authorization hoặc bug propagation; xử lý fail-closed.

### 4.3. Key String hay Object?

```java
public final class Keys {
    public static final String TRACE_ID = "example.trace-id";
    private Keys() {}
}
```

Chuỗi có namespace tránh va chạm khi dùng chung libraries. Nếu muốn type-safety và chống collisions tốt hơn, có thể dùng `private static final Object TRACE_KEY = new Object()` và dùng object đó làm key; nhưng phải chia sẻ chính **cùng object key** qua các class đọc/ghi.

**Không** tạo `new Object()` mỗi lần đọc/ghi, vì key identity không khớp. Dự án demo bên dưới dùng string constant để dễ quan sát/test.

## 5. Lợi ích trong Streaming WebFlux: nhiều onNext, một context

Một `Flux` SSE có thể phát ba sự kiện hoặc hoạt động nhiều phút. Context gắn với subscription của client; mỗi event có thể đọc cùng correlation ID.

```java
Flux<String> events =
    Flux.interval(Duration.ofMillis(100))
        .take(3)
        .concatMap(n ->
            Mono.deferContextual(ctx ->
                Mono.just(ctx.get("traceId") + ":" + n)))
        .contextWrite(Context.of("traceId", "stream-A"));
```

Khi complete bình thường, các items là:

```text
stream-A:0
stream-A:1
stream-A:2
```

Vì `Flux.interval` phát nhịp scheduler khác, `ThreadLocal.get()` không bảo đảm cùng giá trị như lúc HTTP request bắt đầu. Nhưng `deferContextual` phía inner publisher được compose trong chain thấy context của subscriber.

### 5.1. Một client không được đọc nhầm request ID của client khác

Giả sử A gửi `X-Request-Id: A` và B gửi `X-Request-Id: B`. Nếu dùng static mutable field:

```java
// ANTI-PATTERN — request A/B có thể ghi đè nhau.
static String currentRequestId;
```

thì events của A có thể hiển thị B. Với Reactor Context, filter thiết lập key **cho từng subscriber**, khi các signals xen kẽ nhau context vẫn tách biệt theo subscription.

**Tuy nhiên:** một publisher hot/shared có thể cần thiết kế scope riêng. Nếu tạo một `Flux.share()` ở singleton service với context từ request đầu tiên, không suy rằng context của các subscribers sau sẽ tự được áp chính xác cho upstream chung. Khi mỗi người cần own trace/tenant, đọc context ở **downstream branch** riêng của từng subscriber hoặc explicitly pass immutable metadata sau authentication; không share một upstream chứa user-specific context mà chưa hiểu multicast/replay semantics.

### 5.2. SSE và cancellation

Client ngắt SSE có thể khiến subscription bị **cancel**. `doFinally` nhận `SignalType.CANCEL` và phù hợp cho cleanup/metrics; `doOnComplete` không chạy khi cancel.

```java
Flux<String> stream = service.events()
    .doFinally(signalType -> {
        // COMPLETE, ERROR hoặc CANCEL.
        // Không block event-loop; tránh log context nhạy cảm.
    });
```

Đây là snippet với `service` giả định, không phải một file chạy độc lập. Nếu cần log request ID ở `doFinally`, có thể capture **immutable request ID đã được đọc từ `deferContextual`** rồi tạo inner chain chứa cleanup. Không kỳ vọng callback bất kỳ luôn có access trực tiếp tới context hiện tại.

### 5.3. Response đã bắt đầu và lỗi tiếp theo

Một SSE response đã commit status 200 và phát events thì không thể đảm bảo chuyển thành HTTP 500 nếu upstream lỗi giữa chừng. Cần protocol-level error event hoặc kết thúc stream/retry policy. Context propagation hỗ trợ tracing/diagnostics, **không thay** HTTP semantics.

### 5.4. Backpressure không phụ thuộc ThreadLocal

Reactive Streams demand/cancellation thuộc subscription. Reactor Context truyền metadata theo subscription nhưng **không làm downstream nhanh hơn**, không tự giới hạn bộ nhớ của `onBackpressureBuffer` và không bảo đảm remote producer tuân thủ demand. Thiết kế buffering/batching/rate limits riêng.

## 6. Context trong flatMap, concatMap, publishOn và subscribeOn

### 6.1. Scheduler boundary

```java
Mono<String> pipeline = Mono.just("start")
    .publishOn(Schedulers.parallel())
    .flatMap(value ->
        Mono.deferContextual(ctx ->
            Mono.just(value + "-" + ctx.get("traceId"))))
    .contextWrite(Context.of("traceId", "req-123"));
```

Kết quả: `start-req-123`. `publishOn` chuyển nơi chạy một số downstream signals, còn Reactor Context gắn subscriber nên vẫn đi theo chain.

### 6.2. Inner publisher scoped context

```java
Mono<String> result = Mono.just("hello")
    .flatMap(word ->
        Mono.deferContextual(ctx ->
            Mono.just(word + "-" + ctx.get("k")))
        .contextWrite(Context.of("k", "inner")))
    .flatMap(value ->
        Mono.deferContextual(ctx ->
            Mono.just(value + "-" + ctx.get("k"))))
    .contextWrite(Context.of("k", "outer"));
```

Kết quả: `hello-inner-outer`. Context `inner` áp vào inner publisher của flatMap thứ nhất, không ghi đè toàn main sequence downstream. Những chain phức tạp nên kiểm tra bằng StepVerifier trước khi dựa vào scope cho audit/security.

### 6.3. Không viết Context rồi kỳ vọng đọc từ một sibling branch

Hai inner publishers sinh độc lập dưới `flatMap` có thể có context overrides cục bộ khác nhau. Một `contextWrite` trên branch A không tự sửa context của branch B. Muốn chia sẻ metadata đúng, đặt context ở downstream của cả hai hoặc pass một immutable value qua arguments.

### 6.4. concatMap vs flatMap

`flatMap` có thể interleave signals khi inner publishers async; `concatMap` tuần tự hóa inner streams theo order. **Cả hai có thể giữ Reactor Context** khi được compose đúng. Chọn operator dựa trên ordering/concurrency, không dùng `concatMap` chỉ để “fix” ThreadLocal propagation.

### 6.5. publishOn không biến source blocking thành non-blocking

```java
Mono<String> bad =
    Mono.just(legacyJdbc.read()) // blocking chạy ngay!
        .publishOn(Schedulers.boundedElastic());
```

Câu lệnh `legacyJdbc.read()` chạy **trước khi Mono được tạo**. Nếu bắt buộc bridge legacy:

```java
Mono<String> bridged =
    Mono.fromCallable(() -> legacyJdbc.read())
        .subscribeOn(Schedulers.boundedElastic());
```

Đây là snippets với dependency giả định. BoundedElastic không biến JDBC thành reactive DB driver; nguồn blocking cần timeout, pool/concurrency limits. Context có thể tiếp tục được đọc bằng `deferContextual` khi hoàn tất, nhưng `ThreadLocal` của JDBC/custom logger không tự có request metadata trừ khi bridge đúng.

## 7. Những điều Reactor Context KHÔNG tự làm

1. **Không tự tạo authentication**: request ID/tenant header nằm trong context không biến nó thành trusted principal.
2. **Không bảo đảm ThreadLocal của mọi framework**: cần context propagation integration/registered accessors nếu vẫn muốn dùng ThreadLocal.
3. **Không tự truyền sang arbitrary ExecutorService**: nếu tách khỏi Publisher chain, phải truyền immutable value hoặc ContextSnapshot/context-aware wrapper.
4. **Không tự tạo distributed tracing**: trace ID nội bộ không tự propagates qua HTTP headers sang remote service; sử dụng tracing instrumentation theo W3C Trace Context khi cần.
5. **Không tự quản lý HttpSession**: Context thường theo subscription, không phải persistent session store.
6. **Không phải cache**: `Context.put` không làm data source được cache hoặc share giữa requests.
7. **Không tự cleanup các side effects**: cần cancellation-aware lifecycle, reactor resource management.
8. **Không mang lại backpressure** cho callback source không hỗ trợ demand.
9. **Không thay được security context**: Spring Security reactive APIs đã có conventions.
10. **Không bảo đảm data visibility bên ngoài Reactor operators**: plain callback/thread pool có riêng lifecycle.

### 7.1. Bẫy “tự subscribe()” trong handler

```java
Mono<Void> writeAudit() {
    return Mono.deferContextual(ctx -> auditService.save(
        ctx.get("requestId")));
}

Mono<Response> badHandler() {
    writeAudit().subscribe(); // tách subscription khỏi HTTP chain
    return service.load().map(this::toResponse);
}
```

Đây là pseudocode minh họa; không phải class standalone. Subscription mới từ `subscribe()` có thể có **Context rỗng**, xử lý errors ngoài HTTP và gây side effect không được hủy theo request. Hướng đúng là compose audit vào return publisher:

```java
Mono<Response> goodHandler() {
    return writeAudit()
        .then(service.load())
        .map(this::toResponse);
}
```

Trong real app, audit đảm bảo exactly-once/durable cần cơ chế transaction/outbox/event log, không phải chỉ `then`. Điểm của ví dụ là **giữ chuỗi subscription**, không manual subscribe.

### 7.2. Completeness: error và empty

Nếu `Mono.deferContextual(ctx -> Mono.just(ctx.get("key")))` thiếu key, chain phát error. Nếu metadata optional, dùng getOrDefault rõ ràng. Đừng dùng `onErrorResume(any -> Mono.empty())` để nuốt errors do DB hoặc thiếu security context; nó có thể biến failure thành 200 body rỗng/404 tùy web layer.

## 8. ThreadLocal với logging MDC: không được giả định và cũng không phải lúc nào phải viết lại hết

Logback/SLF4J MDC phổ biến dùng ThreadLocal. Code synchronous:

```java
MDC.put("requestId", "req-1");
log.info("processing...");
MDC.remove("requestId");
```

đúng trong cùng thread và scope được dọn sạch. Nhưng nếu Mono chạy một phần trên reactor-http-nio, phần khác trên parallel, MDC không tự đi theo request trong chế độ Reactor chưa có bridge. Mặc dù log message có thể vẫn hiện correlation ID ở một số callbacks, **đừng suy ra nó luôn đúng**.

### 8.1. Một cách thủ công có kiểm soát

Đối với một đoạn logging synchronous ngắn, có thể đọc ContextView rồi set/restore MDC trong phạm vi callback:

```java
Mono<Void> logWithContext() {
    return Mono.deferContextual(ctx -> {
        String requestId =
            ctx.getOrDefault("requestId", "missing");

        String previous = MDC.get("requestId");
        try {
            MDC.put("requestId", requestId);
            log.info("Processing with trace context");
        } finally {
            if (previous == null) MDC.remove("requestId");
            else MDC.put("requestId", previous);
        }
        return Mono.empty();
    });
}
```

Đây là snippet minh họa, cần logger và MDC imports; không runnable riêng. Phạm vi set/restore **chỉ bao quanh log call đồng bộ**; tuyệt đối không set MDC rồi trả một Mono asynchronous và mong ThreadLocal tồn tại cho toàn subscription. Với nhiều logging sites, dùng framework-integrated Micrometer tracing/observability thay vì tự set hàng loạt.

### 8.2. Context propagation bridge: hai chế độ

Từ Reactor 3.5, Reactor Core hỗ trợ tích hợp SPI `io.micrometer:context-propagation`:

- **Default/limited mode**: chỉ một số operators như `handle`/`tap` phục hồi registered ThreadLocal state trong phạm vi nhất định. Không cam kết mọi `map`/`flatMap` callback nhìn được MDC.
- **Automatic mode**: khi bật `Hooks.enableAutomaticContextPropagation()`, Reactor cố gắng khôi phục những ThreadLocal đã được đăng ký thông qua `ThreadLocalAccessor` trên nhiều operator callbacks. Bật từ lúc startup vì chế độ này áp dụng cho **subscriptions mới**.
- `contextCapture()`: snapshot giá trị của **registered** ThreadLocal(s) ở subscription time và đưa chúng vào Reactor Context để upstream có thể nhìn thấy.
- `contextWrite(...)`: trực tiếp đặt key/value trong Reactor Context; không đồng nghĩa đã tạo ThreadLocal restoration.
- Automatic mode có overhead và cleanup semantics; key vắng mặt có thể là tín hiệu clear ThreadLocal tránh leak.

**Điều kiện rất quan trọng:** chỉ bật hook **không đủ** để một arbitrary `new ThreadLocal<>()` được propagates. Cần dependency context-propagation và `ThreadLocalAccessor` được đăng ký theo library hoặc code ứng dụng.

### 8.3. Spring Boot property trên các phiên bản hỗ trợ

Trong Spring Boot 3.3, có thể cấu hình:

```properties
spring.reactor.context-propagation=auto
```

Property này dùng cơ chế automatic context propagation của Reactor; không làm mất yêu cầu registered accessors hoặc biến Reactor Context thành implicit user identity. Tránh vừa bật hook thủ công ở nhiều nơi vừa cấu hình property mà không có lý do. Production cần benchmark và kiểm tra context lifecycle.

Nếu ứng dụng chỉ cần request correlation ID trong business/service code, **đọc Context trực tiếp** bằng `deferContextual` thường rõ ràng hơn dependency vào ThreadLocal restoration. Khi cần tương thích OpenTelemetry/Micrometer/SLF4J, dùng integration chuẩn và đối chiếu log traces trong test.

### 8.4. Bảng so sánh kết quả kỳ vọng

| Điều kiện | Reactor Context `deferContextual` | Arbitrary ThreadLocal.get() |
| --- | --- | --- |
| Một Reactor pipeline bình thường có contextWrite | Đọc được key hợp lệ | Không tự đảm bảo |
| Chuyển thread bằng publishOn | Vẫn đọc context qua operators | Không tự đảm bảo |
| Default Micrometer context propagation | Vẫn đọc context | Khôi phục ở các operators hỗ trợ cho registered accessor |
| Automatic propagation với registered accessor | Vẫn đọc context | Có thể restore theo contract/library |
| Automatic mode nhưng ThreadLocal chưa đăng ký | Vẫn đọc context | Không tự đảm bảo |
| Tách công việc bằng manual subscribe | Có thể mất parent context | Không tự đảm bảo |
| Tách sang raw ExecutorService | Cần explicit propagation | Cần explicit propagation |
| Một hot source share nhiều subscribers | Phải thiết kế per-subscriber scope | Có nguy cơ lẫn nếu đặt sai |

## 9. Spring Security: SecurityContext nằm ở đâu trong WebFlux?

Spring Security reactive sử dụng các reactive contexts và `SecurityWebFilterChain`, không dựa vào một Servlet `SecurityContextHolder` ThreadLocal luôn hiện diện trên mọi scheduler. Spring Security cung cấp `ReactiveSecurityContextHolder`:

```java
Mono<String> currentUser() {
    return ReactiveSecurityContextHolder.getContext()
        .map(security -> security.getAuthentication())
        .filter(auth -> auth != null && auth.isAuthenticated())
        .map(auth -> auth.getName());
}
```

Đây là snippet yêu cầu `spring-boot-starter-security`, imports và authentication config thích hợp. **Không** tự tạo SecurityContext từ request header `X-User-Role` rồi đặt vào Reactor Context như một cách “đăng nhập”.

### 9.1. Ngữ cảnh Request ID khác ngữ cảnh phân quyền

- `X-Request-Id` từ client: có thể dùng để correlate logs, **không** xác thực identity.
- Tracing context: có thể đến từ W3C `traceparent` được kiểm soát theo ingress/tracing policy.
- Principal: được Spring Security tạo từ trusted authentication method.
- Tenant ID: phải được xác định từ principal/session/authorization, có thể so với route parameter hoặc header đã validate theo policy.
- Locale/feature flag: có thể là metadata nhưng cần nguồn đáng tin nếu ảnh hưởng kết quả nhạy cảm.

Không log tokens/credentials và không lưu cả principal object mutable trong singleton Map rồi suy đó là safe context for all requests.

## 10. WebClient, R2DBC và ranh giới giữa các subscriptions

### 10.1. WebClient compose trong cùng chain

```java
Mono<String> result = Mono.deferContextual(ctx -> {
    String correlation = ctx.get("requestId");

    return webClient.get()
        .uri("/remote/items")
        .header("X-Request-Id", correlation)
        .retrieve()
        .bodyToMono(String.class);
});
```

Đây là snippet có WebClient đã inject và URL remote giả định, không phải class hoàn chỉnh. Ở đây Reactor Context **được đọc tường minh**, sau đó ID được đặt thành outbound HTTP header. Reactor Context **không tự gửi qua mạng** nếu client không có instrumentation hoặc application logic phù hợp.

**Không truyền security credential** lấy từ context thành arbitrary outbound header; cần OAuth/OIDC, token exchange hoặc trust delegation đúng policy.

### 10.2. R2DBC reactive repository

```java
Mono<Note> selected =
    repository.findById(id)
       .flatMap(note ->
           Mono.deferContextual(ctx -> {
               audit.record(ctx.get("requestId"), note.id());
               return Mono.just(note);
           }));
```

Snippet minh họa, `audit.record` nếu blocking phải được thay bằng reactive publisher/bridge phù hợp; nếu chỉ gọi sync rồi return Mono, bạn vẫn block caller thread. Chính việc chuỗi vẫn nằm trong Reactor composition giữ context; dùng `block()` hoặc manual subscribe cắt đứt ngữ nghĩa.

### 10.3. Transaction context khác request ID

Reactive transaction management sử dụng subscriber Context để nối transaction resources qua operators, thay vì chỉ ThreadLocal của imperative `@Transactional`. Nhưng tự đặt key `transactionId` vào Reactor Context **không tạo transaction thực**. Dùng `TransactionalOperator`/reactive Spring transaction infrastructure và driver hỗ trợ. Tránh chia sẻ một transaction-scoped publisher ra các subscribers độc lập.

### 10.4. Quay về legacy ExecutorService

Nếu bắt buộc dùng một asynchronous API khác Reactor, hãy truyền một immutable subset (ví dụ request ID) như method parameter, hoặc dùng Micrometer `ContextSnapshot`/context-aware Executor wrapper được cấu hình với accessors phù hợp. Không ném cả `ContextView` vào global static variable và không duy trì nó sau request lâu hơn cần thiết.

## 11. Demo runnable: Spring Boot 3.3.13, Java 17, WebFlux Context

Đây là ứng dụng đầy đủ, không cần database hoặc remote service. Tất cả mã dùng `spring-boot-starter-webflux` và `reactor-core` từ Spring Boot quản lý. Demo dùng Reactor Context trực tiếp, **không bật automatic ThreadLocal propagation** vì mục tiêu là chứng minh lý do không phụ thuộc ThreadLocal.

API:

- `GET /api/context`: trả requestId và stage = `direct`.
- `GET /api/context/delayed`: đi qua `Mono.delay`, vẫn đọc requestId.
- `GET /api/context/bounded`: chuyển bước nhỏ qua `Schedulers.boundedElastic()`, vẫn giữ requestId.
- `GET /api/context/scoped`: ghi đè context trong một nhánh cục bộ thành `local-override` để hiểu scope; response header do filter vẫn là ID bên ngoài.
- `GET /api/context/events`: 3 SSE events, mỗi event đọc context trên inner Mono.
- `GET /api/context/error`: reactive error 400; WebFilter đã set correlation response header.
- `GET /api/context/missing`: route không tồn tại, xác nhận 404 của WebFlux.

Request ID header mẫu `X-Request-Id` chỉ dùng **diagnostics**, không dùng cho auth/tenant. Filter chỉ nhận characters allowlist và độ dài ≤64 để hạn chế log injection; nếu input không đạt rule, nó tạo UUID.

### 11.1. Cấu trúc file

```text
reactor-context-demo/
├── pom.xml
└── src/
    ├── main/java/example/
    │   ├── ReactorContextApplication.java
    │   ├── ContextKeys.java
    │   ├── TraceReply.java
    │   ├── RequestIdFilter.java
    │   ├── TraceService.java
    │   └── TraceController.java
    └── test/java/example/
        ├── ContextOperatorsTest.java
        └── TraceHttpTest.java
```

### 11.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-context-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

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
            <artifactId>spring-boot-starter-test</artifactId>
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

**Lưu ý:** Không thêm `spring-boot-starter-web` vào demo, vì khi MVC và WebFlux starters cùng có mặt Boot thường chọn Servlet MVC. Mã `WebFilter` ở đây thuộc `org.springframework.web.server` và phù hợp reactive web application type.

### 11.3. ReactorContextApplication.java

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactorContextApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactorContextApplication.class, args);
    }
}
```

### 11.4. ContextKeys.java

```java
package example;

public final class ContextKeys {

    public static final String REQUEST_ID = "example.request-id";

    private ContextKeys() {
    }
}
```

Dùng một constant key chung cho filter và service. Không copy-paste String literals khác nhau ở nhiều nơi.

### 11.5. TraceReply.java

```java
package example;

public record TraceReply(
        String requestId,
        String stage,
        String threadName) {
}
```

`threadName` chỉ để quan sát diagnostics; không xây assertions “phải là thread X” vì Reactor schedulers và Netty thread names có thể đổi theo môi trường/versions.

### 11.6. RequestIdFilter.java

```java
package example;

import java.util.UUID;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(0)
public class RequestIdFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String requested = exchange.getRequest()
                .getHeaders().getFirst("X-Request-Id");

        final String requestId = requested != null &&
                requested.matches("[A-Za-z0-9._-]{1,64}")
            ? requested
            : UUID.randomUUID().toString();

        exchange.getResponse().getHeaders()
                .set("X-Request-Id", requestId);

        return chain.filter(exchange)
            .contextWrite(context ->
                context.put(ContextKeys.REQUEST_ID, requestId));
    }
}
```

Giải thích:

1. `WebFilter` chạy trong reactive WebHandler chain.
2. Đọc ID tùy chọn từ HTTP request, kiểm tra ký tự/độ dài.
3. Đặt một header response để client correlate lỗi với request.
4. Trả `chain.filter(exchange).contextWrite(...)`, không gọi `block()` hay `subscribe()`.
5. Phần chain **upstream** của contextWrite có thể đọc ID qua `deferContextual`, kể cả sau scheduler hops.

ID từ client vẫn **không đáng tin cho authorization**, và không bao giờ dùng để quyết định principal/tenant. Trong production tracing instrumentation có thể tạo/validate trace IDs riêng.

### 11.7. TraceService.java

```java
package example;

import java.time.Duration;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Service
public class TraceService {

    public Mono<TraceReply> snapshot(String stage) {
        return Mono.deferContextual(context -> {
            String requestId = context.getOrDefault(
                    ContextKeys.REQUEST_ID, "missing");

            return Mono.just(new TraceReply(
                requestId,
                stage,
                Thread.currentThread().getName()));
        });
    }

    public Mono<TraceReply> delayed() {
        return Mono.delay(Duration.ofMillis(10))
                .flatMap(value -> snapshot("after-delay"));
    }

    public Mono<TraceReply> bounded() {
        return Mono.fromCallable(() -> "legacy-stage")
                .subscribeOn(Schedulers.boundedElastic())
                .flatMap(this::snapshot);
    }

    public Mono<TraceReply> scoped() {
        return snapshot("local-scope")
            .contextWrite(context ->
                context.put(
                    ContextKeys.REQUEST_ID, "local-override"));
    }
}
```

- `snapshot` lấy requestId khi **subscription** đi đến `deferContextual`. Không có static state.
- `delayed` dùng timer scheduler rồi `flatMap` tới `snapshot`; context vẫn có.
- `bounded` cho thấy context vẫn truy cập được sau `subscribeOn(boundedElastic)`. Callable trả một String nhỏ, **không thực hiện blocking I/O thật**.
- `scoped` cố ý ghi đè cùng key gần source; response body thấy `local-override`, nhưng WebFilter response header phản ánh ID gốc vì nó được đặt từ request trước khi body subscribe.

Không gán `threadName` của hai requests như một bằng chứng context isolation, vì scheduler names có thể trùng. Test dựa vào *giá trị requestId*.

### 11.8. TraceController.java

```java
package example;

import java.time.Duration;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class TraceController {

    private final TraceService service;

    public TraceController(TraceService service) {
        this.service = service;
    }

    @GetMapping("/api/context")
    public Mono<TraceReply> direct() {
        return service.snapshot("direct");
    }

    @GetMapping("/api/context/delayed")
    public Mono<TraceReply> delayed() {
        return service.delayed();
    }

    @GetMapping("/api/context/bounded")
    public Mono<TraceReply> bounded() {
        return service.bounded();
    }

    @GetMapping("/api/context/scoped")
    public Mono<TraceReply> scoped() {
        return service.scoped();
    }

    @GetMapping(
        value = "/api/context/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<TraceReply>> events() {
        return Flux.interval(Duration.ofMillis(10))
            .take(3)
            .concatMap(index ->
                service.snapshot("event-" + index)
                    .map(reply ->
                        ServerSentEvent.<TraceReply>builder()
                            .id(Long.toString(index))
                            .event("trace")
                            .data(reply)
                            .build()));
    }

    @GetMapping("/api/context/error")
    public Mono<TraceReply> error() {
        return Mono.error(new ResponseStatusException(
            HttpStatus.BAD_REQUEST,
            "demonstration error"));
    }
}
```

**Chuỗi streaming:** mỗi `index` từ Flux timer được chuyển sang một `service.snapshot(...)`. Vì inner Mono thuộc same composed subscription, context của WebFilter vẫn xuất hiện trong từng SSE payload. `take(3)` dừng stream để test không treo. Production SSE vô hạn cần heartbeat, request cancellation, resource controls và proxies timeouts.

**Error path:** `ResponseStatusException(HttpStatus.BAD_REQUEST)` được WebFlux exception infrastructure xử lý thành 400 khi chưa commit. Filter đã đặt `X-Request-Id` header, giúp client correlate lỗi ngay cả khi body error do framework sinh.

### 11.9. Chạy Maven/cURL

Tại thư mục chứa `pom.xml` (JDK 17+, Maven):

```bash
mvn test
mvn spring-boot:run
```

**Lưu ý:** Các câu lệnh này là hướng dẫn dành cho người học. Tài liệu tự chứa code; chưa tuyên bố tests được chạy trong môi trường tạo bài.

Gọi trực tiếp:

```bash
curl -i -H "X-Request-Id: demo-A" \
  http://localhost:8080/api/context
```

HTTP 200, header `X-Request-Id: demo-A` và body JSON dạng:

```json
{
  "requestId": "demo-A",
  "stage": "direct",
  "threadName": "reactor-http-nio-1"
}
```

**Không** dựa vào giá trị `threadName` ở trên vì chỉ là ví dụ; tên thực thay đổi. Chỉ các fields `requestId` và `stage` là contract ổn định.

Bước delay:

```bash
curl -i -H "X-Request-Id: demo-B" \
  http://localhost:8080/api/context/delayed
```

Kỳ vọng body chứa:

```json
{"requestId":"demo-B","stage":"after-delay"}
```

Phần threadName khác tùy runtime.

Bước boundedElastic:

```bash
curl -i -H "X-Request-Id: demo-C" \
  http://localhost:8080/api/context/bounded
```

Kỳ vọng requestId `demo-C` và stage `legacy-stage`.

Scope:

```bash
curl -i -H "X-Request-Id: outer-123" \
  http://localhost:8080/api/context/scoped
```

Kỳ vọng **header** `X-Request-Id: outer-123`, nhưng **body** có `"requestId":"local-override"`. Đây là một demo cố tình ghi đè để minh họa scope; không nên ghi đè correlation ID trong business code production trừ khi có lý do và audit.

Invalid header:

```bash
curl -i -H "X-Request-Id: invalid id" \
  http://localhost:8080/api/context
```

Kỳ vọng header/body requestId là một UUID mới theo logic validation; đừng assert một UUID cố định.

SSE:

```bash
curl -N -i -H "X-Request-Id: stream-9" \
  -H "Accept: text/event-stream" \
  http://localhost:8080/api/context/events
```

Body SSE sẽ chứa ba events (format/whitespace và thread names không cố định):

```text
id:0
event:trace
data:{"requestId":"stream-9","stage":"event-0","threadName":"..."}

id:1
event:trace
data:{"requestId":"stream-9","stage":"event-1","threadName":"..."}

id:2
event:trace
data:{"requestId":"stream-9","stage":"event-2","threadName":"..."}

```

Không kỳ vọng SSE chunk boundaries giống line boundaries của TCP. `curl -N` chỉ tắt buffering của curl.

## 12. Tests: WebTestClient kiểm tra context qua HTTP thật

File `src/test/java/example/TraceHttpTest.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class TraceHttpTest {

    @Autowired
    WebTestClient client;

    @Test
    void requestIdAppearsInBodyAndResponseHeader() {
        client.get().uri("/api/context")
            .header("X-Request-Id", "req-one")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals("X-Request-Id", "req-one")
            .expectBody()
                .jsonPath("$.requestId").isEqualTo("req-one")
                .jsonPath("$.stage").isEqualTo("direct");
    }

    @Test
    void contextSurvivesDelayBoundary() {
        client.get().uri("/api/context/delayed")
            .header("X-Request-Id", "req-delay")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
                .jsonPath("$.requestId").isEqualTo("req-delay")
                .jsonPath("$.stage").isEqualTo("after-delay");
    }

    @Test
    void contextSurvivesBoundedElasticBoundary() {
        client.get().uri("/api/context/bounded")
            .header("X-Request-Id", "req-bounded")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
                .jsonPath("$.requestId").isEqualTo("req-bounded")
                .jsonPath("$.stage").isEqualTo("legacy-stage");
    }

    @Test
    void innerContextOverrideHasLocalScope() {
        client.get().uri("/api/context/scoped")
            .header("X-Request-Id", "external-id")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                "X-Request-Id", "external-id")
            .expectBody()
                .jsonPath("$.requestId")
                    .isEqualTo("local-override")
                .jsonPath("$.stage")
                    .isEqualTo("local-scope");
    }

    @Test
    void invalidInboundIdGetsNewId() {
        client.get().uri("/api/context")
            .header("X-Request-Id", "invalid id with spaces")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
                .jsonPath("$.requestId")
                    .value(value -> {
                        String id = String.valueOf(value);
                        assertNotEquals(
                            "invalid id with spaces", id);
                        assertTrue(id.length() >= 30);
                    });
    }

    @Test
    void errorKeepsCorrelationHeader() {
        client.get().uri("/api/context/error")
            .header("X-Request-Id", "req-error")
            .exchange()
            .expectStatus().isBadRequest()
            .expectHeader().valueEquals(
                "X-Request-Id", "req-error");
    }

    @Test
    void sseEventsKeepSameSubscriptionContext() {
        FluxExchangeResult<ServerSentEvent<TraceReply>> result =
            client.get().uri("/api/context/events")
                .header("X-Request-Id", "req-stream")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM)
                .returnResult(new ParameterizedTypeReference<
                    ServerSentEvent<TraceReply>>() {});

        StepVerifier.create(result.getResponseBody())
            .expectNextMatches(event ->
                event.data() != null &&
                "req-stream".equals(event.data().requestId()) &&
                "event-0".equals(event.data().stage()))
            .expectNextMatches(event ->
                event.data() != null &&
                "req-stream".equals(event.data().requestId()) &&
                "event-1".equals(event.data().stage()))
            .expectNextMatches(event ->
                event.data() != null &&
                "req-stream".equals(event.data().requestId()) &&
                "event-2".equals(event.data().stage()))
            .verifyComplete();
    }

    @Test
    void twoHttpRequestsHaveDifferentContext() {
        client.get().uri("/api/context")
            .header("X-Request-Id", "client-A")
            .exchange()
            .expectStatus().isOk()
            .expectBody().jsonPath("$.requestId")
                .isEqualTo("client-A");

        client.get().uri("/api/context")
            .header("X-Request-Id", "client-B")
            .exchange()
            .expectStatus().isOk()
            .expectBody().jsonPath("$.requestId")
                .isEqualTo("client-B");
    }

    @Test
    void missingRouteIs404() {
        client.get().uri("/api/context/not-mapped")
            .exchange()
            .expectStatus().isNotFound();
    }
}
```

Có **9 WebTestClient test methods**. Test SSE thực sự consume 3 events, không chỉ kiểm tra Content-Type. Test request A/B ở trên gọi tuần tự — xác nhận context không bị giữ thành singleton từ request trước; để test **concurrency thật**, xem StepVerifier merge ở phần sau.

**Không assert threadName cố định**, vì project cần chạy ổn định trên OS/CPU/scheduler khác nhau. Nếu test ngữ cảnh trên một actual network/proxy runtime, có thể bổ sung parallel HTTP load và trace IDs theo log instrumentation.

## 13. Tests: StepVerifier xác minh semantics Context không phụ thuộc WebFlux HTTP

File `src/test/java/example/ContextOperatorsTest.java`:

```java
package example;

import java.time.Duration;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;
import reactor.util.context.Context;

class ContextOperatorsTest {

    private static final String KEY = "test.trace";

    @Test
    void contextWriteIsVisibleUpstream() {
        Mono<String> source = Mono.deferContextual(ctx ->
            Mono.just(ctx.get(KEY)));

        StepVerifier.create(
                source.contextWrite(Context.of(KEY, "A")))
            .expectNext("A")
            .verifyComplete();
    }

    @Test
    void withoutContextDefaultIsUsed() {
        Mono<String> source = Mono.deferContextual(ctx ->
            Mono.just(ctx.getOrDefault(KEY, "missing")));

        StepVerifier.create(source)
            .expectNext("missing")
            .verifyComplete();
    }

    @Test
    void wrongOperatorPositionDoesNotAffectDownstream() {
        Mono<String> source = Mono.just("x")
            .contextWrite(ctx -> ctx.put(KEY, "inner"))
            .flatMap(value ->
                Mono.deferContextual(ctx ->
                    Mono.just(ctx.getOrDefault(KEY, "missing"))));

        StepVerifier.create(source)
            .expectNext("missing")
            .verifyComplete();
    }

    @Test
    void rightOperatorPositionIsVisibleToFlatMap() {
        Mono<String> source = Mono.just("x")
            .flatMap(value ->
                Mono.deferContextual(ctx ->
                    Mono.just(ctx.getOrDefault(KEY, "missing"))))
            .contextWrite(ctx -> ctx.put(KEY, "A"));

        StepVerifier.create(source)
            .expectNext("A")
            .verifyComplete();
    }

    @Test
    void nearestUpstreamContextWriteWinsForSameKey() {
        Mono<String> source =
            Mono.deferContextual(ctx -> Mono.just(ctx.get(KEY)))
                .contextWrite(ctx -> ctx.put(KEY, "inner"))
                .contextWrite(ctx -> ctx.put(KEY, "outer"));

        StepVerifier.create(source)
            .expectNext("inner")
            .verifyComplete();
    }

    @Test
    void contextSurvivesPublishOn() {
        Mono<String> source =
            Mono.just("start")
                .publishOn(Schedulers.parallel())
                .flatMap(value ->
                    Mono.deferContextual(ctx ->
                        Mono.just(value + "-" + ctx.get(KEY))))
                .contextWrite(Context.of(KEY, "X"));

        StepVerifier.create(source)
            .expectNext("start-X")
            .verifyComplete();
    }

    @Test
    void contextSurvivesDelay() {
        Mono<String> source = Mono.delay(Duration.ofMillis(5))
            .flatMap(tick ->
                Mono.deferContextual(ctx ->
                    Mono.just(ctx.get(KEY))))
            .contextWrite(Context.of(KEY, "delayed"));

        StepVerifier.create(source)
            .expectNext("delayed")
            .verifyComplete();
    }

    @Test
    void separateSubscriptionsAreIsolated() {
        Mono<String> source =
            Mono.deferContextual(ctx -> Mono.just(ctx.get(KEY)));

        Flux<String> merged = Flux.merge(
            source.contextWrite(Context.of(KEY, "A"))
                .subscribeOn(Schedulers.parallel()),
            source.contextWrite(Context.of(KEY, "B"))
                .subscribeOn(Schedulers.parallel()));

        StepVerifier.create(merged.collectList())
            .expectNextMatches(list ->
                list.size() == 2 &&
                list.contains("A") &&
                list.contains("B"))
            .verifyComplete();
    }

    @Test
    void innerFlatMapContextDoesNotRewriteSibling() {
        Mono<String> source = Mono.just("hello")
            .flatMap(word ->
                Mono.deferContextual(ctx ->
                    Mono.just(word + "-" + ctx.get(KEY)))
                    .contextWrite(Context.of(KEY, "inner")))
            .flatMap(value ->
                Mono.deferContextual(ctx ->
                    Mono.just(value + "-" + ctx.get(KEY))))
            .contextWrite(Context.of(KEY, "outer"));

        StepVerifier.create(source)
            .expectNext("hello-inner-outer")
            .verifyComplete();
    }

    @Test
    void manyFluxEventsSeeContext() {
        Flux<String> source = Flux.range(0, 3)
            .concatMap(index -> Mono.deferContextual(ctx ->
                Mono.just(ctx.get(KEY) + ":" + index)))
            .contextWrite(Context.of(KEY, "stream-A"));

        StepVerifier.create(source)
            .expectNext("stream-A:0", "stream-A:1",
                "stream-A:2")
            .verifyComplete();
    }

    @Test
    void innerOverrideAffectsOnlyInnerPublisher() {
        Mono<String> base =
            Mono.deferContextual(ctx -> Mono.just(ctx.get(KEY)));

        Mono<String> source = base
            .contextWrite(Context.of(KEY, "inner"));

        StepVerifier.create(
            source.contextWrite(Context.of(KEY, "outer")))
            .expectNext("inner")
            .verifyComplete();

        StepVerifier.create(
            base.contextWrite(Context.of(KEY, "outer")))
            .expectNext("outer")
            .verifyComplete();
    }

    @Test
    void missingRequiredKeyIsAnError() {
        Mono<String> source =
            Mono.deferContextual(ctx -> Mono.just(ctx.get(KEY)));

        StepVerifier.create(source)
            .expectError(java.util.NoSuchElementException.class)
            .verify();
    }
}
```

Có **12 Reactor unit tests**. Kết quả không lệ thuộc Netty thread names; StepVerifier xác nhận exact values, completion và missing context. Test `separateSubscriptionsAreIsolated` merge hai pipelines chạy cùng scheduler, kiểm tra A/B cùng xuất hiện dù thứ tự completion có thể thay đổi. Đó là minh họa concurrency tốt hơn test sequential HTTP đơn thuần.

### 13.1. Khi nào dùng StepVerifier.withVirtualTime?

Khi test stream nhiều phút có `delayElements`/`interval`, dùng virtual scheduler sẽ nhanh và ổn định hơn `Thread.sleep`. Tạo publisher **bên trong Supplier** của `withVirtualTime`:

```java
@Test
void virtualTimeStillPreservesContext() {
    StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofHours(1))
            .take(2)
            .concatMap(n ->
                Mono.deferContextual(ctx ->
                    Mono.just(ctx.get("trace") + ":" + n)))
            .contextWrite(Context.of("trace", "virtual")))
        .expectSubscription()
        .thenAwait(Duration.ofHours(2))
        .expectNext("virtual:0", "virtual:1")
        .verifyComplete();
}
```

Snippet bổ sung đặt trong `ContextOperatorsTest` với imports đã có. Khi dùng `withVirtualTime`, không tạo Flux.interval ở ngoài Supplier rồi mới verify vì scheduler có thể đã được capture trước khi virtual scheduler được cài đặt.

## 14. Truyền context sang callbacks khác Reactor

### 14.1. CompletableFuture

```java
CompletableFuture<String> future =
    CompletableFuture.supplyAsync(
        () -> legacyService.readData());
```

Đoạn này sử dụng executor khác và không nhất thiết có Reactor subscriber context. Nếu bọc:

```java
Mono<String> wrapped = Mono.fromFuture(future);
```

bạn có reactive result nhưng không tự có context bên trong `supplyAsync` đã chạy trước đó. Nếu việc đọc ngữ cảnh quan trọng, đọc từ `deferContextual` rồi pass **immutable request ID** vào supplier hoặc dùng context-propagating executor chuẩn.

### 14.2. Scheduler wrappers, Micrometer ContextSnapshot

Với non-Reactor executors và libraries phụ thuộc ThreadLocal, dùng `io.micrometer:context-propagation` để đăng ký accessors/capture snapshot khi cần, rồi bọc công việc thực thi theo đúng API version. Không triển khai “set ThreadLocal mà quên restore” vì thread pool sẽ reuse. Chỉ restore đúng một **scope** và close/clear trong finally/try-with-resources.

### 14.3. Coroutines

Spring WebFlux với Kotlin coroutines có khả năng bridge Reactor Context sang coroutine context qua integrations phù hợp (ví dụ `ReactorContext`), nhưng không mặc định every Java ThreadLocal survives suspension. Trước khi port Java Reactor code sang Kotlin, kiểm tra coroutine context propagation/withContext boundaries và framework dependencies.

### 14.4. Reactive transaction boundaries

Một Spring reactive transaction giữ connection/transaction state theo reactive context. Nếu tự `subscribe()` một repository.save() riêng, operation đó có thể thoát khỏi transaction/subscription và commit ngoài thời điểm kỳ vọng. Compose publisher trong transaction chain, dùng `TransactionalOperator` hoặc reactive @Transactional đúng config.

## 15. Security, privacy và logging hygiene

Dù Reactor Context hữu ích cho audit/tracing, không nên biến nó thành nơi giữ tất cả state của user.

### 15.1. Phân loại metadata

| Loại | Có thể dùng context? | Ghi chú |
| --- | --- | --- |
| Correlation/request ID đã validate | Có | Chỉ cho logs/tracing, không xác thực |
| Span/observation context | Có qua instrumentation | Để Micrometer/OpenTelemetry quản lý |
| Authenticated principal | Spring Security reactive context | Không tự tin X-User headers |
| Tenant ID | Chỉ khi nguồn đáng tin | Phải authorize từng resource |
| Locale/timezone preference | Có thể | Chọn nguồn và validation rõ |
| Raw JWT/password/session cookie | Tránh | Có thể lộ qua context dumps/logs |
| Large request body/FilePart | Tránh | Buffer/memory/resources |
| Mutable JPA EntityManager | Không phù hợp | Blocking/thread-bound semantics |
| Mutable global Map state | Không | Rủi ro data races/leaks |

### 15.2. IDs từ client: xác thực hay chỉ correlation?

Một requestId header có thể do client giả, tái sử dụng hoặc chứa dữ liệu không phù hợp. Trong demo chỉ cho allowed pattern và echo. Trong production cần quy định độ dài, uniqueness, log forging, ingress trusted trace correlation và sampling. Không dùng requestId làm access control hay idempotency key nếu chưa xác thực scope.

### 15.3. Tracing qua mạng

Reactor Context nằm **trong process/JVM**. Khi WebClient gọi remote service, remote JVM không tự đọc được Context này. Distributed tracing dùng HTTP propagation conventions như W3C `traceparent` và instrumentation. Không tự log toàn ContextView để debug vì có thể chứa keys nội bộ từ security/tracing libraries.

### 15.4. Correlation logs và lỗi HTTP

Khi xảy ra lỗi giữa một SSE stream, correlation ID giúp tìm logs đúng request. Nhưng response có thể đã commit 200 và không còn cách sửa status; correlation không thay business failure protocol. Error logs cần severity, structured error codes và không leak tokens/PII.

## 16. Lỗi phổ biến cần nhận diện

| Nhầm lẫn / triệu chứng | Nguyên nhân | Hướng đúng |
| --- | --- | --- |
| “ThreadLocal luôn còn nguyên trong WebFlux” | Publisher chuyển scheduler/thread | Dùng Reactor Context hoặc bridge |
| “Một request có một thread Netty riêng” | Event loops phục vụ nhiều channels | Không dựa vào thread identity |
| “Context chỉ là một global map” | Gắn subscriber | Đọc bằng deferContextual |
| “contextWrite sửa Context object tại chỗ” | Context immutable | Nhận Context mới theo chain |
| “contextWrite luôn ảnh hưởng mọi operator bên dưới nó” | Hướng propagation ngược | Đặt write downstream của readers |
| “Context đặt ở source được mọi flatMap downstream đọc” | Scope của contextWrite chỉ upstream | Test order bằng StepVerifier |
| “Mono.just(ctx.get(...)) ở controller lấy context hiện tại” | Không có ctx per-subscription trong imperative code | deferContextual |
| “Một static String requestId đủ cho tất cả” | Race/leak cross-request | Context per-subscriber |
| “Context inner branch ảnh hưởng mọi siblings” | Ghi đè scoped | Đặt write ở common downstream nếu cần |
| “subscribe() thủ công giữ HTTP context” | Tạo subscription khác | Compose publisher/return chain |
| “publishOn làm mất Reactor Context” | Thường không khi pipeline đúng | deferContextual qua operator |
| “publishOn tự truyền mọi ThreadLocal” | ThreadLocal khác Context | Registered accessor/bridge |
| “Bật auto hook là mọi ThreadLocal đều có” | Thiếu SPI/accessor | Cấu hình Micrometer đúng |
| “default mode khôi phục MDC trong mọi map” | Limited restoration | Kiểm tra handle/tap/automatic mode |
| “contextCapture đọc Context rồi ghi ThreadLocal” | Thường capture registered ThreadLocal vào Context | Hiểu chiều capture/restore |
| “WebFilter set ThreadLocal là đủ cho stream SSE dài” | Lối sống thread thay đổi | WebFilter contextWrite |
| “SSE Flux share global có per-client Context tự động” | Upstream hot sharing phức tạp | Đọc context theo per-client downstream |
| “Reactive Context tự gửi sang remote microservice” | Chỉ local JVM/subscription | Tracing/outbound headers rõ |
| “Mất Context thì fallback admin” | Auth bypass | Fail-closed |
| “X-Request-Id là user identity” | Header client tự sửa | Auth principal đáng tin |
| “MDC.put rồi không cần remove” | Thread reused | try/finally hoặc integration |
| “Dump toàn Context ra logs an toàn” | Có thể chứa sensitive metadata | Chỉ log allowlisted keys |
| “Mọi blocking call sẽ được boundedElastic tự nhận” | Reactor không tự chuyển library code | Explicit bridge/non-blocking driver |
| “Context giúp Flux nhanh hơn” | Chỉ mang metadata | Tối ưu nguồn/backpressure riêng |
| “HTTP 200 stream lỗi vẫn set lại 500” | Headers đã commit | Protocol error/cancel |
| “WebTestClient assert threadName đủ chứng minh” | Runtime detail unstable | Assert requestId và test scheduler hops |
| “Context key string không có collision” | Libraries/app có thể cùng key | Namespace/object keys |
| “Context cache() luôn riêng cho từng subscriber” | Shared source có lifecycle riêng | Hiểu hot/cold/cache semantics |
| “Request context là transaction” | Business transaction API khác | Reactive transaction infrastructure |
| “Context là HttpSession” | Subscription-scoped không durable | Dùng session store đúng |

## 17. Checklist trước khi dùng trong production

1. [ ] Định nghĩa rõ metadata cần truyền (correlation ID, trusted principal reference, trace).
2. [ ] Không dùng static mutable request state hay ThreadLocal mà thiếu bridge/cleanup.
3. [ ] Context keys ổn định, namespaced hoặc typed identity.
4. [ ] Đặt `contextWrite` downstream của readers mong muốn.
5. [ ] Dùng `deferContextual` đúng tại subscription time.
6. [ ] Không gọi `subscribe()` để làm side effects ngoài request chain.
7. [ ] Nếu chuyển scheduler bằng publishOn/subscribeOn, test context còn nguyên.
8. [ ] Test context trong inner publishers và sibling branches.
9. [ ] Với SSE/streaming, test nhiều events có cùng context.
10. [ ] Dọn tài nguyên khi complete/error/cancel; không phụ thuộc chỉ doOnComplete.
11. [ ] Nếu dùng MDC/ThreadLocal, cấu hình Micrometer accessors và automatic/default mode rõ.
12. [ ] Không bật auto context propagation chỉ vì “bật cho chắc”; đo overhead.
13. [ ] Spring Security principal/tenant nhận từ trusted auth, không từ request ID header.
14. [ ] Outbound WebClient tracing/correlation được propagates qua headers có kiểm soát.
15. [ ] DB transaction vẫn dùng reactive transaction APIs, không tự giả bằng context key.
16. [ ] Không log/copy secrets và không dump toàn context.
17. [ ] Backpressure, buffering, timeouts và long-lived connections có giới hạn.
18. [ ] Có tests StepVerifier cho missing/override/parallel context isolation.
19. [ ] WebTestClient xác minh header/body/error/SSE sau scheduler boundaries.
20. [ ] Quan sát trace/log correlation theo request dưới concurrent load.

## 18. Câu hỏi ôn tập và đáp án

**1.** Reactor Context gắn với thread hay subscriber?  
**Đáp án:** Subscriber/subscription, không phải một Java Thread.

**2.** `contextWrite` truyền giá trị về phía nào?  
**Đáp án:** Về upstream operators khi subscription thiết lập.

**3.** Vì sao dùng `deferContextual`?  
**Đáp án:** Đọc ngữ cảnh khi Publisher được subscribe thay vì tại assembly time.

**4.** `ContextView` có mutable set() không?  
**Đáp án:** Không; nó là read-only view.

**5.** `Context.put` có mutate instance gốc không?  
**Đáp án:** Không, trả một Context mới.

**6.** Có thể dùng ThreadLocal trong MVC sync không?  
**Đáp án:** Có khi scope được quản lý và cleanup đúng; nhưng không suy sang WebFlux.

**7.** `publishOn` có tự xóa Reactor Context không?  
**Đáp án:** Không, nếu chuỗi Reactor được compose đúng, context vẫn theo subscription.

**8.** `ThreadLocal.get()` sau publishOn có chắc đọc đúng request?  
**Đáp án:** Không, trừ khi có context propagation bridge được cấu hình phù hợp.

**9.** Automatic mode có propagates một arbitrary ThreadLocal chưa đăng ký không?  
**Đáp án:** Không; cần ThreadLocalAccessor/context-propagation integration.

**10.** `contextCapture()` chủ yếu làm gì?  
**Đáp án:** Capture registered ThreadLocal values tại subscription time vào Reactor Context.

**11.** Tại sao không tự `subscribe()` trong WebFlux handler?  
**Đáp án:** Tạo subscription mới có thể làm mất context, cancellation, error handling và transaction scope.

**12.** `X-Request-Id` có nên dùng làm role hoặc tenant authority?  
**Đáp án:** Không; nó chỉ là metadata correlation không đáng tin để phân quyền.

**13.** Một Flux SSE có ba events thì có ba Context riêng không?  
**Đáp án:** Thường cùng một subscription context cho client, trừ khi inner branches override có chủ ý.

**14.** `flatMap` inner publisher viết context có thay context toàn app không?  
**Đáp án:** Không, scope của inner context write là cục bộ.

**15.** Dùng một global shared Flux cho dữ liệu riêng tư của từng user cần cẩn thận gì?  
**Đáp án:** Upstream sharing có thể không bảo đảm per-subscriber context/tenant boundaries; phải tách scope và authorization.

**16.** Làm sao đưa correlation ID ra một remote HTTP service?  
**Đáp án:** Đọc Context và đặt outbound header có policy hoặc dùng tracing instrumentation.

**17.** ReactiveSecurityContextHolder dùng cho gì?  
**Đáp án:** Lấy Spring Security authentication context trong reactive chain.

**18.** Context có tự tạo DB transaction không?  
**Đáp án:** Không, cần reactive transaction infrastructure.

**19.** Vì sao MDC cần cleanup trên thread pool?  
**Đáp án:** Thread reused, state cũ có thể lộ sang request khác.

**20.** Cách kiểm thử context không phụ thuộc threadName là gì?  
**Đáp án:** StepVerifier expectNext values và WebTestClient HTTP IDs, thêm scheduler hops.

**21.** Context có ảnh hưởng HTTP status sau response commit không?  
**Đáp án:** Không, nó chỉ truyền metadata.

**22.** `contextWrite` gần source hơn ghi giá trị nào nếu downstream cũng ghi cùng key?  
**Đáp án:** Giá trị gần source hơn có thể override giá trị downstream đối với source.

**23.** Nếu context key bắt buộc không tồn tại, `ctx.get(key)` làm gì?  
**Đáp án:** Thường ném NoSuchElementException; nên xử lý fail-closed hoặc policy rõ.

**24.** `spring.reactor.context-propagation=auto` có tự tạo principal không?  
**Đáp án:** Không, nó chỉ cấu hình propagation cho registered ThreadLocal integration.

**25.** Khi người dùng hủy SSE, cleanup nên xem tín hiệu nào?  
**Đáp án:** `SignalType.CANCEL` qua `doFinally`/lifecycle phù hợp, không chờ complete.

## 19. Nguồn tham khảo chính thức

- [Project Reactor 3.6 Reference — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/3.6.12/reference/index.html#context): cơ chế per-subscriber Context, contextWrite, deferContextual, thứ tự operators và inner scopes.
- [Project Reactor — Context-Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html): Micrometer context-propagation, default/automatic modes, ThreadLocalAccessor, contextCapture.
- [Project Reactor — Mono Javadoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): `deferContextual`, `contextWrite`, subscription and operator behavior.
- [Project Reactor — Flux Javadoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): `Flux.deferContextual`, scheduler and error/cancellation operators.
- [Spring Framework 6.2 — WebFlux WebHandler API](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/web-handler-api.html): WebFilter, ServerWebExchange, reactive request lifecycle.
- [Spring Boot — Observability and Context Propagation](https://docs.spring.io/spring-boot/reference/actuator/observability.html): Reactor context-propagation auto setting và Micrometer integration.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): reactive security context/authorization.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html): HTTP reactive tests.
- [Reactor Test StepVerifier Javadoc](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): signal/value/time tests.

**Điều cần nhớ:** ***ThreadLocal thuộc về thread, Reactor Context thuộc về subscriber.*** Với WebFlux stream, muốn truyền request ID/trace/locale qua asynchronous boundaries thì ghi vào Context bằng `contextWrite` và đọc bằng `deferContextual` theo đúng scope. Nếu cần MDC hoặc thư viện dựa ThreadLocal, dùng Micrometer context-propagation/registered accessors rõ ràng; không suy rằng Reactor Context tự biến mọi ThreadLocal thành an toàn. Và luôn tách metadata correlation với authentication/authorization.
