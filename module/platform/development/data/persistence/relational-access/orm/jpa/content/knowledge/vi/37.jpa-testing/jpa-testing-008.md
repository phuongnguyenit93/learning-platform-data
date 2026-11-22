# Kiểm thử commit, rollback và trạng thái entity sau lỗi

Một phép kiểm thử JPA có thể **pass dù không có dữ liệu nào được commit**. Lý do là JPA có *persistence context* chứa các entity đang được quản lý, còn database sử dụng transaction để quyết định thay đổi nào được lưu bền vững và thay đổi nào phải hoàn tác.

Ví dụ dễ gây hiểu nhầm:

```java
EntityManager em = emf.createEntityManager();
em.getTransaction().begin();

Invoice invoice = new Invoice(
    101L, 7L, "INV-101", new BigDecimal("150.00")
);

em.persist(invoice);
em.flush();

assertNotNull(em.find(Invoice.class, 101L));

// Chưa có commit.
em.getTransaction().rollback();
em.close();
```

Assertion trong cùng `EntityManager` có thể thành công vì Invoice đang nằm trong first-level cache. Lệnh `flush()` có thể đã gửi `INSERT` tới database, nhưng `rollback()` cuối cùng vẫn hủy thay đổi. Một test thật sự kiểm tra commit phải **hoàn tất transaction rồi đọc bằng persistence context mới**; một test rollback phải chứng minh dữ liệu không còn ở trạng thái committed, thay vì chỉ xem Java object.

Bài **“Kiểm thử commit, rollback và trạng thái entity sau lỗi”**, thuộc chương **Kiểm thử JPA** trong chủ đề **Data Persistence Relational Access ORM JPA**, trình bày cách tổ chức integration tests để xác minh:

- Các mốc `persist`, `flush`, `commit`, `rollback` và database visibility.
- Trạng thái `new`, `managed`, `removed`, `detached` của entity trước và sau transaction.
- Điều gì xảy ra với object Java, ID, version và persistence context khi transaction thất bại.
- Cách phân loại lỗi `PersistenceException`, constraint violation, `OptimisticLockException`, Bean Validation và transaction rollback-only.
- Cách test đúng bằng JUnit 5, Jakarta Persistence, PostgreSQL/Testcontainers.
- Cách áp dụng trong Spring Data JPA với `@Transactional`, `@DataJpaTest`, `TestTransaction` và transaction propagation.
- Cách xây test chống false positive, chống rò dữ liệu và có thể tái lập trên CI.

Ví dụ dùng Jakarta Persistence 3.x (`jakarta.persistence`) và Java 17+. Các chi tiết ở PostgreSQL như SQLState `23505`/`23514` và hành vi constraint được ghi chú riêng. Với JPA cũ sử dụng `javax.persistence`, cần điều chỉnh namespace và phiên bản thư viện. Những thời điểm SQL được phát có thể thay đổi theo JPA provider, ID generation strategy, flush mode và constraint deferral; **không mặc định một câu SQL luôn xuất hiện đúng tại một lời gọi Java duy nhất**.

---

## 1. Ba lớp trạng thái cần phân biệt

Khi nói “đã lưu entity”, phải tách ba câu hỏi:

1. **Trạng thái Java object:** field của `invoice` hiện mang giá trị nào?
2. **Trạng thái persistence context:** `invoice` có được `EntityManager` quản lý không, dirty checking có theo dõi nó không?
3. **Trạng thái committed database:** một transaction khác, với visibility thích hợp, có nhìn thấy row và giá trị đó không?

Ba lớp không nhất thiết giống nhau.

```text
Java object                      Persistence context                  Database
    │                                   │                                 │
invoice.amount = 150              managed Invoice #101                 chưa có row
    │                                   │                                 │
em.persist(invoice)         đăng ký entity mới                       chưa chắc INSERT
    │                                   │                                 │
em.flush()                  đồng bộ pending state                      INSERT chưa commit
    │                                   │                                 │
rollback()                  context không còn đáng tin                 INSERT hoàn tác
    │                                   │                                 │
invoice.amount vẫn 150             không suy managed state              không có row 101
```

**Rollback của database không tua ngược các phép gán field trên Java object.** Một object còn `id` và `amount` sau rollback không phải bằng chứng row được lưu.

## 2. `persist()`, `flush()`, `commit()` khác nhau thế nào?

| Thao tác | Mục tiêu | Không bảo đảm |
| --- | --- | --- |
| `em.persist(entity)` | Đưa entity mới vào persistence context | Không bảo đảm transaction đã commit |
| `em.flush()` | Đồng bộ pending changes với database trong transaction | Không commit, không đảm bảo transaction sẽ commit thành công |
| `em.getTransaction().commit()` | Hoàn tất resource-local transaction, thường flush pending work | Có thể ném lỗi; không phải lúc nào cũng thành công |
| `em.getTransaction().rollback()` | Hoàn tác database changes của transaction | Không khôi phục các Java fields về giá trị cũ |
| `em.find(Entity.class,id)` | Tìm entity trong context/DB theo contract | Nếu entity đã managed, không nhất thiết query database lại |
| `em.clear()` | Detach toàn bộ managed entities | Không rollback SQL đã flush; có thể làm mất pending changes chưa flush |
| `em.close()` | Giải phóng EntityManager | Không phải API để commit hoặc rollback transaction |

Thời điểm `INSERT` có thể bị đẩy sớm nếu provider cần generated identity (`IDENTITY`), hoặc được trì hoãn tới flush/commit. Vì vậy test **nên khẳng định kết quả tại transaction boundary** hơn là giả định thứ tự SQL giống nhau trên mọi provider.

## 3. Transaction timeline: thành công và thất bại

Đường thành công:

```text
begin
  │
persist(invoice)
  │
flush()           → SQL INSERT/UPDATE có thể được gửi
  │
commit()          → DB xác nhận transaction
  │
close EntityManager
  │
open new EntityManager
  │
find(invoiceId)   → có row committed
```

Đường thất bại:

```text
begin
  │
persist(invoice)
  │
flush()           → SQL có thể đã được gửi
  │
business failure hoặc DB constraint failure
  │
rollback()        → DB không commit transaction
  │
close EntityManager
  │
open new EntityManager
  │
find(invoiceId)   → không có row được tạo bởi transaction lỗi
```

Với lỗi ở `commit()`, transaction có thể đã được đánh dấu rollback-only từ trước hoặc database phát hiện constraint deferred tại completion. **Bắt exception tại `flush()` thôi chưa đủ để kết luận commit sẽ thành công.**

## 4. Bốn trạng thái entity quan trọng

Một JPA entity có thể được xem ở các trạng thái lifecycle:

- **New/transient:** object mới tạo, chưa có persistent identity được context quản lý.
- **Managed/persistent:** đang được một persistence context quản lý; thay đổi có thể được phát hiện và đồng bộ.
- **Removed:** entity được đánh dấu xóa trong context; SQL DELETE có thể được gửi ở flush.
- **Detached:** từng có persistent identity nhưng không còn được một persistence context quản lý.

Sơ đồ thông dụng:

```text
new --persist()--> managed --remove()--> removed
                       │                   │
                       │ detach()/clear()  │ rollback/close semantics
                       │ hoặc close        │ phải xem transaction
                       ▼                   │
                    detached <─────────────┘

detached --merge()--> managed COPY mới hoặc instance managed hiện có
```

Sơ đồ là trực giác lifecycle; chính xác trạng thái sau rollback và completion chịu semantics JPA/provider. **Không dùng lại persistence context đã thất bại như thể mọi entity trở về trạng thái sạch.**

### `merge()` không làm detached object thành managed object gốc

```java
Invoice managedCopy = em.merge(detachedInvoice);

assertNotSame(detachedInvoice, managedCopy);
```

`merge()` sao chép trạng thái sang instance managed (có thể là entity đã tồn tại trong context), trả về reference managed. Object `detachedInvoice` truyền vào **không tự trở thành managed**. Sau lỗi merge hoặc rollback, đừng tiếp tục ghi vào object cũ rồi giả định ORM sẽ flush.

---

## 5. Mô hình Invoice cho các integration tests

Dùng một bảng hóa đơn đơn giản để quan sát commit, rollback và version.

```java
package com.example.jpa;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.math.BigDecimal;

@Entity
@Table(name = "invoices")
public class Invoice {

    @Id
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "invoice_no", nullable = false, length = 50)
    private String invoiceNo;

    @Column(name = "total_amount",
            nullable = false, precision = 12, scale = 2)
    private BigDecimal totalAmount;

    @Enumerated(EnumType.STRING)
    @Column(name = "state", nullable = false, length = 20)
    private InvoiceState state;

    @Version
    @Column(name = "version", nullable = false)
    private Long version;

    protected Invoice() {}

    public Invoice(
            Long id, Long tenantId, String invoiceNo,
            BigDecimal totalAmount) {
        this.id = id;
        this.tenantId = tenantId;
        this.invoiceNo = invoiceNo;
        this.totalAmount = totalAmount;
        this.state = InvoiceState.DRAFT;
    }

    public Long getId() { return id; }
    public Long getTenantId() { return tenantId; }
    public String getInvoiceNo() { return invoiceNo; }
    public BigDecimal getTotalAmount() { return totalAmount; }
    public InvoiceState getState() { return state; }
    public Long getVersion() { return version; }

    public void changeAmount(BigDecimal newAmount) {
        this.totalAmount = newAmount;
    }

    public void approve() {
        this.state = InvoiceState.APPROVED;
    }
}
```

Enum:

```java
package com.example.jpa;

public enum InvoiceState {
    DRAFT,
    APPROVED
}
```

Không gắn `@DecimalMin` ở đây để bài test về DB `CHECK` có thể quan sát lỗi database; một domain model thật vẫn nên kiểm tra nghiệp vụ ở lớp Java và giữ CHECK như hàng rào sau cùng.

### Vì sao dùng ID do ứng dụng cấp?

Ví dụ dùng `id = 101L` thay vì generated ID để dễ khẳng định. Với `GenerationType.IDENTITY`, INSERT có thể xảy ra sớm trong `persist()` và một ID đã cấp có thể **không được thu hồi sau rollback**. Không viết test giả định ID sequence không có gaps sau transaction failure.

## 6. Migration schema thử nghiệm

Ví dụ PostgreSQL:

```sql
CREATE TABLE invoices (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    invoice_no VARCHAR(50) NOT NULL,
    total_amount NUMERIC(12,2) NOT NULL,
    state VARCHAR(20) NOT NULL,
    version BIGINT NOT NULL,

    CONSTRAINT uq_invoice_tenant_number
        UNIQUE (tenant_id, invoice_no),

    CONSTRAINT ck_invoice_nonnegative_amount
        CHECK (total_amount >= 0),

    CONSTRAINT ck_invoice_state
        CHECK (state IN ('DRAFT', 'APPROVED'))
);
```

Mục tiêu:

- Kiểm tra `INSERT`/`UPDATE` thành công.
- Tạo deliberate unique-key failure.
- Tạo deliberate CHECK failure.
- Kiểm tra optimistic version.
- Quan sát rollback không làm biến mất committed row cũ.
- Bảo vệ dữ liệu kể cả khi writers dùng JDBC/native SQL.

Schema cần được tạo qua Flyway/Liquibase hoặc migration fixture có version, **không phải copy thủ công một phiên bản DDL yếu hơn production**.

## 7. Tại sao dùng database thật thay vì chỉ mock?

Mockito mock `EntityManager` có thể kiểm tra method được gọi, nhưng không chứng minh:

- `flush()` gửi SQL thật.
- DB UNIQUE/CHECK/FK từ chối thay đổi.
- `commit()` thực sự ghi dữ liệu.
- `rollback()` hoàn tác SQL.
- Two-transaction isolation/visibility.
- Optimistic version conflict.
- EntityManager state sau provider failure.
- Transaction manager xử lý rollback-only.

Để xác minh những thứ đó cần **JPA provider + database + transaction thật**.

Một database trong bộ nhớ có thể đủ cho mapping tests đơn giản, nhưng kiểm tra PostgreSQL SQLState, locking, deferred constraints và concurrency nên chạy trên PostgreSQL hoặc cùng loại database production.

---

## 8. Cấu hình persistence unit cho JUnit

File `src/test/resources/META-INF/persistence.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    version="3.1">

    <persistence-unit
        name="invoice-test"
        transaction-type="RESOURCE_LOCAL">

        <provider>
            org.hibernate.jpa.HibernatePersistenceProvider
        </provider>

        <class>com.example.jpa.Invoice</class>
        <exclude-unlisted-classes>true</exclude-unlisted-classes>

        <properties>
            <property
                name="hibernate.hbm2ddl.auto"
                value="validate"/>
        </properties>
    </persistence-unit>
</persistence>
```

Ở đây `hibernate.hbm2ddl.auto=validate` là Hibernate-specific: provider kiểm tra một số đặc điểm mapping/schema, không tự tạo tables. Migrations phải chạy **trước khi** bootstrap factory. Validation này **không thay thế** tests cho UNIQUE/CHECK/FK/indexes.

Ví dụ dùng `RESOURCE_LOCAL` để có thể gọi `em.getTransaction().begin()/commit()/rollback()`. Trong Spring/JTA, transaction manager sở hữu completion; không sao chép resource-local API vào managed services.

## 9. JUnit 5 + Testcontainers + Flyway: fixture mẫu

Một integration test class:

```java
package com.example.jpa;

import jakarta.persistence.*;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.*;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import java.math.BigDecimal;
import java.util.Map;
import java.util.function.Consumer;

import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
class InvoicePersistenceIT {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    private static EntityManagerFactory emf;

    @BeforeAll
    static void init() {
        Flyway.configure()
            .dataSource(
                postgres.getJdbcUrl(),
                postgres.getUsername(),
                postgres.getPassword()
            )
            .locations("classpath:db/migration")
            .load()
            .migrate();

        Map<String, Object> properties = Map.of(
            "jakarta.persistence.jdbc.url",
            postgres.getJdbcUrl(),
            "jakarta.persistence.jdbc.user",
            postgres.getUsername(),
            "jakarta.persistence.jdbc.password",
            postgres.getPassword(),
            "jakarta.persistence.jdbc.driver",
            "org.postgresql.Driver",
            "hibernate.hbm2ddl.auto",
            "validate"
        );

        emf = Persistence.createEntityManagerFactory(
            "invoice-test",
            properties
        );
    }

    @AfterAll
    static void shutdown() {
        if (emf != null) {
            emf.close();
        }
    }

    @BeforeEach
    void clean() {
        withTransaction(em -> {
            em.createQuery("DELETE FROM Invoice i")
                .executeUpdate();
        });
    }

    static Invoice invoice(long id, String number) {
        return new Invoice(
            id,
            7L,
            number,
            new BigDecimal("150.00")
        );
    }

    static void withTransaction(Consumer<EntityManager> work) {
        EntityManager em = emf.createEntityManager();
        EntityTransaction tx = em.getTransaction();

        try {
            tx.begin();
            work.accept(em);
            tx.commit();
        } catch (RuntimeException failure) {
            if (tx.isActive()) {
                try {
                    tx.rollback();
                } catch (RuntimeException rollbackError) {
                    failure.addSuppressed(rollbackError);
                }
            }
            throw failure;
        } finally {
            em.close();
        }
    }

    static Invoice readCommitted(Long id) {
        EntityManager fresh = emf.createEntityManager();
        try {
            return fresh.find(Invoice.class, id);
        } finally {
            fresh.close();
        }
    }
}
```

File DDL có thể đặt tại `src/test/resources/db/migration/V1__create_invoices.sql`. Nếu project đã có migrations production, test dùng **cùng nguồn migration production** sẽ phát hiện drift tốt hơn tạo riêng một DDL khác.

Mỗi test dùng EntityManager/transaction riêng. Static container được giữ cho cả test class, và `@BeforeEach` xóa fixtures trước mỗi method; **không chạy tests cùng class song song nếu chúng dùng cleanup chung**. Không dùng cleanup như trên với database shared/production.

### Ghi chú về `readCommitted()`

Helper trả về một entity vừa được load rồi đóng EntityManager. Các basic fields đã nạp có thể đọc để assert, nhưng lazy associations chưa được initialized sẽ không nên truy cập ngoài context. Nếu test muốn kiểm tra lazy state, thực hiện assertions trong một EntityManager còn mở hoặc dùng DTO projection.

---

## 10. Test commit: phải đọc lại sau completion

```java
@Test
void commitPersistsInvoice() {
    withTransaction(em -> {
        Invoice invoice = invoice(101L, "INV-101");
        em.persist(invoice);
        em.flush();
    });

    Invoice committed = readCommitted(101L);

    assertNotNull(committed);
    assertEquals("INV-101", committed.getInvoiceNo());
    assertEquals(InvoiceState.DRAFT, committed.getState());
    assertEquals(
        0,
        committed.getTotalAmount()
            .compareTo(new BigDecimal("150.00"))
    );
}
```

`withTransaction` chạy `commit()` trước khi trả về. `readCommitted` mở context mới nên tránh trả cùng managed object trong context ghi.

Test này chứng minh sau transaction completion, row có thể tìm được theo committed state mà transaction test mới nhìn thấy.

### Vì sao so sánh BigDecimal bằng compareTo?

`BigDecimal.equals` xét cả scale, ví dụ `150.0` và `150.00` có thể không bằng nhau. Với giá trị nghiệp vụ, `compareTo(...) == 0` thường thích hợp hơn khi scale có thể được DB mapping chuẩn hóa. Nếu domain cần bảo toàn scale như một invariant riêng, hãy test scale tường minh.

## 11. Test rollback: SQL đã flush nhưng row không được lưu

Dùng một exception chỉ dành cho test:

```java
static final class AbortTestTransaction extends RuntimeException {
}
```

Test:

```java
@Test
void rollbackDiscardsInsertedRow() {
    assertThrows(
        AbortTestTransaction.class,
        () -> withTransaction(em -> {
            Invoice invoice = invoice(202L, "INV-202");
            em.persist(invoice);
            em.flush();

            // Giả lập lỗi nghiệp vụ sau khi INSERT đã
            // được đồng bộ trong transaction.
            throw new AbortTestTransaction();
        })
    );

    assertNull(readCommitted(202L));
}
```

**Ý nghĩa:** test không chỉ thấy helper gọi `rollback`; nó mở context mới và xác nhận row không được commit. Đây là cách phân biệt rollback thật với một try/catch chỉ sửa Java state.

Test cùng nguyên tắc cho DELETE/UPDATE: sau rollback, readback phải cho thấy giá trị committed trước đó.

## 12. Test rollback UPDATE giữ nguyên giá trị cũ

Seed committed row, sau đó sửa trong transaction nhưng rollback:

```java
@Test
void rollbackRestoresDatabaseAmount() {
    withTransaction(em -> em.persist(
        invoice(301L, "INV-301")
    ));

    assertThrows(
        AbortTestTransaction.class,
        () -> withTransaction(em -> {
            Invoice managed = em.find(
                Invoice.class, 301L
            );

            managed.changeAmount(
                new BigDecimal("999.00")
            );

            em.flush();
            throw new AbortTestTransaction();
        })
    );

    Invoice afterRollback = readCommitted(301L);

    assertNotNull(afterRollback);
    assertEquals(
        0,
        afterRollback.getTotalAmount()
            .compareTo(new BigDecimal("150.00"))
    );
}
```

Điều được xác minh là **database vẫn lưu 150.00**, mặc dù Java object bên trong transaction thất bại đã có 999.00.

Nếu test chỉ `assertEquals(999.00, managed.getTotalAmount())` sau rollback, nó sẽ kiểm tra object đã được sửa trước lỗi, không kiểm tra rollback semantics.

## 13. Test rollback DELETE giữ nguyên row

```java
@Test
void rollbackOfRemoveKeepsPreviouslyCommittedInvoice() {
    withTransaction(em -> em.persist(
        invoice(401L, "INV-401")
    ));

    assertThrows(
        AbortTestTransaction.class,
        () -> withTransaction(em -> {
            Invoice managed = em.find(
                Invoice.class, 401L
            );

            em.remove(managed);
            em.flush();
            throw new AbortTestTransaction();
        })
    );

    assertNotNull(readCommitted(401L));
}
```

Dù `remove` và `flush` đã phát yêu cầu DELETE trong transaction, rollback giữ row đã commit trước đó.

### Cần chú ý cascade

Nếu entity có `CascadeType.REMOVE` hoặc database `ON DELETE CASCADE`, DELETE có thể tác động cả dữ liệu liên quan. Test rollback nên seed cả child rows nếu business invariant yêu cầu toàn bộ aggregate được phục hồi. Đừng chỉ assert root entity rồi bỏ qua linked rows.

---

## 14. Điều gì xảy ra với Java entity sau rollback?

Ví dụ:

```java
Invoice invoice = invoice(501L, "INV-501");

EntityManager em = emf.createEntityManager();

try {
    em.getTransaction().begin();
    em.persist(invoice);
    em.flush();
    em.getTransaction().rollback();
} finally {
    em.close();
}

System.out.println(invoice.getId());        // 501
System.out.println(invoice.getInvoiceNo()); // INV-501
```

Object vẫn có field values; điều đó không tạo row trong DB.

Sau rollback:

- Những giá trị Java đã gán **không tự được hoàn tác**.
- ID được sinh/gán có thể còn trên object.
- Provider có thể đã tăng/đặt version ở memory.
- Entity instances từng managed không nên được coi là đồng bộ với committed DB state.
- Các proxies/collections cũ có thể không dùng được khi context đóng.
- Trạng thái managed/detached/removed sau rollback chịu contract JPA và provider; không giả định EntityManager cũ còn an toàn để tiếp tục.
- Với persistence failure, nên rollback (nếu còn active), đóng context và tạo context mới.

Thực hành an toàn: **không tiếp tục business operation trên graph cũ sau một transaction thất bại**, trừ khi bạn đã thiết kế rõ việc reload/reconstruct state.

## 15. Java object state không đồng nhất database state

Một test sai:

```java
em.getTransaction().begin();

invoice.changeAmount(new BigDecimal("200.00"));
em.getTransaction().rollback();

assertEquals(
    new BigDecimal("200.00"),
    invoice.getTotalAmount()
);
```

Assertion đúng về Java object nhưng không nói gì về DB. Để kiểm tra rollback, mở một EntityManager mới và đọc row committed.

Một test tốt nên đặt tên thể hiện mục tiêu:

- `rollbackDoesNotInsertNewRow()`.
- `rollbackLeavesCommittedPriceUnchanged()`.
- `rollbackOfDeleteKeepsParentAndChildren()`.
- `commitMakesChangesVisibleToNewContext()`.

Tên `saveWorks()` quá mơ hồ để người đọc biết đã kiểm tra boundary nào.

## 16. `contains(entity)` chỉ nói về context hiện tại

`em.contains(invoice)` trả liệu một entity instance có đang được EntityManager đó quản lý hay không. Nó **không xác minh row committed**.

```java
em.getTransaction().begin();

Invoice invoice = invoice(601L, "INV-601");
em.persist(invoice);

assertTrue(em.contains(invoice));

em.getTransaction().rollback();
```

Ngay lúc `contains` true, database vẫn có thể chưa có INSERT. Sau rollback, không giả định kết quả `contains` của EM cũ giống nhau trên mọi provider; test portable tập trung vào **không có row committed trong context mới**.

Khi muốn test lifecycle, xác định rõ mốc transaction và provider behavior mong đợi; đừng dùng `contains` như một phép thay thế DB query.

## 17. Entity state sau `close()`

Sau:

```java
em.close();
```

những entities được quản lý bởi EM đó không còn gắn với một context đang hoạt động. Các basic fields đã được nạp vẫn là Java values, nhưng lazy associations chưa nạp có thể gây `LazyInitializationException` (Hibernate-specific) khi dereference.

Không sửa bằng cách để EM mở xuyên nhiều requests hoặc nhiều tests. Đối với API read-only, chuyển thành DTO/projection trong transaction thích hợp.

---

## 18. Một test `flush()` không chứng minh được `commit()`

Anti-pattern:

```java
@Test
void insertWorks() {
    em.getTransaction().begin();
    em.persist(invoice);
    assertDoesNotThrow(em::flush);

    em.getTransaction().rollback();
}
```

Test này chỉ chứng minh operation đến flush chưa phát exception. Nó **không chứng minh transaction có thể commit**.

Các lỗi có thể xuất hiện sau flush:

- Deferrable database constraints.
- Transaction completion validation/locking.
- Optimistic conflict ở mốc provider quyết định flush.
- Network/database failure lúc commit.
- Transaction đã bị đánh dấu rollback-only.
- Trigger hoặc DB rules phát sinh tại completion.

Khi mục tiêu là kiểm tra commit, phải gọi commit thực sự và readback trong context mới.

## 19. Constraint deferral: lý do exception có thể xuất hiện muộn

Một số database, như PostgreSQL, hỗ trợ deferrable foreign key hoặc unique constraints theo cấu hình. Một constraint được defer có thể không từ chối statement ở `flush()`, nhưng từ chối transaction ở `commit()`.

Ví dụ sơ đồ:

```text
begin
  │
INSERT child with missing parent
  │
flush()  → statement accepted by deferred constraint
  │
commit() → DB checks deferred FK and rejects
  │
rollback/transaction failure
```

**Không khẳng định mọi CHECK/UNIQUE/FK đều deferred**. Cú pháp và loại constraint có thể deferrable khác theo DB. Với PostgreSQL, CHECK không có semantics deferrable giống FK/UNIQUE; test phải dùng schema đúng loại constraint được defer.

Nếu muốn test lỗi tại commit, cần setup constraint và transaction phù hợp. Nếu muốn test lỗi ngay khi SQL được gửi, dùng constraint immediate và gọi flush.

## 20. Test UNIQUE constraint có nguyên nhân cụ thể

Với migration `UNIQUE(tenant_id, invoice_no)`:

```java
@Test
void duplicateInvoiceNumberFailsAndDoesNotCommit() {
    withTransaction(em -> em.persist(
        invoice(701L, "DUP-001")
    ));

    RuntimeException failure = assertThrows(
        RuntimeException.class,
        () -> withTransaction(em -> {
            em.persist(invoice(702L, "DUP-001"));
            em.flush();
        })
    );

    assertTrue(
        hasSqlState(failure, "23505"),
        "Expected PostgreSQL UNIQUE violation"
    );

    assertNotNull(readCommitted(701L));
    assertNull(readCommitted(702L));
}
```

Helper duyệt cause chain:

```java
static boolean hasSqlState(
        Throwable failure,
        String expected) {

    Throwable current = failure;

    while (current != null) {
        if (current instanceof java.sql.SQLException sql
                && expected.equals(sql.getSQLState())) {
            return true;
        }
        current = current.getCause();
    }

    return false;
}
```

`23505` là PostgreSQL unique_violation. Với database khác, loại exception/SQLState có thể khác. **Không chỉ assert bất kỳ RuntimeException nào rồi coi đó là bằng chứng UNIQUE hoạt động**; runtime failure có thể do DB connection, missing table hoặc mapping sai.

### Vì sao phải assert trạng thái database sau failure?

Để chứng minh row ban đầu `701L` vẫn tồn tại và row bị từ chối `702L` không được commit. Đây là phần kiểm tra tính nguyên tử, không chỉ exception classification.

## 21. Test CHECK constraint và rollback

```java
@Test
void negativeAmountCannotBeCommitted() {
    RuntimeException failure = assertThrows(
        RuntimeException.class,
        () -> withTransaction(em -> {
            Invoice invalid = new Invoice(
                801L,
                7L,
                "NEGATIVE",
                new BigDecimal("-1.00")
            );

            em.persist(invalid);
            em.flush();
        })
    );

    assertTrue(
        hasSqlState(failure, "23514"),
        "Expected PostgreSQL CHECK violation"
    );

    assertNull(readCommitted(801L));
}
```

`23514` là PostgreSQL check_violation. Vì ví dụ entity không có Bean Validation `@DecimalMin`, test hướng tới DB CHECK. Nếu một dự án có automatic Bean Validation, validation có thể chặn thay đổi **trước SQL**; khi đó test database CHECK riêng có thể dùng JDBC/native SQL có kiểm soát thay vì tắt toàn bộ validation của ứng dụng.

### Không cố commit tiếp sau lỗi constraint

Khi `flush()` bị DB constraint failure, transaction có thể bị rollback-only hoặc database đặt transaction vào failed state. Helper phải rollback và đóng EntityManager; không tiếp tục persist entity thứ hai trong transaction đã lỗi.

---

## 22. Phân biệt hai loại `ConstraintViolationException`

Tên trùng nhau nhưng thuộc tầng khác:

| Loại | Package điển hình | Nguồn |
| --- | --- | --- |
| Bean Validation violation | `jakarta.validation.ConstraintViolationException` | `@NotNull`, `@Size`, `@DecimalMin` trong Validator/JPA lifecycle |
| Hibernate SQL constraint violation | `org.hibernate.exception.ConstraintViolationException` | DB UNIQUE/FK/CHECK/NOT NULL failure |
| JPA wrapper | `jakarta.persistence.PersistenceException`, `RollbackException` | Provider hoặc transaction boundary |
| Spring translation | `DataIntegrityViolationException` và những loại phù hợp khác | Spring DAO exception translation |

Đừng bắt `jakarta.validation.ConstraintViolationException` để xử lý mọi UNIQUE violation ở database.

Một integration test cần kiểm tra **root cause** nếu mục tiêu là database constraint, không chỉ class exception nhìn thấy ở service boundary.

## 23. Khi Bean Validation chặn trước SQL

Entity:

```java
@NotNull
@DecimalMin("0.00")
private BigDecimal totalAmount;
```

Nếu Jakarta Validation provider được tích hợp vào JPA lifecycle và validation mode thích hợp, `flush()` có thể ném Bean Validation exception trước khi gửi SQL. Trong trường hợp đó:

- Entity state có thể đã được thay đổi ở memory.
- Transaction có thể không còn an toàn để tiếp tục.
- Database CHECK chưa được thực thi trong đường test này.
- Nên tách test Validator behavior và DB integrity test.

Một DB integrity test bằng JDBC trực tiếp dùng schema disposable có thể xác minh CHECK độc lập với JPA callbacks.

**Đừng gọi một test "CHECK database works" nếu nó chỉ đi qua Java Bean Validation.**

## 24. Khi nào provider đánh dấu rollback-only?

Một persistence failure nghiêm trọng có thể làm transaction rollback-only, ví dụ optimistic locking hoặc entity-not-found trong transaction theo JPA contract. Nhiều `PersistenceException` còn lại có quy tắc rollback tương ứng.

Nhưng **không nên gom mọi exception vào một quy tắc tuyệt đối**: một số trường hợp theo JPA như `NoResultException` và `NonUniqueResultException` không nhất thiết làm transaction rollback-only; query/lock timeout có thể mang statement-level thay vì transaction-level semantics.

Vì vậy:

- Đọc contract của exception cụ thể.
- Nếu đã có DB/ORM persistence failure nghiêm trọng, không tiếp tục unit of work cũ.
- Với RESOURCE_LOCAL, có thể kiểm tra `EntityTransaction.getRollbackOnly()` nếu transaction còn active.
- Đừng coi `EntityTransaction.isActive() == true` là bằng chứng commit sẽ thành công.
- Khi test cố tạo lỗi, **rollback và đóng context** là phương án rõ ràng.

## 25. `isActive()` khác `getRollbackOnly()`

```java
EntityTransaction tx = em.getTransaction();

if (tx.isActive()) {
    boolean doomed = tx.getRollbackOnly();
    // true nghĩa transaction được đánh dấu chỉ có thể rollback.
}
```

Một transaction có thể còn active về lifecycle nhưng đã ở trạng thái rollback-only. Nếu thử `commit()`, có thể gặp `RollbackException` hoặc exception khác theo provider/transaction manager.

Không gọi `getRollbackOnly()` bừa bãi khi transaction không active; API có điều kiện sử dụng cụ thể.

Trong Spring/JTA, không dựa vào `em.getTransaction()`; sử dụng transaction manager/test APIs phù hợp.

## 26. Test rollback-only theo nguyên nhân cụ thể

Một skeleton minh họa với optimistic locking:

```java
EntityManager em = emf.createEntityManager();

try {
    em.getTransaction().begin();

    // Tạo tình huống version conflict có kiểm soát.
    // Khi provider phát OptimisticLockException,
    // transaction phải được xử lý như failure.

    // Không tiếp tục lưu dữ liệu khác trong transaction này.
} finally {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    em.close();
}
```

Ở đây không gọi `getRollbackOnly()` trong test giả định vì phần tạo conflict cần thêm hai independent transactions. Test optimistic-lock đầy đủ được trình bày ở phần sau.

**Mục tiêu của test không chỉ là thấy rollback-only**, mà còn xác minh không có thay đổi sai nào được commit.

---

## 27. `OptimisticLockException` và entity version

Với `@Version`:

```java
@Version
private Long version;
```

Provider dùng version để phát hiện ghi đè một state cũ. Ví dụ:

```text
T1: đọc Invoice #1, version=0
T2: đọc Invoice #1, version=0

T1: sửa amount=200, commit → version=1
T2: sửa amount=300, flush/commit → version mismatch
                                   → OptimisticLockException/rollback
```

Chính xác exception được bọc ở `RollbackException` hoặc Spring wrapper tùy boundary. Điều quan trọng là T2 không được silently overwrite T1.

### Optimistic lock không ngăn mọi race

`@Version` bảo vệ optimistic concurrency khi ORM thực hiện version-aware updates theo mapping. Bulk JPQL UPDATE/native SQL thường **không tự tăng/check version như dirty checking thông thường**, nếu không được thiết kế rõ. Test concurrent updates phải thực thi đúng đường ghi production.

## 28. Test optimistic locking bằng hai EntityManagers

Đầu tiên commit một Invoice:

```java
withTransaction(em -> em.persist(
    invoice(901L, "INV-901")
));
```

Sau đó dùng hai contexts:

```java
@Test
void staleUpdateCannotOverwriteCommittedValue() {
    withTransaction(em -> em.persist(
        invoice(901L, "INV-901")
    ));

    EntityManager emA = emf.createEntityManager();
    EntityManager emB = emf.createEntityManager();

    try {
        emA.getTransaction().begin();
        emB.getTransaction().begin();

        Invoice a = emA.find(Invoice.class, 901L);
        Invoice b = emB.find(Invoice.class, 901L);

        a.changeAmount(new BigDecimal("200.00"));
        emA.getTransaction().commit();

        b.changeAmount(new BigDecimal("300.00"));

        RuntimeException failure = assertThrows(
            RuntimeException.class,
            () -> {
                emB.flush();
                emB.getTransaction().commit();
            }
        );

        assertTrue(
            hasCause(failure, OptimisticLockException.class),
            "Expected optimistic version conflict"
        );

    } finally {
        if (emA.getTransaction().isActive()) {
            emA.getTransaction().rollback();
        }
        if (emB.getTransaction().isActive()) {
            emB.getTransaction().rollback();
        }
        emA.close();
        emB.close();
    }

    Invoice committed = readCommitted(901L);

    assertEquals(
        0,
        committed.getTotalAmount()
            .compareTo(new BigDecimal("200.00"))
    );
}
```

Helper:

```java
static boolean hasCause(
        Throwable failure,
        Class<? extends Throwable> expectedType) {

    Throwable current = failure;

    while (current != null) {
        if (expectedType.isInstance(current)) {
            return true;
        }
        current = current.getCause();
    }

    return false;
}
```

**Quan trọng:** test này giữ hai transaction đang hoạt động đồng thời. Trên PostgreSQL, `READ COMMITTED` với two-row versions và không đặt lock đọc trước, thứ tự commit A rồi update B thường phát optimistic conflict. Với database/isolation khác, cần xem khả năng snapshot isolation errors, lock timeouts hoặc provider wrapping; không coi cùng exception class/timing là portable tuyệt đối.

Cũng không được share một EntityManager giữa hai threads để mô phỏng concurrency. Dùng EM riêng và điều phối transaction thật.

## 29. Test optimistic locking không nên dựa vào `Thread.sleep()`

Nếu cần chạy hai threads thật, dùng `CountDownLatch` hoặc synchronization barriers để kiểm soát thứ tự:

```text
Thread A: load version 0 ──────────┐
                                   │ barrier: cả hai đã load
Thread B: load version 0 ──────────┘
                                   │
Thread A: commit amount 200
                                   │ barrier: A đã commit
Thread B: flush/commit amount 300
                                   │
Expected: B conflict, database keeps 200
```

Không dùng `Thread.sleep(500)` rồi hy vọng scheduler sắp đúng thứ tự. Sleep-based concurrency test dễ flaky trên CI.

Với mục tiêu kiểm tra optimistic version, hai EntityManagers trong cùng test thread như ví dụ trước có thể đủ để tạo stale snapshot. Với locking behavior cần concurrency thật, dùng hai threads và DB thật.

---

## 30. Đừng tiếp tục dùng EntityManager sau persistence failure

Anti-pattern:

```java
em.getTransaction().begin();

try {
    em.persist(duplicateInvoice);
    em.flush();
} catch (PersistenceException ex) {
    // Bỏ qua, thử sửa và tiếp tục.
}

em.persist(otherInvoice);
em.getTransaction().commit();
```

Nguy cơ:

- Transaction có thể rollback-only.
- Database transaction đã failed.
- Persistence context có những inserts/updates chưa đồng bộ hoặc không thể phục hồi.
- Provider giữ managed state không khớp committed data.
- Một exception thứ hai che root cause.
- Business code có thể phát event dù không có commit.

Hướng xử lý:

1. Bắt exception ở transaction boundary phù hợp.
2. Rollback nếu transaction còn active.
3. Đóng EntityManager/hủy unit of work thất bại.
4. Ghi nhận cause và request/aggregate IDs an toàn.
5. Nếu business flow cho phép thử lại, **mở transaction và context mới**.
6. Reload current committed state, không tái sử dụng graph cũ.
7. Bảo đảm idempotency trước khi retry thao tác có side effects.

**`em.clear()` không phải một nút sửa transaction đã failed.** Nó detach entities chứ không thay DB rollback, cũng không đảm bảo context/resource state được khôi phục đúng sau lỗi.

## 31. ID và version sau rollback không phải committed state

Một provider có thể đặt ID/version vào entity trước transaction completion:

```java
em.persist(invoice);
em.flush();

Long assignedId = invoice.getId();
Long observedVersion = invoice.getVersion();

em.getTransaction().rollback();
```

Sau rollback, object vẫn có thể giữ `assignedId` và `observedVersion`. Đừng dùng chúng để suy:

- Row tồn tại.
- Version đã được commit.
- Sequence không có gaps.
- Entity còn managed.
- Có thể gọi merge lại mà không xử lý conflict.

Đặc biệt với sequence/identity generation, database có thể cấp ID mà transaction cuối cùng rollback. **Gaps trong ID sequence là bình thường ở nhiều RDBMS**, không phải chứng cứ lỗi giao dịch.

## 32. Detached entity từ transaction thất bại có thể gây lỗi tiếp theo

Giả sử:

```java
Invoice failed = invoice(1101L, "INV-1101");

try {
    withTransaction(em -> {
        em.persist(failed);
        em.flush();
        throw new AbortTestTransaction();
    });
} catch (AbortTestTransaction ignored) {
    // Transaction đã rollback.
}
```

Object `failed` còn values và ID. Nếu code sau đó:

```java
withTransaction(em -> em.merge(failed));
```

nó có thể tạo lại row, update một row khác hoặc phát error tùy entity identity/version/provider semantics. Đây không phải “tiếp tục commit transaction cũ”; là **một operation mới** cần nghiệp vụ cho phép.

Nếu nghiệp vụ muốn retry tạo Invoice, hãy tạo command/data transfer object bất biến, kiểm tra current DB state và xây entity/transaction mới có idempotency key, thay vì tùy tiện merge object cũ.

---

## 33. `remove()` sau rollback khác remove thành công

Entity được `remove` trong transaction:

```java
Invoice managed = em.find(Invoice.class, id);

em.remove(managed);
em.flush();
em.getTransaction().rollback();
```

Trong DB, row đã tồn tại trước transaction vẫn còn. Nhưng Java reference `managed` đã đi qua removed state. Không suy sau rollback nó tự trở về một managed object sạch với mọi quan hệ được khôi phục.

Đọc lại bằng context mới. Nếu cần tiếp tục cập nhật Invoice, load instance mới rồi thực hiện business rule.

## 34. Cascade và orphan removal khi transaction bị rollback

Ví dụ:

```java
@OneToMany(
    mappedBy = "invoice",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<InvoiceLine> lines;
```

Nếu xóa một line khỏi collection và flush, ORM có thể phát DELETE. Rollback sẽ hoàn tác database changes trong transaction, nhưng collection Java vẫn có thể thiếu line đó. Khi dùng lại object graph cũ, nó **không tự đảm bảo phản ánh DB**.

Test cho aggregate cần:

- Seed Invoice + Lines trong committed transaction.
- Thực hiện modification/remove và flush.
- Rollback.
- Mở context mới.
- Query cả Invoice và Lines.
- Assert đầy đủ rows và amounts được phục hồi.
- Không chỉ xem `invoice.getLines().size()` trên Java object đã bị sửa.

L1 object graph và committed aggregate state phải được kiểm tra riêng.

## 35. L1 cache có thể làm test commit pass giả

```java
em.getTransaction().begin();
Invoice i = em.find(Invoice.class, 101L);

i.changeAmount(new BigDecimal("999.00"));

Invoice again = em.find(Invoice.class, 101L);

assertSame(i, again);
assertEquals(
    0,
    again.getTotalAmount()
        .compareTo(new BigDecimal("999.00"))
);
```

Chưa gọi flush hoặc commit mà assertion vẫn có thể pass vì cùng managed instance. Để xác minh DB, hoàn tất transaction rồi dùng new context/JDBC readback.

Với L2 cache, context mới có thể vẫn lấy entity qua shared cache; nếu mục tiêu là chứng minh trực tiếp DB committed state, có thể dùng `emf.getCache().evict(...)` ở test cô lập hoặc JDBC lookup với transaction visibility phù hợp. Không xóa global cache vô tội vạ ở tests song song.

## 36. Một transaction khác có nhìn thấy flush chưa commit không?

Theo isolation level phổ biến như READ COMMITTED, transaction B **không thấy uncommitted changes** của transaction A.

```text
T1                          T2
--------------------------------------------
begin
persist Invoice #1
flush INSERT
                            SELECT id=1
                            → không nhìn thấy row #1
commit
                            SELECT id=1 lại
                            → có thể nhìn thấy theo isolation
```

Nhưng behavior đọc lại phụ thuộc database và isolation:

- READ COMMITTED: mỗi statement thường thấy committed state mới.
- REPEATABLE READ/SNAPSHOT: transaction B có thể giữ snapshot cũ.
- READ UNCOMMITTED: semantics hỗ trợ khác nhau theo DB.
- SERIALIZABLE: có thể có serialization failures.
- L1 cache của EntityManager B có thể che kết quả nếu đã managed.
- Read replicas có replication lag.

Vì vậy test isolation phải chỉ định engine/level và dùng **hai EntityManagers/connections độc lập**; không viết một assertion tuyệt đối cho mọi RDBMS.

## 37. Test visibility trước và sau commit

Một skeleton với hai EMs:

```java
EntityManager writer = emf.createEntityManager();
EntityManager reader = emf.createEntityManager();

try {
    writer.getTransaction().begin();

    writer.persist(
        invoice(1201L, "INV-1201")
    );
    writer.flush();

    // Với PostgreSQL READ COMMITTED và reader query
    // trực tiếp DB trong transaction riêng/autocommit,
    // row chưa commit không được nhìn thấy.
    assertNull(reader.find(Invoice.class, 1201L));

    writer.getTransaction().commit();

    // Với EntityManager mới để loại L1/cache ảnh hưởng:
    reader.close();
    reader = emf.createEntityManager();

    assertNotNull(reader.find(Invoice.class, 1201L));

} finally {
    if (writer.getTransaction().isActive()) {
        writer.getTransaction().rollback();
    }
    writer.close();
    if (reader.isOpen()) {
        reader.close();
    }
}
```

Đây là test dành cho **PostgreSQL READ COMMITTED** với connection/transaction contexts độc lập và cache không che DB reads. Không coi kết quả như một contract chung cho mọi isolation level.

**Đặc biệt:** nếu reader đã query một ID trước commit và có cache/provider-specific behavior, tạo reader context mới sau commit giúp kết quả dễ hiểu hơn.

---

## 38. Spring `@Transactional` thay đổi transaction ownership

Trong Spring Data JPA:

```java
@Service
public class InvoiceService {

    private final InvoiceRepository repository;

    public InvoiceService(InvoiceRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Long create(Invoice invoice) {
        repository.save(invoice);
        return invoice.getId();
    }
}
```

Transaction thường được Spring proxy/transaction manager mở/commit quanh service method. Khi gọi qua proxy, **commit xảy ra sau khi body method trả về**. Vì vậy một exception ở commit có thể không bị catch trong method bằng `try/catch` quanh `save()`.

Test service cần gọi đúng Spring-managed bean/proxy và bao cả call bằng assertion; không chỉ test private method nội bộ.

### Self-invocation trap

Với proxy-based transaction management, lời gọi `this.someTransactionalMethod()` trong cùng class thường không đi qua proxy, nên annotation `@Transactional` ở method đích có thể không tạo transaction mới như bạn nghĩ. Test transaction boundary phải phản ánh đường gọi production.

## 39. `@DataJpaTest` rollback mặc định

Một Spring Boot slice test:

```java
@DataJpaTest
class InvoiceRepositoryTest {

    @Autowired InvoiceRepository repository;

    @Test
    void storesInvoiceInTestTransaction() {
        repository.save(
            new Invoice(
                1L, 7L, "T-001",
                new BigDecimal("150.00")
            )
        );

        assertTrue(
            repository.findById(1L).isPresent()
        );
    }
}
```

Test có thể pass vì Spring Test quản lý một test transaction được **rollback sau method**. Vì vậy:

- Nó không chứng minh row đã commit.
- Có thể chưa kích hoạt DB constraint nếu không flush.
- Nếu test dùng embedded DB replacement, nó chưa chứng minh PostgreSQL behavior.
- Truy vấn `findById` có thể dùng cùng persistence context.
- Nếu service mở `REQUIRES_NEW` và commit, outer rollback không dọn được commit đó.

`@DataJpaTest` rất hữu ích cho repository/mapping tests, nhưng **commit/rollback integration tests cần chủ động transaction boundary**.

## 40. Test commit thật bằng `TestTransaction`

Spring Test hỗ trợ `TestTransaction` khi có test-managed transaction:

```java
@Test
@Transactional
void commitIsVisibleAfterTestTransactionEnds() {
    repository.save(
        new Invoice(
            1401L, 7L, "INV-1401",
            new BigDecimal("150.00")
        )
    );

    entityManager.flush();

    TestTransaction.flagForCommit();
    TestTransaction.end();

    // Test-managed transaction đã kết thúc bằng commit.
    // Không giả định EntityManager cũ còn là cùng context
    // được dùng để chứng minh data committed.
    assertTrue(repository.findById(1401L).isPresent());
}
```

Mẫu này phụ thuộc Spring Test setup và imports; khi cần **đọc committed state chắc chắn từ transaction/context mới**, có thể gọi `TestTransaction.start()` để bắt đầu một test-managed transaction mới rồi thực hiện query, hoặc dùng `TransactionTemplate`/new service boundary thích hợp. Nếu bắt đầu test transaction mới, nhớ cleanup/rollback cuối test.

Không gọi `TestTransaction.flagForCommit()` ngoài một test-managed transaction active.

## 41. `TransactionTemplate` cho test commit độc lập

Một cách khác:

```java
@Autowired
TransactionTemplate transactionTemplate;

@Test
void serviceCommitCanBeReadLater() {
    transactionTemplate.executeWithoutResult(status -> {
        repository.save(
            new Invoice(
                1501L, 7L, "INV-1501",
                new BigDecimal("150.00")
            )
        );
    });

    Invoice committed = transactionTemplate.execute(
        status -> repository.findById(1501L)
            .orElseThrow()
    );

    assertEquals("INV-1501", committed.getInvoiceNo());
}
```

Để test này thực sự commit độc lập, **không đặt một outer test `@Transactional` bao quanh method**, vì `TransactionTemplate` với propagation REQUIRED có thể tham gia transaction đang có. Chọn transaction manager/propagation một cách rõ ràng.

Lưu ý query trả entity từ transaction callback có thể detached sau callback; chỉ assert basic fields đã load hoặc chuyển sang DTO khi còn trong transaction.

## 42. `REQUIRES_NEW` không bị rollback theo outer test transaction

Giả sử service:

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeAudit(...) {
    auditRepository.save(...);
}
```

Nếu test method đã có outer transaction:

```java
@Test
@Transactional
void testSomething() {
    service.writeAudit(...);
    // Outer test rollback sau method.
}
```

Audit row có thể đã commit ở transaction mới và **không biến mất vì outer rollback**. Đây là một nguồn cross-test contamination rất thường gặp.

Test nên:

- Chủ động transaction ownership.
- Có cleanup cho committed side effects.
- Không dựa vào outer rollback nếu code dùng new transactions.
- Kiểm tra idempotency/transactional outbox semantics nếu phù hợp.
- Xác nhận service method được gọi qua Spring proxy.

## 43. `UnexpectedRollbackException` và swallowed exceptions

Trong Spring, nếu inner transactional operation đánh dấu transaction rollback-only nhưng outer method catch exception rồi trả thành công, outer commit có thể ném `UnexpectedRollbackException`.

Ví dụ ý tưởng:

```text
Outer @Transactional begins
   └─ Inner repository/service operation fails
           └─ transaction marked rollback-only
   └─ Outer catches failure and continues
   └─ Outer method returns
   └─ Spring tries commit → UnexpectedRollbackException
```

Đừng “sửa” bằng cách catch `UnexpectedRollbackException` rồi trả success. Cần xử lý root cause và thiết kế transaction/recovery boundary.

Test nên assert cả:

- Exception gốc/rollback failure.
- Không có partial committed state.
- Không có success event/outbox record nếu transaction thất bại.
- Không dùng lại context cũ để đọc.

---

## 44. Test rollback của service do business exception

Ví dụ service:

```java
@Transactional
public void approveAndFail(Long id) {
    Invoice invoice = repository.findById(id)
        .orElseThrow();

    invoice.approve();

    throw new BusinessRuleException(
        "Simulated failure after state change"
    );
}
```

Với Spring mặc định, unchecked `RuntimeException` thường kích hoạt rollback. Nhưng **checked exception** không mặc định cùng rollback rule nếu không cấu hình `rollbackFor` hoặc policy khác. Các custom annotations/transaction managers có thể thay đổi behavior.

Integration test nên:

1. Seed Invoice và commit.
2. Gọi service qua proxy.
3. Assert exception.
4. Mở transaction/context mới.
5. Assert Invoice vẫn DRAFT.
6. Cleanup fixtures đã commit.

Không chỉ assert Java entity trong service đã được đổi rồi exception ném.

## 45. Checked exception và rollback rules

Một lỗi dễ bị bỏ qua:

```java
@Transactional
public void updateThenThrowChecked() throws IOException {
    Invoice invoice = repository.findById(id)
        .orElseThrow();

    invoice.approve();

    throw new IOException("External step failed");
}
```

Trong Spring transaction management theo default rollback rules, checked `IOException` **không tự động gây rollback** như unchecked RuntimeException, nếu không có cấu hình khác. Kết quả có thể là transaction commit dù method ném checked exception.

Nếu business rule cần rollback:

```java
@Transactional(rollbackFor = IOException.class)
public void updateThenThrowChecked() throws IOException {
    // ...
}
```

Đây là **Spring-specific**, không phải contract của `EntityTransaction` resource-local. Test phải xác nhận kết quả committed thay vì chỉ nhìn exception type.

## 46. `@Transactional(readOnly = true)` không phải bảo đảm rollback

Spring `readOnly=true` là transaction hint/setting có thể tác động flush mode hoặc JDBC read-only flag tùy stack. Nó không thay thế một phép kiểm tra xem operation có commit hay rollback không.

Không viết test với giả định “method readOnly thì mọi thay đổi bị rollback”. Nếu code làm write trong read-only transaction, behavior phụ thuộc provider/DB/transaction manager; nên thiết kế service rõ và test đúng business contract.

---

## 47. Error recovery: retry trong transaction mới

Nếu operation fail vì optimistic conflict:

```text
Attempt 1
  new EntityManager/transaction
  load Invoice version 0
  update
  OptimisticLockException
  rollback + close

Decide retry is allowed
          │
          ▼
Attempt 2
  new EntityManager/transaction
  reload current version
  recompute business rule
  try commit
```

Điều quan trọng:

- Retry chỉ khi lỗi được phân loại là transient/conflict và nghiệp vụ cho phép.
- Mỗi attempt có **transaction và persistence context mới**.
- Reload values vì state có thể đã thay đổi.
- Recompute amount/invariant, không replay setter mù quáng.
- Giới hạn số attempts/backoff.
- Bảo vệ idempotency nếu có event, email, payment call.
- Không gửi side effects ngoài DB trước khi commit nếu có nguy cơ rollback.

**Unique-key failure do invoiceNo đã tồn tại không tự nhiên biến mất vì retry**. Nếu business rule là conflict, trả lỗi/đổi input thay vì retry vô hạn.

## 48. Sau rollback, có nên gọi `refresh()` trên entity cũ?

`em.refresh(entity)` dành cho một managed entity theo contract JPA. Sau rollback/failure, entity có thể không còn managed và context không đáng tin; `refresh` có thể ném `IllegalArgumentException`/persistence exception, hoặc tải state khác.

Thực hành an toàn:

```java
EntityManager fresh = emf.createEntityManager();

try {
    Invoice current = fresh.find(Invoice.class, id);
    // Dùng current cho thao tác mới nếu tồn tại.
} finally {
    fresh.close();
}
```

Đừng dùng `refresh` như cách “undo tất cả Java setters” sau một rollback. Nó không thay thế xây lại unit of work.

## 49. `clear()` và `detach()` không thay rollback

`em.clear()` detach mọi managed entities. `em.detach(entity)` detach một entity. Chúng không làm database rollback những SQL đã flush trong transaction.

Ngược lại, nếu gọi `clear` trước khi flush, pending changes có thể bị bỏ qua khi entities bị detached, tạo một test pass giả vì không có UPDATE nào được gửi.

Nếu test muốn kiểm tra một update, hãy:

1. Seed committed data.
2. Đổi managed entity.
3. Flush/commit rõ ràng.
4. Đóng context.
5. Readback trong context mới.

Nếu test muốn kiểm tra rollback, hãy rollback chứ không dùng `clear` làm “giả rollback”.

## 50. FlushMode và mốc phát SQL

JPA có `FlushModeType.AUTO` và `COMMIT`.

- `AUTO`: provider phải bảo đảm effects của pending changes phù hợp với queries theo semantics trước query; có thể flush trước một số SELECT.
- `COMMIT`: effect của pending changes lên queries trước commit có những semantics khác/không được đảm bảo theo cùng cách.
- Provider có thể thêm modes riêng (`MANUAL`, `ALWAYS`, v.v.).

Nếu test muốn cố định mốc kiểm tra DB constraint, gọi `em.flush()` trong transaction là cách diễn đạt mục tiêu rõ, nhưng **vẫn phải assert commit** nếu yêu cầu là transaction completion.

Đừng viết test dựa vào một JPQL SELECT tình cờ trigger auto-flush mà không giải thích.

---

## 51. Những thay đổi transaction chưa commit và JPQL query

Trong cùng persistence context:

```java
em.getTransaction().begin();
Invoice invoice = invoice(1601L, "INV-1601");

em.persist(invoice);

Long count = em.createQuery(
    "SELECT COUNT(i) FROM Invoice i WHERE i.id = :id",
    Long.class
).setParameter("id", 1601L)
 .getSingleResult();
```

Với AUTO flush và provider/query semantics phù hợp, query có thể khiến INSERT được flush trước khi count. Nhưng count trong cùng transaction vẫn không chứng minh commit; SQL có thể nhìn thấy uncommitted writes của chính transaction.

Do đó test “count == 1 trước commit” không thay test “context mới thấy row sau commit”.

## 52. Một API trả success trước commit có thể nói sai sự thật

Trong Spring:

```java
@Transactional
public Long createInvoice(Command command) {
    Invoice invoice = ...;
    repository.save(invoice);
    return invoice.getId();
}
```

Method body trả ID rồi transaction interceptor mới commit. Nếu commit thất bại, caller sẽ thường nhận exception từ proxy chứ không nhận success. Nhưng nếu code đã gửi email hoặc publish event ra ngoài trong method body, side effect đó có thể xảy ra **trước khi DB commit**.

Integration test có thể cần assert:

- Failed transaction không tạo committed Invoice.
- Không có outbox row committed.
- Không phát một success event không thể hoàn tác trước commit.
- Transactional outbox hoặc after-commit hook được sử dụng đúng nếu nghiệp vụ cần.

Không nên dùng rollback như một cách hoàn tác HTTP/email gửi ra bên ngoài.

## 53. Transactional outbox khi test commit/rollback

Một pattern:

```text
Transaction:
  INSERT invoice
  INSERT outbox_event
          │
          ├─ COMMIT  → cả invoice và event row tồn tại
          └─ ROLLBACK → cả hai rows không tồn tại
```

Test lý tưởng có hai assertions:

- Commit: Invoice và event committed.
- Rollback: cả hai không committed.

Publisher xử lý outbox sau commit theo pipeline riêng. Nếu trực tiếp publish message trong transaction trước commit, rollback DB không đảm bảo message biến mất.

Điều này minh họa vì sao test JPA commit/rollback không nên chỉ nhìn entity root khi use case có related writes.

---

## 54. Test resource cleanup khi assertion thất bại

Một test có thể fail giữa chừng:

```java
em.getTransaction().begin();
em.persist(invoice);
assertEquals(...); // AssertionError nếu không đạt
```

`AssertionError` kế thừa `Error`, không phải `RuntimeException`. Helper `withTransaction(Consumer)` ở ví dụ trước chỉ catch `RuntimeException`; khi assertion thất bại bên trong callback, khối `finally` vẫn đóng EntityManager nhưng không chủ động gọi rollback. Để **test harness** xử lý cả assertion failures, có thể mở rộng helper thành bắt `RuntimeException | Error` rồi rollback.

```java
static void inTestTransaction(
        EntityManagerFactory emf,
        Consumer<EntityManager> work) {

    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();
        work.accept(em);
        tx.commit();
    } catch (RuntimeException | Error failure) {
        if (tx.isActive()) {
            try {
                tx.rollback();
            } catch (RuntimeException rollbackError) {
                failure.addSuppressed(rollbackError);
            }
        }
        throw failure;
    } finally {
        em.close();
    }
}
```

Đây là một helper dành cho môi trường kiểm thử; production code có thể có chính sách exception/transaction khác. **Không nuốt original assertion failure** khi rollback cũng gặp lỗi.

Với resource-local EntityManager và transaction còn active, đóng EM không nên được dùng thay rollback tường minh của test harness.

## 55. Kiểm tra rollback khi `commit()` ném exception

Một helper nên bao `tx.commit()` trong cùng try, vì lỗi có thể chỉ xuất hiện tại completion:

```java
try {
    tx.begin();
    work.accept(em);
    tx.commit();
} catch (RuntimeException | Error failure) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw failure;
} finally {
    em.close();
}
```

Sau một commit attempt thất bại, transaction manager/provider có thể đã hoàn tất rollback hoặc vẫn cần cleanup; kiểm tra `isActive()` trước khi gọi rollback. Test không được giả định mọi failed commit để lại transaction active.

Nếu rollback cũng fail, giữ exception ban đầu và ghi nhận rollback failure như suppressed, thay vì để lỗi cleanup che mất cause chính.

## 56. Khi không chắc outcome của commit do mất kết nối

Một trường hợp production khó hơn:

```text
Client gửi COMMIT
Database commit thành công
Connection bị đứt trước khi client nhận ACK
Ứng dụng nhìn thấy exception/timeout
```

Ở đây **exception tại commit không luôn đồng nghĩa chắc chắn không có row** nếu kết nối bị hỏng ở ranh giới acknowledgement. Đó là tình huống *unknown transaction outcome*, khác với một UNIQUE/CHECK rejection rõ ràng.

Recovery đúng cần:

- Mở connection/context mới.
- Tra cứu bằng stable business key/idempotency key.
- Không tự động insert lại nếu có nguy cơ duplicate.
- Xử lý retry idempotent.
- Ghi nhận trạng thái không xác định cho operator/client khi cần.
- Không dùng Java object cũ làm bằng chứng outcome.

Trong integration tests bình thường với DB khỏe và constraint failure xác định, rollback semantics rất rõ. Nhưng test fault injection/network partition có thể cần mô phỏng unknown outcome riêng; không ép mọi exception commit vào “chắc chắn rollback” một cách thiếu căn cứ.

---

## 57. Test với isolation và snapshot thực

Nếu transaction B bắt đầu trước khi A commit, B có thể không thấy thay đổi sau commit A khi dùng snapshot isolation.

Một test portable không nên:

```java
// B transaction đã giữ snapshot cũ.
assertNotNull(emB.find(Invoice.class, newlyCommittedId));
```

rồi suy commit A thất bại nếu emB vẫn không thấy row.

Thay bằng EntityManager/transaction mới với isolation visibility policy mong đợi, và nếu có read replica phải cân nhắc replication lag.

**Đọc committed state** cần định nghĩa rõ: DB nào, isolation nào, snapshot nào, cache nào.

## 58. JPA provider exception translation trong Spring

Một DB unique violation có thể xuất hiện dưới dạng:

- Hibernate `org.hibernate.exception.ConstraintViolationException`.
- JPA `PersistenceException` hoặc `RollbackException`.
- Spring `DataIntegrityViolationException`.
- Driver `SQLException` với SQLState.
- Một cause chain qua nhiều lớp.

Trong test Spring, assert ở tầng phù hợp:

- Repository/service API contract: Spring exception/domain exception đúng.
- Database integrity: SQLState/constraint name/root cause.
- Transaction semantics: row được commit/rollback đúng.
- External API: HTTP 409/422 hoặc error mapping theo nghiệp vụ.

Đừng bắt mọi `DataAccessException` rồi gọi là “hóa đơn đã tồn tại”, vì lỗi DB connection cũng là data access failure nhưng không tương đương unique conflict.

---

## 59. Anti-pattern 1: chỉ assert entity ID sau `save()`

```java
Invoice saved = repository.save(invoice);
assertNotNull(saved.getId());
```

ID có thể được gán trước commit. Test này không chứng minh row committed.

**Sửa:** kiểm tra transaction completion rồi đọc bằng context mới.

## 60. Anti-pattern 2: `flush()` được xem là commit

```java
em.flush();
assertNotNull(em.find(Invoice.class, id));
```

Có thể pass dù transaction rollback sau đó.

**Sửa:** explicit commit/rollback và fresh readback.

## 61. Anti-pattern 3: rollback rồi assert Java fields đã trở về cũ

Rollback không undo setters của Java object.

**Sửa:** đọc lại committed DB state qua context mới.

## 62. Anti-pattern 4: catch exception rồi tiếp tục commit

Persistence context/transaction có thể rollback-only hoặc inconsistent.

**Sửa:** rollback, close, context/transaction mới nếu recovery hợp lệ.

## 63. Anti-pattern 5: assert bất kỳ RuntimeException

Unique/CHECK/optimistic test có thể pass vì nguyên nhân unrelated.

**Sửa:** inspect causes, SQLState, provider exception và DB state.

## 64. Anti-pattern 6: Testcontainers DB shared không dọn fixtures

Tests lệ thuộc thứ tự, IDs bị trùng và cross-test contamination.

**Sửa:** per-test rollback/cleanup/schema isolation phù hợp, không chạy tests cùng cleanup chung song song.

## 65. Anti-pattern 7: @DataJpaTest mặc định rollback nhưng lại kết luận commit

Spring test transaction có thể rollback sau method.

**Sửa:** explicit transaction completion hoặc service integration test không có outer test transaction.

## 66. Anti-pattern 8: Readback trong cùng persistence context

L1 trả managed object và che DB state.

**Sửa:** close/clear phù hợp và mở context/transaction mới, kiểm soát L2 cache.

## 67. Anti-pattern 9: Retry failed entity graph bằng `merge()` ngay

Detached/stale/rolled-back object không bảo đảm đại diện current DB state.

**Sửa:** dùng command/idempotency key, reload state, tạo transaction mới.

## 68. Anti-pattern 10: Không xét optimistic conflicts

Hai writers có thể cùng sửa một entity và commit theo thứ tự không mong muốn nếu thiếu version/locking policy.

**Sửa:** test two-context stale-write behavior bằng `@Version`.

## 69. Anti-pattern 11: Gửi event trước khi commit

Rollback DB không undo message đã phát.

**Sửa:** transactional outbox hoặc after-commit orchestration, và integration test failure path.

## 70. Anti-pattern 12: Dùng H2 để khẳng định PostgreSQL constraint deferral

Different database engines có behavior khác.

**Sửa:** production-like database integration tests.

## 71. Anti-pattern 13: Test query AUTO flush thay vì chủ động flush

Mốc SQL phụ thuộc provider/query semantics.

**Sửa:** explicit flush khi mục tiêu là kiểm tra SQL constraint tại mốc đó.

## 72. Anti-pattern 14: Outer test rollback được coi là dọn `REQUIRES_NEW`

Transaction mới commit độc lập.

**Sửa:** cleanup committed side effects theo scope.

## 73. Anti-pattern 15: `isActive() == true` được coi là commit được

Transaction có thể rollback-only.

**Sửa:** đọc contract exception, kiểm tra rollback-only nếu cần và rollback failed unit of work.

---

## 74. Bài tập 1: Flush rồi rollback

```java
em.persist(invoice);
em.flush();
em.getTransaction().rollback();
```

**Câu hỏi:** ID tồn tại trên Java object có chứng minh row committed không?

**Đáp án:** Không. Mở context mới và `find`; transaction rollback không lưu row.

## 75. Bài tập 2: Test commit thật

Một test chỉ gọi `persist` rồi `assertNotNull(entity.getId())`.

**Đáp án:** Chưa đủ. Cần commit và fresh-context readback.

## 76. Bài tập 3: Rollback update

Invoice committed amount=100; trong transaction đổi thành 200 và rollback.

**Đáp án:** DB vẫn 100; object Java có thể vẫn 200. Assert DB trong context mới.

## 77. Bài tập 4: Rollback remove

`remove`/`flush` xóa Invoice rồi rollback.

**Đáp án:** Row committed trước đó còn. Đọc bằng EntityManager mới.

## 78. Bài tập 5: Unique constraint

Hai Invoice cùng tenant+invoiceNo bị DB từ chối.

**Đáp án:** Assert PostgreSQL SQLState `23505`/constraint name và verify row thứ hai không committed.

## 79. Bài tập 6: CHECK constraint

Invoice amount -1, DB có `CHECK(total_amount>=0)`.

**Đáp án:** Assert SQLState `23514` nếu test đi tới DB, không nhầm Bean Validation exception.

## 80. Bài tập 7: Entity state sau rollback

`invoice.getTotalAmount()` vẫn trả giá trị mới.

**Đáp án:** Java object không được tự rollback. Không dùng lại graph cũ như synchronized state.

## 81. Bài tập 8: Detached merge

`Invoice copied = em.merge(detached)`.

**Đáp án:** `copied` là managed reference được trả về; object `detached` không trở thành managed do lời gọi merge.

## 82. Bài tập 9: First-level cache

`em.find` hai lần cùng ID trả cùng instance.

**Đáp án:** Identity map hợp lệ, nhưng không chứng minh query DB lần hai hay committed state mới nhất.

## 83. Bài tập 10: Deferred FK

`flush()` thành công; `commit()` fail vì FK được defer.

**Đáp án:** Cần test bao cả commit boundary, không chỉ flush.

## 84. Bài tập 11: Rollback-only

Transaction còn active sau persistence failure.

**Đáp án:** Active không bảo đảm committable; có thể rollback-only. Rollback/close unit of work lỗi.

## 85. Bài tập 12: Optimistic locking

Hai EMs load version=0; A commit amount=200, B cố commit amount=300.

**Đáp án:** B nên conflict/rollback với version-aware ORM update; DB giữ 200. Test hai contexts độc lập.

## 86. Bài tập 13: Cross-test contamination

Test A commit Invoice #1; test B mặc định có Invoice #1 tồn tại.

**Đáp án:** Fixture order dependency. Mỗi test seed/cleanup độc lập hoặc dùng schema isolation.

## 87. Bài tập 14: Checked exception trong Spring

`@Transactional` method đổi Invoice rồi throw `IOException`.

**Đáp án:** Default Spring rollback rules thường không rollback checked exception nếu không cấu hình `rollbackFor`. Test committed state, không suy theo exception.

## 88. Bài tập 15: `@DataJpaTest`

`saveAndFlush` pass trong rollback-managed test.

**Đáp án:** Chứng minh flush path, chưa chứng minh commit.

## 89. Bài tập 16: `REQUIRES_NEW`

Inner audit transaction commit, outer test rollback.

**Đáp án:** Audit row có thể còn; cần cleanup rõ.

## 90. Bài tập 17: `clear()`

Developer gọi `em.clear()` để “rollback”.

**Đáp án:** Sai. Clear detach entities, không hoàn tác database SQL đã flush.

## 91. Bài tập 18: Event ngoài DB

Service gửi email trước commit rồi DB fail unique.

**Đáp án:** Email không tự rollback. Dùng outbox/after-commit policy.

## 92. Bài tập 19: Unknown commit outcome

DB commit xong nhưng connection mất trước ACK.

**Đáp án:** Không biết chắc outcome chỉ từ exception. Query lại bằng idempotency key/context mới trước retry.

## 93. Bài tập 20: Wrong SQLState

Test CHECK assert `23505`.

**Đáp án:** Sai nhóm. PostgreSQL `23505` là unique violation, `23514` là CHECK violation.

## 94. Bài tập 21: Fresh readback và replica

Ngay sau commit primary, đọc read replica chưa thấy row.

**Đáp án:** Có thể replication lag. Dùng consistency route thích hợp cho test committed state.

## 95. Bài tập 22: EntityManager giữa các threads

Hai threads chia sẻ một EntityManager để test race.

**Đáp án:** Không an toàn, EM không thread-safe. Dùng riêng mỗi thread.

## 96. Bài tập 23: FlushMode COMMIT

Test dựa vào `SELECT COUNT` trước commit để ép flush.

**Đáp án:** Không chắc portable. Explicit `flush` khi muốn mốc SQL rõ.

## 97. Bài tập 24: Constraint lỗi nhưng exception bị nuốt

Service catch `DataIntegrityViolationException` rồi return success.

**Đáp án:** Transaction có thể rollback-only; phải propagate/translate lỗi đúng và assert không committed.

## 98. Bài tập 25: Bộ kiểm thử hoàn chỉnh

**Yêu cầu:** Thiết kế JPA integration test cho tạo/cập nhật/xóa Invoice, rollback sau lỗi, UNIQUE, CHECK và optimistic locking.

**Hướng giải:**

1. PostgreSQL Testcontainers + Flyway migrations.
2. JPA `RESOURCE_LOCAL` unit riêng cho tests.
3. Mỗi method có fixtures riêng và cleanup có kiểm soát.
4. Test persist + commit + fresh readback.
5. Test flush + rollback + readback không có row.
6. Test UPDATE rollback giữ nguyên committed amount.
7. Test DELETE rollback giữ nguyên committed Invoice.
8. Test UNIQUE/CHECK failure bằng cause/SQLState.
9. Test failed transaction không tiếp tục commit thao tác khác.
10. Test hai EntityManagers cạnh tranh với `@Version`.
11. Test service-level Spring transaction boundaries nếu production dùng Spring.
12. Test outbox/related writes cùng rollback nếu business operation có side effects.
13. Bảo đảm tests không phụ thuộc thứ tự/parallel run và không xóa shared DB.

---

## 99. Checklist kiểm thử commit/rollback và trạng thái entity

Khi hoàn thiện một phép thử JPA:

1. Test đang kiểm tra Java object hay committed database state?
2. Có transaction thật và EntityManager phù hợp không?
3. `EntityManagerFactory`/persistence unit trỏ đúng DB/schema test không?
4. Có migrations và constraints thật không?
5. Có phân biệt `persist`, `flush` và `commit` không?
6. Test commit có thật sự hoàn tất transaction không?
7. Có readback bằng context mới sau commit không?
8. Có tránh dùng entity trong L1 làm chứng cứ DB state không?
9. Test rollback có đọc lại committed state sau rollback không?
10. Có kiểm tra INSERT rollback không tạo row không?
11. Có kiểm tra UPDATE rollback giữ giá trị cũ không?
12. Có kiểm tra DELETE rollback giữ row cũ không?
13. Có kiểm tra child/cascade state nếu nghiệp vụ yêu cầu không?
14. Có biết Java fields/ID/version không tự reset sau rollback không?
15. Có tránh tái sử dụng persistence context đã lỗi không?
16. Có đóng EntityManager trong finally không?
17. Có rollback chủ động khi runtime failure xảy ra không?
18. Test harness có cleanup khi `AssertionError` xảy ra không?
19. Có giữ original exception nếu rollback cũng fail không?
20. Có kiểm tra `isActive` khác rollback-only không?
21. Có phân biệt Bean Validation với SQL constraint failure không?
22. Có assert đúng SQLState/constraint khi test DB integrity không?
23. Có assert committed DB state sau constraint failure không?
24. Có bao cả `commit()` trong vùng test lỗi deferred constraints không?
25. Có dùng optimistic version nếu cần chống lost updates không?
26. Có dùng hai independent EntityManagers/transactions khi test concurrency không?
27. Có tránh share EntityManager giữa threads không?
28. Có dùng synchronization thay sleep nếu test threads không?
29. Có kiểm tra isolation level/snapshot visibility không?
30. Có tránh dùng read replica lag làm false negative không?
31. Có kiểm soát L2 cache nếu mục tiêu là DB readback không?
32. Có biết `merge` trả managed copy chứ không quản lý object gốc không?
33. Có tránh `clear()` thay rollback không?
34. Có tránh reliance vào AUTO query-triggered flush không?
35. Nếu Spring, có biết transaction boundary do proxy sở hữu không?
36. Có test commit thật thay vì chỉ `@DataJpaTest` rollback không?
37. Có biết checked exception rollback rules của Spring không?
38. Có test `REQUIRES_NEW` side effects độc lập không?
39. Có kiểm tra `UnexpectedRollbackException` root cause không?
40. Có dùng transaction/context mới cho retry hợp lệ không?
41. Có idempotency key nếu commit outcome không xác định không?
42. Có bảo vệ external side effects qua outbox/after-commit không?
43. Có test đúng aggregate invariants khi rollback không?
44. Có deterministic fixtures và cleanup đủ mạnh không?
45. Có tránh destructive cleanup trên DB shared/production không?
46. Có đảm bảo tests parallel không làm hỏng fixtures của nhau không?
47. Có production-like DB cho locking/SQLState/deferred constraint không?
48. Có phân biệt provider-specific timing với JPA contract không?
49. Có CI logs đủ debug mà không lộ credentials/PII không?
50. Có thể chạy lại test suite từ schema sạch với cùng kết quả không?

Checklist trên dùng để thiết kế các tình huống kiểm thử đáng tin, không có nghĩa mọi test method phải lặp lại tất cả thao tác. Bài test tốt chỉ kiểm tra **một invariant rõ ràng**, nhưng hệ thống fixtures phải giúp quan sát đúng transaction outcome.

## Kết luận

**Kiểm thử commit, rollback và trạng thái entity sau lỗi** là bài học về ranh giới giữa Java memory, JPA persistence context và database transaction.

Cần nhớ:

- `persist()` làm entity được quản lý, không đồng nghĩa row đã commit.
- `flush()` đồng bộ pending changes vào transaction, không thay `commit()`.
- `commit()` mới cố hoàn tất giao dịch; lỗi có thể phát ở flush hoặc ngay tại commit.
- `rollback()` hoàn tác database changes, nhưng **không hoàn tác Java setters hoặc đảm bảo object cũ trở về managed state sạch**.
- Muốn kiểm tra committed state, hãy hoàn tất transaction và dùng EntityManager/transaction mới theo isolation/cache policy phù hợp.
- Sau persistence failure, không tiếp tục dùng context đã lỗi; rollback và tạo unit of work mới nếu cần.
- UNIQUE/CHECK/FK/optimistic failures phải được phân loại đúng nguyên nhân, không chỉ assert `RuntimeException` bất kỳ.
- `@Version` và two-transaction integration tests giúp phát hiện stale writes.
- Trong Spring, `@DataJpaTest` thường rollback theo mặc định, còn `@Transactional` service commit ở transaction proxy boundary; tests cần kiểm tra đúng nơi transaction kết thúc.
- Các side effects ngoài database không tự rollback; transactional outbox và idempotency là những phần cần thiết cho nhiều use cases thực.
- Một commit exception do mất kết nối có thể tạo **unknown outcome**; không retry mù quáng khi chưa kiểm tra state mới.

Phép thử chất lượng cần trả lời được bốn câu hỏi: **“Thay đổi đã được gửi xuống database chưa? Transaction thực sự commit hay rollback? Entity đang được nhìn từ persistence context nào? Và sau lỗi, committed state cuối cùng là gì?”**. Khi tách bốn câu hỏi đó, ta tránh được những integration tests pass giả và có thể tin cậy hành vi JPA khi gặp lỗi thực tế.
