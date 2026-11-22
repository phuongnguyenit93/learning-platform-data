# Cập nhật hàng loạt rồi đồng bộ lại persistence context trong JPA

Trong ứng dụng JPA, cách cập nhật quen thuộc là lấy entity bằng `EntityManager.find()`, sửa thuộc tính trên object đang **managed**, sau đó để cơ chế dirty checking ghi SQL vào lúc `flush()` hoặc commit. Tuy nhiên, nếu cần đổi trạng thái cho 50.000 đơn hàng, việc load từng entity có thể gây chi phí lớn về truy vấn, bộ nhớ và thời gian xử lý. **JPQL bulk UPDATE** giúp cập nhật nhiều rows trực tiếp bằng một câu lệnh.

Đánh đổi quan trọng của bulk UPDATE: **database rows thay đổi, nhưng những managed entity instances đang nằm trong persistence context không tự thay đổi theo**. Một object vẫn có thể báo trạng thái cũ; gọi `find()` lần nữa trong cùng `EntityManager` có thể trả lại chính object cũ từ first-level cache. Nếu tiếp tục thao tác mà không đồng bộ, ứng dụng có thể đưa ra quyết định nghiệp vụ sai, ghi đè dữ liệu hoặc gặp optimistic lock conflict.

Bài học thuộc chương **Thực hành tổng hợp** của chủ đề **Data Persistence Relational Access ORM JPA**. Chúng ta sẽ thực hành theo luồng:

```text
Tạo dữ liệu mẫu và mở transaction
             |
             v
Load Order -> managed entity trong L1 cache
             |
             v
JPQL bulk UPDATE trực tiếp trên database
             |
             v
Database state mới nhưng managed state có thể cũ
             |
       +-----+----------------------+
       |                            |
       v                            v
refresh(managed)            flush() -> clear()
giữ object reference         bỏ stale managed objects
       |                            |
       v                            v
State mới trên object       find/query tạo managed state mới
       +------------+---------------+
                    |
                    v
       Version/audit/tenant/transaction checks
                    |
                    v
       Commit và readback bằng context mới
```

**Mục tiêu sau bài học:** hiểu chính xác SQL bulk khác với managed updates và JDBC batching; biết khi nào dùng `refresh`, `clear`, `detach`; xử lý pending changes bằng `flush`; cấu hình Spring Data JPA `@Modifying`; quản lý `@Version`, callbacks, audit, caches, concurrency, rollback và triển khai một batch job an toàn có kiểm thử.

---

## 1. Bài toán nghiệp vụ

Một hệ thống nhiều tenant có quy trình đơn hàng:

```text
NEW ----đã đối soát----> READY ----giao hàng----> SHIPPED
  \
   \----hủy đơn--------------------------------> CANCELLED
```

Một job của tenant 10 cần chuyển toàn bộ đơn **NEW → READY**. Giả sử fixture:

| Order ID | Tenant | Trạng thái ban đầu | Total |
|---|---:|---|---:|
| 101 | 10 | NEW | 100.00 |
| 102 | 10 | NEW | 200.00 |
| 103 | 10 | READY | 300.00 |
| 201 | 20 | NEW | 400.00 |

Sau job, 101 và 102 phải READY; 103 giữ READY; 201 của tenant khác vẫn NEW.

Với một Order, code thông thường:

```java
CustomerOrder order =
    em.find(CustomerOrder.class, orderId);

order.markReady(Instant.now());
```

Với nhiều Orders, bulk DML:

```java
int count = em.createQuery(
        """
        UPDATE CustomerOrder o
        SET o.status = :ready,
            o.updatedAt = :now
        WHERE o.tenantId = :tenantId
          AND o.status = :expected
        """
    )
    .setParameter("ready", OrderStatus.READY)
    .setParameter("now", Instant.now())
    .setParameter("tenantId", 10L)
    .setParameter("expected", OrderStatus.NEW)
    .executeUpdate();
```

Với fixture cô lập, `count` dự kiến là 2. Trong production, concurrency có thể khiến tập rows đủ điều kiện thay đổi giữa các lần kiểm tra; không được suy rằng affected count luôn cố định.

---

## 2. Phân biệt managed update, JDBC batching và JPQL bulk UPDATE

| Cách cập nhật | Cơ chế | Hệ quả đáng chú ý |
|---|---|---|
| Managed entity update | Load rồi sửa Java object | Dirty checking, callbacks, version theo lifecycle |
| JDBC batching | Gom nhiều executions cùng SQL shape | Có thể dùng cho nhiều managed INSERT/UPDATE |
| JPQL bulk UPDATE | Một modification query tác động nhiều rows | Bỏ qua xử lý từng managed entity |
| Native SQL UPDATE | Trực tiếp SQL theo dialect | Không tự đồng bộ persistence context |

**JPQL bulk UPDATE không phải một vòng lặp ngầm gọi domain setter trên từng object.** Database phải cập nhật rows và indexes theo điều kiện, nhưng provider không bắt buộc materialize mọi entity phù hợp vào persistence context.

Một câu bulk SQL có thể giảm round trips và heap pressure, nhưng vẫn gây locks, WAL/redo, index maintenance và chi phí commit. Một câu UPDATE hàng triệu rows có thể chậm hoặc gây blocking hơn nhiều transactions nhỏ.

### 2.1. Khi nào nên dùng bulk?

- Thay cùng một số fields cho nhiều rows theo predicate rõ.
- Không cần chạy per-entity domain callbacks/cascades.
- Không cần load đầy đủ entity graph để xác định eligibility.
- Có chiến lược version, audit và cache invalidation phù hợp.

### 2.2. Khi nào nên dùng managed updates?

- Transition cần validation nghiệp vụ riêng trên mỗi entity.
- Cần cascade, orphanRemoval, lifecycle callbacks theo entity.
- Cần phiên bản optimistic locking do provider quản lý.
- Cần biết chính xác thay đổi và phát domain events per entity.
- Số entity không lớn hoặc đã nằm trong persistence context.

---

## 3. Persistence context và identity map

Trong cùng một `EntityManager`, một persistent identity tương ứng với một managed instance:

```java
CustomerOrder a =
    em.find(CustomerOrder.class, 101L);

CustomerOrder b =
    em.find(CustomerOrder.class, 101L);

assertSame(a, b);
```

`find()` có thể trả managed instance từ **first-level cache (L1)**, không nhất thiết phát SQL SELECT mới.

### 3.1. Dirty checking

Khi sửa một managed entity, JPA provider theo dõi persistent state. Khi flush, nó quyết định những UPDATE cần gửi database.

### 3.2. Bulk UPDATE không thông báo cho object đã load

Nếu SQL bulk đổi row 101 sang READY, `a.getStatus()` có thể vẫn NEW. JPA không đi qua mọi entity trong L1 rồi cập nhật status.

### 3.3. L1 khác L2 và query cache

`EntityManager.clear()` chỉ dọn persistence context. Second-level cache/query cache, nếu được bật, có invalidation contract riêng phụ thuộc provider.

---

## 4. Entity mẫu của phòng thực hành

```java
package com.example.orders;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(
    name = "customer_order",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_order_tenant_request",
        columnNames = {"tenant_id", "request_id"}
    ),
    indexes = @Index(
        name = "ix_order_tenant_status",
        columnList = "tenant_id, status"
    )
)
public class CustomerOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "request_id", nullable = false)
    private String requestId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private OrderStatus status;

    @Column(nullable = false, precision = 16, scale = 2)
    private BigDecimal total;

    @Column(name = "updated_at")
    private Instant updatedAt;

    @Version
    private long version;

    @Transient
    private int preUpdateCalls;

    protected CustomerOrder() {}

    public CustomerOrder(
            Long tenantId,
            String requestId,
            BigDecimal total) {
        this.tenantId = tenantId;
        this.requestId = requestId;
        this.total = total;
        this.status = OrderStatus.NEW;
    }

    public Long getId() { return id; }
    public Long getTenantId() { return tenantId; }
    public String getRequestId() { return requestId; }
    public OrderStatus getStatus() { return status; }
    public BigDecimal getTotal() { return total; }
    public Instant getUpdatedAt() { return updatedAt; }
    public long getVersion() { return version; }
    public int getPreUpdateCalls() {
        return preUpdateCalls;
    }

    public void markReady(Instant now) {
        if (status != OrderStatus.NEW) {
            throw new IllegalStateException(
                "Only NEW order can become READY"
            );
        }
        status = OrderStatus.READY;
        updatedAt = now;
    }

    public void changeTotal(BigDecimal newTotal) {
        if (newTotal == null ||
            newTotal.signum() < 0) {
            throw new IllegalArgumentException(
                "Total must be nonnegative"
            );
        }
        total = newTotal;
    }

    @PreUpdate
    void beforeUpdate() {
        preUpdateCalls++;
    }
}
```

```java
public enum OrderStatus {
    NEW, READY, SHIPPED, CANCELLED
}
```

### 4.1. Lý do có các trường

`tenantId` là phạm vi dữ liệu; `requestId` hỗ trợ uniqueness của business operation; `status` dùng để làm state transition; `updatedAt` là metadata; `@Version` để kiểm concurrency; `preUpdateCalls` là một `@Transient` counter quan sát callbacks.

### 4.2. IDENTITY không thay bản chất bài học

Nếu database mục tiêu dùng SEQUENCE, có thể đổi chiến lược và DDL cho test profile. Bulk stale state không phụ thuộc IDENTITY hay SEQUENCE.

### 4.3. Domain method không tự được chạy bởi bulk

Bulk query không gọi `markReady()`. Nếu method này kiểm thêm payment, stock hoặc ACL, bạn phải thực thi invariant tương đương trong điều kiện SQL/transaction hoặc chọn cách cập nhật khác.

---

## 5. Schema tham khảo

Ví dụ theo một dialect có identity columns:

```sql
CREATE TABLE customer_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    request_id VARCHAR(120) NOT NULL,
    status VARCHAR(20) NOT NULL,
    total NUMERIC(16,2) NOT NULL,
    updated_at TIMESTAMP,
    version BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT uk_order_tenant_request
      UNIQUE (tenant_id, request_id),

    CONSTRAINT ck_order_total
      CHECK (total >= 0)
);

CREATE INDEX ix_order_tenant_status
ON customer_order (tenant_id, status);
```

Đây là cú pháp SQL minh họa, không phải DDL portable cho mọi database. Cột `@Version` phải tương thích với mapping và schema migration thực tế.

### 5.1. Unique business key

Hai requests tạo Orders khác nhau có thể nhận hai generated IDs khác nhau; unique `(tenant_id, request_id)` giúp bảo vệ business idempotency khi retry.

### 5.2. Không tự tạo schema production bằng create-drop

Production nên dùng migration được review. Annotation không thay việc xác minh database constraints thực.

---

## 6. Helper transaction cho integration tests

Các tests sau dùng JUnit 5, `EntityManagerFactory` và một helper dành cho `RESOURCE_LOCAL`:

```java
import jakarta.persistence.*;
import java.util.function.Function;

public final class JpaTestTx {

    private JpaTestTx() {}

    public static <T> T committed(
            EntityManagerFactory emf,
            Function<EntityManager, T> work) {

        EntityManager em = emf.createEntityManager();
        EntityTransaction tx = em.getTransaction();

        try {
            tx.begin();

            T value = work.apply(em);

            tx.commit();
            return value;
        } catch (RuntimeException | Error failure) {
            if (tx.isActive()) {
                try {
                    tx.rollback();
                } catch (RuntimeException cleanup) {
                    failure.addSuppressed(cleanup);
                }
            }
            throw failure;
        } finally {
            em.close();
        }
    }
}
```

Với Spring/JTA-managed EntityManager, transaction owner là framework/container; không dùng `EntityManager.getTransaction()` như ví dụ RESOURCE_LOCAL.

Một fixture helper trong test class:

```java
Long createNewOrder(long tenantId) {
    return JpaTestTx.committed(emf, em -> {
        CustomerOrder order = new CustomerOrder(
            tenantId,
            "test-" + UUID.randomUUID(),
            new BigDecimal("100.00")
        );

        em.persist(order);
        em.flush();

        return order.getId();
    });
}
```

`emf` là `EntityManagerFactory` được setup/close bởi test lifecycle. Sử dụng unique request keys và database/schema cô lập để affected counts không phụ thuộc tests khác.

---

## 7. Bước A: Managed update thông thường

```java
@Test
void managedUpdate_changesJavaStateAndDatabase() {
    Long id = createNewOrder(10L);

    JpaTestTx.committed(emf, em -> {
        CustomerOrder order =
            em.find(CustomerOrder.class, id);

        assertEquals(
            OrderStatus.NEW,
            order.getStatus()
        );

        order.markReady(Instant.now());

        assertEquals(
            OrderStatus.READY,
            order.getStatus()
        );

        em.flush();

        assertTrue(
            order.getPreUpdateCalls() >= 1
        );

        return null;
    });

    OrderStatus stored = JpaTestTx.committed(
        emf,
        em -> em.find(
            CustomerOrder.class, id
        ).getStatus()
    );

    assertEquals(OrderStatus.READY, stored);
}
```

### 7.1. Điểm đáng nhớ

Java getter đổi ngay vì domain method đã sửa object. Sau flush/commit, database được đồng bộ theo lifecycle; callback `@PreUpdate` có thể được gọi trước actual UPDATE.

### 7.2. Không dùng getter làm commit proof

Nếu chỉ assert status trong cùng transaction, transaction vẫn có thể rollback sau đó. Test này cố ý mở transaction mới để xác minh.

---

## 8. Bước B: JPQL bulk UPDATE được scoped

```java
int promoteNewOrders(
        EntityManager em,
        long tenantId,
        Instant now) {

    return em.createQuery(
            """
            UPDATE CustomerOrder o
            SET o.status = :ready,
                o.updatedAt = :now
            WHERE o.tenantId = :tenantId
              AND o.status = :expected
            """
        )
        .setParameter("ready", OrderStatus.READY)
        .setParameter("now", now)
        .setParameter("tenantId", tenantId)
        .setParameter("expected", OrderStatus.NEW)
        .executeUpdate();
}
```

### 8.1. TransactionRequiredException

Modification query cần active transaction. Chạy `executeUpdate()` ngoài transaction có thể ném `TransactionRequiredException`.

### 8.2. Trả về affected count

`executeUpdate()` trả affected entity/row count theo JPQL/provider semantics. Nó **không trả list IDs** đã được sửa.

### 8.3. WHERE vừa là eligibility, vừa là security

Trong shared-table multi-tenancy, tenant predicate bắt buộc phải được đưa vào query hoặc một database-level policy đáng tin. Không dùng tenant ID do client tùy ý cung cấp làm source authoritative.

---

## 9. Bước C: Tái hiện stale managed entity

```java
@Test
void bulkUpdate_doesNotRefreshManagedEntity() {
    Long id = createNewOrder(10L);

    JpaTestTx.committed(emf, em -> {
        CustomerOrder managed =
            em.find(CustomerOrder.class, id);

        assertEquals(
            OrderStatus.NEW,
            managed.getStatus()
        );

        int updated = em.createQuery(
                """
                UPDATE CustomerOrder o
                SET o.status = :ready
                WHERE o.id = :id
                  AND o.tenantId = :tenantId
                """
            )
            .setParameter("ready", OrderStatus.READY)
            .setParameter("id", id)
            .setParameter("tenantId", 10L)
            .executeUpdate();

        assertEquals(1, updated);

        // Bulk statement thay DB nhưng không thay Java object.
        assertEquals(
            OrderStatus.NEW,
            managed.getStatus()
        );

        CustomerOrder again =
            em.find(CustomerOrder.class, id);

        assertSame(managed, again);
        assertEquals(
            OrderStatus.NEW,
            again.getStatus()
        );

        return null;
    });
}
```

### 9.1. Câu query không hỏng

Database row đã bị UPDATE trong transaction; trạng thái cũ nằm ở Java object đã được load trước đó.

### 9.2. Vì sao find vẫn cũ?

First-level identity map đang giữ managed instance, nên `find` cùng PK không buộc reload database.

### 9.3. Khi nào rủi ro xuất hiện?

Khi một service dùng status cũ để quyết định shipping, billing, cancellation hoặc update fields khác trong cùng transaction.

---

## 10. Bước D: Xác nhận dữ liệu đã commit từ context mới

```java
@Test
void committedBulkUpdate_isVisibleToNewContext() {
    Long id = createNewOrder(10L);

    int changed = JpaTestTx.committed(
        emf,
        em -> em.createQuery(
                """
                UPDATE CustomerOrder o
                SET o.status = :ready
                WHERE o.id = :id
                """
            )
            .setParameter("ready", OrderStatus.READY)
            .setParameter("id", id)
            .executeUpdate()
    );

    assertEquals(1, changed);

    OrderStatus stored = JpaTestTx.committed(
        emf,
        em -> em.find(
            CustomerOrder.class, id
        ).getStatus()
    );

    assertEquals(OrderStatus.READY, stored);
}
```

### 10.1. Không nhầm flush và commit

`flush()` đồng bộ SQL trong transaction; chưa bảo đảm thay đổi bền vững. Chỉ sau commit thành công và fresh readback mới có bằng chứng mạnh hơn về database state.

### 10.2. Nếu bật second-level cache

Một test muốn kiểm trực tiếp DB có thể cần cache bypass/eviction hoặc kiểm JDBC DB state để phân biệt cached read và authoritative read. Cache behavior là một phần riêng cần test.

---

## 11. Cách 1: Refresh một managed entity

```java
@Test
void refresh_loadsLatestPersistentState() {
    Long id = createNewOrder(10L);

    JpaTestTx.committed(emf, em -> {
        CustomerOrder managed =
            em.find(CustomerOrder.class, id);

        CustomerOrder reference = managed;

        em.createQuery(
                """
                UPDATE CustomerOrder o
                SET o.status = :ready
                WHERE o.id = :id
                """
            )
            .setParameter("ready", OrderStatus.READY)
            .setParameter("id", id)
            .executeUpdate();

        assertEquals(
            OrderStatus.NEW,
            managed.getStatus()
        );

        em.refresh(managed);

        assertSame(reference, managed);
        assertTrue(em.contains(managed));
        assertEquals(
            OrderStatus.READY,
            managed.getStatus()
        );

        return null;
    });
}
```

### 11.1. refresh giữ object reference

`refresh(entity)` reload persistent state vào chính managed Java instance đó.

### 11.2. Không dùng trên detached entity

```java
em.detach(managed);
// em.refresh(managed); // Không hợp lệ: không managed.
```

### 11.3. Rủi ro overwrite pending changes

Nếu đã sửa total trong memory nhưng chưa flush, refresh có thể ghi đè nó bằng giá trị database. Không refresh mù quáng khi service đang giữ business edits cần lưu.

### 11.4. Phù hợp khi nào?

Khi cần giữ một vài managed references và muốn dùng state mới sau bulk. Nếu cần refresh hàng chục nghìn objects, phương án này có thể làm mất lợi ích hiệu năng.

---

## 12. Cách 2: Clear rồi tìm lại

```java
@Test
void clear_thenFindGetsFreshManagedInstance() {
    Long id = createNewOrder(10L);

    JpaTestTx.committed(emf, em -> {
        CustomerOrder old =
            em.find(CustomerOrder.class, id);

        em.createQuery(
                """
                UPDATE CustomerOrder o
                SET o.status = :ready
                WHERE o.id = :id
                """
            )
            .setParameter("ready", OrderStatus.READY)
            .setParameter("id", id)
            .executeUpdate();

        em.clear();

        assertFalse(em.contains(old));

        CustomerOrder reloaded =
            em.find(CustomerOrder.class, id);

        assertNotSame(old, reloaded);
        assertTrue(em.contains(reloaded));
        assertEquals(
            OrderStatus.READY,
            reloaded.getStatus()
        );

        return null;
    });
}
```

### 12.1. clear ảnh hưởng toàn context

`EntityManager.clear()` detach mọi managed instances trong persistence context, không chỉ những rows bulk đã thay.

### 12.2. Old reference không tự biến mất

`old` vẫn là Java object trong memory và có thể giữ status cũ, nhưng không còn được managed. Sửa nó sau clear không tự trigger dirty checking.

### 12.3. clear không phải rollback

SQL đã flush vẫn nằm trong transaction; clear không hủy chúng, cũng không commit transaction.

---

## 13. Refresh, clear, detach và context mới: So sánh

| Cách làm | Giữ reference? | Phạm vi | Tác động tới pending changes |
|---|---|---|---|
| `em.refresh(entity)` | Có | Entity/graph được refresh | Có thể overwrite local state |
| `em.detach(entity)` | Object còn, nhưng detached | Một entity theo cascade rules | Unflushed state trên target có thể mất |
| `em.clear()` | Old references thành detached | Toàn context | Unflushed changes có thể mất |
| Close EM, mở EM mới | Managed refs cũ detached | Context mới | Pending changes phải xử lý trước close |
| Commit + fresh read | Không tái sử dụng L1 cũ | Transaction mới | Tách rõ durability boundary |

### 13.1. Đừng dùng merge để reload

`merge(detached)` sao chép state của detached argument vào managed instance. Nếu detached state cũ, merge có thể đưa giá trị cũ vào managed state hoặc gây optimistic conflict. Nó không tương đương `refresh`.

### 13.2. Targeted detach có thể bỏ sót

Khi bulk predicate ảnh hưởng một tập IDs động, chỉ detach một object có thể để lại nhiều managed instances stale. Clear thường dễ lập luận hơn cho batch service độc lập.

---

## 14. Bẫy nguy hiểm: Clear mất pending edits

```java
CustomerOrder managed =
    em.find(CustomerOrder.class, orderId);

managed.changeTotal(
    new BigDecimal("700.00")
);

// Chưa flush total change.
em.clear();

// Old object đã detached; total mới có thể không được ghi.
```

Test:

```java
@Test
void clear_withoutFlush_dropsPendingChange() {
    Long id = createNewOrder(10L);

    JpaTestTx.committed(emf, em -> {
        CustomerOrder order =
            em.find(CustomerOrder.class, id);

        order.changeTotal(
            new BigDecimal("700.00")
        );

        em.clear();

        return null;
    });

    BigDecimal stored = JpaTestTx.committed(
        emf,
        em -> em.find(
            CustomerOrder.class, id
        ).getTotal()
    );

    assertEquals(
        new BigDecimal("100.00"),
        stored
    );
}
```

### 14.1. Vì sao cần test này?

Nó chứng minh một side effect quan trọng của clear: không chỉ làm mất dữ liệu stale mà còn có thể loại bỏ những edits **đúng** chưa được đồng bộ.

### 14.2. Không cố dùng clear như cleanup chung

Nếu một service có nhiều managed entities với các changes chưa commit, việc clear toàn context có thể làm mất state ngoài ý muốn. Tốt hơn là dùng transaction/service boundary chuyên biệt cho bulk job.

---

## 15. Pattern chuẩn: Flush → Bulk UPDATE → Clear

```java
@Transactional
public int promoteTenantOrders(long tenantId) {
    Instant now = Instant.now();

    entityManager.flush();

    int affected = entityManager.createQuery(
            """
            UPDATE CustomerOrder o
            SET o.status = :ready,
                o.updatedAt = :now
            WHERE o.tenantId = :tenantId
              AND o.status = :expected
            """
        )
        .setParameter("ready", OrderStatus.READY)
        .setParameter("now", now)
        .setParameter("tenantId", tenantId)
        .setParameter("expected", OrderStatus.NEW)
        .executeUpdate();

    entityManager.clear();

    return affected;
}
```

### 15.1. Tại sao flush trước?

Để đồng bộ những managed changes phải giữ trước khi bulk SQL đánh giá trạng thái DB. Flush thuộc cùng transaction, chưa phải commit.

### 15.2. Tại sao clear sau?

Để những queries sau đó không tái sử dụng managed snapshots cũ.

### 15.3. Cẩn trọng: flush đồng bộ toàn context

`em.flush()` không chỉ flush một Order; nó có thể phát SQL cho tất cả managed changes trong context. Nếu chưa nên flush một số edits, tách bulk operation ra transaction khác thay vì chỉ chèn flush bừa bãi.

### 15.4. Pattern không giải quyết mọi vấn đề

Nó không tự tăng version, gọi callbacks, phát outbox event, bảo vệ tenant scope hoặc làm invalidation mọi cache.

---

## 16. Test giữ pending change với flush trước bulk

```java
@Test
void flushBeforeBulk_keepsOtherFieldChange() {
    Long id = createNewOrder(10L);

    JpaTestTx.committed(emf, em -> {
        CustomerOrder order =
            em.find(CustomerOrder.class, id);

        order.changeTotal(
            new BigDecimal("800.00")
        );

        em.flush();

        em.createQuery(
                """
                UPDATE CustomerOrder o
                SET o.status = :ready
                WHERE o.id = :id
                """
            )
            .setParameter("ready", OrderStatus.READY)
            .setParameter("id", id)
            .executeUpdate();

        em.clear();

        CustomerOrder fresh =
            em.find(CustomerOrder.class, id);

        assertEquals(
            new BigDecimal("800.00"),
            fresh.getTotal()
        );
        assertEquals(
            OrderStatus.READY,
            fresh.getStatus()
        );

        return null;
    });
}
```

### 16.1. Điều được xác minh

Total change được flush trước khi clear, và status được bulk cập nhật. Entity được reload với state sau hai thao tác.

### 16.2. Version vẫn cần chính sách riêng

Bulk query ví dụ chưa tăng version. Bài test này chứng minh ordering/flush, không phải concurrency safety.

---

## 17. FlushModeType.AUTO và COMMIT

JPA có các flush modes:

```java
em.setFlushMode(FlushModeType.AUTO);
```

và:

```java
em.setFlushMode(FlushModeType.COMMIT);
```

### 17.1. AUTO

Provider đáp ứng visibility semantics của queries với pending state và có thể flush trước query nếu cần. Không nên dựa vào một exact SQL timing chung cho mọi implementations.

### 17.2. COMMIT

Tác động của pending changes lên query execution trước commit có thể không được đảm bảo như AUTO. Nếu bulk WHERE phụ thuộc giá trị vừa sửa trong memory, explicit flush giúp rõ thứ tự.

### 17.3. Không dùng flush mode để tránh hiểu transaction

Một workaround đổi sang AUTO có thể che bug nhưng không bảo đảm mọi clear/refresh path đúng. Hãy thiết kế rõ transaction boundaries và state synchronization.

---

## 18. Vì sao @Version cần được xem xét đặc biệt?

Một versioned entity dùng:

```java
@Version
private long version;
```

Managed update có thể phát SQL logic:

```sql
UPDATE customer_order
SET status = ?, version = ?
WHERE id = ? AND version = ?;
```

JPQL bulk:

```java
UPDATE CustomerOrder o
SET o.status = :ready
WHERE o.status = :expected
```

không tự áp per-entity version increment/optimistic check như managed dirty checking.

### 18.1. Lost-update scenario

```text
Tx A load Order 101: status NEW, version 5
Tx B bulk đổi status READY, version vẫn 5
Tx B commit
Tx A sửa total rồi flush theo version 5
```

Tx A có thể không phát hiện bulk đã thay row; tùy provider SQL, status cũ cũng có thể bị ghi đè. Ngay cả nếu SQL chỉ update total, business logic A vẫn dựa vào status cũ.

### 18.2. Không phải mọi bulk đều cần version bump

Nếu một operation có contract độc lập với entity version, có thể có lý do không bump. Nhưng đây là quyết định thiết kế phải được ghi rõ và kiểm thử, không mặc định.

---

## 19. Version-aware bulk UPDATE

```java
int changed = em.createQuery(
        """
        UPDATE CustomerOrder o
        SET o.status = :ready,
            o.updatedAt = :now,
            o.version = o.version + 1
        WHERE o.tenantId = :tenantId
          AND o.status = :expected
        """
    )
    .setParameter("ready", OrderStatus.READY)
    .setParameter("now", Instant.now())
    .setParameter("tenantId", 10L)
    .setParameter("expected", OrderStatus.NEW)
    .executeUpdate();
```

### 19.1. Tăng version theo từng row

Với numeric version mapping, biểu thức cộng một có thể áp cho từng affected row. Nếu dùng version type tùy biến hoặc provider extensions, kiểm khả năng hỗ trợ với database thực.

### 19.2. Managed instances vẫn stale

Nếu entity nằm trong L1, cả status và version trong Java object vẫn có thể cũ. Version bump không thay §refresh/clear§.

### 19.3. Conflict mong muốn

Một managed writer từ snapshot cũ có thể bị optimistic lock failure tại flush/commit, buộc reload thay vì âm thầm overwrite.

---

## 20. Conditional update như compare-and-set

```java
int promoteOne(
        EntityManager em,
        long orderId,
        long tenantId) {

    return em.createQuery(
            """
            UPDATE CustomerOrder o
            SET o.status = :ready,
                o.version = o.version + 1
            WHERE o.id = :id
              AND o.tenantId = :tenantId
              AND o.status = :expected
            """
        )
        .setParameter("ready", OrderStatus.READY)
        .setParameter("id", orderId)
        .setParameter("tenantId", tenantId)
        .setParameter("expected", OrderStatus.NEW)
        .executeUpdate();
}
```

### 20.1. Ý nghĩa count

- `1`: một order đã transition đúng điều kiện.
- `0`: ID không tồn tại, không trong tenant hoặc không còn NEW.
- Nếu query theo PK trả nhiều hơn 1, cần điều tra nghiêm túc.

### 20.2. CAS giảm race

Hai transactions cùng đọc NEW rồi thực hiện UPDATE không có expected-state predicate có thể cùng xử lý một operation. Conditional UPDATE đưa điều kiện eligibility vào chính DB write.

### 20.3. Không tự suy affected=0 là success của lần trước

Một lần retry trả 0 có thể vì chưa có eligible row hoặc do transaction trước đã commit. Nếu client cần outcome chính xác, dùng operation ID/receipt và reconciliation.

---

## 21. Spring Data JPA @Modifying

Repository:

```java
public interface CustomerOrderRepository
        extends JpaRepository<CustomerOrder, Long> {

    @Modifying
    @Query(
        """
        UPDATE CustomerOrder o
        SET o.status = :ready,
            o.updatedAt = :now
        WHERE o.tenantId = :tenantId
          AND o.status = :expected
        """
    )
    int bulkPromote(
        @Param("tenantId") long tenantId,
        @Param("expected") OrderStatus expected,
        @Param("ready") OrderStatus ready,
        @Param("now") Instant now
    );
}
```

### 21.1. @Modifying làm gì?

Nó đánh dấu một Spring Data repository `@Query` là modification query và gọi execution path phù hợp, thường trả affected count.

### 21.2. Không đồng nghĩa commit

DML phải chạy trong transaction. Service layer là nơi phù hợp giữ toàn use case trong §@Transactional§.

### 21.3. saveAll không phải bulk JPQL

§saveAll§ thường thao tác từng entity qua persist/merge, có semantics và performance khác một JPQL UPDATE ảnh hưởng nhiều rows.

---

## 22. Spring Data flushAutomatically và clearAutomatically

```java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query(
    """
    UPDATE CustomerOrder o
    SET o.status = :ready,
        o.updatedAt = :now,
        o.version = o.version + 1
    WHERE o.tenantId = :tenantId
      AND o.status = :expected
    """
)
int bulkPromoteAndClear(
    @Param("tenantId") long tenantId,
    @Param("expected") OrderStatus expected,
    @Param("ready") OrderStatus ready,
    @Param("now") Instant now
);
```

### 22.1. Hai flags xử lý hai thời điểm

- `flushAutomatically = true`: flush context **trước** modification query.
- `clearAutomatically = true`: clear context **sau** modification query.

### 22.2. Hậu quả của clearAutomatically

Một entity đang managed trước repository call có thể trở thành detached ngay sau call. Service không được tiếp tục sửa object cũ rồi mong dirty checking tự lưu.

### 22.3. Vì sao không mặc định clear luôn?

Clear có thể bỏ pending unflushed changes. Việc framework yêu cầu flag explicit cho thấy cần kiểm soát transaction semantics.

### 22.4. Không thay second-level cache

Những flags này quản lý persistence context, không bảo đảm eviction mọi L2/query/application caches.

---

## 23. Spring service hoàn chỉnh

```java
@Service
public class OrderBatchService {

    private final CustomerOrderRepository repository;

    public OrderBatchService(
            CustomerOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public int promote(long tenantId) {
        // tenantId cần được lấy/kiểm từ trusted scope.
        return repository.bulkPromoteAndClear(
            tenantId,
            OrderStatus.NEW,
            OrderStatus.READY,
            Instant.now()
        );
    }
}
```

### 23.1. Transaction proxy

Nếu gọi §@Transactional§ method từ cùng class qua `this.promote(...)`, Spring proxy có thể không intercept theo proxy-based model. Kiểm service boundary và integration tests.

### 23.2. Không đặt tenantId từ request thành quyền tự động

Trong application multi-tenant, tenant/actor/role phải được server-side security resolver xác minh. API parameter binding không phải authorization.

### 23.3. Service vừa sửa object vừa bulk

Nếu cùng transaction có nhiều managed edits, hai flags có thể ảnh hưởng toàn context. Cân nhắc chuyển bulk job sang một transaction/service scope độc lập.

---

## 24. Spring Data @DataJpaTest: Không nhầm rollback test

```java
@DataJpaTest
class CustomerOrderBulkTest {

    @Autowired
    TestEntityManager tem;

    @Autowired
    CustomerOrderRepository repository;

    @Test
    void bulkClear_detachesOldInstance() {
        CustomerOrder order = new CustomerOrder(
            10L,
            "spring-" + UUID.randomUUID(),
            new BigDecimal("50.00")
        );

        tem.persistAndFlush(order);
        tem.clear();

        CustomerOrder old = tem.find(
            CustomerOrder.class,
            order.getId()
        );

        assertTrue(
            tem.getEntityManager().contains(old)
        );

        repository.bulkPromoteAndClear(
            10L,
            OrderStatus.NEW,
            OrderStatus.READY,
            Instant.now()
        );

        assertFalse(
            tem.getEntityManager().contains(old)
        );

        CustomerOrder fresh = tem.find(
            CustomerOrder.class,
            order.getId()
        );

        assertNotSame(old, fresh);
        assertEquals(
            OrderStatus.READY,
            fresh.getStatus()
        );
    }
}
```

§@DataJpaTest§ thường chạy trong một test-managed transaction được rollback khi test kết thúc. Bài test trên kiểm L1 state và SQL trong test transaction, **không chứng minh commit thật**.

### 24.1. Fixture isolation

Nếu tenant 10 có nhiều NEW orders từ tests khác, affected count có thể lớn hơn 1. Dùng unique tenant hoặc DB reset/test profile riêng.

### 24.2. Commit tests riêng

Khi muốn chứng minh visibility sau commit, dùng TransactionTemplate/TestTransaction hoặc test không nằm trong test-level rollback transaction.

---

## 25. TransactionTemplate: Kiểm committed state trong Spring

```java
@DataJpaTest
@Transactional(
    propagation = Propagation.NOT_SUPPORTED
)
class CommittedOrderBulkTest {

    @Autowired
    EntityManager em;

    @Autowired
    PlatformTransactionManager manager;

    @Test
    void bulkUpdate_commitsAcrossTransactions() {
        TransactionTemplate tx =
            new TransactionTemplate(manager);

        Long id = tx.execute(status -> {
            CustomerOrder order = new CustomerOrder(
                10L,
                "tx-" + UUID.randomUUID(),
                new BigDecimal("90.00")
            );
            em.persist(order);
            em.flush();
            return order.getId();
        });

        Integer affected = tx.execute(status ->
            em.createQuery(
                    """
                    UPDATE CustomerOrder o
                    SET o.status = :ready
                    WHERE o.id = :id
                    """
                )
                .setParameter("ready", OrderStatus.READY)
                .setParameter("id", id)
                .executeUpdate()
        );

        assertEquals(1, affected);

        OrderStatus stored = tx.execute(status -> {
            em.clear();
            return em.find(
                CustomerOrder.class,
                id
            ).getStatus();
        });

        assertEquals(OrderStatus.READY, stored);
    }
}
```

### 25.1. Vì sao cần NOT_SUPPORTED?

Vì `@DataJpaTest` thường tạo một transaction bao cả test. Với test-level transaction không active, hai `TransactionTemplate.execute` calls có commit boundaries rõ.

### 25.2. Cleanup data đã commit

Dùng disposable DB/schema hoặc transaction cleanup. Không mong test framework tự rollback các rows đã commit.

---

## 26. Bulk UPDATE và lifecycle callbacks

Entity mẫu có:

```java
@PreUpdate
void beforeUpdate() {
    preUpdateCalls++;
}
```

Managed entity UPDATE có thể trigger callback; JPQL bulk UPDATE **không** gọi per-entity `@PreUpdate`/`@PostUpdate`.

### 26.1. Điều này ảnh hưởng gì?

Nếu callback gán:
- `updatedAt`.
- `updatedBy`.
- Audit metadata.
- Normalized fields.

thì bulk query phải set explicit những fields cần thiết hoặc có một audit strategy riêng.

### 26.2. @Version tương tự

Bulk UPDATE không mặc định áp versioning như managed entity UPDATE. Tăng version trong DML cần thực hiện có chủ đích.

### 26.3. Domain methods bị bỏ qua

Một method có kiểm trạng thái, số dư, stock hoặc permissions không chạy tự động vì JPQL thay row trong DB. Review business invariants trước khi thay managed updates bằng bulk.

---

## 27. Audit fields trong bulk

Nếu mở rộng entity:

```java
@Column(name = "updated_by")
private Long updatedBy;
```

có thể dùng:

```java
em.createQuery(
    """
    UPDATE CustomerOrder o
    SET o.status = :ready,
        o.updatedAt = :now,
        o.updatedBy = :actorId,
        o.version = o.version + 1
    WHERE o.tenantId = :tenantId
      AND o.status = :expected
    """
)
.setParameter("ready", OrderStatus.READY)
.setParameter("now", now)
.setParameter("actorId", actorId)
.setParameter("tenantId", tenantId)
.setParameter("expected", OrderStatus.NEW)
.executeUpdate();
```

Đoạn này giả định entity đã thực sự khai báo persistent `updatedBy`.

### 27.1. Actor identity phải đáng tin

`actorId` phải được resolve từ authenticated principal hoặc service identity; không lấy arbitrary value của client làm audit author.

### 27.2. Per-row audit log phức tạp hơn

JPQL bulk DML không trả danh sách affected IDs và old values. Nếu cần audit mỗi row, thiết kế query/transaction/DB feature khác, không suy IDs từ affected count.

---

## 28. Tenant scope và điều kiện phân quyền

Sai:

```java
UPDATE CustomerOrder o
SET o.status = :ready
WHERE o.status = :expected
```

Nếu user thuộc tenant 10 gọi query này, nó có thể sửa cả tenant 20.

Đúng hơn:

```java
UPDATE CustomerOrder o
SET o.status = :ready
WHERE o.tenantId = :tenantId
  AND o.status = :expected
```

### 28.1. Tenant condition chưa đủ cho mọi policy

Nếu chỉ Order owner hoặc project editor được sửa, WHERE/action service phải enforce write authorization, không chỉ tenant.

### 28.2. Filter riêng provider không luôn bảo vệ bulk

Hibernate filters và native SQL behavior có thể khác theo version; không mặc định mọi DML path tự áp tenant filter. Explicit predicates hoặc DB Row-Level Security cần được kiểm.

### 28.3. Negative test quan trọng

Tạo một NEW order cho tenant 10 và một NEW order cho tenant 20, chạy bulk tenant 10, commit và readback. Tenant 20 phải không đổi.

---

## 29. Test tenant isolation

```java
@Test
void bulkUpdate_cannotTouchOtherTenant() {
    Long id10 = createNewOrder(10L);
    Long id20 = createNewOrder(20L);

    JpaTestTx.committed(emf, em -> {
        em.createQuery(
                """
                UPDATE CustomerOrder o
                SET o.status = :ready
                WHERE o.tenantId = :tenantId
                  AND o.status = :expected
                """
            )
            .setParameter("ready", OrderStatus.READY)
            .setParameter("tenantId", 10L)
            .setParameter("expected", OrderStatus.NEW)
            .executeUpdate();

        return null;
    });

    JpaTestTx.committed(emf, em -> {
        assertEquals(
            OrderStatus.READY,
            em.find(CustomerOrder.class, id10)
                .getStatus()
        );
        assertEquals(
            OrderStatus.NEW,
            em.find(CustomerOrder.class, id20)
                .getStatus()
        );
        return null;
    });
}
```

Nếu DB không cô lập và tenant 10 có nhiều NEW rows khác, affected count sẽ khác; test vẫn xác nhận hai fixture objects đúng, nhưng nên dùng unique tenant scope hoặc reset schema để tránh side effects sang test khác.

---

## 30. Native SQL có cùng vấn đề đồng bộ

```java
int affected = em.createNativeQuery(
        """
        UPDATE customer_order
        SET status = :ready,
            updated_at = :now
        WHERE tenant_id = :tenantId
          AND status = :oldStatus
        """
    )
    .setParameter("ready", "READY")
    .setParameter("now", now)
    .setParameter("tenantId", tenantId)
    .setParameter("oldStatus", "NEW")
    .executeUpdate();

em.clear();
```

### 30.1. JPQL enum khác physical SQL value

JPQL có thể bind `OrderStatus.READY` và provider map theo annotation. Native SQL dùng database representation trực tiếp. Nếu entity lưu EnumType.ORDINAL/custom converter, literal `'READY'` có thể sai.

### 30.2. Vendor-specific cache synchronization

Một số providers cung cấp hints để đồng bộ/invalidate cache với native SQL. Chúng không thay việc refresh/clear managed state ở L1.

### 30.3. Native SQL phải tự scope

Parameter binding ngăn SQL injection qua values nhưng không tự thêm tenant/ACL predicates.

---

## 31. JPQL UPDATE không phải arbitrary SQL

JPQL bulk DML có UPDATE target entity, SET và WHERE. Không mặc định có thể viết SQL JOIN UPDATE vendor-specific.

Ví dụ SQL đặc thù không phải JPQL portable:

```sql
UPDATE customer_order o
JOIN payment p ON p.order_id = o.id
SET o.status = 'READY'
WHERE p.authorized = true;
```

Một cách JPQL có thể dùng correlated subquery khi mappings cho phép:

```java
em.createQuery(
    """
    UPDATE CustomerOrder o
    SET o.status = :ready
    WHERE o.tenantId = :tenantId
      AND o.status = :newStatus
      AND EXISTS (
          SELECT p.id FROM Payment p
          WHERE p.order = o
            AND p.authorized = true
      )
    """
).executeUpdate();
```

Ví dụ giả định có `Payment` entity với `order` và `authorized` fields, và parameters được bind đầy đủ như các đoạn trước. Query thực phải được kiểm trên provider/DB target.

### 31.1. Khi cần DB-specific RETURNING

Nếu muốn nhận actual affected IDs, có thể dùng native SQL `UPDATE ... RETURNING` hoặc feature tương đương ở database hỗ trợ, nhưng đó không phải API portable mà JPQL `executeUpdate()` cung cấp.

---

## 32. L2 cache và query cache

Sau bulk UPDATE có thể xuất hiện những nguồn stale state khác:

1. L1 managed instance cũ trong EntityManager.
2. L2 cache entity state.
3. Query cache.
4. Application/HTTP cache.
5. Read replica lag.

### 32.1. JPA Cache API

```java
Cache cache = emf.getCache();

cache.evict(CustomerOrder.class, orderId);
```

hoặc:

```java
cache.evict(CustomerOrder.class);
```

`evict` xử lý L2 theo API/provider; **không làm managed instance ở L1 tự cập nhật**.

### 32.2. Bulk invalidation không giống nhau ở mọi provider

Một số ORM có cơ chế invalidation query spaces cho bulk JPQL, nhưng native SQL, stored procedures hoặc external DB writers có thể không được theo dõi đầy đủ. Phải có test và cache policy rõ.

### 32.3. Cache trong multi-tenancy

Cache keys cần tenant-aware identity phù hợp, đặc biệt nếu mỗi tenant có IDs giống nhau trong database/schema khác. Không dùng cache key chỉ gồm ID mà không xét tenant nếu semantics yêu cầu.

---

## 33. Transaction isolation và visibility

```text
Transaction A:
  BEGIN
  Bulk update Order 101 -> READY
  [Chưa COMMIT]

Transaction B:
  SELECT Order 101

Transaction A:
  COMMIT
```

Transaction B có thể thấy committed old state hoặc wait locks trước A commit tùy DB/isolation. Sau commit, một transaction mới đọc authoritative primary DB thường thấy state mới.

### 33.1. Clear không đổi isolation level

`em.clear()` không thay snapshot hoặc row lock semantics. Trong REPEATABLE READ, fresh SELECT trong cùng transaction có thể vẫn chịu snapshot rules.

### 33.2. Read replica có thể lag

Commit thành công trên primary không đồng nghĩa replica đã catch up. Nếu cần read-your-writes/validation tức thì, dùng primary/consistency mechanism phù hợp.

### 33.3. Đừng dùng refresh như commit acknowledgment

Refresh trong transaction hiện tại có thể thấy own uncommitted updates; transaction vẫn có thể rollback.

---

## 34. Rollback sau bulk UPDATE

```java
@Test
void bulkUpdate_thenRollback_keepsOldState() {
    Long id = createNewOrder(10L);

    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        em.createQuery(
                """
                UPDATE CustomerOrder o
                SET o.status = :ready
                WHERE o.id = :id
                """
            )
            .setParameter("ready", OrderStatus.READY)
            .setParameter("id", id)
            .executeUpdate();

        em.clear();

        tx.rollback();

    } finally {
        if (tx.isActive()) {
            tx.rollback();
        }
        em.close();
    }

    OrderStatus stored = JpaTestTx.committed(
        emf,
        check -> check.find(
            CustomerOrder.class, id
        ).getStatus()
    );

    assertEquals(OrderStatus.NEW, stored);
}
```

### 34.1. Count trước rollback không phải committed count

Một query có thể ảnh hưởng 200 rows trong transaction rồi toàn bộ thay đổi bị rollback. Không phát thông báo “200 orders đã hoàn tất” trước khi transaction outcome được xác định.

### 34.2. Sau failure phải tạo context mới

Persistence context sau SQL/transaction failure có thể không đáng tin để đưa ra quyết định business.

---

## 35. Concurrency khi hai writers cùng xử lý NEW orders

```text
Worker A                         Worker B
------------------------------   ------------------------------
Đọc Order 101 NEW                Đọc Order 101 NEW
Conditional UPDATE NEW->READY    Conditional UPDATE NEW->READY
Affected=1                       Affected=0 (nếu A thắng)
COMMIT                           Không publish event trùng
```

Đây là kịch bản minh họa; kết quả phụ thuộc transaction ordering, locks và isolation.

### 35.1. Conditional update là lớp bảo vệ

`WHERE status = NEW` giúp chỉ một transition từ NEW thành READY xảy ra theo thời điểm database xử lý writers.

### 35.2. Đừng gửi side effect dựa trên SELECT trước đó

Nếu cả hai workers SELECT thấy Order 101, chúng không được cùng charge hoặc publish event chỉ vì đã SELECT. Chỉ transaction thực sự claim/update row theo contract mới xử lý side effect.

### 35.3. @Version và state condition bổ trợ nhau

Status condition bảo vệ transition cụ thể; version increment giúp những managed writers khác nhận biết row đã thay đổi.

---

## 36. Idempotent retry và unknown commit outcome

Một lần chạy bulk NEW→READY có thể được retry. Lần đầu cập nhật N rows; lần sau có thể cập nhật 0 nếu không có NEW rows mới.

### 36.1. Idempotent theo status chưa đủ cho toàn workflow

External events, email và payment operations không tự idempotent. Cần operation/event IDs và consumer deduplication.

### 36.2. COMMIT ACK loss

Nếu mất connection ngay lúc commit, client có thể không biết DB đã commit hay rollback. Không suy `exception => rollback` chắc chắn, cũng không suy `affected count > 0 => committed`.

### 36.3. Durable receipt

Nếu application cần trả chính xác kết quả mỗi batch request, có thể ghi một `batch_operation` record có unique operation key và trạng thái/counters cùng transaction, rồi reconcile trên kết nối mới. Cách lưu actual affected IDs phụ thuộc workflow/DB support.

---

## 37. Audit và transactional outbox

Một job chuyển Order READY và phát `OrderReady` events cần đảm bảo events tương ứng committed changes.

### 37.1. JPQL bulk không trả danh sách IDs

`executeUpdate()` trả count. Một SELECT eligible IDs trước khi bulk có thể khác actual affected set khi có concurrency.

### 37.2. Các phương án

- Claim/update IDs theo chunks và ghi outbox records trong transaction.
- Dùng DB-specific RETURNING/OUTPUT nếu cần actual affected IDs và database hỗ trợ.
- Dùng stored procedure/trigger có contract audit rõ.
- Ghi event cấp batch thay per-order event khi business semantics cho phép.

### 37.3. Không publish trước commit

Nếu broker nhận event rồi DB rollback, dữ liệu và event bất nhất. Transactional outbox hoặc cơ chế after-commit với recovery được thiết kế phù hợp hơn.

### 37.4. At-least-once vẫn cần dedup

Outbox publisher có thể gửi lại event sau crash; consumer phải idempotent.

---

## 38. Bulk UPDATE rất lớn: Chia chunks

Một statement sửa hàng triệu rows có thể giữ locks lâu, tạo WAL/redo lớn, tăng replica lag và làm rollback tốn kém.

Một chiến lược:

1. Select một batch IDs đủ điều kiện với stable ordering.
2. Conditional bulk UPDATE `WHERE id IN :ids AND tenantId=:tenantId AND status=NEW`.
3. Commit chunk.
4. Ghi checkpoint/metrics.
5. Lặp lại với batch tiếp theo và retry có giới hạn.

### 38.1. Đừng dùng OFFSET trên tập eligible đang co

Sau khi chuyển trang NEW đầu tiên thành READY, tập NEW giảm. Query trang tiếp theo với OFFSET có thể bỏ qua records. Thường chọn lại first eligible page hoặc dùng keyset/high-water mark, với concurrency semantics đã xác định.

### 38.2. `IN :ids` với list rỗng

Không mặc định mọi JPQL provider/dialect xử lý empty IN list giống nhau. Nếu danh sách IDs rỗng, return 0 trước khi tạo query.

### 38.3. Batch size phải được đo

Dựa vào DB lock waits, transaction p95/p99, WAL, pool usage, replica lag và throughput, không dùng một số duy nhất cho mọi workload.

---

## 39. Bulk DELETE và soft delete cũng có stale context

JPQL bulk DELETE trực tiếp xóa rows, không đi qua `em.remove(managed)` lifecycle từng entity như cascades và callbacks:

```java
int removed = em.createQuery(
        """
        DELETE FROM CustomerOrder o
        WHERE o.tenantId = :tenantId
          AND o.status = :cancelled
        """
    )
    .setParameter("tenantId", tenantId)
    .setParameter("cancelled", OrderStatus.CANCELLED)
    .executeUpdate();

em.clear();
```

### 39.1. Không tự hard-delete Orders

OrderLines, audit history, retention và FKs có thể làm DELETE sai business policy hoặc fail constraints.

### 39.2. Soft delete vẫn là bulk UPDATE

Nếu entity có `deletedAt`, có thể dùng:

```java
UPDATE CustomerOrder o
SET o.deletedAt = :now,
    o.version = o.version + 1
WHERE o.tenantId = :tenantId
  AND o.id IN :ids
  AND o.deletedAt IS NULL
```

Snippet giả định entity mở rộng có persistent `deletedAt`. Các read queries và security policies phải lọc soft-deleted rows đúng action.

### 39.3. Refresh một deleted entity

Nếu row đã bulk DELETE, `refresh` entity tương ứng có thể báo không còn row; khi cần reset context thường clear/reload với not-found handling an toàn hơn.

---

## 40. Bulk thay FK/association tạo stale object graph

Nếu bulk/native SQL đổi `projectId`, `ownerId` hoặc FK:
- Managed entity có thể giữ old association.
- Parent collection đã initialized có thể giữ old child membership.
- Owning/inverse relationship helpers không chạy.
- JPA cascade và orphanRemoval không chạy theo từng entity.
- Tenant consistency có thể bị vi phạm nếu không có proper predicate/constraints.

### 40.1. Targeted refresh có thể chưa đủ

Refresh một child không nhất thiết cập nhật mọi initialized inverse collections của parent. Đánh giá cả graph hoặc clear context.

### 40.2. Ownership/tenant transfer phải là command riêng

Một bulk UPDATE trực tiếp thay tenant/owner không tự kiểm permission, audit và referential integrity. Dùng action-specific authorization + DB constraints.

---

## 41. Hiệu năng: Đo đúng chi phí

| Metric | Mục đích |
|---|---|
| Rows/s | Throughput |
| p50/p95/p99 transaction latency | Tail latency |
| DB CPU/IO/WAL | Physical write cost |
| Row lock waits/deadlocks | Concurrency pressure |
| JDBC round trips | Client/server overhead |
| L1 heap/GC | Managed object overhead |
| SQL executions/batches | So bulk và managed paths |
| Index maintenance | Write amplification |
| Replica lag | Downstream visibility |
| Rollback rate | Stability |
| Affected-count distribution | Eligibility correctness |

### 41.1. Không so thiếu công bằng

Managed update có callbacks/version/audit còn bulk bỏ qua chúng thì hai paths chưa thực hiện cùng business operation. So trên cùng invariants.

### 41.2. Đo toàn transaction

Chỉ đo `executeUpdate()` mà không tính commit hoặc wait locks có thể bỏ sót nút cổ chai.

### 41.3. Flush/clear cũng có chi phí

Một `flush()` có thể đồng bộ nhiều pending entities. Clear toàn context có thể khiến code sau phải query lại, làm tăng total workflow latency.

---

## 42. Test trên database production-like

Với PostgreSQL, một Testcontainers setup có thể như sau:

```java
@Testcontainers
@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
class PostgresBulkIntegrationTest {

    @Container
    static PostgreSQLContainer<?> db =
        new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void config(
            DynamicPropertyRegistry registry) {
        registry.add(
            "spring.datasource.url",
            db::getJdbcUrl
        );
        registry.add(
            "spring.datasource.username",
            db::getUsername
        );
        registry.add(
            "spring.datasource.password",
            db::getPassword
        );
    }
}
```

Đây là skeleton; imports/dependencies/schema setup cần khớp Spring Boot/Testcontainers/JUnit versions và database target. H2 có thể phục vụ smoke tests nhưng không đại diện đầy đủ cho locks, native SQL hoặc type mappings của production DB.

---

## 43. Bảng test cases cần có

| Tình huống | Điều cần kiểm |
|---|---|
| Managed mutation | Getter mới, callback và DB state |
| Bulk update | DB affected; L1 không tự refresh |
| Find cùng EM | Same managed reference stale |
| Refresh | Same reference, state mới |
| Clear | Old detached; new find loads state mới |
| Clear trước flush | Pending changes có thể mất |
| Flush–bulk–clear | Pending edits được giữ |
| Version-aware bulk | Version increment đúng |
| Two EM concurrency | Conflict và final DB state |
| Tenant scope | Tenant khác không đổi |
| @PreUpdate | Bulk không gọi per-entity callback |
| updatedAt/updatedBy | Explicit audit data persisted |
| Native SQL | Cùng rủi ro stale L1 |
| L2/query cache | Invalidation theo policy |
| Rollback | Không có committed bulk change |
| Spring @Modifying | Flags hoạt động như kỳ vọng |
| Spring committed test | Transaction mới đọc committed state |
| Chunking | Không bỏ sót eligible rows |
| Retry/outbox | Không tạo duplicate business effects |

---

## 44. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Bulk count > 0, getter vẫn NEW | L1 managed stale | Refresh hoặc clear/reload |
| Find cùng EM vẫn NEW | Identity map | Fresh context |
| Clear xong mất total change | Chưa flush pending edit | Flush trước clear |
| Old object sau clear không lưu | Detached | Reload managed |
| Bulk không tăng version | Không auto optimistic handling | Explicit version increment |
| Optimistic conflict sau bulk | Snapshot stale | Rollback/reload/retry |
| updatedAt không đổi | Callback bị bỏ qua | SET field trong DML |
| Tenant khác bị thay | Thiếu tenant predicate | Security regression test |
| `TransactionRequiredException` | Không active transaction | Service transaction |
| Count ít hơn expected | Concurrent writer/eligibility | Conditional DML, telemetry |
| Query cache stale | Invalidation thiếu | Cache policy |
| Native SQL enum sai | Physical representation khác | Map DB values đúng |
| Bulk giữ locks lâu | Transaction quá lớn | Chunks/throttling |
| Job bỏ qua rows | OFFSET trên shrinking set | Keyset/first page |
| Events trùng | Retry thiếu idempotency | Outbox/dedup |
| FK lỗi khi bulk delete | Không chạy cascades | DB constraints/action policy |
| Spring test đọc được nhưng production không | Test rollback/DB dialect khác | Commit + DB target tests |

---

## 45. Bài tập thực hành

### Bài 1. `executeUpdate()` có đổi getter của loaded entity?

**Đáp án:** Không bảo đảm. Bulk DML không tự cập nhật managed instances.

### Bài 2. Vì sao find cùng ID sau bulk vẫn thấy cũ?

**Đáp án:** First-level cache có thể trả lại same managed instance.

### Bài 3. Khi nào dùng refresh?

**Đáp án:** Khi cần giữ một managed reference và reload state từ database.

### Bài 4. Khi nào dùng clear?

**Đáp án:** Khi muốn bỏ stale managed state toàn context, rồi query lại khi cần.

### Bài 5. Clear có commit không?

**Đáp án:** Không. Clear chỉ detach managed objects.

### Bài 6. Clear khi còn unflushed changes?

**Đáp án:** Có thể mất pending changes.

### Bài 7. Pattern an toàn phổ biến?

**Đáp án:** Flush những thay đổi cần giữ, bulk UPDATE, rồi clear hoặc refresh theo mục đích.

### Bài 8. Flush có chỉ xử lý một entity không?

**Đáp án:** Không; flush có thể đồng bộ pending changes của toàn context.

### Bài 9. `@Modifying` trên Spring Data?

**Đáp án:** Dùng cho modifying `@Query` như UPDATE/DELETE.

### Bài 10. `flushAutomatically`?

**Đáp án:** Flush trước modification query.

### Bài 11. `clearAutomatically`?

**Đáp án:** Clear context sau modification query.

### Bài 12. `@Modifying` tự commit?

**Đáp án:** Không thay active transaction requirement.

### Bài 13. Bulk gọi `@PreUpdate` từng row không?

**Đáp án:** Không theo managed per-entity lifecycle.

### Bài 14. Bulk tự tăng @Version?

**Đáp án:** Không như managed update; nếu cần version bump phải explicit.

### Bài 15. Vì sao dùng `version = version + 1`?

**Đáp án:** Để stale managed writers có thể bị optimistic conflict.

### Bài 16. Affected count = 0 nghĩa là gì?

**Đáp án:** Row không tồn tại, không trong scope hoặc không còn đủ điều kiện; tùy business contract.

### Bài 17. Tenant ID trong WHERE?

**Đáp án:** Giữ tenant isolation và phải đến từ trusted context.

### Bài 18. JDBC batching có giống JPQL bulk?

**Đáp án:** Không. Một cơ chế gom nhiều SQL executions, cơ chế kia là DML sửa nhiều rows.

### Bài 19. Native SQL có tự đồng bộ L1?

**Đáp án:** Không.

### Bài 20. Merge detached old object để lấy state mới?

**Đáp án:** Sai. Merge copy detached state; dùng fresh find/refresh.

### Bài 21. Bulk cần phát event mỗi row?

**Đáp án:** Xác định actual affected IDs và ghi outbox cùng transaction.

### Bài 22. Retry NEW→READY?

**Đáp án:** Conditional status giúp idempotent về transition nhưng external effects vẫn cần dedup.

### Bài 23. Vì sao OFFSET nguy hiểm khi job chuyển NEW→READY?

**Đáp án:** Eligible set co lại, OFFSET có thể bỏ qua rows.

### Bài 24. Evict L2 có refresh managed L1 entity?

**Đáp án:** Không.

### Bài 25. Read replica sau commit?

**Đáp án:** Có thể stale do replica lag; clear L1 không giải quyết.

### Bài 26. Bulk DELETE có gọi @PreRemove từng entity?

**Đáp án:** Không theo per-entity lifecycle.

### Bài 27. @DataJpaTest có commit mặc định?

**Đáp án:** Thường rollback test transaction cuối test.

### Bài 28. Cần test commit thật trong Spring?

**Đáp án:** Dùng TransactionTemplate/TestTransaction hoặc transaction boundaries phù hợp.

### Bài 29. Bulk đổi FK ảnh hưởng gì?

**Đáp án:** Managed associations/collections có thể stale, JPA helpers/cascades không chạy.

### Bài 30. Update hàng triệu rows?

**Đáp án:** Chia chunks, kiểm locks/WAL/lag, checkpoint và retry có kiểm soát.

---

## 46. Checklist triển khai

1. Có lý do dùng bulk thay managed update?
2. Có active transaction rõ ràng?
3. Có tenant/owner/ACL predicates?
4. Có expected state condition?
5. Có bảo vệ DB constraints/business invariants?
6. Có hiểu callbacks không chạy?
7. Có explicit updatedAt/updatedBy nếu cần?
8. Có chính sách version increment?
9. Có flush pending changes trước bulk khi cần?
10. Có clear/refresh L1 sau bulk?
11. Có tránh dùng old detached references?
12. Có tránh merge state cũ thay reload?
13. Có kiểm L2/query/application caches?
14. Có handling ảnh hưởng association graph?
15. Có affected-count contract?
16. Có empty-IN handling?
17. Có idempotency cho retries?
18. Có outbox cho external effects?
19. Có chunking và timeouts?
20. Có tránh OFFSET pagination trên tập co?
21. Có test rollback sau bulk?
22. Có fresh-context readback sau commit?
23. Có concurrency test với hai EM?
24. Có negative cross-tenant tests?
25. Có native SQL/dialect tests nếu dùng?
26. Có test Spring @Modifying flags?
27. Có biết @DataJpaTest rollback mặc định?
28. Có cleanup committed fixtures?
29. Có metrics SQL counts, rows/s, p95/p99, lock waits và WAL?
30. Có runbook khi data outcome không rõ?

---

## 47. Kết luận

**Bulk UPDATE trong JPA đổi database state, không đổi toàn bộ Java managed state theo cách một vòng lặp setters/dirty checking vẫn làm.** Vì vậy, ứng dụng phải chủ động xử lý sự lệch nhau giữa persistence context và database.

Các nguyên tắc quan trọng:

1. JPQL/native bulk UPDATE không tự đồng bộ managed entities trong L1.
2. `find()` cùng ID trong cùng context có thể trả stale instance.
3. `refresh(managed)` reload state vào cùng reference; `clear()` detach toàn context.
4. Clear có thể bỏ unflushed changes, nên **flush trước bulk và clear sau bulk** là pattern phổ biến khi cần bảo toàn changes và bỏ stale state.
5. Spring Data JPA hỗ trợ `@Modifying(flushAutomatically=true, clearAutomatically=true)`, nhưng vẫn cần transaction boundary đúng.
6. Bulk DML không tự gọi callbacks/domain methods hoặc auto-version như managed update; audit fields và version increment phải có chính sách riêng.
7. Conditional WHERE, tenant/ACL predicates và DB constraints giữ business correctness/security.
8. Affected count không cho biết exact affected IDs; outbox/audit/retries cần workflow transaction-aware.
9. Với operations lớn, chunking, checkpoint và đo DB locks/WAL giúp giới hạn impact.
10. Test cuối phải **commit rồi đọc lại từ một persistence context độc lập**, đồng thời kiểm negative tenant cases và optimistic concurrency.

Quy tắc thực hành ngắn gọn: **đồng bộ những thay đổi đang chờ trước bulk, bỏ hoặc làm mới managed state cũ sau bulk, rồi xác nhận database state sau commit bằng transaction mới**. Khi kết hợp đúng version, quyền truy cập, audit và idempotency, bulk UPDATE có thể tối ưu hiệu năng ghi mà vẫn bảo toàn tính đúng dữ liệu.
