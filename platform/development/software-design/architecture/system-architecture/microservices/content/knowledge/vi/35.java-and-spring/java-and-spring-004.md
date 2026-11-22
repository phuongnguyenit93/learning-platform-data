# Quản lý dữ liệu và giao dịch cục bộ trong từng dịch vụ

> **Lĩnh vực:** Software Design / Software Architecture / System Architecture / Microservices  
> **Nhóm kiến thức:** Java và Spring  
> **Mục tiêu:** Thiết kế ranh giới dữ liệu và transaction trong từng microservice bằng Java/Spring; bảo đảm mỗi dịch vụ kiểm soát dữ liệu mình sở hữu, transaction cục bộ ngắn và đúng, đồng thời phối hợp với dịch vụ khác qua API, event, outbox hoặc saga mà không giả định một transaction database có thể bao trùm toàn hệ thống.

## 1. Vì sao mỗi dịch vụ cần quản lý dữ liệu và transaction của chính nó?

Một microservice thường sở hữu một phần trạng thái nghiệp vụ: Order quản lý đơn hàng, Inventory quản lý tồn kho và reservation, Payment quản lý giao dịch thanh toán. Dịch vụ phải chịu trách nhiệm về schema, invariant, transaction, migration, backup và cách công bố thay đổi dữ liệu của domain đó.

Nếu các service cùng đọc/ghi trực tiếp một database schema, ranh giới triển khai chỉ còn là ranh giới process. Order có thể vô tình phụ thuộc vào bảng Inventory; một migration của Inventory làm Order hỏng; một transaction của Order giữ lock trên dữ liệu do Inventory sở hữu. Các nhóm khó thay đổi độc lập và sự cố ở một luồng có thể lan sang các luồng khác.

**Database per service** là nguyên tắc ownership: mỗi service là chủ sở hữu duy nhất của dữ liệu ghi thuộc domain của nó. Điều này không bắt buộc mỗi service phải có một máy chủ database vật lý riêng. Nhiều database/schema có thể cùng nằm trên một cluster, miễn quyền truy cập, ownership và contract được thực thi rõ ràng.

~~~text
                  Order Service
                 +-------------+
                 | Order API   |
                 | Order Logic |
                 +------+------+
                        |
                 Local Transaction
                        |
                 +------v------+
                 | Order DB    |
                 | orders      |
                 | order_items |
                 +-------------+

Inventory Service                 Payment Service
+------------------+               +------------------+
| Inventory Logic  |               | Payment Logic    |
+--------+---------+               +--------+---------+
         |                                  |
  Local Transaction                  Local Transaction
         |                                  |
+--------v---------+               +--------v---------+
| Inventory DB     |               | Payment DB       |
| stock            |               | payment_attempts |
| reservations     |               | transactions     |
+------------------+               +------------------+
~~~

Mỗi service có thể bảo đảm atomicity trong transaction của database do mình quản lý. Khi nghiệp vụ đi qua nhiều service, mỗi service commit transaction riêng; tính nhất quán toàn luồng được xây dựng bằng contract, event, idempotency, saga và reconciliation.

## 2. Transaction cục bộ bảo đảm điều gì?

Transaction database là một đơn vị thao tác có các thuộc tính ACID:

- **Atomicity:** các thay đổi trong transaction được commit cùng nhau hoặc rollback cùng nhau.
- **Consistency:** transaction chuyển dữ liệu từ trạng thái hợp lệ này sang trạng thái hợp lệ khác theo constraint và invariant được thực thi.
- **Isolation:** transaction đồng thời không quan sát hoặc ghi đè dữ liệu trái với isolation level và semantics của database.
- **Durability:** sau khi commit thành công, dữ liệu được lưu bền theo cam kết của database/hạ tầng.

ACID không tự bảo đảm nghiệp vụ đúng. Một transaction có thể atomic nhưng vẫn ghi sai giá tiền, trừ tồn kho hai lần hoặc chuyển trạng thái không hợp lệ. Invariant nghiệp vụ phải được kiểm tra trong domain/application và được bảo vệ bằng constraint/locking/version tại database khi cần.

### 2.1. Phạm vi transaction là một database resource

Ví dụ một transaction trong Order DB có thể:
1. Insert order.
2. Insert order items.
3. Ghi trạng thái ban đầu.
4. Ghi outbox event OrderCreated.
5. Commit.

Nếu tất cả thao tác cùng tham gia một transaction manager và cùng database transaction, chúng có thể commit/rollback nguyên tử.

Nhưng gọi Inventory API hoặc Payment API trong cùng method Java không khiến transaction của Order DB tự động bao trùm database của service kia. Một transaction manager cục bộ không thể rollback một commit đã xảy ra ở Payment DB.

~~~text
Order DB transaction
   BEGIN
     insert order
     insert order_items
     insert outbox event
   COMMIT
        |
        v
   Outbox relay publishes event
        |
        v
Inventory DB transaction
   BEGIN
     create reservation
     update available quantity
   COMMIT
~~~

Hai transaction có hai commit point độc lập. Nếu Inventory thất bại sau khi Order commit, hệ thống cần trạng thái pending, retry hoặc compensation theo workflow. Không giả vờ rằng rollback Order DB có thể xóa một reservation đã commit ở Inventory.

### 2.2. Consistency có nhiều mức

- **Strong consistency trong service:** invariant và transaction được bảo vệ trong database của owner.
- **Read-your-writes:** caller đọc lại được thay đổi vừa commit theo contract.
- **Eventual consistency:** projection/service khác nhận cập nhật sau một khoảng trễ có giới hạn theo SLO.
- **Causal consistency:** các thay đổi có quan hệ nhân quả được quan sát theo thứ tự phù hợp.
- **Business consistency:** toàn workflow cuối cùng đạt trạng thái nghiệp vụ hợp lệ, có thể qua nhiều transaction và compensation.

Không phải mọi màn hình cần đọc từ primary hoặc thấy thay đổi ngay lập tức. Nhưng các quyết định quan trọng như xác nhận thanh toán, giữ hàng hay ghi sổ cần semantics rõ, không dựa vào một cache/projection cũ nếu điều đó có thể vi phạm invariant.

## 3. Ranh giới sở hữu dữ liệu trong microservices

Mỗi service cần xác định:

1. Dữ liệu nào là source of truth của service?
2. Invariant nào chỉ service đó có quyền thực thi?
3. Ai được phép ghi, ai chỉ được đọc qua contract?
4. Dữ liệu nào được phép copy sang service khác và với mục đích gì?
5. Cách version hóa schema và event?
6. Cách migration, backup, restore, retention và deletion?
7. Khi service ngừng hoạt động, caller nhận hành vi gì?
8. Ai chịu trách nhiệm xử lý inconsistency và replay?

Ví dụ:
- Order sở hữu order status, order lines và order total đã được chốt theo hợp đồng.
- Inventory sở hữu stock, reservation và quy tắc không oversell.
- Payment sở hữu payment attempt, authorization/capture/refund state.
- Customer sở hữu profile và thông tin liên hệ.
- Fulfillment sở hữu shipment và tracking state.

Một service khác không được UPDATE bảng do owner quản lý chỉ vì có quyền kỹ thuật truy cập database. Quyền database cần được giới hạn để ranh giới kiến trúc có hiệu lực.

### 3.1. Dùng reference thay vì sao chép entity

Order có thể lưu customerId và một số snapshot cần thiết tại thời điểm đặt hàng như tên người nhận hoặc địa chỉ giao, nếu hợp đồng nghiệp vụ yêu cầu. Không cần copy toàn bộ Customer entity, password hash, preference và thông tin không liên quan vào Order DB.

Snapshot có ý nghĩa khác với read-through profile:
- **Reference:** định danh tới tài nguyên do service khác sở hữu.
- **Snapshot:** giá trị được chụp tại một thời điểm để bảo toàn lịch sử nghiệp vụ.
- **Projection:** bản sao tối thiểu để đọc nhanh, được cập nhật theo event.
- **Cache:** bản sao tạm có TTL/freshness contract.

Mỗi loại cần mục đích, retention, version và deletion policy phù hợp. Đừng gọi mọi bản sao là cache để bỏ qua trách nhiệm quản trị.

### 3.2. Shared database cluster không đồng nghĩa shared ownership

Có thể chạy nhiều schema trong cùng PostgreSQL cluster vì chi phí vận hành. Nhưng nên:
- Chỉ định owner cho từng schema/table.
- Cấp database role riêng cho từng service.
- Hạn chế quyền ghi xuyên schema.
- Không dùng một superuser credential cho mọi ứng dụng.
- Quản lý migration theo owner.
- Quan sát pool, query và resource budget theo service.
- Có kế hoạch khi cần tách database vật lý.

Nếu mọi service dùng chung một database user có quyền ghi tất cả bảng, database-per-service mới chỉ là quy ước trên sơ đồ.

## 4. Tổ chức transaction boundary trong domain

Một transaction nên bao quanh một thay đổi nghiệp vụ cần atomic trong cùng ownership boundary. Đừng đặt transaction tùy tiện quanh controller hoặc toàn bộ request nếu nó bao gồm nhiều thao tác chậm.

Ví dụ tạo đơn:
- Validate input và policy.
- Tính toán dữ liệu cần thiết.
- Trong transaction Order DB: insert order, order items, ghi outbox.
- Commit.
- Publish event sau commit qua outbox relay.
- Các service khác xử lý trong transaction riêng.

~~~text
HTTP request
    |
    v
Application command handler
    |
    +-- validate / authorize
    |
    v
@Transactional local unit of work
    |
    +-- save order aggregate
    +-- save order items
    +-- save outbox message
    |
    v
COMMIT
    |
    v
Return accepted/pending result
    |
    v
Outbox relay -> broker -> consumers
~~~

Không giữ transaction DB mở trong khi chờ người dùng, gọi HTTP bên ngoài hoặc chờ message broker. Những khoảng chờ này có thể giữ connection, lock và snapshot lâu hơn cần thiết.

### 4.1. Transaction phải bảo vệ invariant

Ví dụ invariant: một reservation chỉ được xác nhận nếu số lượng còn khả dụng đủ.

Một cách kiểm soát có thể là conditional update:

~~~sql
UPDATE inventory_stock
SET available_quantity = available_quantity - :quantity,
    reserved_quantity = reserved_quantity + :quantity,
    version = version + 1
WHERE sku = :sku
  AND available_quantity >= :quantity;
~~~

Nếu affected row count bằng 1, lượng hàng được giữ thành công; nếu bằng 0, SKU không tồn tại hoặc không đủ lượng theo logic đã xác định. Cần phân biệt hai trường hợp nếu nghiệp vụ yêu cầu.

Conditional update có thể tránh race giữa hai request cùng đọc số lượng trước đó rồi cùng ghi. Nhưng cần kiểm tra DB engine, index, transaction isolation và semantics thực tế. Không đọc quantity ở Java rồi UPDATE vô điều kiện.

### 4.2. Aggregate boundary và transaction

DDD thường khuyến nghị một transaction bảo vệ invariant trong một aggregate. Nếu một thao tác cần sửa nhiều aggregate hoặc nhiều bounded context, hãy xem lại:
- Có invariant thực sự cần atomic không?
- Có thể dùng reservation/state transition thay vì commit mọi thứ một lần?
- Có thể chấp nhận eventual consistency với reconciliation không?
- Có cần orchestration/saga không?
- Có nên gộp hai phần nếu chúng luôn phải thay đổi cùng nhau?

Đừng chia aggregate chỉ để mỗi bảng có repository riêng; cũng đừng tạo aggregate khổng lồ khóa quá nhiều dữ liệu.

## 5. Spring transaction management hoạt động như thế nào?

Spring cung cấp abstraction transaction qua PlatformTransactionManager/TransactionManager và annotation **@Transactional**. Với JDBC/JPA, transaction manager phù hợp quản lý lifecycle transaction và gắn transaction resource vào execution context theo cơ chế của framework.

Ví dụ:

~~~java
@Service
public class OrderApplicationService {
    private final OrderRepository orders;
    private final OrderItemRepository items;
    private final OutboxRepository outbox;

    public OrderApplicationService(
            OrderRepository orders,
            OrderItemRepository items,
            OutboxRepository outbox
    ) {
        this.orders = orders;
        this.items = items;
        this.outbox = outbox;
    }

    @Transactional
    public OrderId placeOrder(PlaceOrderCommand command) {
        Order order = Order.create(command);
        orders.save(order);
        items.saveAll(order.items());

        outbox.save(OutboxMessage.orderCreated(order));

        return order.id();
    }
}
~~~

Nếu ba repository dùng cùng datasource/transaction manager và tham gia cùng transaction, order, items và outbox được commit cùng nhau. Nếu một lỗi phù hợp rollback xảy ra trước commit, cả nhóm thay đổi sẽ rollback.

### 5.1. Transaction manager phải khớp resource

- JDBC thường dùng DataSourceTransactionManager hoặc transaction manager phù hợp trong Spring Boot.
- JPA thường dùng JpaTransactionManager và EntityManagerFactory.
- R2DBC dùng reactive transaction manager với reactive context.
- Nhiều datasource cần cấu hình transaction manager rõ cho từng resource.
- Chỉ thêm @Transactional không tự làm hai database độc lập thành một local atomic transaction.

Nếu ứng dụng có nhiều datasource, cần chỉ rõ manager phù hợp, ví dụ **@Transactional("orderTransactionManager")** theo cấu hình thực tế. Đừng để một method vô tình dùng manager mặc định khác với repository đang gọi.

### 5.2. Proxy và self-invocation

Trong cấu hình Spring proxy-based thông thường, @Transactional được áp dụng khi lời gọi đi qua proxy. Gọi một method transactional khác bằng this.method() trong cùng object có thể không đi qua proxy nên annotation ở method được gọi không được áp dụng như mong đợi.

Ví dụ dễ gây nhầm:

~~~java
@Service
public class OrderService {
    public void process() {
        saveOrder(); // self-invocation; thường không qua Spring proxy
    }

    @Transactional
    public void saveOrder() {
        // Developer may incorrectly assume a transaction is active.
    }
}
~~~

Cách tổ chức tốt hơn là đặt transaction boundary ở public application service method được gọi từ bean khác, hoặc tách bean theo trách nhiệm. Có thể dùng AspectJ weaving trong cấu hình đặc biệt, nhưng không nên dựa vào hành vi đó nếu ứng dụng đang dùng proxy mặc định.

### 5.3. Method visibility và proxy type

Cách Spring áp dụng transaction cho method phụ thuộc proxy mechanism, cấu hình và phiên bản. Với proxy interface/class và method visibility khác nhau, đừng dựa vào annotation trên private method để tạo boundary. Ưu tiên public method trên Spring-managed bean và kiểm thử hành vi transaction thực tế.

### 5.4. Checked exception và rollback rule

Theo mặc định truyền thống của Spring, RuntimeException và Error thường kích hoạt rollback; checked exception không tự động rollback trừ khi được cấu hình. Hãy khai báo rõ khi cần:

~~~java
@Transactional(rollbackFor = BusinessPersistenceException.class)
public void updateOrder() throws BusinessPersistenceException {
    // local transactional work
}
~~~

Ngược lại, có thể dùng noRollbackFor cho một loại exception nếu semantics đã được hiểu rõ. Tránh catch exception rồi nuốt lỗi trong transaction vì Spring có thể không biết cần rollback; hoặc transaction đã bị đánh dấu rollback-only và cuối cùng phát UnexpectedRollbackException.

Các default có thể thay đổi theo phiên bản/cấu hình; kiểm tra tài liệu Spring đang dùng và test rollback behavior cho loại exception thực tế.

## 6. Propagation: transaction được tham gia hay tạo mới?

Propagation xác định cách method xử lý khi đã có transaction.

| Propagation | Hành vi tổng quát | Khi cân nhắc |
|---|---|---|
| REQUIRED | Tham gia transaction hiện có, nếu chưa có thì tạo mới | Default phổ biến cho một unit of work |
| REQUIRES_NEW | Tạm treo transaction hiện có và tạo transaction độc lập | Audit/record độc lập khi thật sự cần semantics riêng |
| SUPPORTS | Tham gia nếu có, nếu không thì chạy không transaction | Read operation có thể chạy cả hai ngữ cảnh |
| MANDATORY | Yêu cầu caller đã có transaction, nếu không thì lỗi | Internal operation chỉ hợp lệ trong unit of work |
| NOT_SUPPORTED | Tạm treo transaction, chạy không transaction | Công việc không nên giữ transaction hiện có |
| NEVER | Yêu cầu không có transaction | Bảo vệ operation không được chạy trong transaction |
| NESTED | Transaction lồng nhau qua savepoint nếu resource manager hỗ trợ | Rollback một phần trong cùng physical transaction |

### 6.1. REQUIRED là mặc định thường hợp lý

~~~java
@Transactional
public void createOrder() {
    saveHeader();
    saveLines();
}
~~~

Nếu saveHeader và saveLines cũng là transactional REQUIRED và được gọi qua proxy phù hợp, chúng tham gia cùng transaction hiện tại. Nếu một thao tác thất bại, cả unit of work có thể rollback.

Không cần thêm @Transactional ở mọi repository/service method nếu application boundary đã rõ. Quá nhiều boundary nhỏ làm khó hiểu transaction ownership.

### 6.2. REQUIRES_NEW không phải cách “tạo microservice transaction”

~~~java
@Transactional
public void placeOrder() {
    orders.save(...);
    auditService.recordAttempt();
}
~~~

Nếu recordAttempt dùng REQUIRES_NEW, audit transaction có thể commit ngay cả khi transaction đặt đơn bên ngoài rollback. Đây có thể là semantics mong muốn cho audit attempt, nhưng không phải mọi event/audit đều nên tồn tại độc lập.

Cũng cần nhớ REQUIRES_NEW có thể cần connection thứ hai trong lúc transaction ngoài vẫn giữ connection. Khi pool nhỏ và concurrency cao, nó có thể làm cạn connection pool hoặc deadlock chờ tài nguyên.

### 6.3. NESTED khác REQUIRES_NEW

NESTED thường dùng savepoint trong cùng physical transaction khi được hỗ trợ; commit của phần nested chưa phải commit độc lập ra database. Nếu transaction ngoài rollback, thay đổi nested vẫn bị rollback. REQUIRES_NEW có transaction độc lập và có thể commit dù transaction ngoài thất bại.

Đừng chọn propagation chỉ dựa vào tên. Hãy xác định kết quả cần có khi transaction ngoài commit, rollback hoặc timeout.

## 7. Isolation level và concurrency control

Isolation quyết định các transaction đồng thời có thể quan sát/ảnh hưởng nhau thế nào. Các mức SQL phổ biến:

| Isolation | Ý nghĩa tổng quát | Hiện tượng còn có thể tùy engine |
|---|---|---|
| READ UNCOMMITTED | Có thể đọc thay đổi chưa commit | Dirty read có thể xảy ra nếu engine hỗ trợ |
| READ COMMITTED | Mỗi statement đọc dữ liệu đã commit | Non-repeatable read/phantom tùy engine |
| REPEATABLE READ | Snapshot/row reads ổn định theo semantics engine | Phantom/serialization behavior khác nhau |
| SERIALIZABLE | Hành vi tương đương một thứ tự tuần tự hợp lệ | Có thể abort/retry transaction vì serialization conflict |

**Tên isolation level không đủ để suy ra mọi chi tiết.** PostgreSQL, MySQL/InnoDB và các database khác có implementation/semantics khác nhau. Đọc tài liệu engine, test với workload thật và không giả định mọi REPEATABLE READ giống nhau.

### 7.1. Dirty read, non-repeatable read và phantom

- **Dirty read:** transaction đọc dữ liệu chưa commit từ transaction khác.
- **Non-repeatable read:** cùng một row được đọc hai lần trong một transaction nhưng giá trị khác do transaction khác commit.
- **Phantom:** cùng một predicate query trả tập row khác vì transaction khác insert/delete/update phù hợp.
- **Lost update:** hai transaction cùng đọc một giá trị rồi ghi đè, khiến một thay đổi bị mất.
- **Write skew:** các transaction đọc cùng snapshot và cập nhật các row khác nhau, nhưng cùng phá invariant tổng thể.

Một isolation level có thể ngăn một số anomaly nhưng không phải tất cả. Với invariant phức tạp, cần constraint, locking hoặc serializable transaction có retry.

### 7.2. Optimistic locking với JPA @Version

Optimistic locking phù hợp khi xung đột không quá thường xuyên. Entity có version:

~~~java
@Entity
public class InventoryItem {
    @Id
    private String sku;

    private int availableQuantity;

    @Version
    private long version;

    public void reserve(int quantity) {
        if (quantity <= 0 || availableQuantity < quantity) {
            throw new InsufficientStockException();
        }
        availableQuantity -= quantity;
    }
}
~~~

Khi update, JPA dùng version để phát hiện một transaction khác đã cập nhật row. Một transaction có thể nhận OptimisticLockException/ObjectOptimisticLockingFailureException thay vì ghi đè âm thầm.

Caller cần quyết định retry có giới hạn hay trả conflict. Retry phải đọc lại trạng thái và đánh giá nghiệp vụ từ đầu; không lặp một write cũ như thể chưa có cạnh tranh.

### 7.3. Pessimistic locking

Khi cần tuần tự hóa thao tác trên một row, có thể dùng SELECT FOR UPDATE hoặc JPA LockModeType.PESSIMISTIC_WRITE. Row bị khóa cho tới khi transaction kết thúc.

Ưu điểm: ngăn transaction khác cập nhật row đang khóa theo semantics engine. Nhược điểm:
- Giữ lock lâu làm tăng contention.
- Có thể deadlock nếu thứ tự lấy lock khác nhau.
- Lock timeout cần cấu hình.
- Không giải quyết invariant trải trên những row không được khóa.
- Dễ tạo bottleneck ở hot row.

Giữ transaction ngắn và lấy lock theo thứ tự nhất quán để giảm deadlock.

### 7.4. Database constraint là lớp bảo vệ cuối cùng

Nếu email phải unique, tạo unique constraint trong DB thay vì chỉ kiểm tra SELECT trước khi INSERT. Hai request đồng thời có thể cùng thấy “chưa tồn tại”; chỉ database constraint mới bảo vệ uniqueness ở commit boundary.

Tương tự, CHECK constraint, foreign key, NOT NULL và conditional update có thể bảo vệ invariant cơ bản. Domain validation vẫn cần để trả lỗi nghiệp vụ dễ hiểu.

## 8. Transaction trong Spring Data JPA

Spring Data repository có transaction semantics mặc định tùy loại method; tuy nhiên application service thường nên định nghĩa boundary rõ cho một use case, để nhiều repository operation tham gia cùng unit of work.

### 8.1. Entity lifecycle và flush

Trong JPA:
- Entity mới có thể ở trạng thái transient.
- persist/save đưa entity vào persistence context.
- Managed entity được dirty checking.
- flush đồng bộ thay đổi xuống database nhưng **không đồng nghĩa commit**.
- commit kết thúc transaction và flush nếu cần.
- rollback hủy thay đổi transaction theo resource semantics.

~~~java
@Transactional
public void renameOrder(OrderId id, String newName) {
    OrderEntity order = repository.findById(id)
        .orElseThrow(OrderNotFoundException::new);

    order.setDisplayName(newName);
    // JPA dirty checking persists the change at flush/commit.
}
~~~

Không nhất thiết gọi save lại entity managed trong transaction. Nhưng repository abstraction và mapping cụ thể có thể có behavior khác; hiểu persistence context để tránh query thừa.

### 8.2. Flush có thể phát hiện lỗi trước commit

Một số constraint violation chỉ xuất hiện khi flush/commit, không nhất thiết ngay ở lệnh save. Nếu cần bắt lỗi tại vị trí cụ thể, có thể flush có chủ đích; nhưng flush không biến thay đổi thành durable và không giải phóng lock trước commit.

### 8.3. Lazy loading và transaction boundary

Lazy relationship có thể lỗi khi truy cập ngoài persistence context, hoặc dẫn đến N+1 query nếu serialize entity trong controller. Tạo DTO/projection bên trong application boundary và truy vấn dữ liệu cần thiết có chủ đích. Không mở transaction dài chỉ để giữ EntityManager cho quá trình render hoặc network response.

### 8.4. Open Session in View

Open Session in View có thể giữ persistence context mở qua web response, khiến controller/view truy cập lazy field và phát sinh SQL ngoài service transaction rõ ràng. Điều này làm query behavior khó đo và có thể giữ resource lâu hơn mong muốn. Với API, cân nhắc tắt OSIV và dùng DTO/projection, nhưng cần kiểm tra toàn bộ use case trước khi thay đổi.

## 9. Read-only transaction và transaction timeout

**@Transactional(readOnly = true)** thể hiện ý định đọc và có thể cho framework/provider tối ưu. Với JPA/Hibernate, tùy cấu hình nó có thể thay đổi flush mode hoặc dirty checking behavior. Đây không phải một cơ chế bảo mật chắc chắn ngăn mọi lệnh ghi ở database.

Ví dụ:

~~~java
@Transactional(readOnly = true)
public Optional<OrderSummary> findOrder(OrderId id) {
    return repository.findSummaryById(id);
}
~~~

Nếu cần ngăn ghi thật, dùng database privilege, read replica hoặc enforcement khác phù hợp.

### 9.1. Timeout

Transaction timeout giới hạn thời gian một transaction có thể hoạt động theo khả năng transaction manager/driver/database. Nó không thay thế:
- HTTP request deadline.
- JDBC query timeout.
- Connection acquisition timeout.
- Lock wait timeout.
- Downstream client timeout.

Cần ngân sách thời gian đầu-cuối và truyền remaining deadline. Nếu HTTP client đã timeout nhưng transaction vẫn giữ lock hoặc connection, hệ thống có thể tiếp tục làm việc không cần thiết.

### 9.2. Không gọi network trong transaction

Mẫu rủi ro:

~~~java
@Transactional
public void placeOrder(PlaceOrderCommand command) {
    Order order = orders.save(...);
    paymentClient.authorize(order); // network call while DB tx is open
    order.markAuthorized();
}
~~~

Nếu Payment mất 4 giây, transaction Order DB có thể giữ connection/lock trong 4 giây. Nếu Payment thành công nhưng Order commit lỗi, hai service bất đồng. Nếu caller retry, có thể tạo payment attempt lặp.

Tách thành workflow rõ:
1. Ghi Order trạng thái PENDING_PAYMENT và outbox command/event trong transaction cục bộ.
2. Commit.
3. Worker gọi Payment với idempotency key.
4. Payment quản lý transaction riêng.
5. Kết quả được phát event hoặc callback.
6. Order cập nhật trạng thái trong transaction riêng.
7. Nếu thất bại hoặc quá hạn, workflow thực hiện retry/compensation/reconciliation.

Không phải mọi business flow đều cần async; nếu synchronous API được chọn, vẫn cần timeout, idempotency và xử lý trạng thái không xác định. Điều quan trọng là không giữ DB transaction cục bộ mở xuyên network call.

## 10. Transaction và nhiều datasource

Một service có thể dùng nhiều database vì nhu cầu legacy hoặc tách read/write. Khi đó:
- Xác định datasource nào sở hữu dữ liệu nào.
- Tạo transaction manager rõ ràng cho từng resource.
- Không giả định một @Transactional mặc định bao trùm mọi datasource.
- Cân nhắc distributed transaction chỉ khi thật sự cần semantics và hạ tầng hỗ trợ.
- Ưu tiên thiết kế ownership/consistency để giảm nhu cầu atomic commit xuyên database.

Ví dụ hai datasource độc lập:

~~~java
@Transactional("orderTransactionManager")
public void saveOrder(Order order) {
    orderRepository.save(order);
}

@Transactional("auditTransactionManager")
public void recordAudit(AuditRecord audit) {
    auditRepository.save(audit);
}
~~~

Hai method trên có hai transaction riêng. Gọi cả hai trong một method không tự làm commit atomic. Nếu cần phối hợp, cần mô hình workflow, outbox hoặc transaction coordinator được cấu hình đúng.

### 10.1. JTA/XA có phải luôn là lời giải?

XA/JTA có thể phối hợp distributed transaction giữa những resource hỗ trợ, nhưng kéo theo:
- Transaction coordinator và recovery logs.
- Khả năng tương thích của driver/resource.
- Operational complexity.
- Lock và transaction duration dài hơn.
- Failure/recovery phức tạp.
- Khó mở rộng qua các dịch vụ độc lập và bên thứ ba.

XA có thể phù hợp cho một số ứng dụng/hạ tầng được kiểm soát, nhưng không phải mặc định để kết nối mọi microservice. Một external payment provider hoặc message broker thường không tham gia cùng XA transaction của ứng dụng.

## 11. Transactional Outbox: commit dữ liệu và event cùng nhau

Một lỗi phổ biến khi publish event:

~~~text
BEGIN DB transaction
  INSERT order
COMMIT
publish OrderCreated to broker
~~~

Nếu process crash sau commit nhưng trước publish, order đã tồn tại mà event không được phát. Nếu publish trước commit rồi transaction rollback, consumer có thể nhận event cho order chưa tồn tại.

**Transactional Outbox** giải quyết dual-write bằng cách ghi business data và một outbox record trong cùng local transaction.

~~~text
Order Service transaction
  BEGIN
    INSERT order
    INSERT order_items
    INSERT outbox(event_id, event_type, payload, status)
  COMMIT
             |
             v
       Outbox Relay
             |
             v
          Broker
             |
        +----+----+
        |         |
        v         v
    Inventory   Notification
~~~

### 11.1. Schema outbox minh họa

~~~sql
CREATE TABLE outbox_messages (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(100) NOT NULL,
    aggregate_version BIGINT,
    event_type VARCHAR(200) NOT NULL,
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    published_at TIMESTAMPTZ,
    attempts INTEGER NOT NULL DEFAULT 0
);
~~~

Schema này chỉ minh họa. Production cần cân nhắc index, partitioning, payload size, classification, retention, locking strategy, polling efficiency và cleanup. Không giữ outbox vô hạn.

### 11.2. Relay và delivery semantics

Relay có thể:
- Poll batch theo published_at/row lock.
- Dùng CDC từ transaction log.
- Publish message rồi đánh dấu published.
- Retry lỗi tạm thời với backoff.
- Đưa message quá hạn vào quy trình cảnh báo/DLQ theo policy.

Một relay có thể publish thành công nhưng crash trước khi đánh dấu published. Khi chạy lại, nó publish duplicate. Vì vậy outbox thường cung cấp **at-least-once delivery**, không mặc nhiên exactly-once.

Event cần eventId ổn định và consumer cần idempotency/dedup. Đánh dấu published trước khi broker xác nhận sẽ tạo nguy cơ mất event; đánh dấu sau khi xác nhận có thể tạo duplicate. Phải chấp nhận và xử lý đúng delivery semantics.

### 11.3. Ordering và aggregate version

Nếu event của cùng một aggregate cần đúng thứ tự, có thể gắn aggregateId và aggregateVersion, publish theo partition/key phù hợp và kiểm tra version ở consumer. Nhiều worker poll cùng outbox có thể publish sai thứ tự nếu không có ownership/locking thích hợp.

Không giả định timestamp toàn hệ thống là thứ tự chính xác. Dùng sequence/version được tạo trong transaction nguồn khi semantics cần.

### 11.4. Outbox không thay event contract

Payload vẫn cần schema/version, owner, semantics, data classification, consumer, retention và compatibility. Outbox chỉ bảo đảm business state và event intent được ghi cùng transaction; nó không tự bảo đảm consumer thành công hoặc nghiệp vụ hoàn tất.

## 12. Inbox và idempotent consumer

Consumer có thể nhận cùng một event nhiều lần do broker redelivery, relay retry hoặc consumer crash. Nếu handler thực hiện side effect lặp, trạng thái sai.

Một **inbox/dedup table** có thể lưu eventId đã xử lý:

~~~sql
CREATE TABLE processed_messages (
    consumer_name VARCHAR(150) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Trong một transaction cục bộ:
1. Insert eventId vào processed_messages.
2. Nếu unique conflict, event đã được xử lý; bỏ qua theo policy.
3. Nếu mới, cập nhật domain state.
4. Commit cả inbox marker và domain changes cùng nhau.
5. Chỉ ack broker sau khi transaction commit.

~~~java
@Transactional
public void handle(OrderCreated event) {
    boolean firstDelivery = inbox.tryRegister(
        "inventory-consumer", event.eventId());

    if (!firstDelivery) {
        return;
    }

    inventory.reserve(event.orderId(), event.items());
}
~~~

Đây là pseudocode; cách xử lý unique constraint race và transaction exception phải được triển khai phù hợp DB/repository. Nếu insert inbox và cập nhật domain không cùng transaction, crash có thể tạo trạng thái “đã đánh dấu nhưng chưa xử lý” hoặc “đã xử lý nhưng chưa đánh dấu”.

### 12.1. Idempotency ở nghiệp vụ

Dedup theo eventId ngăn cùng một message được áp dụng lặp, nhưng hai event khác ID có thể đại diện cùng command nghiệp vụ. Ví dụ client gửi POST /payments hai lần với request ID khác nhau nhưng cùng order. Payment vẫn cần idempotency key theo business operation, unique constraint và trạng thái attempt.

### 12.2. Retention của inbox

Nếu xóa processed_messages quá sớm trong khi broker vẫn có thể replay event cũ, duplicate có thể được xử lý lại. Retention phải phù hợp với broker retention, replay policy, business idempotency và khả năng phục hồi. Có thể dùng version/aggregate state để bảo vệ thêm.

## 13. Saga: phối hợp nhiều transaction cục bộ

Một order workflow có thể đi qua:
1. Order tạo đơn PENDING.
2. Inventory reserve stock.
3. Payment authorize.
4. Order xác nhận.
5. Fulfillment bắt đầu.

Mỗi bước commit transaction riêng. Nếu Payment thất bại sau khi Inventory đã reserve, hệ thống cần release reservation. Đây là **Saga**, một chuỗi local transactions có các bước compensation khi cần.

~~~text
Create Order
    |
    v
Reserve Inventory
    |
    +-- failure --> Reject Order
    |
    v
Authorize Payment
    |
    +-- failure --> Release Inventory
    |                |
    |                v
    |             Cancel Order
    |
    v
Confirm Order
    |
    v
Request Fulfillment
~~~

### 13.1. Choreography và orchestration

- **Choreography:** service phát event và service khác phản ứng; không có một coordinator trung tâm giữ toàn bộ flow.
- **Orchestration:** một saga orchestrator quản lý state, quyết định bước tiếp theo, timeout, retry và compensation.

Choreography phù hợp flow ngắn, ít bước và semantics rõ. Khi flow dài, nhiều nhánh, timeout hoặc compensation phức tạp, orchestration có thể giúp nhìn trạng thái và ownership rõ hơn. Cả hai đều cần idempotency, durable state và observability.

### 13.2. Compensation không phải rollback database

Rollback hủy thay đổi chưa commit trong một transaction. Compensation là một **hành động nghiệp vụ mới** nhằm đưa hệ thống về trạng thái chấp nhận được sau khi một bước trước đã commit.

Ví dụ:
- Release inventory reservation.
- Void payment authorization.
- Issue refund nếu đã capture.
- Cancel shipment nếu chưa giao.

Refund không xóa lịch sử charge; nó tạo một giao dịch mới. Compensation có thể thất bại hoặc chỉ khôi phục một phần. Saga cần trạng thái pending/manual review và reconciliation khi compensation không hoàn tất.

### 13.3. Saga state machine

Một workflow có thể có trạng thái:
- STARTED
- INVENTORY_RESERVED
- PAYMENT_AUTHORIZED
- ORDER_CONFIRMED
- COMPENSATING
- COMPENSATED
- FAILED_REQUIRES_REVIEW
- COMPLETED

Mọi transition cần:
- Điều kiện hợp lệ.
- Version/optimistic locking.
- Idempotency key.
- Timeout và retry policy.
- Event phát ra.
- Cách phục hồi khi process crash.
- Audit và correlation ID.

Không giữ saga state chỉ trong memory của worker. Sau restart, hệ thống phải khôi phục được bước đang chạy và biết thao tác nào đã commit.

## 14. Java/Spring: tổ chức transaction theo application service

Một pattern thường dùng:
- Controller nhận request, xác thực input cơ bản và gọi use case.
- Application service định nghĩa transaction boundary.
- Domain model kiểm invariant.
- Repository lưu aggregate.
- Outbox repository ghi event intent cùng transaction.
- Worker/relay xử lý công việc bên ngoài transaction.

~~~java
@Service
public class CreateOrderHandler {
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public CreateOrderHandler(
            OrderRepository orders,
            OutboxRepository outbox
    ) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public OrderResult handle(CreateOrderCommand command) {
        Order order = Order.create(command);
        orders.save(order);

        outbox.append(OrderCreated.from(order));

        return new OrderResult(order.id(), order.status());
    }
}
~~~

Controller không cần tự quản EntityManager hoặc gọi commit. Application service diễn đạt một use case có transaction boundary rõ.

### 14.1. Không đặt transaction quá rộng ở controller

Nếu controller method gọi nhiều application service với các transaction semantics khác nhau, một @Transactional ở controller có thể khiến resource bị giữ lâu và propagation khó đoán. Đặt boundary gần use case/application service, nơi biết invariant nào phải commit cùng nhau.

### 14.2. Không trả entity managed ra ngoài

Trả DTO/value object sau khi transaction kết thúc. Tránh lazy loading trong JSON serializer và tránh exposing internal persistence model.

### 14.3. Tách transaction cho read và write khi hợp lý

Read query có thể dùng projection, read-only transaction hoặc read replica nếu consistency cho phép. Write command phải bảo vệ invariant và dùng primary/transactional store phù hợp. CQRS có thể hữu ích nhưng không cần tạo hai model phức tạp cho mọi CRUD service.

## 15. Transaction propagation và event publishing pitfalls trong Spring

### 15.1. @TransactionalEventListener

Spring có thể xử lý application event theo phase như AFTER_COMMIT, AFTER_ROLLBACK hoặc BEFORE_COMMIT. AFTER_COMMIT giúp listener chỉ chạy sau khi transaction commit thành công, nhưng listener in-process vẫn có nguy cơ process crash sau commit trước khi listener thực thi xong. Nó không thay thế durable outbox khi mất event là không chấp nhận được.

Ví dụ:

~~~java
@Component
public class OrderEventListener {
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderCreatedLocalEvent event) {
        // Trigger a best-effort in-process action.
    }
}
~~~

Phù hợp với side effect có thể khôi phục/không yêu cầu durability tuyệt đối. Với event liên service cần bảo đảm không mất intent, ghi outbox trong transaction nguồn.

### 15.2. BEFORE_COMMIT không đồng nghĩa broker commit cùng DB

Nếu publish message tới broker trong BEFORE_COMMIT, broker có thể nhận message rồi database transaction rollback. Hai resource vẫn độc lập trừ khi có transaction coordination được cấu hình và hỗ trợ đúng. Outbox tránh dual-write bằng cách ghi message intent vào cùng database transaction.

### 15.3. Transactional event listener với REQUIRES_NEW

Listener chạy sau commit và ghi audit trong transaction mới có thể hợp lý, nhưng phải tính connection, retry và lỗi listener. Nếu listener thất bại sau commit, transaction nghiệp vụ đã hoàn tất; cần cơ chế retry/durable processing nếu side effect là bắt buộc.

## 16. Deadlock, lock timeout và cách phòng tránh

Deadlock có thể xảy ra khi:
- Transaction A giữ row 1 và chờ row 2.
- Transaction B giữ row 2 và chờ row 1.

~~~text
Transaction A                Transaction B
-------------                -------------
LOCK row 1                   LOCK row 2
WAIT row 2                   WAIT row 1
       \                     /
        +---- DEADLOCK -----+
~~~

Database thường phát hiện và hủy một transaction để phá deadlock. Ứng dụng cần phân loại lỗi và retry có giới hạn nếu operation idempotent/transaction được thiết kế lại an toàn.

Biện pháp:
- Lấy lock theo thứ tự nhất quán.
- Giữ transaction ngắn.
- Truy vấn theo index phù hợp để tránh lock range quá rộng.
- Không gọi network khi đang giữ lock.
- Cập nhật ít row nhất có thể.
- Dùng optimistic locking khi contention thấp.
- Đặt lock timeout và theo dõi deadlock metrics.
- Kiểm tra query plan và transaction duration.

Không retry deadlock vô hạn. Backoff/jitter và retry budget giúp tránh các transaction va nhau liên tục.

## 17. Connection pool và transaction duration

Một transaction thường chiếm một connection trong khoảng thời gian resource cần thiết. Nếu 100 request/s giữ connection trung bình 2 giây, nhu cầu concurrent connection trung bình theo Little's Law xấp xỉ 200, trước khi tính burst.

Một transaction 50 ms và một transaction 3 giây có tác động rất khác nhau dù cùng chạy một câu UPDATE. Vì vậy:
- Đừng gọi API bên ngoài trong transaction.
- Không chờ user input hoặc sleep.
- Tránh query N+1 trong unit of work.
- Không serialize response lớn khi connection còn giữ.
- Dùng batch phù hợp nhưng tránh transaction khổng lồ.
- Theo dõi active/idle/pending connections, acquisition latency và transaction duration.
- Tính tổng pool của tất cả replica khi autoscaling và rolling deployment.

Pool size không phải capacity target của DB. Quá nhiều active connections có thể làm tăng contention và giảm throughput. Chọn pool theo benchmark và DB budget.

## 18. Transaction trong batch processing

Batch job có thể xử lý hàng triệu row. Một transaction duy nhất:
- Giữ lock lâu.
- Dùng nhiều undo/redo/WAL.
- Tăng rủi ro rollback rất lớn.
- Giữ connection lâu.
- Gây replication lag.
- Khó restart sau lỗi.

Chia thành batch có checkpoint:
1. Lấy một tập record theo thứ tự ổn định.
2. Xử lý trong transaction giới hạn.
3. Ghi checkpoint/cursor hoặc trạng thái đã xử lý cùng transaction nếu cần.
4. Commit.
5. Lặp lại.
6. Thiết kế idempotency để resume sau crash.

### 18.1. Spring Batch

Spring Batch cung cấp job/step/chunk processing và transaction boundary cho chunk. Chunk size là quyết định về memory, lock duration, commit overhead và khả năng restart. Chọn bằng đo lường, không có con số tối ưu phổ quát.

### 18.2. Không dùng offset pagination cho mọi batch

Khi dữ liệu thay đổi đồng thời, OFFSET/LIMIT lớn có thể chậm và bỏ sót/đọc lặp tùy query. Keyset pagination hoặc checkpoint theo ID/version có thể phù hợp hơn. Phải xác định snapshot semantics và cách xử lý row mới/cập nhật trong lúc chạy.

### 18.3. Batch side effects

Nếu mỗi row gọi external API, không giữ DB transaction của chunk mở trong suốt thời gian network. Tạo durable work item/outbox và xử lý bên ngoài, hoặc thiết kế chunk/worker với timeout, retry, idempotency rõ.

## 19. Reactive Spring và transaction context

Với Spring WebFlux/R2DBC, transaction context thường gắn với Reactor context thay vì ThreadLocal kiểu imperative. Vì vậy:
- Dùng reactive transaction manager tương ứng.
- Giữ pipeline reactive; không tùy tiện block.
- TransactionalOperator hoặc cơ chế annotation reactive phải được cấu hình phù hợp.
- Không chuyển sang thread tùy ý làm mất context.
- Tránh transaction kéo dài qua publisher không kết thúc.
- Cancellation và backpressure có thể ảnh hưởng lifecycle.
- Kiểm thử rollback khi reactive chain lỗi/cancel.

Ví dụ minh họa:

~~~java
Mono<Order> createOrder(Order order) {
    return transactionalOperator.transactional(
        orderRepository.save(order)
            .flatMap(saved -> outboxRepository.save(
                OutboxMessage.orderCreated(saved))
                .thenReturn(saved))
    );
}
~~~

Đây là pseudocode; kiểu trả về và repository cần phù hợp Spring Data R2DBC. Không áp dụng trực tiếp mẫu ThreadLocal/JPA sang reactive stack.

## 20. Transaction boundary và security

Transaction đảm bảo thay đổi dữ liệu nguyên tử, không đảm bảo caller có quyền thực hiện thay đổi. Authorization cần được kiểm tra trong use case và ràng buộc tenant/resource ở nơi thích hợp.

Các nguyên tắc:
- Xác thực danh tính trước khi thực hiện command.
- Kiểm tra quyền trên resource cụ thể, không chỉ endpoint.
- Tenant ID lấy từ identity/context đã xác minh, không tin trường client tự gửi.
- Đặt tenant predicate trong query/write path.
- Không log payload/credential trong transaction errors.
- Audit những thay đổi quan trọng với actor, action, resource và correlation.
- Giữ audit record theo policy và xử lý failure semantics rõ.

Một request có thể được authorize lúc đầu nhưng quyền thay đổi trước commit. Với use case rủi ro cao, xác định thời điểm authorization phải có hiệu lực và có cần version/lock để bảo vệ quyết định hay không.

## 21. Schema migration trong khi service vẫn đang chạy

Service thường có nhiều instance và rollout phiên bản cũ/mới cùng lúc. Migration cần backward/forward compatibility.

Mẫu expand-and-contract:

~~~text
1. EXPAND
   Add nullable column/table/index; old code still works.

2. DEPLOY COMPATIBLE CODE
   New code can read old/new representation.
   Writes follow a controlled strategy.

3. BACKFILL
   Migrate historical rows in bounded batches.
   Track progress and reconcile.

4. SWITCH
   New code reads/writes the new representation.
   Verify counts, constraints and business results.

5. CONTRACT
   Remove old column/path only after no active version needs it.
~~~

Dual-write có thể gây mismatch nếu một write thành công còn write kia thất bại. Dùng outbox, reconciliation hoặc một source of truth trong từng phase. Không chạy migration phá hủy trước khi phiên bản code cũ không còn dùng schema đó.

### 21.1. Flyway/Liquibase

Các công cụ migration giúp version hóa schema changes và chạy có kiểm soát. Migration nên:
- Có version và review.
- Idempotent hoặc có trạng thái rõ theo tool.
- Có kiểm tra trên dữ liệu representative.
- Có chiến lược rollback hoặc forward-fix.
- Không chứa thao tác full-table blocking không được đánh giá.
- Có owner và runbook.
- Tương thích rolling deployment.

Rollback DDL không phải lúc nào cũng khả thi hoặc an toàn; đôi khi forward-fix là chiến lược đúng hơn. Kiểm tra khả năng lock table và thời gian chạy trên engine thật.

## 22. Test transaction behavior

Unit test mock repository không chứng minh transaction thực sự commit/rollback đúng. Cần các integration tests với database phù hợp, thường dùng Testcontainers hoặc môi trường test tương đương.

Test quan trọng:
- Nếu insert order item thất bại, order header rollback.
- Nếu outbox insert thất bại, order không commit mà thiếu event intent.
- RuntimeException/checked exception có rollback đúng rule.
- Constraint violation được xử lý đúng.
- Hai request cạnh tranh không oversell.
- Optimistic locking conflict được phát hiện và xử lý.
- Duplicate event không tạo side effect lặp.
- Transaction timeout/deadlock được quan sát.
- Schema migration chạy với version cũ/mới theo rollout.
- Multi-tenant query không đọc/ghi chéo.
- Read-only path không phát sinh write ngoài dự kiến.

### 22.1. Test rollback minh họa

~~~java
@Test
void orderAndOutboxAreRolledBackTogether() {
    assertThatThrownBy(() -> orderService.placeOrder(commandThatFails()))
        .isInstanceOf(RuntimeException.class);

    assertThat(orderRepository.findAll()).isEmpty();
    assertThat(outboxRepository.findAll()).isEmpty();
}
~~~

Test cần chạy trong transaction và database configuration tương đương ứng dụng. Spring test framework có thể tự mở transaction cho test và rollback khi kết thúc, vì vậy cần chú ý test thực sự commit/rollback ở boundary nào. Không để transaction của test che giấu hành vi transaction của service.

### 22.2. Test concurrent invariants

Ví dụ tồn kho chỉ có 5 đơn vị, hai request đồng thời muốn giữ 4 đơn vị:
- Không được cả hai cùng thành công nếu invariant không cho oversell.
- Tổng reserved không vượt 5.
- Một request nhận business rejection/conflict rõ.
- Retry không làm reservation trùng.
- Dữ liệu cuối cùng phù hợp với source of truth.

Test concurrency cần điều phối barrier/latch để tạo overlap thực tế, không chỉ gọi hai method tuần tự.

## 23. Observability cho local transactions

Theo dõi:
- Transaction count và outcome (commit/rollback).
- Transaction duration p50/p95/p99.
- Active transaction/connection pool.
- Connection acquisition wait và timeout.
- Lock wait, deadlock, serialization failure.
- Query latency/slow query.
- Rows affected và constraint violations.
- Outbox backlog age, publish attempts và failure.
- Inbox duplicate count và processing lag.
- Saga state age, timeout, compensation failure.
- Projection lag và reconciliation mismatch.

Không gắn raw customer ID, email, payment token hoặc full SQL parameters vào metric labels/logs. Dùng aggregate dimensions và correlation IDs đã được kiểm soát. Log error phải đủ chẩn đoán mà không lộ payload nhạy cảm.

### 23.1. Transaction duration là tín hiệu quan trọng

Một transaction trung bình 40 ms nhưng p99 8 giây có thể gây pool starvation và lock contention. Phân đoạn theo use case/transaction name, nhưng giữ cardinality hợp lý. Trace nên chỉ ra query, external call và thời gian chờ connection; nếu network call nằm trong transaction, cần nhận ra điều đó.

### 23.2. Business outcome sau commit

Database commit thành công không đồng nghĩa workflow đã hoàn tất. Theo dõi:
- Order ở PENDING_PAYMENT quá lâu.
- Outbox event chưa publish.
- Consumer lag.
- Saga compensation đang chờ.
- Reservation chưa release.
- Payment result chưa reconcile.
- Projection chưa cập nhật trong SLO.

Một dashboard chỉ có SQL commit rate có thể xanh trong khi khách hàng bị kẹt.

## 24. Xử lý sự cố transaction và dữ liệu

### 24.1. Connection pool cạn

Triệu chứng: connection acquisition timeout, pending threads tăng, DB có nhiều active connection hoặc transaction dài.

Điều tra:
1. Pool active/idle/pending theo service.
2. Transaction duration và query latency.
3. Connection leak hoặc code giữ stream/result set.
4. Network call trong transaction.
5. Autoscaling làm tổng pool vượt DB budget.
6. REQUIRES_NEW tạo nhu cầu connection bổ sung.
7. Deadlock/lock wait làm transaction không kết thúc.

Khắc phục bằng cách dừng nguồn tải không cần thiết, giới hạn concurrency, xử lý transaction/query kéo dài, sửa pool budget. Không tăng maxPoolSize mù khi DB đã bão hòa.

### 24.2. Deadlock tăng sau release

- Xác định query fingerprint và bảng/row bị tranh chấp.
- Kiểm tra thứ tự lock trong code mới.
- Xem index thay đổi làm phạm vi scan/lock rộng hơn không.
- Xác định transaction có giữ lock trong network wait không.
- Thêm retry bounded cho lỗi transient khi operation an toàn.
- Rollback release nếu cần.
- Bổ sung concurrency test để tái hiện.

### 24.3. Outbox backlog tăng

- Kiểm broker availability/quota.
- Kiểm relay errors, credentials và schema compatibility.
- Kiểm DB polling/locking và batch size.
- Đo oldest unpublished message age.
- Tăng relay concurrency trong ngân sách broker và DB.
- Không xóa message để làm dashboard xanh.
- Reconcile các aggregate/event chưa publish nếu có nguy cơ mất.

### 24.4. Saga bị kẹt

- Tìm saga state và bước cuối đã commit.
- Kiểm idempotency key và event history.
- Xác định timeout thực hay event bị trễ.
- Retry step nếu safe, hoặc chạy compensation.
- Nếu kết quả Payment không xác định, query/reconcile provider trước khi retry side effect.
- Ghi audit và trạng thái manual review khi không thể tự phục hồi.
- Xác nhận customer-facing status đúng với sự thật.

Không sửa trực tiếp database nhiều service để “đưa mọi thứ về trạng thái mong muốn” mà không có owner và audit.

## 25. Ví dụ workflow tạo đơn với Spring, Outbox và Saga

Một thiết kế minh họa:

**Bước 1 — Order nhận command.** Xác thực caller, kiểm tra idempotency key, validate mặt hàng và lưu Order PENDING cùng Outbox OrderPlaced trong một transaction Order DB.

**Bước 2 — Relay publish.** Outbox relay gửi OrderPlaced với eventId và aggregateVersion. Nếu relay publish rồi crash trước khi đánh dấu, event có thể được gửi lại.

**Bước 3 — Inventory consume.** Inbox và reservation update nằm cùng transaction Inventory DB. Nếu event duplicate, consumer bỏ qua. Nếu thiếu stock, Inventory phát ReservationRejected.

**Bước 4 — Payment consume command.** Payment dùng idempotency key gắn với order/payment attempt. Payment lưu trạng thái PENDING/AUTHORIZED/DECLINED trong transaction cục bộ.

**Bước 5 — Order cập nhật.** Order nhận InventoryReserved và PaymentAuthorized qua event, cập nhật saga/order state trong transaction riêng.

**Bước 6 — Hoàn tất hoặc compensation.** Nếu Payment bị decline, saga yêu cầu Inventory release reservation và chuyển Order sang trạng thái phù hợp. Nếu callback bị mất, reconciliation tìm giao dịch chưa rõ.

~~~text
Order DB                    Inventory DB                 Payment DB
--------                    ------------                 ----------
PENDING order               (no reservation)             (no payment)
outbox OrderPlaced
   | commit
   v
publish event
   |
   +-----------------------> reserve stock
                              inbox + stock + reservation
                              commit
                                  |
                                  v
                              InventoryReserved
   <------------------------------+
   |
   v
Order saga state update
outbox AuthorizePayment
   |
   +---------------------------------------------------->
                                               inbox/idempotency
                                               payment attempt
                                               commit
                                                       |
                                                       v
                                                PaymentAuthorized
   <---------------------------------------------------+
   |
   v
Order CONFIRMED + outbox OrderConfirmed
   |
   v
Fulfillment starts
~~~

Sơ đồ bỏ qua nhiều nhánh timeout/rejection để tập trung vào transaction boundaries. Trong thực tế mỗi message handler cần outbox riêng nếu nó phát tiếp event và phải bảo đảm local state với event intent được ghi cùng nhau.

### 25.1. Idempotency key và unique constraints

Có thể lưu:
- requestKey do client gửi.
- operation type.
- resource/order reference.
- kết quả đã tạo.
- trạng thái xử lý.
- thời điểm hết hiệu lực theo policy.

Đặt unique constraint trên phạm vi key phù hợp. Nếu key được dùng lại với payload khác, trả conflict thay vì trả kết quả cũ sai ngữ cảnh. Không dùng một idempotency key toàn cục không có tenant/client scope nếu policy yêu cầu cô lập.

### 25.2. Reconciliation là một phần của thiết kế

Không thể bảo đảm mọi callback/event luôn tới đúng một lần. Job reconciliation có thể tìm:
- Payment PENDING quá lâu.
- Reservation không gắn với order active.
- Order PENDING nhưng Payment đã authorized.
- Outbox unpublished quá SLA.
- Inbox processing error.
- Saga đang COMPENSATING quá lâu.

Reconciliation phải idempotent, có rate limit, audit và owner. Nó không nên là một script thủ công chỉ người viết ban đầu mới chạy được.

## 26. Những sai lầm thường gặp

**Một transaction bao quanh toàn bộ request và mọi API call.** Giữ DB connection/lock trong network wait và không tạo atomicity giữa database khác.

**Dùng @Transactional rồi giả định mọi repository đều chung transaction.** Nhiều datasource/transaction manager có thể hoạt động độc lập.

**Gọi method transactional qua self-invocation.** Proxy không được đi qua nên transaction có thể không được tạo theo kỳ vọng.

**Nuốt exception trong method transactional.** Spring không thấy lỗi để rollback, hoặc transaction bị đánh dấu rollback-only và lỗi xuất hiện lúc commit.

**Dùng REQUIRES_NEW cho mọi audit/event.** Tạo commit độc lập ngoài ý muốn, tăng connection pressure và có thể ghi audit cho nghiệp vụ đã rollback.

**Dùng isolation SERIALIZABLE cho mọi query.** Có thể tăng contention/serialization abort; chọn theo invariant và đo workload.

**Chỉ validate bằng SELECT trước INSERT.** Race condition vẫn có; cần unique constraint hoặc conditional write.

**Đọc stock rồi trừ bằng giá trị cũ.** Lost update/oversell; dùng atomic conditional update hoặc locking/version.

**Publish event trước khi DB commit.** Consumer có thể nhận event cho dữ liệu chưa tồn tại hoặc sẽ rollback.

**Commit DB rồi publish trực tiếp mà không outbox.** Crash giữa hai bước làm mất event.

**Tin rằng outbox bảo đảm exactly-once.** Relay có thể publish duplicate; consumer cần idempotency.

**Đánh dấu inbox đã xử lý trước khi domain update commit.** Crash có thể khiến message bị bỏ qua dù nghiệp vụ chưa hoàn thành.

**Giữ transaction mở khi gọi HTTP.** Tăng lock duration và connection pool pressure, không tạo distributed atomicity.

**Dùng transaction rollback để hoàn tác Payment đã commit.** Cần compensation như void/refund, không thể rollback transaction của service khác.

**Dùng shared database credential cho tất cả service.** Không enforce được ownership và blast radius.

**Chạy batch toàn bộ trong một transaction.** Lock, log và rollback cost tăng; chia chunk/checkpoint phù hợp.

**Không test concurrency.** Unit tests tuần tự không phát hiện lost update, duplicate reservation hoặc deadlock.

**Dùng test transaction rollback tự động để kết luận service rollback đúng.** Transaction do test framework mở có thể che boundary thật.

**Xóa outbox/inbox theo ngày tùy tiện.** Có thể phá replay, dedup hoặc audit; retention phải gắn delivery/recovery policy.

**Dùng cache/projection stale cho quyết định giao dịch cuối.** Read model có thể trễ; xác minh ở owner khi invariant yêu cầu.

## 27. Bài tập tình huống

Một hệ thống Commerce có Order, Inventory và Payment service. Mỗi service có database riêng nhưng chạy trên cùng PostgreSQL cluster.

- Order endpoint bắt đầu một @Transactional method.
- Method ghi Order PENDING.
- Method gọi HTTP tới Inventory để reserve stock.
- Inventory commit reservation.
- Method gọi Payment để authorize.
- Payment authorize thành công và commit.
- Order update thành CONFIRMED nhưng transaction Order DB bị timeout trước commit.
- Client nhận 504 và retry POST /orders.
- Hệ thống tạo một order mới và gọi Payment lần nữa.

### Câu hỏi

1. Vì sao @Transactional ở Order không rollback được reservation của Inventory hoặc authorization của Payment?
2. Vì sao giữ transaction Order mở qua hai HTTP call gây rủi ro pool/lock?
3. Nếu Payment đã authorize nhưng Order timeout, trạng thái nghiệp vụ nào đang không xác định?
4. Dùng idempotency key nào ở Order và Payment để tránh tạo giao dịch trùng?
5. Thiết kế Outbox để Order state và intent publish được ghi nguyên tử ra sao?
6. Inbox ở Inventory/Payment cần ghi cùng transaction với những thay đổi nào?
7. Saga cần compensation nào khi Payment thất bại sau khi Inventory reserve?
8. Khi Payment timeout và không biết provider đã authorize hay chưa, nên query/reconcile hay retry mù?
9. Metric nào phát hiện order pending, outbox backlog và reservation orphan?
10. Test concurrency và failure injection nào cần có?

### Hướng giải

- Tách mỗi service thành local transaction.
- Order tạo PENDING và outbox command trong một transaction ngắn.
- Relay publish event/command sau commit.
- Inventory xử lý reservation với inbox/idempotency trong transaction của mình.
- Payment dùng idempotency key và lưu payment attempt bền vững.
- Order nhận kết quả và cập nhật saga state trong transaction mới.
- Compensation release inventory hoặc void/refund tùy bước đã hoàn tất.
- Timeout tạo trạng thái UNKNOWN/PENDING cần reconciliation, không tự kết luận thất bại.
- Thêm unique constraints, optimistic/pessimistic locking phù hợp và workflow tests.

## 28. Checklist thiết kế transaction cho một service Java/Spring

1. **Ownership:** service sở hữu những bảng/aggregate nào và có quyền ghi ở đâu?
2. **Invariant:** điều kiện nghiệp vụ nào phải đúng tại commit?
3. **Boundary:** use case nào là một local unit of work?
4. **Transaction manager:** đúng datasource/JPA/JDBC/R2DBC resource chưa?
5. **Proxy:** @Transactional được gọi qua Spring proxy theo cách dự kiến?
6. **Propagation:** REQUIRED/REQUIRES_NEW/NESTED có semantics cần thiết không?
7. **Rollback:** checked/unchecked exceptions và catch behavior có rõ?
8. **Isolation:** isolation level có bảo vệ invariant, được kiểm trên engine thật?
9. **Concurrency:** constraint, optimistic/pessimistic lock hoặc conditional update phù hợp?
10. **Duration:** transaction có ngắn, không chờ network/user/broker?
11. **Pool:** tổng connections theo max replicas/rollout có nằm trong DB budget?
12. **JPA:** flush, lazy loading, OSIV và entity serialization được kiểm soát?
13. **Outbox:** state và event intent được ghi cùng transaction khi cần?
14. **Inbox:** dedup marker và domain update commit cùng nhau?
15. **Saga:** workflow nhiều service có state, timeout, retry, compensation và recovery?
16. **Idempotency:** command có side effect được bảo vệ khi client/broker retry?
17. **Migration:** schema change tương thích code cũ/mới trong rollout?
18. **Security:** authorization/tenant isolation và audit ở đúng boundary?
19. **Observability:** transaction duration, rollback, lock, pool, backlog và saga age?
20. **Testing:** integration, concurrency, failure, rollback và recovery tests?
21. **Retention:** outbox/inbox/audit có retention phù hợp replay và policy?
22. **Reconciliation:** có cách tìm và sửa trạng thái không xác định/orphan?
23. **Runbook:** ai xử lý deadlock, pool exhaustion, backlog và saga stuck?
24. **Correctness:** API trả trạng thái phản ánh sự thật nghiệp vụ, không báo thành công giả?

## 29. Ghi nhớ cốt lõi

- **Mỗi microservice sở hữu dữ liệu ghi và invariant của domain mình.** Database cluster có thể dùng chung, nhưng ownership và quyền truy cập phải rõ.
- **@Transactional chỉ quản lý transaction của resource/transaction manager được cấu hình.** Nó không tự tạo atomic commit xuyên database hoặc HTTP service.
- **Đặt transaction quanh một use case cục bộ, ngắn và có invariant rõ.** Không giữ connection/lock trong khi gọi network hoặc chờ bên ngoài.
- **Propagation, isolation, rollback rules và Spring proxy semantics ảnh hưởng trực tiếp hành vi.** Cần hiểu và kiểm thử, không chỉ thêm annotation.
- **Constraint, conditional update và optimistic/pessimistic locking** bảo vệ dữ liệu khi có concurrency; đọc rồi ghi vô điều kiện dễ tạo lost update/oversell.
- **Outbox** ghi business state và event intent cùng transaction; **inbox/idempotency** xử lý duplicate delivery và side effect lặp.
- **Saga** phối hợp các local transactions; compensation là hành động nghiệp vụ mới, không phải rollback một database transaction đã commit ở service khác.
- **Migration, batch, reactive flow và connection pool** đều có transaction lifecycle riêng cần quản lý.
- **Observability và reconciliation** giúp phát hiện trạng thái không xác định, backlog, lock contention và dữ liệu không nhất quán.
- **Một service chỉ đáng tin khi trạng thái nghiệp vụ đúng sau cả success, timeout, retry, crash và recovery**, chứ không chỉ khi request trả HTTP 200.
