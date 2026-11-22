# Giao dịch không có hiệu lực do proxy, context hoặc ranh giới luồng

## 1. Nhận diện vấn đề

Trong Spring Data Relational R2DBC, một method có gắn @Transactional nhưng dữ liệu vẫn được commit từng phần, không rollback khi lỗi, hoặc các repository call dường như chạy ngoài transaction. Đây thường là vấn đề ở ranh giới giao dịch: Spring không intercept lời gọi, transaction manager không quản lý đúng ConnectionFactory, Reactor Context không đi theo publisher, hoặc thao tác database đã tách khỏi luồng reactive được trả về.

Các triệu chứng thường gặp:

- Một method có @Transactional nhưng lỗi ở thao tác thứ hai không rollback thao tác thứ nhất.
- Gọi một method transactional từ method khác trong cùng class nhưng transaction không được áp dụng.
- Repository save được gọi bằng subscribe() bên trong service; method trả về trước khi thao tác hoàn tất.
- Dữ liệu được lưu dù publisher kết thúc bằng lỗi mà developer nghĩ phải rollback.
- Một repository tham gia transaction, repository khác lại commit độc lập.
- Code chạy trên thread khác thì không còn thấy transaction.
- Test có @Transactional nhưng dữ liệu vẫn tồn tại sau test hoặc không phản ánh hành vi production.
- Một publisher được tạo trong method nhưng không được nối vào publisher cuối cùng.

Cần xác định chính xác transaction nào đang được kỳ vọng, thao tác nào phải cùng commit/rollback và publisher nào thực sự được subscribe. Annotation chỉ là một phần của cơ chế; transaction reactive được gắn với quá trình subscribe và Reactor Context.

## 2. Vòng đời của reactive transaction

Với R2DBC, Spring thường dùng ReactiveTransactionManager, phổ biến là R2dbcTransactionManager. Transaction manager lấy connection từ ConnectionFactory, bắt đầu transaction và bind resource vào Reactor Context của subscription hiện tại.

Luồng khái quát:

~~~text
Caller invokes service through Spring proxy
                 |
                 v
        Service returns Publisher
                 |
                 v
          Caller subscribes
                 |
                 v
    Transaction interceptor / operator
                 |
                 v
     ReactiveTransactionManager
                 |
                 v
      Acquire R2DBC Connection
                 |
                 v
      Bind resource to Reactor Context
                 |
                 v
       Repository / DatabaseClient
                 |
                 v
        Execute SQL statements
                 |
          +------+------+
          |             |
          v             v
       Complete        Error
          |             |
          v             v
        COMMIT        ROLLBACK
          |             |
          +------+------+
                 |
                 v
       Release / cleanup connection
~~~

Điểm khác biệt quan trọng so với transaction imperative là transaction reactive không được truyền chủ yếu bằng ThreadLocal. Nó gắn với reactive subscription và Reactor Context. Một publisher nằm ngoài chain, một subscription tự tạo hoặc một ConnectionFactory khác có thể khiến thao tác không tham gia transaction mong đợi.

Ngoài ra, publisher reactive thường lazy. Việc gọi repository method thường chỉ tạo Publisher; SQL chạy khi có subscription. Vì vậy, method Java có thể đã trả về Publisher trước khi transaction thực sự bắt đầu.

## 3. Proxy không intercept lời gọi method

Spring declarative transaction thường được triển khai qua AOP proxy. Lời gọi đi qua proxy mới có cơ hội được transaction interceptor xử lý. Có nhiều cách vô tình bỏ qua proxy.

### 3.1. Self-invocation trong cùng class

Đây là nguyên nhân phổ biến nhất.

Ví dụ:

~~~java
@Service
class OrderService {

    public Mono<Void> placeOrder(CreateOrderCommand command) {
        return saveOrderAndLines(command);
    }

    @Transactional
    public Mono<Void> saveOrderAndLines(CreateOrderCommand command) {
        return orderRepository.save(toOrder(command))
                .flatMap(order ->
                        orderLineRepository.saveAll(toLines(order.id(), command))
                                .then()
                );
    }
}
~~~

Nếu placeOrder gọi saveOrderAndLines trực tiếp qua this trong cùng instance, lời gọi không đi qua Spring proxy. Transaction interceptor trên saveOrderAndLines có thể không chạy.

Cách sửa ưu tiên là đặt transaction boundary ở method public được gọi từ bean khác:

~~~java
@Service
class OrderService {

    private final OrderPersistenceService persistenceService;

    OrderService(OrderPersistenceService persistenceService) {
        this.persistenceService = persistenceService;
    }

    public Mono<Void> placeOrder(CreateOrderCommand command) {
        return persistenceService.saveOrderAndLines(command);
    }
}

@Service
class OrderPersistenceService {

    @Transactional
    public Mono<Void> saveOrderAndLines(CreateOrderCommand command) {
        return orderRepository.save(toOrder(command))
                .flatMap(order ->
                        orderLineRepository.saveAll(toLines(order.id(), command))
                                .then()
                );
    }
}
~~~

Lời gọi từ OrderService sang OrderPersistenceService đi qua proxy của bean persistence. Có thể dùng TransactionalOperator nếu muốn biểu diễn transaction boundary trực tiếp trong publisher.

Không nên chuyển transaction annotation qua lại giữa nhiều method mà chưa xác định method nào là entry point thật của transaction.

### 3.2. Tự tạo object bằng new

Ví dụ:

~~~java
OrderService service = new OrderService(repository);
service.placeOrder(command);
~~~

Object được tạo bằng new không phải bean do Spring quản lý. Spring không tạo proxy cho instance đó, không inject transaction interceptor và không áp dụng các bean post-processor liên quan.

Hãy inject bean từ ApplicationContext thông qua constructor injection. Trong test, dùng Spring context khi cần xác nhận proxy thật; test unit tạo object bằng new có thể kiểm tra logic nhưng không chứng minh @Transactional hoạt động.

### 3.3. Method private, final hoặc class final

Khả năng intercept phụ thuộc proxy strategy:

- JDK dynamic proxy intercept lời gọi qua interface proxy.
- Class-based proxy dùng subclass và không thể override method final hoặc private.
- Class final không thể được subclass bằng CGLIB.
- Lời gọi nội bộ qua this vẫn bỏ qua proxy dù method có public.

Spring có thể hỗ trợ thêm visibility nhất định với class-based proxy tùy cấu hình/phiên bản, nhưng cách dễ dự đoán nhất là đặt transaction boundary ở method public, non-final của một Spring bean được gọi từ bean khác.

Không dùng private helper có @Transactional rồi kỳ vọng annotation tạo transaction độc lập. Private helper nên được gọi bên trong method transaction đã được intercept hoặc chuyển sang bean riêng nếu cần boundary riêng.

### 3.4. Method được gọi trong constructor hoặc trước khi proxy sẵn sàng

Không gọi method transactional từ constructor của bean hoặc từ logic khởi tạo trước khi bean hoàn tất quá trình tạo proxy. Trong constructor, object đang được tạo có thể chưa phải proxy mà caller sẽ nhận sau này.

Đưa công việc cần transaction vào service method được gọi sau khi context khởi động, application runner hoặc component orchestration phù hợp.

### 3.5. Annotation có mặt nhưng method không phải đường gọi thực tế

Có thể annotation nằm trên method overload, interface hoặc implementation khác với method thực tế được gọi. Hãy kiểm tra:

- Bean được inject là implementation nào?
- Lời gọi có qua interface proxy hay class proxy?
- Annotation nằm trên method/class nào?
- Có override method và thay đổi annotation không?
- Có gọi method bằng reference khác hoặc instance tự tạo không?
- Có cấu hình AOP proxy mode khác dự kiến không?

Đừng chỉ tìm chuỗi @Transactional trong source rồi kết luận lời gọi chắc chắn được intercept.

## 4. Chọn đúng transaction manager

Ứng dụng có thể có nhiều transaction manager, đặc biệt trong giai đoạn coexistence JDBC/JPA và R2DBC.

Một số loại thường gặp:

- PlatformTransactionManager, ví dụ JpaTransactionManager hoặc DataSourceTransactionManager, cho transaction imperative.
- ReactiveTransactionManager, ví dụ R2dbcTransactionManager, cho reactive transaction.
- Transaction manager khác cho từng database hoặc resource.

Nếu ứng dụng có cả JpaTransactionManager và R2dbcTransactionManager, annotation không nên để Spring phải suy đoán manager nào cần dùng. Chỉ rõ manager tương ứng với R2DBC:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(order ->
                    orderLineRepository.saveAll(toLines(order.id(), command))
                            .thenReturn(order)
            );
}
~~~

Tên bean trong ví dụ phải khớp với tên thực tế của cấu hình ứng dụng. Spring Boot có thể auto-configure manager cho R2DBC; khi tự khai báo nhiều manager, hãy đặt tên rõ và kiểm tra bean được chọn.

Nếu dùng nhầm JpaTransactionManager cho một publisher R2DBC, JPA transaction không tự quản lý connection R2DBC. Tương tự, R2dbcTransactionManager không tự quản lý JDBC Connection hoặc EntityManager.

### 4.1. Kiểm tra kiểu trả về

Reactive transaction manager cần một reactive return type, chẳng hạn Mono, Flux hoặc Publisher. Nếu method trả về void, primitive hoặc một object đồng bộ trong khi bên trong chỉ tạo Publisher rồi bỏ qua, transaction reactive không bao bọc publisher đó.

Ví dụ sai:

~~~java
@Transactional
public void createOrder(Order order) {
    orderRepository.save(order);
}
~~~

save trả về Publisher nhưng không được trả về hoặc subscribe một cách có kiểm soát. Method void kết thúc trước khi reactive operation chạy.

Ví dụ đúng:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Order> createOrder(Order order) {
    return orderRepository.save(order);
}
~~~

Nếu method có nhiều thao tác, trả về một publisher đại diện cho toàn bộ công việc, nối các bước bằng flatMap, then, concatMap hoặc operator phù hợp.

### 4.2. Nhiều ConnectionFactory

R2dbcTransactionManager quản lý một ConnectionFactory cụ thể. Repository hoặc DatabaseClient tham gia transaction khi chúng dùng cùng resource ConnectionFactory mà transaction manager quản lý.

Nếu ứng dụng có hai ConnectionFactory, hoặc tạo hai pool riêng cho cùng một database, transaction manager của pool A không tự bind connection cho repository dùng pool B.

Ví dụ cấu hình:

~~~java
@Bean
ConnectionFactory primaryConnectionFactory() {
    // Tạo pooled ConnectionFactory cho database chính.
}

@Bean
ConnectionFactory reportingConnectionFactory() {
    // Tạo pooled ConnectionFactory cho database báo cáo.
}

@Bean
ReactiveTransactionManager primaryR2dbcTransactionManager(
        @Qualifier("primaryConnectionFactory") ConnectionFactory factory) {
    return new R2dbcTransactionManager(factory);
}
~~~

Cần bảo đảm repository, DatabaseClient và transaction manager được cấu hình cùng ConnectionFactory tương ứng. Kiểm tra cả bean qualifier, cấu hình repository base packages và các custom template.

Một transaction trên database chính không tự bao trùm thao tác ở reporting database. Nếu cần thay đổi atomic trên nhiều database/resource, phải thiết kế một cơ chế phù hợp; đừng giả định một @Transactional đơn giản tạo distributed transaction.

## 5. Reactive transaction dùng Reactor Context, không phải ThreadLocal

Transaction imperative thường gắn resource với thread thông qua ThreadLocal. Reactive pipeline có thể chuyển thread giữa các operator, vì vậy Spring dùng Reactor Context để truyền transaction resource và synchronization.

Điều này có nghĩa:

- publishOn và subscribeOn thông thường không tự làm mất Reactor Context.
- Chuyển thread không đồng nghĩa transaction bị mất.
- Đọc transaction/security state từ ThreadLocal có thể cho kết quả sai.
- Tạo subscription mới không tự kế thừa transaction context của subscription ban đầu.
- Chuyển sang callback/executor hoặc API ngoài Reactor có thể cần bridge context rõ ràng.

Không dùng TransactionSynchronizationManager imperative hoặc TransactionAspectSupport để suy luận reactive transaction state. Những API imperative dựa vào thread-bound context.

Khi cần kiểm tra transaction reactive hiện tại, dùng API reactive transaction context phù hợp với phiên bản Spring đang chạy, hoặc quan sát bằng integration test và instrumentation transaction manager.

### 5.1. publishOn và subscribeOn không phải nguyên nhân mặc định làm mất transaction

Ví dụ:

~~~java
return orderRepository.findById(id)
        .publishOn(Schedulers.parallel())
        .flatMap(order ->
                orderRepository.save(order.withStatus("PROCESSING"))
        );
~~~

Reactor Context được truyền qua các operator Reactor thông thường. Việc chuyển scheduler ở đây không tự động làm transaction biến mất.

Vấn đề thường xảy ra khi code rời khỏi chain, dùng ThreadLocal hoặc tạo một luồng reactive mới không được nối vào publisher đang được quản lý.

Không chữa lỗi context bằng cách bỏ publishOn/subscribeOn một cách mù quáng. Hãy xác định nơi context thực sự bị tách.

### 5.2. ThreadLocal không phải nơi lưu actor hoặc transaction trong reactive flow

Một helper như:

~~~java
String actor = SecurityContextHolder.getContext()
        .getAuthentication()
        .getName();
~~~

dựa trên imperative SecurityContextHolder và có thể không thấy identity trong WebFlux reactive flow. Tương tự, ThreadLocal tùy chỉnh không tự đi theo Reactor Context.

Dùng ReactiveSecurityContextHolder cho Spring Security reactive và Reactor Context hoặc abstraction context-aware cho metadata riêng. Không lấy actor hoặc tenant bằng cách đoán thread hiện tại.

## 6. subscribe() bên trong service tạo transaction boundary khác

Đây là lỗi rất phổ biến khi mới chuyển từ imperative sang reactive.

Ví dụ sai:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Void> createOrder(CreateOrderCommand command) {
    orderRepository.save(toOrder(command))
            .subscribe();

    return Mono.empty();
}
~~~

Điều gì xảy ra:

1. Method tạo publisher save.
2. subscribe() tạo một subscription độc lập ngay bên trong method.
3. Publisher được trả về là Mono.empty().
4. Transaction interceptor quản lý publisher rỗng được trả về, không nhất thiết quản lý subscription save đã tự tạo.
5. Caller thấy method hoàn tất dù thao tác save vẫn có thể đang chạy.

Thay bằng composition:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Void> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .then();
}
~~~

Nếu cần nhiều thao tác:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(saved ->
                    orderLineRepository.saveAll(toLines(saved.id(), command))
                            .thenReturn(saved)
            );
}
~~~

Mọi thao tác database phải là một phần của publisher được trả về. Caller subscribe vào publisher cuối cùng; transaction interceptor hoặc TransactionalOperator quản lý cùng subscription đó.

### 6.1. subscribe() trong doOnNext cũng tạo side effect tách rời

Ví dụ:

~~~java
return orderRepository.findById(id)
        .doOnNext(order ->
                auditRepository.save(toAudit(order)).subscribe()
        );
~~~

Audit save chạy trong subscription riêng. Nó không tự tham gia transaction của publisher findById và có thể hoàn tất trước hoặc sau luồng chính.

Nối audit operation vào chain:

~~~java
return orderRepository.findById(id)
        .flatMap(order ->
                auditRepository.save(toAudit(order))
                        .thenReturn(order)
        );
~~~

Nếu cả hai thao tác cần atomic, bảo đảm toàn bộ chain nằm trong reactive transaction và cả hai repository dùng cùng ConnectionFactory.

### 6.2. block() cũng tạo subscription riêng

Không dùng block() để lấy kết quả reactive bên trong một reactive transaction:

~~~java
@Transactional
public Mono<Void> update(Long id) {
    Order order = orderRepository.findById(id).block();
    // ...
    return Mono.empty();
}
~~~

block() tự subscribe và chờ. Nó có thể chạy ngoài transaction context dự kiến, chặn thread, hoặc gây deadlock nếu được gọi trên event-loop. Thay bằng flatMap/map/then để giữ một chain reactive.

## 7. Publisher được tạo nhưng không được nối vào luồng

Reactive code có thể tạo một Publisher nhưng không subscribe nó. Khi đó không có SQL tương ứng.

Ví dụ:

~~~java
@Transactional
public Mono<Void> create(Order order, AuditEvent event) {
    Mono<Order> saveOrder = orderRepository.save(order);
    Mono<AuditEvent> saveAudit = auditRepository.save(event);

    return saveOrder.then();
}
~~~

saveAudit không nằm trong publisher trả về. Nó không được thực thi.

Nối cả hai:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Void> create(Order order, AuditEvent event) {
    return orderRepository.save(order)
            .then(auditRepository.save(event))
            .then();
}
~~~

Nếu audit event cần ID từ order:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Void> create(Order order, Function<Long, AuditEvent> eventFactory) {
    return orderRepository.save(order)
            .flatMap(saved ->
                    auditRepository.save(eventFactory.apply(saved.id()))
            )
            .then();
}
~~~

Các dấu hiệu cần tìm trong code:

- Publisher được gán vào biến nhưng không được return, compose hoặc subscribe có chủ đích.
- Dùng map tạo ra Mono/Flux lồng nhau thay vì flatMap.
- Gọi repository trong callback imperative rồi bỏ kết quả.
- Method trả về Mono.empty() dù đã tạo publisher khác.
- Dùng thenReturn hoặc onNext theo cách bỏ mất một publisher chứa side effect.

### 7.1. map và flatMap khác nhau

map dùng cho phép biến đổi đồng bộ:

~~~java
Mono<OrderSummary> summary =
        orderRepository.findById(id)
                .map(this::toSummary);
~~~

flatMap dùng khi phép biến đổi trả về Publisher:

~~~java
Mono<Customer> customer =
        orderRepository.findById(id)
                .flatMap(order ->
                        customerRepository.findById(order.customerId())
                );
~~~

Nếu dùng map với một hàm trả Mono, kết quả là Mono<Mono<Customer>>. Inner publisher không tự chạy cho đến khi được flatten/subscribe. Dùng flatMap để nối thao tác reactive phụ thuộc.

## 8. Nuốt lỗi khiến transaction commit

Reactive transaction thường commit khi publisher hoàn tất thành công và rollback khi publisher phát error theo rollback rules. Nếu code chuyển error thành complete trước khi error đến transaction boundary, transaction có thể commit.

Ví dụ:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Void> transfer(...) {
    return debitAccount(...)
            .then(creditAccount(...))
            .onErrorResume(error -> {
                log.warn("Transfer failed", error);
                return Mono.empty();
            });
}
~~~

onErrorResume chuyển lỗi thành Mono.empty(). Với transaction manager, publisher đã hoàn tất thành công; rollback không còn được kích hoạt bởi error đã bị nuốt.

Nếu muốn rollback, ghi log nhưng giữ error:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Void> transfer(...) {
    return debitAccount(...)
            .then(creditAccount(...))
            .doOnError(error ->
                    log.warn("Transfer failed", error)
            );
}
~~~

doOnError chỉ quan sát lỗi và không thay đổi tín hiệu. Error vẫn đi tới transaction boundary.

Nếu cần chuyển exception sang loại khác, hãy phát một error mới:

~~~java
return work()
        .onErrorMap(DatabaseException.class,
                error -> new TransferFailedException(error));
~~~

### 8.1. Vị trí của onErrorResume quyết định rollback

Hai cách đặt operator sau đây có semantics khác nhau:

~~~java
// Error đi qua transaction boundary trước, sau đó mới được xử lý.
return transactionalOperator.transactional(work)
        .onErrorResume(error -> fallback());
~~~

~~~java
// Error bị xử lý bên trong transaction boundary.
return transactionalOperator.transactional(
        work.onErrorResume(error -> fallback())
);
~~~

Ở ví dụ thứ nhất, transaction operator nhìn thấy error và có thể rollback trước khi caller áp dụng fallback. Ở ví dụ thứ hai, transaction operator chỉ thấy publisher hoàn tất sau fallback và có thể commit.

Hãy đặt error recovery ở đúng tầng nghiệp vụ. Nếu fallback là một phần của transaction và muốn commit, đó có thể là chủ đích. Nếu lỗi có nghĩa toàn bộ thao tác phải rollback, để error đi qua transaction boundary.

### 8.2. Mono.empty() là hoàn tất thành công

Mono.empty() không phải error. Transaction thường commit nếu publisher hoàn tất rỗng và không có rollback-only marker hoặc lỗi khác.

Ví dụ:

~~~java
return orderRepository.findById(id)
        .switchIfEmpty(Mono.empty())
        .flatMap(this::updateOrder);
~~~

Nếu không tìm thấy order, publisher complete rỗng. Điều đó không tự rollback. Nếu nghiệp vụ yêu cầu coi thiếu order là thất bại, phát exception:

~~~java
return orderRepository.findById(id)
        .switchIfEmpty(Mono.error(
                new OrderNotFoundException(id)
        ))
        .flatMap(this::updateOrder);
~~~

Không dùng empty như một tín hiệu rollback. Hãy phân biệt “không có dữ liệu” với “giao dịch phải thất bại”.

### 8.3. Checked exception và rollback rules

Mặc định của Spring transaction thường rollback với RuntimeException và Error. Checked exception không tự động kích hoạt rollback nếu không có rule phù hợp.

Nếu reactive pipeline phát một checked exception và nghiệp vụ yêu cầu rollback, khai báo rõ:

~~~java
@Transactional(
    transactionManager = "r2dbcTransactionManager",
    rollbackFor = ImportRejectedException.class
)
public Mono<Void> importData(...) {
    return performImport(...);
}
~~~

Kiểm tra rollback rules theo Spring Framework version và kiểu exception thực tế. Không chỉ kiểm tra exception ở log; cần xác nhận trạng thái dữ liệu sau transaction.

## 9. Ranh giới transaction không bao trùm toàn bộ thao tác

Một method có thể có nhiều repository call nhưng chỉ một phần nằm trong transaction chain.

Ví dụ:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(order -> {
                notificationRepository.save(toNotification(order)).subscribe();
                return orderLineRepository.saveAll(toLines(order.id(), command))
                        .thenReturn(order);
            });
}
~~~

Order và OrderLine có thể tham gia transaction, nhưng notification save chạy bằng subscription riêng. Nếu order line thất bại, notification có thể vẫn được commit.

Sửa bằng composition:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(order ->
                    orderLineRepository.saveAll(toLines(order.id(), command))
                            .then(notificationRepository.save(toNotification(order)))
                            .thenReturn(order)
            );
}
~~~

Nếu notification là message tới hệ thống ngoài, không gọi network trực tiếp trong database transaction để giả định atomicity. Ghi outbox row trong cùng transaction rồi publish sau commit.

## 10. Trộn JDBC/JPA và R2DBC trong một transaction

Một ứng dụng hybrid có thể có JpaTransactionManager và R2dbcTransactionManager. Chúng quản lý hai loại resource khác nhau.

Ví dụ:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Void> updateBoth(...) {
    return r2dbcRepository.save(...).then(
            Mono.fromRunnable(() -> jpaRepository.save(...))
    );
}
~~~

R2DBC transaction manager không tự enlist JDBC connection hoặc EntityManager. JPA save có thể chạy trong một transaction imperative khác, hoặc thậm chí không có transaction nếu không cấu hình. Nếu R2DBC commit thất bại sau khi JPA đã commit, dữ liệu có thể lệch.

Không coi một method annotation là transaction phân tán. Các lựa chọn:

- Giữ mọi thao tác atomic trong cùng một công nghệ/resource khi có thể.
- Tách thành các bước độc lập với state machine.
- Dùng transactional outbox và consumer idempotent.
- Dùng saga/compensating action cho workflow nhiều resource.
- Chỉ dùng distributed transaction khi toàn bộ resource và stack hỗ trợ rõ ràng, đã kiểm chứng.

Trong migration, tránh để một use case vừa ghi JPA vừa ghi R2DBC nếu chưa có thiết kế consistency cụ thể.

## 11. Tạo TransactionalOperator khi muốn thấy ranh giới rõ ràng

TransactionalOperator cho phép gói một publisher vào transaction một cách tường minh.

Cấu hình:

~~~java
@Configuration
class TransactionConfiguration {

    @Bean
    TransactionalOperator r2dbcTransactionalOperator(
            ReactiveTransactionManager transactionManager) {
        return TransactionalOperator.create(transactionManager);
    }
}
~~~

Nếu có nhiều manager, inject đúng manager bằng qualifier:

~~~java
@Bean
TransactionalOperator r2dbcTransactionalOperator(
        @Qualifier("r2dbcTransactionManager")
        ReactiveTransactionManager transactionManager) {
    return TransactionalOperator.create(transactionManager);
}
~~~

Sử dụng:

~~~java
@Service
class TransferService {

    private final TransactionalOperator tx;
    private final AccountRepository accounts;

    TransferService(
            TransactionalOperator tx,
            AccountRepository accounts) {
        this.tx = tx;
        this.accounts = accounts;
    }

    Mono<Void> transfer(
            Long fromId,
            Long toId,
            BigDecimal amount) {

        Mono<Void> work =
                accounts.debit(fromId, amount)
                        .then(accounts.credit(toId, amount));

        return tx.transactional(work);
    }
}
~~~

TransactionalOperator giúp nhìn rõ publisher nào được bao bọc. Nó không tự sửa các lỗi do publisher bên trong gọi subscribe(), dùng ConnectionFactory khác hoặc swallow error.

### 11.1. Dùng execute khi cần TransactionStatus

TransactionalOperator cũng có thể nhận callback trả Publisher qua execute:

~~~java
Mono<Void> work =
        tx.execute(status ->
                accounts.debit(fromId, amount)
                        .then(accounts.credit(toId, amount))
        ).then();
~~~

Đây là cách phù hợp khi cần thao tác transaction status trong phạm vi callback. Không gọi subscribe bên trong callback; trả Publisher để operator điều khiển lifecycle.

### 11.2. Đừng bọc quá nhiều publisher không liên quan trong transaction

Một transaction nên bao đúng nhóm thao tác cần atomic. Nếu bọc cả HTTP request, stream export hoặc nhiều công việc không liên quan, connection có thể bị giữ lâu.

Hãy xác định ranh giới theo invariants nghiệp vụ: những thay đổi nào bắt buộc cùng commit hoặc rollback? Chỉ những thao tác đó nên nằm trong transaction.

## 12. Nested calls và propagation

Một method transactional gọi method transactional khác có thể tham gia transaction hiện tại hoặc yêu cầu semantics khác tùy propagation.

Các điểm cần xác nhận:

- REQUIRED thường tham gia transaction hiện có hoặc tạo transaction mới nếu chưa có.
- REQUIRES_NEW yêu cầu transaction độc lập theo khả năng transaction manager.
- SUPPORTS/NOT_SUPPORTED và các propagation khác thay đổi cách tham gia transaction.
- NESTED/savepoint phụ thuộc hỗ trợ của transaction manager và driver.

Không giả định propagation imperative và reactive có mọi hành vi giống nhau trong tất cả phiên bản/driver. Nếu dùng REQUIRES_NEW hoặc savepoint, hãy kiểm tra khả năng của R2dbcTransactionManager và R2DBC driver cụ thể.

Self-invocation vẫn là vấn đề: propagation annotation trên method nội bộ không được áp dụng nếu lời gọi không qua proxy. Nếu cần transaction boundary riêng, chuyển method sang bean khác hoặc dùng TransactionalOperator với manager phù hợp.

## 13. Streaming Flux có thể kéo dài transaction

Khi method transactional trả Flux, transaction có thể tồn tại trong suốt thời gian stream được tiêu thụ, tới khi complete, error hoặc cancel.

Ví dụ:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Flux<Document> exportDocuments(UUID tenantId) {
    return documentRepository.findAllByTenantId(tenantId)
            .map(this::toExportRow);
}
~~~

Nếu client đọc chậm hoặc downstream xử lý lâu, transaction và connection có thể bị giữ lâu. Điều này làm tăng connection hold duration, giữ snapshot/lock tùy query và gây pool pressure.

Cân nhắc:

- Có thực sự cần một transaction nhất quán cho toàn bộ export không?
- Có thể dùng keyset pagination theo từng batch không?
- Có thể tạo snapshot/export job riêng không?
- Có cần giới hạn số stream đang chạy không?
- Hành vi cancellation và cleanup đã được kiểm thử chưa?

Không thu thập toàn bộ dữ liệu vào memory chỉ để đóng transaction sớm nếu tập dữ liệu lớn. Hãy chọn pagination hoặc export workflow phù hợp.

## 14. Cancellation và timeout

Reactive transaction có thể nhận cancellation khi caller hủy subscription hoặc timeout xảy ra. Transaction manager cần cleanup resource và rollback transaction còn mở theo semantics của driver.

Tuy nhiên:

- Cancellation không thể hoàn tác transaction đã commit.
- Timeout đặt ngoài transaction có thể hủy publisher và khiến cleanup diễn ra bất đồng bộ.
- Nếu timeout chỉ được áp dụng cho một inner publisher và error bị nuốt, transaction có thể không rollback như mong muốn.
- Một write đã được database commit nhưng response bị mất vẫn có thể tạo tình huống client không biết kết quả.

Đối với thao tác ghi quan trọng, cần idempotency key hoặc cơ chế kiểm tra trạng thái để xử lý retry an toàn. Đừng coi cancellation như bằng chứng chắc chắn rằng database chưa ghi gì.

Ví dụ:

~~~java
return transactionalOperator.transactional(work)
        .timeout(Duration.ofSeconds(3));
~~~

Ở vị trí này, timeout nằm sau publisher được bọc bởi transaction operator. Khi timeout hủy upstream, transaction manager có cơ hội xử lý cancellation/rollback. Cần test trên driver thực tế để xác nhận cleanup và trạng thái dữ liệu.

## 15. Context bị tách khi tích hợp với callback hoặc API ngoài Reactor

Reactor operators chuẩn thường truyền Reactor Context. Nhưng context có thể không còn khi code:

- Gọi subscribe() thủ công.
- Chuyển sang Executor/CompletableFuture mà không bridge context.
- Đăng ký callback với thư viện không hiểu Reactor Context.
- Tạo một publisher mới và subscribe độc lập.
- Dùng ThreadLocal để đọc transaction hoặc actor.
- Gọi một service đồng bộ rồi tạo reactive chain mới từ kết quả.

Nếu cần bridge sang API ngoài Reactor, hãy dùng cơ chế context propagation phù hợp với Spring/Reactor version và bảo đảm resource lifecycle vẫn nằm trong chain được quản lý.

Không cố truyền object Connection hoặc TransactionStatus bằng biến toàn cục. Connection phải được quản lý bởi transaction manager và lifecycle reactive tương ứng.

## 16. Lỗi cấu hình thường gặp

### 16.1. Repository và transaction manager dùng khác ConnectionFactory

Kiểm tra:

- Bean ConnectionFactory mà repository sử dụng.
- Bean ConnectionFactory mà DatabaseClient sử dụng.
- Bean ConnectionFactory truyền vào R2dbcTransactionManager.
- Qualifier tại các cấu hình nhiều database.
- Pool wrapper hoặc decorator có tạo resource key khác không.

Cùng URL database không đồng nghĩa cùng ConnectionFactory resource. Resource binding của transaction dựa vào ConnectionFactory được cấu hình, không chỉ dựa vào hostname/database name.

### 16.2. Thiếu R2DBC transaction manager

Nếu không có ReactiveTransactionManager phù hợp, annotation có thể chọn manager khác hoặc cấu hình transaction không như mong đợi. Kiểm tra bean thực tế trong ApplicationContext và loại interface mà bean implement.

Không chỉ dựa vào tên method hoặc tên class. Một bean PlatformTransactionManager không phải reactive manager.

### 16.3. Cấu hình nhiều manager không rõ ràng

Nếu có cả JDBC/JPA và R2DBC manager, chỉ định rõ transactionManager trên annotation hoặc tạo TransactionalOperator với manager được inject qua qualifier.

Đừng dựa vào thứ tự bean được đăng ký hoặc giả định manager mặc định luôn là R2DBC.

### 16.4. Repository dùng DatabaseClient khác

Một custom DatabaseClient có thể được tạo từ ConnectionFactory khác với repository chính. Nếu transaction manager chỉ quản lý factory A, câu SQL qua client B không tham gia transaction A.

Đảm bảo tất cả component trong một atomic unit dùng cùng factory/transaction manager.

## 17. Kiểm thử để chứng minh transaction thực sự hoạt động

Unit test với mock không thể chứng minh commit/rollback database. Cần integration test dùng repository thật, R2DBC driver thật và database phù hợp.

Một bài test rollback nên:

1. Tạo dữ liệu fixture với business key riêng.
2. Thực hiện ít nhất hai thao tác ghi trong một transaction.
3. Cố tình phát error sau thao tác đầu hoặc giữa các thao tác.
4. Tiêu thụ publisher tới error.
5. Sau khi transaction kết thúc, đọc dữ liệu bằng một thao tác ngoài transaction đó.
6. Xác nhận không có dữ liệu nào trong nhóm atomic được commit.

Ví dụ với TransactionalOperator:

~~~java
@Test
void shouldRollbackAllWritesWhenSecondStepFails() {
    Mono<Void> work =
            orderRepository.save(orderWithKey("tx-test-1"))
                    .then(Mono.error(
                            new IllegalStateException("force rollback")
                    ));

    StepVerifier.create(transactionalOperator.transactional(work))
            .expectError(IllegalStateException.class)
            .verify();

    StepVerifier.create(orderRepository.existsByBusinessKey("tx-test-1"))
            .expectNext(false)
            .verifyComplete();
}
~~~

Ví dụ cần điều chỉnh theo repository thực tế. Điểm quan trọng là assertion đọc trạng thái sau khi transaction đã hoàn tất và không bị một transaction test bao ngoài che khuất kết quả.

### 17.1. Kiểm tra proxy thật

Trong integration test, inject service từ Spring context:

~~~java
@SpringBootTest
class OrderTransactionIntegrationTest {

    @Autowired
    OrderService orderService;

    @Autowired
    OrderRepository orderRepository;

    // Test gọi bean được Spring quản lý.
}
~~~

Không tự new OrderService nếu mục tiêu là xác nhận AOP proxy. Trong test có thể kiểm tra service có phải AOP proxy bằng Spring AOP utility, nhưng bằng chứng quan trọng hơn vẫn là test behavior commit/rollback.

### 17.2. Không nhầm test-managed transaction với reactive transaction

Một test method có @Transactional không tự chứng minh mọi publisher reactive được thực thi trong đúng transaction mong muốn. Cách quản lý test transaction phụ thuộc Spring Framework/TestContext version và loại transaction manager.

Với reactive test, hãy xác nhận transaction boundary thực tế bằng ReactiveTransactionManager/TransactionalOperator và kiểm tra dữ liệu sau completion. Nếu test framework hỗ trợ reactive transactional test trong version đang dùng, vẫn cần bảo đảm publisher được subscribe trong lifecycle mà framework quản lý.

Khi cần kiểm tra rollback của service, tránh để một transaction ngoài bao quanh toàn bộ test làm dữ liệu biến mất chỉ vì test kết thúc, khiến assertion không chứng minh transaction bên trong đã rollback.

### 17.3. Test trường hợp error bị nuốt

Viết test cho hai hành vi khác nhau:

- Error đi qua transaction boundary: kỳ vọng rollback.
- Error được xử lý bên trong transaction và publisher complete: kỳ vọng commit nếu không có rollback-only marker.

Điều này giúp developer hiểu rõ vị trí của onErrorResume và tránh vô tình biến failure thành success.

### 17.4. Test cancellation và timeout

Với operation có thể bị cancel, dùng StepVerifier hoặc test utility có điều phối để hủy subscription. Sau cleanup, kiểm tra trạng thái database và connection pool.

Không dùng Thread.sleep tùy tiện để đoán transaction đã rollback. Dùng tín hiệu terminal, latch hoặc cơ chế đồng bộ test có giới hạn thời gian. Cần chạy trên driver/database production nếu cancellation semantics quan trọng.

## 18. Quy trình chẩn đoán theo thứ tự

Khi transaction dường như không có hiệu lực, hãy kiểm tra theo thứ tự để tìm đúng lớp lỗi.

### Bước 1: Xác định publisher cuối cùng

- Method transactional trả về Mono/Flux/Publisher chưa?
- Tất cả repository call có được nối vào publisher đó không?
- Có subscribe(), block(), toFuture() hoặc callback tách luồng không?
- Có publisher nào được tạo nhưng bỏ quên không?

### Bước 2: Xác nhận lời gọi đi qua proxy

- Bean được inject từ Spring hay tự new?
- Có self-invocation không?
- Method có thể được proxy intercept không?
- Có gọi từ constructor hoặc initialization path không?
- Có gọi qua bean reference thật không?

### Bước 3: Xác nhận transaction manager

- Bean có implement ReactiveTransactionManager không?
- Annotation có chọn đúng manager không?
- Manager có quản lý R2DBC ConnectionFactory không?
- Có đồng thời JpaTransactionManager/DataSourceTransactionManager không?

### Bước 4: Xác nhận ConnectionFactory

- Repository và DatabaseClient dùng cùng factory không?
- Transaction manager có nhận đúng factory không?
- Có nhiều pool/ConnectionFactory cho cùng database không?
- Có custom configuration/qualifier sai không?

### Bước 5: Xác nhận Reactor Context và error signal

- Có tạo subscription mới không?
- Có dựa vào ThreadLocal không?
- Có onErrorResume/onErrorComplete biến lỗi thành complete không?
- Có checked exception cần rollbackFor không?
- Publisher có hoàn tất rỗng trong khi code kỳ vọng rollback không?

### Bước 6: Kiểm tra database state

- Có đọc trạng thái sau khi transaction hoàn tất không?
- Query xác nhận có dùng cùng database/schema không?
- Có transaction test bao ngoài không?
- Có trigger, autocommit hoặc thao tác khác ghi cùng dữ liệu không?
- Có một service khác đang cập nhật row không?

### Bước 7: Kiểm tra log và metrics

- Transaction begin có xảy ra không?
- Commit hay rollback được gọi?
- Connection nào được mượn?
- Repository query có tham gia cùng transaction không?
- Có acquire timeout, cancellation hoặc cleanup failure không?

## 19. Dấu hiệu và nguyên nhân thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Method có @Transactional nhưng không có rollback | Self-invocation hoặc object tự new | Gọi qua Spring bean proxy |
| Save thứ hai lỗi nhưng save đầu vẫn còn | Hai publisher/subscription tách rời hoặc khác manager | Nối publisher và dùng cùng ConnectionFactory |
| Method trả về trước khi save xong | subscribe() nội bộ hoặc method void | Trả Publisher cuối cùng |
| Lỗi được log nhưng dữ liệu vẫn commit | onErrorResume/onErrorComplete nuốt error | Để error đi qua transaction boundary |
| Không tìm thấy row nhưng transaction commit | Mono.empty là complete thành công | Phát error nếu nghiệp vụ yêu cầu rollback |
| JPA rollback nhưng R2DBC vẫn commit | Chọn nhầm transaction manager hoặc hai resource riêng | Dùng manager đúng, thiết kế consistency hybrid |
| Chỉ mất transaction sau khi chuyển thread | Đọc ThreadLocal hoặc bridge context sai | Dùng Reactor Context; kiểm tra chain |
| Một repository tham gia, repository khác không | Khác ConnectionFactory | Cấu hình chung factory/manager |
| Test rollback pass nhưng production không rollback | Test có transaction bao ngoài hoặc mock | Test integration với database và boundary thật |
| Transaction kéo dài tới khi client đọc xong Flux | Transaction bao toàn stream | Đánh giá streaming/pagination và boundary |
| Timeout nhưng dữ liệu đôi khi vẫn tồn tại | Commit đã xảy ra trước timeout/response loss | Dùng idempotency và kiểm tra trạng thái |
| Annotation trên private helper không có tác dụng | Proxy không intercept | Chuyển boundary sang public bean method |
| REQUIRES_NEW không tạo boundary mới | Self-invocation hoặc manager/driver semantics | Gọi qua proxy và kiểm tra manager hỗ trợ |
| Audit/message vẫn phát dù transaction rollback | Side effect được subscribe độc lập | Dùng outbox trong transaction |

## 20. Những anti-pattern cần loại bỏ

- Gọi subscribe() bên trong service chỉ để kích hoạt query.
- Gọi block() để lấy entity giữa reactive transaction.
- Gọi method transactional bằng this.
- Tự new service trong production code.
- Đặt @Transactional lên private/final method rồi mong proxy intercept.
- Dùng JpaTransactionManager cho repository R2DBC.
- Dùng nhiều ConnectionFactory nhưng nghĩ chúng cùng transaction vì chung URL.
- Tạo Publisher nhưng không compose vào kết quả cuối.
- Dùng map khi cần flatMap để nối Publisher.
- Nuốt lỗi bên trong transaction rồi kỳ vọng rollback.
- Coi Mono.empty() là lỗi.
- Gọi HTTP hoặc message broker trong transaction dài không cần thiết.
- Ghi database bằng JDBC và R2DBC rồi giả định một manager quản lý cả hai.
- Dùng ThreadLocal để giữ transaction/actor context reactive.
- Chỉ kiểm tra annotation thay vì kiểm tra trạng thái database sau commit/rollback.

## 21. Checklist xác nhận transaction boundary

Trước khi kết luận transaction hoạt động, xác nhận:

- [ ] Entry method được gọi qua Spring-managed proxy.
- [ ] Không có self-invocation bỏ qua proxy tại boundary cần thiết.
- [ ] Method trả về Mono, Flux hoặc Publisher phù hợp.
- [ ] ReactiveTransactionManager đúng được chọn.
- [ ] Transaction manager và repository dùng cùng ConnectionFactory.
- [ ] Toàn bộ thao tác database được compose trong publisher trả về.
- [ ] Không có subscribe() hoặc block() tách luồng.
- [ ] Không có Publisher bị bỏ quên hoặc lồng sai bằng map.
- [ ] Reactor Context được giữ qua các operator và integration boundary.
- [ ] Error cần rollback đi qua transaction boundary.
- [ ] Rollback rules phù hợp loại exception.
- [ ] Empty completion được phân biệt với failure.
- [ ] Side effect ngoài database được xử lý sau commit hoặc qua outbox.
- [ ] Flux dài không giữ transaction lâu ngoài yêu cầu.
- [ ] Integration test xác nhận trạng thái dữ liệu sau commit/rollback.
- [ ] Test dùng đúng database/driver và không bị transaction ngoài che khuất.

## 22. Kết luận

Transaction R2DBC không có hiệu lực thường xuất phát từ một trong ba nhóm ranh giới. Proxy không intercept vì self-invocation, object tự tạo hoặc method không thể được proxy; transaction manager/ConnectionFactory không đúng; hoặc publisher reactive đã tách khỏi subscription và Reactor Context được transaction quản lý. Ngoài ra, nuốt error, trả Mono.empty() hoặc trộn JDBC/JPA với R2DBC có thể làm kết quả khác với kỳ vọng rollback.

Hãy xác nhận lời gọi đi qua Spring proxy, chọn đúng ReactiveTransactionManager, bảo đảm repository dùng cùng ConnectionFactory và nối mọi thao tác database vào một publisher duy nhất. Reactive transaction dựa trên Reactor Context chứ không phải ThreadLocal; không gọi subscribe() hoặc block() bên trong service để điều khiển thao tác. Để rollback, error cần đi qua transaction boundary và phù hợp rollback rules. Khi cần ranh giới rõ ràng, dùng TransactionalOperator.

Cuối cùng, chứng minh behavior bằng integration test trên database thật: thực hiện nhiều thao tác, phát lỗi có chủ đích, chờ transaction hoàn tất rồi đọc dữ liệu từ bên ngoài boundary. Quan sát begin/commit/rollback, connection acquire và context giúp phân biệt lỗi proxy, cấu hình và luồng reactive thay vì chỉ thêm annotation hoặc thay đổi pool theo phỏng đoán.

