# Nghiệm thu bằng bằng chứng SQL, giao dịch và kiểm thử tính đúng

Một hệ thống JPA không thể được nghiệm thu chỉ bằng câu trả lời **“chạy không lỗi”**. Một endpoint có thể trả HTTP 200 dù dữ liệu chưa commit, một repository test có thể pass nhờ first-level cache, một migration có thể thành công nhưng thiếu constraint, và một trang danh sách có thể trả đúng kết quả với 101 câu SQL thay vì một vài câu SQL.

Đặc biệt trong bài thực hành tổng hợp, sản phẩm cần bàn giao không chỉ là Java code. Người đánh giá cần **bằng chứng có thể kiểm tra lại** để trả lời:

- SQL thực sự được gửi tới database là gì?
- Lược đồ thật có đúng tables, columns, indexes và constraints không?
- Những thay đổi nào đã commit, những thay đổi nào bị rollback?
- Hai giao dịch đồng thời có thể làm tồn kho âm hoặc ghi đè state không?
- JPQL có tôn trọng tenant, ordering, pagination và các điều kiện nghiệp vụ không?
- Các tests có thực sự chạm database và bắt đúng loại lỗi không?
- Có bằng chứng định lượng rằng fetch plan không gây N+1, và hiệu năng nằm trong mức chấp nhận?
- Khi test thất bại, có đủ thông tin để phân biệt lỗi code, schema, hạ tầng và dữ liệu không?

Bài **“Nghiệm thu bằng bằng chứng SQL, giao dịch và kiểm thử tính đúng”**, thuộc chương **Thực hành tổng hợp** của chủ đề **Data Persistence Relational Access ORM JPA**, hướng dẫn xây dựng một **hồ sơ nghiệm thu có thể truy vết** cho tính năng đặt đơn và giữ tồn kho, từ yêu cầu nghiệp vụ đến Java/JPA, SQL, transactions, database constraints, integration tests và kết quả vận hành.

Bài dùng Java 17+, Jakarta Persistence 3.x, PostgreSQL, JUnit 5, Testcontainers và Flyway để minh họa. Các ví dụ Spring Data JPA được đánh dấu riêng. Chúng không bắt buộc người học phải chọn đúng công cụ này: nguyên tắc nghiệm thu áp dụng cho các JPA providers và relational databases khác, với điều chỉnh SQL dialect, locking, transaction manager và ngoại lệ theo thực tế.

**Mục tiêu hoàn thành:** mỗi tiêu chí chấp nhận phải có **một phép kiểm tra phù hợp, bằng chứng đầu ra và kết luận pass/fail**, thay vì chỉ có tuyên bố chung chung.

---

## 1. Nghiệm thu JPA khác kiểm tra ứng dụng khởi động

Giả sử chương trình:

```java
PurchaseOrder order = repository.save(newOrder);

assertNotNull(order.getId());
```

Test pass, nhưng chưa chứng minh:

1. Order đã commit.
2. OrderLines đã được ghi.
3. Inventory đã giảm.
4. Tất cả thay đổi nằm trong **cùng transaction**.
5. Một lỗi sau bước ghi inventory khiến cả Order và Inventory rollback.
6. Cùng `orderNo` không thể bị tạo trùng.
7. Tenant A không xem được đơn Tenant B.
8. Cạnh tranh hai requests không bán vượt tồn kho.
9. Query danh sách không phát N+1.
10. Lược đồ production có đúng ràng buộc.

ID có thể được cấp trước commit, và `save` có thể chỉ thao tác với persistence context. Do đó **“test xanh” chỉ có ý nghĩa trong phạm vi những gì test đã quan sát thật**.

## 2. Ba loại bằng chứng tối thiểu

Một hồ sơ nghiệm thu nên có ba nhóm chính.

| Loại | Cần chứng minh | Ví dụ evidence |
| --- | --- | --- |
| **SQL/schema** | JPA đang chạy SQL đúng, database có cấu trúc đúng | SQL logs có masking, schema catalog, migration history, execution plan |
| **Giao dịch** | Commit/rollback/visibility/locking đúng | Transaction tests, fresh-context JDBC readback, optimistic conflict |
| **Tính đúng** | Business invariants và query contract được bảo vệ | JUnit assertions, DB constraints negative tests, reconciliation queries |

Nhóm thứ tư thường cần thiết trong hệ thống thật là **hiệu năng và vận hành**: SQL count, execution plan, API latency, connection pool, locking và observability.

## 3. Dòng truy vết từ yêu cầu tới bằng chứng

```text
Business requirement
       │
       ▼
Acceptance criterion (AC-ID)
       │
       ▼
Domain invariant / expected result
       │
       ▼
Java/JPA implementation
       │
       ▼
Generated SQL and schema constraints
       │
       ▼
Integration test / concurrency scenario
       │
       ▼
Evidence: SQL, DB state, assertions, metrics
       │
       ▼
PASS / FAIL / BLOCKED with reproducible details
```

Một tiêu chí thiếu bằng chứng không nên được tự động đánh dấu pass chỉ vì test khác chạy thành công.

## 4. Nguyên tắc đánh giá bằng chứng

**Bằng chứng tốt** có những thuộc tính:

- **Gắn một tiêu chí cụ thể:** biết bằng chứng dùng cho AC nào.
- **Có thể tái lập:** ghi test version, database version và fixture.
- **Quan sát đúng tầng:** DB constraints bằng DB tests, transaction bằng commit/rollback thật.
- **Có negative cases:** cố tình tạo điều kiện sai để chứng minh hệ thống từ chối.
- **Đủ độc lập:** không lấy L1 cache làm đại diện cho committed DB.
- **Giới hạn rõ:** PostgreSQL-specific behavior không được tuyên bố portable tuyệt đối.
- **Không lộ dữ liệu nhạy cảm:** che passwords, credentials, PII và payloads không cần thiết.
- **Có outcome:** expected vs actual, pass/fail, nguyên nhân, người chịu trách nhiệm.

Kết quả “không ném exception” chỉ là một quan sát; nó không mặc nhiên chứng minh đúng nghiệp vụ.

---

## 5. Bối cảnh thực hành: Đặt đơn và giữ tồn kho

Hệ thống nhiều tenant cho phép khách hàng đặt một sản phẩm theo số lượng. Khi đặt đơn:

1. Kiểm tra tenant hợp lệ và product đang tồn tại.
2. Kiểm tra quantity dương.
3. Đảm bảo không bán vượt tồn kho.
4. Giảm `availableQuantity`.
5. Tạo Order có một OrderLine.
6. Tính `totalAmount = quantity × unitPrice`.
7. Đánh dấu Order đã xác nhận.
8. Commit Order và Inventory **cùng giao dịch**.
9. Nếu bất kỳ bước nào lỗi, không lưu dữ liệu nửa chừng.
10. Không cho phép tạo hai Orders cùng `(tenantId, orderNo)`.

Để tập trung vào kiểm thử JPA, ví dụ xử lý **một sản phẩm trên một lần đặt**. Bài tập cuối mở rộng sang nhiều sản phẩm, lock ordering và idempotency ở hệ thống phân tán.

### Sơ đồ aggregate và lưu trữ

```text
Command: PlaceOrder(tenant, orderNo, inventoryItem, quantity)
                 │
                 ▼
         OrderApplicationService
                 │ transaction
       ┌─────────┴──────────┐
       │                    │
       ▼                    ▼
 InventoryItem           PurchaseOrder
 (stock aggregate)       (order aggregate)
 availableQuantity         totalAmount, state
 version                   version
                            │
                            ▼
                         OrderLine
                         productCode, quantity,
                         unitPrice
       │                    │
       └─────────┬──────────┘
                 ▼
          One database commit
          or one rollback
```

Inventory và Order là hai aggregate roots khác nhau, nhưng use case này cần một **single local DB transaction** vì cả hai bảng nằm trên cùng primary database và cùng transaction manager. Nếu Inventory là một microservice riêng, không được giả định JPA transaction tự bao phủ HTTP call tới service đó; khi ấy cần workflow saga/outbox/idempotency và một consistency contract khác.

## 6. Business invariants phải viết trước code

Các bất biến định nghĩa rõ:

- `quantity > 0`.
- `availableQuantity >= 0` sau mọi committed reservation.
- Mỗi OrderLine có `quantity > 0` và `unitPrice >= 0`.
- `totalAmount` bằng tổng Lines với `BigDecimal`.
- `orderNo` duy nhất trong cùng tenant.
- `tenantId` của Order và InventoryItem phải trùng.
- Không sửa Order sau khi state đã `CONFIRMED` nếu workflow không cho phép.
- Một Order đã commit phải có ít nhất một OrderLine.
- Order và Inventory debit phải commit/rollback cùng nhau.
- Những stale updates phải bị phát hiện theo concurrency policy.
- List/query phải giới hạn tenant và sort ổn định.

**Độ đúng ở tầng Java và integrity trong database bổ trợ nhau.** Validation trước DB giúp báo lỗi dễ hiểu; database UNIQUE, CHECK và FK bảo vệ cả những writers khác ORM.

## 7. Ma trận tiêu chí nghiệm thu mẫu

| ID | Tiêu chí | Bằng chứng cần có |
| --- | --- | --- |
| AC-01 | Đặt đơn hợp lệ tạo Order và Line, giảm Inventory đúng | Commit + JDBC readback cả ba bảng |
| AC-02 | Quantity không hợp lệ không tạo thay đổi | Domain negative test + DB state |
| AC-03 | Không đủ tồn kho thì không có Order | Domain failure + rollback readback |
| AC-04 | Lỗi sau khi trừ tồn kho rollback toàn bộ | Fault injection + two-table reconciliation |
| AC-05 | OrderNo không trùng trong tenant | UNIQUE catalog + duplicate SQLState test |
| AC-06 | Hai tenants có thể dùng cùng orderNo | Cross-tenant integration test |
| AC-07 | Query không lộ Order của tenant khác | JPQL + cross-tenant fixtures |
| AC-08 | Database FK/CHECK chặn dữ liệu sai | Negative JDBC tests + cause/SQLState |
| AC-09 | Two concurrent orders không oversell | Lock/concurrency test + final stock invariant |
| AC-10 | Stale update không ghi đè Order | `@Version` conflict test |
| AC-11 | List page đúng, sort ổn định | Multi-page fixtures + SQL order/limit evidence |
| AC-12 | Không có N+1 ngoài budget | SQL count khi N tăng và read DTO |
| AC-13 | Schema và migrations khớp mappings | Flyway history + schema catalog + Hibernate validate |
| AC-14 | Query hot nằm trong performance budget | Actual plan, representative workload, latency metrics |
| AC-15 | Các tests độc lập, CI chạy lặp lại được | Disposable DB + deterministic fixtures |

AC-14 cần **budget do dự án xác định**. Không tự đặt một SLA chung cho mọi môi trường; một bài thực hành có thể ghi target là giả định và phân biệt rõ với SLO thực tế.

## 8. Định nghĩa điều kiện nghiệm thu trước khi thực hiện

Một mô tả AC nên có cấu trúc:

```text
ID: AC-04
Given: tồn kho item #77 = 5; chưa có orderNo "PO-FAIL"
When: service đã thay đổi stock trong transaction
      nhưng gặp lỗi trước commit
Then: database committed inventory vẫn bằng 5
      và không có purchase order/line mới
Evidence:
  - Test class/method
  - SQL transaction trace (đã ẩn bind PII)
  - Independent new-connection readback
  - Expected/actual values
Environment:
  - PostgreSQL version, Hibernate version, migration version
```

Tránh mô tả mơ hồ kiểu **“rollback hoạt động”** vì không biết thao tác nào đã được rollback và bằng chứng quan sát ở đâu.

---

## 9. Lược đồ PostgreSQL cho bài thực hành

Ví dụ migration `V1__create_order_inventory.sql`:

```sql
CREATE TABLE inventory_items (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    product_code VARCHAR(64) NOT NULL,
    available_quantity INTEGER NOT NULL,
    unit_price NUMERIC(14, 2) NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT uq_inventory_tenant_product
        UNIQUE (tenant_id, product_code),
    CONSTRAINT ck_inventory_nonnegative_stock
        CHECK (available_quantity >= 0),
    CONSTRAINT ck_inventory_nonnegative_price
        CHECK (unit_price >= 0)
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    order_no VARCHAR(64) NOT NULL,
    state VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    total_amount NUMERIC(14, 2) NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT uq_orders_tenant_no
        UNIQUE (tenant_id, order_no),
    CONSTRAINT ck_order_total_nonnegative
        CHECK (total_amount >= 0),
    CONSTRAINT ck_order_state
        CHECK (state IN ('DRAFT', 'CONFIRMED'))
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_code VARCHAR(64) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(14, 2) NOT NULL,
    CONSTRAINT fk_order_line_order
        FOREIGN KEY (order_id) REFERENCES purchase_orders(id),
    CONSTRAINT ck_order_line_quantity
        CHECK (quantity > 0),
    CONSTRAINT ck_order_line_price
        CHECK (unit_price >= 0)
);

CREATE INDEX idx_orders_tenant_created_id
ON purchase_orders (
    tenant_id,
    created_at DESC,
    id DESC
);

CREATE INDEX idx_lines_order_id
ON order_lines(order_id);
```

Ràng buộc UNIQUE theo tenant cho phép cùng `order_no` ở hai tenants, nhưng cấm trùng trong một tenant. CHECK tồn kho âm bảo vệ cả khi một writer không đi qua Java business method.

Các index là **candidates theo query patterns**; với production cần đọc actual execution plan và write overhead. Không tạo indexes chỉ vì ví dụ đã minh họa.

## 10. Bằng chứng migration cần có

Bằng chứng AC-13 có thể gồm:

```sql
SELECT installed_rank, version, description, success
FROM flyway_schema_history
ORDER BY installed_rank;
```

Và catalog:

```sql
SELECT
    c.conname,
    c.contype,
    pg_get_constraintdef(c.oid) AS definition,
    c.convalidated
FROM pg_constraint c
JOIN pg_class t ON t.oid = c.conrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname = 'public'
  AND t.relname IN (
      'inventory_items',
      'purchase_orders',
      'order_lines'
  )
ORDER BY t.relname, c.conname;
```

Kèm:

```sql
SELECT schemaname, tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN (
      'inventory_items',
      'purchase_orders',
      'order_lines'
  )
ORDER BY tablename, indexname;
```

Lưu ý: `pg_catalog` và `pg_indexes` là PostgreSQL-specific; `flyway_schema_history` có thể ở schema khác theo config. **Bằng chứng phải lấy trên đúng database/schema nơi ứng dụng đang kết nối**, không phải database test khác tình cờ có table giống tên.

## 11. Hibernate `validate` không kiểm toán toàn bộ schema

Có thể dùng:

```properties
hibernate.hbm2ddl.auto=validate
```

để provider kiểm tra một số khía cạnh entity mapping và database schema. Nhưng nó thường **không xác minh tất cả**:

- CHECK expression.
- UNIQUE composite rule.
- FK actions.
- Partial indexes.
- Trigger behavior.
- Collation.
- Row-level security.
- Migration history.
- Sequence state.

Nghiệm thu AC-13 vì vậy cần **Flyway/migration evidence, schema-catalog evidence và targeted behavior tests**. Một startup thành công hoặc `validate` không lỗi chưa đủ.

---

## 12. Entity `InventoryItem` với optimistic version

```java
package com.example.checkout;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.util.Objects;

@Entity
@Table(name = "inventory_items")
public class InventoryItem {

    @Id
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "product_code", nullable = false)
    private String productCode;

    @Column(name = "available_quantity", nullable = false)
    private int availableQuantity;

    @Column(name = "unit_price", nullable = false,
            precision = 14, scale = 2)
    private BigDecimal unitPrice;

    @Version
    @Column(name = "version", nullable = false)
    private Long version;

    protected InventoryItem() {}

    public InventoryItem(
            Long id,
            Long tenantId,
            String productCode,
            int availableQuantity,
            BigDecimal unitPrice) {

        if (availableQuantity < 0) {
            throw new IllegalArgumentException(
                "Stock cannot be negative"
            );
        }
        if (unitPrice == null ||
                unitPrice.signum() < 0) {
            throw new IllegalArgumentException(
                "Price cannot be negative"
            );
        }

        this.id = Objects.requireNonNull(id);
        this.tenantId = Objects.requireNonNull(tenantId);
        this.productCode =
            Objects.requireNonNull(productCode);
        this.availableQuantity = availableQuantity;
        this.unitPrice = unitPrice;
    }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive"
            );
        }

        if (availableQuantity < quantity) {
            throw new InsufficientStockException(
                "Available stock is insufficient"
            );
        }

        availableQuantity -= quantity;
    }

    public Long getId() {
        return id;
    }

    public Long getTenantId() {
        return tenantId;
    }

    public String getProductCode() {
        return productCode;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }

    public int getAvailableQuantity() {
        return availableQuantity;
    }

    public Long getVersion() {
        return version;
    }
}
```

`InsufficientStockException` là một custom unchecked exception. Đối với bài thực hành, có thể định nghĩa:

```java
package com.example.checkout;

public class InsufficientStockException
        extends RuntimeException {

    public InsufficientStockException(String message) {
        super(message);
    }
}
```

Trong ứng dụng thật có thể dùng domain error codes thay vì message text để map sang API response.

### Evidence kỳ vọng

Khi số lượng hợp lệ, Inventory giảm và version được cập nhật theo provider semantics ở flush/commit. Khi quantity quá lớn, domain method ném lỗi trước khi giảm stock và transaction phải rollback các thay đổi khác trong cùng unit of work.

**`@Version` không thay database CHECK**, và CHECK không tự ngăn lost update nếu một đường ghi bỏ qua locking/version checks.

## 13. Entity `PurchaseOrder` là aggregate root

```java
package com.example.checkout;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "order_no", nullable = false)
    private String orderNumber;

    @Enumerated(EnumType.STRING)
    @Column(name = "state", nullable = false)
    private OrderState state = OrderState.DRAFT;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "total_amount", nullable = false,
            precision = 14, scale = 2)
    private BigDecimal totalAmount = BigDecimal.ZERO;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    @Version
    @Column(name = "version", nullable = false)
    private Long version;

    protected PurchaseOrder() {}

    public PurchaseOrder(
            Long tenantId,
            String orderNumber,
            Instant createdAt) {
        this.tenantId = Objects.requireNonNull(tenantId);
        this.orderNumber =
            Objects.requireNonNull(orderNumber);
        this.createdAt = Objects.requireNonNull(createdAt);
    }

    public void addLine(
            String productCode,
            int quantity,
            BigDecimal unitPrice) {

        ensureDraft();

        OrderLine line = new OrderLine(
            this, productCode, quantity, unitPrice
        );
        lines.add(line);
        totalAmount = totalAmount.add(line.lineTotal());
    }

    public void confirm() {
        ensureDraft();
        if (lines.isEmpty()) {
            throw new IllegalStateException(
                "Cannot confirm empty order"
            );
        }
        state = OrderState.CONFIRMED;
    }

    private void ensureDraft() {
        if (state != OrderState.DRAFT) {
            throw new IllegalStateException(
                "Confirmed order is immutable"
            );
        }
    }

    public Long getId() { return id; }
    public Long getTenantId() { return tenantId; }
    public String getOrderNumber() { return orderNumber; }
    public OrderState getState() { return state; }
    public Instant getCreatedAt() { return createdAt; }
    public BigDecimal getTotalAmount() {
        return totalAmount;
    }
    public Long getVersion() { return version; }
}
```

Enum:

```java
public enum OrderState {
    DRAFT,
    CONFIRMED
}
```

Ở đây thêm line tính total và root kiểm tra state. Domain invariants còn có thể bao gồm currency, tax, discounts, promotions và rounding policy; với bài tập chúng được giữ đơn giản và **không được suy là logic thanh toán production hoàn chỉnh**.

## 14. Owned child `OrderLine`

```java
package com.example.checkout;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.util.Objects;

@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "product_code", nullable = false)
    private String productCode;

    @Column(nullable = false)
    private int quantity;

    @Column(name = "unit_price", nullable = false,
            precision = 14, scale = 2)
    private BigDecimal unitPrice;

    protected OrderLine() {}

    OrderLine(
            PurchaseOrder order,
            String productCode,
            int quantity,
            BigDecimal unitPrice) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive"
            );
        }
        if (unitPrice == null ||
                unitPrice.signum() < 0) {
            throw new IllegalArgumentException(
                "Price must be nonnegative"
            );
        }

        this.order = Objects.requireNonNull(order);
        this.productCode =
            Objects.requireNonNull(productCode);
        this.quantity = quantity;
        this.unitPrice = unitPrice;
    }

    public BigDecimal lineTotal() {
        return unitPrice.multiply(
            BigDecimal.valueOf(quantity)
        );
    }

    public Long getId() { return id; }
    public String getProductCode() { return productCode; }
    public int getQuantity() { return quantity; }
    public BigDecimal getUnitPrice() {
        return unitPrice;
    }
}
```

`cascade = ALL` và `orphanRemoval = true` được sử dụng vì OrderLine thuộc vòng đời của PurchaseOrder trong mô hình ví dụ. Không áp cascade REMOVE bừa bãi tới Product/Customer/Inventory là các aggregate độc lập.

## 15. Lược đồ và entity phải khớp nhưng không phải cùng một thứ

`@Column(nullable=false)` là metadata ORM; **constraint database phải thật sự tồn tại**. `@Version` cho phép optimistic locking với managed entity writes; **bulk JPQL/native SQL có thể không tự tuân thủ version behavior theo cách thông thường**. `@OneToMany(cascade=ALL)` mô tả lifecycle; SQL FK bảo vệ referential integrity.

Một bảng evidence nên thể hiện:

| Invariant | Java/JPA | Database |
| --- | --- | --- |
| Quantity dương | `reserve`/`OrderLine` constructor | CHECK quantity |
| Stock không âm | `InventoryItem.reserve` | CHECK available_quantity |
| Unique orderNo/tenant | Error handling/pre-check tùy chọn | UNIQUE(tenant_id,order_no) |
| Line phải thuộc Order | Owned child relationship | FK order_id |
| Version-aware update | `@Version` | version column + provider SQL |
| Order total hợp lệ | `PurchaseOrder.addLine` | CHECK total nonnegative; test sum invariant |
| Tenant isolation | Repository predicate/authorization | Tenant fields, optional RLS |

Không cố thay thế mọi business invariant bằng CHECK khi invariant đòi đọc nhiều rows; JPA/domain logic và concurrency policy vẫn cần có.

---

## 16. Application use case: một transaction cho Order và Inventory

Một implementation dùng Jakarta Persistence/resource-local transaction boundary do caller sở hữu:

```java
package com.example.checkout;

import jakarta.persistence.EntityManager;
import jakarta.persistence.LockModeType;
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public final class OrderPlacement {

    private final Clock clock;

    public OrderPlacement(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    // Caller phải mở transaction trước khi gọi method.
    public Long place(
            EntityManager em,
            Long tenantId,
            Long inventoryId,
            String orderNo,
            int quantity) {

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive"
            );
        }

        InventoryItem stock = em.createQuery(
            "SELECT s FROM InventoryItem s " +
            "WHERE s.id = :id AND s.tenantId = :tenant",
            InventoryItem.class
        )
        .setParameter("id", inventoryId)
        .setParameter("tenant", tenantId)
        .setLockMode(LockModeType.PESSIMISTIC_WRITE)
        .getSingleResult();

        stock.reserve(quantity);

        PurchaseOrder order = new PurchaseOrder(
            tenantId,
            orderNo,
            Instant.now(clock)
        );

        order.addLine(
            stock.getProductCode(),
            quantity,
            stock.getUnitPrice()
        );
        order.confirm();

        em.persist(order);
        em.flush();

        return order.getId();
    }
}
```

Điểm thiết kế:

- Caller có transaction active bao toàn bộ thao tác.
- `PESSIMISTIC_WRITE` được yêu cầu khi query tồn kho để giảm nguy cơ oversell dưới cạnh tranh.
- Query luôn chứa `tenantId`.
- `stock.reserve` kiểm tra và giảm số lượng **trong managed entity**.
- Order có một child line được cascade persist.
- `em.flush()` giúp bộc lộ SQL/constraint errors trước khi method trả về, nhưng **chưa phải commit**.
- Nếu commit fail, caller phải rollback/close context theo contract và không coi ID đã trả là bằng chứng lưu thành công.

Trong Spring, caller sẽ là application service `@Transactional`; method trong ví dụ không nên tự mở thêm `EntityManager` không thuộc transaction manager của Spring.

## 17. Tại sao `flush()` không phải bằng chứng commit?

Timeline:

```text
BEGIN
   │
SELECT inventory FOR UPDATE
   │
Java: stock.availableQuantity -= quantity
   │
JPA: persist(order), cascade line
   │
FLUSH
   │
SQL: INSERT purchase_orders
SQL: INSERT order_lines
SQL: UPDATE inventory_items ...
   │
   ├── COMMIT   → các rows/stock mới committed
   │
   └── ROLLBACK → Order/Lines biến mất,
                  Inventory giữ giá trị cũ
```

Đối với `IDENTITY`, Hibernate có thể INSERT sớm trong quá trình persist để lấy generated ID. Provider có quyền sắp lịch SQL khác minh họa; **bằng chứng transaction phải xác minh committed outcome**, không dựa vào thứ tự log giả định.

## 18. Transaction helper cho kiểm thử RESOURCE_LOCAL

```java
static <T> T inTransaction(
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
            } catch (RuntimeException rollbackFailure) {
                failure.addSuppressed(rollbackFailure);
            }
        }
        throw failure;
    } finally {
        em.close();
    }
}
```

Imports liên quan: `jakarta.persistence.*` và `java.util.function.Function`.

Helper này bao `commit()` trong vùng catch để lỗi xuất hiện tại transaction completion cũng được cleanup. Nó bắt `Error` trong môi trường kiểm thử để rollback khi JUnit assertion fail bên trong callback; production code có thể có error-handling policy khác. Nếu commit outcome không xác định vì mất kết nối sau khi DB đã commit, không được khẳng định mọi exception luôn đồng nghĩa rollback; trường hợp đó cần idempotency và readback.

## 19. Đọc committed state bằng connection độc lập

Một readback trực tiếp qua JDBC:

```java
static int readAvailableStock(
        DataSource ds,
        long inventoryId) throws SQLException {

    String sql =
        "SELECT available_quantity " +
        "FROM inventory_items WHERE id = ?";

    try (Connection connection = ds.getConnection();
         PreparedStatement statement =
             connection.prepareStatement(sql)) {

        statement.setLong(1, inventoryId);

        try (ResultSet rows = statement.executeQuery()) {
            if (!rows.next()) {
                throw new AssertionError(
                    "Missing inventory item: " + inventoryId
                );
            }
            return rows.getInt(1);
        }
    }
}
```

Imports `javax.sql.DataSource` và `java.sql.*`.

Đọc bằng một connection mới trên primary với isolation phù hợp giúp giảm nguy cơ lẫn lộn với JPA first-level cache. Nếu dùng read replica, phải tính replication lag; nếu test đọc trong transaction giữ snapshot cũ, kết quả cũng có thể khác dù writer đã commit.

## 20. Kết luận nào chỉ cần EntityManager mới, kết luận nào nên dùng JDBC?

| Mục tiêu | Đường quan sát phù hợp |
| --- | --- |
| JPA mapping có thể load entity sau commit | EntityManager mới |
| DB row/column committed chính xác | JDBC connection mới |
| Lazy associations hoạt động | EntityManager còn mở trong test |
| UNIQUE/FK/CHECK tồn tại | DB negative SQL tests + catalog |
| L2 cache không che state | JDBC hoặc test cache policy |
| Commit/rollback service Spring | New transaction/context ngoài outer test transaction |
| Query list dùng đúng projection | DTO query + SQL capture |
| Optimistic conflict | Hai EMs, transactions và fresh readback |

Không có nghĩa phải dùng JDBC trong mọi assertion. Chọn đường quan sát tương ứng **đúng điều cần chứng minh**.

---

## 21. Setup JUnit 5 + PostgreSQL Testcontainers

Một fixture Java SE:

```java
@Testcontainers
class CheckoutAcceptanceIT {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    private static EntityManagerFactory emf;
    private static DataSource dataSource;

    private static final Clock FIXED_CLOCK =
        Clock.fixed(
            Instant.parse("2026-01-02T03:04:05Z"),
            ZoneOffset.UTC
        );

    @BeforeAll
    static void start() {
        Flyway.configure()
            .dataSource(
                postgres.getJdbcUrl(),
                postgres.getUsername(),
                postgres.getPassword()
            )
            .locations("classpath:db/migration")
            .load()
            .migrate();

        Map<String, Object> props = Map.of(
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
            "checkout-test", props
        );

        PGSimpleDataSource pg = new PGSimpleDataSource();
        pg.setURL(postgres.getJdbcUrl());
        pg.setUser(postgres.getUsername());
        pg.setPassword(postgres.getPassword());
        dataSource = pg;
    }

    @AfterAll
    static void stop() {
        if (emf != null) {
            emf.close();
        }
    }
}
```

Đoạn code là skeleton cần đặt trong test class, thêm imports `java.time.*`, `java.util.Map`, `jakarta.persistence.*`, JUnit/Testcontainers/Flyway/PostgreSQL datasource. `PGSimpleDataSource` thuộc PostgreSQL JDBC driver. JUnit extension quản lý container static; factory đóng trước container stop.

Cần có `src/test/resources/META-INF/persistence.xml` với persistence unit `checkout-test`, `RESOURCE_LOCAL` và khai báo ba entity `InventoryItem`, `PurchaseOrder`, `OrderLine`. Migration nằm trong classpath `db/migration`.

**Không dùng JDBC URL production** để chạy fixture có `DELETE`, `TRUNCATE` hoặc schema creation.

## 22. Persistence unit test tối thiểu

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    version="3.1">

    <persistence-unit
        name="checkout-test"
        transaction-type="RESOURCE_LOCAL">

        <provider>
            org.hibernate.jpa.HibernatePersistenceProvider
        </provider>

        <class>com.example.checkout.InventoryItem</class>
        <class>com.example.checkout.PurchaseOrder</class>
        <class>com.example.checkout.OrderLine</class>

        <exclude-unlisted-classes>true</exclude-unlisted-classes>

        <properties>
            <property
                name="hibernate.hbm2ddl.auto"
                value="validate"/>
        </properties>
    </persistence-unit>
</persistence>
```

JDBC connection values được truyền khi bootstrap trong test fixture. Đừng hardcode `localhost:5432` hoặc credential production vào test XML.

Hệ thống dùng Spring Boot thường để Spring sở hữu `DataSource`, `EntityManagerFactory`, Flyway và transaction manager; không tạo factory RESOURCE_LOCAL song song rồi tưởng đã test đúng Spring-managed repository.

## 23. Dữ liệu fixture phải có định danh rõ

Ví dụ seed một StockItem:

```java
static void seedStock(
        EntityManagerFactory emf,
        long id,
        long tenantId,
        int available) {

    inTransaction(emf, em -> {
        em.persist(new InventoryItem(
            id,
            tenantId,
            "SKU-" + id,
            available,
            new BigDecimal("12.50")
        ));
        return null;
    });
}
```

Mỗi test nên có dữ liệu riêng hoặc reset đúng phạm vi.

Với một test class dùng static container:

- Các methods có thể dùng cùng schema.
- `@BeforeEach` cleanup phải xét FK child-before-parent.
- Nếu tests chạy parallel, global cleanup có thể xóa fixture của test khác.
- Dữ liệu có ID giống nhau không nên rò giữa methods.
- Có thể dùng database/schema per class hoặc per test nếu cần isolation mạnh.

Không làm một test “pass khi chạy sau test A, fail khi chạy riêng”.

---

## 24. AC-01: Đặt đơn hợp lệ phải commit đồng bộ

Given Stock #77 của Tenant #7 có số lượng 10. When đặt quantity=3 với orderNo `ORD-001`. Then:

- Tồn kho committed còn 7.
- Order `ORD-001` committed.
- Order có đúng một line quantity=3.
- Total = 37.50.
- Order state = CONFIRMED.
- Order/Line/Inventory nằm trong cùng transaction outcome.

Mẫu test:

```java
@Test
void placingOrderCommitsOrderLineAndInventory() {
    seedStock(emf, 77L, 7L, 10);

    OrderPlacement useCase =
        new OrderPlacement(FIXED_CLOCK);

    Long orderId = inTransaction(
        emf,
        em -> useCase.place(
            em, 7L, 77L, "ORD-001", 3
        )
    );

    assertEquals(
        7, readAvailableStock(dataSource, 77L)
    );

    EntityManager reader = emf.createEntityManager();
    try {
        PurchaseOrder order =
            reader.find(PurchaseOrder.class, orderId);

        assertNotNull(order);
        assertEquals(
            OrderState.CONFIRMED,
            order.getState()
        );
        assertEquals(
            0,
            order.getTotalAmount().compareTo(
                new BigDecimal("37.50")
            )
        );
    } finally {
        reader.close();
    }

    // Thêm JDBC assertion đếm đúng 1 line,
    // order_id = orderId, quantity = 3.
}
```

Đoạn test minh họa kết hợp service transaction, JDBC stock readback và fresh JPA context. Phần line assertion phải được triển khai như test statement cụ thể; **không đánh dấu AC-01 pass hoàn toàn nếu chưa kiểm chứng child row**, vì yêu cầu bao cả OrderLine.

### SQL bằng chứng AC-01

Một tập query kiểm tra trực tiếp:

```sql
SELECT id, tenant_id, order_no, state,
       total_amount, version
FROM purchase_orders
WHERE tenant_id = 7
  AND order_no = 'ORD-001';

SELECT l.order_id, l.product_code,
       l.quantity, l.unit_price
FROM order_lines l
JOIN purchase_orders o ON o.id = l.order_id
WHERE o.tenant_id = 7
  AND o.order_no = 'ORD-001';

SELECT id, tenant_id, product_code,
       available_quantity, version
FROM inventory_items
WHERE id = 77
  AND tenant_id = 7;
```

Không chỉ lưu một screenshot query result. Ghi context fixture (stock trước=10), transaction completion, actual row values và các assertions.

## 25. AC-02: Quantity không hợp lệ

```java
@Test
void zeroQuantityDoesNotChangeData() {
    seedStock(emf, 78L, 7L, 10);

    OrderPlacement useCase =
        new OrderPlacement(FIXED_CLOCK);

    assertThrows(
        IllegalArgumentException.class,
        () -> inTransaction(
            emf,
            em -> useCase.place(
                em, 7L, 78L, "ORD-ZERO", 0
            )
        )
    );

    assertEquals(
        10,
        readAvailableStock(dataSource, 78L)
    );

    assertEquals(
        0L,
        countOrdersByNumber(dataSource, 7L, "ORD-ZERO")
    );
}
```

`countOrdersByNumber` là test helper dùng parameterized JDBC SQL:

```java
static long countOrdersByNumber(
        DataSource ds,
        long tenantId,
        String orderNo) throws SQLException {

    String sql =
        "SELECT COUNT(*) FROM purchase_orders " +
        "WHERE tenant_id = ? AND order_no = ?";

    try (Connection c = ds.getConnection();
         PreparedStatement st = c.prepareStatement(sql)) {

        st.setLong(1, tenantId);
        st.setString(2, orderNo);

        try (ResultSet rows = st.executeQuery()) {
            rows.next();
            return rows.getLong(1);
        }
    }
}
```

**Một exception duy nhất chưa đủ**; phải kiểm tra dữ liệu cuối cùng không thay đổi ngoài ý định.

## 26. AC-03: Không đủ tồn kho

Given available=2, when đặt quantity=3.

```java
@Test
void insufficientStockRejectsOrder() {
    seedStock(emf, 79L, 7L, 2);

    OrderPlacement useCase =
        new OrderPlacement(FIXED_CLOCK);

    assertThrows(
        InsufficientStockException.class,
        () -> inTransaction(
            emf,
            em -> useCase.place(
                em, 7L, 79L, "ORD-TOO-MUCH", 3
            )
        )
    );

    assertEquals(
        2,
        readAvailableStock(dataSource, 79L)
    );

    assertEquals(
        0L,
        countOrdersByNumber(
            dataSource, 7L, "ORD-TOO-MUCH"
        )
    );
}
```

Điểm cần phân biệt: invariant Java chặn request trước thay đổi state, nhưng **database CHECK vẫn phải được nghiệm thu độc lập** với đường viết bypass JPA nếu muốn chứng minh storage integrity.

## 27. AC-04: Fault injection sau trừ tồn kho

Đây là test atomicity rõ hơn insufficient stock, vì state đã bị sửa trong persistence context trước khi gặp lỗi.

```java
static final class SimulatedFailure
        extends RuntimeException {}

@Test
void failureAfterStockUpdateRollsBackEverything() {
    seedStock(emf, 80L, 7L, 8);

    assertThrows(
        SimulatedFailure.class,
        () -> inTransaction(emf, em -> {
            InventoryItem stock =
                em.find(InventoryItem.class, 80L);

            stock.reserve(3);
            em.flush(); // Gửi UPDATE trong transaction.

            throw new SimulatedFailure();
        })
    );

    assertEquals(
        8,
        readAvailableStock(dataSource, 80L)
    );
}
```

Test này chứng minh `UPDATE inventory` đã flush nhưng không committed. Để nghiệm thu **atomicity giữa Order và Inventory**, nên có fault-injection hook ở một vị trí sau khi cả Order/Line và stock được chuẩn bị, sau đó `flush` và ném exception, rồi assert cả ba bảng không có partial writes.

Không nên thêm những hooks kiểu `forceFailure()` vào production domain model vô điều kiện. Có thể dùng test-only orchestration, interceptor hoặc một collaborator injectable để tạo lỗi tại mốc hợp lệ.

## 28. AC-04 nâng cao: rollback sau khi đã flush Order và Line

Một test-only transaction trực tiếp:

```java
@Test
void flushOfOrderAndStockStillRollsBack() {
    seedStock(emf, 81L, 7L, 8);

    assertThrows(
        SimulatedFailure.class,
        () -> inTransaction(emf, em -> {
            InventoryItem stock =
                em.find(InventoryItem.class, 81L);

            stock.reserve(3);

            PurchaseOrder order = new PurchaseOrder(
                7L,
                "ORD-ROLLBACK",
                Instant.now(FIXED_CLOCK)
            );

            order.addLine(
                stock.getProductCode(),
                3,
                stock.getUnitPrice()
            );
            order.confirm();

            em.persist(order);
            em.flush();

            throw new SimulatedFailure();
        })
    );

    assertEquals(
        8,
        readAvailableStock(dataSource, 81L)
    );
    assertEquals(
        0L,
        countOrdersByNumber(
            dataSource, 7L, "ORD-ROLLBACK"
        )
    );
}
```

Bằng chứng mạnh hơn cần query `order_lines` theo Order correlation key hoặc ghi nhận SQL INSERT trong test; FK có thể bảo đảm line không còn khi parent rollback, nhưng acceptance report vẫn nên ghi rõ expected/actual.

**Không dùng Java object `order` sau rollback để suy database state**: object vẫn có ID, fields và version cho dù transaction đã rollback.

---

## 29. AC-05: UNIQUE theo tenant là ràng buộc database

Nếu chỉ kiểm tra:

```java
if (!existsOrderNumber(tenantId, orderNo)) {
    createOrder(...);
}
```

hai concurrent writers có thể cùng thấy chưa tồn tại và cùng insert. Bằng chứng cuối cùng phải là DB UNIQUE constraint.

PostgreSQL:

```sql
CONSTRAINT uq_orders_tenant_no
    UNIQUE (tenant_id, order_no)
```

Một phép thử:

1. Commit `ORD-DUP` Tenant 7.
2. Thử insert `ORD-DUP` Tenant 7 với ID khác.
3. Assert UNIQUE-specific failure.
4. Assert chỉ có một committed Order.
5. Assert inventory cho lần cố tạo thứ hai không bị trừ sau rollback.

## 30. Phân loại lỗi SQLState thay vì mọi RuntimeException

Helper cho PostgreSQL:

```java
static boolean hasSqlState(
        Throwable failure,
        String expected) {

    Throwable current = failure;

    while (current != null) {
        if (current instanceof SQLException sql
                && expected.equals(sql.getSQLState())) {
            return true;
        }
        current = current.getCause();
    }
    return false;
}
```

Các SQLStates minh họa:

| PostgreSQL SQLState | Ý nghĩa |
| --- | --- |
| `23505` | Unique violation |
| `23503` | Foreign-key violation |
| `23514` | Check violation |
| `23502` | Not-null violation |

JPA/Spring có thể bọc `SQLException` trong `PersistenceException`, `RollbackException` hoặc `DataIntegrityViolationException`. Khi test DB UNIQUE, assert đúng root cause/constraint name/SQLState theo database, không coi bất kỳ `RuntimeException` là thành công.

## 31. AC-06: Hai tenants cùng business key

```text
Tenant 7: orderNo ORD-100
Tenant 8: orderNo ORD-100
```

Nếu yêu cầu unique *trong tenant*, cả hai phải được phép.

Nghiệm thu:

```sql
SELECT tenant_id, order_no, COUNT(*) AS n
FROM purchase_orders
WHERE order_no = 'ORD-100'
GROUP BY tenant_id, order_no
ORDER BY tenant_id;
```

Expected: mỗi tenant đúng một row. Đồng thời thử tạo hai Orders Tenant 7 trùng number, expected UNIQUE error.

Một UNIQUE trên riêng `order_no` có thể khiến test cross-tenant fail dù cùng dữ liệu của tenant đơn lẻ vẫn chạy tốt; đó là lý do cần fixtures nhiều tenants.

## 32. AC-07: Không rò dữ liệu chéo tenant

Repository query:

```java
List<PurchaseOrder> orders = em.createQuery(
    "SELECT o FROM PurchaseOrder o " +
    "WHERE o.tenantId = :tenantId " +
    "ORDER BY o.createdAt DESC, o.id DESC",
    PurchaseOrder.class
)
.setParameter("tenantId", tenantId)
.setMaxResults(pageSize)
.getResultList();
```

Test seed Tenant 7 và Tenant 8, cùng order number ở hai tenants. Assertions:

- Tenant 7 chỉ nhận Orders của Tenant 7.
- Tenant 8 chỉ nhận Orders của Tenant 8.
- ID của Tenant 8 không được trả khi query Tenant 7.
- Query theo ID không dùng mỗi `findById(id)` rồi quên tenant/authorization nếu application policy yêu cầu tenant-scoped access.
- Không dùng empty list làm pass giả cho `allMatch`: phải seed ít nhất một row tenant hợp lệ.

**Index tối ưu không bao giờ là lý do bỏ điều kiện tenant.** Tenant scoping ở repository là defense-in-depth; authorization có thể còn phụ thuộc user/role/RLS.

---

## 33. AC-08: Kiểm thử DB CHECK độc lập với Java validation

Nếu `InventoryItem.reserve` đã chặn stock âm, test đó **không chứng minh CHECK(available_quantity >= 0)** thật sự tồn tại.

Dùng JDBC trong disposable test DB:

```java
@Test
void databaseCheckRejectsNegativeInventory()
        throws SQLException {

    seedStock(emf, 82L, 7L, 5);

    SQLException failure = assertThrows(
        SQLException.class,
        () -> {
            try (Connection c = dataSource.getConnection();
                 PreparedStatement st =
                     c.prepareStatement(
                         "UPDATE inventory_items " +
                         "SET available_quantity = -1 " +
                         "WHERE id = ?")) {

                st.setLong(1, 82L);
                st.executeUpdate();
            }
        }
    );

    assertEquals("23514", failure.getSQLState());
    assertEquals(
        5,
        readAvailableStock(dataSource, 82L)
    );
}
```

Trong PostgreSQL, CHECK được kiểm tra khi statement thực thi theo schema ví dụ. Với constraints deferred ở DB khác, lỗi có thể xuất hiện khi commit. Test rollback/connection autocommit cần thiết kế phù hợp.

Dùng test database riêng. **Không cố tình UPDATE dữ liệu sai trên production** để kiểm tra CHECK.

## 34. AC-08: Kiểm thử FK OrderLine độc lập

PostgreSQL:

```sql
INSERT INTO order_lines(
    order_id, product_code, quantity, unit_price
)
VALUES (9999999, 'SKU-MISSING', 1, 12.50);
```

Expected: foreign-key violation nếu Order ID không tồn tại.

Để thành integration test mạnh:

- Chọn ID chắc chắn vắng mặt trong disposable DB.
- Assert SQLState `23503`.
- Assert không có committed orphan line.
- Kiểm tra FK được khai báo và validated trong catalog.
- Không vô hiệu FK trong setup/cleanup rồi quên bật lại.

Một OrderLine tạo qua JPA có `@ManyToOne` đúng vẫn có thể không chứng minh FK database có thật nếu chưa thử invalid FK.

## 35. AC-08: Test NOT NULL và giới hạn kiểu

Nghiệm thu dữ liệu đầu vào:

- `tenant_id` không null.
- `order_no` không null và không vượt `VARCHAR(64)`.
- `quantity` dương.
- `total_amount` không âm.
- `NUMERIC(14,2)` giữ precision/scale theo contract.
- `state` nằm trong allowed set.
- `created_at` dùng timezone/time type thống nhất.

Không chuyển money sang `double` để “test dễ hơn”. Trong Java dùng `BigDecimal` và so sánh theo business numeric semantics.

Ví dụ:

```java
assertEquals(
    0,
    actualAmount.compareTo(
        new BigDecimal("37.50")
    )
);
```

Nếu nghiệp vụ yêu cầu đúng scale, bổ sung assertion scale; nếu dữ liệu có currency, tổng tiền cần currency consistency và rounding rule rõ.

---

## 36. AC-09: Hai requests không được oversell

Given available stock = 5.

```text
Request A: reserve 4
Request B: reserve 4
```

Sau hai transactions cạnh tranh, chỉ một request được commit thành công. Expected final stock = 1, không bao giờ = -3.

Nếu cả hai đọc `5` trước khi update bằng logic không có locking/version:

```text
A reads 5
B reads 5
A writes 1
B writes 1
```

có thể xảy ra **lost update** hoặc hai orders cùng confirm dù kho chỉ giảm một lần.

Ví dụ dùng `PESSIMISTIC_WRITE` trên stock row, giúp serialize đoạn đọc-kiểm tra-ghi trong **cùng transaction**. Tuy nhiên lock behavior, timeout, deadlock, transaction isolation và vendor SQL cần được xác minh với database thật.

## 37. Test concurrency cần điều phối thực, không dựa vào sleep

Dùng:

- Hai independent EntityManagers.
- Hai transactions.
- Một barrier để hai worker bắt đầu gần nhau.
- `ExecutorService` và `Future` với timeout.
- Định nghĩa expected outcomes.
- Readback committed DB state cuối cùng.
- Cleanup mọi thread/connection.

Không dùng một `EntityManager` static chia sẻ giữa threads; EntityManager không thread-safe. Không dùng `Thread.sleep(500)` thay barrier rồi mặc định thứ tự luôn ổn định trên CI.

## 38. Pseudocode kiểm thử không oversell

```java
// Setup: stock #90 có available=5.
// Dùng hai threads với EntityManagers/transactions riêng.
//
// Barrier giải phóng hai requests cùng thời điểm.
// Request A gọi place(..., "ORD-A", qty=4).
// Request B gọi place(..., "ORD-B", qty=4).
//
// Đợi cả hai Future kết thúc với timeout.
//
// Assert:
// - exactly one successful commit
// - other result is InsufficientStockException
//   hoặc một lỗi concurrency được policy cho phép
// - stock #90 committed available = 1
// - exactly one committed Order (A hoặc B)
// - no orphan OrderLines
// - no database CHECK violation được bỏ qua
```

**Tại sao là pseudocode?** Concurrency harness phải gắn với transaction helper và executor của dự án, có barrier/timeout/cleanup phù hợp. Không nên giả vờ một đoạn không có coordination đầy đủ là integration test runnable.

Nghiệm thu cần kiểm tra **kết quả cuối DB**, không chỉ số exceptions: một bug có thể trả một lỗi cho B nhưng đã commit Order B trước đó.

## 39. Lock ordering khi Order có nhiều products

Nếu mở rộng sang nhiều `InventoryItem`:

```text
Transaction A locks product 10 then 20
Transaction B locks product 20 then 10
```

có thể gây deadlock. Một chiến lược là lock tất cả inventory items theo thứ tự khóa ổn định:

```text
Sort inventory IDs ascending
Lock 10, then 20, then 30
Validate all quantities
Apply all reservations
Persist Order and Lines
Commit
```

Nhưng không đảm bảo tuyệt đối không deadlock vì database còn locks khác và query optimizer có thể chọn order riêng. Cần integration tests, deadlock handling và retry policy có giới hạn; không kéo transaction dài xuyên network calls.

## 40. Atomic SQL update là một phương án khác

Trong một số use cases, thay vì read-then-lock có thể dùng conditional update:

```sql
UPDATE inventory_items
SET available_quantity = available_quantity - :qty,
    version = version + 1
WHERE id = :id
  AND tenant_id = :tenantId
  AND available_quantity >= :qty;
```

Nếu affected rows = 1, reservation thành công; nếu = 0, không có stock đủ hoặc item không đúng tenant.

Nhưng cần hiểu:

- Đây là SQL-native/bulk update, không gọi `InventoryItem.reserve` domain method.
- Không tự đồng bộ mọi managed entity trong L1.
- Phải cập nhật/check version đúng với concurrency strategy.
- Trigger/audit/domain events cần thiết kế riêng.
- Update và persist Order phải nằm trong cùng transaction.
- Nghiệm thu phải chứng minh affected row count/rollback và event integrity.

Không coi native SQL là một “cách miễn phí” thay mọi domain invariants.

---

## 41. AC-10: Optimistic locking trên Order

Với:

```java
@Version
private Long version;
```

khi hai contexts đọc cùng Order version 0:

```text
EM A reads Order v0
EM B reads Order v0

A changes state, commits → DB version v1
B changes stale state, flush/commit → conflict
```

Bằng chứng cần:

- Generated SQL UPDATE có version predicate tương ứng.
- Một transaction thành công.
- Một transaction thất bại optimistic conflict.
- Committed Order giữ state của winner.
- Không có ghi một phần/outbox event của loser.
- Retry (nếu có) dùng context mới, reload state.

Một test chỉ check `@Version` annotation tồn tại không chứng minh provider thực thi optimistic version check.

## 42. Cách kiểm tra stale update

Một skeleton:

```java
EntityManager emA = emf.createEntityManager();
EntityManager emB = emf.createEntityManager();

try {
    emA.getTransaction().begin();
    emB.getTransaction().begin();

    PurchaseOrder a =
        emA.find(PurchaseOrder.class, orderId);

    PurchaseOrder b =
        emB.find(PurchaseOrder.class, orderId);

    // Chuẩn bị operation thay đổi một managed
    // field hợp lệ qua domain method.
    // A commit trước; B giữ version cũ.

    emA.getTransaction().commit();

    assertThrows(
        RuntimeException.class,
        () -> {
            emB.flush();
            emB.getTransaction().commit();
        }
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
```

Đây là **skeleton**, chưa đầy đủ để pass vì còn thiếu thay đổi field hợp lệ để trigger UPDATE. Khi hoàn thiện, phải xác minh specific `OptimisticLockException` (hoặc wrapper/cause phù hợp) và committed state. Một test generic `RuntimeException` không đạt AC-10 nếu exception thực chất là missing table hay connection failure.

Nếu domain model không cho sửa Order đã CONFIRMED, seed một DRAFT Order hoặc dùng use case state transition hợp lệ để tạo hai stale writers.

## 43. Khi nào `@Version` không tự đủ?

Các trường hợp cần chú ý:

- Bulk JPQL `UPDATE`/`DELETE`.
- Native SQL writes.
- Child collection changes không bump root version theo kỳ vọng.
- External writer không kiểm tra version.
- Retry cùng stale object mà không reload.
- HTTP request sử dụng version cũ nhưng service bỏ qua expected version.
- Transaction isolation/conflict semantics khác theo engine.

Đối với một aggregate có nhiều child rows, nghiệm thu phải xác minh mọi thay đổi ảnh hưởng invariant có được bảo vệ concurrency đúng như contract, chứ không suy từ một field annotation.

---

## 44. AC-11: JPQL list đúng và sort ổn định

API list Orders:

```java
public record OrderSummary(
    Long id,
    String orderNumber,
    Instant createdAt,
    BigDecimal totalAmount
) {}
```

JPQL:

```java
String jpql =
    "SELECT new com.example.checkout.OrderSummary(" +
    "o.id, o.orderNumber, o.createdAt, o.totalAmount" +
    ") FROM PurchaseOrder o " +
    "WHERE o.tenantId = :tenantId " +
    "ORDER BY o.createdAt DESC, o.id DESC";

List<OrderSummary> page = em.createQuery(
    jpql, OrderSummary.class
)
.setParameter("tenantId", tenantId)
.setFirstResult(offset)
.setMaxResults(size)
.getResultList();
```

Đây là DTO projection, không cần materialize OrderLines. `id` làm tie-breaker khi `createdAt` trùng, giúp sort deterministic với dataset không đổi.

Test:

- Seed ≥ 25 Orders Tenant 7.
- Seed ≥ 5 Orders Tenant 8.
- Cho nhiều Orders cùng `createdAt`.
- Lấy các pages size 10.
- So expected order IDs từ fixture.
- Không duplicates/missing IDs trên dataset tĩnh.
- Không có Tenant 8 trong kết quả Tenant 7.
- Truy vấn `ORDER BY` và `LIMIT/OFFSET` đúng trên SQL generated.
- Không dùng collection FETCH JOIN làm phá pagination.

## 45. Offset và keyset có tiêu chí riêng

Deep OFFSET có thể chậm dù index đúng:

```java
query.setFirstResult(200_000);
query.setMaxResults(20);
```

Nếu use case cần duyệt tuần tự nhiều pages, keyset pagination có thể phù hợp:

```sql
WHERE tenant_id = :tenantId
  AND (
      created_at < :lastCreatedAt
      OR (
          created_at = :lastCreatedAt
          AND id < :lastId
      )
  )
ORDER BY created_at DESC, id DESC
LIMIT :size;
```

Nghiệm thu phải test:

- Cursor mang tenant/filter/sort scope.
- Không trùng/mất dữ liệu trên dataset tĩnh.
- Behavior khi inserts/updates diễn ra giữa pages được định nghĩa.
- NULL sort fields được xử lý.
- Không gắn dữ liệu nhạy cảm vào cursor không được bảo vệ.
- Query plan phù hợp index.

Không tự coi keyset và offset semantics là tương đương hoàn toàn: keyset không tự hỗ trợ nhảy thẳng tới page N.

## 46. AC-12: N+1 phải được đo bằng SQL count

Một test tạo 1, 10, 30 Orders với Customers khác nhau:

```text
N=1  → 2 SQL
N=10 → 11 SQL
N=30 → 31 SQL
```

đây là dấu hiệu có thể xảy ra N+1 khi mapper gọi `order.getCustomer()` và từng Customer được lazy-load.

Sau khi chuyển sang DTO projection hoặc to-one JOIN FETCH phù hợp:

```text
N=1  → 1 SQL
N=10 → 1 SQL
N=30 → 1 SQL
```

đây là một mục tiêu test có thể kiểm chứng cho một query shape cụ thể, **không phải bảo đảm mọi ứng dụng chỉ cần đúng một SQL**. Thêm count query cho pagination hoặc lookup khác có thể hợp lệ. Nghiệm thu cần đặt SQL-count budget theo use case và xem cả rows/bytes/latency.

### Cách tránh test SQL count pass giả

- Seed fixtures trong transaction khác.
- Clear/close EntityManager trước khi đo.
- Bắt đầu counter trước repository call và mapper/serialization.
- Không để L1/L2 cache làm các extra SQL biến mất không chủ ý.
- Tránh test song song cập nhật shared Hibernate Statistics counter.
- Xác minh output DTO fields đúng, không chỉ số SQL.

## 47. SQL logging cho bằng chứng

Có thể thu SQL với datasource-proxy/P6Spy, Hibernate SQL logging hoặc tracing tại JDBC layer. Bản evidence cần:

```text
AC-ID: AC-12
Test: OrderQueryIT.listDoesNotTriggerNPlusOne
Dataset: 30 Orders, 30 Customers
Observed statement count: 1 (example target)
SQL fingerprint: SELECT ... JOIN ...
Unexpected SELECT per customer: 0
Environment: PostgreSQL ..., Hibernate ...
Captured at: test execution ...
Result: PASS/FAIL
```

Các giá trị cụ thể phải được đo từ test thật; không dùng “Observed 1” như con số mặc định trong báo cáo thực tế.

---

## 48. Generated SQL là bằng chứng kỹ thuật quan trọng

JPQL:

```java
"SELECT o FROM PurchaseOrder o " +
"WHERE o.tenantId = :tenantId"
```

không cho thấy toàn bộ những thứ database thực thi nếu có:

- EntityGraph.
- EAGER associations.
- Multi-tenancy/soft-delete filters.
- Dialect pagination.
- SQL casts.
- Additional selects.
- Lazy association access sau repository call.
- Provider-generated version updates.
- Batch insert/update statements.

Một bằng chứng đúng cần chỉ ra **SQL generated thực tế** và **bind types/values đã được masking phù hợp**, không chỉ ảnh chụp JPQL source.

## 49. Nhận diện SQL DML chứng minh transaction path

Một trace minh họa:

```text
BEGIN
SELECT ... inventory_items ... FOR UPDATE
INSERT INTO purchase_orders (...)
INSERT INTO order_lines (...)
UPDATE inventory_items
  SET available_quantity=?, version=?
  WHERE id=? AND version=?
COMMIT
```

Đây là **trace kỳ vọng về semantics**, không phải thứ tự SQL bắt buộc trên mọi provider. Lúc triển khai, capture statement list thật.

Đối với rollback:

```text
BEGIN
... DML statements ...
ROLLBACK
```

Trace SQL cho thấy activity, nhưng **nghiệm thu outcome vẫn cần readback** vì log có thể thiếu transaction completion, bị sampling hoặc không bao gồm connection của reader.

## 50. Vì sao rollback SQL trace chưa đủ?

Một log có `ROLLBACK` có thể thuộc connection khác với INSERT mà bạn đang nghĩ. Bằng chứng mạnh cần:

- Correlation ID/test ID.
- Transaction/session ID khi có.
- DML nằm trên đúng connection/transaction.
- Application exception cause.
- Fresh DB readback sau completion.
- Kết quả cả các bảng liên quan.
- Isolation/read routing rõ.

Không gắn kết hai log lines chỉ vì timestamps gần nhau.

## 51. SQL parameter binding và type correctness

Sau upgrade JDBC driver/ORM, kiểu bind có thể thay đổi:

- Enum ORDINAL vs STRING.
- `Instant` ↔ TIMESTAMP/TIMESTAMPTZ.
- `BigDecimal` precision/scale.
- UUID/JDBC type.
- JSON/array types.
- String length/collation.
- Null typed parameters.

Một SQL query vẫn chạy nhưng cast trên indexed column có thể làm query plan kém. Nghiệm thu phải xem **kiểu dữ liệu và hiệu quả query**, không chỉ kết quả một fixture nhỏ.

Không nối input vào JPQL/SQL string thay `setParameter`: vừa tạo injection risk vừa làm plan reuse khó đo.

---

## 52. AC-14: Execution plan là một bằng chứng, không phải mục tiêu duy nhất

PostgreSQL:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    id, order_no, created_at, total_amount
FROM purchase_orders
WHERE tenant_id = 7
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

Ghi:

- Scan type và index name nếu có.
- Actual vs estimated rows.
- Rows removed by filter.
- Buffers hit/read.
- Sort, spills, memory.
- Planning/execution time.
- Query parameters.
- Dataset size/distribution.
- Cache warm/cold state.
- Concurrency và lock waits bên ngoài plan.

Một Seq Scan có thể tối ưu cho bảng nhỏ; một Index Scan quét hàng triệu entries có thể chậm. **Không assert “phải có Index Scan” như tiêu chí cuối cùng** nếu latency và resources tốt hơn với plan khác.

`EXPLAIN ANALYZE` thực thi statement; không vô ý chạy với destructive DML trên production.

## 53. Index cho list query

JPQL:

```java
"WHERE o.tenantId = :tenantId " +
"ORDER BY o.createdAt DESC, o.id DESC"
```

Index candidate:

```sql
CREATE INDEX idx_orders_tenant_created_id
ON purchase_orders(
    tenant_id,
    created_at DESC,
    id DESC
);
```

Nó phù hợp ý tưởng equality tenant trước sort columns.

Nếu query thêm `status = :status` và lọc thường xuyên theo status, index candidate khác có thể là:

```sql
CREATE INDEX idx_orders_tenant_status_created_id
ON purchase_orders(
    tenant_id, state, created_at DESC, id DESC
);
```

Đây là PostgreSQL candidate, phải cân nhắc workload/tần suất writes và query không lọc state. Không tạo mọi combination indexes chỉ để bảng evidence dài hơn.

## 54. Latency budget phải gắn với workload

Một mẫu định nghĩa giả định:

```text
GET /orders:
  Dataset ≥ 1 million Orders
  Tenant size distribution đại diện
  Concurrency 20 clients
  Request size 20
  P95 target = do dự án quyết định
  SQL count budget = do dự án quyết định
  DB CPU/IO budget = đo cùng baseline
```

Không bịa P95 “đã đạt” khi chưa có đo thực tế. Nghiệm thu performance cần:

- Baseline trước thay đổi.
- Benchmark ở dữ liệu đại diện.
- Same SQL parameters và behavior.
- Tài nguyên DB/CPU/IO/heap.
- P95/P99, throughput và error rate.
- Multiple runs, không chỉ một lần.

---

## 55. Transaction outcome sau `@Transactional` trong Spring

Nếu application dùng Spring:

```java
@Service
public class CheckoutService {

    private final OrderPlacement placement;
    private final EntityManager entityManager;

    public CheckoutService(
            OrderPlacement placement,
            EntityManager entityManager) {
        this.placement = placement;
        this.entityManager = entityManager;
    }

    @Transactional
    public Long place(
            Long tenantId,
            Long inventoryId,
            String orderNo,
            int quantity) {

        return placement.place(
            entityManager,
            tenantId,
            inventoryId,
            orderNo,
            quantity
        );
    }
}
```

Ví dụ giả định `OrderPlacement` được cấu hình thành Spring bean và `EntityManager` được inject theo cơ chế Spring/JPA phù hợp (thường `@PersistenceContext`). Mã được gọi qua Spring proxy để transaction interceptor hoạt động.

**Điểm nghiệm thu:** transaction Spring commit sau khi body service method hoàn tất; một `flush` trong service không chứng minh commit. Gọi service qua proxy và đọc lại bằng context/transaction mới. Tránh self-invocation làm bypass `@Transactional` trong proxy-based mode.

## 56. `@DataJpaTest` không mặc nhiên kiểm tra commit thật

Spring Boot `@DataJpaTest` thường dùng test-managed transaction và rollback sau mỗi test. Một test:

```java
@Test
void saveWorks() {
    repository.save(order);
    assertTrue(repository.findById(id).isPresent());
}
```

có thể pass mà không có commit.

Khi tiêu chí là committed state, dùng:

- `TestTransaction.flagForCommit(); TestTransaction.end();` khi đang ở active test-managed transaction, hoặc
- `TransactionTemplate` ngoài outer test transaction, hoặc
- Service integration test không có outer `@Transactional` test method.

Sau đó dùng new transaction/context hoặc JDBC primary readback.

**Không gọi `@Commit` trên mọi test chỉ để tránh rollback**, vì committed fixtures có thể rò sang tests khác.

## 57. `REQUIRES_NEW` và cleanup

Nếu service viết audit/outbox bằng một transaction `REQUIRES_NEW`, outer test rollback **không undo** committed inner transaction. Một bài nghiệm thu phải:

- Xác định transaction owner và propagation.
- Seed/dọn dữ liệu riêng.
- Assert side effects committed ngoài outer boundary nếu đó là contract.
- Không coi rollback test method là phép dọn mọi transaction.
- Không dùng cùng database schema giữa parallel tests với global cleanup.

Nếu Order và Inventory cần atomicity, việc vô tình tách một repository method sang `REQUIRES_NEW` có thể phá AC-01/AC-04 dù từng repository method riêng lẻ chạy đúng.

## 58. Checked exception và rollback rule Spring

Theo cấu hình Spring thông dụng:

- Unchecked `RuntimeException` và `Error` thường kích hoạt rollback.
- Checked exception không mặc nhiên rollback nếu không cấu hình `rollbackFor` hoặc rule tương ứng.

Vì vậy:

```java
@Transactional(rollbackFor = IOException.class)
public void process() throws IOException {
    // ...
}
```

có thể cần thiết nếu nghiệp vụ muốn rollback khi `IOException` xảy ra.

Đây là **Spring transaction rule**, không áp nguyên xi cho JPA `RESOURCE_LOCAL` nơi caller tự điều khiển commit/rollback. Test phải assert committed state, không đoán outcome chỉ từ exception class.

---

## 59. Test dữ liệu phải độc lập với Java first-level cache

Một test sai:

```java
em.getTransaction().begin();

PurchaseOrder order = new PurchaseOrder(...);
em.persist(order);

assertNotNull(em.find(
    PurchaseOrder.class, order.getId()
));

em.getTransaction().rollback();
```

`find` có thể trả managed instance trong cùng context. Sau rollback, Java object vẫn có ID/values.

Test đúng:

1. Commit hoặc rollback.
2. Đóng EntityManager writer.
3. Mở reader context/connection mới.
4. Assert committed DB state.
5. Với DB read replica, xác định consistency contract và lag.
6. Với L2 cache, dùng JDBC khi cần kết luận DB trực tiếp.

**Bằng chứng không được dùng một object trong memory để khẳng định một transaction đã commit.**

## 60. Rollback không “undo” setters trên Java object

Sau:

```java
stock.reserve(3);
em.flush();
tx.rollback();
```

`stock.getAvailableQuantity()` có thể vẫn trả 7 dù DB đã rollback về 10.

Nghiệm thu phải đọc lại stock từ DB. Sau một JPA persistence failure, đừng tiếp tục dùng persistence context/graph cũ như một session sạch; rollback, close và tạo unit of work mới nếu retry phù hợp.

## 61. Commit lỗi do mất kết nối có thể có outcome không xác định

Trường hợp:

```text
Client sends COMMIT
DB commits successfully
Connection fails before ACK reaches client
Application receives an exception
```

Không được suy “exception nghĩa chắc chắn rollback”. Với fault injection/network failure, kết quả có thể **unknown**. Recovery cần:

- Stable business key/idempotency key.
- Reconnect và kiểm tra committed state.
- Không retry insert mù quáng.
- Không gửi payment/email lần hai không có idempotency.
- Ghi nhận operator evidence và transaction outcome uncertainty.

Trong normal constraint failures trên healthy test DB, rollback path có thể được kiểm chứng rõ. Nhưng nghiệm thu toàn diện phải phân biệt known rollback và unknown commit result.

---

## 62. Mẫu bảng evidence theo tiêu chí

Một bảng kết quả nghiệm thu có thể có:

| AC | Test name | Evidence ID | Expected | Actual | Status |
| --- | --- | --- | --- | --- | --- |
| AC-01 | `placingOrderCommits...` | E-TXN-01 | Stock=7, Order+Line=1 | *Điền sau chạy test* | Pending |
| AC-04 | `flushOfOrderAndStock...` | E-TXN-04 | Stock=8, Order=0 | *Điền sau chạy test* | Pending |
| AC-05 | `duplicateOrderNo...` | E-DB-05 | Unique violation | *Điền sau chạy test* | Pending |
| AC-09 | `concurrentOrders...` | E-CONC-09 | One commit, stock=1 | *Điền sau chạy test* | Pending |
| AC-12 | `listDoesNotNPlusOne` | E-SQL-12 | Trong SQL budget | *Điền sau đo* | Pending |
| AC-13 | `schemaMatches...` | E-DDL-13 | Version/schema đúng | *Điền sau kiểm tra* | Pending |

Bảng trên là **mẫu**, không phải kết quả nghiệm thu đã thực thi. Chỉ chuyển `Pending` thành `PASS` khi có kết quả từ đúng test/environment và evidence được lưu.

## 63. Cấu trúc thư mục bằng chứng

Một cách tổ chức:

```text
acceptance-evidence/
├── README.md
├── environment.json
├── criteria-matrix.md
├── schema/
│   ├── flyway-history.txt
│   ├── columns.txt
│   ├── constraints.txt
│   └── indexes.txt
├── sql/
│   ├── place-order-sanitized.log
│   ├── order-list-sanitized.log
│   ├── sql-count.csv
│   └── explain-order-list.txt
├── transactions/
│   ├── commit-readback.txt
│   ├── rollback-readback.txt
│   └── concurrent-reservation.txt
├── data/
│   ├── order-line-counts.csv
│   ├── inventory-reconciliation.csv
│   └── tenant-isolation.txt
└── tests/
    ├── junit-results.xml
    └── coverage-summary.txt
```

Không bắt buộc cấu trúc này; điểm quan trọng là evidence IDs có thể chỉ tới artifacts thật. Không đính kèm unmasked passwords, access tokens, payment data, email cá nhân hoặc raw production snapshots không được phép.

## 64. Environment manifest cần ghi gì?

Ví dụ:

```json
{
  "applicationVersion": "example-commit-sha",
  "javaRuntime": "version-from-test-run",
  "jpaApi": "version-from-dependency-lock",
  "ormProvider": "provider-and-version",
  "jdbcDriver": "driver-and-version",
  "database": "PostgreSQL version-from-runtime",
  "schemaMigration": "Flyway V1..Vn",
  "testProfile": "acceptance",
  "testDataset": "fixture-bundle-id",
  "executedAt": "timestamp-of-test-run",
  "runId": "ci-run-reference"
}
```

Các values là placeholders để tránh bịa phiên bản đã chạy. Trong báo cáo thực tế phải thay bằng dữ liệu từ build lockfile/runtime và test report.

## 65. Test report phải chứa cả thất bại

Nếu AC-09 concurrency fail, ghi:

```text
AC-09: FAIL
Expected:
  at most one Order confirmed for stock=5, qty=4+4
  final available=1
Actual:
  two Orders confirmed, final available=1
Diagnosis:
  business invariant violated despite stock not negative
Evidence:
  test result, committed Order rows,
  inventory row, SQL/transaction traces
Owner:
  checkout backend
Next action:
  fix locking/atomic update, rerun full scenario
```

Đây là **tình huống giả định** để minh họa cách ghi kết quả, không phải một failure đã quan sát. Mẫu cho thấy vì sao chỉ assert stock không âm là chưa đủ: hai Orders có thể được xác nhận dù kho chỉ giảm một lần.

## 66. Phân biệt pass, fail, blocked và not-run

- **PASS:** tiêu chí có phép kiểm tra hợp lệ và bằng chứng actual đáp ứng expected.
- **FAIL:** phép kiểm tra chạy, kết quả thực không đáp ứng expected.
- **BLOCKED:** không thể thực hiện có căn cứ (ví dụ CI không có container runtime).
- **NOT RUN:** chưa chạy hoặc không được đưa vào run.
- **INCONCLUSIVE:** test chạy nhưng bằng chứng không đủ kết luận (ví dụ không xác định transaction owner).

Đừng chuyển BLOCKED hoặc NOT RUN thành PASS vì unit tests khác thành công.

---

## 67. Ma trận truy vết SQL → invariant

| SQL/DDL evidence | Invariant / AC |
| --- | --- |
| SELECT Inventory có tenant predicate, lock clause | AC-03/AC-09 |
| INSERT Order có tenant/orderNo | AC-01/AC-05/AC-07 |
| INSERT OrderLine có order_id FK | AC-01/AC-08 |
| UPDATE Inventory có version check hoặc atomic predicate | AC-09 |
| BEGIN/COMMIT + fresh readback | AC-01 |
| BEGIN/ROLLBACK + fresh readback | AC-04 |
| UNIQUE(tenant_id,order_no) catalog | AC-05 |
| CHECK available_quantity >= 0 | AC-08 |
| ORDER BY createdAt DESC, id DESC, LIMIT | AC-11 |
| SQL count under representative N | AC-12 |
| Flyway history + constraints/indexes | AC-13 |

Bảng này đặc biệt hữu ích khi test suite lớn: một lỗi SQL/DB có thể tác động nhiều tiêu chí, nhưng mỗi tiêu chí vẫn cần own assertion/evidence.

## 68. Truy vết theo code commit và schema version

Mọi evidence nên có:

```text
git commit / release tag
migration version/checksum
database engine/version
JPA provider/version
JDBC driver/version
test dataset version
test execution run ID
timestamp
SQL fingerprint
acceptance criterion ID
```

Nếu không, một file `explain.txt` có thể đến từ database cũ hoặc code commit khác, và so sánh sẽ sai.

Không cần lưu toàn bộ bí mật runtime để tái lập: dùng configuration fingerprints, masking và secret references an toàn.

## 69. Negative test phải chứng minh đúng loại lỗi

Một test:

```java
assertThrows(RuntimeException.class, () -> {
    // tạo Order trùng
});
```

có thể pass vì:

- No persistence provider.
- Missing relation.
- Connection failed.
- Tenant ID sai.
- Mapping mismatch.
- Null field bug.
- SQL syntax error.

Với AC-05 phải kiểm tra unique violation cụ thể và final committed state. Với AC-09 phải kiểm tra business/concurrency behavior, không nhầm lock timeout bất kỳ thành “đã bảo vệ stock” nếu timeout không nằm trong expected policy.

## 70. Test độc lập, không dựa vào thứ tự thực thi

Anti-pattern:

```text
Test A creates order 101
Test B assumes order 101 exists
Test C deletes order 101
```

Chạy riêng test B sẽ fail hoặc pass sai. Để nghiệm thu:

- Mỗi test setup/teardown dữ liệu mình cần.
- Không dùng global mutable EntityManager.
- DB schema được khởi tạo có phiên bản.
- Không chia sẻ table cleanup giữa parallel tests.
- Test fixtures dùng IDs/scope rõ.
- Reset L2 cache nếu cần để đảm bảo observation.
- Không dùng system clock tùy tiện với date boundaries.
- Không dùng random seed không được ghi lại.
- Không dùng sleeps thay synchronization.

Độc lập giúp kết quả PASS có thể kiểm tra lại bởi người khác.

---

## 71. Nghiệm thu schema trên database production-like

Với Flyway + PostgreSQL Testcontainers:

```text
Start disposable PostgreSQL
        │
        ▼
Apply source-controlled migrations
        │
        ▼
Bootstrap Hibernate (validate)
        │
        ▼
Catalog checks
        │
        ▼
Negative constraint tests
        │
        ▼
JPA CRUD/transaction tests
        │
        ▼
Performance smoke
```

H2 có thể tốt cho smoke tests nhỏ, nhưng không đủ chứng minh PostgreSQL lock modes, SQLState, partial indexes, provider dialect SQL hoặc constraints đặc thù.

**Khả năng chạy lại từ một database sạch** là bằng chứng về tính tái lập của môi trường nghiệm thu.

## 72. Fresh schema test chưa đủ cho upgrade migration

Một thay đổi:

```text
V1 → V2: added NOT NULL field after backfill
```

nếu chỉ apply V1..V2 trên một database rỗng, không kiểm tra việc backfill **dữ liệu cũ**.

Một migration acceptance scenario cần:

1. Apply V1.
2. Seed realistic legacy rows.
3. Apply V2.
4. Verify backfilled field values.
5. Check constraints valid.
6. Bootstrap new JPA entity mapping.
7. Test read and writes.
8. Verify data preserved by stable business keys.

Đây là bằng chứng riêng với schema bootstrap từ empty DB.

## 73. Reconciliation sau migration

Nếu migrate bảng Orders và Lines, cần checks:

```sql
SELECT tenant_id, COUNT(*) AS orders,
       COALESCE(SUM(total_amount), 0) AS total
FROM purchase_orders
GROUP BY tenant_id;

SELECT COUNT(*) AS orphan_lines
FROM order_lines l
LEFT JOIN purchase_orders o
    ON o.id = l.order_id
WHERE o.id IS NULL;

SELECT tenant_id, order_no, COUNT(*)
FROM purchase_orders
GROUP BY tenant_id, order_no
HAVING COUNT(*) > 1;
```

Không chỉ so total counts vì có thể mất một row và trùng một row khác. Khi so source/target đang live, phải dùng snapshot/CDC watermark nhất quán; không so hai thời điểm có writes khác nhau rồi gọi mọi lệch là migration bug.

## 74. Đối soát totalAmount với OrderLines

Trong schema ví dụ (chưa tính tax/discount):

```sql
SELECT
    o.id,
    o.total_amount,
    COALESCE(
        SUM(l.quantity * l.unit_price),
        0
    ) AS computed_total
FROM purchase_orders o
LEFT JOIN order_lines l ON l.order_id = o.id
GROUP BY o.id, o.total_amount
HAVING o.total_amount IS DISTINCT FROM
    COALESCE(SUM(l.quantity * l.unit_price), 0);
```

Expected: không có rows sai lệch.

**Đây là PostgreSQL query** dùng `IS DISTINCT FROM`. Khi business có tax/discount/rounding, cần thay `computed_total` bằng công thức contract thật; không dùng công thức đơn giản để báo sai dữ liệu hợp lệ.

## 75. Đối soát inventory và Orders có giới hạn

Một kiểm tra:

```text
stock_after =
    stock_before
    - SUM(successfully reserved quantity)
    + SUM(released quantity)
    + SUM(received/restocked quantity)
```

Không thể suy stock_after chỉ từ Orders hiện tại nếu hệ thống còn restock, cancel, return, manual adjustments. Muốn đối soát đầy đủ cần **inventory ledger** hoặc event history có coverage và rules rõ.

Trong bài thực hành một product, không có restock/cancel, fixtures tạo database riêng thì expected stock có thể suy trực tiếp từ Orders mới. Trong production, không lấy công thức đơn giản này làm “bằng chứng không mất tồn kho” nếu có những dòng thay đổi khác.

---

## 76. Nghiệm thu lỗi và timeout đúng tầng

Phân biệt:

| Tình huống | Kết luận hợp lệ |
| --- | --- |
| Unique violation `23505` | DB từ chối duplicate key |
| FK violation `23503` | DB từ chối orphan |
| CHECK violation `23514` | DB từ chối giá trị vi phạm CHECK |
| OptimisticLockException | Stale version conflict trong JPA path |
| LockTimeoutException | Timeout liên quan lock, transaction semantics theo contract |
| QueryTimeoutException | Query timeout, không chứng minh business validation |
| ConnectionException | Hạ tầng không sẵn sàng |
| Bean Validation exception | Java/JPA validation path chặn |
| Business exception insufficient stock | Domain invariant chặn |
| Unknown commit result | Cần readback/idempotency, không suy rollback |

Một test nên assert failure **đúng loại và đúng boundary**. Đừng viết một catch chung rồi trả "Out of stock" cho cả trường hợp database mất kết nối.

## 77. Nghiệm thu observability khi chạy thật

Ngoài tests, môi trường staging/production cần quan sát:

- API P50/P95/P99 và error rates.
- SQL count/request, top slow statements.
- Database CPU, I/O, buffer reads.
- Active/pending connections.
- Transaction duration.
- Lock wait/deadlock count.
- Optimistic conflict count.
- Constraint violation count theo code.
- Replica lag nếu có.
- GC/hydration overhead.
- Business invariants metrics: oversell, duplicate order, orphan line.
- Change deployment version, schema version.

Không chạy full-table destructive checks trên production chỉ để tạo bằng chứng. Có thể dùng read-only SQL, synthetic data trong môi trường test hoặc data reconciliation có thời điểm/chi phí kiểm soát.

## 78. Nghiệm thu không được phá dữ liệu thật

Không:

- Chạy `flyway.clean` vào shared database.
- Bật `hibernate.hbm2ddl.auto=create-drop` trên production.
- Thử insert invalid rows trên production không có cleanup/ownership.
- Disable FK/RLS để test nhanh.
- Log full bind parameters/PII.
- Chạy `EXPLAIN ANALYZE DELETE...` trên production và tưởng chỉ xem plan.
- Dùng test credential có superuser privilege không cần thiết.

Dùng disposable database và quyền hạn giới hạn. Nếu cần production diagnostics, ưu tiên read-only queries đã được phê duyệt và không ảnh hưởng tải đáng kể.

---

## 79. Những lỗi nghiệm thu thường gặp

### Lỗi 1: Chỉ demo API trả 200

Không chứng minh commit, rollback, concurrency hoặc schema.

### Lỗi 2: Chỉ đính kèm source code

Code là thiết kế; cần test output/SQL/DB evidence.

### Lỗi 3: Có test nhưng không chạy trên DB thật

Mocks không thay DB constraints/transactions.

### Lỗi 4: `save` trả ID nên coi là đã commit

ID có thể được cấp trước completion.

### Lỗi 5: `flush` xong gọi `find` cùng EntityManager

First-level cache che committed state.

### Lỗi 6: Rollback xong nhìn Java object fields

Rollback không undo setters trên object.

### Lỗi 7: Chỉ assert RuntimeException

Không chứng minh đúng UNIQUE/CHECK/concurrency failure.

### Lỗi 8: Không có cross-tenant fixtures

Dễ bỏ sót tenant filter và unique scope.

### Lỗi 9: Test concurrent nhưng dùng một EntityManager

EM không thread-safe, test không mô phỏng độc lập transactions.

### Lỗi 10: Concurrency test chỉ assert stock không âm

Có thể hai Orders committed trong khi stock chỉ trừ một lần.

### Lỗi 11: Dùng sleeps để điều phối race

Flaky, không có deterministic ordering.

### Lỗi 12: Chỉ test schema bằng Hibernate validate

Không chứng minh mọi constraints/indexes/trigger.

### Lỗi 13: So Count(*) mà không kiểm keys/values

Có thể có missing+duplicate offset nhau.

### Lỗi 14: Không kiểm tra query SQL count khi N tăng

N+1 có thể bị che bởi dataset nhỏ/caches.

### Lỗi 15: Index exists là đủ nghiệm thu performance

Phải xem actual plan/latency và workloads.

### Lỗi 16: Không có benchmark baseline

Không thể khẳng định sau thay đổi tốt hơn hay không.

### Lỗi 17: Test Spring `@DataJpaTest` rollback nhưng ghi “commit pass”

Phải có transaction completion thật.

### Lỗi 18: Transaction inner `REQUIRES_NEW` được coi là rollback theo outer

Không đúng, cần cleanup/contract riêng.

### Lỗi 19: Mọi failures được retry tự động

Unique business conflict không transient; commit unknown outcome cần idempotency.

### Lỗi 20: Test cases phụ thuộc thứ tự

Không tái lập được và dễ pass giả.

### Lỗi 21: Thay enum/precision/timezone mà không test dữ liệu cũ

Có thể SQL vẫn chạy nhưng values sai.

### Lỗi 22: Artifact không ghi version/DB/migration

Không thể biết evidence ứng với release nào.

### Lỗi 23: Ghi con số expected thành actual

Mẫu nghiệm thu chưa được chạy không phải bằng chứng.

### Lỗi 24: Dùng raw production data/PII cho evidence

Rủi ro bảo mật và không cần thiết để chứng minh kỹ thuật.

### Lỗi 25: PASS mọi thứ dù một tiêu chí chưa chạy

Phải phân biệt PASS/FAIL/BLOCKED/NOT RUN/INCONCLUSIVE.

---

## 80. Bài tập 1: Phân loại bằng chứng

Một test chỉ gọi `repository.save(order)` và kiểm `getId()!=null`.

**Câu hỏi:** Có nghiệm thu được AC-01 commit không?

**Đáp án:** Không. Cần transaction completion và fresh database readback của Order, Lines và stock.

## 81. Bài tập 2: Flush nhưng không commit

Test `persist → flush → rollback`, JPA object vẫn có ID.

**Đáp án:** Không có committed row do transaction rollback; assert qua context/connection mới.

## 82. Bài tập 3: UNIQUE hay validation?

`orderNo` trùng và Java service throw `IllegalArgumentException` trước SQL.

**Đáp án:** Đây là Java validation evidence, không chứng minh database UNIQUE. Dùng DB negative test và SQLState.

## 83. Bài tập 4: Hai tenants cùng orderNo

Tenant 7 và Tenant 8 cùng tạo `ORD-1` nhưng unique constraint là `UNIQUE(order_no)`.

**Đáp án:** Sai business contract nếu uniqueness chỉ trong tenant; cần composite UNIQUE.

## 84. Bài tập 5: Rollback sau stock update

Stock 8, trong transaction trừ 3, flush, ném exception và rollback.

**Đáp án:** DB committed phải là 8; object Java có thể vẫn là 5.

## 85. Bài tập 6: Oversell

Stock 5, hai requests mỗi cái đặt 4 và cả hai Orders được confirm.

**Đáp án:** FAIL AC-09 ngay cả khi stock cuối không âm. Phải assert số Orders committed, stock và business inventory invariant.

## 86. Bài tập 7: Optimistic version

Hai EMs load same version, cả hai updates đều commit mà không conflict.

**Đáp án:** Cần xem `@Version` mapping, SQL WHERE version, bulk DML/other writers và isolation; không chấp nhận stale overwrite nếu contract cấm.

## 87. Bài tập 8: Lock timeout

Concurrent test fail với lock timeout thay vì InsufficientStockException.

**Đáp án:** Chỉ pass nếu acceptance policy cho phép timeout/concurrency response tương ứng và final DB state đúng; phân loại rõ transient/error semantics.

## 88. Bài tập 9: Query list 20 Orders

JPQL có `ORDER BY createdAt DESC` nhưng nhiều timestamps trùng.

**Đáp án:** Thêm tie-breaker `id DESC` và test pagination deterministic.

## 89. Bài tập 10: N+1

Test với 1 Order phát 2 SQL; với 30 Orders phát 31 SQL.

**Đáp án:** SQL count tăng tuyến tính; cần projection/fetch plan phù hợp, đo cả mapper/serialization.

## 90. Bài tập 11: Empty stream assertion

`orders.stream().allMatch(o → tenantId==7)` pass nhưng orders rỗng.

**Đáp án:** Assertion không có coverage; seed expected Order tenant 7 và assert list không rỗng/IDs đúng.

## 91. Bài tập 12: Missing CHECK

Entity có `@Column(nullable=false)` nhưng DB cho insert null.

**Đáp án:** Mapping metadata không thay DB constraint; kiểm tra DDL/catalog và DB negative test.

## 92. Bài tập 13: Flyway pass nhưng data sai

V2 migrate thành công nhưng totalAmount của một số Orders sai rounding.

**Đáp án:** Migration success không thay reconciliation. So row-level numeric values/aggregates và rounding policy.

## 93. Bài tập 14: Index Scan chậm

Plan báo Index Scan nhưng execution time 2 giây.

**Đáp án:** Xem actual rows/buffers/filter/sort/locks; Index Scan không đồng nghĩa nhanh.

## 94. Bài tập 15: Baseline không tương đồng

Trước thay đổi đo 100 rows, sau thay đổi đo 10 triệu rows.

**Đáp án:** Không thể so latency một cách công bằng; cần workload/data distributions tương đương.

## 95. Bài tập 16: Spring test transaction

`@DataJpaTest` saveAndFlush pass rồi test-managed rollback.

**Đáp án:** Chưa test commit thật; dùng TestTransaction/TransactionTemplate hoặc service test boundary rõ.

## 96. Bài tập 17: REQUIRES_NEW audit

Outer transaction rollback nhưng audit row vẫn tồn tại.

**Đáp án:** Audit đã commit độc lập; cần có acceptance/cleanup riêng, không giả định outer rollback bao hết.

## 97. Bài tập 18: JPA L2 cache

Một EntityManager mới trả giá trị cũ sau JDBC update.

**Đáp án:** Có thể shared cache stale; dùng JDBC readback/cache invalidation test và kiểm tra caching policy.

## 98. Bài tập 19: Data totals đúng nhưng lines sai

Order total 37.50, nhưng một line quantity=1 và unitPrice=37.50 thay vì quantity=3, unitPrice=12.50.

**Đáp án:** Total bằng nhau không chứng minh line semantics; phải assert từng line fields.

## 99. Bài tập 20: Identity sequence drift

Sau import, Order IDs lớn nhưng sequence phát giá trị trùng.

**Đáp án:** Kiểm tra sequence/identity ownership và state theo engine trước khi đưa writes vào target; không cập nhật counter bừa bãi khi writers hoạt động.

## 100. Bài tập 21: Không có evidence version

File SQL log không ghi commit hash hoặc migration version.

**Đáp án:** Khó truy vết release. Thêm environment manifest/CI run metadata.

## 101. Bài tập 22: H2 PostgreSQL compatibility

Test PostgreSQL-specific locks/constraints chỉ chạy trên H2 compatibility mode.

**Đáp án:** Chưa đủ; cần production-like database integration tests.

## 102. Bài tập 23: Mất kết nối sau COMMIT

App nhận exception nhưng database có thể đã commit.

**Đáp án:** Unknown outcome; tra cứu bằng stable business key/idempotency key trước khi retry, không khẳng định rollback chắc chắn.

## 103. Bài tập 24: Báo cáo trạng thái

AC-09 chưa chạy vì CI không có Docker, nhưng tất cả unit tests pass.

**Đáp án:** AC-09 là BLOCKED/NOT RUN, không phải PASS; nêu blocker và kế hoạch thực hiện có môi trường phù hợp.

## 104. Bài tập 25: Tự nghiệm thu end-to-end

**Yêu cầu:** Hoàn thành bộ evidence cho use case đặt đơn, giảm tồn kho và danh sách Orders.

**Hướng triển khai:**

1. Xác định ít nhất AC-01..AC-15 cho system contract thật.
2. Dựng disposable PostgreSQL và chạy migrations.
3. Kiểm tra tables/columns/constraints/indexes bằng catalog.
4. Seed tenants, inventory items, Orders và edge cases.
5. Ghi Order/Line/Inventory trong cùng transaction.
6. Commit và readback JDBC/new EntityManager.
7. Thử quantity âm/0, stock thiếu, duplicate orderNo, FK/CHECK invalid.
8. Inject failure sau flush, xác nhận rollback cả Order và stock.
9. Test hai transactions cạnh tranh reservation.
10. Test stale Order update với `@Version`.
11. Test tenant-scoped JPQL, stable pagination, DTO projection.
12. Đo SQL count khi số Orders tăng.
13. Thu hot-query plans và latency trên data phù hợp.
14. Lưu evidence theo AC IDs, có code/schema/runtime versions.
15. Chỉ đánh dấu PASS cho tiêu chí đã chạy và có expected/actual.

---

## 105. Checklist nghiệm thu có thể áp dụng

### A. Yêu cầu và môi trường

- [ ] Mỗi business invariant có acceptance criterion ID.
- [ ] Expected results và negative cases được viết rõ.
- [ ] Database là disposable/production-like cho DB-specific tests.
- [ ] JPA provider, JDBC driver, Java, DB versions được ghi lại.
- [ ] Schema migration được chạy từ nguồn có version.
- [ ] Test fixtures độc lập, không phụ thuộc thứ tự.
- [ ] Không dùng production credentials cho destructive tests.
- [ ] Không chạy parallel tests cùng global cleanup thiếu isolation.

### B. SQL và database

- [ ] Generated SQL của hot use cases được thu sau mapping/mapper.
- [ ] Bound parameter types đúng, sensitive values được masking.
- [ ] Tenant/authorization/soft-delete filters có bằng chứng.
- [ ] ORDER BY/pagination/limit đúng.
- [ ] SQL count không có N+1 ngoài budget.
- [ ] To-many fetch không gây row explosion/pagination sai.
- [ ] Flyway/schema history đúng.
- [ ] PK/UNIQUE/FK/CHECK/index definitions được kiểm tra.
- [ ] Constraint negative tests bắt đúng SQLState/cause.
- [ ] Query plan/row counts/buffers được so với workload đại diện.

### C. Giao dịch và concurrency

- [ ] Ghi Order, Lines, Inventory trong cùng local transaction.
- [ ] Commit được xác minh sau completion bằng context/connection mới.
- [ ] Flush không bị nhầm là commit.
- [ ] Insert rollback không giữ Order/Line mới.
- [ ] Stock update rollback khôi phục committed amount.
- [ ] Exception được phân loại đúng nguyên nhân.
- [ ] Sau failed persistence không reuse context cũ.
- [ ] Concurrent reservations không oversell.
- [ ] Tests dùng EntityManagers/connections riêng.
- [ ] Optimistic conflict bảo vệ stale writes theo contract.
- [ ] Retry sử dụng context mới và idempotency nếu cần.
- [ ] Lock timeout/deadlock behavior được test và document.
- [ ] Spring `@Transactional`/`@DataJpaTest` boundaries được hiểu đúng.

### D. Tính đúng dữ liệu

- [ ] Order total bằng Lines theo công thức nghiệp vụ.
- [ ] Stock available không âm sau commit.
- [ ] Số Orders confirmed không vượt inventory contract.
- [ ] Không có duplicated business keys theo tenant.
- [ ] Không có orphan OrderLines.
- [ ] Hai tenants không nhìn thấy dữ liệu chéo.
- [ ] Timezone/timestamp và decimal rounding đúng.
- [ ] ID/sequence và version semantics được kiểm tra.
- [ ] Nếu migration, đối soát keys/rows/aggregates theo watermark nhất quán.

### E. Hồ sơ bằng chứng

- [ ] Evidence IDs khớp AC IDs.
- [ ] Kết quả test/SQL/catalog/plan thật được lưu an toàn.
- [ ] Expected khác actual và status rõ ràng.
- [ ] Có build commit, migration version và test run ID.
- [ ] Failure logs giữ root cause và context đủ debug.
- [ ] Không phát tán secrets hoặc dữ liệu cá nhân trong artifacts.
- [ ] Có PASS/FAIL/BLOCKED/NOT RUN/INCONCLUSIVE đúng nghĩa.
- [ ] Những AC chưa được kiểm tra không bị đánh dấu PASS.
- [ ] Người đánh giá có thể tái lập bước chạy từ một DB sạch.

Checklist này là công cụ **thiết kế nghiệm thu**, không phải tuyên bố các bài test trong ví dụ đã được thực thi. Trong một dự án thật, từng dấu chọn phải gắn với lần chạy và evidence tương ứng.

---

## 106. Mẫu báo cáo nghiệm thu cuối cùng

```markdown
# JPA Persistence Acceptance Report

## Release context
- Commit: <commit-sha>
- Java / JPA / ORM: <versions>
- Database / JDBC: <versions>
- Migration: <schema-version>
- Environment: <test-or-staging>
- Run ID: <ci-run-id>

## Acceptance summary
| AC | Expected | Actual | Status | Evidence |
|----|----------|--------|--------|----------|
| AC-01 | Order+Line and stock committed | ... | ... | E-TXN-01 |
| AC-04 | All changes rolled back on fault | ... | ... | E-TXN-04 |
| AC-05 | Duplicate same-tenant order rejected | ... | ... | E-DB-05 |
| AC-09 | No oversell | ... | ... | E-CONC-09 |
| AC-12 | SQL count under budget | ... | ... | E-SQL-12 |
| AC-13 | Schema and migration valid | ... | ... | E-DDL-13 |

## Findings and blockers
- ...

## Residual risks
- ...

## Decision
- PASS / CONDITIONAL / FAIL / BLOCKED
- Reviewer:
- Evidence location:
- Decision date:
```

Mẫu phải được điền bằng số liệu thực tế. Nếu có acceptance criteria quan trọng chưa chạy hoặc fail, báo cáo không nên tự động kết luận “toàn bộ PASS”.

## 107. Ý nghĩa của nghiệm thu trong thực hành tổng hợp

Một bài thực hành JPA thành công không nhất thiết phải có nhiều annotations hay một repository siêu tổng quát. Quan trọng là chứng minh được một luồng nghiệp vụ tương đối thực tế:

```text
Requirement
    ↓
JPA model + domain invariants
    ↓
Database migrations + constraints
    ↓
Transaction-aware application service
    ↓
SQL produced by ORM
    ↓
Commit / rollback / concurrency outcomes
    ↓
Correct data returned by JPQL queries
    ↓
Tests + SQL/DB evidence
    ↓
Acceptance decision
```

Bằng chứng buộc người thực hành **đi qua ranh giới Java object → persistence context → SQL → database transaction → committed rows**, thay vì chỉ nhìn method call trong Java.

## Kết luận

**Nghiệm thu bằng bằng chứng SQL, giao dịch và kiểm thử tính đúng** là bước chuyển từ “viết code JPA có vẻ đúng” sang “có cơ sở kỹ thuật để tin dữ liệu được lưu và truy xuất đúng”.

Những nguyên tắc cần giữ:

- **SQL thật** là thứ database thực thi; JPQL, repository names và annotations chỉ là một phần thiết kế.
- **Schema thật** cần được kiểm chứng bằng migration history, catalog và negative tests, không chỉ `hibernate.hbm2ddl.auto=validate`.
- **`persist()` và `flush()` không phải commit**. Bằng chứng giao dịch phải có transaction completion và fresh-context/JDBC readback.
- **Rollback không khôi phục Java object state**, nên không dùng fields đang ở memory để kết luận về committed data.
- **Business invariants** như không oversell, total đúng, tenant isolation và order uniqueness cần kiểm tra cả positive, negative và concurrent cases.
- **`@Version`, pessimistic locks, unique constraints và transaction boundaries** phải được xác minh bằng hành vi, không chỉ có mặt trong source code.
- **N+1, pagination và execution plans** cần bằng chứng định lượng trên fixtures/workload đủ đại diện.
- **Mỗi AC phải có evidence và trạng thái rõ**; test chưa chạy không phải pass, mock test không thay database integration test.
- **An toàn và tái lập** là điều kiện của nghiệm thu: database disposable, không lộ secrets, fixture deterministic, metadata versions/CI run đầy đủ.

Công thức thực hành nên nhớ là: **yêu cầu → tiêu chí nghiệm thu → invariant → code + schema → SQL và transaction thực → assertion độc lập → evidence → quyết định pass/fail**.

Khi làm được điều đó, người học không chỉ chứng minh một thao tác JPA chạy thành công, mà còn chứng minh được **tại sao hệ thống đúng, đúng đến mức nào, và bằng chứng nào sẽ phát hiện nếu nó sai sau thay đổi tiếp theo**.
