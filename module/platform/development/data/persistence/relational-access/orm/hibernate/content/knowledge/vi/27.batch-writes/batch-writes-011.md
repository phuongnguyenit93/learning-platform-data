# Chọn ORM, HQL mutation hoặc JDBC theo bằng chứng hiệu năng

## 1. Quyết định quan trọng nhất khi ghi hàng loạt

Trong ứng dụng Java dùng Hibernate, một tác vụ ghi hàng loạt (*bulk writing*) có thể triển khai theo nhiều cách:

1. **ORM entity lifecycle:** tạo hoặc tải entity, thay đổi trạng thái Java, để Hibernate sinh INSERT/UPDATE/DELETE; có thể bật JDBC batching.
2. **HQL bulk mutation:** dùng một câu `update`, `delete` hoặc `insert ... select` tác động lên cả tập entity theo điều kiện.
3. **JDBC trực tiếp:** viết SQL, bind parameter và quản lý `PreparedStatement`/`executeBatch()` hoặc khai thác cơ chế nạp dữ liệu đặc thù DBMS.

Không có phương án luôn nhanh nhất cho mọi bài toán. Một câu HQL UPDATE có thể vượt xa vòng lặp sửa entity khi cần cập nhật cùng một trạng thái trên 500.000 hàng. Ngược lại, ORM có thể là lựa chọn đúng nếu mỗi entity cần callback, cascade, validation hoặc optimistic locking. JDBC có thể vượt trội trong ETL lớn, nhưng đòi hỏi ứng dụng tự chịu trách nhiệm về mapping, version, cache, lỗi và quy tắc nghiệp vụ.

**Tiêu chí lựa chọn là kết hợp tính đúng đắn và bằng chứng đo đạc trên workload thực tế**, không phải cảm giác rằng “ORM chậm” hay “SQL thuần luôn nhanh”.

## 2. Phân biệt ba loại workload trước khi chọn công cụ

Một bài toán có 100.000 bản ghi chưa đủ thông tin để quyết định.

| Workload | Ví dụ | Đặc điểm |
|---|---|---|
| Tạo nhiều entity mới | Nhập 100.000 khách hàng từ tệp | Nguồn dữ liệu ở Java, mỗi hàng có giá trị khác nhau |
| Cập nhật/xóa theo một điều kiện chung | Khóa tài khoản không hoạt động trước ngày X | Database tự xác định tập bản ghi thỏa predicate |
| Biến đổi dữ liệu từ bảng này sang bảng khác | Tạo bảng snapshot từ các order đã thanh toán | Nguồn và đích ở cùng database, có thể xử lý set-based |
| Cập nhật theo lô với dữ liệu từ bên ngoài | Ghi 50.000 giá mới từ API đối tác | Mỗi hàng có key/value khác nhau |
| Thay đổi aggregate có quy tắc domain | Hủy đơn và hoàn tồn kho theo từng đơn | Có invariant, lifecycle, event và nhiều association |

Đối với workload thứ hai và thứ ba, database thường có thể làm việc theo tập hợp mà không gửi từng entity tới Java. Đối với workload thứ nhất và thứ tư, ORM batch hoặc JDBC batch là các ứng viên trực tiếp. Workload thứ năm trước hết cần xác định tính đúng đắn và ranh giới transaction; tối ưu SQL chỉ là bước tiếp theo.

### 2.1. Các câu hỏi phải trả lời

- Dữ liệu đầu vào đã ở trong database hay đang nằm trong bộ nhớ/application?
- Tất cả hàng dùng cùng một công thức cập nhật hay mỗi hàng có giá trị riêng?
- Có cần gọi constructor, setter, domain method, callback, cascade, orphan removal không?
- Có `@Version`, audit, tenant filtering, soft delete hoặc database trigger không?
- Có cần toàn bộ tác vụ nguyên tử hay chấp nhận commit theo chunk?
- Khối lượng và kích thước mỗi hàng là bao nhiêu?
- Mục tiêu là throughput, latency, bộ nhớ, độ ổn định hay giảm lock contention?

Chỉ sau khi xác định các yếu tố này mới so sánh được hiệu năng một cách có ý nghĩa.

## 3. Kiến trúc dữ liệu khác nhau của ba cách

```text
                    YÊU CẦU GHI HÀNG LOẠT
                              |
              +---------------+---------------+
              |               |               |
              v               v               v
           ORM              HQL DML         JDBC
       persist/merge/       update/        PreparedStatement
       dirty checking       delete/         addBatch()
              |             insert-select      |
              v               |               v
      Persistence Context    v           JDBC driver batch
      + entity lifecycle  Hibernate query       |
              |           translation           |
              v               |                 |
      ORM-generated SQL       v                 |
              |          Set-based SQL          |
              v               |                 |
        JDBC batching         |                 |
              +---------------+-----------------+
                              |
                              v
                       Database engine
                              |
                       Index / constraint
                       lock / WAL / redo
```

Lưu ý: ORM batching **cũng dùng JDBC** ở tầng dưới. So sánh “ORM hay JDBC” ở đây là so sánh **việc Hibernate quản lý entity lifecycle** với **việc ứng dụng tự điều khiển SQL/JDBC**, không phải nói ORM không chạy qua JDBC.

## 4. Trước khi đo tốc độ: xác định semantics phải giữ nguyên

Một benchmark chỉ có giá trị khi ba cách cùng giải quyết **một bài toán nghiệp vụ**.

Giả sử entity:

```java
@Entity
@Table(name = "inventory_items")
public class InventoryItem {
    @Id
    private Long id;

    @Column(nullable = false)
    private int available;

    @Version
    private long version;

    protected InventoryItem() {}

    public void reserve(int quantity) {
        if (quantity <= 0 || available < quantity) {
            throw new IllegalArgumentException("Invalid quantity");
        }
        available -= quantity;
    }
}
```

Với ORM:

```java
InventoryItem item = em.find(InventoryItem.class, itemId);
item.reserve(quantity);
// Hibernate dirty checking; có @Version khi flush.
```

Với HQL:

```hql
update InventoryItem i
set i.available = i.available - :quantity,
    i.version = i.version + 1
where i.id = :id
  and i.version = :expectedVersion
  and i.available >= :quantity
```

Với JDBC:

```sql
UPDATE inventory_items
SET available = available - ?,
    version = version + 1
WHERE id = ?
  AND version = ?
  AND available >= ?;
```

Ba ví dụ không tự động tương đương:

- ORM gọi method `reserve()` để validate quantity; HQL/JDBC cần validate `quantity > 0` ở application hoặc constraint.
- ORM quản lý version; HQL/JDBC phải thể hiện version trong query khi cần cùng optimistic-locking semantics.
- ORM có thể gọi lifecycle callback; HQL/JDBC bulk không gọi từng callback.
- Nếu có event/audit/cascade, phải bổ sung cơ chế tương đương cho HQL/JDBC.

**Nếu một phương án nhanh hơn vì bỏ qua nghiệp vụ bắt buộc, đó không phải một chiến thắng hiệu năng hợp lệ.**

## 5. ORM batching là gì?

Với ORM, ứng dụng thao tác các entity Java. Hibernate theo dõi persistence context và tạo SQL khi flush. JDBC batching giúp gom nhiều statement cùng dạng thành các batch gửi tới JDBC driver, giảm số round trips.

```text
persist(entity 1) ─┐
persist(entity 2)  │
persist(entity 3)  ├── Hibernate action queue
...                │          |
persist(entity N) ─┘          v
                       flush / ordering
                              |
                              v
                     JDBC statement batches
                              |
                              v
                            Database
```

ORM batching không biến `N` entity thành một câu SQL `UPDATE ... WHERE ...` có tác động theo tập. Nó thường vẫn tạo INSERT/UPDATE cho từng entity, nhưng nhóm các lệnh JDBC tương tự để truyền/thi hành hiệu quả hơn.

### 5.1. Các cấu hình Hibernate thường dùng

Ví dụ Spring Boot:

```properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
spring.jpa.properties.hibernate.generate_statistics=true
```

Ý nghĩa:

| Cấu hình | Vai trò |
|---|---|
| `hibernate.jdbc.batch_size` | Số JDBC statements mục tiêu trong một batch |
| `hibernate.order_inserts` | Sắp xếp insert theo nhóm để tăng cơ hội batch |
| `hibernate.order_updates` | Sắp xếp update để tăng cơ hội batch, có thể giảm deadlock trong vài workload |
| `hibernate.generate_statistics` | Thu thập thống kê cho chẩn đoán, có overhead nên dùng có kiểm soát |

Giá trị 50 là **điểm khởi đầu để thử nghiệm**, không phải cấu hình tối ưu cho mọi hệ thống. Có thể benchmark các batch size như 10, 25, 50, 100 hoặc cao hơn tùy DBMS, driver, statement size, lock và memory.

Không nhầm `hibernate.jdbc.batch_size` với `@BatchSize` dành cho **fetching**; `@BatchSize` giúp tải nhiều entity/collection lazy, không phải thiết lập số câu INSERT/UPDATE trong JDBC write batch.

### 5.2. Batch chỉ hình thành với SQL đủ tương đồng

Nếu một vòng lặp xen kẽ INSERT vào nhiều bảng hoặc tạo statement có SQL shape khác nhau, việc gom batch có thể bị chia nhỏ. `order_inserts` và `order_updates` thường giúp Hibernate nhóm lệnh theo entity/statement.

Nhưng ordering cũng tạo chi phí sắp xếp và có thể đổi thứ tự DML thực thi. Nếu nghiệp vụ phụ thuộc vào thứ tự hoặc có FK phức tạp, phải kiểm chứng kết quả và lock behavior.

## 6. Mẫu ORM insert với flush/clear theo chunk

Giả sử nhập các bản ghi Customer từ dữ liệu đã kiểm tra:

```java
@Transactional
public void importCustomers(List<CustomerInput> inputs) {
    int batchSize = 50;

    for (int i = 0; i < inputs.size(); i++) {
        CustomerInput input = inputs.get(i);
        Customer customer = new Customer(
                input.externalId(), input.name());
        entityManager.persist(customer);

        if ((i + 1) % batchSize == 0) {
            entityManager.flush();
            entityManager.clear();
        }
    }

    entityManager.flush();
    entityManager.clear();
}
```

Đây là một transaction bao trùm toàn bộ method; `flush()` gửi SQL xuống database nhưng **không commit** transaction. `clear()` detach các managed instances, tránh persistence context tăng mãi.

Lưu ý:

- Chỉ clear khi không cần tiếp tục thao tác managed instances trong chunk.
- Nếu entity có cascade/association đến đối tượng đang được giữ ở nơi khác, clear có thể khiến chúng detached; cần thiết kế graph và batch boundary.
- Nếu import rất lớn, không nên nhận toàn bộ danh sách vào RAM; có thể stream input theo chunk.
- Nếu cần commit từng chunk, tách transaction boundary ở service khác. Không nhầm flush với commit.

### 6.1. Batching update qua managed entity

```java
@Transactional
public void deactivateByIds(List<Long> ids) {
    int chunkSize = 50;
    int changed = 0;

    for (Long id : ids) {
        Customer c = entityManager.find(Customer.class, id);
        if (c == null) {
            continue;
        }
        c.deactivate();
        changed++;

        if (changed % chunkSize == 0) {
            entityManager.flush();
            entityManager.clear();
        }
    }

    entityManager.flush();
    entityManager.clear();
}
```

Mẫu này giữ domain method và lifecycle, nhưng có thể có một SELECT cho mỗi ID trước khi UPDATE. Với tập ID lớn, tìm entity theo từng ID có thể rất tốn thời gian; cần đo chi phí đọc, N+1 từ association và lock.

Nếu nghiệp vụ cho phép, có thể query entity theo chunk `WHERE id IN :ids` để giảm SELECT. Nhưng query có fetch graph phức tạp cũng có thể làm memory tăng hoặc sinh SQL lớn.

## 7. Identifier generator ảnh hưởng mạnh đến ORM batching

Một điểm dễ bỏ sót: cách sinh ID có thể quyết định JDBC insert batching có diễn ra hay không.

### 7.1. IDENTITY

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

Với IDENTITY, Hibernate thường phải thực thi INSERT sớm để database trả generated ID. Điều này hạn chế hoặc làm Hibernate không batch được INSERT theo cơ chế ORM thông thường cho entity đó. Không giả định đặt `hibernate.jdbc.batch_size=50` sẽ tự khiến mọi IDENTITY INSERT thành batch.

### 7.2. SEQUENCE có pooling

```java
@Id
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "customer_seq")
@SequenceGenerator(
    name = "customer_seq",
    sequenceName = "customer_seq",
    allocationSize = 50)
private Long id;
```

Generator sequence có pooled allocation phù hợp có thể giảm số lần lấy ID và cho phép Hibernate gom INSERT tốt hơn. Nhưng cần đồng bộ sequence configuration, allocation size, migration và chiến lược optimizer với DBMS.

### 7.3. Assigned ID

Nếu key được tạo ở application theo quy tắc an toàn (ví dụ UUID), Hibernate không nhất thiết phải thực thi INSERT để lấy ID. Tuy nhiên, mapping/version/driver/dialect vẫn ảnh hưởng hiệu quả batching.

Đừng đổi ID strategy chỉ để benchmark nhanh hơn mà bỏ qua yêu cầu tương thích schema, dữ liệu hiện tại và uniqueness.

## 8. ORM và optimistic locking khi batch UPDATE

Hibernate thường dùng cột `@Version` để phát hiện optimistic conflict. Ví dụ SQL sinh ra có dạng:

```sql
UPDATE inventory_items
SET available = ?, version = ?
WHERE id = ?
  AND version = ?;
```

Trong một JDBC batch, driver có thể trả update count cho từng statement hoặc giá trị tổng quát `SUCCESS_NO_INFO`. Hibernate có cơ chế kiểm tra số hàng bị ảnh hưởng để phát hiện stale update, nhưng behavior phụ thuộc driver, Hibernate version và configuration.

Một số phiên bản Hibernate có setting liên quan batch versioned data. **Không copy setting từ tutorial cũ mà không kiểm tra phiên bản Hibernate đang chạy**: tên setting, mặc định và cách kiểm tra row count đã thay đổi theo lịch sử release.

Nếu cần optimistic locking, benchmark phải giữ điều kiện version và kiểm tra race thực tế; không bỏ version predicate chỉ để JDBC batch thắng ORM.

## 9. HQL bulk mutation là gì?

HQL bulk DML trực tiếp yêu cầu database tìm và sửa tập hàng theo predicate:

```hql
update Customer c
set c.active = false
where c.lastLoginAt < :cutoff
  and c.active = true
```

Thực thi trên Hibernate 6:

```java
@Transactional
public int deactivateInactiveCustomers(Instant cutoff) {
    entityManager.flush();

    int affected = entityManager.unwrap(Session.class)
        .createMutationQuery("""
            update Customer c
            set c.active = false
            where c.lastLoginAt < :cutoff
              and c.active = true
            """)
        .setParameter("cutoff", cutoff)
        .executeUpdate();

    entityManager.clear();
    return affected;
}
```

Đây là một câu HQL được Hibernate dịch thành SQL phù hợp. Nếu entity dùng inheritance hoặc secondary tables, Hibernate có thể sinh nhiều câu SQL hoặc mutation strategy khác nhau; không mặc định một HQL tương đương một SQL statement trong mọi mapping.

Với hàng trăm nghìn bản ghi thỏa cùng predicate, bulk HQL thường giảm mạnh số round trips và không cần hydrate từng entity. Tuy nhiên, nó cũng **bỏ qua vòng đời từng entity**.

## 10. HQL DELETE và INSERT ... SELECT

### 10.1. Bulk delete

```hql
delete from TemporaryToken t
where t.expiresAt < :now
```

```java
int deleted = session.createMutationQuery("""
    delete from TemporaryToken t
    where t.expiresAt < :now
    """)
    .setParameter("now", now)
    .executeUpdate();
```

Không có lệnh gọi `remove()` cho từng token. Nếu deletion cần JPA cascade, `@PreRemove`, orphan removal hoặc domain event theo từng entity, cách làm này có thể không phù hợp.

### 10.2. Insert-select

Khi nguồn và đích ở cùng database:

```hql
insert into OrderArchive (id, orderNumber, total)
select o.id, o.orderNumber, o.total
from Order o
where o.completedAt < :cutoff
```

Insert-select có thể tránh truyền hàng trăm nghìn row từ DB sang Java rồi quay lại DB. Đây là HQL extension, không phải JPQL INSERT portable.

Identifier strategy, type compatibility, non-polymorphic insert và mapping các thuộc tính đích cần được kiểm tra. Query không tự thực hiện cascade persist của toàn bộ object graph.

## 11. HQL bulk không đồng nghĩa ORM lifecycle

So sánh:

| Yêu cầu | ORM entity-by-entity | HQL bulk mutation |
|---|---|---|
| Dirty checking | Có | Không |
| Domain methods | Có nếu code gọi | Không |
| `@PreUpdate`/`@PreRemove` per entity | Theo lifecycle | Không gọi cho từng entity |
| Bean Validation per entity | Theo cấu hình | Không chạy cho từng entity |
| Cascade JPA, orphan removal | Theo mapping | Không thực hiện như object graph |
| Optimistic locking qua `@Version` | Theo dirty checking | Không tự áp dụng mặc định như managed entity |
| Hibernate persistence context | Managed state được theo dõi | Managed state có thể stale |
| Database constraints/triggers | Vẫn chạy | Vẫn chạy |
| Data volume qua JVM | Có thể lớn | Thường nhỏ khi predicate ở DB |

**Bằng chứng hiệu năng phải luôn đi kèm danh sách chức năng nghiệp vụ được bảo toàn.**

### 11.1. Versioning với HQL bulk

Ví dụ bulk update mặc định:

```hql
update Product p
set p.price = p.price * :factor
where p.category.id = :categoryId
```

Không nên giả định cột `@Version` tự tăng như managed update. Hibernate có extension:

```hql
update versioned Product p
set p.price = p.price * :factor
where p.category.id = :categoryId
```

hoặc dùng version predicate/tăng version tường minh theo mapping nếu cần compare-and-set. `update versioned` là HQL-specific, có giới hạn đối với một số custom version types; phải kiểm thử trên phiên bản thực tế.

## 12. Persistence context và cache sau HQL/JDBC mutation

Ví dụ:

```java
Product p = em.find(Product.class, 42L);

em.createQuery("""
    update Product p2
    set p2.active = false
    where p2.id = :id
    """)
    .setParameter("id", 42L)
    .executeUpdate();

// p có thể vẫn chứa active=true.
```

Bulk HQL và native JDBC mutate database, không sửa trực tiếp mọi managed object đang tồn tại. Nếu sau đó code dùng state cũ, có thể ra quyết định nghiệp vụ sai hoặc ghi đè state mới ở lần flush sau.

Quy trình phổ biến:

1. `flush()` các thay đổi pending trước bulk mutation khi cần.
2. Chạy mutation trong transaction.
3. `clear()` persistence context nếu ảnh hưởng rộng, hoặc `refresh()` những entity cần dùng tiếp.
4. Kiểm tra second-level/query cache synchronization nếu dùng native JDBC hoặc truy vấn ngoài Hibernate.

`clear()` detach **tất cả** managed entities, không riêng entity bị cập nhật. Nó có thể bỏ mất các thay đổi chưa flush; không dùng tùy tiện giữa một transaction chứa nhiều thao tác domain.

Với native SQL thông qua Hibernate, có thể khai báo synchronized entity/query spaces phù hợp; với JDBC thuần qua connection của Hibernate, ứng dụng phải chủ động xem xét cache invalidation và persistence context state.

## 13. JDBC batching trực tiếp

Khi mỗi hàng có một giá trị khác nhau từ nguồn ngoài, JDBC batch là một lựa chọn mạnh. Ví dụ:

```java
record PriceChange(long productId, BigDecimal newPrice) {}
```

Với một Hibernate Session trong transaction được quản lý:

```java
@Transactional
public void updatePrices(List<PriceChange> changes) {
    Session session = entityManager.unwrap(Session.class);
    session.flush();

    session.doWork(connection -> {
        String sql = """
            UPDATE products
            SET price = ?
            WHERE id = ?
            """;

        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            int pending = 0;

            for (PriceChange change : changes) {
                ps.setBigDecimal(1, change.newPrice());
                ps.setLong(2, change.productId());
                ps.addBatch();

                if (++pending == 100) {
                    ps.executeBatch();
                    ps.clearBatch();
                    pending = 0;
                }
            }

            if (pending > 0) {
                ps.executeBatch();
                ps.clearBatch();
            }
        }
    });

    session.clear();
}
```

Ở đây Hibernate cung cấp JDBC connection qua `Session.doWork()`, nhưng SQL, binding và batching do ứng dụng tự kiểm soát. Transaction do Spring quản lý; **không tự gọi `connection.commit()` hoặc thay đổi `autoCommit` bên trong `doWork()`** vì sẽ phá transaction boundary của container.

Ví dụ giả định dữ liệu đã được validate, có uniqueness của product ID và tác vụ không cần JPA lifecycle callback. Nếu cần version/audit, câu SQL này chưa đủ: phải bổ sung predicate/update tương ứng.

### 13.1. JDBC batch khác set-based UPDATE

JDBC batch:

```text
UPDATE products SET price = 10 WHERE id = 1
UPDATE products SET price = 20 WHERE id = 2
UPDATE products SET price = 30 WHERE id = 3
...
```

Các statement cùng shape được gom vào batch. Hệ quản trị vẫn xử lý nhiều điều kiện/giá trị riêng, dù driver có thể tối ưu giao thức hoặc rewrite theo khả năng.

HQL set-based UPDATE:

```hql
update Product p
set p.active = false
where p.discontinued = true
```

Một predicate chọn toàn bộ tập đích; không phải JDBC batch của N statement riêng. Vì vậy, việc so sánh hai cách phải kiểm tra liệu chúng có cùng input/semantics hay không.

## 14. JDBC batch và kết quả executeBatch()

JDBC `executeBatch()` trả một mảng update counts:

```java
int[] counts = ps.executeBatch();
```

Theo JDBC, phần tử có thể là:

- Số không âm: row count cho command tương ứng.
- `Statement.SUCCESS_NO_INFO` (−2): command thành công nhưng driver không cung cấp số row cụ thể.
- `Statement.EXECUTE_FAILED` (−3): command thất bại nếu driver tiếp tục thực thi batch sau lỗi.

Trong trường hợp lỗi, driver có thể ném `BatchUpdateException`; `getUpdateCounts()` cho biết phần kết quả đã thực thi theo behavior của driver. Không giả định batch luôn atomic nếu chạy ngoài transaction. Trong transaction, khi gặp lỗi cần rollback cả unit of work theo policy.

### 14.1. Không dựa trên affected count khi driver trả SUCCESS_NO_INFO

Với logic compare-and-set, ứng dụng có thể cần phân biệt “update đúng một row” và “không match vì version conflict”. Nếu driver báo `SUCCESS_NO_INFO` cho các statements, bạn không thể xác nhận kết quả từng row bằng mảng count.

Khi business semantics yêu cầu kết quả từng item:

- Xem driver có hỗ trợ per-statement accurate counts với batch không.
- Dùng câu UPDATE riêng hoặc API trả kết quả rõ ràng cho những operation cần kiểm tra.
- Dùng staging table + set-based UPDATE + bảng kết quả để đối chiếu các ID thành công/thất bại nếu workload lớn.
- Không coi `SUCCESS_NO_INFO` là chính xác một row bị update.

### 14.2. Partial failure

Nếu batch có 100 câu SQL và câu thứ 37 lỗi:

- Driver có thể dừng batch hoặc tiếp tục tùy DBMS/driver.
- Một số command có thể đã thực thi trước lỗi.
- Transaction vẫn quyết định commit/rollback tổng thể.
- Nếu tách commit theo chunk, các chunk trước có thể đã commit.

Đối với import có retry, cần xác định deduplication key, unique constraint và idempotency. Thử chạy lại toàn bộ batch mà không có chiến lược chống trùng có thể tạo dữ liệu lặp.

## 15. JDBC trực tiếp và optimistic locking

ORM update có `@Version` thường tạo câu SQL có version predicate. Nếu chuyển sang JDBC, ứng dụng phải thể hiện semantics ấy:

```sql
UPDATE products
SET price = ?,
    version = version + 1
WHERE id = ?
  AND version = ?;
```

Java:

```java
record VersionedPriceChange(
    long productId,
    long expectedVersion,
    BigDecimal newPrice) {}
```

Khi affected row count bằng 0, có thể là ID không tồn tại hoặc version không còn phù hợp. Nếu chỉ có một product change, câu update đơn giản dễ xử lý. Với hàng chục nghìn rows, một phương án phải cân đối giữa batching throughput và khả năng báo lỗi từng bản ghi.

**Không bỏ version check để JDBC batch trông nhanh hơn ORM batch** nếu optimistic locking là invariant bắt buộc của hệ thống.

## 16. JDBC không chỉ có executeBatch()

Trong ETL hoặc import rất lớn, database có thể cung cấp:

- Bulk load protocol/command như PostgreSQL `COPY`.
- SQL Server bulk copy hoặc table-valued parameters.
- Database-specific array binding.
- Temporary/staging table, sau đó UPDATE/INSERT theo tập.
- Upsert/MERGE khi DBMS và version hỗ trợ semantics phù hợp.

Những kỹ thuật này có thể vượt cả ORM batching lẫn `PreparedStatement.executeBatch()` truyền thống. Nhưng chúng giảm portability và có thể thay đổi transaction, error reporting, lock và constraint behavior.

Ví dụ luồng dữ liệu:

```text
CSV / partner data
      |
      v
Validate / normalize rows
      |
      v
COPY / bulk load into staging table
      |
      v
SQL validate duplicates + constraints
      |
      v
Set-based UPDATE / INSERT into target
      |
      v
Publish audit summary + commit
```

Với các tập dữ liệu rất lớn, staging strategy có thể tốt hơn gửi hàng nghìn individual updates qua JDBC. Cần benchmark trên DBMS thật thay vì coi một trong ba lựa chọn gốc là giới hạn cuối cùng.

## 17. So sánh nhanh các công cụ

| Tiêu chí | ORM + JDBC batching | HQL mutation | JDBC direct/batch |
|---|---|---|---|
| Nguồn dữ liệu | Java entities | Thường ở DB qua predicate | Java/external, SQL rõ |
| Đơn vị thao tác | Entity lifecycle | Tập entity theo query | Statement/row hoặc DB-specific bulk |
| Callback và cascade | Có theo mapping | Không per entity | Không per entity |
| Dirty checking | Có | Không | Không |
| Optimistic locking | ORM quản lý | Cần thiết kế rõ | Cần viết SQL rõ |
| Persistence context | Tích hợp tự nhiên | Có thể stale sau mutation | Có thể stale nếu trộn ORM |
| Query portability | Thường tốt qua Dialect | HQL tương đối tốt, extension tùy version | Phụ thuộc SQL/DBMS |
| Round trips | Giảm nhờ batching | Rất thấp cho set-based operation | Giảm nhờ batching/driver |
| Memory | Phải kiểm soát PC | Thường thấp | Thường thấp nếu stream input |
| Mapping nhiều bảng | Hibernate xử lý lifecycle | Có thể cần multi-table strategy | Ứng dụng tự xử lý |
| Dễ kiểm soát SQL shape | Vừa phải | Khá rõ ở HQL | Cao nhất |
| Bảo trì business rules | Thuận lợi | Cần thể hiện ở query/DB | Tự chịu trách nhiệm nhiều hơn |

Không có cột “nhanh nhất” cố định vì kết quả phụ thuộc workload.

## 18. Một mô hình chi phí để hình dung

Giả sử cần xử lý `N` rows, có `B` statements trong một batch. Một mô hình rất thô:

```text
ORM entity loop:
  tổng thời gian ≈ đọc entity
                 + tạo/quản lý object
                 + dirty checking/flush
                 + gửi các JDBC batches
                 + chi phí thực thi SQL/lock/index

HQL set-based:
  tổng thời gian ≈ chuẩn bị query
                 + scan/seek tập rows theo predicate
                 + chi phí cập nhật SQL/lock/index

JDBC batch:
  tổng thời gian ≈ chuẩn bị bind params
                 + gửi ~ceil(N/B) batches
                 + chi phí thực thi N DML operations
                 + index/lock/log
```

Mô hình này **không phải công thức dự đoán latency chính xác**. Driver có thể rewrite batch, network khác nhau và DBMS optimizer có thể biến đổi SQL. Nó chỉ cho thấy những thành phần chi phí cần đo.

Điểm thường gặp:

- ORM bị chi phối bởi SELECT/managed memory khi phải tải entity trước khi update.
- HQL set-based bị chi phối bởi scan, index update, row locks và transaction log khi thay đổi rất nhiều rows.
- JDBC batch bị chi phối bởi bind, round trips và DBMS processing từng statement.
- Với transaction dài, lock contention và log flush có thể lớn hơn toàn bộ thời gian Java.

## 19. Bằng chứng hiệu năng cần đo là gì?

Đừng chỉ dùng một con số “mất bao nhiêu giây”. Các chỉ số hữu ích:

| Chỉ số | Ý nghĩa |
|---|---|
| Tổng thời gian hoàn thành | End-to-end duration của workload |
| Throughput (rows/s) | Số hàng hoàn tất mỗi giây |
| p50/p95/p99 latency | Độ trễ thao tác hoặc chunk, quan trọng trong hệ thống online |
| Số JDBC round trips | Chi phí network/driver |
| Số SQL statements/batches | Xác nhận batching thực sự xảy ra |
| Heap peak/GC pause | Chi phí managed entities và mapping |
| CPU application | Chi phí Java mapping/validation |
| CPU database | Chi phí SQL execution/optimizer |
| Lock wait/deadlock | Ảnh hưởng lên transaction khác |
| WAL/redo/binlog volume | Write amplification, replication |
| Rows scanned/modified | Hiệu quả index/predicate |
| Error/retry rate | Độ ổn định dưới tải |
| Constraint/audit correctness | Có giữ đủ semantics nghiệp vụ không? |

Một lựa chọn throughput cao hơn nhưng giữ row lock quá lâu có thể gây p95 latency xấu cho các request khác. Khi tối ưu batch job, hãy xem cả **tác động tới hệ thống chung**.

## 20. Điều kiện để benchmark công bằng

Thử nghiệm cần giữ giống nhau:

1. Cùng DBMS, major version, JDBC driver và Hibernate version.
2. Cùng schema, indexes, constraints, triggers và data distribution.
3. Cùng tập input và số hàng thực sự bị ảnh hưởng.
4. Cùng transaction semantics: một transaction hay commit theo chunk.
5. Cùng yêu cầu về version, validation, audit, tenant và cascade.
6. Cùng pool/network topology (local vs remote có thể thay thứ tự chiến thắng).
7. Cùng cách tính thời gian: từ trước khi đọc input tới sau commit, hoặc tách rõ giai đoạn.
8. Cùng warm-up, database cache conditions và môi trường tải đồng thời.

Nếu ORM chạy qua mạng đến DB nhưng JDBC chạy trên cùng máy DB, kết quả không chứng minh bản chất ORM kém hơn. Nếu HQL bỏ toàn bộ event/audit trong khi ORM ghi đầy đủ, kết quả cũng không thể so sánh trực tiếp.

### 20.1. Benchmark dữ liệu nhỏ thường đánh lừa

Một thử nghiệm 100 rows có thể bị chi phối bởi startup, class loading, JIT warm-up, connection acquisition hoặc logging. Với hàng triệu rows, index maintenance và transaction log lại có thể chiếm ưu thế.

Do đó nên thử nhiều kích thước:

- Tập nhỏ đại diện một API request.
- Tập trung bình như một chunk import.
- Tập lớn giống batch job production.
- Tập có skew/duplicates/null/constraints như dữ liệu thật.

Đo lại sau khi đổi batch size, generator, index hoặc driver settings.

## 21. Thiết kế một thí nghiệm có thể lặp lại

Giả sử cần cập nhật trạng thái của một tập Product.

**Bước 1 — Định nghĩa cùng kết quả:** chỉ Product bị ngừng kinh doanh được đặt `active=false`; version/audit phải có policy thống nhất.

**Bước 2 — Chuẩn bị fixture:** tạo một bảng với hàng đủ lớn, các index/constraints thực tế, phân bố `discontinued` giống workload.

**Bước 3 — Reset dữ liệu:** trước mỗi lần chạy, đưa database về trạng thái tương đương; tránh để lần chạy sau tác động ít rows hơn lần trước.

**Bước 4 — Warm-up:** chạy thử đủ lần để JVM/JIT, connection pool và cache ổn định; không dùng kết quả warm-up làm số chính.

**Bước 5 — Chạy nhiều lần:** thay đổi thứ tự các phương án để giảm thiên lệch do cache và load. Ghi phân bố kết quả, không chọn duy nhất lần nhanh nhất.

**Bước 6 — Thu metrics:** rows/s, total elapsed, SQL statement count, round trips, app CPU/heap, DB CPU/IO, lock waits, error count.

**Bước 7 — So sánh semantics:** validate sau mỗi lần rằng số hàng và dữ liệu đúng, version/callback/audit theo yêu cầu.

**Bước 8 — Lưu môi trường:** DBMS, schema migration, Hibernate/JDBC version, batch size, dataset size, commit policy.

### 21.1. Bảng ghi nhận kết quả (mẫu, không có số giả)

| Phương án | Rows | Total elapsed | Rows/s | SQL/batches | Heap peak | Lock wait | Đúng semantics? |
|---|---:|---:|---:|---|---|---|---|
| ORM + batch size 25 | Đo | Đo | Đo | Đo | Đo | Đo | Kiểm chứng |
| ORM + batch size 50 | Đo | Đo | Đo | Đo | Đo | Đo | Kiểm chứng |
| HQL update | Đo | Đo | Đo | Đo | Đo | Đo | Kiểm chứng |
| JDBC batch size 100 | Đo | Đo | Đo | Đo | Đo | Đo | Kiểm chứng |

Không điền các số “minh họa” rồi dùng chúng làm kết luận kỹ thuật. Quyết định phải dựa trên số đo của chính ứng dụng.

## 22. Đo đúng ranh giới thời gian

Ví dụ benchmark:

```java
long start = System.nanoTime();

int affected = performBatchOperation();

long elapsedNanos = System.nanoTime() - start;
double seconds = elapsedNanos / 1_000_000_000.0;
double rowsPerSecond = affected / seconds;
```

Đoạn này chỉ là một phép đo sơ bộ. Nếu `performBatchOperation()` trả trước commit, kết quả bỏ sót chi phí commit/log flush. Nếu input được tạo trước timer nhưng phương án khác phải đọc input trong timer, phép so sánh không công bằng.

Cần quyết định rõ:

- Thời gian **end-to-end:** input acquisition đến commit.
- Thời gian **database write:** bắt đầu gửi SQL đến commit.
- Thời gian **per chunk:** giúp tìm outliers và p95.

Với benchmark nghiêm túc, tách phần chuẩn bị dataset và đo nhiều lần bằng tooling/metrics nhất quán. JMH phù hợp microbenchmark Java, nhưng JDBC/database performance chịu ảnh hưởng I/O, concurrency, DB state và không thể suy ra chỉ từ một microbenchmark method.

## 23. Bật Hibernate statistics để xác nhận batching

Hibernate statistics có thể hỗ trợ quan sát session/query/JDBC activity nếu bật:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
```

Trong Java:

```java
Statistics statistics = sessionFactory.getStatistics();
statistics.clear();

// Thực thi workload benchmark.

long entityInsertCount = statistics.getEntityInsertCount();
long entityUpdateCount = statistics.getEntityUpdateCount();
long entityDeleteCount = statistics.getEntityDeleteCount();
```

Những chỉ số entity count hữu ích cho ORM lifecycle; bulk HQL/JDBC có thể không làm tăng các counter entity theo cùng semantics. Do đó không lấy `entityUpdateCount` làm số rows bị ảnh hưởng của HQL bulk.

Để xác nhận JDBC batch thực sự diễn ra, kết hợp SQL/driver logs, session metrics, JDBC instrumentation hoặc proxy datasource trên môi trường test. Một số metric của Hibernate thay đổi theo version; hãy kiểm tra API thống kê thực tế của phiên bản dự án.

### 23.1. Không dùng số dòng log làm số round trips

Một logger có thể hiển thị SQL một lần cho mỗi bind hoặc một statement template, trong khi JDBC driver thực hiện batch. Vì vậy:

- Phân biệt SQL statement count và JDBC executeBatch calls.
- Kiểm tra driver rewrite behavior khi có.
- Đo network round trips hoặc database metrics nếu mục tiêu là giảm round trips.
- Tránh bật bind-parameter logs khối lượng lớn trong benchmark vì bản thân logging gây overhead đáng kể.

## 24. DB metrics quyết định kết quả cuối cùng

Khi insert/update nhiều rows, DBMS phải duy trì index, FK, triggers, WAL/redo/binlog và locks. Sau một ngưỡng, cải thiện Java/JDBC có thể không tăng throughput nhiều.

Ví dụ:

```text
Application CPU:  15%
Database CPU:     90%
Disk/WAL:         gần bão hòa
Lock wait:        tăng
```

Trong tình huống này, tăng batch size từ 50 lên 500 chưa chắc cải thiện. Nó có thể giữ lock lâu hơn, tăng transaction log và làm các request online chậm.

Tương tự, nếu database rất nhàn nhưng app tạo hàng triệu managed objects và GC thường xuyên, việc chuyển sang HQL set-based/JDBC streaming có thể đem lại lợi ích lớn.

**Tối ưu đúng điểm nghẽn được đo**, không tối ưu theo định kiến về tầng công nghệ.

## 25. Transaction size và chunking

Một batch size 50 không đồng nghĩa mỗi batch là một transaction.

```text
Transaction
   |
   +-- batch 1 (50 statements)
   +-- batch 2 (50 statements)
   +-- batch 3 (50 statements)
   +-- ...
   |
 COMMIT một lần
```

Nếu yêu cầu toàn bộ import nguyên tử, một transaction lớn có thể cần thiết nhưng sẽ giữ tài nguyên và locks lâu. Nếu chấp nhận partial progress, có thể chia nhiều transaction:

```text
Chunk 1 -> transaction -> commit
Chunk 2 -> transaction -> commit
Chunk 3 -> transaction -> commit
...
```

Chia chunk làm thay đổi semantics:

- Nếu chunk 3 lỗi, chunk 1 và 2 đã commit.
- Retry phải idempotent.
- Có thể cần checkpoint/progress marker.
- Dữ liệu nguồn có thể đổi giữa các chunk.
- Nếu cập nhật dựa trên predicate, row mới có thể xuất hiện và row cũ có thể không còn khớp.

Do đó, quyết định transaction/chunking phải có trước khi so sánh thời gian; không benchmark một phương án atomic với phương án khác commit từng chunk rồi tuyên bố thứ hai nhanh hơn mà không đề cập sự khác biệt.

## 26. Ví dụ Spring: transaction riêng cho từng chunk

Một mô hình rõ ràng là service điều phối gọi một service khác có transaction:

```java
@Service
public class ImportCoordinator {
    private final ImportChunkService chunks;

    public ImportCoordinator(ImportChunkService chunks) {
        this.chunks = chunks;
    }

    public void runImport(Iterator<CustomerInput> source) {
        while (source.hasNext()) {
            List<CustomerInput> chunk = nextChunk(source, 500);
            chunks.saveChunk(chunk);
        }
    }
}

@Service
public class ImportChunkService {
    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void saveChunk(List<CustomerInput> inputs) {
        for (CustomerInput input : inputs) {
            em.persist(new Customer(
                input.externalId(), input.name()));
        }
        em.flush();
        em.clear();
    }
}
```

Ví dụ giả định có helper `nextChunk()`. Việc gọi service khác qua Spring proxy giúp transaction advice hoạt động; tự gọi một method `@Transactional` khác trong cùng object có thể không đi qua proxy, dẫn tới ranh giới transaction không như mong đợi.

Nếu cần toàn tác vụ atomic, không dùng mô hình commit theo chunk này. Nếu chấp nhận partial progress, hãy có retry/idempotency và cách báo lỗi từng chunk.

## 27. Phát sinh deadlock và tranh chấp khóa

Một bulk UPDATE tác động nhiều rows có thể giữ lock lâu; một vòng JDBC batch cập nhật các ID khác thứ tự giữa hai transaction cũng có thể tạo deadlock.

Ví dụ:

```text
Transaction A                Transaction B
-------------                -------------
UPDATE row 10                UPDATE row 20
UPDATE row 20 (wait)         UPDATE row 10 (wait)
           \                  /
            \--- deadlock ---/
```

Các biện pháp:

- Nếu có thể, cập nhật các ID theo thứ tự thống nhất.
- Giữ transaction đủ ngắn phù hợp yêu cầu atomicity.
- Dùng index tốt để giảm scan/lock ngoài ý muốn.
- Thiết kế retry cho deadlock/serialization failures với giới hạn và backoff.
- Không giữ transaction mở trong lúc gọi network/API ngoài.

`hibernate.order_updates` có thể giúp Hibernate sắp xếp update để tăng batch và đôi khi giảm deadlock, nhưng không bảo đảm không còn deadlock. Với HQL set-based, thứ tự khóa do DBMS execution plan quyết định; cần quan sát trên DB thật.

## 28. Khi nào ORM batching là lựa chọn tốt?

Chọn ORM khi:

- Mỗi entity có invariant được biểu diễn bằng domain method.
- Cần entity callbacks, validation, audit hoặc cascade ORM.
- Có nhiều association phải duy trì trong object graph.
- Dùng `@Version` và cần optimistic locking do ORM quản lý.
- Khối lượng không quá lớn hoặc đã được chia chunk hợp lý.
- Khác biệt tốc độ đo được không đáng để đánh đổi khả năng bảo trì.

Ví dụ import đơn hàng có lines, tính total và kiểm tra discount:

```java
Order order = Order.create(customer, items);
order.applyPromotion(promotion);
entityManager.persist(order);
```

Nếu aggregate có quy tắc phức tạp, vòng đời entity có thể là lựa chọn đúng dù statement count lớn hơn. Cần tối ưu query fetch plan, JDBC batching, ID generator và chunk size trước khi bỏ ORM.

## 29. Khi nào HQL mutation là lựa chọn tốt?

Chọn HQL bulk khi:

- Mọi rows thỏa cùng predicate và dùng cùng công thức cập nhật.
- Không cần callbacks/cascade/domain method từng entity.
- Dữ liệu để chọn rows đã ở database.
- Cần giữ mapping entity tốt hơn native SQL.
- Có thể xử lý version/cache/PC staleness tường minh.

Ví dụ:

```hql
update versioned Subscription s
set s.status = :expired
where s.status = :active
  and s.validUntil < :now
```

Nếu `@Version` dùng kiểu được hỗ trợ, `update versioned` thể hiện yêu cầu tăng version. Nếu cần event cho mỗi Subscription, hệ thống phải thiết kế cơ chế khác; câu HQL không tự publish event.

HQL mutation cũng hữu ích với `delete` bản ghi tạm hết hạn hoặc `insert ... select` để tạo snapshot cùng DB. Không dùng nó như cách “tự động thay thế mọi `entityManager.remove()`”.

## 30. Khi nào JDBC batch là lựa chọn tốt?

Chọn JDBC khi:

- Nguồn dữ liệu từ bên ngoài chứa giá trị riêng cho từng row.
- SQL shape ổn định, quy tắc domain đơn giản.
- ORM đang tạo overhead đo được về heap, GC, SELECT hoặc JDBC batching không hiệu quả.
- Cần API driver như `executeBatch()` hoặc bulk load.
- Có khả năng chủ động quản lý transaction, version, audit, cache và error reporting.

Ví dụ nhập giá từ đối tác có thể dùng JDBC batch sau khi validate record. Nếu cần PostgreSQL COPY để nạp 10 triệu rows, đó là một phương án đặc thù DBMS cần benchmark cùng staging strategy.

Nếu yêu cầu transaction có side effects Java theo từng entity, việc dùng JDBC trực tiếp có thể tạo thêm nợ kỹ thuật nghiêm trọng dù throughput cao.

## 31. Không nhầm Hibernate StatelessSession với Session thường

Hibernate có `StatelessSession` dành cho một số workload xử lý nhiều bản ghi mà không cần persistence context/dirty checking giống Session thông thường. Nó có semantics khác entity lifecycle tiêu chuẩn và API có thể thay đổi theo Hibernate version.

`StatelessSession` có thể là phương án trung gian đáng khảo sát khi:

- Cần map dữ liệu qua Hibernate entity metadata.
- Không muốn duy trì first-level cache lớn.
- Chấp nhận semantics lifecycle khác Session.

Tuy nhiên, nó **không tự động tương đương** ORM Session thường về cascades, dirty checking hoặc event. Nếu đưa vào benchmark, hãy coi đó là phương án thứ tư với semantics riêng và đọc hướng dẫn của Hibernate version cụ thể.

## 32. N+1, SELECT trước UPDATE và cấu hình fetch

Một lỗi benchmark phổ biến là ORM cần tải từng entity:

```java
for (Long id : ids) {
    Product p = em.find(Product.class, id);
    p.changePrice(...);
}
```

Nếu cần dữ liệu đầy đủ để validate, SELECT là công việc có thật. Nhưng nếu chỉ cần update cùng một cờ, tải từng Product là overhead không cần thiết và HQL có lợi thế rõ.

Nếu ORM còn truy cập lazy association trong domain method:

```java
order.cancel();
// cancel() có thể duyệt lines/payments để xử lý nghiệp vụ.
```

N+1 queries có thể chiếm phần lớn thời gian. Cần dùng fetch plan, batch fetching hoặc query theo chunk để giảm chi phí đọc trước khi đánh giá write batching.

Đừng đánh đồng `@BatchSize` của lazy fetching với JDBC write batch size; hai tối ưu phục vụ các giai đoạn khác nhau.

## 33. Xem lại schema và index trước khi đổi API

Một câu HQL UPDATE chậm có thể do predicate không có index:

```hql
update Customer c
set c.active = false
where c.lastLoginAt < :cutoff
  and c.active = true
```

SQL tương ứng có thể scan toàn bộ bảng. Nếu hàng trăm triệu Customer nhưng chỉ một phần nhỏ thỏa điều kiện, một index phù hợp có thể quan trọng hơn việc đổi HQL sang JDBC.

Ngược lại, nếu query cập nhật phần lớn bảng, index maintenance đôi khi làm workload nặng hơn; index không luôn là “càng nhiều càng tốt”.

Khi phân tích DBMS:

- Dùng EXPLAIN/execution plan cho SELECT predicate tương đương và mutation khi có công cụ an toàn.
- Quan sát rows scanned vs rows modified.
- Xem lock waits, index page splits, WAL/redo volume.
- Kiểm tra trigger/FK và cascading tại DB.
- Theo dõi replication lag.

Với `EXPLAIN ANALYZE` trên mutation, nhớ nhiều DBMS thực thi câu lệnh để đo; chỉ chạy trong môi trường/transaction có kiểm soát.

## 34. Benchmark với dữ liệu thực tế, không chỉ rows cùng kích thước

Workload production có thể có:

- Dữ liệu phân bố lệch: vài tenant rất lớn, nhiều tenant nhỏ.
- Row có nhiều association/collection.
- Cột text/JSON lớn hoặc LOB.
- Constraint và trigger khác nhau theo bảng.
- Nhiều duplicate/existing keys trong import.
- Contention với giao dịch online.

Benchmark chỉ có 10.000 rows giống hệt nhau thường không phản ánh hotspot, lock và cache miss thật.

Nên thu thập dữ liệu đại diện đã được ẩn danh/giả lập đúng phân bố. Không mang dữ liệu cá nhân production vào môi trường test không được phép.

## 35. Tác động của batch size lên memory và driver

Tăng batch size thường giảm số lần `executeBatch()`, nhưng có giới hạn:

```text
Batch size nhỏ:
  + ít statement/parameters giữ trong bộ nhớ
  - nhiều lần executeBatch và round trip

Batch size lớn:
  + có thể giảm round trips
  - driver buffer lớn hơn
  - statement/packet/parameter limits
  - transaction và lock có thể giữ lâu
```

Không nên chọn batch size tối đa theo cảm tính. Một DBMS/driver có thể rewrite multi-row INSERT nhưng không rewrite UPDATE cùng cách. Một driver có thể hỗ trợ pipeline tốt trong khi driver khác gặp giới hạn parameter hoặc packet size.

Cần benchmark batch size trong điều kiện có latency network thật. Benchmark trên cùng máy có thể đánh giá thấp lợi ích giảm round trips.

## 36. An toàn SQL và dữ liệu khi dùng JDBC/HQL

HQL mutation:

```java
session.createMutationQuery("""
    update Product p set p.price = :price
    where p.id = :id
    """)
    .setParameter("price", price)
    .setParameter("id", id)
    .executeUpdate();
```

JDBC:

```java
PreparedStatement ps = connection.prepareStatement(
    "UPDATE products SET price = ? WHERE id = ?");
ps.setBigDecimal(1, price);
ps.setLong(2, id);
```

Cả hai đều bind giá trị an toàn. Không nối input raw thành SQL/HQL.

Nếu cần dynamic table/column/ORDER BY trong JDBC, phải dùng whitelist identifier/fragment cố định ở phía server; placeholder không thể đại diện cho tên bảng hoặc tên cột. Với multi-tenancy, tenant condition phải xuất phát từ trusted context hoặc cơ chế database row-level security đã kiểm chứng.

Bảo mật không phải một lựa chọn độc lập với hiệu năng; một benchmark bỏ tenant filter để nhanh hơn là không đo cùng nghiệp vụ.

## 37. Các kịch bản chọn công cụ

### 37.1. Đánh dấu tất cả token hết hạn

```hql
delete from AccessToken t
where t.expiresAt < :now
```

Nếu token không cần `@PreRemove`, cascade và audit per row, HQL bulk delete là ứng viên tự nhiên. Database cần index phù hợp và transaction/lock policy; với bảng cực lớn có thể cần chia chunk theo key/time.

### 37.2. Import nhiều đơn hàng có aggregate logic

Nếu mỗi Order có nhiều lines, discount, callback và business invariants, ORM batching thường giữ semantics tốt hơn. Tối ưu ID generator, `order_inserts`, batch size, flush/clear và prefetch associations cần thiết.

### 37.3. Đồng bộ giá từ partner

Nếu mỗi Product nhận một giá khác nhau và không cần entity lifecycle, JDBC batch là ứng viên mạnh. Nếu cần compare-and-set, SQL phải có version predicate; nếu cần report thất bại từng row, phải xem driver update counts hoặc dùng staging table.

### 37.4. Chuyển dữ liệu từ bảng sang bảng snapshot

HQL `insert ... select` hoặc native `INSERT ... SELECT` có thể thực hiện gần toàn bộ công việc bên DB. Đọc tất cả rows vào Java rồi persist từng snapshot chỉ để copy cùng dữ liệu thường phát sinh network/memory thừa.

### 37.5. Bù tồn kho sau khi hủy đơn

Nếu logic liên quan Order, Payment, Reservation, Inventory và outbox event, không nên thay bằng một câu JDBC UPDATE chỉ vì nó nhanh. Cần thiết kế một transaction với invariant và idempotency. Sau khi chứng minh correctness, mới chọn ORM hoặc set-based DML cho từng bước thích hợp.

## 38. Ma trận quyết định theo yêu cầu

| Yêu cầu chính | Khuyến nghị ban đầu | Cần đo thêm |
|---|---|---|
| Cập nhật cùng giá trị theo predicate rộng | HQL bulk UPDATE | DB scan/lock, version, cache |
| Xóa tập hàng không cần callbacks | HQL bulk DELETE | FK, triggers, lock, chunking |
| Copy dữ liệu nội bộ DB | HQL/native INSERT SELECT | ID mapping, constraints |
| Nhiều entity có callback/cascade | ORM batching | Batch formation, PC memory |
| Nhiều rows từ nguồn ngoài, mỗi row giá trị riêng | JDBC batch hoặc ORM batch | Version/audit, throughput |
| Nạp dữ liệu cực lớn qua staging | JDBC bulk load/vendor-specific | Portability, dedup, transaction |
| SQL đặc thù DBMS | JDBC/native SQL | Query plan, migration, tests |
| Cần tối đa portability theo entity model | ORM hoặc HQL | Dialect-specific limits |
| Cần trả lỗi chính xác từng row | ORM hoặc JDBC có result strategy | Driver update counts |
| Không được mất bất kỳ event/domain rule nào | ORM hoặc workflow riêng | End-to-end correctness |

Ma trận là **giả thuyết ban đầu để thiết kế benchmark**, không phải quyết định cuối cùng.

## 39. Checklist thực nghiệm để ra quyết định

**Tính đúng đắn**

- Ba phương án có cập nhật đúng cùng rows và cùng field không?
- Version, audit, callbacks, cascade, constraints và tenant isolation có được giữ không?
- Transaction atomicity, retry và idempotency có tương đương không?

**Cấu hình**

- Hibernate batch size, insert/update ordering và ID generator đã phù hợp chưa?
- Với JDBC, driver batching/rewrite settings có được bật và kiểm chứng chưa?
- Với HQL, SQL sinh ra là một hay nhiều statements theo mapping?

**Đo đạc**

- Có đo end-to-end tới commit, rows/s, p95 và heap/GC không?
- Có đo DB CPU/IO, locks, WAL/redo, index plan không?
- Có lặp nhiều lần trên cùng dataset/DBMS/version không?

**Vận hành**

- Nếu chunk lỗi giữa chừng, có thể retry an toàn không?
- Nếu cache có state cũ, có clear/refresh/invalidation đúng không?
- Nếu DB contention tăng, có ngưỡng dừng/throttle không?
- Có đủ observability để xác định bottleneck khi production khác benchmark không?

## 40. Sơ đồ chọn công cụ

```text
             Cần ghi nhiều bản ghi
                      |
                      v
       Cần lifecycle/domain logic mỗi entity?
               /                 \
              CÓ                 KHÔNG
              |                   |
              v                   v
         ORM batching      Dữ liệu cần ghi đã ở DB?
                                   /      \
                                  CÓ      KHÔNG
                                  |        |
                                  v        v
                         Cùng predicate?  Giá trị riêng
                            /     \        mỗi row?
                          CÓ      KHÔNG       |
                          |         |         v
                          v         v    JDBC batch hoặc
                      HQL bulk    HQL/native  ORM batch
                      UPDATE/     set-based   (so benchmark)
                      DELETE      strategy
                          \         |         /
                           \        |        /
                            v       v       v
                         Benchmark cùng semantics
                           + DBMS đích + metrics
                                     |
                                     v
                         Chọn phương án đáp ứng
                         correctness và SLO với
                         chi phí vận hành thấp nhất
```

## 41. Tổng kết

ORM batching, HQL bulk mutation và JDBC batch giải quyết những loại ghi hàng loạt khác nhau:

- **ORM batching** phù hợp khi cần entity lifecycle, domain methods, cascade, validation và optimistic locking. Cần cấu hình batch size, ordering, generator và flush/clear để kiểm soát JDBC batching và memory.
- **HQL mutation** phù hợp khi cùng một predicate/công thức có thể cập nhật hoặc xóa cả tập entity, hoặc khi dữ liệu nguồn/đích đều ở DB. Nó không chạy lifecycle cho từng entity và có thể khiến persistence context stale; phải xử lý version và cache.
- **JDBC direct/batch** phù hợp khi mỗi row có input riêng từ nguồn ngoài, cần giảm ORM overhead hoặc tận dụng bulk load/staging. Ứng dụng tự chịu trách nhiệm về SQL, mapping, version, transaction, error counts, audit và portability.

Đừng chọn một phương án chỉ vì benchmark giả định hoặc một bài viết tuyên bố “nhanh hơn X lần”. Hãy dùng **cùng workload, cùng DBMS, cùng transaction và cùng semantics**, đo end-to-end time, throughput, heap/GC, JDBC round trips và tác động tới database. Kết hợp dữ liệu thực tế với khả năng bảo trì, rủi ro vận hành và yêu cầu nghiệp vụ.

**Kết luận cốt lõi: phương án tốt nhất là phương án đáp ứng đầy đủ tính đúng đắn rồi chứng minh được lợi ích hiệu năng trong môi trường triển khai thực tế.**
