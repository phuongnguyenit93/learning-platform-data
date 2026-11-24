# Dùng thời gian ảo cho timeout, retry và nguồn phát định kỳ

Các pipeline Reactor thường phụ thuộc vào thời gian: request có timeout, retry dùng backoff, heartbeat phát định kỳ hoặc một nguồn `Flux.interval` tạo sự kiện theo chu kỳ. Nếu kiểm thử các pipeline này bằng đồng hồ thật, test có thể phải chờ nhiều giây hoặc nhiều phút, dễ chậm và không ổn định khi máy chạy tải cao.

Reactor Test cung cấp **virtual time** để tiến đồng hồ kiểm thử theo yêu cầu. Thay vì chờ thời gian thực trôi qua, test điều khiển scheduler ảo để chạy các tác vụ đã đến hạn. `StepVerifier.withVirtualTime(...)` kết hợp với `VirtualTimeScheduler` giúp kiểm thử timeout, retry và nguồn định kỳ nhanh, xác định và không phụ thuộc vào `Thread.sleep`.

Virtual time chỉ điều khiển các tác vụ được lập lịch trên scheduler mà nó quản lý. Nó không làm TCP, WebSocket, Netty event loop, database hoặc một thread tùy ý chạy nhanh hơn. Vì vậy, cần phân biệt kiểm thử logic thời gian của Reactor với kiểm thử tích hợp transport RSocket thực.

## 1. Vì sao cần thời gian ảo?

Giả sử một service chỉ trả kết quả sau 30 giây:

```java
Mono<String> response = Mono.delay(Duration.ofSeconds(30))
    .thenReturn("ready");
```

Test dùng thời gian thật phải chờ đủ 30 giây cho một trường hợp thành công. Nếu kiểm thử timeout 10 giây, retry backoff 1 + 2 + 4 giây và heartbeat mỗi giây trong 2 phút, tổng thời gian test tăng nhanh.

Virtual time cho phép test nhảy tới mốc cần kiểm tra:

```text
Thời gian thực:
0s ------------------------------ 30s
       test phải chờ 30 giây

Thời gian ảo:
0s -- advanceTimeBy(30s) --> 30s
       scheduler chạy các task đến hạn
```

Lợi ích chính:

- Kiểm thử timeout và backoff mà không chờ lâu.
- Xác minh chính xác thời điểm retry hoặc phát sự kiện định kỳ.
- Giảm flakiness do scheduling và tải máy.
- Kiểm tra cancellation và completion sau một số chu kỳ xác định.
- Giữ test thời gian ở dạng deterministic, dễ đọc và dễ bảo trì.

## 2. Các thành phần cần biết

| Thành phần | Vai trò |
|---|---|
| `reactor-test` | Cung cấp công cụ kiểm thử Reactor như `StepVerifier` và `VirtualTimeScheduler`. |
| `StepVerifier` | Subscribe publisher, phát demand và xác minh signal theo kịch bản. |
| `StepVerifier.withVirtualTime(...)` | Tạo môi trường test với virtual scheduler trước khi publisher được assemble. |
| `VirtualTimeScheduler` | Scheduler có đồng hồ do test điều khiển. |
| `thenAwait(Duration)` | Tiến thời gian ảo và chạy task đến hạn trong khoảng đó. |
| `expectNoEvent(Duration)` | Tiến thời gian và xác minh không có signal trong khoảng đó. |
| `advanceTimeBy(...)` | Tiến trực tiếp `VirtualTimeScheduler` một khoảng thời gian. |
| `advanceTimeTo(...)` | Tiến scheduler đến một mốc thời gian ảo cụ thể. |

Thêm dependency `reactor-test` ở test scope. Nếu dùng Spring Boot dependency management, để BOM quản lý phiên bản Reactor đồng bộ với Reactor Core:

```kotlin
dependencies {
    testImplementation("io.projectreactor:reactor-test")
}
```

Với Maven:

```xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>
```

## 3. Nguyên tắc quan trọng: tạo publisher bên trong supplier

`StepVerifier.withVirtualTime` nhận một `Supplier` tạo publisher. Publisher cần được tạo **sau khi virtual scheduler đã được cài đặt** để các operator thời gian lấy đúng scheduler ảo.

Đúng:

```java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofHours(1)))
    .expectSubscription()
    .thenAwait(Duration.ofHours(1))
    .expectNext(0L)
    .verifyComplete();
```

Không nên assemble publisher thời gian trước rồi truyền instance đã tạo sẵn:

```java
Mono<Long> delayed = Mono.delay(Duration.ofHours(1));

// Không phù hợp cho virtual time: scheduler có thể đã được lấy
// trước khi StepVerifier cài đặt virtual scheduler.
StepVerifier.withVirtualTime(() -> delayed)
    .thenAwait(Duration.ofHours(1))
    .expectNext(0L)
    .verifyComplete();
```

Quy tắc này đặc biệt quan trọng với `Mono.delay`, `Flux.interval`, `delayElements`, `delaySubscription`, `timeout` và retry backoff. Hãy assemble toàn bộ pipeline bên trong supplier, kể cả operator dùng scheduler mặc định.

`Mono.defer(...)` cũng hữu ích vì nó trì hoãn việc tạo publisher con đến lúc subscribe:

```java
Mono<String> lazyOperation = Mono.defer(() ->
    Mono.delay(Duration.ofSeconds(5))
        .thenReturn("done"));
```

Tuy vậy, `defer` không tự động thay thế yêu cầu tạo pipeline trong supplier của `withVirtualTime`. Hãy giữ cả hai khi cần kiểm soát thời điểm assemble và thời điểm thực thi.

## 4. Kiểm thử một publisher phát trễ

Ví dụ nguồn chỉ phát giá trị sau 10 giây:

```java
@Test
void emitsAfterTenVirtualSeconds() {
    StepVerifier.withVirtualTime(() ->
            Mono.delay(Duration.ofSeconds(10)))
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(10))
        .expectNext(0L)
        .verifyComplete();
}
```

`thenAwait` tiến virtual clock 10 giây. Scheduler chạy các task có deadline trong khoảng đó, nên `Mono.delay` phát giá trị mà test không phải chờ 10 giây thực.

Nếu muốn xác minh chưa có giá trị trước deadline:

```java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofSeconds(10)))
    .expectSubscription()
    .expectNoEvent(Duration.ofSeconds(9))
    .thenAwait(Duration.ofSeconds(1))
    .expectNext(0L)
    .verifyComplete();
```

`expectNoEvent` cũng xem subscription là một event. Vì vậy, hãy dùng `expectSubscription()` trước khi gọi `expectNoEvent(...)`; nếu không, test có thể thất bại ngay khi subscribe.

## 5. `thenAwait` và `expectNoEvent` khác nhau thế nào?

Hai bước này đều tiến thời gian ảo, nhưng ý nghĩa xác minh khác nhau:

| Bước | Hành vi | Dùng khi |
|---|---|---|
| `thenAwait(duration)` | Tiến virtual clock và xử lý task đến hạn; không khẳng định publisher im lặng. | Muốn đi tới mốc thời gian rồi kiểm tra signal tiếp theo. |
| `expectNoEvent(duration)` | Tiến virtual clock và thất bại nếu có signal trong khoảng đó. | Muốn chứng minh chưa timeout/chưa retry/chưa phát tick. |
| `then(...)` | Chạy assertion hoặc side effect đồng bộ tại bước hiện tại. | Kiểm tra bộ đếm attempt, mock invocation hoặc trạng thái test. |

Ví dụ xác minh timeout chưa xảy ra ở giây thứ hai nhưng xảy ra ở giây thứ ba:

```java
StepVerifier.withVirtualTime(() ->
        Mono.never().timeout(Duration.ofSeconds(3)))
    .expectSubscription()
    .expectNoEvent(Duration.ofSeconds(2))
    .thenAwait(Duration.ofSeconds(1))
    .expectError(TimeoutException.class)
    .verify();
```

Ở đây `expectNoEvent` chứng minh hai giây đầu không có signal; `thenAwait` đưa clock tới deadline. Sau deadline, `timeout` phát lỗi.

## 6. Kiểm thử `timeout`

`timeout` phát `TimeoutException` nếu upstream không phát signal cần thiết trong khoảng thời gian cho phép. Với `Mono`, điều đó thường có nghĩa không nhận được `onNext`/terminal signal trước deadline.

```java
@Test
void timesOutWhenResponseIsTooSlow() {
    StepVerifier.withVirtualTime(() ->
            Mono.delay(Duration.ofSeconds(8))
                .map(ignored -> "response")
                .timeout(Duration.ofSeconds(3)))
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(3))
        .expectError(TimeoutException.class)
        .verify();
}
```

Nguồn dự kiến trả kết quả sau 8 giây nhưng timeout được đặt ở 3 giây. Khi deadline đến, `timeout` hủy upstream và phát lỗi. Test xác minh thời điểm và loại lỗi mà không phải chờ thực.

### Timeout có fallback

Nếu API dùng fallback publisher, kiểm thử giá trị thay thế:

```java
@Test
void returnsFallbackWhenResponseTimesOut() {
    StepVerifier.withVirtualTime(() ->
            Mono.<String>never()
                .timeout(
                    Duration.ofSeconds(2),
                    Mono.just("cached")))
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(2))
        .expectNext("cached")
        .verifyComplete();
}
```

Fallback chỉ được subscribe khi timeout xảy ra. Nếu fallback cũng phụ thuộc thời gian, nó cần dùng scheduler được virtualize hoặc scheduler được inject.

### Kiểm tra timeout và cancellation

`timeout` thường hủy upstream khi deadline đến. Có thể xác minh cancellation bằng `doFinally` hoặc `doOnCancel`:

```java
@Test
void cancelsTheSlowUpstreamAfterTimeout() {
    AtomicBoolean cancelled = new AtomicBoolean();

    StepVerifier.withVirtualTime(() ->
            Mono.<String>never()
                .doOnCancel(() -> cancelled.set(true))
                .timeout(Duration.ofSeconds(4)))
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(4))
        .expectError(TimeoutException.class)
        .verify();

    assertThat(cancelled).isTrue();
}
```

Test này xác minh timeout không chỉ phát lỗi mà còn hủy nguồn đang chờ. Với publisher bọc một API ngoài Reactor, cancellation chỉ có tác dụng nếu adapter thực sự truyền cancellation xuống resource bên dưới.

## 7. Scheduler tường minh cho timeout

Các overload có scheduler cho phép ứng dụng kiểm soát scheduler dùng để đo deadline:

```java
Mono<Reply> withTimeout(
        Mono<Reply> response,
        Duration timeout,
        Scheduler timerScheduler) {

    return response.timeout(timeout, timerScheduler);
}
```

Trong production, `timerScheduler` có thể là scheduler phù hợp với ứng dụng. Trong test, truyền `VirtualTimeScheduler`:

```java
@Test
void usesInjectedVirtualSchedulerForTimeout() {
    VirtualTimeScheduler clock = VirtualTimeScheduler.create();
    try {
        Mono<String> result = withTimeout(
            Mono.never(),
            Duration.ofSeconds(5),
            clock);

        StepVerifier.withVirtualTime(
                () -> result,
                () -> clock)
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(5))
            .expectError(TimeoutException.class)
            .verify();
    } finally {
        clock.dispose();
    }
}
```

Trong ví dụ này publisher `result` được tạo trước, nhưng timeout dùng scheduler được truyền tường minh là `clock`; supplier của StepVerifier trả đúng publisher và cùng scheduler. Với operator dùng scheduler mặc định, vẫn phải assemble pipeline bên trong supplier như các ví dụ trước.

## 8. Kiểm thử retry backoff

`Retry.backoff(maxRetries, minBackoff)` chờ một khoảng thời gian tăng dần giữa các lần subscribe lại. Với `minBackoff = 1s`, các lần chờ cơ bản là 1 giây, 2 giây, 4 giây... cho đến giới hạn cấu hình. Jitter mặc định có thể làm khoảng chờ thay đổi ngẫu nhiên; trong test thời gian chính xác, đặt `.jitter(0)`.

Ví dụ thao tác thất bại hai lần rồi thành công:

```java
@Test
void retriesWithExponentialBackoff() {
    AtomicInteger attempts = new AtomicInteger();
    VirtualTimeScheduler clock = VirtualTimeScheduler.create();

    try {
        StepVerifier.withVirtualTime(
                () -> Mono.defer(() -> {
                    int attempt = attempts.incrementAndGet();
                    if (attempt < 3) {
                        return Mono.error(
                            new IOException("temporary failure"));
                    }
                    return Mono.just("ok");
                }).retryWhen(
                    Retry.backoff(2, Duration.ofSeconds(1))
                        .jitter(0)
                        .onRetryExhaustedThrow((spec, signal) ->
                            signal.failure())
                        .scheduler(clock)),
                () -> clock)
            .expectSubscription()
            .then(() -> assertThat(attempts).hasValue(1))
            .thenAwait(Duration.ofSeconds(1))
            .then(() -> assertThat(attempts).hasValue(2))
            .thenAwait(Duration.ofSeconds(2))
            .expectNext("ok")
            .verifyComplete();
    } finally {
        clock.dispose();
    }

    assertThat(attempts).hasValue(3);
}
```

Timeline của test:

| Thời điểm ảo | Hành động |
|---:|---|
| 0 giây | Attempt 1 thất bại. |
| 1 giây | Retry lần 1, attempt 2 thất bại. |
| 3 giây | Retry lần 2, attempt 3 thành công. |

`maxRetries = 2` nghĩa là tối đa hai lần retry sau lần subscribe đầu tiên, tức tổng cộng ba attempts. Nếu publisher thất bại cả ba lần, kết quả cuối cùng sẽ là lỗi.

### Kiểm tra hết số lần retry

```java
@Test
void stopsAfterConfiguredRetries() {
    AtomicInteger attempts = new AtomicInteger();
    VirtualTimeScheduler clock = VirtualTimeScheduler.create();

    try {
        StepVerifier.withVirtualTime(
                () -> Mono.defer(() -> {
                    attempts.incrementAndGet();
                    return Mono.error(new IOException("offline"));
                }).retryWhen(
                    Retry.backoff(2, Duration.ofSeconds(1))
                        .jitter(0)
                        .onRetryExhaustedThrow((spec, signal) ->
                            signal.failure())
                        .scheduler(clock)),
                () -> clock)
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(3))
            .expectError(IOException.class)
            .verify();
    } finally {
        clock.dispose();
    }

    assertThat(attempts).hasValue(3);
}
```

Khi hết retry, Reactor có thể phát lỗi retry exhausted tùy operator và cách unwrap lỗi; nếu ứng dụng cần kiểm tra exception cuối cùng, hãy xác minh đúng kiểu/causal chain theo phiên bản Reactor đang dùng.

## 9. Vì sao cần `Mono.defer` khi đếm retry?

Retry hoạt động bằng cách subscribe lại publisher. Nếu thao tác chỉ được tạo một lần trước subscription, test có thể đếm sai số lần thực thi hoặc không mô phỏng được một request mới cho mỗi attempt.

Ví dụ đúng:

```java
Mono<Response> operation = Mono.defer(() -> {
    int attempt = attempts.incrementAndGet();
    return clientCall(attempt);
});
```

Mỗi lần subscribe, lambda trong `defer` chạy lại. Điều này giúp test quan sát được số attempts và tạo request mới cho từng lần retry.

Không đặt việc tạo idempotency key bên trong `defer` nếu các lần retry phải đại diện cho cùng một lệnh nghiệp vụ. Hãy tạo key bên ngoài, giữ nguyên command và chỉ tạo lại publisher thực hiện gửi:

```java
TransferCommand command = createCommandWithOneStableKey();

Mono<Receipt> operation = Mono.defer(() -> send(command))
    .retryWhen(Retry.backoff(2, Duration.ofMillis(200)));
```

Như vậy mỗi attempt có thể tạo một request transport mới nhưng vẫn dùng cùng idempotency key. Đây là điểm quan trọng khi RSocket timeout xảy ra sau khi server có thể đã thực hiện side effect.

## 10. Kiểm thử `Flux.interval` và nguồn phát định kỳ

`Flux.interval(period)` phát một dãy số tăng dần theo chu kỳ. Nó thường dùng cho heartbeat, polling, refresh hoặc nguồn sự kiện định kỳ.

```java
@Test
void emitsThreePeriodicTicks() {
    StepVerifier.withVirtualTime(() ->
            Flux.interval(Duration.ofSeconds(1)).take(3))
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(3))
        .expectNext(0L, 1L, 2L)
        .verifyComplete();
}
```

Tick đầu tiên của `Flux.interval(period)` xuất hiện sau một period. Với period một giây và `take(3)`, các giá trị 0, 1, 2 xuất hiện ở giây 1, 2 và 3; sau tick thứ ba, `take(3)` hủy nguồn và hoàn tất.

### Xác minh khoảng thời gian giữa các tick

```java
StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofSeconds(2)).take(2))
    .expectSubscription()
    .expectNoEvent(Duration.ofSeconds(1))
    .thenAwait(Duration.ofSeconds(1))
    .expectNext(0L)
    .expectNoEvent(Duration.ofSeconds(1))
    .thenAwait(Duration.ofSeconds(1))
    .expectNext(1L)
    .verifyComplete();
```

Test chứng minh không có tick trong giây đầu tiên và tick xuất hiện đúng sau mỗi hai giây ảo.

## 11. Nguồn định kỳ có scheduler được inject

Trong code ứng dụng, không nên hard-code scheduler nếu cần kiểm soát thời gian khi test. Hãy inject `Scheduler` vào component:

```java
public final class HeartbeatSource {

    private final Scheduler scheduler;

    public HeartbeatSource(Scheduler scheduler) {
        this.scheduler = scheduler;
    }

    public Flux<Long> ticks(Duration period) {
        return Flux.interval(period, scheduler);
    }
}
```

Test tạo virtual scheduler riêng:

```java
@Test
void heartbeatUsesInjectedClock() {
    VirtualTimeScheduler clock = VirtualTimeScheduler.create();
    try {
        HeartbeatSource source = new HeartbeatSource(clock);

        StepVerifier.withVirtualTime(
                () -> source.ticks(Duration.ofSeconds(5)),
                () -> clock)
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(15))
            .expectNext(0L, 1L, 2L)
            .thenCancel()
            .verify();
    } finally {
        clock.dispose();
    }
}
```

Việc inject scheduler làm component dễ kiểm thử và tránh phụ thuộc vào global scheduler. Trong Spring, có thể cung cấp một bean `Scheduler` cho production và thay bằng `VirtualTimeScheduler` trong test configuration.

## 12. `advanceTimeBy` và `advanceTimeTo`

Ngoài `StepVerifier`, có thể điều khiển `VirtualTimeScheduler` trực tiếp. Cách này hữu ích khi muốn kiểm tra trạng thái nội bộ hoặc tương tác với một component không dễ mô tả hoàn toàn bằng expectation chain.

```java
@Test
void advancesSchedulerDirectly() {
    VirtualTimeScheduler clock = VirtualTimeScheduler.create();
    AtomicInteger ticks = new AtomicInteger();

    try {
        Disposable subscription = Flux.interval(
                Duration.ofSeconds(1), clock)
            .subscribe(ignored -> ticks.incrementAndGet());

        clock.advanceTimeBy(Duration.ofSeconds(3));
        assertThat(ticks).hasValue(3);

        clock.advanceTimeTo(Duration.ofSeconds(5));
        assertThat(ticks).hasValue(5);

        subscription.dispose();
    } finally {
        clock.dispose();
    }
}
```

`advanceTimeBy` cộng thêm một khoảng vào thời gian hiện tại; `advanceTimeTo` tiến tới một mốc tuyệt đối trên đồng hồ ảo. Khi tiến thời gian, scheduler chạy các task đã đến hạn theo thứ tự deadline và quy tắc lập lịch của nó.

Luôn hủy subscription và dispose scheduler trong `finally` nếu test tự tạo chúng. Điều này tránh task hoặc scheduler còn sống ảnh hưởng test khác.

## 13. Dùng `withVirtualTime` với scheduler supplier

`withVirtualTime` có overload nhận supplier cho scheduler và initial request. Overload này hữu ích khi component dùng scheduler được inject:

```java
VirtualTimeScheduler clock = VirtualTimeScheduler.create();

StepVerifier.withVirtualTime(
        () -> service.periodicUpdates(),
        () -> clock,
        0)
    .expectSubscription()
    .thenRequest(1)
    .thenAwait(Duration.ofSeconds(1))
    .expectNext(firstUpdate)
    .thenCancel()
    .verify();
```

`initialRequest = 0` giúp test kiểm soát demand rõ ràng. `thenRequest(1)` yêu cầu một phần tử, phù hợp khi muốn kiểm tra nguồn định kỳ kết hợp backpressure. Với nguồn mặc định không cần kiểm tra demand, có thể dùng overload đơn giản hơn.

Đảm bảo publisher và scheduler supplier trỏ đến cùng scheduler. Nếu component dùng một scheduler khác, virtual clock trong StepVerifier sẽ không điều khiển được tác vụ đó.

## 14. Virtual time và backpressure

Virtual time không bỏ qua demand của Reactive Streams. Một nguồn có thể đến deadline nhưng không phát `onNext` nếu downstream chưa yêu cầu phần tử. Đây là hành vi đúng của backpressure.

Ví dụ nguồn interval với initial request bằng 0:

```java
VirtualTimeScheduler clock = VirtualTimeScheduler.create();

StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofSeconds(1), clock),
        () -> clock,
        0)
    .expectSubscription()
    .thenRequest(1)
    .thenAwait(Duration.ofSeconds(1))
    .expectNext(0L)
    .thenRequest(1)
    .thenAwait(Duration.ofSeconds(1))
    .expectNext(1L)
    .thenCancel()
    .verify();
```

Ví dụ phát demand trước từng tick để nguồn không phát khi subscriber chưa sẵn sàng. Với `Flux.interval`, nếu tick phát sinh khi downstream không có demand, operator có thể báo `OverflowException` thay vì giữ vô hạn mọi tick. Khi test backpressure, hãy định nghĩa rõ mong đợi về demand, buffering, drop hoặc overflow.

## 15. Kết hợp timeout và retry

Trong ứng dụng, mỗi attempt có thể có timeout riêng, sau đó retry dùng backoff. Vị trí của `timeout` ảnh hưởng semantics:

```java
Mono<Response> perAttemptTimeout = callRemote()
    .timeout(Duration.ofSeconds(2))
    .retryWhen(Retry.backoff(2, Duration.ofSeconds(1)).jitter(0));
```

Ở đây mỗi lần subscribe lại đều có timeout hai giây. Ngược lại:

```java
Mono<Response> overallDeadline = callRemote()
    .retryWhen(Retry.backoff(2, Duration.ofSeconds(1)).jitter(0))
    .timeout(Duration.ofSeconds(5));
```

Ở đây timeout bao quanh cả chuỗi retry, tạo deadline tổng cho toàn bộ quá trình. Hai cách không tương đương.

Có thể kiểm thử từng trường hợp bằng virtual time:

```java
StepVerifier.withVirtualTime(() ->
        Mono.<String>never()
            .timeout(Duration.ofSeconds(2))
            .retryWhen(Retry.max(2)
                .onRetryExhaustedThrow((spec, signal) ->
                    signal.failure())))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(6))
    .expectError(TimeoutException.class)
    .verify();
```

Với retry backoff, hãy tính tổng thời gian chờ và timeout của từng attempt trước khi chọn khoảng `thenAwait`. Không nên đoán deadline; viết timeline để test dễ kiểm tra.

## 16. Ứng dụng vào RSocket request-response

Một RSocket requester có thể áp timeout ở application layer:

```java
Mono<OrderReply> findOrder(
        RSocketRequester requester,
        OrderQuery query,
        Scheduler timerScheduler) {

    return requester.route("orders.find")
        .data(query)
        .retrieveMono(OrderReply.class)
        .timeout(Duration.ofSeconds(2), timerScheduler);
}
```

Trong unit test, có thể thay phần gọi remote bằng một publisher giả lập như `Mono.never()` hoặc `Mono.delay(...)`, rồi truyền `VirtualTimeScheduler`. Test này kiểm tra chính sách timeout ở application layer mà không cần mở socket.

```java
@Test
void requestWrapperAppliesDeadline() {
    VirtualTimeScheduler clock = VirtualTimeScheduler.create();
    try {
        Mono<String> response = Mono.<String>never()
            .timeout(Duration.ofSeconds(2), clock);

        StepVerifier.withVirtualTime(
                () -> response,
                () -> clock)
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(2))
            .expectError(TimeoutException.class)
            .verify();
    } finally {
        clock.dispose();
    }
}
```

Nếu kiểm thử trực tiếp `RSocketRequester` qua TCP/WebSocket, timer nội bộ của client/runtime có thể thuộc scheduler hoặc event loop riêng. `VirtualTimeScheduler` không tự điều khiển mọi timer nội bộ đó. Hãy kiểm tra API/version cụ thể và dùng integration test với timeout thực có giới hạn cho hành vi transport.

## 17. Kiểm thử heartbeat và nguồn định kỳ của RSocket

Ứng dụng có thể phát heartbeat nghiệp vụ qua một route RSocket:

```java
Flux<Heartbeat> heartbeatStream(Scheduler scheduler) {
    return Flux.interval(Duration.ofSeconds(10), scheduler)
        .map(sequence -> new Heartbeat(sequence, Instant.now()));
}
```

Nếu cần kiểm thử cả timestamp, không dùng `Instant.now()` trực tiếp vì nó đọc đồng hồ thực, không phải virtual clock. Hãy inject `Clock` riêng:

```java
Flux<Heartbeat> heartbeatStream(
        Scheduler scheduler, Clock clock) {
    return Flux.interval(Duration.ofSeconds(10), scheduler)
        .map(sequence -> new Heartbeat(sequence, clock.instant()));
}
```

Test có thể dùng `Clock.fixed(...)` để xác minh timestamp cố định, hoặc một clock test có thể tiến cùng scheduler ảo nếu nghiệp vụ cần kiểm tra thời điểm. Virtual scheduler điều khiển việc chạy task; nó không tự thay đổi `System.currentTimeMillis()` hay `Instant.now()`.

Ngoài ra, RSocket `KEEPALIVE` ở tầng protocol do runtime quản lý. Test `Flux.interval` heartbeat nghiệp vụ không chứng minh frame KEEPALIVE thực được gửi đúng thời điểm. Cần test riêng runtime/transport khi muốn xác minh protocol keepalive.

## 18. Những scheduler không được virtualize tự động

`withVirtualTime` có thể thay thế các scheduler mặc định của Reactor cho các operator thời gian khi publisher được assemble đúng thời điểm. Nhưng không phải mọi công việc bất đồng bộ trong ứng dụng đều đi qua các scheduler đó.

Các trường hợp cần chú ý:

- `Schedulers.newSingle(...)`, `newParallel(...)` hoặc `newBoundedElastic(...)` được tạo trước khi virtual time bắt đầu.
- Scheduler được tạo từ `ExecutorService` hoặc thread pool tùy chỉnh.
- Netty event loop và timer nội bộ của transport.
- `ScheduledExecutorService` được gọi trực tiếp.
- `Thread.sleep`, `System.currentTimeMillis()` hoặc `Instant.now()`.
- Database driver, HTTP client hoặc SDK bên ngoài có timer riêng.

Giải pháp tốt là inject `Scheduler`, `Clock` hoặc abstraction thời gian vào component cần kiểm thử. Với dependency ngoài không cho inject clock/scheduler, dùng fake/mock ở unit test và giữ integration test thời gian thật có giới hạn.

## 19. Tránh test bị treo

Virtual time không bảo đảm mọi test tự kết thúc. Một publisher `Flux.never()` vẫn không complete nếu test không cancel hoặc không tạo timeout. Một retry không giới hạn có thể tiếp tục lập lịch mãi nếu test không đưa ra điều kiện kết thúc.

Các nguyên tắc:

1. Xác định signal cuối cùng: complete, error hay cancel.
2. Với stream vô hạn, dùng `take(n)` hoặc `thenCancel()`.
3. Giới hạn retry trong test hoặc điều khiển điều kiện dừng.
4. Dùng `verify(Duration)` để đặt giới hạn thời gian thực cho chính test.
5. Không dùng `block()` hoặc `Thread.sleep()` bên trong chuỗi virtual-time.
6. Dispose scheduler tự tạo và hủy subscription khi test kết thúc.

Ví dụ test stream vô hạn:

```java
StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofSeconds(1)))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(5))
    .expectNext(0L, 1L, 2L, 3L, 4L)
    .thenCancel()
    .verify(Duration.ofSeconds(1));
```

`verify(Duration.ofSeconds(1))` là watchdog theo thời gian thực để test không treo vô hạn. Nó không thay đổi virtual clock và không có nghĩa test đã chờ một giây cho mỗi tick.

## 20. Kiểm tra cancellation của nguồn định kỳ

Khi subscriber hủy một `Flux.interval`, nguồn phải dừng phát tick cho subscriber đó. Có thể xác minh bằng `doFinally`:

```java
@Test
void periodicSourceStopsAfterCancellation() {
    AtomicBoolean cancelled = new AtomicBoolean();

    StepVerifier.withVirtualTime(() ->
            Flux.interval(Duration.ofSeconds(1))
                .doFinally(signal -> {
                    if (signal == SignalType.CANCEL) {
                        cancelled.set(true);
                    }
                }))
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(2))
        .expectNext(0L, 1L)
        .thenCancel()
        .verify();

    assertThat(cancelled).isTrue();
}
```

Đây là cách kiểm tra publisher cleanup. Nếu publisher bọc một socket hoặc external resource, cần xác minh cancellation được truyền xuống resource đó bằng integration test phù hợp.

## 21. Test retry không làm lặp side effect ngoài ý muốn

Virtual time giúp kiểm tra số lần subscribe và thời gian giữa các lần retry, nhưng không tự bảo đảm thao tác nghiệp vụ an toàn khi gửi lặp. Với command RSocket có tác dụng phụ, test nên xác minh idempotency key ổn định:

```java
@Test
void retriesTheSameLogicalCommand() {
    UUID key = UUID.randomUUID();
    TransferCommand command = new TransferCommand(key, "A", "B", 100);
    List<UUID> receivedKeys = new CopyOnWriteArrayList<>();
    AtomicInteger attempts = new AtomicInteger();

    StepVerifier.withVirtualTime(() ->
            Mono.defer(() -> {
                receivedKeys.add(command.idempotencyKey());
                if (attempts.incrementAndGet() == 1) {
                    return Mono.error(new IOException("lost response"));
                }
                return Mono.just(new TransferReceipt("tx-1"));
            }).retryWhen(
                Retry.backoff(1, Duration.ofSeconds(1))
                    .jitter(0)))
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(1))
        .expectNextCount(1)
        .verifyComplete();

    assertThat(receivedKeys).containsExactly(key, key);
}
```

Trong test này, request thứ hai đại diện cho retry cùng một logical command nên dùng cùng key. Ở integration test, server cần được xác minh chỉ tạo một side effect và trả lại kết quả đã lưu khi nhận lại key.

## 22. Lỗi thường gặp khi dùng virtual time

| Lỗi | Vì sao xảy ra? | Cách xử lý |
|---|---|---|
| Tạo `Mono.delay`/`Flux.interval` trước supplier | Publisher có thể đã lấy scheduler thật khi assemble. | Tạo toàn bộ pipeline trong `withVirtualTime` supplier. |
| Dùng `expectNoEvent` ngay sau khi bắt đầu | Subscription cũng được tính là event. | Gọi `expectSubscription()` trước. |
| Nghĩ `thenAwait` xác minh không có signal | `thenAwait` chỉ tiến thời gian và chạy task. | Dùng `expectNoEvent` khi cần assertion im lặng. |
| Retry backoff có jitter | Deadline không còn cố định. | Đặt `.jitter(0)` trong test thời gian chính xác. |
| Scheduler custom được tạo từ trước | Virtual time không thay thế scheduler đó. | Inject scheduler và truyền `VirtualTimeScheduler`. |
| Dùng `Thread.sleep` | Sleep dùng đồng hồ thật và block thread. | Dùng `thenAwait`, `expectNoEvent` hoặc `advanceTimeBy`. |
| Dùng `Instant.now()` trong test | Đồng hồ hệ thống không chạy theo virtual time. | Inject `Clock` hoặc tách assertion thời gian thực. |
| Stream vô hạn không cancel | Publisher không có điều kiện complete. | Dùng `take(n)` hoặc `thenCancel()`. |
| Gọi `verify()` với publisher không kết thúc | Test có thể chờ mãi. | Tạo signal cuối hoặc dùng `verify(Duration)`. |
| Nghĩ virtual time điều khiển TCP/Netty | Transport có scheduler và event loop riêng. | Dùng fake publisher cho unit test và integration test thời gian thật cho transport. |
| Tạo scheduler toàn cục rồi không reset | Test khác có thể dùng nhầm clock hoặc task còn sống. | Ưu tiên scheduler riêng; dispose/reset đúng vòng đời. |

## 23. Chiến lược kiểm thử theo tầng

Không nên cố dùng virtual time cho mọi kiểm thử. Chia test theo ranh giới cần xác minh:

| Tầng kiểm thử | Nên dùng gì? | Ví dụ |
|---|---|---|
| Unit test operator | `StepVerifier.withVirtualTime` | Timeout, retry backoff, `Flux.interval`, delay. |
| Unit test component có scheduler | Inject `VirtualTimeScheduler` | Heartbeat service, polling publisher, scheduled retry. |
| Unit test logic dùng đồng hồ | Inject `Clock` | Timestamp, expiry, business deadline. |
| RSocket service test | Fake/mock response publisher + virtual scheduler | Application timeout, retry policy, idempotency key. |
| RSocket transport integration | TCP/WebSocket thật và timeout thực có giới hạn | SETUP, frame, cancellation, connection close, protocol keepalive. |
| End-to-end test | Môi trường thật hoặc test container | Latency, reconnect, server timeout và hành vi client. |

Virtual time làm unit test nhanh và xác định. Integration test vẫn cần một số kiểm tra thời gian thật vì transport, scheduler của Netty và hạ tầng bên ngoài không nhất thiết dùng Reactor virtual scheduler.

## 24. Checklist cho test thời gian

Trước khi hoàn thành test timeout, retry hoặc nguồn định kỳ, hãy kiểm tra:

- Publisher được tạo bên trong supplier của `withVirtualTime` nếu dùng scheduler mặc định.
- Scheduler custom được inject và là `VirtualTimeScheduler` trong test.
- `expectSubscription()` đứng trước `expectNoEvent(...)`.
- `thenAwait` chỉ được dùng để tiến clock; dùng assertion riêng để kiểm tra signal.
- Retry backoff được đặt jitter phù hợp cho test deterministic.
- Số lần retry được tính gồm lần đầu hay chỉ retry theo đúng API.
- Stream vô hạn có `take(n)` hoặc `thenCancel()`.
- Scheduler/subscription tự tạo được dispose/cancel.
- Không có `Thread.sleep`, `block()` hoặc `Instant.now()` ngoài chủ đích.
- Test có `verify(Duration)` khi cần watchdog thời gian thực.
- Unit test không bị nhầm với kiểm thử timer nội bộ của Netty/RSocket transport.
- Retry command có tác dụng phụ vẫn giữ cùng idempotency key.

## Tài liệu tham khảo

- [Reactor Test Reference — Testing](https://projectreactor.io/docs/core/release/reference/testing.html) — `StepVerifier`, virtual time và kiểm thử publisher.
- [Reactor Test Javadoc — StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html) — API `withVirtualTime`, expectation và verification.
- [Reactor Test Javadoc — VirtualTimeScheduler](https://projectreactor.io/docs/test/release/api/reactor/test/scheduler/VirtualTimeScheduler.html) — điều khiển thời gian ảo.
- [Reactor Core Reference — Which operator do I need?](https://projectreactor.io/docs/core/release/reference/apdx-operatorChoice.html) — các operator thời gian và retry.
- [RSocket Protocol](https://rsocket.io/about/protocol/) — các interaction model và KEEPALIVE ở tầng giao thức.

## Kết luận

Virtual time cho phép kiểm thử các publisher phụ thuộc thời gian mà không phải chờ đồng hồ thật. `StepVerifier.withVirtualTime` cài virtual scheduler trước khi publisher được tạo; `thenAwait` tiến thời gian, còn `expectNoEvent` xác minh không có signal trong khoảng đó. Dùng virtual time để kiểm tra `timeout`, retry backoff và `Flux.interval`; đặt jitter bằng 0 khi cần timeline xác định, inject scheduler/clock cho component riêng và luôn kết thúc stream vô hạn bằng cancellation hoặc giới hạn phần tử. Với RSocket, virtual time phù hợp để kiểm tra chính sách reactive ở application layer; timer nội bộ của TCP, WebSocket và Netty vẫn cần integration test riêng. Kết hợp hai loại kiểm thử giúp xác minh cả logic thời gian lẫn hành vi transport thực tế.
