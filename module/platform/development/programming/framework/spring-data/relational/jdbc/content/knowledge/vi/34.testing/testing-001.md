# Chọn unit test, repository test và integration test theo mục tiêu

Trong ứng dụng **Spring Data Relational JDBC**, một thay đổi có thể đi qua nhiều lớp: quy tắc domain, application service, repository, mapping aggregate, JDBC driver và database. Không phải bài kiểm thử nào cũng cần khởi động toàn bộ những lớp đó. Chọn đúng phạm vi giúp test chạy nhanh, chỉ ra lỗi ở đúng nơi và vẫn bảo vệ được các hành vi quan trọng.

Ba nhóm kiểm thử thường gặp là:

- **Unit test:** kiểm tra một lớp hoặc một quy tắc nhỏ trong bộ nhớ, không cần Spring context hay database.
- **Repository test:** kiểm tra persistence adapter của Spring Data JDBC với database, tập trung vào mapping, SQL và hành vi repository.
- **Integration test:** kiểm tra nhiều thành phần được ghép với nhau trong application context, thường bao gồm service, transaction, repository, migration và database thực tế.

Không có một loại test nào thay thế hoàn toàn hai loại còn lại. Unit test giúp kiểm tra quy tắc nhanh; repository test xác nhận mapping và câu SQL hoạt động; integration test chứng minh các thành phần phối hợp đúng trong cấu hình gần production.

## 1. Bắt đầu từ câu hỏi cần kiểm chứng

Trước khi chọn annotation hoặc test framework, hãy viết rõ điều cần chứng minh.

| Câu hỏi | Phạm vi phù hợp |
|---|---|
| Đơn hàng có từ chối chuyển sang PAID khi chưa được xác nhận không? | Unit test domain |
| Repository có lưu và tải lại đầy đủ order cùng order lines không? | Repository test |
| Custom converter có chuyển Money thành DECIMAL đúng không? | Repository test, có thể thêm unit test converter |
| Migration có tạo đúng FK, unique và index không? | Integration test với database tương thích |
| Service lưu order và audit trong cùng transaction không? | Integration test |
| Optimistic locking có từ chối bản cập nhật cũ không? | Repository test với database |
| Event AFTER_COMMIT chỉ chạy khi transaction commit không? | Integration test |
| Endpoint gọi service và trả response đúng không? | Web/integration test ở tầng ứng dụng |

Cùng một tính năng có thể cần nhiều test nếu có nhiều rủi ro độc lập. Ví dụ, quy tắc domain thanh toán có thể được unit test, còn việc lưu trạng thái và phát event sau commit cần repository/integration test.

### 1.1. Phân biệt lỗi logic và lỗi tích hợp

Một unit test có thể chứng minh phương thức tính tổng tiền trả đúng kết quả. Nhưng nó không chứng minh:

- Mapping Spring Data JDBC ghi đúng cột.
- Converter được đăng ký.
- JDBC driver hỗ trợ kiểu dữ liệu.
- Database có constraint phù hợp.
- Transaction rollback được toàn bộ thay đổi.
- Migration chạy được trên phiên bản database production.

Ngược lại, một integration test end-to-end có thể phát hiện lỗi nhưng thường mất thời gian hơn và khó chỉ ra nguyên nhân chính xác. Vì vậy, hãy đặt test ở lớp gần nhất có thể chứng minh điều đang quan tâm.

## 2. Unit test: kiểm tra domain và logic độc lập

Unit test kiểm tra một đơn vị nhỏ trong bộ nhớ. Test thường không khởi động Spring, không tạo DataSource và không truy cập database.

Các mục tiêu phù hợp:

- Quy tắc chuyển trạng thái aggregate.
- Validation và invariant trong domain model.
- Tính toán giá, thuế, chiết khấu.
- Chọn điều kiện nghiệp vụ.
- Logic chuyển đổi thuần Java.
- Xử lý kết quả từ một dependency giả lập.

Ví dụ aggregate:

```java
public class PurchaseOrder {

    private OrderStatus status;
    private final List<OrderLine> lines;

    public PurchaseOrder(
            OrderStatus status,
            List<OrderLine> lines) {
        this.status = status;
        this.lines = new ArrayList<>(lines);
    }

    public void markPaid() {
        if (lines.isEmpty()) {
            throw new IllegalStateException(
                "An empty order cannot be paid"
            );
        }

        if (status != OrderStatus.NEW) {
            throw new IllegalStateException(
                "Only a new order can be paid"
            );
        }

        status = OrderStatus.PAID;
    }

    public OrderStatus getStatus() {
        return status;
    }
}
```

Unit test:

```java
class PurchaseOrderTest {

    @Test
    void marksNonEmptyNewOrderAsPaid() {
        PurchaseOrder order = new PurchaseOrder(
            OrderStatus.NEW,
            List.of(new OrderLine("BOOK-01", 2))
        );

        order.markPaid();

        assertThat(order.getStatus())
            .isEqualTo(OrderStatus.PAID);
    }

    @Test
    void rejectsPaymentForEmptyOrder() {
        PurchaseOrder order = new PurchaseOrder(
            OrderStatus.NEW,
            List.of()
        );

        assertThatThrownBy(order::markPaid)
            .isInstanceOf(IllegalStateException.class)
            .hasMessageContaining("empty order");
    }

    @Test
    void rejectsPayingAnAlreadyPaidOrder() {
        PurchaseOrder order = new PurchaseOrder(
            OrderStatus.PAID,
            List.of(new OrderLine("BOOK-01", 2))
        );

        assertThatThrownBy(order::markPaid)
            .isInstanceOf(IllegalStateException.class)
            .hasMessageContaining("new order");
    }
}
```

Các test này chỉ kiểm tra quy tắc của aggregate. Không cần dùng repository mock vì không có persistence trong hành vi đang kiểm tra.

### 2.1. Khi nào nên mock dependency?

Nếu một application service điều phối nhiều cổng bên ngoài, unit test có thể mock các dependency để kiểm tra quyết định điều phối.

```java
class PaymentApplicationServiceTest {

    private final PurchaseOrderRepository repository =
        mock(PurchaseOrderRepository.class);

    private final PaymentGateway paymentGateway =
        mock(PaymentGateway.class);

    private final PaymentApplicationService service =
        new PaymentApplicationService(repository, paymentGateway);

    @Test
    void requestsPaymentForTheOrder() {
        PurchaseOrder order = newOrder();
        when(repository.findById(42L))
            .thenReturn(Optional.of(order));

        when(paymentGateway.charge(any()))
            .thenReturn(PaymentResult.approved("PAY-100"));

        service.pay(42L);

        verify(paymentGateway).charge(any());
        verify(repository).save(order);
    }
}
```

Test này kiểm tra service gọi gateway và lưu aggregate theo luồng mong muốn. Nó không chứng minh repository thật có thể lưu aggregate. Hành vi đó cần repository test.

### 2.2. Tránh mock quá sâu

Không nên mock từng lớp Spring Data JDBC nội bộ như `JdbcConverter`, `DataAccessStrategy`, `JdbcTemplate` hoặc `MappingContext` chỉ để kiểm tra một repository thật. Khi mock quá sâu, test dễ xác nhận cách triển khai hiện tại thay vì hành vi mà ứng dụng cần.

Với persistence, dùng database test thật thường cung cấp bằng chứng đáng tin cậy hơn việc giả lập nhiều thành phần framework.

### 2.3. Khi unit test không đủ

Nếu logic phụ thuộc vào semantics database như NULL, collation, decimal precision, transaction isolation, generated key hoặc FK, unit test không thể chứng minh hành vi đó. Hãy chuyển phần kiểm chứng này sang repository hoặc integration test.

## 3. Repository test: kiểm tra mapping và persistence

Repository test tập trung vào cách Spring Data JDBC tương tác với database. Nó kiểm tra những điều mà unit test không thể xác nhận:

- Entity và aggregate được ánh xạ đúng bảng/cột.
- `@Id`, `@Column`, `@Table` và `@MappedCollection` hoạt động đúng.
- Aggregate root cùng member được lưu và tải lại đúng.
- Custom reading/writing converter được áp dụng.
- Query method và `@Query` trả kết quả đúng.
- Generated ID và optimistic locking hoạt động.
- Database constraint từ chối dữ liệu không hợp lệ.

Với Spring Boot, annotation thường dùng là `@DataJdbcTest`.

### 3.1. @DataJdbcTest cung cấp những gì?

`@DataJdbcTest` là test slice dành cho Spring Data JDBC. Theo cấu hình mặc định, Spring Boot tạo application context giới hạn cho lớp persistence, cấu hình repository Spring Data JDBC, `JdbcTemplate` và một database nhúng nếu dependency database nhúng có trên classpath.

Thông thường:

- Repository và entity được đưa vào test context.
- Cấu hình kế thừa `AbstractJdbcConfiguration` được xem xét.
- Các component thông thường của ứng dụng không tự động được scan như trong `@SpringBootTest`.
- Test được chạy trong transaction và rollback khi test kết thúc.
- Có thể dùng `@AutoConfigureTestDatabase` để kiểm soát DataSource được sử dụng.

Import của `@DataJdbcTest` khác nhau theo thế hệ Spring Boot. Với Spring Boot 3.x, package thường là `org.springframework.boot.test.autoconfigure.data.jdbc.DataJdbcTest`. Với các dòng Spring Boot mới tách test module, hãy dùng package được tài liệu của phiên bản dự án chỉ định.

### 3.2. Ví dụ kiểm tra lưu và tải aggregate

Aggregate:

```java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;

    @MappedCollection(idColumn = "order_id")
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public PurchaseOrder(
            String orderNumber,
            List<OrderLine> lines) {
        this.orderNumber = orderNumber;
        this.lines = new ArrayList<>(lines);
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public List<OrderLine> getLines() {
        return List.copyOf(lines);
    }
}
```

Member:

```java
public class OrderLine {

    @Id
    private Long id;

    private String productCode;
    private int quantity;

    protected OrderLine() {
    }

    public OrderLine(String productCode, int quantity) {
        this.productCode = productCode;
        this.quantity = quantity;
    }

    public String getProductCode() {
        return productCode;
    }

    public int getQuantity() {
        return quantity;
    }
}
```

Repository:

```java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
```

Repository test:

```java
@DataJdbcTest
class PurchaseOrderRepositoryTest {

    @Autowired
    PurchaseOrderRepository repository;

    @Test
    void savesAndLoadsTheCompleteAggregate() {
        PurchaseOrder order = new PurchaseOrder(
            "ORD-1001",
            List.of(
                new OrderLine("BOOK-01", 2),
                new OrderLine("PEN-02", 5)
            )
        );

        PurchaseOrder saved = repository.save(order);

        assertThat(saved.getId()).isNotNull();

        PurchaseOrder loaded = repository.findById(saved.getId())
            .orElseThrow();

        assertThat(loaded.getOrderNumber())
            .isEqualTo("ORD-1001");

        assertThat(loaded.getLines())
            .extracting(OrderLine::getProductCode)
            .containsExactly("BOOK-01", "PEN-02");

        assertThat(loaded.getLines())
            .extracting(OrderLine::getQuantity)
            .containsExactly(2, 5);
    }
}
```

Test này chứng minh Spring Data JDBC lưu và tải aggregate theo mapping đã khai báo. Nó có thể phát hiện sai tên bảng/cột, thiếu schema, sai `idColumn` hoặc mapping member không đúng.

### 3.3. Kiểm tra custom converter

Giả sử domain dùng value object `EmailAddress`, nhưng database lưu chuỗi VARCHAR. Repository test nên xác nhận hai chiều:

1. Lưu aggregate chứa `EmailAddress`.
2. Đọc aggregate từ database.
3. Xác nhận giá trị domain được khôi phục chính xác.

```java
@DataJdbcTest
@Import(CustomerJdbcConfiguration.class)
class CustomerRepositoryTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void writesAndReadsEmailAddress() {
        Customer customer = new Customer(
            new EmailAddress("an@example.com")
        );

        Customer saved = repository.save(customer);

        Customer loaded = repository.findById(saved.getId())
            .orElseThrow();

        assertThat(loaded.getEmail())
            .isEqualTo(new EmailAddress("an@example.com"));
    }
}
```

`@Import` dùng để đưa cấu hình bổ sung vào test slice nếu cấu hình đó không tự được phát hiện. Với cấu hình converter, cần kiểm tra đúng cơ chế đăng ký của phiên bản Spring Data JDBC đang dùng.

### 3.4. Kiểm tra query method

Ví dụ repository:

```java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByStatus(OrderStatus status);

    boolean existsByOrderNumber(String orderNumber);

    long countByStatus(OrderStatus status);
}
```

Repository test nên tạo nhiều bản ghi với trạng thái khác nhau, sau đó xác nhận query chỉ trả đúng các hàng thỏa điều kiện.

```java
@Test
void findsOnlyOrdersWithRequestedStatus() {
    repository.save(newOrder("ORD-1"));
    repository.save(paidOrder("ORD-2"));

    List<PurchaseOrder> paid =
        repository.findByStatus(OrderStatus.PAID);

    assertThat(paid)
        .extracting(PurchaseOrder::getOrderNumber)
        .containsExactly("ORD-2");
}
```

Nếu query phụ thuộc vào kiểu dữ liệu hoặc cú pháp riêng của database, hãy chạy test với dialect tương ứng.

### 3.5. Kiểm tra database constraint

Có thể dùng `JdbcTemplate` trong repository test để thử ghi trực tiếp một hàng vi phạm constraint. Cách này chứng minh database thực sự bảo vệ quy tắc, thay vì chỉ xác nhận domain validation.

```java
@DataJdbcTest
class OrderConstraintTest {

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void rejectsDuplicateOrderNumber() {
        insertOrder("ORD-1001");

        assertThatThrownBy(() -> insertOrder("ORD-1001"))
            .isInstanceOf(DataIntegrityViolationException.class);
    }

    private void insertOrder(String orderNumber) {
        jdbcTemplate.update(
            "INSERT INTO purchase_orders(order_number) VALUES (?)",
            orderNumber
        );
    }
}
```

Test cần schema có unique constraint tương ứng. Nếu database nhúng không hỗ trợ đầy đủ cú pháp hoặc semantics production, hãy chuyển test này sang database phù hợp.

## 4. Repository test dùng database nhúng hay database thật?

Database nhúng như H2 hữu ích vì:

- Khởi động nhanh.
- Dễ chạy trong CI.
- Không cần cài database riêng.
- Phù hợp kiểm tra mapping và CRUD cơ bản.
- Có thể tạo database mới cho từng test context.

Nhưng database nhúng không đảm bảo tương thích hoàn toàn với production.

Khác biệt có thể xuất hiện ở:

- Cú pháp SQL.
- Kiểu dữ liệu và conversion.
- Identity, sequence và generated keys.
- JSON, ARRAY và kiểu vendor-specific.
- Collation và so sánh chuỗi.
- Semantics của NULL và unique.
- Foreign key, cascade và deferred constraint.
- Locking và isolation.
- Execution plan và index.

Vì vậy, không nên xem một test chạy thành công trên H2 là bằng chứng đầy đủ rằng ứng dụng sẽ hoạt động trên PostgreSQL, MySQL, Oracle hoặc SQL Server.

### 4.1. Khi database nhúng là đủ?

H2 thường đủ cho các kiểm tra mapping đơn giản nếu ứng dụng dùng những kiểu SQL phổ biến và không phụ thuộc hành vi đặc thù của vendor.

Ví dụ:

- Lưu và tải một aggregate đơn giản.
- Kiểm tra repository CRUD.
- Kiểm tra converter từ String sang value object.
- Kiểm tra query equality cơ bản.
- Kiểm tra domain-to-database mapping không phụ thuộc dialect.

### 4.2. Khi cần database production-compatible?

Dùng database cùng hệ quản trị và phiên bản tương thích khi test liên quan:

- Sequence hoặc identity behavior.
- Custom SQL và vendor-specific syntax.
- JSONB, ARRAY, UUID hoặc spatial types.
- Locking, transaction isolation và concurrency.
- Migration có cú pháp đặc thù.
- Constraint hoặc index có semantics riêng.
- Query plan hoặc hiệu năng.

Trong các trường hợp này, Testcontainers thường là lựa chọn phù hợp.

## 5. Integration test: kiểm tra nhiều thành phần phối hợp

Integration test kiểm tra nhiều lớp cùng hoạt động trong application context. Với Spring Data JDBC, một integration test có thể đi qua:

```text
HTTP Controller
      |
Application Service
      |
Repository / JdbcAggregateTemplate
      |
JdbcConverter / DataAccessStrategy
      |
DataSource / JDBC Driver
      |
Database
```

Mục tiêu là xác nhận hành vi thực tế của use case trong cấu hình gần với ứng dụng đang triển khai.

Integration test phù hợp để kiểm tra:

- Service điều phối nhiều repository.
- Transaction bao trùm nhiều thao tác persistence.
- Rollback khi một bước thất bại.
- Event chỉ được xử lý sau commit.
- Outbox record được ghi cùng aggregate.
- Flyway/Liquibase migration chạy trên database đích.
- Cấu hình custom converter, dialect và DataSource.
- Kết nối giữa controller, service và persistence.

### 5.1. Dùng @SpringBootTest

`@SpringBootTest` khởi động Spring application context để kiểm tra cấu hình và các bean của ứng dụng.

```java
@SpringBootTest
class CheckoutServiceIntegrationTest {

    @Autowired
    CheckoutService checkoutService;

    @Autowired
    PurchaseOrderRepository orderRepository;

    @Test
    void completesCheckout() {
        Long orderId = checkoutService.checkout(testOrder());

        PurchaseOrder saved = orderRepository.findById(orderId)
            .orElseThrow();

        assertThat(saved.getStatus())
            .isEqualTo(OrderStatus.NEW);
    }
}
```

Ví dụ này kiểm tra service và repository được kết nối trong Spring context. Với database nhúng, nó vẫn chưa chứng minh hoàn toàn tính tương thích với database production.

### 5.2. Dùng Testcontainers

Testcontainers tạo database trong container để test sử dụng JDBC driver và database engine thực tế.

Ví dụ PostgreSQL với Spring Boot hỗ trợ `@ServiceConnection`:

```java
@Testcontainers
@SpringBootTest
class CheckoutPostgresIntegrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    CheckoutService checkoutService;

    @Autowired
    PurchaseOrderRepository repository;

    @Test
    void persistsOrderUsingPostgres() {
        Long id = checkoutService.checkout(testOrder());

        PurchaseOrder loaded = repository.findById(id)
            .orElseThrow();

        assertThat(loaded.getId()).isEqualTo(id);
    }
}
```

Cấu hình này cần dependency Testcontainers cho PostgreSQL và module `spring-boot-testcontainers` khi dùng Spring Boot hỗ trợ service connection. `@ServiceConnection` có từ Spring Boot 3.1; hãy đối chiếu package và module theo phiên bản Boot của dự án.

Nếu dùng test slice `@DataJdbcTest` với container, cần bảo đảm auto-configuration không thay DataSource container bằng database nhúng. Có thể dùng `@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)` khi cấu hình test cần giữ DataSource đã khai báo.

### 5.3. Chạy migration trong integration test

Nếu production sử dụng Flyway hoặc Liquibase, integration test nên dùng cùng migration để kiểm tra schema thực tế.

Quy trình:

1. Khởi động database container sạch.
2. Tạo DataSource từ container.
3. Chạy migration.
4. Khởi tạo repository và service.
5. Thực hiện use case.
6. Đọc lại dữ liệu và xác nhận kết quả.

Không nên duy trì một schema test viết tay khác hẳn schema production. Điều đó có thể khiến test pass dù migration thật bị lỗi hoặc thiếu constraint.

## 6. Kiểm tra transaction và rollback

Transaction là một trong những hành vi cần integration test khi dùng Spring Data JDBC.

Ví dụ service:

```java
@Service
public class CheckoutService {

    private final PurchaseOrderRepository orders;
    private final JdbcTemplate jdbcTemplate;

    public CheckoutService(
            PurchaseOrderRepository orders,
            JdbcTemplate jdbcTemplate) {
        this.orders = orders;
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public Long checkout(PurchaseOrder order) {
        PurchaseOrder saved = orders.save(order);

        jdbcTemplate.update(
            "INSERT INTO order_audit(order_id, action) VALUES (?, ?)",
            saved.getId(),
            "CHECKOUT"
        );

        return saved.getId();
    }
}
```

Một integration test cần chứng minh hai thay đổi cùng rollback khi bước audit thất bại.

```java
@Test
void rollsBackOrderWhenAuditInsertFails() {
    assertThatThrownBy(() ->
        checkoutService.checkout(orderThatCausesAuditFailure())
    ).isInstanceOf(DataAccessException.class);

    assertThat(orderRepository.findByOrderNumber("ORD-FAIL"))
        .isEmpty();
}
```

Test giả định có thể cấu hình dữ liệu hoặc constraint để audit insert thất bại. Mục tiêu là xác nhận đơn hàng không được commit riêng trước khi toàn bộ use case hoàn tất.

### 6.1. Chú ý transaction của chính test

`@DataJdbcTest` mặc định chạy mỗi test trong transaction và rollback khi kết thúc. Đây là hành vi tiện lợi cho test repository.

Tuy nhiên, nếu integration test cần quan sát transaction do service tự mở, đặc biệt với `AFTER_COMMIT`, không nên vô tình bọc toàn bộ test trong một transaction ngoài.

Có thể tắt transaction test cho method hoặc class:

```java
@SpringBootTest
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class TransactionBoundaryIntegrationTest {
    // Service sẽ mở transaction riêng qua Spring proxy.
}
```

Khi đó, transaction của service thực sự commit hoặc rollback trước khi test đọc lại dữ liệu.

### 6.2. Test rollback và exception

Spring mặc định rollback với `RuntimeException` và `Error`; checked exception không rollback theo mặc định nếu không cấu hình `rollbackFor`.

Test nên phản ánh chính sách thực tế của service. Nếu exception bị bắt và không được ném lại, transaction có thể commit. Hãy kiểm tra chính xác đường đi của exception.

## 7. Kiểm thử optimistic locking

Nếu aggregate dùng `@Version`, repository test cần kiểm tra rằng hai bản đọc cùng một phiên bản không thể ghi đè lẫn nhau mà không phát hiện xung đột.

Ví dụ:

```java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    private String status;
}
```

Kịch bản:

1. Đọc cùng một order thành hai object độc lập.
2. Cập nhật và save object thứ nhất.
3. Thử save object thứ hai với version cũ.
4. Xác nhận Spring Data JDBC ném `OptimisticLockingFailureException`.

```java
@Test
void rejectsStaleAggregateUpdate() {
    PurchaseOrder first = repository.findById(42L).orElseThrow();
    PurchaseOrder second = repository.findById(42L).orElseThrow();

    first.setStatus("PAID");
    repository.save(first);

    second.setStatus("CANCELLED");

    assertThatThrownBy(() -> repository.save(second))
        .isInstanceOf(OptimisticLockingFailureException.class);
}
```

Đây là hành vi phụ thuộc database update và version column, nên cần repository test với database thực tế.

## 8. Kiểm thử custom query và SQL

Nếu repository dùng query method hoặc `@Query`, lựa chọn test theo độ phức tạp của SQL.

- Query đơn giản dựa trên property có thể kiểm tra bằng `@DataJdbcTest`.
- Query có join, projection hoặc vendor-specific SQL nên kiểm tra trên database production-compatible.
- Query trả aggregate cần cung cấp đủ cột cho mapping.
- Query có LIMIT, OFFSET, named parameter hoặc biểu thức SQL riêng cần được xác nhận bằng JDBC driver thật.

Ví dụ:

```java
@Query("""
    SELECT *
    FROM purchase_orders
    WHERE status = :status
      AND created_at >= :from
    ORDER BY created_at DESC
    """)
List<PurchaseOrder> findRecentOrders(
    String status,
    LocalDateTime from
);
```

Test nên tạo dữ liệu ở cả hai phía của điều kiện ngày và trạng thái, sau đó xác nhận kết quả. Không chỉ kiểm tra danh sách không rỗng vì test đó có thể pass ngay cả khi query lọc sai.

## 9. Kiểm thử lifecycle callback và domain event

Nếu aggregate sử dụng callback hoặc event, test nên tách hai câu hỏi:

- Repository có kích hoạt callback/event publication đúng không?
- Listener có được gọi ở đúng transaction phase không?

Repository test có thể kiểm tra callback mapping như `BeforeConvertCallback` hoặc `AfterSaveCallback`.

Integration test phù hợp hơn khi cần chứng minh `@TransactionalEventListener(AFTER_COMMIT)` chỉ chạy sau commit:

1. Gọi service trong transaction.
2. Xác nhận listener chưa chạy trước commit.
3. Cho transaction commit.
4. Xác nhận listener được gọi.
5. Thực hiện trường hợp rollback và xác nhận listener AFTER_COMMIT không chạy.

Nếu listener gửi message ra broker, cần thêm test cho phần tích hợp đó hoặc dùng outbox test để kiểm tra record được ghi cùng transaction. Không dùng mock listener để kết luận broker đã nhận message.

## 10. Kiểm thử repository và service với các ranh giới rõ ràng

Có thể tổ chức test theo cấu trúc:

```text
src/test/java/
  domain/
    PurchaseOrderTest.java
    MoneyTest.java

  persistence/
    PurchaseOrderRepositoryTest.java
    CustomerRepositoryTest.java
    JdbcConverterTest.java

  integration/
    CheckoutServiceIntegrationTest.java
    TransactionBoundaryIntegrationTest.java
    MigrationIntegrationTest.java
```

Tên package có thể theo cấu trúc dự án. Điều quan trọng là mỗi test class có một mục tiêu rõ ràng.

### 10.1. Unit test không cần database

Đặt test cho domain object và logic thuần Java ở lớp unit test. Test chạy nhanh, không cần profile database hoặc migration.

### 10.2. Repository test không cần toàn bộ ứng dụng

Dùng `@DataJdbcTest` cho persistence slice. Chỉ import những cấu hình bổ sung thực sự cần thiết.

### 10.3. Integration test cần cấu hình gần production

Dùng `@SpringBootTest` và Testcontainers khi cần kiểm tra service, transaction, migration hoặc cấu hình dialect. Có thể nhóm các test tốn thời gian vào một task/profile riêng trong CI nếu thời gian pipeline là vấn đề.

## 11. Chọn test theo rủi ro, không theo số lượng

Không cần viết cả ba loại test cho mọi phương thức. Hãy chọn theo rủi ro của hành vi:

| Hành vi | Unit | Repository | Integration |
|---|---:|---:|---:|
| Domain state transition | Chính | Không cần | Tùy use case |
| Tính tổng tiền thuần Java | Chính | Không cần | Không cần |
| Mapping aggregate | Không đủ | Chính | Có thể bổ sung |
| Custom converter | Có thể test riêng | Chính | Khi phụ thuộc vendor |
| Repository query | Không đủ | Chính | Khi SQL phức tạp |
| Unique/FK/CHECK | Không đủ | Chính | Với database production |
| Flyway/Liquibase migration | Không đủ | Có thể | Chính |
| Transaction nhiều repository | Không đủ | Không đủ | Chính |
| AFTER_COMMIT listener | Không đủ | Một phần | Chính |
| API + service + database | Không đủ | Không đủ | Chính |

Một quy tắc thực tế:

- Nếu hành vi không cần Spring hoặc database, viết unit test.
- Nếu câu hỏi liên quan persistence, viết repository test.
- Nếu cần xác nhận nhiều bean, transaction, migration hoặc database vendor, viết integration test.

## 12. Những lỗi thường gặp khi chọn phạm vi test

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Unit test pass nhưng repository lưu sai cột | Không có test mapping | Thêm `@DataJdbcTest` |
| H2 pass nhưng PostgreSQL fail | Khác biệt dialect | Dùng PostgreSQL Testcontainers |
| `@DataJdbcTest` không tìm thấy service | Slice không scan component thông thường | Dùng `@Import` hoặc `@SpringBootTest` nếu cần |
| Test converter không được áp dụng | Chưa đưa cấu hình converter vào slice | Import cấu hình hoặc kiểm tra `AbstractJdbcConfiguration` |
| Test transaction không thấy commit | Test tự mở transaction ngoài | Dùng `Propagation.NOT_SUPPORTED` khi cần quan sát commit thật |
| Migration production lỗi nhưng test pass | Test dùng schema tự tạo khác migration | Chạy migration thật trong test |
| Test phụ thuộc ID cố định | Sequence/identity không bảo đảm số liên tục | Chỉ kiểm tra ID hợp lệ hoặc quan hệ dữ liệu |
| Test repository quá chậm | Khởi động full context không cần thiết | Dùng `@DataJdbcTest` |
| Integration test quá khó tìm nguyên nhân | Gộp quá nhiều hành vi vào một test | Tách test domain, persistence và use case |
| Mock quá nhiều thành phần framework | Test đang kiểm tra implementation nội bộ | Dùng database test cho persistence |
| Test chạy phụ thuộc thứ tự | Dữ liệu dùng chung hoặc cleanup không rõ | Dùng transaction rollback hoặc fixture riêng |
| Test concurrency không tái hiện race condition | Chỉ kiểm tra tuần tự | Dùng nhiều transaction/thread và database thực tế |

## 13. Ví dụ một bộ test hoàn chỉnh cho tính năng thanh toán

Giả sử tính năng thanh toán có ba yêu cầu:

1. Đơn hàng rỗng không được thanh toán.
2. Trạng thái PAID phải được lưu.
3. Audit được ghi trong cùng transaction với thay đổi đơn hàng.

Có thể chia như sau.

### 13.1. Unit test domain

```java
@Test
void emptyOrderCannotBePaid() {
    PurchaseOrder order = emptyNewOrder();

    assertThatThrownBy(order::markPaid)
        .isInstanceOf(IllegalStateException.class);
}
```

Test này xác nhận invariant của aggregate.

### 13.2. Repository test

```java
@DataJdbcTest
class PurchaseOrderPersistenceTest {

    @Autowired
    PurchaseOrderRepository repository;

    @Test
    void persistsPaidStatus() {
        PurchaseOrder order = newNewOrder();
        order.markPaid();

        PurchaseOrder saved = repository.save(order);

        PurchaseOrder loaded = repository.findById(saved.getId())
            .orElseThrow();

        assertThat(loaded.getStatus())
            .isEqualTo(OrderStatus.PAID);
    }
}
```

Test này xác nhận mapping và persistence trạng thái.

### 13.3. Integration test transaction

```java
@SpringBootTest
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class PaymentTransactionIntegrationTest {

    @Autowired
    PaymentService paymentService;

    @Autowired
    PurchaseOrderRepository orderRepository;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void rollsBackOrderWhenAuditFails() {
        PurchaseOrder order = createOrderWithAuditConflict();

        assertThatThrownBy(() ->
            paymentService.pay(order.getId())
        ).isInstanceOf(DataAccessException.class);

        PurchaseOrder reloaded = orderRepository
            .findById(order.getId())
            .orElseThrow();

        assertThat(reloaded.getStatus())
            .isEqualTo(OrderStatus.NEW);
    }
}
```

Test này giả định có thể tạo điều kiện khiến bước audit vi phạm constraint. Nó kiểm tra transaction service với repository và JDBC cùng database.

Bộ test trên tránh dùng một test lớn để chứng minh mọi thứ cùng lúc. Mỗi test có một mục tiêu riêng, nên khi lỗi xuất hiện sẽ dễ xác định lớp cần sửa.

## 14. Tích hợp vào CI

Một pipeline có thể phân nhóm test theo chi phí:

```text
Pull request:
  1. Compile
  2. Unit tests
  3. Repository tests với database nhúng
  4. Integration tests quan trọng với Testcontainers

Main branch / nightly:
  1. Toàn bộ test suite
  2. Integration test theo từng database được hỗ trợ
  3. Migration compatibility test
  4. Concurrency hoặc performance test cần môi trường riêng
```

Không phải dự án nào cũng cần mọi nhóm. Hãy chọn theo số database hỗ trợ, độ phức tạp persistence và mức rủi ro của nghiệp vụ.

### 14.1. Giữ dữ liệu test độc lập

Mỗi test nên tự tạo dữ liệu cần thiết và tránh dựa vào thứ tự thực thi. Dùng ID trả về từ repository thay vì giả định sequence bắt đầu ở một số cố định.

Nếu test cần dữ liệu nền, dùng fixture hoặc SQL script rõ ràng. Tránh dùng một database đang có dữ liệu phát triển làm nguồn test.

### 14.2. Chạy migration trên database sạch

CI nên có ít nhất một đường chạy migration từ schema trống trên database tương thích production. Điều này phát hiện lỗi DDL mà unit test hoặc H2 có thể không thấy.

Với dự án hỗ trợ nhiều dialect, có thể tạo matrix job cho từng database quan trọng thay vì chỉ kiểm tra một hệ quản trị.

## 15. Bài thực hành

**Bài 1.** Một phương thức domain từ chối thanh toán khi đơn hàng rỗng. Nên dùng loại test nào?

*Đáp án:* Unit test, vì đây là quy tắc domain thuần Java.

**Bài 2.** Muốn chứng minh `@MappedCollection` lưu và tải lại child rows đúng, cần loại test nào?

*Đáp án:* Repository test với `@DataJdbcTest` và database.

**Bài 3.** Muốn kiểm tra custom converter hoạt động với PostgreSQL JSONB, nên dùng gì?

*Đáp án:* Repository/integration test với PostgreSQL tương thích production, thường qua Testcontainers.

**Bài 4.** `@DataJdbcTest` có tự tải toàn bộ application service không?

*Đáp án:* Không. Đây là test slice cho Spring Data JDBC; component thông thường cần được import hoặc dùng full application context.

**Bài 5.** Vì sao repository test mặc định rollback sau mỗi test?

*Đáp án:* Spring Boot cấu hình `@DataJdbcTest` theo transaction test để dữ liệu không rò sang test khác. Đây không phải bằng chứng rằng transaction service đã commit.

**Bài 6.** Cần xác nhận service lưu order và audit cùng transaction. Nên dùng loại test nào?

*Đáp án:* Integration test với service, repository/JDBC và database thật; cố ý làm một bước thất bại rồi xác nhận toàn bộ thay đổi rollback.

**Bài 7.** Vì sao H2 pass không chứng minh PostgreSQL pass?

*Đáp án:* Hai database có thể khác SQL dialect, type mapping, sequence, locking, constraint và transaction semantics.

**Bài 8.** Khi nào cần `@SpringBootTest` thay cho `@DataJdbcTest`?

*Đáp án:* Khi cần kiểm tra nhiều bean và cấu hình ứng dụng như service, transaction, event listener, security hoặc HTTP flow.

**Bài 9.** Một test kiểm tra query có trả đúng hàng hay không nhưng không kiểm tra execution plan. Test đó chứng minh query đã tối ưu chưa?

*Đáp án:* Chưa. Kết quả đúng chứng minh logic lọc; hiệu năng cần dữ liệu đại diện, execution plan và đo đạc phù hợp.

## 16. Điều cần ghi nhớ

- **Unit test** dành cho domain logic và code thuần Java, chạy nhanh, không cần Spring context hoặc database.
- **Repository test** dùng `@DataJdbcTest` để xác nhận aggregate mapping, converter, query, generated ID, constraint và optimistic locking.
- **Integration test** dùng `@SpringBootTest` khi cần kiểm tra service, transaction, migration, event hoặc nhiều bean phối hợp.
- `@DataJdbcTest` thường dùng database nhúng và rollback transaction sau mỗi test; điều này tiện cho persistence slice nhưng không chứng minh dialect production.
- Dùng Testcontainers khi hành vi phụ thuộc database engine, JDBC driver, SQL vendor-specific hoặc transaction semantics.
- Dùng migration thật trong test để schema được kiểm chứng giống cách triển khai.
- Không mock toàn bộ Spring Data JDBC internals để giả lập persistence; kiểm tra mapping bằng database thật.
- Tắt transaction của test bằng `Propagation.NOT_SUPPORTED` khi cần quan sát transaction commit do service quản lý.
- Chia test theo mục tiêu để lỗi dễ xác định và pipeline giữ được tốc độ.
- Chọn test theo rủi ro và hành vi cần chứng minh, không theo số lượng test cho mỗi lớp.

### Tài liệu tham khảo chính thức

- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@DataJdbcTest`, `@JdbcTest`, `@SpringBootTest` và hành vi transaction của test slice.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): quản lý container và service connection trong integration test.
- [Spring Boot 3.5 — DataJdbcTest API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/data/jdbc/DataJdbcTest.html): phạm vi component scan, database nhúng và rollback mặc định.
- [Spring Framework — Testing](https://docs.spring.io/spring-framework/reference/testing.html): hỗ trợ kiểm thử tích hợp với Spring TestContext Framework.
- [Spring Data Relational — JDBC Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): mapping aggregate và dữ liệu quan hệ trong Spring Data JDBC.
- [Testcontainers — PostgreSQL Module](https://java.testcontainers.org/modules/databases/postgres/): khởi chạy PostgreSQL container cho test.

Khi lựa chọn, hãy bắt đầu từ hành vi cần chứng minh: logic thuần Java dùng unit test; mapping và SQL dùng repository test; transaction, migration và nhiều thành phần phối hợp dùng integration test trên database tương thích production.
