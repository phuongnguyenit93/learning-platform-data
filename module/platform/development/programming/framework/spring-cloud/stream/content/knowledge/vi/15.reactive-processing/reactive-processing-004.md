# `Consumer<Flux<T>>` và phương án `Function<Flux<T>, Mono<Void>>`

## Mục tiêu

Spring Cloud Stream hỗ trợ mô hình hàm phản ứng dựa trên Project Reactor. Thay vì nhận từng đối tượng một cách độc lập, một hàm có thể nhận cả luồng `Flux<T>` gồm nhiều message. Với một consumer chỉ thực hiện side effect, có hai cách khai báo thường được cân nhắc:

- `Consumer<Flux<T>>`: hàm nhận Flux nhưng có kiểu trả về `void`.
- `Function<Flux<T>, Mono<Void>>`: hàm nhận Flux và trả về một publisher biểu diễn thời điểm hoàn tất xử lý, không phát payload đầu ra.

Khác biệt về kiểu trả về ảnh hưởng đến cách quản lý subscription, lỗi và vòng đời xử lý. Bài học này giải thích khi nào mỗi cách phù hợp, cách điều khiển tuần tự hoặc song song, cách tránh blocking và cách kiểm thử reactive pipeline trong ứng dụng Spring Cloud Stream.

Sau bài học, bạn có thể:

- Phân biệt một consumer nhận từng message với consumer nhận cả `Flux<T>`.
- Giải thích vì sao `Consumer<Flux<T>>` cần tự quản lý subscription.
- Dùng `Function<Flux<T>, Mono<Void>>` để biểu diễn quá trình xử lý hoàn tất.
- Chọn `concatMap`, `flatMap` hoặc các toán tử phù hợp với yêu cầu thứ tự và concurrency.
- Xử lý lỗi và backpressure mà không chặn luồng reactive.
- Kiểm thử pipeline và xác minh semantics với binder/broker đang triển khai.

## 1. Flux là luồng dữ liệu, không phải collection

`Flux<T>` là một Publisher của Reactor có thể phát từ không đến nhiều phần tử theo thời gian. Nó không tương đương `List<T>`:

- `List<T>` chứa sẵn các phần tử trong bộ nhớ.
- `Flux<T>` mô tả một quá trình phát dữ liệu có thể diễn ra bất đồng bộ.
- Subscriber yêu cầu dữ liệu theo cơ chế demand; publisher có thể phát dần theo tốc độ tiêu thụ và khả năng hỗ trợ backpressure.
- Một Flux có thể hoàn tất, phát lỗi hoặc không kết thúc.

Ví dụ một function nhận từng message:

```java
public record OrderCreated(String eventId, String orderId) {}

@Bean
Consumer<OrderCreated> orderCreated(OrderService service) {
    return event -> service.handle(event);
}
```

Đây là kiểu imperative: mỗi lần function được gọi, nó nhận một `OrderCreated`. Với reactive consumer, tham số là cả luồng:

```java
@Bean
Consumer<Flux<OrderCreated>> orderStream(OrderService service) {
    return events -> events
            .doOnNext(event -> service.recordReceived(event.eventId()))
            .subscribe();
}
```

Chữ ký `Consumer<Flux<OrderCreated>>` có nghĩa hàm nhận một Flux, không có nghĩa nó tự động trả về một publisher cho framework theo dõi. Đây là khác biệt quan trọng khi cần gắn thời điểm hoàn tất xử lý với vòng đời message.

## 2. Consumer<Flux<T>>: consumer tự subscribe

`Consumer` là functional interface có phương thức trả về `void`. Khi dùng `Consumer<Flux<T>>`, code nhận Flux và phải tạo subscription để pipeline bắt đầu chạy. Nếu chỉ xây dựng chuỗi toán tử mà không subscribe, các thao tác sẽ không được thực thi.

Ví dụ có side effect bất đồng bộ:

```java
@Bean
Consumer<Flux<OrderCreated>> orderConsumer(OrderService service) {
    return events -> events
            .concatMap(event -> service.handle(event))
            .doOnError(error ->
                    log.error("Order stream failed", error))
            .subscribe();
}
```

Giả sử `service.handle(event)` trả về `Mono<Void>`. `concatMap` gọi xử lý cho từng sự kiện và chờ publisher của sự kiện trước hoàn tất rồi mới chuyển sang sự kiện tiếp theo.

### Hệ quả của subscription thủ công

Vì `subscribe()` được gọi bên trong Consumer:

- Code ứng dụng quyết định thời điểm subscribe.
- Lời gọi Consumer có thể kết thúc ngay sau khi tạo subscription, trong khi pipeline còn chạy.
- Lỗi xảy ra sau khi subscribe không tự động trở thành exception đồng bộ của lời gọi Consumer.
- Ứng dụng cần cân nhắc cách theo dõi và quản lý subscription, lỗi và shutdown.
- Không nên tạo nhiều subscription độc lập cho cùng một Flux đầu vào nếu điều đó khiến mỗi message bị xử lý lặp.

Một lỗi thường gặp là bỏ quên `subscribe()`:

```java
@Bean
Consumer<Flux<OrderCreated>> brokenConsumer(OrderService service) {
    return events -> events
            .concatMap(service::handle);
            // Chưa subscribe: pipeline chưa được tiêu thụ.
}
```

Một lỗi khác là subscribe nhiều lần vào cùng nguồn hoặc tạo thêm subscription trong mỗi nhánh xử lý. Tùy nguồn Flux và binder, điều này có thể gây side effect trùng, cạnh tranh tài nguyên hoặc hành vi không dự kiến.

### Quản lý lỗi trong Consumer

Có thể đặt error callback trong subscription:

```java
@Bean
Consumer<Flux<OrderCreated>> orderConsumer(OrderService service) {
    return events -> events
            .concatMap(service::handle)
            .subscribe(
                    ignored -> { },
                    error -> log.error("Order processing failed", error)
            );
}
```

Với `Mono<Void>`, pipeline không phát giá trị `onNext`, nên callback giá trị thường không được gọi; callback lỗi nhận tín hiệu lỗi của subscription. Ví dụ chỉ ghi log để minh họa nơi lỗi xuất hiện. Trong ứng dụng thật, ghi log không tự tạo retry, không đưa message vào DLQ và không đảm bảo broker biết xử lý thất bại. Cần có chính sách lỗi rõ ràng và xác minh ack/nack hoặc offset commit của binder.

Do Consumer trả về `void`, framework không nhận được publisher biểu diễn thời điểm hoàn tất pipeline do ứng dụng subscribe. Vì vậy, nếu yêu cầu là để framework quan sát completion/error của reactive work, một function trả về publisher thường dễ thể hiện ý định hơn.

## 3. Function<Flux<T>, Mono<Void>>: trả về tín hiệu hoàn tất

`Function<Flux<T>, Mono<Void>>` nhận luồng đầu vào và trả về một `Mono<Void>`. Mono này không phát payload kết quả; nó chỉ biểu diễn quá trình xử lý đã hoàn tất hoặc thất bại.

Ví dụ:

```java
@Bean
Function<Flux<OrderCreated>, Mono<Void>> processOrders(
        OrderService service) {
    return events -> events
            .concatMap(event -> service.handle(event))
            .then();
}
```

Ở đây:

1. Framework cung cấp Flux đầu vào cho function.
2. Function xây dựng pipeline xử lý từng sự kiện.
3. `concatMap` gọi `service.handle` theo thứ tự tuần tự.
4. `then()` chuyển kết quả thành `Mono<Void>`, chỉ phát tín hiệu hoàn tất khi upstream hoàn tất.
5. Function trả publisher cho framework quản lý subscription theo mô hình reactive.

Khác với Consumer, function không gọi `subscribe()` thủ công. Framework có thể theo dõi publisher được trả về để quản lý việc thực thi và tín hiệu completion/error theo integration của phiên bản đang dùng.

`Mono<Void>` không có nghĩa là một message rỗng được gửi đến output destination. Nó biểu diễn hoàn tất mà không phát phần tử dữ liệu. Khi dùng chữ ký này như một endpoint chỉ nhận dữ liệu, hãy xác minh cách phiên bản Spring Cloud Stream đang dùng diễn giải output type `Void` và cấu hình binding tương ứng; không khai báo output destination chỉ vì tên interface là `Function`.

### Tại sao dùng then()?

Chuỗi `concatMap` tạo một Flux từ các publisher xử lý. `then()` bỏ qua các giá trị đầu ra và chỉ giữ tín hiệu hoàn tất:

```java
Mono<Void> completion = events
        .concatMap(service::handle)
        .then();
```

Nếu một lần `service.handle` phát lỗi, lỗi đó truyền qua pipeline và Mono kết thúc bằng tín hiệu error thay vì complete. Điều này giúp lỗi không bị biến thành thành công chỉ vì một subscription thủ công đã được tạo.

Nếu cần phát một kết quả nghiệp vụ, chữ ký nên trả kiểu có dữ liệu, ví dụ `Function<Flux<OrderCreated>, Flux<OrderAccepted>>` hoặc kiểu publisher phù hợp khác, thay vì `Mono<Void>`.

## 4. So sánh hai chữ ký

| Tiêu chí | `Consumer<Flux<T>>` | `Function<Flux<T>, Mono<Void>>` |
|---|---|---|
| Kiểu trả về | `void` | Publisher biểu diễn completion |
| Subscription | Code consumer thường phải gọi `subscribe()` | Trả publisher để framework quản lý theo reactive model |
| Theo dõi completion | Consumer không trả completion về caller | Completion nằm trong `Mono<Void>` |
| Truyền tín hiệu lỗi | Lỗi sau subscribe thuộc subscription do ứng dụng quản lý | Error signal nằm trong publisher trả về |
| Quản lý vòng đời | Ứng dụng phải chú ý subscription và shutdown | Framework có thể quản lý subscription theo lifecycle function |
| Phù hợp | Consumer reactive tự quản lý subscription hoặc tích hợp đặc biệt | Luồng chỉ nhận, cần biểu diễn hoàn tất xử lý bằng publisher |
| Rủi ro | Quên subscribe, lỗi bị tách khỏi lời gọi, subscription trùng | Cần xác minh function/binder hỗ trợ chữ ký và semantics output Void |

Đối với xử lý message cần gắn completion/error với pipeline của framework, `Function<Flux<T>, Mono<Void>>` thường diễn đạt ý định rõ hơn. Tuy nhiên, không thể suy ra semantics acknowledgment chỉ từ chữ ký Java; binder và phiên bản cụ thể vẫn quyết định cách tín hiệu reactive liên kết với message delivery.

## 5. Chọn tuần tự hay song song

Sau khi chọn chữ ký, cần quyết định cách xử lý các phần tử trong Flux.

### concatMap: tuần tự

`concatMap` chỉ bắt đầu publisher tiếp theo sau khi publisher hiện tại hoàn tất. Đây là lựa chọn phù hợp khi:

- Các sự kiện cần được áp dụng theo thứ tự nhận.
- Cùng một aggregate có các thay đổi phụ thuộc nhau.
- Muốn giới hạn số thao tác đồng thời ở mức một.
- Muốn hành vi dễ dự đoán khi debug.

```java
@Bean
Function<Flux<OrderEvent>, Mono<Void>> processInOrder(
        OrderService service) {
    return events -> events
            .concatMap(service::apply)
            .then();
}
```

Tuần tự trên toàn Flux có thể giới hạn throughput. Nếu chỉ cần thứ tự theo từng order ID, có thể thiết kế xử lý theo key và partition để các key khác nhau được xử lý song song, trong khi cùng key vẫn tuân theo thứ tự thích hợp.

### flatMap: song song có giới hạn

`flatMap` cho phép nhiều publisher con chạy đồng thời. Nó có thể tăng throughput khi các sự kiện độc lập, nhưng thứ tự hoàn tất có thể khác thứ tự đầu vào.

```java
@Bean
Function<Flux<OrderCreated>, Mono<Void>> processConcurrently(
        OrderService service) {
    return events -> events
            .flatMap(service::handle, 8)
            .then();
}
```

Tham số `8` giới hạn số publisher con được subscribe đồng thời trong ví dụ. Chọn concurrency dựa trên năng lực database/API và giới hạn downstream; tăng số này không tự động làm broker nhanh hơn.

### flatMapSequential

`flatMapSequential` có thể subscribe và thực hiện publisher con đồng thời nhưng phát kết quả theo thứ tự nguồn. Nó có thể phải giữ kết quả hoàn tất sớm trong bộ đệm nếu publisher trước còn chậm. Nếu các publisher con có side effect bên ngoài, thứ tự phát kết quả không có nghĩa side effect đã xảy ra theo thứ tự đó.

Vì vậy, nếu thứ tự side effect là yêu cầu nghiệp vụ, `concatMap` hoặc partitioning theo khóa thường dễ lý giải hơn.

## 6. Backpressure và giới hạn tài nguyên

Backpressure là cơ chế consumer báo lượng dữ liệu nó sẵn sàng nhận. Trong Reactor, subscriber có thể yêu cầu một số phần tử thông qua demand; các operator cũng có thể tạo buffer hoặc điều chỉnh prefetch.

Một pipeline reactive tốt cần:

- Tránh đọc toàn bộ luồng vào `List` nếu dữ liệu có thể lớn hoặc không kết thúc.
- Giới hạn concurrency khi gọi database hoặc API.
- Tránh tạo buffer không giới hạn.
- Không gọi `block()` trong reactive chain.
- Dùng các operator phù hợp với khả năng điều tiết của nguồn.
- Đo queue depth, latency, throughput và số subscription đang hoạt động.

Ví dụ giới hạn số thao tác đồng thời:

```java
@Bean
Function<Flux<PaymentCaptured>, Mono<Void>> recordPayments(
        PaymentService service) {
    return events -> events
            .flatMap(service::record, 4)
            .then();
}
```

Backpressure của Reactor không có nghĩa mọi broker đều dừng phát message đúng theo demand của downstream. Binder có thể phải chuyển demand thành prefetch, poll, pause/resume hoặc cơ chế khác. Khả năng điều tiết và giới hạn buffer khác nhau giữa Kafka, RabbitMQ và Pulsar binder; hãy kiểm tra tài liệu và quan sát runtime.

## 7. Không chặn luồng reactive

Không dùng các thao tác blocking trong pipeline như:

- `block()` hoặc `blockFirst()`.
- `Thread.sleep()`.
- Truy vấn JDBC đồng bộ trên event loop.
- Gọi HTTP đồng bộ hoặc chờ Future bằng `get()`.
- Chuyển Flux thành collection lớn rồi xử lý đồng bộ.

Nếu service sử dụng reactive database hoặc WebClient, hãy trả trực tiếp `Mono`/`Flux` để pipeline kết hợp được:

```java
public Mono<Void> handle(OrderCreated event) {
    return inventoryRepository.reserve(
                    event.orderId(),
                    event.lines()
            )
            .then(outboxRepository.append(
                    StockReserved.from(event)
            ));
}
```

Nếu phải tích hợp thư viện blocking, cô lập thao tác đó trên scheduler phù hợp thay vì chạy trên event loop:

```java
Mono<Void> handleLegacy(OrderCreated event) {
    return Mono.fromRunnable(() -> legacyService.reserve(event))
            .subscribeOn(Schedulers.boundedElastic())
            .then();
}
```

Không chuyển mọi thao tác sang `boundedElastic` một cách mặc định. Chỉ dùng cho công việc blocking thực sự và kiểm soát concurrency để không làm cạn scheduler.

## 8. Error handling trong reactive pipeline

Reactor biểu diễn lỗi bằng terminal signal. Khi một publisher phát error, pipeline thông thường kết thúc nếu không có operator xử lý lỗi. Có thể phân loại lỗi tạm thời và lỗi không thể khắc phục:

```java
@Bean
Function<Flux<OrderCreated>, Mono<Void>> processOrders(
        OrderService service) {
    return events -> events
            .concatMap(event ->
                    service.handle(event)
                            .retryWhen(
                                    Retry.backoff(2, Duration.ofMillis(200))
                                            .filter(this::isTransient)
                            )
            )
            .then();
}
```

Ví dụ retry tối đa hai lần bổ sung cho mỗi lần xử lý event nếu lỗi thỏa điều kiện `isTransient`. Retry trong Reactor khác với redelivery của broker. Nếu pipeline vẫn lỗi sau retry, error signal có thể được chuyển đến error handling của Spring Cloud Stream/binder tùy cấu hình; binder có thể ack/nack, commit offset, redeliver hoặc gửi DLQ theo semantics riêng.

Không dùng `onErrorResume(error -> Mono.empty())` để biến mọi lỗi thành hoàn tất. Cách đó có thể khiến framework thấy pipeline thành công trong khi nghiệp vụ chưa xử lý xong. Chỉ phục hồi lỗi khi đã có kết quả nghiệp vụ rõ ràng, ví dụ ghi nhận một trạng thái từ chối hợp lệ hoặc chuyển event vào một kho lỗi có thể truy vết.

Nếu xử lý một Flux lớn bằng `concatMap`, lỗi ở một event có thể kết thúc cả pipeline. Nếu cần cô lập lỗi từng event, có thể đặt recovery bên trong publisher con, nhưng phải phân biệt rõ lỗi đã được xử lý thành công theo nghiệp vụ với lỗi cần broker retry/DLQ. Không nuốt lỗi chỉ để các message tiếp theo tiếp tục chạy.

## 9. Acknowledgment và delivery semantics

Reactive completion không đồng nghĩa tự động với exactly-once. Có ba tầng cần phân biệt:

1. **Reactor completion:** publisher đã complete hoặc error.
2. **Framework processing:** Spring Cloud Stream quan sát tín hiệu của function và áp dụng cơ chế xử lý lỗi tương ứng.
3. **Broker delivery state:** binder xác nhận, commit offset, nack, redelivery hoặc cập nhật subscription theo cơ chế broker.

Với `Consumer<Flux<T>>` tự subscribe, function trả về `void` trước khi pipeline con nhất thiết hoàn tất. Vì vậy, không nên giả định framework có thể chờ mọi side effect trong subscription đó để xác nhận message. Cần đặc biệt kiểm tra ack/error semantics khi dùng chữ ký này.

Với `Function<Flux<T>, Mono<Void>>`, completion/error được biểu diễn trong publisher trả về nên framework có cơ hội quản lý pipeline theo reactive integration. Tuy nhiên, thời điểm commit/ack cụ thể còn phụ thuộc binder, batch/polling behavior, transaction và phiên bản. Hãy xác minh bằng integration test tạo lỗi ở các điểm khác nhau.

Dù dùng chữ ký nào, consumer nên idempotent. Một event có thể được giao lại sau restart, timeout hoặc commit thất bại. Dùng event ID ổn định, inbox/unique constraint hoặc idempotency key để tránh nhân đôi tác động nghiệp vụ.

## 10. Ví dụ hoàn chỉnh cho hai phương án

Giả sử service trả `Mono<Void>` khi đã ghi nhận sự kiện:

```java
public interface OrderService {
    Mono<Void> handle(OrderCreated event);
}
```

### Phương án A: Consumer<Flux<T>>

```java
@Bean
Consumer<Flux<OrderCreated>> consumeOrders(OrderService service) {
    return events -> events
            .concatMap(service::handle)
            .doOnError(error ->
                    log.error("Reactive consumer failed", error))
            .subscribe();
}
```

Đặc điểm:

- Consumer tự subscribe.
- Pipeline có thể chạy sau khi method Consumer trả về.
- Cần quyết định nơi quản lý lỗi và vòng đời subscription.
- Không thể dựa vào giá trị trả về của Consumer để báo completion.

### Phương án B: Function<Flux<T>, Mono<Void>>

```java
@Bean
Function<Flux<OrderCreated>, Mono<Void>> processOrders(
        OrderService service) {
    return events -> events
            .concatMap(service::handle)
            .then();
}
```

Đặc điểm:

- Function trả publisher hoàn tất.
- Không subscribe thủ công.
- Completion/error nằm trong reactive chain mà framework quản lý.
- `Mono<Void>` không phát message đầu ra; xác minh cách function catalog/binder của phiên bản đang dùng xử lý kiểu output Void.

Hai bean là hai phương án thay thế cho cùng một input flow. Không khai báo đồng thời cả hai cùng tiêu thụ một destination nếu không có chủ đích tạo hai logical consumer độc lập.

## 11. Cấu hình binding và function definition

Ví dụ cấu hình cho function tên `processOrders`:

```yaml
spring:
  cloud:
    function:
      definition: processOrders
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.created
          group: inventory-service
          content-type: application/json
```

Tên input binding được suy ra từ function name và vị trí input. Nếu function có output dữ liệu, khai báo binding output tương ứng. Với `Function<Flux<T>, Mono<Void>>`, không có payload output để gửi; kiểm tra behavior của framework version và không cấu hình destination đầu ra giả chỉ để thỏa quy ước đặt tên.

Reactive support và cách binder liên kết demand/acknowledgment có thể khác giữa các binder và phiên bản Spring Cloud Stream. Đừng giả định một pipeline chạy với Test Binder có nghĩa mọi binder production có cùng backpressure hoặc redelivery behavior.

## 12. Kiểm thử reactive function

Unit test cho function trả `Mono<Void>` có thể dùng Reactor Test và `StepVerifier`:

```java
@Test
void shouldCompleteAfterAllOrdersAreHandled() {
    OrderService service = event -> Mono.empty();

    Function<Flux<OrderCreated>, Mono<Void>> function =
            events -> events.concatMap(service::handle).then();

    StepVerifier.create(function.apply(Flux.just(
                    new OrderCreated("evt-1", "order-1"),
                    new OrderCreated("evt-2", "order-2")
            )))
            .verifyComplete();
}
```

Test trên xác minh publisher hoàn tất sau khi các publisher con hoàn tất. Nên bổ sung test xác minh:

- Event được xử lý theo thứ tự với `concatMap`.
- `flatMap` không vượt quá concurrency đã cấu hình.
- Lỗi từ service được truyền thành error signal.
- Retry chỉ áp dụng cho lỗi tạm thời.
- Lỗi không được chuyển thành complete ngoài ý muốn.
- Flux rỗng hoàn tất bình thường nếu đó là semantics mong đợi.
- Cancel/dispose dừng công việc tiếp tục theo khả năng của publisher.

Với `Consumer<Flux<T>>`, unit test cần xác minh subscription thực sự chạy và xử lý bất đồng bộ hoàn tất. Có thể dùng `Sinks.One`, `CountDownLatch` trong test hoặc test double có tín hiệu completion; tránh dùng sleep tùy tiện vì dễ tạo test không ổn định. Consumer tự subscribe cũng cần test error callback và cách dừng subscription.

### Integration test với binder

Dùng Test Binder hoặc broker test để xác minh:

- Binding input được tạo và function được kích hoạt.
- Payload được chuyển đổi đúng kiểu.
- Reactive pipeline nhận message theo đúng semantics.
- Lỗi được xử lý theo cấu hình retry/error/DLQ.
- Acknowledgment/offset chỉ tiến theo cách dự kiến khi pipeline hoàn tất hoặc lỗi.
- Backpressure, prefetch hoặc poll behavior phù hợp với binder thực tế.

Test Binder không mô phỏng đầy đủ Kafka poll/commit, RabbitMQ prefetch/ack hoặc Pulsar subscription acknowledgment. Với cam kết giao nhận production, cần integration test trên binder/broker tương ứng.

## 13. Chọn phương án nào?

Dùng `Consumer<Flux<T>>` khi có lý do rõ ràng để consumer tự sở hữu subscription, ví dụ tích hợp với một nguồn reactive đặc thù hoặc quản lý lifecycle riêng đã được thiết kế. Khi đó phải có chiến lược rõ về error, disposal, shutdown và delivery semantics.

Dùng `Function<Flux<T>, Mono<Void>>` khi muốn biểu diễn một luồng chỉ nhận, thực hiện side effect và trả tín hiệu hoàn tất cho framework. Đây thường là cách dễ đọc hơn cho xử lý reactive cần completion/error được giữ trong publisher. Hãy xác minh chữ ký này được hỗ trợ đúng cách trong phiên bản Spring Cloud Function/Spring Cloud Stream và binder đang sử dụng.

Nếu không cần reactive stream và chỉ xử lý từng message độc lập, `Consumer<T>` imperative có thể đơn giản hơn. Không chuyển sang Flux chỉ vì muốn code trông bất đồng bộ; reactive model có ý nghĩa khi toàn bộ đường xử lý hỗ trợ non-blocking, backpressure và composition.

## Kết luận

`Consumer<Flux<T>>` nhận một luồng nhưng trả về `void`, vì vậy code thường phải subscribe và tự quản lý subscription. `Function<Flux<T>, Mono<Void>>` trả publisher biểu diễn thời điểm hoàn tất mà không phát payload đầu ra, cho phép framework quản lý reactive pipeline theo integration của nó.

Chọn toán tử dựa trên yêu cầu thứ tự và concurrency: `concatMap` cho xử lý tuần tự, `flatMap` cho xử lý song song có giới hạn. Tránh blocking, kiểm soát backpressure và không nuốt lỗi. Reactor completion, framework processing và broker acknowledgment là các tầng khác nhau; hãy kiểm chứng semantics của binder và luôn thiết kế consumer idempotent để chịu được redelivery.

