# Phối hợp thủ tục lưu trữ với giao dịch đang có trong JPA

Một ứng dụng JPA thường lưu entity bằng `persist()`, dirty checking hoặc JPQL. Tuy nhiên, nhiều hệ thống vẫn sử dụng **stored procedure** để thực hiện nghiệp vụ đã được tối ưu bằng SQL/PLSQL/T-SQL, thao tác trên dữ liệu lớn, cập nhật tồn kho, ghi sổ kế toán hoặc tích hợp một hệ thống cơ sở dữ liệu lâu đời.

Vấn đề quan trọng không chỉ là gọi được procedure. **Nếu ứng dụng đang ở giữa một giao dịch, procedure sẽ tham gia giao dịch đó như thế nào?** Những thay đổi JPA chưa flush có được procedure nhìn thấy không? Một lệnh `CALL` thất bại có làm rollback các entity đã lưu trước đó không? Sau khi procedure cập nhật bảng, entity đã managed trong persistence context có tự đổi theo không? Nếu procedure tự `COMMIT` thì bên nào còn kiểm soát transaction?

Đây là các câu hỏi quyết định **tính nguyên tử, nhất quán và khả năng phục hồi** của một luồng nghiệp vụ. Ví dụ:

~~~text
Service tạo đơn hàng
    |
    v
BEGIN TRANSACTION
    |
    +--> JPA persist(PurchaseOrder)
    |
    +--> JPA flush() để SQL INSERT được gửi
    |
    +--> CALL reserve_stock(...) trong cùng transaction
    |
    +--> Kiểm tra kết quả, tiếp tục cập nhật entity
    |
    v
COMMIT nếu toàn bộ thành công
ROLLBACK nếu có lỗi
~~~

**Mục tiêu:** đơn hàng và tồn kho hoặc **cùng được commit**, hoặc **cùng bị rollback**. Điều này chỉ đúng nếu lời gọi procedure và các lệnh JPA thực sự dùng **cùng phạm vi giao dịch trên resource phù hợp** và procedure không tự tạo một ranh giới commit độc lập.

Bài học trình bày cách phối hợp `StoredProcedureQuery` với transaction `RESOURCE_LOCAL`, JTA và Spring; tương tác flush/commit; IN/OUT parameters và nhiều kết quả; persistence context stale; optimistic/pessimistic locking; lỗi, rollback, retry; các trường hợp database-specific và phương pháp kiểm thử bằng hai transaction thật.

## 1. Phân biệt lời gọi procedure với ranh giới transaction

Một stored procedure là chương trình lưu ở DBMS, có thể chứa nhiều câu SQL và control flow:

~~~sql
-- Dạng minh họa, cú pháp procedure thực tế phụ thuộc DBMS
PROCEDURE reserve_stock(item_id, quantity)
    UPDATE inventory_items ...
    INSERT inventory_events ...
END
~~~

Trong khi đó, **transaction** xác định phạm vi nguyên tử và cô lập cho những câu SQL được thực hiện.

Hai khái niệm không đồng nghĩa:

| Khái niệm | Câu hỏi nó trả lời |
| --- | --- |
| Stored procedure | Những thao tác SQL/logic database nào sẽ được chạy? |
| Transaction | Những thao tác nào sẽ commit hoặc rollback cùng nhau? |
| `EntityManager` | Entity nào đang managed và khi nào pending state được đồng bộ? |
| `StoredProcedureQuery` | JPA đăng ký parameter và gọi routine như thế nào? |
| Transaction manager | Ai bắt đầu, tham gia, commit và rollback transaction? |
| DB isolation/locking | Transaction khác thấy dữ liệu gì và tranh chấp được xử lý ra sao? |

Một procedure chỉ có một lệnh UPDATE vẫn có thể cần được gọi trong transaction của service. Ngược lại, một procedure chứa mười UPDATE **không tự chứng minh** rằng nó sẽ rollback cùng transaction ngoài nếu bên trong tự commit hoặc dùng connection/resource khác.

## 2. Bản đồ các tầng khi JPA gọi stored procedure

~~~text
┌────────────────────────────────────────────────────────────┐
│ Application Service                                        │
│ - Quyết định unit of work                                  │
│ - Kiểm tra nghiệp vụ, phân quyền, xử lý retry               │
└───────────────────────────┬────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────┐
│ Transaction Manager                                        │
│ RESOURCE_LOCAL / JTA / Spring                              │
│ - begin / join / commit / rollback                         │
└───────────────────────────┬────────────────────────────────┘
                            │ transaction-bound resource
                            ▼
┌────────────────────────────────────────────────────────────┐
│ JPA EntityManager                                          │
│ - Managed entities / first-level cache                     │
│ - Dirty checking / flush                                   │
│ - StoredProcedureQuery                                     │
└───────────────────────────┬────────────────────────────────┘
                            │ JDBC / CALL
                            ▼
┌────────────────────────────────────────────────────────────┐
│ Database                                                   │
│ - Procedure body chạy SQL                                  │
│ - Lock, MVCC, constraints, error state                     │
│ - Commit/rollback theo phạm vi transaction thực            │
└────────────────────────────────────────────────────────────┘
~~~

Trong một cấu hình đúng, EntityManager gắn với transaction hiện tại sử dụng database resource đã được transaction manager điều phối. SQL từ `em.flush()` và SQL của procedure được thực hiện trong **cùng giao dịch cơ sở dữ liệu**, đối với một database/resource tương ứng.

Điểm cần kiểm tra trong ứng dụng thực:

- EntityManager có tham gia transaction thực sự không?
- Procedure được gọi qua **EntityManager/connection đang tham gia transaction** hay qua một datasource/connection khác?
- Hệ thống có `read replica`, multi-datasource hoặc JTA/XA không?
- Stored procedure có tự commit, tự rollback, dùng autonomous transaction hoặc gọi resource khác không?
- Người gọi có chờ kết quả procedure trước khi quyết định commit không?

**Chỉ đặt annotation `@Transactional` trên method mà không xác minh các điều kiện trên là chưa đủ.**

## 3. Quy tắc cốt lõi: procedure tham gia transaction đang hoạt động

Trong cách sử dụng điển hình, nếu có một transaction hợp lệ đang hoạt động, `EntityManager` tham gia transaction ấy và `StoredProcedureQuery.execute()` thực hiện procedure trên resource được quản lý, những thao tác SQL transactional của procedure sẽ là **một phần của unit of work hiện tại**.

Ví dụ trình tự:

~~~text
T1: BEGIN
T2: INSERT purchase_order từ JPA
T3: CALL reserve_stock từ StoredProcedureQuery
T4: UPDATE purchase_order.status từ JPA
T5: COMMIT
~~~

Khi T5 commit thành công, thay đổi trên purchase_order và inventory cùng được xác nhận. Nếu tại T3 procedure báo lỗi rồi transaction bị rollback:

~~~text
T1: BEGIN
T2: INSERT purchase_order từ JPA
T3: CALL reserve_stock -> ERROR
T4: ROLLBACK
~~~

thì INSERT chưa commit ở T2 cũng bị hủy, **với điều kiện nó thuộc cùng một transaction/resource và không có cơ chế commit độc lập**.

### Procedure return không có nghĩa commit

Khi Java gọi:

~~~java
storedProcedure.execute();
~~~

và method trả về bình thường, điều đó có nghĩa lần thực thi procedure đã đến điểm mà provider/JDBC trả quyền điều khiển về ứng dụng. **Không suy ra transaction đã commit.**

Lock của các UPDATE trong procedure thường còn được giữ theo quy tắc của DBMS cho đến khi transaction hiện tại kết thúc, không nhất thiết được giải phóng ngay khi procedure return.

### Không xem stored procedure là “transaction lồng nhau” mặc định

Một lời gọi procedure bên trong transaction không tự tạo một transaction con độc lập có thể commit riêng và rollback riêng. Cơ chế nested transactions, savepoint, autonomous transactions khác nhau giữa DBMS; phải kiểm tra cụ thể nếu muốn sử dụng.

## 4. Phân biệt hai kiểu quản lý transaction trong JPA

JPA ứng dụng thường gặp hai mô hình:

| Mô hình | Ai kiểm soát ranh giới? | API/cách dùng chính |
| --- | --- | --- |
| `RESOURCE_LOCAL` | Ứng dụng qua EntityManager | `EntityTransaction.begin()/commit()/rollback()` |
| JTA-managed | Container/JTA transaction manager | `@Transactional`, `UserTransaction` hoặc API hạ tầng phù hợp |

Spring Data JPA/Spring Transaction cũng có thể quản lý transaction ứng dụng thông qua `@org.springframework.transaction.annotation.Transactional`, sử dụng một `EntityManager` transaction-bound ở bên dưới.

**Không sử dụng `em.getTransaction().begin()` trên một JTA-managed EntityManager**; `getTransaction()` chỉ thích hợp cho resource-local EntityManager.

### Ai là người sở hữu commit?

Một service có transaction đang mở thường phải là nơi quyết định **thành công toàn bộ unit of work**. Repository/procedure adapter không nên tự ý commit, bởi nó không biết còn bao nhiêu bước nghiệp vụ của caller cần được thực hiện trước commit.

Một sơ đồ tốt:

~~~text
Service / Transaction boundary
      |
      +-- Repository JPA: persist Order
      |
      +-- Procedure adapter: CALL reserve_stock
      |
      +-- Repository JPA: cập nhật trạng thái Order
      |
      +-- COMMIT hoặc ROLLBACK toàn bộ
~~~

Sơ đồ dễ gây lỗi:

~~~text
Service transaction
      |
      +-- Repository: persist Order
      |
      +-- Procedure adapter:
      |     - mở connection thứ hai
      |     - CALL
      |     - COMMIT riêng
      |
      +-- Service sau đó ROLLBACK
            -> Inventory vẫn đã thay đổi!
~~~

Đây là lỗi **tách transaction ngoài ý định**, không phải lỗi ánh xạ entity.

## 5. Mô hình ví dụ: tạo đơn và giữ tồn kho

Để giải thích cụ thể, giả sử hệ thống có:

~~~text
inventory_items
--------------------------------------------------------
id (PK) | tenant_id | sku | available | version

purchase_orders
--------------------------------------------------------
id (PK) | tenant_id | item_id (FK) | quantity | status
~~~

Một đơn hàng yêu cầu đặt trước N sản phẩm. Service lưu đơn, sau đó gọi procedure giảm số lượng `available`. Nếu hết hàng hoặc gặp lỗi, **toàn bộ transaction phải rollback**, không để tồn tại đơn không có tồn kho tương ứng.

### 5.1. DDL PostgreSQL minh họa

~~~sql
CREATE TABLE inventory_items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    sku VARCHAR(80) NOT NULL,
    available INTEGER NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT uq_inventory_tenant_sku
        UNIQUE (tenant_id, sku),
    CONSTRAINT ck_inventory_available
        CHECK (available >= 0)
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    item_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    status VARCHAR(30) NOT NULL,
    CONSTRAINT ck_order_quantity
        CHECK (quantity > 0),
    CONSTRAINT fk_order_item
        FOREIGN KEY (item_id) REFERENCES inventory_items(id)
);
~~~

Đây là schema **tối giản để học transaction**, không phải hệ thống đặt hàng production đầy đủ. Một hệ thống thực còn cần đơn nhiều dòng, kiểm soát idempotency, giá tại thời điểm mua, thanh toán, ledger, audit, trạng thái giữ chỗ và ràng buộc tenant đối với khóa ngoại.

### 5.2. Enum trạng thái đơn

~~~java
package com.example.inventory;

public enum OrderStatus {
    PENDING,
    RESERVED,
    CANCELLED
}
~~~

### 5.3. Entity InventoryItem

~~~java
package com.example.inventory;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "inventory_items")
public class InventoryItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(nullable = false, length = 80)
    private String sku;

    @Column(nullable = false)
    private int available;

    @Version
    private Long version;

    protected InventoryItem() {
    }

    public Long getId() {
        return id;
    }

    public Long getTenantId() {
        return tenantId;
    }

    public int getAvailable() {
        return available;
    }

    public Long getVersion() {
        return version;
    }
}
~~~

### 5.4. Entity PurchaseOrder

~~~java
package com.example.inventory;

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

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "item_id", nullable = false)
    private InventoryItem item;

    @Column(nullable = false)
    private int quantity;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 30)
    private OrderStatus status;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(
            long tenantId,
            InventoryItem item,
            int quantity) {

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "quantity phải dương");
        }
        this.tenantId = tenantId;
        this.item = java.util.Objects.requireNonNull(item);
        this.quantity = quantity;
        this.status = OrderStatus.PENDING;
    }

    public Long getId() {
        return id;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public void markReserved() {
        if (status != OrderStatus.PENDING) {
            throw new IllegalStateException(
                "Order không ở trạng thái PENDING");
        }
        status = OrderStatus.RESERVED;
    }
}
~~~

Quan hệ `@ManyToOne` cho phép PurchaseOrder tham chiếu InventoryItem; `@Version` ở InventoryItem sẽ có ý nghĩa khi cả JPA và procedure cùng tuân thủ cơ chế version. Entity và schema ở đây cố tình đơn giản để thấy các ranh giới flush/call/commit.

## 6. Viết procedure thực hiện UPDATE tồn kho nguyên tử

Đối với PostgreSQL, ta có thể tạo procedure bằng PL/pgSQL:

~~~sql
CREATE OR REPLACE PROCEDURE reserve_stock(
    IN p_tenant_id BIGINT,
    IN p_item_id BIGINT,
    IN p_quantity INTEGER
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_quantity IS NULL OR p_quantity <= 0 THEN
        RAISE EXCEPTION
            'Invalid requested quantity: %', p_quantity;
    END IF;

    UPDATE inventory_items
    SET available = available - p_quantity,
        version = version + 1
    WHERE id = p_item_id
      AND tenant_id = p_tenant_id
      AND available >= p_quantity;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Item unavailable or insufficient stock';
    END IF;
END;
$$;
~~~

Đây là **cú pháp PostgreSQL**, không phải SQL portable cho Oracle, MySQL hay SQL Server. Procedure không chứa `COMMIT` hoặc `ROLLBACK`, nên khi được gọi trong transaction hợp lệ, UPDATE thuộc transaction của caller.

### Vì sao kiểm tra available ngay trong UPDATE?

Không nên viết:

~~~text
SELECT available
if available >= quantity:
    UPDATE available = previouslyReadValue - quantity
~~~

mà không có biện pháp bảo vệ cạnh tranh, vì hai transaction có thể cùng đọc tồn kho cũ rồi ghi đè.

Procedure dùng:

~~~sql
UPDATE inventory_items
SET available = available - p_quantity
WHERE id = p_item_id
  AND available >= p_quantity;
~~~

Đây là thao tác cập nhật có điều kiện trên **chính row tồn kho**. Database điều phối khóa ghi/xung đột theo isolation và DBMS, tránh nhiều lỗi check-then-act đơn giản. Constraint `CHECK (available >= 0)` bổ sung lớp bảo vệ tại database.

### Vì sao tăng version?

`InventoryItem` có `@Version`. Procedure làm thay đổi row bên ngoài cơ chế dirty checking JPA; việc tăng `version` theo giao thức thống nhất giúp các transaction JPA giữ phiên bản cũ phát hiện xung đột khi cập nhật sau đó.

Nếu quy ước version của hệ thống khác (trigger hoặc DB-managed version), procedure và provider phải được thiết kế nhất quán. **Không giả định mọi native UPDATE tự tăng version của JPA**.

### Điều gì còn chưa được giải quyết?

Procedure không ghi idempotency key hay reservation history. Nếu client gửi cùng request hai lần trong **hai transaction thành công khác nhau**, tồn kho vẫn có thể bị trừ hai lần. Production cần khóa yêu cầu và tính idempotent nếu nghiệp vụ yêu cầu.

## 7. Gọi procedure bằng StoredProcedureQuery

`StoredProcedureQuery` thuộc `jakarta.persistence`. Để gọi procedure ba tham số IN:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.ParameterMode;
import jakarta.persistence.StoredProcedureQuery;

public void reserveStock(
        EntityManager em,
        long tenantId,
        long itemId,
        int quantity) {

    StoredProcedureQuery call =
        em.createStoredProcedureQuery("reserve_stock");

    call.registerStoredProcedureParameter(
        1, Long.class, ParameterMode.IN);
    call.registerStoredProcedureParameter(
        2, Long.class, ParameterMode.IN);
    call.registerStoredProcedureParameter(
        3, Integer.class, ParameterMode.IN);

    call.setParameter(1, tenantId);
    call.setParameter(2, itemId);
    call.setParameter(3, quantity);

    call.execute();
}
~~~

Điểm quan trọng:

- `createStoredProcedureQuery("reserve_stock")` nhận **tên procedure của database**, không phải chuỗi `"CALL reserve_stock(...)"`.
- `registerStoredProcedureParameter(...)` khai báo vị trí, Java type và parameter mode.
- `setParameter(...)` truyền giá trị IN trước khi thực thi.
- `execute()` gọi routine; nó **không tự commit transaction**.
- `StoredProcedureQuery` được tạo từ `EntityManager` đang tham gia unit of work.

Khả năng gọi PostgreSQL procedure bằng JDBC `CallableStatement`, cách driver diễn dịch `CALL` và cách provider hỗ trợ `StoredProcedureQuery` có thể khác theo phiên bản. Khi chạy thực tế, cần xác nhận **JPA provider, PostgreSQL JDBC driver và routine kind (procedure hay function)** tương thích; ví dụ PL/pgSQL này không bảo đảm chạy nguyên vẹn trên mọi stack JPA.

### execute() trả boolean có nghĩa gì?

Chữ ký:

~~~java
boolean hasResultSet = call.execute();
~~~

Giá trị boolean thể hiện **loại kết quả đầu tiên**:

- `true`: kết quả đầu tiên là result set.
- `false`: kết quả đầu tiên không phải result set, có thể là update count hoặc không có result.

**Không viết `if (!call.execute()) throw ...` để suy ra procedure thất bại.** Với procedure chỉ UPDATE, `execute()` trả `false` vẫn hoàn toàn có thể là thực thi thành công.

Lỗi thực thi thường được biểu diễn bằng exception thích hợp của JPA/provider/JDBC, không bằng boolean thành công/thất bại.

## 8. Resource-local: gọi procedure trong transaction đang mở

Ví dụ đầy đủ với `EntityManagerFactory` RESOURCE_LOCAL:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;

public Long createOrderAndReserve(
        EntityManagerFactory emf,
        long tenantId,
        long itemId,
        int quantity) {

    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        InventoryItem item =
            em.find(InventoryItem.class, itemId);

        if (item == null
                || !java.util.Objects.equals(
                    item.getTenantId(), tenantId)) {
            throw new IllegalArgumentException(
                "Không tìm thấy item trong tenant");
        }

        PurchaseOrder order =
            new PurchaseOrder(tenantId, item, quantity);
        em.persist(order);

        // INSERT order trước khi procedure xử lý tiếp.
        em.flush();

        reserveStock(em, tenantId, itemId, quantity);

        // Procedure UPDATE row mà item managed đã nạp.
        em.refresh(item);

        order.markReserved();

        tx.commit();
        return order.getId();

    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    } finally {
        em.close();
    }
}
~~~

Method `reserveStock(...)` là helper ở mục 7. Ví dụ giả sử helper được gọi trong cùng class hoặc được truy cập qua dependency thích hợp.

### Phân tích từng mốc

| Mốc | JPA/DB trạng thái |
| --- | --- |
| `tx.begin()` | Transaction bắt đầu |
| `em.find(item)` | Item trở thành managed trong context |
| `em.persist(order)` | Order được quản lý, INSERT có thể pending |
| `em.flush()` | SQL pending được đồng bộ trong transaction |
| `reserveStock(...)` | Procedure UPDATE tồn kho trong cùng transaction |
| `em.refresh(item)` | Nạp lại tồn kho và version vào item managed |
| `order.markReserved()` | Order dirty; SQL UPDATE có thể được phát tại commit flush |
| `tx.commit()` | Đồng bộ pending state và commit transaction |
| `tx.rollback()` khi lỗi | Hủy các thay đổi transactional chưa commit |

### Tại sao không begin/commit bên trong reserveStock?

Vì service đang sở hữu transaction. Nếu helper tự bắt đầu/commit một transaction khác, đơn và tồn kho không còn thuộc cùng unit of work. Helper nên chỉ làm việc với `EntityManager` của caller và giả định transaction hiện tại đã được thiết lập đúng.

### Vì sao có flush rồi mới call?

Service cần database nhìn được INSERT Order trước khi procedure chạy, nếu procedure có thể đọc/đối chiếu Order hoặc thao tác khác phụ thuộc pending JPA state. Trong procedure ví dụ, UPDATE inventory không trực tiếp đọc Order, nên `flush()` được đặt để minh họa **điểm đồng bộ tường minh**. Không phải mọi procedure bắt buộc phải flush toàn bộ context trước khi chạy; quyết định dựa trên phụ thuộc dữ liệu.

## 9. Pending changes của JPA và dữ liệu procedure nhìn thấy

Giả sử:

~~~java
PurchaseOrder order = new PurchaseOrder(...);
em.persist(order);

StoredProcedureQuery sp =
    em.createStoredProcedureQuery("inspect_new_orders");
sp.execute();
~~~

Một entity mới managed có thể **chưa được INSERT xuống database** tại thời điểm gọi procedure. Việc provider tự flush trước native/procedure call phụ thuộc flush mode, synchronization rules và provider.

Nếu procedure phải thấy dữ liệu mới:

~~~java
em.persist(order);
em.flush();
sp.execute();
~~~

Sau `flush()`, những lệnh SQL pending đã được JPA gửi theo quy tắc đồng bộ. Procedure trên **cùng transaction/resource** có thể đọc những thay đổi đã thực thi của transaction chính nó theo semantics của database.

### Flush khác commit

~~~text
T1: BEGIN
T2: persist(Order)       -> state trong RAM
T3: flush                -> INSERT trong DB transaction
T4: CALL                 -> procedure nhìn dữ liệu của T1
T5: ROLLBACK             -> Order INSERT và stock UPDATE bị hủy
~~~

Ngay sau T3/T4, transaction khác **không mặc nhiên thấy Order chưa commit**, vì visibility của dữ liệu phụ thuộc isolation và DBMS. **Flush chỉ là đồng bộ trong transaction, không phải xác nhận giao dịch.**

### Không cần flush lặp lại vô tội vạ

Flush có thể gây:

- Kiểm tra constraint và phát exception sớm.
- Gửi SQL sớm, giữ lock lâu hơn.
- Phá cơ hội batching nếu chèn điểm flush không cần thiết.
- Đồng bộ **toàn bộ pending state trong context**, không chỉ Order đang quan tâm.

Đặt flush ở **ranh giới phụ thuộc dữ liệu thật** là chiến lược phù hợp hơn gọi flush trước mọi stored procedure.

## 10. Procedure UPDATE nhưng entity managed vẫn đang giữ state cũ

Một lỗi phổ biến:

~~~java
InventoryItem item =
    em.find(InventoryItem.class, itemId);

int before = item.getAvailable();  // 20

reserveStock(em, tenantId, itemId, 5);

System.out.println(item.getAvailable());
// Có thể vẫn là 20 thay vì 15.
~~~

Lý do: stored procedure thay đổi **database row trực tiếp**, không gọi setter trên Java object `item` và không thực hiện dirty checking thông qua JPA entity-state transitions.

### Persistence context là identity map, không phải live view

~~~text
JPA persistence context
  InventoryItem#10: available=20, version=3

Stored procedure trên DB row
  UPDATE inventory_items
     available=15, version=4

Sau CALL, trước refresh:
  Java item có thể vẫn available=20, version=3
  DB transaction có row available=15, version=4
~~~

SQL đúng, transaction đúng, nhưng Java object vẫn **stale**. Điều này khác với vấn đề transaction khác không nhìn thấy write chưa commit.

## 11. Dùng refresh() để đồng bộ một entity sau procedure

Khi procedure đã cập nhật InventoryItem, ta có thể yêu cầu:

~~~java
em.refresh(item);
~~~

`refresh()` nạp lại persistent state của entity managed từ database theo transaction hiện tại. Trong ví dụ:

~~~text
Trước CALL:    item.available = 20, version = 3
Sau CALL DB:   row.available = 15, version = 4
Sau refresh:   item.available = 15, version = 4
~~~

### Khi nào refresh có ích?

- Procedure cập nhật một entity mà service sẽ **tiếp tục đọc hoặc sửa**.
- Procedure cập nhật `@Version` và service cần state version mới.
- Cần bảo đảm object managed phản ánh thay đổi đã thực thi qua SQL trực tiếp.

### Cảnh báo về refresh

- `refresh()` dùng trên **managed entity**, không phải DTO hoặc entity detached tùy tiện.
- Nó có thể **ghi đè thay đổi chưa flush của chính entity**.
- Nó vẫn chịu transaction isolation/snapshot và provider/database semantics.
- Nó không tự refresh **mọi entity khác** bị procedure cập nhật.
- Nếu SQL xóa row, refresh có thể thất bại vì entity không còn tồn tại.

Ví dụ rủi ro:

~~~java
item.changeDisplayName("Tên mới"); // Giả sử field và method này tồn tại
reserveStock(em, tenantId, itemId, quantity);
em.refresh(item); // Thay đổi displayName pending có thể bị mất!
~~~

Vì vậy nếu phải refresh:

1. Xác định entity nào có pending changes.
2. Flush những thay đổi cần giữ trước khi procedure thay row.
3. Thực thi procedure.
4. Refresh đúng các entity cần tiếp tục sử dụng.
5. Tránh cả JPA và procedure cùng sửa một field mà không có quy ước rõ.

## 12. Dùng clear() khi procedure ảnh hưởng nhiều entity

Nếu procedure cập nhật hàng nghìn Product/InventoryItem, `refresh()` từng entity đang managed có thể tốn nhiều query.

Một chiến lược:

~~~java
em.flush();
callProcedure(em);
em.clear();
~~~

`em.clear()` detach **toàn bộ managed entities** khỏi context. Những lần `find()` sau có thể nạp object mới theo isolation/cache semantics.

### Hệ quả quan trọng

Sau:

~~~java
InventoryItem item = em.find(InventoryItem.class, id);
em.clear();
~~~

`item` là detached. Sửa field của `item` rồi mong JPA tự dirty-check trong transaction là **sai**.

Nếu cần tiếp tục:

~~~java
InventoryItem fresh = em.find(InventoryItem.class, id);
// Dùng fresh là managed reference mới.
~~~

### Clear không phải rollback

`em.clear()` không đảo ngược SQL đã flush. Những thay đổi đã ghi trong transaction vẫn thuộc DB transaction và sẽ commit/rollback theo ranh giới thực.

### Clear không đảm bảo đọc “mới nhất tuyệt đối”

Một SELECT mới có thể đọc theo snapshot/isolation đã bắt đầu trước đó, hoặc bị ảnh hưởng cache/replica. Clear chỉ xử lý **trạng thái managed trong RAM**.

## 13. Tránh JPA dirty checking ghi đè kết quả procedure

Giả sử:

~~~java
InventoryItem item = em.find(InventoryItem.class, id);
// available = 20, version = 3

reserveStock(em, tenantId, id, 5);
// Trong DB: available=15, version=4

// item vẫn stale; service tiếp tục sửa một field khác:
item.changeSomeProperty(...);

tx.commit();
~~~

Khi commit, provider flush entity đang dirty. Nếu không đồng bộ state/version sau procedure:

- Với `@Version`, UPDATE dựa trên version cũ có thể bị từ chối bằng optimistic lock conflict.
- Nếu không có version hoặc chiến lược kiểm tra phù hợp, một UPDATE từ entity stale có thể **ghi đè một phần state procedure vừa đổi**, tùy SQL do provider sinh.
- Nếu provider chỉ cập nhật các field dirty hoặc có cơ chế riêng, outcome có thể khác, nhưng **không được thiết kế dựa trên giả định “JPA luôn chỉ update đúng một cột”**.

### Quy tắc thiết kế

Với một row được cả JPA và procedure cập nhật trong cùng transaction, cần **một giao thức phối hợp rõ**:

1. JPA flush pending changes trước CALL nếu chúng cần được bảo toàn và procedure cần nhìn.
2. Procedure cập nhật row, version và mọi constraint theo domain.
3. Refresh entity trước khi tiếp tục sửa nó qua JPA.
4. Commit ở transaction boundary ngoài.

Hoặc tốt hơn, tách quyền sở hữu cập nhật: một operation cụ thể giao row/field đó cho **JPA hoặc procedure**, tránh hai cơ chế ghi lẫn nhau khi không cần.

## 14. @Version và optimistic locking qua ranh giới CALL

Trong JPA:

~~~java
@Version
private Long version;
~~~

cho phép provider kiểm tra cập nhật cạnh tranh của managed entity, ví dụ SQL có điều kiện version.

Procedure đang làm:

~~~sql
UPDATE inventory_items
SET available = available - p_quantity,
    version = version + 1
WHERE id = p_item_id
  AND tenant_id = p_tenant_id
  AND available >= p_quantity;
~~~

Điều này giúp những EntityManager khác đang giữ version cũ phát hiện row đã thay đổi khi chúng UPDATE tiếp bằng JPA.

### Không nên gọi procedure bỏ qua version mà lại trông chờ @Version

Sai về quy ước:

~~~sql
UPDATE inventory_items
SET available = available - 1
WHERE id = ?;
~~~

Nếu procedure cập nhật row mà **không tăng version**, transaction JPA khác có thể có version không đổi và không phát hiện conflict như kỳ vọng. Muốn đồng bộ chiến lược optimistic locking, hãy đưa tăng/check version vào các đường ghi native phù hợp.

### Transaction nội bộ không thay thế optimistic checking đa transaction

Cho dù JPA và procedure chạy cùng transaction, hai request khác nhau vẫn có thể cạnh tranh. `@Version`, row lock, atomic conditional UPDATE, isolation và constraint phối hợp để giải quyết lớp concurrency tương ứng.

Một procedure cập nhật nhiều hàng có thể phá invariant đa hàng nếu isolation không đủ mạnh; `@Version` trên từng hàng không bảo vệ tất cả hiện tượng write skew.

## 15. Atomic UPDATE của procedure và hai giao dịch cạnh tranh

Giả sử tồn kho ban đầu bằng 5; T1 muốn giữ 4, T2 cũng muốn giữ 4.

~~~text
T1                                 T2
--------------------------------   --------------------------------
BEGIN                              BEGIN
CALL reserve_stock(..., 4)
  -> UPDATE available 5 -> 1
  -> giữ write lock             CALL reserve_stock(..., 4)
                                  -> có thể chờ row lock
COMMIT
                                Sau khi có thể thực thi UPDATE:
                                  available >= 4 không còn đúng
                                  UPDATE 0 rows, procedure báo lỗi
                                ROLLBACK
~~~

Kết quả mong muốn:

~~~text
available = 1
chỉ một giao dịch giữ được 4 đơn vị
~~~

Thao tác điều kiện trên cùng row và khóa/serialization do database thực thi giúp tránh việc cả hai transaction cùng dựa trên giá trị 5 cũ để trừ.

### Không suy luận từ ví dụ rằng mọi isolation cho mọi business rule đều an toàn

Với invariant liên quan nhiều row, ví dụ “tổng số hàng được đặt không vượt một hạn mức nhóm”, hai procedure có thể sửa các row khác nhau mà vẫn phá tổng. Lúc đó có thể cần lock một tài nguyên chung, constraint DB, SERIALIZABLE isolation hoặc thiết kế dữ liệu khác.

### Lỗi concurrency phát sinh ở đâu?

Có thể xảy ra:

- Ngay trong `call.execute()` do procedure `RAISE EXCEPTION`, deadlock, lock timeout.
- Trong bước flush sau đó do optimistic conflict hoặc constraint.
- Khi commit transaction do DB kiểm tra xung đột/deferred constraint.

Không chỉ try/catch quanh `execute()` rồi giả định commit chắc chắn thành công.

## 16. Spring @Transactional: procedure tham gia giao dịch caller

Trong ứng dụng Spring Data JPA, một service có thể mở hoặc tham gia transaction:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.ParameterMode;
import jakarta.persistence.StoredProcedureQuery;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public Long createAndReserve(
            long tenantId,
            long itemId,
            int quantity) {

        InventoryItem item =
            em.find(InventoryItem.class, itemId);

        if (item == null
                || !java.util.Objects.equals(
                    item.getTenantId(), tenantId)) {
            throw new IllegalArgumentException(
                "Item không thuộc tenant");
        }

        PurchaseOrder order =
            new PurchaseOrder(tenantId, item, quantity);
        em.persist(order);

        // Nếu procedure cần nhìn INSERT/UPDATE pending:
        em.flush();

        StoredProcedureQuery sp =
            em.createStoredProcedureQuery("reserve_stock");
        sp.registerStoredProcedureParameter(
            1, Long.class, ParameterMode.IN);
        sp.registerStoredProcedureParameter(
            2, Long.class, ParameterMode.IN);
        sp.registerStoredProcedureParameter(
            3, Integer.class, ParameterMode.IN);

        sp.setParameter(1, tenantId);
        sp.setParameter(2, itemId);
        sp.setParameter(3, quantity);
        sp.execute();

        em.refresh(item);
        order.markReserved();
        return order.getId();
    }
}
~~~

Ở đây `@Transactional` là **annotation của Spring**, không phải annotation mặc định của JPA. Khi method được gọi qua transaction proxy phù hợp:

1. Spring bắt đầu transaction mới hoặc tham gia transaction hiện có theo propagation.
2. EntityManager transaction-bound tham gia transaction.
3. JPA INSERT, CALL và UPDATE thuộc cùng unit of work/resource.
4. Spring quyết định commit/rollback khi method kết thúc.

### Service không nên tự commit

Không gọi:

~~~java
em.getTransaction().commit();
~~~

trong method này, bởi EntityManager do Spring quản lý và transaction boundary thuộc transaction manager. Tương tự, repository adapter chỉ gọi procedure, không tạo transaction mới nếu nghiệp vụ yêu cầu tham gia outer transaction.

### Default rollback rule

Với Spring `@Transactional` mặc định, unchecked `RuntimeException`/`Error` thường kích hoạt rollback; checked exceptions cần cấu hình `rollbackFor` khi muốn rollback. Đối với procedure, provider thường ném một dạng unchecked `PersistenceException` hoặc exception do Spring chuyển đổi, nhưng ứng dụng **không nên dựa vào việc mọi lỗi procedure luôn có cùng loại exception**.

Ví dụ nếu service có checked exception nghiệp vụ:

~~~java
@Transactional(rollbackFor = ReservationFailedException.class)
public void reserve(...) throws ReservationFailedException {
    // ...
}
~~~

Đây là ví dụ Spring-specific; `ReservationFailedException` là class checked exception do ứng dụng định nghĩa. Cần xác định rule rollback thực sự và không che giấu lỗi bằng catch rồi return thành công.

## 17. Propagation.REQUIRED: tham gia transaction đã tồn tại

Spring `@Transactional` mặc định dùng propagation `REQUIRED`:

~~~text
CheckoutService.checkout()       -- đã có transaction
    |
    +-- OrderService.createOrder()
    |
    +-- InventoryService.reserveStock()
    |     @Transactional(REQUIRED)
    |     -> tham gia transaction hiện tại
    |
    +-- PaymentRecordService.persist()
    |
    v
CheckoutService trả về
    -> transaction ngoài commit hoặc rollback
~~~

Điều quan trọng: method reserveStock có annotation `@Transactional` **không có nghĩa nó tự commit khi method return**, nếu nó đang tham gia outer transaction.

### Khi outer transaction rollback

Nếu tất cả thao tác sử dụng cùng transaction, một lỗi xảy ra **sau** procedure cũng có thể khiến UPDATE stock bị rollback.

~~~text
BEGIN outer transaction
  persist Order
  CALL reserve_stock  -> thành công
  persist PaymentRecord
  validation fails
ROLLBACK
=> Order, stock, PaymentRecord cùng bị hủy
~~~

Đây chính là ý nghĩa “phối hợp thủ tục với giao dịch đang có”.

### Cẩn trọng với self-invocation

Trong Spring proxy-based AOP phổ biến:

~~~java
public void checkout() {
    this.reserveStock(); // Gọi nội bộ cùng object
}

@Transactional
public void reserveStock() {
    // ...
}
~~~

lời gọi `this.reserveStock()` có thể không đi qua transaction proxy, khiến annotation không được áp dụng như kỳ vọng. Cần xác định transaction được tạo ở method entrypoint thực sự, không chỉ nhìn annotation trong source.

## 18. Propagation.REQUIRES_NEW: khác “tham gia transaction đang có”

Một anti-pattern nguy hiểm nếu mục tiêu là nguyên tử toàn bộ:

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void reserveStock(...) {
    // CALL reserve_stock(...)
}
~~~

Với Spring transaction manager hỗ trợ, `REQUIRES_NEW` thường **tạm ngưng transaction ngoài và mở một transaction vật lý mới**:

~~~text
Outer Transaction A
  persist(Order) chưa commit
  |
  +-- Inner Transaction B (REQUIRES_NEW)
        CALL reserve_stock
        COMMIT B
  |
  Outer service gặp lỗi
  ROLLBACK A

Kết quả:
  stock đã trừ (B commit)
  Order bị rollback (A rollback)
~~~

Nếu muốn Order và stock cùng nguyên tử, đây là cấu hình **sai mục tiêu**.

### Khi REQUIRES_NEW có thể được dùng?

Ví dụ ghi một audit record được thiết kế có thể tồn tại kể cả khi outer transaction rollback — nhưng đây là **quyết định nghiệp vụ khác**, cần cân nhắc dữ liệu audit có thể không tương ứng một Order đã commit.

Thêm nữa, Inner transaction riêng có thể **không đọc được các INSERT chưa commit** của Outer transaction A theo isolation thông thường, và có thể phải chờ lock do A nắm. Không mở REQUIRES_NEW chỉ để “ép CALL chạy ngay” nếu procedure phụ thuộc pending data của A.

## 19. Propagation.NESTED và savepoint không phải portable JPA

Một câu hỏi phổ biến:

> Nếu procedure thất bại, có thể rollback riêng phần procedure nhưng vẫn giữ phần JPA đã lưu trước đó không?

Ở một số database có **savepoint**, có thể rollback tới một điểm trong transaction:

~~~text
BEGIN
  INSERT order
  SAVEPOINT before_procedure
  CALL some_optional_procedure
  -- Nếu lỗi có thể phục hồi bằng savepoint:
  ROLLBACK TO SAVEPOINT before_procedure
  -- Tiếp tục transaction ngoài trong điều kiện DB cho phép
COMMIT
~~~

Nhưng:

- JPA `EntityTransaction` không cung cấp API savepoint portable theo cách JDBC `Connection.setSavepoint()`.
- Spring `Propagation.NESTED` phụ thuộc transaction manager và database; không thể giả định `JpaTransactionManager` hỗ trợ đầy đủ nested semantics cho mọi thay đổi EntityManager.
- Rollback savepoint tại database không tự làm **persistence context Java quay lại trạng thái trước savepoint**.
- Một lỗi DB có thể làm transaction không còn dùng được nếu không có savepoint hợp lệ được thiết lập đúng trước đó.

Vì vậy, **không tự coi CALL là một nested transaction có rollback riêng**. Nếu use case yêu cầu recovery một phần, hãy thiết kế và kiểm thử cụ thể trên DBMS/transaction manager đang sử dụng.

## 20. JTA: đồng bộ procedure với transaction do container quản lý

Trong Jakarta EE, có thể sử dụng:

~~~java
import jakarta.inject.Inject;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.transaction.Transactional;

public class CheckoutService {

    @PersistenceContext
    private EntityManager em;

    @Inject
    private InventoryProcedureAdapter inventory;

    @Transactional
    public void checkout(...) {
        // persist Order
        // inventory.reserveStock(...) gọi qua cùng transaction context
        // persist các entity liên quan
    }
}
~~~

Annotation ở đây là `jakarta.transaction.Transactional`. JTA/container điều phối transaction; JPA EntityManager phải tham gia transaction theo cấu hình persistence unit.

### Không dùng resource-local API ở JTA

Sai:

~~~java
EntityTransaction tx = em.getTransaction();
tx.begin(); // Không phù hợp với JTA-managed EntityManager.
~~~

Cách đúng là để container, `UserTransaction` (khi phù hợp) hoặc transaction manager quản lý ranh giới, rồi gọi procedure qua EntityManager được enlist.

### Nếu EntityManager không tự tham gia?

Một số mô hình như unsynchronized persistence context có quy tắc tham gia transaction riêng. JPA cung cấp `joinTransaction()` trong những tình huống phù hợp. Nhưng không gọi `joinTransaction()` bừa bãi như một cách chữa mọi lỗi: phải biết **EntityManager có loại synchronization nào, transaction nào đang active và datasource có được enlist không**.

### JTA có nghĩa mọi resource cùng serializable?

Không. JTA điều phối unit of work và khả năng tham gia của các resources, nhưng **isolation level của database** vẫn do DBMS, datasource và môi trường quyết định. Nếu có nhiều database dùng XA, cần cấu hình transaction manager và driver/resource hỗ trợ thực sự; một `@Transactional` không tự biến HTTP request hoặc email thành XA participant.

## 21. Procedure gọi qua DataSource/JdbcTemplate khác có cùng transaction không?

Giả sử:

~~~java
@Transactional
public void checkout() {
    em.persist(order);
    jdbcTemplate.execute("CALL reserve_stock(...)");
}
~~~

Liệu JPA và JdbcTemplate có dùng cùng transaction?

**Câu trả lời phụ thuộc cấu hình.**

Trong Spring, một số tổ hợp `JpaTransactionManager`, DataSource, JdbcTemplate và transaction-aware connection có thể cùng tham gia transaction của resource tương ứng, **nếu được cấu hình và sử dụng đúng cách**. Nhưng không được suy luận từ tên method `execute`:

- JDBC đang lấy connection từ DataSource nào?
- EntityManager được cấu hình trên DataSource nào?
- JDBC connection có được transaction manager ràng buộc/enlist không?
- Có gọi `DriverManager.getConnection()` tạo connection ngoài pool/manager không?
- Có nhiều transaction managers với qualifiers khác nhau không?

### Anti-pattern: mở connection riêng

~~~java
Connection c = DriverManager.getConnection(url, user, pwd);
c.setAutoCommit(true);
// CALL reserve_stock bằng c
~~~

Nếu đây là connection **khác transaction của JPA**, procedure có thể auto-commit ngay, trong khi `em.persist(order)` ở transaction ngoài chưa commit. Lỗi sau đó sẽ không rollback cả hai như mong muốn.

### Khuyến nghị

Nếu yêu cầu phối hợp chặt với entity trong cùng unit of work, ưu tiên **StoredProcedureQuery tạo từ chính transaction-bound EntityManager**. Nếu phải dùng JDBC trực tiếp để khai thác tính năng provider/driver không hỗ trợ, cần kiểm chứng cùng transaction resource và transaction manager bằng integration test.

## 22. Procedure có tự COMMIT hay ROLLBACK không?

Đây là một điểm **phụ thuộc DBMS** rất lớn.

### Trường hợp lý tưởng

Procedure chỉ thực hiện DML và để **caller làm chủ commit**:

~~~text
BEGIN bởi service
  CALL procedure: UPDATE + INSERT
  JPA: UPDATE entity
COMMIT bởi service
~~~

### Trường hợp nguy hiểm

Procedure tự quyết định:

~~~text
PROCEDURE:
   UPDATE inventory
   COMMIT
~~~

Tùy DBMS, cấu trúc gọi và cơ chế transaction, `COMMIT` trong procedure có thể:

- Không được phép trong transaction block hiện có.
- Commit transaction/session hiện tại và làm hỏng giả định của transaction manager.
- Tạo kết quả độc lập khi procedure dùng autonomous transaction.
- Có semantics đặc thù của engine.

**Không thể có quy tắc JPA chung rằng mọi COMMIT trong procedure luôn bị bỏ qua hoặc luôn thành nested commit.**

### PostgreSQL

PostgreSQL hỗ trợ transaction control trong một số thủ tục được gọi trong những điều kiện nhất định, nhưng **CALL procedure chứa COMMIT/ROLLBACK không thể tự điều khiển transaction khi đang nằm trong một explicit transaction block do caller mở theo cách thông thường**. Vì mục tiêu của bài là tham gia transaction JPA, procedure mẫu **không chứa COMMIT/ROLLBACK**.

### Oracle

PL/SQL routine thông thường có thể chạy trong transaction của caller; nhưng Oracle có `PRAGMA AUTONOMOUS_TRANSACTION` cho phép một khối thực hiện transaction riêng. Nếu khối autonomous commit, outer JPA rollback không tự đảo ngược kết quả đó.

### SQL Server

Transact-SQL procedure có thể có các lệnh `BEGIN TRAN`/`COMMIT`/`ROLLBACK` với ngữ nghĩa transaction count và savepoint riêng. “COMMIT bên trong” không đồng nghĩa nested transaction độc lập; một ROLLBACK có thể ảnh hưởng transaction ngoài. Kiểm tra `@@TRANCOUNT`, error handling và transaction manager thay vì suy luận từ tên lệnh.

### MySQL

Quy tắc transaction control của stored procedure, implicit commit của một số câu DDL, autocommit/session state và storage engine ảnh hưởng kết quả. Một CALL có thể tương tác với transaction của connection theo cách làm thay đổi boundary nếu routine chứa commit. Không đem một procedure tự commit sang service JPA đang quản lý transaction mà không sửa contract.

**Quy ước nên áp dụng cho nghiệp vụ cần nguyên tử:** procedure do JPA gọi trong transaction phải *transaction-neutral*: thực hiện DML cần thiết, trả kết quả/lỗi và **để caller quyết định commit/rollback**.

## 23. Autonomous transaction và ghi log riêng

Một số hệ thống có procedure ghi audit bằng autonomous transaction:

~~~text
Outer transaction:
    INSERT order
    CALL procedure
        -> autonomous INSERT audit
        -> COMMIT audit riêng
    ROLLBACK outer

Kết quả:
    Order không tồn tại
    Audit vẫn tồn tại
~~~

Điều này có thể là chủ đích để lưu dấu những lần thao tác thất bại, nhưng **không phải là một phần của nguyên tử outer transaction**.

Nếu audit record ghi “Order thành công” trước khi outer commit, nội dung audit có thể sai sự thật. Nên phân biệt:

- Audit thao tác đã *thử thực hiện*.
- Audit thay đổi đã *commit thành công*.
- Audit bảo mật/tuân thủ cần được lưu ngay cả khi nghiệp vụ rollback.

Đây là ba yêu cầu khác nhau và có thể cần transaction strategy khác nhau.

## 24. IN, OUT, INOUT và REF_CURSOR trong một transaction

Stored procedures có thể có các tham số:

| Mode | Ý nghĩa |
| --- | --- |
| `ParameterMode.IN` | Ứng dụng truyền giá trị vào |
| `ParameterMode.OUT` | Procedure đặt giá trị để ứng dụng đọc ra |
| `ParameterMode.INOUT` | Ứng dụng truyền vào và nhận lại một giá trị |
| `ParameterMode.REF_CURSOR` | Truy cập dữ liệu dạng cursor theo khả năng hỗ trợ của DBMS/provider |

### Ví dụ OUT parameter về mặt cấu trúc

Giả sử database có procedure `count_orders_for_tenant`:

~~~text
IN  p_tenant_id
OUT p_total
~~~

JPA:

~~~java
StoredProcedureQuery sp =
    em.createStoredProcedureQuery("count_orders_for_tenant");

sp.registerStoredProcedureParameter(
    "p_tenant_id", Long.class, ParameterMode.IN);
sp.registerStoredProcedureParameter(
    "p_total", Long.class, ParameterMode.OUT);

sp.setParameter("p_tenant_id", tenantId);
sp.execute();

Object value = sp.getOutputParameterValue("p_total");
long total = ((Number) value).longValue();
~~~

Đây là ví dụ **minh họa API theo routine contract giả định**, không phải cam kết mọi database hỗ trợ cùng một procedure signature hoặc cùng cách bind OUT theo tên. Có môi trường hỗ trợ tốt positional parameter hơn named parameter; một số dialect có cách đăng ký OUT khác.

### Kiểu OUT và NULL

Nếu OUT có thể NULL, không viết ngay:

~~~java
((Number) value).longValue()
~~~

mà không kiểm tra. Dùng:

~~~java
Long total = value == null
    ? null
    : ((Number) value).longValue();
~~~

Kiểu Number trả về có thể khác theo driver/provider, nhất là với SQL NUMERIC; `type=Long.class` không thay thế việc hiểu kiểu OUT thật sự của DBMS.

### REF_CURSOR

Một số database/provider hỗ trợ:

~~~java
sp.registerStoredProcedureParameter(
    "p_cursor",
    void.class,
    ParameterMode.REF_CURSOR);
~~~

Nhưng **cách khai báo cursor type và cách đọc result set** khác theo provider/driver. Một số stack cần class hoặc JDBC type riêng và cơ chế transaction phải giữ connection/cursor còn hoạt động. Vì vậy chỉ dùng đoạn này làm sơ đồ API; khi triển khai PostgreSQL/Oracle cụ thể phải theo hướng dẫn provider đang sử dụng.

## 25. Thứ tự lấy result sets, update counts và OUT parameters

Một procedure có thể trả **nhiều loại kết quả**:

~~~text
CALL procedure
  |
  +-- Update count 1
  +-- Result set A
  +-- Update count 2
  +-- Result set B
  +-- OUT parameters
~~~

JPA cung cấp:

- `execute()`: thực thi và cho biết kết quả đầu tiên có phải result set.
- `getResultList()`: đọc result set hiện tại khi phù hợp.
- `getUpdateCount()`: đọc update count hiện tại, có thể trả -1 khi không phải update count.
- `hasMoreResults()`: chuyển sang kết quả tiếp theo và báo có phải result set.
- `getOutputParameterValue(...)`: đọc OUT/INOUT parameters.

### Nguyên tắc portability

Đối với `StoredProcedureQuery` trả cả result sets/update counts lẫn OUT parameters, **nên tiêu thụ hết các result sets và update counts trước khi đọc OUT parameters** theo yêu cầu portability của JPA. Một số driver/procedure có ràng buộc riêng về đóng/duyệt kết quả.

Pseudo-flow:

~~~text
boolean resultSet = sp.execute()
loop:
    if resultSet:
        consume sp.getResultList()
    else:
        count = sp.getUpdateCount()
        if count == -1:
            break
        consume count
    resultSet = sp.hasMoreResults()
after all results:
    read OUT parameters
~~~

Lưu ý: các provider có thể khác ở cách báo “không còn kết quả” hoặc hỗ trợ nhiều result sets. **Không viết vòng lặp vô hạn chỉ dựa vào `hasMoreResults()==false`**, vì false còn có thể nghĩa “kết quả tiếp theo là update count”.

### Nếu procedure không trả result set

Với `reserve_stock` chỉ UPDATE và báo exception khi thất bại, service đơn giản có thể gọi:

~~~java
sp.execute();
~~~

không cần phức tạp hóa bằng một vòng lặp đọc multiple results. Tuy nhiên, nếu provider yêu cầu giải phóng/consume update counts, tuân thủ hướng dẫn stack đang chạy.

## 26. JPA StoredProcedureQuery và JDBC CallableStatement

Về bản chất JPA provider thường sử dụng JDBC/driver để thực thi lời gọi procedure, nhưng API JPA và API JDBC có mức trừu tượng khác nhau.

Ví dụ JDBC:

~~~java
try (CallableStatement stmt =
         connection.prepareCall("{call reserve_stock(?, ?, ?)}")) {
    stmt.setLong(1, tenantId);
    stmt.setLong(2, itemId);
    stmt.setInt(3, quantity);
    stmt.execute();
}
~~~

Đây là ví dụ về **CallableStatement API**, không cam kết escape syntax `{call ...}` được driver đang dùng diễn dịch giống nhau với mọi loại PostgreSQL procedure/function.

### Vì sao ưu tiên StoredProcedureQuery khi đang ở JPA?

- Giữ lời gọi ở tầng `EntityManager` đang được transaction manager điều phối.
- Sử dụng chuẩn API `jakarta.persistence.StoredProcedureQuery`.
- Có thể khai báo result mapping từ JPA metadata.
- Giảm rủi ro vô ý mở connection ngoài transaction.

### Khi nào cần JDBC trực tiếp?

- Driver/provider có hạn chế với cursor, OUT params hoặc multiple result sets.
- Cần vendor-specific callable operations không được JPA hỗ trợ.
- Muốn truy cập JDBC advanced streaming/result handling.

Nếu dùng JDBC trong cùng unit of work, phải chứng minh **connection được enlist vào transaction đang có**, không đơn thuần lấy một connection mới cùng URL.

## 27. @NamedStoredProcedureQuery cho lời gọi tái sử dụng

Thay vì mỗi lần gọi đều đăng ký parameters, JPA hỗ trợ khai báo named stored procedure query trên metadata entity:

~~~java
import jakarta.persistence.NamedStoredProcedureQuery;
import jakarta.persistence.ParameterMode;
import jakarta.persistence.StoredProcedureParameter;

@NamedStoredProcedureQuery(
    name = "InventoryItem.reserveStock",
    procedureName = "reserve_stock",
    parameters = {
        @StoredProcedureParameter(
            position = 1,
            mode = ParameterMode.IN,
            type = Long.class),
        @StoredProcedureParameter(
            position = 2,
            mode = ParameterMode.IN,
            type = Long.class),
        @StoredProcedureParameter(
            position = 3,
            mode = ParameterMode.IN,
            type = Integer.class)
    }
)
@Entity
public class InventoryItem {
    // Các persistent fields đã trình bày.
}
~~~

Đây là **phần annotation bổ sung** vào class InventoryItem ở mục 5, không phải tạo class InventoryItem thứ hai trong dự án.

Thực thi:

~~~java
StoredProcedureQuery sp =
    em.createNamedStoredProcedureQuery(
        "InventoryItem.reserveStock");

sp.setParameter(1, tenantId);
sp.setParameter(2, itemId);
sp.setParameter(3, quantity);
sp.execute();
~~~

### Phân biệt hai tên

- `"InventoryItem.reserveStock"` là tên **JPA named stored procedure query**.
- `"reserve_stock"` là tên routine vật lý ở database.

Đừng nhầm:

~~~java
em.createNamedStoredProcedureQuery(
    "InventoryItem.reserveStock");
~~~

với:

~~~java
em.createStoredProcedureQuery("reserve_stock");
~~~

### Kết quả trả về

Named stored procedure query có thể liên hệ tới entity result classes hoặc SqlResultSetMapping tùy metadata JPA và provider hỗ trợ. Nhưng việc gắn mapping không đổi transaction boundary: procedure vẫn phải tham gia transaction caller theo cấu hình resource phù hợp.

## 28. Spring Data JPA @Procedure và transaction caller

Spring Data JPA có hỗ trợ khai báo stored procedure ở repository, ví dụ dạng:

~~~java
public interface InventoryRepository
        extends JpaRepository<InventoryItem, Long> {

    @Procedure(procedureName = "reserve_stock")
    void reserveStock(
            Long tenantId,
            Long itemId,
            Integer quantity);
}
~~~

Đây là **ví dụ Spring Data-specific**, cần import `org.springframework.data.jpa.repository.query.Procedure` và `org.springframework.data.jpa.repository.JpaRepository`. Cách bind tên/vị trí tham số, routine kind và khả năng hoạt động có thể cần `@Param` hoặc named metadata tùy cấu hình và phiên bản; vì thế không xem đoạn trên là portable JPA.

### Điểm quan trọng không nằm ở annotation @Procedure

Nếu service:

~~~java
@Transactional
public void placeOrder(...) {
    orderRepository.save(order);
    inventoryRepository.reserveStock(...);
}
~~~

và hai repository cùng dùng EntityManager/resource trong transaction của service, procedure có thể tham gia transaction đó.

Nhưng nếu method repository được cấu hình `REQUIRES_NEW` hoặc DataSource/transaction manager khác, nguyên tử có thể bị phá. **`@Procedure` chỉ là cơ chế gọi routine, không tự đặt đúng transaction propagation cho nghiệp vụ.**

## 29. Read-only transaction không phải môi trường phù hợp để ghi bằng procedure

Một method:

~~~java
@Transactional(readOnly = true)
public void report(...) {
    // ...
}
~~~

trong Spring có thể ảnh hưởng flush mode, JDBC connection/read-only hint và tùy DBMS có thể ngăn ghi. Không nên gọi một procedure chứa UPDATE từ đây rồi hy vọng database cho phép vì “procedure tự chạy”.

### Nguyên tắc

- Procedure chỉ đọc: có thể hoạt động dưới transaction read-only, nhưng cần kiểm tra cursor/result handling và isolation.
- Procedure có DML: dùng transaction được phép ghi.
- Read-only annotation **không phải một bảo đảm JPA chuẩn rằng mọi write luôn bị DB từ chối**.
- Read-only cũng không đồng nghĩa REPEATABLE READ hoặc SERIALIZABLE.

Tách rõ contract: routine có side effect không? Nếu có, caller phải cho phép side effect và quản lý rollback tương ứng.

## 30. Lỗi procedure ảnh hưởng transaction như thế nào?

Ví dụ procedure PostgreSQL:

~~~sql
RAISE EXCEPTION 'Item unavailable or insufficient stock';
~~~

Khi JPA gọi:

~~~java
sp.execute();
~~~

provider có thể chuyển lỗi DB thành `PersistenceException` hoặc exception cụ thể hơn, rồi framework có thể bọc/chuyển tiếp.

### Không bắt exception rồi giả vờ thành công

Sai:

~~~java
try {
    sp.execute();
} catch (RuntimeException ex) {
    log.warn("Procedure lỗi, bỏ qua");
}

return "SUCCESS";
~~~

Sau lỗi SQL, transaction có thể đã bị DB đánh dấu thất bại hoặc transaction manager đánh dấu rollback-only; dù code Java tiếp tục, commit có thể thất bại.

### PostgreSQL: transaction-aborted state

Trong PostgreSQL, một lỗi SQL chưa được xử lý bằng cơ chế transaction/savepoint phù hợp thường khiến transaction hiện tại ở trạng thái aborted. Những câu SQL tiếp theo có thể nhận thông báo rằng transaction đang lỗi và phải rollback.

**Không sửa bằng cách gọi lại `em.flush()` trong cùng transaction đã lỗi.** Phải rollback và mở transaction mới nếu nghiệp vụ cho phép retry.

### Một số lỗi có thể xuất hiện khi commit

- Optimistic lock conflict.
- Deferred constraint violation.
- Serialization failure.
- Deadlock hoặc transaction timeout.
- JTA resource/transaction coordination failure.

Vì vậy không nên tuyên bố operation thành công trước khi transaction boundary báo commit thành công.

## 31. Rollback-only và UnexpectedRollbackException

Trong Spring, một inner method tham gia transaction hiện có có thể gặp lỗi và khiến transaction bị đánh dấu rollback-only:

~~~text
Outer @Transactional
    |
    +-- Inner REQUIRED gọi procedure
    |       -> exception
    |       -> transaction bị đánh dấu rollback-only
    |
    +-- Outer catch exception rồi return bình thường
    |
    v
Outer cố commit
    -> rollback và có thể ném UnexpectedRollbackException
~~~

Đây là một cơ chế bảo vệ: outer caller không được lầm tưởng đã commit khi inner operation trước đó đã yêu cầu rollback.

### Cách xử lý đúng

- Nếu procedure thất bại khiến unit of work không hợp lệ, hãy **để lỗi lan ra** và rollback toàn bộ.
- Nếu cần chuyển thành business error, chuyển đổi exception theo cách vẫn bảo đảm rollback (ví dụ ném unchecked domain exception hoặc cấu hình rollback rule).
- Nếu phải tiếp tục sau lỗi, cần thiết kế savepoint/recovery chính thức được DB/transaction manager hỗ trợ, không chỉ catch rồi bỏ qua.

Trong JTA, cũng có tình huống transaction được đánh dấu rollback-only; phải kiểm tra transaction status bằng API/container phù hợp trước khi làm thêm việc.

## 32. Lock, deadlock và thời gian thực thi procedure

Procedure có thể thực hiện nhiều UPDATE/SELECT FOR UPDATE liên tiếp. Dù Java chỉ có **một lời gọi `execute()`**, database vẫn có thể giữ nhiều locks, thực hiện nhiều câu SQL và chờ các transaction khác.

~~~text
T1: CALL reserve_stock(item A)
    -> khóa A
    -> tiếp tục cần khóa B

T2: CALL reserve_stock(item B)
    -> khóa B
    -> tiếp tục cần khóa A

=> Có thể xảy ra deadlock.
~~~

### Giảm rủi ro

- Giữ transaction ngắn, tránh network call trong khi giữ locks.
- Khi cập nhật nhiều item, dùng thứ tự khóa ổn định (ví dụ theo ID tăng).
- Index các cột dùng trong WHERE/JOIN để giảm phạm vi quét và lock.
- Thiết kế timeout hợp lý ở transaction manager, database và driver.
- Phân biệt deadlock/serialization failure có thể retry với lỗi nghiệp vụ như thiếu tồn kho.
- Giới hạn số lần retry và dùng backoff/jitter khi cần.

### Query timeout không bảo đảm chính xác từng mili giây

JPA có hint:

~~~java
sp.setHint("jakarta.persistence.query.timeout", 3000);
~~~

Nhiều provider/DBMS không thực thi mọi timeout hint giống nhau. Timeout có thể không cắt được một routine dài đúng sau 3 giây do cách JDBC/DBMS xử lý. Nếu timeout cần mang tính hợp đồng, phải kiểm chứng trên stack thực, có giám sát và kế hoạch rollback.

## 33. Isolation level vẫn do database quyết định

Một CALL trong transaction không tự làm transaction thành SERIALIZABLE:

| Mức cô lập | Khía cạnh cần cân nhắc |
| --- | --- |
| READ COMMITTED | Các statement có thể nhìn phiên bản committed mới theo cơ chế DBMS |
| REPEATABLE READ | Snapshot/locking đọc lặp lại thay đổi theo DBMS; không mặc nhiên giải quyết mọi write skew |
| SERIALIZABLE | Các transaction commit phải tương đương lịch tuần tự; có thể có serialization failure cần retry |

JPA **không định nghĩa một isolation mặc định thống nhất** cho mọi DBMS. Spring có thuộc tính isolation trong `@Transactional`, nhưng nó là tính năng framework, chỉ có thể được áp dụng trong điều kiện transaction manager tạo/điều khiển transaction thích hợp.

### Tại sao nhiều UPDATE trong một procedure vẫn có thể phá invariant?

Giả sử mỗi transaction đọc tổng số reservation của một nhóm, rồi tăng reservation ở một row khác nhau. Hai transaction có thể cùng thấy tổng cũ và cùng commit dưới một số mô hình isolation, làm vượt hạn mức.

Procedure không làm kiểm tra tổng trở nên nguyên tử chỉ vì nó nằm trong database. Cần bảo vệ invariant bằng một lock chung, constraint, SERIALIZABLE hoặc mô hình dữ liệu/thao tác SQL phù hợp.

## 34. Retry phải bao trùm toàn bộ unit of work

Khi transaction thất bại do deadlock hoặc serialization conflict, ứng dụng có thể muốn retry:

~~~text
Attempt 1:
    BEGIN
    persist Order
    CALL reserve_stock
    COMMIT -> serialization failure
    ROLLBACK

Attempt 2:
    BEGIN transaction MỚI
    đọc lại item và dữ liệu nghiệp vụ
    persist Order mới theo idempotency policy
    CALL reserve_stock
    COMMIT
~~~

**Không retry riêng `sp.execute()` trong transaction cũ đã rollback-only.** Bất biến nghiệp vụ phụ thuộc cả Order và stock, nên retry phải bắt đầu từ đơn vị công việc có thể lặp lại an toàn.

### Phân loại lỗi

| Lỗi | Nên tự động retry? |
| --- | --- |
| Hết tồn kho thực sự | Thường **không**, trả business conflict |
| Không tìm thấy item/tenant sai | Không; xử lý validation/authorization |
| Deadlock | Có thể retry toàn transaction có giới hạn |
| Serialization failure | Có thể retry toàn transaction có giới hạn |
| Mất kết nối khi commit không rõ kết quả | Cần xác minh trạng thái/idempotency, không retry mù |
| Syntax SQL/procedure không tồn tại | Không; đây là lỗi triển khai |
| Vi phạm unique idempotency key | Có thể truy vấn trạng thái request trước để trả kết quả cũ |

### Backoff và giới hạn

Retry vô hạn dưới tải cao có thể làm tình trạng contention tệ hơn. Thiết kế số attempt tối đa, backoff/jitter và quan sát tần suất conflict.

## 35. Idempotency: chống trừ tồn kho hai lần

Transaction bảo vệ **một lần chạy**, nhưng không tự bảo vệ hai request có cùng ý định:

~~~text
Client POST /orders
  -> transaction commit thành công
  -> response bị mất do network
Client retry POST /orders
  -> transaction thứ hai cũng commit
  -> stock trừ lần nữa
~~~

Đây là vấn đề **idempotency**, khác rollback.

Một giải pháp là request key duy nhất trong phạm vi tenant:

~~~sql
ALTER TABLE purchase_orders
ADD COLUMN request_key VARCHAR(100);

ALTER TABLE purchase_orders
ADD CONSTRAINT uq_order_tenant_request
UNIQUE (tenant_id, request_key);
~~~

Trong production, trường request_key nên bắt buộc và có chính sách lifecycle phù hợp, thay vì tùy tiện nullable như lệnh ALTER minh họa.

### Luồng idempotent có chủ đích

1. Client gửi idempotency key ổn định cho **cùng một yêu cầu**.
2. Service kiểm tra/ghi nhận key trong transaction với unique constraint.
3. Nếu đây là request mới, tạo Order rồi CALL reserve_stock.
4. Commit cả Order, trạng thái xử lý key và stock cùng nhau.
5. Nếu request lặp, tra trạng thái và trả cùng kết quả phù hợp thay vì CALL lại.

Không chỉ làm:

~~~text
SELECT COUNT(*) WHERE request_key=...
if count=0 then INSERT
~~~

và tưởng đã an toàn trước hai transaction concurrent. Database UNIQUE constraint là lớp bảo vệ quan trọng; ứng dụng phải xử lý conflict cùng ngữ nghĩa trả kết quả.

## 36. Không gọi HTTP/email trong procedure hoặc khi đang giữ transaction lâu

Một số procedure có khả năng gọi extension, network service hoặc ghi ra hệ thống ngoài database. Nhưng một database transaction **không tự rollback được email/HTTP request đã hoàn thành**.

Ví dụ lỗi:

~~~text
BEGIN
  persist Order
  CALL reserve_stock
  sendEmail("Đã xác nhận đơn")
  COMMIT -> thất bại

Email đã gửi nhưng đơn chưa commit.
~~~

### Transactional outbox

Một lựa chọn phổ biến:

~~~text
BEGIN
  INSERT order
  CALL reserve_stock
  INSERT outbox_event(OrderReserved)
COMMIT

Worker khác:
  đọc outbox đã commit
  publish message
  retry nếu cần
~~~

Order, stock và **ý định phát event** cùng commit trong database; việc publish ra broker được thực hiện sau, cần idempotent consumer và cơ chế retry.

Nếu procedure tự gọi HTTP bên trong hoặc sử dụng autonomous transaction để log event, phải đánh giá lại ranh giới atomicity. **Không gán bảo đảm ACID của database cho những side effects bên ngoài**.

## 37. Có nhiều database thì cùng @Transactional đã đủ chưa?

Giả sử:

~~~text
JPA Order -> Database A
Procedure stock -> Database B
~~~

Nếu dùng hai transaction managers hoặc hai connection không được XA-coordinated:

~~~text
Commit A thành công
Commit B thất bại
=> trạng thái hai hệ thống không nhất quán
~~~

JTA/XA có thể phối hợp một số loại transactional resources khi driver, datasource và transaction manager được cấu hình hỗ trợ, nhưng có chi phí và giới hạn thực tế.

Nếu không dùng distributed transaction, cần thiết kế các mô hình như saga, outbox, reservation state, compensation và idempotency thay vì khẳng định một `@Transactional` có thể commit atomically qua mọi hệ thống.

### Chọn theo yêu cầu

| Kiến trúc | Cơ chế thường cần |
| --- | --- |
| JPA + procedure trong **cùng một DB** | Một transaction manager, một enlisted DB resource |
| JPA + JDBC cùng DB | Xác minh cùng transaction-bound connection/resource |
| Hai DB có XA support | JTA/XA khi yêu cầu atomicity và hạ tầng đáp ứng |
| Hai microservices qua HTTP | Saga/outbox, idempotency, compensation |
| Database + message broker | Outbox hoặc transaction coordination phù hợp |

Không có một API `StoredProcedureQuery` nào tự biến một hệ thống phân tán thành một transaction duy nhất.

## 38. Stored procedure và quyền truy cập dữ liệu

Trong ví dụ `reserve_stock`:

~~~sql
WHERE id = p_item_id
  AND tenant_id = p_tenant_id
  AND available >= p_quantity
~~~

Điều kiện tenant phải đến từ nguồn đáng tin trong application. Không nên dựa hoàn toàn vào ID item do client truyền.

### Procedure privileges

DBMS có cơ chế cấp quyền EXECUTE và đôi khi procedure chạy theo quyền chủ sở hữu/definer hoặc người gọi/invoker. Điều này có thể tạo khác biệt lớn:

- Procedure có thể truy cập bảng mà caller không thể SELECT trực tiếp.
- Procedure có thể vô tình vượt chính sách row-level security nếu cấu hình quyền sai.
- Một routine có `SECURITY DEFINER` hoặc cơ chế tương đương phải validate input chặt chẽ.
- Native SQL, procedure và JPQL provider filters không mặc nhiên có cùng tenant policy.

Không cho client truyền raw SQL, tên procedure hay tên schema tùy ý để ứng dụng gọi mà không whitelist.

### Phân quyền phải được đảm bảo ở đúng tầng

Ứng dụng kiểm tra user/tenant, procedure kiểm tra điều kiện nghiệp vụ và database dùng constraints/RLS phù hợp. Những lớp bảo vệ này bổ sung nhau.

## 39. Quan sát SQL và log transaction

Khi lỗi “procedure chạy nhưng không thấy dữ liệu” hoặc “rollback không hủy update”, việc quan sát đúng sẽ giúp khoanh vùng:

- Transaction ID hoặc correlation ID của request.
- Ranh giới begin/commit/rollback từ transaction manager.
- SQL INSERT/UPDATE JPA phát ra trước/sau flush.
- Thời điểm CALL và danh sách parameters đã được mask nếu nhạy cảm.
- Connection/resource nào được dùng cho JPA và procedure.
- SQLSTATE/error code từ DBMS (không chỉ message chung của framework).
- Row locks, deadlocks, timeout hoặc wait events.
- State entity sau CALL và sau refresh.
- DB state nhìn bằng transaction mới **sau commit/rollback**.

### Tránh kết luận sai từ log

1. Thấy `CALL reserve_stock` trong log không chứng minh commit thành công.
2. Thấy `UPDATE inventory_items` bên trong procedure không chứng minh transaction khác đã thấy dữ liệu.
3. Thấy entity Java giữ `available=20` sau CALL không chứng minh DB vẫn là 20.
4. Thấy exception ở commit không nhất thiết lỗi bắt nguồn ở câu SQL cuối cùng.
5. Truy vấn kiểm tra qua một tool SQL trên connection khác có thể đọc snapshot khác.

## 40. Integration test: rollback của JPA phải hủy tác động procedure

Đây là kiểm thử quan trọng nhất của bài.

### Kịch bản

Tồn kho ban đầu:

~~~text
InventoryItem#10:
  available = 20
  version = 0

purchase_orders: chưa có đơn test
~~~

Trong transaction:

1. Persist một PurchaseOrder quantity=5.
2. Flush để INSERT xảy ra.
3. CALL reserve_stock(tenant, item=10, quantity=5).
4. **Cố ý tạo lỗi** sau CALL trước commit.
5. Rollback.

Sau đó dùng **EntityManager/transaction mới** để kiểm tra:

~~~text
InventoryItem#10.available = 20
Không có PurchaseOrder mới
Version chưa được commit tăng
~~~

### Pseudocode integration test

~~~java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    InventoryItem item =
        em.find(InventoryItem.class, 10L);

    PurchaseOrder order =
        new PurchaseOrder(tenantId, item, 5);
    em.persist(order);
    em.flush();

    reserveStock(em, tenantId, 10L, 5);

    throw new IllegalStateException(
        "Test rollback sau CALL");
} catch (IllegalStateException expected) {
    if (tx.isActive()) {
        tx.rollback();
    }
} finally {
    em.close();
}

// Mở EntityManager mới để đọc committed state.
EntityManager verify = emf.createEntityManager();
try {
    InventoryItem fresh =
        verify.find(InventoryItem.class, 10L);

    if (fresh.getAvailable() != 20) {
        throw new AssertionError(
            "Procedure đã commit ngoài transaction?");
    }

    // Dùng một query COUNT cho Order test theo request key/ID
    // đã biết để xác nhận Order insert cũng bị rollback.
} finally {
    verify.close();
}
~~~

Đây là test phác họa; trong dự án thực, dùng JUnit/assertions, dữ liệu fixture độc lập và không bắt tất cả IllegalStateException từ bất kỳ nguồn nào như thể đều là exception cố ý. Một test nghiêm túc phải phân biệt lỗi test chủ động với lỗi của CALL và kiểm tra cả số Order theo định danh request.

### Vì sao dùng EntityManager mới?

Để tránh đọc state stale đang managed trong context vừa rollback. Rollback database **không tự đảo ngược tất cả Java field setters** trong object đã thay đổi. Context mới giúp kiểm tra committed database state đáng tin hơn.

## 41. Integration test: commit thành công

Kịch bản ngược:

~~~text
BEGIN
  persist Order qty=5
  flush
  CALL reserve_stock qty=5
  refresh inventory item
  mark order RESERVED
COMMIT
~~~

Kiểm tra bằng context mới:

- Order tồn tại với trạng thái RESERVED.
- Tồn kho giảm từ 20 xuống 15.
- Version tăng đúng theo giao thức đã định nghĩa.
- Không có hai Order trùng idempotency key nếu constraint được thiết kế.
- Một operation ở tenant khác không truy cập hoặc sửa item tenant hiện hành.

Nếu dùng read replica bất đồng bộ để verify ngay, có thể quan sát dữ liệu cũ dù commit trên primary đã thành công. Integration test cần đọc từ database/resource phù hợp với mục tiêu kiểm tra.

## 42. Integration test: thiếu tồn kho và hai transaction cạnh tranh

### Thiếu tồn kho

Tồn kho có 3, gọi reserve quantity=5:

~~~text
BEGIN
  persist Order
  CALL reserve_stock(5) -> procedure báo lỗi
ROLLBACK

Kỳ vọng:
  available = 3
  không có Order đã commit
~~~

### Hai request cùng giữ hàng

Tồn kho 5:

~~~text
T1: BEGIN; CALL reserve_stock(4)
T2: BEGIN; CALL reserve_stock(4)
T1: COMMIT
T2: conflict / insufficient stock / retry theo DBMS
~~~

Kỳ vọng **không có kết quả hai giao dịch cùng giữ 4 khiến available âm**.

Khi kiểm thử concurrency:

- Dùng **hai EntityManager, hai transaction, hai connection**.
- Đồng bộ các mốc bằng barrier/latch trong test harness, không dựa vào sleep tùy ý.
- Đảm bảo pool đủ connection cho hai transaction.
- Đặt timeout tránh test treo do lock.
- Assert bất biến cuối cùng và exception/rollback behavior.

Không chia sẻ một EntityManager instance giữa hai threads; JPA EntityManager không được thiết kế cho concurrent access.

## 43. Các lỗi thường gặp khi phối hợp procedure với transaction

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Order rollback nhưng stock đã trừ | Procedure dùng connection/transaction khác hoặc tự commit | Gọi trên cùng resource, loại bỏ commit độc lập |
| Procedure không thấy Order vừa persist | Entity còn pending trong context | Flush trước CALL khi có phụ thuộc dữ liệu |
| CALL thành công nhưng Java item.available chưa đổi | Managed entity stale | Refresh đúng entity hoặc clear/nạp lại |
| Sau CALL, commit báo optimistic lock conflict | Procedure tăng version nhưng entity giữ version cũ | Refresh sau CALL, thống nhất write ownership |
| Procedure bỏ qua @Version | Native UPDATE không tự tăng/check version | Áp quy ước version nhất quán |
| execute() trả false và code báo thất bại | Hiểu sai boolean thành result set indicator | Không dùng execute() làm success flag |
| Spring @Transactional không có hiệu lực | Self-invocation hoặc gọi ngoài proxy | Xác minh boundary thực, cấu hình proxy |
| Outer rollback nhưng inner vẫn commit | REQUIRES_NEW hoặc resource riêng | Dùng REQUIRED/cùng transaction khi cần atomicity |
| CALL không chạy trong read-only TX | Transaction/datasource read-only | Dùng transaction writable cho DML |
| Postgres báo transaction aborted sau lỗi | Tiếp tục dùng TX đã lỗi | Rollback, transaction mới; savepoint khi được hỗ trợ |
| OUT parameter đọc sai hoặc không đọc được | Chưa consume result sets/update counts, driver limitation | Đọc theo contract, kiểm tra provider |
| REF_CURSOR lỗi khi TX kết thúc | Cursor/connection lifecycle | Tiêu thụ cursor khi transaction còn phù hợp |
| Lỗi JPA EntityTransaction trên JTA | Dùng sai transaction API | Container/JTA manager làm chủ |
| JdbcTemplate procedure không rollback theo JPA | Không cùng transaction-bound DataSource/connection | Kiểm chứng enlistment/transaction manager |
| Nhiều tenant cùng sửa item | Thiếu tenant check trong service/procedure | Scope theo tenant ở mọi lớp |
| Retry làm trừ stock hai lần | Retry mù sau commit không rõ kết quả | Idempotency key và kiểm tra outcome |
| Procedure gây deadlock khi nhiều item | Thứ tự khóa khác nhau giữa requests | Lock theo thứ tự nhất quán, retry có giới hạn |
| EntityManager.clear() làm mất pending changes | Clear trước flush | Flush/đồng bộ có chủ đích, không clear máy móc |
| SQL UPDATE thấy trong log nhưng API đọc state cũ | Chưa commit, context stale, snapshot hoặc replica | Phân biệt các tầng visibility |
| Database rollback nhưng email đã gửi | Side effect ngoài DB | Outbox/idempotency/compensation |
| Procedure cập nhật nhưng row count sai | Procedure/SQL aggregate hoặc OUT param sai | Kiểm tra SQL và result handling, không chỉ mapping |
| Stored procedure báo success dù business operation không thực hiện | Routine nuốt lỗi hoặc trả code nhưng Java không kiểm tra | Xác định contract OUT/status và validation |

## 44. Thiết kế contract procedure để phối hợp transaction dễ hiểu

Một procedure dùng trong JPA service nên có **contract tường minh**:

1. **Tên và schema:** procedure nào, có overload theo signature không?
2. **Loại routine:** procedure hay function, DBMS hỗ trợ CallableStatement như thế nào?
3. **Input types:** thứ tự/tên tham số, nullable hay không, enum/date/money mapping?
4. **Output types:** OUT/INOUT, result sets, update counts, mã lỗi?
5. **Side effects:** bảng nào được INSERT/UPDATE/DELETE?
6. **Transaction semantics:** có tự COMMIT/ROLLBACK không, có autonomous transaction không?
7. **Concurrency:** lock row nào, thứ tự lock, retryable errors?
8. **Versioning:** có tăng/chạm optimistic version không?
9. **Idempotency:** gọi lặp cùng request có an toàn không?
10. **Security:** execute privileges, tenant/ACL, RLS/definer rights?
11. **Performance:** thời gian chạy, index, batch size, timeout.
12. **Persistence context:** entity nào stale sau CALL, adapter cần refresh/clear?
13. **Observability:** correlation ID, audit, SQLSTATE, error mapping.
14. **Testing:** rollback test, concurrent test, null/OUT/result-set test trên DBMS thật.

### Một contract đề xuất cho reserve_stock

~~~text
Routine: reserve_stock(tenant_id, item_id, quantity)
Input:
  tenant_id: positive BIGINT, trusted tenant context
  item_id: positive BIGINT
  quantity: positive INTEGER
Precondition:
  item belongs to tenant
  available >= quantity
Success:
  available decreases exactly by quantity
  version increments by one
  no transaction COMMIT inside routine
Failure:
  raises database exception when condition not met
  caller rolls back entire unit of work
Concurrency:
  atomic conditional UPDATE on inventory row
  DB locks/isolation apply
Caller:
  owns transaction
  flushes pending data when needed
  refreshes affected managed InventoryItem before reuse
~~~

Một hợp đồng như vậy giúp code review biết rõ **trách nhiệm của service, JPA adapter và procedure**, thay vì phải suy đoán từ nội dung SQL.

## 45. Quy trình kiểm tra khi một luồng JPA + procedure bị lỗi

Thứ tự điều tra:

1. Kiểm tra transaction boundary: ai bắt đầu và commit/rollback?
2. Kiểm tra EntityManager và procedure call có cùng resource/transaction không.
3. Kiểm tra `@Transactional` có thực sự được kích hoạt (proxy, propagation, manager).
4. Kiểm tra procedure có lệnh commit/rollback, autonomous transaction hoặc side effect ngoài DB không.
5. Kiểm tra JPA state đã flush trước CALL nếu procedure cần đọc nó.
6. Kiểm tra routine SQL dùng tenant/PK và điều kiện nghiệp vụ đúng.
7. Kiểm tra exception có bị nuốt hoặc chuyển thành “success” không.
8. Kiểm tra transaction có rollback-only/aborted sau lỗi không.
9. Kiểm tra managed entity có stale sau procedure không.
10. Kiểm tra version/locking và concurrency với giao dịch khác.
11. Kiểm tra dữ liệu **sau commit/rollback bằng transaction mới**.
12. Kiểm tra connection/session thật qua log/metrics được phép, không suy luận từ tên DataSource.

### Sơ đồ quyết định

~~~text
Procedure chạy cùng unit of work JPA?
              |
              v
Có transaction active đúng resource?
       |                  |
      Không               Có
       |                  |
       v                  v
Sửa transaction      JPA có pending state
boundary/enlistment   procedure cần đọc?
                         |          |
                        Có         Không
                         |          |
                         v          |
                    Flush có chủ đích|
                         +----------+
                         |
                         v
             Procedure có commit độc lập?
                    |          |
                   Có          Không
                    |          |
                    v          v
            Đổi contract   CALL trong TX
                    |          |
                    +----------+
                         |
                         v
              Procedure cập nhật entity managed?
                    |          |
                   Có          Không
                    |          |
                    v          |
            Refresh/clear đúng |
                    +----------+
                         |
                         v
              Commit hoặc rollback tại caller
~~~

## 46. Bài tập thực hành

### Bài 1 — Có cần transaction cho CALL?

Một service cần persist Order và CALL reserve_stock, bảo đảm cả hai cùng commit hoặc rollback. Nên để repository gọi CALL tự commit hay đặt transaction boundary ở service?

**Gợi ý:** service/transaction manager nên sở hữu một transaction bao trùm cả hai thao tác.

### Bài 2 — Flush trước procedure

Service gọi `em.persist(order)` rồi CALL procedure kiểm tra Order vừa tạo. Vì sao procedure có thể chưa thấy Order?

**Gợi ý:** Order có thể còn pending trong persistence context. Flush trong cùng transaction khi procedure phụ thuộc dữ liệu.

### Bài 3 — Flush khác commit

Sau `em.flush()`, transaction A chưa commit. Transaction B có bắt buộc thấy Order mới không?

**Gợi ý:** không. Visibility do DB isolation và commit quyết định.

### Bài 4 — Boolean của execute

`StoredProcedureQuery.execute()` trả `false` đối với một procedure chỉ UPDATE. Có chứng minh procedure thất bại không?

**Gợi ý:** không. Boolean mô tả kết quả đầu tiên có phải result set, không phải success flag.

### Bài 5 — Entity stale

InventoryItem managed có available=20. CALL procedure giảm xuống 15. Vì sao getter trên managed entity có thể vẫn là 20?

**Gợi ý:** procedure sửa DB trực tiếp, không cập nhật field Java trong persistence context. Cân nhắc refresh.

### Bài 6 — Refresh mất pending state

Trước CALL, service vừa đổi một field managed chưa flush; sau CALL gọi `em.refresh(item)`. Rủi ro gì?

**Gợi ý:** refresh có thể ghi đè pending state của entity. Flush/điều phối field ownership có chủ đích.

### Bài 7 — Version

Procedure cập nhật available nhưng không tăng `version`. Điều này ảnh hưởng optimistic locking của các JPA transactions khác như thế nào?

**Gợi ý:** chúng có thể không phát hiện write native như kỳ vọng. Thống nhất giao thức version.

### Bài 8 — REQUIRED và REQUIRES_NEW

Tại sao một procedure được gọi qua method `REQUIRES_NEW` có thể commit stock dù outer Order transaction rollback?

**Gợi ý:** inner physical transaction độc lập commit trước outer.

### Bài 9 — Self-invocation

Trong Spring, `this.reserveStock()` gọi một method có `@Transactional`. Có luôn tạo transaction mới theo annotation không?

**Gợi ý:** không ở mô hình proxy thông thường; lời gọi không đi qua proxy.

### Bài 10 — JTA

Một EntityManager JTA-managed đang tham gia transaction container. Có nên gọi `em.getTransaction().begin()` trước procedure?

**Gợi ý:** không. Container/JTA manager sở hữu transaction boundary.

### Bài 11 — Connection khác

JPA dùng connection A đang trong transaction; helper mở `DriverManager.getConnection()` mới autoCommit=true để CALL. Khi outer rollback, UPDATE procedure có chắc bị hủy?

**Gợi ý:** không. Đây có thể là transaction riêng.

### Bài 12 — Procedure tự commit

Một PostgreSQL procedure có `COMMIT` được CALL trong explicit transaction block của ứng dụng. Có được mặc định nó sẽ commit riêng một “nested transaction” không?

**Gợi ý:** không. PostgreSQL có các hạn chế transaction control ở CALL trong explicit transaction block; cần điều chỉnh procedure contract.

### Bài 13 — Oracle autonomous transaction

Procedure sử dụng autonomous transaction để ghi log và commit riêng. Outer rollback có xóa log đó không?

**Gợi ý:** không. Đây là transaction độc lập; phải xác định log là “attempt” hay “success”.

### Bài 14 — OUT parameter

Procedure trả result sets/update counts và OUT parameter. Thứ tự đọc nào giúp tăng tính portable?

**Gợi ý:** đọc/consume result sets và update counts trước, sau đó lấy OUT parameters.

### Bài 15 — Ref cursor

Procedure trả REF_CURSOR, service đóng transaction/connection trước khi duyệt cursor. Vì sao có thể lỗi?

**Gợi ý:** cursor có thể phụ thuộc lifetime của transaction/connection/provider.

### Bài 16 — Retry

Transaction thất bại tại commit do serialization failure sau CALL. Có nên retry riêng câu CALL trong EntityManager cũ?

**Gợi ý:** không. Rollback, context/transaction mới, thực thi lại toàn bộ logic đọc–kiểm tra–ghi nếu retry an toàn.

### Bài 17 — Idempotency

Client không nhận được response dù Order transaction đã commit, rồi gửi lại request. Một database transaction có tự ngăn việc trừ stock lần hai không?

**Gợi ý:** không. Cần idempotency key và unique constraint/record status.

### Bài 18 — Hai resource

Order ở DB A, procedure ở DB B. Cùng một method `@Transactional` có chắc commit atomically cả hai không?

**Gợi ý:** không. Cần transaction manager/resources coordinated (ví dụ XA/JTA khi phù hợp) hoặc thiết kế saga/outbox.

### Bài 19 — Kiểm thử rollback

Viết test: persist Order, CALL reserve_stock, cố tình throw exception rồi rollback. Sau đó kiểm tra những dữ liệu nào bằng EntityManager mới?

**Gợi ý:** Order không tồn tại, available/version không đổi sau committed rollback.

### Bài 20 — Query result versus transaction success

Một procedure trả OUT status = “OK” nhưng transaction commit sau đó thất bại. API có nên trả thành công chỉ vì OUT status không?

**Gợi ý:** không. OUT mô tả execution của procedure; outcome của unit of work phụ thuộc commit.

## 47. Bảng ghi nhớ nhanh

| Câu hỏi | Quy tắc thực hành |
| --- | --- |
| Ai commit khi procedure được gọi từ service? | Transaction boundary ngoài |
| Procedure có nên tự COMMIT? | Không nếu cần atomicity với JPA, trừ contract đặc biệt đã thiết kế |
| JPA pending state phải được procedure đọc? | Flush trước CALL khi có phụ thuộc |
| Procedure đổi row có managed entity tương ứng? | Refresh entity hoặc clear/nạp lại có chủ đích |
| `execute() == false` có nghĩa lỗi? | Không; có thể chỉ là không có result set đầu tiên |
| Dùng `REQUIRED` để tham gia outer TX? | Có trong Spring khi proxy và manager cấu hình đúng |
| Dùng `REQUIRES_NEW` cho atomic Order + Stock? | Thường không; có thể commit độc lập |
| JTA-managed EntityManager gọi `getTransaction()`? | Không; dùng container/transaction manager |
| Procedure dùng connection khác autoCommit? | Có rủi ro không rollback cùng JPA |
| Oracle autonomous transaction? | Commit độc lập với outer |
| Procedure đổi @Version row? | Cần cập nhật/versioning theo giao thức nhất quán |
| Procedure lỗi SQL, tiếp tục transaction cũ? | Không mặc định; rollback hoặc savepoint/recovery được hỗ trợ |
| OUT parameter có bảo đảm commit? | Không |
| Deadlock/serialization failure có retry? | Có thể retry **toàn bộ transaction mới**, có giới hạn |
| Client retry sau response mất? | Dùng idempotency, không dựa riêng vào transaction |
| DB + email/message cùng transaction? | Không mặc định; dùng outbox/coordination |
| StoredProcedureQuery nhiều result sets? | Duyệt kết quả/update counts và OUT theo contract |
| Kiểm chứng atomicity thế nào? | Integration test commit, rollback, concurrency trên DBMS thật |

## Kết luận

**Phối hợp stored procedure với giao dịch đang có** không đơn thuần là tạo `StoredProcedureQuery` rồi gọi `execute()`. Trọng tâm là **ai sở hữu transaction**, procedure có tham gia đúng resource hay không, các thay đổi JPA đã được flush khi procedure cần đọc chưa, và managed entities có được đồng bộ lại sau SQL trực tiếp hay không.

Với một luồng nghiệp vụ nguyên tử, service hoặc transaction manager nên **bắt đầu/tiếp nhận transaction, gọi các thao tác JPA và procedure trong cùng phạm vi, rồi commit hoặc rollback toàn bộ**. Procedure không nên tự commit nếu kết quả của nó phải rollback cùng caller. `em.flush()` giúp gửi pending SQL nhưng chưa commit; `em.refresh()` hoặc `em.clear()` xử lý state stale sau procedure nhưng không tự đổi isolation hay làm rollback. `@Version`, lock, constraint, retry và idempotency cần được thiết kế thống nhất vì procedure có thể cập nhật dữ liệu ngoài cơ chế dirty checking.

Hãy luôn phân biệt **transaction tham gia** với **transaction độc lập**, **procedure thực thi thành công** với **transaction commit thành công**, và **dữ liệu trong managed entity** với **dữ liệu đã thay đổi trong database**. Khi các ranh giới này được xác định rõ trong contract, code và integration test, JPA và stored procedure có thể phối hợp an toàn trong cùng một unit of work mà không tạo ra những lần commit hoặc rollback bất ngờ.
