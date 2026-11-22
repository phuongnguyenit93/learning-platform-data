# Khai báo @Transactional trên phương thức trả về Publisher

## 1. Giao dịch reactive trong Spring Data R2DBC

Một nghiệp vụ thường gồm nhiều thao tác database phải thành công hoặc thất bại cùng nhau. Ví dụ tạo đơn hàng có thể cần insert Order, insert các OrderLine và cập nhật số lượng tồn kho. Nếu bước cuối thất bại, ứng dụng thường muốn rollback các thay đổi trước đó để database không lưu một trạng thái dở dang.

Trong Spring Data R2DBC, các thao tác database trả về kiểu reactive như `Mono` và `Flux`. Vì vậy, giao dịch cũng phải được quản lý theo mô hình reactive. Spring cung cấp annotation **@Transactional** để khai báo ranh giới giao dịch trên phương thức trả về một reactive publisher.

Ví dụ:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final OrderLineRepository orderLineRepository;

    public OrderService(
            OrderRepository orderRepository,
            OrderLineRepository orderLineRepository) {
        this.orderRepository = orderRepository;
        this.orderLineRepository = orderLineRepository;
    }

    @Transactional
    public Mono<Order> createOrder(CreateOrderCommand command) {
        Order order = new Order(
                null,
                command.customerId(),
                "NEW"
        );

        return orderRepository.save(order)
                .flatMap(savedOrder -> {
                    List<OrderLine> lines = command.lines().stream()
                            .map(line -> new OrderLine(
                                    null,
                                    savedOrder.id(),
                                    line.sku(),
                                    line.quantity()
                            ))
                            .toList();

                    return orderLineRepository.saveAll(lines)
                            .thenReturn(savedOrder);
                });
    }
}
~~~

Spring quản lý transaction cho publisher được phương thức trả về. Khi chuỗi reactive hoàn tất thành công, transaction được commit; khi chuỗi kết thúc bằng lỗi, transaction được rollback theo rollback rules. Các thao tác repository phải tham gia cùng transaction manager và cùng ConnectionFactory.

Điểm cốt lõi là **publisher được trả về chính là một phần của transaction boundary**. Việc gọi repository tạo ra publisher chưa có nghĩa câu SQL đã chạy ngay tại thời điểm gọi phương thức. Reactive publisher thường thực thi khi có subscription.

## 2. Vì sao cần ReactiveTransactionManager?

Spring có hai mô hình transaction manager chính:

- **PlatformTransactionManager:** quản lý giao dịch imperative, thường gắn với thread-bound transaction context.
- **ReactiveTransactionManager:** quản lý giao dịch reactive, truyền transaction context theo Reactor Context.

Với Spring Data R2DBC, transaction manager thông dụng là **R2dbcTransactionManager** thuộc Spring Framework:

~~~java
import io.r2dbc.spi.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.r2dbc.connection.R2dbcTransactionManager;
import org.springframework.transaction.ReactiveTransactionManager;

@Configuration
class TransactionConfiguration {

    @Bean
    ReactiveTransactionManager transactionManager(
            ConnectionFactory connectionFactory) {
        return new R2dbcTransactionManager(connectionFactory);
    }
}
~~~

R2dbcTransactionManager quản lý một R2DBC ConnectionFactory. Nó lấy connection, bắt đầu transaction, đưa connection được quản lý vào reactive context và hoàn tất commit/rollback theo lifecycle của publisher.

Trong ứng dụng Spring Boot, cấu hình tự động có thể tạo transaction manager khi điều kiện phù hợp được đáp ứng. Nếu ứng dụng có nhiều ConnectionFactory hoặc tự cấu hình persistence infrastructure, cần khai báo và liên kết transaction manager rõ ràng.

Không dùng transaction manager JDBC/JPA cho thao tác R2DBC. Một JpaTransactionManager hoặc DataSourceTransactionManager không tự quản lý R2DBC ConnectionFactory.

## 3. Bật transaction annotation

Để Spring xử lý annotation giao dịch, ứng dụng cần transaction management infrastructure. Trong ứng dụng Spring Boot có starter phù hợp, transaction auto-configuration thường được thiết lập khi có transaction manager. Với cấu hình Spring thuần, có thể bật bằng `@EnableTransactionManagement`:

~~~java
@Configuration
@EnableTransactionManagement
class TransactionConfiguration {
}
~~~

Annotation `@Transactional` thuộc package:

~~~java
import org.springframework.transaction.annotation.Transactional;
~~~

Cấu hình bật annotation tạo cơ chế proxy/interceptor để nhận diện lời gọi phương thức và áp dụng transaction policy. Trong Spring Boot, không nên thêm cấu hình trùng lặp nếu auto-configuration đã bật chức năng cần thiết.

Ngoài việc có annotation, ứng dụng còn phải có một `ReactiveTransactionManager` phù hợp. Nếu không có reactive manager, hoặc phương thức không được nhận diện là reactive return type, Spring có thể chọn transaction manager không phù hợp hoặc không tạo được transaction như mong muốn.

## 4. Phương thức trả về Publisher là điều kiện quan trọng

Spring nhận diện phương thức reactive dựa trên kiểu trả về được hỗ trợ bởi reactive adapter infrastructure, điển hình là:

- `Mono<T>`
- `Flux<T>`
- `Publisher<T>`
- Một số kiểu reactive được adapter tương ứng hỗ trợ.

Ví dụ:

~~~java
@Transactional
public Mono<Customer> createCustomer(CreateCustomerCommand command) {
    Customer customer = new Customer(
            null,
            command.name(),
            command.email()
    );

    return customerRepository.save(customer);
}
~~~

Phương thức trả về `Mono<Customer>`, vì vậy Spring có thể áp dụng reactive transaction management cho publisher đó.

Với một thao tác không cần phát dữ liệu nhưng cần hoàn tất trong transaction, có thể trả `Mono<Void>`:

~~~java
@Transactional
public Mono<Void> archiveCustomer(Long id) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)
            ))
            .flatMap(customer -> {
                Customer archived = customer.withStatus("ARCHIVED");
                return customerRepository.save(archived);
            })
            .then();
}
~~~

Ở đây, `then()` chuyển kết quả cuối thành tín hiệu hoàn tất. Publisher vẫn nằm trong transaction boundary.

### 4.1. Phương thức void hoặc trả về giá trị đồng bộ không phải reactive transaction boundary

Ví dụ sau không thể quản lý lifecycle reactive của một publisher vì method trả về void:

~~~java
@Transactional
public void createCustomer(Customer customer) {
    customerRepository.save(customer);
}
~~~

Lời gọi `save` chỉ tạo publisher và publisher bị bỏ đi. Không có subscriber tiêu thụ nó, nên thao tác có thể không chạy. Annotation không tự subscribe vào publisher bị bỏ qua.

Tương tự, method trả về một object đồng bộ:

~~~java
@Transactional
public Customer createCustomer(Customer customer) {
    customerRepository.save(customer).subscribe();
    return customer;
}
~~~

cũng không tạo được ranh giới reactive đúng. Subscription tự tạo chạy tách khỏi publisher mà method trả về; transaction interceptor không thể điều phối lifecycle của thao tác bị tách đó.

Với R2DBC, hãy trả `Mono`, `Flux` hoặc Publisher phù hợp từ method transactional và kết hợp toàn bộ thao tác trong publisher đó.

## 5. Transaction bắt đầu khi publisher được subscribe

Reactive execution có tính lazy. Khi gọi:

~~~java
Mono<Order> result = orderService.createOrder(command);
~~~

biến result mới là một mô tả công việc. Chưa thể kết luận database đã insert hoặc transaction đã mở.

Trong mô hình proxy transaction reactive, Spring bao publisher được trả về. Khi subscriber tiêu thụ publisher, transaction manager bắt đầu transaction và đưa context của transaction vào Reactor Context. Khi publisher kết thúc, Spring commit hoặc rollback.

~~~text
Caller gọi phương thức qua Spring proxy
                 |
                 v
       Phương thức trả Publisher
                 |
                 v
       Subscriber subscribe()
                 |
                 v
       Reactive transaction bắt đầu
                 |
                 v
       Publisher thực hiện các thao tác
                 |
          +------+------+
          |             |
          v             v
       Complete       Error / cancel
          |             |
          v             v
        Commit        Rollback
~~~

Điều này có một hệ quả thực tế: không nên gọi method transactional rồi bỏ publisher. Nếu không ai subscribe, không có pipeline database được thực thi và transaction reactive cũng không được vận hành theo cách ứng dụng mong đợi.

Trong WebFlux, controller có thể trả publisher cho framework để framework subscribe. Trong test, dùng StepVerifier. Trong một pipeline service khác, nối publisher bằng `flatMap`, `then` hoặc operator phù hợp.

## 6. Ghép nhiều thao tác trong cùng transaction

Ví dụ tạo đơn hàng gồm root và các dòng hàng:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    Order order = new Order(
            null,
            command.customerId(),
            "NEW"
    );

    return orderRepository.save(order)
            .flatMap(savedOrder -> {
                Flux<OrderLine> lines = Flux.fromIterable(command.lines())
                        .map(line -> new OrderLine(
                                null,
                                savedOrder.id(),
                                line.sku(),
                                line.quantity()
                        ));

                return orderLineRepository.saveAll(lines)
                        .thenReturn(savedOrder);
            });
}
~~~

Thứ tự thực hiện:

1. Lưu Order và nhận ID được database sinh.
2. Dùng ID đó để tạo các OrderLine.
3. Lưu các OrderLine.
4. Khi tất cả publisher hoàn tất, phát Order đã lưu.
5. Transaction interceptor commit khi toàn bộ publisher hoàn tất thành công.

Nếu lưu một dòng hàng thất bại và lỗi truyền ra khỏi publisher transactional, transaction sẽ rollback các thao tác trước đó trong cùng transaction.

Với mô hình aggregate của Spring Data Relational, cần thiết kế việc lưu aggregate root và các thành phần theo mapping phù hợp. Ví dụ trên minh họa trình tự transaction; cách lưu collection thực tế phụ thuộc entity mapping và repository được dùng.

## 7. Dùng flatMap, then và map đúng trong transaction

Các Reactor operator quyết định publisher nào nằm trong chuỗi được transaction quản lý.

### 7.1. flatMap khi thao tác kế tiếp trả Publisher

~~~java
@Transactional
public Mono<OrderReceipt> placeOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(order ->
                    paymentAttemptRepository.save(
                            toPaymentAttempt(order.id(), command)
                    ).map(attempt ->
                            new OrderReceipt(order.id(), attempt.id())
                    )
            );
}
~~~

Thao tác lưu payment attempt được nối vào publisher của thao tác lưu order. Vì publisher cuối cùng được trả về, cả hai có thể tham gia cùng transaction nếu dùng đúng hạ tầng.

### 7.2. then khi chỉ cần chờ thao tác hoàn tất

~~~java
@Transactional
public Mono<Void> deleteCustomerData(Long customerId) {
    return addressRepository.deleteByCustomerId(customerId)
            .then(orderNoteRepository.deleteByCustomerId(customerId))
            .then(customerRepository.deleteById(customerId));
}
~~~

`then` bỏ qua giá trị của publisher trước và chỉ chạy publisher kế tiếp sau khi publisher trước hoàn tất. Nếu bất kỳ thao tác nào phát lỗi, lỗi truyền tiếp và transaction có thể rollback.

### 7.3. map khi chỉ biến đổi dữ liệu đồng bộ

~~~java
@Transactional
public Mono<OrderResponse> create(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .map(saved -> new OrderResponse(
                    saved.id(),
                    saved.status()
            ));
}
~~~

`map` chỉ chuyển đổi object đã phát ra, không dùng để gọi một thao tác reactive khác. Nếu bên trong map trả về Mono, kết quả sẽ thành Mono lồng nhau; hãy dùng flatMap trong trường hợp đó.

## 8. Không tự subscribe hoặc block bên trong phương thức transactional

Đây là lỗi dễ làm mất transaction boundary.

### 8.1. Không subscribe thủ công

Không nên:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    orderRepository.save(toOrder(command)).subscribe();

    return Mono.just(new Order(null, command.customerId(), "NEW"));
}
~~~

Subscription do `subscribe()` tạo ra là một luồng thực thi độc lập. Transaction interceptor chỉ quản lý publisher mà method trả về; thao tác bị subscribe riêng có thể chạy ngoài transaction, không được rollback cùng các bước khác và lỗi của nó không được trả về caller.

Cách đúng:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command));
}
~~~

### 8.2. Không block để lấy kết quả

Không nên:

~~~java
@Transactional
public Order createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command)).block();
}
~~~

`block()` chặn thread chờ kết quả và phá vỡ cách phối hợp reactive. Trong WebFlux, nó có thể chặn event-loop và gây giảm thông lượng hoặc lỗi runtime.

Hãy trả publisher cho caller. Nếu một bước cần kết quả từ bước trước, dùng `flatMap` để biểu diễn quan hệ phụ thuộc.

### 8.3. Không tạo publisher rồi bỏ qua

Không nên:

~~~java
@Transactional
public Mono<Void> createOrder(CreateOrderCommand command) {
    orderRepository.save(toOrder(command));
    return Mono.empty();
}
~~~

Publisher từ `save` không được nối vào kết quả trả về nên không được tiêu thụ. Cần trả trực tiếp hoặc ghép nó:

~~~java
@Transactional
public Mono<Void> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command)).then();
}
~~~

## 9. Reactor Context và việc chuyển thread

Imperative transaction thường gắn trạng thái với thread. Reactive transaction không dựa vào giả định mọi thao tác luôn chạy trên cùng một thread. Spring lưu transaction context trong **Reactor Context**, và các operator Reactor chuẩn truyền context theo subscription.

Do đó, việc dùng `publishOn` hoặc `subscribeOn` trong pipeline không tự động làm mất transaction chỉ vì callback chạy trên thread khác:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .publishOn(Schedulers.parallel())
            .flatMap(saved ->
                    orderLineRepository.saveAll(toLines(saved.id(), command))
                            .thenReturn(saved)
            );
}
~~~

Dù vậy, không nên chuyển công việc blocking vào reactive transaction. Thread switching không biến JDBC call hoặc file/network blocking thành reactive operation. Nếu cần truy cập database, hãy dùng R2DBC client/repository tham gia transaction context.

Không lưu transaction context vào biến ThreadLocal tự quản lý hoặc giả định một thread cụ thể sẽ giữ connection. Hãy để Spring và Reactor quản lý context.

## 10. Các thao tác phải dùng cùng transaction-aware infrastructure

Một reactive transaction chỉ quản lý những thao tác tham gia đúng transaction context và ConnectionFactory.

Các API Spring Data R2DBC như:

- ReactiveCrudRepository.
- R2dbcEntityTemplate.
- DatabaseClient được cấu hình với cùng ConnectionFactory.

có thể tham gia transaction do R2dbcTransactionManager quản lý.

Nếu code tự lấy connection trực tiếp từ `ConnectionFactory.create()` và tự thực thi statement, nó có thể không dùng connection đã được bind vào transaction context. Khi cần truy cập connection theo transaction, dùng cơ chế Spring như `ConnectionFactoryUtils` hoặc API được thiết kế để tham gia context hiện hành.

Ví dụ DatabaseClient được xây dựng từ ConnectionFactory tương ứng thường tích hợp với cơ chế quản lý connection của Spring:

~~~java
@Bean
DatabaseClient databaseClient(ConnectionFactory connectionFactory) {
    return DatabaseClient.create(connectionFactory);
}
~~~

Điều quan trọng là DatabaseClient, template và transaction manager phải được cấu hình với đúng ConnectionFactory. Nếu template dùng factory A nhưng transaction manager quản lý factory B, thao tác template không tham gia transaction của manager B.

## 11. Rollback khi Publisher phát lỗi

Mặc định, Spring rollback transaction khi phương thức transactional kết thúc bằng unchecked exception (RuntimeException) hoặc Error. Checked exception theo mặc định không kích hoạt rollback, trừ khi cấu hình rollback rule.

Ví dụ:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(order ->
                    validateAndSaveLines(order, command)
                            .thenReturn(order)
            );
}
~~~

Nếu `validateAndSaveLines` phát `IllegalStateException`, lỗi đi ra khỏi publisher và transaction được rollback.

Có thể khai báo rollback rule:

~~~java
@Transactional(rollbackFor = BusinessRuleException.class)
public Mono<Order> createOrder(CreateOrderCommand command) {
    return performCreate(command);
}
~~~

Hoặc loại trừ một loại exception:

~~~java
@Transactional(noRollbackFor = DuplicateNotificationException.class)
public Mono<Order> createOrder(CreateOrderCommand command) {
    return performCreate(command);
}
~~~

Chỉ cấu hình `noRollbackFor` khi nghiệp vụ thực sự muốn commit dù exception đó xảy ra. Đừng dùng rule này để che lỗi database hoặc lỗi toàn vẹn dữ liệu.

### 11.1. Lỗi cần truyền qua ranh giới transaction

Nếu code bắt lỗi và biến nó thành giá trị thành công bên trong publisher transactional, transaction manager có thể chỉ nhìn thấy completion bình thường và commit.

Ví dụ:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(order -> saveLines(order, command))
            .onErrorResume(error -> Mono.empty());
}
~~~

Ở đây lỗi của bước saveLines bị chuyển thành completion rỗng. Nếu không đánh dấu rollback-only hoặc để lỗi thoát khỏi transactional publisher, transaction có thể commit những thao tác trước đó.

Nếu cần chuyển lỗi thành response nghiệp vụ, hãy xử lý sau khi publisher transactional đã rollback, hoặc dùng cách đánh dấu transaction rollback-only phù hợp với transaction API. Thiết kế đơn giản và dễ dự đoán nhất là để lỗi đi qua boundary rồi chuyển đổi ở tầng gọi.

Ví dụ:

~~~java
public Mono<OrderResponse> create(CreateOrderCommand command) {
    return transactionalOrderWriter.createOrder(command)
            .map(OrderResponse::from)
            .onErrorMap(
                    BusinessRuleException.class,
                    OrderRejectedException::new
            );
}
~~~

Trong ví dụ, phương thức writer là transaction boundary riêng. Caller có thể ánh xạ lỗi sau khi transaction interceptor đã quan sát lỗi và rollback.

## 12. Rollback khi subscriber hủy subscription

Reactive Streams cho phép subscriber hủy subscription. Ví dụ HTTP client đóng kết nối hoặc caller không còn cần kết quả. Với reactive transaction, cancellation được xem là một kết thúc không thành công đối với transaction đang mở; Spring reactive transaction manager thực hiện rollback khi phù hợp.

Điều này khác với một publisher hoàn tất bình thường. Không nên coi việc client ngừng chờ là bằng chứng database đã commit.

Cũng cần lưu ý rằng cancellation không thể đảo ngược một transaction đã commit. Nếu transaction đã hoàn tất trước khi cancellation được xử lý, rollback không còn ý nghĩa. Vì vậy, API ghi dữ liệu cần có cách tra cứu trạng thái hoặc idempotency khi client không biết kết quả do timeout/disconnect.

## 13. Phạm vi của @Transactional ở class và method

Có thể đặt annotation ở cấp class:

~~~java
@Service
@Transactional
public class CustomerService {

    public Mono<Customer> create(CreateCustomerCommand command) {
        return customerRepository.save(toCustomer(command));
    }

    public Mono<Customer> find(Long id) {
        return customerRepository.findById(id);
    }
}
~~~

Annotation cấp class cung cấp transaction metadata mặc định cho các phương thức phù hợp của class. Có thể ghi đè ở method:

~~~java
@Transactional(readOnly = true)
public Mono<Customer> find(Long id) {
    return customerRepository.findById(id);
}

@Transactional
public Mono<Customer> create(CreateCustomerCommand command) {
    return customerRepository.save(toCustomer(command));
}
~~~

Method-level metadata có độ ưu tiên cao hơn class-level metadata khi xác định transaction attribute.

Với ứng dụng đọc nhiều, có thể đánh dấu query method là readOnly:

~~~java
@Transactional(readOnly = true)
public Flux<Customer> findActive() {
    return customerRepository.findByStatus("ACTIVE");
}
~~~

`readOnly = true` là transaction hint. Khả năng database/driver thực thi hoặc tối ưu theo hint này phụ thuộc transaction manager và hệ quản trị. Không coi nó là cơ chế bảo mật ngăn mọi lệnh ghi; vẫn cần authorization, quyền database và thiết kế query phù hợp.

## 14. Propagation và transaction lồng nhau

`@Transactional` hỗ trợ propagation để xác định hành vi khi một phương thức được gọi trong bối cảnh đã có transaction.

Một số giá trị thường gặp:

| Propagation | Ý nghĩa khái quát |
|---|---|
| REQUIRED | Tham gia transaction hiện có hoặc tạo transaction mới |
| REQUIRES_NEW | Tạm ngưng transaction hiện có và tạo transaction riêng nếu transaction manager hỗ trợ |
| SUPPORTS | Tham gia transaction nếu có; nếu không thì chạy không transaction |
| MANDATORY | Yêu cầu phải có transaction hiện tại |
| NOT_SUPPORTED | Tạm ngưng transaction hiện tại và chạy không transaction |
| NEVER | Không cho phép có transaction hiện tại |
| NESTED | Yêu cầu nested transaction/savepoint nếu transaction manager hỗ trợ |

Ví dụ:

~~~java
@Transactional(propagation = Propagation.REQUIRED)
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command));
}
~~~

`REQUIRED` là mặc định. Nếu một service khác gọi method này trong cùng reactive transaction context và cùng transaction manager, thao tác có thể tham gia transaction hiện tại.

Không giả định mọi propagation mode đều được hỗ trợ giống nhau bởi mọi R2DBC driver hoặc transaction manager. Đặc biệt, `NESTED` phụ thuộc khả năng savepoint và hỗ trợ của transaction manager/driver. Hãy xác nhận với database thực tế trước khi dùng.

## 15. Isolation, timeout và readOnly

Có thể chỉ định các thuộc tính transaction:

~~~java
@Transactional(
        isolation = Isolation.READ_COMMITTED,
        timeout = 10,
        readOnly = true
)
public Flux<OrderSummary> findRecentOrders() {
    return orderRepository.findRecentSummaries();
}
~~~

- **isolation:** yêu cầu mức cô lập transaction, chẳng hạn READ_COMMITTED hoặc REPEATABLE_READ.
- **timeout:** giới hạn thời gian transaction theo khả năng transaction manager.
- **readOnly:** gợi ý transaction chỉ đọc.
- **propagation:** xác định cách tham gia hoặc tạo transaction.
- **rollbackFor/noRollbackFor:** quy định loại exception có hoặc không gây rollback.

Các thuộc tính này không đảm bảo database nào cũng hỗ trợ mọi giá trị giống nhau. Isolation thực tế chịu ảnh hưởng hệ quản trị, driver và transaction manager. Timeout của transaction cũng không thay thế timeout query, timeout connection acquisition hoặc deadline HTTP.

Không tăng transaction timeout để che một query chậm mà chưa hiểu nguyên nhân. Hãy đo query plan, thời gian chờ pool và thời gian thực thi riêng.

## 16. Nhiều transaction manager và nhiều ConnectionFactory

Một ứng dụng có thể kết nối nhiều database. Mỗi R2dbcTransactionManager quản lý một ConnectionFactory. Transaction của database A không tự bao trùm thao tác ở database B.

Có thể đặt tên bean transaction manager:

~~~java
@Bean("customerTransactionManager")
ReactiveTransactionManager customerTransactionManager(
        @Qualifier("customerConnectionFactory")
        ConnectionFactory connectionFactory) {
    return new R2dbcTransactionManager(connectionFactory);
}

@Bean("orderTransactionManager")
ReactiveTransactionManager orderTransactionManager(
        @Qualifier("orderConnectionFactory")
        ConnectionFactory connectionFactory) {
    return new R2dbcTransactionManager(connectionFactory);
}
~~~

Sau đó chỉ định manager cho method:

~~~java
@Transactional(transactionManager = "orderTransactionManager")
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command));
}
~~~

Repository/template trong method này phải dùng order ConnectionFactory tương ứng. Nếu method gọi cả customer database và order database, một local transaction manager không thể atomic commit cả hai.

Để phối hợp thay đổi qua nhiều database/service, thường cần kiến trúc như saga, outbox hoặc workflow bù trừ. Không giả định một annotation @Transactional duy nhất cung cấp distributed transaction.

## 17. Self-invocation và giới hạn proxy

Trong cấu hình transaction annotation mặc định, Spring thường dùng proxy để chặn lời gọi từ bean bên ngoài. Vì vậy, một phương thức gọi phương thức transactional khác trên cùng instance có thể bỏ qua proxy.

Ví dụ dễ gây hiểu nhầm:

~~~java
@Service
public class OrderService {

    public Mono<Order> submit(CreateOrderCommand command) {
        return this.createInTransaction(command);
    }

    @Transactional
    public Mono<Order> createInTransaction(CreateOrderCommand command) {
        return orderRepository.save(toOrder(command));
    }
}
~~~

Lời gọi `this.createInTransaction(...)` là self-invocation và không đi qua Spring proxy. Annotation trên method được gọi có thể không được áp dụng.

Cách rõ ràng hơn là đặt transaction boundary trong một bean riêng:

~~~java
@Service
public class OrderWriter {

    private final OrderRepository repository;

    public OrderWriter(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Mono<Order> create(CreateOrderCommand command) {
        return repository.save(toOrder(command));
    }
}
~~~

~~~java
@Service
public class OrderFacade {

    private final OrderWriter writer;

    public OrderFacade(OrderWriter writer) {
        this.writer = writer;
    }

    public Mono<OrderResponse> submit(CreateOrderCommand command) {
        return writer.create(command).map(OrderResponse::from);
    }
}
~~~

Lời gọi qua bean proxy bảo đảm interceptor có cơ hội áp dụng transaction metadata. Với proxy-based transaction management, cũng cần chú ý method visibility và cách bean được gọi; phương thức public được gọi từ bean khác là lựa chọn dễ dự đoán nhất.

## 18. Transaction và concurrency trong reactive pipeline

Reactive code cho phép ghép nhiều publisher. Nhưng việc chạy nhiều thao tác database song song trong cùng một transaction cần được cân nhắc.

Ví dụ:

~~~java
Mono.zip(
        customerRepository.findById(customerId),
        inventoryRepository.findBySku(sku)
)
~~~

Nếu hai repository dùng cùng ConnectionFactory và transaction context, các thao tác có thể cùng sử dụng connection được bind cho transaction. Không phải mọi R2DBC driver/connection đều hỗ trợ nhiều statement đồng thời trên cùng một connection. Việc dùng `zip` hoặc `flatMap` với concurrency có thể gây lỗi hoặc hành vi không mong muốn tùy driver.

Với thao tác phụ thuộc nhau hoặc cần tuần tự trên cùng transaction connection, dùng `flatMap` theo chuỗi:

~~~java
return customerRepository.findById(customerId)
        .flatMap(customer ->
                inventoryRepository.findBySku(sku)
                        .map(inventory -> new OrderDraft(customer, inventory))
        );
~~~

Nếu thực sự muốn chạy song song, cần xác nhận driver và cách transaction manager cấp connection hỗ trợ mô hình đó. Không nên mặc định reactive concurrency đồng nghĩa một transaction có thể dùng nhiều connection độc lập mà vẫn atomic.

Transaction dài cũng giữ connection và có thể giữ lock hoặc snapshot lâu hơn. Chỉ đưa các thao tác database cần atomic vào transaction; tránh gọi HTTP, gửi email hoặc chờ người dùng trong khi transaction đang mở.

## 19. Kết hợp DatabaseClient và R2dbcEntityTemplate trong transaction

Hai API có thể cùng tham gia một transaction nếu sử dụng cùng ConnectionFactory và transaction-aware infrastructure.

Ví dụ cập nhật entity bằng template và ghi audit bằng DatabaseClient:

~~~java
@Transactional
public Mono<Customer> changeStatus(Long id, String newStatus) {
    return template.selectOne(
                Query.query(Criteria.where("id").is(id)),
                Customer.class
            )
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)
            ))
            .flatMap(customer ->
                    template.update(Customer.class)
                            .matching(Query.query(Criteria.where("id").is(id)))
                            .apply(Update.update("status", newStatus))
                            .flatMap(rows -> {
                                if (rows != 1) {
                                    return Mono.error(
                                            new IllegalStateException(
                                                    "Expected one updated row"
                                            )
                                    );
                                }

                                return databaseClient.sql("""
                                        INSERT INTO customer_audit
                                            (customer_id, action)
                                        VALUES (:id, :action)
                                        """)
                                    .bind("id", id)
                                    .bind("action", "STATUS_CHANGED")
                                    .fetch()
                                    .rowsUpdated()
                                    .thenReturn(new Customer(
                                            customer.id(),
                                            customer.name(),
                                            customer.email(),
                                            newStatus
                                    ));
                            })
            );
}
~~~

Template thực hiện thao tác theo entity metadata; DatabaseClient chạy SQL audit. Cả hai có thể tham gia transaction do cùng R2DBC ConnectionFactory quản lý.

Nếu audit insert thất bại và lỗi truyền ra ngoài, cập nhật status có thể rollback cùng transaction. Nếu code bắt lỗi audit và biến thành completion bình thường, transaction có thể commit status mà không có audit; hãy quyết định rõ đó có phải semantics mong muốn hay không.

## 20. Dùng TransactionalOperator thay cho annotation

Khi cần ranh giới transaction linh hoạt theo từng đoạn publisher, có thể dùng **TransactionalOperator**:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

@Service
public class OrderWriter {

    private final TransactionalOperator transactionalOperator;
    private final OrderRepository orderRepository;
    private final OrderLineRepository orderLineRepository;

    public OrderWriter(
            TransactionalOperator transactionalOperator,
            OrderRepository orderRepository,
            OrderLineRepository orderLineRepository) {
        this.transactionalOperator = transactionalOperator;
        this.orderRepository = orderRepository;
        this.orderLineRepository = orderLineRepository;
    }

    public Mono<Order> create(CreateOrderCommand command) {
        Mono<Order> work = orderRepository.save(toOrder(command))
                .flatMap(order ->
                        orderLineRepository.saveAll(toLines(order.id(), command))
                                .thenReturn(order)
                );

        return transactionalOperator.transactional(work);
    }
}
~~~

TransactionalOperator bọc một publisher và áp dụng transaction cho phần publisher đó. Nó hữu ích khi:

- Không muốn dùng proxy annotation.
- Cần xác định ranh giới transaction trong một method lớn.
- Cần điều khiển transaction trên một nhánh publisher cụ thể.
- Muốn viết test hoặc composition rõ ràng.

Annotation phù hợp với transaction boundary ở cấp service method; TransactionalOperator phù hợp khi cần bọc một đoạn pipeline. Cả hai đều cần ReactiveTransactionManager đúng.

Không bọc cùng một đoạn công việc bằng nhiều transaction boundary không cần thiết. Hãy hiểu propagation và transaction context trước khi lồng nhiều operator.

## 21. Kiểm thử phương thức @Transactional reactive

Test cần subscribe vào publisher và kiểm tra cả dữ liệu commit lẫn rollback.

### 21.1. Kiểm tra commit khi thành công

~~~java
@Test
void shouldCommitOrderAndLines() {
    CreateOrderCommand command = sampleCommand();

    StepVerifier.create(orderWriter.createOrder(command))
            .assertNext(order -> assertThat(order.id()).isNotNull())
            .verifyComplete();

    StepVerifier.create(orderRepository.count())
            .expectNext(1L)
            .verifyComplete();

    StepVerifier.create(orderLineRepository.count())
            .expectNext(2L)
            .verifyComplete();
}
~~~

Các assertion sau khi publisher hoàn tất xác nhận dữ liệu đã được commit và có thể đọc lại qua transaction khác hoặc context kiểm thử phù hợp.

### 21.2. Kiểm tra rollback khi bước sau thất bại

Có thể tạo một command chứa dòng hàng vi phạm constraint để bước lưu line phát lỗi:

~~~java
@Test
void shouldRollbackOrderWhenLineInsertFails() {
    CreateOrderCommand invalid = commandWithInvalidLine();

    StepVerifier.create(orderWriter.createOrder(invalid))
            .expectError()
            .verify();

    StepVerifier.create(orderRepository.count())
            .expectNext(0L)
            .verifyComplete();
}
~~~

Test này kiểm tra rằng Order đã insert trước đó không còn tồn tại sau khi bước sau thất bại. Cần dùng database test thực tế hoặc Testcontainers để kiểm tra transaction semantics của driver.

### 21.3. Kiểm tra cancellation nếu use case cần

Với publisher dài hoặc endpoint streaming, có thể kiểm tra cancellation và rollback. Test cần chủ động tạo publisher có thể hủy sau khi một thao tác đã bắt đầu, sau đó xác nhận trạng thái database không bị commit ngoài ý muốn.

Không phải mọi test đều cần cancellation case; ưu tiên test những đường đi mà caller thực sự có thể hủy.

### 21.4. Tránh để test transaction bao ngoài làm che kết quả

Một số test framework có thể tự mở transaction cho test method. Nếu transaction của test bao quanh thao tác cần kiểm tra, dữ liệu có thể chưa commit hoặc có thể rollback khi test kết thúc, làm kết quả quan sát khác với request thật.

Hãy hiểu transaction boundary của test, subscription và service. Với test commit/rollback, cần bố trí cách đọc dữ liệu để xác nhận kết quả sau khi transaction của service đã kết thúc.

## 22. Những lỗi thường gặp khi dùng @Transactional với Publisher

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Repository operation không chạy | Publisher bị bỏ qua hoặc không được subscribe | Trả publisher hoặc ghép vào pipeline |
| Thao tác không rollback cùng nhau | Một publisher được subscribe riêng | Không gọi `subscribe()` trong service |
| Thread bị chặn | Gọi `block()` trong reactive flow | Dùng `flatMap`, `map`, `then` và trả Publisher |
| Annotation không có tác dụng | Self-invocation không đi qua proxy | Gọi qua bean khác hoặc tổ chức lại service boundary |
| Không có reactive transaction | Thiếu ReactiveTransactionManager hoặc cấu hình sai manager | Cấu hình R2dbcTransactionManager đúng ConnectionFactory |
| Chỉ một phần thao tác được rollback | Một thao tác dùng ConnectionFactory khác | Dùng cùng factory/manager hoặc thiết kế transaction riêng |
| Error bị nuốt nhưng dữ liệu vẫn commit | `onErrorResume` chuyển lỗi thành completion thành công | Để lỗi đi qua boundary hoặc đánh dấu rollback-only |
| Transaction giữ connection quá lâu | Publisher chờ I/O bên ngoài hoặc streaming dài | Thu hẹp transaction boundary |
| Lỗi dùng connection đồng thời | Nhiều query chạy song song trên cùng transactional connection | Tuần tự hóa hoặc xác nhận driver hỗ trợ |
| Checked exception không rollback | Default rollback rules không bao gồm checked exception | Khai báo `rollbackFor` phù hợp |
| readOnly không ngăn ghi | readOnly chỉ là hint hoặc database không enforce | Dùng quyền DB và authorization; không dựa vào hint |
| Transaction dùng nhầm database | Nhiều manager/factory và method chọn sai manager | Chỉ định `transactionManager` và qualifier rõ ràng |
| Timeout không dừng query như mong đợi | Nhầm transaction timeout với statement/HTTP timeout | Cấu hình timeout phù hợp ở từng tầng |

## 23. Quy trình thiết kế transaction boundary

Khi thêm `@Transactional` vào một service method reactive, hãy xác định:

1. Method có trả về Publisher được Spring hỗ trợ không?
2. Có ReactiveTransactionManager phù hợp không?
3. Manager có quản lý đúng ConnectionFactory mà repository/template/client sử dụng không?
4. Toàn bộ thao tác database cần atomic có nằm trong publisher được trả về không?
5. Có publisher nào bị bỏ qua, subscribe riêng hoặc block không?
6. Lỗi nào phải rollback và lỗi nào được phép commit?
7. Có onErrorResume hoặc operator nào đang nuốt lỗi trước transaction boundary không?
8. Method có được gọi qua Spring proxy hay chỉ self-invocation?
9. Có nhiều transaction manager hoặc database không?
10. Có thao tác HTTP, message, email hoặc công việc dài nằm trong transaction không?
11. Có query chạy đồng thời trên cùng connection không?
12. Đã kiểm thử commit, rollback, cancellation và retry với database/driver thực tế chưa?

Một transaction boundary tốt thường nằm ở service method đại diện cho một đơn vị nghiệp vụ cần atomic. Repository method đơn lẻ không nhất thiết phải tự tạo transaction riêng nếu nó được gọi bên trong một transaction lớn hơn.

## 24. Kết luận

Với Spring Data R2DBC, có thể khai báo `@Transactional` trên service method trả về `Mono`, `Flux` hoặc Publisher reactive được hỗ trợ. Spring sử dụng ReactiveTransactionManager, thường là R2dbcTransactionManager, để mở transaction khi publisher được subscribe và commit/rollback khi publisher hoàn tất, phát lỗi hoặc bị hủy theo lifecycle reactive.

Toàn bộ thao tác cần atomic phải được nối vào publisher mà method trả về và dùng cùng ConnectionFactory/transaction manager. Không gọi `subscribe()`, `block()` hoặc bỏ publisher bên trong method; tránh self-invocation làm bypass proxy; xác định rollback rules và không nuốt lỗi trước transaction boundary. Với nhiều database, mỗi transaction manager chỉ quản lý ConnectionFactory của nó.

Annotation giúp đặt ranh giới transaction rõ ở cấp service. Khi cần bọc một đoạn pipeline linh hoạt hơn, có thể dùng TransactionalOperator. Dù dùng cách nào, hãy kiểm thử commit, rollback và cancellation trên database/driver thực tế để xác nhận các thao tác reactive thật sự tham gia cùng một transaction.

