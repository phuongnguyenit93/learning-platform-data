# SQL được log khác với thời điểm giao dịch hoàn tất

Khi làm việc với JPA/Hibernate, lập trình viên thường bật log SQL để xem ứng dụng đang gửi những câu lệnh nào xuống database:

```text
Hibernate:
    insert into purchase_orders
        (customer_id, status, total, id)
    values
        (?, ?, ?, ?)
```

Dòng log này **không chứng minh đơn hàng đã được commit thành công**. Nó chỉ là một tín hiệu từ lớp Hibernate/JDBC về một câu SQL đang được chuẩn bị, bind hoặc đưa vào luồng thực thi. Một transaction còn có thể tiếp tục chạy, gặp constraint violation, bị rollback do exception hoặc thất bại ngay trong bước commit.

Điều tương tự xảy ra với câu UPDATE/DELETE:

```text
Hibernate:
    update purchase_orders
    set status=?, version=?
    where id=? and version=?
```

Nếu sau đó transaction rollback, thay đổi không tồn tại trong database committed state dù SQL đã từng xuất hiện trong log.

**Thông điệp cốt lõi:** Phải tách **log SQL**, **đồng bộ Persistence Context (`flush`)**, **JDBC execution**, **transaction completion (`commit`/`rollback`)** và **khả năng một giao dịch khác nhìn thấy dữ liệu**. Đó là các mốc khác nhau, thuộc những lớp khác nhau của hệ thống.

Bài học này xây dựng cách quan sát từng mốc, giải thích Hibernate SQL logging và parameter binding, ảnh hưởng của ID generator và flush mode, JDBC batching, transaction management trong Spring/JPA, ngoại lệ tại flush hoặc commit, transaction isolation, event callbacks, transactional outbox, và cách kiểm thử để không nhầm một câu SQL đã log với một thay đổi thực sự bền vững.

---

## 1. Năm câu hỏi khác nhau về cùng một thao tác ghi

Giả sử ứng dụng chạy:

```java
em.persist(order);
```

Có thể đặt năm câu hỏi:

1. **Ứng dụng đã gọi `persist()` chưa?** Có — entity được đưa vào lifecycle do Persistence Context quản lý.
2. **Hibernate đã tạo hoặc ghi log một câu INSERT chưa?** Có thể chưa, vì INSERT có thể được hoãn đến flush.
3. **JDBC đã gửi INSERT tới database chưa?** Có thể xảy ra tại flush hoặc sớm hơn tùy ID generator; riêng SQL logger không chứng minh.
4. **Database đã thực thi INSERT trong transaction chưa?** Có thể có, nhưng transaction vẫn có thể rollback.
5. **Database đã commit thành công, để giao dịch khác nhìn thấy row theo isolation policy chưa?** Chỉ có thể xác nhận bằng transaction outcome và phép kiểm tra phù hợp; không suy từ dòng SQL.

Sơ đồ khái quát:

```text
Ứng dụng gọi persist()/sửa entity
            |
            v
Persistence Context giữ trạng thái
            |
            v
Hibernate quyết định flush
            |
            v
Hibernate sinh/ghi log SQL
            |
            v
JDBC prepare + bind + execute/batch
            |
            v
Database xử lý SQL trong transaction
            |
            v
COMMIT hoặc ROLLBACK
            |
            v
Trạng thái committed / khả năng quan sát từ transaction khác
```

**Mỗi mũi tên là một ranh giới cần phân biệt khi chẩn đoán.** Trong một số trường hợp, Hibernate phải INSERT sớm để lấy generated identifier; trong một số trường hợp khác, native/bulk SQL thực thi theo đường đi khác entity dirty checking. Sơ đồ là mô hình tư duy, không phải lời hứa về thứ tự của mọi operation.

## 2. Bảng thuật ngữ quan trọng

| Thuật ngữ | Nghĩa | Không có nghĩa |
| --- | --- | --- |
| `persist()` | Chuyển entity mới thành managed và đăng ký công việc ghi phù hợp | INSERT đã commit |
| Dirty checking | Hibernate nhận diện thay đổi của managed entity | SQL UPDATE xuất hiện ngay khi gọi setter |
| Flush | Đồng bộ những thay đổi pending sang DB qua SQL trong transaction | Commit |
| SQL logging | Ghi nhận câu SQL/parameter/hoạt động JDBC ở một tầng cụ thể | JDBC và DB đã commit |
| JDBC execution | Driver thực thi SQL/batch trên connection | Transaction đã kết thúc thành công |
| Transaction commit | Yêu cầu DB xác nhận các thay đổi của giao dịch | Mọi hệ thống ngoài DB đã cập nhật |
| Transaction rollback | Hủy thay đổi chưa commit trong transaction | Xóa những log/counter/message bên ngoài DB |
| Visibility | Một transaction đọc được phiên bản dữ liệu nào theo isolation/cache | Tất cả connection đều thấy giống nhau ngay |
| `@PostPersist` | JPA callback sau giai đoạn persist/insert phù hợp | After-commit callback |
| After-commit callback | Logic được gọi sau khi transaction được xác nhận thành công trong framework | Durable event delivery khi process crash |

Đặc biệt nhớ:

> **Một dòng `INSERT` trong log không phải bằng chứng database đã commit row.**

## 3. Entity ví dụ: PurchaseOrder

Giả sử schema PostgreSQL có:

```sql
CREATE SEQUENCE purchase_order_seq
    START WITH 1 INCREMENT BY 50;

CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    total NUMERIC(18, 2) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);
```

Entity:

```java
import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "purchaseOrderSeq"
    )
    @SequenceGenerator(
        name = "purchaseOrderSeq",
        sequenceName = "purchase_order_seq",
        allocationSize = 50
    )
    private Long id;

    @Column(name = "customer_id", nullable = false)
    private Long customerId;

    @Column(nullable = false, length = 20)
    private String status;

    @Column(nullable = false, precision = 18, scale = 2)
    private BigDecimal total;

    @Version
    private long version;

    protected PurchaseOrder() {}

    public PurchaseOrder(Long customerId, BigDecimal total) {
        this.customerId = customerId;
        this.total = total;
        this.status = "DRAFT";
    }

    public Long getId() { return id; }
    public String getStatus() { return status; }

    public void markPaid() {
        if (!"DRAFT".equals(status)) {
            throw new IllegalStateException("Not in DRAFT status");
        }
        status = "PAID";
    }
}
```

`purchase_order_seq` có increment tương thích với `allocationSize=50` theo Hibernate sequence optimizer/configuration của ví dụ. Một ứng dụng thực cần migrations, connection/transaction configuration và test với đúng DBMS/dialect.

## 4. Bật SQL logging trong Spring Boot

Để xem Hibernate tạo SQL:

```properties
logging.level.org.hibernate.SQL=DEBUG
```

Để xem JDBC bind parameter values trong Hibernate 6/7:

```properties
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Để quan sát result extraction (chỉ bật lúc chẩn đoán):

```properties
logging.level.org.hibernate.orm.jdbc.extract=TRACE
```

Để xem thông tin JDBC batching trong các Hibernate versions hỗ trợ category này:

```properties
logging.level.org.hibernate.orm.jdbc.batch=TRACE
```

Và có thể bật formatting:

```properties
spring.jpa.properties.hibernate.format_sql=true
```

Hoặc dùng:

```properties
spring.jpa.show-sql=true
```

nhưng `show-sql` thường xuất SQL trực tiếp ra console, khác với việc cấu hình category logging trong hệ thống SLF4J/Logback/Log4j. Khi đã dùng logging framework, thông thường chỉ cần `org.hibernate.SQL=DEBUG` và các category cần thiết; bật cả hai có thể tạo log trùng.

### 4.1. Không bật `TRACE` bind parameters bừa bãi trên production

Bind logs có thể chứa:
- Email, số điện thoại và dữ liệu định danh.
- Access tokens, session identifiers.
- Thông tin tài chính.
- Payload JSON hoặc nội dung tài liệu.
- Những giá trị thuộc dữ liệu nhạy cảm khác.

Chỉ bật tracing có thời hạn, phạm vi hẹp, access control và chính sách redaction. **Không coi SQL log là một audit log an toàn.**

### 4.2. Chú ý tên category theo Hibernate version

Hibernate 5 thường được minh họa với logger `org.hibernate.type.descriptor.sql.BasicBinder`. Hibernate 6/7 dùng category hiện đại như `org.hibernate.orm.jdbc.bind`.

Cần kiểm tra version đang chạy; nếu bật category cũ mà không thấy bind logs, không kết luận Hibernate không bind tham số.

## 5. Dòng SQL log chứng minh điều gì?

Xem:

```text
2026-11-15 09:30:00.101 DEBUG org.hibernate.SQL -
    insert into purchase_orders (customer_id, status, total, version, id)
    values (?, ?, ?, ?, ?)
```

Tín hiệu này cho biết Hibernate đã đến một điểm code **phát sinh/ghi nhận SQL**. Nó không bao gồm:

- Một xác nhận SQL đã thực thi thành công.
- `affected row count` đã được kiểm chứng.
- JDBC batch đã được gửi hết.
- Transaction đã commit.
- Replica đã replay thay đổi.
- Cache downstream đã invalidated.
- Event message đã được publish.
- Người dùng khác đã thấy row.

Tùy Hibernate implementation, logging diễn ra trước hoặc trong quá trình chuẩn bị JDBC statement. Nếu driver ném lỗi khi execute hoặc DB từ chối constraint, dòng SQL vẫn có thể đã xuất hiện.

### 5.1. SQL text thường chỉ có placeholder

```sql
INSERT INTO purchase_orders (customer_id, total) VALUES (?, ?)
```

Các dấu `?` là JDBC bind placeholders. Dùng bind logger để biết giá trị tương ứng, không ghép chuỗi SQL bằng tay từ log rồi mặc định đó là câu SQL DB thực sự nhận trong mọi trường hợp.

Database có thể dùng prepared statement/server-side protocol khác representation hiển thị ở Hibernate log.

## 6. `persist()` có thể chưa phát INSERT

Ví dụ JPA RESOURCE_LOCAL:

```java
EntityTransaction tx = em.getTransaction();
tx.begin();

PurchaseOrder order =
    new PurchaseOrder(42L, new BigDecimal("250.00"));

em.persist(order);

System.out.println("Persist returned");

tx.commit();
```

Với `SEQUENCE`, Hibernate có thể lấy ID trước, giữ entity trong Persistence Context và hoãn INSERT đến flush trước commit.

Một thứ tự log có thể là:

```text
Hibernate SQL: select nextval('purchase_order_seq')
Application: Persist returned
Hibernate SQL: insert into purchase_orders ...
Transaction: commit
```

`select nextval` chỉ là ví dụ PostgreSQL, không phải câu SQL mọi dialect sẽ dùng; với sequence pooling, thậm chí không phải mỗi `persist()` đều phát `nextval`.

Nếu bạn nhìn thấy dòng `Persist returned` **trước** INSERT, đó là hành vi hợp lệ. Hibernate chưa cần thực thi INSERT ngay khi `persist()` trả về.

### 6.1. `persist()` vẫn có thể phát SQL sớm

Không được suy ngược rằng “mọi persist chỉ ghi RAM”. Một số ID generator, flush mode, query hoặc cascade có thể đòi SQL sớm hơn.

Phải quan sát SQL/transaction theo **ID strategy và đường đi thực tế**.

## 7. `IDENTITY` có thể INSERT ngay để lấy ID

Ví dụ:

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

Với identity-based generated key, Hibernate thường cần thực thi INSERT để lấy identifier do database tạo, nên SQL INSERT có thể xuất hiện ngay trong lời gọi `persist()` hoặc một thời điểm sớm phù hợp provider/configuration.

```text
BEGIN
  persist(entity)
    -> INSERT to obtain generated ID
  business logic continues
  ...
ROLLBACK
```

Kể cả khi INSERT đã thực thi và ID được sinh, **rollback vẫn có thể hủy row**. Trên nhiều DBMS, sequence/identity values đã tiêu thụ không được rollback; có khoảng trống ID không có nghĩa entity đã được commit.

### 7.1. Một ID đã được gán không chứng minh đã commit

```java
em.persist(order);
Long id = order.getId();
```

`id != null` chỉ nói identifier đã được cấp/gán theo generator semantics. Nó không chứng minh transaction sẽ commit thành công hoặc row tồn tại sau rollback.

## 8. Dirty checking: gọi setter không đồng nghĩa UPDATE ngay

Ví dụ:

```java
tx.begin();

PurchaseOrder order =
    em.find(PurchaseOrder.class, 100L);

order.markPaid();

System.out.println("Status changed in memory");

tx.commit();
```

Hibernate theo dõi managed entity và phát UPDATE khi nó quyết định flush, không nhất thiết tại `order.markPaid()`.

Có thể thấy:

```text
SELECT ... FROM purchase_orders WHERE id=?
Application: Status changed in memory
UPDATE purchase_orders SET status=?, version=? WHERE id=? AND version=?
JDBC commit
```

Nếu entity không thực sự dirty, Hibernate có thể không phát UPDATE dù code gọi setter gán lại cùng giá trị.

### 8.1. `@Version` và thời điểm lỗi

Với optimistic locking, Hibernate có thể phát:

```sql
UPDATE purchase_orders
SET status=?, version=?
WHERE id=? AND version=?;
```

Nếu affected count không như kỳ vọng vì row đã bị transaction khác thay đổi, lỗi optimistic locking có thể chỉ xuất hiện khi flush/executeBatch. SQL log vẫn có thể có trước exception.

## 9. `flush()` là đồng bộ, không phải commit

Ví dụ:

```java
tx.begin();

em.persist(order);
em.flush();

System.out.println("Flush completed");

tx.rollback();
```

Khi `flush()` thành công, Hibernate đã cố thực hiện các SQL cần thiết để đồng bộ pending work vào database **trong transaction hiện tại**.

Điều đó có nghĩa:
- DB có thể đã xử lý INSERT/UPDATE/DELETE.
- Constraints không deferred có thể đã được kiểm tra.
- Hibernate có thể đã cập nhật internal snapshots/action queues.
- Transaction **vẫn mở**, có thể rollback.
- Không có cam kết một transaction khác đã thấy dữ liệu.

**Flush thành công là điều kiện hữu ích để phát hiện nhiều lỗi ghi sớm, nhưng không phải bằng chứng durable commit.**

### 9.1. Không gọi `clear()` trước flush

```java
em.persist(order);
em.clear();
em.flush();
```

có thể làm các pending changes bị bỏ khi entity bị detach. Trong các batch imports, thứ tự chuẩn khi cần giải phóng Persistence Context là:

```java
em.flush();
em.clear();
```

Và sau đó vẫn cần commit transaction nếu muốn DB giữ thay đổi.

### 9.2. Nhiều flush vẫn là một transaction

```text
BEGIN
  persist 100
  FLUSH
  clear
  persist 100
  FLUSH
  clear
  persist 50
  FLUSH
COMMIT
```

Ba lần flush không tạo ba commits. Nếu transaction cuối cùng rollback, các SQL trong các lần flush cũng không được commit.

## 10. Hibernate flush mode và thời điểm SQL được log

JPA có:

```java
em.setFlushMode(FlushModeType.AUTO);
em.setFlushMode(FlushModeType.COMMIT);
```

Hibernate bổ sung các flush modes như `ALWAYS`, `AUTO`, `COMMIT`, `MANUAL` theo API/version.

| Flush mode | Hành vi thông thường | Hệ quả quan sát |
| --- | --- | --- |
| `AUTO` | Flush trước commit, và trước query khi cần bảo đảm semantics liên quan | SQL có thể xuất hiện giữa service method |
| `COMMIT` | Cố hoãn flush đến commit, có các ngoại lệ/provider details | SQL ghi muộn hơn; JPQL query visibility có caveat |
| `ALWAYS` (Hibernate) | Flush trước mỗi query phù hợp và commit | Có thể thấy nhiều SQL/flush hơn |
| `MANUAL` (Hibernate) | Application chịu trách nhiệm gọi flush | Có thể không có DML khi commit nếu không flush |
 
**Không tự đặt `MANUAL` chỉ để giảm log hay tối ưu hiệu năng.** Bạn có thể không đồng bộ pending state như dự kiến nếu thiếu explicit flush. Với JPA `FlushModeType.COMMIT`, quy tắc query visibility có những điểm phụ thuộc provider/spec.

### 10.1. Mode ảnh hưởng khi nào SQL xuất hiện, không đổi nghĩa commit

Dù Hibernate gửi INSERT tại auto-flush, manual flush hay flush trước commit, database chỉ công nhận giao dịch hoàn tất khi transaction commit thành công.

## 11. Auto-flush trước JPQL/HQL query

Xét:

```java
em.persist(order);

long count = em.createQuery("""
    select count(o)
    from PurchaseOrder o
    """, Long.class).getSingleResult();
```

Với `AUTO` mode, nếu Hibernate xác định query overlaps với những pending changes, nó có thể flush INSERT **trước câu SELECT** để query thấy dữ liệu phù hợp.

Một chuỗi:

```text
persist()
  |
  v
JPQL SELECT COUNT on PurchaseOrder
  |
  v
AUTO FLUSH
  |
  +-- Hibernate SQL: INSERT purchase_orders
  |
  +-- Hibernate SQL: SELECT COUNT
```

Lúc này bạn có thể nghĩ “chưa commit sao đã thấy INSERT?” — bởi vì query làm phát sinh flush, **không phải vì transaction đã kết thúc**.

### 11.1. Không phải mọi query đều auto-flush như nhau

Một query tới bảng không liên quan pending changes có thể không cần flush. Native SQL qua JPA `EntityManager` và Hibernate-native Session có rules phụ thuộc synchronization/query spaces và bootstrap.

Không dựa vào một ví dụ duy nhất để suy mọi query đều flush hoặc không flush. Hibernate User Guide mô tả những trường hợp AUTO flush tương ứng.

## 12. Native query và synchronized query spaces

Một native SQL query có thể ảnh hưởng cách Hibernate quyết định flush.

Hibernate-specific API:

```java
import org.hibernate.Session;
import org.hibernate.query.NativeQuery;

Session session = em.unwrap(Session.class);

NativeQuery<?> query = session.createNativeQuery("""
    select count(*)
    from purchase_orders
    """);

query.addSynchronizedEntityClass(PurchaseOrder.class);

Object result = query.getSingleResult();
```

Việc khai báo synchronized entity/query spaces giúp Hibernate biết bảng/entity spaces liên quan tới query, phục vụ việc xác định thời điểm flush và một số cache synchronization decisions theo version.

Nhưng đừng nhầm:
- `addSynchronizedEntityClass()` không commit transaction.
- Một native SELECT không chứng minh pending changes đã commit.
- Một JDBC query bên ngoài Hibernate không tự kích hoạt flush của Persistence Context Hibernate.

## 13. `save()` và `saveAndFlush()` trong Spring Data JPA

Spring Data JPA repository:

```java
repository.save(order);
```

không phải một lời hứa “đã INSERT và commit ngay”. Tùy entity new/detached state, implementation có thể gọi `EntityManager.persist()` hoặc `merge()` và transaction boundary do service/repository quản lý.

```java
repository.saveAndFlush(order);
```

yêu cầu flush sau save theo repository contract, nhưng **không tự bảo đảm một transaction bên ngoài đã commit**.

Ví dụ:

```java
@Transactional
public void createThenFail(PurchaseOrder order) {
    repository.saveAndFlush(order);
    throw new IllegalStateException("Fail after flush");
}
```

Nếu exception khiến Spring rollback transaction, database không giữ row đã flush, dù Hibernate SQL logger đã in INSERT.

### 13.1. Có transaction ngoài hay không quyết định khác biệt

Nếu repository method được gọi **không có transaction service bao quanh**, repository có thể tự mở và commit transaction theo cấu hình `@Transactional` của Spring Data JPA. Nếu có transaction đang tồn tại với propagation `REQUIRED`, nó thường tham gia transaction đó.

Đừng suy transaction boundary từ tên method `save` hoặc số dòng SQL log; phải xem **call stack, proxy và transaction manager**.

## 14. Timeline một service `@Transactional` trong Spring

Ví dụ:

```java
@Service
public class OrderService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public Long createOrder() {
        PurchaseOrder order = new PurchaseOrder(
            42L, new BigDecimal("250.00")
        );

        em.persist(order);

        System.out.println("Inside method, ID=" + order.getId());

        return order.getId();
    }
}
```

Controller gọi:

```java
Long id = orderService.createOrder();

System.out.println("Service proxy returned, ID=" + id);
```

Với Spring proxy-based declarative transactions:

```text
Controller
    |
    v
Spring transaction proxy
    |
    +-- BEGIN transaction
    |
    +-- invoke OrderService.createOrder()
    |       |
    |       +-- em.persist()
    |       +-- log "Inside method"
    |       +-- return result to proxy
    |
    +-- beforeCommit / flush if needed
    +-- JDBC transaction commit
    +-- afterCommit / afterCompletion callbacks
    |
    v
Return result to Controller
    |
    +-- log "Service proxy returned"
```

Đây là mô hình phổ biến khi method được **gọi qua Spring transactional proxy** và transaction manager đồng bộ. Một lời gọi nội bộ/self-invocation không đi qua proxy có thể làm annotation không tạo transaction mới như mong đợi.

### 14.1. Method body kết thúc khác caller nhận return

Trong service method, bạn có thể in `"returning"` trước commit. Nhưng caller thông thường chỉ nhận được kết quả sau khi transactional interceptor xử lý commit thành công.

Nếu commit thất bại, caller có thể nhận exception **dù method body đã return một ID cho proxy**. Vì vậy không coi log cuối service method là bằng chứng transaction đã commit.

### 14.2. Commit đôi khi làm Hibernate phát SQL

Nếu chưa flush trước đó, transaction manager/JPA provider thường auto-flush pending changes trong quá trình commit theo flush mode. Do đó bạn có thể thấy SQL **sau log cuối trong service method nhưng trước log đầu tiên tại caller**.

## 15. RESOURCE_LOCAL JPA và Spring/JTA khác cách quản lý transaction

JPA resource-local:

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();
    em.persist(order);
    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

Ở đây code tự begin/commit/rollback.

Trong Spring:

```java
@Transactional
public void createOrder() {
    em.persist(order);
}
```

transaction manager điều khiển boundary; không thường xuyên gọi `em.getTransaction().begin()` thủ công bên trong cùng Spring-managed JPA transaction.

Trong JTA/XA transaction, commit có thể bao gồm transaction coordinator và nhiều tài nguyên; lời gọi JDBC `Connection.commit()` trực tiếp không còn là toàn bộ câu chuyện. Cần dùng instrumentation của transaction manager tương ứng.

### 15.1. Đừng kết luận COMMIT từ việc Session được đóng

Đóng một EntityManager/Session không tự có nghĩa mọi thay đổi đã commit. Nếu transaction chưa commit, rollback/cleanup behavior phụ thuộc transaction/connection management. Luôn thiết kế rõ transaction lifecycle.

## 16. SQL đã chạy vẫn có thể rollback

Transaction T1:

```sql
BEGIN;

INSERT INTO purchase_orders
    (id, customer_id, status, total, version)
VALUES
    (101, 42, 'DRAFT', 100.00, 0);

ROLLBACK;
```

Câu INSERT đã thực thi trên database; SQL có thể được ghi trong database statement log hoặc Hibernate log.

Nhưng:

```sql
SELECT *
FROM purchase_orders
WHERE id = 101;
```

trong một transaction mới thông thường không tìm thấy row.

Điều này không phải Hibernate lỗi, mà là **transaction atomicity**.

### 16.1. Dòng SQL log là tín hiệu của attempt, không phải kết quả cuối

Một hệ thống diagnostic nên phân biệt:

```text
sql.attempted
sql.executed
tx.committed
tx.rolled_back
business_operation.completed
```

Không tạo metric `orders_created_total` chỉ bằng cách đếm `org.hibernate.SQL` có từ khóa `INSERT`, vì retry và rollback sẽ làm metric sai.

## 17. `flush()` thành công nhưng `commit()` vẫn có thể thất bại

Nhiều lỗi được phát hiện tại flush:

- NOT NULL violation.
- UNIQUE violation (nếu constraint được kiểm tra tức thời).
- FK violation.
- Optimistic locking conflict.
- JDBC connection issue.
- Deadlock/lock timeout.

Nhưng cũng có lỗi được phát hiện muộn hơn, **tại commit**:

- Deferred constraints.
- Serialization failure trong một số isolation/DBMS conditions.
- Deadlock hoặc transaction abort được phát hiện muộn.
- Transaction manager/resource failure.
- Network connection failure khi xác nhận commit.

### 17.1. Ví dụ PostgreSQL constraint deferred

PostgreSQL hỗ trợ foreign key có thể được defer:

```sql
CREATE TABLE parents (
    id BIGINT PRIMARY KEY
);

CREATE TABLE children (
    id BIGINT PRIMARY KEY,
    parent_id BIGINT NOT NULL,
    CONSTRAINT fk_children_parent
        FOREIGN KEY (parent_id)
        REFERENCES parents(id)
        DEFERRABLE INITIALLY DEFERRED
);
```

Một transaction:

```sql
BEGIN;

INSERT INTO children (id, parent_id)
VALUES (1, 999);

-- Statement có thể thành công,
-- vì FK được trì hoãn kiểm tra đến COMMIT.

COMMIT; -- Có thể thất bại do parent#999 không tồn tại.
```

Đây là ví dụ phù hợp với PostgreSQL, không phải hành vi mọi DBMS/constraint. `em.flush()` có thể thành công vì SQL đã chạy, nhưng commit thất bại khi constraint deferred được kiểm tra.

### 17.2. Kết luận

**Không thể thay `commit()` bằng một lần `flush()` và khẳng định transaction thành công.**

## 18. SQL logging và JDBC batching

Hibernate có cấu hình:

```properties
spring.jpa.properties.hibernate.jdbc.batch_size=25
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
```

Một application loop có thể:

```java
for (PurchaseOrder order : orders) {
    em.persist(order);
}

em.flush();
```

SQL logger có thể ghi nhiều lệnh có cùng SQL shape:

```text
insert into purchase_orders (...) values (...)
insert into purchase_orders (...) values (...)
insert into purchase_orders (...) values (...)
...
```

Nhưng driver/Hibernate có thể gom thành JDBC batches để giảm round trips.

### 18.1. SQL log lines không tương đương network round trips

Đếm 100 dòng INSERT **không chứng minh**:
- Driver đã gọi `executeUpdate()` 100 lần.
- Driver đã gửi đúng 100 round trips.
- Database đã commit 100 rows.
- Một JDBC batch đã thành công toàn bộ.

Ngược lại, nếu log SQL được tạo từ một prepared statement shape rồi driver execute nhiều parameter sets, số dòng được log có thể không phản ánh trực tiếp số rows.

Để đo batching, cần:
- Hibernate JDBC batch logger/metrics tương ứng.
- Datasource proxy/JDBC instrumentation có hỗ trợ batch operations.
- Driver/database statement/round-trip metrics.
- Transaction commit/rollback outcome.

### 18.2. `IDENTITY` ảnh hưởng batching

Với Hibernate entity INSERT dùng IDENTITY, ORM thường cần INSERT sớm để lấy ID và có thể không dùng JDBC insert batching như khi dùng pooled SEQUENCE. Đừng chỉ bật `hibernate.jdbc.batch_size` rồi suy mọi INSERT đã được batch.

### 18.3. Lỗi trong batch có thể phát hiện muộn

Hibernate có thể đã log nhiều INSERT, nhưng tới `executeBatch()` driver mới ném `BatchUpdateException`. Khi đó các statement trước có thể đã được xử lý **trong transaction**, nhưng transaction phải được rollback/đánh giá theo trạng thái lỗi, không tiếp tục như đã commit một phần an toàn.

## 19. Prepared statement và bind logging

JDBC lifecycle dạng đơn giản:

```text
SQL generated
   |
   v
prepareStatement(sql)
   |
   v
setLong / setString / setBigDecimal parameters
   |
   v
executeUpdate / addBatch + executeBatch
   |
   v
DB response / JDBC result
```

SQL logging ở một điểm trong quá trình này có thể xảy ra **trước** khi DB trả response.

`org.hibernate.orm.jdbc.bind=TRACE` cho biết binding của values tại JDBC layer, nhưng vẫn chưa là commit marker.

### 19.1. `StatementInspector` chỉ nhìn SQL string

Hibernate cung cấp:

```java
import org.hibernate.resource.jdbc.spi.StatementInspector;

public final class SqlTraceInspector
        implements StatementInspector {

    @Override
    public String inspect(String sql) {
        // Gắn correlation metadata hoặc ghi nhận SQL text
        // trong môi trường chẩn đoán có kiểm soát.
        return sql;
    }
}
```

`inspect(sql)` được gọi khi Hibernate chuẩn bị SQL statement cho JDBC. Nó **không phải callback sau SQL execution** và không phải callback after commit.

Nếu muốn biết thực tế `execute` kéo dài bao lâu, có exception gì và transaction outcome gì, cần JDBC/datasource/transaction instrumentation khác.

## 20. L1 cache: `find()` có thể không phát SQL

```java
PurchaseOrder first = em.find(PurchaseOrder.class, 101L);
PurchaseOrder second = em.find(PurchaseOrder.class, 101L);
```

Trong cùng Persistence Context:

```java
first == second // thường true
```

Lần thứ hai có thể không phát SELECT vì entity đã managed ở first-level cache.

Điều đó nghĩa là:
- **Không thấy SQL** không chứng minh operation không được xử lý.
- **Thấy SQL SELECT** không chứng minh transaction ghi đã commit.
- Entity load từ L2 cũng có thể không cần SQL SELECT.
- SQL logger không thể dùng một mình để reconstruct toàn bộ application-level reads.

### 20.1. Lazy loading còn làm SQL xuất hiện muộn

Một association:

```java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
```

có thể không tải Customer khi truy vấn Order, mà chỉ SELECT khi application truy cập proxy/association.

Nếu SELECT xuất hiện **sau một log nghiệp vụ**, không nhất thiết query nghiệp vụ kia được commit trễ; có thể chỉ là lazy initialization.

## 21. Bulk HQL/JPQL và native SQL có timing khác entity dirty checking

Một bulk HQL mutation:

```java
int affected = em.createQuery("""
    update PurchaseOrder o
    set o.status = :next
    where o.status = :current
    """)
    .setParameter("next", "PAID")
    .setParameter("current", "DRAFT")
    .executeUpdate();
```

đi qua query execution, không nhất thiết phải load từng managed PurchaseOrder rồi dirty-check như vòng lặp setter.

**`affected` là số rows được báo theo bulk operation semantics, không phải số rows đã commit.** Nếu transaction rollback, update không bền vững.

Một native SQL:

```java
em.createNativeQuery("""
    update purchase_orders
    set status = :status
    where id = :id
    """)
    .setParameter("status", "PAID")
    .setParameter("id", 101L)
    .executeUpdate();
```

cũng thực thi trực tiếp qua query execution. Persistence Context đã load order trước đó có thể còn state cũ; ORM callbacks/Envers không tự áp lên từng row như managed updates.

### 21.1. Native DML không có “commit ngầm” khi transaction vẫn mở

`executeUpdate()` hoàn tất không tự làm `COMMIT` chỉ vì SQL UPDATE đã chạy. Nó vẫn nằm trong transaction do JPA/Spring/JTA quản lý.

## 22. Transaction isolation: cùng SQL, hai kết quả đọc

Hai connections:

```text
Connection A:
  BEGIN
  INSERT Order#101
  FLUSH

Connection B:
  BEGIN
  SELECT Order#101
     -> thường CHƯA THẤY

Connection A:
  COMMIT

Connection B:
  SELECT Order#101
     -> có thể thấy theo isolation/snapshot
```

Với isolation `READ COMMITTED` và một SELECT mới sau commit của A, B thường có thể thấy row (nếu cùng primary DB, không có filter/cache khác).

Nhưng với `REPEATABLE READ` hoặc snapshot isolation, B có thể tiếp tục thấy snapshot trước commit A trong cùng transaction B.

### 22.1. Flush không thay quy tắc isolation

Trong transaction A, JDBC SELECT qua **cùng transaction/connection** có thể thấy những writes chưa commit của chính A.

Một transaction B bình thường **không** được xem row đó chỉ vì Hibernate A đã flush. Đây là mục đích của transaction isolation.

### 22.2. Cache và replica làm việc kiểm tra phức tạp hơn

Nếu B đọc từ:
- Entity đang managed trong L1.
- Cache L2.
- Query result cache.
- Read replica có replication lag.

thì kết quả không chỉ phụ thuộc SQL commit của primary. Khi điều tra visibility, dùng context mới, chính xác datasource/replica, tắt/bypass các cache cần thiết và ghi nhận isolation level.

## 23. JDBC auto-commit có thể làm thay đổi cách hiểu log

Nếu JDBC connection ở `autoCommit=true`, mỗi SQL statement có thể được commit tự động theo JDBC/DB semantics, thay vì tham gia một explicit application transaction lớn.

Trong một Spring/JPA `@Transactional` thông thường, transaction manager cấu hình connection phù hợp để quản lý commit/rollback. Không suy điều này đúng chỉ vì có HikariCP; phải xác nhận datasource/transaction manager thực tế.

### 23.1. Phân biệt raw JDBC không tham gia transaction

Ví dụ nguy hiểm:

```java
@Transactional
public void createOrder() {
    em.persist(order);

    Connection con = anotherDataSource.getConnection();
    // UPDATE ... qua một connection khác có autoCommit=true.
}
```

Hai operations có thể không nằm trong cùng transaction nếu datasource/connection không được phối hợp.

Hibernate log và JDBC log cùng thread không chứng minh **cùng physical transaction**. Với Spring, ưu tiên transaction-aware `JdbcTemplate`/DataSource integration phù hợp khi cần ORM + JDBC tham gia cùng transaction.

## 24. Spring propagation tạo nhiều commit boundaries

Một service outer:

```java
@Transactional
public void outer() {
    orderService.saveOrder();
    auditService.saveAuditRequiresNew();
    throw new RuntimeException("Outer fails");
}
```

Và inner khác bean:

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void saveAuditRequiresNew() {
    auditRepository.save(...);
}
```

Nếu proxy wiring/transaction manager đúng:

```text
Outer transaction T1 BEGIN
  Save Order pending
  Suspend T1
  Inner transaction T2 BEGIN
    INSERT audit
  T2 COMMIT
  Resume T1
  Exception
T1 ROLLBACK
```

Kết quả:
- Audit của T2 có thể đã commit.
- Order của T1 rollback.
- SQL logs xen kẽ nhưng **không cùng commit**.

Điều này có thể hợp lý cho audit *attempt* logs, nhưng không phù hợp nếu audit row T2 khẳng định Order đã tạo thành công.

### 24.1. Self-invocation không bảo đảm `REQUIRES_NEW`

```java
public void outer() {
    this.innerRequiresNew(); // Có thể bypass Spring proxy.
}
```

Trong Spring proxy-based mode, lời gọi qua `this` không chạy transaction advice như lời gọi từ bean khác đi qua proxy. Không kết luận “đã có 2 transactions” chỉ vì có hai annotations trong source.

### 24.2. `NESTED` và savepoint không giống `REQUIRES_NEW`

Propagation `NESTED` thường dựa trên JDBC savepoints khi transaction manager hỗ trợ. Một rollback tới savepoint không đồng nghĩa transaction vật lý độc lập đã commit.

Nhìn SQL log đơn thuần càng khó xác định transaction propagation; cần transaction-manager traces và connection/tx IDs.

## 25. `@Transactional(readOnly = true)` không phải SQL COMMIT indicator

Spring:

```java
@Transactional(readOnly = true)
public PurchaseOrder findOrder(Long id) {
    return em.find(PurchaseOrder.class, id);
}
```

`readOnly=true` chủ yếu là hint/optimization theo transaction manager, provider và database; nó không phải lời hứa ứng dụng bất khả thi ghi dữ liệu trong mọi cấu hình.

Với Hibernate, một số read-only transaction settings có thể ảnh hưởng flush/dirty checking. Đừng đặt một method đang ghi trong read-only transaction rồi suy `save()` chắc chắn đã commit chỉ vì SQL log có INSERT.

### 25.1. Read-only queries vẫn có transaction lifecycle

Một `SELECT` thường có thể chạy bên trong transaction, nhưng SQL SELECT xuất hiện không nói gì về successful completion của một transaction ghi khác.

## 26. `@PostPersist` và Hibernate `POST_INSERT` không phải after-commit

Entity callback:

```java
@PostPersist
public void afterPersist() {
    // Thời điểm phù hợp trong entity lifecycle.
}
```

Hibernate event listener:

```java
public void onPostInsert(PostInsertEvent event) {
    // Thời điểm sau SQL INSERT theo event semantics.
}
```

Hai callback trên không có contract “DB transaction đã commit thành công”.

Timeline:

```text
BEGIN
  Hibernate INSERT
  @PostPersist / POST_INSERT events có thể chạy
  Gửi message bên ngoài (NGUY HIỂM)
  UPDATE khác bị lỗi
ROLLBACK
```

Message đã gửi ra ngoài không tự rollback.

### 26.1. Một revision Envers cũng không là commit marker trước transaction completion

Envers ghi các audited changes trong transaction ORM phù hợp. Audit SQL có thể được phát/ghi log trước commit; nếu transaction rollback, audit rows cùng transaction không tồn tại trong committed state.

Đừng đếm audit INSERT log rồi kết luận đã có một revision bền vững.

## 27. Spring `TransactionSynchronization`: quan sát transaction completion

Spring cung cấp callbacks transaction lifecycle:

```java
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Transactional
public void processOrder() {
    // Mutate managed entities...

    TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {

            @Override
            public void afterCommit() {
                // Chỉ chạy sau khi Spring xác nhận commit thành công.
                // Không phải nơi lý tưởng cho network call quan trọng.
            }

            @Override
            public void afterCompletion(int status) {
                if (status == STATUS_COMMITTED) {
                    // Mark commit observed.
                } else if (status == STATUS_ROLLED_BACK) {
                    // Mark rollback observed.
                } else {
                    // STATUS_UNKNOWN.
                }
            }
        }
    );
}
```

Đây là snippet minh họa, giả định Spring transaction synchronization đang active; nếu gọi ngoài transaction phù hợp, registration có thể lỗi.

### 27.1. After-commit không tự trở thành durable event delivery

Một callback Java có thể:
- Ném exception sau DB commit.
- Không chạy vì process crash ngay sau DB commit.
- Gặp network timeout khi gọi broker.
- Bị thực thi lại khi application retry logic không idempotent.

Vì vậy không gửi message nghiệp vụ quan trọng chỉ dựa vào `afterCommit()` và coi là exactly-once.

### 27.2. `afterCompletion(STATUS_UNKNOWN)` có ý nghĩa

Một số failure paths khiến transaction manager không thể xác nhận chính xác outcome với ứng dụng. Đừng biến mọi exception ở commit thành “chắc chắn rollback thành công”; có tình huống outcome chưa rõ và cần reconciliation.

## 28. `@TransactionalEventListener(AFTER_COMMIT)` cũng có giới hạn

Spring có:

```java
@Component
public class OrderCreatedListener {

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void onOrderCreated(OrderCreated event) {
        // Chạy sau commit trong process này.
    }
}
```

`OrderCreated` là application event do hệ thống định nghĩa, không phải Hibernate `PostInsertEvent`.

Thích hợp cho:
- In-process notification ít rủi ro.
- Cache invalidation có retry/fallback.
- Metrics sau commit.

Không đủ nếu:
- Broker message không được phép mất.
- Downstream system phải nhất quán dù JVM crash.
- Cần một durable queue.
- Hệ thống phải replay events sau outage.

Khi cần bảo đảm, dùng **transactional outbox** hoặc CDC với delivery/idempotency strategy.

## 29. Transactional outbox: tách SQL đã ghi khỏi event đã xuất bản

Ví dụ trong cùng transaction:

```java
@Transactional
public Long createOrder(CreateOrderCommand cmd) {
    PurchaseOrder order = new PurchaseOrder(
        cmd.customerId(), cmd.total()
    );

    em.persist(order);

    OutboxEvent event = OutboxEvent.orderCreated(
        UUID.randomUUID(),
        order.getId()
    );

    em.persist(event);

    return order.getId();
}
```

`CreateOrderCommand` và `OutboxEvent` là các types ứng dụng cần định nghĩa; ví dụ giả định ID của order được cấp tại thời điểm tạo event, hoặc logic có cách lấy identifier phù hợp.

Một transaction:

```text
BEGIN
  INSERT purchase_orders
  INSERT outbox_events
COMMIT
   |
   v
Publisher đọc outbox đã commit
   |
   v
Publish broker với retry/idempotency
```

Lợi ích:
- Nếu transaction rollback, cả order và outbox event rollback.
- Nếu DB commit nhưng JVM crash trước publish, outbox row vẫn còn.
- Publisher có thể retry sau khi khởi động lại.
- Consumer dùng event ID để deduplicate.

Nhưng outbox cũng không tự bảo đảm exactly-once broker delivery; một event có thể publish lặp khi publisher crash trước khi đánh dấu đã gửi.

### 29.1. Tại sao SQL log không thay thế outbox?

Một đoạn text:

```text
Hibernate: insert into outbox_events ...
```

không phải một queue bền vững. Nếu transaction rollback, row không tồn tại; nếu log bị rotate, log line có thể biến mất; nếu log chứa PII, nó có rủi ro bảo mật.

Outbox dựa vào **committed database state**, không dựa vào SQL debug messages.

## 30. Lỗi commit có thể để trạng thái transaction “chưa xác định”

Giả sử:
1. Ứng dụng gửi yêu cầu COMMIT.
2. Database thực sự commit.
3. Mạng bị ngắt trước khi ứng dụng nhận acknowledgement.
4. Client thấy exception/time-out.

Lúc này ứng dụng **không thể chỉ từ exception suy rằng DB đã rollback**. Tùy DB/driver/transaction manager, outcome có thể ambiguous.

```text
Application              Database
     |                      |
     |---- COMMIT --------->|
     |                      | Commit succeeds
     |<--- X network ------|
     |
     +-- Exception/timeout, outcome uncertain
```

### 30.1. Retry phải idempotent

Nếu application tự động retry `createOrder()` không có idempotency key, có thể tạo hai đơn hàng.

Một chiến lược:
- Mỗi command có `requestId` unique.
- Database có UNIQUE constraint cho key.
- Khi retry, query committed state theo requestId.
- Phân biệt failed/uncommitted/committed/unknown.
- Dùng optimistic/concurrency controls theo nghiệp vụ.

**Đừng coi “SQL INSERT đã log” là bằng chứng vừa để xác nhận thành công, vừa để xác nhận thất bại.** Cần authoritative state và retry design.

## 31. Spring exception rules và rollback-only

Ví dụ:

```java
@Transactional
public void process() {
    repository.saveAndFlush(order);
    throw new RuntimeException("Failed later");
}
```

Với Spring declarative transaction defaults, một unchecked exception thông thường làm transaction rollback.

Nhưng checked exceptions có rollback rules khác theo cấu hình:

```java
@Transactional(rollbackFor = MyCheckedException.class)
public void process() throws MyCheckedException {
    ...
}
```

Không mặc định mọi exception đều tạo rollback nếu transaction manager/annotation đã custom rules.

### 31.1. Catch exception không có nghĩa transaction vẫn commit an toàn

Ví dụ:

```java
@Transactional
public void process() {
    try {
        repository.saveAndFlush(order);
    } catch (PersistenceException ex) {
        // Log và bỏ qua?
    }
}
```

Sau exception từ flush/JDBC, transaction có thể bị đánh dấu rollback-only hoặc Session không còn sử dụng an toàn. Dù method body tiếp tục và trả bình thường, transaction manager có thể ném `UnexpectedRollbackException` hoặc exception khác ở commit.

Hướng xử lý thường là rollback, bỏ context lỗi và chạy transaction mới khi có chính sách retry hợp lệ.

## 32. SQL log và database statement log là hai hệ quan sát

Hibernate SQL log phát tại JVM/ORM layer.

Database log hoặc query monitoring ở DB server có thể cho biết:
- Statement nào DB nhận/thực thi.
- Connection/session ID.
- Duration/lock waits.
- SQLSTATE/error.
- Transaction IDs/commit markers tùy DBMS/extension/log format.
- Deadlocks và slow queries.

Nhưng **database statement log của INSERT cũng không tự chứng minh COMMIT** nếu chỉ xem riêng statement line.

Muốn khẳng định commit:
- Quan sát transaction manager outcome.
- Dùng DB transaction/audit/commit logs với cấu hình phù hợp.
- Hoặc kiểm tra committed state bằng transaction khác theo consistency requirements.

### 32.1. Một connection pool tạo nhiều physical connections

Application có thể dùng HikariCP, với nhiều sessions/transactions luân phiên mượn connections. Hai SQL liên tiếp trong cùng log file không chắc cùng transaction.

Khi chẩn đoán, cần correlation IDs hoặc connection/transaction context từ instrumentation, thay vì nhìn timestamp gần nhau rồi ghép tùy ý.

## 33. Correlation IDs giúp ghép đúng request và transaction

Một log application hữu ích nên có:

```text
timestamp
traceId / requestId
thread
service / operation
transaction phase
connection or session identifier (nếu có an toàn)
SQL category
exception / SQLSTATE
```

Ví dụ minh họa:

```text
09:00:00.100 trace=abc operation=createOrder tx=begin
09:00:00.105 trace=abc operation=createOrder entity=persist
09:00:00.130 trace=abc category=org.hibernate.SQL INSERT purchase_orders ...
09:00:00.134 trace=abc tx=flush-complete
09:00:00.140 trace=abc tx=commit-start
09:00:00.155 trace=abc tx=commit-complete
09:00:00.158 trace=abc operation=createOrder outcome=SUCCESS
```

Nếu commit lỗi:

```text
09:00:00.155 trace=abc tx=commit-error SQLSTATE=...
09:00:00.158 trace=abc operation=createOrder outcome=FAILED_OR_UNKNOWN
```

`tx=commit-complete` là log **do transaction instrumentation thực sự đặt sau successful commit**, không phải dòng giả định Hibernate SQL logger tự sinh ra.

### 33.1. Không dùng thread ID làm transaction ID duy nhất

Thread pools tái sử dụng threads; reactive/asynchronous execution có thể chuyển threads; propagation REQUIRES_NEW tạo transaction khác trong cùng thread.

Cần kết hợp trace/request ID với transaction boundary/connection metadata, không chỉ `%thread`.

### 33.2. Bảo mật khi dùng SQL comments

Hibernate có `hibernate.use_sql_comments` và `StatementInspector` có thể gắn comments với SQL. Không đưa secrets, token, PII hoặc data có độ nhạy cao vào comments, vì chúng có thể vào DB logs và query statistics.

## 34. Hibernate Statistics giúp đo, không chứng minh commit nghiệp vụ

Có thể bật:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
```

Và đọc:

```java
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;

SessionFactory sessionFactory =
    emf.unwrap(SessionFactory.class);

Statistics stats = sessionFactory.getStatistics();

System.out.println(
    "Entity inserts=" + stats.getEntityInsertCount()
);

System.out.println(
    "Flushes=" + stats.getFlushCount()
);

System.out.println(
    "Prepared statements=" +
        stats.getPrepareStatementCount()
);
```

Giải thích:
- Entity insert count đo hoạt động ORM theo metrics semantics, không phải committed business rows.
- Flush count không bằng commit count.
- Prepared statement count không bằng JDBC network round trips.
- SessionFactory statistics là shared/global, test song song có thể nhiễu.

Một transaction rollback vẫn có thể góp phần vào một số counts vì ORM đã thực thi nhiều hành động trước rollback. Tên counters cần được hiểu theo Hibernate version/implementation.

### 34.1. Đo business success ở ranh giới phù hợp

Muốn metric `orders_committed_total`, hãy cập nhật nó sau **successful transaction completion** hoặc dẫn xuất từ committed outbox/business state, tùy độ tin cậy cần.

Không lấy `getEntityInsertCount()` rồi gọi nó là “orders đã tạo thành công”.

## 35. Bật transaction traces trong Spring khi cần

Trong môi trường chẩn đoán:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.orm.jpa.JpaTransactionManager=DEBUG
logging.level.org.springframework.transaction.interceptor=TRACE
```

Các category và chi tiết log tùy Spring version/transaction manager. Có thể có những thông điệp về:
- Creating transaction.
- Joining existing transaction.
- Suspending/resuming transaction.
- Committing.
- Rolling back.
- Marked rollback-only.

Nếu dùng `DataSourceTransactionManager`, JTA manager hoặc custom transaction manager, nên xem logger của implementation tương ứng. **Đừng suy từ một log “Initiating transaction commit” rằng commit đã thành công**; phải quan sát completion/outcome.

### 35.1. Cẩn thận thứ tự log trong môi trường async

Log appenders có thể bất đồng bộ. Dòng xuất hiện trên một sink có thể bị trễ hoặc sắp xếp khác với thời điểm sự kiện thật, đặc biệt khi nhiều threads/nodes ghi log tập trung.

Dùng timestamp có độ chính xác phù hợp, trace IDs và nguồn phát logs để diễn giải, không chỉ thứ tự dòng hiển thị.

## 36. Test 1 — `flush()` rồi rollback: SQL có, row không

Một test JPA resource-local minh họa:

```java
@Test
void flushedInsertIsNotCommittedAfterRollback() {
    Long id;

    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        PurchaseOrder order = new PurchaseOrder(
            42L, new BigDecimal("100.00")
        );

        em.persist(order);
        em.flush();

        id = order.getId();

        assertNotNull(id);

        tx.rollback();
    } finally {
        if (tx.isActive()) {
            tx.rollback();
        }
        em.close();
    }

    EntityManager verify = emf.createEntityManager();

    try {
        assertNull(
            verify.find(PurchaseOrder.class, id)
        );
    } finally {
        verify.close();
    }
}
```

Đây là test body minh họa; cần JUnit imports, fixture `emf`, migrations và seeded schema phù hợp.

Kết luận kiểm chứng:
- SQL INSERT có thể được log ở flush.
- Hibernate đã có ID.
- Transaction rollback.
- Một EntityManager mới không tìm thấy row committed.

### 36.1. Vì sao dùng EntityManager mới?

Nếu kiểm tra ngay trong cùng Persistence Context, identity map có thể trả một object managed/detached mà không phản ánh committed DB state. Dùng context/transaction mới để kiểm chứng.

## 37. Test 2 — Commit thành công rồi transaction khác mới thấy row

Flow:
1. Begin transaction T1.
2. Persist Order#101.
3. Flush trong T1.
4. Dùng transaction/connection T2 đọc Order#101 ở READ COMMITTED trước commit T1.
5. Assert chưa thấy row.
6. Commit T1.
7. Dùng một transaction READ COMMITTED mới để đọc.
8. Assert đã thấy row.

Sơ đồ:

```text
T1: BEGIN -> persist -> flush -----------------> COMMIT
T2:                     SELECT -> no row
T3:                                              SELECT -> row
```

Thực hiện với **hai physical connections** nếu cần để chứng minh isolation. Đừng vô tình reuse cùng thread-bound connection cho T2 thông qua Spring transaction participation.

### 37.1. Dùng Testcontainers phù hợp

Với PostgreSQL production, test trên PostgreSQL container:
- DB isolation.
- FK deferred constraints.
- JDBC batching.
- ID generation.
- Transaction errors.

Không dùng một H2 in-memory test để khẳng định behavior cụ thể của PostgreSQL deferred FK/identity/locking.

## 38. Test 3 — SQL đã log nhưng commit thất bại

Dùng bảng `children` có deferred FK ở mục 17:

```java
EntityTransaction tx = em.getTransaction();
tx.begin();

try {
    em.createNativeQuery("""
        insert into children(id, parent_id)
        values (1, 999)
        """).executeUpdate();

    // Với constraint INITIALLY DEFERRED,
    // SQL INSERT có thể thành công ở đây.

    tx.commit(); // Có thể ném exception do FK ở commit.
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    // Không tiếp tục dùng EntityManager như chưa có lỗi.
    throw ex;
}
```

Sau lỗi, mở connection/transaction mới để xác minh row không được commit theo DB outcome. Test phải phân biệt “commit bị DB từ chối xác định” và “application mất network sau commit, outcome uncertain”.

### 38.1. Không test commit bằng cách đợi một log line

Test nên assert database state hoặc transaction outcome. Một SQL logger message là tín hiệu hỗ trợ debug, không phải business correctness assertion.

## 39. Test 4 — `REQUIRES_NEW` commit trước outer rollback

Có thể tạo hai Spring beans:

```java
@Service
class AuditWriter {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void logAttempt(String requestId) {
        auditRepository.save(new AuditAttempt(requestId));
    }
}
```

```java
@Service
class OrderWriter {

    private final AuditWriter auditWriter;

    @Transactional
    public void createAndFail() {
        orderRepository.save(new PurchaseOrder(...));

        auditWriter.logAttempt("req-123");

        throw new IllegalStateException("outer rollback");
    }
}
```

`AuditAttempt`, constructor và repositories là application fixtures cần triển khai.

Khi test:
- Assert outer order không tồn tại sau rollback.
- Assert inner audit attempt tồn tại nếu REQUIRES_NEW đã commit thành công.
- Xem transaction traces để biết T2 là transaction mới.
- Không chạy assertions trong cùng test transaction bị rollback hoặc cache context cũ.

**Kết quả này nhắc rằng “log SQL nằm cùng request” không đồng nghĩa SQL thuộc cùng transaction.**

## 40. Test 5 — Spring `@Transactional` test thường rollback mặc định

Với Spring Test:

```java
@SpringBootTest
@Transactional
class OrderServiceTest {
    @Test
    void createOrder() {
        orderService.createOrder();
    }
}
```

Test-managed transaction thông thường được rollback sau test theo Spring TestContext rules. Khi test kết thúc, SQL đã log có thể vẫn không còn row trong DB.

Nếu muốn kiểm tra **commit thực sự**, dùng:
- Một integration test không có outer `@Transactional` test wrapper.
- Hoặc API Spring Test `TestTransaction`/`@Commit`/`@Rollback(false)` có kiểm soát.
- Hoặc RESOURCE_LOCAL/JDBC transaction boundary tường minh trong một test fixture phù hợp.

Không dùng `@Rollback(false)` bừa bãi cho toàn suite vì có thể làm các test ảnh hưởng lẫn nhau.

## 41. Những chẩn đoán sai phổ biến

| Quan sát | Kết luận sai | Cách hiểu đúng |
| --- | --- | --- |
| `Hibernate: INSERT ...` xuất hiện | Row đã commit | Chỉ SQL được log; cần transaction outcome |
| `em.persist()` return | DB đã có row durable | ORM managed state, INSERT có thể pending |
| `saveAndFlush()` return | Đã commit | Flush khác commit |
| `@PostPersist` chạy | Đã hoàn tất transaction | Có thể rollback sau callback |
| ID `order.getId()` khác null | Order đã tạo thành công | ID cấp không đồng nghĩa commit |
| `getEntityInsertCount()` tăng | Có một committed order | Counter ORM không phải business commit metric |
| SQL SELECT không xuất hiện | Không hề đọc entity | Có thể lấy từ L1/L2 |
| SQL INSERT xuất hiện trước SELECT | Người khác phải thấy row | Trong transaction khác có isolation |
| `executeUpdate()` trả 10 | 10 rows đã commit | Affected rows trong transaction; rollback vẫn có thể |
| 100 SQL lines | 100 JDBC round trips | Batching/driver behavior khác |
| `commit()` bắt đầu | Commit thành công | Cần completion/outcome |
| Method body log “done” | @Transactional đã commit | Proxy còn phải commit sau method return |
| `@Transactional` inner method có annotation | Tự tạo tx riêng | Self-invocation có thể bypass proxy |
| `REQUIRES_NEW` SQL cùng trace ID | Cùng transaction ngoài | Inner physical transaction riêng |
| Query thấy row sau flush trong cùng tx | Row đã visible toàn hệ thống | Own writes visible trong transaction không đồng nghĩa external visibility |
| DB statement log có INSERT | Không thể rollback | Statement log không phải commit log |
| SQL lỗi ở commit sau flush thành công | Hibernate flush hỏng | Deferred constraint/tx outcome có thể lỗi muộn |
| Commit method ném network timeout | Chắc chắn rollback | Có thể outcome unknown, cần reconciliation |
| `TRACE` bind log không thấy | SQL không có params | Logger category/version chưa đúng hoặc level/filter |
| SQL có trong JVM log | DB nhận SQL chắc chắn | Log có thể trước JDBC execute hoặc error |
| “Transaction committed” log từ app tự viết trước commit | DB đã commit | Log placement sai |
| Outbox INSERT đã log | Event sẵn sàng publish | Phải đợi outbox row committed |
| SQL log mất sau restart | DB thay đổi bị mất | Logging và DB durability không gắn nhau |

## 42. Quy trình chẩn đoán “Có SQL log nhưng không thấy dữ liệu”

**Bước 1 — Xác định transaction boundary.** Xem `@Transactional`, JTA/resource-local, propagation, test-managed transaction và connection manager.

**Bước 2 — Xác nhận SQL log thuộc request nào.** Dùng trace/request ID và time window, không chỉ thread hoặc SQL text.

**Bước 3 — Phân biệt persist/flush/execute.** Có explicit flush không? Có IDENTITY không? Có query auto-flush không?

**Bước 4 — Kiểm tra exception sau SQL.** Constraint errors, optimistic locking, JDBC batch errors, deadlock hoặc lỗi commit.

**Bước 5 — Kiểm tra rollback-only.** Một inner method có thể đánh dấu transaction rollback-only rồi outer method vẫn return bình thường trước khi commit ném exception.

**Bước 6 — Kiểm tra propagation.** `REQUIRES_NEW`/`NESTED`/suspended transaction có thể khiến SQL logs xen kẽ.

**Bước 7 — Kiểm tra connection và datasource.** App có đang ghi primary DB nhưng query kiểm tra đọc replica/staging DB/schema/tenant khác không?

**Bước 8 — Kiểm tra isolation.** Một transaction khác đang giữ snapshot cũ hoặc read replica chưa replay commit.

**Bước 9 — Loại trừ L1/L2/query cache.** Dùng EntityManager mới; nếu cần, đọc trực tiếp DB bằng connection có quyền thích hợp.

**Bước 10 — Đối chiếu SQL/JDBC metrics.** SQL log vs actual JDBC execution/batching và DB errors.

**Bước 11 — Kiểm tra event side effects.** `@PostPersist`, after-commit callback, outbox và broker publish có thể thuộc các mốc khác nhau.

**Bước 12 — Thiết kế kết luận an toàn.** Nếu commit outcome chưa rõ vì network timeout, không retry non-idempotent command vô điều kiện.

**Bước 13 — Bổ sung integration test.** Test rollback-after-flush, deferred constraint, propagation và committed visibility trên DBMS thật.

## 43. Câu hỏi thực hành

### Bài 1 — Gọi persist chưa có INSERT

```java
tx.begin();
em.persist(new PurchaseOrder(...));
System.out.println("after persist");
tx.commit();
```

Log `after persist` xuất hiện trước INSERT. Có bất thường không?

**Đáp án:** Không. Với SEQUENCE/flush-on-commit, Hibernate có thể hoãn INSERT đến flush ở commit.

### Bài 2 — IDENTITY

Với `GenerationType.IDENTITY`, INSERT xuất hiện ngay trong `persist`. Có chắc row đã commit?

**Đáp án:** Không. INSERT sớm để lấy generated ID vẫn nằm trong transaction và có thể rollback.

### Bài 3 — `saveAndFlush`

Service `@Transactional` gọi `saveAndFlush` rồi ném unchecked exception. SQL đã in. Row có còn sau request không?

**Đáp án:** Thông thường không nếu transaction rollback thành công.

### Bài 4 — `@PostPersist`

`@PostPersist` gửi email, transaction sau đó rollback. Email có tự thu hồi không?

**Đáp án:** Không. Email là external side effect; dùng outbox nếu yêu cầu reliable notification sau commit.

### Bài 5 — Auto-flush

Vì sao SQL INSERT xuất hiện trước một SELECT count dù chưa gọi `flush()`?

**Đáp án:** Hibernate `AUTO` mode có thể flush pending changes trước JPQL/HQL query liên quan.

### Bài 6 — JDBC batch

Có 250 log lines INSERT, `hibernate.jdbc.batch_size=25`. Có thể kết luận 250 JDBC round trips không?

**Đáp án:** Không. Driver có thể gom statements thành batches; cần JDBC/driver/DB metrics.

### Bài 7 — Deferred FK

INSERT child thiếu parent được log và flush không lỗi, nhưng commit ném FK violation. Có mâu thuẫn không?

**Đáp án:** Không. FK được khai báo deferred có thể chỉ được kiểm tra tại commit.

### Bài 8 — Isolation

T1 flush Order#101. T2 READ COMMITTED SELECT trước commit T1 không thấy Order#101. Tại sao?

**Đáp án:** T2 không thấy uncommitted data của T1 trong isolation thông thường.

### Bài 9 — Spring service

Dòng `"service returned"` cuối method `@Transactional` xuất hiện trước log COMMIT. Có nghĩa client đã nhận success?

**Đáp án:** Không. Target method return về Spring proxy; proxy còn commit trước khi trả về caller.

### Bài 10 — `REQUIRES_NEW`

Audit inner transaction commit, outer transaction rollback. Vì sao audit row vẫn có trong DB?

**Đáp án:** Inner dùng transaction vật lý riêng và đã commit trước, không bị rollback bởi outer.

### Bài 11 — Query không log SQL

Hai lần `em.find()` cùng ID trong cùng Persistence Context, lần hai không có SELECT. Có thể vẫn có entity không?

**Đáp án:** Có. L1 identity map có thể trả managed entity trực tiếp.

### Bài 12 — Timeout lúc commit

Application gửi COMMIT, mất kết nối rồi ném exception. Có nên tạo lại order ngay?

**Đáp án:** Không nếu thiếu idempotency. Outcome có thể chưa rõ; kiểm tra committed state theo request ID và retry an toàn.

### Bài 13 — SQL log và bind log

SQL logger chỉ thấy `values (?, ?)`. Bật category nào trong Hibernate 6/7 để xem bind values?

**Đáp án:** `org.hibernate.orm.jdbc.bind=TRACE` trong môi trường chẩn đoán có kiểm soát, vì có thể chứa PII.

### Bài 14 — Spring Test

Test `@Transactional` chạy xong và log INSERT nhưng DB rỗng. Vì sao?

**Đáp án:** Spring test transaction thường tự rollback sau test.

### Bài 15 — Envers

Audit INSERT SQL xuất hiện nhưng transaction rollback. Có revision bền vững không?

**Đáp án:** Không nếu audit records cùng transaction đã rollback; SQL log không chứng minh audit committed.

### Bài 16 — Metric

`getEntityInsertCount()` tăng 5. Có thể tăng `orders_committed_total` thêm 5 không?

**Đáp án:** Không. ORM counter không bảo đảm 5 business orders đã commit thành công.

### Bài 17 — Native SQL

`executeUpdate()` trả 1. `tx.rollback()` được gọi sau đó. UPDATE có được giữ không?

**Đáp án:** Không, nếu transaction rollback thành công và SQL thuộc đúng transaction đó.

### Bài 18 — After-commit callback

`@TransactionalEventListener(AFTER_COMMIT)` chạy sau DB commit. Có đảm bảo message broker nhận được event dù JVM crash không?

**Đáp án:** Không. Cần durable outbox/CDC và retry/idempotency.

### Bài 19 — Two databases

Hibernate SQL log nói INSERT, nhưng DBA query database khác. Có thể thấy không?

**Đáp án:** Không. Xác minh datasource URL, schema, tenant, primary/replica và credentials.

### Bài 20 — Logging order

Log async hiển thị `"commit complete"` trước một SQL line cũ. Có chắc SQL chạy sau commit không?

**Đáp án:** Không. Appenders/collectors có thể reorder hoặc delay messages. Dùng correlation IDs và instrumentation theo sự kiện thực.

## 44. Tài liệu tham khảo chính thức

- [Hibernate ORM User Guide — Flushing](https://docs.hibernate.org/orm/7.2/userguide/html_single/#flushing): flush modes, AUTO/COMMIT/MANUAL, entity state synchronization và query-triggered flush.
- [Hibernate ORM User Guide — Persistence Context](https://docs.hibernate.org/orm/7.2/userguide/html_single/#pc): managed state, dirty checking, first-level cache.
- [Hibernate ORM User Guide — Batch processing](https://docs.hibernate.org/orm/7.2/userguide/html_single/#batch): JDBC batching và batch processing.
- [Hibernate ORM 7.1 — A Short Guide, Logging SQL](https://docs.hibernate.org/orm/7.1/introduction/html_single/#logging-generated-sql): `hibernate.show_sql`, `org.hibernate.SQL`, JDBC bind/extract/batch loggers.
- [Hibernate ORM 7.1 — Logging categories](https://docs.hibernate.org/orm/7.1/logging/logging.html): các Hibernate logging categories.
- [Hibernate ORM Javadocs — `Session.flush()`](https://docs.hibernate.org/orm/current/javadocs/org/hibernate/Session.html): đồng bộ state và transaction flush behavior.
- [Hibernate ORM User Guide — Transactions](https://docs.hibernate.org/orm/7.2/userguide/html_single/#transactions): JDBC/JTA transaction management.
- [Hibernate ORM User Guide — Identifiers](https://docs.hibernate.org/orm/7.2/userguide/html_single/#identifiers): SEQUENCE, IDENTITY và generated key timing.
- [Hibernate ORM User Guide — Statistics](https://docs.hibernate.org/orm/7.2/userguide/html_single/#statistics): ORM metrics và session statistics.
- [Jakarta Persistence 3.2 Specification](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html): persist, flush, transaction lifecycle và bulk DML.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): `@Transactional`, rollback rules, proxy mode và propagation.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRED`, `REQUIRES_NEW`, `NESTED`.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener` và `AFTER_COMMIT`.
- [Spring Framework Javadoc — `TransactionSynchronization`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html): `afterCommit`, `afterCompletion` và outcome statuses.
- [Spring Data JPA — Persisting Entities](https://docs.spring.io/spring-data/jpa/reference/jpa/entity-persistence.html): `save`, `persist` và `merge`.
- [PostgreSQL — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): visibility, snapshots và isolation semantics.
- [PostgreSQL — SET CONSTRAINTS](https://www.postgresql.org/docs/current/sql-set-constraints.html): deferred constraint checks.
- [PostgreSQL — Foreign Keys](https://www.postgresql.org/docs/current/ddl-constraints.html): FK constraints, deferred checks và referential integrity.
- [Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html): durable messaging sau commit qua outbox, retry và idempotency.

**Giới hạn phiên bản:** SQL logger category, generated ID behavior, query flush rules, JDBC batch implementation và transaction instrumentation phụ thuộc Hibernate/Spring/driver/DBMS version. Các ví dụ deferred FK, sequence syntax và isolation lấy PostgreSQL làm ngữ cảnh. Không suy từ một câu SQL trong JVM log rằng database đã thực thi hoặc commit thành công; hãy xác minh bằng outcome instrumentation và integration tests trên đúng stack.

## Kết luận

**SQL được log là một dấu hiệu quan sát trong quá trình Hibernate làm việc với JDBC, không phải dấu mốc giao dịch hoàn tất.** `persist()` có thể chỉ đưa entity vào Persistence Context; `flush()` đồng bộ pending changes xuống database; JDBC có thể thực thi statement hoặc batch; nhưng **chỉ commit thành công mới xác nhận thay đổi trong transaction đã được chấp nhận**, và khả năng transaction khác nhìn thấy dữ liệu còn phụ thuộc isolation, cache và replication.

SQL có thể xuất hiện sớm vì `IDENTITY` hoặc auto-flush trước query, xuất hiện muộn trong flush-on-commit, hoặc xuất hiện nhiều lần do JDBC batching/rollback/retry. Một `INSERT` đã log vẫn có thể bị rollback; một `flush()` thành công vẫn có thể gặp lỗi deferred constraint khi commit; một commit timeout đôi khi để lại outcome chưa rõ.

Khi chẩn đoán, hãy ghép **request/trace ID, flush events, JDBC execution metrics, transaction-manager commit/rollback outcomes và database state** thay vì chỉ đếm SQL lines. Và khi cần phát business event sau khi dữ liệu thật sự bền vững, đừng dùng `@PostPersist`/SQL log như commit callback: ưu tiên transaction-aware completion cho thông báo không critical, hoặc transactional outbox với idempotency cho luồng liên hệ thống cần độ tin cậy cao.
