# Kiểm tra Reactor Context với StepVerifier trong Spring Framework reactive

## 1. Vì sao cần kiểm thử `Context`?

Trong ứng dụng Spring WebFlux, một `Mono` hoặc `Flux` không chỉ truyền tín hiệu dữ liệu (`onNext`, `onError`, `onComplete`). Mỗi subscription còn có thể mang **Reactor Context**: một tập key–value nhỏ chứa metadata đi kèm luồng xử lý, chẳng hạn correlation ID, tenant ID, trace information hoặc Spring Security context.

Không giống tham số truyền trong `onNext`, những giá trị này **không phải dữ liệu nghiệp vụ chính**. Chúng mô tả ngữ cảnh của một subscriber và được truyền theo cơ chế subscription của Reactor.

Khi kiểm thử một pipeline, chỉ viết:

```java
StepVerifier.create(service.find("42"))
        .expectNextMatches(item -> item.id().equals("42"))
        .verifyComplete();
```

là chưa đủ nếu service còn dựa vào tenant, request ID hoặc identity trong Reactor Context. Response có thể đúng ở môi trường đơn giản nhưng sai khi:

- Tenant bị mất sau một operator hoặc nested publisher.
- Hai request đồng thời dùng nhầm context của nhau.
- `contextWrite` đặt sai vị trí nên operator không nhìn thấy key.
- `ThreadLocal` không còn giá trị khi chuyển thread.
- Logic fallback che đi việc thiếu context bắt buộc.
- Test chỉ kiểm tra `onNext` mà không xác minh context đã thực sự đến source.

Bài học này hướng dẫn **kiểm tra Reactor Context bằng `StepVerifier`**: từ mô hình truyền Context, `StepVerifierOptions.withInitialContext(...)`, `expectAccessibleContext()`, cho tới các tình huống khó về thứ tự `contextWrite`, async boundaries, Reactor Context trong Spring Security và bộ kiểm thử Java 17+ có thể chạy bằng Maven.

**Kết quả mong muốn:** viết được test vừa kiểm tra tín hiệu của Publisher, vừa xác nhận chính xác ngữ cảnh subscription; nhận diện lỗi mất Context hoặc lẫn ngữ cảnh giữa các request mà không lạm dụng `block()`, `ThreadLocal` hay global state.

## 2. `Context` và `ContextView`: bản chất dữ liệu

Các API nằm trong package:

```java
import reactor.util.context.Context;
import reactor.util.context.ContextView;
```

`Context` là một kho key–value bất biến (immutable), tối ưu cho lượng metadata nhỏ. `ContextView` là giao diện chỉ đọc.

| API | Tác dụng |
|---|---|
| `Context.empty()` | Tạo context rỗng |
| `Context.of(key, value)` | Tạo context có cặp key–value |
| `context.put(key, value)` | Trả về **Context mới** đã thêm/ghi đè key |
| `context.delete(key)` | Trả về Context mới bỏ một key |
| `context.putAll(other)` | Trả về Context mới có dữ liệu được hợp nhất |
| `view.hasKey(key)` | Kiểm tra key tồn tại |
| `view.get(key)` | Lấy value; có thể ném lỗi nếu thiếu key |
| `view.getOrDefault(key, defaultValue)` | Lấy giá trị hoặc fallback |
| `view.getOrEmpty(key)` | Lấy `Optional<T>` |
| `view.size()` | Đếm số cặp key–value |
| `view.stream()` | Duyệt entries |

Ví dụ:

```java
Context original = Context.of("tenant", "alpha");
Context updated = original.put("traceId", "trace-17");

System.out.println(original.hasKey("traceId")); // false
System.out.println(updated.hasKey("traceId"));  // true
```

`original` không bị sửa. Đây là đặc tính quan trọng giúp context của các subscriber tách biệt.

### 2.1. Không nhầm Reactor Context với các khái niệm khác

- `reactor.util.context.Context`: metadata theo subscription.
- `org.springframework.context.ApplicationContext`: bean container của Spring.
- `ServerWebExchange`: request/response HTTP trong WebFlux.
- `SecurityContext`: thông tin authentication/authorization của Spring Security.
- `ThreadLocal`: trạng thái gắn với thread, không tự đi theo một subscription qua nhiều scheduler.

Một `SecurityContext` có thể được lưu bên trong Reactor Context thông qua `ReactiveSecurityContextHolder`, nhưng hai kiểu Context này không đồng nhất.

### 2.2. Những gì nên và không nên đặt vào Reactor Context

Phù hợp:

- Correlation ID hoặc trace ID.
- Tenant identifier đã được xác minh.
- Security context do Spring Security tạo.
- Một số metadata dành cho thư viện tracing, logging hoặc authorization.

Không phù hợp:

- Danh sách hàng triệu bản ghi.
- Mutable state lớn chia sẻ giữa nhiều request.
- Một connection hoặc file resource cần quản lý lifecycle riêng.
- Mật khẩu thô hoặc token được log tùy tiện.
- Dữ liệu nghiệp vụ lớn đáng lẽ nên nằm trong `Mono<T>`/`Flux<T>`.

`Context` bất biến ở cấp cấu trúc, nhưng object value bên trong có thể mutable. Đừng diễn giải “immutable Context” thành “mọi value bên trong đều tự động thread-safe”.

## 3. Context gắn với subscriber, không gắn với biến Publisher

Một Publisher có thể được subscribe nhiều lần. Mỗi lần subscribe có thể có Context khác nhau.

```text
                Mono<String> dùng chung
                    |
             Mono.deferContextual(...)
                    ^
                    |
           Subscription propagation
              /              \
             /                \
     Subscriber A          Subscriber B
     Context tenant=A      Context tenant=B
             |                |
         "A:hello"         "B:hello"
```

Do đó không nên lưu một biến `currentTenant` trong singleton service rồi thay nó ở từng request. Một `@Service` có thể phục vụ hàng nghìn requests đồng thời, trong khi Reactor Context đi theo từng subscription.

### 3.1. Context được truyền theo chiều subscription

Một cách nhớ:

```text
assembly:       source --- map --- flatMap --- contextWrite --- subscriber
data signals:   onNext --------------------------------------->

Context:        source <--------------------------------------- subscriber
                               contextWrite bổ sung key
```

Tín hiệu dữ liệu thường đi từ source tới downstream. Context được nhìn theo hướng ngược lại, từ subscriber về upstream trong lúc thiết lập subscription.

Điều này giải thích vì sao vị trí của `contextWrite` ảnh hưởng tới operator nào nhìn thấy key.

### 3.2. Assembly khác subscription

Ví dụ:

```java
Mono<String> source = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("tenant", "public")));
```

Đoạn code tạo Publisher chưa đọc Context. Lambda trong `deferContextual` được thực thi khi có subscription phù hợp, lúc đó `ContextView` được cung cấp.

Nếu đọc tenant từ một biến global **trước khi** tạo Publisher, mỗi subscriber không còn cơ hội có ngữ cảnh độc lập.

## 4. Ghi và đọc Context bằng `contextWrite` và `deferContextual`

### 4.1. Viết Context

```java
Mono<String> result = Mono.deferContextual(ctx ->
                Mono.just("tenant=" + ctx.get("tenant")))
        .contextWrite(Context.of("tenant", "alpha"));
```

Expected value:

```text
tenant=alpha
```

`contextWrite(ContextView)` hợp nhất các entry cung cấp vào Context từ downstream và tạo một Context mới cho upstream. Có thể dùng overload function:

```java
.contextWrite(ctx -> ctx.put("tenant", "alpha"))
```

Không sửa Context tại chỗ. `put(...)` trả một Context mới.

### 4.2. Đọc Context an toàn

```java
Mono<String> tenant = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("tenant", "public")));
```

Ở đây thiếu key không làm hỏng request, vì contract cho phép tenant mặc định `"public"`.

Ngược lại, nếu tenant **bắt buộc**, hãy fail rõ ràng:

```java
Mono<String> tenantRequired = Mono.deferContextual(ctx -> {
    if (!ctx.hasKey("tenant")) {
        return Mono.error(
                new IllegalStateException("tenant missing"));
    }

    String tenantId = ctx.get("tenant");
    return Mono.just(tenantId);
});
```

Không gắn fallback `"public"` vào những thao tác cần ranh giới tenant nghiêm ngặt. Một fallback thuận tiện có thể trở thành lỗi phân quyền nghiêm trọng.

### 4.3. `ContextView` giúp tách đọc khỏi ghi

Một thư viện chỉ đọc Context nên nhận `ContextView`, không yêu cầu quyền tạo/ghi Context:

```java
private String resolveTenant(ContextView context) {
    return context.getOrDefault("tenant", "public");
}
```

API đọc chỉ cần những gì thực sự dùng. Ghi Context thường nên ở boundary như WebFilter, adapter, client hoặc test subscriber.

## 5. `StepVerifier`: kiểm tra tín hiệu lẫn Context

`StepVerifier` nằm trong artifact `reactor-test`, thường khai báo với scope `test`:

```xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>
```

Test đơn giản:

```java
StepVerifier.create(Mono.just("ok"))
        .expectNext("ok")
        .verifyComplete();
```

Khi cần đưa Context vào subscriber, tạo `StepVerifierOptions`:

```java
StepVerifierOptions options = StepVerifierOptions.create()
        .withInitialContext(Context.of("tenant", "alpha"));

StepVerifier.create(
                Mono.deferContextual(ctx ->
                        Mono.just(ctx.get("tenant"))),
                options)
        .expectNext("alpha")
        .verifyComplete();
```

`withInitialContext` đặt Context ban đầu ở **subscriber của StepVerifier**, không phải sửa một biến global, không phải ghi vào static map và không phải gọi `block()`.

### 5.1. Các API của `StepVerifierOptions`

| API | Dùng để |
|---|---|
| `create()` | Tạo options |
| `withInitialContext(Context)` | Gắn Context cho subscriber test |
| `scenarioName(String)` | Đặt tên kịch bản trong assertion diagnostics |
| `initialRequest(long)` | Điều khiển demand ban đầu khi test backpressure |
| `checkUnderRequesting(boolean)` | Cấu hình kiểm tra under-requesting |
| `copy()` | Tạo bản sao options |

Ví dụ:

```java
StepVerifierOptions options = StepVerifierOptions.create()
        .scenarioName("tenant-aware greeting")
        .withInitialContext(Context.of(
                "tenant", "alpha",
                "traceId", "req-17"));
```

Nếu test thất bại, `scenarioName` giúp phân biệt tình huống nào lỗi. Không sử dụng tên chứa token hoặc dữ liệu cá nhân.

### 5.2. Kiểm tra Context và output trong cùng test

```java
Mono<String> result = Mono.deferContextual(ctx ->
        Mono.just(ctx.get("tenant")));

StepVerifier.create(
                result,
                StepVerifierOptions.create()
                        .withInitialContext(
                                Context.of("tenant", "alpha")))
        .expectAccessibleContext()
        .contains("tenant", "alpha")
        .then()
        .expectNext("alpha")
        .verifyComplete();
```

Test kiểm tra **hai điều độc lập**:

1. Context được propagate tới vùng kiểm tra ở subscription phase và chứa `"tenant"="alpha"`.
2. Publisher phát `"alpha"` rồi complete.

Chỉ kiểm tra output có thể bỏ sót một pipeline vô tình hardcode `"alpha"`. Chỉ kiểm tra Context mà không kiểm tra output có thể bỏ sót logic đọc sai key.

## 6. `expectAccessibleContext()` và `ContextExpectations`

Sau khi gọi:

```java
.expectAccessibleContext()
```

StepVerifier chuyển sang đối tượng `StepVerifier.ContextExpectations<T>` để khai báo các assertion đối với Context được propagate trong giai đoạn subscription.

Những API quan trọng:

| API | Ý nghĩa |
|---|---|
| `.hasKey("tenant")` | Yêu cầu có key |
| `.contains("tenant", "alpha")` | Yêu cầu key có value chính xác |
| `.containsAllOf(Context.of(...))` | Yêu cầu chứa các cặp key–value |
| `.containsOnly(Context.of(...))` | Yêu cầu đúng các cặp, không có entry thêm |
| `.hasSize(2)` | Yêu cầu Context có đúng 2 entries |
| `.matches(predicate)` | Kiểm tra predicate tùy biến |
| `.matches(predicate, description)` | Predicate kèm mô tả lỗi |
| `.assertThat(consumer)` | Gọi assertion tùy biến |
| `.then()` | Quay lại kiểm tra các tín hiệu của Publisher |

### 6.1. Kiểm tra các key–value

```java
StepVerifier.create(
                Mono.just(5),
                StepVerifierOptions.create()
                        .withInitialContext(
                                Context.of("tenant", "alpha", "traceId", "t-1")))
        .expectAccessibleContext()
        .contains("tenant", "alpha")
        .hasKey("traceId")
        .hasSize(2)
        .then()
        .expectNext(5)
        .verifyComplete();
```

Không nên dùng `.containsOnly(...)` hoặc `.hasSize(...)` một cách máy móc trong ứng dụng WebFlux đầy đủ, vì thư viện tracing/security có thể thêm Context entries của riêng chúng. Test tập trung vào **các key mà code của bạn sở hữu** sẽ ít giòn hơn.

### 6.2. Predicate tùy biến

```java
StepVerifier.create(
                Mono.just("ready"),
                StepVerifierOptions.create()
                        .withInitialContext(
                                Context.of("traceId", "req-abc")))
        .expectAccessibleContext()
        .matches(
                ctx -> ctx.<String>get("traceId").startsWith("req-"),
                "traceId must start with req-")
        .then()
        .expectNext("ready")
        .verifyComplete();
```

Dùng `.matches(...)` cho điều kiện có thể diễn đạt gọn bằng predicate. Nếu cần nhiều assertion với thông báo riêng, dùng `.assertThat(...)`.

### 6.3. Assertion tùy biến

```java
StepVerifier.create(
                Mono.just(10),
                StepVerifierOptions.create()
                        .withInitialContext(
                                Context.of("tenant", "alpha")))
        .expectAccessibleContext()
        .assertThat(ctx -> {
            assertTrue(ctx.hasKey("tenant"));
            assertEquals("alpha", ctx.get("tenant"));
        })
        .then()
        .expectNext(10)
        .verifyComplete();
```

`assertTrue` và `assertEquals` ở đây từ JUnit Jupiter. Assertion được thực hiện khi StepVerifier chạy kịch bản, không phải khi dựng chuỗi assertion.

### 6.4. Không quên `.then()`

Sau `expectAccessibleContext()` các hàm `contains`, `hasKey`, `matches`, `assertThat` nằm trong `ContextExpectations`. Phải gọi `.then()` để quay lại builder kiểm tra `expectNext`, `expectComplete`, `expectError`...

Sai về cấu trúc:

```java
// Không hợp lệ: ContextExpectations không có expectNext.
// .expectAccessibleContext().contains("tenant", "alpha").expectNext("alpha")
```

Đúng:

```java
.expectAccessibleContext()
.contains("tenant", "alpha")
.then()
.expectNext("alpha")
.verifyComplete();
```

## 7. `expectNoAccessibleContext()` không có nghĩa “thiếu key”

`expectNoAccessibleContext()` là API chuyên biệt kiểm tra rằng StepVerifier **không quan sát được một Reactor Context được propagate** ở subscription phase. Trường hợp này có thể xảy ra với publisher không sử dụng infrastructure Reactor context hoặc publisher từ thư viện ngoài.

Nó **không** tương đương câu hỏi:

```text
Context có tồn tại nhưng thiếu key "tenant"?
```

Để kiểm tra thiếu key nghiệp vụ, hãy:

- Tạo subscriber không cung cấp key đó.
- Dùng `Mono.deferContextual(...)` đọc và phát error/fallback theo contract.
- Dùng `expectError(...)` hoặc `expectNext(...)` để assert hành vi.

Ví dụ:

```java
Mono<String> requireTenant = Mono.deferContextual(ctx -> {
    if (!ctx.hasKey("tenant")) {
        return Mono.error(new IllegalStateException("tenant missing"));
    }
    return Mono.just(ctx.get("tenant"));
});

StepVerifier.create(requireTenant)
        .expectErrorMatches(error ->
                error instanceof IllegalStateException
                && "tenant missing".equals(error.getMessage()))
        .verify();
```

Test đúng điều kiện **thiếu key**; không phụ thuộc việc external publisher có hay không có khả năng propagate Context.

### Khi nào không nên gọi `expectNoAccessibleContext()`?

- Để kiểm tra tenant không tồn tại.
- Để kiểm tra một JWT claim không tồn tại.
- Để khẳng định Spring Security user chưa xác thực.
- Để assert Context size bằng 0.
- Để test một operator Reactor thuần đơn giản mà bạn không chắc về accessibility contract.

Nếu mục tiêu là không có authentication, kiểm tra behavior của service hoặc `ReactiveSecurityContextHolder.getContext()` trực tiếp.

## 8. `contextWrite` ghi từ downstream lên upstream

Đây là quy tắc thường gây kết quả bất ngờ.

```java
Mono<String> source = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("tenant", "missing")));

Mono<String> result = source
        .contextWrite(ctx -> ctx.put("tenant", "inner"))
        .contextWrite(ctx -> ctx.put("tenant", "outer"));
```

Expected result:

```text
inner
```

Dòng `.contextWrite("outer")` gần subscriber hơn nên được áp dụng trước trong subscription phase. Dòng `.contextWrite("inner")` gần source hơn nên ghi đè key cho phần source ở upstream.

**Không kết luận dựa trên thứ tự “trên xuống” của code Java mà bỏ qua chiều subscription.**

### 8.1. `contextWrite` chỉ thay đổi Context thấy được ở upstream

```java
Mono<String> upstream = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("tenant", "missing")))
        .contextWrite(ctx -> ctx.put("tenant", "inner"));

Mono<String> result = upstream.flatMap(value ->
        Mono.deferContextual(ctx ->
                Mono.just(value + "|" +
                        ctx.getOrDefault("tenant", "missing"))));
```

Với subscriber không cung cấp tenant, giá trị mong đợi:

```text
inner|missing
```

Vì:

- Source bên trái `.contextWrite` thấy `"inner"`.
- `flatMap` ở downstream không được thừa kế một Context mới từ upstream.
- Inner `Mono.deferContextual(...)` của `flatMap` thấy Context của subscriber thực tế, không tự nhận thay đổi chỉ có hiệu lực upstream của operator trước đó.

Đây là loại bug mà test output bình thường có thể bỏ sót. Nên có test xác nhận cả vị trí đọc và nơi ghi Context.

### 8.2. Kết hợp initial Context với override

Nếu StepVerifier đưa `"tenant"="outer"` vào subscriber, source có `.contextWrite(... "inner")` sẽ đọc `"inner"`; phần downstream không nằm trong phạm vi override vẫn có thể thấy `"outer"`.

Lưu ý khi dùng `expectAccessibleContext()`: assertion đó kiểm tra **Context được công cụ nhìn thấy trong subscription phase**, không phải lời khẳng định rằng mọi operator trong một chuỗi có nhiều `contextWrite` đều quan sát đúng cùng một Context. Để xác minh giá trị tại điểm đọc quan trọng, hãy cho operator dùng `deferContextual` xuất giá trị ra và kiểm tra tín hiệu.

## 9. Hai subscriber phải độc lập với nhau

Một bài test quan trọng trong dịch vụ multi-tenant:

```java
Mono<String> shared = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("tenant", "public")));

StepVerifier.create(
                shared,
                StepVerifierOptions.create()
                        .withInitialContext(Context.of("tenant", "A")))
        .expectNext("A")
        .verifyComplete();

StepVerifier.create(
                shared,
                StepVerifierOptions.create()
                        .withInitialContext(Context.of("tenant", "B")))
        .expectNext("B")
        .verifyComplete();
```

Một Publisher dùng chung được subscribe hai lần với hai Context khác nhau. Kết quả không bị lẫn.

### 9.1. Kiểm tra thời điểm đọc

Dùng `AtomicInteger` để chứng minh việc đọc Context chỉ xảy ra khi subscribe:

```java
AtomicInteger reads = new AtomicInteger();

Mono<String> source = Mono.deferContextual(ctx -> {
    reads.incrementAndGet();
    return Mono.just(ctx.getOrDefault("tenant", "public"));
});

assertEquals(0, reads.get());

StepVerifier.create(
                source,
                StepVerifierOptions.create()
                        .withInitialContext(Context.of("tenant", "A")))
        .expectNext("A")
        .verifyComplete();

assertEquals(1, reads.get());
```

Đây là cách kiểm tra **deferred execution**, không phải đo hiệu năng.

### 9.2. Không dùng static field cho tenant

Anti-pattern:

```java
static String currentTenant;
```

Nếu request A đặt `"A"`, request B đặt `"B"` trước khi A dùng lại field, kết quả có thể lẫn tenant. Dùng Reactor Context hoặc truyền tenant qua tham số nghiệp vụ đã được kiểm tra thay vì một trạng thái mutable global.

## 10. Context và các operator `map`, `flatMap`, `concatMap`

### 10.1. `map` chỉ nhận giá trị của stream

```java
Mono<String> item = Mono.just("book")
        .map(value -> value.toUpperCase());
```

Lambda `map` nhận `value`, không có đối số `ContextView`. Để đọc Context trong logic cần nó, tạo operator có ý thức về Context:

```java
Mono<String> labeled = Mono.just("book")
        .flatMap(value -> Mono.deferContextual(ctx ->
                Mono.just(ctx.getOrDefault("tenant", "public") + ":" + value)));
```

### 10.2. `flatMap` và inner publisher

```java
Flux<String> result = Flux.just("one", "two")
        .flatMap(value ->
                Mono.deferContextual(ctx ->
                        Mono.just(ctx.get("tenant") + ":" + value)));
```

Trong pipeline Reactor thông thường, inner publisher có thể đọc Context của subscription tương ứng. `flatMap` không bảo đảm output order nếu các inner publishers bất đồng bộ. Nếu cần thứ tự, dùng `concatMap`.

### 10.3. `concatMap` khi cần thứ tự

```java
Flux<String> result = Flux.just("one", "two")
        .concatMap(value ->
                Mono.deferContextual(ctx ->
                        Mono.just(ctx.get("tenant") + ":" + value)));
```

Expected:

```text
A:one
A:two
```

nếu subscriber có `"tenant"="A"`.

Đừng dùng các biến `ThreadLocal` hoặc mutable counters toàn cục để thay cho Context propagation khi nhiều inner publishers chạy đồng thời.

## 11. Context và scheduler: đừng đồng nhất với ThreadLocal

Một luồng có thể chuyển scheduler:

```java
Mono<String> result = Mono.just("item")
        .publishOn(Schedulers.parallel())
        .flatMap(value -> Mono.deferContextual(ctx ->
                Mono.just(ctx.getOrDefault("tenant", "public")
                        + ":" + value)));
```

Khi StepVerifier đưa tenant vào Context, inner `deferContextual` vẫn có thể đọc được trong reactive chain, dù execution chuyển thread.

```java
StepVerifier.create(
                result,
                StepVerifierOptions.create()
                        .withInitialContext(Context.of("tenant", "A")))
        .expectNext("A:item")
        .expectComplete()
        .verify(Duration.ofSeconds(3));
```

Nhưng:

```java
ThreadLocal<String> tenant = new ThreadLocal<>();
```

không được Reactor tự truyền qua mọi scheduler một cách mặc định. Một test chỉ chạy trên một thread có thể vô tình “pass” khi code dựa vào ThreadLocal, rồi lỗi ở môi trường có `publishOn`/`subscribeOn`.

### 11.1. Micrometer Context Propagation

Reactor có thể tích hợp thư viện `io.micrometer:context-propagation` để bridge các giá trị giữa Reactor Context và `ThreadLocal` trong những điều kiện được cấu hình. Những API như `contextCapture()`, `Hooks.enableAutomaticContextPropagation()` và `ThreadLocalAccessor` liên quan chế độ propagation đó.

Đây là một cơ chế **khác** với Reactor Context chuẩn. Không giả định chỉ cần gọi `contextWrite` thì MDC ThreadLocal tự được gắn trên mọi callback.

Khi test cơ chế Micrometer:

- Đăng ký `ThreadLocalAccessor` phù hợp.
- Kiểm soát lúc bật/tắt hook global.
- Tránh rò rỉ cấu hình giữa các test chạy song song.
- Kiểm tra restoration/cleanup, không chỉ giá trị xuất hiện trong callback.
- Cẩn thận việc hook toàn cục có thể ảnh hưởng các Publisher được tạo trước/sau.

Trong phần lớn business services, đọc trực tiếp Reactor Context bằng `deferContextual` đơn giản và dễ kiểm thử hơn bridge với ThreadLocal.

## 12. Context trong Spring WebFlux HTTP request

Một WebFlux `WebFilter` có thể đặt trace ID hoặc tenant ID đã được xác minh vào Reactor Context để downstream service đọc được.

Ví dụ minh họa:

```java
@Component
public class TraceContextWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String traceId = UUID.randomUUID().toString();

        return chain.filter(exchange)
                .contextWrite(ctx -> ctx.put("traceId", traceId));
    }
}
```

Các import chính:

```java
import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;
```

Dịch vụ downstream:

```java
public Mono<String> traceId() {
    return Mono.deferContextual(ctx ->
            Mono.just(ctx.getOrDefault("traceId", "missing")));
}
```

Đây là cách test Context ở lớp service không phụ thuộc vào HTTP server: dùng `StepVerifierOptions.withInitialContext` để tái hiện ngữ cảnh mà WebFilter sẽ cung cấp.

### 12.1. Trust boundary

Đối với tenant ID hoặc user identity, WebFilter không được tin ngay một header như `X-Tenant-Id` do client tự gửi. Cần xác thực và kiểm tra quyền trước khi đặt identity vào Context. StepVerifier chỉ chứng minh data propagation; nó **không** chứng minh nguồn dữ liệu đó đáng tin.

### 12.2. Kiểm thử ở hai tầng

- **Unit test service**: đưa Context bằng `withInitialContext(...)` rồi kiểm tra output/error.
- **WebTestClient integration test**: gửi HTTP request qua filter chain và xác nhận request cuối cùng thấy đúng context, đồng thời kiểm tra authentication/authorization nếu có.

Cả hai cần thiết khi metadata được thiết lập ở WebFilter nhưng được sử dụng trong service.

## 13. Context của Spring Security trong Reactor

Spring Security Reactive lưu thông tin SecurityContext trong Reactor Context và đọc qua:

```java
ReactiveSecurityContextHolder.getContext()
```

Ví dụ service:

```java
public Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
            .map(securityContext ->
                    securityContext.getAuthentication().getName());
}
```

Một unit test có thể tạo Authentication phù hợp và gắn vào Context:

```java
Authentication authentication =
        new UsernamePasswordAuthenticationToken(
                "alice",
                "unused",
                List.of(new SimpleGrantedAuthority("ROLE_READER")));

Mono<String> currentUser =
        ReactiveSecurityContextHolder.getContext()
                .map(security ->
                        security.getAuthentication().getName())
                .contextWrite(
                        ReactiveSecurityContextHolder
                                .withAuthentication(authentication));

StepVerifier.create(currentUser)
        .expectNext("alice")
        .verifyComplete();
```

Điều này kiểm tra **service đọc principal đã có trong Reactor Context**. Nó **không** xác minh password, JWT signature, issuer, audience, CSRF hoặc HTTP security filter chain.

Muốn kiểm tra toàn bộ authentication/authorization của endpoint, dùng `WebTestClient` cùng Spring Security Test hoặc integration test với credential thật theo mục tiêu.

### 13.1. Đừng hardcode internal Context key của Spring Security

Spring Security quản lý cách lưu SecurityContext trong Reactor Context. Không tự thêm `"spring.security.context"` hoặc một key đoán mò vào `Context.of(...)` rồi cho rằng Spring Security sẽ đọc nó.

Dùng public API:

```java
ReactiveSecurityContextHolder.withAuthentication(authentication)
```

hoặc testing support của Spring Security, tránh phụ thuộc vào key private có thể thay đổi.

## 14. Context qua `WebClient` và các ranh giới mạng

Reactor Context là metadata **nội bộ của một subscription JVM**. Khi ứng dụng gọi HTTP bằng WebClient hoặc RSocket tới một process khác, Context không tự biến thành HTTP headers, RSocket metadata hoặc trace context ở process kia.

Ví dụ:

```text
Spring WebFlux service A
    |
    | Reactor Context: traceId=trace-1
    |
    v
WebClient outbound HTTP
    |
    | HTTP headers chỉ chứa gì client/filter chủ động gửi
    v
Service B
```

Nếu muốn propagate trace ID qua mạng, cần một filter/interceptor/tracing library chuyển metadata được phép thành header và phía nhận kiểm tra/khởi tạo lại context. Không tự chuyển access token sang mọi host đích.

### 14.1. Test Context không thay thế integration test metadata

Một StepVerifier test:

```java
StepVerifier.create(service.send(...), options.withInitialContext(...))
```

chỉ kiểm tra publisher của process hiện tại nhìn thấy Context như thế nào. Nó không chứng minh WebClient thật đã gửi `traceparent`, `X-Request-Id` hoặc một header bất kỳ. Cần thêm MockWebServer/WireMock hoặc một HTTP test server để verify outbound request.

### 14.2. Dữ liệu tenant và security

Ngay cả khi tenant được đặt trong Reactor Context, outbound API cần chính sách rõ ràng về tenant/authorization. Reactor Context không tự mã hóa, xác thực hoặc ký metadata khi đi qua mạng.

## 15. Kỹ thuật test lỗi thiếu, sai kiểu hoặc bị ghi đè key

Nên bao phủ ít nhất ba trường hợp.

### 15.1. Thiếu key bắt buộc

```java
Mono<String> required = Mono.deferContextual(ctx -> {
    if (!ctx.hasKey("tenant")) {
        return Mono.error(
                new IllegalStateException("tenant missing"));
    }
    return Mono.just(ctx.get("tenant"));
});

StepVerifier.create(required)
        .expectErrorMatches(error ->
                error instanceof IllegalStateException
                && "tenant missing".equals(error.getMessage()))
        .verify();
```

Đây là negative test có terminal error rõ ràng.

### 15.2. Sai kiểu value

Vì key/value là `Object`, code sau có thể lỗi runtime nếu schema Context không thống nhất:

```java
Mono<String> readTenant = Mono.deferContextual(ctx -> {
    String tenant = ctx.get("tenant");
    return Mono.just(tenant);
});

StepVerifier.create(
                readTenant,
                StepVerifierOptions.create()
                        .withInitialContext(Context.of("tenant", 123)))
        .expectError(ClassCastException.class)
        .verify();
```

Trong production, định nghĩa key có kiểu nhất quán hoặc dùng một kiểu wrapper rõ ràng để tránh nhầm key. Không dùng một chuỗi `"id"` chung cho nhiều metadata khác kiểu từ các thư viện.

### 15.3. Bị ghi đè đúng/không đúng scope

```java
Mono<String> source = Mono.deferContextual(ctx ->
        Mono.just(ctx.get("tenant")));

Mono<String> result =
        source.contextWrite(ctx -> ctx.put("tenant", "inner"));

StepVerifier.create(
                result,
                StepVerifierOptions.create()
                        .withInitialContext(Context.of("tenant", "outer")))
        .expectNext("inner")
        .verifyComplete();
```

Nếu service được thiết kế để **không** ghi đè tenant của caller, test này cho thấy override đang xảy ra; khi đó sửa code của service thay vì điều chỉnh assertion cho pass.

## 16. `ContextView` với `get`, `getOrDefault` và `getOrEmpty`

Việc chọn API đọc Context quyết định error contract.

| API | Khi key thiếu | Nên dùng khi |
|---|---|---|
| `get(key)` | Ném exception | Invariant đã được xác lập |
| `hasKey(key)` | `false` | Cần kiểm tra hiện diện trước |
| `getOrDefault(key, fallback)` | Dùng fallback | Metadata tùy chọn |
| `getOrEmpty(key)` | `Optional.empty()` | Muốn biểu diễn optional rõ ràng |

Ví dụ:

```java
Mono<String> optional = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("traceId", "unknown")));
```

Nếu key thiếu, test mong `"unknown"`. Với tenant dùng để phân vùng dữ liệu, nên fail khi thiếu thay vì rơi về một tenant mặc định bất ngờ.

### 16.1. Key nên độc nhất và khó va chạm

Có thể dùng một object key do ứng dụng sở hữu:

```java
public static final Object TENANT_KEY = new Object();
```

Các component thuộc cùng module phải chia sẻ chính xác cùng reference key. Cách này giảm va chạm với key `"tenant"` của thư viện khác. Với ví dụ học tập và contract public rõ ràng, dùng String key vẫn dễ đọc.

### 16.2. Không đặt `null` trong Context

`Context` không được thiết kế để chứa value null. Dùng Optional/record phù hợp hoặc xóa key nếu không có giá trị.

Không viết:

```java
// Không hợp lệ về contract:
Context.of("tenant", null);
```

Hãy test trường hợp “không có tenant” bằng việc **không đặt key**, không phải đặt value null.

## 17. Kết hợp Context và virtual time

Reactor Context không gắn với clock. Tuy nhiên, nếu pipeline có delay, retry hoặc timeout, có thể kết hợp `withInitialContext` với `StepVerifier.withVirtualTime(...)`.

```java
StepVerifierOptions options = StepVerifierOptions.create()
        .withInitialContext(Context.of("tenant", "alpha"));

StepVerifier.withVirtualTime(
                () -> Mono.delay(Duration.ofHours(1))
                        .flatMap(tick -> Mono.deferContextual(ctx ->
                                Mono.just(ctx.get("tenant")))),
                options)
        .thenAwait(Duration.ofHours(1))
        .expectNext("alpha")
        .verifyComplete();
```

`withVirtualTime` không đợi một giờ thật. Nó dùng virtual scheduler để tiến thời gian.

Điều kiện quan trọng:

- Tạo các time-based operators **bên trong lambda** truyền cho `withVirtualTime`.
- Đừng khởi tạo scheduler riêng ngoài lambda rồi mong virtual time điều khiển.
- Cẩn thận timeout và request demand trong test.
- Hạn chế thay đổi global hooks/schedulers khi test chạy song song.

Virtual time kiểm tra semantics thời gian, còn `withInitialContext` kiểm tra ngữ cảnh của subscriber. Hai cơ chế có thể kết hợp nhưng độc lập.

## 18. Dự án Java 17+ chạy được với Reactor Test

Dự án minh họa bằng Spring Boot 3.3.5 làm dependency management, nhưng bài kiểm thử thuần Reactor không cần khởi động Spring ApplicationContext. Điều này giúp test nhanh, tập trung vào đúng nội dung **Reactor Context**.

Bao gồm:

- Service đọc tenant/trace ID bằng `deferContextual`.
- Required tenant và fallback tenant.
- Scope override của `contextWrite`.
- Inner `flatMap` với Context.
- Context tách biệt ở từng subscription.
- Async boundary với `publishOn`.
- Các assertion `expectAccessibleContext`, `contains`, `hasKey`, `matches`, `assertThat`, `hasSize`.
- Virtual time + initial Context.
- Spring Security reactive context thông qua public API.

### 18.1. Cấu trúc thư mục

```text
reactor-context-testing/
├── pom.xml
└── src/
    ├── main/java/edu/demo/context/
    │   └── ContextGreetingService.java
    └── test/java/edu/demo/context/
        ├── ContextGreetingServiceTests.java
        └── SecurityContextTests.java
```

### 18.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>reactor-context-testing</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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

`spring-boot-starter-security` cung cấp Spring Security core và reactive context holder. Nó không tự tạo HTTP endpoint trong dự án này. `reactor-test` chỉ cần trong scope test.

### 18.3. `ContextGreetingService.java`

```java
package edu.demo.context;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public final class ContextGreetingService {

    public static final String TENANT = "tenant";
    public static final String TRACE_ID = "traceId";

    public Mono<String> greet(String name) {
        return Mono.deferContextual(ctx -> {
            String tenant = ctx.getOrDefault(TENANT, "public");
            String trace = ctx.getOrDefault(TRACE_ID, "none");

            return Mono.just(tenant + ":" + name + ":" + trace);
        });
    }

    public Mono<String> requiredTenant() {
        return Mono.deferContextual(ctx -> {
            if (!ctx.hasKey(TENANT)) {
                return Mono.error(
                        new IllegalStateException("tenant missing"));
            }

            String tenant = ctx.get(TENANT);

            if (tenant.isBlank()) {
                return Mono.error(
                        new IllegalArgumentException("tenant empty"));
            }

            return Mono.just(tenant);
        });
    }

    public Flux<String> markAll(Flux<String> items) {
        return items.concatMap(item ->
                Mono.deferContextual(ctx -> {
                    String tenant =
                            ctx.getOrDefault(TENANT, "public");
                    return Mono.just(tenant + ":" + item);
                }));
    }

    public Mono<String> scopedRead() {
        Mono<String> upstream = Mono.deferContextual(ctx ->
                Mono.just(ctx.getOrDefault(TENANT, "missing")))
                .contextWrite(ctx -> ctx.put(TENANT, "inner"));

        return upstream.flatMap(value ->
                Mono.deferContextual(ctx ->
                        Mono.just(value + "|"
                                + ctx.getOrDefault(TENANT, "missing"))));
    }

    public Mono<String> asyncGreeting(String name) {
        return Mono.just(name)
                .publishOn(Schedulers.parallel())
                .flatMap(value ->
                        Mono.deferContextual(ctx -> {
                            String tenant =
                                    ctx.getOrDefault(TENANT, "public");

                            return Mono.just(tenant + ":" + value);
                        }));
    }
}
```

Giải thích:

- `greet` đọc tenant và trace ID khi subscribe.
- `requiredTenant` phát error nếu không có tenant.
- `markAll` dùng `concatMap` để giữ thứ tự.
- `scopedRead` cho thấy `contextWrite` chỉ áp dụng upstream.
- `asyncGreeting` kiểm tra Context propagation sau `publishOn`.

Không có method nào lưu tenant trong field mutable, nên một service singleton có thể phục vụ nhiều subscribers khác nhau.

### 18.4. `ContextGreetingServiceTests.java`

```java
package edu.demo.context;

import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.util.context.Context;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ContextGreetingServiceTests {

    private final ContextGreetingService service =
            new ContextGreetingService();

    @Test
    void initialContextIsVisibleToPublisherAndVerifier() {
        StepVerifierOptions options = StepVerifierOptions.create()
                .scenarioName("tenant and trace")
                .withInitialContext(Context.of(
                        ContextGreetingService.TENANT, "alpha",
                        ContextGreetingService.TRACE_ID, "req-7"));

        StepVerifier.create(service.greet("An"), options)
                .expectAccessibleContext()
                .contains(ContextGreetingService.TENANT, "alpha")
                .hasKey(ContextGreetingService.TRACE_ID)
                .matches(ctx ->
                                Objects.equals(
                                        ctx.get("traceId"),
                                        "req-7"),
                        "traceId equals req-7")
                .then()
                .expectNext("alpha:An:req-7")
                .verifyComplete();
    }

    @Test
    void contextExpectationsCanAssertExactSmallContext() {
        StepVerifierOptions options = StepVerifierOptions.create()
                .withInitialContext(Context.of(
                        "tenant", "alpha",
                        "traceId", "req-8"));

        StepVerifier.create(Mono.just(10), options)
                .expectAccessibleContext()
                .hasSize(2)
                .containsAllOf(
                        Context.of("tenant", "alpha", "traceId", "req-8"))
                .assertThat(ctx -> {
                    assertTrue(ctx.hasKey("tenant"));
                    assertEquals("alpha", ctx.get("tenant"));
                })
                .then()
                .expectNext(10)
                .verifyComplete();
    }

    @Test
    void missingOptionalContextUsesFallbacks() {
        StepVerifier.create(service.greet("An"))
                .expectNext("public:An:none")
                .verifyComplete();
    }

    @Test
    void missingRequiredTenantIsError() {
        StepVerifier.create(service.requiredTenant())
                .expectErrorMatches(error ->
                        error instanceof IllegalStateException
                                && "tenant missing".equals(
                                        error.getMessage()))
                .verify();
    }

    @Test
    void blankRequiredTenantIsError() {
        StepVerifier.create(
                        service.requiredTenant(),
                        StepVerifierOptions.create()
                                .withInitialContext(
                                        Context.of("tenant", "")))
                .expectError(IllegalArgumentException.class)
                .verify();
    }

    @Test
    void eachSubscriptionHasItsOwnContext() {
        Mono<String> shared = service.greet("An");

        StepVerifier.create(
                        shared,
                        StepVerifierOptions.create()
                                .withInitialContext(
                                        Context.of("tenant", "A")))
                .expectNext("A:An:none")
                .verifyComplete();

        StepVerifier.create(
                        shared,
                        StepVerifierOptions.create()
                                .withInitialContext(
                                        Context.of("tenant", "B")))
                .expectNext("B:An:none")
                .verifyComplete();
    }

    @Test
    void contextIsReadAtSubscriptionTime() {
        AtomicInteger reads = new AtomicInteger();

        Mono<String> source = Mono.deferContextual(ctx -> {
            reads.incrementAndGet();

            return Mono.just(
                    ctx.getOrDefault("tenant", "public"));
        });

        assertEquals(0, reads.get());

        StepVerifier.create(
                        source,
                        StepVerifierOptions.create()
                                .withInitialContext(
                                        Context.of("tenant", "A")))
                .expectNext("A")
                .verifyComplete();

        assertEquals(1, reads.get());
    }

    @Test
    void contextWriteCanOverrideInitialContext() {
        Mono<String> result = service.requiredTenant()
                .contextWrite(ctx -> ctx.put("tenant", "inner"));

        StepVerifier.create(
                        result,
                        StepVerifierOptions.create()
                                .withInitialContext(
                                        Context.of("tenant", "outer")))
                .expectNext("inner")
                .verifyComplete();
    }

    @Test
    void contextWriteClosestToSourceWinsForThatSource() {
        Mono<String> result = service.requiredTenant()
                .contextWrite(ctx -> ctx.put("tenant", "source"))
                .contextWrite(ctx -> ctx.put("tenant", "subscriber"));

        StepVerifier.create(result)
                .expectNext("source")
                .verifyComplete();
    }

    @Test
    void contextWriteDoesNotModifyDownstreamContext() {
        StepVerifier.create(service.scopedRead())
                .expectNext("inner|missing")
                .verifyComplete();
    }

    @Test
    void downstreamCanStillReadInitialContext() {
        StepVerifier.create(
                        service.scopedRead(),
                        StepVerifierOptions.create()
                                .withInitialContext(
                                        Context.of("tenant", "outer")))
                .expectNext("inner|outer")
                .verifyComplete();
    }

    @Test
    void concatMapRetainsContextAndItemOrder() {
        StepVerifier.create(
                        service.markAll(
                                Flux.just("one", "two", "three")),
                        StepVerifierOptions.create()
                                .withInitialContext(
                                        Context.of("tenant", "A")))
                .expectNext("A:one", "A:two", "A:three")
                .verifyComplete();
    }

    @Test
    void contextSurvivesPublishOnSchedulerSwitch() {
        StepVerifier.create(
                        service.asyncGreeting("An"),
                        StepVerifierOptions.create()
                                .withInitialContext(
                                        Context.of("tenant", "A")))
                .expectNext("A:An")
                .expectComplete()
                .verify(Duration.ofSeconds(3));
    }

    @Test
    void immutableContextOperationsDoNotChangeOriginal() {
        Context original = Context.of("tenant", "A");
        Context updated = original.put("traceId", "t-1");

        assertFalse(original.hasKey("traceId"));
        assertTrue(updated.hasKey("traceId"));
        assertEquals("A", original.get("tenant"));
        assertEquals("A", updated.get("tenant"));
    }

    @Test
    void virtualTimeAndInitialContextWorkTogether() {
        StepVerifierOptions options = StepVerifierOptions.create()
                .withInitialContext(Context.of("tenant", "alpha"));

        StepVerifier.withVirtualTime(
                        () -> Mono.delay(Duration.ofHours(1))
                                .flatMap(tick ->
                                        service.requiredTenant()),
                        options)
                .thenAwait(Duration.ofHours(1))
                .expectNext("alpha")
                .verifyComplete();
    }
}
```

Bộ test này gồm 15 method, trong đó có test khởi tạo Context, kiểm tra ContextExpectations, fallback, negative cases, nhiều subscriptions, override scope, `concatMap`, scheduler switch, immutable context và virtual time.

Các test `expectAccessibleContext()` dùng **initial context** của chính verifier làm nguồn dữ liệu rõ ràng. Những test `contextWrite` dùng kết quả đọc bằng `deferContextual` để xác nhận scope override. Việc tách hai nhóm giúp tránh nhầm “Context nhìn thấy ở một điểm” với “Context nhìn thấy ở mọi operator”.

### 18.5. `SecurityContextTests.java`

```java
package edu.demo.context;

import java.util.List;

import org.junit.jupiter.api.Test;

import org.springframework.security.authentication
        .UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority
        .SimpleGrantedAuthority;
import org.springframework.security.core.context
        .ReactiveSecurityContextHolder;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class SecurityContextTests {

    @Test
    void reactiveSecurityContextHolderReadsAuthentication() {
        Authentication authentication =
                new UsernamePasswordAuthenticationToken(
                        "alice",
                        "unused",
                        List.of(new SimpleGrantedAuthority(
                                "ROLE_READER")));

        Mono<String> currentUsername =
                ReactiveSecurityContextHolder.getContext()
                        .map(security ->
                                security.getAuthentication().getName())
                        .contextWrite(
                                ReactiveSecurityContextHolder
                                        .withAuthentication(authentication));

        StepVerifier.create(currentUsername)
                .expectNext("alice")
                .verifyComplete();
    }

    @Test
    void absentSecurityContextDoesNotInventPrincipal() {
        Mono<String> name =
                ReactiveSecurityContextHolder.getContext()
                        .map(security ->
                                security.getAuthentication().getName());

        StepVerifier.create(name)
                .verifyComplete();
    }
}
```

Hai test này xác nhận việc đọc SecurityContext qua public API. Kết quả mặc định khi không có SecurityContext là empty publisher, chứ không phải một user `"anonymous"` do test tự tạo.

Test không xác thực mật khẩu, token hoặc HTTP security chain. Để kiểm tra HTTP 401/403, dùng `WebTestClient` với cấu hình Spring Security phù hợp.

### 18.6. Chạy thử

Trong thư mục chứa `pom.xml`:

```bash
mvn test
```

Kết quả kỳ vọng khi Maven chạy thành công:

```text
Tests run: 17, Failures: 0, Errors: 0, Skipped: 0
```

Tổng số test được khai báo: **15** trong `ContextGreetingServiceTests` và **2** trong `SecurityContextTests`.

Dòng trên là **kết quả mong đợi**, không phải kết quả đã thực thi trong môi trường biên soạn. Khi triển khai thực tế, cần chạy Maven và xác minh phiên bản Reactor do Spring Boot BOM quản lý.

## 19. Những lỗi thường gặp khi kiểm tra Reactor Context

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Chỉ kiểm tra `expectNext` | Có thể bỏ sót Context propagation | Dùng `withInitialContext` + `expectAccessibleContext` hoặc assert kết quả `deferContextual` |
| Quên `.then()` sau ContextExpectations | Không thể chuyển sang `expectNext` | Gọi `.then()` |
| Dùng `expectNoAccessibleContext()` để kiểm tra thiếu tenant | Test sai đặc tính | Dùng `deferContextual` kiểm tra thiếu key |
| Đặt `contextWrite` phía trên điểm đọc theo suy nghĩ data flow | Operator không nhìn thấy key | Xét chiều subscription từ downstream lên upstream |
| Nghĩ `contextWrite` sửa Context của mọi operator | Downstream đọc giá trị khác | Kiểm tra scope tại điểm đọc thật |
| Tưởng Context gắn với biến `Mono` | Hai subscriber có thể cần context khác | Test từng subscriber với initial context riêng |
| Dùng `ThreadLocal` làm tenant chính | Mất ngữ cảnh khi scheduler đổi thread | Dùng Reactor Context |
| `Context.get` với key không tồn tại | `NoSuchElementException` hoặc lỗi tương ứng | Dùng hasKey/getOrDefault/getOrEmpty theo contract |
| Dùng cùng key với hai kiểu object | `ClassCastException` | Định nghĩa typed keys và thống nhất schema |
| Đặt mutable object trong Context | Race khi object bị sửa đồng thời | Dùng immutable value hoặc quản lý đồng bộ rõ |
| Lưu Context trong static field | Rò dữ liệu giữa requests | Chỉ đọc trong subscription |
| Test hasSize chính xác khi tracing/security thêm keys | Test giòn, fail khi thay instrumentation | Assert key/value mình sở hữu |
| Chỉ gọi `StepVerifier.create` mà không `verify...` | Kịch bản không chạy | Kết thúc bằng `verifyComplete`, `verifyError` hoặc `verify` |
| Không giới hạn thời gian cho test async thực | Test có thể treo | Dùng `verify(Duration)` hoặc virtual time phù hợp |
| Tạo `Mono.delay` ngoài supplier virtual time | Virtual scheduler không điều khiển | Tạo publisher bên trong lambda `withVirtualTime` |
| Bật global propagation Hooks trong test mà không cleanup | Ảnh hưởng test khác | Thiết lập/khôi phục hook có kiểm soát |
| Nghĩ Context tự qua HTTP/WebSocket/RSocket | Metadata không tới service khác | Dùng propagation ở network boundary |
| Tự gắn Authentication đã xác thực từ untrusted header | Privilege escalation | Dùng authentication manager/Spring Security |
| Đưa token/raw PII vào log/test snapshot | Rò thông tin | Redact/mask và chỉ kiểm tra metadata an toàn |
| Dùng `block()` trong WebFlux service | Chặn event loop | Return/compose reactive publisher |
| So sánh Context key `"tenant"` do hai thư viện sở hữu | Collision và override bất ngờ | Dùng key riêng/type wrapper |

## 20. Checklist để viết test tốt

### Thiết kế Context

- Key nào là bắt buộc, key nào tùy chọn?
- Giá trị key có kiểu nhất quán không?
- Key do component nào tạo, ai được phép ghi đè?
- Có dùng immutable data và tránh secret thô không?
- Context có được tạo tại boundary tin cậy không?

### Unit tests với StepVerifier

- Có `withInitialContext` cho metadata được subscriber cung cấp?
- Có `.expectAccessibleContext().contains(...)` cho propagation khi cần?
- Có `.then()` trước sequence assertions?
- Có assert `onNext`, completion hoặc error đúng contract?
- Có test thiếu key và fallback?
- Có test override `contextWrite`?
- Có test nhiều subscriber độc lập?
- Có test nested `flatMap`/`concatMap` nếu code dùng?
- Có test khi `publishOn`/`subscribeOn` thay đổi execution?
- Có timeout cho test async có nguy cơ không hoàn tất?

### Integration với Spring WebFlux

- WebFilter có đặt Context sau khi xác minh metadata chưa?
- Controller/service có đọc `deferContextual` không?
- Security context có do Spring Security quản lý không?
- Có test HTTP 401/403 riêng với WebTestClient?
- Outbound WebClient có propagate header đúng theo contract không?
- Có test hai request đồng thời để phát hiện lẫn tenant không?

### Vận hành

- Trace ID/correlation ID có được gắn nhất quán?
- Có tránh log full Reactor Context chứa credential?
- MDC/ThreadLocal propagation có được cấu hình và test tách biệt?
- Không có static context chứa trạng thái người dùng?
- Không có global hooks bị bỏ lại sau test?
- Tracing instrumentation không khiến test phụ thuộc Context size cứng nhắc?

## 21. Bài tập tự kiểm tra

**Bài 1.** `Context` thuộc về Publisher hay subscriber?

**Đáp án:** Nó gắn với subscription/subscriber; cùng một Publisher có thể được subscribe nhiều lần với Context khác nhau.

**Bài 2.** `context.put(...)` có thay đổi object Context ban đầu không?

**Đáp án:** Không. Context immutable; `put` trả về một Context mới.

**Bài 3.** Đưa tenant vào subscriber của StepVerifier bằng API nào?

**Đáp án:** `StepVerifierOptions.create().withInitialContext(Context.of("tenant","alpha"))`.

**Bài 4.** `expectAccessibleContext()` dùng khi nào?

**Đáp án:** Khi muốn assert Context được propagate và quan sát trong subscription phase; có thể nối với `.contains`, `.hasKey`, `.matches`, `.assertThat`.

**Bài 5.** Sau `.expectAccessibleContext().contains(...)` cần gọi gì trước `expectNext`?

**Đáp án:** `.then()`.

**Bài 6.** `expectNoAccessibleContext()` có chứng minh thiếu key `"tenant"` không?

**Đáp án:** Không. Nó kiểm tra khả năng truy cập Reactor Context trong subscription phase. Thiếu key nghiệp vụ nên được kiểm tra qua `deferContextual` và output/error contract.

**Bài 7.** Vì sao `contextWrite` gần source hơn có thể ghi đè giá trị ở downstream?

**Đáp án:** Vì Context được truyền từ subscriber lên upstream trong lúc subscribe. Operator gần source hơn áp dụng biến đổi sau và source thấy giá trị mới.

**Bài 8.** `publishOn` có làm mất Reactor Context không?

**Đáp án:** Trong chuỗi Reactor thông thường, Context tiếp tục đi theo subscription; ThreadLocal không có bảo đảm giống vậy nếu không cấu hình propagation bridge.

**Bài 9.** Unit test đọc `ReactiveSecurityContextHolder` có đủ chứng minh JWT hợp lệ không?

**Đáp án:** Không. Nó chỉ kiểm tra service đọc SecurityContext; JWT signature/issuer/audience/expiry cần test authentication pipeline.

**Bài 10.** Khi cần tiến một giờ ảo trong test Context, dùng API nào?

**Đáp án:** `StepVerifier.withVirtualTime(...)` và `thenAwait(Duration.ofHours(1))`; tạo time-based publisher bên trong supplier lambda, đồng thời dùng `withInitialContext` trong `StepVerifierOptions`.

## 22. Ghi nhớ

- Reactor `Context` là immutable key–value store cho subscription-scoped metadata, không phải `ThreadLocal` hay `ApplicationContext`.
- `ContextView` cung cấp API chỉ đọc; `Context` thêm `put`, `delete`, `putAll`.
- `contextWrite` đưa metadata từ downstream lên upstream khi subscribe.
- `deferContextual` đọc Context tại điểm và thời điểm publisher được subscribe.
- `StepVerifierOptions.withInitialContext(Context)` đặt Context ban đầu cho test subscriber.
- `expectAccessibleContext()` hỗ trợ `contains`, `hasKey`, `hasSize`, `matches`, `assertThat`, `containsAllOf`; nhớ `.then()` trước khi assert sequence.
- `expectNoAccessibleContext()` **không** phải cách kiểm tra thiếu một key riêng lẻ.
- Kiểm tra đồng thời Context propagation và `onNext`/`onError`/`onComplete`.
- Nhiều subscriptions dùng cùng Publisher có thể mang các Context khác nhau.
- `contextWrite` chỉ có hiệu lực theo scope upstream; kiểm tra giá trị tại đúng operator cần dùng nó.
- Reactor Context vẫn truyền qua các Reactor operators/schedulers thông thường; ThreadLocal và MDC cần cơ chế bridging riêng.
- `ReactiveSecurityContextHolder` dùng Reactor Context, nhưng unit test context không thay thế authentication integration test.
- Context không tự truyền qua network boundary; HTTP/RSocket metadata phải có propagation riêng.
- Giữ Context nhỏ, không chứa mutable shared state hoặc credential/log payload nhạy cảm.
- Test với initial Context, key thiếu, override, nhiều subscribers, async boundaries và virtual time sẽ phát hiện đa số lỗi propagation.

**Câu hỏi chẩn đoán nhanh:** *Ai tạo key, subscription nào đang dùng key, operator nào đọc key, `contextWrite` nằm ở đâu so với source, và test đã xác minh cả Context lẫn kết quả chưa?*

## 23. Tài liệu chính thức

- Reactor Core Reference — **Adding a Context to a Reactive Sequence**: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Reactor Core Reference — **Testing a Sequence with StepVerifier**: https://projectreactor.io/docs/core/release/reference/testing.html
- Reactor Test Javadoc — **StepVerifier**: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html
- Reactor Test Javadoc — **StepVerifier.ContextExpectations**: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.ContextExpectations.html
- Reactor Test Javadoc — **StepVerifierOptions**: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifierOptions.html
- Reactor Core Javadoc — **Context / ContextView**: https://projectreactor.io/docs/core/release/api/reactor/util/context/Context.html
- Spring Security Reference — **Reactive Method Security and Reactor Context**: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security API — **ReactiveSecurityContextHolder**: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- Spring Framework Reference — **WebFlux WebFilter**: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Micrometer — **Context Propagation**: https://docs.micrometer.io/context-propagation/reference/