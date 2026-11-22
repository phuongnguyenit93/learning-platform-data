# Propagation: REQUIRED, REQUIRES_NEW và NESTED

Trong **Spring Data Relational JDBC**, transaction xác định phạm vi mà các thao tác database được commit hoặc rollback cùng nhau. Khi một service gọi service khác, câu hỏi quan trọng là: method được gọi sẽ tham gia transaction đang chạy, tạo transaction độc lập hay tạo một điểm rollback bên trong transaction hiện tại?

Spring quản lý hành vi này bằng thuộc tính **propagation** của `@Transactional`. Ba chế độ thường cần phân biệt là:

- **`REQUIRED`**: tham gia transaction hiện tại; nếu chưa có thì tạo transaction mới.
- **`REQUIRES_NEW`**: tạm ngưng transaction hiện tại và tạo một transaction vật lý mới.
- **`NESTED`**: nếu đã có transaction thì tạo savepoint để rollback một phần; nếu chưa có thì hoạt động như `REQUIRED`.

Các chế độ này không chỉ là ba cách viết annotation. Chúng quyết định phạm vi commit, rollback, việc giữ connection và cách xử lý lỗi giữa các service. Bài học dùng ví dụ đặt hàng để giải thích từng chế độ, cách chọn và các giới hạn khi chạy với JDBC transaction manager.

## 1. Propagation là gì?

Propagation mô tả cách một method có `@Transactional` tương tác với transaction đang tồn tại tại thời điểm method được gọi.

Ví dụ, một application service tạo đơn hàng rồi gọi service giữ hàng trong kho:

~~~text
OrderApplicationService.createOrder()
    |
    +-- PurchaseOrderRepository.save()
    |
    +-- InventoryService.reserve()
            |
            +-- InventoryRepository.update()
~~~

Cả hai service đều thao tác database. Nếu việc tạo đơn và giữ hàng phải thành công hoặc thất bại cùng nhau, `InventoryService.reserve()` cần tham gia cùng transaction của `createOrder()`. Đây là trường hợp điển hình của `REQUIRED`.

Nếu service ghi audit cần commit độc lập ngay cả khi tạo đơn thất bại, `REQUIRES_NEW` có thể phù hợp. Nếu một phần thao tác có thể rollback về savepoint trong khi phần còn lại tiếp tục, `NESTED` có thể phù hợp khi transaction manager hỗ trợ savepoint.

### 1.1. Transaction logic và transaction vật lý

Spring có thể tạo nhiều phạm vi transaction logic thông qua các method được đánh dấu `@Transactional`. Những phạm vi logic đó không nhất thiết tương ứng với nhiều transaction vật lý trong database.

- Với `REQUIRED`, nhiều phạm vi logic có thể cùng tham gia một transaction vật lý.
- Với `REQUIRES_NEW`, Spring tạm ngưng transaction vật lý bên ngoài và mở transaction vật lý độc lập.
- Với `NESTED`, phạm vi bên trong dùng savepoint của transaction vật lý hiện tại.

Đây là khác biệt nền tảng để hiểu vì sao một lỗi trong method con có thể làm rollback cả transaction cha, vì sao audit có thể được giữ lại sau khi transaction ngoài rollback, và vì sao rollback một nested scope không nhất thiết hủy toàn bộ công việc trước đó.

## 2. Cách khai báo propagation

Sử dụng `Propagation` trong package `org.springframework.transaction.annotation`:

~~~java
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
~~~

Ví dụ:

~~~java
@Transactional(propagation = Propagation.REQUIRED)
public void createOrder() {
    // Các thao tác database.
}
~~~

Nếu không khai báo `propagation`, mặc định của `@Transactional` là `Propagation.REQUIRED`:

~~~java
@Transactional
public void createOrder() {
    // Tương đương REQUIRED.
}
~~~

Hãy đặt transaction boundary ở application/service layer theo một use case hoàn chỉnh. Repository của Spring Data JDBC cũng có cấu hình transaction cho các method CRUD, nhưng transaction ở service giúp nhiều thao tác repository tham gia cùng một đơn vị nghiệp vụ.

## 3. REQUIRED: tham gia transaction hiện tại hoặc tạo mới

`REQUIRED` là propagation mặc định và thường là lựa chọn phù hợp cho các service cùng thực hiện một use case nghiệp vụ.

Quy tắc:

| Trạng thái lúc method được gọi | Hành vi của REQUIRED |
|---|---|
| Chưa có transaction | Tạo transaction mới |
| Đang có transaction | Tham gia transaction hiện tại |

### 3.1. Ví dụ tạo đơn và giữ hàng

Application service:

~~~java
@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository orders;
    private final InventoryService inventory;

    public OrderApplicationService(
            PurchaseOrderRepository orders,
            InventoryService inventory) {
        this.orders = orders;
        this.inventory = inventory;
    }

    @Transactional
    public Long createOrder(CreateOrderCommand command) {
        PurchaseOrder order = PurchaseOrder.create(command);
        PurchaseOrder saved = orders.save(order);

        inventory.reserve(command.items());

        return saved.getId();
    }
}
~~~

Service kho:

~~~java
@Service
public class InventoryService {

    private final InventoryRepository inventory;

    public InventoryService(InventoryRepository inventory) {
        this.inventory = inventory;
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void reserve(List<OrderItem> items) {
        for (OrderItem item : items) {
            inventory.decreaseAvailable(item.productId(), item.quantity());
        }
    }
}
~~~

Khi `createOrder()` được gọi từ bên ngoài và chưa có transaction:

1. Spring mở transaction cho `createOrder()`.
2. `orders.save()` thực hiện trong transaction đó.
3. `inventory.reserve()` được gọi qua bean proxy và tham gia transaction đang chạy.
4. Các cập nhật kho cùng thuộc transaction vật lý với thao tác lưu đơn.
5. Nếu transaction commit, cả hai nhóm thay đổi được commit.
6. Nếu transaction rollback, cả hai nhóm thay đổi được rollback.

~~~mermaid
sequenceDiagram
    participant Client
    participant Order as OrderApplicationService
    participant Inventory as InventoryService
    participant DB as Database
    Client->>Order: createOrder()
    Order->>DB: BEGIN transaction T1
    Order->>DB: INSERT purchase_order
    Order->>Inventory: reserve()
    Note over Inventory,DB: REQUIRED tham gia T1
    Inventory->>DB: UPDATE inventory
    Order->>DB: COMMIT T1
    Order-->>Client: orderId
~~~

Sơ đồ mô tả trường hợp thành công. Nếu thao tác cập nhật kho ném exception thuộc loại được cấu hình rollback, toàn bộ T1 bị rollback.

### 3.2. REQUIRED khi service con được gọi độc lập

Nếu `InventoryService.reserve()` được gọi từ một nơi không có transaction, `REQUIRED` sẽ tự mở transaction mới cho method đó. Vì vậy, cùng một service có thể tham gia transaction của caller hoặc tạo transaction khi được gọi độc lập.

### 3.3. Lỗi trong transaction được tham gia

Một điểm quan trọng: phạm vi `REQUIRED` bên trong dùng chung transaction vật lý với bên ngoài. Khi interceptor của method con nhận exception thuộc loại rollback, transaction đang tham gia có thể bị đánh dấu **rollback-only**.

Ví dụ:

~~~java
@Service
public class InventoryService {

    @Transactional(propagation = Propagation.REQUIRED)
    public void reserve() {
        // Cập nhật kho.
        throw new IllegalStateException("Không đủ hàng");
    }
}
~~~

Caller bắt exception:

~~~java
@Transactional
public void createOrder() {
    orders.save(newOrder());

    try {
        inventory.reserve();
    } catch (IllegalStateException ex) {
        // Ghi nhận lỗi và tiếp tục xử lý.
    }

    // Method kết thúc bình thường.
}
~~~

Nếu exception từ `reserve()` làm transaction bị đánh dấu rollback-only, việc caller bắt exception không xóa cờ rollback-only. Khi `createOrder()` kết thúc, Spring không thể commit transaction như thể không có lỗi. Transaction bị rollback và caller có thể nhận `UnexpectedRollbackException`.

Điều này ngăn caller tưởng rằng dữ liệu đã commit trong khi một phạm vi tham gia trước đó đã yêu cầu rollback.

### 3.4. Quy tắc rollback mặc định

Theo mặc định của Spring transaction, exception kiểu `RuntimeException` và `Error` làm transaction rollback. Checked exception không tự động làm rollback theo quy tắc mặc định.

Có thể cấu hình rõ:

~~~java
@Transactional(rollbackFor = BusinessException.class)
public void createOrder() throws BusinessException {
    // Thao tác database.
}
~~~

Hoặc loại trừ một exception:

~~~java
@Transactional(noRollbackFor = DuplicateNoticeException.class)
public void recordNotice() {
    // Thao tác database.
}
~~~

Quy tắc rollback phải được xét cùng propagation. `REQUIRED` chia sẻ trạng thái rollback với transaction hiện tại; `REQUIRES_NEW` có trạng thái rollback độc lập; `NESTED` có thể rollback về savepoint nếu transaction manager hỗ trợ.

## 4. REQUIRES_NEW: tạo transaction vật lý độc lập

`REQUIRES_NEW` luôn thực hiện method trong một transaction vật lý mới. Nếu caller đang có transaction, Spring tạm ngưng transaction đó trong thời gian transaction mới chạy.

Quy tắc:

| Trạng thái lúc method được gọi | Hành vi của REQUIRES_NEW |
|---|---|
| Chưa có transaction | Tạo transaction mới |
| Đang có transaction | Tạm ngưng transaction hiện tại và tạo transaction mới |

Transaction bên trong có thể commit hoặc rollback độc lập với transaction bên ngoài.

### 4.1. Ví dụ ghi audit độc lập

Giả sử hệ thống cần ghi nhận một lần thử tạo đơn, kể cả khi nghiệp vụ tạo đơn thất bại. Có thể dùng service audit:

~~~java
@Service
public class OrderAuditService {

    private final OrderAuditRepository audits;

    public OrderAuditService(OrderAuditRepository audits) {
        this.audits = audits;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordAttempt(Long orderId, String outcome) {
        audits.save(new OrderAudit(orderId, outcome));
    }
}
~~~

Service ngoài:

~~~java
@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository orders;
    private final OrderAuditService audit;

    public OrderApplicationService(
            PurchaseOrderRepository orders,
            OrderAuditService audit) {
        this.orders = orders;
        this.audit = audit;
    }

    @Transactional
    public Long createOrder(CreateOrderCommand command) {
        PurchaseOrder saved = orders.save(PurchaseOrder.create(command));

        audit.recordAttempt(saved.getId(), "CREATED");

        // Ví dụ một bước nghiệp vụ tiếp theo thất bại.
        validateShipping(command);

        return saved.getId();
    }
}
~~~

Luồng transaction:

~~~mermaid
sequenceDiagram
    participant Client
    participant Order as OrderApplicationService
    participant Audit as OrderAuditService
    participant DB as Database
    Client->>Order: createOrder()
    Order->>DB: BEGIN T1
    Order->>DB: INSERT purchase_order
    Order->>Audit: recordAttempt()
    Note over Order: T1 bị tạm ngưng
    Audit->>DB: BEGIN T2
    Audit->>DB: INSERT order_audit
    Audit->>DB: COMMIT T2
    Audit-->>Order: return
    Note over Order: T1 tiếp tục
    Order->>Order: validateShipping() thất bại
    Order->>DB: ROLLBACK T1
    Order-->>Client: exception
~~~

Trong ví dụ, bản ghi audit được commit trong T2. Nếu bước xác thực sau đó làm T1 rollback, bản ghi audit vẫn tồn tại vì T2 độc lập.

### 4.2. Khi nào REQUIRES_NEW hữu ích?

Một số trường hợp có thể cần transaction độc lập:

- Ghi nhận audit về lần thử hoặc kết quả xử lý cần tồn tại dù transaction nghiệp vụ rollback.
- Lưu trạng thái kỹ thuật của một tác vụ cần commit riêng.
- Cập nhật bộ đếm hoặc dữ liệu vận hành độc lập với transaction nghiệp vụ, sau khi đã cân nhắc consistency.
- Lưu một phần kết quả mà hợp đồng nghiệp vụ xác định rõ là phải tồn tại độc lập.

Hãy xác định rõ ý nghĩa dữ liệu trước khi dùng. Nếu audit phải mô tả **sự kiện nghiệp vụ đã commit**, ghi audit bằng `REQUIRES_NEW` trước khi transaction ngoài commit có thể tạo bản ghi sai: audit nói đơn đã tạo nhưng đơn cuối cùng bị rollback.

Với outbox event cần tồn tại đúng khi thay đổi nghiệp vụ commit, thông thường ghi outbox trong **cùng transaction** với aggregate, tức cùng transaction `REQUIRED`, để cả hai cùng commit hoặc rollback.

### 4.3. Transaction ngoài không thể rollback phần đã commit bên trong

Ví dụ:

1. T1 cập nhật đơn hàng.
2. T2 được mở bằng `REQUIRES_NEW`.
3. T2 ghi audit và commit.
4. T1 gặp lỗi và rollback.

Kết quả:

- Thay đổi của T1 bị rollback.
- Bản ghi audit của T2 vẫn được giữ.

Đây chính là mục đích của transaction độc lập. Nếu không muốn dữ liệu con tồn tại khi dữ liệu cha rollback, `REQUIRES_NEW` không phù hợp.

### 4.4. Chi phí connection và nguy cơ chờ khóa

Khi transaction ngoài bị tạm ngưng, connection và tài nguyên của nó thường vẫn được giữ trong lúc transaction mới chạy. T2 cần một connection khác.

Điều này tạo hai rủi ro:

**Connection pool thiếu:** nếu nhiều request đồng thời đều giữ connection của T1 rồi chờ T2 lấy connection mới, pool có thể cạn. Các request phải chờ nhau và có thể bị timeout. Cần tính kích thước pool theo số transaction lồng nhau và concurrency thực tế.

**Chờ khóa do chính transaction ngoài giữ:** nếu T1 đã khóa một hàng và T2 cố cập nhật cùng hàng đó, T2 có thể chờ T1 giải phóng khóa. Nhưng T1 đang bị tạm ngưng và chờ T2 kết thúc. Điều này có thể dẫn đến chờ đến timeout hoặc deadlock tùy database và lock behavior.

Không dùng `REQUIRES_NEW` tùy tiện trong vòng lặp lớn hoặc cho các thao tác cần sửa cùng những hàng mà transaction ngoài đang giữ khóa.

## 5. NESTED: dùng savepoint bên trong transaction hiện tại

`NESTED` cho phép tạo một phạm vi rollback bên trong transaction vật lý hiện tại bằng **savepoint** của JDBC.

Quy tắc:

| Trạng thái lúc method được gọi | Hành vi của NESTED |
|---|---|
| Chưa có transaction | Hoạt động như REQUIRED và tạo transaction mới |
| Đang có transaction | Tạo savepoint trong transaction hiện tại |

Khác với `REQUIRES_NEW`, nested scope không có transaction vật lý độc lập. Nó dùng chung connection và transaction với caller.

### 5.1. Savepoint hoạt động như thế nào?

Giả sử transaction ngoài đã ghi đơn hàng rồi gọi một bước nhập thông tin tùy chọn:

~~~text
BEGIN T1
  INSERT purchase_order
  SAVEPOINT S1
    INSERT optional_order_note
    UPDATE optional_shipping_data
  RELEASE S1
COMMIT T1
~~~

Nếu phần nested gặp lỗi và được rollback về savepoint:

~~~text
BEGIN T1
  INSERT purchase_order
  SAVEPOINT S1
    INSERT optional_order_note
    UPDATE optional_shipping_data
  ROLLBACK TO S1
  -- T1 vẫn có thể tiếp tục
  UPDATE purchase_order
COMMIT T1
~~~

Các thay đổi trước savepoint vẫn còn trong T1. Các thay đổi sau savepoint trong nested scope bị hủy khi rollback về S1. Transaction ngoài có thể tiếp tục và commit phần còn lại nếu lỗi được xử lý đúng.

### 5.2. Ví dụ với service riêng

Service xử lý phần tùy chọn:

~~~java
@Service
public class OptionalOrderDataService {

    private final OptionalOrderDataRepository data;

    public OptionalOrderDataService(OptionalOrderDataRepository data) {
        this.data = data;
    }

    @Transactional(propagation = Propagation.NESTED)
    public void addOptionalData(Long orderId) {
        data.insertNote(orderId, "Customer requested gift wrapping");
        data.updateShippingPreference(orderId, "GIFT_WRAP");

        validateOptionalData(orderId);
    }
}
~~~

Caller:

~~~java
@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository orders;
    private final OptionalOrderDataService optionalData;

    public OrderApplicationService(
            PurchaseOrderRepository orders,
            OptionalOrderDataService optionalData) {
        this.orders = orders;
        this.optionalData = optionalData;
    }

    @Transactional
    public Long createOrder(CreateOrderCommand command) {
        PurchaseOrder saved = orders.save(PurchaseOrder.create(command));

        try {
            optionalData.addOptionalData(saved.getId());
        } catch (OptionalDataException ex) {
            // Bỏ phần dữ liệu tùy chọn; transaction ngoài tiếp tục.
        }

        return saved.getId();
    }
}
~~~

Nếu `addOptionalData()` ném exception làm nested scope rollback và caller bắt exception, T1 có thể tiếp tục với đơn hàng đã lưu. Điều này chỉ đúng khi nested transaction/savepoint thực sự được hỗ trợ và exception không làm transaction ngoài bị đánh dấu rollback-only bởi một cơ chế khác.

### 5.3. Nested thành công không có commit độc lập

Nếu `addOptionalData()` kết thúc thành công, thay đổi của nested scope vẫn thuộc T1. Sau đó:

- T1 commit: thay đổi của outer và nested cùng commit.
- T1 rollback: thay đổi của outer và nested cùng rollback.

NESTED không giúp giữ dữ liệu bên trong nếu transaction ngoài thất bại. Nếu cần điều đó, hãy xem xét `REQUIRES_NEW` và những hệ quả consistency của nó.

## 6. Điều kiện để NESTED hoạt động với Spring Data JDBC

`NESTED` phụ thuộc khả năng savepoint của transaction manager và JDBC driver/database.

Với ứng dụng Spring Data JDBC, các transaction manager JDBC như `DataSourceTransactionManager` và `JdbcTransactionManager` có thể hỗ trợ nested transaction bằng JDBC savepoint. Cần xác nhận:

- Transaction manager đang dùng có hỗ trợ nested transaction không.
- Nested transaction support có được bật trong cấu hình hay không.
- JDBC driver và database hỗ trợ savepoint.
- Các thao tác tham gia cùng transaction manager và cùng connection resource.

Không phải mọi transaction manager đều hỗ trợ `NESTED`. Ví dụ, không thể mặc định `JtaTransactionManager` hoặc một transaction manager không dùng JDBC savepoint sẽ cung cấp cùng semantics.

Nếu ứng dụng Spring Data JDBC dùng Spring Boot, hãy kiểm tra bean transaction manager thực tế thay vì chỉ suy luận từ việc có dependency Spring Data JDBC.

### 6.1. NESTED không phải nested object hoặc nested aggregate

Từ “nested” ở đây nói về **transaction savepoint**, không nói về:

- Một object lồng trong object khác.
- Một entity con được khai báo bằng `@MappedCollection`.
- Một aggregate root nằm bên trong aggregate khác.

Quan hệ aggregate vẫn do domain model và mapping Spring Data JDBC quyết định. Propagation chỉ điều khiển cách phạm vi transaction tương tác với transaction hiện có.

## 7. So sánh ba propagation

| Tiêu chí | REQUIRED | REQUIRES_NEW | NESTED |
|---|---|---|---|
| Có transaction ngoài | Tham gia transaction ngoài | Tạm ngưng ngoài, mở transaction mới | Tạo savepoint trong transaction ngoài |
| Không có transaction ngoài | Tạo transaction mới | Tạo transaction mới | Hoạt động như REQUIRED |
| Transaction vật lý | Dùng chung | Transaction độc lập | Dùng chung |
| Connection | Thường dùng connection của transaction hiện tại | Cần connection cho transaction mới trong khi tài nguyên ngoài được giữ | Dùng connection của transaction hiện tại |
| Commit bên trong | Không commit độc lập | Có thể commit độc lập | Không commit độc lập |
| Rollback bên trong | Có thể đánh dấu transaction chung rollback-only | Rollback transaction mới, outer có thể tiếp tục | Rollback về savepoint nếu được hỗ trợ |
| Outer rollback | Rollback tất cả thay đổi chung | Không undo phần inner đã commit | Undo cả phần outer và nested đã commit trong T1 |
| Hỗ trợ savepoint | Không cần | Không cần | Bắt buộc |
| Use case thường gặp | Một nghiệp vụ gồm nhiều service | Ghi độc lập có chủ đích | Thử một phần công việc và rollback cục bộ |

### 7.1. Sơ đồ lựa chọn nhanh

~~~mermaid
flowchart TD
    A["Method @Transactional được gọi"] --> B{"Đang có transaction?"}
    B -->|Không| C["Cả ba chế độ đều mở transaction mới"]
    B -->|Có| D{"Propagation"}
    D -->|REQUIRED| E["Tham gia transaction hiện tại"]
    D -->|REQUIRES_NEW| F["Tạm ngưng transaction ngoài; mở transaction độc lập"]
    D -->|NESTED| G["Tạo savepoint trong transaction hiện tại"]
~~~

Khi chưa có transaction, cả ba chế độ đều dẫn đến một transaction mới, nhưng `NESTED` không tạo savepoint vì chưa có transaction bên ngoài để làm điểm quay lại.

## 8. Isolation, timeout và readOnly khi tham gia transaction

Propagation quyết định cách tham gia transaction; các thuộc tính khác của `@Transactional` như `isolation`, `timeout` và `readOnly` cần được hiểu cùng nó.

Ví dụ:

~~~java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    isolation = Isolation.READ_COMMITTED,
    timeout = 10,
    readOnly = false
)
public void writeAudit() {
    // Ghi dữ liệu audit.
}
~~~

Một số nguyên tắc:

- Khi `REQUIRED` tham gia transaction đã tồn tại, cấu hình isolation/timeout/readOnly của phạm vi bên trong thường không tạo một transaction vật lý mới để áp dụng độc lập. Transaction đang chạy quyết định các đặc tính vật lý.
- `REQUIRES_NEW` tạo transaction vật lý mới nên có thể áp dụng cấu hình transaction riêng của nó, tùy transaction manager và database.
- `NESTED` dùng chung transaction vật lý; savepoint không tạo một isolation level độc lập cho phần nested.

Nếu cần phát hiện trường hợp method con yêu cầu isolation khác với transaction hiện tại, `AbstractPlatformTransactionManager` có tùy chọn `validateExistingTransaction`. Cấu hình này cần được cân nhắc theo ứng dụng; không nên giả định Spring luôn từ chối mọi khác biệt thuộc tính khi join.

`readOnly = true` là một chỉ dẫn/hint cho transaction manager và database. Nó không phải cơ chế bảo mật bảo đảm mọi câu ghi đều bị chặn trong tất cả hệ quản trị.

## 9. Transaction propagation chỉ hoạt động khi lời gọi đi qua proxy

Trong cấu hình transaction dựa trên Spring AOP proxy, `@Transactional` được áp dụng khi method được gọi qua proxy của Spring bean.

Ví dụ dễ gây hiểu nhầm:

~~~java
@Service
public class OrderService {

    public void create() {
        saveAudit(); // self-invocation
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveAudit() {
        // Người viết kỳ vọng một transaction mới.
    }
}
~~~

Lời gọi `this.saveAudit()` bên trong cùng object không đi qua proxy, vì vậy interceptor transaction thường không áp dụng propagation `REQUIRES_NEW` cho lời gọi này.

Cách tổ chức rõ ràng hơn là chuyển phần cần propagation riêng sang một bean khác:

~~~java
@Service
public class AuditService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveAudit() {
        // Transaction độc lập.
    }
}
~~~

~~~java
@Service
public class OrderService {

    private final AuditService audit;

    public OrderService(AuditService audit) {
        this.audit = audit;
    }

    @Transactional
    public void create() {
        // Ghi đơn trong transaction ngoài.
        audit.saveAudit(); // Gọi qua Spring proxy của bean AuditService.
    }
}
~~~

Với proxy-based transaction management, method thường cần được gọi qua proxy và visibility phải phù hợp với loại proxy/cấu hình. Không dựa vào lời gọi nội bộ để tạo transaction mới. AspectJ transaction weaving có semantics khác, nhưng không phải cấu hình mặc định thường gặp trong Spring Boot.

Transaction JDBC của Spring thường gắn với thread hiện tại. Nếu tạo thread mới, dùng `@Async` hoặc tự gửi công việc sang executor, transaction không tự động truyền sang thread khác. Công việc bất đồng bộ cần transaction boundary riêng.

## 10. Chọn propagation theo yêu cầu nghiệp vụ

### Chọn REQUIRED khi các thay đổi phải cùng thành công

Ví dụ:

- Tạo đơn và tạo các dòng hàng thuộc aggregate.
- Cập nhật trạng thái đơn và cập nhật tồn kho trong cùng một database transaction.
- Ghi aggregate và ghi outbox event cần commit cùng nhau.
- Nhiều service cùng tham gia một use case không có nhu cầu commit độc lập.

Đây thường là lựa chọn mặc định. Nếu transaction ngoài rollback, các thao tác tham gia REQUIRED cũng rollback.

### Chọn REQUIRES_NEW khi cần kết quả độc lập có chủ đích

Ví dụ:

- Ghi audit về một lần thử cần tồn tại dù nghiệp vụ chính rollback.
- Ghi một trạng thái vận hành độc lập có hợp đồng rõ ràng.
- Lưu dữ liệu phụ mà yêu cầu nghiệp vụ xác định không phụ thuộc commit của transaction ngoài.

Trước khi chọn, hãy hỏi:

- Có chấp nhận bản ghi bên trong tồn tại khi nghiệp vụ ngoài thất bại không?
- Có thể ghi cùng hàng đang bị transaction ngoài khóa không?
- Connection pool có đủ cho transaction lồng nhau không?
- Việc commit riêng có tạo dữ liệu gây hiểu nhầm hoặc mất nhất quán không?

### Chọn NESTED khi cần rollback một phần nhưng vẫn cùng transaction

Ví dụ:

- Thử áp dụng một phần dữ liệu tùy chọn.
- Xử lý một nhóm thao tác có thể bỏ qua nếu thất bại, trong khi phần nghiệp vụ chính vẫn hợp lệ.
- Rollback về savepoint để giữ những thay đổi trước đó trong cùng transaction.

Chỉ dùng khi transaction manager hỗ trợ savepoint và caller có thể xử lý lỗi để tiếp tục. Nếu nested scope thành công nhưng transaction ngoài rollback, mọi thay đổi vẫn bị rollback.

## 11. Những lỗi thiết kế thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Bắt exception ở caller nhưng cuối cùng vẫn rollback | Method REQUIRED bên trong đã đánh dấu transaction chung rollback-only | Hiểu rollback rule; không kỳ vọng bắt exception sẽ xóa rollback-only |
| Ghi audit nhưng audit biến mất cùng đơn hàng | Audit dùng REQUIRED và tham gia transaction ngoài | Dùng REQUIRES_NEW chỉ khi audit thực sự cần tồn tại độc lập |
| Audit nói đơn đã tạo nhưng đơn không tồn tại | Ghi audit REQUIRES_NEW trước khi transaction tạo đơn commit | Ghi outbox/audit xác nhận commit trong cùng transaction nếu cần nhất quán |
| REQUIRES_NEW bị chờ lâu | Transaction ngoài giữ lock mà transaction trong cần | Tránh cập nhật cùng hàng; xem lại transaction boundary |
| Request bị treo khi pool cạn | Outer giữ connection, inner cần connection mới | Tính connection pool theo concurrency và transaction lồng nhau |
| NESTED không tạo savepoint | Transaction manager hoặc driver không hỗ trợ | Xác nhận JDBC transaction manager và savepoint support |
| Dùng NESTED nhưng outer rollback vẫn mất dữ liệu inner | Nested scope không commit độc lập | Dùng REQUIRES_NEW nếu thật sự cần commit riêng |
| `@Transactional` trên method nội bộ không có tác dụng | Self-invocation không đi qua proxy | Tách method sang bean khác hoặc dùng cơ chế weaving phù hợp |
| Transaction không bao phủ tác vụ async | Transaction thread-bound không tự truyền sang thread mới | Mở transaction riêng trong worker/task |
| Chọn propagation để tối ưu tốc độ | Nhầm propagation với batch/bulk | Chọn theo semantics commit/rollback, đo hiệu năng riêng |

## 12. Ví dụ tổng hợp: đặt hàng, ghi audit và xử lý dữ liệu tùy chọn

Một use case có thể dùng cả ba chế độ, nhưng chỉ khi từng phần có yêu cầu rõ ràng:

~~~java
@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository orders;
    private final InventoryService inventory;
    private final OrderAuditService audit;
    private final OptionalOrderDataService optionalData;

    public OrderApplicationService(
            PurchaseOrderRepository orders,
            InventoryService inventory,
            OrderAuditService audit,
            OptionalOrderDataService optionalData) {
        this.orders = orders;
        this.inventory = inventory;
        this.audit = audit;
        this.optionalData = optionalData;
    }

    @Transactional
    public Long create(CreateOrderCommand command) {
        PurchaseOrder saved = orders.save(
            PurchaseOrder.create(command)
        );

        // REQUIRED: cùng transaction với việc tạo đơn.
        inventory.reserve(command.items());

        // NESTED: phần tùy chọn có thể rollback về savepoint.
        try {
            optionalData.addOptionalData(saved.getId());
        } catch (OptionalDataException ex) {
            // Đơn vẫn có thể tiếp tục nếu nghiệp vụ cho phép.
        }

        // REQUIRES_NEW: ghi nhận lần thử độc lập theo yêu cầu audit.
        audit.recordAttempt(saved.getId(), "PROCESSING");

        return saved.getId();
    }
}
~~~

Các service được gọi phải là Spring bean riêng với propagation tương ứng. Ví dụ trên chỉ minh họa cơ chế; trong một hệ thống thực tế, trạng thái audit nên được đặt tên chính xác. Ghi `PROCESSING` trong transaction độc lập có nghĩa là trạng thái này có thể tồn tại dù transaction tạo đơn sau đó rollback.

Nếu yêu cầu là “chỉ ghi sự kiện ORDER_CREATED khi đơn thực sự commit”, hãy lưu outbox event trong transaction REQUIRED cùng đơn hàng. Không dùng REQUIRES_NEW cho sự kiện xác nhận commit đó.

## 13. Bài tập thực hành

### Bài 1 — REQUIRED và rollback chung

1. Tạo `OrderApplicationService.createOrder()` có `@Transactional`.
2. Gọi `InventoryService.reserve()` với `REQUIRED`.
3. Cho service kho ném `IllegalStateException` sau khi cập nhật một mặt hàng.
4. Gọi use case và kiểm tra cả đơn hàng lẫn tồn kho.
5. Xác nhận các thay đổi cùng rollback.

### Bài 2 — REQUIRED và rollback-only

1. Để method con REQUIRED ném runtime exception.
2. Bắt exception ở caller.
3. Cho caller kết thúc bình thường.
4. Quan sát rollback và `UnexpectedRollbackException` nếu transaction đã bị đánh dấu rollback-only.
5. Thử lại với checked exception và cấu hình `rollbackFor`.

### Bài 3 — REQUIRES_NEW

1. Tạo `OrderAuditService.recordAttempt()` với REQUIRES_NEW.
2. Gọi nó trong transaction tạo đơn.
3. Làm transaction ngoài rollback sau khi audit commit.
4. Kiểm tra bản ghi audit còn tồn tại trong khi đơn hàng bị rollback.
5. Quan sát connection pool và thử trường hợp inner cập nhật hàng đang bị outer khóa.

### Bài 4 — NESTED

1. Dùng JDBC transaction manager hỗ trợ savepoint.
2. Tạo method `OptionalOrderDataService.addOptionalData()` với NESTED.
3. Ghi một phần dữ liệu rồi cố ý ném runtime exception.
4. Bắt exception ở caller và tiếp tục cập nhật đơn.
5. Kiểm tra dữ liệu trước savepoint còn, dữ liệu sau savepoint bị rollback.
6. Cho outer transaction rollback và xác nhận toàn bộ thay đổi của T1 đều mất.

### Bài 5 — Proxy và self-invocation

1. Đặt method REQUIRES_NEW trong cùng class với caller.
2. Gọi bằng `this.method()` và quan sát transaction.
3. Chuyển method sang một bean khác.
4. Gọi qua dependency injection và so sánh.

## 14. Kết luận

`REQUIRED` tham gia transaction đang có hoặc tạo transaction mới. Đây là lựa chọn mặc định khi nhiều service phải cùng commit hoặc rollback cho một use case. Vì các phạm vi REQUIRED dùng chung transaction vật lý, lỗi ở một phạm vi có thể đánh dấu toàn bộ transaction rollback-only, kể cả khi caller bắt exception.

`REQUIRES_NEW` tạm ngưng transaction ngoài và tạo transaction vật lý độc lập. Phần bên trong có thể commit ngay cả khi transaction ngoài rollback, nhưng cần cân nhắc consistency, connection pool và khóa database.

`NESTED` tạo savepoint trong transaction hiện tại. Nó cho phép rollback một phần và tiếp tục transaction ngoài khi transaction manager hỗ trợ JDBC savepoint. Nested scope thành công vẫn phụ thuộc commit của transaction ngoài.

Hãy chọn propagation dựa trên ý nghĩa commit/rollback của nghiệp vụ. Đặt transaction boundary ở service, gọi method qua Spring proxy, kiểm tra rollback rules và xác nhận transaction manager thực tế. Khi hiểu rõ transaction vật lý, savepoint và phạm vi rollback, bạn có thể phối hợp nhiều service Spring Data JDBC mà vẫn giữ dữ liệu nhất quán.
