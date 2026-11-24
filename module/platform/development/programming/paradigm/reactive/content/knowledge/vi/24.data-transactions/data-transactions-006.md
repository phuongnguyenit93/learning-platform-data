# Hoàn tất, lỗi và hủy chuỗi khi đang có giao dịch

Một giao dịch reactive có vòng đời gắn với subscription của publisher. Khi pipeline hoàn tất bình thường, transaction manager có thể commit; khi pipeline phát lỗi, transaction manager rollback; khi downstream hủy subscription, transaction manager cần xử lý nhánh cancellation và giải phóng transaction. Ba trường hợp này có thể dẫn đến kết quả dữ liệu khác nhau, dù ở phía consumer đôi khi chỉ thấy một response hoặc một luồng đã dừng.

Trong Reactor kết hợp Spring Reactive Transactions, transaction được quản lý bằng `ReactiveTransactionManager` và thường được áp dụng qua `TransactionalOperator` hoặc `@Transactional` trên phương thức trả về `Mono`/`Flux`. Ngữ cảnh transaction được gắn với Reactor Context để các thao tác database trong cùng subscription tham gia đúng transaction, kể cả khi pipeline đổi scheduler. Vì vậy, cần hiểu chính xác terminal signal và cancellation đi qua ranh giới transaction như thế nào.

## 1. Vòng đời transaction trong pipeline reactive

Một transaction thường đi qua các bước:

1. Publisher được subscribe và transaction manager bắt đầu hoặc tham gia transaction.
2. Các thao tác database trong pipeline dùng tài nguyên gắn với transaction.
3. Pipeline phát tín hiệu kết thúc.
4. Transaction manager commit, rollback hoặc xử lý cancellation.
5. Tài nguyên như connection được giải phóng.

| Kết thúc pipeline | Tín hiệu/hành động | Xử lý transaction thường cần |
| --- | --- | --- |
| Hoàn tất bình thường | `onComplete` | Commit |
| Phát lỗi | `onError(error)` | Rollback |
| Bị hủy | `cancel()` từ downstream | Rollback và cleanup theo semantics của reactive transaction manager |

Cancellation không phải `onComplete` và cũng không phải `onError`. Subscriber gọi `cancel()` để ngừng nhận tín hiệu. Với Spring reactive transaction, `TransactionalOperator` xử lý cancellation như một nhánh rollback. Điều này đặc biệt quan trọng với `Flux`: downstream có thể đã nhận một vài phần tử rồi hủy phần còn lại, nhưng transaction vẫn cần rollback nếu toàn bộ publisher transactional chưa hoàn tất bình thường.

Sơ đồ khái niệm:

~~~mermaid
flowchart TD
    A[Subscribe publisher transactional] --> B[Bắt đầu hoặc tham gia transaction]
    B --> C[Thực hiện thao tác database]
    C --> D{Kết thúc subscription}
    D -->|onComplete| E[Commit]
    D -->|onError| F[Rollback]
    D -->|cancel| G[Rollback và cleanup]
    E --> H[Giải phóng tài nguyên]
    F --> H
    G --> H
~~~

Đây là mô hình tổng quát. Chi tiết về propagation, savepoint, lỗi commit/rollback và khả năng hủy truy vấn phụ thuộc transaction manager, driver và database đang dùng.

## 2. Đặt ranh giới bằng TransactionalOperator

`TransactionalOperator` cho phép bọc một publisher trong transaction. Với `Mono`, transaction kết thúc khi Mono complete hoặc error; với `Flux`, transaction bao trùm toàn bộ subscription và chỉ kết thúc khi luồng hoàn tất, phát lỗi hoặc bị hủy.

Ví dụ ghi đơn hàng và bản ghi outbox trong cùng transaction:

~~~java
Mono<Order> createOrder(Order order, OutboxEvent event) {
    return orderRepository.save(order)
        .then(outboxRepository.save(event))
        .thenReturn(order)
        .as(transactionalOperator::transactional);
}
~~~

Nếu cả hai thao tác database thành công và publisher hoàn tất, transaction được commit. Nếu lưu order hoặc outbox phát lỗi, transaction được rollback. `then` chỉ tiếp tục bước kế tiếp sau khi publisher trước hoàn tất; do đó outbox chỉ được lưu sau khi thao tác lưu order thành công.

`as(transactionalOperator::transactional)` làm rõ ranh giới transaction ngay trong pipeline. Publisher được tạo trước đó nhưng transaction chỉ được bắt đầu khi có subscription. Mỗi subscription có vòng đời transaction riêng theo chính sách của transaction manager.

### Dùng execute khi cần truy cập TransactionStatus

Nếu cần đánh dấu rollback-only hoặc điều khiển một số chi tiết transaction, `execute` cung cấp callback nhận `TransactionStatus`:

~~~java
Mono<Order> createOrder(Order order) {
    return transactionalOperator.execute(status ->
        orderRepository.save(order)
            .onErrorResume(error -> {
                status.setRollbackOnly();
                return Mono.error(error);
            })
    ).single();
}
~~~

Ví dụ minh họa việc đánh dấu rollback-only rồi giữ lỗi đi ra ngoài. `execute` trả về một `Flux` các kết quả từ callback; với callback chỉ phát một kết quả, có thể dùng `single()` nếu hợp đồng bảo đảm đúng một phần tử. Không dùng `single()` nếu callback có thể complete rỗng hoặc phát nhiều phần tử.

Trong phần lớn trường hợp, để lỗi đi qua ranh giới `TransactionalOperator` là đủ để rollback. Chỉ dùng `setRollbackOnly()` khi nghiệp vụ cần tiếp tục xử lý bên trong transaction nhưng vẫn yêu cầu rollback lúc kết thúc.

## 3. Hoàn tất bình thường dẫn đến commit

Một transaction được commit khi publisher transactional hoàn tất bình thường và không bị đánh dấu rollback-only.

~~~java
Mono<Receipt> receipt = inventoryRepository.reserve(itemId, quantity)
    .then(orderRepository.insert(order))
    .then(receiptRepository.create(order.id()))
    .as(transactionalOperator::transactional);
~~~

Nếu cả ba thao tác hoàn tất thành công, transaction manager commit. Nếu một publisher hoàn tất rỗng nhưng không phát lỗi, `then` vẫn có thể tiếp tục bước kế tiếp; do đó cần bảo đảm mỗi repository method có semantics đúng với nghiệp vụ. Ví dụ, nếu reserve không tìm thấy hàng và trả `Mono.empty()`, pipeline vẫn chạy insert order nếu không có bước kiểm tra rõ ràng.

Nếu kết quả nghiệp vụ cần xác nhận có cập nhật, hãy chuyển trạng thái empty thành lỗi hoặc kết quả từ chối trước khi commit:

~~~java
Mono<Reservation> reservation = inventoryRepository.reserve(itemId, quantity)
    .switchIfEmpty(Mono.error(new OutOfStockException(itemId)));
~~~

Một publisher complete rỗng vẫn là completion bình thường về mặt Reactive Streams. Transaction manager không thể tự suy ra rằng empty đồng nghĩa thất bại nghiệp vụ.

## 4. Lỗi trong transaction dẫn đến rollback

Khi một thao tác database hoặc bước xử lý phát `onError`, lỗi truyền đến ranh giới transaction và transaction manager rollback.

~~~java
Mono<Order> createOrder(Order order) {
    return orderRepository.save(order)
        .then(paymentRecordRepository.insert(order.id()))
        .then(Mono.error(new IllegalStateException("Lỗi kiểm tra sau ghi")))
        .as(transactionalOperator::transactional);
}
~~~

Ví dụ cố ý phát lỗi sau khi ghi để minh họa rollback: bản ghi order và payment record thuộc cùng transaction nên không được commit nếu rollback thành công. Trong ứng dụng thật, lỗi nghiệp vụ nên được biểu diễn bằng exception miền nghiệp vụ phù hợp, không dùng IllegalStateException chung chung.

`doOnError` chỉ quan sát lỗi; nó không phục hồi publisher:

~~~java
Mono<Order> tx = orderRepository.save(order)
    .doOnError(error -> log.warn("Ghi order thất bại", error))
    .as(transactionalOperator::transactional);
~~~

Lỗi vẫn đi qua ranh giới transaction, vì vậy rollback vẫn diễn ra. Nếu dùng `onErrorResume`, `onErrorReturn` hoặc `onErrorComplete`, publisher có thể chuyển lỗi thành completion bình thường. Vị trí của các operator phục hồi lỗi sẽ quyết định transaction manager có nhìn thấy lỗi hay không.

## 5. Vị trí onErrorResume quyết định commit hay rollback

Đây là một trong những điểm dễ gây lỗi nhất khi kết hợp transaction và error recovery.

**Phục hồi lỗi bên trong transaction:**

~~~java
Mono<Order> result = orderRepository.save(order)
    .onErrorResume(error -> {
        log.warn("Không lưu được order, dùng kết quả dự phòng", error);
        return Mono.just(fallbackOrder);
    })
    .as(transactionalOperator::transactional);
~~~

Ở đây, `onErrorResume` nằm trước `transactional`. Nó chuyển lỗi thành một giá trị bình thường. TransactionalOperator chỉ nhìn thấy publisher hoàn tất thành công, vì vậy có thể commit các thay đổi trước đó nếu transaction chưa bị đánh dấu rollback-only. Cách này chỉ đúng khi nghiệp vụ thực sự muốn commit phần công việc còn hợp lệ sau khi phục hồi.

**Phục hồi lỗi bên ngoài transaction:**

~~~java
Mono<Order> result = orderRepository.save(order)
    .as(transactionalOperator::transactional)
    .onErrorResume(error -> {
        log.warn("Transaction thất bại, trả kết quả dự phòng", error);
        return Mono.just(fallbackOrder);
    });
~~~

Ở đây, lỗi đi qua `TransactionalOperator` trước. Transaction manager có cơ hội rollback; sau đó `onErrorResume` phía downstream mới tạo kết quả dự phòng. Consumer vẫn nhận một giá trị nhưng transaction gốc đã thất bại.

Quy tắc lựa chọn:

- Đặt recovery bên trong transaction nếu lỗi là một nhánh nghiệp vụ có thể phục hồi và vẫn muốn commit phần thay đổi hợp lệ.
- Đặt recovery bên ngoài transaction nếu lỗi phải làm transaction rollback nhưng API vẫn cần trả fallback.
- Nếu cần tiếp tục pipeline nhưng chắc chắn rollback, đánh dấu rollback-only hoặc dùng một ranh giới transaction rõ ràng; đừng dựa vào việc log lỗi rồi trả `Mono.empty()`.

`onErrorComplete` và `onErrorReturn` cũng có thể làm lỗi biến mất trước ranh giới transaction. Hãy xem xét toàn bộ thứ tự operator thay vì chỉ nhìn một callback lỗi.

## 6. Cancellation trong transaction có thể rollback dù downstream đã nhận phần tử

Với `Flux`, downstream có thể nhận một phần tử rồi hủy subscription. Ví dụ `take(1)` phát completion cho consumer nhưng hủy publisher transactional upstream:

~~~java
Flux<OrderEvent> firstEvent = orderEventService.eventsInTransaction()
    .take(1);
~~~

Nếu `eventsInTransaction()` bọc một transaction bằng `TransactionalOperator`, việc `take(1)` hủy upstream có thể kích hoạt nhánh cancellation và rollback transaction. Consumer cuối nhìn thấy `onComplete` vì `take(1)` đã nhận đủ một phần tử, nhưng publisher transactional upstream không hoàn tất bình thường.

Điều này có ý nghĩa khi transaction bao quanh luồng nhiều phần tử. Không giả định rằng việc downstream đã nhận một phần dữ liệu đồng nghĩa transaction đã commit. Transaction chỉ được commit khi publisher nằm trong ranh giới transaction hoàn tất bình thường.

### Tránh transaction kéo dài quanh stream không giới hạn

Không nên giữ transaction database mở trong khi phát một `Flux` vô hạn hoặc một luồng phụ thuộc tốc độ client:

~~~java
// Không phù hợp nếu eventStream là luồng sống lâu.
Flux<Event> events = eventStream
    .as(transactionalOperator::transactional);
~~~

Transaction có thể giữ connection, lock hoặc snapshot database trong thời gian dài. Client chậm hoặc ngắt kết nối muộn có thể khiến tài nguyên bị giữ lâu hơn dự kiến. Thay vào đó, dùng transaction ngắn cho từng thao tác ghi/đọc cần tính nhất quán, rồi phát dữ liệu sau khi transaction đã kết thúc.

Ví dụ xử lý từng event trong transaction riêng:

~~~java
Flux<ProcessedEvent> processed = eventStream.concatMap(event ->
    processOne(event)
        .as(transactionalOperator::transactional)
);
~~~

`concatMap` tuần tự hóa việc xử lý từng event trong ví dụ. Nếu nghiệp vụ cho phép xử lý đồng thời, có thể chọn giới hạn concurrency với operator phù hợp, nhưng phải xác minh transaction và connection pool chịu được mức đồng thời đó.

## 7. Transaction context không gắn với một thread

Spring reactive transaction sử dụng Reactor Context để gắn transaction resource, chẳng hạn R2DBC Connection, với subscription. Vì vậy, các repository reactive trong cùng pipeline có thể tham gia transaction dù pipeline chuyển scheduler:

~~~java
Mono<Order> result = orderRepository.save(order)
    .publishOn(Schedulers.parallel())
    .then(outboxRepository.save(event))
    .as(transactionalOperator::transactional);
~~~

Reactor Context theo subscription chứ không theo ThreadLocal. Tuy nhiên, điều đó không có nghĩa mọi API imperative đều tự tham gia reactive transaction. JDBC hoặc một thư viện blocking dùng transaction ThreadLocal riêng không tự động dùng chung R2DBC transaction.

Không gọi `subscribe()` bên trong một phương thức nghiệp vụ đang chạy trong transaction:

~~~java
// Không làm như sau trong service transactional.
Mono<Void> createOrder(Order order) {
    orderRepository.save(order).subscribe();
    return Mono.empty();
}
~~~

Lệnh `subscribe()` tạo subscription độc lập, tách khỏi transaction context và lifecycle mà caller quản lý. Phương thức có thể trả về trước khi thao tác database hoàn tất; lỗi và cancellation cũng không còn được nối đúng với caller. Hãy compose publisher và trả nó về:

~~~java
Mono<Void> createOrder(Order order) {
    return orderRepository.save(order).then();
}
~~~

Nếu cần chạy công việc nền độc lập, hãy tạo ranh giới xử lý và transaction riêng có owner rõ ràng, thay vì tách subscription ngầm.

## 8. Dùng @Transactional cho phương thức reactive

Spring hỗ trợ khai báo transaction bằng `@Transactional` trên phương thức trả về kiểu reactive như `Mono` hoặc `Flux`, khi ứng dụng cấu hình `ReactiveTransactionManager` phù hợp:

~~~java
@Transactional
public Mono<Order> createOrder(Order order) {
    return orderRepository.save(order)
        .flatMap(saved -> outboxRepository.save(toEvent(saved))
            .thenReturn(saved));
}
~~~

Spring sử dụng reactive transaction infrastructure để quản lý transaction theo subscription. Hãy bảo đảm bean dùng đúng reactive transaction manager (ví dụ R2DBC) và method thực sự trả publisher. Một transaction manager imperative dành cho JDBC không thể thay thế reactive transaction manager chỉ vì phương thức có annotation.

`@Transactional` dựa trên cơ chế proxy trong cấu hình Spring thông thường. Gọi một phương thức transactional khác qua `this` trong cùng object có thể bỏ qua proxy, nên transaction annotation không được áp dụng như mong đợi. Nếu cần ranh giới transaction rõ ràng trong cùng class, có thể tách service hoặc dùng `TransactionalOperator`.

Không gọi `block()` trong phương thức reactive transactional. Blocking làm mất lợi ích non-blocking và có thể gây deadlock hoặc chiếm event-loop. Hãy trả `Mono`/`Flux` xuyên suốt call chain.

## 9. Retry nên tạo transaction mới cho mỗi lần thử

Retry có thể subscribe lại publisher. Khi retry liên quan đến thao tác database, cần quyết định mỗi lần thử có dùng transaction mới không.

Một mẫu thường dễ kiểm soát là đặt transaction bên trong publisher được tạo cho mỗi lần thử, rồi retry bên ngoài:

~~~java
Mono<Order> createWithRetry(Order order) {
    return Mono.defer(() ->
            orderRepository.save(order)
                .then(outboxRepository.save(toEvent(order)))
                .thenReturn(order)
                .as(transactionalOperator::transactional)
        )
        .retryWhen(Retry.max(2));
}
~~~

Mỗi lần subscribe lại vào `Mono.defer`, pipeline transaction được tạo và thực thi cho lần thử đó. Nếu lần trước lỗi, transaction của lần đó được rollback trước khi retry tiếp tục theo semantics của operator. Điều này tránh việc cố gắng tiếp tục dùng một transaction đã ở trạng thái lỗi.

Không retry mù mọi exception. Lỗi validation, lỗi constraint vĩnh viễn hoặc lỗi nghiệp vụ thường không thể khắc phục bằng thử lại. Retry chỉ phù hợp với lỗi tạm thời và thao tác có thể thực hiện lại an toàn. Với lệnh ghi có side effect, cần idempotency key hoặc khóa nghiệp vụ để tránh tạo dữ liệu trùng khi kết quả commit không rõ.

## 10. Transaction không bao trùm dịch vụ bên ngoài

Một transaction R2DBC chỉ quản lý tài nguyên thuộc transaction manager và resource được enlist vào transaction đó. Gọi HTTP sang dịch vụ thanh toán, gửi email hoặc publish message đến broker không tự động trở thành một phần của transaction database.

Ví dụ:

~~~java
Mono<Order> unsafeFlow = orderRepository.save(order)
    .then(paymentClient.charge(order.payment()))
    .thenReturn(order)
    .as(transactionalOperator::transactional);
~~~

Nếu payment service đã thu tiền nhưng thao tác database sau đó lỗi, rollback database không tự hoàn tiền. Ngược lại, database có thể commit trong khi message/email không được gửi. Một transaction cục bộ không thể bảo đảm atomicity giữa các hệ thống độc lập.

Với tích hợp event, có thể dùng transactional outbox: ghi dữ liệu nghiệp vụ và bản ghi outbox trong cùng database transaction, sau đó một publisher riêng đọc outbox và gửi message. Với quy trình nhiều dịch vụ, cân nhắc saga và các hành động bù trừ.

~~~java
Mono<Order> createOrder(Order order) {
    return orderRepository.save(order)
        .flatMap(saved ->
            outboxRepository.save(OrderCreatedEvent.from(saved))
                .thenReturn(saved)
        )
        .as(transactionalOperator::transactional);
}
~~~

Transaction bảo đảm order và outbox record cùng commit hoặc cùng rollback. Việc chuyển outbox record thành message là một bước riêng, cần retry và idempotency ở consumer.

## 11. Lỗi trong commit hoặc rollback

Commit và rollback cũng là thao tác I/O có thể thất bại. Ví dụ, kết nối bị đứt đúng lúc gửi commit khiến ứng dụng không biết database đã commit hay chưa. Đây là trạng thái kết quả không xác định, không thể luôn coi là rollback.

Khi commit/rollback lỗi:

- Giữ exception gốc và thông tin lỗi cleanup nếu transaction manager cung cấp.
- Ghi correlation ID, transaction/operation ID và loại thao tác.
- Không tự retry lệnh ghi nếu không biết lần trước đã commit hay chưa.
- Dùng idempotency key hoặc truy vấn trạng thái theo khóa nghiệp vụ để đối soát.
- Theo dõi connection pool và trạng thái tài nguyên để phát hiện connection không được trả lại.

Nếu rollback thất bại sau một lỗi nghiệp vụ, lỗi cleanup có thể được gắn thêm hoặc ảnh hưởng exception cuối cùng tùy transaction manager. Cần đọc log và exception chain thay vì chỉ ghi nhận message ngoài cùng.

## 12. Kiểm thử complete, error và cancellation

`StepVerifier` kiểm tra tín hiệu của pipeline, nhưng để xác minh commit/rollback thực tế cần kiểm tra database sau khi subscription kết thúc. Nên dùng integration test với database/driver tương thích môi trường ứng dụng; mock repository đơn thuần không chứng minh transaction manager đã commit hoặc rollback.

### Kiểm tra commit khi hoàn tất

~~~java
Mono<Order> transaction = orderRepository.save(order)
    .as(transactionalOperator::transactional);

StepVerifier.create(transaction)
    .expectNextMatches(saved -> saved.id() != null)
    .verifyComplete();

StepVerifier.create(orderRepository.findById(order.id()))
    .expectNextCount(1)
    .verifyComplete();
~~~

Test xác minh pipeline complete và dữ liệu tồn tại sau transaction. Trong test thật, dùng ID do database sinh hoặc lấy từ giá trị saved để truy vấn đúng bản ghi.

### Kiểm tra rollback khi có lỗi

~~~java
Mono<Order> transaction = orderRepository.save(order)
    .then(Mono.error(new IllegalStateException("forced failure")))
    .as(transactionalOperator::transactional);

StepVerifier.create(transaction)
    .expectError(IllegalStateException.class)
    .verify();

StepVerifier.create(orderRepository.findById(order.id()))
    .verifyComplete();
~~~

Test cần bảo đảm lỗi xảy ra sau khi lệnh insert đã chạy và truy vấn kiểm tra được thực hiện ngoài transaction thất bại. Nếu test framework tự bọc test trong một transaction, hãy tránh để transaction test che khuất kết quả commit/rollback mà test đang muốn xác minh.

### Kiểm tra rollback khi downstream hủy

~~~java
Flux<Integer> transaction = orderRepository.save(order)
    .thenMany(Flux.concat(
        Flux.just(1),
        Flux.<Integer>never()
    ))
    .as(transactionalOperator::transactional);

StepVerifier.create(transaction)
    .expectNext(1)
    .thenCancel()
    .verify();

StepVerifier.create(orderRepository.findById(order.id()))
    .verifyComplete();
~~~

Publisher phát một phần tử sau khi insert rồi không hoàn tất. Downstream hủy sau phần tử đó; transaction manager cần rollback transaction theo cancellation semantics. Integration test cần xác minh bản ghi không tồn tại sau cleanup. Không chỉ kiểm tra `doOnCancel`, vì hook đó không chứng minh database đã rollback.

### Kiểm tra recovery operator placement

Viết hai test riêng cho:

1. `onErrorResume` nằm trước `transactional`: xác minh transaction có thể commit nếu lỗi được chuyển thành completion và không bị đánh dấu rollback-only.
2. `onErrorResume` nằm sau `transactional`: xác minh transaction rollback trước khi fallback phát kết quả.

Đây là test có giá trị vì thứ tự operator thay đổi kết quả dữ liệu dù consumer có thể nhận cùng một fallback.

## 13. Những lỗi thường gặp

- **Cho rằng chỉ onError mới rollback:** cancellation cũng cần được xử lý như một nhánh kết thúc transaction.
- **Nhầm completion downstream với completion transactional upstream:** `take(1)` có thể complete cho consumer nhưng cancel publisher transaction.
- **Phục hồi lỗi trước transaction mà vẫn mong rollback:** transaction manager chỉ thấy completion nếu lỗi đã bị chuyển thành giá trị/empty.
- **Dùng doOnError như cơ chế phục hồi:** hook chỉ quan sát lỗi, không thay đổi terminal signal.
- **Dùng onErrorComplete để che lỗi ghi dữ liệu:** transaction có thể commit nếu lỗi bị nuốt trước ranh giới transaction.
- **Retry bên trong transaction đã lỗi:** có thể tiếp tục trên transaction không còn hợp lệ; cân nhắc tạo transaction mới cho từng lần thử.
- **Giữ transaction quanh Flux vô hạn:** connection, lock và snapshot có thể bị giữ lâu.
- **Gọi subscribe() hoặc block() trong service transactional:** tạo lifecycle độc lập hoặc phá mô hình non-blocking.
- **Dùng JDBC và R2DBC như cùng một transaction:** hai transaction manager không tự chia sẻ transaction context.
- **Giả định HTTP/email/broker nằm trong transaction database:** side effect bên ngoài cần outbox, saga hoặc compensation.
- **Retry khi commit không rõ kết quả:** có thể thực hiện side effect hai lần; cần idempotency và đối soát.
- **Chỉ test tín hiệu mà không kiểm tra dữ liệu:** verifyComplete() không chứng minh database đã commit đúng.

## 14. Checklist thiết kế transaction reactive

Trước khi hoàn thiện pipeline, hãy xác định:

1. Publisher nào nằm trong transaction boundary?
2. Complete, error và cancel được transaction manager xử lý ra sao?
3. onErrorResume, onErrorComplete hoặc retryWhen nằm ở phía nào của boundary?
4. Cancellation có thể xảy ra sau khi downstream đã nhận một phần dữ liệu không?
5. Luồng có hữu hạn và transaction có thời gian sống ngắn không?
6. Các thao tác database có dùng cùng reactive transaction manager và Context không?
7. Có lệnh blocking, subscribe() hoặc block() nào tách khỏi subscription không?
8. Retry có tạo transaction mới và có an toàn/idempotent không?
9. Có side effect bên ngoài cần outbox hoặc compensation không?
10. Integration test đã xác minh commit, rollback do error và rollback do cancel chưa?
11. Lỗi commit/rollback có thể được đối soát bằng operation ID hay không?

Transaction reactive gắn với lifecycle của subscription. Hoàn tất bình thường thường dẫn đến commit; lỗi dẫn đến rollback; cancellation cũng kích hoạt nhánh rollback và cleanup của reactive transaction manager. Vị trí onErrorResume, retryWhen và các operator kết thúc sớm có thể thay đổi kết quả transaction dù consumer nhìn thấy cùng một giá trị hoặc completion. Hãy giữ transaction ngắn, để transaction context đi cùng publisher, tránh tách subscription, tách side effect bên ngoài bằng outbox/saga và kiểm thử trực tiếp dữ liệu đã commit hoặc rollback. Điều đó giúp pipeline giữ được tính nhất quán khi hoàn tất, gặp lỗi hoặc bị hủy giữa chừng.
