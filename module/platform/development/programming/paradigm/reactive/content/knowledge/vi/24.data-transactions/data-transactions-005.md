# TransactionalOperator và giao dịch phản ứng trong Spring

Trong module `REACTIVE_PROGRAMMING`, ta xây dựng các luồng bất đồng bộ theo hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams, đồng thời thực hành `Mono`, `Flux`, kết hợp toán tử, scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Khi một nghiệp vụ cần ghi nhiều bản ghi hoặc cập nhật nhiều bảng, ta thường cần bảo đảm các thao tác cùng thành công hoặc cùng được hoàn tác. Với ứng dụng dùng API dữ liệu reactive như R2DBC, Spring cung cấp `TransactionalOperator` để đặt ranh giới transaction trực tiếp quanh một Publisher.

`TransactionalOperator` là abstraction lập trình transaction theo kiểu reactive. Nó làm việc với một `ReactiveTransactionManager`, mở transaction khi có subscription, đưa ngữ cảnh transaction vào pipeline, rồi commit hoặc rollback theo kết quả kết thúc của Publisher. Cách dùng này cho phép ghép nhiều thao tác repository thành một đơn vị nghiệp vụ mà không phải chặn thread để chờ từng lệnh.

## 1. Giao dịch phản ứng khác giao dịch imperative ở đâu?

Trong mã imperative, một transaction thường được mở, các lệnh database chạy tuần tự trên thread hiện tại, rồi commit hoặc rollback trước khi phương thức trả về. Với reactive pipeline, một phương thức thường trả về `Mono` hoặc `Flux`; công việc chỉ bắt đầu khi Publisher được subscribe và có thể tiếp tục qua nhiều thread hoặc scheduler.

Do đó, transaction reactive cần gắn với **subscription context** thay vì dựa vào `ThreadLocal` của một thread cố định. Spring quản lý tài nguyên transaction và liên kết chúng với Reactor Context để các thao tác dữ liệu trong cùng pipeline có thể tham gia cùng transaction.

| Khía cạnh | Transaction imperative | Transaction reactive |
|---|---|---|
| API quản lý | `PlatformTransactionManager`, `@Transactional` trên luồng imperative | `ReactiveTransactionManager`, `TransactionalOperator` hoặc `@Transactional` trên reactive return type |
| Vòng đời | Theo lời gọi phương thức đồng bộ | Theo subscription và tín hiệu kết thúc Publisher |
| Ngữ cảnh | Thường gắn với thread | Gắn với Reactor Context của subscription |
| Kiểu kết quả | Giá trị hoặc exception | `Mono`, `Flux` và tín hiệu `onComplete`/`onError` |
| Tài nguyên | Connection được giữ trong phạm vi lời gọi transaction | Connection reactive được liên kết với reactive transaction context |
| Rủi ro chính | Giữ transaction quá lâu hoặc quên rollback | Tách subscription, block, mất context ở ranh giới ngoài pipeline hoặc giữ connection quá lâu |

Reactive transaction không làm database trở nên non-blocking nếu driver bên dưới là JDBC đồng bộ. Với R2DBC, thao tác database dùng API non-blocking và phù hợp hơn với pipeline reactive. Cần dùng đúng loại transaction manager cho loại tài nguyên; không thể lấy `R2dbcTransactionManager` để quản lý một JDBC `DataSource` thông thường.

## 2. Các thành phần của transaction reactive trong Spring

Các abstraction chính gồm:

- `ReactiveTransactionManager`: hợp đồng quản lý transaction cho tài nguyên reactive.
- `R2dbcTransactionManager`: implementation quản lý transaction cho một R2DBC `ConnectionFactory`.
- `TransactionalOperator`: lớp điều phối ranh giới transaction theo Publisher.
- `TransactionDefinition`: mô tả thuộc tính transaction như propagation, isolation, timeout và read-only.
- `TransactionStatus`: cho phép kiểm soát trạng thái transaction, ví dụ đánh dấu rollback-only trong callback.

Với ứng dụng Spring dùng R2DBC, cấu hình thường có dạng:

```java
@Configuration
class TransactionConfiguration {

    @Bean
    ReactiveTransactionManager transactionManager(ConnectionFactory connectionFactory) {
        return new R2dbcTransactionManager(connectionFactory);
    }

    @Bean
    TransactionalOperator transactionalOperator(
            ReactiveTransactionManager transactionManager) {
        return TransactionalOperator.create(transactionManager);
    }
}
```

`ConnectionFactory` ở đây phải là factory mà các repository cần tham gia transaction cùng sử dụng. Nếu các repository dùng những connection factory hoặc transaction manager khác nhau, một `TransactionalOperator` không tự tạo ra transaction phân tán bao trùm tất cả tài nguyên đó.

Trong Spring Boot, nhiều cấu hình có thể được auto-configure theo dependency và bean hiện có. Hãy kiểm tra transaction manager thực tế được inject, tránh khai báo trùng hoặc vô tình chọn nhầm manager khi ứng dụng có cả JDBC và R2DBC.

## 3. Bọc một Publisher bằng `transactional`

Cách đơn giản nhất là tạo chuỗi thao tác reactive rồi bọc bằng `TransactionalOperator.transactional`:

```java
Mono<Order> createOrder(CreateOrder command) {
    Mono<Order> work = orderRepository.save(Order.from(command))
        .flatMap(saved -> inventoryRepository.reserve(
            saved.sku(), saved.quantity()
        ).thenReturn(saved))
        .flatMap(saved -> auditRepository.recordCreated(saved.id())
            .thenReturn(saved));

    return transactionalOperator.transactional(work);
}
```

Khi có subscription, Spring bắt đầu transaction trước khi chạy `work`. Các thao tác `orderRepository`, `inventoryRepository` và `auditRepository` có thể cùng tham gia transaction nếu chúng dùng cùng reactive transaction manager và tài nguyên được quản lý. Nếu toàn bộ Publisher hoàn tất thành công, transaction được commit. Nếu một thao tác phát `onError`, transaction được rollback theo chính sách mặc định của manager.

Có thể dùng toán tử `as` để đặt ranh giới rõ ở cuối chuỗi:

```java
Mono<Order> createOrder(CreateOrder command) {
    return orderRepository.save(Order.from(command))
        .flatMap(saved -> inventoryRepository.reserve(
            saved.sku(), saved.quantity()
        ).thenReturn(saved))
        .as(transactionalOperator::transactional);
}
```

`as(transactionalOperator::transactional)` chỉ là cách viết khác để áp dụng operator lên Publisher hiện tại. Ranh giới transaction bao phủ phần Publisher nằm trước nó trong chuỗi.

## 4. Transaction với `Flux` và nhiều bản ghi

`TransactionalOperator` cũng có thể bọc một `Flux`. Transaction được giữ trong suốt thời gian Publisher nằm trong ranh giới được tiêu thụ và kết thúc theo tín hiệu terminal của Publisher.

```java
Flux<SavedOrder> saveOrders(Flux<CreateOrder> commands) {
    return commands
        .concatMap(command -> orderRepository.save(Order.from(command)))
        .as(transactionalOperator::transactional);
}
```

Trong ví dụ, tất cả lệnh save thuộc một transaction. Nếu phần tử thứ mười phát lỗi sau khi chín phần tử đầu đã được ghi, transaction có thể rollback các thay đổi trước đó trong cùng transaction. Điều này phù hợp khi toàn bộ batch là một đơn vị nguyên tử.

Tuy nhiên, transaction bao trùm một `Flux` dài hoặc vô hạn có thể giữ connection và khóa quá lâu. Với nguồn không hoàn tất, transaction có thể không bao giờ commit. Với batch lớn, thời gian giữ connection có thể gây cạn pool hoặc làm tăng tranh chấp khóa.

Nếu cần chia batch thành các đơn vị commit độc lập, hãy đặt transaction bên trong từng batch:

```java
Flux<List<SavedOrder>> saveInBatches(Flux<CreateOrder> commands) {
    return commands
        .buffer(100)
        .concatMap(batch -> Flux.fromIterable(batch)
            .concatMap(command -> orderRepository.save(Order.from(command)))
            .collectList()
            .as(transactionalOperator::transactional));
}
```

Mỗi batch tối đa 100 bản ghi được xử lý trong một transaction riêng. Nếu một batch lỗi, batch đó rollback; những batch đã commit trước đó vẫn giữ kết quả. Đây là ngữ nghĩa khác với một transaction duy nhất bao trùm toàn bộ luồng. Chọn cách nào phải dựa trên yêu cầu nguyên tử của nghiệp vụ.

## 5. Dùng `execute` để truy cập `TransactionStatus`

Khi cần chủ động đánh dấu rollback-only hoặc kiểm soát transaction theo kết quả nghiệp vụ, có thể dùng `execute`:

```java
Mono<Order> createIfAllowed(CreateOrder command) {
    return transactionalOperator.execute(status ->
        orderRepository.save(Order.from(command))
            .flatMap(saved -> {
                if (saved.total().signum() <= 0) {
                    status.setRollbackOnly();
                }
                return Mono.just(saved);
            })
    ).single();
}
```

`execute` nhận callback với `TransactionStatus` và trả về một `Flux` chứa các giá trị callback phát ra. Trong ví dụ, `.single()` chuyển kết quả thành `Mono<Order>` vì callback được kỳ vọng phát đúng một Order. Nếu status được đánh dấu rollback-only, transaction không commit dù callback hoàn tất bình thường. Tùy cấu hình và transaction manager, caller có thể nhận kết quả callback nhưng thay đổi database vẫn bị rollback; hãy thiết kế kiểu kết quả nghiệp vụ để thể hiện rõ trường hợp này.

Không nên đánh dấu rollback-only một cách tùy tiện sau khi đã phát dữ liệu thành công cho client. Với một `Flux` có nhiều phần tử, downstream có thể đã quan sát một số giá trị trước khi transaction cuối cùng rollback. Nếu cần bảo đảm client chỉ nhận dữ liệu sau khi commit, cân nhắc thu thập một kết quả hữu hạn hoặc thiết kế giao thức xác nhận riêng.

## 6. Commit, rollback và tín hiệu reactive

Vòng đời transaction reactive gắn với kết quả của Publisher:

| Tín hiệu/kết quả | Hành vi transaction thường gặp |
|---|---|
| Publisher hoàn tất bình thường | Commit nếu transaction chưa bị đánh dấu rollback-only |
| Publisher phát `onError` | Rollback theo quy tắc rollback của transaction manager |
| Transaction được đánh dấu rollback-only | Rollback dù Publisher hoàn tất bình thường |
| Subscription bị cancel | Spring reactive transaction xử lý cancellation theo chính sách rollback; cần kiểm thử với loại Publisher và framework version đang dùng |

Với `Mono`, kết quả thường chỉ có tối đa một phần tử rồi hoàn tất. Với `Flux`, nhiều phần tử có thể được phát trước khi transaction kết thúc. Vì vậy, không nên coi việc nhận một phần tử từ Flux là bằng chứng transaction đã commit.

Cancellation là một điểm đặc biệt. Khi subscriber hủy, transaction reactive cần giải phóng tài nguyên và Spring có thể rollback thay vì commit. Điều này quan trọng với HTTP streaming hoặc client ngắt kết nối giữa chừng. Không được dựa vào việc client đã nhận một phần response để kết luận toàn bộ transaction đã thành công.

## 7. Vị trí xử lý lỗi quyết định transaction có commit hay rollback

Một lỗi chỉ có thể kích hoạt rollback nếu nó được nhìn thấy tại ranh giới transaction hoặc transaction đã được đánh dấu rollback-only. Cách đặt `onErrorResume` rất quan trọng.

**Phục hồi sau ranh giới transaction:**

```java
Mono<Order> result = transactionalOperator
    .transactional(saveOrderAndReserveInventory(command))
    .onErrorResume(error -> fallbackOrderResult(error));
```

Trong trường hợp này, lỗi đi qua `TransactionalOperator` trước. Transaction có cơ hội rollback; sau đó `onErrorResume` ở downstream tạo kết quả thay thế cho caller.

**Phục hồi bên trong ranh giới transaction:**

```java
Mono<Order> result = transactionalOperator.transactional(
    saveOrderAndReserveInventory(command)
        .onErrorResume(error -> Mono.just(Order.pendingReview(command)))
);
```

Ở ví dụ thứ hai, lỗi được chuyển thành một giá trị trước khi đến `TransactionalOperator`. Operator có thể thấy Publisher hoàn tất bình thường và commit các thay đổi trước đó. Điều này có thể đúng nếu nghiệp vụ thực sự muốn giữ những thay đổi đã thực hiện, nhưng có thể gây dữ liệu dở dang nếu ý định là rollback toàn bộ.

Nếu cần ghi nhận lỗi nhưng vẫn rollback, có thể để lỗi tiếp tục truyền ra khỏi ranh giới transaction hoặc đánh dấu `rollbackOnly` trong callback `execute` trước khi chuyển lỗi thành kết quả. Hãy phân biệt lỗi nghiệp vụ được phép phục hồi với lỗi vận hành cần rollback.

## 8. Transaction context và ranh giới thread

Spring reactive transaction dùng Reactor Context để liên kết tài nguyên với subscription. Các thao tác repository trong cùng pipeline có thể tham gia transaction ngay cả khi scheduler chuyển callback sang thread khác, miễn là chúng tiếp tục trong cùng reactive subscription/context và dùng đúng transaction manager.

```java
Mono<Order> result = orderRepository.save(order)
    .publishOn(Schedulers.parallel())
    .flatMap(saved -> orderLineRepository.saveAll(linesFor(saved)))
    .as(transactionalOperator::transactional);
```

`publishOn` chuyển tín hiệu downstream sang worker của `parallel`, nhưng Context của Reactor vẫn đi theo subscription. Điều đó cho phép reactive transaction context tiếp tục được nhìn thấy qua ranh giới scheduler.

Tuy nhiên, không nên gọi `.block()`, tự gọi `.subscribe()` bên trong transaction hoặc chuyển công việc sang một thread/Executor độc lập rồi mong nó tự tham gia transaction. Những hành động này có thể tạo subscription khác, không còn cùng Context và transaction. Nếu cần chạy công việc đồng thời, hãy ghép các Publisher bằng `flatMap`, `concatMap`, `zip` hoặc toán tử phù hợp trong cùng pipeline.

Transaction reactive cũng không làm một lời gọi JDBC blocking tự động tham gia cùng R2DBC transaction. Nếu một service gọi cả R2DBC lẫn JDBC, hai tài nguyên có transaction manager riêng và không tự tạo thành một transaction nguyên tử.

## 9. Cấu hình propagation, isolation, timeout và read-only

`TransactionalOperator.create(manager)` dùng transaction definition mặc định của Spring. Khi cần thuộc tính riêng, có thể tạo `DefaultTransactionDefinition`:

```java
DefaultTransactionDefinition definition = new DefaultTransactionDefinition();
definition.setName("create-order");
definition.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);
definition.setIsolationLevel(TransactionDefinition.ISOLATION_READ_COMMITTED);
definition.setTimeout(10);

TransactionalOperator orderTransaction =
    TransactionalOperator.create(transactionManager, definition);
```

Các thuộc tính cần hiểu đúng:

- **Propagation** xác định cách một transaction mới tham gia hoặc tương tác với transaction hiện có. `PROPAGATION_REQUIRED` thường tham gia transaction hiện tại nếu có, nếu không thì tạo mới.
- **Isolation** xác định mức cô lập mà transaction yêu cầu. Khả năng thực thi và ý nghĩa cụ thể còn phụ thuộc database.
- **Timeout** đặt giới hạn thời gian transaction theo hỗ trợ của transaction manager và driver. Đây không thay thế timeout cho từng HTTP request hoặc lời gọi dịch vụ.
- **Read-only** là gợi ý/thuộc tính transaction mà database hoặc driver có thể hỗ trợ ở các mức khác nhau; không nên coi nó là cơ chế bảo mật ngăn mọi lệnh ghi.

Ví dụ transaction đọc:

```java
DefaultTransactionDefinition readDefinition = new DefaultTransactionDefinition();
readDefinition.setReadOnly(true);
readDefinition.setTimeout(5);

TransactionalOperator readOnlyOperator =
    TransactionalOperator.create(transactionManager, readDefinition);

Mono<Order> order = orderRepository.findById(orderId)
    .as(readOnlyOperator::transactional);
```

Đặt thuộc tính transaction cần dựa trên yêu cầu nghiệp vụ và khả năng của database. Isolation cao hơn có thể làm tăng khóa hoặc giảm concurrency; timeout quá ngắn có thể gây rollback ở tải bình thường; read-only không thay thế quyền database.

## 10. Tương tác với `@Transactional` trong Spring

Spring hỗ trợ `@Transactional` cho phương thức trả về reactive type khi có `ReactiveTransactionManager` phù hợp. Với reactive method, transaction được quản lý theo subscription của Publisher được trả về, không đơn thuần theo thời điểm method Java kết thúc.

```java
@Service
class OrderService {

    @Transactional
    public Mono<Order> create(CreateOrder command) {
        return orderRepository.save(Order.from(command))
            .flatMap(saved -> inventoryRepository.reserve(
                saved.sku(), saved.quantity()
            ).thenReturn(saved));
    }
}
```

Khi Spring gọi phương thức qua proxy và reactive transaction manager được cấu hình, transaction reactive bao quanh Publisher được trả về. Lưu ý các quy tắc proxy thông thường vẫn áp dụng: self-invocation không đi qua proxy có thể khiến annotation không được áp dụng như mong đợi. Cũng cần bảo đảm phương thức thực sự trả về reactive type; một phương thức `void` hoặc giá trị đồng bộ không trở thành reactive transaction chỉ vì đặt annotation.

`TransactionalOperator` hữu ích khi muốn đặt ranh giới tường minh trong pipeline, chọn transaction definition tại chỗ hoặc kiểm soát `TransactionStatus`. `@Transactional` hữu ích khi transaction là thuộc tính ổn định của một service method. Không nên lồng hai cơ chế một cách tùy tiện; hãy xác định rõ propagation và manager được sử dụng.

## 11. Giới hạn của transaction: không bao trùm side effect bên ngoài

Transaction database chỉ quản lý tài nguyên được transaction manager đó điều khiển. Nếu pipeline cập nhật database rồi gọi HTTP để gửi email hoặc trừ tiền ở một dịch vụ khác, rollback database không thể thu hồi side effect đã xảy ra ở hệ thống ngoài.

```java
Mono<Order> unsafeFlow = transactionalOperator.transactional(
    orderRepository.save(order)
        .flatMap(saved -> emailClient.sendConfirmation(saved)
            .thenReturn(saved))
);
```

Nếu email đã được gửi nhưng bước sau đó phát lỗi, database có thể rollback trong khi email vẫn tồn tại. Giữ một HTTP call lâu bên trong transaction cũng làm connection và khóa database bị giữ trong thời gian chờ mạng.

Với side effect phân tán, cân nhắc Transactional Outbox:

1. Trong cùng transaction database, lưu thay đổi nghiệp vụ và một outbox event.
2. Một publisher riêng đọc outbox và gửi event đến hệ thống ngoài.
3. Nếu gửi thất bại hoặc không nhận được xác nhận, publisher có thể gửi lại.
4. Consumer dùng event ID hoặc idempotency key để xử lý trùng an toàn.

Outbox thường cung cấp giao ít nhất một lần; consumer vẫn cần idempotency. `TransactionalOperator` bảo đảm tính nguyên tử cho các thao tác thuộc transaction manager hiện tại, không tạo transaction phân tán tự động.

## 12. Kiểm thử commit và rollback

Kiểm thử operator bằng mock có thể xác nhận pipeline phát tín hiệu đúng, nhưng để chứng minh rollback thực sự, cần kiểm thử tích hợp với database và driver reactive. Một kịch bản điển hình là ghi một bản ghi, cố ý phát lỗi ở thao tác tiếp theo, rồi truy vấn lại để xác nhận bản ghi đầu không còn.

Ví dụ cấu trúc test với repository reactive:

```java
@Test
void rollsBackWhenSecondWriteFails() {
    Mono<Void> work = orderRepository.save(order)
        .then(Mono.error(new IllegalStateException("force rollback")));

    StepVerifier.create(transactionalOperator.transactional(work))
        .expectError(IllegalStateException.class)
        .verify();

    StepVerifier.create(orderRepository.findById(order.id()))
        .verifyComplete();
}
```

Ví dụ minh họa cần chạy trong test integration có R2DBC database thật hoặc Testcontainers, và không nên để test framework bọc toàn bộ test trong một transaction khác làm sai kết quả quan sát. Tùy database, cần chờ Publisher truy vấn hoàn tất trước khi đánh giá trạng thái.

Kiểm thử commit thành công:

```java
StepVerifier.create(
        transactionalOperator.transactional(orderRepository.save(order))
    )
    .expectNextMatches(saved -> saved.id().equals(order.id()))
    .verifyComplete();

StepVerifier.create(orderRepository.findById(order.id()))
    .expectNextCount(1)
    .verifyComplete();
```

Ngoài commit/rollback, nên kiểm thử:

- Lỗi phát sinh ở từng bước trong transaction.
- Publisher hoàn tất rỗng và chính sách nghiệp vụ tương ứng.
- `onErrorResume` đặt trong và ngoài ranh giới transaction.
- Cancellation khi subscriber dừng tiêu thụ `Flux`.
- Timeout, isolation và propagation theo database được sử dụng.
- Nhiều thao tác repository có cùng tham gia một transaction manager hay không.

## 13. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng `R2dbcTransactionManager` cho repository JDBC | JDBC không tham gia transaction R2DBC | Dùng transaction manager đúng loại tài nguyên |
| Gọi `.block()` trong transaction reactive | Chặn thread và có thể tách khỏi ngữ cảnh reactive | Ghép Publisher bằng toán tử |
| Gọi `.subscribe()` bên trong callback transaction | Tạo subscription độc lập, có thể chạy ngoài transaction | Trả Publisher về pipeline hiện tại |
| Đặt `onErrorResume` bên trong transaction mà quên rollback | Lỗi bị chuyển thành completion và transaction có thể commit | Đặt phục hồi sau operator hoặc đánh dấu rollback-only |
| Bao một `Flux` vô hạn trong transaction | Transaction không hoàn tất, giữ connection quá lâu | Chia thành batch hoặc transaction ngắn |
| Cho rằng nhận `onNext` nghĩa là đã commit | Transaction chỉ kết thúc khi Publisher terminal | Xác nhận commit qua completion hoặc kết quả nghiệp vụ |
| Cho rằng rollback database thu hồi HTTP/email | Side effect ngoài transaction vẫn tồn tại | Dùng outbox, idempotency hoặc saga |
| Dùng nhiều transaction manager nhưng kỳ vọng một transaction chung | Các tài nguyên có thể commit/rollback độc lập | Thiết kế điều phối phân tán rõ ràng |

## 14. Quy trình thiết kế transaction reactive

Khi đặt transaction quanh một pipeline, hãy xác định:

1. **Tài nguyên nào cần nguyên tử?** Liệt kê database và repository phải cùng commit hoặc rollback.
2. **Transaction manager nào sở hữu tài nguyên?** Dùng `ReactiveTransactionManager` tương ứng, ví dụ `R2dbcTransactionManager` cho R2DBC.
3. **Ranh giới Publisher nằm ở đâu?** Bọc đúng chuỗi thao tác bằng `transactional` hoặc đặt `@Transactional` trên reactive service method.
4. **Nguồn có hữu hạn không?** Tránh giữ transaction quanh `Flux` dài hoặc vô hạn; cân nhắc batch nhỏ.
5. **Lỗi được phục hồi ở đâu?** Đảm bảo lỗi cần rollback đi qua ranh giới transaction hoặc đánh dấu rollback-only.
6. **Có side effect ngoài database không?** Tách qua outbox/saga và dùng idempotency ở consumer.
7. **Có giữ cùng subscription/context không?** Không block, không tự subscribe và không tách công việc ra khỏi pipeline.
8. **Đã kiểm thử với database thực tế chưa?** Xác nhận commit, rollback, cancellation và thuộc tính transaction bằng integration test.

`TransactionalOperator` đưa transaction vào mô hình Publisher–Subscriber: transaction bắt đầu khi subscription chạy, các thao tác dữ liệu chia sẻ reactive transaction context, rồi commit hoặc rollback theo tín hiệu kết thúc và trạng thái transaction. Khi chọn đúng transaction manager, giữ ranh giới ngắn, đặt xử lý lỗi đúng vị trí và kiểm thử với driver/database thực tế, ta có thể phối hợp nhiều thao tác dữ liệu reactive thành một đơn vị nghiệp vụ nhất quán mà không chặn thread.
