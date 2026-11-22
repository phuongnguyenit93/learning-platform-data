# Đánh giá ảnh hưởng tới callback, cascade và kiểm tra phiên bản trong truy vấn thay đổi JPA

## 1. Vấn đề: cập nhật hàng loạt không giống cập nhật entity được quản lý

Một ứng dụng JPA cần hủy 15.000 đơn hàng đang ở trạng thái nháp sau thời hạn giữ chỗ. Có hai cách viết rất khác nhau về mặt **ngữ nghĩa persistence**, dù cuối cùng đều có thể tạo SQL `UPDATE`.

**Cách A — tải entity rồi thay đổi trạng thái:**

```java
List<PurchaseOrder> orders = em.createQuery(
    """
    SELECT o FROM PurchaseOrder o
    WHERE o.status = :draft AND o.expiresAt < :now
    """,
    PurchaseOrder.class
)
.setParameter("draft", OrderStatus.DRAFT)
.setParameter("now", now)
.getResultList();

for (PurchaseOrder order : orders) {
    order.expire();
}
```

**Cách B — cập nhật hàng loạt bằng JPQL:**

```java
int changed = em.createQuery(
    """
    UPDATE PurchaseOrder o
    SET o.status = :expired
    WHERE o.status = :draft
      AND o.expiresAt < :now
    """
)
.setParameter("expired", OrderStatus.EXPIRED)
.setParameter("draft", OrderStatus.DRAFT)
.setParameter("now", now)
.executeUpdate();
```

Hai cách có thể tạo kết quả nhìn thấy ở database giống nhau về cột `status`. Nhưng **chúng không tương đương về lifecycle**:

- Cách A làm việc với các **managed entities** và các business methods.
- Cách B là **bulk update query**: gửi yêu cầu thay đổi trực tiếp cho database theo tập điều kiện.
- Các callback `@PreUpdate`/`@PostUpdate` của những entity bị thay đổi bởi bulk query **không được gọi theo cơ chế cập nhật entity thông thường**.
- Cascade persistence operations và `orphanRemoval` **không được thực hiện trên từng entity** chỉ vì bulk query đụng tới hàng tương ứng.
- Cơ chế optimistic locking tự động dựa trên `@Version` **bị bỏ qua** nếu truy vấn không tự đưa version vào logic.
- Các managed entities đã có trong persistence context có thể **giữ state cũ**, trái với database sau bulk query.

Một lệnh `executeUpdate()` không chỉ là “cách viết ngắn hơn”. Nó là **quyết định đổi mô hình thực thi**: từ quản lý graph object sang thao tác tập hợp ở database.

Bài học này giúp đánh giá tác động ấy đối với **callback, cascade và kiểm tra phiên bản** khi dùng JPQL `UPDATE`/`DELETE`, Criteria API `CriteriaUpdate`/`CriteriaDelete` hoặc Native SQL DML.

---

## 2. Phân biệt những đường cập nhật trong JPA

Một entity có thể bị thay đổi theo nhiều đường:

| Cách thay đổi | Đầu vào | Điều gì thực hiện thay đổi? | Có đi qua lifecycle của từng entity? |
|---|---|---|---|
| Sửa managed entity | Object đã được `find`/query rồi sửa field | Dirty checking + flush | **Có**, theo quy tắc lifecycle JPA |
| `em.remove(entity)` | Managed entity | JPA remove operation | **Có**; xét cascade, orphan removal, callback |
| `em.persist(newEntity)` | Entity mới | JPA persist operation | **Có**; xét cascade, callbacks |
| JPQL bulk `UPDATE` | Entity type + `WHERE` | SQL update tập hợp | **Không** cho từng hàng bị bulk update |
| JPQL bulk `DELETE` | Entity type + `WHERE` | SQL delete tập hợp | **Không** cho từng hàng bị bulk delete |
| Criteria `CriteriaUpdate` | Criteria tree | Bulk update theo điều kiện | **Không** cho từng hàng |
| Criteria `CriteriaDelete` | Criteria tree | Bulk delete theo điều kiện | **Không** cho từng hàng |
| Native SQL `UPDATE/DELETE` | Tên bảng/cột SQL thật | Database thực thi SQL | **Không** qua entity lifecycle JPA |

Cột cuối không có nghĩa “trong cả transaction không bao giờ có callback”. Ví dụ trước bulk update, JPA có thể flush **những thay đổi managed entities đã chờ sẵn** và callback tương ứng của quá trình flush vẫn có thể chạy. Điều **không xảy ra** là JPA tự nạp từng hàng do câu bulk query tác động để gọi callback của hàng đó.

### 2.1. Ba tầng dễ bị nhầm

```text
Entity / object graph
    |  domain methods, dirty checking, @Version,
    |  callbacks, cascade, orphanRemoval
    v
JPA persistence context
    |  managed entity state, identity map, pending changes
    v
Database transaction
    |  SQL UPDATE / DELETE, FK, CHECK, triggers, locks
    v
Committed rows
```

**Bulk DML** đi vào tầng database thông qua query engine, nhưng **không thực thi tương đương một chuỗi `em.remove` hoặc setter + flush trên mọi entity**.

Database vẫn áp dụng **constraints, triggers, isolation và locks** cho những câu SQL được gửi xuống. Những cơ chế database ấy khác với callback/cascade do JPA quản lý.

## 3. Nhắc lại lifecycle callbacks trong JPA

Các annotation callback chuẩn:

- `@PrePersist` — trước khi persist.
- `@PostPersist` — sau thao tác insert trong quá trình persistence.
- `@PreUpdate` — trước khi provider cập nhật một entity theo lifecycle bình thường.
- `@PostUpdate` — sau khi cập nhật entity theo lifecycle bình thường.
- `@PreRemove` — trước khi remove entity.
- `@PostRemove` — sau khi remove entity.
- `@PostLoad` — sau khi entity được load/refresh theo semantics JPA.

Callback có thể đặt trong entity hoặc trong listener class khai báo qua `@EntityListeners`.

### 3.1. Ví dụ callback cập nhật dấu thời gian

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    @Column(name = "row_version", nullable = false)
    private Long version;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 20)
    private OrderStatus status;

    @Column(name = "updated_at", nullable = false)
    private LocalDateTime updatedAt;

    protected PurchaseOrder() {}

    @PreUpdate
    private void beforeUpdate() {
        updatedAt = LocalDateTime.now();
    }

    @PreRemove
    private void beforeRemove() {
        // Ví dụ: kiểm tra logic cục bộ phù hợp.
        // Không thực hiện HTTP call/email không thể rollback tại đây.
    }

    public void expire() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                "Chỉ đơn DRAFT mới được chuyển thành EXPIRED"
            );
        }
        status = OrderStatus.EXPIRED;
    }
}
```

Đây là đoạn minh họa; phần sau trình bày entity đầy đủ hơn. Khi dùng `LocalDateTime.now()`, production cần có chính sách timezone/clock nhất quán.

**Managed update:**

```java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
order.expire();
em.flush(); // Nếu entity dirty, có thể gọi @PreUpdate và thực hiện UPDATE.
```

**Bulk update:**

```java
em.createQuery(
    "UPDATE PurchaseOrder o SET o.status = :newStatus WHERE o.id = :id"
)
.setParameter("newStatus", OrderStatus.EXPIRED)
.setParameter("id", orderId)
.executeUpdate();
```

Ở trường hợp bulk, `@PreUpdate` của `PurchaseOrder` **không được kích hoạt cho hàng do câu UPDATE này sửa**, và do đó code trong `beforeUpdate()` không tự cập nhật `updatedAt`.

Nếu phải cập nhật `updatedAt`, bulk query phải thực hiện **có chủ đích**:

```java
em.createQuery(
    """
    UPDATE PurchaseOrder o
    SET o.status = :newStatus, o.updatedAt = :now
    WHERE o.id = :id
    """
)
.setParameter("newStatus", OrderStatus.EXPIRED)
.setParameter("now", now)
.setParameter("id", orderId)
.executeUpdate();
```

### 3.2. Phân biệt `@PreUpdate` với database trigger

Một database có thể khai báo trigger kiểu:

```sql
-- Pseudocode, cú pháp mỗi RDBMS khác nhau:
AFTER UPDATE ON purchase_orders
    INSERT INTO order_audit ...
```

Trigger database có thể chạy cho SQL bulk update vì đó là cơ chế của database. Nhưng `@PreUpdate`/`@PostUpdate` ở Java **không chạy chỉ vì database UPDATE xảy ra**.

Không nên dựa vào một trigger để kết luận mọi JPA entity listener đều chạy, hoặc ngược lại.

### 3.3. Callback không phải phép thuật cho mọi biến đổi state

Ngay cả trong đường managed entity bình thường:

- `@PreUpdate` chỉ được gọi khi provider thực hiện một lifecycle update thích hợp, không đơn thuần vì có `find`.
- Thời điểm callback có thể nằm ở `flush`/`commit`.
- Một managed entity không dirty có thể không sinh SQL UPDATE/callback update.
- Query chỉ lấy scalar/DTO không tự biến thành entity callback.
- Callback không bảo đảm một external side effect (email, HTTP) sẽ được rollback nếu transaction DB thất bại.

Hãy xem callback như **một phần của entity lifecycle do JPA quản lý**, không phải cách duy nhất để bảo vệ invariant xuyên mọi đường ghi dữ liệu.

---

## 4. Nhắc lại cascade và orphan removal

Giả sử một đơn có nhiều dòng hàng:

```text
PurchaseOrder#10
  |
  +-- OrderLine#1001
  +-- OrderLine#1002
```

Mapping:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines = new ArrayList<>();
```

`CascadeType.ALL` bao gồm các cascade persistence operations:

- `PERSIST`
- `MERGE`
- `REMOVE`
- `REFRESH`
- `DETACH`

`orphanRemoval = true` là cơ chế riêng để xóa dependent entity khi nó bị tách khỏi association `@OneToMany` hoặc `@OneToOne` phù hợp.

### 4.1. Xóa từng managed entity

```java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
em.remove(order);
```

Khi `REMOVE` được cascade từ parent tới lines, provider quản lý quá trình remove của các line theo mapping/lifecycle. Các `@PreRemove`/`@PostRemove` callbacks có thể được áp dụng cho những entity được remove qua đường này.

### 4.2. Xóa bằng JPQL bulk

```java
em.createQuery(
    "DELETE FROM PurchaseOrder o WHERE o.id = :id"
)
.setParameter("id", orderId)
.executeUpdate();
```

Đây **không phải** việc JPA lặp qua từng order và gọi `em.remove(order)`. Vì vậy:

- `CascadeType.REMOVE` **không được áp dụng** để xóa các `OrderLine`.
- `orphanRemoval = true` **không được áp dụng** như khi gỡ child khỏi managed collection.
- `@PreRemove` và `@PostRemove` của order/line **không chạy** vì chính bulk DELETE.
- Database foreign key constraints vẫn được áp dụng.

Nếu `order_lines.order_id` tham chiếu `purchase_orders.id` với FK không có `ON DELETE CASCADE`, bulk DELETE parent có thể **thất bại do FK**.

**Không phải cứ mapping có `cascade = ALL, orphanRemoval = true` là mọi câu `DELETE FROM PurchaseOrder` tự động xóa các dòng hàng.**

---

## 5. Entity ví dụ hoàn chỉnh: `PurchaseOrder` và `OrderLine`

Bài dùng một domain tối giản có trạng thái và version.

### 5.1. Enum trạng thái

```java
package com.example.bulk;

public enum OrderStatus {
    DRAFT,
    EXPIRED,
    PAID,
    CANCELLED
}
```

### 5.2. Entity `PurchaseOrder`

```java
package com.example.bulk;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    @Column(name = "row_version", nullable = false)
    private Long version;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 20)
    private OrderStatus status = OrderStatus.DRAFT;

    @Column(name = "total_amount", nullable = false,
            precision = 15, scale = 2)
    private BigDecimal totalAmount;

    @Column(name = "expires_at", nullable = false)
    private LocalDateTime expiresAt;

    @Column(name = "updated_at", nullable = false)
    private LocalDateTime updatedAt;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true,
        fetch = FetchType.LAZY
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    public PurchaseOrder(
            BigDecimal totalAmount,
            LocalDateTime expiresAt,
            LocalDateTime now
    ) {
        this.totalAmount = Objects.requireNonNull(totalAmount);
        this.expiresAt = Objects.requireNonNull(expiresAt);
        this.updatedAt = Objects.requireNonNull(now);

        if (totalAmount.signum() < 0) {
            throw new IllegalArgumentException(
                "Tổng tiền không được âm"
            );
        }
    }

    public Long getId() { return id; }
    public Long getVersion() { return version; }
    public OrderStatus getStatus() { return status; }
    public LocalDateTime getUpdatedAt() { return updatedAt; }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }

    public void addLine(String sku, int quantity) {
        requireDraft();

        OrderLine line = new OrderLine(this, sku, quantity);
        lines.add(line);
    }

    public void expire() {
        requireDraft();
        this.status = OrderStatus.EXPIRED;
    }

    public void cancel() {
        if (status == OrderStatus.PAID) {
            throw new IllegalStateException(
                "Đơn đã thanh toán cần quy trình hoàn tiền"
            );
        }
        this.status = OrderStatus.CANCELLED;
    }

    private void requireDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                "Thao tác chỉ hợp lệ khi DRAFT"
            );
        }
    }

    @PreUpdate
    private void onPreUpdate() {
        this.updatedAt = LocalDateTime.now();
    }

    @PreRemove
    private void onPreRemove() {
        // Ví dụ chỗ callback của entity lifecycle.
        // Bulk DELETE không gọi phương thức này.
    }
}
```

`@Version` cho phép JPA hỗ trợ optimistic locking khi quản lý entity update/remove theo cơ chế thông thường. `@PreUpdate` điều chỉnh `updatedAt` khi có entity lifecycle update.

Điểm quan trọng về business method: `expire()` từ chối thay đổi từ trạng thái không phải `DRAFT`. Nhưng bulk query đặt trực tiếp `status` theo `WHERE` **không gọi `expire()`**. Nếu muốn bulk giữ đúng business invariant, phải mã hóa điều kiện tương ứng trong SQL/JPQL hoặc thiết kế use case khác.

### 5.3. Entity `OrderLine`

```java
package com.example.bulk;

import jakarta.persistence.*;

@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "sku", nullable = false, length = 64)
    private String sku;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    protected OrderLine() {}

    OrderLine(PurchaseOrder order, String sku, int quantity) {
        if (order == null || sku == null || sku.isBlank()
                || quantity <= 0) {
            throw new IllegalArgumentException(
                "Dòng hàng không hợp lệ"
            );
        }
        this.order = order;
        this.sku = sku;
        this.quantity = quantity;
    }

    public Long getId() { return id; }

    @PreRemove
    private void beforeRemove() {
        // Callback chỉ thuộc lifecycle remove qua JPA.
    }
}
```

`OrderLine.order` là owning side của FK, còn `PurchaseOrder.lines` là inverse side nhưng có cascade do domain sở hữu vòng đời các dòng.

### 5.4. SQL DDL

```sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    row_version BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(15, 2) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    sku VARCHAR(64) NOT NULL,
    quantity INTEGER NOT NULL,

    CONSTRAINT fk_line_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_orders(id)
);

CREATE INDEX ix_orders_status_expiry
    ON purchase_orders(status, expires_at);

CREATE INDEX ix_lines_order
    ON order_lines(order_id);
```

DDL không khai báo `ON DELETE CASCADE`. Vì vậy database từ chối xóa parent nếu còn rows child tham chiếu đến nó, trừ khi các rows được xóa/sửa theo một cách hợp lệ khác trước khi xóa parent.

Cấu trúc tạo khóa IDENTITY chỉ mang tính minh họa: cần điều chỉnh theo dialect database thực tế.

---

## 6. Một phép so sánh trực tiếp: managed update và bulk update

Giả sử có:

```text
PurchaseOrder#42
  status = DRAFT
  version = 5
  updated_at = 2026-11-01 09:00
```

### 6.1. Managed update

```java
PurchaseOrder order = em.find(PurchaseOrder.class, 42L);

order.expire();
em.flush();
```

Theo mapping/transaction phù hợp:

1. Entity `PurchaseOrder#42` được JPA quản lý.
2. `expire()` kiểm tra invariant `DRAFT`.
3. Khi dirty checking xác định có thay đổi, provider thực hiện lifecycle update.
4. `@PreUpdate` có thể đặt lại `updatedAt`.
5. Optimistic locking dựa trên `@Version` có thể tạo SQL có kiểm tra version và tăng version theo cơ chế provider.
6. `@PostUpdate` sẽ được gọi nếu có cấu hình và update lifecycle được thực hiện.
7. Nếu version đã đổi bởi transaction khác, provider có thể báo `OptimisticLockException`.

SQL khái niệm:

```sql
UPDATE purchase_orders
SET status = 'EXPIRED',
    updated_at = ?,
    row_version = 6
WHERE id = 42
  AND row_version = 5;
```

SQL thực tế và thời điểm thực thi do provider/dialect quyết định; ví dụ chỉ cho thấy **kiểm tra version** đi cùng một entity update thông thường.

### 6.2. Bulk JPQL update

```java
em.createQuery(
    """
    UPDATE PurchaseOrder o
    SET o.status = :expired
    WHERE o.id = :id
    """
)
.setParameter("expired", OrderStatus.EXPIRED)
.setParameter("id", 42L)
.executeUpdate();
```

SQL khái niệm:

```sql
UPDATE purchase_orders
SET status = 'EXPIRED'
WHERE id = 42;
```

Khác biệt:

- Không gọi `expire()`.
- Không có callback `@PreUpdate` được kích hoạt bởi row update này.
- Không tự cập nhật `updated_at` từ callback.
- Không tự kiểm tra `row_version = 5`.
- Không tự tăng `row_version` chỉ vì field có `@Version`.
- Managed `PurchaseOrder#42` đang nằm trong context có thể vẫn có `status = DRAFT`.

### 6.3. Ma trận tác động

| Thuộc tính | Managed entity update | Bulk JPQL UPDATE |
|---|---|---|
| Gọi domain method | Tùy code ứng dụng, thường có thể gọi. | Không tự gọi. |
| Dirty checking | Có. | Bypass cho các rows bulk. |
| `@PreUpdate` / `@PostUpdate` | Áp dụng theo lifecycle. | **Không gọi** cho các rows bulk sửa. |
| `@Version` tự động | Có theo JPA optimistic locking. | **Không bắt buộc kiểm tra/tăng**; cần tự thiết kế. |
| Cascade PERSIST/MERGE/REMOVE | Theo thao tác JPA tương ứng. | Không cascade entity operations chỉ vì bulk UPDATE. |
| Orphan removal | Theo association lifecycle được sửa. | Không tự kích hoạt. |
| Database constraint | Vẫn áp dụng. | Vẫn áp dụng. |
| Database trigger | Theo SQL thực tế. | Theo SQL thực tế. |
| Persistence context state | Managed state được đồng bộ qua flush. | Có thể stale sau query. |
| Khối lượng SQL | Có thể nhiều UPDATE per entity, có batching. | Thường diễn đạt thay đổi theo tập, đôi khi dịch thành nhiều SQL tùy inheritance/provider. |

**Thông điệp quan trọng:** bulk update không “tắt database transaction”; nó **bỏ qua tầng xử lý từng entity**.

---

## 7. Cú pháp JPQL bulk UPDATE

Cú pháp khái quát:

```text
UPDATE EntityName [alias]
SET attribute = expression [, attribute = expression ...]
[WHERE predicate]
```

Ví dụ:

```java
int changed = em.createQuery(
    """
    UPDATE PurchaseOrder o
    SET o.status = :expired,
        o.updatedAt = :now
    WHERE o.status = :draft
      AND o.expiresAt < :now
    """
)
.setParameter("draft", OrderStatus.DRAFT)
.setParameter("expired", OrderStatus.EXPIRED)
.setParameter("now", now)
.executeUpdate();
```

Điều kiện `o.status = DRAFT` là cách **mã hóa một phần business rule** vào `WHERE`. Nếu status đã được transaction khác đổi sang PAID, câu update theo điều kiện sẽ không đụng tới row ấy.

Nhưng câu này **vẫn chưa tự bảo vệ đầy đủ** mọi invariant phức tạp, nhất là khi invariant phụ thuộc nhiều bảng, dữ liệu đồng thời hoặc side effects.

### 7.1. `executeUpdate()` trả về gì?

Với JPQL update/delete, `executeUpdate()` trả số lượng entity bị tác động bởi bulk operation theo contract JPA. Giá trị này **không phải tổng số callback được chạy** và không nhất thiết bằng tổng số SQL rows của mọi bảng phụ khi một inheritance strategy làm provider phát nhiều SQL statements.

Ví dụ:

```java
int changed = query.executeUpdate();

log.info("Affected orders: {}", changed);
```

Nếu câu query định sửa **một entity xác định**, kiểm tra `changed == 1` có thể hữu ích để biết thao tác đã khớp đúng một row/entity.

Nếu câu query cố ý sửa một tập lớn, `changed` là một chỉ số kiểm soát phạm vi; không nên dùng nó thay thế báo cáo per-row audit nếu nghiệp vụ cần biết chính xác những ID đã thay đổi.

### 7.2. Không có `WHERE` là thay đổi toàn bộ tập

```java
em.createQuery(
    "UPDATE PurchaseOrder o SET o.status = :status"
)
.setParameter("status", OrderStatus.EXPIRED)
.executeUpdate();
```

Câu này có thể cập nhật **mọi đơn** của entity type, không phân biệt trạng thái. Nó bỏ qua domain methods và version handling như những bulk updates khác.

Trong production, nên yêu cầu một predicate scope rõ ràng (tenant, trạng thái trước đó, thời gian, job batch ID...) và kiểm tra expected affected count.

### 7.3. Không viết JPQL bằng tên bảng SQL

JPQL:

```sql
UPDATE PurchaseOrder o
SET o.status = :status
WHERE o.id = :id
```

không phải:

```sql
UPDATE purchase_orders
SET status = 'EXPIRED'
WHERE id = 42
```

Câu thứ hai là **native SQL** và được thực thi bằng `createNativeQuery` hoặc JDBC. Hai con đường đều bypass entity lifecycle khi thực thi bulk DML, nhưng cú pháp và tính portable khác nhau.

---

## 8. Cú pháp JPQL bulk DELETE

```java
int deleted = em.createQuery(
    """
    DELETE FROM PurchaseOrder o
    WHERE o.status = :expired
      AND o.expiresAt < :before
    """
)
.setParameter("expired", OrderStatus.EXPIRED)
.setParameter("before", cutoff)
.executeUpdate();
```

Đây là một phép xóa tập hợp: **không tự gọi `em.remove` trên từng `PurchaseOrder`**.

### 8.1. Một vấn đề xảy ra ngay: foreign key child

Với schema có:

```sql
FOREIGN KEY (order_id)
REFERENCES purchase_orders(id)
```

nếu order bị bulk DELETE vẫn có line tham chiếu, database có thể từ chối:

```text
foreign key violation:
order_lines.order_id references purchase_orders.id
```

Mapping:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines;
```

**không làm lỗi FK biến mất**, vì bulk delete không dùng REMOVE cascade của JPA.

### 8.2. Vì sao không đơn giản thêm cascade cho child?

Bạn có thể muốn sửa thành:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL
)
private List<OrderLine> lines;
```

Nhưng `ALL` đã bao gồm `REMOVE`. Nó hoạt động trong **entity remove lifecycle**, không chuyển một JPQL bulk DELETE thành vòng lặp JPA removes.

Cần thay đổi **chiến lược xóa**, không phải tăng số lượng cascade annotations.

---

## 9. Ba chiến lược xóa dữ liệu có dependent entities

### 9.1. Chiến lược A — load rồi `em.remove`: ưu tiên semantics JPA

```java
List<PurchaseOrder> expiredOrders = em.createQuery(
    """
    SELECT o FROM PurchaseOrder o
    WHERE o.status = :expired
      AND o.expiresAt < :cutoff
    """,
    PurchaseOrder.class
)
.setParameter("expired", OrderStatus.EXPIRED)
.setParameter("cutoff", cutoff)
.getResultList();

for (PurchaseOrder order : expiredOrders) {
    em.remove(order);
}
```

Ưu điểm:

- `@PreRemove`/`@PostRemove` được xử lý theo JPA lifecycle.
- `CascadeType.REMOVE` và dependent associations được xét.
- Có thể dùng optimistic locking của managed entities.
- Có thể kiểm soát domain conditions trước từng remove.

Nhược điểm:

- Phải load entities.
- Với rất nhiều child, provider có thể thực hiện nhiều SQL và dùng nhiều bộ nhớ.
- Transaction và lock có thể kéo dài.
- Callback/domain logic vẫn cần được thiết kế đúng; JPA cascade không tự bảo đảm mọi yêu cầu audit/pháp lý.

### 9.2. Chiến lược B — bulk xóa child rồi parent

Khi nghiệp vụ cho phép bypass callbacks và muốn SQL tập hợp:

```java
// Bước 1: xóa child của các parent đủ điều kiện.
int linesDeleted = em.createQuery(
    """
    DELETE FROM OrderLine l
    WHERE l.order.id IN (
        SELECT o.id
        FROM PurchaseOrder o
        WHERE o.status = :expired
          AND o.expiresAt < :cutoff
    )
    """
)
.setParameter("expired", OrderStatus.EXPIRED)
.setParameter("cutoff", cutoff)
.executeUpdate();

// Bước 2: xóa parent.
int ordersDeleted = em.createQuery(
    """
    DELETE FROM PurchaseOrder o
    WHERE o.status = :expired
      AND o.expiresAt < :cutoff
    """
)
.setParameter("expired", OrderStatus.EXPIRED)
.setParameter("cutoff", cutoff)
.executeUpdate();
```

Những điểm **bắt buộc đánh giá**:

- Hai bước phải nằm trong **transaction phù hợp** để rollback toàn bộ nếu một bước lỗi.
- Không có `@PreRemove`/`@PostRemove` của child/parent cho những rows bulk.
- Không có JPA cascade/orphanRemoval.
- Nếu parent bị sửa/đổi status giữa hai statement trong hệ thống concurrent, tập child bị xóa và tập parent cần xóa có thể lệch; isolation/locks hoặc cơ chế xác định tập ID phải đáp ứng invariant.
- FK khác hoặc descendants sâu hơn có thể yêu cầu xóa theo thứ tự khác.
- `executeUpdate` count hai câu không tự diễn đạt toàn bộ auditing event per order.
- Nếu có second-level cache hoặc managed entities cũ, phải xử lý đồng bộ.

Ví dụ chỉ minh họa một cách xóa theo quan hệ đơn giản, không phải phương án chung cho mọi schema.

### 9.3. Chiến lược C — database `ON DELETE CASCADE`

Schema:

```sql
ALTER TABLE order_lines
ADD CONSTRAINT fk_line_order
FOREIGN KEY (order_id)
REFERENCES purchase_orders(id)
ON DELETE CASCADE;
```

DDL này chỉ minh họa ý tưởng; với database đã có FK, cần drop/alter constraint đúng dialect thay vì luôn có thể thêm constraint trùng tên.

Khi database có `ON DELETE CASCADE`, bulk DELETE parent có thể khiến database tự xóa các hàng child.

**Nhưng:**

- Đây là **database-level referential action**, không phải JPA `CascadeType.REMOVE`.
- `@PreRemove`/`@PostRemove` của child **không chạy**.
- Persistence context có thể còn managed `OrderLine` mà row đã bị database xóa.
- ORM cache/audit lifecycle không tự được đồng bộ.
- DB triggers có thể chạy theo luật của database (khác với JPA callbacks).
- Phải xác định ảnh hưởng tới retention, compliance, event sourcing và phục hồi dữ liệu.

Chọn DB cascade khi hiểu rõ những đánh đổi đó; không dùng nó như “sửa nhanh” vì bulk DELETE không gọi cascade của JPA.

---

## 10. `orphanRemoval` không được kích hoạt bởi bulk UPDATE FK

Trong entity-managed workflow:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, id);
OrderLine line = ...; // line thuộc order.

order.removeLine(line); // Helper cập nhật collection và owning side.
```

Nếu `@OneToMany(orphanRemoval = true)`, một dependent child được loại khỏi association theo semantics JPA có thể được remove tại flush.

Một câu bulk update kiểu:

```sql
-- Native SQL chỉ để minh họa ý nghĩa, không phải thay thế orphanRemoval.
UPDATE order_lines
SET order_id = NULL
WHERE id = 1001;
```

**không tự kích hoạt JPA orphan removal**, dù kết quả SQL có thể làm line “không còn parent” về mặt FK.

Với mapping `optional=false` và `order_id NOT NULL` trong ví dụ, DB sẽ từ chối thao tác đặt FK thành NULL ngay cả trước khi xét orphan removal.

### 10.1. Không tự hiểu mọi FK NULL là orphan cần xóa

Một số domain cho phép child đổi owner hoặc tồn tại độc lập. Database FK có thể null và hợp lệ; orphan removal chỉ đúng khi **entity ownership lifecycle** quy định rằng child bị tách phải bị xóa.

Nếu muốn xóa những rows orphan bằng bulk job, đó là một **explicit data cleanup query**, không phải cách JPA tự quan sát một biến động của object graph rồi cascade theo entity.

### 10.2. Soft delete không đồng nghĩa `orphanRemoval`

Đánh dấu:

```java
UPDATE OrderLine l SET l.deleted = true WHERE ...
```

(giả định entity có thuộc tính `deleted`) là **soft delete**. Nó không tương đương `em.remove(line)` và không dùng `@PreRemove`.

Nếu hệ thống có yêu cầu audit, retention hoặc event khi xóa mềm, ứng dụng phải chọn cơ chế tạo audit/event phù hợp cho cả đường bulk lẫn đường managed.

---

## 11. `@Version` và optimistic locking hoạt động ra sao?

Giả sử entity:

```java
@Version
@Column(name = "row_version", nullable = false)
private Long version;
```

Trong workflow managed:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, 42L);
// version = 5
order.expire();
em.flush();
```

Provider có thể sinh SQL khái niệm:

```sql
UPDATE purchase_orders
SET status = 'EXPIRED',
    row_version = 6
WHERE id = 42
  AND row_version = 5;
```

Nếu version database không còn 5 (do transaction khác đã cập nhật), số hàng matched có thể bằng 0, dẫn tới optimistic lock conflict. Provider ném `OptimisticLockException` hoặc báo lỗi tương ứng ở flush/commit.

### 11.1. Bulk UPDATE bỏ qua cơ chế này

```java
em.createQuery(
    """
    UPDATE PurchaseOrder o
    SET o.status = :expired
    WHERE o.id = :id
    """
)
.setParameter("expired", OrderStatus.EXPIRED)
.setParameter("id", 42L)
.executeUpdate();
```

**Không có quy tắc JPA tự động** thêm `AND row_version = ?` hoặc `SET row_version = row_version + 1` vào bulk update.

Ngay cả khi `PurchaseOrder` có `@Version`, câu bulk update trên vẫn có thể thay đổi `status` mà không tăng version.

### 11.2. Điều đó nguy hiểm thế nào?

Hai transaction:

```text
Database: Order#42 (status=DRAFT, version=5)

T1:
    load Order#42 -> DRAFT, version=5

T2:
    bulk UPDATE status=EXPIRED
    (KHÔNG tăng version)
    COMMIT
    DB: EXPIRED, version=5

T1:
    order.cancel() -> status=CANCELLED
    flush: UPDATE ... WHERE version=5
    thành công vì version vẫn 5
    COMMIT

Kết quả: CANCELLED, version=6
          T2 bị ghi đè mà không có optimistic conflict.
```

Vì T2 đã sửa dữ liệu **không tăng version**, T1 không thể nhận ra thay đổi thông qua `@Version`.

Đây là một dạng **lost update về mặt nghiệp vụ**. Việc T2 dùng bulk query không bị API cấm; nhưng nếu dữ liệu đó đồng thời được cập nhật bằng managed entities, sự thiếu version discipline có thể phá cơ chế concurrency chung.

### 11.3. Bulk DELETE cũng không tự kiểm tra version

```java
em.createQuery(
    "DELETE FROM PurchaseOrder o WHERE o.id = :id"
)
.setParameter("id", 42L)
.executeUpdate();
```

Không có `WHERE o.version = :expectedVersion` trừ khi code tự thêm. Transaction có thể xóa row ngay cả khi một người khác vừa thay đổi nó, nếu predicate không hạn chế.

Ngoài ra bulk DELETE còn bypass `@PreRemove` và cascade/orphanRemoval, nên xóa dữ liệu chứa history/dependents cần đánh giá cả **concurrency lẫn lifecycle**.

---

## 12. Mẫu optimistic locking thủ công cho bulk UPDATE một entity

Để giữ discipline với một `@Version Long`:

```java
int updated = em.createQuery(
    """
    UPDATE PurchaseOrder o
    SET o.status = :expired,
        o.updatedAt = :now,
        o.version = o.version + 1
    WHERE o.id = :id
      AND o.status = :draft
      AND o.version = :expectedVersion
    """
)
.setParameter("expired", OrderStatus.EXPIRED)
.setParameter("draft", OrderStatus.DRAFT)
.setParameter("now", now)
.setParameter("id", orderId)
.setParameter("expectedVersion", expectedVersion)
.executeUpdate();

if (updated != 1) {
    throw new ConcurrentModificationException(
        "Đơn không tồn tại, sai trạng thái hoặc version đã đổi"
    );
}
```

Cách làm này có ba ý:

1. **WHERE theo ID**: nhắm đúng một đơn.
2. **WHERE theo version và trạng thái mong đợi**: chỉ cập nhật khi preconditions còn đúng.
3. **SET version = version + 1**: báo cho các managed transactions khác rằng hàng đã thay đổi.

Một câu UPDATE có điều kiện tại database có thể đánh giá preconditions và thay đổi row một cách **atomic theo một SQL statement**, phù hợp cho compare-and-set trên một hàng.

### 12.1. Có phải mọi kiểu `@Version` đều tăng bằng `+ 1` không?

Không. Ví dụ dùng `Long`, là numeric version có thể tăng. Nếu version là timestamp hoặc một kiểu do provider quản lý với cách sinh version riêng, không được máy móc viết `version + 1`.

Ngay cả numeric version có thể được provider/configuration quản lý theo convention riêng. Khi ứng dụng quyết định **tự tăng version trong bulk query**, phải bảo đảm quy tắc đó thống nhất với cách entity updates bình thường xử lý version.

### 12.2. `updated != 1` là lỗi gì?

Kết quả 0 có thể do:

- ID không tồn tại.
- Status không còn là DRAFT.
- Version không khớp.
- Các điều kiện khác trong WHERE không thỏa.

Không thể kết luận **chắc chắn version conflict** chỉ từ `0` khi WHERE còn nhiều predicate.

Tầng service có thể trả một lỗi tổng quát “Không thể cập nhật theo trạng thái hiện tại” hoặc đọc lại để phân biệt nguyên nhân, tùy UX/contract. Nếu đọc lại, cần xem isolation, transaction boundary và tránh giả định kết quả readback là nguyên nhân lịch sử duy nhất trong môi trường concurrent.

### 12.3. Không gọi thêm một SELECT rồi mới UPDATE mà bỏ WHERE version

Sai:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, id);

if (order.getVersion().equals(expectedVersion)) {
    // Giữa hai dòng có thể có transaction khác cập nhật.
    em.createQuery(
        "UPDATE PurchaseOrder o SET o.status = :status WHERE o.id = :id"
    ).executeUpdate();
}
```

Đây là race condition **check-then-act**. Muốn precondition chống concurrent write có ý nghĩa, cần đưa version vào **cùng câu UPDATE** hoặc dùng lock/transaction isolation phù hợp.

### 12.4. Kết thúc bằng transaction commit

`executeUpdate() == 1` chỉ nói câu UPDATE đã tác động một entity theo transaction hiện tại. Transaction vẫn có thể rollback do lỗi sau đó. Không gửi kết quả “đã lưu bền vững” ra ngoài trước khi transaction boundary commit thành công.

---

## 13. Mẫu optimistic locking cho bulk DELETE một entity

Nếu nghiệp vụ cho phép xóa hẳn một order **không có dependent rows**, có thể dùng:

```java
int deleted = em.createQuery(
    """
    DELETE FROM PurchaseOrder o
    WHERE o.id = :id
      AND o.version = :expectedVersion
      AND o.status = :draft
    """
)
.setParameter("id", orderId)
.setParameter("expectedVersion", expectedVersion)
.setParameter("draft", OrderStatus.DRAFT)
.executeUpdate();

if (deleted != 1) {
    throw new IllegalStateException(
        "Không thể xóa: đơn đã đổi hoặc không phù hợp"
    );
}
```

Với DELETE, không cần tăng version của **row bị xóa** vì row không còn tồn tại sau commit. Nhưng precondition version là cách tránh xóa một row đã được thay đổi kể từ thời điểm caller đọc.

**Cần đánh giá thêm:**

- FK tới lines, payments, audit records.
- Quy tắc retention/legal hold.
- `@PreRemove` và cascade không chạy.
- Cache/persistence context stale.
- External events cần phát sau commit.
- Sự vắng mặt row ở thời điểm query và kết quả commit.
- Số rows bị ảnh hưởng trong inheritance mapping.

Nếu business cần callback/cascade và không có yêu cầu throughput cực lớn, đường `find + em.remove` thường dễ diễn đạt semantics hơn.

---

## 14. Bulk UPDATE nhiều hàng và ý nghĩa của version

Một batch:

```java
int affected = em.createQuery(
    """
    UPDATE PurchaseOrder o
    SET o.status = :expired,
        o.updatedAt = :now,
        o.version = o.version + 1
    WHERE o.status = :draft
      AND o.expiresAt < :now
    """
)
.setParameter("expired", OrderStatus.EXPIRED)
.setParameter("draft", OrderStatus.DRAFT)
.setParameter("now", now)
.executeUpdate();
```

đảm bảo numeric version của những rows được cập nhật tăng lên khi query thực thi thành công. Điều đó giúp managed updates từ phiên cũ phát hiện version thay đổi.

Nhưng **khác một compare-and-set theo từng ID**:

- Batch không biết caller mong đợi version cụ thể của từng row nào.
- Không thể từ `affected = 1000` suy ra 1000 user expectations độc lập đều hợp lệ.
- Một row chỉ được update nếu thỏa `status`/`expiresAt` tại thời điểm statement xét điều kiện theo semantics DB.
- Những rows bị transaction khác thay đổi trước đó có thể không còn được chọn.
- Business invariants phụ thuộc nhiều bảng có thể cần isolation/lock bổ sung.

Nếu mục tiêu là “đánh dấu tất cả DRAFT hết hạn tại thời điểm chạy”, query ở trên có thể phù hợp. Nếu mục tiêu là “cập nhật chính xác 1000 đơn đã duyệt với expected version riêng”, cần một **cơ chế theo từng version** hoặc thiết kế batch conditions/table of expected values.

### 14.1. Tại sao cập nhật version thủ công vẫn chưa thay thế callback?

Câu query đã tăng `version` và đặt `updatedAt`, nhưng vẫn không gọi:

- `PurchaseOrder.expire()`.
- `@PreUpdate`.
- `@PostUpdate`.
- Domain event tạo trong service method.
- Custom validation chạy trên Java entity instance.

Mỗi invariant cần được đánh giá độc lập. Không nên coi “đã tăng version” là đồng nghĩa lifecycle đã được bảo toàn.

### 14.2. Version root và child

Nếu `OrderLine` được sửa bởi bulk UPDATE:

```java
UPDATE OrderLine l
SET l.quantity = l.quantity + 1
WHERE l.id = :lineId
```

thì `PurchaseOrder.version` **không tự tăng** chỉ vì line thuộc collection của order. Đây còn là vấn đề của thay đổi child qua managed entities: cần thiết kế rõ aggregate-level concurrency.

Nếu một business invariant phụ thuộc vào cả root và lines, có thể:

- Dùng một query cập nhật root version trong cùng transaction có điều kiện.
- Chọn locking strategy phù hợp, chẳng hạn `OPTIMISTIC_FORCE_INCREMENT` trên managed root khi đang làm qua entity.
- Dùng database constraint/atomic updates để bảo vệ invariant.
- Thiết kế command có expected aggregate version.

Không dựa vào quan hệ `@OneToMany` như một lời hứa rằng mọi bulk child update tự bảo vệ root version.

---

## 15. Trạng thái persistence context sau bulk query: vấn đề “hai sự thật”

Ví dụ trong **cùng EntityManager**:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, 42L);

// Object Java hiện là DRAFT.
System.out.println(order.getStatus());

int changed = em.createQuery(
    """
    UPDATE PurchaseOrder o
    SET o.status = :expired
    WHERE o.id = :id
    """
)
.setParameter("expired", OrderStatus.EXPIRED)
.setParameter("id", 42L)
.executeUpdate();

// Entity managed có thể VẪN là DRAFT.
System.out.println(order.getStatus());
```

Database row đã được update trong transaction hiện tại, nhưng object Java đang managed có thể không được JPA sửa theo.

### 15.1. Vì sao JPA không tự đồng bộ tất cả managed entities?

Bulk query có thể cập nhật hàng nghìn rows qua những điều kiện phức tạp. JPA không thực thi như một vòng lặp entity-by-entity, nên nó không tự biết/cập nhật trạng thái của mọi object đã có trong persistence context.

Đặc tả khuyến nghị thực hiện bulk operations trong **persistence context mới** hoặc **trước khi tìm/tải các entity có thể bị ảnh hưởng**, để tránh sự không nhất quán giữa managed state và database.

### 15.2. Rủi ro sau đó: dirty checking ghi đè lại kết quả bulk

Giả sử `order` đang managed với:

```text
status = DRAFT
version = 5
```

Bulk đổi DB thành:

```text
status = EXPIRED
version = 5
```

Sau đó code sửa một field khác trên `order` và flush. Nếu version không đổi, một SQL update từ state cũ có thể gây dữ liệu bất ngờ tùy dirty fields/update strategy/provider.

Đừng sử dụng managed entities đang stale để tiếp tục một transaction như thể bulk query đã thay đổi chúng trong memory.

### 15.3. `find()` lại có chắc lấy row mới không?

Không nên giả định:

```java
PurchaseOrder again = em.find(PurchaseOrder.class, 42L);
```

sẽ bắt buộc SELECT lại từ DB. Nếu entity đã tồn tại trong identity map, `find` có thể trả **cùng managed instance cũ**.

Để quan sát state database mới, dùng context mới hoặc refresh phù hợp; xem phần tiếp theo.

---

## 16. Quy trình `flush → bulk query → clear`

Khi bắt buộc kết hợp managed changes và bulk update trong một unit of work, một quy trình thường dùng là:

```java
em.flush(); // Đồng bộ pending changes của managed entities.
int affected = em.createQuery(jpql)
        .setParameter("status", newStatus)
        .executeUpdate();
em.clear(); // Detach managed entities, tránh sử dụng state cũ.
```

Ba thao tác giải quyết ba vấn đề khác nhau:

| Thao tác | Mục đích |
|---|---|
| `em.flush()` | Đẩy pending managed changes vào database transaction trước bulk query. |
| `executeUpdate()` | Chạy bulk update/delete trên tập rows phù hợp. |
| `em.clear()` | Detach các managed entities để chúng không tiếp tục bị coi là state đồng bộ với database sau bulk. |

### 16.1. Cực kỳ quan trọng: `clear()` có thể làm mất pending changes

```java
PurchaseOrder a = em.find(PurchaseOrder.class, aId);
a.cancel();

// Rất nguy hiểm nếu chưa flush:
em.clear();
```

`em.clear()` detach tất cả managed entities. Pending changes chưa được flush **không được tự động ghi chỉ vì clear**.

Đó là lý do nếu cần bảo tồn những thay đổi trước bulk, hãy `flush()` có chủ đích **trước** khi `clear()`.

### 16.2. `flush` trước bulk có thể kích hoạt callback bình thường

Nếu trước bulk có managed `PurchaseOrder` dirty, `em.flush()` có thể kích hoạt `@PreUpdate` cho các thay đổi ấy. Điều này **không mâu thuẫn** với nhận định bulk update bypass callback.

Phải chỉ rõ nguồn thay đổi:

```text
Managed changes -- flush --> entity callbacks có thể chạy.

Bulk UPDATE -------- SQL --> không gọi callback từng row bulk.
```

### 16.3. `clear()` chỉ xử lý first-level persistence context

`em.clear()` không tự xóa mọi entry trong:

- JPA second-level cache.
- Spring application cache.
- Distributed Redis cache.
- HTTP cache.
- DTO cache.

Tùy provider, bulk operations có thể có các chính sách invalidation riêng nhưng **không nên giả định tất cả cache trong hệ thống đều đồng bộ**. Nếu cần, dùng `EntityManagerFactory.getCache().evict(...)` hoặc chính sách cache của tầng tương ứng sau khi đánh giá phạm vi.

### 16.4. Cẩn thận với `clear()` giữa use case phức tạp

Nếu application đang giữ các managed entities và muốn tiếp tục gọi domain methods sau bulk, `clear()` sẽ làm chúng detached.

Điều này có thể gây:

- Không còn dirty checking tự động.
- Lazy association access lỗi ngoài context thích hợp.
- `merge` lại graph không đúng thời điểm.
- Dùng object stale không biết đã detach.

Vì vậy phương án đơn giản hơn đôi khi là **tách bulk operation vào EntityManager/transaction riêng** thay vì xen nó giữa logic aggregate phức tạp.

---

## 17. Dùng `refresh()` thay `clear()` khi chỉ cần một entity

Nếu muốn đồng bộ một managed entity cụ thể sau bulk:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, 42L);

em.createQuery(
    "UPDATE PurchaseOrder o SET o.status = :expired WHERE o.id = :id"
)
.setParameter("expired", OrderStatus.EXPIRED)
.setParameter("id", 42L)
.executeUpdate();

em.refresh(order);

System.out.println(order.getStatus()); // Đọc state sau refresh.
```

`refresh` tải lại state của entity theo semantics persistence context/transaction/isolation.

**Nhưng:**

- Pending local changes của entity được refresh có thể bị ghi đè.
- Refresh không phải phương án đồng bộ hàng nghìn entities tự động.
- Nếu bulk DELETE đã xóa row, `refresh` trên object cũ không phải cách phù hợp để “đọc trạng thái mới”; có thể gây `EntityNotFoundException` hoặc lỗi tương ứng.
- Transaction isolation có thể chi phối dữ liệu nhìn thấy.
- Refresh có thể cascade nếu mapping có `CascadeType.REFRESH`, ảnh hưởng các entities liên quan.

`clear` và `refresh` có mục đích khác nhau; chọn công cụ theo **phạm vi entity cần đồng bộ**.

---

## 18. `FlushModeType.AUTO` không chữa vấn đề stale state sau bulk

JPA có hai flush modes thường gặp:

- `FlushModeType.AUTO`.
- `FlushModeType.COMMIT`.

Trong `AUTO`, provider phải bảo đảm những thay đổi managed có thể ảnh hưởng tới việc xử lý query được nhìn thấy theo quy tắc đặc tả; provider có thể quyết định flush phù hợp.

Nhưng **điều đó không có nghĩa** sau bulk query provider tự cập nhật managed entities bị ảnh hưởng.

Hai hướng khác nhau:

```text
Trước query:
  Managed changes -> database visibility cho query.

Sau bulk query:
  Database changes -> managed entities đã load?
                     Không được bảo đảm tự đồng bộ.
```

Khi correctness phụ thuộc thứ tự:

```java
em.flush();
query.executeUpdate();
em.clear();
```

giúp ý định tường minh hơn.

Không dùng `FlushModeType.COMMIT` như một giải pháp để tránh callback/cascade hoặc để bỏ qua việc hiểu state; nó chỉ ảnh hưởng thời điểm flush, không đổi ngữ nghĩa bulk DML.

---

## 19. `CriteriaUpdate` và `CriteriaDelete` cũng là bulk DML

Một số developer nghĩ rằng dùng Criteria API thì provider sẽ “hiểu entity” và tự chạy callback/cascade. **Không đúng.**

`CriteriaUpdate` và `CriteriaDelete` được đưa vào JPA từ 2.1 để xây bulk DML bằng Criteria API.

### 19.1. `CriteriaUpdate`

```java
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaUpdate;
import jakarta.persistence.criteria.Root;

CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaUpdate<PurchaseOrder> update =
    cb.createCriteriaUpdate(PurchaseOrder.class);

Root<PurchaseOrder> order =
    update.from(PurchaseOrder.class);

update.set("status", OrderStatus.EXPIRED);
update.set("updatedAt", now);

update.where(
    cb.and(
        cb.equal(order.get("status"), OrderStatus.DRAFT),
        cb.lessThan(
            order.<LocalDateTime>get("expiresAt"),
            now
        )
    )
);

int changed = em.createQuery(update).executeUpdate();
```

Đây là **bulk update**, dù `CriteriaUpdate` có type-safe constructs.

Nó vẫn:

- Bypass `@PreUpdate`/`@PostUpdate` cho rows bulk.
- Không cascade persistence operations.
- Không tự kiểm tra/tăng `@Version`.
- Không đồng bộ các managed instances đã có với database.

### 19.2. `CriteriaDelete`

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaDelete<PurchaseOrder> delete =
    cb.createCriteriaDelete(PurchaseOrder.class);

Root<PurchaseOrder> order =
    delete.from(PurchaseOrder.class);

delete.where(
    cb.equal(order.get("status"), OrderStatus.EXPIRED)
);

int count = em.createQuery(delete).executeUpdate();
```

Cũng là bulk delete: **không gọi `@PreRemove`, cascade REMOVE hoặc orphanRemoval theo từng entity**.

### 19.3. Version thủ công trong CriteriaUpdate

Khi version là `Long`:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaUpdate<PurchaseOrder> update =
    cb.createCriteriaUpdate(PurchaseOrder.class);

Root<PurchaseOrder> order =
    update.from(PurchaseOrder.class);

update.set("status", OrderStatus.EXPIRED);

update.set(
    order.<Long>get("version"),
    cb.sum(order.<Long>get("version"), 1L)
);

update.where(
    cb.and(
        cb.equal(order.get("id"), orderId),
        cb.equal(order.get("version"), expectedVersion),
        cb.equal(order.get("status"), OrderStatus.DRAFT)
    )
);

int changed = em.createQuery(update).executeUpdate();
```

Ý nghĩa giống compare-and-set JPQL trong phần 12. Code cần import các loại Criteria/Java tương ứng. `cb.sum` không phải cơ chế tự động của `@Version`; chính application đã **chủ động** thêm expression cập nhật version.

### 19.4. Criteria không thay thế review phạm vi

Dù Criteria có typed paths, nó không tự biết use case nào yêu cầu audit, event, ownership hoặc soft delete. Những rủi ro về callback/cascade/version giống như JPQL bulk DML.

---

## 20. Giới hạn cú pháp bulk DML: không viết JOIN tùy tiện

Trong JPQL chuẩn, bulk `UPDATE`/`DELETE` có **một entity target** trong mệnh đề FROM/UPDATE. Không trực tiếp viết các JOIN tùy ý như query `SELECT`:

```sql
-- Không phải JPQL bulk UPDATE portable:
UPDATE PurchaseOrder o JOIN o.lines l
SET o.status = :status
WHERE l.quantity > 10
```

Nếu cần điều kiện phụ thuộc association, có thể dùng **subquery** trong `WHERE` khi phù hợp:

```java
int changed = em.createQuery(
    """
    UPDATE PurchaseOrder o
    SET o.status = :review
    WHERE o.status = :draft
      AND EXISTS (
          SELECT l.id
          FROM OrderLine l
          WHERE l.order = o
            AND l.quantity > :threshold
      )
    """
)
.setParameter("review", OrderStatus.CANCELLED)
.setParameter("draft", OrderStatus.DRAFT)
.setParameter("threshold", 10)
.executeUpdate();
```

Đây là ví dụ cú pháp điều kiện; về domain, chuyển sang CANCELLED có thể cần business process khác. **Subquery trong WHERE không làm callback/cascade/version tự hoạt động**.

### 20.1. Không suy ra một `JOIN FETCH` cho bulk UPDATE

`JOIN FETCH` là công cụ tải association trong query select. Nó không được dùng để biến bulk UPDATE thành một thao tác load graph rồi xử lý từng entity.

### 20.2. Dùng native SQL nếu cần cú pháp DML đặc thù

Một số RDBMS hỗ trợ:

```sql
UPDATE purchase_orders
SET status = 'EXPIRED'
FROM order_lines
WHERE ...
```

hoặc `DELETE ... USING`, CTE, `RETURNING`. Đây là **SQL dialect-specific**; khi cần, dùng native query/JDBC, nhưng vẫn phải thiết kế callback/cascade/version và cache theo nguyên tắc bulk DML.

---

## 21. Native SQL UPDATE/DELETE: còn xa hơn khỏi entity lifecycle

Ví dụ:

```java
int changed = em.createNativeQuery(
    """
    UPDATE purchase_orders
    SET status = ?,
        row_version = row_version + 1,
        updated_at = ?
    WHERE id = ?
      AND row_version = ?
    """
)
.setParameter(1, "EXPIRED")
.setParameter(2, now)
.setParameter(3, orderId)
.setParameter(4, expectedVersion)
.executeUpdate();
```

Vì đây là SQL trực tiếp:

- Sử dụng tên bảng/cột thật.
- Không dùng JPA enum mapping tự động theo cách JPQL attribute `o.status` thông thường; ví dụ truyền `"EXPIRED"` theo schema VARCHAR.
- Không gọi lifecycle callbacks.
- Không cascade entity operations.
- Không tự đồng bộ first-level cache.
- Version phải do SQL/caller xử lý nếu muốn optimistic discipline.

### 21.1. Trigger DB vẫn hoạt động

Nếu database có trigger audit chạy sau UPDATE/DELETE, native SQL có thể kích hoạt trigger theo database rules. Nhưng audit được tạo bởi DB trigger không nhất thiết có cùng nội dung với event được phát trong `@PostUpdate` hoặc domain method.

### 21.2. `executeUpdate` count của native query

Với native SQL, số lượng trả về phụ thuộc semantics JDBC/database cho statement. Không nên đồng nhất **affected parent rows** với số child rows bị DB cascade xóa hoặc với số business entities nhận event.

### 21.3. Native SQL có thể bypass schema-level abstraction

JPQL UPDATE làm việc với entity model/attribute names và có thể được provider dịch khác nhau theo inheritance mapping. Native SQL tác động trực tiếp bảng thực tế, nên khi entity được ánh xạ qua nhiều bảng (`JOINED` inheritance, secondary tables), một câu native UPDATE có thể **không cập nhật toàn bộ state liên quan** như developer tưởng.

Native query là lựa chọn có chủ đích về database, không phải lối đi “mặc định tốt hơn” cho mọi write.

---

## 22. Spring Data JPA `@Modifying`: một bẫy thường gặp

Trong ứng dụng Spring Data JPA, repository có thể khai báo:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Modifying
    @Query("""
        UPDATE PurchaseOrder o
        SET o.status = :expired
        WHERE o.status = :draft
          AND o.expiresAt < :now
        """)
    int expireDrafts(
        @Param("draft") OrderStatus draft,
        @Param("expired") OrderStatus expired,
        @Param("now") LocalDateTime now
    );
}
```

Đây vẫn là **JPQL bulk UPDATE**, dù method nằm trong Spring Data repository.

### 22.1. Những điều `@Modifying` không thay đổi

- Không tự chạy `@PreUpdate` cho từng row.
- Không kích hoạt domain method `expire()`.
- Không áp dụng JPA cascade remove/orphanRemoval.
- Không tự bump `@Version`.
- Không tự cập nhật những managed instances đã load.

### 22.2. `flushAutomatically` và `clearAutomatically`

Spring Data JPA cung cấp các option:

```java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query("""
    UPDATE PurchaseOrder o
    SET o.status = :expired
    WHERE o.status = :draft
    """)
int expireAllDrafts(
    @Param("draft") OrderStatus draft,
    @Param("expired") OrderStatus expired
);
```

Ý nghĩa khái quát:

- `flushAutomatically = true`: flush persistence context trước modifying query.
- `clearAutomatically = true`: clear persistence context sau modifying query.

Chúng giúp quản lý stale state trong một số tình huống. **Chúng không biến bulk query thành entity lifecycle update.**

Cần có transaction boundary thích hợp, ví dụ service `@Transactional`. Khi clear, các object trước đó có thể detached, ảnh hưởng phần code chạy sau repository call.

### 22.3. Repository delete method có thể có semantics khác nhau

Trong Spring Data JPA, cách xóa từng entity thông thường và cách xóa theo batch/bulk query không phải lúc nào cũng giống nhau:

- Xóa qua `EntityManager.remove`/từng entity: đi qua lifecycle/cascade theo mapping.
- Một bulk repository delete/query: bypass per-entity lifecycle.

Không suy luận từ tên method chứa chữ `delete` rằng mọi thao tác đều gọi `@PreRemove`; cần biết implementation/API cụ thể.

---

## 23. Soft delete, `@PreRemove` và audit: hậu quả kinh doanh

Một hệ thống kế toán có quy tắc: **đơn đã thanh toán không được xóa cứng**. Thông thường service có domain guard:

```java
public void deleteDraftOrder(Long orderId) {
    PurchaseOrder order = em.find(
        PurchaseOrder.class,
        orderId
    );

    if (order == null) {
        return;
    }

    if (order.getStatus() != OrderStatus.DRAFT) {
        throw new IllegalStateException(
            "Không thể xóa đơn ngoài trạng thái DRAFT"
        );
    }

    em.remove(order);
}
```

Một bulk query:

```java
em.createQuery(
    "DELETE FROM PurchaseOrder o WHERE o.id = :id"
)
.setParameter("id", orderId)
.executeUpdate();
```

bỏ qua guard trong service nếu được gọi từ nơi khác.

**Hệ quả:** không nên để quy tắc giữ dữ liệu quan trọng chỉ tồn tại ở callback hoặc một đường gọi service nếu ứng dụng còn có DML bulk/native, migration, job riêng hoặc hệ thống ghi DB khác.

### 23.1. Các lớp bảo vệ nên được xem xét

- Domain method/application command bảo vệ workflow bình thường.
- Query predicate giới hạn trạng thái đối với bulk operations.
- Database constraints cho invariant có thể kiểm tra ở DB.
- Quyền/permission kiểm soát ai được chạy DML.
- Audit log/outbox được thiết kế cho cả đường managed và bulk.
- Retention/soft delete policy ở kiến trúc dữ liệu.
- Integration tests trên cả hai đường thực thi.

### 23.2. Provider-specific soft delete annotation có thể không áp dụng cho bulk

Một số ORM có extension để chuyển entity `remove` thành SQL UPDATE hoặc áp bộ lọc soft-deleted entities.

Đừng mặc định một JPQL/native bulk `DELETE` sẽ được rewrite giống thao tác `em.remove(entity)` trong mọi provider/version. Phải kiểm tra semantics của extension và SQL thực tế.

### 23.3. Bulk soft delete cần tự bảo vệ audit fields và version

Ví dụ:

```java
int affected = em.createQuery(
    """
    UPDATE PurchaseOrder o
    SET o.status = :cancelled,
        o.updatedAt = :now,
        o.version = o.version + 1
    WHERE o.status = :draft
    """
)
.setParameter("cancelled", OrderStatus.CANCELLED)
.setParameter("draft", OrderStatus.DRAFT)
.setParameter("now", now)
.executeUpdate();
```

Việc đặt `updatedAt`, bump version và lọc trạng thái là **trách nhiệm tường minh** của query. Nếu còn cần `cancelledBy`, `cancelReason`, event audit hoặc quyền truy cập, phải thêm dữ liệu/logic tương ứng; query trên chỉ là bước đầu.

---

## 24. Domain events, outbox và callback không thay thế transaction messaging

Nếu entity có `@PostUpdate` hoặc listener để tạo event, bulk update không gọi listener cho từng hàng bị sửa. Vì vậy một job bulk:

```java
UPDATE PurchaseOrder o SET o.status = :expired WHERE ...
```

sẽ **không tự phát ra 15.000 domain events** chỉ vì managed entity path thường có listener.

### 24.1. Rủi ro khi chỉ audit ở callback

Giả sử hệ thống có:

```text
@PreUpdate -> cập nhật updatedAt
@PostUpdate -> ghi log sự kiện
@PreRemove -> kiểm tra một số quy tắc
```

Một bulk query có thể:

- Đổi status mà không cập nhật updatedAt.
- Không ghi các event dựa trên callbacks.
- Bỏ qua kiểm tra tại callback.
- Để reporting/cache khác không nhận biết thay đổi.

Nếu audit là yêu cầu không thể thiếu, hệ thống cần kiểm soát **tất cả các write paths**, không chỉ JPA managed entity updates.

### 24.2. Transactional outbox có thể phù hợp

Một cách thiết kế:

```text
Transaction DB:
  1. Xác định tập order cần thay đổi.
  2. UPDATE các orders.
  3. INSERT các outbox messages phù hợp.
  4. COMMIT cả dữ liệu và outbox.

Worker khác:
  5. Đọc outbox.
  6. Phát messages idempotently.
  7. Đánh dấu đã phát.
```

Tuy nhiên, với bulk query thay đổi hàng nghìn rows, việc tạo **một event per row** không tự xuất hiện từ `executeUpdate()`. Cần chọn một chiến lược nhận diện ID và snapshot phù hợp, chẳng hạn:

- Chọn danh sách target IDs và giữ scope nhất quán bằng transaction/locking.
- Sử dụng bảng tạm/batch ID phù hợp DB.
- Dùng `UPDATE ... RETURNING` hoặc CTE database-specific nếu DB hỗ trợ.
- Phát một **batch-level event** nếu consumer thực sự chỉ cần thông báo “batch hoàn tất” và có thể tự truy vấn theo version/snapshot.

Không tạo outbox sau commit rồi coi chắc chắn sẽ được ghi; nếu outbox bắt buộc phải đi cùng DB mutation, lưu chúng trong **cùng transaction** hoặc dùng cơ chế đáng tin cậy tương đương.

### 24.3. Side effects ngoài DB không bị rollback tự động

Gọi email/HTTP trước khi commit:

```java
externalClient.notifyExpiredOrders(...);
tx.commit();
```

có thể gửi thông báo dù commit thất bại. Bulk DML không giải quyết vấn đề này; use case cần outbox/idempotency/compensation tùy tính chất hệ thống.

---

## 25. Xử lý transaction đúng khi thực hiện bulk DML

Bulk UPDATE/DELETE phải được thực hiện trong **transaction phù hợp**.

### 25.1. Resource-local example

```java
public int expireOrders(
        EntityManagerFactory emf,
        LocalDateTime now
) {
    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        int affected = em.createQuery(
            """
            UPDATE PurchaseOrder o
            SET o.status = :expired,
                o.updatedAt = :now,
                o.version = o.version + 1
            WHERE o.status = :draft
              AND o.expiresAt < :now
            """
        )
        .setParameter("expired", OrderStatus.EXPIRED)
        .setParameter("draft", OrderStatus.DRAFT)
        .setParameter("now", now)
        .executeUpdate();

        tx.commit();
        return affected;
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            try {
                tx.rollback();
            } catch (RuntimeException rollbackFailure) {
                ex.addSuppressed(rollbackFailure);
            }
        }
        throw ex;
    } finally {
        em.close();
    }
}
```

Ưu điểm của ví dụ: mỗi job tạo một EntityManager mới, không có managed graph cũ trước bulk. Sau khi commit, EntityManager được đóng; không để lại stale managed entities cho use case sau.

### 25.2. JTA/Spring

Trong môi trường JTA hoặc Spring-managed transaction, không gọi `em.getTransaction().begin()` trên JTA EntityManager; dùng transaction boundary do container/framework quản lý.

Ví dụ Spring:

```java
@Service
public class OrderExpirationService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public int expire(LocalDateTime now) {
        return em.createQuery(
            """
            UPDATE PurchaseOrder o
            SET o.status = :expired,
                o.updatedAt = :now,
                o.version = o.version + 1
            WHERE o.status = :draft
              AND o.expiresAt < :now
            """
        )
        .setParameter("expired", OrderStatus.EXPIRED)
        .setParameter("draft", OrderStatus.DRAFT)
        .setParameter("now", now)
        .executeUpdate();
    }
}
```

Ví dụ giả định imports Spring `@Service`, `@Transactional` và JPA `@PersistenceContext`/`EntityManager`. Transactional advice phải thực sự được áp dụng khi method được gọi; không coi self-invocation qua `this` trong proxy mode thông dụng là một transaction boundary mới.

**Cần phân biệt** method return và commit ở interceptor: commit có thể thất bại **sau khi body của method đã return**. Caller không nên tuyên bố tác vụ chắc chắn thành công chỉ dựa vào số count trước khi transaction hoàn tất.

---

## 26. Bulk UPDATE cùng managed entity đã dirty: thứ tự thực hiện rất quan trọng

Giả sử:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, 42L);
order.cancel(); // Pending managed change.

em.createQuery(
    """
    UPDATE PurchaseOrder o
    SET o.status = :expired
    WHERE o.id = :id
    """
)
.setParameter("expired", OrderStatus.EXPIRED)
.setParameter("id", 42L)
.executeUpdate();

tx.commit();
```

Bạn có **hai nguồn thay đổi** trên cùng row:

1. `order.cancel()` thay đổi managed state (có thể chỉ ghi ở flush).
2. Bulk UPDATE đổi DB state trực tiếp.

Tùy flush timing, provider may flush managed change trước query; sau query entity có thể vẫn mang state do code trước đó đặt. Những bước tiếp theo hoặc flush cuối có thể tạo kết quả bất ngờ nếu code lại sửa entity.

### 26.1. Không để query ordering quyết định business rule tình cờ

Nếu nghiệp vụ muốn “hủy đơn”, hãy chọn **một đường ghi chính** thay vì vừa gọi `cancel()` vừa bulk đặt EXPIRED cho cùng ID trong cùng unit of work.

Nếu muốn sau một workflow managed có một batch update **khác tập entity**, có thể:

```java
em.flush();
int affected = em.createQuery(...).executeUpdate();
em.clear();
```

và tránh giữ những managed object cũ cho các phép sửa tiếp theo.

### 26.2. Nếu bắt buộc đồng bộ một entity riêng

Sau bulk có thể:

```java
em.refresh(order);
```

nhưng điều này **bỏ state local chưa lưu** của entity được refresh, và có thể kích hoạt refresh cascade. Phải có chủ đích về việc mất state và transaction isolation.

### 26.3. Vì sao không “để flush tự xử lý”?

`FlushModeType.AUTO` và provider có những bảo đảm về query visibility, nhưng không thay thế sự phân biệt:

- Những field đã sửa trong managed object.
- Những field bulk query đã sửa trong database.
- Version có được bump đúng không.
- Object nào còn managed, object nào cần reload.

Rõ ràng về transaction boundaries và không trộn write paths thường dễ bảo trì hơn phụ thuộc tình cờ vào thứ tự flush.

---

## 27. Bulk DELETE và second-level cache

JPA **first-level cache** là persistence context gắn với EntityManager. Nó giữ managed entity instances theo identity.

**Second-level cache** có thể do provider và cấu hình triển khai, thường chia sẻ giữa EntityManagers.

### 27.1. Xóa database row nhưng object vẫn còn trong context

```java
PurchaseOrder order = em.find(PurchaseOrder.class, 42L);

em.createQuery(
    "DELETE FROM PurchaseOrder o WHERE o.id = :id"
)
.setParameter("id", 42L)
.executeUpdate();

// Biến order vẫn trỏ tới Java object cũ.
```

Không được coi `em.contains(order)` hoặc giá trị field cũ như bằng chứng row vẫn tồn tại. JPA không tự đưa object đó vào trạng thái REMOVED theo lifecycle `em.remove` chỉ vì bulk DELETE.

### 27.2. Chính sách cache invalidation

Một số providers có thể tự xử lý/invalidate những vùng cache nhất định cho các bulk queries mà chúng nhận diện. Mức độ và thời điểm không nên được suy diễn như bảo đảm chung cho:

- Native SQL UPDATE/DELETE.
- Cross-application writes.
- Custom application caches.
- Distributed caches.
- DTO/materialized report caches.

Nếu yêu cầu correctness phụ thuộc cache, phải có chiến lược invalidation rõ ràng và integration tests.

API JPA cấp factory:

```java
em.getEntityManagerFactory()
  .getCache()
  .evict(PurchaseOrder.class);
```

có thể evict cache entries cho entity type nếu cache có dùng. Đây là một công cụ, không phải cách thay thế việc quản lý context và không tự xử lý mọi cache ngoài JPA.

### 27.3. Không gọi `clear` rồi nghĩ mọi bộ nhớ hệ thống đều sạch

`em.clear()` chỉ detach managed entities của persistence context hiện tại. Nó không làm mất mọi DTO đã đưa cho caller, mọi object trong HTTP session hoặc mọi distributed cache.

---

## 28. Hiệu năng: vì sao bulk DML hấp dẫn, và cái giá phải trả

### 28.1. Managed loop

```java
for (PurchaseOrder o : orders) {
    o.expire();
}
```

Chi phí có thể gồm:

- SELECT load mỗi entity và association cần thiết.
- Memory của persistence context.
- Dirty checking.
- Callback invocation.
- Optimistic version checks.
- Multiple UPDATEs, dù JDBC batching có thể giảm round trips.

Đổi lại, giữ semantics object lifecycle.

### 28.2. Bulk DML

```java
UPDATE PurchaseOrder o
SET o.status = :expired
WHERE ...
```

Ưu điểm thường gặp:

- Thao tác tập hợp ngay tại database.
- Ít cần tải entity.
- Ít Java heap memory.
- Có thể tận dụng index và SQL optimizer.
- Phù hợp dữ liệu lớn khi không cần per-entity lifecycle behavior.

Đánh đổi:

- Không callbacks.
- Không cascades/orphan removal JPA.
- Không automatic `@Version`.
- Stale persistence context/cache.
- Khó tạo per-row domain events.
- Cần quản lý concurrency/isolation và SQL constraint trực tiếp.

### 28.3. Không mặc định bulk luôn nhanh hơn trong mọi case

Một UPDATE rất rộng có thể:

- Giữ locks trên nhiều rows.
- Gây deadlocks hoặc timeout.
- Tăng transaction log/WAL.
- Tạo áp lực replication.
- Kích hoạt database triggers nặng.
- Cạnh tranh với request online.
- Làm index updates/fragmentation.

Nếu cần xử lý hàng triệu rows, phải lên kế hoạch batch size, transaction length, lock strategy, index và rollback/retry. Chia nhiều transaction có thể phá tính atomic của use case; chỉ thực hiện khi nghiệp vụ cho phép xử lý từng phần.

---

## 29. Phạm vi đa tenant: rủi ro đặc biệt của bulk UPDATE/DELETE

Giả sử bảng có `tenant_id` và entity có `tenantId`.

Một bulk query:

```java
em.createQuery(
    """
    DELETE FROM PurchaseOrder o
    WHERE o.status = :expired
    """
).executeUpdate();
```

có thể tác động nhiều tenant nếu framework/security filters không được áp dụng theo cách người viết tưởng.

Nên xác định **bộ lọc tenant như một phần của query contract**:

```java
int affected = em.createQuery(
    """
    UPDATE PurchaseOrder o
    SET o.status = :expired
    WHERE o.tenantId = :tenantId
      AND o.status = :draft
    """
)
.setParameter("tenantId", tenantId)
.setParameter("draft", OrderStatus.DRAFT)
.setParameter("expired", OrderStatus.EXPIRED)
.executeUpdate();
```

`tenantId` là thuộc tính giả định trong một mô hình multi-tenant mở rộng, không có trong `PurchaseOrder` demo phần 5.

Tùy phương pháp multi-tenancy và provider, có thể có automatic tenant filters hoặc database row-level security, nhưng **không nên dựa vào giả định** rằng mọi extension/filter trên entity select chắc chắn tự bảo vệ native/bulk DML. Kiểm tra SQL thực tế và quyền truy cập database.

### 29.1. An toàn dữ liệu bắt đầu từ phạm vi ảnh hưởng

Với một destructive query, nên biết trước:

- Tenant scope.
- Status/age predicate.
- Max expected affected count.
- Dependent FK graph.
- Audit/retention requirements.
- Ai cho phép chạy job.
- Cách rollback/khôi phục nếu điều kiện sai.

Callback, cascade và version chỉ là một phần của đánh giá tổng thể.

---

## 30. Một chiến lược hai giai đoạn để có both bulk efficiency và audit

Có những bài toán muốn:

1. Nhanh hơn so với load hàng chục nghìn entities.
2. Vẫn ghi nhận các ID đã thay đổi.

Một hướng:

```text
Transaction:
  - Xác định tập IDs với điều kiện chính xác.
  - Ghi nhận batch marker / audit scope.
  - UPDATE các IDs với preconditions tương ứng.
  - Ghi outbox/audit rows cho những IDs thực sự affected.
  - COMMIT.
```

Nhưng cần cân nhắc concurrency.

### 30.1. Vì sao SELECT IDs rồi UPDATE không luôn bảo đảm cùng một tập?

Giữa:

```sql
SELECT id FROM purchase_orders WHERE status = 'DRAFT';
```

và:

```sql
UPDATE purchase_orders
SET status = 'EXPIRED'
WHERE status = 'DRAFT';
```

một transaction khác có thể đổi status của một order. Danh sách ID lấy trước có thể không khớp tập thực sự được update.

Để có audit per-row đáng tin cậy, phải thiết kế transaction isolation/locking hoặc dùng cơ chế DB hỗ trợ nhận lại ID affected (`RETURNING`, table-valued output, staging table...) một cách tương thích.

### 30.2. Chỉ kiểm tra count không đủ cho per-row audit

`executeUpdate() == 500` không cho biết **500 order IDs nào** đã đổi. Nó chỉ cho một số lượng affected theo query. Nếu hệ thống cần event chứa old/new state từng row, cần cơ chế thu thập ID và snapshot có chủ đích.

### 30.3. Đánh giá database triggers như một lựa chọn

Database trigger có thể ghi audit row cho mỗi SQL UPDATE, kể cả bulk. Lợi ích: bao phủ cả write paths ngoài JPA. Đánh đổi: logic nằm ở DB, deployment/migration khó hơn, transaction log overhead, và semantics có thể khác entity/domain events.

Không nhất thiết phải chọn trigger; nhưng nếu yêu cầu audit **mọi thay đổi DB dù nguồn nào**, chỉ dựa vào JPA callbacks là không đủ.

---

## 31. Khi nào nên dùng `em.remove` thay vì bulk DELETE?

Đặt hai lựa chọn cạnh nhau.

| Câu hỏi | Ưu tiên managed remove khi | Bulk DELETE có thể phù hợp khi |
|---|---|---|
| Cần `@PreRemove`/`@PostRemove`? | Có. | Không; hoặc đã có cơ chế audit/validation khác. |
| Cần `CascadeType.REMOVE`? | Có. | Tự xử lý child/DB FK phù hợp. |
| Cần `orphanRemoval`? | Có, child phụ thuộc lifecycle. | Không dựa vào orphanRemoval cho job. |
| Cần optimistic version check từng entity? | Có, lifecycle JPA hỗ trợ. | Tự đưa version vào WHERE hoặc dùng locking khác. |
| Tập dữ liệu | Nhỏ/vừa, hoặc yêu cầu logic per-row. | Lớn, thao tác đơn giản theo predicate. |
| Per-row domain events | Có. | Có thiết kế outbox/trigger thu thập rows. |
| SQL/database constraints | Đều phải tuân thủ. | Đều phải tuân thủ. |
| Managed context hiện tại | Đã có nhiều entities cần xử lý. | Tốt nhất trong context mới hoặc trước khi load affected entities. |

### 31.1. Dữ liệu tài chính thường không được xóa cứng

Đối với thanh toán, hóa đơn, sổ kế toán, danh sách transactions hoặc records cần đối soát, `DELETE` có thể không phù hợp bất kể dùng managed hay bulk. Thay bằng:

- Chuyển trạng thái nghiệp vụ.
- Soft delete theo policy.
- Archive cùng retention period.
- Quy trình hoàn tiền/đảo bút toán thay vì xóa lịch sử.

Cascade không phải công cụ quyết định quyền xóa dữ liệu.

---

## 32. Khi nào nên dùng managed update thay vì bulk UPDATE?

Đặc biệt phù hợp khi:

- Entity có state machine phức tạp: `DRAFT → PAID → REFUNDED`.
- Domain method phát event hoặc thực hiện invariant.
- Callback cập nhật metadata quan trọng.
- Có nhiều entity thuộc aggregate cần cập nhật nhất quán.
- Optimistic locking cần kiểm tra theo expected version mỗi command.
- Cần biết rõ **thất bại của từng entity**.
- Đơn hàng/dữ liệu có external actions liên quan.
- Tập dữ liệu đủ nhỏ để xử lý per-entity với batching hợp lý.

Ví dụ:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, id);

order.expire(); // Guard DRAFT.

em.flush();     // Dirty checking, callbacks, @Version.
```

Nếu yêu cầu chỉ là “đổi tất cả DRAFT quá hạn sang EXPIRED” với invariant đơn giản, bulk có thể hợp lý hơn, miễn là mã hóa trạng thái, version, audit và consistency theo thiết kế.

---

## 33. Kiểm thử callback: managed khác bulk như thế nào?

Không nên chỉ test câu bulk update chạy đúng `executeUpdate()`. Cần test **những điều không xảy ra**, vì chúng dễ bị developer hiểu lầm.

### 33.1. Callback test listener khái niệm

Có thể cấu hình một listener chỉ dùng trong test:

```java
public class OrderLifecycleProbe {

    public static final AtomicInteger updates =
            new AtomicInteger();

    public static final AtomicInteger removes =
            new AtomicInteger();

    @PreUpdate
    public void beforeUpdate(PurchaseOrder order) {
        updates.incrementAndGet();
    }

    @PreRemove
    public void beforeRemove(PurchaseOrder order) {
        removes.incrementAndGet();
    }
}
```

Entity khai báo:

```java
@EntityListeners(OrderLifecycleProbe.class)
@Entity
public class PurchaseOrder {
    // ...
}
```

**Đây chỉ là ví dụ test fixture:** biến static mutable không thích hợp cho production audit, không có bảo đảm isolation nếu tests chạy song song, và việc JPA callback xảy ra trước transaction commit không tương đương một event đã bền vững.

### 33.2. Managed update test

Pseudocode:

```java
OrderLifecycleProbe.updates.set(0);

EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    PurchaseOrder order =
            em.find(PurchaseOrder.class, knownDraftOrderId);

    order.expire();
    em.flush();

    assertEquals(1, OrderLifecycleProbe.updates.get());

    tx.rollback(); // Giữ fixture DB như cũ.
} finally {
    if (tx.isActive()) tx.rollback();
    em.close();
}
```

Trong một fixture cô lập, callback `@PreUpdate` được mong đợi khi entity dirty và flush thực hiện update.

### 33.3. Bulk update test

```java
OrderLifecycleProbe.updates.set(0);

EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    int affected = em.createQuery(
        """
        UPDATE PurchaseOrder o
        SET o.status = :expired
        WHERE o.id = :id
          AND o.status = :draft
        """
    )
    .setParameter("expired", OrderStatus.EXPIRED)
    .setParameter("draft", OrderStatus.DRAFT)
    .setParameter("id", knownDraftOrderId)
    .executeUpdate();

    assertEquals(1, affected);
    assertEquals(0, OrderLifecycleProbe.updates.get());

    tx.rollback();
} finally {
    if (tx.isActive()) tx.rollback();
    em.close();
}
```

Test giả định transaction không có managed dirty entities khác gây callback. Không nên viết test trên shared database với các threads/tasks đồng thời rồi kết luận callback của bulk query đã chạy chỉ vì counter static thay đổi.

**Điểm cần chứng minh:** bulk update tự nó không gọi JPA callback cho row bị sửa.

---

## 34. Integration test: bulk query không tự tăng `@Version`

Một test với numeric version:

```java
@Test
void bulkUpdateDoesNotAutomaticallyIncrementVersion() {
    Long id = knownDraftOrderId;

    EntityManager initial = emf.createEntityManager();
    Long before;
    try {
        PurchaseOrder order =
                initial.find(PurchaseOrder.class, id);
        before = order.getVersion();
    } finally {
        initial.close();
    }

    EntityManager work = emf.createEntityManager();
    EntityTransaction tx = work.getTransaction();

    try {
        tx.begin();

        int count = work.createQuery(
            """
            UPDATE PurchaseOrder o
            SET o.status = :expired
            WHERE o.id = :id
            """
        )
        .setParameter("expired", OrderStatus.EXPIRED)
        .setParameter("id", id)
        .executeUpdate();

        assertEquals(1, count);
        tx.commit();
    } finally {
        if (tx.isActive()) tx.rollback();
        work.close();
    }

    EntityManager verify = emf.createEntityManager();
    try {
        PurchaseOrder reloaded =
                verify.find(PurchaseOrder.class, id);

        assertEquals(OrderStatus.EXPIRED, reloaded.getStatus());
        assertEquals(before, reloaded.getVersion());
    } finally {
        verify.close();
    }
}
```

Điều kiện để kết luận rõ:

- Test dùng fixture độc lập, không có transaction khác cập nhật cùng row.
- Query **không SET version**.
- Đọc lại với context mới sau commit.
- Không có database trigger hoặc custom provider behavior tự thay version ngoài đặc tả.
- Nếu second-level cache bật, cần xác nhận cơ chế invalidation của provider hoặc đọc trực tiếp database trong test kiểm tra để tránh cache stale.

Đây là **integration test minh họa**, không phải lời khuyên tắt `@Version`. Nó chứng minh nguyên nhân bulk operations có thể phá optimistic locking discipline nếu không thêm logic version.

### 34.1. Test có bump version thủ công

```java
@Test
void bulkUpdateWithExpectedVersionRejectsStaleVersion() {
    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        int count = em.createQuery(
            """
            UPDATE PurchaseOrder o
            SET o.status = :expired,
                o.version = o.version + 1
            WHERE o.id = :id
              AND o.version = :expected
              AND o.status = :draft
            """
        )
        .setParameter("expired", OrderStatus.EXPIRED)
        .setParameter("draft", OrderStatus.DRAFT)
        .setParameter("id", knownDraftOrderId)
        .setParameter("expected", staleVersion)
        .executeUpdate();

        assertEquals(0, count);
        tx.rollback();
    } finally {
        if (tx.isActive()) tx.rollback();
        em.close();
    }
}
```

`staleVersion` là fixture được tạo cho test (một version chắc chắn đã cũ), không phải biến JPA cung cấp. Trong test khác, dùng expected version hiện tại và xác nhận `count == 1` và version tăng đúng một bước.

### 34.2. Test conflict thật với hai EntityManagers

Một test mạnh hơn:

1. T1 load entity ở version 5.
2. T2 dùng bulk UPDATE **có bump version**, commit thành version 6.
3. T1 sửa managed entity và cố flush/commit với version 5.
4. Mong đợi optimistic locking conflict theo provider/transaction semantics.
5. Rollback T1, đóng context, đọc lại database.

Nếu T2 không bump version, test có thể thấy T1 update thành công ngoài ý muốn; đó là lý do cần version discipline khi trộn bulk với managed writes.

---

## 35. Integration test: bulk DELETE không thực hiện cascade/remove callback

Với FK trong schema phần 5:

```java
@Test
void bulkDeleteParentWithLinesHitsForeignKey() {
    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        int deleted = em.createQuery(
            """
            DELETE FROM PurchaseOrder o
            WHERE o.id = :id
            """
        )
        .setParameter("id", orderIdWithLines)
        .executeUpdate();

        // Tùy DB, constraint có thể được kiểm tra khi
        // executeUpdate hoặc commit.
        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) tx.rollback();

        // Trong fixture này, FK không có ON DELETE CASCADE
        // nên lỗi constraint là kết quả mong đợi.
        // Test framework nên assert exception tại đúng boundary.
        throw ex;
    } finally {
        if (tx.isActive()) tx.rollback();
        em.close();
    }
}
```

Đoạn trên minh họa luồng gặp lỗi FK, **chưa phải assertion test hoàn chỉnh**. Một integration test thật nên:

- Tạo order có ít nhất một line tham chiếu.
- Cố bulk delete parent.
- Assert lỗi tại `executeUpdate()` hoặc `commit()` theo DB constraint timing.
- Rollback/cleanup.
- Xác nhận rows vẫn tồn tại.
- So sánh với `em.remove(order)` trên fixture tương đương, nơi REMOVE cascade có thể xử lý lines hợp lệ.

Không khẳng định mọi RDBMS ném lỗi ở cùng một dòng code; một số constraints có thể được kiểm tra muộn.

### 35.1. Khi database có `ON DELETE CASCADE`

Test khác có thể xác nhận bulk DELETE parent xóa child **ở database** nhưng **không gọi JPA child `@PreRemove`**. Phải cô lập cache/context và listener probe để không nhầm DB cascade với JPA cascade.

---

## 36. Những lỗi thường gặp khi dùng bulk UPDATE/DELETE

| Triệu chứng / anti-pattern | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Cập nhật `status` bằng JPQL nhưng `@PreUpdate` không chạy | Bulk update bypass per-entity callbacks. | Set audit fields trong DML hoặc dùng managed update. |
| Xóa bằng `DELETE FROM Entity` nhưng `@PreRemove` không chạy | Bulk delete không gọi `em.remove` từng entity. | Dùng managed remove nếu cần lifecycle hoặc thiết kế audit khác. |
| Có `cascade=ALL` nhưng bulk DELETE parent bị FK error | JPA REMOVE cascade không chạy trên bulk DELETE. | Xóa child có chủ đích, dùng managed remove hoặc DB cascade theo policy. |
| Có `orphanRemoval=true` nhưng bulk UPDATE FK không xóa orphan | Orphan removal gắn với entity relationship lifecycle. | Thiết kế explicit cleanup/bulk delete nếu thực sự cần. |
| Row đã update nhưng `@Version` vẫn như cũ | Bulk UPDATE không tự bump version. | Thêm logic version hoặc chọn managed path. |
| Managed transaction sau bulk ghi đè dữ liệu | Version không được bump, object stale. | Manual version bump + WHERE version và context management. |
| `executeUpdate()==1` nhưng callback không chạy | Row count không liên quan số callbacks. | Không coi row count là per-entity lifecycle. |
| `executeUpdate()==0` và code kết luận chắc chắn conflict | WHERE còn điều kiện status/tenant/time. | Phân biệt không tồn tại, sai trạng thái và stale version theo contract. |
| Đặt `version = version + 1` cho timestamp version | Kiểu version không phải numeric. | Chọn policy phù hợp kiểu version/provider. |
| Bulk query đổi DB nhưng `em.find` vẫn trả giá trị cũ | Persistence context identity map giữ managed instance. | Context mới, clear hoặc refresh có chủ đích. |
| `em.clear` làm mất sửa đổi chưa lưu | Clear detach pending state không tự flush. | Flush trước hoặc tách transaction/context. |
| Gọi refresh sau bulk DELETE lỗi | Row đã bị xóa. | Đừng refresh entity đã mất; clear/new context. |
| Spring `@Modifying` được hiểu là lifecycle-safe | Nó vẫn là bulk query. | Đánh giá callback/cascade/version như JPQL DML. |
| `@Modifying(clearAutomatically=true)` làm object đang dùng detached | Clear toàn persistence context. | Điều chỉnh transaction boundary, không giữ object managed cũ. |
| Native SQL UPDATE không làm entity listener chạy | Truy cập DB trực tiếp không đi qua JPA lifecycle. | Sử dụng callback-independent audit hoặc managed operations. |
| Database trigger chạy nhưng JPA callback không | Hai cơ chế ở hai tầng khác nhau. | Thiết kế kỳ vọng audit chính xác theo tầng. |
| Bulk job không phát domain events | Các event dựa trên domain methods/listeners không được sinh. | Outbox/trigger/event logic riêng cho batch. |
| Bulk query sửa tất cả rows nhiều tenant | Predicate scope thiếu tenant. | Đưa tenant predicate/DB security vào contract, test SQL thật. |
| `@Version` ở root không đổi khi bulk child update | Child DML không tự bump root. | Chọn aggregate concurrency policy tường minh. |
| Dùng JPQL `JOIN` trong bulk UPDATE như SELECT | Bulk DML grammar có giới hạn. | Dùng WHERE subquery hoặc native SQL có chủ đích. |
| Dùng JPQL entity name trong native SQL | Nhầm JPQL và SQL. | Native dùng tên bảng/cột thật. |
| Bulk DELETE theo status PAID xóa lịch sử | Thiếu business/retention guard. | Soft delete/archive/domain policy. |
| Tưởng `executeUpdate` là commit | DML chạy trong transaction, commit vẫn có thể lỗi. | Xử lý transaction boundary và outcome. |
| Chỉ dùng `@PreRemove` để ngăn xóa dữ liệu pháp lý | Bulk/native DML bỏ qua callback. | Thêm DB constraints/quyền/retention process. |
| Bulk query đổi DB nhưng Redis/DTO cache còn cũ | Clear first-level không xử lý application cache. | Invalidation/versioned cache strategy. |
| Đếm ảnh hưởng DB cascade không khớp `executeUpdate` | Row count thường đo trực tiếp target, không mọi child. | Dùng DB audit/metrics nếu cần total effects. |
| Job bulk cập nhật triệu rows làm timeout | Transaction/locks/log quá lớn. | Batch design và kế hoạch vận hành theo invariant. |
| Query chạy trên H2 nhưng production khác | Native SQL/dialect/constraint timing khác. | Integration test trên database gần production. |

---

## 37. Quy trình review một câu truy vấn thay đổi

Trước khi chấp nhận một `UPDATE`/`DELETE` qua `executeUpdate()`, hãy hỏi theo thứ tự.

### Bước 1 — Đây có thật sự là bulk operation không?

- `em.find` rồi thay managed entity?
- `em.remove`?
- `createQuery("UPDATE ...")`?
- `CriteriaUpdate`/`CriteriaDelete`?
- Native SQL/JDBC?

Đường thực thi quyết định callback/cascade/version semantics.

### Bước 2 — Những callback nào bị bỏ qua?

- `@PreUpdate`/`@PostUpdate`?
- `@PreRemove`/`@PostRemove`?
- Entity listener cung cấp audit timestamps?
- Domain methods có validation/trạng thái?

Đừng chỉ kiểm tra annotations hiện có; xem **điều kiện nghiệp vụ thực sự phụ thuộc** vào chúng.

### Bước 3 — Có cascade hoặc orphan removal cần thiết không?

- Parent có children không?
- FK có `ON DELETE CASCADE` không?
- Có dependent entity cần retention không?
- DB triggers có tham gia không?
- Có cần gọi `em.remove` từng entity để giữ lifecycle không?

### Bước 4 — `@Version` được xử lý thế nào?

- Bulk query có thể sửa rows đang được managed transactions khác sử dụng không?
- Có bump numeric version không?
- Có cần expectedVersion predicate không?
- Bản cập nhật của child có cần bump root version không?
- Cơ chế version có thống nhất giữa bulk và managed paths không?

### Bước 5 — Persistence context/cache ra sao?

- Có loaded entities bị affected trong context hiện tại không?
- Có pending changes cần flush trước không?
- Sau bulk nên `clear`, `refresh` hay đóng EntityManager?
- Có 2nd-level/application cache khác cần invalidation không?

### Bước 6 — Transaction và concurrency

- Query nằm trong transaction hợp lệ chưa?
- Có đúng tenant và status predicate không?
- Có yêu cầu snapshot/lock giữa nhiều statements không?
- Count = 0/partial affected được diễn giải thế nào?
- Nếu commit thất bại, rollback/cleanup ra sao?

### Bước 7 — Audit và vận hành

- Có cần event từng row không?
- Có outbox/triggers/backup không?
- Dữ liệu có được phép hard-delete không?
- Batch size, index, lock duration có phù hợp không?
- Integration tests đã bao phủ cả managed và bulk paths chưa?

Đây không phải checklist QA của repository hiện tại mà là **quy trình thiết kế kỹ thuật của bài học**, giúp tránh một câu bulk DML chạy được nhưng vi phạm semantics domain.

---

## 38. Tình huống thực tế để luyện đánh giá

### Tình huống A — Tự động hết hạn đơn DRAFT

Yêu cầu: mọi đơn `DRAFT` quá hạn chuyển `EXPIRED`; không cần callback per-row, nhưng phải tăng version và cập nhật timestamp.

**Lựa chọn có thể phù hợp:** JPQL bulk UPDATE có:

```sql
SET o.status = :expired,
    o.updatedAt = :now,
    o.version = o.version + 1
WHERE o.status = :draft
  AND o.expiresAt < :now
```

**Còn cần:** audit/outbox nếu consumer muốn biết từng đơn đã hết hạn; test concurrency và time boundary.

### Tình huống B — Xóa order và lines, cần `@PreRemove` trên từng line

**Không nên dùng:** bulk DELETE parent với kỳ vọng `cascade=ALL` tự xử lý.

**Lựa chọn phù hợp hơn:** load order và `em.remove(order)` trong transaction, bảo đảm mapping cascade/ownership và callback semantics đúng.

Nếu tập lớn và callback bắt buộc, cần tìm phương án batching managed deletes hoặc thay kiến trúc audit — không thể chỉ thay bằng bulk mà đòi mọi callback vẫn chạy.

### Tình huống C — Sửa giá một sản phẩm đang được nhiều request cập nhật

Nếu dùng bulk UPDATE nhưng không cập nhật version, các managed requests có thể ghi đè thay đổi. Với một product xác định, dùng expectedVersion trong `WHERE` và bump version, hoặc dùng managed entity update.

**Không đủ:** chỉ kiểm tra version trước bằng SELECT rồi bulk UPDATE không điều kiện.

### Tình huống D — Xóa hàng loạt inactive users nhưng có audit history

Hard-delete có thể phá retention. Phải quyết định soft-delete/ẩn danh hóa/archive. `@PreRemove` không phải “hàng rào cuối cùng” nếu các tool/migration/bulk jobs vẫn có đường xóa DB trực tiếp.

### Tình huống E — CriteriaUpdate để đổi status

Dù được tạo bằng Criteria API, thao tác vẫn là bulk DML, **không khác JPQL UPDATE** về callback/cascade/version. Type safety của Criteria chỉ giúp xây query, không tự gọi Java domain logic.

### Tình huống F — Bulk DELETE trong database có `ON DELETE CASCADE`

Child rows có thể bị database xóa. Nhưng `OrderLine.@PreRemove` không chạy và managed OrderLine đang trong context có thể stale. Nếu audit dựa trên JPA listener, **không coi DB cascade là thay thế tương đương**.

### Tình huống G — Spring Data `@Modifying(clearAutomatically=true)`

Sau update, các entity trước đó có thể detached; code sau repository call không thể mặc định tiếp tục dirty checking. Dùng command boundary riêng hoặc load lại trong context phù hợp.

### Tình huống H — Job update tất cả tenants do quên filter

Callback/version có được xử lý hay không đều không cứu được phạm vi UPDATE sai. Bulk DML cần predicates scope, quyền thực thi, safe rollout, row count và audit.

### Tình huống I — Báo cáo muốn “đơn nào đã đổi” sau `executeUpdate()`

Row count chỉ có số lượng. Muốn danh sách ID, cần cơ chế truy xuất target set với consistency/locking hoặc SQL returning/output dialect-specific; không thể tự suy ra từ một con số.

### Tình huống J — Đã tăng version của order nhưng child được bulk cập nhật

Nếu business invariant bao phủ cả order và lines, bump version root khi cần cũng là một quyết định riêng. Chỉ cập nhật `OrderLine.quantity` không tự làm `PurchaseOrder.version` tăng theo mọi provider.

---

## 39. Câu hỏi tự kiểm tra

**1. JPQL `UPDATE` có gọi `@PreUpdate` của từng entity bị sửa không?**

Không. Nó là bulk operation, không đi qua entity-by-entity lifecycle update.

**2. `CriteriaUpdate` có khác JPQL bulk update về callback không?**

Không. Nó cũng là bulk DML, bypass per-entity callbacks.

**3. `DELETE FROM PurchaseOrder` có áp dụng `CascadeType.REMOVE` xuống `OrderLine` không?**

Không. Cascade REMOVE là cơ chế của entity remove operations, không phải bulk delete query.

**4. Có `orphanRemoval = true` thì bulk UPDATE `order_id = NULL` có tự xóa child không?**

Không. Bulk SQL/JPQL không kích hoạt orphan removal như thao tác thay đổi managed association.

**5. Database `ON DELETE CASCADE` có bị bỏ qua khi bulk DELETE không?**

Không. Đó là ràng buộc database; SQL DELETE có thể kích hoạt DB cascade. Nó **không kích hoạt JPA callbacks**.

**6. Bulk UPDATE có tự tăng `@Version` không?**

Không theo cơ chế optimistic locking tự động của managed entities. Cần tự đưa version logic vào bulk query nếu cần.

**7. Cách phổ biến để bảo vệ một bulk UPDATE bằng numeric version là gì?**

`WHERE id = :id AND version = :expected` cùng `SET version = version + 1`; kiểm tra affected count.

**8. `executeUpdate() == 0` có luôn nghĩa optimistic lock conflict không?**

Không. Row có thể không tồn tại hoặc không thỏa trạng thái/tenant/time predicate.

**9. Sau bulk UPDATE, managed entity đã tải có tự thay đổi field không?**

Không được bảo đảm. Có thể stale; cần context mới/clear/refresh phù hợp.

**10. Vì sao cần `flush()` trước `clear()`?**

Vì `clear()` detach các managed entities, làm những pending changes chưa flush có thể không được ghi.

**11. `em.find` lại cùng ID sau bulk query có chắc SELECT database mới không?**

Không. Nếu entity đã có trong persistence context, JPA có thể trả managed instance cũ.

**12. `@PreUpdate` vẫn có thể chạy trong transaction chứa bulk UPDATE không?**

Có, nếu còn managed entity changes được flush riêng. Nhưng callback đó **không phải do bulk UPDATE gọi cho mọi row**.

**13. Bulk DELETE có luôn nhanh hơn managed remove không?**

Không có bảo đảm. Nó thường giảm object work nhưng có thể gây lock/transaction log/FK/trigger overhead lớn.

**14. Có nên dùng bulk DELETE cho hóa đơn đã thanh toán không?**

Phải xét retention, audit và quyền xóa. Nhiều hệ thống cần giữ history hoặc soft-delete/đảo giao dịch.

**15. `@Version` trên PurchaseOrder có tự tăng khi bulk UPDATE OrderLine không?**

Không. Cần aggregate concurrency policy riêng.

**16. Spring Data `@Modifying` có làm entity lifecycle callbacks chạy không?**

Không nếu method là JPQL/native bulk modifying query.

**17. `@Modifying(flushAutomatically=true,clearAutomatically=true)` giải quyết điều gì?**

Giúp flush pending changes trước và clear persistence context sau modifying query, nhưng không cung cấp callback/cascade/optimistic lock tự động.

**18. Vì sao audit dựa riêng vào `@PostUpdate` có thể thiếu dữ liệu?**

Vì bulk/native DML và các hệ thống khác ghi DB không chạy JPA listener cho các rows ấy.

**19. Muốn biết ID của mọi row affected, `executeUpdate` có đủ không?**

Không. Nó trả count, không trả danh sách IDs; cần thiết kế truy xuất IDs/DB returning/audit theo consistency.

**20. Vì sao không được gọi `commit` thành công chỉ từ kết quả `executeUpdate`?**

Vì transaction còn có thể rollback hoặc lỗi ở commit. Kết quả bền vững chỉ được xác nhận tại transaction boundary.

**21. Bulk UPDATE có cho phép trực tiếp `JOIN FETCH` như SELECT không?**

Không. Bulk DML có grammar riêng; dùng subquery trong WHERE hoặc native SQL khi cần.

**22. Tại sao thay đổi version thủ công vẫn chưa bảo đảm domain invariant?**

Vì việc bump version không gọi business method, không chạy callback và không tự xử lý cascade/audit.

**23. Việc gọi `refresh` sau bulk update có rủi ro gì?**

Nó có thể ghi đè pending local changes, cascade REFRESH và chịu transaction isolation.

**24. Bulk DELETE ảnh hưởng second-level cache như thế nào?**

Tùy provider/cấu hình, không được mặc định mọi caches đều đồng bộ. Cần chính sách invalidation rõ.

**25. Khi nào entity-by-entity update là lựa chọn tốt hơn bulk?**

Khi cần domain methods, callbacks, cascade, per-entity version checks và event semantics thực sự.

---

## 40. Tổng kết: sự khác nhau nằm ở semantics, không chỉ SQL

Khi thực hiện `em.remove(managedEntity)` hoặc sửa một managed entity, JPA có thể quản lý vòng đời object, callbacks, cascade và optimistic locking dựa trên `@Version`.

Khi dùng **JPQL bulk UPDATE/DELETE, CriteriaUpdate/CriteriaDelete hoặc native SQL DML**, dữ liệu được thay đổi trực tiếp theo tập điều kiện ở database:

```text
                       Managed entity path       Bulk DML path
                       -------------------       -------------
Domain methods         Có thể gọi                Không tự gọi
@PreUpdate/@PostUpdate Theo entity lifecycle     Không chạy cho rows bulk
@PreRemove/@PostRemove Theo entity lifecycle     Không chạy cho rows bulk
Cascade REMOVE         Theo em.remove            Không áp dụng
orphanRemoval          Theo managed relation     Không áp dụng
@Version               JPA tự quản lý            Tự đưa vào query nếu cần
Persistence context    Theo dõi managed state    Có thể stale
DB constraints         Vẫn chạy                  Vẫn chạy
DB triggers            Theo SQL thực tế          Theo SQL thực tế
Transaction            Cần đúng boundary         Cần đúng boundary
```

### 40.1. Mẫu bulk UPDATE có ý thức về version

```java
int affected = em.createQuery(
    """
    UPDATE PurchaseOrder o
    SET o.status = :expired,
        o.updatedAt = :now,
        o.version = o.version + 1
    WHERE o.status = :draft
      AND o.expiresAt < :now
    """
)
.setParameter("expired", OrderStatus.EXPIRED)
.setParameter("draft", OrderStatus.DRAFT)
.setParameter("now", now)
.executeUpdate();
```

Nó **đặt được một số quy tắc** (trạng thái trước đó, thời điểm, audit timestamp, numeric version increment), nhưng vẫn **không** gọi callback/cascade hoặc domain method.

### 40.2. Mẫu bulk UPDATE với expected version của một entity

```java
int count = em.createQuery(
    """
    UPDATE PurchaseOrder o
    SET o.status = :newStatus,
        o.version = o.version + 1
    WHERE o.id = :id
      AND o.version = :expectedVersion
    """
)
.setParameter("newStatus", OrderStatus.EXPIRED)
.setParameter("id", id)
.setParameter("expectedVersion", expectedVersion)
.executeUpdate();

if (count != 1) {
    // Phân loại không tồn tại/version mismatch/khác...
    throw new IllegalStateException(
        "Không thể cập nhật với trạng thái dữ liệu hiện tại"
    );
}
```

### 40.3. Quy tắc ghi nhớ

1. **Bulk DML bỏ qua callback lifecycle của những entity được update/delete trực tiếp.**
2. **Bulk DELETE không áp dụng JPA cascade REMOVE hoặc orphanRemoval**, dù database FK/ON DELETE CASCADE vẫn có hiệu lực.
3. **Bulk DML không có optimistic locking tự động theo `@Version`**; nếu cần, phải chủ động thêm predicate/increment phù hợp.
4. **Persistence context không được tự đồng bộ sau bulk**; tránh tiếp tục dùng managed state cũ. Cân nhắc context mới hoặc `flush → bulk → clear` với hiểu biết về pending changes.
5. **Database triggers, constraints và transaction vẫn hoạt động**, nhưng không tương đương JPA lifecycle/domain events.
6. **Audit, soft delete, version và business invariant phải bao phủ tất cả write paths**, không chỉ managed entity methods.
7. **Chọn bulk khi lợi ích thao tác tập hợp đáng giá hơn việc bỏ qua per-entity lifecycle**, và đã thiết kế bù những semantics cần giữ.

Câu hỏi cốt lõi trước một lệnh `executeUpdate()` là:

> **Nếu bỏ qua mọi callback, cascade và version check mà entity bình thường đang dựa vào, dữ liệu và quy trình nghiệp vụ có còn đúng không?**

Nếu câu trả lời chưa rõ, hãy xem lại đường cập nhật hoặc thêm những bảo vệ cần thiết một cách tường minh, thay vì coi bulk query là phiên bản “nhanh hơn nhưng giống hệt” của quản lý entity.

### Tài liệu tham khảo

- [Jakarta Persistence — các phiên bản đặc tả chính thức](https://jakarta.ee/specifications/persistence/)
- [Jakarta Persistence 3.1 — toàn văn đặc tả, phần Bulk Update and Delete Operations](https://jakarta.ee/specifications/persistence/3.1/jakarta-persistence-spec-3.1.html)
- [Jakarta Persistence 3.2 — đặc tả chính thức](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html)
- [Jakarta Persistence API — `Query` / `executeUpdate()`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/query)
- [Jakarta Persistence API — `CriteriaUpdate`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/criteria/criteriaupdate)
- [Jakarta Persistence API — `CriteriaDelete`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/criteria/criteriadelete)
- [Jakarta Persistence API — `Version`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/version)
- [Jakarta Persistence API — `PreUpdate`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/preupdate)
- [Jakarta Persistence API — `PreRemove`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/preremove)
