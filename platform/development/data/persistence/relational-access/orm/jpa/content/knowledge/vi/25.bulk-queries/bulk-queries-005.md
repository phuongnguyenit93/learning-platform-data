# Phân biệt thay đổi hàng loạt và thay đổi từng entity được quản lý

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Nhóm kiến thức:** Truy vấn thay đổi

Khi cần đổi trạng thái cho 50.000 đơn hàng đã quá hạn, ứng dụng JPA có ít nhất hai hướng triển khai:

1. **Tải từng entity thành managed, gọi phương thức nghiệp vụ rồi để JPA dirty checking ghi thay đổi.**
2. **Gửi một truy vấn bulk UPDATE trực tiếp tới cơ sở dữ liệu** bằng JPQL, CriteriaUpdate hoặc một API repository tương ứng.

Hai hướng có thể tạo ra dữ liệu cuối cùng giống nhau trong trường hợp rất đơn giản, nhưng **khác nhau căn bản ở vòng đời entity, đồng bộ persistence context, optimistic locking, cascade, callbacks, transaction và chi phí thực thi**.

Ví dụ đầu tiên:

~~~java
// Thay đổi từng managed entity.
List<SalesOrder> orders = em.createQuery(
    """
    select o
    from SalesOrder o
    where o.status = :created and o.expiresAt < :now
    """,
    SalesOrder.class
)
.setParameter("created", OrderStatus.CREATED)
.setParameter("now", now)
.getResultList();

for (SalesOrder order : orders) {
    order.expire(now);
}
// Dirty checking đưa thay đổi vào SQL tại flush/commit.
~~~

Ví dụ thứ hai:

~~~java
// Thay đổi hàng loạt, không load SalesOrder entities.
int affected = em.createQuery(
    """
    update SalesOrder o
    set o.status = :expired,
        o.closedAt = :now
    where o.status = :created
      and o.expiresAt < :now
    """
)
.setParameter("expired", OrderStatus.EXPIRED)
.setParameter("created", OrderStatus.CREATED)
.setParameter("now", now)
.executeUpdate();
~~~

**Bulk UPDATE không gọi phương thức expire(now) cho từng SalesOrder**, cũng không tự làm cho các SalesOrder đã managed trong RAM nhận trạng thái mới. Đổi lại, nó có thể xử lý nhiều hàng qua một câu SQL tương ứng mà không cần tạo hàng nghìn Java entities.

Bài học này xây dựng tư duy chọn đúng kỹ thuật cho từng mục tiêu, minh họa bằng **Jakarta Persistence (JPA)**, JPQL bulk DML, Criteria API và Spring Data JPA. Các ví dụ chủ yếu dùng entity SalesOrder để giữ nhất quán về nghiệp vụ.

## 1. Bản đồ tư duy: hai con đường thay đổi dữ liệu

~~~text
Yêu cầu: thay đổi các đơn hàng quá hạn
                    |
        +-----------+-----------+
        |                       |
        v                       v
   Từng entity             Bulk DML query
        |                       |
 SELECT / find           JPQL UPDATE/DELETE
        |                 CriteriaUpdate/Delete
        v                       |
 Managed SalesOrder             |
        |                       |
 domain method                 |
        |                       |
 dirty checking                |
        |                       |
        +-------> SQL <---------+
                   |
                   v
           Database transaction
                   |
            commit / rollback
~~~

Ở phía **managed entity**, JPA quản lý Java instances và chuyển những thay đổi state thành SQL. Ở phía **bulk DML**, query mô tả trực tiếp những database rows sẽ được cập nhật/xóa. Cả hai vẫn có thể chạy trong một transaction, nhưng bulk DML **bỏ qua phần lớn cơ chế vòng đời của từng managed entity**.

### 1.1. Bảng so sánh nhanh

| Khía cạnh | Thay đổi từng managed entity | Bulk UPDATE/DELETE |
|---|---|---|
| Đọc entity vào Java | Thường có | Không bắt buộc |
| Dirty checking | Có, với managed entity | Không áp cho các rows bulk xử lý |
| Gọi domain method | Có thể thực hiện từng entity | Không tự gọi |
| @PreUpdate / @PreRemove | Theo lifecycle callback tương ứng | Không gọi trên từng entity bởi bulk DML |
| Entity listeners/auditing | Theo lifecycle JPA | Không tự chạy từng entity |
| @Version | Provider thường kiểm tra khi update/remove entity versioned | Không tự áp optimistic locking cho từng row |
| CascadeType.REMOVE | Có thể áp qua em.remove theo mapping | Không chạy ORM cascade như em.remove |
| orphanRemoval | Theo thay đổi managed associations | Không tự chạy collection lifecycle |
| Persistence context sau thay đổi | Tracking managed state | Có thể chứa entity stale |
| Số SQL statements | Có thể nhiều UPDATE/DELETE, batching tùy provider | Thường một SQL DML tương ứng một bulk query |
| Số hàng bị ảnh hưởng | Theo số entities được xử lý/ghi | executeUpdate() trả số lượng được báo theo JPA |
| Validation/domain invariant | Có thể áp trong method/entity lifecycle | Phải biểu đạt/kiểm soát riêng |
| DB constraints/triggers | Vẫn áp dụng | Vẫn áp dụng |
| Transaction commit/rollback | Có | Có |
| Phù hợp | Logic từng entity, aggregates, lifecycle | Thay đổi set-based đơn giản, số lượng lớn |

**Không nên coi bulk là phiên bản nhanh hơn nhưng tương đương 100% với vòng lặp em.remove hoặc dirty checking.** Nó có hợp đồng hành vi khác, nên quyết định phải bắt đầu từ tính đúng đắn nghiệp vụ.

## 2. Mô hình dữ liệu xuyên suốt bài học

Ta dùng đơn hàng **SalesOrder**. Một đơn hàng ở trạng thái CREATED có thời hạn xác nhận; khi thời hạn đã qua, hệ thống có thể chuyển nó thành EXPIRED.

### 2.1. Enum OrderStatus

~~~java
package com.example.order;

public enum OrderStatus {
    CREATED,
    CONFIRMED,
    CANCELLED,
    EXPIRED
}
~~~

### 2.2. Entity SalesOrder

~~~java
package com.example.order;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

@Entity
@Table(name = "sales_orders")
public class SalesOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    @Column(name = "version", nullable = false)
    private Long version;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 20)
    private OrderStatus status;

    @Column(name = "expires_at")
    private Instant expiresAt;

    @Column(name = "closed_at")
    private Instant closedAt;

    @Column(name = "archived_at")
    private Instant archivedAt;

    @Column(name = "total_amount", nullable = false,
            precision = 19, scale = 2)
    private BigDecimal totalAmount;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<SalesOrderLine> lines = new ArrayList<>();

    protected SalesOrder() {}

    public SalesOrder(
            Long tenantId,
            Instant expiresAt,
            BigDecimal totalAmount) {
        this.tenantId = Objects.requireNonNull(tenantId);
        this.expiresAt = expiresAt;
        this.totalAmount = Objects.requireNonNull(totalAmount);
        this.status = OrderStatus.CREATED;
    }

    public Long getId() { return id; }
    public Long getVersion() { return version; }
    public Long getTenantId() { return tenantId; }
    public OrderStatus getStatus() { return status; }
    public Instant getExpiresAt() { return expiresAt; }
    public Instant getClosedAt() { return closedAt; }
    public Instant getArchivedAt() { return archivedAt; }
    public BigDecimal getTotalAmount() { return totalAmount; }

    public void expire(Instant now) {
        Objects.requireNonNull(now);

        if (status != OrderStatus.CREATED) {
            throw new IllegalStateException(
                "Chỉ đơn CREATED mới có thể hết hạn");
        }
        if (expiresAt == null || !expiresAt.isBefore(now)) {
            throw new IllegalStateException(
                "Chưa đến thời điểm hết hạn");
        }

        status = OrderStatus.EXPIRED;
        closedAt = now;
    }

    public void archive(Instant now) {
        Objects.requireNonNull(now);

        if (status != OrderStatus.CANCELLED
                && status != OrderStatus.EXPIRED) {
            throw new IllegalStateException(
                "Chỉ đơn đã kết thúc mới được lưu trữ");
        }

        archivedAt = now;
    }
}
~~~

Phương thức **expire** đại diện cho một quy tắc nghiệp vụ. Nó không đơn thuần set status: nó kiểm tra trạng thái hiện tại và thời hạn, rồi ghi closedAt.

### 2.3. Entity SalesOrderLine

~~~java
package com.example.order;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.util.Objects;

@Entity
@Table(name = "sales_order_lines")
public class SalesOrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private SalesOrder order;

    @Column(name = "sku", nullable = false)
    private String sku;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    @Column(name = "unit_price", nullable = false,
            precision = 19, scale = 2)
    private BigDecimal unitPrice;

    protected SalesOrderLine() {}

    public SalesOrderLine(
            SalesOrder order, String sku,
            int quantity, BigDecimal unitPrice) {
        this.order = Objects.requireNonNull(order);
        this.sku = Objects.requireNonNull(sku);
        this.quantity = quantity;
        this.unitPrice = Objects.requireNonNull(unitPrice);
    }

    public Long getId() { return id; }
}
~~~

Ví dụ chỉ cần mô tả quan hệ line–order; khi xây aggregate thật, nên có helper trên SalesOrder để thêm/xóa line và đồng bộ cả hai phía của quan hệ.

### 2.4. Schema minh họa bằng PostgreSQL

~~~sql
CREATE TABLE sales_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    version BIGINT NOT NULL DEFAULT 0,
    tenant_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    expires_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    archived_at TIMESTAMPTZ,
    total_amount NUMERIC(19, 2) NOT NULL
        CHECK (total_amount >= 0)
);

CREATE INDEX idx_sales_orders_expiry
    ON sales_orders (tenant_id, status, expires_at);

CREATE TABLE sales_order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES sales_orders(id),
    sku VARCHAR(100) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(19, 2) NOT NULL
        CHECK (unit_price >= 0)
);
~~~

Đây là SQL minh họa; cú pháp IDENTITY, kiểu timestamp và index phụ thuộc database. Cột **version** được dùng để giải thích optimistic locking. Với Hibernate và schema do migration quản lý, cần chắc chắn cơ chế khởi tạo và cập nhật version tương thích với mapping @Version.

### 2.5. Tập dữ liệu ví dụ

| ID | Tenant | Status | expiresAt so với now | archivedAt |
|---:|---:|---|---|---|
| 1 | 10 | CREATED | Đã qua | NULL |
| 2 | 10 | CREATED | Tương lai | NULL |
| 3 | 10 | CONFIRMED | Đã qua | NULL |
| 4 | 10 | CREATED | Đã qua | NULL |
| 5 | 20 | CREATED | Đã qua | NULL |
| 6 | 10 | CANCELLED | Đã qua | NULL |
| 7 | 10 | CREATED | NULL | NULL |
| 8 | 10 | CREATED | Đã qua | Có timestamp |

Nếu nghiệp vụ chỉ xử lý **tenant 10, status CREATED, expiresAt trước now và chưa archived**, tập đơn cần chuyển là **ID 1 và 4**. Query chỉ lọc status + expiresAt nhưng quên tenant/archivedAt có thể sửa dữ liệu ngoài phạm vi yêu cầu.

## 3. Thay đổi từng entity được quản lý: dirty checking

Khi JPA tải SalesOrder trong một persistence context đang hoạt động, entity trở thành **managed**. Provider theo dõi những thay đổi persistent state và đồng bộ chúng khi flush/commit.

~~~java
SalesOrder order = em.find(SalesOrder.class, id);

order.expire(now);

// Không cần gọi em.merge(order) nếu order vẫn managed.
// Flush/commit sẽ xử lý thay đổi theo cơ chế JPA.
~~~

Một SQL update điển hình cho entity versioned có thể tương tự:

~~~sql
UPDATE sales_orders
SET status = 'EXPIRED',
    closed_at = ?,
    version = ?
WHERE id = ?
  AND version = ?;
~~~

SQL thực tế phụ thuộc provider, chiến lược cập nhật và những column đang dirty. Điểm cần nhớ là JPA có thể sử dụng version gốc trong WHERE để phát hiện xung đột.

### 3.1. Ví dụ service Spring @Transactional

~~~java
@Service
public class OrderLifecycleService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void expireOne(
            long tenantId, long orderId, Instant now) {

        SalesOrder order = em.find(
            SalesOrder.class, orderId);

        if (order == null
                || !order.getTenantId().equals(tenantId)) {
            throw new IllegalArgumentException(
                "Đơn hàng không tồn tại trong tenant");
        }

        order.expire(now);
    }
}
~~~

Logic xác thực **tenantId** nằm trong service trước khi áp dụng domain method. Trong ứng dụng thật, tenantId phải bắt nguồn từ context xác thực/ủy quyền của server, không tin hoàn toàn vào ID do client tự gửi.

Lợi ích:
- Gọi quy tắc expire trên từng order;
- @Version có thể phát hiện stale write;
- Entity lifecycle callback tương ứng có thể được gọi;
- Có thể đồng bộ domain events/audit ở service theo cơ chế phù hợp;
- Các quan hệ/aggregate rules có thể được xử lý rõ.

### 3.2. Từng entity vẫn có thể xử lý một danh sách

~~~java
@Transactional
public int expireSelected(
        long tenantId, List<Long> ids, Instant now) {

    int expired = 0;

    for (Long id : ids) {
        SalesOrder order = em.find(SalesOrder.class, id);

        if (order == null
                || !order.getTenantId().equals(tenantId)) {
            continue;
        }

        order.expire(now);
        expired++;
    }

    return expired;
}
~~~

Đây là **nhiều thay đổi entity theo từng instance**, không phải một truy vấn bulk UPDATE. Dù framework/driver có thể batch các SQL UPDATE khi flush, cơ chế dirty checking và lifecycle vẫn áp dụng cho từng managed entity.

### 3.3. SELECT trước khi sửa có chi phí

Để gọi domain method, code thường phải load entity và đôi khi associations. Với 100.000 đơn, có thể phát:
- Nhiều SELECT;
- Nhiều Java entity allocations;
- Managed snapshots và persistence context lớn;
- Nhiều UPDATE statements;
- N+1 nếu domain method đọc lazy relationships.

Có thể cải thiện bằng pagination, fetch plan phù hợp, JDBC statement batching và flush/clear theo chunk, nhưng vẫn khác bản chất với bulk JPQL.

### 3.4. Managed entity không cần save mỗi lần

~~~java
SalesOrder managed = em.find(SalesOrder.class, id);
managed.expire(now);
~~~

Không cần gọi **repository.save(managed)** chỉ để JPA phát hiện thay đổi. Spring Data JPA save có semantics persist/merge tùy trạng thái entity; với managed entity đang nằm trong transaction, dirty checking đã đảm nhiệm việc ghi.

### 3.5. Không mọi setter đều tạo UPDATE

Nếu một managed entity được gán lại đúng giá trị cũ, provider có thể nhận thấy không có persistent state thay đổi và không tạo SQL UPDATE. Vì thế không khẳng định “một entity duyệt qua vòng lặp luôn tạo một SQL UPDATE” hay callback PreUpdate nhất định chạy nếu không có thực tế cập nhật.

## 4. Bulk JPQL UPDATE: thay đổi tập hàng không cần tải entity

JPA hỗ trợ **bulk update statement** bằng JPQL:

~~~java
int affected = em.createQuery(
    """
    update SalesOrder o
    set o.status = :expired,
        o.closedAt = :now
    where o.tenantId = :tenantId
      and o.status = :created
      and o.expiresAt < :now
      and o.archivedAt is null
    """
)
.setParameter("expired", OrderStatus.EXPIRED)
.setParameter("created", OrderStatus.CREATED)
.setParameter("now", now)
.setParameter("tenantId", 10L)
.executeUpdate();
~~~

Với dataset, về mặt điều kiện logic **ID 1 và ID 4** khớp. Giá trị **affected** do executeUpdate trả về là số entity được báo là đã cập nhật theo API, không phải List<SalesOrder> và không phải số entity đã trở thành managed.

### 4.1. Cú pháp UPDATE JPQL

Dạng khái niệm:

~~~text
UPDATE EntityName alias
SET alias.property = expression,
    alias.otherProperty = expression
WHERE predicate
~~~

Đặc điểm:
- Dùng **entity name** SalesOrder, không dùng bảng sales_orders trực tiếp.
- Dùng **persistent property** status, closedAt, tenantId.
- Không có SELECT root.
- Dữ liệu input dùng named parameters.
- Gọi **Query.executeUpdate()**, không gọi getResultList().
- Các giá trị được chuyển tới database mà không phải dựng managed entity cho từng row.

### 4.2. Có thể cập nhật nhiều thuộc tính trong một câu

~~~java
em.createQuery(
    """
    update SalesOrder o
    set o.status = :status,
        o.closedAt = :closedAt
    where o.id = :id
    """
)
.setParameter("status", OrderStatus.CANCELLED)
.setParameter("closedAt", now)
.setParameter("id", id)
.executeUpdate();
~~~

Ngay cả khi WHERE chỉ nhắm tới một ID, **đây vẫn là bulk UPDATE theo semantics JPA**, không phải entity update. Việc chỉ sửa một row không làm JPA tự chạy @PreUpdate hoặc optimistic version check.

### 4.3. Bulk UPDATE có thể dùng biểu thức

Giả sử entity có trường **retryCount Integer**, có thể tăng trực tiếp tại DB:

~~~java
update JobTask t
set t.retryCount = t.retryCount + 1
where t.status = :waiting
~~~

Ví dụ giả định có entity JobTask với các fields tương ứng. Đây là cách set-based atomic increment, không cần đọc retryCount về Java rồi cộng 1, nhưng vẫn phải hiểu NULL, overflow, concurrency và các rule của nghiệp vụ.

### 4.4. Phép so sánh với NULL vẫn theo SQL

Điều kiện:

~~~java
where o.expiresAt < :now
~~~

không chọn orders có expiresAt NULL vì kết quả so sánh là UNKNOWN. Nếu nghiệp vụ xem expiresAt NULL là “không bao giờ hết hạn”, đây là điều đúng. Nếu có semantics khác, cần predicate rõ ràng chứ không xem NULL là một ngày rất xa hoặc rất sớm.

### 4.5. Không tự gọi domain method

Bulk UPDATE ở phần đầu tương đương phép chuyển dữ liệu **status = EXPIRED, closedAt = now** đối với rows khớp. Nó **không chạy**:

~~~java
order.expire(now);
~~~

nên mọi validation, audit, calculation, domain event hoặc side effect chỉ tồn tại trong expire() sẽ không được gọi. Nếu điều kiện chuyển trạng thái chỉ được biểu diễn bằng Java code mà không được chuyển thành WHERE/SET logic, bulk update có nguy cơ phá vỡ invariant.

## 5. Bulk JPQL DELETE khác EntityManager.remove

Để xóa tất cả các đơn đã archived trước một thời điểm:

~~~java
int deleted = em.createQuery(
    """
    delete from SalesOrder o
    where o.tenantId = :tenantId
      and o.archivedAt < :cutoff
    """
)
.setParameter("tenantId", 10L)
.setParameter("cutoff", cutoff)
.executeUpdate();
~~~

**Bulk DELETE tác động trực tiếp lên rows phù hợp trong database**, không gọi em.remove cho từng managed SalesOrder.

### 5.1. Xóa từng entity

~~~java
SalesOrder order = em.find(SalesOrder.class, id);

if (order != null) {
    em.remove(order);
}
~~~

Với em.remove(managed):
- SalesOrder chuyển sang trạng thái removed theo JPA;
- CascadeType.REMOVE hoặc CascadeType.ALL có thể lan tới children theo mapping;
- @PreRemove/@PostRemove và entity listeners tương ứng có thể chạy;
- ORM quản lý những thao tác xóa liên quan và thứ tự SQL;
- Version check có thể áp dụng với versioned entity.

### 5.2. Bulk DELETE không thực thi ORM cascade

Trong ví dụ, SalesOrder có:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<SalesOrderLine> lines;
~~~

Nếu xóa bằng em.remove(order), CascadeType.REMOVE từ ALL có thể xóa lines qua lifecycle JPA.

Nhưng:

~~~java
delete from SalesOrder o where o.id = :id
~~~

**không kích hoạt** CascadeType.REMOVE hoặc orphanRemoval trên từng SalesOrderLine. Nếu bảng sales_order_lines còn FK tham chiếu order và DB không có ON DELETE CASCADE, câu DELETE có thể thất bại vì foreign key constraint.

### 5.3. Database cascade khác JPA cascade

Nếu FK được định nghĩa:

~~~sql
FOREIGN KEY (order_id)
REFERENCES sales_orders(id)
ON DELETE CASCADE
~~~

database có thể tự xóa child rows khi DELETE parent. Nhưng đó là **DB constraint cascade**, không phải JPA lifecycle cascade; @PreRemove trên child không tự chạy theo các DELETE do database thực hiện.

Không chuyển một ứng dụng dùng JPA cascade sang bulk DELETE chỉ vì “có cascade rồi” mà chưa xác định cascade thuộc tầng nào.

### 5.4. Soft delete là UPDATE, không phải DELETE

Đánh dấu:

~~~java
update SalesOrder o
set o.archivedAt = :now
where o.tenantId = :tenantId
  and o.status in :terminalStatuses
  and o.archivedAt is null
~~~

là một bulk UPDATE lưu trữ mềm, **không xóa row**. Điều kiện về các trạng thái kết thúc phải được xác định bởi business rules.

Trong ví dụ:

~~~java
List<OrderStatus> terminalStatuses = List.of(
    OrderStatus.CANCELLED,
    OrderStatus.EXPIRED
);
~~~

Dù có tên archivedAt, ứng dụng phải nhất quán trong tất cả query đọc để không hiển thị hàng đã lưu trữ nếu đó là policy. Bulk soft delete không tự động bổ sung WHERE archivedAt IS NULL vào mọi JPQL sau này.

### 5.5. Xóa có thể liên quan nhiều bảng

Nếu cần xóa một Order aggregate gồm Lines, Payments, Audit logs và foreign keys, nên chọn một trong các chiến lược có chủ đích:
- Từng entity em.remove với JPA cascade và callbacks;
- DB ON DELETE CASCADE đã được thiết kế và kiểm thử;
- Xóa theo thứ tự phụ thuộc bằng nhiều DML queries trong một transaction;
- Archival/partitioning hoặc batch cleanup riêng.

Không dùng bulk DELETE parent rồi bỏ qua lỗi FK bằng cách tắt constraints.

## 6. Khác biệt lớn nhất: persistence context không được tự đồng bộ

Trong một persistence context, JPA duy trì **identity map**: một database entity identity tương ứng một managed instance.

Giả sử:

~~~java
SalesOrder order = em.find(SalesOrder.class, orderId);

System.out.println(order.getStatus()); // CREATED
~~~

Sau đó bulk update database:

~~~java
em.createQuery(
    """
    update SalesOrder o
    set o.status = :expired,
        o.closedAt = :now
    where o.id = :id
    """
)
.setParameter("expired", OrderStatus.EXPIRED)
.setParameter("now", now)
.setParameter("id", orderId)
.executeUpdate();
~~~

Object **order** đang managed có thể vẫn chứa:

~~~java
order.getStatus() == OrderStatus.CREATED
~~~

dù database đã được UPDATE trong transaction.

### 6.1. Vì sao vậy?

Bulk DML **không duyệt từng managed SalesOrder trong Java để gọi setters**. Provider gửi một DML statement tới DB và nhận số lượng rows; nó không có nghĩa vụ cập nhật mọi object Java tương ứng trong persistence context.

~~~text
Persistence context trước bulk:
SalesOrder#42 { status = CREATED }  [managed]

             bulk JPQL UPDATE
                      |
                      v
Database row #42 { status = EXPIRED }

Persistence context ngay sau bulk:
SalesOrder#42 { status = CREATED }  [vẫn managed, stale]
~~~

### 6.2. Find lại cùng ID chưa chắc giúp

~~~java
SalesOrder same = em.find(SalesOrder.class, orderId);
~~~

Nếu context đang giữ SalesOrder#42, **em.find** có thể trả chính managed instance cũ từ identity map:

~~~java
same == order // true trong cùng persistence context.
~~~

Vì vậy gọi find lại mà không refresh/clear không bảo đảm đọc state mới của bulk update.

### 6.3. Cách 1: refresh một managed entity

~~~java
em.refresh(order);

System.out.println(order.getStatus()); // EXPIRED nếu DB đã ghi.
~~~

**em.refresh** nạp lại state của một managed entity từ database. Dùng khi bạn phải tiếp tục làm việc với chính reference đó và biết procedure/bulk update đã thay đổi row.

Lưu ý:
- refresh chỉ hợp lệ với managed entity;
- có thể ghi đè những thay đổi Java chưa flush;
- có thể phát SELECT;
- không phải cách tốt để refresh 100.000 managed entities;
- nếu bulk DELETE đã xóa row, refresh có thể báo lỗi khi entity không còn tồn tại.

### 6.4. Cách 2: clear toàn persistence context

~~~java
em.clear();

SalesOrder reloaded =
    em.find(SalesOrder.class, orderId);
~~~

Sau clear, old **order** trở thành detached và reloaded là một managed instance mới (nếu row còn tồn tại). **clear ảnh hưởng toàn context**, không chỉ orders bị bulk update. Những references ngoài vòng lặp vẫn còn là Java objects nhưng không còn được dirty checking.

### 6.5. Cách 3: tách transaction/persistence context

Một service được thiết kế thành các unit of work tách biệt có thể:
1. Hoàn tất transaction đọc/sửa trước;
2. Thực thi bulk DML trong transaction riêng;
3. Dùng persistence context mới cho các truy vấn sau.

Lựa chọn này có thể giảm nguy cơ dùng stale entities, nhưng phải xét atomicity và concurrency. Không chia transaction chỉ để tránh clear nếu nghiệp vụ đòi tất cả thao tác phải cùng rollback.

### 6.6. Stale state không chỉ ảnh hưởng getter

Nguy cơ lớn hơn việc hiển thị giá trị cũ: code có thể tiếp tục sửa object **order** đang stale:

~~~java
order.archive(now);
~~~

Nếu provider phát một UPDATE từ snapshot cũ mà không kiểm soát version, dữ liệu có thể bị ghi đè hoặc lỗi concurrency tùy mapping/provider. Với @Version mà bulk DML không tăng version, khả năng phát hiện xung đột cũng có thể suy yếu.

**Không tiếp tục dùng managed entity stale sau bulk DML** nếu nó nằm trong phạm vi bulk thay đổi; làm mới context hoặc thiết kế transaction boundary rõ.

## 7. Thứ tự an toàn: flush trước bulk, clear sau bulk

Một trình tự thông dụng:

~~~java
em.flush();

int affected = em.createQuery(
    """
    update SalesOrder o
    set o.status = :expired,
        o.closedAt = :now
    where o.tenantId = :tenantId
      and o.status = :created
      and o.expiresAt < :now
    """
)
.setParameter("expired", OrderStatus.EXPIRED)
.setParameter("created", OrderStatus.CREATED)
.setParameter("tenantId", tenantId)
.setParameter("now", now)
.executeUpdate();

em.clear();
~~~

### 7.1. Vì sao flush trước?

Nếu context có pending changes, mà bulk DML cũng đụng cùng bảng/rows, **thứ tự SQL** có thể ảnh hưởng kết quả. Flush trước bulk giúp DB thấy những thay đổi pending mà ứng dụng muốn được thực hiện trước câu bulk.

Ví dụ:

~~~java
SalesOrder managed = em.find(SalesOrder.class, id);
// Một domain method đã đổi status nhưng chưa flush.

em.flush();
bulkUpdate(...);
~~~

Tất nhiên, **flush không commit**: cả hai loại thay đổi vẫn có thể rollback cùng transaction.

### 7.2. Vì sao không clear trước flush?

~~~java
em.clear();
em.flush();
~~~

Clear tách các managed entities khỏi context; những thay đổi pending chưa được đồng bộ có thể bị mất khỏi luồng ghi. Nếu cần giữ chúng, phải flush trước clear.

### 7.3. Vì sao clear sau bulk?

Sau bulk, các managed objects có thể không khớp database. Clear làm chúng detached, buộc code đọc lại bằng một context sạch nếu cần.

Nhưng clear cũng tách **các entity không liên quan**, ví dụ một Customer vừa được service tải để xử lý tiếp. Vì thế không nên gọi clear trong một helper ngầm mà không nói rõ side effect.

### 7.4. Flush mode AUTO không thay thế thiết kế rõ ràng

Tùy flush mode và provider, JPA có thể auto-flush trước một query. Tuy nhiên khi correctness phụ thuộc thứ tự UPDATE của managed entities và bulk DML, **explicit flush** thường làm flow dễ hiểu hơn. Không dùng FlushModeType.COMMIT với hy vọng mọi pending state luôn được bỏ qua một cách an toàn.

### 7.5. Flush sau bulk có giải quyết stale state không?

Không. **em.flush() sau bulk không tự cập nhật Java instances** tương ứng. Nó chủ yếu đồng bộ các dirty managed state đang có, thậm chí có nguy cơ ghi đè dữ liệu nếu chúng stale.

Để xử lý stale state, dùng refresh/clear hoặc persistence context mới. Flush là chiều **Java managed → DB**, còn refresh là chiều **DB → managed Java** cho một entity.

### 7.6. Nếu service có nhiều bước liên quan

~~~text
A. Sửa managed Customer
B. Bulk expire SalesOrders
C. Tiếp tục sửa Customer
D. Commit
~~~

Nếu gọi clear ở B, Customer từ A cũng detached; bước C sẽ không được dirty checking trừ khi nạp lại. Tùy nghiệp vụ:
- Flush trước B, clear sau B, rồi find lại Customer;
- Hoặc tổ chức B ở một boundary/context khác phù hợp;
- Hoặc dùng refresh có mục tiêu thay vì clear toàn context, khi số entity bị ảnh hưởng nhỏ và biết rõ phạm vi.

## 8. @Version: optimistic locking khác nhau ra sao?

Với managed entity versioned:

~~~java
@Version
private Long version;
~~~

JPA có thể sử dụng version trong UPDATE để phát hiện người khác đã sửa entity kể từ lúc load.

### 8.1. Managed update thường có version check

Giả sử:
- Transaction A tải SalesOrder#42 version=5.
- Transaction B tải SalesOrder#42 version=5.
- B cập nhật/commit, version lên 6.
- A cố ghi lại bản version=5.

JPA thường tạo SQL về mặt logic:

~~~sql
UPDATE sales_orders
SET status = 'EXPIRED',
    version = 6
WHERE id = 42 AND version = 5;
~~~

Nếu không còn row version=5, provider phát hiện stale write và báo **OptimisticLockException** ở flush/commit hoặc điểm phù hợp. Transaction lỗi cần rollback; không tiếp tục ghi như không có gì xảy ra.

### 8.2. Bulk UPDATE không tự áp @Version

~~~java
update SalesOrder o
set o.status = :expired
where o.id = :id
~~~

Câu này **không tự thêm** điều kiện:

~~~sql
AND version = :expectedVersion
~~~

và không tự tăng version theo cơ chế managed entity optimistic locking. Việc entity class có @Version **không biến bulk JPQL UPDATE thành từng versioned entity update**.

### 8.3. Có thể tăng version thủ công trong bulk

Với version là Long, khi thiết kế cho phép:

~~~java
int changed = em.createQuery(
    """
    update SalesOrder o
    set o.status = :expired,
        o.closedAt = :now,
        o.version = o.version + 1
    where o.tenantId = :tenantId
      and o.status = :created
      and o.expiresAt < :now
    """
)
.setParameter("expired", OrderStatus.EXPIRED)
.setParameter("created", OrderStatus.CREATED)
.setParameter("now", now)
.setParameter("tenantId", tenantId)
.executeUpdate();
~~~

Cách này làm các managed snapshots đã load version cũ có thể gặp conflict nếu cố UPDATE tiếp. Nhưng đây là **tăng version thủ công**, không đồng nghĩa JPA tự kiểm tra version của từng row được bulk update.

### 8.4. Version predicate cho cập nhật có điều kiện một row

Nếu API muốn cập nhật SalesOrder#42 chỉ khi version vẫn là 5:

~~~java
int changed = em.createQuery(
    """
    update SalesOrder o
    set o.status = :expired,
        o.closedAt = :now,
        o.version = o.version + 1
    where o.id = :id
      and o.tenantId = :tenantId
      and o.version = :expectedVersion
      and o.status = :created
    """
)
.setParameter("expired", OrderStatus.EXPIRED)
.setParameter("now", now)
.setParameter("id", orderId)
.setParameter("tenantId", tenantId)
.setParameter("expectedVersion", expectedVersion)
.setParameter("created", OrderStatus.CREATED)
.executeUpdate();

if (changed != 1) {
    // Không có row khớp version/trạng thái/tenant,
    // không khẳng định ngay là chỉ do version conflict.
    throw new IllegalStateException(
        "Đơn không tồn tại, không đúng trạng thái hoặc đã đổi");
}
~~~

Đây là mô hình **compare-and-set** ở database, hữu ích cho conditional transitions. Nhưng cần xác định:
- Có đúng một row theo ID;
- Kết quả 0 có thể do tenant, status hoặc version;
- @PreUpdate/domain method vẫn bị bypass;
- Context phải được làm mới sau bulk;
- Dùng transaction và DB constraints phù hợp.

### 8.5. Tăng version không tự bảo vệ invariant nhiều hàng

Một business rule như “không được oversell hàng tồn kho qua nhiều đơn” liên quan nhiều rows. Tăng SalesOrder.version không đảm bảo tồn kho Product được bảo vệ. Cần thiết kế transactional locking, atomic conditional UPDATE, constraint hoặc phương pháp concurrency riêng cho dữ liệu liên quan.

### 8.6. Khi version không phải số nguyên

Các provider/JPA có thể hỗ trợ version kiểu khác, như timestamp. Không dùng phép cộng **version + 1** nếu version không phải numeric phù hợp. Chọn cơ chế tương thích provider và schema.

## 9. Entity callbacks, Bean Validation và auditing

Thay đổi managed entity có thể đi qua JPA lifecycle events:

~~~java
@EntityListeners(OrderAuditListener.class)
@Entity
public class SalesOrder {
    // ...
}
~~~

Listener ví dụ:

~~~java
public class OrderAuditListener {

    @PreUpdate
    public void beforeUpdate(SalesOrder order) {
        // Chỉ là ví dụ lifecycle callback.
    }

    @PreRemove
    public void beforeRemove(SalesOrder order) {
        // Chỉ là ví dụ lifecycle callback.
    }
}
~~~

Khi JPA cập nhật managed entity bằng dirty checking, callback tương ứng có thể chạy. Khi em.remove, remove callbacks có thể chạy.

### 9.1. Bulk DML không gọi callback từng entity

~~~java
update SalesOrder o
set o.status = :expired
where ...
~~~

không load mỗi SalesOrder rồi gọi @PreUpdate hoặc @PostUpdate trên từng Java instance. Tương tự, bulk DELETE không gọi @PreRemove/@PostRemove theo từng entity.

Hệ quả:
- Audit fields đặt qua listener có thể không được cập nhật;
- Logic tính toán phụ thuộc callback không chạy;
- Các kiểm tra gắn với entity method/listener bị bỏ qua;
- Entity-level validation tích hợp vào lifecycle không được thực hiện cho từng row theo cách managed update.

### 9.2. Database constraints vẫn chạy

Nếu table có:

~~~sql
CHECK (total_amount >= 0)
~~~

thì bulk UPDATE đặt total_amount âm có thể bị DB từ chối giống các đường ghi khác. Database FK, UNIQUE, CHECK, NOT NULL và triggers là lớp bảo vệ chung cho tất cả SQL statements.

Tuy nhiên **DB constraint không tự thay thế mọi business invariant**, đặc biệt những logic liên quan trạng thái, role, hoạt động bên ngoài DB hoặc nhiều bảng.

### 9.3. DB trigger khác JPA callback

Một database trigger có thể chạy khi bulk SQL UPDATE tác động rows, nhưng đó là **trigger của database**. Nó không tương đương một @PreUpdate Java method:
- Chạy ở môi trường khác;
- Có quyền và lỗi khác;
- Thời điểm/chi tiết ghi log khác;
- Không tự truy cập Java domain service;
- Có thể áp dụng với mọi đường ghi SQL.

Nếu audit bắt buộc với cả ORM, SQL thủ công và procedure, cần kiến trúc audit chung có chủ đích: DB triggers, outbox, application service hoặc tổ hợp phù hợp.

### 9.4. Spring Data auditing không tự cập nhật mọi bulk DML

Các annotation như **@LastModifiedDate** thường dựa vào auditing listener/lifecycle callback. Một bulk update không tự đi qua callback đó. Nếu yêu cầu changedAt, updatedAt hoặc modifiedBy, có thể cần set trực tiếp trong bulk statement:

~~~java
update SalesOrder o
set o.status = :expired,
    o.closedAt = :now,
    o.updatedAt = :now
where ...
~~~

Ví dụ giả định entity có persistent field updatedAt. Nếu chưa mapping trường ấy thì không đưa nó vào query đang chạy.

### 9.5. Domain events cũng không tự phát

Nếu method **expire(now)** ghi domain event hoặc application service gửi event theo mỗi order, bulk UPDATE sẽ không gọi method đó. Đừng tự gửi N sự kiện sau bulk chỉ từ affected count nếu không biết IDs thực tế.

Khi cần publish events bảo đảm sau commit, cân nhắc:
- Lấy tập IDs đã chọn trong transaction thích hợp rồi ghi outbox;
- Dùng database transactional outbox phù hợp;
- Thiết kế transition table/batch event;
- Tách bulk job và event generation có thể retry/idempotent.

Không gửi email/webhook dựa trên việc executeUpdate trả số dương **trước khi transaction commit thành công**.

## 10. Cascade, orphanRemoval và aggregate invariants

Với SalesOrder có SalesOrderLines, thay đổi từng entity cho phép JPA áp mapping lifecycle theo aggregate.

### 10.1. em.remove và cascade

~~~java
SalesOrder order = em.find(SalesOrder.class, id);

if (order != null) {
    em.remove(order);
}
~~~

Khi mapping cascade=ALL, provider có thể xử lý remove cho children được mapping. Những callbacks của children tương ứng có thể chạy theo lifecycle.

Bulk:

~~~java
delete from SalesOrder o
where o.id = :id
~~~

không chạy ORM cascade. Vì vậy nếu FK trong sales_order_lines tham chiếu order, câu delete có thể thất bại.

### 10.2. orphanRemoval là lifecycle cho managed relationship

Nếu một line bị bỏ khỏi collection trong managed SalesOrder, orphanRemoval=true có thể dẫn đến DELETE child ở flush theo semantics mapping. Bulk UPDATE trạng thái SalesOrder **không duyệt collection để tìm orphan**.

Ngược lại, gọi bulk DELETE parent không tự làm orphanRemoval trên children. Không nhầm orphanRemoval với DB ON DELETE CASCADE.

### 10.3. Không nạp toàn bộ aggregate chỉ để đổi một cờ nếu không cần

Một đơn có 10.000 lines. Nếu nghiệp vụ chỉ cần set archivedAt khi trạng thái đã kết thúc và không có callback/cascade đặc biệt, việc fetch cả OrderLines để cập nhật một field có thể rất tốn RAM/SQL.

Nhưng nếu archive là transition cần:
- Kết chuyển số dư;
- Tạo credit note;
- Kiểm tra từng line;
- Phát một audit event cho mỗi child;

thì bulk update đơn giản có thể không đủ. **Chọn theo aggregate invariant**, không theo mong muốn “ít query nhất”.

### 10.4. Xóa mềm và dữ liệu phụ thuộc

Nếu giữ SalesOrder row và các lines, bulk UPDATE archivedAt có thể thích hợp. Nếu xóa vật lý, cần bảo vệ tính toàn vẹn FK và retention/audit policy. Một hệ thống tài chính có thể không được phép xóa cứng orders ngay cả khi SQL cho phép.

### 10.5. Entity callbacks cũng không thay authorization

Dù dùng managed entity hay bulk DML, service phải xác định người dùng được phép thao tác các order nào. Bulk UPDATE có thể tác động nhiều tenant hơn dự kiến chỉ vì quên WHERE tenantId. Không dựa vào việc domain method có check quyền nếu bulk không gọi method ấy.

## 11. Bulk DML cần transaction và kết quả thực thi được hiểu đúng

### 11.1. executeUpdate chỉ dùng cho mutation query

~~~java
int affected = em.createQuery(
    """
    update SalesOrder o
    set o.status = :expired
    where o.status = :created
    """
)
.setParameter("expired", OrderStatus.EXPIRED)
.setParameter("created", OrderStatus.CREATED)
.executeUpdate();
~~~

**affected** là số entity được cập nhật hoặc xóa theo hợp đồng của JPA Query.executeUpdate. Với inheritance/table-per-class hoặc nhiều bảng vật lý, số SQL statements và số database rows vật lý có thể không bằng số entity logic được báo.

Không dùng executeUpdate trên một SELECT rồi mong nhận row count của query. SELECT dùng getResultList/getSingleResult.

### 11.2. Mutation query cần transaction

JPQL bulk UPDATE/DELETE thực thi khi có transaction thích hợp. Nếu không có transaction, JPA có thể ném **TransactionRequiredException**. Trong Spring service, nên gọi trong method @Transactional thực sự được advice.

~~~java
@Transactional
public int expireBulk(...) {
    return em.createQuery("update ...")
             .setParameter(...)
             .executeUpdate();
}
~~~

Đoạn trên chỉ là khung; câu query và parameter cần được hoàn thiện theo các ví dụ trước.

### 11.3. executeUpdate không phải commit

~~~text
begin transaction
    |
    +-- executeUpdate() => affected = 500
    |
    +-- một thao tác khác gặp lỗi
    |
    +-- rollback transaction
~~~

Sau rollback, **500 rows trong transaction đó không được commit**, dù executeUpdate từng trả affected=500.

Không trả thông báo “500 đơn đã hoàn tất vĩnh viễn” dựa trên affected trước khi transaction kết thúc thành công, nhất là nếu còn các bước có thể lỗi sau bulk.

### 11.4. Rollback không làm Java objects tự hồi phục

Sau rollback, những managed/detached references mà ứng dụng còn giữ có thể chứa state cũ hoặc state mới trong RAM; không coi chúng là bản sao chính xác của DB. Với workflow lỗi transaction, tải lại trong persistence context/transaction mới.

### 11.5. Không nuốt database exceptions

Một bulk DELETE vi phạm FK có thể làm transaction rollback-only hoặc lỗi. Đừng bắt lỗi rồi tiếp tục thực thi nhiều query trên transaction đã hỏng. Cần rollback, phân loại exception và dùng transaction mới cho retry nếu nghiệp vụ cho phép.

### 11.6. Query timeout và lock timeout

Với bảng lớn, bulk UPDATE có thể giữ locks, ảnh hưởng giao dịch khác hoặc chờ lâu. Tùy JPA provider/DB, query timeout hint và database lock timeout có thể hữu ích:

~~~java
query.setHint("jakarta.persistence.query.timeout", 5000);
~~~

Con số milliseconds theo JPA hint, nhưng hỗ trợ và hành vi cancel/rollback phụ thuộc provider/driver/DB. Không giả định timeout đồng nghĩa statement chưa từng tác động database; cần kiểm tra trạng thái transaction và commit.

## 12. Spring Data JPA: @Modifying và @Query

Spring Data JPA cung cấp các repository methods cho bulk JPQL:

~~~java
public interface SalesOrderRepository
        extends JpaRepository<SalesOrder, Long> {

    @Modifying
    @Query("""
        update SalesOrder o
        set o.status = :expired,
            o.closedAt = :now
        where o.tenantId = :tenantId
          and o.status = :created
          and o.expiresAt < :now
          and o.archivedAt is null
        """)
    int expireMatching(
        @Param("tenantId") Long tenantId,
        @Param("created") OrderStatus created,
        @Param("expired") OrderStatus expired,
        @Param("now") Instant now
    );
}
~~~

Các imports chính:
- **org.springframework.data.jpa.repository.JpaRepository**;
- **org.springframework.data.jpa.repository.Modifying**;
- **org.springframework.data.jpa.repository.Query**;
- **org.springframework.data.repository.query.Param**;
- **java.time.Instant**.

### 12.1. @Modifying nói cho Spring Data biết đây là mutation

Với @Query chứa UPDATE/DELETE, **@Modifying** chỉ định rằng method thực thi DML thay vì đọc List/entity result. Return type có thể là int/Integer để nhận số affected, hoặc void nếu caller không cần.

### 12.2. Chạy từ service transaction

~~~java
@Service
public class OrderMaintenanceService {
    private final SalesOrderRepository repository;

    public OrderMaintenanceService(
            SalesOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public int expire(long authorizedTenantId, Instant now) {
        return repository.expireMatching(
            authorizedTenantId,
            OrderStatus.CREATED,
            OrderStatus.EXPIRED,
            now
        );
    }
}
~~~

**authorizedTenantId** phải đến từ quyền/identity do server xác minh. Service transaction là ranh giới để rollback khi có lỗi.

### 12.3. clearAutomatically và flushAutomatically

Spring Data @Modifying có hai thuộc tính:

~~~java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
~~~

Ý nghĩa:
- **flushAutomatically=true**: yêu cầu flush persistence context trước khi chạy modifying query;
- **clearAutomatically=true**: clear persistence context sau khi thực thi query.

Trong các phiên bản Spring Data JPA phổ biến, mặc định hai tùy chọn này là false. Không coi @Modifying mặc định luôn tự flush/clear theo đúng mong muốn.

### 12.4. Clear tự động có tác động rộng

Giả sử một service đã load Customer managed, sau đó gọi repository bulk method có **clearAutomatically=true**, thì Customer cũng trở thành detached trong cùng EntityManager.

Không bật clearAutomatically vô điều kiện trên một repository method được gọi giữa workflow phức tạp nếu caller còn cần dirty checking các entities đã load.

### 12.5. @Modifying không khôi phục lifecycle

Ngay cả khi:

~~~java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
~~~

bulk UPDATE vẫn:
- Không gọi domain method từng entity;
- Không kích hoạt @PreUpdate cho từng row;
- Không tự áp @Version check;
- Không chạy CascadeType.REMOVE cho bulk DELETE.

Hai thuộc tính chỉ quản lý persistence context quanh query, **không biến bulk thành entity-by-entity update**.

### 12.6. Derived delete method và bulk @Query không giống nhau

Spring Data có những derived delete methods có thể thực hiện **load entities rồi delete từng cái** để áp lifecycle/callbacks theo implementation. Trong khi đó:

~~~java
@Modifying
@Query("delete from SalesOrder o where o.archivedAt < :cutoff")
int deleteArchived(@Param("cutoff") Instant cutoff);
~~~

là JPQL bulk DELETE với semantics bypass lifecycle.

**Không suy từ chữ delete trong tên method** rằng repository sẽ dùng cùng một đường xóa. Phải xem đó là derived delete, standard repository delete/deleteAll, hay @Query bulk DML, và xác minh phiên bản Spring Data đang dùng.

### 12.7. deleteAllInBatch cũng khác deleteAll

Các API batch delete của JpaRepository được thiết kế để phát bulk-like deletes và có thể bỏ qua cascade/lifecycle như đã phân tích; **deleteAll** có thể xóa theo từng entity. Hãy đọc contract của API tương ứng trước khi chọn nó cho dữ liệu có FK/callbacks.

### 12.8. saveAll không phải một JPQL bulk UPDATE

~~~java
repository.saveAll(orders);
~~~

thường thực hiện persist/merge theo từng entity qua repository implementation, rồi ORM phát SQL tại flush/commit. Với Hibernate JDBC batching bật, nhiều statement tương tự có thể được gộp ở driver level.

Đây vẫn là **entity-oriented persistence**, không tương đương:

~~~java
@Modifying
@Query("update SalesOrder o set o.status = :status where ...")
~~~

về callbacks/version/context/performance.

## 13. CriteriaUpdate và CriteriaDelete: bulk DML bằng Java API

JPA còn có **CriteriaUpdate<T>** và **CriteriaDelete<T>** để diễn đạt bulk mutation mà không ghép chuỗi JPQL.

### 13.1. CriteriaUpdate

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaUpdate<SalesOrder> update =
    cb.createCriteriaUpdate(SalesOrder.class);

Root<SalesOrder> o = update.from(SalesOrder.class);

update.set("status", OrderStatus.EXPIRED)
      .set("closedAt", now)
      .where(
          cb.equal(o.get("tenantId"), tenantId),
          cb.equal(o.get("status"), OrderStatus.CREATED),
          cb.lessThan(o.<Instant>get("expiresAt"), now),
          cb.isNull(o.get("archivedAt"))
      );

int changed = em.createQuery(update).executeUpdate();
~~~

Điều này tương ứng với JPQL bulk UPDATE ở phần 4. **CriteriaUpdate cũng bypass managed-entity lifecycle**, không phải vì viết bằng Criteria thì dirty checking tự được áp.

### 13.2. CriteriaUpdate chỉ định entity target

~~~java
CriteriaUpdate<SalesOrder> update =
    cb.createCriteriaUpdate(SalesOrder.class);

Root<SalesOrder> root = update.from(SalesOrder.class);
~~~

Root mô tả entity được update. Khi đặt SET, đường dẫn/thuộc tính phải thuộc mapping phù hợp. CriteriaUpdate không trở thành CriteriaQuery SELECT và không có multiselect/result DTO.

### 13.3. CriteriaDelete

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaDelete<SalesOrder> delete =
    cb.createCriteriaDelete(SalesOrder.class);

Root<SalesOrder> o = delete.from(SalesOrder.class);

delete.where(
    cb.equal(o.get("tenantId"), tenantId),
    cb.lessThan(o.<Instant>get("archivedAt"), cutoff)
);

int deleted = em.createQuery(delete).executeUpdate();
~~~

Nếu archivedAt=NULL, so sánh **archivedAt < cutoff** là UNKNOWN nên row không được chọn.

### 13.4. CriteriaUpdate/CriteriaDelete không tự có optimistic locking

Giống JPQL bulk DML, Criteria mutation không tự dùng version để kiểm tra từng managed entity. Nếu muốn điều kiện version, phải khai báo rõ:

~~~java
update.where(
    cb.equal(o.get("id"), id),
    cb.equal(o.get("version"), expectedVersion)
);
~~~

và nếu muốn tăng numeric version, cần set expression tương ứng trong cùng update theo mapping.

### 13.5. Dùng Criteria khi bộ lọc thay đổi động

Ví dụ:
- Chỉ archive một tenant;
- Chỉ một tập statuses;
- Chỉ những orders trước cutoff;
- Có tùy chọn loại những orders đang bị giữ pháp lý.

CriteriaBuilder giúp tạo tập Predicate theo những điều kiện đã validate mà không ghép string. Tuy nhiên business invariants và authorization vẫn phải được lập trình riêng.

### 13.6. Hạn chế cú pháp bulk DML

JPQL bulk UPDATE/DELETE có giới hạn so với SQL dialect-specific:
- Mutation target là một entity abstract schema type;
- Không có mô hình JOIN UPDATE tự do như SELECT JOIN portable;
- Subquery ở WHERE có thể hỗ trợ những trường hợp lọc liên quan;
- ORDER BY/LIMIT cho bulk UPDATE/DELETE không phải cú pháp JPQL portable;
- Những kiểu UPDATE ... FROM, DELETE ... USING hoặc RETURNING là SQL/database/provider-specific.

Nếu cần các cú pháp mở rộng, có thể dùng native SQL với một adapter rõ ràng và kiểm thử dialect, thay vì cho rằng mọi cú pháp SQL đều viết được trong JPQL.

## 14. Batch entity updates và JDBC batching khác bulk JPQL

Một nhầm lẫn thường gặp là coi mọi thao tác “hàng loạt” như nhau.

### 14.1. Có ba mức khác nhau

| Kỹ thuật | Hành vi chính | Lifecycle entity? |
|---|---|---|
| Vòng lặp managed entities | Load/mutate từng entity, dirty checking | Có |
| JDBC batching các UPDATE | Driver gộp nhiều statements do ORM sinh | Vẫn có nếu nguồn là managed entities |
| JPQL/Criteria bulk UPDATE | Một set-based mutation query | Không gọi lifecycle từng entity |

~~~text
Managed entities:
  UPDATE id=1
  UPDATE id=2
  UPDATE id=3
       |
       +-- JDBC batching có thể gom gửi xuống driver

JPQL bulk:
  UPDATE sales_orders
  SET status='EXPIRED'
  WHERE status='CREATED' AND expires_at < ...
       |
       +-- database xử lý các rows khớp WHERE
~~~

### 14.2. Hibernate JDBC batching

Ví dụ Spring Boot dùng Hibernate:

~~~properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_updates=true
~~~

Đây là cấu hình Hibernate-specific, không phải chuẩn JPA. Nó có thể cải thiện round trips với nhiều UPDATE tương tự, nhưng không biến Java entity operations thành một JPQL bulk statement.

### 14.3. Batching vẫn giữ optimistic locking và callbacks

Khi Hibernate batch những UPDATE phát sinh từ managed entities, lifecycle và optimistic locking của từng entity vẫn là một phần của đường ORM. Ngược lại, bulk UPDATE dù chỉ có một statement vẫn bypass các cơ chế đó trừ khi ứng dụng biểu đạt thay thế rõ ràng.

### 14.4. Flush/clear theo chunk khi xử lý nhiều managed entities

~~~java
int processed = 0;

for (Long id : ids) {
    SalesOrder order = em.find(SalesOrder.class, id);

    if (order != null) {
        order.expire(now);
        processed++;
    }

    if (processed > 0 && processed % 100 == 0) {
        em.flush();
        em.clear();
    }
}

if (processed % 100 != 0) {
    em.flush();
    em.clear();
}
~~~

Code minh họa xử lý danh sách IDs. Khi số IDs lớn, list IDs cũng nên được phân trang/stream phù hợp. Nếu một order không hợp lệ và expire ném exception, cần rollback transaction/chunk theo policy, không tiếp tục sử dụng context đã lỗi.

**Clear detaches tất cả managed entities**, không chỉ 100 orders vừa xử lý. Nếu trước vòng lặp đã load List<SalesOrder> toàn bộ, sau clear đầu tiên những phần tử chưa xử lý cũng có thể detached, khiến các bước sửa tiếp không được tracking.

### 14.5. Flush mỗi 100 không phải commit mỗi 100

Một transaction chứa 100 lần flush/clear vẫn có thể rollback toàn bộ. Nếu muốn commit per chunk, phải tổ chức transaction boundary per chunk, checkpoint/idempotency, và chấp nhận partial success nếu phù hợp nghiệp vụ.

### 14.6. Vì sao bulk thường nhanh hơn khi chỉ sửa cờ?

Bulk UPDATE có thể:
- Tránh SELECT từng entity;
- Tránh khởi tạo managed entities;
- Giảm memory pressure;
- Giảm số SQL round trips;
- Đẩy filter và update set-based xuống DB.

Nhưng nếu bảng rất lớn, bulk cũng có thể tốn thời gian, giữ locks, tạo WAL/redo log và ảnh hưởng replication. Không mặc định nó luôn nhanh hơn trong mọi workload.

## 15. Business invariants: điều kiện nào có thể chuyển vào WHERE?

Mục tiêu: chuyển CREATED → EXPIRED chỉ nếu:
- Cùng tenant;
- Chưa archived;
- expiresAt khác NULL và trước now;
- Status còn CREATED.

Một bulk statement có thể bảo vệ điều kiện cơ bản:

~~~java
update SalesOrder o
set o.status = :expired,
    o.closedAt = :now
where o.tenantId = :tenantId
  and o.status = :created
  and o.expiresAt < :now
  and o.archivedAt is null
~~~

Từng phần tương ứng với một business predicate.

### 15.1. Điều kiện đơn hàng thay đổi giữa SELECT và UPDATE

Nếu code làm:
1. SELECT tất cả IDs CREATED đã quá hạn;
2. Client khác CONFIRM một order;
3. UPDATE order đó thành EXPIRED theo ID mà không kiểm tra status;

thì có thể ghi đè trạng thái CONFIRMED.

Câu bulk có WHERE **status=CREATED** được database đánh giá trong chính câu UPDATE, nên giảm rủi ro ghi nhầm row đã đổi trạng thái. Dù vậy còn phải xét isolation và business concurrency policy.

### 15.2. Điều kiện đơn giản thích hợp cho bulk

Thường gồm:
- Đổi status theo điều kiện hiện hữu của row;
- Đặt timestamp;
- Tăng một counter bằng biểu thức SQL;
- Đánh dấu archived;
- Chuẩn hóa một cột theo công thức xác định;
- Xóa rows theo retention policy khi không cần lifecycle cascade.

### 15.3. Điều kiện khó chuyển sang bulk

Ví dụ:
- Kiểm tra quyền theo một cấu trúc object/domain phức tạp;
- Tính tiền dựa trên nhiều line với quy tắc thay đổi liên tục;
- Gửi một domain event khác nhau cho mỗi order;
- Gọi external API cho từng entity;
- Thực hiện validation phụ thuộc nhiều aggregate;
- Cập nhật các liên kết JPA với orphanRemoval;
- Cần xử lý optimistic conflict theo từng entity và thông báo khác nhau.

Những trường hợp này có thể phù hợp với per-entity processing hoặc một quy trình DB set-based được thiết kế kỹ hơn, chứ không phải một lệnh UPDATE status đơn giản.

### 15.4. Dùng hai pha khi cần cả tốc độ và nghiệp vụ

Một phương án:
1. Chọn IDs theo các điều kiện cụ thể;
2. Tính toán domain logic cần thiết ở Java theo chunk;
3. Ghi một bảng trạng thái/outbox trong transaction phù hợp;
4. Thực thi bulk DML điều kiện theo IDs và version/status;
5. Kiểm tra số rows affected;
6. Commit và xử lý events sau commit.

Nhưng phải tránh race giữa pha đọc và pha ghi, giữ transaction/lock/version phù hợp, và không kỳ vọng số IDs ban đầu luôn bằng số rows bulk updated sau concurrent writes.

## 16. Bulk update trong hệ thống đa tenant và soft delete

Một câu bulk DML có khả năng tác động hàng nghìn rows. Quên một điều kiện có thể nghiêm trọng hơn rất nhiều so với một update từng entity.

### 16.1. Luôn áp row-level scope

~~~java
update SalesOrder o
set o.status = :expired,
    o.closedAt = :now
where o.tenantId = :authorizedTenantId
  and o.archivedAt is null
  and o.status = :created
  and o.expiresAt < :now
~~~

**authorizedTenantId** phải được lấy từ security context/server authorization. Không cho phép client quyết định tenantId muốn bulk-update nếu không có quyền quản trị phù hợp.

### 16.2. Soft delete không tự bật cho bulk query

Khi dùng archivedAt như soft delete flag, code phải áp:
- archivedAt IS NULL trong truy vấn active;
- archivedAt IS NOT NULL hoặc cutoff rõ trong cleanup;
- Constraint/retention policy phù hợp.

Các Hibernate-specific filters hoặc @SQLDelete có thể có hành vi riêng với bulk DML. **Không mặc định provider-specific entity filter/delete behavior sẽ tự áp vào mọi JPQL bulk update/delete**; cần xem tài liệu và kiểm thử SQL thực tế.

### 16.3. Quên WHERE là lỗi nguy hiểm

~~~java
em.createQuery(
    "update SalesOrder o set o.status = :expired"
).setParameter("expired", OrderStatus.EXPIRED)
 .executeUpdate();
~~~

Query này nhắm tới mọi SalesOrder thuộc entity scope, không tự thêm giới hạn tenant, trạng thái hay thời hạn từ ý định người lập trình.

Nên đóng gói bulk mutations trong service methods có tên nghiệp vụ, nhận những tham số đã kiểm tra và tránh cho caller truyền các JPQL fragments tùy ý.

### 16.4. Read-only transaction không phù hợp cho mutation

Spring @Transactional(readOnly = true) có thể ảnh hưởng flush mode/connection optimization tùy provider và database. Không dùng nó cho service có bulk UPDATE/DELETE. Bảo đảm write transaction được cấu hình đúng và được áp dụng qua Spring proxy.

## 17. Sự khác biệt về locking và concurrency

Bulk UPDATE vẫn là một SQL UPDATE tại database, nên có thể lấy locks và chịu transaction isolation như các câu UPDATE khác. Nhưng **cách JPA quản lý concurrency** khác per-entity update.

### 17.1. Per-entity optimistic locking

JPA dựa vào @Version của từng SalesOrder. Nếu update với old version không còn khớp, có thể ném OptimisticLockException.

### 17.2. Bulk update theo điều kiện hiện tại

Câu:

~~~sql
UPDATE sales_orders
SET status='EXPIRED'
WHERE status='CREATED'
  AND expires_at < :now;
~~~

được DB đánh giá trực tiếp theo những hàng phù hợp tại thời điểm thực thi/isolation. Nó có thể là một chuyển trạng thái atomic theo điều kiện, nhưng không có callback hay version checking mặc định của JPA.

### 17.3. Bulk update có thể khóa nhiều rows

Một bulk UPDATE 500.000 rows có thể:
- Giữ locks lâu tới commit;
- Tăng transaction log/WAL;
- Chờ các transaction khác;
- Gây deadlock nếu nhiều job update theo những đường không nhất quán;
- Làm chậm queries hoặc replication tùy DB.

Khi bảng lớn, cần lên lịch/chunk và đo trên database mục tiêu; không coi “chỉ một SQL statement” là không tốn tài nguyên.

### 17.4. Chia chunk theo ID khi cần

Một số database hỗ trợ UPDATE LIMIT hoặc RETURNING, nhưng **JPQL bulk UPDATE portable không có LIMIT/ORDER BY**. Có thể:
1. Query một trang IDs theo keyset;
2. Bulk update với WHERE id IN :ids và các điều kiện business;
3. Commit/clear theo boundary được định nghĩa;
4. Chuyển sang trang IDs tiếp theo.

Phải cẩn thận khi update chính thuộc tính dùng để lọc các trang: OFFSET pagination có thể bỏ sót rows khi result set co lại. Keyset theo ID bất biến thường dễ kiểm soát hơn.

### 17.5. Chunk commits không còn all-or-nothing

Nếu mỗi chunk commit riêng:
- Chunk 1 thành công;
- Chunk 2 thành công;
- Chunk 3 thất bại;

hai chunks đầu vẫn được lưu. Cần checkpoint và idempotency. Nếu yêu cầu toàn bộ batch phải atomic, dùng một transaction phù hợp, chấp nhận những trade-offs về locking/log/time.

### 17.6. Retry phải có điều kiện

Câu UPDATE dạng:

~~~java
set status = :expired
where status = :created
~~~

có thể trở thành idempotent ở mức status transition sau commit: chạy lại sẽ không match những rows đã chuyển EXPIRED. Nhưng nếu câu lệnh tăng counter:

~~~java
set retryCount = retryCount + 1
~~~

chạy lại sẽ tăng thêm lần nữa. Khi có timeout không biết commit đã thành công hay chưa, cần idempotency key/checkpoint hoặc điều kiện trạng thái thích hợp, không retry mù quáng.

## 18. Xử lý nhiều bảng, liên kết và cập nhật liên quan

JPQL bulk UPDATE thường nhắm tới một entity type. Nhưng nghiệp vụ có thể yêu cầu thay đổi nhiều bảng đồng thời.

### 18.1. Trường hợp chỉ cập nhật parent status

Nếu SalesOrder chỉ đổi từ CREATED sang EXPIRED và các lines không cần thay đổi, bulk UPDATE SalesOrder có thể phù hợp.

### 18.2. Trường hợp cần xử lý cả child rows

Nếu khi expire phải:
- Đặt reservedQuantity=0 trên từng line;
- Trả hàng vào Product.stock;
- Ghi ledger;
- Tạo notification;

thì một câu bulk UPDATE parent không đủ. Cần một transaction workflow gồm nhiều DML operations hoặc xử lý aggregate với domain methods, bảo đảm invariant toàn bộ.

### 18.3. Những SQL cập nhật liên quan cần thứ tự

Nếu dùng nhiều bulk statements:
1. Update child state;
2. Update parent;
3. Insert audit/outbox;
4. Commit;

thứ tự phụ thuộc FK constraints và nghiệp vụ. Có thể cần kiểm tra affected row counts để phát hiện dữ liệu thiếu/đã đổi. Không dựa vào cascade ORM vì bulk bypass lifecycle.

### 18.4. Không dùng mệnh đề JOIN UPDATE tùy tiện trong JPQL

Một số DB hỗ trợ cú pháp **UPDATE ... FROM ... JOIN**, nhưng JPQL bulk update có grammar hạn chế. Có thể dùng subqueries trong WHERE khi được hỗ trợ:

~~~java
update SalesOrder o
set o.status = :expired
where o.id in (
    select x.id
    from SalesOrder x
    where x.tenantId = :tenantId
      and x.expiresAt < :now
)
~~~

Ví dụ chỉ minh họa subquery, không cần thiết hơn predicate trực tiếp trong trường hợp này. Với update-from-join phức tạp, dùng native SQL nếu đáng và ghi rõ phụ thuộc dialect.

### 18.5. Tránh tổng hợp thông qua join to-many rồi UPDATE sai

Một Order có 3 Lines có thể tạo 3 rows khi JOIN. Một phép tính tổng dựa JOIN mà không group đúng có thể nhân dữ liệu. Nếu bulk DML dựa aggregate, hãy kiểm chứng subquery, join cardinality và constraints để không cập nhật ngoài ý muốn.

## 19. Caches và dữ liệu stale

### 19.1. First-level cache

Persistence context là first-level cache của EntityManager. Bulk DML **không tự đồng bộ các managed instances** tương ứng.

Dùng:
- refresh cho một vài entities;
- clear để detach toàn context;
- transaction-scoped EntityManager mới cho workflow sau bulk.

### 19.2. Second-level cache

Nếu provider bật second-level cache, bulk mutations có thể cần cache invalidation/eviction. Các provider hiện đại có thể tự làm một số bước invalidation cho những DML họ phát, nhưng **không mặc định mọi đường native SQL, procedure hoặc bulk DML sẽ đồng bộ cache theo một cách hoàn toàn portable**.

Cần kiểm tra provider/version và cache configuration. Không coi em.clear() là lệnh xóa L2 cache: clear chỉ ảnh hưởng persistence context.

### 19.3. Query cache

Nếu bật query cache, bulk DML có thể khiến những cached results trước đó stale nếu invalidation không đúng. Trong Hibernate, việc đồng bộ query cache thường liên quan tables/query spaces và provider mechanisms. Với native SQL hoặc thủ tục, cần chú ý khai báo/evict theo cách provider hỗ trợ.

### 19.4. Khi nào không cần bật cache?

Với các bảng trạng thái thay đổi thường xuyên, L2/query cache có thể không đem lại lợi ích như mong đợi. Nên đo hit ratio và invalidation cost, thay vì chỉ thêm eviction mỗi lần bulk update.

## 20. So sánh chi tiết bằng hai service

### 20.1. Service A: per-entity transition

~~~java
@Service
public class OrderExpirationEntityService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public int expireBatch(
            long tenantId, Instant now, int pageSize) {

        List<SalesOrder> orders = em.createQuery(
            """
            select o
            from SalesOrder o
            where o.tenantId = :tenantId
              and o.status = :created
              and o.expiresAt < :now
              and o.archivedAt is null
            order by o.id
            """,
            SalesOrder.class
        )
        .setParameter("tenantId", tenantId)
        .setParameter("created", OrderStatus.CREATED)
        .setParameter("now", now)
        .setMaxResults(pageSize)
        .getResultList();

        for (SalesOrder order : orders) {
            order.expire(now);
        }

        return orders.size();
    }
}
~~~

Ưu điểm:
- Mọi order đi qua expire(now);
- JPA quản lý @Version;
- Có thể sử dụng lifecycle callbacks;
- Có thể thêm logic theo từng Order.

Nhược điểm:
- Load entities;
- UPDATE nhiều rows theo đường ORM;
- Cần tổ chức paging/flush/clear khi chạy trên tập rất lớn;
- @Transactional chỉ bao một page ở ví dụ, không tự xử lý toàn bộ các page.

### 20.2. Service B: bulk transition

~~~java
@Service
public class OrderExpirationBulkService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public int expireAll(
            long tenantId, Instant now) {

        em.flush();

        int affected = em.createQuery(
            """
            update SalesOrder o
            set o.status = :expired,
                o.closedAt = :now,
                o.version = o.version + 1
            where o.tenantId = :tenantId
              and o.status = :created
              and o.expiresAt < :now
              and o.archivedAt is null
            """
        )
        .setParameter("expired", OrderStatus.EXPIRED)
        .setParameter("created", OrderStatus.CREATED)
        .setParameter("tenantId", tenantId)
        .setParameter("now", now)
        .executeUpdate();

        em.clear();
        return affected;
    }
}
~~~

Ưu điểm:
- Không load mỗi SalesOrder;
- Ít Java allocations;
- Một set-based statement có thể xử lý nhiều rows;
- Tăng version thủ công theo policy được mô tả.

Nhược điểm:
- Không gọi expire(now);
- Không chạy entity callbacks;
- Không áp ORM cascade/orphanRemoval;
- Clear ảnh hưởng toàn persistence context;
- Có thể tạo lock/transaction log lớn;
- Vẫn phải bảo đảm business predicates đúng.

### 20.3. Hai service không hoàn toàn tương đương

Dù cùng cho trạng thái EXPIRED và closedAt, EntityService có thể thực thi thêm validations trong expire(now) hoặc listener. BulkService chỉ làm các điều kiện và SET được ghi rõ trong JPQL.

Nếu nghiệp vụ thay đổi (ví dụ phải kiểm tra có payment chưa hoàn tất), cả hai đường ghi phải được cập nhật nhất quán hoặc giới hạn việc gọi bulk trong các trường hợp nghiệp vụ cho phép.

### 20.4. Không phân tích hiệu năng chỉ từ số dòng Java

Một method 10 dòng có thể tạo một SQL rất nặng. Một method 50 dòng có thể thực thi 100 SQL trong một JDBC batch hiệu quả. Hãy đo:
- DB execution plan;
- Số SQL statements và JDBC round trips;
- Row count;
- Heap/GC;
- Locks và transaction duration;
- Tỷ lệ optimistic conflicts;
- Correctness của dữ liệu/audit.

## 21. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
|---|---|---|
| Bulk xong entity vẫn status cũ | Persistence context không được đồng bộ | refresh/clear hoặc context mới |
| find lại vẫn nhận object cũ | Identity map giữ managed instance | clear hoặc refresh trước |
| Sau clear sửa Customer không lưu | Clear detach mọi managed entities | find lại managed Customer |
| Clear trước flush làm mất thay đổi | Pending changes bị detach | flush trước clear |
| em.flush sau bulk không làm object mới | Flush không phải refresh | refresh/clear |
| @PreUpdate không chạy | Bulk bypass JPA callbacks | Chọn per-entity hoặc audit riêng |
| @LastModifiedDate không đổi | Entity listener không được gọi | Set timestamp trong bulk hoặc DB trigger |
| @Version không tăng | Bulk không tự optimistic lock | Tăng version/WHERE version thủ công nếu phù hợp |
| Concurrent update ghi đè | Không có version/status predicate | Dùng conditional UPDATE, version policy |
| Bulk DELETE lỗi FK | Không chạy ORM cascade | Xóa child có chủ đích/DB cascade/per-entity |
| Child @PreRemove không chạy | DB hoặc bulk delete bypass callbacks | Dùng lifecycle hoặc cơ chế audit riêng |
| Query sửa ngoài tenant | WHERE thiếu tenantId | Mandatory security predicate |
| Không loại archived | Thiếu archivedAt IS NULL | Áp policy thống nhất |
| Dùng executeUpdate ngoài transaction | Không có active transaction | @Transactional/transaction boundary |
| executeUpdate trả 500 nhưng rollback | Nhầm affected với committed | Chờ transaction commit |
| getResultList trên UPDATE | Sai API cho mutation | executeUpdate |
| saveAll chậm hơn bulk | saveAll làm persist/merge từng entity | Chọn đúng technique/JDBC batching |
| @Modifying không tự clear | clearAutomatically mặc định false | Bật có chủ đích hoặc quản lý context |
| @Modifying clear làm mất managed work | Clear toàn context | flush trước, thiết kế boundary |
| Derived delete và bulk delete khác nhau | Khác implementation path | Kiểm tra repository method contract |
| JOIN làm COUNT/SUM sai | Nhân rows qua to-many | Đếm đúng entity/grain |
| Bulk không ghi domain event | Không gọi business method | Outbox/audit/flow riêng |
| Retry tăng counter hai lần | DML không idempotent | Status/unique/idempotency key |
| Transaction giữ lock lâu | Bulk quá lớn | Chia chunk nếu nghiệp vụ cho phép |
| OFFSET pagination bỏ sót | Update làm thay đổi bộ lọc | Keyset theo ID |
| DB cache trả dữ liệu cũ | Provider cache invalidation chưa đủ | Kiểm tra L2/query cache |
| Version conflict sau bulk | Entity managed giữ version cũ | refresh/clear, xử lý conflict |
| Soft delete bị thành hard delete | Nhầm UPDATE archivedAt với DELETE | Chọn policy rõ |
| DB constraint thất bại | DML vi phạm FK/CHECK/UNIQUE | Sửa logic/transaction, không tắt constraint |

## 22. Kiểm thử tích hợp: phân biệt hai cơ chế

Unit test chỉ xem chuỗi JPQL được tạo ra không thể chứng minh lifecycle callback, @Version và database state thực tế. Nên có integration test dùng provider/database gần production.

### 22.1. Test managed update đi qua lifecycle

Ví dụ có listener ghi nhận @PreUpdate hoặc audit field đã mapping:
1. Persist SalesOrder CREATED.
2. Flush/clear.
3. Load managed SalesOrder.
4. Gọi expire(now).
5. Flush.
6. Assert status EXPIRED và version thay đổi.
7. Assert callback/audit theo thiết kế.
8. Rollback hoặc dọn fixture.

Không khẳng định callback bắt buộc chạy nếu không có UPDATE thực sự; bảo đảm dữ liệu test tạo ra state transition.

### 22.2. Test bulk cập nhật DB nhưng không cập nhật Java instance

~~~java
@Test
void bulkUpdateLeavesManagedOrderStaleUntilRefresh() {
    SalesOrder managed =
        em.find(SalesOrder.class, testOrderId);

    assertEquals(OrderStatus.CREATED, managed.getStatus());

    int changed = em.createQuery(
        """
        update SalesOrder o
        set o.status = :expired
        where o.id = :id
        """
    )
    .setParameter("expired", OrderStatus.EXPIRED)
    .setParameter("id", testOrderId)
    .executeUpdate();

    assertEquals(1, changed);

    // Bulk DML không tự gọi setter trên managed instance.
    assertEquals(OrderStatus.CREATED, managed.getStatus());

    em.refresh(managed);

    assertEquals(OrderStatus.EXPIRED, managed.getStatus());
}
~~~

Ví dụ giả định JUnit 5, EntityManager trong transaction và fixture testOrderId có status CREATED. Test cho thấy sự tách biệt **DB state** và **managed Java state**.

### 22.3. Test clear sau bulk

~~~java
@Test
void clearAfterBulkDetachesOldReference() {
    SalesOrder old = em.find(
        SalesOrder.class, testOrderId);

    em.createQuery(
        "update SalesOrder o set o.status = :status where o.id = :id"
    )
    .setParameter("status", OrderStatus.EXPIRED)
    .setParameter("id", testOrderId)
    .executeUpdate();

    em.clear();

    assertFalse(em.contains(old));

    SalesOrder reloaded =
        em.find(SalesOrder.class, testOrderId);

    assertNotSame(old, reloaded);
    assertEquals(OrderStatus.EXPIRED, reloaded.getStatus());
}
~~~

### 22.4. Test @Version khác biệt

Tạo SalesOrder version V:
- Update qua managed entity, flush; assert version tăng;
- Reset fixture, bulk UPDATE chỉ status; assert version không tự tăng do bulk;
- Reset fixture, bulk UPDATE với version = version + 1; assert tăng;
- Test một writer giữ snapshot version cũ, cố update sau bulk tăng version; kỳ vọng optimistic conflict theo provider.

Để test concurrency thật, sử dụng hai EntityManagers/transactions độc lập; cùng một persistence context không mô phỏng đúng stale snapshot.

### 22.5. Test entity callback không được gọi bởi bulk

Tạo listener/counter hoặc audit field phù hợp cho test, không dựa vào global mutable state không thread-safe. So sánh:
- Managed update kích hoạt callback;
- Bulk UPDATE không kích hoạt JPA entity callback;
- Database trigger có thể vẫn chạy nếu DB schema có trigger.

### 22.6. Test em.remove cascade và bulk DELETE

Tạo SalesOrder có hai SalesOrderLines:
1. Test em.remove(order) với cascade=ALL, flush; assert parent/children bị xóa theo mapping.
2. Tạo fixture lại; thử bulk DELETE parent khi FK restrict; kỳ vọng DB constraint từ chối, hoặc nếu FK ON DELETE CASCADE thì DB xóa children.
3. Assert child @PreRemove không được gọi bởi DB cascade/bulk DELETE.

Không chạy test bulk DELETE trên database có FK đã bị tắt vì sẽ che lỗi mà production cần ngăn.

### 22.7. Test rollback

Trong một transaction:
1. Bulk UPDATE một tập orders.
2. Nhận affected count.
3. Cố ý rollback.
4. Mở transaction/context mới.
5. Query DB xác minh rows không giữ thay đổi chưa commit.

Không lấy object managed trước rollback làm nguồn sự thật.

### 22.8. Test tenant isolation và status predicates

Fixture gồm:
- Tenant 10 có CREATED quá hạn;
- Tenant 20 có CREATED quá hạn;
- Tenant 10 có CONFIRMED quá hạn;
- Tenant 10 có CREATED chưa quá hạn;
- Tenant 10 có CREATED archived.

Call bulk cho tenant 10 và assert chỉ những rows đúng tenant/status/time/archived được cập nhật. Đây là test quan trọng hơn việc chỉ assert affected > 0.

### 22.9. Test Spring Data @Modifying

Khi dùng @Modifying(clearAutomatically=true, flushAutomatically=true):
- Tải entity managed trước;
- Có pending change khác;
- Gọi modifying query;
- Xác minh flush trước và clear sau theo policy;
- Đảm bảo caller không tiếp tục sửa detached instance;
- Test transaction rollback khi query lỗi.

### 22.10. Test hiệu năng có kiểm soát

Chuẩn bị dataset đủ lớn và đo per-entity + JDBC batching so với bulk update:
- Cùng điều kiện nghiệp vụ và constraints;
- Số rows tương đương;
- Cache/transaction setup được ghi nhận;
- Đo SQL count, execution time, DB load, heap;
- Không lấy một lần chạy nhỏ để khẳng định bulk luôn tốt hơn.

## 23. Bài tập thực hành

### Bài 1. Nhận diện hai cơ chế

Cho:

~~~java
List<SalesOrder> orders = em.createQuery(
    "select o from SalesOrder o where o.status = :status",
    SalesOrder.class
).setParameter("status", OrderStatus.CREATED)
 .getResultList();

orders.forEach(o -> o.expire(now));
~~~

và:

~~~java
em.createQuery(
    "update SalesOrder o set o.status = :status where ..."
).setParameter("status", OrderStatus.EXPIRED)
 .executeUpdate();
~~~

Giải thích khác nhau về số entities được load, dirty checking, @PreUpdate, @Version và business method.

### Bài 2. Viết bulk UPDATE đầy đủ điều kiện

Từ dataset, chỉ expire orders của tenant 10, CREATED, expiresAt trước now, archivedAt NULL. Viết JPQL và setParameters. Dự đoán ID nào được cập nhật.

### Bài 3. Lỗi quên tenant

Một câu bulk UPDATE thiếu **o.tenantId = :tenantId**. Trong dataset, row nào của tenant khác có thể bị sửa? Đề xuất cách buộc service luôn áp scope xác thực.

### Bài 4. WHERE với NULL

Một SalesOrder có expiresAt NULL. Điều kiện **expiresAt < :now** có chọn không? Nếu NULL nghĩa “không bao giờ hết hạn”, logic hiện tại đúng chưa? Giải thích ba giá trị TRUE/FALSE/UNKNOWN.

### Bài 5. Flush trước bulk

Service sửa một managed SalesOrder nhưng chưa flush, sau đó bulk UPDATE cùng bảng. Tại sao thứ tự SQL có thể ảnh hưởng kết quả? Viết flow flush → bulk → clear.

### Bài 6. Clear ảnh hưởng entity ngoài batch

Một Customer managed đã được tải trước bulk Orders. Repository @Modifying(clearAutomatically=true) chạy rồi service tiếp tục sửa Customer. Vì sao thay đổi sau clear có thể không được lưu? Đề xuất cách find lại managed Customer.

### Bài 7. Refresh sau bulk

Một SalesOrder managed có status CREATED. Bulk UPDATE đặt status EXPIRED ở DB. Vì sao em.find cùng ID có thể trả status CREATED? Dùng em.refresh rồi giải thích khác biệt refresh và clear.

### Bài 8. @Version không tự tăng

Với version=5, chạy bulk UPDATE chỉ đổi status. Phiên bản ở DB sẽ thế nào nếu query không set version? So sánh với managed update. Viết một phiên bản bulk có **version = version + 1**.

### Bài 9. Optimistic compare-and-set

Viết bulk UPDATE cho một ID với điều kiện version=:expectedVersion và status=CREATED. Nếu executeUpdate trả 0, có thể do những nguyên nhân nào ngoài version conflict?

### Bài 10. Callbacks và auditing

Một listener @PreUpdate đặt updatedAt. Tại sao bulk UPDATE không làm updatedAt tự đổi theo listener? Hãy viết bulk SET updatedAt=:now và nói rõ nó không thay thế mọi domain audit logic.

### Bài 11. Cascade REMOVE

Một SalesOrder có 3 Lines và cascade=ALL. So sánh em.remove(order) với JPQL delete from SalesOrder. Khi FK restrict, trường hợp nào có thể lỗi? Nếu DB ON DELETE CASCADE, child @PreRemove có chạy không?

### Bài 12. Soft delete

Viết bulk UPDATE đặt archivedAt cho các order ở trạng thái CANCELLED/EXPIRED. Vì sao khác bulk DELETE? Những SELECT sau đó cần filter thế nào để không hiển thị order archived?

### Bài 13. CriteriaUpdate

Dùng CriteriaBuilder.createCriteriaUpdate(SalesOrder.class) đặt status EXPIRED và closedAt=now với tenant/status/expiresAt/archivedAt predicates. Gọi executeUpdate. Nó có dùng dirty checking không?

### Bài 14. CriteriaDelete

Tạo CriteriaDelete<SalesOrder> xóa rows archived trước cutoff. Viết criteria WHERE có tenant. Giải thích vì sao vẫn cần xét FK/cascade.

### Bài 15. Spring Data @Modifying

Khai báo repository method @Query bulk update và @Modifying(flushAutomatically=true, clearAutomatically=true), trả int. Gọi từ @Transactional service. Hai thuộc tính Modifying giải quyết điều gì và **không** giải quyết điều gì?

### Bài 16. saveAll và bulk UPDATE

Vì sao repository.saveAll(List<SalesOrder>) không tương đương một câu JPQL UPDATE? Nếu Hibernate jdbc.batch_size=50, callbacks và version semantics có còn khác bulk không?

### Bài 17. Cập nhật 100.000 rows

So sánh:
1. Load entities, gọi domain methods, flush/clear mỗi 100;
2. Một bulk UPDATE;
3. Các bulk UPDATE theo chunk ID trong nhiều transactions.

Trình bày memory, DB locks, rollback scope, idempotency, validation và tính đúng đắn.

### Bài 18. OFFSET pagination bỏ sót

Một query lấy trang CREATED orders với OFFSET, sau mỗi trang đổi status thành EXPIRED. Vì sao trang kế có thể bỏ sót? Đề xuất keyset pagination theo ID ổn định.

### Bài 19. Business event

Domain method expire() phát domain event; bulk UPDATE không gọi method. Làm sao bảo đảm mỗi transition có event chính xác một lần sau commit? Phác thảo transactional outbox hoặc cơ chế batch event có idempotency.

### Bài 20. Affected count và rollback

Bulk UPDATE trả affected=500 nhưng transaction sau đó rollback. Có bao nhiêu orders được commit? Thiết kế thông báo tiến độ phân biệt matched/affected/flushed/committed.

### Bài 21. Bulk trên nhiều bảng

Hết hạn SalesOrder phải trả reserved stock, đổi status lines và ghi audit. Một bulk UPDATE parent có đủ không? Đề xuất transaction workflow và cách bảo vệ concurrency/constraints.

### Bài 22. To-many JOIN làm sai số liệu

Một Order có 3 Lines và 4 Tags. Query aggregate join cả hai collections rồi tính tổng giá trị order. Vì sao kết quả có thể bị nhân 12 lần? Vì sao SUM(DISTINCT amount) không phải lời giải tổng quát?

### Bài 23. Cache consistency

Bulk UPDATE trong EntityManager đang giữ SalesOrder managed; second-level cache đang bật. Hãy phân biệt tác dụng của em.clear, em.refresh, L2 eviction và provider-specific cache invalidation.

### Bài 24. Lựa chọn theo nghiệp vụ

Chọn giải pháp cho:
- Đánh dấu archived cho một triệu logs đã hết retention;
- Chuyển tiền giữa tài khoản với rule phức tạp;
- Xóa Order có Lines cần @PreRemove audit;
- Expire hàng nghìn Orders theo điều kiện status/time;
- Cập nhật một SalesOrder qua HTTP PATCH với version client;
- Tăng một counter atomically.

Giải thích trade-offs, không chỉ chọn phương án ít dòng code nhất.

### Bài 25. Tự viết integration test

Tạo fixture Orders nhiều tenant/status, một entity managed trước bulk, callback audit và @Version. Thiết kế tests cho:
- Per-entity update và optimistic locking;
- Bulk update affected count;
- Stale managed entity;
- Flush/clear;
- Bulk không chạy callback;
- Manual version increment;
- FK restrict trên bulk DELETE;
- Rollback không commit;
- Tenant isolation.

## 24. Bảng chọn kỹ thuật theo mục tiêu

| Mục tiêu | Kỹ thuật ưu tiên cân nhắc | Lý do |
|---|---|---|
| Sửa một entity theo business method | Load managed + mutate | Domain rules/dirty checking/version |
| Thay đổi nhiều entities nhưng mỗi cái có rule khác | Per-entity theo chunk | Áp invariants/callbacks riêng |
| Chỉ đổi cùng một status trên nhiều rows | JPQL bulk UPDATE | Set-based, tránh load entities |
| Xóa parent có ORM cascades và callbacks | em.remove từng aggregate | Lifecycle đúng mapping |
| Xóa log độc lập rất lớn | Bulk DELETE/chunk SQL | Hiệu quả, không cần managed graph |
| Đánh dấu soft delete | Bulk UPDATE archivedAt hoặc per-entity method | Tùy callbacks/domain policy |
| Một row conditional update theo expectedVersion | Bulk compare-and-set hoặc managed entity | Có version/status predicate rõ |
| Tăng counter theo atomic DB expression | Conditional bulk UPDATE | Tránh read-modify-write race nếu thiết kế đúng |
| Batch SQL với callbacks/@Version | Managed entities + JDBC batching | Tối ưu round trip, giữ lifecycle |
| Có nhiều FK/child rules | Per-entity hoặc DB workflow đã thiết kế | Không dựa vào ORM cascade trong bulk |
| Bulk update động nhiều filter | CriteriaUpdate | Dynamic predicates, vẫn bulk semantics |
| Repository @Query UPDATE/DELETE | @Modifying + @Transactional | Mutation via Spring Data |
| Import/cleanup hàng triệu rows với checkpoint | Chunk transactions + idempotency | Kiểm soát long transactions |
| Cần domain events sau commit | Per-entity/outbox workflow | Bulk không tự phát từng event |
| Dữ liệu có tenant/soft-delete policy | Mandatory WHERE predicates | Tránh sửa ngoài phạm vi |

## 25. Checklist trước khi chạy bulk UPDATE/DELETE

1. **Có thực sự cần bulk không?** Nếu chỉ sửa một entity có domain rule phức tạp, managed update có thể đúng hơn.
2. **Câu DML có WHERE đủ chặt chưa?** Tenant, status, thời gian, archivedAt, quyền truy cập.
3. **NULL semantics đã rõ chưa?** expiresAt NULL không tự nhỏ hơn now.
4. **Có bỏ qua domain method không?** Nếu có invariant nằm trong Java, đã chuyển vào DML hoặc workflow khác chưa?
5. **Có callback/auditing cần chạy không?** Bulk không tự gọi từng entity.
6. **Có quan hệ/cascade/orphanRemoval không?** Bulk DELETE không thay em.remove.
7. **DB FK/CHECK/UNIQUE còn bảo vệ dữ liệu không?** Không tắt constraints để bulk chạy qua.
8. **@Version có được xử lý đúng không?** Bulk không tự optimistic lock.
9. **Có điều kiện expectedVersion/status cần kiểm tra không?** Dùng conditional WHERE và affected count.
10. **Có entities managed trước bulk không?** Nếu có thể stale, chuẩn bị refresh/clear.
11. **Có pending changes trước bulk không?** Flush trước khi clear hoặc khi thứ tự SQL quan trọng.
12. **Clear có làm detach entity ngoài phạm vi không?** Đánh giá side effect toàn context.
13. **Transaction có thực sự active không?** Không chạy executeUpdate ngoài transaction.
14. **Số affected được hiểu đúng không?** Affected chưa phải committed.
15. **Có side effects bên ngoài DB không?** Email/events nên sau commit hoặc outbox.
16. **Có thể rollback đúng không?** Không bắt lỗi rồi tiếp tục transaction invalid.
17. **Có concurrency với những writers khác không?** Version, WHERE predicates, locks, isolation.
18. **Có cần cập nhật cache không?** JPA context, L2, query cache tùy provider.
19. **Có yêu cầu retention/audit không?** Không dùng hard DELETE tùy tiện.
20. **Có bảng rất lớn không?** Locks, WAL/redo, replication, chunking, timeout.
21. **Có dùng Spring Data @Modifying không?** Hiểu flushAutomatically/clearAutomatically.
22. **Có nhầm saveAll/JDBC batching với bulk JPQL không?** Phân biệt lifecycle và SQL shape.
23. **Có dùng CriteriaUpdate/CriteriaDelete đúng giới hạn JPQL không?** Native SQL khi cần dialect-specific.
24. **Có test actual DB state sau bulk không?** Refresh/clear/transaction mới để tránh identity map.
25. **Có test negative cases không?** Wrong tenant, wrong status, NULL, FK, rollback, conflicts.
26. **Có đo hiệu năng trên DB mục tiêu không?** Không tối ưu chỉ từ dự đoán.

## 26. Tổng kết

**Thay đổi từng entity được quản lý** và **thay đổi hàng loạt bằng truy vấn DML** đều có thể ghi UPDATE/DELETE vào cơ sở dữ liệu, nhưng **không có cùng hợp đồng JPA**.

~~~text
Thay đổi từng entity:
    find/query entity
      → managed instance
      → domain method / setter
      → dirty checking
      → JPA callbacks/cascades/version handling phù hợp
      → flush
      → transaction commit

Thay đổi hàng loạt:
    JPQL UPDATE/DELETE hoặc CriteriaUpdate/CriteriaDelete
      → executeUpdate()
      → database xử lý tập rows theo WHERE
      → không đồng bộ managed Java entities
      → không gọi entity callback/cascade từng row
      → không tự áp @Version như managed updates
      → refresh/clear khi cần
      → transaction commit
~~~

**Quy tắc chọn lựa:** nếu cần xử lý lifecycle, validation, callbacks, aggregate rules và optimistic locking tự động của JPA, hãy ưu tiên thay đổi managed entities. Nếu thay đổi có thể biểu diễn chính xác dưới dạng một phép set-based trên nhiều rows, không cần logic từng entity, bulk DML thường hiệu quả và rõ ràng hơn.

Với bulk DML, ghi nhớ đặc biệt **flush trước khi cần bảo toàn pending changes, refresh hoặc clear sau khi các managed entities có thể stale**; đồng thời kiểm soát **@Version, transaction, foreign keys, tenant/soft-delete predicates và affected count**. Chỉ khi những khác biệt này được xử lý có chủ đích, bulk mutation mới là một công cụ tối ưu an toàn thay vì nguồn gây lỗi dữ liệu âm thầm.

