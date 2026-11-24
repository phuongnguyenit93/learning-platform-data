# Lỗi thường gặp

## Gọi subscribe lồng nhau làm tách vòng đời và đường truyền lỗi

Trong mô-đun **REACTIVE_PROGRAMMING**, ta học tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams. Ta thực hành `Mono`, `Flux`, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Một lỗi thiết kế dễ gặp là gọi `subscribe()` bên trong một service, toán tử hoặc callback trong khi Publisher bên ngoài vẫn đang được ghép. Lời gọi đó tạo ra một subscription mới, độc lập với subscription của pipeline chính.

Kết quả là hai luồng công việc có vòng đời riêng. Pipeline bên ngoài có thể hoàn tất trước khi công việc bên trong hoàn tất; lỗi của công việc bên trong không tự đi vào `onError` của pipeline ngoài; cancellation và demand từ Subscriber cuối không tự điều khiển subscription lồng nhau. Các context gắn với subscription, như reactive transaction hoặc Reactor Context, cũng có thể bị tách khỏi đường thực thi ban đầu.

Cách khắc phục thường là trả Publisher từ phương thức và ghép nó bằng toán tử phù hợp: `flatMap` khi bước sau trả Publisher và cần kết quả của nó, `then` khi chỉ cần chờ một thao tác hoàn tất, `zip` hoặc `Mono.when` khi cần phối hợp các nguồn độc lập. `subscribe()` vẫn cần thiết ở ranh giới tiêu thụ, nhưng nơi đó phải sở hữu rõ ràng vòng đời công việc.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao `subscribe()` tạo một subscription độc lập.
- Nhận diện nested subscription trong `doOnNext`, service và callback.
- Phân tích việc tách subscription ảnh hưởng tới completion, error, cancellation và demand.
- Giải thích vì sao reactive transaction và Reactor Context không tự truyền sang subscription mới.
- Thay nested `subscribe()` bằng `flatMap`, `then`, `zip` hoặc `Mono.when`.
- Phân biệt tác vụ thuộc request với công việc nền cần tiếp tục độc lập.
- Chọn đúng ranh giới để subscribe và quản lý `Disposable`.
- Kiểm thử đường truyền lỗi và cancellation bằng `StepVerifier`.

## 1. subscribe() thực hiện điều gì?

Một Publisher mô tả nguồn dữ liệu hoặc một quy trình xử lý. Khi Subscriber đăng ký, Publisher thiết lập subscription và bắt đầu trao đổi tín hiệu theo hợp đồng Reactive Streams:

- `onSubscribe`: Publisher cung cấp Subscription cho Subscriber.
- `request(n)`: Subscriber yêu cầu số phần tử có thể nhận.
- `onNext(value)`: Publisher phát một phần tử theo demand.
- `onError(error)`: Publisher kết thúc do lỗi.
- `onComplete()`: Publisher kết thúc bình thường.
- `cancel()`: Subscriber yêu cầu dừng subscription.

Trong Reactor, gọi `subscribe()` là một cách tạo Subscriber và bắt đầu tiêu thụ Publisher. Một số overload trả về `Disposable` để bên gọi có thể hủy subscription đó.

~~~java
Mono<Order> publisher = orderRepository.findById(orderId);

// Chưa có subscription: nguồn cold thường chưa thực thi truy vấn.
Disposable subscription = publisher.subscribe(
    order -> log.info("Loaded order {}", order.id()),
    error -> log.error("Could not load order", error),
    () -> log.info("Lookup completed")
);
~~~

Đoạn mã trên tạo một subscription riêng. Nếu cùng Publisher được subscribe lần nữa, nguồn cold có thể thực thi lại từ đầu:

~~~java
Mono<Order> publisher = orderRepository.findById(orderId);

publisher.subscribe(this::updateScreen);
publisher.subscribe(this::writeAudit);
~~~

Hai subscription không tự hợp thành một workflow. Chúng có thể thực hiện hai lần truy vấn, có thời điểm hoàn tất khác nhau và nhận lỗi độc lập. Với hot Publisher, subscriber thứ hai còn có thể chỉ nhìn thấy những tín hiệu phát sau thời điểm nó đăng ký, tùy semantics của nguồn.

**Nested subscription** xảy ra khi một subscription được tạo trong lúc xử lý tín hiệu của một subscription khác, ví dụ gọi `subscribe()` trong `doOnNext` hoặc trong một hàm service đang trả Publisher.

## 2. Ví dụ sai: subscribe trong doOnNext

Giả sử khi đọc đơn hàng, hệ thống cần ghi nhận audit:

~~~java
// Không nên: audit có subscription riêng.
Mono<Order> findOrder(String orderId) {
    return orderRepository.findById(orderId)
        .doOnNext(order ->
            auditRepository.recordViewed(order).subscribe()
        );
}
~~~

Pipeline ngoài trả về `Mono<Order>`. Khi repository phát Order, callback gọi `subscribe()` để khởi động thao tác audit. Nhưng `doOnNext` chỉ là callback quan sát tín hiệu; nó không ghép Publisher audit vào pipeline ngoài.

Điều đó dẫn tới một số hệ quả:

1. Pipeline tìm đơn hàng có thể phát Order và hoàn tất ngay, trong khi audit vẫn đang chạy.
2. Caller không thể chờ audit hoàn tất trước khi trả kết quả.
3. `onErrorResume` ở caller không nhận được lỗi từ audit.
4. Caller hủy subscription tìm đơn hàng không tự hủy subscription audit.
5. Demand của Subscriber cuối không điều tiết demand của audit.
6. Reactive transaction của pipeline ngoài không tự bao bọc thao tác audit.
7. Test chỉ xác minh được kết quả tìm đơn hàng, trừ khi test quản lý riêng subscription audit.

Nếu audit là một phần của nghiệp vụ đọc đơn hàng, những hành vi này làm hợp đồng của API không rõ ràng. Caller tưởng rằng thao tác đã hoàn tất khi nhận được kết quả, nhưng một phần công việc vẫn còn chạy ở nơi khác.

## 3. Ghép Publisher con bằng flatMap

Nếu thao tác audit cần hoàn tất trước khi phát đơn hàng, hãy dùng `flatMap` để kết hợp Publisher con:

~~~java
Mono<Order> findOrder(String orderId) {
    return orderRepository.findById(orderId)
        .flatMap(order ->
            auditRepository.recordViewed(order)
                .thenReturn(order)
        );
}
~~~

`auditRepository.recordViewed(order)` trả về `Mono<Void>`. `thenReturn(order)` chờ audit hoàn tất rồi phát lại Order ban đầu. Vì Publisher con nằm trong chuỗi `flatMap`, pipeline ngoài chỉ hoàn tất sau khi audit hoàn tất.

Đường truyền tín hiệu giờ đây liền mạch:

~~~mermaid
flowchart TD
    A[Caller subscribe] --> B[orderRepository.findById]
    B --> C{Có Order?}
    C -->|Có| D[flatMap]
    D --> E[auditRepository.recordViewed]
    E --> F[thenReturn Order]
    F --> G[Caller nhận Order]
    E -->|Lỗi| H[onError của pipeline]
    H --> I[Caller xử lý lỗi]
    G --> J[Complete]
~~~

Nếu audit lỗi, lỗi truyền qua `flatMap` tới Subscriber cuối. Caller có thể quyết định trả lỗi, fallback hoặc ghi nhận kết quả nghiệp vụ theo đúng hợp đồng.

### map và flatMap khác nhau thế nào?

Dùng `map` khi hàm biến đổi nhận một giá trị và trả về một giá trị đồng bộ:

~~~java
Mono<OrderView> view =
    orderRepository.findById(orderId)
        .map(this::toView);
~~~

Dùng `flatMap` khi hàm biến đổi trả về một Publisher khác:

~~~java
Mono<OrderView> view =
    orderRepository.findById(orderId)
        .flatMap(order ->
            customerRepository.findById(order.customerId())
                .map(customer -> toView(order, customer))
        );
~~~

Nếu dùng `map` với hàm trả Publisher, kiểu kết quả sẽ bị lồng, chẳng hạn `Mono<Mono<Customer>>`. `flatMap` ghép Publisher con vào cùng chuỗi để Subscriber cuối nhận `Customer`.

## 4. Dùng then khi không cần giá trị của bước trước

Nhiều thao tác bất đồng bộ chỉ cần hoàn tất hoặc báo lỗi, không cần trả dữ liệu. `then` thể hiện quan hệ tuần tự đó:

~~~java
Mono<Void> processOrder(Order order) {
    return orderRepository.save(order)
        .then(auditRepository.recordOrderCreated(order))
        .then(notificationService.sendOrderCreated(order.id()));
}
~~~

Các bước chạy lần lượt. Nếu lưu đơn hàng lỗi, audit và notification không chạy. Nếu audit lỗi, notification không chạy. Toàn bộ workflow được biểu diễn bằng một `Mono<Void>`.

Nếu cần trả kết quả sau cùng, dùng `thenReturn`:

~~~java
Mono<OrderReceipt> processOrder(Order order) {
    return orderRepository.save(order)
        .flatMap(saved ->
            auditRepository.recordOrderCreated(saved)
                .then(notificationService.sendOrderCreated(saved.id()))
                .thenReturn(OrderReceipt.from(saved))
        );
}
~~~

`then` không phát giá trị của Publisher trước. Nó chờ Publisher đó hoàn tất rồi mới subscribe Publisher kế tiếp. Nếu cần giá trị của bước trước, giữ giá trị trong `flatMap` hoặc dùng `thenReturn`.

## 5. Phối hợp các công việc độc lập

Nếu nhiều Publisher độc lập và đều phải hoàn tất, có thể dùng `Mono.when`:

~~~java
Mono<Void> updateRelatedSystems(Order order) {
    return Mono.when(
        auditRepository.recordOrderCreated(order),
        notificationService.sendOrderCreated(order.id()),
        searchIndex.updateOrder(order)
    );
}
~~~

Các nguồn được phối hợp trong cùng một Publisher. Subscriber cuối có một điểm quan sát completion, error và cancellation cho nhóm công việc. `Mono.when` hoàn tất khi các nguồn hoàn tất; nếu một nguồn lỗi, kết quả lỗi và các nguồn còn lại được toán tử quản lý có thể bị hủy.

Nếu cần kết quả từ nhiều nguồn, dùng `Mono.zip`:

~~~java
Mono<OrderSummary> summary(String orderId) {
    return Mono.zip(
        orderRepository.findById(orderId),
        paymentRepository.findLatest(orderId),
        inventoryRepository.findReservation(orderId)
    )
    .map(tuple ->
        new OrderSummary(
            tuple.getT1(),
            tuple.getT2(),
            tuple.getT3()
        )
    );
}
~~~

Không cần tạo subscription riêng cho từng nguồn. `zip` phối hợp chúng trong cùng chuỗi và chỉ phát kết quả khi mỗi nguồn cung cấp giá trị. Nếu một nguồn hoàn tất rỗng, zip có thể hoàn tất rỗng; hãy biểu diễn giá trị tùy chọn bằng `defaultIfEmpty` nếu nghiệp vụ yêu cầu.

### Chọn toán tử theo quan hệ giữa các bước

| Nhu cầu | Toán tử thường dùng | Kết quả |
|---|---|---|
| Biến đổi đồng bộ một giá trị | `map` | Một giá trị mới |
| Bước sau trả Publisher và phụ thuộc giá trị trước | `flatMap` | Ghép Publisher con |
| Chờ bước trước rồi chạy bước sau | `then` | Publisher của bước sau |
| Chờ bước trước rồi phát giá trị cố định | `thenReturn` | Giá trị được giữ lại |
| Chờ nhiều tác vụ độc lập hoàn tất | `Mono.when` | `Mono<Void>` |
| Kết hợp kết quả từ nhiều nguồn | `Mono.zip` | Một tuple hoặc kết quả đã ánh xạ |
| Xử lý nhiều phần tử với thứ tự nguồn | `concatMap` | Inner được xử lý tuần tự |
| Xử lý nhiều phần tử có concurrency | `flatMap` | Inner có thể chạy đồng thời |

Chọn toán tử dựa trên quan hệ dữ liệu và thứ tự nghiệp vụ, không dựa trên việc muốn "chạy ngay" hay "chạy nền".

## 6. Lỗi từ subscription lồng nhau đi đâu?

Xét ví dụ:

~~~java
Mono<Order> result =
    orderRepository.findById(orderId)
        .doOnNext(order ->
            auditRepository.recordViewed(order).subscribe()
        );
~~~

Nếu audit thất bại, lỗi thuộc subscription audit. Nó không trở thành lỗi của `result`. Do đó, đoạn xử lý sau không bắt được lỗi audit:

~~~java
result.onErrorResume(error -> fallbackOrder());
~~~

`onErrorResume` chỉ xử lý lỗi truyền qua Publisher mà nó đang đứng trên đó. Nó không thể quan sát một subscription độc lập được tạo bên trong callback.

Nếu dùng `subscribe()` không cung cấp error consumer, Reactor phải chuyển lỗi không được xử lý tới cơ chế lỗi không được tiêu thụ của subscription, có thể dẫn đến log hoặc dropped-error hook tùy cấu hình. Nếu cung cấp error consumer, lỗi được xử lý ở callback riêng, nhưng vẫn không quay lại pipeline ngoài:

~~~java
.doOnNext(order ->
    auditRepository.recordViewed(order)
        .subscribe(
            ignored -> {},
            error -> log.error("Audit failed", error)
        )
)
~~~

Đoạn này có thể làm lỗi audit bớt im lặng, nhưng không giải quyết vấn đề composition. Pipeline ngoài vẫn không chờ audit và caller vẫn không nhận lỗi đó. Nếu audit là một phần của hợp đồng, hãy ghép Publisher bằng `flatMap` hoặc `then`.

### Đặt recovery ở đúng ranh giới

Khi đã ghép đúng, có thể xử lý lỗi ngay ở bước con nếu nghiệp vụ cho phép:

~~~java
Mono<Order> findOrder(String orderId) {
    return orderRepository.findById(orderId)
        .flatMap(order ->
            auditRepository.recordViewed(order)
                .onErrorResume(AuditUnavailableException.class, error -> {
                    log.warn("Audit is temporarily unavailable", error);
                    return Mono.empty();
                })
                .thenReturn(order)
        );
}
~~~

Ví dụ này cho phép đọc đơn hàng tiếp tục khi audit gặp đúng loại lỗi được chấp nhận. Các lỗi khác vẫn truyền ra ngoài. Nếu audit bắt buộc phải thành công, không dùng fallback rỗng; hãy để lỗi truyền tới caller.

## 7. Cancellation không tự truyền vào subscription độc lập

Một lợi ích quan trọng của composition là cancellation truyền qua chuỗi Publisher được ghép. Khi Subscriber cuối hủy, Reactor yêu cầu các toán tử và Publisher con đang hoạt động dừng theo hợp đồng của chúng.

Với nested subscription:

~~~java
Mono<Order> result =
    orderRepository.findById(orderId)
        .doOnNext(order ->
            auditRepository.recordViewed(order).subscribe()
        );
~~~

Caller hủy `result`, nhưng subscription audit đã được tạo riêng và không được pipeline ngoài quản lý. Audit có thể tiếp tục chạy sau khi request HTTP đã kết thúc.

Với `flatMap`:

~~~java
Mono<Order> result =
    orderRepository.findById(orderId)
        .flatMap(order ->
            auditRepository.recordViewed(order)
                .thenReturn(order)
        );
~~~

Cancellation từ caller được truyền tới Publisher audit đang hoạt động. Adapter database hoặc HTTP có thể hủy công việc bên dưới nếu hỗ trợ. Nếu thao tác đã commit ở hệ thống từ xa, cancellation không tự rollback tác dụng phụ đó.

### Kiểm thử cancellation propagation

~~~java
AtomicBoolean innerSubscribed = new AtomicBoolean();
AtomicBoolean innerCancelled = new AtomicBoolean();

Mono<Void> inner = Mono.<Void>never()
    .doOnSubscribe(subscription -> innerSubscribed.set(true))
    .doOnCancel(() -> innerCancelled.set(true));

Mono<Void> workflow =
    Mono.just("order-1")
        .flatMap(orderId -> inner);

StepVerifier.create(workflow)
    .expectSubscription()
    .then(() -> assertThat(innerSubscribed).isTrue())
    .thenCancel()
    .verify();

assertThat(innerCancelled).isTrue();
~~~

Inner Publisher không bao giờ hoàn tất. Khi verifier hủy workflow, `flatMap` chuyển cancellation tới inner; callback xác nhận nó đã bị hủy. Nếu inner được khởi động bằng nested `subscribe()`, cancellation của workflow ngoài không bảo đảm hủy inner đó.

## 8. Demand và backpressure cũng bị tách

Một subscription có demand riêng. Khi Subscriber cuối yêu cầu một phần tử từ pipeline ngoài, demand đó đi qua các toán tử của pipeline ngoài. Subscription được tạo bằng nested `subscribe()` có Subscriber riêng và có thể yêu cầu dữ liệu theo cách hoàn toàn khác.

Ví dụ:

~~~java
Flux<Order> orders = orderRepository.findRecent()
    .doOnNext(order ->
        auditStream.eventsFor(order.id()).subscribe()
    );
~~~

Subscriber cuối điều tiết demand của `orders`, nhưng không điều tiết demand của các `auditStream` được subscribe riêng. Nếu mỗi order tạo một subscription audit và mỗi subscription yêu cầu không giới hạn, hệ thống có thể tạo nhiều công việc đồng thời mà caller không kiểm soát được.

Ghép Publisher con bằng `flatMap` cho phép đặt concurrency:

~~~java
Flux<Order> orders =
    orderRepository.findRecent()
        .flatMap(
            order -> auditStream.eventsFor(order.id())
                .thenReturn(order),
            8
        );
~~~

Ví dụ này giới hạn tối đa tám Publisher con đang hoạt động đồng thời. Nếu mỗi order cần xử lý tuần tự, dùng `concatMap`. Cần nhớ rằng concurrency và prefetch vẫn có thể tạo buffer nội bộ; chọn giới hạn theo năng lực database, connection pool và dịch vụ phụ thuộc.

Không dùng nested `subscribe()` để né backpressure hoặc tạo "fire-and-forget" hàng loạt. Nếu công việc cần chạy độc lập, hãy đưa nó vào một cơ chế job/message có giới hạn và lưu bền vững.

## 9. Reactor Context và transaction bị tách khỏi caller

Reactor Context gắn với subscription, không phải một biến toàn cục. Nó thường mang correlation ID, security context hoặc dữ liệu phục vụ reactive transaction.

Ví dụ một chuỗi gắn correlation ID:

~~~java
Mono<OrderView> view =
    orderRepository.findById(orderId)
        .flatMap(order -> auditRepository.recordViewed(order)
            .thenReturn(toView(order)))
        .contextWrite(context ->
            context.put("correlationId", correlationId)
        );
~~~

Các bước được ghép nằm trên cùng subscription và có thể đọc context tương ứng bằng `deferContextual`.

Nếu callback gọi `subscribe()` tạo subscription mới, subscription đó không tự kế thừa Reactor Context của caller. Context phải được truyền rõ ràng nếu thực sự cần, nhưng với workflow thuộc cùng request, giải pháp đúng thường là giữ các Publisher trong cùng chuỗi.

Reactive transaction cũng gắn với context của subscription. Ví dụ:

~~~java
Mono<Void> createOrder(Order order) {
    return transactionalOperator.transactional(
        orderRepository.save(order)
            .flatMap(saved ->
                auditRepository.recordCreated(saved.id())
            )
    );
}
~~~

Các thao tác tham gia transaction nếu chúng dùng cùng transaction manager và transactional resource. Nếu `auditRepository.recordCreated` được gọi bằng nested `subscribe()`, nó có thể chạy ngoài transaction của caller và commit độc lập. Điều này phá vỡ kỳ vọng rollback cùng nhau.

Một subscription độc lập không thể được coi là một phần của reactive transaction chỉ vì nó được tạo bên trong một callback của pipeline transactional.

## 10. Phân biệt tác vụ thuộc request với tác vụ nền

Không phải mọi tác vụ đều cần nằm trong vòng đời HTTP request. Cần xác định rõ hợp đồng nghiệp vụ:

- Nếu tác vụ là một phần của kết quả request, ghép nó vào Publisher response.
- Nếu tác vụ có thể bỏ khi client rời đi, để cancellation truyền tới nguồn và cleanup tài nguyên.
- Nếu tác vụ phải tiếp tục sau khi client rời đi, ghi nhận nó như một job hoặc message bền vững rồi để worker riêng sở hữu.
- Nếu tác vụ chỉ là metric/log nhẹ, dùng hook quan sát phù hợp; tránh tạo subscription con cho một công việc bất đồng bộ lớn.

### Tác vụ thuộc request

~~~java
Mono<OrderReceipt> placeOrder(OrderCommand command) {
    return customerRepository.findById(command.customerId())
        .switchIfEmpty(Mono.error(
            new CustomerNotFoundException(command.customerId())
        ))
        .flatMap(customer ->
            orderRepository.save(Order.from(command, customer))
        )
        .flatMap(saved ->
            inventoryService.reserve(saved)
                .thenReturn(OrderReceipt.from(saved))
        );
}
~~~

Caller hoặc WebFlux framework sở hữu subscription. Nếu một bước lỗi, lỗi truyền tới caller. Nếu request bị hủy trước khi hoàn tất, cancellation có thể truyền tới bước đang hoạt động. Những tác dụng phụ đã commit vẫn cần chính sách idempotency/đối soát.

### Tác vụ phải tiếp tục độc lập

Nếu yêu cầu xuất báo cáo cần tiếp tục dù client disconnect, hãy lưu job và outbox trước khi trả xác nhận:

~~~java
Mono<JobAccepted> submitExport(ExportCommand command) {
    return transactionalOperator.transactional(
        exportJobRepository.create(command)
            .flatMap(job ->
                outboxRepository.append(ExportRequested.from(job))
                    .thenReturn(new JobAccepted(job.id(), "ACCEPTED"))
            )
    );
}
~~~

Sau khi transaction commit, worker outbox hoặc message consumer xử lý job. Worker có vòng đời riêng, retry có giới hạn, trạng thái bền vững và cơ chế đối soát. HTTP request chỉ nhận job ID; không cần giữ một nested subscription sống sau response.

## 11. Subscribe ở ranh giới tiêu thụ có chủ sở hữu

Một ứng dụng cần có nơi subscribe. Điều quan trọng là subscription phải thuộc về thành phần có thể quản lý vòng đời và outcome.

Các ranh giới thường gặp:

- Spring WebFlux tiêu thụ Publisher được controller trả về.
- Một reactive message listener framework nhận Publisher và quản lý acknowledgement.
- Một worker imperative tích hợp với API chỉ nhận callback và phải subscribe có chủ đích.
- Entry point của ứng dụng batch hoặc command-line.
- Một thành phần scheduler kích hoạt tác vụ định kỳ.

Ví dụ một worker imperative sở hữu subscription:

~~~java
Disposable startReport(String reportId) {
    return reportService.generate(reportId)
        .doOnError(error ->
            log.error("Report {} failed", reportId, error)
        )
        .subscribe(
            report -> log.info("Report {} completed", report.id()),
            error -> log.error("Could not generate report {}", reportId, error)
        );
}
~~~

Worker phải giữ và quản lý `Disposable` nếu cần hủy khi shutdown. Nó cũng phải quyết định retry, trạng thái job, metric và cách phục hồi. Với công việc quan trọng, subscription trong bộ nhớ không thay thế hàng đợi bền vững hoặc job store.

Tránh subscribe trong controller, service nghiệp vụ hoặc repository chỉ để "cho nó chạy". Hãy để các tầng đó trả Publisher lên phía caller.

## 12. Những biến thể nested subscription thường bị bỏ sót

Nested subscription không chỉ xuất hiện trong một lời gọi `subscribe()` nhìn thấy rõ. Hãy chú ý các dạng sau:

### Subscribe trong doOnSuccess hoặc doOnNext

~~~java
Mono<Order> order =
    orderRepository.findById(orderId)
        .doOnSuccess(value -> cacheClient.refresh(orderId).subscribe());
~~~

Hook quan sát không ghép Publisher cache. Nếu refresh thuộc workflow, dùng `flatMap` hoặc `then`.

### Subscribe trong vòng lặp

~~~java
// Không nên: mỗi phần tử tạo một subscription riêng.
orders.doOnNext(order ->
    notificationClient.send(order).subscribe()
);
~~~

Dùng `flatMap` với concurrency phù hợp:

~~~java
orders.flatMap(
    order -> notificationClient.send(order),
    16
);
~~~

### Subscribe trong hàm tiện ích

~~~java
void recordMetricAsync(Order order) {
    metricsClient.publish(order).subscribe();
}
~~~

Tên hàm tiện ích không làm thay đổi ownership. Nếu Publisher cần được chờ, trả nó về caller. Nếu đây là telemetry có thể bỏ, dùng metric client phù hợp hoặc queue có giới hạn và chính sách drop rõ ràng.

### Subscribe trong onErrorResume

~~~java
.onErrorResume(error -> {
    fallbackService.notifyFailure(error).subscribe();
    return Mono.empty();
})
~~~

Thông báo lỗi được tách khỏi pipeline. Nếu cần chờ notification trước khi hoàn tất recovery, ghép nó:

~~~java
.onErrorResume(error ->
    fallbackService.notifyFailure(error)
        .then(Mono.empty())
)
~~~

Nếu cần trả một giá trị thay thế:

~~~java
.onErrorResume(error ->
    fallbackService.notifyFailure(error)
        .thenReturn(cachedResult)
)
~~~

## 13. Những nhầm lẫn thường gặp

- **subscribe() bên trong chỉ là cách viết ngắn:** nó tạo subscription độc lập với lifecycle riêng.
- **Pipeline ngoài chờ Publisher được subscribe bên trong:** callback không tự ghép hoặc chờ Publisher con; dùng `flatMap` hoặc `then`.
- **onErrorResume ngoài bắt được lỗi inner đã subscribe riêng:** lỗi của subscription độc lập không đi qua Publisher ngoài.
- **Thêm error consumer là đã sửa đúng:** error consumer chỉ xử lý lỗi ở subscription riêng; caller vẫn không chờ hoặc điều khiển công việc đó.
- **Cancel pipeline ngoài sẽ cancel mọi công việc đã khởi động:** nested subscription không tự nhận cancellation từ subscription cha.
- **Demand của Subscriber cuối áp dụng cho mọi subscription:** mỗi subscription có demand riêng; nested subscription có thể tiêu thụ độc lập.
- **doOnNext thích hợp để gọi dịch vụ reactive:** hook này dành cho quan sát; dùng toán tử composition để ghép Publisher.
- **map có thể thay flatMap:** map với Publisher con tạo kiểu lồng như `Mono<Mono<T>>`; flatMap mới ghép nó.
- **subscribe mới dùng chung reactive transaction:** transaction context gắn với subscription; nested subscription có thể chạy ngoài transaction.
- **Reactor Context giống ThreadLocal toàn cục:** context thuộc đường subscription và không tự truyền sang subscription mới.
- **subscribe() không có error consumer vẫn chuyển lỗi về caller:** lỗi không được xử lý thuộc subscription mới và đi tới cơ chế lỗi không được tiêu thụ của Reactor.
- **Công việc cần sống sau HTTP request nên nested subscribe:** hãy lưu job/outbox và giao worker có vòng đời độc lập.
- **share() tự sửa được ownership:** share có thể chia sẻ upstream giữa các Subscriber đang tham gia, nhưng không tạo transaction, không bảo đảm replay bền vững và không thay thế composition.

## 14. Bài tập vận dụng

Một service đọc đơn hàng rồi cần ghi audit, cập nhật cache và gửi notification. Audit và cache phải hoàn tất trước khi service trả kết quả; notification phải được lưu bền vững để worker gửi sau, kể cả khi client disconnect.

Hãy thiết kế lại API:

1. Phương thức service nên trả về `Mono<OrderReceipt>` hay `void`? Giải thích.
2. Ghi audit và cập nhật cache nên ghép bằng toán tử nào nếu cả hai đều phải hoàn tất?
3. Nếu cache update phụ thuộc dữ liệu do audit trả về, dùng `flatMap` hay `zip`?
4. Nếu audit lỗi, caller có thể xử lý lỗi bằng cách nào khi Publisher được ghép đúng?
5. Vì sao gọi `subscribe()` trong `doOnNext` không đáp ứng hợp đồng "phải hoàn tất trước khi trả kết quả"?
6. Notification cần được lưu ở đâu để tiếp tục sau client disconnect?
7. Nếu caller hủy request khi audit đang chạy, cancellation truyền qua chuỗi ra sao?
8. Hãy viết một test `StepVerifier` xác minh lỗi audit tới caller và một test xác minh cancellation tới Publisher con.
9. Hãy xác định ranh giới duy nhất nơi worker nền tiêu thụ outbox event và quản lý lỗi giao gửi.

**Gợi ý:** trả `Mono<OrderReceipt>`; ghép audit và cache bằng `flatMap`/`then` hoặc `Mono.when` tùy quan hệ phụ thuộc. Ghi notification outbox trong transaction phù hợp, rồi để worker xử lý sau commit. Dùng `StepVerifier` để xác minh terminal error và cancellation; không tạo nested subscription cho bất kỳ bước nào thuộc workflow response.

## Kết luận

Gọi `subscribe()` lồng nhau tạo một subscription độc lập, khiến pipeline ngoài mất quyền điều phối completion, lỗi, cancellation, demand và context của công việc bên trong. Nếu Publisher con thuộc cùng nghiệp vụ, hãy ghép nó bằng `flatMap`, `then`, `Mono.when` hoặc `Mono.zip` để caller có một đường tín hiệu thống nhất. Nếu công việc phải tiếp tục sau khi request kết thúc, hãy lưu job hoặc outbox bền vững và để worker riêng sở hữu subscription. Chỉ subscribe tại ranh giới tiêu thụ có trách nhiệm quản lý vòng đời, lỗi và tài nguyên; cách tổ chức đó làm cho API reactive dễ kết hợp, kiểm thử và vận hành.
