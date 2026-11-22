# Thời điểm bắt đầu, commit và rollback theo đăng ký thực thi

Trong Spring Data Relational R2DBC, transaction hoạt động theo mô hình reactive và gắn với vòng đời subscription của `Mono` hoặc `Flux`. Việc gọi một phương thức repository, tạo `Mono`, ghép các toán tử Reactor hoặc bọc publisher bằng `TransactionalOperator` mới chỉ mô tả công việc. Transaction reactive được bắt đầu khi publisher transactional được subscribe; transaction được commit khi luồng hoàn tất thành công và được rollback khi luồng kết thúc bằng lỗi hoặc bị hủy theo cơ chế quản lý transaction.

Điểm này khác với cách nhiều lập trình viên quen thuộc khi dùng JDBC đồng bộ, nơi câu lệnh thường được thực thi ngay trong lời gọi phương thức. Nếu hiểu sai thời điểm subscription, ứng dụng có thể tạo publisher nhưng không thực thi, chạy một thao tác ngoài transaction, nuốt lỗi khiến transaction commit hoặc hủy luồng theo cách làm transaction rollback ngoài dự kiến.

## 1. Transaction reactive gắn với subscription

Các thao tác R2DBC như repository method, `DatabaseClient` và `R2dbcEntityTemplate` trả về publisher. Những publisher này thường lazy: chúng mô tả công việc và chỉ thực thi khi có subscriber yêu cầu dữ liệu.

Ví dụ:

```java
Mono<Customer> customerMono = customerRepository.findById(10L);
```

Tại thời điểm dòng code chạy, ứng dụng tạo một `Mono<Customer>`. Truy vấn database thường chưa được thực hiện. Khi có subscription:

```java
customerMono.subscribe();
```

hoặc khi publisher được framework WebFlux tiêu thụ, thao tác mới bắt đầu thực thi.

Với reactive transaction, quy tắc tương tự áp dụng cho ranh giới transaction:

- Tạo publisher transactional: mô tả công việc cần thực hiện trong transaction.
- Subscribe publisher: transaction manager bắt đầu transaction và thiết lập transaction context.
- Thực thi các thao tác R2DBC: các thao tác tham gia transaction nếu dùng đúng connection factory và cơ chế kết nối do Spring quản lý.
- Publisher hoàn tất thành công: transaction manager commit.
- Publisher phát lỗi: transaction manager rollback theo quy tắc transaction.
- Subscription bị hủy trước khi hoàn tất: transaction manager xử lý rollback khi nhận cancellation theo semantics của reactive transaction.

### 1.1. Sơ đồ vòng đời

```text
Application gọi service method
             |
             v
Tạo Mono / Flux (chưa chạy SQL)
             |
             v
Publisher được subscribe
             |
             v
ReactiveTransactionManager bắt đầu transaction
             |
             v
Các thao tác R2DBC chạy trong transaction context
             |
       +-----+----------------+
       |                      |
       v                      v
Publisher onComplete      onError / cancel
       |                      |
       v                      v
    COMMIT                 ROLLBACK
```

Sơ đồ mô tả quy tắc chung. Các toán tử có thể chuyển một tín hiệu lỗi thành giá trị hoặc chuyển việc dừng upstream thành complete; vì vậy vị trí đặt toán tử trong và ngoài ranh giới transaction rất quan trọng.

## 2. Tạo publisher không đồng nghĩa với bắt đầu transaction

Một lỗi thường gặp là cho rằng transaction đã bắt đầu ngay khi gọi phương thức có `@Transactional` hoặc khi tạo publisher.

Ví dụ:

```java
@Transactional
public Mono<Order> createOrder(CreateOrderRequest request) {
    return orderRepository.save(toOrder(request));
}
```

Phương thức trả về `Mono<Order>`. Với reactive transaction manager, transaction được gắn vào quá trình subscription của publisher được proxy quản lý. Nếu caller không subscribe hoặc framework không tiêu thụ publisher, thao tác lưu không chạy và transaction không được thực thi.

Đây là lý do controller WebFlux thường trả trực tiếp `Mono` hoặc `Flux` cho framework:

```java
@PostMapping("/orders")
public Mono<Order> create(@RequestBody CreateOrderRequest request) {
    return orderService.createOrder(request);
}
```

WebFlux quản lý subscription của response body. Không cần gọi `subscribe()` thủ công trong controller.

### 2.1. Publisher được subscribe nhiều lần

Một publisher reactive thông thường có thể được subscribe nhiều lần. Với các thao tác database lazy, mỗi subscription có thể thực thi lại truy vấn hoặc thao tác ghi. Nếu publisher được bọc trong ranh giới transaction, mỗi subscription thường tạo một lần thực thi transaction riêng.

```java
Mono<Order> savePublisher = transactionalOperator.transactional(
    orderRepository.save(order)
);
```

Nếu hai subscriber độc lập cùng subscribe `savePublisher`, không nên giả định thao tác INSERT chỉ chạy một lần. Có thể có hai transaction và hai lần ghi, tùy publisher và chiến lược ID/constraint.

Nếu nghiệp vụ cần đúng một lần thực thi, hãy quản lý subscription ở một nơi, dùng idempotency key hoặc cơ chế chống ghi trùng phù hợp. Không dùng việc giữ một biến `Mono` làm bảo đảm rằng database chỉ thực hiện một lần.

## 3. Thời điểm thực thi code trong method và Mono.defer

Transaction reactive bắt đầu khi publisher transactional được subscribe, nhưng phần thân Java của service method vẫn có thể chạy ngay khi method được gọi để tạo publisher. Những thao tác được thực hiện ngay trong lúc lắp ráp pipeline không tự động trở thành reactive database work.

Ví dụ:

```java
@Transactional
public Mono<Order> createOrder(CreateOrderRequest request) {
    AuditEntry audit = createAuditEntry(request); // Chạy ngay khi gọi method.

    return orderRepository.save(toOrder(request))
        .doOnNext(order -> audit.setOrderId(order.getId()));
}
```

`createAuditEntry(...)` là code Java đồng bộ và chạy trước subscription. Nếu nó truy cập tài nguyên hoặc thực hiện side effect mà bạn muốn nằm trong luồng transaction, hãy trì hoãn công việc đó bằng `Mono.defer` hoặc một publisher thích hợp:

```java
@Transactional
public Mono<Order> createOrder(CreateOrderRequest request) {
    return Mono.defer(() -> {
        AuditEntry audit = createAuditEntry(request);

        return orderRepository.save(toOrder(request))
            .flatMap(order -> auditRepository.save(
                audit.withOrderId(order.getId())
            ).thenReturn(order));
    });
}
```

Lambda trong `defer` được gọi khi subscription bắt đầu. Các publisher repository được compose trong cùng pipeline nên có thể tham gia cùng transaction được Spring quản lý.

Không cần bọc mọi lời gọi repository bằng `defer` nếu chúng chỉ tạo publisher lazy và không có side effect eager. `defer` đặc biệt hữu ích khi cần trì hoãn việc tạo publisher, đọc trạng thái runtime hoặc thực hiện code đồng bộ cho đến lúc subscription.

## 4. Commit xảy ra khi publisher hoàn tất thành công

Với một reactive transaction, tín hiệu `onComplete` cho biết publisher đã hoàn tất bình thường. Transaction manager có thể thực hiện commit sau khi toàn bộ công việc trong ranh giới transactional hoàn tất.

Ví dụ dùng `TransactionalOperator`:

```java
Mono<Order> work = orderRepository.save(order)
    .flatMap(saved -> orderLineRepository.saveAll(linesFor(saved))
        .then(Mono.just(saved)));

return transactionalOperator.transactional(work);
```

Khi subscription hoàn tất bình thường, các thao tác lưu order và order lines nằm trong cùng publisher transactional. Transaction manager commit sau khi publisher nguồn hoàn tất.

### 4.1. Mono.empty() vẫn là complete thành công

Một điểm quan trọng: `Mono.empty()` không phải lỗi. Nó phát `onComplete` mà không phát giá trị. Vì vậy, nếu publisher transactional hoàn tất bằng `Mono.empty()`, transaction thông thường được xem là hoàn tất thành công và có thể commit.

Ví dụ:

```java
@Transactional
public Mono<Void> cancelOrder(Long orderId) {
    return orderRepository.findById(orderId)
        .flatMap(order -> orderRepository.delete(order))
        .then();
}
```

Nếu không tìm thấy order, `findById` hoàn tất rỗng. `flatMap` không chạy và `.then()` cũng hoàn tất bình thường. Đây không tự động gây rollback.

Nếu nghiệp vụ yêu cầu không tìm thấy order phải là lỗi, hãy chuyển trạng thái rỗng thành error:

```java
@Transactional
public Mono<Void> cancelOrder(Long orderId) {
    return orderRepository.findById(orderId)
        .switchIfEmpty(Mono.error(
            new OrderNotFoundException(orderId)
        ))
        .flatMap(order -> orderRepository.delete(order));
}
```

Khi exception được phát qua publisher và nằm trong phạm vi transaction, transaction manager có thể rollback theo rollback rules.

### 4.2. Commit không xảy ra ngay sau khi một query phát giá trị

Một `Mono` có thể phát giá trị rồi mới complete. Với transaction bao quanh toàn pipeline, việc nhận một phần tử không đồng nghĩa transaction đã commit. Commit xảy ra khi publisher transactional kết thúc thành công.

Với `Flux`, transaction có thể còn mở trong toàn bộ thời gian các phần tử được phát. Nếu downstream xử lý chậm, connection và transaction có thể bị giữ lâu. Không nên trả một Flux không giới hạn từ bên trong transaction nếu nghiệp vụ không cần transaction kéo dài qua toàn bộ stream.

## 5. Rollback khi publisher phát lỗi

Khi một thao tác trong transaction phát lỗi và lỗi truyền tới ranh giới transactional, transaction manager thực hiện rollback theo quy tắc được cấu hình.

Ví dụ:

```java
Mono<Order> createOrder(CreateOrderRequest request) {
    Mono<Order> work = orderRepository.save(toOrder(request))
        .flatMap(order -> orderLineRepository.saveAll(
                linesFor(order, request))
            .then(Mono.just(order)))
        .flatMap(order -> inventoryRepository.reserve(
                request.productId(), request.quantity())
            .thenReturn(order));

    return transactionalOperator.transactional(work);
}
```

Nếu lưu order thành công nhưng lưu order line hoặc reserve inventory phát lỗi trong cùng transaction, lỗi được truyền ra ngoài và transaction manager rollback các thay đổi thuộc transaction đó.

Điều kiện để rollback đúng:

- Các thao tác thực sự nằm trong cùng publisher transactional.
- Chúng dùng cùng connection factory được transaction manager quản lý.
- Lỗi không bị nuốt trước khi đi tới transaction boundary.
- Database và driver hỗ trợ transaction cho các thao tác đó.

Nếu một thao tác đã được tách ra bằng `subscribe()` độc lập, hoặc dùng một connection factory khác, nó có thể không thuộc transaction đang xét.

## 6. Cancellation cũng ảnh hưởng đến transaction

Trong reactive streams, cancellation là tín hiệu downstream không cần dữ liệu nữa. Nó khác `onComplete` và `onError`. Khi subscriber hủy một publisher transactional trước khi hoàn tất, reactive transaction management của Spring xử lý rollback để tránh commit một luồng bị dừng giữa chừng.

Các nguyên nhân cancellation thường gặp:

- Client HTTP đóng kết nối khi request đang chạy.
- Timeout ở tầng web hoặc service hủy subscription.
- Toán tử phía downstream không cần thêm dữ liệu và hủy upstream.
- Một pipeline lớn bị hủy do một nhánh khác thất bại.
- Ứng dụng chủ động dispose subscription.

Điều này đặc biệt quan trọng với `Flux`:

```java
Flux<Order> transactionalOrders = transactionalOperator.transactional(
    orderRepository.findAll()
        .doOnNext(this::processOrder)
);

return transactionalOrders;
```

Nếu subscriber hủy luồng trước khi nó hoàn tất, transaction có thể rollback. Không nên dùng một Flux transactional như một stream tải dữ liệu dài vô hạn nếu không có chủ đích giữ transaction và connection trong toàn bộ vòng đời stream.

### 6.1. Vị trí toán tử có thể thay đổi tín hiệu mà transaction nhìn thấy

Transaction boundary chỉ có thể phản ứng với tín hiệu mà publisher bên trong nó phát ra. Ví dụ, `onErrorResume` đặt bên trong boundary có thể biến lỗi thành complete bình thường; `take` đặt bên trong boundary có thể hoàn tất publisher downstream sau khi hủy nguồn upstream. Ngược lại, cancellation từ phía downstream đối với publisher transactional được bọc có thể được transaction operator nhận trực tiếp.

Vì vậy, hãy thiết kế vị trí của `take`, `next`, `onErrorResume`, timeout và các toán tử short-circuit một cách có chủ đích. Nếu mục tiêu là rollback khi không xử lý hết toàn bộ công việc, đừng chuyển cancellation hoặc lỗi thành một completion thành công trước khi tín hiệu tới transaction boundary.

## 7. Dùng TransactionalOperator

`TransactionalOperator` là cách lập trình tường minh để bọc một publisher trong transaction reactive. Nó sử dụng một `ReactiveTransactionManager`, ví dụ `R2dbcTransactionManager`.

### 7.1. Khai báo bean

```java
@Configuration
public class TransactionConfiguration {

    @Bean
    TransactionalOperator transactionalOperator(
            ReactiveTransactionManager transactionManager) {
        return TransactionalOperator.create(transactionManager);
    }
}
```

Trong ứng dụng chỉ có một reactive transaction manager, Spring có thể inject bean phù hợp. Nếu ứng dụng có nhiều manager, hãy dùng qualifier hoặc cấu hình tên bean rõ ràng để tránh chọn nhầm manager.

### 7.2. Bọc publisher bằng transactional(...)

```java
public Mono<Order> placeOrder(CreateOrderRequest request) {
    Mono<Order> work = orderRepository.save(toOrder(request))
        .flatMap(order -> saveLines(order, request)
            .thenReturn(order))
        .flatMap(order -> reserveInventory(order, request)
            .thenReturn(order));

    return transactionalOperator.transactional(work);
}
```

`transactional(work)` trả về publisher được quản lý transaction. Khi publisher đó được subscribe, transaction bắt đầu. Khi `work` hoàn tất thành công, transaction commit; nếu lỗi được truyền qua, transaction rollback.

### 7.3. Dùng as(...) để thể hiện ranh giới

Reactor cho phép viết pipeline theo dạng:

```java
return orderRepository.save(order)
    .flatMap(this::saveLines)
    .thenReturn(order)
    .as(transactionalOperator::transactional);
```

`as(...)` chuyển publisher hiện tại cho hàm được cung cấp. Cách viết này giúp ranh giới transaction xuất hiện ở cuối pipeline và dễ nhìn thấy toàn bộ công việc được bọc.

### 7.4. Dùng execute(...) khi cần TransactionStatus

`execute(...)` cho phép nhận `ReactiveTransaction` trong callback:

```java
Flux<Order> result = transactionalOperator.execute(status ->
    orderRepository.findByStatus("PENDING")
        .flatMap(order -> process(order))
);
```

API này trả về `Flux<T>`. Có thể dùng khi cần thao tác với trạng thái transaction theo API được cung cấp. Không nên gọi commit thủ công trong callback khi `TransactionalOperator` đang quản lý vòng đời; để operator kết thúc transaction theo tín hiệu của publisher.

## 8. Dùng @Transactional cho reactive method

Spring hỗ trợ declarative transaction với `@Transactional`. Với reactive method trả về `Mono` hoặc `Flux`, Spring sử dụng `ReactiveTransactionManager` và quản lý transaction theo subscription.

```java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final OrderLineRepository lineRepository;

    public OrderService(
            OrderRepository orderRepository,
            OrderLineRepository lineRepository) {
        this.orderRepository = orderRepository;
        this.lineRepository = lineRepository;
    }

    @Transactional
    public Mono<Order> create(CreateOrderRequest request) {
        return orderRepository.save(toOrder(request))
            .flatMap(order -> lineRepository.saveAll(
                    toLines(order, request))
                .then(Mono.just(order)));
    }
}
```

Khi phương thức được gọi qua Spring proxy và publisher được subscribe, các thao tác trong pipeline có thể tham gia cùng reactive transaction.

### 8.1. Chọn đúng transaction manager

Ứng dụng có thể đồng thời dùng JDBC/JPA và R2DBC. `PlatformTransactionManager` dành cho transaction imperative, còn R2DBC cần `ReactiveTransactionManager`, thường là `R2dbcTransactionManager`.

Nếu có nhiều manager, có thể chỉ rõ:

```java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Order> create(CreateOrderRequest request) {
    return orderRepository.save(toOrder(request));
}
```

Tên bean phải khớp cấu hình thực tế của ứng dụng. Không giả định annotation tự chọn đúng manager chỉ vì phương thức trả về `Mono`.

### 8.2. Phải đi qua Spring proxy

`@Transactional` dựa trên cơ chế proxy trong cấu hình Spring thông thường. Gọi một phương thức transactional từ bên ngoài bean qua proxy sẽ kích hoạt interceptor. Gọi nội bộ một phương thức khác trên cùng instance (`this.someTransactionalMethod()`) thường không đi qua proxy nên annotation của phương thức được gọi có thể không được áp dụng.

Nếu cần transaction boundary riêng, hãy tổ chức service bean phù hợp hoặc dùng `TransactionalOperator` tường minh. Không dựa vào self-invocation để tạo một transaction mới.

### 8.3. Phương thức cần trả publisher

Đối với reactive transaction, phương thức nên trả về publisher mà Spring có thể bọc và quản lý. Nếu method trả `void` hoặc gọi `subscribe()` rồi trả về ngay, transaction interceptor không thể quản lý toàn bộ công việc bất đồng bộ theo cách mong muốn.

## 9. Khác biệt giữa TransactionalOperator và @Transactional

| Tiêu chí | `TransactionalOperator` | `@Transactional` |
|---|---|---|
| Cách khai báo | Bọc publisher tường minh trong code | Annotation trên method/class |
| Ranh giới | Vị trí `transactional(...)` hoặc `as(...)` | Ranh giới method được Spring proxy quản lý |
| Phù hợp | Pipeline cần transaction ở giữa hoặc ranh giới linh hoạt | Use case/service method có ranh giới rõ |
| Cần proxy | Không cần AOP proxy cho operator | Có trong cơ chế proxy mặc định |
| Chọn manager | Truyền `ReactiveTransactionManager` khi tạo operator | Chọn manager qua cấu hình/thuộc tính annotation |
| Khả năng đọc | Ranh giới hiện ngay trong pipeline | Annotation thể hiện ranh giới ở method/class |

Hai cách đều dựa trên reactive transaction management của Spring. Chọn một cách phù hợp với cấu trúc use case; không bọc cùng một publisher bằng nhiều transaction boundary lồng nhau chỉ vì muốn “an toàn hơn”. Transaction propagation và nesting cần được thiết kế có chủ đích.

## 10. Vị trí của onErrorResume quyết định transaction có thấy lỗi hay không

Một trong những lỗi khó phát hiện nhất là bắt lỗi bên trong publisher transactional rồi chuyển thành giá trị thành công. Khi đó transaction boundary có thể chỉ nhìn thấy `onComplete` và commit.

### 10.1. Bắt lỗi bên trong transaction: có thể commit

```java
Mono<Order> work = orderRepository.save(order)
    .flatMap(this::saveLines)
    .onErrorResume(error -> {
        log.error("Không lưu được chi tiết đơn hàng", error);
        return Mono.empty();
    });

return transactionalOperator.transactional(work);
```

`onErrorResume` nằm trong publisher được bọc. Nếu nó chuyển lỗi thành `Mono.empty()`, publisher `work` hoàn tất bình thường. Transaction operator có thể commit những thay đổi đã thực hiện trước khi lỗi xảy ra.

Điều này có thể tạo trạng thái không nhất quán nếu order đã được INSERT nhưng order lines thất bại rồi bị nuốt lỗi.

### 10.2. Bắt lỗi bên ngoài transaction: rollback trước fallback

```java
return transactionalOperator.transactional(
        orderRepository.save(order)
            .flatMap(this::saveLines)
    )
    .onErrorResume(error -> {
        log.error("Không tạo được đơn hàng", error);
        return Mono.empty();
    });
```

Ở đây transaction operator nhận lỗi từ công việc bên trong và thực hiện rollback. Sau khi publisher transactional kết thúc bằng lỗi, `onErrorResume` bên ngoài mới chuyển lỗi thành kết quả rỗng cho caller.

### 10.3. Nguyên tắc đặt error handler

- Nếu lỗi phải làm rollback, để lỗi truyền qua transaction boundary.
- Nếu cần fallback sau rollback, đặt fallback bên ngoài publisher transactional.
- Nếu chủ ý xử lý lỗi và tiếp tục transaction, xác định rõ dữ liệu đã thay đổi và trạng thái transaction có còn hợp lệ không.
- Không biến lỗi persistence thành `Mono.empty()` chỉ để tránh trả lỗi cho API.
- Log và ánh xạ lỗi ở tầng phù hợp, nhưng không che mất tín hiệu cần thiết cho transaction manager.

Với `@Transactional`, nguyên tắc tương tự: nếu publisher trả về từ method đã chuyển lỗi thành complete trước khi interceptor quan sát, transaction có thể commit. Hãy xác định rõ lỗi nào được coi là thất bại của use case.

## 11. Rollback rules với @Transactional

Với declarative transaction, Spring áp dụng rollback rules. Theo mặc định truyền thống, unchecked exception (`RuntimeException`) và `Error` kích hoạt rollback; checked exception không tự động kích hoạt rollback trừ khi có cấu hình tương ứng.

Ví dụ:

```java
@Transactional(rollbackFor = Exception.class)
public Mono<Order> create(CreateOrderRequest request) {
    return orderRepository.save(toOrder(request))
        .flatMap(order -> validateAndSaveLines(order, request));
}
```

`rollbackFor` mở rộng quy tắc rollback cho loại exception được chỉ định. Có thể dùng `noRollbackFor` khi một exception được định nghĩa là không yêu cầu rollback, nhưng cần cân nhắc kỹ vì transaction có thể commit một phần dữ liệu dù caller nhận lỗi.

Khi làm việc với `TransactionalOperator`, lỗi phát ra từ publisher là tín hiệu thất bại của pipeline và operator xử lý rollback theo semantics programmatic transaction. Nếu cần quy tắc rollback đặc biệt theo loại exception, hãy thiết kế việc phân loại lỗi và transaction definition phù hợp với API/version của Spring đang sử dụng; đừng giả định annotation rollback rules và mọi operator tùy chỉnh có cấu hình hoàn toàn giống nhau.

## 12. Mono.empty(), lỗi nghiệp vụ và số hàng bị ảnh hưởng

Không phải mọi kết quả “không có thay đổi” đều là lỗi kỹ thuật. Ví dụ update có thể trả về 0 hàng bị ảnh hưởng:

```java
Mono<Long> updated = template.update(query, update, Order.class);
```

Nếu kết quả là `0L`, transaction vẫn có thể hoàn tất bình thường. Nếu nghiệp vụ yêu cầu phải cập nhật đúng một hàng, hãy biến kết quả đó thành lỗi trước khi kết thúc transaction:

```java
Mono<Void> markPaid(Long orderId) {
    return orderRepository.updateStatus(orderId, "PAID")
        .flatMap(rows -> rows == 1
            ? Mono.empty()
            : Mono.error(new OrderStateConflictException(orderId)))
        .then();
}
```

Khi error truyền tới transaction boundary, transaction có thể rollback. Nếu chỉ log `rows == 0` rồi trả `Mono.empty()`, transaction có thể commit vì publisher hoàn tất thành công.

## 13. Tất cả thao tác phải tham gia cùng transaction context

Reactive transaction không dựa vào `ThreadLocal` như cách quản lý transaction imperative truyền thống. Spring gắn transaction resource với Reactor Context của subscription.

Điều đó có nghĩa:

- Các toán tử Reactor được compose trong cùng subscription có thể tiếp tục mang transaction context qua các thread khác nhau.
- `publishOn` hoặc `subscribeOn` không tự làm mất transaction context khi dùng Reactor đúng cách.
- Tạo một subscription mới bằng `subscribe()` thủ công sẽ tạo một luồng thực thi độc lập, không tự thừa hưởng transaction của luồng cha.
- Thao tác dùng `ConnectionFactory` khác không tham gia transaction hiện tại.
- Thao tác truy cập connection trực tiếp phải dùng cơ chế Spring-aware nếu cần lấy connection đã gắn với transaction.

### 13.1. Dùng DatabaseClient/repository/template

Các abstraction Spring Data R2DBC được thiết kế để phối hợp với connection được Spring quản lý. Ví dụ:

```java
@Transactional
public Mono<Void> createOrderAndAudit(Order order, AuditEntry audit) {
    return orderRepository.save(order)
        .flatMap(saved -> auditRepository.save(
            audit.withOrderId(saved.getId())
        ))
        .then();
}
```

Nếu hai repository dùng cùng `ConnectionFactory` và transaction manager, các thao tác có thể tham gia cùng transaction.

### 13.2. Cẩn thận khi gọi ConnectionFactory.create() trực tiếp

Đoạn code sau tạo connection trực tiếp:

```java
Mono.from(connectionFactory.create())
    .flatMap(connection -> ...);
```

Trong một transaction Spring đang hoạt động, gọi raw `create()` có thể lấy một connection độc lập thay vì connection đã được transaction manager bind vào Reactor Context. Nếu thao tác cần tham gia transaction, hãy dùng `DatabaseClient`, `R2dbcEntityTemplate`, repository hoặc tiện ích Spring như `ConnectionFactoryUtils` theo đúng phiên bản.

Đây là lỗi dễ tạo ra tình huống một phần dữ liệu rollback nhưng thao tác dùng connection độc lập vẫn commit.

## 14. Không gọi subscribe() bên trong transactional service

Không nên tự subscribe một thao tác database bên trong method rồi trả về ngay:

```java
@Transactional
public Mono<Void> createOrder(Order order) {
    orderRepository.save(order).subscribe();
    return Mono.empty();
}
```

Trong ví dụ này, subscription của `save` tách khỏi publisher mà transaction interceptor quản lý. Method trả về `Mono.empty()` có thể hoàn tất ngay, transaction boundary không chờ thao tác save độc lập. Lỗi từ subscription riêng cũng không được truyền đúng vào caller.

Hãy compose publisher:

```java
@Transactional
public Mono<Void> createOrder(Order order) {
    return orderRepository.save(order).then();
}
```

Nguyên tắc tương tự áp dụng cho `block()`: không chặn reactive pipeline để chờ kết quả database. Hãy nối các publisher bằng `map`, `flatMap`, `then`, `zip` hoặc toán tử phù hợp.

## 15. Transaction lồng nhau và propagation

Khi một transactional service gọi service transactional khác, Spring áp dụng propagation được cấu hình. Với reactive transaction, context và resource được truyền theo subscription.

Các propagation thường gặp:

| Propagation | Ý nghĩa khái quát |
|---|---|
| `REQUIRED` | Tham gia transaction hiện có; nếu chưa có thì tạo transaction mới |
| `REQUIRES_NEW` | Tạo transaction độc lập mới, tạm tách transaction hiện tại theo khả năng manager |
| `SUPPORTS` | Tham gia nếu có transaction; nếu không thì chạy không transaction |
| `MANDATORY` | Yêu cầu phải có transaction hiện tại |
| `NOT_SUPPORTED` | Tạm chạy ngoài transaction hiện tại |
| `NEVER` | Không cho phép có transaction hiện tại |
| `NESTED` | Transaction lồng nhau/savepoint nếu transaction manager hỗ trợ |

Khả năng hỗ trợ thực tế phụ thuộc `ReactiveTransactionManager` và driver. Không nên giả định mọi propagation hoặc nested savepoint đều được hỗ trợ giống nhau ở mọi R2DBC driver.

Ví dụ:

```java
@Transactional(propagation = Propagation.REQUIRED)
public Mono<Void> createOrder(...) {
    return orderRepository.save(...)
        .flatMap(order -> auditService.writeAudit(order));
}
```

Nếu `auditService.writeAudit` cũng dùng `REQUIRED` và cùng transaction manager, nó có thể tham gia transaction hiện tại. Nếu audit phát lỗi và lỗi truyền ra ngoài, transaction chung có thể rollback.

`REQUIRES_NEW` cần được dùng có chủ đích. Nếu transaction ngoài rollback nhưng transaction audit độc lập đã commit, audit record vẫn tồn tại. Điều này có thể phù hợp cho audit thất bại hoặc trạng thái retry, nhưng không phù hợp nếu audit phải nguyên tử với dữ liệu chính.

## 16. Transaction và các Publisher chạy song song

Có thể kết hợp các thao tác độc lập bằng `Mono.zip`, nhưng không nên mặc định một R2DBC connection có thể chạy nhiều statement song song an toàn. Nhiều driver/connection yêu cầu các thao tác trên cùng connection được tuần tự hóa hoặc có giới hạn protocol.

Ví dụ:

```java
@Transactional
public Mono<DashboardData> loadData(Long id) {
    Mono<Customer> customer = customerRepository.findById(id);
    Mono<List<Order>> orders = orderRepository.findByCustomerId(id)
        .collectList();

    return Mono.zip(customer, orders)
        .map(tuple -> new DashboardData(tuple.getT1(), tuple.getT2()));
}
```

Đây là ví dụ composition trong một transaction. Tuy nhiên, nếu cả hai truy vấn dùng cùng connection transaction-bound, driver có thể tuần tự hóa chúng hoặc không cho thực thi đồng thời. Nếu cần thứ tự rõ ràng, compose tuần tự:

```java
@Transactional
public Mono<CustomerDetail> loadDetail(Long id) {
    return customerRepository.findById(id)
        .flatMap(customer -> orderRepository.findByCustomerId(id)
            .collectList()
            .map(orders -> new CustomerDetail(customer, orders)));
}
```

Lựa chọn phụ thuộc driver, workload và yêu cầu nhất quán. Transaction không có nghĩa mọi Publisher con đều chạy song song trên cùng connection.

## 17. Transaction kéo dài và tài nguyên

Transaction thường giữ connection cho tới khi commit hoặc rollback. Nếu publisher transactional bao gồm tác vụ chậm như gọi HTTP, chờ người dùng, đọc file lớn hoặc xử lý CPU dài, connection có thể bị giữ trong suốt thời gian đó.

Ví dụ không nên giữ transaction qua lời gọi HTTP chậm nếu không cần:

```java
@Transactional
public Mono<Order> createOrder(CreateOrderRequest request) {
    return orderRepository.save(toOrder(request))
        .flatMap(order -> paymentClient.authorize(order)
            .thenReturn(order));
}
```

Trong ví dụ này, transaction có thể giữ connection trong khi chờ payment service. Nếu payment service chậm, pool database có thể bị bão hòa.

Hãy cân nhắc tách workflow:

1. Lưu trạng thái đơn hàng ban đầu trong transaction ngắn.
2. Commit transaction.
3. Gọi payment service ngoài transaction.
4. Mở transaction mới để cập nhật kết quả thanh toán.
5. Dùng trạng thái trung gian, idempotency và quy trình bù trừ nếu một bước thất bại.

Đây là cách tiếp cận workflow/saga ở mức nghiệp vụ; không phải transaction ACID xuyên qua HTTP service.

## 18. Kiểm thử thời điểm commit và rollback

Kiểm thử transaction cần xác nhận trạng thái database sau khi publisher kết thúc, không chỉ xác nhận giá trị mà publisher phát ra.

### 18.1. Kiểm thử rollback khi có lỗi

Ví dụ kiểm thử service:

```java
StepVerifier.create(orderService.createOrder(requestThatFailsAfterOrderInsert()))
    .expectError(OrderLinePersistenceException.class)
    .verify();

StepVerifier.create(orderRepository.count())
    .expectNext(0L)
    .verifyComplete();
```

Ví dụ giả định order được INSERT trước khi lỗi xảy ra ở bước tiếp theo, và cả hai thao tác dùng cùng transaction. Truy vấn count sau đó xác nhận dữ liệu đã rollback.

### 18.2. Kiểm thử commit khi complete

```java
StepVerifier.create(orderService.createOrder(validRequest))
    .assertNext(order -> assertNotNull(order.getId()))
    .verifyComplete();

StepVerifier.create(orderRepository.count())
    .expectNext(1L)
    .verifyComplete();
```

Test cần xác nhận thao tác đã được subscribe và hoàn tất trước khi đọc lại trạng thái.

### 18.3. Kiểm thử Mono.empty()

Nếu nghiệp vụ coi kết quả rỗng là thành công, hãy xác nhận transaction commit như thiết kế. Nếu không tìm thấy dữ liệu phải rollback, test cần xác nhận service chuyển empty thành exception trước transaction boundary.

### 18.4. Kiểm thử cancellation

Cancellation khó kiểm thử hơn complete/error. Có thể dùng `StepVerifier` với subscription control để hủy trước khi nguồn hoàn tất, sau đó xác nhận transaction rollback và connection được trả về pool. Test nên chạy trên database/driver thật hoặc môi trường tích hợp tương thích, vì hành vi cancellation và cleanup có thể phụ thuộc driver.

### 18.5. Tránh để test tự bao quanh transaction cần kiểm tra

Một số test framework có thể tự mở transaction cho test method và rollback sau test. Điều đó có thể che giấu việc service đã commit hay rollback như thế nào. Khi kiểm tra ranh giới transaction của service, hãy thiết kế test để quan sát trạng thái sau khi transaction của service kết thúc, không để transaction bên ngoài làm kết quả khó diễn giải.

## 19. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ transaction bắt đầu khi tạo `Mono` | Hiểu sai thời điểm thực thi và side effect | Nhớ transaction reactive bắt đầu khi publisher transactional được subscribe |
| Tạo publisher nhưng không subscribe | SQL không chạy, transaction không được thực thi | Trả publisher cho framework hoặc compose vào pipeline được tiêu thụ |
| Gọi `subscribe()` bên trong service | Tạo luồng độc lập, transaction không chờ và không nhận lỗi | Compose publisher bằng toán tử Reactor |
| Gọi `block()` trong reactive transaction | Chặn thread và phá mô hình reactive | Dùng `flatMap`, `then`, `zip` hoặc operator phù hợp |
| Dùng `Mono.empty()` khi muốn rollback | Publisher complete bình thường nên transaction có thể commit | Chuyển thành error nếu đó là thất bại nghiệp vụ |
| Nuốt lỗi bằng `onErrorResume` bên trong boundary | Transaction có thể nhìn thấy complete và commit | Đặt fallback bên ngoài boundary nếu cần rollback trước |
| Dùng sai transaction manager | R2DBC operation không được quản lý bởi manager mong muốn | Dùng `ReactiveTransactionManager` và chỉ rõ bean khi có nhiều manager |
| Gọi method transactional qua self-invocation | Proxy không chặn lời gọi nội bộ | Tổ chức bean hoặc dùng `TransactionalOperator` |
| Dùng raw `ConnectionFactory.create()` | Có thể lấy connection ngoài transaction context | Dùng Spring-aware client hoặc `ConnectionFactoryUtils` |
| Dùng ConnectionFactory khác trong cùng workflow | Thao tác không thuộc cùng transaction | Dùng cùng connection factory hoặc thiết kế consistency riêng |
| Giữ transaction trong lúc gọi HTTP lâu | Giữ connection, tăng pool pressure | Tách transaction ngắn và workflow ngoài database |
| Cho rằng `Mono.zip` tự tạo transaction | Composition không tạo transaction | Dùng `@Transactional` hoặc `TransactionalOperator` |
| Giả định mọi propagation/savepoint đều được hỗ trợ | Hành vi có thể khác driver/manager | Xác nhận capability của transaction manager và driver |
| Trả Flux dài hạn trong transaction | Giữ transaction/connection trong thời gian stream | Giới hạn stream hoặc tách transaction theo batch |

## 20. Quy trình xác định ranh giới transaction

Khi thiết kế một use case reactive, hãy trả lời các câu hỏi theo thứ tự:

1. Những thao tác database nào phải thành công hoặc rollback cùng nhau?
2. Tất cả thao tác có dùng cùng `ConnectionFactory` không?
3. Nên đặt boundary ở service method bằng `@Transactional` hay tại vị trí pipeline bằng `TransactionalOperator`?
4. Publisher có được trả về caller và subscribe đúng một lần theo ý định không?
5. Có code eager nào chạy trước subscription cần chuyển vào `defer` không?
6. Trường hợp không có dữ liệu là complete hợp lệ hay lỗi cần rollback?
7. Lỗi nào phải truyền tới boundary, lỗi nào có fallback bên ngoài boundary?
8. Downstream có thể cancel hoặc timeout giữa chừng không?
9. Transaction có giữ connection trong lúc chờ HTTP, file hoặc xử lý CPU lâu không?
10. Các thao tác song song có tương thích với driver và connection transaction-bound không?
11. Đã kiểm thử commit, rollback, empty, error và cancellation trên database mục tiêu chưa?

## 21. Nguyên tắc cần nhớ

- Reactive transaction gắn với subscription của publisher, không bắt đầu chỉ vì tạo `Mono` hoặc `Flux`.
- Publisher không được subscribe thì thao tác database lazy thường không chạy.
- Mỗi subscription có thể thực thi lại công việc và tạo transaction riêng.
- `Mono.defer` trì hoãn việc tạo/thực hiện công việc đến lúc subscription khi cần.
- Publisher hoàn tất bình thường (`onComplete`), kể cả `Mono.empty()`, thường dẫn đến commit.
- Lỗi truyền qua transaction boundary dẫn đến rollback theo quy tắc transaction.
- Cancellation của publisher transactional trước khi hoàn tất được xử lý theo semantics rollback của reactive transaction.
- Vị trí `onErrorResume`, `take`, timeout và các toán tử short-circuit có thể thay đổi tín hiệu mà transaction boundary nhận được.
- `@Transactional` reactive cần `ReactiveTransactionManager`, proxy phù hợp và method trả `Mono`/`Flux`.
- `TransactionalOperator` bọc publisher tường minh và không cần AOP proxy.
- Không gọi `subscribe()` hoặc `block()` bên trong transactional service.
- Dùng cùng `ConnectionFactory` và Spring-aware data access để các thao tác tham gia transaction context.
- Không mặc định raw `ConnectionFactory.create()` lấy connection transaction-bound.
- Reactive transaction context đi theo Reactor Context, không dựa vào ThreadLocal.
- Tránh giữ transaction/connection trong các tác vụ mạng hoặc stream dài không cần thiết.
- Kiểm thử trạng thái database sau commit/rollback và xác nhận cancellation/cleanup trên driver thực tế.

Trong Spring Data Relational R2DBC, thời điểm bắt đầu, commit và rollback được quyết định bởi vòng đời thực thi reactive. Tạo publisher chỉ đăng ký công việc; subscription kích hoạt transaction; complete thành công cho phép commit; error hoặc cancellation được transaction manager xử lý theo quy tắc rollback. Khi đặt đúng ranh giới, giữ lỗi đi tới transaction manager và để toàn bộ thao tác dùng cùng transaction context, ứng dụng có thể duy trì tính nguyên tử mà vẫn tận dụng mô hình non-blocking của R2DBC.
