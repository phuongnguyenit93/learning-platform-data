# Chọn đúng transaction manager cho từng nguồn dữ liệu

Trong ứng dụng Spring có nhiều nguồn dữ liệu, mỗi nguồn thường có một ConnectionFactory hoặc DataSource riêng. Transaction manager phải quản lý đúng tài nguyên mà thao tác đang sử dụng. Với Spring Data R2DBC, transaction manager thường là **R2dbcTransactionManager**, triển khai **ReactiveTransactionManager** và gắn với một ConnectionFactory cụ thể.

Nếu ứng dụng có nhiều database R2DBC, mỗi database cần cấu hình rõ ConnectionFactory, template/repository và transaction manager tương ứng. Khi dùng @Transactional, hãy chỉ định đúng bean transaction manager cho phương thức. Một transaction manager R2DBC chỉ quản lý transaction trên ConnectionFactory mà nó được cấu hình; nó không tự bao trùm các database khác hoặc một dịch vụ HTTP.

## 1. Transaction manager có vai trò gì?

Transaction manager bắt đầu, commit hoặc rollback một transaction. Nó cung cấp ranh giới để nhiều thao tác dữ liệu được thực hiện như một đơn vị công việc.

Spring có hai abstraction chính:

- **PlatformTransactionManager**: quản lý transaction theo mô hình imperative, thường dùng với JDBC, JPA hoặc các tài nguyên đồng bộ.
- **ReactiveTransactionManager**: quản lý transaction theo mô hình reactive, tích hợp với Reactor Context và Publisher như Mono/Flux.

Trong Spring Data R2DBC, implementation thường dùng là R2dbcTransactionManager. Nó quản lý một R2DBC ConnectionFactory và bind connection tham gia transaction vào reactive context để các thao tác R2DBC tương ứng sử dụng cùng transaction.

| Nguồn dữ liệu | Transaction manager thường dùng | Abstraction |
|---|---|---|
| R2DBC | R2dbcTransactionManager | ReactiveTransactionManager |
| JDBC | DataSourceTransactionManager | PlatformTransactionManager |
| JPA | JpaTransactionManager | PlatformTransactionManager |
| Nhiều tài nguyên XA được hỗ trợ | JTA transaction manager | JTA integration |

Không nên dùng DataSourceTransactionManager để quản lý thao tác R2DBC chỉ vì cả hai cùng truy cập một database. JDBC Connection và R2DBC Connection thuộc hai API và vòng đời tài nguyên khác nhau. Tương tự, R2dbcTransactionManager không tự quản lý JDBC Connection của DataSource.

### 1.1. Một transaction manager gắn với tài nguyên cụ thể

R2dbcTransactionManager được tạo từ một ConnectionFactory. ConnectionFactory đó xác định pool, driver và database mà transaction manager quản lý.

~~~java
@Bean("ordersTransactionManager")
ReactiveTransactionManager ordersTransactionManager(
        @Qualifier("ordersConnectionFactory")
        ConnectionFactory connectionFactory) {

    return new R2dbcTransactionManager(connectionFactory);
}
~~~

Nếu transaction manager được tạo từ ordersConnectionFactory, nó quản lý các thao tác tham gia transaction trên factory đó. Nó không tự quản lý một billingConnectionFactory khác.

## 2. Một nguồn dữ liệu R2DBC

Với một database, Spring Boot thường tự cấu hình ConnectionFactory từ spring.r2dbc.* và tạo các thành phần Spring Data cần thiết. Transaction manager có thể được khai báo tường minh:

~~~java
import io.r2dbc.spi.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.r2dbc.connection.R2dbcTransactionManager;
import org.springframework.transaction.ReactiveTransactionManager;

@Configuration
public class OrdersTransactionConfiguration {

    @Bean
    ReactiveTransactionManager transactionManager(
            ConnectionFactory connectionFactory) {
        return new R2dbcTransactionManager(connectionFactory);
    }
}
~~~

Khi chỉ có một transaction manager phù hợp, Spring có thể sử dụng bean đó cho các phương thức @Transactional. Đặt tên bean có ý nghĩa vẫn hữu ích để sau này mở rộng nhiều nguồn dữ liệu.

Service reactive:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final AuditRepository auditRepository;

    public OrderService(
            OrderRepository orderRepository,
            AuditRepository auditRepository) {
        this.orderRepository = orderRepository;
        this.auditRepository = auditRepository;
    }

    @Transactional
    public Mono<Order> create(Order order) {
        return orderRepository.save(order)
            .flatMap(saved ->
                auditRepository.recordCreated(saved.id())
                    .thenReturn(saved)
            );
    }
}
~~~

Nếu hai repository dùng cùng ConnectionFactory và transaction manager, các thao tác trong reactive chain có thể tham gia cùng transaction. Nếu auditRepository sử dụng nguồn dữ liệu khác, annotation không tự làm transaction trở thành transaction đa database.

## 3. Khi ứng dụng có nhiều R2DBC database

Giả sử ứng dụng có hai nguồn dữ liệu độc lập:

- Orders database lưu đơn hàng.
- Billing database lưu hóa đơn.

Mỗi nguồn cần ConnectionFactory, template/repository và transaction manager riêng:

~~~text
OrdersRepository
    -> Orders R2dbcEntityTemplate
    -> ordersConnectionFactory
    -> ordersTransactionManager

BillingRepository
    -> Billing R2dbcEntityTemplate
    -> billingConnectionFactory
    -> billingTransactionManager
~~~

### 3.1. Đặt tên bean rõ ràng

Ví dụ cấu hình hai ConnectionFactory:

~~~java
import io.r2dbc.spi.ConnectionFactory;
import io.r2dbc.spi.ConnectionFactories;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MultiDatabaseConfiguration {

    @Bean("ordersConnectionFactory")
    ConnectionFactory ordersConnectionFactory() {
        return ConnectionFactories.get(
            "r2dbc:postgresql://localhost:5432/orders"
        );
    }

    @Bean("billingConnectionFactory")
    ConnectionFactory billingConnectionFactory() {
        return ConnectionFactories.get(
            "r2dbc:postgresql://localhost:5432/billing"
        );
    }
}
~~~

Đây là ví dụ minh họa. Trong môi trường thực tế, credentials nên lấy từ biến môi trường hoặc secret manager; không hard-code mật khẩu trong source code. Có thể dùng ConnectionFactoryOptions hoặc builder riêng nếu cần TLS, pool và các option theo driver.

Khi có nhiều bean cùng kiểu ConnectionFactory, hãy inject bằng @Qualifier:

~~~java
public BillingAdapter(
        @Qualifier("billingConnectionFactory")
        ConnectionFactory connectionFactory) {
    this.connectionFactory = connectionFactory;
}
~~~

Nếu inject chỉ bằng kiểu mà không có @Qualifier hoặc bean @Primary, Spring có thể không xác định được bean phù hợp và báo NoUniqueBeanDefinitionException.

### 3.2. Tạo transaction manager cho từng ConnectionFactory

~~~java
@Configuration
public class MultiTransactionConfiguration {

    @Bean("ordersTransactionManager")
    ReactiveTransactionManager ordersTransactionManager(
            @Qualifier("ordersConnectionFactory")
            ConnectionFactory connectionFactory) {
        return new R2dbcTransactionManager(connectionFactory);
    }

    @Bean("billingTransactionManager")
    ReactiveTransactionManager billingTransactionManager(
            @Qualifier("billingConnectionFactory")
            ConnectionFactory connectionFactory) {
        return new R2dbcTransactionManager(connectionFactory);
    }
}
~~~

Tên bean phản ánh rõ transaction manager quản lý database nào. Khi một phương thức cần transaction trên Orders, chỉ định ordersTransactionManager. Khi một phương thức cần transaction trên Billing, chỉ định billingTransactionManager.

### 3.3. Cấu hình template và repository cho đúng nguồn

Mỗi R2dbcEntityTemplate phải dùng ConnectionFactory của database tương ứng:

~~~java
@Configuration
public class EntityTemplateConfiguration {

    @Bean("ordersR2dbcEntityTemplate")
    R2dbcEntityTemplate ordersTemplate(
            @Qualifier("ordersConnectionFactory")
            ConnectionFactory connectionFactory) {
        return new R2dbcEntityTemplate(connectionFactory);
    }

    @Bean("billingR2dbcEntityTemplate")
    R2dbcEntityTemplate billingTemplate(
            @Qualifier("billingConnectionFactory")
            ConnectionFactory connectionFactory) {
        return new R2dbcEntityTemplate(connectionFactory);
    }
}
~~~

Với nhiều repository package, chỉ định entityOperationsRef để mỗi nhóm repository dùng template riêng:

~~~java
@Configuration
@EnableR2dbcRepositories(
    basePackages = "com.example.orders.repository",
    entityOperationsRef = "ordersR2dbcEntityTemplate"
)
class OrdersRepositoriesConfiguration {
}
~~~

~~~java
@Configuration
@EnableR2dbcRepositories(
    basePackages = "com.example.billing.repository",
    entityOperationsRef = "billingR2dbcEntityTemplate"
)
class BillingRepositoriesConfiguration {
}
~~~

Các package và tên bean trong ví dụ cần thay theo cấu trúc dự án. Không để hai cấu hình repository cùng scan một package nếu chúng được dự định gắn với hai template khác nhau.

Spring Boot auto-configuration cho R2DBC thường hướng tới một ConnectionFactory mặc định. Khi ứng dụng khai báo nhiều factory, cần cấu hình rõ các bean và repository tương ứng; hành vi auto-configuration cụ thể phụ thuộc phiên bản Spring Boot.

## 4. Chọn transaction manager bằng @Transactional

Khi có nhiều transaction manager, đừng để phương thức phụ thuộc vào lựa chọn mặc định nếu nó phải truy cập một database cụ thể. Dùng thuộc tính transactionManager của @Transactional để chỉ rõ bean.

Phương thức ghi Orders:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional(transactionManager = "ordersTransactionManager")
    public Mono<Order> create(Order order) {
        return orderRepository.save(order);
    }
}
~~~

Phương thức ghi Billing:

~~~java
@Service
public class BillingService {

    private final InvoiceRepository invoiceRepository;

    public BillingService(InvoiceRepository invoiceRepository) {
        this.invoiceRepository = invoiceRepository;
    }

    @Transactional(transactionManager = "billingTransactionManager")
    public Mono<Invoice> createInvoice(Invoice invoice) {
        return invoiceRepository.save(invoice);
    }
}
~~~

Các cách viết phổ biến:

~~~java
@Transactional("ordersTransactionManager")
public Mono<Order> create(Order order) {
    return orderRepository.save(order);
}
~~~

hoặc:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<Order> create(Order order) {
    return orderRepository.save(order);
}
~~~

Thuộc tính value là alias của transactionManager trong annotation. Dùng tên bean hoặc qualifier đã cấu hình để Spring tìm đúng manager.

### 4.1. @Primary và transaction manager mặc định

Có thể đánh dấu một transaction manager là @Primary để Spring chọn nó khi không có qualifier rõ ràng:

~~~java
@Bean("ordersTransactionManager")
@Primary
ReactiveTransactionManager ordersTransactionManager(
        @Qualifier("ordersConnectionFactory")
        ConnectionFactory connectionFactory) {
    return new R2dbcTransactionManager(connectionFactory);
}
~~~

@Primary hữu ích khi một database là nguồn mặc định của phần lớn ứng dụng. Tuy nhiên, nó không thay thế việc chỉ định manager tường minh cho các phương thức dùng database khác.

Nếu có nhiều manager và không có bean mặc định phù hợp, một @Transactional không chỉ rõ manager có thể gây lỗi phân giải bean. Không dựa vào thứ tự khai báo bean để lựa chọn transaction manager.

## 5. Reactive transaction và imperative transaction

Một điểm dễ nhầm là @Transactional có thể áp dụng cho cả phương thức imperative và reactive, nhưng cơ chế quản lý transaction khác nhau.

### 5.1. ReactiveTransactionManager cho Mono/Flux

Với Spring Data R2DBC, phương thức nên trả về Publisher như Mono hoặc Flux:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<Order> placeOrder(Order order) {
    return orderRepository.save(order);
}
~~~

Reactive transaction sử dụng Reactor Context để truyền transaction resource qua chuỗi publisher. Không dựa vào ThreadLocal như cách quản lý transaction imperative truyền thống.

Cần giữ các thao tác trong cùng reactive chain:

~~~java
return orderRepository.save(order)
    .flatMap(saved ->
        orderLineRepository.saveAll(saved.lines())
            .thenReturn(saved)
    );
~~~

Không gọi subscribe() bên trong phương thức transactional để khởi chạy publisher tách rời. Không gọi block() để lấy kết quả đồng bộ giữa chừng. Hai hành động này có thể làm thao tác chạy ngoài transaction context hoặc khiến transaction kết thúc trước khi công việc thực tế hoàn thành.

### 5.2. PlatformTransactionManager cho JDBC/JPA

Với JDBC hoặc JPA, phương thức thường thực hiện lời gọi đồng bộ và transaction được quản lý qua PlatformTransactionManager:

~~~java
@Transactional(transactionManager = "jdbcTransactionManager")
public void updateLegacyRecord(LegacyRecord record) {
    jdbcRepository.save(record);
}
~~~

Không dùng ReactiveTransactionManager để thay thế transaction manager của JDBC chỉ vì service có một số phương thức trả Mono. Mỗi resource cần manager tương ứng.

### 5.3. Không trộn hai mô hình và kỳ vọng cùng transaction

Ví dụ sau không tự động tạo một transaction nguyên tử chung cho cả hai database API:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<Result> updateBoth(Order order, LegacyRecord record) {
    return orderRepository.save(order)
        .map(saved -> {
            jdbcRepository.save(record);
            return toResult(saved);
        });
}
~~~

JDBC call là blocking và dùng resource khác. Nó không tự tham gia reactive transaction của ordersTransactionManager. Ngoài ra, thực hiện blocking JDBC call trong reactive pipeline có thể chặn event-loop thread.

Nếu buộc phải tích hợp JDBC cũ, cần tách rõ transaction boundary, thực thi blocking trên scheduler phù hợp và thiết kế tính nhất quán giữa hai nguồn dữ liệu. Không coi một annotation @Transactional đơn lẻ là giải pháp cho distributed transaction.

## 6. Dùng TransactionalOperator cho từng nguồn dữ liệu

Ngoài @Transactional, Spring cung cấp TransactionalOperator để điều khiển reactive transaction bằng chương trình.

Mỗi operator phải được tạo từ transaction manager tương ứng:

~~~java
@Configuration
public class TransactionOperatorConfiguration {

    @Bean("ordersTransactionalOperator")
    TransactionalOperator ordersOperator(
            @Qualifier("ordersTransactionManager")
            ReactiveTransactionManager transactionManager) {
        return TransactionalOperator.create(transactionManager);
    }

    @Bean("billingTransactionalOperator")
    TransactionalOperator billingOperator(
            @Qualifier("billingTransactionManager")
            ReactiveTransactionManager transactionManager) {
        return TransactionalOperator.create(transactionManager);
    }
}
~~~

Dùng operator cho Orders:

~~~java
public Mono<Order> create(Order order) {
    Mono<Order> work = orderRepository.save(order);
    return ordersTransactionalOperator.transactional(work);
}
~~~

Dùng operator cho Billing:

~~~java
public Mono<Invoice> createInvoice(Invoice invoice) {
    Mono<Invoice> work = billingRepository.save(invoice);
    return billingTransactionalOperator.transactional(work);
}
~~~

TransactionalOperator hữu ích khi transaction boundary cần được bao quanh một publisher cụ thể hoặc khi muốn điều khiển transaction theo nhánh xử lý. Tuy nhiên, nó vẫn chỉ quản lý tài nguyên thuộc transaction manager đã truyền vào.

## 7. Một phương thức gọi hai database có tạo transaction chung không?

Giả sử một nghiệp vụ tạo Order trong Orders database rồi tạo Invoice trong Billing database:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<Order> placeOrder(Order order) {
    return orderRepository.save(order)
        .flatMap(saved ->
            invoiceRepository.createFor(saved)
                .thenReturn(saved)
        );
}
~~~

Nếu invoiceRepository dùng billingConnectionFactory, transaction manager của Orders không quản lý transaction Billing. Lệnh Billing có thể chạy và commit độc lập. Nếu Billing thành công nhưng một thao tác Orders sau đó rollback, hai database có thể ở trạng thái không đồng bộ.

Một transaction manager R2DBC gắn với một ConnectionFactory không tự động bao trùm một ConnectionFactory khác. Việc hai database nằm trên cùng một máy chủ hoặc cùng một loại hệ quản trị cũng không tự làm hai connection/pool thành một transaction.

### 7.1. Khi nào có thể dùng cùng transaction?

Nếu nhiều bảng/schema được truy cập qua cùng một ConnectionFactory và cùng một transaction context, các thao tác có thể tham gia cùng transaction database đó. Ví dụ, hai schema trong cùng database session có thể được truy cập trong một transaction nếu database hỗ trợ và quyền cho phép.

Nhưng nếu mỗi schema được cấu hình bằng ConnectionFactory/pool riêng, chúng là các resource connection độc lập. Không nên giả định chúng dùng cùng transaction chỉ vì cùng host.

### 7.2. Distributed transaction không tự xuất hiện

Để một transaction nguyên tử bao trùm nhiều resource độc lập, cần một cơ chế distributed transaction thực sự, chẳng hạn XA/JTA với các resource và driver tương thích. Khả năng hỗ trợ phụ thuộc nền tảng và driver; không nên mặc định rằng mọi R2DBC driver đều hỗ trợ XA hoặc có thể được ghép vào một JTA transaction manager.

Trong kiến trúc reactive nhiều service, cách phổ biến hơn thường là transaction local kết hợp Outbox, Saga và compensation thay vì cố gắng dùng một transaction xuyên nhiều hệ thống.

## 8. Dùng Outbox khi cần phát sự kiện sang nguồn khác

Nếu Orders database cần thông báo cho Billing hoặc Inventory, có thể ghi sự kiện outbox cùng transaction với Order:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<Order> create(Order order) {
    return orderRepository.save(order)
        .flatMap(saved -> {
            OutboxMessage event =
                OutboxMessage.orderCreated(saved.id());

            return outboxRepository.save(event)
                .thenReturn(saved);
        });
}
~~~

Order và outbox row cùng commit hoặc rollback trong Orders database. Một relay đọc outbox sau commit rồi publish message. Consumer ở Billing xử lý message trong transaction local của Billing database.

Outbox tránh việc gửi message trước khi dữ liệu nguồn commit. Tuy nhiên, relay có thể gửi trùng nếu crash sau broker acknowledgment nhưng trước khi đánh dấu event đã publish. Consumer cần idempotency hoặc inbox để tránh áp dụng nghiệp vụ nhiều lần.

## 9. Dùng Saga và compensation cho nhiều transaction local

Một quy trình phân tán có thể gồm:

1. Orders database tạo Order.
2. Inventory database giữ hàng.
3. Billing database thu tiền.
4. Shipping database tạo vận đơn.

Mỗi bước có transaction manager riêng và commit độc lập. Nếu bước Billing thất bại sau khi Inventory đã giữ hàng, ứng dụng cần một thao tác bù trừ để release reservation.

~~~mermaid
flowchart TD
    A["Orders transaction: tạo Order"]
    B["Inventory transaction: reserve"]
    C["Billing transaction: charge"]
    D["Shipping transaction: tạo shipment"]
    E["Hoàn tất"]
    X["Một bước thất bại"]
    R1["Compensation: release inventory"]
    R2["Compensation: refund nếu đã charge"]
    F["Cập nhật trạng thái Order"]

    A --> B --> C --> D --> E
    B --> X
    C --> X
    D --> X
    X --> R1 --> R2 --> F
~~~

Saga không rollback transaction đã commit ở database khác. Nó thực hiện các hành động nghiệp vụ mới để bù lại tác động trước đó. Mỗi bước và compensation cần idempotent, có trạng thái lưu bền vững và có thể tiếp tục sau khi service restart.

## 10. Chọn manager khi có JDBC và R2DBC cùng lúc

Một ứng dụng có thể đang chuyển dần từ JDBC/JPA sang R2DBC. Khi đó có cả hai loại resource:

~~~text
JDBC repository
    -> DataSource
    -> jdbcTransactionManager (PlatformTransactionManager)

R2DBC repository
    -> ConnectionFactory
    -> r2dbcTransactionManager (ReactiveTransactionManager)
~~~

Cấu hình bean có tên riêng:

~~~java
@Bean("jdbcTransactionManager")
PlatformTransactionManager jdbcTransactionManager(
        DataSource dataSource) {
    return new DataSourceTransactionManager(dataSource);
}

@Bean("r2dbcTransactionManager")
ReactiveTransactionManager r2dbcTransactionManager(
        ConnectionFactory connectionFactory) {
    return new R2dbcTransactionManager(connectionFactory);
}
~~~

Service JDBC dùng:

~~~java
@Transactional(transactionManager = "jdbcTransactionManager")
public void updateLegacyData() {
    jdbcRepository.updateSomething();
}
~~~

Service R2DBC dùng:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Void> updateReactiveData() {
    return reactiveRepository.updateSomething();
}
~~~

Không đặt cả hai thao tác vào một phương thức và kỳ vọng chúng cùng rollback chỉ vì có một @Transactional. Nếu cần phối hợp, hãy thiết kế transaction local riêng và cơ chế nhất quán ở tầng nghiệp vụ.

## 11. Lựa chọn manager mặc định và tránh lỗi bean ambiguity

Khi có nhiều bean cùng implement ReactiveTransactionManager, Spring cần biết bean nào được dùng.

Các cách phổ biến:

- Chỉ định tên manager trong @Transactional.
- Inject bằng @Qualifier khi tạo TransactionalOperator.
- Đánh dấu một manager @Primary nếu nó thực sự là mặc định.
- Dùng cấu hình transaction riêng cho từng module/repository package.

Nếu quên qualifier và có nhiều manager, ứng dụng có thể lỗi khi khởi tạo hoặc chọn manager không như mong muốn tùy cấu hình. Không dựa vào tên class hay thứ tự khai báo bean để suy đoán.

@Primary chỉ giải quyết lựa chọn mặc định khi có nhiều candidate. Nó không biến manager mặc định thành manager bao trùm các nguồn khác.

## 12. Ranh giới transaction và propagation

Các transaction manager có thể hỗ trợ propagation như REQUIRED, REQUIRES_NEW và các thuộc tính transaction khác theo implementation.

Với R2dbcTransactionManager, propagation được áp dụng trong phạm vi transaction resource mà manager đó quản lý. Ví dụ, REQUIRES_NEW trên ordersTransactionManager tạo transaction mới cho Orders resource; nó không tự tạo transaction cho Billing database.

Khi gọi một phương thức transactional khác, cần nhớ:

- Cùng manager và REQUIRED: thường tham gia transaction hiện có nếu cùng reactive context.
- Cùng manager và REQUIRES_NEW: yêu cầu transaction mới theo semantics manager.
- Manager khác: đó là resource transaction khác; không tự động join transaction hiện tại.
- Self-invocation trong cùng object có thể bỏ qua proxy transaction trong cấu hình proxy-based thông thường.

Nếu cần transaction độc lập, đặt phương thức ở bean khác hoặc dùng TransactionalOperator rõ ràng. Đừng dùng propagation như một cách thay thế distributed transaction.

## 13. Kiểm thử transaction manager

Với nhiều database, test cần chứng minh repository đang dùng đúng ConnectionFactory và manager.

Các trường hợp nên kiểm thử:

- Phương thức @Transactional của Orders rollback khi thao tác thứ hai trên Orders thất bại.
- Phương thức Billing dùng billingTransactionManager và không ghi nhầm vào Orders.
- Một manager không vô tình bao trùm repository thuộc ConnectionFactory khác.
- TransactionalOperator được tạo từ đúng manager.
- Reactive chain giữ transaction context khi dùng flatMap/then.
- Lỗi trong publisher dẫn tới rollback khi lỗi đi qua transaction boundary.
- Cancellation trước commit được xử lý theo quy tắc reactive transaction của phiên bản Spring.
- JDBC transaction và R2DBC transaction được kiểm thử riêng nếu ứng dụng dùng cả hai.
- Outbox event được commit/rollback cùng business data trong database nguồn.
- Các quy trình nhiều database có compensation khi một bước local thất bại.

Nên dùng integration test với database/driver tương ứng production. Database nhúng có thể không phản ánh chính xác hành vi transaction, lock, isolation hoặc kiểu dữ liệu của hệ quản trị thật.

## 14. Những lỗi thường gặp

**Dùng nhầm transaction manager.** Một phương thức thao tác Billing nhưng lại chỉ định ordersTransactionManager. Billing repository không tham gia transaction được chọn. Đối chiếu repository, template, ConnectionFactory và manager theo từng nguồn; dùng tên manager rõ ràng.

**Thiếu @Qualifier khi có nhiều ConnectionFactory.** Spring không thể chọn một bean duy nhất. Inject bằng @Qualifier hoặc đánh dấu @Primary cho nguồn mặc định nếu phù hợp.

**Nghĩ một @Transactional bao trùm mọi database.** Transaction manager R2DBC quản lý một ConnectionFactory. Hai database độc lập cần hai transaction local hoặc distributed transaction infrastructure thực sự.

**Trộn JDBC blocking trong reactive transaction.** JDBC call không tự tham gia reactive transaction và có thể chặn event-loop. Tách mô hình transaction, chạy blocking trên scheduler phù hợp nếu cần, và thiết kế nhất quán liên nguồn rõ ràng.

**Gọi subscribe() hoặc block() trong phương thức transactional.** Publisher có thể chạy tách khỏi transaction context hoặc kết thúc transaction trước khi thao tác hoàn tất. Hãy trả Mono/Flux và nối publisher bằng flatMap, then hoặc toán tử phù hợp.

**Dùng một TransactionalOperator cho mọi nguồn.** Operator giữ manager đã truyền vào lúc tạo. Dùng operator của Orders cho công việc Billing sẽ chọn sai resource. Tạo operator riêng cho từng manager và inject bằng qualifier.

**Cho rằng cùng host là cùng transaction.** Hai ConnectionFactory hoặc hai pool có thể tạo hai connection riêng biệt dù cùng host. Kiểm tra chính xác transaction resource.

## 15. Nguyên tắc thiết kế

- Mỗi ConnectionFactory cần có transaction manager tương ứng khi ứng dụng cần transaction trên nguồn đó.
- Đặt tên bean theo nguồn dữ liệu: ordersConnectionFactory, ordersTransactionManager, billingConnectionFactory, billingTransactionManager.
- Gắn repository và R2dbcEntityTemplate với đúng ConnectionFactory.
- Dùng @Transactional(transactionManager = "...") cho phương thức có nguồn dữ liệu cụ thể.
- Dùng @Qualifier khi inject manager, factory, template hoặc TransactionalOperator.
- Chỉ đánh dấu @Primary cho manager mặc định thực sự.
- Dùng ReactiveTransactionManager cho R2DBC Mono/Flux; dùng PlatformTransactionManager cho JDBC/JPA imperative.
- Giữ reactive transaction trong cùng Publisher chain và không tự subscribe/block.
- Không giả định một manager bao trùm nhiều ConnectionFactory.
- Dùng Outbox/Saga/compensation khi cần phối hợp nhiều transaction local.
- Kiểm tra auto-configuration của Spring Boot khi khai báo nhiều nguồn dữ liệu.
- Kiểm thử rollback, manager selection và ranh giới tài nguyên trên database mục tiêu.

## 16. Ghi nhớ

Chọn transaction manager theo đúng loại tài nguyên và ConnectionFactory mà repository đang dùng. R2dbcTransactionManager quản lý một ConnectionFactory theo mô hình reactive; JDBC/JPA thường dùng PlatformTransactionManager riêng. Khi có nhiều database R2DBC, cấu hình mỗi factory, template/repository và transaction manager thành một nhóm có tên rõ ràng, sau đó chỉ định manager qua @Transactional hoặc tạo TransactionalOperator tương ứng.

Một phương thức @Transactional chỉ tạo transaction cho resource do manager được chọn quản lý. Nó không tự tạo transaction nguyên tử xuyên nhiều database, JDBC và HTTP. Khi nghiệp vụ cần phối hợp nhiều nguồn độc lập, hãy dùng transaction local cho từng nguồn và Outbox/Saga/compensation để xử lý việc truyền trạng thái và khôi phục nghiệp vụ sau lỗi.

