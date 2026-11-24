# Lựa chọn toán tử tương đương và khác biệt về ngữ nghĩa

Khi chuyển một pipeline giữa Reactor và RxJava, tên toán tử giống nhau không bảo đảm hành vi giống nhau trong mọi trường hợp. Hai thư viện cùng dựa trên mô hình reactive và có nhiều phép biến đổi tương tự, nhưng hệ kiểu, backpressure, cách biểu diễn nguồn rỗng và một số chi tiết về scheduler hoặc lỗi khác nhau. Chọn toán tử tương đương cần bắt đầu từ hợp đồng dữ liệu và tín hiệu mà ứng dụng mong muốn, sau đó mới ánh xạ sang API của thư viện đích.

Bài học thuộc chương **RxJava** của module `REACTIVE_PROGRAMMING`. Module hướng dẫn tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams; người học thực hành `Mono`, `Flux`, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Trọng tâm ở đây là đối chiếu Reactor với RxJava 3, nhận diện các toán tử tương đương và kiểm tra những khác biệt có thể làm thay đổi kết quả khi chuyển đổi pipeline.

Sau bài học, bạn có thể:

- Ánh xạ các kiểu nguồn Reactor sang kiểu nguồn RxJava phù hợp.
- Chọn đúng toán tử cho map, flatMap, zip, fallback và xử lý lỗi.
- Phân biệt `subscribeOn`/`publishOn` của Reactor với `subscribeOn`/`observeOn` của RxJava.
- Nhận diện khác biệt giữa `Flowable` và `Observable` về backpressure.
- Giữ đúng semantics khi một nguồn empty, error, phát nhiều phần tử hoặc bị hủy.
- Thiết kế kiểm thử tương đương bằng `StepVerifier`, `TestObserver` và `TestSubscriber`.

## 1. Bắt đầu từ kiểu nguồn, không bắt đầu từ tên toán tử

Reactor và RxJava có các kiểu Publisher khác nhau. Trước khi thay một operator, hãy xác định nguồn có thể phát bao nhiêu phần tử và có hỗ trợ backpressure hay không.

| Nhu cầu | Reactor | RxJava 3 | Ngữ nghĩa cần giữ |
|---|---|---|---|
| Không hoặc một phần tử | `Mono<T>` | `Maybe<T>` | Có thể hoàn tất empty hoặc phát một giá trị. |
| Chính xác một phần tử hoặc lỗi | Không có kiểu riêng tương ứng trực tiếp; `Mono<T>` vẫn có thể empty | `Single<T>` | `Single` phải phát đúng một giá trị hoặc lỗi. |
| Luồng nhiều phần tử có backpressure | `Flux<T>` | `Flowable<T>` | Consumer điều tiết nhu cầu qua Reactive Streams. |
| Luồng nhiều phần tử không có backpressure | Không có kiểu tương đương trực tiếp trong Reactor Core | `Observable<T>` | Nguồn không tham gia giao thức `request(n)` của Reactive Streams. |
| Chỉ biểu diễn hoàn tất hoặc lỗi | `Mono<Void>` | `Completable` | Không phát giá trị `onNext`. |

Một số ánh xạ thường gặp:

```java
// Reactor
Mono<User> userMono = userRepository.findById(id);
Flux<Order> ordersFlux = orderRepository.findAll();
Mono<Void> saved = auditRepository.save(event).then();

// RxJava 3
Maybe<User> userMaybe = userRepository.findById(id);
Flowable<Order> ordersFlowable = orderRepository.findAll();
Completable savedCompletable = auditRepository.save(event).ignoreElements();
```

Các đoạn mã minh họa kiểu trả về; API repository cụ thể phụ thuộc ứng dụng. Không nên chuyển `Mono<T>` sang `Single<T>` một cách máy móc nếu nguồn Reactor có thể empty. Khi đó cần định nghĩa rõ cách xử lý empty, ví dụ chuyển sang `Maybe<T>` hoặc dùng `switchIfEmpty` trước khi tạo `Single`.

### `Flux` và `Flowable` có backpressure; `Observable` thì không

`Flux` và `Flowable` đều triển khai Reactive Streams Publisher và hỗ trợ demand qua `Subscription.request(n)`. `Observable` của RxJava không triển khai giao thức Reactive Streams và không có backpressure theo hợp đồng `request(n)`.

Vì vậy:

- Khi chuyển `Flux` sang RxJava, `Flowable` thường là lựa chọn gần nhất.
- Khi dùng `Observable`, phải xác định chính sách nếu producer nhanh hơn consumer: buffer, sample, throttle, drop hoặc giới hạn tốc độ ở tầng ứng dụng.
- Khi chuyển `Observable` sang Reactor, cần chọn cách chuyển đổi có chính sách backpressure rõ ràng; không nên giả định nguồn sẽ tự tôn trọng demand.

Đây là khác biệt về hợp đồng, không chỉ là khác tên class. Một pipeline có thể biên dịch sau khi thay `Flowable` bằng `Observable`, nhưng hành vi khi tải tăng cao có thể thay đổi đáng kể.

## 2. Nguồn dữ liệu và cách biểu diễn empty

Các nguồn tạo giá trị cơ bản khá tương đồng:

| Ý định | Reactor | RxJava 3 |
|---|---|---|
| Phát một giá trị | `Mono.just(value)` | `Maybe.just(value)`, `Single.just(value)` hoặc `Flowable.just(value)` |
| Không phát giá trị rồi hoàn tất | `Mono.empty()` / `Flux.empty()` | `Maybe.empty()`, `Flowable.empty()` hoặc `Observable.empty()` |
| Phát lỗi | `Mono.error(error)` / `Flux.error(error)` | `Maybe.error(error)`, `Single.error(error)`, `Flowable.error(error)` |
| Tạo nguồn theo subscription | `Mono.defer(...)` / `Flux.defer(...)` | `Maybe.defer(...)`, `Single.defer(...)`, `Flowable.defer(...)` |
| Giá trị đồng bộ có thể ném lỗi | `Mono.fromCallable(...)` | `Maybe.fromCallable(...)`, `Single.fromCallable(...)` hoặc `Flowable.fromCallable(...)` |

Ví dụ, truy vấn hồ sơ có thể không tìm thấy:

```java
// Reactor: 0..1 kết quả
Mono<User> user = repository.findById(id);

// RxJava: 0..1 kết quả
Maybe<User> user = repository.findById(id);
```

Nếu chuyển sang `Single<User>`, cần quyết định empty sẽ trở thành lỗi, giá trị mặc định hay một nhánh khác. `Single` không có trạng thái hoàn tất empty: nó phải phát đúng một giá trị hoặc `onError`.

### Empty không giống null

Reactor và RxJava đều không cho phép phát `null` như một phần tử reactive. Hãy biểu diễn không có kết quả bằng empty source hoặc một kiểu dữ liệu mô tả trạng thái. Không chuyển `Mono.empty()` thành `Maybe.just(null)` hay cố phát null qua `Flowable`/`Observable`.

### Nguồn hoàn tất-only

`Mono<Void>` thường tương đương về ý định với `Completable`: caller chỉ cần biết thao tác hoàn tất hay lỗi.

```java
// Reactor
Mono<Void> writeAudit = auditRepository.save(event).then();

// RxJava 3
Completable writeAudit = auditRepository.save(event).ignoreElement();
```

Khi ghép nhiều thao tác completion-only, Reactor thường dùng `Mono.when(...)`; RxJava dùng `Completable.merge(...)` hoặc các operator kết hợp Completable phù hợp. Hãy kiểm tra chính sách lỗi và cancellation của operator được chọn thay vì chỉ đổi tên.

## 3. Ánh xạ các toán tử biến đổi cơ bản

Các phép biến đổi một-một có cách dùng tương tự:

| Ý định | Reactor | RxJava 3 |
|---|---|---|
| Biến đổi giá trị | `map` | `map` |
| Biến đổi thành Publisher rồi flatten | `flatMap` | `flatMap` |
| Ghép tuần tự, giữ thứ tự | `concatMap` | `concatMap` |
| Ghép các nguồn theo thứ tự đến | `flatMap` | `flatMap` |
| Lọc phần tử | `filter` | `filter` |
| Bỏ một số phần tử đầu | `skip` | `skip` |
| Giới hạn số phần tử | `take` | `take` |
| Chỉ phát phần tử đầu tiên phù hợp | `next`, `filter(...).next()` | `firstElement`, `first` hoặc `take(1)` tùy kiểu nguồn |

Ví dụ chuyển một bước tra cứu bất đồng bộ:

```java
// Reactor
Flux<Profile> profiles = userIds
    .flatMap(userId -> profileClient.find(userId));

// RxJava 3
Flowable<Profile> profiles = userIds
    .flatMap(userId -> profileClient.find(userId));
```

Trong cả hai thư viện, `flatMap` có thể cho phép các Publisher con chạy đồng thời và kết quả được phát theo thời điểm hoàn tất. Nếu thứ tự nguồn cần được giữ, dùng `concatMap`. Trong RxJava, `concatMapEager` có thể subscribe các inner Publisher sớm nhưng vẫn phát theo thứ tự nguồn; trong Reactor, `flatMapSequential` cung cấp mô hình tương tự về việc subscribe inner có concurrency nhưng giữ thứ tự đầu ra.

Đừng thay `flatMap` bằng `concatMap` chỉ để “an toàn”. Điều đó thay đổi concurrency và có thể giảm throughput. Ngược lại, không dùng `flatMap` nếu nghiệp vụ đòi hỏi kết quả theo thứ tự đầu vào.

## 4. `zip`, `combineLatest` và `merge` không thể thay thế tùy ý

Ba cách kết hợp nguồn có semantics khác nhau trong cả Reactor lẫn RxJava.

| Toán tử | Cách kết hợp | Khi nào dùng |
|---|---|---|
| `zip` | Ghép phần tử thứ n của mỗi nguồn thành một tuple/kết quả | Cần một bộ giá trị tương ứng theo vị trí. |
| `combineLatest` | Sau khi mỗi nguồn có ít nhất một giá trị, kết hợp giá trị mới nhất của tất cả nguồn mỗi khi một nguồn cập nhật | Cần trạng thái tổng hợp luôn phản ánh dữ liệu mới nhất. |
| `merge` | Chuyển tiếp phần tử từ nhiều nguồn theo thời điểm chúng đến | Nguồn độc lập, không cần ghép cặp. |

Ví dụ `zip`:

```java
// Reactor
Mono<Summary> summary = Mono.zip(
    loadCustomer(id),
    loadBalance(id),
    Summary::new
);

// RxJava 3
Maybe<Summary> summary = Maybe.zip(
    loadCustomer(id),
    loadBalance(id),
    Summary::new
);
```

Nếu một nguồn `Mono` hoàn tất empty, `Mono.zip` không thể tạo đủ tuple và kết quả hoàn tất empty. Với `Maybe.zip`, nếu một nguồn empty thì Maybe tổng hợp cũng empty. Khi chuyển sang `Single.zip`, mỗi nguồn phải phát đúng một giá trị hoặc lỗi, vì `Single` không thể empty.

Ví dụ `combineLatest` phù hợp cho giao diện theo dõi trạng thái:

```java
// Reactor
Flux<DashboardState> state = Flux.combineLatest(
    cpuUsage,
    memoryUsage,
    DashboardState::new
);

// RxJava 3
Flowable<DashboardState> state = Flowable.combineLatest(
    cpuUsage,
    memoryUsage,
    DashboardState::new
);
```

Không thay `zip` bằng `combineLatest` nếu mỗi bản ghi phải ghép đúng theo vị trí. `combineLatest` có thể tạo nhiều trạng thái lặp lại với cùng giá trị mới nhất của một nguồn khi nguồn khác tiếp tục phát.

## 5. Fallback: `switchIfEmpty`, `defaultIfEmpty` và xử lý lỗi

Reactor và RxJava có các toán tử cùng tên hoặc gần nghĩa, nhưng kiểu nguồn quyết định overload có sẵn và kết quả cuối cùng.

| Ý định | Reactor | RxJava 3 |
|---|---|---|
| Thay nguồn empty bằng Publisher khác | `switchIfEmpty` | `switchIfEmpty` trên các kiểu hỗ trợ |
| Phát giá trị mặc định nếu empty | `defaultIfEmpty` | `defaultIfEmpty` |
| Thay lỗi bằng giá trị cố định | `onErrorReturn` | `onErrorReturnItem` hoặc `onErrorReturn` |
| Thay lỗi bằng Publisher khác | `onErrorResume` | `onErrorResumeNext` |
| Chuyển lỗi sang exception khác | `onErrorMap` | `onErrorResumeNext` tạo nguồn lỗi mới hoặc `map` lỗi theo kiểu nguồn |

Ví dụ fallback khi cache empty:

```java
// Reactor
Mono<User> user = cache.find(id)
    .switchIfEmpty(remote.find(id));

// RxJava 3
Maybe<User> user = cache.find(id)
    .switchIfEmpty(remote.find(id));
```

Ví dụ fallback khi nguồn lỗi:

```java
// Reactor
Mono<User> user = remote.find(id)
    .onErrorResume(TimeoutException.class,
        error -> cache.find(id));

// RxJava 3
Maybe<User> user = remote.find(id)
    .onErrorResumeNext(error -> {
        if (error instanceof TimeoutException) {
            return cache.find(id);
        }
        return Maybe.error(error);
    });
```

Hai đoạn code đều phục hồi timeout bằng cache. RxJava `onErrorResumeNext` nhận function trả về nguồn thay thế; nếu chỉ muốn phát một giá trị mặc định, `onErrorReturnItem` có thể rõ ràng hơn. Hãy kiểm tra overload theo loại nguồn (`Maybe`, `Single`, `Flowable`, `Observable`) vì API không hoàn toàn giống nhau giữa các kiểu.

### Error và empty phải có chính sách riêng

`switchIfEmpty` xử lý `onComplete` không có phần tử. `onErrorResume`/`onErrorResumeNext` xử lý `onError`. Không có toán tử fallback nào tự động coi cancellation là lỗi. Khi chuyển pipeline, hãy giữ riêng ba trường hợp:

- Không tìm thấy dữ liệu: empty hoặc giá trị mặc định theo nghiệp vụ.
- Dịch vụ thất bại: lỗi, có thể retry hoặc chuyển nguồn dự phòng.
- Caller hủy: dừng công việc và giải phóng tài nguyên.

## 6. `subscribeOn` và `publishOn` so với `subscribeOn` và `observeOn`

Đây là một khác biệt quan trọng khi chuyển code có scheduler.

| Mục đích | Reactor | RxJava 3 |
|---|---|---|
| Điều phối subscription của nguồn | `subscribeOn(scheduler)` | `subscribeOn(scheduler)` |
| Chuyển nơi xử lý tín hiệu downstream tại một vị trí | `publishOn(scheduler)` | `observeOn(scheduler)` |

Ví dụ:

```java
// Reactor
Mono<Result> result = Mono.fromCallable(this::blockingCall)
    .subscribeOn(Schedulers.boundedElastic())
    .publishOn(Schedulers.parallel())
    .map(this::calculate);

// RxJava 3
Single<Result> result = Single.fromCallable(this::blockingCall)
    .subscribeOn(Schedulers.io())
    .observeOn(Schedulers.computation())
    .map(this::calculate);
```

Ý định tương đương: thực hiện lời gọi blocking trên scheduler dành cho I/O, sau đó chuyển kết quả sang scheduler tính toán. Nhưng scheduler cụ thể và chính sách pool khác nhau. Reactor `boundedElastic` có giới hạn tài nguyên theo cấu hình; RxJava `Schedulers.io()` có semantics pool I/O riêng. Không thay scheduler chỉ dựa trên tên gần giống; hãy xem cấu hình, giới hạn thread, queue và vòng đời của từng thư viện.

`publishOn` và `observeOn` đều tạo ranh giới xử lý tín hiệu downstream, nhưng chi tiết prefetch, queue, fusion và overload khác nhau. Một pipeline có thể giữ đúng kết quả mà vẫn có latency hoặc mức sử dụng bộ nhớ khác sau khi chuyển đổi. Đo tải thực tế nếu hiệu năng quan trọng.

## 7. Side effect và thứ tự callback

Các operator quan sát side effect có tên khá giống:

| Mục đích | Reactor | RxJava 3 |
|---|---|---|
| Quan sát phần tử trước khi chuyển downstream | `doOnNext` | `doOnNext` |
| Quan sát sau khi downstream xử lý phần tử | `doAfterNext` | `doAfterNext` |
| Quan sát lỗi | `doOnError` | `doOnError` |
| Quan sát subscription | `doOnSubscribe` | `doOnSubscribe` |
| Quan sát cancellation | `doOnCancel` | `doOnCancel` |
| Hook khi kết thúc bằng complete/error/cancel | `doFinally` | `doFinally` |

Ví dụ:

```java
// Reactor
Flux<Event> observed = events
    .doOnNext(event -> metrics.received())
    .doAfterNext(event -> metrics.afterDownstream(event));

// RxJava 3
Flowable<Event> observed = events
    .doOnNext(event -> metrics.received())
    .doAfterNext(event -> metrics.afterDownstream(event));
```

Tên operator tương đương không làm cho side effect trở nên an toàn khi chạy đồng thời. Nếu downstream xử lý trên nhiều thread hoặc nhiều subscription, bộ đếm và cấu trúc dùng chung vẫn cần atomic, khóa hoặc một chiến lược sở hữu trạng thái phù hợp.

Tránh đặt nghiệp vụ quan trọng chỉ trong `doOnNext` nếu cần retry, transaction hoặc bảo đảm thực thi. Các operator `doOn...` chủ yếu để quan sát; việc biến đổi kết quả hoặc điều khiển luồng nên được thể hiện bằng operator chức năng tương ứng.

## 8. Timeout, retry và cancellation

Reactor và RxJava đều có toán tử timeout và retry, nhưng cách cấu hình backoff, filter lỗi, scheduler và overload có thể khác nhau.

```java
// Reactor
Mono<Response> response = client.call()
    .timeout(Duration.ofSeconds(2))
    .retryWhen(Retry.max(2)
        .filter(TransientException.class::isInstance));

// RxJava 3 (minh họa)
Single<Response> response = client.call()
    .timeout(2, TimeUnit.SECONDS)
    .retry(2, error -> error instanceof TransientException);
```

Hai đoạn minh họa cùng mục tiêu giới hạn thời gian và thử lại lỗi tạm thời, nhưng không nên coi cấu hình là tương đương tuyệt đối: Reactor `Retry` và RxJava `retry` có API, backoff và cách đếm lần thử riêng. Nếu cần delay, jitter hoặc giới hạn tổng thời gian, hãy cấu hình chính sách cụ thể trong thư viện đích.

Cancellation cũng cần được giữ đúng. Reactor subscription và RxJava `Disposable`/`Subscription` có API khác nhau tùy kiểu nguồn. `Flowable` sử dụng Reactive Streams Subscription; `Observable`, `Single`, `Maybe` và `Completable` thường trả về `Disposable` khi subscribe bằng consumer API. Khi chuyển code, cần bảo đảm dispose/cancel được nối với vòng đời request và tài nguyên.

Không được biến cancellation thành retry hoặc fallback. Nếu caller đã hủy, việc tự khởi động lại nguồn có thể tiếp tục công việc mà không còn ai nhận kết quả.

## 9. Chuyển đổi giữa Reactor và RxJava

Khi hai thư viện cùng tham gia một ứng dụng, có thể cần chuyển Publisher qua ranh giới API.

### Từ Reactor sang RxJava

`Flux` và `Mono` triển khai Reactive Streams Publisher, vì vậy có thể chuyển sang `Flowable` bằng `Flowable.fromPublisher`:

```java
Flux<Order> reactorOrders = orderService.findAll();

Flowable<Order> rxOrders = Flowable.fromPublisher(reactorOrders);
```

Với `Mono<T>`, hãy quyết định cách biểu diễn empty:

```java
Mono<User> reactorUser = userService.find(id);

Maybe<User> rxUser = Maybe.fromPublisher(reactorUser);
```

`Maybe` phù hợp với 0..1 phần tử. Nếu cần `Single`, phải bảo đảm nguồn có đúng một phần tử hoặc chuyển empty thành lỗi/giá trị mặc định trước khi chuyển.

### Từ RxJava sang Reactor

`Flowable` triển khai Reactive Streams Publisher nên có thể dùng `Flux.from`:

```java
Flowable<Order> rxOrders = orderService.findAll();

Flux<Order> reactorOrders = Flux.from(rxOrders);
```

`Maybe<T>` cũng là Publisher và có thể chuyển thành `Mono<T>`:

```java
Maybe<User> rxUser = userService.find(id);

Mono<User> reactorUser = Mono.from(rxUser);
```

`Observable<T>` không triển khai Reactive Streams Publisher vì không có giao thức demand. Muốn chuyển sang Reactor, cần chọn cầu nối hoặc chính sách chuyển đổi cụ thể để xử lý tốc độ nguồn và overflow. Không ép kiểu trực tiếp `Observable` thành `Publisher`.

### Ranh giới chuyển đổi không tự đồng bộ Context

Reactor Context và các cơ chế context của RxJava không phải cùng một kho metadata. Khi chuyển qua Publisher boundary, request ID, tracing hoặc security metadata không tự động được sao chép giữa hai thư viện. Hãy truyền metadata tường minh, dùng bridge tương thích hoặc cấu hình context propagation tại ranh giới tích hợp.

## 10. Kiểm thử tương đương trong hai thư viện

Reactor thường dùng `StepVerifier`; RxJava cung cấp `TestObserver` cho kiểu nguồn không backpressure và `TestSubscriber` cho `Flowable`.

### Kiểm thử giá trị và completion

```java
// Reactor
StepVerifier.create(Flux.just(1, 2, 3).map(value -> value * 2))
    .expectNext(2, 4, 6)
    .verifyComplete();

// RxJava 3
Flowable.just(1, 2, 3)
    .map(value -> value * 2)
    .test()
    .assertResult(2, 4, 6);
```

### Kiểm thử nguồn empty

```java
// Reactor
StepVerifier.create(Mono.<String>empty())
    .verifyComplete();

// RxJava 3
Maybe.<String>empty()
    .test()
    .assertResult();
```

### Kiểm thử fallback khi lỗi

```java
// Reactor
StepVerifier.create(
        Mono.<String>error(new TimeoutException())
            .onErrorResume(error -> Mono.just("backup"))
    )
    .expectNext("backup")
    .verifyComplete();

// RxJava 3
Maybe.<String>error(new TimeoutException())
    .onErrorResumeNext(error -> Maybe.just("backup"))
    .test()
    .assertResult("backup");
```

### Kiểm thử demand

Với Reactor, `StepVerifier` có thể khởi tạo demand bằng `0` rồi yêu cầu từng lô bằng `thenRequest`. Với RxJava `Flowable`, `TestSubscriber` cho phép điều khiển request:

```java
TestSubscriber<Integer> subscriber = new TestSubscriber<>(0L);

Flowable.range(1, 3).subscribe(subscriber);

subscriber.assertNoValues();
subscriber.request(1);
subscriber.assertValues(1);
subscriber.request(2);
subscriber.assertValues(1, 2, 3);
subscriber.assertComplete();
```

Đây là kiểm thử quan trọng khi chuyển từ `Flux` sang `Flowable`: cần xác nhận demand và không phát vượt quá số phần tử được yêu cầu. `Observable` không thể được kiểm thử bằng cùng hợp đồng request vì nó không có backpressure.

Khi chuyển pipeline thực tế, hãy tạo bộ kiểm thử dùng chung cho các trường hợp: nguồn empty, lỗi, fallback, nguồn ngắn hơn khi zip, thứ tự `flatMap`/`concatMap`, timeout, cancellation và demand. Kiểm thử cùng dữ liệu đầu vào trên hai triển khai giúp phát hiện khác biệt ngữ nghĩa sớm.

## 11. Bảng chọn nhanh khi chuyển toán tử

| Ý định nghiệp vụ | Chọn trong Reactor | Chọn trong RxJava 3 | Điểm cần xác minh |
|---|---|---|---|
| Nguồn có 0..1 giá trị | `Mono<T>` | `Maybe<T>` | Empty phải được giữ hay chuyển thành default/error? |
| Nguồn có đúng 1 giá trị | `Mono<T>` với invariant rõ ràng | `Single<T>` | Nguồn Reactor có thể empty không? |
| Nguồn nhiều phần tử có demand | `Flux<T>` | `Flowable<T>` | Prefetch, buffer và request semantics. |
| Nguồn completion-only | `Mono<Void>` | `Completable` | Chỉ cần completion hay cần payload? |
| Ghép từng cặp theo vị trí | `zip` | `zip` | Một nguồn empty hoặc ngắn hơn sẽ làm kết quả kết thúc thế nào? |
| Ghép trạng thái mới nhất | `combineLatest` | `combineLatest` | Khi nào mọi nguồn đã phát giá trị đầu tiên? |
| Thay nguồn empty | `switchIfEmpty` | `switchIfEmpty` | Empty khác error. |
| Thay lỗi bằng nguồn khác | `onErrorResume` | `onErrorResumeNext` | Chỉ phục hồi loại lỗi nào? |
| Chuyển execution context downstream | `publishOn` | `observeOn` | Prefetch, queue và scheduler khác nhau. |
| Điều phối subscribe nguồn | `subscribeOn` | `subscribeOn` | Nguồn thực sự được subscribe trên scheduler nào? |

## 12. Những lỗi thường gặp

| Cách làm sai | Hậu quả | Cách xử lý |
|---|---|---|
| Chuyển `Mono<T>` có thể empty thành `Single<T>` mà không xử lý empty | Hợp đồng 0..1 bị đổi thành đúng 1 hoặc lỗi. | Dùng `Maybe<T>` hoặc định nghĩa fallback trước khi chuyển. |
| Thay `Flowable` bằng `Observable` | Mất giao thức backpressure và khả năng điều tiết demand. | Giữ `Flowable` khi cần Reactive Streams hoặc đặt chính sách overflow rõ ràng. |
| Xem `zip` và `combineLatest` là tương đương | Dữ liệu có thể ghép sai cặp hoặc phát nhiều trạng thái ngoài ý muốn. | Chọn theo ghép vị trí hay kết hợp giá trị mới nhất. |
| Đổi `flatMap` thành `concatMap` mà không xét concurrency | Thay đổi thứ tự và throughput. | Chỉ tuần tự hóa khi nghiệp vụ yêu cầu. |
| Đổi `publishOn` thành `observeOn` mà không đo lại | Queue, prefetch và scheduler có thể khác. | Kiểm thử demand, latency và bộ nhớ trên thư viện đích. |
| Phục hồi mọi lỗi bằng fallback | Lỗi không thể phục hồi bị che giấu. | Lọc loại lỗi và ghi nhận sự cố nguồn chính. |
| Giả định Context tự đi qua ranh giới hai thư viện | Metadata request hoặc tracing có thể bị mất. | Bridge hoặc truyền metadata tường minh. |
| Chỉ kiểm thử giá trị đầu ra | Bỏ sót khác biệt về demand, cancellation và terminal signal. | Bổ sung kiểm thử protocol bằng StepVerifier/TestSubscriber. |

## 13. Checklist trước khi chuyển pipeline

- Đã xác định nguồn là 0..1, đúng 1, 0..N có backpressure hay 0..N không backpressure chưa?
- Empty có giữ nguyên hay cần chuyển thành giá trị mặc định/lỗi?
- `zip`, `combineLatest` và `merge` đang được dùng theo đúng semantics chưa?
- Concurrency và thứ tự của `flatMap`, `concatMap` hoặc biến thể eager có được giữ không?
- Fallback chỉ xử lý lỗi được phép và không bị nhầm với empty/cancellation chưa?
- Scheduler, prefetch và queue có được đánh giá lại trong thư viện đích chưa?
- Tài nguyên có được giải phóng khi complete, error và cancel không?
- Context, tracing và security metadata có được truyền qua ranh giới thư viện không?
- Kiểm thử đã xác nhận giá trị, terminal signal, demand, thứ tự và cancellation chưa?

Khi chuyển giữa Reactor và RxJava, hãy giữ hợp đồng nguồn, tín hiệu và backpressure trước khi thay tên operator. `Mono` gần với `Maybe` trong trường hợp 0..1, `Flux` gần với `Flowable` khi cần demand, còn các phép kết hợp và xử lý lỗi cần được chọn theo semantics cụ thể. Kiểm thử cùng tình huống trên cả hai thư viện giúp bảo đảm pipeline mới giữ đúng hành vi, kể cả ở các trường hợp empty, lỗi, tải cao và cancellation.
