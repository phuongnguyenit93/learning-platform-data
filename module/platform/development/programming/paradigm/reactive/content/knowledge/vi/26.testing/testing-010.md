# Kiểm thử xử lý đồng thời mà không phụ thuộc sleep tùy tiện

Pipeline reactive thường xử lý nhiều tác vụ cùng lúc: gọi hai dịch vụ độc lập, giới hạn số request đang chạy bằng `flatMap`, chuyển công việc sang scheduler khác hoặc xử lý tín hiệu đến từ nhiều nguồn. Các lỗi về thứ tự, race condition và cancellation thường chỉ xuất hiện khi những tác vụ đó tương tác.

Một cách kiểm thử thiếu ổn định là chèn `Thread.sleep` để “đợi đủ lâu” rồi kiểm tra kết quả. Thời gian chạy thay đổi theo máy, tải CI, scheduler và trạng thái thread. Sleep có thể làm test chậm nhưng vẫn không bảo đảm sự kiện đã xảy ra đúng lúc cần kiểm tra.

Với Project Reactor, có thể kiểm soát tín hiệu bằng `StepVerifier` và `TestPublisher`, điều khiển thời gian bằng virtual time, và dùng latch hoặc barrier có timeout khi cần xác minh các thread thực sự chạy đồng thời. Mục tiêu là tạo ra một thứ tự hoặc điểm đồng bộ xác định để kiểm thử hành vi, thay vì đoán thời điểm bằng thời gian chờ tùy ý.

## 1. Phân biệt thời gian, thứ tự và đồng thời

Ba khía cạnh này thường bị trộn lẫn trong test:

- **Thời gian:** một tín hiệu cần phát sau một khoảng thời gian, ví dụ `delay`, `timeout` hoặc `interval`.
- **Thứ tự:** tín hiệu A phải đến trước B, hoặc một Publisher con chỉ được subscribe sau khi nguồn cha phát giá trị.
- **Đồng thời:** nhiều tác vụ có khoảng thời gian thực thi chồng lấp, chẳng hạn hai request đã bắt đầu trước khi một request nào được phép hoàn tất.

Mỗi mục tiêu cần công cụ phù hợp:

| Điều cần xác minh | Công cụ phù hợp |
|---|---|
| Giá trị và terminal signal theo thứ tự | `StepVerifier` |
| Điều khiển chính xác lúc nguồn phát tín hiệu | `TestPublisher` hoặc `Sinks.One` |
| Timer, delay, interval, timeout | `StepVerifier.withVirtualTime` |
| Nhiều tác vụ thực sự cùng chạy | `CountDownLatch`, `CyclicBarrier` hoặc `Phaser` có timeout |
| Giới hạn số Publisher con đang hoạt động | `flatMap` kết hợp gate điều khiển được |
| Nhánh fallback có được subscribe | `PublisherProbe` |
| Cancellation được truyền lên nguồn | `thenCancel` và hook quan sát cancellation |

Một test tốt xác định được điều kiện cần đạt và điểm đồng bộ cần thiết. Nó không cần giả định rằng “sau 100 mili giây chắc chắn tác vụ đã chạy xong”.

## 2. Xác minh tín hiệu bằng StepVerifier

`StepVerifier` đăng ký vào Publisher và cho phép khai báo các tín hiệu mong đợi. Các bước xác minh được thực thi theo thứ tự; test chỉ tiến sang bước tiếp theo khi tín hiệu tương ứng đã xuất hiện.

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@Test
void kiemTraThuTuPhatDuLieu() {
    Flux<Integer> values = Flux.just(1, 2, 3)
        .map(value -> value * 10);

    StepVerifier.create(values)
        .expectNext(10)
        .expectNext(20)
        .expectNext(30)
        .verifyComplete();
}
~~~

Không cần sleep vì `verifyComplete` chờ giao thức Publisher hoàn tất và kiểm tra các phần tử theo đúng thứ tự. Nếu pipeline phát sai giá trị, thiếu phần tử, phát thêm phần tử hoặc kết thúc bằng lỗi, test sẽ thất bại.

Có thể gom các kỳ vọng liên tiếp bằng `expectNext`:

~~~java
StepVerifier.create(Flux.just("A", "B", "C"))
    .expectNext("A", "B", "C")
    .verifyComplete();
~~~

Khi kiểm tra kết quả từ `flatMap`, hãy nhớ rằng thứ tự phát toàn cục thường không được bảo đảm. Nếu nghiệp vụ chỉ yêu cầu đủ tập kết quả, dùng predicate hoặc thu thập rồi so sánh theo tập hợp. Chỉ khẳng định thứ tự nếu toán tử và hợp đồng nguồn thực sự bảo đảm thứ tự đó.

## 3. Điều khiển nguồn bằng TestPublisher

`TestPublisher` là Publisher dành cho kiểm thử. Test chủ động quyết định lúc nào phát phần tử, lỗi hoặc completion. Nhờ đó, có thể tạo một interleaving cụ thể mà không phụ thuộc scheduler hoặc tốc độ máy.

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;

@Test
void chuDongPhatTinHieuTheoTungBuoc() {
    TestPublisher<Integer> source = TestPublisher.create();

    Flux<Integer> doubled = source.flux()
        .map(value -> value * 2);

    StepVerifier.create(doubled)
        .then(() -> source.next(3))
        .expectNext(6)
        .then(() -> source.next(4))
        .expectNext(8)
        .then(source::complete)
        .verifyComplete();
}
~~~

Ở đây, `StepVerifier.then` chạy hành động do test cung cấp. Test phát một phần tử rồi đợi kết quả tương ứng trước khi phát phần tử kế tiếp. Có thể dùng cách này để kiểm tra:

- Một Publisher con chỉ được tạo sau khi nguồn cha phát giá trị.
- Dữ liệu được buffer khi downstream chưa yêu cầu.
- Lỗi xảy ra trước hoặc sau một phần tử cụ thể.
- Một nhánh được hủy khi nhánh khác thắng cuộc.
- Nguồn hoàn tất rỗng và kích hoạt fallback.

`TestPublisher` phù hợp để kiểm soát tín hiệu của nguồn trong test. Nó không tự mô phỏng mọi hành vi của một HTTP client, database driver hoặc thread pool thực tế; những thành phần đó nên được thay bằng fake hoặc adapter có thể điều khiển.

## 4. Kiểm thử thời gian bằng virtual time

Các toán tử như `delayElements`, `interval`, `delay` và `timeout` dựa trên scheduler. Nếu dùng thời gian thực, test phải chờ thật và có thể chậm hoặc flaky trên CI.

`StepVerifier.withVirtualTime` thay scheduler mặc định bằng virtual scheduler trong phạm vi kiểm thử. Khi test gọi `thenAwait`, đồng hồ ảo tiến lên mà không phải chờ cùng khoảng thời gian ngoài đời.

~~~java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@Test
void intervalDuocDieuKhienBangVirtualTime() {
    StepVerifier.withVirtualTime(() ->
            Flux.interval(Duration.ofSeconds(1)).take(3)
        )
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(3))
        .expectNext(0L, 1L, 2L)
        .verifyComplete();
}
~~~

Publisher cần được tạo bên trong supplier truyền cho `withVirtualTime`. Nếu tạo `Flux.interval` trước khi gọi phương thức này, nó có thể đã giữ scheduler thật và không chịu sự điều khiển của virtual time.

Có thể kiểm tra timeout mà không chờ năm giây thực:

~~~java
@Test
void timeoutDuocKiemThuKhongCanSleep() {
    StepVerifier.withVirtualTime(() ->
            Flux.<String>never()
                .timeout(Duration.ofSeconds(5))
                .onErrorReturn("timed-out")
        )
        .thenAwait(Duration.ofSeconds(5))
        .expectNext("timed-out")
        .verifyComplete();
}
~~~

Virtual time thích hợp với logic thời gian do Reactor scheduler quản lý. Nó không tự điều khiển HTTP request thật, database driver, executor tùy chỉnh hoặc API dùng đồng hồ hệ thống trực tiếp. Với những thành phần đó, hãy inject scheduler/clock hoặc dùng fake để test có thể điều khiển.

## 5. Phân biệt thenAwait và expectNoEvent

`thenAwait(duration)` tiến thời gian hoặc chờ một khoảng thời gian tùy loại StepVerifier đang dùng. Với virtual time, nó tiến đồng hồ ảo. Với verifier thông thường, nó chờ thời gian thực và chỉ nên dùng khi thời gian chờ là một phần có chủ đích của hợp đồng.

`expectNoEvent(duration)` xác minh rằng không có tín hiệu nào xuất hiện trong khoảng đó. Nó cũng xem subscription là một event, vì vậy nên gọi `expectSubscription()` trước khi dùng.

~~~java
StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofSeconds(1)).take(2)
    )
    .expectSubscription()
    .expectNoEvent(Duration.ofMillis(500))
    .thenAwait(Duration.ofSeconds(1))
    .expectNext(0L)
    .thenAwait(Duration.ofSeconds(1))
    .expectNext(1L)
    .verifyComplete();
~~~

Test trên kiểm tra phần tử đầu tiên chưa xuất hiện trong 500 mili giây ảo đầu tiên, sau đó xuất hiện ở mốc một giây. Không dùng `expectNoEvent` để “đoán” một tác vụ nền đã chạy xong; hãy dùng nó khi hợp đồng thực sự quy định không có tín hiệu trong một khoảng thời gian.

## 6. Kiểm tra hai tác vụ thực sự chạy đồng thời

Virtual time kiểm soát timer, nhưng không chứng minh hai thread thật sự chồng lấp. Để xác minh đồng thời, có thể dùng `CountDownLatch` làm cổng đồng bộ.

Trong ví dụ, hai tác vụ chỉ hoàn tất sau khi cả hai đã đi vào phần xử lý. Test chờ latch với timeout hữu hạn rồi mở cổng:

~~~java
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertTrue;

private Mono<String> gatedCall(
        String value,
        CountDownLatch entered,
        CountDownLatch release,
        Scheduler scheduler) {

    return Mono.fromCallable(() -> {
            entered.countDown();

            if (!release.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Test gate was not released");
            }

            return value;
        })
        .subscribeOn(scheduler);
}

@Test
void haiTacVuDaBatDauTruocKhiMotTacVuHoanTat() {
    CountDownLatch entered = new CountDownLatch(2);
    CountDownLatch release = new CountDownLatch(1);
    Scheduler scheduler =
        Schedulers.newBoundedElastic(2, 10, "concurrency-test");

    try {
        Mono<String> first =
            gatedCall("first", entered, release, scheduler);
        Mono<String> second =
            gatedCall("second", entered, release, scheduler);

        StepVerifier.create(Mono.zip(first, second))
            .then(() -> {
                try {
                    assertTrue(
                        entered.await(2, TimeUnit.SECONDS),
                        "Cả hai tác vụ phải bắt đầu trước khi mở cổng"
                    );
                } catch (InterruptedException error) {
                    Thread.currentThread().interrupt();
                    throw new AssertionError(error);
                } finally {
                    release.countDown();
                }
            })
            .expectNextMatches(pair ->
                pair.getT1().equals("first")
                    && pair.getT2().equals("second")
            )
            .verify(Duration.ofSeconds(3));
    } finally {
        release.countDown();
        scheduler.dispose();
    }
}
~~~

Hai lời gọi được subscribe trên scheduler có ít nhất hai worker. Mỗi lời gọi giảm bộ đếm `entered`, rồi chờ `release`. Test chỉ mở cổng sau khi cả hai đã vào phần xử lý. Nếu pipeline vô tình tuần tự hóa hai lời gọi, latch không đạt ngưỡng trong thời gian giới hạn và test báo lỗi.

Điểm quan trọng là timeout ở đây chỉ bảo vệ test khỏi treo vô hạn. Điều kiện thành công là cả hai tác vụ đã thực sự đến latch trước khi cổng được mở, không phải “đã chờ đủ lâu nên chắc chúng đã chạy”.

Không đặt latch chặn trên event loop hoặc scheduler có số worker bị giới hạn quá nhỏ. Trong ví dụ, công việc chờ được chuyển sang một bounded elastic scheduler có hai worker và scheduler được dispose sau test.

## 7. Kiểm tra giới hạn concurrency của flatMap

`flatMap(mapper, concurrency)` giới hạn số Publisher con được subscribe đồng thời. Có thể kiểm tra giới hạn này bằng các `Sinks.One` làm cổng hoàn tất cho từng Publisher con.

~~~java
import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Test
void flatMapKhongVuotQuaConcurrencyDaDat() {
    Map<Integer, Sinks.One<Integer>> gates = Map.of(
        1, Sinks.one(),
        2, Sinks.one(),
        3, Sinks.one()
    );

    List<Integer> started = new CopyOnWriteArrayList<>();
    AtomicInteger active = new AtomicInteger();
    AtomicInteger maxActive = new AtomicInteger();

    Flux<Integer> result = Flux.range(1, 3)
        .flatMap(id -> Mono.defer(() -> {
            started.add(id);
            int current = active.incrementAndGet();
            maxActive.accumulateAndGet(current, Math::max);

            return gates.get(id).asMono()
                .doFinally(signal -> {
                    active.decrementAndGet();
                });
        }), 2);

    StepVerifier.create(result)
        .then(() -> assertEquals(List.of(1, 2), started))
        .then(() ->
            assertEquals(Sinks.EmitResult.OK, gates.get(2).tryEmitValue(2))
        )
        .expectNext(2)
        .then(() -> assertEquals(List.of(1, 2, 3), started))
        .then(() ->
            assertEquals(Sinks.EmitResult.OK, gates.get(1).tryEmitValue(1))
        )
        .expectNext(1)
        .then(() ->
            assertEquals(Sinks.EmitResult.OK, gates.get(3).tryEmitValue(3))
        )
        .expectNext(3)
        .verifyComplete();

    assertEquals(2, maxActive.get());
}
~~~

Hai Publisher với ID 1 và 2 được subscribe trước. Khi gate của ID 2 phát giá trị và hoàn tất, `flatMap` mới subscribe Publisher thứ ba. Bộ đếm `maxActive` xác nhận số nhánh đồng thời không vượt quá hai.

Test chủ động điều khiển thứ tự hoàn tất nên không cần khẳng định thứ tự phát tự nhiên của các tác vụ. Trong ví dụ, ta cố ý phát gate 2 trước gate 1 để chứng minh `flatMap` có thể phát kết quả theo thời điểm Publisher con hoàn tất.

Nếu yêu cầu nghiệp vụ cần giữ thứ tự nguồn, hãy kiểm thử với `flatMapSequential` hoặc `concatMap` theo hợp đồng tương ứng. Không nên sửa test để mong `flatMap` luôn phát theo thứ tự đầu vào.

## 8. Kiểm thử cancellation mà không chờ thời gian

Cancellation là một tín hiệu điều khiển quan trọng. Có thể dùng `thenCancel` để hủy subscription tại một điểm xác định và kiểm tra nguồn đã nhận cancellation:

~~~java
import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;

@Test
void cancellationDuocTruyenDenNguon() {
    TestPublisher<Long> source = TestPublisher.create();

    StepVerifier.create(source.flux())
        .thenCancel()
        .verify();

    source.assertCancelled();
}
~~~

Cách này xác minh hành vi hủy trực tiếp mà không cần sleep để chờ một callback. Với resource thực như socket hoặc database cursor, hãy đặt hook quan sát cleanup hoặc dùng fake resource có trạng thái đóng/hủy để kiểm tra hành vi tương ứng.

Không đồng nhất cancellation với completion. Khi downstream hủy, nguồn không bắt buộc phát `onComplete`; test cần xác minh cancellation bằng hook hoặc probe phù hợp.

## 9. Dùng PublisherProbe để xác minh nhánh được subscribe

Một test có thể nhận đúng kết quả nhưng vẫn đi qua nhánh xử lý không mong muốn. `PublisherProbe` giúp xác minh một Publisher có được subscribe, request hoặc cancel hay không.

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;

@Test
void emptyKichHoatFallback() {
    PublisherProbe<String> fallback =
        PublisherProbe.of(Mono.just("default"));

    Mono<String> result = Mono.<String>empty()
        .switchIfEmpty(fallback.mono());

    StepVerifier.create(result)
        .expectNext("default")
        .verifyComplete();

    fallback.assertWasSubscribed();
}
~~~

Probe hữu ích khi kiểm tra retry, fallback, nhánh cache hoặc Publisher con được chọn theo điều kiện. Nó làm rõ đường đi của pipeline mà không cần thêm log hoặc chờ một khoảng thời gian.

## 10. Kiểm thử lỗi và retry bằng tín hiệu điều khiển

Để kiểm tra retry, hãy tạo nguồn có thể phát lỗi theo số lần gọi thay vì dùng sleep để tạo lỗi “đến muộn”:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Test
void retryLaiKhiNguonThatBaiTamThoi() {
    AtomicInteger attempts = new AtomicInteger();

    Mono<String> result = Mono.defer(() -> {
        if (attempts.incrementAndGet() < 3) {
            return Mono.error(new IllegalStateException("temporary"));
        }
        return Mono.just("ok");
    }).retry(2);

    StepVerifier.create(result)
        .expectNext("ok")
        .verifyComplete();

    assertEquals(3, attempts.get());
}
~~~

Nguồn phát lỗi ở hai lần subscribe đầu và phát giá trị ở lần thứ ba. `retry(2)` tạo lại subscription tối đa hai lần sau lần đầu. Test xác minh số lần thử chính xác mà không phụ thuộc thời gian.

Với retry có delay, kết hợp `withVirtualTime` để tiến thời gian ảo. Nếu cần kiểm tra backoff, hãy xác minh các mốc delay và số lần subscribe bằng counter hoặc probe.

## 11. Những giới hạn cần nhớ khi kiểm thử concurrency

Không phải mọi test đều có thể trở nên hoàn toàn xác định bằng virtual time. Virtual time điều khiển scheduler tương thích với Reactor; nó không ép một thread Java bất kỳ dừng hoặc chạy theo ý muốn.

Một số nguyên tắc thực tế:

- Dùng `TestPublisher` để điều khiển thứ tự phát tín hiệu của nguồn.
- Dùng virtual time cho timer của Reactor thay vì chờ thời gian thật.
- Dùng latch hoặc barrier có timeout để tạo điểm đồng bộ giữa thread thật.
- Inject `Scheduler`, `Clock` hoặc client interface để test có thể thay bằng implementation điều khiển được.
- Khi dùng `flatMap`, chỉ khẳng định thứ tự phát nếu toán tử bảo đảm thứ tự.
- Không dùng một latch không có timeout; test có thể treo vô hạn khi pipeline lỗi.
- Luôn mở gate trong `finally` và dispose scheduler do test tự tạo.
- Không dùng `System.gc()` hoặc đo thời gian chạy để suy luận rằng một task đã kết thúc.
- Tránh chia sẻ mutable collection không thread-safe giữa các nhánh chạy đồng thời.
- Với race condition hiếm, bổ sung stress test hoặc lặp nhiều interleaving; một lần chạy thành công không chứng minh không có race.

Nếu test cần kiểm tra một race giữa hai thao tác, hãy xác định điểm mà cả hai thread phải đạt tới trước khi tiếp tục. `CyclicBarrier` hoặc `Phaser` phù hợp khi có nhiều pha đồng bộ; `CountDownLatch` phù hợp khi chỉ cần chờ một số tác vụ đến cùng một điểm rồi mở cổng.

## 12. Checklist viết test không flaky

Trước khi chấp nhận một test concurrency, hãy kiểm tra:

1. Test đang xác minh thời gian, thứ tự hay sự chồng lấp thực sự?
2. Có thể điều khiển tín hiệu bằng `TestPublisher` hoặc `Sinks.One` không?
3. Nếu kiểm tra timer, Publisher có được tạo bên trong `withVirtualTime` không?
4. Nếu cần thread thật, test có barrier/latch với timeout hữu hạn không?
5. Có mở gate và dispose scheduler trong `finally` không?
6. Có đang giả định thứ tự phát của `flatMap` không?
7. Test có phân biệt completion, error và cancellation không?
8. Có kiểm tra số lần subscribe hoặc nhánh fallback bằng probe/counter không?
9. Mọi assertion đều dựa trên tín hiệu hoặc trạng thái đồng bộ xác định, thay vì một khoảng sleep đoán trước không?

Kiểm thử xử lý đồng thời đáng tin cậy bắt đầu từ việc điều khiển nguyên nhân tạo ra interleaving. `StepVerifier` xác minh tín hiệu, `TestPublisher` điều khiển nguồn, virtual time điều khiển timer, còn latch và barrier đồng bộ các thread thực. Khi test có điểm đồng bộ rõ ràng, timeout hữu hạn và cleanup đầy đủ, bộ kiểm thử có thể phát hiện lỗi về thứ tự, giới hạn concurrency và cancellation mà không phụ thuộc vào tốc độ máy chạy.

