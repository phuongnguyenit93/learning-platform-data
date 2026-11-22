# Chỉ đọc, thực thể bất biến và chi phí dirty checking

Hibernate quản lý vòng đời entity trong một **persistence context**. Khi entity được nạp và trở thành managed, ORM giữ trạng thái persistent của nó. Đến lúc flush, Hibernate xác định thuộc tính nào thay đổi và cần phát INSERT/UPDATE/DELETE. Cơ chế này gọi là **dirty checking**.

~~~java
@Transactional
public void approve(Long id) {
    PurchaseOrder order = entityManager.find(
        PurchaseOrder.class, id
    );
    order.approve();
    // Hibernate phát hiện thay đổi khi flush.
}
~~~

Dirty checking giúp code nghiệp vụ tự nhiên, nhưng với request chỉ đọc hoặc dữ liệu thực sự bất biến, việc giữ snapshot và theo dõi thay đổi có thể tạo chi phí không cần thiết. Một batch đọc 200.000 entities có thể tiêu thụ nhiều memory; một query report hydrate cả graph phải quản lý hàng loạt objects dù không ai định sửa chúng.

Các cơ chế giảm chi phí gồm:

- **Read-only transaction**: khai báo ý định chỉ đọc để Spring transaction manager/ORM áp dụng tối ưu phù hợp.
- **Read-only entity/session/query**: yêu cầu Hibernate không dirty-check entities được nạp theo chế độ read-only.
- **Immutable mapping**: khai báo entity/property/collection không được thay đổi theo mapping Hibernate.
- **DTO/scalar projection**: chỉ lấy dữ liệu cần trả về, không tạo managed entities.
- **StatelessSession**: dùng Hibernate session không có persistence context thông thường, phù hợp một số workload xử lý dữ liệu lớn.

Các khái niệm này **không tương đương nhau**. `@Transactional(readOnly = true)` không tự biến entity thành immutable; `@Immutable` không thay thế authorization; DTO projection không cần dirty checking vì nó không phải managed entity; read-only database connection là một lớp khác nữa.

Bài học thuộc chương **Hiệu năng**, tập trung vào việc chọn đúng cơ chế để giảm dirty-checking, memory và flush overhead mà vẫn giữ đúng semantics Hibernate/JPA.

---

## 1. Phân biệt các khái niệm thường bị gọi chung là “read-only”

| Cơ chế | Phạm vi | Mục tiêu chính | Có tự ngăn mọi ghi DB không? |
| --- | --- | --- | --- |
| `@Transactional(readOnly = true)` | Transaction method/boundary | Khai báo ý định chỉ đọc, cho transaction manager/ORM tối ưu | Không bảo đảm |
| Hibernate read-only entity | Một entity instance | Bỏ dirty checking/snapshot synchronization cho state entity | Không phải security boundary |
| Hibernate default read-only Session | Entities được load sau khi bật | Mặc định nạp entities ở trạng thái read-only | Không ngăn raw SQL |
| Hibernate `@Immutable` | Mapping entity/property/collection | Khai báo dữ liệu không được sửa theo mapping | Không bảo vệ mọi SQL writer |
| Database read-only transaction/permissions | Connection/transaction/database role | DB từ chối một số writes theo DB semantics | Mạnh hơn ở DB layer, nhưng phụ thuộc cấu hình |

DTO projection và StatelessSession là hai cách giảm overhead bằng cách thay đổi mô hình truy cập dữ liệu, không đơn giản là một cờ read-only.

### 1.1. Read-only không có nghĩa “không thể thay đổi object Java”

Một entity vẫn có thể có setter hoặc domain method:

~~~java
order.changeStatus(OrderStatus.CANCELLED);
~~~

Nếu entity đang ở Hibernate read-only state, thay đổi Java object có thể xảy ra trong memory nhưng **không được Hibernate đồng bộ thành UPDATE thông thường**. Developer có thể tưởng dữ liệu đã lưu trong khi DB vẫn giữ giá trị cũ.

Với immutable mapping, thay đổi entity state cũng không được đồng bộ theo contract của mapping; tùy trường hợp, thay đổi có thể bị bỏ qua hoặc bị phát hiện là thao tác không hợp lệ, đặc biệt với immutable collections.

### 1.2. Read-only không đồng nghĩa không có transaction

Một query chỉ đọc vẫn có thể cần transaction để có snapshot isolation nhất quán, đọc nhiều bảng trong cùng boundary, kiểm soát lazy loading/persistence context, đọc từ replica theo routing policy hoặc bảo đảm read-your-writes.

`readOnly=true` không phải lệnh “không mở transaction”.

### 1.3. Immutable khác read-only theo từng request

Một bảng danh mục tiền tệ có thể bất biến theo domain trong suốt vòng đời ứng dụng. Mapping `@Immutable` phù hợp hơn với cờ read-only tạm thời của một query báo cáo.

Một entity đơn hàng vẫn mutable trong use case cập nhật, nhưng có thể được nạp read-only khi chỉ dùng để hiển thị. Đó là quyết định theo **use case**, không phải bản chất bất biến của entity.

## 2. Dirty checking hoạt động như thế nào?

Khi Hibernate nạp một entity managed, persistence context (first-level cache) giữ entry theo entity identity và metadata quản lý. Với snapshot-based dirty checking, ORM lưu trạng thái persistent ban đầu.

~~~java
PurchaseOrder order = entityManager.find(
    PurchaseOrder.class, 9001L
);
~~~

Trạng thái lúc nạp:

~~~text
id          = 9001
status      = PAID
totalAmount = 100.00
version     = 4
~~~

Sau đó:

~~~java
order.changeStatus(OrderStatus.COMPLETED);
~~~

Khi flush, Hibernate phát hiện `status` khác snapshot và tạo UPDATE phù hợp, đồng thời xử lý optimistic version nếu entity có `@Version`.

~~~sql
UPDATE purchase_orders
SET status = 'COMPLETED',
    version = 5
WHERE id = 9001
  AND version = 4;
~~~

SQL thực tế phụ thuộc mapping, dialect, dynamic update, version type và cấu hình.

### 2.1. Dirty checking thường diễn ra lúc flush

Flush có thể xảy ra khi transaction commit, gọi `EntityManager.flush()`/`Session.flush()`, hoặc trước một query cần đồng bộ pending changes theo flush mode và query spaces.

~~~java
@Transactional
public void updateStatus(Long id) {
    PurchaseOrder order = entityManager.find(
        PurchaseOrder.class, id
    );
    order.changeStatus(OrderStatus.COMPLETED);

    // Có thể chưa có UPDATE SQL tại đây.
    entityManager.flush();
}
~~~

`flush()` không phải commit. Transaction vẫn có thể rollback sau khi SQL đã được gửi.

### 2.2. Chi phí không chỉ là so sánh field

Khi quản lý nhiều entities, chi phí có thể đến từ:

1. Tạo Java entity objects và proxies.
2. Lưu chúng trong persistence context.
3. Lưu snapshot/state metadata để dirty checking.
4. Theo dõi collections và associations.
5. Quét entities khi flush.
6. So sánh property values/type-specific state.
7. Xây dựng action queue và SQL statements.
8. Quản lý cascade, callbacks, interceptors và optimistic locking.
9. Giữ graph trong heap tới khi detach/clear/session close.

Do đó query read-only hydrate hàng trăm nghìn entities có thể tốn CPU và memory dù cuối cùng **không phát bất kỳ UPDATE nào**.

### 2.3. Độ phức tạp phụ thuộc mapping và Hibernate version

Không nên khẳng định mọi flush luôn là phép so sánh đơn giản `O(entityCount × fieldCount)`. Hibernate có nhiều tối ưu, dirty tracking strategies, bytecode enhancement, collection tracking và action queue optimizations. Tuy vậy, số managed entities, properties, collections và loại mappings vẫn ảnh hưởng đáng kể.

## 3. Bytecode-enhanced dirty tracking

Hibernate có thể dùng bytecode enhancement để entity theo dõi field nào bị thay đổi thay vì luôn so sánh toàn bộ state theo snapshot strategy.

~~~java
order.setStatus(OrderStatus.COMPLETED);
// Enhanced entity có thể đánh dấu status là dirty.
~~~

| Cách | Cơ chế khái quát | Chi phí có thể giảm |
| --- | --- | --- |
| Snapshot-based dirty checking | So trạng thái hiện tại với snapshot khi flush | Không cần developer gọi update thủ công |
| Bytecode-enhanced inline tracking | Entity đánh dấu attributes thay đổi khi setter/field access phù hợp | Giảm công việc so sánh properties ở một số mappings |

Inline tracking có thể giúp entity có nhiều fields nhưng chỉ đổi ít fields. Tuy nhiên, nó **không loại bỏ** persistence context, entity objects, SQL generation/flush, collection tracking, memory của graph, database work, network round-trips hay chi phí hydration.

### 3.1. Mutable custom types cần chú ý

~~~java
order.getMetadata().put("source", "batch");
~~~

Một property chứa object mutable có thể bị sửa nội bộ mà không qua setter theo cách enhancement nhận diện được. Nếu Hibernate không phát hiện đúng mutation của custom type/value mapping, state có thể không được persist hoặc dirty tracking hoạt động khác kỳ vọng. Cần dùng immutable value objects, mutability plan/type semantics phù hợp và integration tests.

### 3.2. Enhancement không thay thế read-only strategy

Nếu use case chỉ cần đọc `id`, `status`, `totalAmount`, DTO projection thường tiết kiệm hơn việc nạp managed entities rồi tối ưu dirty checking. Enhancement tối ưu cơ chế quản lý entity; nó không làm cho việc tạo entity graph không cần thiết trở nên miễn phí.

## 4. Spring @Transactional(readOnly = true)

~~~java
@Service
public class OrderQueryService {

    private final OrderRepository orders;

    public OrderQueryService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(readOnly = true)
    public List<OrderView> findRecentOrders() {
        return orders.findRecent()
            .stream()
            .map(OrderView::from)
            .toList();
    }
}
~~~

`readOnly = true` là transaction attribute/hint. Spring transaction manager có thể chuyển ý định này tới JDBC connection, Hibernate Session hoặc JPA provider để áp dụng tối ưu phù hợp.

### 4.1. Hibernate integration có thể giảm flush và dirty checking

Với Spring transaction manager/JPA dialect tích hợp Hibernate phù hợp, transaction read-only thường có thể:

- Đặt Hibernate flush mode sang `MANUAL` trong transaction tương ứng.
- Đặt default read-only state cho entities được load trong session.
- Giảm snapshot/dirty checking overhead của entities read-only.
- Truyền read-only hint tới JDBC connection khi transaction manager hỗ trợ.

Chi tiết phụ thuộc Spring Framework, Hibernate, transaction manager và cách bootstrap EntityManagerFactory. Không suy luận mọi `@Transactional(readOnly=true)` ở mọi stack đều thực hiện đầy đủ các tối ưu này.

### 4.2. readOnly=true không phải write prohibition

~~~java
@Transactional(readOnly = true)
public void incorrectlyWrite() {
    PurchaseOrder order = entityManager.find(
        PurchaseOrder.class, 9001L
    );
    order.changeStatus(OrderStatus.CANCELLED);
}
~~~

Không được xem annotation như cơ chế authorization hoặc validation bảo đảm write sẽ bị từ chối.

Trong tích hợp Hibernate/Spring, read-only transaction có thể khiến flush không diễn ra theo cách thông thường hoặc entities được load ở read-only mode, khiến thay đổi bị bỏ qua. Nhưng raw JDBC, native SQL, stored procedure hoặc database khác có thể có behavior khác. Một số DB/transaction manager thực thi read-only ở DB layer; số khác chỉ coi đó là hint.

Nếu nghiệp vụ bắt buộc không ghi, dùng DB permissions/transaction policy thích hợp và không expose write operations trong read API.

### 4.3. readOnly=true không thay thế @Immutable

Một service query có thể dùng read-only transaction dù entities bên trong vẫn mutable trong domain. Một entity mapping immutable có thể được load cả trong transaction read-write nhưng Hibernate vẫn không đồng bộ entity field changes theo immutable mapping.

### 4.4. Transaction hiện có quyết định semantics

~~~java
@Transactional
public void outerWrite() {
    queryService.readSomething();
}
~~~

Nếu inner method dùng propagation `REQUIRED`, nó có thể tham gia transaction read-write hiện có. Không nên giả định annotation `readOnly=true` ở inner method sẽ biến transaction đã mở thành read-only hoặc đổi isolation/flush semantics của transaction vật lý.

Ngược lại, nếu một read-only outer transaction gọi inner write method `REQUIRED`, inner method có thể tham gia read-only transaction đó. Kết quả phụ thuộc transaction manager, flush mode, database enforcement và rollback rules.

Thiết kế transaction boundaries theo use case; không trộn read và write operations trong một call graph mà không hiểu propagation.

### 4.5. Kiểm tra existing transaction mismatch

Spring có tùy chọn transaction manager để validate việc tham gia transaction hiện có với attributes không tương thích trong một số cấu hình. Nó không phải bảo đảm mặc định trên mọi ứng dụng. Nếu hệ thống cần fail-fast khi read-only/write transaction mismatch, hãy kiểm tra khả năng hỗ trợ của transaction manager/version và viết integration test.

## 5. JPA FlushModeType và Hibernate flush modes

JPA có `FlushModeType.AUTO` và `FlushModeType.COMMIT`:

- `AUTO`: provider phải đảm bảo query nhìn thấy những thay đổi cần thiết theo semantics JPA; provider có thể flush trước query.
- `COMMIT`: provider trì hoãn synchronization cho tới commit, nhưng query visibility và provider behavior cần tuân thủ JPA contract.

Hibernate còn có flush modes riêng, ví dụ `MANUAL`, `COMMIT`, `AUTO`, `ALWAYS` tùy version/API. `MANUAL` là Hibernate-specific và thường được dùng trong một số read-only integration paths để tránh automatic flush.

~~~java
Session session = entityManager.unwrap(Session.class);
FlushMode previous = session.getHibernateFlushMode();

try {
    session.setHibernateFlushMode(FlushMode.MANUAL);
    // Workload chỉ đọc, được thiết kế và kiểm soát rõ.
} finally {
    session.setHibernateFlushMode(previous);
}
~~~

Đây là thao tác Hibernate-specific; trong ứng dụng Spring, transaction manager có thể đã quản lý flush mode. Không tùy tiện ghi đè rồi quên khôi phục, đặc biệt khi Session được framework quản lý.

### 5.1. MANUAL không phải “không thể ghi”

Nếu code explicit `flush()` hoặc chạy native SQL/JDBC, SQL vẫn có thể được thực thi theo đường đó. `MANUAL` chủ yếu thay đổi automatic flush behavior của Hibernate.

### 5.2. Đừng đổi flush mode toàn cục để sửa một query

Flush mode có thể ảnh hưởng query visibility, transaction semantics và updates đang chờ. Dùng transaction/read-only boundary hoặc query-specific strategy khi thích hợp, rồi test các trường hợp pending changes.

## 6. Hibernate Session default read-only

Hibernate cho phép đánh dấu các entities được nạp sau đó là read-only:

~~~java
Session session = entityManager.unwrap(Session.class);
session.setDefaultReadOnly(true);

PurchaseOrder order = session.find(
    PurchaseOrder.class, 9001L
);
~~~

Trong các Hibernate versions hỗ trợ API này, entities được load sau khi bật default read-only thường được quản lý ở read-only state.

### 6.1. Thời điểm gọi rất quan trọng

`setDefaultReadOnly(true)` áp dụng cho entities **được load sau khi đặt chế độ**. Những entities đã được load và managed trước đó không tự động trở thành read-only chỉ vì đổi default.

~~~java
PurchaseOrder first = session.find(PurchaseOrder.class, 1L);
session.setDefaultReadOnly(true);
PurchaseOrder second = session.find(PurchaseOrder.class, 2L);
// first và second không nhất thiết có cùng read-only status.
~~~

Nếu cần đổi state của entity đã managed, dùng API per-entity phù hợp và hiểu tác động của việc chuyển state.

### 6.2. Query-level read-only

~~~java
org.hibernate.query.Query<PurchaseOrder> query =
    session.createQuery(
        "from PurchaseOrder o where o.status = :status",
        PurchaseOrder.class
    );

query.setParameter("status", OrderStatus.PAID);
query.setReadOnly(true);

List<PurchaseOrder> rows = query.getResultList();
~~~

`setReadOnly(true)` là Hibernate-specific. Kiểm tra API đúng với Hibernate version đang dùng; query read-only state áp dụng cho entities do query load theo semantics của provider.

### 6.3. Per-entity read-only

~~~java
PurchaseOrder order = session.find(PurchaseOrder.class, 9001L);
session.setReadOnly(order, true);
~~~

Đây là cách đánh dấu instance cụ thể. Một entity read-only không được dirty-check/synchronize persistent property changes như entity mutable thông thường.

### 6.4. Có thể chuyển lại thành mutable không?

~~~java
session.setReadOnly(order, false);
~~~

Hibernate có API thay đổi read-only status của managed entity trong những trường hợp hỗ trợ. Nhưng không dùng tùy tiện để “bật lại tracking” sau khi đã mutate object. Cần kiểm tra snapshot, collection changes, version và semantics của Hibernate version. An toàn hơn là xác định mode trước khi sửa entity hoặc load lại trong persistence context phù hợp.

## 7. Hibernate read-only entity giảm chi phí nào?

Với entity read-only, Hibernate có thể không cần giữ snapshot state đầy đủ để so sánh dirty fields theo cách thông thường.

| Chi phí | Entity mutable managed | Entity read-only |
| --- | --- | --- |
| Entity object | Có | Có |
| Persistence context entry | Có | Có |
| First-level identity management | Có | Có |
| Snapshot cho dirty checking | Thường có theo strategy | Có thể được loại bỏ/giảm theo read-only semantics |
| Dirty checking persistent scalar state | Có | Không theo semantics read-only |
| Automatic UPDATE do field mutation | Có thể có | Không đồng bộ field mutation thông thường |
| Hydration từ ResultSet | Có | Vẫn có |
| Collection/association management | Có | Cần xem semantics riêng |
| SQL SELECT | Có | Có |

**Read-only không loại bỏ entity hydration.** Nếu query trả một triệu entities, vẫn phải truyền dữ liệu, tạo objects và quản lý identity/persistence context; read-only chủ yếu giảm phần theo dõi state.

### 7.1. Memory vẫn có thể lớn

Ngay cả khi không giữ snapshot, entity instances, proxies, collection wrappers, persistence context entries và associated data vẫn chiếm memory.

Với batch read rất lớn, có thể cần DTO projection, pagination/scrolling hoặc StatelessSession thay vì chỉ bật read-only.

### 7.2. Không dirty-check không có nghĩa không có mọi synchronization

Collection state, associations, cascades và thao tác explicit cần được xem riêng. Read-only entity mode không phải một “deep immutable object graph” áp dụng đệ quy cho tất cả related entities.

## 8. @Immutable trên entity

Hibernate cung cấp `org.hibernate.annotations.Immutable`:

~~~java
import jakarta.persistence.*;
import org.hibernate.annotations.Immutable;

@Entity
@Immutable
@Table(name = "currencies")
public class Currency {

    @Id
    private String code;

    @Column(nullable = false)
    private String displayName;

    @Column(nullable = false)
    private int minorUnits;

    protected Currency() {}

    public String getCode() { return code; }
    public String getDisplayName() { return displayName; }
    public int getMinorUnits() { return minorUnits; }
}
~~~

### 8.1. Ý nghĩa mapping

`@Immutable` trên entity nói với Hibernate rằng entity được xem là immutable. Hibernate không cần dirty-check persistent state theo cách entity mutable thông thường và thay đổi property state của entity **không được đồng bộ thành UPDATE**.

Đây là Hibernate-specific mapping metadata, không phải JPA chuẩn.

### 8.2. Khi nào phù hợp?

- Bảng lookup/reference data ít hoặc không thay đổi.
- Dữ liệu danh mục được quản lý bởi migration.
- Historical snapshots chỉ đọc.
- Entity đại diện dữ liệu append-only mà ứng dụng không update.
- Read model được xây dựng và thay thế theo phiên bản.

### 8.3. @Immutable không biến Java class thành immutable

Class trên vẫn có thể có setter nếu developer viết thêm. Annotation không tự tạo final fields, không cấm mọi Java mutation và không ngăn DBA/JDBC client UPDATE bảng.

Nên kết hợp API chỉ expose getters/constructors phù hợp, domain model không có mutation methods và DB privileges/policies nếu cần bảo vệ ở tầng dữ liệu.

### 8.4. Hibernate bỏ qua entity changes không có nghĩa code được phép giả định đã lưu

~~~java
Currency currency = entityManager.find(Currency.class, "USD");
currency.rename("US Dollar Revised");
entityManager.flush();
~~~

Với immutable entity, Hibernate không phát UPDATE thông thường cho thay đổi đó. Java object trong persistence context có thể hiển thị giá trị mới trong khi DB vẫn giữ giá trị cũ. Không trả object này như thể mutation đã thành công.

Nếu reference data cần sửa, dùng write path có chủ đích và mapping mutable phù hợp; không cố cập nhật entity immutable qua setter.

### 8.5. @Immutable và optimistic locking

Vì Hibernate không đồng bộ entity property updates thông thường, không dựa vào `@Version` trên immutable entity để biến nó thành entity mutable có optimistic locking. Nếu entity thực sự cần update, xem lại mapping/ownership. Nếu chỉ cần lịch sử phiên bản, có thể tạo bản ghi mới theo model append-only hoặc versioned reference data.

## 9. @Immutable trên attribute

Hibernate cũng hỗ trợ đánh dấu một property/attribute là immutable theo mapping trong các phiên bản phù hợp.

~~~java
@Entity
public class Product {

    @Id
    private Long id;

    @org.hibernate.annotations.Immutable
    @Column(name = "external_reference")
    private String externalReference;

    private String displayName;
}
~~~

Phù hợp với external immutable identifier, dữ liệu nguồn được chốt khi tạo, giá trị bất biến theo domain hoặc field do hệ thống khác sở hữu và app này chỉ đọc.

Không dùng cho field chỉ “ít khi thay đổi”. Nếu field có thể thay đổi hợp lệ theo nghiệp vụ, dù hiếm, không nên đánh dấu immutable chỉ để tối ưu.

### 9.1. Không nhầm với updatable=false

~~~java
@Column(updatable = false)
private String externalReference;
~~~

`updatable=false` hướng dẫn JPA provider không đưa column vào SQL UPDATE thông thường do ORM sinh. `@Immutable` là Hibernate-specific mutability metadata. Hai cơ chế có overlap về mục tiêu nhưng semantics/implementation khác nhau.

Cả hai đều không tự tạo DB-level permission ngăn native SQL/script/DBA sửa column.

## 10. @Immutable trên collection

~~~java
@Entity
public class Customer {

    @Id
    private Long id;

    @org.hibernate.annotations.Immutable
    @OneToMany(mappedBy = "customer")
    private List<LegacyRecord> legacyRecords;
}
~~~

Với immutable collection mapping, cố sửa collection theo cách Hibernate phát hiện có thể ném `HibernateException` thay vì âm thầm đồng bộ thay đổi.

~~~java
customer.getLegacyRecords().add(newRecord);
~~~

### 10.1. Collection immutable khác entity immutable

| Mapping | Hành vi khái quát |
| --- | --- |
| Entity `@Immutable` | Persistent property changes của entity không được đồng bộ thành UPDATE |
| Attribute `@Immutable` | Property được coi là immutable theo mapping |
| Collection `@Immutable` | Thay đổi collection bị từ chối theo semantics Hibernate, thường phát exception |

Entity immutable không tự làm mọi association immutable. Một entity `@Immutable` có association tới entity mutable; việc thay đổi entity đích có thể vẫn được Hibernate quản lý theo mapping của entity đích nếu nó được load mutable.

Java collection `List.of()` không đồng nhất với Hibernate collection wrapper/lifecycle. Cần mapping phù hợp và test persist/load/update.

## 11. Read-only entity có phải immutable collection không?

Không. Một entity được load read-only theo Session có thể bỏ dirty checking scalar state, nhưng collection/association changes có semantics riêng.

~~~java
PurchaseOrder order = session.find(PurchaseOrder.class, id);
session.setReadOnly(order, true);

order.changeStatus(OrderStatus.CANCELLED);
order.getLines().add(new OrderLine(...));
~~~

Không được giả định cả hai thay đổi đều bị bỏ qua giống nhau hoặc cả graph tự động read-only. Kết quả phụ thuộc collection mapping, ownership, entity state của child, Hibernate version và cascade settings.

Nếu yêu cầu không được sửa, không expose mutation API trong read model; dùng DTO projection khi chỉ cần đọc; dùng `@Immutable` cho mapping thực sự bất biến; dùng DB permissions/constraints khi cần enforcement; và viết integration test cho collection/child mutations.

## 12. DTO projection: không tạo managed entity khi chỉ cần đọc

Đối với API query, cách giảm overhead mạnh thường là **không load entity**.

~~~java
List<PurchaseOrder> orders = entityManager
    .createQuery("""
        select o from PurchaseOrder o
        where o.organizationId = :org
        order by o.createdAt desc
        """, PurchaseOrder.class)
    .setParameter("org", organizationId)
    .getResultList();
~~~

DTO projection:

~~~java
public record OrderSummary(
    Long id,
    OrderStatus status,
    BigDecimal totalAmount,
    Instant createdAt
) {}
~~~

~~~java
List<OrderSummary> rows = entityManager
    .createQuery("""
        select new com.example.api.OrderSummary(
            o.id, o.status, o.totalAmount, o.createdAt
        )
        from PurchaseOrder o
        where o.organizationId = :org
        order by o.createdAt desc
        """, OrderSummary.class)
    .setParameter("org", organizationId)
    .getResultList();
~~~

DTO projection không hydrate đầy đủ entity graph, không đăng ký mỗi row như managed entity trong persistence context, không cần entity dirty checking, chỉ select columns cần thiết và giảm rủi ro serializer kích hoạt N+1.

Projection không phải lúc nào cũng nhanh hơn: nhiều joins, tính toán SQL phức tạp hoặc quá nhiều rows vẫn có thể làm DB/network chậm. DTO constructor expression cũng tạo object; đo actual rows, bytes, execution plan và allocation.

### 12.1. Interface projection của Spring Data

~~~java
public interface OrderSummaryView {
    Long getId();
    OrderStatus getStatus();
    BigDecimal getTotalAmount();
}
~~~

~~~java
public interface OrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    List<OrderSummaryView>
    findByOrganizationId(String organizationId);
}
~~~

Spring Data có thể tạo projection proxy/tuple mapping tùy loại projection và query. Interface projection không tự bảo đảm SQL chỉ chọn đúng columns trong mọi query shape; kiểm tra generated SQL.

### 12.2. Scalar/record projection cho báo cáo

~~~java
List<Object[]> totals = entityManager.createQuery("""
    select o.status, count(o), sum(o.totalAmount)
    from PurchaseOrder o
    where o.organizationId = :org
    group by o.status
    """)
    .setParameter("org", organizationId)
    .getResultList();
~~~

Với API rõ ràng hơn, dùng constructor projection hoặc map kết quả thành record. Không tạo entity chỉ để lấy COUNT, SUM hoặc vài fields.

## 13. Khi nào chọn read-only entity thay vì DTO?

| Nhu cầu | Lựa chọn thường phù hợp |
| --- | --- |
| Hiển thị vài fields, list lớn | DTO/scalar projection |
| Đọc entity graph để gọi domain read methods | Entity read-only/session read-only |
| Reference entity không bao giờ sửa | `@Immutable` |
| API service query cần read-only transaction semantics | `@Transactional(readOnly=true)` |
| Batch scan rất lớn, không cần identity map/cascades | StatelessSession hoặc JDBC streaming |
| Đọc và sau đó có thể sửa cùng transaction | Managed mutable entity |
| Báo cáo aggregate/count/sum | Scalar/DTO projection |
| Dữ liệu live cần transaction snapshot | Read-only transaction theo isolation phù hợp |

Entity read-only vẫn hữu ích khi cần domain methods, association navigation và mapping của entity, nhưng không muốn giữ snapshot dirty-checking. DTO không có lazy loading tự động; nếu cần nhiều associations, phải thiết kế query/projection phù hợp.

## 14. StatelessSession: bỏ persistence context thông thường

Hibernate `StatelessSession` là API khác với `Session` thông thường.

~~~java
try (StatelessSession stateless =
         sessionFactory.openStatelessSession()) {

    try (Transaction tx = stateless.beginTransaction()) {
        // Read/insert/update/delete explicitly.
        tx.commit();
    }
}
~~~

StatelessSession thường không có first-level persistence context, identity map hoặc automatic dirty checking thông thường; không dùng write-behind/action queue theo cùng mô hình managed entities; không tự cascade operations; không quản lý collections/lazy association graph theo cách Session thông thường; và cần thao tác explicit hơn khi insert/update/delete.

### 14.1. Không phải chỉ bật read-only

StatelessSession có thể thực hiện writes explicit; nó không tự biến DB transaction thành read-only. Nó phù hợp cho bulk/streaming workloads cần giảm persistence context overhead, nhưng developer chịu trách nhiệm nhiều hơn về mapping, associations và lifecycle.

Nếu use case dựa vào dirty checking tự động, cascade, collection management, first-level identity, lifecycle callbacks/interceptors hoặc lazy loading graph, StatelessSession có thể không phù hợp.

Với endpoint trả 20 rows, DTO projection hoặc read-only query thường đơn giản hơn. StatelessSession có ý nghĩa khi đo được persistence context overhead là vấn đề và team chấp nhận semantics khác.

## 15. Read-only và persistence context memory

~~~java
List<PurchaseOrder> orders = entityManager
    .createQuery("from PurchaseOrder", PurchaseOrder.class)
    .getResultList();
~~~

Nếu mỗi entity có Java object, Strings/BigDecimals/Instant, EntityEntry, identity map structures, snapshot arrays, collections/proxies/associations, heap sử dụng có thể lớn hơn nhiều so với kích thước rows trong DB.

Read-only entity có thể giảm snapshot state và dirty checking, nhưng 100.000 entities vẫn là 100.000 Java objects trong persistence context. DTOs không được quản lý như entity instances, do đó không cần EntityEntry/dirty checking; tuy nhiên list DTO vẫn chiếm memory. Với kết quả lớn, cần pagination/streaming.

### 15.1. Keyset pagination

~~~sql
SELECT id, status, total_amount, created_at
FROM purchase_orders
WHERE organization_id = :org
  AND (
      created_at < :lastCreatedAt
      OR (
          created_at = :lastCreatedAt
          AND id < :lastId
      )
  )
ORDER BY created_at DESC, id DESC
LIMIT 500;
~~~

Cần index phù hợp và cursor ổn định. Nếu dữ liệu thay đổi liên tục, định nghĩa rõ snapshot/consistency semantics cho toàn bộ batch.

## 16. Scroll/stream large result sets

Hibernate có API scroll/stream tùy version:

~~~java
try (Stream<PurchaseOrder> stream =
         session.createQuery(
             "from PurchaseOrder o order by o.id",
             PurchaseOrder.class
         )
         .setReadOnly(true)
         .setFetchSize(500)
         .stream()) {

    stream.forEach(order -> {
        // Xử lý ngay; tránh giữ reference lâu.
    });
}
~~~

Streaming behavior phụ thuộc dialect, JDBC driver, cursor mode và transaction/autocommit settings.

- Đóng stream luôn: stream có thể giữ ResultSet, Statement và connection.
- Không chuyển managed entities sang worker thread: Session/EntityManager không thread-safe.
- Fetch size là hint, không bảo đảm cursor: driver có thể bỏ qua hoặc có điều kiện riêng.
- Clear persistence context theo chunk khi semantics cho phép; không clear khi còn cần managed references hoặc pending operations.

Nếu cần parallel processing, map thành immutable DTO/command rồi truyền dữ liệu đã tách khỏi persistence context.

## 17. Read-only và collection/association loading

~~~java
PurchaseOrder order = session.find(PurchaseOrder.class, id);
session.setReadOnly(order, true);
int lineCount = order.getLines().size();
~~~

Truy cập collection lazy vẫn có thể phát SQL và hydrate collection elements. Read-only root không có nghĩa collection đã được load miễn phí.

`@BatchSize` có thể giảm N+1 khi nhiều associations được truy cập, nhưng vẫn hydrate nhiều collections/rows. EntityGraph giúp định nghĩa relations cần load theo use case; fetch join nhiều to-many relations có thể nhân số rows. DTO projection thường dễ kiểm soát hơn cho read API.

Nếu collection thực sự không bao giờ thay đổi, `@Immutable` trên collection là lựa chọn Hibernate-specific. Nếu chỉ một endpoint không muốn sửa collection, DTO/read-only design phù hợp hơn.

## 18. Read-only cache và @Cache(usage = READ_ONLY)

~~~java
@Entity
@org.hibernate.annotations.Immutable
@org.hibernate.annotations.Cache(
    usage = org.hibernate.annotations.CacheConcurrencyStrategy.READ_ONLY
)
@Table(name = "currencies")
public class Currency {
    @Id
    private String code;
    private String displayName;
}
~~~

`READ_ONLY` cache strategy phù hợp với dữ liệu **thực sự bất biến**. Nó không đồng nghĩa với `@Transactional(readOnly=true)`.

Dùng cho lookup/reference tables ít đổi, static catalogs được version hóa hoặc immutable dictionaries. Nếu dữ liệu cần sửa, dùng cache concurrency strategy phù hợp hoặc không cache. Cố update entity trong READ_ONLY cache có thể gây exception/cache behavior không phù hợp theo Hibernate/cache provider.

Second-level cache hit có thể giảm SQL, nhưng cache miss vẫn query DB. Query cache, first-level cache và second-level entity cache có semantics khác nhau; cần đo hit/miss và invalidation. Trong hệ multi-tenant, custom Redis/application cache keys cần đưa tenant identity vào key.

## 19. Read-only transaction và database replica

~~~text
Read API
   -> read-only transaction
   -> replica datasource

Write API
   -> read-write transaction
   -> primary datasource
~~~

`@Transactional(readOnly=true)` **không tự động route sang replica**. Routing thường cần `AbstractRoutingDataSource`, transaction routing policy hoặc kiến trúc datasource riêng.

### 19.1. Routing phải xảy ra trước connection acquisition

Nếu transaction/session đã acquire connection từ primary, việc đổi một ThreadLocal thành replica sau đó không chuyển connection đang dùng.

### 19.2. Replica lag

Một write vừa commit trên primary có thể chưa xuất hiện trên replica. Nếu user ghi rồi đọc ngay, có thể cần read-your-writes routing về primary, chấp nhận eventual consistency hoặc dùng replication position/consistency token nếu kiến trúc hỗ trợ.

Read-only chỉ nói về ý định transaction, không hứa dữ liệu mới nhất toàn hệ thống. Nó cũng không tự chọn REPEATABLE_READ hay SERIALIZABLE; isolation phải được thiết kế theo database và use case.

## 20. Read-only không thay authorization hay tenant isolation

~~~java
@Transactional(readOnly = true)
public PurchaseOrder getOrder(Long id) {
    return repository.findById(id).orElseThrow();
}
~~~

Method read-only vẫn có thể đọc **nhầm tenant** nếu query không scope đúng. Read-only không tự thêm `organization_id` predicate và không ngăn user truy cập resource ngoài quyền.

~~~java
public interface OrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    Optional<PurchaseOrder>
    findByOrganizationIdAndId(
        String organizationId, Long id
    );
}
~~~

Context organization phải được xác minh từ server-side identity/authorization. Read-only là performance/transaction hint, không phải security boundary.

## 21. Flush behavior khi có thay đổi ngoài ý muốn

~~~java
@Transactional(readOnly = true)
public OrderView queryAndMutate(Long id) {
    PurchaseOrder order = repository.findById(id)
        .orElseThrow();

    order.changeStatus(OrderStatus.CANCELLED);
    return OrderView.from(order);
}
~~~

Response có thể hiển thị `CANCELLED` do Java object đã thay đổi, nhưng DB vẫn là `PAID` vì entity được quản lý read-only/flush mode không đồng bộ thay đổi. Đây là bug nguy hiểm vì client nghĩ write đã thành công.

### 21.1. Phân tách command và query

~~~java
@Service
public class OrderQueryService {
    @Transactional(readOnly = true)
    public OrderView get(Long id) {
        // Chỉ đọc, trả DTO.
    }
}

@Service
public class OrderCommandService {
    @Transactional
    public void cancel(Long id) {
        // Load mutable entity và thực hiện domain command.
    }
}
~~~

Tách CQ paths giúp transaction boundaries, authorization và tests rõ ràng.

### 21.2. Không gọi save() như cách “bắt buộc ghi” trong read-only flow

`repository.save()` có thể gọi persist/merge nhưng không có nghĩa transaction read-only sẽ trở thành write transaction. Không thiết kế write operation bên trong read-only method.

### 21.3. Native SQL/JDBC có thể vẫn ghi

Nếu transaction manager chỉ truyền read-only hint và DB không enforce, `JdbcTemplate.update()` hoặc native SQL có thể vẫn thực thi. Để bảo đảm read-only tuyệt đối, dùng DB role/permissions hoặc database-enforced transaction policy tương ứng.

## 22. @Immutable và Envers

Nếu entity được audit bằng Envers rồi mapping thành immutable, cần hiểu mục tiêu:

- Envers ghi lịch sử khi có lifecycle writes mà nó theo dõi.
- Immutable entity không có các UPDATE thông thường qua Hibernate.
- Nếu dữ liệu thay đổi qua JDBC/native SQL, Envers không tự thấy update đó.
- Nếu dữ liệu là append-only, mỗi thay đổi có thể nên tạo entity/version mới thay vì sửa entity cũ.

Nếu cần giữ lịch sử thay đổi Currency/TaxRate, có thể dùng entity mutable + Envers, hoặc mô hình versioned rows:

~~~text
tax_rate_id | valid_from | valid_to | rate
------------+------------+----------+-----
VAT         | 2025-01-01 | 2026-01-01 | 0.10
VAT         | 2026-01-01 | NULL       | 0.12
~~~

Một phiên bản row đã phát hành có thể bất biến; thay đổi tạo row mới. Đây là domain temporal design, không chỉ một annotation.

## 23. Chi phí dirty checking trong batch đọc lớn

~~~java
@Transactional(readOnly = true)
public void exportOrders(String organizationId) {
    List<PurchaseOrder> orders =
        repository.findByOrganizationId(organizationId);

    for (PurchaseOrder order : orders) {
        writeCsv(order);
    }
}
~~~

Nếu danh sách có 500.000 entities, chỉ `readOnly=true` có thể giảm snapshot/dirty checking tùy Hibernate integration, nhưng list và persistence context vẫn có thể giữ toàn bộ entities.

### 23.1. Chuyển sang DTO streaming

~~~java
@Transactional(readOnly = true)
public void exportOrders(String organizationId) {
    try (Stream<OrderExportRow> rows =
             repository.streamExportRows(organizationId)) {
        rows.forEach(csvWriter::write);
    }
}
~~~

Repository query phải projection sang `OrderExportRow` và stream phải được đóng trong transaction phù hợp. Cần xác minh driver fetch behavior, không để client tải CSV chậm giữ connection mở lâu ngoài ý muốn.

### 23.2. Chunked keyset export

~~~java
Long lastId = 0L;

while (true) {
    List<OrderExportRow> chunk =
        repository.fetchAfter(organizationId, lastId, 1000);

    if (chunk.isEmpty()) {
        break;
    }

    writeChunk(chunk);
    lastId = chunk.get(chunk.size() - 1).id();
}
~~~

Mỗi chunk có thể dùng transaction ngắn riêng. Cần xác định consistency: nếu dữ liệu thay đổi trong lúc export, snapshot theo thời điểm bắt đầu hay best-effort current state? Có thể cần watermark, snapshot isolation hoặc immutable export source.

Không giữ một transaction nhiều giờ nếu không cần; transaction dài giữ snapshot/connection và có thể gây vacuum/undo pressure.

## 24. Khi nào StatelessSession đáng cân nhắc?

~~~java
try (StatelessSession stateless =
         sessionFactory.openStatelessSession()) {

    try (Transaction tx = stateless.beginTransaction()) {
        // Read/insert/update/delete explicitly.
        tx.commit();
    }
}
~~~

Lợi ích: không tích lũy persistence context entries như Session thông thường, không automatic dirty checking, giảm memory cho workloads nhiều rows và operations explicit.

Rủi ro: không có identity map như Session thông thường; không dựa vào cascade/lifecycle semantics; quan hệ/collections phải xử lý tường minh; có thể bỏ sót callbacks/interceptors/audit behavior; developer phải quản lý transaction và ordering cẩn thận.

StatelessSession không phải lựa chọn đầu tiên cho API CRUD. Dùng khi đo được persistence context overhead là vấn đề và team chấp nhận semantics explicit.

## 25. Tương tác với @Version và optimistic locking

~~~java
@Entity
public class InventoryItem {
    @Id
    private Long id;

    @Version
    private long version;

    private int available;
}
~~~

Hibernate dùng version để phát hiện stale updates. Read-only entity không đồng bộ persistent field changes thông thường, nên không phát sinh optimistic update theo cách entity mutable.

### 25.1. Read-only không phải “bỏ version check để nhanh hơn” cho writes

Nếu command path cần optimistic locking, giữ entity mutable và transaction write. Không đánh dấu entity read-only chỉ để tránh dirty checking rồi tự update SQL mà quên version predicate.

### 25.2. DTO command cần expected version

~~~json
{
  "status": "CANCELLED",
  "expectedVersion": 4
}
~~~

Server load managed entity và kiểm tra version theo policy; không để client ghi đè `@Version` tùy tiện. Optimistic locking vẫn là concurrency mechanism riêng, không phải read-only feature.

### 25.3. Bulk DML

Bulk JPQL/native SQL thường bypass entity dirty checking và lifecycle callbacks; nếu cần concurrency control, tự đưa expected version/tenant predicate vào SQL và xử lý affected-row count. Read-only transaction không thay đổi semantics đó.

## 26. Testing: chứng minh không phát UPDATE

Một unit test chỉ gọi getter không đủ chứng minh Hibernate không dirty-check hoặc không ghi DB. Cần integration test với database/SQL capture phù hợp.

~~~java
@SpringBootTest
class OrderReadOnlyIT {

    @Autowired
    OrderQueryService queryService;

    @Test
    void queryDoesNotModifyDatabase() {
        OrderView result = queryService.getAndReturn(9001L);

        assertThat(result.status())
            .isEqualTo(OrderStatus.PAID);

        // Re-read committed state trong transaction/persistence
        // context mới hoặc sau khi test transaction kết thúc.
    }
}
~~~

Nếu test class/method tự có `@Transactional`, nó có thể làm thay đổi boundary và che behavior của service.

### 26.1. Đếm SQL statements

Có thể dùng JDBC proxy/instrumentation, Hibernate SQL logging hoặc datasource test wrapper để đếm UPDATE/INSERT/DELETE. Chú ý:

- Schema setup/teardown cũng có SQL.
- Hibernate statistics có scope SessionFactory.
- Request song song có thể làm nhiễu counter.
- Native SQL có thể không xuất hiện trong Hibernate SQL logger.
- SQL log không chứng minh commit; đọc lại DB để xác nhận.

### 26.2. Test mutation trên read-only entity

~~~java
PurchaseOrder order = session.find(PurchaseOrder.class, id);
session.setReadOnly(order, true);

order.changeStatus(OrderStatus.CANCELLED);
session.flush();
~~~

Assert DB vẫn giữ trạng thái cũ theo contract read-only entity của Hibernate version đang dùng. Đồng thời kiểm tra Java object có thể vẫn giữ giá trị mới trong memory; không dùng nó làm response thành công.

### 26.3. Test immutable entity

- Load entity `@Immutable`.
- Thay đổi property trong Java.
- Flush/commit.
- Đọc lại bằng Session mới.
- Xác nhận DB không bị UPDATE theo mapping.
- Kiểm tra collection `@Immutable` mutation có hành vi từ chối mong đợi.
- Xác minh native SQL vẫn có thể thay đổi DB nếu DB permissions cho phép, để chứng minh annotation không phải security boundary.

Test collection/child state, inverse/owning side, cascade và join table riêng. Nếu contract yêu cầu DB-enforced read-only, test EntityManager, JdbcTemplate, native queries và stored procedures trên database thật; không dựa vào H2/in-memory để kết luận behavior của PostgreSQL/MySQL/Oracle.

## 27. Benchmark dirty checking và memory

So sánh các phương án trên cùng dataset:

1. Managed mutable entities.
2. `@Transactional(readOnly=true)` theo Spring/Hibernate integration.
3. `Session.setDefaultReadOnly(true)` hoặc query `setReadOnly(true)`.
4. `@Immutable` entity mapping (nếu domain thật sự immutable).
5. DTO projection.
6. StatelessSession (nếu phù hợp).

### 27.1. Metrics

| Metric | Ý nghĩa |
| --- | --- |
| Query elapsed p50/p95/p99 | Client-observed latency |
| DB execution/rows | Công việc ở database |
| SQL count | Round-trips/statements |
| Rows/bytes returned | Lượng dữ liệu truyền |
| Entity load count | Số entities hydrate |
| Collection fetch count | Số collections được load |
| Heap allocation | Object/snapshot allocation |
| Peak heap/retained heap | Memory persistence context giữ |
| GC pause/frequency | Áp lực heap |
| Flush duration | Dirty checking/action queue cost |
| Connection usage | Thời gian giữ DB resource |
| Throughput | Rows/second hoặc requests/second |

Giữ ổn định database/schema/indexes/dataset, query predicates/sort, page/fetch size, cache warm/cold, JVM heap/GC, connection pool và concurrency. Warm-up JIT/pool, đo nhiều lần và so percentiles.

Nếu DTO projection chỉ chọn 4 columns còn entity query chọn 40 columns, kết quả nhanh hơn không chỉ đến từ dirty checking; đó vẫn là lợi ích hợp lệ nhưng phải nêu đúng nguyên nhân.

### 27.2. Dùng JFR/profiler khi cần

Java Flight Recorder hoặc allocation profiler có thể chỉ ra Hibernate entity/collection hydration, snapshot/state arrays, proxy/collection wrappers, DTO/Jackson allocations, GC pauses, thread blocking và CPU hot methods.

Không suy ra memory savings chỉ từ số SQL statements.

## 28. Những lỗi thiết kế phổ biến

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ `@Transactional(readOnly=true)` chặn mọi write | Raw SQL hoặc DB không enforce vẫn ghi được | DB permissions/policy và service design |
| Đánh dấu mọi entity `@Immutable` để tối ưu | Domain updates bị bỏ qua | Chỉ immutable thật sự theo domain |
| Load 500.000 entities rồi chỉ bật read-only | Vẫn tốn object/PC memory | DTO, pagination, streaming |
| Trả entity trực tiếp cho JSON | Lazy loading/N+1 và accidental mutation | DTO projection |
| Đổi Session default read-only sau khi load entities | Entities cũ có state khác entities mới | Đặt mode trước query hoặc set per entity |
| Tưởng read-only root làm collection immutable | Collection/child vẫn có lifecycle riêng | Mapping/test riêng |
| Dùng `MANUAL` rồi explicit flush tùy tiện | Có thể vẫn ghi SQL | Transaction contract và tests |
| Dùng `@Immutable` cho field có thể đổi | Java state và DB state lệch nhau | Mutable mapping hoặc versioned model |
| Dùng StatelessSession cho CRUD graph | Mất cascade/identity/lazy semantics | Session thông thường |
| Chọn `READ_ONLY` second-level cache cho data mutable | Cache update errors/inconsistency | Cache strategy phù hợp |
| Cho rằng read-only transaction route replica tự động | Query vẫn ở primary | Routing datasource policy |
| Đổi read-only thành write giữa một transaction | Flush/resource semantics khó đoán | Tách command/query transaction |
| Dùng ThreadLocal/OSIV để giữ session qua async | Thread/session safety và context leaks | DTO/IDs + transaction worker riêng |
| Dùng `save()` để ép persist trong read-only method | Write không được commit như mong đợi | Command service write transaction |
| Chỉ test Java object state | Object có thể đổi nhưng DB không đổi | Re-read bằng context mới |
| Chỉ xem SQL count | Không thấy rows/bytes/hydration | Kết hợp DB/JVM/pool metrics |

## 29. Quy trình chọn chiến lược

1. **Có cần managed entity không?** Nếu chỉ trả 3–5 fields, dùng DTO/scalar projection trước. Nếu cần domain behavior/associations, managed entity có thể hợp lý.
2. **Entity có thực sự bất biến theo domain không?** Nếu dữ liệu không bao giờ được sửa sau khi tạo, xem `@Immutable`. Nếu chỉ query hiện tại không muốn sửa, dùng read-only query/session/transaction.
3. **Có cần transaction read-only không?** Nếu use case cần consistent read boundary hoặc Spring/Hibernate optimization, `@Transactional(readOnly=true)` có thể phù hợp. Xác định transaction manager và DB behavior.
4. **Kích thước result/persistence context là bao nhiêu?** Nếu hàng trăm nghìn rows, ưu tiên DTO streaming/keyset/chunking hoặc StatelessSession.
5. **Có collection/association nào được load?** Đánh giá fetch plan, batch size, collection mutability, lazy access và serializer behavior.
6. **Có write side effects ngoài ORM không?** Nếu có JDBC/native SQL/stored procedures, kiểm tra database enforcement.
7. **Đo trước và sau.** Đo query count, rows/bytes, pool usage, DB execution, heap allocation, GC, flush time và latency percentiles.

## 30. Checklist triển khai

- [ ] Phân biệt read-only transaction, read-only entity và immutable mapping.
- [ ] Không dùng read-only annotation như authorization/security control.
- [ ] Kiểm tra transaction manager/provider thực sự áp dụng read-only hint ra sao.
- [ ] Không giả định `readOnly=true` thay đổi transaction đã mở.
- [ ] Thiết lập Session default read-only trước khi load entities cần áp dụng.
- [ ] Dùng per-entity/query read-only khi cần scope nhỏ.
- [ ] Chỉ dùng `@Immutable` cho dữ liệu bất biến theo domain.
- [ ] Kiểm tra immutable collection và association behavior riêng.
- [ ] Không giả định read-only root làm mọi child immutable.
- [ ] Dùng DTO/scalar projection cho API/report chỉ cần một phần fields.
- [ ] Dùng pagination/streaming/chunking cho kết quả lớn.
- [ ] Đóng stream/ResultSet và quản lý transaction lifetime.
- [ ] Không chuyển Session/EntityManager/managed entity sang thread khác.
- [ ] Chỉ dùng StatelessSession khi chấp nhận semantics explicit/no persistence context.
- [ ] Không cache `@Cache(READ_ONLY)` cho entity mutable.
- [ ] Định nghĩa routing/consistency nếu đọc replica.
- [ ] Kiểm tra native SQL/JDBC/stored procedures nếu cần DB-level read-only.
- [ ] Test DB state sau flush/commit bằng persistence context mới.
- [ ] Test collection/child updates và version behavior.
- [ ] Benchmark heap/GC/flush/SQL/network cùng một workload.

## 31. Bài tập thực hành

### Bài 1 — Dirty checking

Giải thích vì sao `order.setStatus(...)` không nhất thiết gửi UPDATE ngay. Nêu các thời điểm Hibernate có thể flush.

### Bài 2 — Snapshot overhead

Một request đọc 100.000 entities nhưng không sửa. Những phần memory nào persistence context có thể giữ? Read-only entity giảm phần nào và không giảm phần nào?

### Bài 3 — Read-only transaction

`@Transactional(readOnly=true)` có bảo đảm JDBC UPDATE luôn bị database từ chối không? Phân biệt Spring hint, Hibernate flush mode và DB permissions.

### Bài 4 — Transaction propagation

Một inner method `REQUIRED(readOnly=true)` được gọi trong outer write transaction. Vì sao không nên giả định transaction hiện có đã biến thành read-only?

### Bài 5 — Default read-only

Một entity được load trước `session.setDefaultReadOnly(true)`, entity khác load sau. Hai entities có chắc cùng read-only status không? Cách xử lý per entity?

### Bài 6 — Query read-only

Viết Hibernate query `setReadOnly(true)` và giải thích tại sao API này không thuộc JPA chuẩn.

### Bài 7 — Immutable entity

Một entity Currency có `@Immutable`, code gọi setter đổi displayName, flush và commit. DB có tự cập nhật không? Vì sao không nên trả object đó như write success?

### Bài 8 — Immutable collection

So sánh `@Immutable` trên entity và trên collection. Khi cố thêm phần tử vào immutable collection, loại behavior nào có thể xảy ra?

### Bài 9 — Attribute immutable

So sánh `@Immutable` trên field với `@Column(updatable=false)`. Cả hai có ngăn native SQL không?

### Bài 10 — DTO projection

Một API chỉ cần id, status, totalAmount. Viết constructor projection và nêu lợi ích so với load entity + lazy associations.

### Bài 11 — StatelessSession

Nêu ít nhất bốn semantics của Session thông thường mà StatelessSession không cung cấp theo cùng cách. Khi nào phù hợp?

### Bài 12 — Bytecode enhancement

Inline dirty tracking giảm công việc nào? Vì sao vẫn cần persistence context và memory management?

### Bài 13 — Collection caveat

Một root entity được set read-only nhưng collection child được thêm phần tử. Vì sao không nên giả định cả graph read-only? Viết integration test cần thiết.

### Bài 14 — Read-only cache

Khi nào `@Cache(usage=READ_ONLY)` phù hợp? Điều gì xảy ra nếu entity thực sự cần cập nhật?

### Bài 15 — Replica routing

`@Transactional(readOnly=true)` có tự route datasource sang replica không? Nếu có replication lag, read-your-writes được xử lý ra sao?

### Bài 16 — Bulk SQL

Một read-only transaction chạy `JdbcTemplate.update()`. Kết quả có chắc bị từ chối không? Cần kiểm tra ở tầng nào?

### Bài 17 — Batch export

Một export nạp 500.000 managed entities trong một List. So sánh read-only entity, DTO keyset pagination và streaming.

### Bài 18 — Flush mode

`FlushMode.MANUAL` có ngăn explicit `flush()` không? Vì sao không nên tự đổi flush mode của Session do Spring quản lý mà không khôi phục?

### Bài 19 — Versioning

Một entity read-only có `@Version`. Có nên dùng nó làm mutable optimistic locking mechanism không? Phân biệt read-only mapping và write transaction.

### Bài 20 — Testing

Thiết kế integration test chứng minh một entity `@Immutable` không phát UPDATE, một immutable collection từ chối mutation và một native SQL write vẫn phụ thuộc DB permissions.

### Bài 21 — Dirty checking benchmark

Đề xuất benchmark so mutable managed entities, Hibernate read-only entities và DTO projection. Những metric nào cần đo ngoài query latency?

### Bài 22 — Read-only response sai

Service thay đổi entity trong read-only transaction rồi trả DTO có status mới, nhưng DB không đổi. Vì sao client nhận dữ liệu gây hiểu nhầm? Thiết kế command/query services riêng.

### Gợi ý đáp án

- **Bài 1:** Thay đổi Java state được đồng bộ khi flush; flush có thể xảy ra ở commit, explicit flush hoặc auto-flush trước query theo mode.
- **Bài 2:** Entity objects, identity map, snapshots, collections/proxies và graph; read-only giảm dirty-check snapshots, không loại hydration/objects.
- **Bài 3:** Không; readOnly là hint/provider integration, DB permissions/transaction policy mới có thể enforce.
- **Bài 4:** Inner REQUIRED tham gia transaction ngoài; attributes không tự đổi physical transaction đã mở.
- **Bài 5:** Không; default áp dụng cho entities load sau thời điểm bật; dùng setReadOnly cho instance.
- **Bài 6:** Gọi `query.setReadOnly(true)` trên Hibernate Query; đây là provider-specific.
- **Bài 7:** Hibernate không phát UPDATE theo immutable mapping; Java object có thể khác DB state.
- **Bài 8:** Entity changes bị bỏ qua theo mapping; immutable collection mutation thường bị từ chối bằng exception.
- **Bài 9:** Semantics khác nhau nhưng cả hai là ORM mapping behavior, không chặn raw SQL/DBA.
- **Bài 10:** Constructor projection chọn đúng columns và không tạo managed entity graph.
- **Bài 11:** Không identity map/automatic dirty checking/cascade/collection lifecycle theo cùng cách; dùng cho explicit bulk processing.
- **Bài 12:** Giảm so sánh state fields ở flush; vẫn có entity objects/persistence context/collections/SQL.
- **Bài 13:** Collection/child state có lifecycle riêng; test root scalar và child/join table separately.
- **Bài 14:** Dữ liệu thực sự immutable; mutable data cần cache strategy phù hợp hoặc không cache.
- **Bài 15:** Không; routing cần datasource policy trước acquire; read-your-writes có thể route primary.
- **Bài 16:** Không chắc; DB/driver/transaction manager enforcement khác nhau; test JDBC/native path trên DB thật.
- **Bài 17:** Read-only giảm snapshots; DTO keyset giảm hydration/PC; streaming giảm peak list memory nhưng phải quản lý cursor/connection.
- **Bài 18:** Explicit flush vẫn có thể chạy; khôi phục mode để tránh ảnh hưởng code khác.
- **Bài 19:** Không; read-only state không dùng để thực hiện optimistic updates; mutable command path cần version check.
- **Bài 20:** Đếm SQL và re-read DB; test collection exception; kiểm tra native SQL theo DB role.
- **Bài 21:** Đo heap/allocation/GC/flush/entity loads/rows/bytes/pool/DB, cùng dataset và cache state.
- **Bài 22:** Java object bị mutate nhưng DB không commit; DTO có thể phản ánh state chưa lưu; tách read query và write command.

---

## Tổng kết

**Chỉ đọc, entity read-only và immutable mapping là ba công cụ khác nhau để quản lý chi phí persistence.**

1. `@Transactional(readOnly = true)` thể hiện ý định transaction và có thể giúp Spring/Hibernate tối ưu flush/read-only state; nó **không phải bảo đảm DB không thể ghi** và không thay authorization.
2. Hibernate Session/query/entity read-only có thể bỏ dirty checking và giảm snapshot memory cho entities được nạp ở trạng thái đó. Entity objects, persistence context và hydration vẫn tồn tại; collection/association phải xem riêng.
3. `@Immutable` dành cho dữ liệu bất biến theo mapping. Hibernate không đồng bộ thay đổi entity/property thông thường; immutable collection có semantics từ chối mutation. Đây không phải DB-level protection.
4. DTO/scalar projection thường là lựa chọn hiệu quả cho read API chỉ cần một phần dữ liệu; pagination/streaming/chunking giải quyết thêm memory khi đọc lớn.
5. StatelessSession giảm persistence context/automatic dirty checking nhưng bỏ nhiều tiện ích managed-entity; chỉ dùng khi chấp nhận semantics explicit.
6. Bytecode-enhanced dirty tracking có thể giảm chi phí so sánh state, nhưng không thay thế fetch planning, projection và memory management.
7. Đo đúng workload bằng SQL counts, rows/bytes, heap allocation, GC, flush duration và database metrics; kiểm tra DB state bằng context mới thay vì chỉ nhìn Java object.

**Chọn cơ chế theo bản chất dữ liệu và use case:** dữ liệu thật sự bất biến thì mapping immutable; transaction chỉ đọc thì khai báo read-only; chỉ cần dữ liệu trình bày thì projection; batch rất lớn thì quản lý persistence context/streaming; còn command cập nhật thì dùng entity mutable trong write transaction với optimistic locking phù hợp.**
