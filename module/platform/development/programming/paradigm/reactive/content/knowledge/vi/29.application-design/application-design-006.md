# Phân tách tác dụng phụ, tài nguyên và điều phối thực thi

Một ứng dụng reactive dễ trở nên khó bảo trì khi một phương thức vừa tính toán quy tắc nghiệp vụ, vừa gọi database, gửi HTTP, mở tài nguyên, chọn scheduler và tự subscribe để khởi chạy công việc. Những trách nhiệm này có vòng đời và cách kiểm thử khác nhau. Khi chúng bị trộn lẫn, ứng dụng khó xác định lỗi xảy ra ở đâu, khó hủy công việc đúng lúc và khó bảo đảm side effect chỉ được thực hiện khi có subscription.

Thiết kế tốt nên tách ba mối quan tâm: **tác dụng phụ** (*side effects*) thuộc về các adapter và ranh giới I/O; **tài nguyên** (*resources*) có owner và lifecycle rõ ràng; **điều phối thực thi** (*execution orchestration*) kết hợp các publisher theo thứ tự, concurrency và chính sách lỗi mà use case yêu cầu. Phần quy tắc nghiệp vụ thuần nên dễ kiểm thử và không phụ thuộc thread, database hoặc framework.

Bài học thuộc chương **Thiết kế ứng dụng** của module `REACTIVE_PROGRAMMING`, nơi người học thực hành các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; đồng thời sử dụng `Mono`, `Flux`, operator, scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java.

## 1. Ba mối quan tâm cần được phân tách

Hãy xem một use case đặt hàng. Nó cần kiểm tra đầu vào, tính tổng tiền, đọc tồn kho, lưu đơn hàng và phát sự kiện `OrderCreated`.

Ba nhóm trách nhiệm xuất hiện:

| Mối quan tâm | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Tác dụng phụ | Hệ thống bên ngoài thay đổi hoặc cung cấp dữ liệu ở đâu? | Query database, gọi HTTP, publish message, ghi file. |
| Tài nguyên | Ai sở hữu và giải phóng thứ được mở ra? | Connection, transaction, cursor, response body, listener. |
| Điều phối thực thi | Các bước chạy theo thứ tự nào, đồng thời đến mức nào và lỗi được xử lý ra sao? | `flatMap`, `concatMap`, `zip`, `when`, scheduler, retry. |

Một thiết kế có thể được hình dung như sau:

```text
        HTTP Controller / Message Handler
                     |
                     v
              Application Use Case
          điều phối các publisher/port
              /       |        \
             v        v         v
       Domain rules  Repository  Event Publisher
       thuần         port        port
                         |          |
                         v          v
                    R2DBC adapter  Broker adapter
                         |
                         v
                 Connection / Transaction
                  có owner và lifecycle
```

Controller nhận request và chuyển nó vào use case. Use case điều phối các port, nhưng không cần biết chi tiết driver, HTTP client hoặc broker. Domain rules tính toán kết quả từ dữ liệu đầu vào. Adapter thực hiện I/O và quản lý tài nguyên tương ứng.

## 2. Giữ quy tắc nghiệp vụ thuần và dễ kiểm thử

Quy tắc thuần (*pure function*) nhận đầu vào và trả đầu ra mà không thay đổi trạng thái bên ngoài. Cùng đầu vào tạo cùng đầu ra. Nó không đọc đồng hồ hệ thống, không sinh ID ngẫu nhiên, không ghi database và không gọi mạng.

Ví dụ tính tổng đơn hàng:

```java
record OrderLine(String sku, int quantity, BigDecimal unitPrice) {}

record OrderDraft(List<OrderLine> lines) {}

record OrderTotal(BigDecimal amount, int lineCount) {}

final class OrderPricing {
    OrderTotal calculate(OrderDraft draft) {
        BigDecimal amount = draft.lines().stream()
            .map(line -> line.unitPrice()
                .multiply(BigDecimal.valueOf(line.quantity())))
            .reduce(BigDecimal.ZERO, BigDecimal::add);

        return new OrderTotal(amount, draft.lines().size());
    }
}
```

`OrderPricing` không biết `Mono`, `Flux`, scheduler hoặc database. Có thể kiểm thử nó bằng unit test thông thường mà không cần khởi tạo Reactor hay môi trường I/O.

Khi một giá trị cần được tạo từ bên ngoài, hãy đưa nó vào đầu vào của quy tắc hoặc tạo ở application layer. Ví dụ, nếu thời điểm tạo đơn là dữ liệu nghiệp vụ, use case có thể nhận `Clock` và lấy thời gian một lần, sau đó truyền `Instant` vào domain logic. Khi replay hoặc kiểm thử, thời gian có thể được kiểm soát.

```java
final class CreateOrderUseCase {
    private final Clock clock;

    CreateOrderUseCase(Clock clock) {
        this.clock = clock;
    }

    OrderCreatedEvent createEvent(Order order) {
        return new OrderCreatedEvent(order.id(), clock.instant());
    }
}
```

Ở đây `Clock` là một dependency được tiêm vào. Domain event giữ lại timestamp đã tạo; reducer hoặc logic replay về sau không gọi lại `Instant.now()` để thay đổi kết quả lịch sử.

## 3. Biểu diễn tác dụng phụ bằng Publisher trì hoãn

Một publisher mô tả công việc có thể thực thi khi subscriber đăng ký. Để giữ được đặc tính đó, cần tạo side effect tại thời điểm subscription, không thực hiện ngay khi xây dựng biểu thức.

### `Mono.just` và `Mono.fromCallable`

Không nên:

```java
Mono<Customer> unsafe = Mono.just(
    jdbcCustomerDao.findById(customerId)
);
```

`findById` chạy ngay khi biểu thức được đánh giá. Nếu đây là JDBC đồng bộ, thread hiện tại bị chặn trước khi `Mono` được tạo.

Nên:

```java
Mono<Customer> legacyLookup = Mono.fromCallable(
    () -> jdbcCustomerDao.findById(customerId)
).subscribeOn(Schedulers.boundedElastic());
```

`fromCallable` trì hoãn lời gọi đến lúc subscribe. `subscribeOn(boundedElastic())` đặt tác vụ blocking lên scheduler phù hợp. Nếu có driver reactive, hãy ưu tiên dùng API đó để không phải giữ worker trong lúc chờ I/O.

### `Mono.defer` cho publisher cần được tạo theo subscription

`defer` hữu ích khi chính publisher nguồn cần được tạo lại cho mỗi subscription:

```java
Mono<PaymentResult> charge(PaymentCommand command) {
    return Mono.defer(() -> paymentClient.charge(command));
}
```

Nếu `paymentClient.charge` tạo request hoặc publisher có trạng thái theo lần gọi, `defer` bảo đảm nó chỉ được tạo khi có subscription. Khi retry, supplier có thể chạy lại để tạo attempt mới. Dữ liệu định danh command, như idempotency key, phải ổn định qua các lần thử và được tạo ở bên ngoài supplier.

### Không đặt side effect nghiệp vụ vào `map`

`map` nên biến đổi giá trị đồng bộ. Không dùng nó để gọi `subscribe()` lồng nhau hoặc khởi chạy công việc không được trả về pipeline:

```java
// Không nên: tác vụ con nằm ngoài lifecycle của chuỗi.
orders.map(order -> {
    notificationClient.send(order).subscribe();
    return order;
});
```

Hãy nối publisher con bằng `flatMap` hoặc `then`:

```java
Flux<Order> notified = orders.concatMap(order ->
    notificationClient.send(order)
        .thenReturn(order)
);
```

Giờ đây lỗi và cancellation của notification nằm trong pipeline. Use case có thể quyết định có cần chờ notification hoàn tất trước khi tiếp tục hay không.

## 4. Đặt side effect sau một ranh giới port

Application layer nên phụ thuộc vào interface mô tả nhu cầu nghiệp vụ thay vì phụ thuộc trực tiếp vào driver hoặc framework. Đây là cách áp dụng kiến trúc ports and adapters (hexagonal architecture) cho reactive application.

Ví dụ các port:

```java
interface CustomerRepository {
    Mono<Customer> findById(CustomerId id);
}

interface OrderRepository {
    Mono<Order> save(Order order);
}

interface OrderEventPublisher {
    Mono<Void> publish(OrderCreatedEvent event);
}

interface InventoryService {
    Mono<Reservation> reserve(ReserveInventory command);
}
```

Các port trả về publisher vì công việc có thể bất đồng bộ. Chúng không tiết lộ `DatabaseClient`, `WebClient`, Kafka `ReceiverRecord` hoặc connection cụ thể. Adapter hiện thực interface bằng công nghệ tương ứng.

Ví dụ adapter database:

```java
@Repository
final class R2dbcOrderRepository implements OrderRepository {
    private final DatabaseClient database;

    R2dbcOrderRepository(DatabaseClient database) {
        this.database = database;
    }

    @Override
    public Mono<Order> save(Order order) {
        return database.sql("""
                INSERT INTO orders (id, customer_id, total)
                VALUES (:id, :customerId, :total)
                RETURNING id, customer_id, total
                """)
            .bind("id", order.id().value())
            .bind("customerId", order.customerId().value())
            .bind("total", order.total())
            .map((row, metadata) -> new Order(
                new OrderId(row.get("id", UUID.class)),
                new CustomerId(row.get("customer_id", UUID.class)),
                row.get("total", BigDecimal.class)
            ))
            .one();
    }
}
```

Ví dụ dùng cú pháp `RETURNING` của PostgreSQL để minh họa. SQL và kiểu ánh xạ cần được điều chỉnh theo database và driver thực tế. Điểm kiến trúc là adapter chứa chi tiết SQL, còn use case chỉ biết `OrderRepository`.

### Lợi ích của port

- Unit test use case có thể thay adapter bằng publisher giả lập.
- Đổi driver hoặc broker không buộc domain phải thay đổi.
- Chính sách retry, timeout và concurrency có thể được đặt tại đúng ranh giới.
- Tài nguyên được quản lý bên trong adapter hoặc transaction scope có owner rõ ràng.
- Application layer thể hiện thứ tự nghiệp vụ thay vì chi tiết giao thức I/O.

Không nên tạo interface cho mọi hàm nhỏ chỉ để tăng số lượng abstraction. Hãy tạo port tại ranh giới có ý nghĩa: nơi nghiệp vụ cần một khả năng bên ngoài và nơi implementation có thể thay đổi độc lập.

## 5. Tách điều phối khỏi cách thực thi

Use case quyết định các bước nghiệp vụ cần hoàn tất và quan hệ giữa chúng. Operator Reactor thể hiện cách các publisher được kết hợp.

Một số lựa chọn phổ biến:

| Operator | Ngữ nghĩa | Khi dùng |
|---|---|---|
| `map` | Biến đổi một giá trị đồng bộ. | Tính toán thuần, ánh xạ DTO. |
| `flatMap` | Nối một publisher con bất đồng bộ. | Bước tiếp theo phụ thuộc kết quả bước trước. |
| `concatMap` | Nối publisher con tuần tự, giữ thứ tự. | Ghi hoặc xử lý từng phần tử theo thứ tự. |
| `flatMapSequential` | Chạy publisher con đồng thời nhưng phát theo thứ tự nguồn. | Cần concurrency và thứ tự đầu ra. |
| `Mono.zip` | Kết hợp giá trị từ nhiều nguồn độc lập. | Cần tất cả kết quả để tính bước tiếp theo. |
| `Mono.when` | Chờ nhiều publisher hoàn tất. | Nhiều side effect độc lập, không cần kết quả dữ liệu. |
| `then` | Chờ publisher trước hoàn tất rồi chạy bước sau. | Tuần tự hóa các side effect. |

### Dùng `zip` cho dữ liệu độc lập

```java
Mono<OrderPreview> preview(OrderDraft draft) {
    Mono<Customer> customer = customerRepository.findById(draft.customerId());
    Mono<PriceQuote> quote = pricingService.quote(draft.lines());

    return Mono.zip(customer, quote)
        .map(tuple -> new OrderPreview(
            tuple.getT1(),
            tuple.getT2(),
            draft.lines()
        ));
}
```

Hai nguồn không phụ thuộc nhau nên có thể được subscribe đồng thời. `zip` phát kết quả khi cả hai nguồn cung cấp giá trị. Nếu một nguồn hoàn tất rỗng, `zip` không có đủ giá trị để tạo tuple và kết quả có thể hoàn tất rỗng; hãy xử lý `Mono.empty()` rõ ràng nếu nghiệp vụ cần phân biệt trường hợp đó.

### Dùng `when` cho side effect độc lập

```java
Mono<Void> refreshReadModels(Customer customer) {
    return Mono.when(
        searchIndex.refresh(customer),
        recommendationCache.invalidate(customer.id()),
        auditLog.recordProfileRefresh(customer.id())
    );
}
```

`when` chờ các publisher hoàn tất và không tạo tuple kết quả. Nếu một publisher lỗi, `Mono.when` có thể kết thúc lỗi và hủy các publisher còn lại. Nếu cần thu thập lỗi từ mọi nhánh trước khi báo lỗi, xem xét `whenDelayError` và chính sách tổng hợp lỗi phù hợp.

### Dùng `then` khi bước sau phụ thuộc vào việc bước trước hoàn tất

```java
Mono<Void> saveThenPublish(Order order, OrderCreatedEvent event) {
    return orderRepository.save(order)
        .then(eventPublisher.publish(event));
}
```

`then` bỏ qua giá trị của publisher trước và subscribe publisher sau khi bước trước hoàn tất bình thường. Tuy nhiên, đoạn mã này chưa bảo đảm tính nguyên tử giữa database và broker. Nếu publish thất bại sau khi database đã commit, đơn hàng tồn tại nhưng event chưa được gửi. Phần transaction/outbox bên dưới giải quyết ranh giới đó.

## 6. Tách orchestration thành use case dễ đọc

Use case nên đọc như một quy trình nghiệp vụ. Các chi tiết SQL, HTTP và broker nằm sau port. Ví dụ tạo đơn hàng:

```java
final class CreateOrderUseCase {
    private final CustomerRepository customers;
    private final InventoryService inventory;
    private final OrderRepository orders;
    private final OrderPricing pricing;
    private final Clock clock;

    CreateOrderUseCase(
            CustomerRepository customers,
            InventoryService inventory,
            OrderRepository orders,
            OrderPricing pricing,
            Clock clock) {
        this.customers = customers;
        this.inventory = inventory;
        this.orders = orders;
        this.pricing = pricing;
        this.clock = clock;
    }

    Mono<Order> execute(CreateOrderCommand command) {
        return customers.findById(command.customerId())
            .switchIfEmpty(Mono.error(
                new CustomerNotFoundException(command.customerId())
            ))
            .flatMap(customer -> {
                if (!customer.active()) {
                    return Mono.error(
                        new CustomerInactiveException(customer.id())
                    );
                }

                OrderTotal total = pricing.calculate(command.draft());
                ReserveInventory reservation =
                    ReserveInventory.from(command, total);

                return inventory.reserve(reservation)
                    .flatMap(ignored -> {
                        Order order = Order.create(
                            command,
                            total,
                            clock.instant()
                        );
                        return orders.save(order);
                    });
            });
    }
}
```

Đây là skeleton minh họa điều phối và có thể được mở rộng để phát event bằng outbox. Use case không gọi `subscribe()` và không tự mở connection. Nó trả `Mono<Order>` cho caller quyết định nơi subscribe, thường là framework ở ranh giới HTTP hoặc message handler.

Trong ví dụ, reservation xảy ra trước khi lưu đơn. Nếu lưu thất bại sau khi tồn kho đã được giữ, cần có thao tác release/compensation hoặc một transaction/saga được thiết kế phù hợp. Không được giả định hai port khác hệ thống tự động nằm trong cùng transaction chỉ vì chúng được nối bằng `flatMap`.

## 7. Phân biệt điều phối và sở hữu tài nguyên

Use case có thể điều phối publisher nhưng không nhất thiết phải trực tiếp sở hữu connection hoặc cursor. Tài nguyên nên được mở ở nơi biết cách đóng nó và gắn cleanup với vòng đời publisher.

Một số quy tắc:

- Repository/adapter sở hữu connection trong phạm vi query nếu framework quản lý theo operation.
- Transaction boundary sở hữu connection/transaction trong phạm vi transaction reactive.
- Adapter streaming sở hữu cursor hoặc response body cho đến khi luồng hoàn tất hoặc bị hủy.
- Component sở hữu subscription dài hạn và phải dispose khi component kết thúc.
- Scheduler tùy chỉnh do thành phần tạo ra phải được dispose khi thành phần đó shutdown.

Không trả một connection thô ra nhiều tầng để mọi caller tự quyết định lúc đóng. Điều đó làm ownership mơ hồ và dễ tạo use-after-close hoặc rò rỉ connection.

### Quản lý tài nguyên đồng bộ với `using`

Với tài nguyên có cleanup đồng bộ, Reactor có `using`:

```java
Flux<String> readLines(Path path) {
    return Flux.using(
        () -> Files.lines(path),
        Flux::fromStream,
        Stream::close
    ).subscribeOn(Schedulers.boundedElastic());
}
```

Resource supplier chỉ được gọi khi có subscription. Stream được đóng khi publisher hoàn tất, phát lỗi hoặc bị cancel. Nếu thao tác mở/đọc file là blocking, cần đặt nguồn trên scheduler phù hợp hoặc dùng API file bất đồng bộ; `using` quản lý lifecycle chứ không biến I/O đồng bộ thành non-blocking.

### Quản lý tài nguyên cleanup bất đồng bộ bằng `usingWhen`

Nếu tạo và đóng tài nguyên đều bất đồng bộ, dùng `usingWhen`:

```java
Mono<Report> loadReport(ConnectionFactory factory, long reportId) {
    return Mono.usingWhen(
        Mono.from(factory.create()),
        connection -> queryReport(connection, reportId),
        connection -> Mono.from(connection.close()),
        (connection, error) -> Mono.from(connection.close()),
        connection -> Mono.from(connection.close())
    );
}
```

`usingWhen` gắn publisher cleanup với ba kết cục: complete, error và cancel. Ví dụ đóng connection theo cùng một thao tác ở cả ba nhánh; trong ứng dụng thực tế, cleanup khi error có thể cần rollback trước khi close và cleanup khi cancel cần theo đúng hợp đồng driver.

Với Spring `DatabaseClient` hoặc Spring Data R2DBC, framework thường quản lý connection cho query. Chỉ dùng `usingWhen` trực tiếp khi adapter thực sự sở hữu tài nguyên cấp thấp và cần tự quản lý lifecycle.

## 8. Transaction là một resource scope có ranh giới rõ ràng

Transaction reactive cần được gắn với cùng `ConnectionFactory` và context mà các thao tác database sử dụng. Spring cung cấp `R2dbcTransactionManager` và `TransactionalOperator` để điều phối transaction trong publisher chain.

```java
Mono<Order> persistOrder(Order order) {
    Mono<Order> work = orders.save(order)
        .flatMap(saved -> orderLines.saveAll(order.lines())
            .thenReturn(saved));

    return transactionalOperator.transactional(work);
}
```

Khi publisher hoàn tất bình thường, transaction manager commit. Khi publisher phát lỗi, transaction được rollback theo cơ chế của manager. Các repository phải tham gia cùng transaction context; một thao tác tự mở connection ngoài context có thể không nằm trong transaction.

Không gọi `block()` hoặc `subscribe()` lồng nhau trong transaction. Những thao tác đó tạo subscription riêng và có thể không tham gia transaction context của chuỗi hiện tại.

Transaction nên ngắn. Không giữ transaction database trong lúc gọi HTTP chậm, chờ người dùng hoặc retry dài. Nếu quy trình trải qua nhiều hệ thống, hãy cân nhắc outbox, inbox hoặc saga thay vì giữ một connection và lock trong toàn bộ quy trình.

## 9. Điều phối scheduler tại ranh giới thực thi

Scheduler trả lời câu hỏi công việc được thực thi trên nhóm thread nào. Nó không thay đổi ý nghĩa nghiệp vụ và không tự giải quyết concurrency ở dependency.

| Scheduler | Công việc phù hợp | Điều cần tránh |
|---|---|---|
| `Schedulers.parallel()` | Tính toán CPU-bound ngắn, không blocking. | JDBC, file I/O đồng bộ, `block()` hoặc chờ khóa. |
| `Schedulers.boundedElastic()` | Adapter cho API blocking/legacy I/O. | Tạo vô hạn tác vụ blocking hoặc dùng làm nơi mặc định cho mọi bước. |
| `Schedulers.single()` | Tác vụ cần một worker tuần tự trong phạm vi scheduler. | Dùng cho workload blocking dài hoặc nhiều luồng không liên quan. |
| `Schedulers.immediate()` | Thực thi ngay trên thread hiện tại. | Nghĩ rằng nó chuyển thread hoặc bảo vệ khỏi blocking. |

Ví dụ tách blocking I/O và CPU transform:

```java
Mono<Score> calculateScore(long customerId) {
    return Mono.fromCallable(() -> legacyCustomerDao.load(customerId))
        .subscribeOn(Schedulers.boundedElastic())
        .publishOn(Schedulers.parallel())
        .map(this::computeScore);
}
```

Lời gọi DAO được trì hoãn và thực thi trên `boundedElastic`. Sau `publishOn`, phép tính CPU-bound chạy trên `parallel`. Nếu DAO đã có API R2DBC hoặc reactive HTTP, bỏ adapter blocking và không cần chuyển sang `boundedElastic`.

### `subscribeOn` và `publishOn` có vai trò riêng

- `subscribeOn` ảnh hưởng đến quá trình subscribe nguồn upstream; thường dùng để đặt nguồn blocking trên `boundedElastic`.
- `publishOn` chuyển việc xử lý tín hiệu downstream sau vị trí operator sang scheduler chỉ định.

Đặt `publishOn` sau một lời gọi blocking đã chạy không thể chuyển ngược lời gọi đó. Hãy đặt `subscribeOn` ngay tại adapter nguồn blocking.

Không nên tạo scheduler mới cho mỗi request. Scheduler là tài nguyên dùng chung hoặc do component quản lý; tạo quá nhiều scheduler có thể làm tăng thread và chi phí quản lý. Dùng scheduler mặc định khi phù hợp, hoặc tạo scheduler riêng có giới hạn và lifecycle rõ ràng cho workload đặc thù.

## 10. Context truyền dữ liệu theo subscription

Reactive pipeline có thể chuyển thread, vì vậy không nên dựa vào `ThreadLocal` để truyền dữ liệu xuyên suốt các operator như thể mọi bước luôn chạy trên cùng thread. Reactor Context cung cấp dữ liệu gắn với subscription, ví dụ correlation ID, tenant hoặc metadata quan sát.

```java
Mono<Order> traced = orderUseCase.execute(command)
    .contextWrite(context -> context.put("correlationId", correlationId));
```

Đọc context bằng `deferContextual`:

```java
Mono<Order> withAudit(Order order) {
    return Mono.deferContextual(contextView -> {
        String correlationId = contextView.get("correlationId");
        return auditPort.record(order.id(), correlationId)
            .thenReturn(order);
    });
}
```

Context được truyền theo subscription và có thể được đọc ở các bước downstream phù hợp. Không dùng Context làm nơi chứa object mutable lớn hoặc thay thế tham số nghiệp vụ cần được khai báo rõ. Dữ liệu bắt buộc để tính kết quả nên tiếp tục được truyền bằng kiểu dữ liệu/command.

Các framework tracing và transaction reactive có thể tích hợp với Reactor Context. Hãy tránh tự sao chép ThreadLocal bằng callback thủ công nếu thư viện đã có integration chính thức.

## 11. Tách chính sách lỗi khỏi adapter kỹ thuật

Adapter nên chuyển lỗi kỹ thuật thành loại lỗi có ý nghĩa với application layer mà không xóa mất nguyên nhân gốc. Use case quyết định lỗi đó dẫn đến retry, fallback, compensation hay trả lỗi cho caller.

Ví dụ:

```java
Mono<Inventory> findInventory(String sku) {
    return inventoryClient.fetch(sku)
        .onErrorMap(TimeoutException.class,
            error -> new InventoryUnavailableException(sku, error));
}
```

Use case có thể chọn retry cho lỗi tạm thời:

```java
Mono<Inventory> loadInventory(String sku) {
    return findInventory(sku)
        .retryWhen(Retry.backoff(2, Duration.ofMillis(100))
            .maxBackoff(Duration.ofSeconds(1))
            .filter(this::isTransient));
}
```

Không nên retry tất cả lỗi tại mọi adapter và use case. Retry lồng nhau có thể nhân số lần gọi, vượt deadline và gây retry storm. Chọn một tầng sở hữu retry cho dependency, giới hạn số lần và dùng idempotency cho thao tác có side effect.

### Phân biệt fallback và che giấu lỗi

`onErrorResume` phù hợp khi có một kết quả thay thế được nghiệp vụ chấp nhận, ví dụ dùng cache cũ với nhãn stale. Trả `Mono.empty()` cho mọi lỗi có thể khiến caller hiểu nhầm rằng dữ liệu không tồn tại. Hãy giữ khác biệt giữa not found, unavailable và invalid input.

## 12. Điều phối side effect có thứ tự và bù trừ

Một use case nhiều bước có thể yêu cầu thứ tự rõ ràng. Ví dụ đặt hàng: giữ tồn kho, lưu đơn hàng, sau đó phát event. Nếu bước sau thất bại, hệ thống cần biết side effect nào đã xảy ra.

```java
Mono<Order> placeOrder(CreateOrderCommand command) {
    return inventory.reserve(command.reservation())
        .flatMap(reservation ->
            orders.save(command.toOrder(reservation))
                .flatMap(order -> events.publish(
                        OrderCreatedEvent.from(order)
                    )
                    .thenReturn(order)
                    .onErrorResume(error ->
                        inventory.release(reservation)
                            .then(Mono.error(error))
                    )
                )
        );
}
```

Ví dụ này minh họa compensation khi publish event lỗi sau khi reservation và lưu đơn đã xảy ra. Tuy nhiên, release tồn kho không xóa đơn hàng đã lưu; quy trình thực tế cần xác định trạng thái đơn hàng và cách phục hồi dữ liệu. Nếu event được ghi vào outbox trong cùng transaction với đơn hàng, ứng dụng có thể tránh phụ thuộc vào việc publish broker ngay trong request.

### Outbox tách commit database khỏi gửi message

Khi cần bảo đảm thay đổi database và ý định phát event được lưu cùng nhau, ghi cả entity và outbox record trong một transaction:

```text
BEGIN DATABASE TRANSACTION
    INSERT order
    INSERT outbox_event
COMMIT

Background publisher:
    read pending outbox rows
    publish to broker
    mark row as published
```

Nếu service crash sau commit nhưng trước khi publish, outbox row vẫn còn để worker gửi sau. Nếu publish thành công nhưng đánh dấu outbox thất bại, message có thể được gửi lại; consumer vẫn cần idempotency. Outbox không tự tạo exactly-once xuyên database và broker, nhưng nó giữ được ý định phát event bền vững cùng transaction của dữ liệu nghiệp vụ.

Worker outbox là một thành phần có lifecycle riêng: nó sở hữu subscription poll/tail, giới hạn số bản ghi đang xử lý, commit trạng thái gửi và dispose khi shutdown. Như vậy, side effect broker, tài nguyên database và điều phối thực thi vẫn có owner rõ ràng.

## 13. Hủy subscription và lifecycle của ứng dụng

Một publisher mô tả công việc; subscription bắt đầu công việc. Khi subscriber hủy, cancellation được truyền ngược upstream. Adapter cần phản ứng bằng cách dừng đọc, tháo listener hoặc giải phóng tài nguyên nếu API nguồn hỗ trợ.

Với một nguồn sự kiện dài hạn, service có thể giữ `Disposable`:

```java
final class OrderEventListener {
    private final Disposable.Composite subscriptions =
        Disposables.composite();

    void start(Flux<OrderEvent> events) {
        subscriptions.add(
            events.concatMap(this::handle)
                .subscribe(
                    ignored -> {},
                    this::onFatalError
                )
        );
    }

    void stop() {
        subscriptions.dispose();
    }
}
```

Đây là cách quản lý subscription bằng Reactor Core: `Disposables.composite()` tạo một `Disposable.Composite`, còn `subscribe()` trả về `Disposable` để thêm vào nhóm. Trong RxJava, kiểu container tương ứng thường là `CompositeDisposable`. Service sở hữu subscription dài hạn và phải dispose trong lifecycle shutdown. Đừng tạo subscription trong mọi request nếu công việc thực ra là một listener toàn service.

Trong Spring, có thể gắn việc khởi động/dừng với lifecycle bean hoặc hook shutdown phù hợp. Hãy xác định rõ service nào sở hữu subscription, cách xử lý lỗi terminal và cách khởi động lại sau lỗi.

Cancellation không phải rollback. Một HTTP request đã đến server hoặc một lệnh database đã commit không tự bị đảo ngược khi client hủy. Side effect cần compensation hoặc idempotency theo quy tắc nghiệp vụ.

## 14. Kiểm thử từng lớp độc lập

Phân tách trách nhiệm làm cho kiểm thử rõ ràng hơn:

| Lớp | Kiểm thử trọng tâm | Công cụ phù hợp |
|---|---|---|
| Domain rules thuần | Giá trị, bất biến, boundary condition. | JUnit thông thường. |
| Application use case | Thứ tự gọi port, nhánh lỗi, empty, cancellation. | Fake/mock port, `StepVerifier`. |
| Adapter database | SQL, mapping, transaction, resource cleanup. | R2DBC test database, Testcontainers, `StepVerifier`. |
| Adapter HTTP/broker | Serialization, timeout, retry, acknowledgement. | Mock server hoặc broker test, integration test. |
| Scheduler boundary | Blocking không chạy trên non-blocking thread. | BlockHound, test thread/scheduler. |
| Lifecycle service | Subscription được hủy và resource được giải phóng. | Test lifecycle, `Disposable`, probe/fake resource. |

### Kiểm thử use case bằng fake publisher

```java
@Test
void savesOrderAfterInventoryReservation() {
    List<String> calls = new ArrayList<>();

    InventoryService inventory = command -> {
        calls.add("reserve");
        return Mono.just(new Reservation("reservation-1"));
    };

    OrderRepository orders = order -> {
        calls.add("save");
        return Mono.just(order);
    };

    CreateOrderUseCase useCase = new CreateOrderUseCase(
        customerRepository,
        inventory,
        orders,
        pricing,
        clock
    );

    StepVerifier.create(useCase.execute(command))
        .expectNextMatches(order -> order.id() != null)
        .verifyComplete();

    assertEquals(List.of("reserve", "save"), calls);
}
```

Đây là skeleton minh họa cách kiểm tra thứ tự; các dependency còn lại được cung cấp bằng fake tương ứng. Không cần khởi tạo database thật để kiểm tra orchestration của use case.

### Kiểm thử lỗi không kích hoạt bước tiếp theo

```java
AtomicBoolean saved = new AtomicBoolean();

InventoryService failingInventory = command ->
    Mono.error(new InventoryUnavailableException(command.sku()));

OrderRepository trackingOrders = order ->
    Mono.fromRunnable(() -> saved.set(true)).thenReturn(order);

CreateOrderUseCase failingUseCase = new CreateOrderUseCase(
    customerRepository,
    failingInventory,
    trackingOrders,
    pricing,
    clock
);

StepVerifier.create(failingUseCase.execute(command))
    .expectError(InventoryUnavailableException.class)
    .verify();

assertFalse(saved.get());
```

Test xác minh lỗi từ reservation dừng chuỗi và không gọi bước lưu. Với mỗi nhánh lỗi, hãy kiểm tra side effect nào đã xảy ra và compensation nào cần chạy.

### Kiểm thử scheduler và cancellation

Đưa scheduler vào constructor hoặc adapter khi cần điều khiển trong test. Dùng `StepVerifier.withVirtualTime` cho timer và backoff; dùng BlockHound để phát hiện blocking trên thread non-blocking; dùng resource fake có cờ `closed` để xác minh cleanup khi complete, error và cancel.

Không dùng `Thread.sleep()` để đồng bộ test. Hãy dùng `StepVerifier`, `TestPublisher`, `Sinks.One`, latch chỉ ở ranh giới test khi thực sự cần, hoặc scheduler ảo.

## 15. Những dấu hiệu thiết kế đang trộn lẫn trách nhiệm

- Controller gọi trực tiếp JDBC, HTTP client và broker rồi tự xử lý thứ tự.
- Domain object import `Mono`, `Flux`, `DatabaseClient` hoặc annotation của framework dù không cần biết về I/O.
- Repository tự `subscribe()` thay vì trả publisher cho caller.
- Một service vừa tạo scheduler, vừa mở connection, vừa retry mọi lỗi và vừa ghi metric nghiệp vụ.
- `doOnNext` chứa lệnh ghi dữ liệu hoặc gọi dịch vụ mà không được kết hợp vào publisher.
- Một connection hoặc cursor được truyền qua nhiều tầng mà không xác định owner đóng.
- Transaction giữ mở trong lúc gọi API mạng hoặc chờ timer dài.
- Mọi bước đều được chuyển scheduler dù nguồn đã non-blocking.
- Test use case cần broker/database thật chỉ để xác minh thứ tự operator.
- Hủy request nhưng subscription nền vẫn chạy vì đã được subscribe riêng.

Khi gặp các dấu hiệu này, hãy xác định lại owner của side effect và resource, chuyển I/O vào adapter, để use case trả publisher đã được kết hợp và gắn lifecycle ở đúng ranh giới.

## 16. Tình huống thực tế: thiết kế một use case đặt hàng

Một yêu cầu đặt hàng cần:

1. Tìm khách hàng và xác minh khách hàng còn hoạt động.
2. Tính tổng tiền bằng quy tắc thuần.
3. Giữ tồn kho qua dịch vụ inventory.
4. Lưu đơn hàng và outbox event trong một transaction R2DBC.
5. Trả đơn hàng cho controller.
6. Một worker riêng đọc outbox và phát event lên broker.

Kiến trúc đề xuất:

```text
HTTP request
    |
    v
CreateOrderUseCase
    |-- CustomerRepository.findById       (I/O port)
    |-- OrderPricing.calculate             (pure domain rule)
    |-- InventoryService.reserve           (remote side effect)
    |-- OrderPersistence.saveWithOutbox    (transaction boundary)
    |
    v
Mono<Order>

OutboxPublisher (service lifecycle riêng)
    |-- read pending rows                  (database resource)
    |-- publish event                      (broker side effect)
    |-- mark published                     (database update)
    |-- retry / backoff / idempotency
```

Use case điều phối các bước phụ thuộc nhau bằng `flatMap` và `then`. Adapter R2DBC quản lý transaction và connection. Inventory adapter chịu trách nhiệm timeout, retry có giới hạn và idempotency key. Outbox worker sở hữu subscription dài hạn và được dispose khi service shutdown. Domain pricing có thể kiểm thử độc lập.

Nếu reservation tồn kho thành công nhưng transaction lưu đơn thất bại, use case cần gọi release/compensation hoặc một quy trình đối soát. Nếu transaction lưu đơn và outbox thành công nhưng broker đang lỗi, worker tiếp tục gửi lại sau; event consumer phải idempotent vì publish có thể lặp khi worker crash giữa publish và đánh dấu hoàn tất.

Không có một operator duy nhất giải quyết các vấn đề nhất quán xuyên nhiều hệ thống. `flatMap` điều phối tín hiệu trong một pipeline; transaction bảo vệ thao tác trong một resource scope; outbox/inbox và idempotency xử lý ranh giới bền vững giữa các hệ thống.

## 17. Checklist phân tách side effects, resources và orchestration

- Giữ quy tắc nghiệp vụ thuần, không phụ thuộc Reactor hoặc driver nếu không cần.
- Đặt I/O sau port và adapter có hợp đồng rõ ràng.
- Trả `Mono`/`Flux` từ service; để caller ở ranh giới ứng dụng sở hữu subscription.
- Dùng `fromCallable`/`defer` để trì hoãn side effect đến subscription.
- Không gọi `subscribe()` lồng nhau trong `map`, `doOnNext` hoặc service.
- Chọn `map`, `flatMap`, `concatMap`, `zip`, `when` và `then` theo quan hệ nghiệp vụ.
- Đặt owner và cleanup cho connection, cursor, response body, listener và scheduler.
- Dùng `using`/`usingWhen` khi adapter trực tiếp quản lý resource.
- Giữ transaction reactive ngắn và không chặn; không giả định transaction bao phủ hệ thống bên ngoài.
- Chọn scheduler tại ranh giới blocking hoặc CPU-bound thực sự.
- Truyền metadata theo Reactor Context khi phù hợp; không dựa vào ThreadLocal qua thread switch.
- Đặt retry ở phạm vi nhỏ, phân loại lỗi, giới hạn attempt và bảo vệ side effect bằng idempotency.
- Dùng outbox/inbox hoặc compensation cho quy trình xuyên nhiều hệ thống.
- Kiểm thử domain, use case, adapter, scheduler và lifecycle ở đúng tầng.
- Xác minh cancellation thực sự dừng nguồn hoặc giải phóng tài nguyên khi API hỗ trợ.

Khi side effect nằm ở adapter, tài nguyên có owner và cleanup rõ ràng, còn use case chỉ điều phối các publisher theo quy tắc nghiệp vụ, ứng dụng reactive dễ đọc và dễ kiểm thử hơn. Cách phân tách này cũng làm rõ nơi đặt concurrency, scheduler, retry, transaction và cancellation, giúp pipeline duy trì hành vi nhất quán khi tải tăng hoặc một dependency gặp lỗi.
