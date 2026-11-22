# @Transactional và vị trí ranh giới tại dịch vụ ứng dụng trong Spring và Hibernate ORM

Khi kết hợp Spring với Hibernate/JPA, chú thích `@Transactional` thường xuất hiện ở service, repository hoặc đôi khi ngay cả controller. Tuy nhiên, điều quyết định tính đúng đắn không phải “đã có annotation hay chưa”, mà là **ranh giới giao dịch có bao trùm toàn bộ một ca sử dụng nghiệp vụ cần thành công hoặc thất bại cùng nhau hay không**.

Giả sử hệ thống nhận một đơn hàng:

1. Kiểm tra khách hàng và giỏ hàng.
2. Tạo đơn hàng.
3. Trừ tồn kho.
4. Ghi bản ghi sự kiện chờ gửi.
5. Trả mã đơn hàng.

Nếu bước tạo đơn đã commit nhưng bước trừ kho thất bại, database có thể rơi vào trạng thái không nhất quán. Nếu mỗi thao tác repository tự commit riêng, annotation ở repository không bảo đảm toàn bộ quy trình nguyên tử.

Trong kiến trúc Spring phổ biến, **application service** là nơi phù hợp để đặt một transaction boundary cho mỗi use case đồng bộ, ngắn và chủ yếu thao tác trên cùng transactional resource:

```text
Controller / API adapter
        |
        v
Application Service
  @Transactional
        |
        +-- Kiểm tra dữ liệu và quyền
        +-- Load aggregate / entity
        +-- Thực hiện domain operation
        +-- Gọi repositories cần thiết
        +-- Ghi outbox/audit trong cùng DB transaction
        |
        v
  Commit hoặc rollback
        |
        v
Controller trả response
```

Đây là **nguyên tắc thiết kế**, không phải luật rằng mọi service method đều phải có `@Transactional`. Transaction boundary cần phù hợp với tính nguyên tử nghiệp vụ, đặc tính tài nguyên, độ dài thao tác và cơ chế Spring đang dùng.

Bài học giải thích đầy đủ cơ chế `@Transactional` với Hibernate ORM, lý do đặt ở application service, các thuộc tính propagation/isolation/rollback/readOnly/timeout, Spring proxy và self-invocation, persistence context, dirty checking, lazy loading, Spring Data JPA, lỗi transaction, concurrency, external side effects, kiểm thử và cách thiết kế workflow nhiều bước an toàn.

---

## 1. Giao dịch database giải quyết vấn đề gì?

Một transaction gom nhiều câu lệnh đọc/ghi vào một đơn vị xử lý có ranh giới:

```sql
BEGIN;

INSERT INTO orders (...);
UPDATE inventory SET available = available - 1 WHERE ...;
INSERT INTO outbox_events (...);

COMMIT;
```

Nếu có lỗi trước commit, hệ thống có thể rollback:

```sql
ROLLBACK;
```

Các tính chất ACID thường được nhắc đến:

| Tính chất | Ý nghĩa thực tế |
|---|---|
| Atomicity | Những thay đổi trong cùng transaction commit hoặc rollback cùng nhau |
| Consistency | Constraints và các quy tắc được thực thi giúp dữ liệu chuyển giữa trạng thái hợp lệ |
| Isolation | Các transaction đồng thời quan sát/ảnh hưởng lẫn nhau theo isolation level |
| Durability | Sau commit thành công, database bảo đảm độ bền theo cơ chế của nó |

**Transaction không tự thay thế business validation**. Ví dụ, database không thể đoán “một customer chỉ có thể đặt hàng khi account chưa bị khóa” nếu application/schema chưa biểu đạt quy tắc ấy.

### 1.1. Ba ranh giới cần phân biệt

- **Transaction boundary**: nơi commit/rollback.
- **Persistence context boundary**: nơi Hibernate quản lý entity instances, loaded state và dirty checking.
- **HTTP request boundary**: thời gian server tiếp nhận và trả HTTP response.

Ba ranh giới có thể liên quan, nhưng **không mặc nhiên trùng nhau**.

Ví dụ khi bật Open Session in View (OSIV), EntityManager có thể tồn tại suốt request, trong khi transaction nghiệp vụ chỉ nằm trong service method. Persistence context còn mở không có nghĩa mọi câu lệnh sau đó vẫn thuộc cùng transaction.

## 2. Spring @Transactional là gì?

Trong Spring, annotation phổ biến là:

```java
import org.springframework.transaction.annotation.Transactional;
```

Nó khai báo metadata giao dịch để Spring transaction infrastructure áp dụng quanh lời gọi method phù hợp.

Ví dụ:

```java
@Service
public class CustomerApplicationService {

    private final CustomerRepository customers;

    public CustomerApplicationService(CustomerRepository customers) {
        this.customers = customers;
    }

    @Transactional
    public Long registerCustomer(RegisterCustomerCommand command) {
        Customer customer = new Customer(
            command.email(),
            command.displayName()
        );

        customers.save(customer);
        return customer.getId();
    }
}
```

Trong mô hình proxy-based Spring transaction management thông dụng:

1. Caller gọi method qua **Spring-managed proxy**.
2. Transaction interceptor xác định cấu hình `@Transactional`.
3. Spring tìm hoặc tạo transaction theo propagation policy.
4. Method thực thi trong transaction phù hợp.
5. Nếu thành công, transaction mới do interceptor tạo được commit.
6. Nếu exception phù hợp rollback rules, transaction được rollback hoặc đánh dấu rollback-only.
7. EntityManager/Connection/resources được quản lý theo transaction manager.

**Annotation không tự thêm `BEGIN`/`COMMIT` vào bytecode của method**. Phải có transaction manager, proxy/advice và lời gọi đi qua cơ chế interception thích hợp.

### 2.1. @Transactional không phải API của Hibernate

Spring quản lý transaction boundary; Hibernate ORM thực hiện mapping, entity lifecycle, dirty checking và SQL.

Trong ứng dụng Spring Boot + Spring Data JPA thường gặp:

```text
Spring @Transactional
        |
        v
TransactionInterceptor
        |
        v
JpaTransactionManager
        |
        v
EntityManager / Hibernate Session
        |
        v
JDBC Connection / Database Transaction
```

Cần cấu hình đúng `PlatformTransactionManager` (ví dụ `JpaTransactionManager` cho JPA). Nếu có nhiều transaction managers, method phải dùng đúng manager theo cấu hình/qualifier.

### 2.2. Spring @Transactional và Jakarta @Transactional

Ứng dụng có thể gặp:

```java
org.springframework.transaction.annotation.Transactional
```

và:

```java
jakarta.transaction.Transactional
```

Hai annotation có hỗ trợ và thuộc tính không hoàn toàn giống nhau. Ví dụ Spring annotation có `readOnly`, `timeout`, `isolation`, `rollbackFor` và `propagation` theo API Spring. Không nên trộn import rồi mặc định cùng cú pháp/semantics.

Bài này dùng **Spring `@Transactional`** để minh họa những thuộc tính cụ thể.

## 3. Application service là gì và vì sao thường giữ transaction boundary?

**Application service** điều phối một ca sử dụng: nhận command/input đã được xác thực, kiểm tra quyền và policy, gọi domain objects, repositories, ghi kết quả cần thiết rồi trả response/DTO. Nó khác:

- **Controller**: chuyển request/response của một transport như HTTP.
- **Domain entity/domain service**: biểu đạt quy tắc nghiệp vụ, không cần biết HTTP hoặc Spring transaction manager.
- **Repository**: trừu tượng hóa truy xuất persistence, không nhất thiết biết toàn bộ use case.
- **Infrastructure adapter**: gửi email, gọi payment gateway, publish message.

Ví dụ:

```text
POST /orders
     |
     v
OrderController
     |
     v
PlaceOrderService.place(command)  @Transactional
     |
     +-- customerRepository.find(...)
     +-- inventoryRepository.find(...)
     +-- inventory.reserve(quantity)
     +-- orderRepository.save(order)
     +-- outboxRepository.save(event)
     |
     v
Return OrderReceipt
```

Đặt `@Transactional` tại `place` giúp Spring tạo **một transaction chung** cho các repository calls tham gia cùng resource và propagation phù hợp.

### 3.1. Vì sao không đặt transaction chỉ ở repository?

Giả sử:

```java
public Long placeOrder(PlaceOrderCommand command) {
    Order order = orders.save(newOrder(command));
    inventory.decrease(command.productId(), command.quantity());
    outbox.save(newOrderEvent(order));
    return order.getId();
}
```

Nếu không có outer service transaction, mỗi repository call có thể tạo transaction riêng (hoặc một số call yêu cầu caller cung cấp transaction). `orders.save` đã commit rồi `inventory.decrease` mới thất bại thì không còn cơ chế database thông thường để rollback phần order đã commit trước đó.

Với:

```java
@Transactional
public Long placeOrder(PlaceOrderCommand command) {
    Order order = orders.save(newOrder(command));
    inventory.decrease(command.productId(), command.quantity());
    outbox.save(newOrderEvent(order));
    return order.getId();
}
```

Các thao tác JPA tham gia cùng transaction do service mở (khi dùng cùng transaction manager/resource và không cố ý tách bằng propagation như `REQUIRES_NEW`).

### 3.2. Một use case, một boundary rõ nghĩa

Một method service có thể đặt tên phản ánh nghiệp vụ:

```java
placeOrder(...)
cancelOrder(...)
approveInvoice(...)
transferOwnership(...)
deactivateCustomer(...)
```

Khi đọc code, người khác nhận ra những bước nào phải nguyên tử.

Không nhất thiết đặt transaction quanh mọi helper nhỏ:

```java
normalizeEmail(...)
validateQuantity(...)
calculateTotal(...)
```

Các helper thuần Java không có truy cập database có thể chạy trước transaction để giảm thời gian giữ connection/lock, miễn việc validation không cần đọc state transactional.

## 4. Ví dụ nguyên tử: đặt hàng và trừ tồn kho

Mô hình tối giản:

```java
@Entity
@Table(name = "inventory_items")
public class InventoryItem {

    @Id
    private Long productId;

    @Column(nullable = false)
    private int available;

    @Version
    private long version;

    protected InventoryItem() {}

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Invalid quantity");
        }
        if (available < quantity) {
            throw new InsufficientInventoryException(productId);
        }
        available -= quantity;
    }
}
```

Entity đơn hàng:

```java
@Entity
@Table(name = "orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(nullable = false)
    private Long customerId;

    @Column(nullable = false)
    private String status;

    protected PurchaseOrder() {}

    public PurchaseOrder(Long customerId) {
        this.customerId = customerId;
        this.status = "PLACED";
    }

    public Long getId() {
        return id;
    }
}
```

Service minh họa:

```java
@Service
public class PlaceOrderService {

    private final EntityManager em;
    private final OutboxWriter outbox;

    public PlaceOrderService(
            EntityManager em,
            OutboxWriter outbox) {
        this.em = em;
        this.outbox = outbox;
    }

    @Transactional
    public Long place(PlaceOrderCommand command) {
        InventoryItem inventory = em.find(
            InventoryItem.class,
            command.productId()
        );

        if (inventory == null) {
            throw new ProductNotFoundException(
                command.productId()
            );
        }

        inventory.reserve(command.quantity());

        PurchaseOrder order = new PurchaseOrder(
            command.customerId()
        );

        em.persist(order);

        outbox.recordOrderPlaced(
            order.getId(),
            command.customerId()
        );

        return order.getId();
    }
}
```

Các exception, command và `OutboxWriter` là thành phần ứng dụng cần định nghĩa. Giả định `OutboxWriter` ghi bản ghi outbox bằng **cùng EntityManager/database transaction**, không publish trực tiếp qua mạng.

### 4.1. Dirty checking hoạt động khi nào?

`inventory` được tải dưới transaction nên managed trong persistence context. Gọi `inventory.reserve(...)` đổi field `available`; Hibernate có thể phát hiện và sinh SQL UPDATE khi flush.

`order` được `persist` đưa vào managed state và INSERT được thực hiện khi flush theo generator/mapping.

Service không cần gọi `inventoryRepository.save(inventory)` để Hibernate nhận biết thay đổi trên **managed entity**.

### 4.2. @Version bảo vệ một loại xung đột

Hai transactions cùng tải tồn kho còn 1 đơn vị có thể cùng gọi `reserve(1)` trong Java. Với `@Version`, Hibernate thường kiểm tra version khi UPDATE managed entity; một transaction có thể gặp optimistic locking conflict thay vì cả hai cùng trừ thành công.

Đây là một lớp bảo vệ concurrency, không phải lời cam kết mọi business invariant đều được giải quyết. Với lượng cạnh tranh cao có thể cân nhắc pessimistic lock hoặc atomic SQL conditional update.

### 4.3. Lỗi có thể xuất hiện tại commit

`place` có thể hoàn thành code Java nhưng transaction interceptor gặp `OptimisticLockException` hoặc constraint violation khi flush/commit sau khi method body đã trả ID.

Do đó, “method đã chạy tới return” không đồng nghĩa dữ liệu đã commit thành công. Caller nhận kết quả thành công chỉ sau khi proxy hoàn tất transaction nếu exception không phát sinh.

## 5. Persistence context trong transaction

Spring JPA integration thường liên kết một EntityManager thích hợp với transaction hiện hành. Các entity được load trong đó là **managed**:

```java
@Transactional
public void changeCustomerName(Long customerId, String name) {
    Customer customer = em.find(Customer.class, customerId);

    if (customer == null) {
        throw new CustomerNotFoundException(customerId);
    }

    customer.rename(name);
    // Không bắt buộc gọi em.merge(customer).
}
```

Khi flush, Hibernate kiểm tra thay đổi và tạo SQL. Khi transaction kết thúc, context transaction-scoped thường được đóng/giải phóng theo quản lý của Spring.

### 5.1. Identity map

Trong cùng context:

```java
Customer a = em.find(Customer.class, 10L);
Customer b = em.find(Customer.class, 10L);

System.out.println(a == b); // Thường true.
```

Đây là first-level cache/identity map. Nó giúp Hibernate quản lý nhất quán một entity identity trong unit of work.

### 5.2. Không giữ managed entity vượt transaction rồi kỳ vọng dirty checking

```java
Customer customer = service.loadCustomer(id);

// Nếu loadCustomer đã kết thúc transaction/context:
customer.rename("New name");

// Không tự có UPDATE chỉ vì object từng được managed.
```

Khi detached, setter không còn tự tạo SQL. Cách thường an toàn là gọi một application service method có transaction, load managed aggregate trong method ấy rồi áp thay đổi.

### 5.3. OSIV khiến trực giác khó hơn

Nếu Open Session in View đang bật, EntityManager có thể còn mở đến khi request kết thúc; entity chưa chắc detached ngay khi method service trả về. Nhưng transaction đã kết thúc và những lazy loads trong controller/serializer có thể phát SQL ngoài boundary nghiệp vụ.

**Đừng phụ thuộc OSIV** để che việc service trả entity chưa chuẩn bị fetch plan hoặc để thực hiện business updates ngoài `@Transactional`.

## 6. Flush, commit và rollback là ba thao tác khác nhau

Trong service:

```java
@Transactional
public void createCustomer(RegisterCommand command) {
    Customer customer = new Customer(command.email());
    em.persist(customer);

    em.flush();

    // SQL INSERT có thể đã chạy,
    // nhưng transaction chưa commit.
}
```

`flush()` yêu cầu Hibernate đồng bộ pending changes xuống database trong transaction; không làm dữ liệu trở thành committed cho mọi transaction khác.

### 6.1. Lý do gọi flush tường minh

Có thể cần flush để:

- Phát hiện constraint violations sớm hơn trong workflow.
- Bảo đảm SQL thay đổi trước đã chạy trước bước phụ thuộc.
- Nhận thông tin mà generator/mapping yêu cầu sau INSERT.
- Thiết lập điểm đồng bộ trước bulk DML hoặc clear theo chunk.

Không gọi flush sau từng setter chỉ để “đảm bảo lưu”, vì điều đó có thể tăng số round-trip và phá hiệu quả batching.

### 6.2. Exception tại flush

Nếu `em.flush()` ném constraint violation, không nên bắt rồi tiếp tục dùng EntityManager/transaction như chưa có chuyện gì. Transaction có thể rollback-only hoặc persistence context không còn phù hợp.

Thông thường rollback unit of work và mở transaction/context mới cho retry đúng cách.

### 6.3. Nếu không có @Transactional thì sao?

Một thao tác `persist`, `remove`, `executeUpdate` có thể cần transaction đang hoạt động theo JPA semantics. Nếu không có boundary hợp lệ, có thể gặp `TransactionRequiredException` hoặc hành vi không đáp ứng kỳ vọng.

Đừng giả định Spring sẽ luôn tự tạo transaction cho mọi lời gọi EntityManager tùy ý ngoài service.

## 7. Tại sao transaction boundary không nên trải dài đến controller?

Ví dụ không khuyến khích như mặc định:

```java
@RestController
public class OrderController {

    @Transactional
    @PostMapping("/orders")
    public OrderResponse place(@RequestBody OrderRequest request) {
        // Validate HTTP, gọi DB, gọi service,
        // map response và nhiều việc khác.
    }
}
```

Controller là HTTP adapter. Đặt transaction ở đây có thể khiến:

- Boundary phụ thuộc transport thay vì use case.
- Database transaction bị mở trong lúc mapping/serialization/logic HTTP.
- Business use case gọi từ scheduler/queue không có boundary tương đương.
- Controller khó unit test và tái sử dụng.
- Không rõ ai sở hữu rollback policy.

Mẫu rõ hơn:

```java
@RestController
public class OrderController {

    private final PlaceOrderService service;

    @PostMapping("/orders")
    public ResponseEntity<OrderResponse> place(
            @RequestBody OrderRequest request) {

        Long id = service.place(request.toCommand());

        return ResponseEntity
            .status(HttpStatus.CREATED)
            .body(new OrderResponse(id));
    }
}
```

Ở đây service chịu trách nhiệm atomic database unit; controller xử lý HTTP response.

### 7.1. Authorization ở đâu?

Authentication có thể được thực hiện bởi Spring Security filter trước controller. Application service vẫn nên nhận verified principal/tenant context và kiểm tra quyền nghiệp vụ liên quan resource ngay trong use case.

Đừng coi `@Transactional` là authorization. Transaction không ngăn một query thiếu tenant predicate đọc dữ liệu của tổ chức khác.

## 8. Vì sao transaction chỉ ở repository chưa đủ?

Spring Data JPA thường cung cấp transaction metadata cho những method kế thừa như `save`, `delete`, `findById` trong `SimpleJpaRepository` (với các mặc định phân biệt read/write). Nhưng **tính nguyên tử giữa nhiều repository operations phải do boundary bên ngoài quyết định**.

Ví dụ:

```java
public void transferBalance(
        Long fromId,
        Long toId,
        BigDecimal amount) {

    Account from = accounts.findById(fromId).orElseThrow();
    from.debit(amount);
    accounts.save(from);

    Account to = accounts.findById(toId).orElseThrow();
    to.credit(amount);
    accounts.save(to);
}
```

Nếu method không có outer transaction, từng repository operation có thể chạy trong transaction riêng. Sau khi repository find kết thúc, entity có thể detached; changes trong service không nhất thiết được dirty checked như bạn nghĩ.

Đặt boundary:

```java
@Transactional
public void transferBalance(
        Long fromId,
        Long toId,
        BigDecimal amount) {

    Account from = accounts.findById(fromId).orElseThrow();
    Account to = accounts.findById(toId).orElseThrow();

    from.debit(amount);
    to.credit(amount);
}
```

Hai accounts được load và sửa trong cùng persistence context. Khi transaction flush, Hibernate đồng bộ thay đổi; version/locking hoặc database constraints cần bảo vệ concurrent transfers.

### 8.1. Không phải repository method tự định nghĩa nào cũng transactional

Trong Spring Data JPA, method query do bạn tự khai báo có thể không tự nhận transaction configuration như các CRUD methods kế thừa; cần kiểm tra annotation và service boundary.

Đừng viết service không có transaction chỉ vì “repository interface extends JpaRepository”.

### 8.2. save không phải commit

`repository.save(entity)` trong một outer transaction thường thực hiện `persist` hoặc `merge` theo newness detection, không ép commit transaction ngay. Khi `save` return, SQL có thể còn pending cho tới flush/commit.

`saveAndFlush` yêu cầu flush nhưng vẫn **không tương đương commit**.

### 8.3. Managed entity không cần save lại chỉ để được ghi

Nếu `Customer` đã managed và thay field, dirty checking sẽ phát hiện trong transaction phù hợp.

Nhưng nếu nhận detached entity (ví dụ mapping từ request), `save` có thể chọn `merge` và **trả về managed copy**, không tự biến object truyền vào thành managed. Với partial update, load managed entity rồi apply command thường an toàn hơn merge object có nhiều field null.

## 9. Spring proxy: @Transactional chỉ có hiệu lực khi lời gọi được intercept

Trong proxy-based Spring transaction management thường dùng, Spring tạo một proxy bao quanh bean.

```text
OtherBean
    |
    v
TransactionalProxy
    |
    +-- Begin / join transaction
    |
    v
TargetService.method()
    |
    +-- Repository / Hibernate
    |
    v
Proxy commit / rollback
```

Khi caller gọi qua proxy, transaction advice có cơ hội áp dụng.

### 9.1. Self-invocation: this.method() bỏ qua proxy

Ví dụ có lỗi:

```java
@Service
public class ImportService {

    public void importAll(List<Row> rows) {
        for (Row row : rows) {
            saveOne(row); // Internal call trong cùng instance.
        }
    }

    @Transactional
    public void saveOne(Row row) {
        // DB writes...
    }
}
```

Lời gọi `saveOne(row)` đi trực tiếp trong target object, không qua transaction proxy. Vì vậy annotation trên `saveOne` có thể **không được áp dụng**.

### 9.2. Cách sửa: đặt boundary tại public entry point

Nếu toàn import cần một transaction:

```java
@Service
public class ImportService {

    @Transactional
    public void importAll(List<Row> rows) {
        for (Row row : rows) {
            saveOneInternal(row);
        }
    }

    private void saveOneInternal(Row row) {
        // DB writes tham gia transaction của importAll.
    }
}
```

Nếu từng chunk cần transaction riêng, tách thành Spring bean khác hoặc dùng programmatic `TransactionTemplate`.

### 9.3. Không lấy injection chính mình làm mặc định

Một số code tự inject proxy của chính mình để gọi method. Cách ấy tạo coupling và rủi ro vòng dependency/khó hiểu. Thường nên tách boundary thành service riêng hoặc tái cấu trúc use case rõ hơn.

### 9.4. Visibility và final methods

Với proxy mode:

- Public method là lựa chọn dễ hiểu/portable nhất.
- Hành vi interception cho protected/package-private phụ thuộc Spring version và loại proxy.
- Private methods không được override/intercept như public methods.
- Final class/final method có giới hạn với class-based proxy (CGLIB).
- Method được tạo ngoài Spring-managed bean không tự có transaction advice.

Với Kotlin, class/method final mặc định nên cần cấu hình compiler/plugin thích hợp hoặc kiến trúc proxy phù hợp.

Không kết luận “chỉ cần đặt annotation ở bất cứ method nào là được”.

### 9.5. AspectJ weaving khác proxy mode

Spring có thể dùng AspectJ mode để xử lý interception khác proxy-based mode và có thể giải quyết một số giới hạn self-invocation. Nhưng đó là lựa chọn triển khai cần cấu hình weaving/kiểm thử; không mặc định ứng dụng Spring Boot dùng nó.

## 10. Transaction propagation: lời gọi tham gia transaction nào?

Spring `@Transactional` có thuộc tính `propagation`:

```java
@Transactional(propagation = Propagation.REQUIRED)
public void doWork() {
    ...
}
```

`REQUIRED` là mặc định của Spring annotation: nếu đã có transaction thì tham gia; nếu chưa có thì tạo transaction mới.

### 10.1. Những propagation thường gặp

| Propagation | Ý nghĩa khái quát | Trường hợp cân nhắc |
|---|---|---|
| `REQUIRED` | Join transaction hiện có, hoặc tạo mới | Hầu hết application service operations |
| `REQUIRES_NEW` | Suspend transaction ngoài, tạo transaction độc lập | Một số audit/retry unit thực sự độc lập |
| `MANDATORY` | Chỉ chạy khi caller đã có transaction | Component bắt buộc tham gia một use case transaction |
| `SUPPORTS` | Có transaction thì join, không có thì chạy không transaction | Read helper có chính sách phù hợp |
| `NOT_SUPPORTED` | Suspend transaction hiện có, chạy ngoài transaction | Đoạn đọc/operation không muốn giữ DB transaction |
| `NEVER` | Báo lỗi nếu đang trong transaction | Component bắt buộc chạy ngoài transaction |
| `NESTED` | Savepoint nested trong physical transaction khi manager hỗ trợ | JDBC savepoint workflow cụ thể |

Propagation **không làm business workflow đúng một cách tự động**. Đặc biệt `REQUIRES_NEW` có thể phá atomicity nếu dùng cho những bước lẽ ra phải rollback cùng nhau.

## 11. REQUIRED: mặc định cho application service

Ví dụ:

```java
@Service
public class ApproveInvoiceService {

    private final InvoiceRepository invoices;
    private final LedgerService ledger;

    @Transactional
    public void approve(Long invoiceId) {
        Invoice invoice = invoices
            .findById(invoiceId)
            .orElseThrow();

        invoice.approve();

        ledger.recordApproval(invoice);
    }
}
```

Giả sử `LedgerService.recordApproval` dùng `@Transactional` mặc định `REQUIRED` và cùng transaction manager: nó **tham gia transaction hiện có**. Các database writes của invoice và ledger có thể rollback cùng nhau.

### 11.1. Có transaction scope nhưng không có “transaction lồng độc lập”

Một method REQUIRED bên trong method REQUIRED thường không tạo physical transaction thứ hai. Hai annotation có thể tương ứng hai *logical transaction scopes* nhưng cùng physical transaction.

Khi inner scope đánh dấu rollback-only, outer scope không thể tự quyết commit vật lý thành công.

### 11.2. Một repository.save() trong service transaction

`save` không tạo commit riêng khi nó tham gia outer REQUIRED transaction. Vì vậy việc có transaction metadata ở cả service và repository không tự tạo “nhiều commit”.

## 12. REQUIRES_NEW: độc lập về commit/rollback

Ví dụ:

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordAuditAttempt(AuditAttempt attempt) {
    em.persist(attempt);
}
```

Nếu caller đang có transaction:

```text
Outer transaction A
    |
    +-- suspended
    |
    +-- Inner transaction B (REQUIRES_NEW)
    |      INSERT audit_attempt
    |      COMMIT B
    |
    +-- resume A
    |
    +-- ROLLBACK A
```

B đã commit có thể **không rollback** khi A rollback. Điều này đúng nếu audit attempt phải được lưu bất kể transaction nghiệp vụ, nhưng là lỗi nếu audit đó chỉ được phép tồn tại khi business change commit.

### 12.1. REQUIRES_NEW không phải cách “chữa” transaction lỗi

Nếu outer transaction có lỗi và bị rollback-only, mở một inner REQUIRES_NEW để tiếp tục một vài SQL không cứu được atomicity của outer. Phải có chủ đích độc lập giữa các business units.

### 12.2. Connection pool

REQUIRES_NEW có thể cần thêm connection trong khi outer transaction vẫn giữ resources. Dưới tải cao, dùng nhiều REQUIRES_NEW lồng nhau có thể gây thiếu connection/deadlock hoặc chờ đợi dài.

Không thêm annotation này vào mọi repository method.

### 12.3. Self-invocation vẫn là vấn đề

`@Transactional(propagation = REQUIRES_NEW)` trên method được gọi bằng `this.method()` trong cùng class thường **không tạo transaction mới** ở proxy mode. Hãy để lời gọi qua một proxied bean hoặc dùng TransactionTemplate.

## 13. NESTED không giống REQUIRES_NEW

`Propagation.NESTED` có ý tưởng dùng database savepoints trong **cùng physical transaction**:

```text
BEGIN outer transaction
   |
   +-- SAVEPOINT s1
   |     operation B
   |     rollback to s1 nếu cần
   |
   +-- operation C
   |
COMMIT outer
```

Nếu outer rollback, toàn bộ thay đổi (kể cả phần đã release savepoint) vẫn rollback.

### 13.1. Không giả định JPA luôn hỗ trợ NESTED

Savepoint behavior phụ thuộc `PlatformTransactionManager` và JDBC driver. `DataSourceTransactionManager` có hỗ trợ nested transactions qua JDBC savepoints trong các điều kiện phù hợp; `JpaTransactionManager` không tự bảo đảm nested entity-manager state tương ứng.

Ngay cả khi JDBC savepoint rollback SQL, Hibernate persistence context đang quản lý entity có thể **không tự quay ngược Java object state** về snapshot trước savepoint.

Với JPA entity lifecycle, hãy thận trọng và integration-test thật kỹ hoặc thiết kế chunk boundary độc lập nếu cần partial rollback.

## 14. Rollback rules: mặc định chỉ một số exception gây rollback

Spring `@Transactional` theo defaults truyền thống:

- Rollback khi unchecked `RuntimeException` hoặc `Error` thoát ra.
- Không tự rollback vì một **checked exception** thông thường, trừ khi được cấu hình rollback rule khác.

Ví dụ:

```java
@Transactional
public void importDocument(ImportCommand command)
        throws IOException {

    em.persist(new Document(command.title()));

    if (command.fileIsUnreadable()) {
        throw new IOException("Failed to read source file");
    }
}
```

Nếu `IOException` là checked exception và không có rollback rule bổ sung, Spring có thể **commit database changes dù method ném IOException**.

### 14.1. rollbackFor

```java
@Transactional(rollbackFor = IOException.class)
public void importDocument(ImportCommand command)
        throws IOException {
    ...
}
```

Khi `IOException` thoát method được intercept, transaction mới có thể được rollback theo rule.

Trong những Spring version/cấu hình mới, có thể có cơ chế đặt default rollback policy khác (ví dụ rollback for all exceptions). Vì vậy khi làm việc trong codebase thực tế, phải kiểm tra **effective transaction configuration**, không chỉ thuộc lòng default của một phiên bản.

### 14.2. noRollbackFor

```java
@Transactional(
    noRollbackFor = BusinessWarningException.class
)
public void runProcess() {
    ...
}
```

Có thể dùng nếu exception biểu thị một trạng thái chấp nhận commit. Nhưng cần chắc rằng dữ liệu vẫn hợp lệ, không đơn giản dùng `noRollbackFor` để che lỗi.

### 14.3. Rule cụ thể hơn có thể thắng

Spring có thuật toán chọn rollback rule theo exception type/strength. Nếu cấu hình kết hợp `rollbackFor` và `noRollbackFor`, cần test đường exception thực tế để đảm bảo hành vi mong muốn.

## 15. Bắt exception bên trong transaction có thể dẫn đến commit ngoài ý định

Ví dụ:

```java
@Transactional
public void placeOrder(PlaceOrderCommand command) {
    em.persist(new PurchaseOrder(command.customerId()));

    try {
        auditWriter.recordAudit();
    } catch (RuntimeException ex) {
        log.warn("Audit failed", ex);
    }

    // Method trả thành công.
}
```

Nếu exception đã bị bắt và transaction chưa bị resource/inner scope đánh dấu rollback-only, interceptor có thể commit order dù audit thất bại.

Nếu audit **là phần bắt buộc của cùng business invariant**, không nên nuốt exception. Nên để transaction rollback hoặc chủ động đánh dấu rollback-only khi policy yêu cầu.

### 15.1. Exception bị bắt sau khi DB đã báo lỗi không chắc an toàn

Một constraint violation khi flush có thể làm transaction rollback-only và EntityManager không còn phù hợp để tiếp tục, dù Java code bắt exception. Không nên lấy “đã catch” làm bằng chứng có thể commit.

### 15.2. Mark rollback-only có chủ đích

Spring có API như `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()` trong scope phù hợp. Nhưng gọi API này tạo coupling tới infrastructure; thường domain/application nên dùng exception có ý nghĩa và để boundary quyết định rollback.

Chỉ dùng programmatic rollback-only khi cần kiểm soát kết quả đặc biệt và hiểu commit behavior.

## 16. UnexpectedRollbackException: vì sao outer catch không cứu được transaction?

Một tình huống:

```java
@Service
public class OuterService {

    private final InnerService inner;

    @Transactional
    public void run() {
        saveA();

        try {
            inner.doRequiredWork();
        } catch (RuntimeException ex) {
            log.warn("Continuing", ex);
        }

        saveC();
    }
}
```

`InnerService.doRequiredWork` là một method được proxy, có `@Transactional(REQUIRED)` và ném RuntimeException.

Khi exception đi qua inner transaction interceptor, nó có thể đánh dấu **physical transaction chung là rollback-only**. Outer catch exception và tiếp tục, nhưng khi outer proxy cố commit, Spring có thể ném:

```text
org.springframework.transaction.UnexpectedRollbackException
```

### 16.1. Đây là cơ chế bảo vệ

Spring không muốn caller hiểu “outer method thành công” khi transaction thực tế đã bị đánh dấu rollback. Lỗi báo rằng **không thể commit vì rollback-only**.

### 16.2. Cách xử lý đúng

- Nếu inner failure phải làm hỏng use case: để exception đi ra, rollback toàn bộ.
- Nếu inner work thật sự optional và phải độc lập: xem xét transaction riêng với `REQUIRES_NEW`, nhưng hiểu consistency/cost.
- Nếu cần partial rollback trong cùng DB transaction: xem khả năng savepoint/NESTED với đúng transaction manager.
- Nếu chỉ cần lưu cảnh báo không ảnh hưởng business: tách thành logging/telemetry ngoài transactional resource hoặc theo policy rõ.

Đừng cố bắt `UnexpectedRollbackException` rồi trả thành công cho operation đã rollback.

## 17. Isolation level: transaction nào nhìn thấy dữ liệu gì?

Ví dụ:

```java
@Transactional(isolation = Isolation.READ_COMMITTED)
public void updateInventory(...) {
    ...
}
```

Spring có các mức `Isolation.DEFAULT`, `READ_UNCOMMITTED`, `READ_COMMITTED`, `REPEATABLE_READ`, `SERIALIZABLE`.

Ý nghĩa tổng quát:

| Isolation | Một số đặc điểm |
|---|---|
| DEFAULT | Dùng mặc định của underlying database |
| READ_UNCOMMITTED | Có thể cho phép dirty reads tùy DB |
| READ_COMMITTED | Tránh dirty reads; kết quả các lần đọc có thể khác nhau |
| REPEATABLE_READ | Mức lặp lại đọc mạnh hơn; chi tiết và anomalies tùy DB |
| SERIALIZABLE | Semantics tương đương tuần tự hóa cao nhất, có thể thêm abort/retry |

Database triển khai bằng MVCC/locks khác nhau; ví dụ cùng tên `REPEATABLE_READ` không bảo đảm mọi anomaly được xử lý giống nhau ở PostgreSQL và MySQL.

### 17.1. Isolation khác optimistic locking

`@Version` giúp phát hiện một số xung đột update trên entity. Isolation level quyết định visibility và nhiều loại tương tác concurrent transaction. Hai cơ chế bổ sung cho nhau.

### 17.2. Isolation attribute thường chỉ có hiệu lực khi tạo transaction mới

Nếu một method `REQUIRED` tham gia transaction đã tồn tại, nó thường kế thừa physical transaction và isolation đang có; khai báo isolation khác tại inner method không tự thay isolation của connection đã mở.

Có thể cấu hình transaction manager để validate sự khác biệt, nhưng phải hiểu behavior thực tế. Không trông chờ `@Transactional(isolation = SERIALIZABLE)` ở một helper method tự tạo mức isolation mới trong outer transaction.

### 17.3. SERIALIZABLE không miễn retry

Mức isolation cao có thể khiến transaction bị abort do serialization conflict/deadlock. Ứng dụng phải xử lý retry toàn bộ unit of work khi phù hợp, thay vì giữ context lỗi rồi thực hiện lại vài statement.

## 18. @Version và optimistic locking ở application service

Ví dụ:

```java
@Entity
public class Account {

    @Id
    private Long id;

    @Version
    private long version;

    private BigDecimal balance;

    public void debit(BigDecimal amount) {
        if (balance.compareTo(amount) < 0) {
            throw new InsufficientFundsException();
        }
        balance = balance.subtract(amount);
    }
}
```

Hai giao dịch cùng load Account version 3. Nếu cùng update, Hibernate thường dùng điều kiện version:

```sql
UPDATE accounts
SET balance = ?, version = 4
WHERE id = ? AND version = 3;
```

Một transaction thành công, transaction kia có thể nhận optimistic locking exception khi flush/commit.

### 18.1. Vì sao service transaction vẫn cần concurrency policy?

`@Transactional` không tự bảo đảm “hai người đồng thời không thể trừ vượt tồn kho” nếu isolation/concurrency không phù hợp và không dùng version/lock/atomic SQL.

Những lựa chọn:

- Optimistic locking `@Version`.
- `LockModeType.PESSIMISTIC_WRITE`.
- Atomic conditional UPDATE như `where available >= :qty`.
- Unique/check/FK constraints.
- Transaction isolation phù hợp.

Chọn theo domain và mức contention.

### 18.2. Retry tại boundary ngoài transaction

Khi bị `OptimisticLockException`, không sửa lại object đang managed trong transaction lỗi và flush tiếp. Cần rollback transaction hiện tại và retry trong một **unit of work mới** với state được đọc lại.

Nếu dùng Spring Retry, chú ý thứ tự AOP interceptors giữa retry và transaction để mỗi attempt có transaction mới; một vòng retry bên trong cùng `@Transactional` chưa chắc đúng.

## 19. Pessimistic locking và thời gian giữ lock

Ví dụ:

```java
@Transactional
public void reserve(Long productId, int quantity) {
    InventoryItem stock = em.find(
        InventoryItem.class,
        productId,
        LockModeType.PESSIMISTIC_WRITE
    );

    if (stock == null) {
        throw new ProductNotFoundException(productId);
    }

    stock.reserve(quantity);
}
```

Database có thể giữ row lock từ khi lấy lock tới transaction end. Nếu service tiếp tục gọi remote API trong khi transaction vẫn mở, lock bị giữ lâu, tăng khả năng contention/timeouts.

Vì vậy **đặt transaction đúng vị trí** không chỉ là atomicity mà còn là **giữ transaction đủ ngắn**.

### 19.1. Quy tắc thực dụng

Trong transaction:

- Đọc state cần thiết.
- Kiểm tra invariant dựa trên DB state phù hợp.
- Thực hiện thay đổi đồng bộ.
- Ghi event/outbox nếu cần.
- Kết thúc nhanh.

Ngoài transaction:

- Parse file lớn.
- Gọi HTTP API chậm nếu không có cơ chế coordination.
- Chờ người dùng nhập liệu.
- Sleep/retry backoff.
- Render PDF/ảnh lớn.
- Gửi email hoặc publish remote message không được database transaction bảo vệ.

Không phải mọi loại công việc bên ngoài đều tuyệt đối cấm trong transaction, nhưng phải có lý do và hiểu chi phí locks/resources.

## 20. readOnly = true: hint tối ưu, không phải bảo vệ quyền

Ví dụ:

```java
@Transactional(readOnly = true)
public CustomerProfile getProfile(Long customerId) {
    Customer customer = em.find(
        Customer.class,
        customerId
    );

    return mapper.toProfile(customer);
}
```

`readOnly=true` biểu đạt mục đích chỉ đọc. Với Spring + Hibernate, integration có thể điều chỉnh flush mode và read-only state để giảm dirty checking/flush overhead. Hành vi cụ thể phụ thuộc Spring/Hibernate version và cấu hình.

### 20.1. readOnly không có nghĩa “không thể ghi”

Trong nhiều cấu hình, `@Transactional(readOnly = true)` là một hint, không phải quy tắc bảo mật được DB cưỡng chế tuyệt đối. Một số database/transaction manager có thể áp connection read-only hoặc chặn DML, nhưng không được giả định điều đó luôn xảy ra.

Không sử dụng `readOnly=true` thay cho authorization hoặc database grants.

### 20.2. Cảnh báo khi sửa entity trong read-only transaction

```java
@Transactional(readOnly = true)
public void accidentallyChange(Long id) {
    Customer customer = em.find(Customer.class, id);
    customer.rename("Oops");
}
```

Tùy integration/flush mode, thay đổi có thể không được flush như mong muốn. Việc method trả về bình thường không đảm bảo UPDATE đã chạy.

Các method ghi nên dùng transaction ghi thông thường, không dựa vào may rủi của provider.

### 20.3. Class-level readOnly mặc định

Một pattern:

```java
@Service
@Transactional(readOnly = true)
public class CustomerService {

    public CustomerDto find(Long id) {
        ...
    }

    @Transactional
    public void rename(Long id, String name) {
        ...
    }
}
```

Method `rename` override metadata transaction class-level khi được Spring intercept đúng. Tuy nhiên class-level annotation cũng có thể làm các method không chủ đích trở thành transaction-scoped; cân nhắc explicit method boundaries nếu codebase phức tạp.

## 21. Timeout: không để transaction treo vô hạn

```java
@Transactional(timeout = 10)
public void reserveInventory(...) {
    ...
}
```

Timeout theo đơn vị giây trong Spring annotation giúp mô tả thời gian tối đa cho transaction mới theo transaction manager hỗ trợ.

Giới hạn:

- Không phải đồng hồ hẹn giờ Java tự ngắt mọi dòng code.
- Database statement/network behavior khác nhau.
- Timeout có thể được áp tại statement hoặc transaction manager tùy resource.
- Nếu method tham gia existing transaction, timeout mới không nhất thiết thay được timeout outer.
- Connection pool, lock timeout và statement timeout là các lớp cấu hình khác nhau.

Một external API bị treo chưa chắc bị dừng đúng lúc do `@Transactional(timeout = 10)`. Thiết kế client timeout/circuit breaker riêng.

## 22. Lazy loading và ranh giới transaction

Ví dụ:

```java
@Entity
public class Customer {

    @OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
    private List<PurchaseOrder> orders;
}
```

Service chỉ load Customer:

```java
@Transactional(readOnly = true)
public Customer loadCustomer(Long id) {
    return em.find(Customer.class, id);
}
```

Caller ngoài transaction gọi:

```java
Customer customer = service.loadCustomer(id);
customer.getOrders().size();
```

Nếu persistence context đã đóng và collection chưa initialized, Hibernate có thể ném:

```text
org.hibernate.LazyInitializationException:
    failed to lazily initialize a collection
```

### 22.1. Không sửa bằng cách kéo transaction lên controller một cách máy móc

Tốt hơn, service biết cần trả dữ liệu nào:

```java
@Transactional(readOnly = true)
public CustomerDetail getCustomerDetail(Long id) {
    Customer customer = em.createQuery("""
        select c
        from Customer c
        left join fetch c.primaryAddress
        where c.id = :id
        """, Customer.class)
        .setParameter("id", id)
        .getSingleResult();

    return mapper.toDetail(customer);
}
```

Giả định `primaryAddress` là association to-one đã mapping và `CustomerDetail` là DTO ứng dụng.

### 22.2. DTO trong boundary

Map entity sang DTO **trong transaction đọc**, sử dụng `JOIN FETCH`, EntityGraph, batch fetching hoặc DTO projection có chủ đích.

Đừng trả entity chứa lazy graph chưa xác định sang JSON serializer rồi mong OSIV luôn tự xử lý đúng hiệu năng và security.

### 22.3. Collection fetch join và pagination

Một query fetch collection có thể nhân SQL rows. Kết hợp pagination cần cẩn thận; Hibernate có thể paginate in memory hoặc cảnh báo/lỗi tùy cấu hình.

Với trang đơn hàng kèm lines, thường nên:

1. Query page IDs/DTO root với ORDER BY ổn định.
2. Query lần hai fetch association theo IDs cần thiết.
3. Map DTO trong service transaction.

## 23. Tầng đọc có cần transaction không?

Một query SELECT đơn lẻ có thể chạy khi không có explicit service `@Transactional` trong một số cấu hình. Nhưng một read use case gồm nhiều query hoặc lazy association có thể hưởng lợi từ transaction:

- Một persistence context nhất quán trong thời gian thao tác.
- Ranh giới rõ cho entity lifecycle/fetch plan.
- Khả năng áp isolation/readOnly policy.
- Giảm sự phụ thuộc vào OSIV.

Ví dụ:

```java
@Transactional(readOnly = true)
public ReportDto buildCustomerReport(Long id) {
    Customer c = em.find(Customer.class, id);
    long total = countOrders(id);
    BigDecimal paid = sumPaidOrders(id);

    return new ReportDto(
        c.getId(), total, paid
    );
}
```

Tuy nhiên, `readOnly=true` không tự đảm bảo mọi query thấy cùng snapshot; điều đó còn phụ thuộc database isolation và SQL thực thi.

### 23.1. Read-only transaction vẫn dùng database resources

Đừng giữ transaction đọc mở trong lúc chờ remote API hoặc tạo báo cáo rất lâu không cần DB. Có thể lấy DTO/snapshot cần thiết trong transaction ngắn rồi tính toán thuần Java sau đó.

## 24. @Transactional ở interface, method và class

Spring có thể phát hiện transaction metadata từ các vị trí khác nhau:

```java
@Transactional(readOnly = true)
public interface CustomerQueryService {
    CustomerDto find(Long id);
}
```

hoặc:

```java
@Service
public class CustomerQueryServiceImpl {

    @Transactional(readOnly = true)
    public CustomerDto find(Long id) {
        ...
    }
}
```

Hỗ trợ annotation trên interface/class/method và cách override có thể phụ thuộc Spring version, proxy mode và cấu hình. Với code cần rõ ràng và tránh bất ngờ khi chuyển JDK proxy/CGLIB/AspectJ, thường nên đặt boundary **trên public implementation service method hoặc class** theo convention nhất quán.

### 24.1. Method được kế thừa và method override

Khi thay đổi inheritance hoặc chuyển annotation từ interface sang implementation, cần test transaction thực tế. Không dựa vào suy luận “annotation trên interface chắc chắn được mọi cơ chế weaving nhìn thấy”.

### 24.2. Multiple transaction managers

Ứng dụng có hai databases hoặc JPA + Kafka có thể có nhiều transaction managers:

```java
@Transactional(transactionManager = "ordersTransactionManager")
public void createOrder(...) {
    ...
}
```

Chọn manager phải đúng resource. Một annotation sử dụng một local `JpaTransactionManager` không tự tạo atomic commit xuyên hai databases hoặc với broker.

## 25. External API, message broker và email nằm ngoài local DB transaction

Giả sử:

```java
@Transactional
public void placeAndCharge(OrderCommand command) {
    em.persist(new PurchaseOrder(...));
    paymentGateway.charge(command.payment());
}
```

Vấn đề có thể xảy ra:

- Gateway charge thành công.
- Database commit thất bại.
- Tiền đã bị charge nhưng order không tồn tại.

Hoặc:

- Database đã ghi order.
- Gateway timeout nhưng request có thể đã xử lý.
- Application retry thiếu idempotency gây double charge.

**Local database transaction không rollback được một HTTP request đã thành công**.

### 25.1. Không giải quyết bằng việc bọc mọi thứ trong @Transactional

Annotation không biến email, HTTP hoặc broker publish thành cùng ACID transaction với Hibernate.

Thay vào đó cần design coordination:

- **Transactional outbox** khi cần phát event sau commit bền vững.
- **Saga/process manager** cho workflow nhiều service với compensating actions.
- **Idempotency keys** khi gọi payment hoặc job retry.
- **Reservation/confirmation state machine** cho các bước dài.
- Distributed transaction/XA chỉ khi hệ thống thực sự hỗ trợ và chấp nhận độ phức tạp.

### 25.2. Transactional outbox

Trong service transaction:

```java
@Transactional
public Long place(OrderCommand command) {
    PurchaseOrder order = new PurchaseOrder(...);
    em.persist(order);

    em.persist(new OutboxEvent(
        "ORDER_PLACED",
        order.getId(),
        serializeEvent(order)
    ));

    return order.getId();
}
```

Sau commit, một outbox publisher riêng đọc event và gửi broker; có retry/at-least-once delivery + consumer idempotency theo thiết kế.

`serializeEvent` không nên tự tạo side effect ngoài DB trong transaction. Event dữ liệu nên mang IDs và thông tin cần thiết, không serialize nguyên Hibernate managed graph/lazy collection.

### 25.3. @TransactionalEventListener AFTER_COMMIT

Spring có `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` cho event listener chạy sau commit khi có transaction phù hợp.

Nó hữu ích cho callback không yêu cầu bảo đảm delivery bền vững, nhưng nếu process crash sau commit trước khi gửi message thì callback có thể không thực hiện. **AFTER_COMMIT listener không tự thay thế persistent outbox**.

Nếu callback sau commit muốn ghi DB mới, cần chú ý transaction/resources có thể vẫn gắn với thread trong cleanup phase; thường nên mở transaction mới có chủ đích thay vì giả định lời ghi tự commit trong transaction đã kết thúc.

## 26. Phân biệt DB transaction với business transaction dài

Một quy trình thanh toán có thể gồm:

```text
Create order -> Reserve inventory -> Charge card
-> Confirm payment -> Arrange shipment
```

Nó có thể kéo dài giây/phút và nhiều services. Không nên giữ một SQL transaction mở xuyên toàn bộ quy trình đó.

Thay bằng trạng thái:

```text
NEW
 -> INVENTORY_RESERVED
 -> PAYMENT_PENDING
 -> PAID
 -> FULFILLMENT_PENDING
 -> COMPLETED
```

Mỗi transition thường là **một local transaction ở application service**, với outbox/idempotency và compensation khi có lỗi.

### 26.1. Transaction đúng quy mô

- **Nhỏ quá:** các cập nhật của một invariant bị commit riêng.
- **Lớn quá:** giữ locks/connections lâu, khó retry và dễ deadlock.
- **Vừa đủ:** bao những thay đổi database cần nguyên tử trong một use case đồng bộ.

Đây là lý do “đặt ở application service” là starting point có giá trị: service nhìn được toàn bộ invariant và dependencies.

## 27. @Async, CompletableFuture và giới hạn ThreadLocal transaction

Trong Spring proxy transaction management phổ biến, transaction context gắn với **thread thực thi** thông qua transaction synchronization/resources.

Ví dụ:

```java
@Transactional
public void createAndNotify() {
    em.persist(new NotificationRecord(...));

    asyncSender.sendAsync(...);
}
```

Nếu `sendAsync` chạy ở thread khác, **nó không tự tham gia transaction của thread caller**. Nó có thể thấy database chưa commit hoặc gọi external API trước khi caller rollback.

### 27.1. Không kỳ vọng propagation qua thread boundary

`@Async`, `CompletableFuture.supplyAsync`, executor, scheduled task hoặc reactive pipelines có mô hình context khác nhau. Không chuyển một `EntityManager` stateful sang worker thread để dùng chung, vì EntityManager/Session không thread-safe.

### 27.2. Các chiến lược phù hợp

- Để async task nhận **ID/immutable command data**, mở transaction riêng nếu cần DB.
- Chỉ enqueue work sau commit theo cơ chế phù hợp.
- Dùng outbox nếu cần bảo đảm event/delivery.
- Dùng transaction/context propagation đặc thù của reactive stack nếu ứng dụng dùng R2DBC/reactive APIs, không copy nguyên ví dụ thread-bound JPA.

### 27.3. Future return không đồng nghĩa mọi async code đã chạy trong transaction

Một `@Transactional` method trả `CompletableFuture` có thể có behavior riêng theo Spring version cho trạng thái Future đã thất bại ngay tại thời điểm return. Nhưng transaction không kéo dài tự động cho công việc còn chạy trong thread khác sau khi method được intercept hoàn tất.

Cần kiểm tra version và thiết kế explicit async unit of work.

## 28. Bulk DML trong service transaction

Ví dụ:

```java
@Transactional
public int deactivateExpired(Instant cutoff) {
    return em.createQuery("""
        update Customer c
        set c.active = false
        where c.expiredAt < :cutoff
        """)
        .setParameter("cutoff", cutoff)
        .executeUpdate();
}
```

Bulk HQL/JPQL DML chạy trong transaction nhưng **không đồng bộ từng managed entity trong persistence context** như dirty checking.

Hệ quả:

- Entity đã load trước bulk có thể stale.
- `@Version` không tự tăng như managed update mặc định.
- `@PreUpdate` callbacks không được gọi per-entity.
- L2/query cache có các cơ chế invalidation riêng.
- Transaction vẫn rollback bulk SQL cùng những thay đổi khác nếu cùng resource/boundary.

### 28.1. Khi cần flush → bulk → clear

```java
@Transactional
public int bulkUpdate(...) {
    em.flush();

    int affected = em.createQuery(...).executeUpdate();

    em.clear();
    return affected;
}
```

Pattern này có thể phù hợp nếu có managed state pending trước DML và không muốn tiếp tục dùng stale objects sau đó.

Nhưng `clear()` detach **toàn bộ** managed entities, không chỉ những entity bị bulk update. Nếu còn pending changes chưa flush, chúng có thể bị mất.

Đừng thêm `clear()` vào service lớn đang thao tác nhiều aggregates khi chưa hiểu tác động.

### 28.2. Spring Data @Modifying

```java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query("""
    update Customer c
    set c.active = false
    where c.expiredAt < :cutoff
    """)
int deactivateExpired(@Param("cutoff") Instant cutoff);
```

Các flag giúp flush EntityManager trước và clear sau query method, nhưng không tạo per-entity lifecycle semantics. Transaction boundary ở service vẫn là nơi tốt để điều phối use case.

## 29. Batch import: một transaction cho toàn bộ hay mỗi chunk?

Một import 200.000 rows không nhất thiết phù hợp với một transaction duy nhất.

### 29.1. Một transaction toàn job

```java
@Transactional
public void importAll(Stream<Row> rows) {
    int count = 0;
    for (Row row : (Iterable<Row>) rows::iterator) {
        em.persist(map(row));

        if (++count % 100 == 0) {
            em.flush();
            em.clear();
        }
    }
}
```

`flush/clear` giúp giới hạn memory/persistence context. Nhưng **không commit mỗi 100 rows**. Nếu lỗi cuối cùng khiến transaction rollback, toàn bộ job có thể rollback.

### 29.2. Transaction riêng mỗi chunk

```java
@Service
public class ChunkWriter {

    @Transactional
    public void writeChunk(List<Row> chunk) {
        for (Row row : chunk) {
            em.persist(map(row));
        }
    }
}
```

Coordinator:

```java
@Service
public class ImportCoordinator {

    private final ChunkWriter writer;

    public void importAll(Iterable<List<Row>> chunks) {
        for (List<Row> chunk : chunks) {
            writer.writeChunk(chunk);
        }
    }
}
```

Vì coordinator gọi **một bean có proxy khác**, mỗi `writeChunk` có thể có transaction riêng nếu không có outer transaction và propagation mặc định REQUIRED.

### 29.3. Trade-off

- Một transaction: atomic cả job nhưng dài, rollback lớn.
- Nhiều transaction: bounded locks/retry nhưng partial progress, cần checkpoint/idempotency.
- Một chunk không nhất thiết trùng một aggregate; cần giữ parent-child dependency và invariant đúng.
- `REQUIRES_NEW` trong outer transaction không phải mặc định tốt cho batch, có thể gây connection overhead và partial commit phức tạp.

## 30. TransactionTemplate khi boundary động hoặc nhiều bước

Nếu cần kiểm soát transaction programmatically:

```java
@Service
public class ChunkImportCoordinator {

    private final TransactionTemplate txTemplate;
    private final EntityManager em;

    public ChunkImportCoordinator(
            PlatformTransactionManager txManager,
            EntityManager em) {

        this.txTemplate = new TransactionTemplate(txManager);
        this.em = em;
    }

    public void importChunks(List<List<Row>> chunks) {
        for (List<Row> chunk : chunks) {
            txTemplate.executeWithoutResult(status -> {
                for (Row row : chunk) {
                    em.persist(map(row));
                }
            });
        }
    }
}
```

Ví dụ có `Row` và `map` là logic ứng dụng. Spring `TransactionTemplate` cho phép mô tả rõ start/end transaction per chunk khi proxy self-invocation không phù hợp.

### 30.1. Cần manager phù hợp

Với JPA, cấu hình template dùng đúng `JpaTransactionManager` hoặc transaction manager đã được tích hợp cho EntityManager. Nếu ứng dụng có nhiều managers, không dùng một manager tùy ý rồi giả định JPA repository tham gia.

### 30.2. Đừng nhét mọi business logic vào TransactionTemplate

Programmatic boundary hữu ích cho looping, retry orchestration và trường hợp phức tạp. Với use case đơn giản, `@Transactional` ở public application service method dễ đọc và ít boilerplate hơn.

## 31. Transaction rollback và retry: lỗi tạm thời cần unit mới

Các lỗi có thể yêu cầu retry:

- Optimistic locking conflict.
- Deadlock victim.
- Serialization failure.
- Một số transient database availability errors.

Nhưng không phải lỗi nào cũng nên retry:

- Unique constraint violation do input trùng hợp lệ.
- Validation failure.
- FK violation do dữ liệu sai.
- Authorization denial.
- SQL syntax/mapping bug.

### 31.1. Retry phải bao cả transaction

Sai về ý tưởng:

```java
@Transactional
public void doWork() {
    for (int i = 0; i < 3; i++) {
        try {
            executeStatements();
            return;
        } catch (OptimisticLockException ex) {
            // Tiếp tục trong cùng transaction đã lỗi?
        }
    }
}
```

Không nên cố tiếp tục sử dụng entity/context của transaction có lỗi.

Cách đúng về kiến trúc:

```text
Retry orchestrator (ngoài transaction)
     |
     +-- Attempt 1 -> new transaction -> conflict -> rollback
     |
     +-- Attempt 2 -> new transaction -> reload state -> commit
```

Nếu dùng Spring Retry hoặc retry template, đảm bảo mỗi attempt đi qua transaction proxy/TransactionTemplate mới và operation idempotent khi side effects có thể đã xảy ra.

## 32. Transaction với nhiều data sources

Ví dụ:

```java
@Transactional("ordersTransactionManager")
public void createOrderAndInvoice() {
    ordersDb.saveOrder();
    billingDb.saveInvoice();
}
```

Nếu `ordersDb` và `billingDb` dùng **hai resources/transaction managers khác nhau**, annotation đặt vào một manager không bảo đảm cả hai commit/rollback nguyên tử.

Các phương án:

- Distributed/JTA/XA transaction khi thật sự cần và hạ tầng hỗ trợ.
- Saga/outbox/eventual consistency giữa services/databases.
- Consolidate những thay đổi cần nguyên tử vào cùng database/transaction nếu domain cho phép.
- Đánh dấu ranh giới consistency và compensation minh bạch.

Không dùng hai `@Transactional` annotations như cách đơn giản tạo distributed ACID.

## 33. Tenant context và authorization vẫn phải đặt đúng trong transaction

Trong multi-tenant application, tenant context phải được xác thực và gắn với đúng persistence session/connection **trước** khi query.

Ví dụ:

```java
@Transactional
public void renameDocument(
        AuthenticatedUser user,
        UUID organizationId,
        Long documentId,
        String newTitle) {

    membership.requireActive(user, organizationId);

    Document document = documents
        .findByIdAndOrganizationId(documentId, organizationId)
        .orElseThrow(DocumentNotFoundException::new);

    policy.requireCanEdit(user, document);

    document.rename(newTitle);
}
```

Ở đây `@Transactional` giữ các DB operations trong một unit, nhưng **không tự thêm WHERE tenant hoặc kiểm tra permission**. Repository scope và policy check vẫn phải chính xác.

### 33.1. Tránh thay tenant giữa transaction

Nếu Hibernate Session đang gắn tenant A, đổi biến tenant context sang B ở giữa method không biến Session thành B. Có thể tạo cross-tenant data access bug nếu application dùng resolver/connection routing sai.

Mỗi unit of work nên có một effective tenant rõ ràng; cross-tenant admin operations cần execution mode riêng và audit chặt.

### 33.2. Async mất tenant context

Tenant context dựa trên ThreadLocal không nhất thiết được truyền qua `@Async`/thread pool. Một async service có transaction riêng phải nhận verified tenant identifier đúng và không dùng giá trị sót lại từ request trước.

## 34. Transactional tests: khi test xanh nhưng production sai

Spring Test có thể chạy test method trong transaction rồi rollback sau test:

```java
@SpringBootTest
@Transactional
class OrderServiceTest {

    @Test
    void placeOrder() {
        service.place(...);
        // Test và service có thể join cùng test transaction.
    }
}
```

Điều này tiện cho cleanup nhưng có thể che một số vấn đề:

- Service method thiếu transaction riêng nhưng test đã cung cấp sẵn transaction.
- Exception tại commit chưa xảy ra vì test rollback thay vì commit.
- Lazy loading hoạt động vì test context còn mở.
- Database constraints deferred tới commit chưa được kiểm tra.
- REQUIRES_NEW behavior khác mong đợi.

### 34.1. Test ranh giới thật

Cho một số integration tests:

- Gọi public service method qua Spring bean/proxy như production.
- Không bọc test method trong outer transaction, hoặc dùng `TestTransaction`/cơ chế phù hợp để kết thúc transaction thật.
- Xác nhận commit và rollback bằng một EntityManager/context mới.
- Kiểm tra SQL/constraints ở flush/commit.
- Kiểm tra exception propagation/self-invocation.
- Kiểm tra concurrency với transactions/threads riêng.
- Kiểm tra permission/tenant với users khác nhau.

### 34.2. Test rollback use case

Ví dụ:

```text
Given:
    inventory = 5
When:
    service.placeOrder fails during outbox insert
Then:
    no order committed
    inventory remains 5
    no outbox row committed
```

Để test thực tế, inject failure trong cùng DB transaction và đọc lại dữ liệu ở context mới sau rollback. Không chỉ assert exception được ném.

### 34.3. Test checked exception

Nếu use case ném checked exception sau khi persist, kiểm tra `rollbackFor` theo annotation/config thực tế. Một assertion “method ném IOException” không chứng minh SQL đã rollback.

## 35. Các lỗi phổ biến khi đặt @Transactional

| Sai lầm | Hệ quả có thể xảy ra | Cách xử lý |
|---|---|---|
| Chỉ có transaction ở từng repository call | Một phần use case commit trước khi bước khác lỗi | Đặt outer boundary ở application service |
| Đặt @Transactional vào private method | Proxy không intercept như mong đợi | Public proxied service method/TransactionTemplate |
| Gọi `this.innerTransactionalMethod()` | Self-invocation bỏ qua proxy | Tách bean hoặc boundary ở entry point |
| Tạo service bằng `new` thay vì Spring DI | Không có transactional proxy | Dùng Spring-managed beans |
| Dùng final method với class-based proxy | Advice có thể không áp | Thiết kế proxy-compatible |
| Bắt RuntimeException rồi return success | Có thể commit lỗi hoặc rollback-only bất ngờ | Không nuốt lỗi invariant |
| Checked exception không có rollbackFor | Có thể commit dù method ném lỗi | Rollback policy rõ và kiểm thử |
| Catch inner REQUIRED exception rồi outer commit | `UnexpectedRollbackException` | Hiểu rollback-only và refactor boundary |
| Dùng REQUIRES_NEW cho từng repository | Partial commit, thêm connections | Chỉ dùng khi thật sự độc lập |
| Nghĩ NESTED luôn hỗ trợ JPA rollback entity state | Savepoint/Session mismatch | Kiểm tra transaction manager |
| Gọi flush rồi nghĩ đã commit | Dữ liệu vẫn rollback được | Phân biệt flush và commit |
| Trả managed entity rồi lazy-load trong controller | LazyInitializationException/N+1 | DTO/fetch plan trong service |
| Bật OSIV để chữa mọi lazy lỗi | Query ngoài boundary nghiệp vụ | Thiết kế transaction/read model rõ |
| Sửa entity trong readOnly=true | Có thể không được flush | Chọn write transaction |
| Dùng @Transactional để gói HTTP payment + DB | Local rollback không undo remote charge | Outbox/saga/idempotency |
| Gọi @Async rồi tin nó join transaction | Work ở thread khác | Async transaction/context riêng |
| Retry trong transaction đã lỗi | EntityManager/tx rollback-only | Retry toàn unit mới |
| Multi-DB trong một local transaction manager | Không atomic hai databases | XA/saga/outbox |
| Test luôn @Transactional | Che thiếu boundary và commit-time errors | Test qua proxy với commit thật |
| Bulk update rồi đọc managed entity cũ | Persistence context stale | Flush/clear/refresh có chủ đích |

## 36. Bài tập 1: xác định boundary của chuyển tiền

Đoạn code:

```java
public void transfer(Long fromId, Long toId, BigDecimal amount) {
    accounts.debit(fromId, amount);
    accounts.credit(toId, amount);
}
```

`debit` và `credit` mỗi method có transaction riêng.

**Câu hỏi:** Nếu debit thành công nhưng credit gặp lỗi?

**Giải thích:** Debit có thể đã commit độc lập. Đặt một `@Transactional` ở public application service `transfer` và bảo đảm cả hai repository updates tham gia cùng transaction. Đồng thời dùng version/locking/constraints để xử lý concurrent transfers.

## 37. Bài tập 2: self-invocation

```java
@Service
public class BatchService {

    public void run() {
        processChunk();
    }

    @Transactional
    public void processChunk() {
        em.persist(...);
    }
}
```

**Câu hỏi:** Vì sao `processChunk` có thể không chạy trong transaction?

**Giải thích:** `run` gọi internal method trên cùng object, bỏ qua transactional proxy trong Spring proxy mode. Gọi qua bean khác hoặc đặt `@Transactional` lên `run` nếu boundary phù hợp.

## 38. Bài tập 3: checked exception

```java
@Transactional
public void importRow() throws IOException {
    em.persist(new Item(...));
    throw new IOException("Bad file");
}
```

**Câu hỏi:** Spring mặc định có rollback không?

**Giải thích:** Với default rules truyền thống, checked IOException không tự kích hoạt rollback. Khai báo `rollbackFor = IOException.class` nếu transaction phải rollback, hoặc cấu hình global rollback defaults theo phiên bản phù hợp.

## 39. Bài tập 4: rollback-only

```java
@Transactional
public void outer() {
    try {
        innerService.saveRequired(); // @Transactional(REQUIRED)
    } catch (RuntimeException ex) {
        log.info("Ignoring");
    }
}
```

**Câu hỏi:** Vì sao có thể nhận `UnexpectedRollbackException` khi outer kết thúc?

**Giải thích:** Inner transactional interceptor đã đánh dấu physical transaction chung rollback-only. Outer catch exception không xóa dấu ấy; commit không thể thành công.

## 40. Bài tập 5: readOnly và lazy loading

```java
@Transactional(readOnly = true)
public Customer getCustomer(Long id) {
    return em.find(Customer.class, id);
}
```

Controller gọi `customer.getOrders().size()` sau khi service trả.

**Câu hỏi:** Vì sao có thể có `LazyInitializationException`?

**Giải thích:** Association chưa được load và persistence context có thể đã đóng. Cách phù hợp là trả DTO được xây trong transaction với fetch plan thích hợp, không kéo boundary lên controller theo phản xạ.

## 41. Bài tập 6: gửi email trong transaction

```java
@Transactional
public void register(...) {
    em.persist(newUser);
    mailer.sendWelcomeEmail(newUser);
}
```

**Câu hỏi:** Nếu mail gửi thành công rồi DB commit thất bại, có rollback email không?

**Giải thích:** Không. Email nằm ngoài local DB transaction. Nếu cần đồng bộ bền vững, ghi outbox email event trong DB transaction và xử lý gửi sau commit với retry/idempotency.

## 42. Bài tập 7: mỗi chunk một commit

```java
@Transactional
public void importAll(List<Row> rows) {
    for (...) {
        em.persist(...);
        if (chunkDone) {
            em.flush();
            em.clear();
        }
    }
}
```

**Câu hỏi:** Các chunks đã commit độc lập chưa?

**Giải thích:** Chưa. Flush/clear không commit. Muốn mỗi chunk commit riêng, cần transaction boundary thật, ví dụ `ChunkWriter.writeChunk` qua proxied bean hoặc TransactionTemplate bên ngoài.

## 43. Checklist thiết kế transaction ở application service

Khi review một use case Hibernate/Spring, hãy kiểm tra:

1. **Atomic unit:** Những thay đổi nào phải commit hoặc rollback cùng nhau?
2. **Service entry point:** Method nào thực sự đại diện cho use case?
3. **Proxy interception:** Method có được gọi qua Spring-managed bean/proxy không?
4. **Self-invocation:** Có internal calls khiến annotation bị bỏ qua không?
5. **Transaction manager:** Mọi JPA repositories có dùng đúng manager/resource?
6. **Propagation:** Có inner `REQUIRES_NEW` vô tình tách commit không?
7. **Rollback rules:** Checked/unchecked exceptions và catch blocks có đúng policy?
8. **Rollback-only:** Có inner failures bị nuốt khiến outer commit bất ngờ?
9. **Persistence context:** Entities có managed khi setters chạy không?
10. **Flush/commit:** Có hiểu lỗi phát sinh ở flush/commit không?
11. **Concurrency:** Version, locks, atomic predicates và constraints đã đủ?
12. **Isolation:** Mức hiện tại có đáp ứng read/write anomalies quan trọng?
13. **readOnly:** Method chỉ đọc thật sự không? Có đúng flush semantics?
14. **Fetch plan:** Có tránh lazy loading ngoài boundary, N+1, Cartesian product?
15. **OSIV:** Có đang dựa vào Session mở trong controller/serializer không?
16. **Thời gian:** Có external HTTP, sleep, file parsing hoặc render lâu bên trong transaction?
17. **External effects:** Email/payment/broker có cần outbox/saga/idempotency?
18. **Async:** Thread khác có transaction/context/tenant riêng hợp lệ?
19. **Bulk DML:** Context sau update có stale và cần clear/refresh không?
20. **Batch:** Transaction toàn job hay từng chunk? Có checkpoint/partial progress?
21. **Multiple DBs:** Local transaction có đủ bao phủ resources không?
22. **Authorization/tenant:** Có scope và policy đúng, độc lập annotation?
23. **Testing:** Đã test qua proxy, commit/rollback thật, concurrency, failure injection?
24. **Observability:** Log/metrics có cho thấy transaction timeout, retry và slow queries?
25. **Reusability:** Use case gọi từ HTTP, queue, CLI đều giữ cùng boundary?

Một service transaction tốt phải đúng về **nghiệp vụ, lifetime, concurrency và side effects**, không chỉ qua được một unit test.

## 44. Những nguyên tắc cần ghi nhớ

- **`@Transactional` đặt ở application service** thường là cách rõ ràng nhất để bao quanh một ca sử dụng database cần tính nguyên tử.
- Transaction ở repository có giá trị cho thao tác riêng, nhưng **không thay outer transaction** nếu use case gọi nhiều repositories.
- Spring transaction hoạt động qua infrastructure/proxy hoặc weaving phù hợp; **self-invocation, private/final methods hoặc bean không được Spring quản lý** có thể khiến advice không chạy.
- `Propagation.REQUIRED` mặc định thường tham gia transaction hiện có; `REQUIRES_NEW` tạo transaction độc lập và có thể commit dù outer rollback.
- `NESTED` là savepoint semantics tùy transaction manager, **không** tương đương REQUIRES_NEW và không tự reset Hibernate managed state.
- Spring rollback defaults truyền thống ưu tiên unchecked exceptions; với checked exceptions cần `rollbackFor` hoặc policy tương ứng.
- **Bắt exception không tự rollback**; một inner REQUIRED scope có thể đánh dấu rollback-only, khiến outer gặp `UnexpectedRollbackException`.
- `flush()` gửi SQL pending nhưng **không commit**. Lỗi optimistic lock/constraint có thể xuất hiện khi flush hoặc lúc interceptor commit.
- Managed entities được Hibernate dirty checked trong persistence context; không nhất thiết phải `save` lại entity managed sau mỗi setter.
- `readOnly=true` là hint/optimization, **không phải cơ chế authorization hay bảo đảm tuyệt đối cấm ghi**.
- `@Version`, locks và database constraints giải quyết concurrency; `@Transactional` đơn lẻ không đủ bảo vệ mọi invariant.
- Đọc và map DTO trong service transaction với fetch plan phù hợp; không phụ thuộc OSIV để lazy-load trong controller.
- Database transaction nên **ngắn**, tránh giữ locks trong lúc gọi external API hoặc thực hiện công việc lâu.
- **Local DB transaction không rollback HTTP/email/broker**; dùng outbox, saga, idempotency và các boundary phối hợp khi cần.
- `@Async` và thread pool không tự kế thừa transaction của caller; EntityManager/Session không thread-safe.
- Flush/clear theo chunk giúp memory, nhưng **không tạo per-chunk commit** nếu vẫn nằm trong một outer transaction.
- Test cần bao gồm **proxy entry point, commit/rollback, failure injection và concurrency**, không chỉ test methods luôn được bọc một test transaction.

**Kết luận:** `@Transactional` là công cụ khai báo ranh giới giao dịch rất tiện trong Spring, nhưng chỉ phát huy đúng tác dụng khi được đặt ở nơi hiểu được **toàn bộ nghiệp vụ cần nguyên tử** và được gọi qua transaction infrastructure phù hợp. Trong phần lớn ứng dụng Spring + Hibernate, nơi đó là **public application service method đại diện cho một use case**. Hãy để repository làm nhiệm vụ truy xuất, domain objects bảo vệ invariant, application service điều phối commit/rollback và infrastructure xử lý external side effects bằng cơ chế riêng. Một transaction đúng không chỉ giúp dữ liệu được lưu, mà còn xác định rõ khi nào dữ liệu được phép coi là thành công, khi nào phải rollback, và những sự kiện ngoài database cần được phối hợp ra sao.
