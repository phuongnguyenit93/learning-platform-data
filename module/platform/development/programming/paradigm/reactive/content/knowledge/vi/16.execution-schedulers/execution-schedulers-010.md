# Nguy cơ tự chờ, bế tắc và chặn vòng lặp sự kiện

Một pipeline reactive có thể bất đồng bộ ở giao diện nhưng vẫn bị chặn bởi cách một đoạn mã chờ kết quả. Những lời gọi như `block()`, `Future.get()`, `join()`, `CountDownLatch.await()` hoặc thao tác I/O đồng bộ có thể giữ một worker trong lúc công việc cần thiết để hoàn tất lại đang chờ chính worker đó. Trên một event loop, một lời gọi blocking còn có thể làm chậm nhiều kết nối cùng lúc.

Trong module `REACTIVE_PROGRAMMING`, người học thực hành các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams; đồng thời sử dụng `Mono`, `Flux`, operator, scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Bài học này tập trung nhận diện ba rủi ro liên quan chặt chẽ: tự chờ (*self-wait*), bế tắc (*deadlock*) và chặn event loop (*event-loop blocking*). Mục tiêu là giữ công việc trong cùng một chuỗi reactive, đặt thao tác blocking đúng scheduler và để việc hủy subscription có thể truyền đến nguồn.

## 1. Vì sao một lời gọi chờ có thể phá vỡ pipeline reactive?

Reactive Streams truyền tín hiệu dữ liệu bằng `onNext`, tín hiệu kết thúc bằng `onComplete` hoặc `onError`, và nhu cầu nhận dữ liệu bằng `request(n)`. Các operator phối hợp những tín hiệu này mà không yêu cầu ứng dụng phải chặn thread để đợi kết quả.

Khi gọi `block()` hoặc `get()` bên trong pipeline, thread đang xử lý phải dừng lại cho đến khi kết quả có mặt. Nếu công việc tạo ra kết quả cần chạy trên cùng scheduler nhưng scheduler không còn worker rảnh, hệ thống có thể rơi vào tình trạng tự chờ.

Ví dụ một bước xử lý đã có publisher:

```java
Mono<Profile> profile = profileClient.findById(id);

Mono<ProfileView> view = profile
    .map(this::toView);
```

Pipeline trên mô tả quan hệ bất đồng bộ. Subscriber đăng ký vào `view`, Reactor điều phối việc lấy profile và chuyển kết quả qua `map`.

Nếu chuyển publisher thành lời gọi đồng bộ bên trong callback:

```java
Mono<ProfileView> unsafe = Mono.just(id)
    .map(profileId -> profileClient.findById(profileId).block())
    .map(this::toView);
```

`block()` tạo một subscription riêng cho publisher con rồi giữ thread đang chạy `map` cho đến khi subscription đó có kết quả. Cách viết này phá vỡ tính không chặn của pipeline, tách công việc con khỏi demand và lifecycle của chuỗi ngoài, đồng thời có thể gây lỗi ngay nếu thread hiện tại được đánh dấu là non-blocking.

## 2. Phân biệt self-wait, deadlock và event-loop blocking

Ba hiện tượng có liên quan nhưng không đồng nghĩa.

| Hiện tượng | Điều xảy ra | Hậu quả thường gặp |
|---|---|---|
| Self-wait | Một tác vụ chờ kết quả từ công việc mà nó đã khởi chạy hoặc đang giữ điều kiện để công việc đó chạy. | Worker bị giữ trong lúc kết quả không thể được tạo. |
| Deadlock | Hai hay nhiều tác vụ giữ tài nguyên hoặc chờ điều kiện theo vòng khép kín. | Không tác vụ nào trong vòng chờ có thể tiếp tục. |
| Thread starvation | Các worker khả dụng đều bị chiếm bởi tác vụ đang chờ hoặc chạy quá lâu. | Tác vụ mới nằm trong hàng đợi dù không có khóa vòng tròn rõ ràng. |
| Event-loop blocking | Một callback trên event loop thực hiện công việc blocking hoặc chạy quá lâu. | Nhiều channel/kết nối dùng chung event loop bị chậm. |

### Tự chờ trên một scheduler có một worker

Giả sử scheduler chỉ có một worker. Tác vụ cha chạy trên worker đó, sau đó đăng ký tác vụ con trên cùng scheduler và chờ kết quả con bằng `block()`:

```text
Scheduler chỉ có một worker

Worker 1: [ chạy tác vụ cha ---------------- chờ kết quả con ]
Hàng đợi:                                      [ tác vụ con ]

Tác vụ con chỉ chạy được khi Worker 1 rảnh.
Worker 1 chỉ rảnh khi tác vụ cha kết thúc.
Tác vụ cha chỉ kết thúc khi tác vụ con chạy xong.
```

Không có worker thứ hai để thực thi tác vụ con. Đây là self-wait có thể dẫn đến deadlock hoặc timeout.

### Deadlock do nhiều khóa

Một deadlock cổ điển xảy ra khi tác vụ A giữ khóa X rồi chờ khóa Y, trong khi tác vụ B giữ khóa Y rồi chờ khóa X. Dù pipeline dùng `Mono` hay `Flux`, các đoạn `synchronized`, `Lock.lock()` hoặc API blocking vẫn có thể tạo vòng chờ như vậy. Reactive không tự loại bỏ deadlock ở tầng tài nguyên dùng chung.

### Event loop bị chặn

Trong server như Reactor Netty, event loop thường phục vụ nhiều channel. Nếu một handler gọi JDBC đồng bộ hoặc `block()`, thread event loop dừng xử lý các sự kiện khác trong lúc chờ. Một request chậm có thể làm tăng độ trễ cho nhiều request không liên quan.

```text
Event loop E1 phục vụ Channel A, B, C

Channel A -> handler -> gọi JDBC đồng bộ -> chờ 800 ms
                         |
                         +-- E1 bị giữ

Channel B -> dữ liệu đã sẵn sàng nhưng chưa được xử lý
Channel C -> dữ liệu đã sẵn sàng nhưng chưa được xử lý
```

Vấn đề không chỉ là request A chậm. B và C cũng phải đợi vì dùng chung event loop.

## 3. Reactor bảo vệ một số thread non-blocking

Reactor đánh dấu một số thread scheduler là non-blocking. Các phương thức chặn như `block()`, `blockFirst()` và `blockLast()` được kiểm tra khi chạy trên những thread này; nếu phát hiện lời gọi không hợp lệ, Reactor ném `IllegalStateException` với thông báo cho biết thao tác blocking không được hỗ trợ trên thread hiện tại.

Các scheduler thường dùng có vai trò khác nhau:

| Scheduler | Mục đích chính | Lưu ý |
|---|---|---|
| `Schedulers.parallel()` | Công việc tính toán CPU-bound, ngắn và không blocking. | Worker được đánh dấu non-blocking; không gọi `block()` hoặc I/O đồng bộ. |
| `Schedulers.single()` | Công việc tuần tự trên một worker. | Một tác vụ chậm có thể trì hoãn mọi tác vụ khác trên scheduler đó. |
| `Schedulers.boundedElastic()` | Tích hợp API blocking như JDBC, file I/O hoặc thư viện đồng bộ. | Có giới hạn thread và hàng đợi; không phải nơi để tạo số lượng tác vụ blocking vô hạn. |
| `Schedulers.immediate()` | Thực thi ngay trên thread hiện tại. | Không chuyển thread và không làm thao tác blocking trở nên an toàn. |

Reactor Netty event loop cũng là môi trường non-blocking. Không nên dùng nó để chạy lời gọi chặn như truy vấn JDBC đồng bộ, `Thread.sleep()` hoặc chờ `Future.get()`.

Việc một lời gọi chưa bị Reactor phát hiện không có nghĩa là nó an toàn. Ví dụ, `Future.get()` hoặc `CountDownLatch.await()` có thể chặn thread mà không đi qua guard của `block()`. Cần đánh giá bản chất thao tác, không chỉ dựa vào việc có exception hay không.

## 4. Ví dụ tự chờ trên scheduler bị giới hạn

Một scheduler có một worker có thể minh họa rõ việc tác vụ cha chờ tác vụ con trên cùng hàng đợi:

```java
Scheduler oneWorker = Schedulers.newBoundedElastic(
    1,      // chỉ một worker
    100,    // giới hạn tác vụ đang chờ
    "one-worker"
);

Mono<String> child = Mono.fromCallable(() -> "child result")
    .subscribeOn(oneWorker);

Mono<String> parent = Mono.fromCallable(() -> child.block())
    .subscribeOn(oneWorker);

// Không chạy cách kết hợp này trong mã ứng dụng:
// parent.block(Duration.ofSeconds(1));
```

Tác vụ `parent` chiếm worker duy nhất rồi gọi `child.block()`. Publisher `child` được subscribe trên cùng scheduler, nhưng worker duy nhất đang bận chờ. Khi không có worker khác thực thi `child`, tác vụ cha không thể nhận kết quả. Ví dụ đặt thời hạn ở lời gọi ngoài chỉ nhằm tránh chờ vô hạn khi thử nghiệm; timeout không sửa được thiết kế tự chờ.

Cách đúng là kết hợp publisher con bằng operator:

```java
Mono<String> safe = Mono.fromCallable(this::createParentInput)
    .subscribeOn(oneWorker)
    .flatMap(input -> childFor(input));
```

Trong ứng dụng thật, `childFor(input)` trả về publisher và không tự gọi `block()`. Reactor có thể phối hợp subscription và tín hiệu của các bước mà không giữ worker cha trong lúc chờ worker con.

Khi dùng scheduler do ứng dụng tạo, hãy dispose scheduler ở lifecycle shutdown tương ứng:

```java
oneWorker.dispose();
```

Không dispose scheduler toàn cục do Reactor quản lý như `Schedulers.parallel()` hoặc `Schedulers.boundedElastic()` chỉ vì một pipeline kết thúc.

## 5. Giữ công việc trong cùng chuỗi bằng `flatMap`

Nếu một bước trả về `Mono` hoặc `Flux`, hãy dùng operator kết hợp thay vì gọi `block()` hoặc `subscribe()` lồng nhau.

Không nên:

```java
Mono<OrderView> unsafe = orderService.findById(orderId)
    .map(order -> {
        Customer customer = customerService
            .findById(order.customerId())
            .block();

        return new OrderView(order, customer);
    });
```

Nên:

```java
Mono<OrderView> safe = orderService.findById(orderId)
    .flatMap(order -> customerService
        .findById(order.customerId())
        .map(customer -> new OrderView(order, customer))
    );
```

`flatMap` đăng ký publisher con và hợp nhất kết quả vào pipeline. Lỗi từ publisher con đi theo nhánh `onError`, cancel có thể truyền xuống subscription con, và không cần giữ một thread chỉ để chờ kết quả.

Nếu nhiều phần tử nguồn cần gọi publisher con, hãy giới hạn concurrency khi dịch vụ đích có năng lực hữu hạn:

```java
Flux<CustomerView> views = customerIds.flatMap(
    customerService::findById,
    12, // số publisher con tối đa đang hoạt động
    4   // prefetch từ mỗi publisher con
);
```

Concurrency giới hạn số lời gọi đang hoạt động. Nó không biến một API blocking thành API non-blocking; nếu `customerService.findById` thực hiện JDBC đồng bộ, phần gọi đó vẫn cần được đặt trên scheduler dành cho blocking.

## 6. Đưa API blocking lên `boundedElastic`

Một ứng dụng có thể phải tích hợp thư viện cũ chỉ cung cấp API đồng bộ. Hãy trì hoãn lời gọi đó đến lúc subscribe và thực thi nó trên `boundedElastic`.

```java
Mono<LegacyProfile> findProfile(String id) {
    return Mono.fromCallable(() -> legacyProfileDao.findById(id))
        .subscribeOn(Schedulers.boundedElastic());
}
```

`fromCallable` trì hoãn việc gọi `legacyProfileDao.findById` cho đến khi có subscription. `subscribeOn(boundedElastic())` chuyển subscription và việc thực thi callable lên scheduler phù hợp với tác vụ blocking.

Sau đó, kết quả có thể tiếp tục đi qua các operator reactive:

```java
Mono<ProfileView> view = findProfile(id)
    .flatMap(profile -> permissionService.load(profile.userId())
        .map(permission -> new ProfileView(profile, permission))
    );
```

Nếu `permissionService` cũng dùng API blocking, adapter của nó cần tự chuyển lời gọi blocking lên scheduler phù hợp. Không nên giả định một lần `subscribeOn` ở một nguồn sẽ tự động làm mọi tác vụ blocking ở bất kỳ nhánh nào trở nên an toàn.

### Vì sao `Mono.just` không giải quyết được blocking?

```java
// Lời gọi DAO chạy ngay khi biểu thức này được tạo.
Mono<LegacyProfile> unsafe = Mono.just(
    legacyProfileDao.findById(id)
);
```

`legacyProfileDao.findById(id)` được thực thi trước khi `Mono.just` nhận giá trị. Thêm `publishOn` sau đó không thể chuyển ngược lời gọi đã xảy ra sang scheduler khác.

```java
// Lời gọi DAO được trì hoãn đến subscription.
Mono<LegacyProfile> safe = Mono.fromCallable(
    () -> legacyProfileDao.findById(id)
).subscribeOn(Schedulers.boundedElastic());
```

Nếu phương thức blocking trả về một collection, có thể dùng `fromCallable` để lấy collection trên `boundedElastic`, sau đó chuyển thành `Flux`:

```java
Flux<LegacyRecord> records = Mono.fromCallable(
        () -> legacyDao.loadAllRecords()
    )
    .subscribeOn(Schedulers.boundedElastic())
    .flatMapMany(Flux::fromIterable);
```

Lưu ý rằng ví dụ này vẫn nạp toàn bộ collection vào bộ nhớ. Nếu tập dữ liệu lớn, hãy dùng API phân trang hoặc cursor có quản lý vòng đời thay vì đọc tất cả một lần.

## 7. `subscribeOn` và `publishOn` không thay thế nhau

Hai operator này điều khiển vị trí thực thi ở các ranh giới khác nhau.

- `subscribeOn` ảnh hưởng đến quá trình subscribe nguồn upstream và thường dùng để chuyển lời gọi nguồn blocking sang scheduler khác.
- `publishOn` chuyển việc xử lý các tín hiệu downstream sau vị trí đặt operator sang scheduler được chọn.

Ví dụ:

```java
Mono<Result> pipeline = Mono.fromCallable(this::blockingLookup)
    .subscribeOn(Schedulers.boundedElastic())
    .publishOn(Schedulers.parallel())
    .map(this::cpuIntensiveTransform);
```

Lời gọi `blockingLookup` chạy trên `boundedElastic`. Sau ranh giới `publishOn`, phép biến đổi CPU-bound chạy trên `parallel`.

Đặt `publishOn` sau một lời gọi blocking không bảo vệ được lời gọi đó:

```java
Mono<Result> unsafe = Mono.fromCallable(this::blockingLookup)
    .publishOn(Schedulers.boundedElastic());
```

Nguồn callable có thể được thực thi trong quá trình subscribe trên thread hiện tại; `publishOn` chuyển các tín hiệu phía sau nó, không chuyển ngược việc thực thi nguồn sang scheduler. Với nguồn blocking, hãy dùng `subscribeOn` ngay tại adapter nguồn.

Một pipeline có thể có nhiều `publishOn` để đặt ranh giới thực thi cho các giai đoạn khác nhau. Hãy tránh thêm scheduler chỉ vì muốn “làm cho reactive hơn”; mỗi ranh giới có thể thêm queue, prefetch và chi phí chuyển thread.

## 8. Chặn event loop bằng API đồng bộ

Trong ứng dụng WebFlux, controller hoặc handler thường trả về `Mono`/`Flux` để server gửi dữ liệu khi sẵn sàng. Nếu handler gọi một API đồng bộ trực tiếp, event loop có thể bị giữ trong suốt thời gian chờ.

Không nên:

```java
@GetMapping("/profiles/{id}")
Mono<Profile> getProfile(@PathVariable String id) {
    Profile profile = jdbcProfileDao.findById(id); // blocking trên event loop
    return Mono.just(profile);
}
```

Nên chuyển thao tác blocking vào adapter:

```java
@GetMapping("/profiles/{id}")
Mono<Profile> getProfile(@PathVariable String id) {
    return Mono.fromCallable(() -> jdbcProfileDao.findById(id))
        .subscribeOn(Schedulers.boundedElastic());
}
```

Tốt hơn nữa, nếu có driver reactive phù hợp như R2DBC hoặc client HTTP reactive, hãy dùng API non-blocking trực tiếp và giữ pipeline không chặn:

```java
@GetMapping("/profiles/{id}")
Mono<Profile> getProfile(@PathVariable String id) {
    return reactiveProfileRepository.findById(id);
}
```

Không nên chuyển toàn bộ handler sang `boundedElastic` chỉ để che giấu một lời gọi blocking. Hãy cô lập ranh giới legacy và dùng driver non-blocking khi phù hợp. Nếu phần lớn xử lý đã reactive, việc giữ event loop rảnh giúp server phục vụ nhiều kết nối với ít thread hơn.

## 9. Những thao tác dễ chặn mà không gọi `block()`

Rủi ro không chỉ đến từ API Reactor. Bất kỳ thao tác đồng bộ nào chờ I/O, khóa hoặc tác vụ khác đều có thể chiếm worker.

| Thao tác | Vì sao nguy hiểm | Hướng xử lý |
|---|---|---|
| `Future.get()` / `CompletableFuture.join()` | Chờ kết quả hoàn tất trên thread hiện tại. | Dùng `Mono.fromFuture` hoặc chuyển future thành publisher và kết hợp bằng operator. |
| `CountDownLatch.await()` | Chờ một thread khác đếm latch về 0. | Kết hợp tín hiệu bất đồng bộ; tránh chờ trong callback. |
| `Thread.sleep()` | Giữ worker trong thời gian ngủ. | Dùng `Mono.delay` hoặc timer phù hợp. |
| JDBC/JPA đồng bộ | Chờ I/O và connection. | Dùng driver reactive hoặc adapter `fromCallable` trên `boundedElastic`. |
| HTTP client đồng bộ | Chờ phản hồi mạng. | Dùng WebClient hoặc adapter blocking trên `boundedElastic`. |
| `InputStream.read()` / `Files.readAllBytes()` | Có thể chờ I/O và nạp dữ liệu lớn. | Dùng API async/reactive hoặc cô lập trên `boundedElastic`, đọc theo chunk. |
| `Lock.lock()` / khóa `synchronized` bị tranh chấp | Có thể chờ thread khác nhả khóa. | Giảm vùng chia sẻ mutable, dùng cấu trúc thread-safe hoặc điều phối tuần tự bằng operator. |
| Tính toán CPU kéo dài | Không chờ I/O nhưng chiếm worker quá lâu. | Chia nhỏ công việc hoặc dùng scheduler CPU-bound với concurrency có giới hạn. |

`Mono.fromFuture(future)` cho phép kết hợp một `CompletableFuture` đã có vào pipeline mà không cần gọi `join()`. Nếu cần tạo future riêng cho từng subscription, dùng supplier tương ứng để tránh chia sẻ một future đã hoàn tất hoặc đã bị hủy ngoài ý muốn.

Ví dụ dùng `Mono.delay` thay cho `Thread.sleep`:

```java
Mono<String> delayed = Mono.delay(Duration.ofSeconds(1))
    .thenReturn("ready");
```

`Mono.delay` lên lịch phát tín hiệu sau thời gian quy định; nó không giữ thread nằm ngủ trong khoảng chờ.

## 10. Vì sao backpressure không cứu được một thread đang bị chặn?

Backpressure giới hạn số phần tử publisher được phép phát dựa trên demand. Nó không thể giải phóng một worker đang mắc kẹt trong `block()`, `get()` hoặc I/O đồng bộ.

Ví dụ, subscriber yêu cầu một phần tử mỗi lần. Nếu callback xử lý phần tử đầu tiên gọi JDBC đồng bộ trong 2 giây trên event loop, demand vẫn được tôn trọng nhưng event loop vẫn bị giữ 2 giây. Những channel khác dùng chung event loop cũng bị ảnh hưởng.

Tương tự, `limitRate`, `onBackpressureBuffer` hoặc giới hạn `flatMap` concurrency không làm một thao tác blocking trở thành non-blocking. Các operator này điều tiết lượng dữ liệu hoặc công việc; scheduler và API nguồn mới quyết định thread có bị giữ trong lúc chờ hay không.

Khi dùng adapter blocking, cần kết hợp:

- Chuyển lời gọi lên `boundedElastic`.
- Giới hạn concurrency để không tạo quá nhiều lời gọi đồng thời.
- Đặt timeout phù hợp cho I/O.
- Đảm bảo cancel có thể truyền đến API nguồn nếu API hỗ trợ hủy.
- Theo dõi thời gian chờ, số worker đang hoạt động và hàng đợi.

## 11. Timeout và cancellation không tự sửa một thiết kế blocking

`timeout(Duration)` có thể phát lỗi khi nguồn không phát tín hiệu trong thời hạn. Nó hữu ích để giới hạn thời gian chờ của một publisher, nhưng không bảo đảm một lời gọi blocking bên trong đã dừng ngay lập tức.

Ví dụ:

```java
Mono<LegacyResult> result = Mono.fromCallable(
        () -> legacyClient.call()
    )
    .subscribeOn(Schedulers.boundedElastic())
    .timeout(Duration.ofSeconds(2));
```

Khi timeout xảy ra, Reactor hủy subscription upstream. Tuy nhiên, một thư viện blocking có thể không hỗ trợ interrupt hoặc cancel, nên thread có thể tiếp tục chạy cho đến khi lời gọi trả về hoặc timeout nội bộ của thư viện xảy ra. Hãy cấu hình timeout tại chính HTTP client, JDBC driver hoặc API blocking khi có thể.

Cancellation là tín hiệu hợp tác. Nguồn cần có cơ chế dừng công việc và giải phóng tài nguyên khi subscription bị hủy. Không nên coi `timeout` là thay thế cho timeout của socket, query hoặc connection pool.

## 12. Mẫu thiết kế an toàn cho một pipeline có cả blocking và reactive

Một hệ thống có thể dùng driver reactive cho phần lớn thao tác, nhưng vẫn phải gọi một thư viện cũ để tra cứu dữ liệu. Hãy cô lập lời gọi đồng bộ thành adapter nhỏ, rồi kết hợp adapter đó với phần reactive.

```java
Mono<LegacyCustomer> findLegacyCustomer(String customerId) {
    return Mono.fromCallable(() -> legacyCustomerDao.find(customerId))
        .subscribeOn(Schedulers.boundedElastic());
}

Mono<OrderView> loadOrderView(String orderId) {
    return reactiveOrderRepository.findById(orderId)
        .flatMap(order -> findLegacyCustomer(order.customerId())
            .map(customer -> new OrderView(order, customer))
        )
        .timeout(Duration.ofSeconds(3));
}
```

Trong thiết kế này:

1. Adapter `findLegacyCustomer` sở hữu ranh giới blocking và chuyển lời gọi lên `boundedElastic`.
2. Repository reactive tiếp tục dùng API non-blocking.
3. `flatMap` nối hai bước mà không chặn thread để chờ kết quả.
4. `timeout` giới hạn thời gian chờ ở cấp pipeline; adapter và thư viện legacy vẫn cần timeout riêng nếu hỗ trợ.

Nếu endpoint bị hủy, cancellation có thể đi qua publisher kết hợp đến nguồn. Khả năng dừng thực tế của lời gọi legacy phụ thuộc API DAO và driver đang dùng.

## 13. Kiểm thử để phát hiện blocking và self-wait

Không nên viết bài kiểm thử có thể deadlock vô thời hạn. Hãy thiết kế test có timeout hữu hạn và kiểm tra scheduler hoặc thread name ở ranh giới cần thiết.

### Kiểm tra adapter blocking chạy trên scheduler phù hợp

```java
Mono<String> adapter = Mono.fromCallable(() ->
        Thread.currentThread().getName()
    )
    .subscribeOn(Schedulers.boundedElastic());

StepVerifier.create(adapter)
    .assertNext(threadName ->
        assertTrue(threadName.startsWith("boundedElastic-"))
    )
    .verifyComplete();
```

Tên thread có thể khác theo phiên bản hoặc cấu hình scheduler; trong dự án thực tế, ưu tiên kiểm tra hành vi và dùng scheduler được tiêm vào adapter nếu cần test ổn định.

### Kiểm tra pipeline kết hợp publisher mà không block

```java
Mono<String> child = Mono.just("child");

Mono<String> composed = Mono.just("parent")
    .flatMap(ignored -> child.map(value -> "result: " + value));

StepVerifier.create(composed)
    .expectNext("result: child")
    .verifyComplete();
```

Kiểm thử này xác minh publisher con được kết hợp vào pipeline và kết quả được chuyển xuống bằng tín hiệu reactive.

### Đặt timeout hữu hạn cho test có nguy cơ chờ

```java
StepVerifier.create(pipeline)
    .expectNextCount(1)
    .verifyComplete(Duration.ofSeconds(2));
```

Timeout giúp bài kiểm thử thất bại thay vì treo vô hạn. Tuy nhiên, một test timeout chỉ cho biết pipeline không hoàn tất đúng hạn; nó không tự xác định nguyên nhân là deadlock, nguồn không phát dữ liệu hay scheduler bị quá tải. Hãy bổ sung quan sát thread, log và trạng thái nguồn để chẩn đoán.

### Kiểm tra không dùng blocking API trên non-blocking scheduler

Có thể viết test xác minh một đoạn code không gọi `block()` bằng cách giữ API trong kiểu reactive và kiểm tra kết quả với `StepVerifier`. Với code tích hợp, Reactor có thể ném `IllegalStateException` nếu `block()` được gọi trên thread non-blocking. Không nên dựa hoàn toàn vào guard này vì nhiều API blocking khác không được guard phát hiện.

## 14. Chẩn đoán khi ứng dụng có dấu hiệu bị kẹt

Khi throughput giảm, độ trễ tăng hoặc request treo, hãy quan sát cả thread và pipeline:

1. **Lấy thread dump:** tìm event loop hoặc worker đang ở `WAITING`, `TIMED_WAITING` hay bị giữ trong lời gọi JDBC, socket, `Future.get`, `LockSupport.park` hoặc `CountDownLatch.await`.
2. **Xác định scheduler:** xem thread thuộc `reactor-http-nio`, `parallel`, `single`, `boundedElastic` hay executor tùy chỉnh.
3. **Tìm lời gọi blocking:** kiểm tra `block`, `get`, `join`, `await`, `sleep`, JDBC/JPA đồng bộ và client HTTP đồng bộ.
4. **Kiểm tra vòng chờ:** tác vụ đang đợi có cần chạy trên cùng scheduler hoặc lấy cùng khóa mà thread đang giữ không?
5. **Đo hàng đợi và concurrency:** số worker bận, số tác vụ chờ, độ dài queue và thời gian thực thi có tăng không?
6. **Kiểm tra cancellation:** khi client ngắt kết nối hoặc timeout, nguồn và tác vụ nền có dừng không?

Một event loop bị chặn thường biểu hiện nhiều request cùng tăng độ trễ dù các request không phụ thuộc nhau. Thread dump có thể cho thấy cùng một event-loop thread đang ở trong lời gọi đồng bộ. Thread starvation trên `boundedElastic` thường biểu hiện worker đều bận, queue tăng và tác vụ mới chờ lâu. Deadlock do khóa thường có chuỗi thread chờ nhau trong monitor hoặc lock.

Đừng kết luận deadlock chỉ từ một request treo. Một nguồn có thể đơn giản là chưa phát dữ liệu hoặc đang chờ I/O lâu. Cần đối chiếu thread dump, log, metric và trạng thái subscription.

## 15. Checklist tránh tự chờ và chặn event loop

- Không gọi `block()`, `blockFirst()` hoặc `blockLast()` bên trong pipeline hoặc trên event loop.
- Không gọi `Future.get()`, `join()`, `CountDownLatch.await()` hay `Thread.sleep()` trong callback reactive.
- Dùng `flatMap`, `concatMap` hoặc operator phù hợp để kết hợp publisher con.
- Dùng `Mono.fromCallable`/`Flux.defer` để trì hoãn lời gọi blocking đến subscription.
- Đặt adapter blocking trên `Schedulers.boundedElastic()`; không đặt `publishOn` sau lời gọi như một cách sửa muộn.
- Dùng `Schedulers.parallel()` cho công việc CPU-bound ngắn, không blocking.
- Không giả định `boundedElastic` có tài nguyên vô hạn; giới hạn concurrency và cấu hình timeout.
- Ưu tiên driver và client reactive thay cho API đồng bộ trong event loop.
- Không gọi `subscribe()` lồng nhau để tạo tác vụ tách khỏi lifecycle của pipeline.
- Kiểm tra cancel có dừng nguồn và giải phóng tài nguyên hay không.
- Dùng timeout hữu hạn trong kiểm thử và kiểm tra thread dump khi cần chẩn đoán.

Một pipeline reactive giữ được lợi ích khi các bước bất đồng bộ tiếp tục được biểu diễn bằng publisher và được kết hợp bằng operator. Khi phải dùng thư viện blocking, hãy cô lập lời gọi ở một adapter có ranh giới scheduler rõ ràng. Cách tổ chức này tránh việc worker tự chờ công việc do chính nó giữ lại, giữ event loop rảnh để phục vụ các kết nối khác và giúp cancellation, lỗi cùng backpressure tiếp tục hoạt động trong cùng một chuỗi xử lý.
