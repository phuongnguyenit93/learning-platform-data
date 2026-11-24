# `publishOn` hoặc `observeOn`: chuyển nơi xử lý tín hiệu phía sau

Trong một pipeline reactive, nguồn dữ liệu và các bước xử lý không nhất thiết chạy trên cùng một luồng thực thi. Có lúc ta muốn đọc dữ liệu trên luồng hiện tại, nhưng chuyển các bước xử lý phía sau sang một scheduler khác để cô lập phép tính CPU, tránh chặn event loop hoặc tách biệt công việc khỏi thread phát sự kiện. Reactor cung cấp `publishOn` cho mục đích này; RxJava có toán tử tương ứng về ý nghĩa là `observeOn`.

Điểm cốt lõi của hai toán tử là tạo một ranh giới thực thi: các tín hiệu đi qua ranh giới được lên lịch để xử lý ở phía downstream trên scheduler đã chọn. Những toán tử đứng trước ranh giới vẫn chạy theo luồng thực thi upstream. Vì vậy, vị trí đặt `publishOn` hoặc `observeOn` quyết định chính xác phần nào của pipeline được chuyển nơi xử lý.

Chủ đề này thuộc chương **Luồng thực thi** của REACTIVE_PROGRAMMING. Module học tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; đồng thời thực hành Mono, Flux, kết hợp toán tử, scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Khi chuyển nơi xử lý tín hiệu, cần hiểu ranh giới scheduler, hàng đợi và demand để tránh tạo thêm độ trễ hoặc áp lực bộ nhớ ngoài dự kiến.

## Ranh giới thực thi nằm tại vị trí toán tử

Trong Reactor, `publishOn(scheduler)` yêu cầu các tín hiệu downstream kể từ vị trí toán tử được xử lý thông qua scheduler đã chọn. Nó không chuyển ngược các toán tử upstream sang scheduler đó.

```java
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Schedulers;

Flux.range(1, 3)
    .map(value -> {
        logThread("before publishOn", value);
        return value * 10;
    })
    .publishOn(Schedulers.parallel())
    .map(value -> {
        logThread("after publishOn", value);
        return value + 1;
    })
    .subscribe(value -> logThread("subscriber", value));
```

Trong ví dụ:

- `Flux.range` và `map` đầu tiên phát tín hiệu trên luồng thực thi của nguồn đồng bộ, thường là luồng gọi `subscribe`.
- `publishOn` đưa việc xử lý tín hiệu tiếp theo sang worker của `Schedulers.parallel()`.
- `map` thứ hai và consumer cuối nhận tín hiệu ở phía downstream của ranh giới đó.

Có thể hình dung pipeline như sau:

```text
Luồng nguồn / upstream                    Scheduler downstream
─────────────────────────                  ─────────────────────
Flux.range
    │
    ▼
map trước publishOn
    │
    ▼
publishOn(parallel) ─────── xếp tín hiệu ───────► worker scheduler
                                                   │
                                                   ▼
                                            map sau publishOn
                                                   │
                                                   ▼
                                               subscribe
```

Ranh giới này không có nghĩa mỗi phần tử tạo một thread mới. Scheduler quản lý worker và việc thực thi tác vụ; nhiều phần tử có thể được xử lý nối tiếp qua cùng worker. `publishOn` cũng không tự làm phép tính chạy song song. Nó chuyển nơi xử lý downstream; muốn phân chia công việc thành nhiều tác vụ độc lập, cần thiết kế concurrency hoặc parallel rails riêng.

## Vị trí của `publishOn` thay đổi hành vi thế nào?

So sánh hai pipeline:

```java
Flux.range(1, 5)
    .publishOn(Schedulers.parallel())
    .map(this::transform)
    .filter(this::isAccepted);
```

Trong pipeline này, cả `map` và `filter` nằm sau `publishOn`, nên chúng xử lý tín hiệu qua scheduler đã chọn.

```java
Flux.range(1, 5)
    .map(this::transform)
    .filter(this::isAccepted)
    .publishOn(Schedulers.parallel())
    .map(this::buildResponse);
```

Ở pipeline thứ hai, `transform` và `isAccepted` chạy trước ranh giới; chỉ `buildResponse` cùng các bước sau nó được chuyển sang scheduler mới. Nếu `transform` là phép tính nặng, đặt `publishOn` sau `map` không giúp cô lập phép tính đó.

Một quy tắc thực hành hữu ích là đặt `publishOn` ngay trước nhóm thao tác cần đổi nơi thực thi. Điều này giúp người đọc nhìn thấy ranh giới rõ ràng và tránh chuyển scheduler nhiều lần không cần thiết.

## Nhiều `publishOn` tạo nhiều ranh giới

Một pipeline có thể có nhiều ranh giới thực thi nếu từng nhóm công việc cần scheduler khác nhau:

```java
Flux<Event> result = eventSource()
    .publishOn(Schedulers.parallel())
    .map(this::calculateDerivedValues)
    .publishOn(Schedulers.boundedElastic())
    .map(this::callLegacyBlockingLibrary)
    .publishOn(Schedulers.parallel())
    .map(this::formatResult);
```

Ví dụ minh họa ba nhóm công việc: tính toán CPU, gọi thư viện blocking và định dạng kết quả. Mỗi `publishOn` tạo một ranh giới chuyển nơi xử lý cho các bước sau nó. Trong ứng dụng thật, chỉ nên thêm ranh giới khi có lý do cụ thể; mỗi ranh giới có thể cần hàng đợi, prefetch và chi phí chuyển tác vụ.

Đặc biệt, `boundedElastic` phù hợp hơn `parallel` cho lời gọi blocking, nhưng vẫn cần giới hạn số tác vụ và timeout. Nếu thư viện blocking có thể mất nhiều thời gian hoặc mở kết nối tới dịch vụ ngoài, scheduler không thay thế giới hạn connection pool hoặc chính sách concurrency của dịch vụ đó.

## Phân biệt `publishOn` với `subscribeOn`

Hai toán tử thường được dùng cùng nhau nhưng có vai trò khác nhau:

| Toán tử | Tác động chính | Câu hỏi nó trả lời |
|---|---|---|
| `subscribeOn(scheduler)` | Điều khiển scheduler dùng để bắt đầu quá trình subscription và thực thi nguồn theo ngữ nghĩa của nguồn | Nguồn nên bắt đầu chạy ở đâu? |
| `publishOn(scheduler)` | Chuyển xử lý các tín hiệu downstream kể từ vị trí toán tử | Các bước phía sau nên chạy ở đâu? |

Ví dụ kết hợp:

```java
Mono.fromCallable(() -> legacyClient.loadRecord("R-42"))
    .subscribeOn(Schedulers.boundedElastic())
    .map(this::normalize)
    .publishOn(Schedulers.parallel())
    .map(this::calculateScore)
    .subscribe(this::storeResult);
```

`subscribeOn` đưa lời gọi blocking trong nguồn `fromCallable` sang `boundedElastic`. Khi nguồn phát kết quả, `publishOn` chuyển các bước `calculateScore` và consumer xuống `parallel`. Nếu bỏ `publishOn`, downstream thường tiếp tục trên thread đang phát tín hiệu từ nguồn; nếu bỏ `subscribeOn`, lời gọi blocking có thể chạy ngay trên thread thực hiện subscription.

Đặt nhiều `subscribeOn` trong cùng một chuỗi thường không tạo các ranh giới downstream như nhiều `publishOn`. Với mục tiêu chuyển một nhóm toán tử phía sau, hãy dùng `publishOn` tại vị trí nhóm đó bắt đầu.

## `observeOn` trong RxJava có ý nghĩa tương ứng

`observeOn` là tên toán tử được dùng trong RxJava. Nó cũng chuyển việc quan sát và xử lý các tín hiệu phía downstream sang một `Scheduler` kể từ vị trí xuất hiện trong chuỗi. Reactor không đặt tên toán tử này là `observeOn`; trong Reactor, hãy dùng `publishOn`.

Ví dụ với RxJava 3 `Flowable`:

```java
import io.reactivex.rxjava3.core.Flowable;
import io.reactivex.rxjava3.schedulers.Schedulers;

Flowable.range(1, 5)
    .map(value -> transform(value))
    .observeOn(Schedulers.computation(), false, 32)
    .map(value -> calculate(value))
    .subscribe(System.out::println);
```

`map(transform)` chạy trước `observeOn`; `map(calculate)` và consumer chạy ở phía scheduler `computation`. Overload này minh họa thêm hai tham số: `delayError` điều khiển cách xử lý lỗi khi còn phần tử đang chờ trong hàng đợi, còn `bufferSize` đặt kích thước prefetch/buffer cho ranh giới đó.

RxJava có cả `Flowable` và `Observable`. `Flowable` hỗ trợ backpressure theo Reactive Streams; `observeOn` của nó điều phối demand và buffer theo cơ chế backpressure. `Observable` không có giao thức `request(n)`, vì vậy `observeOn` của `Observable` không thể dùng demand để điều tiết nguồn. Nếu upstream phát nhanh hơn downstream trong một pipeline `Observable`, hàng đợi có thể tăng và gây áp lực bộ nhớ. Hãy chọn kiểu nguồn đúng với khả năng điều tiết dữ liệu của ứng dụng.

## `publishOn` tạo ranh giới hàng đợi và phối hợp backpressure

Khi chuyển tín hiệu sang một scheduler khác, upstream và downstream không còn xử lý trực tiếp trên cùng một call stack. Reactor cần điều phối tín hiệu qua ranh giới bất đồng bộ. Với `Flux`, `publishOn` dùng hàng đợi nội bộ và prefetch để lấy dữ liệu từ upstream rồi chuyển dần tới downstream.

```text
Upstream             Hàng đợi publishOn              Downstream
   │                         │                            │
   ├──── onNext(A) ─────────►│                            │
   ├──── onNext(B) ─────────►│                            │
   ├──── onNext(C) ─────────►│──── phát A ───────────────►│ xử lý A
   │                         │──── phát B ───────────────►│ xử lý B
   │                         │──── phát C ───────────────►│ xử lý C
```

`publishOn(scheduler, prefetch)` cho phép chỉ định số phần tử được prefetch tại ranh giới. Khi downstream tiêu thụ dữ liệu, Reactor bổ sung demand upstream theo cơ chế replenishment. Vì vậy, `publishOn` vẫn tham gia vào backpressure; nó không đơn giản là một queue không giới hạn nhận mọi phần tử.

Tuy nhiên, prefetch lớn hơn làm tăng lượng dữ liệu có thể được giữ tạm thời. Nếu mỗi phần tử có payload lớn, nhiều subscription cùng dùng `publishOn`, hoặc downstream bị chặn lâu, tổng bộ nhớ dành cho các hàng đợi có thể đáng kể. Chọn prefetch theo kích thước phần tử, throughput và độ trễ thực tế; không tăng prefetch chỉ để che giấu consumer chậm.

Ví dụ giới hạn prefetch:

```java
Flux<Event> processed = eventSource()
    .publishOn(Schedulers.parallel(), 64)
    .map(this::transform);
```

Ở đây, `64` là prefetch được cấu hình cho ranh giới `publishOn`. Đây không phải giới hạn tổng số phần tử trong toàn ứng dụng và cũng không phải giới hạn tốc độ theo giây. Các operator khác như `flatMap`, `buffer` hoặc adapter nguồn có thể có hàng đợi riêng.

Với nguồn push-only không thể dừng theo demand, adapter ở ranh giới nguồn vẫn cần chính sách buffer/overflow riêng. `publishOn` không thể ép một thư viện callback bên ngoài ngừng phát nếu API gốc không hỗ trợ flow control.

## Thứ tự tín hiệu được giữ trong một luồng

`publishOn` chuyển việc xử lý tín hiệu nhưng vẫn giữ thứ tự phát của một subscription. Nếu upstream phát `A`, `B`, `C`, downstream qua một ranh giới `publishOn` quan sát chúng theo thứ tự đó. Điều này không đồng nghĩa các phép tính được chạy song song hoặc hoàn tất không theo thứ tự; một worker xử lý tín hiệu của chuỗi theo cách tuần tự.

Nếu cần xử lý nhiều phần tử đồng thời, có thể dùng `flatMap` với giới hạn concurrency hoặc `parallel()`/`runOn()` cho công việc độc lập. Những cơ chế đó có ngữ nghĩa khác với việc chỉ đổi scheduler downstream. Khi xử lý song song, kết quả có thể hoàn tất hoặc phát ra theo thứ tự khác đầu vào tùy operator.

## Tín hiệu lỗi, hoàn tất và hủy cũng đi qua ranh giới

Ranh giới scheduler không chỉ áp dụng cho `onNext`. Các tín hiệu kết thúc như `onError` và `onComplete` cũng được chuyển tới downstream theo luồng thực thi của `publishOn` hoặc `observeOn`. Điều này có nghĩa callback xử lý lỗi và callback hoàn tất có thể chạy trên scheduler downstream.

Trong Reactor, overload `publishOn(scheduler, delayError, prefetch)` cho phép chọn có trì hoãn việc phát lỗi cho tới khi các phần tử đang chờ được xử lý hay không. Khi dùng mặc định, lỗi có thể được ưu tiên chuyển xuống thay vì chờ drain hết hàng đợi. Nếu nghiệp vụ cần xử lý các phần tử đã được xếp trước lỗi, hãy kiểm tra và chọn chính sách `delayError` phù hợp; không giả định mọi phần tử đang chờ luôn được phát trước terminal error.

Khi Subscriber hủy subscription, Reactor truyền việc hủy upstream và dọn hàng đợi liên quan theo vòng đời của operator. Tuy nhiên, một tác vụ đã bắt đầu chạy hoặc một side effect đã thực hiện không tự động bị rollback. Nếu công việc downstream có side effect, cần thiết kế tính idempotent hoặc cơ chế bù trừ riêng.

## Chọn scheduler cho phần downstream

`publishOn` và `observeOn` chỉ chuyển nơi xử lý; scheduler được chọn vẫn cần phù hợp với loại công việc:

| Loại công việc downstream | Scheduler thường phù hợp | Lý do |
|---|---|---|
| Tính toán CPU-bound ngắn, không blocking | `Schedulers.parallel()` trong Reactor; `Schedulers.computation()` trong RxJava | Dùng pool phù hợp với năng lực CPU |
| Gọi thư viện blocking hoặc I/O cũ | `Schedulers.boundedElastic()` trong Reactor; scheduler I/O thích hợp trong RxJava | Cô lập thread bị chặn khỏi pool CPU/event loop |
| Xử lý tuần tự cần cô lập một luồng | `Schedulers.single()` hoặc scheduler một luồng riêng | Có một worker tuần tự cho nhóm thao tác |
| Công việc có executor riêng do ứng dụng quản lý | Scheduler bọc executor hoặc scheduler tạo riêng | Tích hợp với giới hạn và vòng đời tài nguyên đã có |

Không dùng `Schedulers.parallel()` cho lời gọi blocking kéo dài vì worker CPU có thể bị chiếm giữ. Cũng không chuyển mọi operator sang `boundedElastic()` theo thói quen; pool có giới hạn vẫn có hàng đợi và giới hạn tài nguyên. Hãy chuyển đúng nhóm thao tác cần thiết và đặt timeout/concurrency cho lời gọi bên ngoài.

## Tránh các lỗi phổ biến

**Đặt `publishOn` sau công việc cần cô lập.** Những toán tử đứng trước ranh giới vẫn chạy ở upstream. Hãy đặt nó trước nhóm bước cần đổi nơi xử lý.

**Nhầm `publishOn` với `subscribeOn`.** `publishOn` chuyển xử lý downstream; `subscribeOn` điều khiển nơi bắt đầu subscription và thực thi nguồn theo ngữ nghĩa của nguồn.

**Cho rằng mỗi `publishOn` tạo một thread mới.** Scheduler quản lý worker và tài nguyên; nhiều subscription hoặc nhiều tác vụ có thể dùng chung scheduler. Không tạo thread thủ công cho từng phần tử.

**Cho rằng chuyển scheduler làm công việc chạy song song.** Một ranh giới `publishOn` vẫn xử lý tín hiệu tuần tự cho subscription. Muốn concurrency cần operator và mô hình phân chia công việc phù hợp.

**Thêm nhiều ranh giới mà không đo lường.** Mỗi ranh giới có thể tạo queue, prefetch và chi phí lập lịch. Dùng số lượng ranh giới tối thiểu đáp ứng yêu cầu thực thi.

**Dùng prefetch lớn để che giấu consumer chậm.** Buffer lớn có thể làm độ trễ và bộ nhớ tăng. Đo throughput, queue và thời gian xử lý trước khi điều chỉnh.

**Chặn worker downstream.** `publishOn` không biến lời gọi blocking thành non-blocking. Dùng scheduler phù hợp và giới hạn số tác vụ đang chạy.

**Dùng `observeOn` như thể đó là API Reactor.** `observeOn` là tên thường gặp trong RxJava; Reactor sử dụng `publishOn`. Chọn đúng API theo thư viện trong dự án.

## Kiểm thử ranh giới bằng `StepVerifier`

`StepVerifier` giúp kiểm tra dữ liệu và terminal signal sau khi chuyển scheduler. Có thể dùng scheduler riêng để quan sát thread xử lý downstream:

```java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PublishOnTest {
    @Test
    void downstreamSignalsUseSelectedScheduler() {
        Scheduler downstream = Schedulers.newSingle("downstream-test");
        List<String> threadNames = new CopyOnWriteArrayList<>();

        try {
            Flux<Integer> result = Flux.range(1, 3)
                .publishOn(downstream)
                .doOnNext(value ->
                    threadNames.add(Thread.currentThread().getName())
                );

            StepVerifier.create(result)
                .expectNext(1, 2, 3)
                .verifyComplete();

            assertTrue(threadNames.stream()
                .allMatch(name -> name.startsWith("downstream-test")));
        } finally {
            downstream.dispose();
        }
    }
}
```

Test xác nhận các callback `doOnNext` sau `publishOn` chạy trên scheduler riêng. `CopyOnWriteArrayList` giúp thu thập tên thread an toàn nếu test được mở rộng. Scheduler riêng được dispose trong `finally` để không giữ thread sau khi test kết thúc.

Ngoài thread, hãy kiểm thử các khía cạnh quan trọng khác:

- Dữ liệu và thứ tự downstream có được giữ nguyên không.
- Lỗi có được chuyển tới downstream theo chính sách `delayError` đã chọn không.
- Hủy subscription có dừng việc nhận thêm dữ liệu không.
- Prefetch phù hợp với tốc độ và kích thước phần tử không.
- Công việc blocking có thực sự được chuyển khỏi thread nguồn/event loop không.

Không nên dùng `Thread.sleep` để chứng minh scheduler đã chuyển thread. Dùng `StepVerifier`, latch hoặc công cụ kiểm thử có điều khiển để đồng bộ kết quả; tên thread có thể được ghi nhận tại các ranh giới để chẩn đoán.

## Quan sát khi chạy ứng dụng

Khi cần xác nhận vị trí xử lý, đặt log hoặc metric ở hai phía ranh giới:

```java
Flux<Event> result = eventSource()
    .doOnNext(event -> logThread("source", event.id()))
    .publishOn(Schedulers.parallel(), 128)
    .doOnNext(event -> logThread("downstream", event.id()))
    .map(this::transform);
```

Ghi nhận tên thread, event ID, thời gian nhận và thời gian hoàn tất giúp phân biệt độ trễ do nguồn, hàng đợi scheduler hay phép tính downstream. Trong môi trường tải lớn, nên dùng metric về throughput, độ trễ, queue và số tác vụ đang chờ thay vì log mọi phần tử.

Nếu downstream thường xuyên xử lý chậm hơn upstream, việc đổi scheduler có thể chỉ chuyển nơi backlog hình thành. Hãy xem xét prefetch, concurrency, giới hạn buffer và chính sách bỏ/giữ dữ liệu theo yêu cầu nghiệp vụ. Với dữ liệu cần giữ đầy đủ, có thể cần lưu trữ bền vững hoặc điều tiết nguồn thay vì tăng queue trong heap.

## Tự kiểm tra

1. Trong Reactor, `publishOn` ảnh hưởng những toán tử nào khi đặt giữa hai `map`?
2. Vì sao `publishOn` không chuyển các toán tử nằm trước nó sang scheduler mới?
3. `observeOn` thường được dùng trong thư viện nào và API tương ứng trong Reactor là gì?
4. `publishOn` khác `subscribeOn` ở điểm nào?
5. Vì sao `publishOn` tạo ranh giới bất đồng bộ và có thể làm phát sinh hàng đợi/prefetch?
6. Nếu downstream xử lý chậm hơn upstream, điều gì có thể xảy ra với queue và độ trễ?
7. Vì sao đổi scheduler không tự làm các phần tử chạy song song?
8. Khi nào nên dùng `parallel`, `boundedElastic` hoặc scheduler một luồng cho phần downstream?

Khi đặt `publishOn` hoặc `observeOn` đúng vị trí, bạn có thể chuyển nhóm xử lý phía sau sang scheduler phù hợp, giữ rõ ranh giới giữa nguồn và consumer, đồng thời kiểm soát hàng đợi, demand và vòng đời tài nguyên trong pipeline reactive.
