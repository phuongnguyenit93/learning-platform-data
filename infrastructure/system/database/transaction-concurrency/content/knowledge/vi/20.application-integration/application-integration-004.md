# Ngữ cảnh giao dịch khi đổi luồng, chạy bất đồng bộ hoặc dùng luồng phản ứng

Trong ứng dụng Java, một transaction không chỉ là cặp lệnh `BEGIN` và `COMMIT`. Nó còn gắn với một ngữ cảnh thực thi: transaction manager nào quản lý, connection hoặc session nào đang tham gia, tài nguyên nào đã được đăng ký và thời điểm nào transaction kết thúc. Khi chương trình đổi thread, gửi công việc sang executor, dùng `CompletableFuture` hoặc xử lý bằng reactive stream, ngữ cảnh đó có thể không còn ở nơi mã tiếp theo chạy.

Đây là vấn đề quan trọng khi tích hợp database với bất đồng bộ. Một phương thức được gọi từ bên trong `@Transactional` không có nghĩa mọi công việc được khởi chạy từ phương thức đó tự động tham gia cùng transaction. Cách truyền ngữ cảnh phụ thuộc mô hình giao dịch đang dùng:

- Với giao dịch imperative kiểu JDBC/JPA và Spring `PlatformTransactionManager`, tài nguyên giao dịch thường được gắn với thread hiện tại.
- Với giao dịch reactive trong Spring, ngữ cảnh giao dịch được truyền qua Reactor `Context` trong subscription, nên có thể đi qua các lần chuyển scheduler/thread của cùng reactive chain.
- Với Jakarta Transactions/JTA hoặc container-managed transaction, việc chạy bất đồng bộ tuân theo hợp đồng của container và managed executor; không thể suy ra rằng một `Executor` Java bất kỳ sẽ mang transaction đang hoạt động sang thread khác.

Muốn giữ một đơn vị nghiệp vụ nguyên tử, cần quyết định rõ công việc phải chạy trong cùng transaction, trong một transaction mới độc lập, hay trong một luồng reactive có transaction context riêng. Chọn sai ranh giới có thể làm dữ liệu chưa commit bị đọc quá sớm, thay đổi được commit một phần, hoặc worker xử lý cùng tài nguyên trong khi transaction cha vẫn giữ khóa.

## 1. Transaction context gồm những gì?

Ngữ cảnh giao dịch là tập thông tin mà transaction manager cần để điều phối một đơn vị công việc. Tùy công nghệ, nó có thể gồm:

- Transaction đang hoạt động và trạng thái của nó: active, marked rollback-only, committed hoặc rolled back.
- Connection JDBC, R2DBC connection hoặc session đang được transaction manager quản lý.
- Các tài nguyên đã tham gia transaction như `EntityManager`, Hibernate `Session` hoặc connection holder.
- Isolation level, read-only flag, timeout và các thuộc tính giao dịch.
- Các callback đồng bộ hóa trước/sau commit, rollback hoặc completion.
- Ngữ cảnh truyền qua framework để biết lời gọi tiếp theo thuộc transaction nào.

Không nên đồng nhất transaction context với `ThreadLocal`, connection, MDC hay security context. `ThreadLocal` có thể là cách một framework lưu tham chiếu tài nguyên cho thread hiện tại, nhưng transaction còn có trạng thái và quy tắc điều phối. Sao chép một giá trị `ThreadLocal` sang thread khác không tự biến connection thành tài nguyên an toàn để chia sẻ và cũng không bảo đảm transaction manager quản lý đúng vòng đời.

## 2. Giao dịch imperative trong Spring thường gắn với thread

Với JDBC/JPA và `PlatformTransactionManager`, Spring thường bind tài nguyên giao dịch vào thread hiện tại. Ví dụ khi một phương thức `@Transactional` bắt đầu:

1. Transaction interceptor gọi transaction manager để bắt đầu hoặc tham gia transaction.
2. Transaction manager lấy connection từ pool và bind tài nguyên vào thread hiện tại.
3. Các repository/JDBC operation chạy trên thread đó có thể lấy lại tài nguyên đã bind và tham gia cùng transaction.
4. Khi phương thức kết thúc, interceptor commit hoặc rollback và giải phóng tài nguyên theo quy tắc transaction manager.

Ví dụ đơn giản:

```java
@Service
public class OrderService {
    private final OrderRepository orders;
    private final PaymentRecordRepository payments;

    @Transactional
    public void createOrder(Order order, PaymentRecord payment) {
        orders.save(order);
        payments.save(payment);
        // Hai thao tác tham gia cùng transaction imperative hiện tại.
    }
}
```

Nếu hai repository dùng cùng transaction manager và cùng transaction context, cả hai thay đổi được commit hoặc rollback như một đơn vị. Transaction context được quản lý trong phạm vi thực thi của thread đang chạy `createOrder`.

`@Transactional` là cơ chế khai báo ranh giới transaction thông qua Spring AOP/proxy trong cách cấu hình phổ biến. Annotation không tự gắn transaction vào mọi thread được tạo ra từ phương thức đó.

## 3. Điều gì xảy ra khi chuyển sang thread khác?

Giả sử một phương thức transaction đang chạy trên thread T1 và gửi một tác vụ sang executor để thực hiện cập nhật database:

```java
@Transactional
public void updateOrder(long orderId) {
    orderRepository.updateStatus(orderId, "PROCESSING");

    executor.execute(() -> {
        auditRepository.insert(orderId, "PROCESSING");
    });
}
```

Với transaction imperative gắn thread, tác vụ trong executor thường chạy trên thread T2 và **không tham gia transaction của T1**. Khi `updateOrder` kết thúc, transaction trên T1 có thể commit hoặc rollback độc lập với thao tác audit trên T2.

```text
Thread T1 (caller)                       Thread T2 (executor)
------------------------------------------------------------------
BEGIN transaction
UPDATE order
submit task ---------------------------> bắt đầu task
                                        INSERT audit
                                        COMMIT transaction riêng
COMMIT hoặc ROLLBACK transaction T1
```

Trình tự thực tế có thể khác tùy scheduler, nhưng hai thread có transaction context độc lập. T2 có thể chạy trước khi T1 commit; nếu T2 đọc dữ liệu mà T1 vừa ghi, nó có thể chưa nhìn thấy thay đổi đó, hoặc phải chờ khóa. Nếu T1 rollback, thao tác đã commit độc lập của T2 vẫn tồn tại.

Một số hậu quả thường gặp:

- **Commit một phần:** tác vụ async commit thành công nhưng transaction cha rollback.
- **Đọc dữ liệu chưa commit:** worker chạy trước khi transaction cha commit nên không nhìn thấy bản ghi mới.
- **Chờ khóa:** worker cần cập nhật cùng hàng mà transaction cha đang giữ khóa; worker có thể chờ chính transaction cha.
- **Sai kết quả trả về:** phương thức cha kết thúc và commit trước khi tác vụ async hoàn tất.
- **Lỗi bị bỏ sót:** exception trong tác vụ async không tự động được ném ngược về thread gọi ban đầu.

Vì vậy, đừng giả định `executor.execute`, `new Thread`, `CompletableFuture.supplyAsync` hoặc `@Async` sẽ kế thừa transaction imperative hiện tại.

## 4. `@Async` không tự mang transaction của caller

Spring `@Async` chuyển lời gọi sang executor. Với imperative transaction management, phương thức chạy trên worker thread và không nhận transaction thread-bound của caller.

Ví dụ:

```java
@Service
public class OrderService {
    private final AuditService auditService;

    @Transactional
    public void updateOrder(long orderId) {
        orderRepository.updateStatus(orderId, "PROCESSING");
        auditService.writeAsync(orderId);
    }
}

@Service
public class AuditService {
    @Async("auditExecutor")
    public void writeAsync(long orderId) {
        auditRepository.insert(orderId, "PROCESSING");
    }
}
```

`writeAsync` chạy trên executor thread. Nếu thao tác repository tự mở transaction hoặc không cần transaction rõ ràng, nó vẫn hoạt động theo cấu hình riêng của nó; nó không trở thành một phần của transaction trong `updateOrder`.

Nếu cần worker có transaction riêng, hãy đặt `@Transactional` trên một service được gọi qua Spring proxy:

```java
@Service
public class AuditDispatcher {
    private final AuditWorker worker;

    @Async("auditExecutor")
    public CompletableFuture<Void> writeAsync(long orderId) {
        worker.writeInNewCall(orderId);
        return CompletableFuture.completedFuture(null);
    }
}

@Service
public class AuditWorker {
    @Transactional
    public void writeInNewCall(long orderId) {
        auditRepository.insert(orderId, "PROCESSING");
    }
}
```

Ở đây `AuditDispatcher` chuyển công việc sang worker thread. Lời gọi `worker.writeInNewCall` đi qua proxy của `AuditWorker`, nên transaction manager có thể bắt đầu transaction cho thread đó. Transaction này là transaction của worker, độc lập với transaction caller.

Trong Spring proxy mode, gọi một phương thức `@Transactional` khác trong cùng object bằng `this.someMethod()` thường không đi qua proxy, vì vậy advice có thể không được áp dụng. Tách ranh giới transaction sang bean khác hoặc dùng cách điều khiển transaction tường minh giúp tránh nhầm lẫn.

## 5. `CompletableFuture` và executor cũng tạo ranh giới thực thi

`CompletableFuture` chỉ mô tả quá trình hoàn tất bất đồng bộ. Nó không tự truyền transaction imperative của thread tạo future sang thread thực hiện continuation.

```java
@Transactional
public void process(long id) {
    orderRepository.updateStatus(id, "PROCESSING");

    CompletableFuture.runAsync(() -> {
        auditRepository.insert(id, "PROCESSING");
    }, executor);
}
```

Lambda thường chạy trên thread executor. Nó không tự tham gia transaction của `process`.

Các phương thức continuation có thể chạy ở thread khác nhau:

- `thenApply`, `thenCompose` có thể chạy trên thread hoàn tất stage trước đó hoặc thread đăng ký continuation nếu stage đã hoàn tất.
- `thenApplyAsync`, `thenComposeAsync`, `supplyAsync` thường dùng executor được chỉ định hoặc common pool mặc định.
- Không nên dựa vào thread cụ thể để suy luận transaction; hãy xác định transaction boundary rõ ràng tại nơi thực hiện database work.

Nếu worker cần transaction riêng, gọi một service transaction qua proxy hoặc dùng `TransactionTemplate` bên trong worker:

```java
CompletableFuture<Void> future = CompletableFuture.runAsync(() ->
    transactionTemplate.executeWithoutResult(status -> {
        auditRepository.insert(orderId, "PROCESSING");
    }), executor);
```

`TransactionTemplate` bắt đầu và kết thúc transaction trong thread đang gọi `execute`/`executeWithoutResult`. Ví dụ trên tạo transaction riêng trong executor thread; nó không nối transaction của caller vào worker.

Nếu cần kết quả async để tiếp tục logic, hãy kết hợp future và xử lý exception rõ ràng. Nhưng `future.join()` trong khi caller vẫn giữ khóa có thể làm caller chờ worker, còn worker lại chờ khóa của caller. Đây là dạng tự gây tắc nghẽn cần tránh.

## 6. Khi nào nên dùng cùng transaction, khi nào nên dùng transaction riêng?

Hãy bắt đầu từ yêu cầu nguyên tử của nghiệp vụ:

| Yêu cầu | Cách tổ chức phù hợp |
|---|---|
| Nhiều thao tác database phải commit/rollback cùng nhau | Thực hiện trong cùng transaction context; không chuyển phần database work sang thread độc lập |
| Tác vụ độc lập có thể thành công/thất bại riêng | Chạy trên worker thread và mở transaction riêng tại worker |
| Chỉ cần tính toán CPU song song, chưa ghi database | Tách phần tính toán ra async, sau đó quay về ranh giới transaction để ghi kết quả |
| Phát sự kiện sau khi dữ liệu đã commit | Dùng callback/event sau commit cho dispatch best-effort; dùng transactional outbox nếu cần bảo đảm bền vững |
| Xử lý bằng R2DBC/reactive repository | Dùng reactive transaction manager và giữ database operations trong cùng reactive subscription/context |
| Công việc phân tán qua nhiều service/database | Dùng outbox, idempotency và saga/compensation; một transaction local không tự bao phủ mọi hệ thống |

Nếu nghiệp vụ yêu cầu order và audit phải luôn cùng commit hoặc cùng rollback, không gửi audit sang async transaction độc lập. Hãy ghi cả hai trong transaction hiện tại. Nếu audit chỉ là telemetry có thể mất, có thể phát sau commit. Nếu audit/event là dữ liệu quan trọng cần phát chắc chắn, hãy ghi outbox row cùng transaction với order rồi để worker phát sau.

## 7. Đừng khởi chạy worker trước khi dữ liệu cha commit

Một lỗi phổ biến là tạo bản ghi trong transaction rồi lập tức gửi ID sang worker:

```java
@Transactional
public void createOrder(Order order) {
    Order saved = orderRepository.save(order);
    dispatcher.dispatch(saved.getId());
}
```

Worker có thể chạy trước khi transaction cha commit. Nếu worker dùng transaction riêng để đọc order, nó có thể không nhìn thấy hàng mới. Nếu worker cập nhật cùng dữ liệu, nó có thể chờ transaction cha. Nếu transaction cha rollback, worker đã nhận một ID không tồn tại.

Với công việc chỉ cần chạy sau commit, có thể đăng ký xử lý ở phase `AFTER_COMMIT`, ví dụ qua `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`. Listener chỉ được gọi sau khi transaction thành công commit; nếu transaction rollback, listener ở phase này không chạy.

Tuy nhiên, callback sau commit không tự bảo đảm giao việc bền vững. Process có thể chết sau khi commit database nhưng trước khi gửi message. Nếu mất event là không chấp nhận được, hãy ghi một outbox event trong transaction tạo order. Worker poll outbox và phát event sau commit; việc gửi lặp cần được xử lý bằng idempotency/deduplication.

## 8. Propagation không truyền transaction qua thread

Các propagation mode của Spring quy định cách một lời gọi tham gia transaction hiện có trong execution context hiện tại. Chúng không phải cơ chế truyền transaction context qua executor.

| Propagation | Ý nghĩa khái quát trong thread/context hiện tại | Khi chạy trên thread mới |
|---|---|---|
| `REQUIRED` | Tham gia transaction hiện tại hoặc tạo transaction mới nếu chưa có | Không thấy transaction của caller; thường tạo transaction mới nếu được gọi qua proxy |
| `REQUIRES_NEW` | Tạm dừng transaction hiện tại và mở transaction mới | Không có transaction caller để tạm dừng; mở transaction riêng |
| `SUPPORTS` | Tham gia nếu có, nếu không thì chạy không transaction | Không tự nhận transaction của caller |
| `MANDATORY` | Yêu cầu phải có transaction hiện tại, nếu không thì lỗi | Thường lỗi vì thread mới không có transaction context được bind |
| `NOT_SUPPORTED` | Tạm dừng transaction hiện tại và chạy không transaction | Chạy không transaction theo lời gọi đó |
| `NEVER` | Yêu cầu không có transaction hiện tại | Chạy được nếu thread mới không có transaction; lỗi nếu có transaction |
| `NESTED` | Có thể dùng savepoint trong transaction hiện tại nếu manager hỗ trợ | Không tạo nested scope bên trong transaction caller; worker có context riêng |

Ví dụ `REQUIRES_NEW` thường được dùng để ghi audit độc lập ngay cả khi transaction nghiệp vụ rollback. Nhưng nếu gọi nó từ một thread mới, nó chỉ tạo transaction mới trong thread đó; không phải “mang transaction cũ sang rồi tách ra”.

`NESTED` thường dựa trên savepoint của cùng transaction/resource. Nó không biến một tác vụ async thành phần con có thể commit độc lập trong transaction cha.

## 9. Không chia sẻ connection hoặc persistence context giữa các thread

JDBC `Connection`, JPA `EntityManager` và Hibernate `Session` không nên được chia sẻ đồng thời giữa các thread như một tài nguyên dùng chung. Trong Spring, các đối tượng proxy như repository hoặc injected `EntityManager` thường tìm tài nguyên được quản lý cho thread/context hiện tại; chúng không có nghĩa một `EntityManager` thực tế có thể được truyền cho worker và sử dụng song song.

Không làm các việc sau:

- Lấy JDBC connection đang thuộc transaction caller rồi truyền vào lambda executor.
- Truyền một Hibernate `Session` hoặc JPA persistence context sang thread khác.
- Đọc/ghi cùng một entity đang được persistence context quản lý đồng thời ở nhiều thread.
- Tự sao chép `TransactionSynchronizationManager` resource map hoặc `ThreadLocal` sang worker.
- Giữ transaction caller mở trong lúc chờ một worker cần chính connection/row lock mà caller đang giữ.

Worker cần truy cập database nên lấy tài nguyên qua repository/transaction manager trong chính execution context của nó. Nếu cần dữ liệu từ caller, truyền ID hoặc immutable DTO đã được tạo an toàn; worker tự đọc lại dữ liệu cần thiết sau khi transaction cha commit.

## 10. Reactive transaction: context đi cùng subscription

Reactive programming thường đổi thread trong một pipeline. Nếu transaction vẫn chỉ gắn với `ThreadLocal` của thread, mỗi lần scheduler chuyển thread sẽ làm mất liên kết. Vì vậy, Spring reactive transaction management dùng Reactor `Context` để gắn transaction context với subscription.

Điều này tạo ra khác biệt quan trọng:

- Với JDBC/JPA imperative transaction, thread hiện tại thường là một phần của transaction context.
- Với R2DBC/reactive transaction, transaction context đi theo Reactor subscriber context, không phụ thuộc một thread duy nhất.
- Các operator như `publishOn` hoặc `subscribeOn` có thể đổi thread nhưng cùng subscription vẫn giữ Reactor context.
- Mọi database operation muốn tham gia transaction phải được compose trong cùng reactive chain/context và dùng reactive resource tương ứng.

Ví dụ dùng `TransactionalOperator` với Spring R2DBC:

```java
@Service
public class ReactiveOrderService {
    private final OrderRepository orders;
    private final PaymentRecordRepository payments;
    private final TransactionalOperator tx;

    public Mono<Void> createOrder(Order order, PaymentRecord payment) {
        return orders.save(order)
            .flatMap(saved -> payments.save(payment))
            .then()
            .as(tx::transactional);
    }
}
```

`TransactionalOperator` bao quanh publisher. Khi subscription chạy, reactive transaction manager bắt đầu transaction, các reactive repository operation trong chain dùng connection được quản lý trong Reactor context, rồi transaction commit khi publisher hoàn tất thành công hoặc rollback khi có lỗi/hủy theo quy tắc của manager.

Với Spring reactive `@Transactional`, phương thức trả về reactive type như `Mono` hoặc `Flux` có thể được bao quanh bởi reactive transaction manager phù hợp. Transaction được gắn với quá trình subscription/execution của publisher, không chỉ thời gian phương thức Java tạo ra publisher.

## 11. Chuyển scheduler trong Reactor không giống tạo một tác vụ rời

Trong một reactive chain, `publishOn` và `subscribeOn` có thể chuyển nơi thực thi nhưng không tạo một subscription độc lập. Reactor Context đi cùng subscriber nên transaction context vẫn có thể được sử dụng qua scheduler hop.

```java
return orderRepository.findById(orderId)
    .publishOn(Schedulers.boundedElastic())
    .flatMap(order -> orderRepository.save(order.withStatus("PROCESSING")))
    .as(tx::transactional);
```

Trong ví dụ, các operator vẫn thuộc cùng publisher/subscription được `TransactionalOperator` bao quanh. Tuy nhiên, chuyển sang scheduler không biến JDBC blocking code thành reactive database operation. Nếu gọi JDBC bên trong `boundedElastic`, JDBC vẫn dùng imperative transaction model và không tự tham gia R2DBC transaction.

Không nên tạo subscription tách rời bên trong reactive chain:

```java
// Không nên: tạo subscription độc lập, tách khỏi lifecycle của chain ngoài.
return orderRepository.findById(orderId)
    .doOnNext(order -> auditRepository.save(order.toAudit()).subscribe())
    .then();
```

`subscribe()` bên trong operator khởi động một luồng xử lý độc lập. Nó không được điều phối như một phần của publisher cha; transaction context, lỗi và thời điểm hoàn tất có thể tách rời. Hãy compose bằng `flatMap`, `concatMap`, `then` hoặc operator phù hợp để framework nhìn thấy toàn bộ công việc.

Tương tự, gọi `block()` bên trong reactive chain thường phá vỡ mô hình non-blocking và có thể gây deadlock hoặc lỗi khi chạy trên non-blocking scheduler. Hãy trả về publisher thay vì tự subscribe hoặc block.

## 12. Nhiều subscription nghĩa là nhiều lần thực thi

Reactive publisher thường lazy. Tạo một `Mono` hoặc `Flux` không nhất thiết thực hiện query ngay; công việc chạy khi có subscription. Nếu publisher transaction được subscribe hai lần, có thể có hai lần thực thi và hai transaction riêng.

```java
Mono<Void> operation = orderService.createOrder(order, payment);

operation.subscribe();
operation.subscribe(); // Có thể chạy nghiệp vụ lần thứ hai.
```

Không gọi subscribe lặp lại chỉ để “lấy kết quả”. Hãy trả publisher cho tầng framework hoặc subscribe đúng một lần ở boundary của ứng dụng. Với side effect, dùng idempotency để bảo vệ trường hợp publisher được chạy lại ngoài ý muốn.

`retry()` trong Reactor cũng resubscribe vào publisher. Nếu transaction operator được đặt ở vị trí phù hợp, mỗi lần retry có thể tạo transaction mới; không nên giả định transaction đã rollback sẽ được tái sử dụng. Hãy xác định rõ operator order và bảo đảm retry chạy lại toàn bộ đơn vị nghiệp vụ cần thiết.

## 13. Không trộn JDBC và R2DBC rồi mong chúng dùng chung transaction

JDBC và R2DBC có loại connection, transaction manager và cách lưu context khác nhau. Một `DataSourceTransactionManager`/JDBC transaction không tự điều phối `R2dbcTransactionManager`, và ngược lại.

Ví dụ, trong một reactive transaction dùng R2DBC, nếu code gọi một JDBC repository đồng bộ, JDBC call thường không tham gia transaction R2DBC. Nó có thể mở connection/transaction riêng hoặc chạy theo autocommit. Nếu JDBC call commit rồi R2DBC transaction rollback, dữ liệu đã ghi qua JDBC vẫn có thể tồn tại.

Muốn phối hợp nhiều resource cần một cơ chế được hỗ trợ rõ ràng như JTA/XA trong môi trường phù hợp, hoặc thiết kế theo outbox/saga với tính nhất quán cuối cùng. Không nên cho rằng hai transaction manager khác nhau sẽ tự chia sẻ transaction chỉ vì chúng được gọi trong cùng một method.

## 14. Virtual threads không tự truyền transaction giữa các tác vụ

Virtual threads giúp tạo nhiều luồng nhẹ hơn, nhưng không thay đổi nguyên tắc của transaction imperative gắn với thread. Khi một phương thức chạy liên tục trên một virtual thread, `ThreadLocal`-based context của framework vẫn có thể hoạt động theo cơ chế được hỗ trợ. Nhưng khi code submit một task sang virtual thread khác, task mới là thread khác và không tự kế thừa transaction của thread gọi.

```java
@Transactional
public void update(long id) {
    repository.update(id);

    Thread.startVirtualThread(() -> {
        repository.writeAudit(id); // Không tự tham gia transaction của caller.
    });
}
```

Hãy áp dụng cùng nguyên tắc như với executor truyền thống: hoặc giữ database work trong transaction hiện tại, hoặc mở transaction riêng trong task mới. Virtual thread không làm JDBC connection hoặc persistence context trở nên an toàn để chia sẻ đồng thời.

## 15. Jakarta Transactions/JTA và managed asynchronous execution

Trong ứng dụng Jakarta EE, transaction có thể do container quản lý bằng JTA. Container có quy tắc riêng cho EJB asynchronous invocation, `ManagedExecutorService` và các context được truyền giữa component. Không nên giả định transaction caller sẽ được truyền sang một tác vụ bất đồng bộ chỉ vì task được submit qua một executor do container quản lý.

Thông thường, asynchronous method có ranh giới transaction riêng theo transaction attribute của component; caller và worker không mặc nhiên trở thành một transaction kéo dài qua hai luồng. Cần kiểm tra hợp đồng của container, Jakarta Concurrency và transaction manager đang dùng. Không dùng raw thread hoặc executor không được container quản lý để thao tác với tài nguyên container-managed nếu nền tảng yêu cầu managed execution.

Nếu cần atomicity xuyên nhiều resource hoặc nhiều service, hãy đánh giá JTA/XA, outbox hoặc saga thay vì tự truyền một transaction object qua thread.

## 16. Kiểm thử transaction khi có async hoặc reactive

Test cũng có thể che giấu lỗi context propagation. Ví dụ một test Spring được đánh dấu `@Transactional` thường chạy transaction trên test thread và rollback khi test kết thúc. Nếu test khởi chạy `@Async` worker, worker có thể chạy transaction riêng và commit dữ liệu thật. Rollback của test thread không tự rollback phần đã commit ở worker.

Một số lưu ý khi kiểm thử:

- Chờ async task hoàn tất và kiểm tra kết quả/exception; đừng để test kết thúc khi worker vẫn chạy.
- Dọn dữ liệu được worker commit bằng fixture hoặc cleanup riêng, không dựa vào rollback của test thread.
- Kiểm thử trường hợp transaction cha rollback sau khi đã submit task để xác nhận worker có chạy ngoài ý muốn hay không.
- Kiểm thử worker chạy trước commit và sau commit để phát hiện vấn đề visibility.
- Với reactive transaction, subscription thực sự mới kích hoạt publisher; dùng công cụ như `StepVerifier` để điều khiển và chờ hoàn tất chain.
- Kiểm thử publisher được subscribe nhiều lần nếu có side effect hoặc retry.
- Xác nhận rollback khi publisher phát error hoặc bị cancel theo đúng reactive transaction manager.

## 17. Cách chẩn đoán transaction context bị mất

Khi một repository call bất ngờ chạy ngoài transaction hoặc commit riêng, hãy ghi nhận các thông tin sau:

- Thread name và execution path tại lúc transaction bắt đầu và lúc repository được gọi.
- Transaction manager được dùng: JDBC/JPA, R2DBC hay JTA.
- Transaction có active/rollback-only không trong context hiện tại.
- Connection/resource nào đang được bind hoặc reactive context nào đang được sử dụng.
- Lời gọi có đi qua Spring proxy không, hay là self-invocation.
- Tác vụ có đi qua executor, `@Async`, `CompletableFuture`, raw thread hay detached Reactor subscription không.
- Transaction cha đã commit trước khi worker đọc dữ liệu chưa.
- Exception có được chuyển về caller hay bị bỏ qua trong future/async callback không.
- Có trộn JDBC và R2DBC hoặc nhiều transaction manager không.

Trong Spring imperative, `TransactionSynchronizationManager.isActualTransactionActive()` có thể hỗ trợ chẩn đoán trạng thái thread hiện tại, nhưng không phải cách truyền transaction context. Với reactive flow, cần kiểm tra context qua reactive APIs của framework và bảo đảm repository operation nằm trong cùng subscription.

Không log nội dung nhạy cảm hoặc connection credentials. Có thể ghi correlation ID, transaction boundary, thread name, transaction manager, operation name và kết quả commit/rollback.

## 18. Những điểm cần nhớ

- Với Spring imperative JDBC/JPA, transaction context thường gắn với thread hiện tại; executor, `@Async` và `CompletableFuture` không tự kế thừa transaction của caller.
- Một async worker cần transaction riêng thì phải mở transaction trong worker thread, ví dụ qua service `@Transactional` được gọi qua proxy hoặc `TransactionTemplate`.
- `REQUIRES_NEW` mở transaction mới trong context hiện tại; nó không truyền transaction qua thread. `NESTED` thường dùng savepoint và cũng không tạo transaction con async.
- Không truyền JDBC connection, JPA `EntityManager` hoặc Hibernate `Session` qua thread để dùng chung.
- Nếu công việc phải chạy sau khi transaction cha commit, dùng after-commit callback; nếu cần bảo đảm phát sự kiện bền vững, dùng transactional outbox.
- Reactive transaction của Spring gắn với Reactor Context/subscription; scheduler hop trong cùng chain vẫn có thể giữ context.
- Không gọi `subscribe()` rời hoặc `block()` bên trong reactive chain để chạy database work tách khỏi transaction.
- JDBC và R2DBC thường dùng transaction manager/resource riêng; không mặc định chúng cùng một transaction.
- Virtual thread không tự truyền transaction sang virtual thread khác.
- Transaction của async worker có thể commit dù test hoặc transaction cha rollback; cần kiểm thử và cleanup riêng.

Khi đổi luồng hoặc chuyển sang bất đồng bộ, hãy xác định rõ ai sở hữu transaction và transaction kết thúc ở đâu. Giữ các thao tác cần atomicity trong cùng context; với công việc độc lập, mở transaction riêng ở worker; với reactive pipeline, giữ mọi database operation trong cùng subscription và Reactor context. Ranh giới rõ ràng giúp tránh commit một phần, đọc dữ liệu chưa commit và giữ tài nguyên giao dịch quá lâu.
