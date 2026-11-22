# Kiểm thử rollback giữa các bảng và nhiều repository

Trong **Spring Data Relational JDBC**, một use case thường ghi nhiều bảng và có thể gọi nhiều repository. Ví dụ tạo đơn hàng có thể lưu aggregate đơn hàng, cập nhật tồn kho và ghi audit record. Nếu một bước thất bại, ứng dụng thường cần rollback toàn bộ thay đổi để database không rơi vào trạng thái chỉ hoàn thành một nửa nghiệp vụ.

Để kiểm thử điều đó, cần hiểu transaction boundary của Spring, cách Spring Data JDBC dùng chung connection trong transaction, và cách test framework tự rollback test. Một test có thể pass vì transaction của chính test bị rollback, dù service thực tế không có transaction bao quanh nhiều repository. Vì vậy, phải chọn đúng kiểu test cho câu hỏi cần xác nhận.

Bài này tập trung vào:

- Transaction bao quanh nhiều repository và nhiều bảng.
- Khác biệt giữa test-managed transaction và transaction của service.
- Cách kiểm tra dữ liệu sau khi một bước giữa chừng thất bại.
- Rollback rules cho runtime exception và checked exception.
- Propagation, REQUIRES_NEW, nhiều DataSource và thao tác bất đồng bộ.
- Giới hạn rollback đối với hệ thống bên ngoài và cách dùng transactional outbox.

## 1. Vì sao cần rollback giữa nhiều bảng?

Giả sử một use case đặt hàng thực hiện ba thay đổi:

1. Insert đơn hàng và các dòng hàng vào bảng order/order_line.
2. Trừ số lượng tồn kho trong bảng inventory.
3. Ghi lịch sử nghiệp vụ vào bảng order_audit.

Nếu bước 1 và 2 thành công nhưng bước 3 thất bại, trạng thái mong muốn thường là tất cả thay đổi database được hoàn tác:

```text
placeOrder()
    │
    ├── save PurchaseOrder + OrderLine
    │
    ├── update Inventory
    │
    └── insert OrderAudit  ── lỗi
                  │
                  ▼
              ROLLBACK
                  │
                  ├── Order không tồn tại
                  ├── OrderLine không tồn tại
                  ├── Inventory trở về số lượng cũ
                  └── OrderAudit không tồn tại
```

Rollback chỉ có thể hoàn tác các thay đổi thuộc cùng transaction database. Nếu mỗi repository call tự hoàn tất một transaction riêng, thay đổi của bước trước có thể đã commit trước khi bước sau thất bại.

## 2. Transaction boundary nên đặt ở service/use case

Repository là thành phần truy cập dữ liệu. Một nghiệp vụ gồm nhiều thao tác repository thường cần transaction ở tầng service:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final PurchaseOrderRepository orderRepository;
    private final InventoryRepository inventoryRepository;
    private final OrderAuditRepository auditRepository;

    public OrderService(
            PurchaseOrderRepository orderRepository,
            InventoryRepository inventoryRepository,
            OrderAuditRepository auditRepository) {
        this.orderRepository = orderRepository;
        this.inventoryRepository = inventoryRepository;
        this.auditRepository = auditRepository;
    }

    @Transactional
    public PurchaseOrder placeOrder(PlaceOrderCommand command) {
        InventoryItem item = inventoryRepository
                .findBySku(command.sku())
                .orElseThrow();

        if (item.availableQuantity() < command.quantity()) {
            throw new IllegalStateException("Insufficient inventory");
        }

        PurchaseOrder order = orderRepository.save(
                PurchaseOrder.pending(
                        command.customerId(),
                        command.sku(),
                        command.quantity()
                )
        );

        inventoryRepository.save(
                item.decrease(command.quantity())
        );

        auditRepository.save(
                OrderAudit.created(order.id(), command.customerId())
        );

        return order;
    }
}
```

`@Transactional` trên service tạo một transaction bao quanh toàn bộ lời gọi phương thức. Các repository call bên trong tham gia transaction hiện tại nếu chúng dùng cùng transaction manager và cùng DataSource.

Nếu một thao tác ném runtime exception và exception đi ra khỏi transaction boundary, Spring mặc định đánh dấu transaction rollback. Các lệnh ghi trước đó trong transaction sẽ không được commit.

### 2.1. Vì sao không chỉ dựa vào transaction của từng repository?

Các phương thức CRUD của Spring Data repository thường có transaction configuration riêng. Nhưng nếu service gọi ba repository mà không có transaction bao quanh, mỗi repository call có thể chạy trong transaction riêng:

```text
Service không có @Transactional
    │
    ├── orderRepository.save() ── transaction A ── COMMIT
    │
    ├── inventoryRepository.save() ─ transaction B ─ COMMIT
    │
    └── auditRepository.save() ─── transaction C ── ERROR
                                                       │
                                                       ▼
                                  A và B đã commit, không rollback cùng nhau
```

Đây là lý do transaction boundary nên đặt ở use case khi nhiều thao tác phải thành công hoặc thất bại cùng nhau.

### 2.2. Nhiều repository có thể dùng chung một transaction

Điều kiện quan trọng là các repository tham gia cùng transaction manager và cùng DataSource. Spring JDBC transaction manager gắn connection với transaction hiện tại; Spring Data JDBC và JdbcTemplate dùng đúng DataSource có thể cùng tham gia connection đó.

Ví dụ service có thể kết hợp:

- Spring Data JDBC repository.
- Repository khác cũng dùng Spring Data JDBC.
- JdbcTemplate dùng cùng DataSource.
- DAO tự viết dùng cơ chế transaction-aware của Spring.

Không phải số lượng repository quyết định số transaction. Một transaction có thể bao gồm nhiều repository và nhiều bảng nếu chúng cùng tham gia cùng transaction resource.

## 3. Ví dụ model cho test rollback

Các ví dụ sau dùng ba bảng: purchase_order, inventory_item và order_audit. Schema PostgreSQL minh họa:

```sql
CREATE TABLE inventory_item (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(50) NOT NULL UNIQUE,
    available_quantity INTEGER NOT NULL
);

CREATE TABLE purchase_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    sku VARCHAR(50) NOT NULL,
    quantity INTEGER NOT NULL,
    status VARCHAR(30) NOT NULL
);

CREATE TABLE order_audit (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    actor_id VARCHAR(80) NOT NULL
);
```

Repository:

```java
import java.util.Optional;
import org.springframework.data.repository.CrudRepository;

public interface InventoryRepository
        extends CrudRepository<InventoryItem, Long> {

    Optional<InventoryItem> findBySku(String sku);
}

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}

public interface OrderAuditRepository
        extends CrudRepository<OrderAudit, Long> {
}
```

Domain factory và method trong ví dụ:

```java
public record PlaceOrderCommand(
        Long customerId,
        String sku,
        int quantity,
        boolean failAfterInventoryUpdate
) {}

public record InventoryItem(
        @Id Long id,
        String sku,
        int availableQuantity
) {
    public InventoryItem decrease(int amount) {
        return new InventoryItem(
                id,
                sku,
                availableQuantity - amount
        );
    }
}

public record PurchaseOrder(
        @Id Long id,
        Long customerId,
        String sku,
        int quantity,
        String status
) {
    public static PurchaseOrder pending(
            Long customerId,
            String sku,
            int quantity) {
        return new PurchaseOrder(
                null, customerId, sku, quantity, "PENDING");
    }
}

public record OrderAudit(
        @Id Long id,
        Long orderId,
        String eventType,
        String actorId
) {
    public static OrderAudit created(Long orderId, Long customerId) {
        return new OrderAudit(
                null, orderId, "ORDER_CREATED", customerId.toString());
    }
}
```

Các import annotation và kiểu Spring Data có thể được gom vào file tương ứng của dự án. Ví dụ chỉ minh họa mapping tối thiểu; trong ứng dụng thật, cần áp dụng naming/schema mapping và validation domain phù hợp.

Để tạo lỗi có chủ đích sau khi hai repository đầu đã ghi, service có thể có một nhánh dành riêng cho test hoặc một collaborator có thể thay thế trong test:

```java
@Transactional
public PurchaseOrder placeOrder(PlaceOrderCommand command) {
    InventoryItem item = inventoryRepository.findBySku(command.sku())
            .orElseThrow();

    if (item.availableQuantity() < command.quantity()) {
        throw new IllegalStateException("Insufficient inventory");
    }

    PurchaseOrder order = orderRepository.save(
            PurchaseOrder.pending(
                    command.customerId(),
                    command.sku(),
                    command.quantity()
            )
    );

    inventoryRepository.save(item.decrease(command.quantity()));

    if (command.failAfterInventoryUpdate()) {
        throw new IllegalStateException("Simulated failure");
    }

    auditRepository.save(
            OrderAudit.created(order.id(), command.customerId())
    );

    return order;
}
```

Trong production, không nên để client gửi cờ tùy ý để gây lỗi. Có thể thay nhánh mô phỏng bằng một collaborator có thể mock trong test, hoặc tạo lỗi tự nhiên từ constraint/validation ở bước cuối. Mục tiêu là buộc transaction thất bại sau khi đã thực hiện một số lệnh ghi.

## 4. Test slice: @DataJdbcTest rollback test mặc định

`@DataJdbcTest` là test slice dành cho Spring Data JDBC. Nó cấu hình phần lớn hạ tầng cần thiết cho repository JDBC và mặc định chạy mỗi test trong transaction được rollback sau khi test kết thúc.

Ví dụ:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.jdbc.DataJdbcTest;

@DataJdbcTest
class PurchaseOrderRepositoryTest {

    @Autowired
    PurchaseOrderRepository orderRepository;

    @Autowired
    InventoryRepository inventoryRepository;

    @Test
    void repositoryWritesAreRolledBackAfterTest() {
        InventoryItem savedInventory = inventoryRepository.save(
                new InventoryItem(null, "SKU-CHAIR", 10)
        );

        PurchaseOrder savedOrder = orderRepository.save(
                PurchaseOrder.pending(100L, "SKU-CHAIR", 2)
        );

        assertThat(inventoryRepository.findById(savedInventory.id()))
                .isPresent();
        assertThat(orderRepository.findById(savedOrder.id()))
                .isPresent();
    }
}
```

Sau khi test hoàn tất, Spring TestContext rollback transaction mặc định. Test này hữu ích để kiểm tra mapping/repository mà không cần tự xóa dữ liệu fixture sau mỗi test.

### 4.1. Test rollback tự động không chứng minh service có transaction

Nếu test method có transaction do test framework tạo, service method có `@Transactional` với propagation mặc định REQUIRED sẽ tham gia transaction bên ngoài đó. Khi test kết thúc, transaction test bị rollback dù service method có transaction boundary hay không.

Vì vậy, một test `@DataJdbcTest` có thể xác nhận repository ghi dữ liệu đúng, nhưng chưa đủ để chứng minh một lời gọi service độc lập sẽ rollback toàn bộ các repository khi một bước thất bại.

Muốn kiểm tra đúng transaction boundary của service, hãy để transaction do service quản lý và quan sát database sau khi service đã kết thúc.

## 5. Integration test kiểm tra rollback thực sự của service

Dùng `@SpringBootTest` để nạp service, repository, DataSource và transaction configuration như ứng dụng. Với test này, **không đánh dấu chính test method là @Transactional**. Nếu test method tạo transaction bên ngoài, service có thể tham gia transaction đó và kết quả assertion không còn chứng minh transaction của service tự rollback.

Ví dụ:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class OrderServiceRollbackIntegrationTest {

    @Autowired
    OrderService orderService;

    @Autowired
    InventoryRepository inventoryRepository;

    @Autowired
    PurchaseOrderRepository orderRepository;

    @Autowired
    OrderAuditRepository auditRepository;

    @BeforeEach
    void setUp() {
        auditRepository.deleteAll();
        orderRepository.deleteAll();
        inventoryRepository.deleteAll();

        inventoryRepository.save(
                new InventoryItem(null, "SKU-CHAIR", 10)
        );
    }

    @Test
    void rollsBackAllRepositoryWritesWhenLaterStepFails() {
        assertThatThrownBy(() -> orderService.placeOrder(
                new PlaceOrderCommand(
                        100L,
                        "SKU-CHAIR",
                        2,
                        true
                )
        )).isInstanceOf(IllegalStateException.class)
          .hasMessage("Simulated failure");

        assertThat(orderRepository.count()).isZero();
        assertThat(auditRepository.count()).isZero();

        InventoryItem inventory = inventoryRepository
                .findBySku("SKU-CHAIR")
                .orElseThrow();

        assertThat(inventory.availableQuantity()).isEqualTo(10);
    }
}
```

Test thực hiện:

1. Tạo fixture inventory có số lượng 10.
2. Gọi service qua Spring bean/proxy.
3. Service insert order, cập nhật inventory rồi ném runtime exception.
4. Transaction của service rollback.
5. Test đọc lại database sau khi lời gọi service kết thúc.
6. Xác nhận order/audit không tồn tại và inventory trở về 10.

Vì test method không có transaction bao quanh, các truy vấn assertion đọc trạng thái đã được transaction service rollback. Đây là bằng chứng trực tiếp hơn cho rollback giữa nhiều repository.

### 5.1. Vì sao gọi service qua Spring bean quan trọng?

`@Transactional` thường được thực thi qua Spring AOP proxy. Nếu test tự tạo service bằng `new OrderService(...)`, annotation không tự tạo transaction. Tương tự, lời gọi một method transactional khác bên trong cùng instance (self-invocation) thường không đi qua proxy nên không kích hoạt transaction advice như mong đợi.

Trong integration test, inject service từ ApplicationContext và gọi qua bean đó. Tránh tự khởi tạo service trong test nếu mục tiêu là kiểm tra transaction behavior của Spring.

### 5.2. Dùng database nào?

Test slice có thể dùng embedded database nếu dependency và cấu hình cho phép. Tuy nhiên, nếu production dùng PostgreSQL/MySQL hoặc dựa vào dialect, constraint, isolation hay kiểu dữ liệu riêng, nên chạy integration test trên cùng loại database bằng Testcontainers hoặc môi trường test tương đương.

Rollback transaction là tính năng database phổ biến, nhưng hành vi SQL, foreign key, isolation, generated key và locking có thể khác giữa database engine. Một test với H2 không chứng minh đầy đủ behavior trên PostgreSQL hoặc MySQL.

## 6. Kiểm thử rollback khi có nhiều bảng trong một aggregate

Spring Data JDBC lưu aggregate root cùng các entity con thuộc aggregate. Ví dụ một đơn hàng có collection line:

```java
@Table("purchase_order")
public record PurchaseOrder(
        @Id Long id,
        Long customerId,
        String status,
        @MappedCollection(idColumn = "purchase_order_id")
        List<OrderLine> lines
) {}
```

Một lần insert aggregate có thể tạo hàng root và nhiều hàng child. Nếu sau khi lưu aggregate, một repository khác trong cùng transaction ném lỗi, cả hàng root và child đều phải rollback cùng các thay đổi ở bảng khác.

Test nên xác nhận cả root lẫn child:

```java
assertThat(orderRepository.count()).isZero();
assertThat(orderLineRepository.count()).isZero();
assertThat(inventoryRepository.findBySku("SKU-CHAIR")
        .orElseThrow()
        .availableQuantity()).isEqualTo(10);
```

Nếu child chỉ được quản lý qua aggregate root và không có repository riêng, có thể kiểm tra bằng query trực tiếp hoặc kiểm tra schema bằng JdbcTemplate. Điều quan trọng là xác nhận không còn hàng child mồ côi sau rollback.

## 7. Rollback rules: RuntimeException và checked exception

Theo mặc định, Spring rollback transaction khi method transactional kết thúc bằng `RuntimeException` hoặc `Error`. Checked exception không tự động kích hoạt rollback theo quy tắc mặc định.

Ví dụ runtime exception:

```java
@Transactional
public void createOrder() {
    orderRepository.save(...);
    throw new IllegalStateException("Failure");
}
```

Mặc định transaction rollback.

Nếu method ném checked exception:

```java
@Transactional
public void createOrder() throws IOException {
    orderRepository.save(...);
    throw new IOException("Cannot read input");
}
```

Theo mặc định, checked exception như IOException không thuộc rollback rule mặc định. Nếu muốn rollback, khai báo:

```java
@Transactional(rollbackFor = IOException.class)
public void createOrder() throws IOException {
    orderRepository.save(...);
    throw new IOException("Cannot read input");
}
```

Có thể dùng rollbackFor với một kiểu exception cha nếu muốn áp dụng cho một nhóm lỗi. Hãy chọn rule rõ ràng theo contract nghiệp vụ, không dùng rollbackFor quá rộng khi một số lỗi được xem là kết quả hợp lệ.

### 7.1. Bắt exception bên trong transactional method

Nếu method bắt exception rồi không ném lại, transaction interceptor có thể xem method đã kết thúc bình thường và commit:

```java
@Transactional
public void createOrder() {
    orderRepository.save(...);

    try {
        auditRepository.save(...);
    } catch (DataAccessException ex) {
        log.warn("Audit write failed", ex);
        // Method kết thúc bình thường: transaction có thể commit.
    }
}
```

Nếu lỗi phải làm rollback, có thể ném exception ra ngoài transaction boundary:

```java
@Transactional
public void createOrder() {
    orderRepository.save(...);

    try {
        auditRepository.save(...);
    } catch (DataAccessException ex) {
        throw new OrderCreationException("Cannot write audit", ex);
    }
}
```

Hoặc chủ động đánh dấu rollback-only qua transaction status phù hợp. Tuy nhiên, thường nên để exception phản ánh thất bại đi qua boundary và xử lý ở tầng gọi phía ngoài. Nếu exception bị bắt ở controller hoặc caller bên ngoài proxy, transaction interceptor đã có cơ hội áp dụng rollback rule.

## 8. Test-managed transaction và @Rollback/@Commit

Spring TestContext hỗ trợ transaction cho test bằng `@Transactional` trên test class hoặc method. Mặc định transaction test được rollback sau khi test kết thúc.

Ví dụ:

```java
@SpringBootTest
@Transactional
class OrderRepositoryTransactionalTest {

    @Test
    void writesAreRolledBackAfterTest() {
        // Test data access trong transaction của test.
    }
}
```

Các annotation thường gặp:

| Annotation | Ý nghĩa |
| --- | --- |
| `@Transactional` trên test | Chạy test trong test-managed transaction nếu test framework hỗ trợ |
| `@Rollback` | Chỉ định transaction test có rollback khi kết thúc hay không |
| `@Commit` | Yêu cầu commit transaction test khi kết thúc |
| `@Rollback(false)` | Tắt rollback mặc định và commit transaction test |

Ví dụ:

```java
@Test
@Commit
void commitsTestData() {
    // Dữ liệu được commit khi test kết thúc.
}
```

Hoặc:

```java
@Test
@Rollback(false)
void alsoCommitsTestData() {
    // Dùng khi cần kiểm soát commit tường minh.
}
```

Không bật commit chỉ để kiểm tra một thao tác rollback rồi để dữ liệu test tồn tại ngoài dự kiến. Nếu cần commit để xác nhận trạng thái qua connection khác, hãy quản lý fixture và cleanup rõ ràng.

### 8.1. Test transaction có thể che lỗi transaction boundary

Nếu test method đã có transaction, lời gọi service có propagation REQUIRED sẽ tham gia transaction test. Khi đó:

- Service có thể không mở transaction mới.
- Assertion trong test có thể vẫn nhìn thấy dữ liệu chưa commit.
- Test rollback cuối cùng có thể xóa mọi thay đổi dù service không có transaction boundary riêng.

Để xác nhận service rollback khi được gọi độc lập, dùng test không có `@Transactional` ở method/class, gọi service qua proxy, bắt exception rồi đọc lại dữ liệu sau lời gọi.

## 9. Transaction propagation và REQUIRES_NEW

Propagation quyết định một method transactional tham gia transaction hiện tại hay tạo transaction khác.

### 9.1. REQUIRED

Đây là propagation mặc định. Nếu đã có transaction, method tham gia transaction đó; nếu chưa có, Spring tạo transaction mới.

```java
@Transactional
public void placeOrder() {
    orderRepository.save(...);
    inventoryService.reserve(...); // REQUIRED mặc định
}
```

Nếu cả hai method dùng cùng transaction manager, thay đổi có thể rollback cùng nhau.

### 9.2. REQUIRES_NEW

`REQUIRES_NEW` luôn dùng một transaction độc lập. Transaction ngoài bị suspend trong khi transaction mới chạy:

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeAuditRecord(OrderAudit audit) {
    auditRepository.save(audit);
}
```

Nếu transaction audit commit thành công rồi transaction đặt hàng bên ngoài rollback, audit record vẫn tồn tại. Đây không phải hành vi rollback toàn bộ.

Điều này có thể hữu ích khi muốn lưu một bản ghi ghi nhận thất bại độc lập, nhưng không phù hợp nếu audit row phải tồn tại đúng khi đơn hàng được tạo thành công.

REQUIRES_NEW thường cần một connection khác trong khi transaction ngoài đang giữ connection. Nếu pool nhỏ và nhiều request lồng transaction như vậy, pool có thể cạn. Cần tính đến số connection và thời gian giữ transaction.

### 9.3. NESTED

`NESTED` có thể dùng savepoint trong transaction hiện tại nếu transaction manager và database hỗ trợ. Nó không phải một transaction độc lập được commit riêng như REQUIRES_NEW. Khả năng hỗ trợ và semantics phụ thuộc transaction manager/driver/database; hãy kiểm tra trước khi dựa vào nó.

## 10. Nhiều DataSource hoặc nhiều transaction manager

Một transaction JDBC cục bộ thường quản lý một DataSource. Nếu ứng dụng có hai DataSource:

```text
OrderRepository ── DataSource A ── Database A
AuditRepository ── DataSource B ── Database B
```

`@Transactional` dùng transaction manager của DataSource A không tự động làm transaction ở DataSource B rollback cùng nhau.

Với nhiều transaction manager, cần chỉ định manager đúng:

```java
@Transactional(transactionManager = "ordersTransactionManager")
public void placeOrder() {
    // Các repository tham gia ordersTransactionManager.
}
```

Nếu cần cập nhật nguyên tử nhiều database resource, cần kiến trúc phù hợp như JTA/XA khi hạ tầng hỗ trợ, hoặc thiết kế eventual consistency với saga/outbox. Không giả định hai DataSource trỏ cùng một server/database sẽ tự chia sẻ transaction.

Ngay cả khi hai DataSource dùng cùng JDBC URL, nếu chúng là hai pool/connection độc lập và hai transaction manager riêng, các thao tác không tự động tham gia cùng một local transaction.

## 11. Bất đồng bộ và side effect bên ngoài transaction

Transaction JDBC do Spring quản lý thường gắn với thread hiện tại. Một tác vụ chạy trên thread khác, ví dụ qua @Async, executor hoặc message listener, không tự tham gia transaction của thread gọi:

```text
Thread A: @Transactional service
   │
   ├── ghi order trong transaction A
   │
   └── submit async task ─────────────► Thread B
                                         │
                                         └── transaction/connection riêng
```

Nếu thread A rollback, thao tác database đã commit trong thread B không tự rollback theo. Tương tự, gửi email, gọi payment gateway hoặc publish message ra broker không thể được database rollback tự động.

Không thực hiện side effect bên ngoài trước khi transaction database có kết quả cuối cùng nếu nghiệp vụ yêu cầu chúng chỉ xảy ra sau commit. Có thể dùng transaction synchronization/after-commit event cho side effect đơn giản; với yêu cầu độ tin cậy cao, transactional outbox thường phù hợp hơn.

## 12. Transactional outbox cho message cần đồng bộ với database

Giả sử tạo đơn hàng phải publish sự kiện ORDER_CREATED. Nếu ghi database rồi gửi message:

1. Database commit thành công.
2. Ứng dụng chết trước khi gửi message.
3. Đơn hàng tồn tại nhưng consumer không nhận sự kiện.

Nếu gửi message trước rồi database rollback, consumer có thể nhận sự kiện cho đơn hàng không tồn tại.

Transactional outbox giải quyết bằng cách ghi domain data và outbox record trong cùng transaction:

```text
@Transactional
placeOrder()
    │
    ├── INSERT purchase_order
    ├── UPDATE inventory_item
    └── INSERT outbox_event
              │
              ▼
           COMMIT
              │
              ▼
Background publisher đọc outbox
              │
              ▼
         Publish message
              │
              ▼
       Đánh dấu đã gửi
```

Nếu transaction rollback, cả order, inventory và outbox record đều không tồn tại. Nếu commit thành công nhưng publisher tạm thời lỗi, outbox record vẫn còn để gửi lại.

Publisher cần xử lý gửi lặp (at-least-once) và consumer nên idempotent. Outbox không biến database và message broker thành một transaction phân tán; nó cung cấp cách đáng tin cậy để phối hợp eventual consistency.

## 13. Kiểm thử transaction bằng TransactionTemplate

Khi muốn kiểm soát transaction rõ ràng trong test hoặc code imperative, có thể dùng `TransactionTemplate`:

```java
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;

@Component
public class OrderWriter {

    private final TransactionTemplate transactionTemplate;
    private final PurchaseOrderRepository orderRepository;
    private final InventoryRepository inventoryRepository;

    public OrderWriter(
            TransactionTemplate transactionTemplate,
            PurchaseOrderRepository orderRepository,
            InventoryRepository inventoryRepository) {
        this.transactionTemplate = transactionTemplate;
        this.orderRepository = orderRepository;
        this.inventoryRepository = inventoryRepository;
    }

    public void writeThenFail(PurchaseOrder order, InventoryItem item) {
        transactionTemplate.executeWithoutResult(status -> {
            orderRepository.save(order);
            inventoryRepository.save(item);
            throw new IllegalStateException("Force rollback");
        });
    }
}
```

TransactionTemplate dùng transaction manager được inject và áp dụng rollback rules cho callback. Có thể đánh dấu rollback-only bằng status khi cần kết thúc callback mà không ném exception:

```java
transactionTemplate.executeWithoutResult(status -> {
    orderRepository.save(order);

    if (shouldAbort()) {
        status.setRollbackOnly();
    }
});
```

Trong ứng dụng Spring Data JDBC thông thường, `@Transactional` trên service thường dễ đọc hơn. TransactionTemplate hữu ích khi transaction boundary phải được điều khiển theo từng nhánh imperative hoặc trong một số test.

## 14. Cách thiết kế test rollback đáng tin cậy

Một test service-level nên xác nhận cả dữ liệu ban đầu lẫn trạng thái sau lỗi:

1. Dùng database test sạch hoặc tạo fixture xác định.
2. Seed dữ liệu trước khi gọi service, ví dụ inventory có 10 sản phẩm.
3. Gọi service Spring bean qua proxy, không tự khởi tạo bằng new.
4. Làm cho bước giữa hoặc cuối ném exception sau khi các lệnh ghi trước đã chạy.
5. Bắt exception ở test.
6. Đọc lại dữ liệu qua repository sau khi lời gọi service đã kết thúc.
7. Xác nhận mọi bảng trong transaction trở về trạng thái trước đó.
8. Không đặt @Transactional lên test nếu cần xác nhận transaction service tự rollback.
9. Dùng cùng DataSource/transaction manager cho tất cả repository cần rollback cùng nhau.
10. Chạy test trên database engine gần production khi phụ thuộc dialect, locking hoặc constraint.

### 14.1. Kiểm tra cả dữ liệu được giữ lại

Rollback không có nghĩa xóa toàn bộ database. Test cần xác nhận fixture ban đầu vẫn tồn tại:

```java
InventoryItem inventory = inventoryRepository.findBySku("SKU-CHAIR")
        .orElseThrow();

assertThat(inventory.availableQuantity()).isEqualTo(10);
assertThat(orderRepository.count()).isZero();
assertThat(auditRepository.count()).isZero();
```

Nếu chỉ kiểm tra order không tồn tại mà quên inventory, test có thể bỏ sót lỗi rollback một phần.

### 14.2. Kiểm tra số lượng hàng child

Nếu aggregate lưu child collection, kiểm tra cả hàng root và child. Một query kiểm tra trực tiếp có thể hữu ích:

```sql
SELECT COUNT(*)
FROM order_line
WHERE purchase_order_id = ?;
```

Sau rollback, số hàng phải là 0 nếu aggregate mới được tạo trong transaction thất bại. Với fixture có sẵn, so sánh đúng số hàng ban đầu thay vì luôn kỳ vọng 0.

## 15. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Order đã lưu nhưng inventory không rollback | Các repository chạy trong transaction riêng | Đặt @Transactional ở service và dùng cùng DataSource/manager |
| Test pass nhưng service production vẫn ghi một phần | Test method có transaction ngoài và rollback sau test | Viết integration test không có @Transactional ở test method |
| Exception xảy ra nhưng dữ liệu vẫn commit | Checked exception không nằm trong rollback rule hoặc exception đã bị bắt | Dùng rollbackFor phù hợp hoặc ném runtime exception qua boundary |
| Audit record vẫn còn sau khi order rollback | Audit method dùng REQUIRES_NEW | Xác nhận có thật sự cần transaction độc lập không |
| Service @Transactional không hoạt động | Gọi self-invocation hoặc service được tạo bằng new | Gọi qua Spring proxy bean |
| Repository dùng connection khác | Khác DataSource/transaction manager | Chuẩn hóa cấu hình và chỉ định transaction manager |
| Async task vẫn ghi dữ liệu sau rollback | Thread khác có transaction riêng | Truyền command sau commit hoặc dùng outbox |
| Message đã gửi nhưng database rollback | Publish trước commit | Dùng after-commit hoặc transactional outbox |
| Test data còn lại sau test | Dùng @Commit/@Rollback(false) hoặc test không rollback | Kiểm tra annotation và cleanup fixture |
| Rollback test làm mất dữ liệu setup | Setup chạy trong cùng test-managed transaction | Dùng fixture ngoài transaction hoặc thiết kế setup/cleanup rõ ràng |
| H2 pass nhưng database production fail | SQL/constraint/transaction semantics khác nhau | Chạy integration test trên database mục tiêu |
| Connection pool cạn với REQUIRES_NEW | Transaction ngoài giữ connection trong khi transaction mới cần connection khác | Giảm nesting, tăng ngân sách pool có kiểm chứng hoặc đổi thiết kế |

## 16. Bài tập thực hành

**Bài 1 — Một service, hai repository.** Tạo service có @Transactional, lưu order và cập nhật inventory. Cố ý ném IllegalStateException sau hai thao tác, rồi xác nhận cả hai thay đổi rollback.

**Bài 2 — Thêm bảng audit.** Ghi OrderAudit qua repository thứ ba. Làm lỗi ở bước audit và xác nhận order, inventory và audit đều giữ trạng thái ban đầu.

**Bài 3 — Aggregate có child.** Lưu PurchaseOrder cùng OrderLine collection, sau đó làm một repository khác thất bại. Kiểm tra cả root và child đã rollback.

**Bài 4 — So sánh test transaction.** Viết một test @SpringBootTest có @Transactional và một test không có. Giải thích vì sao test thứ hai chứng minh service rollback độc lập tốt hơn.

**Bài 5 — Checked exception.** Thay runtime exception bằng IOException. Quan sát behavior mặc định, sau đó thêm rollbackFor và xác nhận dữ liệu được rollback.

**Bài 6 — Exception bị bắt.** Bắt DataAccessException trong service và không ném lại. Quan sát transaction có thể commit; sau đó sửa để rollback và kiểm thử lại.

**Bài 7 — REQUIRES_NEW.** Tạo audit method dùng REQUIRES_NEW. Làm transaction order rollback và quan sát audit record vẫn commit. Giải thích khi nào hành vi đó có ích.

**Bài 8 — Nhiều DataSource.** Cấu hình hai datasource và hai transaction manager. Xác nhận transaction local không tự rollback thao tác ở datasource còn lại; tìm hiểu giải pháp phù hợp cho nghiệp vụ.

**Bài 9 — Async side effect.** Gọi một tác vụ @Async từ service transactional. Quan sát thread khác không tự tham gia transaction của caller. Thiết kế lại bằng outbox hoặc after-commit.

**Bài 10 — TransactionTemplate.** Viết test dùng TransactionTemplate, đánh dấu rollback-only và xác nhận dữ liệu không được commit.

**Bài 11 — Database production-like.** Chạy test rollback với PostgreSQL/MySQL bằng Testcontainers. So sánh behavior với embedded database nếu dự án có dùng.

**Bài 12 — Transactional outbox.** Ghi order và outbox event trong một transaction. Làm lỗi sau khi ghi outbox để xác nhận cả hai rollback; sau đó commit và mô phỏng publisher gửi event.

### Tài liệu tham khảo

- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): @Transactional, proxy và rollback rules.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): REQUIRED, REQUIRES_NEW và NESTED.
- [Spring Framework — Transaction-bound Resources](https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-resource-synchronization.html): connection/resource gắn với transaction.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/index.html): test slices và integration test.
- [Spring Framework — TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): test-managed transaction, rollback và commit.
- [Spring Data Relational Reference](https://docs.spring.io/spring-data/relational/reference/): transaction và persistence trong Spring Data JDBC.
