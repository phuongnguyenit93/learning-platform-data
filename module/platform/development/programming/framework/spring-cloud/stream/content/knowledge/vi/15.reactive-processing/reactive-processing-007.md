# Tách thao tác chặn luồng và chọn Scheduler phù hợp

Reactive programming giúp xử lý nhiều message mà không phải giữ một thread chờ cho từng thao tác I/O. Tuy nhiên, một pipeline Reactor chỉ phát huy lợi ích khi các thao tác bên trong không chặn thread đang điều phối luồng dữ liệu. Nếu gọi JDBC đồng bộ, HTTP client blocking, đọc file đồng bộ hoặc `Thread.sleep()` trực tiếp trong operator, thread xử lý reactive có thể bị giữ lại và làm chậm nhiều message khác.

Reactor cung cấp `Scheduler` để quyết định pipeline chạy trên nhóm thread nào. Với thao tác blocking, thường dùng `Schedulers.boundedElastic()` hoặc một scheduler riêng có giới hạn. Với phép tính CPU-bound, dùng `Schedulers.parallel()`. Hai thao tác `subscribeOn` và `publishOn` có vai trò khác nhau: `subscribeOn` ảnh hưởng tới quá trình subscribe và phần upstream, còn `publishOn` chuyển việc thực thi các operator phía sau nó sang scheduler được chọn.

## 1. Vì sao thao tác blocking gây vấn đề trong reactive pipeline?

Reactor sử dụng các thread để nhận tín hiệu, điều phối subscription và thực thi operator. Một số thread có thể phục vụ nhiều luồng message hoặc nhiều kết nối cùng lúc. Nếu một operator gọi hàm blocking, thread hiện tại phải chờ cho tới khi hàm đó trả về.

Ví dụ không phù hợp:

```java
@Bean
Function<Flux<OrderEvent>, Flux<OrderResult>> processOrders(
        LegacyInventoryClient inventoryClient) {

    return events -> events.map(event -> {
        // Hàm đồng bộ giữ thread hiện tại cho đến khi trả về.
        Reservation reservation = inventoryClient.reserve(event);
        return OrderResult.from(event, reservation);
    });
}
```

Nếu `reserve()` dùng HTTP client blocking hoặc JDBC đồng bộ, mỗi lần gọi sẽ giữ thread đang thực thi `map()`. Khi nhiều message đến cùng lúc, các thread điều phối có thể bị chiếm dụng, khiến độ trễ tăng và các luồng khác phải chờ.

Các thao tác thường có nguy cơ blocking:

- JDBC/JPA gọi database đồng bộ.
- HTTP client đồng bộ như một số cách dùng RestTemplate hoặc client cũ.
- Đọc/ghi file bằng API blocking.
- Gọi thư viện legacy dùng socket hoặc chờ phản hồi đồng bộ.
- `Thread.sleep()`, chờ lock lâu hoặc gọi `Future.get()`/`join()` trong pipeline.

Không phải mọi thao tác tốn thời gian đều là blocking. Một phép tính CPU-bound sử dụng CPU liên tục nhưng không chờ I/O; nó cần được lập lịch trên nhóm thread dành cho tính toán, không phải nhóm chuyên cho I/O blocking.

## 2. Nhận diện thread và mô hình thực thi

Trong một ứng dụng Spring Cloud Stream reactive, function có thể nhận và trả về `Flux` hoặc `Mono`. Binder và framework phối hợp subscription để nối luồng message với function. Tùy binder, các thread nhận message, thread điều phối Reactor và thread thực hiện callback có thể khác nhau.

Không nên giả định mọi function đều chạy trên một thread duy nhất hoặc mọi binder đều dùng cùng một thread model. Điều quan trọng là không giữ thread nhạy cảm của event loop hoặc thread điều phối bằng thao tác blocking.

Một cách quan sát đơn giản là ghi tên thread trong operator:

```java
events.doOnNext(event ->
    log.debug("Processing {} on {}",
        event.orderId(),
        Thread.currentThread().getName())
);
```

Tên thread giúp chẩn đoán, nhưng không nên dùng tên thread làm hợp đồng nghiệp vụ. Thread có thể thay đổi theo phiên bản Reactor, binder và cấu hình scheduler.

## 3. Các Scheduler thường dùng của Reactor

Reactor cung cấp một số scheduler phổ biến:

| Scheduler | Đặc điểm | Công việc phù hợp |
|---|---|---|
| `Schedulers.immediate()` | Thực thi ngay trên thread hiện tại | Trường hợp cần thực thi trực tiếp, không chuyển thread |
| `Schedulers.single()` | Một thread dùng chung | Công việc tuần tự, nhẹ, cần một luồng thực thi |
| `Schedulers.parallel()` | Nhóm thread tối ưu cho CPU-bound | Tính toán, biến đổi dữ liệu không blocking |
| `Schedulers.boundedElastic()` | Nhóm thread có giới hạn và hàng đợi cho công việc blocking | JDBC, API đồng bộ, file I/O hoặc thư viện legacy |
| `Schedulers.fromExecutorService(...)` | Bọc ExecutorService do ứng dụng quản lý | Cần kiểm soát executor hoặc tích hợp hạ tầng thread riêng |

### boundedElastic cho I/O blocking

`boundedElastic()` dành cho tác vụ có thể chờ I/O. Nó dùng tài nguyên thread có giới hạn và cơ chế hàng đợi, tránh tạo thread vô hạn khi hệ thống có nhiều tác vụ blocking. Đây thường là lựa chọn mặc định hợp lý để cô lập một lời gọi đồng bộ trong pipeline Reactor.

Tuy vậy, bounded elastic không làm cho API blocking trở thành non-blocking. Thread vẫn bị giữ trong thời gian chờ. Scheduler chỉ cô lập tác động đó khỏi thread điều phối chính và giới hạn tài nguyên sử dụng.

### parallel cho CPU-bound

`parallel()` phù hợp với phép tính cần CPU nhưng không chờ I/O, ví dụ tính điểm, chuẩn hóa dữ liệu hoặc mã hóa thuần CPU. Không dùng `parallel()` cho JDBC hay HTTP blocking; các tác vụ chờ có thể chiếm hết thread dành cho tính toán.

Nếu có một phép tính nặng trong pipeline, có thể chuyển đoạn tính toán sang parallel:

```java
Flux<Score> scores = events
    .publishOn(Schedulers.parallel())
    .map(this::calculateScore);
```

Các operator phía sau `publishOn` chạy trên scheduler đó cho đến khi có lần chuyển scheduler khác. Ví dụ này chuyển đoạn downstream sang một worker của parallel scheduler; nó không tự biến một phép tính thành nhiều phép tính song song. Muốn chạy nhiều tác vụ độc lập đồng thời, cần thiết kế concurrency rõ ràng, ví dụ dùng `flatMap` với giới hạn concurrency.

## 4. Dùng subscribeOn để cô lập lời gọi blocking

Với một hàm blocking trả về kết quả, cách phổ biến là bọc lời gọi bằng `Mono.fromCallable()` rồi gắn `subscribeOn(Schedulers.boundedElastic())`:

```java
Mono<Reservation> reservation =
    Mono.fromCallable(() -> inventoryClient.reserve(event))
        .subscribeOn(Schedulers.boundedElastic());
```

`fromCallable()` trì hoãn việc gọi hàm cho tới khi có subscription. `subscribeOn()` khiến quá trình subscribe và thực thi nguồn upstream bắt đầu trên scheduler đã chọn. Vì lời gọi blocking nằm trong nguồn `fromCallable`, nó chạy trên bounded elastic thay vì thread đang xây dựng pipeline.

Trong Spring Cloud Stream, có thể dùng cách này khi chuyển từng message qua service đồng bộ:

```java
@Bean
Function<Flux<OrderEvent>, Flux<OrderResult>> processOrders(
        LegacyInventoryClient inventoryClient) {

    return events -> events.flatMap(
        event -> Mono.fromCallable(
                () -> inventoryClient.reserve(event))
            .subscribeOn(Schedulers.boundedElastic())
            .map(reservation ->
                OrderResult.from(event, reservation)),
        8
    );
}
```

Tham số `8` là giới hạn số inner publisher được `flatMap` xử lý đồng thời. Nó giúp tránh gửi quá nhiều lời gọi blocking cùng lúc tới dịch vụ hoặc database. Giá trị phù hợp phụ thuộc vào connection pool, năng lực downstream, thời gian đáp ứng và giới hạn tài nguyên của ứng dụng.

Mỗi lời gọi blocking được lên lịch trên bounded elastic. Nếu service có giới hạn concurrency thấp hơn, hãy đặt giới hạn `flatMap` tương ứng thay vì tăng concurrency tùy ý. Không nên coi scheduler là cơ chế điều tiết tải duy nhất.

## 5. Dùng publishOn để chuyển đoạn downstream

`publishOn(scheduler)` chuyển việc thực thi các operator phía sau nó sang scheduler đã chỉ định. Nó không thay đổi cách nguồn upstream được subscribe.

Ví dụ:

```java
Flux<OrderResult> results = events
    .publishOn(Schedulers.boundedElastic())
    .map(event -> {
        Reservation reservation = inventoryClient.reserve(event);
        return OrderResult.from(event, reservation);
    });
```

Sau `publishOn`, operator `map` và các operator downstream tiếp theo chạy trên worker của bounded elastic. Cách này hữu ích khi có một đoạn xử lý đồng bộ liên tiếp cần chạy trên scheduler riêng.

Tuy nhiên, cần chú ý:

- `publishOn` đặt trước `map` sẽ chuyển toàn bộ đoạn downstream, không chỉ một dòng gọi blocking.
- Nếu có nhiều bước downstream không cần blocking, chúng cũng có thể chạy trên bounded elastic cho tới khi chuyển scheduler lần nữa.
- `publishOn` không tự tạo concurrency cho các phần tử; nó thay đổi thread thực thi.
- Nếu cần cô lập từng lời gọi blocking và giới hạn số lời gọi đồng thời, mẫu `flatMap + fromCallable + subscribeOn` thường thể hiện ý định rõ hơn.

Không dùng `publishOn` sau khi thao tác blocking đã chạy xong để “sửa” thao tác đó. Scheduler cần được áp dụng trước điểm blocking.

## 6. Phân biệt subscribeOn và publishOn

Hai operator đều nhận một `Scheduler`, nhưng vị trí tác động khác nhau:

| Tiêu chí | `subscribeOn` | `publishOn` |
|---|---|---|
| Tác động chính | Quá trình subscribe và nguồn upstream | Các operator downstream kể từ vị trí đặt |
| Vị trí thường dùng | Gần nguồn blocking, thường sau `fromCallable` | Trước đoạn downstream cần chuyển thread |
| Dùng để | Đưa việc tạo/đọc nguồn lên scheduler phù hợp | Chuyển việc xử lý tín hiệu phía sau sang scheduler khác |
| Ví dụ | `Mono.fromCallable(this::blockingCall).subscribeOn(boundedElastic)` | `flux.publishOn(parallel).map(this::cpuWork)` |

Ví dụ minh họa:

```java
Mono<Result> result = Mono.fromCallable(this::blockingRead)
    .subscribeOn(Schedulers.boundedElastic())
    .map(this::transform);
```

Nguồn blocking và phần upstream được subscribe trên bounded elastic. Operator `map` cũng nhận tín hiệu từ nguồn đã được thực thi ở scheduler đó nếu không có điểm chuyển khác.

Ví dụ với `publishOn`:

```java
Flux<Result> result = source
    .map(this::lightweightValidation)
    .publishOn(Schedulers.parallel())
    .map(this::cpuIntensiveTransform)
    .publishOn(Schedulers.boundedElastic())
    .map(this::blockingWrite);
```

Validation ban đầu chạy theo thread phát tín hiệu từ source. Phép tính CPU được chuyển sang parallel. Lời gọi ghi blocking được chuyển sang bounded elastic. Trong thực tế, nếu `blockingWrite` trả về kết quả đồng bộ và cần quản lý concurrency, có thể dùng `flatMap` cùng `Mono.fromCallable` thay cho một đoạn `map` tuần tự.

Không cần đặt nhiều `subscribeOn` một cách tùy tiện. Thông thường, một `subscribeOn` gần nguồn xác định nơi subscription/upstream bắt đầu; nhiều lần chuyển scheduler nên được đặt có chủ đích bằng `publishOn` hoặc các publisher con.

## 7. Tích hợp client reactive và client blocking

Không phải mọi lời gọi I/O đều cần bounded elastic.

### Client reactive

Nếu service sử dụng WebClient hoặc R2DBC và các API đang được gọi theo cách reactive, hãy nối trực tiếp publisher vào pipeline:

```java
@Bean
Function<Flux<OrderEvent>, Flux<CustomerProfile>> enrichOrders(
        CustomerClient customerClient) {

    return events -> events.flatMap(
        event -> customerClient.findById(event.customerId())
            .map(profile -> profile),
        16
    );
}
```

Giả sử `findById()` trả về `Mono<CustomerProfile>` và thực hiện I/O non-blocking. Không cần bọc nó trong `fromCallable` hoặc chuyển sang bounded elastic. Có thể giới hạn concurrency của `flatMap` để kiểm soát số request đang hoạt động.

### Client blocking

Nếu thư viện hiện có chỉ cung cấp phương thức đồng bộ, hãy cô lập lời gọi:

```java
Mono<CustomerProfile> profile =
    Mono.fromCallable(() ->
            legacyCustomerClient.findById(customerId))
        .subscribeOn(Schedulers.boundedElastic());
```

Khi có thể, ưu tiên thay client blocking bằng client reactive hoặc API non-blocking phù hợp. Offload sang scheduler là giải pháp tích hợp cho thư viện đồng bộ, không phải lý do để chuyển toàn bộ ứng dụng sang blocking.

## 8. Tạo scheduler riêng và quản lý vòng đời

Scheduler dùng chung `Schedulers.boundedElastic()` thường đủ cho các lời gọi blocking thông thường. Nếu một nhóm tích hợp legacy có đặc tính tải hoặc giới hạn riêng, có thể tạo scheduler riêng để cô lập tài nguyên.

```java
@Configuration
public class SchedulerConfiguration {

    @Bean(destroyMethod = "dispose")
    Scheduler legacyIoScheduler() {
        return Schedulers.newBoundedElastic(
            16,
            1000,
            "legacy-io"
        );
    }
}
```

Tham số minh họa đặt giới hạn số thread và dung lượng hàng đợi cho scheduler này. Hãy chọn các giới hạn theo năng lực downstream, số connection, timeout và tải dự kiến. Hàng đợi quá lớn có thể làm độ trễ tăng và giữ nhiều công việc chờ trong bộ nhớ; giới hạn quá thấp có thể gây từ chối hoặc nghẽn khi tải tăng.

Inject scheduler vào function:

```java
@Bean
Function<Flux<OrderEvent>, Flux<OrderResult>> processOrders(
        LegacyInventoryClient client,
        Scheduler legacyIoScheduler) {

    return events -> events.flatMap(
        event -> Mono.fromCallable(() -> client.reserve(event))
            .subscribeOn(legacyIoScheduler)
            .map(reservation -> OrderResult.from(event, reservation)),
        8
    );
}
```

Scheduler riêng cần được dispose khi ứng dụng dừng. Bean với `destroyMethod = "dispose"` giúp Spring gọi phương thức dispose trong quá trình đóng context. Không tạo scheduler mới cho từng message; làm như vậy tạo thêm thread pool, gây rò rỉ tài nguyên và khó kiểm soát tải.

## 9. Giới hạn concurrency, timeout và backpressure

Chuyển blocking call sang bounded elastic giúp tránh chặn event-loop, nhưng không loại bỏ giới hạn của hệ thống phụ thuộc. Nếu ứng dụng nhận message nhanh hơn tốc độ database hoặc HTTP service xử lý, hàng đợi có thể tăng và độ trễ tiếp tục kéo dài.

Cần phối hợp các giới hạn:

- **Concurrency**: giới hạn số inner publisher đang chạy, ví dụ tham số concurrency của `flatMap`.
- **Connection pool**: không gửi nhiều lời gọi đồng thời hơn số connection hoặc năng lực downstream cho phép.
- **Timeout**: giới hạn thời gian chờ của client để tác vụ không chiếm thread quá lâu.
- **Backpressure**: để subscriber điều tiết tốc độ yêu cầu phần tử khi nguồn hỗ trợ backpressure.
- **Queue capacity**: đặt giới hạn scheduler và các buffer nội bộ.
- **Retry**: tránh retry đồng loạt khi downstream đang quá tải; dùng backoff và giới hạn số lần thử.

Ví dụ giới hạn concurrency:

```java
Flux<OrderResult> results = events.flatMap(
    event -> Mono.fromCallable(() -> legacyClient.process(event))
        .subscribeOn(Schedulers.boundedElastic()),
    10
);
```

Tối đa 10 inner publisher được subscribe đồng thời bởi toán tử này. Nó không bảo đảm chỉ có 10 thread trên toàn ứng dụng nếu còn các pipeline khác hoặc scheduler khác sử dụng cùng pool.

Không nên dùng `parallel()` hoặc tăng số thread để che giấu một downstream chậm. Hãy đo latency, số tác vụ đang chờ, timeout, connection pool saturation và tỷ lệ lỗi.

## 10. Những cách làm cần tránh

### Gọi block() trong pipeline

```java
events.map(event ->
    inventoryClient.reserveReactive(event).block()
);
```

Gọi `block()` chuyển một publisher reactive thành lời gọi đồng bộ. Trong pipeline reactive, điều này có thể chặn thread đang phát tín hiệu và làm mất lợi ích non-blocking. Hãy nối publisher bằng `flatMap`:

```java
events.flatMap(inventoryClient::reserveReactive);
```

### Tự subscribe bên trong function

```java
@Bean
Consumer<Flux<OrderEvent>> process() {
    return events -> events.subscribe(this::handle);
}
```

Không tự gọi `subscribe()` để tạo một luồng xử lý tách rời bên trong function. Framework cần publisher mà function trả về để phối hợp vòng đời, lỗi và tín hiệu hoàn tất. Hãy trả về publisher:

```java
@Bean
Function<Flux<OrderEvent>, Flux<OrderResult>> process() {
    return events -> events.map(this::handle);
}
```

Nếu function cần gọi blocking service, bọc lời gọi trong `Mono.fromCallable()` và gắn scheduler như các ví dụ trước.

### Dùng parallel cho blocking I/O

`Schedulers.parallel()` được thiết kế cho công việc CPU-bound. Gọi JDBC hoặc HTTP blocking trên scheduler này có thể chiếm các worker dành cho tính toán và làm chậm pipeline khác. Chuyển blocking call sang bounded elastic hoặc scheduler blocking chuyên biệt.

### Chuyển toàn bộ pipeline sang boundedElastic

Không cần đưa mọi operator sang bounded elastic. Các phép biến đổi nhẹ và client reactive có thể tiếp tục chạy theo scheduler hiện tại. Chỉ chuyển đúng đoạn có thao tác blocking hoặc đoạn cần cô lập thread.

## 11. Lỗi và cancellation khi chuyển scheduler

Khi publisher con thất bại, lỗi được truyền theo tín hiệu reactive tới downstream nếu không bị xử lý hoặc chuyển thành giá trị khác. Với function reactive của Spring Cloud Stream, hãy để lỗi được biểu diễn trong publisher để framework/binder áp dụng cơ chế xử lý lỗi đã cấu hình. Không nuốt exception trong lambda rồi trả về kết quả giả.

Cancellation có thể xảy ra khi downstream hủy subscription, timeout hoặc ứng dụng dừng. Reactor có thể hủy tác vụ theo khả năng của scheduler và nguồn. Tuy nhiên, một lời gọi blocking đang chạy trong thư viện không hỗ trợ interruption/cancellation có thể tiếp tục cho tới khi thư viện trả về hoặc timeout. Vì vậy:

- Cấu hình connect/read/request timeout trong client blocking.
- Tránh gọi thư viện có thời gian chờ vô hạn.
- Đặt timeout ở tầng phù hợp và hiểu rằng timeout reactive không nhất thiết dừng được I/O đang chạy.
- Đảm bảo thao tác có thể được retry là idempotent nếu kết quả trước đó không xác định.
- Theo dõi các tác vụ đang chạy khi ứng dụng shutdown.

Scheduler chỉ quyết định nơi thực thi; nó không tự bảo đảm một lời gọi blocking sẽ bị dừng ngay khi subscription bị cancel.

## 12. Kiểm thử việc tách blocking call

Nên kiểm thử cả kết quả nghiệp vụ và cách pipeline xử lý lỗi. Ví dụ với `StepVerifier`:

```java
@Test
void processesBlockingCallOnBoundedElastic() {
    LegacyInventoryClient client = event -> {
        if (event.orderId().isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }
        return new Reservation(event.orderId(), true);
    };

    Function<Flux<OrderEvent>, Flux<OrderResult>> function =
        events -> events.flatMap(
            event -> Mono.fromCallable(() -> client.reserve(event))
                .subscribeOn(Schedulers.boundedElastic())
                .map(reservation -> OrderResult.from(event, reservation)),
            4
        );

    StepVerifier.create(
            function.apply(Flux.just(new OrderEvent("order-1001")))
        )
        .expectNextMatches(result ->
            result.orderId().equals("order-1001") && result.reserved())
        .verifyComplete();
}
```

Test này xác minh kết quả của function với một client đồng bộ. Để kiểm tra thread isolation, có thể ghi lại tên thread trong stub và xác minh lời gọi chạy trên scheduler được chọn; tránh phụ thuộc vào một tên thread cụ thể nếu phiên bản Reactor hoặc cấu hình pool có thể thay đổi.

Các lớp kiểm thử nên gồm:

1. Unit test cho phép biến đổi và xử lý lỗi.
2. Test xác minh blocking stub được thực thi ngoài thread điều phối ban đầu.
3. Test giới hạn concurrency và timeout khi downstream chậm.
4. Integration test với binder để xác minh function reactive được kết nối đúng.
5. Kiểm thử tải để đánh giá queue, latency, connection pool và hành vi khi downstream quá tải.

BlockHound là công cụ tùy chọn có thể phát hiện một số lời gọi blocking trên thread được đánh dấu non-blocking trong môi trường kiểm thử. Nó hữu ích để tìm lỗi vô tình gọi blocking API, nhưng không thay thế integration test hoặc đo tải thực tế.

## 13. Checklist chọn Scheduler

- Xác định thao tác là I/O blocking, I/O reactive hay CPU-bound.
- Giữ WebClient/R2DBC và publisher non-blocking trong chuỗi reactive; không offload chúng nếu không có lý do.
- Bọc lời gọi đồng bộ bằng `Mono.fromCallable()` hoặc `Flux.defer()`.
- Dùng `subscribeOn(boundedElastic)` cho nguồn blocking; dùng `publishOn` khi cần chuyển đoạn downstream.
- Dùng `parallel()` cho phép tính CPU-bound, không dùng cho JDBC hoặc HTTP blocking.
- Giới hạn concurrency, timeout, connection pool và hàng đợi.
- Không gọi `block()` hoặc tự `subscribe()` trong function reactive.
- Quản lý vòng đời scheduler riêng và dispose khi ứng dụng dừng.
- Giữ lỗi trong publisher để binder/framework có thể xử lý theo chính sách đã cấu hình.
- Kiểm thử thread isolation, cancellation, lỗi và tải với môi trường phù hợp.

## 14. Tài liệu tham khảo

- [Project Reactor Reference — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html), phần `subscribeOn`, `publishOn` và các scheduler chuẩn.
- [Project Reactor API — Schedulers](https://projectreactor.io/docs/core/release/api/reactor/core/scheduler/Schedulers.html), phần `boundedElastic`, `parallel` và tạo scheduler riêng.
- [Spring Cloud Stream Reference — Programming Model](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/programming-model.html), phần function reactive và tích hợp message.

Trong Spring Cloud Stream, reactive function giúp xử lý message theo luồng và phối hợp các thao tác bất đồng bộ. Để giữ khả năng đáp ứng, cần tách thư viện blocking khỏi thread điều phối bằng bounded elastic hoặc scheduler riêng; phép tính CPU nên dùng parallel. Chọn đúng `subscribeOn` và `publishOn`, giới hạn concurrency và kiểm soát timeout sẽ giúp pipeline không chặn luồng xử lý message khi tích hợp với các hệ thống đồng bộ.

