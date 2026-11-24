# Đặt phục hồi lỗi sai vị trí làm kết thúc toàn bộ nguồn

Trong Reactor, một lỗi là tín hiệu kết thúc (*terminal signal*) của publisher. Khi `Flux` phát `onError`, publisher đó không tiếp tục phát các phần tử còn lại. Một lỗi xảy ra khi xử lý một phần tử trong `flatMap` có thể lan ra toàn bộ `Flux` nếu operator phục hồi được đặt ở sai tầng. Khi đó, một bản ghi lỗi có thể làm dừng cả batch, hủy các publisher con đang chạy và khiến những phần tử chưa được xử lý bị bỏ qua.

Vấn đề thường gặp là đặt `onErrorResume` ở cuối pipeline trong khi mong muốn chỉ thay thế kết quả của một phần tử. `onErrorResume` ở ngoài `flatMap` nhìn thấy lỗi của toàn bộ chuỗi đã merge; khi nó chuyển sang publisher dự phòng, nguồn ban đầu đã kết thúc. Muốn cô lập lỗi theo từng phần tử, hãy đặt chính sách phục hồi bên trong publisher con được tạo cho phần tử đó.

Bài học thuộc chương **Lỗi thường gặp** của module `REACTIVE_PROGRAMMING`, nơi người học thực hành các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams; đồng thời sử dụng `Mono`, `Flux`, operator, scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java.

## 1. Lỗi là tín hiệu kết thúc của publisher

Reactive Streams định nghĩa ba loại tín hiệu chính từ publisher đến subscriber:

- `onNext(value)`: phát một phần tử dữ liệu.
- `onComplete()`: kết thúc bình thường.
- `onError(error)`: kết thúc do lỗi.

`onComplete` và `onError` là terminal signal. Sau khi một trong hai tín hiệu này được phát, publisher không được phát thêm `onNext` hoặc terminal signal thứ hai cho subscription đó.

Điều này có nghĩa `onErrorResume` không thể yêu cầu publisher cũ tiếp tục từ đúng phần tử kế tiếp sau khi lỗi đã xảy ra. Operator này chuyển sang một publisher thay thế để hoàn thành phần downstream còn lại. Publisher ban đầu vẫn đã kết thúc.

Với `Mono`, phạm vi lỗi thường là một kết quả. Với `Flux`, phạm vi có thể là toàn bộ chuỗi nhiều phần tử hoặc chỉ một publisher con được tạo cho mỗi phần tử. Vị trí đặt operator quyết định phạm vi nào được phục hồi.

## 2. Nhầm lẫn phổ biến: phục hồi ở ngoài `flatMap`

Giả sử ứng dụng xử lý danh sách mã đơn hàng. Mỗi mã được gửi đến service để tải chi tiết. Một đơn hàng không tồn tại hoặc có dữ liệu không hợp lệ có thể được thay bằng kết quả `Rejected`, trong khi những đơn hàng còn lại vẫn cần xử lý.

Đoạn code sau đặt phục hồi ở cuối pipeline:

```java
Flux<OrderResult> results = orderIds
    .flatMap(orderService::process)
    .onErrorResume(error ->
        Flux.just(OrderResult.batchFailed(error))
    );
```

`onErrorResume` đang gắn với `Flux<OrderResult>` sau `flatMap`. Nếu bất kỳ publisher con nào phát lỗi, lỗi đó đi ra khỏi `flatMap` và kết thúc publisher kết quả. Operator phục hồi sau đó nhận lỗi của toàn bộ luồng và chuyển sang `Flux.just(...)`.

Hành vi này có thể gây ra các hệ quả:

- Các phần tử nguồn chưa được xử lý có thể không được đưa vào mapper nữa.
- Những publisher con còn hoạt động có thể bị hủy theo chính sách lỗi mặc định của `flatMap`.
- Kết quả đã phát trước lỗi vẫn có thể đã đến downstream, nhưng publisher dự phòng không khôi phục các phần tử còn thiếu.
- Kết quả fallback mang ý nghĩa “batch đã chuyển sang nhánh dự phòng”, không phải “chỉ riêng đơn hàng lỗi đã được thay thế”.

Nếu mục tiêu nghiệp vụ là cô lập lỗi từng đơn hàng, đây là vị trí phục hồi sai.

## 3. Phục hồi bên trong publisher con

Đặt `onErrorResume` bên trong mapper của `flatMap` để mỗi phần tử có chính sách lỗi riêng:

```java
Flux<OrderResult> results = orderIds
    .flatMap(orderId ->
        orderService.process(orderId)
            .map(OrderResult::success)
            .onErrorResume(OrderNotFoundException.class, error ->
                Mono.just(OrderResult.rejected(orderId, "NOT_FOUND"))
            )
            .onErrorResume(InvalidOrderException.class, error ->
                Mono.just(OrderResult.rejected(orderId, "INVALID"))
            ),
        8
    );
```

Mỗi lần mapper chạy, nó tạo một publisher con gắn với một `orderId`. Nếu publisher con đó phát lỗi thuộc nhóm đã chọn, `onErrorResume` thay thế chính publisher con bằng một `Mono` kết quả từ chối. Publisher con hoàn tất bình thường sau fallback, vì vậy `flatMap` có thể tiếp tục tiêu thụ các phần tử khác.

Phạm vi được cô lập như sau:

```text
Flux<OrderId>
     |
     v
  flatMap(orderId ->
     process(orderId)
       .onErrorResume(error -> fallback(orderId, error))
  )
     |
     +-- order 101: success ------------> Success(101)
     +-- order 102: error -> fallback --> Rejected(102)
     +-- order 103: success ------------> Success(103)
     +-- order 104: success ------------> Success(104)
```

Lỗi của order 102 được chuyển thành kết quả bình thường trong publisher con của nó. Nó không phát `onError` ra khỏi `flatMap`, nên không kết thúc toàn bộ luồng kết quả.

### Chọn `flatMap` hay `concatMap`

Ví dụ dùng `flatMap` để xử lý đồng thời tối đa tám đơn hàng. Thứ tự kết quả không được bảo đảm giống thứ tự đầu vào vì publisher con hoàn tất độc lập. Nếu nghiệp vụ yêu cầu giữ thứ tự, dùng `concatMap` để xử lý tuần tự hoặc `flatMapSequential` để chạy đồng thời nhưng phát kết quả theo thứ tự nguồn.

```java
Flux<OrderResult> orderedResults = orderIds
    .concatMap(orderId -> orderService.process(orderId)
        .map(OrderResult::success)
        .onErrorResume(error ->
            Mono.just(OrderResult.rejected(orderId, classify(error)))
        )
    );
```

Điểm quyết định vị trí phục hồi không phụ thuộc vào operator merge được chọn: lỗi cần được xử lý bên trong publisher con trước khi nó thoát ra ranh giới kết hợp.

## 4. So sánh hai vị trí phục hồi

| Cấu trúc | Phạm vi `onErrorResume` | Hành vi khi một phần tử lỗi |
|---|---|---|
| `source.flatMap(this::process).onErrorResume(...)` | Toàn bộ luồng sau `flatMap`. | Publisher kết quả kết thúc lỗi; fallback thay thế phần còn lại của luồng. |
| `source.flatMap(item -> process(item).onErrorResume(...))` | Publisher con của từng phần tử. | Chỉ publisher con lỗi được thay thế; luồng ngoài có thể tiếp tục. |
| `source.concatMap(item -> process(item).onErrorResume(...))` | Publisher con của từng phần tử, xử lý tuần tự. | Phục hồi phần tử hiện tại rồi tiếp tục phần tử kế tiếp. |
| `source.onErrorResume(...)` | Nguồn `source` trước các bước sau. | Lỗi của chính nguồn được thay bằng publisher khác; không khôi phục subscription nguồn cũ. |

Đọc pipeline từ trong ra ngoài và xác định publisher nào sở hữu lỗi. Hỏi rõ: lỗi này có nghĩa toàn bộ use case thất bại, hay chỉ một phần tử không xử lý được? Chính sách phải được đặt tại ranh giới tương ứng.

## 5. Lỗi của nguồn và lỗi của từng phần tử là hai phạm vi khác nhau

Đặt phục hồi trong publisher con chỉ bắt được lỗi phát ra từ publisher con. Nó không tự bắt lỗi của nguồn ngoài trước khi mapper được gọi.

Ví dụ nguồn đọc từ broker có thể lỗi kết nối trước khi phát phần tử mới. Lỗi đó là lỗi của `source`, không gắn với một `orderId` cụ thể:

```java
Flux<OrderResult> results = orderIds
    .flatMap(orderId -> processOne(orderId)
        .onErrorResume(error -> recoverOne(orderId, error))
    )
    .onErrorResume(BrokerUnavailableException.class, error ->
        fallbackSourceUnavailable(error)
    );
```

Ở đây có hai chính sách riêng:

- `onErrorResume` bên trong `flatMap` xử lý lỗi của một lần `processOne`.
- `onErrorResume` bên ngoài xử lý lỗi của nguồn hoặc lỗi không được phục hồi thoát ra từ các nhánh con.

Việc có cả hai tầng không sai nếu chúng có ý nghĩa nghiệp vụ rõ ràng. Sai lầm nằm ở việc mong operator bên ngoài phục hồi một phần tử riêng lẻ trong khi nó chỉ nhìn thấy lỗi của toàn publisher.

Một nguồn có thể phát vài phần tử rồi mới lỗi. Fallback bên ngoài sẽ thay phần còn lại sau thời điểm lỗi; nó không tự tạo lại nguồn ban đầu hoặc tiếp tục từ offset vừa dừng. Nếu cần resume từ checkpoint, hãy lưu checkpoint và tạo publisher mới bắt đầu từ vị trí đó.

## 6. Lỗi đồng bộ khi tạo publisher con

Một mapper của `flatMap` có thể ném exception ngay trong lúc tạo publisher, trước khi trả về publisher con. Reactor bắt exception từ mapper và chuyển thành lỗi của operator `flatMap`. Một `onErrorResume` được gắn trên publisher con chỉ tồn tại nếu mapper đã trả publisher đó.

Ví dụ dễ bỏ sót:

```java
Flux<Result> results = inputs.flatMap(input -> {
    validateShape(input); // Có thể ném exception ngay tại đây.
    return remoteService.process(input)
        .onErrorResume(this::recoverRemoteFailure);
});
```

Nếu `validateShape` ném exception, biểu thức trả publisher con chưa được tạo; `onErrorResume` bên trong không thể bắt lỗi đó.

Nếu cần chuyển cả bước tạo publisher và lời gọi xử lý vào cùng phạm vi phục hồi, dùng `Mono.defer` hoặc `Flux.defer`:

```java
Flux<Result> results = inputs.flatMap(input ->
    Mono.defer(() -> {
        validateShape(input);
        return remoteService.process(input);
    })
    .onErrorResume(error -> recoverFor(input, error))
);
```

Supplier của `defer` chạy khi publisher con được subscribe. Exception đồng bộ từ `validateShape` được chuyển thành `onError` của publisher con và có thể được xử lý bởi `onErrorResume` cùng tầng.

Không bọc mọi mapper bằng `defer` một cách máy móc. Dùng nó khi có logic có thể ném lỗi trong lúc tạo publisher và bạn muốn lỗi đó thuộc về phạm vi từng phần tử.

## 7. `onErrorResume`, `onErrorReturn`, `onErrorComplete` và `onErrorMap`

Các operator xử lý lỗi có ngữ nghĩa khác nhau. Chọn theo kết quả mà downstream cần nhận.

| Operator | Tác dụng | Lỗi có còn đi xuống downstream không? |
|---|---|---|
| `onErrorResume` | Chuyển sang publisher thay thế. | Không nếu publisher thay thế hoàn tất bình thường; lỗi mới từ fallback vẫn có thể đi xuống. |
| `onErrorReturn` | Phát một giá trị fallback rồi hoàn tất. | Không nếu fallback được phát thành công. |
| `onErrorComplete` | Chuyển lỗi thành hoàn tất rỗng. | Không; downstream chỉ thấy complete. |
| `onErrorMap` | Chuyển loại exception. | Có; vẫn là terminal error. |
| `doOnError` | Quan sát lỗi để log/metric. | Có; lỗi tiếp tục đi xuống. |

Ví dụ fallback giá trị đơn giản:

```java
Mono<Profile> profile = profileClient.findById(id)
    .onErrorReturn(Profile.anonymous());
```

Ví dụ chuyển lỗi kỹ thuật thành lỗi ứng dụng:

```java
Mono<Profile> profile = profileClient.findById(id)
    .onErrorMap(TimeoutException.class,
        error -> new ProfileServiceUnavailableException(id, error));
```

`onErrorMap` không phục hồi publisher. Nó thay exception rồi vẫn phát `onError`. Nếu đặt `onErrorMap` trong publisher con mà không có operator phục hồi tiếp theo, lỗi vẫn thoát ra `flatMap` và có thể kết thúc luồng ngoài.

### `onErrorComplete` bên trong và bên ngoài cũng khác nhau

Nếu đặt `onErrorComplete` bên trong publisher con, lỗi của phần tử đó được chuyển thành complete cho publisher con. `flatMap` có thể tiếp tục với phần tử khác, nhưng downstream không nhận được kết quả cho phần tử lỗi.

Nếu đặt `onErrorComplete` sau `flatMap`, lỗi của toàn bộ luồng được chuyển thành complete; phần tử nguồn còn lại không được tự động xử lý tiếp.

Chỉ bỏ qua lỗi khi nghiệp vụ cho phép. Với batch cần báo cáo từng phần tử, một kết quả `Rejected` thường tốt hơn việc im lặng bỏ mất phần tử.

## 8. `doOnError` chỉ quan sát, không phục hồi

`doOnError` phù hợp để ghi log, tăng metric hoặc ghi nhận chẩn đoán. Nó không thay thế lỗi bằng kết quả khác:

```java
Flux<Result> results = source
    .flatMap(this::process)
    .doOnError(error -> log.error("Batch failed", error));
```

Nếu `process` phát lỗi, `doOnError` chạy callback rồi lỗi tiếp tục xuống subscriber. Luồng vẫn kết thúc lỗi.

Để log lỗi từng phần tử mà vẫn tiếp tục, đặt callback trong publisher con:

```java
Flux<Result> results = source.flatMap(item ->
    process(item)
        .doOnError(error -> log.warn(
            "Item {} failed: {}", item.id(), error.toString()
        ))
        .onErrorResume(error ->
            Mono.just(Result.failed(item.id(), classify(error)))
        )
);
```

Không ghi payload nhạy cảm hoặc dữ liệu cá nhân vào log. Dùng ID tương quan có kiểm soát và metric có cardinality phù hợp.

## 9. `onErrorContinue` không phải giải pháp mặc định

`onErrorContinue` có vẻ hấp dẫn vì tên gọi gợi ý bỏ qua phần tử lỗi và tiếp tục. Tuy nhiên, operator này có ngữ nghĩa phụ thuộc vào operator upstream hỗ trợ chế độ continue, và lỗi có thể được xử lý tại một điểm khác với nơi đặt nó. Nó không phải một cơ chế tổng quát để biến mọi lỗi trong pipeline thành lỗi từng phần tử.

Những rủi ro khi dùng `onErrorContinue` như chính sách mặc định:

- Không phải mọi publisher hoặc operator đều hỗ trợ hành vi continue giống nhau.
- Side effect có thể đã xảy ra một phần trước khi lỗi được phát.
- Việc bỏ qua phần tử có thể làm mất dấu vết nghiệp vụ nếu không ghi nhận rõ.
- Người đọc khó xác định chính xác phần tử nào bị bỏ và ở operator nào.
- Lỗi từ nguồn hoặc một số lỗi terminal không thể được hiểu đơn giản như lỗi mapping của một phần tử.

Với batch nghiệp vụ, cách rõ ràng hơn thường là đặt `onErrorResume` trong publisher con và trả về một kiểu kết quả biểu diễn thành công/thất bại:

```java
Flux<ItemOutcome> outcomes = items.flatMap(item ->
    process(item)
        .map(value -> ItemOutcome.success(item.id(), value))
        .onErrorResume(error ->
            Mono.just(ItemOutcome.failure(item.id(), classify(error)))
        ),
    10
);
```

Kết quả thất bại trở thành dữ liệu có cấu trúc. Caller có thể đếm, lưu báo cáo, gửi lại các item được phép retry hoặc đưa lỗi vĩnh viễn vào DLQ.

## 10. Khi nào dùng `flatMapDelayError`?

Reactor có các operator trì hoãn phát lỗi như `flatMapDelayError`. Chúng cho phép các publisher con còn lại tiếp tục một phần công việc trước khi lỗi được truyền xuống downstream.

```java
Flux<Result> results = source.flatMapDelayError(
    this::process,
    8,
    16
);
```

Đây là chính sách khác với phục hồi lỗi từng phần tử:

- `flatMapDelayError` trì hoãn việc phát terminal error trong khi các publisher con còn lại được phép hoàn tất theo semantics của operator.
- Cuối cùng downstream vẫn nhận lỗi nếu có lỗi được giữ lại.
- Nó không tự chuyển từng lỗi thành `Result.failure`.
- Nó không bảo đảm nguồn vô hạn sẽ kết thúc để lỗi được phát.

Dùng delay-error khi batch cần cho các công việc đang hoạt động có cơ hội hoàn tất trước khi báo lỗi tổng hợp. Dùng `onErrorResume` bên trong publisher con khi nghiệp vụ cần một kết quả riêng cho từng phần tử và muốn luồng ngoài hoàn tất bình thường.

## 11. Đặt retry đúng phạm vi

Retry cũng chịu ảnh hưởng của vị trí operator. Nếu đặt retry sau `flatMap`, lỗi của một publisher con có thể khiến toàn bộ nguồn được đăng ký lại. Với nguồn cold, các phần tử đã xử lý trước đó có thể được phát lại và tạo side effect trùng.

Không nên:

```java
Flux<Receipt> receipts = orderIds
    .flatMap(orderService::createReceipt)
    .retryWhen(Retry.max(2));
```

Khi một publisher con lỗi, retry ở ngoài có thể đăng ký lại toàn bộ chuỗi nguồn. Nếu `createReceipt` đã ghi dữ liệu cho một số đơn hàng trước đó, những đơn hàng đó có thể được xử lý lại.

Nếu chỉ muốn retry thao tác của một phần tử, đặt retry bên trong publisher con:

```java
Flux<Receipt> receipts = orderIds.flatMap(orderId ->
    Mono.defer(() -> orderService.createReceipt(orderId))
        .retryWhen(Retry.backoff(2, Duration.ofMillis(100))
            .maxBackoff(Duration.ofSeconds(1))
            .filter(this::isTransient))
        .onErrorResume(PermanentOrderException.class, error ->
            auditService.recordRejected(orderId, error)
                .then(Mono.empty())
        ),
    8
);
```

Retry trong inner publisher chỉ đăng ký lại thao tác cho `orderId` đó. Tuy nhiên, nếu thao tác ghi đã thành công ở server nhưng response bị mất, retry vẫn có thể lặp side effect. Hãy dùng idempotency key hoặc thao tác vốn lũy đẳng.

## 12. Không để fallback che giấu lỗi của chính fallback

`onErrorResume` thay publisher lỗi bằng publisher mới. Nếu publisher fallback cũng lỗi, lỗi mới sẽ đi xuống downstream:

```java
Mono<Report> report = reportService.load(id)
    .onErrorResume(ReportUnavailableException.class, error ->
        cache.load(id)
    );
```

Nếu `cache.load` phát lỗi, toàn bộ publisher `report` vẫn kết thúc lỗi. Không nên giả định có fallback đồng nghĩa mọi lỗi đã được phục hồi.

Nếu cần phân biệt lỗi chính và lỗi fallback, có thể ánh xạ lỗi fallback thành một exception mang cả hai nguyên nhân hoặc ghi nhận lỗi gốc trước khi chuyển nhánh. Tránh lồng nhiều `onErrorResume` không có phân loại rõ ràng, vì điều đó làm mất khả năng hiểu nguồn lỗi.

Với publisher con, nếu fallback cho một item lỗi thì vẫn cần quyết định trường hợp audit hoặc ghi DLQ cũng lỗi. Có thể để lỗi audit thoát ra để dừng batch vì không thể bảo đảm ghi nhận thất bại; hoặc có một kênh vận hành khác để ghi nhận. Quyết định này phải phản ánh yêu cầu dữ liệu, không chỉ nhằm làm pipeline luôn xanh.

## 13. Kiểu kết quả cho batch xử lý một phần

Một batch thường có ba loại kết quả:

1. Thành công: phần tử được xử lý và có giá trị đầu ra.
2. Thất bại nghiệp vụ: phần tử không hợp lệ hoặc không được phép xử lý; cần ghi nhận nhưng không nhất thiết dừng batch.
3. Thất bại hạ tầng: database/broker/service không khả dụng; có thể cần dừng batch, retry hoặc để hệ thống chạy lại từ checkpoint.

Không nên gom tất cả vào một fallback rỗng. Hãy dùng kiểu kết quả rõ ràng:

```java
sealed interface ItemOutcome {
    record Success(String itemId, ProcessedValue value)
        implements ItemOutcome {}

    record Rejected(String itemId, String reason)
        implements ItemOutcome {}

    record Deferred(String itemId, String cause)
        implements ItemOutcome {}
}
```

Pipeline có thể xử lý lỗi nghiệp vụ thành `Rejected`, lỗi tạm thời đã retry hết thành `Deferred`, còn lỗi nghiêm trọng như nguồn bị mất kết nối có thể để phát ra ngoài để batch coordinator quyết định dừng:

```java
Flux<ItemOutcome> outcomes = items.flatMap(item ->
    Mono.defer(() -> processor.process(item))
        .map(value -> (ItemOutcome) new ItemOutcome.Success(item.id(), value))
        .onErrorResume(ValidationException.class, error ->
            Mono.just(new ItemOutcome.Rejected(item.id(), error.getMessage()))
        )
        .onErrorResume(TemporaryDependencyException.class, error ->
            Mono.just(new ItemOutcome.Deferred(item.id(), "DEPENDENCY_UNAVAILABLE"))
        ),
    12
);
```

Ví dụ chỉ chuyển hai loại lỗi đã xác định thành dữ liệu. Những lỗi khác tiếp tục là terminal error và có thể kết thúc batch. Không nên bắt `Throwable` hoặc `Exception` chung rồi chuyển thành `Rejected`, vì lỗi lập trình và lỗi hệ thống nghiêm trọng có thể bị che giấu.

## 14. Kiểm thử sự khác biệt bằng `StepVerifier`

Kiểm thử là cách tốt để chứng minh phạm vi phục hồi đúng như mong muốn. Dùng `concatMap` trong ví dụ để thứ tự phát kết quả xác định, giúp test không phụ thuộc tốc độ hoàn tất publisher con.

### Test phục hồi sai ở ngoài `flatMap`

```java
Flux<Integer> process(int value) {
    if (value == 2) {
        return Flux.error(new IllegalStateException("bad item"));
    }
    return Flux.just(value);
}

Flux<Integer> batch = Flux.just(1, 2, 3)
    .concatMap(this::process)
    .onErrorResume(error -> Flux.just(-1));

StepVerifier.create(batch)
    .expectNext(1, -1)
    .verifyComplete();
```

Publisher nguồn đã phát phần tử 1. Khi phần tử 2 lỗi, `concatMap` phát lỗi ra ngoài và không xử lý phần tử 3. `onErrorResume` ngoài thay phần còn lại bằng `-1`. Test thể hiện rõ rằng phần tử 3 không được tự động tiếp tục.

### Test phục hồi đúng bên trong publisher con

```java
Flux<Integer> batch = Flux.just(1, 2, 3)
    .concatMap(value -> process(value)
        .onErrorResume(error -> Flux.just(-value))
    );

StepVerifier.create(batch)
    .expectNext(1, -2, 3)
    .verifyComplete();
```

Publisher con của phần tử 2 chuyển lỗi thành `-2` và hoàn tất. `concatMap` tiếp tục subscribe publisher con của phần tử 3. Test chứng minh chính sách phục hồi được áp dụng cho từng item.

### Test lỗi nguồn vẫn có thể kết thúc luồng ngoài

```java
Flux<Integer> source = Flux.concat(
    Flux.just(1, 2),
    Flux.error(new SourceUnavailableException())
);

Flux<Integer> batch = source.concatMap(value -> process(value)
    .onErrorResume(error -> Flux.just(-value))
);

StepVerifier.create(batch)
    .expectNext(1, 2)
    .expectError(SourceUnavailableException.class)
    .verify();
```

Phục hồi bên trong mapper không bắt được lỗi của nguồn xảy ra sau các phần tử đã phát. Nếu muốn xử lý lỗi nguồn, cần một chính sách riêng ở tầng nguồn hoặc tầng coordinator.

## 15. Kiểm thử publisher con chạy đồng thời

Với `flatMap`, thứ tự kết quả không xác định. Không nên viết test giả định phần tử nào hoàn tất trước nếu thời gian inner publisher khác nhau. Hãy kiểm tra tập kết quả hoặc dùng `collectList()` rồi sắp xếp trong test khi thứ tự không thuộc hợp đồng.

```java
Flux<ItemOutcome> outcomes = items.flatMap(item ->
    processor.process(item)
        .map(value -> ItemOutcome.success(item.id(), value))
        .onErrorResume(ValidationException.class, error ->
            Mono.just(ItemOutcome.rejected(item.id(), "INVALID"))
        ),
    8
);

StepVerifier.create(outcomes.collectList())
    .assertNext(values -> {
        assertEquals(3, values.size());
        assertTrue(values.stream().anyMatch(
            value -> value.itemId().equals("item-2")
                && value.isRejected()
        ));
    })
    .verifyComplete();
```

Đoạn mã dùng các factory/accessor minh họa của `ItemOutcome`; điều chỉnh theo kiểu kết quả thực tế. Test nên xác minh mọi item có một outcome tương ứng và không có item bị mất âm thầm.

Các trường hợp nên có trong suite:

- Một publisher con lỗi nghiệp vụ và được thay bằng outcome thất bại.
- Một publisher con lỗi hạ tầng không được phục hồi và làm batch kết thúc theo chính sách.
- Publisher fallback cũng lỗi; lỗi fallback phải được quan sát.
- Lỗi đồng bộ trong mapper được bọc bằng `defer` và phục hồi đúng phạm vi.
- Lỗi nguồn ngoài không bị nhầm thành lỗi của item.
- Retry chỉ lặp publisher con tương ứng, không phát lại side effect của các item trước.
- Cancellation từ downstream được truyền đến các publisher con đang chạy.
- Số publisher con đồng thời không vượt giới hạn đã cấu hình.

## 16. Những lỗi thiết kế thường gặp

### Dùng một fallback chung cho toàn batch

Một `onErrorResume` cuối pipeline biến lỗi của một item thành fallback cấp batch. Caller mất thông tin item nào lỗi và các item còn lại có thể chưa được xử lý. Hãy dùng outcome theo item khi batch cần tiếp tục.

### Bắt mọi exception rồi trả `Mono.empty()`

Điều này biến lỗi lập trình, lỗi hạ tầng và lỗi nghiệp vụ thành trường hợp không có dữ liệu. Hãy bắt các loại lỗi có ý nghĩa cụ thể và ghi nhận đầy đủ.

### Nghĩ `doOnError` sẽ làm luồng tiếp tục

`doOnError` chỉ quan sát. Nếu cần phục hồi, dùng `onErrorResume`, `onErrorReturn` hoặc một operator có ngữ nghĩa tương ứng.

### Dùng `onErrorContinue` để bỏ qua mọi lỗi

Hành vi phụ thuộc operator và có thể che giấu lỗi. Với xử lý theo item, biểu diễn lỗi thành outcome trong publisher con sẽ rõ ràng hơn.

### Đặt retry ngoài toàn bộ batch

Nguồn có thể bị đăng ký lại và các item đã xử lý có thể được phát lại. Đặt retry trong publisher con nếu chỉ thao tác item đó cần được thử lại, đồng thời bảo vệ side effect bằng idempotency.

### Quên lỗi từ fallback hoặc audit

Một nhánh phục hồi cũng có thể thất bại. Quyết định rõ lỗi audit/DLQ có được phép làm dừng batch hay cần một kênh ghi nhận riêng.

### Không phân biệt lỗi nguồn với lỗi item

Lỗi broker, lỗi đọc file hoặc lỗi truy vấn nguồn có thể xảy ra ngoài mapper. Cần một chính sách riêng cho lifecycle của nguồn và checkpoint.

## 17. Quy trình xác định vị trí phục hồi

Khi một luồng dừng sớm, hãy lần theo publisher sở hữu lỗi:

1. Xác định operator đầu tiên phát `onError`.
2. Xác định lỗi phát ra từ nguồn ngoài, mapper, publisher con hay operator downstream.
3. Xác định phạm vi nghiệp vụ cần phục hồi: một giá trị, một item, một partition hay toàn batch.
4. Đặt operator phục hồi bên trong publisher tương ứng với phạm vi đó.
5. Chỉ chuyển lỗi đã phân loại thành fallback; để lỗi không thể phục hồi đi xuống tầng coordinator.
6. Nếu retry, đặt nó quanh thao tác cần thử lại và bảo vệ side effect lặp.
7. Kiểm thử bằng `StepVerifier` cả trường hợp item lỗi, lỗi nguồn và lỗi fallback.
8. Kiểm tra cancellation, concurrency và việc ghi nhận item thất bại.

Một câu hỏi hữu ích khi đọc pipeline là: “Nếu publisher này phát `onError`, phần nào của luồng đã kết thúc?” Trả lời được câu hỏi đó sẽ giúp đặt `onErrorResume` và `retryWhen` đúng phạm vi, tránh biến một lỗi cục bộ thành lỗi của toàn batch.

## 18. Checklist phục hồi lỗi theo đúng phạm vi

- Hiểu `onError` là terminal signal của publisher hiện tại.
- Không kỳ vọng `onErrorResume` bên ngoài `flatMap` tiếp tục nguồn đã kết thúc.
- Đặt `onErrorResume` trong publisher con khi muốn cô lập lỗi từng phần tử.
- Dùng `Mono.defer`/`Flux.defer` nếu logic tạo publisher có thể ném lỗi đồng bộ và cần được phục hồi theo item.
- Xử lý lỗi của nguồn ngoài ở một tầng riêng.
- Chọn `concatMap`, `flatMap` hoặc `flatMapSequential` theo yêu cầu thứ tự và concurrency.
- Phân biệt phục hồi bằng fallback với chuyển đổi exception bằng `onErrorMap`.
- Dùng `doOnError` để quan sát, không coi nó là cơ chế phục hồi.
- Tránh dùng `onErrorContinue` như chính sách chung cho batch.
- Dùng `flatMapDelayError` khi muốn trì hoãn lỗi tổng hợp, không nhầm nó với fallback từng item.
- Đặt retry trong publisher con khi chỉ thao tác của item đó cần được thử lại.
- Dùng idempotency cho thao tác có side effect có thể bị thực hiện lặp.
- Giữ outcome thất bại có cấu trúc để có thể audit, retry hoặc đưa vào DLQ.
- Kiểm thử item failure, source failure, fallback failure, retry và cancellation bằng `StepVerifier`.

Phục hồi lỗi đúng vị trí giúp một phần tử không hợp lệ không làm dừng những phần tử độc lập còn lại. Hãy xác định publisher nào sở hữu lỗi rồi đặt fallback hoặc retry bên trong đúng phạm vi đó. Lỗi nguồn và lỗi toàn batch vẫn cần được xử lý ở tầng điều phối tương ứng; việc phân biệt rõ các phạm vi này giúp pipeline reactive dễ dự đoán, dễ kiểm thử và không che giấu những sự cố cần được xử lý ở cấp hệ thống.
