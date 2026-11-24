# Tác dụng phụ lặp lại do nhiều đăng ký, retry hoặc repeat

Một pipeline reactive mô tả công việc sẽ được thực hiện khi có subscription. Vì vậy, việc viết một biểu thức `Mono` hoặc `Flux` một lần không có nghĩa phần công việc bên trong chỉ chạy một lần. Một nguồn lạnh có thể thực thi lại cho mỗi Subscriber; `retry` tạo subscription mới sau lỗi; `repeat` tạo subscription mới sau khi nguồn hoàn tất. Nếu pipeline chứa thao tác ghi database, trừ tiền, gửi email hoặc gọi API có side effect, các lần đăng ký lại có thể khiến thao tác đó được thực hiện nhiều lần.

Đây là một lỗi dễ gặp khi chuyển từ tư duy imperative sang reactive. Trong imperative code, một lời gọi phương thức thường thực hiện ngay và người viết có thể nhìn thấy một lần gọi trong luồng điều khiển. Với Reactor, nhiều phương thức chỉ lắp ráp Publisher; công việc bắt đầu khi Publisher được subscribe. Cùng một Publisher có thể được subscribe bởi nhiều nơi hoặc nhiều lần. Muốn thiết kế đúng, cần hiểu rõ assembly, subscription, retry, repeat, vòng đời nguồn hot/cold và tính idempotent của side effect.

Bài học thuộc chương **Lỗi thường gặp** của REACTIVE_PROGRAMMING. Module học tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams; đồng thời thực hành Mono, Flux, kết hợp operator, scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Nội dung tập trung vào cách nhận diện side effect bị lặp, kiểm soát số lần thực thi và bảo vệ nghiệp vụ khi pipeline được đăng ký hoặc chạy lại.

## Một Publisher có thể được subscribe nhiều lần

Reactive Streams tách việc mô tả nguồn dữ liệu khỏi việc tiêu thụ nguồn. Gọi `map`, `filter`, `flatMap` hoặc `retryWhen` thường chỉ tạo một Publisher mới. Khi có Subscriber, quá trình thực thi mới bắt đầu theo semantics của nguồn.

Với một nguồn lạnh như `Mono.fromCallable`, mỗi subscription thường gọi lại supplier:

```java
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Mono;

AtomicInteger calls = new AtomicInteger();

Mono<Integer> source = Mono.fromCallable(calls::incrementAndGet);

source.subscribe(value -> System.out.println("first=" + value));
source.subscribe(value -> System.out.println("second=" + value));

System.out.println("calls=" + calls.get()); // 2
```

Hai lời gọi `subscribe()` tạo hai subscription độc lập. `Mono.fromCallable` thực hiện supplier một lần cho mỗi subscription, nên bộ đếm tăng hai lần. Việc biến `source` thành một biến và tái sử dụng nó không tự biến nguồn lạnh thành nguồn dùng chung.

Đây là hành vi đúng của Publisher lạnh. Nó hữu ích khi mỗi request cần truy vấn dữ liệu mới hoặc mỗi Subscriber cần một phép tính độc lập. Nó trở thành lỗi khi người viết nhầm rằng một thao tác nghiệp vụ chỉ chạy một lần vì biến Publisher chỉ được khai báo một lần.

## Phân biệt assembly time và subscription time

Thời điểm tạo giá trị có ảnh hưởng trực tiếp đến số lần side effect được thực hiện.

### `Mono.just` đánh giá đối số ngay khi lắp ráp

```java
import reactor.core.publisher.Mono;

Mono<Receipt> receipt = Mono.just(paymentGateway.charge(command));
```

Java đánh giá `paymentGateway.charge(command)` trước khi gọi `Mono.just`. Side effect xảy ra ngay tại assembly time, kể cả khi không có Subscriber. Nếu sau đó `receipt` được subscribe nhiều lần, Reactor phát lại cùng giá trị `Receipt` đã tạo; nó không tự gọi `charge` thêm lần nữa.

Điều này có thể tạo ra lỗi nghiêm trọng khác: thao tác thanh toán chạy trước khi pipeline được tiêu thụ, lỗi đồng bộ có thể ném ngay tại chỗ tạo Publisher và lifecycle của thao tác nằm ngoài pipeline. `Mono.just` phù hợp với một giá trị đã có sẵn, bất biến và không cần trì hoãn việc tạo.

### `Mono.fromCallable` thực hiện supplier cho mỗi subscription

```java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<Receipt> receipt = Mono.fromCallable(
    () -> paymentGateway.charge(command)
).subscribeOn(Schedulers.boundedElastic());
```

Supplier được gọi khi subscribe. Mỗi subscription có thể thực hiện một lần charge mới. Cách viết này đưa kết quả và exception của lời gọi đồng bộ vào pipeline, nhưng không bảo đảm side effect chỉ xảy ra một lần.

Nếu callable thực hiện I/O blocking, `fromCallable` chỉ đưa lời gọi vào lifecycle của subscription; nó không tự biến I/O thành non-blocking. Cần cô lập nó trên scheduler phù hợp, chẳng hạn `subscribeOn(Schedulers.boundedElastic())`, đồng thời đặt timeout và giới hạn concurrency theo capacity của dependency. Việc chuyển scheduler cũng không thay đổi semantics retry: mỗi lần resubscribe vẫn có thể gọi callable lại.

### `Mono.defer` tạo Publisher mới cho mỗi subscription

```java
import reactor.core.publisher.Mono;

Mono<Receipt> receipt = Mono.defer(() ->
    paymentService.charge(command)
);
```

`defer` gọi factory mỗi khi có subscription. Nó hữu ích khi cần tạo Publisher mới dựa trên trạng thái hiện tại, nhưng factory và Publisher con vẫn có thể thực hiện side effect mỗi lần subscribe. `defer` kiểm soát thời điểm tạo Publisher, không phải cơ chế deduplication hoặc idempotency.

| Cách tạo | Thời điểm đánh giá | Khi subscribe nhiều lần |
|---|---|---|
| `Mono.just(value)` | Ngay khi gọi `just` | Phát lại cùng giá trị đã tạo |
| `Mono.fromCallable(callable)` | Khi mỗi subscription bắt đầu | Gọi callable lại cho từng subscription |
| `Mono.defer(factory)` | Gọi factory cho mỗi subscription | Tạo và subscribe Publisher con mới |
| `Flux.just(values...)` | Đánh giá các đối số trước khi gọi `just` | Phát lại các giá trị đã có |
| `Flux.defer(factory)` | Gọi factory cho mỗi subscription | Tạo nguồn Flux mới cho mỗi subscription |

Không chọn API chỉ dựa trên tên “lazy”. Hãy xác định side effect cần chạy ở thời điểm nào và có được phép chạy lại khi có subscription mới hay không.

## Nhiều lời gọi `subscribe()` có thể nhân đôi side effect

Một anti-pattern phổ biến là tự subscribe bên trong service rồi trả lại chính Publisher đó:

```java
Mono<Order> createOrder(CreateOrder command) {
    Mono<Order> result = repository.save(toOrder(command));

    result.subscribe(); // subscription thứ nhất: lưu đơn hàng
    return result;      // framework có thể subscribe lần thứ hai
}
```

Trong Spring WebFlux, framework subscribe Publisher được controller trả về để ghi response. Subscription thủ công trong service tạo một luồng thực thi tách rời; subscription của framework có thể thực hiện thao tác lưu lần nữa. Lỗi của subscription thủ công cũng không được truyền về caller theo cách thông thường, và caller không còn kiểm soát được cancellation hoặc lifecycle của công việc.

Hãy trả Publisher để caller kết hợp vào pipeline:

```java
Mono<Order> createOrder(CreateOrder command) {
    return repository.save(toOrder(command));
}
```

Controller có thể tiếp tục kết hợp kết quả:

```java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import reactor.core.publisher.Mono;

@PostMapping("/orders")
Mono<ResponseEntity<OrderView>> create(@RequestBody CreateOrder command) {
    return orderService.createOrder(command)
        .map(order -> ResponseEntity.status(201).body(OrderView.from(order)));
}
```

Không gọi `subscribe()` trong controller, service hoặc repository chỉ để “kích hoạt” công việc. Chỉ subscribe trực tiếp ở ranh giới ứng dụng được thiết kế rõ ràng, chẳng hạn một worker quản lý vòng đời subscription hoặc một tác vụ nền độc lập có giám sát, và phải giữ `Disposable`, xử lý lỗi và cancellation.

### `block()` cũng tạo subscription

`block()`, `blockOptional()`, `blockFirst()` và `blockLast()` là các thao tác tiêu thụ Publisher theo kiểu đồng bộ. Gọi `block()` hai lần thường tạo hai subscription:

```java
import reactor.core.publisher.Mono;

Mono<String> result = Mono.fromCallable(this::readAndUpdate);

String first = result.block();
String second = result.block(); // supplier được gọi lần nữa
```

Ngoài việc chặn thread, cách này có thể lặp side effect. Trong một pipeline reactive, hãy dùng `map`, `flatMap`, `then` hoặc operator phù hợp để kết hợp Publisher. Nếu cần đọc kết quả ở một ranh giới imperative được kiểm soát, xác định rõ việc block có được phép và liệu Publisher có thể được tiêu thụ nhiều lần hay không.

## `retry` là resubscribe, không phải chạy tiếp từ điểm lỗi

Khi một Publisher phát `onError`, `retry` hoặc `retryWhen` có thể subscribe lại vào nguồn upstream. Các operator và side effect nằm phía upstream của retry sẽ được thực thi lại theo subscription mới.

```java
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Mono;

AtomicInteger attempts = new AtomicInteger();

Mono<String> call = Mono.fromCallable(() -> {
    int attempt = attempts.incrementAndGet();
    if (attempt < 3) {
        throw new IllegalStateException("temporary failure");
    }
    return "ok";
}).retry(2);
```

`retry(2)` cho phép hai lần retry sau lần subscribe đầu tiên, vì vậy supplier có thể chạy tổng cộng ba lần. Nếu supplier gửi email, tạo hóa đơn hoặc trừ tiền trước khi ném lỗi, thao tác có thể đã xảy ra dù client nhận lỗi và Reactor thử lại.

Retry không biết side effect đã được hệ thống bên ngoài commit hay chưa. Ví dụ, server thanh toán có thể đã trừ tiền nhưng response bị mất trên mạng. Client thấy timeout và retry; nếu endpoint không hỗ trợ idempotency, lần gọi thứ hai có thể trừ tiền thêm lần nữa.

### Vị trí của side effect so với `retryWhen` rất quan trọng

```java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

source
    .doOnNext(this::recordAttemptResult)
    .retryWhen(retryPolicy);
```

`doOnNext` nằm upstream của retry, nên callback có thể chạy ở mỗi attempt. Khi một attempt lỗi sau khi đã phát một số phần tử, những phần tử đó đã được phát ra downstream trước lỗi; retry không thể thu hồi chúng.

```java
import reactor.core.publisher.Flux;

source
    .retryWhen(retryPolicy)
    .doOnNext(this::observeFinalStream);
```

Callback nằm downstream quan sát các phần tử do toàn bộ Publisher sau retry phát ra. Nhưng với `Flux`, nếu attempt đầu đã phát `A`, `B` rồi lỗi, attempt tiếp theo phát lại `A`, `B`, `C`, downstream vẫn có thể nhìn thấy `A`, `B`, `A`, `B`, `C`. Đặt side effect sau retry không tự loại bỏ các phần tử đã phát từ attempt thất bại.

Nếu cần chỉ công bố kết quả khi một lần xử lý hoàn tất, hãy thiết kế nguồn theo đơn vị có thể commit nguyên tử hoặc gom kết quả trước khi phát. Với `Flux` lớn, việc gom toàn bộ có thể không phù hợp bộ nhớ; khi đó cần sequence/version, deduplication hoặc xử lý idempotent theo từng phần tử.

## `Flux.retry` có thể phát lại phần tử đã phát trước lỗi

Khác với một `Mono` thường chỉ phát tối đa một giá trị rồi hoàn tất, `Flux` có thể phát nhiều phần tử rồi mới gặp lỗi. Khi retry, subscription mới bắt đầu lại nguồn. Những phần tử đã phát từ lần thử trước không bị xóa khỏi downstream.

```java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger subscriptions = new AtomicInteger();

Flux<Integer> unstable = Flux.defer(() -> {
    int attempt = subscriptions.incrementAndGet();
    if (attempt == 1) {
        return Flux.just(1, 2)
            .concatWith(Mono.error(new IllegalStateException("broken connection")));
    }
    return Flux.just(1, 2, 3);
});

StepVerifier.create(unstable.retry(1))
    .expectNext(1, 2, 1, 2, 3)
    .verifyComplete();
```

Kết quả có `1, 2` hai lần. Đây không phải lỗi của Reactor: retry thực hiện lại Publisher, còn hai phần tử đầu đã được phát hợp lệ trước khi lỗi xuất hiện. Nếu consumer ghi từng phần tử vào database, các bản ghi có thể bị lặp.

Các chiến lược xử lý:

- Gắn sequence hoặc event ID ổn định để consumer nhận biết phần tử đã xử lý.
- Dùng thao tác upsert hoặc unique constraint nếu phù hợp với nghiệp vụ.
- Lưu checkpoint sau khi xử lý thành công và tiếp tục từ checkpoint thay vì luôn đọc lại từ đầu.
- Chia nguồn thành batch có ranh giới commit rõ ràng.
- Chỉ retry phần thao tác có thể lặp an toàn; không retry toàn bộ pipeline nếu một phần đã commit không thể rollback.

## `repeat` chạy lại nguồn sau khi hoàn tất

`repeat` khác `retry`: retry phản ứng với `onError`, còn repeat phản ứng với `onComplete`. Mỗi lần repeat tạo một subscription mới tới upstream.

```java
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Flux;

AtomicInteger reads = new AtomicInteger();

Flux<Integer> polls = Mono.fromCallable(reads::incrementAndGet)
    .repeat(2);
```

`repeat(2)` thực hiện hai lần lặp sau lần đầu, nên supplier có thể được gọi ba lần. Đây là cách có thể dùng để poll nguồn đồng bộ, nhưng nếu thao tác đọc có side effect như cập nhật last-access, ghi audit hoặc tiêu thụ message, side effect đó cũng lặp theo.

`repeatWhen` cho phép điều khiển thời điểm lặp bằng một Publisher tín hiệu. Ví dụ poll cách nhau một giây:

```java
import java.time.Duration;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Flux<Snapshot> snapshots = Mono.defer(snapshotService::readCurrent)
    .repeatWhen(completions -> completions.delayElements(Duration.ofSeconds(1)));
```

Publisher trong `repeatWhen` nhận tín hiệu hoàn tất và quyết định khi nào cho phép subscription tiếp theo. Cần có điều kiện dừng, cancellation và giới hạn tài nguyên. Một polling stream vô hạn có thể tiếp tục gọi dependency ngay cả khi không còn client quan tâm nếu vòng đời subscription không được quản lý.

### Phân biệt `retry`, `repeat` và `repeatWhen`

| Operator | Kích hoạt khi | Tạo lại subscription? | Trường hợp thường gặp |
|---|---|---|---|
| `retry(n)` | Upstream phát `onError` | Có, tối đa n lần retry | Thử lại lỗi tạm thời |
| `retryWhen(companion)` | Companion cho phép sau lỗi | Có | Backoff, phân loại lỗi, deadline |
| `repeat(n)` | Upstream phát `onComplete` | Có, tối đa n lần lặp sau lần đầu | Lặp nguồn hữu hạn |
| `repeatWhen(companion)` | Companion cho phép sau hoàn tất | Có | Polling, vòng đọc tiếp theo |

Không dùng `repeat` để phục hồi lỗi hoặc `retry` để tạo vòng poll sau khi hoàn tất. Chọn operator theo terminal signal cần xử lý.

## Nguồn hot, cold và chia sẻ side effect

Nguồn lạnh thường tạo một luồng thực thi cho mỗi subscription. Nguồn nóng có thể phát độc lập với subscription; Subscriber đến muộn chỉ nhận những tín hiệu phát sau khi nó tham gia, tùy loại Publisher. Việc chia sẻ nguồn có thể giảm số lần gọi upstream nhưng thay đổi semantics về thời điểm và subscriber nhận dữ liệu.

### `cache()` chia sẻ kết quả đã phát

Với `Mono`, `cache()` lưu terminal signal và phát lại cho các Subscriber sau:

```java
Mono<Config> config = Mono.fromCallable(configClient::load)
    .cache();
```

Trong vòng đời của Publisher đã cache, lần subscription đầu kích hoạt nguồn; các subscription sau nhận lại giá trị hoặc terminal signal đã lưu. Điều này có thể tránh gọi lại dependency, nhưng cũng có thể cache lỗi hoặc trạng thái rỗng. Nếu config thay đổi, giá trị cache có thể cũ; nếu lỗi tạm thời xảy ra ở lần đầu, những Subscriber sau có thể nhận lại lỗi đã cache.

Có thể đặt TTL hoặc chính sách cache theo signal nếu phù hợp với phiên bản Reactor đang dùng. Dù vậy, cache trong bộ nhớ của một instance không thay thế cache phân tán hoặc kho dữ liệu bền vững. Mỗi instance có thể có cache riêng và khởi động lại sẽ mất cache.

Với `Flux.cache()`, Reactor có thể lưu các phần tử đã phát để replay cho subscriber mới. Nếu nguồn vô hạn hoặc phát lượng dữ liệu lớn, cache không giới hạn có thể giữ dữ liệu trong heap mãi. Chỉ dùng khi giới hạn replay, TTL và vòng đời được xác định.

### `share()` multicast luồng đang phát

`share()` cho phép nhiều Subscriber cùng quan sát một upstream đang được chia sẻ:

```java
Flux<Event> sharedEvents = eventSource()
    .doOnSubscribe(ignored -> metrics.incrementUpstreamSubscriptions())
    .share();
```

Khi có subscriber, upstream được kết nối theo semantics của `share`/refCount. Các subscriber đang cùng tham gia có thể nhận cùng sự kiện; subscriber đến muộn không tự nhận lịch sử đã phát. Khi tất cả subscriber hủy, upstream có thể bị ngắt; subscription mới sau đó có thể tạo một lần kết nối upstream mới. Do đó, side effect ở nguồn vẫn có thể lặp theo vòng đời kết nối.

`share()` không phải cơ chế đảm bảo exactly-once và không phải event store. Nếu cần replay, lưu event bền vững hoặc chọn cơ chế replay có giới hạn. Nếu side effect phải chạy một lần trên toàn hệ thống, cần một cơ chế phối hợp bền vững và idempotency; không dựa vào một instance `Flux` được chia sẻ trong bộ nhớ.

### Chọn giữa cold, cache và share

| Nhu cầu | Cách thường cân nhắc | Rủi ro cần quản lý |
|---|---|---|
| Mỗi request cần truy vấn mới | Nguồn cold | Nhiều subscriber đồng nghĩa nhiều lần gọi upstream |
| Nhiều subscriber cần cùng một kết quả bất biến trong TTL | `Mono.cache()` | Cache lỗi/rỗng, stale data, cache riêng từng instance |
| Nhiều client cùng nhận event đang phát | `share()` hoặc sink multicast | Subscriber muộn bỏ lỡ event; upstream có thể kết nối lại |
| Cần replay event và phục hồi sau restart | Event store hoặc broker bền vững | Cần cursor, retention, deduplication và ordering |
| Side effect chỉ được commit một lần theo nghiệp vụ | Idempotency/deduplication bền vững | Cần key ổn định và lưu kết quả commit |

## Idempotency: bảo vệ nghiệp vụ trước lần gọi lặp

Một thao tác idempotent có thể được thực hiện nhiều lần với cùng định danh yêu cầu mà trạng thái nghiệp vụ cuối cùng vẫn như khi thực hiện một lần. Tính idempotent đặc biệt quan trọng với API thanh toán, tạo đơn, gửi command và consumer nhận message theo at-least-once.

Ví dụ, client gửi `POST /payments` kèm `Idempotency-Key`. Server lưu key cùng kết quả xử lý trong một transaction. Nếu request cùng key đến lần nữa, server trả lại kết quả đã lưu thay vì trừ tiền lần nữa.

```java
import reactor.core.publisher.Mono;

Mono<PaymentResult> charge(ChargeCommand command, String idempotencyKey) {
    return idempotencyService.executeOnce(
        idempotencyKey,
        command,
        () -> paymentGateway.charge(command, idempotencyKey)
    );
}
```

`executeOnce` là abstraction nghiệp vụ có trách nhiệm atomically claim key, kiểm tra payload, thực hiện thao tác và lưu kết quả để lần gọi sau nhận lại cùng kết quả. Đây là API minh họa; implementation thực tế cần unique constraint hoặc cơ chế claim có trạng thái `IN_PROGRESS` để bảo vệ hai request đồng thời cùng key. Transaction và cơ chế phối hợp cần phù hợp với gateway bên ngoài. Nếu gateway hỗ trợ idempotency key, truyền cùng key đó cho gateway để bảo vệ cả ranh giới mạng.

Idempotency key phải đại diện cho một ý định nghiệp vụ cụ thể và được giữ ổn định qua các lần retry. Không tạo UUID mới trong supplier của `Mono.defer` ở mỗi lần subscription, vì mỗi retry sẽ trở thành một yêu cầu mới theo góc nhìn hệ thống đích.

### Idempotency key và payload phải nhất quán

Nếu cùng một key được gửi với payload khác nhau, server cần phát hiện và từ chối xung đột thay vì trả kết quả cũ một cách âm thầm. Có thể lưu hash của payload chuẩn hóa cùng key. Quy định thời gian lưu key phải dài hơn cửa sổ retry/replay có thể xảy ra; xóa key quá sớm có thể khiến message cũ tạo side effect lại.

Không phải mọi side effect đều có thể trở nên idempotent chỉ bằng một key. Gửi email, gọi hệ thống đối tác hoặc ghi file cần thiết kế deduplication hoặc outbox phù hợp. Nếu dependency không hỗ trợ idempotency, cần xác định cách đối soát trạng thái trước khi retry.

## Side effect trong `doOnNext` và `flatMap`

`doOnNext` phù hợp cho hành động quan sát đồng bộ như metric, log hoặc ghi nhận một tín hiệu. Nó không biến callback thành một tác vụ bất đồng bộ có quản lý lifecycle. Nếu callback gọi API blocking hoặc ghi database đồng bộ, nó có thể chặn thread phát tín hiệu.

```java
import reactor.core.publisher.Flux;

events()
    .doOnNext(event -> auditRepository.writeBlocking(event))
    .subscribe();
```

Đoạn mã có hai vấn đề: `writeBlocking` có thể chặn thread; và subscription thủ công có thể lặp khi phương thức được gọi nhiều lần hoặc Publisher được tiêu thụ ở nơi khác.

Nếu thao tác audit có API reactive, biểu diễn nó thành Publisher:

```java
import reactor.core.publisher.Flux;

Flux<AuditReceipt> audited = events()
    .concatMap(event -> auditRepository.save(event)
        .map(receipt -> new AuditReceipt(event.id(), receipt.id())));
```

`concatMap` tuần tự hóa thao tác lưu theo thứ tự event và đưa lỗi lưu vào pipeline. Nếu cho phép ghi đồng thời, có thể dùng `flatMap` với giới hạn concurrency, nhưng phải bảo đảm thứ tự và capacity phù hợp. Retry ở upstream vẫn có thể gọi lại `save`; database nên có unique key hoặc upsert theo event ID nếu xử lý trùng là không được phép.

Đặt side effect vào `flatMap` giúp nó trở thành một phần của pipeline, nhưng không tự làm nó exactly-once. Khi subscription bị retry hoặc repeat, inner Publisher cũng có thể được gọi lại.

## Phân biệt retry ở tầng client, service và broker

Một yêu cầu có thể bị lặp ở nhiều tầng cùng lúc:

- Client retry vì timeout không nhận được response.
- Gateway retry request tới service khác.
- Service dùng `retryWhen` cho một lời gọi dependency.
- Broker redeliver message vì consumer không acknowledge.
- Scheduler chạy lại job sau khi process restart.

Nếu mỗi tầng đều retry ba lần, tổng số lần gọi dependency có thể lớn hơn nhiều so với dự tính. Cần quy định một ngân sách retry end-to-end, deadline tổng và tầng nào chịu trách nhiệm retry. Không retry cùng một lỗi ở mọi tầng mà không phối hợp.

Với message broker, at-least-once delivery có nghĩa consumer có thể nhận cùng message nhiều lần. Consumer cần idempotent theo message ID hoặc business key. Một mẫu thường dùng là bảng inbox/deduplication: ghi message ID và thay đổi nghiệp vụ trong cùng transaction; unique constraint ngăn xử lý lặp. Nếu consumer đã commit nhưng acknowledgement bị mất, message được giao lại và lần sau phát hiện ID đã xử lý.

Với workflow nhiều service, Transactional Outbox giúp lưu thay đổi nghiệp vụ và sự kiện cần phát trong cùng transaction local. Publisher có thể phát lại outbox khi lỗi; consumer vẫn cần deduplication. Outbox giải quyết khoảng trống giữa commit database và publish message, không tự bảo đảm mọi side effect downstream chỉ chạy một lần.

## Thiết kế retry có kiểm soát

Chỉ retry lỗi có khả năng tạm thời, như một số lỗi kết nối hoặc giới hạn tải có thể phục hồi. Retry cần giới hạn số lần, backoff, jitter, deadline và phân loại lỗi:

```java
import java.time.Duration;
import reactor.util.retry.Retry;

Retry policy = Retry.backoff(3, Duration.ofMillis(200))
    .maxBackoff(Duration.ofSeconds(2))
    .filter(this::isTransientFailure);
```

Policy trên cho tối đa ba lần retry sau lần đầu, tăng thời gian chờ và giới hạn backoff tối đa. Trong production, cân nhắc jitter để tránh nhiều client cùng retry tại một thời điểm. Deadline tổng phải tính cả thời gian mỗi attempt và thời gian chờ giữa các attempt.

Không retry:

- Lỗi validation hoặc dữ liệu đầu vào không hợp lệ.
- Lỗi xác thực/phân quyền.
- Xung đột nghiệp vụ cần client đọc trạng thái mới.
- Thao tác không idempotent khi chưa có cơ chế bảo vệ.
- Lỗi vĩnh viễn mà retry chỉ làm tăng tải.

Retry không phải giải pháp cho mọi `onError`. Nếu dependency quá tải, retry nhanh và đồng loạt có thể tạo retry storm. Kết hợp timeout, circuit breaker, bulkhead, rate limit và load shedding để giữ hệ thống trong giới hạn chịu tải.

## Cancellation không hoàn tác side effect đã xảy ra

Khi client hủy subscription, Reactor truyền cancellation upstream theo hợp đồng của Publisher và operator. Điều này giúp dừng công việc chưa cần tiếp tục, nhưng không thể hoàn tác side effect đã commit ở hệ thống bên ngoài.

Ví dụ, server đã gửi request thanh toán và gateway đã trừ tiền; sau đó client đóng kết nối. Việc hủy subscription có thể khiến ứng dụng không nhận response, nhưng không có nghĩa giao dịch đã được rollback. Nếu client gửi lại request, idempotency key là cần thiết để tránh charge lần hai.

Khi thiết kế side effect:

- Xác định điểm commit và khả năng cancellation của dependency.
- Không xem cancellation như bằng chứng thao tác chưa xảy ra.
- Lưu trạng thái trung gian để có thể truy vấn hoặc đối soát kết quả chưa rõ.
- Dùng idempotency key xuyên suốt các lần thử lại.
- Đảm bảo cleanup tài nguyên trong `doFinally` hoặc API quản lý resource phù hợp, nhưng không đặt logic rollback giả định vào cleanup nếu side effect đã commit.

## Kiểm thử số lần subscription và side effect

Một test tốt nên xác nhận số lần nguồn được subscribe, số lần side effect chạy và dữ liệu downstream quan sát được. Dùng `AtomicInteger` hoặc fake dependency để đếm, tránh gọi dịch vụ thật.

### Kiểm thử nhiều subscriber trên nguồn lạnh

```java
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import static org.junit.jupiter.api.Assertions.assertEquals;

class SubscriptionCountTest {
    @Test
    void coldSourceRunsOncePerSubscriber() {
        AtomicInteger calls = new AtomicInteger();
        Mono<Integer> source = Mono.fromCallable(calls::incrementAndGet);

        StepVerifier.create(source)
            .expectNext(1)
            .verifyComplete();

        StepVerifier.create(source)
            .expectNext(2)
            .verifyComplete();

        assertEquals(2, calls.get());
    }
}
```

Test xác nhận cùng một biến Publisher cold được subscribe hai lần thì supplier chạy hai lần. Nếu yêu cầu nghiệp vụ là một lần thực thi dùng chung, hãy thay semantics bằng cache/share phù hợp hoặc một cơ chế lưu kết quả bền vững; không thay assertion chỉ để test qua.

### Kiểm thử retry tạo subscription mới

```java
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import static org.junit.jupiter.api.Assertions.assertEquals;

class RetrySideEffectTest {
    @Test
    void retryRepeatsUpstreamSupplier() {
        AtomicInteger attempts = new AtomicInteger();

        Mono<String> source = Mono.fromCallable(() -> {
            if (attempts.incrementAndGet() < 3) {
                throw new IllegalStateException("temporary");
            }
            return "ok";
        }).retry(2);

        StepVerifier.create(source)
            .expectNext("ok")
            .verifyComplete();

        assertEquals(3, attempts.get());
    }
}
```

Test này xác nhận lần subscribe đầu cộng hai lần retry, tổng cộng ba lần thực thi supplier. Với retry có backoff, dùng virtual time để xác nhận khoảng chờ mà không phải `Thread.sleep`.

### Kiểm thử `repeat` sau hoàn tất

```java
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import static org.junit.jupiter.api.Assertions.assertEquals;

class RepeatSideEffectTest {
    @Test
    void repeatResubscribesAfterCompletion() {
        AtomicInteger reads = new AtomicInteger();

        Mono<Integer> source = Mono.fromCallable(reads::incrementAndGet)
            .repeat(2);

        StepVerifier.create(source)
            .expectNext(1, 2, 3)
            .verifyComplete();

        assertEquals(3, reads.get());
    }
}
```

`repeat(2)` tạo hai lần lặp sau lần đầu, do đó nguồn chạy ba lần. Test này giúp tránh nhầm tham số `2` là tổng số subscription.

### Kiểm thử side effect chỉ một lần bằng idempotency store giả lập

Với thao tác nghiệp vụ, test nên xác nhận cùng key không tạo thêm charge. Có thể dùng fake store/gateway để mô phỏng việc lưu kết quả:

```java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

final class FakeIdempotentGateway {
    private final Map<String, String> results = new ConcurrentHashMap<>();
    private final AtomicInteger charges = new AtomicInteger();

    String charge(String key) {
        return results.computeIfAbsent(key, ignored -> {
            int number = charges.incrementAndGet();
            return "receipt-" + number;
        });
    }

    int chargeCount() {
        return charges.get();
    }
}
```

Khi kiểm thử, gọi cùng key nhiều lần và xác nhận receipt giống nhau, `chargeCount()` vẫn bằng một. Với test đồng thời, chạy nhiều request cùng key và xác nhận chỉ một kết quả được tạo. Fake này minh họa semantics; implementation production cần lưu key và kết quả trong storage bền vững với unique constraint hoặc thao tác nguyên tử phù hợp.

### Những tình huống cần có test

- Cùng một Publisher được subscribe hai lần.
- Controller và service không tạo subscription thủ công trùng với subscription của framework.
- Retry sau lỗi trước commit và retry sau khi side effect có thể đã commit.
- Flux phát một phần tử rồi lỗi, sau đó retry và phát lại prefix.
- Repeat sau hoàn tất với đúng số lần lặp.
- Hai subscription đồng thời cùng dùng một idempotency key.
- Hai key khác nhau không bị gộp thành một giao dịch.
- Message broker redelivery sau khi consumer commit nhưng chưa acknowledgement.
- Cancellation xảy ra trước và sau điểm commit.
- Cache hết TTL hoặc cache một lỗi theo chính sách đã định.

## Những lỗi thường gặp

**Nghĩ rằng khai báo Publisher một lần thì side effect chỉ chạy một lần.** Nguồn cold thường thực thi cho mỗi subscription. Đếm subscription trong test và xác định vòng đời Publisher.

**Dùng `Mono.just(callWithSideEffect())` để trì hoãn công việc.** Đối số được đánh giá ngay khi lắp ráp. Dùng `fromCallable` hoặc `defer` nếu cần thực hiện khi subscribe, rồi vẫn phải quản lý retry và idempotency.

**Dùng `defer` như cơ chế chống lặp.** `defer` gọi factory mỗi subscription; nó có thể làm side effect lặp dễ hơn nếu factory thực hiện thao tác ghi.

**Tự gọi `subscribe()` trong service.** Tạo subscription tách rời, có thể chạy song song với subscription của caller, làm mất khả năng quản lý lỗi và cancellation.

**Gọi `block()` nhiều lần trên cùng Publisher.** Mỗi lần block có thể subscribe lại và thực hiện nguồn cold lần nữa, đồng thời chặn thread.

**Retry một thao tác ghi không idempotent.** Timeout có thể xảy ra sau khi hệ thống đích đã commit. Dùng idempotency key hoặc kiểm tra trạng thái trước khi thử lại.

**Cho rằng retry tiếp tục từ phần tử bị lỗi.** Retry resubscribe upstream. Với Flux, phần tử đã phát trước lỗi có thể xuất hiện lại.

**Đặt side effect sau `retryWhen` rồi nghĩ không thể lặp.** Các phần tử đã phát từ attempt lỗi vẫn có thể đi xuống downstream trước khi retry.

**Dùng repeat mà không có điều kiện dừng.** Polling vô hạn có thể tiếp tục giữ tài nguyên hoặc gọi dependency khi không còn consumer. Quản lý cancellation và vòng đời subscription.

**Dùng `cache()` hoặc `share()` như bảo đảm exactly-once.** Đây là cơ chế chia sẻ trong bộ nhớ với semantics và vòng đời cụ thể; chúng không thay thế idempotency bền vững.

**Bỏ qua lỗi của subscription nền.** Subscription thủ công không truyền lỗi về caller như pipeline được trả về. Nếu cần worker nền, quản lý lỗi, metric, cancellation và restart rõ ràng.

**Retry ở mọi tầng mà không có ngân sách chung.** Client, gateway, Reactor và broker có thể nhân số lần gọi. Phối hợp deadline và chính sách retry end-to-end.

## Tự kiểm tra

1. Vì sao cùng một `Mono.fromCallable` có thể thực thi supplier nhiều lần dù Publisher chỉ được khai báo một lần?
2. `Mono.just(call())`, `Mono.fromCallable(call)` và `Mono.defer(...)` khác nhau ở thời điểm đánh giá nào?
3. Vì sao tự gọi `subscribe()` trong service có thể làm thao tác lưu chạy hai lần trong Spring WebFlux?
4. `block()` có tạo subscription không? Điều gì xảy ra nếu gọi nó hai lần trên một nguồn cold?
5. `retry(2)` có thể tạo tổng cộng bao nhiêu subscription nếu nguồn luôn lỗi trước khi thành công?
6. Vì sao `Flux.retry` có thể phát lại các phần tử đã phát trước lỗi?
7. `repeat(2)` khác `retry(2)` ở terminal signal nào và số lần thực thi ra sao?
8. `cache()` và `share()` khác nhau thế nào về replay và vòng đời upstream?
9. Vì sao idempotency key phải ổn định qua các lần retry?
10. Khi nào cần inbox/deduplication hoặc Transactional Outbox ở ranh giới broker?
11. Cancellation có hoàn tác được side effect đã commit ở hệ thống bên ngoài không?
12. Những test nào giúp xác nhận số lần subscription, retry, repeat và side effect thực tế?

Khi xem mỗi subscription là một lần thực thi tiềm năng, nhận diện retry/repeat như cơ chế tạo subscription mới và bảo vệ thao tác nghiệp vụ bằng idempotency, bạn có thể xây dựng pipeline reactive an toàn hơn. Side effect cần có chủ sở hữu, vòng đời và chính sách lặp rõ ràng; khi đó retry phục hồi lỗi tạm thời mà không biến một yêu cầu thành nhiều giao dịch ngoài ý muốn.
