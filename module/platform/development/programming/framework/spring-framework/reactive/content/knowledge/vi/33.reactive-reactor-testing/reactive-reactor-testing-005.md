# withVirtualTime và tạo publisher sau khi thiết lập thời gian ảo trong Reactor

Các phép thử reactive có thể phải kiểm tra một sự kiện xảy ra sau 10 giây, một lần retry sau vài phút hoặc một timeout sau một ngày. Nếu dùng thời gian thật, test suite sẽ chậm và dễ bị flakiness do tốc độ máy, scheduler và tải CI. Project Reactor cung cấp **StepVerifier.withVirtualTime** để thay thế đồng hồ của các Scheduler được Reactor quản lý bằng đồng hồ ảo. Test có thể tiến thời gian trong vài mili giây thực tế mà vẫn kiểm tra đúng quan hệ giữa thời điểm subscribe, sự kiện, timeout và completion.

Điểm quan trọng nhất của bài này là: **publisher dùng toán tử thời gian phải được tạo sau khi virtual scheduler được cài đặt**. Vì vậy StepVerifier.withVirtualTime không nhận thẳng Flux hoặc Mono đã được tạo trước; nó nhận **Supplier của Publisher**. Nếu tạo publisher trước rồi viết lambda chỉ trả về publisher cũ, các toán tử như delay, interval hay timeout có thể đã giữ tham chiếu tới scheduler thật, khiến virtual time không có tác dụng.

Bài học thuộc nhóm **Kiểm thử Reactor** của module Spring Framework - reactive. Nội dung trình bày cách hoạt động của virtual scheduler, vị trí tạo publisher, API StepVerifier, các ca kiểm thử thực hành với Java 17+, các lỗi nguy hiểm và giới hạn của mô phỏng thời gian.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao test dùng Thread.sleep không phù hợp với phần lớn reactive time operators.
- Phân biệt thời gian thực (wall-clock time) và thời gian ảo của VirtualTimeScheduler.
- Hiểu vì sao withVirtualTime nhận Supplier thay vì Flux/Mono đã có.
- Tạo publisher bên trong supplier để scheduler được chọn đúng thời điểm.
- Dùng expectSubscription, thenAwait và expectNoEvent đúng thứ tự.
- Hiểu kết quả của Mono.delay, Flux.interval, delayElements và delayElement.
- Kiểm tra timeout, retryBackoff, take(Duration) và cancellation.
- Kết hợp withVirtualTime với StepVerifierOptions và timeout thực cho verification.
- Dùng VirtualTimeScheduler thủ công cho trường hợp scheduler được truyền tường minh.
- Phân biệt toán tử dùng scheduler mặc định và scheduler custom được tạo sớm.
- Nhận biết deadlock hoặc test treo do đồng hồ ảo không được tiến.
- Hiểu virtual time không làm nhanh Thread.sleep, API mạng hoặc blocking I/O.
- Tránh nhiễu giữa các test khi virtual scheduler thay đổi factory toàn cục.
- Viết và đọc một bộ test JUnit 5 chạy được trên Java 17 và Reactor Test.

## 2. Vì sao cần thời gian ảo?

Giả sử một nghiệp vụ gửi thông báo sau một ngày:

~~~java
Mono<String> delayed = Mono.just("ready")
    .delayElement(Duration.ofDays(1));
~~~

Nếu kiểm thử bằng thời gian thật, một test có thể phải đợi đến ngày hôm sau. Đổi sang một khoảng 100 ms cho nhanh sẽ không còn kiểm tra đúng tham số cấu hình một ngày và vẫn có nguy cơ thất bại do máy chạy chậm.

Cách kiểm thử với virtual time:

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.just("ready")
            .delayElement(Duration.ofDays(1)))
    .expectSubscription()
    .expectNoEvent(Duration.ofDays(1))
    .expectNext("ready")
    .verifyComplete();
~~~

Test tiến đồng hồ ảo thêm một ngày mà không đợi một ngày ngoài đời. Đây là kỹ thuật **kiểm soát scheduler và thời gian sự kiện**, không phải thay đổi đồng hồ hệ điều hành.

Các ứng dụng hữu ích:

- Thông báo trì hoãn bằng delayElement.
- Tick định kỳ bằng Flux.interval.
- Phát nhiều phần tử có khoảng cách bằng delayElements.
- Timeout khi không có sự kiện.
- Retry với backoff.
- Cửa sổ thời gian và cache TTL, khi toán tử dùng scheduler có thể điều khiển.
- Chính sách hết hạn, debounce, bufferTimeout, windowTimeout hoặc take(Duration).
- Kiểm tra không phát sự kiện trước một mốc thời gian.

Không phải logic nào có khái niệm thời gian cũng dùng được virtual time: thư viện gọi System.currentTimeMillis(), java.time.Clock.systemUTC(), Thread.sleep, socket timeout của OS hoặc timer không thuộc Reactor sẽ không tự động theo VirtualTimeScheduler.

## 3. StepVerifier kiểm tra những gì?

StepVerifier là tiện ích từ dependency reactor-test, cho phép mô tả tuần tự tín hiệu mà Publisher phải phát.

Ví dụ thông thường:

~~~java
StepVerifier.create(Flux.just("A", "B"))
    .expectNext("A")
    .expectNext("B")
    .verifyComplete();
~~~

Các tín hiệu chính của Reactive Streams:

- **onSubscribe**: downstream nhận Subscription.
- **onNext**: phát một phần tử.
- **onError**: kết thúc bằng lỗi.
- **onComplete**: kết thúc thành công.
- **cancel**: downstream hủy Subscription.

StepVerifier mô tả kỳ vọng theo thứ tự xuất hiện. Khi gọi verify(), verifyComplete(), verifyError() hoặc biến thể tương ứng, việc subscribe và kiểm tra mới thực sự diễn ra.

### Hai cách tạo verifier

~~~java
StepVerifier.create(publisher)
    .expectNext("A")
    .verifyComplete();
~~~

Đây là kiểm thử bình thường, sử dụng scheduler của publisher.

~~~java
StepVerifier.withVirtualTime(() -> publisherCreatedHere())
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(30))
    .expectNext("A")
    .verifyComplete();
~~~

Đây là kiểm thử có virtual clock, được cài đặt trước khi gọi supplier tạo Publisher.

Dùng withVirtualTime khi cần điều khiển **thời điểm**; không cần nó cho một Flux.just thuần túy không liên quan đến thời gian.

## 4. VirtualTimeScheduler hoạt động như thế nào?

VirtualTimeScheduler triển khai Scheduler cho các công việc được lập lịch trên một trục thời gian giả lập. Thay vì đợi đồng hồ ngoài đời chạy tới hạn, test gọi advanceTimeBy, advanceTimeTo hoặc dùng StepVerifier.thenAwait để tiến đồng hồ và kích hoạt các task đã được xếp lịch.

Sơ đồ:

~~~text
Thời gian ảo: 0s ----- 5s ----- 10s ----- 15s
             |        |         |         |
             |     task A     task B    task C
             |
     StepVerifier subscribe

thenAwait(5s)  --> chạy task A
thenAwait(5s)  --> chạy task B
thenAwait(5s)  --> chạy task C
~~~

Thông thường Reactor time operators chọn scheduler qua Schedulers.parallel() hoặc factory tương đương. withVirtualTime cài VirtualTimeScheduler vào các Schedulers factories, để những operator **được tạo sau đó** có thể lấy scheduler ảo thay vì scheduler thật.

VirtualTimeScheduler không phải một thread chờ ảo. Nó lưu công việc hẹn giờ và chạy chúng khi test tiến thời gian. Khi clock tiến, nhiều task đến hạn có thể chạy ngay trong quá trình verify. Nếu một task block, test vẫn có thể bị treo.

### Một vài khái niệm

| Khái niệm | Giải thích |
| --- | --- |
| VirtualTimeScheduler | Scheduler có đồng hồ điều khiển thủ công |
| Scheduler factory | Cơ chế cung cấp các Schedulers mặc định của Reactor |
| Supplier<Publisher<T>> | Hàm tạo publisher sau khi scheduler ảo đã có |
| thenAwait(Duration) | Tiến đồng hồ mà không khẳng định không có sự kiện |
| expectNoEvent(Duration) | Tiến đồng hồ và xác minh không có tín hiệu trong khoảng đó |
| verify(Duration) | Giới hạn thời gian thực cho việc chờ verifier hoàn tất |
| expectSubscription() | Xác nhận onSubscribe, thường đặt trước expectNoEvent |

## 5. Tại sao withVirtualTime phải nhận Supplier?

API phổ biến:

~~~java
StepVerifier.withVirtualTime(
    () -> Mono.delay(Duration.ofHours(12)))
~~~

Supplier là một lambda trả Publisher, không phải Publisher đã được tạo. Lý do thuộc về **thời điểm khởi tạo operator**.

Khi tạo operator có thời gian, Reactor có thể chọn và giữ tham chiếu tới scheduler. Nếu operator được tạo trước khi StepVerifier cài clock ảo, nó có thể giữ scheduler thật.

### Cách đúng

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofHours(1))
            .take(3))
    .expectSubscription()
    .thenAwait(Duration.ofHours(3))
    .expectNext(0L, 1L, 2L)
    .verifyComplete();
~~~

Flux.interval và take(3) được tạo **bên trong** supplier. Scheduler ảo được cài trước, vì vậy khoảng ba giờ được mô phỏng.

### Cách sai

~~~java
Flux<Long> intervalAlreadyCreated =
    Flux.interval(Duration.ofHours(1)).take(3);

StepVerifier.withVirtualTime(() -> intervalAlreadyCreated)
    .expectSubscription()
    .thenAwait(Duration.ofHours(3))
    .expectNext(0L, 1L, 2L)
    .verifyComplete();
~~~

Lambda chỉ trả về publisher đã tạo sẵn. Nếu intervalAlreadyCreated đã giữ scheduler thật ở thời điểm assembly, tiến ba giờ ảo không khiến scheduler thật phát tick. Kết quả có thể treo hoặc vượt verification timeout.

Điểm cần nhớ: **supplier phải tạo lại ít nhất các operator phụ thuộc thời gian**, không chỉ trì hoãn việc lấy một biến chứa publisher.

### Cách sửa bằng method reference

~~~java
Flux<Long> buildIntervals() {
    return Flux.interval(Duration.ofHours(1)).take(3);
}

void testIntervals() {
    StepVerifier.withVirtualTime(this::buildIntervals)
        .expectSubscription()
        .thenAwait(Duration.ofHours(3))
        .expectNext(0L, 1L, 2L)
        .verifyComplete();
}
~~~

Method reference this::buildIntervals chỉ được gọi khi StepVerifier đã sắp đặt virtual time. Đây là một cách gọn để giữ phần dựng pipeline trong service hoặc factory.

## 6. Tạo publisher trong service phải thực sự lazy

Lấy ví dụ service:

~~~java
public final class ClockService {

    public Flux<String> heartbeat() {
        return Flux.interval(Duration.ofSeconds(10))
            .map(index -> "heartbeat-" + index);
    }
}
~~~

Nếu test gọi service.heartbeat() **bên trong lambda**, cách này phù hợp:

~~~java
StepVerifier.withVirtualTime(() -> service.heartbeat().take(2))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(20))
    .expectNext("heartbeat-0", "heartbeat-1")
    .verifyComplete();
~~~

Ngược lại, nếu service khởi tạo Flux.interval trong constructor và lưu vào field, thì ngay cả việc gọi service.heartbeat() trong supplier cũng có thể trả publisher đã giữ scheduler cũ.

~~~java
public final class EagerClockService {

    private final Flux<Long> sharedTicks =
        Flux.interval(Duration.ofSeconds(10));

    public Flux<Long> heartbeat() {
        return sharedTicks;
    }
}
~~~

Nếu EagerClockService được khởi tạo trước virtual clock, test dùng withVirtualTime(() -> service.heartbeat()) không đảm bảo đúng.

Có thể sửa bằng cách lưu **factory**, thay vì lưu publisher đã assembly:

~~~java
public final class LazyClockService {

    public Flux<Long> heartbeat() {
        return Flux.interval(Duration.ofSeconds(10));
    }
}
~~~

Hoặc dùng Flux.defer để xây time operator tại subscription nếu điều đó phù hợp nghiệp vụ:

~~~java
public Flux<Long> heartbeat() {
    return Flux.defer(
        () -> Flux.interval(Duration.ofSeconds(10)));
}
~~~

Flux.defer hữu ích, nhưng không phải “phép màu” cho publisher đã được tạo trước. Flux.defer(() -> oldPublisher) vẫn chỉ trả oldPublisher. Hãy đặt **việc tạo time operator** vào supplier/defer.

## 7. expectSubscription() và expectNoEvent()

Reactor xem onSubscribe là một tín hiệu. expectNoEvent(Duration) khẳng định không có bất cứ signal nào trong khoảng được xét, **bao gồm onSubscribe**.

Do đó, cách này thường sai:

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofSeconds(5)))
    .expectNoEvent(Duration.ofSeconds(5))
    .expectNext(0L)
    .verifyComplete();
~~~

onSubscribe xuất hiện ngay sau khi verifier subscribe, nên expectNoEvent ở vị trí đầu có thể thất bại vì chính signal đó.

Cách đúng:

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofSeconds(5)))
    .expectSubscription()
    .expectNoEvent(Duration.ofSeconds(5))
    .expectNext(0L)
    .verifyComplete();
~~~

### Vì sao expectNoEvent mạnh hơn thenAwait?

Hai cách đều có thể tiến thời gian ảo:

~~~java
.thenAwait(Duration.ofSeconds(5))
~~~

và:

~~~java
.expectNoEvent(Duration.ofSeconds(5))
~~~

Khác biệt quan trọng:

- thenAwait chỉ tiến thời gian, không tự khẳng định không phát onNext trong khoảng.
- expectNoEvent tiến thời gian **và thất bại nếu gặp bất kỳ tín hiệu không mong đợi** trong khoảng.

Nếu yêu cầu là “chỉ phát sau 5 giây”, expectNoEvent phù hợp hơn, vì nó phát hiện một giá trị đến quá sớm. Nếu chỉ muốn scheduler chạy task đến hạn và sau đó kiểm tra nhiều giá trị, thenAwait tiện hơn.

### Tín hiệu tại đúng biên thời gian

Trong ví dụ tài liệu Reactor, expectNoEvent(Duration.ofDays(1)) tiếp theo expectNext(0L) dùng được với Mono.delay(Duration.ofDays(1)). Tuy nhiên, đối với operator phức tạp có nhiều task cùng đến hạn ở một timestamp, hãy tránh suy luận thứ tự sự kiện nếu hợp đồng không yêu cầu; có thể tách mốc thành những khoảng nhỏ hoặc kiểm tra với thenAwait và expectNext theo nội dung.

## 8. thenAwait() không phải Thread.sleep()

Đối với StepVerifier thông thường, thenAwait(Duration) đợi theo thời gian thực. Đối với StepVerifier.withVirtualTime, thenAwait tiến đồng hồ ảo.

Ví dụ:

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.just("done")
            .delayElement(Duration.ofMinutes(30)))
    .expectSubscription()
    .thenAwait(Duration.ofMinutes(30))
    .expectNext("done")
    .verifyComplete();
~~~

Bài test mô phỏng 30 phút trì hoãn, nhưng không chờ 30 phút thật.

Đừng thay thenAwait bằng:

~~~java
Thread.sleep(30_000);
~~~

Thread.sleep không tiến VirtualTimeScheduler; ngược lại nó chỉ giữ thread thực trong 30 giây, làm chậm test và có thể khiến deadline của test hết hạn.

Trong virtual test, cần chủ động tiến clock tới những mốc có task được lập lịch. Nếu một sự kiện phụ thuộc vào thời gian ảo nhưng test chờ expectNext() trước khi gọi thenAwait(), verifier có thể chờ mãi.

## 9. Mono.delay: một tín hiệu sau thời gian hẹn

Mono.delay(Duration) phát Long 0L sau khoảng thời gian yêu cầu, rồi complete. Đây là ví dụ nhập môn nhất của virtual time.

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofDays(1)))
    .expectSubscription()
    .expectNoEvent(Duration.ofDays(1))
    .expectNext(0L)
    .verifyComplete();
~~~

Expected signal trace:

~~~text
t = 0: subscribe
t = 0 .. 1 ngày: không có onNext
t = 1 ngày: onNext(0)
t = 1 ngày: onComplete
~~~

Mặc dù test hẹn một ngày, verify chạy nhanh nếu tất cả toán tử phụ thuộc thời gian đều dùng scheduler ảo và không có tác vụ chặn thực tế.

### delayElement khác Mono.delay

~~~java
Mono.just("hello").delayElement(Duration.ofSeconds(5))
~~~

phát lại String hello sau 5 giây. Còn:

~~~java
Mono.delay(Duration.ofSeconds(5))
~~~

phát số Long 0L. Khi viết expectNext, cần khớp đúng loại dữ liệu.

## 10. Flux.interval: nhiều tick theo thời gian ảo

Flux.interval(Duration) phát Long tăng từ 0, mỗi lần sau một khoảng cố định. Ví dụ interval 2 giây:

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofSeconds(2))
            .take(3))
    .expectSubscription()
    .expectNoEvent(Duration.ofSeconds(2))
    .expectNext(0L)
    .thenAwait(Duration.ofSeconds(2))
    .expectNext(1L)
    .thenAwait(Duration.ofSeconds(2))
    .expectNext(2L)
    .verifyComplete();
~~~

Trace:

~~~text
t=0s: subscribe
t=2s: onNext(0)
t=4s: onNext(1)
t=6s: onNext(2), onComplete vì take(3)
~~~

### Tránh interval vô hạn trong test

Không làm:

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofMillis(1)))
    .thenAwait(Duration.ofDays(100))
    .expectNextCount(1_000_000)
    .verifyComplete();
~~~

Publisher là vô hạn nên verifyComplete không có completion. Ngoài ra, một bước tiến thời gian khổng lồ có thể kích hoạt hàng triệu task/tick đồng thời, làm tốn CPU và bộ nhớ.

Dùng take(n), thenCancel hoặc một predicate kết thúc rõ ràng:

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofSeconds(1)))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(3))
    .expectNext(0L, 1L, 2L)
    .thenCancel()
    .verify();
~~~

thenCancel kết thúc verification bằng cách cancel subscription; không kỳ vọng onComplete từ một stream không giới hạn.

## 11. delayElements và thứ tự phát tín hiệu

delayElements(Duration) trì hoãn mỗi phần tử theo một khoảng từ lúc phần tử trước được phát trong luồng có điều tiết. Với Flux.just có ba phần tử:

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.just("A", "B", "C")
            .delayElements(Duration.ofSeconds(5)))
    .expectSubscription()
    .expectNoEvent(Duration.ofSeconds(5))
    .expectNext("A")
    .thenAwait(Duration.ofSeconds(5))
    .expectNext("B")
    .thenAwait(Duration.ofSeconds(5))
    .expectNext("C")
    .verifyComplete();
~~~

Với pipeline này, thời điểm mong đợi là:

~~~text
t=0s: subscribe
t=5s: A
t=10s: B
t=15s: C, complete
~~~

Đừng nhầm delayElements với delaySequence. delaySequence trì hoãn sự khởi đầu phát của toàn chuỗi theo một duration; delayElements trì hoãn các phần tử riêng lẻ. Với nguồn phức tạp hoặc nguồn hot, semantics phải được kiểm tra theo từng operator.

### Dùng thenAwait một lần hay nhiều lần?

Cách gộp:

~~~java
.thenAwait(Duration.ofSeconds(15))
.expectNext("A", "B", "C")
.verifyComplete();
~~~

thường đủ khi chỉ quan tâm tập các giá trị và thứ tự sau 15 giây. Cách chia ba mốc như ở trên hữu ích khi muốn xác nhận không phát sớm. Chọn độ chi tiết của test dựa trên yêu cầu nghiệp vụ, không nhất thiết chia mỗi tick thành một assertion riêng.

## 12. timeout với đồng hồ ảo

Mono.timeout(Duration) tạo lỗi TimeoutException nếu publisher không đáp ứng đúng thời hạn. Kiểm thử với Mono.never:

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.<String>never()
            .timeout(Duration.ofSeconds(5)))
    .expectSubscription()
    .expectNoEvent(Duration.ofSeconds(4))
    .thenAwait(Duration.ofSeconds(1))
    .expectError(TimeoutException.class)
    .verify();
~~~

Trace:

~~~text
t=0s: subscribe, upstream không phát gì
t=4s: chưa có sự kiện
t=5s: TimeoutException
~~~

Dùng Mono.<String>never() để compiler biết kiểu String. Mono.never() không tự complete và không tự error. Chính toán tử timeout tạo lỗi khi clock đạt hạn.

### Timeout với fallback

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.<String>never()
            .timeout(Duration.ofSeconds(5))
            .onErrorReturn(TimeoutException.class, "fallback"))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(5))
    .expectNext("fallback")
    .verifyComplete();
~~~

Trong trường hợp này, timeout không xuất hiện như terminal error vì onErrorReturn chuyển nó thành onNext rồi onComplete. Đây là ví dụ kiểm tra **hợp đồng của operator composition**, không chỉ kiểm tra timer riêng lẻ.

### Không nhầm timeout nội bộ và verification timeout

Hai loại timeout khác nhau:

- Mono.timeout(Duration): logic nghiệp vụ của Publisher, có thể dùng virtual clock.
- StepVerifier.verify(Duration): thời hạn theo thời gian thực để verifier không treo vô hạn.

Ví dụ:

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofDays(10)))
    .expectSubscription()
    .thenAwait(Duration.ofDays(10))
    .expectNext(0L)
    .expectComplete()
    .verify(Duration.ofSeconds(5));
~~~

Test mô phỏng 10 ngày, nhưng giới hạn tối đa 5 giây thực cho việc verify. Giá trị 5 giây là guard phù hợp với CI chứ không phải một phần của logic 10 ngày.

## 13. Retry với backoff được kiểm thử như thế nào?

Retry có backoff là một tình huống kinh điển cần virtual time. Một request có thể retry lần đầu sau 1 giây, lần tiếp theo sau 2 giây và cuối cùng thành công.

Ví dụ supplier tạo workflow mới trong virtual scheduler:

~~~java
AtomicInteger attempts = new AtomicInteger();

StepVerifier.withVirtualTime(() ->
        Mono.defer(() -> {
                int attempt = attempts.incrementAndGet();
                return attempt < 3
                    ? Mono.<String>error(
                        new IllegalStateException("temporary"))
                    : Mono.just("ok");
            })
            .retryWhen(
                Retry.backoff(2, Duration.ofSeconds(1))
                    .jitter(0d)))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(3))
    .expectNext("ok")
    .verifyComplete();

assertEquals(3, attempts.get());
~~~

Giải thích:

1. Subscription đầu tiên tăng attempts lên 1 và phát lỗi.
2. Retry.backoff(2, ...) cho tối đa hai lần retry.
3. Lần retry đầu đến sau 1 giây.
4. Lần retry tiếp đến sau 2 giây nữa.
5. Đến thời điểm 3 giây ảo, attempts = 3 và kết quả là ok.
6. jitter(0d) tắt độ ngẫu nhiên cho lịch test có tính xác định.

Nếu giữ jitter mặc định, thời gian của từng retry có thể thay đổi trong giới hạn jitter, khiến assertion đúng 3 giây trở nên không ổn định. Với production, jitter hữu ích để tránh thundering herd; chỉ tắt nó trong test cần lịch chính xác.

### Đừng tạo retry publisher từ trước

Không tạo toàn bộ pipeline retryWhen trước khi withVirtualTime thiết lập scheduler rồi chỉ trả publisher đó. Retry có thể chọn scheduler tại thời điểm assembly. Hãy đặt cả retryWhen trong lambda hoặc một service method được gọi từ lambda.

## 14. Kiểm thử giới hạn theo khoảng thời gian

Các operator như take(Duration), skip(Duration), bufferTimeout, windowTimeout và debounce có thể phụ thuộc scheduler. Ví dụ giới hạn một stream bằng take(Duration):

~~~java
StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofSeconds(1))
            .take(Duration.ofMillis(3500))
            .map(n -> "tick-" + n))
    .expectSubscription()
    .thenAwait(Duration.ofMillis(3500))
    .expectNext("tick-0", "tick-1", "tick-2")
    .verifyComplete();
~~~

Trace mong đợi:

~~~text
t=1s: tick-0
t=2s: tick-1
t=3s: tick-2
t=3.5s: onComplete do take(Duration)
~~~

Thời điểm task cùng timestamp có thể cần xem operator semantics. Một bài kiểm thử production nên thể hiện đúng boundary cần quan tâm, ví dụ “không có tick sau 3,5 giây”, thay vì phụ thuộc thứ tự ngẫu nhiên của các task không liên quan.

### Debounce và window time

Khi kiểm thử debounce, phải chắc chắn source phát sự kiện ở **những timestamp được kiểm soát**. Nếu dùng Flux.just rồi debounce(Duration) mà không có khoảng cách thời gian, mọi giá trị có thể phát tức thời và chỉ giá trị cuối được giữ lại.

Khi kiểm thử windowTimeout hoặc bufferTimeout, cần xét cả kích thước buffer và ranh giới thời gian; chỉ tiến clock không đảm bảo cửa sổ đã nhận dữ liệu nếu subscription tới inner publisher hoặc demand chưa được thiết lập.

## 15. VirtualTimeScheduler sử dụng thủ công

withVirtualTime phù hợp cho phần lớn test. Đôi khi code truyền Scheduler tường minh và bạn muốn điều khiển chính xác clock đó mà không thay factory toàn cục.

Ví dụ:

~~~java
VirtualTimeScheduler clock = VirtualTimeScheduler.create();

try {
    Flux<Long> events =
        Flux.interval(Duration.ofSeconds(2), clock)
            .take(2);

    StepVerifier.create(events)
        .expectSubscription()
        .then(() ->
            clock.advanceTimeBy(Duration.ofSeconds(2)))
        .expectNext(0L)
        .then(() ->
            clock.advanceTimeBy(Duration.ofSeconds(2)))
        .expectNext(1L)
        .verifyComplete();
} finally {
    clock.dispose();
}
~~~

Giải thích:

- VirtualTimeScheduler.create() tạo scheduler nhưng chưa thay các global Schedulers factories.
- Flux.interval(Duration, Scheduler) nhận trực tiếp clock.
- StepVerifier.create đăng ký pipeline theo cách bình thường.
- then(Runnable) gọi advanceTimeBy sau khi subscription đã được thiết lập.
- Clock chạy các task đến hạn và verifier đọc được signal.
- finally đóng clock để tránh giữ tài nguyên qua các test.

Nếu source được viết để nhận Scheduler qua constructor, đây là một thiết kế có lợi cho unit testing:

~~~java
public final class ScheduledAlerts {

    private final Scheduler scheduler;

    public ScheduledAlerts(Scheduler scheduler) {
        this.scheduler = scheduler;
    }

    public Flux<Long> ticks() {
        return Flux.interval(Duration.ofSeconds(2), scheduler);
    }
}
~~~

Trong production, inject scheduler thực. Trong test, inject VirtualTimeScheduler rồi tiến clock thủ công.

## 16. withVirtualTime và scheduler custom

withVirtualTime thay thế các scheduler được lấy từ các factory mặc định của Reactor. Nó không tự động thay thế mọi Scheduler custom.

Ví dụ vấn đề:

~~~java
Scheduler explicitScheduler = Schedulers.newSingle("external");

Flux<Long> stream = Flux.interval(
    Duration.ofSeconds(1),
    explicitScheduler);
~~~

Nếu explicitScheduler được tạo trước rồi truyền vào Flux.interval, withVirtualTime không kiểm soát được nó. Test tiến thời gian ảo nhưng operator vẫn hẹn giờ trên thread/scheduler thực.

Cách tốt hơn:

- Truyền Scheduler dưới dạng dependency để test có thể inject VirtualTimeScheduler.
- Hoặc tránh truyền scheduler tùy chỉnh khi không cần và tạo operator **trong supplier** để dùng scheduler mặc định đã được virtual hóa.
- Hoặc sử dụng biến thể withVirtualTime hỗ trợ supplier của VirtualTimeScheduler khi cần kiểm soát instance scheduler.

Không giả định rằng chỉ cần đặt một lambda quanh publisher là mọi timer ở mọi thư viện sẽ được thay thế.

### withVirtualTime có tạo một “thời gian riêng” cho mọi thread không?

Không. VirtualTimeScheduler thay đổi cách các Scheduler mặc định của Reactor được cung cấp trong thời gian test. Nhiều operator có thể cùng dùng một virtual clock. Điều này khác với việc điều chỉnh java.time.Clock cho từng thread và có thể ảnh hưởng các test khác chạy song song.

## 17. Kiểm thử backpressure với virtual time

StepVerifier có overload withVirtualTime(Supplier, long initialRequest) để kiểm soát demand ban đầu.

Ví dụ:

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofSeconds(1)).take(2),
        0)
    .expectSubscription()
    .thenRequest(1)
    .thenAwait(Duration.ofSeconds(1))
    .expectNext(0L)
    .thenRequest(1)
    .thenAwait(Duration.ofSeconds(1))
    .expectNext(1L)
    .verifyComplete();
~~~

Giải thích:

- initialRequest = 0: chưa yêu cầu phần tử.
- thenRequest(1): yêu cầu một phần tử trước tick đầu.
- thenAwait(1 giây): tiến đến tick 0.
- thenRequest(1): mở thêm một đơn vị demand.
- thenAwait(1 giây): tiến đến tick 1.
- take(2) hoàn tất sau hai giá trị.

Flux.interval có thể phát lỗi overflow nếu đến tick mà downstream chưa yêu cầu đủ. Đây là một thuộc tính có ý nghĩa khi kiểm thử pressure, không phải lỗi của virtual time.

### Backpressure và đồng hồ ảo là hai trục khác nhau

Virtual time điều khiển **khi nào task chạy**. Request demand điều khiển **publisher được phép phát bao nhiêu phần tử**. Một test đúng phải đáp ứng cả hai. Nếu clock đã tiến nhưng không có demand, interval có thể không phát hoặc lỗi; nếu có demand nhưng clock chưa tiến, interval chưa có tick.

Đừng dùng withVirtualTime như cách bỏ qua Reactive Streams backpressure.

## 18. Khi nào expectNextCount, thenCancel hoặc verifyThenAssertThat hữu ích?

Khi kiểm thử nhiều phần tử cùng format:

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofSeconds(1)).take(100))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(100))
    .expectNextCount(100)
    .verifyComplete();
~~~

expectNextCount kiểm tra đủ số phần tử nhưng không kiểm tra value. Nếu giá trị hoặc thứ tự có ý nghĩa, dùng expectNext hoặc assertNext.

Đối với publisher không có điểm dừng:

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofSeconds(1)))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(2))
    .expectNext(0L, 1L)
    .thenCancel()
    .verify();
~~~

verifyThenAssertThat hữu ích nếu bạn cần kiểm tra thêm dropped elements hoặc các trạng thái sau khi verifier đã phát lại scenario. Chỉ sử dụng khi mục tiêu test thực sự cần loại post-execution assertion này; không cần kết hợp với mọi bài kiểm thử thời gian.

### expectNext khi clock chưa tiến

Nếu source có timer, cách viết sau dễ treo:

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofDays(1)))
    .expectSubscription()
    .expectNext(0L)
    .verifyComplete();
~~~

Ở đây verifier chờ onNext trước khi clock được tiến. Không có onNext nên không tới bước hoàn tất. Cần thêm thenAwait hoặc expectNoEvent trước expectNext.

## 19. Thiết lập verification timeout thực

Virtual test có thể treo vì source thật bị blocking, custom scheduler không được thay, hoặc thiếu thenAwait. Để không làm CI treo vô hạn, thêm timeout thực:

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofDays(30)))
    .expectSubscription()
    .thenAwait(Duration.ofDays(30))
    .expectNext(0L)
    .expectComplete()
    .verify(Duration.ofSeconds(5));
~~~

Đây là mô hình an toàn: bài test mô phỏng 30 ngày nhưng phải hoàn tất trong 5 giây wall-clock.

StepVerifier còn có timeout mặc định có thể được cấu hình cho một test suite. Tuy nhiên, thay static default timeout toàn cục có thể ảnh hưởng các test khác; hãy ưu tiên verify(Duration) tại test nếu cần quy tắc cụ thể.

Nếu timeout thực bị chạm, hãy kiểm tra:

1. Publisher có được tạo trong supplier không?
2. Có scheduler custom được tạo trước không?
3. Có Thread.sleep, I/O thật hoặc blocking source không?
4. Có thiếu thenAwait/expectNoEvent để tiến clock không?
5. Có publisher vô hạn mà lại dùng verifyComplete không?
6. Có demand đủ cho Flux.interval không?
7. Có một operator trong flatMap chưa kịp đăng ký timer khi clock được tiến không?

Đừng sửa đơn thuần bằng tăng verification timeout lên nhiều phút. Trước tiên hãy xác định vì sao sự kiện không xuất hiện.

## 20. Thời gian ảo và inner publisher trong flatMap

Một trường hợp phức tạp: Flux bên ngoài phát phần tử rồi flatMap tạo một inner publisher có timer.

~~~java
Flux<String> source = Flux.just("A", "B")
    .flatMap(value ->
        Mono.delay(Duration.ofSeconds(5))
            .map(tick -> value));
~~~

Nếu source được tạo trong supplier, scheduler có thể được virtual hóa. Tuy nhiên, khi dùng StepVerifier.thenAwait một bước rất lớn, việc tạo inner publisher, thứ tự đăng ký timer và tiến clock có thể không giống một chương trình tuyến tính đơn giản.

Theo Javadoc StepVerifier, virtual time có thể không tương thích trong vài trường hợp inner delay được lập lịch sau khi clock đã tiến, khiến sự kiện mong đợi không xuất hiện.

Cách viết test rõ hơn là cho source phát phần tử và tiến đồng hồ theo từng chặng:

~~~java
StepVerifier.withVirtualTime(() ->
        Flux.just("A", "B")
            .flatMap(value ->
                Mono.delay(Duration.ofSeconds(5))
                    .map(tick -> value)))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(5))
    .expectNextCount(2)
    .verifyComplete();
~~~

Do Flux.just phát A và B đồng bộ ngay khi subscribe, hai inner timer được đăng ký trước khi tiến 5 giây. Với nguồn chậm hoặc hot producer, cần xây dựng kịch bản dựa trên thời điểm thực sự subscribe tới từng inner publisher.

Nếu thứ tự A/B là bắt buộc, thay flatMap bằng concatMap và tiến thời gian đủ cho hai inner publishers tuần tự:

~~~java
StepVerifier.withVirtualTime(() ->
        Flux.just("A", "B")
            .concatMap(value ->
                Mono.delay(Duration.ofSeconds(5))
                    .map(tick -> value)))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(5))
    .expectNext("A")
    .thenAwait(Duration.ofSeconds(5))
    .expectNext("B")
    .verifyComplete();
~~~

Ở đây B được xử lý sau A; tổng thời gian ảo là 10 giây. Sự khác biệt xuất phát từ semantics flatMap và concatMap, không phải tính ngẫu nhiên của test.

## 21. Các ranh giới mà virtual time không kiểm soát

VirtualTimeScheduler không sửa đồng hồ hệ điều hành và không thay mọi nguồn thời gian của JVM.

| Thao tác | Có tự dùng virtual time không? | Cách test phù hợp |
| --- | --- | --- |
| Mono.delay với scheduler mặc định được tạo trong supplier | Có | withVirtualTime |
| Flux.interval với scheduler mặc định được tạo trong supplier | Có | withVirtualTime |
| delayElements với scheduler mặc định phù hợp | Thường có | withVirtualTime |
| retryWhen dùng Reactor scheduler mặc định đúng thời điểm | Có thể | withVirtualTime, tắt jitter để cố định |
| Publisher dùng Scheduler custom đã tạo trước | Không tự động | Inject VirtualTimeScheduler tường minh |
| Thread.sleep | Không | Refactor bỏ sleep, inject scheduler |
| java.time.Clock.systemUTC() | Không | Inject java.time.Clock giả lập |
| System.currentTimeMillis() | Không | Inject Clock hoặc time provider |
| Real HTTP/WebClient network delay | Không | MockWebServer, fake transport, test riêng |
| Database TTL/Redis expiration thật | Không | Integration test có cấu hình môi trường phù hợp |
| Cron scheduler của hệ thống khác | Không tự động | Test scheduling component riêng |
| CompletableFuture.delayedExecutor ngoài Reactor | Không tự động | Inject executor/clock phù hợp |

Ví dụ nếu business logic so sánh Instant.now() với deadline, chỉ cài StepVerifier.withVirtualTime không thay Instant.now(). Hãy truyền java.time.Clock vào service:

~~~java
public final class ExpiryPolicy {

    private final Clock clock;

    public ExpiryPolicy(Clock clock) {
        this.clock = clock;
    }

    public boolean expired(Instant deadline) {
        return !Instant.now(clock).isBefore(deadline);
    }
}
~~~

Trong unit test có thể dùng Clock.fixed hoặc Clock.offset. Đây là một vấn đề khác với timer Scheduler của Reactor. Hai cơ chế có thể được phối hợp nếu một ứng dụng vừa dùng business clock vừa dùng operator time-based.

## 22. Project thực hành Java 17+ với Maven và JUnit 5

Dự án dưới đây là bộ unit test Reactor chạy được bằng Maven. Nó không cần khởi động một WebFlux HTTP server vì mục tiêu là kiểm tra các toán tử của Reactor một cách cô lập. Parent Spring Boot 3.3.5 quản lý phiên bản Reactor tương thích với hệ sinh thái Spring Framework.

### Cấu trúc thư mục

~~~text
reactor-virtual-time-demo/
├── pom.xml
└── src
    ├── main/java/com/example/virtualtime
    │   └── TimeBasedService.java
    └── test/java/com/example/virtualtime
        └── VirtualTimeExamplesTest.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>reactor-virtual-time-demo</artifactId>
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
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### TimeBasedService.java

~~~java
package com.example.virtualtime;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

public class TimeBasedService {

    public Flux<String> heartbeat(int count) {
        return Flux.interval(Duration.ofSeconds(10))
            .take(count)
            .map(index -> "heartbeat-" + index);
    }

    public Mono<String> delayedNotice() {
        return Mono.just("ready")
            .delayElement(Duration.ofMinutes(5));
    }

    public Mono<String> expireAndFallback() {
        return Mono.<String>never()
            .timeout(Duration.ofSeconds(5))
            .onErrorReturn(
                TimeoutException.class, "fallback");
    }

    public Mono<String> retryThenSucceed(
            AtomicInteger attempts) {

        return Mono.defer(() -> {
                int attempt = attempts.incrementAndGet();
                if (attempt < 3) {
                    return Mono.<String>error(
                        new IllegalStateException(
                            "attempt-" + attempt));
                }
                return Mono.just("ok");
            })
            .retryWhen(
                Retry.backoff(2, Duration.ofSeconds(1))
                    .jitter(0d));
    }

    public Flux<String> ticksInWindow() {
        return Flux.interval(Duration.ofSeconds(1))
            .take(Duration.ofMillis(3500))
            .map(index -> "tick-" + index);
    }
}
~~~

Chú ý phương thức heartbeat() tạo Flux.interval **khi method được gọi**, không tạo ở constructor hay static field. Mỗi test sẽ gọi service.heartbeat(...) từ Supplier mà withVirtualTime nhận.

### VirtualTimeExamplesTest.java — các ca kiểm thử

~~~java
package com.example.virtualtime;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.test.scheduler.VirtualTimeScheduler;

class VirtualTimeExamplesTest {

    private final TimeBasedService service =
        new TimeBasedService();

    @Test
    void oneDayDelayEmitsWithoutWaitingOneRealDay() {
        StepVerifier.withVirtualTime(
                () -> Mono.delay(Duration.ofDays(1)))
            .expectSubscription()
            .expectNoEvent(Duration.ofDays(1))
            .expectNext(0L)
            .verifyComplete();
    }

    @Test
    void serviceCreatesTimeOperatorAfterVirtualSetup() {
        StepVerifier.withVirtualTime(
                () -> service.heartbeat(3))
            .expectSubscription()
            .expectNoEvent(Duration.ofSeconds(10))
            .expectNext("heartbeat-0")
            .thenAwait(Duration.ofSeconds(10))
            .expectNext("heartbeat-1")
            .thenAwait(Duration.ofSeconds(10))
            .expectNext("heartbeat-2")
            .verifyComplete();
    }

    @Test
    void delayedElementUsesVirtualClock() {
        StepVerifier.withVirtualTime(
                service::delayedNotice)
            .expectSubscription()
            .thenAwait(Duration.ofMinutes(5))
            .expectNext("ready")
            .verifyComplete();
    }

    @Test
    void timeoutFiresAtVirtualDeadline() {
        StepVerifier.withVirtualTime(() ->
                Mono.<String>never()
                    .timeout(Duration.ofSeconds(5)))
            .expectSubscription()
            .expectNoEvent(Duration.ofSeconds(4))
            .thenAwait(Duration.ofSeconds(1))
            .expectError(TimeoutException.class)
            .verify();
    }

    @Test
    void timeoutFallbackIsDecodedAsValue() {
        StepVerifier.withVirtualTime(
                service::expireAndFallback)
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(5))
            .expectNext("fallback")
            .verifyComplete();
    }

    @Test
    void retryBackoffUsesDeterministicVirtualTime() {
        AtomicInteger attempts = new AtomicInteger();

        StepVerifier.withVirtualTime(
                () -> service.retryThenSucceed(attempts))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(3))
            .expectNext("ok")
            .verifyComplete();

        assertEquals(3, attempts.get());
    }

    @Test
    void takeDurationEndsStreamAtConfiguredWindow() {
        StepVerifier.withVirtualTime(
                service::ticksInWindow)
            .expectSubscription()
            .thenAwait(Duration.ofMillis(3500))
            .expectNext(
                "tick-0", "tick-1", "tick-2")
            .verifyComplete();
    }

    @Test
    void infiniteIntervalIsCancelledAfterThreeTicks() {
        StepVerifier.withVirtualTime(() ->
                Flux.interval(Duration.ofMinutes(1)))
            .expectSubscription()
            .thenAwait(Duration.ofMinutes(3))
            .expectNext(0L, 1L, 2L)
            .thenCancel()
            .verify();
    }

    @Test
    void controlledDemandWorksWithVirtualTime() {
        StepVerifier.withVirtualTime(
                () -> Flux.interval(Duration.ofSeconds(1))
                    .take(2),
                0)
            .expectSubscription()
            .thenRequest(1)
            .thenAwait(Duration.ofSeconds(1))
            .expectNext(0L)
            .thenRequest(1)
            .thenAwait(Duration.ofSeconds(1))
            .expectNext(1L)
            .verifyComplete();
    }

    @Test
    void explicitSchedulerCanAdvanceManually() {
        VirtualTimeScheduler clock =
            VirtualTimeScheduler.create();

        try {
            Flux<Long> events =
                Flux.interval(Duration.ofSeconds(2), clock)
                    .take(2);

            StepVerifier.create(events)
                .expectSubscription()
                .then(() ->
                    clock.advanceTimeBy(
                        Duration.ofSeconds(2)))
                .expectNext(0L)
                .then(() ->
                    clock.advanceTimeBy(
                        Duration.ofSeconds(2)))
                .expectNext(1L)
                .verifyComplete();
        } finally {
            clock.dispose();
        }
    }

    @Test
    void namedScenarioHasWallClockVerificationGuard() {
        StepVerifier.withVirtualTime(
                () -> Mono.delay(Duration.ofDays(2)),
                StepVerifierOptions.create()
                    .scenarioName("two-day-delay"))
            .expectSubscription()
            .thenAwait(Duration.ofDays(2))
            .expectNext(0L)
            .expectComplete()
            .verify(Duration.ofSeconds(5));
    }

    @Test
    void supplierIsInvokedDuringVirtualScenarioSetup() {
        AtomicInteger assemblies = new AtomicInteger();

        StepVerifier.withVirtualTime(() -> {
                assemblies.incrementAndGet();
                return Mono.delay(
                    Duration.ofSeconds(20));
            })
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(20))
            .expectNext(0L)
            .verifyComplete();

        assertEquals(1, assemblies.get());
    }
}
~~~

Các test này không cần gọi Thread.sleep. Chúng dùng một trong hai cách:

- withVirtualTime tạo publisher sau khi Reactor cài scheduler ảo.
- VirtualTimeScheduler.create tạo clock tường minh và truyền vào Flux.interval(..., clock).

### Chạy project

Cần Java 17+ và Maven 3.8+ trong môi trường có thể tải dependencies:

~~~bash
java -version
mvn -version
mvn -q clean test
~~~

Khi toàn bộ 12 test pass, Maven trả exit code 0. Tùy logging cấu hình, chạy Maven không có -q để đọc test summary:

~~~bash
mvn test
~~~

Một đoạn summary mong đợi khi tất cả test pass:

~~~text
Tests run: 12, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Đây là output **mang tính minh họa**; số dòng log, thứ tự và thời lượng phụ thuộc môi trường Maven. Không diễn giải nó là kết quả test đã thực thi trong môi trường hiện tại.

## 23. Đọc từng test: kịch bản và kết quả

### Test 1 — một ngày ảo

oneDayDelayEmitsWithoutWaitingOneRealDay kiểm tra Mono.delay một ngày. Nó xác nhận không có signal trước ngày ảo rồi nhận Long 0.

Kết quả logic:

~~~text
subscribe -> no event for 1 virtual day -> onNext(0) -> onComplete
~~~

### Test 2 — tạo publisher bên trong Supplier

serviceCreatesTimeOperatorAfterVirtualSetup kiểm tra ba heartbeat. Giá trị đầu ở giây thứ 10, giá trị tiếp ở giây 20 và 30. Đây là minh chứng trực tiếp cho chủ đề bài học: gọi service.heartbeat(3) trong supplier giúp dựng Flux.interval sau khi scheduler ảo đã có.

### Test 3 — delayElement

delayedElementUsesVirtualClock gọi method reference service::delayedNotice. Method chỉ được thực thi khi StepVerifier thiết lập scenario, nên delayElement dùng scheduler phù hợp.

### Test 4 và 5 — timeout

timeoutFiresAtVirtualDeadline kiểm tra lỗi TimeoutException tại 5 giây. timeoutFallbackIsDecodedAsValue kiểm tra toán tử xử lý lỗi biến nó thành String fallback. Hai test có cùng nguồn không phát dữ liệu nhưng khác hợp đồng output.

### Test 6 — retry backoff

retryBackoffUsesDeterministicVirtualTime tắt jitter và xác nhận attempts = 3. Nếu quên jitter(0d), mốc 3 giây có thể không còn chính xác.

### Test 7 — take(Duration)

takeDurationEndsStreamAtConfiguredWindow phát tick tại 1, 2, 3 giây rồi complete ở 3,5 giây, không đợi đến giây thứ 4.

### Test 8 — cancellation

infiniteIntervalIsCancelledAfterThreeTicks không đòi onComplete từ Flux vô hạn. thenCancel mô tả hành vi tiêu thụ hữu hạn một stream không có natural completion.

### Test 9 — demand

controlledDemandWorksWithVirtualTime thể hiện clock và request(n) là hai điều kiện độc lập. Nếu không yêu cầu thêm phần tử kịp thời, interval có thể lỗi overflow.

### Test 10 — clock thủ công

explicitSchedulerCanAdvanceManually không cần thay global factory; clock được truyền trực tiếp vào operator và StepVerifier.create gọi advanceTimeBy qua then(Runnable).

### Test 11 — timeout thực

namedScenarioHasWallClockVerificationGuard dùng hai ngày thời gian ảo, nhưng verification phải hoàn tất trong 5 giây thực. Scenario name giúp đọc thông báo thất bại.

### Test 12 — supplier được thực thi sau setup

supplierIsInvokedDuringVirtualScenarioSetup đếm số lần lambda được gọi, khẳng định kịch bản được tạo trong ngữ cảnh thiết lập của verifier. Không dùng một publisher cache sẵn để vượt qua cơ chế tạo lazy.

## 24. Trường hợp cần dùng StepVerifierOptions

StepVerifierOptions hỗ trợ cấu hình bổ sung cho scenario, ví dụ tên test và virtual scheduler supplier trong overload phù hợp.

Ví dụ đặt tên scenario:

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofSeconds(1))
            .take(2),
        StepVerifierOptions.create()
            .scenarioName("heartbeat-second-by-second"))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(2))
    .expectNext(0L, 1L)
    .verifyComplete();
~~~

Scenario name đặc biệt hữu ích khi nhiều StepVerifier cùng có các assertion gần giống nhau. Tên này hỗ trợ chẩn đoán failure, không thay đổi semantics của publisher.

Nếu cần điều khiển lượng request ban đầu, withVirtualTime(supplier, long initialRequest) là lựa chọn trực tiếp. Với kịch bản chuyên biệt cần scheduler riêng, có overload nhận supplier của VirtualTimeScheduler và lượng request, hoặc nhận StepVerifierOptions có virtualTimeSchedulerSupplier.

Khi dùng overload tùy chỉnh, cần đảm bảo scheduler được cung cấp thật sự là clock mà các timed operators của kịch bản sử dụng. Không tạo hai instance khác nhau rồi tiến một clock trong khi operator đang hẹn giờ trên clock còn lại.

## 25. Race condition và nhiễu giữa các test

withVirtualTime thay scheduler factories ở mức process của Reactor trong thời gian test. Vì vậy có các rủi ro:

- Test A cài virtual clock trong khi test B đang dùng time operators mặc định.
- Một singleton tạo interval khi Test A đã cài virtual scheduler, rồi được dùng sau khi scheduler đã reset.
- Một test chạy song song khiến thời gian ảo tiến ngoài dự kiến của test khác.
- Một custom Scheduler tiếp tục tồn tại sau khi test kết thúc.
- Test không dọn clock sau khi đặt global factory thủ công.

Khuyến nghị:

1. Không chạy song song các virtual-time tests đụng global scheduler factory mà không có chiến lược cô lập.
2. Tạo time-dependent publisher bên trong mỗi scenario supplier.
3. Tránh static Flux.interval/Mono.delay được assembly ở class initialization.
4. Ưu tiên test riêng cho logic time-based, thay vì dùng virtual clock trong integration test có HTTP/network thật.
5. Nếu tự tạo VirtualTimeScheduler, dispose trong finally hoặc @AfterEach.
6. Nếu thay global scheduler bằng VirtualTimeScheduler.getOrSet hoặc set thủ công, phải restore/reset đúng lifecycle; với StepVerifier.withVirtualTime, để framework quản lý setup/cleanup theo API.
7. Tách unit test về thời gian khỏi load test/performance test.

Không tự gọi Schedulers.resetFactory() bừa bãi khi test khác còn sử dụng scheduler. Cấu hình test parallel và lifecycle phải được thiết kế ở cấp project.

## 26. Những lỗi thường gặp và cách khắc phục

1. **Tạo Flux.interval trước withVirtualTime.** Publisher có thể giữ scheduler thật; tạo nó bên trong Supplier.
2. **Supplier chỉ trả publisher cache sẵn.** Không đảm bảo tính lazy; đưa time operator vào factory/method được gọi trong lambda.
3. **Đặt expectNoEvent ở bước đầu.** onSubscribe cũng là event; thêm expectSubscription trước.
4. **Quên thenAwait.** Không có clock advancement, timer không chạy và verifier có thể treo.
5. **Nhầm thenAwait với expectNoEvent.** thenAwait không khẳng định sự im lặng; expectNoEvent kiểm tra không có signal.
6. **Dùng Thread.sleep trong virtual test.** Nó chỉ chờ thời gian thực; dùng thenAwait hoặc advanceTimeBy.
7. **Dùng Scheduler custom tạo trước.** withVirtualTime không tự kiểm soát; inject VirtualTimeScheduler trực tiếp.
8. **Dùng publisher vô hạn và verifyComplete.** Không có completion; dùng take(n), thenCancel hoặc timeout hợp đồng rõ ràng.
9. **Tiến clock quá xa ở interval dày đặc.** Có thể kích hoạt lượng lớn task; giới hạn số sự kiện và khoảng thời gian.
10. **Đọc thời gian bằng Instant.now() và nghĩ đó là virtual clock.** Inject java.time.Clock cho logic wall-clock.
11. **Kiểm thử socket timeout thật bằng virtual time.** OS/network có timer riêng; dùng integration test hoặc fake transport.
12. **Quên initial demand.** Flux.interval có thể overflow; thiết lập thenRequest đúng thời điểm.
13. **Dùng Retry.backoff có jitter khi assert timestamp tuyệt đối.** Tắt jitter trong test cần lịch cố định.
14. **Viết retry publisher bên ngoài supplier.** Retry có thể giữ scheduler được chọn trước; dựng trong lambda.
15. **Dùng flatMap với inner delay và một bước thenAwait quá sớm.** Inner timer có thể chưa được lên lịch; chia bước hoặc kiểm tra operator semantics.
16. **Dùng concatMap rồi đòi kết quả của hai inner publisher ở cùng timestamp.** ConcatMap xử lý tuần tự; phải tiến đủ thời gian cho từng inner.
17. **Đặt verify() không có guard khi test dễ treo.** Dùng expectComplete().verify(Duration) để giới hạn wall-clock.
18. **Nâng verification timeout quá cao thay vì sửa scheduler.** Tìm root cause: eager assembly, custom scheduler, blocking I/O.
19. **Chạy virtual-time tests song song thiếu cô lập.** Scheduler factory là shared process state; điều phối hoặc tách test.
20. **Không dọn VirtualTimeScheduler thủ công.** Có thể gây giữ tài nguyên và làm nhiễu test sau.
21. **Cho rằng virtual time mô phỏng chính xác performance.** Nó kiểm tra semantics thời gian, không phải tốc độ thực của scheduler, CPU, network hay DB.
22. **Kiểm tra theo tên thread.** Virtual time không có nghĩa bảo toàn thread identity; kiểm tra signal và timestamp logic.
23. **Dựa vào thứ tự task cùng hạn mà hợp đồng không yêu cầu.** Test có thể giòn; xác định chính xác ranh giới nghiệp vụ cần kiểm chứng.
24. **Bỏ qua cancellation/backpressure.** Có clock ảo vẫn phải mô tả demand và kết thúc subscription.

## 27. Checklist trước khi viết một virtual-time test

- Publisher có operator thời gian nào cần kiểm thử?
- Operator có dùng Scheduler mặc định do Reactor quản lý không?
- Publisher và những timed operators có được tạo trong Supplier không?
- Service có static/constructor field tạo Flux.interval từ trước không?
- Test có gọi service method từ supplier thay vì từ ngoài không?
- Có custom Scheduler đã tạo trước không?
- Nếu có, scheduler có được inject dưới dạng VirtualTimeScheduler không?
- Có expectSubscription trước expectNoEvent không?
- Mốc thenAwait có tiến đủ để timer cần kiểm chứng chạy không?
- Test có đòi sự im lặng trước mốc hay chỉ cần cho clock chạy?
- Kiểu dữ liệu của signal có chính xác không, ví dụ Mono.delay phát Long 0?
- Publisher có natural completion không?
- Nếu vô hạn, có take(n) hoặc thenCancel không?
- Có kiểm soát initialRequest/backpressure nếu cần không?
- Có bỏ Thread.sleep và blocking I/O khỏi virtual scenario không?
- Có sử dụng java.time.Clock riêng khi kiểm tra business wall-clock không?
- Có tắt jitter nếu kiểm tra retry schedule chính xác không?
- Có đặt wall-clock verification guard nếu kịch bản có nguy cơ treo không?
- Các virtual time tests có đang chạy đồng thời gây ảnh hưởng global scheduler không?
- Có cleanup scheduler nếu tạo thủ công không?
- Output/kết quả mong đợi có mô tả đúng thứ tự onNext/onError/onComplete không?

## 28. Bài tập tự kiểm tra

**Câu 1.** withVirtualTime nhận Publisher hay Supplier<Publisher>?  
**Đáp án:** Nó nhận Supplier<Publisher>, cho phép tạo publisher sau khi virtual scheduler đã được thiết lập.

**Câu 2.** Vì sao không nên tạo Flux.interval ngoài lambda?  
**Đáp án:** Operator có thể giữ scheduler thật từ lúc assembly; tiến clock ảo không kích hoạt nó.

**Câu 3.** Reactor Context có liên quan trực tiếp tới VirtualTimeScheduler không?  
**Đáp án:** Không. Reactor Context truyền dữ liệu theo subscriber; VirtualTimeScheduler điều khiển lịch thời gian của tasks.

**Câu 4.** thenAwait khác expectNoEvent ở đâu?  
**Đáp án:** Cả hai có thể tiến thời gian, nhưng expectNoEvent còn khẳng định không có signal trong khoảng.

**Câu 5.** Vì sao cần expectSubscription trước expectNoEvent?  
**Đáp án:** Vì onSubscribe được xem là event và sẽ khiến expectNoEvent ở bước đầu thất bại.

**Câu 6.** Mono.delay(Duration.ofSeconds(2)) phát giá trị gì?  
**Đáp án:** Long 0L sau 2 giây, rồi hoàn tất.

**Câu 7.** Flux.interval(Duration.ofSeconds(1)).take(3) phát khi nào?  
**Đáp án:** Long 0L, 1L, 2L ở giây 1, 2, 3 rồi hoàn tất.

**Câu 8.** Có thể tăng thời gian ảo bằng cách nào?  
**Đáp án:** thenAwait, expectNoEvent hoặc VirtualTimeScheduler.advanceTimeBy/advanceTimeTo.

**Câu 9.** Thread.sleep có làm clock ảo chạy không?  
**Đáp án:** Không, nó chỉ chặn thread thực.

**Câu 10.** verify(Duration.ofSeconds(5)) là timeout logic hay timeout verifier?  
**Đáp án:** Timeout của StepVerifier theo thời gian thực để tránh đợi lâu.

**Câu 11.** Retry.backoff có jitter nên xử lý thế nào nếu cần test timestamp chính xác?  
**Đáp án:** Tắt jitter bằng jitter(0d) trong test, không nhất thiết bỏ jitter ở production.

**Câu 12.** Vì sao cần thenCancel với interval vô hạn?  
**Đáp án:** Vì nguồn không tự complete; cancel là kết thúc hợp lệ của kịch bản.

**Câu 13.** Có thể dùng virtual time để kiểm thử java.time.Clock.systemUTC không?  
**Đáp án:** Không tự động; hãy inject Clock.fixed hoặc một clock fake.

**Câu 14.** Nếu source dùng Schedulers.newSingle tạo sẵn, withVirtualTime có thay nó không?  
**Đáp án:** Không đảm bảo; nên inject VirtualTimeScheduler hoặc refactor time operator.

**Câu 15.** Điều kiện quan trọng nhất để withVirtualTime đáng tin là gì?  
**Đáp án:** Time-dependent publisher phải được tạo sau khi virtual scheduler đã được kích hoạt, thường bằng cách xây dựng toàn bộ chain trong Supplier.

## 29. Ghi nhớ

StepVerifier.withVirtualTime thay scheduler factory mặc định của Reactor bằng VirtualTimeScheduler và cho phép kiểm thử các operator phụ thuộc thời gian mà không chờ wall-clock. API nhận Supplier để **tạo publisher sau khi scheduler ảo được thiết lập**. Một lambda chỉ trả về Flux đã tạo trước không đảm bảo hiệu quả; phải xây các operator như delay, interval, timeout hoặc retry trong supplier hoặc method factory được gọi từ supplier.

expectSubscription nên đứng trước expectNoEvent vì onSubscribe cũng là signal. thenAwait tiến thời gian nhưng không khẳng định không có event; expectNoEvent vừa tiến thời gian vừa kiểm tra im lặng. Nếu publisher vô hạn, dùng take hoặc thenCancel; nếu cần chặn test treo, dùng verify(Duration) làm wall-clock guard.

VirtualTimeScheduler chỉ quản lý công việc được lập lịch trên scheduler phù hợp. Nó không điều khiển Thread.sleep, thời gian hệ thống, network, database hay scheduler tùy chỉnh tạo trước. Có thể inject VirtualTimeScheduler và tiến clock thủ công để kiểm thử code nhận Scheduler tường minh. Để test ổn định, kiểm soát demand, retry jitter, inner publishers, lifecycle scheduler và parallel test interference.

### Tài liệu tham khảo

- Project Reactor, [Testing — Manipulating Time](https://projectreactor.io/docs/core/release/reference/testing.html#_manipulating_time).
- Project Reactor, [StepVerifier Javadoc](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html).
- Project Reactor, [VirtualTimeScheduler Javadoc](https://projectreactor.io/docs/test/release/api/reactor/test/scheduler/VirtualTimeScheduler.html).
- Project Reactor, [Reactor Core Reference](https://projectreactor.io/docs/core/release/reference/).
- Project Reactor, [Retry Javadoc](https://projectreactor.io/docs/core/release/api/reactor/util/retry/Retry.html).
- Spring Boot, [Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/).
