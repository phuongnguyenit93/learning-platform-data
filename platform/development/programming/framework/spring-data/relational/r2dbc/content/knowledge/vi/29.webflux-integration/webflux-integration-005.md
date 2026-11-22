# Đặt ranh giới giao dịch ở tầng dịch vụ

## 1. Vì sao cần đặt transaction ở tầng dịch vụ?

Trong ứng dụng Spring WebFlux dùng Spring Data Relational R2DBC, một thao tác nghiệp vụ thường gồm nhiều bước truy cập dữ liệu. Ví dụ, xác nhận đơn hàng có thể cần:

1. Đọc đơn hàng.
2. Kiểm tra trạng thái hiện tại.
3. Kiểm tra và cập nhật tồn kho.
4. Cập nhật trạng thái đơn hàng.
5. Ghi một bản ghi lịch sử hoặc outbox event.

Nếu từng repository method tự quản lý một transaction độc lập, một bước có thể commit thành công trong khi bước tiếp theo thất bại. Khi đó dữ liệu có thể rơi vào trạng thái không nhất quán.

Ranh giới transaction nên phản ánh **một đơn vị công việc nghiệp vụ cần cùng thành công hoặc cùng thất bại**. Trong ứng dụng phân tầng, tầng dịch vụ (service layer) thường là nơi biết đầy đủ use case và có thể phối hợp nhiều repository. Vì vậy đây thường là vị trí phù hợp để xác định transaction boundary.

Ví dụ, khi xác nhận đơn hàng, việc cập nhật order, trừ tồn kho và ghi outbox event có thể cần nằm trong cùng một transaction database. Service điều phối các bước đó và bao bọc publisher bằng transaction manager R2DBC.

Controller chỉ nhận HTTP request và trả publisher. Repository tập trung vào thao tác lưu trữ. Service quyết định các bước nào thuộc cùng một giao dịch.

Đặt transaction ở tầng dịch vụ giúp:

- Bảo vệ tính nguyên tử của một use case qua nhiều repository.
- Tránh commit từng bước quá sớm.
- Làm rõ nơi bắt đầu và kết thúc transaction.
- Giữ controller mỏng và repository tập trung vào persistence.
- Kiểm thử hành vi commit/rollback theo nghiệp vụ.
- Giới hạn thời gian giữ connection bằng cách chỉ bao bọc các thao tác cần transaction.

## 2. Transaction boundary là gì?

Transaction boundary là phạm vi các thao tác được database xử lý như một đơn vị commit hoặc rollback.

Giả sử nghiệp vụ chuyển tiền cần trừ tài khoản nguồn và cộng tài khoản đích. Hai thao tác phải cùng thành công:

~~~text
HTTP request
     |
     v
TransferController
     |
     v
TransferService  <--- transaction boundary
     |
     +-- đọc tài khoản nguồn
     |
     +-- kiểm tra số dư
     |
     +-- trừ tài khoản nguồn
     |
     +-- cộng tài khoản đích
     |
     +-- ghi lịch sử chuyển tiền
     |
     v
COMMIT nếu toàn bộ thành công
ROLLBACK nếu có lỗi
~~~

Nếu bước cộng tiền thất bại sau khi đã trừ tiền nguồn, transaction rollback sẽ hoàn tác thay đổi trừ tiền trong cùng database transaction.

Transaction không tự bao gồm mọi hoạt động xảy ra trong HTTP request. Nó chỉ quản lý các tài nguyên tham gia transaction thông qua transaction manager tương ứng.

Ví dụ, một lời gọi HTTP tới dịch vụ khác, gửi email hoặc ghi file không tự động được rollback khi R2DBC transaction rollback.

## 3. Vì sao service layer là vị trí phù hợp?

### 3.1. Controller không nên quyết định transaction nghiệp vụ

Controller chịu trách nhiệm chuyển đổi HTTP request thành lời gọi ứng dụng và chuyển kết quả thành HTTP response.

Ví dụ:

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping("/{id}/confirm")
    public Mono<OrderResponse> confirm(@PathVariable Long id) {
        return orderService.confirm(id)
            .map(OrderResponse::from);
    }
}
~~~

Controller không cần biết có bao nhiêu repository được gọi hoặc transaction được cấu hình ra sao. Nó chỉ trả publisher từ service.

Không gọi subscribe() trong controller để tự chạy publisher. WebFlux cần nhận publisher để điều phối việc subscribe, backpressure, cancellation và ghi response.

### 3.2. Repository không nên điều phối toàn bộ use case

Repository biểu diễn thao tác truy cập dữ liệu:

~~~java
public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {
}

public interface InventoryRepository
        extends ReactiveCrudRepository<Inventory, Long> {
}

public interface OutboxRepository
        extends ReactiveCrudRepository<OutboxEvent, Long> {
}
~~~

Repository không biết đầy đủ ý nghĩa nghiệp vụ của việc xác nhận đơn hàng. Nó cung cấp các thao tác đọc/ghi để service phối hợp.

Một repository method có thể có transaction semantics riêng theo cấu hình Spring Data, nhưng transaction ở repository không tự bao phủ toàn bộ chuỗi thao tác của một use case qua nhiều repository. Service cần xác định phạm vi chung.

### 3.3. Service nhìn thấy toàn bộ đơn vị nghiệp vụ

Service có đủ thông tin để quyết định:

- Cần đọc những aggregate nào.
- Những thay đổi nào phải commit cùng nhau.
- Điều kiện nghiệp vụ nào phải được kiểm tra trước khi ghi.
- Khi nào cần rollback.
- Có thể gọi hệ thống bên ngoài trước hay sau transaction.
- Có cần outbox hoặc quy trình bù hay không.

Vì vậy, service layer thường là nơi đặt ranh giới transaction phù hợp nhất cho một use case.

## 4. Reactive transaction khác transaction imperative như thế nào?

Trong ứng dụng imperative dùng JDBC, transaction thường được gắn với thread thông qua ThreadLocal. Trong ứng dụng reactive dùng R2DBC, transaction context được truyền theo Reactor Context của subscription.

Điều này có ý nghĩa quan trọng:

- Một reactive pipeline có thể chạy qua nhiều thread.
- Transaction không phụ thuộc vào một thread cố định.
- Spring gắn thông tin transaction và connection với Reactor Context.
- Các thao tác R2DBC trong cùng reactive transaction có thể sử dụng connection được transaction manager quản lý.
- Không nên tự tạo subscription tách rời hoặc gọi block() để lấy kết quả.

Với Spring WebFlux và R2DBC, hãy dùng reactive transaction manager như R2dbcTransactionManager. Transaction manager imperative dành cho JDBC không thay thế transaction manager R2DBC.

### 4.1. Publisher phải được trả về từ service

Phương thức service nên trả Mono hoặc Flux để transaction interceptor có thể quản lý toàn bộ vòng đời publisher.

Ví dụ:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Order> confirm(Long orderId) {
    return orderRepository.findById(orderId)
        .flatMap(order -> {
            order.setStatus("CONFIRMED");
            return orderRepository.save(order);
        });
}
~~~

Transaction reactive được gắn với việc thực thi publisher. Trong mô hình reactive, công việc thực tế diễn ra khi publisher được subscribe.

Không viết:

~~~java
@Transactional
public Mono<Void> confirm(Long orderId) {
    orderRepository.findById(orderId)
        .flatMap(order -> orderRepository.save(order))
        .subscribe();

    return Mono.empty();
}
~~~

subscribe() tạo một subscription độc lập. Phương thức có thể trả Mono.empty() và transaction interceptor kết thúc trước khi thao tác save trong subscription kia hoàn tất. Lỗi và transaction context của subscription đó cũng không được điều phối như một phần của publisher mà service trả về.

Hãy trả chính publisher:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Void> confirm(Long orderId) {
    return orderRepository.findById(orderId)
        .flatMap(order -> orderRepository.save(order))
        .then();
}
~~~

### 4.2. Không gọi block() trong reactive transaction

Không chuyển một publisher R2DBC thành lời gọi đồng bộ bên trong service:

~~~java
@Transactional
public Order confirm(Long orderId) {
    Order order = orderRepository.findById(orderId).block();
    order.setStatus("CONFIRMED");
    return orderRepository.save(order).block();
}
~~~

Cách này chặn thread, tạo các subscription riêng và không dùng đúng reactive transaction model. Trong WebFlux, hãy nối các publisher bằng flatMap, map, then hoặc các toán tử Reactor phù hợp.

### 4.3. Reactor Context thay cho giả định ThreadLocal

Transaction context có thể theo reactive pipeline khi các toán tử Reactor chuyển scheduler. Không nên giả định rằng tất cả callback chạy trên cùng thread.

Nếu tự tạo thread, tự gọi subscribe(), hoặc chuyển công việc sang executor không tích hợp Reactor Context, thông tin transaction có thể không còn được truyền theo cách mong đợi.

Giữ các thao tác trong một pipeline được trả về từ service giúp Spring quản lý transaction context nhất quán.

## 5. Cấu hình R2DBC transaction manager

Spring Data R2DBC sử dụng ConnectionFactory để lấy connection. Reactive transaction manager tương ứng là R2dbcTransactionManager.

Ví dụ cấu hình:

~~~java
@Configuration
public class R2dbcTransactionConfiguration {

    @Bean("r2dbcTransactionManager")
    ReactiveTransactionManager r2dbcTransactionManager(
            ConnectionFactory connectionFactory) {

        return new R2dbcTransactionManager(connectionFactory);
    }
}
~~~

Nếu ứng dụng chỉ có một ConnectionFactory, Spring Boot có thể tự cấu hình một số thành phần tùy phiên bản và điều kiện auto-configuration. Hãy xác nhận transaction manager thực tế mà ứng dụng sử dụng.

Nếu có nhiều ConnectionFactory hoặc nhiều transaction manager, cần chỉ định manager rõ ràng tại ranh giới transaction:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<Order> confirm(Long orderId) {
    // ...
}
~~~

Transaction manager phải quản lý cùng ConnectionFactory mà các repository trong use case sử dụng. Nếu service mở transaction trên manager A nhưng repository lại dùng ConnectionFactory B, thao tác repository B không tự động tham gia transaction A.

### 5.1. Transaction manager phải phù hợp với loại truy cập dữ liệu

| Công nghệ truy cập | Transaction manager tương ứng |
|---|---|
| Spring Data R2DBC | R2dbcTransactionManager |
| JDBC / JdbcTemplate | DataSourceTransactionManager hoặc JdbcTransactionManager tùy cấu hình |
| JPA | JpaTransactionManager |
| Nhiều nguồn dữ liệu | Manager riêng cho từng nguồn hoặc giải pháp điều phối được thiết kế riêng |

Không dùng transaction manager JDBC chỉ vì ứng dụng đang chạy trên WebFlux. Loại transaction manager phải khớp với tài nguyên database mà publisher sử dụng.

## 6. Đặt transaction bằng @Transactional ở service

### 6.1. Ví dụ use case cập nhật nhiều repository

Giả sử xác nhận đơn hàng cần:

- Đọc order.
- Đọc inventory.
- Kiểm tra số lượng còn lại.
- Trừ tồn kho.
- Cập nhật order.
- Ghi outbox event.

Các thao tác ghi phải cùng commit hoặc rollback:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final InventoryRepository inventoryRepository;
    private final OutboxRepository outboxRepository;

    public OrderService(
            OrderRepository orderRepository,
            InventoryRepository inventoryRepository,
            OutboxRepository outboxRepository) {
        this.orderRepository = orderRepository;
        this.inventoryRepository = inventoryRepository;
        this.outboxRepository = outboxRepository;
    }

    @Transactional(transactionManager = "r2dbcTransactionManager")
    public Mono<Order> confirm(Long orderId) {
        return orderRepository.findById(orderId)
            .switchIfEmpty(Mono.error(
                new OrderNotFoundException(orderId)
            ))
            .flatMap(order ->
                inventoryRepository.findById(order.getProductId())
                    .switchIfEmpty(Mono.error(
                        new InventoryNotFoundException(order.getProductId())
                    ))
                    .flatMap(inventory -> {
                        if (inventory.getAvailable() < order.getQuantity()) {
                            return Mono.error(
                                new InsufficientInventoryException(orderId)
                            );
                        }

                        inventory.setAvailable(
                            inventory.getAvailable() - order.getQuantity()
                        );

                        order.setStatus("CONFIRMED");

                        return inventoryRepository.save(inventory)
                            .then(orderRepository.save(order));
                    })
            )
            .flatMap(savedOrder ->
                outboxRepository.save(
                    OutboxEvent.orderConfirmed(savedOrder.getId())
                ).thenReturn(savedOrder)
            );
    }
}
~~~

Ví dụ giả định cả ba repository dùng cùng ConnectionFactory và transaction manager. Khi đó các thao tác ghi có thể tham gia cùng một reactive transaction.

Nếu bước ghi outbox thất bại, lỗi truyền ra khỏi publisher và transaction có thể rollback cả thay đổi inventory lẫn order.

Đây là lý do service layer phù hợp: nó biết toàn bộ các thao tác nào phải cùng thành công.

### 6.2. Không đặt transaction ở mọi method một cách máy móc

Không phải mọi service method đều cần transaction ghi:

- Một thao tác đọc đơn giản có thể không cần transaction tường minh.
- Một use case ghi một entity có thể dựa vào transaction semantics của repository nếu phù hợp.
- Một use case phối hợp nhiều thao tác database cần transaction boundary rõ ràng.
- Một quy trình gọi dịch vụ ngoài trong thời gian dài thường cần tách transaction.

Hãy quyết định theo yêu cầu nhất quán của nghiệp vụ, không chỉ theo số lượng method được gọi.

### 6.3. @Transactional ở cấp lớp và cấp method

Có thể đặt @Transactional ở cấp lớp:

~~~java
@Service
@Transactional(transactionManager = "r2dbcTransactionManager")
public class OrderService {
    // ...
}
~~~

Các method phù hợp trong lớp sẽ dùng transaction mặc định này. Một method có thể ghi đè cấu hình ở cấp method:

~~~java
@Transactional(
    transactionManager = "r2dbcTransactionManager",
    readOnly = true
)
public Flux<Order> findOpenOrders() {
    return orderRepository.findByStatus("OPEN");
}
~~~

Dùng annotation cấp method khi các use case có yêu cầu transaction khác nhau. Cấu hình cấp lớp tiện lợi nhưng có thể khiến method đọc hoặc thao tác dài vô tình nằm trong transaction không cần thiết.

## 7. Dùng TransactionalOperator cho transaction tường minh

Ngoài annotation, Spring cung cấp TransactionalOperator để bao bọc một publisher bằng transaction.

Cấu hình:

~~~java
@Configuration
public class TransactionalOperatorConfiguration {

    @Bean
    TransactionalOperator transactionalOperator(
            ReactiveTransactionManager r2dbcTransactionManager) {

        return TransactionalOperator.create(r2dbcTransactionManager);
    }
}
~~~

Sử dụng trong service:

~~~java
@Service
public class TransferService {

    private final AccountRepository accountRepository;
    private final TransactionalOperator transactionalOperator;

    public TransferService(
            AccountRepository accountRepository,
            TransactionalOperator transactionalOperator) {
        this.accountRepository = accountRepository;
        this.transactionalOperator = transactionalOperator;
    }

    public Mono<Void> transfer(
            Long sourceId,
            Long targetId,
            BigDecimal amount) {

        Mono<Void> work =
            accountRepository.findById(sourceId)
                .switchIfEmpty(Mono.error(
                    new AccountNotFoundException(sourceId)
                ))
                .flatMap(source ->
                    accountRepository.findById(targetId)
                        .switchIfEmpty(Mono.error(
                            new AccountNotFoundException(targetId)
                        ))
                        .flatMap(target -> {
                            if (source.getBalance().compareTo(amount) < 0) {
                                return Mono.error(
                                    new InsufficientBalanceException()
                                );
                            }

                            source.setBalance(
                                source.getBalance().subtract(amount)
                            );
                            target.setBalance(
                                target.getBalance().add(amount)
                            );

                            return accountRepository.save(source)
                                .then(accountRepository.save(target))
                                .then();
                        })
                );

        return transactionalOperator.transactional(work);
    }
}
~~~

TransactionalOperator giúp thấy rõ publisher nào được bao bọc bởi transaction. Cách này hữu ích khi:

- Chỉ một nhánh trong service cần transaction.
- Ranh giới transaction được xác định theo điều kiện runtime.
- Muốn dùng transaction manager cụ thể qua constructor injection.
- Cần tránh annotation proxy trong một số cấu trúc code.
- Muốn kiểm soát transaction trong một publisher composition.

### 7.1. Dùng execute khi cần TransactionStatus

TransactionalOperator còn cung cấp execute với callback nhận TransactionStatus:

~~~java
return transactionalOperator.execute(status ->
    performDatabaseWork()
        .onErrorResume(error -> {
            status.setRollbackOnly();
            return Mono.error(error);
        })
).then();
~~~

Trong ví dụ, lỗi được truyền tiếp và transaction sẽ rollback theo tín hiệu lỗi. setRollbackOnly hữu ích khi logic cần đánh dấu rollback một cách tường minh, nhưng không nên dùng thay cho việc thiết kế luồng lỗi rõ ràng.

execute trả về Flux cho publisher callback. Nếu callback chỉ có một kết quả, có thể dùng single(), singleOrEmpty() hoặc toán tử phù hợp với cardinality thực tế.

## 8. Chọn giữa @Transactional và TransactionalOperator

| Tiêu chí | @Transactional | TransactionalOperator |
|---|---|---|
| Cách khai báo | Annotation trên service class/method | Bao publisher bằng code |
| Ranh giới | Theo method được proxy quản lý | Theo publisher được truyền vào operator |
| Đọc cấu trúc | Dễ nhận biết tại khai báo method | Dễ thấy phạm vi trong pipeline |
| Điều kiện runtime | Có thể khó thể hiện nếu nhiều nhánh khác nhau | Linh hoạt khi chọn publisher cần bao bọc |
| Cấu hình manager | Thuộc tính transactionManager/qualifier theo annotation | Inject operator được tạo từ manager cụ thể |
| Phụ thuộc proxy | Có | Không cần proxy để áp dụng operator |
| Kiểm soát status | Qua transaction rules và exception | Có thể dùng execute và TransactionStatus |

Một ứng dụng có thể dùng cả hai. Tuy nhiên, hãy giữ quy ước nhất quán để người đọc biết transaction được mở ở đâu và manager nào đang được dùng.

Không bọc cùng một công việc nhiều lần bằng nhiều transaction manager khác nhau nếu không có lý do rõ ràng. Nested hoặc chained transaction cần được thiết kế theo propagation và resource cụ thể.

## 9. Transaction propagation giữa các service

Spring định nghĩa propagation để quyết định một method transactional tham gia transaction hiện có hay tạo transaction mới.

### 9.1. REQUIRED

REQUIRED là propagation mặc định. Nếu đã có transaction phù hợp, method tham gia transaction đó; nếu chưa có, Spring tạo transaction mới.

Ví dụ:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Order> confirm(Long orderId) {
    return inventoryService.reserve(orderId)
        .then(orderRepository.findById(orderId))
        .flatMap(order -> {
            order.setStatus("CONFIRMED");
            return orderRepository.save(order);
        });
}
~~~

Nếu inventoryService cũng dùng cùng transaction manager và propagation REQUIRED, thao tác của nó có thể tham gia transaction bên ngoài.

Điều này hữu ích khi một use case gọi các service con nhưng cần một đơn vị commit/rollback chung.

### 9.2. REQUIRES_NEW

REQUIRES_NEW yêu cầu một transaction độc lập, tạm ngưng transaction hiện có theo semantics của transaction manager.

Không dùng REQUIRES_NEW chỉ để "cho chắc". Nó có thể khiến một thao tác phụ commit ngay cả khi transaction bên ngoài rollback. Điều này có thể đúng với một số audit hoặc log kỹ thuật, nhưng cần xem xét yêu cầu nhất quán và khả năng transaction manager hỗ trợ việc suspend trong reactive context.

Nếu cần audit phải tồn tại kể cả khi nghiệp vụ thất bại, hãy xác định rõ mục đích. Một audit record trong transaction độc lập có thể ghi nhận sự kiện nhưng cũng có thể tạo ra trạng thái mà dữ liệu nghiệp vụ không bao giờ commit. Transactional outbox thường phù hợp hơn khi cần ghi nhận một sự kiện sẽ được xử lý sau commit.

### 9.3. NESTED và savepoint

NESTED có thể dựa vào savepoint nếu transaction manager và driver hỗ trợ. Không giả định mọi R2DBC driver đều hỗ trợ mọi kiểu nested transaction hoặc savepoint như nhau.

Trước khi dùng, hãy xác nhận khả năng của driver/database và viết integration test. Nếu nghiệp vụ chỉ cần một transaction chung, REQUIRED thường là lựa chọn đơn giản hơn.

### 9.4. Khác transaction manager thì không tự tham gia cùng transaction

Hai method cùng có @Transactional nhưng chỉ định hai manager khác nhau không tạo ra một transaction chung. Mỗi manager quản lý resource của nó.

Ví dụ, method ngoài dùng ordersTransactionManager còn method con dùng auditTransactionManager. Hai database có transaction riêng. Nếu một bên commit và bên kia thất bại, không có rollback tự động xuyên qua cả hai.

## 10. Rollback khi reactive publisher phát lỗi

Trong reactive transaction, lỗi được truyền qua tín hiệu onError của publisher. Transaction manager quan sát tín hiệu đó để quyết định rollback theo rollback rules.

Ví dụ:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Order> confirm(Long orderId) {
    return orderRepository.findById(orderId)
        .flatMap(order -> {
            order.setStatus("CONFIRMED");

            return orderRepository.save(order)
                .flatMap(saved ->
                    inventoryRepository.reserve(saved.getProductId())
                        .thenReturn(saved)
                );
        });
}
~~~

Nếu reserve phát lỗi và lỗi được truyền ra khỏi publisher, transaction có thể rollback thay đổi order đã thực hiện trước đó.

### 10.1. Lỗi phải đi tới transaction boundary

Không nuốt lỗi bên trong transaction nếu muốn rollback.

Ví dụ không phù hợp:

~~~java
@Transactional
public Mono<Order> confirm(Long orderId) {
    return orderRepository.save(createOrder(orderId))
        .onErrorResume(error -> Mono.just(fallbackOrder()));
}
~~~

onErrorResume biến lỗi thành một kết quả bình thường. Transaction manager nhìn thấy publisher hoàn tất thành công và có thể commit các thay đổi trước đó.

Nếu cần chuyển lỗi thành HTTP response, hãy xử lý sau transaction boundary:

~~~java
public Mono<OrderResponse> confirm(Long orderId) {
    return transactionalConfirm(orderId)
        .map(OrderResponse::from)
        .onErrorResume(
            InsufficientInventoryException.class,
            error -> Mono.error(
                new OrderConflictException(error.getMessage())
            )
        );
}

@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Order> transactionalConfirm(Long orderId) {
    // Thực hiện toàn bộ thao tác database cần nguyên tử.
    return performConfirmation(orderId);
}
~~~

Trong ví dụ, lỗi rời khỏi method transactional trước khi được ánh xạ thành lỗi API ở method gọi. Transaction có cơ hội rollback trước khi lớp ngoài chuyển đổi lỗi.

Nếu dùng TransactionalOperator, cùng nguyên tắc áp dụng: đặt onErrorResume bên ngoài publisher đã được bọc nếu muốn operator nhìn thấy lỗi gốc.

### 10.2. onErrorMap và doOnError

onErrorMap biến đổi loại lỗi nhưng vẫn phát tín hiệu lỗi. doOnError thực hiện side effect quan sát như ghi log nhưng không nuốt lỗi.

Ví dụ:

~~~java
return transactionalOperator.transactional(work)
    .doOnError(error -> log.error("Order transaction failed", error))
    .onErrorMap(
        OptimisticLockingFailureException.class,
        OrderConflictException::new
    );
~~~

Publisher vẫn phát lỗi sau khi ánh xạ, nên transaction operator đã nhận được lỗi và có thể rollback.

### 10.3. Rollback rules và checked exception

Với annotation transaction, quy tắc rollback mặc định của Spring tập trung vào RuntimeException và Error. Checked exception không mặc nhiên làm rollback theo quy tắc mặc định.

Nếu service phát một checked exception được wrap hoặc cần rollback theo checked exception, hãy cấu hình rollbackFor phù hợp:

~~~java
@Transactional(
    transactionManager = "r2dbcTransactionManager",
    rollbackFor = BusinessCheckedException.class
)
public Mono<Order> process(Long orderId) {
    // ...
}
~~~

Trong reactive code, exception được phát dưới dạng tín hiệu lỗi. Hãy xác nhận loại exception thực tế và rollback rules mà Spring đang áp dụng.

### 10.4. Kết quả nghiệp vụ thất bại không phải lúc nào cũng là lỗi reactive

Nếu service trả:

~~~java
return Mono.just(ConfirmationResult.rejected("Insufficient stock"));
~~~

publisher hoàn tất bình thường. Transaction manager không tự hiểu rằng kết quả nghiệp vụ có trạng thái rejected và cần rollback.

Nếu một nhánh đã ghi dữ liệu rồi sau đó nghiệp vụ cần rollback, hãy phát lỗi hoặc đánh dấu rollback-only theo cách được thiết kế. Đừng dùng một response object bình thường rồi kỳ vọng transaction tự rollback.

## 11. Transaction và thứ tự các thao tác reactive

Một transaction có thể bao quanh nhiều thao tác repository. Hãy kết hợp chúng theo đúng quan hệ phụ thuộc.

### 11.1. Dùng flatMap và then cho thao tác tuần tự

Ví dụ:

~~~java
return orderRepository.save(order)
    .flatMap(saved ->
        outboxRepository.save(
            OutboxEvent.orderCreated(saved.getId())
        ).thenReturn(saved)
    );
~~~

Outbox chỉ được ghi sau khi order save thành công. Nếu outbox save lỗi và lỗi truyền ra, transaction có thể rollback cả hai.

### 11.2. Cẩn trọng với Mono.zip hoặc Mono.when trên cùng transaction connection

Không phải lúc nào các thao tác độc lập cũng nên được chạy song song trong cùng reactive transaction.

Trong một transaction R2DBC, các repository thường sử dụng cùng connection được transaction manager gắn vào Reactor Context. Nhiều driver/connection không hỗ trợ thực thi nhiều statement đồng thời trên cùng một connection.

Ví dụ cần thận trọng:

~~~java
return Mono.zip(
    orderRepository.save(order),
    inventoryRepository.save(inventory)
);
~~~

Mono.zip subscribe vào các nguồn để lấy kết quả. Nếu cả hai dùng cùng transaction connection, chúng có thể cạnh tranh trên connection hoặc gặp hạn chế của driver.

Nếu các thao tác cần cùng transaction và không có bảo đảm về concurrent statement support, hãy tuần tự hóa:

~~~java
return inventoryRepository.save(inventory)
    .then(orderRepository.save(order));
~~~

Hoặc dùng flatMap để thể hiện thứ tự phụ thuộc.

Nếu cần chạy song song, hãy xác nhận rõ driver, transaction manager và connection semantics hỗ trợ tình huống đó. Không giả định reactive đồng nghĩa với việc có thể gửi nhiều statement đồng thời trên một connection.

### 11.3. Flux dài có thể giữ transaction lâu

Nếu một service trả Flux lớn bên trong transaction, transaction có thể tồn tại trong suốt thời gian publisher được tiêu thụ.

Điều này có thể giữ connection và transaction lâu hơn dự kiến, đặc biệt khi client HTTP đọc chậm hoặc downstream áp dụng backpressure.

Với danh sách lớn, hãy cân nhắc:

- Phân trang.
- Đọc theo batch nhỏ.
- Chỉ mở transaction cho phần cần consistency.
- Tránh giữ transaction trong khi chờ xử lý ngoài database.
- Không gom toàn bộ dữ liệu vào bộ nhớ nếu không cần.

Transaction boundary nên có thời gian hữu hạn và gắn với một đơn vị công việc có thể xác định.

## 12. Read-only transaction và các thuộc tính khác

### 12.1. readOnly

Với use case chỉ đọc, có thể khai báo:

~~~java
@Transactional(
    transactionManager = "r2dbcTransactionManager",
    readOnly = true
)
public Flux<Order> findOpenOrders() {
    return orderRepository.findByStatus("OPEN");
}
~~~

readOnly là metadata/hint cho transaction manager và resource. Mức độ database thực thi hoặc tối ưu theo hint này phụ thuộc driver và database. Không coi nó là cơ chế bảo mật ngăn mọi câu ghi.

Nếu use case thực hiện ghi, hãy không đánh dấu readOnly.

### 12.2. isolation

Isolation level quy định mức độ một transaction nhìn thấy thay đổi từ transaction khác theo semantics database.

Ví dụ:

~~~java
@Transactional(
    transactionManager = "r2dbcTransactionManager",
    isolation = Isolation.READ_COMMITTED
)
public Mono<Order> confirm(Long orderId) {
    return performConfirmation(orderId);
}
~~~

Các isolation level được hỗ trợ và semantics cụ thể phụ thuộc database/driver. Hãy chọn dựa trên bất biến nghiệp vụ và kiểm thử concurrency. Tăng isolation có thể làm tăng lock, chờ hoặc chi phí xử lý.

### 12.3. timeout

Có thể đặt timeout cho transaction:

~~~java
@Transactional(
    transactionManager = "r2dbcTransactionManager",
    timeout = 5
)
public Mono<Order> updateOrder(Long orderId) {
    return performUpdate(orderId);
}
~~~

Timeout transaction không thay thế timeout HTTP client, timeout query hoặc timeout của SDK bên ngoài. Nó giới hạn thời gian transaction theo khả năng transaction manager và resource.

Nếu transaction thường xuyên chạm timeout, hãy xem lại query, lock contention, connection pool và phạm vi công việc. Không chỉ tăng timeout để che giấu transaction kéo dài.

### 12.4. noRollbackFor

Trong một số nghiệp vụ, một loại exception cụ thể không nên rollback. Có thể dùng noRollbackFor, nhưng cần rất thận trọng:

~~~java
@Transactional(
    transactionManager = "r2dbcTransactionManager",
    noRollbackFor = DuplicateNotificationException.class
)
public Mono<Void> recordNotification(Long orderId) {
    // ...
}
~~~

Chỉ dùng khi commit dù exception đó xảy ra là đúng về nghiệp vụ. Nếu exception biểu thị một phần dữ liệu chưa hoàn chỉnh, cho phép commit có thể tạo trạng thái không nhất quán.

## 13. Tránh giữ transaction trong lúc gọi hệ thống bên ngoài

Một transaction R2DBC không thể rollback HTTP call, thanh toán, email hoặc message broker không tham gia transaction đó.

Không nên bao bọc toàn bộ request trong một transaction nếu có lời gọi ngoài database kéo dài:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Order> pay(Long orderId) {
    return orderRepository.findById(orderId)
        .flatMap(order ->
            paymentClient.authorize(order)
                .flatMap(payment -> {
                    order.setStatus("PAID");
                    return orderRepository.save(order);
                })
        );
}
~~~

Nếu paymentClient chờ 10 giây, transaction có thể giữ connection trong suốt thời gian đó. Nếu thanh toán thành công nhưng save thất bại, rollback database không hoàn lại khoản thanh toán.

### 13.1. Chia thành các bước rõ ràng

Một cách thiết kế là:

1. Ghi trạng thái PENDING và outbox event trong transaction ngắn.
2. Worker xử lý yêu cầu thanh toán sau commit.
3. Worker cập nhật kết quả trong transaction riêng.
4. Nếu thất bại, chuyển trạng thái và chạy quy trình bù phù hợp.

Transactional outbox bảo đảm yêu cầu xử lý tiếp theo được lưu cùng thay đổi nghiệp vụ. Worker cần idempotency để tránh thanh toán hoặc xử lý lặp.

### 13.2. Saga khi có nhiều hệ thống

Nếu một use case gồm nhiều bước qua nhiều hệ thống, hãy xem xét saga. Mỗi bước có transaction cục bộ và hành động bù tương ứng.

Saga không phải một transaction ACID duy nhất. Nó là quy trình nghiệp vụ có trạng thái, retry, timeout và hành động bù.

## 14. Transaction boundary và nhiều repository

Một service có thể gọi nhiều repository trong cùng transaction nếu chúng sử dụng cùng transaction manager và cùng ConnectionFactory.

Ví dụ:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Purchase> createPurchase(Purchase purchase) {
    return customerRepository.findById(purchase.getCustomerId())
        .switchIfEmpty(Mono.error(
            new CustomerNotFoundException(purchase.getCustomerId())
        ))
        .flatMap(customer ->
            inventoryRepository.findById(purchase.getProductId())
                .switchIfEmpty(Mono.error(
                    new ProductNotFoundException(purchase.getProductId())
                ))
                .flatMap(inventory -> {
                    if (inventory.getAvailable() < purchase.getQuantity()) {
                        return Mono.error(
                            new InsufficientInventoryException()
                        );
                    }

                    inventory.reserve(purchase.getQuantity());

                    return inventoryRepository.save(inventory)
                        .then(purchaseRepository.save(purchase));
                })
        );
}
~~~

Các repository phải được định tuyến tới cùng database nếu muốn tham gia một transaction R2DBC đơn. Nếu repository dùng ConnectionFactory khác, transaction manager hiện tại không tự bao phủ nguồn đó.

Nếu use case cần ghi hai database, hãy đánh giá outbox, saga hoặc cơ chế phối hợp được thiết kế riêng. Không suy luận rằng cùng một service method đồng nghĩa mọi database đều atomic.

## 15. AOP proxy và những trường hợp @Transactional không được áp dụng

Annotation @Transactional trong cấu hình proxy-based của Spring được áp dụng khi lời gọi đi qua proxy transaction.

### 15.1. Self-invocation

Ví dụ:

~~~java
@Service
public class OrderService {

    public Mono<Order> process(Long orderId) {
        return confirmInTransaction(orderId);
    }

    @Transactional(transactionManager = "r2dbcTransactionManager")
    public Mono<Order> confirmInTransaction(Long orderId) {
        return orderRepository.findById(orderId);
    }
}
~~~

Nếu process gọi confirmInTransaction trực tiếp trên cùng instance, lời gọi nội bộ không đi qua proxy. Transaction annotation trên method con có thể không được áp dụng như kỳ vọng.

Có thể giải quyết bằng cách:

- Đặt use case transactional trong một service bean riêng và inject bean đó.
- Gọi method transactional qua Spring proxy từ bên ngoài.
- Dùng TransactionalOperator để bao publisher tường minh.

Không tự inject bean vào chính nó chỉ để lách self-invocation nếu có thể thiết kế ranh giới service rõ hơn.

### 15.2. Tạo service bằng new

Không tạo service bằng toán tử new rồi kỳ vọng Spring áp dụng @Transactional:

~~~java
OrderService service = new OrderService(...);
~~~

Instance tự tạo không được Spring quản lý như bean proxy. Hãy inject service bean từ ApplicationContext hoặc constructor injection.

### 15.3. Phương thức không trả reactive publisher

R2DBC reactive transaction cần quản lý publisher. Phương thức service trả Mono hoặc Flux để transaction interceptor có thể bao bọc việc thực thi reactive.

Một method trả void hoặc một giá trị đồng bộ không tự trở thành reactive transaction chỉ vì có @Transactional. Nếu dùng JDBC imperative, đó là mô hình transaction khác.

### 15.4. Method visibility và proxy strategy

Hãy khai báo các service method transactional theo cách tương thích với proxy strategy của ứng dụng, thường là public method được gọi từ bean khác. CGLIB/JDK proxy có các giới hạn khác nhau đối với final class, final method và interface method.

Nếu transaction không hoạt động như mong đợi, hãy kiểm tra bean có được Spring quản lý không, lời gọi có đi qua proxy không và reactive transaction manager có được chọn đúng không.

## 16. Transaction boundary và validation

Không phải mọi validation đều cần chạy trong transaction.

Có thể phân loại:

- Validation thuần dữ liệu đầu vào: thực hiện trước transaction.
- Validation cần đọc database để quyết định ghi: thực hiện trong transaction hoặc kết hợp với constraint/optimistic locking.
- Validation gọi hệ thống ngoài: thường thực hiện ngoài transaction nếu không cần cùng transaction database.
- Validation dựa trên trạng thái có thể thay đổi đồng thời: cần bảo vệ bằng transaction, version hoặc constraint phù hợp.

Ví dụ, kiểm tra số lượng tồn kho rồi trừ kho phải tránh race condition. Chỉ đọc số lượng trong service rồi cập nhật sau có thể không đủ nếu request khác cùng thao tác. Hãy cân nhắc @Version, câu UPDATE có điều kiện hoặc cơ chế locking phù hợp.

Transaction bảo vệ nhóm thao tác theo isolation semantics, nhưng không thay thế mọi quy tắc concurrency. Hãy chọn cơ chế bảo vệ bất biến theo yêu cầu nghiệp vụ.

## 17. Kiểm thử transaction ở tầng dịch vụ

Test transaction cần xác nhận trạng thái database sau khi publisher hoàn tất hoặc phát lỗi. Chỉ kiểm tra exception không đủ để chứng minh rollback đã xảy ra.

### 17.1. Kiểm tra rollback khi bước sau thất bại

Giả sử service cập nhật inventory rồi ghi order. Nếu save order lỗi, inventory phải được khôi phục.

Ví dụ:

~~~java
@Test
void shouldRollbackInventoryWhenOrderSaveFails() {
    StepVerifier.create(orderService.createPurchase(failingPurchase))
        .expectError()
        .verify();

    StepVerifier.create(inventoryRepository.findById(productId))
        .assertNext(inventory ->
            assertThat(inventory.getAvailable()).isEqualTo(10)
        )
        .verifyComplete();
}
~~~

Test cần dùng database integration thật hoặc môi trường test tương thích với R2DBC. Cấu hình transaction manager và repository phải giống đường chạy của ứng dụng.

### 17.2. Không để test transaction che mất kết quả

Nếu test method tự được bao bọc trong transaction test, dữ liệu có thể bị rollback khi test kết thúc. Điều này có thể làm khó xác định transaction của service đã commit hay rollback đúng hay chưa.

Hãy thiết kế test để quan sát trạng thái sau khi service publisher kết thúc. Tùy test framework và cấu hình, có thể cần thực hiện truy vấn xác minh ngoài transaction của test hoặc dùng transaction setup rõ ràng.

### 17.3. Kiểm tra commit khi thành công

Ngoài rollback, cần test đường thành công:

- Tất cả thay đổi được lưu.
- Outbox record được tạo.
- Version entity tăng nếu dùng optimistic locking.
- Không có dữ liệu một phần khi một bước thất bại.

### 17.4. Kiểm tra transaction context

Có thể kiểm tra một service được gọi qua Spring bean proxy và sử dụng đúng transaction manager. Không test bằng instance tự tạo nếu mục tiêu là kiểm tra annotation transaction.

Nếu dùng TransactionalOperator, test publisher đã được bọc bởi operator tương ứng.

### 17.5. Kiểm tra nhiều thao tác và concurrency

Test nên mô phỏng các trường hợp:

- Repository đầu tiên thành công, repository thứ hai lỗi.
- Validation phát lỗi trước khi ghi.
- Hai request cùng cập nhật một entity.
- Publisher bị cancel hoặc timeout.
- Một lời gọi ngoài database thất bại.
- Lỗi được chuyển đổi sau transaction boundary.

## 18. Những lỗi thường gặp

| Lỗi hoặc nhầm lẫn | Hệ quả | Cách xử lý |
|---|---|---|
| Đặt transaction chỉ ở controller | Controller biết quá nhiều về persistence và use case | Đặt transaction ở service điều phối nghiệp vụ |
| Mỗi repository có transaction riêng | Các bước của một use case có thể commit độc lập | Bao bọc toàn bộ publisher ở service |
| Dùng transaction manager JDBC cho R2DBC | Connection R2DBC không thuộc transaction đó | Dùng R2dbcTransactionManager |
| Method transactional trả kiểu đồng bộ | Không áp dụng đúng reactive transaction model | Trả Mono/Flux |
| Gọi subscribe() bên trong service | Tạo subscription tách rời khỏi transaction | Trả publisher từ method |
| Gọi block() trong pipeline | Chặn thread và tách reactive flow | Dùng flatMap/map/then |
| Service gọi method transactional nội bộ | Self-invocation bỏ qua proxy | Tách bean hoặc dùng TransactionalOperator |
| Nuốt lỗi bằng onErrorResume bên trong transaction | Transaction có thể commit dù một bước thất bại | Để lỗi truyền qua boundary rồi xử lý bên ngoài |
| Trả kết quả rejected bình thường và mong rollback | Transaction thấy publisher hoàn tất | Phát lỗi hoặc đánh dấu rollback-only |
| Bao bọc lời gọi HTTP trong transaction dài | Giữ connection và không rollback được hệ thống ngoài | Tách transaction, dùng outbox/saga |
| Dùng nhiều manager và nghĩ có atomic commit | Mỗi manager quản lý transaction riêng | Thiết kế phối hợp phân tán rõ ràng |
| Dùng Mono.zip cho nhiều lệnh trên cùng connection mà không kiểm tra | Driver có thể không hỗ trợ statement đồng thời | Tuần tự hóa bằng flatMap/then/concatMap |
| Trả Flux lớn trong transaction | Connection có thể bị giữ lâu theo tốc độ consumer | Phân trang hoặc thu hẹp transaction |
| Không chỉ định manager khi có nhiều manager | Transaction có thể mơ hồ hoặc chọn sai nguồn | Chỉ định transactionManager hoặc inject operator |
| Test chỉ kiểm tra exception | Không chứng minh dữ liệu đã rollback | Truy vấn lại database sau khi publisher kết thúc |

## 19. Quy trình đặt transaction boundary ở tầng dịch vụ

Khi thiết kế một use case WebFlux với R2DBC, hãy thực hiện theo trình tự:

1. Xác định các thao tác database thuộc cùng một đơn vị nghiệp vụ.
2. Xác định các thay đổi phải cùng commit hoặc rollback.
3. Đưa việc điều phối các repository vào service method.
4. Xác nhận các repository dùng cùng ConnectionFactory nếu cần một transaction R2DBC chung.
5. Chọn R2dbcTransactionManager phù hợp.
6. Dùng @Transactional trên service method reactive hoặc TransactionalOperator quanh publisher.
7. Trả Mono/Flux từ service và controller; không subscribe hoặc block thủ công.
8. Nối các thao tác theo thứ tự phụ thuộc bằng flatMap, then hoặc concatMap.
9. Để lỗi cần rollback truyền ra ngoài transaction boundary.
10. Chỉ xử lý lỗi thành HTTP response sau khi transaction đã kết thúc.
11. Không giữ transaction trong lúc chờ HTTP, email, payment hoặc I/O blocking ngoài database nếu không thực sự cần.
12. Dùng outbox/saga khi cần phối hợp side effect hoặc nhiều database.
13. Kiểm tra proxy, self-invocation và transaction manager thực tế.
14. Viết integration test xác nhận cả commit và rollback.
15. Theo dõi transaction duration, connection pool và lock wait trong môi trường chạy.

## 20. Bài tập tự kiểm tra

### Bài 1: Chọn tầng đặt transaction

Một request xác nhận đơn hàng cần cập nhật order, inventory và outbox. Nên đặt transaction ở controller, repository hay service?

Gợi ý: Service vì đây là nơi điều phối toàn bộ use case và biết các thao tác phải cùng commit/rollback.

### Bài 2: Chọn transaction manager

Ứng dụng dùng Spring Data R2DBC. Nên dùng transaction manager nào?

Gợi ý: R2dbcTransactionManager gắn với ConnectionFactory mà repository sử dụng.

### Bài 3: Publisher và transaction

Một service có @Transactional nhưng gọi subscribe() bên trong rồi trả Mono.empty(). Điều gì có thể xảy ra?

Gợi ý: Subscription bên trong tách khỏi publisher mà Spring quản lý; transaction có thể kết thúc trước khi công việc hoàn tất.

### Bài 4: Rollback và onErrorResume

Một thao tác save thất bại nhưng service dùng onErrorResume để trả Mono.just(fallback). Transaction có chắc rollback không?

Gợi ý: Không. Lỗi đã bị chuyển thành completion bình thường trước khi transaction boundary quan sát publisher. Hãy xử lý lỗi bên ngoài transaction nếu cần rollback.

### Bài 5: Hai repository

Hai repository dùng cùng ConnectionFactory và được gọi trong một service method @Transactional. Chúng có thể tham gia cùng transaction không?

Gợi ý: Có, nếu cùng transaction manager/resource và publisher được kết hợp trong cùng reactive transaction context.

### Bài 6: Hai database

Một use case ghi orders database và audit database với hai transaction manager. Một @Transactional có tự rollback cả hai không?

Gợi ý: Không. Mỗi manager quản lý một transaction riêng. Cần outbox, saga hoặc giải pháp phân tán được thiết kế riêng.

### Bài 7: Lời gọi HTTP

Một service mở transaction rồi chờ payment gateway 10 giây. Tác động có thể xảy ra là gì?

Gợi ý: Transaction và connection có thể bị giữ lâu; rollback database không hoàn lại thanh toán bên ngoài. Tách lời gọi ngoài transaction và dùng idempotency/outbox/saga.

### Bài 8: Self-invocation

Method A trong service gọi trực tiếp method B có @Transactional trên cùng instance. Annotation của B có chắc được áp dụng không?

Gợi ý: Không trong proxy-based transaction khi đó là self-invocation. Tách bean hoặc dùng TransactionalOperator.

### Bài 9: Thao tác song song

Hai repository cùng tham gia một R2DBC transaction và được gọi trong Mono.zip. Có thể giả định driver luôn chạy đồng thời an toàn không?

Gợi ý: Không. Cùng transaction thường dùng một connection; hãy kiểm tra driver hoặc tuần tự hóa các statement.

### Bài 10: Kiểm thử rollback

Sau khi service phát lỗi, chỉ kiểm tra expectError có đủ xác nhận rollback không?

Gợi ý: Không. Cần truy vấn lại database để xác nhận các thay đổi trước lỗi đã được hoàn tác.

## 21. Ghi nhớ

- Transaction boundary nên phản ánh một đơn vị công việc nghiệp vụ cần cùng thành công hoặc cùng thất bại.
- Service layer thường là nơi phù hợp để điều phối nhiều repository trong một use case.
- Controller nhận request và trả publisher; repository tập trung vào persistence.
- Spring Data R2DBC cần reactive transaction manager như R2dbcTransactionManager.
- Reactive transaction context được truyền qua Reactor Context, không dựa vào một thread cố định.
- Service method transactional nên trả Mono hoặc Flux và được gọi qua Spring proxy.
- Dùng @Transactional hoặc TransactionalOperator để bao bọc publisher cần tính nguyên tử.
- Các repository phải dùng đúng ConnectionFactory/transaction manager để tham gia cùng transaction.
- Không gọi subscribe() hoặc block() bên trong reactive service.
- Lỗi phải truyền tới transaction boundary nếu muốn rollback; xử lý fallback sau khi transaction kết thúc.
- onErrorResume bên trong boundary có thể biến lỗi thành completion và khiến transaction commit.
- REQUIRED thường tham gia transaction hiện có của cùng manager; manager khác không tự tạo transaction chung.
- Cẩn trọng với statement song song trên cùng R2DBC connection và với Flux dài giữ transaction lâu.
- Không giữ transaction trong lúc chờ hệ thống ngoài database; transaction không rollback được HTTP, email hay payment.
- Dùng outbox/saga và idempotency để phối hợp side effect hoặc nhiều hệ thống.
- Kiểm thử cả commit lẫn rollback bằng cách kiểm tra trạng thái database sau khi publisher hoàn tất.

Khi đặt ranh giới giao dịch ở tầng dịch vụ, hãy bao bọc đúng những thao tác database tạo thành một đơn vị nghiệp vụ và để reactive publisher đi trọn vòng đời qua Spring transaction manager. Controller không cần quản lý transaction, repository không cần điều phối toàn bộ use case, còn service có thể thể hiện rõ các bước phải commit hoặc rollback cùng nhau. Transaction ngắn, được chọn đúng manager và được kiểm thử bằng trạng thái dữ liệu thực tế sẽ giúp ứng dụng WebFlux và R2DBC duy trì tính nhất quán mà không giữ connection lâu hơn cần thiết.

