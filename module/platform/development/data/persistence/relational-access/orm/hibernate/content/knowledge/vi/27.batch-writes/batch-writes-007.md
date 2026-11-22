# StatelessSession và khác biệt với Session có context trong Hibernate

Trong Hibernate ORM, một tác vụ nhập hàng trăm nghìn sản phẩm có thể dùng `Session` thông thường hoặc `StatelessSession`. Hai API cùng làm việc với entity mapping và database, nhưng khác nhau về **quản lý trạng thái đối tượng, thời điểm ghi SQL, cascade và trách nhiệm của mã nghiệp vụ**.

- **`Session` (stateful)** có *persistence context*, first-level cache, identity map, dirty checking, write-behind/action queue và các cơ chế cascade/lifecycle.
- **`StatelessSession`** không duy trì persistence context cấp một theo cách trên. Entity được đọc không được theo dõi dirty state; thao tác ghi phải gọi `insert()`, `update()` hoặc `delete()` tường minh; ORM cascade và các entity events/interceptors thông thường không diễn ra như trong Session.

Ví dụ với StatelessSession:

~~~java
try (StatelessSession ss = sessionFactory.openStatelessSession()) {
    Transaction tx = ss.beginTransaction();
    try {
        Product p = new Product("SKU-001", "Bút", new BigDecimal("15000"));
        ss.insert(p);

        p.rename("Bút xanh");
        ss.update(p);  // Không có dirty checking tự động.

        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) tx.rollback();
        throw ex;
    }
}
~~~

Với Session thông thường, một entity được `persist()` hoặc `get()` trở thành managed; Hibernate có thể nhận biết thay đổi ở lần flush:

~~~java
try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();
    try {
        Product p = new Product("SKU-002", "Sổ", new BigDecimal("25000"));
        session.persist(p);
        p.rename("Sổ A");

        tx.commit();  // Dirty checking/flush theo Session.
    } catch (RuntimeException ex) {
        if (tx.isActive()) tx.rollback();
        throw ex;
    }
}
~~~

> **Phạm vi:** Ví dụ theo Hibernate ORM 6.x, Java 17+, Jakarta Persistence và JDBC. StatelessSession là API **riêng của Hibernate**, không phải chuẩn JPA `EntityManager`. Batching, API multi-row, custom SQL và một số tính năng có khác biệt giữa Hibernate 5, các bản 6.x và 7.x. Hãy kiểm chứng đúng phiên bản ứng dụng; không mặc định mọi release có cùng hành vi.

## 1. Vì sao cần cân nhắc StatelessSession?

Một import naïve có thể trông như sau:

~~~java
List<Product> products = parseEntireCsv();
try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();
    for (Product p : products) {
        session.persist(p);
    }
    tx.commit();
}
~~~

Nếu có một triệu bản ghi, bộ nhớ có thể chứa:

1. Một triệu objects trong `products`.
2. Entity entries và các managed objects ở first-level persistence context.
3. Snapshots phục vụ dirty checking.
4. Pending actions trước flush.
5. Associations/collections và JDBC buffers.

Ngay cả khi mã hợp lệ, thao tác có thể bị `OutOfMemoryError`, GC pauses và flush kéo dài. StatelessSession giảm một phần overhead **ORM state tracking**; nhưng nếu input vẫn là List một triệu objects, RAM vẫn lớn.

Hai giải pháp cạnh tranh cần so sánh là **stateful Session + flush/clear** và **StatelessSession + explicit operations**. Khi nhiều rows có thể thay đổi bằng một câu SQL, bulk DML/JDBC loader là lựa chọn thứ ba.

## 2. Persistence context trong Session stateful

Persistence context chứa các entity instances được Hibernate quản lý. Trong cùng Session:

~~~java
Product a = session.get(Product.class, 42L);
Product b = session.get(Product.class, 42L);

assert a == b;
~~~

Điều này xuất phát từ **identity map**: cùng entity key có một managed instance đại diện trong context.

~~~java
Product p = session.get(Product.class, 42L);
p.rename("Tên mới");

// Trong transaction, Hibernate có thể UPDATE khi flush.
~~~

Các thành phần liên quan:

- **Managed lifecycle:** Entity được gắn với persistence context.
- **Dirty checking:** Phát hiện khác biệt giữa state hiện tại và state theo dõi.
- **Write-behind/action queue:** Gom, sắp xếp pending operations đến khi flush phù hợp.
- **Cascade:** Truyền `PERSIST`, `MERGE`, `REMOVE` theo association mapping.
- **Callbacks/events:** Phối hợp entity listeners và Hibernate events.
- **Auto-flush:** Đồng bộ pending SQL theo flush mode.

Đây là cơ chế hữu ích cho aggregate/domain logic, nhưng đi kèm chi phí khi số managed entities quá lớn.

## 3. StatelessSession không quản lý dirty state

~~~java
Product p = ss.get(Product.class, 42L);
p.rename("Tên mới");

// Không tự UPDATE database.
~~~

Muốn ghi:

~~~java
ss.update(p);
~~~

StatelessSession không giữ first-level managed identity map giống Session; gọi `get()` nhiều lần có thể tạo các Java objects độc lập cho cùng row:

~~~java
Product a = ss.get(Product.class, 42L);
Product b = ss.get(Product.class, 42L);

// Không dựa vào a == b.
~~~

“Stateless” không có nghĩa một Hibernate object hoàn toàn không có state vận hành. Nó vẫn có JDBC connection, transaction và query resources. Điểm cần nhớ: **không có lifecycle quản lý entity state như Session stateful**.

## 4. Bảng so sánh

| Thuộc tính | Session có persistence context | StatelessSession |
|---|---|---|
| First-level cache/identity map | Có | Không theo mô hình stateful |
| Managed entity | Có | Không dirty-check như managed entity |
| Dirty checking | Có | Không |
| Automatic flush của changes | Có theo flush mode | Không có managed dirty state để flush |
| SQL write-behind/action queue | Có | Không theo cơ chế stateful |
| CRUD thường dùng | `persist`, `merge`, `remove`, `get` | `insert`, `update`, `delete`, `get` |
| ORM cascade | Có theo mapping | Không cascade lifecycle thông thường |
| Orphan removal | Có theo mapping | Không tự phát hiện |
| Entity events/callbacks | Có theo lifecycle | Bỏ qua lifecycle events/interceptors thông thường |
| Entity aliasing trong cùng session | Identity map giảm rủi ro | Có thể có nhiều copies cùng ID |
| L2 cache | Có thể dùng | Thông thường bypass |
| JDBC connection/transaction | Có | Có |
| Phù hợp | CRUD domain, entity graph | Bulk read/write rows độc lập |
| Tính portable JPA | Có phần JPA tương ứng | Hibernate-specific |

Số câu SQL và throughput không cố định theo bảng này: generator, mapping, JDBC batching, driver và database dialect vẫn ảnh hưởng kết quả.

## 5. Sơ đồ hai mô hình

~~~mermaid
flowchart LR
    A["Application"] --> B["Stateful Session"]
    B --> C["Persistence context"]
    C --> D["Dirty checking + actions"]
    D --> E["Flush SQL/JDBC"]
    A --> F["StatelessSession"]
    F --> G["Explicit get/insert/update/delete"]
    G --> E
    E --> H["Database"]
~~~

Stateful:

~~~text
get/persist -> managed -> thay đổi field -> dirty checking -> flush -> commit
~~~

Stateless:

~~~text
get -> Java object -> thay đổi field -> update(entity) -> commit
~~~

Khi StatelessSession được gọi để ghi, SQL có thể được thực hiện ngay theo operation; nhưng transaction vẫn có thể rollback cho đến khi commit. Không có dirty-check write-behind như Session stateful.

## 6. Entity Product dùng xuyên suốt

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "product")
public class Product {
    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "product_generator"
    )
    @SequenceGenerator(
        name = "product_generator",
        sequenceName = "product_id_seq",
        allocationSize = 50
    )
    private Long id;

    @Column(nullable = false, unique = true, length = 60)
    private String sku;

    @Column(nullable = false, length = 200)
    private String name;

    @Column(nullable = false, precision = 15, scale = 2)
    private BigDecimal price;

    @Version
    private long version;

    protected Product() {}

    public Product(String sku, String name, BigDecimal price) {
        this.sku = sku;
        this.name = name;
        this.price = price;
    }

    public Long getId() { return id; }
    public String getSku() { return sku; }
    public String getName() { return name; }
    public BigDecimal getPrice() { return price; }
    public long getVersion() { return version; }

    public void rename(String name) { this.name = name; }
    public void changePrice(BigDecimal price) { this.price = price; }
}
~~~

PostgreSQL DDL minh họa:

~~~sql
CREATE SEQUENCE product_id_seq START WITH 1 INCREMENT BY 50;

CREATE TABLE product (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(60) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    price NUMERIC(15,2) NOT NULL,
    version BIGINT NOT NULL
);
~~~

Trong dự án thực, sequence allocation/increment, schema migration và mapping phải khớp nhau. Đoạn này chỉ phục vụ bài học; không thay cho migration production.

## 7. Tạo StatelessSession

~~~java
import org.hibernate.SessionFactory;
import org.hibernate.StatelessSession;

try (StatelessSession ss = sessionFactory.openStatelessSession()) {
    // Chủ sở hữu phải đóng StatelessSession.
}
~~~

Nếu đang dùng Hibernate làm JPA provider:

~~~java
SessionFactory sessionFactory =
    entityManagerFactory.unwrap(SessionFactory.class);
~~~

`StatelessSession` không phải một `EntityManager` chuẩn, và API khác với `Session`.

### Với Spring @Transactional

Không nên mặc định `sessionFactory.openStatelessSession()` mới sẽ tham gia chính transaction/connection của EntityManager đã được Spring quản lý. Cần xác nhận integration, transaction manager, session ownership và kết nối thực tế. Nếu tự quản lý session, pattern `beginTransaction/commit/rollback` là cách minh họa rõ ràng.

## 8. Transaction vẫn có ý nghĩa

~~~java
try (StatelessSession ss = sessionFactory.openStatelessSession()) {
    Transaction tx = ss.beginTransaction();
    try {
        ss.insert(new Product(
            "SKU-101", "Bút bi", new BigDecimal("5000")
        ));
        ss.insert(new Product(
            "SKU-102", "Sổ tay", new BigDecimal("30000")
        ));
        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) tx.rollback();
        throw ex;
    }
}
~~~

Nếu INSERT thứ hai lỗi unique/FK constraint, rollback sẽ hoàn nguyên những thay đổi transactional trước đó khi DB hỗ trợ atomicity. `StatelessSession` không tự tạo một transaction phân tán cho các side effects như HTTP calls, message brokers hoặc filesystem.

Không nuốt lỗi SQL rồi tiếp tục dùng transaction đã aborted; PostgreSQL và nhiều môi trường DB có quy tắc rollback rõ ràng sau lỗi statement.

## 9. Đọc bằng get()

~~~java
try (StatelessSession ss = sessionFactory.openStatelessSession()) {
    Product p = ss.get(Product.class, 42L);
    if (p != null) {
        System.out.println(p.getName());
    }
}
~~~

Hibernate hydrate object theo entity mapping, nhưng object đó không được tự dirty-check. Một lần đọc mới có thể trả Java instance khác. Nếu chỉ cần ID/SKU/price cho export, scalar/DTO projection có thể tiết kiệm hơn việc tạo full entity.

## 10. insert(): yêu cầu ghi tường minh

~~~java
Product product = new Product(
    "SKU-203",
    "Bàn phím",
    new BigDecimal("800000.00")
);

try (StatelessSession ss = sessionFactory.openStatelessSession()) {
    Transaction tx = ss.beginTransaction();
    try {
        ss.insert(product);
        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) tx.rollback();
        throw ex;
    }
}
~~~

`insert()` dựa trên entity mapping để xác định table, columns và generated identifier. Nó **không** đưa product vào managed context để Hibernate theo dõi những thay đổi sau này, và **không cascade** persist sang children.

Generator kiểu IDENTITY/SEQUENCE ảnh hưởng khả năng cấp ID và batching. Không giả định một operation insert luôn có đúng một network round trip.

## 11. update(): thiếu dirty checking phải gọi rõ

~~~java
try (StatelessSession ss = sessionFactory.openStatelessSession()) {
    Transaction tx = ss.beginTransaction();
    try {
        Product p = ss.get(Product.class, 42L);
        if (p == null) {
            throw new IllegalArgumentException("Product not found");
        }

        p.changePrice(new BigDecimal("199000.00"));
        ss.update(p);

        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) tx.rollback();
        throw ex;
    }
}
~~~

Nếu chỉ sửa `p.changePrice()` mà không gọi `ss.update(p)`, database không tự thay đổi.

Cần lưu ý `update(entity)` có thể phát SQL gồm nhiều mapped columns, không chỉ field vừa thay đổi. Nếu entity là object dựng thiếu thuộc tính hoặc chứa state cũ, update có thể ghi đè dữ liệu đúng. Với partial updates, cân nhắc SQL UPDATE có danh sách columns tường minh.

## 12. delete(): không có cascade REMOVE thông thường

~~~java
try (StatelessSession ss = sessionFactory.openStatelessSession()) {
    Transaction tx = ss.beginTransaction();
    try {
        Product p = ss.get(Product.class, 42L);
        if (p != null) ss.delete(p);
        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) tx.rollback();
        throw ex;
    }
}
~~~

Nếu Product bị tham chiếu bởi child rows, DB FK có thể từ chối DELETE. Annotation `cascade = REMOVE` trong association không khiến StatelessSession tự thực hiện ORM cascade.

Nếu FK có `ON DELETE CASCADE`, database tự xóa child rows khi parent row bị physical DELETE; đó là **DB cascade**, không phải entity lifecycle cascade. Java `@PreRemove` của các child DB tự xóa không được gọi.

## 13. Không nhầm update() và merge()

JPA/Session stateful có `merge(detachedEntity)`:

~~~java
Product managed = entityManager.merge(detachedProduct);
~~~

Merge copy state vào managed instance trong persistence context. StatelessSession không có managed context tương tự; `update()` là operation ghi tường minh theo entity mapping.

Không thay `merge()` bằng `stateless.update()` một cách máy móc khi chưa xét:

- Entity mới hay đã tồn tại?
- Identifier hợp lệ?
- Version có stale?
- Field nào đang NULL hoặc chưa được load?
- Các relationships cần thao tác riêng không?
- Có callback/validation trước đây tự chạy?

Một object chỉ có ID và price nhưng các field khác NULL có thể gây mất dữ liệu khi update nhiều columns. SQL mutation đúng columns thường thích hợp hơn.

## 14. Flush/clear thuộc mẫu stateful

Trong Session:

~~~java
session.persist(product);
session.flush();
session.clear();
~~~

`flush()` đồng bộ pending changes với DB; `clear()` detach managed entities, giảm first-level cache.

StatelessSession không có managed dirty-state queue tương tự để flush/clear theo cách này. Muốn giới hạn memory, xử lý input theo lô và quản lý transaction/objects ở application.

Không sao chép phương thức của `Session` sang `StatelessSession` chỉ vì tên gần giống.

## 15. Cascading cần được thay bằng explicit operations

Giả sử:

~~~java
@Entity
class PurchaseOrder {
    @Id Long id;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    List<OrderLine> lines = new ArrayList<>();
}

@Entity
class OrderLine {
    @Id Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "order_id")
    PurchaseOrder order;
}
~~~

Với Stateful Session:

~~~java
session.persist(order);
// Cascade PERSIST có thể lưu child theo mapping.
~~~

Với StatelessSession:

~~~java
ss.insert(order);
// Không tự insert toàn bộ OrderLine.
~~~

Cần thuật toán tường minh:

~~~java
ss.insert(order);

for (OrderLine line : lines) {
    line.attachTo(order);
    ss.insert(line);
}
~~~

Thứ tự, ID generation và owning side/FK phải đúng với schema thật. Không có cascade không đồng nghĩa database bỏ qua referential integrity.

## 16. Thứ tự INSERT/DELETE và foreign key

Schema:

~~~sql
CREATE TABLE purchase_order (
    id BIGINT PRIMARY KEY
);

CREATE TABLE order_line (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES purchase_order(id)
);
~~~

Thứ tự insert thường:

~~~text
INSERT purchase_order
INSERT order_line (order_id đã hợp lệ)
~~~

Thứ tự delete khi FK không cascade:

~~~text
DELETE order_line
DELETE purchase_order
~~~

Stateful Hibernate có action queue/cascade để phối hợp với mapping. Stateless code phải xác định thứ tự operations. Khi batch import graph phức tạp, sự khác biệt này có thể làm tăng độ phức tạp ứng dụng đáng kể.

## 17. orphanRemoval không tự phát hiện orphan

Với Stateful Session, remove child khỏi managed collection có `orphanRemoval=true` có thể khiến Hibernate DELETE child khi flush.

StatelessSession không theo dõi collection snapshots để phát hiện child bị tách khỏi parent. Nếu yêu cầu xóa OrderLine, phải gọi `ss.delete(line)` hoặc một SQL DELETE thích hợp.

Đừng giả định việc sửa `order.getLines()` rồi `ss.update(order)` sẽ tự tìm children bị xóa/thêm. Các child/association operations phải được thiết kế tường minh.

## 18. Entity callbacks và interceptors

Với Stateful Session, các annotations như:

~~~java
@PrePersist
void beforeInsert() {
    // Đặt createdAt, chuẩn hóa SKU...
}

@PreUpdate
void beforeUpdate() {
    // Ghi metadata...
}

@PreRemove
void beforeDelete() {
    // Kiểm tra invariant...
}
~~~

có thể chạy theo lifecycle. **StatelessSession bỏ qua Hibernate event model/interceptors và JPA entity callbacks thông thường.**

Do đó, nếu trước đây `@PrePersist` tự điền timestamp, batch stateless insert có thể thiếu timestamp.

Hướng xử lý:

- Validate và normalize trong service trước khi `insert()`.
- Gọi domain methods tường minh.
- Dùng DB DEFAULT/CHECK/UNIQUE/NOT NULL constraints phù hợp.
- Nếu audit áp dụng với mọi writer, dùng database trigger/CDC hoặc workflow outbox.
- Không đặt toàn bộ authorization/tenant checks vào callback có thể bị bỏ qua.

Database triggers vẫn có thể được kích hoạt bởi SQL của stateless operations, nhưng không phải Java ORM callbacks.

## 19. Identity aliasing và lost update

Vì không có identity map:

~~~java
Product first = ss.get(Product.class, 10L);
Product second = ss.get(Product.class, 10L);

first.changePrice(new BigDecimal("200000"));
second.rename("Tên mới");

ss.update(first);
ss.update(second);
~~~

Nếu hai objects giữ các phiên bản state khác nhau, thao tác UPDATE thứ hai có thể ghi đè field của update thứ nhất:

~~~text
DB:     price=100000, name=A
first:  price=200000, name=A
second: price=100000, name=Tên mới

update(first):  price=200000, name=A
update(second): price=100000, name=Tên mới
~~~

Đây là **data aliasing risk**, thậm chí trong cùng một thread. Cần deduplicate theo ID/natural key, dùng version checking, tránh partial entities và cân nhắc SQL update đúng columns.

## 20. Optimistic locking với @Version

Entity có thể khai báo:

~~~java
@Version
private long version;
~~~

Stateful Session phối hợp version với managed entity updates. Stateless operations trên versioned entity có thể dùng optimistic locking theo mapping/phiên bản Hibernate, nhưng không tự giả định semantics giống dirty checking trong mọi trường hợp.

Integration test nên:

1. Cho hai transactions đọc cùng row/version.
2. Transaction 1 update và commit.
3. Transaction 2 update dựa trên state cũ.
4. Kiểm tra xung đột/version exception hoặc policy phù hợp.
5. Xác nhận DB version thay đổi đúng.

Nếu dùng native SQL:

~~~sql
UPDATE product
SET price = :newPrice,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion
~~~

Kết quả 0 rows cần được xử lý như conflict/not-found. Không dùng StatelessSession thay cho concurrency strategy.

## 21. Memory vẫn có thể tăng khi stateless

Không giữ first-level cache không có nghĩa toàn hệ thống chỉ dùng O(1) RAM.

Những nguyên nhân khác:

- Đọc toàn bộ CSV vào `List<Product>`.
- JDBC driver buffer rows khi streaming.
- Một queue không giới hạn chứa messages.
- Consumer gom danh sách kết quả/lỗi.
- Associations/DTOs được giữ sau khi xử lý.

Pipeline hiệu quả thường là:

~~~text
CSV reader từng dòng
      |
parse + validate
      |
batch nhỏ trong RAM
      |
StatelessSession explicit INSERT/UPDATE
      |
commit + checkpoint
      |
batch tiếp
~~~

Chỉ thay Session thành StatelessSession trong một vòng `for` trên List cực lớn chưa giải quyết memory của input.

## 22. Ghi hàng loạt bằng Session + flush/clear

Nếu cần cascade/callbacks, Session vẫn có thể ghi hiệu quả theo batch:

~~~java
int batchSize = 50;
int processed = 0;

try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();
    try {
        for (Product p : readProductsLazily()) {
            session.persist(p);
            processed++;

            if (processed % batchSize == 0) {
                session.flush();
                session.clear();
            }
        }

        session.flush();
        session.clear();
        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) tx.rollback();
        throw ex;
    }
}
~~~

`readProductsLazily()` là nguồn input minh họa, có resource lifecycle riêng.

Ưu điểm: tiếp tục dùng managed lifecycle, cascade và callbacks. Nhược điểm: cần flush/clear đúng thời điểm; clear detach toàn context, có thể làm mất pending changes nếu dùng sai và khiến references trở thành detached.

Với các association graph lớn, batch boundaries phải giữ tính nhất quán quan hệ.

## 23. Ghi hàng loạt bằng StatelessSession

~~~java
try (StatelessSession ss = sessionFactory.openStatelessSession()) {
    Transaction tx = ss.beginTransaction();
    try {
        for (Product p : readProductsLazily()) {
            validate(p);
            ss.insert(p);
        }
        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) tx.rollback();
        throw ex;
    }
}
~~~

Không cần flush/clear để quản lý persistence context. Tuy nhiên cần tường minh:

- Validation/defaults từng row.
- Thứ tự parent-child/FK.
- Generated ID và version mapping.
- Duplicate ID/unique key behavior.
- Transaction/rollback.
- Retry/idempotency.
- JDBC batching support của chính Hibernate version.

**Một vòng `for` không tự chứng minh có JDBC statement batching.**

## 24. Transaction batching khác JDBC batching

**Transaction batch:** Ghi 1.000 rows rồi commit. Đây là quyết định atomicity và resource duration.

**JDBC batch:** Gom nhiều statement executions bằng JDBC batch API để giảm network round trips.

Hai khái niệm độc lập:

~~~text
Transaction: 1.000 rows
     |
     +--- JDBC batch 50 statements (nếu hỗ trợ)
     +--- JDBC batch 50 statements
     +--- ...
~~~

StatelessSession thích hợp xử lý nhiều rows với overhead context thấp nhưng mức độ JDBC batching **khác nhau theo Hibernate version/API**. Không khẳng định nó tự dùng `hibernate.jdbc.batch_size` trong mọi 5/6/7 release.

Trước khi chọn:

- Xác định exact Hibernate version.
- Xem API batching của StatelessSession trong version đó.
- Đo JDBC batch executions/round trips.
- Kiểm tra IDENTITY/SEQUENCE mapping.
- So sánh với Session + flush/clear và JDBC trực tiếp.

## 25. Cấu hình batching cho Session có context

~~~properties
hibernate.jdbc.batch_size=50
hibernate.order_inserts=true
hibernate.order_updates=true
~~~

Stateful Session có thể dùng cấu hình này để nhóm/sắp xếp SQL operations tương thích. Mức độ sử dụng thật phụ thuộc ID generator, SQL shape, mapping, dialect và driver.

**Không tự chuyển kết luận này sang StatelessSession.** Một số phiên bản có cơ chế batch riêng hoặc không áp dụng cùng thiết lập. Cần quan sát JDBC metrics/SQL thực tế.

## 26. IDENTITY và SEQUENCE khác biệt thế nào?

Với:

~~~java
@GeneratedValue(strategy = GenerationType.IDENTITY)
~~~

Hibernate thường phải thực hiện INSERT để lấy database-generated ID, hạn chế việc trì hoãn/batching inserts trong một số cấu hình.

Với:

~~~java
@GeneratedValue(strategy = GenerationType.SEQUENCE)
~~~

ID có thể được lấy trước INSERT; sequence pooling/allocation phù hợp có thể giảm round trips cấp ID và thuận lợi cho batch trong môi trường hỗ trợ.

Nhưng:

- Không phải DB nào cũng có native sequence.
- `allocationSize` phải phù hợp schema.
- Gaps trong sequence có thể bình thường.
- Stateless batching rules vẫn riêng theo version.
- Cần benchmark với workload thật.

## 27. Transactions theo từng lô để tránh transaction khổng lồ

Một transaction ghi triệu rows có thể giữ locks/undo/WAL lâu, chậm rollback, dễ timeout. Nếu domain cho phép partial progress:

~~~java
void writeBatch(List<Product> batch) {
    try (StatelessSession ss = sessionFactory.openStatelessSession()) {
        Transaction tx = ss.beginTransaction();
        try {
            for (Product p : batch) {
                validate(p);
                ss.insert(p);
            }
            tx.commit();
        } catch (RuntimeException ex) {
            if (tx.isActive()) tx.rollback();
            throw ex;
        }
    }
}
~~~

Bên ngoài:

~~~java
List<Product> batch = new ArrayList<>(1000);

for (Product p : incomingProducts()) {
    batch.add(p);
    if (batch.size() == 1000) {
        writeBatch(batch);
        batch.clear();
    }
}
if (!batch.isEmpty()) {
    writeBatch(batch);
}
~~~

Nếu batch A commit và batch B lỗi, dữ liệu đã ghi một phần. Cần checkpoint và idempotency; nếu phải all-or-nothing, cân nhắc staging + publish/merge hoặc transaction policy khác.

Đây là **batch transactions**, không tự đồng nghĩa JDBC statement batching.

## 28. Retry và idempotency

Nếu bảng có `sku UNIQUE`, retry batch đã commit có thể vi phạm constraint:

~~~sql
INSERT INTO product(sku, name, price)
VALUES ('SKU-A', 'Sản phẩm A', 100000);
~~~

Có thể dùng:

- Checkpoint sau commit, resume đúng vị trí.
- Unique natural key và logic kiểm tra duplicate.
- Database UPSERT, ví dụ PostgreSQL `ON CONFLICT`, nếu chấp nhận DB-specific syntax.
- Staging tables và merge.
- Import job ID/row hash.

Không mặc định `ss.insert()` có nghĩa UPSERT. Một số Hibernate versions có thêm upsert API nhưng availability/dialect khác nhau.

## 29. Lỗi DB phải rollback đúng

Không an toàn:

~~~java
for (Product p : batch) {
    try {
        ss.insert(p);
    } catch (Exception ex) {
        log.warn("Skipped", ex);
        // Có thể đang ở transaction bị aborted.
    }
}
~~~

Với PostgreSQL, một SQL error thông thường có thể làm transaction phải rollback trước khi tiếp tục, trừ khi savepoint được quản lý đúng.

Thiết kế đáng tin cậy:

1. Validate trước khi ghi.
2. Rollback batch lỗi.
3. Log row ID/natural key và nguyên nhân.
4. Retry với batches nhỏ hơn nếu policy cho phép.
5. Dùng savepoints chỉ khi DB/transaction manager hỗ trợ rõ ràng.
6. Không tiếp tục dùng Session sau Hibernate/JDBC exception nghiêm trọng nếu provider yêu cầu kết thúc unit of work.

Nuốt exception có thể khiến dữ liệu không đầy đủ và báo cáo sai.

## 30. Second-level cache và stale state

Stateful Session có thể đọc/ghi L2 cache theo cấu hình. StatelessSession thông thường bypass second-level cache.

Nhưng khi StatelessSession thay đổi DB rows, một stateful Session hoặc process khác có thể đang giữ dữ liệu trong L1/L2 cache. Không giả định mọi cache tự đồng bộ hoàn toàn.

Nếu có nhiều writers/readers:

- Xác định invalidation/eviction behavior của Hibernate version.
- Kiểm tra entity, collection và query cache regions.
- Với SQL ngoài ORM, cần policy invalidation riêng.
- Test cache và persistence context của nhiều sessions.
- Không dùng stale cached entity như nguồn duy nhất cho quyết định concurrency.

Evict L2 không tự cập nhật object đã managed trong first-level context khác.

## 31. StatelessSession không thread-safe

StatelessSession không có managed PC, nhưng vẫn sở hữu connection, transaction và query resources. Nó không phải một immutable singleton dùng chung threads.

Không nên:

~~~java
StatelessSession shared = sessionFactory.openStatelessSession();
// Nhiều threads đồng thời gọi shared.insert(...).
~~~

Nên:

- Mỗi worker sở hữu một session và transaction.
- Partition input theo key để giảm conflicts.
- Giới hạn concurrency theo connection pool/DB capacity.
- Dùng bounded queue thay vì tích lũy vô hạn.
- Có retry logic cho deadlock/serialization conflict.

**Stateless về entity state không đồng nghĩa thread-safe.**

## 32. Associations và lazy fetching

Stateful Session quản lý lazy proxies/collections thông qua context. StatelessSession không có managed context tương đương, vì vậy không nên giả định mọi lazy association sẽ hoạt động như trong Session thường.

Nếu cần dữ liệu liên quan:

- Dùng HQL/SQL projection với JOIN rõ ràng.
- Truy vấn children riêng theo batch.
- Kiểm tra explicit fetch support của phiên bản StatelessSession.
- Không giữ entity rồi truy cập LAZY association sau khi đóng session.
- Không kỳ vọng cascade tự load/ghi graph.

Ví dụ DTO:

~~~java
record ProductRow(Long id, String sku, String name) {}

List<ProductRow> rows = ss.createQuery(
    """
    select new com.example.ProductRow(p.id, p.sku, p.name)
    from Product p
    where p.price >= :minimum
    """,
    ProductRow.class
)
.setParameter("minimum", new BigDecimal("100000"))
.getResultList();
~~~

Tên `com.example.ProductRow` là placeholder của lớp DTO thật; constructor phải khớp. Với lượng dữ liệu lớn, stream hoặc phân trang thay vì materialize toàn bộ List.

## 33. Soft delete, filters và custom SQL

Khi ứng dụng dùng soft delete hoặc SQL riêng của Hibernate, ví dụ:

~~~java
@SQLDelete(sql = "UPDATE product SET deleted = true WHERE id = ?")
@SQLRestriction("deleted = false")
@Entity
class Product {
    // Các thuộc tính entity.
}
~~~

Cần kiểm tra behavior **đúng Hibernate version**. Custom SQL với `@Version` có thể đòi placeholders hoặc semantics đặc biệt. Hibernate mới có thêm cơ chế soft-delete khác.

Trước khi dùng `ss.delete()`:

1. Xem SQL thật phát ra.
2. Xác nhận row bị xóa vật lý hay chỉ đánh dấu deleted.
3. Kiểm tra stateless queries có áp dụng restriction/filter đúng.
4. Kiểm tra auditing và retention policy.
5. Viết integration tests với DB production-like.

Không dựa trên một annotation để khẳng định mọi release có behavior giống stateful Session.

## 34. Tenant và bảo mật dữ liệu

Nếu hệ thống phụ thuộc:

- Hibernate `@Filter`, `@TenantId`, multi-tenancy.
- Entity listeners để set tenantId/createdBy.
- Application permissions.
- Database row-level security.

thì chuyển sang StatelessSession phải được kiểm thử riêng. Logic đặt trong `@PrePersist` có thể không chạy. Tenant ID và authorization phải được thực hiện trong service và/hoặc enforce tại database.

Không dùng một callback có thể bị bypass như hàng rào bảo mật duy nhất.

## 35. Bulk HQL/SQL có thể phù hợp hơn

Nếu tăng giá cho hàng trăm nghìn sản phẩm cùng rule:

~~~java
int changed = entityManager.createQuery(
    """
    update Product p
    set p.price = p.price * :factor
    where p.active = true
    """
)
.setParameter("factor", new BigDecimal("1.05"))
.executeUpdate();
~~~

Một bulk query có thể hiệu quả hơn việc load và `update()` từng Product. Nhưng bulk HQL/native DML cũng bỏ qua managed entity lifecycle trên từng row và cần xử lý cache/version/context consistency.

| Nhu cầu | Công cụ cân nhắc |
|---|---|
| Mỗi row tính toán riêng bằng Java | StatelessSession hoặc Session batch |
| Cùng một phép cập nhật cho nhiều rows | Bulk HQL/SQL |
| Dữ liệu nhập cực lớn | JDBC batch, COPY, DB bulk loader |
| Phải dùng callbacks/cascade đầy đủ | Stateful Session |
| Export chỉ vài columns | DTO/scalar projection |

StatelessSession vẫn sử dụng Hibernate entity mapping; nó không phải JDBC PreparedStatement được đổi tên.

## 36. Stateful read-only khác StatelessSession

Trong Session thường:

~~~java
session.setDefaultReadOnly(true);
~~~

Hoặc:

~~~java
query.setReadOnly(true);
~~~

có thể giảm dirty-checking overhead trong một số tình huống, nhưng Session **vẫn có persistence context/identity map**.

| Kỹ thuật | Ý nghĩa |
|---|---|
| Stateful Session | Managed entities |
| Read-only Session/query | Vẫn stateful nhưng giảm một phần tracking |
| StatelessSession | Không có managed PC theo kiểu stateful |
| DTO projection | Không hydrate managed entity đầy đủ |
| Keyset pagination | Giới hạn batch/page và tạo điểm resume |

Với report đơn giản, DTO projection + pagination có thể đủ mà không cần chuyển sang stateless.

## 37. Dùng StatelessSession để đọc nhiều rows

~~~java
try (StatelessSession ss = sessionFactory.openStatelessSession()) {
    Transaction tx = ss.beginTransaction();
    try {
        Query<Product> query = ss.createQuery(
            "select p from Product p order by p.id",
            Product.class
        );
        query.setFetchSize(250);

        try (Stream<Product> stream = query.stream()) {
            stream.forEach(this::writeCsvRow);
        }

        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) tx.rollback();
        throw ex;
    }
}
~~~

Dù không có L1 dirty tracking, JDBC vẫn có thể giữ ResultSet, Statement, connection/cursor. `fetchSize` là driver hint, không đảm bảo chỉ có 250 rows trên heap. Stream phải đóng bằng try-with-resources.

Khi job rất dài hoặc cần resume, keyset pagination với transaction ngắn thường thuận tiện hơn một cursor mở hàng giờ.

## 38. Ghi cha-con theo transaction

Stateless insert Order và children:

~~~java
ss.insert(order);

for (OrderLine line : orderLines) {
    line.attachTo(order);
    ss.insert(line);
}
~~~

Nếu child thứ mười lỗi constraint, rollback cả transaction nếu Order cần atomicity.

Với update/xóa graph, phải tường minh từng child operation hoặc SQL/FK action phù hợp. Không chia một aggregate phụ thuộc nhau thành nhiều transactions nếu trạng thái trung gian không được phép tồn tại.

## 39. Pipeline import toàn diện

~~~mermaid
flowchart TD
    A["Đọc từng dòng"] --> B["Parse + validate"]
    B --> C["Normalize SKU/price/tenant"]
    C --> D["Batch giới hạn trong RAM"]
    D --> E["StatelessSession + transaction"]
    E --> F["Explicit insert/update"]
    F --> G{"Thành công?"}
    G -- "Có" --> H["Commit"]
    H --> I["Checkpoint"]
    I --> J["Batch kế tiếp"]
    G -- "Không" --> K["Rollback"]
    K --> L["Log/retry/reject theo policy"]
~~~

Pipeline cần trả lời:

- Duplicate ID/SKU được xử lý thế nào?
- Retry sau commit nhưng trước checkpoint có double-insert không?
- Import có cần all-or-nothing không?
- Callback/audit/tenant constraints đã được chuyển ra đâu?
- Rows có thể bị người dùng khác sửa đồng thời không?

StatelessSession không tự cung cấp exactly-once processing hay idempotency.

## 40. Integration test phân biệt dirty checking

~~~java
@Test
void statelessNeedsExplicitUpdate() {
    Long id = insertFixtureProduct("SKU-TEST-1");

    try (StatelessSession ss = sessionFactory.openStatelessSession()) {
        Transaction tx = ss.beginTransaction();
        Product p = ss.get(Product.class, id);
        p.rename("Chỉ đổi trong Java");
        tx.commit();
    }

    try (StatelessSession verify = sessionFactory.openStatelessSession()) {
        Product actual = verify.get(Product.class, id);
        assertNotEquals("Chỉ đổi trong Java", actual.getName());
    }
}
~~~

Đối chứng với `update()`:

~~~java
@Test
void explicitUpdatePersists() {
    Long id = insertFixtureProduct("SKU-TEST-2");

    try (StatelessSession ss = sessionFactory.openStatelessSession()) {
        Transaction tx = ss.beginTransaction();
        Product p = ss.get(Product.class, id);
        p.rename("Tên đã ghi");
        ss.update(p);
        tx.commit();
    }

    try (StatelessSession verify = sessionFactory.openStatelessSession()) {
        Product actual = verify.get(Product.class, id);
        assertEquals("Tên đã ghi", actual.getName());
    }
}
~~~

`insertFixtureProduct()` và `sessionFactory` thuộc test fixture của dự án. Test thêm version conflicts, FK, callbacks và cache nếu có liên quan.

## 41. Test cascade và callbacks đúng cơ chế

Một test dễ nhầm: nếu FK có `ON DELETE CASCADE`, xóa parent bằng StatelessSession có thể xóa children **do database**, không phải do ORM cascade.

Nên:

- Test FK không có ON DELETE CASCADE để quan sát stateless parent delete bị DB chặn.
- Test Session stateful với cascade REMOVE để quan sát ORM lifecycle.
- Phân biệt DB triggers với JPA callbacks.
- Test orphanRemoval trên managed stateful graph.
- Xác nhận stateless insert parent không tự insert children.
- Test SQL thật và row counts thay vì chỉ dựa vào state Java.

## 42. Benchmark hợp lý

| Biến thể | Cần đo |
|---|---|
| Stateful naïve | Peak heap, flush time |
| Stateful + flush/clear | Managed entity count, throughput |
| Stateful + JDBC batching | Batch executions, round trips |
| StatelessSession | Heap, SQL count, batching behavior |
| JDBC batch/DB loader | Throughput khi ít ORM lifecycle |
| Bulk HQL/SQL | Tốc độ khi chung một update rule |

Đo rows/s, DB CPU/IO/WAL, network RTT, GC, transaction duration, connection pool wait, rollback/retry và audit behavior.

Không coi benchmark công bằng nếu một biến thể bỏ validation/callbacks mà biến thể khác vẫn chạy đầy đủ.

## 43. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Đổi field nhưng DB không đổi | Không dirty checking | `update()` tường minh |
| Parent có, children thiếu | Không cascade persist | Insert children đúng FK |
| Delete parent lỗi FK | Không cascade remove | Xử lý child/DB referential action |
| Callback không chạy | Stateless bypass lifecycle | Service validation/DB defaults |
| Hai objects cùng ID ghi đè nhau | Không identity map | Deduplicate, optimistic lock |
| Update làm mất fields khác | Stale/partial entity | Versioning/SQL update đúng cột |
| RAM tăng dù stateless | Input List/driver buffer | Streaming input, bounded batches |
| JDBC batch không chạy | Version/config/generator | Xác nhận Hibernate version, metrics |
| Import partial fail | Không checkpoint/idempotency | Staging, retry strategy |
| Cache vẫn stale | L2/other contexts | Cache invalidation policy |
| Tenant/soft delete sai | Mapping/callback assumptions | Integration tests theo DB/version |
| Concurrency lỗi | Share StatelessSession threads | Mỗi worker session riêng |
| Transaction aborted | Tiếp tục sau SQL exception | Rollback trước retry |

## 44. Chọn API theo tình huống

| Tình huống | Lựa chọn thường phù hợp |
|---|---|
| CRUD aggregate nhiều child/listeners | Stateful Session/JPA |
| Import độc lập hàng triệu rows | StatelessSession hoặc JDBC batch |
| Import cần cascade graph phức tạp | Stateful + flush/clear hoặc stateless graph algorithm rõ |
| Update nhiều rows cùng quy tắc | Bulk HQL/SQL |
| Export vài fields | DTO/scalar projection + stream/pagination |
| Job lâu cần retry/resume | Keyset pagination + transactions theo batch |
| Domain phụ thuộc entity listeners | Stateful hoặc refactor trước |
| Cần portable giữa JPA providers | JPA EntityManager |
| Tối đa DB ingestion throughput | DB bulk loader/COPY/staging |
| Concurrent updates quan trọng | Version/lock strategy rõ |

## 45. Checklist trước khi triển khai

**Domain và semantics**

- [ ] Chấp nhận bỏ dirty checking và managed identity map?
- [ ] Cascade/orphan removal đã được thay bằng explicit operations?
- [ ] Callbacks/audit/timestamps/tenantId có cơ chế thay thế?
- [ ] Không update stale/partial entity gây mất fields?
- [ ] Version/locking được kiểm thử?

**Schema và mapping**

- [ ] ID generator và DB sequence/identity phù hợp?
- [ ] Thứ tự operations thỏa FK?
- [ ] Soft delete/custom SQL/filter/tenant được kiểm chứng?
- [ ] Có unique constraints và deduplication?
- [ ] Ràng buộc fields bắt buộc có ở DB?

**Vận hành**

- [ ] Input không materialize toàn bộ file?
- [ ] Transaction batch size/rollback policy rõ?
- [ ] JDBC batching behavior xác nhận đúng Hibernate version?
- [ ] Checkpoint/idempotency cho partial commits?
- [ ] Không share Session giữa threads?
- [ ] Đã đo heap/SQL/DB load?

**Kiểm thử**

- [ ] Stateful vs stateless dirty checking?
- [ ] Cascade/callback behavior?
- [ ] Version/FK/duplicate/rollback?
- [ ] Cache/tenant/soft-delete?
- [ ] Database/dialect production-like?

## 46. Câu hỏi thường gặp

**1. StatelessSession có luôn nhanh hơn Session?** Không. Nó giảm context overhead nhưng SQL, JDBC batching, driver, constraints và transaction policy vẫn quyết định throughput.

**2. StatelessSession có first-level cache không?** Không có identity map/persistence context theo kiểu Session managed entities.

**3. Có cần flush() sau mỗi 50 inserts không?** Không dùng stateful flush/clear pattern; quản lý transaction batches và API batching thích hợp phiên bản.

**4. CascadeType.ALL tự lưu children không?** Không theo lifecycle cascade thông thường. Child operations phải tường minh.

**5. Có dùng @Version không?** Có thể, nhưng optimistic locking semantics phải test đúng mapping/version; native/bulk DML khác.

**6. Có thread-safe không?** Không nên coi là thread-safe; mỗi worker một session/transaction.

**7. Nếu chỉ đọc, có cần stateless?** Chưa chắc; read-only Session, DTO projection và pagination có thể đủ.

**8. L2 cache thì sao?** Stateless thường bypass, nhưng cache readers khác có thể stale khi DB thay đổi; cần invalidation strategy.

**9. Trong Spring @Transactional được không?** Cần xác nhận stateless session thực sự tham gia đúng transaction; không mặc định `openStatelessSession()` tham gia EntityManager transaction đã có.

**10. Khi nào không nên chuyển sang StatelessSession?** Khi phụ thuộc nặng vào dirty checking, callbacks, cascades, identity map hoặc complex association graphs chưa xử lý tường minh.

## 47. Mô hình ghi nhớ cuối bài

~~~mermaid
flowchart TD
    A["Cần ghi hàng loạt"] --> B{"Cần cascade, callbacks, dirty checking?"}
    B -- "Có" --> C["Stateful Session"]
    C --> D["flush + clear / JDBC batching"]
    B -- "Không" --> E{"Cùng một SQL rule cho mọi rows?"}
    E -- "Có" --> F["Bulk HQL/SQL/DB loader"]
    E -- "Không" --> G["StatelessSession"]
    G --> H["Explicit CRUD + FK order + validation"]
    H --> I["Transactions theo batch"]
    I --> J["Version/cache/idempotency"]
    J --> K["Benchmark DB thực tế"]
    D --> K
    F --> K
~~~

**Session có context** quản lý vòng đời entity: identity map, dirty checking, cascade, events và flush. **StatelessSession** dùng entity mapping mà **không giữ first-level persistence context để theo dõi thay đổi**; ghi là explicit và trách nhiệm điều phối chuyển sang application.

Trong ghi hàng loạt, chọn công cụ theo độ phức tạp domain, transaction boundaries, ràng buộc FK, callbacks, cache và optimistic locking. Đo hiệu năng trên **đúng Hibernate version và JDBC driver**; không coi StatelessSession là một công tắc tự bật JDBC batching hoặc giữ nguyên toàn bộ semantics của Session stateful.
