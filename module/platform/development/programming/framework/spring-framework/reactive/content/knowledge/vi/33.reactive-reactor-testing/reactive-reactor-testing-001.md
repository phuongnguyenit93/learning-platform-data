# StepVerifier và kịch bản tín hiệu mong đợi trong Reactor

> **Module:** Spring Framework – reactive  
> **Chủ đề cha:** Kiểm thử Reactor  
> **Trọng tâm:** kiểm thử `Mono`/`Flux` bằng `reactor-test` với `StepVerifier`, mô tả chính xác trình tự tín hiệu Reactive Streams, xác nhận completion/error, backpressure, thời gian ảo, cancellation và Reactor Context. Bài có ví dụ độc lập, project Spring Boot 4.0.9/Java 17+, JUnit 5, `WebTestClient`, `TestPublisher` và `PublisherProbe`.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt các tín hiệu `onSubscribe`, `onNext`, `onError`, `onComplete` và hành động `request(n)`/`cancel()`.
2. Viết một kịch bản `StepVerifier` theo thứ tự kỳ vọng thay vì gọi `.block()` để tự kiểm tra giá trị.
3. Kiểm tra đúng số lượng, giá trị, thứ tự và terminal signal của `Mono`/`Flux`.
4. Kiểm tra lỗi theo kiểu, thông điệp và điều kiện nghiệp vụ; không nhầm một luồng rỗng với lỗi.
5. Viết assertion riêng trên từng phần tử qua `expectNextMatches`, `assertNext`, `consumeNextWith`.
6. Kiểm thử demand/backpressure với `initialRequest(0)` và `thenRequest(n)`.
7. Kiểm thử `delay`, `interval`, `timeout` và `retry` theo **virtual time** thay vì chờ thật nhiều giây/phút.
8. Kiểm tra propagation của Reactor `Context` bằng `StepVerifierOptions.withInitialContext(...)`.
9. Tạo upstream điều khiển bằng tay với `TestPublisher`, kiểm tra nhánh fallback bằng `PublisherProbe`.
10. Xác minh tín hiệu hủy và cleanup, tránh giả định `cancel` là `onComplete`.
11. Đặt timeout hữu hạn và thông điệp failure rõ để tránh test treo.
12. Kết hợp unit test của service với HTTP contract test bằng `WebTestClient` trong ứng dụng Spring WebFlux.

**Điểm quan trọng:** một bài test Reactor tốt mô tả **cả chuỗi tín hiệu**, không chỉ một giá trị cuối. `StepVerifier` là một subscriber dùng trong test; nó kích hoạt publisher khi `verify()` chạy và xác nhận những gì subscriber thực sự nhận được.

## 2. Trước khi test: hợp đồng tín hiệu của Reactive Streams

Một publisher được subscribe sẽ tạo một `Subscription`. Subscriber có thể yêu cầu dữ liệu (`request(n)`), nhận zero/many giá trị và cuối cùng nhận **một** tín hiệu kết thúc bình thường hoặc lỗi.

~~~text
Publisher                      Subscriber / StepVerifier
    |                                    |
    |-------- onSubscribe(s) ----------->|
    |<------- request(1) ----------------|
    |-------- onNext(A) ---------------->|
    |<------- request(2) ----------------|
    |-------- onNext(B) ---------------->|
    |-------- onNext(C) ---------------->|
    |-------- onComplete() ------------->|
    |                                    |
~~~

Khi lỗi:

~~~text
onSubscribe -> onNext(A) -> onError(IllegalStateException)
~~~

Khi rỗng:

~~~text
onSubscribe -> onComplete
~~~

Khi subscriber hủy:

~~~text
onSubscribe -> onNext(A) -> cancel
~~~

Các quy tắc cần nhớ:

- `Flux<T>` có thể phát `0..N` phần tử và một terminal signal.
- `Mono<T>` chỉ có thể phát tối đa **một** `onNext`, sau đó `onComplete`, hoặc kết thúc bằng `onError`.
- `onError` và `onComplete` **loại trừ nhau** trong một subscription; sau terminal không có thêm tín hiệu hợp lệ.
- `null` không phải giá trị `onNext` hợp lệ của Reactive Streams. `Mono.empty()` biểu thị vắng giá trị, không phải `Mono.just(null)`.
- `request(n)` điều tiết nhu cầu downstream, không phải tín hiệu `onNext` từ publisher.
- `cancel()` là hành động subscriber; **không** đợi publisher gửi `onComplete` sau khi đã cancel.
- Một cold publisher có thể chạy lại mỗi lần test verify/subscription; các operation có side-effect cần được kiểm soát.

`StepVerifier` mô tả các tín hiệu ở mức subscriber. Nó không tự chứng minh kết quả database đã commit hoặc HTTP đã đi qua một proxy production; những điều đó cần integration test riêng.

## 3. Dependency và bước đầu với StepVerifier

`StepVerifier`, `TestPublisher` và `PublisherProbe` thuộc artifact **`io.projectreactor:reactor-test`**, thường chỉ dùng ở `test` scope. Trong Spring Boot 4.0.x, có thể dùng dependency management của Boot để không khai báo version thủ công.

~~~xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

JUnit 5:

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class FirstStepVerifierTest {

    @Test
    void fluxEmitsTwoValuesThenCompletes() {
        Flux<String> source = Flux.just("A", "B");

        StepVerifier.create(source)
            .expectNext("A")
            .expectNext("B")
            .verifyComplete();
    }

    @Test
    void monoEmitsOneValueThenCompletes() {
        Mono<Integer> source = Mono.just(42);

        StepVerifier.create(source)
            .expectNext(42)
            .verifyComplete();
    }
}
~~~

`verifyComplete()` vừa đòi hỏi `onComplete` sau các bước đã viết, vừa kích hoạt verification. Tương đương kịch bản tường minh:

~~~java
StepVerifier.create(Flux.just("A", "B"))
    .expectNext("A", "B")
    .expectComplete()
    .verify();
~~~

**Bắt buộc có bước kích hoạt**: `verify()`, `verify(Duration)`, `verifyComplete()`, `verifyError()` hoặc `verifyThenAssertThat()`. Chỉ gọi `StepVerifier.create(...).expectNext(...)` mà không verify thì test chưa thực thi kịch bản.

## 4. Cấu trúc của một kịch bản

~~~java
StepVerifier.create(publisher)
    .expectSubscription()
    .expectNext(expectedValue)
    .expectNextMatches(value -> predicate(value))
    .expectComplete()
    .verify(Duration.ofSeconds(3));
~~~

Các phần:

1. `create` nhận một `Publisher` đã được tạo. `withVirtualTime` nhận supplier để tạo publisher **bên trong** môi trường virtual time.
2. `expectSubscription` xác nhận `onSubscribe`.
3. `expectNext`/`assertNext`/`expectNextMatches` kiểm tra giá trị hoặc điều kiện.
4. `expectComplete`, `expectError...` hoặc `thenCancel` kết thúc kịch bản.
5. `verify(Duration.ofSeconds(...))` thực sự chạy và chờ trong thời gian giới hạn.

### 4.1. Từ một giá trị tới terminal

| Publisher thực tế | Kịch bản mong đợi | Ý nghĩa |
| --- | --- | --- |
| `Mono.just(7)` | `expectNext(7) → verifyComplete()` | Một giá trị rồi kết thúc |
| `Mono.empty()` | `verifyComplete()` | Rỗng nhưng thành công |
| `Flux.just(1,2,3)` | `expectNext(1,2,3) → verifyComplete()` | Ba giá trị đúng thứ tự |
| `Mono.error(ex)` | `expectError(...) → verify()` | Kết thúc bằng lỗi |
| `Flux.concat(Flux.just(1), Mono.error(ex))` | `expectNext(1) → expectError(...) → verify()` | Có dữ liệu rồi lỗi |
| `Flux.never()` | `thenCancel() → verify()` | Không có terminal; test tự hủy |

Nếu `Flux.just(1,2,3)` được test bằng `expectNext(1,2).verifyComplete()`, bài test **phải fail**, vì phần tử `3` xuất hiện trước `onComplete`. Đây là kiểm tra tốt: tránh vô tình bỏ sót các giá trị ngoài mong đợi.

## 5. Các API kỳ vọng giá trị

### 5.1. `expectNext(T...)`

So sánh equality (thường là `equals`) với giá trị kỳ vọng và giữ thứ tự.

~~~java
StepVerifier.create(Flux.just("new", "validated", "saved"))
    .expectNext("new", "validated", "saved")
    .verifyComplete();
~~~

Với Java `record`, so sánh theo field rất thuận tiện:

~~~java
record OrderView(long id, String state) {}

StepVerifier.create(Mono.just(new OrderView(3L, "READY")))
    .expectNext(new OrderView(3L, "READY"))
    .verifyComplete();
~~~

### 5.2. `expectNextCount(long)`

Khi chỉ quan tâm số phần tử tiếp theo:

~~~java
StepVerifier.create(Flux.range(1, 100))
    .expectNext(1)
    .expectNextCount(98)
    .expectNext(100)
    .verifyComplete();
~~~

Operator chỉ đếm và tiêu thụ đúng số phần tử, **không kiểm tra nội dung** của 98 phần tử ở giữa. Chỉ dùng khi nội dung từng phần tử thật sự không quan trọng. Với nghiệp vụ cần kiểm tra thứ tự hoặc giá trị, dùng `expectNextSequence`, `expectNextMatches` hoặc assertions chi tiết.

### 5.3. `expectNextMatches(Predicate<T>)`

~~~java
StepVerifier.create(Mono.just(new OrderView(5L, "READY")))
    .expectNextMatches(order ->
        order.id() > 0 && "READY".equals(order.state()))
    .verifyComplete();
~~~

Predicate phải trả `true`; nếu trả `false`, scenario fail. Không ghi side-effect quan trọng trong predicate vì mục đích của nó là xác nhận điều kiện.

### 5.4. `assertNext` / `consumeNextWith`

`assertNext` cho phép dùng assertions JUnit hoặc AssertJ để đọc lỗi cụ thể hơn:

~~~java
StepVerifier.create(Mono.just(new OrderView(8L, "PAID")))
    .assertNext(order -> {
        org.junit.jupiter.api.Assertions.assertEquals(
            8L, order.id());
        org.junit.jupiter.api.Assertions.assertEquals(
            "PAID", order.state());
    })
    .verifyComplete();
~~~

`consumeNextWith` cũng nhận `Consumer<T>` để kiểm tra hoặc xử lý phần tử. Với `assertNext`, `AssertionError` do assertion bên trong tạo ra sẽ được truyền lại cho test. `as("...")` của StepVerifier không nhất thiết chèn mô tả vào exception tự ném trong assertion library.

### 5.5. `expectNextSequence(Iterable<T>)`

~~~java
StepVerifier.create(Flux.just("a", "b", "c"))
    .expectNextSequence(java.util.List.of("a", "b", "c"))
    .verifyComplete();
~~~

Hữu ích khi có một danh sách kỳ vọng được chuẩn bị trước. Cần bảo đảm danh sách có thứ tự ổn định; không test một SQL query không có `ORDER BY` bằng một thứ tự tưởng tượng.

## 6. Kiểm tra completion, empty và error

### 6.1. Hoàn tất bình thường

~~~java
StepVerifier.create(Flux.empty())
    .verifyComplete();
~~~

`Mono.empty()` không phát `null`; nó phát `onComplete` mà không có `onNext`. Với repository `findById`, empty thường có nghĩa không tìm thấy, không phải lỗi kết nối.

### 6.2. Lỗi kiểu cụ thể

~~~java
StepVerifier.create(
        Mono.error(new IllegalArgumentException("invalid id")))
    .expectError(IllegalArgumentException.class)
    .verify();
~~~

Tại terminal error, không viết tiếp `expectComplete` vì terminal chỉ có một loại. Nếu muốn kiểm tra message:

~~~java
StepVerifier.create(
        Mono.error(new IllegalStateException("database unavailable")))
    .expectErrorMessage("database unavailable")
    .verify();
~~~

`expectErrorMessage(...)` chủ yếu kiểm tra thông điệp; nếu cần cả type và message, dùng predicate:

~~~java
StepVerifier.create(
        Mono.<String>error(
            new IllegalStateException("database unavailable")))
    .expectErrorMatches(error ->
        error instanceof IllegalStateException
            && "database unavailable".equals(error.getMessage()))
    .verify();
~~~

### 6.3. Dữ liệu trước lỗi

~~~java
Flux<String> response = Flux.concat(
    Flux.just("partial"),
    Flux.error(new IllegalStateException("upstream failed"))
);

StepVerifier.create(response)
    .expectNext("partial")
    .expectErrorMatches(error ->
        error instanceof IllegalStateException
            && error.getMessage().contains("upstream failed"))
    .verify();
~~~

Hữu ích cho `Flux` đọc stream HTTP, message broker hoặc server events. Không thay bài test này bằng `collectList().block()` vì nó làm thay đổi cách nhìn về terminal signal và có thể làm mất thông tin phần dữ liệu đã đến trước lỗi.

### 6.4. Test fallback

~~~java
Mono<String> operation = Mono.<String>error(
        new java.util.concurrent.TimeoutException("slow"))
    .onErrorResume(
        java.util.concurrent.TimeoutException.class,
        ignored -> Mono.just("CACHED"));

StepVerifier.create(operation)
    .expectNext("CACHED")
    .verifyComplete();
~~~

Bài test phải xác minh fallback chỉ áp dụng cho lỗi được cho phép. Ví dụ 401/403 có thể phải giữ nguyên lỗi; không viết `onErrorResume(error -> Mono.empty())` cho mọi loại lỗi để test có vẻ xanh.

## 7. Giới hạn thời gian verify và tránh test treo

Một số shortcut như `verifyComplete()` hoặc `verifyError()` có thể chờ **không có timeout mặc định**. Nếu publisher là `Flux.never()` hoặc kịch bản demand không đủ, test có thể treo.

Ưu tiên:

~~~java
StepVerifier.create(Flux.just(1, 2))
    .expectNext(1, 2)
    .expectComplete()
    .verify(Duration.ofSeconds(3));
~~~

Hoặc cấu hình timeout mặc định cho toàn test suite ở nơi được quản lý tập trung:

~~~java
StepVerifier.setDefaultTimeout(Duration.ofSeconds(3));
~~~

`setDefaultTimeout` là **global setting** của StepVerifier. Không tùy tiện đổi nó ở một test rồi quên reset, vì các test khác có thể bị ảnh hưởng. Trong ví dụ project đầy đủ, phần lớn test dùng `verify(Duration)` để tự giới hạn.

### 7.1. `expectNoEvent(Duration)` khác `thenAwait(Duration)`

- `expectNoEvent(d)` khẳng định không nhận **bất kỳ event nào** trong khoảng thời gian `d`.
- `thenAwait(d)` chỉ đợi hoặc tiến đồng hồ ảo, **không** khẳng định không có event.
- `onSubscribe` cũng là một event: khi kiểm tra không có `onNext` ngay sau subscription, nên viết `.expectSubscription().expectNoEvent(...)`.
- Ở virtual time, cả hai có thể làm tiến đồng hồ ảo. Không dùng `expectNoEvent` như một timeout handler cho publisher vô hạn khi `thenCancel()` hoặc `expectTimeout(...)` phù hợp hơn.

Ví dụ kiểm tra chưa có dữ liệu trước một giây:

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofSeconds(1)))
    .expectSubscription()
    .expectNoEvent(Duration.ofSeconds(1))
    .expectNext(0L)
    .verifyComplete();
~~~

Nếu sự kiện đến sớm hơn 1 giây theo virtual scheduler, test sẽ fail. Test không phải ngủ thật một giây.

## 8. Kiểm thử backpressure: `initialRequest(0)` và `thenRequest(n)`

`StepVerifier.create(publisher)` mặc định có thể request một lượng rất lớn. Vì vậy test happy path **không chứng minh** publisher xử lý demand từng đợt đúng.

Muốn điều khiển:

~~~java
import reactor.test.StepVerifierOptions;

StepVerifier.create(
        Flux.range(1, 3),
        StepVerifierOptions.create()
            .initialRequest(0)
            .scenarioName("bounded-demand"))
    .expectSubscription()
    .thenRequest(1)
    .expectNext(1)
    .thenRequest(2)
    .expectNext(2, 3)
    .expectComplete()
    .verify(Duration.ofSeconds(3));
~~~

Ý nghĩa:
- Subscriber ban đầu request `0`, nên chưa có giá trị hợp lệ được phát.
- Sau `thenRequest(1)`, chỉ kỳ vọng `1`.
- Sau `thenRequest(2)`, kỳ vọng thêm `2`, `3`.
- Khi nguồn hết dữ liệu, kỳ vọng `onComplete`.

### 8.1. `checkUnderRequesting` và deadlock

`StepVerifierOptions` có tính năng kiểm tra kịch bản có đang đòi chờ nhiều phần tử hơn tổng demand đã cấp hay không. Mặc định việc kiểm tra under-requesting được bật. Nếu bạn thiết kế `initialRequest(0)` nhưng lại viết `expectNextCount(10)` trước khi `thenRequest(10)`, kịch bản có thể bị reject hoặc treo do thiếu demand.

Luôn thiết kế script theo thứ tự **request trước, nhận sau**. Đối với `Flux.create` hoặc publisher ngoài Reactor, test demand còn giúp phát hiện adapter phát quá nhanh, không tuân thủ flow control.

### 8.2. `thenCancel()`

~~~java
StepVerifier.create(
        Flux.interval(Duration.ofMillis(10)))
    .expectNext(0L)
    .thenCancel()
    .verify(Duration.ofSeconds(2));
~~~

Publisher vô hạn không bao giờ `onComplete`. Kịch bản này chủ động gửi cancel sau phần tử đầu. Nó **không** kiểm tra tài nguyên bên ngoài đã được giải phóng; muốn vậy, thêm `doOnCancel`, `doFinally` hoặc `PublisherProbe` và assert trạng thái.

Với test dựa trên thời gian thật, tải máy/CI có thể khiến delay timing thay đổi; dùng virtual time cho logic time-based nếu có thể.

## 9. Virtual time: kiểm thử delay, interval và timeout nhanh

`StepVerifier.withVirtualTime(Supplier<? extends Publisher<T>>)` cài `VirtualTimeScheduler` cho các operator thời gian được dựng trong supplier. Điều này cho phép mô phỏng giờ/ngày mà không chờ thực.

### 9.1. Cách đúng

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofHours(1)).take(2))
    .expectSubscription()
    .expectNoEvent(Duration.ofHours(1))
    .expectNext(0L)
    .thenAwait(Duration.ofHours(1))
    .expectNext(1L)
    .verifyComplete();
~~~

Điểm then chốt: `Flux.interval(...)` **được tạo bên trong lambda**. Một pipeline đã tạo ngoài lambda hoặc dùng custom scheduler không thuộc virtual scheduler có thể chờ thật hoặc chạy sai.

### 9.2. Ví dụ sai

~~~java
Flux<Long> createdTooEarly =
    Flux.interval(Duration.ofHours(1)).take(2);

// Không nên: nguồn đã tạo bên ngoài supplier.
StepVerifier.withVirtualTime(() -> createdTooEarly)
    .expectNextCount(2)
    .verifyComplete();
~~~

Tùy operator/scheduler và thời điểm khởi tạo, ví dụ này có thể không được virtual hóa đúng. Ngay cả khi một số operator hoạt động do scheduler được lấy lúc subscribe, mẫu **an toàn được tài liệu Reactor khuyến nghị** là khởi tạo pipeline bên trong supplier.

### 9.3. Test timeout với virtual time

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofSeconds(10))
            .timeout(Duration.ofSeconds(3)))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(3))
    .expectError(java.util.concurrent.TimeoutException.class)
    .verify();
~~~

`Mono.delay` chưa phát phần tử khi `timeout` 3 giây hết hạn. Kết quả là `onError(TimeoutException)` theo timeout operator của Reactor.

### 9.4. Test retry/backoff

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import reactor.util.retry.Retry;

AtomicInteger attempts = new AtomicInteger();

StepVerifier.withVirtualTime(() ->
        Mono.defer(() -> {
            int attempt = attempts.incrementAndGet();
            return attempt < 3
                ? Mono.<String>error(
                    new IllegalStateException("temporary"))
                : Mono.just("OK");
        })
        .retryWhen(
            Retry.fixedDelay(2, Duration.ofSeconds(5))))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(10))
    .expectNext("OK")
    .verifyComplete();

org.junit.jupiter.api.Assertions.assertEquals(3, attempts.get());
~~~

Đây là phép kiểm tra retry **có giới hạn**, retry hai lần sau lỗi ban đầu. Vì `Mono.defer` tạo hành vi mới cho mỗi subscription/retry, `attempts` tăng đúng ba lần. Không dùng retry vô hạn hoặc phụ thuộc vào thời gian thật trong unit test.

**Lưu ý:** virtual time không thay mọi scheduler chuyên dụng do thư viện tự tạo; virtual clock cũng không làm một JDBC hoặc HTTP sync call nhanh hơn. Với mã có phụ thuộc thời gian thật, phân tách clock/scheduler hoặc dùng integration test thích hợp.

## 10. Reactor Context trong kịch bản kiểm thử

Reactor `Context` gắn với subscriber, không phải một `ThreadLocal` tùy ý. Nó thường chứa thông tin như trace/correlation, security context và reactive transaction resource.

### 10.1. `withInitialContext`

~~~java
import reactor.util.context.Context;

Mono<String> currentTrace =
    Mono.deferContextual(ctx ->
        Mono.just(ctx.get("traceId")));

StepVerifier.create(
        currentTrace,
        StepVerifierOptions.create()
            .withInitialContext(Context.of("traceId", "trace-007")))
    .expectAccessibleContext()
    .contains("traceId", "trace-007")
    .then()
    .expectNext("trace-007")
    .verifyComplete();
~~~

`expectAccessibleContext` đi sang nhóm assertions cho Context; `.then()` quay về nhóm bước kiểm tra tín hiệu. Nếu nguồn bị tách qua một `subscribe()` thủ công bên trong service, Context của subscriber ngoài có thể không truyền sang subscription tách.

### 10.2. Kiểm thử Context trong pipeline

~~~java
Mono<String> greeting =
    Mono.deferContextual(ctx ->
        Mono.just("Hello " + ctx.get("user")))
        .contextWrite(ctx -> ctx.put("user", "Mai"));

StepVerifier.create(greeting)
    .expectNext("Hello Mai")
    .verifyComplete();
~~~

Test nên kiểm tra **hành vi** do Context tạo ra, không chỉ tên thread. Không đưa JWT, access token hoặc PII vào nội dung failure report của test nếu chúng có thể bị lộ qua CI logs.

## 11. TestPublisher: chủ động phát từng tín hiệu

`TestPublisher` cho phép test điều khiển thời điểm phát `onNext`, `onComplete`, `onError` mà không cần network hoặc message broker. Nó hữu ích để test operator nhận upstream dữ liệu bất định.

~~~java
import reactor.test.publisher.TestPublisher;

TestPublisher<String> upstream = TestPublisher.create();

Flux<String> upper = upstream.flux()
    .map(String::toUpperCase);

StepVerifier.create(upper)
    .then(() -> upstream.next("a", "b"))
    .expectNext("A", "B")
    .then(upstream::complete)
    .verifyComplete();
~~~

`TestPublisher.create()` thường là **hot** và chỉ chuyển tín hiệu tới subscriber đang có. Vì vậy cần phát dữ liệu bên trong `.then(...)` **sau khi StepVerifier đã subscribe**, thay vì gọi `upstream.next(...)` trước khi dựng verifier.

### 11.1. Kiểm thử lỗi do upstream phát

~~~java
TestPublisher<Integer> source = TestPublisher.create();

StepVerifier.create(source.flux())
    .then(() -> source.next(1))
    .expectNext(1)
    .then(() ->
        source.error(new IllegalStateException("gateway down")))
    .expectErrorMessage("gateway down")
    .verify();
~~~

### 11.2. Kiểm thử nguồn không tuân thủ Reactive Streams

Một số adapter nhận dữ liệu từ callback API có thể cố phát `onNext` khi demand = 0 hoặc phát `null`. `TestPublisher.createNoncompliant(Violation...)` cho phép cố tình tạo nguồn vi phạm để test operator xử lý thế nào.

~~~java
TestPublisher<Integer> misbehaving =
    TestPublisher.createNoncompliant(
        TestPublisher.Violation.REQUEST_OVERFLOW);
~~~

Chỉ dùng noncompliant publisher khi mục tiêu bài test là **kiểm tra resilience trước nguồn sai chuẩn**. Đừng dùng để thay thế nguồn đúng chuẩn trong happy path, vì nó có thể che lỗi backpressure thật.

### 11.3. TestPublisher không phải performance tool

`TestPublisher` thường không được thiết kế để nhiều thread đồng thời phát tín hiệu không có đồng bộ. Nếu muốn stress test, hãy dùng công cụ load/concurrency test có kiểm soát và API thread-safe thích hợp. Trong unit test, giữ kịch bản deterministic và emit ở các bước `.then(...)`.

## 12. PublisherProbe: xác minh nhánh được subscribe

Có khi cần biết một fallback Publisher có thực sự được sử dụng hay không, dù nó không phát dữ liệu. Với `Mono<Void>` hoặc `Mono.empty()`, chỉ kiểm tra terminal signal không cho biết nhánh nào đã chạy.

~~~java
import reactor.test.publisher.PublisherProbe;

PublisherProbe<String> fallback =
    PublisherProbe.of(Mono.just("from-cache"));

Mono<String> result = Mono.<String>empty()
    .switchIfEmpty(fallback.mono());

StepVerifier.create(result)
    .expectNext("from-cache")
    .verifyComplete();

fallback.assertWasSubscribed();
fallback.assertWasRequested();
fallback.assertWasNotCancelled();
~~~

Nếu input có dữ liệu, kiểm tra fallback **không** được subscribe:

~~~java
PublisherProbe<String> unused =
    PublisherProbe.of(Mono.just("fallback"));

Mono<String> result =
    Mono.just("primary").switchIfEmpty(unused.mono());

StepVerifier.create(result)
    .expectNext("primary")
    .verifyComplete();

unused.assertWasNotSubscribed();
~~~

### 12.1. Probe cho cancellation

~~~java
PublisherProbe<Long> probe =
    PublisherProbe.of(Flux.<Long>never());

StepVerifier.create(probe.flux())
    .expectSubscription()
    .thenCancel()
    .verify(Duration.ofSeconds(2));

probe.assertWasSubscribed();
probe.assertWasCancelled();
~~~

`PublisherProbe` không thay thế assertions về data values; nó đo subscription/request/cancel. Dùng cùng StepVerifier để kiểm tra cả **đường thực thi** và **chuỗi tín hiệu**.

## 13. Assertions sau khi verify

`verifyThenAssertThat()` chạy kịch bản, sau đó cho phép kiểm tra các tín hiệu bị **discard** hoặc **drop**.

### 13.1. `discard` khác `drop`

- **Discard:** operator có chủ đích loại bỏ giá trị khi xử lý, ví dụ `filter`, `take`, hoặc cleanup sau cancellation. Một số operator hỗ trợ discard hook cụ thể.
- **Drop:** tín hiệu tới quá muộn hoặc không còn hợp lệ so với trạng thái subscriber/operator, ví dụ dữ liệu phát sau terminal từ nguồn sai chuẩn.
- Không phải mọi operator hoặc thư viện ngoài Reactor đều tạo discard/drop theo cùng cách; đừng viết assertion mơ hồ chỉ dựa vào số phần tử cuối.

Ví dụ:

~~~java
StepVerifier.create(
        Flux.just(1, 2, 3)
            .filter(n -> n % 2 == 0))
    .expectNext(2)
    .expectComplete()
    .verifyThenAssertThat(Duration.ofSeconds(3))
    .hasDiscarded(1, 3);
~~~

`filter` loại 1 và 3 theo discard semantics của operator. Việc test chạy đúng không có nghĩa bộ nhớ/tài nguyên bên ngoài đã giải phóng; nếu dữ liệu là `DataBuffer` hoặc resource có ref-count, kiểm tra cleanup thực tế trong integration test.

### 13.2. Những assertion bổ sung

`StepVerifier.Assertions` còn hỗ trợ những nhóm như:
- `hasDropped(...)`, `hasNotDroppedElements()`.
- `hasDroppedErrors()` và các biến thể.
- `hasDiscardedElements()`, `hasDiscardedExactly(...)`.
- Kiểm tra operator error hooks khi có tình huống đặc biệt.

Tránh tạo dropped signal chỉ để test “có gì đó xảy ra”; hãy xác định rõ contract cần bảo vệ trước khi viết post-verification assertion.

## 14. Đặt tên scenario và mô tả bước lỗi

Một test có nhiều expectation dễ trở nên khó debug khi chỉ báo “expected next value”.

~~~java
StepVerifier.create(
        Flux.just("created", "validated", "saved"),
        StepVerifierOptions.create()
            .scenarioName("order-state-transition"))
    .expectNext("created").as("first state")
    .expectNext("validated").as("validation state")
    .expectNext("saved").as("persisted state")
    .verifyComplete();
~~~

`.as(...)` mô tả kỳ vọng ngay trước đó; `scenarioName(...)` gắn nhãn toàn scenario. Các nhãn này thường giúp error messages do StepVerifier tự tạo có nghĩa hơn; nếu một assertion JUnit bên trong `assertNext` tự ném `AssertionError`, nhãn StepVerifier không nhất thiết xuất hiện.

Không đặt tên test dạng `shouldWork()` chung chung. Nên mô tả hành vi và tình huống, ví dụ `emptyRepositoryUsesFallback()` hoặc `clientCancelStopsSource()`.

## 15. Chọn test layer đúng

| Mục tiêu | Công cụ | Cần gì? |
| --- | --- | --- |
| Toán tử Reactor thuần | `StepVerifier` | `reactor-test` |
| Mô phỏng upstream events/error | `TestPublisher` | `reactor-test` |
| Xác minh fallback được subscribe | `PublisherProbe` | `reactor-test` |
| Time-based operator | `withVirtualTime` | Scheduler không tạo quá sớm |
| WebFlux route, status, header, JSON, SSE | `WebTestClient` | Spring WebFlux test support |
| R2DBC, WebClient, message broker thật | Integration test + StepVerifier | Test database/server hoặc container thích hợp |
| Slow consumer/backpressure end-to-end | Load/integration test | Metrics, driver và server thật |

**Phân biệt rõ:** StepVerifier là công cụ kiểm tra **Reactive Streams signals**; WebTestClient là HTTP client để kiểm tra request/response. Có thể dùng chúng cùng nhau, ví dụ lấy response `Flux` từ WebTestClient rồi assert bằng StepVerifier.

## 16. Project Java 17+ chạy được: Spring Boot WebFlux

Ta tạo một workflow nhỏ: mỗi request phát ba trạng thái `received → validated → completed`. Một endpoint trả JSON summary, một endpoint phát SSE cho client. Unit test dùng StepVerifier; HTTP test dùng WebTestClient.

### 16.1. Cấu trúc project

~~~text
step-verifier-demo/
├── pom.xml
├── src/main/java/com/example/verifier/
│   ├── StepVerifierApplication.java
│   ├── WorkEvent.java
│   ├── WorkSummary.java
│   ├── WorkService.java
│   └── WorkController.java
└── src/test/java/com/example/verifier/
    ├── WorkServiceTest.java
    └── WorkControllerTest.java
~~~

### 16.2. `pom.xml`

Ví dụ dùng Spring Boot **4.0.9** (Java 17+) đã phát hành; `spring-boot-starter-webflux-test` và `reactor-test` ở test scope.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.9</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>step-verifier-demo</artifactId>
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
            <artifactId>spring-boot-starter-webflux-test</artifactId>
            <scope>test</scope>
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
~~~

Parent quản lý dependency versions, không pin Reactor version riêng để tránh lệch phiên bản với Spring Framework trong Boot.

### 16.3. `StepVerifierApplication.java`

~~~java
package com.example.verifier;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StepVerifierApplication {

    public static void main(String[] args) {
        SpringApplication.run(StepVerifierApplication.class, args);
    }
}
~~~

### 16.4. `WorkEvent.java`

~~~java
package com.example.verifier;

public record WorkEvent(long sequence, String id, String stage) {}
~~~

### 16.5. `WorkSummary.java`

~~~java
package com.example.verifier;

public record WorkSummary(
    String id,
    int eventCount,
    String lastStage
) {}
~~~

### 16.6. `WorkService.java`

~~~java
package com.example.verifier;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class WorkService {

    public Flux<WorkEvent> events(String id) {
        return Flux.defer(() -> {
            if (id == null || id.isBlank()) {
                return Flux.<WorkEvent>error(
                    new IllegalArgumentException(
                        "workflow id must not be blank"));
            }

            return Flux.just("received", "validated", "completed")
                .index()
                .map(pair -> new WorkEvent(
                    pair.getT1() + 1, id, pair.getT2()));
        });
    }

    public Mono<WorkSummary> summary(String id) {
        return events(id)
            .collectList()
            .map(list -> new WorkSummary(
                id,
                list.size(),
                list.get(list.size() - 1).stage()));
    }
}
~~~

`events` là cold `Flux`: mỗi subscription tạo sequence mới; validation được trì hoãn tới lúc subscribe. `summary` gom ba event để trả một JSON object. Vì trong demo số event cố định là ba, `collectList()` có giới hạn rõ; không dùng tùy tiện cho stream vô hạn.

### 16.7. `WorkController.java`

~~~java
package com.example.verifier;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/workflows")
public class WorkController {

    private final WorkService service;

    public WorkController(WorkService service) {
        this.service = service;
    }

    @GetMapping(
        value = "/{id}/summary",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<WorkSummary> summary(
            @PathVariable("id") String id) {
        return service.summary(id);
    }

    @GetMapping(
        value = "/{id}/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<WorkEvent>> events(
            @PathVariable("id") String id) {

        return service.events(id)
            .map(event ->
                ServerSentEvent.<WorkEvent>builder(event)
                    .event("stage")
                    .id(Long.toString(event.sequence()))
                    .build());
    }
}
~~~

Controller chỉ compose/return Publisher; WebFlux sở hữu subscription. SSE được dùng để browser có thể nhận từng trạng thái. Không cần gọi `.block()` hoặc `.subscribe()` trong controller.

### 16.8. `WorkServiceTest.java`

~~~java
package com.example.verifier;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.test.publisher.PublisherProbe;
import reactor.test.publisher.TestPublisher;
import reactor.util.context.Context;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class WorkServiceTest {

    private final WorkService service = new WorkService();

    @Test
    void eventsHaveExactValuesAndComplete() {
        StepVerifier.create(service.events("w-7"))
            .expectNext(new WorkEvent(1, "w-7", "received"))
            .expectNextMatches(event ->
                event.sequence() == 2
                    && event.stage().equals("validated"))
            .assertNext(event -> {
                assertEquals(3, event.sequence());
                assertEquals("completed", event.stage());
            })
            .expectComplete()
            .verify(Duration.ofSeconds(3));
    }

    @Test
    void summaryHasCorrectCardinality() {
        StepVerifier.create(service.summary("w-7"))
            .expectNext(new WorkSummary(
                "w-7", 3, "completed"))
            .expectComplete()
            .verify(Duration.ofSeconds(3));
    }

    @Test
    void blankIdProducesErrorNotEmptyCompletion() {
        StepVerifier.create(service.events(" "))
            .expectErrorMatches(error ->
                error instanceof IllegalArgumentException
                    && error.getMessage()
                        .equals("workflow id must not be blank"))
            .verify(Duration.ofSeconds(3));
    }

    @Test
    void sourceIsLazyUntilSubscribed() {
        AtomicInteger calls = new AtomicInteger();

        Mono<Integer> source = Mono.defer(
            () -> Mono.just(calls.incrementAndGet()));

        assertEquals(0, calls.get());

        StepVerifier.create(source)
            .expectNext(1)
            .expectComplete()
            .verify(Duration.ofSeconds(3));

        assertEquals(1, calls.get());
    }

    @Test
    void demandIsGrantedInTwoBatches() {
        StepVerifier.create(
                Flux.range(1, 3),
                StepVerifierOptions.create()
                    .initialRequest(0)
                    .scenarioName("request-1-then-2"))
            .expectSubscription()
            .thenRequest(1)
            .expectNext(1)
            .thenRequest(2)
            .expectNext(2, 3)
            .expectComplete()
            .verify(Duration.ofSeconds(3));
    }

    @Test
    void virtualTimeAvoidsRealOneHourWait() {
        StepVerifier.withVirtualTime(
                () -> Flux.interval(Duration.ofHours(1))
                    .take(2))
            .expectSubscription()
            .expectNoEvent(Duration.ofHours(1))
            .expectNext(0L)
            .thenAwait(Duration.ofHours(1))
            .expectNext(1L)
            .verifyComplete();
    }

    @Test
    void timeoutProducesErrorWithVirtualClock() {
        StepVerifier.withVirtualTime(() ->
                Mono.delay(Duration.ofSeconds(10))
                    .timeout(Duration.ofSeconds(3)))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(3))
            .expectError(TimeoutException.class)
            .verify();
    }

    @Test
    void contextIsVisibleToSubscriber() {
        Mono<String> source = Mono.deferContextual(
            ctx -> Mono.just(ctx.get("traceId")));

        StepVerifier.create(
                source,
                StepVerifierOptions.create().withInitialContext(
                    Context.of("traceId", "t-7")))
            .expectAccessibleContext()
            .contains("traceId", "t-7")
            .then()
            .expectNext("t-7")
            .verifyComplete();
    }

    @Test
    void testPublisherControlsUpstreamSignals() {
        TestPublisher<String> upstream = TestPublisher.create();

        StepVerifier.create(
                upstream.flux().map(String::toUpperCase))
            .then(() -> upstream.next("a", "b"))
            .expectNext("A", "B")
            .then(upstream::complete)
            .verifyComplete();
    }

    @Test
    void probeConfirmsFallbackWasSubscribed() {
        PublisherProbe<String> fallback =
            PublisherProbe.of(Mono.just("from-cache"));

        Mono<String> source = Mono.<String>empty()
            .switchIfEmpty(fallback.mono());

        StepVerifier.create(source)
            .expectNext("from-cache")
            .verifyComplete();

        fallback.assertWasSubscribed();
        fallback.assertWasRequested();
        fallback.assertWasNotCancelled();
    }

    @Test
    void probeConfirmsCancellation() {
        PublisherProbe<Long> probe =
            PublisherProbe.of(Flux.<Long>never());

        StepVerifier.create(probe.flux())
            .expectSubscription()
            .thenCancel()
            .verify(Duration.ofSeconds(3));

        probe.assertWasCancelled();
    }

    @Test
    void discardedValuesAreVisibleAfterVerify() {
        StepVerifier.create(
                Flux.just(1, 2, 3)
                    .filter(n -> n % 2 == 0))
            .expectNext(2)
            .expectComplete()
            .verifyThenAssertThat(Duration.ofSeconds(3))
            .hasDiscarded(1, 3);
    }
}
~~~

Test bao phủ cả terminal, demand, context, error, subscription path, virtual time và cancellation. `verify(Duration)` dùng ở các kịch bản có nguy cơ chờ; `withVirtualTime` kiểm soát đồng hồ ảo cho các operator thời gian.

### 16.9. `WorkControllerTest.java`

~~~java
package com.example.verifier;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class WorkControllerTest {

    private final WebTestClient client = WebTestClient
        .bindToController(new WorkController(new WorkService()))
        .build();

    @Test
    void summaryEndpointReturnsExpectedJson() {
        client.get()
            .uri("/api/workflows/w-7/summary")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("w-7")
            .jsonPath("$.eventCount").isEqualTo(3)
            .jsonPath("$.lastStage").isEqualTo("completed");
    }

    @Test
    void sseEventsHaveCorrectOrderAndCompletion() {
        FluxExchangeResult<ServerSentEvent<WorkEvent>> result =
            client.get()
                .uri("/api/workflows/w-7/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM)
                .returnResult(
                    new ParameterizedTypeReference<
                        ServerSentEvent<WorkEvent>>() {});

        StepVerifier.create(result.getResponseBody())
            .assertNext(event -> {
                assertEquals("stage", event.event());
                assertEquals("1", event.id());
                assertEquals(
                    new WorkEvent(1, "w-7", "received"),
                    event.data());
            })
            .assertNext(event ->
                assertEquals("validated", event.data().stage()))
            .assertNext(event ->
                assertEquals("completed", event.data().stage()))
            .expectComplete()
            .verify(Duration.ofSeconds(3));
    }
}
~~~

`WebTestClient` ở đây bind trực tiếp WebFlux controller để test mapping, status, Content-Type và encoding/decoding SSE. Trong integration test qua TCP server, có thể dùng `WebTestClient.bindToServer()` để kiểm tra connector/proxy thêm. `StepVerifier` vẫn kiểm tra stream tín hiệu trả về từ HTTP client.

### 16.10. Chạy và thử HTTP

Yêu cầu JDK 17+ và Maven.

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

Sau khi server chạy:

~~~bash
curl -i http://localhost:8080/api/workflows/w-7/summary
~~~

Response JSON minh họa:

~~~json
{
  "id": "w-7",
  "eventCount": 3,
  "lastStage": "completed"
}
~~~

SSE:

~~~bash
curl -N http://localhost:8080/api/workflows/w-7/events
~~~

Một response hợp lệ có event tương tự:

~~~text
id: 1
event: stage
data: {"sequence":1,"id":"w-7","stage":"received"}

id: 2
event: stage
data: {"sequence":2,"id":"w-7","stage":"validated"}

id: 3
event: stage
data: {"sequence":3,"id":"w-7","stage":"completed"}
~~~

**Lưu ý:** event có thể đến rất nhanh vì nguồn `Flux.just` đồng bộ; demo này chứng minh event framing và thứ tự, không mô phỏng độ trễ của tác vụ thực. Muốn kiểm thử thời gian, dùng `delayElements`, `withVirtualTime` ở unit test hoặc HTTP streaming integration test với source có độ trễ có kiểm soát.

## 17. Kịch bản kiểm thử cần có trong dự án thực

### 17.1. Service và repository

| Tình huống | Kỳ vọng tín hiệu | Hành động |
| --- | --- | --- |
| Repository có một row | `onNext(row)`, `onComplete` | Map đúng DTO |
| Repository rỗng | `onComplete` không có `onNext` | `switchIfEmpty` hoặc 404 |
| Validation fail | `onError(ValidationException)` | Không gọi repository tiếp |
| Lỗi DB | `onError(DataAccessException)` | Bảo toàn loại lỗi cần mapping |
| Fallback đúng lỗi | `onNext(cached)`, `onComplete` | Chỉ fallback theo policy |
| Hủy giữa luồng | `cancel` | Dừng upstream/cleanup resource |
| Nguồn nhiều row | Đúng số lượng + thứ tự nếu có contract | Không buffer toàn bộ bảng |
| Retry transient | N lần subscribe, cuối cùng success/error | Giới hạn retry và idempotency |

### 17.2. WebClient và stream

- HTTP 200 + JSON: `Mono<T>` có một phần tử và complete.
- HTTP 204: `Mono<Void>` complete không có phần tử.
- HTTP 404: mặc định `retrieve()` có thể phát `WebClientResponseException.NotFound`.
- HTTP stream: nhiều `onNext`, sau đó complete hoặc error.
- Slow response: `timeout` phát error; cancellation được truyền upstream tùy connector.
- Retry: số request outbound phải đúng và không retry POST không idempotent một cách mù quáng.
- SSE event stream: event có ID/type/payload theo thứ tự, kết thúc khi source complete.

`StepVerifier` không thay thế mock HTTP server; test HTTP status/body/headers bằng `WebTestClient` hoặc MockWebServer/WireMock để đảm bảo mapping thật.

### 17.3. Transaction

Với R2DBC reactive transaction, test cần biết:
- Các operation trong cùng `TransactionalOperator` hoặc `@Transactional` reactive.
- Khi một operation error, transaction rollback theo semantics transaction manager.
- Không có `subscribe()` phụ bên trong service làm mất Reactor Context và transaction.
- Khi cancel, driver và transaction manager cần cleanup; không giả định external side-effect đã commit có thể tự rollback.

Dùng integration test với database thật hoặc production-like database để xác nhận transaction state, không chỉ dùng StepVerifier kiểm tra `Mono.error`.

## 18. Debug khi StepVerifier fail

Một số thông điệp điển hình:

| Hiện tượng | Nguyên nhân thường gặp | Cách điều tra |
| --- | --- | --- |
| Expected onNext nhưng nhận onComplete | Source rỗng hoặc bị filter | Kiểm tra `switchIfEmpty`, filter và dữ liệu test |
| Expected onComplete nhưng nhận onError | Exception trong `map`/dependency | Kiểm tra type, stack trace và error mapper |
| Expected onComplete nhưng nhận onNext khác | Có nhiều phần tử hơn dự kiến | Kiểm tra `flatMap` concurrency, count và order |
| Test treo ở expectNext | Thiếu demand, source never hoặc async không phát | Thêm `thenRequest`, timeout và subscriber probe |
| Test virtual-time vẫn đợi thật | Publisher tạo trước supplier hoặc dùng scheduler riêng | Tạo source trong `withVirtualTime` supplier |
| `expectNoEvent` fail ngay | `onSubscribe` cũng là event | Thêm `.expectSubscription()` trước |
| Context không accessible | Publisher ngoài Reactor hoặc subscription tách | Kiểm tra `contextWrite`, `deferContextual`, manual subscribe |
| Fallback probe không subscribed | Primary source không empty, nhánh không đi qua | Kiểm tra `switchIfEmpty` |
| `TestPublisher` emit mà verifier không nhận | Emit trước subscribe ở hot source | Phát trong `.then(...)` |
| `verify()` chưa được gọi | Kịch bản chưa kích hoạt | Kết thúc bằng `verify` hoặc shortcut |
| Flaky do `Thread.sleep` | Timing lệ thuộc CI load | Dùng virtual time/latch/TestPublisher |
| Kết quả test đột ngột sai khi chạy song song | Global hooks/virtual scheduler và shared state | Tách trạng thái mỗi test, cleanup hooks |

### 18.1. Không dùng `Thread.sleep` để làm ổn định test

Ví dụ yếu:

~~~java
// Không nên: mốc thời gian không có bảo đảm.
Thread.sleep(500);
assertEquals(2, collected.size());
~~~

Ví dụ mạnh hơn:

~~~java
StepVerifier.create(
        Flux.just(1, 2).delayElements(Duration.ofMillis(50)))
    .expectNext(1, 2)
    .expectComplete()
    .verify(Duration.ofSeconds(3));
~~~

Với phép toán thời gian thuần, `withVirtualTime` tốt hơn vì không chờ thật. Với callback hoặc event nguồn chủ động, `TestPublisher` giúp kiểm soát thứ tự tuyệt đối hơn so với sleep.

### 18.2. Kiểm tra log/onError

Không dùng `doOnError` như một assertion thay cho StepVerifier:

~~~java
source.doOnError(error -> log.warn("failed", error));
~~~

`doOnError` chỉ quan sát; nếu source lỗi thì test vẫn phải `.expectError(...)`. Nếu code khôi phục lỗi bằng `onErrorResume`, test nên xác nhận tín hiệu đầu ra và nhánh fallback được gọi; có thể dùng `PublisherProbe`.

## 19. Anti-pattern phổ biến

| Anti-pattern | Hậu quả | Cách đúng |
| --- | --- | --- |
| `.block()` mọi `Mono` trong unit test | Mất thông tin thứ tự/terminal, không test demand | `StepVerifier` |
| `.subscribe()` rồi kiểm tra biến mutable | Race, test có thể kết thúc sớm | StepVerifier làm subscriber |
| Không có terminal expectation | Kịch bản có thể chưa đầy đủ | `expectComplete` / `expectError` / `thenCancel` |
| Dùng `verifyComplete()` với `Flux.never()` | Test treo | `thenCancel()` hoặc timeout phù hợp |
| Không giới hạn thời gian verify | CI treo khi source không complete | `verify(Duration)` |
| `expectNextCount(100)` cho dữ liệu nghiệp vụ cần chính xác | Bỏ qua nội dung sai | `expectNextSequence`/`assertNext` |
| `expectNoEvent` trước `expectSubscription` | Nhận subscription, test fail ngay | `expectSubscription()` trước |
| Tạo `Flux.interval` quá sớm | Virtual time không chắc áp dụng | Tạo bên trong supplier |
| Dùng `Thread.sleep` trong mỗi test | Flaky, chậm, không deterministic | Virtual time/TestPublisher |
| Phát TestPublisher trước subscriber | Hot signal bị mất | Emit trong `.then(...)` |
| Tắt `checkUnderRequesting` để qua lỗi | Che bug demand thật | Fix `thenRequest` và script |
| Lẫn cancel với complete | Assert sai terminal và cleanup | `thenCancel`, probe/`doFinally` |
| Mock mọi thứ tới mức không còn HTTP/DB thật | Không kiểm tra serialization/driver | Tách unit và integration tests |
| Assert thread name để chứng minh reactive | Thread có thể thay đổi hợp lệ | Assert signals, context và side-effects |
| Test bám chặt internal operator | Refactor dễ phá test vô ích | Test contract đầu ra |
| Đặt global Hooks/scheduler rồi không cleanup | Cross-test contamination | Scope/cleanup toàn bộ setting |

## 20. Checklist tự đánh giá

- [ ] Biết thứ tự hợp lệ `onSubscribe → onNext* → onComplete/onError`.
- [ ] Phân biệt empty completion và error.
- [ ] Có terminal expectation và bước verify thật.
- [ ] Test giá trị, số lượng và thứ tự khi contract đòi hỏi.
- [ ] Error tests kiểm tra type/message theo nghiệp vụ.
- [ ] Có timeout cho kịch bản có nguy cơ treo.
- [ ] `expectNoEvent` được đặt sau `expectSubscription` khi phù hợp.
- [ ] `withVirtualTime` tạo publisher bên trong supplier.
- [ ] Có test backpressure dùng `initialRequest(0)`/`thenRequest`.
- [ ] Có test cancellation với `thenCancel` và tín hiệu cleanup/probe.
- [ ] Có test Reactor Context khi service phụ thuộc Context.
- [ ] Có `TestPublisher` cho lỗi/nhánh upstream khó mô phỏng.
- [ ] Có `PublisherProbe` cho nhánh fallback/cancel.
- [ ] Dùng `verifyThenAssertThat` khi cần kiểm tra discard/drop.
- [ ] Tên scenario/expectation rõ để debug trên CI.
- [ ] Không dùng `.subscribe()` rồi sleep trong unit tests.
- [ ] Không giữ shared mutable TestPublisher/scheduler giữa các test.
- [ ] Có WebTestClient/integration test cho HTTP/DB contract thực.
- [ ] Kịch bản test không che bug bằng fallback catch-all.
- [ ] Code production không có blocking call trên Netty event-loop.

## 21. Bài tập thực hành

**Bài 1 – Mono đơn:** tạo `Mono.just(new WorkSummary("a",3,"completed"))`; test đúng một `onNext` và `onComplete`.

**Bài 2 – Empty:** tạo `Mono.empty()`; xác nhận không phát `onNext`, chỉ hoàn tất. Thêm `switchIfEmpty` và kiểm tra fallback.

**Bài 3 – Error:** phát `IllegalArgumentException("bad input")`; kiểm tra type/message; thử nhầm `expectComplete` để thấy failure.

**Bài 4 – Data trước error:** tạo Flux có một phần tử rồi `onError`; kiểm tra thứ tự và không có `onComplete`.

**Bài 5 – Predicate:** tạo Flux record có ID động; dùng `expectNextMatches` hoặc `assertNext` xác nhận field mà không hardcode toàn object.

**Bài 6 – Backpressure:** `initialRequest(0)`, rồi request 1 và 2, kiểm tra `Flux.range(1,3)` chỉ phát theo demand.

**Bài 7 – Virtual time:** `Mono.delay(Duration.ofDays(1))`; với virtual time, kiểm tra không có event trước một ngày và phát `0L` khi đến hạn.

**Bài 8 – Timeout:** nguồn chậm 10 giây, timeout 3 giây; test nhận `TimeoutException` bằng virtual clock.

**Bài 9 – Retry:** `Mono.defer` lỗi hai lần rồi thành công; `Retry.fixedDelay` hai lần; xác nhận attempt count bằng `AtomicInteger`.

**Bài 10 – TestPublisher:** điều khiển `next("a")`, `next("b")`, `complete`; xác minh `map(String::toUpperCase)` đúng thứ tự.

**Bài 11 – PublisherProbe:** tạo primary empty và fallback; xác nhận `assertWasSubscribed`. Đổi primary có dữ liệu và kiểm tra `assertWasNotSubscribed`.

**Bài 12 – Context:** đưa trace ID vào `withInitialContext`, đọc bằng `deferContextual` và xác nhận giá trị.

**Bài 13 – Cancel:** tạo nguồn never, hủy bằng `thenCancel`, xác nhận `PublisherProbe.assertWasCancelled`.

**Bài 14 – Post assertions:** filter số lẻ, dùng `verifyThenAssertThat().hasDiscarded(...)`.

**Bài 15 – HTTP:** chạy project, dùng WebTestClient kiểm tra summary JSON và Flux SSE; StepVerifier kiểm tra thứ tự event.

## 22. Tài liệu tham khảo chính thức

1. Project Reactor 3.8 – Testing (`StepVerifier`, virtual time, Context, TestPublisher, PublisherProbe): https://projectreactor.io/docs/core/release/reference/testing.html
2. Reactor Test Javadoc – `StepVerifier`: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html
3. Reactor Test Javadoc – `StepVerifier.Step`: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.Step.html
4. Reactor Test Javadoc – `StepVerifierOptions`: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifierOptions.html
5. Reactor Test Javadoc – `StepVerifier.Assertions`: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.Assertions.html
6. Reactor Test Javadoc – `TestPublisher`: https://projectreactor.io/docs/test/release/api/reactor/test/publisher/TestPublisher.html
7. Reactor Test Javadoc – `PublisherProbe`: https://projectreactor.io/docs/test/release/api/reactor/test/publisher/PublisherProbe.html
8. Spring Framework – WebFlux annotated controllers: https://docs.spring.io/spring-framework/reference/web/webflux/controller.html
9. Spring Framework – `WebTestClient`: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
10. Spring Boot 4.0 – Managed dependency coordinates: https://docs.spring.io/spring-boot/4.0/appendix/dependency-versions/coordinates.html
11. Spring Boot 4.0.9 release: https://spring.io/blog/2026/10/23/spring-boot-4-0-9-available-now/

**Tự đánh giá cuối:** `verifyComplete()` khác `expectNext` thế nào? Tại sao `onError` loại trừ `onComplete`? Vì sao `expectNoEvent` cần đặt sau `expectSubscription`? Khi nào dùng `thenRequest(1)` thay vì để StepVerifier request unbounded? Tại sao `withVirtualTime` nhận supplier chứ không nhận Flux đã tạo? `PublisherProbe` kiểm tra điều gì mà `expectNextCount` không kiểm tra được? Nếu viết được test về giá trị, thứ tự, lỗi, demand, time, Context và cancel, bạn đã biết dùng StepVerifier để bảo vệ hợp đồng tín hiệu của Reactor.
