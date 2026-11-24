# Chuyển Callable, Supplier, Future và CompletionStage thành nguồn

Trong module `REACTIVE_PROGRAMMING`, ta học cách tạo và kết hợp các luồng sự kiện bất đồng bộ theo hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams. Với Reactor, `Mono` và `Flux` là những kiểu Publisher thường dùng để biểu diễn kết quả và chuỗi dữ liệu. Trong ứng dụng Java, dữ liệu hoặc tác vụ ban đầu có thể đang được cung cấp dưới dạng `Callable`, `Supplier`, `Future` hay `CompletionStage`. Chuyển đổi đúng kiểu giúp đưa chúng vào pipeline reactive, xác định rõ thời điểm thực thi, cách truyền lỗi và cách hủy công việc.

Các kiểu này không có cùng ngữ nghĩa. `Callable` và `Supplier` mô tả một tác vụ có thể gọi; `Future` biểu diễn kết quả của một công việc có thể hoàn tất trong tương lai nhưng thường chỉ cho phép chờ lấy kết quả; `CompletionStage` mô tả các bước tính toán có thể nối tiếp khi kết quả sẵn sàng. Vì vậy, lựa chọn API chuyển đổi phải dựa trên việc tác vụ đã bắt đầu hay chưa, có thể thực thi lại cho từng subscription hay không và có cần chặn thread để lấy kết quả hay không.

## 1. Bản đồ các kiểu nguồn Java và API Reactor

| Kiểu Java | API Reactor thường dùng | Thời điểm lấy kết quả | Lưu ý chính |
|---|---|---|---|
| `Callable<T>` | `Mono.fromCallable(callable)` | Khi subscription tiêu thụ nguồn | Cho phép ném checked exception; lỗi trở thành `onError` |
| `Supplier<T>` | `Mono.fromSupplier(supplier)` | Khi subscription tiêu thụ nguồn | Không khai báo checked exception; `null` tạo Mono rỗng |
| `CompletableFuture<T>` | `Mono.fromFuture(future)` | Future có thể đã chạy trước khi subscribe | Các subscriber cùng wrapper quan sát cùng Future |
| `Supplier<CompletableFuture<T>>` | `Mono.fromFuture(futureSupplier)` | Supplier được gọi theo subscription | Có thể tạo một Future mới cho mỗi subscriber |
| `CompletionStage<T>` | `Mono.fromCompletionStage(stage)` | Stage có thể đã được tạo trước khi subscribe | Hỗ trợ abstraction CompletionStage rộng hơn |
| `Supplier<CompletionStage<T>>` | `Mono.fromCompletionStage(stageSupplier)` | Supplier được gọi theo subscription | Trì hoãn việc tạo stage cho từng subscriber |
| `Future<T>` thông thường | `Mono.fromCallable(future::get)` | Khi subscription gọi `get()` | `get()` blocking; cần chuyển sang scheduler phù hợp |

Các API trên tạo `Mono` vì một `Future`, `CompletionStage`, `Callable` hoặc `Supplier` thông thường đại diện cho tối đa một kết quả. Nếu kết quả là một collection và muốn phát từng phần tử, có thể tiếp tục chuyển `Mono<List<T>>` thành `Flux<T>` sau khi nhận được collection.

## 2. `Callable`: trì hoãn tác vụ có thể ném checked exception

`Callable<T>` có phương thức `call()` trả về một giá trị và cho phép khai báo ngoại lệ. `Mono.fromCallable` gọi callable khi có subscription. Nếu callable trả về giá trị khác `null`, Mono phát giá trị đó rồi hoàn tất. Nếu callable trả về `null`, Mono hoàn tất mà không phát `onNext`. Nếu callable ném ngoại lệ, Reactor truyền lỗi xuống subscriber bằng `onError`.

```java
Mono<Account> account = Mono.fromCallable(
    () -> repository.loadAccount(accountId)
);
```

Lời gọi repository nằm bên trong callable nên không chạy khi biến `account` được gán. Nó chạy khi subscription bắt đầu tiêu thụ nguồn. Nếu hai subscriber đăng ký vào cùng Mono này, callable được gọi riêng cho mỗi subscription:

```java
AtomicInteger executions = new AtomicInteger();

Mono<Integer> sequence = Mono.fromCallable(
    executions::incrementAndGet
);

StepVerifier.create(sequence)
    .expectNext(1)
    .verifyComplete();

StepVerifier.create(sequence)
    .expectNext(2)
    .verifyComplete();
```

`Callable` phù hợp với thao tác đồng bộ như truy vấn JDBC, đọc file hoặc gọi một thư viện Java trả về kết quả trực tiếp. Tuy nhiên, trì hoãn đến lúc subscribe không tự biến thao tác blocking thành non-blocking. Nếu callable chờ I/O, cần chọn scheduler để không chặn thread xử lý tín hiệu.

## 3. `Supplier`: tạo giá trị theo subscription

`Supplier<T>` là một hàm không nhận tham số và trả về một giá trị. Khác với `Callable`, phương thức `get()` không khai báo checked exception. Reactor cung cấp `Mono.fromSupplier` để gọi supplier khi có subscription.

```java
Mono<String> requestId = Mono.fromSupplier(
    () -> UUID.randomUUID().toString()
);
```

Mỗi subscription gọi supplier một lần, vì vậy mỗi subscriber có thể nhận một request ID khác nhau. Nếu supplier trả về `null`, Mono hoàn tất rỗng thay vì phát `null`, bởi Reactive Streams không cho phép `null` làm phần tử dữ liệu.

`fromSupplier` phù hợp khi công việc trả về một giá trị và không cần khai báo checked exception. Nếu tác vụ có thể ném checked exception, dùng `fromCallable` để biểu diễn rõ khả năng lỗi đó.

```java
Mono<Instant> timestamp = Mono.fromSupplier(Instant::now);
Mono<Config> config = Mono.fromCallable(configReader::read); // read có thể ném IOException
```

Không nên nhầm `Mono.just(supplier.get())` với `Mono.fromSupplier(supplier)`. Ở cách thứ nhất, `get()` chạy ngay khi Java đánh giá đối số của `just`; ở cách thứ hai, supplier chỉ chạy khi có subscription.

## 4. `CompletableFuture`: chuyển một tác vụ bất đồng bộ đã có

`CompletableFuture<T>` vừa triển khai `Future<T>`, vừa triển khai `CompletionStage<T>`. Nó có thể hoàn tất trong tương lai và cho phép đăng ký các bước xử lý khi kết quả sẵn sàng. Nếu đã có một `CompletableFuture`, dùng `Mono.fromFuture` để chuyển kết quả thành `Mono`:

```java
CompletableFuture<User> future = userClient.fetchAsync(userId);
Mono<User> user = Mono.fromFuture(future);
```

Trong ví dụ, `fetchAsync` được gọi trước khi tạo Mono. Nếu lời gọi đó bắt đầu một request mạng, request có thể đã chạy dù chưa có subscriber. `Mono.fromFuture(future)` bọc Future hiện có; nó không tạo lại công việc cho mỗi subscriber. Nhiều subscriber vào cùng Mono sẽ quan sát kết quả của cùng Future đó. Subscriber đến sau khi Future hoàn tất có thể nhận kết quả đã hoàn tất ngay.

Nếu muốn tạo Future riêng cho từng subscription, truyền một supplier:

```java
Mono<User> user = Mono.fromFuture(
    () -> userClient.fetchAsync(userId)
);
```

Supplier được gọi khi có subscription. Mỗi subscription có thể nhận một `CompletableFuture` mới, do đó mỗi subscriber khởi chạy một lần gọi bất đồng bộ riêng. Đây là lựa chọn thích hợp khi muốn trì hoãn việc gọi client và giữ tính độc lập giữa các subscription.

### Hủy subscription và Future

Khi chuyển `CompletableFuture` bằng `Mono.fromFuture`, Reactor mặc định truyền cancellation từ subscription đến Future bằng cách hủy Future. Nếu cần giữ Future chạy ngay cả khi subscriber hủy, có thể dùng overload có `suppressCancel`:

```java
Mono<User> user = Mono.fromFuture(
    () -> userClient.fetchAsync(userId),
    true // không truyền cancellation xuống Future
);
```

Chỉ tắt truyền cancellation khi có lý do rõ ràng, ví dụ request cần tiếp tục vì một thành phần khác đang sử dụng cùng kết quả. Việc hủy `CompletableFuture` cũng không bảo đảm mọi thao tác bên ngoài như HTTP request hoặc truy vấn database lập tức dừng; khả năng dừng phụ thuộc cách client triển khai cancellation.

Nếu nhiều subscriber dùng chung một Future đã tạo sẵn, cancellation từ một subscription có thể hủy Future mà subscriber khác đang chờ. Khi cần cách ly vòng đời, hãy cân nhắc supplier để tạo Future riêng hoặc một chính sách chia sẻ có chủ đích.

## 5. `CompletionStage`: chuyển một abstraction bất đồng bộ tổng quát

`CompletionStage<T>` biểu diễn một bước tính toán có thể hoàn tất trong tương lai. `CompletableFuture` là implementation phổ biến, nhưng API của thư viện có thể chỉ trả về kiểu `CompletionStage`. Reactor hỗ trợ chuyển trực tiếp kiểu này bằng `Mono.fromCompletionStage`.

```java
CompletionStage<Profile> stage = profileClient.fetchProfile(userId);
Mono<Profile> profile = Mono.fromCompletionStage(stage);
```

Giống như overload nhận Future đã tạo, đoạn mã này bọc một stage có sẵn. Nếu lời gọi `fetchProfile` đã khởi chạy công việc, việc tạo Mono không trì hoãn request đó. Các subscriber của cùng Mono quan sát cùng stage.

Để tạo stage theo từng subscription, truyền supplier:

```java
Mono<Profile> profile = Mono.fromCompletionStage(
    () -> profileClient.fetchProfile(userId)
);
```

Supplier được gọi theo subscription, giúp trì hoãn cả bước tạo stage. Có thể xây dựng stage bằng các phép kết hợp trước khi chuyển sang Reactor:

```java
CompletionStage<User> userStage = userClient.fetchAsync(userId);

CompletionStage<UserView> viewStage = userStage.thenApply(
    user -> UserView.from(user)
);

Mono<UserView> view = Mono.fromCompletionStage(viewStage);
```

Hoặc đưa phần biến đổi vào pipeline Reactor sau khi chuyển đổi:

```java
Mono<UserView> view = Mono.fromCompletionStage(
        () -> userClient.fetchAsync(userId)
    )
    .map(UserView::from);
```

Cách thứ hai cho phép tiếp tục kết hợp với các toán tử Reactor như `map`, `flatMap`, `timeout`, `onErrorMap` và `retry`. Với `CompletionStage` nói chung, không nên mặc định rằng việc hủy subscription có thể dừng tác vụ bên dưới; hành vi đó phụ thuộc implementation và khả năng chuyển stage thành Future có thể hủy.

## 6. Chuyển `Future` thông thường mà không chặn event loop

`Future<T>` cơ bản không cung cấp callback hoàn tất. Cách phổ biến để lấy kết quả là gọi `get()`, nhưng `get()` sẽ chặn thread cho đến khi Future hoàn tất. Reactor không có adapter không blocking tổng quát cho mọi `Future` chỉ bằng interface này.

Có thể bọc `get()` trong `Mono.fromCallable`, rồi dùng `subscribeOn(Schedulers.boundedElastic())` để thao tác chờ chạy trên scheduler dành cho công việc blocking:

```java
Future<Report> future = reportService.startReport();

Mono<Report> report = Mono.fromCallable(() -> {
        try {
            return future.get();
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                "Thread bị ngắt khi chờ báo cáo", error
            );
        }
    })
    .subscribeOn(Schedulers.boundedElastic());
```

`ExecutionException` do `get()` ném ra vẫn được `fromCallable` chuyển thành `onError`. Nếu tầng nghiệp vụ cần xử lý nguyên nhân gốc, có thể ánh xạ lỗi để lấy `getCause()` trong `onErrorMap`. Khi bắt `InterruptedException`, ví dụ khôi phục cờ interrupt trước khi chuyển lỗi thành ngoại lệ để giữ thông tin ngắt của thread.

Đoạn mã trên chỉ chuyển thao tác chờ sang `boundedElastic`; nó không biến `Future` thành API bất đồng bộ thực sự. Nếu có thể thay API nguồn, ưu tiên dùng `CompletableFuture` hoặc `CompletionStage` để nhận callback khi hoàn tất thay vì chiếm một worker để chờ.

### Cancellation với `Future` thông thường

Hủy subscription của `Mono.fromCallable(future::get)` không tự động gọi `future.cancel(...)`. Có thể chủ động nối cancellation với Future:

```java
Mono<Report> report = Mono.fromCallable(() -> future.get())
    .subscribeOn(Schedulers.boundedElastic())
    .doOnCancel(() -> future.cancel(true));
```

`cancel(true)` yêu cầu ngắt tác vụ nếu implementation hỗ trợ. Nó không bảo đảm tác vụ dừng tức thời. Nếu Future được chia sẻ giữa nhiều subscriber, việc một subscriber hủy có thể ảnh hưởng tất cả subscriber còn lại; chỉ nối cancellation theo cách này khi quyền sở hữu Future và chính sách chia sẻ đã rõ ràng.

## 7. Xử lý kết quả rỗng và lỗi

Các nguồn `Mono` không phát `null`. Khi callable hoặc supplier trả về `null`, Mono hoàn tất mà không phát phần tử. Tương tự, stage hoặc Future hoàn tất bình thường với kết quả `null` cũng không thể phát `null` xuống subscriber. Nếu `null` mang ý nghĩa nghiệp vụ, hãy chuyển nó thành kiểu biểu diễn rõ ràng như `Optional<T>` hoặc một đối tượng kết quả riêng.

```java
Mono<Optional<User>> user = Mono.fromCallable(
    () -> repository.findOptional(userId)
);
```

Ở đây, Mono luôn có thể phát một `Optional`, kể cả `Optional.empty()`, vì `Optional.empty()` là một đối tượng khác `null`. Điều này giúp phân biệt “không tìm thấy” với “Publisher hoàn tất rỗng”.

Ngoại lệ đồng bộ phát sinh khi callable hoặc supplier được gọi sẽ trở thành `onError`. Nếu Future hoặc CompletionStage hoàn tất bất thường, lỗi cũng được truyền thành `onError`. Có thể xử lý tiếp bằng các toán tử Reactor:

```java
Mono<User> user = Mono.fromFuture(
        () -> userClient.fetchAsync(userId)
    )
    .onErrorMap(
        error -> new UserFetchException(userId, error)
    )
    .onErrorResume(
        UserFetchException.class,
        error -> cache.findUser(userId)
    );
```

`onErrorMap` đổi lỗi sang loại lỗi nghiệp vụ; `onErrorResume` đăng ký nguồn dự phòng nếu lỗi khớp kiểu. Lưu ý rằng `retry` trên nguồn được tạo từ supplier có thể gọi supplier lại và khởi chạy Future hoặc stage mới. Với Future đã tạo sẵn, retry chỉ đăng ký lại vào cùng Future; nó không tự khởi chạy lại công việc ban đầu.

## 8. Kết hợp kết quả đơn thành `Flux`

`Future` và `CompletionStage` thường trả về một kết quả duy nhất. Nếu kết quả đó là danh sách, có thể dùng `flatMapMany` để chuyển `Mono<List<T>>` thành `Flux<T>`:

```java
Mono<List<Order>> ordersStage = Mono.fromCompletionStage(
    () -> orderClient.fetchOrdersAsync(customerId)
);

Flux<Order> orders = ordersStage.flatMapMany(Flux::fromIterable);
```

`fromCompletionStage` nhận một danh sách như một giá trị của Mono. `flatMapMany` sau đó phát từng phần tử trong danh sách thành tín hiệu `onNext` của Flux. Demand của downstream được áp dụng cho các phần tử mà Flux phát từ iterable; tuy nhiên, request từ xa ban đầu đã trả về cả danh sách nên bản thân bước tải danh sách không nhất thiết có backpressure theo từng đơn hàng.

Nếu API từ xa hỗ trợ phân trang hoặc stream dữ liệu thực sự, nên chuyển từng trang hoặc từng phần tử thành Publisher theo demand thay vì tải toàn bộ danh sách vào bộ nhớ rồi mới chuyển thành Flux.

## 9. Kiểm thử thời điểm thực thi và tín hiệu

Có thể kiểm thử rằng `Callable` và `Supplier` chỉ được gọi khi có subscription:

```java
AtomicInteger calls = new AtomicInteger();
Mono<Integer> source = Mono.fromCallable(calls::incrementAndGet);

assertEquals(0, calls.get());

StepVerifier.create(source)
    .expectNext(1)
    .verifyComplete();

assertEquals(1, calls.get());
```

Với `CompletableFuture`, tạo Future chưa hoàn tất rồi hoàn tất nó trong bước kiểm thử:

```java
CompletableFuture<String> future = new CompletableFuture<>();
Mono<String> source = Mono.fromFuture(future);

StepVerifier.create(source)
    .then(() -> future.complete("done"))
    .expectNext("done")
    .verifyComplete();
```

Kiểm thử lỗi của `CompletionStage`:

```java
CompletableFuture<String> future = new CompletableFuture<>();
Mono<String> source = Mono.fromCompletionStage(future);

StepVerifier.create(source)
    .then(() -> future.completeExceptionally(
        new IllegalStateException("remote failure")
    ))
    .expectError(IllegalStateException.class)
    .verify();
```

Các bài kiểm thử này xác nhận kết quả và tín hiệu kết thúc mà subscriber quan sát được. Với overload nhận supplier, nên bổ sung kiểm tra supplier được gọi một lần cho mỗi subscription. Với Future dùng chung, nên kiểm tra rằng các subscriber nhận cùng kết quả và đánh giá chính sách cancellation để tránh một subscriber hủy công việc mà subscriber khác vẫn cần.

## 10. Chọn API chuyển đổi

Trước khi chuyển một tác vụ Java vào pipeline, hãy xác định nguồn hiện có thuộc trường hợp nào:

1. **Có một phép tính đồng bộ trả về giá trị?** Dùng `Mono.fromCallable` nếu cần hỗ trợ checked exception; dùng `Mono.fromSupplier` cho supplier đơn giản.
2. **Đã có `CompletableFuture` đang chạy hoặc đã hoàn tất?** Dùng `Mono.fromFuture(future)` và nhớ rằng các subscriber dùng chung Future đó.
3. **Muốn khởi chạy Future theo từng subscription?** Dùng overload nhận supplier của `Mono.fromFuture`.
4. **API trả về `CompletionStage`?** Dùng `Mono.fromCompletionStage`; dùng overload supplier nếu cần trì hoãn việc tạo stage.
5. **Chỉ có `Future` không có callback?** Bọc `get()` bằng `fromCallable` trên `boundedElastic`, đồng thời xác định chính sách interruption và cancellation.
6. **Kết quả là collection?** Giữ nó dưới dạng `Mono<Collection<T>>` nếu cần toàn bộ kết quả, hoặc chuyển thành `Flux<T>` bằng `flatMapMany` nếu muốn xử lý từng phần tử.

Khi chuyển đổi đúng, pipeline có thể quản lý kết quả, lỗi và nhu cầu tiêu thụ theo hợp đồng reactive. Điều quan trọng là giữ rõ ranh giới giữa việc tạo tác vụ, thực thi tác vụ và đăng ký Publisher: `Callable`/`Supplier` có thể trì hoãn việc thực thi, Future/CompletionStage có thể đã chạy trước khi được bọc, còn `Future.get()` có thể chặn thread nếu không được đặt trên scheduler phù hợp.
