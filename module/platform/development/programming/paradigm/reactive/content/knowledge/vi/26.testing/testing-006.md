# Thời gian ảo cho `delay`, debounce, `timeout` và `retry`

Các pipeline reactive thường phụ thuộc vào thời gian: trì hoãn phát dữ liệu, chỉ giữ giá trị cuối cùng sau một khoảng yên lặng, kết thúc một thao tác nếu chờ quá lâu hoặc thử lại sau lỗi tạm thời. Nếu kiểm thử những hành vi này bằng đồng hồ thật và `Thread.sleep`, test sẽ chậm, dễ dao động theo tải máy và khó kiểm tra chính xác ranh giới thời gian.

Reactor Test cung cấp **virtual time** (thời gian ảo) để điều khiển đồng hồ mà các toán tử thời gian sử dụng. Test có thể tiến đồng hồ vài giây trong thời gian thực rất ngắn, xác nhận trước một deadline chưa có tín hiệu, rồi tiến tới đúng mốc để kiểm tra `onNext`, `onError` hoặc `onComplete`. Cách này đặc biệt hữu ích với `delay`, debounce, `timeout` và retry có backoff.

Chủ đề này thuộc chương **Kiểm thử** của REACTIVE_PROGRAMMING. Module học tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; đồng thời thực hành Mono, Flux, kết hợp operator, scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Mục tiêu của bài là làm chủ đồng hồ kiểm thử, đặt pipeline đúng thời điểm để virtualize và xác nhận các mốc thời gian mà không phải chờ đồng hồ thật.

## Thời gian ảo hoạt động như thế nào?

Thông thường, các toán tử như `Mono.delay`, `Flux.interval`, `delayElements`, `timeout` và một số chiến lược retry dùng scheduler để lên lịch tác vụ trong tương lai. Scheduler dựa trên đồng hồ thực nên test phải chờ khoảng thời gian đã cấu hình.

`StepVerifier.withVirtualTime` tạo một `VirtualTimeScheduler`, cài nó vào các scheduler mặc định mà Reactor sử dụng cho pipeline được tạo trong phạm vi test, rồi cho phép test tiến đồng hồ theo yêu cầu. Thay vì đợi năm giây, test có thể gọi `thenAwait(Duration.ofSeconds(5))` để nhảy đồng hồ ảo tới mốc đó.

```text
Đồng hồ thực                         Đồng hồ ảo
────────────                         ──────────
Đợi 1 giây                           tiến +1 giây
Đợi thêm 2 giây                       tiến +2 giây
Đợi thêm 5 giây                       tiến +5 giây
Test tốn ít nhất 8 giây               test chạy gần như tức thời
```

Virtual time chỉ điều khiển các tác vụ được lên lịch qua scheduler mà test kiểm soát. Nó không làm cho một lời gọi blocking, `Thread.sleep`, thao tác I/O thật hoặc clock riêng do ứng dụng tự tạo tự động nhảy theo. Muốn kiểm thử thời gian ổn định, hãy đưa scheduler/clock thành dependency có thể thay thế và tránh hard-code việc chờ đồng hồ thật trong logic.

## Quy tắc quan trọng: tạo pipeline bên trong supplier

`StepVerifier.withVirtualTime` nhận một `Supplier<Publisher<T>>`. Hãy tạo toàn bộ pipeline có toán tử thời gian bên trong supplier này:

```java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofSeconds(5))
    )
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(5))
    .expectNext(0L)
    .verifyComplete();
```

Supplier chỉ được gọi sau khi virtual scheduler đã được cài đặt. Nhờ đó, `Mono.delay` lấy scheduler ảo thay vì scheduler thực.

Tránh tạo Publisher thời gian trước rồi truyền biến đã tạo vào `withVirtualTime`:

```java
// Không nên: pipeline có thể đã giữ scheduler thực trước khi virtual time được cài.
Mono<Long> source = Mono.delay(Duration.ofSeconds(5));

StepVerifier.withVirtualTime(() -> source)
    .thenAwait(Duration.ofSeconds(5))
    .expectNext(0L)
    .verifyComplete();
```

Một số operator chỉ chọn scheduler khi subscribe, nhưng không nên dựa vào chi tiết triển khai đó. Quy tắc an toàn là tạo nguồn và gắn tất cả operator phụ thuộc thời gian bên trong supplier. Điều này cũng áp dụng cho `Retry` spec hoặc Publisher con có scheduler được chọn khi tạo.

### Cấu trúc cơ bản của một test virtual time

```java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

StepVerifier.withVirtualTime(() -> Mono.delay(Duration.ofSeconds(3)))
    .expectSubscription()
    .expectNoEvent(Duration.ofSeconds(2))
    .thenAwait(Duration.ofSeconds(1))
    .expectNext(0L)
    .verifyComplete();
```

- `expectSubscription()` xác nhận subscription trước khi bắt đầu kiểm tra khoảng không có tín hiệu.
- `expectNoEvent(duration)` tiến thời gian ảo trong khoảng đó và thất bại nếu có tín hiệu không mong đợi.
- `thenAwait(duration)` tiến thời gian ảo nhưng không yêu cầu khoảng đó phải không có tín hiệu.
- `expectNext(...)`, `expectError(...)` và `verifyComplete()` kiểm tra tín hiệu sau khi đồng hồ đã tới mốc cần thiết.

`expectNoEvent` tính cả subscription như một sự kiện, vì vậy thường đặt `expectSubscription()` trước nó. Dùng `thenAwait` khi chỉ muốn cho timer chạy tới mốc tiếp theo mà không cần khẳng định khoảng đó hoàn toàn im lặng.

## Kiểm thử `delay` và `delayElements`

### Trì hoãn một giá trị bằng `Mono.delay`

`Mono.delay(duration)` phát một số `long` sau khoảng thời gian chỉ định rồi hoàn tất. Đây là nguồn timer thường dùng trong ví dụ và cũng là nền tảng cho nhiều operator thời gian.

```java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class DelayTest {
    @Test
    void emitsOnlyAfterThreeVirtualSeconds() {
        StepVerifier.withVirtualTime(() -> Mono.delay(Duration.ofSeconds(3)))
            .expectSubscription()
            .expectNoEvent(Duration.ofSeconds(2))
            .thenAwait(Duration.ofSeconds(1))
            .expectNext(0L)
            .verifyComplete();
    }
}
```

Test xác nhận hai giây đầu chưa có `onNext`; sau khi tiến thêm một giây, Mono phát `0L`. Test không phải đợi ba giây ngoài đời.

### Trì hoãn từng phần tử bằng `delayElements`

`delayElements` trì hoãn việc phát từng phần tử của Flux theo duration:

```java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class DelayElementsTest {
    @Test
    void delaysEachElementOnVirtualClock() {
        StepVerifier.withVirtualTime(() ->
                Flux.just("A", "B", "C")
                    .delayElements(Duration.ofSeconds(1))
            )
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(3))
            .expectNext("A", "B", "C")
            .verifyComplete();
    }
}
```

Với scheduler mặc định, mỗi phần tử được phát theo timer của `delayElements`. Có thể chia nhỏ bước tiến thời gian để kiểm tra từng mốc:

```java
StepVerifier.withVirtualTime(() ->
        Flux.just("A", "B").delayElements(Duration.ofSeconds(2))
    )
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(2))
    .expectNext("A")
    .thenAwait(Duration.ofSeconds(2))
    .expectNext("B")
    .verifyComplete();
```

Khi kiểm thử một operator trì hoãn, hãy xác nhận cả thứ tự và thời điểm phát. Nếu chỉ gọi `thenAwait` đủ lâu rồi kiểm tra tất cả phần tử, test có thể bỏ sót lỗi lệch thời điểm giữa các phần tử.

### Trì hoãn subscription bằng `delaySubscription`

`delaySubscription` trì hoãn thời điểm đăng ký vào nguồn. Điều này khác với `delayElements`: nguồn chưa bắt đầu được subscribe cho tới khi khoảng chờ kết thúc.

```java
StepVerifier.withVirtualTime(() ->
        Mono.just("ready")
            .delaySubscription(Duration.ofSeconds(4))
    )
    .expectSubscription()
    .expectNoEvent(Duration.ofSeconds(3))
    .thenAwait(Duration.ofSeconds(1))
    .expectNext("ready")
    .verifyComplete();
```

Nếu nguồn có side effect khi subscribe, `delaySubscription` trì hoãn cả side effect đó. Hãy phân biệt thời điểm tạo Publisher với thời điểm subscription thực sự bắt đầu.

## Kiểm thử debounce trong Reactor bằng `sampleTimeout`

Debounce phát một giá trị khi không có giá trị mới hơn xuất hiện trong một khoảng thời gian. Đây là hành vi hữu ích cho ô tìm kiếm: khi người dùng gõ liên tục, chỉ gửi truy vấn sau khi họ ngừng gõ một khoảng ngắn.

Trong Reactor, operator thường dùng cho hành vi debounce là `Flux.sampleTimeout` với một Publisher timer cho mỗi phần tử. Không nên nhầm tên API với RxJava, nơi operator có tên `debounce`.

```java
import java.time.Duration;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Flux<String> searchTerms = inputEvents()
    .sampleTimeout(term -> Mono.delay(Duration.ofMillis(300)));
```

Mỗi phần tử tạo một timer 300 ms. Nếu phần tử mới tới trước khi timer của phần tử trước kết thúc, timer cũ bị hủy và giá trị cũ không được phát. Giá trị gần nhất được phát khi khoảng yên lặng của nó hoàn tất.

### Kiểm thử chuỗi sự kiện có debounce

Tạo ba sự kiện tại các mốc 0 ms, 100 ms và 400 ms. Với cửa sổ debounce 200 ms, sự kiện đầu bị thay thế bởi sự kiện thứ hai; sự kiện thứ hai được phát ở mốc 300 ms. Sự kiện thứ ba được phát ở mốc 600 ms nếu nguồn vẫn còn mở đủ lâu.

```java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class DebounceTest {
    @Test
    void emitsLatestValueAfterQuietWindow() {
        StepVerifier.withVirtualTime(() ->
                Flux.concat(
                    Mono.just("A"),
                    Mono.delay(Duration.ofMillis(100)).thenReturn("B"),
                    Mono.delay(Duration.ofMillis(300)).thenReturn("C"),
                    Mono.delay(Duration.ofMillis(300)).then(Mono.<String>empty())
                ).sampleTimeout(value -> Mono.delay(Duration.ofMillis(200)))
            )
            .expectSubscription()
            .thenAwait(Duration.ofMillis(300))
            .expectNext("B")
            .thenAwait(Duration.ofMillis(300))
            .expectNext("C")
            .thenAwait(Duration.ofMillis(100))
            .verifyComplete();
    }
}
```

Nguồn được tạo bên trong supplier để các `Mono.delay` và timer của `sampleTimeout` cùng dùng virtual scheduler. Phần trì hoãn rỗng sau `C` giữ nguồn mở tới mốc 700 ms, giúp test xác nhận `C` được phát sau cửa sổ 200 ms ở mốc 600 ms thay vì chỉ dựa vào hành vi flush phần tử cuối khi nguồn hoàn tất.

### Những điểm cần kiểm tra với debounce

- Giá trị mới đến trước khi timer cũ kết thúc phải hủy timer cũ.
- Giá trị cuối được phát nếu không có giá trị mới trong cửa sổ debounce.
- Khi nguồn hoàn tất, xác nhận chính sách phát giá trị cuối theo semantics của operator.
- Khi nguồn lỗi, xác nhận lỗi được truyền xuống và không bị biến thành một giá trị bình thường.
- Nếu dùng `switchMap` để tự xây debounce, kiểm tra cancellation của Publisher timer cũ.

Debounce không giống throttle. Debounce chờ khoảng yên lặng sau giá trị gần nhất; throttle thường giới hạn tần suất phát theo một cửa sổ hoặc quy tắc lấy mẫu. Chọn operator theo hành vi sản phẩm cần có.

## Kiểm thử `timeout`

`timeout` phát lỗi `TimeoutException` nếu nguồn không phát tín hiệu tiếp theo trong khoảng thời gian quy định. Với `Mono`, timer bắt đầu chờ kết quả; với `Flux`, timeout thường được áp dụng cho khoảng chờ giữa các tín hiệu, và timer được đặt lại khi có phần tử mới.

### Kiểm tra timeout đúng deadline

```java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class TimeoutTest {
    @Test
    void failsWhenMonoDoesNotRespondBeforeDeadline() {
        StepVerifier.withVirtualTime(() ->
                Mono.<String>never().timeout(Duration.ofSeconds(5))
            )
            .expectSubscription()
            .expectNoEvent(Duration.ofSeconds(4))
            .thenAwait(Duration.ofSeconds(1))
            .expectError(TimeoutException.class)
            .verify();
    }
}
```

`Mono.never()` không phát giá trị hoặc terminal signal. Test xác nhận chưa có lỗi trong bốn giây đầu và timeout xảy ra khi đồng hồ đạt năm giây.

### Kiểm tra fallback khi timeout

Overload có Publisher dự phòng cho phép thay lỗi timeout bằng kết quả fallback:

```java
StepVerifier.withVirtualTime(() ->
        Mono.<String>never()
            .timeout(Duration.ofSeconds(3), Mono.just("cached-result"))
    )
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(3))
    .expectNext("cached-result")
    .verifyComplete();
```

Fallback cần biểu diễn kết quả có ý nghĩa. Nếu trả dữ liệu cache cũ, ứng dụng nên có metadata hoặc trạng thái cho biết dữ liệu có thể stale. Không trả một giá trị giả chỉ để che giấu dependency đã timeout.

### Timeout giữa các phần tử của Flux

```java
StepVerifier.withVirtualTime(() ->
        Flux.concat(
            Mono.just(1),
            Mono.delay(Duration.ofSeconds(2)).thenReturn(2),
            Mono.delay(Duration.ofSeconds(5)).thenReturn(3)
        ).timeout(Duration.ofSeconds(3))
    )
    .expectSubscription()
    .expectNext(1, 2)
    .thenAwait(Duration.ofSeconds(3))
    .expectError(TimeoutException.class)
    .verify();
```

Khoảng cách từ `1` tới `2` là hai giây nên không vượt timeout ba giây. Sau `2`, phần tử `3` cần chờ năm giây; timeout xảy ra sau ba giây không có tín hiệu tiếp theo. Test này xác nhận timer được đặt lại theo từng phần tử.

Timeout của Reactor giới hạn thời gian chờ tín hiệu trong pipeline. Nó không tự bảo đảm thao tác blocking bên dưới đã dừng; API client hoặc driver phải hỗ trợ cancellation/timeout tương ứng. Khi kiểm thử, không dùng một timeout của test quá ngắn khiến test harness kết thúc trước timeout của pipeline cần kiểm tra.

## Kiểm thử retry và backoff

Retry resubscribe vào nguồn sau lỗi theo chính sách được cấu hình. Với retry có delay, test cần xác nhận số lần thử, khoảng chờ và kết quả cuối. `Retry.fixedDelay` tạo khoảng chờ cố định giữa các lần thử; `Retry.backoff` tăng khoảng chờ theo cấp số nhân và có thể thêm jitter.

Ví dụ nguồn thất bại hai lần rồi thành công:

```java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;
import reactor.test.StepVerifier;
import static org.junit.jupiter.api.Assertions.assertEquals;

class RetryVirtualTimeTest {
    @Test
    void retriesAfterTwoVirtualDelays() {
        AtomicInteger attempts = new AtomicInteger();

        StepVerifier.withVirtualTime(() ->
                Mono.defer(() -> {
                    int attempt = attempts.incrementAndGet();
                    if (attempt < 3) {
                        return Mono.error(new IllegalStateException("temporary"));
                    }
                    return Mono.just("ok");
                }).retryWhen(Retry.fixedDelay(2, Duration.ofSeconds(1)))
            )
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(2))
            .expectNext("ok")
            .verifyComplete();

        assertEquals(3, attempts.get());
    }
}
```

`Retry.fixedDelay(2, ...)` cho phép tối đa hai lần retry sau lần gọi ban đầu. Nguồn dùng `Mono.defer` để mỗi lần resubscribe thực hiện logic tạo kết quả mới và tăng bộ đếm. Toàn bộ `defer` và `retryWhen` được tạo trong supplier để scheduler backoff được chọn sau khi virtual time đã cài đặt.

### Kiểm tra retry chưa xảy ra trước thời điểm backoff

Có thể chia nhỏ bước tiến thời gian để xác nhận lần thử tiếp theo chưa chạy sớm:

```java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.retry.Retry;
import static org.junit.jupiter.api.Assertions.assertEquals;

AtomicInteger attempts = new AtomicInteger();

StepVerifier.withVirtualTime(() ->
        Mono.defer(() -> {
            attempts.incrementAndGet();
            return Mono.error(new IllegalStateException("temporary"));
        }).retryWhen(Retry.fixedDelay(1, Duration.ofSeconds(4)))
    )
    .expectSubscription()
    .then(() -> assertEquals(1, attempts.get()))
    .thenAwait(Duration.ofSeconds(3))
    .then(() -> assertEquals(1, attempts.get()))
    .thenAwait(Duration.ofSeconds(1))
    .expectError(IllegalStateException.class)
    .verify();
```

Sau lần lỗi đầu tiên, bộ đếm vẫn là một trong ba giây đầu. Khi đủ bốn giây, lần retry diễn ra; nguồn lỗi lần nữa và không còn lượt retry nên test nhận lỗi cuối. Cách chia nhỏ thời gian giúp test kiểm tra chính sách backoff thay vì chỉ kiểm tra kết quả cuối.

### Retry backoff có jitter

`Retry.backoff` thường thêm jitter để nhiều client không đồng loạt retry tại cùng một thời điểm. Jitter là yếu tố ngẫu nhiên, vì vậy test thời gian chính xác nên tắt jitter hoặc đặt một scheduler và nguồn randomness có thể kiểm soát nếu API hỗ trợ. Ví dụ kiểm tra backoff không jitter:

```java
import java.time.Duration;
import reactor.util.retry.Retry;

Retry retryPolicy = Retry.backoff(2, Duration.ofSeconds(1))
    .maxBackoff(Duration.ofSeconds(4))
    .jitter(0d);
```

Trong test virtual time, tạo `retryPolicy` bên trong supplier cùng với pipeline. Với jitter khác 0, đừng khẳng định một mốc thời gian duy nhất nếu chính sách cho phép khoảng ngẫu nhiên; thay vào đó, kiểm tra giới hạn min/max hoặc tắt jitter trong test đơn vị và kiểm thử phân phối riêng ở cấp tích hợp.

Retry có thể lặp side effect vì mỗi lần thử là một subscription mới. Chỉ retry lỗi tạm thời, giới hạn số lần thử và tổng deadline, đồng thời dùng idempotency key cho thao tác ghi hoặc thanh toán. Virtual time kiểm tra được lịch retry; nó không chứng minh thao tác lặp là an toàn về nghiệp vụ.

## Kiểm thử nhiều operator thời gian trong cùng pipeline

Một pipeline thực tế có thể trì hoãn nguồn, debounce input, gọi service với timeout và retry khi lỗi tạm thời. Khi kiểm thử, nên tách các hành vi thành test nhỏ trước, sau đó thêm một test tích hợp cho thứ tự và tương tác giữa các timer.

Ví dụ mô tả pipeline tìm kiếm:

```java
import java.time.Duration;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

Flux<SearchResult> results = queryEvents()
    .sampleTimeout(query -> Mono.delay(Duration.ofMillis(250)))
    .flatMap(query -> searchClient.search(query)
        .timeout(Duration.ofSeconds(2))
        .retryWhen(Retry.fixedDelay(1, Duration.ofMillis(500))));
```

Trong test, tạo `queryEvents`, `sampleTimeout`, `timeout` và retry bên trong supplier của `withVirtualTime`. Sau đó tiến đồng hồ theo timeline: input ổn định 250 ms, request chờ response tối đa hai giây, và nếu lỗi tạm thời thì chờ 500 ms trước lần thử tiếp theo.

Khi nhiều timer cùng tồn tại, ghi timeline rõ ràng trước khi viết expectation. Xác định timer nào bắt đầu khi subscribe, timer nào bắt đầu sau `onNext`, timer nào được reset khi có tín hiệu mới và timer nào bị hủy khi upstream/downstream kết thúc. Điều này tránh nhầm tổng thời gian với khoảng timeout giữa hai tín hiệu.

## Dùng `VirtualTimeScheduler` khi cần scheduler tường minh

`withVirtualTime` thuận tiện khi operator dùng scheduler mặc định. Nếu ứng dụng truyền scheduler riêng vào operator, hãy đưa scheduler đó vào như dependency và dùng `VirtualTimeScheduler` trong test.

```java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import reactor.test.scheduler.VirtualTimeScheduler;

class ExplicitSchedulerTest {
    @Test
    void advancesInjectedTimer() {
        VirtualTimeScheduler timer = VirtualTimeScheduler.create();
        try {
            Flux<Long> ticks = Flux.interval(Duration.ofSeconds(1), timer)
                .take(2);

            StepVerifier.create(ticks)
                .then(() -> timer.advanceTimeBy(Duration.ofSeconds(1)))
                .expectNext(0L)
                .then(() -> timer.advanceTimeBy(Duration.ofSeconds(1)))
                .expectNext(1L)
                .verifyComplete();
        } finally {
            timer.dispose();
        }
    }
}
```

Test tự tạo `VirtualTimeScheduler` và truyền trực tiếp vào `Flux.interval`. Sau khi subscription bắt đầu, `advanceTimeBy` điều khiển đúng scheduler đó. `finally` dispose scheduler để test không để lại tài nguyên.

Đây cũng là mẫu thiết kế tốt cho production: service nhận scheduler/clock qua constructor hoặc cấu hình, thay vì tự gọi `Schedulers.newSingle()` bên trong mỗi phương thức. Test có thể inject scheduler ảo; ứng dụng thật inject scheduler phù hợp với vòng đời và tải.

## Các giới hạn của virtual time

Virtual time không thể tự điều khiển mọi thứ trong JVM:

- `Thread.sleep`, `System.currentTimeMillis()` và `Instant.now()` không tự chuyển sang đồng hồ ảo.
- JDBC, file I/O, HTTP client blocking hoặc thao tác chờ thread thật vẫn mất thời gian thật.
- Scheduler được tạo tường minh trước khi test cài virtual scheduler có thể không bị thay thế.
- Scheduler từ thư viện bên ngoài có thể không dùng Reactor scheduler factory.
- Một Publisher hot đã bắt đầu phát trước khi test subscribe có thể đã bỏ lỡ sự kiện; virtual time không quay ngược lịch sử của nó.
- Timer phụ thuộc clock riêng hoặc hệ thống bên ngoài cần abstraction clock/scheduler được inject để kiểm thử.

Nếu code cần biết thời điểm hiện tại, có thể inject `Clock` của Java thay vì gọi `Instant.now()` trực tiếp:

```java
import java.time.Clock;
import java.time.Instant;

final class ExpirationService {
    private final Clock clock;

    ExpirationService(Clock clock) {
        this.clock = clock;
    }

    Instant now() {
        return Instant.now(clock);
    }
}
```

Test có thể dùng `Clock.fixed(...)` để xác nhận logic thời gian lịch mà không cần chờ. `Clock` điều khiển thời điểm lịch (wall-clock time), còn `VirtualTimeScheduler` điều khiển tác vụ được lên lịch trong pipeline; hai abstraction giải quyết hai nhu cầu khác nhau.

## Lỗi thường gặp khi viết test virtual time

**Tạo pipeline trước `withVirtualTime`.** Operator có thể giữ scheduler thật. Tạo nguồn và gắn operator bên trong supplier.

**Dùng `Thread.sleep` trong test.** Sleep chờ đồng hồ thật, làm test chậm và không đồng bộ với virtual scheduler. Dùng `thenAwait`, `expectNoEvent` hoặc `advanceTimeBy`.

**Quên subscription trước `expectNoEvent`.** `expectNoEvent` cũng xem subscription là sự kiện. Gọi `expectSubscription()` trước khi xác nhận khoảng yên lặng.

**Nhầm `thenAwait` với `expectNoEvent`.** `thenAwait` chỉ tiến thời gian; `expectNoEvent` tiến thời gian và khẳng định không có tín hiệu trong khoảng đó.

**Tạo scheduler riêng bên ngoài supplier.** Scheduler đó có thể vẫn là scheduler thực. Inject `VirtualTimeScheduler` hoặc tạo scheduler bên trong supplier theo đúng cách test quản lý.

**Không tính đến timer bị reset.** `timeout` trên Flux thường đo khoảng chờ giữa các tín hiệu, không chỉ tổng thời gian từ subscription. Hãy viết timeline theo từng `onNext`.

**Kiểm tra retry nhưng không đếm số lần thử.** Kết quả cuối có thể đúng dù số lần retry sai. Dùng `AtomicInteger` hoặc fake dependency để xác nhận số lần gọi.

**Dùng jitter ngẫu nhiên nhưng kỳ vọng một mốc cố định.** Tắt jitter trong test đơn vị hoặc kiểm tra khoảng thời gian hợp lệ thay vì một timestamp chính xác.

**Giả định virtual time làm blocking code chạy tức thời.** Virtual scheduler không thay đổi thời gian của JDBC, `Thread.sleep` hay API đồng bộ. Cô lập hoặc thay thế dependency đó trong test.

## Tự kiểm tra

1. `StepVerifier.withVirtualTime` cài scheduler ảo vào thời điểm nào và vì sao pipeline cần được tạo trong supplier?
2. Khác biệt giữa `thenAwait` và `expectNoEvent` là gì?
3. Vì sao nên gọi `expectSubscription()` trước `expectNoEvent()`?
4. Làm thế nào kiểm thử `delayElements` để xác nhận từng phần tử xuất hiện đúng mốc?
5. Trong Reactor, có thể dùng operator nào để mô phỏng debounce và vì sao không nên nhầm tên API với RxJava?
6. `timeout` trên Flux đo tổng thời gian hay khoảng chờ giữa các tín hiệu?
7. Làm thế nào xác nhận retry chỉ diễn ra sau đúng backoff và đúng số lần?
8. Khi nào cần inject `VirtualTimeScheduler` thay vì chỉ dùng `withVirtualTime`?
9. Vì sao virtual time không làm `Thread.sleep` hoặc JDBC blocking chạy tức thời?
10. `Clock.fixed` khác `VirtualTimeScheduler` ở mục đích nào?

Khi tạo pipeline đúng thời điểm và điều khiển đồng hồ bằng virtual time, bạn có thể kiểm thử delay, debounce, timeout và retry nhanh, xác định chính xác ranh giới thời gian, đồng thời tránh test phụ thuộc vào tốc độ máy hoặc lịch chạy thread thực.
