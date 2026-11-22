# Vai trò của REFRESH và DETACH khi lan truyền

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Chương:** Cascade và orphanRemoval

Trong ứng dụng dùng Jakarta Persistence (JPA), một entity thường có quan hệ với nhiều entity khác. Khi một thao tác vòng đời được gọi trên entity gốc, JPA có thể **lan truyền** thao tác đó qua những association được khai báo `cascade`. Hai loại cascade quan trọng nhưng dễ bị bỏ qua là **`CascadeType.REFRESH`** và **`CascadeType.DETACH`**.

- `REFRESH`: mở rộng thao tác **làm mới trạng thái persistent từ database** đến các entity liên quan.
- `DETACH`: mở rộng thao tác **tách entity khỏi persistence context** đến các entity liên quan.

Hai thao tác này **không phải DELETE**, không tự commit/rollback transaction và không đồng nghĩa `orphanRemoval=true`. REFRESH có thể ghi đè các thay đổi chưa flush; DETACH có thể khiến những thay đổi chưa flush không còn được tự động lưu vì entity đã ngừng được theo dõi. Để dùng an toàn, cần hiểu đúng **hướng cascade**, **trạng thái managed/detached**, **thời điểm flush** và **ranh giới vòng đời nghiệp vụ**.

## 1. Mục tiêu bài học

Sau bài học, bạn có thể:

1. Mô tả vai trò riêng của `EntityManager.refresh()` và `EntityManager.detach()`.
2. Giải thích vì sao `CascadeType.REFRESH` có thể làm thay đổi state của **nhiều managed entities** chỉ bằng một lệnh trên parent.
3. Giải thích vì sao `CascadeType.DETACH` khiến cả một nhánh entity graph ngừng được dirty checking theo dõi.
4. Phân biệt cascade với phía owning side của foreign key trong quan hệ hai chiều.
5. Phân tích tác động khi một association có cascade REFRESH, cascade DETACH, cả hai hoặc không có cascade.
6. Viết ví dụ Java/JPA với entity cha và con, tự kiểm tra trạng thái bằng `em.contains()`.
7. So sánh `detach()`, `clear()` và `close()`.
8. Phân biệt REFRESH/DETACH với `CascadeType.REMOVE` và `orphanRemoval=true`.
9. Hiểu ảnh hưởng của flush, rollback, lazy loading, transaction và optimistic locking.
10. Đánh giá khi nào nên bật hoặc tránh cascade trên entity **có vòng đời độc lập** hoặc **được nhiều parent dùng chung**.
11. Đọc SQL log và thiết kế thử nghiệm đối chứng có/không có cascade.
12. Tránh dùng refresh hoặc detach làm “phương án chữa cháy” cho transaction đã lỗi.

## 2. Persistence context và trạng thái entity

Persistence context là vùng JPA quản lý các entity instances và persistent state của chúng.

| Trạng thái | Ý nghĩa | Dirty checking |
|---|---|---|
| **New/transient** | Object mới tạo, chưa đưa vào context | Không |
| **Managed** | Entity đang được context quản lý | Có, khi điều kiện transaction/flush phù hợp |
| **Detached** | Entity không còn được context quản lý | Không |
| **Removed** | Entity đã được đánh dấu xóa theo lifecycle JPA | Không xem như entity hoạt động bình thường |

Ví dụ:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);

System.out.println(em.contains(order)); // true nếu tìm thấy.
```

Khi managed, provider có thể theo dõi những thay đổi như:

```java
order.changeNote("Ghi chú mới");
```

Nhưng thao tác với context sẽ ảnh hưởng đến state:

```java
em.refresh(order); // Đọc lại persistent state từ DB.
em.detach(order);  // Tách order khỏi context.
```

Sau refresh thành công, `order` vẫn managed. Sau detach, `order` không còn managed trong EntityManager đó. **Cascade** quyết định các entity được tham chiếu bởi association cũng được thực hiện thao tác tương ứng hay không.

### 2.1. Database row và Java object là hai thứ khác nhau

Entity detached vẫn có ID và field Java, không có nghĩa row database đã bị xóa. Ngược lại, một managed entity có thể mang thay đổi trong memory chưa được commit. Vì vậy, luôn hỏi riêng:

- **Java:** object nào đang managed?
- **Database:** dữ liệu nào đã flush, commit hay rollback?

Hai câu hỏi này giúp tránh đồng nhất REFRESH hoặc DETACH với các thao tác ghi/xóa.

## 3. Tổng quan CascadeType

Enum `jakarta.persistence.CascadeType` có các giá trị:

| CascadeType | Khi nào được lan truyền? | Tác động chính |
|---|---|---|
| `PERSIST` | `em.persist(parent)` | Quản lý entity mới liên quan |
| `MERGE` | `em.merge(parent)` | Sao chép state sang managed entities |
| `REMOVE` | `em.remove(parent)` | Yêu cầu xóa entity liên quan |
| `REFRESH` | `em.refresh(parent)` | Nạp lại state liên quan từ database |
| `DETACH` | `em.detach(parent)` | Tách entity liên quan khỏi context |
| `ALL` | Tất cả thao tác trên | Bao gồm REFRESH, DETACH và REMOVE |

Có thể khai báo một hoặc nhiều cascade:

```java
@OneToMany(
    mappedBy = "order",
    cascade = {
        CascadeType.PERSIST,
        CascadeType.MERGE,
        CascadeType.REFRESH,
        CascadeType.DETACH
    }
)
private List<OrderLine> lines = new ArrayList<>();
```

`CascadeType.ALL` không phải lựa chọn “an toàn mặc định”. Với một association tới entity dùng chung, đặc biệt `@ManyToOne` hoặc `@ManyToMany`, dùng ALL có thể lan truyền `REMOVE` ngoài dự kiến. REFRESH/DETACH cũng có thể ảnh hưởng những phần khác của unit of work.

### 3.1. Cascade là chính sách lifecycle, không phải SQL FK CASCADE

JPA cascade là **quy tắc lan truyền thao tác entity**. Nó không đồng nghĩa:

```sql
FOREIGN KEY (...) REFERENCES ... ON DELETE CASCADE
```

DB cascade là cơ chế database khi xóa parent; JPA REFRESH/DETACH không yêu cầu database xóa hàng.

## 4. Hiểu hướng lan truyền

Giả sử quan hệ một-nhiều:

```text
PurchaseOrder 1 ------ N OrderLine

PurchaseOrder.lines:
  @OneToMany(mappedBy = "order",
             cascade = {REFRESH, DETACH})

OrderLine.order:
  @ManyToOne
  @JoinColumn(name = "order_id")
```

Nếu cascade đặt tại `PurchaseOrder.lines`:

```text
em.refresh(order)
    |
    +-- REFRESH Order
    +-- REFRESH Line A
    +-- REFRESH Line B

em.detach(order)
    |
    +-- DETACH Order
    +-- DETACH Line A
    +-- DETACH Line B
```

Nhưng khi không khai báo cascade trên `OrderLine.order`:

```java
em.refresh(line); // Không tự lan tới Order.
em.detach(line);  // Không tự lan tới Order.
```

**Cascade có hướng.** Nó đi từ entity đang được thao tác qua **association có cấu hình cascade tại phía entity đó**. Không nên hiểu một quan hệ hai chiều nghĩa là cascade tự đi cả hai phía.

### 4.1. Owning side và hướng cascade là hai vấn đề khác nhau

Trong ví dụ:

- `OrderLine.order` là owning side vì ánh xạ cột FK `order_id`.
- `PurchaseOrder.lines` là inverse side vì dùng `mappedBy="order"`.
- Cascade REFRESH/DETACH đặt ở **inverse side** vẫn có thể lan truyền từ Order xuống các Line.

Owning side quyết định ai quản lý FK, còn cascade quyết định đường đi của thao tác vòng đời. Không cần chuyển cascade sang owning side chỉ vì cột FK nằm ở bảng child.

## 5. Mô hình ví dụ: PurchaseOrder và OrderLine

Ta sử dụng aggregate đơn hàng: mỗi `OrderLine` chỉ thuộc một `PurchaseOrder`. Đây là trường hợp hợp lý để xem xét các cascade từ owner xuống children.

### 5.1. Schema

```sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    note VARCHAR(255),
    version BIGINT NOT NULL
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    sku VARCHAR(50) NOT NULL,
    quantity INTEGER NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT fk_order_lines_order
        FOREIGN KEY (order_id) REFERENCES purchase_orders(id),
    CONSTRAINT chk_order_lines_quantity CHECK (quantity > 0)
);
```

DDL chỉ minh họa; cú pháp IDENTITY khác nhau giữa DBMS. Đặc điểm chính là `order_lines.order_id` trỏ về `purchase_orders.id`.

### 5.2. Entity cha

```java
package demo.domain;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

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

    @Column(name = "order_number",
            nullable = false, unique = true, length = 40)
    private String orderNumber;

    @Column(name = "note", length = 255)
    private String note;

    @Version
    private Long version;

    @OneToMany(
        mappedBy = "order",
        cascade = {
            CascadeType.PERSIST,
            CascadeType.MERGE,
            CascadeType.REFRESH,
            CascadeType.DETACH
        },
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
        // JPA
    }

    public PurchaseOrder(String orderNumber, String note) {
        this.orderNumber = Objects.requireNonNull(orderNumber);
        this.note = note;
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public String getNote() {
        return note;
    }

    public Long getVersion() {
        return version;
    }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }

    public void changeNote(String newNote) {
        this.note = newNote;
    }

    public void addLine(String sku, int quantity) {
        lines.add(new OrderLine(this, sku, quantity));
    }

    public void removeLine(OrderLine line) {
        Objects.requireNonNull(line);

        if (lines.remove(line)) {
            line.detachFromOrder();
        }
    }
}
```

### 5.3. Entity con

```java
package demo.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

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

    @Column(name = "sku", nullable = false, length = 50)
    private String sku;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    @Version
    private Long version;

    protected OrderLine() {
        // JPA
    }

    OrderLine(PurchaseOrder order, String sku, int quantity) {
        this.order = Objects.requireNonNull(order);
        this.sku = Objects.requireNonNull(sku);
        changeQuantity(quantity);
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }

    public Long getVersion() {
        return version;
    }

    public PurchaseOrder getOrder() {
        return order;
    }

    public void changeQuantity(int newQuantity) {
        if (newQuantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive");
        }

        quantity = newQuantity;
    }

    void detachFromOrder() {
        this.order = null;
    }
}
```

**Những điều cần nhận ra:**

1. Mỗi Order và Line là entity có ID riêng.
2. `OrderLine.order` là phía quản lý FK.
3. `PurchaseOrder.lines` là phía inverse nhưng có cascade REFRESH/DETACH.
4. `OrderLine.order` không có cascade, vì vậy thao tác trên Line không tự lan ngược tới Order.
5. `orphanRemoval=true` là chính sách **xóa child khi rời association sở hữu vòng đời**, không phải một cascade REFRESH hay DETACH.
6. `@Version` trên cả hai entity giúp minh họa concurrency/optimistic locking, không quyết định cascade.
7. Getter trả view read-only để các thao tác association đi qua helper của aggregate.
8. Mô hình này chỉ phục vụ bài học: nghiệp vụ đơn hàng thật còn cần tính tổng, tính giá, SKU, trạng thái đơn và nhiều invariant khác.

### 5.4. Tạo dữ liệu nền

```java
EntityManager em = emf.createEntityManager();

try {
    EntityTransaction tx = em.getTransaction();
    tx.begin();

    try {
        PurchaseOrder order =
            new PurchaseOrder("ORD-001", "Initial note");

        order.addLine("SKU-A", 2);
        order.addLine("SKU-B", 5);

        em.persist(order);
        tx.commit();

        System.out.println("Order ID: " + order.getId());
    } catch (RuntimeException failure) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw failure;
    }
} finally {
    em.close();
}
```

Vì association có `CascadeType.PERSIST`, khi persist Order, các Line mới thuộc collection được persist theo mapping. Sau khi tạo dữ liệu nền, hãy dùng **EntityManager mới** cho từng thí nghiệm để không nhầm dữ liệu trong first-level cache với dữ liệu đã commit.

## 6. REFRESH: làm mới managed state từ database

`EntityManager.refresh(entity)` yêu cầu provider làm mới persistent state của **một managed entity** từ database.

```java
PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);

order.changeNote("Temporary note");

em.refresh(order);
```

Giả sử database lưu:

```text
purchase_orders.note = "Initial note"
```

và thay đổi local `"Temporary note"` chưa được flush, khi refresh thành công:

```text
Trước refresh:
  order.note = "Temporary note"

Sau refresh:
  order.note = "Initial note"
  em.contains(order) = true
```

REFRESH **không detach** entity; instance vẫn managed. Tác động chính là **ghi đè state persistent đã giữ trong memory** bằng state đọc từ database.

### 6.1. Refresh không giống find()

```java
PurchaseOrder first =
    em.find(PurchaseOrder.class, orderId);

PurchaseOrder second =
    em.find(PurchaseOrder.class, orderId);
```

Trong cùng context, hai biến thường tham chiếu **cùng managed Java instance**, và lần find thứ hai không nhất thiết tạo SQL SELECT mới.

`refresh(first)` khác: đó là yêu cầu rõ ràng **tải lại state** của entity đang managed, thay vì chỉ truy xuất entity identity từ context. Vì vậy nó có thể được dùng khi context giữ dữ liệu đã cũ do transaction khác, DB trigger hoặc thao tác SQL ngoài ORM.

### 6.2. State được làm mới không phải “kết quả mới nhất tuyệt đối”

REFRESH đọc theo quy tắc database và transaction isolation hiện hành. Nếu transaction đang ở isolation level phù hợp hoặc dữ liệu bị transaction khác thay đổi đồng thời, refresh không tạo một giao thức đồng bộ toàn hệ thống. Nó không tự bảo đảm câu trả lời “mới nhất trên toàn thế giới” tại mọi thời điểm.

## 7. CascadeType.REFRESH: làm mới cả phần liên quan

Ví dụ trên Order có:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.REFRESH
)
private List<OrderLine> lines;
```

Khi:

```java
em.refresh(order);
```

JPA làm mới Order và **lan truyền thao tác refresh** đến các OrderLine liên quan theo cấu hình. Vì vậy, nếu đã sửa một Line managed chưa flush, local state của Line có thể bị ghi đè.

### 7.1. Ví dụ cụ thể

Giả sử database đã commit:

```text
Order#10.note = "Initial note"
Line#100.quantity = 2
```

Trong transaction mới:

```java
PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);

OrderLine line = order.getLines().get(0);

order.changeNote("Draft");
line.changeQuantity(99);

em.refresh(order);
```

Với association có cascade REFRESH và không có flush những thay đổi local trước đó, kết quả mong muốn khi refresh thành công:

```text
order.note trở về "Initial note"
line.quantity trở về 2

em.contains(order) == true
em.contains(line) == true
```

Điều này rất khác gọi `detach()`. Cả hai object vẫn managed; chỉ state persistent đã được nạp lại.

### 7.2. Nếu không khai báo REFRESH

Nếu `Order.lines` **không có** `CascadeType.REFRESH` hoặc `CascadeType.ALL`, gọi:

```java
em.refresh(order);
```

không có nghĩa JPA phải refresh **từng Line** do cascade. Một Line đang managed và có giá trị local có thể tiếp tục giữ state đó. Provider có thể cập nhật phần association/collection theo quy tắc riêng, nên không nên tuyệt đối hóa rằng mọi reference hay list membership đều luôn giữ nguyên. Nhưng **refresh parent không thay thế refresh child khi không có cascade**.

### 7.3. Khi nào có lợi?

Cascade REFRESH có thể hữu ích nếu Order và Line là một aggregate nhỏ, có ownership rõ ràng, và use case **cố ý làm mới toàn bộ aggregate** (ví dụ “Tải lại bản lưu cuối cùng” trong giao diện chỉnh sửa).

Ngược lại, khi chỉ cần làm mới đúng một Line:

```java
OrderLine line = em.find(OrderLine.class, lineId);
em.refresh(line);
```

thường có phạm vi dễ kiểm soát hơn một refresh trên Order có hàng trăm children.

## 8. REFRESH có thể làm mất local edits

Một lỗi thiết kế phổ biến:

```java
order.changeNote("Khách vừa sửa ghi chú");
line.changeQuantity(10);

// Một helper nghĩ rằng làm mới order luôn an toàn:
em.refresh(order);
```

Nếu association có cascade REFRESH, **cả ghi chú và số lượng vừa sửa nhưng chưa flush** có thể bị ghi đè. REFRESH không phải thao tác đọc thuần không có tác dụng phụ lên object graph.

Trong workflow chỉnh sửa:

- Nếu muốn giữ những thay đổi chưa lưu, đừng refresh graph tùy tiện.
- Nếu muốn người dùng xác nhận “Bỏ thay đổi”, hãy xác định chính xác phạm vi cần khôi phục.
- Nếu có optimistic locking conflict, đừng refresh rồi âm thầm ghi đè ý định người dùng.
- Nếu chỉ cần xem dữ liệu hiện tại, có thể dùng query/projection/DTO trong context riêng thay vì refresh managed aggregate đang sửa.

### 8.1. Không dùng refresh để undo SQL đã flush

Ví dụ:

```java
tx.begin();

line.changeQuantity(15);
em.flush();       // UPDATE có thể đã chạy trong TX.

em.refresh(line); // Không phải rollback UPDATE.

tx.commit();
```

Nếu flush đã ghi quantity=15 vào database **trong transaction này**, refresh có thể đọc lại chính giá trị 15 vì transaction nhìn thấy những thay đổi của mình.

Muốn hủy cả transaction, dùng:

```java
tx.rollback();
```

Không dùng refresh thay cho rollback. Một provider có thể flush ở những thời điểm khác nhau tùy operation, generator và flush mode, nên cần kiểm soát unit of work chứ không dựa vào một timeline SQL cứng.

### 8.2. Nếu refresh xảy ra sau exception tại flush

```java
try {
    em.flush(); // Có thể ném constraint exception.
} catch (RuntimeException ex) {
    em.refresh(order); // Không phải cách chữa transaction lỗi.
}
```

Một lỗi persistence có thể đánh dấu transaction rollback-only hoặc khiến context không còn phù hợp để tiếp tục. Cách xử lý thường an toàn là rollback, kết thúc unit of work, rồi tải dữ liệu trong transaction/context mới nếu cần.

## 9. REFRESH và version/concurrency

Một entity có:

```java
@Version
private Long version;
```

hỗ trợ optimistic locking khi cập nhật. Giả sử:

```text
Transaction A:
  load Line#100, version=3, quantity=2

Transaction B:
  load Line#100, version=3
  quantity=4
  commit -> version=4

Transaction A:
  vẫn đang giữ version=3 trong context
```

Nếu A update với version cũ, provider có thể báo `OptimisticLockException` tại flush/commit.

`em.refresh(line)` có thể nạp lại state và version theo transaction visibility, nhưng điều đó **có thể xóa những thay đổi local của A**. Nó không tự giải quyết business conflict.

Một workflow đúng khi có xung đột:

1. Rollback transaction đã lỗi.
2. Mở transaction/context mới.
3. Load dữ liệu đang được commit.
4. So sánh version hoặc ý định thay đổi.
5. Quyết định giữ sửa đổi nào, yêu cầu người dùng xác nhận hay thử lại có giới hạn.
6. Commit khi invariant vẫn hợp lệ.

JPA cũng có overload:

```java
em.refresh(managedLine, LockModeType.OPTIMISTIC);
```

Cần transaction phù hợp cho lock mode; yêu cầu và hành vi cụ thể tùy JPA provider/database. Không dùng lock mạnh như một “lá chắn” mặc định cho mọi refresh.

## 10. DETACH: ngừng quản lý entity

`EntityManager.detach(entity)` khiến managed entity không còn được theo dõi bởi persistence context hiện tại.

```java
PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);

System.out.println(em.contains(order)); // true

em.detach(order);

System.out.println(em.contains(order)); // false
```

Sau detach:

- Object `order` vẫn tồn tại trong memory.
- Các field đã load vẫn có thể đọc/sửa như object Java bình thường.
- Những thay đổi persistent sau detach **không được dirty checking** của context cũ tự động ghi.
- Lazy proxy/collection chưa tải có thể không truy cập được khi không còn context thích hợp.
- Không có yêu cầu DELETE row hay hủy foreign key chỉ vì detach.

### 10.1. DETACH không phải xóa liên kết

```java
em.detach(order);
```

không tương đương:

```java
order.removeLine(line);
```

Với detach, Java references như `order.getLines()` và `line.getOrder()` vẫn có thể tồn tại. Không có quy tắc “detach nghĩa là đặt `order_id=NULL`”.

### 10.2. DETACH không phải rollback

Nếu SQL `UPDATE` đã chạy trong transaction, detach không tự hủy lệnh SQL đó. Nếu transaction commit, những SQL đã thực thi thành công trong transaction vẫn có thể được xác nhận.

## 11. CascadeType.DETACH: tách graph theo association

Trên Order:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.DETACH
)
private List<OrderLine> lines;
```

Khi gọi:

```java
em.detach(order);
```

JPA lan truyền detach đến những Line liên quan theo association đó.

```text
TRƯỚC:
  Persistence Context
      Order#10          managed
        |
        +-- Line#100    managed
        +-- Line#101    managed

Gọi em.detach(order)
với cascade DETACH trên Order.lines

SAU:
      Order#10          detached
        |
        +-- Line#100    detached
        +-- Line#101    detached

Các hàng trong database không bị xóa chỉ vì detach.
```

### 11.1. Kiểm tra bằng em.contains()

```java
PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);

OrderLine firstLine = order.getLines().get(0);

System.out.println(em.contains(order));     // true
System.out.println(em.contains(firstLine)); // true

em.detach(order);

System.out.println(em.contains(order));     // false
System.out.println(em.contains(firstLine)); // false
```

Ở đây giả định Order có ít nhất một Line và Line đã là managed. Một test trên provider thực tế có thể ghi nhận việc cascade khi collection đã hoặc chưa khởi tạo, nhưng không nên tự khẳng định rằng DETACH chắc chắn phát hoặc không phát một số SELECT cụ thể trên mọi provider.

### 11.2. Nếu không cấu hình cascade DETACH?

Giả sử `Order.lines` không khai báo DETACH hoặc ALL. Khi:

```java
em.detach(order);
```

Order không còn managed, nhưng **Line đã load và đang managed có thể tiếp tục managed** trong cùng EntityManager.

```text
Order#10:   detached
Line#100:   vẫn managed

Line#100.order:
  vẫn có thể trỏ tới Java object Order#10 đã detached.
```

Đây không phải lỗi association. Một object managed hoàn toàn có thể tham chiếu một object detached trong Java memory. Trạng thái quản lý của từng object là chuyện riêng, không đồng nghĩa FK đã thay đổi.

### 11.3. Tác động đến dirty checking của child

Nếu `line` không bị detach:

```java
em.detach(order);       // Không cascade.
line.changeQuantity(9); // Line vẫn managed.
tx.commit();
```

thay đổi quantity có thể được flush/commit nếu transaction hợp lệ. Nếu `line` bị cascade DETACH cùng Order, setter sau detach không được context cũ theo dõi.

**Không coi detach parent là detach toàn graph nếu không có cascade.**

## 12. DETACH trước flush và sau flush

### 12.1. Sửa rồi detach trước flush

```java
tx.begin();

PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);

OrderLine line = order.getLines().get(0);

order.changeNote("Draft");
line.changeQuantity(99);

em.detach(order); // Cascade DETACH.

tx.commit();
```

Khi những thay đổi trên chưa được đồng bộ trước detach, provider không còn tiếp tục theo dõi parent/child để tự flush chúng ở commit. Vì vậy không nên kỳ vọng draft và quantity=99 được lưu.

Điều này khác refresh: refresh có thể **ghi đè state Java**; detach thường **giữ object Java với state đã mutate nhưng ngừng tracking**.

### 12.2. Flush rồi detach

```java
tx.begin();

PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);

OrderLine line = order.getLines().get(0);
line.changeQuantity(8);

em.flush();       // SQL có thể đã UPDATE trong TX.
em.detach(order); // Cascade DETACH sang Line.

tx.commit();
```

Nếu flush và commit thành công, SQL đã thực thi trong transaction vẫn có thể được commit. DETACH không tự rollback SQL đã flush.

### 12.3. Sửa object sau detach

```java
em.detach(order);

order.changeNote("Edited while detached");
line.changeQuantity(77);
```

Những setter này chỉ sửa Java objects detached. Chúng không tự sinh SQL UPDATE trong EntityManager đã detach chúng. Để lưu, cần load entity managed trong unit of work mới rồi áp dụng thay đổi hoặc dùng `merge` đúng cách.

## 13. So sánh detach(), clear() và close()

| Thao tác | Phạm vi detach | Cần cascade DETACH? | EntityManager có tiếp tục dùng được? |
|---|---|---|---|
| `em.detach(order)` | Một entity và các entity được cascade | Có, nếu muốn tách related entities | Có |
| `em.clear()` | Tất cả managed entities trong context | Không | Có |
| `em.close()` | Kết thúc application-managed EntityManager và context gắn với nó | Không | Không |
| Kết thúc transaction-scoped context | Các entity của context đó | Không cần cấu hình cascade DETACH để đóng context | Container/framework quản lý |

### 13.1. detach chọn lọc

```java
em.detach(order);
```

Một Order và những Lines được cascade sẽ ngừng tracking, nhưng một `Customer` không liên quan vẫn có thể managed.

### 13.2. clear toàn context

```java
em.clear();
```

Tất cả managed entities trở thành detached, bất kể association có cascade DETACH hay không. EntityManager vẫn mở và có thể load entity khác.

### 13.3. close EntityManager do ứng dụng tạo

```java
em.close();
```

Kết thúc EntityManager. Không tiếp tục gọi `find`, `refresh` hoặc `detach` trên EM đã đóng. Không dùng `close` thay cho `commit` hay `rollback` khi transaction còn active.

### 13.4. Với transaction-scoped context

Trong container-managed transaction-scoped model hoặc cách binding Spring JPA phổ biến, context thường kết thúc khi transaction kết thúc. Các entity trở thành detached khi context đó kết thúc **không cần cascade DETACH**.

Một injected EntityManager có thể là proxy tồn tại lâu trong một bean, nhưng lifetime của proxy không phải lifetime managed context. Không gọi close thủ công trên injected container-managed EntityManager.

## 14. DETACH và MERGE

Một detached entity không tự được persist khi gọi setter. Nếu muốn cập nhật:

```java
em.detach(order);

order.changeNote("Edited offline");

PurchaseOrder managedCopy = em.merge(order);
```

`merge` sao chép state từ detached object sang một managed instance. Nó **không bắt buộc biến chính object đầu vào thành managed**.

```java
System.out.println(em.contains(order));       // false
System.out.println(em.contains(managedCopy)); // true
```

### 14.1. Vì sao cascade MERGE độc lập cascade DETACH?

Nếu Order và Lines cùng detached rồi application sửa nhiều Line, để merge graph với các thay đổi của child, association thường cần cascade MERGE thích hợp:

```java
@OneToMany(
    mappedBy = "order",
    cascade = {
        CascadeType.MERGE,
        CascadeType.DETACH
    }
)
private List<OrderLine> lines;
```

Nhưng merge graph dài hoặc dữ liệu client không tin cậy có thể ghi đè field ngoài ý muốn. Với API thực tế, thường dễ kiểm soát hơn nếu dùng DTO, tải lại Order managed và áp dụng những thay đổi được phép.

### 14.2. REFRESH không phải MERGE

- `refresh(managed)` lấy state **từ database về managed entity**.
- `merge(detached)` sao chép state **từ detached object sang managed entity**.
- `detach(managed)` ngừng quản lý object.

Ba phương thức đi theo những hướng dữ liệu khác nhau; không hoán đổi được.

## 15. CascadeType.ALL và rủi ro trên entity dùng chung

Xét đơn hàng có tham chiếu khách hàng:

```java
@Entity
public class Invoice {

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;
}
```

`Customer` có identity riêng, có thể được nhiều Invoice tham chiếu.

Nếu khai báo:

```java
@ManyToOne(cascade = CascadeType.ALL)
private Customer customer;
```

thao tác remove Invoice có thể lan truyền REMOVE tới Customer — điều thường **không đúng nghiệp vụ**. Ngoài ra:

- Refresh Invoice có thể lan truyền refresh tới Customer.
- Detach Invoice có thể lan truyền detach tới Customer.
- Persist/Merge cũng lan truyền theo quy tắc tương ứng.

**Không bật ALL chỉ vì muốn đơn giản hóa code.** Trên shared reference, mặc định nên giới hạn cascade, chỉ khai báo khi có lý do rõ ràng.

### 15.1. Rủi ro REFRESH trên shared Customer

Giả sử một service đang sửa Customer:

```java
Customer customer = em.find(Customer.class, customerId);
customer.rename("Tên vừa chỉnh, chưa flush");

Invoice invoice = em.find(Invoice.class, invoiceId);
em.refresh(invoice);
```

Nếu `Invoice.customer` có cascade REFRESH, thao tác trên Invoice có thể ghi đè state Customer đang sửa trong cùng persistence context. Một phần code tưởng chỉ cần nạp lại hóa đơn lại ảnh hưởng unit of work quản lý khách hàng.

### 15.2. Rủi ro DETACH trên shared Customer

```java
Invoice invoice = em.find(Invoice.class, invoiceId);
Customer customer = invoice.getCustomer();

em.detach(invoice);
```

Nếu `Invoice.customer` có cascade DETACH, Customer cũng bị tách khỏi context. Các setter sau đó trên Customer có thể không được dirty checking như caller mong đợi.

**Nguyên tắc:** khi entity liên quan được dùng chung hoặc có lifecycle độc lập, cascade REFRESH/DETACH cần được xem xét kỹ, không suy từ sự tồn tại của reference rằng thao tác phải lan truyền.

## 16. Cascade trên ManyToMany

Một Project có nhiều User và một User tham gia nhiều Project:

```java
@ManyToMany
@JoinTable(
    name = "project_members",
    joinColumns = @JoinColumn(name = "project_id"),
    inverseJoinColumns = @JoinColumn(name = "member_id")
)
private Set<User> members = new HashSet<>();
```

Nếu bật `CascadeType.REFRESH` hoặc `CascadeType.DETACH`, thao tác trên Project có thể ảnh hưởng các User đang managed.

Ví dụ:

- Refresh Project có thể ghi đè local edits của User.
- Detach Project có thể khiến User bị detach và ngừng dirty checking.
- Nếu dùng ALL, REMOVE còn có thể cố xóa User vốn được nhiều Project sử dụng.

Quan hệ many-to-many thường liên kết **những entity độc lập**. Không dùng cascade REMOVE/DETACH/REFRESH mặc định cho graph chia sẻ nếu không có use case cụ thể và policy rõ ràng.

## 17. REFRESH/DETACH khác orphanRemoval

`orphanRemoval` áp dụng cho `@OneToOne` hoặc `@OneToMany` khi một child thuộc vòng đời owner bị loại khỏi association.

```java
@OneToMany(
    mappedBy = "order",
    orphanRemoval = true
)
private List<OrderLine> lines;
```

Nếu ứng dụng làm:

```java
order.removeLine(line);
```

với managed child trong một association orphan-removal hợp lệ, JPA áp dụng thao tác remove cho orphan theo semantics của đặc tả. Sau transaction thành công, row child có thể bị DELETE.

Nhưng:

```java
em.detach(order);
```

không có nghĩa child bị loại khỏi association và không tự xóa row.

### 17.1. Bảng phân biệt

| Thao tác | Mục đích | Row child có bị xóa vì thao tác này không? |
|---|---|---|
| `em.refresh(order)` | Làm mới state | Không |
| `em.detach(order)` | Dừng quản lý | Không |
| `em.clear()` | Dừng quản lý toàn context | Không |
| `em.remove(line)` | Xóa managed entity | Có thể DELETE sau flush/commit |
| `order.removeLine(line)` + orphanRemoval | Xóa child khỏi aggregate sở hữu vòng đời | Có thể DELETE managed orphan |
| `tx.rollback()` | Hủy các thay đổi DB chưa commit | Không phải xóa child vì unlink |

### 17.2. DETACH không tạo orphan

Nếu `order.lines` vẫn chứa `line`, và `line.order` vẫn trỏ về order, detach chỉ ảnh hưởng **persistence management**. Nó không tự đặt FK thành null hoặc loại phần tử khỏi collection Java.

### 17.3. REFRESH không phải API undo orphan removal

Nếu đã làm:

```java
tx.begin();

PurchaseOrder order = em.find(
    PurchaseOrder.class, orderId);

OrderLine line = order.getLines().get(0);

order.removeLine(line); // orphanRemoval=true

em.refresh(order);      // Không phải undo portable.
```

Đừng dựa vào việc refresh parent để đảo ngược orphan removal đã được xác lập. Việc JPA quản lý orphan, scheduled remove và flush có thể khiến những giả định về reattach/re-add không portable.

Muốn hủy thao tác trong transaction, **rollback** là cơ chế rõ ràng. Tạo unit of work mới và tải lại aggregate nếu cần.

### 17.4. DETACH không phải API hủy pending DELETE

Tương tự:

```java
order.removeLine(line);
em.detach(order);
tx.commit();
```

không phải pattern đáng tin cậy để hủy một thao tác orphan removal đang chờ. Nếu không muốn commit thay đổi, rollback transaction thay vì cố detach graph để “xóa dấu vết”.

## 18. REFRESH và lazy loading

Association `@OneToMany` thường có fetch type LAZY:

```java
@OneToMany(
    mappedBy = "order",
    fetch = FetchType.LAZY,
    cascade = CascadeType.REFRESH
)
private List<OrderLine> lines;
```

Khi refresh Order, provider cần làm mới persistent state và thực hiện các quy tắc cascade; chi phí SQL có thể phụ thuộc vào collection đã được khởi tạo hay chưa, fetch plan và implementation.

Không nên khẳng định:

- “Có cascade REFRESH thì luôn đúng một SELECT.”
- “Cascade REFRESH luôn tải toàn bộ graph chỉ bằng một JOIN.”
- “Không nhìn thấy SQL tức là dữ liệu chắc chắn mới nhất.”

Với graph lớn, cascade REFRESH có thể làm nhiều entity được làm mới hơn cần thiết và tăng round-trip. Nếu chỉ cần quantity hiện tại của một Line, việc refresh riêng Line hoặc đọc một projection có thể hiệu quả hơn.

### 18.1. REFRESH và collection state

Một collection managed có thể có thay đổi membership chưa flush. Refresh parent không phải API chung cho việc phục hồi tất cả thay đổi collection trong mọi tình huống, đặc biệt khi có `orphanRemoval`, insert/remove pending hoặc những quan hệ phức tạp. Thay vì cố dự đoán từng trường hợp, hãy sử dụng transaction rollback khi cần hủy một unit of work.

## 19. DETACH và lazy loading

`@OneToMany(fetch=LAZY)` cũng gây chú ý khi detach.

```java
PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);

em.detach(order);

order.getLines().size();
```

Nếu collection `lines` chưa được tải và provider dùng lazy proxy, truy cập sau detach có thể thất bại, chẳng hạn `LazyInitializationException` trong Hibernate. Đây là exception của Hibernate, không phải tên exception tiêu chuẩn của JPA trên mọi provider.

Field đã load vẫn có thể được đọc vì object Java vẫn còn. Nhưng một object detached không có bảo đảm được tải thêm association từ persistence context cũ.

### 19.1. DTO là cách cắt ranh giới rõ ràng

Thay vì trả entity graph cho controller/serializer, có thể dùng:

```java
public record OrderLineDto(
    Long id,
    String sku,
    int quantity
) {}

public record OrderDto(
    Long id,
    String orderNumber,
    List<OrderLineDto> lines
) {}
```

Xây DTO trong unit of work đang có fetch plan phù hợp. Sau đó EntityManager có thể đóng mà response không phụ thuộc lazy loading.

### 19.2. Không phụ thuộc vào việc DETACH luôn không phát SQL

DETACH không có mục đích tải lại dữ liệu, nhưng provider có thể phải duyệt các association theo quy tắc cascade, và hành vi trên lazy proxies/collections có thể khác nhau. Vì vậy, khi tối ưu, quan sát SQL thực tế trên stack đang dùng thay vì suy từ tên phương thức.

## 20. Transaction-scoped context và ứng dụng Spring

Trong Spring Data JPA, service thường dùng:

```java
@Service
public class OrderService {

    private final PurchaseOrderRepository repository;

    public OrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void updateNote(Long id, String note) {
        PurchaseOrder order = repository.findById(id)
            .orElseThrow(() ->
                new IllegalArgumentException("Order not found"));

        order.changeNote(note);
    }
}
```

Ở cấu hình Spring transaction-bound thông dụng, entity được quản lý trong transaction và kết thúc context theo cơ chế transaction manager. Không cần `em.detach(order)` thủ công chỉ để entity trở thành detached khi service transaction/context đóng.

`@Transactional` cũng không tự biến persistence context thành extended context. Nếu Spring OSIV được bật, EntityManager có thể mở tới cuối web request, **dài hơn service transaction**, nhưng đó không đồng nghĩa một transaction dài tới cuối request.

### 20.1. Khi nào cần DETACH thủ công trong Spring?

Có thể có use case cần ngừng theo dõi một entity hoặc graph **trước khi transaction/context kết thúc**. Khi đó `em.detach` có thể là công cụ phù hợp, nhưng cần chứng minh rõ:

- Vì sao không giữ entity managed tới commit?
- Những thay đổi trước detach có cần được flush không?
- Cascade sang những entity liên quan có làm chúng ngừng theo dõi ngoài dự kiến không?
- Code có tiếp tục dùng graph detached sau method không?
- Có cơ chế merge/reload nếu muốn lưu tiếp không?

Không lạm dụng DETACH như công cụ “giảm memory” cho mọi request ngắn. Khi xử lý batch lớn, `flush`/`clear` theo chunk hoặc transaction mới thường dễ quản lý hơn.

## 21. JTA và extended persistence context

Trong môi trường Jakarta EE có container-managed EntityManager:

```java
@PersistenceContext(type = PersistenceContextType.TRANSACTION)
private EntityManager em;
```

context transaction-scoped thường gắn với JTA transaction. Trong một số workflow stateful:

```java
@PersistenceContext(type = PersistenceContextType.EXTENDED)
private EntityManager em;
```

context có thể tồn tại qua nhiều transactions và tiếp tục quản lý entities.

Trong extended context, `detach` có thể hữu ích để tách **chọn lọc** một graph khỏi vùng managed state đang sống lâu. Tuy nhiên, extended context không làm biến nhiều transaction thành một transaction dài. REFRESH cũng không tự commit những thay đổi pending.

Nếu context là unsynchronized với JTA, cần hiểu quy tắc `joinTransaction()`. Gọi REFRESH/DETACH không thay thế việc tham gia transaction hay quản lý rollback-only.

## 22. REFRESH trên entity mới hoặc detached

`EntityManager.refresh()` là thao tác trên entity **managed** hợp lệ.

Sai:

```java
PurchaseOrder newOrder =
    new PurchaseOrder("ORD-X", "Draft");

em.refresh(newOrder); // Không phải persist.
```

Sai:

```java
PurchaseOrder detached = obtainFromClosedContext();

em.refresh(detached); // Không phải reattach.
```

Với entity không managed, API có thể ném `IllegalArgumentException` theo contract. Nếu row không còn tồn tại ở database, `EntityNotFoundException` hoặc những lỗi persistence phù hợp có thể xảy ra tùy thời điểm/phương thức truy xuất.

Muốn làm mới entity đã detached:

```java
PurchaseOrder managed =
    em.find(PurchaseOrder.class, detached.getId());

if (managed != null) {
    em.refresh(managed);
}
```

Đây là ví dụ thao tác riêng trên **managed instance**. Đừng dùng REFRESH để lưu state của detached object; đó là hướng dữ liệu ngược với merge hoặc load-and-edit.

## 23. Những lỗi sử dụng REFRESH thường gặp

### 23.1. Refresh parent làm mất local edits ở child

```java
line.changeQuantity(15);
em.refresh(order); // Có cascade REFRESH.
```

Các thay đổi quantity chưa flush có thể bị ghi đè. Nếu tác vụ chỉ cần refresh ghi chú Order, không nên mặc định refresh cả aggregate.

### 23.2. Dùng refresh để chữa transaction đã lỗi

```java
em.flush();  // Có thể lỗi constraint.
em.refresh(order);
tx.commit();
```

Một transaction bị đánh dấu rollback-only không trở thành hợp lệ chỉ vì refresh. Rollback và bắt đầu unit of work khác.

### 23.3. Refresh entity đang detached

```java
em.detach(order);
em.refresh(order);
```

Không portable như cách “gắn lại”. Hãy load managed instance và refresh chính instance đó khi cần.

### 23.4. Refresh tất cả như một chiến lược cache chung

Cascade REFRESH chỉ áp dụng theo association mapping. Nó không tự invalidates mọi second-level/query cache hoặc đồng bộ tất cả request. Khi dữ liệu được cập nhật ngoài ORM, cần chiến lược cache invalidation và consistency đầy đủ.

### 23.5. Nghĩ refresh không thay đổi Java object

Đây là hiểu nhầm trọng tâm. REFRESH có thể trực tiếp **thay giá trị persistent fields** trong managed object; nó không phải thao tác chỉ đọc không có ảnh hưởng state.

## 24. Những lỗi sử dụng DETACH thường gặp

### 24.1. Detach rồi mong commit tự lưu local changes

```java
line.changeQuantity(20);
em.detach(line);
tx.commit();
```

Nếu thay đổi chưa flush, không còn được dirty checking tự động sau detach.

### 24.2. Chỉ detach parent nhưng nghĩ mọi child đều detached

Khi không khai báo cascade DETACH, child đang managed có thể vẫn managed. Kiểm tra `em.contains(child)` hoặc xác định scope đúng.

### 24.3. Dùng detach như xóa association

Detach không xóa link Java, không đặt FK null và không xóa row.

### 24.4. Dùng detach để rollback

SQL đã flush vẫn thuộc transaction. Nếu commit, nó có thể được xác nhận. Muốn hủy, rollback transaction.

### 24.5. Cascade DETACH sang entity dùng chung

Một shared Customer hoặc Product có thể bị detach ngoài ý định, khiến service khác trong cùng context không còn dirty checking entity đó.

### 24.6. Dùng detached entity trong HashSet/Map thiếu chính sách equality

Entity detached vẫn có ID, nhưng Java object khác context có thể là reference khác. Nếu domain cần equality theo identity qua contexts, phải thiết kế `equals()/hashCode()` phù hợp. Cascade DETACH không tự bảo đảm equality giữa hai object cùng row.

### 24.7. Truy cập lazy graph sau detach

Một collection chưa load có thể không fetch được. Dùng DTO hoặc fetch plan trong context phù hợp.

### 24.8. Gọi API trên EntityManager đã close

`em.close()` kết thúc application-managed EM. Không gọi `em.detach`, `find` hoặc `refresh` trên EM đã đóng.

## 25. Bảng so sánh đầy đủ

| Tiêu chí | REFRESH | DETACH |
|---|---|---|
| Phương thức | `em.refresh(entity)` | `em.detach(entity)` |
| Cascade tương ứng | `CascadeType.REFRESH` | `CascadeType.DETACH` |
| Mục tiêu | Đồng bộ persistent state từ DB | Ngừng quản lý entity |
| Entity gốc sau thao tác thành công | Managed | Detached |
| Related entity khi có cascade | Được refresh | Được detach |
| Local edits chưa flush | Có thể bị ghi đè | Có thể không được ghi khi ngừng tracking |
| Dirty checking sau thao tác | Tiếp tục với managed state | Ngừng với detached state |
| Có thể phát SELECT? | Có | Không có mục tiêu load lại; chi phí traversal tùy provider |
| Có tự INSERT/UPDATE/DELETE không? | Không phải mục đích của refresh | Không phải mục đích của detach |
| Có tự commit/rollback không? | Không | Không |
| Có xóa child do orphanRemoval không? | Không phải thao tác orphan removal | Không phải thao tác orphan removal |
| Có được gọi trên detached entity? | Không để reattach | Detach entity đã detached không có tác dụng chuyển managed state |
| Thích hợp với graph sở hữu riêng? | Khi muốn reload graph có chủ đích | Khi muốn ngừng tracking graph có chủ đích |
| Rủi ro chính | Mất local edits; mở rộng phạm vi đọc/refresh | Mất dirty checking; tách shared entity ngoài dự kiến |

### 25.1. Bảng tác động theo annotation

Giả sử Order và những Line liên quan đang managed, chưa có thao tác xóa/flush đặc biệt:

| Cascade trên `Order.lines` | `em.refresh(order)` | `em.detach(order)` |
|---|---|---|
| Không có | Refresh Order; không yêu cầu refresh từng Line qua cascade | Chỉ detach Order |
| `REFRESH` | Refresh Order và lan sang Line | Không tự detach Line |
| `DETACH` | Không tự refresh Line | Detach Order và lan sang Line |
| `REFRESH, DETACH` | Lan REFRESH | Lan DETACH |
| `ALL` | Bao gồm REFRESH | Bao gồm DETACH và cả những cascade khác |
| Chỉ `orphanRemoval=true` | Không tự tạo REFRESH cascade | Không tự tạo DETACH cascade |

**Quan trọng:** bảng mô tả semantics; state bất thường như entity removed/new, collection lazy chưa load, orphan pending hoặc nhiều association cascade tạo thêm điều kiện cần xét cụ thể.

## 26. Thực hành 1 — REFRESH có cascade

1. Persist Order có hai Line và commit.
2. Mở EntityManager mới, bắt đầu transaction.
3. Load Order, gọi `getLines().size()` để lấy Line managed.
4. Ghi nhớ `note` và `quantity` từ DB.
5. Sửa cả hai field nhưng **không flush**.
6. Gọi `em.refresh(order)` với `CascadeType.REFRESH` trên collection.
7. In note/quantity sau refresh và `em.contains`.
8. Commit, đọc lại bằng EM mới.

Code trọng tâm:

```java
EntityTransaction tx = em.getTransaction();
tx.begin();

try {
    PurchaseOrder order =
        em.find(PurchaseOrder.class, orderId);

    OrderLine line = order.getLines().get(0);

    String noteBefore = order.getNote();
    int quantityBefore = line.getQuantity();

    order.changeNote("Temporary");
    line.changeQuantity(99);

    em.refresh(order);

    System.out.println(
        "Order restored = " + noteBefore.equals(order.getNote()));
    System.out.println(
        "Line restored = " + (quantityBefore == line.getQuantity()));

    System.out.println(em.contains(order)); // true
    System.out.println(em.contains(line));  // true

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
```

**Đối chứng:** bỏ cascade REFRESH trong một cấu hình thử nghiệm rồi lặp lại. Quan sát state Line và SQL log. Không thay đổi mapping production chỉ để chạy đối chứng.

## 27. Thực hành 2 — DETACH có và không có cascade

### Trường hợp A — Có cascade DETACH

```java
EntityManager em = emf.createEntityManager();

try {
    PurchaseOrder order =
        em.find(PurchaseOrder.class, orderId);

    OrderLine line = order.getLines().get(0);

    System.out.println(em.contains(order)); // true
    System.out.println(em.contains(line));  // true

    em.detach(order);

    System.out.println(em.contains(order)); // false
    System.out.println(em.contains(line));  // false
} finally {
    em.close();
}
```

Đây là thao tác kiểm tra lifecycle, không phải transaction ghi. Môi trường/provider cụ thể có thể có yêu cầu transaction khi tải/lock entity.

### Trường hợp B — Không cascade DETACH

1. Bỏ `CascadeType.DETACH` khỏi association trong một cấu hình test.
2. Mở context mới và load Order/Line.
3. Gọi `em.detach(order)`.
4. Kiểm tra Order detached.
5. Kiểm tra Line có thể vẫn managed.
6. Giải thích tại sao reference `line.getOrder()` vẫn có thể trỏ tới detached Order mà database FK không thay đổi.

## 28. Thực hành 3 — DETACH trước/sau flush

**Trường hợp 1:**

```java
tx.begin();

PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);

OrderLine line = order.getLines().get(0);

line.changeQuantity(12);
em.detach(order); // Cascade DETACH.
tx.commit();
```

**Trường hợp 2:**

```java
tx.begin();

PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);

OrderLine line = order.getLines().get(0);

line.changeQuantity(15);
em.flush();
em.detach(order);
tx.commit();
```

Chạy mỗi trường hợp trong **EntityManager riêng và transaction riêng**, có xử lý rollback nếu lỗi/close trong finally. Đọc lại quantity bằng EM mới. Giải thích vì sao flush trước detach thay đổi kết quả, và vì sao detach không phải commit.

## 29. Thực hành 4 — REFRESH sau cập nhật từ transaction khác

```java
EntityManager emA = emf.createEntityManager();
EntityManager emB = emf.createEntityManager();

try {
    OrderLine lineA =
        emA.find(OrderLine.class, lineId);

    int original = lineA.getQuantity();

    EntityTransaction txB = emB.getTransaction();
    txB.begin();

    try {
        OrderLine lineB =
            emB.find(OrderLine.class, lineId);

        lineB.changeQuantity(original + 2);
        txB.commit();
    } catch (RuntimeException ex) {
        if (txB.isActive()) {
            txB.rollback();
        }
        throw ex;
    }

    OrderLine againA =
        emA.find(OrderLine.class, lineId);

    System.out.println(lineA == againA); // true

    emA.refresh(lineA); // Nạp lại theo visibility hiện tại.

    System.out.println(lineA.getQuantity());
} finally {
    emA.close();
    emB.close();
}
```

Quan sát:

- Context A có thể giữ instance cũ khi tìm lại cùng ID.
- Refresh chủ động lấy state database phù hợp.
- Nếu database isolation/provider yêu cầu active transaction, thực hiện refresh trong transaction thích hợp.
- Không coi refresh là cơ chế chống mọi race condition.

## 30. Thực hành 5 — So sánh cascade với orphanRemoval

1. Tạo Order có hai Lines, commit.
2. Mở context mới, gọi `em.detach(order)` với cascade DETACH, không gỡ Line khỏi association.
3. Đọc lại database và xác nhận các Line vẫn còn.
4. Ở transaction khác, tải managed Order, gọi `order.removeLine(line)`.
5. Commit, kiểm tra row Line bị xóa theo `orphanRemoval=true`.
6. Ở transaction khác, gọi `em.refresh(order)` có cascade REFRESH; xác nhận đây không phải lệnh DELETE.
7. Giải thích vì sao ba hành động có semantics khác nhau.

Kết luận:

```text
DETACH:
    stop tracking object

REFRESH:
    reload persistent state

ORPHAN REMOVAL:
    delete child when removed from ownership association
```

## 31. Thực hành 6 — Ảnh hưởng tới entity dùng chung

Tạo `Invoice` có `@ManyToOne Customer`:

1. Tải Customer managed.
2. Sửa tên Customer nhưng chưa flush.
3. Tải Invoice liên kết với Customer.
4. Bật REFRESH cascade trên `Invoice.customer` trong một cấu hình thử.
5. Gọi `em.refresh(invoice)`; quan sát tên Customer trong context.
6. Bỏ REFRESH cascade và chạy lại.
7. Bật DETACH cascade trên `Invoice.customer` trong cấu hình thử khác.
8. Gọi `em.detach(invoice)`; kiểm tra `em.contains(customer)`.
9. Giải thích rủi ro đối với Customer do một module khác đang chỉnh sửa.

Không dùng `CascadeType.ALL` trên shared Customer chỉ để chạy bài này, vì ALL còn bao gồm REMOVE.

## 32. Bảng quan sát thực nghiệm

| Kịch bản | Tác động trên object | SQL dự kiến về mặt ý nghĩa | Dữ liệu DB |
|---|---|---|---|
| Refresh Order không cascade | Order nạp state DB | SELECT parent | Không DELETE vì refresh |
| Refresh Order có REFRESH | Order và Lines được làm mới | SELECT parent và có thể SELECT child | Không DELETE vì refresh |
| Detach Order không cascade | Order detached; Lines có thể managed | Không chủ đích cập nhật DB | Row còn |
| Detach Order có DETACH | Order và Lines detached | Chi phí traversal tùy provider | Row còn |
| Sửa Line rồi refresh trước flush | Local value có thể bị ghi đè | SELECT | Giá trị DB được nạp lại |
| Sửa Line rồi detach trước flush | Ngừng tracking local value | Không nhất thiết UPDATE | Chỉnh sửa có thể không lưu |
| Sửa Line, flush, detach, commit | Object detached sau khi SQL đã phát | UPDATE | UPDATE có thể được commit |
| `clear()` | Tất cả managed entities detached | Không phải DELETE | Không bị xóa do clear |
| `close()` | Kết thúc context | Cleanup | Không bị xóa do close |
| Gỡ Line với orphanRemoval | Line rời aggregate | DELETE child | Row có thể bị xóa |
| Rollback transaction | SQL chưa commit bị hủy | ROLLBACK | Dữ liệu chưa commit không giữ |

Đây là bảng **ngữ nghĩa**, không phải một bản đo số SQL trên Hibernate/version cụ thể. Cần bật SQL logging và kiểm tra database từ context mới khi đánh giá kết quả.

## 33. Checklist trước khi thêm REFRESH/DETACH cascade

| Câu hỏi | Điều cần quyết định |
|---|---|
| Child có thuộc riêng một aggregate không? | Cascade dễ hợp lý hơn khi ownership rõ |
| Entity có được chia sẻ ở nơi khác không? | Tránh lan truyền ngoài dự kiến |
| Refresh parent có thể ghi đè local edits của child không? | Cần quyết định rõ scope làm mới |
| Chỉ cần làm mới một child? | Có thể gọi `em.refresh(child)` |
| Đã có flush trước refresh chưa? | Refresh không undo SQL đã flush |
| Có thay đổi pending trước detach không? | Chúng có thể không được lưu |
| Detach parent nhưng child vẫn managed có chấp nhận được không? | Nếu không, cần cascade DETACH/chọn scope khác |
| Có orphanRemoval không? | Phân biệt unlink/delete với detach |
| Association lazy/graph lớn không? | Cân nhắc SQL/memory traversal |
| Có context transaction-scoped không? | Entity có thể tự detached khi context kết thúc |
| Có nhiều threads hay requests không? | EntityManager không được chia sẻ đồng thời tùy tiện |
| Có optimistic locking không? | Refresh không tự giải quyết conflict |
| Có shared Customer/Product không? | Cẩn thận cascade trên ManyToOne/ManyToMany |
| Có trả API entity detached không? | Ưu tiên DTO |
| Có test với/không cascade không? | Quan sát chính xác state và SQL |

## 34. Câu hỏi ôn tập

1. `CascadeType.REFRESH` lan truyền thao tác EntityManager nào?
2. `CascadeType.DETACH` lan truyền thao tác nào?
3. Sau `em.refresh(entity)`, entity còn managed không?
4. Sau `em.detach(entity)`, setter có tự được dirty checking không?
5. Vì sao refresh có thể làm mất local changes chưa flush?
6. Vì sao detach không phải thao tác lưu?
7. Vì sao detach không tự xóa FK hoặc row child?
8. Cascade có hướng theo owning side FK hay theo association khai báo cascade?
9. Vì sao `mappedBy` không cản REFRESH/DETACH cascade từ parent xuống child?
10. Nếu Order có REFRESH nhưng không DETACH, điều gì xảy ra khi detach Order?
11. Nếu Order có DETACH nhưng không REFRESH, điều gì xảy ra khi refresh Order?
12. `CascadeType.ALL` có bao gồm REFRESH, DETACH và REMOVE không?
13. Vì sao ALL trên `@ManyToOne Customer` có thể nguy hiểm?
14. Nếu không có DETACH cascade, child đã managed có thể vẫn managed sau detach parent không?
15. `clear()` khác `detach()` về phạm vi thế nào?
16. `close()` khác `clear()` ở khả năng tiếp tục dùng EM?
17. Flush rồi detach có rollback SQL đã flush không?
18. Refresh sau flush có chắc chắn phục hồi database về state trước transaction không?
19. OrphanRemoval có tự tạo REFRESH/DETACH cascade không?
20. Có thể dùng refresh để undo orphan removal đã lên lịch không?
21. Vì sao REFRESH không thay thế rollback một transaction lỗi?
22. Vì sao DETACH không thay thế rollback?
23. Entity detached có thể có ID và Java reference còn nguyên không?
24. Khi muốn lưu detached changes, `merge` khác `refresh` thế nào?
25. REFRESH có thể ảnh hưởng những shared entities ra sao?
26. DETACH có thể ảnh hưởng dirty checking của shared entities ra sao?
27. Lazy collection có thể gặp vấn đề gì sau detach?
28. REFRESH trên graph lớn có thể phát sinh chi phí gì?
29. Optimistic locking có vai trò gì khi một context giữ stale entity?
30. Khi nào nên dùng DTO thay vì trả entity detached cho API?

## 35. Tóm tắt

```text
                 Order [managed]
                      |
                      | @OneToMany(cascade = {REFRESH, DETACH})
                      v
                 Line [managed]

REFRESH:
  em.refresh(order)
    -> Order được làm mới từ DB
    -> Line cũng được refresh nếu mapping có REFRESH
    -> Các entity vẫn managed
    -> Local edits chưa flush có thể bị ghi đè

DETACH:
  em.detach(order)
    -> Order detached
    -> Line cũng detached nếu mapping có DETACH
    -> Không tự DELETE, COMMIT, ROLLBACK
    -> Các field Java có thể vẫn còn nhưng không được track

ORPHAN REMOVAL:
  order.removeLine(line)
    -> Child bị gỡ khỏi association sở hữu
    -> Managed orphan có thể bị DELETE khi flush/commit

TRANSACTION:
  tx.rollback()
    -> Hủy thay đổi DB chưa commit
    -> Không phải REFRESH hoặc DETACH
```

| Nhu cầu | Cơ chế |
|---|---|
| Nạp lại state của managed entity | `em.refresh(entity)` |
| Lan truyền việc nạp lại state | `CascadeType.REFRESH` |
| Ngừng tracking một entity | `em.detach(entity)` |
| Lan truyền việc ngừng tracking | `CascadeType.DETACH` |
| Ngừng tracking toàn persistence context | `em.clear()` |
| Kết thúc application-managed context | `em.close()` |
| Hủy transaction chưa commit | `tx.rollback()` |
| Xóa managed entity | `em.remove(entity)` |
| Xóa child rời aggregate | `orphanRemoval=true` |
| Lưu thay đổi từ detached entity | Load managed rồi cập nhật hoặc `em.merge(...)` có kiểm soát |

**Nguyên tắc cuối cùng:** **REFRESH lan truyền việc làm mới persistent state; DETACH lan truyền việc ngừng quản lý entity.** Chúng không phải cơ chế xóa quan hệ, xóa bản ghi hay commit/rollback. Chỉ cấu hình cascade khi việc lan truyền **đúng với vòng đời nghiệp vụ**, tránh ảnh hưởng các entity độc lập được dùng chung, và kiểm soát chặt các thay đổi chưa flush trước khi làm mới hoặc tách entity graph.

