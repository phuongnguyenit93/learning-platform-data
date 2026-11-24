# Đăng ký nhận

## Đăng ký bên trong toán tử và nguyên nhân tạo luồng tách rời

Trong mô-đun **REACTIVE_PROGRAMMING**, ta xây dựng ứng dụng quanh các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams. Với Java Reactor, `Mono` và `Flux` cho phép mô tả các bước xử lý bằng toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline. Một quy tắc quan trọng để giữ pipeline có thể dự đoán là: **đừng tự ý gọi `subscribe()` bên trong một toán tử khi công việc đó thuộc cùng quy trình nghiệp vụ**.

Lời gọi `subscribe()` bắt đầu một phiên xử lý độc lập. Nếu đặt nó bên trong `map`, `doOnNext` hoặc callback của một toán tử khác, ta thường tạo ra một luồng con tách khỏi luồng bên ngoài. Luồng ngoài có thể hoàn tất trong khi luồng con vẫn đang chạy; lỗi và cancellation của luồng con cũng không tự động truyền về luồng ngoài. Hiểu cơ chế này giúp tránh lỗi mất thông tin, tác dụng phụ chạy trùng, quá tải và các bài toán khó kiểm thử.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao `subscribe()` bên trong toán tử tạo ra một subscription độc lập.
- Phân biệt callback quan sát với tác vụ bất đồng bộ cần được ghép vào pipeline.
- Chọn `flatMap`, `concatMap`, `flatMapSequential`, `then` hoặc `when` để kết hợp Publisher con.
- Nhận diện các vấn đề về lỗi, backpressure, thứ tự, cancellation và vòng đời do nested subscription gây ra.
- Xác định vị trí phù hợp để subscribe ở ranh giới của ứng dụng.
- Biết cách quản lý một tác vụ nền tách rời khi nghiệp vụ thực sự yêu cầu.

## 1. Subscription là điểm bắt đầu thực thi

Một Publisher mô tả nguồn tín hiệu và cách phát dữ liệu. Khi có Subscriber đăng ký, Publisher thiết lập một Subscription; Subscriber sau đó có thể yêu cầu dữ liệu bằng `request(n)` hoặc hủy bằng `cancel()`.

Trong Reactor, các toán tử như `map`, `filter`, `flatMap` tạo ra Publisher mới. Chúng thường chỉ mô tả cách tín hiệu sẽ được biến đổi hoặc kết hợp. Việc thực thi bắt đầu khi một Subscriber subscribe vào chuỗi.

~~~java
Mono<Order> order = orderRepository.findById(orderId)
    .filter(Order::isValid)
    .map(this::enrich);
~~~

Đoạn mã trên lắp ráp một pipeline. Chưa có Subscriber nào được tạo bởi chính đoạn mã đó. Khi caller subscribe hoặc framework reactive subscribe thay caller, các bước trong chuỗi mới được thực thi theo demand.

`subscribe()` là một thao tác kết thúc (terminal operation) ở API sử dụng thông thường: nó đăng ký Subscriber và bắt đầu tiêu thụ Publisher. Ví dụ:

~~~java
orderRepository.findById(orderId)
    .subscribe(order -> log.info("Order: {}", order.id()));
~~~

Lời gọi này tạo một subscription. Trong Reactor, các overload tiện lợi của `subscribe` thường yêu cầu dữ liệu không giới hạn (`Long.MAX_VALUE`) và trả về một `Disposable` để có thể hủy subscription. Nếu không giữ `Disposable`, mã gọi thường không còn handle trực tiếp để điều khiển vòng đời của phiên đó.

Vì vậy, vị trí gọi `subscribe()` có ý nghĩa kiến trúc. Một subscription ở biên ứng dụng có thể là điểm bắt đầu hợp lý. Một subscription được tạo lặp lại bên trong callback của từng phần tử thường là dấu hiệu một phần workflow đang bị tách khỏi pipeline chính.

## 2. Nested subscription tạo ra luồng tách rời

Xét một pipeline xử lý đơn hàng. Với mỗi đơn, ứng dụng cần gọi dịch vụ tồn kho để đặt chỗ:

~~~java
Flux<Order> orders = orderRepository.findPending();

orders.doOnNext(order ->
    inventory.reserve(order).subscribe()
);
~~~

Giả sử `inventory.reserve(order)` trả về `Mono<Void>`. Khi `doOnNext` nhận một đơn hàng, callback gọi `subscribe()` trên Publisher con. Lời gọi này tạo một subscription khác và bắt đầu tác vụ đặt chỗ. Pipeline `orders` không nhận Publisher con như một phần kết quả của nó.

~~~mermaid
flowchart TD
    A[Publisher orders] --> B[doOnNext callback]
    B --> C[subscribe vào inventory.reserve]
    C --> D[Subscription con độc lập]
    D --> E[Đặt chỗ tồn kho]
    A --> F[Pipeline ngoài tiếp tục]
    F --> G[Hoàn tất luồng orders]
~~~

Hai nhánh trong sơ đồ có vòng đời riêng. Pipeline ngoài chỉ biết callback đã gọi `subscribe()`; nó không biết Publisher con hoàn tất lúc nào, có lỗi hay bị hủy ra sao.

Điều này gây ra một số hệ quả:

- **Không chờ công việc con:** `doOnNext` trả về ngay sau khi gọi `subscribe()`. Luồng ngoài có thể phát đơn tiếp theo hoặc hoàn tất trước khi thao tác tồn kho xong.
- **Lỗi bị tách khỏi luồng ngoài:** lỗi của `inventory.reserve` phát trong subscription con. Nó không tự trở thành `onError` của `orders`, vì Publisher con không được ghép vào chuỗi ngoài.
- **Cancellation không truyền xuống:** khi subscription ngoài bị hủy, subscription con không tự động bị hủy theo. Tác vụ con có thể tiếp tục chạy.
- **Backpressure không phối hợp:** demand của Subscriber ngoài không giới hạn số subscription con được tạo theo cách mong muốn. Mỗi `subscribe()` tiện lợi có thể yêu cầu không giới hạn dữ liệu từ Publisher con.
- **Khó bảo đảm thứ tự:** các thao tác con có thể hoàn tất theo thứ tự khác với thứ tự đơn hàng đầu vào.
- **Khó kiểm thử và quan sát:** kiểm thử Publisher ngoài có thể hoàn tất trước khi tác vụ con hoàn tất, nên kết quả kiểm thử không còn đại diện đầy đủ cho workflow.

Nested subscription không phải lúc nào cũng sai về mặt cú pháp. Nó có thể tạo ra một tác vụ tách rời có chủ đích. Vấn đề là dùng nó vô tình cho công việc vẫn cần thuộc cùng một quy trình nghiệp vụ.

## 3. Vì sao `doOnNext` không phải nơi ghép Publisher con?

Các toán tử `doOn...` được thiết kế để quan sát tín hiệu hoặc thực hiện hành động đồng bộ nhỏ như ghi log, tăng metric hay cập nhật một bộ đếm. Callback của `doOnNext` nhận phần tử và trả về `void`; nó không sử dụng giá trị Publisher mà callback có thể tạo ra.

~~~java
orders
    .doOnNext(order -> {
        metrics.incrementOrders();
        inventory.reserve(order); // Chỉ tạo Publisher; chưa được subscribe.
    });
~~~

Nếu `reserve` trả về `Mono<Void>`, lời gọi phương thức có thể chỉ tạo một Publisher mô tả thao tác. Vì không subscribe hoặc ghép Publisher đó, công việc có thể không chạy. Nếu callback viết `inventory.reserve(order).subscribe()`, công việc bắt đầu nhưng tách khỏi pipeline ngoài.

Hai cách trên đều không biểu diễn quan hệ bất đồng bộ mà workflow cần. Hãy phân biệt:

| Nhu cầu | Toán tử hoặc cách làm phù hợp |
|---|---|
| Ghi log, tăng metric đồng bộ khi nhận phần tử | `doOnNext` |
| Biến đổi phần tử đồng bộ | `map` |
| Với mỗi phần tử, gọi Publisher con và chờ kết quả | `flatMap` |
| Chạy Publisher con tuần tự theo thứ tự nguồn | `concatMap` |
| Chạy Publisher con đồng thời nhưng giữ thứ tự phát kết quả | `flatMapSequential` |
| Chờ một Publisher hoàn tất rồi chạy Publisher tiếp theo | `then` |
| Chờ nhiều Publisher độc lập cùng hoàn tất | `Mono.when` |

Ví dụ, `map` phù hợp khi hàm trả về một giá trị thường:

~~~java
Mono<OrderView> view =
    orderRepository.findById(orderId)
        .map(orderMapper::toView);
~~~

Nếu hàm trả về một Publisher, `map` tạo kiểu lồng nhau:

~~~java
Mono<Mono<Reservation>> nested =
    orderRepository.findById(orderId)
        .map(inventory::reserve);
~~~

Kết quả là `Mono<Mono<Reservation>>`. Pipeline ngoài phát ra một Publisher con như một giá trị; nó không tự động subscribe Publisher con đó. Muốn hợp nhất luồng, dùng `flatMap`:

~~~java
Mono<Reservation> reservation =
    orderRepository.findById(orderId)
        .flatMap(inventory::reserve);
~~~

`flatMap` nhận Publisher do hàm ánh xạ trả về, subscribe vào Publisher con và chuyển các tín hiệu của nó vào luồng kết quả. Đây là cách ghép bất đồng bộ thông thường trong Reactor.

## 4. Dùng flatMap để ghép tác vụ bất đồng bộ

Với ví dụ đơn hàng, có thể viết:

~~~java
Flux<Order> reservedOrders =
    orderRepository.findPending()
        .flatMap(order ->
            inventory.reserve(order)
                .thenReturn(order),
            16
        );
~~~

Trong ví dụ:

- `flatMap` nhận mỗi `Order` và gọi `inventory.reserve(order)`.
- `thenReturn(order)` chờ `Mono<Void>` đặt chỗ hoàn tất rồi phát lại đơn hàng.
- Tham số `16` giới hạn số Publisher con được subscribe đồng thời.
- Lỗi của một Publisher con đi vào kênh lỗi của `reservedOrders`, trừ khi được xử lý ở vị trí phù hợp.
- Cancellation của subscription kết quả được truyền qua toán tử để hủy các subscription con mà toán tử quản lý.

~~~mermaid
flowchart TD
    A[orders Publisher] --> B[flatMap]
    B --> C1[reserve order 1]
    B --> C2[reserve order 2]
    B --> C3[reserve order 3]
    C1 --> D[Hợp nhất tín hiệu]
    C2 --> D
    C3 --> D
    D --> E[reservedOrders]
~~~

Giới hạn concurrency phải dựa trên năng lực dịch vụ tồn kho, connection pool và mục tiêu độ trễ. Con số 16 chỉ là ví dụ. Nếu bỏ qua giới hạn trong một pipeline có lượng phần tử lớn, hệ thống có thể mở quá nhiều thao tác I/O đồng thời và gây áp lực lên dịch vụ phụ thuộc.

Nếu mỗi thao tác cần giữ thứ tự và không được chạy song song, dùng `concatMap`:

~~~java
Flux<Order> reservedInOrder =
    orderRepository.findPending()
        .concatMap(order ->
            inventory.reserve(order)
                .thenReturn(order)
        );
~~~

`concatMap` chỉ xử lý Publisher con tiếp theo sau khi Publisher con hiện tại kết thúc. Cách này giữ thứ tự và giới hạn số tác vụ con đang hoạt động, nhưng thông lượng có thể thấp hơn khi mỗi thao tác chờ I/O lâu.

Nếu muốn xử lý đồng thời nhưng phát kết quả theo thứ tự nguồn, có thể dùng `flatMapSequential`:

~~~java
Flux<Order> reservedInSourceOrder =
    orderRepository.findPending()
        .flatMapSequential(order ->
            inventory.reserve(order)
                .thenReturn(order),
            16
        );
~~~

Các thao tác vẫn có thể hoàn tất không theo thứ tự, nhưng kết quả được xếp lại theo thứ tự phần tử nguồn. Điều này có thể cần thêm bộ đệm nếu phần tử đầu tiên chậm trong khi các phần tử sau đã hoàn tất.

## 5. Ghép nhiều bước trong cùng workflow

Một tác vụ nghiệp vụ thường gồm nhiều Publisher. Ví dụ, sau khi lấy đơn hàng, ứng dụng đặt chỗ tồn kho rồi mới yêu cầu thanh toán:

~~~java
Mono<OrderReceipt> processOrder(String orderId) {
    return orderRepository.findById(orderId)
        .switchIfEmpty(Mono.error(new OrderNotFoundException(orderId)))
        .flatMap(order ->
            inventory.reserve(order)
                .then(payment.authorize(order))
                .map(receipt ->
                    new OrderReceipt(order.id(), receipt)
                )
        );
}
~~~

Chuỗi này mô tả thứ tự phụ thuộc:

1. Lấy đơn hàng.
2. Nếu không có đơn, phát lỗi nghiệp vụ.
3. Đặt chỗ tồn kho.
4. Chờ đặt chỗ hoàn tất rồi mới gọi thanh toán.
5. Chuyển kết quả thành biên nhận.

Không có subscription con bị bỏ rơi. Mỗi Publisher con được ghép bằng toán tử, nên kết quả chỉ hoàn tất khi các bước tương ứng hoàn tất.

Nếu hai thao tác độc lập và có thể chạy song song, có thể dùng `Mono.when`:

~~~java
Mono<Order> prepare(Order order) {
    return Mono.when(
            auditRepository.recordAccepted(order),
            notificationService.publishAccepted(order)
        )
        .thenReturn(order);
}
~~~

`Mono.when` hoàn tất khi các Publisher đầu vào hoàn tất. Nếu một Publisher phát lỗi, luồng kết quả báo lỗi và các Publisher còn lại do toán tử quản lý có thể bị hủy. Nếu nghiệp vụ yêu cầu thu thập lỗi từ tất cả tác vụ, hãy cân nhắc toán tử delay-error tương ứng và xác định rõ cách tổng hợp lỗi.

Dùng `then` khi giá trị của bước trước không cần giữ lại và ta chỉ cần chờ nó hoàn tất trước bước kế tiếp:

~~~java
Mono<Void> workflow =
    inventory.reserve(order)
        .then(auditRepository.recordReserved(order))
        .then();
~~~

Các toán tử này làm rõ quan hệ phụ thuộc và vòng đời giữa các tác vụ. Đó chính là thông tin bị mất khi ta gọi `subscribe()` độc lập trong callback.

## 6. Xử lý lỗi ở đúng luồng

Với nested subscription, lỗi của Publisher con không tự truyền tới subscriber của Publisher ngoài. Ví dụ:

~~~java
orders.doOnNext(order ->
    inventory.reserve(order).subscribe()
);
~~~

Nếu `reserve` thất bại, callback lỗi của subscription con hoặc cơ chế xử lý lỗi mặc định của Reactor nhận lỗi đó. Các toán tử `onErrorResume` đặt ở `orders` không nhìn thấy lỗi này vì subscription ngoài không nhận tín hiệu lỗi từ Publisher con.

Khi ghép bằng `flatMap`, lỗi đi vào chuỗi kết quả:

~~~java
Flux<Order> result =
    orders.flatMap(order ->
        inventory.reserve(order)
            .thenReturn(order)
    )
    .onErrorResume(error -> {
        log.error("Order processing failed", error);
        return Flux.empty();
    });
~~~

Ở đây, `onErrorResume` có thể thay thế luồng lỗi bằng một Publisher khác. Tuy nhiên, đặt xử lý lỗi sau `flatMap` thường có nghĩa lỗi của một phần tử có thể kết thúc cả luồng tổng hợp. Nếu muốn xử lý lỗi riêng cho từng đơn hàng và tiếp tục phần còn lại, đặt recovery bên trong hàm ánh xạ:

~~~java
Flux<OrderResult> results =
    orders.flatMap(order ->
        inventory.reserve(order)
            .thenReturn(OrderResult.success(order))
            .onErrorResume(error ->
                Mono.just(OrderResult.failure(order, error))
            ),
        16
    );
~~~

Khi đó lỗi của một đơn được chuyển thành kết quả lỗi tương ứng; các đơn khác vẫn có thể tiếp tục. Chọn vị trí recovery theo quy tắc nghiệp vụ: lỗi nào làm hỏng toàn bộ workflow, lỗi nào chỉ ảnh hưởng một phần tử.

## 7. Backpressure và cancellation khi ghép Publisher

Backpressure chỉ có ích khi quan hệ giữa các bước được giữ trong cùng chuỗi tín hiệu. Nếu callback ngoài tự gọi `subscribe()` cho mỗi phần tử, subscription ngoài và các subscription con có demand riêng. Subscriber ngoài không còn điều khiển trực tiếp số tác vụ con đang hoạt động.

~~~java
orders.doOnNext(order ->
    inventory.reserve(order).subscribe()
);
~~~

Với `Flux` có thể phát nhiều đơn, mỗi phần tử có thể tạo một subscription mới. Các lời gọi con có thể tích tụ, tiêu thụ connection, thread hoặc bộ nhớ. Việc subscription ngoài nhận demand không tự giới hạn số lời gọi con đang chạy.

Khi dùng `flatMap` với concurrency hữu hạn, toán tử điều phối số Publisher con được subscribe đồng thời và phối hợp với demand của upstream. Đây là cách phổ biến để kiểm soát lượng I/O bất đồng bộ đang diễn ra:

~~~java
orders.flatMap(
    order -> inventory.reserve(order),
    16
);
~~~

Nếu Subscriber cuối hủy subscription kết quả, cancellation truyền qua chuỗi toán tử để Publisher con do `flatMap` quản lý nhận yêu cầu hủy. Một thao tác đã được gửi đến dịch vụ từ xa có thể vẫn hoàn tất ở phía dịch vụ; cancellation không phải rollback. Vì vậy, các tác vụ ghi dữ liệu vẫn cần idempotency, timeout và quy tắc xử lý trạng thái chưa rõ kết quả.

## 8. Đặt subscribe ở ranh giới phù hợp

Trong ứng dụng reactive, một tầng thường xây dựng và trả về Publisher để tầng gọi quyết định cách kết hợp. Điểm subscribe nằm ở nơi ứng dụng thực sự bắt đầu tiêu thụ luồng, chẳng hạn một tác nhân chạy độc lập hoặc runtime/framework chịu trách nhiệm điều phối.

Một service nên trả về Publisher:

~~~java
@Service
class OrderService {
    Mono<OrderReceipt> process(String orderId) {
        return orderRepository.findById(orderId)
            .flatMap(order ->
                inventory.reserve(order)
                    .then(payment.authorize(order))
                    .map(receipt ->
                        new OrderReceipt(order.id(), receipt)
                    )
            );
    }
}
~~~

Trong ứng dụng Spring WebFlux, controller có thể trả về Publisher cho framework:

~~~java
@RestController
class OrderController {
    private final OrderService orderService;

    @PostMapping("/orders/{id}/process")
    Mono<OrderReceipt> process(@PathVariable String id) {
        return orderService.process(id);
    }
}
~~~

Framework sẽ subscribe và quản lý vòng đời phản hồi HTTP. Service không cần tự subscribe rồi trả về một giá trị rỗng hoặc một handle không liên quan.

Với một tiến trình nền được khởi động từ entry point, subscribe có thể xuất hiện ở biên đó:

~~~java
Disposable job = orderService.processPendingOrders()
    .subscribe(
        result -> log.info("Processed: {}", result.id()),
        error -> log.error("Batch failed", error)
    );
~~~

Ở đây subscription là một tác vụ độc lập có chủ đích. Mã quản lý tiến trình cần giữ handle nếu cần hủy, theo dõi lỗi và gắn vòng đời job với vòng đời ứng dụng. Không nên sao chép cách này vào từng callback của pipeline chỉ để kích hoạt Publisher con.

## 9. Khi nào tác vụ tách rời là chủ đích?

Một số nghiệp vụ thực sự yêu cầu khởi chạy công việc nền mà không chờ kết quả trong phản hồi hiện tại. Ví dụ, sau khi ghi nhận một thao tác người dùng, hệ thống có thể đưa yêu cầu gửi email vào một worker riêng.

Ngay cả trong trường hợp đó, gọi `subscribe()` trực tiếp trong `doOnNext` thường không đủ để tạo một cơ chế nền đáng tin cậy. Cần trả lời các câu hỏi:

- Ai sở hữu vòng đời của tác vụ sau khi request ban đầu kết thúc?
- Có giới hạn số tác vụ đang chờ và đang chạy hay không?
- Nếu ứng dụng dừng, tác vụ đang chạy hoặc đang chờ được xử lý thế nào?
- Lỗi được ghi nhận, retry và cảnh báo ở đâu?
- Tác vụ có thể chạy lặp lại không, và cơ chế idempotency nào bảo vệ nó?
- Ai có quyền hủy tác vụ và cancellation có ý nghĩa gì với hệ thống từ xa?

Với công việc quan trọng, thường nên gửi một command/event vào hàng đợi bền vững và để worker quản lý việc tiêu thụ, retry và xác nhận. Nếu tác vụ tách rời chỉ là công việc nội bộ nhẹ và vòng đời được quản lý trong cùng tiến trình, cần ít nhất giữ `Disposable`, truyền callback lỗi rõ ràng, giới hạn concurrency và có chính sách shutdown.

Ví dụ minh họa quản lý một subscription độc lập ở tầng điều phối:

~~~java
Disposable backgroundTask = notificationService.sendDigest(userId)
    .subscribe(
        ignored -> log.info("Digest sent for {}", userId),
        error -> log.error("Digest failed for {}", userId)
    );

// Khi vòng đời thành phần kết thúc, tầng sở hữu quyết định dispose.
backgroundTask.dispose();
~~~

Ví dụ này chỉ minh họa việc lưu handle và hủy một subscription. Nó không thay thế hàng đợi bền vững, retry hay bảo đảm giao nhận. Nếu cần bảo đảm tác vụ được xử lý sau khi tiến trình khởi động lại, hãy dùng cơ chế lưu trữ và worker phù hợp.

## 10. Kiểm thử để phát hiện luồng tách rời

Một kiểm thử tốt nên chứng minh rằng Publisher kết quả chỉ hoàn tất sau khi Publisher con hoàn tất. Có thể dùng `StepVerifier` và một Publisher con có độ trễ giả lập:

~~~java
AtomicBoolean completed = new AtomicBoolean();

Mono<String> inner =
    Mono.delay(Duration.ofMillis(50))
        .doOnNext(ignored -> completed.set(true))
        .thenReturn("reserved");

Mono<String> composed =
    inner.map(value -> "order-" + value);

StepVerifier.create(composed)
    .expectNext("order-reserved")
    .verifyComplete();

assertThat(completed).isTrue();
~~~

Với nested subscription, kiểm thử Publisher ngoài có thể kết thúc ngay cả khi Publisher con chưa xong:

~~~java
AtomicBoolean innerCompleted = new AtomicBoolean();

Mono<Void> inner =
    Mono.delay(Duration.ofMillis(50))
        .doOnNext(ignored -> innerCompleted.set(true))
        .then();

Mono<Void> outer =
    Mono.just("start")
        .doOnNext(ignored -> inner.subscribe());

StepVerifier.create(outer)
    .verifyComplete();

// Không thể giả định innerCompleted đã true ở đây.
~~~

Kiểm thử thứ hai minh họa sự tách rời: `outer` không chờ subscription con. Không nên viết assertion phụ thuộc vào việc tác vụ con đã hoàn tất sau khi outer hoàn tất, trừ khi kiểm thử chủ động đồng bộ hoặc chờ tác vụ con riêng.

Các khía cạnh nên kiểm thử cho workflow thực tế:

- Luồng kết quả chỉ hoàn tất sau các tác vụ Publisher con bắt buộc.
- Lỗi của Publisher con truyền đến nơi xử lý lỗi dự kiến.
- Recovery theo từng phần tử không làm dừng các phần tử độc lập còn lại.
- Concurrency không vượt giới hạn được thiết kế.
- Cancellation của subscriber cuối được truyền tới các Publisher con.
- Nhiều subscription không vô tình tạo tác dụng phụ trùng.
- Một tác vụ nền tách rời có callback lỗi và chính sách vòng đời rõ ràng.

## 11. Những nhầm lẫn thường gặp

- **Gọi `subscribe()` trong `doOnNext` là cách ghép hai Publisher:** lời gọi này tạo một subscription độc lập; dùng `flatMap` hoặc toán tử kết hợp phù hợp.
- **`doOnNext` chờ Publisher trả về từ callback:** callback chỉ nhận phần tử và thực hiện hành động quan sát; Publisher con bị bỏ qua nếu không được ghép.
- **Lỗi của Publisher con sẽ đi tới `onErrorResume` bên ngoài:** lỗi chỉ truyền qua quan hệ Publisher đã được ghép; subscription tách rời có kênh lỗi riêng.
- **Hủy luồng ngoài sẽ dừng tất cả công việc đã khởi chạy:** cancellation không tự truyền đến subscription con được tạo độc lập.
- **`map` tự flatten Publisher:** `map` tạo Publisher lồng nhau; `flatMap` mới kết hợp Publisher con.
- **Tạo nhiều subscription con không ảnh hưởng tải:** mỗi subscription có thể tạo I/O, tài nguyên và công việc đồng thời riêng.
- **Có thể bỏ qua lỗi trong tác vụ nền:** lỗi không được xử lý có thể trở thành lỗi không được tiêu thụ hoặc chỉ xuất hiện ở log; tác vụ nền cần cơ chế quan sát rõ ràng.
- **Subscribe ở tầng service giúp workflow chạy chắc chắn hơn:** service nên trả về Publisher để caller hoặc framework quản lý subscription ở ranh giới phù hợp.

## 12. Bài tập vận dụng

Một service xử lý các yêu cầu hoàn tiền:

~~~java
Flux<RefundRequest> requests = refundRepository.findPending();

Flux<RefundRequest> result =
    requests.doOnNext(request ->
        paymentGateway.refund(request).subscribe()
    );
~~~

Hãy phân tích và thiết kế lại:

1. Mỗi yêu cầu hoàn tiền tạo ra bao nhiêu subscription? Publisher ngoài có chờ kết quả hoàn tiền không?
2. Nếu cổng thanh toán trả về lỗi, tầng nào nhận lỗi đó? Một `onErrorResume` đặt sau `doOnNext` có xử lý được không?
3. Nếu người gọi hủy `result`, các thao tác hoàn tiền đã khởi chạy có bị hủy theo không?
4. Hãy viết lại bằng `flatMap` với concurrency hữu hạn để giới hạn số yêu cầu hoàn tiền đồng thời.
5. Nếu cần xử lý tuần tự để bảo đảm thứ tự nghiệp vụ, nên chọn toán tử nào?
6. Nếu một yêu cầu hoàn tiền thất bại nhưng các yêu cầu khác vẫn cần xử lý, nên đặt recovery ở đâu?
7. Nếu hoàn tiền là tác vụ nền phải được bảo đảm sau khi ứng dụng khởi động lại, nên dùng cơ chế nào để lưu và quản lý công việc?

**Gợi ý:** thay `doOnNext` bằng `flatMap(request -> paymentGateway.refund(request).thenReturn(request), concurrency)`. Dùng `concatMap` nếu cần xử lý lần lượt. Đặt `onErrorResume` bên trong hàm ánh xạ nếu chỉ muốn chuyển lỗi của từng yêu cầu thành kết quả riêng. Với công việc phải sống qua lần khởi động lại, hãy cân nhắc hàng đợi bền vững và worker có cơ chế retry/idempotency.

## Kết luận

Mỗi lời gọi `subscribe()` tạo một phiên tiêu thụ Publisher. Khi gọi nó bên trong toán tử, ta có thể vô tình tạo một luồng con không còn nằm trong vòng đời, kênh lỗi, demand và cancellation của pipeline ngoài. Hãy dùng `doOn...` cho tác dụng phụ quan sát đồng bộ, `map` cho biến đổi đồng bộ và `flatMap` hoặc các toán tử kết hợp khác cho tác vụ bất đồng bộ. Đặt subscription ở ranh giới sở hữu việc tiêu thụ luồng; nếu cần công việc nền tách rời, quản lý rõ handle, lỗi, concurrency và vòng đời của nó. Cách tổ chức này giúp pipeline `Mono`/`Flux` có hành vi nhất quán, kiểm thử được và dễ vận hành hơn.
