# Kiểm thử hủy đăng ký và dọn dẹp tài nguyên

Trong **REACTIVE_PROGRAMMING**, `Mono` và `Flux` quản lý dữ liệu bất đồng bộ theo hợp đồng `Publisher–Subscriber`. Subscriber có thể hủy `Subscription` khi không còn cần dữ liệu, chẳng hạn người dùng đóng trang, request HTTP hết thời gian hoặc một toán tử như `take` đã nhận đủ phần tử. Cancellation là một phần bình thường của vòng đời reactive, vì vậy pipeline phải giải phóng listener, timer, connection, file handle, buffer và công việc nền khi subscription kết thúc theo cách này.

Kiểm thử chỉ xác nhận giá trị phát ra và `onComplete`/`onError` là chưa đủ. Một pipeline có thể trả đúng dữ liệu nhưng vẫn để lại subscription, giữ tài nguyên hoặc tiếp tục công việc sau khi caller đã rời đi. Bài này trình bày cách kiểm tra tín hiệu cancellation, xác minh nó được truyền upstream và bảo đảm cleanup chạy đúng trong các đường complete, error và cancel.

## 1. Cancellation là tín hiệu điều khiển riêng

Trong Reactive Streams, Subscriber hủy bằng `Subscription.cancel()`. Sau khi hủy, Publisher được yêu cầu ngừng phát tín hiệu cho subscription đó và giải phóng tài nguyên liên quan nếu có thể.

Cancellation khác với hai tín hiệu kết thúc còn lại:

| Tín hiệu | Ai khởi tạo? | Ý nghĩa | Subscriber nhận tín hiệu kết thúc? |
|---|---|---|---|
| `onComplete` | Publisher | Nguồn hoàn tất bình thường | Có |
| `onError` | Publisher | Nguồn kết thúc do lỗi | Có |
| `cancel()` | Subscriber | Downstream không còn cần dữ liệu | Không có `onComplete` hoặc `onError` chỉ vì cancel |

Cancellation là yêu cầu hợp tác. Một Publisher tuân thủ hợp đồng sẽ ngừng phát dữ liệu sau khi nhận cancel, nhưng một tác vụ blocking hoặc một API bên ngoài có thể không dừng ngay lập tức. Vì vậy, cần kiểm tra cả việc tín hiệu hủy được truyền đi và hành vi thực tế của tài nguyên hoặc tác vụ bên dưới.

Cancellation cũng không đồng nghĩa rollback một side effect đã commit. Nếu server đã ghi database trước khi client hủy request, subscription bị hủy không thể tự hoàn tác giao dịch đó. Muốn hoàn tác nghiệp vụ cần transaction hoặc hành động bù riêng.

## 2. Những trường hợp thường kích hoạt cancellation

Cancellation có thể xuất hiện trong nhiều tình huống bình thường:

- Client HTTP đóng kết nối hoặc người dùng rời trang.
- `timeout` hết hạn và hủy upstream.
- `take(n)` đã nhận đủ số phần tử cần thiết.
- `takeUntil` nhận tín hiệu dừng.
- Một subscriber chủ động gọi `dispose()` trên `Disposable` của Reactor hoặc RxJava adapter.
- Một pipeline phía trên hủy vì không còn nhu cầu hoặc vì một nhánh khác đã quyết định kết quả.
- Ứng dụng shutdown trong khi stream vẫn hoạt động.

Ví dụ, `take(3)` chỉ cần ba phần tử:

```java
Flux<Long> firstThree = Flux.interval(Duration.ofMillis(100))
    .take(3);
```

Sau khi nhận phần tử thứ ba, `take` hoàn tất downstream và hủy subscription upstream. Nguồn interval không cần tiếp tục phát các tick còn lại cho subscription đó.

## 3. Quan sát cancellation bằng doOnCancel và doFinally

Reactor cung cấp các callback quan sát vòng đời:

```java
Flux<Event> events = eventSource()
    .doOnCancel(() -> metrics.increment("events.cancelled"))
    .doFinally(signal -> log.info("Event stream ended: {}", signal));
```

`doOnCancel` chỉ chạy khi subscription bị hủy. `doFinally` chạy sau khi luồng kết thúc bằng complete, error hoặc cancel; tham số `SignalType` cho biết loại kết thúc.

| Toán tử | Complete | Error | Cancel | Mục đích |
|---|---:|---:|---:|---|
| `doOnComplete` | Có | Không | Không | Quan sát hoàn tất bình thường |
| `doOnError` | Không | Có | Không | Quan sát lỗi |
| `doOnCancel` | Không | Không | Có | Quan sát yêu cầu hủy |
| `doFinally` | Có | Có | Có | Ghi nhận mọi đường kết thúc |

Không dùng `doOnComplete` làm callback cleanup duy nhất nếu tài nguyên cũng cần đóng khi lỗi hoặc cancel. `doFinally` phù hợp với cleanup đồng bộ, ngắn như dừng timer hoặc ghi metrics. Với tài nguyên có API đóng bất đồng bộ, dùng `usingWhen` để Reactor quản lý Publisher cleanup.

## 4. Kiểm thử cancellation bằng StepVerifier

`StepVerifier` có bước `thenCancel()` để hủy subscription tại một thời điểm xác định. Có thể kết hợp bộ đếm để xác nhận callback được gọi:

```java
AtomicInteger cancelCount = new AtomicInteger();
AtomicReference<SignalType> finalSignal = new AtomicReference<>();

Flux<Long> source = Flux.interval(Duration.ofMillis(100))
    .doOnCancel(cancelCount::incrementAndGet)
    .doFinally(finalSignal::set);

StepVerifier.create(source)
    .expectSubscription()
    .expectNext(0L)
    .thenCancel()
    .verify();

assertEquals(1, cancelCount.get());
assertEquals(SignalType.CANCEL, finalSignal.get());
```

Test nhận tick đầu tiên rồi chủ động cancel. Hai assertion xác minh cancellation đã đến vị trí đặt `doOnCancel` và `doFinally` ghi nhận `SignalType.CANCEL`.

Nếu cần kiểm thử thời gian, dùng virtual time thay vì `Thread.sleep`:

```java
AtomicInteger cancelCount = new AtomicInteger();

StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofSeconds(1))
            .doOnCancel(cancelCount::incrementAndGet)
    )
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(1))
    .expectNext(0L)
    .thenCancel()
    .verify();

assertEquals(1, cancelCount.get());
```

Supplier truyền vào `withVirtualTime` tạo pipeline trong môi trường scheduler ảo. Cách này làm test nhanh và có thể lặp lại, đồng thời tránh phụ thuộc độ trễ của máy chạy test.

## 5. Xác minh cancellation được truyền đến upstream

Một toán tử hoặc adapter có thể nhận cancellation từ downstream nhưng không truyền đúng đến nguồn nếu có lỗi trong tích hợp. Reactor Test cung cấp `TestPublisher` để kiểm tra việc subscribe, request và cancel.

```java
TestPublisher<Integer> upstream = TestPublisher.create();
AtomicInteger cancelled = new AtomicInteger();

Flux<Integer> pipeline = upstream.flux()
    .doOnCancel(cancelled::incrementAndGet)
    .map(value -> value * 10);

StepVerifier.create(pipeline)
    .expectSubscription()
    .then(() -> upstream.assertWasSubscribed())
    .thenCancel()
    .verify();

upstream.assertCancelled();
assertEquals(1, cancelled.get());
```

`TestPublisher.assertCancelled()` xác nhận nguồn test đã nhận cancellation. Điều này đặc biệt hữu ích khi pipeline có operator tùy chỉnh, adapter callback hoặc wrapper Publisher do ứng dụng tự viết.

Với một nguồn ngoài thực tế, hãy xác minh hành động tương đương: listener đã được gỡ, request HTTP đã bị hủy, consumer đã dừng fetch hoặc task đã nhận tín hiệu dừng. `TestPublisher` chứng minh hợp đồng giữa các Publisher trong test; nó không chứng minh server từ xa đã rollback hoặc dừng side effect.

## 6. Quản lý tài nguyên đồng bộ bằng using

Khi tài nguyên được tạo riêng cho mỗi subscription và có thao tác cleanup đồng bộ, dùng `using` để gắn vòng đời tài nguyên với Publisher:

```java
Mono<String> read = Mono.using(
    Resource::open,
    resource -> resource.read(),
    Resource::close
);
```

Supplier tạo tài nguyên khi subscribe; hàm thứ hai sử dụng tài nguyên và trả về Publisher; hàm cleanup được gọi khi Publisher kết thúc hoặc bị cancel. Mỗi subscription có resource scope riêng.

Ví dụ kiểm thử cleanup khi cancel:

```java
AtomicInteger opened = new AtomicInteger();
AtomicInteger closed = new AtomicInteger();

Mono<String> operation = Mono.using(
    () -> {
        opened.incrementAndGet();
        return new Resource();
    },
    resource -> Mono.<String>never(),
    resource -> {
        resource.close();
        closed.incrementAndGet();
    }
);

StepVerifier.create(operation)
    .expectSubscription()
    .thenCancel()
    .verify();

assertEquals(1, opened.get());
assertEquals(1, closed.get());
```

Publisher bên trong là `Mono.never()`, nên không tự complete hoặc error. Test hủy subscription và xác nhận resource được mở đúng một lần rồi đóng đúng một lần.

Nếu tài nguyên cần được đóng bất đồng bộ, `using` không thể chờ một Publisher cleanup. Khi đó dùng `usingWhen`.

## 7. Quản lý cleanup bất đồng bộ bằng usingWhen

`usingWhen` cho phép định nghĩa Publisher cleanup riêng cho ba đường kết thúc: complete, error và cancel.

```java
Mono<Result> result = Mono.usingWhen(
    connectionFactory.create(),
    connection -> connection.query(sql),
    connection -> connection.close(),
    (connection, error) ->
        connection.rollback().then(connection.close()),
    connection ->
        connection.rollback().then(connection.close())
);
```

Trong ví dụ, connection được cấp theo subscription. Khi query hoàn tất bình thường, connection được đóng. Khi query lỗi hoặc downstream cancel, transaction được rollback rồi connection được đóng. Các hàm cleanup trả về `Publisher`, nên Reactor có thể phối hợp với công việc cleanup bất đồng bộ.

Ví dụ kiểm thử cleanup trên đường cancel:

```java
AtomicInteger cancelCleanup = new AtomicInteger();

Mono<String> operation = Mono.usingWhen(
    Mono.fromSupplier(Resource::new),
    resource -> Mono.<String>never(),
    resource -> Mono.fromRunnable(resource::close),
    (resource, error) -> Mono.fromRunnable(resource::close),
    resource -> Mono.fromRunnable(() -> {
        resource.close();
        cancelCleanup.incrementAndGet();
    })
);

StepVerifier.create(operation)
    .expectSubscription()
    .thenCancel()
    .verify();

assertEquals(1, cancelCleanup.get());
```

Ví dụ dùng Publisher cleanup đồng bộ để kiểm tra nhánh cancellation. Với cleanup thực sự bất đồng bộ, hãy xác minh Publisher cleanup hoàn tất bằng tín hiệu hoặc latch phù hợp trong test; không giả định việc gọi `cancel()` đồng nghĩa thao tác đóng từ xa đã hoàn tất ngay lập tức.

## 8. Kiểm thử riêng ba đường complete, error và cancel

Một resource scope đúng cần cleanup trong cả ba trường hợp. Có thể tạo ba test độc lập để tránh nhầm lẫn giữa các đường kết thúc:

```java
// Complete: cleanup chạy khi nguồn hoàn tất bình thường.
StepVerifier.create(resourceOperation(Mono.just("ok")))
    .expectNext("ok")
    .verifyComplete();

// Error: cleanup chạy khi nguồn phát lỗi.
StepVerifier.create(resourceOperation(
        Mono.error(new IllegalStateException("failed"))
    ))
    .expectErrorMessage("failed")
    .verify();

// Cancel: cleanup chạy khi downstream hủy.
StepVerifier.create(resourceOperation(Mono.never()))
    .expectSubscription()
    .thenCancel()
    .verify();
```

`resourceOperation` trong ví dụ là factory test tạo Publisher bằng `using` hoặc `usingWhen` và ghi nhận số lần cleanup. Mỗi test cần khởi tạo resource và bộ đếm mới để không chia sẻ trạng thái giữa các trường hợp.

Các assertion nên kiểm tra:

- Resource được tạo đúng số lần.
- Cleanup tương ứng được gọi đúng một lần cho mỗi resource.
- Cleanup complete/error/cancel không gọi nhầm nhánh.
- Lỗi gốc vẫn có thể chẩn đoán khi cleanup cũng thất bại.
- Không còn listener, timer, subscription hoặc connection bị giữ sau khi test kết thúc.

## 9. Kiểm thử phần tử bị discard khi cancel hoặc bị loại bỏ

Một phần tử có thể đã được upstream phát nhưng chưa đến `doOnNext` cuối pipeline. Ví dụ, `filter` loại bỏ phần tử không phù hợp. Với tài nguyên như pooled buffer, cần cleanup phần tử bị loại bởi operator có hỗ trợ discard.

```java
AtomicInteger discarded = new AtomicInteger();

Flux<Integer> values = Flux.range(1, 6)
    .filter(value -> value % 2 == 0)
    .doOnDiscard(Integer.class, value -> discarded.incrementAndGet());

StepVerifier.create(values)
    .expectNext(2, 4, 6)
    .verifyComplete();

assertEquals(3, discarded.get());
```

`doOnDiscard` phải được đặt downstream của operator có thể discard và chỉ có tác dụng với operator hỗ trợ discard. Trong ứng dụng, callback có thể gọi `release()` cho `DataBuffer` hoặc `ByteBuf` nếu pipeline sở hữu phần tử đó. Không dùng discard hook như một callback tổng quát cho mọi phần tử không được quan sát ở downstream.

Đối với queue nội bộ của operator, cancellation có thể làm các phần tử đã prefetch bị loại bỏ. Hãy kiểm tra discard support của đúng operator và phiên bản Reactor đang dùng. Không nên dựa vào giả định rằng mọi queue đều gọi hook giống nhau.

## 10. Cleanup phải an toàn khi có race giữa cancel và tín hiệu cuối

Cancellation có thể xảy ra gần thời điểm nguồn complete hoặc error. Khi một tín hiệu kết thúc đã thắng cuộc đua, đường cleanup tương ứng có thể là complete/error thay vì cancel. Không nên viết test dựa trên timing ngẫu nhiên để kỳ vọng luôn chạy một nhánh cụ thể.

Hãy dùng nguồn kiểm thử có thể điều khiển tín hiệu:

```java
TestPublisher<String> source = TestPublisher.create();
AtomicInteger completed = new AtomicInteger();
AtomicInteger cancelled = new AtomicInteger();

Flux<String> pipeline = source.flux()
    .doOnComplete(completed::incrementAndGet)
    .doOnCancel(cancelled::incrementAndGet);

StepVerifier.create(pipeline)
    .then(() -> source.next("value"))
    .expectNext("value")
    .thenCancel()
    .verify();

assertEquals(0, completed.get());
assertEquals(1, cancelled.get());
```

Test chủ động phát một phần tử rồi cancel trước khi nguồn complete. Nhờ vậy, đường cancellation được xác định rõ. Một test khác có thể gọi `source.complete()` để xác minh nhánh complete.

Cleanup nên được bảo vệ để không giải phóng cùng resource hai lần nếu nhiều đường điều khiển cùng có thể yêu cầu dọn dẹp. Cách tốt nhất vẫn là giao ownership cho một cơ chế quản lý vòng đời như `using`/`usingWhen`, thay vì tự ghép nhiều callback cleanup độc lập.

## 11. Tài nguyên blocking không nhất thiết dừng ngay khi cancel

Hủy subscription không thể buộc mọi API blocking dừng tức thời. Một lời gọi JDBC đồng bộ, đọc file blocking hoặc thư viện cũ có thể tiếp tục chạy cho đến khi API trả về hoặc timeout của chính nó hết hạn.

Ví dụ, đưa lời gọi blocking lên bounded elastic giúp không chặn event loop:

```java
Mono<Result> result = Mono.fromCallable(() -> legacyClient.call())
    .subscribeOn(Schedulers.boundedElastic());
```

Điều này không tự bảo đảm `legacyClient.call()` có thể bị ngắt khi subscription bị hủy. Cần dùng timeout/socket timeout của client, API có cơ chế interrupt/cancel nếu có, hoặc đóng resource underlying theo hợp đồng thư viện. Không nên giả định `doOnCancel` đã chạy nghĩa là tác vụ blocking đã dừng.

Với HTTP reactive như WebClient, cancellation có thể được truyền xuống connector để ngừng đọc hoặc hủy request. Tuy nhiên, server từ xa có thể đã thực hiện side effect trước khi nhận biết disconnect. Kiểm thử client cần xác minh request bị cancel và resource cục bộ được giải phóng; kiểm thử server cần xác minh hành vi disconnect riêng.

## 12. Kiểm thử cleanup lỗi

Cleanup cũng có thể thất bại: đóng connection trả lỗi, rollback không thành công hoặc xóa file tạm bị từ chối. Không nên âm thầm bỏ qua các lỗi này.

Với cleanup đồng bộ trong `using`, nếu cleanup ném exception, lỗi có thể ảnh hưởng đến tín hiệu kết thúc của Publisher. Với `usingWhen`, Publisher cleanup có thể phát lỗi; cần định nghĩa cách ghi log, metrics, retry cleanup nếu an toàn hoặc đưa resource vào quy trình phục hồi.

Một số nguyên tắc:

- Giữ lại nguyên nhân lỗi chính và thông tin lỗi cleanup để chẩn đoán.
- Không retry vô hạn thao tác cleanup.
- Cleanup phải có timeout nếu nó phụ thuộc mạng hoặc dịch vụ bên ngoài.
- Không đánh dấu resource đã giải phóng nếu thao tác đóng chưa thành công.
- Có cơ chế phát hiện resource rò rỉ hoặc transaction còn mở sau test.

Test cleanup lỗi nên xác minh tín hiệu quan sát được theo semantics của API đang dùng, thay vì chỉ kiểm tra callback đã được gọi. Với tài nguyên có trạng thái, hãy kiểm tra trạng thái đóng/rollback thực tế.

## 13. Dọn dẹp listener và callback nguồn nóng

Khi bọc API callback bằng `Flux.create` hoặc `Mono.create`, đăng ký listener khi subscribe và gỡ listener khi cancel/dispose:

```java
Flux<SensorReading> readings = Flux.create(sink -> {
    SensorListener listener = sink::next;
    sensor.register(listener);

    sink.onDispose(() -> sensor.unregister(listener));
});
```

`onDispose` chạy khi sink bị dispose do cancellation hoặc kết thúc; nó phù hợp để gỡ listener đồng bộ. Nếu việc gỡ đăng ký là bất đồng bộ, cần chuyển sang mô hình resource cleanup trả Publisher hoặc quản lý lifecycle ở lớp tích hợp tương ứng.

Kiểm thử listener:

```java
AtomicInteger registered = new AtomicInteger();
AtomicInteger unregistered = new AtomicInteger();

Flux<SensorReading> readings = Flux.create(sink -> {
    registered.incrementAndGet();
    sink.onDispose(unregistered::incrementAndGet);
});

StepVerifier.create(readings)
    .expectSubscription()
    .thenCancel()
    .verify();

assertEquals(1, registered.get());
assertEquals(1, unregistered.get());
```

Trong test thực tế, thay bộ đếm bằng sensor fake có thể xác minh đúng listener instance đã được đăng ký và gỡ bỏ. Cũng cần kiểm tra trường hợp source complete hoặc error để listener không bị giữ lại.

## 14. Checklist kiểm thử cancellation và resource cleanup

Trước khi xem pipeline là an toàn, hãy kiểm tra:

1. Có những tình huống nào kích hoạt cancel: caller, timeout, `take`, disconnect hay shutdown?
2. Cancellation có truyền đến Publisher nguồn hoặc adapter callback không?
3. Listener, timer, task, connection và resource scope được đóng ở đâu?
4. Cleanup chạy trên complete, error và cancel hay chỉ trên một đường?
5. Tài nguyên đồng bộ dùng `using`; cleanup bất đồng bộ dùng `usingWhen` khi phù hợp chưa?
6. Phần tử bị filter/drop/discard hoặc còn trong queue có được giải phóng không?
7. Có nguy cơ double release hoặc cleanup nhiều lần không?
8. Tác vụ blocking có timeout hoặc cơ chế dừng riêng không?
9. Cleanup error có được quan sát và xử lý không?
10. Test có dùng `StepVerifier`, `TestPublisher` và virtual time để điều khiển tín hiệu một cách xác định không?
11. Test có xác minh trạng thái tài nguyên sau khi hủy, không chỉ xác minh callback đã chạy không?
12. Có test riêng cho race, disconnect và shutdown khi công việc đang hoạt động không?

Cancellation là một đường kết thúc bình thường của pipeline reactive và phải được kiểm thử như complete và error. `StepVerifier.thenCancel()` giúp chủ động tạo tình huống hủy; `TestPublisher` xác minh cancellation truyền đến upstream; `doOnCancel` và `doFinally` quan sát tín hiệu; `using` và `usingWhen` gắn cleanup với vòng đời subscription. Khi kiểm tra thêm discard, listener, tác vụ blocking và lỗi cleanup, ta có thể phát hiện sớm resource leak và công việc tiếp tục chạy sau khi downstream không còn cần dữ liệu.
