# Tránh subscribe thủ công bên trong tầng Repository và dịch vụ

Trong Spring Data Relational R2DBC, repository và service nên trả về `Mono` hoặc `Flux` để caller quyết định khi nào và trong ngữ cảnh nào công việc được thực thi. Gọi `subscribe()` thủ công bên trong repository hoặc service tạo ra một subscription tách rời khỏi publisher mà phương thức trả về. Caller không còn chờ được kết quả đó, không nhận được lỗi theo reactive pipeline, khó điều khiển cancellation và có thể mất transaction context.

Nguyên tắc quan trọng là **compose publisher xuyên suốt các tầng và chỉ subscribe ở ranh giới thực thi do framework hoặc thành phần điều phối cấp cao quản lý**. Trong ứng dụng WebFlux, controller thường trả publisher để WebFlux subscribe. Trong test, `StepVerifier` subscribe. Với một tiến trình độc lập không có framework tiêu thụ publisher, thành phần ở application boundary có thể sở hữu subscription và vòng đời của nó. Repository và service không nên âm thầm tự chạy công việc rồi trả về một publisher khác.

## 1. Publisher mô tả công việc; subscription kích hoạt công việc

Các API reactive của Spring Data R2DBC như `ReactiveCrudRepository`, `R2dbcEntityTemplate` và `DatabaseClient` trả về publisher. Với thao tác database lazy, lời gọi phương thức thường chỉ tạo mô tả công việc.

Ví dụ:

```java
Mono<Customer> customerMono = customerRepository.findById(10L);
```

Ở thời điểm gán biến `customerMono`, truy vấn thường chưa được thực thi. Khi một subscriber đăng ký và yêu cầu dữ liệu, publisher bắt đầu thực hiện:

```java
customerMono.subscribe();
```

Trong ứng dụng WebFlux, caller thường không cần viết dòng `subscribe()` này. Controller trả `Mono`/`Flux` cho framework; framework đăng ký và quản lý quá trình ghi response.

### 1.1. Vòng đời khi compose đúng

```text
HTTP request
    |
    v
Controller trả Mono / Flux
    |
    v
Service compose publisher
    |
    v
Repository trả publisher database
    |
    v
WebFlux subscribe ở ranh giới response
    |
    v
Database query được thực thi
    |
    v
Kết quả / lỗi / cancellation truyền qua cùng pipeline
```

Mỗi tầng chỉ mô tả phần việc của mình. Publisher đi ngược lên caller; subscriber ở ranh giới thực thi điều khiển toàn bộ chuỗi.

## 2. Vì sao subscribe() bên trong service gây lỗi thiết kế?

Xét đoạn code:

```java
public Mono<Order> createOrder(Order order) {
    orderRepository.save(order).subscribe();
    return Mono.just(order);
}
```

Có hai công việc tách rời:

1. `orderRepository.save(order).subscribe()` tự bắt đầu một subscription riêng.
2. `Mono.just(order)` là publisher mà caller nhận được.

Publisher trả về không đại diện cho thao tác lưu. Nó có thể phát `order` ngay cả khi INSERT chưa hoàn tất hoặc thất bại.

Những vấn đề cụ thể:

- **Caller không chờ thao tác lưu:** response có thể được trả trước khi database ghi xong.
- **Lỗi bị tách khỏi caller:** lỗi từ `save` không truyền qua publisher trả về.
- **Không kiểm soát được cancellation:** client hủy request không tự động hủy subscription lưu đã tách ra.
- **Khó quản lý tài nguyên:** subscription riêng có thể tiếp tục dùng connection sau khi request đã kết thúc.
- **Khó kiểm thử:** test chỉ subscribe publisher trả về có thể không đợi thao tác lưu độc lập.
- **Có nguy cơ ghi lặp:** nếu service được gọi nhiều lần hoặc publisher độc lập được tạo lại, mỗi lần subscribe có thể thực thi một lần ghi.

Việc `subscribe()` trả về một `Disposable` không giải quyết được các vấn đề trên nếu service bỏ qua nó. Ngay cả khi giữ `Disposable`, caller vẫn không nhận được kết quả và lỗi theo cùng một hợp đồng reactive.

### 2.1. Cách viết đúng: trả publisher của thao tác lưu

```java
public Mono<Order> createOrder(Order order) {
    return orderRepository.save(order);
}
```

Caller nhận chính publisher thực hiện INSERT/UPDATE. Khi publisher hoàn tất, caller nhận entity được lưu; khi database phát lỗi, lỗi truyền tới caller; khi caller hủy subscription, cancellation được truyền qua chuỗi publisher theo semantics của các thành phần tham gia.

### 2.2. Không subscribe rồi trả một kết quả giả

Một biến thể nguy hiểm khác:

```java
public Mono<Boolean> register(User user) {
    userRepository.save(user).subscribe();
    return Mono.just(true);
}
```

`true` chỉ xác nhận rằng service đã gọi `subscribe()`, không xác nhận rằng database đã commit. Kết quả thành công phải được phát ra sau khi thao tác lưu hoàn tất:

```java
public Mono<Boolean> register(User user) {
    return userRepository.save(user)
        .thenReturn(true);
}
```

Nếu cần trả entity được lưu, trả trực tiếp `Mono<User>` thay vì đổi thành boolean.

## 3. Không subscribe bên trong Repository

Repository là abstraction truy cập dữ liệu. Trách nhiệm của nó là khai báo hoặc triển khai thao tác dữ liệu và trả publisher cho tầng gọi.

Repository chuẩn:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Mono<Customer> findByEmail(String email);

    Flux<Customer> findByStatus(String status);
}
```

Không cần tự triển khai `subscribe()` cho các phương thức này. Spring Data tạo implementation và quản lý việc thực thi khi publisher được subscribe.

Với custom repository, hãy trả publisher từ `DatabaseClient`:

```java
public class CustomerRepositoryCustomImpl
        implements CustomerRepositoryCustom {

    private final DatabaseClient databaseClient;

    public CustomerRepositoryCustomImpl(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    @Override
    public Flux<CustomerSummary> search(String prefix) {
        return databaseClient.sql("""
                SELECT id, name, email
                FROM customer
                WHERE name LIKE :pattern
                ORDER BY id
                """)
            .bind("pattern", prefix + "%")
            .map((row, metadata) -> new CustomerSummary(
                row.get("id", Long.class),
                row.get("name", String.class),
                row.get("email", String.class)
            ))
            .all();
    }
}
```

Phương thức `search` trả `Flux<CustomerSummary>` để caller quyết định subscribe. Nếu custom repository gọi `.all().subscribe()` rồi trả `Flux.empty()`, nó phá vỡ hợp đồng của repository và khiến các tầng trên không thể điều khiển truy vấn.

### 3.1. Repository không nên tự quyết định thời điểm chạy

Không nên:

```java
@Override
public Mono<Customer> findCustomer(Long id) {
    databaseClient.sql("SELECT id, name FROM customer WHERE id = :id")
        .bind("id", id)
        .map(this::mapCustomer)
        .one()
        .subscribe();

    return Mono.empty();
}
```

Nên:

```java
@Override
public Mono<Customer> findCustomer(Long id) {
    return databaseClient.sql("SELECT id, name FROM customer WHERE id = :id")
        .bind("id", id)
        .map(this::mapCustomer)
        .one();
}
```

Repository không biết request HTTP có bị timeout hay không, caller có muốn lấy một phần tử hay ghép kết quả với nguồn khác, hoặc lỗi nên được chuyển thành HTTP 404/409 thế nào. Những quyết định đó thuộc tầng gọi hoặc service.

## 4. Dùng flatMap để nối thao tác bất đồng bộ phụ thuộc nhau

Một service thường cần thực hiện nhiều thao tác theo thứ tự. Nếu thao tác sau cần kết quả thao tác trước, dùng `flatMap`.

Ví dụ lưu đơn hàng rồi lưu các dòng hàng với ID đơn hàng vừa được tạo:

```java
public Mono<Order> createOrder(
        Order order,
        List<OrderLine> requestedLines) {

    return orderRepository.save(order)
        .flatMap(savedOrder -> {
            List<OrderLine> lines = requestedLines.stream()
                .map(line -> line.withOrderId(savedOrder.getId()))
                .toList();

            return orderLineRepository.saveAll(lines)
                .thenReturn(savedOrder);
        });
}
```

`flatMap` nhận entity sau khi INSERT hoàn tất, tạo publisher lưu lines, đợi publisher đó hoàn tất rồi phát `savedOrder`. Không có subscription thủ công nào được tạo ra.

### 4.1. Dùng then khi chỉ cần đợi thao tác trước hoàn tất

Nếu không cần giá trị từ publisher đầu tiên, dùng `then`:

```java
public Mono<Void> deleteCustomerAndAudit(Long customerId) {
    return customerRepository.deleteById(customerId)
        .then(auditRepository.save(
            AuditEntry.customerDeleted(customerId)
        ))
        .then();
}
```

`then(nextPublisher)` đợi publisher trước hoàn tất thành công rồi mới subscribe publisher tiếp theo. Nếu thao tác đầu phát lỗi, publisher tiếp theo không chạy và lỗi tiếp tục truyền ra ngoài.

Nếu cần phát một giá trị cố định sau khi thao tác trước hoàn tất:

```java
return customerRepository.save(customer)
    .thenReturn("SAVED");
```

`thenReturn` không tạo một subscription tách rời; nó là một toán tử trong cùng pipeline.

### 4.2. Dùng delayUntil khi cần side effect bất đồng bộ nhưng giữ giá trị gốc

`delayUntil` hữu ích khi muốn chờ một publisher phụ thuộc vào giá trị vừa phát, sau đó vẫn trả lại giá trị ban đầu:

```java
public Mono<Order> saveAndAudit(Order order) {
    return orderRepository.save(order)
        .delayUntil(saved -> auditRepository.save(
            AuditEntry.orderCreated(saved.getId())
        ));
}
```

Publisher audit được compose và phải hoàn tất trước khi `saved` được phát downstream. Nếu audit lỗi, lỗi truyền ra ngoài. Đây là một lựa chọn thay cho `doOnNext(saved -> auditRepository.save(...).subscribe())`.

## 5. Không gọi repository bên trong doOnNext rồi subscribe

`doOnNext` dành cho quan sát hoặc side effect đồng bộ gắn với tín hiệu, ví dụ ghi log hoặc tăng metric:

```java
return orderRepository.save(order)
    .doOnNext(saved -> log.info("Created order {}", saved.getId()));
```

Không dùng `doOnNext` để khởi chạy một thao tác reactive khác:

```java
// Không nên: publisher audit bị tách khỏi pipeline chính.
return orderRepository.save(order)
    .doOnNext(saved -> auditRepository.save(
        AuditEntry.orderCreated(saved.getId())
    ).subscribe());
```

`doOnNext` nhận callback trả về `void`. Reactor không thể đợi publisher được tạo bên trong callback. Dùng `flatMap` hoặc `delayUntil`:

```java
return orderRepository.save(order)
    .flatMap(saved -> auditRepository.save(
        AuditEntry.orderCreated(saved.getId())
    ).thenReturn(saved));
```

Trong ví dụ này, kết quả `Order` chỉ được phát sau khi lưu audit hoàn tất. Nếu audit là side effect bắt buộc cùng transaction, hãy bảo đảm cả hai thao tác tham gia cùng transaction. Nếu audit ở hệ thống ngoài, cần cân nhắc outbox hoặc workflow riêng.

## 6. Kết hợp nhiều Publisher mà không subscribe thủ công

Nếu có hai thao tác độc lập và cần cả hai kết quả, có thể dùng `Mono.zip`:

```java
public Mono<CustomerDashboard> loadDashboard(Long customerId) {
    Mono<Customer> customer = customerRepository.findById(customerId);
    Mono<AccountBalance> balance = accountService.findBalance(customerId);

    return Mono.zip(customer, balance)
        .map(tuple -> new CustomerDashboard(
            tuple.getT1(),
            tuple.getT2()
        ));
}
```

`zip` quản lý subscription của cả hai nguồn trong cùng composition. Caller chỉ cần subscribe publisher cuối cùng.

Nếu chỉ cần chờ nhiều thao tác hoàn tất mà không cần giá trị phát ra:

```java
public Mono<Void> refreshCustomerData(Long customerId) {
    Mono<Void> updateSearchIndex = searchIndexService.refresh(customerId);
    Mono<Void> clearCache = cacheService.evictCustomer(customerId);

    return Mono.when(updateSearchIndex, clearCache);
}
```

`Mono.when` kết hợp các publisher hoàn tất. Nếu một nhánh lỗi, lỗi được truyền xuống và các nhánh khác có thể bị hủy theo semantics của toán tử.

### 6.1. Khi các thao tác cần thực hiện tuần tự

Không dùng `Mono.when` hoặc `zip` chỉ vì muốn tránh subscribe. Nếu thao tác thứ hai phụ thuộc kết quả thứ nhất, hãy dùng `flatMap`/`then`.

```java
return customerRepository.save(customer)
    .flatMap(saved -> addressRepository.save(
        address.withCustomerId(saved.getId())
    ).thenReturn(saved));
```

### 6.2. Cẩn thận khi chạy song song trên cùng transaction-bound connection

`zip` hoặc `when` có thể subscribe nhiều thao tác database độc lập. Nếu các thao tác cùng tham gia một reactive transaction và dùng cùng connection, khả năng thực thi song song phụ thuộc driver/connection. Một số driver yêu cầu các statement trên cùng connection được tuần tự hóa hoặc không hỗ trợ nhiều thao tác đồng thời.

Nếu cần thứ tự rõ ràng hoặc driver không hỗ trợ concurrent statements trên cùng connection, hãy compose tuần tự bằng `flatMap`/`then`. Không giả định transaction tự tạo nhiều connection cho từng nhánh.

## 7. Dùng flatMap và concatMap cho Flux

Khi mỗi phần tử của `Flux` cần một thao tác bất đồng bộ, hãy trả publisher từ mapper thay vì subscribe bên trong callback.

Ví dụ xử lý từng đơn hàng:

```java
public Flux<OrderReceipt> processOrders(Flux<Long> orderIds) {
    return orderIds.flatMap(orderId ->
        orderRepository.findById(orderId)
            .flatMap(order -> paymentService.capture(order)
                .map(payment -> new OrderReceipt(order, payment)))
    );
}
```

`flatMap` subscribe và hợp nhất các publisher con, đồng thời có thể chạy nhiều phần tử song song. Thứ tự phát kết quả không nhất thiết giống thứ tự `orderIds`.

Nếu cần giữ thứ tự xử lý:

```java
public Flux<OrderReceipt> processOrdersInOrder(Flux<Long> orderIds) {
    return orderIds.concatMap(orderId ->
        orderRepository.findById(orderId)
            .flatMap(order -> paymentService.capture(order)
                .map(payment -> new OrderReceipt(order, payment)))
    );
}
```

`concatMap` đợi publisher con hiện tại hoàn tất rồi mới xử lý phần tử tiếp theo. Nó giữ thứ tự nhưng giảm concurrency.

### 7.1. Giới hạn concurrency của flatMap

Với nguồn lớn, không nên để hàng nghìn thao tác database hoặc HTTP chạy đồng thời:

```java
return orderIds.flatMap(this::processOneOrder, 8);
```

Con số `8` là concurrency tối đa cho các inner publisher trong toán tử này. Chọn giá trị dựa trên connection pool, giới hạn của dịch vụ ngoài, latency và tải database.

Giới hạn concurrency vẫn là một phần của cùng pipeline. Không cần tạo `subscribe()` riêng cho từng phần tử.

### 7.2. Không dùng subscribe trong vòng lặp

Không nên:

```java
public Mono<Void> importOrders(List<Order> orders) {
    for (Order order : orders) {
        orderRepository.save(order).subscribe();
    }
    return Mono.empty();
}
```

Phương thức có thể hoàn tất ngay khi các subscription riêng vẫn đang chạy. Lỗi của từng INSERT không được tập hợp vào kết quả trả về; không có backpressure hoặc giới hạn concurrency chung.

Nên:

```java
public Mono<Void> importOrders(List<Order> orders) {
    return Flux.fromIterable(orders)
        .concatMap(orderRepository::save)
        .then();
}
```

Hoặc giới hạn concurrency nếu các thao tác độc lập và driver/pool cho phép:

```java
public Mono<Void> importOrders(List<Order> orders) {
    return Flux.fromIterable(orders)
        .flatMap(orderRepository::save, 8)
        .then();
}
```

Với danh sách lớn, có thể dùng `buffer(batchSize)` để xử lý theo batch và giới hạn bộ nhớ.

## 8. subscribe() làm mất đường truyền lỗi và kết quả

Một publisher có hợp đồng tín hiệu rõ ràng:

- `onNext`: phát giá trị.
- `onComplete`: hoàn tất thành công.
- `onError`: kết thúc bằng lỗi.
- `cancel`: downstream không cần dữ liệu nữa.

Khi service tự subscribe và không trả subscription đó, các tín hiệu không còn nằm trong publisher mà caller nhận được.

Ví dụ:

```java
public Mono<Void> saveCustomer(Customer customer) {
    customerRepository.save(customer)
        .subscribe(
            saved -> log.info("Saved {}", saved.getId()),
            error -> log.error("Save failed", error)
        );

    return Mono.empty();
}
```

Callback lỗi có thể ghi log, nhưng caller vẫn thấy `Mono.empty()` hoàn tất bình thường. Controller có thể trả HTTP success dù INSERT thất bại. Test subscribe vào `Mono.empty()` cũng không chờ hoặc kiểm tra thao tác lưu.

Hãy trả publisher:

```java
public Mono<Void> saveCustomer(Customer customer) {
    return customerRepository.save(customer)
        .doOnNext(saved -> log.info("Saved {}", saved.getId()))
        .then();
}
```

Nếu lỗi xảy ra, caller nhận lỗi và có thể quyết định retry, ánh xạ thành lỗi nghiệp vụ hoặc trả HTTP status phù hợp.

## 9. subscribe() làm mất khả năng cancellation

Giả sử client gửi request tạo đơn hàng rồi đóng kết nối trước khi database hoàn tất. Nếu service trả publisher của thao tác lưu, cancellation có thể truyền ngược tới thao tác R2DBC. Driver và transaction manager xử lý việc hủy statement, rollback hoặc giải phóng connection theo khả năng hỗ trợ.

Nếu service đã gọi `subscribe()` riêng:

```java
public Mono<Order> create(Order order) {
    orderRepository.save(order).subscribe();
    return Mono.just(order);
}
```

Publisher trả về không còn liên hệ với thao tác lưu. Khi client hủy response, subscription lưu riêng có thể tiếp tục chạy. Service không có cơ chế rõ ràng để hủy nó, và không biết liệu dữ liệu đã được ghi hay chưa.

Cancellation không có nghĩa mọi thao tác database luôn được hủy tức thì; driver có thể đang thực hiện I/O hoặc database đã xử lý statement. Nhưng giữ công việc trong cùng pipeline giúp framework và driver có cơ hội xử lý cancellation đúng vòng đời, đồng thời caller biết publisher đã bị hủy.

## 10. subscribe() phá vỡ ranh giới reactive transaction

Spring reactive transaction gắn transaction resource với subscription và Reactor Context. `@Transactional` trên một phương thức trả `Mono`/`Flux` quản lý publisher mà phương thức trả về. `TransactionalOperator` cũng bọc publisher được truyền vào.

Ví dụ không nên:

```java
@Transactional
public Mono<Order> createOrder(Order order) {
    orderRepository.save(order).subscribe();
    return Mono.just(order);
}
```

Lời gọi `subscribe()` bên trong thân method tạo một subscription riêng ngay khi thân Java được thực thi để tạo publisher trả về. Publisher transactional do Spring proxy quản lý chỉ được subscribe sau đó. Subscription riêng không tự động tham gia transaction context của publisher bên ngoài. Vì vậy thao tác save có thể chạy ngoài transaction mà caller nghĩ đang quản lý.

Nên compose:

```java
@Transactional
public Mono<Order> createOrder(Order order) {
    return orderRepository.save(order);
}
```

### 10.1. Nhiều thao tác trong cùng transaction

```java
@Transactional
public Mono<Order> createOrder(
        Order order,
        List<OrderLine> requestedLines) {

    return orderRepository.save(order)
        .flatMap(savedOrder -> {
            List<OrderLine> lines = requestedLines.stream()
                .map(line -> line.withOrderId(savedOrder.getId()))
                .toList();

            return orderLineRepository.saveAll(lines)
                .thenReturn(savedOrder);
        });
}
```

Khi publisher trả về được subscribe qua Spring proxy, các thao tác repository trong pipeline có thể tham gia cùng reactive transaction nếu chúng dùng cùng `ConnectionFactory` và transaction manager. Nếu lưu order lines phát lỗi và lỗi truyền ra ngoài, transaction manager có thể rollback cả order lẫn lines.

### 10.2. Nuốt lỗi có thể khiến transaction commit

Ngay cả khi không gọi `subscribe()`, vị trí `onErrorResume` vẫn quan trọng:

```java
@Transactional
public Mono<Order> createOrder(Order order) {
    return orderRepository.save(order)
        .flatMap(this::saveLines)
        .onErrorResume(error -> Mono.empty());
}
```

Nếu lỗi được chuyển thành `Mono.empty()` bên trong publisher transactional, transaction boundary có thể chỉ nhìn thấy completion bình thường và commit những thay đổi trước lỗi. Nếu muốn rollback rồi mới fallback, hãy để lỗi đi qua transaction boundary và đặt handler bên ngoài publisher transactional hoặc bên ngoài method transactional.

## 11. subscribeOn và publishOn không phải subscribe()

Tên các toán tử có thể gây nhầm lẫn:

- `subscribe()` tạo subscription và kích hoạt publisher.
- `subscribeOn(scheduler)` chỉ định scheduler dùng cho quá trình subscription/source subscription theo semantics Reactor.
- `publishOn(scheduler)` chuyển việc xử lý các tín hiệu downstream sang scheduler được chỉ định.

Ví dụ:

```java
return customerRepository.findById(id)
    .publishOn(Schedulers.parallel())
    .map(this::calculateView);
```

`publishOn` không tự subscribe publisher. Caller vẫn cần subscribe ở ranh giới thực thi. Với R2DBC, driver thường đã cung cấp I/O non-blocking; không thêm `subscribeOn(Schedulers.boundedElastic())` một cách máy móc như cách chuyển JDBC blocking sang thread pool. Chỉ chọn scheduler khi có lý do cụ thể, chẳng hạn gọi API blocking không thể thay thế hoặc thực hiện tính toán CPU phù hợp.

Không dùng `subscribeOn` để che giấu việc gọi `subscribe()` thủ công trong service. Hai vấn đề này hoàn toàn khác nhau.

## 12. block(), toFuture() và các cách kích hoạt subscription khác

Tránh chỉ thay `subscribe()` bằng một API khác nhưng vẫn phá vỡ composition.

### 12.1. block()

`block()` subscribe publisher và chờ kết quả theo kiểu đồng bộ:

```java
// Không nên trong reactive service/controller.
Customer customer = customerRepository.findById(id).block();
```

Hành vi này chặn thread, làm mất lợi ích non-blocking và có thể gây lỗi khi gọi trên Reactor non-blocking thread. Hãy trả `Mono<Customer>` hoặc compose bằng `flatMap`.

### 12.2. toFuture()

`Mono.toFuture()` cũng kích hoạt subscription để hoàn tất `CompletableFuture`. Nếu gọi nó rồi bỏ qua future hoặc không compose kết quả, công việc vẫn bị tách khỏi reactive pipeline:

```java
// Không nên: kích hoạt công việc nhưng không đưa kết quả vào pipeline.
customerRepository.findById(id).toFuture();
return Mono.empty();
```

Nếu cần tích hợp với API trả `CompletionStage`, hãy chuyển đổi ở ranh giới tích hợp và bảo đảm future được trả/compose, có xử lý lỗi và cancellation phù hợp. Trong các tầng Repository và service thuần reactive, ưu tiên giữ `Mono`/`Flux` xuyên suốt.

### 12.3. subscribe() không có error handler

Lệnh:

```java
publisher.subscribe();
```

không cung cấp nơi xử lý lỗi nghiệp vụ của caller. Lỗi có thể đi tới hook xử lý lỗi bị bỏ rơi hoặc log mặc định của Reactor, tùy ngữ cảnh. Không nên coi log đó là cơ chế xử lý lỗi của ứng dụng.

## 13. Khi nào subscription thủ công có thể phù hợp?

Subscription là điểm bắt đầu thực thi trong Reactive Streams, vì vậy ở đâu đó phải có thành phần subscribe. Điều cần tránh là repository hoặc service tự tạo subscription ẩn, tách khỏi hợp đồng của caller.

Subscription tường minh có thể phù hợp ở application boundary khi:

- Một tiến trình command-line cần chạy publisher rồi kết thúc.
- Một worker hoặc thành phần background có trách nhiệm sở hữu vòng đời tác vụ.
- Một integration adapter phải nối một nguồn callback imperative với pipeline reactive.
- Một ứng dụng không dùng WebFlux hoặc framework nào tự tiêu thụ publisher.

Trong các trường hợp này, thành phần ở boundary phải chịu trách nhiệm:

- Theo dõi `Disposable` nếu cần hủy công việc.
- Xử lý lỗi đầy đủ và đưa lỗi vào logging/metrics/alert phù hợp.
- Giới hạn concurrency và lượng công việc được xếp hàng.
- Đóng subscription khi ứng dụng shutdown hoặc tác vụ hết hạn.
- Không báo thành công trước khi publisher hoàn tất.
- Bảo đảm transaction và resource lifecycle nằm trong publisher được subscribe.

Ví dụ một runner imperative sở hữu việc chờ tác vụ hoàn tất:

```java
@Component
public class DataImportRunner implements CommandLineRunner {

    private final ImportService importService;

    public DataImportRunner(ImportService importService) {
        this.importService = importService;
    }

    @Override
    public void run(String... args) {
        importService.importData()
            .block(); // Chỉ ở ranh giới imperative của tiến trình.
    }
}
```

Ví dụ này dùng `block()` ở entry point imperative để chờ tác vụ khởi động hoàn tất trước khi runner kết thúc. Nó không phải mẫu để dùng trong repository/service. Trong một ứng dụng reactive end-to-end, hãy để framework quản lý subscription thay vì tự tạo ở nhiều nơi.

Nếu dùng `subscribe()` tại một thành phần background, hãy giữ `Disposable` và có chính sách shutdown/error rõ ràng. Không bỏ subscription vào một biến cục bộ rồi quên nó.

## 14. Công việc nền đáng tin cậy: dùng queue hoặc transactional outbox

Một lý do thường khiến developer gọi `subscribe()` trong service là muốn “lưu dữ liệu xong rồi gửi email/đẩy event ở nền” mà không chờ.

Ví dụ không nên:

```java
public Mono<Order> createOrder(Order order) {
    return orderRepository.save(order)
        .doOnNext(saved -> emailService.sendReceipt(saved).subscribe());
}
```

Email được gửi bằng subscription riêng. Service không biết email thành công hay thất bại; request có thể kết thúc trước khi gửi; tiến trình có thể dừng giữa chừng; và thao tác gửi có thể xảy ra trước khi transaction lưu đơn hàng commit.

Nếu thông báo phải được gửi đáng tin cậy sau khi dữ liệu commit, cân nhắc transactional outbox:

1. Trong cùng transaction, lưu order và một bản ghi outbox mô tả event cần phát.
2. Commit transaction.
3. Worker riêng đọc outbox theo batch và gửi event/email.
4. Khi gửi thành công, đánh dấu bản ghi đã xử lý.
5. Khi lỗi tạm thời, retry có giới hạn; dùng event ID/idempotency để chống gửi trùng.

Ví dụ service:

```java
@Transactional
public Mono<Order> createOrder(Order order) {
    return orderRepository.save(order)
        .flatMap(saved -> outboxRepository.save(
            OutboxEvent.orderCreated(saved.getId())
        ).thenReturn(saved));
}
```

Worker đọc outbox và publish event trong workflow riêng. Cách này giúp việc lưu dữ liệu và ghi nhận ý định gửi event cùng commit, trong khi việc gửi thực tế có thể retry độc lập. Nó không tạo exactly-once delivery tuyệt đối; consumer vẫn cần idempotency vì message có thể được gửi lại.

Nếu side effect chỉ là best-effort và mất đi khi ứng dụng shutdown là chấp nhận được, có thể dùng một background executor/worker có lifecycle rõ ràng. Nhưng hãy đưa trách nhiệm subscribe, error handling và shutdown vào thành phần đó, không giấu nó bên trong repository.

## 15. Xử lý lỗi đúng trong cùng pipeline

Khi giữ publisher trong một pipeline, lỗi có thể được xử lý tại đúng tầng:

```java
public Mono<Customer> findCustomer(Long id) {
    return customerRepository.findById(id)
        .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)))
        .onErrorMap(DataAccessException.class,
            error -> new CustomerStoreUnavailableException(error));
}
```

Caller nhận publisher có thể phát `CustomerNotFoundException` hoặc `CustomerStoreUnavailableException`. Controller advice có thể ánh xạ chúng thành HTTP status thích hợp.

Nếu service gọi `subscribe()` bên trong, lỗi không còn được truyền tới caller theo cùng cách. Service có thể log lỗi nhưng response vẫn thành công, hoặc lỗi bị xử lý ở hook toàn cục mà không có ngữ cảnh request.

### 15.1. Fallback phải là một phần của pipeline

Ví dụ dùng cache trước, rồi đọc database nếu cache miss:

```java
public Mono<Customer> findCustomer(Long id) {
    return cacheService.findCustomer(id)
        .switchIfEmpty(customerRepository.findById(id))
        .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)));
}
```

Publisher database được subscribe khi nhánh fallback được chọn. Không cần subscribe thủ công trong `switchIfEmpty`.

### 15.2. Không chuyển mọi lỗi thành empty

```java
// Không nên nếu lỗi database cần được báo cho caller.
return customerRepository.findById(id)
    .onErrorResume(error -> Mono.empty());
```

Code này làm caller không phân biệt được “không có khách hàng” và “database đang lỗi”. Chỉ fallback cho loại lỗi được xác định và có ý nghĩa nghiệp vụ.

## 16. Kiểm thử service mà không cần subscribe thủ công trong code sản phẩm

Trong test, `StepVerifier` là subscriber có chủ đích. Nó kích hoạt publisher và kiểm tra tín hiệu:

```java
@Test
void createOrderReturnsSavedEntity() {
    StepVerifier.create(orderService.createOrder(order, lines))
        .assertNext(saved -> assertNotNull(saved.getId()))
        .verifyComplete();
}
```

Kiểm thử lỗi:

```java
@Test
void propagatesDatabaseFailure() {
    StepVerifier.create(orderService.createOrder(order, lines))
        .expectError(DataAccessException.class)
        .verify();
}
```

Kiểm thử thứ tự thao tác có thể dùng mock hoặc test database để xác nhận `saveAll(lines)` chỉ chạy sau khi `save(order)` phát entity có ID.

Với integration test R2DBC, cần đợi publisher hoàn tất trước khi đọc trạng thái database. Không gọi `subscribe()` trong service rồi dùng `Thread.sleep()` trong test để chờ thao tác nền; cách đó tạo test không ổn định và che giấu lỗi lifecycle.

## 17. Quan sát subscription và công việc reactive

Khi ứng dụng có vấn đề “request trả thành công nhưng dữ liệu không được ghi”, cần kiểm tra:

- Service có gọi `subscribe()` rồi trả một publisher khác không?
- Có `block()`, `toFuture()` hoặc subscription ẩn trong callback không?
- Publisher có được trả tới controller/framework không?
- Có nhánh `onErrorResume` nào chuyển lỗi thành empty/default không?
- Có inner publisher được tạo nhưng không được compose không?
- Subscription có bị dispose/cancel trước khi hoàn tất không?
- Transaction boundary có bao trùm publisher chứa thao tác database không?
- Có log/metric cho số hàng được ghi, lỗi và thời gian hoàn tất không?

Nên log tại các điểm quan sát trong pipeline:

```java
return orderRepository.save(order)
    .doOnSubscribe(subscription -> log.debug("Saving order"))
    .doOnNext(saved -> log.info("Saved order {}", saved.getId()))
    .doOnError(error -> log.error("Order save failed", error))
    .doFinally(signal -> log.debug("Order save finished: {}", signal));
```

`doFinally` có thể quan sát complete, error hoặc cancel. Các callback này chỉ phục vụ quan sát đồng bộ; không dùng chúng để khởi chạy một publisher khác bằng `subscribe()`.

## 18. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Gọi `repository.save(...).subscribe()` rồi trả `Mono.just(...)` | Caller không chờ database và có thể nhận thành công giả | Trả publisher từ repository |
| Gọi `subscribe()` trong custom repository | Phá vỡ hợp đồng reactive của repository | Trả `Mono`/`Flux` từ `DatabaseClient` hoặc SPI |
| Gọi repository bên trong `doOnNext` rồi subscribe | Inner publisher không được compose hoặc chờ | Dùng `flatMap`/`delayUntil` |
| Subscribe trong vòng lặp | Nhiều tác vụ chạy rời rạc, không có backpressure chung | Dùng `Flux.fromIterable` và `flatMap`/`concatMap` |
| Bỏ qua `Disposable` | Không thể chủ động quản lý cancellation của tác vụ nền | Để caller sở hữu publisher hoặc quản lý Disposable tại boundary |
| Không cung cấp error handler cho subscription nền | Lỗi có thể bị bỏ rơi hoặc chỉ xuất hiện trong hook/log | Trả lỗi qua publisher hoặc xử lý đầy đủ ở worker owner |
| Dùng `block()` trong service reactive | Chặn thread và có thể gây lỗi non-blocking | Compose bằng toán tử Reactor |
| Gọi `toFuture()` rồi bỏ kết quả | Kích hoạt subscription ngoài pipeline | Trả publisher hoặc compose future ở integration boundary |
| Dùng `Mono.empty()` để che lỗi | Caller tưởng không có dữ liệu thay vì biết hệ thống lỗi | Chỉ fallback cho lỗi/empty có semantics rõ |
| Nuốt lỗi trong transaction | Transaction có thể commit sau completion bình thường | Để lỗi truyền qua boundary nếu cần rollback |
| Nghĩ `subscribeOn` tự subscribe | Publisher vẫn chưa chạy nếu không có subscriber | Subscribe ở ranh giới thực thi |
| Gọi `subscribe()` trong method `@Transactional` | Inner subscription có thể nằm ngoài transaction context | Trả publisher được proxy quản lý |
| Gọi `Mono.when` cho các statement cùng connection mà giả định chạy song song an toàn | Driver có thể không hỗ trợ concurrent statements | Tuần tự hóa khi cần và kiểm thử driver |
| Dùng subscription nền cho email/event quan trọng | Side effect có thể mất hoặc chạy trước commit | Dùng outbox/queue và worker có lifecycle |

## 19. Quy trình thiết kế service reactive

Khi viết một phương thức Repository hoặc service, hãy đi theo các bước:

1. Xác định giá trị hoặc tín hiệu mà caller cần nhận: entity, DTO, số hàng, `Void` hay lỗi.
2. Trả `Mono`/`Flux` từ repository và không tự subscribe trong implementation.
3. Nối các thao tác phụ thuộc bằng `flatMap`, `then` hoặc `delayUntil`.
4. Kết hợp các nguồn độc lập bằng `zip`/`when` khi semantics và driver cho phép.
5. Với nguồn nhiều phần tử, chọn `flatMap` có concurrency hữu hạn hoặc `concatMap` nếu cần thứ tự.
6. Đặt error handling trong pipeline nhưng giữ lỗi cần rollback truyền tới transaction boundary.
7. Đặt `@Transactional` hoặc `TransactionalOperator` trên đúng publisher cần quản lý.
8. Trả publisher cho caller/framework; không gọi `subscribe()`, `block()` hoặc bỏ `toFuture()` trong service.
9. Nếu thật sự cần công việc nền, chuyển nó sang worker/queue/outbox có owner rõ ràng.
10. Kiểm thử bằng `StepVerifier` và database tích hợp; xác nhận complete, error, cancellation và transaction.

## 20. Nguyên tắc cần nhớ

- `Mono` và `Flux` mô tả công việc reactive; subscription kích hoạt công việc.
- Repository và service nên trả publisher, không tự gọi `subscribe()` để chạy ngầm.
- `subscribe()` tạo một subscription riêng; caller không còn kiểm soát kết quả, lỗi và cancellation của công việc đó qua publisher trả về.
- Dùng `flatMap` cho thao tác bất đồng bộ phụ thuộc kết quả trước; dùng `then` khi chỉ cần đợi hoàn tất.
- Dùng `delayUntil` khi cần chờ side effect reactive nhưng vẫn phát giá trị gốc.
- `doOnNext` phù hợp với quan sát/side effect đồng bộ; không dùng để khởi chạy Publisher khác.
- Dùng `zip`, `when`, `flatMap` và `concatMap` theo đúng semantics; giới hạn concurrency khi cần.
- `block()` và `toFuture()` cũng có thể kích hoạt subscription; tránh dùng trong các tầng reactive.
- `subscribeOn` và `publishOn` điều khiển scheduler, không thay thế subscription.
- Reactive transaction quản lý publisher được trả về; subscription tách rời có thể không tham gia transaction context.
- Để lỗi đi qua transaction boundary nếu muốn rollback; không biến lỗi thành complete ngoài ý muốn.
- WebFlux, StepVerifier hoặc một application boundary có trách nhiệm là nơi phù hợp để subscribe.
- Công việc nền quan trọng nên dùng queue/outbox và worker có lifecycle, retry và idempotency.
- Không gọi `subscribe()` bên trong vòng lặp; compose nguồn bằng `Flux` để giữ backpressure và error propagation.

Tránh subscribe thủ công bên trong Repository và service giúp giữ một luồng reactive xuyên suốt từ tầng truy cập dữ liệu tới caller. Khi mọi thao tác được compose bằng các toán tử Reactor, caller có thể điều khiển thời điểm thực thi, nhận lỗi, hủy công việc và tham gia transaction đúng cách. Subscription chỉ nên được tạo tại ranh giới thực thi có trách nhiệm quản lý kết quả và vòng đời của nó.
