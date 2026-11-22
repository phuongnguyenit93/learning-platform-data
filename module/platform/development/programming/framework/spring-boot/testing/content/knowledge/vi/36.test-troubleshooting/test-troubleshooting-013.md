# Reactive test không hoàn tất, mất context hoặc dùng scheduler sai — chẩn đoán Spring Boot WebFlux

## 1. Tình huống: một bài kiểm thử reactive bị treo không có nghĩa ứng dụng “chạy chậm”

Một ca JUnit kiểm thử `Mono` hoặc `Flux` có thể bị treo, báo timeout, không nhận được giá trị, mất request/trace/security context, hay chỉ fail trên CI. Các hiện tượng thường giống nhau ở bề mặt — “đang chờ mãi” — nhưng nguyên nhân có thể nằm ở **subscription**, **demand/backpressure**, **terminal signal**, **scheduler**, **Reactor Context**, **blocking call** hoặc cách viết **StepVerifier**.

Đây là bài học trong nhóm **Chẩn đoán lỗi kiểm thử** của Spring Boot. Mục tiêu là biết phân loại tín hiệu trước khi sửa, dựng được test tối thiểu để chứng minh nguyên nhân, rồi chọn đúng cơ chế sửa. Không dùng cách “thử tăng `Thread.sleep`/timeout đến khi CI xanh” như phương pháp mặc định.

Sau bài này, người học phải:
1. Phân biệt **assembly time** với **subscription time**, `onSubscribe`, `request(n)`, `onNext`, `onError` và `onComplete`.
2. Chẩn đoán test quên `verify`, publisher không có subscriber, subscriber không request, `Flux.never()`, infinite source và nhánh không có terminal signal.
3. Dùng `StepVerifier` có timeout thực, expected signals, cancellation và yêu cầu backpressure rõ ràng.
4. Dùng `StepVerifier.withVirtualTime` đúng thời điểm để kiểm tra `delay`, `interval`, `timeout` mà không ngủ theo thời gian thật.
5. Phân biệt `publishOn` với `subscribeOn`; chọn `Schedulers.parallel()`, `Schedulers.single()`, `Schedulers.boundedElastic()` đúng cho tác vụ không blocking hoặc legacy blocking.
6. Chẩn đoán `Context` theo subscriber, `contextWrite`, `deferContextual`, context propagation qua scheduler và sự khác biệt với `ThreadLocal`/MDC.
7. Kiểm thử WebFlux với `WebTestClient`, biết ranh giới giữa mock HTTP exchange và server socket thật.
8. Nhận diện reactive transaction/security/tracing context và vì sao `block()` hoặc `subscribe()` sai chỗ làm test sai dù business logic có vẻ hợp lý.
9. Bảo vệ test trước thread/resource leak, shared global scheduler state, cancellation, CI flakiness và các lỗi chỉ xuất hiện khi chạy song song.

**Phiên bản ví dụ:** Java 17+, Spring Boot 3.5.8, Project Reactor do Spring Boot quản lý BOM, `reactor-test`, JUnit Jupiter/AssertJ và Gradle. Code có dự án nhất quán, không cần database, Docker hoặc service ngoài. Các test được viết như source thực hành; **chúng chưa được chạy thực tế** trong môi trường soạn nội dung này.

## 2. Tư duy đầu tiên: Reactive Streams là một giao thức tín hiệu

```text
Publisher Mono/Flux
       |
       | subscribe()
       v
Subscriber                         Subscription
       ^                                 |
       | onSubscribe(subscription)       |
       |                                 | request(n)
       |                                 v
       |                 publisher có demand để phát
       |
       +-------- onNext(value) [0..N]
       |
       +-------- onComplete()    HOẶC onError(error)
                  [terminal signal, tối đa một lần]
```

Một publisher **có thể chưa thực thi gì trước khi subscribe**. Một subscriber **có thể đã subscribe nhưng chưa request**. Một `Flux` **có thể phát nhiều giá trị nhưng không bao giờ complete**. Đây là ba cơ chế khác nhau, dù đều khiến code thử nghiệm chưa đi đến kỳ vọng tiếp theo.

### 2.1. Cold publisher và assembly không đồng nghĩa execution

```java
AtomicInteger calls = new AtomicInteger();

Mono<String> publisher = Mono.fromSupplier(() -> {
    calls.incrementAndGet();
    return "READY";
});

// Ở đây mới lắp pipeline, chưa gọi supplier.
assertThat(calls.get()).isZero();

StepVerifier.create(publisher)
        .expectNext("READY")
        .expectComplete()
        .verify(Duration.ofSeconds(3));

assertThat(calls.get()).isEqualTo(1);
```

Đây là fragment đặt trong một JUnit method đã import `AtomicInteger`, `Mono`, `StepVerifier`, `Duration` và AssertJ. `StepVerifier.create(...)` xây dựng script; lời gọi `verify(...)` mới kích hoạt subscription và đối chiếu expected events.

Nếu bỏ `verify()`/`verifyComplete()`/`verifyError()`, test **có thể kết thúc “xanh” mà chưa subscribe** publisher. Kiểm thử hợp lệ phải thực sự kích hoạt và kiểm tra terminal/cancellation semantics, không chỉ dựng ra `StepVerifier`.

### 2.2. Mono, Flux và termination không đồng nghĩa “có ít nhất một giá trị”

| Publisher | Kết quả kỳ vọng | Test assertion phù hợp |
|---|---|---|
| `Mono.just("ok")` | Một onNext rồi onComplete | expectNext("ok"), expectComplete |
| `Mono.empty()` | onComplete, **không** onNext | verifyComplete |
| `Mono.error(ex)` | onError, **không** onComplete | expectError... |
| `Mono.never()` | Không phát value/error/complete | cancel hoặc timeout chủ động |
| `Flux.range(1,3)` | 1,2,3 rồi complete | expectNext(1,2,3), complete |
| `Flux.interval(...)` | Mặc định là stream vô hạn | take(n), cancel hoặc test boundary |
| `Flux.just(1,2).concatWith(Flux.never())` | Nhận 1,2 rồi treo | expectNext(1,2).thenCancel |
| `Flux.empty()` | Complete ngay | expectComplete, không chờ value |

Trong thực tế một pipeline có thể **kết thúc sớm** do `take`, **bị cancel** do client disconnect, hoặc **không phát đủ item** do backpressure. Các trường hợp này cần expected signals đúng thay vì luôn gọi `verifyComplete()`.

## 3. Chẩn đoán nhanh theo vị trí test bị dừng

| Triệu chứng | Giả thuyết ưu tiên | Cách xác nhận |
|---|---|---|
| Test xanh nhưng business code chưa chạy | Thiếu `verify`, không subscribe, `Mono` chưa được returned | AtomicInteger side effect/PublisherProbe, kiểm tra verify call |
| `expectNext` đứng mãi, không có request | `initialRequest=0` hoặc custom Subscriber quên `request(n)` | Kiểm tra `doOnRequest`, thêm `thenRequest` |
| Đã nhận đủ values, `verifyComplete` vẫn treo | Source không complete: `never`, `interval`, hot stream | Đổi expectation thành cancellation hoặc thêm business termination |
| `expectNoEvent` fail ngay | Subscription cũng được tính là event | Đặt `expectSubscription()` trước |
| `withVirtualTime` vẫn đợi wall-clock | Publisher/timer/scheduler tạo trước virtual scheduler hoặc explicit real scheduler | Tạo publisher **bên trong** supplier, kiểm scheduler |
| Virtual test treo không có tick | Quên `thenAwait`, clock chưa advance, task chiếm virtual thread | Dùng `thenAwait`/`expectNoEvent`, tránh endless synchronous loop |
| `IllegalStateException: block()... not supported` | `block()` trên Reactor non-blocking thread | Chuyển sang nonblocking API; legacy I/O dùng boundedElastic |
| Context key không tìm thấy | `contextWrite` sai vị trí, subscriber context không được đưa vào, manual `subscribe` | `deferContextual`, test Context per subscription |
| MDC/ThreadLocal mất sau `publishOn` | Thread switch không tự propagate mọi ThreadLocal | Dùng Reactor Context hoặc Micrometer Context Propagation đúng config |
| Test chỉ fail dưới parallel CI | Shared scheduler, `Hooks` global, context/test data dùng chung, thread leak | Chạy tuần tự rồi tăng concurrency từng tầng |
| `onErrorResume` làm test “xanh” sai | Error bị chuyển thành fallback/empty | Assert error upstream riêng và fallback contract riêng |
| WebTestClient timeout | Server chain không complete, response stream infinite, backend blocked | Kiểm tra `onError`/`onComplete`, header, WebFilter, timeout, Reactor Netty |
| `Thread.sleep` fix tạm được | Race hoặc readiness chưa được đồng bộ | Future/StepVerifier/Awaitility hoặc virtual time |

Cách debug có hiệu quả là **thu nhỏ publisher** trước khi tăng timeout:
1. Có subscription chưa?
2. Có demand chưa?
3. Có `onNext`/terminal signal chưa?
4. Có scheduler chuyển thread/đang bị block chưa?
5. Có context đến đúng subscriber chưa?
6. Có shared state hoặc một publisher/stream đang sống lâu hơn test không?

## 4. StepVerifier: xác minh đúng tín hiệu và có deadline

`reactor-test` cung cấp `StepVerifier` để mô tả expected reactive signals. Mẫu:

```java
StepVerifier.create(Mono.just("A"))
        .expectSubscription()
        .expectNext("A")
        .expectComplete()
        .verify(Duration.ofSeconds(3));
```

Một test `StepVerifier` phải gồm:
- `create(publisher)` hoặc `withVirtualTime(supplier)`.
- Kỳ vọng đủ rõ: `expectNext`, `assertNext`, `expectErrorMatches`, `expectComplete`, `thenCancel`...
- **Trigger verification**, thường là `verify(Duration)` hoặc một shortcut `verifyComplete()`/`verifyError()`.
- Có deadline hợp lý. Các shortcut mặc định **không có timeout** nếu chưa cấu hình default global; một publisher không kết thúc có thể treo JUnit worker vô hạn.

### 4.1. Vì sao nên ưu tiên `verify(Duration)`?

```java
StepVerifier.create(source)
        .expectNext(expected)
        .expectComplete()
        .verify(Duration.ofSeconds(3));
```

Đây là fragment có `source` và `expected` được khai báo. Timeout này là **thời gian chờ xác minh thực**, không biến một infinite stream thành finite stream. Nếu app contract là stream kéo dài đến khi client cancel, `expectComplete()` vốn đã sai; cần một `thenCancel()` có chủ đích.

Không dùng `Thread.sleep(5000)` rồi `assertTrue(flag)` làm thay cho terminal events. Không thiết lập `StepVerifier.setDefaultTimeout(...)` trong một test chạy song song vì đó là static/global state có thể ảnh hưởng test khác; cấu hình per-verifier rõ ràng dễ hiểu hơn.

### 4.2. Kết thúc bằng error, complete hay cancel?

```java
// Kỳ vọng complete:
StepVerifier.create(Flux.just(1, 2))
        .expectNext(1, 2)
        .expectComplete()
        .verify(Duration.ofSeconds(2));

// Kỳ vọng onError, không phải onComplete:
StepVerifier.create(Mono.error(
            new IllegalArgumentException("bad input")))
        .expectErrorMatches(ex ->
            ex instanceof IllegalArgumentException
                && "bad input".equals(ex.getMessage()))
        .verify(Duration.ofSeconds(2));

// Kỳ vọng stream dài hạn vẫn đang hoạt động,
// test chủ động cancel:
StepVerifier.create(
            Flux.just(1, 2).concatWith(Flux.never()))
        .expectNext(1, 2)
        .thenCancel()
        .verify(Duration.ofSeconds(2));
```

Các ví dụ này có thể đặt trong một JUnit method với imports cần thiết. Trường hợp cuối **không phải test fail vì không complete**: cancellation là contract được kiểm tra. Tuy nhiên cancellation không chứng minh upstream đã giải phóng hết connection/transaction nếu chưa có assertions/resource probes riêng.

### 4.3. `expectNoEvent` không phải “không thấy giá trị”

Reactor tính **subscription signal** là một event khi `expectNoEvent` kiểm tra khoảng thời gian.

**Sai về expectation:**

```java
StepVerifier.create(Mono.delay(Duration.ofSeconds(1)))
        .expectNoEvent(Duration.ofMillis(100))
        .expectNext(0L)
        .verifyComplete();
```

Đây là anti-pattern: `expectNoEvent` có thể fail ngay vì chính `onSubscribe` xảy ra. Ngoài ra `verifyComplete()` thiếu real timeout nếu publisher mắc lỗi. Cách đúng:

```java
StepVerifier.create(Mono.delay(Duration.ofMillis(100)))
        .expectSubscription()
        .expectNoEvent(Duration.ofMillis(20))
        .expectNext(0L)
        .expectComplete()
        .verify(Duration.ofSeconds(3));
```

Ở test dùng thời gian thật, scheduler/CI load có thể gây timing noise; khi mục tiêu là timing semantics, dùng virtual time thay vì assert mili-giây quá sát giới hạn.

## 5. No demand/backpressure: có subscribe mà vẫn không phát value

Reactive Streams cho phép subscriber điều khiển số phần tử muốn nhận qua `Subscription.request(n)`. Với `Flux.range`, khi demand bằng 0, source chưa phát `onNext`.

```java
StepVerifier.create(
        Flux.range(1, 5),
        StepVerifierOptions.create().initialRequest(0))
    .expectSubscription()
    .thenRequest(2)
    .expectNext(1, 2)
    .thenRequest(3)
    .expectNext(3, 4, 5)
    .expectComplete()
    .verify(Duration.ofSeconds(3));
```

**Bài học:** Nếu test dùng `initialRequest(0)` rồi `expectNext(1)` mà quên `thenRequest(1)`, nó không nhất thiết là deadlock ở business code; đó là test đã không gửi demand. `StepVerifier` còn có kiểm tra under-requesting giúp bắt những kịch bản cấu hình `expectNextCount` vượt demand.

Trong production, backpressure cũng ảnh hưởng queue/workload: `flatMap` concurrency/prefetch, `onBackpressureBuffer`, downstream cancellation, Netty response writing. Đừng dùng `request(Long.MAX_VALUE)` bừa chỉ để che sự cố thiết kế khi system cần demand management.

### 5.1. Empty publisher không phải thiếu demand

`Mono.empty()` phát `onComplete` không có `onNext`. Nếu test đang `expectNext("value")`, nó thất bại do **khác contract**. Dùng:

```java
StepVerifier.create(Mono.<String>empty())
        .expectComplete()
        .verify(Duration.ofSeconds(2));
```

Phân biệt empty với `Mono.never()`: empty kết thúc được; never không phát bất kỳ terminal event nào.

### 5.2. Hot publisher và race khi subscribe

`Flux.just`, `Mono.fromSupplier` thường là cold: mỗi subscription có lifecycle riêng. `Sinks.Many` hoặc hot streams có thể phát dữ liệu trước khi một subscriber được gắn, khiến test mất event và chờ mãi.

Khi test hot publisher:
- Đăng ký subscriber trước khi emit; dùng `StepVerifier.then(() -> sink.tryEmitNext(...))` hoặc `TestPublisher`.
- Nếu dùng `Sinks.many().multicast().onBackpressureBuffer()`, hiểu rõ behavior không có subscriber và buffer.
- Check `Sinks.EmitResult` khi `tryEmitNext`, không bỏ qua `FAIL_ZERO_SUBSCRIBER`/`FAIL_OVERFLOW`.
- Tránh dùng `Thread.sleep` để “đợi subscriber đã vào”.
- Có termination/cancellation rõ ràng để tránh test giữ sink/subscription sống sau khi kết thúc.

Không đổi một hot publisher thành cold một cách ngẫu nhiên trong test nếu production contract yêu cầu hot semantics; hãy dùng test setup đủ chính xác.

## 6. Virtual time: tăng tốc đồng hồ thay vì ngủ chờ

`StepVerifier.withVirtualTime` hoán đổi scheduler mặc định mà các Reactor timed operators sử dụng sang `VirtualTimeScheduler`. Điều kiện quan trọng: **publisher/timer cần được tạo sau khi virtual scheduler có hiệu lực**, do đó API nhận `Supplier<? extends Publisher>` thay vì một publisher đã dựng sẵn.

**Đúng:**

```java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofDays(1)))
    .expectSubscription()
    .expectNoEvent(Duration.ofDays(1))
    .expectNext(0L)
    .expectComplete()
    .verify(Duration.ofSeconds(3));
```

Đây là test không phải chờ một ngày thật. `expectNoEvent` sau `expectSubscription` cho biết trong khoảng một ngày ảo chưa có `onNext` trước thời điểm delay kết thúc.

**Sai thường gặp:**

```java
Mono<Long> alreadyBuilt = Mono.delay(Duration.ofDays(1));

StepVerifier.withVirtualTime(() -> alreadyBuilt)
    .expectSubscription()
    .thenAwait(Duration.ofDays(1))
    .expectNext(0L)
    .verifyComplete();
```

Đoạn sai được đưa ra để phân tích: việc tạo publisher trước có thể capture scheduler thật hoặc tạo những phần timing trước khi virtual time được cài đặt, khiến test không thực sự chạy bằng virtual clock như tưởng. Hãy dựng publisher bên trong supplier và dùng `verify(Duration)`.

### 6.1. `thenAwait` so với `expectNoEvent`

- `thenAwait(Duration)`: tiến đồng hồ ảo (hoặc chờ thời gian thật nếu không dùng virtual time); không assert “không có signal”.
- `expectNoEvent(Duration)`: tiến đồng hồ nhưng **thất bại nếu có signal** trong khoảng; nhớ subscription cũng là event.
- `then(() -> {...})`: chạy hành động sau các bước kỳ vọng trước đó, hữu ích khi test hot publishers.
- `verify(Duration)`: real timeout bảo vệ JUnit nếu có logic không kết thúc.

`thenAwait(Duration.ofDays(1))` mà quên `expectNext`/complete chưa chứng minh business timer trả kết quả đúng; phải assert tín hiệu quan trọng tiếp theo.

### 6.2. Vì sao virtual time vẫn có thể treo?

VirtualTimeScheduler không phải một “time machine” xử lý mọi blocking/thread:
1. Publisher dùng **explicit Scheduler do bạn new sẵn** ngoài supplier, không bị virtual scheduler thay thế.
2. `Flux` được dựng trước `withVirtualTime`, một operator capture real scheduler.
3. Quên `thenAwait` hoặc chờ value trước khi tăng virtual clock.
4. Infinite synchronous loop hoặc `Flux.generate` không yield chiếm thread virtual-time.
5. Kết hợp hot publisher/real external I/O với virtual-time setup làm test phụ thuộc wall-clock.
6. Tests chạy song song cùng thay đổi global `Schedulers` factory, `Hooks` hoặc virtual scheduler state.
7. Logic dùng `Thread.sleep`/blocking socket — virtual time không tự thay đổi Java wall clock hay network.

**Chính sách:** Cô lập virtual-time tests, không lưu scheduler mặc định vào static field, tạo pipeline trong supplier, đặt real timeout và tránh bật hooks/global scheduler overrides cùng các tests concurrent.

## 7. `publishOn` và `subscribeOn`: hai vị trí chuyển execution khác nhau

Reactor không tự chuyển mọi `Mono`/ `Flux` sang thread mới. Nếu không chỉ định scheduler, nhiều operators thực thi trên thread subscription/đang phát signal.

| Operator | Tác dụng chính | Lỗi phổ biến |
|---|---|---|
| `subscribeOn(scheduler)` | Tác động luồng subscribe/request về phía source, thường đặt gần source | Nghĩ rằng nó chỉ ảnh hưởng operator đứng sau nó |
| `publishOn(scheduler)` | Chuyển nơi xử lý signals cho các operators **sau** nó | Nghĩ rằng nó chuyển các operators ở trước nó |
| `Schedulers.parallel()` | CPU-bound, non-blocking work | Dùng `block()` hoặc JDBC trong parallel worker |
| `Schedulers.single()` | Shared single non-blocking worker | Bị chiếm bởi blocking call |
| `Schedulers.boundedElastic()` | Cô lập legacy blocking I/O có giới hạn thread/task queue | Lạm dụng thay vì dùng reactive driver |
| `Schedulers.immediate()` | Không chuyển thread | Tưởng là async executor |
| `Schedulers.newSingle("name")` | Scheduler do test/app sở hữu | Quên `dispose()` làm leak threads |

### 7.1. `publishOn` ảnh hưởng downstream

```java
Flux.range(1, 2)
    .map(i -> "before-" + Thread.currentThread().getName())
    .publishOn(Schedulers.parallel())
    .map(s -> "after-scheduler-change")
    .subscribe();
```

Đây là fragment giải thích thứ tự operators, không phải một unit test xác nhận thread IDs. `publishOn` áp scheduler cho những callbacks đứng sau; nó không “quay ngược thời gian” khiến `map` trước chạy ở worker mới.

Trong test thực, tránh assert tên thread chính xác (`parallel-1`/ `parallel-2`) vì implementation và load khác nhau. Nếu yêu cầu chứng minh một boundary chuyển thread, capture caller thread ID/name trước khi subscribe, rồi assert thread khác theo contract tại operator sau `publishOn`.

### 7.2. `subscribeOn` phù hợp khi wrap blocking source

```java
Mono.fromCallable(() -> legacyJdbcCall())
    .subscribeOn(Schedulers.boundedElastic());
```

Đây là fragment có `legacyJdbcCall()` được khai báo trong ứng dụng thực. `fromCallable` trì hoãn việc gọi blocking code đến lúc subscribe; `boundedElastic` giúp không giữ event-loop/parallel threads bị block. **Đây là biện pháp tương thích với API blocking, không biến JDBC thành R2DBC**. Nếu upstream HTTP/DB driver đã non-blocking, thêm `boundedElastic` không cần thiết có thể tăng context switching và cost.

**Không sửa:**
```java
Mono.just(legacyJdbcCall())
    .subscribeOn(Schedulers.boundedElastic());
```

Trong fragment này, `legacyJdbcCall()` đã chạy **ngay ở lúc assembly**, trước khi `subscribeOn` có cơ hội thay thread. Dùng `Mono.fromCallable(...)` hoặc `Mono.defer(...)` để lazy source.

### 7.3. Lỗi block() trên Reactor non-blocking thread

Reactor đánh dấu nhiều `parallel`/`single` workers là non-blocking, và gọi `Mono.block()` ở những thread này có thể ném `IllegalStateException` với thông báo blocking API không được hỗ trợ.

**Sai trong reactive operator:**

```java
Mono.just("ABC")
    .publishOn(Schedulers.parallel())
    .map(code -> remoteReactiveCall(code).block());
```

Fragment này có `remoteReactiveCall` là một reactive function chưa khai báo. Vấn đề là `block()` tạo subscription đồng bộ bên trong operator, có thể ném lỗi trên non-blocking scheduler, mất Reactor Context hoặc deadlock khi lệ thuộc cùng worker. Sửa thành composition:

```java
Mono.just("ABC")
    .flatMap(code -> remoteReactiveCall(code));
```

Nếu `remoteReactiveCall` trả `Mono<...>`, `flatMap` giữ reactive chain để downstream kiểm soát cancellation, errors và Context. Đừng dùng `block()` trong controller/service WebFlux để chuyển kết quả thành kiểu đồng bộ.

### 7.4. Schedulers trong test phải được giải phóng

Khi test tạo riêng:

```java
Scheduler scheduler = Schedulers.newSingle("probe");
try {
    StepVerifier.create(
            Mono.just("x").publishOn(scheduler))
        .expectNext("x")
        .expectComplete()
        .verify(Duration.ofSeconds(3));
} finally {
    scheduler.dispose();
}
```

Một `Schedulers.newSingle` bị bỏ quên có thể giữ background thread, làm JVM sống lâu hoặc khiến test khác bị ảnh hưởng. Tránh dùng `Schedulers.shutdownNow()`/factory reset toàn cục trong các tests song song vì điều đó có thể tắt scheduler đang được test khác sử dụng.

## 8. Reactor Context: gắn với subscriber, không gắn cố định với thread

`reactor.util.context.Context` là một cấu trúc bất biến theo ngữ nghĩa (các phép `put` tạo context mới). Nó gắn với **Subscription/Subscriber** và được truyền theo hướng từ subscriber về upstream qua `contextWrite`. Điều này khác `ThreadLocal`, vốn gắn với một Java thread cụ thể.

```text
        Assembly time
  service.requestId() tạo Mono
             |
             v
  Subscriber gọi subscribe()
             |
             v
     contextWrite(Context.put)
       đưa giá trị vào
          upstream chain
             |
             v
      deferContextual(...)
      đọc ContextView
             |
             v
      onNext(requestId)
```

**Đúng:**

```java
Mono<String> requestId =
    Mono.deferContextual(context ->
        Mono.just(context.getOrDefault(
            "requestId", "missing")));

StepVerifier.create(
        requestId.contextWrite(
            context -> context.put("requestId", "RID-42")))
    .expectNext("RID-42")
    .expectComplete()
    .verify(Duration.ofSeconds(3));
```

`contextWrite` thường nên đứng **downstream của operator cần đọc Context** để các operators upstream nhìn thấy giá trị này. Context không phải global mutable map; hai subscribers có thể dùng cùng publisher nhưng giữ giá trị `requestId` khác nhau.

### 8.1. Vị trí `contextWrite` rất quan trọng

Giả sử:

```java
Mono<String> current = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("key", "missing")));

Mono<String> correct =
        current.contextWrite(ctx -> ctx.put("key", "value"));
```

`correct` thấy `value`. Nếu một `contextWrite` nằm ở đoạn chain không thuộc upstream subscriber path của `deferContextual`, hoặc đọc trong một subscription mới bị tách, kết quả có thể là `missing`.

Đừng coi `Context` như các `@RequestScope` attributes hoặc MDC đã tự copy vào mọi thread. Lệnh `publishOn` thông thường vẫn nằm trong cùng Reactor chain nên Reactor Context tiếp tục được truy cập qua `deferContextual`, **nhưng ThreadLocal tùy biến không tự được preserve chỉ vì Context còn**.

### 8.2. Context qua `publishOn`

```java
Mono<String> afterSwitch = Mono.just("go")
    .publishOn(Schedulers.parallel())
    .flatMap(ignored ->
        Mono.deferContextual(ctx ->
            Mono.just(ctx.getOrDefault(
                "requestId", "missing"))));

StepVerifier.create(
        afterSwitch.contextWrite(ctx ->
            ctx.put("requestId", "RID-99")))
    .expectNext("RID-99")
    .expectComplete()
    .verify(Duration.ofSeconds(3));
```

Ở đây `deferContextual` được gọi **sau** `publishOn`, do đó test thực sự chứng minh Context có thể được đọc trong downstream flow sau scheduler switch. Nó **không chứng minh MDC/ThreadLocal của application cũng được propagate**.

### 8.3. `ThreadLocal`, MDC, SecurityContext và trace context

| Dữ liệu | Cơ chế phổ biến | Rủi ro |
|---|---|---|
| Java `ThreadLocal` | Theo thread | Mất khi chuyển scheduler, rò trên pooled threads |
| SLF4J MDC | Thường dựa trên ThreadLocal | Log traceId thiếu hoặc mang context cũ |
| Reactor `Context` | Theo subscriber | Mất nếu tách chain/subscribe thủ công hoặc contextWrite sai |
| Spring Security reactive | `ReactiveSecurityContextHolder` dùng Reactor Context | Không đọc bằng `SecurityContextHolder` ThreadLocal như MVC |
| Spring reactive transaction | Transaction context theo Reactor subscriber | Không tương đương JDBC ThreadLocal transaction |
| Micrometer tracing | Bridge + context propagation policy | Không phải mọi custom ThreadLocal đều tự propagate |

Đối với Spring Security WebFlux, cần xây test với `spring-security-test`, `WebTestClient` và các WebFlux security test configurers khi dùng security integration. **Không** lấy `SecurityContextHolder.getContext()` trong random parallel thread rồi kết luận principal của reactive request đã mất; đó có thể là đang đọc sai cơ chế.

Đối với reactive transactions, `@Transactional` trên `Mono`/`Flux` (khi dùng `ReactiveTransactionManager`) gắn transaction vào Reactor Context. Nếu service tự `subscribe()` một publisher khác ngoài flow được quản lý, transaction/cancellation/error context có thể bị tách. Một JDBC `PlatformTransactionManager` thread-bound không tự bao phủ R2DBC operator trên scheduler khác.

### 8.4. Micrometer Context Propagation và automatic mode

Spring Boot/Reactor có tích hợp Micrometer Context Propagation để capture/restore các `ThreadLocalAccessor` thích hợp giữa Reactor Context và ThreadLocal. Điều kiện:
- Dependency/config/version tương thích và accessor đã đăng ký.
- Một context snapshot/automatic propagation mode phù hợp.
- Không tự coi custom `ThreadLocal` có key bất kỳ là được propagate nếu chưa đăng ký.
- Clean up sau khi task hoàn tất để không rò MDC/security/tenant context.

**Không lạm dụng** `Hooks.enableAutomaticContextPropagation()` trong từng test khi JUnit chạy song song: đây là cấu hình toàn cục, có thể ảnh hưởng các test khác. Test theo application configuration hoặc test-specific context fixtures, reset global changes ở teardown khi thực sự cần.

## 9. `subscribe()`, `block()` và `cache()` có thể tạo false positive

### 9.1. `subscribe()` thủ công làm test kết thúc trước pipeline

```java
service.saveReactive(item).subscribe();
assertThat(repository.count()).isEqualTo(1);
```

Đây là anti-pattern minh họa (service/repository/item là đối tượng dự án khác). `subscribe()` là hành động **khởi chạy async**, không phải bảo đảm save đã complete. Assertion kế tiếp có thể chạy trước sự kiện save, và exception async có thể bị log/drop chứ không làm JUnit method fail theo cách mong muốn.

**Sửa:** `return` publisher cho caller trong production; trong test dùng `StepVerifier.create(service.saveReactive(item))` với terminal assertion. Nếu cần truy vấn DB sau save, compose `then(repository.count())` trong cùng flow hoặc dùng một verifier riêng sau khi verifier save complete.

### 9.2. `block()` đôi khi che mất vấn đề subscription

```java
Mono<String> source = service.loadReactive("A");
String first = source.block();
String second = source.block();
```

Đây là fragment, không phải test. Với cold publisher, mỗi `block()` **tạo một subscription mới**. Nếu source làm HTTP call, DB query hoặc tăng counter theo subscription, bạn đã thực thi side effect hai lần.

Ở một plain JUnit test không nằm trên Reactor event-loop, `block(Duration)` có thể dùng như phương tiện lấy một kết quả, nhưng nó không thay thế `StepVerifier` khi cần kiểm tra `onError`, cancellation, request-n hoặc virtual time. `block()` trong chính ứng dụng WebFlux/controller là dấu hiệu cần xem lại thiết kế.

### 9.3. `cache()` đổi semantics

`Mono.cache()` có thể giữ lại kết quả/terminal signal cho những subscribers tiếp theo. Nó hữu ích trong một số service nhưng khiến test tưởng có “chỉ một lần I/O”, trong khi production service có thể cần freshness. Đừng thêm cache chỉ để làm một test chậm/hang thành pass. Khi test cache, hãy assert số subscriptions, expiration/invalidation policy và error semantics, không chỉ giá trị cuối.

## 10. Khi publisher không hoàn tất: nhận diện terminal contract

Có ba trường hợp dễ nhầm:
1. **Finite operation:** một reactive DB query hoặc REST request cần complete/error trong một thời hạn hữu hạn.
2. **Infinite/long-lived stream:** SSE, event subscription, `Flux.interval`, Kafka reactive consumer thường **không tự complete** khi không có lệnh dừng.
3. **Broken flow:** đáng lẽ finite nhưng pipeline `concatWith(Flux.never())`, giữ sink không complete, callback không `success` hoặc deadlock.

Với finite operation, test nên `expectComplete` hoặc `expectError` và `verify(Duration)`. Với infinite stream, test thường chọn `take(n)`, `thenCancel()`, hoặc cancel từ bên nhận sau khi đã kiểm tra số events cần thiết.

### 10.1. `take(n)` là một thay đổi contract có chủ ý

```java
Flux<Long> ticks = Flux.interval(Duration.ofMillis(100));

StepVerifier.create(ticks.take(3))
    .expectNext(0L, 1L, 2L)
    .expectComplete()
    .verify(Duration.ofSeconds(3));
```

Ở đây `take(3)` tạo **finite downstream stream** và hủy subscription upstream khi đủ ba elements. Nếu production API vốn trả infinite SSE, test này chỉ chứng minh ba ticks đầu và cách downstream dừng, không chứng minh server sau này tự complete.

### 10.2. `timeout` là business behavior khác với verifier timeout

```java
Mono<String> result = Mono.<String>never()
    .timeout(Duration.ofSeconds(1))
    .onErrorResume(TimeoutException.class,
        ex -> Mono.just("timed-out"));
```

Fragment này yêu cầu import `java.util.concurrent.TimeoutException`. Operator `timeout` nằm trong **pipeline**, thực sự phát `TimeoutException` nếu source không có signal đúng hạn; `onErrorResume` chuyển lỗi thành kết quả. Trái lại, `verify(Duration.ofSeconds(3))` là **hạn kiểm chứng của test**, không sửa pipeline.

Test cần biết đang kiểm tra:
- Publisher tự timeout theo nghiệp vụ.
- Hay chỉ bảo vệ JUnit khỏi chờ vô hạn.

Hai deadline này nên khác nhau có chủ đích; với timeout pipeline dài, dùng virtual time thay vì sleep thời gian thật.

### 10.3. `onErrorResume` sai vị trí làm mất lỗi cần kiểm chứng

```java
Mono<String> source = Mono.error(
    new IllegalStateException("database unavailable"));

Mono<String> recovered = source.onErrorResume(
    error -> Mono.just("fallback"));
```

Nếu test `recovered` rồi `expectError`, test đang assert sai contract — lỗi đã được chuyển thành fallback. Muốn kiểm tra error propagation từ repository, test **source trước fallback**; muốn kiểm tra fallback behavior của service, assert `fallback`.

Tránh `onErrorResume(ex -> Mono.empty())` ở mọi lớp để “giảm test đỏ”: nó có thể biến lỗi hạ tầng thành một empty completion không phân biệt với dữ liệu không tồn tại, gây false positives.

## 11. WebTestClient: reactive HTTP mock khác StepVerifier thuần

`StepVerifier` kiểm tra publisher APIs trực tiếp. `WebTestClient` kiểm tra **HTTP request/response semantics**; nó có thể bind vào controller/application context bằng mock exchange, không cần khởi động socket server, hoặc bind đến một URL có server thật.

| Loại test | Dùng gì? | Chứng minh được |
|---|---|---|
| Pure operator/service test | `StepVerifier` | Signals, errors, demand, cancellation, Context |
| Controller mock exchange | `WebTestClient.bindToController(...)` hoặc `@WebFluxTest` | HTTP status, headers, body, web binding/filter scope theo setup |
| Full mock Boot context | `@SpringBootTest` + `@AutoConfigureWebTestClient` | Controller/filter/service wiring, response format |
| Running server | `@SpringBootTest(webEnvironment=RANDOM_PORT)` | Netty server/client transport gần production |
| External API dependency | Local mock HTTP server hoặc fake WebClient exchange | Client serialization, timeouts, retry, URI/correlation |

**Không coi** một `WebTestClient` test bị timeout là Reactor publisher không bao giờ complete khi chưa xem handler chain, WebFilter, codec/content negotiation và body streaming. Có thể controller trả `Flux` vô hạn vào endpoint mà test đòi `expectBodyList(...)` complete, hoặc handler chỉ subscribe phụ một pipeline rồi trả `Mono.empty()`.

### 11.1. `@WebFluxTest` slice khác `@SpringBootTest`

Ở Spring Boot 3.5, `@WebFluxTest(Controller.class)` chỉ nạp web slice, không tự quét mọi `@Service`. Controller cần service thì dùng `@MockitoBean`, `@Import` phù hợp hoặc chuyển sang full context test. `@WebFluxTest` tự cấu hình `WebTestClient` để kiểm tra web endpoints mà không cần server socket.

`@SpringBootTest` default là mock web environment và không tự bật `WebTestClient` trong mọi tình huống; với WebFlux, thêm `@AutoConfigureWebTestClient` cho full mock Boot test. Nếu cả MVC và WebFlux cùng có mặt, Boot thường ưu tiên MVC, trừ khi đặt `spring.main.web-application-type=reactive`.

## 12. Dự án thực hành Spring Boot 3.5.8, Java 17+ và Reactor Test

Các đoạn dưới đây tạo một ứng dụng Spring WebFlux nhỏ. Dữ liệu chỉ nằm trong memory; không kết nối database, broker hoặc remote HTTP service. Code dùng một service rõ semantics, WebFilter đặt request ID vào Reactor Context, controller đọc request ID sau scheduler switch và các bộ JUnit tests.

### 12.1. Cây tệp

```text
settings.gradle
build.gradle
src/main/java/com/example/reactivediag/
    ReactiveDiagnosticApplication.java
    ReactiveProbeService.java
    RequestIdWebFilter.java
    ReactiveProbeController.java
src/test/java/com/example/reactivediag/
    ReactiveProbeServiceTest.java
    ReactiveProbeVirtualTimeTest.java
    ReactiveProbeWebTest.java
    PublisherProbeTest.java
```

Bốn lớp test chia theo mục tiêu: signals/backpressure, virtual time, HTTP/Reactor Context, publisher subscription/cancellation. Không có test intentionally hangs; các ví dụ sai ở phần giải thích **không** được đưa vào source set.

### 12.2. settings.gradle

```groovy
rootProject.name = 'reactive-diagnostics-lab'
```

### 12.3. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    // Dùng một fork trong bài học để tránh global virtual-time
    // interactions giữa các test JVMs khi debug.
    maxParallelForks = 1

    testLogging {
        events 'failed', 'skipped'
        exceptionFormat 'full'
    }
}
```

**Giải thích dependency:**
- `spring-boot-starter-webflux`: Reactor, Spring WebFlux, Reactor Netty và runtime HTTP.
- `spring-boot-starter-test`: Spring Boot Test, JUnit/AssertJ và các test utilities.
- `reactor-test`: `StepVerifier`, `StepVerifierOptions`, `PublisherProbe`, virtual time support.
- BOM của Spring Boot quản lý versions Reactor để `reactor-core` và `reactor-test` nhất quán. Không tự ghép một `reactor-test` phiên bản khác với core nếu chưa xác minh.
- Không thêm Spring Security, R2DBC, tracing bridge hoặc Testcontainers vào demo vì chúng không cần để chứng minh vấn đề chính.

**Quan trọng:** `maxParallelForks=1` chỉ giới hạn số **forked test JVMs**, không tự tắt JUnit Jupiter parallel threads nếu dự án sau này thêm `junit-platform.properties` bật concurrent. Mẫu không cung cấp file bật parallel; mặc định Jupiter chạy tuần tự, phù hợp chẩn đoán virtual scheduler và global hooks.

### 12.4. ReactiveDiagnosticApplication.java

Tệp `src/main/java/com/example/reactivediag/ReactiveDiagnosticApplication.java`:

```java
package com.example.reactivediag;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveDiagnosticApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                ReactiveDiagnosticApplication.class, args);
    }
}
```

Spring Boot phát hiện WebFlux vì classpath chỉ có WebFlux starter, không có Spring MVC starter. Chạy `bootRun` sẽ khởi động Reactor Netty server; tuy nhiên các JUnit web tests dưới đây dùng **mock exchange**, không cần mở port.

### 12.5. ReactiveProbeService.java

Tệp `src/main/java/com/example/reactivediag/ReactiveProbeService.java`:

```java
package com.example.reactivediag;

import java.time.Duration;
import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

import org.springframework.stereotype.Service;

@Service
public class ReactiveProbeService {

    public Mono<String> normalize(String input) {
        return Mono.defer(() -> {
            if (input == null || input.isBlank()) {
                return Mono.error(new IllegalArgumentException(
                        "code must not be blank"));
            }

            return Mono.just(
                    input.trim().toUpperCase(Locale.ROOT));
        });
    }

    public Mono<String> deferredLabel(
            String id, AtomicInteger subscriptions) {

        Objects.requireNonNull(subscriptions);

        return Mono.fromSupplier(() -> {
            subscriptions.incrementAndGet();
            return "READY-" + id;
        });
    }

    public Mono<String> requestIdAfterSwitch(
            Scheduler scheduler) {

        Objects.requireNonNull(scheduler);

        return Mono.just("trigger")
                .publishOn(scheduler)
                .flatMap(ignored ->
                    Mono.deferContextual(context ->
                        Mono.just(context.getOrDefault(
                            "requestId", "missing"))));
    }

    public Flux<Integer> numbers() {
        return Flux.range(1, 5);
    }

    public Flux<Integer> numbersThenNever() {
        return Flux.range(1, 3)
                .concatWith(Flux.<Integer>never());
    }

    public Mono<Long> delayedSignal(Duration delay) {
        return Mono.delay(delay);
    }

    public Flux<Long> hourlyTicks(int count) {
        return Flux.interval(Duration.ofHours(1)).take(count);
    }

    public Mono<String> timeoutFallback(Duration timeout) {
        return Mono.<String>never()
                .timeout(timeout)
                .onErrorResume(TimeoutException.class,
                    ex -> Mono.just("timed-out"));
    }

    public Mono<String> blockingWorkThread() {
        return Mono.fromCallable(() ->
                Thread.currentThread().getName())
            .subscribeOn(Schedulers.boundedElastic());
    }
}
```

**Đọc chính xác:**
- `normalize` dùng `Mono.defer` để validation/execution xảy ra khi subscribe; invalid input tạo `onError`.
- `deferredLabel` đếm **thực thi supplier per subscription** chứ không đếm assembly.
- `requestIdAfterSwitch` đặt `deferContextual` **sau `publishOn`**, test được subscriber context trên scheduler đã chuyển.
- `numbers` là finite Flux có backpressure.
- `numbersThenNever` phát ba items rồi không complete, phù hợp cancellation test.
- `delayedSignal`/`hourlyTicks` tạo timer khi method được gọi; phải gọi **bên trong** `withVirtualTime` supplier khi test.
- `timeoutFallback` phân biệt pipeline timeout với verifier timeout.
- `blockingWorkThread` minh họa wrap task bằng `fromCallable`/boundedElastic; nó **không thực hiện blocking I/O thật** trong demo. Không suy ra thread này luôn có một tên cụ thể.

### 12.6. RequestIdWebFilter.java

Tệp `src/main/java/com/example/reactivediag/RequestIdWebFilter.java`:

```java
package com.example.reactivediag;

import reactor.core.publisher.Mono;

import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

@Component
public class RequestIdWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        ServerHttpRequest request = exchange.getRequest();

        String raw = request.getHeaders()
                .getFirst("X-Request-Id");

        String requestId = raw == null || raw.isBlank()
                ? "anonymous"
                : raw;

        return chain.filter(exchange)
                .contextWrite(context ->
                    context.put("requestId", requestId));
    }
}
```

Filter đọc HTTP header và gắn `requestId` vào Reactor Context cho **reactive chain của request này**. Nó không gọi `ThreadLocal.set` và không dựa vào một static map. Với production thực, `X-Request-Id` là untrusted client input: cần validate length/format, sanitize log output và chính sách tracing/security phù hợp. Ví dụ chỉ dùng IDs do test chủ động gửi.

**Lý do viết `chain.filter(exchange).contextWrite(...)`:** `contextWrite` cấp context cho các operators upstream trong same subscription, bao gồm controller/service được chain gọi. Nếu đặt một `Mono.deferContextual` ngoài flow này hoặc dùng `subscribe()` thủ công tách biệt, request ID có thể biến mất.

### 12.7. ReactiveProbeController.java

Tệp `src/main/java/com/example/reactivediag/ReactiveProbeController.java`:

```java
package com.example.reactivediag;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/probe")
public class ReactiveProbeController {

    private final ReactiveProbeService service;

    public ReactiveProbeController(ReactiveProbeService service) {
        this.service = service;
    }

    @GetMapping(
        path = "/context",
        produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> context() {
        return service.requestIdAfterSwitch(
                Schedulers.parallel());
    }

    @GetMapping(
        path = "/normalize/{code}",
        produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> normalize(
            @PathVariable String code) {
        return service.normalize(code);
    }
}
```

Controller **trả publisher**, không gọi `subscribe()` hoặc `block()`. Server/WebFlux infrastructure chịu trách nhiệm subscribe vào publisher và viết HTTP response khi nó phát values/complete. `/probe/context` cố ý đi qua `Schedulers.parallel()` để xác minh Reactor Context không bị mất chỉ vì thread switch.

Không có endpoint trả `Flux.never()` vì demo không cần một API cố tình không kết thúc để dạy cancellation; phần test đơn vị sẽ xử lý stream đó an toàn.

## 13. JUnit 5: kiểm thử subscription, error, backpressure, cancel và scheduler

### 13.1. ReactiveProbeServiceTest.java

Tệp `src/test/java/com/example/reactivediag/ReactiveProbeServiceTest.java`:

```java
package com.example.reactivediag;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.util.context.Context;

import static org.assertj.core.api.Assertions.assertThat;

class ReactiveProbeServiceTest {

    private final ReactiveProbeService service =
            new ReactiveProbeService();

    @Test
    void coldSourceRunsOnlyOnSubscription() {
        AtomicInteger runs = new AtomicInteger();
        Mono<String> publisher =
                service.deferredLabel("A", runs);

        assertThat(runs).hasValue(0);

        StepVerifier.create(publisher)
                .expectNext("READY-A")
                .expectComplete()
                .verify(Duration.ofSeconds(3));

        assertThat(runs).hasValue(1);

        // Cold source: another subscriber triggers it again.
        StepVerifier.create(publisher)
                .expectNext("READY-A")
                .expectComplete()
                .verify(Duration.ofSeconds(3));

        assertThat(runs).hasValue(2);
    }

    @Test
    void validInputCompletesWithValue() {
        StepVerifier.create(service.normalize(" ab-12 "))
                .expectNext("AB-12")
                .expectComplete()
                .verify(Duration.ofSeconds(3));
    }

    @Test
    void invalidInputEmitsError() {
        StepVerifier.create(service.normalize("  "))
                .expectErrorMatches(ex ->
                    ex instanceof IllegalArgumentException
                    && "code must not be blank"
                        .equals(ex.getMessage()))
                .verify(Duration.ofSeconds(3));
    }

    @Test
    void noContextUsesExplicitFallback() {
        StepVerifier.create(
                    service.requestIdAfterSwitch(
                        Schedulers.parallel()))
                .expectNext("missing")
                .expectComplete()
                .verify(Duration.ofSeconds(3));
    }

    @Test
    void contextSurvivesPublishOn() {
        Scheduler worker = Schedulers.newSingle("context-test");
        try {
            StepVerifier.create(
                    service.requestIdAfterSwitch(worker)
                        .contextWrite(
                            Context.of(
                                "requestId", "REQ-42")))
                .expectNext("REQ-42")
                .expectComplete()
                .verify(Duration.ofSeconds(3));
        } finally {
            worker.dispose();
        }
    }

    @Test
    void eachSubscriberHasItsOwnContext() {
        Mono<String> source = service.requestIdAfterSwitch(
                Schedulers.parallel());

        StepVerifier.create(source.contextWrite(
                    Context.of("requestId", "REQ-A")))
                .expectNext("REQ-A")
                .expectComplete()
                .verify(Duration.ofSeconds(3));

        StepVerifier.create(source.contextWrite(
                    Context.of("requestId", "REQ-B")))
                .expectNext("REQ-B")
                .expectComplete()
                .verify(Duration.ofSeconds(3));
    }

    @Test
    void rangeWaitsForExplicitDemand() {
        StepVerifier.create(
                service.numbers(),
                StepVerifierOptions.create().initialRequest(0))
            .expectSubscription()
            .thenRequest(2)
            .expectNext(1, 2)
            .thenRequest(3)
            .expectNext(3, 4, 5)
            .expectComplete()
            .verify(Duration.ofSeconds(3));
    }

    @Test
    void neverEndingTailIsCancelledRatherThanCompleted() {
        StepVerifier.create(service.numbersThenNever())
                .expectNext(1, 2, 3)
                .thenCancel()
                .verify(Duration.ofSeconds(3));
    }

    @Test
    void boundedElasticMovesBlockingWrapperOffCallerThread() {
        String callerThread =
                Thread.currentThread().getName();

        StepVerifier.create(service.blockingWorkThread())
                .expectNextMatches(
                    workerThread ->
                        !workerThread.equals(callerThread))
                .expectComplete()
                .verify(Duration.ofSeconds(3));
    }
}
```

Đây là **9 ca `@Test`**. Nhóm này xác minh:
- Cold publisher không hoạt động trước subscription.
- Hai subscriptions có thể kích hoạt supplier hai lần.
- `onError` khác `onComplete`.
- `deferContextual` đọc giá trị sau scheduler switch.
- Hai subscribers có **Context riêng**, không phụ thuộc một `ThreadLocal` dùng chung.
- Request-n được cấp rõ bằng `thenRequest`.
- Một stream có đuôi `never` được cancel thay vì chờ complete vô hạn.
- `boundedElastic` được dùng để offload callable khỏi JUnit thread.

**Lưu ý về assertions:** Test `boundedElasticMovesBlockingWrapperOffCallerThread` capture `callerThread` **trước subscription**, vì predicate `expectNextMatches` có thể được thực thi trên worker thread. So sánh `Thread.currentThread().getName()` bên trong predicate với work thread sẽ sai mục tiêu. Không assert `boundedElastic-1` vì tên thread không phải business contract.

### 13.2. Vì sao `AtomicInteger` giúp thấy số subscriptions?

Một test chỉ `assertNext("READY-A")` không chứng minh publisher đã thực thi đúng số lần. `AtomicInteger` trong source cho phép assert **không chạy ở assembly**, **chạy một lần khi verifier subscribe**, rồi **chạy lần hai khi một verifier khác subscribe**. Đây là kỹ thuật chẩn đoán cold publisher, không phải khuyến nghị đặt atomic counters vào business services thật chỉ để test.

## 14. JUnit 5: Virtual time, interval và timeout có kiểm soát

### 14.1. ReactiveProbeVirtualTimeTest.java

Tệp `src/test/java/com/example/reactivediag/ReactiveProbeVirtualTimeTest.java`:

```java
package com.example.reactivediag;

import java.time.Duration;

import org.junit.jupiter.api.Test;

import reactor.test.StepVerifier;

class ReactiveProbeVirtualTimeTest {

    private final ReactiveProbeService service =
            new ReactiveProbeService();

    @Test
    void oneDayDelayFinishesWithoutOneDayOfWallClock() {
        StepVerifier.withVirtualTime(() ->
                    service.delayedSignal(
                        Duration.ofDays(1)))
                .expectSubscription()
                .expectNoEvent(Duration.ofDays(1))
                .expectNext(0L)
                .expectComplete()
                .verify(Duration.ofSeconds(3));
    }

    @Test
    void infiniteIntervalBecomesFiniteWithTake() {
        StepVerifier.withVirtualTime(() ->
                    service.hourlyTicks(2))
                .expectSubscription()
                .thenAwait(Duration.ofHours(2))
                .expectNext(0L, 1L)
                .expectComplete()
                .verify(Duration.ofSeconds(3));
    }

    @Test
    void businessTimeoutReturnsFallback() {
        StepVerifier.withVirtualTime(() ->
                    service.timeoutFallback(
                        Duration.ofHours(1)))
                .expectSubscription()
                .thenAwait(Duration.ofHours(1))
                .expectNext("timed-out")
                .expectComplete()
                .verify(Duration.ofSeconds(3));
    }
}
```

Ba tests trên kiểm tra behavior của timed operators bằng **virtual time**. `withVirtualTime` nhận lambda **gọi service để tạo publisher mới**, tránh capture source/scheduler quá sớm.

**Phân biệt hai đồng hồ:**
- `Duration.ofDays(1)` hoặc `Duration.ofHours(1)` là **virtual duration của pipeline**.
- `verify(Duration.ofSeconds(3))` là **real timeout cho JUnit** nếu test không tiến/không kết thúc như mong đợi.

Không khẳng định các test trên đã hoàn thành trong đúng vài mili-giây ở mọi máy; đó là behavior dự kiến, phải xem Gradle report sau khi chạy.

### 14.2. Test timing luôn cần terminal expectation

Một test chỉ gọi `thenAwait(Duration.ofHours(2))` không xác nhận có hai ticks hoặc completion. Hai examples quan trọng trong source là:
- `hourlyTicks(2)` dùng `take(2)`: phát `0L`, `1L` rồi complete.
- `timeoutFallback`: source never tự bị `timeout`, rồi `onErrorResume` phát `timed-out` và complete.

Với một SSE infinite stream không có `take(n)`, test nên `thenCancel` thay vì luôn `expectComplete`.

## 15. WebTestClient: request Context qua WebFilter và controller

### 15.1. ReactiveProbeWebTest.java

Tệp `src/test/java/com/example/reactivediag/ReactiveProbeWebTest.java`:

```java
package com.example.reactivediag;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class ReactiveProbeWebTest {

    @Autowired
    WebTestClient client;

    @Test
    void requestIdFromHeaderSurvivesSchedulerSwitch() {
        client.get()
                .uri("/probe/context")
                .header("X-Request-Id", "HTTP-REQ-42")
                .accept(MediaType.TEXT_PLAIN)
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("HTTP-REQ-42");
    }

    @Test
    void missingHeaderUsesAnonymousRequestId() {
        client.get()
                .uri("/probe/context")
                .accept(MediaType.TEXT_PLAIN)
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("anonymous");
    }

    @Test
    void controllerReturnsNormalizedValue() {
        client.get()
                .uri("/probe/normalize/abc-12")
                .accept(MediaType.TEXT_PLAIN)
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("ABC-12");
    }
}
```

Ba Spring integration tests kiểm chứng:
- Full WebFlux mock application context chứa `RequestIdWebFilter`, controller và service.
- `X-Request-Id` được filter ghi vào Reactor Context và đọc trong service **sau `publishOn`**.
- Khi không có header, filter ghi `anonymous` nên kết quả deterministic.
- Controller trả publisher để WebFlux xử lý response và complete.

**Không đánh đồng:** Test dùng `WebEnvironment.MOCK`, `@AutoConfigureWebTestClient` nên không chứng minh TCP socket Netty đã bind thành công. Nếu muốn end-to-end HTTP server/network behavior, dùng `@SpringBootTest(webEnvironment=RANDOM_PORT)` và test client đi qua port thật. Khi debug, mô phỏng mock exchange là một bước phân tách hữu ích trước khi gắn lỗi cho Reactor Netty.

### 15.2. Timeout của WebTestClient phải đúng contract

Nếu một endpoint trả một `Flux` có stream kéo dài, việc gọi `expectBodyList(...)` đòi aggregation hoàn thành có thể timeout dù streaming đúng yêu cầu. Với SSE, dùng streaming response assertions, `returnResult(...).getResponseBody()` rồi `StepVerifier` kiểm tra số events cần thiết và cancel, hoặc `WebTestClient` API dành cho streaming tương ứng.

Nếu endpoint đáng lẽ finite nhưng không complete, hãy kiểm tra publisher trả bởi controller trước bằng StepVerifier; nếu nó complete nhưng HTTP vẫn timeout, kiểm tra WebFilter, codecs, content negotiation, body writer và server transport ở tầng HTTP.

## 16. PublisherProbe và TestPublisher: biết nhánh nào đã được subscribe

`reactor-test` còn có `PublisherProbe` để theo dõi subscription/request/cancellation mà không phải sửa business code.

### 16.1. PublisherProbeTest.java

Tệp `src/test/java/com/example/reactivediag/PublisherProbeTest.java`:

```java
package com.example.reactivediag;

import java.time.Duration;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;

class PublisherProbeTest {

    @Test
    void emptySourceUsesSubscribedFallback() {
        PublisherProbe<String> fallback =
                PublisherProbe.of(Mono.just("fallback"));

        Mono<String> result =
                Mono.<String>empty()
                    .switchIfEmpty(fallback.mono());

        StepVerifier.create(result)
                .expectNext("fallback")
                .expectComplete()
                .verify(Duration.ofSeconds(3));

        fallback.assertWasSubscribed();
        fallback.assertWasRequested();
        fallback.assertWasNotCancelled();
    }

    @Test
    void nonEmptySourceDoesNotSubscribeFallback() {
        PublisherProbe<String> fallback =
                PublisherProbe.of(Mono.just("fallback"));

        Mono<String> result =
                Mono.just("primary")
                    .switchIfEmpty(fallback.mono());

        StepVerifier.create(result)
                .expectNext("primary")
                .expectComplete()
                .verify(Duration.ofSeconds(3));

        fallback.assertWasNotSubscribed();
    }
}
```

Hai tests này chứng minh fallback branch **có** hoặc **không** được subscribe, thay vì chỉ assert value cuối rồi suy ra execution path. `PublisherProbe` phù hợp để kiểm tra `switchIfEmpty`, `then`, cancellation behavior và những pipeline có nhiều nhánh.

### 16.2. TestPublisher cho nguồn được điều khiển bởi test

Một cách tạo publisher phát signals tại thời điểm test chọn:

```java
TestPublisher<String> publisher = TestPublisher.create();

StepVerifier.create(publisher.flux())
        .then(() -> publisher.next("A"))
        .expectNext("A")
        .then(publisher::complete)
        .expectComplete()
        .verify(Duration.ofSeconds(3));
```

Đây là **fragment** cần import `reactor.test.publisher.TestPublisher`. Điểm then chốt là `then(...)` diễn ra **sau khi verifier đã subscribe**, nên tránh race “emit trước subscribe”. Với streams sử dụng buffer hoặc nguồn hot thật, cần cấu hình publisher đúng semantics production; TestPublisher chủ yếu là test double kiểm soát signals.

`TestPublisher` cũng có noncompliant variants để thử handling Reactive Streams violations, nhưng chỉ dùng trong tests riêng có mục tiêu rõ. Không làm sai chuẩn một publisher production chỉ để khiến test nhanh hơn.

## 17. Reactive transactions, security và WebFlux context: kiểm thử ở đúng lớp

### 17.1. ReactiveTransactionManager và Reactor Context

Một Spring Data R2DBC service có thể dùng `@Transactional` trên `Mono`/`Flux` hoặc `TransactionalOperator` để tạo reactive transaction context. Transaction được liên kết với subscriber/reactive chain, **không phải chỉ `ThreadLocal` của JUnit method**.

Một ca test dễ lỗi:

```java
@Transactional
@Test
void shouldRollback() {
    service.createReactive(entity).subscribe();
    // Method kết thúc trước pipeline,
    // test-managed transaction không bao phủ reactive work
    // theo cách test tưởng.
}
```

Đây là anti-pattern minh họa, **không thuộc runnable project** vì không có R2DBC dependency. Cần test-specific reactive transaction manager và composed publisher:
```java
StepVerifier.create(
        transactionalOperator.transactional(
            service.createReactive(entity)))
    .expectNextCount(1)
    .expectComplete()
    .verify(Duration.ofSeconds(5));
```

Đây là fragment có `transactionalOperator`, `service`, `entity` được định nghĩa trong project R2DBC thật. Kiểm tra commit/rollback ở DB bằng query độc lập và cleanup; không suy ra transaction thành công chỉ từ `onComplete` của một publisher giả lập.

### 17.2. Spring Security reactive

Trong WebFlux, principal/security context có thể được giữ trong Reactor Context qua `ReactiveSecurityContextHolder`. Một test `@WebFluxTest` có Spring Security nên dùng test support cho WebFlux (ví dụ `spring-security-test` và `SecurityMockServerConfigurers.mockUser` theo cấu hình phù hợp), không chỉ `SecurityContextHolder` thread-local như servlet.

Khi một `WebFilter` hoặc service dùng `subscribe()` thủ công ngoài chain, security context có thể không theo subscriber mới. Điều này không được “sửa” bằng cách thêm `ThreadLocal.set` ngẫu nhiên: cần bảo toàn reactive chain và các configurers đúng test framework.

### 17.3. Logging/MDC/tracing propagation

`contextWrite(Context.of("requestId", ...))` đặt giá trị trong Reactor Context; nó **không tự ghi giá trị đó vào SLF4J MDC**. Nếu test log mong `traceId` sau `publishOn`, cần Micrometer tracing/Context Propagation integration cụ thể, `ThreadLocalAccessor` và scope cleanup. Đừng assert `MDC.get("traceId")` mà app không cấu hình tracing; cũng đừng suy ra HTTP traceparent đã được propagate chỉ vì service đọc `requestId`.

**Quan trọng:** Cả reactive transaction, security và tracing đều có semantics riêng. Test `requestId` chứng minh Context propagation của một key trong same chain, không tự chứng minh security authorization, transactional consistency hoặc distributed trace export.

## 18. Khi test chỉ fail trên CI hoặc khi chạy song song

Một test reactive có thể pass riêng nhưng fail khi suite chạy nhiều forks/threads do:
- VirtualTimeScheduler/global Scheduler factory được đổi/reset giữa tests.
- `Hooks.onOperatorDebug()` được bật rồi không reset.
- Custom `Schedulers.newSingle` không dispose, thread leak.
- Static sinks/shared subscribers còn sống sau test.
- Test khác dùng chung Redis/DB topics, queues hoặc file path.
- `@DirtiesContext` đóng cached Spring `ApplicationContext` khi một reactive pipeline đang dùng.
- `@MockitoBean` trong context shared bị test khác reset/stub đồng thời.
- `@Transactional` test thread bị hiểu nhầm với reactive transaction context.
- Container CPU quota làm scheduling latency tăng mạnh.
- Reactive Netty event loop bị blocking/JDBC work chiếm.
- JUnit method tự tạo background subscription, không cancel trong teardown.

### 18.1. Thứ tự debug hợp lý

1. Chạy đúng test class/method qua Gradle `--tests`.
2. Xem StepVerifier có `verify` và deadline không.
3. Xác định nguồn hữu hạn/vô hạn, terminal contract đúng không.
4. Capture `doOnSubscribe`, `doOnRequest`, `doOnNext`, `doOnError`, `doFinally` tại ranh giới đáng nghi.
5. Dùng `StepVerifierOptions.initialRequest(0)` để bóc tách demand nếu có.
6. Đổi thành explicit scheduler per test và dispose đúng; tránh global shutdown.
7. Test Reactor Context trực tiếp bằng `deferContextual` sau `publishOn`.
8. Nếu WebFlux, test service publisher riêng rồi full mock `WebTestClient` rồi mới chạy server socket.
9. Tắt Gradle forks/JUnit concurrency từng tầng để tìm race.
10. Đo actual thread count, active Netty event-loop, boundedElastic queue và DB connection pool.
11. Khi có lỗi, giữ original stack trace và operator checkpoint trước khi retry.
12. Sau khi sửa, chạy suite và CI profile thật, không chỉ một test single-thread.

### 18.2. Reactor debug tooling

Reactor hỗ trợ `.checkpoint("meaningful-stage")`, `Hooks.onOperatorDebug()`, `ReactorDebugAgent` và tín hiệu logging để gắn operator assembly information vào errors.

```java
return repository.findById(id)
        .switchIfEmpty(Mono.error(
            new IllegalStateException("not found")))
        .checkpoint("load-order-by-id");
```

Đây là fragment có `repository` và `id` khai báo trong ứng dụng khác. `.checkpoint` cho một nhãn hữu ích để đọc stack trace mà không cần bật `Hooks.onOperatorDebug()` trên toàn JVM. Global debug hooks có overhead và side effects, nên ưu tiên bật ở diagnostic profile/test có kiểm soát rồi reset theo API khi kết thúc.

### 18.3. Log signals mà không biến test thành phụ thuộc order

```java
Flux<Integer> debug = Flux.range(1, 3)
    .doOnSubscribe(s -> log.debug("subscribed"))
    .doOnRequest(n -> log.debug("requested {}", n))
    .doOnNext(n -> log.debug("next {}", n))
    .doOnError(e -> log.debug("error", e))
    .doFinally(type -> log.debug("finally {}", type));
```

Đây là fragment có `log` từ SLF4J/logger đã khai báo. Các callbacks giúp quan sát subscription, demand và termination/cancel. Không viết JUnit assert chính xác thứ tự mọi log lines giữa nhiều threads: interleaving phụ thuộc scheduler. `doFinally` nhận `SignalType` (như `ON_COMPLETE`, `ON_ERROR`, `CANCEL`) hữu ích khi theo dõi lifecycle cleanup.

## 19. Tại sao reactive test timeout không nên chỉ tăng timeout?

Tăng `verify(Duration.ofSeconds(2))` lên 30 giây có thể hợp lý khi thật sự có external I/O chậm theo SLA, nhưng không sửa:
- `Flux.never()` đáng lẽ phải complete.
- Subscriber không `request(n)`.
- `withVirtualTime` chưa advance clock.
- `Mono.just(blockingCall())` gọi source trước scheduler switch.
- Event-loop bị `block()` hoặc JDBC chiếm.
- `contextWrite` nằm sai ranh giới subscriber.
- Test `subscribe()` mà không await.
- `@Transactional` test bị hiểu sai thread/context.
- Hot sink emit trước subscription.
- Scheduler/executor leak hoặc shared test context race.

Nếu tăng timeout thực sự sửa một flaky test, phải chứng minh **độ trễ thực** là hợp lệ theo contract và ghi nhận load/CI budgets. Với timer-dependent behavior, virtual time giúp giảm time/cost đáng kể hơn là tăng wall-clock sleep.

## 20. Lệnh chạy dự án mẫu và đọc reports

Với Gradle wrapper đã có trong project:

Linux/macOS:

```bash
./gradlew test --tests "com.example.reactivediag.ReactiveProbeServiceTest"
./gradlew test --tests "com.example.reactivediag.ReactiveProbeVirtualTimeTest"
./gradlew test --tests "com.example.reactivediag.ReactiveProbeWebTest"
./gradlew test --tests "com.example.reactivediag.PublisherProbeTest"
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.reactivediag.ReactiveProbeServiceTest"
.\gradlew.bat test --tests "com.example.reactivediag.ReactiveProbeVirtualTimeTest"
.\gradlew.bat test --tests "com.example.reactivediag.ReactiveProbeWebTest"
.\gradlew.bat test --tests "com.example.reactivediag.PublisherProbeTest"
.\gradlew.bat test
```

**Đếm source tests:** `ReactiveProbeServiceTest` có **9** ca, `ReactiveProbeVirtualTimeTest` có **3** ca, `ReactiveProbeWebTest` có **3** ca, `PublisherProbeTest` có **2** ca: tổng **17 JUnit `@Test` methods** được viết. Đây là số source methods/expected discovery của sample, **không phải bằng chứng 17 tests đã chạy PASS**.

Sau khi chạy, xem:
- `build/reports/tests/test/index.html` (HTML report).
- `build/test-results/test/` (JUnit XML results).
- Full stack traces và Gradle task state.
- Tests đã execute hay `UP-TO-DATE`/`FROM-CACHE`/`NO-SOURCE`.
- JVM threads có còn sống sau test không và có timeout/error bị swallowed không.

Nếu dùng Maven thay Gradle, cần một `pom.xml` hoàn chỉnh với Spring Boot BOM, reactor-test, JUnit launcher và Surefire; không thể chạy ngay `./mvnw test` nếu project chỉ có `build.gradle`. Dùng `javac` đơn lẻ cũng không đủ vì Spring/Reactor/JUnit dependencies phải có trên classpath.

### 20.1. Chạy chậm/treo tại một method?

```bash
./gradlew test --tests "com.example.reactivediag.ReactiveProbeServiceTest.neverEndingTailIsCancelledRatherThanCompleted" --info
```

Nếu method này treo, cần xem `Flux.range(...).concatWith(Flux.never())` có thực sự được cancel bởi `thenCancel`, hoặc có global hooks/schedulers từ test khác gây ảnh hưởng hay không. Lệnh `--info` hữu ích để lấy task/test process diagnostics nhưng không cung cấp thay cho Reactor signals logs.

### 20.2. Không kết luận từ chỉ một BUILD SUCCESSFUL

Một test thiếu `verify` có thể kết thúc xanh mà publisher chưa được subscribe. Một Gradle task có thể `UP-TO-DATE` vì kết quả trước đó. Một test bị `@Disabled` hoặc tag filter có thể không chạy. Hãy đối chiếu assertions/signal path và counts ở reports.

## 21. Anti-patterns và cách sửa ngắn

| Anti-pattern | Vì sao sai | Cách đúng |
|---|---|---|
| Dựng StepVerifier nhưng không `verify` | Chưa subscribe | Luôn `verify(Duration)` |
| `Mono` cold nhưng assert side effect trước subscription | Work chưa chạy | Assert laziness hoặc subscribe chủ động bằng verifier |
| `expectNext` với `initialRequest=0` không `thenRequest` | Không demand | Cấp request-n rõ ràng |
| `expectComplete` với `Flux.never()` | Stream không complete | Cancel hoặc sửa business termination |
| `expectNoEvent` ở đầu | Subscription cũng là event | `expectSubscription` trước |
| `Mono.delay` được tạo trước virtual time | Có thể capture real scheduler | Tạo publisher trong supplier |
| `withVirtualTime` không `thenAwait` | Clock chưa tiến | Advance đủ duration |
| `withVirtualTime` với explicit real scheduler | Timer không dùng virtual scheduler | Inject/use scheduler phù hợp hoặc test real-time |
| `Thread.sleep` chờ async | Race với CI scheduling | StepVerifier/Future/latch |
| `Mono.just(blockingCall())` | Blocking call chạy ngay ở assembly | `fromCallable(...).subscribeOn(boundedElastic())` |
| `.block()` trong WebFlux operator | Blocking/nonblocking mismatch, deadlock | `flatMap` compose |
| `subscribe()` thủ công trong service | Mất cancellation/error/context chain | Return Publisher |
| `contextWrite` đặt ngoài subscriber path | Reader thấy context missing | Đặt downstream của reader trong same chain |
| ThreadLocal/MDC không theo publishOn | Scheduler đổi thread | Reactor Context/Micrometer propagation |
| Test reactive security đọc Servlet SecurityContextHolder | Sai context model | ReactiveSecurityContextHolder/test support |
| JDBC transaction của JUnit áp vào R2DBC | Sai transaction model | ReactiveTransactionManager/TransactionalOperator |
| Timeout operator bị nhầm verifier timeout | Một thứ sửa pipeline, một thứ bảo vệ test | Test hai semantics riêng |
| Hot publisher emit trước subscriber | Mất signal | TestPublisher/then action, sink emit result |
| `@WebFluxTest` thiếu service | Slice không quét mọi bean | @MockitoBean/@Import |
| WebTestClient đòi body hoàn chỉnh của SSE infinite | Stream không complete | Streaming assertions + cancel |
| `newSingle` không dispose | Thread/resource leak | finally dispose |
| Global Hooks reset trong tests concurrent | Ảnh hưởng cả JVM | Isolate diagnostic tests |
| Error bị `onErrorResume(Mono.empty())` nuốt | Test xanh giả | Assert failure/fallback contract |
| Test R2DBC tự subscribe trong transaction | Subscriber tách context | Compose/return publisher |
| Testcontainers/DB chưa ready | Setup race | Startup wait + dynamic properties |
| Test chỉ fail CI song song | Shared Context/Mock/DB/global scheduler | Tách tài nguyên/serial lane |

## 22. Checklist chẩn đoán trước khi gửi PR

- [ ] Test đã gọi `verify(Duration)` hoặc shortcut tương đương có deadline.
- [ ] Biết publisher là cold hay hot; khi nào subscription được tạo.
- [ ] Có `expectSubscription` nếu assert subscription signal hoặc `expectNoEvent`.
- [ ] Demand được cấp đủ nếu `initialRequest(0)`.
- [ ] `Mono.empty`, `Mono.never`, `Mono.error` được phân biệt.
- [ ] Kỳ vọng completion/error/cancellation đúng business contract.
- [ ] Infinite stream dùng `take(n)` hoặc `thenCancel()` trong test.
- [ ] Không dùng `Thread.sleep` để thay subscription/terminal signal.
- [ ] `withVirtualTime` xây publisher trong supplier, không capture timer quá sớm.
- [ ] `thenAwait`/`expectNoEvent` advance virtual clock đúng mức.
- [ ] Không gọi `block()` trên nonblocking scheduler hoặc trong WebFlux controller.
- [ ] Blocking legacy call được defer/offload lên boundedElastic khi bắt buộc.
- [ ] `publishOn` vs `subscribeOn` được đặt đúng boundary.
- [ ] Custom scheduler được `dispose()` trong finally.
- [ ] Reactor Context được đọc bằng `deferContextual`, ghi bằng `contextWrite`.
- [ ] Test kiểm tra Context sau scheduler switch nếu cần.
- [ ] Không giả định ThreadLocal/MDC tự propagate qua mọi thread.
- [ ] Reactive security/tracing/transaction sử dụng đúng context mechanism.
- [ ] Không tự `subscribe()` làm tách flow/transaction context.
- [ ] Test HTTP dùng đúng `WebTestClient` mock/slice/full server setup.
- [ ] Lỗi không bị `onErrorResume` biến thành false positive.
- [ ] Spring context/mock state không bị tests song song sửa chung.
- [ ] Không dùng global `Hooks`/`Schedulers` reset khi suite concurrent.
- [ ] Có logs/signals tại nguồn nghi vấn thay vì tăng timeout mù.
- [ ] Đọc JUnit/Gradle report thật trước khi tuyên bố PASS.

## 23. Tài liệu tham khảo chính thức

- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, `withVirtualTime`, `thenAwait`, `expectNoEvent`, `PublisherProbe`.
- [Reactor Test API — StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): verify, verify(Duration), cancellation, expectations.
- [Reactor Test API — StepVerifierOptions](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifierOptions.html): `initialRequest`, `withInitialContext`.
- [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): `publishOn`, `subscribeOn`, boundedElastic và nonblocking threads.
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): subscriber context, `contextWrite`, `deferContextual`.
- [Project Reactor — Debugging](https://projectreactor.io/docs/core/release/reference/debugging.html): `checkpoint`, operator stack traces và hooks.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@WebFluxTest`, `@AutoConfigureWebTestClient`, `@SpringBootTest`.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): bind-to-controller/context/server và reactive HTTP assertions.
- [Spring Framework — WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): reactive server, response semantics, event-loop model.
- [Spring Framework — Reactive Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): reactive transaction operator/context.
- [Micrometer — Context Propagation](https://docs.micrometer.io/context-propagation/reference/purpose.html): ThreadLocal/Reactor Context bridge.
- [JUnit Jupiter — User Guide](https://docs.junit.org/current/user-guide/): test lifecycle, assertions và reports.

**Kết luận:** Khi reactive test không hoàn tất, đừng mặc định Spring Boot bị chậm. Hãy xác nhận **subscription**, **request demand**, **terminal signal**, **scheduler** và **Reactor Context** theo đúng thứ tự. `StepVerifier` với `verify(Duration)` giúp thấy lỗi thay vì treo vô hạn; `withVirtualTime` giúp kiểm tra timers nhanh nếu publisher được tạo đúng lúc; `thenCancel` phù hợp infinite streams; `contextWrite/deferContextual` bảo toàn dữ liệu theo subscriber qua `publishOn` nhưng không tự sao chép mọi ThreadLocal. Với WebFlux, test service publisher trước, rồi kiểm tra HTTP qua `WebTestClient`, cuối cùng mới điều tra server/network. Sửa sai ranh giới/reactive contract và resource leaks, không chỉ tăng timeout để mong lần chạy kế tiếp may mắn.