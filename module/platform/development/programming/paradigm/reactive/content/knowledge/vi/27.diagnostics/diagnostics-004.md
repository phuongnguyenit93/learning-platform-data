# Theo dõi chuỗi không chạy, không kết thúc hoặc bị hủy sớm

Khi một pipeline reactive không cho kết quả như mong đợi, triệu chứng thường rơi vào một trong ba nhóm: công việc chưa bắt đầu, subscription đã chạy nhưng không kết thúc, hoặc subscription bị hủy trước khi hoàn thành. Ba tình huống này có nguyên nhân khác nhau. Một publisher cold chưa được subscribe sẽ không thực thi; một nguồn không phát terminal signal có thể giữ downstream chờ vô hạn; còn một toán tử như `take`, `timeout` hoặc `switchMap` có thể chủ động hủy upstream theo đúng hợp đồng của nó.

Muốn chẩn đoán chính xác, cần theo dõi vòng đời subscription và các tín hiệu tại nhiều vị trí trong pipeline. Reactor cung cấp các hook như `doOnSubscribe`, `doOnRequest`, `doOnNext`, `doOnComplete`, `doOnError`, `doOnCancel`, `doFinally`, cùng `log()` và `checkpoint()`. Kết hợp chúng với `StepVerifier`, `TestPublisher` và `PublisherProbe` giúp xác định công việc dừng ở đâu, vì sao nó dừng và thành phần nào đã yêu cầu cancellation.

## 1. Phân biệt subscribe, demand, terminal signal và cancel

Một publisher không bắt đầu phát dữ liệu chỉ vì pipeline đã được lắp ráp. Subscriber phải đăng ký trước; sau đó demand (`request(n)`) cho biết downstream muốn nhận bao nhiêu phần tử. Publisher có thể phát `onNext` theo demand rồi kết thúc bằng `onComplete` hoặc `onError`. Subscriber cũng có thể gọi `cancel()` để yêu cầu dừng nhận dữ liệu.

```text
Assembly
   |
   v
subscribe() ----> onSubscribe
                      |
                      v
                  request(n)
                      |
                      v
                  onNext(...)  zero or more times
                      |
              +-------+-------+
              |               |
          onComplete        onError

Subscriber có thể gọi cancel() trước terminal signal.
```

Các khái niệm cần tách biệt:

| Quan sát | Ý nghĩa | Hướng kiểm tra đầu tiên |
| --- | --- | --- |
| Không có `onSubscribe` | Chưa có subscription tới vị trí đang quan sát | Caller có subscribe hoặc framework có nhận publisher không? |
| Có `onSubscribe`, không có `request` | Subscriber chưa yêu cầu dữ liệu | Có phải subscriber đang giữ demand ở mức 0? |
| Có request nhưng không có `onNext` | Nguồn chưa phát, đang chờ I/O, đang chờ sự kiện hoặc bị chặn | Nguồn có dữ liệu và có khả năng phát không? |
| Có `onNext`, không có terminal signal | Luồng vẫn mở hoặc một bước đang chờ hoàn tất | Nguồn có complete/error không; inner nào chưa kết thúc? |
| Có `cancel` | Subscriber hoặc toán tử downstream yêu cầu dừng upstream | Thành phần nào tạo cancellation? |

Cancellation không phải `onComplete` hay `onError`. Nó là một hành động từ subscriber lên subscription. Vì vậy, một nguồn bị cancel không nhất thiết phát terminal signal tới subscriber đã hủy.

## 2. Quan sát vòng đời bằng các hook Reactor

Đặt hook ở trước và sau đoạn pipeline nghi ngờ để biết tín hiệu đã đi tới đâu:

```java
Mono<Order> traced = orderRepository.findById(orderId)
    .doOnSubscribe(subscription -> log.debug("order: subscribed"))
    .doOnRequest(n -> log.debug("order: requested {}", n))
    .doOnNext(order -> log.debug("order: value received, id={}", order.id()))
    .doOnSuccess(order -> log.debug("order: completed successfully"))
    .doOnError(error -> log.warn("order: failed", error))
    .doOnCancel(() -> log.debug("order: cancelled"))
    .doFinally(signal -> log.debug("order: finally {}", signal));
```

Các hook có ý nghĩa khác nhau:

- `doOnSubscribe` chạy khi subscriber đăng ký vào vị trí đặt hook.
- `doOnRequest` quan sát lượng demand được yêu cầu qua subscription tại vị trí đó.
- `doOnNext` quan sát từng phần tử đi qua.
- `doOnComplete` quan sát complete bình thường.
- `doOnError` quan sát lỗi được truyền qua.
- `doOnCancel` quan sát cancellation đi qua vị trí đó.
- `doFinally` chạy khi luồng kết thúc bằng complete, error hoặc cancel và cung cấp `SignalType` tương ứng.

Với `Mono`, `doOnSuccess` được gọi khi hoàn tất thành công; đối số có thể là `null` nếu `Mono` hoàn tất rỗng. Không nhầm `doOnSuccess` với `doOnNext`: nguồn rỗng không có `onNext` nhưng vẫn có thể gọi `doOnSuccess(null)`.

Đặt hook ở hai phía của một operator có thể khoanh vùng nơi tín hiệu dừng:

```java
Flux<Result> result = source
    .doOnNext(value -> log.debug("before filter: {}", value.id()))
    .filter(this::isEligible)
    .doOnNext(value -> log.debug("after filter: {}", value.id()))
    .map(this::toResult);
```

Nếu log trước `filter` xuất hiện nhưng log sau không có, hãy kiểm tra predicate và dữ liệu đầu vào. Nếu không có log ở cả hai vị trí, vấn đề có thể nằm ở subscription, demand hoặc nguồn upstream.

Không ghi payload nhạy cảm, token, dữ liệu cá nhân hoặc toàn bộ body request vào log chẩn đoán. Ưu tiên correlation ID, mã định danh đã được phép ghi và tên bước pipeline. Gỡ hook hoặc giảm mức log sau khi điều tra xong nếu chúng không cần thiết trong vận hành.

## 3. Dùng log() và checkpoint() để tìm vị trí lỗi

`log()` ghi lại các sự kiện Reactive Streams như subscribe, request, next, complete, error và cancel:

```java
Flux<OrderView> views = orderRepository.findRecent()
    .log("orders.repository")
    .filter(Order::isVisible)
    .log("orders.visible")
    .map(orderMapper::toView)
    .log("orders.view");
```

So sánh log giữa các điểm để xác định subscription đã tới đâu, demand có được gửi không và terminal signal xuất hiện ở đoạn nào. Có thể chỉ định logger name và `Level` để điều chỉnh lượng log. `log()` hữu ích trong môi trường phát triển và khi điều tra có kiểm soát; tránh bật log payload rộng trên luồng có lưu lượng cao hoặc dữ liệu nhạy cảm.

`checkpoint()` gắn một mốc mô tả vào assembly trace để lỗi có thêm ngữ cảnh về vị trí pipeline:

```java
Mono<OrderView> view = orderRepository.findById(orderId)
    .flatMap(this::loadDetails)
    .map(orderMapper::toView)
    .checkpoint("OrderService.loadOrderView");
```

Checkpoint có mô tả giúp nhận diện đoạn pipeline trong stack trace khi có lỗi. Có thể dùng overload buộc tạo stack trace đầy đủ khi cần điều tra sâu, nhưng việc đó có thêm chi phí. Đặt checkpoint tại ranh giới service hoặc đoạn phối hợp phức tạp thường hữu ích hơn việc gắn tràn lan vào mọi operator.

`Hooks.onOperatorDebug()` có thể bật assembly tracing rộng hơn trong môi trường phát triển, nhưng có chi phí đáng kể và là hook toàn cục. Nếu chỉ cần đánh dấu một vài pipeline, ưu tiên `checkpoint()` có mô tả. Không bật hook debug toàn cục tùy tiện trên production có tải lớn.

## 4. Khi chuỗi không chạy: kiểm tra subscription trước

Các publisher cold phổ biến trong Reactor chỉ thực hiện công việc khi có subscription. Tạo publisher và trả nó từ một phương thức chưa có nghĩa là công việc đã chạy:

```java
Mono<Customer> load(String id) {
    return Mono.fromCallable(() -> legacyDao.find(id));
}

void refresh(String id) {
    load(id); // Publisher bị bỏ đi, không có subscription.
}
```

Trong trường hợp này, `legacyDao.find` không được gọi. Phương thức `refresh` tạo publisher nhưng không trả nó cho caller, không compose nó vào pipeline và cũng không subscribe tại một ranh giới sở hữu phù hợp.

Trong controller WebFlux, hãy trả publisher cho framework:

```java
@GetMapping("/{id}")
Mono<CustomerView> find(@PathVariable String id) {
    return customerService.load(id).map(CustomerView::from);
}
```

Trong một tác vụ nền có chủ đích, subscription có thể được tạo ở ranh giới điều phối của ứng dụng, nơi có trách nhiệm quản lý lỗi, cancellation và lifecycle. Không gọi `subscribe()` tùy tiện bên trong mapper hoặc service chỉ để “cho nó chạy”, vì subscription tách rời sẽ khó được caller điều khiển.

Kiểm tra theo thứ tự:

1. Phương thức có thực sự trả publisher cho caller không?
2. Caller có subscribe, hoặc framework có nhận publisher làm kết quả không?
3. Publisher có bị tạo rồi bỏ đi trong một nhánh điều kiện không?
4. Có subscription nào bị cancel ngay sau khi bắt đầu không?
5. Subscriber có phát demand hay đang giữ request ở mức 0?

## 5. Phân biệt lắp ráp publisher với thời điểm thực thi

Một số lời gọi được thực thi ngay khi lắp ráp pipeline nếu kết quả được tính trước khi truyền vào factory:

```java
// Lời gọi legacyDao.find chạy ngay tại assembly.
Mono<Customer> eager = Mono.just(legacyDao.find(customerId));
```

`Mono.just` giữ giá trị đã được tính. Nếu cần trì hoãn một lời gọi đồng bộ tới lúc subscribe, dùng `fromCallable` hoặc `defer`:

```java
Mono<Customer> lazy = Mono.fromCallable(() -> legacyDao.find(customerId));

Mono<Customer> lazyWithDefer = Mono.defer(() ->
    Mono.just(legacyDao.find(customerId))
);
```

`fromCallable` phù hợp để chuyển một lời gọi đồng bộ thành publisher. `defer` gọi supplier để tạo publisher mới cho mỗi subscription. Nếu lời gọi bên trong blocking, cần cô lập nó bằng scheduler phù hợp, chẳng hạn `subscribeOn(Schedulers.boundedElastic())`; laziness tự nó không biến blocking thành non-blocking.

Khi debug, ghi nhận riêng thời điểm phương thức tạo publisher và thời điểm callable được thực thi. Điều này giúp phân biệt “publisher chưa được subscribe” với “side effect đã xảy ra quá sớm trong assembly”.

## 6. Kiểm tra demand khi subscription đã tồn tại nhưng không có dữ liệu

Một subscriber có thể subscribe nhưng chưa yêu cầu phần tử. Với Reactive Streams, publisher không được phát `onNext` vượt quá demand đã nhận. Dùng `doOnRequest` hoặc một test với initial request bằng 0 để quan sát:

```java
Flux<Integer> source = Flux.range(1, 3)
    .doOnRequest(n -> log.debug("source demand={}", n));

StepVerifier.create(source, 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNext(1)
    .thenRequest(2)
    .expectNext(2, 3)
    .verifyComplete();
```

Ở đây subscription tồn tại ngay từ đầu nhưng demand ban đầu bằng 0. Sau `thenRequest(1)`, phần tử đầu tiên được yêu cầu; sau đó test yêu cầu thêm hai phần tử. Nếu một subscriber thật không request, pipeline có thể không phát `onNext` dù nguồn đã subscribe và sẵn sàng.

Không phải mọi publisher đều phát dữ liệu ngay khi subscribe. Một số nguồn chờ I/O, callback, timer hoặc sự kiện từ hệ thống khác. Demand là điều kiện cho phép phát phần tử, nhưng không thể tự tạo dữ liệu nếu nguồn chưa có dữ liệu.

## 7. Khi chuỗi không kết thúc: tìm nguồn không phát terminal signal

Một pipeline có thể phát một số phần tử rồi chờ mãi vì nguồn không gửi `onComplete` hoặc `onError`. Ví dụ:

```java
Flux<Event> events = eventSource.listen();

Mono<List<Event>> allEvents = events.collectList();
```

`collectList()` chỉ phát danh sách sau khi nguồn hoàn tất. Nếu `listen()` là stream dài hạn và không bao giờ complete, `allEvents` sẽ tiếp tục chờ dù đã nhận nhiều event. Đây có thể là hành vi đúng nếu nguồn là feed vô hạn; khi đó không nên đợi một danh sách cuối cùng. Nếu nghiệp vụ cần batch hữu hạn, phải xác định ranh giới bằng thời gian, số lượng, predicate hoặc cancellation.

Các nguyên nhân thường gặp khiến nguồn không kết thúc:

- API callback không gọi `sink.complete()` hoặc `sink.error()` khi kết thúc.
- Một inner publisher trong `flatMap`/`concatMap` không bao giờ complete.
- `Mono.never()` hoặc một publisher chờ tín hiệu bên ngoài không có timeout.
- Lời gọi blocking chưa trả về, giữ worker thread.
- Một operator như `collectList`, `reduce` hoặc `then` đang chờ nguồn trước hoàn tất.
- Nguồn là stream dài hạn theo thiết kế, nhưng code phía sau lại giả định nó hữu hạn.

Đặt hook trước và sau operator chờ hoàn tất. Nếu nguồn đã phát `onNext` nhưng không có terminal signal, kiểm tra hợp đồng của nguồn và điều kiện đóng nó. Nếu nguồn đã complete nhưng publisher kết quả chưa phát, kiểm tra operator kế tiếp và nhánh điều kiện.

## 8. Kiểm tra inner publisher bị treo

Với `flatMap`, một inner publisher có thể không hoàn tất. Pipeline ngoài có thể tiếp tục phát kết quả từ các inner khác, nhưng việc hoàn tất toàn bộ `Flux` vẫn cần các inner đang hoạt động kết thúc:

```java
Flux<Result> results = ids.flatMap(id ->
    id.equals("slow")
        ? Mono.<Result>never()
        : service.load(id)
);
```

Nếu một inner không bao giờ kết thúc, publisher ngoài có thể không hoàn tất dù những inner khác đã hoàn tất. Giới hạn concurrency cũng có thể khiến các phần tử tiếp theo phải chờ slot trống.

Đặt timeout tại ranh giới của từng inner nếu mỗi lời gọi có deadline riêng:

```java
Flux<Result> results = ids.flatMap(id ->
    service.load(id)
        .timeout(Duration.ofSeconds(2))
        .onErrorResume(TimeoutException.class, error -> Mono.empty()),
    8
);
```

Đoạn mã minh họa một chính sách bỏ qua inner timeout; chỉ dùng nếu nghiệp vụ cho phép thiếu kết quả. Nếu timeout của một inner phải làm thất bại toàn pipeline, bỏ `onErrorResume` để lỗi đi xuống. Timeout giải phóng slot sau khi publisher timeout xử lý cancellation, nhưng không bảo đảm một API blocking không hỗ trợ hủy sẽ dừng tức thời.

Với `concatMap`, một inner không hoàn tất sẽ ngăn inner tiếp theo được subscribe. Đây là hành vi tuần tự đúng theo hợp đồng toán tử; hãy kiểm tra publisher đang được xử lý hiện tại trước khi nghi ngờ các phần tử phía sau bị mất.

## 9. Khi chuỗi bị hủy sớm: tìm toán tử tạo cancellation

Cancellation có thể đến từ caller hoặc do operator downstream không còn cần upstream:

| Nguồn cancellation | Hành vi quan sát được | Cách xác minh |
| --- | --- | --- |
| Caller gọi `Subscription.cancel()` | Subscription upstream nhận cancel | `doOnCancel`, `doFinally(CANCEL)` |
| `take(n)` | Downstream complete sau n phần tử và hủy upstream | Kiểm tra số phần tử và hook upstream |
| `next()` | Lấy phần tử đầu tiên rồi hủy nguồn Flux | Kiểm tra upstream cancel sau `onNext` đầu |
| `timeout` | Hủy nguồn upstream và phát timeout error xuống downstream | Hook upstream thấy CANCEL; downstream thấy `TimeoutException` |
| `switchMap` | Hủy inner cũ khi outer phát giá trị mới | Gắn hook vào từng inner và ghi ID tương ứng |
| Client HTTP disconnect | Framework hủy publisher response | Theo dõi `doFinally(CANCEL)` và cleanup nguồn |

Ví dụ `take(2)`:

```java
Flux<Integer> limited = Flux.range(1, 100)
    .doOnCancel(() -> log.debug("upstream cancelled"))
    .take(2);

StepVerifier.create(limited)
    .expectNext(1, 2)
    .verifyComplete();
```

Downstream quan sát complete bình thường sau hai phần tử, trong khi upstream nhận cancellation vì `take` không cần phần tử còn lại. Vì vậy, log upstream cancellation không nhất thiết có nghĩa request thất bại.

Với `timeout`, hai phía có thể quan sát hai tín hiệu khác nhau:

```java
Mono<String> guarded = Mono.<String>never()
    .doFinally(signal -> log.debug("source ended: {}", signal))
    .timeout(Duration.ofSeconds(1))
    .doOnError(TimeoutException.class,
        error -> log.warn("downstream timed out"));
```

Nguồn `never()` thấy cancellation khi timeout hủy upstream. Downstream thấy `onError(TimeoutException)`. Đọc log ở cả hai phía sẽ tránh nhầm cancellation upstream với lỗi terminal downstream.

## 10. switchMap có thể hủy công việc trước đó

`switchMap` chỉ giữ inner publisher mới nhất. Khi outer phát giá trị mới, inner cũ bị cancel để nhường chỗ cho inner mới:

```java
Flux<SearchResult> results = searchTerms.switchMap(term ->
    searchService.search(term)
        .doFinally(signal -> log.debug(
            "search '{}' ended: {}", term, signal))
);
```

Đây là hành vi mong muốn cho tìm kiếm theo nội dung đang gõ: kết quả của query cũ không còn cần thiết khi query mới xuất hiện. Nếu người dùng nghĩ mọi query đều phải được xử lý, `switchMap` không phù hợp; cân nhắc `flatMap` hoặc `concatMap` theo yêu cầu thứ tự và concurrency.

Khi debug, log khóa định danh của từng inner cùng `SignalType`. Nếu thấy inner cũ kết thúc bằng `CANCEL` ngay sau khi inner mới được tạo, đó thường là hành vi chuẩn của `switchMap`, không phải publisher tự biến mất.

## 11. Phân biệt lỗi, complete và cancellation trong doFinally

`doFinally` nhận một `SignalType` để phân biệt ba đường kết thúc:

```java
Flux<Data> traced = source.doFinally(signal -> {
    switch (signal) {
        case ON_COMPLETE -> metrics.completed();
        case ON_ERROR -> metrics.failed();
        case CANCEL -> metrics.cancelled();
        default -> metrics.otherTermination(signal);
    }
});
```

Không dùng một metric “failed” cho mọi lần `doFinally` chạy. Một pipeline có thể bị cancel vì `take`, `switchMap` hoặc client disconnect trong khi nghiệp vụ không thất bại. Ngược lại, timeout có thể làm upstream bị cancel nhưng downstream kết thúc bằng error. Hãy đặt hook ở vị trí phù hợp với góc nhìn cần đo và phân loại tín hiệu riêng.

`doOnTerminate` quan sát complete/error nhưng không quan sát cancel. Nếu cần đo đầy đủ vòng đời subscription, `doFinally` phù hợp hơn. Nếu cần thực hiện cleanup bất đồng bộ, dùng cơ chế quản lý tài nguyên như `usingWhen`; `doFinally` chỉ nhận callback đồng bộ và không chờ publisher cleanup.

## 12. Dùng StepVerifier để tái hiện ba triệu chứng

`StepVerifier` giúp kiểm tra subscription, demand, dữ liệu và terminal signal mà không cần tự viết subscriber:

```java
// Nguồn rỗng: complete mà không có onNext.
StepVerifier.create(Mono.<String>empty())
    .verifyComplete();

// Nguồn lỗi: phát onError.
StepVerifier.create(Mono.<String>error(new IllegalStateException("failed")))
    .expectError(IllegalStateException.class)
    .verify();

// Nguồn không kết thúc: quan sát rồi chủ động cancel.
StepVerifier.create(Mono.<String>never())
    .expectSubscription()
    .expectNoEvent(Duration.ofMillis(50))
    .thenCancel()
    .verify(Duration.ofSeconds(1));
```

Với nguồn không kết thúc, không gọi `verifyComplete()` vì test sẽ chờ vô hạn. Dùng `thenCancel()` hoặc một timeout xác minh hữu hạn. Với timeout dựa trên scheduler mặc định, dùng virtual time:

```java
StepVerifier.withVirtualTime(() ->
        Mono.<String>never().timeout(Duration.ofSeconds(10))
    )
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(10))
    .expectError(TimeoutException.class)
    .verify(Duration.ofSeconds(1));
```

Tạo publisher bên trong supplier của `withVirtualTime` để operator thời gian được lắp ráp sau khi virtual scheduler đã được cài đặt. Nếu dùng scheduler tùy chỉnh truyền tường minh, test cần điều khiển scheduler đó riêng.

## 13. Dùng TestPublisher và PublisherProbe để kiểm tra nguồn/nhánh

`TestPublisher` cho phép chủ động phát tín hiệu sau khi subscriber đã đăng ký:

```java
TestPublisher<String> source = TestPublisher.create();

StepVerifier.create(source.flux())
    .then(() -> source.next("one", "two"))
    .expectNext("one", "two")
    .then(source::complete)
    .verifyComplete();
```

Test có thể phát error hoặc complete tại thời điểm cụ thể để tái hiện lỗi race, nguồn rỗng hoặc nguồn không gửi terminal signal. Với nguồn không kết thúc, chỉ phát các phần tử cần thiết rồi để nguồn mở; test downstream cancellation và xác minh nguồn nhận cancel.

`PublisherProbe` kiểm tra một publisher thay thế có được subscribe hay không:

```java
PublisherProbe<String> fallback = PublisherProbe.of(Mono.just("cached"));

Mono<String> result = primary
    .switchIfEmpty(fallback.mono());

StepVerifier.create(result)
    .expectNext("cached")
    .verifyComplete();

fallback.assertWasSubscribed();
```

Nếu triệu chứng “không chạy” xuất phát từ một nhánh điều kiện không được chọn, probe giúp xác minh nhánh dự phòng có thực sự được đăng ký. Nếu nhánh không được subscribe như dự kiến, kiểm tra điều kiện empty/error và vị trí đặt `switchIfEmpty` hoặc `onErrorResume`.

## 14. Kiểm tra custom publisher và callback API

Khi tích hợp API callback bằng `Flux.create` hoặc `Mono.create`, cần kiểm tra mọi đường kết thúc và cleanup:

```java
Flux<Event> events = Flux.create(sink -> {
    Listener listener = eventBus.register(sink::next);

    sink.onDispose(() -> eventBus.unregister(listener));
});
```

Ví dụ này tạo một luồng có thể tồn tại lâu dài cho tới khi subscription bị dispose/cancel hoặc nguồn bên ngoài kết thúc. Nếu API callback có sự kiện “closed”, cần nối nó với `sink.complete()`; nếu có lỗi, gọi `sink.error(error)`. Nếu không có đường nào phát terminal signal, downstream dùng `collectList()` hoặc chờ complete sẽ không kết thúc.

`sink.onDispose` giúp dọn listener khi subscription bị dispose, bao gồm cancellation và terminal completion/error. Không đăng ký listener ở assembly bên ngoài `Flux.create`, vì khi đó listener có thể được tạo dù publisher không bao giờ subscribe. Cũng không gọi `sink.complete()` từ nhiều thread mà không tuân thủ API và concurrency mode của sink.

Khi debug custom source, ghi nhận thời điểm đăng ký listener, nhận callback, gọi complete/error và dispose listener. Test đủ các trường hợp nguồn kết thúc tự nhiên, lỗi, subscriber cancel và nhiều subscriber nếu publisher được thiết kế để hỗ trợ nhiều subscription.

## 15. Quy trình khoanh vùng khi pipeline có triệu chứng bất thường

Thực hiện theo thứ tự để tìm vị trí đầu tiên mà tín hiệu mong đợi không còn xuất hiện:

1. **Xác nhận subscription:** đặt `doOnSubscribe` ở đầu pipeline và kiểm tra caller có trả/subscribe publisher hay không.
2. **Xác nhận demand:** đặt `doOnRequest`; nếu demand bằng 0, kiểm tra subscriber và cách yêu cầu phần tử.
3. **Theo dõi phần tử:** đặt `doOnNext` hoặc `log()` trước/sau các filter, map và inner publisher.
4. **Theo dõi terminal signal:** đặt `doOnComplete`, `doOnError` và `doFinally` ở ranh giới nguồn, service và response.
5. **Tìm điểm chờ:** kiểm tra `never`, callback không complete, blocking call, inner publisher và operator chờ nguồn hoàn tất.
6. **Tìm điểm cancel:** gắn `doOnCancel`/`doFinally` vào upstream và từng inner; xem có `take`, `next`, `timeout`, `switchMap` hoặc client disconnect.
7. **Tái hiện bằng test:** dùng `StepVerifier`, `TestPublisher`, `PublisherProbe` và virtual time để tạo lại đúng chuỗi tín hiệu.

Đừng kết luận pipeline “không chạy” chỉ vì không có `onNext`: nguồn có thể empty, demand có thể bằng 0, filter có thể loại mọi phần tử hoặc publisher có thể đang chờ. Đừng kết luận request thất bại chỉ vì upstream thấy cancel: cancellation có thể là kết quả bình thường của `take` hoặc `switchMap`. Hãy đối chiếu các hook ở nhiều ranh giới trước khi thay đổi code.

## 16. Bảng triệu chứng và hướng điều tra

| Triệu chứng | Nguyên nhân thường gặp | Công cụ/hành động |
| --- | --- | --- |
| Không thấy `onSubscribe` | Publisher không được subscribe hoặc nhánh chưa được chọn | `doOnSubscribe`, `PublisherProbe`, kiểm tra caller |
| Subscribe nhưng không thấy request | Subscriber chưa tạo demand | `doOnRequest`, test initial request bằng 0 |
| Có request nhưng không có dữ liệu | Nguồn chờ I/O/event, filter loại hết hoặc nguồn không có dữ liệu | `log`, `doOnNext` ở hai phía operator |
| Có dữ liệu nhưng không complete | Nguồn dài hạn, custom source thiếu complete, inner không kết thúc | Hook terminal signal, kiểm tra source/inner, timeout |
| Upstream thấy cancel nhưng downstream complete | `take`, `next` hoặc operator đã đủ dữ liệu | `doFinally` ở cả hai phía |
| Upstream thấy cancel và downstream error timeout | `timeout` hủy nguồn rồi phát lỗi xuống | Kiểm tra timeout, client deadline và cleanup |
| Inner cũ cancel khi có giá trị mới | `switchMap` thay inner trước | Log khóa của từng inner, xác nhận semantics mong muốn |
| Request HTTP stream dừng khi client rời đi | Framework truyền cancellation từ response | `doFinally(CANCEL)`, kiểm tra resource cleanup |

## 17. Thiết kế pipeline để dễ chẩn đoán

Đặt ranh giới service và adapter rõ ràng, đặt tên checkpoint có ý nghĩa, ghi correlation ID thay vì payload nhạy cảm và đảm bảo custom publisher có đường complete/error/cancel rõ. Với stream dài hạn, không dùng operator yêu cầu nguồn hoàn tất nếu nghiệp vụ không có ranh giới đóng. Với lời gọi blocking, cấu hình timeout ở client và cô lập scheduler; timeout reactive không bảo đảm ngắt một API không hỗ trợ cancellation.

Khi một pipeline bị hủy, luôn phân biệt ai yêu cầu cancel và downstream quan sát terminal signal nào. Khi một pipeline không kết thúc, xác định nguồn hoặc inner nào chưa phát terminal signal. Khi pipeline không chạy, xác nhận subscription và demand trước khi xem xét logic nghiệp vụ. Những phân biệt này giúp chẩn đoán theo bằng chứng, tránh thêm `subscribe()`, retry hoặc timeout một cách tùy tiện và giữ được vòng đời tài nguyên đúng trong ứng dụng Project Reactor.
