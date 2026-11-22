# Kiểm tra retry, timeout và các phần tử bị loại bỏ trong Project Reactor

## 1. Mục tiêu

Trong chương trình reactive, kết quả đúng không chỉ là giá trị cuối cùng của `Mono` hoặc `Flux`. Một luồng có thể thất bại, được subscribe lại, chờ backoff, hết thời gian, cancel upstream, bỏ qua các phần tử khi lọc, hoặc nhận tín hiệu đến muộn từ một publisher lỗi. Những hành vi này rất khó kiểm thử đáng tin cậy nếu dựa vào `Thread.sleep()` và log thủ công.

Project Reactor cung cấp thư viện `reactor-test`, đặc biệt là `StepVerifier`, `VirtualTimeScheduler`, `TestPublisher` và `PublisherProbe`. Bài học giải quyết chính xác chủ đề **kiểm tra retry, timeout và các phần tử bị loại bỏ**:

1. Kiểm thử `retry`/`retryWhen`: số lần subscribe, loại lỗi được retry, hết số lượt, fixed delay và exponential backoff.
2. Kiểm thử `timeout`: thời gian trước deadline, loại lỗi `TimeoutException`, fallback và cancellation.
3. Kiểm thử **discard**: phần tử bị loại hợp lệ trong xử lý `filter`, `skip` hoặc dọn hàng đợi khi cancel.
4. Kiểm thử **drop**: signal không còn hợp lệ sau terminal/cancel, `onNextDropped` và `onErrorDropped`; phân biệt với discard.
5. Kết hợp retry với timeout đúng thứ tự, tránh retry storm hoặc bỏ sót cancellation.
6. Viết test chạy được bằng Java 17+, JUnit 5, Reactor 3.7.x (được quản lý qua Spring Boot 3.5.x) và Gradle.

Đối với code minh họa riêng lẻ, bài sẽ nói rõ đó là snippet hay là một phần của dự án chạy độc lập. Mục tiêu là test **nhanh, xác định, có assertions về toàn bộ lifecycle**, không chỉ kiểm tra rằng sau một khoảng ngủ thì dữ liệu cuối cùng có vẻ đúng.

## 2. Nhắc lại onNext, onComplete, onError và cancel

Reactive Streams định nghĩa các loại tín hiệu chính:

- `onSubscribe(Subscription)`: downstream nhận subscription và có thể yêu cầu dữ liệu.
- `onNext(T)`: emit một phần tử, tuân thủ demand đã được request.
- `onComplete()`: kết thúc thành công.
- `onError(Throwable)`: kết thúc lỗi.
- `cancel()`: downstream không cần nhận thêm dữ liệu; publisher phải ngừng hoặc dọn dẹp phù hợp.

Một sequence nhận tối đa **một terminal signal**: hoặc onComplete, hoặc onError. Sau terminal, onNext/onError bổ sung là không hợp lệ. Với cancellation, một số signal có thể đang trên đường từ nguồn bất đồng bộ; operator phải xử lý chúng theo contract phù hợp.

`Mono<T>` có tối đa một phần tử; `Flux<T>` có thể phát 0..N phần tử. Trong test, đừng nhầm giữa ba trạng thái:

| Trạng thái | Ý nghĩa | Assertion thường dùng |
| --- | --- | --- |
| Hoàn tất thành công | onComplete sau các onNext hợp lệ | `expectNext(...).verifyComplete()` |
| Thất bại | onError và không còn onComplete | `expectError(...).verify()` |
| Bị hủy | Subscriber gọi cancel, upstream không nhất thiết có terminal signal | `thenCancel().verify()` và `doFinally(CANCEL)` |

Nếu một item bị `filter` loại, đó không phải là `onError`. Nếu một response bị `timeout`, upstream thường bị cancel. Nếu `retry` được kích hoạt, đó là **subscribe lại source**, không phải tiếp tục execution cũ tại điểm hỏng.

## 3. Cấu trúc StepVerifier

Ví dụ đơn giản:

```java
Flux<String> words = Flux.just("A", "B");

StepVerifier.create(words)
        .expectSubscription()
        .expectNext("A")
        .expectNext("B")
        .expectComplete()
        .verify();
```

Hoặc dùng phím tắt:

```java
StepVerifier.create(Flux.just(1, 2, 3))
        .expectNext(1, 2, 3)
        .verifyComplete();
```

Các phương thức quan trọng:

| API | Ý nghĩa |
| --- | --- |
| `StepVerifier.create(publisher)` | Tạo một kịch bản cho source |
| `expectSubscription()` | Xác nhận đã có onSubscribe |
| `expectNext(value...)` | Kiểm tra onNext theo thứ tự |
| `assertNext(consumer)` | Kiểm tra chi tiết phần tử |
| `expectNextCount(n)` | Kiểm tra số phần tử mà không so từng giá trị |
| `expectComplete()` | Kỳ vọng onComplete |
| `expectError(Class)` | Kỳ vọng onError thuộc kiểu lỗi |
| `expectErrorMatches(predicate)` | Xác nhận kiểu/nội dung lỗi |
| `expectErrorSatisfies(consumer)` | Assertion sâu với JUnit/AssertJ |
| `thenRequest(n)` | Tăng demand sau khi subscribe |
| `thenCancel()` | Hủy subscription khi đến bước đó |
| `thenAwait(duration)` | Chờ hoặc tăng đồng hồ ảo |
| `expectNoEvent(duration)` | Xác nhận không có signal trong khoảng đó |
| `verify()` | Chạy kịch bản và kiểm tra |
| `verifyThenAssertThat()` | Chạy kịch bản rồi kiểm tra dropped/discarded và state |

**Bắt buộc có verify:** khai báo `expectNext` nhưng không gọi `verify()`, `verifyComplete()` hay `verifyThenAssertThat()` thì test chưa thực sự subscribe publisher.

`verify()` mặc định có thể chờ vô thời hạn. Nếu dùng test trên nguồn thật hay async không chắc chắn, ưu tiên `verify(Duration.ofSeconds(5))` hoặc `verifyThenAssertThat(Duration.ofSeconds(5))`; không dựa vào timeout mặc định của CI.

Với `expectNoEvent`, subscription cũng được xem là một event. Vì vậy sử dụng:

```java
StepVerifier.withVirtualTime(() -> Mono.delay(Duration.ofDays(1)))
        .expectSubscription()
        .expectNoEvent(Duration.ofDays(1))
        .expectNext(0L)
        .verifyComplete();
```

Không đặt `expectNoEvent` ngay bước đầu nếu chưa kiểm tra subscription, vì onSubscribe có thể khiến test thất bại.

## 4. Retry là subscribe lại, không phải chạy tiếp source cũ

`retry(n)` và `retryWhen(Retry...)` được dùng khi source phát `onError`. Cần hiểu chính xác số lượt:

- Lần đầu subscribe: attempt ban đầu.
- `Retry.max(2)`: tối đa **hai lần retry**, tức là tối đa **ba subscription** tổng cộng.
- `Retry.fixedDelay(2, delay)`: cũng tối đa hai lần retry, với delay ở giữa.
- `Retry.backoff(2, minBackoff)`: tối đa hai lần retry với backoff tăng dần, có jitter mặc định.
- `retry` chỉ kích hoạt khi có onError, không kích hoạt khi onComplete hoặc `Mono.empty()`.

### 4.1. Test retry thành công lần ba

```java
AtomicInteger calls = new AtomicInteger();

Mono<String> unstable = Mono.defer(() -> {
    int attempt = calls.incrementAndGet();
    return attempt < 3
            ? Mono.error(new IllegalStateException("temporary-" + attempt))
            : Mono.just("OK");
});

StepVerifier.create(unstable.retryWhen(Retry.max(2)))
        .expectNext("OK")
        .verifyComplete();

assertEquals(3, calls.get());
```

Lý do dùng `Mono.defer`: source tạo kết quả mới **mỗi lần subscription**. Nếu tạo `Mono.error(...)` duy nhất với lỗi cố định và tăng counter bên ngoài một lần, retry không thay đổi điều kiện thành công.

Test kiểm tra **cả dữ liệu** và **số lần subscribe**, thay vì chỉ kiểm tra `OK`. Nếu operator bị cấu hình retry quá nhiều nhưng cuối cùng vẫn thành công, assertion output đơn thuần có thể không bắt được lỗi đó.

### 4.2. Retry hết lượt

```java
AtomicInteger calls = new AtomicInteger();

Mono<String> alwaysFail = Mono.defer(() -> {
    calls.incrementAndGet();
    return Mono.error(new IllegalStateException("down"));
});

StepVerifier.create(alwaysFail.retryWhen(Retry.max(2)))
        .expectErrorSatisfies(error -> {
            assertTrue(Exceptions.isRetryExhausted(error));
            assertInstanceOf(IllegalStateException.class, error.getCause());
        })
        .verify();

assertEquals(3, calls.get());
```

Với `retryWhen(Retry.max(...))`, khi exhaust Reactor mặc định tạo **retry-exhausted exception** bọc `cause` là lỗi cuối cùng. Đừng test rằng exception cuối cùng vẫn chính xác là `IllegalStateException`. Nếu ứng dụng cấu hình `onRetryExhaustedThrow` thì lỗi có thể khác.

### 4.3. Chỉ retry lỗi transient

```java
AtomicInteger calls = new AtomicInteger();

Mono<String> badRequest = Mono.defer(() -> {
    calls.incrementAndGet();
    return Mono.error(new IllegalArgumentException("invalid input"));
});

StepVerifier.create(
        badRequest.retryWhen(Retry.max(5)
                .filter(error -> error instanceof TimeoutException)))
        .expectError(IllegalArgumentException.class)
        .verify();

assertEquals(1, calls.get());
```

Chỉ lỗi TimeoutException được retry theo predicate. `IllegalArgumentException` đi qua ngay. Với HTTP/WebClient, phân loại theo `WebClientResponseException`, status code hoặc network exception thay vì retry mọi 4xx/5xx một cách mù quáng.

### 4.4. retry khác repeat

`retry` phản ứng với `onError`; `repeat` phản ứng với `onComplete`. Sai lầm dùng repeat để “retry request bị lỗi” sẽ khiến test có logic khác dự kiến.

`retryWhen` và `repeatWhen` cũng khác nhau về trigger. Khi viết test, luôn ghi rõ khi nào source trả onComplete/onError và số subscription mong đợi.

## 5. Kiểm thử retry có delay với virtual time

### 5.1. Vì sao không dùng Thread.sleep?

Test như sau là anti-pattern:

```java
Mono<String> result = remoteCall.retryWhen(
        Retry.fixedDelay(2, Duration.ofSeconds(5)));

Thread.sleep(10_000);
assertEquals("OK", result.block());
```

Vấn đề:
- Test chạy chậm và phụ thuộc scheduler/load của CI.
- Sleep xảy ra **trước khi subscribe**, nên không thực sự chờ các retry của result.
- `block()` tạo subscription riêng; có thể mất context và không mô tả đầy đủ signal.
- Không kiểm tra có retry sớm hoặc quá số lần hay không.

`StepVerifier.withVirtualTime` thay scheduler mặc định phù hợp bằng VirtualTimeScheduler và tiến thời gian ảo qua các bước.

### 5.2. Test fixed delay chính xác

```java
AtomicInteger subscriptions = new AtomicInteger();

StepVerifier.withVirtualTime(() ->
        Mono.defer(() -> {
            int attempt = subscriptions.incrementAndGet();
            return attempt < 3
                    ? Mono.<String>error(new IllegalStateException("temporary"))
                    : Mono.just("OK");
        })
        .retryWhen(Retry.fixedDelay(2, Duration.ofSeconds(5))))
        .expectSubscription()
        .expectNoEvent(Duration.ofSeconds(4))
        .thenAwait(Duration.ofSeconds(1))
        .expectNoEvent(Duration.ofSeconds(4))
        .thenAwait(Duration.ofSeconds(1))
        .expectNext("OK")
        .verifyComplete();

assertEquals(3, subscriptions.get());
```

Timeline:

```text
t = 0s   attempt 1 -> onError
t = 5s   attempt 2 -> onError
t = 10s  attempt 3 -> onNext("OK"), onComplete
```

Không cần chờ 10 giây thật. `expectNoEvent(4s)` còn khẳng định kết quả không xuất hiện trước thời điểm cho phép.

### 5.3. Tạo publisher ở bên trong lambda

Đúng:

```java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofHours(2))
                .map(n -> "done"))
        .expectSubscription()
        .thenAwait(Duration.ofHours(2))
        .expectNext("done")
        .verifyComplete();
```

Có rủi ro:

```java
Mono<String> predefined = Mono.delay(Duration.ofHours(2))
        .map(n -> "done");

StepVerifier.withVirtualTime(() -> predefined)
        .expectSubscription()
        .thenAwait(Duration.ofHours(2))
        .expectNext("done")
        .verifyComplete();
```

Trong cách thứ hai, operator có thể đã chọn Scheduler trước lúc virtual scheduler được cài. Hãy tạo toàn bộ pipeline timed/retry bên trong Supplier, không chỉ trả publisher đã tạo sẵn.

Nếu code truyền scheduler riêng bằng `Scheduler` mà `withVirtualTime` không điều khiển, cần inject `VirtualTimeScheduler` vào component dưới test hoặc cấu hình scheduler lookup tường minh. Đừng mặc định mọi thứ trong JVM đều dùng đồng hồ ảo.

## 6. Retry backoff, jitter và RetrySignal

### 6.1. Fixed delay versus exponential backoff

- `Retry.fixedDelay(2, Duration.ofSeconds(2))`: delay ~2s giữa các lần retry.
- `Retry.backoff(2, Duration.ofSeconds(2))`: chiến lược exponential; default multiplier thường là 2, jitter mặc định 0.5.
- `Retry.backoff(...).jitter(0d)`: bỏ randomness, phù hợp để assert thời điểm chính xác trong test.
- `maxBackoff(...)`: giới hạn độ trễ tối đa.
- `filter(...)`: chỉ retry lỗi phù hợp.
- `doBeforeRetry(...)` / `doAfterRetry(...)`: quan sát retry metadata.

Ví dụ:

```java
AtomicInteger calls = new AtomicInteger();

StepVerifier.withVirtualTime(() -> {
    Mono<String> source = Mono.defer(() -> {
        int n = calls.incrementAndGet();
        return n < 3
                ? Mono.<String>error(new IllegalStateException("offline"))
                : Mono.just("OK");
    });

    return source.retryWhen(
            Retry.backoff(2, Duration.ofSeconds(2))
                    .jitter(0d));
})
.expectSubscription()
.thenAwait(Duration.ofSeconds(6))
.expectNext("OK")
.verifyComplete();

assertEquals(3, calls.get());
```

Nếu multiplier = 2 và không jitter, hai delay là 2s và 4s, nên lần thành công ở t=6s. Để kiểm tra “không có kết quả sớm”, có thể thêm `expectNoEvent(Duration.ofMillis(1999))` và bước tiến đồng hồ phù hợp trước khi expectNext.

### 6.2. Quan sát RetrySignal

`Retry.RetrySignal` có:
- `totalRetries()`: số retry trước đó, bắt đầu từ 0 ở lần đầu thất bại.
- `totalRetriesInARow()`: số lỗi liên tiếp trong một burst, reset sau khi source đã onNext thành công.
- `failure()`: Throwable của attempt vừa hỏng.
- `retryContextView()`: context riêng của retry nếu có.

Ví dụ ghi lại retry index:

```java
List<Long> indices = new CopyOnWriteArrayList<>();

Retry strategy = Retry.max(2)
        .doBeforeRetry(signal ->
                indices.add(signal.totalRetries()));

Mono<String> result = failingThenSuccess.retryWhen(strategy);
```

Snippet phụ thuộc `failingThenSuccess` do ứng dụng cấp. Khi source lỗi hai lần rồi thành công, indices mong đợi là `[0, 1]`. Không kiểm tra log timestamp thay cho signal metadata.

### 6.3. transientErrors(true)

Trên `Flux` dài hạn, có thể phát vài `onNext` giữa các burst lỗi rồi subscribe lại. `transientErrors(true)` dùng totalRetriesInARow thay cho totalRetries, nhờ đó cho phép mỗi burst lỗi liên tiếp có giới hạn riêng.

Điều này **không** có nghĩa một stream đã thất bại có thể “tiếp tục trên cùng subscription”; retry vẫn subscribe lại. Nếu source không có cursor/checkpoint, dữ liệu cũ có thể phát lại và gây duplicate side effects. Viết test kiểm tra cả thứ tự/các phần tử trùng khi retry một `Flux` đã emit một số giá trị trước khi error.

## 7. Kiểm thử timeout

`timeout(Duration)` giám sát khoảng thời gian chờ signal theo hợp đồng operator. Khi không có signal đúng hạn, nó chuyển downstream sang `onError(TimeoutException)` và cancel subscription nguồn.

### 7.1. Mono quá chậm

```java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofSeconds(10))
                .thenReturn("late")
                .timeout(Duration.ofSeconds(3)))
        .expectSubscription()
        .expectNoEvent(Duration.ofSeconds(2))
        .thenAwait(Duration.ofSeconds(1))
        .expectError(TimeoutException.class)
        .verify();
```

Giải thích:
- Source hẹn phát sau 10s.
- Timeout cho phép tối đa 3s.
- t=2s chưa có signal.
- t=3s timeout xảy ra và test kỳ vọng TimeoutException.
- Không cần dùng sleep 10s.

### 7.2. Response đến trước deadline

```java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofSeconds(2))
                .thenReturn("fast")
                .timeout(Duration.ofSeconds(3)))
        .expectSubscription()
        .expectNoEvent(Duration.ofSeconds(1))
        .thenAwait(Duration.ofSeconds(1))
        .expectNext("fast")
        .verifyComplete();
```

Test xác minh cả hai phía ranh giới: slow fail, fast pass. Tránh chỉ test timeout “quá chậm” mà bỏ qua case “đúng hạn”.

### 7.3. Timeout với fallback

`timeout(timeout, fallbackPublisher)` sẽ chuyển sang publisher dự phòng khi nguồn chính chậm:

```java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofSeconds(10))
                .thenReturn("remote")
                .timeout(
                        Duration.ofSeconds(3),
                        Mono.just("cache")))
        .expectSubscription()
        .expectNoEvent(Duration.ofSeconds(2))
        .thenAwait(Duration.ofSeconds(1))
        .expectNext("cache")
        .verifyComplete();
```

Đây là fallback có chủ đích. **Kết quả cache không có nghĩa remote call đã thành công**. Kiểm tra tracing/metrics riêng để biết timeout xảy ra.

### 7.4. Timeout thường cancel upstream

```java
AtomicInteger cancelled = new AtomicInteger();

StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofSeconds(10))
                .doOnCancel(cancelled::incrementAndGet)
                .timeout(Duration.ofSeconds(3)))
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(3))
        .expectError(TimeoutException.class)
        .verify();

assertEquals(1, cancelled.get());
```

Khi timeout, upstream có thể đang giữ socket, timer, queue hay subscription khác. Không chỉ assert lỗi; xác nhận cancellation khi resource/lifecycle quan trọng.

### 7.5. Timeout trên Flux và idle gap

Timeout trên `Flux` giám sát khoảng thời gian tới **phần tử tiếp theo**; nếu một phần tử tới kịp, timer được điều chỉnh cho khoảng tiếp theo. Khác với overall deadline cho toàn bộ giao dịch.

Ví dụ:

```text
t=0  subscribe
t=1  onNext A
t=2  onNext B
t=7  onNext C   <-- quá muộn nếu timeout 3s từ B
```

Một `Flux` stream có thể hoạt động hàng giờ nếu mỗi event tới trước idle deadline. Nếu cần hạn toàn bộ stream, phải dùng toán tử deadline hoặc thiết kế riêng, không mặc định `timeout(Duration)` là tổng thời gian của request.

### 7.6. Timeout của StepVerifier khác timeout của publisher

| Loại timeout | Công cụ | Ý nghĩa |
| --- | --- | --- |
| Business/operator timeout | `source.timeout(Duration.ofSeconds(3))` | Pipeline phát TimeoutException và thường cancel upstream |
| Test verification timeout | `verifier.verify(Duration.ofSeconds(5))` | JUnit test fail vì verifier không kết thúc đúng kỳ vọng; không khẳng định publisher đã dùng timeout operator |
| Default verifier timeout | `StepVerifier.setDefaultTimeout(...)` | Áp dụng toàn cục cho StepVerifier mới tạo; cần reset sau test nếu dùng |

Đừng nhầm việc `verify(Duration)` fail sau 5 giây với việc production `Mono.timeout(5s)` được cấu hình đúng.

## 8. Kết hợp retry và timeout: thứ tự operator làm đổi ngữ nghĩa

Đây là một lỗi phổ biến trong client reactive.

### 8.1. Timeout cho mỗi attempt, rồi retry

```java
return callRemote()
        .timeout(Duration.ofSeconds(2))
        .retryWhen(Retry.fixedDelay(
                1, Duration.ofSeconds(1)));
```

Nếu attempt đầu không trả trong 2s:
1. Timeout attempt đầu, cancel upstream.
2. Chờ fixed delay 1s.
3. Subscribe lại callRemote().
4. Attempt thứ hai có thêm tối đa 2s trước khi timeout.

Tổng thời gian có thể khoảng 5s nếu cả hai attempt đều timeout, chưa tính overhead. Kết thúc bằng retry-exhausted exception bọc TimeoutException, trừ khi đã cấu hình generator khác.

### 8.2. Retry trước, timeout cho toàn operation

```java
return callRemote()
        .retryWhen(Retry.fixedDelay(
                1, Duration.ofSeconds(1)))
        .timeout(Duration.ofSeconds(3));
```

Đây là 3s cho **toàn bộ pipeline bao gồm retry và backoff**. Khi deadline tới, timeout bên ngoài cancel chuỗi bên trong, kể cả đang chờ backoff.

Không tuyên bố thứ tự nào luôn đúng: chọn theo SLA business. Thường nên có:
- Timeout từng attempt để một attempt không chiếm vô hạn.
- Giới hạn retry attempts.
- Overall deadline để tổng thời gian không vượt ngân sách.
- Jitter/backoff trong production để giảm retry storm.
- Retry filter chỉ cho lỗi transient và operation idempotent hoặc có idempotency key.

### 8.3. Test mỗi-attempt timeout và số lần thử

```java
AtomicInteger attempts = new AtomicInteger();

StepVerifier.withVirtualTime(() ->
        Mono.defer(() -> {
            attempts.incrementAndGet();
            return Mono.delay(Duration.ofSeconds(9))
                    .thenReturn("late");
        })
        .timeout(Duration.ofSeconds(2))
        .retryWhen(Retry.fixedDelay(
                1, Duration.ofSeconds(1))))
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(5))
        .expectErrorSatisfies(error -> {
            assertTrue(Exceptions.isRetryExhausted(error));
            assertInstanceOf(TimeoutException.class, error.getCause());
        })
        .verify();

assertEquals(2, attempts.get());
```

Timeline dự kiến: attempt #1 t=0..2; backoff t=2..3; attempt #2 t=3..5; hết số retry tại t=5.

### 8.4. Kiểm tra thứ tự bằng assert timestamp ảo

Nếu cần assert từng thời điểm rõ hơn, có thể kiểm tra count tại các mốc thông qua `then(() -> ...)` trong StepVerifier:

```java
AtomicInteger calls = new AtomicInteger();

StepVerifier.withVirtualTime(() ->
        Mono.defer(() -> {
            calls.incrementAndGet();
            return Mono.<String>error(new IllegalStateException());
        })
        .retryWhen(Retry.fixedDelay(1, Duration.ofSeconds(5))))
        .expectSubscription()
        .then(() -> assertEquals(1, calls.get()))
        .thenAwait(Duration.ofSeconds(4))
        .then(() -> assertEquals(1, calls.get()))
        .thenAwait(Duration.ofSeconds(1))
        .expectErrorSatisfies(Exceptions::isRetryExhausted)
        .verify();
```

**Chú ý về snippet:** `expectErrorSatisfies` nhận Consumer<Throwable>, còn `Exceptions::isRetryExhausted` trả boolean nên không phù hợp làm Consumer. Cách đúng là dùng `expectErrorMatches(Exceptions::isRetryExhausted)`, hoặc lambda có `assertTrue(...)`. Ví dụ compilable:

```java
AtomicInteger calls = new AtomicInteger();

StepVerifier.withVirtualTime(() ->
        Mono.defer(() -> {
            calls.incrementAndGet();
            return Mono.<String>error(new IllegalStateException("down"));
        })
        .retryWhen(Retry.fixedDelay(1, Duration.ofSeconds(5))))
        .expectSubscription()
        .then(() -> assertEquals(1, calls.get()))
        .thenAwait(Duration.ofSeconds(4))
        .then(() -> assertEquals(1, calls.get()))
        .thenAwait(Duration.ofSeconds(1))
        .expectErrorMatches(Exceptions::isRetryExhausted)
        .verify();

assertEquals(2, calls.get());
```

Phương pháp này tốt để bắt lỗi retry quá sớm hoặc không retry đúng lúc.

## 9. Ba khái niệm dễ nhầm: emitted, discarded và dropped

### 9.1. Emitted (onNext đến downstream)

Một phần tử hợp lệ đã đi tới subscriber. `expectNext` có thể quan sát được.

### 9.2. Discarded (loại trong quá trình xử lý hợp lệ)

Một operator như `filter` có thể nhận item nhưng **không chuyển tiếp** do predicate false. Đây là behavior bình thường, cần cleanup trong một số trường hợp:

```java
Flux<Integer> evens = Flux.range(1, 6)
        .filter(value -> value % 2 == 0);
```

Output xuống subscriber là `2, 4, 6`; các số `1, 3, 5` bị **discarded**. Chúng không phải onError, không phải dropped do sai protocol.

Các ví dụ khác:
- `skip(n)` bỏ các item đầu.
- Một số operator có queue/prefetch có thể bỏ item đang giữ khi cancel hoặc error.
- Batching có khoảng trống, filterWhen/flatMap hoặc buffer strategy có thể discard theo điều kiện và hỗ trợ của operator.

**Không được đoán rằng mọi operator đều hỗ trợ discard hook như nhau**. Đọc Javadoc phần Discard Support cho operator đang dùng.

### 9.3. Dropped (signal không hợp lệ hoặc không còn người nhận)

Một publisher tạo onNext sau onComplete/onError hoặc tiếp tục emit sau cancellation có thể khiến signal bị “dropped”. Reactor có `Hooks.onNextDropped` và `Hooks.onErrorDropped` cho những tình huống này.

Đây không phải cách xử lý bình thường của `filter`. Một test về loại phần tử trong filter phải kỳ vọng **discard** chứ không kỳ vọng onNextDropped.

### 9.4. Bảng phân biệt

| Tình huống | Kỳ vọng quan sát | Nên test |
| --- | --- | --- |
| filter loại 1,3,5 | 2,4,6 xuống downstream | hasDiscardedExactly(1,3,5) |
| skip(2) bỏ 2 item đầu | Các item sau xuống downstream | hasDiscarded(...) nếu operator hỗ trợ |
| take(n) cancel source | n item, downstream complete | thenCancel/doFinally(CANCEL) ở scope phù hợp |
| Publisher lỗi vẫn onNext sau terminal | Signal muộn không hợp lệ | hasDropped(...), tùy hook/source |
| Publisher lỗi vẫn onError thêm lần nữa | Extra terminal error | hasDroppedError... |
| Tự cancel khi timeout | Upstream nhận cancel | doOnCancel/doFinally(CANCEL) |
| Retry khi source phát onError | Tạo subscription mới | AtomicInteger + StepVerifier |

## 10. Test discard bằng verifyThenAssertThat

`StepVerifier.verifyThenAssertThat()` chạy scenario rồi trả đối tượng `StepVerifier.Assertions` cho phép assert discard/drop qua hooks do test quản lý.

### 10.1. filter() và hasDiscardedExactly

```java
StepVerifier.create(
        Flux.range(1, 6)
                .filter(value -> value % 2 == 0))
        .expectNext(2, 4, 6)
        .expectComplete()
        .verifyThenAssertThat()
        .hasDiscardedExactly(1, 3, 5)
        .hasNotDroppedElements();
```

**Ý nghĩa:**
- Downstream nhận đúng ba số chẵn.
- Có đúng ba item discarded `1,3,5`, không thêm item.
- Không có signal dropped bất thường.
- `hasDiscardedExactly` so tập các phần tử được quan sát, **không nên dùng để chứng minh thứ tự discard**; nếu thứ tự quan trọng, dùng local doOnDiscard và một collection được kiểm soát.

### 10.2. Một số assertion hậu kiểm

| Assertion | Ý nghĩa |
| --- | --- |
| `hasDiscardedElements()` | Có ít nhất một phần tử bị discard |
| `hasDiscarded(values...)` | Có ít nhất các giá trị yêu cầu, không bắt buộc chỉ có chúng |
| `hasDiscardedExactly(values...)` | Không có phần tử discard nào khác ngoài các giá trị được liệt kê |
| `hasNotDiscardedElements()` | Không có discard |
| `hasDroppedElements()` | Có ít nhất một onNext bị dropped |
| `hasDropped(values...)` | Có ít nhất các dropped onNext yêu cầu |
| `hasDroppedExactly(values...)` | Đúng các dropped onNext yêu cầu |
| `hasNotDroppedElements()` | Không có dropped onNext |
| `hasDroppedErrors()` | Có ít nhất một onError bị dropped |
| `hasDroppedErrorOfType(type)` | Kiểm tra dropped error theo kiểu |
| `hasNotDroppedErrors()` | Không có dropped onError |
| `tookLessThan(duration)` | Thời gian *thực* chạy verifier, không phải virtual elapsed time |

Dùng `verifyThenAssertThat(Duration.ofSeconds(5))` nếu có nguy cơ scenario treo. `hasNotDroppedElements` và `hasNotDiscardedElements` khác nhau; không đánh đồng chúng.

### 10.3. doOnDiscard để dọn tài nguyên

Một phần tử bị loại có thể là `DataBuffer`, pooled `ByteBuf` hoặc object chứa tài nguyên. Nếu operator hỗ trợ discard, sử dụng local hook để dọn nó.

```java
List<Integer> discarded = new CopyOnWriteArrayList<>();

Flux<Integer> evens = Flux.range(1, 6)
        .filter(n -> n % 2 == 0)
        .doOnDiscard(Integer.class, discarded::add);

StepVerifier.create(evens)
        .expectNext(2, 4, 6)
        .verifyComplete();

assertEquals(List.of(1, 3, 5), discarded);
```

`doOnDiscard(Class, Consumer)` là local hook áp dụng cho các operator **upstream** của nó; có tính cộng dồn nếu nhiều hooks được khai báo. Callback cleanup nên **idempotent và an toàn** khi bị gọi trên object phù hợp. Nó không nên block event-loop hoặc phát lỗi làm che lỗi chính.

### 10.4. Khi bị cancel, chưa chắc có discard

Ví dụ:

```java
AtomicInteger cancelled = new AtomicInteger();

Flux<Integer> source = Flux.range(1, 10)
        .doOnCancel(cancelled::incrementAndGet);

StepVerifier.create(source.take(2))
        .expectNext(1, 2)
        .verifyComplete();

assertEquals(1, cancelled.get());
```

Ở đây take(2) cancel upstream sau khi đủ hai item. Không thể tự kết luận các item 3..10 **đã được tạo và bị discard**: `Flux.range` hỗ trợ backpressure, source có thể ngừng phát trước khi tạo chúng. Test cancellation không đồng nghĩa test discarded objects.

Nếu có operator buffer/prefetch, discard có thể xảy ra khi cancel, nhưng số item phụ thuộc request, fusion, scheduler và timing. Để test deterministic, dùng TestPublisher/VirtualTimeScheduler hoặc nguồn điều khiển được, thay vì assert số item bỏ đi theo suy đoán.

## 11. Test dropped signals bằng TestPublisher

`TestPublisher` là một test source do `reactor-test` cung cấp; có thể điều khiển chính xác khi nào emit next, complete và error.

### 11.1. Source chuẩn

```java
TestPublisher<String> source = TestPublisher.create();

StepVerifier.create(source.flux())
        .then(() -> source.next("A"))
        .expectNext("A")
        .then(source::complete)
        .verifyComplete();
```

`then(...)` thực hiện hành động trong khi verifier đang subscribe, nên test không phụ thuộc Thread.sleep.

### 11.2. Source cố ý vi phạm protocol

Để kiểm tra dropped signals, cần **một publisher lỗi** phát tín hiệu sau terminal. Đừng dùng một Flux.just/filter bình thường rồi hy vọng có dropped item.

```java
TestPublisher<Integer> source =
        TestPublisher.createNoncompliant(
                TestPublisher.Violation.CLEANUP_ON_TERMINATE);

StepVerifier.create(source.flux().filter(value -> true))
        .then(() -> {
            source.next(1);
            source.complete();
            source.next(99);
        })
        .expectNext(1)
        .expectComplete()
        .verifyThenAssertThat()
        .hasDropped(99);
```

`CLEANUP_ON_TERMINATE` chỉ sử dụng trong test mô phỏng publisher non-compliant. Khi một operator nhận onNext sau terminal, nó có thể chuyển signal muộn tới onNextDropped hook để StepVerifier thống kê.

Một số implementation có cơ chế từ chối ngay tại publisher, bỏ qua hoặc report khác nhau khi vi phạm spec. Nếu test này không phù hợp do nhánh/source hiện hành, hãy kiểm tra implementation và đặt operator có path onNextDropped tường minh; không sửa test thành `hasDiscarded(99)` vì ý nghĩa hoàn toàn khác.

### 11.3. Dropped error

Với publisher phát onError nhiều lần, onError muộn có thể đi tới `Hooks.onErrorDropped`. StepVerifier Assertions cung cấp `hasDroppedErrorOfType`, `hasDroppedErrorWithMessage` và `hasDroppedErrors`.

Snippet minh họa cách kiểm tra:

```java
TestPublisher<Integer> source =
        TestPublisher.createNoncompliant(
                TestPublisher.Violation.CLEANUP_ON_TERMINATE);

StepVerifier.create(source.flux())
        .then(() -> {
            source.error(new IllegalStateException("first"));
            source.error(new IllegalArgumentException("late"));
        })
        .expectErrorMessage("first")
        .verifyThenAssertThat()
        .hasDroppedErrorOfType(IllegalArgumentException.class);
```

Nếu một operator đã chặn extra error ở phía upstream, hook có thể được kích hoạt ở nơi khác. Trong production, lỗi sau terminal thường cho thấy nguồn vi phạm contract hoặc race, không phải là một “lỗi phụ để retry”.

### 11.4. Tránh global Hooks trong unit test song song

`Hooks.onNextDropped(...)` và `Hooks.onErrorDropped(...)` là global hooks trong runtime. Tự cài global hook trong một JUnit test và quên reset có thể ảnh hưởng test khác, nhất là khi chạy song song.

Ưu tiên:
- `StepVerifier.verifyThenAssertThat()` cho assertions về hooks mà verifier quản lý.
- Local `doOnDiscard(...)` cho cleanup theo một pipeline.
- Nếu phải cài global hook, reset trong afterEach/try-finally và tránh test song song cùng can thiệp global state.

## 12. Timeout có gây discard hoặc dropped không?

`timeout` sẽ cancel upstream khi deadline quá hạn. Nhưng điều đó không tự đồng nghĩa **tất cả phần tử chưa tới downstream đều bị dropped**.

Xét ba tình huống:

1. `Mono.delay(10s).timeout(3s)`: timer upstream bị cancel trước khi phát. Thường không có item để discard; test nên assert TimeoutException và `doOnCancel`.
2. Một operator có queue chứa item đã prefetch: khi cancel, item đang giữ có thể bị discard nếu operator hỗ trợ hook.
3. Một publisher không tuân thủ cancellation vẫn cố emit sau khi timeout: có thể xảy ra onNextDropped hoặc signal bị loại theo cleanup path. Muốn kiểm tra, dùng controlled TestPublisher và mô tả rõ violation.

Đừng viết assertion `hasDroppedElements()` trong mọi timeout test. Nếu nguồn là `Mono.delay` đã cancel đúng, không có signal muộn nào được emit để drop.

### 12.1. Dọn buffer và ByteBuf

Đối với network pooled buffers, `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` hoặc cơ chế cleanup tương đương có thể cần thiết, tùy ownership của buffer và operator; không release bừa nếu buffer vẫn đang được dùng ở nơi khác.

Test resource cleanup nên đo release/refCnt của đúng resource hoặc spy cleanup callback, không dựa trên log “dropped”. Trách nhiệm release khác nhau giữa Reactor Netty, DataBuffer/ByteBuf và body extractors.

## 13. Đơn vị test: nguồn, scheduler, side effects và scope

Khi test retry, nếu source có state mutable, hãy xác định rõ state thuộc về **test instance**, **publisher instance** hay **mỗi subscription**.

### 13.1. Mono.defer và số lần subscribe

```java
AtomicInteger subscriptions = new AtomicInteger();

Mono<String> call = Mono.defer(() -> {
    int n = subscriptions.incrementAndGet();
    return n == 1
            ? Mono.error(new IllegalStateException("fail once"))
            : Mono.just("OK");
});
```

Mỗi lần retry làm lambda chạy lại. Nếu dùng `Mono.just(sideEffect())`, side effect xảy ra **khi lắp pipeline**, không phải mỗi subscription.

### 13.2. doOnSubscribe và doFinally

```java
AtomicInteger subscribed = new AtomicInteger();
AtomicInteger cancelled = new AtomicInteger();

Mono<String> call = Mono.never()
        .doOnSubscribe(s -> subscribed.incrementAndGet())
        .doFinally(signal -> {
            if (signal == SignalType.CANCEL) {
                cancelled.incrementAndGet();
            }
        });
```

Với timeout, có thể assert một subscription và một cancellation. `doFinally` nhận `SignalType.ON_COMPLETE`, `ON_ERROR` hoặc `CANCEL`; callback chạy sau khi termination/cancel được xử lý, nên khi cần assert timing của doFinally phải thiết kế đồng bộ phù hợp.

### 13.3. StepVerifierOptions và backpressure

```java
StepVerifier.create(
        Flux.range(1, 3),
        StepVerifierOptions.create().initialRequest(0))
        .expectSubscription()
        .thenRequest(2)
        .expectNext(1, 2)
        .thenRequest(1)
        .expectNext(3)
        .verifyComplete();
```

Test này cho thấy `thenRequest` điều khiển demand. Nó không cần retry/timeout nhưng hữu ích khi muốn kiểm tra cancellation/discard trong operator có prefetch/buffering.

### 13.4. Nguồn hot và race

Virtual time không làm biến mất race giữa publisher nóng, network callbacks, timer và cancellation. Để test edge cases:
- Dùng `TestPublisher` cho source điều khiển được.
- Dùng `Sinks` và latch trong integration test nếu có concurrency thật.
- Dùng `PublisherProbe` nếu cần xác minh fallback publisher thực sự được subscribe.
- Đừng dùng thứ tự `Thread.sleep` làm bằng chứng cho một race condition.

## 14. Test cả đường đi fallback với PublisherProbe

Khi `onErrorResume` hoặc `switchIfEmpty` trả publisher thay thế, assertion vào giá trị kết quả chưa chứng minh fallback path đã được dùng. `PublisherProbe` có thể giúp khẳng định source được subscribe/request/cancel.

Ví dụ:

```java
PublisherProbe<String> fallback =
        PublisherProbe.of(Mono.just("cached"));

Mono<String> source = Mono.<String>error(
        new IllegalStateException("remote"))
        .onErrorResume(error -> fallback.mono());

StepVerifier.create(source)
        .expectNext("cached")
        .verifyComplete();

fallback.assertWasSubscribed();
fallback.assertWasRequested();
```

Có thể dùng tương tự với `timeout(duration, fallback.mono())` và virtual time. Đây là cách để chứng minh fallback path được dùng; không chỉ kiểm tra string trùng.

## 15. Project Gradle hoàn chỉnh: Java 17 + Reactor + JUnit 5

Đây là dự án nhỏ có thể chạy bằng Java 17+ và Gradle. Dùng Spring Boot 3.5 BOM để quản lý dependency Reactor và JUnit tương thích, nhưng phần pipeline/test là Reactor thuần nên **không cần khởi động Spring context**. Điều này giúp test nhanh và ít biến số.

### 15.1. Cấu trúc

```text
reactor-retry-timeout-test/
  settings.gradle
  build.gradle
  src/main/java/demo/reactor/ReactivePipelines.java
  src/test/java/demo/reactor/ReactivePipelinesTest.java
```

### 15.2. settings.gradle

```groovy
rootProject.name = 'reactor-retry-timeout-test'
```

### 15.3. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
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
    implementation 'io.projectreactor:reactor-core'

    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'org.junit.jupiter:junit-jupiter'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Ở đây chỉ dùng Spring Boot plugin để quản lý dependency; không gọi `bootRun` vì project không có ứng dụng `@SpringBootApplication`. Nếu cần tối giản hơn, thay bằng Reactor BOM + JUnit BOM và Gradle Java plugin, miễn version tương thích.

### 15.4. ReactivePipelines.java

Tệp `src/main/java/demo/reactor/ReactivePipelines.java`:

```java
package demo.reactor;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

public final class ReactivePipelines {

    private ReactivePipelines() {
    }

    public static Mono<String> eventuallyOk(AtomicInteger attempts) {
        return Mono.defer(() -> {
            int n = attempts.incrementAndGet();
            if (n < 3) {
                return Mono.error(
                        new IllegalStateException("temporary-" + n));
            }
            return Mono.just("OK");
        });
    }

    public static Mono<String> fixedDelayRetry(
            AtomicInteger attempts) {
        return eventuallyOk(attempts)
                .retryWhen(Retry.fixedDelay(
                        2, Duration.ofSeconds(5)));
    }

    public static Mono<String> backoffRetry(
            AtomicInteger attempts) {
        return eventuallyOk(attempts)
                .retryWhen(
                        Retry.backoff(2, Duration.ofSeconds(2))
                                .jitter(0d));
    }

    public static Mono<String> timeoutTooSlow() {
        return Mono.delay(Duration.ofSeconds(10))
                .thenReturn("slow")
                .timeout(Duration.ofSeconds(3));
    }

    public static Mono<String> timeoutWithFallback() {
        return Mono.delay(Duration.ofSeconds(10))
                .thenReturn("remote")
                .timeout(
                        Duration.ofSeconds(3),
                        Mono.just("cached"));
    }

    public static Flux<Integer> evenNumbers() {
        return Flux.range(1, 6)
                .filter(n -> n % 2 == 0);
    }

    public static Mono<String> twoTimedOutAttempts(
            AtomicInteger attempts) {
        return Mono.defer(() -> {
            attempts.incrementAndGet();
            return Mono.delay(Duration.ofSeconds(9))
                    .thenReturn("late");
        })
        .timeout(Duration.ofSeconds(2))
        .retryWhen(Retry.fixedDelay(
                1, Duration.ofSeconds(1)));
    }
}
```

Để virtual time hoạt động, gọi các factory method này **bên trong** Supplier của `StepVerifier.withVirtualTime`. Nếu gọi factory trước rồi chỉ trả lại publisher có scheduler đã capture từ trước, đồng hồ ảo có thể không điều khiển được các timer.

### 15.5. ReactivePipelinesTest.java

Tệp `src/test/java/demo/reactor/ReactivePipelinesTest.java`:

```java
package demo.reactor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.Exceptions;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.test.publisher.TestPublisher;
import reactor.util.retry.Retry;

class ReactivePipelinesTest {

    @Test
    void retrySucceedsOnThirdSubscription() {
        AtomicInteger calls = new AtomicInteger();

        StepVerifier.create(
                ReactivePipelines.eventuallyOk(calls)
                        .retryWhen(Retry.max(2)))
                .expectNext("OK")
                .verifyComplete();

        assertEquals(3, calls.get());
    }

    @Test
    void retryExhaustionWrapsLastError() {
        AtomicInteger calls = new AtomicInteger();

        Mono<String> alwaysFail = Mono.defer(() -> {
            calls.incrementAndGet();
            return Mono.error(
                    new IllegalStateException("down"));
        });

        StepVerifier.create(
                alwaysFail.retryWhen(Retry.max(2)))
                .expectErrorSatisfies(error -> {
                    assertTrue(Exceptions.isRetryExhausted(error));
                    assertInstanceOf(
                            IllegalStateException.class,
                            error.getCause());
                })
                .verify();

        assertEquals(3, calls.get());
    }

    @Test
    void retryDoesNotRetryNonTransientError() {
        AtomicInteger calls = new AtomicInteger();

        Mono<String> invalid = Mono.defer(() -> {
            calls.incrementAndGet();
            return Mono.error(
                    new IllegalArgumentException("invalid"));
        });

        StepVerifier.create(invalid.retryWhen(
                Retry.max(5)
                        .filter(TimeoutException.class::isInstance)))
                .expectError(IllegalArgumentException.class)
                .verify();

        assertEquals(1, calls.get());
    }

    @Test
    void fixedDelayUsesVirtualTime() {
        AtomicInteger calls = new AtomicInteger();

        StepVerifier.withVirtualTime(
                () -> ReactivePipelines.fixedDelayRetry(calls))
                .expectSubscription()
                .expectNoEvent(Duration.ofSeconds(4))
                .thenAwait(Duration.ofSeconds(1))
                .expectNoEvent(Duration.ofSeconds(4))
                .thenAwait(Duration.ofSeconds(1))
                .expectNext("OK")
                .verifyComplete();

        assertEquals(3, calls.get());
    }

    @Test
    void exponentialBackoffWithoutJitterUsesVirtualTime() {
        AtomicInteger calls = new AtomicInteger();

        StepVerifier.withVirtualTime(
                () -> ReactivePipelines.backoffRetry(calls))
                .expectSubscription()
                .thenAwait(Duration.ofSeconds(6))
                .expectNext("OK")
                .verifyComplete();

        assertEquals(3, calls.get());
    }

    @Test
    void slowMonoTimesOut() {
        StepVerifier.withVirtualTime(
                ReactivePipelines::timeoutTooSlow)
                .expectSubscription()
                .expectNoEvent(Duration.ofSeconds(2))
                .thenAwait(Duration.ofSeconds(1))
                .expectError(TimeoutException.class)
                .verify();
    }

    @Test
    void timeoutSwitchesToFallback() {
        StepVerifier.withVirtualTime(
                ReactivePipelines::timeoutWithFallback)
                .expectSubscription()
                .expectNoEvent(Duration.ofSeconds(2))
                .thenAwait(Duration.ofSeconds(1))
                .expectNext("cached")
                .verifyComplete();
    }

    @Test
    void timeoutCancelsUpstream() {
        AtomicInteger cancels = new AtomicInteger();

        StepVerifier.withVirtualTime(() ->
                Mono.delay(Duration.ofSeconds(10))
                        .doOnCancel(cancels::incrementAndGet)
                        .timeout(Duration.ofSeconds(3)))
                .expectSubscription()
                .thenAwait(Duration.ofSeconds(3))
                .expectError(TimeoutException.class)
                .verify();

        assertEquals(1, cancels.get());
    }

    @Test
    void retryAfterEachTimeoutHasTwoSubscriptions() {
        AtomicInteger calls = new AtomicInteger();

        StepVerifier.withVirtualTime(() ->
                ReactivePipelines.twoTimedOutAttempts(calls))
                .expectSubscription()
                .thenAwait(Duration.ofSeconds(5))
                .expectErrorSatisfies(error -> {
                    assertTrue(Exceptions.isRetryExhausted(error));
                    assertInstanceOf(
                            TimeoutException.class,
                            error.getCause());
                })
                .verify();

        assertEquals(2, calls.get());
    }

    @Test
    void filterDiscardsButDoesNotDrop() {
        StepVerifier.create(
                ReactivePipelines.evenNumbers())
                .expectNext(2, 4, 6)
                .expectComplete()
                .verifyThenAssertThat()
                .hasDiscardedExactly(1, 3, 5)
                .hasNotDroppedElements();
    }

    @Test
    void localDiscardHookSeesFilteredValues() {
        List<Integer> discarded = new CopyOnWriteArrayList<>();

        Flux<Integer> evens = ReactivePipelines.evenNumbers()
                .doOnDiscard(Integer.class, discarded::add);

        StepVerifier.create(evens)
                .expectNext(2, 4, 6)
                .verifyComplete();

        assertEquals(List.of(1, 3, 5), discarded);
    }

    @Test
    void malformedPublisherCanDropLateOnNext() {
        TestPublisher<Integer> source =
                TestPublisher.createNoncompliant(
                        TestPublisher.Violation.CLEANUP_ON_TERMINATE);

        StepVerifier.create(source.flux().filter(value -> true))
                .then(() -> {
                    source.next(1);
                    source.complete();
                    source.next(99);
                })
                .expectNext(1)
                .expectComplete()
                .verifyThenAssertThat()
                .hasDropped(99);
    }

    @Test
    void demandCanBeControlledWithoutSleeping() {
        StepVerifier.create(
                Flux.range(1, 3),
                StepVerifierOptions.create().initialRequest(0))
                .expectSubscription()
                .thenRequest(2)
                .expectNext(1, 2)
                .thenRequest(1)
                .expectNext(3)
                .verifyComplete();
    }
}
```

Bộ test có đủ:
- Retry thành công, exhaust và filter lỗi.
- Fixed delay, backoff với jitter=0.
- Timeout error, timeout fallback và cancel upstream.
- Timeout per attempt kết hợp retry.
- Discard bình thường, local cleanup callback.
- Dropped signal từ publisher cố ý non-compliant.
- Demand riêng không dùng sleep.

Với test malformed source, kết quả dropped signal phụ thuộc đường đi operator và behavior của implementation. Nếu version/nhánh Reactor đổi cơ chế xử lý signal vi phạm spec, cần test theo contract operator hiện hành. Các test còn lại không phụ thuộc một publisher cố ý vi phạm.

### 15.6. Chạy kiểm thử

Nếu dự án đã có Gradle wrapper:

```bash
./gradlew test
```

Nếu chưa có wrapper nhưng máy đã cài Gradle:

```bash
gradle test
```

JUnit báo thành công khi tất cả test pass. Không khẳng định stdout cụ thể của Gradle vì version Gradle, cache, daemon và IDE có thể làm log khác nhau. Cách xác nhận là exit code 0 và test report `build/reports/tests/test/index.html`.

**Lưu ý:** các ví dụ Java có `assertEquals`/`assertTrue` nằm trong test class hoàn chỉnh và cần JUnit dependency; snippet riêng ở các mục trước sử dụng cùng imports.

## 16. Khi kiểm thử WebClient/Spring WebFlux thật

Reactor operator test dùng Mono/Flux có thể không cần khởi động Spring Boot. Nhưng khi có WebClient/HTTP server, cần phân biệt hai lớp:

1. **Unit test reactive operators:** mô phỏng source bằng Mono.defer, TestPublisher hoặc PublisherProbe, dùng StepVerifier/virtual time.
2. **Integration test network:** dùng MockWebServer, WireMock, Reactor Netty test server hoặc WebTestClient để xác nhận status mapping, connection timeout, response timeout, retry filter, cancellation của HTTP call và resource cleanup.

Đừng giả định `withVirtualTime` tự điều khiển mọi timeout trong WebClient. TCP connect timeout, socket read timeout, TLS handshake timeout và client connector timers có thể chạy trên Netty event-loop hoặc scheduler khác, không phụ thuộc VirtualTimeScheduler của Reactor.

### 16.1. Test retry HTTP theo status

Khi dùng WebClient, `retrieve()` thường ánh xạ 4xx/5xx thành WebClientResponseException nếu không tùy biến onStatus.

Ví dụ snippet minh họa:

```java
Mono<Product> response = webClient.get()
        .uri("/products/42")
        .retrieve()
        .bodyToMono(Product.class)
        .retryWhen(Retry.backoff(2, Duration.ofMillis(200))
                .filter(error -> error instanceof WebClientResponseException ex
                        && ex.getStatusCode().is5xxServerError()));
```

Đây là **snippet phụ thuộc Product và webClient của ứng dụng**. Lưu ý:
- 429 Too Many Requests cũng là lỗi transient có thể có Retry-After, nhưng cần policy riêng.
- Không retry 4xx do validation sai mà không có căn cứ.
- Retry POST có side effect có thể tạo trùng lặp; cân nhắc idempotency key.
- Không để retry và timeout làm tổng thời gian vượt SLA.

### 16.2. Test response timeout của connector

Reactor Netty HttpClient có `responseTimeout(Duration)` ở tầng connector. Nó không giống hoàn toàn với `Mono.timeout(Duration)` ở tầng pipeline Reactor. Khi test network behavior, dùng server giả lập phản hồi chậm và kiểm tra loại exception/connection cancellation thực tế; đừng khẳng định nó luôn ném `java.util.concurrent.TimeoutException` như operator timeout của Mono.

### 16.3. Mock source thay network khi chỉ test operator

Thay vì khởi động server để xác minh retry count, bọc phần fetch thành function trả Mono và inject source giả:

```java
Function<String, Mono<String>> fetch = id -> Mono.defer(() ->
        Mono.error(new IllegalStateException("down")));

Mono<String> result = fetch.apply("42")
        .retryWhen(Retry.max(2));
```

Khi test retry count, kết hợp AtomicInteger trong Mono.defer. Khi test HTTP status mapping thực, dùng integration test riêng. Một test không nên cố kiểm tra cả time-based operator, TLS, routing, retry, connection pooling và JSON mapping trong cùng một kịch bản nếu có thể tách chúng.

## 17. Troubleshooting: khi StepVerifier test treo hoặc flaky

| Triệu chứng | Nguyên nhân thường gặp | Khắc phục |
| --- | --- | --- |
| Test không kết thúc | Quên verify/thiếu terminal expectation, nguồn vô hạn | thenCancel hoặc expectError/expectComplete |
| withVirtualTime vẫn chạy chậm | Publisher tạo ngoài Supplier, scheduler được cung cấp riêng | Tạo timed operators trong Supplier hoặc inject scheduler |
| expectNoEvent thất bại ngay | Subscription cũng được tính là event | expectSubscription trước |
| verify() chờ mãi | Mặc định không có verify timeout | verify(Duration), verifyThenAssertThat(Duration) |
| Retry count lệch 1 | Nhầm retries với total subscriptions | max(2) = 1 initial + 2 retries |
| Test retry không thay đổi kết quả | Side effect nằm ngoài Mono.defer | Đưa logic subscription vào defer |
| Retry exhaustion test nhầm exception | Retry.max/backoff bọc nguyên nhân lỗi | Exceptions.isRetryExhausted và getCause |
| backoff test flaky | Jitter mặc định làm thời điểm ngẫu nhiên | jitter(0d) trong unit test |
| timeout test thất bại dù chờ | Dùng sleep trước subscribe hoặc sai boundary | Virtual time và expectNoEvent/thenAwait |
| doOnCancel không chạy | Đang chờ source bình thường hoàn tất, không cancel | Tạo timeout/thenCancel, xác nhận subscription |
| hasDropped cho filter thất bại | filter tạo discarded, không phải dropped | hasDiscardedExactly |
| hasDiscardedExactly dư giá trị | Có operator khác cũng discard hoặc buffer cleanup | Đọc Javadoc/operator chain và hook |
| Không nhận dropped trong test malformed | Source chặn signal trước khi đến hook, hoặc đường operator khác | Dùng TestPublisher non-compliant và kiểm tra hook path |
| Global Hooks ảnh hưởng test khác | Chưa reset hook/test chạy song song | Ưu tiên StepVerifier, doOnDiscard local |
| Cancellation test assert cả 3..N discarded | Source chưa tạo 3..N | Assert cancel; chỉ assert discarded khi item đã thực sự tồn tại |
| Timeout+retry thất bại đúng deadline | Operator ordering khác mong đợi | Vẽ timeline mỗi attempt vs tổng |
| onErrorResume che lỗi gốc | Fallback quá rộng | Filter lỗi, log metadata không lộ dữ liệu |
| Retry HTTP gây side effect lặp | Retry POST không idempotent | Idempotency key, method/policy phù hợp |
| Flux retry phát lại item cũ | Retry subscribe lại cold source | Thiết kế cursor/dedup, test duplicates |

## 18. Checklist test cho pipeline lỗi/timeout

Trước khi merge code, kiểm tra:

1. Source có onError hay onComplete? Retry/repeat đúng trigger không?
2. Retry count là số retry hay tổng subscriptions?
3. Source test có dùng Mono.defer/Flux.defer để tái tạo theo subscription?
4. Có kiểm tra cả output, error cause và số attempt?
5. Retry filter có tránh permanent/validation errors?
6. Có timeout từng attempt, overall deadline và giới hạn retry hợp lý?
7. Virtual time tạo scheduler-aware publisher bên trong Supplier?
8. Backoff jitter được cố định hoặc tắt trong deterministic unit test?
9. expectNoEvent đứng sau expectSubscription?
10. Đã kiểm tra cancellation upstream khi timeout?
11. Fallback thực sự được subscribe? Có thể dùng PublisherProbe?
12. Discard do filter/skip có được assert bằng hasDiscardedExactly hay local doOnDiscard?
13. Có phân biệt discard bình thường và dropped signal vi phạm protocol?
14. Resource được cleanup đúng ownership khi discard/cancel?
15. Không cài global Hooks lâu dài làm ảnh hưởng test song song?
16. Không gọi block()/sleep() chỉ để test một timer có thể chạy ảo?
17. Có verify(Duration) nếu source có nguy cơ treo?
18. Test WebClient/network timeout bằng integration test riêng khi cần?
19. Không retry thao tác gây side effect nếu không có idempotency policy?
20. Test có kiểm tra behavior khi client chậm, cancel hoặc nguồn không tuân thủ spec?

## 19. Tài liệu tham khảo chính thức

- [Project Reactor – Testing](https://projectreactor.io/docs/core/release/reference/testing.html): StepVerifier, virtual time, verifyThenAssertThat, TestPublisher, PublisherProbe và cách tránh expectNoEvent đầu tiên.
- [reactor-test StepVerifier Javadoc](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): create, withVirtualTime, verify, verify(Duration), verifyThenAssertThat.
- [reactor-test StepVerifier.Assertions Javadoc](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.Assertions.html): hasDropped, hasDiscarded, hasDroppedErrors và post-verification assertions.
- [Project Reactor – Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): retry, retryWhen, transientErrors và operator error handling.
- [Project Reactor – RetrySpec Javadoc](https://projectreactor.io/docs/core/release/api/reactor/util/retry/RetrySpec.html): maxAttempts, filter, onRetryExhaustedThrow, doBeforeRetry.
- [Project Reactor – RetryBackoffSpec Javadoc](https://projectreactor.io/docs/core/release/api/reactor/util/retry/RetryBackoffSpec.html): backoff, jitter, maxBackoff, scheduler, transientErrors.
- [Project Reactor – doOnDiscard](https://projectreactor.io/docs/core/release/reference/advancedFeatures/cleanup.html): discard hooks, cleanup resource và khác biệt với dropped signals.
- [Spring Framework – WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): reactive HTTP client và error handling.

## 20. Ghi nhớ

**Retry:** `Retry.max(2)` tương ứng tối đa ba subscriptions, không phải hai. Test cả giá trị, loại lỗi, cause và số attempt.

**Timeout:** dùng `withVirtualTime` để kiểm thử deadline mà không ngủ thật; phân biệt timeout của operator và timeout của verifier. Kiểm tra upstream cancel khi timeout.

**Discard:** `filter`/`skip`/buffer cleanup loại item hợp lệ; dùng `doOnDiscard` và `verifyThenAssertThat().hasDiscardedExactly(...)` nếu operator hỗ trợ.

**Drop:** onNext/onError muộn sau terminal hoặc cancel là sự kiện bất thường; có thể kiểm tra bằng TestPublisher non-compliant và `hasDropped`/`hasDroppedError...`. Đừng đồng nhất drop với discard.

**Kết hợp:** thứ tự `timeout().retryWhen()` khác `retryWhen().timeout()`. Hãy vẽ timeline, tránh retry storm, kiểm tra idempotency và thực hiện integration tests riêng cho network-specific timeouts.
