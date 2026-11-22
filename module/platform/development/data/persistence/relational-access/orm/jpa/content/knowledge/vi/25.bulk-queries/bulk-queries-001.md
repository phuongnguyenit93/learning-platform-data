# Cập nhật hàng loạt bằng JPQL UPDATE trong JPA

Trong nhiều hệ thống dữ liệu quan hệ, ứng dụng thường cần thay đổi **nhiều bản ghi cùng lúc** theo một điều kiện chung. Ví dụ: hết hạn hàng nghìn đơn đặt hàng chưa thanh toán, khóa các tài khoản quá hạn, chuyển trạng thái của một nhóm phiếu xử lý, điều chỉnh một mức phí, hoặc đánh dấu các thông báo đã được đọc.

Cách đầu tiên dễ nghĩ tới là tải mọi entity bằng JPA, lặp qua từng object rồi gọi setter:

~~~java
List<PurchaseOrder> orders = em.createQuery(
        "SELECT o FROM PurchaseOrder o " +
        "WHERE o.status = :status AND o.expiresAt < :now",
        PurchaseOrder.class
    )
    .setParameter("status", OrderStatus.PENDING)
    .setParameter("now", now)
    .getResultList();

for (PurchaseOrder order : orders) {
    order.expire();
}
~~~

Cách này có lợi vì từng entity được quản lý bởi persistence context, vòng đời entity và dirty checking. Nhưng nếu có hàng trăm nghìn bản ghi, việc tải entity, giữ chúng trong bộ nhớ và sinh nhiều UPDATE có thể tốn tài nguyên.

**JPQL bulk UPDATE** cho phép mô tả thao tác cập nhật trực tiếp trên tập entity khớp điều kiện, **không cần tải từng entity lên Java để sửa**:

~~~java
int affected = em.createQuery(
        "UPDATE PurchaseOrder o " +
        "SET o.status = :expired " +
        "WHERE o.status = :pending " +
        "AND o.expiresAt < :now"
    )
    .setParameter("expired", OrderStatus.EXPIRED)
    .setParameter("pending", OrderStatus.PENDING)
    .setParameter("now", now)
    .executeUpdate();
~~~

Câu lệnh ở trên diễn đạt một thao tác cập nhật hàng loạt ở mức entity. JPA provider dịch nó sang SQL phù hợp với mapping và database. Đây là một công cụ mạnh, nhưng cũng có đánh đổi quan trọng:

- **Không đi qua setter hay lifecycle callbacks của từng entity** theo cách sửa entity managed.
- **Không tự đồng bộ trạng thái những entity đã nằm trong persistence context.**
- **Không tự áp dụng optimistic-lock version checks như thao tác cập nhật entity thông thường.**
- **Vẫn phải chạy trong transaction và tuân thủ constraint của database.**
- **Số kết quả từ `executeUpdate()` là số entity chịu tác động theo ngữ nghĩa JPA**, không được nhầm với một cam kết về số SQL statement vật lý hoặc số row trên mọi bảng khi dùng inheritance.

Bài học này tập trung vào việc **khi nào dùng JPQL UPDATE hàng loạt, cách viết an toàn, hiểu chính xác kết quả, phối hợp transaction/persistence context, bảo vệ dữ liệu đồng thời và kiểm thử những rủi ro phát sinh**.

## 1. Bài toán minh họa: Đơn hàng chờ thanh toán hết hạn

Giả sử hệ thống bán hàng có đơn đặt hàng ở các trạng thái:

~~~text
PENDING   - Đang chờ thanh toán
PAID      - Đã thanh toán
EXPIRED   - Hết thời hạn thanh toán
CANCELLED - Đã hủy
~~~

Hệ thống chạy một job định kỳ để chuyển những đơn **PENDING** đã quá thời hạn thành **EXPIRED**.

Ví dụ dữ liệu:

| ID | Tenant | Trạng thái | Hết hạn lúc | Kết quả sau job tại 10:00 |
|---:|---:|---|---|---|
| 101 | 7 | PENDING | 09:30 | EXPIRED |
| 102 | 7 | PENDING | 11:00 | Giữ PENDING |
| 103 | 7 | PAID | 09:00 | Giữ PAID |
| 104 | 7 | CANCELLED | 08:00 | Giữ CANCELLED |
| 105 | 8 | PENDING | 09:00 | Không sửa nếu job chỉ xử lý tenant 7 |

Từ yêu cầu trên có ít nhất bốn điều kiện nghiệp vụ:

1. Chỉ cập nhật entity của **tenant được phép**.
2. Chỉ cập nhật đơn đang **PENDING**.
3. Chỉ cập nhật đơn có `expiresAt < now`.
4. Không thay đổi đơn đã **PAID**, kể cả khi thời gian hết hạn đã qua.

Đây là use case phù hợp với bulk UPDATE vì nhiều row cùng nhận một biến đổi đơn giản, không đòi hỏi tải object để gọi các phương thức nghiệp vụ riêng trên từng đơn.

### 1.1. SQL tương đương về ý tưởng

~~~sql
UPDATE purchase_order
SET status = 'EXPIRED'
WHERE tenant_id = 7
  AND status = 'PENDING'
  AND expires_at < :now;
~~~

JPQL viết bằng **entity và field Java**:

~~~jpql
UPDATE PurchaseOrder o
SET o.status = :expired
WHERE o.tenantId = :tenantId
  AND o.status = :pending
  AND o.expiresAt < :now
~~~

Câu JPQL không dùng tên bảng `purchase_order`, cột `tenant_id` hoặc `expires_at`; provider chuyển entity mapping thành SQL thích hợp.

## 2. Mapping entity và schema làm ví dụ

Để các ví dụ nhất quán, giả sử có entity `PurchaseOrder`.

~~~java
package com.example.shop.domain;

public enum OrderStatus {
    PENDING,
    PAID,
    EXPIRED,
    CANCELLED
}
~~~

Entity:

~~~java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    @Column(name = "version", nullable = false)
    private long version;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "order_number", nullable = false, unique = true)
    private String orderNumber;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 20)
    private OrderStatus status;

    @Column(name = "expires_at", nullable = false)
    private Instant expiresAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @Column(name = "total_amount", nullable = false,
            precision = 14, scale = 2)
    private BigDecimal totalAmount;

    @Column(name = "retry_count", nullable = false)
    private int retryCount;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    protected PurchaseOrder() {
    }

    public Long getId() {
        return id;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public long getVersion() {
        return version;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }

    public void expire(Instant now) {
        if (status != OrderStatus.PENDING) {
            throw new IllegalStateException(
                "Only pending orders can expire"
            );
        }
        if (!expiresAt.isBefore(now)) {
            throw new IllegalStateException(
                "Order has not expired"
            );
        }
        status = OrderStatus.EXPIRED;
        updatedAt = now;
    }
}
~~~

Giả sử `Customer` là một entity được mapping riêng. Trường `@Version` được đưa vào để so sánh optimistic locking giữa cập nhật thông thường và bulk UPDATE.

DDL PostgreSQL minh họa:

~~~sql
CREATE TABLE purchase_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    version BIGINT NOT NULL DEFAULT 0,
    tenant_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL REFERENCES customer(id),
    order_number VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    total_amount NUMERIC(14, 2) NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT ck_nonnegative_total CHECK (total_amount >= 0),
    CONSTRAINT ck_nonnegative_retry CHECK (retry_count >= 0)
);

CREATE INDEX idx_order_expiration
ON purchase_order(
    tenant_id,
    status,
    expires_at
);
~~~

DDL và code chỉ phục vụ bài học. Ứng dụng thực tế cần migration, entity Customer, quy tắc version, auditing và quản lý thời gian phù hợp DB/provider.

## 3. Cú pháp cơ bản của JPQL UPDATE

Một JPQL bulk UPDATE thông thường có cấu trúc:

~~~jpql
UPDATE EntityName alias
SET alias.field1 = expression1,
    alias.field2 = expression2
WHERE condition
~~~

Ví dụ:

~~~jpql
UPDATE PurchaseOrder o
SET o.status = :newStatus,
    o.updatedAt = :changedAt
WHERE o.status = :oldStatus
  AND o.expiresAt < :cutoff
~~~

Ý nghĩa:

- `UPDATE PurchaseOrder`: cập nhật tập entity thuộc abstract schema type `PurchaseOrder`.
- `o`: identification variable/alias được dùng trong JPQL.
- `SET`: gán các thuộc tính có thể cập nhật.
- `:newStatus`, `:changedAt`, `:oldStatus`, `:cutoff`: named parameters.
- `WHERE`: giới hạn đối tượng bị cập nhật.

### 3.1. Không dùng tên bảng hoặc tên cột SQL trong JPQL

Sai nếu entity tên `PurchaseOrder`:

~~~jpql
UPDATE purchase_order
SET status = 'EXPIRED'
WHERE expires_at < :now
~~~

Đây là kiểu SQL theo schema, không phải JPQL chuẩn. JPQL phải dùng:

~~~jpql
UPDATE PurchaseOrder o
SET o.status = :expired
WHERE o.expiresAt < :now
~~~

Nếu muốn viết bằng tên bảng/cột, dùng `createNativeQuery(...)` thay vì `createQuery(...)`.

### 3.2. Một bulk UPDATE nhắm tới một entity type

JPQL UPDATE thay đổi những entity thuộc một abstract schema type ở mỗi statement. Nó không có cú pháp cập nhật nhiều entity root độc lập như một số SQL dialect hỗ trợ.

Nếu domain cần cập nhật PurchaseOrder và Inventory trong cùng use case, có thể cần **hai thao tác** trong **cùng transaction**, kèm thiết kế concurrency/constraint thích hợp. Không biến hai bảng thành một JPQL UPDATE tưởng tượng.

### 3.3. WHERE là tùy chọn cú pháp, nhưng rất nguy hiểm nếu bỏ vô ý

Câu:

~~~jpql
UPDATE PurchaseOrder o
SET o.status = :newStatus
~~~

có thể cập nhật **mọi PurchaseOrder** nằm trong phạm vi entity type. Đây chỉ là thao tác hợp lệ khi nghiệp vụ thực sự muốn sửa toàn bộ tập.

Đối với job hoặc API thông thường, hãy coi `WHERE` với scope rõ ràng là phần bắt buộc của thiết kế. Đặc biệt trong hệ thống multi-tenant, thiếu `tenantId` có thể gây sự cố nghiêm trọng.

## 4. Tạo và thực thi bulk UPDATE bằng EntityManager

Code đầy đủ cho chức năng hết hạn đơn:

~~~java
public int expirePendingOrders(
        EntityManager em,
        long tenantId,
        Instant now) {

    String jpql = """
        UPDATE PurchaseOrder o
        SET o.status = :expired,
            o.updatedAt = :changedAt
        WHERE o.tenantId = :tenantId
          AND o.status = :pending
          AND o.expiresAt < :now
        """;

    Query query = em.createQuery(jpql);

    query.setParameter(
        "expired", OrderStatus.EXPIRED
    );
    query.setParameter(
        "changedAt", now
    );
    query.setParameter(
        "tenantId", tenantId
    );
    query.setParameter(
        "pending", OrderStatus.PENDING
    );
    query.setParameter(
        "now", now
    );

    return query.executeUpdate();
}
~~~

Ở đây:

1. `EntityManager.createQuery(...)` tạo **JPQL** query.
2. `Query.setParameter(...)` bind các giá trị.
3. `executeUpdate()` thực thi JPQL bulk UPDATE.
4. Kết quả là một số nguyên biểu thị **số entity được cập nhật** theo ngữ nghĩa JPA.
5. Transaction owner chịu trách nhiệm commit hoặc rollback.

Nếu ứng dụng dùng Java phiên bản không có text blocks, có thể nối chuỗi string như các ví dụ khác; đó không phải khác biệt về JPA.

### 4.1. Vì sao dùng named parameters?

Với JPQL, named parameters được chuẩn JPA hỗ trợ:

~~~java
query.setParameter("pending", OrderStatus.PENDING);
~~~

Cách này dễ đọc và giảm rủi ro đảo thứ tự tham số trong query dài.

Có thể dùng positional parameters của JPQL:

~~~jpql
UPDATE PurchaseOrder o
SET o.status = ?1
WHERE o.status = ?2
~~~

và:

~~~java
query.setParameter(1, OrderStatus.EXPIRED);
query.setParameter(2, OrderStatus.PENDING);
~~~

Nhưng đối với bulk UPDATE có nhiều điều kiện, named parameters thường rõ ý định hơn.

### 4.2. Không cần `getResultList()`

Sai:

~~~java
query.getResultList();
~~~

cho một UPDATE query. Bulk DML không trả danh sách entity được thay đổi qua cách gọi đó.

Đúng:

~~~java
int affected = query.executeUpdate();
~~~

Nếu ứng dụng cần danh sách ID đã thay đổi, JPQL bulk UPDATE chuẩn không cung cấp một cơ chế portable tương đương `UPDATE ... RETURNING` của một số DB. Cần thiết kế quy trình khác hoặc dùng native SQL/provider-specific feature có kiểm chứng.

## 5. `executeUpdate()` trả về gì?

Theo API JPA, `Query.executeUpdate()` áp dụng cho update/delete statement và trả về **số entity được cập nhật hoặc xóa** theo ngữ nghĩa query.

Ví dụ:

~~~java
int affected = em.createQuery(
        "UPDATE PurchaseOrder o " +
        "SET o.status = :expired " +
        "WHERE o.status = :pending " +
        "AND o.expiresAt < :now"
    )
    .setParameter("expired", OrderStatus.EXPIRED)
    .setParameter("pending", OrderStatus.PENDING)
    .setParameter("now", now)
    .executeUpdate();
~~~

Diễn giải:

| Giá trị | Ý nghĩa |
|---|---|
| `0` | Không có entity nào khớp thao tác cập nhật theo kết quả thực thi |
| `1` | Một entity được cập nhật |
| `27` | Hai mươi bảy entity được cập nhật |
| `n > 0` | Có đối tượng bị tác động, nhưng chưa chứng minh transaction đã commit |

### 5.1. `affected = 0` không luôn là lỗi

Trong job chạy định kỳ, việc không có đơn nào hết hạn có thể hoàn toàn bình thường:

~~~java
int expired = expirePendingOrders(
    em, tenantId, now
);

if (expired == 0) {
    // Không có đơn phù hợp để chuyển trạng thái.
}
~~~

Nhưng trong thao tác sửa một Order cụ thể, `0` có thể có nghĩa ID không tồn tại, sai trạng thái, sai tenant hoặc entity đã bị transaction khác cập nhật. Cần hiểu use case trước khi phân loại là lỗi.

### 5.2. Không nhầm số entity với số SQL vật lý

Với entity inheritance được ánh xạ qua nhiều bảng, provider có thể cần nhiều câu SQL vật lý. Kết quả `executeUpdate()` theo ngữ nghĩa JPA là số **entity** chịu tác động, không phải cam kết rằng hệ thống chỉ gửi một SQL statement trong mọi kiểu mapping.

Đối với mapping một bảng đơn giản, thường có một câu `UPDATE purchase_order ...`. Nhưng ứng dụng không nên phụ thuộc vào số SQL nếu chưa quan sát provider thực tế.

### 5.3. Update không phải SELECT những entity bị tác động

Kết quả `27` không mang theo 27 Order ID hay object. Nếu cần audit theo từng Order, thông báo event cho từng Order hoặc gọi quy tắc nghiệp vụ khác nhau trên mỗi object, bulk UPDATE một mình có thể không đáp ứng yêu cầu.

## 6. Transaction là điều kiện bắt buộc

Bulk UPDATE thay đổi database, vì vậy phải được thực thi trong transaction phù hợp.

Ví dụ JPA resource-local:

~~~java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    int changed = expirePendingOrders(
        em,
        tenantId,
        Instant.now()
    );

    tx.commit();

    System.out.println("Expired orders: " + changed);

} catch (RuntimeException error) {
    if (tx.isActive()) {
        try {
            tx.rollback();
        } catch (RuntimeException rollbackError) {
            error.addSuppressed(rollbackError);
        }
    }
    throw error;
} finally {
    em.close();
}
~~~

**Chú ý:** Mẫu này dành cho persistence unit kiểu `RESOURCE_LOCAL`. Với JTA/container-managed EntityManager hoặc Spring-managed transaction, transaction owner là container/framework; không tự gọi `em.getTransaction().begin()` trên JTA EntityManager.

### 6.1. Không có transaction thì sao?

Khi gọi bulk `executeUpdate()` ngoài transaction hợp lệ, JPA có thể ném `TransactionRequiredException`.

Không giải quyết bằng cách bắt exception rồi trả `0`, vì đó sẽ che lỗi hạ tầng và khiến job báo “không có bản ghi” dù thực tế chưa thực hiện câu UPDATE nào.

### 6.2. `executeUpdate()` không đồng nghĩa `commit()`

Một ví dụ:

~~~text
BEGIN
  UPDATE purchase_order
    SET status='EXPIRED'
    WHERE ...
  -> executeUpdate() trả 50

ROLLBACK
  -> Các thay đổi có thể bị hủy
~~~

SQL được thực thi nhưng transaction chưa được xác nhận. Chỉ sau commit thành công, thay đổi mới được ghi nhận bền vững theo quy tắc DB.

### 6.3. Transaction phải bao trùm các thay đổi liên quan

Nếu nghiệp vụ cần:

1. Chuyển Order thành EXPIRED.
2. Trả lại reservation trong Inventory.
3. Ghi sự kiện outbox.

thì không được tự ý commit bước 1 riêng rồi mới thử 2, 3 nếu yêu cầu tất cả hoặc không có gì. Cần một transaction phù hợp cho các thay đổi trong cùng database; với tài nguyên phân tán, thiết kế outbox/saga theo yêu cầu hệ thống.

## 7. Spring `@Transactional` với bulk JPQL UPDATE

Trong Spring, application service có thể là transaction owner:

~~~java
@Service
public class OrderExpirationService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public int expire(long tenantId, Instant now) {

        return em.createQuery(
                "UPDATE PurchaseOrder o " +
                "SET o.status = :expired, " +
                "o.updatedAt = :now " +
                "WHERE o.tenantId = :tenantId " +
                "AND o.status = :pending " +
                "AND o.expiresAt < :now"
            )
            .setParameter("expired", OrderStatus.EXPIRED)
            .setParameter("pending", OrderStatus.PENDING)
            .setParameter("tenantId", tenantId)
            .setParameter("now", now)
            .executeUpdate();
    }
}
~~~

Import minh họa:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
~~~

Spring `@Transactional` ở đây có ý nghĩa khi transaction infrastructure được cấu hình và method được gọi qua cơ chế interceptor phù hợp.

### 7.1. Repository return không phải là commit của outer transaction

Nếu service trên tham gia một transaction do một method khác mở, `expire()` trả về `100` chưa chứng minh outer transaction đã commit.

Không phát hành thông báo “100 đơn đã hết hạn chắc chắn” tới hệ thống ngoài trước khi commit nếu quy tắc tích hợp yêu cầu độ đúng giao dịch.

### 7.2. Không dùng `readOnly = true` cho bulk DML

~~~java
@Transactional(readOnly = true)
public int expire(...) {
    // Bulk UPDATE
}
~~~

là cấu hình trái ý định. Tùy transaction manager, provider và DB, read-only có thể dẫn đến hạn chế ghi hoặc hành vi tối ưu khác. DML phải chạy trong transaction cho phép ghi.

## 8. Bulk UPDATE khác sửa entity managed như thế nào?

Đây là khác biệt quan trọng nhất của bài.

### 8.1. Cập nhật từng entity

~~~java
PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);

order.expire(now);
~~~

Trong transaction, JPA quản lý dirty checking và vòng đời entity:

~~~text
SELECT Order
    |
    v
Managed Java object
    |
    v
order.expire(now)
    |
    v
Dirty checking ở flush
    |
    v
UPDATE với optimistic version handling
    |
    v
Commit / rollback
~~~

Các entity callbacks như `@PreUpdate`/`@PostUpdate` có thể được gọi theo quy tắc lifecycle khi provider cập nhật entity. Bean Validation cũng có thể được tích hợp ở thời điểm lifecycle tương ứng.

### 8.2. Bulk JPQL UPDATE

~~~java
em.createQuery(
    "UPDATE PurchaseOrder o SET o.status = :expired " +
    "WHERE o.status = :pending"
)
.setParameter("expired", OrderStatus.EXPIRED)
.setParameter("pending", OrderStatus.PENDING)
.executeUpdate();
~~~

Luồng:

~~~text
JPQL UPDATE + parameters
          |
          v
Provider dịch thành SQL DML
          |
          v
Database cập nhật row phù hợp
          |
          v
executeUpdate() trả số entity
          |
          v
Entity đã managed trong memory:
KHÔNG được tự đồng bộ từng field
~~~

### 8.3. Bảng so sánh

| Khía cạnh | Sửa entity managed | JPQL bulk UPDATE |
|---|---|---|
| Tải entity vào memory | Thường có | Không cần |
| Dirty checking | Có | Không cho từng entity bị cập nhật |
| Domain method/invariant | Có thể áp dụng | Không được tự gọi |
| `@PreUpdate` / `@PostUpdate` mỗi entity | Theo entity lifecycle | **Không** |
| Optimistic version update theo ORM | Thường được JPA quản lý | **Không tự động** |
| Persistence context | State entity managed được theo dõi | Có thể trở nên stale |
| Khả năng update nhiều entity | Lặp/batch theo provider | Một bulk operation ở mức JPQL |
| Tối ưu resource cho biến đổi đơn giản | Có thể tốn nhiều entity | Thường có lợi |
| Audit riêng từng entity | Có thể tích hợp callback/domain event | Cần thiết kế audit riêng |
| Quy tắc liên kết/cascade | Theo mapping/lifecycle | Không tương đương cascade entity-level |
| Độ khó concurrency | JPA giúp một phần | Ứng dụng phải thiết kế rõ |

Không có lựa chọn luôn tốt hơn. Bulk UPDATE phù hợp cho **biến đổi tập hợp đơn giản và có thể diễn đạt đầy đủ bằng WHERE/SET**. Cập nhật entity managed phù hợp khi mỗi bản ghi cần hành vi nghiệp vụ và lifecycle riêng.

## 9. Mặt trái: Persistence context có thể giữ dữ liệu cũ

Giả sử trong cùng EntityManager:

~~~java
PurchaseOrder order =
    em.find(PurchaseOrder.class, 101L);

System.out.println(order.getStatus()); // PENDING
~~~

Sau đó:

~~~java
em.createQuery(
    "UPDATE PurchaseOrder o " +
    "SET o.status = :expired " +
    "WHERE o.id = :id"
)
.setParameter("expired", OrderStatus.EXPIRED)
.setParameter("id", 101L)
.executeUpdate();
~~~

Database row có thể đã chuyển sang EXPIRED, nhưng object đang managed:

~~~java
System.out.println(order.getStatus());
~~~

vẫn có thể in `PENDING`.

Sơ đồ:

~~~text
Persistence context:
  PurchaseOrder#101.status = PENDING

Database (trong transaction):
  purchase_order#101.status = EXPIRED

=> Hai trạng thái không tự đồng bộ.
~~~

### 9.1. Vì sao JPA không tự sửa managed entities?

Bulk DML được áp dụng ở tầng database. Provider không bắt buộc duyệt toàn bộ persistence context, tìm các object khớp WHERE rồi gọi setter và cập nhật snapshot của từng object.

Đó chính là một phần lợi thế hiệu năng của bulk UPDATE, nhưng cũng tạo rủi ro state stale.

### 9.2. Query SELECT tiếp theo có thể trả object cũ

Ngay cả khi sau bulk UPDATE ứng dụng gọi:

~~~java
PurchaseOrder again =
    em.find(PurchaseOrder.class, 101L);
~~~

`again` có thể là chính instance đã managed từ trước theo identity map, vẫn có field cũ. Việc gọi `find` không tự bảo đảm refresh vì database đã thay đổi qua bulk query.

### 9.3. Hậu quả khi tiếp tục sửa managed object cũ

Nếu ứng dụng tiếp tục sửa field khác trên managed entity rồi flush, provider có thể phát sinh UPDATE trên snapshot/state cũ. Tùy mapping/versioning và SQL UPDATE được sinh, điều này có thể:

- Ghi đè trạng thái database vừa cập nhật bulk.
- Gây optimistic lock conflict.
- Đưa ra quyết định nghiệp vụ dựa trên trạng thái lỗi thời.
- Làm audit hoặc cache không phản ánh đúng sự kiện.

Không dựa vào một instance managed cũ sau bulk UPDATE trên cùng dữ liệu khi chưa có quy trình đồng bộ.

## 10. Các chiến lược xử lý persistence context

Có ba nhóm lựa chọn: **tránh managed state cũ**, **làm mới entity cần dùng**, hoặc **xóa cache cấp một có kiểm soát**.

### 10.1. Ưu tiên bulk UPDATE đầu transaction, trước khi tải entity liên quan

Nếu use case chỉ cần expire hàng loạt và trả số lượng:

~~~java
@Transactional
public int expireBatch(long tenantId, Instant now) {
    return executeExpireUpdate(tenantId, now);
}
~~~

Không tải Order vào EntityManager trước đó thì rủi ro một số Order managed đã cũ sẽ giảm đáng kể.

Một lời khuyên từ góc thiết kế: với bulk operations, nên dùng **transaction và persistence context ngắn, chuyên biệt** nếu có thể, sau đó giao dịch khác sẽ đọc dữ liệu mới.

### 10.2. `em.refresh(entity)`

Nếu cần tiếp tục dùng một entity đã managed:

~~~java
em.refresh(order);
~~~

Nó yêu cầu provider nạp lại state entity từ database.

Nhưng cần cân nhắc:

- `refresh` có thể ghi đè thay đổi pending trên entity.
- Nếu entity bị bulk DELETE, refresh có thể gặp lỗi do row không còn.
- Nếu một số field do transaction khác cập nhật, state mới phụ thuộc isolation/timing.
- Không refresh hàng chục nghìn entity chỉ để bù cho một thiết kế bulk không phù hợp.

### 10.3. `em.clear()`

~~~java
em.clear();
~~~

Làm mọi managed entity trong context thành detached, khiến các lần `find` sau có thể tải lại từ DB.

**Cảnh báo:** `clear()` có thể loại bỏ những thay đổi chưa flush của bất kỳ managed entity nào, không chỉ Order bị bulk UPDATE. Không gọi clear bừa bãi trong một transaction có nhiều công việc.

### 10.4. `em.flush()` trước và `em.clear()` sau

Một cách tổ chức trong một số use case:

~~~java
em.flush(); // Đồng bộ thay đổi pending nếu cần giữ.

int affected = em.createQuery(
        "UPDATE PurchaseOrder o " +
        "SET o.status = :expired " +
        "WHERE o.tenantId = :tenantId " +
        "AND o.status = :pending " +
        "AND o.expiresAt < :now"
    )
    .setParameter("expired", OrderStatus.EXPIRED)
    .setParameter("tenantId", tenantId)
    .setParameter("pending", OrderStatus.PENDING)
    .setParameter("now", now)
    .executeUpdate();

em.clear(); // Chỉ làm khi phù hợp toàn bộ use case.
~~~

Đoạn này là **một pattern có điều kiện**, không phải công thức bắt buộc. Nó giảm khả năng context stale và giúp không đánh mất pending changes đã flush, nhưng có thể làm những object mà service khác đang dựa vào trở thành detached.

### 10.5. `em.detach(entity)` cho một object

Nếu chỉ một entity cụ thể trở nên stale:

~~~java
em.detach(order);
~~~

Có thể detach riêng object ấy, sau đó nạp lại nếu cần. Nhưng với hàng nghìn entities bị bulk UPDATE, không nên lặp qua context để detach thủ công từng cái. Một transaction chuyên biệt thường dễ kiểm soát hơn.

### 10.6. Không nhầm clear với rollback

`clear()` không hoàn tác SQL bulk UPDATE đã chạy trong transaction. Nó chỉ ảnh hưởng các object mà EntityManager đang quản lý. Rollback mới hủy thay đổi transaction ở database.

## 11. Flush trước bulk UPDATE: Tránh thay đổi pending bị chồng chéo

Giả sử:

~~~java
PurchaseOrder order =
    em.find(PurchaseOrder.class, 101L);

order.changeTotalAmount(new BigDecimal("700000.00"));

// Thay đổi managed có thể chưa được flush.
~~~

Sau đó chạy bulk UPDATE trên cùng bảng:

~~~java
int changed = em.createQuery(
        "UPDATE PurchaseOrder o " +
        "SET o.status = :expired " +
        "WHERE o.status = :pending"
    )
    .setParameter("expired", OrderStatus.EXPIRED)
    .setParameter("pending", OrderStatus.PENDING)
    .executeUpdate();
~~~

Nếu có pending changes có thể tác động đến câu bulk UPDATE, thứ tự flush và SQL thực thi là điều quan trọng.

### 11.1. Flush mode AUTO

Trong transaction phù hợp, `FlushModeType.AUTO` yêu cầu provider bảo đảm các pending changes có khả năng ảnh hưởng kết quả query được phản ánh theo ngữ nghĩa JPA, bằng flush hoặc cơ chế khác.

Tuy nhiên, ứng dụng không nên dựa vào những giả định SQL ordering không kiểm chứng khi kết hợp managed state và bulk DML phức tạp.

### 11.2. Flush mode COMMIT

Với `FlushModeType.COMMIT`, ảnh hưởng của các pending changes chưa flush lên query trước commit không được đặc tả theo cách ứng dụng có thể mặc định.

Nếu bulk UPDATE cần nhìn thấy state mới từ managed entities, hãy có **ranh giới flush rõ ràng**.

### 11.3. Flush không commit

~~~java
em.flush();
~~~

gửi các thay đổi pending xuống DB trong transaction. Nó không có nghĩa transaction đã hoàn tất; rollback vẫn có thể hủy.

### 11.4. Đừng clear trước flush rồi mất dữ liệu

Sai nếu muốn giữ pending change:

~~~java
order.changeTotalAmount(new BigDecimal("700000.00"));
em.clear(); // Pending change có thể bị mất.
~~~

Nếu cần clear, trước đó phải quyết định nên flush, commit hay hủy các thay đổi pending như thế nào.

## 12. Bulk UPDATE không gọi lifecycle callbacks cho từng entity

Một entity có thể có:

~~~java
@PreUpdate
public void beforeUpdate() {
    this.updatedAt = Instant.now();
}
~~~

Với thao tác trên managed entity, provider có thể gọi lifecycle callback này theo quy tắc JPA khi phát sinh update.

Nhưng bulk JPQL:

~~~jpql
UPDATE PurchaseOrder o
SET o.status = :expired
WHERE o.status = :pending
~~~

**không áp dụng thay đổi qua lifecycle callback của từng PurchaseOrder**.

Hệ quả:

- `@PreUpdate`/`@PostUpdate` không tự chạy cho từng entity bị bulk update.
- Logic trong entity setter/domain method không được gọi.
- Những cơ chế auditing dựa trên entity lifecycle không tự cập nhật cho từng entity.
- Các entity validation hooks gắn với lifecycle không phải cách bảo vệ chắc chắn cho bulk DML.
- Entity listeners không tự phát domain event tương ứng cho từng row bị sửa.

### 12.1. Phải cập nhật timestamp tường minh nếu cần

Nếu `updatedAt` chỉ được cập nhật ở `@PreUpdate`, bulk UPDATE cần viết rõ:

~~~jpql
UPDATE PurchaseOrder o
SET o.status = :expired,
    o.updatedAt = :now
WHERE ...
~~~

Nếu không, `status` đã đổi nhưng `updated_at` có thể vẫn là giá trị cũ.

### 12.2. DB constraints và triggers vẫn có thể hoạt động

Bulk UPDATE vẫn là SQL thay đổi database. Vì vậy:

- `NOT NULL`, `CHECK`, `UNIQUE`, FK tiếp tục được DB kiểm tra.
- Trigger của DB có thể chạy theo quy tắc DB.
- Generated columns hoặc các logic DB-specific có thể tác động kết quả.

**Đừng nhầm “bỏ qua JPA entity callback” với “bỏ qua mọi validation/constraint ở database”.**

### 12.3. Nếu mỗi record cần nghiệp vụ phức tạp, bulk UPDATE có thể sai công cụ

Ví dụ hết hạn đơn nhưng mỗi đơn phải:

- Tính hoàn tiền khác nhau.
- Kiểm tra trạng thái inventory reservation riêng.
- Phát một event có payload khác nhau.
- Chạy audit lịch sử chi tiết.
- Cập nhật nhiều aggregate phụ thuộc khác nhau.

Một câu JPQL UPDATE không tự làm được các thao tác đó. Có thể cần xử lý theo batch managed entities, workflow event-driven hoặc SQL/outbox riêng được thiết kế chặt.

## 13. `@Version` và optimistic locking: Cảnh báo bắt buộc

Entity minh họa có:

~~~java
@Version
private long version;
~~~

Với cập nhật entity managed thông thường, JPA provider thực hiện optimistic locking theo version.

Ví dụ ý tưởng:

~~~sql
UPDATE purchase_order
SET status = ?, version = ?
WHERE id = ? AND version = ?
~~~

Nếu version trong DB đã đổi, update có thể thất bại và provider báo lỗi optimistic lock.

**Bulk JPQL UPDATE không tự thực hiện optimistic locking checks cho từng entity, và không tự tăng version field theo cơ chế cập nhật managed entity thông thường.**

Đây là khác biệt lớn, nhất là khi các transaction khác cũng sửa cùng các Order.

### 13.1. Race condition có thể xảy ra

~~~text
Transaction A                    Transaction B
------------------------------   ------------------------------
Load Order#101: PENDING, v=4
                                 Bulk UPDATE:
                                 PENDING -> EXPIRED
                                 (version vẫn có thể là 4)
Sửa Order#101 từ object cũ
Flush UPDATE theo version v=4
                                 B đã thay status nhưng không
                                 tăng version theo ORM thông thường
~~~

Tùy SQL/dirty checking/provider, A có thể ghi đè dữ liệu B đã bulk update hoặc ra quyết định trên state cũ. Không mặc định `@Version` bảo vệ toàn bộ đường bulk DML.

### 13.2. WHERE theo trạng thái là một hàng rào quan trọng

Ví dụ:

~~~jpql
UPDATE PurchaseOrder o
SET o.status = :expired
WHERE o.status = :pending
  AND o.expiresAt < :now
~~~

Nếu transaction khác đã đổi một Order sang PAID trước khi bulk UPDATE tác động, điều kiện `status = PENDING` giúp không chuyển đơn đó thành EXPIRED.

Tuy vậy, điều kiện trạng thái không thay thế optimistic version management trong mọi tình huống, vì transaction có thể cập nhật những field khác mà vẫn giữ status PENDING.

### 13.3. Muốn compare-and-set cho một record?

Có thể dùng điều kiện expected state:

~~~java
int changed = em.createQuery(
        "UPDATE PurchaseOrder o " +
        "SET o.status = :next " +
        "WHERE o.id = :id " +
        "AND o.tenantId = :tenantId " +
        "AND o.status = :expected"
    )
    .setParameter("next", OrderStatus.CANCELLED)
    .setParameter("id", orderId)
    .setParameter("tenantId", tenantId)
    .setParameter("expected", OrderStatus.PENDING)
    .executeUpdate();

if (changed != 1) {
    throw new IllegalStateException(
        "Order absent or state changed"
    );
}
~~~

Đây là kiểu **state-based conditional update**. Nó hữu ích khi business transition phụ thuộc trạng thái hiện tại. Nhưng nó không thay thế kiểm soát version nếu những thay đổi ngoài status cũng cần phát hiện xung đột.

### 13.4. Có nên tự cập nhật trường `@Version` trong bulk JPQL?

Đây là điểm phải thận trọng về portability. Trong một số provider, có thể viết hoặc dùng extension để tăng numeric version khi bulk UPDATE; ví dụ Hibernate hỗ trợ cơ chế versioned bulk update riêng.

Tuy nhiên, **JPA không tự quản lý version của từng entity trong bulk UPDATE**, và hợp đồng `@Version` dành cho vòng đời entity không nên bị thay thế bằng cách ứng dụng tự ý thao tác version mà chưa xem provider/spec và test concurrency.

Nếu hệ thống cần bảo đảm optimistic locking end-to-end, các lựa chọn có thể là:

- Cập nhật từng managed entity để JPA quản lý `@Version`.
- Dùng một trường **revision nghiệp vụ riêng** và conditional bulk UPDATE được thiết kế rõ.
- Dùng native SQL với điều kiện version và cập nhật version được triển khai/kiểm chứng như một chiến lược DB-level cụ thể.
- Dùng extension provider được tài liệu hóa và kiểm thử.

Không khẳng định một mẫu `SET o.version = o.version + 1` là portable cho mọi provider và mọi kiểu version. Nếu cần làm vậy, phải xem giới hạn của phiên bản JPA/provider thực tế.

### 13.5. Timestamp-based version càng không thể tự tăng một cách tùy tiện

Với `@Version Instant version` hoặc kiểu thời gian do provider hỗ trợ, không thể dùng phép `+ 1` như long. Không “phát minh” version value mà không hiểu precision, DB clock, optimistic lock contract và provider.

## 14. SET một hoặc nhiều field cùng lúc

Một JPQL UPDATE có thể gán nhiều field:

~~~jpql
UPDATE PurchaseOrder o
SET o.status = :expired,
    o.updatedAt = :now
WHERE ...
~~~

Cả hai giá trị được ghi trong cùng bulk operation/transaction. Không cần chạy hai UPDATE riêng cho hai field khi chúng thuộc cùng entity và cùng điều kiện.

### 14.1. Gán giá trị literal hay parameter?

Có thể viết giá trị literal trong JPQL cho một số kiểu, nhưng với enum/status và dữ liệu runtime, nên dùng parameter:

~~~java
.setParameter("expired", OrderStatus.EXPIRED)
~~~

Thay vì ghép:

~~~java
"SET o.status = '" + userProvidedStatus + "'"
~~~

Bind parameter vừa làm code rõ ràng, vừa tránh rủi ro khi input đi vào query text.

### 14.2. Gán NULL

Với một thuộc tính nullable và nghiệp vụ cho phép:

~~~jpql
UPDATE PurchaseOrder o
SET o.optionalReferenceCode = NULL
WHERE o.id = :id
~~~

Câu JPQL này minh họa trường hợp entity có thêm field `optionalReferenceCode`. DB vẫn kiểm tra `NOT NULL`; không thể gán NULL cho cột bắt buộc mà mong query tự thành công.

### 14.3. Update số bằng biểu thức

Một use case tăng bộ đếm:

~~~jpql
UPDATE PurchaseOrder o
SET o.retryCount = o.retryCount + 1
WHERE o.tenantId = :tenantId
  AND o.status = :pending
  AND o.retryCount < :maxRetries
~~~

Ví dụ Java:

~~~java
int changed = em.createQuery(
        "UPDATE PurchaseOrder o " +
        "SET o.retryCount = o.retryCount + 1 " +
        "WHERE o.tenantId = :tenantId " +
        "AND o.status = :pending " +
        "AND o.retryCount < :maxRetries"
    )
    .setParameter("tenantId", tenantId)
    .setParameter("pending", OrderStatus.PENDING)
    .setParameter("maxRetries", 3)
    .executeUpdate();
~~~

Tăng giá trị ngay tại DB giúp tránh mẫu read–modify–write bằng Java nếu cần cập nhật một tập record với cùng công thức. Tuy nhiên, phải hiểu tương tác concurrency, constraint và managed state cũ.

### 14.4. Tránh cập nhật bằng giá trị stale từ Java

Nếu đọc retryCount = 1 ở Java, sau đó đặt:

~~~jpql
SET o.retryCount = :newCount
~~~

với `newCount = 2`, một transaction khác có thể đã tăng giá trị lên 2 trước khi UPDATE của bạn chạy, dẫn đến lost update.

Với các phép toán cộng dồn đơn giản, biểu thức:

~~~jpql
SET o.retryCount = o.retryCount + 1
~~~

thường diễn đạt đúng hơn. Nhưng nó không có nghĩa mọi thao tác cạnh tranh đều tự an toàn; điều kiện WHERE, isolation và invariant nghiệp vụ vẫn rất quan trọng.

## 15. Dùng CASE WHEN trong biểu thức UPDATE

Có use case yêu cầu thay đổi giá trị theo trạng thái hoặc điều kiện của từng row.

Ví dụ giả định PurchaseOrder có thêm field `priorityScore`:

~~~jpql
UPDATE PurchaseOrder o
SET o.priorityScore =
    CASE
        WHEN o.totalAmount >= :highValue THEN :highPriority
        ELSE :normalPriority
    END
WHERE o.tenantId = :tenantId
~~~

Ý tưởng: mỗi row nhận một giá trị mới tính từ điều kiện. JPQL hỗ trợ CASE expressions theo quy tắc biểu thức; khả năng provider dịch và kiểu dữ liệu cần được kiểm tra trên stack cụ thể.

### 15.1. CASE không thay business workflow

CASE phù hợp với phép tính thuần dữ liệu, nhưng nếu mỗi nhánh cần gọi API, tính toán từ domain service hoặc tạo event riêng, JPQL UPDATE không thực thi các method Java tương ứng. Chọn quy trình batch theo entity hoặc một pipeline dữ liệu phù hợp.

### 15.2. Biểu thức trên field có thể gặp NULL

Nếu `priorityScore` hoặc counter nullable, phép cộng hoặc so sánh có thể cho kết quả NULL theo SQL. Cần thiết kế schema/COALESCE hoặc xác định semantics trước.

Đối với `retryCount` minh họa, schema đặt NOT NULL để biểu thức `+ 1` có ý nghĩa ổn định.

## 16. WHERE với nhiều điều kiện AND/OR

Một update theo nhiều điều kiện:

~~~jpql
UPDATE PurchaseOrder o
SET o.status = :expired
WHERE o.tenantId = :tenantId
  AND o.status = :pending
  AND o.expiresAt < :now
  AND o.retryCount >= :maxRetries
~~~

Nếu cần OR:

~~~jpql
UPDATE PurchaseOrder o
SET o.status = :expired
WHERE o.tenantId = :tenantId
  AND o.status = :pending
  AND (
      o.expiresAt < :now
      OR o.retryCount >= :maxRetries
  )
~~~

Dấu ngoặc rất quan trọng.

Sai về phạm vi:

~~~jpql
WHERE o.tenantId = :tenantId
  AND o.status = :pending
  AND o.expiresAt < :now
  OR o.retryCount >= :maxRetries
~~~

Vì độ ưu tiên AND/OR, một Order của **tenant khác** có retryCount cao có thể bị cập nhật nếu biểu thức cuối không được nhóm đúng.

**Một lỗi ngoặc trong bulk UPDATE nguy hiểm hơn lỗi SELECT**, vì nó có thể sửa dữ liệu ngoài phạm vi quyền truy cập.

## 17. Multi-tenant và bảo vệ phạm vi cập nhật

Trong hệ thống có nhiều tenant, bulk UPDATE phải có điều kiện tenant được lấy từ context đáng tin cậy:

~~~java
int changed = em.createQuery(
        "UPDATE PurchaseOrder o " +
        "SET o.status = :expired " +
        "WHERE o.tenantId = :tenantId " +
        "AND o.status = :pending " +
        "AND o.expiresAt < :now"
    )
    .setParameter("expired", OrderStatus.EXPIRED)
    .setParameter("tenantId", authenticatedTenantId)
    .setParameter("pending", OrderStatus.PENDING)
    .setParameter("now", now)
    .executeUpdate();
~~~

`authenticatedTenantId` phải được lấy từ security context hoặc quy trình job được cấp phép, không phải một ID tùy ý do caller không tin cậy gửi lên.

### 17.1. Query filters tự động có bảo vệ mọi bulk UPDATE không?

Một số ORM có extension filters hoặc soft-delete restrictions. **Không nên mặc định** mọi filter provider-specific hoặc logic repository SELECT đều được áp dụng tự động cho JPQL bulk UPDATE.

Với thao tác thay đổi dữ liệu, hãy xác định rõ ràng ràng buộc tenant/authorization trong WHERE hoặc dùng cơ chế database/security được kiểm chứng trên đường bulk DML.

### 17.2. Không cho phép caller truyền JPQL fragment tự do

Không dùng:

~~~java
String jpql =
    "UPDATE PurchaseOrder o SET o.status = :status " +
    "WHERE " + request.getRawCondition();
~~~

Đây là cửa ngõ cho injection ở mức truy vấn và lạm dụng phạm vi cập nhật.

Nếu cần filter động, dùng các mảnh cú pháp cố định do server kiểm soát, CriteriaUpdate, hoặc một query builder có whitelist. Giá trị từ client được bind qua parameters.

## 18. UPDATE với danh sách ID

Ví dụ cập nhật nhiều Order đã được chọn và xác thực:

~~~java
int changed = em.createQuery(
        "UPDATE PurchaseOrder o " +
        "SET o.status = :expired " +
        "WHERE o.tenantId = :tenantId " +
        "AND o.status = :pending " +
        "AND o.id IN :ids"
    )
    .setParameter("expired", OrderStatus.EXPIRED)
    .setParameter("tenantId", tenantId)
    .setParameter("pending", OrderStatus.PENDING)
    .setParameter("ids", orderIds)
    .executeUpdate();
~~~

JPQL hỗ trợ collection-valued parameter cho `IN` theo các quy tắc JPA. Nhưng input phải được kiểm soát.

### 18.1. List rỗng

Không nên mặc định truyền một list rỗng sẽ được mọi provider/dialect xử lý như “không cập nhật gì” bằng cùng một SQL. Cách rõ ràng:

~~~java
if (orderIds == null || orderIds.isEmpty()) {
    return 0;
}
~~~

Nếu null nghĩa “không áp dụng filter” nhưng empty nghĩa “không có ID nào”, hãy định nghĩa riêng theo API, tránh một sai lầm làm UPDATE tất cả Order.

### 18.2. List rất lớn

Một list hàng chục nghìn ID có thể gây:

- SQL quá dài.
- Quá nhiều bind parameters.
- Query plan kém.
- Transaction/lock kéo dài.
- Driver/database giới hạn số parameter.

Giải pháp tùy workload: chia batch có kiểm soát, dùng bảng staging/temp table hoặc chiến lược điều kiện theo keyset. Mỗi lựa chọn tác động tính nguyên tử và khả năng rollback, phải thiết kế trước.

### 18.3. Đếm affected theo IDs không đồng nghĩa mọi ID đã đổi

Nếu request có 50 IDs nhưng chỉ 46 Order đang PENDING và thuộc tenant, kết quả có thể là 46. Đây là hành vi mong muốn khi WHERE chặn các trạng thái không hợp lệ.

Nếu nghiệp vụ yêu cầu **tất cả 50 ID phải cùng hợp lệ hoặc không cập nhật gì**, một bulk UPDATE đơn giản rồi thấy affected = 46 chưa đủ. Cần transaction, logic kiểm tra tính đầy đủ và rollback khi thiếu, đồng thời cân nhắc concurrency giữa bước kiểm tra và UPDATE.

## 19. Hạn chế của JPQL UPDATE: Không viết JOIN như SELECT

JPQL SELECT có thể dùng:

~~~jpql
SELECT o
FROM PurchaseOrder o
JOIN o.customer c
WHERE c.tier = :tier
~~~

Nhưng JPQL bulk UPDATE không hỗ trợ cùng cấu trúc FROM/JOIN tùy ý như SELECT. Mẫu:

~~~jpql
UPDATE PurchaseOrder o
JOIN o.customer c
SET o.status = :status
WHERE c.tier = :tier
~~~

không phải cú pháp JPQL UPDATE portable.

Khi cần lọc theo liên kết, cân nhắc **subquery** trong WHERE hoặc một thiết kế cập nhật khác.

### 19.1. Ví dụ dùng EXISTS

Giả sử entity Customer có field `tier`:

~~~jpql
UPDATE PurchaseOrder o
SET o.status = :flagged
WHERE o.tenantId = :tenantId
  AND o.status = :pending
  AND EXISTS (
      SELECT c.id
      FROM Customer c
      WHERE c = o.customer
        AND c.tier = :tier
  )
~~~

Ở đây, query ngoài vẫn là UPDATE một entity type. Subquery trong WHERE xác định những Order có Customer đáp ứng điều kiện.

Ví dụ này giả định PurchaseOrder hỗ trợ trạng thái `FLAGGED` hoặc field đích tương ứng; có thể đổi thành một thuộc tính khác trong domain thật. Điều quan trọng là kỹ thuật **correlated subquery**, không phải enum ví dụ.

### 19.2. Cần kiểm chứng SQL provider sinh

JPQL update với subquery có thể được provider dịch sang SQL khác nhau theo database/dialect. Trên một số DB, các hạn chế khi UPDATE cùng bảng và tham chiếu subquery có thể ảnh hưởng khả năng thực thi.

Đừng suy ra vì JPQL đã parse thành công nên mọi database sẽ xử lý câu update phức tạp giống nhau.

### 19.3. Khi cần UPDATE ... FROM của DB

Một số database có cú pháp `UPDATE ... FROM` hoặc `MERGE` đặc thù. Nếu đó là cách phù hợp hơn với use case, có thể dùng native SQL, nhưng phải chấp nhận portability và persistence-context semantics của native bulk DML.

## 20. Quan hệ entity và thuộc tính cập nhật

JPQL UPDATE thường được dùng để sửa **basic scalar fields** như status, amount, flag, counter, timestamp. Một số association to-one có thể xuất hiện trong ngữ nghĩa update theo đặc tả, nhưng dùng chúng cần thận trọng về FK, type binding và mapping.

Ví dụ không nên tự ý chuyển khách hàng của hàng loạt Order chỉ vì SQL cho phép sửa foreign key. Có thể kéo theo:

- Quy tắc sở hữu đơn hàng.
- Quyền truy cập và phân vùng tenant.
- Audit/fulfillment.
- Các association đang managed.
- Ràng buộc FK/UNIQUE.
- Khả năng xung đột concurrent transaction.

Đối với collection to-many và join table, không thể chỉ gán một `List` cho một field trong SET như cách cập nhật scalar column. Cần thiết kế thao tác quan hệ riêng, thường qua entity lifecycle hoặc SQL/association mapping phù hợp.

## 21. Một bulk UPDATE có thể ảnh hưởng các subclass

Nếu `PurchaseOrder` là class gốc của một hierarchy sử dụng JPA inheritance, bulk:

~~~jpql
UPDATE PurchaseOrder o
SET o.status = :next
WHERE ...
~~~

có thể áp dụng cả entities thuộc subclass trong phạm vi polymorphism của query. Với mapping JOINED/TABLE_PER_CLASS, provider có thể phải xử lý nhiều bảng hoặc nhiều SQL statement.

Vì vậy:

- `executeUpdate()` trả số entity theo ngữ nghĩa JPA, không phải luôn số physical table rows.
- Không đo hiệu năng chỉ bằng suy đoán “một JPQL UPDATE bằng một SQL”.
- Khi có subclass-specific rules, cần xác định rõ entity scope, điều kiện TYPE hoặc một cách cập nhật riêng nếu được provider hỗ trợ.
- Kiểm thử trên hierarchy thật, đặc biệt khi có constraint ở các bảng con.

## 22. Bulk UPDATE và second-level cache

Ngoài first-level persistence context, một số ứng dụng bật **second-level cache** hoặc query-result cache của provider.

Sau bulk UPDATE, những cache này có thể chứa trạng thái cần được invalidated. Một số provider như Hibernate có cơ chế invalidate cache regions bị ảnh hưởng khi bulk operation, nhưng chi tiết thay đổi theo provider/version và loại query.

Không được giả định:

> “Bulk JPQL UPDATE chắc chắn làm sạch mọi cache trong application cluster.”

Khi use case cần độ mới cao, hãy:

1. Xác định entity có dùng second-level cache không.
2. Xác định provider xử lý bulk invalidation thế nào.
3. Kiểm tra multi-node cache consistency.
4. Test đọc lại qua EntityManager/context khác và node khác nếu cần.
5. Dùng cache eviction phù hợp hoặc tắt cache cho dữ liệu biến đổi thường xuyên.

JPA có API cache:

~~~java
Cache cache = emf.getCache();

cache.evict(PurchaseOrder.class);
~~~

Lệnh này là ví dụ loại bỏ các entries của một entity class khỏi second-level cache, không phải cách làm mới first-level persistence context. Không gọi evict toàn bộ cache tùy tiện sau mọi UPDATE mà không đánh giá phạm vi và hiệu năng.

### 22.1. Thời điểm eviction và commit

Nếu evict cache trước khi transaction commit, một reader khác có thể nạp lại state cũ trước commit rồi cache trạng thái chưa mong muốn. Việc phối hợp cache invalidation với commit và khả năng rollback là vấn đề riêng của provider/transaction design; cần kiểm chứng, không đơn giản xem eviction là tương đương commit.

## 23. Bulk UPDATE và audit, domain events, outbox

Giả sử khi một Order hết hạn, hệ thống muốn ghi một event:

~~~text
OrderExpired {
    orderId,
    tenantId,
    expiredAt
}
~~~

Một câu JPQL UPDATE chỉ trả số affected; nó không tự phát một event riêng cho từng Order.

### 23.1. Nếu chỉ cần metric số lượng

~~~java
int affected = expirePendingOrders(...);
metrics.recordExpiredCount(affected);
~~~

có thể phù hợp. Metric tổng số không yêu cầu biết từng ID.

### 23.2. Nếu cần outbox từng Order

Cần một thiết kế khác, ví dụ:

1. Xác định các Order eligible ở transaction phù hợp.
2. Tạo outbox events cho đúng các Order thực sự được chuyển trạng thái.
3. Đảm bảo DB update và outbox insert nằm trong cùng transaction.
4. Có quy tắc xử lý race condition nếu Order đổi trạng thái giữa SELECT và UPDATE.
5. Dùng unique key/idempotency để ngăn phát event trùng.

Có thể cần native SQL với `RETURNING`/CTE trên DB hỗ trợ, hoặc xử lý từng entity/batch managed với optimistic locking. Không suy ra `affected = 100` đủ để xây 100 event có ID chính xác.

### 23.3. `@PreUpdate` không thay thế outbox khi dùng bulk

Nếu hệ thống trước đây tạo audit trong `@PreUpdate`, khi chuyển sang JPQL bulk UPDATE, audit đó có thể biến mất. Cần thay đổi kiến trúc audit tương ứng thay vì coi bulk update chỉ là tối ưu hiệu năng “không ảnh hưởng nghiệp vụ”.

## 24. So sánh JPQL bulk UPDATE với CriteriaUpdate

JPA có Criteria API tương ứng cho bulk update:

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaUpdate<PurchaseOrder> update =
    cb.createCriteriaUpdate(PurchaseOrder.class);

Root<PurchaseOrder> root =
    update.from(PurchaseOrder.class);

update.set("status", OrderStatus.EXPIRED);
update.set("updatedAt", now);

update.where(
    cb.equal(root.get("tenantId"), tenantId),
    cb.equal(root.get("status"), OrderStatus.PENDING),
    cb.lessThan(root.get("expiresAt"), now)
);

int changed = em.createQuery(update).executeUpdate();
~~~

**Lưu ý:** tên field trong Criteria `"expiresAt"` là thuộc tính Java, không phải tên cột SQL.

### 24.1. Khi nào dùng CriteriaUpdate?

- Các điều kiện thay đổi nhiều theo runtime.
- Có filter tùy chọn cần ghép AND/OR.
- Muốn dùng một số tính năng type-safe của static metamodel.
- Một bộ logic bulk update có nhiều biến thể được quản lý bằng code builder.

### 24.2. CriteriaUpdate cũng là bulk update

CriteriaUpdate **không** biến thao tác trở thành cập nhật từng managed entity. Nó chia sẻ những hạn chế quan trọng:

- Không tự đồng bộ persistence context.
- Không tự gọi `@PreUpdate` từng entity.
- Không tự cập nhật `@Version` như dirty checking thông thường.
- Cần transaction và chú ý concurrency.

Đừng đổi từ JPQL UPDATE sang CriteriaUpdate chỉ để hy vọng callback/locking hoạt động như entity setter.

## 25. So sánh bulk JPQL UPDATE với native SQL UPDATE

JPQL:

~~~java
em.createQuery(
    "UPDATE PurchaseOrder o " +
    "SET o.status = :expired " +
    "WHERE o.status = :pending"
);
~~~

Native SQL:

~~~java
em.createNativeQuery(
    "UPDATE purchase_order " +
    "SET status = ? " +
    "WHERE status = ?"
);
~~~

| Điểm so sánh | JPQL bulk UPDATE | Native SQL UPDATE |
|---|---|---|
| Mô hình | Entity/property Java | Bảng/cột SQL |
| SQL do provider sinh | Có | Ứng dụng cung cấp trực tiếp |
| Hỗ trợ cú pháp DB-specific | Hạn chế | Rộng hơn |
| Portability qua DB | Thường tốt hơn | Tùy SQL |
| Result từ DML | `executeUpdate()` | `executeUpdate()` |
| Lifecycle callback từng entity | Không | Không |
| Managed persistence context tự sync | Không | Không |
| Optimistic version tự quản lý | Không | Không |
| Mapping khi schema đổi | Theo entity mapping | Phải sửa query theo schema |

Chọn native SQL nếu cần cú pháp SQL đặc thù hoặc tối ưu đã được kiểm chứng. Chọn JPQL UPDATE nếu thao tác có thể mô tả gọn theo entity và muốn giảm coupling với tên bảng/cột.

## 26. Bulk UPDATE so với JDBC batch UPDATE trên entity

Hai khái niệm thường bị nhầm:

**Bulk JPQL UPDATE:**

~~~jpql
UPDATE PurchaseOrder o
SET o.status = :expired
WHERE o.status = :pending
~~~

Provider thực hiện một thao tác logical update áp dụng cho toàn tập entity khớp.

**JDBC batching từ nhiều entity managed:**

~~~java
for (PurchaseOrder order : orders) {
    order.expire(now);
}
~~~

Provider có thể gom nhiều UPDATE statements vào các batch JDBC khi flush, tùy cấu hình và mapping.

### 26.1. Khác biệt về semantics

JDBC batching không xóa bỏ entity lifecycle/dirty checking; nó chỉ tối ưu truyền nhiều statement. Bulk JPQL bỏ qua tải/sửa từng entity và không áp dụng lifecycle callback cho từng row.

Nếu audit/domain methods là bắt buộc, có thể chọn **xử lý entity theo chunk + JDBC batch** thay vì bulk UPDATE.

### 26.2. Bulk UPDATE không đồng nghĩa không giữ lock

DB vẫn phải khóa những row cập nhật theo isolation/locking semantics. Một UPDATE tác động hàng trăm nghìn row có thể:

- Giữ nhiều lock.
- Cạnh tranh với transaction khác.
- Gây deadlock hoặc lock wait.
- Làm transaction kéo dài.
- Tăng redo/WAL và áp lực replication.

Một statement lớn có thể ít round trip hơn nhưng chưa chắc phù hợp với SLA và mức độ contention của hệ thống.

## 27. Chia nhỏ thao tác bulk UPDATE khi tập dữ liệu lớn

Giả sử cần expire 5 triệu Order. Một câu UPDATE khổng lồ có thể tạo transaction dài và lock contention.

Có thể phân chia công việc:

- Theo tenant.
- Theo khoảng thời gian.
- Theo ID ranges.
- Theo partition/shard.
- Theo tập ID giới hạn được chọn có thứ tự.
- Theo job checkpoint.

Ví dụ xử lý mỗi tenant trong transaction riêng:

~~~java
for (Long tenantId : tenantIds) {
    expirationService.expireTenantInOwnTransaction(
        tenantId, now
    );
}
~~~

Tên method chỉ minh họa; trong Spring, transaction mới cho từng tenant cần được tạo qua cơ chế transaction manager/proxy hợp lệ, không chỉ gọi self-invocation với `@Transactional`.

### 27.1. Đánh đổi tính nguyên tử

Nếu chạy 100 transaction nhỏ, có thể 99 transaction commit và một transaction thất bại. Đó là **partial completion** ở mức toàn job, dù mỗi transaction riêng vẫn atomic.

Cần có cơ chế retry/idempotency/checkpoint phù hợp. Đừng chia batch tùy tiện nếu nghiệp vụ đòi một giao dịch atomic trên toàn tập.

### 27.2. Lựa chọn điều kiện an toàn cho retry

Job:

~~~jpql
WHERE o.status = :pending
  AND o.expiresAt < :now
~~~

có tính idempotent tương đối: các Order đã chuyển sang EXPIRED sẽ không khớp lần sau nữa. Điều kiện trạng thái giúp retry không cập nhật lại toàn bộ row.

Nhưng nếu update thêm `retryCount = retryCount + 1`, retry có thể tăng lần nữa nếu điều kiện vẫn khớp. Phải xác định logic idempotency theo từng loại biến đổi, không chỉ dựa vào việc có WHERE.

### 27.3. Không chọn batch IDs rồi cập nhật không điều kiện

Nếu job SELECT một page ID và sau đó UPDATE theo IDs mà bỏ `status=PENDING`/`expiresAt<now`, một Order có thể đã được PAID trong khoảng giữa hai thao tác nhưng vẫn bị expire.

Luôn giữ các điều kiện nghiệp vụ cần bảo vệ **trong chính câu UPDATE** khi concurrency có thể thay đổi trạng thái.

## 28. Transaction isolation và concurrency

Hai transaction có thể cùng xử lý một Order:

~~~text
Transaction A                        Transaction B
----------------------------------   ----------------------------------
Đọc Order PENDING
                                     Thanh toán Order
                                     và chuyển sang PAID
Chạy bulk expire PENDING -> EXPIRED
~~~

Kết quả tùy thứ tự commit, lock, isolation và các điều kiện WHERE.

Một điều kiện:

~~~jpql
WHERE o.status = :pending
~~~

giúp bulk UPDATE không ghi EXPIRED lên row đã PAID **nếu** DB nhìn thấy trạng thái PAID tại thời điểm thao tác phù hợp với isolation. Nhưng không thể chỉ nhìn logic Java rồi bảo đảm mọi interleaving đều an toàn.

### 28.1. Với transition quan trọng, cần business concurrency contract

Ví dụ Payment workflow phải bảo đảm:

- Không thanh toán Order đã hết hạn.
- Không expire Order vừa xác nhận thanh toán.
- Không ghi đè một trạng thái hợp lệ bằng stale data.
- Nếu có thanh toán đang xử lý, xác định thứ tự ưu tiên và cơ chế giải quyết.

Có thể cần một transaction update trạng thái có điều kiện, optimistic version check hoặc locking thích hợp. Không coi bulk UPDATE tự động xử lý xung đột vì database sẽ “tự biết nghiệp vụ”.

### 28.2. Retry có chọn lọc

Nếu gặp deadlock/lock timeout, có thể retry **toàn transaction hoặc một đơn vị nghiệp vụ idempotent**, theo chính sách giới hạn. Không retry vô hạn hoặc giả định mọi lỗi PersistenceException đều là transient.

## 29. Dùng query timeout khi bulk UPDATE

Một bulk UPDATE quá rộng có thể kéo dài, đặc biệt khi chờ lock.

Có thể yêu cầu timeout:

~~~java
Query query = em.createQuery(
    "UPDATE PurchaseOrder o " +
    "SET o.status = :expired " +
    "WHERE o.tenantId = :tenantId " +
    "AND o.status = :pending"
);

query.setHint(
    "jakarta.persistence.query.timeout",
    10000
);
~~~

`10000` là yêu cầu 10.000 ms theo hint chuẩn. Nhưng provider/driver/database có thể không thực thi chính xác theo thời gian đó.

Timeout là một hàng rào vận hành, **không thay thế WHERE đúng, index phù hợp, giới hạn batch hoặc transaction design**.

### 29.1. Timeout có thể khiến transaction rollback-only

Sau lỗi timeout/lock, transaction có thể không còn hợp lệ. Không bắt exception rồi tiếp tục dùng EntityManager/transaction như thể bulk UPDATE chưa xảy ra. Cần xem exception classification và rollback theo transaction manager.

## 30. SQL index và điều kiện lọc

Với job:

~~~jpql
WHERE o.tenantId = :tenantId
  AND o.status = :pending
  AND o.expiresAt < :now
~~~

DB có thể hưởng lợi từ index phù hợp:

~~~sql
CREATE INDEX idx_order_expiration
ON purchase_order (
    tenant_id,
    status,
    expires_at
);
~~~

Ý tưởng: tenant và status là điều kiện equality, expiresAt là range condition. Nhưng hiệu quả thực tế phụ thuộc:

- Kích thước bảng.
- Độ chọn lọc tenant/status.
- Tỷ lệ PENDING hết hạn.
- Chi phí UPDATE và cập nhật index.
- Phân mảnh/partition.
- Execution plan của DB.

**Không tạo index chỉ bằng cách đọc JPQL rồi tin chắc là tối ưu.** Hãy xem SQL do provider sinh và dùng EXPLAIN/plan/metrics trên workload thích hợp.

### 30.1. Index có thể làm UPDATE tốn chi phí hơn

Mỗi UPDATE thay đổi field đã được index có thể yêu cầu cập nhật entry index. Việc thêm quá nhiều index chỉ để SELECT nhanh có thể khiến bulk DML chậm. Cần cân bằng read/write workload.

### 30.2. Không giả định UPDATE chỉ sửa row thực sự có giá trị khác

Một câu:

~~~jpql
UPDATE PurchaseOrder o SET o.status = :expired
~~~

có thể ảnh hưởng rất nhiều row ngay cả nếu một số đã EXPIRED, tùy WHERE/DB/provider và cách đếm. Thêm điều kiện trạng thái giúp giảm phạm vi thao tác và tránh cập nhật timestamp/counter vô ích.

## 31. Tối ưu bằng cách tính cutoff ở Java hay SQL?

Có thể dùng:

~~~java
Instant now = clock.instant();
~~~

rồi bind:

~~~java
.setParameter("now", now)
~~~

Lợi ích:

- Kiểm soát “thời điểm đánh giá” thống nhất trong một job.
- Dễ viết test bằng Clock giả.
- Dễ log cutoff của một lần chạy.
- Không phụ thuộc cú pháp hàm ngày giờ riêng DB.

Một lựa chọn khác là hàm thời gian SQL như `CURRENT_TIMESTAMP`, nhưng phải hiểu semantics timezone, thời điểm lấy timestamp và khả năng provider/dialect.

Trong job lớn chia nhiều transaction, dùng một `now` cố định có thể giúp mọi chunk xét cùng cutoff; hoặc dùng thời điểm từng chunk nếu nghiệp vụ yêu cầu. Đây là quyết định sản phẩm, không phải chi tiết cú pháp JPQL.

## 32. Khi nào không nên dùng bulk UPDATE?

### 32.1. Entity có invariant phức tạp

Ví dụ:

~~~java
public void markPaid(
        PaymentReceipt receipt,
        InventoryService inventoryService) {
    // Check payment amount
    // Validate inventory
    // Update fields
    // Create domain event
}
~~~

Không thể thay trọn method này bằng một `SET status = PAID` nếu những bước khác là bắt buộc.

### 32.2. Cần callback, listener hoặc validation từng entity

Nếu kết quả đúng phụ thuộc `@PreUpdate`, Bean Validation hoặc auditing tự động theo entity lifecycle, bulk DML bỏ qua các bước đó.

### 32.3. Cần optimistic locking chuẩn cho từng row

Nếu mọi entity cần so khớp `@Version` trước khi cập nhật và báo xung đột riêng, thao tác managed entities có thể phù hợp hơn.

### 32.4. Cần danh sách ID chính xác đã thay đổi

`executeUpdate()` chỉ trả số lượng. Nếu cần event/audit per-row, phải thiết kế thêm cơ chế xác định và xác nhận ID dưới concurrency.

### 32.5. Tập dữ liệu nhỏ và code entity dễ hiểu

Nếu chỉ cập nhật một vài Order và đã tải entity trong transaction, bulk UPDATE có thể làm tăng độ phức tạp do state stale. Đừng tối ưu sớm khi chi phí thực tế không đáng kể.

## 33. Spring Data JPA: `@Modifying` và `@Query`

Spring Data JPA hỗ trợ bulk update qua repository method:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Modifying
    @Query("""
        UPDATE PurchaseOrder o
        SET o.status = :expired,
            o.updatedAt = :now
        WHERE o.tenantId = :tenantId
          AND o.status = :pending
          AND o.expiresAt < :now
        """)
    int expirePending(
        @Param("tenantId") Long tenantId,
        @Param("pending") OrderStatus pending,
        @Param("expired") OrderStatus expired,
        @Param("now") Instant now
    );
}
~~~

Trong đoạn này:

- `@Query` chứa **JPQL**, không phải native SQL.
- `@Modifying` báo Spring Data rằng đây là UPDATE/DELETE thay vì SELECT.
- Method trả `int` với số entity bị tác động theo execution result.
- Transaction phải được mở ở service hoặc method được cấu hình phù hợp.

### 33.1. Transaction ở service

~~~java
@Service
public class OrderExpirationService {

    private final PurchaseOrderRepository repository;

    public OrderExpirationService(
            PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public int expireTenant(Long tenantId, Instant now) {
        return repository.expirePending(
            tenantId,
            OrderStatus.PENDING,
            OrderStatus.EXPIRED,
            now
        );
    }
}
~~~

Đặt transaction ở service giúp một use case có thể phối hợp nhiều repository/operation nguyên tử.

### 33.2. `@Modifying` không có nghĩa auto-clear mặc định

Trong Spring Data JPA, `@Modifying` có các tùy chọn quan trọng:

~~~java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
~~~

Ý nghĩa khái quát:

- `flushAutomatically = true`: Spring Data yêu cầu flush trước khi thực thi modifying query.
- `clearAutomatically = true`: Spring Data yêu cầu clear persistence context sau khi thực thi query.

Các giá trị mặc định không nên bị hiểu là Spring luôn tự flush/clear sau mọi modifying query. Cần đọc contract của phiên bản Spring Data đang dùng.

### 33.3. Cẩn thận với clearAutomatically

Giả sử outer transaction đang sửa một entity khác nhưng chưa flush. Tự động clear sau bulk DML có thể detach entity đó và làm mất pending changes.

Dùng `flushAutomatically=true` và `clearAutomatically=true` có thể phù hợp trong một use case chuyên biệt, nhưng vẫn phải hiểu:

- Flush đồng bộ pending changes vào transaction.
- Clear detach **toàn bộ** managed entities.
- Bulk DML không retroactively gọi callbacks cho entities bị cập nhật.
- Clear không thay thế rollback hoặc bảo đảm đồng bộ second-level cache.

### 33.4. Không nhầm `@Modifying` với `@Transactional`

`@Modifying` xác định query là DML đối với Spring Data. Nó **không tự tạo transaction hợp lệ trong mọi tình huống**. Cần transaction owner qua `@Transactional` hoặc cấu hình phù hợp.

### 33.5. Không cần `@Modifying` khi gọi EntityManager trực tiếp

~~~java
em.createQuery(jpql)
  .executeUpdate();
~~~

là JPA API thuần; `@Modifying` chỉ liên quan đến Spring Data repository method được annotation.

## 34. JPA standard vs Hibernate-specific bulk operations

Một số Hibernate versions hỗ trợ extension liên quan bulk HQL, ví dụ cơ chế tăng version trong bulk update hoặc cú pháp HQL rộng hơn JPQL chuẩn.

Nếu dự án dùng:

~~~java
entityManager.createQuery("...")
~~~

với syntax HQL mở rộng, câu query có thể chạy trên Hibernate nhưng không còn portable khi đổi sang EclipseLink hoặc một provider khác.

Nguyên tắc:

1. Phân biệt **JPQL chuẩn** với **HQL/provider extension**.
2. Nếu chọn extension, khai báo dependency và version.
3. Kiểm thử SQL sinh ra trên DB thật.
4. Hiểu cách extension tương tác `@Version`, inheritance, cache và transaction.
5. Không mô tả một tính năng vendor-specific như là cam kết của JPA.

## 35. Tính idempotent của job bulk UPDATE

Một job thường chạy lặp lại hoặc được retry sau lỗi mạng. Có cần cập nhật row lần hai không?

Với:

~~~jpql
UPDATE PurchaseOrder o
SET o.status = :expired,
    o.updatedAt = :now
WHERE o.status = :pending
  AND o.expiresAt < :now
~~~

những row đã EXPIRED sẽ không còn khớp `status=PENDING` trong lần chạy sau. Đây là một cơ sở tốt cho retry.

Nhưng nếu query:

~~~jpql
UPDATE PurchaseOrder o
SET o.retryCount = o.retryCount + 1
WHERE o.status = :pending
~~~

thì chạy lần nữa sẽ lại tăng retryCount. Nếu retry sau timeout mà không biết transaction trước đã commit chưa, có nguy cơ tăng lặp.

### 35.1. Idempotency key và state transition

Với thao tác có side effect phải thực hiện đúng một lần theo nghiệp vụ, có thể cần:

- Ghi nhận job/run ID.
- Conditional update theo trạng thái trước.
- Unique constraint trên outbox/event.
- Định nghĩa rõ cách nhận biết transaction đã commit hay không.
- Retry có giới hạn và đối soát kết quả.

Không suy ra mọi JPQL UPDATE đều idempotent chỉ vì nó có WHERE.

## 36. Bulk UPDATE với soft delete

Nếu hệ thống không được xóa row lịch sử, có thể dùng update trạng thái/flag:

~~~jpql
UPDATE PurchaseOrder o
SET o.status = :cancelled,
    o.updatedAt = :now
WHERE o.tenantId = :tenantId
  AND o.status = :pending
~~~

Đây là **cập nhật trạng thái nghiệp vụ**, không phải JPA remove.

Nếu dùng field:

~~~java
private boolean deleted;
~~~

và bulk:

~~~jpql
UPDATE PurchaseOrder o
SET o.deleted = true
WHERE ...
~~~

thì cần hiểu:

- Query SELECT phải lọc bản ghi deleted đúng.
- Unique constraint có thể cần điều kiện chỉ tính active rows.
- JPA entity listeners không chạy cho mỗi row bulk update.
- Provider-specific soft-delete filters cần kiểm chứng trên bulk DML.
- Phải quản lý cache và audit tương thích.

Không coi soft delete bằng bulk update là tương đương `entityManager.remove()`.

## 37. Lỗi thường gặp và cách phân tích

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `TransactionRequiredException` | Gọi `executeUpdate` ngoài transaction | Đảm bảo transaction owner hợp lệ |
| Query không chạy và trả kết quả entity | Dùng `getResultList` cho UPDATE | Dùng `executeUpdate` |
| `affected = 0` | Không có row khớp ID/tenant/status/cutoff | Kiểm tra điều kiện nghiệp vụ |
| Hàng của tenant khác bị sửa | Quên tenant predicate hoặc nhóm OR sai | Bắt buộc tenant scope trong WHERE |
| Entity getter vẫn trả status cũ | Persistence context stale | Refresh/clear/reload phù hợp |
| `@PreUpdate` không được gọi | Bulk UPDATE bypass lifecycle từng entity | Viết audit/updatedAt tường minh hoặc sửa từng entity |
| `@Version` không tăng | Bulk DML không auto optimistic version handling | Chọn chiến lược locking phù hợp |
| Entity managed ghi đè bulk change | State/snapshot cũ còn trong context | Không trộn hai đường ghi mà không đồng bộ |
| Query cập nhật nhiều hơn dự kiến | WHERE thiếu hoặc OR sai | Chặn scope, test fixture đa tenant/trạng thái |
| Lỗi UPDATE JOIN | JPQL UPDATE không hỗ trợ syntax SELECT JOIN tùy ý | Dùng subquery/CriteriaUpdate/native khi cần |
| SQL constraint violation | DB CHECK/FK/UNIQUE từ chối state | Sửa business logic/migration, không bỏ constraint tùy tiện |
| Job timeout/deadlock | Update quá nhiều row, lock lâu | Chia batch, index, retry có giới hạn |
| Count affected khác số SQL rows log | Inheritance/provider mapping phức tạp | Hiểu affected entity count |
| Spring repository UPDATE không chạy | Thiếu `@Modifying` hoặc transaction | Thêm annotation/transaction phù hợp |
| Dữ liệu pending bị mất | `clearAutomatically`/`em.clear` khi chưa flush | Rà soát flush/clear boundary |
| Read-only transaction gây lỗi | DML trong transaction read-only | Dùng transaction cho phép ghi |
| Audit thiếu hàng | Chờ đợi callback per entity sau bulk | Thiết kế audit/outbox riêng |
| L2 cache cho dữ liệu cũ | Cache invalidation không đúng | Xem provider behavior và eviction |
| Job retry tăng counter hai lần | Operation không idempotent | Có state guard/idempotency |
| Query chậm dù chỉ một JPQL | Index/row count/lock/DB plan | EXPLAIN và đo workload |
| Test rollback nhưng nghĩ DB không update | Transaction test đã rollback | Kiểm chứng ở context mới sau commit |

## 38. Integration test cho bulk JPQL UPDATE

Kiểm thử nên tập trung vào **dữ liệu thực sau commit và quy tắc lifecycle**, không chỉ kết quả affected count.

### 38.1. Fixture

Giả sử có:

~~~text
Tenant 7:
  O1 PENDING, expiresAt=09:00
  O2 PENDING, expiresAt=11:00
  O3 PAID,    expiresAt=08:00
  O4 PENDING, expiresAt=09:15

Tenant 8:
  O5 PENDING, expiresAt=08:30
~~~

Test chạy lúc `10:00` cho tenant 7.

Kỳ vọng:

- O1 và O4 chuyển EXPIRED.
- O2 vẫn PENDING vì chưa hết hạn.
- O3 vẫn PAID.
- O5 vẫn PENDING vì tenant khác.
- `affected = 2`.
- Nếu bulk query gán `updatedAt`, O1 và O4 có updatedAt mong muốn.

### 38.2. Test thực thi và đọc ở EntityManager mới

Pseudocode:

~~~java
@Test
void expireOnlyEligibleOrders() {
    // Fixture được insert và commit trước đó.

    EntityManager work = emf.createEntityManager();
    EntityTransaction tx = work.getTransaction();

    try {
        tx.begin();

        int changed = expirePendingOrders(
            work, 7L, testClock.instant()
        );

        assertEquals(2, changed);

        tx.commit();
    } finally {
        if (tx.isActive()) {
            tx.rollback();
        }
        work.close();
    }

    EntityManager verify = emf.createEntityManager();
    try {
        PurchaseOrder o1 =
            verify.find(PurchaseOrder.class, order1Id);

        PurchaseOrder o2 =
            verify.find(PurchaseOrder.class, order2Id);

        assertEquals(OrderStatus.EXPIRED, o1.getStatus());
        assertEquals(OrderStatus.PENDING, o2.getStatus());

        // Assert O3, O4, O5 tương ứng.
    } finally {
        verify.close();
    }
}
~~~

Ví dụ giả định test có `emf`, fixture IDs, `testClock` và JUnit assertions. Mục đích là minh họa việc **đọc bằng context khác sau commit**; test thực tế cần setup/cleanup fixture chính xác.

### 38.3. Test persistence context stale

~~~java
tx.begin();

PurchaseOrder managed =
    em.find(PurchaseOrder.class, orderId);

OrderStatus before = managed.getStatus();

int changed = em.createQuery(
        "UPDATE PurchaseOrder o " +
        "SET o.status = :expired WHERE o.id = :id"
    )
    .setParameter("expired", OrderStatus.EXPIRED)
    .setParameter("id", orderId)
    .executeUpdate();

// Không giả định managed.getStatus() đã đổi.
em.refresh(managed);

// Sau refresh, quan sát state đã đồng bộ từ DB
// theo isolation/transaction hiện tại.
tx.commit();
~~~

Test này giúp nhận ra sự khác nhau giữa database state và managed object state.

### 38.4. Test rollback

~~~text
BEGIN
UPDATE ... (affected=2)
ROLLBACK

EntityManager mới:
  O1, O4 vẫn PENDING nếu transaction chưa được commit.
~~~

Không coi SQL UPDATE xuất hiện trong log là bằng chứng nó đã commit.

### 38.5. Test lifecycle callback không chạy

Nếu entity có `@PreUpdate` để tăng một counter audit, test bulk UPDATE cần xác minh callback không được thực thi trên từng entity như update managed entity.

Đây là một phần contract quan trọng của bulk DML, cần thể hiện trong tài liệu code và quyết định có sử dụng nó không.

### 38.6. Test concurrency với hai transaction

Tạo hai transaction độc lập:

- A đang sửa Order managed.
- B chạy bulk UPDATE đổi status.
- Xác nhận logic version/state guard/race condition theo thiết kế đã chọn.

Không dùng cùng EntityManager ở hai thread. EntityManager không thread-safe; integration test concurrency phải dùng context và connection riêng với đồng bộ thời điểm có chủ đích.

### 38.7. Test trên DB thật

H2 có thể khác PostgreSQL/MySQL/Oracle ở locking, isolation, SQL UPDATE translation, inheritance và constraint. Nếu query quan trọng với concurrency hay hiệu năng, test trên DB/dialect mục tiêu.

## 39. Bài tập thực hành

### Bài 1: Chọn UPDATE hay SELECT+loop

Cần chuyển 100.000 Order PENDING quá hạn thành EXPIRED và chỉ cần thống kê tổng số.

**Câu hỏi:** Có nên dùng JPQL bulk UPDATE không?

**Đáp án:** Có thể rất phù hợp nếu mọi row cùng chịu một biến đổi đơn giản và không cần callbacks/domain events riêng. Phải thêm tenant/status/cutoff, transaction, xem version/cache/audit.

### Bài 2: Đúng cú pháp JPQL

~~~jpql
UPDATE purchase_order
SET status = :status
WHERE expires_at < :now
~~~

**Câu hỏi:** Vì sao không phải JPQL chuẩn?

**Đáp án:** `purchase_order` và `expires_at` là tên bảng/cột SQL. JPQL dùng entity `PurchaseOrder` và thuộc tính Java `expiresAt`.

### Bài 3: Kết quả thực thi

~~~java
int updated = query.executeUpdate();
~~~

**Câu hỏi:** Nếu updated = 50, có chắc 50 Order đã commit không?

**Đáp án:** Không. Đây là số entity bị tác động theo thực thi bulk query; transaction có thể rollback sau đó.

### Bài 4: Không có transaction

Service gọi `executeUpdate()` khi chưa có transaction.

**Câu hỏi:** Điều gì xảy ra?

**Đáp án:** JPA có thể ném `TransactionRequiredException`. Cần transaction phù hợp; không được bắt lỗi rồi trả 0 như thể không có dữ liệu.

### Bài 5: Entity managed stale

Một Order đã được `em.find` có status PENDING. Bulk query cập nhật DB thành EXPIRED.

**Câu hỏi:** `order.getStatus()` có chắc EXPIRED không?

**Đáp án:** Không. Bulk DML không tự đồng bộ managed object. Cần refresh hoặc context mới, hoặc tránh tải entity trước bulk.

### Bài 6: Lifecycle callbacks

Entity có `@PreUpdate` cập nhật updatedAt. Bulk UPDATE chỉ viết `SET status = :expired`.

**Câu hỏi:** updatedAt có chắc được cập nhật không?

**Đáp án:** Không. Callback từng entity không tự chạy. Muốn updatedAt đổi, gán field đó trong SET hoặc dùng một cơ chế audit khác được bảo đảm.

### Bài 7: Version

Entity có `@Version`. Bulk query sửa status.

**Câu hỏi:** JPA có tự kiểm tra và tăng version từng row như dirty checking không?

**Đáp án:** Không. Cần chiến lược concurrency riêng hoặc sửa managed entities khi cần hợp đồng optimistic locking chuẩn.

### Bài 8: Tenant scope

~~~jpql
WHERE o.tenantId = :tenantId
  AND o.status = :pending
  OR o.retryCount >= :maxRetries
~~~

**Câu hỏi:** Có an toàn để giới hạn theo tenant không?

**Đáp án:** Không. Nhánh OR có thể khớp Order tenant khác. Dùng `AND (status = ... OR retryCount >= ...)` để tenant scope áp dụng cả hai nhánh.

### Bài 9: Không có WHERE

~~~jpql
UPDATE PurchaseOrder o
SET o.status = :expired
~~~

**Câu hỏi:** Có cập nhật một Order được chỉ định không?

**Đáp án:** Không. Không có WHERE nên có thể cập nhật toàn bộ tập PurchaseOrder; chỉ dùng nếu nghiệp vụ chủ đích thay tất cả.

### Bài 10: Danh sách ID rỗng

Filter `ids = []`.

**Câu hỏi:** Có nên bỏ `WHERE o.id IN :ids` rồi cập nhật mọi Order không?

**Đáp án:** Không. Nếu list rỗng nghĩa không có ID được chọn, trả 0 hoặc validation error; không biến thao tác rỗng thành mass update.

### Bài 11: Increment counter

~~~jpql
SET o.retryCount = :newValue
~~~

với giá trị được đọc trước đó ở Java.

**Câu hỏi:** Có rủi ro nào?

**Đáp án:** Có thể lost update nếu transaction khác thay counter. Với cộng đơn giản, biểu thức `o.retryCount = o.retryCount + 1` có thể phù hợp hơn, kết hợp WHERE và concurrency policy.

### Bài 12: UPDATE JOIN

~~~jpql
UPDATE PurchaseOrder o
JOIN o.customer c
SET o.status = :next
WHERE c.tier = :tier
~~~

**Câu hỏi:** Có phải JPQL UPDATE portable không?

**Đáp án:** Không. Bulk UPDATE JPQL không dùng cú pháp JOIN như SELECT. Xem correlated subquery, CriteriaUpdate hoặc native SQL nếu thật sự cần.

### Bài 13: Spring Data

Repository khai báo:

~~~java
@Query("UPDATE PurchaseOrder o SET o.status = :next")
int updateStatus(...);
~~~

**Câu hỏi:** Thiếu gì?

**Đáp án:** Với Spring Data JPA modifying repository query, cần `@Modifying` và transaction phù hợp; đồng thời WHERE scope bắt buộc để tránh cập nhật mọi Order.

### Bài 14: clearAutomatically

Một service đang thay đổi Customer managed, chưa flush, sau đó gọi repository `@Modifying(clearAutomatically=true)`.

**Câu hỏi:** Rủi ro?

**Đáp án:** Clear detach toàn bộ context, có thể làm mất thay đổi chưa flush. Cần hiểu/kiểm soát flush boundary, không bật auto-clear chỉ vì muốn “chắc chắn”.

### Bài 15: Audit

Nghiệp vụ yêu cầu một outbox event chính xác cho mỗi Order vừa hết hạn.

**Câu hỏi:** Chỉ `executeUpdate()` trả số lượng có đủ không?

**Đáp án:** Không. Cần xác định ID đã chuyển thành công và ghi event atomic, có chiến lược concurrency/idempotency.

### Bài 16: Chia batch

Job cần expire 5 triệu Order.

**Câu hỏi:** Có thể chia theo tenant hoặc ID range không?

**Đáp án:** Có, nhưng mỗi batch/transaction có thể commit riêng, dẫn đến partial completion toàn job. Cần checkpoint, retry/idempotency và đánh giá yêu cầu nguyên tử.

### Bài 17: CriteriaUpdate

**Câu hỏi:** Chuyển từ JPQL UPDATE sang CriteriaUpdate có làm `@PreUpdate` tự chạy không?

**Đáp án:** Không. CriteriaUpdate vẫn là bulk DML, mang cùng giới hạn persistence context/lifecycle/version.

### Bài 18: Native SQL

**Câu hỏi:** Khi nào chọn native UPDATE thay JPQL UPDATE?

**Đáp án:** Khi cần SQL/dialect feature, multi-table UPDATE hoặc tối ưu DB-specific mà JPQL không diễn đạt được; phải chấp nhận dependency và kiểm thử DB mục tiêu.

### Bài 19: Query timeout

**Câu hỏi:** Đặt query timeout 1 giây có bảo đảm mass update dừng chính xác ở 1.000 ms không?

**Đáp án:** Không. Hint phụ thuộc provider/JDBC/DB. Cần quản lý transaction/lock, giới hạn batch và kiểm thử hành vi thực tế.

### Bài 20: Xác minh trạng thái cuối

Test đọc Order ngay trong EntityManager đã load trước bulk update và thấy status cũ.

**Câu hỏi:** Có thể kết luận UPDATE thất bại không?

**Đáp án:** Không. Cần kiểm tra transaction, affected count và đọc lại bằng context mới sau commit, hoặc refresh phù hợp.

## 40. Checklist triển khai JPQL UPDATE hàng loạt

Trước khi dùng trong hệ thống thật, hãy xác định:

1. **Có đúng là cùng một phép biến đổi cho nhiều entity không?**
2. **Có cần domain method/callback/validation/audit từng entity không?**
3. **JPQL dùng entity/property Java đúng mapping không?**
4. **WHERE có giới hạn tenant, trạng thái, thời gian, quyền truy cập không?**
5. **Các nhóm AND/OR có dấu ngoặc đúng không?**
6. **Giá trị động được bind qua `setParameter` chưa?**
7. **Có kiểm soát list rỗng, list quá lớn và null không?**
8. **DML chạy trong transaction owner phù hợp chưa?**
9. **Mã nguồn có phân biệt executeUpdate với commit không?**
10. **Mọi thay đổi pending cần thiết đã được flush đúng thời điểm chưa?**
11. **Sau bulk, các managed entities có thể stale không?**
12. **Có cần `refresh`, `clear` hoặc tách persistence context không?**
13. **Có field updatedAt/audit cần ghi tường minh không?**
14. **`@Version`/optimistic locking có bị bypass không?**
15. **Có DB constraint/trigger nào chịu tác động không?**
16. **Có second-level/query cache cần chiến lược invalidation không?**
17. **Có event/outbox per row cần phát không?**
18. **Nếu dùng Spring Data, đã khai báo `@Modifying`/transaction đúng chưa?**
19. **Khối lượng update có tạo lock contention/transaction quá dài không?**
20. **Đã thiết kế retry/idempotency và partial completion chưa?**
21. **Index trên điều kiện WHERE có hợp lý không?**
22. **Có integration tests với tenant/status/cutoff biên không?**
23. **Có test rollback và đọc ở context mới không?**
24. **Có test concurrency khi Order đang thanh toán không?**
25. **Có xác nhận SQL và execution plan trên DB/provider mục tiêu không?**

## 41. Tổng kết

~~~text
                  NHIỀU ENTITY CẦN ĐỔI
                          |
                          v
          Có cần lifecycle/domain logic từng entity?
                   /                 \
                 Có                 Không
                  |                   |
                  v                   v
        Managed entity update     JPQL bulk UPDATE
        + dirty checking               |
        + @Version                     |
        + callbacks                    |
                                        v
                           UPDATE EntityName alias
                           SET field = :value
                           WHERE scope/condition
                                        |
                                        v
                            setParameter(...) + executeUpdate()
                                        |
                             +----------+----------+
                             |                     |
                             v                     v
                        Transaction           Số entity affected
                        commit/rollback       (không phải commit)
                             |
                             v
                    DB state có thể đổi,
                    managed state có thể stale
                             |
                             v
                 Chọn refresh/clear/context mới
                 và concurrency/audit phù hợp
~~~

Các nguyên tắc trọng tâm:

1. **JPQL bulk UPDATE dùng `UPDATE EntityName ... SET ... WHERE ...`**, làm việc với tên entity/thuộc tính Java, không phải bảng/cột SQL.
2. **Dùng `EntityManager.createQuery` và `Query.executeUpdate()`**, không dùng `getResultList()` cho câu UPDATE.
3. **`executeUpdate()` trả số entity bị tác động**, nhưng không có nghĩa transaction đã commit.
4. **Bulk UPDATE không cần tải từng entity**, giúp phù hợp với những thay đổi tập hợp đơn giản và có thể giảm round trip/memory.
5. **Bulk UPDATE bỏ qua lifecycle callback/dirty checking từng entity**, không tự gọi domain methods hoặc `@PreUpdate`.
6. **Persistence context có thể stale** nếu chứa entities bị bulk UPDATE; cần tách scope hoặc refresh/clear phù hợp.
7. **Flush trước bulk khi cần đồng bộ pending changes; clear sau bulk phải có chủ đích**, vì clear có thể làm mất thay đổi chưa flush và detach object khác.
8. **Bulk UPDATE không tự xử lý `@Version`/optimistic locking như managed update**, nên phải thiết kế concurrency riêng.
9. **WHERE và tenant scope là hàng rào an toàn quan trọng nhất**; thiếu điều kiện hoặc sai AND/OR có thể sửa nhiều dữ liệu ngoài ý định.
10. **JPQL UPDATE không hỗ trợ JOIN giống JPQL SELECT**; dùng subquery, CriteriaUpdate hoặc native SQL phù hợp.
11. **Spring Data JPA yêu cầu `@Modifying` cho repository update query**, cùng transaction hợp lệ; tùy chọn auto-clear/auto-flush cần được hiểu rõ.
12. **Cache, audit, outbox và DB triggers phải được xem xét riêng**, không giả định bulk query kích hoạt mọi cơ chế của entity lifecycle.
13. **Mass update có thể giữ lock và tạo transaction lớn**, nên cần đo SQL plan, thiết kế batch, retry và idempotency.
14. **Kiểm thử trên database/provider thực**, gồm transaction commit/rollback, stale state, tenant boundaries và concurrency.

JPQL UPDATE hàng loạt là công cụ hiệu quả khi thay đổi nhiều entity theo một quy tắc chung có thể diễn đạt ngay trong `SET` và `WHERE`. Sử dụng đúng nghĩa là **không chỉ viết một câu UPDATE ngắn**, mà còn nắm được những bước JPA không thực hiện thay mình: đồng bộ persistence context, lifecycle callbacks, optimistic locking, audit và bảo vệ phạm vi cập nhật.
