# Đối tượng miền Java thuần và cách lắp ghép bằng Spring

Trong Domain-Driven Design (DDD), mô hình miền diễn đạt ngôn ngữ, hành vi và quy tắc nghiệp vụ. Với Java, các Entity, Value Object và Domain Service có thể được viết bằng Java thuần, không cần phụ thuộc vào Spring hoặc ORM. Spring vẫn đóng vai trò quan trọng: nó tạo và kết nối các thành phần ở tầng ứng dụng, cung cấp repository adapter, quản lý transaction và tích hợp hạ tầng.

Điểm cần phân biệt là **đối tượng miền biểu diễn nghiệp vụ**, còn **Spring container quản lý các thành phần của ứng dụng và vòng đời phụ thuộc**. Một Aggregate như Order thường được tạo theo từng giao dịch nghiệp vụ, trong khi một application service như ConfirmOrderHandler có thể là Spring bean dùng chung. Đặt đúng ranh giới giúp domain model giữ hành vi nghiệp vụ mà vẫn tận dụng được dependency injection và transaction của Spring.

## 1. Vai trò của Java thuần và Spring trong kiến trúc DDD

Một ứng dụng DDD thường có các nhóm thành phần:

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| Domain Model | Khái niệm, hành vi và bất biến nghiệp vụ | Order, OrderLine, Money |
| Domain Service | Quy tắc nghiệp vụ không thuộc tự nhiên về một Entity/Value Object | OrderPricingService |
| Repository Port | Hợp đồng nạp/lưu Aggregate | OrderRepository |
| Application Service | Điều phối một use case và transaction | ConfirmOrderHandler |
| Infrastructure Adapter | Kết nối database, message broker hoặc API | JpaOrderRepository |
| Composition Root | Khởi tạo và kết nối implementation | Spring Configuration |

Domain model không cần biết Spring tạo bean bằng component scanning hay Java configuration. Nó cũng không cần biết dữ liệu được lưu bằng JPA, JDBC hay một event store. Application layer phối hợp các thành phần; infrastructure thực hiện các chi tiết kỹ thuật.

Một cách nhìn tổng quát:

~~~mermaid
flowchart TB
    Client["HTTP / Message / UI"] --> App["Application Service<br/>Spring Bean"]
    App --> Domain["Domain Model<br/>Java thuần"]
    App --> Port["Repository Port<br/>Domain Interface"]
    Port -. implemented by .-> Adapter["Persistence Adapter<br/>Spring / JPA"]
    Adapter --> DB[("Database")]
    Config["Spring Composition Root"] -. wires .-> App
    Config -. wires .-> Adapter
~~~

Mũi tên phụ thuộc quan trọng là application layer sử dụng domain model và các port. Infrastructure triển khai port; domain không phụ thuộc vào implementation của infrastructure.

## 2. Đối tượng miền Java thuần là gì?

Đối tượng miền Java thuần là class hoặc record tập trung biểu diễn khái niệm và hành vi nghiệp vụ. Nó có thể dùng các tính năng Java như:

- Constructor để tạo trạng thái hợp lệ.
- Encapsulation để kiểm soát thay đổi.
- final để giới hạn kế thừa hoặc bảo vệ tham chiếu.
- record cho Value Object bất biến khi phù hợp.
- Interface để mô tả hợp đồng miền.
- Exception hoặc kiểu kết quả để biểu diễn trường hợp nghiệp vụ.

Một đối tượng miền không cần kế thừa JpaRepository, JpaEntity, ApplicationContext hoặc một class nền của Spring. Nó không cần annotation @Component chỉ để có thể được sử dụng.

Ví dụ, một Money Value Object:

~~~java
public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount, "amount is required");
        Objects.requireNonNull(currency, "currency is required");
        int fractionDigits = currency.getDefaultFractionDigits();
        if (fractionDigits >= 0 && amount.scale() > fractionDigits) {
            throw new IllegalArgumentException("Unsupported monetary precision");
        }
    }

    public Money add(Money other) {
        requireSameCurrency(other);
        return new Money(amount.add(other.amount), currency);
    }

    public Money multiply(int quantity) {
        if (quantity < 0) {
            throw new IllegalArgumentException("quantity cannot be negative");
        }
        return new Money(amount.multiply(BigDecimal.valueOf(quantity)), currency);
    }

    private void requireSameCurrency(Money other) {
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException("Currency mismatch");
        }
    }
}
~~~

Money tự bảo vệ quy tắc của nó: phải có số tiền và đơn vị tiền tệ, không được cộng hai loại tiền khác nhau. Nó không cần Spring bean vì đây là giá trị được tạo và sử dụng như một phần của mô hình miền.

Ví dụ trên dùng quy tắc precision đơn giản để minh họa. Hệ thống thực tế cần xác định rõ cách làm tròn, độ chính xác theo loại tiền và các phép toán được phép theo nghiệp vụ.

## 3. Entity và Aggregate được tạo theo vòng đời nghiệp vụ

Entity có identity và vòng đời. Aggregate Root kiểm soát các thay đổi để bảo vệ bất biến bên trong Aggregate.

~~~java
public record OrderId(UUID value) {
    public OrderId {
        Objects.requireNonNull(value);
    }
}

public record CustomerId(UUID value) {
    public CustomerId {
        Objects.requireNonNull(value);
    }
}

public enum OrderStatus {
    DRAFT,
    CONFIRMED,
    CANCELLED
}
~~~

Order có thể được tạo bằng constructor riêng và factory:

~~~java
public final class Order {
    private final OrderId id;
    private final CustomerId customerId;
    private final List<OrderLine> lines = new ArrayList<>();
    private Money discount;
    private OrderStatus status;

    private Order(OrderId id, CustomerId customerId) {
        this.id = Objects.requireNonNull(id);
        this.customerId = Objects.requireNonNull(customerId);
        this.status = OrderStatus.DRAFT;
    }

    public static Order create(OrderId id, CustomerId customerId) {
        return new Order(id, customerId);
    }

    public void addLine(OrderLine line) {
        requireDraft();
        lines.add(Objects.requireNonNull(line));
    }

    public void confirm(Money discount) {
        requireDraft();
        if (lines.isEmpty()) {
            throw new OrderMustContainAtLeastOneLine();
        }
        this.discount = Objects.requireNonNull(discount);
        status = OrderStatus.CONFIRMED;
    }

    public void cancel() {
        if (status == OrderStatus.CANCELLED) {
            return;
        }
        if (status == OrderStatus.CONFIRMED) {
            throw new ConfirmedOrderRequiresCancellationPolicy();
        }
        status = OrderStatus.CANCELLED;
    }

    public OrderId id() {
        return id;
    }

    public CustomerId customerId() {
        return customerId;
    }

    public List<OrderLine> lines() {
        return List.copyOf(lines);
    }

    public OrderStatus status() {
        return status;
    }

    public Money discount() {
        return discount;
    }

    private void requireDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new OrderCannotBeChanged(status);
        }
    }
}
~~~

Order không có setter công khai cho status hoặc collection. Application service yêu cầu Aggregate thực hiện hành vi; Aggregate tự kiểm tra điều kiện. Đối tượng này thường được tạo khi xử lý một command và bị loại khỏi bộ nhớ sau khi use case kết thúc. Không cần đăng ký từng Order thành Spring singleton bean.

Các class OrderLine, OrderMustContainAtLeastOneLine, ConfirmedOrderRequiresCancellationPolicy và OrderCannotBeChanged là kiểu miền được định nghĩa riêng. Code rút gọn để tập trung vào ranh giới giữa domain object và Spring.

## 4. Tạo đối tượng miền bằng constructor hoặc factory

Đối tượng miền thường được tạo bởi:

- Constructor khi việc tạo đơn giản và các tham số đủ để bảo đảm trạng thái hợp lệ.
- Static factory khi tên nghiệp vụ làm rõ ý định, ví dụ Order.create() hoặc Money.of().
- Factory object khi việc tạo cần nhiều quy tắc, dữ liệu hoặc lựa chọn implementation.
- Reconstitution khi dựng lại Aggregate từ persistence hoặc event stream.

Ví dụ:

~~~java
public final class OrderFactory {
    private final OrderIdGenerator idGenerator;

    public OrderFactory(OrderIdGenerator idGenerator) {
        this.idGenerator = Objects.requireNonNull(idGenerator);
    }

    public Order createFor(CustomerId customerId) {
        return Order.create(idGenerator.nextId(), customerId);
    }
}
~~~

Factory trên là Java thuần. Nếu cần implementation tạo ID dựa trên UUID hoặc dịch vụ khác, Spring có thể lắp ghép implementation đó với factory. Domain object không cần gọi ApplicationContext.getBean() để tự tìm dependency.

Khi dựng lại Aggregate đã lưu, nên có một factory hoặc phương thức reconstitution riêng. Không nên mở setter công khai chỉ để ORM hoặc application service có thể gán tùy ý mọi trường.

## 5. Domain Service cũng có thể là Java thuần

Một quy tắc có ý nghĩa nghiệp vụ nhưng không thuộc tự nhiên về một Entity hoặc Value Object có thể được biểu diễn bằng Domain Service.

Ví dụ, cách tính giá đơn hàng có thể sử dụng chính sách giảm giá:

~~~java
public interface DiscountPolicy {
    Money discountFor(Order order);
}

public final class OrderPricingService {
    private final DiscountPolicy discountPolicy;

    public OrderPricingService(DiscountPolicy discountPolicy) {
        this.discountPolicy = Objects.requireNonNull(discountPolicy);
    }

    public Money calculateDiscount(Order order) {
        return discountPolicy.discountFor(order);
    }
}
~~~

OrderPricingService không cần annotation Spring. Nó là đối tượng Java nhận dependency qua constructor và thực hiện quy tắc. Có thể khởi tạo trực tiếp trong unit test hoặc đăng ký thành bean nếu application cần chia sẻ implementation.

Không nên biến mọi phép tính thành Domain Service. Nếu quy tắc tự nhiên thuộc Money, OrderLine hoặc Order, hãy đặt hành vi tại đối tượng đó. Domain Service phù hợp khi hành vi liên quan nhiều đối tượng hoặc diễn đạt một quy tắc miền độc lập.

## 6. Repository Port thuộc mô hình miền

Repository mô tả cách application/domain nạp và lưu Aggregate mà không phụ thuộc database cụ thể.

~~~java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}
~~~

Đây là interface Java thuần. Nó không mở rộng JpaRepository và không dùng annotation Spring Data. Domain/application layer chỉ biết hợp đồng làm việc với Order.

Implementation có thể sử dụng JPA, JDBC hoặc một kho dữ liệu khác. Việc chuyển đổi giữa domain object và persistence record thuộc adapter.

Đặt repository interface ở domain hay application tùy cách tổ chức module và dependency rule của dự án. Điều quan trọng là hợp đồng mà use case cần không bị buộc phải phụ thuộc vào chi tiết persistence.

## 7. Application Service là nơi Spring thường quản lý

Application Service điều phối một use case:

1. Nhận command.
2. Nạp Aggregate qua repository.
3. Gọi hành vi domain.
4. Lưu thay đổi.
5. Điều phối các port khác nếu cần.

Đây là một ứng viên phù hợp để Spring quản lý bằng @Service:

~~~java
@Service
public class ConfirmOrderHandler {
    private final OrderRepository orders;
    private final OrderPricingService pricing;

    public ConfirmOrderHandler(
        OrderRepository orders,
        OrderPricingService pricing
    ) {
        this.orders = Objects.requireNonNull(orders);
        this.pricing = Objects.requireNonNull(pricing);
    }

    @Transactional
    public void handle(ConfirmOrder command) {
        Order order = orders.findById(command.orderId())
            .orElseThrow(() -> new OrderNotFound(command.orderId()));

        Money discount = pricing.calculateDiscount(order);
        order.confirm(discount);
        orders.save(order);
    }
}
~~~

@Service cho biết đây là thành phần ứng dụng được Spring quản lý. @Transactional xác định transaction boundary cho use case. Order vẫn là Java thuần; Spring không cần tạo bean cho từng Order.

Ví dụ lược bỏ phần áp dụng discount vào tổng tiền để tập trung vào cấu trúc. Một ứng dụng thật cần đưa kết quả định giá vào mô hình Order theo đúng quy tắc, không bỏ qua kết quả hoặc tính toán hai lần.

Application service nên giữ trạng thái request trong biến cục bộ. Spring bean mặc định thường là singleton; không lưu currentOrder, currentUser hoặc dữ liệu của một request vào field mutable của handler.

## 8. Dependency Injection bằng constructor

Spring Dependency Injection (DI) cung cấp các dependency mà một bean cần. Constructor injection làm rõ các dependency bắt buộc và giúp đối tượng không thể được tạo ở trạng thái thiếu dependency.

~~~java
@Service
public class SubmitOrderHandler {
    private final OrderRepository orders;
    private final CustomerEligibilityQuery customerEligibility;
    private final Clock clock;

    public SubmitOrderHandler(
        OrderRepository orders,
        CustomerEligibilityQuery customerEligibility,
        Clock clock
    ) {
        this.orders = Objects.requireNonNull(orders);
        this.customerEligibility = Objects.requireNonNull(customerEligibility);
        this.clock = Objects.requireNonNull(clock);
    }
}
~~~

Lợi ích của constructor injection:

- Dependency bắt buộc được thể hiện ngay trên constructor.
- Field có thể là final.
- Unit test dễ truyền fake hoặc stub.
- Không cần reflection hoặc setter để hoàn thiện object sau khi tạo.
- Dependency graph dễ đọc và dễ phát hiện vòng phụ thuộc.

Field injection thường làm dependency bị ẩn và khiến class khó khởi tạo độc lập. Setter injection phù hợp hơn với dependency thực sự tùy chọn hoặc cấu hình thay đổi sau khi tạo, không nên là lựa chọn mặc định cho dependency cốt lõi.

## 9. Spring Composition Root lắp ghép implementation

Composition Root là nơi ứng dụng quyết định dùng implementation nào cho từng interface. Trong Spring, việc này có thể được thực hiện bằng component scanning hoặc Java configuration.

Ví dụ cấu hình tường minh:

~~~java
@Configuration
public class DomainConfiguration {
    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }

    @Bean
    DiscountPolicy discountPolicy() {
        return new StandardDiscountPolicy();
    }

    @Bean
    OrderPricingService orderPricingService(DiscountPolicy policy) {
        return new OrderPricingService(policy);
    }
}
~~~

Spring tạo DiscountPolicy, OrderPricingService và cung cấp chúng cho các bean cần sử dụng. OrderPricingService vẫn không phụ thuộc Spring; annotation chỉ xuất hiện tại cấu hình lắp ghép.

Có thể thay implementation bằng profile hoặc cấu hình theo môi trường, nhưng việc lựa chọn phải rõ ràng. Không nên để domain object tự kiểm tra environment variable hoặc tự tìm bean.

## 10. Component Scanning và Java Configuration

Spring hỗ trợ hai cách thường gặp:

| Cách | Ví dụ | Khi phù hợp |
| --- | --- | --- |
| Component scanning | @Service, @Repository, @Component | Thành phần ứng dụng hoặc adapter có vòng đời bean rõ |
| Java configuration | @Configuration, @Bean | Tạo bean từ class không gắn annotation, chọn implementation hoặc cấu hình rõ dependency |

Có thể dùng @Service cho application handler, @Repository cho persistence adapter và @Configuration để lắp ghép domain service. Không cần gắn annotation Spring vào mọi class trong domain package.

Một quy tắc thực dụng:

- Domain Entity/Value Object: tạo bằng constructor/factory.
- Application Service: thường là Spring bean.
- Infrastructure Adapter: thường là Spring bean.
- Domain Service: Java thuần; đăng ký bean khi cần dependency hoặc chia sẻ.
- Value Object: tạo theo giá trị, không quản lý bằng container.

## 11. Domain Object không phải Spring Singleton Bean

Spring singleton nghĩa là một bean instance được chia sẻ trong ApplicationContext. Entity/Value Object thường có identity hoặc giá trị thuộc về một giao dịch, một Aggregate hoặc một request cụ thể.

Nếu đăng ký một Order làm singleton bean, mọi request có thể vô tình chia sẻ cùng một trạng thái đơn hàng. Điều đó sai với vòng đời nghiệp vụ và gây race condition.

Không nên làm như sau:

~~~java
@Component
public class CurrentOrder {
    private Order order;
}
~~~

Class trên giữ dữ liệu nghiệp vụ mutable trong bean dùng chung. Một request có thể ghi đè order của request khác. Nếu cần lưu trạng thái phiên hoặc dữ liệu người dùng, hãy dùng cơ chế phù hợp với scope và persistence, không biến Aggregate thành singleton.

Ngược lại, application service stateless có thể là singleton:

~~~java
@Service
public class OrderQueryHandler {
    private final OrderRepository orders;

    public OrderQueryHandler(OrderRepository orders) {
        this.orders = orders;
    }
}
~~~

Handler chỉ giữ dependency bất biến và dữ liệu xử lý nằm trong biến cục bộ của method.

## 12. Persistence Adapter chuyển đổi Domain Model và ORM Model

Nếu domain object không mang annotation JPA, infrastructure adapter chịu trách nhiệm mapping.

Repository implementation:

~~~java
@Repository
public class JpaOrderRepository implements OrderRepository {
    private final SpringDataOrderRepository dataRepository;
    private final OrderMapper mapper;

    public JpaOrderRepository(
        SpringDataOrderRepository dataRepository,
        OrderMapper mapper
    ) {
        this.dataRepository = dataRepository;
        this.mapper = mapper;
    }

    @Override
    public Optional<Order> findById(OrderId id) {
        return dataRepository.findById(id.value())
            .map(mapper::toDomain);
    }

    @Override
    public void save(Order order) {
        OrderRecord record = mapper.toRecord(order);
        dataRepository.save(record);
    }
}
~~~

Spring Data repository và persistence record thuộc infrastructure:

~~~java
interface SpringDataOrderRepository
        extends JpaRepository<OrderRecord, UUID> {
}

@Entity
@Table(name = "orders")
class OrderRecord {
    @Id
    UUID id;

    @Column(nullable = false)
    String status;

    protected OrderRecord() {}
}
~~~

OrderRecord là mô hình lưu trữ. Nó có thể chứa annotation JPA và cấu trúc phù hợp database. Order vẫn giữ ngôn ngữ và hành vi nghiệp vụ. Mapper chịu trách nhiệm chuyển đổi hai dạng dữ liệu.

Ví dụ chỉ minh họa ranh giới; mapper thực tế phải xử lý đầy đủ OrderLine, Money, ID, version, dữ liệu cũ và các bất biến khi reconstitute Aggregate.

## 13. Transaction Boundary nên nằm ở Application Layer

Một use case thường là đơn vị điều phối transaction. Spring có thể quản lý transaction bằng @Transactional trên application service hoặc một phương thức điều phối chuyên trách.

~~~java
@Service
public class CancelOrderHandler {
    private final OrderRepository orders;

    public CancelOrderHandler(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public void handle(CancelOrder command) {
        Order order = orders.findById(command.orderId())
            .orElseThrow(() -> new OrderNotFound(command.orderId()));

        order.cancel();
        orders.save(order);
    }
}
~~~

Domain method cancel() kiểm tra quy tắc nghiệp vụ; application service xác định transaction và điều phối repository. Domain model không cần gọi TransactionManager hoặc mở transaction.

Lưu ý Spring thường áp dụng @Transactional thông qua proxy. Lời gọi self-invocation trong cùng bean có thể không đi qua proxy nên annotation không được áp dụng như mong đợi. Cần thiết kế transaction boundary tại method được gọi từ bên ngoài bean hoặc dùng cách quản lý transaction phù hợp.

Không nên đặt transaction trên mọi getter hoặc mọi phương thức domain. Transaction bao quanh use case và thao tác persistence, còn domain method tập trung vào quy tắc.

## 14. Không đưa Spring Repository vào Entity

Một Entity không nên tự gọi repository để nạp đối tượng khác:

~~~java
// Không nên: Entity phụ thuộc Spring Data hoặc Application Service.
public void confirm(CustomerRepository customers) {
    Customer customer = customers.findById(customerId).orElseThrow();
    // ...
}
~~~

Entity lúc này biết cách truy cập hạ tầng, khó kiểm thử độc lập và có thể tạo truy vấn ẩn trong hành vi miền.

Thay vào đó, application service nạp các dữ kiện cần thiết rồi gọi hành vi domain:

Ví dụ dưới đây giả định handler đã được tiêm các dependency `orders`, `pricing` và `customerEligibility` qua constructor.

~~~java
public void handle(ConfirmOrder command) {
    CustomerEligibility eligibility =
        customerEligibilityQuery.check(command.customerId());

    if (!eligibility.canPlaceOrder()) {
        throw new CustomerNotEligible();
    }

    Order order = orders.findById(command.orderId())
        .orElseThrow(() -> new OrderNotFound(command.orderId()));

    Money discount = pricing.calculateDiscount(order);
    order.confirm(discount);
    orders.save(order);
}
~~~

Nếu quy tắc cần dữ liệu của context khác, application service có thể dùng query port và chuyển kết quả thành dữ kiện miền. Với quy tắc cần bảo vệ nguyên tử trong cùng Aggregate, không nên dựa vào dữ liệu ngoài đã cũ mà bỏ qua thiết kế consistency.

## 15. Không dùng ApplicationContext như Service Locator

Một anti-pattern là lấy dependency động từ container bên trong domain object:

~~~java
public class Order {
    public void confirm() {
        DiscountPolicy policy =
            ApplicationContextProvider.getBean(DiscountPolicy.class);
        // ...
    }
}
~~~

Cách này che giấu dependency, khiến Order không thể được tạo và kiểm thử độc lập. Nó cũng đảo ngược trách nhiệm: domain object tự tìm dịch vụ thay vì application composition cung cấp những gì cần thiết.

Hãy truyền dependency qua constructor cho service hoặc để application service điều phối:

~~~java
OrderPricingService pricing = new OrderPricingService(discountPolicy);
Money discount = pricing.calculateDiscount(order);
~~~

Service Locator đôi khi xuất hiện trong framework hoặc legacy code, nhưng không nên là cơ chế mặc định để domain model lấy dependency.

## 16. Kiểm thử Domain Model không cần khởi động Spring

Một lợi ích lớn của Java thuần là unit test domain chạy nhanh và tập trung vào hành vi:

~~~java
class OrderTest {
    @Test
    void cannotConfirmAnEmptyOrder() {
        Order order = Order.create(
            new OrderId(UUID.randomUUID()),
            new CustomerId(UUID.randomUUID())
        );

        assertThrows(
            OrderMustContainAtLeastOneLine.class,
            () -> order.confirm(new Money(
                BigDecimal.ZERO,
                Currency.getInstance("VND")
            ))
        );
    }
}
~~~

Test không cần @SpringBootTest, database hoặc application context. Nó kiểm tra quy tắc: đơn không có dòng hàng không thể xác nhận.

Domain Service cũng có thể test bằng constructor injection:

~~~java
class OrderPricingServiceTest {
    @Test
    void delegatesDiscountCalculationToPolicy() {
        DiscountPolicy policy = order -> Money.zero(Currency.getInstance("VND"));
        OrderPricingService pricing = new OrderPricingService(policy);

        Money result = pricing.calculateDiscount(sampleOrder());

        assertEquals(Money.zero(Currency.getInstance("VND")), result);
    }
}
~~~

Money.zero() và sampleOrder() là helper giả định của test. Trong code thực tế, có thể dùng fake policy hoặc mock nếu điều đó làm rõ hành vi cần kiểm tra.

## 17. Kiểm thử Application Service và Spring Wiring

Application service có thể được kiểm thử ở nhiều mức:

- Unit test: tạo handler trực tiếp và truyền fake repository, fake clock hoặc stub port.
- Spring context test: xác nhận component scanning và bean wiring đúng.
- Integration test: xác nhận transaction, JPA mapping và repository adapter hoạt động với database kiểm thử.
- API test: xác nhận request/response và lỗi được ánh xạ đúng.

Không cần dùng @SpringBootTest cho mọi test. Chỉ khởi động Spring khi điều cần xác minh thực sự phụ thuộc container, proxy, transaction hoặc cấu hình.

Ví dụ unit test handler:

~~~java
class ConfirmOrderHandlerTest {
    @Test
    void confirmsAnExistingOrder() {
        InMemoryOrderRepository repository = new InMemoryOrderRepository();
        Order order = sampleDraftOrder();
        repository.save(order);

        OrderPricingService pricing =
            new OrderPricingService(order -> Money.zero(Currency.getInstance("VND")));
        ConfirmOrderHandler handler =
            new ConfirmOrderHandler(repository, pricing);

        handler.handle(new ConfirmOrder(order.id()));

        assertEquals(
            OrderStatus.CONFIRMED,
            repository.findById(order.id()).orElseThrow().status()
        );
    }
}
~~~

Test này giả định handler không phụ thuộc proxy để kiểm tra logic điều phối cơ bản; transaction behavior cần được xác minh bằng integration test với Spring và database.

## 18. Tổ chức package theo ranh giới kiến trúc

Một cấu trúc tham khảo:

~~~text
order/
├── domain/
│   ├── model/
│   │   ├── Order.java
│   │   ├── OrderLine.java
│   │   ├── OrderId.java
│   │   └── Money.java
│   ├── service/
│   │   └── OrderPricingService.java
│   └── port/
│       └── OrderRepository.java
├── application/
│   ├── ConfirmOrderHandler.java
│   └── command/
│       └── ConfirmOrder.java
└── infrastructure/
    ├── configuration/
    │   └── DomainConfiguration.java
    └── persistence/
        ├── JpaOrderRepository.java
        ├── SpringDataOrderRepository.java
        ├── OrderRecord.java
        └── OrderMapper.java
~~~

Package không phải công thức bắt buộc. Dự án nhỏ có thể tổ chức đơn giản hơn; dự án modular monolith có thể đặt mỗi bounded context trong một module riêng. Điều quan trọng là domain không import Spring/JPA và application không phụ thuộc trực tiếp vào implementation hạ tầng.

## 19. Ranh giới module và dependency direction

Một dependency direction thường phù hợp:

~~~mermaid
flowchart LR
    API["Inbound Adapter<br/>Controller / Consumer"] --> APP["Application"]
    APP --> DOMAIN["Domain"]
    INFRA["Infrastructure<br/>Persistence / External API"] --> DOMAIN
    CONFIG["Composition Root"] --> APP
    CONFIG --> INFRA
~~~

Infrastructure triển khai các interface do lớp bên trong định nghĩa. Composition root là nơi biết cả interface lẫn implementation để lắp ghép.

Nếu module domain import org.springframework.*, jakarta.persistence.* hoặc Spring Data chỉ để chạy hành vi nghiệp vụ, ranh giới đã bị rò rỉ. Một số dự án chấp nhận annotation ORM trong domain để giảm mapping; đó là một trade-off riêng. Với mục tiêu domain model Java thuần, hãy giữ framework ở adapter và composition layer.

## 20. Domain Service có cần đăng ký thành Spring Bean không?

Không phải lúc nào cũng cần. Có ba trường hợp thường gặp:

1. Domain Service không có dependency và không giữ trạng thái: có thể tạo trực tiếp hoặc dùng object dùng chung an toàn.
2. Domain Service phụ thuộc một policy hoặc port: có thể được lắp ghép bằng constructor và đăng ký @Bean.
3. Quy tắc thực chất là hành vi của Entity/Value Object: nên chuyển hành vi về đối tượng sở hữu dữ liệu thay vì tạo service chỉ để gọi getter rồi tính.

Nếu domain service được đăng ký singleton, nó phải stateless hoặc chỉ giữ dependency an toàn cho chia sẻ. Không lưu dữ liệu của một Order cụ thể vào field mutable.

Ví dụ:

~~~java
@Configuration
class PricingConfiguration {
    @Bean
    OrderPricingService orderPricingService(DiscountPolicy policy) {
        return new OrderPricingService(policy);
    }
}
~~~

Class OrderPricingService không cần biết nó đang được Spring quản lý. Nó chỉ nhận dependency qua constructor.

## 21. Xử lý Domain Event mà không buộc Domain phụ thuộc Spring

Domain model có thể tạo Domain Event bằng Java thuần:

~~~java
public record OrderConfirmed(
    OrderId orderId,
    Instant occurredAt
) {}
~~~

Aggregate có thể lưu event vừa phát sinh trong một collection nội bộ và cung cấp cách lấy ra cho application/persistence adapter. Application layer hoặc infrastructure sẽ chịu trách nhiệm lưu event cùng transaction, ghi outbox hoặc publish sau commit.

Không nên gọi ApplicationEventPublisher, KafkaTemplate hoặc message broker trực tiếp từ Entity. Những thành phần này thuộc hạ tầng. Domain chỉ diễn đạt sự kiện nghiệp vụ; adapter quyết định cách truyền sự kiện.

Với Spring, có thể dùng application event hoặc transactional event listener cho một số trường hợp trong cùng process. Nếu cần bảo đảm thay đổi database và message được lưu nhất quán, cân nhắc transactional outbox thay vì giả định publish sau commit luôn thành công.

## 22. Những lỗi thường gặp khi kết hợp DDD và Spring

**Gắn @Component cho mọi domain class.** Entity/Value Object không phải service dùng chung. Tạo chúng theo vòng đời nghiệp vụ bằng constructor/factory.

**Để Entity gọi repository hoặc ApplicationContext.** Dependency hạ tầng bị che giấu trong domain. Hãy để application service nạp dữ kiện và gọi hành vi.

**Dùng field injection làm mặc định.** Dependency không rõ ràng và khó test. Ưu tiên constructor injection.

**Đưa trạng thái request vào singleton service.** Có thể gây rò rỉ dữ liệu giữa các request. Giữ handler stateless và dùng biến cục bộ.

**Đặt transaction trong Entity.** Domain object không quản lý transaction manager. Application service xác định transaction boundary.

**Cho domain phụ thuộc Spring Data/JPA.** Mô hình khó chạy độc lập và bị ảnh hưởng bởi ORM. Dùng repository port và adapter nếu cần giữ domain thuần.

**Để persistence record đi xuyên qua application/API.** Hợp đồng ứng dụng bị buộc vào schema. Chuyển đổi sang domain object hoặc DTO phù hợp.

**Dùng Service Locator.** Dependency bị ẩn và khó kiểm thử. Hãy lắp ghép ở composition root.

**Khởi động toàn bộ Spring cho unit test domain.** Test chậm và trộn nhiều trách nhiệm. Kiểm thử domain trực tiếp; dùng Spring integration test cho wiring/transaction.

**Tạo quá nhiều abstraction.** Không cần factory, service và interface nếu chúng không diễn đạt ranh giới hoặc thay đổi thực tế. Giữ thiết kế vừa đủ.

## 23. Quy trình lắp ghép một use case

1. **Xác định hành vi miền:** mô tả quy tắc và bất biến mà use case cần bảo vệ.
2. **Tạo domain object thuần Java:** dùng Entity, Value Object và factory phù hợp.
3. **Định nghĩa port cần thiết:** ví dụ repository, clock hoặc query contract.
4. **Viết application service:** điều phối command, nạp Aggregate, gọi hành vi và lưu kết quả.
5. **Chọn transaction boundary:** đặt @Transactional ở application use case hoặc adapter điều phối phù hợp.
6. **Triển khai infrastructure adapter:** kết nối JPA/database/API và mapping về domain.
7. **Lắp ghép ở Spring composition root:** component scanning hoặc @Configuration/@Bean.
8. **Kiểm thử domain độc lập:** xác nhận hành vi và bất biến không cần Spring.
9. **Kiểm thử wiring và persistence:** xác nhận bean, proxy, transaction và mapping hoạt động.
10. **Rà dependency direction:** domain không phụ thuộc framework hoặc adapter.

## 24. Checklist rà soát

- Entity và Value Object có thể được tạo bằng Java thuần không?
- Constructor/factory có bảo đảm trạng thái hợp lệ không?
- Aggregate Root có kiểm soát thay đổi của Entity con không?
- Domain Service có thực sự diễn đạt quy tắc nghiệp vụ độc lập không?
- Domain model có tránh import Spring, Spring Data và ORM không?
- Repository port có mô tả nhu cầu của Aggregate thay vì CRUD từng bảng không?
- Application service có điều phối use case và giữ trạng thái request trong biến cục bộ không?
- Dependency bắt buộc có được truyền qua constructor không?
- Infrastructure adapter có chuyển đổi persistence model sang domain model không?
- Spring composition root có chọn implementation rõ ràng không?
- Transaction boundary có bao quanh use case phù hợp không?
- Domain unit test có chạy mà không khởi động Spring không?
- Có integration test cho wiring, transaction và persistence không?
- Domain object có bị đăng ký thành singleton bean một cách không cần thiết không?

## 25. Nguyên tắc cần ghi nhớ

Đối tượng miền Java thuần giúp biểu diễn Entity, Value Object, Aggregate và Domain Service bằng ngôn ngữ nghiệp vụ, với constructor, factory và hành vi tự bảo vệ bất biến. Spring đảm nhiệm việc lắp ghép các thành phần ứng dụng, cung cấp dependency, quản lý transaction và kết nối infrastructure adapter.

Hãy để Spring quản lý application service và adapter có vòng đời bean phù hợp; tạo Aggregate theo từng use case bằng constructor hoặc factory. Dùng constructor injection, repository port và composition root để giữ dependency rõ ràng. Khi domain model có thể chạy và được kiểm thử độc lập với Spring, nhóm có thể tận dụng framework mà vẫn giữ mô hình nghiệp vụ dễ hiểu, dễ thay đổi và có ranh giới rõ.
