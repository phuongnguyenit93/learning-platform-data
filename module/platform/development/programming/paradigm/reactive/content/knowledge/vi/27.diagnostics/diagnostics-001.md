# Phân biệt nơi lắp ráp chuỗi và nơi lỗi được phát

Khi một pipeline Reactor thất bại, stack trace thường dẫn người đọc đến nơi exception được tạo hoặc ném ra. Nhưng vị trí đó có thể khác với nơi Publisher được lắp ráp, nơi subscription bắt đầu và nơi tín hiệu lỗi đi qua các operator. Nếu nhầm các thời điểm này, ta dễ đặt `try/catch`, `doOnError` hoặc `onErrorResume` sai chỗ, khiến lỗi không được quan sát hoặc phục hồi như mong đợi.

Bài học thuộc chương **Chẩn đoán** của module `REACTIVE_PROGRAMMING`. Module hướng dẫn tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams; người học thực hành `Mono`, `Flux`, kết hợp toán tử, điều khiển scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Trọng tâm ở đây là phân biệt assembly time, subscription time và signal time, xác định operator nào tạo hoặc quan sát lỗi, và dùng công cụ chẩn đoán của Reactor để truy ngược về đúng vị trí trong code.

Sau bài học, bạn có thể:

- Phân biệt thời điểm lắp ráp Publisher, subscribe và phát tín hiệu.
- Nhận diện exception xảy ra ngay khi tạo pipeline với exception được chuyển thành `onError`.
- Giải thích vì sao `try/catch` bên ngoài không bắt được lỗi phát bất đồng bộ sau khi phương thức đã trả về.
- Đặt `doOnError`, `onErrorMap` và `onErrorResume` ở đúng vị trí trong chuỗi.
- Dùng `defer`, `fromCallable`, `checkpoint` và `Hooks.onOperatorDebug()` để chẩn đoán.
- Hiểu stack trace runtime và assembly traceback cung cấp hai loại thông tin khác nhau.
- Kiểm thử nguồn phát lỗi, operator gây lỗi và đường phục hồi bằng `StepVerifier`.

## 1. Ba thời điểm cần tách biệt

Một pipeline Reactor có ít nhất ba mốc quan trọng:

1. **Assembly time — thời điểm lắp ráp:** code gọi các factory và operator để tạo Publisher. Ví dụ `Flux.range(...)`, `.map(...)`, `.filter(...)`, `.timeout(...)`.
2. **Subscription time — thời điểm đăng ký:** Subscriber subscribe vào Publisher; quá trình subscription đi ngược từ downstream về upstream, thiết lập subscription và demand.
3. **Signal time — thời điểm phát tín hiệu:** nguồn phát `onNext`, `onComplete` hoặc `onError`; các operator xử lý tín hiệu rồi truyền xuống downstream.

```text
Assembly time
  Flux.range(...)
      .map(...)
      .filter(...)
      .onErrorResume(...)
          |
          v
  Publisher được tạo

Subscription time
  subscriber.subscribe()
          |
          v
  subscribe đi ngược về nguồn
  và thiết lập demand

Signal time
  source --onNext/onError/onComplete--> operators --> subscriber
```

Ba mốc này có thể diễn ra cách nhau đáng kể. Một phương thức service có thể lắp ráp Publisher và trả về ngay; việc truy vấn database chỉ bắt đầu khi WebFlux subscribe vào Publisher đó. Vì vậy, nhìn thấy một dòng code tạo pipeline không có nghĩa mọi lambda trong pipeline đã chạy.

### Assembly không đồng nghĩa với thực thi

Ví dụ:

```java
Mono<Integer> result = Mono.just(10)
    .map(value -> {
        log.info("map đang chạy");
        return value * 2;
    });

log.info("Publisher đã được lắp ráp");
```

Khi đoạn code trên chạy, Publisher được tạo nhưng lambda trong `map` chưa được gọi. Dòng log bên trong `map` chỉ xuất hiện khi có subscription và tín hiệu `onNext` đi qua operator.

Ngược lại, biểu thức đối số của `Mono.just` được Java đánh giá trước khi gọi `just`:

```java
Mono<User> user = Mono.just(repository.findNow(userId));
```

`repository.findNow(userId)` chạy ngay trong lúc lắp ráp. Nếu phương thức này ném exception, exception xảy ra trước khi `Mono` được tạo. Một toán tử `onErrorResume` nối phía sau không thể bắt được exception đó vì chưa có Publisher để phát `onError`.

## 2. Exception lúc lắp ráp và lỗi trong reactive signal

Hãy phân biệt hai đoạn code sau:

```java
// Lời gọi đồng bộ được thực hiện ngay khi lắp ráp.
Mono<User> eager = Mono.just(repository.findNow(userId));

// Lời gọi được trì hoãn đến subscription; exception trở thành onError.
Mono<User> deferred = Mono.fromCallable(
    () -> repository.findNow(userId)
);
```

Với `eager`, nếu `findNow` ném exception, dòng khởi tạo `eager` ném exception trực tiếp. Với `deferred`, callable chạy khi có subscription; nếu callable ném exception, Reactor chuyển exception đó thành tín hiệu `onError` của `Mono`.

Đây là khác biệt quan trọng khi muốn áp dụng xử lý lỗi:

```java
Mono<User> user = Mono.fromCallable(
        () -> repository.findNow(userId)
    )
    .onErrorResume(DatabaseException.class,
        error -> cache.findUser(userId));
```

Lỗi từ `findNow` giờ nằm trong reactive flow nên `onErrorResume` có thể quan sát và thay thế nhánh lỗi.

### `defer` trì hoãn cả việc tạo Publisher

`fromCallable` phù hợp khi công việc đồng bộ trả về một giá trị. `defer` phù hợp khi cần tạo một Publisher mới cho từng subscription:

```java
Mono<User> user = Mono.defer(() -> {
    validateUserId(userId);
    return userRepository.findById(userId);
});
```

Supplier của `defer` được gọi khi subscribe. Nếu `validateUserId` ném exception trong supplier, Reactor chuyển lỗi đó thành `onError`. Publisher do `findById` trả về cũng được subscribe trong cùng chuỗi.

So sánh nhanh:

| Cách tạo | Thời điểm gọi logic | Khi logic ném exception |
|---|---|---|
| `Mono.just(method())` | Ngay khi Java đánh giá đối số lúc assembly | Ném đồng bộ; chưa có Mono để phát lỗi. |
| `Mono.fromCallable(method)` | Khi subscribe | Chuyển exception thành `onError`. |
| `Mono.defer(() -> publisher)` | Khi subscribe, lúc supplier tạo Publisher | Chuyển exception từ supplier thành `onError`. |
| `Mono.error(error)` | Publisher phát lỗi khi được subscribe | Phát `onError` theo reactive protocol. |

`Mono.just` không nhận `null`. Nếu phương thức đồng bộ có thể trả `null`, `Mono.fromCallable` chuyển kết quả `null` thành empty completion; hãy xác định xem empty có đúng semantics nghiệp vụ không. Đừng dùng `null` như một giá trị `onNext`.

## 3. Lambda của operator chạy ở đâu và khi nào?

Các operator như `map`, `filter` và `flatMap` được lắp ráp trước, nhưng function truyền vào chúng chỉ được gọi khi tín hiệu đi tới operator tương ứng.

```java
Mono<Invoice> invoice = orderRepository.findById(orderId)
    .map(this::toInvoice)
    .filter(Invoice::isValid)
    .flatMap(invoiceService::enrich);
```

- `toInvoice` chạy khi nguồn phát một order.
- `isValid` chạy sau khi `map` phát invoice.
- `enrich` chạy khi invoice vượt qua `filter`.
- Nếu nguồn empty, các lambda xử lý phần tử này không chạy.
- Nếu nguồn lỗi trước khi phát phần tử, các lambda xử lý `onNext` phía sau không chạy; lỗi đi theo đường terminal signal.

Nếu một lambda trong `map` hoặc `filter` ném exception, Reactor chuyển exception đó thành `onError`. Lỗi được tạo trong quá trình xử lý tín hiệu, không phải khi lắp ráp lambda.

```java
Mono<Integer> result = Mono.just("not-a-number")
    .map(Integer::parseInt);
```

`Integer.parseInt` chạy khi `onNext("not-a-number")` đi qua `map`. `NumberFormatException` trở thành `onError` và đi xuống downstream.

### Lỗi trong Publisher con của `flatMap`

`flatMap` có thể tạo một Publisher con. Lỗi của Publisher con cũng được nhập vào luồng kết quả:

```java
Mono<Profile> profile = userRepository.findById(userId)
    .flatMap(user -> profileClient.fetch(user.id()));
```

Nếu `profileClient.fetch` trả về Publisher phát lỗi, lỗi đó đi xuống `profile`. Nếu chính hàm mapper ném exception trước khi trả Publisher, Reactor cũng chuyển exception đó thành `onError` của chuỗi `flatMap`.

Khi chẩn đoán, hãy tìm cả hai khả năng: lỗi được phát bởi Publisher con và exception đồng bộ từ function tạo Publisher con.

## 4. `try/catch` chỉ bắt lỗi trong phạm vi lời gọi đồng bộ

Một lỗi thường gặp là đặt `try/catch` quanh việc tạo Publisher và mong nó bắt lỗi phát sau đó:

```java
Mono<User> loadUser(String id) {
    try {
        return remoteClient.findUser(id)
            .map(this::enrich);
    } catch (Exception error) {
        return Mono.just(User.guest());
    }
}
```

Khối `catch` chỉ bắt exception ném đồng bộ trong lúc gọi `findUser` hoặc lắp ráp chuỗi. Nếu `findUser` trả về `Mono` rồi Publisher đó phát `onError` sau khi subscribe, khối `catch` đã kết thúc và không bắt được lỗi.

Hãy biểu diễn phục hồi bằng operator:

```java
Mono<User> loadUser(String id) {
    return remoteClient.findUser(id)
        .map(this::enrich)
        .onErrorResume(RemoteUnavailableException.class,
            error -> cache.findUser(id));
}
```

`onErrorResume` nằm trong chuỗi nên nhận lỗi được phát từ nguồn hoặc lỗi do `map` tạo ra ở phía trước nó.

`try/catch` vẫn hữu ích khi xử lý một API imperative cần gọi đồng bộ, nhưng hãy đặt nó bên trong một factory trì hoãn nếu muốn chuyển exception thành reactive error:

```java
Mono<User> loadUser(String id) {
    return Mono.fromCallable(() -> legacyClient.loadUser(id))
        .subscribeOn(Schedulers.boundedElastic());
}
```

Ở đây, exception của `legacyClient` được `fromCallable` chuyển thành `onError`; `subscribeOn` đưa công việc blocking sang scheduler phù hợp. Không cần bọc thêm `try/catch` chỉ để chuyển exception thành `Mono.error`.

## 5. Xác định operator nào nhìn thấy lỗi

Lỗi đi từ vị trí phát về phía downstream. Một operator chỉ quan sát được lỗi nếu tín hiệu lỗi đi qua vị trí của nó.

```java
Mono<Result> result = source
    .doOnError(error -> log.warn("Nguồn upstream thất bại", error))
    .map(this::transform)
    .doOnError(error -> log.error("Pipeline sau transform thất bại", error));
```

Nếu `source` lỗi, cả hai `doOnError` đều có thể quan sát lỗi khi tín hiệu đi qua. Nếu `transform` ném exception, `doOnError` đầu tiên nằm trước `map` nên không nhìn thấy lỗi do `map` tạo ra; `doOnError` thứ hai nhìn thấy lỗi đó.

Điều này cũng áp dụng cho phục hồi:

```java
// Không bắt được lỗi do transform tạo ra ở phía sau.
Mono<Result> first = source
    .onErrorResume(this::fallback)
    .map(this::transform);

// Bắt được lỗi từ source và lỗi do transform tạo ra.
Mono<Result> second = source
    .map(this::transform)
    .onErrorResume(this::fallback);
```

Trong `first`, `onErrorResume` chỉ xử lý lỗi upstream của chính nó. Nếu `transform` lỗi, operator phục hồi đã nằm phía trước nên không nhận được tín hiệu đó. Trong `second`, `onErrorResume` nằm sau `map` nên nhận cả hai loại lỗi.

### `doOnError` quan sát, không phục hồi

`doOnError` phù hợp để log hoặc tăng metric. Nó không thay đổi tín hiệu lỗi:

```java
Mono<Order> order = orderClient.fetch(orderId)
    .doOnError(error -> metrics.increment("order.fetch.failed"));
```

Downstream vẫn nhận `onError`. Nếu muốn đổi loại lỗi, dùng `onErrorMap`; nếu muốn chuyển sang nguồn khác, dùng `onErrorResume`; nếu muốn thay bằng một giá trị, dùng `onErrorReturn`.

Không đặt log cùng một lỗi ở quá nhiều tầng nếu sẽ tạo log trùng. Chọn ranh giới có trách nhiệm ghi nhận lỗi, và phân biệt lỗi nguồn với lỗi do bước biến đổi downstream tạo ra.

## 6. Assembly traceback và runtime stack trace

Khi một operator phát hiện exception trong lúc xử lý tín hiệu, runtime stack trace thường cho biết nơi exception được ném ra và các lời gọi đang hoạt động tại thời điểm đó. Tuy nhiên, do pipeline có thể được lắp ráp ở một phương thức rồi subscribe ở một phương thức khác, stack trace runtime không phải lúc nào cũng chỉ rõ dòng code đã tạo nên chuỗi operator.

Reactor có thể bổ sung assembly traceback để cho biết operator nào được lắp ráp tại vị trí nào. Một thông báo lỗi có thể chứa phần `Suppressed: The stacktrace has been enhanced by Reactor`, kèm các checkpoint hoặc assembly site.

Hai thông tin có ý nghĩa khác nhau:

| Thông tin | Trả lời câu hỏi |
|---|---|
| Runtime stack trace | Exception thực sự được ném ở đâu khi pipeline chạy? |
| Assembly traceback | Publisher/operator liên quan được tạo ở đâu trong code? |
| Checkpoint description | Ranh giới nghiệp vụ hoặc giai đoạn nào đã được đánh dấu? |

Assembly traceback không thay thế việc đọc exception gốc. Nó giúp nối vị trí lắp ráp với lỗi xảy ra sau đó. Nếu một Publisher được tạo trong helper dùng chung, assembly site có thể trỏ đến helper đó; hãy kết hợp checkpoint mô tả nghiệp vụ để biết request hoặc giai đoạn nào đang gặp sự cố.

## 7. Dùng `checkpoint` để đánh dấu vị trí lắp ráp

`checkpoint` thêm thông tin chẩn đoán vào pipeline. Có thể đặt checkpoint ở các ranh giới quan trọng:

```java
Mono<Order> order = orderRepository.findById(orderId)
    .checkpoint("order-repository")
    .flatMap(paymentService::loadPayment)
    .checkpoint("payment-enrichment")
    .map(this::toOrderView)
    .checkpoint("order-response-mapping");
```

Khi lỗi đi qua pipeline, checkpoint description giúp xác định giai đoạn liên quan. Overload `checkpoint(String)` thêm mô tả nhẹ mà không thu thập đầy đủ stack trace tại assembly. Nếu cần stack trace assembly cho checkpoint cụ thể, dùng overload có `forceStackTrace=true`:

```java
Mono<Order> order = orderRepository.findById(orderId)
    .checkpoint("order-repository", true);
```

`checkpoint()` không tham số thu thập assembly traceback cho vị trí đó. Việc thu thập stack trace có chi phí, vì vậy nên đặt checkpoint có chọn lọc ở ranh giới quan trọng hoặc bật chế độ debug đầy đủ trong môi trường phù hợp.

### Checkpoint không phải nơi xử lý lỗi

Checkpoint chỉ bổ sung thông tin chẩn đoán. Nó không thay đổi exception, không phục hồi nguồn và không biến lỗi thành completion. Vẫn cần dùng `onErrorMap`, `onErrorResume` hoặc error handler ở đúng vị trí nếu muốn thay đổi hành vi pipeline.

## 8. Bật `Hooks.onOperatorDebug()` khi cần assembly tracing rộng

Để thu thập thông tin lắp ráp trên các operator Reactor, có thể bật hook toàn cục:

```java
Hooks.onOperatorDebug();
```

Hook nên được bật sớm khi khởi động ứng dụng, trước khi tạo các pipeline cần chẩn đoán. Khi bật, Reactor ghi nhận thông tin assembly để bổ sung traceback khi lỗi đi qua các operator được hỗ trợ.

Đổi lại, việc chụp stack trace lúc lắp ráp có thể làm tăng chi phí CPU và bộ nhớ. Không nên mặc định bật chế độ này cho mọi production workload có yêu cầu latency cao nếu chưa đo tác động. Có thể ưu tiên checkpoint có chọn lọc để giảm overhead.

Nếu bật hook trong kiểm thử hoặc môi trường dùng chung, cần quản lý trạng thái global hook cẩn thận. Không bật/tắt tùy tiện giữa các test chạy song song vì hook ảnh hưởng đến các pipeline được lắp ráp trong cùng JVM.

### Chẩn đoán bằng `log()`

`log()` ghi nhận các tín hiệu đi qua một vị trí của pipeline:

```java
Flux<Integer> values = Flux.range(1, 3)
    .log("source")
    .map(value -> value * 2)
    .log("after-map");
```

Log giúp quan sát `onSubscribe`, request, `onNext`, `onComplete` và `onError` tại ranh giới operator. Đặt log ở hai phía của một bước nghi ngờ có thể cho biết tín hiệu dừng ở đâu. Tuy nhiên, không nên log payload nhạy cảm hoặc bật log tín hiệu chi tiết vô hạn trong production mà không giới hạn mức độ và khối lượng.

## 9. Retry làm thay đổi số lần subscription

Assembly và subscription cũng cần được phân biệt khi dùng `retry` hoặc `retryWhen`. Retry thường subscribe lại Publisher upstream theo chính sách. Nó không có nghĩa toàn bộ biểu thức Java tạo pipeline được thực thi lại.

```java
AtomicInteger calls = new AtomicInteger();

Mono<String> source = Mono.fromCallable(() -> {
        int attempt = calls.incrementAndGet();
        if (attempt < 3) {
            throw new IOException("temporary failure");
        }
        return "ok";
    })
    .retry(2);
```

Mỗi lần subscribe vào nguồn `fromCallable`, callable chạy lại. Với `retry(2)`, Reactor cho phép tối đa hai lần retry sau lần subscribe ban đầu. Nếu lần thứ ba thành công, downstream nhận `ok`.

Ngược lại:

```java
String value = loadValueSynchronously();
Mono<String> source = Mono.just(value).retry(2);
```

`loadValueSynchronously()` đã chạy trong lúc lắp ráp. Nếu nó ném exception, `source` chưa được tạo và `retry` không thể chạy. Nếu nó trả về giá trị, retry subscribe lại cùng Publisher `just(value)`; biểu thức đồng bộ ban đầu không được gọi lại.

Nếu cần tạo Publisher hoặc tài nguyên mới cho mỗi lần retry, đặt thao tác trong `defer` hoặc `fromCallable` tại ranh giới được retry subscribe lại. Đồng thời, chỉ retry thao tác có thể lặp an toàn; retry một lệnh ghi không idempotent có thể tạo tác dụng phụ trùng.

## 10. Lỗi phát sau cancellation và lỗi bị bỏ

Khi downstream đã cancel, nó không còn nhận tín hiệu mới. Nếu một nguồn bất đồng bộ vẫn phát lỗi muộn sau khi cancellation đã xảy ra, Reactor không thể chuyển lỗi đó cho subscriber đã hủy; lỗi có thể được chuyển đến cơ chế xử lý dropped error như `Hooks.onErrorDropped`.

Điều này thường cho thấy một trong các vấn đề:

- Nguồn không dừng công việc sau khi nhận cancellation.
- Callback bất đồng bộ vẫn có thể hoàn tất lỗi sau khi request đã bị hủy.
- Một Publisher hoặc adapter không quản lý đúng vòng đời callback.

Không dùng `onErrorResume` như cách xử lý lỗi sau cancellation; subscriber đã hủy thì nhánh phục hồi không còn người nhận. Hãy sửa vòng đời nguồn, đảm bảo cancellation được truyền đúng và chỉ cài hook xử lý dropped error cho mục đích quan sát có chủ đích. Không nên nuốt mọi dropped error vì có thể che giấu lỗi lập trình hoặc lỗi tài nguyên.

## 11. Quy trình truy tìm lỗi trong một pipeline

Khi một request báo lỗi nhưng stack trace khó đọc, có thể lần lượt thực hiện:

1. Xác định phương thức nào chỉ lắp ráp Publisher và phương thức nào thực sự subscribe.
2. Tìm các biểu thức được đánh giá eager như `Mono.just(method())`, constructor hoặc lời gọi đồng bộ bên ngoài supplier.
3. Tìm operator tạo lỗi trong signal path: `map`, `filter`, `flatMap`, timeout, nguồn remote hoặc Publisher con.
4. Đặt `doOnError` ở các ranh giới để biết lỗi đã đi qua đến đâu; nhớ rằng hook chỉ thấy lỗi upstream của nó.
5. Thêm `checkpoint("stage-name")` ở các ranh giới nghiệp vụ quan trọng.
6. Trong môi trường debug, cân nhắc `Hooks.onOperatorDebug()` để lấy assembly traceback rộng hơn.
7. Kiểm tra thứ tự `onErrorMap`, `onErrorResume` và `retryWhen`; operator phục hồi chỉ xử lý lỗi đi qua vị trí của nó.
8. Kiểm tra cancellation và dropped error nếu lỗi xuất hiện sau khi request đã kết thúc.
9. Tạo kiểm thử nhỏ tái hiện đúng nguồn, operator và loại terminal signal.

Ví dụ pipeline có ranh giới rõ:

```java
Mono<OrderView> loadOrder(String orderId) {
    return Mono.defer(() -> orderRepository.findById(orderId))
        .checkpoint("load-order")
        .switchIfEmpty(Mono.error(new OrderNotFoundException(orderId)))
        .flatMap(order -> paymentClient.findByOrder(order.id())
            .checkpoint("load-payment")
            .map(payment -> new OrderView(order, payment)))
        .checkpoint("build-order-view")
        .doOnError(error -> log.error(
            "Không thể tạo order view cho orderId={}", orderId, error
        ));
}
```

`defer` trì hoãn lời gọi tạo Publisher của repository đến subscription. Checkpoint giúp nhận diện các giai đoạn. `doOnError` ở cuối quan sát lỗi từ các bước trước trong pipeline. Lỗi `OrderNotFoundException` được tạo bởi `switchIfEmpty` cũng đi qua các operator phía sau và được hook cuối quan sát.

## 12. Kiểm thử assembly và signal bằng StepVerifier

`StepVerifier` xác nhận tín hiệu reactive. Để kiểm tra thời điểm thực thi, có thể kết hợp bộ đếm hoặc cờ trạng thái.

### Xác nhận `map` chỉ chạy khi subscribe

```java
AtomicInteger mapped = new AtomicInteger();

Mono<Integer> source = Mono.just(10)
    .map(value -> {
        mapped.incrementAndGet();
        return value * 2;
    });

assertThat(mapped.get()).isZero();

StepVerifier.create(source)
    .expectNext(20)
    .verifyComplete();

assertThat(mapped.get()).isEqualTo(1);
```

Trước subscribe, lambda `map` chưa chạy. Sau khi verifier subscribe và nhận phần tử, bộ đếm tăng lên một.

### Xác nhận exception từ `fromCallable` thành `onError`

```java
Mono<String> source = Mono.fromCallable(() -> {
    throw new IOException("read failed");
});

StepVerifier.create(source)
    .expectError(IOException.class)
    .verify();
```

Exception được tạo khi callable chạy trong subscription và được chuyển thành tín hiệu lỗi.

### Xác nhận lỗi do `map` được phục hồi ở phía sau

```java
StepVerifier.create(
        Mono.just("invalid")
            .map(Integer::parseInt)
            .onErrorResume(NumberFormatException.class,
                error -> Mono.just(-1))
    )
    .expectNext(-1)
    .verifyComplete();
```

`map` tạo lỗi trong lúc xử lý `onNext`; `onErrorResume` đặt sau nó nhận lỗi và phát giá trị thay thế.

### Xác nhận operator phục hồi đặt quá sớm không bắt lỗi downstream

```java
StepVerifier.create(
        Mono.just("invalid")
            .onErrorResume(error -> Mono.just("fallback"))
            .map(Integer::parseInt)
    )
    .expectError(NumberFormatException.class)
    .verify();
```

`onErrorResume` không nhìn thấy lỗi do `map` phía sau tạo ra. Kiểm thử này giúp bảo vệ thứ tự operator khi refactor pipeline.

### Kiểm thử retry và số lần subscribe

```java
AtomicInteger attempts = new AtomicInteger();

Mono<String> source = Mono.fromCallable(() -> {
        if (attempts.incrementAndGet() < 3) {
            throw new IOException("temporary");
        }
        return "ready";
    })
    .retry(2);

StepVerifier.create(source)
    .expectNext("ready")
    .verifyComplete();

assertThat(attempts.get()).isEqualTo(3);
```

Kiểm thử xác nhận retry tạo subscription mới đến callable và callable được thực thi lại. Với pipeline có side effect, hãy kiểm tra thêm idempotency và số lần gọi nguồn ngoài.

## 13. Những lỗi thường gặp

| Cách làm sai | Hậu quả | Cách xử lý |
|---|---|---|
| Gọi `Mono.just(service.call())` với phương thức có thể ném lỗi | Exception xảy ra lúc assembly, ngoài reactive flow. | Dùng `fromCallable` hoặc `defer`. |
| Đặt `try/catch` quanh việc trả Publisher và mong bắt lỗi bất đồng bộ | `onError` đến sau khi khối `try` đã kết thúc. | Dùng operator xử lý lỗi trong pipeline. |
| Nghĩ lambda `map` chạy khi gọi `.map(...)` | Chẩn đoán sai thời điểm và side effect. | Lambda chạy khi có phần tử đi qua operator. |
| Đặt `onErrorResume` trước operator có thể tạo lỗi | Lỗi downstream không đi ngược lại operator phục hồi. | Đặt phục hồi sau vùng cần bảo vệ. |
| Nghĩ `doOnError` đã xử lý lỗi | Downstream vẫn nhận `onError`. | Dùng `onErrorMap` hoặc `onErrorResume` khi cần đổi hành vi. |
| Nhầm runtime stack trace với assembly traceback | Không tìm được nơi tạo chuỗi operator. | Dùng checkpoint hoặc assembly debug để bổ sung vị trí lắp ráp. |
| Bật `Hooks.onOperatorDebug()` mà không xét chi phí | Tăng overhead khi lắp ráp Publisher. | Dùng checkpoint có chọn lọc hoặc bật debug trong môi trường phù hợp. |
| Nghĩ retry chạy lại biểu thức Java đã tạo Publisher | Giá trị eager không được tính lại khi resubscribe. | Đặt công việc cần chạy lại trong `defer` hoặc `fromCallable`. |
| Cố phục hồi lỗi sau cancellation | Không còn subscriber nhận kết quả fallback. | Sửa nguồn và quản lý cancellation/dropped error. |

## 14. Checklist chẩn đoán

Khi một pipeline phát lỗi, hãy kiểm tra:

- Exception xảy ra ngay lúc tạo Publisher hay sau khi subscribe?
- Có lời gọi eager nằm trong đối số của `Mono.just` hoặc trước một factory trì hoãn không?
- Lambda nào thực sự được gọi khi `onNext` đi qua?
- Lỗi phát từ nguồn, operator đồng bộ, Publisher con hay timeout?
- `doOnError` và `onErrorResume` có nằm sau vị trí tạo lỗi không?
- Runtime stack trace đã cho biết dòng ném exception chưa; có cần assembly traceback không?
- Checkpoint có đánh dấu các ranh giới nghiệp vụ quan trọng không?
- Retry có thực sự tạo subscription mới đến công việc cần chạy lại không?
- Cancellation có xảy ra trước khi lỗi được phát, khiến lỗi bị dropped không?
- Kiểm thử đã xác nhận cả thời điểm thực thi, terminal signal và thứ tự operator chưa?

Khi tách assembly time, subscription time và signal time, bạn sẽ biết một exception xuất hiện trước khi Publisher được tạo hay đã trở thành `onError` trong pipeline. Đặt operator quan sát và phục hồi sau đúng vị trí phát lỗi, kết hợp `checkpoint` hoặc assembly debug khi cần, giúp truy ngược lỗi về cả nơi thực thi lẫn nơi lắp ráp chuỗi trong ứng dụng Reactor.
