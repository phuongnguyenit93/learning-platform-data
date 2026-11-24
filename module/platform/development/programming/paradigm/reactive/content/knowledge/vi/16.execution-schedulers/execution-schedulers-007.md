# Cô lập lời gọi chặn vào tài nguyên thực thi có giới hạn

Trong một ứng dụng reactive, một lời gọi I/O chặn có thể giữ luồng đang thực thi cho tới khi file, database hoặc dịch vụ mạng trả kết quả. Nếu lời gọi đó chạy trên event loop hoặc scheduler dùng chung cho nhiều tác vụ non-blocking, một thao tác chậm có thể làm trì hoãn nhiều luồng xử lý khác. Khi tích hợp thư viện Java cũ hoặc API chưa có phiên bản reactive, cần cô lập lời gọi chặn vào một nhóm luồng được giới hạn tài nguyên.

Project Reactor cung cấp `Schedulers.boundedElastic()` cho các tác vụ có thời gian chờ blocking. Scheduler này giới hạn số luồng thực thi và số tác vụ được xếp hàng, nhờ đó hệ thống có thể tiếp nhận một lượng công việc chờ hữu hạn mà không tạo luồng vô hạn. Để dùng đúng, cần trì hoãn lời gọi tới lúc subscription, chuyển việc thực thi nguồn sang scheduler phù hợp, giới hạn concurrency của producer và hiểu rõ điều gì xảy ra khi scheduler quá tải hoặc subscriber hủy.

## 1. Vì sao lời gọi chặn cần được cô lập?

Một hàm đồng bộ như `legacyClient.fetch(id)` không trả quyền điều khiển cho caller cho tới khi hoàn tất. Nếu gọi trực tiếp trong một toán tử chạy trên event loop, luồng đó bị giữ trong suốt thời gian chờ:

```java
Flux<User> users = userIds
    .map(id -> legacyClient.fetch(id)); // Có thể chặn thread đang xử lý pipeline.
```

Trong WebFlux, event loop thường phục vụ nhiều kết nối. Khi một callback blocking chiếm event-loop thread, các request khác dùng chung luồng đó phải chờ dù chúng không liên quan đến lời gọi chậm. Nếu nhiều lời gọi blocking cùng chạy trên một nhóm luồng nhỏ, số request chậm có thể làm toàn bộ hệ thống giảm thông lượng.

Việc chuyển lời gọi chặn sang một scheduler riêng giúp cô lập ảnh hưởng. Các event-loop thread có thể tiếp tục xử lý tín hiệu và request khác trong khi worker thread chờ I/O. Tuy nhiên, cô lập không làm cho lời gọi blocking trở thành non-blocking: worker thread vẫn bị giữ trong thời gian lời gọi chưa trả về. Vì vậy, số worker và số tác vụ chờ phải có giới hạn.

## 2. Dùng boundedElastic với fromCallable

`Schedulers.boundedElastic()` là scheduler dùng chung của Reactor dành cho tác vụ blocking. Cách phổ biến để bọc một lời gọi đồng bộ là `Mono.fromCallable` kết hợp `subscribeOn`:

```java
Mono<User> user = Mono.fromCallable(
        () -> legacyUserClient.fetch(userId)
    )
    .subscribeOn(Schedulers.boundedElastic());
```

`fromCallable` trì hoãn việc gọi `fetch` cho tới khi có subscription. `subscribeOn` khiến quá trình subscribe vào nguồn và việc chạy callable diễn ra trên scheduler được chỉ định. Khi caller subscribe, Reactor gửi tác vụ tới bounded elastic; worker thread thực hiện lời gọi blocking và phát kết quả hoặc lỗi khi callable hoàn tất.

Không viết lời gọi blocking trực tiếp bên trong `Mono.just`:

```java
// Sai mục đích: fetch được gọi ngay khi biểu thức được đánh giá.
Mono<User> wrong = Mono.just(legacyUserClient.fetch(userId))
    .subscribeOn(Schedulers.boundedElastic());
```

Đối số của `Mono.just(...)` được tính trước khi `Mono` được tạo. Vì vậy, `subscribeOn` ở phía sau không thể chuyển lời gọi đã xảy ra sang scheduler khác. Dùng `fromCallable` hoặc `defer` để trì hoãn lời gọi:

```java
Mono<User> alsoDeferred = Mono.defer(() ->
    Mono.just(legacyUserClient.fetch(userId))
).subscribeOn(Schedulers.boundedElastic());
```

Trong trường hợp hàm blocking có thể trả `null`, `fromCallable` chuyển kết quả null thành publisher rỗng thay vì phát `onNext(null)`. Nếu null mang ý nghĩa nghiệp vụ riêng, hãy chuyển đổi nó thành kiểu kết quả rõ ràng trong callable hoặc toán tử tiếp theo.

Với thao tác blocking không trả giá trị, dùng `Mono.fromRunnable`:

```java
Mono<Void> writeAudit = Mono.fromRunnable(
        () -> legacyAuditClient.write(event)
    )
    .subscribeOn(Schedulers.boundedElastic());
```

Publisher này hoàn tất khi runnable chạy xong hoặc phát lỗi nếu lời gọi ném exception. Caller vẫn có thể compose nó bằng `then`, `thenReturn` và các toán tử xử lý lỗi.

## 3. subscribeOn và publishOn có vai trò khác nhau

`subscribeOn` điều khiển scheduler dùng để subscribe vào nguồn và thực thi nguồn. Với một callable blocking, đặt `subscribeOn` trên publisher tạo callable là cách rõ ràng để cô lập lời gọi:

```java
Mono<Record> record = Mono.fromCallable(() -> dao.load(recordId))
    .subscribeOn(Schedulers.boundedElastic());
```

`publishOn` chuyển việc xử lý các tín hiệu downstream kể từ vị trí toán tử đó sang scheduler được chỉ định:

```java
Mono<View> view = recordPublisher
    .publishOn(Schedulers.boundedElastic())
    .map(record -> legacyFormatter.format(record));
```

Trong ví dụ này, `legacyFormatter.format` chạy trên bounded elastic vì nó nằm sau `publishOn`. Các toán tử trước điểm đó vẫn xử lý theo scheduler hiện tại. Có thể dùng `publishOn` khi cần chuyển một đoạn xử lý downstream sang scheduler khác; với lời gọi blocking nằm ngay ở nguồn, `fromCallable(...).subscribeOn(...)` thường thể hiện ý định trực tiếp hơn.

| Toán tử | Phạm vi tác động | Trường hợp thường dùng |
| --- | --- | --- |
| `subscribeOn(scheduler)` | Quá trình subscribe và thực thi nguồn | Đưa callable hoặc nguồn blocking sang bounded elastic |
| `publishOn(scheduler)` | Các toán tử downstream sau vị trí đặt nó | Chuyển một đoạn xử lý sau khi đã nhận dữ liệu |

Không nên nghĩ rằng `publishOn` và `subscribeOn` thay thế nhau trong mọi vị trí. Hãy đặt scheduler sát với ranh giới blocking để người đọc dễ xác định thread nào sẽ bị giữ trong lúc chờ.

## 4. Giới hạn luồng và hàng đợi của boundedElastic

Khác với một executor tạo thread không giới hạn, bounded elastic giới hạn số worker thread có thể được sử dụng và số tác vụ được xếp hàng chờ thực thi. Khi worker đang bận, tác vụ mới có thể chờ trong hàng đợi trong giới hạn cấu hình. Khi giới hạn hàng đợi bị vượt, việc gửi tác vụ có thể bị từ chối và pipeline nhận lỗi thay vì hệ thống tiếp tục tích lũy công việc vô hạn.

Các giới hạn mặc định của scheduler dùng chung có thể được điều chỉnh bằng cấu hình Reactor và có thể khác theo phiên bản hoặc môi trường chạy. Vì vậy, hãy kiểm tra cấu hình thực tế của ứng dụng thay vì coi một con số mặc định là bảo đảm cố định. Hai đại lượng cần quan sát là:

- **Thread cap:** số worker thread tối đa có thể thực thi tác vụ blocking đồng thời.
- **Queue cap:** số tác vụ có thể chờ trên các worker trước khi bị từ chối.

Hàng đợi có giới hạn giúp bảo vệ bộ nhớ, nhưng không tự động làm producer chậm lại. Đây không phải là backpressure của Reactive Streams. Nếu producer tiếp tục gửi tác vụ nhanh hơn tốc độ worker hoàn tất, hàng đợi sẽ đầy và hệ thống cần một chính sách xử lý quá tải.

Khi scheduler từ chối tác vụ do quá tải hoặc đã bị dispose, lỗi từ quá trình lập lịch có thể được chuyển xuống publisher. Hãy xử lý lỗi đó như một tín hiệu quá tải hoặc lỗi hạ tầng; không retry vô hạn vì điều đó có thể làm tăng thêm áp lực lên scheduler.

## 5. Giới hạn concurrency khi gọi nhiều API blocking

Một pipeline có thể gọi một API blocking cho từng phần tử. Nếu dùng `flatMap` không giới hạn phù hợp, nó có thể tạo nhiều inner publisher và gửi nhiều tác vụ vào scheduler. Hãy đặt giới hạn concurrency dựa trên năng lực thực tế của dịch vụ và pool tài nguyên:

```java
Flux<User> users = userIds.flatMap(
    id -> Mono.fromCallable(() -> legacyUserClient.fetch(id))
        .subscribeOn(Schedulers.boundedElastic()),
    12
);
```

Tham số `12` giới hạn số inner publisher đang hoạt động đồng thời. Khi một lời gọi hoàn tất, `flatMap` có thể xử lý phần tử tiếp theo. Giới hạn này giúp tránh gửi hàng nghìn tác vụ blocking vào scheduler cùng một lúc.

Chọn concurrency theo tài nguyên phía sau. Nếu HTTP client chỉ có 20 connection, đặt concurrency hàng nghìn có thể khiến worker thread chờ connection thay vì thực hiện I/O. Nếu database pool có 10 connection, concurrency cao hơn nhiều so với 10 có thể chỉ tạo thêm hàng đợi ở pool database. Cần xem xét cả giới hạn thread, connection pool, quota dịch vụ và độ trễ downstream.

Nếu cần giữ thứ tự đầu ra, có thể dùng `concatMap` để chỉ xử lý một inner tại một thời điểm hoặc `flatMapSequential` để chạy một số inner đồng thời nhưng phát kết quả theo thứ tự nguồn. Việc giữ thứ tự có thể tăng độ trễ khi một lời gọi đầu tiên chậm; hãy cân bằng yêu cầu thứ tự với thông lượng.

## 6. Tạo scheduler riêng cho một nhóm tài nguyên

`Schedulers.boundedElastic()` là scheduler dùng chung. Nếu nhiều loại hệ thống blocking cùng sử dụng nó, một nhóm tác vụ chậm có thể chiếm worker và hàng đợi, ảnh hưởng tới các nhóm khác. Khi cần cô lập theo dependency hoặc có giới hạn tài nguyên riêng, có thể tạo scheduler bounded elastic chuyên dụng:

```java
final class LegacyDatabaseAdapter {
    private final Scheduler legacyDatabaseScheduler =
        Schedulers.newBoundedElastic(
            8,       // Số worker thread tối đa
            200,     // Giới hạn tác vụ chờ trên mỗi backing thread
            "legacy-db"
        );

    Mono<Customer> loadCustomer(String customerId) {
        return Mono.fromCallable(
                () -> legacyDatabase.loadCustomer(customerId)
            )
            .subscribeOn(legacyDatabaseScheduler);
    }

    @PreDestroy
    void shutdown() {
        legacyDatabaseScheduler.dispose();
    }
}
```

Scheduler riêng giúp đặt giới hạn độc lập và đặt tên thread để quan sát trong log hoặc thread dump. Nó cũng tạo thêm một tài nguyên cần quản lý. Ví dụ đặt scheduler thành field của adapter, tái sử dụng cho các lời gọi thuộc cùng nhóm và dispose khi component dừng.

Không tạo `newBoundedElastic` cho từng request hoặc từng phần tử. Cách đó tạo nhiều scheduler và thread pool nhỏ, làm tăng chi phí quản lý và khiến giới hạn tổng thể khó kiểm soát. Với scheduler dùng chung do Reactor cung cấp, ứng dụng không tự dispose nó.

## 7. Chọn scheduler theo đặc tính công việc

`boundedElastic` phù hợp với lời gọi blocking có thời gian chờ, nhưng không phải scheduler tối ưu cho mọi loại công việc:

| Scheduler | Đặc tính | Công việc phù hợp |
| --- | --- | --- |
| `Schedulers.boundedElastic()` | Worker và hàng đợi có giới hạn | Blocking I/O, thư viện đồng bộ cũ |
| `Schedulers.parallel()` | Pool cố định gắn với năng lực CPU | Tính toán CPU-bound ngắn, không blocking |
| `Schedulers.single()` | Một luồng worker tuần tự | Công việc cần tuần tự hóa trên một worker |
| `Schedulers.immediate()` | Thực thi ngay trên thread hiện tại | Không chuyển luồng; không dùng để cô lập blocking |

Không chuyển một tác vụ CPU-bound nặng sang bounded elastic chỉ vì nó có thể chạy bất đồng bộ. Công việc tính toán nên dùng scheduler phù hợp với CPU, còn blocking I/O nên được cô lập để không chiếm các worker dành cho xử lý CPU hoặc event loop.

## 8. Timeout và cancellation không đảm bảo dừng được API blocking

Có thể đặt timeout cho publisher bọc lời gọi blocking:

```java
Mono<Response> response = Mono.fromCallable(
        () -> legacyClient.call(request)
    )
    .subscribeOn(Schedulers.boundedElastic())
    .timeout(Duration.ofSeconds(2));
```

Nếu quá hai giây mà chưa có kết quả, downstream nhận lỗi timeout và subscription bị hủy theo pipeline. Tuy nhiên, timeout reactive không bảo đảm thư viện blocking bên dưới dừng ngay. Nếu API không hỗ trợ interrupt hoặc timeout riêng, worker thread có thể tiếp tục bị giữ cho tới khi lời gọi tự trả về.

Vì vậy, hãy cấu hình timeout ngay trong HTTP client, JDBC driver hoặc thư viện tương ứng. Nếu API hỗ trợ interrupt/cancellation, xác minh cơ chế đó hoạt động đúng với scheduler và thư viện đang dùng. Không dựa vào `.timeout(...)` như biện pháp duy nhất để giới hạn thời gian chiếm thread.

Cancellation vẫn quan trọng vì nó ngăn pipeline tiếp tục chuyển kết quả tới subscriber đã rời đi và cho phép các nguồn hỗ trợ hủy giải phóng tài nguyên. Nhưng với một hàm Java đồng bộ không có khả năng hủy, cancellation chỉ có thể dừng việc quan sát kết quả ở tầng reactive; công việc nền có thể vẫn chạy.

## 9. Xử lý lỗi và quá tải

Lời gọi blocking có thể ném exception nghiệp vụ, lỗi kết nối, lỗi timeout của client hoặc lỗi lập lịch do scheduler quá tải. `fromCallable` chuyển exception phát sinh trong callable thành `onError`, nên có thể xử lý bằng các toán tử Reactor:

```java
Mono<Customer> customer = Mono.fromCallable(
        () -> legacyDatabase.loadCustomer(customerId)
    )
    .subscribeOn(legacyDatabaseScheduler)
    .onErrorMap(SQLException.class,
        error -> new CustomerStoreException(customerId, error))
    .onErrorResume(TransientClientException.class, error ->
        fallbackCustomerService.find(customerId)
    );
```

Chỉ retry lỗi có thể phục hồi và thao tác có thể thực hiện lại an toàn. Không retry tự động mọi lỗi quá tải của scheduler; nếu nhiều request cùng retry ngay, hệ thống có thể tạo thêm tải vào đúng tài nguyên đang bão hòa. Hãy dùng retry có giới hạn, backoff và jitter khi nghiệp vụ cho phép, đồng thời giới hạn concurrency đầu vào.

Khi scheduler chuyên dụng bị dispose trong lúc còn tác vụ mới được gửi tới, việc lập lịch có thể thất bại. Điều này thường chỉ ra lifecycle của component đã kết thúc hoặc có request đến muộn. Hãy dừng nhận công việc trước khi dispose scheduler, và theo dõi lỗi lập lịch để phát hiện thứ tự shutdown sai.

## 10. Kiểm thử việc cô lập lời gọi blocking

Một test có thể xác minh callable chỉ được chạy khi subscribe và được thực thi trên thread do scheduler quản lý:

```java
AtomicReference<String> threadName = new AtomicReference<>();

Mono<String> work = Mono.fromCallable(() -> {
    threadName.set(Thread.currentThread().getName());
    return "done";
}).subscribeOn(Schedulers.boundedElastic());

assertNull(threadName.get()); // Callable chưa chạy khi chưa subscribe.

StepVerifier.create(work)
    .expectNext("done")
    .verifyComplete();

assertNotNull(threadName.get());
assertTrue(threadName.get().contains("boundedElastic"));
```

Assertion tên thread phù hợp cho test minh họa nhưng có thể phụ thuộc cách đặt tên thread của phiên bản Reactor. Trong test ứng dụng, thường tốt hơn nếu kiểm tra hành vi quan sát được, ví dụ callable chưa chạy trước subscription, kết quả/lỗi được truyền đúng, giới hạn concurrency không bị vượt và scheduler được dispose khi component dừng.

Không dùng `Thread.sleep` tùy ý để chờ worker trong test. Dùng `StepVerifier`, latch hoặc công cụ đồng bộ hóa phù hợp. Với test giới hạn concurrency, tạo callable có tín hiệu bắt đầu/kết thúc để đo số tác vụ đang chạy đồng thời và xác minh giá trị cực đại không vượt cấu hình.

## 11. Những lỗi triển khai thường gặp

- Gọi blocking trước khi tạo publisher, ví dụ `Mono.just(client.fetch())`; lời gọi đã xảy ra trước `subscribeOn`.
- Đưa lời gọi blocking vào `map` trên event loop hoặc `Schedulers.parallel()`.
- Dùng `block()` trong controller hoặc trong một callback đang chạy trên event loop để chờ publisher khác.
- Dùng `boundedElastic` như một hàng đợi vô hạn và bỏ qua giới hạn concurrency của producer.
- Tạo scheduler mới cho từng request thay vì tái sử dụng scheduler theo lifecycle.
- Chỉ đặt timeout reactive mà không cấu hình timeout của thư viện blocking bên dưới.
- Retry vô hạn khi scheduler hoặc dịch vụ downstream đang quá tải.

Khi review một pipeline có tích hợp API đồng bộ, hãy tìm chính xác dòng thực hiện blocking, kiểm tra nó được trì hoãn tới subscription hay chưa, xác định scheduler thực thi và xem concurrency/queue có giới hạn hay không. Sau đó kiểm tra lỗi, timeout và shutdown để chắc chắn worker thread không bị giữ ngoài dự kiến.

## 12. Quy trình chọn và cấu hình tài nguyên thực thi

Hãy bắt đầu bằng việc xác định API nào thực sự blocking và tài nguyên phía sau có giới hạn gì. Bọc lời gọi bằng `Mono.fromCallable` hoặc `Mono.fromRunnable`, rồi dùng `subscribeOn(Schedulers.boundedElastic())` để chuyển nguồn sang nhóm worker phù hợp. Nếu cần cô lập một dependency riêng, tạo một bounded elastic scheduler chuyên dụng với thread cap và queue cap phù hợp, tái sử dụng nó và dispose theo lifecycle.

Tiếp theo, giới hạn số inner publisher bằng concurrency của `flatMap` hoặc chọn `concatMap` khi cần tuần tự. Đồng bộ giới hạn này với connection pool, quota và năng lực downstream. Cấu hình timeout ở chính client blocking, xử lý lỗi quá tải có giới hạn và đo queue/thread usage trong vận hành. `boundedElastic` là một vùng cô lập có giới hạn cho API đồng bộ; nó giúp bảo vệ các luồng non-blocking khi được dùng cùng với kiểm soát tải và quản lý vòng đời đúng cách.
