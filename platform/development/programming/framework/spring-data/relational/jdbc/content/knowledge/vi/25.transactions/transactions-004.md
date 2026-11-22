# Phối hợp nhiều repository trong cùng một giao dịch

Trong một use case nghiệp vụ, ứng dụng thường phải thay đổi nhiều aggregate thông qua nhiều repository. Ví dụ, khi đặt hàng, hệ thống vừa giảm số lượng tồn kho vừa tạo đơn hàng. Nếu thao tác giảm tồn kho thành công nhưng lưu đơn hàng thất bại, dữ liệu có thể rơi vào trạng thái không nhất quán.

Spring Data JDBC sử dụng transaction management của Spring JDBC. Để nhiều lời gọi repository cùng thành công hoặc cùng rollback, hãy đặt **ranh giới giao dịch ở service/facade bao quanh toàn bộ use case** bằng §@Transactional§.

Khi các repository cùng sử dụng một §DataSource§ và cùng một transaction manager JDBC, các thao tác của chúng có thể tham gia cùng transaction. Mặc định §Propagation.REQUIRED§ sẽ tạo transaction nếu chưa có hoặc tham gia transaction đang tồn tại.

Bài học giải thích cách phối hợp nhiều repository trong một transaction, vai trò của service, cách rollback hoạt động, các giới hạn khi dùng nhiều transaction manager hoặc nhiều database và những lỗi thường gặp.

## 1. Vì sao cần transaction bao quanh nhiều repository?

Giả sử một use case đặt hàng phải thực hiện hai thao tác:

1. Trừ số lượng tồn kho trong aggregate §InventoryItem§.
2. Tạo aggregate §PurchaseOrder§.

Hai aggregate có repository riêng:

~~~text
PlaceOrderService
       |
       +---- InventoryRepository
       |          |
       |          +---- inventory_items
       |
       +---- PurchaseOrderRepository
                  |
                  +---- purchase_orders
~~~

Nếu mỗi repository call tự chạy transaction riêng, có thể xảy ra:

~~~text
Transaction A: InventoryRepository.save(...)
    COMMIT

Transaction B: PurchaseOrderRepository.save(...)
    ERROR
    ROLLBACK

Kết quả:
    Tồn kho đã bị trừ
    Đơn hàng chưa được tạo
~~~

Đây là trạng thái sai đối với nghiệp vụ đặt hàng. Hệ thống đã giữ hàng nhưng không có đơn hàng tương ứng.

Một transaction bao quanh cả hai thao tác sẽ cho kết quả:

~~~text
PlaceOrderService.placeOrder(...)
    BEGIN

    InventoryRepository.save(...)
    PurchaseOrderRepository.save(...)

    COMMIT nếu toàn bộ thành công
    ROLLBACK nếu lỗi làm transaction rollback
~~~

Nếu thao tác tạo đơn hàng thất bại, thay đổi tồn kho chưa commit cũng được rollback.

**Repository quản lý thao tác persistence của từng aggregate; service quản lý ranh giới transaction của một use case có nhiều bước.**

## 2. Spring Data JDBC quản lý transaction như thế nào?

Spring Data JDBC sử dụng hạ tầng transaction của Spring JDBC. Với một ứng dụng JDBC thông thường, các thành phần quan trọng là:

- §DataSource§: cung cấp kết nối đến database.
- §PlatformTransactionManager§: quản lý transaction cho resource.
- §JdbcTransactionManager§ hoặc §DataSourceTransactionManager§: transaction manager cho JDBC.
- Repository và §JdbcAggregateTemplate§: thực hiện thao tác đọc/ghi bằng JDBC.
- §@Transactional§: khai báo ranh giới transaction ở service hoặc repository.

Với một database và một §DataSource§, kiến trúc thường là:

~~~text
                    Spring Application
                            |
                            v
                   PlaceOrderService
                     @Transactional
                            |
             +--------------+--------------+
             |                             |
             v                             v
      InventoryRepository          OrderRepository
             |                             |
             +--------------+--------------+
                            |
                            v
                    JDBC infrastructure
                            |
                  PlatformTransactionManager
                            |
                            v
                         DataSource
                            |
                            v
                         Database
~~~

Transaction manager gắn kết nối JDBC với transaction hiện tại. Các thao tác JDBC sử dụng cùng resource và transaction manager có thể tham gia transaction đó thay vì tự commit độc lập.

### 2.1. Điều kiện để nhiều repository cùng transaction

Thông thường cần bảo đảm:

1. Các repository sử dụng cùng database resource, tức cùng §DataSource§ hoặc cùng resource được transaction manager quản lý.
2. Các repository được cấu hình với cùng transaction manager JDBC.
3. Service mở transaction bằng transaction manager đó.
4. Các lời gọi repository diễn ra trong cùng transaction context, thường là cùng thread trong ứng dụng Spring imperative.
5. Các thao tác không tự mở transaction độc lập bằng propagation khác.

Việc hai repository cùng nằm trong một package hoặc cùng kế thừa §CrudRepository§ không đủ để bảo đảm chúng tham gia cùng transaction. Điều quyết định là resource và transaction manager mà chúng sử dụng.

Nếu hai repository truy cập hai schema khác nhau nhưng cùng một database connection/resource, chúng vẫn có thể tham gia cùng transaction. Nếu chúng dùng hai database và hai §DataSource§ độc lập, một JDBC transaction manager thông thường không thể tự biến chúng thành một transaction nguyên tử duy nhất.

## 3. Đặt @Transactional ở service/facade

Ví dụ đơn giản:

~~~java
@Service
public class OrderManagementService {

    private final InventoryRepository inventoryRepository;
    private final PurchaseOrderRepository orderRepository;

    public OrderManagementService(
            InventoryRepository inventoryRepository,
            PurchaseOrderRepository orderRepository
    ) {
        this.inventoryRepository = inventoryRepository;
        this.orderRepository = orderRepository;
    }

    @Transactional
    public PurchaseOrder placeOrder(
            String sku,
            int quantity
    ) {
        InventoryItem item = inventoryRepository.findBySku(sku)
                .orElseThrow();

        item.reserve(quantity);
        inventoryRepository.save(item);

        PurchaseOrder order = new PurchaseOrder(
                null,
                sku,
                quantity,
                "PLACED"
        );

        return orderRepository.save(order);
    }
}
~~~

§@Transactional§ bao quanh toàn bộ lời gọi §placeOrder§. Khi method được gọi qua Spring transaction proxy:

- Transaction bắt đầu trước khi thân method chạy nếu chưa có transaction hiện tại.
- Các lời gọi repository bên trong tham gia transaction đó.
- Nếu method hoàn tất bình thường, transaction được commit.
- Nếu có lỗi thuộc quy tắc rollback, transaction được rollback.

Không cần đặt một §@Transactional§ riêng quanh từng câu lệnh repository trong service này.

### 3.1. Vì sao đặt transaction ở service?

Một repository thường đại diện cho thao tác persistence của một aggregate. Một use case nghiệp vụ có thể cần nhiều repository.

Ví dụ:

| Use case | Repository tham gia |
| --- | --- |
| Đặt hàng | §InventoryRepository§, §PurchaseOrderRepository§ |
| Tạo tài khoản và hồ sơ | §AccountRepository§, §ProfileRepository§ |
| Chuyển tiền | §WalletRepository§, §LedgerRepository§ |
| Phân quyền người dùng | §UserRepository§, §RoleRepository§ |
| Hoàn tất đơn hàng | §PurchaseOrderRepository§, §ShipmentRepository§ |

Service biết các bước nào phải cùng thành công. Vì vậy, service là nơi tự nhiên để khai báo transaction boundary.

Nếu chỉ đặt transaction trên từng repository method, mỗi lần gọi có thể có một transaction độc lập khi không có transaction bên ngoài. Khi đó, thao tác thứ hai thất bại không nhất thiết rollback thao tác thứ nhất đã commit.

## 4. Ví dụ đầy đủ: đặt hàng và giữ tồn kho

Ta xây dựng hai aggregate root độc lập:

- §InventoryItem§ quản lý số lượng tồn kho của một SKU.
- §PurchaseOrder§ quản lý đơn hàng.

Cả hai dùng chung database và transaction manager.

### 4.1. InventoryItem aggregate

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Table("inventory_items")
public record InventoryItem(
        @Id Long id,
        String sku,
        int availableQuantity,
        @Version Long version
) {

    public InventoryItem reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Quantity must be positive"
            );
        }

        if (availableQuantity < quantity) {
            throw new InsufficientStockException(sku);
        }

        return new InventoryItem(
                id,
                sku,
                availableQuantity - quantity,
                version
        );
    }
}
~~~

§@Version§ cho phép Spring Data JDBC phát hiện một số trường hợp aggregate bị cập nhật cạnh tranh. Nếu một transaction khác đã thay đổi version sau khi aggregate được đọc, thao tác save có thể thất bại do optimistic locking.

Ngoại lệ nghiệp vụ:

~~~java
public class InsufficientStockException
        extends RuntimeException {

    public InsufficientStockException(String sku) {
        super("Insufficient stock for SKU: " + sku);
    }
}
~~~

### 4.2. PurchaseOrder aggregate

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public record PurchaseOrder(
        @Id Long id,
        String sku,
        int quantity,
        String status
) {
}
~~~

### 4.3. Repository

~~~java
import java.util.Optional;

import org.springframework.data.repository.CrudRepository;

public interface InventoryRepository
        extends CrudRepository<InventoryItem, Long> {

    Optional<InventoryItem> findBySku(String sku);
}
~~~

~~~java
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

Hai repository có thể độc lập về mặt domain nhưng cùng sử dụng transaction manager và database resource.

### 4.4. Service điều phối hai repository

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PlaceOrderService {

    private final InventoryRepository inventoryRepository;
    private final PurchaseOrderRepository orderRepository;

    public PlaceOrderService(
            InventoryRepository inventoryRepository,
            PurchaseOrderRepository orderRepository
    ) {
        this.inventoryRepository = inventoryRepository;
        this.orderRepository = orderRepository;
    }

    @Transactional
    public PurchaseOrder placeOrder(
            String sku,
            int quantity
    ) {
        InventoryItem inventory =
                inventoryRepository.findBySku(sku)
                        .orElseThrow();

        InventoryItem reserved = inventory.reserve(quantity);

        inventoryRepository.save(reserved);

        PurchaseOrder order = new PurchaseOrder(
                null,
                sku,
                quantity,
                "PLACED"
        );

        return orderRepository.save(order);
    }
}
~~~

Transaction bao quanh cả thao tác đọc tồn kho, cập nhật tồn kho và tạo đơn hàng.

### 4.5. Điều gì xảy ra khi có lỗi?

Giả sử tồn kho đủ, nhưng thao tác insert đơn hàng vi phạm một constraint:

~~~text
placeOrder("SKU-01", 2)
       |
       v
BEGIN
       |
       v
SELECT inventory_items
       |
       v
UPDATE inventory_items
       |
       v
INSERT purchase_orders
       |
       v
Database báo lỗi
       |
       v
ROLLBACK
       |
       +---- thay đổi inventory_items bị hoàn tác
       |
       +---- purchase_orders không được tạo
~~~

Database chỉ xác nhận các thay đổi khi transaction commit. Việc repository method trả về một object sau lệnh ghi không có nghĩa transaction bên ngoài đã commit; commit diễn ra khi transaction boundary kết thúc.

## 5. Repository CRUD mặc định và query methods

Spring Data JDBC cấu hình các phương thức CRUD của repository theo transaction mặc định:

- Các thao tác đọc CRUD có cờ §readOnly = true§.
- Các thao tác ghi CRUD sử dụng §@Transactional§ với cấu hình mặc định.

Tuy nhiên, các query method tự khai báo cần được chú ý riêng. Tài liệu Spring Data Relational khuyến nghị đánh dấu query methods là transactional, thường bằng §@Transactional(readOnly = true)§ ở repository interface hoặc đặt chúng bên trong transaction service.

Ví dụ:

~~~java
import java.util.List;

import org.springframework.data.repository.CrudRepository;
import org.springframework.transaction.annotation.Transactional;

@Transactional(readOnly = true)
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    List<Customer> findByStatus(String status);
}
~~~

Nếu query method được gọi từ một service đang có transaction, nó sẽ tham gia transaction bên ngoài theo propagation mặc định.

### 5.1. Vì sao query method cũng cần transaction?

Một truy vấn aggregate của Spring Data JDBC có thể cần nhiều câu SQL để tải root và các entity được sở hữu bên trong aggregate.

Nếu không có một transaction chung, các câu query để tải một aggregate có thể được thực thi trên các connection khác nhau. Điều này có thể:

- Làm tăng áp lực lên connection pool.
- Khiến các câu truy vấn trong cùng một lần đọc không cùng transaction context.
- Tăng nguy cơ deadlock khi nhiều thao tác giữ connection rồi yêu cầu thêm connection.

Đặt transaction ở service hoặc query method giúp các câu truy vấn cần thiết tham gia một transaction chung.

### 5.2. Cấu hình readOnly không phải hàng rào bảo mật

§@Transactional(readOnly = true)§ thể hiện rằng use case dự kiến chỉ đọc. Đây thường là hint được truyền đến transaction manager/JDBC driver để tối ưu.

Không nên coi §readOnly = true§ là một cơ chế kiểm tra chắc chắn rằng code không thể thực hiện INSERT hoặc UPDATE. Hành vi cụ thể phụ thuộc database và driver; một số database có thể từ chối ghi trong read-only transaction.

Nếu service có cả đọc và ghi, hãy dùng transaction read-write mặc định.

## 6. Transaction propagation: REQUIRED và REQUIRES_NEW

Thuộc tính §propagation§ xác định một method xử lý thế nào khi đã có transaction hiện tại.

### 6.1. REQUIRED là mặc định

§Propagation.REQUIRED§ có hai hành vi:

- Nếu chưa có transaction, tạo transaction mới.
- Nếu đã có transaction, tham gia transaction hiện tại.

Ví dụ:

~~~java
@Service
public class InventoryService {

    private final InventoryRepository inventoryRepository;

    public InventoryService(
            InventoryRepository inventoryRepository
    ) {
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public void reserve(String sku, int quantity) {
        // Đọc và cập nhật tồn kho
    }
}
~~~

Service điều phối:

~~~java
@Service
public class OrderService {

    private final InventoryService inventoryService;
    private final PurchaseOrderRepository orderRepository;

    public OrderService(
            InventoryService inventoryService,
            PurchaseOrderRepository orderRepository
    ) {
        this.inventoryService = inventoryService;
        this.orderRepository = orderRepository;
    }

    @Transactional
    public void placeOrder(String sku, int quantity) {
        inventoryService.reserve(sku, quantity);
        orderRepository.save(
                new PurchaseOrder(null, sku, quantity, "PLACED")
        );
    }
}
~~~

Nếu lời gọi §inventoryService.reserve§ đi qua Spring proxy và dùng cùng transaction manager, transaction của InventoryService tham gia transaction đang được OrderService mở. Lỗi ở bước lưu đơn hàng có thể rollback cả thay đổi tồn kho.

### 6.2. REQUIRES_NEW tạo transaction độc lập

§Propagation.REQUIRES_NEW§ luôn tạo một physical transaction mới. Transaction bên ngoài bị suspend trong thời gian transaction bên trong chạy.

Ví dụ:

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordAuditEvent(AuditEvent event) {
    auditRepository.save(event);
}
~~~

Nếu audit được lưu trong transaction REQUIRES_NEW và commit thành công, sau đó transaction đặt hàng bên ngoài rollback thì audit vẫn tồn tại.

Đây là hành vi khác với §REQUIRED§.

Chỉ dùng REQUIRES_NEW khi thực sự muốn kết quả bên trong commit độc lập với transaction bên ngoài. Nếu mục tiêu là tạo đơn hàng và giảm tồn kho cùng thành công hoặc cùng thất bại, không dùng REQUIRES_NEW cho một trong hai thao tác.

**REQUIRES_NEW cũng cần thêm connection/resource trong khi transaction ngoài đang giữ resource.** Dưới tải đồng thời, connection pool không đủ lớn có thể gây cạn connection hoặc deadlock.

### 6.3. NESTED và savepoint

§Propagation.NESTED§ có thể dùng một transaction vật lý với savepoint để rollback một phần thao tác bên trong trong khi transaction ngoài tiếp tục.

Với JDBC, cơ chế này thường dựa trên savepoint. Khả năng sử dụng phụ thuộc transaction manager, database và cấu hình hỗ trợ savepoint. Không nên mặc định mọi database hoặc mọi transaction manager đều hỗ trợ giống nhau.

Nếu không có yêu cầu rollback từng phần rõ ràng, §REQUIRED§ thường là lựa chọn đơn giản hơn cho use case nhiều repository.

### 6.4. Bảng so sánh propagation

| Propagation | Khi chưa có transaction | Khi đã có transaction | Rollback độc lập? |
| --- | --- | --- | --- |
| §REQUIRED§ | Tạo transaction | Tham gia transaction hiện tại | Không |
| §REQUIRES_NEW§ | Tạo transaction mới | Suspend transaction ngoài, tạo transaction mới | Có |
| §NESTED§ | Tạo transaction | Dùng savepoint trong transaction hiện tại nếu được hỗ trợ | Rollback đến savepoint |

## 7. Quy tắc rollback

Mặc định của Spring declarative transaction:

- §RuntimeException§ làm transaction rollback.
- §Error§ làm transaction rollback.
- Checked exception không tự động làm rollback theo quy tắc mặc định.

Ví dụ ngoại lệ runtime:

~~~java
@Transactional
public void placeOrder(...) {
    inventoryRepository.save(...);

    throw new InsufficientStockException("SKU-01");
}
~~~

Transaction được rollback vì §InsufficientStockException§ kế thừa §RuntimeException§.

### 7.1. Checked exception và rollbackFor

Nếu method ném checked exception nhưng nghiệp vụ yêu cầu rollback, khai báo rõ:

~~~java
@Transactional(rollbackFor = Exception.class)
public void importOrders() throws IOException {
    // Ghi qua nhiều repository
}
~~~

Có thể chỉ định loại checked exception cụ thể thay vì rollback với mọi §Exception§.

Không nên đổi toàn bộ checked exception thành runtime chỉ để ép rollback nếu việc phân loại lỗi có ý nghĩa với API hoặc domain.

### 7.2. Bắt exception rồi không ném lại

Ví dụ:

~~~java
@Transactional
public void placeOrder(...) {
    try {
        inventoryRepository.save(...);
        orderRepository.save(...);
    } catch (DataAccessException ex) {
        log.error("Cannot place order", ex);
        // Không ném lại và không đánh dấu rollback-only
    }
}
~~~

Nếu exception bị bắt và method kết thúc bình thường, transaction interceptor có thể xem method đã thành công và commit các thay đổi trước đó.

Nếu cần rollback, hãy:

- Ném lại exception để transaction interceptor nhận biết.
- Hoặc chủ động đánh dấu transaction rollback-only trong trường hợp cần xử lý exception tại chỗ.

Ví dụ ném lại:

~~~java
@Transactional
public void placeOrder(...) {
    try {
        inventoryRepository.save(...);
        orderRepository.save(...);
    } catch (DataAccessException ex) {
        log.error("Cannot place order", ex);
        throw ex;
    }
}
~~~

Việc log lỗi không thay thế quyết định rollback. Hãy xác định rõ lỗi nào phải hủy toàn bộ use case và lỗi nào được phép xử lý để tiếp tục.

### 7.3. Inner transaction đánh dấu rollback-only

Khi một method tham gia transaction hiện tại và đánh dấu transaction rollback-only, outer method không thể ép transaction commit chỉ bằng cách bắt exception bên trong.

Nếu outer method kết thúc bình thường nhưng transaction đã bị đánh dấu rollback-only, Spring có thể ném §UnexpectedRollbackException§ tại thời điểm commit để thông báo rằng transaction thực tế đã rollback.

## 8. Transaction proxy và self-invocation

§@Transactional§ trong chế độ proxy hoạt động khi lời gọi method đi qua Spring proxy.

Ví dụ:

~~~java
@Service
public class OrderService {

    public void submit() {
        placeOrder(); // Self-invocation
    }

    @Transactional
    public void placeOrder() {
        // ...
    }
}
~~~

Lời gọi §placeOrder()§ từ chính instance đó không đi qua proxy, vì vậy annotation trên method có thể không được áp dụng như mong đợi.

Cách rõ ràng hơn là để một bean khác gọi method transactional:

~~~java
@Service
public class OrderService {

    @Transactional
    public void placeOrder() {
        // Nhiều repository calls
    }
}

@Component
public class OrderJob {

    private final OrderService orderService;

    public OrderJob(OrderService orderService) {
        this.orderService = orderService;
    }

    public void run() {
        orderService.placeOrder();
    }
}
~~~

Khi §OrderJob§ gọi bean §OrderService§ qua Spring proxy, transaction interceptor có thể mở transaction.

Nếu ứng dụng không dùng Spring Boot auto-configuration cho transaction, cần bật annotation-driven transaction management bằng §@EnableTransactionManagement§ hoặc cấu hình tương ứng.

## 9. Chọn đúng transaction manager

Trong ứng dụng đơn giản, thường có một transaction manager tên §transactionManager§ và §@Transactional§ sẽ dùng nó theo mặc định.

Nếu có nhiều transaction manager, có thể chỉ định rõ:

~~~java
@Transactional("ordersTransactionManager")
public void placeOrder(...) {
    // ...
}
~~~

Hoặc:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public void placeOrder(...) {
    // ...
}
~~~

Tên được chỉ định phải khớp bean transaction manager thực tế.

### 9.1. Repository phải dùng đúng manager

Khi cấu hình nhiều nhóm repository bằng §@EnableJdbcRepositories§, thuộc tính §transactionManagerRef§ có thể xác định transaction manager mà nhóm repository đó sử dụng.

Ví dụ:

~~~java
@EnableJdbcRepositories(
        basePackages = "com.example.orders.repository",
        transactionManagerRef = "ordersTransactionManager"
)
@Configuration
public class OrdersRepositoryConfiguration {
}
~~~

Service dùng transaction manager tương ứng:

~~~java
@Transactional("ordersTransactionManager")
public void placeOrder(...) {
    // Order repositories
}
~~~

Nếu service chọn transaction manager khác với repository, các repository có thể không tham gia cùng transaction như mong đợi.

## 10. Nhiều repository nhưng một database và nhiều database

Đây là khác biệt cần hiểu rõ.

### 10.1. Nhiều repository, cùng DataSource

~~~text
Repository A ----+
                 |
Repository B ----+----> Same DataSource
                 |          |
Repository C ----+          v
                       One JDBC transaction
~~~

Một transaction manager JDBC quản lý cùng DataSource có thể phối hợp các repository. Đây là trường hợp phổ biến và đơn giản nhất.

### 10.2. Nhiều repository, nhiều schema nhưng cùng resource

Nếu các schema nằm trong cùng một database connection và transaction manager quản lý cùng resource đó, chúng có thể tham gia cùng transaction.

Cần xác nhận quyền truy cập schema, SQL qualification và cấu hình datasource, nhưng ranh giới transaction vẫn có thể là một.

### 10.3. Nhiều repository, nhiều DataSource

~~~text
OrderRepository ----> ordersDataSource
                         |
                         v
                  ordersTransactionManager

AccountRepository --> accountDataSource
                         |
                         v
                  accountTransactionManager
~~~

Một §DataSourceTransactionManager§ hoặc §JdbcTransactionManager§ thông thường chỉ quản lý resource của nó. Đặt §@Transactional§ trên một service không tự động tạo transaction nguyên tử cho cả hai database.

Nếu service gọi hai repository thuộc hai transaction manager độc lập:

- Transaction của database thứ nhất có thể commit.
- Transaction của database thứ hai có thể thất bại.
- Không có rollback tự động xuyên cả hai resource chỉ nhờ một annotation §@Transactional§ thông thường.

Nếu yêu cầu atomic commit thực sự qua nhiều resource, cần một giải pháp distributed transaction phù hợp như JTA/XA với resource và driver hỗ trợ. Đây là lựa chọn có chi phí cấu hình và vận hành đáng kể.

Trong nhiều hệ thống microservice, người ta dùng Saga, transactional outbox và cơ chế bù trừ thay vì cố kéo một transaction JDBC qua nhiều service hoặc database.

## 11. Không mở transaction JDBC để bao quanh lời gọi HTTP

Một transaction JDBC chỉ quản lý các resource mà transaction manager tương ứng kiểm soát. Nó không thể rollback một thao tác đã xảy ra ở hệ thống bên ngoài qua HTTP.

Ví dụ:

~~~java
@Transactional
public void placeOrder(...) {
    inventoryRepository.save(...);
    paymentClient.charge(...);
    orderRepository.save(...);
}
~~~

Nếu §paymentClient.charge§ đã trừ tiền thành công nhưng §orderRepository.save§ thất bại, rollback database không thể tự hoàn tiền ở payment provider.

Ngoài ra, giữ database transaction mở trong lúc chờ HTTP có thể giữ connection và lock lâu, làm giảm khả năng phục vụ request khác.

Một cách thiết kế thường gặp:

1. Trong một database transaction, cập nhật tồn kho và tạo đơn hàng ở trạng thái chờ.
2. Ghi một outbox event trong cùng transaction.
3. Commit transaction.
4. Worker đọc outbox và gọi payment provider.
5. Cập nhật trạng thái thanh toán/đơn hàng bằng transaction mới.
6. Retry hoặc chạy quy trình bù trừ nếu hệ thống bên ngoài thất bại.

Sơ đồ:

~~~text
Database transaction
  +-- reserve inventory
  +-- create pending order
  +-- insert outbox event
             |
             v
           COMMIT
             |
             v
       Outbox publisher
             |
             v
       Payment provider
             |
             v
       Update order status
~~~

Transactional outbox bảo đảm sự kiện cần gửi được lưu cùng thay đổi database. Nó không làm HTTP trở thành một phần của transaction JDBC; nó tạo một quy trình giao tiếp bền vững sau commit.

## 12. Transaction trong luồng bất đồng bộ và nhiều thread

Spring transaction JDBC thường gắn với thread hiện tại. Không nên giả định transaction tự truyền sang:

- Method được gọi qua §@Async§.
- Task gửi vào executor.
- Thread được tạo thủ công.
- Một job chạy độc lập.
- HTTP request hoặc service khác.

Ví dụ:

~~~java
@Transactional
public void placeOrder() {
    inventoryRepository.save(...);

    asyncService.createOrderAsync();
}
~~~

Nếu §createOrderAsync§ chạy ở thread khác, nó không tự tham gia transaction JDBC của thread gọi. Nó có thể chạy trong transaction riêng hoặc không có transaction tùy cấu hình method đích.

Nếu cần cùng một transaction nguyên tử, hãy thực hiện các thao tác JDBC cần thiết trong cùng transaction context. Nếu công việc cần chạy bất đồng bộ sau commit, hãy dùng event/outbox và transaction riêng cho worker.

## 13. Đọc nhất quán khi phối hợp repository

Transaction không chỉ dành cho ghi. Một service có thể cần đọc từ nhiều repository để tạo một quyết định nghiệp vụ.

Ví dụ:

~~~java
@Transactional(readOnly = true)
public OrderSummary getOrderSummary(Long orderId) {
    PurchaseOrder order = orderRepository.findById(orderId)
            .orElseThrow();

    Customer customer = customerRepository.findById(order.customerId())
            .orElseThrow();

    return new OrderSummary(
            order.id(),
            customer.name(),
            order.status()
    );
}
~~~

Transaction chung giúp các thao tác đọc tham gia cùng transaction context và tránh mỗi repository tự lấy một transaction độc lập.

Tuy nhiên, **transaction không mặc định đồng nghĩa với snapshot isolation**. Isolation level thực tế do transaction manager/database quyết định. Nếu nghiệp vụ cần đọc nhất quán dưới mức thay đổi đồng thời cụ thể, hãy xem xét isolation level, locking hoặc optimistic version phù hợp.

### 13.1. readOnly = true

Đối với use case chỉ đọc, có thể dùng:

~~~java
@Transactional(readOnly = true)
public OrderSummary getOrderSummary(Long orderId) {
    // Đọc từ nhiều repository
}
~~~

Cờ read-only là hint cho transaction infrastructure/driver. Nó không thay thế kiểm soát quyền ghi và không bảo đảm mọi database sẽ từ chối thao tác thay đổi.

## 14. Transaction timeout và transaction dài

Một transaction bao quanh nhiều repository có thể trở nên dài nếu service thực hiện:

- Lặp qua hàng nghìn aggregate.
- Gọi dịch vụ bên ngoài.
- Chờ người dùng hoặc chờ message.
- Thực hiện xử lý CPU nặng.
- Giữ lock trong thời gian dài.

Transaction dài có thể giữ connection, lock và tài nguyên database lâu hơn cần thiết.

Có thể đặt timeout:

~~~java
@Transactional(timeout = 10)
public void placeOrder(...) {
    // Các thao tác cần hoàn tất trong giới hạn phù hợp
}
~~~

Timeout được hỗ trợ và thực thi cụ thể phụ thuộc transaction manager/database. Nếu timeout xảy ra, transaction infrastructure có thể đánh dấu rollback hoặc ném lỗi khi truy cập/commit.

Với batch lớn, có thể chia công việc thành các chunk nhỏ, mỗi chunk có transaction riêng. Khi đó, mỗi chunk có thể commit độc lập; nếu chunk sau thất bại, các chunk trước vẫn đã commit. Đây là thay đổi semantics nghiệp vụ, cần checkpoint và cơ chế tiếp tục/retry phù hợp.

Không dùng một transaction khổng lồ chỉ để có cảm giác toàn bộ batch là nguyên tử nếu database không thể giữ tài nguyên lâu như vậy.

## 15. Những lỗi thường gặp

**“Mỗi repository tự transactional nên nhiều repository call tự động cùng một transaction.”** Không đúng. Nếu không có transaction bên ngoài, các lời gọi có thể hoàn tất trong những transaction riêng. Hãy đặt §@Transactional§ ở service bao quanh use case.

**“Chỉ cần đặt @Transactional ở một repository.”** Điều đó không tự bao quanh các lời gọi repository khác từ service. Ranh giới cần bao trùm toàn bộ thao tác nghiệp vụ.

**“Hai repository cùng dùng CrudRepository là đủ để join transaction.”** Không. Chúng cần dùng cùng transaction manager/resource phù hợp.

**“@Transactional luôn quản lý mọi database trong ứng dụng.”** Không. Một transaction manager JDBC thông thường chỉ quản lý resource của nó. Nhiều DataSource độc lập cần giải pháp phối hợp riêng nếu muốn atomicity xuyên resource.

**“REQUIRES_NEW giống REQUIRED.”** Không. REQUIRES_NEW tạo transaction vật lý độc lập và có thể commit dù transaction ngoài rollback.

**“Có thể dùng REQUIRES_NEW cho mọi repository call để an toàn.”** Không. Điều đó phá vỡ atomicity của use case và có thể làm cạn connection pool.

**“Bắt exception rồi log là transaction sẽ rollback.”** Không. Nếu method kết thúc bình thường sau khi bắt exception, transaction có thể commit. Hãy ném lại hoặc đánh dấu rollback-only.

**“Checked exception luôn rollback.”** Không theo mặc định. Dùng §rollbackFor§ nếu checked exception phải làm rollback.

**“Gọi method transactional từ chính class đó vẫn đi qua proxy.”** Không trong proxy mode thông thường. Self-invocation không đi qua Spring proxy.

**“@Transactional bao gồm lời gọi HTTP.”** Không. Transaction JDBC không thể rollback side effect của hệ thống bên ngoài.

**“@Async tự kế thừa transaction hiện tại.”** Không. Transaction JDBC imperative thường gắn với thread; thread khác cần transaction riêng.

**“readOnly = true ngăn tuyệt đối mọi câu lệnh ghi.”** Không. Đây chủ yếu là hint, tùy driver/database.

**“Transaction chung luôn cho snapshot dữ liệu nhất quán.”** Không. Mức nhất quán phụ thuộc isolation level và database.

**“Một transaction dài luôn tốt hơn nhiều transaction nhỏ.”** Không. Transaction dài có thể giữ connection/lock và làm tăng rủi ro vận hành; cần chọn ranh giới theo yêu cầu atomicity.

## 16. Quy trình thiết kế use case nhiều repository

Khi một nghiệp vụ cần phối hợp nhiều repository, hãy thực hiện:

1. **Xác định các thao tác phải cùng thành công:** ghi rõ repository nào tham gia và trạng thái nào phải được bảo vệ.
2. **Xác định resource:** kiểm tra các repository dùng cùng DataSource/database hay không.
3. **Chọn transaction manager:** bảo đảm service và repository cùng sử dụng manager quản lý đúng resource.
4. **Đặt ranh giới ở service:** dùng §@Transactional§ trên method điều phối use case.
5. **Giữ propagation phù hợp:** thường dùng REQUIRED; chỉ dùng REQUIRES_NEW/NESTED khi semantics yêu cầu rõ.
6. **Xác định rollback rules:** RuntimeException/Error mặc định rollback; cấu hình rollbackFor cho checked exception cần rollback.
7. **Không nuốt lỗi:** ném lại hoặc đánh dấu rollback-only nếu cần hủy transaction.
8. **Kiểm tra proxy:** method được gọi qua Spring bean proxy; tránh self-invocation.
9. **Giữ transaction ngắn:** không chờ HTTP hoặc chạy xử lý dài trong transaction JDBC.
10. **Xử lý nhiều database:** dùng JTA/XA nếu thật sự cần distributed atomicity, hoặc Saga/outbox cho quy trình phân tán.
11. **Kiểm tra bằng integration test:** xác nhận một repository ghi thành công nhưng repository tiếp theo thất bại thì dữ liệu trước đó được rollback.
12. **Quan sát transaction:** kiểm tra transaction manager, datasource và SQL thực tế trong môi trường test.

~~~mermaid
flowchart TD
    A["Use case cần nhiều repository"] --> B{"Các repository dùng cùng DataSource/resource?"}
    B -->|Có| C["Chọn cùng JDBC transaction manager"]
    B -->|Không| D["Đánh giá JTA/XA hoặc Saga/Outbox"]
    C --> E["Đặt @Transactional ở service"]
    E --> F["Các repository tham gia REQUIRED"]
    F --> G{"Có lỗi cần rollback?"}
    G -->|Có| H["Ném exception / rollback-only"]
    G -->|Không| I["Commit"]
    H --> J["Rollback mọi thay đổi trong transaction"]
    D --> K["Thiết kế phối hợp nhiều resource"]
~~~

## 17. Kiểm thử transaction giữa nhiều repository

Một integration test nên xác nhận không chỉ từng repository hoạt động, mà cả ranh giới transaction.

Ví dụ kịch bản:

1. Chuẩn bị tồn kho ban đầu là 10.
2. Gọi service đặt 2 sản phẩm.
3. Xác nhận tồn kho còn 8 và đơn hàng được tạo.
4. Chuẩn bị một tình huống làm thao tác lưu đơn hàng thất bại sau khi tồn kho đã được lưu.
5. Gọi lại service.
6. Xác nhận tồn kho vẫn là 10 và không có đơn hàng mới.

Khung test minh họa:

~~~java
@SpringBootTest
class PlaceOrderTransactionTest {

    @Autowired
    PlaceOrderService placeOrderService;

    @Autowired
    InventoryRepository inventoryRepository;

    @Autowired
    PurchaseOrderRepository orderRepository;

    @Test
    void rollsBackInventoryWhenOrderInsertFails() {
        // Arrange:
        // - Tạo inventory có đủ hàng.
        // - Tạo dữ liệu khiến thao tác insert order thất bại.

        // Act:
        assertThrows(
                RuntimeException.class,
                () -> placeOrderService.placeOrder("SKU-01", 2)
        );

        // Assert:
        InventoryItem inventory =
                inventoryRepository.findBySku("SKU-01")
                        .orElseThrow();

        assertEquals(10, inventory.availableQuantity());

        // Kiểm tra không có đơn hàng được tạo.
    }
}
~~~

Test thực tế cần tạo lỗi database có thể tái lập, chẳng hạn constraint violation ở bước insert đơn hàng. Không chỉ ném exception trước khi gọi repository thứ hai, vì test như vậy chưa chứng minh được database đã thực hiện và rollback thao tác ghi đầu tiên.

Cũng cần chú ý transaction của chính test. Nếu test method được đánh dấu §@Transactional§, test framework có thể mở transaction ngoài và rollback khi test kết thúc. Hãy thiết kế setup/assertion sao cho có thể quan sát đúng transaction boundary của service.

## 18. Ghi nhớ

- Một use case dùng nhiều repository nên có transaction boundary ở service/facade bao quanh toàn bộ các thao tác cần atomicity.
- Spring Data JDBC sử dụng transaction management của Spring JDBC.
- Các repository cần cùng DataSource/resource và transaction manager phù hợp để tham gia cùng một JDBC transaction.
- CRUD repository methods mặc định transactional; query methods cần được đánh dấu transactional hoặc chạy bên trong transaction service.
- REQUIRED là propagation mặc định: tạo transaction nếu chưa có hoặc tham gia transaction hiện tại.
- REQUIRES_NEW tạo transaction vật lý độc lập; thao tác bên trong có thể commit dù transaction ngoài rollback.
- NESTED dựa trên savepoint và phụ thuộc hỗ trợ của transaction manager/database.
- RuntimeException và Error rollback theo mặc định; checked exception cần rollback phải được cấu hình bằng rollbackFor.
- Bắt exception rồi kết thúc method bình thường có thể khiến transaction commit; hãy ném lại hoặc đánh dấu rollback-only.
- @Transactional hoạt động qua Spring proxy; self-invocation không kích hoạt proxy trong chế độ thông thường.
- Một JDBC transaction manager không tự phối hợp nhiều DataSource độc lập. Dùng JTA/XA khi cần distributed atomic commit hoặc Saga/outbox cho quy trình phân tán.
- Transaction JDBC không rollback được HTTP side effect; không giữ transaction mở trong lúc chờ hệ thống ngoài.
- Transaction imperative thường gắn với thread; @Async và thread khác không tự kế thừa transaction.
- Chọn isolation, timeout và độ dài transaction theo workload và yêu cầu nhất quán.

Khi phối hợp nhiều repository, hãy xác định **những thay đổi nào phải cùng commit hoặc cùng rollback**, sau đó đặt transaction ở service điều phối và bảo đảm mọi repository dùng đúng resource. Đây là cách giữ một use case nghiệp vụ nhất quán dù dữ liệu được quản lý bởi nhiều aggregate và nhiều repository khác nhau.

## Tài liệu tham khảo

- [Spring Data Relational 4.1.2 — Transactionality](https://docs.spring.io/spring-data/relational/reference/jdbc/transactions.html)
- [Spring Framework — Declarative Transaction Management with @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Transaction Resource Synchronization](https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-resource-synchronization.html)

